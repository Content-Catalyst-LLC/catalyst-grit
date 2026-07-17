from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHP = (ROOT / "wordpress/catalyst-grit-demo/catalyst-grit-demo.php").read_text()
PUBLIC_JS = (ROOT / "wordpress/catalyst-grit-demo/assets/catalyst-grit-demo.js").read_text()
PRIVATE_JS = (ROOT / "wordpress/catalyst-grit-demo/assets/catalyst-grit-workspace.js").read_text()


def test_public_demo_remains_non_persistent():
    assert "localStorage" not in PUBLIC_JS
    assert "sessionStorage" not in PUBLIC_JS
    assert "fetch(" not in PUBLIC_JS
    assert "Inputs remain in the browser unless exported." in PHP


def test_private_workspace_requires_authentication_capability_and_nonce():
    assert "is_user_logged_in()" in PHP
    assert "current_user_can('read')" in PHP
    assert "check_ajax_referer('catalyst_grit_workspace_v190', 'nonce')" in PHP
    assert "wp_ajax_nopriv_catalyst_grit_workspace" not in PHP


def test_private_workspace_is_per_user_and_private_only():
    assert "get_current_user_id()" in PHP
    assert "update_user_meta" in PHP and "delete_user_meta" in PHP
    assert "visibility must remain private" in PHP
    assert "catalyst-grit-workspace/1.0" in PRIVATE_JS
    assert "credentials: \"same-origin\"" in PRIVATE_JS


def test_public_and_private_assets_are_separate():
    assert "assets/catalyst-grit-demo.js" in PHP
    assert "assets/catalyst-grit-workspace.js" in PHP
    assert PUBLIC_JS != PRIVATE_JS


def test_team_workspace_exposes_consent_roles_and_legacy_workspace_migration():
    assert "Private Recovery, Publication, and Governance Workspace" in PHP
    assert "Consent-aware sharing" in PHP
    assert "facilitated_sessions" in PHP
    assert "_catalyst_grit_workspace_v160" in PHP
    assert "_catalyst_grit_workspace_v150" in PHP
    assert "team_members must be an array" in PHP
    assert "evidence_items" in PHP and "assumptions" in PHP and "handoffs" in PHP and "monitoring_snapshots" in PHP and "monitoring_reviews" in PHP and "institutional_policies" in PHP and "access_reviews" in PHP and "publication_artifacts" in PHP and "methodology_registry" in PHP
    assert "evidence_items" in PRIVATE_JS and "assumptions" in PRIVATE_JS and "handoffs" in PRIVATE_JS and "monitoring_snapshots" in PRIVATE_JS and "monitoring_reviews" in PRIVATE_JS and "institutional_policies" in PRIVATE_JS and "access_reviews" in PRIVATE_JS and "publication_artifacts" in PRIVATE_JS and "methodology_registry" in PRIVATE_JS


def test_wordpress_integration_exposes_health_and_authenticated_workspace_routes():
    assert "register_rest_route('catalyst-grit/v1', '/health'" in PHP
    assert "register_rest_route('catalyst-grit/v1', '/workspace'" in PHP
    assert "permission_callback' => 'catalyst_grit_rest_private_permission'" in PHP
    assert "permission_callback' => '__return_true'" in PHP
    assert "public_demo_persistence' => false" in PHP

def test_workspace_migrates_v18_and_exposes_publication_governance_guidance():
    assert "_catalyst_grit_workspace_v180" in PHP
    assert "Publication controls" in PHP
    assert "Institutional integration" in PHP
    assert "Private Recovery, Publication, and Governance Workspace" in PHP
