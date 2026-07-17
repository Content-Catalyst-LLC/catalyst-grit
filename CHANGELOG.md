# Changelog

## 1.0.1 - Repository Integrity and Product Consolidation

- Declared the recovery-record engine as the only production Catalyst Grit model.
- Unified package, plugin, schema, manifest, OpenAPI, browser, documentation, and example versions at `1.0.1`.
- Replaced the installed legacy metrics surface with the canonical recovery-record package and CLI.
- Archived the obsolete Flask event tracker and trait-oriented metrics under `legacy/flask-tracker`.
- Removed tracked SQLite runtime state and generated `egg-info` metadata.
- Added schema, version, repository-integrity, output-parity, browser-parity, package-build, PHP, and JavaScript release checks.
- Added deterministic source and WordPress packaging, checksums, release manifest, and macOS install-and-push tooling.
- Added explicit schema and engine provenance to generated outputs.

## 1.0.0 - Repository refresh

- Added browser-based WordPress demo plugin using shortcode `[catalyst_grit_demo]`.
- Added Python Catalyst Grit recovery-record generator.
- Added JSON schema, sample input, sample output, and markdown brief.
- Added methodology, architecture, export, review, and WordPress demo documentation.
- Added lightweight tests and GitHub Actions workflow.
- Added repository manifest and sample data.
