# Publication and Export

Catalyst Grit v2.0.0 creates governed publication artifacts rather than treating a saved recovery record as automatically publishable.

Supported report types are recovery briefs, facilitated-review briefs, action plans, learning-loop reports, adaptation proposals, monitoring summaries, and Decision Studio handoff packets.

Supported outputs are canonical JSON, JSON-LD, Markdown, HTML, approved tabular CSV, a PDF-render request for the Sustainable Catalyst publication layer, and a deterministic versioned ZIP bundle containing a manifest and SHA-256 checksums.

Every artifact records its project, optional record, report type, output format, visibility, redaction policy, content hash, actor, timestamp, and append-only review/publication history.

## Redaction

`none` is private and retains the complete governed report. `internal` masks user and actor identifiers and removes direct source locations. `public` additionally removes raw user input, private perspectives, audit details, and provenance that is not approved for public disclosure. Public or internal artifacts require human review before institutional publication.

PDF files are intentionally rendered by the platform publication layer. Catalyst Grit exports a stable rendering request rather than silently relying on an optional local PDF library.
