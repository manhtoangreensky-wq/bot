import subprocess
from pathlib import Path

from services import ai_chatbot_copilot as aichat
from services import telegram_business_support as cskh


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _enabled_state(user_id="aichat6-user", *, assist=True):
    state = aichat.default_state()
    state, _enabled = aichat.enable_with_consent(state, user_id)
    if assist:
        state, _permission = aichat.set_action_permission(state, user_id, True)
    return state


def _changed_files():
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        check=False,
        text=True,
        capture_output=True,
        cwd=ROOT,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def _section(source: str, start: str, end: str) -> str:
    assert start in source
    body = source.split(start, 1)[1]
    if end:
        assert end in body
        body = body.split(end, 1)[0]
    return body


def test_live_followup_opens_image_flow_prefill_and_keeps_provider_blocked():
    state = _enabled_state(assist=True)

    state, first = aichat.process_message(
        state,
        "aichat6-user",
        "tạo ảnh xe hơi",
        queue_unknown=False,
        entry_source="live_chat",
    )
    state, follow = aichat.process_message(
        state,
        "aichat6-user",
        "tự tạo ảnh dùm nhé",
        queue_unknown=False,
        entry_source="live_chat",
    )
    folded = cskh._fold(follow["reply"])

    assert first["intent_id"] == "image_create_request"
    assert first["target_flow"]["callback"] == "aichat|open_image_prefill"
    assert follow["intent_id"] == "image_action_confirm"
    assert follow["context_carry_used"] is True
    assert follow["selected_action"] == "open_image_ai_flow_with_prefill"
    assert follow["requested_action"] == "open_image_ai_flow_with_prefill"
    assert follow["action_should_execute"] is True
    assert follow["flow_access_allowed"] is True
    assert follow["provider_submit_allowed"] is False
    assert follow["provider_submit_block_reason"] == "awaiting_user_final_confirm"
    assert follow["provider_call_allowed"] is False
    assert follow["xu_charge_allowed"] is False
    assert "chua hieu" not in folded
    assert "thu nghiem noi bo" not in folded
    assert "chua mo cong khai" not in folded

    state = aichat.mark_action_execution(
        state,
        "aichat6-user",
        selected_action="open_image_ai_flow_with_prefill",
        requested_action="open_image_ai_flow_with_prefill",
        executed=True,
        router_called=True,
        action_result="quick_image_prefill_opened_live",
        flow_access_allowed=True,
        flow_block_reason="",
        provider_submit_allowed=False,
        provider_submit_block_reason="awaiting_user_final_confirm",
        opened_flow=True,
        prefill_saved=True,
    )
    trace = aichat.status_payload(state, "aichat6-user")["last_trace"]

    assert trace["context_source"] == "live_chat"
    assert trace["requested_action"] == "open_image_ai_flow_with_prefill"
    assert trace["flow_access_allowed"] is True
    assert trace["flow_block_reason"] == ""
    assert trace["provider_submit_allowed"] is False
    assert trace["provider_submit_block_reason"] == "awaiting_user_final_confirm"
    assert trace["opened_flow"] is True
    assert trace["prefill_saved"] is True
    assert trace["provider_call_allowed"] is False
    assert trace["xu_charge_allowed"] is False


def test_public_image_flow_sections_do_not_block_before_invoice():
    quick_tier = _section(BOT_SOURCE, 'if action.startswith("qi_tier_"):', 'if action.startswith("ia_") or action.startswith("va_"):')
    aspect = _section(BOT_SOURCE, 'if action.startswith("image_aspect_"):', 'if action.startswith("video_aspect_"):')
    image_tier = _section(BOT_SOURCE, 'if action.startswith("image_tier_"):', 'if action == "quick_video":')
    command_flow = _section(BOT_SOURCE, "async def cmd_shopaikey_image_public", "async def start_public_image_prompt_from_tier_message")
    prompt_pending = _section(BOT_SOURCE, "async def handle_public_image_prompt_pending_text", "async def handle_media_logo_watermark_pending_text")

    for flow_body in [quick_tier, aspect, image_tier, command_flow, prompt_pending]:
        assert 'shopaikey_public_generation_guard("image")' not in flow_body
        assert 'SHOPAIKEY_PUBLIC_IMAGE_ENABLED' not in flow_body
        assert 'shopaikey_active_job_for_user(uid, "image")' not in flow_body
        assert 'ui_text(lang, "media.public_off")' not in flow_body

    assert "set_shopaikey_pending_confirmation" in quick_tier
    assert "public_image_confirm_text" in quick_tier
    assert '"provider_submit_source": "public_user_final_confirm"' in quick_tier
    assert "set_shopaikey_pending_confirmation" in aspect
    assert "public_image_confirm_text" in aspect
    assert '"provider_submit_source": "public_user_final_confirm"' in aspect
    assert "set_public_image_prompt_pending" in image_tier


def test_provider_submit_guard_is_final_confirm_only_and_blocks_hidden_sources():
    guard_body = _section(BOT_SOURCE, "def shopaikey_provider_submit_guard", "def shopaikey_active_job_for_user")
    callback_body = _section(BOT_SOURCE, "async def handle_shopaikey_public_callback", "def provider_error_summary")

    assert "hidden_submit_source_blocked" in guard_body
    assert "missing_user_final_confirm" in guard_body
    assert "provider_submit_runtime_guard_blocked" in guard_body
    assert "shopaikey_public_generation_guard(job)" in guard_body
    assert "source=provider_submit_source" in callback_body
    assert 'confirmed=action in {"confirm", "package"}' in callback_body
    assert "restore_shopaikey_pending_confirmation(token, uid, pending)" in callback_body
    assert "shopaikey_provider_submit_maintenance_message" in callback_body
    assert "spend_fixed_credit_info" in callback_body
    assert "shopaikey_image_generate" in callback_body
    assert callback_body.index("shopaikey_provider_submit_guard") < callback_body.index("spend_fixed_credit_info")
    assert callback_body.index("shopaikey_provider_submit_guard") < callback_body.index("shopaikey_image_generate")


def test_trace_text_exposes_flow_and_provider_submit_reason():
    trace_body = _section(BOT_SOURCE, "def aichat_trace_text", "def aichat_image_flow_keyboard")

    assert "requested_action" in trace_body
    assert "flow_access" in trace_body
    assert "flow_block_reason" in trace_body
    assert "provider_submit" in trace_body
    assert "provider_submit_block_reason" in trace_body
    assert "opened_flow" in trace_body
    assert "prefill_saved" in trace_body


def test_aichat6_no_real_provider_calls_or_forbidden_runtime_scope():
    changed = set(_changed_files())
    allowed = {
        "bot.py",
        "services/ai_chatbot_copilot.py",
        "tests/test_p0_aichat1_copilot_consent.py",
        "tests/test_p0_aichat1b_free_tools_menu_cleanup.py",
        "tests/test_p0_aichat2_natural_context_pricing.py",
        "tests/test_p0_aichat4_smart_intent_context_backstack.py",
        "tests/test_p0_aichat5_live_context_action_trace.py",
        "tests/test_p0_aichat6_open_public_live_flows.py",
        "tests/test_p0_image_live1_public_image_generation.py",
        "tests/test_p0_17c1_payos_signature_idempotency.py",
        "tests/test_p0_17c2_payos_auto_topup_limits.py",
        "tests/test_p0_cskh1_telegram_business_auto_support_bot.py",
        "tests/test_p0_cskh2_toan_aas_training_data_playbook.py",
        "tests/test_p0_cskh2a_business_arm_mode_without_connection.py",
        "tests/test_p0_cskh3_conversation_brain_natural_replies.py",
        "tests/test_p0_cskh4_aas_product_knowledge_pricing_mixed_intents.py",
        "tests/test_p0_cskh5b_live_business_followup_pricing_runtime.py",
        "tests/test_p0_cskh5c_business_self_echo_duplicate_guard.py",
        "tests/test_p0_cskh6_human_touch_playbook_safe_training_pack.py",
        "tests/test_p0_cskh_aichat3_context_brain_retrieval.py",
    }
    forbidden_terms = (
        "music",
        "suno",
        "voice_provider",
        "product_video_provider",
        "subdub",
        "img2vid",
        "payos",
        "wallet",
        "payment",
    )

    assert changed <= allowed
    assert not any(any(term in path.lower() for term in forbidden_terms) and not path.startswith("tests/") for path in changed)
