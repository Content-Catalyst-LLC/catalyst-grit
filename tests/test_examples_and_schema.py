import json
from pathlib import Path

import jsonschema
from jsonschema import FormatChecker

from catalyst_grit import DEFAULT_METHODOLOGY_PROFILE, generate_record

ROOT = Path(__file__).resolve().parents[1]
REQUEST_SCHEMA = json.loads((ROOT / "schemas/catalyst_grit_request.schema.json").read_text())
OUTPUT_SCHEMA = json.loads((ROOT / "schemas/catalyst_grit_record.schema.json").read_text())
PROFILE_SCHEMA = json.loads((ROOT / "schemas/catalyst_grit_methodology_profile.schema.json").read_text())
CHECKER = FormatChecker()


def test_example_request_and_output_validate():
    request = json.loads((ROOT / "examples/grit_record_input.json").read_text())
    output = generate_record(request).to_dict()
    jsonschema.validate(request, REQUEST_SCHEMA, format_checker=CHECKER)
    jsonschema.validate(output, OUTPUT_SCHEMA, format_checker=CHECKER)


def test_committed_output_matches_engine():
    request = json.loads((ROOT / "examples/grit_record_input.json").read_text())
    expected = json.loads((ROOT / "examples/grit_record_output.json").read_text())
    assert generate_record(request).to_dict() == expected


def test_all_golden_outputs_validate_and_match():
    fixtures = json.loads((ROOT / "tests/fixtures/parity_cases.json").read_text())
    for fixture in fixtures:
        generated = generate_record(fixture["input"]).to_dict()
        jsonschema.validate(generated, OUTPUT_SCHEMA, format_checker=CHECKER)
        assert generated == fixture["expected"]


def test_default_methodology_file_matches_engine():
    committed = json.loads((ROOT / "methodology/recovery-profile-v1.5.0.json").read_text())
    assert committed == DEFAULT_METHODOLOGY_PROFILE
    jsonschema.validate(committed, PROFILE_SCHEMA)
