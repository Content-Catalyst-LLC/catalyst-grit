import json
from pathlib import Path

import jsonschema

from catalyst_grit import generate_record

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas/catalyst_grit_record.schema.json").read_text())


def test_example_input_and_output_validate():
    input_data = json.loads((ROOT / "examples/grit_record_input.json").read_text())
    expected = json.loads((ROOT / "examples/grit_record_output.json").read_text())
    generated = generate_record(input_data).to_dict()
    jsonschema.validate(input_data, SCHEMA)
    jsonschema.validate(expected, SCHEMA)
    assert generated == expected


def test_all_parity_fixture_outputs_validate():
    fixtures = json.loads((ROOT / "tests/fixtures/parity_cases.json").read_text())
    for fixture in fixtures:
        generated = generate_record(fixture["input"]).to_dict()
        jsonschema.validate(generated, SCHEMA)
        assert generated == fixture["expected"]
