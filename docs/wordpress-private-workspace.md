# WordPress private workspace

Catalyst Grit provides two intentionally separate WordPress surfaces.

- `[catalyst_grit_demo]` is public, browser-only, and non-persistent.
- `[catalyst_grit_workspace]` requires an authenticated user with read access.

The private shortcode loads separate assets, signs every AJAX request with the v1.5 nonce, stores data only in the current user's metadata, limits payloads to 512 KB, and enforces `visibility: private`. No `wp_ajax_nopriv_*` handlers are registered.

The browser demo now captures retrospective fields and renders the generated learning loop, evidence-linked pattern candidates, review status, and system-change guidance. It does not save submissions or aggregate patterns across visitors.

The WordPress workspace is a compact account-level companion. Complete institutional persistence remains in the Python repository, where revisions, actions, checkpoints, retrospectives, pattern reviews, system changes, retention, and audit events are first-class entities.
