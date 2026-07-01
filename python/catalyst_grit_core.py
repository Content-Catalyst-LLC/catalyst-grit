#!/usr/bin/env python3
"""Catalyst Grit recovery-record generator."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable


@dataclass
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


@dataclass
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


def _clamp(value: Any, low: float = 1, high: float = 10) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = low
    return max(low, min(high, number))


def _clean_actions(actions: Iterable[str] | None) -> list[str]:
    cleaned = [str(a).strip() for a in (actions or []) if str(a).strip()]
    return cleaned or ["Name the smallest recoverable next step", "Review support and constraints", "Schedule a short follow-up review"]


def calculate_recovery_score(record: GritInput) -> float:
    severity = _clamp(record.impact_severity)
    pressure = _clamp(record.pressure_level)
    energy = _clamp(record.energy_level)
    support = _clamp(record.support_level)
    clarity = _clamp(record.clarity_level)
    actions = _clean_actions(record.recovery_actions)
    action_bonus = min(10, len(actions) * 2.5)
    raw = (energy * 2.2) + (support * 2.3) + (clarity * 2.4) + action_bonus + (10 - severity) * 1.7 + (10 - pressure) * 1.4
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
    if _clamp(record.impact_severity) >= 8:
        flags.append("High impact severity: reduce scope and protect recovery time.")
    if _clamp(record.pressure_level) >= 8:
        flags.append("High pressure: clarify what can pause, wait, or be delegated.")
    if _clamp(record.energy_level) <= 3:
        flags.append("Low energy: avoid overloading the next action plan.")
    if _clamp(record.support_level) <= 3:
        flags.append("Low support: identify one concrete support channel before expanding work.")
    if _clamp(record.clarity_level) <= 3:
        flags.append("Low clarity: define the decision, owner, and next checkpoint.")
    if record.time_horizon_days <= 3:
        flags.append("Very short horizon: choose a recovery action that can be completed quickly.")
    return flags


def build_next_actions(record: GritInput) -> list[str]:
    actions = _clean_actions(record.recovery_actions)
    next_actions = actions[:4]
    if _clamp(record.clarity_level) <= 5:
        next_actions.append("Write a one-sentence definition of what recovery means for this situation.")
    if _clamp(record.support_level) <= 5:
        next_actions.append("Ask for one specific form of support or remove one friction point.")
    if _clamp(record.pressure_level) >= 7:
        next_actions.append("Reduce the work to one near-term checkpoint instead of a full reset.")
    return next_actions[:6]


def generate_record(data: dict[str, Any]) -> GritOutput:
    record = GritInput(
        challenge=str(data.get("challenge", "")).strip() or "Unspecified challenge",
        domain=str(data.get("domain", "project")).strip() or "project",
        impact_severity=_clamp(data.get("impact_severity", 5)),
        pressure_level=_clamp(data.get("pressure_level", 5)),
        energy_level=_clamp(data.get("energy_level", 5)),
        support_level=_clamp(data.get("support_level", 5)),
        clarity_level=_clamp(data.get("clarity_level", 5)),
        recovery_actions=_clean_actions(data.get("recovery_actions")),
        time_horizon_days=max(1, int(float(data.get("time_horizon_days", 14)))),
        review_status=str(data.get("review_status", "draft")).strip() or "draft",
    )
    score = calculate_recovery_score(record)
    state = state_from_score(score)
    flags = build_flags(record)
    next_actions = build_next_actions(record)
    note = (
        f"Recovery conditions are assessed as {state} with a score of {score}/100. "
        "Use this as a structured reflection record: clarify the next action, protect recovery capacity, "
        "review support, and update the plan after the next checkpoint."
    )
    return GritOutput(
        challenge=record.challenge,
        domain=record.domain,
        impact_severity=record.impact_severity,
        pressure_level=record.pressure_level,
        energy_level=record.energy_level,
        support_level=record.support_level,
        clarity_level=record.clarity_level,
        recovery_actions=_clean_actions(record.recovery_actions),
        time_horizon_days=record.time_horizon_days,
        review_status=record.review_status,
        recovery_score=score,
        resilience_state=state,
        risk_flags=flags,
        next_actions=next_actions,
        decision_note=note,
        method_path=["setback", "context", "impact", "pressure", "support", "response", "recovery pattern", "next action", "review"],
    )


def to_markdown(output: GritOutput) -> str:
    flags = "\n".join(f"- {item}" for item in output.risk_flags) or "- No major review flags generated."
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
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a Catalyst Grit recovery record.")
    parser.add_argument("input", type=Path, help="Path to input JSON")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    record = generate_record(data)
    rendered = json.dumps(asdict(record), indent=2) if args.format == "json" else to_markdown(record)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
