# Institutional API

Catalyst Grit v2.0.0 exposes a framework-neutral API service contract, `catalyst-grit-api/1.0`, with routes documented in `openapi.yaml`.

Private routes require opaque bearer tokens. Tokens are shown once, stored only as SHA-256 hashes, constrained by scopes and optional project allowlists, rate-limited per minute, and recorded in an append-only API audit log.

Read routes cover records, revisions, actions, checkpoints, reviews, evidence, patterns, monitoring summaries, handoffs, and project audit history. A publication route creates governed, redaction-aware artifacts. The health route contains diagnostics but no private workspace content.

The package does not bind the service to Flask, Django, or FastAPI. Institutional deployments can attach the domain router to their approved web framework without duplicating authorization logic.
