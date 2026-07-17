#!/usr/bin/env python3
"""Portable, dependency-free Catalyst Grit v1.2.0 smoke test."""
from __future__ import annotations

import json
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
        version == __version__ == "1.2.0",
        f"version identity mismatch: VERSION={version!r}, imported={__version__!r}, module={imported_file}",
    )
    manifest = json.loads((ROOT / "catalyst_grit_manifest.json").read_text())
    check(manifest["version"] == manifest["schema_version"] == manifest["engine_version"] == version, "manifest version mismatch")
    check(json.loads((ROOT / "methodology/recovery-profile-v1.2.0.json").read_text()) == DEFAULT_METHODOLOGY_PROFILE, "methodology profile mismatch")
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
    check([item.version for item in MigrationManager.available()] == [1, 2], "packaged migration discovery failed")

    plugin = (ROOT / "wordpress/catalyst-grit-demo/catalyst-grit-demo.php").read_text()
    check(bool(re.search(r"Version:\s*" + re.escape(version), plugin)), "plugin version mismatch")
    check("wp_ajax_nopriv_catalyst_grit_workspace" not in plugin, "private workspace exposes an anonymous AJAX action")
    check("check_ajax_referer('catalyst_grit_workspace_v120', 'nonce')" in plugin, "workspace nonce guard missing")

    request = json.loads((ROOT / "examples/grit_record_input.json").read_text())
    expected = json.loads((ROOT / "examples/grit_record_output.json").read_text())
    check(generate_record(request).to_dict() == expected, "Python output parity failed")

    with tempfile.TemporaryDirectory(prefix="catalyst-grit-smoke-") as temp:
        database = Path(temp) / "workspace.sqlite3"
        with SQLiteWorkspaceRepository(database) as repo:
            project = repo.create_project("Portable smoke project")
            saved = repo.save_record(project["project_id"], request)
            record_id = saved["record"]["record_id"]
            repo.create_checkpoint(project["project_id"], "Review checkpoint", record_id=record_id, scheduled_for="2026-07-24")
            exported = repo.export_record(record_id)
            check(exported["format"] == WORKSPACE_FORMAT, "workspace export format mismatch")
            check(repo.health()["integrity"] == "ok", "SQLite integrity failed")
        with SQLiteWorkspaceRepository(database) as reopened:
            check(reopened.get_record(record_id, include_canonical=True)["canonical"] == expected, "record did not survive restart")
            check(len(reopened.list_revisions(record_id)) == 1, "revision history did not survive restart")

    for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "python").rglob("*.py")) + list((ROOT / "scripts").rglob("*.py")):
        py_compile.compile(str(path), doraise=True)
    if shutil.which("node"):
        subprocess.run(["node", "scripts/check_js_parity.js"], cwd=ROOT, check=True)
        subprocess.run(["node", "--check", "wordpress/catalyst-grit-demo/assets/catalyst-grit-demo.js"], cwd=ROOT, check=True)
        subprocess.run(["node", "--check", "wordpress/catalyst-grit-demo/assets/catalyst-grit-workspace.js"], cwd=ROOT, check=True)
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
    print("Catalyst Grit v1.2.0 portable release smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
