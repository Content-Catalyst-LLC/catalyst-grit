# WordPress Private Workspace

`[catalyst_grit_workspace]` is an authenticated, per-user, private bundle editor. It is separate from the non-persistent public `[catalyst_grit_demo]` surface.

The v1.7 template supports projects, team members, facilitated sessions, evidence items, assumptions, and handoffs. Saves require an authenticated account with `read` capability and a v1.7 nonce. Workspace visibility must remain `private`; listed collections must be arrays; anonymous AJAX actions are not registered.

The loader reads the v1.7 user-meta key and falls back to v1.6 and v1.5 data. Clearing the workspace removes all three keys. The complete SQLite service remains the authoritative interface for revisions, append-only events, evidence links, handoff validation, and Decision Studio packets.
