import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _changed_files() -> set[str]:
    names: set[str] = set()
    for command in (
        ["git", "diff", "--name-only", "origin/main"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        result = subprocess.run(command, check=False, text=True, capture_output=True, cwd=ROOT)
        names.update(
            line.strip().replace("\\", "/")
            for line in result.stdout.splitlines()
            if line.strip() and not line.strip().replace("\\", "/").startswith(".tmp/")
        )
    return names


def _section(source: str, start: str, end: str = "") -> str:
    assert start in source
    body = source.split(start, 1)[1]
    if end:
        assert end in body
        body = body.split(end, 1)[0]
    return body


def test_image_live_public_confirm_allowed_with_provider_freeze_on():
    classifier = _section(BOT_SOURCE, "def classify_provider_submit_source", "def image_explicit_maintenance_on")
    public_guard = _section(BOT_SOURCE, "def shopaikey_image_public_confirm_submit_guard", "def shopaikey_non_public_submit_guard")
    submit_guard = _section(BOT_SOURCE, "def shopaikey_provider_submit_guard", "def shopaikey_active_job_for_user")

    assert "public_user_final_confirm" in classifier
    assert "public_user_confirm" in classifier
    assert 'if job == "image" and submit_kind == "public_user_confirm"' in submit_guard
    assert "return shopaikey_image_public_confirm_submit_guard()" in submit_guard
    assert "PROVIDER_FREEZE" not in public_guard
    assert "provider_freeze_runtime_on" not in public_guard
    assert "provider_freeze_non_public_on" not in public_guard
    assert "REAL_PROVIDER_SMOKE_ENABLED" not in public_guard
    assert '"provider_submit_allowed": True' in public_guard


def test_image_live_hidden_submit_blocked_with_provider_freeze_on():
    non_public_guard = _section(BOT_SOURCE, "def shopaikey_non_public_submit_guard", "def shopaikey_image_block_uses_direct_message")

    assert '"hidden_submit"' in non_public_guard
    assert "provider_freeze_non_public_on()" in non_public_guard
    assert 'f"{kind}_blocked_by_provider_freeze"' in non_public_guard
    assert "Provider freeze đang chặn submit nền/test/debug" in non_public_guard


def test_image_live_smoke_blocked_when_real_provider_smoke_disabled():
    non_public_guard = _section(BOT_SOURCE, "def shopaikey_non_public_submit_guard", "def shopaikey_image_block_uses_direct_message")

    assert 'kind == "smoke"' in non_public_guard
    assert "not REAL_PROVIDER_SMOKE_ENABLED" in non_public_guard
    assert "smoke_blocked_real_provider_smoke_disabled" in non_public_guard


def test_image_live_background_blocked_with_provider_freeze_on():
    classifier = _section(BOT_SOURCE, "def classify_provider_submit_source", "def image_explicit_maintenance_on")
    non_public_guard = _section(BOT_SOURCE, "def shopaikey_non_public_submit_guard", "def shopaikey_image_block_uses_direct_message")

    assert '"background"' in classifier
    assert '"worker"' in classifier
    assert '"status"' in classifier
    assert '"background"' in non_public_guard
    assert 'f"{kind}_blocked_by_provider_freeze"' in non_public_guard


def test_image_live_maintenance_message_only_explicit_image_maintenance():
    public_guard = _section(BOT_SOURCE, "def shopaikey_image_public_confirm_submit_guard", "def shopaikey_non_public_submit_guard")
    explicit = _section(BOT_SOURCE, "def image_public_maintenance_enabled", "def provider_freeze_non_public_on")

    assert "image_explicit_maintenance_on()" in public_guard
    assert "image_explicit_maintenance" in public_guard
    assert "IMAGE_MAINTENANCE" in explicit
    assert "IMAGE_PUBLIC_MAINTENANCE" in explicit
    assert "IMAGE_GENERATION_DISABLED" in explicit
    assert "PUBLIC_IMAGE_DISABLED" in explicit
    assert "AAS_IMAGE_DISABLED" in explicit
    assert "TOOL_FREEZE_IMAGE" not in explicit
    assert "PROVIDER_FREEZE" not in explicit
    assert "PROVIDER_SPEND_FREEZE" not in explicit


def test_image_live_no_maintenance_message_for_provider_freeze():
    callback = _section(BOT_SOURCE, "async def handle_shopaikey_public_callback", "def provider_error_summary")
    direct_helper = _section(BOT_SOURCE, "IMAGE_PROVIDER_DIRECT_BLOCK_REASONS", "def shopaikey_public_flow_access_guard")

    assert "shopaikey_image_block_uses_direct_message(block_reason)" in callback
    assert "shopaikey_provider_submit_maintenance_message" in callback
    assert "hidden_submit_blocked_by_provider_freeze" in direct_helper
    assert "smoke_blocked_by_provider_freeze" in direct_helper
    assert "background_blocked_by_provider_freeze" in direct_helper
    assert "provider_spend_freeze_non_public_submit_blocked" in direct_helper


def test_image_public_status_masks_freeze_secret():
    status_payload = _section(BOT_SOURCE, "def image_public_status_payload", "def image_public_status_text")
    status_text = _section(BOT_SOURCE, "def image_public_status_text", "async def cmd_image_public_status")

    assert "provider_freeze" in status_payload
    assert "provider_spend_freeze" in status_payload
    assert "real_provider_smoke_enabled" in status_payload
    assert "PROVIDER_FREEZE_MESSAGE" not in status_payload + status_text
    assert "Bearer" not in status_payload + status_text
    assert "SHOPAIKEY_API_KEY" not in status_text
    assert "Secret/raw response" in status_text


def test_image_public_status_reports_public_confirm_allowed():
    status_payload = _section(BOT_SOURCE, "def image_public_status_payload", "def image_public_status_text")
    status_text = _section(BOT_SOURCE, "def image_public_status_text", "async def cmd_image_public_status")

    assert '"public_live_confirm_allowed"' in status_payload
    assert '"final_decision_reason"' in status_payload
    assert "Public live confirm allowed" in status_text
    assert "Final decision reason" in status_text


def test_image_public_status_reports_hidden_blocked():
    status_payload = _section(BOT_SOURCE, "def image_public_status_payload", "def image_public_status_text")
    status_text = _section(BOT_SOURCE, "def image_public_status_text", "async def cmd_image_public_status")

    assert 'source="hidden_submit"' in status_payload
    assert '"hidden_submit_blocked"' in status_payload
    assert "Hidden submit blocked" in status_text


def test_no_music_changes():
    changed = _changed_files()
    assert not any(("music" in path.lower() or "suno" in path.lower()) and not path.startswith("tests/") for path in changed)


def test_no_product_video_changes():
    changed = _changed_files()
    assert not any("product_video" in path.lower() and not path.startswith("tests/") for path in changed)


def test_no_subdub_changes():
    changed = _changed_files()
    assert not any(("subdub" in path.lower() or "subtitle_dub" in path.lower()) and not path.startswith("tests/") for path in changed)


def test_no_payos_wallet_payment_destructive_changes():
    changed = _changed_files()
    allowed = {
        "bot.py",
        "tests/test_p0_aichat6_open_public_live_flows.py",
        "tests/test_p0_image_live1_public_image_generation.py",
        "tests/test_p0_image_live1b_provider_freeze_scope_public_confirm.py",
        "tests/test_p0_image_live1d_vproduct_public_confirm_unblocked.py",
        "tests/test_task3d_video_product_prompt_engine.py",
    }
    assert changed <= allowed
    assert not any(
        any(term in path.lower() for term in ("payos", "wallet", "payment"))
        and not path.startswith("tests/")
        for path in changed
    )
