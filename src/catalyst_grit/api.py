"""Dependency-free institutional API service contract for Catalyst Grit v2.0.0."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from .publication import PublicationService
from .platform import ConnectedPlatformService
from .version import __version__

API_CONTRACT = "catalyst-grit-api/2.0"


@dataclass(frozen=True)
class APIResponse:
    status: int
    body: Any
    headers: dict[str, str]


class InstitutionalAPI:
    """Route authenticated API calls without binding the domain to a web framework."""

    def __init__(self, repository: Any):
        self.repository = repository

    @staticmethod
    def _project_from_path(parts: list[str]) -> str | None:
        if len(parts) > 2 and parts[1] == "projects":
            return parts[2]
        return None

    def _response(self, status: int, body: Any, *, client: Mapping[str, Any] | None = None, remaining: int | None = None) -> APIResponse:
        headers = {
            "Content-Type": "application/json",
            "X-Catalyst-Grit-API": API_CONTRACT,
            "X-Catalyst-Grit-Version": __version__,
        }
        if client is not None:
            headers["X-RateLimit-Limit"] = str(client["rate_limit_per_minute"])
        if remaining is not None:
            headers["X-RateLimit-Remaining"] = str(max(remaining, 0))
        return APIResponse(status, body, headers)

    def handle(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        body: Mapping[str, Any] | None = None,
        query: Mapping[str, Any] | None = None,
        actor_id: str = "api",
    ) -> APIResponse:
        method = method.upper().strip()
        clean_path = "/" + path.strip("/")
        parts = clean_path.strip("/").split("/")
        request_hash = hashlib.sha256(json.dumps({"method": method, "path": clean_path, "body": body or {}, "query": query or {}}, sort_keys=True).encode()).hexdigest()
        if clean_path in {"/v1/health", "/v2/health"} and method == "GET":
            service = ConnectedPlatformService(self.repository)
            return self._response(200, {"contract": API_CONTRACT, "version": __version__, "health": self.repository.institutional_diagnostics(), "connected_platform": service.diagnostics()})
        try:
            client = self.repository.authenticate_api_token(token or "")
        except Exception as exc:
            self.repository.record_api_audit(None, actor_id, method, clean_path, 401, request_hash, {"error": str(exc)})
            return self._response(401, {"error": "unauthorized", "message": "A valid active API token is required."})
        allowed, remaining = self.repository.consume_api_rate_limit(client["client_id"])
        if not allowed:
            self.repository.record_api_audit(client["client_id"], actor_id, method, clean_path, 429, request_hash, {"rate_limited": True})
            return self._response(429, {"error": "rate_limited"}, client=client, remaining=0)
        project_id = self._project_from_path(parts)

        def require(scope: str, project: str | None = None) -> APIResponse | None:
            if not self.repository.api_client_authorized(client, scope, project_id=project):
                self.repository.record_api_audit(client["client_id"], actor_id, method, clean_path, 403, request_hash, {"scope": scope, "project_id": project})
                return self._response(403, {"error": "forbidden", "required_scope": scope}, client=client, remaining=remaining)
            return None

        try:
            result: Any
            scope = ""
            if method == "GET" and len(parts) == 4 and parts[:2] == ["v1", "projects"] and parts[3] == "records":
                scope = "records:read"; denied = require(scope, project_id)
                if denied: return denied
                result = self.repository.list_records(project_id, include_archived=True)
            elif method == "GET" and len(parts) == 3 and parts[:2] == ["v1", "records"]:
                scope = "records:read"; record = self.repository.get_record(parts[2], include_canonical=True); project_id = record["project_id"]; denied = require(scope, project_id)
                if denied: return denied
                result = record
            elif method == "GET" and len(parts) == 4 and parts[:2] == ["v1", "records"] and parts[3] == "revisions":
                scope = "revisions:read"; record = self.repository.get_record(parts[2]); project_id = record["project_id"]; denied = require(scope, project_id)
                if denied: return denied
                result = self.repository.list_revisions(parts[2])
            elif method == "GET" and len(parts) == 4 and parts[:2] == ["v1", "records"] and parts[3] == "actions":
                scope = "actions:read"; record = self.repository.get_record(parts[2]); project_id = record["project_id"]; denied = require(scope, project_id)
                if denied: return denied
                result = self.repository.list_actions(parts[2])
            elif method == "GET" and len(parts) == 4 and parts[:2] == ["v1", "projects"] and parts[3] == "checkpoints":
                scope = "checkpoints:read"; denied = require(scope, project_id)
                if denied: return denied
                result = self.repository.list_checkpoints(project_id)
            elif method == "GET" and len(parts) == 4 and parts[:2] == ["v1", "records"] and parts[3] == "reviews":
                scope = "reviews:read"; record = self.repository.get_record(parts[2]); project_id = record["project_id"]; denied = require(scope, project_id)
                if denied: return denied
                result = self.repository.list_reviews(parts[2])
            elif method == "GET" and len(parts) == 4 and parts[:2] == ["v1", "projects"] and parts[3] == "evidence":
                scope = "evidence:read"; denied = require(scope, project_id)
                if denied: return denied
                result = self.repository.list_evidence(project_id)
            elif method == "GET" and len(parts) == 4 and parts[:2] == ["v1", "projects"] and parts[3] == "patterns":
                scope = "patterns:read"; denied = require(scope, project_id)
                if denied: return denied
                result = self.repository.detect_project_patterns(project_id, minimum_occurrences=1, include_singletons=True)
            elif method == "GET" and len(parts) == 4 and parts[:2] == ["v1", "projects"] and parts[3] == "monitoring":
                scope = "monitoring:read"; denied = require(scope, project_id)
                if denied: return denied
                result = self.repository.project_monitoring_dashboard(project_id)
            elif method == "GET" and len(parts) == 4 and parts[:2] == ["v1", "projects"] and parts[3] == "handoffs":
                scope = "handoffs:read"; denied = require(scope, project_id)
                if denied: return denied
                result = self.repository.list_handoffs(project_id)
            elif method == "GET" and len(parts) == 4 and parts[:2] == ["v1", "projects"] and parts[3] == "audit":
                scope = "audit:read"; denied = require(scope, project_id)
                if denied: return denied
                result = self.repository.audit_log("project", project_id) + self.repository.list_api_audit_events(project_id=project_id)
            elif method == "GET" and len(parts) == 4 and parts[:2] == ["v2", "projects"] and parts[3] == "platform":
                scope = "platform:read"; denied = require(scope, project_id)
                if denied: return denied
                result = ConnectedPlatformService(self.repository).platform_overview(project_id)
            elif method == "GET" and len(parts) == 4 and parts[:2] == ["v2", "projects"] and parts[3] == "workflows":
                scope = "platform:read"; denied = require(scope, project_id)
                if denied: return denied
                result = ConnectedPlatformService(self.repository).list_workflows(project_id)
            elif method == "GET" and len(parts) == 3 and parts[:2] == ["v2", "workflows"]:
                scope = "platform:read"; workflow = ConnectedPlatformService(self.repository).get_workflow(parts[2]); project_id = workflow["project_id"]; denied = require(scope, project_id)
                if denied: return denied
                result = workflow
            elif method == "POST" and clean_path == "/v2/workflows":
                record_id = str((body or {}).get("record_id") or ""); record = self.repository.get_record(record_id); project_id = record["project_id"]
                scope = "platform:write"; denied = require(scope, project_id)
                if denied: return denied
                result = ConnectedPlatformService(self.repository).create_workflow(record_id, actor_id=client["client_id"])
            elif method == "POST" and len(parts) == 5 and parts[:2] == ["v2", "workflows"] and parts[3] == "steps":
                workflow = ConnectedPlatformService(self.repository).get_workflow(parts[2]); project_id = workflow["project_id"]
                scope = "platform:review"; denied = require(scope, project_id)
                if denied: return denied
                result = ConnectedPlatformService(self.repository).review_step(parts[2], parts[4], reviewer_id=client["client_id"], notes=str((body or {}).get("notes") or ""))
            elif method == "POST" and len(parts) == 4 and parts[:2] == ["v2", "projects"] and parts[3] == "portable-snapshots":
                project_id = parts[2]; scope = "platform:export"; denied = require(scope, project_id)
                if denied: return denied
                generated = ConnectedPlatformService(self.repository).create_portable_snapshot(project_id, record_id=(body or {}).get("record_id"), actor_id=client["client_id"])
                result = {"metadata": generated.metadata, "bundle": generated.bundle}
            elif method == "GET" and len(parts) == 4 and parts[:2] == ["v2", "projects"] and parts[3] == "connections":
                scope = "platform:read"; denied = require(scope, project_id)
                if denied: return denied
                result = ConnectedPlatformService(self.repository).list_connections(project_id)
            elif method == "POST" and clean_path == "/v1/publications":
                scope = "publications:write"; project_id = str((body or {}).get("project_id") or ""); denied = require(scope, project_id)
                if denied: return denied
                service = PublicationService(self.repository)
                generated = service.generate(
                    str((body or {}).get("report_type") or "recovery_brief"),
                    project_id=project_id,
                    record_id=(body or {}).get("record_id"),
                    export_format=str((body or {}).get("format") or "json"),
                    redaction_policy=str((body or {}).get("redaction_policy") or "none"),
                    actor_id=client["client_id"],
                )
                result = {"publication": generated.publication, "content": generated.content, "mime_type": generated.mime_type}
            else:
                self.repository.record_api_audit(client["client_id"], actor_id, method, clean_path, 404, request_hash, {})
                return self._response(404, {"error": "not_found"}, client=client, remaining=remaining)
            self.repository.record_api_audit(client["client_id"], actor_id, method, clean_path, 200, request_hash, {"scope": scope}, project_id=project_id)
            return self._response(200, {"contract": API_CONTRACT, "data": result}, client=client, remaining=remaining)
        except Exception as exc:
            self.repository.record_api_audit(client["client_id"], actor_id, method, clean_path, 400, request_hash, {"error": str(exc)}, project_id=project_id)
            return self._response(400, {"error": "request_failed", "message": str(exc)}, client=client, remaining=remaining)


__all__ = ["API_CONTRACT", "APIResponse", "InstitutionalAPI"]
