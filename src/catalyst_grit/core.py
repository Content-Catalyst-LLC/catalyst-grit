"""Canonical Catalyst Grit recovery-record domain engine."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from .version import ENGINE_VERSION, SCHEMA_VERSION

METHOD_PATH = [
    "setback",
    "context",
    "impact",
    "pressure",
    "support",
    "response",
    "recovery pattern",
    "next action",
    "review",
]
ALLOWED_DOMAINS = {
    "work",
    "learning",
    "health_wellbeing",
    "relationship",
    "project",
    "career",
    "other",
}
ALLOWED_REVIEW_STATUSES = {"draft", "needs_review", "reviewed"}
DEFAULT_ACTIONS = [
    "Name the smallest recoverable next step",
    "Review support and constraints",
    "Schedule a short follow-up review",
]


class GritValidationError(ValueError):
    """Raised when a recovery-record input cannot be normalized safely."""


@dataclass(frozen=True)
class GritInput:
    challenge: str
    domain: str = "project"
    impact_severity: float = 5
    pressure_level: float = 5
    energy_level: float = 5
    support_level: float = 5
    clarity_level: float = 5
    recovery_actions: list[str] | None = None
    time_horizon_days: int = 14
    review_status: str = "draft"


@dataclass(frozen=True)
class GritOutput:
    challenge: str
    domain: str
    impact_severity: float
    pressure_level: float
    energy_level: float
    support_level: float
    clarity_level: float
    recovery_actions: list[str]
    time_horizon_days: int
    review_status: str
    recovery_score: float
    resilience_state: str
    risk_flags: list[str]
    next_actions: list[str]
    decision_note: str
    method_path: list[str]
    schema_version: str
    engine_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def clamp_scale(value: Any, field: str, low: float = 1, high: float = 10) -> float:
    """Normalize a numeric scale value to the supported inclusive range."""
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise GritValidationError(f"{field} must be numeric") from exc
    return max(low, min(high, number))


def clean_actions(actions: Iterable[Any] | None) -> list[str]:
    if actions is None:
        return list(DEFAULT_ACTIONS)
    if isinstance(actions, (str, bytes)):
        actions = str(actions).splitlines()
    cleaned = [str(action).strip() for action in actions if str(action).strip()]
    return cleaned or list(DEFAULT_ACTIONS)


def normalize_input(data: Mapping[str, Any]) -> GritInput:
    if not isinstance(data, Mapping):
        raise GritValidationError("input must be a JSON object")

    challenge = str(data.get("challenge", "")).strip() or "Unspecified challenge"
    domain = str(data.get("domain", "project")).strip() or "project"
    if domain not in ALLOWED_DOMAINS:
        raise GritValidationError(
            f"domain must be one of: {', '.join(sorted(ALLOWED_DOMAINS))}"
        )

    review_status = str(data.get("review_status", "draft")).strip() or "draft"
    if review_status not in ALLOWED_REVIEW_STATUSES:
        raise GritValidationError(
            "review_status must be one of: "
            + ", ".join(sorted(ALLOWED_REVIEW_STATUSES))
        )

    try:
        horizon = max(1, int(float(data.get("time_horizon_days", 14))))
    except (TypeError, ValueError) as exc:
        raise GritValidationError("time_horizon_days must be numeric") from exc

    return GritInput(
        challenge=challenge,
        domain=domain,
        impact_severity=clamp_scale(data.get("impact_severity", 5), "impact_severity"),
        pressure_level=clamp_scale(data.get("pressure_level", 5), "pressure_level"),
        energy_level=clamp_scale(data.get("energy_level", 5), "energy_level"),
        support_level=clamp_scale(data.get("support_level", 5), "support_level"),
        clarity_level=clamp_scale(data.get("clarity_level", 5), "clarity_level"),
        recovery_actions=clean_actions(data.get("recovery_actions")),
        time_horizon_days=horizon,
        review_status=review_status,
    )


def calculate_recovery_score(record: GritInput) -> float:
    actions = clean_actions(record.recovery_actions)
    action_bonus = min(10, len(actions) * 2.5)
    raw = (
        record.energy_level * 2.2
        + record.support_level * 2.3
        + record.clarity_level * 2.4
        + action_bonus
        + (10 - record.impact_severity) * 1.7
        + (10 - record.pressure_level) * 1.4
    )
    return round(max(0, min(100, raw)), 1)


def state_from_score(score: float) -> str:
    if score >= 76:
        return "stable recovery conditions"
    if score >= 56:
        return "recoverable with focused support"
    if score >= 36:
        return "fragile recovery conditions"
    return "high-friction recovery conditions"


def build_flags(record: GritInput) -> list[str]:
    flags: list[str] = []
    if record.impact_severity >= 8:
        flags.append("High impact severity: reduce scope and protect recovery time.")
    if record.pressure_level >= 8:
        flags.append("High pressure: clarify what can pause, wait, or be delegated.")
    if record.energy_level <= 3:
        flags.append("Low energy: avoid overloading the next action plan.")
    if record.support_level <= 3:
        flags.append(
            "Low support: identify one concrete support channel before expanding work."
        )
    if record.clarity_level <= 3:
        flags.append("Low clarity: define the decision, owner, and next checkpoint.")
    if record.time_horizon_days <= 3:
        flags.append(
            "Very short horizon: choose a recovery action that can be completed quickly."
        )
    return flags


def build_next_actions(record: GritInput) -> list[str]:
    next_actions = clean_actions(record.recovery_actions)[:4]
    if record.clarity_level <= 5:
        next_actions.append(
            "Write a one-sentence definition of what recovery means for this situation."
        )
    if record.support_level <= 5:
        next_actions.append(
            "Ask for one specific form of support or remove one friction point."
        )
    if record.pressure_level >= 7:
        next_actions.append(
            "Reduce the work to one near-term checkpoint instead of a full reset."
        )
    return next_actions[:6]


def generate_record(data: Mapping[str, Any]) -> GritOutput:
    record = normalize_input(data)
    score = calculate_recovery_score(record)
    state = state_from_score(score)
    flags = build_flags(record)
    next_actions = build_next_actions(record)
    note = (
        f"Recovery conditions are assessed as {state} with a score of {score}/100. "
        "Use this as a structured reflection record: clarify the next action, "
        "protect recovery capacity, review support, and update the plan after "
        "the next checkpoint."
    )
    return GritOutput(
        challenge=record.challenge,
        domain=record.domain,
        impact_severity=record.impact_severity,
        pressure_level=record.pressure_level,
        energy_level=record.energy_level,
        support_level=record.support_level,
        clarity_level=record.clarity_level,
        recovery_actions=clean_actions(record.recovery_actions),
        time_horizon_days=record.time_horizon_days,
        review_status=record.review_status,
        recovery_score=score,
        resilience_state=state,
        risk_flags=flags,
        next_actions=next_actions,
        decision_note=note,
        method_path=list(METHOD_PATH),
        schema_version=SCHEMA_VERSION,
        engine_version=ENGINE_VERSION,
    )


def to_markdown(output: GritOutput) -> str:
    flags = "\n".join(f"- {item}" for item in output.risk_flags)
    flags = flags or "- No major review flags generated."
    actions = "\n".join(f"- {item}" for item in output.next_actions)
    return f"""# Catalyst Grit Recovery Brief

## Challenge

{output.challenge}

## Recovery state

- **Score:** {output.recovery_score}/100
- **State:** {output.resilience_state}
- **Domain:** {output.domain}
- **Review status:** {output.review_status}

## Review flags

{flags}

## Next actions

{actions}

## Decision note

{output.decision_note}

## Method path

{' → '.join(output.method_path)}

## Release provenance

- **Schema version:** {output.schema_version}
- **Engine version:** {output.engine_version}
"""
