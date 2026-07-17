"""Publication, redaction, and portable export services for Catalyst Grit v1.9.0."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import csv
import hashlib
import html
import io
import json
from pathlib import Path
import zipfile
from typing import Any, Mapping, Sequence

from .version import __version__

PUBLICATION_FORMAT = "catalyst-grit-publication/1.0"
PUBLICATION_BUNDLE_FORMAT = "catalyst-grit-publication-bundle/1.0"
REPORT_TYPES = {
    "recovery_brief",
    "facilitated_review_brief",
    "action_plan",
    "learning_loop_report",
    "adaptation_proposal",
    "monitoring_summary",
    "decision_studio_handoff",
}
EXPORT_FORMATS = {"json", "jsonld", "markdown", "html", "csv", "pdf_request", "bundle"}
REDACTION_POLICIES = {
    "none": {"visibility": "private", "remove_keys": [], "mask_keys": []},
    "internal": {
        "visibility": "internal",
        "remove_keys": ["token_hash", "source_uri", "private_notes", "raw_content"],
        "mask_keys": ["actor_id", "owner_id", "reviewer_id", "member_key", "created_by"],
    },
    "public": {
        "visibility": "public",
        "remove_keys": [
            "token_hash", "source_uri", "private_notes", "raw_content", "user_input",
            "team_perspectives", "audit_events", "api_audit_events", "provenance",
        ],
        "mask_keys": [
            "actor_id", "owner_id", "reviewer_id", "member_key", "created_by",
            "display_name", "facilitator_key", "contributor_label",
        ],
    },
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _pretty(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _mask(value: Any) -> str:
    if value in (None, ""):
        return ""
    return f"subject-{hashlib.sha256(str(value).encode()).hexdigest()[:12]}"


def apply_redaction(value: Any, policy: str = "none", *, extra_remove_keys: Sequence[str] | None = None) -> Any:
    """Apply deterministic structural redaction without mutating the source value."""
    if policy not in REDACTION_POLICIES:
        raise ValueError(f"unsupported redaction policy: {policy}")
    rules = REDACTION_POLICIES[policy]
    remove = set(rules["remove_keys"]) | set(extra_remove_keys or [])
    mask = set(rules["mask_keys"])

    def visit(item: Any) -> Any:
        if isinstance(item, Mapping):
            result: dict[str, Any] = {}
            for key, child in item.items():
                if key in remove:
                    continue
                if key in mask:
                    result[key] = _mask(child)
                elif key == "sharing_scope" and policy == "public" and child != "shared":
                    result[key] = "withheld"
                else:
                    result[key] = visit(child)
            return result
        if isinstance(item, list):
            return [visit(child) for child in item]
        return deepcopy(item)

    return visit(value)


def _title(text: str) -> str:
    return text.replace("_", " ").strip().title()


def _markdown(value: Any, level: int = 1) -> str:
    lines: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            heading = "#" * min(level, 6)
            if isinstance(child, (Mapping, list)):
                lines.append(f"{heading} {_title(str(key))}")
                lines.append("")
                lines.append(_markdown(child, level + 1).rstrip())
            else:
                lines.append(f"- **{_title(str(key))}:** {child if child not in (None, '') else '—'}")
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, Mapping):
                lines.append(_markdown(child, level).rstrip())
            else:
                lines.append(f"- {child}")
    else:
        lines.append(str(value))
    return "\n".join(lines).strip() + "\n"


def _html(value: Any) -> str:
    def render(item: Any, level: int = 1) -> str:
        if isinstance(item, Mapping):
            chunks = []
            for key, child in item.items():
                if isinstance(child, (Mapping, list)):
                    heading = min(level + 1, 6)
                    chunks.append(f"<section><h{heading}>{html.escape(_title(str(key)))}</h{heading}>{render(child, level + 1)}</section>")
                else:
                    chunks.append(f"<p><strong>{html.escape(_title(str(key)))}:</strong> {html.escape(str(child if child not in (None, '') else '—'))}</p>")
            return "".join(chunks)
        if isinstance(item, list):
            return "<ul>" + "".join(f"<li>{render(child, level) if isinstance(child, (Mapping, list)) else html.escape(str(child))}</li>" for child in item) + "</ul>"
        return html.escape(str(item))

    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>Catalyst Grit Publication</title></head><body>"
        f"<main>{render(value)}</main></body></html>\n"
    )


def _flatten_rows(value: Mapping[str, Any]) -> list[dict[str, Any]]:
    report = value.get("report") or {}
    candidates = []
    for key in ("actions", "agreements", "evidence", "patterns", "monitoring_points", "system_changes"):
        rows = report.get(key)
        if isinstance(rows, list) and rows:
            for row in rows:
                if isinstance(row, Mapping):
                    flat: dict[str, Any] = {"table": key}
                    for field, field_value in row.items():
                        if isinstance(field_value, (Mapping, list)):
                            flat[field] = _canonical_json(field_value)
                        else:
                            flat[field] = field_value
                    candidates.append(flat)
            if candidates:
                return candidates
    return [{"table": "summary", "publication_id": value.get("publication_id", ""), "report_type": value.get("report_type", ""), "content_hash": value.get("content_hash", "")}]


def render_publication(publication: Mapping[str, Any], export_format: str) -> tuple[str, str]:
    """Render a publication to a textual format and MIME type."""
    if export_format == "json":
        return _pretty(publication), "application/json"
    if export_format == "jsonld":
        linked = {
            "@context": {
                "cg": "https://sustainablecatalyst.com/ns/catalyst-grit#",
                "schema": "https://schema.org/",
                "reportType": "cg:reportType",
                "contentHash": "cg:contentHash",
            },
            "@type": "cg:RecoveryPublication",
            **deepcopy(dict(publication)),
        }
        return _pretty(linked), "application/ld+json"
    if export_format == "markdown":
        return _markdown(publication), "text/markdown"
    if export_format == "html":
        return _html(publication), "text/html"
    if export_format == "csv":
        rows = _flatten_rows(publication)
        fields = sorted({key for row in rows for key in row})
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
        return stream.getvalue(), "text/csv"
    if export_format == "pdf_request":
        request = {
            "contract": "sustainable-catalyst-publication-request/1.0",
            "product": "Catalyst Grit",
            "product_version": __version__,
            "source_publication": publication,
            "requested_output": "pdf",
            "rendering_layer": "Sustainable Catalyst publication layer",
            "status": "ready_for_rendering",
        }
        return _pretty(request), "application/vnd.sustainable-catalyst.publication-request+json"
    raise ValueError(f"unsupported textual export format: {export_format}")


@dataclass(frozen=True)
class PublicationResult:
    publication: dict[str, Any]
    content: str
    mime_type: str


class PublicationService:
    """Build governed reports from a Catalyst Grit repository."""

    def __init__(self, repository: Any):
        self.repository = repository

    def _project_context(self, project_id: str) -> dict[str, Any]:
        project = self.repository.get_project(project_id, include_deleted=True)
        return {
            "project": project,
            "evidence": self.repository.list_evidence(project_id),
            "assumptions": self.repository.list_assumptions(project_id),
            "patterns": self.repository.detect_project_patterns(project_id, minimum_occurrences=1, include_singletons=True),
            "system_changes": self.repository.list_system_changes(project_id),
            "monitoring": self.repository.project_monitoring_dashboard(project_id),
        }

    def build_report(self, report_type: str, *, project_id: str, record_id: str | None = None, actor_id: str = "self") -> dict[str, Any]:
        if report_type not in REPORT_TYPES:
            raise ValueError(f"unsupported report type: {report_type}")
        context = self._project_context(project_id)
        record_bundle = self.repository.export_record(record_id) if record_id else None
        if report_type == "recovery_brief":
            if not record_bundle:
                raise ValueError("record_id is required for recovery_brief")
            canonical = record_bundle["current_record"]
            report = {
                "title": canonical["normalized_input"]["context"]["title"],
                "recovery_state": canonical["findings"]["effective_state"],
                "score": canonical["findings"]["recovery_score"],
                "interpretation": canonical["findings"]["interpretation"],
                "flags": canonical["findings"].get("flags", []),
                "next_step": canonical["findings"]["recovery_plan"]["smallest_recoverable_next_step"],
                "traceability": canonical["metadata"],
            }
        elif report_type == "facilitated_review_brief":
            sessions = self.repository.list_facilitated_sessions(project_id, actor_id=actor_id)
            report = {
                "sessions": sessions,
                "agreements": [agreement for session in sessions for agreement in session.get("agreements", [])],
                "shared_perspectives": self.repository.list_team_perspectives(project_id, record_id=record_id, actor_id=actor_id),
                "team_summary": self.repository.team_recovery_summary(project_id, actor_id=actor_id),
            }
        elif report_type == "action_plan":
            if not record_bundle:
                raise ValueError("record_id is required for action_plan")
            report = {
                "record": record_bundle["record"],
                "actions": record_bundle["actions"],
                "blockers": record_bundle["blockers"],
                "checkpoints": record_bundle["checkpoints"],
                "reassessments": record_bundle["reassessments"],
            }
        elif report_type == "learning_loop_report":
            report = {
                "retrospectives": record_bundle["retrospectives"] if record_bundle else [],
                "patterns": context["patterns"],
                "pattern_reviews": self.repository.list_pattern_reviews(project_id),
                "system_changes": context["system_changes"],
            }
        elif report_type == "adaptation_proposal":
            report = {
                "system_changes": context["system_changes"],
                "supporting_evidence": context["evidence"],
                "active_assumptions": [item for item in context["assumptions"] if item.get("status") == "active"],
            }
        elif report_type == "monitoring_summary":
            report = context["monitoring"]
            report["monitoring_points"] = self.repository.list_monitoring_snapshots(project_id, record_id=record_id)
        else:
            if not record_id:
                raise ValueError("record_id is required for decision_studio_handoff")
            report = self.repository.build_decision_handoff(record_id, actor_id=actor_id)
        return report

    def generate(
        self,
        report_type: str,
        *,
        project_id: str,
        record_id: str | None = None,
        export_format: str = "json",
        redaction_policy: str = "none",
        visibility: str | None = None,
        actor_id: str = "self",
        persist: bool = True,
    ) -> PublicationResult:
        if export_format not in EXPORT_FORMATS:
            raise ValueError(f"unsupported export format: {export_format}")
        report = self.build_report(report_type, project_id=project_id, record_id=record_id, actor_id=actor_id)
        redacted_report = apply_redaction(report, redaction_policy)
        publication_id = self.repository.new_identifier("cgpub") if hasattr(self.repository, "new_identifier") else "cgpub_pending"
        publication = {
            "format": PUBLICATION_FORMAT,
            "publication_id": publication_id,
            "product": "Catalyst Grit",
            "product_version": __version__,
            "report_type": report_type,
            "project_id": project_id,
            "record_id": record_id,
            "visibility": visibility or REDACTION_POLICIES[redaction_policy]["visibility"],
            "redaction_policy": redaction_policy,
            "governance": {
                "human_review_required": (visibility or REDACTION_POLICIES[redaction_policy]["visibility"]) != "private",
                "diagnosis_prohibited": True,
                "individual_ranking_prohibited": True,
                "automated_eligibility_prohibited": True,
            },
            "report": redacted_report,
        }
        publication["content_hash"] = _sha_text(_canonical_json(publication))
        if export_format == "bundle":
            content = _pretty({"bundle": "binary", "publication_id": publication_id, "content_hash": publication["content_hash"]})
            mime = "application/zip"
        else:
            content, mime = render_publication(publication, export_format)
        if persist:
            stored = self.repository.create_publication_artifact(
                project_id,
                report_type=report_type,
                export_format=export_format,
                visibility=publication["visibility"],
                redaction_policy=redaction_policy,
                content_hash=publication["content_hash"],
                content_text=content,
                metadata={"mime_type": mime, "record_id": record_id, "publication_format": PUBLICATION_FORMAT},
                record_id=record_id,
                actor_id=actor_id,
                publication_id=publication_id,
            )
            publication["publication_id"] = stored["publication_id"]
        return PublicationResult(publication=publication, content=content, mime_type=mime)

    def write(self, result: PublicationResult, path: str | Path, *, bundle: bool = False) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        if bundle or output.suffix.lower() == ".zip":
            self.write_bundle(result.publication, output)
        else:
            output.write_text(result.content, encoding="utf-8")
        return output

    def write_bundle(self, publication: Mapping[str, Any], path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        files: dict[str, bytes] = {}
        for fmt, suffix in (("json", "json"), ("jsonld", "jsonld"), ("markdown", "md"), ("html", "html"), ("csv", "csv"), ("pdf_request", "pdf-request.json")):
            text, _ = render_publication(publication, fmt)
            files[f"publication.{suffix}"] = text.encode("utf-8")
        checksums = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
        manifest = {
            "format": PUBLICATION_BUNDLE_FORMAT,
            "product": "Catalyst Grit",
            "product_version": __version__,
            "publication_id": publication.get("publication_id"),
            "report_type": publication.get("report_type"),
            "content_hash": publication.get("content_hash"),
            "files": [{"file": name, "bytes": len(files[name]), "sha256": checksums[name]} for name in sorted(files)],
        }
        files["manifest.json"] = _pretty(manifest).encode("utf-8")
        files["SHA256SUMS"] = "".join(f"{checksums[name]}  {name}\n" for name in sorted(checksums)).encode("utf-8")
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name in sorted(files):
                info = zipfile.ZipInfo(name, (2026, 7, 17, 0, 0, 0))
                info.external_attr = (0o644 & 0xFFFF) << 16
                archive.writestr(info, files[name])
        return output


__all__ = [
    "EXPORT_FORMATS", "PUBLICATION_BUNDLE_FORMAT", "PUBLICATION_FORMAT", "REPORT_TYPES",
    "PublicationResult", "PublicationService", "apply_redaction", "render_publication",
]
