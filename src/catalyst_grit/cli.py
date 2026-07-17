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
    record_map = commands.add_parser("record-map", help="Inspect saved condition maps, completeness, contradictions, and flags"); _db_argument(record_map); record_map.add_argument("record_id")
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


    action_list = commands.add_parser("action-list", help="List executable actions and support-oriented timing signals"); _db_argument(action_list); action_list.add_argument("record_id"); action_list.add_argument("--revision", type=int); action_list.add_argument("--as-of")
    action_show = commands.add_parser("action-show", help="Show one action and its current attention state"); _db_argument(action_show); action_show.add_argument("action_id"); action_show.add_argument("--as-of")
    action_update = commands.add_parser("action-update", help="Update an action with append-only status history"); _db_argument(action_update); action_update.add_argument("action_id"); action_update.add_argument("--status", required=True); action_update.add_argument("--reason", default="status updated"); action_update.add_argument("--blocked-reason"); action_update.add_argument("--completion-evidence"); action_update.add_argument("--escalation-path")
    action_history = commands.add_parser("action-history", help="Show append-only action status history"); _db_argument(action_history); action_history.add_argument("action_id")

    blocker_add = commands.add_parser("blocker-add", help="Add a blocker or support need without punitive language"); _db_argument(blocker_add); blocker_add.add_argument("record_id"); blocker_add.add_argument("--title", required=True); blocker_add.add_argument("--action"); blocker_add.add_argument("--owner"); blocker_add.add_argument("--required-support", default=""); blocker_add.add_argument("--escalation-path", default=""); blocker_add.add_argument("--notes", default="")
    blocker_list = commands.add_parser("blocker-list", help="List blocker and escalation entries"); _db_argument(blocker_list); blocker_list.add_argument("record_id"); blocker_list.add_argument("--open-only", action="store_true")
    blocker_update = commands.add_parser("blocker-update", help="Resolve, reopen, or escalate a blocker"); _db_argument(blocker_update); blocker_update.add_argument("blocker_id"); blocker_update.add_argument("--status", required=True); blocker_update.add_argument("--notes"); blocker_update.add_argument("--escalation-path")

    reassess = commands.add_parser("record-reassess", help="Create a new revision at a checkpoint and compare plan versus observation"); _db_argument(reassess); reassess.add_argument("record_id"); reassess.add_argument("input", type=Path); reassess.add_argument("--observed-summary", required=True); reassess.add_argument("--checkpoint"); reassess.add_argument("--changed-assumption", action="append", default=[]); reassess.add_argument("--no-carry", action="store_true")
    reassessments = commands.add_parser("reassessment-list", help="List checkpoint reassessments and plan comparisons"); _db_argument(reassessments); reassessments.add_argument("record_id")

    review_add = commands.add_parser("review-add", help="Record a human review event"); _db_argument(review_add); review_add.add_argument("record_id"); review_add.add_argument("--status", required=True); review_add.add_argument("--reviewer", required=True); review_add.add_argument("--notes", default="")
    review_list = commands.add_parser("review-list", help="List record reviews"); _db_argument(review_list); review_list.add_argument("record_id")

    retrospectives = commands.add_parser("retrospective-list", help="List append-only retrospectives for a record"); _db_argument(retrospectives); retrospectives.add_argument("record_id")
    patterns = commands.add_parser("pattern-list", help="Detect explainable recurring project patterns"); _db_argument(patterns); patterns.add_argument("project_id"); patterns.add_argument("--minimum-occurrences", type=int, default=2); patterns.add_argument("--include-singletons", action="store_true")
    pattern_review = commands.add_parser("pattern-review", help="Accept, reject, or correct a detected pattern"); _db_argument(pattern_review); pattern_review.add_argument("project_id"); pattern_review.add_argument("pattern_key"); pattern_review.add_argument("--decision", choices=("accept","reject","correct"), required=True); pattern_review.add_argument("--corrected-label", default=""); pattern_review.add_argument("--notes", default="")
    pattern_reviews = commands.add_parser("pattern-review-list", help="List append-only pattern review decisions"); _db_argument(pattern_reviews); pattern_reviews.add_argument("project_id")
    change_add = commands.add_parser("system-change-add", help="Create a system-change proposal linked to source records"); _db_argument(change_add); change_add.add_argument("project_id"); change_add.add_argument("--title", required=True); change_add.add_argument("--proposed-change", required=True); change_add.add_argument("--owner"); change_add.add_argument("--record", action="append", required=True); change_add.add_argument("--evidence-note", default=""); change_add.add_argument("--expected-benefit", default=""); change_add.add_argument("--pilot-start"); change_add.add_argument("--pilot-end"); change_add.add_argument("--decision", default="proposed")
    change_list = commands.add_parser("system-change-list", help="List project system-change records"); _db_argument(change_list); change_list.add_argument("project_id")
    change_show = commands.add_parser("system-change-show", help="Show one system-change record and event history"); _db_argument(change_show); change_show.add_argument("system_change_id")
    change_update = commands.add_parser("system-change-update", help="Review a system change after its pilot"); _db_argument(change_update); change_update.add_argument("system_change_id"); change_update.add_argument("--decision", required=True); change_update.add_argument("--review-result", default=""); change_update.add_argument("--reason", default="reviewed"); change_update.add_argument("--owner"); change_update.add_argument("--pilot-start"); change_update.add_argument("--pilot-end")

    member_add = commands.add_parser("team-member-add", help="Add a consent-aware project team member"); _db_argument(member_add); member_add.add_argument("project_id"); member_add.add_argument("--member-key", required=True); member_add.add_argument("--display-name", required=True); member_add.add_argument("--role", default="contributor"); member_add.add_argument("--status", default="invited"); member_add.add_argument("--access-scope", default="shared"); member_add.add_argument("--consent-status", default="pending"); member_add.add_argument("--actor", default="self")
    member_list = commands.add_parser("team-member-list", help="List project team roles and consent states"); _db_argument(member_list); member_list.add_argument("project_id"); member_list.add_argument("--all", action="store_true")
    member_update = commands.add_parser("team-member-update", help="Update a team role, status, scope, or consent state"); _db_argument(member_update); member_update.add_argument("membership_id"); member_update.add_argument("--role"); member_update.add_argument("--status"); member_update.add_argument("--access-scope"); member_update.add_argument("--consent-status"); member_update.add_argument("--actor", default="self")

    session_create = commands.add_parser("session-create", help="Create a facilitated team recovery review"); _db_argument(session_create); session_create.add_argument("project_id"); session_create.add_argument("--title", required=True); session_create.add_argument("--purpose", default=""); session_create.add_argument("--facilitator", default="self"); session_create.add_argument("--record"); session_create.add_argument("--scheduled-for"); session_create.add_argument("--ground-rule", action="append"); session_create.add_argument("--agenda-item", action="append"); session_create.add_argument("--notes", default=""); session_create.add_argument("--actor", default="self")
    session_list = commands.add_parser("session-list", help="List facilitated reviews for a project"); _db_argument(session_list); session_list.add_argument("project_id"); session_list.add_argument("--actor", default="self")
    session_show = commands.add_parser("session-show", help="Show a consent-filtered facilitated review brief"); _db_argument(session_show); session_show.add_argument("session_id"); session_show.add_argument("--actor", default="self")
    session_update = commands.add_parser("session-update", help="Start, complete, cancel, or reopen a facilitated review"); _db_argument(session_update); session_update.add_argument("session_id"); session_update.add_argument("--status", required=True); session_update.add_argument("--notes"); session_update.add_argument("--actor", default="self")
    participant_add = commands.add_parser("session-participant-add", help="Add or update a session participant and sharing scope"); _db_argument(participant_add); participant_add.add_argument("session_id"); participant_add.add_argument("--member-key", required=True); participant_add.add_argument("--participation-status", default="invited"); participant_add.add_argument("--consent-status", default="pending"); participant_add.add_argument("--sharing-scope", default="shared"); participant_add.add_argument("--actor", default="self")

    perspective_add = commands.add_parser("perspective-add", help="Add an append-only team perspective with consent and sharing scope"); _db_argument(perspective_add); perspective_add.add_argument("project_id"); perspective_add.add_argument("--content", required=True); perspective_add.add_argument("--type", dest="perspective_type", default="other"); perspective_add.add_argument("--member-key"); perspective_add.add_argument("--label", default=""); perspective_add.add_argument("--session"); perspective_add.add_argument("--record"); perspective_add.add_argument("--sharing-scope", default="shared"); perspective_add.add_argument("--consent-status", default="granted"); perspective_add.add_argument("--source-path", default=""); perspective_add.add_argument("--actor", default="self")
    perspective_list = commands.add_parser("perspective-list", help="List perspectives visible to the requesting team member"); _db_argument(perspective_list); perspective_list.add_argument("project_id"); perspective_list.add_argument("--session"); perspective_list.add_argument("--record"); perspective_list.add_argument("--actor", default="self"); perspective_list.add_argument("--include-withdrawn", action="store_true")

    agreement_add = commands.add_parser("agreement-add", help="Create a shared facilitated-review agreement"); _db_argument(agreement_add); agreement_add.add_argument("session_id"); agreement_add.add_argument("--title", required=True); agreement_add.add_argument("--owner-key"); agreement_add.add_argument("--due-date"); agreement_add.add_argument("--status", default="proposed"); agreement_add.add_argument("--support-needed", default=""); agreement_add.add_argument("--actor", default="self")
    agreement_update = commands.add_parser("agreement-update", help="Update an agreement with append-only history"); _db_argument(agreement_update); agreement_update.add_argument("agreement_id"); agreement_update.add_argument("--status", required=True); agreement_update.add_argument("--reason", default="agreement reviewed"); agreement_update.add_argument("--completion-evidence", default=""); agreement_update.add_argument("--support-needed"); agreement_update.add_argument("--actor", default="self")
    team_summary = commands.add_parser("team-summary", help="Summarize team recovery work without individual scoring"); _db_argument(team_summary); team_summary.add_argument("project_id"); team_summary.add_argument("--actor", default="self")

    evidence_add = commands.add_parser("evidence-add", help="Add a traceable evidence item"); _db_argument(evidence_add); evidence_add.add_argument("project_id"); evidence_add.add_argument("--title", required=True); evidence_add.add_argument("--type", dest="evidence_type", default="note"); evidence_add.add_argument("--content", default=""); evidence_add.add_argument("--record"); evidence_add.add_argument("--source-uri", default=""); evidence_add.add_argument("--artifact-id", default=""); evidence_add.add_argument("--source-product", default=""); evidence_add.add_argument("--source-version", default=""); evidence_add.add_argument("--strength", default="unknown"); evidence_add.add_argument("--review-state", default="unreviewed"); evidence_add.add_argument("--observed-at"); evidence_add.add_argument("--actor", default="self")
    evidence_list = commands.add_parser("evidence-list", help="List project or record evidence"); _db_argument(evidence_list); evidence_list.add_argument("project_id"); evidence_list.add_argument("--record"); evidence_list.add_argument("--type", dest="evidence_type"); evidence_list.add_argument("--review-state")
    evidence_review = commands.add_parser("evidence-review", help="Review evidence strength and state with append-only history"); _db_argument(evidence_review); evidence_review.add_argument("evidence_id"); evidence_review.add_argument("--state", required=True); evidence_review.add_argument("--strength"); evidence_review.add_argument("--notes", default=""); evidence_review.add_argument("--actor", default="self")
    evidence_link = commands.add_parser("evidence-link", help="Link evidence to an assumption, action, decision, or handoff"); _db_argument(evidence_link); evidence_link.add_argument("evidence_id"); evidence_link.add_argument("target_type"); evidence_link.add_argument("target_id"); evidence_link.add_argument("--relation", default="supports"); evidence_link.add_argument("--notes", default=""); evidence_link.add_argument("--actor", default="self")
    evidence_ledger = commands.add_parser("evidence-ledger", help="Summarize evidence strength, review state, and conflicts"); _db_argument(evidence_ledger); evidence_ledger.add_argument("project_id"); evidence_ledger.add_argument("--record")

    assumption_add = commands.add_parser("assumption-add", help="Record an explicit uncertainty-aware assumption"); _db_argument(assumption_add); assumption_add.add_argument("project_id"); assumption_add.add_argument("--statement", required=True); assumption_add.add_argument("--record"); assumption_add.add_argument("--uncertainty", default=""); assumption_add.add_argument("--confidence", type=int, default=50); assumption_add.add_argument("--owner"); assumption_add.add_argument("--review-due"); assumption_add.add_argument("--source-path", action="append", default=[]); assumption_add.add_argument("--actor", default="self")
    assumption_list = commands.add_parser("assumption-list", help="List explicit assumptions and review states"); _db_argument(assumption_list); assumption_list.add_argument("project_id"); assumption_list.add_argument("--record"); assumption_list.add_argument("--status")
    assumption_update = commands.add_parser("assumption-update", help="Validate, reject, retire, or revise an assumption"); _db_argument(assumption_update); assumption_update.add_argument("assumption_id"); assumption_update.add_argument("--status", required=True); assumption_update.add_argument("--confidence", type=int); assumption_update.add_argument("--uncertainty"); assumption_update.add_argument("--owner"); assumption_update.add_argument("--review-due"); assumption_update.add_argument("--reason", default="assumption reviewed"); assumption_update.add_argument("--actor", default="self")
    assumption_matrix = commands.add_parser("assumption-matrix", help="Summarize active assumptions and review attention"); _db_argument(assumption_matrix); assumption_matrix.add_argument("project_id"); assumption_matrix.add_argument("--record")

    handoff_create = commands.add_parser("handoff-create", help="Create a validated cross-product artifact handoff"); _db_argument(handoff_create); handoff_create.add_argument("project_id"); handoff_create.add_argument("--source-product", required=True); handoff_create.add_argument("--source-version", required=True); handoff_create.add_argument("--target-product", required=True); handoff_create.add_argument("--artifact-type", required=True); handoff_create.add_argument("--artifact-id", required=True); handoff_create.add_argument("--payload", type=Path); handoff_create.add_argument("--record"); handoff_create.add_argument("--direction", default="inbound"); handoff_create.add_argument("--reference-mode", default="snapshot"); handoff_create.add_argument("--source-uri", default=""); handoff_create.add_argument("--stale-after"); handoff_create.add_argument("--actor", default="self")
    handoff_list = commands.add_parser("handoff-list", help="List cross-product handoffs and validation state"); _db_argument(handoff_list); handoff_list.add_argument("project_id"); handoff_list.add_argument("--record"); handoff_list.add_argument("--target-product"); handoff_list.add_argument("--state")
    handoff_show = commands.add_parser("handoff-show", help="Show a handoff, provenance chain, and event history"); _db_argument(handoff_show); handoff_show.add_argument("handoff_id")
    handoff_validate = commands.add_parser("handoff-validate", help="Validate a handoff or record stale/conflicting state"); _db_argument(handoff_validate); handoff_validate.add_argument("handoff_id"); handoff_validate.add_argument("--payload", type=Path); handoff_validate.add_argument("--state"); handoff_validate.add_argument("--notes", default=""); handoff_validate.add_argument("--actor", default="self")
    decision_handoff = commands.add_parser("decision-handoff", help="Build a provenance-preserving Decision Studio packet"); _db_argument(decision_handoff); decision_handoff.add_argument("record_id"); decision_handoff.add_argument("--actor", default="self"); decision_handoff.add_argument("--output", type=Path)

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
        if args.command == "record-map":
            canonical = repo.get_record(args.record_id, include_canonical=True, include_deleted=True)["canonical"]
            return {"record_id": args.record_id, "condition_map": canonical["findings"]["condition_map"], "interpretation": canonical["findings"]["interpretation"], "flags": canonical["findings"]["flags"]}
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
        if args.command == "action-list": return repo.list_actions(args.record_id, revision_number=args.revision, as_of=args.as_of)
        if args.command == "action-show": return repo.get_action(args.action_id, as_of=args.as_of)
        if args.command == "action-update": return repo.update_action(args.action_id, status=args.status, reason=args.reason, blocked_reason=args.blocked_reason, completion_evidence=args.completion_evidence, escalation_path=args.escalation_path)
        if args.command == "action-history": return repo.action_history(args.action_id)
        if args.command == "blocker-add": return repo.add_blocker(args.record_id, args.title, action_id=args.action, owner=args.owner, required_support=args.required_support, escalation_path=args.escalation_path, notes=args.notes)
        if args.command == "blocker-list": return repo.list_blockers(args.record_id, include_resolved=not args.open_only)
        if args.command == "blocker-update": return repo.update_blocker(args.blocker_id, status=args.status, notes=args.notes, escalation_path=args.escalation_path)
        if args.command == "record-reassess": return repo.create_reassessment(args.record_id, _read_json(args.input), observed_summary=args.observed_summary, checkpoint_id=args.checkpoint, changed_assumptions=args.changed_assumption, carry_unresolved=not args.no_carry)
        if args.command == "reassessment-list": return repo.list_reassessments(args.record_id)
        if args.command == "review-add": return repo.add_review(args.record_id, status=args.status, reviewer_id=args.reviewer, notes=args.notes)
        if args.command == "review-list": return repo.list_reviews(args.record_id)
        if args.command == "retrospective-list": return repo.list_retrospectives(args.record_id)
        if args.command == "pattern-list": return repo.detect_project_patterns(args.project_id, minimum_occurrences=args.minimum_occurrences, include_singletons=args.include_singletons)
        if args.command == "pattern-review": return repo.review_pattern(args.project_id, args.pattern_key, decision=args.decision, corrected_label=args.corrected_label, notes=args.notes)
        if args.command == "pattern-review-list": return repo.list_pattern_reviews(args.project_id)
        if args.command == "system-change-add": return repo.create_system_change(args.project_id, args.title, args.proposed_change, owner=args.owner, source_record_ids=args.record, evidence_note=args.evidence_note, expected_benefit=args.expected_benefit, pilot_start=args.pilot_start, pilot_end=args.pilot_end, decision=args.decision)
        if args.command == "system-change-list": return repo.list_system_changes(args.project_id)
        if args.command == "system-change-show": return repo.get_system_change(args.system_change_id)
        if args.command == "system-change-update": return repo.update_system_change(args.system_change_id, decision=args.decision, review_result=args.review_result, reason=args.reason, owner=args.owner, pilot_start=args.pilot_start, pilot_end=args.pilot_end)
        if args.command == "team-member-add": return repo.add_team_member(args.project_id, args.member_key, args.display_name, role=args.role, status=args.status, access_scope=args.access_scope, consent_status=args.consent_status, actor_id=args.actor)
        if args.command == "team-member-list": return repo.list_team_members(args.project_id, include_removed=args.all)
        if args.command == "team-member-update": return repo.update_team_member(args.membership_id, role=args.role, status=args.status, access_scope=args.access_scope, consent_status=args.consent_status, actor_id=args.actor)
        if args.command == "session-create": return repo.create_facilitated_session(args.project_id, args.title, purpose=args.purpose, facilitator_key=args.facilitator, record_id=args.record, scheduled_for=args.scheduled_for, ground_rules=args.ground_rule, agenda=args.agenda_item, notes=args.notes, actor_id=args.actor)
        if args.command == "session-list": return repo.list_facilitated_sessions(args.project_id, actor_id=args.actor)
        if args.command == "session-show": return repo.get_facilitated_session(args.session_id, actor_id=args.actor)
        if args.command == "session-update": return repo.update_facilitated_session(args.session_id, status=args.status, notes=args.notes, actor_id=args.actor)
        if args.command == "session-participant-add": return repo.add_session_participant(args.session_id, args.member_key, participation_status=args.participation_status, consent_status=args.consent_status, sharing_scope=args.sharing_scope, actor_id=args.actor)
        if args.command == "perspective-add": return repo.add_team_perspective(args.project_id, args.content, perspective_type=args.perspective_type, member_key=args.member_key, contributor_label=args.label, session_id=args.session, record_id=args.record, sharing_scope=args.sharing_scope, consent_status=args.consent_status, source_path=args.source_path, actor_id=args.actor)
        if args.command == "perspective-list": return repo.list_team_perspectives(args.project_id, session_id=args.session, record_id=args.record, actor_id=args.actor, include_withdrawn=args.include_withdrawn)
        if args.command == "agreement-add": return repo.create_facilitated_agreement(args.session_id, args.title, owner_key=args.owner_key, due_date=args.due_date, status=args.status, support_needed=args.support_needed, actor_id=args.actor)
        if args.command == "agreement-update": return repo.update_facilitated_agreement(args.agreement_id, status=args.status, reason=args.reason, completion_evidence=args.completion_evidence, support_needed=args.support_needed, actor_id=args.actor)
        if args.command == "team-summary": return repo.team_recovery_summary(args.project_id, actor_id=args.actor)
        if args.command == "evidence-add": return repo.add_evidence(args.project_id, args.title, evidence_type=args.evidence_type, content=args.content, record_id=args.record, source_uri=args.source_uri, source_artifact_id=args.artifact_id, source_product=args.source_product, source_version=args.source_version, strength=args.strength, review_state=args.review_state, observed_at=args.observed_at, actor_id=args.actor)
        if args.command == "evidence-list": return repo.list_evidence(args.project_id, record_id=args.record, evidence_type=args.evidence_type, review_state=args.review_state)
        if args.command == "evidence-review": return repo.review_evidence(args.evidence_id, review_state=args.state, strength=args.strength, notes=args.notes, actor_id=args.actor)
        if args.command == "evidence-link": return repo.link_evidence(args.evidence_id, args.target_type, args.target_id, relation=args.relation, notes=args.notes, actor_id=args.actor)
        if args.command == "evidence-ledger": return repo.evidence_ledger(args.project_id, record_id=args.record)
        if args.command == "assumption-add": return repo.add_assumption(args.project_id, args.statement, record_id=args.record, uncertainty=args.uncertainty, confidence=args.confidence, owner=args.owner, review_due=args.review_due, source_paths=args.source_path, actor_id=args.actor)
        if args.command == "assumption-list": return repo.list_assumptions(args.project_id, record_id=args.record, status=args.status)
        if args.command == "assumption-update": return repo.update_assumption(args.assumption_id, status=args.status, confidence=args.confidence, uncertainty=args.uncertainty, owner=args.owner, review_due=args.review_due, reason=args.reason, actor_id=args.actor)
        if args.command == "assumption-matrix": return repo.assumption_matrix(args.project_id, record_id=args.record)
        if args.command == "handoff-create": return repo.create_handoff(args.project_id, source_product=args.source_product, source_version=args.source_version, target_product=args.target_product, artifact_type=args.artifact_type, artifact_id=args.artifact_id, payload=_read_json(args.payload) if args.payload else {}, record_id=args.record, direction=args.direction, reference_mode=args.reference_mode, source_uri=args.source_uri, stale_after=args.stale_after, actor_id=args.actor)
        if args.command == "handoff-list": return repo.list_handoffs(args.project_id, record_id=args.record, target_product=args.target_product, validation_state=args.state)
        if args.command == "handoff-show": return repo.get_handoff(args.handoff_id)
        if args.command == "handoff-validate": return repo.validate_handoff(args.handoff_id, payload=_read_json(args.payload) if args.payload else None, state=args.state, conflict_notes=args.notes, actor_id=args.actor)
        if args.command == "decision-handoff":
            packet = repo.build_decision_handoff(args.record_id, actor_id=args.actor)
            if args.output:
                repo.write_export(packet, args.output)
                return {"output": str(args.output), "handoff_id": packet["handoff_id"], "content_hash": packet["content_hash"]}
            return packet
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
