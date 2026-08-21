import asyncio
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class CaptureMessage:
    def __init__(self):
        self.chat_id = 919300
        self.message_id = 7
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(**item)

    async def reply_audio(self, **kwargs):
        item = {"audio": True, **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(message_id=919401, audio=SimpleNamespace(file_id="audio-file"))

    async def reply_document(self, **kwargs):
        item = {"document": True, **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(message_id=919402, document=SimpleNamespace(file_id="doc-file"))


class CaptureQuery:
    def __init__(self, user_id, data):
        self.from_user = SimpleNamespace(id=user_id)
        self.data = data
        self.message = CaptureMessage()
        self.outputs = self.message.outputs

    async def answer(self, *args, **kwargs):
        return None

    async def edit_message_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(**item)


def _update_with_message(user_id, message):
    return SimpleNamespace(effective_user=SimpleNamespace(id=user_id), message=message)


def _update_with_query(query):
    return SimpleNamespace(callback_query=query)


def test_product_menu_and_copy_are_clean_two_path():
    labels = _labels(bot.video_dubbing_menu_keyboard("vi", "translation"))
    assert "🎙 Lồng tiếng video" in labels
    assert "🎞 Phụ đề + Lồng tiếng" in labels
    assert "📄 Dịch file" in labels
    assert "🎧 Dịch audio" in labels
    assert "📄 Dịch file phụ đề" not in labels
    assert "🧾 Bóc lời thoại" not in labels
    assert "Voice video" not in "\n".join(labels)

    surfaces = "\n".join(
        [
            bot.video_dubbing_source_text({"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE}, "vi"),
            bot.video_dubbing_source_text({"mode": bot.VIDEO_SUBTITLE_MODE_DUB}, "vi"),
            bot.video_dubbing_source_text({"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}, "vi"),
            bot.video_dubbing_upload_text({"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "flow_type": bot.VIDEO_DUBBING_FLOW_HAS_SUBTITLE}, "vi"),
            bot.video_dubbing_original_subtitle_confirm_text({"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE}, "vi"),
            bot.video_dubbing_custom_voice_admin_test_text("vi"),
        ]
    )
    for forbidden in [
        "ADMIN TEST MODE",
        "Voice video",
        "provider",
        "API",
        "FFmpeg",
        "ASR",
        "TTS",
        "mux",
        "blackbox",
        "worker",
        "fake",
        "smoke",
        "command handler",
        "debug",
        "traceback",
        "public_ready",
        "ready=false",
        "timestamp",
    ]:
        assert forbidden not in surfaces


def test_translate_and_dub_source_keyboards_are_clean_closed_video_flows():
    translate = bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE})
    dub = bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_DUB})
    combo = bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB})

    assert _labels(translate)[:3] == ["📤 Gửi video đã có phụ đề", "⬅️ Phụ đề / Lồng tiếng", "🏠 Menu chính"]
    assert _callbacks(translate)[:3] == ["videodub|source_upload", "videodub|back_type", "menu|main"]
    assert _labels(dub)[:1] == ["📤 Gửi video cần lồng tiếng"]
    assert _callbacks(dub)[:1] == ["videodub|source_upload"]
    assert _callbacks(combo).count("videodub|source_upload") == 1
    assert not any(callback.startswith("videodub|path|") for callback in _callbacks(combo))


def test_upload_video_waits_for_original_subtitle_confirm(monkeypatch):
    uid = 919301
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "await_video",
        mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        process_type=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        origin="translation",
        flow_type=bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE,
    )
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "video_dubbing_subtitle_document_info", lambda _message: None)
    monkeypatch.setattr(bot, "video_reference_media_info", lambda _message: {"file_id": "tg-video", "file_name": "clip.mp4", "mime_type": "video/mp4", "file_type": "video"})
    monkeypatch.setattr(bot, "cache_recent_media_state", lambda _update: None)
    monkeypatch.setattr(bot, "remember_last_media", lambda _update: None)
    monkeypatch.setattr(
        bot,
        "video_dubbing_source_fields_from_upload",
        lambda _info, subtitle_file=False: {
            "source_file_id": "tg-video",
            "video_file_id": "tg-video",
            "source_file_name": "clip.mp4",
            "source_mime_type": "video/mp4",
            "media_kind": "video",
            "source_kind": "media",
        },
    )

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("original subtitle processing must wait for confirm")

    monkeypatch.setattr(bot, "video_dubbing_create_original_subtitle_for_next_step", forbidden)

    message = CaptureMessage()
    handled = asyncio.run(bot.handle_video_dubbing_pending_upload(_update_with_message(uid, message), SimpleNamespace()))
    state = bot.get_video_dubbing_pending(uid)
    assert handled is True
    assert state["step"] == "language"
    assert state["flow_type"] == bot.VIDEO_DUBBING_FLOW_HAS_SUBTITLE
    assert "Tạo phụ đề gốc trước" not in message.outputs[-1]["text"]


def test_upload_subtitle_file_skips_original_subtitle_step(monkeypatch):
    uid = 919302
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "await_subtitle_file",
        mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        process_type=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        origin="translation",
        flow_type=bot.VIDEO_DUBBING_FLOW_HAS_SUBTITLE,
    )
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "video_dubbing_subtitle_document_info", lambda _message: {"file_id": "tg-srt", "file_name": "captions.srt", "mime_type": "application/x-subrip", "file_type": "document"})
    monkeypatch.setattr(bot, "video_reference_media_info", lambda _message: None)
    monkeypatch.setattr(bot, "cache_recent_media_state", lambda _update: None)
    monkeypatch.setattr(bot, "remember_last_media", lambda _update: None)
    monkeypatch.setattr(
        bot,
        "video_dubbing_source_fields_from_upload",
        lambda _info, subtitle_file=False: {
            "source_file_id": "tg-srt",
            "source_file_name": "captions.srt",
            "source_mime_type": "application/x-subrip",
            "media_kind": "subtitle_file",
            "source_kind": "subtitle_file",
        },
    )

    message = CaptureMessage()
    handled = asyncio.run(bot.handle_video_dubbing_pending_upload(_update_with_message(uid, message), SimpleNamespace()))
    state = bot.get_video_dubbing_pending(uid)
    assert handled is True
    assert state["step"] == "await_subtitle_file"
    assert state["flow_type"] == bot.VIDEO_DUBBING_FLOW_HAS_SUBTITLE
    assert "chỉ xử lý video" in message.outputs[-1]["text"]


def test_confirm_original_subtitle_is_the_first_processing_call(monkeypatch):
    uid = 919303
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "original_subtitle_confirm",
        mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        process_type=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        source_file_id="tg-video",
        video_file_id="tg-video",
        source_file_name="clip.mp4",
        source_mime_type="video/mp4",
        media_kind="video",
    )
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    calls = {}

    async def fake_create(message, context, user_id, state, lang):
        calls["user_id"] = user_id
        calls["step"] = state.get("step")
        await message.reply_text("ok")
        return state

    monkeypatch.setattr(bot, "video_dubbing_create_original_subtitle_for_next_step", fake_create)
    query = CaptureQuery(uid, "videodub|confirm_original_subtitle")
    asyncio.run(bot.handle_video_dubbing_callback(_update_with_query(query), SimpleNamespace()))
    assert calls == {"user_id": uid, "step": "original_subtitle_confirm"}


def test_uploaded_translate_guard_does_not_fire_after_original_subtitle(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(bot, "video_dubbing_configured_readiness", lambda *_args, **_kwargs: {"missing": ["asr", "translation"]})
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "source_file_id": "tg-video",
        "video_file_id": "tg-video",
        "source_file_name": "clip.mp4",
        "source_mime_type": "video/mp4",
        "media_kind": "video",
        "subtitle_ref": "video_dubbing_artifact:test:source",
    }
    assert bot.video_dubbing_uploaded_translate_locked(919304, state) is False


def test_saved_voice_selection_uses_provider_voice_id(monkeypatch):
    uid = 919305
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "voice",
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        process_type=bot.VIDEO_SUBTITLE_MODE_DUB,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        source_file_id="tg-video",
        video_file_id="tg-video",
        target_language="Tiếng Việt",
    )
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "video_dubbing_custom_voice_public_locked", lambda _uid: False)
    monkeypatch.setattr(
        bot,
        "user_voice_profile_by_display_code",
        lambda _uid, code, page_size=5: {
            "id": 77,
            "display_name": "Giọng riêng đã lưu",
            "provider_voice_id": "provider-custom-77",
            "status": "active",
        },
    )

    query = CaptureQuery(uid, "videodub|voice_profile|1")
    asyncio.run(bot.handle_video_dubbing_callback(_update_with_query(query), SimpleNamespace()))
    state = bot.get_video_dubbing_pending(uid)
    assert state["voice_kind"] == "saved_voice"
    assert int(state["voice_profile_id"]) == 77
    assert state["voice_id"] == "provider-custom-77"
    assert state["step"] == "confirm"


def test_combo_translation_receipt_can_continue_to_dub():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "requested_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "final_video_available": "1",
        "final_subtitle_available": "1",
    }
    labels = _labels(bot.video_dubbing_receipt_keyboard("vi", "translation", state))
    assert "🎙 Lồng tiếng bản dịch" in labels


def test_partial_result_sends_audio_and_subtitle():
    message = CaptureMessage()
    srt = "1\n00:00:00,000 --> 00:00:01,000\nXin chào\n"
    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            active_flow=bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
            requested_mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            subtitle_items=[{"output_type": "srt", "bytes": srt.encode("utf-8"), "filename": "translated.srt"}],
            audio_bytes=b"audio-bytes",
            video_bytes=b"",
            lang="vi",
        )
    )
    assert sent["documents"] == 0
    assert sent["audio"] == 0
    assert sent["video"] == 0
    assert sent["partial_audio_available"] is True
    assert sent["partial_audio_delivered"] is False
    assert sent["audio_fallback_suppressed"] is True
    assert sent["audio_artifact_internal_only"] is True
    assert sent["success_blocked_reason"] == "missing_valid_delivered_mp4"
    assert not any(item.get("audio") for item in message.outputs)
    assert not any(item.get("document") for item in message.outputs)
