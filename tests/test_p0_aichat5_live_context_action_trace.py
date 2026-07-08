import subprocess
from pathlib import Path

from services import ai_chatbot_copilot as aichat
from services import telegram_business_support as cskh


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CSKH_BUSINESS_STATE_FILE", str(tmp_path / "cskh_state.json"))
    monkeypatch.setenv("AICHAT_COPILOT_STATE_FILE", str(tmp_path / "aichat_state.json"))


def _enabled_state(user_id="aichat5-user", *, assist=False):
    state = aichat.default_state()
    state, _enabled = aichat.enable_with_consent(state, user_id)
    if assist:
        state, _permission = aichat.set_action_permission(state, user_id, True)
    return state


def _event(text, *, message_id="m1"):
    return cskh.BusinessMessageEvent(
        update_type="business_message",
        business_connection_id="bc-5",
        chat_id="chat-5",
        from_user_id="customer-5",
        from_is_bot=False,
        text=text,
        caption="",
        message_id=message_id,
        timestamp=1000.0,
        media_type="",
    )


def _changed_files():
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        check=False,
        text=True,
        capture_output=True,
        cwd=ROOT,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def test_live_context_carries_lexus_image_prompt_into_followup_action(tmp_path, monkeypatch):
    _isolated_env(tmp_path, monkeypatch)
    state = _enabled_state(assist=True)

    state, first = aichat.process_message(
        state,
        "aichat5-user",
        "tự tạo dùm tôi 1 bức ảnh về xe lexus",
        queue_unknown=False,
        entry_source="live_chat",
    )
    state, follow = aichat.process_message(
        state,
        "aichat5-user",
        "tự tạo dùm tôi đi",
        queue_unknown=False,
        entry_source="live_chat",
    )
    state = aichat.mark_action_execution(
        state,
        "aichat5-user",
        selected_action="open_image_ai_flow_with_prefill",
        executed=True,
        router_called=True,
        action_result="quick_image_prefill_opened_live",
    )
    payload = aichat.status_payload(state, "aichat5-user")
    memory = payload["conversation_memory"]
    trace = payload["last_trace"]

    assert first["intent_id"] == "image_create_request"
    assert first["target_flow"]["callback"] == "aichat|open_image_prefill"
    assert first["last_generated_prompt"]
    assert "Lexus" in first["last_generated_prompt"]
    assert follow["intent_id"] == "image_action_confirm"
    assert follow["context_carry_used"] is True
    assert follow["selected_action"] == "open_image_ai_flow_with_prefill"
    assert follow["action_should_execute"] is True
    assert follow["target_flow"]["callback"] == "aichat|open_image_prefill"
    assert follow["provider_call_allowed"] is False
    assert follow["xu_charge_allowed"] is False
    assert memory["last_subject"] == "xe Lexus"
    assert memory["last_generated_prompt"] == first["last_generated_prompt"]
    assert trace["context_source"] == "live_chat"
    assert trace["resolved_intent"] == "image_action_confirm"
    assert trace["context_carry_used"] is True
    assert trace["action_selected"] == "open_image_ai_flow_with_prefill"
    assert trace["action_executed"] is True
    assert trace["action_router_called"] is True
    assert trace["provider_call_allowed"] is False
    assert trace["xu_charge_allowed"] is False


def test_live_followup_without_action_permission_shows_button_not_provider(tmp_path, monkeypatch):
    _isolated_env(tmp_path, monkeypatch)
    state = _enabled_state(assist=False)

    state, _first = aichat.process_message(state, "aichat5-user", "tạo ảnh xe Lexus", queue_unknown=False)
    state, follow = aichat.process_message(state, "aichat5-user", "làm đi", queue_unknown=False)

    assert follow["intent_id"] == "image_action_confirm"
    assert follow["action_guard"] == "needs_action_permission"
    assert follow["action_should_execute"] is False
    assert follow["selected_action"] == "open_image_ai_flow_with_prefill"
    assert follow["target_flow"]["callback"] == "aichat|open_image_prefill"
    assert follow["provider_call_allowed"] is False
    assert follow["xu_charge_allowed"] is False


def test_live_image_complaint_uses_context_not_fallback(tmp_path, monkeypatch):
    _isolated_env(tmp_path, monkeypatch)
    state = _enabled_state(assist=True)

    state, _first = aichat.process_message(state, "aichat5-user", "tạo ảnh xe Lexus", queue_unknown=False)
    state, complaint = aichat.process_message(state, "aichat5-user", "không tạo được à", queue_unknown=False)
    folded = cskh._fold(complaint["reply"])

    assert complaint["intent_id"] == "image_action_complaint_or_capability"
    assert complaint["context_carry_used"] is True
    assert complaint["learning_queue"] is False
    assert complaint["selected_action"] == "open_image_ai_flow_with_prefill"
    assert complaint["action_should_execute"] is True
    assert "tao duoc" in folded
    assert "tu xac nhan" in folded or "tu tru xu" in folded
    assert "chua hieu" not in folded
    assert complaint["provider_call_allowed"] is False
    assert complaint["xu_charge_allowed"] is False


def test_short_image_after_context_continues_lexus_flow_but_no_context_is_directed(tmp_path, monkeypatch):
    _isolated_env(tmp_path, monkeypatch)
    state = _enabled_state()

    state, _first = aichat.process_message(state, "aichat5-user", "tạo ảnh xe Lexus", queue_unknown=False)
    state, short = aichat.process_message(state, "aichat5-user", "ảnh", queue_unknown=False)
    fresh_state = _enabled_state("fresh-user")
    fresh_state, no_context = aichat.process_message(fresh_state, "fresh-user", "ảnh", queue_unknown=False)

    assert short["intent_id"] == "image_create_request"
    assert short["context_carry_used"] is True
    assert "Lexus" in short["reply"]
    assert short["target_flow"]["callback"] == "aichat|open_image_prefill"
    assert no_context["intent_id"] == "image_create_request"
    assert no_context["learning_queue"] is False
    assert "tạo ảnh mới" in no_context["reply"]
    assert "xem giá" in no_context["reply"]


def test_live_trace_separates_aichat_test_and_live_source(tmp_path, monkeypatch):
    _isolated_env(tmp_path, monkeypatch)
    preview = aichat.preview_message("tạo ảnh xe Lexus", user_id="aichat5-preview")
    state = _enabled_state("aichat5-live")

    state, _result = aichat.process_message(
        state,
        "aichat5-live",
        "tạo ảnh xe Lexus",
        queue_unknown=False,
        entry_source="live_chat",
    )
    trace = aichat.status_payload(state, "aichat5-live")["last_trace"]

    assert "aichat_test" in preview["source"]
    assert trace["context_source"] == "live_chat"
    assert "live_chat" in trace["source"]
    assert trace["last_user_message"] == "tạo ảnh xe Lexus"
    assert trace["resolver_version"]
    assert trace["action_permission_enabled"] is False
    assert trace["action_selected"] == "open_image_ai_flow_with_prefill"


def test_existing_pricing_and_prompt_intents_still_work(tmp_path, monkeypatch):
    _isolated_env(tmp_path, monkeypatch)
    state = _enabled_state()

    state, topup = aichat.process_message(state, "aichat5-user", "100k được nhiêu Xu", queue_unknown=False)
    state, prompt = aichat.process_message(state, "aichat5-user", "tạo prompt video nước hoa nam", queue_unknown=False)

    assert topup["intent_id"] == "pricing_topup"
    assert "1.000 Xu" in topup["reply"]
    assert prompt["intent_id"] == "prompt_create_request"
    assert prompt["action_guard"] == "free_text_only"
    assert "nước hoa nam" in prompt["reply"]
    assert topup["provider_call_allowed"] is False
    assert prompt["provider_call_allowed"] is False


def test_cskh_shared_context_understands_followup_without_executing_action(tmp_path, monkeypatch):
    _isolated_env(tmp_path, monkeypatch)
    state = cskh.default_state()
    first_event = _event("tạo ảnh xe Lexus được không", message_id="m1")
    first = cskh.classify_business_event(first_event, conversation_memory=cskh.get_conversation_memory(state, "chat-5"))
    state = cskh.update_conversation_memory(state, first_event, first, reply=first["reply"], now=1000)
    follow_event = _event("làm đi", message_id="m2")
    follow = cskh.classify_business_event(
        follow_event,
        conversation_memory=cskh.get_conversation_memory(state, "chat-5", now=1001),
    )

    assert first["intent_id"] == "image_create_request"
    assert follow["intent_id"] == "image_action_confirm"
    assert follow["context_carry_used"] is True
    assert follow["last_offered_action"] == "open_image_ai_flow"
    assert "Lexus" in follow["reply"]
    assert "hóa đơn" in follow["reply"]
    assert "tự xác nhận" in follow["reply"]


def test_bot_live_handler_routes_action_to_quick_image_prefill_and_trace():
    handler_body = BOT_SOURCE.split("async def handle_aichat_message", 1)[1].split("async def cmd_cskh_business_status", 1)[0]
    callback_body = BOT_SOURCE.split("async def handle_aichat_callback", 1)[1].split("async def handle_aichat_message", 1)[0]
    prefill_body = BOT_SOURCE.split("def aichat_prepare_image_prefill_flow", 1)[1].split("async def cmd_aichat_on", 1)[0]

    assert "action_should_execute" in handler_body
    assert "open_image_ai_flow_with_prefill" in handler_body
    assert "aichat_prepare_image_prefill_flow" in handler_body
    assert "mark_action_execution" in handler_body
    assert "quick_image_prefill_opened_live" in handler_body
    assert 'if action == "open_image_prefill"' in callback_body
    assert "quick_image_prepared_prompt_text" in callback_body
    assert "quick_image_prefill_opened_by_button" in callback_body
    assert 'prompt_source="aichat"' in prefill_body
    assert 'back_callback="aichat|back_active"' in BOT_SOURCE
    assert "action_executed" in BOT_SOURCE
    assert "context_carry_used" in BOT_SOURCE
    assert "context_source" in BOT_SOURCE


def test_aichat5_no_real_provider_calls_or_forbidden_runtime_scope():
    changed = set(_changed_files())
    allowed = {
        "bot.py",
        "services/aas_shared_knowledge.py",
        "services/ai_chatbot_copilot.py",
        "services/telegram_business_support.py",
        "tests/test_p0_aichat1_copilot_consent.py",
        "tests/test_p0_aichat1b_free_tools_menu_cleanup.py",
        "tests/test_p0_aichat2_natural_context_pricing.py",
        "tests/test_p0_aichat4_smart_intent_context_backstack.py",
        "tests/test_p0_aichat5_live_context_action_trace.py",
        "tests/test_p0_aichat6_open_public_live_flows.py",
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
    forbidden_terms = ("music", "suno", "voice_provider", "product_video_provider", "subdub", "img2vid", "payos", "wallet", "payment")

    assert changed <= allowed
    assert not any(any(term in path.lower() for term in forbidden_terms) and not path.startswith("tests/") for path in changed)
