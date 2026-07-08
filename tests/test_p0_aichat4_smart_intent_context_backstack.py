import subprocess
from pathlib import Path

from services import ai_chatbot_copilot as aichat
from services import telegram_business_support as cskh


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _enabled_state(user_id="aichat4-user"):
    state = aichat.default_state()
    state, _enabled = aichat.enable_with_consent(state, user_id)
    return state


def _event(text, *, message_id="m1"):
    return cskh.BusinessMessageEvent(
        update_type="business_message",
        business_connection_id="bc-4",
        chat_id="chat-4",
        from_user_id="customer-4",
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


def test_aichat_image_lexus_request_is_image_flow_not_generic():
    state = _enabled_state()

    state, result = aichat.process_message(state, "aichat4-user", "tự tạo dùm tôi 1 bức ảnh về xe lexus", queue_unknown=False)
    folded = cskh._fold(result["reply"])

    assert result["intent_id"] == "image_create_request"
    assert result["target_flow"]["callback"] == "menu|main_image"
    assert result["provider_call_allowed"] is False
    assert result["xu_charge_allowed"] is False
    assert "Lexus" in result["reply"]
    assert "Prompt đề xuất" in result["reply"]
    assert "hoa don" in folded or "xac nhan" in folded


def test_aichat_image_followup_stays_on_previous_lexus_context():
    state = _enabled_state()

    state, first = aichat.process_message(state, "aichat4-user", "tự tạo dùm tôi 1 bức ảnh về xe lexus", queue_unknown=False)
    state, follow = aichat.process_message(state, "aichat4-user", "tự tạo dùm ảnh được không?", queue_unknown=False)
    state, short = aichat.process_message(state, "aichat4-user", "ảnh", queue_unknown=False)
    memory = aichat.status_payload(state, "aichat4-user")["conversation_memory"]

    assert first["intent_id"] == "image_create_request"
    assert follow["intent_id"] == "image_create_request"
    assert short["intent_id"] == "image_create_request"
    assert "Lexus" in short["reply"]
    assert memory["previous_topic"] == "image"
    assert memory["last_subject"] == "xe Lexus"


def test_aichat_short_image_without_context_asks_directed_followup_not_fallback():
    state = _enabled_state()

    state, result = aichat.process_message(state, "aichat4-user", "ảnh", queue_unknown=False)
    folded = cskh._fold(result["reply"])

    assert result["intent_id"] == "image_create_request"
    assert result["learning_queue"] is False
    assert "tao anh moi" in folded
    assert "xem gia" in folded
    assert "chinh anh" in folded


def test_aichat_video_sales_create_request_guides_flow_without_provider():
    state = _enabled_state()

    state, result = aichat.process_message(state, "aichat4-user", "tạo video bán hàng mỹ phẩm", queue_unknown=False)
    folded = cskh._fold(result["reply"])

    assert result["intent_id"] == "video_create_request"
    assert result["target_flow"]["callback"] == "menu|main_video"
    assert "mỹ phẩm" in result["reply"]
    assert "hoa don" in folded or "xac nhan" in folded
    assert result["provider_call_allowed"] is False


def test_aichat_prompt_video_request_returns_concrete_free_prompt():
    state = _enabled_state()

    state, result = aichat.process_message(state, "aichat4-user", "tạo prompt video nước hoa nam", queue_unknown=False)

    assert result["intent_id"] == "prompt_create_request"
    assert result["action_guard"] == "free_text_only"
    assert "nước hoa nam" in result["reply"]
    assert "9:16" in result["reply"]
    assert result["provider_call_allowed"] is False


def test_context_price_followup_uses_previous_image_topic():
    state = _enabled_state()

    state, _first = aichat.process_message(state, "aichat4-user", "tạo ảnh xe Lexus", queue_unknown=False)
    state, price = aichat.process_message(state, "aichat4-user", "giá", queue_unknown=False)

    assert price["intent_id"] == "image_ai_pricing"
    assert "50 Xu" in price["reply"]
    assert "600 Xu" in price["reply"]


def test_support_complaint_keeps_safe_handoff_reply():
    state = _enabled_state()

    state, result = aichat.process_message(state, "aichat4-user", "bot trừ Xu rồi không ra video", queue_unknown=False)
    folded = cskh._fold(result["reply"])

    assert result["intent_id"] == "complaint_charged_no_result"
    assert "mã xử lý" in result["reply"]
    assert "kiem tra" in folded
    assert "da hoan xu" not in folded
    assert "da cong xu" not in folded
    assert result["provider_call_allowed"] is False


def test_cskh_business_uses_same_image_intent_and_context_carry():
    state = cskh.default_state()
    first_event = _event("tạo dùm ảnh xe Lexus được không", message_id="m1")
    first = cskh.classify_business_event(first_event, conversation_memory=cskh.get_conversation_memory(state, "chat-4"))
    state = cskh.update_conversation_memory(state, first_event, first, reply=first["reply"], now=1000)

    follow_event = _event("ảnh", message_id="m2")
    follow = cskh.classify_business_event(follow_event, conversation_memory=cskh.get_conversation_memory(state, "chat-4", now=1001))

    assert first["intent_id"] == "image_create_request"
    assert follow["intent_id"] == "image_create_request"
    assert "Lexus" in follow["reply"]
    assert first["context_file_used"] is True
    assert follow["source_file_version"]


def test_trace_records_context_source_confidence_and_subject():
    state = _enabled_state()

    state, _result = aichat.process_message(state, "aichat4-user", "tạo dùm ảnh xe Lexus được không", queue_unknown=False)
    trace = aichat.status_payload(state, "aichat4-user")["last_trace"]

    assert trace["intent_id"] == "image_create_request"
    assert trace["confidence"] == "high"
    assert trace["context_file_used"] is True
    assert trace["context_version"]
    assert trace["previous_topic"] == "image"
    assert trace["last_subject"] == "xe Lexus"


def test_aichat_status_trace_back_stack_has_explicit_active_and_free_tools_routes():
    assert 'callback_data="aichat|back_freehub"' in BOT_SOURCE
    assert 'callback_data=back_callback' in BOT_SOURCE
    assert 'back_callback = "aichat|back_active" if data.get("enabled") else "aichat|back_freehub"' in BOT_SOURCE
    assert 'if action == "back_active"' in BOT_SOURCE
    assert "free_hub_main_text(lang)" in BOT_SOURCE
    assert "free_hub_main_keyboard(lang)" in BOT_SOURCE


def test_aichat_back_stack_does_not_cross_to_paid_or_unrelated_routes():
    callback_body = BOT_SOURCE.split("async def handle_aichat_callback", 1)[1].split("async def handle_aichat_message", 1)[0]

    assert "menu|main_video" not in callback_body
    assert "menu|translate" not in callback_body
    assert "invoice" not in callback_body.lower()
    assert "payos" not in callback_body.lower()


def test_no_real_provider_calls_or_forbidden_runtime_scope():
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
    forbidden_terms = ("music", "suno", "voice_provider", "product_video_provider", "payos", "wallet", "payment")

    assert changed <= allowed
    assert not any(any(term in path.lower() for term in forbidden_terms) and not path.startswith("tests/") for path in changed)
