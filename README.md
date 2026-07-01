# Catalyst Grit

Catalyst Grit is a Sustainable Catalyst human-systems module for documenting setbacks, recovery patterns, resilience capacity, and learning loops. It treats grit as a system behavior: pressure, friction, support, clarity, response, recovery time, and adaptation.

The module is designed for educational, analytical, and planning workflows. It does not diagnose people, score character, or replace coaching, therapy, management judgment, or professional support. Its purpose is to make recovery conditions and learning signals visible.

## What this repo contains

- A lightweight Python engine for generating a Catalyst Grit recovery record
- A browser-based WordPress demo plugin
- JSON schema for exports
- Sample records and example outputs
- Methodology, architecture, export, and review documentation
- Tests and GitHub Actions validation

## WordPress demo

Install the plugin in `wordpress/catalyst-grit-demo` or upload the generated zip from `dist/catalyst-grit-demo.zip`.

Shortcode:

```text
[catalyst_grit_demo]
```

The demo lets visitors describe a setback or challenge, assess pressure, severity, energy, support, clarity, recovery actions, and time horizon, then generate a recovery score, resilience state, review flags, next actions, decision note, and JSON export.

## Python usage

```bash
python3 python/catalyst_grit_core.py examples/grit_record_input.json --format json --output outputs/grit_record_output.json
python3 python/catalyst_grit_core.py examples/grit_record_input.json --format markdown --output outputs/grit_record_brief.md
```

## Repository structure

```text
.github/workflows/            CI validation
data/                         sample CSV records
docs/                         methodology and implementation docs
examples/                     sample inputs and outputs
outputs/                      generated outputs, ignored except .gitkeep
python/                       core generator and CLI
schemas/                      JSON schema
tests/                        lightweight Python tests
wordpress/catalyst-grit-demo/ WordPress shortcode plugin
```

## Methodological path

```text
setback → context → impact → pressure → supports → response → recovery pattern → next action → review
```

## Boundaries

Catalyst Grit is not a mental-health tool, diagnostic instrument, performance rating system, or guarantee of resilience. It is a structured reflection and documentation layer for human-systems work.

## License

Use the repository license unless another file specifies otherwise.
