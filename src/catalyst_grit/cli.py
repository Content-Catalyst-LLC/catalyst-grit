"""Command-line interface for the Catalyst Grit engine and private workspace."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
import sys
from typing import Any, Sequence

from .core import DEFAULT_METHODOLOGY_PROFILE, GritValidationError, generate_record, migrate_v1_request, to_markdown, validate_request
from .storage import SQLiteWorkspaceRepository, WorkspaceError
from .version import __version__


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkspaceError(f"input file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise WorkspaceError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise WorkspaceError("input JSON must contain an object")
    return value


def _render(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _write(value: str | MappingLike, output: Path | None = None) -> None:
    text = value if isinstance(value, str) else _render(value)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text.rstrip() + "\n", encoding="utf-8")
    else:
        print(text)


MappingLike = dict[str, Any] | list[Any]


def _db_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--database", type=Path, default=Path(os.environ.get("CATALYST_GRIT_DB", "catalyst-grit.sqlite3")), help="SQLite workspace database")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="grit", description="Generate records and manage private Catalyst Grit recovery workspaces.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    generate = commands.add_parser("generate", help="Generate a canonical recovery record")
    generate.add_argument("input", type=Path)
    generate.add_argument("--format", choices=("json", "markdown"), default="json")
    generate.add_argument("--profile", type=Path)
    generate.add_argument("--output", type=Path)

    validate = commands.add_parser("validate", help="Validate and normalize a request")
    validate.add_argument("input", type=Path); validate.add_argument("--output", type=Path)
    migrate_request = commands.add_parser("migrate-request", aliases=["migrate-record"], help="Migrate a v1.0.x flat request")
    migrate_request.add_argument("input", type=Path); migrate_request.add_argument("--output", type=Path)
    profile = commands.add_parser("profile", help="Print the default methodology profile"); profile.add_argument("--output", type=Path)

    init = commands.add_parser("init", help="Create or migrate a private SQLite workspace"); _db_argument(init)
    db_migrate = commands.add_parser("migrate", help="Apply workspace database migrations"); _db_argument(db_migrate); db_migrate.add_argument("--target", type=int)
    rollback = commands.add_parser("rollback", help="Reverse workspace migrations"); _db_argument(rollback); rollback.add_argument("--steps", type=int, default=1)
    status = commands.add_parser("status", help="Show workspace health and migration status"); _db_argument(status)

    project_create = commands.add_parser("project-create", help="Create a private recovery project"); _db_argument(project_create)
    project_create.add_argument("--title", required=True); project_create.add_argument("--description", default=""); project_create.add_argument("--owner", default="self"); project_create.add_argument("--retention-days", type=int)
    project_list = commands.add_parser("project-list", help="List recovery projects"); _db_argument(project_list); project_list.add_argument("--all", action="store_true")
    project_show = commands.add_parser("project-show", help="Show one recovery project"); _db_argument(project_show); project_show.add_argument("project_id")
    project_archive = commands.add_parser("project-archive", help="Archive a recovery project"); _db_argument(project_archive); project_archive.add_argument("project_id"); project_archive.add_argument("--reason", default="")

    record_save = commands.add_parser("record-save", help="Generate/import and persist a record"); _db_argument(record_save); record_save.add_argument("project_id"); record_save.add_argument("input", type=Path); record_save.add_argument("--reason", default="saved")
    record_revise = commands.add_parser("record-revise", help="Create an append-only record revision"); _db_argument(record_revise); record_revise.add_argument("record_id"); record_revise.add_argument("input", type=Path); record_revise.add_argument("--reason", default="reassessment")
    record_show = commands.add_parser("record-show", help="Reopen a saved recovery record"); _db_argument(record_show); record_show.add_argument("record_id"); record_show.add_argument("--canonical", action="store_true")
    record_list = commands.add_parser("record-list", help="List records in a project"); _db_argument(record_list); record_list.add_argument("project_id"); record_list.add_argument("--all", action="store_true")
    revisions = commands.add_parser("record-revisions", help="Inspect append-only revision history"); _db_argument(revisions); revisions.add_argument("record_id")
    compare = commands.add_parser("record-compare", help="Compare two revisions"); _db_argument(compare); compare.add_argument("record_id"); compare.add_argument("--from", dest="from_revision", type=int, required=True); compare.add_argument("--to", dest="to_revision", type=int, required=True)
    duplicate = commands.add_parser("record-duplicate", help="Duplicate a record into a new draft"); _db_argument(duplicate); duplicate.add_argument("record_id"); duplicate.add_argument("--project")
    archive = commands.add_parser("record-archive", help="Archive a record through a new revision"); _db_argument(archive); archive.add_argument("record_id"); archive.add_argument("--reason", default="archived")
    delete = commands.add_parser("record-delete", help="Soft-delete a record"); _db_argument(delete); delete.add_argument("record_id"); delete.add_argument("--reason", default="deleted")
    retention = commands.add_parser("record-retention", help="Set a record retention date or duration"); _db_argument(retention); retention.add_argument("record_id"); retention.add_argument("--until"); retention.add_argument("--days", type=int)
    purge = commands.add_parser("record-purge", help="Permanently purge a record and its revisions"); _db_argument(purge); purge.add_argument("record_id"); purge.add_argument("--confirm", action="store_true")

    checkpoint_add = commands.add_parser("checkpoint-add", help="Schedule a review checkpoint"); _db_argument(checkpoint_add); checkpoint_add.add_argument("project_id"); checkpoint_add.add_argument("--title", required=True); checkpoint_add.add_argument("--record"); checkpoint_add.add_argument("--date"); checkpoint_add.add_argument("--notes", default="")
    checkpoint_list = commands.add_parser("checkpoint-list", help="List project or record checkpoints"); _db_argument(checkpoint_list); checkpoint_list.add_argument("project_id"); checkpoint_list.add_argument("--record")
    checkpoint_complete = commands.add_parser("checkpoint-complete", help="Complete a checkpoint"); _db_argument(checkpoint_complete); checkpoint_complete.add_argument("checkpoint_id"); checkpoint_complete.add_argument("--notes")

    review_add = commands.add_parser("review-add", help="Record a human review event"); _db_argument(review_add); review_add.add_argument("record_id"); review_add.add_argument("--status", required=True); review_add.add_argument("--reviewer", required=True); review_add.add_argument("--notes", default="")
    review_list = commands.add_parser("review-list", help="List record reviews"); _db_argument(review_list); review_list.add_argument("record_id")

    export = commands.add_parser("workspace-export", help="Export a record or project bundle"); _db_argument(export); group = export.add_mutually_exclusive_group(required=True); group.add_argument("--record"); group.add_argument("--project"); export.add_argument("--output", type=Path, required=True)
    import_cmd = commands.add_parser("workspace-import", help="Import v1.0/v1.1 records or workspace bundles"); _db_argument(import_cmd); import_cmd.add_argument("input", type=Path); import_cmd.add_argument("--project")
    return parser


def _workspace_command(args: argparse.Namespace) -> Any:
    auto_migrate = args.command not in {"rollback"}
    with SQLiteWorkspaceRepository(args.database, auto_migrate=auto_migrate) as repo:
        if args.command == "init": return repo.health()
        if args.command == "migrate": return {"applied": repo.migrations.migrate(args.target), "status": repo.migrations.status()}
        if args.command == "rollback": return {"rolled_back": repo.migrations.rollback(args.steps), "status": repo.migrations.status()}
        if args.command == "status": return repo.health()
        if args.command == "project-create": return repo.create_project(args.title, description=args.description, owner_id=args.owner, retention_days=args.retention_days)
        if args.command == "project-list": return repo.list_projects(include_archived=args.all, include_deleted=args.all)
        if args.command == "project-show": return repo.get_project(args.project_id, include_deleted=True)
        if args.command == "project-archive": return repo.archive_project(args.project_id, reason=args.reason)
        if args.command == "record-save": return repo.save_record(args.project_id, _read_json(args.input), reason=args.reason)
        if args.command == "record-revise": return repo.revise_record(args.record_id, _read_json(args.input), reason=args.reason)
        if args.command == "record-show": return repo.get_record(args.record_id, include_canonical=args.canonical, include_deleted=True)
        if args.command == "record-list": return repo.list_records(args.project_id, include_archived=args.all, include_deleted=args.all)
        if args.command == "record-revisions": return repo.list_revisions(args.record_id)
        if args.command == "record-compare": return repo.compare_revisions(args.record_id, args.from_revision, args.to_revision)
        if args.command == "record-duplicate": return repo.duplicate_record(args.record_id, project_id=args.project)
        if args.command == "record-archive": return repo.archive_record(args.record_id, reason=args.reason)
        if args.command == "record-delete": return repo.delete_record(args.record_id, reason=args.reason)
        if args.command == "record-retention": return repo.set_retention(args.record_id, retention_until=args.until, retention_days=args.days)
        if args.command == "record-purge": return repo.purge_record(args.record_id, confirm=args.confirm)
        if args.command == "checkpoint-add": return repo.create_checkpoint(args.project_id, args.title, record_id=args.record, scheduled_for=args.date, notes=args.notes)
        if args.command == "checkpoint-list": return repo.list_checkpoints(args.project_id, record_id=args.record)
        if args.command == "checkpoint-complete": return repo.complete_checkpoint(args.checkpoint_id, notes=args.notes)
        if args.command == "review-add": return repo.add_review(args.record_id, status=args.status, reviewer_id=args.reviewer, notes=args.notes)
        if args.command == "review-list": return repo.list_reviews(args.record_id)
        if args.command == "workspace-export":
            payload = repo.export_record(args.record) if args.record else repo.export_project(args.project)
            repo.write_export(payload, args.output)
            return {"output": str(args.output), "format": payload["format"]}
        if args.command == "workspace-import": return repo.import_payload(_read_json(args.input), project_id=args.project)
    raise WorkspaceError(f"unsupported command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser(); args = parser.parse_args(argv)
    try:
        if args.command == "profile": _write(DEFAULT_METHODOLOGY_PROFILE, args.output); return 0
        if args.command in {"validate", "generate", "migrate-request", "migrate-record"}:
            data = _read_json(args.input)
            if args.command == "validate": _write(validate_request(data), args.output); return 0
            if args.command in {"migrate-request", "migrate-record"}: _write(migrate_v1_request(data), args.output); return 0
            profile = _read_json(args.profile) if args.profile else None
            record = generate_record(data, methodology_profile=profile)
            _write(record.to_dict() if args.format == "json" else to_markdown(record), args.output)
            return 0
        _write(_workspace_command(args))
        return 0
    except GritValidationError as exc:
        print(_render(exc.to_dict()), file=sys.stderr); return 2
    except (WorkspaceError, ValueError, sqlite3.Error) as exc:  # type: ignore[name-defined]
        print(_render({"error": "workspace_error", "message": str(exc)}), file=sys.stderr); return 3


if __name__ == "__main__":
    raise SystemExit(main())
