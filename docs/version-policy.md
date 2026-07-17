# Version policy

`VERSION` is the canonical repository release identity. Every release must mirror that value in:

- `src/catalyst_grit/version.py`
- `pyproject.toml`
- `catalyst_grit_manifest.json`
- `schemas/catalyst_grit_record.schema.json`
- `openapi.yaml`
- the WordPress plugin header, constant, and JavaScript engine
- changelog and release notes

`scripts/release_contract.py` and `tests/test_version_contract.py` fail when these surfaces drift.
