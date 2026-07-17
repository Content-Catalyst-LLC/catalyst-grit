from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import sqlite3

import pytest

from catalyst_grit import SQLiteWorkspaceRepository, WORKSPACE_FORMAT, WorkspaceError, generate_record

ROOT = Path(__file__).resolve().parents[1]


def request() -> dict:
    return json.loads((ROOT / "examples/grit_record_input.json").read_text())


def create_saved(repo: SQLiteWorkspaceRepository):
    project = repo.create_project("Recovery project", description="Private test workspace", owner_id="user-1")
    saved = repo.save_record(project["project_id"], request(), actor_id="user-1", reason="initial")
    return project, saved


def revised_request() -> dict:
    value = request()
    value["metadata"]["updated_at"] = "2026-07-18T12:00:00Z"
    value["input"]["capacity"]["clarity_level"] = 7
    value["input"]["next_steps"]["success_signal"] = "Decision owner confirmed and checkpoint completed."
    return value


def test_project_is_private_by_default(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "private.sqlite3") as repo:
        project = repo.create_project("Private recovery", owner_id="person-a", retention_days=30)
        assert project["visibility"] == "private"
        assert project["status"] == "active"
        assert project["retention_days"] == 30
        assert repo.list_projects() == [project]


def test_record_survives_repository_restart(tmp_path: Path):
    database = tmp_path / "restart.sqlite3"
    with SQLiteWorkspaceRepository(database) as repo:
        project, saved = create_saved(repo)
        record_id = saved["record"]["record_id"]
        expected = saved["revision"]["canonical"]
    with SQLiteWorkspaceRepository(database) as reopened:
        record = reopened.get_record(record_id, include_canonical=True)
        assert record["project_id"] == project["project_id"]
        assert record["visibility"] == "private"
        assert record["canonical"] == expected
        assert record["revision_number"] == 1


def test_identical_save_is_deduplicated(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "dedupe.sqlite3") as repo:
        project, first = create_saved(repo)
        second = repo.save_record(project["project_id"], request())
        assert second["deduplicated"] is True
        assert second["revision"]["revision_id"] == first["revision"]["revision_id"]
        assert len(repo.list_revisions(first["record"]["record_id"])) == 1


def test_changed_record_creates_append_only_revision(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "revision.sqlite3") as repo:
        _, first = create_saved(repo)
        record_id = first["record"]["record_id"]
        second = repo.revise_record(record_id, revised_request(), actor_id="user-2", reason="checkpoint reassessment")
        revisions = repo.list_revisions(record_id)
        assert [item["revision_number"] for item in revisions] == [1, 2]
        assert revisions[0]["canonical"]["normalized_input"]["capacity"]["clarity_level"] == 4.0
        assert revisions[1]["canonical"]["normalized_input"]["capacity"]["clarity_level"] == 7.0
        assert second["revision"]["created_by"] == "user-2"
        assert second["revision"]["reason"] == "checkpoint reassessment"
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repo.connection.execute("UPDATE record_revisions SET reason='changed' WHERE revision_id=?", (revisions[0]["revision_id"],))


def test_revision_delete_is_blocked_outside_guarded_purge(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "revision-delete.sqlite3") as repo:
        _, saved = create_saved(repo)
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repo.connection.execute("DELETE FROM record_revisions WHERE revision_id=?", (saved["revision"]["revision_id"],))


def test_compare_revisions_reports_changed_paths(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "compare.sqlite3") as repo:
        _, first = create_saved(repo)
        record_id = first["record"]["record_id"]
        repo.revise_record(record_id, revised_request())
        comparison = repo.compare_revisions(record_id, 1, 2)
        paths = {item["path"] for item in comparison["changes"]}
        assert "$.normalized_input.capacity.clarity_level" in paths
        assert "$.normalized_input.next_steps.success_signal" in paths
        assert comparison["from_revision"] == 1 and comparison["to_revision"] == 2


def test_actions_are_snapshotted_per_revision(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "actions.sqlite3") as repo:
        _, saved = create_saved(repo)
        record_id = saved["record"]["record_id"]
        first_actions = repo.list_actions(record_id, revision_number=1)
        assert len(first_actions) == 4
        changed = revised_request()
        changed["input"]["next_steps"]["actions"].append({"title": "Confirm recovery scope", "status": "planned", "owner": "project lead", "target_date": "2026-07-23"})
        repo.revise_record(record_id, changed)
        assert len(repo.list_actions(record_id, revision_number=1)) == 4
        assert len(repo.list_actions(record_id, revision_number=2)) == 5


def test_checkpoint_schedule_and_completion_are_auditable(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "checkpoint.sqlite3") as repo:
        project, saved = create_saved(repo)
        checkpoint = repo.create_checkpoint(project["project_id"], "72-hour review", record_id=saved["record"]["record_id"], scheduled_for="2026-07-20", actor_id="facilitator")
        assert checkpoint["status"] == "planned"
        assert checkpoint["revision_id"] == saved["revision"]["revision_id"]
        complete = repo.complete_checkpoint(checkpoint["checkpoint_id"], notes="Scope clarified", actor_id="facilitator")
        assert complete["status"] == "completed" and complete["completed_at"]
        history = repo.status_history("checkpoint", checkpoint["checkpoint_id"])
        assert [item["to_status"] for item in history] == ["planned", "completed"]
        assert {item["event_type"] for item in repo.audit_log(entity_type="checkpoint", entity_id=checkpoint["checkpoint_id"])} == {"checkpoint.created", "checkpoint.completed"}


def test_reviews_are_append_only(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "reviews.sqlite3") as repo:
        _, saved = create_saved(repo)
        review = repo.add_review(saved["record"]["record_id"], status="needs_review", reviewer_id="reviewer-a", notes="Confirm ownership")
        assert repo.list_reviews(saved["record"]["record_id"])[0]["notes"] == "Confirm ownership"
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repo.connection.execute("UPDATE reviews SET notes='rewritten' WHERE review_id=?", (review["review_id"],))


def test_duplicate_creates_new_draft_with_source_provenance(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "duplicate.sqlite3") as repo:
        project, saved = create_saved(repo)
        duplicate = repo.duplicate_record(saved["record"]["record_id"], actor_id="user-2")
        assert duplicate["record"]["record_id"] != saved["record"]["record_id"]
        canonical = duplicate["revision"]["canonical"]
        assert canonical["metadata"]["status"] == "draft"
        assert canonical["metadata"]["provenance"]["source_record_id"] == saved["record"]["record_id"]
        assert len(repo.list_records(project["project_id"])) == 2


def test_archive_creates_new_revision_without_overwriting_history(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "archive.sqlite3") as repo:
        project, saved = create_saved(repo)
        record_id = saved["record"]["record_id"]
        archived = repo.archive_record(record_id, actor_id="user-1")
        assert archived["record"]["status"] == "archived"
        assert archived["revision"]["revision_number"] == 2
        assert repo.list_records(project["project_id"]) == []
        assert len(repo.list_records(project["project_id"], include_archived=True)) == 1


def test_soft_delete_hides_record_but_preserves_history(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "delete.sqlite3") as repo:
        project, saved = create_saved(repo)
        record_id = saved["record"]["record_id"]
        deleted = repo.delete_record(record_id, reason="user requested deletion")
        assert deleted["status"] == "deleted" and deleted["deleted_at"]
        assert repo.list_records(project["project_id"], include_archived=True) == []
        assert repo.get_record(record_id, include_deleted=True)["revision_number"] == 1
        assert repo.status_history("record", record_id)[-1]["to_status"] == "deleted"


def test_permanent_purge_requires_confirmation_and_removes_content(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "purge.sqlite3") as repo:
        _, saved = create_saved(repo)
        record_id = saved["record"]["record_id"]
        with pytest.raises(WorkspaceError, match="confirm=True"):
            repo.purge_record(record_id)
        tombstone = repo.purge_record(record_id, confirm=True, actor_id="privacy-admin")
        assert tombstone["record_id"] == record_id
        with pytest.raises(WorkspaceError, match="record not found"):
            repo.get_record(record_id, include_deleted=True)
        event = repo.audit_log(entity_type="record_tombstone", entity_id=record_id)[-1]
        assert event["event_type"] == "record.purged"
        assert "canonical" not in event["payload"]


def test_retention_purge_removes_due_records_only(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "retention.sqlite3") as repo:
        project = repo.create_project("Retention")
        first = repo.save_record(project["project_id"], request())["record"]["record_id"]
        second_request = request(); second_request["metadata"]["record_id"] = "cgr_22222222222222222222222222222222"
        second = repo.save_record(project["project_id"], second_request)["record"]["record_id"]
        repo.set_retention(first, retention_until=(date.today() - timedelta(days=1)).isoformat())
        repo.set_retention(second, retention_until=(date.today() + timedelta(days=10)).isoformat())
        assert repo.purge_due_records() == [first]
        assert repo.get_record(second)["record_id"] == second


def test_export_import_round_trip_preserves_canonical_record(tmp_path: Path):
    source = tmp_path / "source.sqlite3"; target = tmp_path / "target.sqlite3"
    with SQLiteWorkspaceRepository(source) as repo:
        project, saved = create_saved(repo)
        record_id = saved["record"]["record_id"]
        repo.revise_record(record_id, revised_request())
        repo.create_checkpoint(project["project_id"], "Review", record_id=record_id, scheduled_for="2026-07-21")
        repo.add_review(record_id, status="in_review", reviewer_id="reviewer")
        bundle = repo.export_record(record_id)
        assert bundle["format"] == WORKSPACE_FORMAT
        expected = bundle["current_record"]
    with SQLiteWorkspaceRepository(target) as imported:
        result = imported.import_payload(bundle)
        actual = imported.get_record(record_id, include_canonical=True)["canonical"]
        assert result["project_id"] == project["project_id"]
        assert actual == expected
        assert len(imported.list_revisions(record_id)) == 2
        assert len(imported.list_checkpoints(project["project_id"], record_id=record_id)) == 1


def test_import_accepts_v1_flat_request(tmp_path: Path):
    legacy = json.loads((ROOT / "examples/grit_record_v1_0_input.json").read_text())
    with SQLiteWorkspaceRepository(tmp_path / "legacy.sqlite3") as repo:
        project = repo.create_project("Legacy import")
        saved = repo.import_payload(legacy, project_id=project["project_id"])
        canonical = saved["revision"]["canonical"]
        assert canonical["metadata"]["provenance"]["source"] == "migration"
        assert canonical["metadata"]["provenance"]["source_schema_version"] == "1.0.1"


def test_import_preserves_v1_1_canonical_engine_provenance(tmp_path: Path):
    canonical = generate_record(request()).to_dict()
    canonical["metadata"]["schema_version"] = "1.1.0"
    canonical["metadata"]["engine_version"] = "1.1.0"
    canonical["findings"]["methodology"]["profile_version"] = "1.1.0"
    canonical["findings"]["methodology"]["engine_version"] = "1.1.0"
    with SQLiteWorkspaceRepository(tmp_path / "v11.sqlite3") as repo:
        project = repo.create_project("v1.1 import")
        saved = repo.import_payload(canonical, project_id=project["project_id"])
        assert saved["revision"]["schema_version"] == "1.1.0"
        assert saved["revision"]["engine_version"] == "1.1.0"
        assert saved["revision"]["canonical"] == canonical


def test_health_reports_integrity_migrations_and_counts(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "health.sqlite3") as repo:
        create_saved(repo)
        health = repo.health()
        assert health["integrity"] == "ok"
        assert health["migrations"]["current"] == 2
        assert health["counts"]["projects"] == 1
        assert health["counts"]["record_revisions"] == 1
        assert health["private_by_default"] is True
