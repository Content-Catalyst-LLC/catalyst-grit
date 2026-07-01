from python.catalyst_grit_core import generate_record, state_from_score


def test_generate_record_has_score_and_actions():
    record = generate_record({
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
    })
    assert 0 <= record.recovery_score <= 100
    assert record.next_actions
    assert "recovery" in record.decision_note.lower()


def test_state_from_score_boundaries():
    assert state_from_score(90) == "stable recovery conditions"
    assert state_from_score(60) == "recoverable with focused support"
    assert state_from_score(40) == "fragile recovery conditions"
    assert state_from_score(20) == "high-friction recovery conditions"
