import asyncio
from types import SimpleNamespace

import bot


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class CaptureMessage:
    def __init__(self, file_id="task2-video"):
        self.video = SimpleNamespace(
            file_id=file_id,
            file_unique_id=f"{file_id}-unique",
            file_name=f"{file_id}.mp4",
            mime_type="video/mp4",
            duration=12,
            file_size=1024,
            width=720,
            height=1280,
        )
        self.audio = None
        self.voice = None
        self.document = None
        self.message_id = 23
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"text": str(text), **kwargs})
        return SimpleNamespace(text=text)


def _update(uid, message):
    return SimpleNamespace(effective_user=SimpleNamespace(id=uid), message=message)


def _prepare_upload(monkeypatch, uid, mode, step="source"):
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(uid, step, mode=mode, process_type=mode, video_processing_mode=mode, origin="translation")
    monkeypatch.setattr(bot, "cache_recent_media_state", lambda _update: "video")
    monkeypatch.setattr(bot, "remember_last_media", lambda _update: None)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")


def _patch_create_subtitle(monkeypatch):
    async def fake_prepare(_context, state, user_id, allow_admin=False):
        source = "1\n00:00:00,000 --> 00:00:02,000\nXin chào"
        subtitle_ref = bot.set_video_dubbing_artifact(user_id, "source_subtitle", source)
        saved = bot.set_video_dubbing_pending(user_id, state.get("step") or "creating_original_subtitle", subtitle_ref=subtitle_ref)
        return {
            "state": saved,
            "source_subtitle": source,
            "source_segments": [{"start": 0, "end": 2, "text": "Xin chào"}],
            "detected_language": "vi",
        }

    monkeypatch.setattr(bot, "video_dubbing_prepare_subtitles", fake_prepare)


def test_public_translation_guard_hides_admin_blocker():
    text = bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_DUB, {}, "vi", admin=False)
    assert "TOAN AAS chưa thể tạo giọng lồng tiếng" in text
    assert "chưa trừ Xu" in text
    assert "Admin blocker" not in text


def test_public_translation_guard_hides_factory_status_buttons():
    callbacks = _callbacks(bot.video_dubbing_guard_keyboard("vi", admin=False))
    assert callbacks == ["videodub|guard_back", "menu|main"]
    assert "videodub|admin_smoke" not in callbacks
    assert "videodub|admin_status" not in callbacks


def test_admin_translation_guard_shows_debug_buttons():
    callbacks = _callbacks(bot.video_dubbing_guard_keyboard("vi", admin=True))
    assert "videodub|admin_smoke" in callbacks
    assert "videodub|admin_status" in callbacks
    assert "videodub|admin_curl" in callbacks


def test_public_no_provider_terms_translation():
    texts = [
        bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_CREATE, {}, "vi", admin=False),
        bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_DUB, {}, "vi", admin=False),
        bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_TRANSLATE, {"requested_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}, "vi", admin=False),
        bot.translation_voice_guard_text(False),
    ]
    public_text = " ".join(texts).lower()
    for term in ("admin blocker", "provider", "api", "env", "smoke", "key4u", "shopaikey", "minimax"):
        assert term not in public_text


def test_translation_provider_curl_admin_only(monkeypatch):
    replies = []

    async def reply_text(text, **kwargs):
        replies.append(str(text))

    monkeypatch.setattr(bot, "is_translation_admin", lambda _uid: False)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=823001), message=SimpleNamespace(reply_text=reply_text))
    asyncio.run(bot.cmd_translation_provider_curl(update, SimpleNamespace()))
    assert replies == ["⛔ Lệnh này chỉ dành cho admin."]


def test_no_curl_button_public_translation_flow():
    for markup in (
        bot.video_dubbing_guard_keyboard("vi", admin=False),
        bot.video_dubbing_menu_keyboard("vi", "translation"),
        bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}),
    ):
        assert "videodub|admin_curl" not in _callbacks(markup)


def test_task2_upload_video_stays_in_auto_subtitle(monkeypatch):
    uid = 823010
    _prepare_upload(monkeypatch, uid, bot.VIDEO_SUBTITLE_MODE_CREATE)
    _patch_create_subtitle(monkeypatch)
    monkeypatch.setattr(bot, "video_dubbing_capability", lambda *_args, **_kwargs: {"ok": False})
    message = CaptureMessage("auto-subtitle")
    assert asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace())) is True
    state = bot.get_video_dubbing_pending(uid)
    assert state["product"] == "auto_subtitle"
    assert state["source_ref"] == "auto-subtitle"
    assert state["step"] == "output"
    assert "Phụ đề đã sẵn sàng xuất" in message.outputs[-1]["text"]


def test_task2_upload_video_stays_in_auto_dubbing(monkeypatch):
    uid = 823011
    _prepare_upload(monkeypatch, uid, bot.VIDEO_SUBTITLE_MODE_DUB)
    message = CaptureMessage("auto-dubbing")
    assert asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace())) is True
    state = bot.get_video_dubbing_pending(uid)
    assert state["product"] == "auto_dubbing"
    assert state["source_ref"] == "auto-dubbing"
    assert state["step"] == "language"
    assert "Chọn ngôn ngữ lồng tiếng" in message.outputs[-1]["text"]


def test_task2_upload_video_stays_in_subtitle_plus_dubbing(monkeypatch):
    uid = 823012
    _prepare_upload(monkeypatch, uid, bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB)
    monkeypatch.setattr(bot, "video_dubbing_configured_readiness", lambda *_args, **_kwargs: {"missing": []})
    monkeypatch.setattr(bot, "video_dubbing_asr_missing_for_state", lambda *_args, **_kwargs: False)

    async def fake_prepare(_context, state, user_id, allow_admin=False):
        source = "1\n00:00:00,000 --> 00:00:02,000\nXin chào"
        subtitle_ref = bot.set_video_dubbing_artifact(user_id, "source_subtitle", source)
        saved = bot.set_video_dubbing_pending(user_id, state.get("step") or "creating_original_subtitle", subtitle_ref=subtitle_ref)
        return {
            "state": saved,
            "source_subtitle": source,
            "source_segments": [{"start": 0, "end": 2, "text": "Xin chào"}],
            "detected_language": "vi",
        }

    monkeypatch.setattr(bot, "video_dubbing_prepare_subtitles", fake_prepare)
    message = CaptureMessage("subtitle-dubbing")
    assert asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace())) is True
    state = bot.get_video_dubbing_pending(uid)
    assert state["product"] == "subtitle_plus_dubbing"
    assert state["requested_mode"] == bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB
    assert state["source_ref"] == "subtitle-dubbing"
    assert state["step"] == "original_subtitle_ready"
    assert "Đã tạo phụ đề gốc" in message.outputs[-1]["text"]


def test_task2_upload_video_does_not_open_generic_video_menu(monkeypatch):
    uid = 823013
    _prepare_upload(monkeypatch, uid, bot.VIDEO_SUBTITLE_MODE_CREATE, step="await_video")
    _patch_create_subtitle(monkeypatch)
    monkeypatch.setattr(bot, "video_dubbing_capability", lambda *_args, **_kwargs: {"ok": False})

    async def must_not_run(*_args, **_kwargs):
        raise AssertionError("Task 2 upload must beat stale/global media handlers")

    monkeypatch.setattr(bot, "handle_free_hub_pending_upload", must_not_run)
    monkeypatch.setattr(bot, "handle_translation_session_media", must_not_run)
    message = CaptureMessage("routing-lock")
    asyncio.run(bot.handle_media_cache_only(_update(uid, message), SimpleNamespace()))
    joined = " ".join(item["text"] for item in message.outputs)
    assert "Bạn muốn xử lý video này theo hướng nào" not in joined
    assert "Phụ đề đã sẵn sàng xuất" in joined


def test_auto_subtitle_preview_back_to_output():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE, "step": "preview_guarded", "source_file_id": "file-1"}
    assert bot.video_dubbing_back_route(state, "preview_back") == "output"


def test_auto_dubbing_preview_back_to_invoice():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "step": "preview_guarded", "source_file_id": "file-2"}
    assert bot.video_dubbing_back_route(state, "preview_back") == "confirm"


def test_subtitle_plus_preview_back_to_output():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "requested_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "step": "preview_guarded"}
    assert bot.video_dubbing_back_route(state, "preview_back") == "output"


def test_task2_no_reupload_after_back():
    uid = 823020
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(uid, "guarded", mode=bot.VIDEO_SUBTITLE_MODE_DUB, source_file_id="kept-file")
    for step in ("voice_speed", "voice", "language", "source"):
        state = bot.set_video_dubbing_pending(uid, step)
        assert state["source_file_id"] == "kept-file"
        assert state["source_ref"] == "kept-file"


def test_two_way_text_translation_not_blocked_by_tts_off(monkeypatch):
    message = SimpleNamespace(outputs=[])

    async def reply_text(text, **kwargs):
        message.outputs.append(str(text))

    message.reply_text = reply_text
    monkeypatch.setattr(bot, "video_tts_provider_available", lambda: False)
    session = {"mode": "two_way", "lang_a": "vi", "lang_b": "en", "output_mode": "voice"}
    update = SimpleNamespace(effective_user=SimpleNamespace(id=823030), message=message)
    asyncio.run(bot.send_translation_session_result(update, SimpleNamespace(), session, "Xin chào", "Hello", "vi", "en"))
    assert "Hello" in message.outputs[-1]


def test_two_way_voice_public_guard_clean():
    text = bot.translation_voice_guard_text(False)
    assert text == "Dịch voice đang chờ tài nguyên xử lý. TOAN AAS chưa xử lý và chưa trừ Xu."
    assert "Admin blocker" not in text


def test_conversation_public_guard_clean():
    text = bot.translation_voice_guard_text(False)
    for term in ("provider", "api", "smoke", "key4u", "shopaikey"):
        assert term not in text.lower()
