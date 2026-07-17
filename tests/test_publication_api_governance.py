import csv
import io
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from catalyst_grit import InstitutionalAPI, PublicationService, SQLiteWorkspaceRepository, WorkspaceError, apply_redaction
from catalyst_grit.cli import main

ROOT = Path(__file__).resolve().parents[1]


def _setup(repo: SQLiteWorkspaceRepository):
    project = repo.create_project("Institutional recovery", owner_id="owner")
    request = json.loads((ROOT / "examples/grit_record_input.json").read_text())
    saved = repo.save_record(project["project_id"], request, actor_id="owner")
    record_id = saved["record"]["record_id"]
    repo.capture_monitoring_snapshot(record_id, observed_at="2026-07-18T12:00:00Z", actor_id="owner")
    repo.add_evidence(project["project_id"], "Approved dataset", evidence_type="dataset", record_id=record_id, source_uri="https://private.example/data", source_product="Catalyst Data", source_version="1.12.0", strength="moderate", actor_id="owner")
    return project, record_id


def test_migration_008_tables_and_append_only_guards(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "governance.sqlite3") as repo:
        assert repo.health()["migrations"]["current"] == 9
        project, _ = _setup(repo)
        review = repo.record_access_review(project["project_id"], "project", project["project_id"], "approved", reviewer_id="owner")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repo.connection.execute("UPDATE access_reviews SET notes='changed' WHERE access_review_id=?", (review["access_review_id"],))
        event = repo.record_api_audit(None, "anonymous", "GET", "/v1/private", 401, "hash", {})
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repo.connection.execute("UPDATE api_audit_events SET response_status=200 WHERE api_event_id=?", (event["api_event_id"],))


def test_recovery_brief_formats_round_trip_and_pdf_handoff(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "publication.sqlite3") as repo:
        project, record_id = _setup(repo)
        service = PublicationService(repo)
        json_result = service.generate("recovery_brief", project_id=project["project_id"], record_id=record_id, export_format="json", actor_id="owner")
        assert json.loads(json_result.content)["content_hash"] == json_result.publication["content_hash"]
        assert json_result.mime_type == "application/json"
        jsonld = service.generate("recovery_brief", project_id=project["project_id"], record_id=record_id, export_format="jsonld", persist=False)
        assert json.loads(jsonld.content)["@type"] == "cg:RecoveryPublication"
        markdown = service.generate("recovery_brief", project_id=project["project_id"], record_id=record_id, export_format="markdown", persist=False)
        assert "Recovery State" in markdown.content
        html = service.generate("recovery_brief", project_id=project["project_id"], record_id=record_id, export_format="html", persist=False)
        assert html.content.startswith("<!doctype html>")
        csv_result = service.generate("action_plan", project_id=project["project_id"], record_id=record_id, export_format="csv", persist=False)
        rows = list(csv.DictReader(io.StringIO(csv_result.content)))
        assert rows and rows[0]["table"] == "actions"
        pdf_request = service.generate("recovery_brief", project_id=project["project_id"], record_id=record_id, export_format="pdf_request", persist=False)
        assert json.loads(pdf_request.content)["rendering_layer"] == "Sustainable Catalyst publication layer"


def test_deterministic_publication_bundle_contains_manifest_and_checksums(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "bundle.sqlite3") as repo:
        project, record_id = _setup(repo)
        service = PublicationService(repo)
        result = service.generate("action_plan", project_id=project["project_id"], record_id=record_id, persist=False)
        one = service.write_bundle(result.publication, tmp_path / "one.zip")
        two = service.write_bundle(result.publication, tmp_path / "two.zip")
        assert one.read_bytes() == two.read_bytes()
        with zipfile.ZipFile(one) as archive:
            names = set(archive.namelist())
            assert {"manifest.json", "SHA256SUMS", "publication.json", "publication.jsonld", "publication.md", "publication.html", "publication.csv", "publication.pdf-request.json"} <= names
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["format"] == "catalyst-grit-publication-bundle/1.0"
            checksums = archive.read("SHA256SUMS").decode()
            assert "publication.json" in checksums


def test_public_redaction_masks_identity_and_removes_private_fields():
    source = {
        "owner_id": "owner@example.com",
        "actor_id": "person-1",
        "source_uri": "https://private.example/source",
        "user_input": {"notes": "private"},
        "team_perspectives": [{"sharing_scope": "private", "content": "private contribution"}],
        "safe": "retained",
    }
    redacted = apply_redaction(source, "public")
    assert redacted["owner_id"].startswith("subject-")
    assert redacted["actor_id"].startswith("subject-")
    assert "source_uri" not in redacted and "user_input" not in redacted and "team_perspectives" not in redacted
    assert redacted["safe"] == "retained"
    assert source["owner_id"] == "owner@example.com"


def test_publication_persistence_and_append_only_events(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "events.sqlite3") as repo:
        project, record_id = _setup(repo)
        result = PublicationService(repo).generate("monitoring_summary", project_id=project["project_id"], record_id=record_id, export_format="html", redaction_policy="internal", visibility="internal", actor_id="owner")
        stored = repo.get_publication_artifact(result.publication["publication_id"])
        assert stored["content_hash"] == result.publication["content_hash"]
        event = repo.add_publication_event(stored["publication_id"], "reviewed", actor_id="reviewer", notes="Reviewed for internal circulation")
        assert event["event_type"] == "reviewed"
        assert [item["event_type"] for item in repo.get_publication_artifact(stored["publication_id"])["events"]] == ["created", "reviewed"]
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repo.connection.execute("UPDATE publication_events SET notes='changed' WHERE publication_event_id=?", (event["publication_event_id"],))


def test_api_auth_scope_project_rate_limit_and_audit(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "api.sqlite3") as repo:
        project, record_id = _setup(repo)
        other = repo.create_project("Other", owner_id="owner")
        created = repo.create_api_client("Institutional reader", scopes=["records:read"], project_ids=[project["project_id"]], rate_limit_per_minute=2, actor_id="owner")
        token = created["token"]
        assert "token_hash" not in repo.get_api_client(created["client_id"])
        api = InstitutionalAPI(repo)
        unauthorized = api.handle("GET", f"/v1/records/{record_id}")
        assert unauthorized.status == 401
        first = api.handle("GET", f"/v1/records/{record_id}", token=token)
        assert first.status == 200 and first.body["data"]["record_id"] == record_id
        forbidden_project = api.handle("GET", f"/v1/projects/{other['project_id']}/records", token=token)
        assert forbidden_project.status == 403
        rate_limited = api.handle("GET", f"/v1/records/{record_id}", token=token)
        assert rate_limited.status == 429
        audits = repo.list_api_audit_events(client_id=created["client_id"])
        assert {item["response_status"] for item in audits} >= {200, 403, 429}
        repo.revoke_api_client(created["client_id"], actor_id="owner")
        assert api.handle("GET", f"/v1/records/{record_id}", token=token).status == 401


def test_api_publication_route_requires_write_scope(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "api-publication.sqlite3") as repo:
        project, record_id = _setup(repo)
        reader = repo.create_api_client("Reader", scopes=["records:read"], project_ids=[project["project_id"]])
        publisher = repo.create_api_client("Publisher", scopes=["publications:write"], project_ids=[project["project_id"]])
        body = {"project_id": project["project_id"], "record_id": record_id, "report_type": "recovery_brief", "format": "json", "redaction_policy": "internal"}
        api = InstitutionalAPI(repo)
        assert api.handle("POST", "/v1/publications", token=reader["token"], body=body).status == 403
        response = api.handle("POST", "/v1/publications", token=publisher["token"], body=body)
        assert response.status == 200
        assert response.body["data"]["publication"]["redaction_policy"] == "internal"


def test_versioned_policies_access_reviews_and_export_import(tmp_path: Path):
    source = tmp_path / "source.sqlite3"; target = tmp_path / "target.sqlite3"
    with SQLiteWorkspaceRepository(source) as repo:
        project, _ = _setup(repo)
        first = repo.set_institutional_policy("export_redaction", {"default": "internal"}, project_id=project["project_id"], actor_id="owner")
        second = repo.set_institutional_policy("export_redaction", {"default": "public", "human_review": True}, project_id=project["project_id"], actor_id="owner")
        assert first["version"] == 1 and repo.get_institutional_policy(first["policy_id"])["status"] == "retired"
        assert second["version"] == 2 and second["status"] == "active"
        repo.record_access_review(project["project_id"], "project", project["project_id"], "approved", reviewer_id="owner", scopes=["records:read"], next_review_at="2027-01-01T00:00:00Z")
        bundle = repo.export_project(project["project_id"])
        assert bundle["institutional_policies"] and bundle["access_reviews"]
    with SQLiteWorkspaceRepository(target) as repo:
        imported = repo.import_payload(bundle, actor_id="owner")
        assert imported["institutional_policies_imported"] == 2
        assert imported["access_reviews_imported"] == 1


def test_methodology_and_schema_governance(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "methodology.sqlite3") as repo:
        profile = json.loads((ROOT / "methodology/recovery-profile-v2.0.0.json").read_text())
        registered = repo.register_methodology("cg-recovery-conditions", "2.0.0", profile, status="approved", approved_by="methodology-board", effective_at="2026-07-17T00:00:00Z")
        assert registered["status"] == "approved" and len(registered["content_hash"]) == 64
        declaration = repo.declare_schema_deprecation("catalyst_grit_record", "1.7.0", replacement_version="2.0.0", status="deprecated", sunset_at="2027-07-17T00:00:00Z", migration_notes="Use canonical migration.")
        assert declaration["replacement_version"] == "2.0.0"
        compatibility = repo.schema_compatibility("catalyst_grit_record", "1.7.0")
        assert compatibility["migration_required"] is True and compatibility["supported"] is True
        assert repo.schema_compatibility("catalyst_grit_record", "2.0.0")["status"] == "supported"


def test_diagnostics_exposes_health_not_tokens_or_private_records(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "diagnostics.sqlite3") as repo:
        project, _ = _setup(repo)
        repo.set_institutional_policy("retention", {"days": 365}, project_id=project["project_id"])
        repo.create_api_client("Diagnostics client", scopes=["records:read"])
        diagnostics = repo.institutional_diagnostics()
        assert diagnostics["database_integrity"] == "ok"
        assert diagnostics["migration_status"]["current"] == 9
        assert diagnostics["active_policy_count"] == 1
        assert diagnostics["active_api_client_count"] == 1
        assert "token" not in json.dumps(diagnostics).lower()
        assert "current_record" not in diagnostics


def test_cli_publication_policy_and_diagnostics(tmp_path: Path, capsys):
    db = tmp_path / "cli.sqlite3"
    with SQLiteWorkspaceRepository(db) as repo:
        project, record_id = _setup(repo)
    output = tmp_path / "brief.md"
    assert main(["publication-generate", "--database", str(db), project["project_id"], "recovery_brief", "--record", record_id, "--format", "markdown", "--output", str(output)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert output.exists() and payload["content_hash"]
    config = tmp_path / "policy.json"; config.write_text(json.dumps({"default": "internal"}))
    assert main(["policy-set", "--database", str(db), "export_redaction", str(config), "--project", project["project_id"]]) == 0
    assert json.loads(capsys.readouterr().out)["version"] == 1
    assert main(["institution-diagnostics", "--database", str(db)]) == 0
    assert json.loads(capsys.readouterr().out)["migration_status"]["current"] == 9
