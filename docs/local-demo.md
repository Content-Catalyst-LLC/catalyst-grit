# Local demo

Install the package in editable mode:

```bash
python3 -m pip install -e .
```

Generate records through the canonical CLI:

```bash
grit generate examples/grit_record_input.json --format json
grit generate examples/grit_record_input.json --format markdown
```

The v1.0-compatible wrapper remains available:

```bash
python3 python/catalyst_grit_core.py examples/grit_record_input.json --format json
```

Run the portable dependency-free validation:

```bash
python3 scripts/smoke_test.py
```

Run the complete development release contract after installing `.[dev]`:

```bash
python3 scripts/release_contract.py
```

Build the WordPress plugin and repository artifacts with:

```bash
python3 scripts/build_release.py
```

The plugin artifact is written to `dist/catalyst-grit-demo-v2.0.0.zip`.
