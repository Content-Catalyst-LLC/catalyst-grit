#!/usr/bin/env python3
"""Portable, dependency-free release smoke test used by the installer."""
from __future__ import annotations

import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from catalyst_grit import __version__, generate_record


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> int:
    version = (ROOT / "VERSION").read_text().strip()
    check(version == __version__ == "1.0.1", "version identity mismatch")
    manifest = json.loads((ROOT / "catalyst_grit_manifest.json").read_text())
    check(manifest["version"] == version, "manifest version mismatch")
    schema = json.loads((ROOT / "schemas/catalyst_grit_record.schema.json").read_text())
    check(schema["x-catalyst-grit-version"] == version, "schema version mismatch")
    plugin = (ROOT / "wordpress/catalyst-grit-demo/catalyst-grit-demo.php").read_text()
    check(bool(re.search(r"Version:\s*" + re.escape(version), plugin)), "plugin version mismatch")

    input_data = json.loads((ROOT / "examples/grit_record_input.json").read_text())
    expected = json.loads((ROOT / "examples/grit_record_output.json").read_text())
    check(generate_record(input_data).to_dict() == expected, "Python output parity failed")

    for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "python").rglob("*.py")):
        py_compile.compile(str(path), doraise=True)

    if shutil.which("node"):
        subprocess.run(["node", "scripts/check_js_parity.js"], cwd=ROOT, check=True)
        subprocess.run(["node", "--check", "wordpress/catalyst-grit-demo/assets/catalyst-grit-demo.js"], cwd=ROOT, check=True)
    if shutil.which("php"):
        subprocess.run(["php", "-l", "wordpress/catalyst-grit-demo/catalyst-grit-demo.php"], cwd=ROOT, check=True)

    forbidden = []
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if any(part in {".git", "dist", "build", "__pycache__", ".pytest_cache"} for part in rel.parts):
            continue
        if path.is_file() and (path.suffix in {".db", ".sqlite", ".sqlite3"} or ".egg-info" in rel.parts):
            forbidden.append(str(rel))
    check(not forbidden, "forbidden repository artifacts: " + ", ".join(forbidden))
    print("Catalyst Grit v1.0.1 portable release smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
