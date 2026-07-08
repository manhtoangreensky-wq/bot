import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _changed_files():
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        check=False,
        text=True,
        capture_output=True,
        cwd=ROOT,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def _section(source: str, start: str, end: str = "") -> str:
    assert start in source
    body = source.split(start, 1)[1]
    if end:
        assert end in body
        body = body.split(end, 1)[0]
    return body


def test_image_live_final_confirm_routes_to_delivery_first_before_legacy_billing():
    callback = _section(BOT_SOURCE, "async def handle_shopaikey_public_callback", "def provider_error_summary")

    route = 'if job_type == "image":\n        return await handle_shopaikey_public_image_confirm_delivery_first'
    assert route in callback
    assert callback.index("shopaikey_provider_submit_guard") < callback.index(route)
    assert callback.index(route) < callback.index("package_use_result = {}")
    assert callback.index(route) < callback.index("spend_fixed_credit_info(")
    assert "source=provider_submit_source" in callback
    assert 'confirmed=action in {"confirm", "package"}' in callback


def test_image_live_delivery_first_helper_sends_real_output_before_charge():
    helper = _section(
        BOT_SOURCE,
        "async def handle_shopaikey_public_image_confirm_delivery_first",
        "async def handle_shopaikey_public_callback",
    )

    assert "awaiting_delivery_before_charge" in helper
    assert "image_provider_submit_allowed" in helper
    assert "shopaikey_image_generate(" in helper
    assert "shopaikey_image_result_payload_looks_valid" in helper
    assert "send_generated_image_result(" in helper
    assert "spend_fixed_credit_info(" in helper
    assert "deduct_package_item_for_job(" in helper
    assert helper.index("shopaikey_image_generate(") < helper.index("send_generated_image_result(")
    assert helper.index("send_generated_image_result(") < helper.index("spend_fixed_credit_info(")
    assert helper.index("send_generated_image_result(") < helper.index("deduct_package_item_for_job(")
    assert "FAIL_INVALID_IMAGE_RESULT" in helper
    assert "FAIL_SEND_IMAGE" in helper
    assert 'refund_status="not_charged"' in helper
    assert 'billing_status="failed_not_charged"' in helper
    assert "no_charge_before_delivery=true" in helper


def test_image_live_result_validation_rejects_obvious_non_image_payloads():
    validator = _section(
        BOT_SOURCE,
        "def shopaikey_image_result_payload_looks_valid",
        "async def handle_shopaikey_public_image_confirm_delivery_first",
    )

    assert 'url.startswith("https://")' in validator
    assert 'url.endswith((".json", ".html", ".htm", ".txt"))' in validator
    assert '"/error"' in validator
    assert "base64.b64decode" in validator
    assert 'head.startswith((b"<html", b"<!doctype", b"{", b"["))' in validator


def test_image_provider_submit_guard_blocks_hidden_but_allows_live_guard_path():
    guard = _section(BOT_SOURCE, "def shopaikey_provider_submit_guard", "def shopaikey_active_job_for_user")
    public_image_guard = _section(BOT_SOURCE, "def shopaikey_image_public_confirm_submit_guard", "def shopaikey_non_public_submit_guard")

    for token in ("smoke", "background", "debug", "codex", "hidden", "status", "worker"):
        assert f'"{token}"' in BOT_SOURCE
    assert "missing_user_final_confirm" in guard
    assert "shopaikey_non_public_submit_guard(submit_kind)" in guard
    assert "hidden_submit_source_blocked" in BOT_SOURCE
    assert "image_public_flag_off" in public_image_guard
    assert "image_provider_not_configured" in public_image_guard
    assert "shopaikey_public_generation_guard(job)" in guard
    assert "provider_submit_allowed" in guard


def test_image_maintenance_message_is_not_used_for_hidden_or_missing_config_blocks():
    callback = _section(BOT_SOURCE, "async def handle_shopaikey_public_callback", "def provider_error_summary")
    block = _section(callback, "if not provider_submit_allowed and not key4u_runtime_fallback_allowed:", "active_public_job =")

    assert "shopaikey_image_block_uses_direct_message(block_reason)" in block
    assert "shopaikey_provider_submit_maintenance_message" in block
    assert "restore_shopaikey_pending_confirmation(token, uid, pending)" in block


def test_image_public_status_command_is_registered_safe_and_readonly():
    status_payload = _section(BOT_SOURCE, "def image_public_status_payload", "def image_public_status_text")
    status_text = _section(BOT_SOURCE, "def image_public_status_text", "async def cmd_image_public_status")
    command = _section(BOT_SOURCE, "async def cmd_image_public_status", "async def cmd_providers")

    assert "public_user_final_confirm" in status_payload
    assert 'source="hidden_submit"' in status_payload
    assert 'source="smoke"' in status_payload
    assert 'source="background"' in status_payload
    assert '"provider_called": False' in status_payload
    assert '"billing_policy": "delivery_before_charge"' in status_payload
    assert '"xu_charge_allowed": "after_successful_telegram_delivery_only"' in status_payload
    assert "IMAGE_MAINTENANCE" in status_payload
    assert "SHOPAIKEY_PUBLIC_IMAGE_ENABLED" in status_payload
    assert "bool(SHOPAIKEY_API_KEY)" in status_payload
    assert "shopaikey_image_generate" not in status_payload
    assert "spend_fixed_credit_info" not in status_payload
    assert "Bearer" not in status_payload + status_text + command
    assert "raw response" in status_text.lower() or "secret/raw" in status_text.lower()
    assert 'CommandHandler("image_public_status", cmd_image_public_status)' in BOT_SOURCE


def test_image_live1_no_forbidden_runtime_scope_or_provider_submit_in_tests():
    changed = set(_changed_files())
    allowed = {
        "bot.py",
        "tests/test_p0_image_live1_public_image_generation.py",
        "tests/test_p0_image_live1b_provider_freeze_scope_public_confirm.py",
        "tests/test_p0_aichat5_live_context_action_trace.py",
        "tests/test_p0_aichat6_open_public_live_flows.py",
        "tests/test_p0_17c1_payos_signature_idempotency.py",
        "tests/test_p0_17c2_payos_auto_topup_limits.py",
    }
    forbidden_paths = (
        "music",
        "suno",
        "voice",
        "product_video",
        "subdub",
        "img2vid",
        "payos",
        "wallet",
        "payment",
    )

    assert changed <= allowed
    assert not any(any(term in path.lower() for term in forbidden_paths) and not path.startswith("tests/") for path in changed)
