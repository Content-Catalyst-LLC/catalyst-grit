from __future__ import annotations

import copy
import json
from pathlib import Path
import sqlite3

import pytest

from catalyst_grit import SQLiteWorkspaceRepository, WorkspaceError, generate_record
from catalyst_grit.cli import main

ROOT = Path(__file__).resolve().parents[1]


def sample() -> dict:
    return json.loads((ROOT / "examples/grit_record_input.json").read_text())


def second_record() -> dict:
    value = copy.deepcopy(sample())
    value["metadata"]["record_id"] = "cgr_22222222222222222222222222222222"
    value["metadata"]["created_at"] = "2026-07-18T12:00:00Z"
    value["metadata"]["updated_at"] = "2026-07-18T12:00:00Z"
    value["input"]["learning"]["what_changed"] = "A second review cycle repeated the separate feedback channels."
    return value


def test_retrospective_preserves_evidence_and_uncertainty():
    retrospective = generate_record(sample()).findings["retrospective"]
    assert retrospective["completion"]["percent"] == 100.0
    assert retrospective["what_happened"].startswith("Conflicting review channels")
    assert retrospective["evidence_paths"]["uncertainties"] == "$.input.learning.uncertainties"
    assert retrospective["uncertainties"] == ["Whether all reviewers can use the same feedback channel."]
    assert "does not establish causation" in retrospective["interpretation_limit"]


def test_patterns_are_explainable_and_reviewable_not_personality_labels():
    findings = generate_record(sample()).findings
    patterns = findings["adaptation_patterns"]
    dependency = next(item for item in patterns if item["category"] == "dependency_failure")
    assert dependency["evidence"][0]["source_path"] == "$.input.constraints.items[0]"
    assert dependency["status"] == "inferred"
    assert findings["learning_loop"]["review_required"] is True
    assert findings["learning_loop"]["personality_labeling_prohibited"] is True
    rendered = json.dumps(patterns).lower()
    assert "personality" not in rendered and "grit score" not in rendered


def test_user_can_reject_or_correct_inferred_patterns():
    value = sample()
    baseline = generate_record(value).findings["adaptation_patterns"]
    pressure = next(item for item in baseline if item["category"] == "recurring_pressure")
    clarity = next(item for item in baseline if item["category"] == "clarity_failure")
    value["input"]["learning"]["pattern_reviews"] = [
        {"pattern_key": pressure["pattern_key"], "decision": "reject", "notes": "One-time deadline"},
        {"pattern_key": clarity["pattern_key"], "decision": "correct", "corrected_label": "Approval ownership gap", "notes": "Task clarity was adequate"},
    ]
    reviewed = generate_record(value).findings["adaptation_patterns"]
    rejected = next(item for item in reviewed if item["pattern_key"] == pressure["pattern_key"])
    corrected = next(item for item in reviewed if item["pattern_key"] == clarity["pattern_key"])
    assert rejected["status"] == "rejected"
    assert corrected["status"] == "corrected" and corrected["label"] == "Approval ownership gap"


def test_v14_input_gets_visible_learning_defaults():
    value = sample()
    value["metadata"]["schema_version"] = "1.4.0"
    value["metadata"]["provenance"]["source_schema_version"] = "1.4.0"
    for key in ["what_happened", "what_was_expected", "what_changed", "what_helped", "what_hindered", "what_was_learned", "repeat", "redesign", "uncertainties", "pattern_reviews"]:
        value["input"]["learning"].pop(key)
    record = generate_record(value)
    assert record.metadata["schema_version"] == "1.9.0"
    assert record.normalized_input["learning"]["pattern_reviews"] == []
    assert record.findings["retrospective"]["what_happened"] == value["input"]["trigger"]["summary"]


def test_retrospectives_are_persisted_per_revision_and_append_only(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "learning.sqlite3") as repo:
        project = repo.create_project("Learning loop")
        saved = repo.save_record(project["project_id"], sample())
        items = repo.list_retrospectives(saved["record"]["record_id"])
        assert len(items) == 1
        assert items[0]["content"]["uncertainties"]
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repo.connection.execute("UPDATE retrospectives SET content_json='{}'")


def test_project_pattern_detection_counts_records_and_retains_sources(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "patterns.sqlite3") as repo:
        project = repo.create_project("Pattern project")
        first = repo.save_record(project["project_id"], sample())
        second = repo.save_record(project["project_id"], second_record())
        patterns = repo.detect_project_patterns(project["project_id"])
        item = next(pattern for pattern in patterns if pattern["pattern_key"] == "recurring_pressure:publication-deadline")
        assert item["occurrence_count"] == 2
        assert set(item["record_ids"]) == {first["record"]["record_id"], second["record"]["record_id"]}
        assert all(evidence["record_id"] and evidence["revision_id"] and evidence["source_path"] for evidence in item["evidence"])


def test_project_pattern_review_is_append_only_and_changes_visible_status(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "pattern-review.sqlite3") as repo:
        project = repo.create_project("Pattern review")
        repo.save_record(project["project_id"], sample())
        key = "recurring_pressure:publication-deadline"
        review = repo.review_pattern(project["project_id"], key, decision="correct", corrected_label="Recurring publication deadline pressure", notes="Confirmed in review")
        assert review["decision"] == "correct"
        visible = next(item for item in repo.detect_project_patterns(project["project_id"], minimum_occurrences=1, include_singletons=True) if item["pattern_key"] == key)
        assert visible["status"] == "corrected" and visible["label"] == "Recurring publication deadline pressure"
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repo.connection.execute("UPDATE pattern_reviews SET decision='reject'")


def test_system_change_links_source_records_and_tracks_pilot_decisions(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "changes.sqlite3") as repo:
        project = repo.create_project("System changes")
        saved = repo.save_record(project["project_id"], sample())
        record_id = saved["record"]["record_id"]
        change = repo.create_system_change(
            project["project_id"],
            "Single review channel",
            "Route all review feedback through one decision log.",
            owner="project lead",
            source_record_ids=[record_id],
            evidence_note="Separate channels appeared in the retrospective.",
            expected_benefit="Fewer conflicting instructions.",
            pilot_start="2026-07-20",
            pilot_end="2026-08-03",
            decision="piloting",
        )
        assert change["sources"][0]["record_id"] == record_id
        reviewed = repo.update_system_change(change["system_change_id"], decision="adopt", review_result="The pilot reduced duplicate feedback.")
        assert reviewed["decision"] == "adopt" and len(reviewed["events"]) == 2
        assert reviewed["events"][0]["to_decision"] == "piloting"
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            repo.connection.execute("UPDATE system_change_events SET reason='rewritten'")


def test_system_change_requires_evidence_record(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "change-guard.sqlite3") as repo:
        project = repo.create_project("Change guard")
        with pytest.raises(WorkspaceError, match="source record"):
            repo.create_system_change(project["project_id"], "No evidence", "Change something", source_record_ids=[])


def test_project_export_preserves_learning_evidence_reviews_and_changes(tmp_path: Path):
    with SQLiteWorkspaceRepository(tmp_path / "export-learning.sqlite3") as repo:
        project = repo.create_project("Export learning")
        saved = repo.save_record(project["project_id"], sample())
        key = "recurring_pressure:publication-deadline"
        repo.review_pattern(project["project_id"], key, decision="accept")
        repo.create_system_change(project["project_id"], "One channel", "Use one review channel.", source_record_ids=[saved["record"]["record_id"]])
        payload = repo.export_project(project["project_id"])
        assert payload["records"][0]["retrospectives"][0]["uncertainties"]
        assert payload["pattern_reviews"][0]["evidence"]
        assert payload["system_changes"][0]["sources"][0]["record_id"] == saved["record"]["record_id"]



def test_project_export_import_restores_pattern_reviews_and_system_change_history(tmp_path: Path):
    source_db = tmp_path / "source-learning.sqlite3"
    target_db = tmp_path / "target-learning.sqlite3"
    with SQLiteWorkspaceRepository(source_db) as source:
        project = source.create_project("Round trip learning")
        saved = source.save_record(project["project_id"], sample())
        record_id = saved["record"]["record_id"]
        key = "recurring_pressure:publication-deadline"
        source.review_pattern(project["project_id"], key, decision="correct", corrected_label="Deadline coordination pressure", notes="Reviewed by the project owner")
        change = source.create_system_change(
            project["project_id"],
            "One review channel",
            "Use one review channel.",
            source_record_ids=[record_id],
            decision="piloting",
            evidence_note="Source-linked retrospective evidence.",
        )
        source.update_system_change(change["system_change_id"], decision="adopt", review_result="Pilot reduced duplicate feedback.")
        exported = source.export_project(project["project_id"])

    with SQLiteWorkspaceRepository(target_db) as target:
        result = target.import_payload(exported)
        assert result["pattern_reviews_imported"] == 1
        assert result["system_changes_imported"] == 1
        reviews = target.list_pattern_reviews(result["project_id"])
        changes = target.list_system_changes(result["project_id"])
        assert reviews[0]["decision"] == "correct"
        assert reviews[0]["evidence"]
        assert changes[0]["sources"][0]["evidence_note"] == "Source-linked retrospective evidence."
        assert [event["to_decision"] for event in changes[0]["events"]] == ["piloting", "adopt"]

def test_learning_cli_commands(tmp_path: Path, capsys):
    db = tmp_path / "learning-cli.sqlite3"
    assert main(["project-create", "--database", str(db), "--title", "CLI learning"]) == 0
    project = json.loads(capsys.readouterr().out)
    assert main(["record-save", "--database", str(db), project["project_id"], str(ROOT / "examples/grit_record_input.json")]) == 0
    saved = json.loads(capsys.readouterr().out)
    record_id = saved["record"]["record_id"]
    assert main(["pattern-list", "--database", str(db), project["project_id"], "--minimum-occurrences", "1", "--include-singletons"]) == 0
    patterns = json.loads(capsys.readouterr().out)
    key = next(item["pattern_key"] for item in patterns if item["category"] == "recurring_pressure")
    assert main(["pattern-review", "--database", str(db), project["project_id"], key, "--decision", "accept"]) == 0
    assert json.loads(capsys.readouterr().out)["decision"] == "accept"
    assert main(["system-change-add", "--database", str(db), project["project_id"], "--title", "One channel", "--proposed-change", "Use one review channel", "--record", record_id]) == 0
    change = json.loads(capsys.readouterr().out)
    assert change["sources"][0]["record_id"] == record_id
