import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import telegram_business_support as cskh


ROOT = Path(__file__).resolve().parents[1]


class FakeBot:
    def __init__(self, *, bot_id="999", username="toanaasbot"):
        self.id = str(bot_id)
        self.username = username
        self.sent_messages = []

    async def send_message(self, **kwargs):
        self.sent_messages.append(kwargs)
        return SimpleNamespace(message_id=9000 + len(self.sent_messages))


def _event(
    text="alo",
    *,
    message_id=1,
    chat_id="chat-1",
    connection_id="bc-1",
    from_user_id="user-1",
    from_username="customer",
    from_is_bot=False,
    media_type="",
    caption="",
    has_service_payload=False,
    sender_business_bot_id="",
    sender_business_bot_username="",
    via_bot_id="",
    via_bot_username="",
    reply_to_from_user_id="",
    reply_to_from_is_bot=False,
    reply_to_from_username="",
    is_from_offline=False,
    update_type="business_message",
    update_id="",
):
    return cskh.BusinessMessageEvent(
        update_type=update_type,
        business_connection_id=connection_id,
        chat_id=str(chat_id),
        from_user_id=str(from_user_id),
        from_is_bot=bool(from_is_bot),
        text=text,
        caption=caption,
        message_id=str(message_id),
        timestamp=1000.0 + int(message_id),
        media_type=media_type,
        is_edited=update_type == "edited_business_message",
        update_id=str(update_id or message_id),
        from_username=from_username,
        sender_business_bot_id=str(sender_business_bot_id or ""),
        sender_business_bot_username=sender_business_bot_username,
        via_bot_id=str(via_bot_id or ""),
        via_bot_username=via_bot_username,
        reply_to_message_id="bot-msg" if reply_to_from_user_id else "",
        reply_to_from_user_id=str(reply_to_from_user_id or ""),
        reply_to_from_is_bot=bool(reply_to_from_is_bot),
        reply_to_from_username=reply_to_from_username,
        is_from_offline=bool(is_from_offline),
        has_service_payload=bool(has_service_payload),
    )


def _enabled_state():
    return {
        **cskh.default_state(),
        "enabled": True,
        "connections": {
            "bc-1": {
                "id": "bc-1",
                "is_enabled": True,
                "user_id": "owner-1",
                "username": "owner",
            }
        },
    }


def _save_into(box):
    def save(next_state):
        box.clear()
        box.update(next_state)
        return box

    return save


def _run(coro):
    return asyncio.run(coro)


def _process(state, event, bot=None):
    fake_bot = bot or FakeBot()
    result = _run(
        cskh.process_business_event_runtime(
            event,
            SimpleNamespace(bot=fake_bot),
            state=state,
            save_state_fn=_save_into(state),
            bot_user_id=fake_bot.id,
            bot_username=fake_bot.username,
            allow_debounce=False,
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


@pytest.mark.parametrize(
    "event",
    [
        _event("giá video", from_user_id="999", from_username="toanaasbot", from_is_bot=True),
        _event("giá video", from_user_id="777", from_username="toanaasbot"),
        _event("giá video", sender_business_bot_id="999"),
        _event("giá video", sender_business_bot_username="toanaasbot"),
        _event("giá video", via_bot_id="999"),
        _event("giá video", from_user_id="owner-1", from_username="owner", is_from_offline=True),
        _event("giá video", from_user_id="999", update_type="edited_business_message", from_is_bot=True),
    ],
)
def test_cskh5c_self_or_outbound_business_messages_are_ignored(event):
    state = _enabled_state()
    result, bot = _process(state, event)

    assert result["sent"] is False
    assert result["guard"]["block_reason"] == "self_or_outbound_message"
    assert result["guard"]["self_or_outbound_suppressed"] is True
    assert bot.sent_messages == []
    assert state["business_trace"][-1]["block_reason"] == "self_or_outbound_message"


@pytest.mark.parametrize(
    "event",
    [
        _event("", media_type="sticker"),
        _event("🎉 👋 Dân nhắn", has_service_payload=True),
        _event("🙂🙂"),
    ],
)
def test_cskh5c_non_text_service_and_sticker_do_not_enter_classifier(monkeypatch, event):
    state = _enabled_state()

    def fail_classifier(*_args, **_kwargs):
        raise AssertionError("non-text/service event must not enter classifier")

    monkeypatch.setattr(cskh, "classify_business_event", fail_classifier)
    result, bot = _process(state, event)

    assert result["sent"] is False
    assert result["guard"]["block_reason"] == "non_text_or_service_event"
    assert bot.sent_messages == []
    assert state["business_trace"][-1]["eligible"] is False


def test_cskh5c_media_without_caption_asks_customer_what_to_do():
    state = _enabled_state()
    result, bot = _process(state, _event("", media_type="photo"))

    assert result["sent"] is True
    assert result["guard"]["block_reason"] == ""
    assert result["classification"]["intent_id"] == "file_without_instruction"
    assert "nhận được file" in bot.sent_messages[-1]["text"]


def test_cskh5c_media_caption_with_customer_text_is_allowed():
    state = _enabled_state()
    result, bot = _process(state, _event("", caption="giá video", media_type="photo"))

    assert result["sent"] is True
    assert result["guard"]["block_reason"] == ""
    assert bot.sent_messages


def test_cskh5c_same_real_message_replies_once_with_idempotency_key():
    state = _enabled_state()
    bot = FakeBot()
    event = _event("giá video", message_id=21, update_id=2100)

    first, _bot = _process(state, event, bot)
    second, _bot = _process(state, _event("giá video", message_id=21, update_id=2199), bot)

    assert first["sent"] is True
    assert second["sent"] is False
    assert second["guard"]["block_reason"] == "already_replied_event"
    assert second["guard"]["already_replied_event_suppressed"] is True
    assert len(bot.sent_messages) == 1


def test_cskh5c_customer_reply_to_bot_with_text_is_allowed_but_quote_only_echo_is_ignored():
    state = _enabled_state()
    bot = FakeBot()

    customer_reply = _event(
        "giá video",
        message_id=31,
        reply_to_from_user_id="999",
        reply_to_from_is_bot=True,
        reply_to_from_username="toanaasbot",
    )
    quote_only = _event(
        "",
        message_id=32,
        reply_to_from_user_id="999",
        reply_to_from_is_bot=True,
        reply_to_from_username="toanaasbot",
    )

    allowed, _bot = _process(state, customer_reply, bot)
    ignored, _bot = _process(state, quote_only, bot)

    assert allowed["sent"] is True
    assert ignored["sent"] is False
    assert ignored["guard"]["block_reason"] == "non_text_or_service_event"
    assert len(bot.sent_messages) == 1


def test_cskh5c_confused_customer_intent_answers_naturally():
    result = cskh.classify_business_event(_event("?"))

    assert result["intent_id"] == "vague_or_unclear"
    assert "Mình nhắn giúp em rõ hơn" in result["reply"]
    assert "giá" in result["reply"]


def test_cskh5c_live_screenshot_repro_service_then_self_echo_then_customer_question():
    state = _enabled_state()
    bot = FakeBot()

    service_event = _event("🎉 👋 Dân nhắn", message_id=41, has_service_payload=True, from_user_id="")
    own_echo = _event(
        "Dạ được ạ. Nếu anh/chị đã có ảnh sẵn...",
        message_id=42,
        from_user_id="999",
        from_username="toanaasbot",
        from_is_bot=True,
    )
    confused = _event("gì vậy?", message_id=43)

    service_result, _bot = _process(state, service_event, bot)
    echo_result, _bot = _process(state, own_echo, bot)
    confused_result, _bot = _process(state, confused, bot)

    assert service_result["guard"]["block_reason"] == "non_text_or_service_event"
    assert echo_result["guard"]["block_reason"] == "self_or_outbound_message"
    assert confused_result["sent"] is True
    assert confused_result["classification"]["intent_id"] in {"customer_confused_or_what", "vague_or_unclear"}
    assert len(bot.sent_messages) == 1
    assert [item["block_reason"] for item in state["business_trace"][-3:]] == [
        "non_text_or_service_event",
        "self_or_outbound_message",
        "",
    ]


def test_cskh5c_trace_keeps_last_ten_ignored_events_with_direction_and_reason():
    state = _enabled_state()
    bot = FakeBot()
    for index in range(12):
        _process(state, _event("", message_id=100 + index, media_type="sticker"), bot)

    trace = state["business_trace"]
    assert len(trace) == 10
    assert all(item["block_reason"] == "non_text_or_service_event" for item in trace)
    assert all(item["direction_guess"] == "non_text_or_service" for item in trace)
    assert all(item["idempotency_key"].startswith("replied:") for item in trace)
    assert state["last_debug"]["block_reason"] == "non_text_or_service_event"
    assert state["last_debug"]["idempotency_key"].startswith("replied:")


def test_cskh5c_scope_guard_only_touches_cskh_runtime_bot_trace_and_tests():
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
        "tests/test_p0_17c1_payos_signature_idempotency.py",
        "tests/test_p0_17c2_payos_auto_topup_limits.py",
        "tests/test_p0_cskh1_telegram_business_auto_support_bot.py",
        "tests/test_p0_cskh2_toan_aas_training_data_playbook.py",
        "tests/test_p0_cskh2a_business_arm_mode_without_connection.py",
        "tests/test_p0_cskh3_conversation_brain_natural_replies.py",
        "tests/test_p0_cskh5b_live_business_followup_pricing_runtime.py",
        "tests/test_p0_cskh_aichat3_context_brain_retrieval.py",
        "tests/test_p0_cskh6_human_touch_playbook_safe_training_pack.py",
        "tests/test_p0_cskh5c_business_self_echo_duplicate_guard.py",
    }

    assert set(_changed_files()).issubset(allowed)
