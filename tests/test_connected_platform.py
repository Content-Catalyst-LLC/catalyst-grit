from __future__ import annotations

import copy
import json
from pathlib import Path
import sqlite3

import pytest
from jsonschema import validate

from catalyst_grit import (
    ConnectedPlatformService,
    InstitutionalAPI,
    PLATFORM_CONTRACT,
    PORTABLE_PLATFORM_FORMAT,
    PublicationService,
    SQLiteWorkspaceRepository,
)
from catalyst_grit.cli import main

ROOT = Path(__file__).resolve().parents[1]


def sample() -> dict:
    return json.loads((ROOT / "examples/grit_record_input.json").read_text())


def setup_workspace(repo: SQLiteWorkspaceRepository):
    project = repo.create_project("Connected recovery", owner_id="owner")
    saved = repo.save_record(project["project_id"], sample(), actor_id="owner")
    return project, saved["record"]["record_id"]


def complete_connected_workflow(repo: SQLiteWorkspaceRepository, project_id: str, record_id: str):
    service = ConnectedPlatformService(repo)
    workflow = service.create_workflow(record_id, actor_id="owner")
    assert workflow["status"] == "needs_review"
    assert workflow["current_step_key"] == "recovery_assessment"
    workflow = service.review_step(workflow["workflow_id"], "recovery_assessment", reviewer_id="owner", notes="Assessment reviewed in context.")

    checkpoint = repo.create_checkpoint(project_id, "Connected checkpoint", record_id=record_id, scheduled_for="2026-07-24")
    revised = copy.deepcopy(sample())
    revised["input"]["pressure"]["level"] = 6
    repo.create_reassessment(record_id, revised, observed_summary="Ownership clarity reduced pressure.", checkpoint_id=checkpoint["checkpoint_id"], changed_assumptions=["Decision ownership is now explicit"], actor_id="owner")
    repo.create_system_change(project_id, "One review channel", "Route review comments through one named owner.", source_record_ids=[record_id], evidence_note="Retrospective and reassessment evidence.", decision="piloting", actor_id="owner")
    repo.build_decision_handoff(record_id, actor_id="owner")
    snapshot = repo.capture_monitoring_snapshot(record_id, observed_at="2026-07-25T12:00:00Z", actor_id="owner")
    dashboard = repo.record_monitoring_dashboard(record_id)
    repo.review_monitoring_summary(project_id, dashboard["summary_hash"], scope="record", status="approved", reviewer_id="owner", record_id=record_id, notes="Monitoring context reviewed.")
    publication = PublicationService(repo).generate("recovery_brief", project_id=project_id, record_id=record_id, export_format="json", redaction_policy="internal", visibility="internal", actor_id="owner")
    assert publication.publication["publication_id"]
    workflow = service.refresh_workflow(workflow["workflow_id"], actor_id="owner")
    return service, workflow, snapshot


def test_migration_009_tables_and_append_only_guards(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "platform.sqlite3") as repo:
        assert repo.health()["migrations"]["current"] == 9
        tables = {row[0] for row in repo.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"connected_workflows", "connected_workflow_steps", "connected_workflow_events", "artifact_connections", "artifact_connection_events", "portable_platform_snapshots", "platform_sync_events"} <= tables
        project, record_id = setup_workspace(repo)
        workflow = ConnectedPlatformService(repo).create_workflow(record_id)
        event_id = workflow["events"][0]["workflow_event_id"]
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repo.connection.execute("UPDATE connected_workflow_events SET notes='changed' WHERE workflow_event_id=?", (event_id,))


def test_connected_workflow_is_traceable_and_completes_end_to_end(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "workflow.sqlite3") as repo:
        project, record_id = setup_workspace(repo)
        service, workflow, snapshot = complete_connected_workflow(repo, project["project_id"], record_id)
        assert workflow["contract_version"] == PLATFORM_CONTRACT
        assert workflow["status"] == "completed"
        assert workflow["progress"] == {"completed": 12, "total": 12, "percent": 100.0}
        assert all(step["source_hash"] for step in workflow["steps"])
        assert next(step for step in workflow["steps"] if step["step_key"] == "monitoring_review")["source_id"] == snapshot["snapshot_id"]
        assert any(event["event_type"] == "reviewed" for event in workflow["events"])
        assert any("No character" in item for item in workflow["guardrails"])
        overview = service.platform_overview(project["project_id"])
        schema = json.loads((ROOT / "schemas/catalyst_grit_connected_platform.schema.json").read_text())
        validate(overview, schema)
        assert overview["workflow_status_counts"]["completed"] == 1
        assert overview["governance"]["automated_eligibility_allowed"] is False


def test_artifact_graph_preserves_hashes_and_exposes_conflicts(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "graph.sqlite3") as repo:
        project, record_id = setup_workspace(repo)
        record = repo.get_record(record_id, include_canonical=True)
        service = ConnectedPlatformService(repo)
        connection = service.connect_artifacts(
            project["project_id"],
            source_product="Catalyst Data",
            source_artifact_type="dataset",
            source_artifact_id="dataset-001",
            source_version="2.0.0",
            source_hash="a" * 64,
            target_product="Catalyst Grit",
            target_artifact_type="recovery_record",
            target_artifact_id=record_id,
            target_version="2.0.0",
            target_hash=record["current_revision_id"].replace("cgrv_", "")[:64].ljust(64, "0"),
            relation="informs",
            provenance=[{"route": "Catalyst Data → Catalyst Grit"}],
            actor_id="owner",
        )
        assert connection["validation_state"] == "valid"
        conflict = service.validate_connection(connection["connection_id"], source_hash="b" * 64, actor_id="reviewer", notes="Source changed after import.")
        assert conflict["validation_state"] == "conflict"
        assert [event["event_type"] for event in conflict["events"]] == ["created", "conflict_recorded"]
        overview = service.platform_overview(project["project_id"])
        assert overview["artifact_graph"]["conflict_count"] == 1


def test_portable_snapshot_verifies_offline_and_restores(tmp_path: Path):
    source_db = tmp_path / "source.sqlite3"
    target_db = tmp_path / "target.sqlite3"
    with SQLiteWorkspaceRepository(source_db) as repo:
        project, record_id = setup_workspace(repo)
        service = ConnectedPlatformService(repo)
        service.create_workflow(record_id, actor_id="owner")
        service.record_sync_event(project["project_id"], "Decision Studio", direction="outbound", status="completed", artifact_count=1, actor_id="owner")
        created = service.create_portable_snapshot(project["project_id"], record_id=record_id, actor_id="owner")
        assert created.bundle["format"] == PORTABLE_PLATFORM_FORMAT
        verification = service.verify_portable_bundle(created.bundle)
        assert verification == {
            "format": PORTABLE_PLATFORM_FORMAT,
            "supplied_hash": created.bundle["bundle_hash"],
            "calculated_hash": created.bundle["bundle_hash"],
            "verified": True,
            "network_required": False,
        }
        tampered = copy.deepcopy(created.bundle); tampered["workspace"]["project"]["title"] = "Changed"
        assert service.verify_portable_bundle(tampered)["verified"] is False
    with SQLiteWorkspaceRepository(target_db) as repo:
        restored = ConnectedPlatformService(repo).restore_portable_bundle(created.bundle, actor_id="restore-owner")
        assert restored["offline_restore"] is True
        assert restored["verification"]["verified"] is True
        assert repo.list_projects()
        assert repo.list_records(restored["import"]["project_id"])
        assert restored["restored_workflow_ids"]


def test_v2_api_scopes_workflow_overview_and_snapshot(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "api.sqlite3") as repo:
        project, record_id = setup_workspace(repo)
        reader = repo.create_api_client("Platform reader", scopes=["platform:read"], project_ids=[project["project_id"]])
        writer = repo.create_api_client("Platform operator", scopes=["platform:read", "platform:write", "platform:review", "platform:export"], project_ids=[project["project_id"]])
        api = InstitutionalAPI(repo)
        denied = api.handle("POST", "/v2/workflows", token=reader["token"], body={"record_id": record_id})
        assert denied.status == 403
        created = api.handle("POST", "/v2/workflows", token=writer["token"], body={"record_id": record_id})
        assert created.status == 200
        workflow_id = created.body["data"]["workflow_id"]
        overview = api.handle("GET", f"/v2/projects/{project['project_id']}/platform", token=reader["token"])
        assert overview.status == 200 and overview.body["data"]["workflow_count"] == 1
        reviewed = api.handle("POST", f"/v2/workflows/{workflow_id}/steps/recovery_assessment", token=writer["token"], body={"notes": "Reviewed"})
        assert reviewed.status == 200
        portable = api.handle("POST", f"/v2/projects/{project['project_id']}/portable-snapshots", token=writer["token"], body={"record_id": record_id})
        assert portable.status == 200
        assert portable.body["data"]["bundle"]["format"] == PORTABLE_PLATFORM_FORMAT
        assert api.handle("GET", "/v2/health").status == 200


def test_platform_cli_workflow_snapshot_verify_and_diagnostics(tmp_path: Path, capsys):
    db = tmp_path / "cli.sqlite3"
    with SQLiteWorkspaceRepository(db) as repo:
        project, record_id = setup_workspace(repo)
    assert main(["platform-workflow-start", "--database", str(db), record_id, "--actor", "owner"]) == 0
    workflow = json.loads(capsys.readouterr().out)
    assert workflow["contract_version"] == PLATFORM_CONTRACT
    output = tmp_path / "portable.json"
    assert main(["platform-snapshot", "--database", str(db), project["project_id"], "--record", record_id, "--output", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["snapshot"]["verification_state"] == "verified"
    assert main(["platform-verify", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["verified"] is True
    assert main(["platform-diagnostics", "--database", str(db)]) == 0
    diagnostics = json.loads(capsys.readouterr().out)
    assert diagnostics["migration_status"]["current"] == 9
    assert diagnostics["portable_offline_supported"] is True


def test_project_export_includes_connected_platform_state(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "export.sqlite3") as repo:
        project, record_id = setup_workspace(repo)
        service = ConnectedPlatformService(repo)
        service.create_workflow(record_id)
        service.record_sync_event(project["project_id"], "Knowledge Library", direction="outbound", status="completed", artifact_count=1)
        exported = repo.export_project(project["project_id"])
        connected = exported["connected_platform"]
        assert connected["contract"] == PLATFORM_CONTRACT
        assert connected["workflows"] and connected["sync_events"]
