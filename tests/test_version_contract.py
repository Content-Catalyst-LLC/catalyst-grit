import json
import re
from pathlib import Path

from catalyst_grit import ENGINE_VERSION, SCHEMA_VERSION, __version__

ROOT = Path(__file__).resolve().parents[1]


def test_all_release_surfaces_match_version_file():
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert version == "1.0.1"
    assert __version__ == version
    assert ENGINE_VERSION == version
    assert SCHEMA_VERSION == version

    manifest = json.loads((ROOT / "catalyst_grit_manifest.json").read_text())
    assert manifest["version"] == version
    assert manifest["schema_version"] == version
    assert manifest["engine_version"] == version

    schema = json.loads((ROOT / "schemas/catalyst_grit_record.schema.json").read_text())
    assert schema["x-catalyst-grit-version"] == version
    assert schema["properties"]["schema_version"]["const"] == version

    pyproject = (ROOT / "pyproject.toml").read_text()
    assert re.search(r'^version = "' + re.escape(version) + r'"$', pyproject, re.M)

    plugin = (ROOT / "wordpress/catalyst-grit-demo/catalyst-grit-demo.php").read_text()
    assert re.search(r"Version:\s*" + re.escape(version), plugin)
    assert "CATALYST_GRIT_DEMO_VERSION', '" + version + "'" in plugin

    openapi = (ROOT / "openapi.yaml").read_text()
    assert re.search(r"^  version: " + re.escape(version) + r"$", openapi, re.M)
