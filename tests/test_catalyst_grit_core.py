import pytest

from catalyst_grit import (
    GritValidationError,
    calculate_recovery_score,
    generate_record,
    normalize_input,
    state_from_score,
)


def sample_input(**overrides):
    data = {
        "challenge": "A project stalled after feedback changed.",
        "domain": "project",
        "impact_severity": 7,
        "pressure_level": 8,
        "energy_level": 5,
        "support_level": 6,
        "clarity_level": 4,
        "recovery_actions": ["Clarify owner", "Set checkpoint"],
        "time_horizon_days": 14,
        "review_status": "draft",
    }
    data.update(overrides)
    return data


def test_generate_record_has_score_actions_and_provenance():
    record = generate_record(sample_input())
    assert 0 <= record.recovery_score <= 100
    assert record.next_actions
    assert "recovery" in record.decision_note.lower()
    assert record.schema_version == "1.0.1"
    assert record.engine_version == "1.0.1"


@pytest.mark.parametrize(
    ("score", "state"),
    [
        (100, "stable recovery conditions"),
        (76, "stable recovery conditions"),
        (75.9, "recoverable with focused support"),
        (56, "recoverable with focused support"),
        (55.9, "fragile recovery conditions"),
        (36, "fragile recovery conditions"),
        (35.9, "high-friction recovery conditions"),
    ],
)
def test_state_boundaries(score, state):
    assert state_from_score(score) == state


def test_numeric_scales_are_clamped():
    record = normalize_input(sample_input(impact_severity=99, energy_level=-4))
    assert record.impact_severity == 10
    assert record.energy_level == 1


def test_default_actions_are_supplied_for_empty_list():
    record = generate_record(sample_input(recovery_actions=[]))
    assert len(record.recovery_actions) == 3


def test_string_actions_are_split_by_line():
    record = generate_record(sample_input(recovery_actions="One\nTwo\n"))
    assert record.recovery_actions == ["One", "Two"]


def test_high_friction_conditions_generate_all_relevant_flags():
    record = generate_record(sample_input(
        impact_severity=9,
        pressure_level=9,
        energy_level=2,
        support_level=2,
        clarity_level=2,
        time_horizon_days=2,
    ))
    assert len(record.risk_flags) == 6


def test_invalid_domain_fails_closed():
    with pytest.raises(GritValidationError, match="domain"):
        generate_record(sample_input(domain="personality_score"))


def test_invalid_review_status_fails_closed():
    with pytest.raises(GritValidationError, match="review_status"):
        generate_record(sample_input(review_status="ranked"))


def test_invalid_numeric_value_is_rejected():
    with pytest.raises(GritValidationError, match="pressure_level"):
        generate_record(sample_input(pressure_level="high"))


def test_score_is_deterministic():
    normalized = normalize_input(sample_input())
    assert calculate_recovery_score(normalized) == calculate_recovery_score(normalized)
