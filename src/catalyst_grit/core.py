"""Canonical Catalyst Grit recovery-record contract and shared engine.

Catalyst Grit evaluates recovery *conditions*, not character. The engine is
pure, dependency-free, deterministic for supplied metadata, and shared by the
CLI, examples, tests, OpenAPI contract, and browser parity implementation.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
import re
import math
from typing import Any, Callable, Iterable, Mapping, Sequence
from uuid import uuid4

from .version import ENGINE_VERSION, SCHEMA_VERSION

METHOD_PATH = [
    "context",
    "trigger",
    "impact",
    "pressure",
    "constraints",
    "supports",
    "capacity",
    "response",
    "learning",
    "retrospective",
    "adaptation patterns",
    "next steps",
    "human review",
]

ALLOWED_DOMAINS = {
    "work",
    "learning",
    "health_wellbeing",
    "relationship",
    "project",
    "career",
    "community",
    "organization",
    "other",
}
ALLOWED_RECORD_STATUSES = {"draft", "active", "under_review", "reviewed", "archived"}
ALLOWED_REVIEW_STATUSES = {
    "not_reviewed",
    "needs_review",
    "in_review",
    "reviewed",
    "changes_requested",
}
ALLOWED_TRIGGER_TYPES = {
    "setback",
    "delay",
    "conflict",
    "constraint_change",
    "capacity_change",
    "external_event",
    "other",
}
ALLOWED_IMPACT_SCOPES = {
    "task",
    "workstream",
    "project",
    "team",
    "organization",
    "personal",
    "multi_system",
    "other",
}
ALLOWED_CONSTRAINT_TYPES = {
    "time",
    "resource",
    "dependency",
    "information",
    "coordination",
    "policy",
    "capacity",
    "other",
}
ALLOWED_CONTROLLABILITY = {"controllable", "influence", "limited", "unknown"}
ALLOWED_CONTROL_ZONES = {"control", "influence", "outside_control", "unknown"}
ALLOWED_FRICTION_LAYERS = {"immediate", "near_term", "structural"}
ALLOWED_SUPPORT_STATUSES = {"active", "potential", "unavailable"}
ALLOWED_SUPPORT_TYPES = {
    "person",
    "team",
    "tool",
    "process",
    "time",
    "funding",
    "information",
    "other",
}
ALLOWED_ACTION_STATUSES = {"planned", "in_progress", "blocked", "completed", "paused", "deferred", "cancelled"}
ALLOWED_ACTION_HORIZONS = {"24_hours", "72_hours", "7_days", "longer_term"}
ALLOWED_PLAN_DECISIONS = {"continue", "reduce_scope", "pause", "delegate", "escalate"}
ALLOWED_PATTERN_REVIEW_DECISIONS = {"accept", "reject", "correct"}
ALLOWED_SYSTEM_CHANGE_DECISIONS = {"proposed", "piloting", "adopt", "revise", "defer", "retire"}
ALLOWED_PROVENANCE_SOURCES = {"direct_entry", "browser", "cli", "api", "import", "migration"}

EXTENSION_KEY = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z0-9-]+)+$")
RECORD_ID = re.compile(r"^cgr_[0-9a-f]{32}$")

DEFAULT_ACTIONS = [
    "Name the smallest recoverable next step",
    "Review support and constraints",
    "Schedule a short follow-up review",
]

DEFAULT_METHODOLOGY_PROFILE: dict[str, Any] = {
    "profile_id": "cg-recovery-conditions",
    "profile_version": "1.5.0",
    "calculation_spec": "weighted-components-v1",
    "component_weights": {
        "impact_buffer": 15.0,
        "pressure_buffer": 15.0,
        "energy_capacity": 15.0,
        "support_capacity": 15.0,
        "clarity_capacity": 15.0,
        "action_readiness": 15.0,
        "constraint_manageability": 10.0,
    },
    "thresholds": {
        "stable": 75.0,
        "focused_support": 55.0,
        "fragile": 35.0,
    },
}

INTERPRETATION_LIMITS = [
    "Describes recorded recovery conditions, not a person's character.",
    "Does not diagnose mental health, predict outcomes, or replace professional support.",
    "Must not be used for employee ranking, automated eligibility, or performance evaluation.",
    "Generated findings require human review when used for consequential decisions.",
]


@dataclass(frozen=True)
class ValidationIssue:
    """Machine-readable validation issue."""

    path: str
    code: str
    message: str
    value: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        if self.value is None:
            value.pop("value")
        return value


class GritValidationError(ValueError):
    """Raised when a recovery-record request violates the canonical contract."""

    def __init__(self, issues: ValidationIssue | Sequence[ValidationIssue] | str):
        if isinstance(issues, str):
            normalized = [ValidationIssue("$", "invalid_request", issues)]
        elif isinstance(issues, ValidationIssue):
            normalized = [issues]
        else:
            normalized = list(issues)
        self.issues = normalized
        super().__init__("; ".join(f"{issue.path}: {issue.message}" for issue in normalized))

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": "validation_failed",
            "message": "The recovery-record request is invalid.",
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True)
class RecoveryRecord:
    """Generated canonical recovery record."""

    metadata: dict[str, Any]
    user_input: dict[str, Any]
    normalized_input: dict[str, Any]
    findings: dict[str, Any]
    human_review: dict[str, Any]
    extensions: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Backward-compatible public names retained for clients importing v1.0 symbols.
GritOutput = RecoveryRecord
GritInput = dict[str, Any]


def _issue(path: str, code: str, message: str, value: Any | None = None) -> GritValidationError:
    return GritValidationError(ValidationIssue(path, code, message, value))


def _reject_unknown(value: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise _issue(
            path,
            "unknown_field",
            "Unsupported field(s): " + ", ".join(unknown) + ". Use the extensions object for namespaced additions.",
            unknown,
        )


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _issue(path, "type_error", "Must be an object.", value)
    return value


def _text(value: Any, path: str, *, default: str = "", required: bool = False) -> str:
    text = default if value is None else str(value).strip()
    if required and not text:
        raise _issue(path, "required", "Must not be empty.")
    return text


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def clamp_scale(value: Any, field: str, low: float = 1, high: float = 10) -> float:
    """Normalize a numeric scale to the supported inclusive range."""
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise _issue(field, "numeric_required", "Must be numeric.", value) from exc
    return max(low, min(high, number))


def _integer(value: Any, path: str, *, default: int, minimum: int = 1) -> int:
    try:
        number = int(float(default if value is None else value))
    except (TypeError, ValueError) as exc:
        raise _issue(path, "integer_required", "Must be numeric.", value) from exc
    return max(minimum, number)


def _nullable_number(value: Any, path: str, *, minimum: float = 0) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise _issue(path, "numeric_required", "Must be numeric or null.", value) from exc
    if number < minimum:
        raise _issue(path, "minimum", f"Must be at least {minimum}.", value)
    return number


def _enum(value: Any, path: str, allowed: set[str], default: str) -> str:
    normalized = _text(value, path, default=default) or default
    if normalized not in allowed:
        raise _issue(path, "enum", "Must be one of: " + ", ".join(sorted(allowed)) + ".", value)
    return normalized


def _string_list(value: Any, path: str) -> list[str]:
    if value in (None, ""):
        return []
    source: Iterable[Any]
    if isinstance(value, (str, bytes)):
        source = str(value).splitlines()
    elif isinstance(value, Sequence):
        source = value
    else:
        raise _issue(path, "type_error", "Must be an array of strings or newline-delimited text.", value)
    return [str(item).strip() for item in source if str(item).strip()]


def clean_actions(actions: Iterable[Any] | str | None) -> list[str]:
    """Compatibility helper returning clean action titles."""
    cleaned = _string_list(actions, "$.input.response.actions")
    return cleaned or list(DEFAULT_ACTIONS)


def _normalize_action_list(value: Any, path: str, *, default_actions: bool = False) -> list[dict[str, Any]]:
    if value in (None, ""):
        source: list[Any] = []
    elif isinstance(value, (str, bytes)):
        source = list(str(value).splitlines())
    elif isinstance(value, Sequence):
        source = list(value)
    else:
        raise _issue(path, "type_error", "Must be an array or newline-delimited text.", value)

    actions: list[dict[str, Any]] = []
    for index, item in enumerate(source):
        item_path = f"{path}[{index}]"
        default_horizon = ("24_hours", "72_hours", "7_days", "longer_term")[min(index, 3)]
        if isinstance(item, Mapping):
            _reject_unknown(
                item,
                {
                    "action_key", "title", "statement", "status", "owner", "target_date", "horizon",
                    "expected_effect", "required_support", "dependencies", "effort", "urgency",
                    "completion_evidence", "reassessment_trigger", "blocked_reason", "escalation_path",
                },
                item_path,
            )
            title = _text(item.get("title", item.get("statement")), f"{item_path}.title", required=True)
            action_key = _text(item.get("action_key"), f"{item_path}.action_key", default=f"action-{index + 1}") or f"action-{index + 1}"
            status = _enum(item.get("status"), f"{item_path}.status", ALLOWED_ACTION_STATUSES, "planned")
            owner = _optional_text(item.get("owner"))
            target_date = _optional_date(item.get("target_date"), f"{item_path}.target_date")
            horizon = _enum(item.get("horizon"), f"{item_path}.horizon", ALLOWED_ACTION_HORIZONS, default_horizon)
            expected_effect = _text(item.get("expected_effect"), f"{item_path}.expected_effect")
            required_support = _string_list(item.get("required_support"), f"{item_path}.required_support")
            dependencies = _string_list(item.get("dependencies"), f"{item_path}.dependencies")
            effort = clamp_scale(item.get("effort", 3), f"{item_path}.effort", 1, 5)
            urgency = clamp_scale(item.get("urgency", 3), f"{item_path}.urgency", 1, 5)
            completion_evidence = _text(item.get("completion_evidence"), f"{item_path}.completion_evidence")
            reassessment_trigger = _text(item.get("reassessment_trigger"), f"{item_path}.reassessment_trigger")
            blocked_reason = _text(item.get("blocked_reason"), f"{item_path}.blocked_reason")
            escalation_path = _text(item.get("escalation_path"), f"{item_path}.escalation_path")
        else:
            title = _text(item, item_path)
            if not title:
                continue
            action_key = f"action-{index + 1}"
            status = "planned"
            owner = None
            target_date = None
            horizon = default_horizon
            expected_effect = ""
            required_support = []
            dependencies = []
            effort = 3.0
            urgency = 3.0
            completion_evidence = ""
            reassessment_trigger = ""
            blocked_reason = ""
            escalation_path = ""
        if status == "blocked" and not blocked_reason:
            raise _issue(f"{item_path}.blocked_reason", "blocked_reason_required", "A blocked action requires a non-punitive description of the support or dependency needed.")
        if status == "completed" and not completion_evidence:
            raise _issue(f"{item_path}.completion_evidence", "completion_evidence_required", "A completed action requires completion evidence.")
        actions.append({
            "action_key": action_key,
            "title": title,
            "status": status,
            "owner": owner,
            "target_date": target_date,
            "horizon": horizon,
            "expected_effect": expected_effect,
            "required_support": required_support,
            "dependencies": dependencies,
            "effort": effort,
            "urgency": urgency,
            "completion_evidence": completion_evidence,
            "reassessment_trigger": reassessment_trigger,
            "blocked_reason": blocked_reason,
            "escalation_path": escalation_path,
        })

    if not actions and default_actions:
        actions = [
            {
                "action_key": f"default-{index + 1}", "title": title, "status": "planned", "owner": "self",
                "target_date": None, "horizon": ("24_hours", "72_hours", "7_days")[index],
                "expected_effect": "", "required_support": [], "dependencies": [], "effort": 3.0,
                "urgency": 3.0, "completion_evidence": "", "reassessment_trigger": "",
                "blocked_reason": "", "escalation_path": "",
            }
            for index, title in enumerate(DEFAULT_ACTIONS)
        ]
    keys = [item["action_key"] for item in actions]
    if len(keys) != len(set(keys)):
        raise _issue(path, "duplicate_action_key", "Action keys must be unique within a section.", keys)
    return actions


def _normalize_pattern_reviews(value: Any, path: str) -> list[dict[str, Any]]:
    if value in (None, ""):
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise _issue(path, "type_error", "Must be an array of pattern review objects.", value)
    reviews: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        item_path = f"{path}[{index}]"
        item = _mapping(raw, item_path)
        _reject_unknown(item, {"pattern_key", "decision", "corrected_label", "notes"}, item_path)
        decision = _enum(item.get("decision"), f"{item_path}.decision", ALLOWED_PATTERN_REVIEW_DECISIONS, "accept")
        corrected = _text(item.get("corrected_label"), f"{item_path}.corrected_label")
        if decision == "correct" and not corrected:
            raise _issue(f"{item_path}.corrected_label", "required", "A corrected pattern requires corrected_label.")
        reviews.append({
            "pattern_key": _text(item.get("pattern_key"), f"{item_path}.pattern_key", required=True),
            "decision": decision,
            "corrected_label": corrected,
            "notes": _text(item.get("notes"), f"{item_path}.notes"),
        })
    return reviews


def _pattern_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:56] or "unspecified"


def _control_zone(controllability: str) -> str:
    return {"controllable": "control", "influence": "influence", "limited": "outside_control", "unknown": "unknown"}[controllability]


def _normalize_constraints(value: Any, path: str) -> list[dict[str, Any]]:
    if value in (None, ""):
        return []
    if isinstance(value, (str, bytes)):
        source: list[Any] = list(str(value).splitlines())
    elif isinstance(value, Sequence):
        source = list(value)
    else:
        raise _issue(path, "type_error", "Must be an array or newline-delimited text.", value)

    output: list[dict[str, Any]] = []
    for index, item in enumerate(source):
        item_path = f"{path}[{index}]"
        if isinstance(item, Mapping):
            _reject_unknown(item, {"label", "type", "controllability", "control_zone", "layer", "severity", "notes"}, item_path)
            label = _text(item.get("label"), f"{item_path}.label", required=True)
            item_type = _enum(item.get("type"), f"{item_path}.type", ALLOWED_CONSTRAINT_TYPES, "other")
            controllability = _enum(item.get("controllability"), f"{item_path}.controllability", ALLOWED_CONTROLLABILITY, "unknown")
            control_zone = _enum(item.get("control_zone"), f"{item_path}.control_zone", ALLOWED_CONTROL_ZONES, _control_zone(controllability))
            layer = _enum(item.get("layer"), f"{item_path}.layer", ALLOWED_FRICTION_LAYERS, "immediate")
            severity = clamp_scale(item.get("severity", 5), f"{item_path}.severity")
            notes = _text(item.get("notes"), f"{item_path}.notes")
        else:
            label = _text(item, item_path)
            if not label:
                continue
            item_type = "other"; controllability = "unknown"; control_zone = "unknown"; layer = "immediate"; severity = 5.0; notes = ""
        output.append({"label": label, "type": item_type, "controllability": controllability, "control_zone": control_zone, "layer": layer, "severity": severity, "notes": notes})
    return output


def _normalize_supports(value: Any, path: str) -> list[dict[str, Any]]:
    if value in (None, ""):
        return []
    if isinstance(value, (str, bytes)):
        source: list[Any] = list(str(value).splitlines())
    elif isinstance(value, Sequence):
        source = list(value)
    else:
        raise _issue(path, "type_error", "Must be an array or newline-delimited text.", value)

    output: list[dict[str, Any]] = []
    for index, item in enumerate(source):
        item_path = f"{path}[{index}]"
        if isinstance(item, Mapping):
            _reject_unknown(item, {"label", "type", "reliability", "status", "capacity_contribution", "notes"}, item_path)
            label = _text(item.get("label"), f"{item_path}.label", required=True)
            item_type = _enum(item.get("type"), f"{item_path}.type", ALLOWED_SUPPORT_TYPES, "other")
            reliability = clamp_scale(item.get("reliability", 5), f"{item_path}.reliability")
            status = _enum(item.get("status"), f"{item_path}.status", ALLOWED_SUPPORT_STATUSES, "active")
            contribution = clamp_scale(item.get("capacity_contribution", reliability), f"{item_path}.capacity_contribution")
            notes = _text(item.get("notes"), f"{item_path}.notes")
        else:
            label = _text(item, item_path)
            if not label:
                continue
            item_type = "other"; reliability = 5.0; status = "active"; contribution = 5.0; notes = ""
        output.append({"label": label, "type": item_type, "reliability": reliability, "status": status, "capacity_contribution": contribution, "notes": notes})
    return output


def _normalize_timestamp(value: Any, path: str, default: str) -> str:
    text = _text(value, path, default=default) or default
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _issue(path, "date_time", "Must be an ISO 8601 date-time with a timezone.", value) from exc
    if parsed.tzinfo is None:
        raise _issue(path, "date_time_timezone", "Must include a timezone.", value)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _optional_timestamp(value: Any, path: str) -> str | None:
    if value in (None, ""):
        return None
    return _normalize_timestamp(value, path, "")


def _optional_date(value: Any, path: str) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError as exc:
        raise _issue(path, "date", "Must use YYYY-MM-DD.", value) from exc
    return text


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _record_id() -> str:
    return "cgr_" + uuid4().hex


def _normalize_extensions(value: Any, path: str = "$.extensions") -> dict[str, Any]:
    if value in (None, ""):
        return {}
    mapping = _mapping(value, path)
    invalid = [key for key in mapping if not isinstance(key, str) or not EXTENSION_KEY.fullmatch(key)]
    if invalid:
        raise _issue(
            path,
            "extension_namespace",
            "Extension keys must be namespaced, for example org.example.field.",
            invalid,
        )
    return deepcopy(dict(mapping))


def _legacy_request(data: Mapping[str, Any]) -> bool:
    return "challenge" in data and "input" not in data


def migrate_v1_request(data: Mapping[str, Any]) -> dict[str, Any]:
    """Migrate a v1.0.x flat request into the v1.1 canonical request shape."""
    if not isinstance(data, Mapping):
        raise _issue("$", "type_error", "Input must be an object.", data)
    actions = data.get("recovery_actions")
    review_status = str(data.get("review_status", "draft"))
    record_status = {"draft": "draft", "needs_review": "under_review", "reviewed": "reviewed"}.get(review_status, "draft")
    human_status = {"draft": "not_reviewed", "needs_review": "needs_review", "reviewed": "reviewed"}.get(review_status, "not_reviewed")
    challenge = str(data.get("challenge", "")).strip() or "Unspecified challenge"
    return {
        "metadata": {
            "status": record_status,
            "provenance": {
                "created_by": "self",
                "source": "migration",
                "source_schema_version": "1.0.1",
                "source_record_id": None,
                "notes": "Migrated from the v1.0.x flat recovery-record request.",
            },
        },
        "input": {
            "context": {
                "title": challenge,
                "domain": data.get("domain", "project"),
                "description": "",
                "stakeholders": [],
                "affected_work": [],
            },
            "trigger": {"summary": challenge, "type": "setback", "occurred_at": None},
            "impact": {
                "severity": data.get("impact_severity", 5),
                "scope": "project",
                "description": "",
            },
            "pressure": {"level": data.get("pressure_level", 5), "sources": [], "competing_demands": [], "decision_ambiguity": 5, "dependency_friction": 5, "stakeholder_friction": 5},
            "constraints": {"items": []},
            "supports": {"level": data.get("support_level", 5), "available": []},
            "capacity": {
                "energy_level": data.get("energy_level", 5),
                "clarity_level": data.get("clarity_level", 5),
                "available_time_hours": None,
                "time_horizon_days": data.get("time_horizon_days", 14),
                "attention_level": data.get("clarity_level", 5),
                "coordination_capacity": data.get("support_level", 5),
                "recovery_time_hours": None,
                "load_level": data.get("pressure_level", 5),
            },
            "response": {
                "actions": actions,
                "current_strategy": "",
            },
            "learning": {"observations": [], "assumptions": [], "adaptations": [], "what_happened": "", "what_was_expected": "", "what_changed": "", "what_helped": [], "what_hindered": [], "what_was_learned": [], "repeat": [], "redesign": [], "uncertainties": [], "pattern_reviews": []},
            "next_steps": {"actions": [], "checkpoint_date": None, "success_signal": ""},
        },
        "human_review": {
            "review_status": human_status,
            "reviewer": None,
            "reviewed_at": None,
            "notes": "",
            "accepted_findings": [],
            "rejected_findings": [],
            "override_state": None,
        },
        "extensions": {},
    }


def _normalize_metadata(value: Any, *, source_schema_version: str) -> dict[str, Any]:
    metadata = _mapping(value or {}, "$.metadata")
    _reject_unknown(
        metadata,
        {"record_id", "schema_version", "engine_version", "created_at", "updated_at", "status", "provenance"},
        "$.metadata",
    )
    record_id = _text(metadata.get("record_id"), "$.metadata.record_id", default=_record_id())
    if not RECORD_ID.fullmatch(record_id):
        raise _issue("$.metadata.record_id", "record_id", "Must match cgr_ followed by 32 lowercase hexadecimal characters.", record_id)

    supplied_schema = _optional_text(metadata.get("schema_version"))
    if supplied_schema and supplied_schema not in {SCHEMA_VERSION, "1.4.0", "1.3.0", "1.2.0", "1.1.0", "1.0.1"}:
        raise _issue("$.metadata.schema_version", "schema_version", f"Unsupported source schema version: {supplied_schema}.", supplied_schema)
    supplied_engine = _optional_text(metadata.get("engine_version"))
    if supplied_engine and supplied_engine != ENGINE_VERSION:
        raise _issue("$.metadata.engine_version", "engine_version", "Requests may not select a different engine version.", supplied_engine)

    created_default = _now_iso()
    created_at = _normalize_timestamp(metadata.get("created_at"), "$.metadata.created_at", created_default)
    updated_at = _normalize_timestamp(metadata.get("updated_at"), "$.metadata.updated_at", created_at)
    if updated_at < created_at:
        raise _issue("$.metadata.updated_at", "chronology", "Must not be earlier than created_at.", updated_at)
    status = _enum(metadata.get("status"), "$.metadata.status", ALLOWED_RECORD_STATUSES, "draft")

    provenance = _mapping(metadata.get("provenance") or {}, "$.metadata.provenance")
    _reject_unknown(
        provenance,
        {"created_by", "source", "source_schema_version", "source_record_id", "notes"},
        "$.metadata.provenance",
    )
    provenance_output = {
        "created_by": _text(provenance.get("created_by"), "$.metadata.provenance.created_by", default="self") or "self",
        "source": _enum(provenance.get("source"), "$.metadata.provenance.source", ALLOWED_PROVENANCE_SOURCES, "direct_entry"),
        "source_schema_version": _text(
            provenance.get("source_schema_version"),
            "$.metadata.provenance.source_schema_version",
            default=source_schema_version,
        ) or source_schema_version,
        "source_record_id": _optional_text(provenance.get("source_record_id")),
        "notes": _text(provenance.get("notes"), "$.metadata.provenance.notes"),
    }
    return {
        "record_id": record_id,
        "schema_version": SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "created_at": created_at,
        "updated_at": updated_at,
        "status": status,
        "provenance": provenance_output,
    }


def _normalize_human_review(value: Any, *, record_status: str) -> dict[str, Any]:
    review = _mapping(value or {}, "$.human_review")
    _reject_unknown(
        review,
        {"review_status", "reviewer", "reviewed_at", "notes", "accepted_findings", "rejected_findings", "override_state"},
        "$.human_review",
    )
    status = _enum(review.get("review_status"), "$.human_review.review_status", ALLOWED_REVIEW_STATUSES, "not_reviewed")
    reviewer = _optional_text(review.get("reviewer"))
    reviewed_at = _optional_timestamp(review.get("reviewed_at"), "$.human_review.reviewed_at")
    override = _optional_text(review.get("override_state"))
    allowed_states = {
        "stable recovery conditions",
        "recoverable with focused support",
        "fragile recovery conditions",
        "high-friction recovery conditions",
    }
    if override and override not in allowed_states:
        raise _issue("$.human_review.override_state", "enum", "Must be a recognized recovery-condition state or null.", override)
    if status == "reviewed" and not reviewed_at:
        raise _issue("$.human_review.reviewed_at", "review_lifecycle", "A reviewed record requires reviewed_at.")
    if status == "reviewed" and not reviewer:
        raise _issue("$.human_review.reviewer", "review_lifecycle", "A reviewed record requires a reviewer.")
    if record_status == "reviewed" and status != "reviewed":
        raise _issue("$.human_review.review_status", "review_lifecycle", "A record with status reviewed requires human_review.review_status reviewed.", status)
    return {
        "review_status": status,
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "notes": _text(review.get("notes"), "$.human_review.notes"),
        "accepted_findings": _string_list(review.get("accepted_findings"), "$.human_review.accepted_findings"),
        "rejected_findings": _string_list(review.get("rejected_findings"), "$.human_review.rejected_findings"),
        "override_state": override,
    }


def _normalize_input_sections(value: Any) -> dict[str, Any]:
    input_data = _mapping(value, "$.input")
    required = {
        "context",
        "trigger",
        "impact",
        "pressure",
        "constraints",
        "supports",
        "capacity",
        "response",
        "learning",
        "next_steps",
    }
    _reject_unknown(input_data, required, "$.input")
    missing = sorted(required - set(input_data))
    if missing:
        raise _issue("$.input", "required", "Missing section(s): " + ", ".join(missing) + ".", missing)

    context = _mapping(input_data["context"], "$.input.context")
    _reject_unknown(context, {"title", "domain", "description", "stakeholders", "affected_work"}, "$.input.context")
    trigger = _mapping(input_data["trigger"], "$.input.trigger")
    _reject_unknown(trigger, {"summary", "type", "occurred_at"}, "$.input.trigger")
    impact = _mapping(input_data["impact"], "$.input.impact")
    _reject_unknown(impact, {"severity", "scope", "description"}, "$.input.impact")
    pressure = _mapping(input_data["pressure"], "$.input.pressure")
    _reject_unknown(pressure, {"level", "sources", "competing_demands", "decision_ambiguity", "dependency_friction", "stakeholder_friction"}, "$.input.pressure")
    constraints = _mapping(input_data["constraints"], "$.input.constraints")
    _reject_unknown(constraints, {"items"}, "$.input.constraints")
    supports = _mapping(input_data["supports"], "$.input.supports")
    _reject_unknown(supports, {"level", "available"}, "$.input.supports")
    capacity = _mapping(input_data["capacity"], "$.input.capacity")
    _reject_unknown(capacity, {"energy_level", "clarity_level", "available_time_hours", "time_horizon_days", "attention_level", "coordination_capacity", "recovery_time_hours", "load_level"}, "$.input.capacity")
    response = _mapping(input_data["response"], "$.input.response")
    _reject_unknown(response, {"actions", "current_strategy"}, "$.input.response")
    learning = _mapping(input_data["learning"], "$.input.learning")
    _reject_unknown(learning, {"observations", "assumptions", "adaptations", "what_happened", "what_was_expected", "what_changed", "what_helped", "what_hindered", "what_was_learned", "repeat", "redesign", "uncertainties", "pattern_reviews"}, "$.input.learning")
    next_steps = _mapping(input_data["next_steps"], "$.input.next_steps")
    _reject_unknown(next_steps, {"actions", "checkpoint_date", "success_signal", "scope_decision", "scope_decision_notes", "blockers", "escalation_log", "changed_assumptions", "reassessment_trigger"}, "$.input.next_steps")

    return {
        "context": {
            "title": _text(context.get("title"), "$.input.context.title", required=True),
            "domain": _enum(context.get("domain"), "$.input.context.domain", ALLOWED_DOMAINS, "project"),
            "description": _text(context.get("description"), "$.input.context.description"),
            "stakeholders": _string_list(context.get("stakeholders"), "$.input.context.stakeholders"),
            "affected_work": _string_list(context.get("affected_work"), "$.input.context.affected_work"),
        },
        "trigger": {
            "summary": _text(trigger.get("summary"), "$.input.trigger.summary", required=True),
            "type": _enum(trigger.get("type"), "$.input.trigger.type", ALLOWED_TRIGGER_TYPES, "setback"),
            "occurred_at": _optional_timestamp(trigger.get("occurred_at"), "$.input.trigger.occurred_at"),
        },
        "impact": {
            "severity": clamp_scale(impact.get("severity", 5), "$.input.impact.severity"),
            "scope": _enum(impact.get("scope"), "$.input.impact.scope", ALLOWED_IMPACT_SCOPES, "project"),
            "description": _text(impact.get("description"), "$.input.impact.description"),
        },
        "pressure": {
            "level": clamp_scale(pressure.get("level", 5), "$.input.pressure.level"),
            "sources": _string_list(pressure.get("sources"), "$.input.pressure.sources"),
            "competing_demands": _string_list(pressure.get("competing_demands"), "$.input.pressure.competing_demands"),
            "decision_ambiguity": clamp_scale(pressure.get("decision_ambiguity", 5), "$.input.pressure.decision_ambiguity"),
            "dependency_friction": clamp_scale(pressure.get("dependency_friction", 5), "$.input.pressure.dependency_friction"),
            "stakeholder_friction": clamp_scale(pressure.get("stakeholder_friction", 5), "$.input.pressure.stakeholder_friction"),
        },
        "constraints": {"items": _normalize_constraints(constraints.get("items"), "$.input.constraints.items")},
        "supports": {
            "level": clamp_scale(supports.get("level", 5), "$.input.supports.level"),
            "available": _normalize_supports(supports.get("available"), "$.input.supports.available"),
        },
        "capacity": {
            "energy_level": clamp_scale(capacity.get("energy_level", 5), "$.input.capacity.energy_level"),
            "clarity_level": clamp_scale(capacity.get("clarity_level", 5), "$.input.capacity.clarity_level"),
            "available_time_hours": _nullable_number(capacity.get("available_time_hours"), "$.input.capacity.available_time_hours"),
            "time_horizon_days": _integer(capacity.get("time_horizon_days"), "$.input.capacity.time_horizon_days", default=14),
            "attention_level": clamp_scale(capacity.get("attention_level", capacity.get("clarity_level", 5)), "$.input.capacity.attention_level"),
            "coordination_capacity": clamp_scale(capacity.get("coordination_capacity", supports.get("level", 5)), "$.input.capacity.coordination_capacity"),
            "recovery_time_hours": _nullable_number(capacity.get("recovery_time_hours"), "$.input.capacity.recovery_time_hours"),
            "load_level": clamp_scale(capacity.get("load_level", pressure.get("level", 5)), "$.input.capacity.load_level"),
        },
        "response": {
            "actions": _normalize_action_list(response.get("actions"), "$.input.response.actions", default_actions=True),
            "current_strategy": _text(response.get("current_strategy"), "$.input.response.current_strategy"),
        },
        "learning": {
            "observations": _string_list(learning.get("observations"), "$.input.learning.observations"),
            "assumptions": _string_list(learning.get("assumptions"), "$.input.learning.assumptions"),
            "adaptations": _string_list(learning.get("adaptations"), "$.input.learning.adaptations"),
            "what_happened": _text(learning.get("what_happened"), "$.input.learning.what_happened"),
            "what_was_expected": _text(learning.get("what_was_expected"), "$.input.learning.what_was_expected"),
            "what_changed": _text(learning.get("what_changed"), "$.input.learning.what_changed"),
            "what_helped": _string_list(learning.get("what_helped"), "$.input.learning.what_helped"),
            "what_hindered": _string_list(learning.get("what_hindered"), "$.input.learning.what_hindered"),
            "what_was_learned": _string_list(learning.get("what_was_learned"), "$.input.learning.what_was_learned"),
            "repeat": _string_list(learning.get("repeat"), "$.input.learning.repeat"),
            "redesign": _string_list(learning.get("redesign"), "$.input.learning.redesign"),
            "uncertainties": _string_list(learning.get("uncertainties"), "$.input.learning.uncertainties"),
            "pattern_reviews": _normalize_pattern_reviews(learning.get("pattern_reviews"), "$.input.learning.pattern_reviews"),
        },
        "next_steps": {
            "actions": _normalize_action_list(next_steps.get("actions"), "$.input.next_steps.actions"),
            "checkpoint_date": _optional_date(next_steps.get("checkpoint_date"), "$.input.next_steps.checkpoint_date"),
            "success_signal": _text(next_steps.get("success_signal"), "$.input.next_steps.success_signal"),
            "scope_decision": _enum(next_steps.get("scope_decision"), "$.input.next_steps.scope_decision", ALLOWED_PLAN_DECISIONS, "continue"),
            "scope_decision_notes": _text(next_steps.get("scope_decision_notes"), "$.input.next_steps.scope_decision_notes"),
            "blockers": _string_list(next_steps.get("blockers"), "$.input.next_steps.blockers"),
            "escalation_log": _string_list(next_steps.get("escalation_log"), "$.input.next_steps.escalation_log"),
            "changed_assumptions": _string_list(next_steps.get("changed_assumptions"), "$.input.next_steps.changed_assumptions"),
            "reassessment_trigger": _text(next_steps.get("reassessment_trigger"), "$.input.next_steps.reassessment_trigger"),
        },
    }


def normalize_methodology_profile(value: Mapping[str, Any] | None = None) -> dict[str, Any]:
    profile = deepcopy(DEFAULT_METHODOLOGY_PROFILE if value is None else dict(value))
    profile = dict(_mapping(profile, "$.methodology_profile"))
    _reject_unknown(profile, {"profile_id", "profile_version", "calculation_spec", "component_weights", "thresholds"}, "$.methodology_profile")
    profile_id = _text(profile.get("profile_id"), "$.methodology_profile.profile_id", required=True)
    profile_version = _text(profile.get("profile_version"), "$.methodology_profile.profile_version", required=True)
    spec = _text(profile.get("calculation_spec"), "$.methodology_profile.calculation_spec", required=True)
    if spec != "weighted-components-v1":
        raise _issue("$.methodology_profile.calculation_spec", "calculation_spec", "Only weighted-components-v1 is supported.", spec)

    weights_map = _mapping(profile.get("component_weights"), "$.methodology_profile.component_weights")
    expected_components = set(DEFAULT_METHODOLOGY_PROFILE["component_weights"])
    _reject_unknown(weights_map, expected_components, "$.methodology_profile.component_weights")
    missing = sorted(expected_components - set(weights_map))
    if missing:
        raise _issue("$.methodology_profile.component_weights", "required", "Missing component weight(s): " + ", ".join(missing) + ".", missing)
    weights: dict[str, float] = {}
    for key in DEFAULT_METHODOLOGY_PROFILE["component_weights"]:
        try:
            weight = float(weights_map[key])
        except (TypeError, ValueError) as exc:
            raise _issue(f"$.methodology_profile.component_weights.{key}", "numeric_required", "Must be numeric.", weights_map[key]) from exc
        if weight < 0:
            raise _issue(f"$.methodology_profile.component_weights.{key}", "minimum", "Must be zero or greater.", weight)
        weights[key] = weight
    if abs(sum(weights.values()) - 100.0) > 1e-6:
        raise _issue("$.methodology_profile.component_weights", "weight_total", "Component weights must total 100.", sum(weights.values()))

    thresholds_map = _mapping(profile.get("thresholds"), "$.methodology_profile.thresholds")
    threshold_keys = {"stable", "focused_support", "fragile"}
    _reject_unknown(thresholds_map, threshold_keys, "$.methodology_profile.thresholds")
    missing_thresholds = sorted(threshold_keys - set(thresholds_map))
    if missing_thresholds:
        raise _issue("$.methodology_profile.thresholds", "required", "Missing threshold(s): " + ", ".join(missing_thresholds) + ".", missing_thresholds)
    thresholds: dict[str, float] = {}
    for key in ("stable", "focused_support", "fragile"):
        try:
            threshold = float(thresholds_map[key])
        except (TypeError, ValueError) as exc:
            raise _issue(f"$.methodology_profile.thresholds.{key}", "numeric_required", "Must be numeric.", thresholds_map[key]) from exc
        if not 0 <= threshold <= 100:
            raise _issue(f"$.methodology_profile.thresholds.{key}", "range", "Must be between 0 and 100.", threshold)
        thresholds[key] = threshold
    if not thresholds["stable"] > thresholds["focused_support"] > thresholds["fragile"]:
        raise _issue("$.methodology_profile.thresholds", "threshold_order", "Thresholds must descend: stable > focused_support > fragile.", thresholds)

    return {
        "profile_id": profile_id,
        "profile_version": profile_version,
        "calculation_spec": spec,
        "component_weights": weights,
        "thresholds": thresholds,
    }


def _upgrade_prior_input(value: Mapping[str, Any], source_schema: str) -> dict[str, Any]:
    """Add non-destructive v1.5 defaults to earlier canonical requests."""
    upgraded = deepcopy(dict(value))
    if source_schema == SCHEMA_VERSION:
        return upgraded
    learning = dict(upgraded.get("learning") or {})
    learning.setdefault("what_happened", "")
    learning.setdefault("what_was_expected", "")
    learning.setdefault("what_changed", "")
    learning.setdefault("what_helped", [])
    learning.setdefault("what_hindered", [])
    learning.setdefault("what_was_learned", [])
    learning.setdefault("repeat", [])
    learning.setdefault("redesign", [])
    learning.setdefault("uncertainties", [])
    learning.setdefault("pattern_reviews", [])
    upgraded["learning"] = learning
    next_steps = dict(upgraded.get("next_steps") or {})
    next_steps.setdefault("scope_decision", "continue")
    next_steps.setdefault("scope_decision_notes", "")
    next_steps.setdefault("blockers", [])
    next_steps.setdefault("escalation_log", [])
    next_steps.setdefault("changed_assumptions", [])
    next_steps.setdefault("reassessment_trigger", "")
    upgraded["next_steps"] = next_steps
    for section in ("response", "next_steps"):
        section_value = dict(upgraded.get(section) or {})
        actions = []
        for item in section_value.get("actions") or []:
            if isinstance(item, Mapping):
                action = deepcopy(dict(item))
                if action.get("status") == "completed" and not action.get("completion_evidence"):
                    action["completion_evidence"] = "Completion predates v1.4; evidence was not supplied."
                if action.get("status") == "blocked" and not action.get("blocked_reason"):
                    action["blocked_reason"] = "Blocked status predates v1.4; the support need was not supplied."
                actions.append(action)
            else:
                actions.append(item)
        section_value["actions"] = actions
        upgraded[section] = section_value
    return upgraded


def normalize_input(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return a canonical normalized request without generated findings."""
    if not isinstance(data, Mapping):
        raise _issue("$", "type_error", "Input must be an object.", data)
    migrated = _legacy_request(data)
    request = migrate_v1_request(data) if migrated else deepcopy(dict(data))
    _reject_unknown(request, {"metadata", "input", "human_review", "extensions", "methodology_profile"}, "$")
    if "input" not in request:
        raise _issue("$.input", "required", "The input object is required.")
    source_schema = "1.0.1" if migrated else str(
        (request.get("metadata") or {}).get("schema_version")
        or (request.get("metadata") or {}).get("provenance", {}).get("source_schema_version")
        or SCHEMA_VERSION
    )
    metadata = _normalize_metadata(request.get("metadata"), source_schema_version=source_schema)
    upgraded_input = _upgrade_prior_input(request["input"], source_schema)
    normalized_sections = _normalize_input_sections(upgraded_input)
    human_review = _normalize_human_review(request.get("human_review"), record_status=metadata["status"])
    extensions = _normalize_extensions(request.get("extensions"))
    methodology = normalize_methodology_profile(request.get("methodology_profile"))
    return {
        "metadata": metadata,
        "input": normalized_sections,
        "human_review": human_review,
        "extensions": extensions,
        "methodology_profile": methodology,
        "migrated": migrated,
        "user_input": deepcopy(dict(request["input"])),
    }



def _round_half_up(value: float, places: int) -> float:
    factor = 10 ** places
    return math.floor(value * factor + 0.5) / factor

def _positive(value: float) -> float:
    return max(0.0, min(1.0, (value - 1.0) / 9.0))


def _inverse(value: float) -> float:
    return max(0.0, min(1.0, (10.0 - value) / 9.0))


def _constraint_manageability(items: list[dict[str, Any]]) -> float:
    if not items:
        return 1.0
    values = {"controllable": 1.0, "influence": 0.65, "limited": 0.25, "unknown": 0.4}
    return sum(values[item["controllability"]] for item in items) / len(items)


def _action_readiness(normalized: Mapping[str, Any]) -> tuple[float, int]:
    response_actions = normalized["response"]["actions"]
    next_actions = normalized["next_steps"]["actions"]
    titles: list[str] = []
    for action in [*response_actions, *next_actions]:
        title = action["title"].strip().lower()
        if title and title not in titles:
            titles.append(title)
    count = len(titles)
    return min(1.0, count / 4.0), count


def calculate_component_scores(normalized: Mapping[str, Any], profile: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Calculate explainable weighted component scores."""
    weights = profile["component_weights"]
    action_value, action_count = _action_readiness(normalized)
    raw: dict[str, tuple[Any, float, str]] = {
        "impact_buffer": (
            normalized["impact"]["severity"],
            _inverse(normalized["impact"]["severity"]),
            "Lower recorded impact leaves more near-term recovery room; severity remains visible separately.",
        ),
        "pressure_buffer": (
            normalized["pressure"]["level"],
            _inverse(normalized["pressure"]["level"]),
            "Lower recorded pressure increases the room available for deliberate recovery action.",
        ),
        "energy_capacity": (
            normalized["capacity"]["energy_level"],
            _positive(normalized["capacity"]["energy_level"]),
            "Recorded energy is treated as available capacity, not motivation or character.",
        ),
        "support_capacity": (
            normalized["supports"]["level"],
            _positive(normalized["supports"]["level"]),
            "Recorded access to support increases recovery capacity.",
        ),
        "clarity_capacity": (
            normalized["capacity"]["clarity_level"],
            _positive(normalized["capacity"]["clarity_level"]),
            "Recorded clarity supports prioritization and a bounded next step.",
        ),
        "action_readiness": (
            action_count,
            action_value,
            "Readiness increases with up to four distinct response or next-step actions.",
        ),
        "constraint_manageability": (
            len(normalized["constraints"]["items"]),
            _constraint_manageability(normalized["constraints"]["items"]),
            "Manageability reflects the recorded controllability of constraints; no listed constraints defaults to full manageability.",
        ),
    }
    scores: dict[str, dict[str, Any]] = {}
    for key in weights:
        input_value, normalized_value, explanation = raw[key]
        weight = float(weights[key])
        scores[key] = {
            "input_value": input_value,
            "normalized_value": _round_half_up(normalized_value, 4),
            "weight": weight,
            "weighted_score": _round_half_up(normalized_value * weight, 1),
            "explanation": explanation,
        }
    return scores


def calculate_recovery_score(
    record: Mapping[str, Any], profile: Mapping[str, Any] | None = None
) -> float:
    """Calculate the composite conditions score from normalized sections.

    A canonical request may also be supplied; it is normalized first.
    """
    methodology = normalize_methodology_profile(profile)
    normalized = record
    if "impact" not in record:
        normalized = normalize_input(record)["input"]
    components = calculate_component_scores(normalized, methodology)
    return _round_half_up(sum(item["normalized_value"] * item["weight"] for item in components.values()), 1)


def state_from_score(score: float, profile: Mapping[str, Any] | None = None) -> str:
    methodology = normalize_methodology_profile(profile)
    thresholds = methodology["thresholds"]
    if score >= thresholds["stable"]:
        return "stable recovery conditions"
    if score >= thresholds["focused_support"]:
        return "recoverable with focused support"
    if score >= thresholds["fragile"]:
        return "fragile recovery conditions"
    return "high-friction recovery conditions"


def build_condition_map(normalized: Mapping[str, Any]) -> dict[str, Any]:
    """Build inspectable pressure, constraint, support, capacity, control, and friction maps."""
    pressure_items = [
        {"code": "overall_pressure", "label": "Overall pressure", "value": normalized["pressure"]["level"], "source_path": "$.input.pressure.level", "layer": "immediate", "control_zone": "influence"},
        {"code": "decision_ambiguity", "label": "Decision ambiguity", "value": normalized["pressure"]["decision_ambiguity"], "source_path": "$.input.pressure.decision_ambiguity", "layer": "near_term", "control_zone": "influence"},
        {"code": "dependency_friction", "label": "Dependency friction", "value": normalized["pressure"]["dependency_friction"], "source_path": "$.input.pressure.dependency_friction", "layer": "near_term", "control_zone": "influence"},
        {"code": "stakeholder_friction", "label": "Stakeholder friction", "value": normalized["pressure"]["stakeholder_friction"], "source_path": "$.input.pressure.stakeholder_friction", "layer": "near_term", "control_zone": "influence"},
        {"code": "load_level", "label": "Competing load", "value": normalized["capacity"]["load_level"], "source_path": "$.input.capacity.load_level", "layer": "immediate", "control_zone": "control"},
    ]
    constraints = []
    for index, item in enumerate(normalized["constraints"]["items"]):
        constraints.append({**item, "source_path": f"$.input.constraints.items[{index}]"})
    supports = []
    for index, item in enumerate(normalized["supports"]["available"]):
        supports.append({**item, "source_path": f"$.input.supports.available[{index}]"})
    capacity = [
        {"code": "energy", "label": "Energy capacity", "value": normalized["capacity"]["energy_level"], "source_path": "$.input.capacity.energy_level"},
        {"code": "clarity", "label": "Decision clarity", "value": normalized["capacity"]["clarity_level"], "source_path": "$.input.capacity.clarity_level"},
        {"code": "attention", "label": "Attention capacity", "value": normalized["capacity"]["attention_level"], "source_path": "$.input.capacity.attention_level"},
        {"code": "coordination", "label": "Coordination capacity", "value": normalized["capacity"]["coordination_capacity"], "source_path": "$.input.capacity.coordination_capacity"},
        {"code": "support_access", "label": "Support access", "value": normalized["supports"]["level"], "source_path": "$.input.supports.level"},
    ]
    control_view = {zone: [] for zone in ("control", "influence", "outside_control", "unknown")}
    for item in constraints:
        control_view[item["control_zone"]].append({"label": item["label"], "source_path": item["source_path"], "kind": "constraint"})
    for item in pressure_items:
        control_view[item["control_zone"]].append({"label": item["label"], "source_path": item["source_path"], "kind": "pressure"})
    friction_layers = {layer: [] for layer in ("immediate", "near_term", "structural")}
    for item in constraints:
        friction_layers[item["layer"]].append({"label": item["label"], "severity": item["severity"], "source_path": item["source_path"]})
    for item in pressure_items:
        friction_layers[item["layer"]].append({"label": item["label"], "severity": item["value"], "source_path": item["source_path"]})
    return {"pressure_map": pressure_items, "constraint_map": constraints, "support_map": supports, "capacity_profile": capacity, "control_view": control_view, "friction_layers": friction_layers}


def build_interpretation(normalized: Mapping[str, Any]) -> dict[str, Any]:
    checks = [
        ("$.input.context.description", bool(normalized["context"]["description"]), "Describe the affected situation and work."),
        ("$.input.context.affected_work", bool(normalized["context"]["affected_work"]), "List the work, decisions, or relationships affected."),
        ("$.input.pressure.sources", bool(normalized["pressure"]["sources"]), "Name the main pressure sources."),
        ("$.input.pressure.competing_demands", bool(normalized["pressure"]["competing_demands"]), "Record competing demands that consume capacity."),
        ("$.input.constraints.items", bool(normalized["constraints"]["items"]), "Map at least one constraint and its control zone."),
        ("$.input.supports.available", bool(normalized["supports"]["available"]), "Identify available or potential support channels."),
        ("$.input.capacity.available_time_hours", normalized["capacity"]["available_time_hours"] is not None, "Estimate available work time."),
        ("$.input.capacity.recovery_time_hours", normalized["capacity"]["recovery_time_hours"] is not None, "Estimate protected recovery time."),
        ("$.input.next_steps.checkpoint_date", normalized["next_steps"]["checkpoint_date"] is not None, "Set a checkpoint date."),
        ("$.input.next_steps.success_signal", bool(normalized["next_steps"]["success_signal"]), "Define an observable success signal."),
    ]
    missing = [{"path": path, "prompt": prompt} for path, present, prompt in checks if not present]
    percent = _round_half_up((len(checks) - len(missing)) / len(checks) * 100, 1)
    contradictions = []
    def contradiction(code: str, paths: list[str], message: str, prompt: str) -> None:
        contradictions.append({"code": code, "source_paths": paths, "message": message, "review_prompt": prompt})
    if normalized["supports"]["level"] >= 8 and not normalized["supports"]["available"]:
        contradiction("support_without_channel", ["$.input.supports.level", "$.input.supports.available"], "High support access is recorded without a named support channel.", "Name the support channel or revise the support level.")
    if normalized["capacity"]["clarity_level"] >= 8 and normalized["pressure"]["decision_ambiguity"] >= 8:
        contradiction("clarity_ambiguity_conflict", ["$.input.capacity.clarity_level", "$.input.pressure.decision_ambiguity"], "High clarity and high decision ambiguity are both recorded.", "Clarify whether personal task clarity differs from system-level decision ambiguity.")
    if normalized["capacity"]["available_time_hours"] is not None and normalized["capacity"]["recovery_time_hours"] is not None and normalized["capacity"]["recovery_time_hours"] > normalized["capacity"]["available_time_hours"]:
        contradiction("recovery_time_exceeds_available", ["$.input.capacity.recovery_time_hours", "$.input.capacity.available_time_hours"], "Protected recovery time exceeds total available time.", "Revise the estimates or explain the separate time windows.")
    if normalized["pressure"]["level"] >= 8 and normalized["capacity"]["load_level"] <= 3:
        contradiction("pressure_load_conflict", ["$.input.pressure.level", "$.input.capacity.load_level"], "High pressure is recorded alongside low competing load.", "Explain whether pressure is driven by urgency, consequences, or external uncertainty rather than workload.")
    confidence_score = max(0.0, percent - len(contradictions) * 10.0)
    level = "high" if confidence_score >= 80 else "moderate" if confidence_score >= 55 else "low"
    return {
        "completeness": {"percent": percent, "present_fields": len(checks) - len(missing), "total_fields": len(checks), "missing_context": missing},
        "confidence": {"level": level, "score": _round_half_up(confidence_score, 1), "rationale": "Confidence reflects recorded context completeness and unresolved contradictions, not certainty about future outcomes."},
        "contradictions": contradictions,
        "review_required": bool(missing or contradictions),
        "score_display_policy": {"mode": "component_context_required", "message": "The composite conditions score must be shown with component explanations and condition maps."},
    }


def build_flags(normalized: Mapping[str, Any]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []

    def add(code: str, severity: str, section: str, message: str, rationale: str, paths: list[str], conditions: dict[str, Any]) -> None:
        flags.append({"code": code, "severity": severity, "section": section, "message": message, "rationale": rationale, "source_paths": paths, "input_conditions": conditions})

    if normalized["impact"]["severity"] >= 8:
        add("high_impact", "high", "impact", "Reduce scope and protect recovery time.", "Impact severity is recorded at 8 or above.", ["$.input.impact.severity"], {"impact_severity": normalized["impact"]["severity"]})
    if normalized["pressure"]["level"] >= 8:
        add("high_pressure", "high", "pressure", "Clarify what can pause, wait, or be delegated.", "Pressure is recorded at 8 or above.", ["$.input.pressure.level"], {"pressure_level": normalized["pressure"]["level"]})
    if normalized["pressure"]["decision_ambiguity"] >= 8:
        add("decision_ambiguity", "high", "pressure", "Name the decision, owner, and information still needed.", "Decision ambiguity is recorded at 8 or above.", ["$.input.pressure.decision_ambiguity"], {"decision_ambiguity": normalized["pressure"]["decision_ambiguity"]})
    if normalized["pressure"]["dependency_friction"] >= 8:
        add("dependency_friction", "high", "constraints", "Route the dependency to an owner or escalation path.", "Dependency friction is recorded at 8 or above.", ["$.input.pressure.dependency_friction"], {"dependency_friction": normalized["pressure"]["dependency_friction"]})
    if normalized["capacity"]["energy_level"] <= 3:
        add("low_energy_capacity", "high", "capacity", "Avoid overloading the next action plan.", "Energy capacity is recorded at 3 or below.", ["$.input.capacity.energy_level"], {"energy_level": normalized["capacity"]["energy_level"]})
    if normalized["supports"]["level"] <= 3:
        add("low_support_capacity", "high", "supports", "Identify one concrete support channel before expanding work.", "Support capacity is recorded at 3 or below.", ["$.input.supports.level"], {"support_level": normalized["supports"]["level"]})
    if normalized["capacity"]["clarity_level"] <= 3:
        add("low_clarity_capacity", "high", "capacity", "Define the decision, owner, and next checkpoint.", "Clarity is recorded at 3 or below.", ["$.input.capacity.clarity_level"], {"clarity_level": normalized["capacity"]["clarity_level"]})
    if normalized["capacity"]["time_horizon_days"] <= 3:
        add("short_horizon", "medium", "capacity", "Choose a recovery action that can be completed quickly.", "The time horizon is three days or less.", ["$.input.capacity.time_horizon_days"], {"time_horizon_days": normalized["capacity"]["time_horizon_days"]})
    limited = [item for item in normalized["constraints"]["items"] if item["control_zone"] == "outside_control"]
    if len(limited) >= 2:
        paths = [f"$.input.constraints.items[{i}]" for i,item in enumerate(normalized["constraints"]["items"]) if item["control_zone"] == "outside_control"]
        add("outside_control_constraints", "medium", "constraints", "Separate adaptation work from constraints requiring accommodation or escalation.", "Two or more constraints are outside direct control.", paths, {"count": len(limited)})
    return flags


def build_recovery_plan(normalized: Mapping[str, Any], *, as_of: str | None = None) -> dict[str, Any]:
    """Build an executable, non-punitive plan view from normalized actions."""
    actions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for section in ("response", "next_steps"):
        for ordinal, source in enumerate(normalized[section]["actions"]):
            key = source["action_key"]
            if key in seen:
                key = f"{section}-{key}"
            seen.add(key)
            item = deepcopy(source)
            item["action_key"] = key
            item["source_section"] = section
            item["ordinal"] = ordinal
            actions.append(item)

    checkpoint_date = normalized["next_steps"]["checkpoint_date"]
    compatibility_defaults: list[str] = []
    if not actions:
        raise _issue("$.input.next_steps.actions", "plan_action_required", "A recovery plan requires at least one action.")
    if not any(item["owner"] for item in actions):
        actions[0]["owner"] = "self"
        compatibility_defaults.append("Assigned the first action to self because the imported plan had no owner.")
    if not checkpoint_date:
        base = date.fromisoformat(as_of) if as_of else datetime.now(timezone.utc).date()
        checkpoint_date = (base + timedelta(days=7)).isoformat()
        compatibility_defaults.append("Scheduled a seven-day review checkpoint because the imported plan had no checkpoint.")

    horizon_order = {"24_hours": 0, "72_hours": 1, "7_days": 2, "longer_term": 3}
    status_order = {"in_progress": 0, "planned": 1, "blocked": 2, "paused": 3, "deferred": 4, "completed": 5, "cancelled": 6}
    actions.sort(key=lambda item: (horizon_order[item["horizon"]], status_order[item["status"]], -item["urgency"], item["ordinal"]))
    smallest = next((item for item in actions if item["status"] not in {"completed", "cancelled"}), actions[0])
    by_horizon = {key: [] for key in ("24_hours", "72_hours", "7_days", "longer_term")}
    for item in actions:
        by_horizon[item["horizon"]].append(item)

    keys = {item["action_key"] for item in actions}
    dependency_sequence = []
    unresolved_dependencies = []
    for item in actions:
        internal = [dep for dep in item["dependencies"] if dep in keys]
        external = [dep for dep in item["dependencies"] if dep not in keys]
        dependency_sequence.append({"action_key": item["action_key"], "depends_on": internal, "external_dependencies": external})
        unresolved_dependencies.extend({"action_key": item["action_key"], "dependency": dep} for dep in external)

    blocked = [
        {"action_key": item["action_key"], "title": item["title"], "blocked_reason": item["blocked_reason"], "required_support": item["required_support"], "escalation_path": item["escalation_path"]}
        for item in actions if item["status"] == "blocked"
    ]
    today = date.fromisoformat(as_of) if as_of else datetime.now(timezone.utc).date()
    due_for_review = []
    for item in actions:
        if item["target_date"] and item["status"] not in {"completed", "cancelled"}:
            target = date.fromisoformat(item["target_date"])
            if target < today:
                due_for_review.append({"action_key": item["action_key"], "title": item["title"], "target_date": item["target_date"], "days_past_target": (today - target).days, "message": "Target date passed; review support, scope, or sequencing without assigning blame."})

    return {
        "plan_status": "needs_support" if blocked else "ready",
        "smallest_recoverable_next_step": smallest,
        "horizons": by_horizon,
        "dependency_sequence": dependency_sequence,
        "unresolved_dependencies": unresolved_dependencies,
        "scope_decision": {
            "decision": normalized["next_steps"]["scope_decision"],
            "notes": normalized["next_steps"]["scope_decision_notes"],
        },
        "checkpoint": {
            "scheduled_for": checkpoint_date,
            "success_signal": normalized["next_steps"]["success_signal"],
            "reassessment_trigger": normalized["next_steps"]["reassessment_trigger"],
        },
        "blocker_log": blocked + [{"action_key": None, "title": item, "blocked_reason": item, "required_support": [], "escalation_path": ""} for item in normalized["next_steps"]["blockers"]],
        "escalation_log": list(normalized["next_steps"]["escalation_log"]),
        "changed_assumptions": list(normalized["next_steps"]["changed_assumptions"]),
        "due_for_review": due_for_review,
        "compatibility_defaults": compatibility_defaults,
        "plan_rules": [
            "At least one action has a named owner.",
            "A dated checkpoint is required.",
            "Blocked and past-target actions are support signals, not performance judgments.",
            "Reassessment creates a new record revision and preserves prior findings.",
        ],
    }


def build_retrospective(normalized: Mapping[str, Any]) -> dict[str, Any]:
    """Build an evidence-preserving retrospective without inventing certainty."""
    learning = normalized["learning"]
    what_happened = learning["what_happened"] or normalized["trigger"]["summary"]
    expected = learning["what_was_expected"]
    changed = learning["what_changed"]
    learned = list(dict.fromkeys([*learning["what_was_learned"], *learning["observations"]]))
    repeat = list(dict.fromkeys([*learning["repeat"], *learning["what_helped"]]))
    redesign = list(dict.fromkeys([*learning["redesign"], *learning["adaptations"]]))
    fields = [what_happened, expected, changed, learning["what_helped"], learning["what_hindered"], learned, repeat, redesign, learning["uncertainties"]]
    completed = sum(bool(item) for item in fields)
    return {
        "what_happened": what_happened,
        "what_was_expected": expected,
        "what_changed": changed,
        "what_helped": list(learning["what_helped"]),
        "what_hindered": list(learning["what_hindered"]),
        "what_was_learned": learned,
        "repeat": repeat,
        "redesign": redesign,
        "uncertainties": list(learning["uncertainties"]),
        "completion": {
            "percent": _round_half_up(completed / len(fields) * 100, 1),
            "completed_fields": completed,
            "total_fields": len(fields),
        },
        "evidence_paths": {
            "what_happened": "$.input.learning.what_happened" if learning["what_happened"] else "$.input.trigger.summary",
            "what_was_expected": "$.input.learning.what_was_expected",
            "what_changed": "$.input.learning.what_changed",
            "what_helped": "$.input.learning.what_helped",
            "what_hindered": "$.input.learning.what_hindered",
            "what_was_learned": "$.input.learning.what_was_learned",
            "repeat": "$.input.learning.repeat",
            "redesign": "$.input.learning.redesign",
            "uncertainties": "$.input.learning.uncertainties",
        },
        "interpretation_limit": "The retrospective records supplied observations and uncertainty; it does not establish causation by itself.",
    }


def build_adaptation_patterns(normalized: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Create explainable, reviewable pattern candidates from recorded conditions."""
    patterns: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(category: str, label: str, path: str, value: Any, *, basis: str = "recorded", candidate: str = "") -> None:
        clean = str(label).strip()
        if not clean:
            return
        key = f"{category}:{_pattern_slug(clean)}"
        if key in seen:
            return
        seen.add(key)
        patterns.append({
            "pattern_key": key,
            "category": category,
            "label": clean,
            "status": "inferred",
            "basis": basis,
            "occurrence_count": 1,
            "evidence": [{"source_path": path, "value": deepcopy(value)}],
            "adaptation_candidate": candidate,
            "review": {"decision": None, "corrected_label": "", "notes": ""},
            "interpretation": "Candidate pattern derived from recorded conditions; confirm, reject, or correct before reuse.",
        })

    for index, item in enumerate(normalized["pressure"]["sources"]):
        add("recurring_pressure", item, f"$.input.pressure.sources[{index}]", item)
    for index, item in enumerate(normalized["pressure"]["competing_demands"]):
        add("scope_workload", item, f"$.input.pressure.competing_demands[{index}]", item)
    for index, item in enumerate(normalized["constraints"]["items"]):
        if item["type"] == "dependency":
            add("dependency_failure", item["label"], f"$.input.constraints.items[{index}]", item)
    for index, item in enumerate(normalized["supports"]["available"]):
        if item["status"] != "active" or item["reliability"] <= 4:
            add("support_gap", item["label"], f"$.input.supports.available[{index}]", item)
    if normalized["supports"]["level"] <= 4:
        add("support_gap", "Low recorded support capacity", "$.input.supports.level", normalized["supports"]["level"])
    if normalized["capacity"]["clarity_level"] <= 4 or normalized["pressure"]["decision_ambiguity"] >= 7:
        add("clarity_failure", "Decision or recovery clarity gap", "$.input.capacity.clarity_level", normalized["capacity"]["clarity_level"])
    if normalized["capacity"]["load_level"] >= 7:
        add("scope_workload", "High competing load", "$.input.capacity.load_level", normalized["capacity"]["load_level"])
    for index, item in enumerate(normalized["learning"]["what_helped"]):
        add("recovery_action_helped", item, f"$.input.learning.what_helped[{index}]", item, basis="user_observation")
    for index, item in enumerate(normalized["learning"]["what_hindered"]):
        add("action_did_not_help", item, f"$.input.learning.what_hindered[{index}]", item, basis="user_observation")
    candidates = list(dict.fromkeys([*normalized["learning"]["redesign"], *normalized["learning"]["adaptations"]]))
    for index, item in enumerate(candidates):
        add("adaptation_candidate", item, f"$.input.learning.redesign[{index}]", item, basis="user_proposed", candidate=item)

    reviews = {item["pattern_key"]: item for item in normalized["learning"]["pattern_reviews"]}
    for item in patterns:
        review = reviews.get(item["pattern_key"])
        if not review:
            continue
        item["review"] = deepcopy(review)
        item["status"] = {"accept": "accepted", "reject": "rejected", "correct": "corrected"}[review["decision"]]
        if review["decision"] == "correct":
            item["label"] = review["corrected_label"]
    return patterns


def build_learning_loop(normalized: Mapping[str, Any]) -> dict[str, Any]:
    retrospective = build_retrospective(normalized)
    patterns = build_adaptation_patterns(normalized)
    active_patterns = [item for item in patterns if item["status"] != "rejected"]
    candidates = []
    for item in active_patterns:
        candidate = item["adaptation_candidate"]
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return {
        "retrospective": retrospective,
        "patterns": patterns,
        "adaptation_candidates": candidates,
        "review_required": any(item["status"] == "inferred" for item in patterns),
        "review_guidance": "Patterns remain proposals until a user accepts, rejects, or corrects them.",
        "system_change_guidance": "Link any process change to the records and evidence that motivated it, then record an adopt, revise, defer, or retire decision after the pilot.",
        "personality_labeling_prohibited": True,
    }


def build_next_actions(normalized: Mapping[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(code: str, title: str, rationale: str, source: str, priority: str) -> None:
        key = title.strip().lower()
        if key and key not in seen and len(output) < 6:
            seen.add(key)
            output.append({"code": code, "title": title, "rationale": rationale, "source": source, "priority": priority})

    user_actions = [*normalized["next_steps"]["actions"], *normalized["response"]["actions"]]
    for index, action in enumerate(user_actions):
        add(
            f"user_action_{index + 1}",
            action["title"],
            "Preserved from the recorded response or next-step plan.",
            "user",
            "high" if index == 0 else "medium",
        )
    if normalized["capacity"]["clarity_level"] <= 5:
        add("define_recovery", "Write a one-sentence definition of recovery for this situation.", "Clarity is at or below the midpoint.", "engine", "high")
    if normalized["supports"]["level"] <= 5:
        add("request_support", "Ask for one specific form of support or remove one friction point.", "Support is at or below the midpoint.", "engine", "high")
    if normalized["pressure"]["level"] >= 7:
        add("bound_checkpoint", "Reduce the work to one near-term checkpoint instead of a full reset.", "Pressure is elevated.", "engine", "high")
    if normalized["constraints"]["items"]:
        add("map_constraints", "Mark each constraint as controllable, influenceable, or limited.", "Recorded constraints should be routed differently based on controllability.", "engine", "medium")
    if not output:
        for index, title in enumerate(DEFAULT_ACTIONS):
            add(f"default_action_{index + 1}", title, "Default recovery-planning prompt.", "engine", "medium")
    return output


def generate_record(
    data: Mapping[str, Any],
    methodology_profile: Mapping[str, Any] | None = None,
) -> RecoveryRecord:
    """Generate a canonical v1.5 recovery record with learning loops and adaptation patterns."""
    canonical = normalize_input(data)
    normalized = canonical["input"]
    profile = normalize_methodology_profile(methodology_profile or canonical["methodology_profile"])
    components = calculate_component_scores(normalized, profile)
    score = _round_half_up(sum(item["normalized_value"] * item["weight"] for item in components.values()), 1)
    generated_state = state_from_score(score, profile)
    human_state = canonical["human_review"]["override_state"]
    effective_state = human_state or generated_state
    condition_map = build_condition_map(normalized)
    interpretation = build_interpretation(normalized)
    flags = build_flags(normalized)
    actions = build_next_actions(normalized)
    recovery_plan = build_recovery_plan(normalized, as_of=canonical["metadata"]["updated_at"][:10])
    learning_loop = build_learning_loop(normalized)
    note = (
        f"Recorded recovery conditions are assessed as {generated_state}. The composite conditions score is {score}/100 and must be interpreted with the pressure, constraint, support, capacity, and component maps. "
        "Protect available capacity, address the highest-friction condition, "
        "and update the record at the next checkpoint."
    )
    findings = {
        "methodology": profile,
        "condition_map": condition_map,
        "interpretation": interpretation,
        "component_scores": components,
        "recovery_score": score,
        "generated_state": generated_state,
        "effective_state": effective_state,
        "human_override_applied": bool(human_state),
        "flags": flags,
        "recommended_actions": actions,
        "recovery_plan": recovery_plan,
        "retrospective": learning_loop["retrospective"],
        "adaptation_patterns": learning_loop["patterns"],
        "learning_loop": learning_loop,
        "decision_note": note,
        "method_path": list(METHOD_PATH),
        "interpretation_limits": list(INTERPRETATION_LIMITS),
        "calculation_provenance": {
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "profile_id": profile["profile_id"],
            "profile_version": profile["profile_version"],
            "calculated_at": canonical["metadata"]["updated_at"],
        },
    }
    return RecoveryRecord(
        metadata=canonical["metadata"],
        user_input=canonical["user_input"],
        normalized_input=normalized,
        findings=findings,
        human_review=canonical["human_review"],
        extensions=canonical["extensions"],
    )


def validate_request(data: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return the canonical normalized request."""
    canonical = normalize_input(data)
    return {
        "metadata": canonical["metadata"],
        "normalized_input": canonical["input"],
        "human_review": canonical["human_review"],
        "extensions": canonical["extensions"],
        "methodology_profile": canonical["methodology_profile"],
        "migrated": canonical["migrated"],
    }


def to_markdown(output: RecoveryRecord) -> str:
    flags = "\n".join(
        f"- **{item['severity'].title()} · {item['section']}:** {item['message']}"
        for item in output.findings["flags"]
    ) or "- No major review flags generated."
    actions = "\n".join(
        f"- **{item['priority'].title()}:** {item['title']} — {item['rationale']}"
        for item in output.findings["recommended_actions"]
    )
    components = "\n".join(
        f"- **{name.replace('_', ' ').title()}:** {item['weighted_score']}/{item['weight']} — {item['explanation']}"
        for name, item in output.findings["component_scores"].items()
    )
    condition_map = output.findings["condition_map"]
    pressure_map = "\n".join(f"- **{item['label']}:** {item['value']}/10 — `{item['source_path']}`" for item in condition_map["pressure_map"])
    constraints_map = "\n".join(f"- **{item['label']}:** {item['control_zone'].replace('_',' ')} · {item['layer'].replace('_',' ')} · {item['severity']}/10" for item in condition_map["constraint_map"]) or "- No constraints mapped."
    supports_map = "\n".join(f"- **{item['label']}:** {item['status']} · reliability {item['reliability']}/10 · contribution {item['capacity_contribution']}/10" for item in condition_map["support_map"]) or "- No support channels mapped."
    missing_context = "\n".join(f"- `{item['path']}` — {item['prompt']}" for item in output.findings["interpretation"]["completeness"]["missing_context"]) or "- No required context prompts remain."
    contradictions = "\n".join(f"- **{item['code']}:** {item['message']}" for item in output.findings["interpretation"]["contradictions"]) or "- No contradictions detected."
    retrospective = output.findings["retrospective"]
    pattern_lines = "\n".join(
        f"- **{item['category'].replace('_', ' ').title()}:** {item['label']} — {item['status']} · evidence `{item['evidence'][0]['source_path']}`"
        for item in output.findings["adaptation_patterns"]
    ) or "- No pattern candidates generated."
    repeat_lines = "\n".join(f"- {item}" for item in retrospective["repeat"]) or "- Nothing recorded yet."
    redesign_lines = "\n".join(f"- {item}" for item in retrospective["redesign"]) or "- Nothing recorded yet."
    uncertainty_lines = "\n".join(f"- {item}" for item in retrospective["uncertainties"]) or "- No uncertainty recorded."
    metadata = output.metadata
    context = output.normalized_input["context"]
    return f"""# Catalyst Grit Recovery Brief

## Record

- **Record ID:** {metadata['record_id']}
- **Status:** {metadata['status']}
- **Created:** {metadata['created_at']}
- **Updated:** {metadata['updated_at']}
- **Domain:** {context['domain']}

## Context

### {context['title']}

{context['description'] or output.normalized_input['trigger']['summary']}

## Condition maps

### Pressure map

{pressure_map}

### Constraint map

{constraints_map}

### Support map

{supports_map}

### Completeness and review

- **Completeness:** {output.findings['interpretation']['completeness']['percent']}%
- **Confidence:** {output.findings['interpretation']['confidence']['level']} ({output.findings['interpretation']['confidence']['score']}/100)

#### Missing-context prompts

{missing_context}

#### Contradictions

{contradictions}

## Recovery conditions

- **Score (component context required):** {output.findings['recovery_score']}/100
- **Generated state:** {output.findings['generated_state']}
- **Effective state:** {output.findings['effective_state']}
- **Methodology:** {output.findings['methodology']['profile_id']} v{output.findings['methodology']['profile_version']}

## Component scores

{components}

## Review flags

{flags}

## Recommended actions

{actions}

## Learning loop

- **What happened:** {retrospective['what_happened'] or 'Not recorded'}
- **What was expected:** {retrospective['what_was_expected'] or 'Not recorded'}
- **What changed:** {retrospective['what_changed'] or 'Not recorded'}
- **Retrospective completion:** {retrospective['completion']['percent']}%

### Repeat

{repeat_lines}

### Redesign

{redesign_lines}

### Uncertainty

{uncertainty_lines}

### Adaptation pattern candidates

{pattern_lines}

## Decision note

{output.findings['decision_note']}

## Human review

- **Review status:** {output.human_review['review_status']}
- **Reviewer:** {output.human_review['reviewer'] or 'Not assigned'}
- **Override applied:** {'Yes' if output.findings['human_override_applied'] else 'No'}

## Interpretation limits

""" + "\n".join(f"- {item}" for item in output.findings["interpretation_limits"]) + f"""

## Release provenance

- **Schema version:** {metadata['schema_version']}
- **Engine version:** {metadata['engine_version']}
- **Method path:** {' → '.join(output.findings['method_path'])}
"""
