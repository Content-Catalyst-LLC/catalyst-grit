import json
from pathlib import Path

from catalyst_grit.cli import main

ROOT = Path(__file__).resolve().parents[1]


def parsed(capsys):
    return json.loads(capsys.readouterr().out)


def test_cli_init_and_status(tmp_path, capsys):
    db = tmp_path / "cli.sqlite3"
    assert main(["init", "--database", str(db)]) == 0
    assert parsed(capsys)["migrations"]["current"] == 3
    assert main(["status", "--database", str(db)]) == 0
    assert parsed(capsys)["integrity"] == "ok"


def test_cli_project_save_show_and_revision_compare(tmp_path, capsys):
    db = tmp_path / "flow.sqlite3"
    assert main(["project-create", "--database", str(db), "--title", "CLI recovery"]) == 0
    project = parsed(capsys)
    assert project["visibility"] == "private"
    assert main(["record-save", "--database", str(db), project["project_id"], str(ROOT / "examples/grit_record_input.json")]) == 0
    saved = parsed(capsys); record_id = saved["record"]["record_id"]
    changed = json.loads((ROOT / "examples/grit_record_input.json").read_text())
    changed["metadata"]["updated_at"] = "2026-07-18T12:00:00Z"
    changed["input"]["capacity"]["clarity_level"] = 8
    changed_path = tmp_path / "changed.json"; changed_path.write_text(json.dumps(changed))
    assert main(["record-revise", "--database", str(db), record_id, str(changed_path)]) == 0
    parsed(capsys)
    assert main(["record-compare", "--database", str(db), record_id, "--from", "1", "--to", "2"]) == 0
    comparison = parsed(capsys)
    assert any(item["path"] == "$.normalized_input.capacity.clarity_level" for item in comparison["changes"])


def test_cli_workspace_export_and_import(tmp_path, capsys):
    source = tmp_path / "source.sqlite3"; target = tmp_path / "target.sqlite3"; bundle = tmp_path / "bundle.json"
    main(["project-create", "--database", str(source), "--title", "Export"]); project = parsed(capsys)
    main(["record-save", "--database", str(source), project["project_id"], str(ROOT / "examples/grit_record_input.json")]); record = parsed(capsys)["record"]
    assert main(["workspace-export", "--database", str(source), "--record", record["record_id"], "--output", str(bundle)]) == 0
    assert parsed(capsys)["format"] == "catalyst-grit-workspace/1.0"
    assert main(["workspace-import", "--database", str(target), str(bundle)]) == 0
    imported = parsed(capsys)
    assert imported["project_id"] == project["project_id"]
    assert main(["record-show", "--database", str(target), record["record_id"], "--canonical"]) == 0
    assert parsed(capsys)["canonical"]["metadata"]["record_id"] == record["record_id"]


def test_cli_purge_without_confirmation_fails(tmp_path, capsys):
    db = tmp_path / "purge.sqlite3"
    main(["project-create", "--database", str(db), "--title", "Purge"]); project = parsed(capsys)
    main(["record-save", "--database", str(db), project["project_id"], str(ROOT / "examples/grit_record_input.json")]); record = parsed(capsys)["record"]
    assert main(["record-purge", "--database", str(db), record["record_id"]]) == 3
    error = json.loads(capsys.readouterr().err)
    assert "confirm=True" in error["message"]
