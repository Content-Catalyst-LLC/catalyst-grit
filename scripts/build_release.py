#!/usr/bin/env python3
"""Build deterministic Catalyst Grit source and WordPress release artifacts."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
VERSION = (ROOT / "VERSION").read_text().strip()
FIXED_TIME = (2026, 7, 17, 0, 0, 0)
EXCLUDED_PARTS = {".git", ".venv", "venv", "dist", "build", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".db", ".sqlite", ".sqlite3"}


def add_file(archive: zipfile.ZipFile, source: Path, arcname: str) -> None:
    info = zipfile.ZipInfo(arcname, FIXED_TIME)
    mode = source.stat().st_mode
    permission = 0o755 if mode & stat.S_IXUSR else 0o644
    info.external_attr = (permission & 0xFFFF) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, source.read_bytes())


def included_files(base: Path):
    for path in sorted(base.rglob("*"), key=lambda p: p.as_posix()):
        if not path.is_file():
            continue
        relative = path.relative_to(base)
        if any(part in EXCLUDED_PARTS or part.endswith(".egg-info") for part in relative.parts):
            continue
        if path.suffix in EXCLUDED_SUFFIXES:
            continue
        if relative.parts and relative.parts[0] == "outputs" and path.name != ".gitkeep":
            continue
        yield path, relative


def zip_tree(base: Path, destination: Path, prefix: str) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, relative in included_files(base):
            add_file(archive, path, f"{prefix}/{relative.as_posix()}")


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def main() -> int:
    subprocess.run([sys.executable, "scripts/release_contract.py"], cwd=ROOT, check=True)
    shutil.rmtree(DIST, ignore_errors=True)
    DIST.mkdir(parents=True)

    source_zip = DIST / f"catalyst-grit-v{VERSION}-repository.zip"
    plugin_zip = DIST / f"catalyst-grit-demo-v{VERSION}.zip"
    zip_tree(ROOT, source_zip, f"catalyst-grit-v{VERSION}")
    zip_tree(ROOT / "wordpress/catalyst-grit-demo", plugin_zip, "catalyst-grit-demo")

    installer_source = ROOT / f"install_and_push_catalyst_grit_v{VERSION.replace('.', '_')}_macos.sh"
    installer_target = DIST / installer_source.name
    shutil.copy2(installer_source, installer_target)

    artifacts = []
    for path in (source_zip, plugin_zip, installer_target):
        artifacts.append({"file": path.name, "bytes": path.stat().st_size, "sha256": digest(path)})

    manifest = {
        "product": "Catalyst Grit",
        "version": VERSION,
        "release": "Repository Integrity and Product Consolidation",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "artifacts": artifacts,
    }
    manifest_path = DIST / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    checksums = DIST / "SHA256SUMS"
    checksums.write_text("".join(f"{item['sha256']}  {item['file']}\n" for item in artifacts), encoding="utf-8")

    bundle = DIST / f"catalyst-grit-v{VERSION}-release.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(DIST.iterdir(), key=lambda p: p.name):
            if path == bundle or not path.is_file():
                continue
            add_file(archive, path, path.name)

    print(f"Built {source_zip.name}")
    print(f"Built {plugin_zip.name}")
    print(f"Built {bundle.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
