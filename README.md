# Catalyst Grit

**Current release: v1.0.1 — Repository Integrity and Product Consolidation**

Catalyst Grit is a Sustainable Catalyst human-systems module for documenting setbacks, recovery conditions, response choices, next actions, and learning loops. It treats grit as a system behavior shaped by pressure, friction, support, clarity, energy, response, recovery time, and adaptation.

Catalyst Grit is educational and analytical infrastructure. It does not diagnose people, score character, rank employees, replace professional support, or guarantee resilience.

## Canonical product model

The structured **recovery record** is the only production model. An older Flask event tracker is preserved under `legacy/` solely for historical reference and is excluded from the installed Python package, WordPress plugin, and current interfaces.

## Repository surfaces

- `src/catalyst_grit/` — canonical installable engine and CLI
- `python/catalyst_grit_core.py` — v1.0-compatible repository wrapper
- `wordpress/catalyst-grit-demo/` — client-side public demo
- `schemas/` — versioned recovery-record contract
- `openapi.yaml` — recovery-record integration contract
- `tests/fixtures/` — shared Python/browser golden fixtures
- `scripts/` — smoke, release-contract, parity, and deterministic build tooling
- `release/` — release notes
- `legacy/` — isolated, unsupported prototypes

## Python usage

Install the package:

```bash
python3 -m pip install -e .
```

Generate a JSON record:

```bash
grit generate examples/grit_record_input.json --format json
```

Generate a Markdown brief:

```bash
grit generate examples/grit_record_input.json   --format markdown   --output outputs/grit_record_brief.md
```

The v1.0 repository command remains supported:

```bash
python3 python/catalyst_grit_core.py examples/grit_record_input.json --format json
```

## WordPress demo

Install `wordpress/catalyst-grit-demo` or upload the generated plugin ZIP, then use:

```text
[catalyst_grit_demo]
```

The public demo runs locally in the browser and does not persist inputs.

## Validation

```bash
python3 -m pip install -e '.[dev]'
python3 scripts/release_contract.py
```

The release contract checks Python tests and compilation, schema validation, Python/browser parity, committed output parity, PHP and JavaScript syntax when available, package build/install/import, version consistency, and forbidden repository artifacts.

## Build release artifacts

```bash
python3 scripts/build_release.py
```

Generated artifacts include the repository ZIP, WordPress plugin ZIP, checksums, release manifest, all-in-one release bundle, and macOS install-and-push script.

## Method path

```text
setback → context → impact → pressure → support → response → recovery pattern → next action → review
```

## License

MIT. See `LICENSE`.
