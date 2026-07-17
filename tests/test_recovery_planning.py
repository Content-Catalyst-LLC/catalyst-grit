import copy
import json
from pathlib import Path

import pytest

from catalyst_grit import GritValidationError, SQLiteWorkspaceRepository, generate_record
from catalyst_grit.storage import WorkspaceError

ROOT = Path(__file__).resolve().parents[1]


def sample():
    return json.loads((ROOT / "examples/grit_record_input.json").read_text())


def saved_workspace(tmp_path):
    repo = SQLiteWorkspaceRepository(tmp_path / "planning.sqlite3")
    project = repo.create_project("Recovery planning")
    saved = repo.save_record(project["project_id"], sample())
    return repo, project, saved


def test_plan_has_owned_next_action_checkpoint_and_horizons():
    plan = generate_record(sample()).findings["recovery_plan"]
    assert plan["smallest_recoverable_next_step"]["owner"] == "project lead"
    assert plan["checkpoint"]["scheduled_for"] == "2026-07-24"
    assert set(plan["horizons"]) == {"24_hours", "72_hours", "7_days", "longer_term"}
    assert plan["scope_decision"]["decision"] == "reduce_scope"
    assert any(item["action_key"] == "stakeholder-review" and item["depends_on"] == ["document-assumptions", "recovery-task"] for item in plan["dependency_sequence"])


def test_blocked_action_requires_support_or_dependency_description():
    value = sample()
    value["input"]["response"]["actions"][0]["status"] = "blocked"
    value["input"]["response"]["actions"][0]["blocked_reason"] = ""
    with pytest.raises(GritValidationError) as error:
        generate_record(value)
    assert error.value.issues[0].code == "blocked_reason_required"


def test_completed_action_requires_completion_evidence():
    value = sample()
    value["input"]["response"]["actions"][0]["status"] = "completed"
    value["input"]["response"]["actions"][0]["completion_evidence"] = ""
    with pytest.raises(GritValidationError) as error:
        generate_record(value)
    assert error.value.issues[0].code == "completion_evidence_required"


def test_v13_plan_receives_non_destructive_compatibility_defaults():
    value = sample()
    value["metadata"]["schema_version"] = "1.3.0"
    value["input"]["next_steps"]["checkpoint_date"] = None
    for section in ("response", "next_steps"):
        for action in value["input"][section]["actions"]:
            action["owner"] = None
    plan = generate_record(value).findings["recovery_plan"]
    assert plan["smallest_recoverable_next_step"]["owner"] == "self"
    assert plan["checkpoint"]["scheduled_for"] == "2026-07-24"
    assert len(plan["compatibility_defaults"]) == 2


def test_action_status_changes_are_append_only_and_non_punitive(tmp_path):
    repo, _, saved = saved_workspace(tmp_path)
    try:
        record_id = saved["record"]["record_id"]
        action = repo.list_actions(record_id)[0]
        blocked = repo.update_action(action["action_id"], status="blocked", blocked_reason="Waiting for a named decision owner", escalation_path="program sponsor")
        assert blocked["attention_state"] == "blocked_needs_support"
        assert "without assigning blame" in blocked["message"]
        completed = repo.update_action(action["action_id"], status="completed", completion_evidence="Decision owner recorded in the decision log")
        assert completed["status"] == "completed"
        history = repo.action_history(action["action_id"])
        assert [item["to_status"] for item in history] == ["planned", "blocked", "completed"]
        with pytest.raises(Exception):
            repo.connection.execute("UPDATE action_events SET reason='changed'")
    finally:
        repo.close()


def test_past_target_action_is_visible_as_review_signal(tmp_path):
    repo, _, saved = saved_workspace(tmp_path)
    try:
        action = repo.list_actions(saved["record"]["record_id"], as_of="2026-07-30")[0]
        assert action["attention_state"] == "target_date_passed"
        assert action["days_past_target"] == 9
        assert "review capacity" in action["message"]
    finally:
        repo.close()


def test_blocker_and_escalation_log_lifecycle(tmp_path):
    repo, _, saved = saved_workspace(tmp_path)
    try:
        record_id = saved["record"]["record_id"]
        action_id = repo.list_actions(record_id)[0]["action_id"]
        blocker = repo.add_blocker(record_id, "Decision ownership unresolved", action_id=action_id, required_support="Sponsor decision", escalation_path="program sponsor")
        escalated = repo.update_blocker(blocker["blocker_id"], status="escalated")
        assert escalated["status"] == "escalated"
        resolved = repo.update_blocker(blocker["blocker_id"], status="resolved", notes="Owner named")
        assert resolved["resolved_at"]
        assert len(repo.status_history("blocker", blocker["blocker_id"])) == 2
    finally:
        repo.close()


def test_reassessment_creates_revision_compares_plan_and_carries_work(tmp_path):
    repo, project, saved = saved_workspace(tmp_path)
    try:
        record_id = saved["record"]["record_id"]
        checkpoint = repo.create_checkpoint(project["project_id"], "Seven-day review", record_id=record_id, scheduled_for="2026-07-24")
        revised = sample()
        revised["input"]["pressure"]["level"] = 6
        revised["input"]["next_steps"]["actions"] = [copy.deepcopy(revised["input"]["next_steps"]["actions"][0])]
        revised["input"]["next_steps"]["actions"][0]["status"] = "completed"
        revised["input"]["next_steps"]["actions"][0]["completion_evidence"] = "Assumptions documented in the decision log"
        result = repo.create_reassessment(record_id, revised, observed_summary="Pressure decreased after ownership was clarified.", checkpoint_id=checkpoint["checkpoint_id"], changed_assumptions=["Reviewer availability improved"])
        assert result["from_revision_id"] != result["to_revision_id"]
        assert result["planned_vs_observed"]["score_before"] != result["planned_vs_observed"]["score_after"]
        assert "stakeholder-review" in result["carried_actions"]
        assert len(repo.list_revisions(record_id)) == 2
        assert repo.get_checkpoint(checkpoint["checkpoint_id"])["status"] == "completed"
    finally:
        repo.close()


def test_export_contains_plan_action_history_blockers_and_reassessments(tmp_path):
    repo, project, saved = saved_workspace(tmp_path)
    try:
        record_id = saved["record"]["record_id"]
        action = repo.list_actions(record_id)[0]
        repo.update_action(action["action_id"], status="blocked", blocked_reason="Waiting for approval")
        repo.add_blocker(record_id, "Approval dependency", action_id=action["action_id"])
        payload = repo.export_record(record_id)
        assert payload["current_record"]["findings"]["recovery_plan"]
        assert len(payload["action_events"]) >= 2
        assert len(payload["blockers"]) == 1
        assert payload["reassessments"] == []
    finally:
        repo.close()
