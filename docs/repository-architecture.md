# Repository Architecture

Catalyst Grit is organized as a small reproducible module.

```text
python/catalyst_grit_core.py       Core engine and CLI
schemas/catalyst_grit_record.schema.json Export schema
examples/                          Example input and output
wordpress/catalyst-grit-demo/      Shortcode plugin
docs/                              Methodology and implementation notes
tests/                             Lightweight validation
```

The browser demo and Python engine use the same conceptual fields: challenge, domain, impact severity, pressure, energy, clarity, support, recovery actions, time horizon, and review status.
