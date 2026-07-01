# Contributing

Catalyst Grit contributions should preserve the module's purpose: structured human-systems reflection, recovery documentation, and learning-loop clarity.

## Guidelines

- Keep language non-diagnostic and non-punitive.
- Avoid turning grit into a character score.
- Make assumptions and limits explicit.
- Preserve traceability between inputs, generated outputs, and interpretation notes.
- Keep browser demos client-side unless a future implementation clearly documents storage, consent, privacy, and security.

## Development

```bash
python3 -m pytest tests
python3 python/catalyst_grit_core.py examples/grit_record_input.json --format json
```
