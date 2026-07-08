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


def _vproduct_execute_block() -> str:
    handler = _section(BOT_SOURCE, "async def handle_video_product_callback", "async def handle_trend_guided_callback")
    return _section(handler, 'if action == "prompt_image_execute":', 'if action == "prompt_video":')


def _submit_guard() -> str:
    return _section(BOT_SOURCE, "def shopaikey_provider_submit_guard", "def shopaikey_active_job_for_user")


def _public_image_guard() -> str:
    return _section(BOT_SOURCE, "def shopaikey_image_public_confirm_submit_guard", "def shopaikey_non_public_submit_guard")


def _non_public_guard() -> str:
    return _section(BOT_SOURCE, "def shopaikey_non_public_submit_guard", "def shopaikey_image_block_uses_direct_message")


def _delivery_helper() -> str:
    return _section(
        BOT_SOURCE,
        "async def handle_shopaikey_public_image_confirm_delivery_first",
        "async def handle_shopaikey_public_callback",
    )


def test_image_live1d_vproduct_prompt_image_execute_not_blocked_by_generic_guard():
    block = _vproduct_execute_block()

    assert 'shopaikey_public_generation_guard("image")' not in block
    assert "shopaikey_provider_submit_guard(" in block
    assert "handle_shopaikey_public_callback(update, context" in block
    assert "shopaikey_provider_submit_maintenance_message" in block


def test_image_live1d_vproduct_prompt_image_uses_public_confirm_source():
    block = _vproduct_execute_block()
    classifier = _section(BOT_SOURCE, "def classify_provider_submit_source", "def image_public_maintenance_enabled")

    assert 'source="vproduct_public_user_final_confirm"' in block
    assert 'pending["provider_submit_source"] = "vproduct_public_user_final_confirm"' in block
    assert 'pending["submit_source"] = "vproduct_public_user_final_confirm"' in block
    assert "vproduct_public_user_final_confirm" in classifier


def test_image_live1d_public_confirm_not_blocked_by_provider_freeze_enabled():
    public_guard = _public_image_guard()
    submit_guard = _submit_guard()

    assert 'if job == "image" and submit_kind == "public_user_confirm"' in submit_guard
    assert "return shopaikey_image_public_confirm_submit_guard()" in submit_guard
    assert "PROVIDER_FREEZE_ENABLED" not in public_guard
    assert "provider_freeze_non_public_on" not in public_guard
    assert '"provider_submit_allowed": True' in public_guard


def test_image_live1d_public_confirm_not_blocked_by_provider_spend_freeze():
    public_guard = _public_image_guard()
    non_public = _non_public_guard()

    assert "PROVIDER_SPEND_FREEZE" not in public_guard
    assert "PROVIDER_SPEND_FREEZE" in non_public


def test_image_live1d_public_confirm_not_blocked_by_real_provider_smoke_disabled():
    public_guard = _public_image_guard()
    non_public = _non_public_guard()

    assert "REAL_PROVIDER_SMOKE_ENABLED" not in public_guard
    assert "not REAL_PROVIDER_SMOKE_ENABLED" in non_public


def test_image_live1d_smoke_source_blocked():
    non_public = _non_public_guard()
    classifier = _section(BOT_SOURCE, "def classify_provider_submit_source", "def image_public_maintenance_enabled")

    assert '"smoke"' in classifier
    assert '"tool_test"' in classifier
    assert "smoke_blocked_real_provider_smoke_disabled" in non_public
    assert "smoke_blocked_by_provider_freeze" in BOT_SOURCE


def test_image_live1d_tool_test_source_blocked():
    classifier = _section(BOT_SOURCE, "def classify_provider_submit_source", "def image_public_maintenance_enabled")

    assert '"tool_test"' in classifier
    assert 'return "smoke"' in classifier


def test_image_live1d_background_source_blocked():
    classifier = _section(BOT_SOURCE, "def classify_provider_submit_source", "def image_public_maintenance_enabled")

    assert '"background"' in classifier
    assert 'return "background"' in classifier
    assert "background_blocked_by_provider_freeze" in BOT_SOURCE


def test_image_live1d_worker_source_blocked():
    classifier = _section(BOT_SOURCE, "def classify_provider_submit_source", "def image_public_maintenance_enabled")

    assert '"worker"' in classifier
    assert 'return "background"' in classifier


def test_image_live1d_missing_confirm_blocked():
    submit_guard = _submit_guard()

    assert "if not confirmed:" in submit_guard
    assert "missing_user_final_confirm" in submit_guard


def test_image_live1d_explicit_image_maintenance_blocks_public_confirm():
    public_guard = _public_image_guard()
    maintenance = _section(BOT_SOURCE, "def image_public_maintenance_enabled", "def image_explicit_maintenance_on")

    for flag in ("IMAGE_MAINTENANCE", "IMAGE_PUBLIC_MAINTENANCE", "IMAGE_GENERATION_DISABLED", "PUBLIC_IMAGE_DISABLED", "AAS_IMAGE_DISABLED"):
        assert flag in maintenance
    assert "image_explicit_maintenance_on()" in public_guard
    assert "image_explicit_maintenance" in public_guard


def test_image_live1d_generic_provider_freeze_does_not_show_image_maintenance():
    block = _vproduct_execute_block()
    direct = _section(BOT_SOURCE, "IMAGE_PROVIDER_DIRECT_BLOCK_REASONS", "def shopaikey_public_flow_access_guard")

    assert "shopaikey_provider_submit_maintenance_message" in block
    assert 'if block_reason == "image_explicit_maintenance"' in block
    assert "background_blocked_by_provider_freeze" in direct
    assert "hidden_submit_blocked_by_provider_freeze" in direct


def test_image_live1d_maintenance_message_only_explicit_image_maintenance():
    block = _vproduct_execute_block()

    assert 'if block_reason == "image_explicit_maintenance"' in block
    assert "else str(provider_submit_guard.get(\"message\")" in block


def test_image_live1d_vproduct_prompt_image_execute_calls_mock_provider_once():
    block = _vproduct_execute_block()
    helper = _delivery_helper()

    assert block.count("handle_shopaikey_public_callback(update, context") == 1
    assert "shopaikey_image_generate(" not in block
    assert helper.count("shopaikey_image_generate(") == 1


def test_image_live1d_quick_image_confirm_calls_mock_provider_once():
    callback = _section(BOT_SOURCE, "async def handle_shopaikey_public_callback", "def provider_error_summary")
    helper = _delivery_helper()

    assert "handle_shopaikey_public_image_confirm_delivery_first(" in callback
    assert callback.count("handle_shopaikey_public_image_confirm_delivery_first(") == 1
    assert helper.count("shopaikey_image_generate(") == 1


def test_image_live1d_no_charge_before_provider_result_on_failure():
    helper = _delivery_helper()
    failure_block = _section(helper, "if status != \"PASS\":", "deducted = 0")

    assert "spend_fixed_credit_info(" not in failure_block
    assert "deduct_package_item_for_job(" not in failure_block
    assert "failed_not_charged" in failure_block
    assert "no_charge_before_delivery=true" in failure_block


def test_image_live1d_valid_result_delivery_path_preserved():
    helper = _delivery_helper()

    assert helper.index("shopaikey_image_generate(") < helper.index("send_generated_image_result(")
    assert helper.index("send_generated_image_result(") < helper.index("spend_fixed_credit_info(")
    assert helper.index("send_generated_image_result(") < helper.index("deduct_package_item_for_job(")
    assert "shopaikey_image_result_payload_looks_valid" in helper


def test_image_live1d_image_public_status_masks_secret():
    status_payload = _section(BOT_SOURCE, "def image_public_status_payload", "def image_public_status_text")
    status_text = _section(BOT_SOURCE, "def image_public_status_text", "async def cmd_image_public_status")

    assert "bool(SHOPAIKEY_API_KEY)" in status_payload
    assert "SHOPAIKEY_API_KEY" not in status_text
    assert "Bearer" not in status_payload + status_text
    assert "Secret/raw response" in status_text


def test_image_live1d_image_public_status_reports_public_allowed():
    status_payload = _section(BOT_SOURCE, "def image_public_status_payload", "def image_public_status_text")
    status_text = _section(BOT_SOURCE, "def image_public_status_text", "async def cmd_image_public_status")

    assert '"public_live_confirm_allowed"' in status_payload
    assert '"vproduct_image_confirm_allowed"' in status_payload
    assert "Public live confirm allowed" in status_text
    assert "VProduct image confirm allowed" in status_text


def test_image_live1d_image_public_status_reports_hidden_blocked():
    status_payload = _section(BOT_SOURCE, "def image_public_status_payload", "def image_public_status_text")
    status_text = _section(BOT_SOURCE, "def image_public_status_text", "async def cmd_image_public_status")

    assert 'source="hidden_submit"' in status_payload
    assert '"hidden_submit_blocked"' in status_payload
    assert "Hidden submit blocked" in status_text


def test_image_live1d_image_public_status_reports_explicit_maintenance():
    status_payload = _section(BOT_SOURCE, "def image_public_status_payload", "def image_public_status_text")
    status_text = _section(BOT_SOURCE, "def image_public_status_text", "async def cmd_image_public_status")

    assert '"explicit_image_maintenance"' in status_payload
    assert "IMAGE_PUBLIC_MAINTENANCE" in status_text
    assert "PUBLIC_IMAGE_DISABLED" in status_text
    assert "AAS_IMAGE_DISABLED" in status_text


def test_image_live1d_no_music_changes():
    changed = _changed_files()
    assert not any(("music" in path.lower() or "suno" in path.lower()) and not path.startswith("tests/") for path in changed)


def test_image_live1d_no_product_video_runtime_changes():
    changed = _changed_files()
    assert not any("product_video" in path.lower() and not path.startswith("tests/") for path in changed)


def test_image_live1d_no_subdub_changes():
    changed = _changed_files()
    assert not any(("subdub" in path.lower() or "subtitle_dub" in path.lower()) and not path.startswith("tests/") for path in changed)


def test_image_live1d_no_img2vid_runtime_changes():
    changed = _changed_files()
    assert not any("img2vid" in path.lower() and not path.startswith("tests/") for path in changed)


def test_image_live1d_no_voice_changes():
    changed = _changed_files()
    assert not any("voice" in path.lower() and not path.startswith("tests/") for path in changed)


def test_image_live1d_no_payos_wallet_payment_destructive_changes():
    changed = _changed_files()
    assert not any(
        any(term in path.lower() for term in ("payos", "wallet", "payment"))
        and not path.startswith("tests/")
        for path in changed
    )


def test_image_live1d_no_db_webhook_changes():
    changed = _changed_files()
    assert not any(("webhook" in path.lower() or path.lower().startswith(("migrations/", "db/"))) for path in changed)


def test_image_live1d_no_worker_changes():
    changed = _changed_files()
    assert not any(path.lower().endswith(("remote_worker.py", "local_worker.py")) for path in changed)


def test_image_live1d_scope_allowlist():
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
