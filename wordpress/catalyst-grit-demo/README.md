# Catalyst Grit WordPress v1.2.0

## Public demo

Use `[catalyst_grit_demo]` for the browser-only canonical recovery-record demo. It does not call WordPress AJAX, use local storage, or persist input. Users may explicitly download a JSON record.

## Authenticated private workspace

Use `[catalyst_grit_workspace]` on a page restricted to signed-in users. The shortcode:

- refuses anonymous and unauthorized access;
- uses a WordPress nonce on every request;
- stores a private `catalyst-grit-workspace/1.0` object in the current user's metadata;
- limits stored JSON to 512 KB;
- enforces `visibility: private`;
- provides load, save, and deletion actions;
- loads separate workspace JavaScript and CSS assets.

The WordPress workspace is a lightweight authenticated companion. The Python/SQLite workspace remains the canonical persistence implementation for complete projects, revisions, checkpoints, reviews, status history, audit events, retention, and export/import.
