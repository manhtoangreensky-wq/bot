import asyncio
from types import SimpleNamespace

import pytest

import bot


def test_public_translation_response_and_language_mapping_are_deterministic():
    payload = [[
        ["Xin chào", "Hello", None, None],
        [" thế giới", " world", None, None],
    ]]

    assert bot.parse_public_translation_response(payload) == "Xin chào thế giới"
    assert bot.public_translation_target_code("zh_tw") == "zh-TW"
    assert bot.public_translation_target_code("fil") == "tl"
    with pytest.raises(RuntimeError, match="unsupported_target"):
        bot.public_translation_target_code("auto")


def test_public_translation_fallback_covers_every_explicit_menu_target():
    explicit_targets = set(bot.TRANSLATE_LANGUAGE_OPTIONS) - {"auto"}

    assert explicit_targets == set(bot.PUBLIC_TRANSLATION_TARGET_CODES)


def test_shared_translation_chain_uses_public_fallback_without_paid_provider(monkeypatch):
    calls = []

    async def fake_public(text, target):
        calls.append((text, target))
        return "Xin chào"

    monkeypatch.setattr(bot, "DEEPL_API_KEY", "")
    monkeypatch.setattr(bot, "key4u_translation_provider_available", lambda: False)
    monkeypatch.setattr(bot, "PUBLIC_TRANSLATION_FALLBACK_ENABLED", True)
    monkeypatch.setattr(bot, "PUBLIC_TRANSLATION_FALLBACK_URL", "https://translation.invalid/test")
    monkeypatch.setattr(bot, "translate_with_public_fallback", fake_public)
    monkeypatch.setattr(bot, "gemini_client", None)
    monkeypatch.setattr(bot, "openai_client", None)

    result = asyncio.run(bot.translate_to_language("Hello", "vi"))

    assert result["provider"] == "public"
    assert result["text"] == "Xin chào"
    assert result["target"] == "vi"
    assert result["statuses"]["public"] == "PASS"
    assert calls == [("Hello", "vi")]


def test_public_failure_keeps_existing_provider_fallback_order(monkeypatch):
    calls = []

    async def fail_public(_text, _target):
        calls.append("public")
        raise RuntimeError("public unavailable")

    async def fake_gemini(_text, _target):
        calls.append("gemini")
        return "Bản dịch"

    monkeypatch.setattr(bot, "DEEPL_API_KEY", "")
    monkeypatch.setattr(bot, "key4u_translation_provider_available", lambda: False)
    monkeypatch.setattr(bot, "PUBLIC_TRANSLATION_FALLBACK_ENABLED", True)
    monkeypatch.setattr(bot, "PUBLIC_TRANSLATION_FALLBACK_URL", "https://translation.invalid/test")
    monkeypatch.setattr(bot, "translate_with_public_fallback", fail_public)
    monkeypatch.setattr(bot, "gemini_client", object())
    monkeypatch.setattr(bot, "translate_with_gemini", fake_gemini)
    monkeypatch.setattr(bot, "openai_client", None)

    result = asyncio.run(bot.translate_to_language("Source", "vi"))

    assert result["provider"] == "gemini"
    assert calls == ["public", "gemini"]
    assert result["statuses"]["public"] == "FAIL"


class _ExpiredConfirmQuery:
    def __init__(self, user_id):
        self.data = "videodub|final"
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace(chat_id=user_id)

    async def answer(self, *args, **kwargs):
        raise RuntimeError("Query is too old and response timeout expired or query id is invalid")


class _CaptureApplication:
    def __init__(self):
        self.tasks = []

    def create_task(self, coroutine, **kwargs):
        task = asyncio.create_task(coroutine)
        self.tasks.append(task)
        return task


def test_expired_confirm_acknowledgement_does_not_block_subdub_route(monkeypatch):
    async def scenario():
        user_id = 919001
        query = _ExpiredConfirmQuery(user_id)
        application = _CaptureApplication()
        calls = []

        monkeypatch.setattr(
            bot,
            "get_video_dubbing_pending",
            lambda _uid: {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB},
        )
        monkeypatch.setattr(bot, "subtitle_dub_pipeline_job_key", lambda *_args: "job-live19")

        async def fake_background(_update, _context, task_key):
            calls.append(task_key)

        monkeypatch.setattr(bot, "_run_subdub_public_final_background", fake_background)
        bot.SUBDUB_PUBLIC_FINAL_BACKGROUND_TASKS.clear()

        await bot.handle_video_dubbing_callback(
            SimpleNamespace(callback_query=query),
            SimpleNamespace(application=application),
        )
        await asyncio.gather(*application.tasks)

        assert calls == ["job-live19"]
        bot.SUBDUB_PUBLIC_FINAL_BACKGROUND_TASKS.clear()

    asyncio.run(scenario())


def test_callback_acknowledgement_does_not_hide_unrelated_errors():
    class BrokenQuery:
        async def answer(self):
            raise RuntimeError("network transport failure")

    with pytest.raises(RuntimeError, match="network transport failure"):
        asyncio.run(bot.safe_answer_callback_query(BrokenQuery()))
