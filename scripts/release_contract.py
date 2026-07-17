#!/usr/bin/env python3
"""Run the complete Catalyst Grit v1.4.0 release contract."""
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
assert catalyst_grit.__version__ == '1.4.0'
assert [m.version for m in catalyst_grit.MigrationManager.available()] == [1, 2, 3]
with tempfile.TemporaryDirectory() as d:
    with catalyst_grit.SQLiteWorkspaceRepository(Path(d)/'installed.sqlite3') as repo:
        project=repo.create_project('Installed wheel')
        assert project['visibility']=='private'
        assert repo.health()['migrations']['current']==3
        saved=repo.save_record(project['project_id'], json.loads({example_payload!r}))
        record_id=saved['record']['record_id']
        assert repo.list_actions(record_id)
print(catalyst_grit.__version__)
"""
        run("Import installed package and migrations", [sys.executable, "-c", code], cwd=Path(temp), env=wheel_env)

    run("Portable smoke test", [sys.executable, "scripts/smoke_test.py"], env=env)
    for generated in ROOT.glob("src/*.egg-info"):
        shutil.rmtree(generated, ignore_errors=True)
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    print("Catalyst Grit v1.4.0 release contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
