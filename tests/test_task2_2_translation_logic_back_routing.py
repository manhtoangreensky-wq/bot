import asyncio
import inspect
from types import SimpleNamespace

import bot


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class FakeMessage:
    def __init__(self, text=""):
        self.text = text
        self.replies = []
        self.audio_replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))

    async def reply_audio(self, **kwargs):
        self.audio_replies.append(kwargs)


def _update(user_id, message):
    return SimpleNamespace(effective_user=SimpleNamespace(id=user_id), message=message)


def test_two_way_translation_accepts_text(monkeypatch):
    uid = 822001
    bot.clear_translation_session(uid)
    bot.set_translation_session(uid, "two_way", "vi", "en")
    message = FakeMessage("Xin chào bạn")

    async def fake_translate(text, target, **kwargs):
        return {"provider": "test", "text": "Hello", "target": target}

    monkeypatch.setattr(bot, "translate_subtitle_text", fake_translate)
    assert asyncio.run(bot.handle_translation_session_text(_update(uid, message), SimpleNamespace())) is True
    assert "Hello" in message.replies[-1][0]


def test_two_way_translation_accepts_voice(monkeypatch):
    uid = 822002
    bot.clear_translation_session(uid)
    bot.set_translation_session(uid, "two_way", "vi", "en")
    message = FakeMessage()

    async def fake_media(update, context):
        return {"bytes": b"voice", "content_type": "audio/ogg", "file_id": "voice-1"}

    async def fake_stt(*args, **kwargs):
        return "Key4U ASR", "Xin chào bạn", "ok"

    async def fake_translate(text, target, **kwargs):
        return {"provider": "test", "text": "Hello", "target": target}

    monkeypatch.setattr(bot, "resolve_stt_test_media", fake_media)
    monkeypatch.setattr(bot, "video_dubbing_transcribe_bytes", fake_stt)
    monkeypatch.setattr(bot, "translate_subtitle_text", fake_translate)
    assert asyncio.run(bot.handle_translation_session_media(_update(uid, message), SimpleNamespace())) is True
    assert "Hello" in message.replies[-1][0]
    assert bot.get_translation_session(uid)["source_ref"] == "voice-1"


def test_two_way_translation_swap_direction():
    source, target = bot.translation_detect_direction("Hello, how are you?", {"lang_a": "en", "lang_b": "vi"})
    assert source == "en"
    assert target == "vi"


def test_conversation_translation_detects_direction():
    session = {"mode": "live_conversation", "lang_a": "vi", "lang_b": "en"}
    assert bot.translation_detect_direction("Tôi muốn dịch câu này", session)[1] == "en"
    assert bot.translation_detect_direction("Hello, this is a conversation", session)[1] == "vi"


def test_voice_translation_returns_text_even_if_tts_off(monkeypatch):
    message = FakeMessage()
    session = {"mode": "two_way", "lang_a": "vi", "lang_b": "en", "output_mode": "voice"}
    monkeypatch.setattr(bot, "video_tts_provider_available", lambda: False)
    asyncio.run(bot.send_translation_session_result(_update(822003, message), SimpleNamespace(), session, "Xin chào", "Hello", "vi", "en"))
    assert "Hello" in message.replies[-1][0]
    assert message.audio_replies == []


def test_language_tools_not_deleted():
    _, markup = bot.localized_menu_content("translation_language_hub", False, "vi", user_id=822004)
    callbacks = _callbacks(markup)
    assert "menu|translation_two_way" in callbacks
    assert "menu|translation_live_conversation" in callbacks
    assert "menu|translation_text" in callbacks
    assert "menu|translation_voice" in callbacks


def test_auto_subtitle_capcut_style_original_language(monkeypatch):
    async def no_subtitle(*args, **kwargs):
        return "", "none"

    async def fake_audio(*args, **kwargs):
        return b"speech", "audio/mpeg", "ffmpeg"

    async def fake_stt(*args, **kwargs):
        return "Key4U ASR", "Đây là lời nói gốc", "ok"

    monkeypatch.setattr(bot, "video_dubbing_extract_embedded_subtitle", no_subtitle)
    monkeypatch.setattr(bot, "video_dubbing_extract_audio", fake_audio)
    monkeypatch.setattr(bot, "video_dubbing_transcribe_bytes", fake_stt)
    result = asyncio.run(bot.video_dubbing_resolve_source_script(b"video", "video/mp4", SimpleNamespace(), 10))
    assert result["script"] == "Đây là lời nói gốc"
    assert "-->" in result["subtitle"]


def test_auto_subtitle_no_translate_no_voice():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}
    capability_source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert bot.video_dubbing_requires_voice(state["mode"]) is False
    assert "mode == VIDEO_SUBTITLE_MODE_TRANSLATE" in inspect.getsource(bot.video_dubbing_prepare_subtitles)
    assert "mode in {VIDEO_SUBTITLE_MODE_DUB" in capability_source


def test_auto_subtitle_preview_back_returns_output():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE, "source_file_id": "file-1"}
    assert bot.video_dubbing_back_route(state, "preview_back") == "output"


def test_auto_subtitle_no_reupload_after_back():
    uid = 822010
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(uid, "confirm", mode=bot.VIDEO_SUBTITLE_MODE_CREATE, source_file_id="file-1")
    state = bot.set_video_dubbing_pending(uid, "output")
    assert state["source_file_id"] == "file-1"
    assert bot.video_dubbing_has_media(state)


def test_auto_dubbing_uses_existing_subtitle_or_asr(monkeypatch):
    embedded = "1\n00:00:00,000 --> 00:00:02,000\nHello"

    async def fake_embedded(*args, **kwargs):
        return embedded, "embedded_subtitle"

    async def fail_audio(*args, **kwargs):
        raise AssertionError("ASR must not run when a subtitle exists")

    monkeypatch.setattr(bot, "video_dubbing_extract_embedded_subtitle", fake_embedded)
    monkeypatch.setattr(bot, "video_dubbing_extract_audio", fail_audio)
    result = asyncio.run(bot.video_dubbing_resolve_source_script(b"video", "video/mp4", SimpleNamespace()))
    assert result["source_kind"] == "embedded_subtitle"
    assert result["script"] == "Hello"


def test_auto_dubbing_target_language_voice_speed():
    uid = 822011
    bot.clear_video_dubbing_pending(uid)
    state = bot.set_video_dubbing_pending(
        uid,
        "confirm",
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        source_file_id="file-1",
        target_language="English",
        voice_style="default_female",
        voice_speed="1.2",
    )
    assert state["selected_language"] == "English"
    assert state["selected_voice"] == "default_female"
    assert state["speed"] == "1.2"


def test_auto_dubbing_tts_reads_transcript():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert 'output_text = str(prepared.get("output_script")' in source
    assert "synthesize_dub_segment_chunks(" in source
    assert "output_text," in source


def test_auto_dubbing_preview_back_invoice():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "source_file_id": "file-1"}
    assert bot.video_dubbing_back_route(state, "preview_back") == "confirm"


def test_auto_dubbing_no_reupload_after_back():
    uid = 822012
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(uid, "confirm", mode=bot.VIDEO_SUBTITLE_MODE_DUB, source_file_id="file-2")
    for step in ("voice_speed", "voice", "language", "source"):
        state = bot.set_video_dubbing_pending(uid, step)
        assert state["source_file_id"] == "file-2"


def test_subtitle_plus_dubbing_translate_first(monkeypatch):
    uid = 822013
    bot.clear_video_dubbing_pending(uid)
    state = bot.set_video_dubbing_pending(uid, "output", mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE, requested_mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, source_file_id="file-3", target_language="vi", translate_requested="1")

    async def fake_download(*args, **kwargs):
        return b"video", "video/mp4"

    async def fake_source(*args, **kwargs):
        return {"subtitle": "1\n00:00:00,000 --> 00:00:02,000\nHello", "script": "Hello", "asr_provider": "test"}

    async def fake_translate(*args, **kwargs):
        return {"text": "1\n00:00:00,000 --> 00:00:02,000\nXin chào"}

    monkeypatch.setattr(bot, "video_dubbing_download_source", fake_download)
    monkeypatch.setattr(bot, "video_dubbing_resolve_source_script", fake_source)
    monkeypatch.setattr(bot, "translate_subtitle_text", fake_translate)
    prepared = asyncio.run(bot.video_dubbing_prepare_subtitles(SimpleNamespace(), state, uid))
    assert "Xin chào" in prepared["output_subtitle"]
    assert prepared["state"]["translated_subtitle_ref"]


def test_subtitle_plus_dubbing_export_before_voice():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "requested_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}
    callbacks = _callbacks(bot.video_dubbing_output_keyboard("vi", state))
    assert "videodub|output|srt" not in callbacks
    assert "videodub|final" in callbacks
    assert "videodub|continue_dubbing" not in callbacks
    ready_callbacks = _callbacks(bot.video_dubbing_output_keyboard("vi", {
        **state,
        "translated_subtitle_ref": "video_dubbing_artifact:test:translated",
    }))
    assert "videodub|output|srt" in ready_callbacks
    assert "videodub|continue_dubbing" in ready_callbacks
    ready_state = {**state, "translated_subtitle_ref": "video_dubbing_artifact:ready:translated"}
    assert "videodub|continue_dubbing" in _callbacks(bot.video_dubbing_output_keyboard("vi", ready_state))
    assert not any(callback.startswith("videodub|voice|") for callback in callbacks)


def test_subtitle_plus_dubbing_continue_uses_translated_subtitle(monkeypatch):
    uid = 822014
    bot.clear_video_dubbing_pending(uid)
    translated_ref = bot.set_video_dubbing_artifact(uid, "translated_subtitle", "1\n00:00:00,000 --> 00:00:02,000\nXin chào")
    source_ref = bot.set_video_dubbing_artifact(uid, "source_subtitle", "1\n00:00:00,000 --> 00:00:02,000\nHello")
    state = bot.set_video_dubbing_pending(uid, "voice", mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, source_file_id="file-4", target_language="vi", translate_requested="1", subtitle_ref=source_ref, translated_subtitle_ref=translated_ref)

    async def fake_download(*args, **kwargs):
        return b"video", "video/mp4"

    async def should_not_translate(*args, **kwargs):
        raise AssertionError("cached translated subtitle must be reused")

    monkeypatch.setattr(bot, "video_dubbing_download_source", fake_download)
    monkeypatch.setattr(bot, "translate_subtitle_text", should_not_translate)
    prepared = asyncio.run(bot.video_dubbing_prepare_subtitles(SimpleNamespace(), state, uid))
    assert prepared["output_script"] == "Xin chào"


def test_subtitle_plus_dubbing_preview_back_invoice():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "requested_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}
    assert bot.video_dubbing_back_route(state, "preview_back") == "confirm"


def test_subtitle_plus_dubbing_no_reupload_after_back():
    uid = 822015
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(uid, "confirm", mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, source_file_id="file-5")
    state = bot.set_video_dubbing_pending(uid, "output")
    assert state["source_file_id"] == "file-5"


def test_task2_back_source_to_product_menu():
    assert "videodub|back_type" in _callbacks(bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}))


def test_task2_back_language_to_source():
    assert bot.video_dubbing_back_route({"mode": bot.VIDEO_SUBTITLE_MODE_DUB}, "back_language_to_source") == "source"


def test_task2_back_voice_to_language_or_subtitle_output():
    assert bot.video_dubbing_back_route({"mode": bot.VIDEO_SUBTITLE_MODE_DUB}, "back_voice") == "language"
    combo = {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "requested_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}
    assert bot.video_dubbing_back_route(combo, "back_voice") == "output"


def test_task2_back_speed_to_voice():
    assert bot.video_dubbing_back_route({"mode": bot.VIDEO_SUBTITLE_MODE_DUB}, "back_speed") == "voice"


def test_task2_back_invoice_to_speed():
    assert bot.video_dubbing_back_route({"mode": bot.VIDEO_SUBTITLE_MODE_DUB}, "back_confirm") == "voice_speed"


def test_task2_back_preview_to_invoice():
    assert bot.video_dubbing_back_route({"mode": bot.VIDEO_SUBTITLE_MODE_DUB}, "preview_back") == "confirm"


def test_task2_back_output_to_output_choice():
    combo_stage = {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "requested_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}
    assert bot.video_dubbing_back_route(combo_stage, "preview_back") == "output"
    assert bot.video_dubbing_back_route(combo_stage, "subtitle_editor_back") == "output"


def test_public_never_sees_admin_blocker():
    assert "Admin blocker" not in bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_DUB, {}, "vi", admin=False)
    assert "Admin blocker" not in bot.translation_voice_guard_text(admin=False)


def test_admin_sees_admin_blocker():
    assert "Admin blocker" in bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_DUB, {}, "vi", admin=True)
    assert "Admin blocker" in bot.translation_voice_guard_text(admin=True)


def test_public_no_provider_terms():
    text = (bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_DUB, {}, "vi", admin=False) + " " + bot.translation_voice_guard_text(False)).lower()
    for term in ("provider", "api", "key4u", "shopaikey", "minimax", "smoke", "admin blocker"):
        assert term not in text
