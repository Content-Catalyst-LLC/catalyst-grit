#!/usr/bin/env python3
"""Run the complete Catalyst Grit v1.0.1 release contract."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(label: str, command: list[str], *, cwd: Path = ROOT) -> None:
    print(f"STEP: {label}")
    subprocess.run(command, cwd=cwd, check=True)


def main() -> int:
    os.environ.setdefault("PYTHONPATH", str(ROOT / "src"))
    run("Python tests", [sys.executable, "-m", "pytest", "tests"])
    run("Python compilation", [sys.executable, "-m", "compileall", "-q", "src", "python", "scripts"])
    run("Generate JSON example", [sys.executable, "python/catalyst_grit_core.py", "examples/grit_record_input.json", "--format", "json", "--output", "outputs/grit_record_output.json"])
    run("Generate Markdown example", [sys.executable, "python/catalyst_grit_core.py", "examples/grit_record_input.json", "--format", "markdown", "--output", "outputs/grit_record_brief.md"])

    expected_json = json.loads((ROOT / "examples/grit_record_output.json").read_text())
    actual_json = json.loads((ROOT / "outputs/grit_record_output.json").read_text())
    if actual_json != expected_json:
        raise SystemExit("Generated JSON output does not match the committed example.")
    if (ROOT / "outputs/grit_record_brief.md").read_text() != (ROOT / "examples/grit_record_brief.md").read_text():
        raise SystemExit("Generated Markdown output does not match the committed example.")
    print("Generated-output parity passed.")

    if shutil.which("node"):
        run("Browser parity", ["node", "scripts/check_js_parity.js"])
        run("JavaScript syntax", ["node", "--check", "wordpress/catalyst-grit-demo/assets/catalyst-grit-demo.js"])
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
        run(
            "Build package (pip wheel fallback)",
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--no-build-isolation",
                "--wheel-dir",
                "dist",
                ".",
            ],
        )
    else:
        run("Build package", [sys.executable, "-m", "build", "--no-isolation"])
    wheels = sorted((ROOT / "dist").glob("catalyst_grit-*.whl"))
    if not wheels:
        raise SystemExit("Package build did not produce a wheel.")
    with tempfile.TemporaryDirectory(prefix="catalyst-grit-wheel-") as temp:
        target = Path(temp) / "site"
        run("Install wheel", [sys.executable, "-m", "pip", "install", "--no-deps", "--target", str(target), str(wheels[-1])])
        env = os.environ.copy()
        env["PYTHONPATH"] = str(target)
        print("STEP: Import installed package")
        subprocess.run(
            [sys.executable, "-c", "import catalyst_grit; assert catalyst_grit.__version__ == '1.0.1'; print(catalyst_grit.__version__)"],
            cwd=temp,
            env=env,
            check=True,
        )

    for generated in ROOT.glob("src/*.egg-info"):
        shutil.rmtree(generated, ignore_errors=True)
    shutil.rmtree(ROOT / "build", ignore_errors=True)

    print("Catalyst Grit v1.0.1 release contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
