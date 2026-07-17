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
                    self.connection.execute(
                        "INSERT INTO actions(action_id,record_id,revision_id,source_section,ordinal,title,status,owner,target_date,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (_id("cga"), record_id, revision_id, section, ordinal, str(action.get("title", "")), str(action.get("status", "planned")), action.get("owner"), action.get("target_date"), _utc_now()),
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

    def list_actions(self, record_id: str, *, revision_number: int | None = None) -> list[dict[str, Any]]:
        record = self._require_record(record_id, include_deleted=True)
        revision_id = record["current_revision_id"]
        if revision_number is not None:
            row = self.connection.execute("SELECT revision_id FROM record_revisions WHERE record_id=? AND revision_number=?", (record_id, revision_number)).fetchone()
            if not row:
                raise WorkspaceError("revision not found")
            revision_id = row["revision_id"]
        return [dict(row) for row in self.connection.execute("SELECT * FROM actions WHERE revision_id=? ORDER BY source_section,ordinal", (revision_id,))]

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
            "checkpoints": self.list_checkpoints(project["project_id"], record_id=record_id),
            "reviews": self.list_reviews(record_id),
            "status_history": self.status_history("record", record_id),
            "audit_events": self.audit_log(entity_id=record_id),
        }

    def export_project(self, project_id: str) -> dict[str, Any]:
        project = self.get_project(project_id, include_deleted=True)
        records = self.list_records(project_id, include_archived=True, include_deleted=True)
        return {"format": WORKSPACE_FORMAT, "exported_at": _utc_now(), "product_version": __version__, "project": project, "records": [self.export_record(item["record_id"]) for item in records]}

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
        return {"project_id": target_project, "imported": imported}

    def write_export(self, payload: Mapping[str, Any], path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(_pretty(payload), encoding="utf-8")
        return output

    def health(self) -> dict[str, Any]:
        integrity = self.connection.execute("PRAGMA integrity_check").fetchone()[0]
        counts = {}
        for table in ("projects", "recovery_records", "record_revisions", "actions", "checkpoints", "reviews", "status_history", "audit_events"):
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
