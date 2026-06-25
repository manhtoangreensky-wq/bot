import asyncio
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _joined_ui(text, markup):
    return (str(text or "") + "\n" + "\n".join(_labels(markup)) + "\n" + "\n".join(_callbacks(markup))).lower()


class CaptureMessage:
    def __init__(self, file_id="task24-video"):
        self.video = SimpleNamespace(
            file_id=file_id,
            file_unique_id=f"{file_id}-unique",
            file_name=f"{file_id}.mp4",
            mime_type="video/mp4",
            duration=39,
            file_size=2048,
            width=720,
            height=1280,
        )
        self.audio = None
        self.voice = None
        self.document = None
        self.message_id = 24
        self.chat_id = 2400
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"text": str(text), **kwargs})
        return SimpleNamespace(text=text)


class DummyQuery:
    def __init__(self, uid, data):
        self.from_user = SimpleNamespace(id=uid)
        self.data = data
        self.message = SimpleNamespace(chat_id=uid, outputs=[])
        self.edits = []
        self.answers = []

        async def reply_text(text, **kwargs):
            self.message.outputs.append({"text": str(text), **kwargs})
            return SimpleNamespace(text=text)

        self.message.reply_text = reply_text

    async def answer(self, text=None, **kwargs):
        self.answers.append({"text": text, **kwargs})

    async def edit_message_text(self, text, **kwargs):
        self.edits.append({"text": str(text), **kwargs})
        return SimpleNamespace(text=text)


def _update(uid, message):
    return SimpleNamespace(effective_user=SimpleNamespace(id=uid), message=message)


def _callback_update(query):
    return SimpleNamespace(callback_query=query, effective_user=query.from_user)


def _prepare_upload(monkeypatch, uid, mode, step="source", **fields):
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        step,
        mode=mode,
        process_type=mode,
        video_processing_mode=mode,
        origin="translation",
        **fields,
    )
    monkeypatch.setattr(bot, "cache_recent_media_state", lambda _update: "video")
    monkeypatch.setattr(bot, "remember_last_media", lambda _update: None)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(
        bot,
        "video_dubbing_configured_readiness",
        lambda *_args, **_kwargs: {"ok": True, "reason": "ready", "missing": []},
    )


def test_auto_subtitle_after_upload_shows_product_confirmation(monkeypatch):
    uid = 824001
    _prepare_upload(monkeypatch, uid, bot.VIDEO_SUBTITLE_MODE_CREATE)
    monkeypatch.setattr(bot, "video_dubbing_capability", lambda *_args, **_kwargs: {"ok": False})
    message = CaptureMessage("subtitle-product")

    assert asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace())) is True

    state = bot.get_video_dubbing_pending(uid)
    assert state["step"] == "output"
    text = message.outputs[-1]["text"]
    labels = _labels(message.outputs[-1]["reply_markup"])
    assert "Video đã sẵn sàng tạo phụ đề" in text
    assert "Tác vụ:" not in text
    assert "Nguồn:" not in text
    assert labels == [
        "👁 Xem thử",
        "✅ Xác nhận tạo đầy đủ",
        "⬅️ Quay lại",
        "🏠 Menu chính",
    ]


def test_auto_subtitle_public_no_admin_buttons():
    text = bot.video_dubbing_output_text({"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}, "vi")
    markup = bot.video_dubbing_output_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE})
    ui = _joined_ui(text, markup)
    for term in ("admin blocker", "kiểm tra factory", "trạng thái dịch", "curl provider", "key4u", "shopaikey", "provider", "api", "smoke"):
        assert term not in ui


def test_auto_subtitle_provider_off_clean_buttons(monkeypatch):
    uid = 824002
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(uid, "output", mode=bot.VIDEO_SUBTITLE_MODE_CREATE, source_file_id="file-subtitle")
    monkeypatch.setattr(bot, "video_dubbing_capability", lambda *_args, **_kwargs: {"ok": False})
    monkeypatch.setattr(bot, "is_translation_admin", lambda _uid: True)
    query = DummyQuery(uid, "videodub|confirm_subtitle_create")

    asyncio.run(bot.handle_video_dubbing_callback(_callback_update(query), SimpleNamespace()))

    text = query.edits[-1]["text"]
    markup = query.edits[-1]["reply_markup"]
    assert "Chưa cấu hình nhận diện giọng nói" in text
    assert "bảo trì/nâng cấp" not in text
    assert _callbacks(markup) == ["videodub|guard_back", "menu|main"]
    assert "Admin blocker" not in text


def test_auto_subtitle_no_voice_or_dub_button():
    labels = _labels(bot.video_dubbing_output_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}))
    assert not any("giọng" in label.lower() or "lồng tiếng" in label.lower() for label in labels)


def test_auto_dubbing_confirmation_has_preview_and_full():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "source_file_id": "dub-file",
        "target_language": "English",
        "voice_style": "giọng nữ mặc định",
        "voice_speed": "0.9",
    }
    text = bot.video_dubbing_confirm_text(state, "vi")
    labels = _labels(bot.video_dubbing_confirm_keyboard("vi", state))
    assert "✅ <b>Video đã sẵn sàng lồng tiếng</b>" in text
    assert "Tác vụ:" not in text
    assert "Nguồn:" not in text
    assert "Chi phí dự kiến" not in text
    assert "Tốc độ: <b>0.9</b>" in text
    assert labels == ["▶️ Nghe thử", "✅ Xác nhận tạo đầy đủ", "⬅️ Quay lại", "🏠 Menu chính"]


def test_auto_dubbing_provider_off_no_debug_buttons(monkeypatch):
    uid = 824003
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "confirm",
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        source_file_id="dub-file",
        target_language="English",
        voice_style="giọng nữ mặc định",
        voice_speed="1.0",
    )
    monkeypatch.setattr(
        bot,
        "video_dubbing_configured_readiness",
        lambda *_args, **_kwargs: {"ok": False, "reason": "missing_tts", "missing": ["tts"]},
    )
    monkeypatch.setattr(bot, "is_translation_admin", lambda _uid: True)
    query = DummyQuery(uid, "videodub|confirm_dub")

    asyncio.run(bot.handle_video_dubbing_callback(_callback_update(query), SimpleNamespace()))

    ui = _joined_ui(query.edits[-1]["text"], query.edits[-1]["reply_markup"])
    assert "chưa cấu hình giọng đọc để lồng tiếng" in ui
    assert "bảo trì/nâng cấp" not in ui
    for term in ("admin blocker", "kiểm tra factory", "trạng thái dịch", "curl provider", "provider", "api", "key4u", "shopaikey"):
        assert term not in ui


def test_auto_dubbing_no_reupload_after_guard_back(monkeypatch):
    uid = 824004
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "confirm",
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        source_file_id="kept-dub-file",
        target_language="English",
        voice_style="giọng nam mặc định",
        voice_speed="1.0",
    )
    monkeypatch.setattr(bot, "video_dubbing_capability", lambda *_args, **_kwargs: {"ok": False})
    asyncio.run(bot.handle_video_dubbing_callback(_callback_update(DummyQuery(uid, "videodub|confirm_dub")), SimpleNamespace()))

    query = DummyQuery(uid, "videodub|guard_back")
    asyncio.run(bot.handle_video_dubbing_callback(_callback_update(query), SimpleNamespace()))

    state = bot.get_video_dubbing_pending(uid)
    assert state["source_file_id"] == "kept-dub-file"
    assert state["step"] == "confirm"
    assert "Video đã sẵn sàng lồng tiếng" in query.edits[-1]["text"]


def test_subtitle_plus_confirmation_has_preview_and_full_subtitle():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "requested_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "source_file_id": "combo-file",
        "target_language": "Tiếng Việt",
    }
    text = bot.video_dubbing_output_text(state, "vi")
    labels = _labels(bot.video_dubbing_output_keyboard("vi", state))
    assert "Video đã sẵn sàng tạo phụ đề dịch" in text
    assert "TOAN AAS sẽ tạo phụ đề dịch trước" in text
    assert labels == ["👁 Xem thử", "✅ Xác nhận tạo đầy đủ", "⬅️ Quay lại", "🏠 Menu chính"]
    assert "📄 Xuất SRT" not in labels
    assert "🎞 Gắn phụ đề vào video" not in labels


def test_subtitle_plus_provider_off_no_debug_buttons(monkeypatch):
    uid = 824005
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "output",
        mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        requested_mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        source_file_id="combo-file",
        target_language="Tiếng Việt",
    )
    monkeypatch.setattr(bot, "video_dubbing_capability", lambda *_args, **_kwargs: {"ok": False})
    monkeypatch.setattr(bot, "is_translation_admin", lambda _uid: True)
    query = DummyQuery(uid, "videodub|output|srt")

    asyncio.run(bot.handle_video_dubbing_callback(_callback_update(query), SimpleNamespace()))

    ui = _joined_ui(query.edits[-1]["text"], query.edits[-1]["reply_markup"])
    assert "chưa cấu hình bộ dịch phụ đề" in ui
    assert "bảo trì/nâng cấp" not in ui
    assert "admin blocker" not in ui
    assert "curl provider" not in ui


def test_subtitle_plus_continue_dubbing_only_after_subtitle_output():
    pending_state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "requested_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "target_language": "Tiếng Việt",
    }
    ready_state = {**pending_state, "translated_subtitle_ref": "video_dubbing_artifact:824:translated"}
    assert "🗣 Tiếp tục lồng tiếng" not in _labels(bot.video_dubbing_output_keyboard("vi", pending_state))
    assert "🗣 Tiếp tục lồng tiếng" in _labels(bot.video_dubbing_output_keyboard("vi", ready_state))


def test_subtitle_plus_dubbing_confirmation_has_preview_and_full():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "requested_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "source_file_id": "combo-file",
        "target_language": "Tiếng Việt",
        "voice_style": "giọng nữ mặc định",
        "voice_speed": "1.5",
    }
    text = bot.video_dubbing_confirm_text(state, "vi")
    labels = _labels(bot.video_dubbing_confirm_keyboard("vi", state))
    assert "Video đã sẵn sàng lồng tiếng" in text
    assert "Tác vụ:" not in text
    assert "Chi phí dự kiến" not in text
    assert labels == ["▶️ Nghe thử", "✅ Xác nhận tạo đầy đủ", "⬅️ Quay lại", "🏠 Menu chính"]


def test_link_import_top_level_usable_or_guarded():
    assert "🔗 Tải video từ link" not in _labels(bot.video_dubbing_menu_keyboard("vi", "translation"))
    assert "videodub|link_start" not in _callbacks(bot.video_dubbing_menu_keyboard("vi", "translation"))
    assert "📥 Tải video từ link" in _labels(bot.main_video_keyboard("vi"))
    assert "vdownload|start" in _callbacks(bot.main_video_keyboard("vi"))
    guard = bot.social_link_import_guard_text("vi")
    labels = _labels(bot.social_link_import_guard_keyboard("vi"))
    assert guard == "Tải video từ link đang bảo trì/nâng cấp, xin vui lòng thử lại sau. TOAN AAS chưa xử lý và chưa trừ Xu. Bạn có thể gửi video/audio trực tiếp."
    assert labels == ["📎 Gửi video/audio", "⬅️ Dịch video", "🏠 Menu chính"]


def test_link_import_provider_off_clean_guard(monkeypatch):
    uid = 824006
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(uid, "link_confirm", source_url="https://youtu.be/test", source_platform="YouTube", origin="translation")
    monkeypatch.setattr(bot, "get_user", lambda _uid: (999, None, None))
    monkeypatch.setattr(bot, "local_worker_status_payload", lambda: {"connected": False})
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no charge on link guard")))
    query = DummyQuery(uid, "videodub|link_confirm")

    asyncio.run(bot.handle_video_dubbing_callback(_callback_update(query), SimpleNamespace()))

    assert query.edits[-1]["text"] == bot.social_link_import_guard_text("vi")
    assert _callbacks(query.edits[-1]["reply_markup"]) == ["videodub|link_upload_direct", "videodub|back_type", "menu|main"]


def test_link_import_no_inner_flow_buttons():
    for mode in (bot.VIDEO_SUBTITLE_MODE_CREATE, bot.VIDEO_SUBTITLE_MODE_DUB, bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB):
        ui = _joined_ui(bot.video_dubbing_source_text({"mode": mode}, "vi"), bot.video_dubbing_source_keyboard("vi", {"mode": mode}))
        assert "tải video từ link" not in ui
        assert "videodub|link_start" not in ui


def test_link_import_no_charge_on_fail(monkeypatch):
    calls = []
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: calls.append((args, kwargs)))
    uid = "task24-link-fail"
    bot.set_video_dubbing_pending(uid, "link_processing", link_import_job_id="240")
    bot.handle_social_link_import_worker_job_update(
        {"id": "240", "job_type": "social_link_import", "status": "running"},
        {"id": "240", "job_type": "social_link_import", "status": "failed", "user_id": uid, "input_file_id": '{"user_id":"task24-link-fail"}'},
    )
    assert calls == []
    assert bot.get_video_dubbing_pending(uid)["link_import_status"] == "failed"


def test_public_product_flow_never_shows_admin_blocker():
    screens = [
        (bot.video_dubbing_output_text({"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}, "vi"), bot.video_dubbing_output_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE})),
        (bot.video_dubbing_confirm_text({"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "source_file_id": "x", "target_language": "English", "voice_style": "voice", "voice_speed": "1.0"}, "vi"), bot.video_dubbing_confirm_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_DUB})),
        (bot.social_link_import_guard_text("vi"), bot.social_link_import_guard_keyboard("vi")),
    ]
    for text, markup in screens:
        assert "admin blocker" not in _joined_ui(text, markup)


def test_public_product_flow_never_shows_curl_button():
    markups = [
        bot.video_dubbing_output_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}),
        bot.video_dubbing_confirm_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_DUB}),
        bot.video_dubbing_guard_keyboard("vi", admin=False),
        bot.social_link_import_guard_keyboard("vi"),
    ]
    for markup in markups:
        assert "videodub|admin_curl" not in _callbacks(markup)
        assert not any("curl" in label.lower() for label in _labels(markup))


def test_admin_commands_still_available():
    assert hasattr(bot, "cmd_translation_provider_status")
    assert hasattr(bot, "cmd_tool_test_translation_factory")
    assert hasattr(bot, "cmd_translation_provider_curl")


def test_task2_upload_does_not_open_generic_video_menu(monkeypatch):
    uid = 824007
    _prepare_upload(monkeypatch, uid, bot.VIDEO_SUBTITLE_MODE_CREATE, step="await_video")
    message = CaptureMessage("routing-product")
    asyncio.run(bot.handle_media_cache_only(_update(uid, message), SimpleNamespace()))
    joined = " ".join(item["text"] for item in message.outputs)
    assert "Bạn muốn xử lý video này theo hướng nào" not in joined
    assert "Video đã sẵn sàng tạo phụ đề" in joined


def test_task2_upload_preserves_session_source_ref(monkeypatch):
    uid = 824008
    _prepare_upload(monkeypatch, uid, bot.VIDEO_SUBTITLE_MODE_CREATE)
    message = CaptureMessage("preserve-source")
    asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace()))
    state = bot.get_video_dubbing_pending(uid)
    assert state["source_ref"] == "preserve-source"
    assert state["source_file_id"] == "preserve-source"


def test_task2_link_wait_upload_preserves_task2_session(monkeypatch):
    uid = 824009
    _prepare_upload(monkeypatch, uid, bot.VIDEO_SUBTITLE_MODE_CREATE, step="link_input")
    message = CaptureMessage("direct-link-fallback")
    asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace()))
    state = bot.get_video_dubbing_pending(uid)
    assert state["step"] == "link_ready"
    assert state["source_kind"] == "direct_upload"
    assert state["link_import_charged_xu"] == "0"
    assert "Đã có video nguồn" in message.outputs[-1]["text"]


def test_task2_job_progress_screen():
    text = bot.video_dubbing_job_progress_text("Tạo phụ đề tự động", 2468, "vi")
    labels = _labels(bot.video_dubbing_job_progress_keyboard(2468, "vi"))
    assert "TOAN AAS đang xử lý yêu cầu của bạn" in text
    assert "Mã job" not in text
    assert "Tác vụ:" not in text
    assert labels == ["🔄 Kiểm tra kết quả", "⬅️ Quay lại", "🏠 Menu chính"]


def test_task2_check_result_processing():
    assert bot.video_dubbing_job_status_text({"status": "running"}, "vi") == "⏳ Tác vụ vẫn đang xử lý. Bạn chờ thêm một chút rồi kiểm tra lại."


def test_task2_check_result_completed():
    text = bot.video_dubbing_job_status_text({"status": "succeeded"}, "vi")
    labels = _labels(bot.video_dubbing_job_result_keyboard("vi"))
    assert "Tác vụ đã hoàn tất" in text
    assert labels == ["📥 Tải file", "🔁 Làm video khác", "🏠 Menu chính"]


def test_task2_check_result_failed_no_charge():
    text = bot.video_dubbing_job_status_text({"status": "failed"}, "vi")
    assert "chưa trừ Xu" in text or "hoàn Xu" in text


def test_task2_guard_back_returns_product_confirmation():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE, "step": "preview_guarded", "source_file_id": "file"}
    assert bot.video_dubbing_back_route(state, "guard_back") == "output"


def test_task2_preview_back_returns_confirmation():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "step": "preview_ready", "source_file_id": "file"}
    assert bot.video_dubbing_back_route(state, "preview_back") == "confirm"


def test_task2_no_reupload_after_back():
    uid = 824010
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(uid, "preview_guarded", mode=bot.VIDEO_SUBTITLE_MODE_CREATE, source_file_id="kept-file")
    state = bot.set_video_dubbing_pending(uid, bot.video_dubbing_back_route(bot.get_video_dubbing_pending(uid), "guard_back"))
    assert state["step"] == "output"
    assert state["source_file_id"] == "kept-file"
