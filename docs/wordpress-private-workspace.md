# WordPress private workspace

Catalyst Grit provides two intentionally separate WordPress surfaces.

- `[catalyst_grit_demo]` is public, browser-only, and non-persistent.
- `[catalyst_grit_workspace]` requires an authenticated user with read access.

The private shortcode loads separate assets, signs every AJAX request with a nonce, stores data only in the current user's metadata, limits payloads to 512 KB, and enforces `visibility: private`. No `wp_ajax_nopriv_*` handlers are registered.

The WordPress workspace is a compact account-level companion. Complete institutional persistence remains in the Python repository, where revisions, checkpoints, reviews, history, retention, and audit events are first-class entities.
