#!/usr/bin/env python3
"""Portable, dependency-free Catalyst Grit v1.8.0 smoke test."""
from __future__ import annotations

import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_SRC = (ROOT / "src").resolve()
# Force the repository source ahead of any globally installed or editable copy.
sys.path.insert(0, str(LOCAL_SRC))
import catalyst_grit as catalyst_grit_package  # noqa: E402
from catalyst_grit import (  # noqa: E402
    DEFAULT_METHODOLOGY_PROFILE,
    MigrationManager,
    SQLiteWorkspaceRepository,
    WORKSPACE_FORMAT,
    __version__,
    generate_record,
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> int:
    version = (ROOT / "VERSION").read_text().strip()
    imported_file = Path(catalyst_grit_package.__file__).resolve()
    expected_package = LOCAL_SRC / "catalyst_grit"
    check(
        imported_file.is_relative_to(expected_package),
        f"local package import mismatch: imported {imported_file}; expected under {expected_package}",
    )
    check(
        version == __version__ == "1.8.0",
        f"version identity mismatch: VERSION={version!r}, imported={__version__!r}, module={imported_file}",
    )
    manifest = json.loads((ROOT / "catalyst_grit_manifest.json").read_text())
    check(manifest["version"] == manifest["schema_version"] == manifest["engine_version"] == version, "manifest version mismatch")
    check(json.loads((ROOT / "methodology/recovery-profile-v1.8.0.json").read_text()) == DEFAULT_METHODOLOGY_PROFILE, "methodology profile mismatch")
    schema_names = [
        "catalyst_grit_record.schema.json",
        "catalyst_grit_request.schema.json",
        "catalyst_grit_methodology_profile.schema.json",
        "catalyst_grit_project.schema.json",
        "catalyst_grit_workspace_bundle.schema.json",
    ]
    for name in schema_names:
        schema = json.loads((ROOT / "schemas" / name).read_text())
        check(schema["x-catalyst-grit-version"] == version, f"schema version mismatch: {name}")
    check([item.version for item in MigrationManager.available()] == [1, 2, 3, 4, 5, 6, 7], "packaged migration discovery failed")

    plugin = (ROOT / "wordpress/catalyst-grit-demo/catalyst-grit-demo.php").read_text()
    check(bool(re.search(r"Version:\s*" + re.escape(version), plugin)), "plugin version mismatch")
    check("wp_ajax_nopriv_catalyst_grit_workspace" not in plugin, "private workspace exposes an anonymous AJAX action")
    check("check_ajax_referer('catalyst_grit_workspace_v180', 'nonce')" in plugin, "workspace nonce guard missing")

    request = json.loads((ROOT / "examples/grit_record_input.json").read_text())
    expected = json.loads((ROOT / "examples/grit_record_output.json").read_text())
    generated = generate_record(request).to_dict()
    check(generated == expected, "Python output parity failed")
    check(generated["findings"]["interpretation"]["score_display_policy"]["mode"] == "component_context_required", "score display policy missing")
    check(all(item.get("source_paths") for item in generated["findings"]["flags"]), "flag source paths missing")
    plan = generated["findings"]["recovery_plan"]
    check(plan["smallest_recoverable_next_step"]["owner"], "smallest next step has no owner")
    check(plan["checkpoint"]["scheduled_for"], "recovery plan has no checkpoint")
    check(set(plan["horizons"]) == {"24_hours", "72_hours", "7_days", "longer_term"}, "planning horizons missing")
    retrospective = generated["findings"]["retrospective"]
    check(retrospective["completion"]["percent"] == 100.0, "retrospective completeness mismatch")
    check(retrospective["evidence_paths"]["uncertainties"] == "$.input.learning.uncertainties", "retrospective evidence path missing")
    patterns = generated["findings"]["adaptation_patterns"]
    check(patterns and all(item["evidence"] for item in patterns), "adaptation pattern evidence missing")
    check(all(all(evidence.get("source_path") for evidence in item["evidence"]) for item in patterns), "adaptation pattern source path missing")
    check(generated["findings"]["learning_loop"]["personality_labeling_prohibited"] is True, "learning-loop personality safeguard missing")

    with tempfile.TemporaryDirectory(prefix="catalyst-grit-smoke-") as temp:
        database = Path(temp) / "workspace.sqlite3"
        with SQLiteWorkspaceRepository(database) as repo:
            project = repo.create_project("Portable smoke project")
            saved = repo.save_record(project["project_id"], request)
            record_id = saved["record"]["record_id"]
            checkpoint = repo.create_checkpoint(project["project_id"], "Review checkpoint", record_id=record_id, scheduled_for="2026-07-24")
            actions = repo.list_actions(record_id)
            check(actions and actions[0]["action_key"], "recovery-plan actions were not persisted")
            updated = repo.update_action(actions[0]["action_id"], status="in_progress", actor_id="portable-smoke", reason="Start the smallest recoverable next step")
            check(updated["status"] == "in_progress", "action transition failed")
            check(len(repo.action_history(actions[0]["action_id"])) >= 2, "append-only action history missing")
            blocker = repo.add_blocker(record_id, "Portable smoke dependency", action_id=actions[0]["action_id"], actor_id="portable-smoke")
            check(blocker["status"] == "open", "blocker persistence failed")
            check(repo.health()["migrations"]["current"] == 7, "workspace migration level mismatch")
            retrospectives = repo.list_retrospectives(record_id)
            check(retrospectives and retrospectives[0]["content"]["uncertainties"], "persistent retrospective missing")
            project_patterns = repo.detect_project_patterns(project["project_id"], minimum_occurrences=1, include_singletons=True)
            pressure_pattern = next(item for item in project_patterns if item["category"] == "recurring_pressure")
            reviewed_pattern = repo.review_pattern(project["project_id"], pressure_pattern["pattern_key"], decision="accept", actor_id="portable-smoke")
            check(reviewed_pattern["evidence"], "pattern review evidence missing")
            system_change = repo.create_system_change(
                project["project_id"],
                "Portable smoke system change",
                "Use one review channel.",
                source_record_ids=[record_id],
                evidence_note="Linked to the generated retrospective.",
                decision="piloting",
                actor_id="portable-smoke",
            )
            system_change = repo.update_system_change(system_change["system_change_id"], decision="adopt", review_result="The pilot reduced duplicate feedback.", actor_id="portable-smoke")
            check(len(system_change["events"]) == 2, "system-change event history missing")
            exported = repo.export_record(record_id)
            check(exported["format"] == WORKSPACE_FORMAT, "workspace export format mismatch")
            check(exported["action_events"] and exported["blockers"], "plan-history export missing")
            facilitator = repo.add_team_member(project["project_id"], "facilitator", "Facilitator", role="facilitator", status="active", consent_status="granted")
            session = repo.create_facilitated_session(project["project_id"], "Portable facilitated review", facilitator_key="facilitator")
            repo.add_session_participant(session["session_id"], "facilitator", participation_status="confirmed", consent_status="granted", actor_id="facilitator")
            perspective = repo.add_team_perspective(project["project_id"], "Shared dependency pressure", perspective_type="constraint", member_key="facilitator", session_id=session["session_id"], actor_id="facilitator")
            agreement = repo.create_facilitated_agreement(session["session_id"], "Name the decision owner", owner_key="facilitator", actor_id="facilitator")
            agreement = repo.update_facilitated_agreement(agreement["agreement_id"], status="completed", completion_evidence="Decision owner recorded.", actor_id="facilitator")
            check(perspective["sharing_scope"] == "shared", "team perspective sharing scope missing")
            check(len(agreement["events"]) == 2, "facilitated agreement history missing")
            summary = repo.team_recovery_summary(project["project_id"], actor_id="facilitator")
            check(summary["member_count"] == 2 and summary["agreement_count"] == 1, "team recovery summary mismatch")
            evidence = repo.add_evidence(project["project_id"], "Smoke dataset", evidence_type="dataset", record_id=record_id, source_artifact_id="dataset-smoke", source_product="Catalyst Data", source_version="1.12.0", strength="moderate")
            assumption = repo.add_assumption(project["project_id"], "Smoke assumption", record_id=record_id, confidence=40, uncertainty="Needs review")
            repo.link_evidence(evidence["evidence_id"], "assumption", assumption["assumption_id"], relation="supports")
            packet = repo.build_decision_handoff(record_id)
            check(packet["contract"] == "sustainable-catalyst-decision-handoff/1.0", "decision handoff contract missing")
            check(repo.evidence_ledger(project["project_id"])["evidence_count"] == 1, "evidence ledger mismatch")
            check(repo.assumption_matrix(project["project_id"])["assumption_count"] == 1, "assumption matrix mismatch")
            check(repo.list_handoffs(project["project_id"], target_product="Decision Studio"), "decision handoff was not persisted")
            first_snapshot = repo.capture_monitoring_snapshot(record_id, observed_at="2026-07-18T12:00:00Z", actor_id="portable-smoke")
            check(first_snapshot["source_revision_hash"] == saved["revision"]["content_sha256"], "monitoring source revision hash mismatch")
            check(repo.record_trends(record_id)["data_state"] == "sparse", "single-point monitoring must remain sparse")
            revised_request = json.loads((ROOT / "examples/grit_record_input.json").read_text())
            revised_request["input"]["pressure"]["level"] = 5
            repo.revise_record(record_id, revised_request, actor_id="portable-smoke", reason="monitoring condition change")
            repo.capture_monitoring_snapshot(record_id, observed_at="2026-07-20T12:00:00Z", actor_id="portable-smoke")
            trends = repo.record_trends(record_id)
            check(trends["minimum_data_met"] is True, "two-point monitoring threshold failed")
            check(trends["trends"]["pressure"]["direction"] == "improving", "pressure trend direction mismatch")
            owner_dashboard = repo.team_conditions_dashboard(project["project_id"], actor_id="self")
            check(owner_dashboard["privacy"]["suppressed"] is True, "team privacy threshold was not enforced")
            project_export = repo.export_project(project["project_id"])
            check(project_export["pattern_reviews"] and project_export["system_changes"], "learning-history export missing")
            check(project_export["team_members"] and project_export["facilitated_sessions"], "facilitated-review export missing")
            check(project_export["evidence_ledger"]["evidence_count"] == 1, "evidence export missing")
            check(project_export["assumption_matrix"]["assumption_count"] == 1, "assumption export missing")
            check(project_export["handoffs"], "handoff export missing")
            check(project_export["monitoring_dashboard"]["aggregate"]["snapshot_count"] == 2, "monitoring dashboard export missing")
            check(project_export["records"][0]["monitoring_snapshots"], "monitoring snapshot export missing")
            check(repo.health()["integrity"] == "ok", "SQLite integrity failed")
        with SQLiteWorkspaceRepository(database) as reopened:
            check(reopened.get_record(record_id, include_canonical=True)["canonical"]["normalized_input"]["pressure"]["level"] == 5.0, "revised record did not survive restart")
            check(len(reopened.list_revisions(record_id)) == 2, "revision history did not survive restart")
            check(len(reopened.list_monitoring_snapshots(project["project_id"], record_id=record_id)) == 2, "monitoring history did not survive restart")

    for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "python").rglob("*.py")) + list((ROOT / "scripts").rglob("*.py")):
        py_compile.compile(str(path), doraise=True)
    if shutil.which("node"):
        subprocess.run(["node", "scripts/check_js_parity.js"], cwd=ROOT, check=True)
        subprocess.run(["node", "--check", "wordpress/catalyst-grit-demo/assets/catalyst-grit-demo.js"], cwd=ROOT, check=True)
        subprocess.run(["node", "--check", "wordpress/catalyst-grit-demo/assets/catalyst-grit-workspace.js"], cwd=ROOT, check=True)
    if shutil.which("php"):
        subprocess.run(["php", "-l", "wordpress/catalyst-grit-demo/catalyst-grit-demo.php"], cwd=ROOT, check=True)
    allow_local_state = os.environ.get("CATALYST_GRIT_ALLOW_LOCAL_STATE") == "1"
    forbidden = []
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if any(part in {".git", "dist", "build", "__pycache__", ".pytest_cache"} for part in rel.parts):
            continue
        if not path.is_file():
            continue
        if ".egg-info" in rel.parts:
            forbidden.append(str(rel))
        elif path.suffix in {".db", ".sqlite", ".sqlite3"} and not allow_local_state:
            forbidden.append(str(rel))
    check(not forbidden, "forbidden repository artifacts: " + ", ".join(forbidden))
    print("Catalyst Grit v1.8.0 portable release smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
