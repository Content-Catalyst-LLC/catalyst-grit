from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from catalyst_grit import SQLiteWorkspaceRepository, WorkspaceError

ROOT = Path(__file__).resolve().parents[1]


def request() -> dict:
    return json.loads((ROOT / "examples/grit_record_input.json").read_text())


def workspace(repo: SQLiteWorkspaceRepository):
    project = repo.create_project("Evidence project", owner_id="owner")
    saved = repo.save_record(project["project_id"], request(), actor_id="owner")
    return project, saved


def test_evidence_preserves_source_provenance_hash_and_events(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "evidence.sqlite3") as repo:
        project, saved = workspace(repo)
        item = repo.add_evidence(
            project["project_id"],
            "Dataset observation",
            evidence_type="dataset",
            content="Cycle time increased from five to eight days.",
            record_id=saved["record"]["record_id"],
            source_uri="https://example.test/datasets/cycle-time",
            source_artifact_id="dataset-42",
            source_product="Catalyst Data",
            source_version="1.12.0",
            provenance=[{"dataset_id": "dataset-42", "observation_id": "obs-7"}],
            strength="moderate",
            actor_id="owner",
        )
        assert item["content_hash"]
        assert item["provenance"][0]["observation_id"] == "obs-7"
        assert item["events"][0]["event_type"] == "created"
        reviewed = repo.review_evidence(item["evidence_id"], review_state="accepted", strength="strong", notes="Source and method verified", actor_id="reviewer")
        assert reviewed["review_state"] == "accepted" and reviewed["strength"] == "strong"
        assert [event["event_type"] for event in reviewed["events"]] == ["created", "reviewed"]


def test_reference_evidence_requires_uri_or_artifact_id(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "reference.sqlite3") as repo:
        project = repo.create_project("References")
        with pytest.raises(WorkspaceError, match="source URI or artifact ID"):
            repo.add_evidence(project["project_id"], "Missing source", evidence_type="reference_document")


def test_evidence_links_support_and_conflict_without_overwrite(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "links.sqlite3") as repo:
        project, saved = workspace(repo)
        assumption = repo.add_assumption(project["project_id"], "The reviewer is available this week", record_id=saved["record"]["record_id"])
        supporting = repo.add_evidence(project["project_id"], "Calendar note", content="Reviewer confirmed Friday.", record_id=saved["record"]["record_id"])
        conflicting = repo.add_evidence(project["project_id"], "Absence notice", content="Reviewer is unavailable Friday.", record_id=saved["record"]["record_id"], review_state="questioned")
        repo.link_evidence(supporting["evidence_id"], "assumption", assumption["assumption_id"], relation="supports")
        repo.link_evidence(conflicting["evidence_id"], "assumption", assumption["assumption_id"], relation="conflicts_with")
        ledger = repo.evidence_ledger(project["project_id"], record_id=saved["record"]["record_id"])
        assert ledger["evidence_count"] == 2
        assert ledger["conflict_count"] == 1
        assert len(repo.get_assumption(assumption["assumption_id"])["evidence_links"]) == 2


def test_assumption_lifecycle_is_explicit_and_append_only(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "assumptions.sqlite3") as repo:
        project, saved = workspace(repo)
        item = repo.add_assumption(project["project_id"], "One approval path will be accepted", record_id=saved["record"]["record_id"], uncertainty="Two leaders have not aligned", confidence=35, owner="project lead", review_due="2026-07-22", source_paths=["$.user_input.constraints.items[0]"])
        assert item["status"] == "active" and item["confidence"] == 35
        validated = repo.update_assumption(item["assumption_id"], status="validated", confidence=85, reason="Decision owner confirmed")
        assert validated["status"] == "validated"
        assert [event["to_status"] for event in validated["events"]] == ["active", "validated"]
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repo.connection.execute("UPDATE assumption_events SET reason='rewritten' WHERE assumption_id=?", (item["assumption_id"],))


def test_assumption_matrix_surfaces_review_attention(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "matrix.sqlite3") as repo:
        project = repo.create_project("Assumption matrix")
        repo.add_assumption(project["project_id"], "Low confidence", confidence=20)
        repo.add_assumption(project["project_id"], "Higher confidence", confidence=80)
        matrix = repo.assumption_matrix(project["project_id"])
        assert matrix["active_count"] == 2
        assert matrix["review_attention_count"] == 1


def test_handoff_contract_preserves_snapshot_provenance_and_hash(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "handoff.sqlite3") as repo:
        project, saved = workspace(repo)
        handoff = repo.create_handoff(
            project["project_id"],
            source_product="Catalyst Canvas",
            source_version="2.0.0",
            target_product="Catalyst Grit",
            artifact_type="stakeholder_context",
            artifact_id="canvas-artifact-7",
            payload={"stakeholders": ["project lead", "reviewer"], "assumptions": ["approval path is stable"]},
            record_id=saved["record"]["record_id"],
            provenance=[{"project_id": "canvas-project-2", "revision": 4}],
        )
        assert handoff["validation_state"] == "valid"
        assert handoff["content_hash"]
        assert handoff["events"][0]["event_type"] == "created"
        assert handoff["provenance"][0]["revision"] == 4


def test_live_handoff_requires_uri_and_conflict_detection(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "live.sqlite3") as repo:
        project = repo.create_project("Live reference")
        with pytest.raises(WorkspaceError, match="live references require"):
            repo.create_handoff(project["project_id"], source_product="Knowledge Library", source_version="4.0.0", target_product="Catalyst Grit", artifact_type="reference_document", artifact_id="doc-1", reference_mode="live_reference")
        handoff = repo.create_handoff(project["project_id"], source_product="Knowledge Library", source_version="4.0.0", target_product="Catalyst Grit", artifact_type="reference_document", artifact_id="doc-1", reference_mode="live_reference", source_uri="https://example.test/library/doc-1", payload={"version": 1})
        conflict = repo.validate_handoff(handoff["handoff_id"], payload={"version": 2}, conflict_notes="Source changed")
        assert conflict["validation_state"] == "conflict"
        assert conflict["events"][-1]["event_type"] == "conflict_recorded"


def test_handoff_can_be_marked_stale_without_deleting_snapshot(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "stale.sqlite3") as repo:
        project = repo.create_project("Stale")
        handoff = repo.create_handoff(project["project_id"], source_product="Research Librarian", source_version="7.0.0", target_product="Catalyst Grit", artifact_type="source_discovery", artifact_id="search-1", payload={"sources": ["a"]})
        stale = repo.validate_handoff(handoff["handoff_id"], state="stale", conflict_notes="Source index is older than the review date")
        assert stale["payload"] == {"sources": ["a"]}
        assert stale["validation_state"] == "stale"


def test_decision_studio_packet_contains_traceable_evidence_assumptions_and_actions(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "decision.sqlite3") as repo:
        project, saved = workspace(repo)
        record_id = saved["record"]["record_id"]
        evidence = repo.add_evidence(project["project_id"], "Decision log", content="The project lead owns final approval.", record_id=record_id, strength="strong", review_state="accepted")
        assumption = repo.add_assumption(project["project_id"], "The revised scope can ship within seven days", record_id=record_id, confidence=60)
        repo.link_evidence(evidence["evidence_id"], "assumption", assumption["assumption_id"], relation="supports")
        packet = repo.build_decision_handoff(record_id)
        assert packet["contract"] == "sustainable-catalyst-decision-handoff/1.0"
        assert packet["source"]["version"] == "1.9.0"
        assert packet["evidence"][0]["evidence_id"] == evidence["evidence_id"]
        assert packet["assumptions"][0]["assumption_id"] == assumption["assumption_id"]
        assert packet["actions"]
        assert packet["handoff_id"] == repo.list_handoffs(project["project_id"], target_product="Decision Studio")[0]["handoff_id"]


def test_project_export_import_round_trip_includes_evidence_assumptions_and_handoffs(tmp_path: Path):
    source = tmp_path / "source.sqlite3"; target = tmp_path / "target.sqlite3"
    with SQLiteWorkspaceRepository(source) as repo:
        project, saved = workspace(repo); record_id = saved["record"]["record_id"]
        repo.add_evidence(project["project_id"], "Lab analysis", evidence_type="analysis", content="Sensitivity analysis complete.", record_id=record_id, source_product="Sustainable Catalyst Lab", source_version="0.36.2")
        repo.add_assumption(project["project_id"], "The sensitivity range is adequate", record_id=record_id, confidence=70)
        repo.create_handoff(project["project_id"], source_product="Sustainable Catalyst Lab", source_version="0.36.2", target_product="Catalyst Grit", artifact_type="analysis_result", artifact_id="analysis-9", payload={"range": [1, 4]}, record_id=record_id)
        bundle = repo.export_project(project["project_id"])
        assert bundle["evidence_ledger"]["evidence_count"] == 1
        assert bundle["assumption_matrix"]["assumption_count"] == 1
    with SQLiteWorkspaceRepository(target) as repo:
        result = repo.import_payload(bundle)
        assert result["evidence_items_imported"] >= 1
        assert result["assumptions_imported"] >= 1
        assert result["handoffs_imported"] >= 1
        assert len(repo.list_evidence(project["project_id"])) >= 1
        assert len(repo.list_assumptions(project["project_id"])) >= 1
        assert len(repo.list_handoffs(project["project_id"])) >= 1


def test_health_reports_v17_tables(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "health.sqlite3") as repo:
        health = repo.health()
        assert health["migrations"]["current"] == 8
        for table in ("evidence_items", "evidence_events", "evidence_links", "assumptions", "assumption_events", "handoff_artifacts", "handoff_events"):
            assert health["counts"][table] == 0
