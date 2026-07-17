import copy
import sqlite3
from pathlib import Path

import pytest
import json

from catalyst_grit import SQLiteWorkspaceRepository, WorkspaceError


def _request(example_request, record_id="cgr_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", created_at="2026-07-01T12:00:00Z", pressure=8, support=6):
    value = copy.deepcopy(example_request)
    value["metadata"]["record_id"] = record_id
    value["metadata"]["created_at"] = created_at
    value["metadata"]["updated_at"] = created_at
    value["input"]["pressure"]["level"] = pressure
    value["input"]["supports"]["level"] = support
    return value


def test_snapshot_is_traceable_append_only_and_reproducible(tmp_path: Path):
    example_request = json.loads((Path(__file__).resolve().parents[1] / "examples/grit_record_input.json").read_text())
    with SQLiteWorkspaceRepository(tmp_path / "monitor.sqlite3") as repo:
        project = repo.create_project("Monitoring")
        saved = repo.save_record(project["project_id"], _request(example_request))
        snapshot = repo.capture_monitoring_snapshot(saved["record"]["record_id"], observed_at="2026-07-02T12:00:00Z")
        assert snapshot["engine_version"] == "1.8.0"
        assert snapshot["source_trace"]["revision_id"] == saved["revision"]["revision_id"]
        assert snapshot["source_revision_hash"] == saved["revision"]["content_sha256"]
        assert snapshot["condition_metrics"]["pressure"] == 8
        assert snapshot["events"][0]["event_type"] == "captured"
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repo.connection.execute("UPDATE monitoring_snapshots SET recovery_score=99 WHERE snapshot_id=?", (snapshot["snapshot_id"],))


def test_sparse_and_sufficient_record_trends(tmp_path: Path):
    example_request = json.loads((Path(__file__).resolve().parents[1] / "examples/grit_record_input.json").read_text())
    with SQLiteWorkspaceRepository(tmp_path / "trends.sqlite3") as repo:
        project = repo.create_project("Trends")
        saved = repo.save_record(project["project_id"], _request(example_request))
        record_id = saved["record"]["record_id"]
        repo.capture_monitoring_snapshot(record_id, observed_at="2026-07-02T12:00:00Z")
        sparse = repo.record_trends(record_id)
        assert sparse["data_state"] == "sparse"
        assert sparse["confidence"]["state"] == "sparse_data"
        revised = _request(example_request, pressure=5, support=8)
        repo.revise_record(record_id, revised, reason="conditions changed")
        repo.capture_monitoring_snapshot(record_id, observed_at="2026-07-05T12:00:00Z")
        trends = repo.record_trends(record_id)
        assert trends["minimum_data_met"] is True
        assert trends["trends"]["pressure"]["direction"] == "improving"
        assert trends["trends"]["support"]["direction"] == "improving"
        assert trends["traceability"]["recalculated"] is False
        assert len(trends["traceability"]["revision_ids"]) == 2


def test_timeline_workflow_and_review(tmp_path: Path):
    example_request = json.loads((Path(__file__).resolve().parents[1] / "examples/grit_record_input.json").read_text())
    with SQLiteWorkspaceRepository(tmp_path / "timeline.sqlite3") as repo:
        project = repo.create_project("Timeline")
        saved = repo.save_record(project["project_id"], _request(example_request))
        record_id = saved["record"]["record_id"]
        checkpoint = repo.create_checkpoint(project["project_id"], "Review", record_id=record_id, scheduled_for="2026-07-03")
        repo.complete_checkpoint(checkpoint["checkpoint_id"])
        snapshot = repo.capture_monitoring_snapshot(record_id, observed_at="2026-07-04T12:00:00Z")
        snapshot = repo.annotate_monitoring_snapshot(snapshot["snapshot_id"], "Pressure fell after ownership was clarified.", signal_key="pressure")
        assert len(snapshot["events"]) == 2
        timeline = repo.recovery_timeline(record_id)
        assert {item["event_type"] for item in timeline["events"]} >= {"record_revision", "monitoring_snapshot", "checkpoint"}
        dashboard = repo.record_monitoring_dashboard(record_id)
        review = repo.review_monitoring_summary(project["project_id"], dashboard["summary_hash"], scope="record", status="reviewed", reviewer_id="reviewer", record_id=record_id)
        assert review["status"] == "reviewed"


def test_team_dashboard_enforces_privacy_threshold_and_never_ranks(tmp_path: Path):
    example_request = json.loads((Path(__file__).resolve().parents[1] / "examples/grit_record_input.json").read_text())
    with SQLiteWorkspaceRepository(tmp_path / "team-monitor.sqlite3") as repo:
        project = repo.create_project("Team monitoring", owner_id="owner")
        saved = repo.save_record(project["project_id"], _request(example_request), actor_id="owner")
        repo.capture_monitoring_snapshot(saved["record"]["record_id"], actor_id="owner")
        suppressed = repo.team_conditions_dashboard(project["project_id"], actor_id="owner")
        assert suppressed["privacy"]["suppressed"] is True
        assert suppressed["aggregate_conditions"] is None
        assert suppressed["individual_comparisons"] == []
        repo.add_team_member(project["project_id"], "member-2", "Member 2", status="active", consent_status="granted", actor_id="owner")
        repo.add_team_member(project["project_id"], "member-3", "Member 3", status="active", consent_status="granted", actor_id="owner")
        visible = repo.team_conditions_dashboard(project["project_id"], actor_id="owner")
        assert visible["privacy"]["threshold_met"] is True
        assert visible["aggregate_conditions"]["record_count"] == 1
        assert visible["individual_comparisons"] == []
        assert visible["governance"]["individual_ranking_allowed"] is False


def test_project_export_import_restores_monitoring(tmp_path: Path):
    example_request = json.loads((Path(__file__).resolve().parents[1] / "examples/grit_record_input.json").read_text())
    source = tmp_path / "source.sqlite3"; target = tmp_path / "target.sqlite3"
    with SQLiteWorkspaceRepository(source) as repo:
        project = repo.create_project("Export monitoring")
        saved = repo.save_record(project["project_id"], _request(example_request))
        repo.capture_monitoring_snapshot(saved["record"]["record_id"], observed_at="2026-07-02T12:00:00Z")
        dashboard = repo.project_monitoring_dashboard(project["project_id"])
        repo.review_monitoring_summary(project["project_id"], dashboard["summary_hash"], scope="project", status="approved", reviewer_id="owner")
        bundle = repo.export_project(project["project_id"])
        assert bundle["records"][0]["monitoring_snapshots"]
        assert bundle["monitoring_reviews"]
    with SQLiteWorkspaceRepository(target) as repo:
        result = repo.import_payload(bundle, actor_id="owner")
        assert result["monitoring_snapshots_imported"] == 1
        assert result["monitoring_reviews_imported"] == 1
        assert repo.health()["migrations"]["current"] == 7
