from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_forbidden_generated_artifacts_are_not_tracked_in_source_tree():
    forbidden = []
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if any(part in {".git", ".venv", "dist", "build", "__pycache__", ".pytest_cache"} for part in relative.parts):
            continue
        if path.is_file() and (path.suffix in {".db", ".sqlite", ".sqlite3"} or ".egg-info" in relative.parts):
            forbidden.append(str(relative))
    assert forbidden == []


def test_legacy_tracker_is_not_importable_from_package():
    assert not (ROOT / "project").exists()
    assert not (ROOT / "notebooks").exists()
    package_files = {path.name for path in (ROOT / "src/catalyst_grit").glob("*.py")}
    assert package_files == {"__init__.py", "cli.py", "core.py", "version.py"}


def test_production_copy_avoids_trait_metric_language():
    files = [
        ROOT / "README.md",
        ROOT / "pyproject.toml",
        ROOT / "openapi.yaml",
        ROOT / "wordpress/catalyst-grit-demo/README.md",
    ]
    forbidden = ("duckworth", "consistency_of_interests", "deliberate_practice_ratio")
    for path in files:
        text = path.read_text(encoding="utf-8").lower()
        assert not any(term in text for term in forbidden), path
