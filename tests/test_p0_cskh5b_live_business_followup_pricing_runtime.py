import asyncio
import inspect
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

from aiedit1_scope_guard import without_aiedit1_scope

from services import telegram_business_support as cskh


ROOT = Path(__file__).resolve().parents[1]


class FakeBot:
    def __init__(self):
        self.id = "999"
        self.sent_messages = []

    async def send_message(self, **kwargs):
        self.sent_messages.append(kwargs)
        return SimpleNamespace(message_id=len(self.sent_messages))


def _event(text="alo", *, message_id=1, chat_id="chat-1", connection_id="bc-1", from_user_id="user-1", at=None):
    return cskh.BusinessMessageEvent(
        update_type="business_message",
        business_connection_id=connection_id,
        chat_id=str(chat_id),
        from_user_id=str(from_user_id),
        from_is_bot=False,
        text=text,
        caption="",
        message_id=str(message_id),
        timestamp=float(at if at is not None else 1000 + int(message_id)),
        media_type="",
    )


def _ctx(fake_bot=None):
    return SimpleNamespace(bot=fake_bot or FakeBot())


def _run(coro):
    return asyncio.run(coro)


def _enabled_state():
    return {
        **cskh.default_state(),
        "enabled": True,
        "connections": {"bc-1": {"id": "bc-1", "is_enabled": True}},
    }


def _save_into(box):
    def save(next_state):
        box.clear()
        box.update(next_state)
        return box

    return save


def _process(state, event, fake_bot=None, *, allow_debounce=False):
    fake_bot = fake_bot or FakeBot()
    result = _run(
        cskh.process_business_event_runtime(
            event,
            _ctx(fake_bot),
            state=state,
            save_state_fn=_save_into(state),
            bot_user_id="999",
            allow_debounce=allow_debounce,
        )
    )
    return result, fake_bot


def _changed_files():
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main"],
        check=False,
        text=True,
        capture_output=True,
        cwd=ROOT,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def test_cskh5b_live_uses_same_brain_as_cskh_test_for_gia_video():
    live = cskh.classify_business_event(_event("giá video"))
    test = cskh.classify_cskh_message("giá video")

    assert live["intent_id"] == test["intent_id"] == "product_video_pricing"
    assert live["playbook_scenario_id"] == test["playbook_scenario_id"] == "video_sales_consulting"
    assert live["reply_template_id"].startswith(("playbook:", "shared_knowledge:"))
    assert test["reply_template_id"].startswith(("playbook:", "shared_knowledge:"))
    assert "context_file" in live["source"]
    assert "context_file" in test["source"]


def test_cskh5b_live_uses_same_brain_as_cskh_test_for_bang_gia():
    live = cskh.classify_business_event(_event("bảng giá"))
    test = cskh.classify_cskh_message("bảng giá")

    assert live["intent_id"] == test["intent_id"] == "pricing_table_general"
    assert live["reply"] == test["reply"]


def test_cskh5b_live_uses_playbook_for_how_to_use():
    result = cskh.classify_business_event(_event("bot này dùng sao"))

    assert result["intent_id"] == "new_user_what_is_toan_aas"
    assert result["playbook_scenario_id"] == "new_user_how_to_use"


def test_cskh5b_live_no_old_generic_template_when_brain_matches():
    result = cskh.classify_business_event(_event("giá video"))

    assert result["intent_id"] == "product_video_pricing"
    assert result["reply_template_id"].startswith(("playbook:", "shared_knowledge:"))
    assert "context_file" in result["source"]
    assert "Chào bạn" not in result["reply"]


def test_cskh5b_after_alo_gia_video_replies():
    state = _enabled_state()
    bot = FakeBot()

    _process(state, _event("alo", message_id=1), bot)
    result, _bot = _process(state, _event("giá video", message_id=2), bot)

    assert result["sent"] is True
    assert result["classification"]["intent_id"] == "product_video_pricing"
    assert len(bot.sent_messages) == 2


def test_cskh5b_after_alo_bang_gia_replies():
    state = _enabled_state()
    bot = FakeBot()

    _process(state, _event("alo", message_id=1), bot)
    result, _bot = _process(state, _event("bảng giá", message_id=2), bot)

    assert result["sent"] is True
    assert result["classification"]["intent_id"] == "pricing_table_general"
    assert "Video AI" in bot.sent_messages[-1]["text"]


def test_cskh5b_gia_video_then_bang_gia_not_suppressed():
    state = _enabled_state()
    bot = FakeBot()

    _process(state, _event("giá video", message_id=1), bot)
    result, _bot = _process(state, _event("bảng giá", message_id=2), bot)

    assert result["sent"] is True
    assert result["guard"]["block_reason"] == ""
    assert len(bot.sent_messages) == 2


def test_cskh5b_exact_duplicate_still_suppressed():
    state = _enabled_state()
    bot = FakeBot()

    _process(state, _event("giá video", message_id=1), bot)
    result, _bot = _process(state, _event("giá video", message_id=2), bot)

    assert result["sent"] is False
    assert result["guard"]["block_reason"] == "exact_duplicate"
    assert len(bot.sent_messages) == 1


def test_cskh5b_pricing_keyword_bypasses_greeting_cooldown():
    state = _enabled_state()
    e1 = _event("alo", message_id=1)
    c1 = cskh.classify_business_event(e1)
    state = cskh.record_auto_reply(state, e1, c1, guard=cskh.evaluate_auto_reply_guard(state, e1, now=1000, classification=c1))
    e2 = _event("giá video", message_id=2)
    c2 = cskh.classify_business_event(e2, conversation_memory=cskh.get_conversation_memory(state, e2.chat_id))
    guard = cskh.evaluate_auto_reply_guard(state, e2, now=1001, classification=c2)

    assert guard["allowed"] is True
    assert guard["pricing_cooldown_bypass"] is True


def test_cskh5b_different_intent_bypasses_previous_cooldown():
    state = _enabled_state()
    bot = FakeBot()

    _process(state, _event("giá video", message_id=1), bot)
    result, _bot = _process(state, _event("giá ảnh như nào", message_id=2), bot)

    assert result["sent"] is True
    assert result["classification"]["intent_id"] == "image_ai_pricing"


def test_cskh5b_bang_gia_classifies_pricing_table_general():
    assert cskh.classify_cskh_message("cho em bảng giá")["intent_id"] == "pricing_table_general"


def test_cskh5b_bang_gia_reply_lists_main_categories():
    reply = cskh.classify_cskh_message("bảng giá")["reply"]

    for expected in ("Video AI", "ảnh", "SubDub", "voice", "bot riêng"):
        assert expected in reply


def test_cskh5b_bang_gia_uses_verified_pricing_doc_numbers():
    reply = cskh.classify_cskh_message("bảng giá")["reply"].lower()

    for marker in ("1 xu = 100đ", "50 / 150 / 200", "200 / 300 / 400", "0.1 xu/ký tự"):
        assert marker in reply


def test_cskh5b_bang_gia_mentions_invoice_before_charge():
    reply = cskh.classify_cskh_message("bảng giá")["reply"]

    assert "hiện hóa đơn trước" in reply


def test_cskh5b_alo_new_chat_short_helpful():
    result = cskh.classify_cskh_message("alo")

    assert result["intent_id"] == "greeting_ping"
    assert result["reply_template_id"] == "context_greeting:new"
    assert len(result["reply"]) < 120


def test_cskh5b_alo_existing_pricing_context_not_full_onboarding():
    memory = {"conversation_stage": "pricing", "last_intent": "product_video_pricing", "last_product": "product_video"}
    result = cskh.classify_cskh_message("alo", conversation_memory=memory)

    assert result["reply_template_id"] == "context_greeting:pricing"
    assert "TOAN AAS có thể hỗ trợ" not in result["reply"]
    assert "bảng giá tổng" in result["reply"]


def test_cskh5b_alo_then_gia_video_buffer_prioritizes_price():
    result = cskh.classify_thread_messages(["alo", "giá video"])

    assert result["intent_id"] == "product_video_pricing"


def test_cskh5b_repeated_alo_does_not_spam_long_intro():
    result = cskh.classify_cskh_message("alo")

    assert len(result["reply"]) < 120
    assert "hướng dẫn mình từng bước" not in result["reply"]


def test_cskh5b_buffer_alo_gia_video_bang_gia_replies_once_pricing():
    state = _enabled_state()
    bot = FakeBot()

    _process(state, _event("alo", message_id=1), bot, allow_debounce=True)
    _process(state, _event("giá video", message_id=2), bot, allow_debounce=True)
    _process(state, _event("bảng giá", message_id=3), bot, allow_debounce=True)
    state, buffer = cskh.pop_message_buffer(state, "chat-1", force=True)
    event = cskh.event_from_buffer(buffer)
    result, _bot = _process(state, event, bot, allow_debounce=False)

    assert result["sent"] is True
    assert result["classification"]["intent_id"] == "product_video_pricing"
    assert result["classification"]["reply_template_id"] == "pricing_thread:video_plus_table"
    assert len(bot.sent_messages) == 1


def test_cskh5b_buffer_prioritizes_pricing_over_greeting():
    result = cskh.classify_thread_messages(["alo", "bảng giá"])

    assert result["intent_id"] == "pricing_table_general"


def test_cskh5b_separate_price_messages_can_each_reply_after_debounce():
    state = _enabled_state()
    bot = FakeBot()

    _process(state, _event("giá video", message_id=1, at=1000), bot)
    result, _bot = _process(state, _event("bảng giá", message_id=2, at=1065), bot)

    assert result["sent"] is True
    assert len(bot.sent_messages) == 2


def test_cskh5b_status_records_ignored_gia_video_reason():
    state = _enabled_state()
    e1 = _event("giá video", message_id=1)
    c1 = cskh.classify_business_event(e1)
    state = cskh.record_auto_reply(state, e1, c1, guard=cskh.evaluate_auto_reply_guard(state, e1, now=1000, classification=c1))
    e2 = _event("giá video", message_id=2)
    c2 = cskh.classify_business_event(e2)
    guard = cskh.evaluate_auto_reply_guard(state, e2, now=1001, classification=c2)
    state = cskh.record_suppressed(state, e2, c2, guard)
    payload = cskh.status_payload(state)

    assert payload["last_block_reason"] == "exact_duplicate"
    assert payload["last_ignored_message"]["text"] == "giá video"
    assert payload["last_cooldown_key"]
    assert payload["last_duplicate_key"]


def test_cskh5b_status_records_bang_gia_reply_success():
    state = _enabled_state()
    bot = FakeBot()

    _process(state, _event("bảng giá", message_id=1), bot)
    payload = cskh.status_payload(state)

    assert payload["last_reply_sent"] is True
    assert payload["last_intent"] == "pricing_table_general"
    assert payload["last_brain_path"] == "cskh4_cskh6"


def test_cskh5b_trace_shows_last_messages():
    state = _enabled_state()
    bot = FakeBot()

    _process(state, _event("alo", message_id=1), bot)
    _process(state, _event("bảng giá", message_id=2), bot)
    trace = cskh.status_payload(state)["business_trace"]

    assert len(trace) == 2
    assert trace[-1]["intent_id"] == "pricing_table_general"
    assert trace[-1]["replied"] is True


def test_cskh5b_trace_admin_only():
    source = (ROOT / "bot.py").read_text(encoding="utf-8")
    assert 'CommandHandler("cskh_business_trace", cmd_cskh_business_trace)' in source
    trace_source = source[source.find("async def cmd_cskh_business_trace") : source.find("async def cmd_cskh_on")]
    assert "is_admin_user" in trace_source


def test_cskh5b_cskh_on_persists_armed_state(tmp_path):
    path = tmp_path / "cskh_state.json"
    saved = cskh.save_state(cskh.set_enabled(cskh.default_state(), True), path)
    loaded = cskh.load_state(path)

    assert saved["enabled"] is True
    assert loaded["enabled"] is True


def test_cskh5b_cskh_off_persists_off_state(tmp_path):
    path = tmp_path / "cskh_state.json"
    saved = cskh.save_state(cskh.set_enabled(cskh.default_state(), False), path)
    loaded = cskh.load_state(path)

    assert saved["enabled"] is False
    assert loaded["enabled"] is False


def test_cskh5b_status_shows_state_source():
    payload = cskh.status_payload(cskh.default_state())

    assert payload["state_source"]


def test_cskh5b_live_repro_sequence_all_distinct_followups_reply():
    state = _enabled_state()
    bot = FakeBot()

    _process(state, _event("giá video như nào", message_id=1, at=1000), bot)
    _process(state, _event("giá ảnh như nào", message_id=2, at=1001), bot)
    _process(state, _event("alo", message_id=3, at=1100), bot)
    _process(state, _event("giá video", message_id=4, at=1101), bot)
    _process(state, _event("bảng giá", message_id=5, at=1102), bot)

    assert [item["text"] for item in bot.sent_messages][-5:]
    assert len(bot.sent_messages) == 5
    assert cskh.status_payload(state)["business_trace"][-1]["intent_id"] == "pricing_table_general"


def test_cskh5b_live_repro_sequence_no_silent_bang_gia():
    state = _enabled_state()
    bot = FakeBot()

    _process(state, _event("alo", message_id=1), bot)
    result, _bot = _process(state, _event("bảng giá", message_id=2), bot)

    assert result["sent"] is True
    assert bot.sent_messages[-1]["text"]


def test_cskh5b_live_repro_sequence_no_chatwide_cooldown_block():
    state = _enabled_state()
    e1 = _event("alo", message_id=1)
    c1 = cskh.classify_business_event(e1)
    state = cskh.record_auto_reply(state, e1, c1, guard=cskh.evaluate_auto_reply_guard(state, e1, now=1000, classification=c1))
    e2 = _event("bảng giá", message_id=2)
    c2 = cskh.classify_business_event(e2, conversation_memory=cskh.get_conversation_memory(state, e2.chat_id))
    guard = cskh.evaluate_auto_reply_guard(state, e2, now=1001, classification=c2)

    assert guard["allowed"] is True
    assert guard["block_reason"] == ""


def test_cskh5b_no_locked_runtime_scope_changes():
    changed = without_aiedit1_scope(_changed_files())
    allowed = {
        "bot.py",
        "knowledge/toan_aas_cskh_aichat_context.md",
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
        "tests/test_p0_cskh_aichat3_context_brain_retrieval.py",
        "tests/test_p0_cskh6_human_touch_playbook_safe_training_pack.py",
        "tests/test_p0_cskh5c_business_self_echo_duplicate_guard.py",
        "tests/test_p0_cskh5b_live_business_followup_pricing_runtime.py",
    }
    forbidden_fragments = (
        "music",
        "product_video",
        "img2vid",
        "subdub",
        "voice",
        "payos",
        "wallet",
        "payment",
        "provider",
        "database",
        "webhook",
        "remote_worker",
        "local_worker",
    )

    assert changed <= allowed
    assert not any(any(fragment in path.lower() for fragment in forbidden_fragments) and not path.startswith("tests/") for path in changed)


def test_cskh5b_no_provider_calls():
    source = inspect.getsource(cskh)

    assert "ShopAIKey" not in source
    assert "Key4U" not in source
    assert "requests.post" not in source
