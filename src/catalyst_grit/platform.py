"""Connected human-systems resilience workflow for Catalyst Grit v2.0.0.

The service joins existing recovery records, plans, checkpoints, learning,
evidence, handoffs, monitoring, and publications without replacing their
source contracts. It records orchestration state and provenance; it does not
score people, predict outcomes, or make automated employment decisions.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence
from uuid import uuid4

from .storage import WorkspaceError
from .version import __version__

PLATFORM_CONTRACT = "catalyst-grit-connected-platform/2.0"
PORTABLE_PLATFORM_FORMAT = "catalyst-grit-portable-platform/2.0"

WORKFLOW_STEPS: tuple[dict[str, Any], ...] = (
    {"key": "setback", "title": "Setback recorded", "review": False},
    {"key": "context", "title": "Context and trigger", "review": False},
    {"key": "conditions_mapping", "title": "Pressure, constraints, supports, and capacity", "review": False},
    {"key": "recovery_assessment", "title": "Recovery assessment", "review": True},
    {"key": "action_plan", "title": "Recovery action plan", "review": False},
    {"key": "checkpoint", "title": "Checkpoint", "review": False},
    {"key": "reassessment", "title": "Reassessment", "review": True},
    {"key": "learning_loop", "title": "Learning loop", "review": True},
    {"key": "system_adaptation", "title": "System adaptation", "review": True},
    {"key": "decision_handoff", "title": "Decision handoff", "review": True},
    {"key": "monitoring_review", "title": "Monitoring and review", "review": True},
    {"key": "publication", "title": "Governed publication or export", "review": True},
)

KNOWN_PRODUCTS = {
    "Catalyst Canvas", "Catalyst Data", "Workbench", "Sustainable Catalyst Lab",
    "Decision Studio", "Knowledge Library", "Research Librarian", "Catalyst Grit", "External",
}


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PortableSnapshotResult:
    metadata: dict[str, Any]
    bundle: dict[str, Any]


class ConnectedPlatformService:
    """Orchestrate the full Catalyst Grit workflow over an existing repository."""

    def __init__(self, repository: Any):
        self.repository = repository

    def create_workflow(self, record_id: str, *, actor_id: str = "self") -> dict[str, Any]:
        record = self.repository.get_record(record_id, include_canonical=True)
        project_id = record["project_id"]
        existing = self.repository.connection.execute(
            "SELECT workflow_id FROM connected_workflows WHERE project_id=? AND record_id=? AND contract_version=?",
            (project_id, record_id, PLATFORM_CONTRACT),
        ).fetchone()
        if existing:
            return self.refresh_workflow(existing["workflow_id"], actor_id=actor_id)
        workflow_id = _id("cgwf")
        now = _utc_now()
        with self.repository.connection:
            self.repository.connection.execute(
                "INSERT INTO connected_workflows(workflow_id,project_id,record_id,contract_version,status,current_step_key,started_by,started_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (workflow_id, project_id, record_id, PLATFORM_CONTRACT, "planned", WORKFLOW_STEPS[0]["key"], actor_id, now, now),
            )
            for ordinal, spec in enumerate(WORKFLOW_STEPS, start=1):
                self.repository.connection.execute(
                    "INSERT INTO connected_workflow_steps(step_id,workflow_id,step_key,ordinal,title,status,output_json,human_review_required,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (_id("cgwfs"), workflow_id, spec["key"], ordinal, spec["title"], "pending", "{}", int(spec["review"]), now),
                )
            self._event(workflow_id, "created", actor_id=actor_id, to_status="planned", payload={"record_id": record_id, "contract": PLATFORM_CONTRACT})
            self.repository._audit("connected_workflow.created", "workflow", workflow_id, actor_id, {"project_id": project_id, "record_id": record_id})
        return self.refresh_workflow(workflow_id, actor_id=actor_id)

    def _event(
        self,
        workflow_id: str,
        event_type: str,
        *,
        actor_id: str,
        step_key: str = "",
        from_status: str | None = None,
        to_status: str | None = None,
        notes: str = "",
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        self.repository.connection.execute(
            "INSERT INTO connected_workflow_events(workflow_event_id,workflow_id,step_key,event_type,from_status,to_status,actor_id,notes,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (_id("cgwfe"), workflow_id, step_key, event_type, from_status, to_status, actor_id, notes, _json(dict(payload or {})), _utc_now()),
        )

    @staticmethod
    def _decode_step(row: Mapping[str, Any]) -> dict[str, Any]:
        item = dict(row)
        item["output"] = json.loads(item.pop("output_json"))
        item["human_review_required"] = bool(item["human_review_required"])
        return item

    @staticmethod
    def _decode_connection(row: Mapping[str, Any]) -> dict[str, Any]:
        item = dict(row)
        item["provenance"] = json.loads(item.pop("provenance_json"))
        return item

    def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        row = self.repository.connection.execute("SELECT * FROM connected_workflows WHERE workflow_id=?", (workflow_id,)).fetchone()
        if not row:
            raise WorkspaceError(f"connected workflow not found: {workflow_id}")
        item = dict(row)
        item["steps"] = [self._decode_step(step) for step in self.repository.connection.execute("SELECT * FROM connected_workflow_steps WHERE workflow_id=? ORDER BY ordinal", (workflow_id,))]
        item["events"] = []
        for event in self.repository.connection.execute("SELECT * FROM connected_workflow_events WHERE workflow_id=? ORDER BY created_at,rowid", (workflow_id,)):
            decoded = dict(event); decoded["payload"] = json.loads(decoded.pop("payload_json")); item["events"].append(decoded)
        item["progress"] = {
            "completed": sum(step["status"] == "completed" for step in item["steps"]),
            "total": len(item["steps"]),
            "percent": round(100 * sum(step["status"] == "completed" for step in item["steps"]) / max(len(item["steps"]), 1), 1),
        }
        item["guardrails"] = self.guardrails()
        return item

    def list_workflows(self, project_id: str, *, status: str | None = None) -> list[dict[str, Any]]:
        self.repository.get_project(project_id, include_deleted=True)
        query = "SELECT workflow_id FROM connected_workflows WHERE project_id=?"; params: list[Any] = [project_id]
        if status:
            query += " AND status=?"; params.append(status)
        query += " ORDER BY updated_at DESC,rowid DESC"
        return [self.get_workflow(row["workflow_id"]) for row in self.repository.connection.execute(query, params)]

    def _evidence_for_steps(self, workflow: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        record_id = str(workflow["record_id"]); project_id = str(workflow["project_id"])
        record = self.repository.get_record(record_id, include_canonical=True)
        canonical = record["canonical"]
        revision = self.repository.get_revision(record["current_revision_id"])
        actions = self.repository.list_actions(record_id)
        checkpoints = self.repository.list_checkpoints(project_id, record_id=record_id)
        reassessments = self.repository.list_reassessments(record_id)
        retrospectives = self.repository.list_retrospectives(record_id)
        system_changes = self.repository.list_system_changes(project_id)
        handoffs = self.repository.list_handoffs(project_id, record_id=record_id, target_product="Decision Studio")
        snapshots = self.repository.list_monitoring_snapshots(project_id, record_id=record_id)
        reviews = self.repository.list_monitoring_reviews(project_id, record_id=record_id)
        publications = self.repository.list_publication_artifacts(project_id, include_content=False)
        context = canonical.get("user_input", {}).get("context", {})
        findings = canonical.get("findings", {})

        def state(exists: bool, *, source_type: str, source_id: str, payload: Mapping[str, Any], review: bool = False, reviewed: bool = False) -> dict[str, Any]:
            if not exists:
                return {"status": "pending", "source_type": "", "source_id": "", "source_hash": "", "output": dict(payload)}
            status = "completed"
            if review and not reviewed:
                status = "needs_review"
            return {"status": status, "source_type": source_type, "source_id": source_id, "source_hash": _sha(payload), "output": dict(payload)}

        completed_checkpoints = [item for item in checkpoints if item.get("status") == "completed"]
        monitoring_reviewed = any(item.get("status") in {"reviewed", "approved"} for item in reviews)
        human_review = canonical.get("human_review", {})
        record_reviewed = human_review.get("status") in {"reviewed"}
        return {
            "setback": state(True, source_type="record_revision", source_id=revision["revision_id"], payload={"record_id": record_id, "revision_id": revision["revision_id"], "content_hash": revision["content_sha256"]}),
            "context": state(bool(context.get("title") and canonical.get("user_input", {}).get("trigger")), source_type="record_revision", source_id=revision["revision_id"], payload={"context": context, "trigger": canonical.get("user_input", {}).get("trigger", {})}),
            "conditions_mapping": state(bool(findings.get("condition_map")), source_type="record_revision", source_id=revision["revision_id"], payload={"condition_map": findings.get("condition_map", {})}),
            "recovery_assessment": state(bool(findings.get("component_scores")), source_type="record_revision", source_id=revision["revision_id"], payload={"recovery_score": findings.get("recovery_score"), "component_scores": findings.get("component_scores", {}), "interpretation": findings.get("interpretation", {})}, review=True, reviewed=record_reviewed),
            "action_plan": state(bool(actions), source_type="action", source_id=actions[0]["action_id"] if actions else "", payload={"action_count": len(actions), "actions": actions}),
            "checkpoint": state(bool(completed_checkpoints), source_type="checkpoint", source_id=completed_checkpoints[-1]["checkpoint_id"] if completed_checkpoints else (checkpoints[0]["checkpoint_id"] if checkpoints else ""), payload={"checkpoint_count": len(checkpoints), "completed_count": len(completed_checkpoints), "checkpoints": checkpoints}),
            "reassessment": state(bool(reassessments), source_type="reassessment", source_id=reassessments[-1]["reassessment_id"] if reassessments else "", payload={"reassessment_count": len(reassessments), "latest": reassessments[-1] if reassessments else None}, review=True, reviewed=bool(reassessments)),
            "learning_loop": state(bool(retrospectives), source_type="retrospective", source_id=retrospectives[-1]["retrospective_id"] if retrospectives else "", payload={"retrospective_count": len(retrospectives), "latest": retrospectives[-1] if retrospectives else None}, review=True, reviewed=bool(retrospectives)),
            "system_adaptation": state(bool(system_changes), source_type="system_change", source_id=system_changes[-1]["system_change_id"] if system_changes else "", payload={"system_change_count": len(system_changes), "latest": system_changes[-1] if system_changes else None}, review=True, reviewed=any(item.get("decision") in {"piloting", "adopt", "revise", "defer", "retire"} for item in system_changes)),
            "decision_handoff": state(bool(handoffs), source_type="handoff", source_id=handoffs[-1]["handoff_id"] if handoffs else "", payload={"handoff_count": len(handoffs), "latest": handoffs[-1] if handoffs else None}, review=True, reviewed=bool(handoffs) and handoffs[-1].get("validation_state") == "valid"),
            "monitoring_review": state(bool(snapshots), source_type="monitoring_snapshot", source_id=snapshots[-1]["snapshot_id"] if snapshots else "", payload={"snapshot_count": len(snapshots), "review_count": len(reviews), "latest_snapshot": snapshots[-1] if snapshots else None}, review=True, reviewed=monitoring_reviewed),
            "publication": state(bool(publications), source_type="publication", source_id=publications[-1]["publication_id"] if publications else "", payload={"publication_count": len(publications), "latest": publications[-1] if publications else None}, review=True, reviewed=any(item.get("visibility") in {"internal", "public"} for item in publications)),
        }

    def refresh_workflow(self, workflow_id: str, *, actor_id: str = "self") -> dict[str, Any]:
        workflow = self.get_workflow(workflow_id)
        evidence = self._evidence_for_steps(workflow)
        now = _utc_now()
        with self.repository.connection:
            for current in workflow["steps"]:
                next_item = evidence[current["step_key"]]
                next_status = next_item["status"]
                if current["reviewed_at"] and next_status == "needs_review":
                    next_status = "completed"
                changed = any((
                    current["status"] != next_status,
                    current["source_hash"] != next_item["source_hash"],
                    current["source_id"] != next_item["source_id"],
                ))
                if changed:
                    self.repository.connection.execute(
                        "UPDATE connected_workflow_steps SET status=?,source_type=?,source_id=?,source_hash=?,output_json=?,updated_at=? WHERE step_id=?",
                        (next_status, next_item["source_type"], next_item["source_id"], next_item["source_hash"], _json(next_item["output"]), now, current["step_id"]),
                    )
                    self._event(workflow_id, "step_changed", actor_id=actor_id, step_key=current["step_key"], from_status=current["status"], to_status=next_status, payload={"source_type": next_item["source_type"], "source_id": next_item["source_id"], "source_hash": next_item["source_hash"]})
            refreshed = [self._decode_step(row) for row in self.repository.connection.execute("SELECT * FROM connected_workflow_steps WHERE workflow_id=? ORDER BY ordinal", (workflow_id,))]
            first_incomplete = next((step for step in refreshed if step["status"] != "completed"), None)
            if first_incomplete is None:
                next_workflow_status = "completed"; current_step = WORKFLOW_STEPS[-1]["key"]; completed_at = now
            elif first_incomplete["status"] == "needs_review":
                next_workflow_status = "needs_review"; current_step = first_incomplete["step_key"]; completed_at = None
            elif first_incomplete["status"] == "blocked":
                next_workflow_status = "blocked"; current_step = first_incomplete["step_key"]; completed_at = None
            else:
                next_workflow_status = "active"; current_step = first_incomplete["step_key"]; completed_at = None
            old_status = workflow["status"]
            self.repository.connection.execute("UPDATE connected_workflows SET status=?,current_step_key=?,updated_at=?,completed_at=? WHERE workflow_id=?", (next_workflow_status, current_step, now, completed_at, workflow_id))
            self._event(workflow_id, "completed" if next_workflow_status == "completed" and old_status != "completed" else "refreshed", actor_id=actor_id, from_status=old_status, to_status=next_workflow_status, payload={"current_step_key": current_step})
        return self.get_workflow(workflow_id)

    def review_step(self, workflow_id: str, step_key: str, *, reviewer_id: str, notes: str = "") -> dict[str, Any]:
        row = self.repository.connection.execute("SELECT * FROM connected_workflow_steps WHERE workflow_id=? AND step_key=?", (workflow_id, step_key)).fetchone()
        if not row:
            raise WorkspaceError(f"workflow step not found: {step_key}")
        if not row["human_review_required"]:
            raise WorkspaceError("this workflow step does not require human review")
        if row["status"] == "pending":
            raise WorkspaceError("a step cannot be reviewed before source evidence exists")
        now = _utc_now()
        with self.repository.connection:
            self.repository.connection.execute("UPDATE connected_workflow_steps SET status='completed',reviewed_by=?,reviewed_at=?,updated_at=? WHERE step_id=?", (reviewer_id, now, now, row["step_id"]))
            self._event(workflow_id, "reviewed", actor_id=reviewer_id, step_key=step_key, from_status=row["status"], to_status="completed", notes=notes)
            self.repository._audit("connected_workflow.step_reviewed", "workflow", workflow_id, reviewer_id, {"step_key": step_key, "notes": notes})
        return self.refresh_workflow(workflow_id, actor_id=reviewer_id)

    def connect_artifacts(
        self,
        project_id: str,
        *,
        source_product: str,
        source_artifact_type: str,
        source_artifact_id: str,
        source_version: str,
        source_hash: str,
        target_product: str,
        target_artifact_type: str,
        target_artifact_id: str,
        target_version: str,
        target_hash: str,
        relation: str = "informs",
        provenance: Sequence[Mapping[str, Any] | str] | None = None,
        actor_id: str = "self",
    ) -> dict[str, Any]:
        self.repository.get_project(project_id, include_deleted=True)
        if source_product not in KNOWN_PRODUCTS or target_product not in KNOWN_PRODUCTS:
            raise WorkspaceError("unsupported platform product")
        if relation not in {"informs","supports","challenges","derived_from","supersedes","monitors","publishes","hands_off_to"}:
            raise WorkspaceError("unsupported artifact connection relation")
        required = (source_artifact_type, source_artifact_id, source_version, source_hash, target_artifact_type, target_artifact_id, target_version, target_hash)
        if not all(str(value).strip() for value in required):
            raise WorkspaceError("artifact connection identity and hashes are required")
        connection_id = _id("cgconn"); now = _utc_now()
        with self.repository.connection:
            self.repository.connection.execute(
                "INSERT INTO artifact_connections(connection_id,project_id,source_product,source_artifact_type,source_artifact_id,source_version,source_hash,target_product,target_artifact_type,target_artifact_id,target_version,target_hash,relation,validation_state,provenance_json,created_by,created_at,last_checked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (connection_id, project_id, source_product, source_artifact_type, source_artifact_id, source_version, source_hash, target_product, target_artifact_type, target_artifact_id, target_version, target_hash, relation, "valid", _json(list(provenance or [])), actor_id, now, now),
            )
            self.repository.connection.execute("INSERT INTO artifact_connection_events(connection_event_id,connection_id,event_type,from_state,to_state,actor_id,notes,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (_id("cgce"), connection_id, "created", None, "valid", actor_id, "", _json({"source_hash": source_hash, "target_hash": target_hash}), now))
            self.repository._audit("artifact_connection.created", "artifact_connection", connection_id, actor_id, {"project_id": project_id, "relation": relation})
        return self.get_connection(connection_id)

    def get_connection(self, connection_id: str) -> dict[str, Any]:
        row = self.repository.connection.execute("SELECT * FROM artifact_connections WHERE connection_id=?", (connection_id,)).fetchone()
        if not row:
            raise WorkspaceError(f"artifact connection not found: {connection_id}")
        item = self._decode_connection(row); item["events"] = []
        for event in self.repository.connection.execute("SELECT * FROM artifact_connection_events WHERE connection_id=? ORDER BY created_at,rowid", (connection_id,)):
            decoded = dict(event); decoded["payload"] = json.loads(decoded.pop("payload_json")); item["events"].append(decoded)
        return item

    def list_connections(self, project_id: str, *, validation_state: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT connection_id FROM artifact_connections WHERE project_id=?"; params: list[Any] = [project_id]
        if validation_state:
            query += " AND validation_state=?"; params.append(validation_state)
        query += " ORDER BY created_at,rowid"
        return [self.get_connection(row["connection_id"]) for row in self.repository.connection.execute(query, params)]

    def validate_connection(self, connection_id: str, *, source_hash: str | None = None, target_hash: str | None = None, actor_id: str = "self", notes: str = "") -> dict[str, Any]:
        current = self.get_connection(connection_id)
        next_state = "valid"
        if source_hash is not None and source_hash != current["source_hash"]:
            next_state = "conflict"
        if target_hash is not None and target_hash != current["target_hash"]:
            next_state = "conflict"
        event_type = "validated" if next_state == "valid" else "conflict_recorded"
        now = _utc_now()
        with self.repository.connection:
            self.repository.connection.execute("UPDATE artifact_connections SET validation_state=?,last_checked_at=? WHERE connection_id=?", (next_state, now, connection_id))
            self.repository.connection.execute("INSERT INTO artifact_connection_events(connection_event_id,connection_id,event_type,from_state,to_state,actor_id,notes,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (_id("cgce"), connection_id, event_type, current["validation_state"], next_state, actor_id, notes, _json({"supplied_source_hash": source_hash, "supplied_target_hash": target_hash}), now))
        return self.get_connection(connection_id)

    def record_sync_event(self, project_id: str, connector: str, *, direction: str, status: str, artifact_count: int = 0, source_cursor: str = "", target_cursor: str = "", detail: Mapping[str, Any] | None = None, actor_id: str = "self") -> dict[str, Any]:
        if direction not in {"inbound","outbound","bidirectional"} or status not in {"planned","completed","partial","failed","conflict"}:
            raise WorkspaceError("unsupported sync direction or status")
        event_id = _id("cgsync")
        with self.repository.connection:
            self.repository.connection.execute("INSERT INTO platform_sync_events(sync_event_id,project_id,connector,direction,status,source_cursor,target_cursor,artifact_count,detail_json,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (event_id, project_id, connector.strip(), direction, status, source_cursor, target_cursor, max(0, int(artifact_count)), _json(dict(detail or {})), actor_id, _utc_now()))
        row = self.repository.connection.execute("SELECT * FROM platform_sync_events WHERE sync_event_id=?", (event_id,)).fetchone()
        item = dict(row); item["detail"] = json.loads(item.pop("detail_json")); return item

    def list_sync_events(self, project_id: str) -> list[dict[str, Any]]:
        result=[]
        for row in self.repository.connection.execute("SELECT * FROM platform_sync_events WHERE project_id=? ORDER BY created_at,rowid", (project_id,)):
            item=dict(row); item["detail"]=json.loads(item.pop("detail_json")); result.append(item)
        return result

    def platform_overview(self, project_id: str) -> dict[str, Any]:
        project = self.repository.get_project(project_id, include_deleted=True)
        workflows = self.list_workflows(project_id)
        connections = self.list_connections(project_id)
        handoffs = self.repository.list_handoffs(project_id)
        overview = {
            "contract": PLATFORM_CONTRACT,
            "version": __version__,
            "project": {"project_id": project_id, "title": project["title"], "visibility": project["visibility"]},
            "workflow_count": len(workflows),
            "workflow_status_counts": {status: sum(item["status"] == status for item in workflows) for status in ("planned","active","needs_review","blocked","completed","archived")},
            "workflow_progress": [{"workflow_id": item["workflow_id"], "record_id": item["record_id"], "status": item["status"], "current_step_key": item["current_step_key"], "progress": item["progress"]} for item in workflows],
            "artifact_graph": {"connection_count": len(connections), "valid_count": sum(item["validation_state"] == "valid" for item in connections), "conflict_count": sum(item["validation_state"] == "conflict" for item in connections), "connections": connections},
            "handoff_count": len(handoffs),
            "monitoring": self.repository.project_monitoring_dashboard(project_id),
            "governance": {"private_by_default": True, "human_review_required": True, "individual_ranking_allowed": False, "diagnosis_allowed": False, "automated_eligibility_allowed": False},
            "sync_events": self.list_sync_events(project_id),
            "generated_at": _utc_now(),
        }
        overview["summary_hash"] = _sha(overview)
        return overview

    def create_portable_snapshot(self, project_id: str, *, record_id: str | None = None, actor_id: str = "self") -> PortableSnapshotResult:
        workspace = self.repository.export_project(project_id)
        workflows = self.list_workflows(project_id)
        connections = self.list_connections(project_id)
        sync_events = self.list_sync_events(project_id)
        payload = {
            "format": PORTABLE_PLATFORM_FORMAT,
            "product_version": __version__,
            "created_at": _utc_now(),
            "project_id": project_id,
            "record_id": record_id,
            "workspace": workspace,
            "connected_workflows": workflows,
            "artifact_connections": connections,
            "sync_events": sync_events,
            "recovery_instructions": {"operation": "workspace-import", "network_required": False, "verify_before_restore": True},
            "guardrails": self.guardrails(),
        }
        bundle_hash = _sha(payload)
        bundle = dict(payload); bundle["bundle_hash"] = bundle_hash
        snapshot_id = _id("cgps"); now = _utc_now()
        with self.repository.connection:
            self.repository.connection.execute("INSERT INTO portable_platform_snapshots(snapshot_id,project_id,record_id,format,bundle_hash,bundle_json,verification_state,created_by,created_at,verified_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (snapshot_id, project_id, record_id, PORTABLE_PLATFORM_FORMAT, bundle_hash, _json(bundle), "verified", actor_id, now, now))
            self.repository._audit("portable_snapshot.created", "portable_snapshot", snapshot_id, actor_id, {"project_id": project_id, "bundle_hash": bundle_hash})
        metadata = self.get_portable_snapshot(snapshot_id, include_bundle=False)
        return PortableSnapshotResult(metadata=metadata, bundle=bundle)

    def get_portable_snapshot(self, snapshot_id: str, *, include_bundle: bool = True) -> dict[str, Any]:
        row = self.repository.connection.execute("SELECT * FROM portable_platform_snapshots WHERE snapshot_id=?", (snapshot_id,)).fetchone()
        if not row:
            raise WorkspaceError(f"portable snapshot not found: {snapshot_id}")
        item = dict(row)
        bundle = json.loads(item.pop("bundle_json"))
        if include_bundle: item["bundle"] = bundle
        return item

    def list_portable_snapshots(self, project_id: str) -> list[dict[str, Any]]:
        return [self.get_portable_snapshot(row["snapshot_id"], include_bundle=False) for row in self.repository.connection.execute("SELECT snapshot_id FROM portable_platform_snapshots WHERE project_id=? ORDER BY created_at,rowid", (project_id,))]

    @staticmethod
    def verify_portable_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
        supplied = str(bundle.get("bundle_hash") or "")
        unsigned = dict(bundle); unsigned.pop("bundle_hash", None)
        calculated = _sha(unsigned)
        return {"format": bundle.get("format"), "supplied_hash": supplied, "calculated_hash": calculated, "verified": bool(supplied and supplied == calculated), "network_required": False}

    def restore_portable_bundle(self, bundle: Mapping[str, Any], *, actor_id: str = "self", project_id: str | None = None) -> dict[str, Any]:
        verification = self.verify_portable_bundle(bundle)
        if not verification["verified"]:
            raise WorkspaceError("portable platform bundle hash verification failed")
        if bundle.get("format") != PORTABLE_PLATFORM_FORMAT:
            raise WorkspaceError("unsupported portable platform format")
        imported = self.repository.import_payload(bundle["workspace"], project_id=project_id, actor_id=actor_id)
        target_project = imported["project_id"]
        records = self.repository.list_records(target_project, include_archived=True)
        restored_workflows = []
        for record in records:
            restored_workflows.append(self.create_workflow(record["record_id"], actor_id=actor_id))
        self.record_sync_event(target_project, "portable_restore", direction="inbound", status="completed", artifact_count=len(records), detail={"source_bundle_hash": verification["calculated_hash"]}, actor_id=actor_id)
        return {"verification": verification, "import": imported, "restored_workflow_ids": [item["workflow_id"] for item in restored_workflows], "offline_restore": True}

    def diagnostics(self) -> dict[str, Any]:
        counts = {}
        for table in ("connected_workflows","connected_workflow_steps","connected_workflow_events","artifact_connections","artifact_connection_events","portable_platform_snapshots","platform_sync_events"):
            counts[table] = int(self.repository.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        return {"contract": PLATFORM_CONTRACT, "version": __version__, "database_integrity": self.repository.health()["integrity"], "migration_status": self.repository.migrations.status(), "counts": counts, "portable_offline_supported": True, "public_demo_persistent": False, "guardrails": self.guardrails()}

    @staticmethod
    def guardrails() -> list[str]:
        return [
            "Structured reflection and recovery planning only; not mental-health diagnosis or professional care.",
            "No character, personality, employee-resilience, or performance ranking.",
            "No automated employment, eligibility, promotion, discipline, or benefit decisions.",
            "Human review is required before institutional interpretation, publication, or cross-product action.",
            "Private-by-default persistence, provenance-preserving connections, and explicit consent boundaries remain mandatory.",
        ]


__all__ = ["ConnectedPlatformService", "PLATFORM_CONTRACT", "PORTABLE_PLATFORM_FORMAT", "PortableSnapshotResult", "WORKFLOW_STEPS"]
