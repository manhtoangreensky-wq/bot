import asyncio
import inspect
import json
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class CaptureMessage:
    def __init__(self, chat_id=171010):
        self.chat_id = chat_id
        self.outputs = []

    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        self.outputs.append({"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup, **kwargs})
        return SimpleNamespace(text=text, reply_markup=reply_markup)

    async def reply_document(self, document=None, filename=None, caption=None, **kwargs):
        data = b""
        if hasattr(document, "getvalue"):
            data = document.getvalue()
        self.outputs.append({"document": data, "filename": filename, "caption": str(caption or ""), **kwargs})
        return SimpleNamespace(document=SimpleNamespace(file_id="doc-id"))


def test_default_voice_locked_no_forced_preview_copy():
    text = bot.default_voice_confirm_text("Xin chào TOAN AAS", "female", "vi")
    assert "Giọng nam/nữ mặc định miễn phí và không trừ Xu" in text
    assert "6 giây" not in text
    assert "Nghe thử" not in text
    assert "cap_voice_preview_audio_bytes" not in inspect.getsource(bot.send_default_free_tts_result)


def test_custom_voice_readiness_checked_before_create(monkeypatch):
    profile = {
        "id": 77,
        "user_id": "171011",
        "display_name": "Voice riêng",
        "consent_status": "confirmed",
        "source_file_id": "telegram-file",
        "source_file_ref": "telegram-file",
        "provider_voice_id": "",
        "metadata_json": json.dumps({"confirmation_sample_text": bot.VOICE_CLONE_CONFIRMATION_SAMPLE_TEXT}, ensure_ascii=False),
    }
    store = dict(profile)
    provider_calls = {"count": 0}

    def update_profile(_uid, _pid, **fields):
        store.update(fields)
        return True

    async def forbidden_provider(*_args, **_kwargs):
        provider_calls["count"] += 1
        raise AssertionError("custom voice must not call provider before clone smoke is ready")

    monkeypatch.setattr(bot, "get_user_voice_profile", lambda _uid, _pid: dict(store))
    monkeypatch.setattr(bot, "update_user_voice_profile", update_profile)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(bot, "voice_clone_access_allowed", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(bot, "get_minimax_voice_clone_readiness", lambda: {
        "ready": True,
        "public_enabled": True,
        "shopaikey_configured": True,
        "key4u_configured": False,
        "tts_smoke": "PASS",
        "clone_smoke": "NOT_TESTED",
        "routes": ["shopaikey_minimax"],
    })
    monkeypatch.setattr(bot, "shopaikey_minimax_upload_voice_sample", forbidden_provider)
    monkeypatch.setattr(bot, "shopaikey_minimax_voice_clone", forbidden_provider)
    monkeypatch.setattr(bot, "shopaikey_minimax_tts_bytes", forbidden_provider)

    message = CaptureMessage()
    query = SimpleNamespace(message=message)
    asyncio.run(bot.create_minimax_voice_profile_preview(query, SimpleNamespace(bot=SimpleNamespace()), 171011, profile, "vi"))

    assert provider_calls["count"] == 0
    assert store["status"] == "failed_provider_not_ready"
    assert store["provider_voice_id"] == ""
    assert "Voice riêng đang được chuẩn bị" in message.outputs[-1]["text"]
    assert "đang tạo voice riêng" not in "\n".join(item["text"] for item in message.outputs)


def test_custom_voice_guard_fallback_buttons():
    markup = bot.voice_clone_permission_forbidden_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM)
    labels = _labels(markup)
    callbacks = _callbacks(markup)
    assert labels == ["🎙 Dùng giọng nữ mặc định", "🎙 Dùng giọng nam mặc định", "🔁 Thử lại sau", "⬅️ Kho voice", "🏠 Menu chính"]
    assert "music_quick|showroom|voice_default_female" in callbacks
    assert "music_quick|showroom|voice_default_male" in callbacks
    assert "music_quick|showroom|voice_clone" in callbacks


def test_translate_subtitle_text_uses_core_translation_chain(monkeypatch):
    calls = []

    async def fake_translate(text, target):
        calls.append((text, target))
        return {"provider": "deepl", "text": "Hello TOAN AAS", "target": target}

    monkeypatch.setattr(bot, "translate_to_language", fake_translate)
    monkeypatch.setattr(bot, "save_tool_test_result", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bot, "save_provider_attempt", lambda *_args, **_kwargs: None)

    result = asyncio.run(bot.translate_subtitle_text("Xin chào TOAN AAS", "en", updated_by=171012))

    assert calls == [("Xin chào TOAN AAS", "en")]
    assert result["provider"] == "deepl"
    assert result["text"] == "Hello TOAN AAS"


def test_subtitle_translate_failure_guard_clean_copy():
    text = bot.subtitle_translate_failure_text("vi")
    labels = _labels(bot.subtitle_translate_failure_keyboard("vi", "English"))
    callbacks = _callbacks(bot.subtitle_translate_failure_keyboard("vi", "English"))

    assert text == "TOAN AAS chưa dịch được phụ đề lúc này. Hệ thống chưa trừ Xu. Anh/chị có thể thử lại hoặc tải phụ đề gốc trước."
    assert labels == ["🔁 Thử lại", "📄 Tải phụ đề gốc", "🌐 Chọn ngôn ngữ khác", "⬅️ Quay lại", "🏠 Menu chính"]
    assert "videodub|language|English" in callbacks
    assert "videodub|download_original_srt" in callbacks
    assert "videodub|back_language" in callbacks


def test_subtitle_translate_failure_not_reported_as_asr(monkeypatch):
    uid = 171013
    bot.clear_video_dubbing_pending(uid)
    ref = bot.set_video_dubbing_artifact(uid, "source_subtitle", "1\n00:00:00,000 --> 00:00:01,000\nXin chào\n")
    state = bot.set_video_dubbing_pending(
        uid,
        "language",
        mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        active_flow="subtitle_translate",
        subtitle_ref=ref,
        source_subtitle_ref=ref,
        translate_requested="1",
    )

    prepare_calls = {"count": 0}

    async def fail_prepare(*_args, **_kwargs):
        prepare_calls["count"] += 1
        raise AssertionError("translation must wait until final confirmation")

    monkeypatch.setattr(bot, "video_dubbing_prepare_subtitles", fail_prepare)
    message = CaptureMessage(uid)

    asyncio.run(bot.video_dubbing_translate_current_subtitle_to_output(message, SimpleNamespace(), uid, state, "English", "vi"))

    assert "Dịch phụ đề video" in message.outputs[-1]["text"]
    assert "chưa tạo được phụ đề" not in message.outputs[-1]["text"]
    assert "videodub|final" in _callbacks(message.outputs[-1]["reply_markup"])
    assert "videodub|download_original_srt" not in _callbacks(message.outputs[-1]["reply_markup"])
    assert prepare_calls["count"] == 0


def test_subtitle_translate_stores_translated_ref_and_exports_all(monkeypatch):
    uid = 171014
    bot.clear_video_dubbing_pending(uid)
    source = (
        "1\n00:00:00,000 --> 00:00:01,200\nXin chào\n\n"
        "2\n00:00:01,200 --> 00:00:02,500\nTOAN AAS\n"
    )
    source_ref = bot.set_video_dubbing_artifact(uid, "source_subtitle", source)
    state = bot.set_video_dubbing_pending(
        uid,
        "language",
        mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        active_flow="subtitle_translate",
        subtitle_ref=source_ref,
        source_subtitle_ref=source_ref,
        source_mime_type="text/plain",
        translate_requested="1",
        output_type="srt",
        output_format="srt",
    )

    translate_calls = {"count": 0}

    async def fake_translate(text, target, **_kwargs):
        translate_calls["count"] += 1
        raise AssertionError("translation must wait until final confirmation")

    monkeypatch.setattr(bot, "translate_subtitle_text", fake_translate)
    message = CaptureMessage(uid)

    final_state = asyncio.run(bot.video_dubbing_translate_current_subtitle_to_output(message, SimpleNamespace(), uid, state, "English", "vi"))
    callbacks = _callbacks(message.outputs[-1]["reply_markup"])

    assert final_state["step"] == "confirm"
    assert not final_state.get("translated_subtitle_ref")
    assert "Dịch phụ đề video" in message.outputs[-1]["text"]
    assert "videodub|final" in callbacks
    assert "videodub|output|srt" not in callbacks
    assert translate_calls["count"] == 0


def test_download_original_srt_callback_uses_source_subtitle_ref(monkeypatch):
    uid = 171015
    bot.clear_video_dubbing_pending(uid)
    ref = bot.set_video_dubbing_artifact(uid, "source_subtitle", "1\n00:00:00,000 --> 00:00:01,000\nXin chào\n")
    bot.set_video_dubbing_pending(
        uid,
        "language",
        mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        active_flow="subtitle_translate",
        source_subtitle_ref=ref,
        translate_requested="1",
    )
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    message = CaptureMessage(uid)

    async def answer(*_args, **_kwargs):
        return None

    query = SimpleNamespace(
        data="videodub|download_original_srt",
        from_user=SimpleNamespace(id=uid),
        message=message,
        answer=answer,
    )

    asyncio.run(bot.handle_video_dubbing_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert message.outputs[-1]["filename"].endswith(".srt")
    assert b"Xin ch\xc3\xa0o" in message.outputs[-1]["document"]
