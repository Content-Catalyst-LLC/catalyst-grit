import copy
import json
from pathlib import Path

import pytest

from catalyst_grit import (
    DEFAULT_METHODOLOGY_PROFILE,
    GritValidationError,
    calculate_component_scores,
    calculate_recovery_score,
    generate_record,
    migrate_v1_request,
    normalize_input,
    normalize_methodology_profile,
    state_from_score,
    validate_request,
)

ROOT = Path(__file__).resolve().parents[1]


def sample():
    return json.loads((ROOT / "examples/grit_record_input.json").read_text())


def test_generated_record_separates_contract_layers():
    record = generate_record(sample()).to_dict()
    assert set(record) == {"metadata", "user_input", "normalized_input", "findings", "human_review", "extensions"}
    assert record["metadata"]["record_id"].startswith("cgr_")
    assert record["findings"]["calculation_provenance"]["engine_version"] == "2.0.0"


def test_all_explicit_sections_are_present():
    record = generate_record(sample())
    assert list(record.normalized_input) == ["context", "trigger", "impact", "pressure", "constraints", "supports", "capacity", "response", "learning", "next_steps"]


def test_component_weights_total_100():
    profile = normalize_methodology_profile()
    assert sum(profile["component_weights"].values()) == 100


def test_component_scores_are_explainable():
    canonical = normalize_input(sample())
    scores = calculate_component_scores(canonical["input"], canonical["methodology_profile"])
    assert len(scores) == 7
    assert all(item["explanation"] for item in scores.values())
    assert all(0 <= item["normalized_value"] <= 1 for item in scores.values())


def test_score_matches_components():
    record = generate_record(sample())
    calculated = sum(item["normalized_value"] * item["weight"] for item in record.findings["component_scores"].values())
    assert record.findings["recovery_score"] == pytest.approx(calculated, abs=0.1)


@pytest.mark.parametrize("score,state", [(75,"stable recovery conditions"),(55,"recoverable with focused support"),(35,"fragile recovery conditions"),(34.9,"high-friction recovery conditions")])
def test_default_threshold_boundaries(score, state):
    assert state_from_score(score) == state


def test_custom_thresholds_change_state_without_changing_engine():
    profile = copy.deepcopy(DEFAULT_METHODOLOGY_PROFILE)
    profile["profile_id"] = "test"
    profile["thresholds"] = {"stable": 40, "focused_support": 25, "fragile": 10}
    assert state_from_score(45, profile) == "stable recovery conditions"


def test_custom_weights_must_total_100():
    profile = copy.deepcopy(DEFAULT_METHODOLOGY_PROFILE)
    profile["component_weights"]["impact_buffer"] = 1
    with pytest.raises(GritValidationError) as error:
        normalize_methodology_profile(profile)
    assert error.value.issues[0].code == "weight_total"


def test_thresholds_must_descend():
    profile = copy.deepcopy(DEFAULT_METHODOLOGY_PROFILE)
    profile["thresholds"] = {"stable": 40, "focused_support": 50, "fragile": 10}
    with pytest.raises(GritValidationError, match="descend"):
        normalize_methodology_profile(profile)


def test_unknown_fields_fail_closed():
    data = sample(); data["input"]["context"]["personality"] = "gritty"
    with pytest.raises(GritValidationError) as error:
        generate_record(data)
    assert error.value.issues[0].code == "unknown_field"


def test_extensions_require_namespace():
    data = sample(); data["extensions"] = {"custom": 1}
    with pytest.raises(GritValidationError) as error:
        generate_record(data)
    assert error.value.issues[0].code == "extension_namespace"


def test_namespaced_extensions_are_preserved():
    data = sample(); data["extensions"] = {"org.example.case": {"id": 1}}
    assert generate_record(data).extensions == data["extensions"]


def test_reviewed_lifecycle_requires_reviewer_and_timestamp():
    data = sample(); data["metadata"]["status"] = "reviewed"; data["human_review"]["review_status"] = "reviewed"
    with pytest.raises(GritValidationError) as error:
        generate_record(data)
    assert error.value.issues[0].code == "review_lifecycle"


def test_human_override_is_explicit():
    data = sample(); data["human_review"]["override_state"] = "recoverable with focused support"
    record = generate_record(data)
    assert record.findings["human_override_applied"] is True
    assert record.findings["effective_state"] == "recoverable with focused support"


def test_v1_flat_input_migrates():
    legacy = json.loads((ROOT / "examples/grit_record_v1_0_input.json").read_text())
    migrated = migrate_v1_request(legacy)
    assert migrated["metadata"]["provenance"]["source"] == "migration"
    record = generate_record(legacy)
    assert record.metadata["provenance"]["source_schema_version"] == "1.0.1"


def test_validation_error_is_structured():
    data = sample(); data["input"]["impact"]["severity"] = "severe"
    with pytest.raises(GritValidationError) as error:
        validate_request(data)
    payload = error.value.to_dict()
    assert payload["error"] == "validation_failed"
    assert payload["issues"][0]["path"] == "$.input.impact.severity"


def test_low_conditions_generate_contextual_flags():
    fixtures = json.loads((ROOT / "tests/fixtures/parity_cases.json").read_text())
    high = next(item for item in fixtures if item["name"] == "high-friction")
    record = generate_record(high["input"])
    assert len(record.findings["flags"]) == 7
    assert {flag["section"] for flag in record.findings["flags"]} >= {"impact", "pressure", "capacity", "supports", "constraints"}


def test_public_language_avoids_character_judgment():
    text = json.dumps(generate_record(sample()).to_dict()).lower()
    assert "personality score" not in text
    assert "character score" not in text
    assert "diagnose" in text
