# Release process

1. Update `VERSION` and all synchronized release surfaces.
2. Run `python3 -m pip install -e '.[dev]'` in a development environment.
3. Run `python3 scripts/release_contract.py`.
4. Run `python3 scripts/build_release.py`.
5. Verify `dist/SHA256SUMS` and `dist/release-manifest.json`.
6. Install with the generated macOS install-and-push script or copy the repository release manually.

The build is deterministic at the ZIP-content level: file ordering, timestamps, permissions, and compression settings are fixed.
