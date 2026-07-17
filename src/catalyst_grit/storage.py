"""Private, local-first persistence for Catalyst Grit recovery workspaces.

The repository uses SQLite in portable mode and keeps SQL behind a small
repository abstraction so a later PostgreSQL implementation can preserve the
same service contract. Records are private by default, revisions and audit
entries are append-only, and destructive purge requires an explicit flag.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from importlib import resources
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Iterator, Mapping, Sequence
from uuid import uuid4

from .core import RecoveryRecord, generate_record, migrate_v1_request
from .version import ENGINE_VERSION, SCHEMA_VERSION, __version__

WORKSPACE_FORMAT = "catalyst-grit-workspace/1.0"
MIGRATION_PACKAGE = "catalyst_grit.migrations"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _pretty(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


class WorkspaceError(RuntimeError):
    """Raised for persistent-workspace contract failures."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    up_sql: str
    down_sql: str


class MigrationManager:
    """Apply and reverse ordered packaged SQL migrations."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
               version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL
            )"""
        )
        self.connection.commit()

    @staticmethod
    def available() -> list[Migration]:
        root = resources.files(MIGRATION_PACKAGE)
        migrations: list[Migration] = []
        for path in sorted(root.iterdir(), key=lambda item: item.name):
            if not path.name.endswith(".up.sql"):
                continue
            stem = path.name.removesuffix(".up.sql")
            version_text, _, name = stem.partition("_")
            down = root.joinpath(f"{stem}.down.sql")
            migrations.append(
                Migration(int(version_text), name, path.read_text(encoding="utf-8"), down.read_text(encoding="utf-8"))
            )
        return migrations

    def applied(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.connection.execute("SELECT version,name,applied_at FROM schema_migrations ORDER BY version")]

    def status(self) -> dict[str, Any]:
        applied = {item["version"] for item in self.applied()}
        available = self.available()
        return {
            "current": max(applied, default=0),
            "latest": max((item.version for item in available), default=0),
            "applied": sorted(applied),
            "pending": [item.version for item in available if item.version not in applied],
        }

    def migrate(self, target: int | None = None) -> list[int]:
        migrations = self.available()
        latest = max((item.version for item in migrations), default=0)
        target = latest if target is None else target
        if target < 0 or target > latest:
            raise WorkspaceError(f"invalid migration target: {target}")
        current = self.status()["current"]
        if target < current:
            self.rollback(current - target)
            return []
        applied: list[int] = []
        for migration in migrations:
            if migration.version <= current or migration.version > target:
                continue
            with self.connection:
                self.connection.executescript(migration.up_sql)
                self.connection.execute(
                    "INSERT INTO schema_migrations(version,name,applied_at) VALUES(?,?,?)",
                    (migration.version, migration.name, _utc_now()),
                )
            applied.append(migration.version)
        return applied

    def rollback(self, steps: int = 1) -> list[int]:
        if steps < 1:
            raise WorkspaceError("rollback steps must be at least one")
        migrations = {item.version: item for item in self.available()}
        applied = [item["version"] for item in self.applied()][-steps:]
        rolled_back: list[int] = []
        for version in reversed(applied):
            migration = migrations[version]
            with self.connection:
                self.connection.executescript(migration.down_sql)
                self.connection.execute("DELETE FROM schema_migrations WHERE version=?", (version,))
            rolled_back.append(version)
        return rolled_back


class SQLiteWorkspaceRepository:
    """Repository implementation for private Catalyst Grit workspaces."""

    def __init__(self, database: str | Path = ":memory:", *, auto_migrate: bool = True):
        self.database = str(database)
        self._allow_purge = False
        self.connection = sqlite3.connect(self.database)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.create_function("cg_allow_purge", 0, lambda: 1 if self._allow_purge else 0)
        self.migrations = MigrationManager(self.connection)
        if auto_migrate:
            self.migrations.migrate()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "SQLiteWorkspaceRepository":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            self.connection.execute("BEGIN")
            yield self.connection
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def _require_project(self, project_id: str, *, include_deleted: bool = False) -> dict[str, Any]:
        row = _row(self.connection.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone())
        if not row or (row["deleted_at"] and not include_deleted):
            raise WorkspaceError(f"project not found: {project_id}")
        return row

    def _require_record(self, record_id: str, *, include_deleted: bool = False) -> dict[str, Any]:
        row = _row(self.connection.execute("SELECT * FROM recovery_records WHERE record_id=?", (record_id,)).fetchone())
        if not row or (row["deleted_at"] and not include_deleted):
            raise WorkspaceError(f"record not found: {record_id}")
        return row

    def _audit(self, event_type: str, entity_type: str, entity_id: str, actor_id: str, payload: Mapping[str, Any] | None = None) -> str:
        event_id = _id("cge")
        self.connection.execute(
            "INSERT INTO audit_events(event_id,event_type,entity_type,entity_id,actor_id,payload_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (event_id, event_type, entity_type, entity_id, actor_id, _json(dict(payload or {})), _utc_now()),
        )
        return event_id

    def _history(self, entity_type: str, entity_id: str, before: str | None, after: str, actor_id: str, reason: str = "") -> str:
        history_id = _id("cgh")
        self.connection.execute(
            "INSERT INTO status_history(history_id,entity_type,entity_id,from_status,to_status,actor_id,reason,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (history_id, entity_type, entity_id, before, after, actor_id, reason, _utc_now()),
        )
        return history_id

    def create_project(
        self,
        title: str,
        *,
        description: str = "",
        owner_id: str = "self",
        retention_days: int | None = None,
        project_id: str | None = None,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        title = title.strip()
        if not title:
            raise WorkspaceError("project title is required")
        if retention_days is not None and retention_days < 1:
            raise WorkspaceError("retention_days must be at least one")
        project_id = project_id or _id("cgp")
        now = _utc_now()
        actor_id = actor_id or owner_id
        with self.connection:
            self.connection.execute(
                "INSERT INTO projects(project_id,title,description,status,visibility,owner_id,retention_days,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (project_id, title, description.strip(), "active", "private", owner_id, retention_days, now, now),
            )
            self.connection.execute(
                "INSERT INTO team_memberships(membership_id,project_id,member_key,display_name,role,status,access_scope,consent_status,joined_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (_id("cgm"), project_id, owner_id, owner_id, "owner", "active", "shared", "granted", now, now, now),
            )
            self._history("project", project_id, None, "active", actor_id, "project created")
            self._audit("project.created", "project", project_id, actor_id, {"visibility": "private"})
        return self.get_project(project_id)

    def get_project(self, project_id: str, *, include_deleted: bool = False) -> dict[str, Any]:
        return self._require_project(project_id, include_deleted=include_deleted)

    def list_projects(self, *, include_archived: bool = False, include_deleted: bool = False) -> list[dict[str, Any]]:
        clauses = []
        if not include_archived:
            clauses.append("archived_at IS NULL")
        if not include_deleted:
            clauses.append("deleted_at IS NULL")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        return [dict(row) for row in self.connection.execute("SELECT * FROM projects" + where + " ORDER BY updated_at DESC")]

    def archive_project(self, project_id: str, *, actor_id: str = "self", reason: str = "") -> dict[str, Any]:
        project = self._require_project(project_id)
        now = _utc_now()
        with self.connection:
            self.connection.execute("UPDATE projects SET status='archived',archived_at=?,updated_at=? WHERE project_id=?", (now, now, project_id))
            self._history("project", project_id, project["status"], "archived", actor_id, reason)
            self._audit("project.archived", "project", project_id, actor_id, {"reason": reason})
        return self.get_project(project_id)

    @staticmethod
    def _is_canonical(payload: Mapping[str, Any]) -> bool:
        return all(key in payload for key in ("metadata", "user_input", "normalized_input", "findings", "human_review", "extensions"))

    @staticmethod
    def _canonical_dict(payload: Mapping[str, Any] | RecoveryRecord) -> dict[str, Any]:
        if isinstance(payload, RecoveryRecord):
            return payload.to_dict()
        if not isinstance(payload, Mapping):
            raise WorkspaceError("record payload must be an object")
        if SQLiteWorkspaceRepository._is_canonical(payload):
            return deepcopy(dict(payload))
        return generate_record(payload).to_dict()

    @staticmethod
    def _request_snapshot(payload: Mapping[str, Any], canonical: Mapping[str, Any]) -> dict[str, Any]:
        if SQLiteWorkspaceRepository._is_canonical(payload):
            return {
                "metadata": canonical["metadata"],
                "input": canonical["user_input"],
                "human_review": canonical["human_review"],
                "extensions": canonical["extensions"],
            }
        return deepcopy(dict(payload))

    def save_record(
        self,
        project_id: str,
        payload: Mapping[str, Any] | RecoveryRecord,
        *,
        actor_id: str = "self",
        reason: str = "saved",
    ) -> dict[str, Any]:
        self._require_project(project_id)
        canonical = self._canonical_dict(payload)
        metadata = canonical.get("metadata") or {}
        record_id = str(metadata.get("record_id") or "")
        if not record_id:
            raise WorkspaceError("canonical record is missing metadata.record_id")
        schema_version = str(metadata.get("schema_version") or "")
        engine_version = str(metadata.get("engine_version") or "")
        created_at = str(metadata.get("created_at") or _utc_now())
        updated_at = str(metadata.get("updated_at") or created_at)
        status = str(metadata.get("status") or "draft")
        request = self._request_snapshot(payload if isinstance(payload, Mapping) else canonical, canonical)
        content_sha = _sha(canonical)
        existing = _row(self.connection.execute("SELECT * FROM recovery_records WHERE record_id=?", (record_id,)).fetchone())
        if existing and existing["project_id"] != project_id:
            raise WorkspaceError("record_id already belongs to another project")
        if existing and existing["deleted_at"]:
            raise WorkspaceError("deleted records cannot be revised")
        latest = None
        if existing:
            latest = _row(self.connection.execute("SELECT * FROM record_revisions WHERE revision_id=?", (existing["current_revision_id"],)).fetchone())
            if latest and latest["content_sha256"] == content_sha:
                return {"record": self.get_record(record_id), "revision": self.get_revision(latest["revision_id"]), "created": False, "deduplicated": True}
        revision_number = 1 if not existing else int(latest["revision_number"]) + 1
        revision_id = _id("cgv")
        retention_until = None
        project = self.get_project(project_id)
        if project["retention_days"]:
            retention_until = (datetime.now(timezone.utc) + timedelta(days=int(project["retention_days"]))).date().isoformat()
        with self.connection:
            if not existing:
                self.connection.execute(
                    "INSERT INTO recovery_records(record_id,project_id,current_revision_id,status,visibility,retention_until,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                    (record_id, project_id, None, status, "private", retention_until, created_at, updated_at),
                )
            self.connection.execute(
                "INSERT INTO record_revisions(revision_id,record_id,revision_number,canonical_json,request_json,content_sha256,schema_version,engine_version,created_at,created_by,reason) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (revision_id, record_id, revision_number, _json(canonical), _json(request), content_sha, schema_version, engine_version, _utc_now(), actor_id, reason),
            )
            archived_at = updated_at if status == "archived" else None
            self.connection.execute(
                "UPDATE recovery_records SET current_revision_id=?,status=?,updated_at=?,archived_at=? WHERE record_id=?",
                (revision_id, status, updated_at, archived_at, record_id),
            )
            normalized = canonical.get("normalized_input") or {}
            for section in ("response", "next_steps"):
                for ordinal, action in enumerate((normalized.get(section) or {}).get("actions") or []):
                    action_id = _id("cga")
                    created_at_action = _utc_now()
                    action_key = str(action.get("action_key") or f"{section}-{ordinal + 1}")
                    self.connection.execute(
                        """INSERT INTO actions(
                           action_id,record_id,revision_id,source_section,ordinal,title,status,owner,target_date,created_at,
                           action_key,horizon,expected_effect,required_support_json,dependencies_json,effort,urgency,
                           completion_evidence,reassessment_trigger,blocked_reason,escalation_path,completed_at,updated_at
                           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            action_id, record_id, revision_id, section, ordinal, str(action.get("title", "")),
                            str(action.get("status", "planned")), action.get("owner"), action.get("target_date"), created_at_action,
                            action_key, str(action.get("horizon", "7_days")), str(action.get("expected_effect", "")),
                            _json(action.get("required_support") or []), _json(action.get("dependencies") or []),
                            float(action.get("effort", 3)), float(action.get("urgency", 3)),
                            str(action.get("completion_evidence", "")), str(action.get("reassessment_trigger", "")),
                            str(action.get("blocked_reason", "")), str(action.get("escalation_path", "")),
                            created_at_action if action.get("status") == "completed" else None, created_at_action,
                        ),
                    )
                    self.connection.execute(
                        "INSERT INTO action_events(event_id,action_id,record_id,revision_id,from_status,to_status,actor_id,reason,blocked_reason,completion_evidence,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (_id("cgae"), action_id, record_id, revision_id, None, str(action.get("status", "planned")), actor_id, "action created from record revision", str(action.get("blocked_reason", "")), str(action.get("completion_evidence", "")), created_at_action),
                    )
            retrospective = (canonical.get("findings") or {}).get("retrospective") or {}
            if retrospective:
                self.connection.execute(
                    "INSERT OR IGNORE INTO retrospectives(retrospective_id,record_id,revision_id,content_json,uncertainties_json,created_by,created_at) VALUES(?,?,?,?,?,?,?)",
                    (_id("cgrt"), record_id, revision_id, _json(retrospective), _json(retrospective.get("uncertainties") or []), actor_id, _utc_now()),
                )
            previous_status = existing["status"] if existing else None
            if previous_status != status:
                self._history("record", record_id, previous_status, status, actor_id, reason)
            self._audit("record.created" if not existing else "record.revised", "record", record_id, actor_id, {"revision_id": revision_id, "revision_number": revision_number, "reason": reason})
        return {"record": self.get_record(record_id), "revision": self.get_revision(revision_id), "created": not existing, "deduplicated": False}

    def revise_record(self, record_id: str, request: Mapping[str, Any], *, actor_id: str = "self", reason: str = "reassessment") -> dict[str, Any]:
        record = self._require_record(record_id)
        current = self.get_record(record_id, include_canonical=True)["canonical"]
        request = migrate_v1_request(request) if "challenge" in request and "input" not in request else deepcopy(dict(request))
        metadata = dict(request.get("metadata") or {})
        metadata["record_id"] = record_id
        metadata["created_at"] = current["metadata"]["created_at"]
        metadata["updated_at"] = metadata.get("updated_at") or _utc_now()
        metadata.pop("engine_version", None)
        if metadata.get("schema_version") not in (None, SCHEMA_VERSION):
            metadata["provenance"] = dict(metadata.get("provenance") or {})
            metadata["provenance"].setdefault("source_schema_version", metadata["schema_version"])
            metadata.pop("schema_version", None)
        request["metadata"] = metadata
        return self.save_record(record["project_id"], request, actor_id=actor_id, reason=reason)

    def get_record(self, record_id: str, *, include_canonical: bool = False, include_deleted: bool = False) -> dict[str, Any]:
        record = self._require_record(record_id, include_deleted=include_deleted)
        result = dict(record)
        if record["current_revision_id"]:
            revision = self.get_revision(record["current_revision_id"])
            result["revision_number"] = revision["revision_number"]
            result["content_sha256"] = revision["content_sha256"]
            if include_canonical:
                result["canonical"] = revision["canonical"]
        return result

    def list_records(self, project_id: str, *, include_archived: bool = False, include_deleted: bool = False) -> list[dict[str, Any]]:
        self._require_project(project_id)
        clauses = ["project_id=?"]
        params: list[Any] = [project_id]
        if not include_archived:
            clauses.append("archived_at IS NULL")
        if not include_deleted:
            clauses.append("deleted_at IS NULL")
        rows = self.connection.execute("SELECT * FROM recovery_records WHERE " + " AND ".join(clauses) + " ORDER BY updated_at DESC", params)
        return [self.get_record(row["record_id"]) for row in rows]

    def get_revision(self, revision_id: str) -> dict[str, Any]:
        row = _row(self.connection.execute("SELECT * FROM record_revisions WHERE revision_id=?", (revision_id,)).fetchone())
        if not row:
            raise WorkspaceError(f"revision not found: {revision_id}")
        row["canonical"] = json.loads(row.pop("canonical_json"))
        row["request"] = json.loads(row.pop("request_json"))
        return row

    def list_revisions(self, record_id: str) -> list[dict[str, Any]]:
        self._require_record(record_id, include_deleted=True)
        ids = [row["revision_id"] for row in self.connection.execute("SELECT revision_id FROM record_revisions WHERE record_id=? ORDER BY revision_number", (record_id,))]
        return [self.get_revision(item) for item in ids]

    @staticmethod
    def _flatten(value: Any, prefix: str = "$") -> dict[str, Any]:
        output: dict[str, Any] = {}
        if isinstance(value, Mapping):
            for key in sorted(value):
                output.update(SQLiteWorkspaceRepository._flatten(value[key], f"{prefix}.{key}"))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                output.update(SQLiteWorkspaceRepository._flatten(item, f"{prefix}[{index}]"))
        else:
            output[prefix] = value
        return output

    def compare_revisions(self, record_id: str, from_revision: int, to_revision: int) -> dict[str, Any]:
        revisions = {item["revision_number"]: item for item in self.list_revisions(record_id)}
        if from_revision not in revisions or to_revision not in revisions:
            raise WorkspaceError("requested revision number was not found")
        before = self._flatten(revisions[from_revision]["canonical"])
        after = self._flatten(revisions[to_revision]["canonical"])
        changes = []
        for path in sorted(set(before) | set(after)):
            if before.get(path) != after.get(path):
                changes.append({"path": path, "before": before.get(path), "after": after.get(path)})
        return {"record_id": record_id, "from_revision": from_revision, "to_revision": to_revision, "changes": changes}

    def duplicate_record(self, record_id: str, *, project_id: str | None = None, actor_id: str = "self") -> dict[str, Any]:
        original = self.get_record(record_id, include_canonical=True)
        canonical = original["canonical"]
        request = {
            "metadata": {
                "status": "draft",
                "provenance": {"created_by": actor_id, "source": "import", "source_schema_version": canonical["metadata"]["schema_version"], "source_record_id": record_id, "notes": "Duplicated from an existing recovery record."},
            },
            "input": canonical["normalized_input"],
            "human_review": {"review_status": "not_reviewed", "reviewer": None, "reviewed_at": None, "notes": "", "accepted_findings": [], "rejected_findings": [], "override_state": None},
            "extensions": canonical.get("extensions") or {},
        }
        return self.save_record(project_id or original["project_id"], request, actor_id=actor_id, reason=f"duplicated from {record_id}")

    def archive_record(self, record_id: str, *, actor_id: str = "self", reason: str = "archived") -> dict[str, Any]:
        current = self.get_record(record_id, include_canonical=True)
        canonical = deepcopy(current["canonical"])
        canonical["metadata"]["status"] = "archived"
        canonical["metadata"]["updated_at"] = _utc_now()
        return self.save_record(current["project_id"], canonical, actor_id=actor_id, reason=reason)

    def delete_record(self, record_id: str, *, actor_id: str = "self", reason: str = "deleted") -> dict[str, Any]:
        record = self._require_record(record_id)
        now = _utc_now()
        with self.connection:
            self.connection.execute("UPDATE recovery_records SET status='deleted',deleted_at=?,updated_at=? WHERE record_id=?", (now, now, record_id))
            self._history("record", record_id, record["status"], "deleted", actor_id, reason)
            self._audit("record.deleted", "record", record_id, actor_id, {"reason": reason, "mode": "soft-delete"})
        return self.get_record(record_id, include_deleted=True)

    def set_retention(self, record_id: str, *, retention_until: str | None = None, retention_days: int | None = None, actor_id: str = "self") -> dict[str, Any]:
        self._require_record(record_id)
        if retention_days is not None:
            if retention_days < 1:
                raise WorkspaceError("retention_days must be at least one")
            retention_until = (datetime.now(timezone.utc) + timedelta(days=retention_days)).date().isoformat()
        if retention_until is not None:
            date.fromisoformat(retention_until)
        with self.connection:
            self.connection.execute("UPDATE recovery_records SET retention_until=?,updated_at=? WHERE record_id=?", (retention_until, _utc_now(), record_id))
            self._audit("record.retention_updated", "record", record_id, actor_id, {"retention_until": retention_until})
        return self.get_record(record_id)

    def purge_record(self, record_id: str, *, confirm: bool = False, actor_id: str = "self") -> dict[str, Any]:
        if not confirm:
            raise WorkspaceError("permanent purge requires confirm=True")
        record = self._require_record(record_id, include_deleted=True)
        tombstone = {"record_id": record_id, "project_id": record["project_id"], "purged_at": _utc_now()}
        try:
            self._allow_purge = True
            with self.connection:
                self.connection.execute("DELETE FROM recovery_records WHERE record_id=?", (record_id,))
                self._audit("record.purged", "record_tombstone", record_id, actor_id, tombstone)
        finally:
            self._allow_purge = False
        return tombstone

    def purge_due_records(self, *, as_of: str | None = None, actor_id: str = "system") -> list[str]:
        as_of = as_of or date.today().isoformat()
        date.fromisoformat(as_of)
        ids = [row["record_id"] for row in self.connection.execute("SELECT record_id FROM recovery_records WHERE retention_until IS NOT NULL AND retention_until<=?", (as_of,))]
        for record_id in ids:
            self.purge_record(record_id, confirm=True, actor_id=actor_id)
        return ids

    def create_checkpoint(
        self,
        project_id: str,
        title: str,
        *,
        record_id: str | None = None,
        scheduled_for: str | None = None,
        notes: str = "",
        actor_id: str = "self",
        checkpoint_id: str | None = None,
    ) -> dict[str, Any]:
        self._require_project(project_id)
        revision_id = None
        if record_id:
            record = self._require_record(record_id)
            if record["project_id"] != project_id:
                raise WorkspaceError("checkpoint record must belong to the project")
            revision_id = record["current_revision_id"]
        if scheduled_for:
            date.fromisoformat(scheduled_for)
        checkpoint_id = checkpoint_id or _id("cgc")
        with self.connection:
            self.connection.execute(
                "INSERT INTO checkpoints(checkpoint_id,project_id,record_id,revision_id,title,scheduled_for,status,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (checkpoint_id, project_id, record_id, revision_id, title.strip() or "Review checkpoint", scheduled_for, "planned", notes.strip(), _utc_now()),
            )
            self._history("checkpoint", checkpoint_id, None, "planned", actor_id, "checkpoint created")
            self._audit("checkpoint.created", "checkpoint", checkpoint_id, actor_id, {"record_id": record_id, "scheduled_for": scheduled_for})
        return self.get_checkpoint(checkpoint_id)

    def get_checkpoint(self, checkpoint_id: str) -> dict[str, Any]:
        row = _row(self.connection.execute("SELECT * FROM checkpoints WHERE checkpoint_id=?", (checkpoint_id,)).fetchone())
        if not row:
            raise WorkspaceError(f"checkpoint not found: {checkpoint_id}")
        return row

    def list_checkpoints(self, project_id: str, *, record_id: str | None = None) -> list[dict[str, Any]]:
        self._require_project(project_id)
        if record_id:
            rows = self.connection.execute("SELECT * FROM checkpoints WHERE project_id=? AND record_id=? ORDER BY scheduled_for,created_at", (project_id, record_id))
        else:
            rows = self.connection.execute("SELECT * FROM checkpoints WHERE project_id=? ORDER BY scheduled_for,created_at", (project_id,))
        return [dict(row) for row in rows]

    def complete_checkpoint(self, checkpoint_id: str, *, notes: str | None = None, actor_id: str = "self") -> dict[str, Any]:
        checkpoint = self.get_checkpoint(checkpoint_id)
        with self.connection:
            self.connection.execute("UPDATE checkpoints SET status='completed',completed_at=?,notes=? WHERE checkpoint_id=?", (_utc_now(), checkpoint["notes"] if notes is None else notes.strip(), checkpoint_id))
            self._history("checkpoint", checkpoint_id, checkpoint["status"], "completed", actor_id, "checkpoint completed")
            self._audit("checkpoint.completed", "checkpoint", checkpoint_id, actor_id)
        return self.get_checkpoint(checkpoint_id)

    def add_review(self, record_id: str, *, status: str, reviewer_id: str, notes: str = "", completed_at: str | None = None) -> dict[str, Any]:
        record = self._require_record(record_id)
        review_id = _id("cgrv")
        with self.connection:
            self.connection.execute(
                "INSERT INTO reviews(review_id,record_id,revision_id,status,reviewer_id,notes,created_at,completed_at) VALUES(?,?,?,?,?,?,?,?)",
                (review_id, record_id, record["current_revision_id"], status, reviewer_id, notes.strip(), _utc_now(), completed_at),
            )
            self._audit("review.recorded", "review", review_id, reviewer_id, {"record_id": record_id, "status": status})
        return dict(self.connection.execute("SELECT * FROM reviews WHERE review_id=?", (review_id,)).fetchone())

    def list_reviews(self, record_id: str) -> list[dict[str, Any]]:
        self._require_record(record_id, include_deleted=True)
        return [dict(row) for row in self.connection.execute("SELECT * FROM reviews WHERE record_id=? ORDER BY created_at", (record_id,))]

    @staticmethod
    def _decode_action(row: Mapping[str, Any]) -> dict[str, Any]:
        item = dict(row)
        item["required_support"] = json.loads(item.pop("required_support_json", "[]") or "[]")
        item["dependencies"] = json.loads(item.pop("dependencies_json", "[]") or "[]")
        return item

    @staticmethod
    def _action_attention(item: Mapping[str, Any], *, as_of: str | None = None) -> dict[str, Any]:
        status = str(item.get("status") or "planned")
        if status == "blocked":
            return {"attention_state": "blocked_needs_support", "days_past_target": 0, "message": "This action is blocked; review support, sequencing, or escalation without assigning blame."}
        if status in {"completed", "cancelled"}:
            return {"attention_state": "closed", "days_past_target": 0, "message": "No timing review is required."}
        target_date = item.get("target_date")
        if target_date:
            today = date.fromisoformat(as_of) if as_of else date.today()
            target = date.fromisoformat(str(target_date))
            if target < today:
                days = (today - target).days
                return {"attention_state": "target_date_passed", "days_past_target": days, "message": "The target date passed; review capacity, support, scope, or sequencing."}
        return {"attention_state": "on_track", "days_past_target": 0, "message": "No immediate timing or blocker signal."}

    def get_action(self, action_id: str, *, as_of: str | None = None) -> dict[str, Any]:
        row = _row(self.connection.execute("SELECT * FROM actions WHERE action_id=?", (action_id,)).fetchone())
        if not row:
            raise WorkspaceError(f"action not found: {action_id}")
        item = self._decode_action(row)
        item.update(self._action_attention(item, as_of=as_of))
        return item

    def list_actions(self, record_id: str, *, revision_number: int | None = None, as_of: str | None = None) -> list[dict[str, Any]]:
        record = self._require_record(record_id, include_deleted=True)
        revision_id = record["current_revision_id"]
        if revision_number is not None:
            row = self.connection.execute("SELECT revision_id FROM record_revisions WHERE record_id=? AND revision_number=?", (record_id, revision_number)).fetchone()
            if not row:
                raise WorkspaceError("revision not found")
            revision_id = row["revision_id"]
        result = []
        for row in self.connection.execute("SELECT * FROM actions WHERE revision_id=? ORDER BY source_section,ordinal", (revision_id,)):
            item = self._decode_action(row)
            item.update(self._action_attention(item, as_of=as_of))
            result.append(item)
        return result

    def update_action(
        self,
        action_id: str,
        *,
        status: str,
        actor_id: str = "self",
        reason: str = "status updated",
        blocked_reason: str | None = None,
        completion_evidence: str | None = None,
        escalation_path: str | None = None,
    ) -> dict[str, Any]:
        allowed = {"planned", "in_progress", "blocked", "completed", "paused", "deferred", "cancelled"}
        if status not in allowed:
            raise WorkspaceError("unsupported action status")
        current = self.get_action(action_id)
        blocked_reason = current["blocked_reason"] if blocked_reason is None else blocked_reason.strip()
        completion_evidence = current["completion_evidence"] if completion_evidence is None else completion_evidence.strip()
        escalation_path = current["escalation_path"] if escalation_path is None else escalation_path.strip()
        if status == "blocked" and not blocked_reason:
            raise WorkspaceError("blocked actions require a support-oriented blocked reason")
        if status == "completed" and not completion_evidence:
            raise WorkspaceError("completed actions require completion evidence")
        now = _utc_now()
        completed_at = now if status == "completed" else None
        with self.connection:
            self.connection.execute(
                "UPDATE actions SET status=?,blocked_reason=?,completion_evidence=?,escalation_path=?,completed_at=?,updated_at=? WHERE action_id=?",
                (status, blocked_reason, completion_evidence, escalation_path, completed_at, now, action_id),
            )
            self.connection.execute(
                "INSERT INTO action_events(event_id,action_id,record_id,revision_id,from_status,to_status,actor_id,reason,blocked_reason,completion_evidence,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (_id("cgae"), action_id, current["record_id"], current["revision_id"], current["status"], status, actor_id, reason, blocked_reason, completion_evidence, now),
            )
            self._history("action", action_id, current["status"], status, actor_id, reason)
            self._audit("action.status_changed", "action", action_id, actor_id, {"record_id": current["record_id"], "from_status": current["status"], "to_status": status, "reason": reason})
        return self.get_action(action_id)

    def action_history(self, action_id: str) -> list[dict[str, Any]]:
        self.get_action(action_id)
        return [dict(row) for row in self.connection.execute("SELECT * FROM action_events WHERE action_id=? ORDER BY created_at,rowid", (action_id,))]

    def add_blocker(
        self,
        record_id: str,
        title: str,
        *,
        action_id: str | None = None,
        owner: str | None = None,
        required_support: str = "",
        escalation_path: str = "",
        notes: str = "",
        actor_id: str = "self",
    ) -> dict[str, Any]:
        self._require_record(record_id)
        if action_id and self.get_action(action_id)["record_id"] != record_id:
            raise WorkspaceError("blocker action must belong to the record")
        blocker_id = _id("cgb")
        now = _utc_now()
        with self.connection:
            self.connection.execute(
                "INSERT INTO blockers(blocker_id,record_id,action_id,title,status,owner,required_support,escalation_path,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (blocker_id, record_id, action_id, title.strip() or "Unspecified blocker", "open", owner, required_support.strip(), escalation_path.strip(), notes.strip(), now, now),
            )
            self._audit("blocker.created", "blocker", blocker_id, actor_id, {"record_id": record_id, "action_id": action_id})
        return self.get_blocker(blocker_id)

    def get_blocker(self, blocker_id: str) -> dict[str, Any]:
        row = _row(self.connection.execute("SELECT * FROM blockers WHERE blocker_id=?", (blocker_id,)).fetchone())
        if not row:
            raise WorkspaceError(f"blocker not found: {blocker_id}")
        return row

    def list_blockers(self, record_id: str, *, include_resolved: bool = True) -> list[dict[str, Any]]:
        self._require_record(record_id, include_deleted=True)
        query = "SELECT * FROM blockers WHERE record_id=?"
        params: list[Any] = [record_id]
        if not include_resolved:
            query += " AND status!='resolved'"
        query += " ORDER BY created_at,rowid"
        return [dict(row) for row in self.connection.execute(query, params)]

    def update_blocker(self, blocker_id: str, *, status: str, actor_id: str = "self", notes: str | None = None, escalation_path: str | None = None) -> dict[str, Any]:
        if status not in {"open", "resolved", "escalated"}:
            raise WorkspaceError("unsupported blocker status")
        current = self.get_blocker(blocker_id)
        now = _utc_now()
        with self.connection:
            self.connection.execute(
                "UPDATE blockers SET status=?,notes=?,escalation_path=?,updated_at=?,resolved_at=? WHERE blocker_id=?",
                (status, current["notes"] if notes is None else notes.strip(), current["escalation_path"] if escalation_path is None else escalation_path.strip(), now, now if status == "resolved" else None, blocker_id),
            )
            self._history("blocker", blocker_id, current["status"], status, actor_id, "blocker reviewed")
            self._audit("blocker.status_changed", "blocker", blocker_id, actor_id, {"record_id": current["record_id"], "from_status": current["status"], "to_status": status})
        return self.get_blocker(blocker_id)

    @staticmethod
    def _plan_comparison(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
        before_plan = (before.get("findings") or {}).get("recovery_plan") or {}
        after_plan = (after.get("findings") or {}).get("recovery_plan") or {}
        before_actions = {item["action_key"]: item for horizon in (before_plan.get("horizons") or {}).values() for item in horizon}
        after_actions = {item["action_key"]: item for horizon in (after_plan.get("horizons") or {}).values() for item in horizon}
        return {
            "checkpoint_before": (before_plan.get("checkpoint") or {}).get("scheduled_for"),
            "checkpoint_after": (after_plan.get("checkpoint") or {}).get("scheduled_for"),
            "added_actions": sorted(set(after_actions) - set(before_actions)),
            "removed_actions": sorted(set(before_actions) - set(after_actions)),
            "status_changes": [
                {"action_key": key, "before": before_actions[key]["status"], "after": after_actions[key]["status"]}
                for key in sorted(set(before_actions) & set(after_actions))
                if before_actions[key]["status"] != after_actions[key]["status"]
            ],
            "score_before": (before.get("findings") or {}).get("recovery_score"),
            "score_after": (after.get("findings") or {}).get("recovery_score"),
        }

    def create_reassessment(
        self,
        record_id: str,
        request: Mapping[str, Any],
        *,
        observed_summary: str,
        checkpoint_id: str | None = None,
        changed_assumptions: Sequence[str] | None = None,
        carry_unresolved: bool = True,
        actor_id: str = "self",
    ) -> dict[str, Any]:
        record = self.get_record(record_id, include_canonical=True)
        before = record["canonical"]
        before_revision_id = record["current_revision_id"]
        request_value = deepcopy(dict(request))
        if carry_unresolved:
            input_value = dict(request_value.get("input") or {})
            next_steps = dict(input_value.get("next_steps") or {})
            current_actions = [item for item in before["normalized_input"]["next_steps"]["actions"] if item["status"] not in {"completed", "cancelled"}]
            supplied = list(next_steps.get("actions") or [])
            supplied_keys = {str(item.get("action_key")) for item in supplied if isinstance(item, Mapping)}
            carried = [deepcopy(item) for item in current_actions if item["action_key"] not in supplied_keys]
            next_steps["actions"] = supplied + carried
            next_steps.setdefault("changed_assumptions", list(changed_assumptions or []))
            input_value["next_steps"] = next_steps
            request_value["input"] = input_value
        saved = self.revise_record(record_id, request_value, actor_id=actor_id, reason="checkpoint reassessment")
        after = self.get_record(record_id, include_canonical=True)["canonical"]
        comparison = self._plan_comparison(before, after)
        carried_keys = [item["action_key"] for item in after["normalized_input"]["next_steps"]["actions"] if item["action_key"] in {x["action_key"] for x in before["normalized_input"]["next_steps"]["actions"]}]
        reassessment_id = _id("cgra")
        with self.connection:
            self.connection.execute(
                "INSERT INTO reassessments(reassessment_id,record_id,checkpoint_id,from_revision_id,to_revision_id,observed_summary,changed_assumptions_json,planned_vs_observed_json,carried_actions_json,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (reassessment_id, record_id, checkpoint_id, before_revision_id, saved["revision"]["revision_id"], observed_summary.strip(), _json(list(changed_assumptions or [])), _json(comparison), _json(carried_keys), actor_id, _utc_now()),
            )
            self._audit("record.reassessed", "record", record_id, actor_id, {"reassessment_id": reassessment_id, "checkpoint_id": checkpoint_id, "from_revision_id": before_revision_id, "to_revision_id": saved["revision"]["revision_id"]})
        if checkpoint_id:
            self.complete_checkpoint(checkpoint_id, notes=observed_summary, actor_id=actor_id)
        return self.get_reassessment(reassessment_id)

    def get_reassessment(self, reassessment_id: str) -> dict[str, Any]:
        row = _row(self.connection.execute("SELECT * FROM reassessments WHERE reassessment_id=?", (reassessment_id,)).fetchone())
        if not row:
            raise WorkspaceError(f"reassessment not found: {reassessment_id}")
        row["changed_assumptions"] = json.loads(row.pop("changed_assumptions_json"))
        row["planned_vs_observed"] = json.loads(row.pop("planned_vs_observed_json"))
        row["carried_actions"] = json.loads(row.pop("carried_actions_json"))
        return row

    def list_reassessments(self, record_id: str) -> list[dict[str, Any]]:
        self._require_record(record_id, include_deleted=True)
        ids = [row["reassessment_id"] for row in self.connection.execute("SELECT reassessment_id FROM reassessments WHERE record_id=? ORDER BY created_at,rowid", (record_id,))]
        return [self.get_reassessment(item) for item in ids]

    def list_retrospectives(self, record_id: str) -> list[dict[str, Any]]:
        self._require_record(record_id, include_deleted=True)
        output = []
        for row in self.connection.execute("SELECT * FROM retrospectives WHERE record_id=? ORDER BY created_at,rowid", (record_id,)):
            item = dict(row)
            item["content"] = json.loads(item.pop("content_json"))
            item["uncertainties"] = json.loads(item.pop("uncertainties_json"))
            output.append(item)
        return output

    @staticmethod
    def _merge_pattern(group: dict[str, Any], item: Mapping[str, Any], record_id: str, revision_id: str) -> None:
        group["occurrence_count"] += 1
        group["record_ids"].append(record_id)
        for evidence in item.get("evidence") or []:
            group["evidence"].append({"record_id": record_id, "revision_id": revision_id, **deepcopy(dict(evidence))})
        candidate = str(item.get("adaptation_candidate") or "")
        if candidate and candidate not in group["adaptation_candidates"]:
            group["adaptation_candidates"].append(candidate)

    def detect_project_patterns(self, project_id: str, *, minimum_occurrences: int = 2, include_singletons: bool = False) -> list[dict[str, Any]]:
        self._require_project(project_id, include_deleted=True)
        if minimum_occurrences < 1:
            raise WorkspaceError("minimum_occurrences must be at least one")
        grouped: dict[str, dict[str, Any]] = {}
        records = self.list_records(project_id, include_archived=True, include_deleted=False)
        for record in records:
            current = self.get_record(record["record_id"], include_canonical=True)["canonical"]
            revision_id = record["current_revision_id"]
            for item in (current.get("findings") or {}).get("adaptation_patterns") or []:
                key = str(item.get("pattern_key") or "")
                if not key or item.get("status") == "rejected":
                    continue
                if key not in grouped:
                    grouped[key] = {
                        "pattern_key": key,
                        "category": item.get("category"),
                        "label": item.get("label"),
                        "status": "inferred",
                        "occurrence_count": 0,
                        "record_ids": [],
                        "evidence": [],
                        "adaptation_candidates": [],
                        "review": None,
                        "explanation": "Occurrences are counted from current record revisions and retain record, revision, path, and value evidence.",
                    }
                self._merge_pattern(grouped[key], item, record["record_id"], revision_id)
        reviews: dict[str, dict[str, Any]] = {}
        for row in self.connection.execute("SELECT * FROM pattern_reviews WHERE project_id=? ORDER BY created_at,rowid", (project_id,)):
            item = dict(row); item["evidence"] = json.loads(item.pop("evidence_json")); reviews[item["pattern_key"]] = item
        output = []
        for key in sorted(grouped):
            item = grouped[key]
            item["record_ids"] = sorted(set(item["record_ids"]))
            review = reviews.get(key)
            if review:
                item["review"] = review
                item["status"] = {"accept": "accepted", "reject": "rejected", "correct": "corrected"}[review["decision"]]
                if review["decision"] == "correct":
                    item["label"] = review["corrected_label"]
            if include_singletons or item["occurrence_count"] >= minimum_occurrences or review:
                output.append(item)
        return output

    def review_pattern(
        self,
        project_id: str,
        pattern_key: str,
        *,
        decision: str,
        corrected_label: str = "",
        notes: str = "",
        actor_id: str = "self",
    ) -> dict[str, Any]:
        self._require_project(project_id)
        if decision not in {"accept", "reject", "correct"}:
            raise WorkspaceError("unsupported pattern review decision")
        if decision == "correct" and not corrected_label.strip():
            raise WorkspaceError("corrected_label is required when correcting a pattern")
        patterns = {item["pattern_key"]: item for item in self.detect_project_patterns(project_id, minimum_occurrences=1, include_singletons=True)}
        if pattern_key not in patterns:
            raise WorkspaceError(f"pattern not found: {pattern_key}")
        review_id = _id("cgpr")
        now = _utc_now()
        with self.connection:
            self.connection.execute(
                "INSERT INTO pattern_reviews(pattern_review_id,project_id,pattern_key,decision,corrected_label,notes,evidence_json,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (review_id, project_id, pattern_key, decision, corrected_label.strip(), notes.strip(), _json(patterns[pattern_key]["evidence"]), actor_id, now),
            )
            self._audit("pattern.reviewed", "pattern", pattern_key, actor_id, {"project_id": project_id, "decision": decision})
        row = dict(self.connection.execute("SELECT * FROM pattern_reviews WHERE pattern_review_id=?", (review_id,)).fetchone())
        row["evidence"] = json.loads(row.pop("evidence_json"))
        return row

    def list_pattern_reviews(self, project_id: str) -> list[dict[str, Any]]:
        self._require_project(project_id, include_deleted=True)
        output = []
        for row in self.connection.execute("SELECT * FROM pattern_reviews WHERE project_id=? ORDER BY created_at,rowid", (project_id,)):
            item = dict(row); item["evidence"] = json.loads(item.pop("evidence_json")); output.append(item)
        return output

    def create_system_change(
        self,
        project_id: str,
        title: str,
        proposed_change: str,
        *,
        owner: str | None = None,
        source_record_ids: Sequence[str] | None = None,
        evidence_note: str = "",
        expected_benefit: str = "",
        pilot_start: str | None = None,
        pilot_end: str | None = None,
        decision: str = "proposed",
        actor_id: str = "self",
    ) -> dict[str, Any]:
        self._require_project(project_id)
        if decision not in {"proposed", "piloting", "adopt", "revise", "defer", "retire"}:
            raise WorkspaceError("unsupported system change decision")
        if not title.strip() or not proposed_change.strip():
            raise WorkspaceError("title and proposed_change are required")
        sources = list(dict.fromkeys(source_record_ids or []))
        if not sources:
            raise WorkspaceError("at least one source record is required")
        for record_id in sources:
            record = self._require_record(record_id)
            if record["project_id"] != project_id:
                raise WorkspaceError("system-change source record belongs to another project")
        change_id = _id("cgsc")
        now = _utc_now()
        with self.connection:
            self.connection.execute(
                "INSERT INTO system_changes(system_change_id,project_id,title,proposed_change,owner,expected_benefit,pilot_start,pilot_end,review_result,decision,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (change_id, project_id, title.strip(), proposed_change.strip(), owner, expected_benefit.strip(), pilot_start, pilot_end, "", decision, now, now),
            )
            for record_id in sources:
                self.connection.execute("INSERT INTO system_change_sources(system_change_id,record_id,evidence_note) VALUES(?,?,?)", (change_id, record_id, evidence_note.strip()))
            self.connection.execute(
                "INSERT INTO system_change_events(event_id,system_change_id,from_decision,to_decision,review_result,actor_id,reason,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (_id("cgsce"), change_id, None, decision, "", actor_id, "system change created", now),
            )
            self._audit("system_change.created", "system_change", change_id, actor_id, {"project_id": project_id, "source_record_ids": sources})
        return self.get_system_change(change_id)

    def get_system_change(self, system_change_id: str) -> dict[str, Any]:
        row = _row(self.connection.execute("SELECT * FROM system_changes WHERE system_change_id=?", (system_change_id,)).fetchone())
        if not row:
            raise WorkspaceError(f"system change not found: {system_change_id}")
        row["sources"] = [dict(item) for item in self.connection.execute("SELECT * FROM system_change_sources WHERE system_change_id=? ORDER BY record_id", (system_change_id,))]
        row["events"] = [dict(item) for item in self.connection.execute("SELECT * FROM system_change_events WHERE system_change_id=? ORDER BY created_at,rowid", (system_change_id,))]
        return row

    def list_system_changes(self, project_id: str) -> list[dict[str, Any]]:
        self._require_project(project_id, include_deleted=True)
        ids = [row["system_change_id"] for row in self.connection.execute("SELECT system_change_id FROM system_changes WHERE project_id=? ORDER BY created_at,rowid", (project_id,))]
        return [self.get_system_change(item) for item in ids]

    def update_system_change(
        self,
        system_change_id: str,
        *,
        decision: str,
        review_result: str = "",
        reason: str = "reviewed",
        owner: str | None = None,
        pilot_start: str | None = None,
        pilot_end: str | None = None,
        actor_id: str = "self",
    ) -> dict[str, Any]:
        if decision not in {"proposed", "piloting", "adopt", "revise", "defer", "retire"}:
            raise WorkspaceError("unsupported system change decision")
        current = self.get_system_change(system_change_id)
        now = _utc_now()
        with self.connection:
            self.connection.execute(
                "UPDATE system_changes SET decision=?,review_result=?,owner=?,pilot_start=?,pilot_end=?,updated_at=? WHERE system_change_id=?",
                (decision, review_result.strip(), current["owner"] if owner is None else owner, current["pilot_start"] if pilot_start is None else pilot_start, current["pilot_end"] if pilot_end is None else pilot_end, now, system_change_id),
            )
            self.connection.execute(
                "INSERT INTO system_change_events(event_id,system_change_id,from_decision,to_decision,review_result,actor_id,reason,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (_id("cgsce"), system_change_id, current["decision"], decision, review_result.strip(), actor_id, reason.strip(), now),
            )
            self._history("system_change", system_change_id, current["decision"], decision, actor_id, reason)
            self._audit("system_change.reviewed", "system_change", system_change_id, actor_id, {"from_decision": current["decision"], "to_decision": decision})
        return self.get_system_change(system_change_id)

    # --- v1.6 team recovery and facilitated review -------------------------

    def _membership(self, project_id: str, member_key: str, *, include_removed: bool = False) -> dict[str, Any]:
        row = _row(self.connection.execute(
            "SELECT * FROM team_memberships WHERE project_id=? AND member_key=?",
            (project_id, member_key),
        ).fetchone())
        if not row or (row["status"] == "removed" and not include_removed):
            raise WorkspaceError(f"active team membership not found: {member_key}")
        return row

    def _require_team_role(self, project_id: str, actor_id: str, roles: set[str]) -> dict[str, Any]:
        member = self._membership(project_id, actor_id)
        if member["role"] not in roles or member["status"] != "active":
            raise WorkspaceError("actor is not authorized for this team operation")
        return member

    def add_team_member(
        self,
        project_id: str,
        member_key: str,
        display_name: str,
        *,
        role: str = "contributor",
        status: str = "invited",
        access_scope: str = "shared",
        consent_status: str = "pending",
        actor_id: str = "self",
    ) -> dict[str, Any]:
        self._require_project(project_id)
        self._require_team_role(project_id, actor_id, {"owner", "facilitator"})
        if role not in {"owner", "facilitator", "contributor", "reviewer", "observer"}:
            raise WorkspaceError("unsupported team role")
        if role == "owner" and self._membership(project_id, actor_id)["role"] != "owner":
            raise WorkspaceError("only an owner can grant owner access")
        if status not in {"invited", "active", "removed"}:
            raise WorkspaceError("unsupported membership status")
        if access_scope not in {"shared", "facilitation_only"}:
            raise WorkspaceError("unsupported access scope")
        if consent_status not in {"pending", "granted", "withdrawn"}:
            raise WorkspaceError("unsupported consent status")
        member_key = member_key.strip(); display_name = display_name.strip()
        if not member_key or not display_name:
            raise WorkspaceError("member_key and display_name are required")
        membership_id = _id("cgm")
        now = _utc_now()
        joined_at = now if status == "active" else None
        with self.connection:
            self.connection.execute(
                "INSERT INTO team_memberships(membership_id,project_id,member_key,display_name,role,status,access_scope,consent_status,joined_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (membership_id, project_id, member_key, display_name, role, status, access_scope, consent_status, joined_at, now, now),
            )
            self._audit("team.member_added", "membership", membership_id, actor_id, {"project_id": project_id, "role": role, "status": status})
        return self.get_team_member(membership_id)

    def get_team_member(self, membership_id: str) -> dict[str, Any]:
        row = _row(self.connection.execute("SELECT * FROM team_memberships WHERE membership_id=?", (membership_id,)).fetchone())
        if not row:
            raise WorkspaceError(f"team membership not found: {membership_id}")
        return row

    def list_team_members(self, project_id: str, *, include_removed: bool = False) -> list[dict[str, Any]]:
        self._require_project(project_id, include_deleted=True)
        sql = "SELECT * FROM team_memberships WHERE project_id=?"
        params: list[Any] = [project_id]
        if not include_removed:
            sql += " AND status<>'removed'"
        sql += " ORDER BY CASE role WHEN 'owner' THEN 0 WHEN 'facilitator' THEN 1 WHEN 'reviewer' THEN 2 WHEN 'contributor' THEN 3 ELSE 4 END, display_name"
        return [dict(row) for row in self.connection.execute(sql, params)]

    def update_team_member(
        self,
        membership_id: str,
        *,
        role: str | None = None,
        status: str | None = None,
        access_scope: str | None = None,
        consent_status: str | None = None,
        actor_id: str = "self",
    ) -> dict[str, Any]:
        current = self.get_team_member(membership_id)
        actor = self._require_team_role(current["project_id"], actor_id, {"owner", "facilitator"})
        next_role = current["role"] if role is None else role
        next_status = current["status"] if status is None else status
        next_scope = current["access_scope"] if access_scope is None else access_scope
        next_consent = current["consent_status"] if consent_status is None else consent_status
        if next_role not in {"owner", "facilitator", "contributor", "reviewer", "observer"}:
            raise WorkspaceError("unsupported team role")
        if (current["role"] == "owner" or next_role == "owner") and actor["role"] != "owner":
            raise WorkspaceError("only an owner can change owner access")
        if next_status not in {"invited", "active", "removed"}:
            raise WorkspaceError("unsupported membership status")
        if next_scope not in {"shared", "facilitation_only"}:
            raise WorkspaceError("unsupported access scope")
        if next_consent not in {"pending", "granted", "withdrawn"}:
            raise WorkspaceError("unsupported consent status")
        now = _utc_now()
        joined_at = current["joined_at"] or (now if next_status == "active" else None)
        with self.connection:
            self.connection.execute(
                "UPDATE team_memberships SET role=?,status=?,access_scope=?,consent_status=?,joined_at=?,updated_at=? WHERE membership_id=?",
                (next_role, next_status, next_scope, next_consent, joined_at, now, membership_id),
            )
            self._audit("team.member_updated", "membership", membership_id, actor_id, {"role": next_role, "status": next_status, "consent_status": next_consent})
        return self.get_team_member(membership_id)

    def create_facilitated_session(
        self,
        project_id: str,
        title: str,
        *,
        purpose: str = "",
        facilitator_key: str = "self",
        record_id: str | None = None,
        scheduled_for: str | None = None,
        ground_rules: Sequence[str] | None = None,
        agenda: Sequence[str] | None = None,
        notes: str = "",
        actor_id: str = "self",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        self._require_project(project_id)
        self._require_team_role(project_id, actor_id, {"owner", "facilitator"})
        facilitator = self._membership(project_id, facilitator_key)
        if facilitator["role"] not in {"owner", "facilitator"}:
            raise WorkspaceError("session facilitator must have owner or facilitator role")
        if facilitator["consent_status"] == "withdrawn":
            raise WorkspaceError("session facilitator has withdrawn consent")
        if record_id:
            record = self._require_record(record_id)
            if record["project_id"] != project_id:
                raise WorkspaceError("session record belongs to another project")
        title = title.strip()
        if not title:
            raise WorkspaceError("session title is required")
        session_id = session_id or _id("cgfs")
        now = _utc_now()
        rules = list(ground_rules or [
            "Discuss recorded conditions, not individual character.",
            "No ranking, diagnosis, or hidden performance evaluation.",
            "Participants control the sharing scope of their contributions.",
            "Separate observation, interpretation, and decision.",
        ])
        steps = list(agenda or ["prepare", "share perspectives", "map conditions", "agree actions", "close and review consent"])
        with self.connection:
            self.connection.execute(
                "INSERT INTO facilitated_sessions(session_id,project_id,record_id,title,purpose,status,facilitator_key,scheduled_for,started_at,completed_at,ground_rules_json,agenda_json,notes,created_at,updated_at) VALUES(?,?,?,?,?,'planned',?,?,NULL,NULL,?,?,?,?,?)",
                (session_id, project_id, record_id, title, purpose.strip(), facilitator_key, scheduled_for, _json(rules), _json(steps), notes.strip(), now, now),
            )
            self._audit("facilitated_session.created", "facilitated_session", session_id, actor_id, {"project_id": project_id, "record_id": record_id})
        return self.get_facilitated_session(session_id, actor_id=actor_id)

    def _session_row(self, session_id: str) -> dict[str, Any]:
        row = _row(self.connection.execute("SELECT * FROM facilitated_sessions WHERE session_id=?", (session_id,)).fetchone())
        if not row:
            raise WorkspaceError(f"facilitated session not found: {session_id}")
        row["ground_rules"] = json.loads(row.pop("ground_rules_json"))
        row["agenda"] = json.loads(row.pop("agenda_json"))
        return row

    def add_session_participant(
        self,
        session_id: str,
        member_key: str,
        *,
        participation_status: str = "invited",
        consent_status: str = "pending",
        sharing_scope: str = "shared",
        actor_id: str = "self",
    ) -> dict[str, Any]:
        session = self._session_row(session_id)
        self._require_team_role(session["project_id"], actor_id, {"owner", "facilitator"})
        member = self._membership(session["project_id"], member_key)
        if participation_status not in {"invited", "confirmed", "declined", "attended", "absent"}:
            raise WorkspaceError("unsupported participation status")
        if consent_status not in {"pending", "granted", "withdrawn"}:
            raise WorkspaceError("unsupported consent status")
        if sharing_scope not in {"shared", "facilitator_only", "private"}:
            raise WorkspaceError("unsupported sharing scope")
        now = _utc_now()
        with self.connection:
            self.connection.execute(
                "INSERT INTO session_participants(session_id,membership_id,participation_status,consent_status,sharing_scope,created_at,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(session_id,membership_id) DO UPDATE SET participation_status=excluded.participation_status,consent_status=excluded.consent_status,sharing_scope=excluded.sharing_scope,updated_at=excluded.updated_at",
                (session_id, member["membership_id"], participation_status, consent_status, sharing_scope, now, now),
            )
            self._audit("facilitated_session.participant_updated", "facilitated_session", session_id, actor_id, {"member_key": member_key, "participation_status": participation_status, "consent_status": consent_status})
        return dict(self.connection.execute(
            "SELECT sp.*,tm.member_key,tm.display_name,tm.role FROM session_participants sp JOIN team_memberships tm USING(membership_id) WHERE sp.session_id=? AND sp.membership_id=?",
            (session_id, member["membership_id"]),
        ).fetchone())

    def add_team_perspective(
        self,
        project_id: str,
        content: str,
        *,
        perspective_type: str = "other",
        member_key: str | None = None,
        contributor_label: str = "",
        session_id: str | None = None,
        record_id: str | None = None,
        sharing_scope: str = "shared",
        consent_status: str = "granted",
        source_path: str = "",
        actor_id: str = "self",
    ) -> dict[str, Any]:
        self._require_project(project_id)
        actor = self._membership(project_id, actor_id)
        if perspective_type not in {"impact", "pressure", "constraint", "support", "capacity", "response", "learning", "other"}:
            raise WorkspaceError("unsupported perspective type")
        if sharing_scope not in {"shared", "facilitator_only", "private"}:
            raise WorkspaceError("unsupported sharing scope")
        if consent_status not in {"pending", "granted", "withdrawn"}:
            raise WorkspaceError("unsupported consent status")
        content = content.strip()
        if not content:
            raise WorkspaceError("perspective content is required")
        member = self._membership(project_id, member_key or actor_id)
        if member["member_key"] != actor_id and actor["role"] not in {"owner", "facilitator"}:
            raise WorkspaceError("contributors may only submit their own perspective")
        if session_id:
            session = self._session_row(session_id)
            if session["project_id"] != project_id:
                raise WorkspaceError("session belongs to another project")
        if record_id:
            record = self._require_record(record_id)
            if record["project_id"] != project_id:
                raise WorkspaceError("record belongs to another project")
        perspective_id = _id("cgtp")
        now = _utc_now()
        label = contributor_label.strip() or member["display_name"]
        with self.connection:
            self.connection.execute(
                "INSERT INTO team_perspectives(perspective_id,project_id,session_id,record_id,membership_id,contributor_label,perspective_type,content,sharing_scope,consent_status,source_path,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (perspective_id, project_id, session_id, record_id, member["membership_id"], label, perspective_type, content, sharing_scope, consent_status, source_path.strip(), now),
            )
            self._audit("team.perspective_added", "team_perspective", perspective_id, actor_id, {"project_id": project_id, "session_id": session_id, "sharing_scope": sharing_scope, "consent_status": consent_status})
        return dict(self.connection.execute("SELECT * FROM team_perspectives WHERE perspective_id=?", (perspective_id,)).fetchone())

    def list_team_perspectives(
        self,
        project_id: str,
        *,
        session_id: str | None = None,
        record_id: str | None = None,
        actor_id: str = "self",
        include_withdrawn: bool = False,
    ) -> list[dict[str, Any]]:
        viewer = self._membership(project_id, actor_id)
        sql = "SELECT tp.*,tm.member_key,tm.display_name FROM team_perspectives tp LEFT JOIN team_memberships tm USING(membership_id) WHERE tp.project_id=?"
        params: list[Any] = [project_id]
        if session_id:
            sql += " AND tp.session_id=?"; params.append(session_id)
        if record_id:
            sql += " AND tp.record_id=?"; params.append(record_id)
        if not include_withdrawn:
            sql += " AND tp.consent_status='granted'"
        sql += " ORDER BY tp.created_at,tp.rowid"
        output = []
        for row in self.connection.execute(sql, params):
            item = dict(row)
            own = item.get("member_key") == actor_id
            manager = viewer["role"] in {"owner", "facilitator"}
            visible = item["sharing_scope"] == "shared" or own or (manager and item["sharing_scope"] == "facilitator_only")
            if visible:
                output.append(item)
        return output

    def create_facilitated_agreement(
        self,
        session_id: str,
        title: str,
        *,
        owner_key: str | None = None,
        due_date: str | None = None,
        status: str = "proposed",
        support_needed: str = "",
        actor_id: str = "self",
    ) -> dict[str, Any]:
        session = self._session_row(session_id)
        self._require_team_role(session["project_id"], actor_id, {"owner", "facilitator"})
        if status not in {"proposed", "accepted", "in_progress", "completed", "blocked", "retired"}:
            raise WorkspaceError("unsupported agreement status")
        if owner_key:
            self._membership(session["project_id"], owner_key)
        title = title.strip()
        if not title:
            raise WorkspaceError("agreement title is required")
        agreement_id = _id("cgfa")
        now = _utc_now()
        with self.connection:
            self.connection.execute(
                "INSERT INTO facilitated_agreements(agreement_id,session_id,title,owner_key,due_date,status,completion_evidence,support_needed,created_at,updated_at) VALUES(?,?,?,?,?,?, '',?,?,?)",
                (agreement_id, session_id, title, owner_key, due_date, status, support_needed.strip(), now, now),
            )
            self.connection.execute(
                "INSERT INTO facilitated_agreement_events(event_id,agreement_id,from_status,to_status,actor_id,reason,evidence,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (_id("cgfae"), agreement_id, None, status, actor_id, "agreement created", "", now),
            )
            self._audit("facilitated_agreement.created", "facilitated_agreement", agreement_id, actor_id, {"session_id": session_id, "owner_key": owner_key})
        return self.get_facilitated_agreement(agreement_id)

    def get_facilitated_agreement(self, agreement_id: str) -> dict[str, Any]:
        row = _row(self.connection.execute("SELECT * FROM facilitated_agreements WHERE agreement_id=?", (agreement_id,)).fetchone())
        if not row:
            raise WorkspaceError(f"facilitated agreement not found: {agreement_id}")
        row["events"] = [dict(item) for item in self.connection.execute("SELECT * FROM facilitated_agreement_events WHERE agreement_id=? ORDER BY created_at,rowid", (agreement_id,))]
        return row

    def update_facilitated_agreement(
        self,
        agreement_id: str,
        *,
        status: str,
        reason: str = "agreement reviewed",
        completion_evidence: str = "",
        support_needed: str | None = None,
        actor_id: str = "self",
    ) -> dict[str, Any]:
        current = self.get_facilitated_agreement(agreement_id)
        session = self._session_row(current["session_id"])
        self._require_team_role(session["project_id"], actor_id, {"owner", "facilitator", "reviewer"})
        if status not in {"proposed", "accepted", "in_progress", "completed", "blocked", "retired"}:
            raise WorkspaceError("unsupported agreement status")
        if status == "completed" and not completion_evidence.strip():
            raise WorkspaceError("completion evidence is required for a completed agreement")
        next_support = current["support_needed"] if support_needed is None else support_needed.strip()
        if status == "blocked" and not next_support:
            raise WorkspaceError("support_needed is required for a blocked agreement")
        now = _utc_now()
        evidence = completion_evidence.strip()
        with self.connection:
            self.connection.execute(
                "UPDATE facilitated_agreements SET status=?,completion_evidence=?,support_needed=?,updated_at=? WHERE agreement_id=?",
                (status, evidence, next_support, now, agreement_id),
            )
            self.connection.execute(
                "INSERT INTO facilitated_agreement_events(event_id,agreement_id,from_status,to_status,actor_id,reason,evidence,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (_id("cgfae"), agreement_id, current["status"], status, actor_id, reason.strip(), evidence, now),
            )
            self._history("facilitated_agreement", agreement_id, current["status"], status, actor_id, reason)
            self._audit("facilitated_agreement.updated", "facilitated_agreement", agreement_id, actor_id, {"from_status": current["status"], "to_status": status})
        return self.get_facilitated_agreement(agreement_id)

    def list_facilitated_agreements(self, session_id: str) -> list[dict[str, Any]]:
        self._session_row(session_id)
        ids = [row["agreement_id"] for row in self.connection.execute("SELECT agreement_id FROM facilitated_agreements WHERE session_id=? ORDER BY created_at,rowid", (session_id,))]
        return [self.get_facilitated_agreement(item) for item in ids]

    def update_facilitated_session(
        self,
        session_id: str,
        *,
        status: str,
        notes: str | None = None,
        actor_id: str = "self",
    ) -> dict[str, Any]:
        current = self._session_row(session_id)
        self._require_team_role(current["project_id"], actor_id, {"owner", "facilitator"})
        if status not in {"planned", "in_progress", "completed", "cancelled"}:
            raise WorkspaceError("unsupported facilitated-session status")
        now = _utc_now()
        started_at = current["started_at"] or (now if status == "in_progress" else None)
        completed_at = current["completed_at"] or (now if status == "completed" else None)
        with self.connection:
            self.connection.execute(
                "UPDATE facilitated_sessions SET status=?,started_at=?,completed_at=?,notes=?,updated_at=? WHERE session_id=?",
                (status, started_at, completed_at, current["notes"] if notes is None else notes.strip(), now, session_id),
            )
            self._history("facilitated_session", session_id, current["status"], status, actor_id, "session status updated")
            self._audit("facilitated_session.updated", "facilitated_session", session_id, actor_id, {"from_status": current["status"], "to_status": status})
        return self.get_facilitated_session(session_id, actor_id=actor_id)

    def get_facilitated_session(self, session_id: str, *, actor_id: str = "self") -> dict[str, Any]:
        session = self._session_row(session_id)
        self._membership(session["project_id"], actor_id)
        session["participants"] = [dict(row) for row in self.connection.execute(
            "SELECT sp.*,tm.member_key,tm.display_name,tm.role FROM session_participants sp JOIN team_memberships tm USING(membership_id) WHERE sp.session_id=? ORDER BY tm.display_name",
            (session_id,),
        )]
        session["perspectives"] = self.list_team_perspectives(session["project_id"], session_id=session_id, actor_id=actor_id)
        session["agreements"] = self.list_facilitated_agreements(session_id)
        session["facilitation_boundary"] = {
            "individual_scoring_prohibited": True,
            "ranking_prohibited": True,
            "diagnosis_prohibited": True,
            "hidden_evaluation_prohibited": True,
            "consent_required_for_shared_perspectives": True,
        }
        return session

    def list_facilitated_sessions(self, project_id: str, *, actor_id: str = "self") -> list[dict[str, Any]]:
        self._membership(project_id, actor_id)
        ids = [row["session_id"] for row in self.connection.execute("SELECT session_id FROM facilitated_sessions WHERE project_id=? ORDER BY COALESCE(scheduled_for,created_at),rowid", (project_id,))]
        return [self.get_facilitated_session(item, actor_id=actor_id) for item in ids]

    def team_recovery_summary(self, project_id: str, *, actor_id: str = "self") -> dict[str, Any]:
        members = self.list_team_members(project_id)
        sessions = self.list_facilitated_sessions(project_id, actor_id=actor_id)
        perspectives = self.list_team_perspectives(project_id, actor_id=actor_id)
        agreements = [agreement for session in sessions for agreement in session["agreements"]]
        by_type: dict[str, int] = {}
        for item in perspectives:
            by_type[item["perspective_type"]] = by_type.get(item["perspective_type"], 0) + 1
        by_status: dict[str, int] = {}
        for item in agreements:
            by_status[item["status"]] = by_status.get(item["status"], 0) + 1
        return {
            "project_id": project_id,
            "member_count": len([item for item in members if item["status"] == "active"]),
            "session_count": len(sessions),
            "perspective_count": len(perspectives),
            "agreement_count": len(agreements),
            "perspectives_by_type": by_type,
            "agreements_by_status": by_status,
            "review_required": any(item["status"] == "blocked" for item in agreements),
            "interpretation_limit": "Team summaries describe shared work conditions and agreements. They do not score, rank, diagnose, or compare individual participants.",
        }

    @staticmethod
    def _decode_evidence(row: Mapping[str, Any]) -> dict[str, Any]:
        item = dict(row)
        item["provenance"] = json.loads(item.pop("provenance_json"))
        return item

    def add_evidence(
        self,
        project_id: str,
        title: str,
        *,
        evidence_type: str = "note",
        content: str = "",
        record_id: str | None = None,
        revision_id: str | None = None,
        source_uri: str = "",
        source_artifact_id: str = "",
        source_product: str = "",
        source_version: str = "",
        provenance: Sequence[Mapping[str, Any] | str] | None = None,
        strength: str = "unknown",
        review_state: str = "unreviewed",
        observed_at: str | None = None,
        actor_id: str = "self",
        evidence_id: str | None = None,
    ) -> dict[str, Any]:
        self._require_project(project_id)
        allowed_types = {"note", "source_link", "file_reference", "quote", "observation", "dataset", "calculation", "analysis", "experiment_result", "method", "reference_document"}
        if evidence_type not in allowed_types:
            raise WorkspaceError("unsupported evidence type")
        if strength not in {"unknown", "weak", "moderate", "strong"}:
            raise WorkspaceError("unsupported evidence strength")
        if review_state not in {"unreviewed", "accepted", "questioned", "rejected"}:
            raise WorkspaceError("unsupported evidence review state")
        if not title.strip():
            raise WorkspaceError("evidence title is required")
        if evidence_type in {"source_link", "file_reference", "dataset", "reference_document"} and not (source_uri.strip() or source_artifact_id.strip()):
            raise WorkspaceError("a source URI or artifact ID is required for referenced evidence")
        if record_id:
            record = self._require_record(record_id)
            if record["project_id"] != project_id:
                raise WorkspaceError("evidence record belongs to another project")
        if revision_id:
            revision = self.get_revision(revision_id)
            if record_id and revision["record_id"] != record_id:
                raise WorkspaceError("evidence revision does not belong to the selected record")
        evidence_id = evidence_id or _id("cge")
        now = _utc_now()
        immutable = {
            "title": title.strip(), "content": content.strip(), "source_uri": source_uri.strip(),
            "source_artifact_id": source_artifact_id.strip(), "source_product": source_product.strip(),
            "source_version": source_version.strip(), "provenance": list(provenance or []),
        }
        content_hash = _sha(immutable)
        with self.connection:
            self.connection.execute(
                "INSERT INTO evidence_items(evidence_id,project_id,record_id,revision_id,evidence_type,title,content,source_uri,source_artifact_id,source_product,source_version,provenance_json,strength,review_state,observed_at,added_by,content_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (evidence_id, project_id, record_id, revision_id, evidence_type, title.strip(), content.strip(), source_uri.strip(), source_artifact_id.strip(), source_product.strip(), source_version.strip(), _json(list(provenance or [])), strength, review_state, observed_at, actor_id, content_hash, now, now),
            )
            self.connection.execute(
                "INSERT INTO evidence_events(event_id,evidence_id,event_type,from_state,to_state,actor_id,notes,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (_id("cgee"), evidence_id, "created", None, review_state, actor_id, "evidence recorded", _json({"strength": strength, "content_hash": content_hash}), now),
            )
            self._audit("evidence.created", "evidence", evidence_id, actor_id, {"project_id": project_id, "record_id": record_id, "evidence_type": evidence_type})
        return self.get_evidence(evidence_id)

    def get_evidence(self, evidence_id: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM evidence_items WHERE evidence_id=?", (evidence_id,)).fetchone()
        if not row:
            raise WorkspaceError(f"evidence not found: {evidence_id}")
        item = self._decode_evidence(row)
        item["events"] = []
        for event in self.connection.execute("SELECT * FROM evidence_events WHERE evidence_id=? ORDER BY created_at,rowid", (evidence_id,)):
            decoded = dict(event); decoded["payload"] = json.loads(decoded.pop("payload_json")); item["events"].append(decoded)
        item["links"] = [dict(link) for link in self.connection.execute("SELECT * FROM evidence_links WHERE evidence_id=? ORDER BY created_at,rowid", (evidence_id,))]
        return item

    def list_evidence(self, project_id: str, *, record_id: str | None = None, evidence_type: str | None = None, review_state: str | None = None) -> list[dict[str, Any]]:
        self._require_project(project_id)
        clauses = ["project_id=?"]; params: list[Any] = [project_id]
        if record_id is not None: clauses.append("record_id=?"); params.append(record_id)
        if evidence_type is not None: clauses.append("evidence_type=?"); params.append(evidence_type)
        if review_state is not None: clauses.append("review_state=?"); params.append(review_state)
        ids = [row["evidence_id"] for row in self.connection.execute("SELECT evidence_id FROM evidence_items WHERE " + " AND ".join(clauses) + " ORDER BY created_at,rowid", params)]
        return [self.get_evidence(item) for item in ids]

    def review_evidence(self, evidence_id: str, *, review_state: str, strength: str | None = None, notes: str = "", actor_id: str = "self") -> dict[str, Any]:
        if review_state not in {"unreviewed", "accepted", "questioned", "rejected"}:
            raise WorkspaceError("unsupported evidence review state")
        current = self.get_evidence(evidence_id)
        next_strength = current["strength"] if strength is None else strength
        if next_strength not in {"unknown", "weak", "moderate", "strong"}:
            raise WorkspaceError("unsupported evidence strength")
        now = _utc_now()
        with self.connection:
            self.connection.execute("UPDATE evidence_items SET review_state=?,strength=?,updated_at=? WHERE evidence_id=?", (review_state, next_strength, now, evidence_id))
            self.connection.execute(
                "INSERT INTO evidence_events(event_id,evidence_id,event_type,from_state,to_state,actor_id,notes,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (_id("cgee"), evidence_id, "reviewed", current["review_state"], review_state, actor_id, notes.strip(), _json({"from_strength": current["strength"], "to_strength": next_strength}), now),
            )
            self._history("evidence", evidence_id, current["review_state"], review_state, actor_id, notes or "evidence reviewed")
            self._audit("evidence.reviewed", "evidence", evidence_id, actor_id, {"from_state": current["review_state"], "to_state": review_state, "strength": next_strength})
        return self.get_evidence(evidence_id)

    def link_evidence(self, evidence_id: str, target_type: str, target_id: str, *, relation: str = "supports", notes: str = "", actor_id: str = "self") -> dict[str, Any]:
        self.get_evidence(evidence_id)
        if target_type not in {"record", "revision", "assumption", "action", "checkpoint", "system_change", "agreement", "handoff"}:
            raise WorkspaceError("unsupported evidence link target")
        if relation not in {"supports", "challenges", "context", "derived_from", "conflicts_with"}:
            raise WorkspaceError("unsupported evidence relation")
        validators = {
            "record": lambda: self._require_record(target_id),
            "revision": lambda: self.get_revision(target_id),
            "assumption": lambda: self.get_assumption(target_id),
            "action": lambda: self.get_action(target_id),
            "checkpoint": lambda: self.get_checkpoint(target_id),
            "system_change": lambda: self.get_system_change(target_id),
            "agreement": lambda: self.get_facilitated_agreement(target_id),
            "handoff": lambda: self.get_handoff(target_id),
        }
        validators[target_type]()
        link_id = _id("cgel")
        with self.connection:
            try:
                self.connection.execute("INSERT INTO evidence_links(link_id,evidence_id,target_type,target_id,relation,notes,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?)", (link_id, evidence_id, target_type, target_id, relation, notes.strip(), actor_id, _utc_now()))
            except sqlite3.IntegrityError as exc:
                raise WorkspaceError("this evidence link already exists") from exc
            self._audit("evidence.linked", "evidence", evidence_id, actor_id, {"target_type": target_type, "target_id": target_id, "relation": relation})
        return dict(self.connection.execute("SELECT * FROM evidence_links WHERE link_id=?", (link_id,)).fetchone())

    def evidence_ledger(self, project_id: str, *, record_id: str | None = None) -> dict[str, Any]:
        items = self.list_evidence(project_id, record_id=record_id)
        by_type: dict[str, int] = {}; by_state: dict[str, int] = {}; by_strength: dict[str, int] = {}
        for item in items:
            by_type[item["evidence_type"]] = by_type.get(item["evidence_type"], 0) + 1
            by_state[item["review_state"]] = by_state.get(item["review_state"], 0) + 1
            by_strength[item["strength"]] = by_strength.get(item["strength"], 0) + 1
        conflicts = [item for item in items if item["review_state"] == "questioned" or any(link["relation"] == "conflicts_with" for link in item["links"])]
        return {"project_id": project_id, "record_id": record_id, "evidence_count": len(items), "by_type": by_type, "by_review_state": by_state, "by_strength": by_strength, "conflict_count": len(conflicts), "items": items}

    def add_assumption(self, project_id: str, statement: str, *, record_id: str | None = None, uncertainty: str = "", confidence: int = 50, owner: str | None = None, review_due: str | None = None, source_paths: Sequence[str] | None = None, actor_id: str = "self", assumption_id: str | None = None) -> dict[str, Any]:
        self._require_project(project_id)
        if not statement.strip(): raise WorkspaceError("assumption statement is required")
        if confidence < 0 or confidence > 100: raise WorkspaceError("confidence must be between 0 and 100")
        if record_id:
            record = self._require_record(record_id)
            if record["project_id"] != project_id: raise WorkspaceError("assumption record belongs to another project")
        assumption_id = assumption_id or _id("cga")
        now = _utc_now()
        with self.connection:
            self.connection.execute("INSERT INTO assumptions(assumption_id,project_id,record_id,statement,status,uncertainty,confidence,owner,review_due,source_paths_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (assumption_id, project_id, record_id, statement.strip(), "active", uncertainty.strip(), confidence, owner, review_due, _json(list(source_paths or [])), now, now))
            self.connection.execute("INSERT INTO assumption_events(event_id,assumption_id,from_status,to_status,confidence,actor_id,reason,created_at) VALUES(?,?,?,?,?,?,?,?)", (_id("cgae"), assumption_id, None, "active", confidence, actor_id, "assumption recorded", now))
            self._audit("assumption.created", "assumption", assumption_id, actor_id, {"project_id": project_id, "record_id": record_id})
        return self.get_assumption(assumption_id)

    def get_assumption(self, assumption_id: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM assumptions WHERE assumption_id=?", (assumption_id,)).fetchone()
        if not row: raise WorkspaceError(f"assumption not found: {assumption_id}")
        item = dict(row); item["source_paths"] = json.loads(item.pop("source_paths_json")); item["events"] = [dict(event) for event in self.connection.execute("SELECT * FROM assumption_events WHERE assumption_id=? ORDER BY created_at,rowid", (assumption_id,))]
        item["evidence_links"] = [dict(link) for link in self.connection.execute("SELECT * FROM evidence_links WHERE target_type='assumption' AND target_id=? ORDER BY created_at,rowid", (assumption_id,))]
        return item

    def list_assumptions(self, project_id: str, *, record_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        self._require_project(project_id); clauses=["project_id=?"]; params: list[Any]=[project_id]
        if record_id is not None: clauses.append("record_id=?"); params.append(record_id)
        if status is not None: clauses.append("status=?"); params.append(status)
        ids=[row["assumption_id"] for row in self.connection.execute("SELECT assumption_id FROM assumptions WHERE " + " AND ".join(clauses) + " ORDER BY created_at,rowid", params)]
        return [self.get_assumption(item) for item in ids]

    def update_assumption(self, assumption_id: str, *, status: str, confidence: int | None = None, uncertainty: str | None = None, owner: str | None = None, review_due: str | None = None, reason: str = "assumption reviewed", actor_id: str = "self") -> dict[str, Any]:
        if status not in {"active", "validated", "rejected", "retired"}: raise WorkspaceError("unsupported assumption status")
        current=self.get_assumption(assumption_id); next_confidence=current["confidence"] if confidence is None else confidence
        if next_confidence < 0 or next_confidence > 100: raise WorkspaceError("confidence must be between 0 and 100")
        now=_utc_now()
        with self.connection:
            self.connection.execute("UPDATE assumptions SET status=?,confidence=?,uncertainty=?,owner=?,review_due=?,updated_at=? WHERE assumption_id=?", (status,next_confidence,current["uncertainty"] if uncertainty is None else uncertainty.strip(),current["owner"] if owner is None else owner,current["review_due"] if review_due is None else review_due,now,assumption_id))
            self.connection.execute("INSERT INTO assumption_events(event_id,assumption_id,from_status,to_status,confidence,actor_id,reason,created_at) VALUES(?,?,?,?,?,?,?,?)", (_id("cgae"),assumption_id,current["status"],status,next_confidence,actor_id,reason.strip(),now))
            self._history("assumption", assumption_id, current["status"], status, actor_id, reason)
            self._audit("assumption.updated", "assumption", assumption_id, actor_id, {"from_status": current["status"], "to_status": status, "confidence": next_confidence})
        return self.get_assumption(assumption_id)

    def assumption_matrix(self, project_id: str, *, record_id: str | None = None) -> dict[str, Any]:
        items=self.list_assumptions(project_id, record_id=record_id)
        for item in items:
            item["review_attention"] = bool(item["status"] == "active" and (item["confidence"] < 50 or item["review_due"]))
        return {"project_id": project_id,"record_id": record_id,"assumption_count": len(items),"active_count": sum(item["status"]=="active" for item in items),"review_attention_count": sum(bool(item["review_attention"]) for item in items),"items": items}

    @staticmethod
    def _decode_handoff(row: Mapping[str, Any]) -> dict[str, Any]:
        item=dict(row); item["payload"]=json.loads(item.pop("payload_json")); item["provenance"]=json.loads(item.pop("provenance_json")); return item

    def create_handoff(self, project_id: str, *, source_product: str, source_version: str, target_product: str, artifact_type: str, artifact_id: str, payload: Mapping[str, Any] | None = None, record_id: str | None = None, direction: str = "inbound", reference_mode: str = "snapshot", source_uri: str = "", provenance: Sequence[Mapping[str, Any] | str] | None = None, stale_after: str | None = None, actor_id: str = "self", handoff_id: str | None = None) -> dict[str, Any]:
        self._require_project(project_id)
        known={"Catalyst Canvas","Catalyst Data","Workbench","Sustainable Catalyst Lab","Decision Studio","Knowledge Library","Research Librarian","Catalyst Grit","External"}
        if source_product not in known or target_product not in known: raise WorkspaceError("unsupported handoff product")
        if direction not in {"inbound","outbound"}: raise WorkspaceError("unsupported handoff direction")
        if reference_mode not in {"snapshot","live_reference"}: raise WorkspaceError("unsupported reference mode")
        if not source_version.strip() or not artifact_type.strip() or not artifact_id.strip(): raise WorkspaceError("source version, artifact type, and artifact ID are required")
        if reference_mode == "live_reference" and not source_uri.strip(): raise WorkspaceError("live references require a source URI")
        if record_id:
            record=self._require_record(record_id)
            if record["project_id"] != project_id: raise WorkspaceError("handoff record belongs to another project")
        payload_dict=dict(payload or {}); content_hash=_sha(payload_dict); handoff_id=handoff_id or _id("cgh"); now=_utc_now()
        with self.connection:
            try:
                self.connection.execute("INSERT INTO handoff_artifacts(handoff_id,project_id,record_id,direction,source_product,source_version,target_product,artifact_type,artifact_id,reference_mode,source_uri,payload_json,provenance_json,content_hash,validation_state,stale_after,last_checked_at,conflict_notes,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (handoff_id,project_id,record_id,direction,source_product,source_version,target_product,artifact_type.strip(),artifact_id.strip(),reference_mode,source_uri.strip(),_json(payload_dict),_json(list(provenance or [])),content_hash,"valid",stale_after,now,"",actor_id,now,now))
            except sqlite3.IntegrityError as exc:
                raise WorkspaceError("an identical handoff artifact already exists") from exc
            self.connection.execute("INSERT INTO handoff_events(event_id,handoff_id,event_type,from_state,to_state,actor_id,notes,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (_id("cghe"),handoff_id,"created",None,"valid",actor_id,"handoff created",_json({"content_hash":content_hash}),now))
            self._audit("handoff.created", "handoff", handoff_id, actor_id, {"source_product":source_product,"target_product":target_product,"artifact_id":artifact_id})
        return self.get_handoff(handoff_id)

    def get_handoff(self, handoff_id: str) -> dict[str, Any]:
        row=self.connection.execute("SELECT * FROM handoff_artifacts WHERE handoff_id=?",(handoff_id,)).fetchone()
        if not row: raise WorkspaceError(f"handoff not found: {handoff_id}")
        item=self._decode_handoff(row); item["events"]=[]
        for event in self.connection.execute("SELECT * FROM handoff_events WHERE handoff_id=? ORDER BY created_at,rowid",(handoff_id,)):
            decoded=dict(event); decoded["payload"]=json.loads(decoded.pop("payload_json")); item["events"].append(decoded)
        item["evidence_links"]=[dict(link) for link in self.connection.execute("SELECT * FROM evidence_links WHERE target_type='handoff' AND target_id=? ORDER BY created_at,rowid",(handoff_id,))]
        return item

    def list_handoffs(self, project_id: str, *, record_id: str | None = None, target_product: str | None = None, validation_state: str | None = None) -> list[dict[str, Any]]:
        self._require_project(project_id); clauses=["project_id=?"]; params: list[Any]=[project_id]
        if record_id is not None: clauses.append("record_id=?"); params.append(record_id)
        if target_product is not None: clauses.append("target_product=?"); params.append(target_product)
        if validation_state is not None: clauses.append("validation_state=?"); params.append(validation_state)
        ids=[row["handoff_id"] for row in self.connection.execute("SELECT handoff_id FROM handoff_artifacts WHERE "+" AND ".join(clauses)+" ORDER BY created_at,rowid",params)]
        return [self.get_handoff(item) for item in ids]

    def validate_handoff(self, handoff_id: str, *, payload: Mapping[str, Any] | None = None, state: str | None = None, conflict_notes: str = "", actor_id: str = "self") -> dict[str, Any]:
        current=self.get_handoff(handoff_id); next_state=state
        if next_state is None:
            if payload is not None and _sha(dict(payload)) != current["content_hash"]: next_state="conflict"
            elif current["stale_after"] and current["stale_after"] < _utc_now(): next_state="stale"
            else: next_state="valid"
        if next_state not in {"valid","invalid","stale","conflict"}: raise WorkspaceError("unsupported handoff validation state")
        now=_utc_now(); event_type={"valid":"validated","invalid":"validated","stale":"marked_stale","conflict":"conflict_recorded"}[next_state]
        with self.connection:
            self.connection.execute("UPDATE handoff_artifacts SET validation_state=?,last_checked_at=?,conflict_notes=?,updated_at=? WHERE handoff_id=?",(next_state,now,conflict_notes.strip(),now,handoff_id))
            self.connection.execute("INSERT INTO handoff_events(event_id,handoff_id,event_type,from_state,to_state,actor_id,notes,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(_id("cghe"),handoff_id,event_type,current["validation_state"],next_state,actor_id,conflict_notes.strip(),_json({"supplied_content_hash":_sha(dict(payload)) if payload is not None else None}),now))
            self._history("handoff",handoff_id,current["validation_state"],next_state,actor_id,conflict_notes or "handoff validated")
            self._audit("handoff.validated","handoff",handoff_id,actor_id,{"from_state":current["validation_state"],"to_state":next_state})
        return self.get_handoff(handoff_id)

    def build_decision_handoff(self, record_id: str, *, actor_id: str = "self") -> dict[str, Any]:
        record=self.get_record(record_id,include_canonical=True); project_id=record["project_id"]; canonical=record["canonical"]
        evidence=self.list_evidence(project_id,record_id=record_id); assumptions=self.list_assumptions(project_id,record_id=record_id); actions=self.list_actions(record_id); reviews=self.list_reviews(record_id)
        packet={
            "contract":"sustainable-catalyst-decision-handoff/1.0",
            "source":{"product":"Catalyst Grit","version":__version__,"record_id":record_id,"revision_id":record["current_revision_id"]},
            "target":{"product":"Decision Studio","artifact_type":"decision_packet_context"},
            "provenance":{"generated_at":_utc_now(),"canonical_hash":_sha(canonical),"evidence_ids":[item["evidence_id"] for item in evidence],"assumption_ids":[item["assumption_id"] for item in assumptions]},
            "recovery_context":{"title":canonical["user_input"]["context"]["title"],"trigger":canonical["user_input"]["trigger"],"condition_map":canonical["findings"]["condition_map"],"interpretation":canonical["findings"]["interpretation"]},
            "options_and_actions":canonical["findings"].get("recovery_plan",{}),
            "actions":actions,
            "evidence":[{key:item[key] for key in ("evidence_id","evidence_type","title","content","source_uri","source_product","source_version","strength","review_state","content_hash")} for item in evidence],
            "assumptions":[{key:item[key] for key in ("assumption_id","statement","status","uncertainty","confidence","owner","review_due")} for item in assumptions],
            "human_review":canonical.get("human_review",{}),
            "review_history":reviews,
            "decision_guardrails":["Preserve evidence provenance.","Keep unresolved assumptions explicit.","Do not convert recovery conditions into individual scores, rankings, diagnoses, or eligibility decisions."],
        }
        packet["content_hash"]=_sha(packet)
        handoff=self.create_handoff(project_id,source_product="Catalyst Grit",source_version=__version__,target_product="Decision Studio",artifact_type="decision_packet_context",artifact_id=f"{record_id}:{record['current_revision_id']}",payload=packet,record_id=record_id,direction="outbound",reference_mode="snapshot",provenance=[{"record_id":record_id,"revision_id":record["current_revision_id"]}],actor_id=actor_id)
        packet["handoff_id"]=handoff["handoff_id"]
        return packet

    # --- v1.8 longitudinal monitoring and resilience signals ---------------

    @staticmethod
    def _decode_monitoring_snapshot(row: Mapping[str, Any]) -> dict[str, Any]:
        item = dict(row)
        for source, target in (
            ("component_scores_json", "component_scores"),
            ("condition_metrics_json", "condition_metrics"),
            ("action_counts_json", "action_counts"),
            ("blocker_counts_json", "blocker_counts"),
            ("checkpoint_counts_json", "checkpoint_counts"),
            ("pattern_keys_json", "pattern_keys"),
            ("system_change_counts_json", "system_change_counts"),
            ("source_trace_json", "source_trace"),
        ):
            item[target] = json.loads(item.pop(source))
        return item

    @staticmethod
    def monitoring_governance(*, minimum_points: int = 2, privacy_threshold: int = 3) -> dict[str, Any]:
        return {
            "minimum_points": max(2, int(minimum_points)),
            "aggregation_privacy_threshold": max(3, int(privacy_threshold)),
            "predictive_claims_allowed": False,
            "individual_ranking_allowed": False,
            "hidden_scoring_allowed": False,
            "institutional_interpretation_requires_human_review": True,
            "historical_calculation_policy": "Use the recorded engine, schema, methodology, source revision, and exact stored values; do not silently recalculate history.",
            "interpretation": "Signals describe recorded recovery conditions and workflow outcomes, not character, diagnosis, employability, or future performance.",
        }

    @staticmethod
    def _count_by_status(items: Sequence[Mapping[str, Any]], statuses: Sequence[str]) -> dict[str, int]:
        result = {status: 0 for status in statuses}
        for item in items:
            status = str(item.get("status") or "")
            if status in result:
                result[status] += 1
        result["total"] = len(items)
        return result

    def capture_monitoring_snapshot(
        self,
        record_id: str,
        *,
        observed_at: str | None = None,
        note: str = "",
        actor_id: str = "self",
        snapshot_id: str | None = None,
    ) -> dict[str, Any]:
        record = self.get_record(record_id, include_canonical=True)
        canonical = record["canonical"]
        revision = self.get_revision(record["current_revision_id"])
        observed_at = observed_at or _utc_now()
        try:
            datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise WorkspaceError("observed_at must be an ISO-8601 datetime") from exc
        findings = canonical.get("findings") or {}
        normalized = canonical.get("normalized_input") or {}
        pressure = normalized.get("pressure") or {}
        supports = normalized.get("supports") or {}
        capacity = normalized.get("capacity") or {}
        capacity_values = [capacity.get(key) for key in ("energy_level", "clarity_level", "attention_level", "coordination_capacity")]
        capacity_values = [float(value) for value in capacity_values if value is not None]
        condition_metrics = {
            "pressure": float(pressure.get("level") or 0),
            "support": float(supports.get("level") or 0),
            "clarity": float(capacity.get("clarity_level") or 0),
            "energy": float(capacity.get("energy_level") or 0),
            "capacity": round(sum(capacity_values) / len(capacity_values), 2) if capacity_values else 0.0,
        }
        actions = self.list_actions(record_id, revision_number=revision["revision_number"], as_of=observed_at[:10])
        blockers = self.list_blockers(record_id)
        checkpoints = self.list_checkpoints(record["project_id"], record_id=record_id)
        action_counts = self._count_by_status(actions, ("planned", "in_progress", "blocked", "completed", "paused", "deferred", "cancelled"))
        blocker_counts = self._count_by_status(blockers, ("open", "resolved", "escalated"))
        checkpoint_counts = self._count_by_status(checkpoints, ("planned", "due", "completed", "cancelled"))
        reopened_count = self.connection.execute(
            "SELECT COUNT(*) FROM status_history WHERE entity_type='record' AND entity_id=? AND to_status='active' AND from_status IN ('archived','reviewed','under_review')",
            (record_id,),
        ).fetchone()[0]
        pattern_keys = [str(item.get("pattern_key")) for item in findings.get("adaptation_patterns") or [] if item.get("pattern_key")]
        changes = [item for item in self.list_system_changes(record["project_id"]) if any(source.get("record_id") == record_id for source in item.get("sources") or [])]
        system_change_counts = {key: 0 for key in ("proposed", "piloting", "adopt", "revise", "defer", "retire")}
        for change in changes:
            if change["decision"] in system_change_counts:
                system_change_counts[change["decision"]] += 1
        system_change_counts["total"] = len(changes)
        interpretation = findings.get("interpretation") or {}
        completeness = interpretation.get("completeness") or {}
        confidence = interpretation.get("confidence") or {}
        methodology = findings.get("methodology") or {}
        threshold = float((methodology.get("thresholds") or {}).get("stable", 75.0))
        metadata = canonical.get("metadata") or {}
        profile_version = str((findings.get("calculation_provenance") or {}).get("profile_version") or metadata.get("engine_version") or __version__)
        snapshot_id = snapshot_id or _id("cgms")
        now = _utc_now()
        source_trace = {
            "record_id": record_id,
            "revision_id": revision["revision_id"],
            "revision_number": revision["revision_number"],
            "canonical_path": "$.findings",
            "source_paths": {
                "recovery_score": "$.findings.recovery_score",
                "component_scores": "$.findings.component_scores",
                "pressure": "$.normalized_input.pressure.level",
                "support": "$.normalized_input.supports.level",
                "clarity": "$.normalized_input.capacity.clarity_level",
                "energy": "$.normalized_input.capacity.energy_level",
                "capacity": "$.normalized_input.capacity",
            },
        }
        with self.connection:
            self.connection.execute(
                """INSERT INTO monitoring_snapshots(
                snapshot_id,project_id,record_id,revision_id,revision_number,observed_at,engine_version,schema_version,methodology_profile_version,
                recovery_score,component_scores_json,condition_metrics_json,completeness_percent,confidence_level,confidence_score,
                action_counts_json,blocker_counts_json,checkpoint_counts_json,reopened_count,pattern_keys_json,system_change_counts_json,
                stable_threshold,source_record_hash,source_revision_hash,source_trace_json,note,created_by,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    snapshot_id, record["project_id"], record_id, revision["revision_id"], revision["revision_number"], observed_at,
                    str(metadata.get("engine_version") or revision["engine_version"]), str(metadata.get("schema_version") or revision["schema_version"]), profile_version,
                    float(findings.get("recovery_score") or 0), _json(findings.get("component_scores") or {}), _json(condition_metrics),
                    float(completeness.get("percent") or 0), str(confidence.get("level") or "unknown"), float(confidence.get("score") or 0),
                    _json(action_counts), _json(blocker_counts), _json(checkpoint_counts), int(reopened_count), _json(pattern_keys), _json(system_change_counts),
                    threshold, str(revision["content_sha256"]), str(revision["content_sha256"]), _json(source_trace), note.strip(), actor_id, now,
                ),
            )
            self.connection.execute(
                "INSERT INTO monitoring_snapshot_events(event_id,snapshot_id,event_type,signal_key,actor_id,notes,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (_id("cgmse"), snapshot_id, "captured", "", actor_id, note.strip(), _json({"record_id": record_id, "revision_id": revision["revision_id"]}), now),
            )
            self._audit("monitoring.snapshot_captured", "monitoring_snapshot", snapshot_id, actor_id, {"record_id": record_id, "revision_id": revision["revision_id"]})
        return self.get_monitoring_snapshot(snapshot_id)

    def get_monitoring_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        row = _row(self.connection.execute("SELECT * FROM monitoring_snapshots WHERE snapshot_id=?", (snapshot_id,)).fetchone())
        if not row:
            raise WorkspaceError(f"monitoring snapshot not found: {snapshot_id}")
        item = self._decode_monitoring_snapshot(row)
        item["events"] = [self._decode_monitoring_event(event) for event in self.connection.execute("SELECT * FROM monitoring_snapshot_events WHERE snapshot_id=? ORDER BY created_at,rowid", (snapshot_id,))]
        return item

    @staticmethod
    def _decode_monitoring_event(row: Mapping[str, Any]) -> dict[str, Any]:
        item = dict(row)
        item["payload"] = json.loads(item.pop("payload_json"))
        return item

    def list_monitoring_snapshots(self, project_id: str, *, record_id: str | None = None) -> list[dict[str, Any]]:
        self._require_project(project_id, include_deleted=True)
        if record_id:
            rows = self.connection.execute("SELECT * FROM monitoring_snapshots WHERE project_id=? AND record_id=? ORDER BY observed_at,created_at,rowid", (project_id, record_id))
        else:
            rows = self.connection.execute("SELECT * FROM monitoring_snapshots WHERE project_id=? ORDER BY observed_at,created_at,rowid", (project_id,))
        return [self._decode_monitoring_snapshot(row) for row in rows]

    def annotate_monitoring_snapshot(self, snapshot_id: str, notes: str, *, signal_key: str = "", actor_id: str = "self") -> dict[str, Any]:
        self.get_monitoring_snapshot(snapshot_id)
        if not notes.strip():
            raise WorkspaceError("monitoring annotation notes are required")
        with self.connection:
            self.connection.execute(
                "INSERT INTO monitoring_snapshot_events(event_id,snapshot_id,event_type,signal_key,actor_id,notes,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (_id("cgmse"), snapshot_id, "annotated", signal_key.strip(), actor_id, notes.strip(), "{}", _utc_now()),
            )
            self._audit("monitoring.snapshot_annotated", "monitoring_snapshot", snapshot_id, actor_id, {"signal_key": signal_key.strip()})
        return self.get_monitoring_snapshot(snapshot_id)

    @staticmethod
    def _trend_direction(values: Sequence[float], *, lower_is_better: bool = False) -> str:
        if len(values) < 2:
            return "insufficient_data"
        delta = float(values[-1]) - float(values[0])
        if abs(delta) < 0.5:
            return "stable"
        improving = delta < 0 if lower_is_better else delta > 0
        return "improving" if improving else "declining"

    @staticmethod
    def _days_between(start: str | None, end: str | None) -> float | None:
        if not start or not end:
            return None
        try:
            a = datetime.fromisoformat(start.replace("Z", "+00:00")); b = datetime.fromisoformat(end.replace("Z", "+00:00"))
        except ValueError:
            return None
        return round((b - a).total_seconds() / 86400.0, 2)

    def record_trends(self, record_id: str, *, minimum_points: int = 2) -> dict[str, Any]:
        record = self.get_record(record_id, include_canonical=True, include_deleted=True)
        snapshots = self.list_monitoring_snapshots(record["project_id"], record_id=record_id)
        minimum_points = max(2, int(minimum_points))
        metrics = ("recovery_score", "pressure", "support", "clarity", "energy", "capacity")
        series: dict[str, list[dict[str, Any]]] = {metric: [] for metric in metrics}
        for item in snapshots:
            base = {"snapshot_id": item["snapshot_id"], "record_id": record_id, "revision_id": item["revision_id"], "revision_number": item["revision_number"], "observed_at": item["observed_at"], "engine_version": item["engine_version"], "schema_version": item["schema_version"], "methodology_profile_version": item["methodology_profile_version"], "source_revision_hash": item["source_revision_hash"]}
            series["recovery_score"].append({**base, "value": item["recovery_score"], "source_path": "$.findings.recovery_score"})
            for metric in metrics[1:]:
                series[metric].append({**base, "value": item["condition_metrics"].get(metric), "source_path": item["source_trace"]["source_paths"].get(metric)})
        trends = {}
        for metric, points in series.items():
            values = [float(point["value"]) for point in points if point["value"] is not None]
            trends[metric] = {
                "points": points,
                "direction": self._trend_direction(values, lower_is_better=(metric == "pressure")),
                "delta": round(values[-1] - values[0], 2) if len(values) >= 2 else None,
            }
        average_completeness = round(sum(float(item["completeness_percent"]) for item in snapshots) / len(snapshots), 2) if snapshots else 0.0
        if len(snapshots) < minimum_points:
            confidence = {"state": "sparse_data", "level": "low", "score": min(49.0, average_completeness / 2), "rationale": f"At least {minimum_points} traceable snapshots are required; {len(snapshots)} are available."}
        elif len(snapshots) >= 3 and average_completeness >= 80:
            confidence = {"state": "usable", "level": "high", "score": average_completeness, "rationale": "Three or more traceable snapshots with strong average completeness are available."}
        else:
            confidence = {"state": "usable_with_caution", "level": "moderate", "score": min(79.0, average_completeness), "rationale": "The minimum longitudinal record exists, but interpretation should remain cautious."}
        checkpoints = self.list_checkpoints(record["project_id"], record_id=record_id)
        completed = [item for item in checkpoints if item["status"] == "completed" and item.get("completed_at")]
        first_checkpoint = min(completed, key=lambda item: item["completed_at"]) if completed else None
        stable_snapshot = next((item for item in snapshots if float(item["recovery_score"]) >= float(item["stable_threshold"])), None)
        pattern_counts: dict[str, int] = {}
        for item in snapshots:
            for key in item["pattern_keys"]:
                pattern_counts[key] = pattern_counts.get(key, 0) + 1
        repeated_patterns = [{"pattern_key": key, "snapshot_occurrences": count} for key, count in sorted(pattern_counts.items()) if count >= 2]
        changes = [item for item in self.list_system_changes(record["project_id"]) if any(source.get("record_id") == record_id for source in item.get("sources") or [])]
        latest = snapshots[-1] if snapshots else None
        summary = {
            "contract": "catalyst-grit-monitoring/1.0",
            "scope": "record",
            "record_id": record_id,
            "project_id": record["project_id"],
            "generated_at": _utc_now(),
            "data_state": "sufficient" if len(snapshots) >= minimum_points else "sparse",
            "snapshot_count": len(snapshots),
            "minimum_data_met": len(snapshots) >= minimum_points,
            "confidence": confidence,
            "trends": trends,
            "workflow_outcomes": {
                "latest_action_counts": latest["action_counts"] if latest else {},
                "latest_blocker_counts": latest["blocker_counts"] if latest else {},
                "latest_checkpoint_counts": latest["checkpoint_counts"] if latest else {},
                "reopened_setback_count": max((int(item["reopened_count"]) for item in snapshots), default=0),
                "time_to_first_completed_checkpoint_days": self._days_between(record.get("created_at"), first_checkpoint.get("completed_at") if first_checkpoint else None),
                "time_to_first_stable_condition_days": self._days_between(record.get("created_at"), stable_snapshot.get("observed_at") if stable_snapshot else None),
            },
            "repeated_friction_patterns": repeated_patterns,
            "intervention_outcomes": [{"system_change_id": item["system_change_id"], "decision": item["decision"], "review_result": item["review_result"], "source_record_ids": [source["record_id"] for source in item.get("sources") or []]} for item in changes],
            "traceability": {"snapshot_ids": [item["snapshot_id"] for item in snapshots], "revision_ids": [item["revision_id"] for item in snapshots], "original_engine_versions": sorted({item["engine_version"] for item in snapshots}), "recalculated": False},
            "governance": self.monitoring_governance(minimum_points=minimum_points),
        }
        summary["summary_hash"] = _sha(summary)
        return summary

    def recovery_timeline(self, record_id: str) -> dict[str, Any]:
        record = self.get_record(record_id, include_canonical=True, include_deleted=True)
        events: list[dict[str, Any]] = []
        for revision in self.list_revisions(record_id):
            events.append({"occurred_at": revision["created_at"], "event_type": "record_revision", "entity_id": revision["revision_id"], "revision_number": revision["revision_number"], "engine_version": revision["engine_version"], "source_hash": revision["content_sha256"]})
        for snapshot in self.list_monitoring_snapshots(record["project_id"], record_id=record_id):
            events.append({"occurred_at": snapshot["observed_at"], "event_type": "monitoring_snapshot", "entity_id": snapshot["snapshot_id"], "revision_id": snapshot["revision_id"], "recovery_score": snapshot["recovery_score"], "source_hash": snapshot["source_revision_hash"]})
        for row in self.connection.execute("SELECT * FROM action_events WHERE record_id=?", (record_id,)):
            events.append({"occurred_at": row["created_at"], "event_type": "action_event", "entity_id": row["event_id"], "action_id": row["action_id"], "from_status": row["from_status"], "to_status": row["to_status"]})
        for checkpoint in self.list_checkpoints(record["project_id"], record_id=record_id):
            events.append({"occurred_at": checkpoint["completed_at"] or checkpoint["created_at"], "event_type": "checkpoint", "entity_id": checkpoint["checkpoint_id"], "status": checkpoint["status"], "scheduled_for": checkpoint["scheduled_for"]})
        for reassessment in self.list_reassessments(record_id):
            events.append({"occurred_at": reassessment["created_at"], "event_type": "reassessment", "entity_id": reassessment["reassessment_id"], "from_revision_id": reassessment["from_revision_id"], "to_revision_id": reassessment["to_revision_id"]})
        events.sort(key=lambda item: (item.get("occurred_at") or "", item["event_type"], item["entity_id"]))
        return {"record_id": record_id, "project_id": record["project_id"], "events": events, "event_count": len(events), "governance": self.monitoring_governance()}

    def record_monitoring_dashboard(self, record_id: str, *, minimum_points: int = 2) -> dict[str, Any]:
        trends = self.record_trends(record_id, minimum_points=minimum_points)
        trends["dashboard"] = "personal_private"
        trends["timeline"] = self.recovery_timeline(record_id)
        trends["publication_state"] = "private"
        return trends

    def project_monitoring_dashboard(self, project_id: str, *, minimum_points: int = 2) -> dict[str, Any]:
        project = self.get_project(project_id, include_deleted=True)
        records = self.list_records(project_id, include_archived=True)
        record_summaries = [self.record_trends(item["record_id"], minimum_points=minimum_points) for item in records]
        snapshots = self.list_monitoring_snapshots(project_id)
        latest_by_record: dict[str, dict[str, Any]] = {}
        for item in snapshots:
            latest_by_record[item["record_id"]] = item
        latest = list(latest_by_record.values())
        aggregate = {
            "record_count": len(records),
            "monitored_record_count": len(latest),
            "snapshot_count": len(snapshots),
            "average_latest_recovery_score": round(sum(item["recovery_score"] for item in latest) / len(latest), 2) if latest else None,
            "action_counts": {},
            "blocker_counts": {},
            "checkpoint_counts": {},
        }
        for key in ("action_counts", "blocker_counts", "checkpoint_counts"):
            merged: dict[str, int] = {}
            for item in latest:
                for status, count in item[key].items():
                    merged[status] = merged.get(status, 0) + int(count)
            aggregate[key] = merged
        patterns = self.detect_project_patterns(project_id, minimum_occurrences=2)
        changes = self.list_system_changes(project_id)
        dashboard = {
            "contract": "catalyst-grit-monitoring-dashboard/1.0",
            "dashboard": "project",
            "project": {"project_id": project_id, "title": project["title"], "visibility": project["visibility"]},
            "generated_at": _utc_now(),
            "aggregate": aggregate,
            "records": [{"record_id": item["record_id"], "data_state": item["data_state"], "snapshot_count": item["snapshot_count"], "summary_hash": item["summary_hash"]} for item in record_summaries],
            "pattern_summary": {"repeated_pattern_count": len(patterns), "patterns": patterns},
            "adaptation_summary": {"system_change_count": len(changes), "decisions": {decision: sum(1 for item in changes if item.get("decision") == decision) for decision in ("proposed", "piloting", "adopt", "revise", "defer", "retire")}},
            "governance": self.monitoring_governance(minimum_points=minimum_points),
            "human_review": {"required_before_institutional_interpretation": True, "reviews": self.list_monitoring_reviews(project_id, scope="project")},
        }
        dashboard["summary_hash"] = _sha(dashboard)
        return dashboard

    def team_conditions_dashboard(self, project_id: str, *, actor_id: str = "self", minimum_group_size: int = 3) -> dict[str, Any]:
        self._require_team_role(project_id, actor_id, {"owner", "facilitator", "reviewer"})
        threshold = max(3, int(minimum_group_size))
        members = [item for item in self.list_team_members(project_id) if item["status"] == "active" and item["consent_status"] == "granted"]
        snapshots = self.list_monitoring_snapshots(project_id)
        latest_by_record: dict[str, dict[str, Any]] = {}
        for item in snapshots:
            latest_by_record[item["record_id"]] = item
        privacy_met = len(members) >= threshold and len(latest_by_record) >= 1
        dashboard = {
            "contract": "catalyst-grit-monitoring-dashboard/1.0",
            "dashboard": "team_system_conditions",
            "project_id": project_id,
            "generated_at": _utc_now(),
            "privacy": {"threshold": threshold, "consented_active_member_count": len(members), "threshold_met": privacy_met, "suppressed": not privacy_met},
            "individual_comparisons": [],
            "governance": self.monitoring_governance(privacy_threshold=threshold),
            "human_review": {"required": True, "reviews": self.list_monitoring_reviews(project_id, scope="team_system")},
        }
        if privacy_met:
            latest = list(latest_by_record.values())
            dashboard["aggregate_conditions"] = {
                "record_count": len(latest),
                "average_recovery_score": round(sum(item["recovery_score"] for item in latest) / len(latest), 2),
                "average_pressure": round(sum(item["condition_metrics"]["pressure"] for item in latest) / len(latest), 2),
                "average_support": round(sum(item["condition_metrics"]["support"] for item in latest) / len(latest), 2),
                "average_clarity": round(sum(item["condition_metrics"]["clarity"] for item in latest) / len(latest), 2),
                "average_energy": round(sum(item["condition_metrics"]["energy"] for item in latest) / len(latest), 2),
                "average_capacity": round(sum(item["condition_metrics"]["capacity"] for item in latest) / len(latest), 2),
                "traceable_snapshot_ids": [item["snapshot_id"] for item in latest],
            }
        else:
            dashboard["aggregate_conditions"] = None
            dashboard["suppression_reason"] = "Aggregation is withheld until the minimum consented group-size threshold is met."
        dashboard["summary_hash"] = _sha(dashboard)
        return dashboard

    def review_monitoring_summary(self, project_id: str, summary_hash: str, *, scope: str, status: str, reviewer_id: str, notes: str = "", record_id: str | None = None) -> dict[str, Any]:
        self._require_project(project_id, include_deleted=True)
        if scope not in {"record", "project", "team_system"}:
            raise WorkspaceError("unsupported monitoring review scope")
        if status not in {"pending", "reviewed", "changes_requested", "approved"}:
            raise WorkspaceError("unsupported monitoring review status")
        if scope == "record":
            if not record_id:
                raise WorkspaceError("record_id is required for record monitoring reviews")
            record = self._require_record(record_id, include_deleted=True)
            if record["project_id"] != project_id:
                raise WorkspaceError("monitoring review record must belong to the project")
        review_id = _id("cgmr")
        with self.connection:
            self.connection.execute("INSERT INTO monitoring_reviews(review_id,project_id,record_id,scope,summary_hash,status,reviewer_id,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (review_id, project_id, record_id, scope, summary_hash.strip(), status, reviewer_id, notes.strip(), _utc_now()))
            self._audit("monitoring.summary_reviewed", "monitoring_review", review_id, reviewer_id, {"scope": scope, "status": status, "summary_hash": summary_hash})
        return dict(self.connection.execute("SELECT * FROM monitoring_reviews WHERE review_id=?", (review_id,)).fetchone())

    def list_monitoring_reviews(self, project_id: str, *, scope: str | None = None, record_id: str | None = None) -> list[dict[str, Any]]:
        self._require_project(project_id, include_deleted=True)
        query = "SELECT * FROM monitoring_reviews WHERE project_id=?"; params: list[Any] = [project_id]
        if scope:
            query += " AND scope=?"; params.append(scope)
        if record_id:
            query += " AND record_id=?"; params.append(record_id)
        query += " ORDER BY created_at,rowid"
        return [dict(row) for row in self.connection.execute(query, params)]

    def status_history(self, entity_type: str, entity_id: str) -> list[dict[str, Any]]:
        return [dict(row) for row in self.connection.execute("SELECT * FROM status_history WHERE entity_type=? AND entity_id=? ORDER BY created_at, rowid", (entity_type, entity_id))]

    def audit_log(self, entity_type: str | None = None, entity_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM audit_events"
        params: list[Any] = []
        clauses = []
        if entity_type:
            clauses.append("entity_type=?"); params.append(entity_type)
        if entity_id:
            clauses.append("entity_id=?"); params.append(entity_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at,rowid"
        result = []
        for row in self.connection.execute(query, params):
            item = dict(row); item["payload"] = json.loads(item.pop("payload_json")); result.append(item)
        return result

    def export_record(self, record_id: str) -> dict[str, Any]:
        record = self.get_record(record_id, include_canonical=True, include_deleted=True)
        project = self.get_project(record["project_id"], include_deleted=True)
        revisions = self.list_revisions(record_id)
        return {
            "format": WORKSPACE_FORMAT,
            "exported_at": _utc_now(),
            "product_version": __version__,
            "project": project,
            "record": {key: value for key, value in record.items() if key != "canonical"},
            "current_record": record.get("canonical"),
            "revisions": revisions,
            "actions": [item for revision in revisions for item in self.list_actions(record_id, revision_number=revision["revision_number"])],
            "action_events": [dict(row) for row in self.connection.execute("SELECT * FROM action_events WHERE record_id=? ORDER BY created_at,rowid", (record_id,))],
            "blockers": self.list_blockers(record_id),
            "reassessments": self.list_reassessments(record_id),
            "retrospectives": self.list_retrospectives(record_id),
            "checkpoints": self.list_checkpoints(project["project_id"], record_id=record_id),
            "reviews": self.list_reviews(record_id),
            "status_history": self.status_history("record", record_id),
            "audit_events": self.audit_log(entity_id=record_id),
            "team_perspectives": self.list_team_perspectives(project["project_id"], record_id=record_id, actor_id=project["owner_id"]),
            "evidence_items": self.list_evidence(project["project_id"], record_id=record_id),
            "assumptions": self.list_assumptions(project["project_id"], record_id=record_id),
            "handoffs": self.list_handoffs(project["project_id"], record_id=record_id),
            "monitoring_snapshots": self.list_monitoring_snapshots(project["project_id"], record_id=record_id),
            "monitoring_reviews": self.list_monitoring_reviews(project["project_id"], record_id=record_id),
        }

    def export_project(self, project_id: str) -> dict[str, Any]:
        project = self.get_project(project_id, include_deleted=True)
        records = self.list_records(project_id, include_archived=True, include_deleted=True)
        return {
            "format": WORKSPACE_FORMAT,
            "exported_at": _utc_now(),
            "product_version": __version__,
            "project": project,
            "records": [self.export_record(item["record_id"]) for item in records],
            "patterns": self.detect_project_patterns(project_id, minimum_occurrences=1, include_singletons=True),
            "pattern_reviews": self.list_pattern_reviews(project_id),
            "system_changes": self.list_system_changes(project_id),
            "team_members": self.list_team_members(project_id, include_removed=True),
            "facilitated_sessions": self.list_facilitated_sessions(project_id, actor_id=project["owner_id"]),
            "team_recovery_summary": self.team_recovery_summary(project_id, actor_id=project["owner_id"]),
            "evidence_ledger": self.evidence_ledger(project_id),
            "assumption_matrix": self.assumption_matrix(project_id),
            "handoffs": self.list_handoffs(project_id),
            "monitoring_dashboard": self.project_monitoring_dashboard(project_id),
            "monitoring_reviews": self.list_monitoring_reviews(project_id),
            "institutional_policies": self.list_institutional_policies(project_id=project_id),
            "access_reviews": self.list_access_reviews(project_id),
            "publication_artifacts": self.list_publication_artifacts(project_id, include_content=False),
            "methodology_registry": self.list_methodologies(),
            "schema_compatibility": self.schema_compatibility("catalyst_grit_record", SCHEMA_VERSION),
            "institutional_diagnostics": self.institutional_diagnostics(),
            "connected_platform": self._connected_platform_export(project_id),
        }

    def _connected_platform_export(self, project_id: str) -> dict[str, Any]:
        from .platform import ConnectedPlatformService
        service = ConnectedPlatformService(self)
        return {
            "contract": "catalyst-grit-connected-platform/2.0",
            "workflows": service.list_workflows(project_id),
            "artifact_connections": service.list_connections(project_id),
            "sync_events": service.list_sync_events(project_id),
            "portable_snapshots": service.list_portable_snapshots(project_id),
        }

    def import_payload(self, payload: Mapping[str, Any], *, project_id: str | None = None, actor_id: str = "self") -> dict[str, Any]:
        if payload.get("format") == WORKSPACE_FORMAT:
            return self._import_bundle(payload, project_id=project_id, actor_id=actor_id)
        if not project_id:
            raise WorkspaceError("project_id is required when importing a record or request")
        return self.save_record(project_id, payload, actor_id=actor_id, reason="imported")

    def _import_bundle(self, payload: Mapping[str, Any], *, project_id: str | None, actor_id: str) -> dict[str, Any]:
        project_data = dict(payload.get("project") or {})
        target_project = project_id or project_data.get("project_id")
        if not target_project:
            target_project = _id("cgp")
        try:
            self.get_project(target_project, include_deleted=True)
        except WorkspaceError:
            self.create_project(project_data.get("title") or "Imported recovery project", description=project_data.get("description") or "", owner_id=actor_id, retention_days=project_data.get("retention_days"), project_id=target_project, actor_id=actor_id)
        bundles: Sequence[Mapping[str, Any]]
        if "records" in payload:
            bundles = payload.get("records") or []
        else:
            bundles = [payload]
        imported = []
        for bundle in bundles:
            revisions = bundle.get("revisions") or []
            if revisions:
                for revision in sorted(revisions, key=lambda item: item.get("revision_number", 0)):
                    imported.append(self.save_record(target_project, revision["canonical"], actor_id=actor_id, reason="workspace import"))
            elif bundle.get("current_record"):
                imported.append(self.save_record(target_project, bundle["current_record"], actor_id=actor_id, reason="workspace import"))
            for checkpoint in bundle.get("checkpoints") or []:
                existing = self.connection.execute("SELECT 1 FROM checkpoints WHERE checkpoint_id=?", (checkpoint.get("checkpoint_id"),)).fetchone()
                if not existing:
                    record_id = checkpoint.get("record_id")
                    try:
                        if record_id:
                            self._require_record(record_id)
                    except WorkspaceError:
                        record_id = None
                    self.create_checkpoint(target_project, checkpoint.get("title") or "Imported checkpoint", record_id=record_id, scheduled_for=checkpoint.get("scheduled_for"), notes=checkpoint.get("notes") or "", actor_id=actor_id, checkpoint_id=checkpoint.get("checkpoint_id"))

        imported_pattern_reviews = 0
        for review in payload.get("pattern_reviews") or []:
            review_id = str(review.get("pattern_review_id") or _id("cgpr"))
            if self.connection.execute("SELECT 1 FROM pattern_reviews WHERE pattern_review_id=?", (review_id,)).fetchone():
                continue
            decision = str(review.get("decision") or "")
            if decision not in {"accept", "reject", "correct"}:
                continue
            with self.connection:
                self.connection.execute(
                    "INSERT INTO pattern_reviews(pattern_review_id,project_id,pattern_key,decision,corrected_label,notes,evidence_json,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        review_id,
                        target_project,
                        str(review.get("pattern_key") or ""),
                        decision,
                        str(review.get("corrected_label") or ""),
                        str(review.get("notes") or ""),
                        _json(review.get("evidence") or []),
                        actor_id,
                        str(review.get("created_at") or _utc_now()),
                    ),
                )
                self._audit("pattern.review_imported", "pattern", str(review.get("pattern_key") or ""), actor_id, {"project_id": target_project, "source_pattern_review_id": review_id})
            imported_pattern_reviews += 1

        imported_system_changes = 0
        for change in payload.get("system_changes") or []:
            change_id = str(change.get("system_change_id") or _id("cgsc"))
            if self.connection.execute("SELECT 1 FROM system_changes WHERE system_change_id=?", (change_id,)).fetchone():
                continue
            valid_sources = []
            for source in change.get("sources") or []:
                record_id = str(source.get("record_id") or "")
                try:
                    record = self._require_record(record_id)
                except WorkspaceError:
                    continue
                if record["project_id"] == target_project:
                    valid_sources.append(source)
            if not valid_sources:
                continue
            decision = str(change.get("decision") or "proposed")
            if decision not in {"proposed", "piloting", "adopt", "revise", "defer", "retire"}:
                decision = "proposed"
            created_at = str(change.get("created_at") or _utc_now())
            updated_at = str(change.get("updated_at") or created_at)
            with self.connection:
                self.connection.execute(
                    "INSERT INTO system_changes(system_change_id,project_id,title,proposed_change,owner,expected_benefit,pilot_start,pilot_end,review_result,decision,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        change_id,
                        target_project,
                        str(change.get("title") or "Imported system change"),
                        str(change.get("proposed_change") or "Imported proposal"),
                        change.get("owner"),
                        str(change.get("expected_benefit") or ""),
                        change.get("pilot_start"),
                        change.get("pilot_end"),
                        str(change.get("review_result") or ""),
                        decision,
                        created_at,
                        updated_at,
                    ),
                )
                for source in valid_sources:
                    self.connection.execute(
                        "INSERT INTO system_change_sources(system_change_id,record_id,evidence_note) VALUES(?,?,?)",
                        (change_id, source["record_id"], str(source.get("evidence_note") or "")),
                    )
                events = change.get("events") or []
                if not events:
                    events = [{"from_decision": None, "to_decision": decision, "review_result": str(change.get("review_result") or ""), "reason": "system change imported", "created_at": created_at}]
                for event in events:
                    event_id = str(event.get("event_id") or _id("cgsce"))
                    if self.connection.execute("SELECT 1 FROM system_change_events WHERE event_id=?", (event_id,)).fetchone():
                        event_id = _id("cgsce")
                    self.connection.execute(
                        "INSERT INTO system_change_events(event_id,system_change_id,from_decision,to_decision,review_result,actor_id,reason,created_at) VALUES(?,?,?,?,?,?,?,?)",
                        (
                            event_id,
                            change_id,
                            event.get("from_decision"),
                            str(event.get("to_decision") or decision),
                            str(event.get("review_result") or ""),
                            actor_id,
                            str(event.get("reason") or "system change imported"),
                            str(event.get("created_at") or created_at),
                        ),
                    )
                self._audit("system_change.imported", "system_change", change_id, actor_id, {"project_id": target_project, "source_records": [item["record_id"] for item in valid_sources]})
            imported_system_changes += 1

        imported_team_members = 0
        for member in payload.get("team_members") or []:
            member_key = str(member.get("member_key") or "").strip()
            if not member_key or member_key == actor_id:
                continue
            if self.connection.execute("SELECT 1 FROM team_memberships WHERE project_id=? AND member_key=?", (target_project, member_key)).fetchone():
                continue
            role = str(member.get("role") or "contributor")
            if role not in {"owner", "facilitator", "contributor", "reviewer", "observer"}:
                role = "contributor"
            status = str(member.get("status") or "invited")
            if status not in {"invited", "active", "removed"}:
                status = "invited"
            consent = str(member.get("consent_status") or "pending")
            if consent not in {"pending", "granted", "withdrawn"}:
                consent = "pending"
            self.add_team_member(
                target_project,
                member_key,
                str(member.get("display_name") or member_key),
                role=role,
                status=status,
                access_scope=str(member.get("access_scope") or "shared"),
                consent_status=consent,
                actor_id=actor_id,
            )
            imported_team_members += 1

        imported_sessions = 0
        imported_perspectives = 0
        imported_agreements = 0
        for source_session in payload.get("facilitated_sessions") or []:
            facilitator_key = str(source_session.get("facilitator_key") or actor_id)
            try:
                facilitator = self._membership(target_project, facilitator_key)
                if facilitator["role"] not in {"owner", "facilitator"}:
                    facilitator_key = actor_id
            except WorkspaceError:
                facilitator_key = actor_id
            record_id = source_session.get("record_id")
            try:
                if record_id:
                    record = self._require_record(str(record_id))
                    if record["project_id"] != target_project:
                        record_id = None
            except WorkspaceError:
                record_id = None
            session = self.create_facilitated_session(
                target_project,
                str(source_session.get("title") or "Imported facilitated review"),
                purpose=str(source_session.get("purpose") or ""),
                facilitator_key=facilitator_key,
                record_id=record_id,
                scheduled_for=source_session.get("scheduled_for"),
                ground_rules=source_session.get("ground_rules") or [],
                agenda=source_session.get("agenda") or [],
                notes=str(source_session.get("notes") or ""),
                actor_id=actor_id,
            )
            imported_sessions += 1
            for participant in source_session.get("participants") or []:
                member_key = str(participant.get("member_key") or "")
                if not member_key:
                    continue
                try:
                    self.add_session_participant(
                        session["session_id"],
                        member_key,
                        participation_status=str(participant.get("participation_status") or "invited"),
                        consent_status=str(participant.get("consent_status") or "pending"),
                        sharing_scope=str(participant.get("sharing_scope") or "shared"),
                        actor_id=actor_id,
                    )
                except WorkspaceError:
                    continue
            for perspective in source_session.get("perspectives") or []:
                member_key = str(perspective.get("member_key") or actor_id)
                try:
                    self.add_team_perspective(
                        target_project,
                        str(perspective.get("content") or ""),
                        perspective_type=str(perspective.get("perspective_type") or "other"),
                        member_key=member_key,
                        contributor_label=str(perspective.get("contributor_label") or ""),
                        session_id=session["session_id"],
                        record_id=record_id,
                        sharing_scope=str(perspective.get("sharing_scope") or "shared"),
                        consent_status=str(perspective.get("consent_status") or "granted"),
                        source_path=str(perspective.get("source_path") or ""),
                        actor_id=actor_id,
                    )
                    imported_perspectives += 1
                except WorkspaceError:
                    continue
            for agreement in source_session.get("agreements") or []:
                owner_key = agreement.get("owner_key")
                try:
                    created = self.create_facilitated_agreement(
                        session["session_id"],
                        str(agreement.get("title") or "Imported agreement"),
                        owner_key=owner_key,
                        due_date=agreement.get("due_date"),
                        status="proposed",
                        support_needed=str(agreement.get("support_needed") or ""),
                        actor_id=actor_id,
                    )
                    target_status = str(agreement.get("status") or "proposed")
                    if target_status != "proposed":
                        evidence = str(agreement.get("completion_evidence") or "")
                        if target_status == "completed" and not evidence:
                            evidence = "Imported completion evidence was not supplied."
                        support = str(agreement.get("support_needed") or "")
                        if target_status == "blocked" and not support:
                            support = "Imported blocker support need was not supplied."
                        self.update_facilitated_agreement(
                            created["agreement_id"],
                            status=target_status,
                            reason="workspace import",
                            completion_evidence=evidence,
                            support_needed=support,
                            actor_id=actor_id,
                        )
                    imported_agreements += 1
                except WorkspaceError:
                    continue
            source_status = str(source_session.get("status") or "planned")
            if source_status != "planned" and source_status in {"in_progress", "completed", "cancelled"}:
                self.update_facilitated_session(session["session_id"], status=source_status, actor_id=actor_id)

        imported_evidence = 0
        imported_assumptions = 0
        imported_handoffs = 0
        evidence_sources = list(payload.get("evidence_items") or [])
        assumption_sources = list(payload.get("assumptions") or [])
        handoff_sources = list(payload.get("handoffs") or [])
        for bundle in bundles:
            evidence_sources.extend(bundle.get("evidence_items") or [])
            assumption_sources.extend(bundle.get("assumptions") or [])
            handoff_sources.extend(bundle.get("handoffs") or [])
        evidence_id_map: dict[str, str] = {}
        for item in evidence_sources:
            try:
                record_id = item.get("record_id")
                if record_id:
                    try:
                        record = self._require_record(str(record_id))
                        if record["project_id"] != target_project:
                            record_id = None
                    except WorkspaceError:
                        record_id = None
                created = self.add_evidence(
                    target_project,
                    str(item.get("title") or "Imported evidence"),
                    evidence_type=str(item.get("evidence_type") or "note"),
                    content=str(item.get("content") or ""),
                    record_id=record_id,
                    source_uri=str(item.get("source_uri") or ""),
                    source_artifact_id=str(item.get("source_artifact_id") or ""),
                    source_product=str(item.get("source_product") or ""),
                    source_version=str(item.get("source_version") or ""),
                    provenance=item.get("provenance") or [],
                    strength=str(item.get("strength") or "unknown"),
                    review_state=str(item.get("review_state") or "unreviewed"),
                    observed_at=item.get("observed_at"),
                    actor_id=actor_id,
                )
                evidence_id_map[str(item.get("evidence_id") or "")] = created["evidence_id"]
                imported_evidence += 1
            except WorkspaceError:
                continue
        assumption_id_map: dict[str, str] = {}
        for item in assumption_sources:
            try:
                record_id = item.get("record_id")
                if record_id:
                    try:
                        record = self._require_record(str(record_id))
                        if record["project_id"] != target_project:
                            record_id = None
                    except WorkspaceError:
                        record_id = None
                created = self.add_assumption(
                    target_project,
                    str(item.get("statement") or "Imported assumption"),
                    record_id=record_id,
                    uncertainty=str(item.get("uncertainty") or ""),
                    confidence=int(item.get("confidence", 50)),
                    owner=item.get("owner"),
                    review_due=item.get("review_due"),
                    source_paths=item.get("source_paths") or [],
                    actor_id=actor_id,
                )
                target_status = str(item.get("status") or "active")
                if target_status != "active" and target_status in {"validated", "rejected", "retired"}:
                    created = self.update_assumption(created["assumption_id"], status=target_status, confidence=int(item.get("confidence", 50)), reason="workspace import", actor_id=actor_id)
                assumption_id_map[str(item.get("assumption_id") or "")] = created["assumption_id"]
                imported_assumptions += 1
            except (WorkspaceError, ValueError, TypeError):
                continue
        for item in handoff_sources:
            try:
                record_id = item.get("record_id")
                if record_id:
                    try:
                        record = self._require_record(str(record_id))
                        if record["project_id"] != target_project:
                            record_id = None
                    except WorkspaceError:
                        record_id = None
                created = self.create_handoff(
                    target_project,
                    source_product=str(item.get("source_product") or "External"),
                    source_version=str(item.get("source_version") or "unknown"),
                    target_product=str(item.get("target_product") or "Catalyst Grit"),
                    artifact_type=str(item.get("artifact_type") or "imported_artifact"),
                    artifact_id=str(item.get("artifact_id") or _id("artifact")),
                    payload=item.get("payload") or {},
                    record_id=record_id,
                    direction=str(item.get("direction") or "inbound"),
                    reference_mode=str(item.get("reference_mode") or "snapshot"),
                    source_uri=str(item.get("source_uri") or ""),
                    provenance=item.get("provenance") or [],
                    stale_after=item.get("stale_after"),
                    actor_id=actor_id,
                )
                target_state = str(item.get("validation_state") or "valid")
                if target_state != "valid" and target_state in {"invalid", "stale", "conflict"}:
                    self.validate_handoff(created["handoff_id"], state=target_state, conflict_notes=str(item.get("conflict_notes") or ""), actor_id=actor_id)
                imported_handoffs += 1
            except WorkspaceError:
                continue

        imported_monitoring_snapshots = 0
        monitoring_sources = list(payload.get("monitoring_snapshots") or [])
        for bundle in bundles:
            monitoring_sources.extend(bundle.get("monitoring_snapshots") or [])
        for item in monitoring_sources:
            record_id = str(item.get("record_id") or "")
            try:
                record = self._require_record(record_id)
            except WorkspaceError:
                continue
            if record["project_id"] != target_project:
                continue
            revision_number = int(item.get("revision_number") or 0)
            revision = _row(self.connection.execute("SELECT * FROM record_revisions WHERE record_id=? AND revision_number=?", (record_id, revision_number)).fetchone())
            if not revision:
                continue
            try:
                restored = self.capture_monitoring_snapshot(record_id, observed_at=str(item.get("observed_at") or _utc_now()), note=str(item.get("note") or "Imported monitoring snapshot"), actor_id=actor_id)
                imported_monitoring_snapshots += 1
            except WorkspaceError:
                continue
        imported_monitoring_reviews = 0
        for review in payload.get("monitoring_reviews") or []:
            try:
                self.review_monitoring_summary(target_project, str(review.get("summary_hash") or "imported"), scope=str(review.get("scope") or "project"), status=str(review.get("status") or "pending"), reviewer_id=actor_id, notes=str(review.get("notes") or "Imported monitoring review"), record_id=review.get("record_id"))
                imported_monitoring_reviews += 1
            except WorkspaceError:
                continue

        imported_policies = 0
        for policy in payload.get("institutional_policies") or []:
            try:
                self.set_institutional_policy(str(policy.get("policy_type") or "export_redaction"), policy.get("config") or {}, project_id=target_project if policy.get("project_id") else None, status=str(policy.get("status") or "active"), effective_at=policy.get("effective_at"), expires_at=policy.get("expires_at"), actor_id=actor_id)
                imported_policies += 1
            except WorkspaceError:
                continue
        imported_access_reviews = 0
        for review in payload.get("access_reviews") or []:
            try:
                self.record_access_review(target_project, str(review.get("subject_type") or "project"), str(review.get("subject_id") or target_project), str(review.get("decision") or "approved"), reviewer_id=actor_id, scopes=review.get("scopes") or [], notes=str(review.get("notes") or "Imported access review"), reviewed_at=review.get("reviewed_at"), next_review_at=review.get("next_review_at"))
                imported_access_reviews += 1
            except WorkspaceError:
                continue

        return {
            "project_id": target_project,
            "imported": imported,
            "pattern_reviews_imported": imported_pattern_reviews,
            "system_changes_imported": imported_system_changes,
            "team_members_imported": imported_team_members,
            "facilitated_sessions_imported": imported_sessions,
            "team_perspectives_imported": imported_perspectives,
            "facilitated_agreements_imported": imported_agreements,
            "evidence_items_imported": imported_evidence,
            "assumptions_imported": imported_assumptions,
            "handoffs_imported": imported_handoffs,
            "monitoring_snapshots_imported": imported_monitoring_snapshots,
            "monitoring_reviews_imported": imported_monitoring_reviews,
            "institutional_policies_imported": imported_policies,
            "access_reviews_imported": imported_access_reviews,
        }


    @staticmethod
    def new_identifier(prefix: str) -> str:
        """Return a stable-prefix opaque identifier for external services."""
        return _id(prefix)

    @staticmethod
    def _decode_policy(row: Mapping[str, Any]) -> dict[str, Any]:
        item = dict(row)
        item["config"] = json.loads(item.pop("config_json"))
        return item

    def set_institutional_policy(
        self,
        policy_type: str,
        config: Mapping[str, Any],
        *,
        project_id: str | None = None,
        status: str = "active",
        effective_at: str | None = None,
        expires_at: str | None = None,
        actor_id: str = "self",
    ) -> dict[str, Any]:
        allowed = {"retention", "export_redaction", "access_review", "methodology_governance", "schema_deprecation"}
        if policy_type not in allowed:
            raise WorkspaceError(f"unsupported institutional policy: {policy_type}")
        if status not in {"draft", "active", "retired"}:
            raise WorkspaceError(f"unsupported policy status: {status}")
        if project_id:
            self._require_project(project_id, include_deleted=True)
        version = int(self.connection.execute(
            "SELECT COALESCE(MAX(version),0)+1 FROM institutional_policies WHERE project_id IS ? AND policy_type=?",
            (project_id, policy_type),
        ).fetchone()[0])
        policy_id = _id("cgpol")
        now = _utc_now()
        with self.connection:
            if status == "active":
                self.connection.execute(
                    "UPDATE institutional_policies SET status='retired' WHERE project_id IS ? AND policy_type=? AND status='active'",
                    (project_id, policy_type),
                )
            self.connection.execute(
                "INSERT INTO institutional_policies(policy_id,project_id,policy_type,version,status,config_json,effective_at,expires_at,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (policy_id, project_id, policy_type, version, status, _json(dict(config)), effective_at or now, expires_at, actor_id, now),
            )
            self._audit("institutional_policy.created", "project" if project_id else "institution", project_id or "global", actor_id, {"policy_id": policy_id, "policy_type": policy_type, "version": version, "status": status})
        return self.get_institutional_policy(policy_id)

    def get_institutional_policy(self, policy_id: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM institutional_policies WHERE policy_id=?", (policy_id,)).fetchone()
        if not row:
            raise WorkspaceError(f"institutional policy not found: {policy_id}")
        return self._decode_policy(row)

    def list_institutional_policies(self, *, project_id: str | None = None, policy_type: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM institutional_policies WHERE 1=1"; params: list[Any] = []
        if project_id is not None:
            query += " AND (project_id=? OR project_id IS NULL)"; params.append(project_id)
        if policy_type:
            query += " AND policy_type=?"; params.append(policy_type)
        if status:
            query += " AND status=?"; params.append(status)
        query += " ORDER BY policy_type,version,created_at"
        return [self._decode_policy(row) for row in self.connection.execute(query, params)]

    def record_access_review(
        self,
        project_id: str,
        subject_type: str,
        subject_id: str,
        decision: str,
        *,
        reviewer_id: str,
        scopes: Sequence[str] | None = None,
        notes: str = "",
        reviewed_at: str | None = None,
        next_review_at: str | None = None,
    ) -> dict[str, Any]:
        self._require_project(project_id, include_deleted=True)
        if subject_type not in {"member", "api_client", "publication", "project"}:
            raise WorkspaceError(f"unsupported access-review subject: {subject_type}")
        if decision not in {"approved", "changes_required", "revoked", "expired"}:
            raise WorkspaceError(f"unsupported access-review decision: {decision}")
        access_review_id = _id("cgar")
        now = _utc_now()
        with self.connection:
            self.connection.execute(
                "INSERT INTO access_reviews(access_review_id,project_id,subject_type,subject_id,decision,reviewer_id,scope_json,notes,reviewed_at,next_review_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (access_review_id, project_id, subject_type, subject_id, decision, reviewer_id, _json(list(scopes or [])), notes.strip(), reviewed_at or now, next_review_at, now),
            )
            self._audit("access.reviewed", subject_type, subject_id, reviewer_id, {"project_id": project_id, "decision": decision, "scopes": list(scopes or [])})
        return self.get_access_review(access_review_id)

    def get_access_review(self, access_review_id: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM access_reviews WHERE access_review_id=?", (access_review_id,)).fetchone()
        if not row:
            raise WorkspaceError(f"access review not found: {access_review_id}")
        item = dict(row); item["scopes"] = json.loads(item.pop("scope_json")); return item

    def list_access_reviews(self, project_id: str, *, subject_type: str | None = None, subject_id: str | None = None) -> list[dict[str, Any]]:
        self._require_project(project_id, include_deleted=True)
        query = "SELECT * FROM access_reviews WHERE project_id=?"; params: list[Any] = [project_id]
        if subject_type:
            query += " AND subject_type=?"; params.append(subject_type)
        if subject_id:
            query += " AND subject_id=?"; params.append(subject_id)
        query += " ORDER BY reviewed_at,created_at,rowid"
        result=[]
        for row in self.connection.execute(query, params):
            item=dict(row); item["scopes"]=json.loads(item.pop("scope_json")); result.append(item)
        return result

    def create_api_client(
        self,
        name: str,
        *,
        scopes: Sequence[str],
        project_ids: Sequence[str] | None = None,
        rate_limit_per_minute: int = 60,
        actor_id: str = "self",
    ) -> dict[str, Any]:
        if not name.strip():
            raise WorkspaceError("API client name is required")
        if not scopes:
            raise WorkspaceError("at least one API scope is required")
        if rate_limit_per_minute < 1 or rate_limit_per_minute > 10000:
            raise WorkspaceError("rate limit must be between 1 and 10000")
        for project_id in project_ids or []:
            self._require_project(project_id, include_deleted=True)
        client_id = _id("cgapi")
        token = f"cg_live_{secrets.token_urlsafe(32)}"
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = _utc_now()
        with self.connection:
            self.connection.execute(
                "INSERT INTO api_clients(client_id,name,token_hash,scopes_json,project_ids_json,rate_limit_per_minute,status,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (client_id, name.strip(), token_hash, _json(sorted(set(scopes))), _json(sorted(set(project_ids or []))), rate_limit_per_minute, "active", actor_id, now),
            )
            self._audit("api_client.created", "api_client", client_id, actor_id, {"scopes": sorted(set(scopes)), "project_ids": sorted(set(project_ids or [])), "rate_limit_per_minute": rate_limit_per_minute})
        client = self.get_api_client(client_id)
        client["token"] = token
        client["token_displayed_once"] = True
        return client

    @staticmethod
    def _decode_api_client(row: Mapping[str, Any], *, include_hash: bool = False) -> dict[str, Any]:
        item = dict(row)
        item["scopes"] = json.loads(item.pop("scopes_json"))
        item["project_ids"] = json.loads(item.pop("project_ids_json"))
        if not include_hash:
            item.pop("token_hash", None)
        return item

    def get_api_client(self, client_id: str, *, include_hash: bool = False) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM api_clients WHERE client_id=?", (client_id,)).fetchone()
        if not row:
            raise WorkspaceError(f"API client not found: {client_id}")
        return self._decode_api_client(row, include_hash=include_hash)

    def list_api_clients(self, *, include_revoked: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM api_clients" + ("" if include_revoked else " WHERE status='active'") + " ORDER BY created_at,rowid"
        return [self._decode_api_client(row) for row in self.connection.execute(query)]

    def revoke_api_client(self, client_id: str, *, actor_id: str = "self", reason: str = "") -> dict[str, Any]:
        client = self.get_api_client(client_id)
        if client["status"] == "revoked":
            return client
        with self.connection:
            self.connection.execute("UPDATE api_clients SET status='revoked',revoked_at=? WHERE client_id=?", (_utc_now(), client_id))
            self._audit("api_client.revoked", "api_client", client_id, actor_id, {"reason": reason})
        return self.get_api_client(client_id)

    def authenticate_api_token(self, token: str) -> dict[str, Any]:
        if not token:
            raise WorkspaceError("API token is required")
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        rows = self.connection.execute("SELECT * FROM api_clients WHERE status='active'").fetchall()
        for row in rows:
            if hmac.compare_digest(str(row["token_hash"]), digest):
                return self._decode_api_client(row)
        raise WorkspaceError("invalid or revoked API token")

    @staticmethod
    def api_client_authorized(client: Mapping[str, Any], scope: str, *, project_id: str | None = None) -> bool:
        scopes = set(client.get("scopes") or [])
        scope_allowed = "*" in scopes or scope in scopes or (":" in scope and f"{scope.split(':')[0]}:*" in scopes)
        if not scope_allowed:
            return False
        allowed_projects = set(client.get("project_ids") or [])
        return not project_id or not allowed_projects or project_id in allowed_projects

    def consume_api_rate_limit(self, client_id: str, *, now: datetime | None = None) -> tuple[bool, int]:
        client = self.get_api_client(client_id)
        moment = now or datetime.now(timezone.utc)
        window = moment.replace(second=0, microsecond=0).isoformat().replace("+00:00", "Z")
        with self.connection:
            self.connection.execute(
                "INSERT INTO api_rate_windows(client_id,window_start,request_count) VALUES(?,?,1) ON CONFLICT(client_id,window_start) DO UPDATE SET request_count=request_count+1",
                (client_id, window),
            )
        count = int(self.connection.execute("SELECT request_count FROM api_rate_windows WHERE client_id=? AND window_start=?", (client_id, window)).fetchone()[0])
        remaining = int(client["rate_limit_per_minute"]) - count
        return count <= int(client["rate_limit_per_minute"]), remaining

    def record_api_audit(
        self,
        client_id: str | None,
        actor_id: str,
        method: str,
        route: str,
        response_status: int,
        request_hash: str,
        detail: Mapping[str, Any] | None = None,
        *,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        api_event_id = _id("cgaae")
        with self.connection:
            self.connection.execute(
                "INSERT INTO api_audit_events(api_event_id,client_id,actor_id,method,route,project_id,response_status,request_hash,detail_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (api_event_id, client_id, actor_id, method, route, project_id, int(response_status), request_hash, _json(dict(detail or {})), _utc_now()),
            )
        return self.get_api_audit_event(api_event_id)

    def get_api_audit_event(self, api_event_id: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM api_audit_events WHERE api_event_id=?", (api_event_id,)).fetchone()
        if not row:
            raise WorkspaceError(f"API audit event not found: {api_event_id}")
        item=dict(row); item["detail"]=json.loads(item.pop("detail_json")); return item

    def list_api_audit_events(self, *, client_id: str | None = None, project_id: str | None = None) -> list[dict[str, Any]]:
        query="SELECT * FROM api_audit_events WHERE 1=1"; params: list[Any]=[]
        if client_id:
            query += " AND client_id=?"; params.append(client_id)
        if project_id:
            query += " AND project_id=?"; params.append(project_id)
        query += " ORDER BY created_at,rowid"
        result=[]
        for row in self.connection.execute(query, params):
            item=dict(row); item["detail"]=json.loads(item.pop("detail_json")); result.append(item)
        return result

    def create_publication_artifact(
        self,
        project_id: str,
        *,
        report_type: str,
        export_format: str,
        visibility: str,
        redaction_policy: str,
        content_hash: str,
        content_text: str,
        metadata: Mapping[str, Any] | None = None,
        record_id: str | None = None,
        actor_id: str = "self",
        publication_id: str | None = None,
    ) -> dict[str, Any]:
        self._require_project(project_id, include_deleted=True)
        if record_id:
            record = self._require_record(record_id, include_deleted=True)
            if record["project_id"] != project_id:
                raise WorkspaceError("publication record does not belong to the project")
        publication_id = publication_id or _id("cgpub")
        now = _utc_now()
        with self.connection:
            self.connection.execute(
                "INSERT INTO publication_artifacts(publication_id,project_id,record_id,report_type,format,visibility,redaction_policy,content_hash,content_text,metadata_json,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (publication_id, project_id, record_id, report_type, export_format, visibility, redaction_policy, content_hash, content_text, _json(dict(metadata or {})), actor_id, now),
            )
            self.connection.execute(
                "INSERT INTO publication_events(publication_event_id,publication_id,event_type,actor_id,notes,payload_json,created_at) VALUES(?,?,?,?,?,?,?)",
                (_id("cgpe"), publication_id, "created", actor_id, "", _json({"content_hash": content_hash, "format": export_format}), now),
            )
            self._audit("publication.created", "publication", publication_id, actor_id, {"project_id": project_id, "record_id": record_id, "report_type": report_type, "format": export_format, "visibility": visibility})
        return self.get_publication_artifact(publication_id)

    @staticmethod
    def _decode_publication(row: Mapping[str, Any], *, include_content: bool = True) -> dict[str, Any]:
        item=dict(row); item["metadata"]=json.loads(item.pop("metadata_json"))
        if not include_content:
            item.pop("content_text", None)
        return item

    def get_publication_artifact(self, publication_id: str, *, include_content: bool = True) -> dict[str, Any]:
        row=self.connection.execute("SELECT * FROM publication_artifacts WHERE publication_id=?", (publication_id,)).fetchone()
        if not row:
            raise WorkspaceError(f"publication not found: {publication_id}")
        item=self._decode_publication(row, include_content=include_content)
        item["events"]=[self._decode_publication_event(event) for event in self.connection.execute("SELECT * FROM publication_events WHERE publication_id=? ORDER BY created_at,rowid", (publication_id,))]
        return item

    @staticmethod
    def _decode_publication_event(row: Mapping[str, Any]) -> dict[str, Any]:
        item=dict(row); item["payload"]=json.loads(item.pop("payload_json")); return item

    def list_publication_artifacts(self, project_id: str, *, report_type: str | None = None, visibility: str | None = None, include_content: bool = False) -> list[dict[str, Any]]:
        self._require_project(project_id, include_deleted=True)
        query="SELECT * FROM publication_artifacts WHERE project_id=?"; params: list[Any]=[project_id]
        if report_type:
            query += " AND report_type=?"; params.append(report_type)
        if visibility:
            query += " AND visibility=?"; params.append(visibility)
        query += " ORDER BY created_at,rowid"
        return [self._decode_publication(row, include_content=include_content) for row in self.connection.execute(query, params)]

    def add_publication_event(self, publication_id: str, event_type: str, *, actor_id: str = "self", notes: str = "", payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        self.get_publication_artifact(publication_id, include_content=False)
        if event_type not in {"reviewed", "approved", "published", "withdrawn", "exported"}:
            raise WorkspaceError(f"unsupported publication event: {event_type}")
        event_id=_id("cgpe")
        with self.connection:
            self.connection.execute("INSERT INTO publication_events(publication_event_id,publication_id,event_type,actor_id,notes,payload_json,created_at) VALUES(?,?,?,?,?,?,?)", (event_id,publication_id,event_type,actor_id,notes.strip(),_json(dict(payload or {})),_utc_now()))
            self._audit(f"publication.{event_type}", "publication", publication_id, actor_id, dict(payload or {}))
        return self._decode_publication_event(self.connection.execute("SELECT * FROM publication_events WHERE publication_event_id=?", (event_id,)).fetchone())

    def register_methodology(self, profile_name: str, profile_version: str, content: Mapping[str, Any], *, status: str = "draft", approved_by: str | None = None, effective_at: str | None = None, notes: str = "") -> dict[str, Any]:
        if status not in {"draft", "approved", "deprecated"}:
            raise WorkspaceError(f"unsupported methodology status: {status}")
        methodology_id=_id("cgmeth"); content_hash=_sha(content); now=_utc_now()
        with self.connection:
            self.connection.execute("INSERT INTO methodology_registry(methodology_id,profile_name,profile_version,content_hash,status,approved_by,effective_at,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (methodology_id,profile_name,profile_version,content_hash,status,approved_by,effective_at,notes,now))
            self._audit("methodology.registered", "methodology", methodology_id, approved_by or "self", {"profile_name":profile_name,"profile_version":profile_version,"status":status,"content_hash":content_hash})
        return dict(self.connection.execute("SELECT * FROM methodology_registry WHERE methodology_id=?", (methodology_id,)).fetchone())

    def list_methodologies(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.connection.execute("SELECT * FROM methodology_registry ORDER BY profile_name,profile_version")]

    def declare_schema_deprecation(self, schema_name: str, schema_version: str, *, replacement_version: str | None = None, status: str = "announced", announced_at: str | None = None, sunset_at: str | None = None, migration_notes: str = "", actor_id: str = "self") -> dict[str, Any]:
        if status not in {"announced","deprecated","retired"}:
            raise WorkspaceError(f"unsupported schema deprecation status: {status}")
        deprecation_id=_id("cgsd"); now=_utc_now()
        with self.connection:
            self.connection.execute("INSERT INTO schema_deprecations(deprecation_id,schema_name,schema_version,replacement_version,status,announced_at,sunset_at,migration_notes,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (deprecation_id,schema_name,schema_version,replacement_version,status,announced_at or now,sunset_at,migration_notes,actor_id,now))
            self._audit("schema.deprecation_declared", "schema", f"{schema_name}@{schema_version}", actor_id, {"status":status,"replacement_version":replacement_version,"sunset_at":sunset_at})
        return dict(self.connection.execute("SELECT * FROM schema_deprecations WHERE deprecation_id=?", (deprecation_id,)).fetchone())

    def schema_compatibility(self, schema_name: str, schema_version: str) -> dict[str, Any]:
        row=self.connection.execute("SELECT * FROM schema_deprecations WHERE schema_name=? AND schema_version=?", (schema_name,schema_version)).fetchone()
        if not row:
            return {"schema_name":schema_name,"schema_version":schema_version,"status":"supported","replacement_version":None,"migration_required":False}
        item=dict(row)
        item["migration_required"] = item["status"] in {"deprecated","retired"}
        item["supported"] = item["status"] != "retired"
        return item

    def institutional_diagnostics(self) -> dict[str, Any]:
        health=self.health()
        active_policies=int(self.connection.execute("SELECT COUNT(*) FROM institutional_policies WHERE status='active'").fetchone()[0])
        active_clients=int(self.connection.execute("SELECT COUNT(*) FROM api_clients WHERE status='active'").fetchone()[0])
        publications=int(self.connection.execute("SELECT COUNT(*) FROM publication_artifacts").fetchone()[0])
        overdue_access_reviews=int(self.connection.execute("SELECT COUNT(*) FROM access_reviews WHERE next_review_at IS NOT NULL AND next_review_at < ?", (_utc_now(),)).fetchone()[0])
        return {
            "product_version": __version__,
            "database_integrity": health["integrity"],
            "migration_status": health["migrations"],
            "active_policy_count": active_policies,
            "active_api_client_count": active_clients,
            "publication_count": publications,
            "overdue_access_review_count": overdue_access_reviews,
            "private_by_default": True,
            "api_authentication_required": True,
            "audit_append_only": True,
            "connected_platform": {
                "workflow_count": int(self.connection.execute("SELECT COUNT(*) FROM connected_workflows").fetchone()[0]),
                "artifact_connection_count": int(self.connection.execute("SELECT COUNT(*) FROM artifact_connections").fetchone()[0]),
                "portable_snapshot_count": int(self.connection.execute("SELECT COUNT(*) FROM portable_platform_snapshots").fetchone()[0]),
                "offline_restore_supported": True,
            },
        }

    def write_export(self, payload: Mapping[str, Any], path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(_pretty(payload), encoding="utf-8")
        return output

    def health(self) -> dict[str, Any]:
        integrity = self.connection.execute("PRAGMA integrity_check").fetchone()[0]
        counts = {}
        for table in ("projects", "recovery_records", "record_revisions", "actions", "action_events", "blockers", "reassessments", "retrospectives", "pattern_reviews", "system_changes", "system_change_events", "team_memberships", "facilitated_sessions", "session_participants", "team_perspectives", "facilitated_agreements", "facilitated_agreement_events", "evidence_items", "evidence_events", "evidence_links", "assumptions", "assumption_events", "handoff_artifacts", "handoff_events", "monitoring_snapshots", "monitoring_snapshot_events", "monitoring_reviews", "institutional_policies", "access_reviews", "api_clients", "api_rate_windows", "api_audit_events", "publication_artifacts", "publication_events", "methodology_registry", "schema_deprecations", "connected_workflows", "connected_workflow_steps", "connected_workflow_events", "artifact_connections", "artifact_connection_events", "portable_platform_snapshots", "platform_sync_events", "checkpoints", "reviews", "status_history", "audit_events"):
            try:
                counts[table] = self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.OperationalError:
                counts[table] = None
        return {"database": self.database, "integrity": integrity, "migrations": self.migrations.status(), "counts": counts, "private_by_default": True}


__all__ = [
    "Migration",
    "MigrationManager",
    "SQLiteWorkspaceRepository",
    "WORKSPACE_FORMAT",
    "WorkspaceError",
]
