import json
import re
from pathlib import Path

from catalyst_grit import ENGINE_VERSION, SCHEMA_VERSION, __version__

ROOT = Path(__file__).resolve().parents[1]


def test_all_release_surfaces_match_version_file():
    version = (ROOT / "VERSION").read_text().strip()
    assert version == "1.2.0" == __version__ == ENGINE_VERSION == SCHEMA_VERSION
    manifest = json.loads((ROOT / "catalyst_grit_manifest.json").read_text())
    assert manifest["version"] == manifest["schema_version"] == manifest["engine_version"] == version
    for name in ["catalyst_grit_record.schema.json", "catalyst_grit_request.schema.json", "catalyst_grit_methodology_profile.schema.json", "catalyst_grit_project.schema.json", "catalyst_grit_workspace_bundle.schema.json"]:
        schema = json.loads((ROOT / "schemas" / name).read_text())
        assert schema["x-catalyst-grit-version"] == version
    assert re.search(r'^version = "1\.2\.0"$', (ROOT / "pyproject.toml").read_text(), re.M)
    plugin = (ROOT / "wordpress/catalyst-grit-demo/catalyst-grit-demo.php").read_text()
    assert "Version: 1.2.0" in plugin and "CATALYST_GRIT_DEMO_VERSION', '1.2.0'" in plugin
    assert re.search(r"^  version: 1\.2\.0$", (ROOT / "openapi.yaml").read_text(), re.M)


def test_installer_uses_isolated_local_source_smoke_test():
    installer = (ROOT / "install_and_push_catalyst_grit_v1_2_0_macos.sh").read_text()
    assert 'INSTALLER_REVISION="REPAIRED_V3"' in installer
    assert 'repository-REPAIRED_V3.zip' in installer
    assert 'rsync -a --checksum --delete' in installer
    assert 'cmp -s "$SOURCE/VERSION" "$REPO/VERSION"' in installer
    assert 'env -u PYTHONPATH -u PYTHONHOME PYTHONNOUSERSITE=1 "$PYTHON_BIN" -I -S scripts/smoke_test.py' in installer


def test_smoke_test_verifies_local_package_origin():
    smoke = (ROOT / "scripts/smoke_test.py").read_text()
    assert "local package import mismatch" in smoke
    assert "module={imported_file}" in smoke
