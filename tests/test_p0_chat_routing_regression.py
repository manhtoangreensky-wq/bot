import asyncio
from types import SimpleNamespace

import bot
from services import telegram_business_support as cskh


class _ReplyMessage:
    def __init__(self, text: str, message_id: int = 101):
        self.text = text
        self.message_id = message_id
        self.chat = SimpleNamespace(id=9001)
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))
        return SimpleNamespace(message_id=500 + len(self.replies))


def _text_update(text: str, user_id: int = 77):
    message = _ReplyMessage(text)
    return SimpleNamespace(
        message=message,
        effective_user=SimpleNamespace(id=user_id, username="tester", first_name="Tester"),
        effective_chat=SimpleNamespace(id=9001),
    )


def test_message_dispatch_deduplicates_same_chat_message(monkeypatch):
    calls = []

    async def handler(update, context):
        calls.append(update.message.message_id)
        return True

    guarded = bot.telegram_message_idempotent(handler)
    update = _text_update("hello")
    asyncio.run(guarded(update, SimpleNamespace()))
    asyncio.run(guarded(update, SimpleNamespace()))

    assert calls == [101]


def test_webhook_update_deduplicates_commands_and_callbacks(monkeypatch):
    calls = []

    class _App:
        async def process_update(self, update):
            calls.append(update)

    monkeypatch.setattr(bot, "tg_app", _App())
    payload = {"update_id": 90001, "message": {"message_id": 101}}
    update = SimpleNamespace()
    asyncio.run(bot.process_telegram_update_once(update, payload))
    asyncio.run(bot.process_telegram_update_once(update, payload))

    assert len(calls) == 1


def test_video_trim_input_is_owned_and_does_not_fall_through_to_chat(monkeypatch):
    uid = 77
    state = {
        "step": "await_trim_range",
        "source_metadata": {"duration_ms": 60_000},
        "source_duration_ms": 60_000,
        "manual_edit_plan": {},
    }
    monkeypatch.setattr(bot, "get_video_editor_pending", lambda _uid: dict(state))
    monkeypatch.setattr(bot, "clear_video_editor_competing_video_states", lambda *_args: None)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")

    update = _text_update("00:10-00:40", user_id=uid)
    handled = asyncio.run(bot.handle_video_editor_pending_text(update, SimpleNamespace()))

    assert handled is True
    assert len(update.message.replies) == 1
    assert "Dạ em chưa hiểu" not in update.message.replies[0][0]


def test_shopaikey_chat_completion_carries_only_same_chat_context(monkeypatch):
    calls = []

    async def fake_single(system_prompt, user_text, model, max_tokens=1200, history=None):
        calls.append(list(history or []))
        return {
            "status": "PASS",
            "provider": "shopaikey",
            "model": model,
            "text": "reply",
            "http_status": 200,
            "latency_ms": 1,
            "error_class": "",
        }

    monkeypatch.setattr(bot, "shopaikey_chat_completion_single_model", fake_single)
    monkeypatch.setattr(bot, "shopaikey_chat_model_sequence", lambda _override="": ["model-a"])
    monkeypatch.setattr(bot, "shopaikey_public_chat_fallback_enabled", lambda: True)
    monkeypatch.setattr(bot, "save_tool_test_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(bot, "save_shopaikey_chat_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(bot, "SHOPAIKEY_CHAT_MEMORY", {}, raising=False)

    asyncio.run(bot.shopaikey_chat_completion("normal system", "hello", "user-1"))
    asyncio.run(bot.shopaikey_chat_completion("normal system", "follow up", "user-1"))
    asyncio.run(bot.shopaikey_chat_completion("other system", "isolated", "user-1"))

    assert calls[0] == []
    assert calls[1] == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "reply"},
    ]
    assert calls[2] == []


def test_cskh_context_ttl_keeps_private_48_hour_memory(monkeypatch):
    monkeypatch.setenv("CSKH_CONVERSATION_TTL_SECONDS", str(48 * 60 * 60))

    assert cskh.conversation_ttl_seconds() == 48 * 60 * 60


def test_openai_fallback_does_not_send_current_message_twice(monkeypatch):
    calls = []

    class _Completions:
        def create(self, **kwargs):
            calls.append(kwargs["messages"])
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])

    fake_openai = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
    monkeypatch.setattr(bot, "gemini_client", None)
    monkeypatch.setattr(bot, "openai_client", fake_openai)
    monkeypatch.setattr(bot, "user_memory", {}, raising=False)
    monkeypatch.setattr(bot, "shopaikey_public_chat_fallback_enabled", lambda: False)
    monkeypatch.setattr(bot, "record_api_debug", lambda *args, **kwargs: None)

    asyncio.run(bot.call_ai_chat_with_fallback("system", "first", "user-1"))
    asyncio.run(bot.call_ai_chat_with_fallback("system", "second", "user-1"))

    assert [item["content"] for item in calls[0]] == ["system", "first"]
    second_contents = [item["content"] for item in calls[1]]
    assert second_contents.count("second") == 1
    assert second_contents == ["system", "first", "ok", "second"]


def test_cskh_classifier_memory_never_enters_normal_chat(monkeypatch):
    calls = []

    class _Completions:
        def create(self, **kwargs):
            calls.append(kwargs["messages"])
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])

    monkeypatch.setattr(bot, "gemini_client", None)
    monkeypatch.setattr(bot, "openai_client", SimpleNamespace(chat=SimpleNamespace(completions=_Completions())))
    monkeypatch.setattr(bot, "user_memory", {}, raising=False)
    monkeypatch.setattr(bot, "shopaikey_public_chat_fallback_enabled", lambda: False)
    monkeypatch.setattr(bot, "record_api_debug", lambda *args, **kwargs: None)

    asyncio.run(bot.call_ai_chat_with_fallback("cskh", "classification only", 77, memory_scope="cskh_classifier"))
    asyncio.run(bot.call_ai_chat_with_fallback("normal", "follow up", 77, memory_scope="normal_chat"))

    assert [item["content"] for item in calls[1]] == ["normal", "follow up"]




def test_json_task_router_does_not_pollute_chat_memory(monkeypatch):
    captured = []

    class _Models:
        def generate_content(self, **kwargs):
            captured.append(kwargs["contents"])
            return SimpleNamespace(text='{"action":"general","data":"hello"}')

    monkeypatch.setattr(bot, "gemini_client", SimpleNamespace(models=_Models()))
    monkeypatch.setattr(bot, "openai_client", None)
    monkeypatch.setattr(bot, "user_memory", {}, raising=False)
    monkeypatch.setattr(bot.types, "GenerateContentConfig", lambda **kwargs: kwargs)

    result = bot.AgentGemini.chat("route", "hello", "router-user", is_json=True)

    assert "router-user" not in bot.user_memory
    assert captured == ["hello"]
    assert '"action"' in result
