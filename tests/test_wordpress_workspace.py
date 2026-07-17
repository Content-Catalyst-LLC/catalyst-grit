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
    assert "check_ajax_referer('catalyst_grit_workspace_v140', 'nonce')" in PHP
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
