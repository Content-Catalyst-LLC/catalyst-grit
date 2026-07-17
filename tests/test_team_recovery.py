from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from catalyst_grit import SQLiteWorkspaceRepository, WorkspaceError
from catalyst_grit.cli import main

ROOT = Path(__file__).resolve().parents[1]


def sample() -> dict:
    return json.loads((ROOT / "examples/grit_record_input.json").read_text())


def setup_team(repo: SQLiteWorkspaceRepository):
    project = repo.create_project("Team recovery review")
    facilitator = repo.add_team_member(
        project["project_id"], "facilitator-1", "Facilitator One",
        role="facilitator", status="active", consent_status="granted",
    )
    contributor = repo.add_team_member(
        project["project_id"], "member-1", "Member One",
        role="contributor", status="active", consent_status="granted",
    )
    return project, facilitator, contributor


def test_new_projects_receive_an_active_owner_membership(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "team.sqlite3") as repo:
        project = repo.create_project("Team project", owner_id="owner-a")
        members = repo.list_team_members(project["project_id"])
        assert len(members) == 1
        assert members[0]["member_key"] == "owner-a"
        assert members[0]["role"] == "owner"
        assert members[0]["consent_status"] == "granted"


def test_only_owner_or_facilitator_can_manage_members(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "roles.sqlite3") as repo:
        project, _, _ = setup_team(repo)
        with pytest.raises(WorkspaceError, match="not authorized"):
            repo.add_team_member(project["project_id"], "x", "X", actor_id="member-1")
        added = repo.add_team_member(project["project_id"], "reviewer-1", "Reviewer", role="reviewer", actor_id="facilitator-1")
        assert added["role"] == "reviewer"


def test_facilitator_cannot_grant_owner_access(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "owner.sqlite3") as repo:
        project, _, _ = setup_team(repo)
        with pytest.raises(WorkspaceError, match="only an owner"):
            repo.add_team_member(project["project_id"], "owner-b", "Owner B", role="owner", actor_id="facilitator-1")


def test_session_has_default_ground_rules_and_no_individual_scoring(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "session.sqlite3") as repo:
        project, _, _ = setup_team(repo)
        session = repo.create_facilitated_session(project["project_id"], "Recovery review", facilitator_key="facilitator-1")
        assert session["status"] == "planned"
        assert "No ranking, diagnosis, or hidden performance evaluation." in session["ground_rules"]
        assert session["facilitation_boundary"]["individual_scoring_prohibited"] is True
        assert session["facilitation_boundary"]["consent_required_for_shared_perspectives"] is True


def test_session_facilitator_requires_facilitator_role(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "bad-facilitator.sqlite3") as repo:
        project, _, _ = setup_team(repo)
        with pytest.raises(WorkspaceError, match="facilitator role"):
            repo.create_facilitated_session(project["project_id"], "Review", facilitator_key="member-1")


def test_participant_consent_and_sharing_scope_are_explicit(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "participant.sqlite3") as repo:
        project, _, _ = setup_team(repo)
        session = repo.create_facilitated_session(project["project_id"], "Review", facilitator_key="facilitator-1")
        participant = repo.add_session_participant(
            session["session_id"], "member-1", participation_status="confirmed",
            consent_status="granted", sharing_scope="facilitator_only",
            actor_id="facilitator-1",
        )
        assert participant["consent_status"] == "granted"
        assert participant["sharing_scope"] == "facilitator_only"


def test_perspective_visibility_respects_private_and_facilitator_scopes(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "scope.sqlite3") as repo:
        project, _, _ = setup_team(repo)
        session = repo.create_facilitated_session(project["project_id"], "Review", facilitator_key="facilitator-1")
        repo.add_team_perspective(project["project_id"], "Shared observation", perspective_type="pressure", member_key="member-1", session_id=session["session_id"], actor_id="member-1")
        repo.add_team_perspective(project["project_id"], "Facilitator note", perspective_type="constraint", member_key="member-1", session_id=session["session_id"], sharing_scope="facilitator_only", actor_id="member-1")
        repo.add_team_perspective(project["project_id"], "Private reflection", perspective_type="learning", member_key="member-1", session_id=session["session_id"], sharing_scope="private", actor_id="member-1")
        assert [item["content"] for item in repo.list_team_perspectives(project["project_id"], actor_id="self")] == ["Shared observation", "Facilitator note"]
        assert [item["content"] for item in repo.list_team_perspectives(project["project_id"], actor_id="facilitator-1")] == ["Shared observation", "Facilitator note"]
        assert [item["content"] for item in repo.list_team_perspectives(project["project_id"], actor_id="member-1")] == ["Shared observation", "Facilitator note", "Private reflection"]


def test_withdrawn_perspective_is_excluded_by_default(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "withdrawn.sqlite3") as repo:
        project, _, _ = setup_team(repo)
        repo.add_team_perspective(project["project_id"], "Withdrawn note", member_key="member-1", consent_status="withdrawn", actor_id="member-1")
        assert repo.list_team_perspectives(project["project_id"], actor_id="member-1") == []
        visible = repo.list_team_perspectives(project["project_id"], actor_id="member-1", include_withdrawn=True)
        assert visible[0]["consent_status"] == "withdrawn"


def test_team_perspectives_are_append_only(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "append-only.sqlite3") as repo:
        project, _, _ = setup_team(repo)
        perspective = repo.add_team_perspective(project["project_id"], "Recorded perspective", member_key="member-1", actor_id="member-1")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repo.connection.execute("UPDATE team_perspectives SET content='changed' WHERE perspective_id=?", (perspective["perspective_id"],))


def test_completed_agreement_requires_evidence_and_blocked_requires_support(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "agreement-rules.sqlite3") as repo:
        project, _, _ = setup_team(repo)
        session = repo.create_facilitated_session(project["project_id"], "Review", facilitator_key="facilitator-1")
        agreement = repo.create_facilitated_agreement(session["session_id"], "Confirm decision owner", owner_key="member-1", actor_id="facilitator-1")
        with pytest.raises(WorkspaceError, match="completion evidence"):
            repo.update_facilitated_agreement(agreement["agreement_id"], status="completed", actor_id="facilitator-1")
        with pytest.raises(WorkspaceError, match="support_needed"):
            repo.update_facilitated_agreement(agreement["agreement_id"], status="blocked", actor_id="facilitator-1")
        completed = repo.update_facilitated_agreement(agreement["agreement_id"], status="completed", completion_evidence="Decision owner recorded in shared log.", actor_id="facilitator-1")
        assert completed["status"] == "completed"
        assert [event["to_status"] for event in completed["events"]] == ["proposed", "completed"]


def test_agreement_events_are_append_only(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "agreement-events.sqlite3") as repo:
        project, _, _ = setup_team(repo)
        session = repo.create_facilitated_session(project["project_id"], "Review", facilitator_key="facilitator-1")
        agreement = repo.create_facilitated_agreement(session["session_id"], "Reduce scope", actor_id="facilitator-1")
        event_id = agreement["events"][0]["event_id"]
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repo.connection.execute("UPDATE facilitated_agreement_events SET reason='changed' WHERE event_id=?", (event_id,))


def test_team_summary_reports_shared_work_not_individual_scores(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "summary.sqlite3") as repo:
        project, _, _ = setup_team(repo)
        session = repo.create_facilitated_session(project["project_id"], "Review", facilitator_key="facilitator-1")
        repo.add_team_perspective(project["project_id"], "Dependency is unclear", perspective_type="constraint", member_key="member-1", session_id=session["session_id"], actor_id="member-1")
        agreement = repo.create_facilitated_agreement(session["session_id"], "Escalate dependency", actor_id="facilitator-1")
        repo.update_facilitated_agreement(agreement["agreement_id"], status="blocked", support_needed="Sponsor decision", actor_id="facilitator-1")
        summary = repo.team_recovery_summary(project["project_id"], actor_id="facilitator-1")
        assert summary["perspectives_by_type"] == {"constraint": 1}
        assert summary["agreements_by_status"] == {"blocked": 1}
        assert summary["review_required"] is True
        rendered = json.dumps(summary).lower()
        assert "individual score" not in rendered and "rank" in summary["interpretation_limit"].lower()


def test_project_export_import_round_trips_team_sessions(tmp_path: Path):
    source_db = tmp_path / "source.sqlite3"
    target_db = tmp_path / "target.sqlite3"
    with SQLiteWorkspaceRepository(source_db) as repo:
        project, _, _ = setup_team(repo)
        repo.save_record(project["project_id"], sample())
        session = repo.create_facilitated_session(project["project_id"], "Review", facilitator_key="facilitator-1")
        repo.add_session_participant(session["session_id"], "member-1", consent_status="granted", actor_id="facilitator-1")
        repo.add_team_perspective(project["project_id"], "Shared pressure", perspective_type="pressure", member_key="member-1", session_id=session["session_id"], actor_id="member-1")
        repo.create_facilitated_agreement(session["session_id"], "Clarify owner", owner_key="member-1", actor_id="facilitator-1")
        bundle = repo.export_project(project["project_id"])
        assert len(bundle["team_members"]) == 3
        assert len(bundle["facilitated_sessions"]) == 1
    with SQLiteWorkspaceRepository(target_db) as repo:
        result = repo.import_payload(bundle, project_id="cgp_importedteam000000000000000001")
        assert result["team_members_imported"] == 2
        assert result["facilitated_sessions_imported"] == 1
        assert result["team_perspectives_imported"] == 1
        assert result["facilitated_agreements_imported"] == 1


def test_team_cli_workflow(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    db = tmp_path / "cli.sqlite3"
    assert main(["project-create", "--database", str(db), "--title", "Team CLI"]) == 0
    project_id = json.loads(capsys.readouterr().out)["project_id"]
    assert main(["team-member-add", "--database", str(db), project_id, "--member-key", "fac-1", "--display-name", "Fac One", "--role", "facilitator", "--status", "active", "--consent-status", "granted"]) == 0
    capsys.readouterr()
    assert main(["session-create", "--database", str(db), project_id, "--title", "CLI review", "--facilitator", "fac-1"]) == 0
    session_id = json.loads(capsys.readouterr().out)["session_id"]
    assert main(["agreement-add", "--database", str(db), session_id, "--title", "Name owner", "--actor", "fac-1"]) == 0
    capsys.readouterr()
    assert main(["team-summary", "--database", str(db), project_id, "--actor", "fac-1"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["session_count"] == 1 and summary["agreement_count"] == 1
