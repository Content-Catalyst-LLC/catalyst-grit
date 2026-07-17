#!/usr/bin/env python3
"""Run the complete Catalyst Grit v1.8.0 release contract."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(label: str, command: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    print(f"STEP: {label}")
    subprocess.run(command, cwd=cwd, env=env, check=True)


def main() -> int:
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(ROOT / "src"))
    run("Python tests", [sys.executable, "-m", "pytest", "tests"], env=env)
    run("Python compilation", [sys.executable, "-m", "compileall", "-q", "src", "python", "scripts"], env=env)
    run("Generate JSON example", [sys.executable, "python/catalyst_grit_core.py", "generate", "examples/grit_record_input.json", "--format", "json", "--output", "outputs/grit_record_output.json"], env=env)
    run("Generate Markdown example", [sys.executable, "python/catalyst_grit_core.py", "generate", "examples/grit_record_input.json", "--format", "markdown", "--output", "outputs/grit_record_brief.md"], env=env)

    expected_json = json.loads((ROOT / "examples/grit_record_output.json").read_text())
    actual_json = json.loads((ROOT / "outputs/grit_record_output.json").read_text())
    if actual_json != expected_json:
        raise SystemExit("Generated JSON output does not match the committed example.")
    if (ROOT / "outputs/grit_record_brief.md").read_text() != (ROOT / "examples/grit_record_brief.md").read_text():
        raise SystemExit("Generated Markdown output does not match the committed example.")
    print("Generated-output parity passed.")

    if shutil.which("node"):
        run("Browser parity", ["node", "scripts/check_js_parity.js"])
        run("Public JavaScript syntax", ["node", "--check", "wordpress/catalyst-grit-demo/assets/catalyst-grit-demo.js"])
        run("Private workspace JavaScript syntax", ["node", "--check", "wordpress/catalyst-grit-demo/assets/catalyst-grit-workspace.js"])
    else:
        print("INFO: node unavailable; browser checks skipped")
    if shutil.which("php"):
        run("PHP syntax", ["php", "-l", "wordpress/catalyst-grit-demo/catalyst-grit-demo.php"])
    else:
        print("INFO: php unavailable; PHP syntax check skipped")

    shutil.rmtree(ROOT / "dist", ignore_errors=True)
    try:
        import build  # type: ignore  # noqa: F401
    except ImportError:
        run("Build package (pip wheel fallback)", [sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", "--wheel-dir", "dist", "."])
    else:
        run("Build package", [sys.executable, "-m", "build", "--no-isolation"])
    wheels = sorted((ROOT / "dist").glob("catalyst_grit-*.whl"))
    if not wheels:
        raise SystemExit("Package build did not produce a wheel.")
    with tempfile.TemporaryDirectory(prefix="catalyst-grit-wheel-") as temp:
        target = Path(temp) / "site"
        run("Install wheel", [sys.executable, "-m", "pip", "install", "--no-deps", "--target", str(target), str(wheels[-1])])
        wheel_env = os.environ.copy(); wheel_env["PYTHONPATH"] = str(target)
        example_payload = json.dumps(json.loads((ROOT / "examples/grit_record_input.json").read_text()))
        code = f"""
import json, tempfile
from pathlib import Path
import catalyst_grit
assert catalyst_grit.__version__ == '1.8.0'
assert [m.version for m in catalyst_grit.MigrationManager.available()] == [1, 2, 3, 4, 5, 6, 7]
with tempfile.TemporaryDirectory() as d:
    with catalyst_grit.SQLiteWorkspaceRepository(Path(d)/'installed.sqlite3') as repo:
        project=repo.create_project('Installed wheel')
        assert project['visibility']=='private'
        assert repo.health()['migrations']['current']==7
        saved=repo.save_record(project['project_id'], json.loads({example_payload!r}))
        record_id=saved['record']['record_id']
        assert repo.list_actions(record_id)
        retrospectives=repo.list_retrospectives(record_id)
        assert retrospectives and retrospectives[0]['content']['uncertainties']
        patterns=repo.detect_project_patterns(project['project_id'], minimum_occurrences=1, include_singletons=True)
        pattern=next(item for item in patterns if item['category']=='recurring_pressure')
        review=repo.review_pattern(project['project_id'], pattern['pattern_key'], decision='accept')
        assert review['evidence']
        change=repo.create_system_change(project['project_id'], 'Installed learning change', 'Use one review channel.', source_record_ids=[record_id], decision='piloting')
        assert change['sources'][0]['record_id']==record_id
        facilitator=repo.add_team_member(project['project_id'], 'facilitator', 'Facilitator', role='facilitator', status='active', consent_status='granted')
        session=repo.create_facilitated_session(project['project_id'], 'Installed facilitated review', facilitator_key='facilitator')
        repo.add_team_perspective(project['project_id'], 'Shared pressure condition', perspective_type='pressure', member_key='facilitator', session_id=session['session_id'], actor_id='facilitator')
        agreement=repo.create_facilitated_agreement(session['session_id'], 'Confirm shared owner', owner_key='facilitator', actor_id='facilitator')
        assert repo.team_recovery_summary(project['project_id'], actor_id='facilitator')['agreement_count']==1
        evidence=repo.add_evidence(project['project_id'], 'Installed dataset', evidence_type='dataset', record_id=record_id, source_artifact_id='dataset-installed', source_product='Catalyst Data', source_version='1.12.0', strength='moderate')
        assumption=repo.add_assumption(project['project_id'], 'Installed assumption', record_id=record_id, confidence=45)
        repo.link_evidence(evidence['evidence_id'], 'assumption', assumption['assumption_id'], relation='supports')
        packet=repo.build_decision_handoff(record_id)
        assert packet['contract']=='sustainable-catalyst-decision-handoff/1.0'
        assert repo.evidence_ledger(project['project_id'])['evidence_count']==1
        assert repo.assumption_matrix(project['project_id'])['assumption_count']==1
        assert repo.list_handoffs(project['project_id'], target_product='Decision Studio')
        first=repo.capture_monitoring_snapshot(record_id, observed_at='2026-07-18T12:00:00Z')
        assert first['source_revision_hash']==saved['revision']['content_sha256']
        dashboard=repo.record_monitoring_dashboard(record_id)
        assert dashboard['data_state']=='sparse'
        assert dashboard['governance']['individual_ranking_allowed'] is False
        project_dashboard=repo.project_monitoring_dashboard(project['project_id'])
        assert project_dashboard['aggregate']['snapshot_count']==1
print(catalyst_grit.__version__)
"""
        run("Import installed package and migrations", [sys.executable, "-c", code], cwd=Path(temp), env=wheel_env)

    run("Portable smoke test", [sys.executable, "scripts/smoke_test.py"], env=env)
    for generated in ROOT.glob("src/*.egg-info"):
        shutil.rmtree(generated, ignore_errors=True)
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    print("Catalyst Grit v1.8.0 release contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
