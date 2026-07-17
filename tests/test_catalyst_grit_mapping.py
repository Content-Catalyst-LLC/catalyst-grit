import copy
import json
from pathlib import Path

from catalyst_grit import build_condition_map, build_interpretation, generate_record, normalize_input

ROOT = Path(__file__).resolve().parents[1]

def sample():
    return json.loads((ROOT / "examples/grit_record_input.json").read_text())

def test_condition_maps_cover_all_v13_views():
    record = generate_record(sample()).to_dict()
    maps = record["findings"]["condition_map"]
    assert set(maps) == {"pressure_map", "constraint_map", "support_map", "capacity_profile", "control_view", "friction_layers"}
    assert len(maps["pressure_map"]) == 5
    assert maps["constraint_map"][0]["source_path"] == "$.input.constraints.items[0]"
    assert maps["control_view"]["outside_control"][0]["label"] == "Limited review window"

def test_every_flag_links_to_triggering_conditions():
    flags = generate_record(sample()).findings["flags"]
    assert flags
    assert all(item["source_paths"] and item["input_conditions"] for item in flags)
    assert all(path.startswith("$.input.") for item in flags for path in item["source_paths"])

def test_missing_context_and_contradictions_are_explicit():
    value = sample()
    value["input"]["context"]["affected_work"] = []
    value["input"]["supports"]["level"] = 9
    value["input"]["supports"]["available"] = []
    value["input"]["capacity"]["clarity_level"] = 9
    value["input"]["pressure"]["decision_ambiguity"] = 9
    interpretation = generate_record(value).findings["interpretation"]
    paths = {item["path"] for item in interpretation["completeness"]["missing_context"]}
    codes = {item["code"] for item in interpretation["contradictions"]}
    assert "$.input.context.affected_work" in paths
    assert {"support_without_channel", "clarity_ambiguity_conflict"} <= codes
    assert interpretation["review_required"] is True

def test_v12_request_receives_defaults_and_prompts():
    value = sample()
    value["metadata"]["schema_version"] = "1.2.0"
    for key in ["affected_work"]: value["input"]["context"].pop(key, None)
    for key in ["competing_demands","decision_ambiguity","dependency_friction","stakeholder_friction"]: value["input"]["pressure"].pop(key, None)
    for item in value["input"]["constraints"]["items"]:
        for key in ["control_zone","layer","severity","notes"]: item.pop(key, None)
    for item in value["input"]["supports"]["available"]:
        for key in ["status","capacity_contribution","notes"]: item.pop(key, None)
    for key in ["attention_level","coordination_capacity","recovery_time_hours","load_level"]: value["input"]["capacity"].pop(key, None)
    record = generate_record(value).to_dict()
    assert record["metadata"]["schema_version"] == "1.5.0"
    assert record["normalized_input"]["pressure"]["decision_ambiguity"] == 5
    assert record["normalized_input"]["constraints"]["items"][0]["control_zone"] == "influence"
    assert record["findings"]["interpretation"]["review_required"] is True
