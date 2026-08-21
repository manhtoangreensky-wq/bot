import asyncio
import inspect
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _ui_text(*items):
    parts = []
    for item in items:
        if isinstance(item, str):
            parts.append(item)
        else:
            parts.extend(_labels(item))
    return "\n".join(parts)


class Media:
    def __init__(self, file_id="video-file", file_name="clip.mp4", mime_type="video/mp4", duration=30):
        self.file_id = file_id
        self.file_unique_id = file_id + "-unique"
        self.file_name = file_name
        self.mime_type = mime_type
        self.duration = duration
        self.file_size = 1024
        self.width = 1280
        self.height = 720


class CaptureMessage:
    def __init__(self, *, video=None, audio=None, document=None):
        self.chat_id = 919500
        self.message_id = 5
        self.video = video
        self.audio = audio
        self.document = document
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(**item)

    async def reply_audio(self, **kwargs):
        item = {"audio": True, **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(message_id=919601, audio=SimpleNamespace(file_id="audio-file"))

    async def reply_document(self, **kwargs):
        item = {"document": True, **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(message_id=919602, document=SimpleNamespace(file_id="doc-file"))

    async def reply_video(self, **kwargs):
        item = {"video": True, **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(message_id=919603, video=SimpleNamespace(file_id="video-file"))


class CaptureQuery:
    def __init__(self, uid, data):
        self.from_user = SimpleNamespace(id=uid)
        self.data = data
        self.message = CaptureMessage()
        self.outputs = self.message.outputs

    async def answer(self, *args, **kwargs):
        return None

    async def edit_message_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(**item)


def _update(uid, message):
    return SimpleNamespace(effective_user=SimpleNamespace(id=uid), message=message)


def _query_update(query):
    return SimpleNamespace(callback_query=query)


def _seed(uid, mode, step="await_video", **fields):
    bot.clear_video_dubbing_pending(uid)
    return bot.set_video_dubbing_pending(
        uid,
        step,
        mode=mode,
        process_type=mode,
        video_processing_mode=mode,
        requested_mode=mode,
        origin="translation",
        **fields,
    )


def _patch_upload_basics(monkeypatch):
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "cache_recent_media_state", lambda _update: None)
    monkeypatch.setattr(bot, "remember_last_media", lambda _update: None)


def test_translation_center_restores_file_audio_srt_flows():
    labels = _labels(bot.translation_menu_keyboard("vi"))
    callbacks = _callbacks(bot.translation_menu_keyboard("vi"))
    assert labels == ["🌐 Dịch ngôn ngữ", "🎬 Phụ đề / Lồng tiếng", "⬅️ Quay lại", "🏠 Menu chính"]
    assert "menu|translation_video_factory" in callbacks
    center_labels = _labels(bot.video_dubbing_menu_keyboard("vi", "translation"))
    center_callbacks = _callbacks(bot.video_dubbing_menu_keyboard("vi", "translation"))
    assert "📄 Dịch file" in center_labels
    assert "🎧 Dịch audio" in center_labels
    assert "menu|translation_media_file" in center_callbacks
    assert "menu|translation_media_audio" in center_callbacks


def test_video_translation_menu_has_exact_four_video_buttons():
    assert _labels(bot.video_dubbing_menu_keyboard("vi", "translation")) == [
        "🎬 Tạo phụ đề tự động",
        "🌐 Dịch phụ đề video",
        "🎙 Lồng tiếng video",
        "🎞 Phụ đề + Lồng tiếng",
        "📄 Dịch file",
        "🎧 Dịch audio",
        "⬅️ Trung tâm dịch",
        "🏠 Menu chính",
    ]


def test_video_menu_has_no_file_audio_srt_prompt():
    ui = _ui_text(bot.translation_menu_text("vi"), bot.translation_menu_keyboard("vi"))
    for forbidden in ("Dịch phụ đề / Video", "Dịch file", "Dịch audio", "SRT/VTT/TXT", "file phụ đề"):
        assert forbidden not in ui


def test_auto_subtitle_video_only_free():
    text = bot.video_dubbing_confirm_text({"mode": bot.VIDEO_SUBTITLE_MODE_CREATE, "source_file_id": "video"}, "vi")
    assert "Xác nhận tạo phụ đề gốc" in text
    assert "Miễn phí" in text


def test_auto_subtitle_does_not_translate_without_user_choice(monkeypatch):
    uid = 919501
    _patch_upload_basics(monkeypatch)
    _seed(uid, bot.VIDEO_SUBTITLE_MODE_CREATE)

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("auto subtitle upload must wait for confirm")

    monkeypatch.setattr(bot, "video_dubbing_create_original_subtitle_then_output", forbidden)
    message = CaptureMessage(video=Media())
    asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace()))
    state = bot.get_video_dubbing_pending(uid)
    assert state["step"] == "confirm"
    assert state["translate_requested"] == "0"
    assert "dịch" not in message.outputs[-1]["text"].lower()


def test_translate_subtitle_video_with_existing_subtitle_only(monkeypatch):
    uid = 919502
    _patch_upload_basics(monkeypatch)
    _seed(uid, bot.VIDEO_SUBTITLE_MODE_TRANSLATE, source_has_subtitle="1")
    message = CaptureMessage(video=Media())
    asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace()))
    state = bot.get_video_dubbing_pending(uid)
    assert state["step"] == "language"
    assert state["flow_type"] == bot.VIDEO_DUBBING_FLOW_HAS_SUBTITLE


def test_translate_subtitle_no_subtitle_guard_no_auto_asr(monkeypatch):
    uid = 919503
    _patch_upload_basics(monkeypatch)
    _seed(uid, bot.VIDEO_SUBTITLE_MODE_TRANSLATE, source_has_subtitle="0")

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("translate subtitle must not create subtitles automatically")

    monkeypatch.setattr(bot, "video_dubbing_create_original_subtitle_for_next_step", forbidden)
    message = CaptureMessage(video=Media())
    asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace()))
    assert "chưa tìm thấy phụ đề có sẵn" in message.outputs[-1]["text"]
    assert bot.get_video_dubbing_pending(uid)["step"] == "await_video"


def test_translate_subtitle_does_not_jump_to_auto_subtitle():
    labels = _labels(bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE}))
    callbacks = _callbacks(bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE}))
    assert "🎬 Tạo phụ đề tự động" not in labels
    assert f"videodub|type|{bot.VIDEO_SUBTITLE_MODE_CREATE}" not in callbacks


def test_translate_subtitle_price_summary_before_confirm():
    text = bot.video_dubbing_confirm_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "target_language": "English", "billing_chars": 1200},
        "vi",
    )
    assert "Xác nhận dịch phụ đề video" in text
    assert "Đơn giá: <b>0.1 Xu / ký tự</b>" in text
    assert "TOAN AAS chỉ xử lý và trừ Xu sau khi anh/chị xác nhận" in text


def test_dubbing_closed_flow_no_redundant_has_no_subtitle_first_screen():
    labels = _labels(bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_DUB}))
    ui = _ui_text(bot.video_dubbing_source_text({"mode": bot.VIDEO_SUBTITLE_MODE_DUB}, "vi"), bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_DUB}))
    assert labels[0] == "📤 Gửi video cần lồng tiếng"
    assert "Video đã có phụ đề" not in ui
    assert "Video chỉ có tiếng" not in ui


def test_dubbing_requires_voice_selection():
    state, text, markup = bot.video_dubbing_next_screen_after_source(
        919504,
        {"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "source_file_id": "video", "target_language": "English"},
        "vi",
    )
    assert state["step"] == "voice"
    assert "Chọn giọng lồng tiếng" in text
    assert "👩 Giọng nữ mặc định" in _labels(markup)


def test_dubbing_female_voice_not_male(monkeypatch):
    monkeypatch.setattr(bot, "get_tts_voice_id", lambda key: {"default_female": "female-id", "default_male": "male-id"}[key])
    payload = bot.video_dubbing_voice_payload("default_female", None, "vi")
    assert payload["voice_kind"] == "default_female"
    assert payload["voice_id"] == "female-id"


def test_dubbing_custom_voice_uses_provider_voice_id():
    payload = bot.video_dubbing_voice_payload("", {"id": 9, "display_name": "Giọng riêng", "provider_voice_id": "provider-voice-9"}, "vi")
    assert payload["voice_kind"] == "saved_voice"
    assert payload["voice_id"] == "provider-voice-9"


def test_dubbing_final_mp4_required_for_full_success():
    message = CaptureMessage()
    sent = asyncio.run(bot.send_public_subtitle_dub_final_outputs(message, mode=bot.VIDEO_SUBTITLE_MODE_DUB, audio_bytes=b"audio", video_bytes=b"video", lang="vi"))
    assert sent["video"] == 1
    assert sent["audio"] == 0


def test_dubbing_partial_copy_not_success():
    message = CaptureMessage()
    sent = asyncio.run(bot.send_public_subtitle_dub_final_outputs(message, mode=bot.VIDEO_SUBTITLE_MODE_DUB, audio_bytes=b"audio", video_bytes=b"", lang="vi"))
    assert sent["audio"] == 1
    assert sent["video"] == 0
    assert "chưa ghép được thành video hoàn chỉnh" in message.outputs[-1]["caption"]
    assert not message.outputs[-1]["caption"].startswith("✅")


def test_combo_single_upload_lane():
    markup = bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB})
    callbacks = _callbacks(markup)
    ui = _ui_text(
        bot.video_dubbing_source_text({"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}, "vi"),
        markup,
    )
    assert callbacks.count("videodub|source_upload") == 1
    assert not any(callback.startswith("videodub|path|") for callback in callbacks)
    assert f"videodub|path|{bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE}" not in callbacks
    assert "chưa có phụ đề" not in ui


def test_combo_internal_transcript_after_confirm_only(monkeypatch):
    uid = 919505
    _patch_upload_basics(monkeypatch)
    _seed(uid, bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, active_flow=bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB)

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("combo must not create transcript before final confirm")

    monkeypatch.setattr(bot, "video_dubbing_create_original_subtitle_for_next_step", forbidden)
    monkeypatch.setattr(bot, "video_dubbing_create_original_subtitle_then_output", forbidden)
    message = CaptureMessage(video=Media())
    asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace()))
    state = bot.get_video_dubbing_pending(uid)
    assert state["step"] == "language"
    assert state["step"] != "original_subtitle_confirm"
    assert state["active_flow"] == bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB
    assert "videodub|confirm_original_subtitle" not in _callbacks(message.outputs[-1]["reply_markup"])


def test_combo_price_summary_total_before_confirm():
    text = bot.video_dubbing_confirm_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "target_language": "English", "voice_style": "giọng nữ mặc định", "billing_chars": 2000},
        "vi",
    )
    assert "Xác nhận phụ đề + lồng tiếng" in text
    assert "Dịch phụ đề: <b>180 Xu</b>" in text
    assert "Lồng tiếng: <b>180 Xu</b>" in text
    assert "Tổng cộng: <b>360 Xu</b>" in text


def test_combo_no_provider_before_confirm(monkeypatch):
    uid = 919506
    _patch_upload_basics(monkeypatch)
    _seed(uid, bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, active_flow=bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB)
    called = {"charge": 0}
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *_args, **_kwargs: called.__setitem__("charge", called["charge"] + 1))
    message = CaptureMessage(video=Media())
    asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace()))
    assert called["charge"] == 0


def test_combo_final_mp4_required_for_full_success():
    message = CaptureMessage()
    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            subtitle_items=[{"output_type": "srt", "bytes": b"srt", "filename": "translated.srt"}],
            audio_bytes=b"audio",
            video_bytes=b"video",
            lang="vi",
        )
    )
    assert sent["video"] == 1


def test_no_adapter_missing_code_provider_api_asr_tts_mux_ffmpeg_in_product_ui():
    ui = _ui_text(
        bot.translation_menu_text("vi"),
        bot.translation_menu_keyboard("vi"),
        bot.video_dubbing_menu_text("vi", "translation"),
        bot.video_dubbing_source_text({"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE}, "vi"),
        bot.video_dubbing_source_text({"mode": bot.VIDEO_SUBTITLE_MODE_DUB}, "vi"),
        bot.video_dubbing_source_text({"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}, "vi"),
        bot.video_dubbing_confirm_text({"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "target_language": "English", "voice_style": "giọng nữ mặc định", "billing_chars": 1200}, "vi"),
        bot.video_dubbing_confirm_text({"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "target_language": "English", "voice_style": "giọng nữ mặc định", "billing_chars": 1200}, "vi"),
    )
    lowered = ui.lower()
    for forbidden in ("adapter_missing", "provider", "api", "asr", "tts", "mux", "ffmpeg", "traceback", "runtimeerror", "debug", "route", "payload", "fake", "sample", "redacted"):
        assert forbidden not in lowered
    assert "code" not in lowered


def test_product_failure_copy_clean_no_technical_words():
    texts = [
        bot.video_dubbing_flow_failure_text(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "vi"),
        bot.video_dubbing_asr_missing_guard_text("vi"),
        bot.subtitle_plus_dub_safe_fail_text("temporary_failure", "vi"),
    ]
    lowered = "\n".join(texts).lower()
    for forbidden in ("adapter_missing", "provider", "api", "asr", "tts", "mux", "ffmpeg", "traceback", "runtimeerror", "debug", "route", "payload", "fake", "sample", "redacted", "code"):
        assert forbidden not in lowered


def test_back_from_each_video_translation_subflow_returns_correct_parent():
    assert _callbacks(bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}))[-2] == "videodub|back_type"
    assert _callbacks(bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE}))[-2] == "videodub|back_type"
    assert _callbacks(bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_DUB}))[-2] == "videodub|back_type"
    assert _callbacks(bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}))[-2] == "videodub|back_type"


def test_file_audio_routes_do_not_jump_to_video():
    callbacks = _callbacks(bot.video_dubbing_menu_keyboard("vi", "translation"))
    assert "menu|translation_media_file" in callbacks
    assert "menu|translation_media_audio" in callbacks
    file_text, file_markup = bot.localized_menu_content("translation_media_file", False, "vi", user_id=919507)
    assert "Dịch file" in file_text
    assert "menu|translation_video_factory" in _callbacks(file_markup)


def test_video_addon_buttons_return_to_addon_menu(monkeypatch):
    uid = 919508
    bot.clear_video_addon_state(uid)
    monkeypatch.setattr(bot, "user_ui_lang", lambda _uid: "vi")
    state = bot.set_video_addon_state(uid, {
        "video_tier": "basic",
        "pending_payload": {"video_tier": "basic", "prompt": "video san pham", "duration_seconds": 18},
        "video_order": {"current_screen": "addon_voice", "screen_stack": ["video_tier_detail", "video_addon_menu", "addon_voice"]},
    })
    query = CaptureQuery(uid, "videoaddon|back")
    asyncio.run(bot.handle_video_addon_callback(_query_update(query), SimpleNamespace()))
    assert "Công cụ hoàn thiện video" in query.outputs[-1]["text"]
    assert "🎙 Giọng/lồng tiếng" in _labels(query.outputs[-1]["reply_markup"])
    assert bot.get_video_addon_state(uid)["pending_payload"]["prompt"] == state["pending_payload"]["prompt"]


def test_video_addon_preserves_draft_state():
    uid = 919509
    bot.clear_video_addon_state(uid)
    original = {
        "video_tier": "basic",
        "pending_payload": {
            "video_tier": "basic",
            "prompt": "video san pham",
            "duration_seconds": 18,
            "source_file_id": "source-video",
        },
        "current_video_subtitle_option": "subtitle_translated",
        "current_video_dubbing_option": "dub_translated",
        "current_video_music_option": "stock_music_library",
        "video_voice_volume_percent": "200",
    }
    saved = bot.set_video_addon_state(uid, original)
    assert saved["pending_payload"]["source_file_id"] == "source-video"
    assert saved["current_video_subtitle_option"] == "subtitle_translated"
    assert saved["current_video_dubbing_option"] == "dub_translated"
    assert saved["current_video_music_option"] == "stock_music_library"
    assert saved["video_voice_volume_percent"] == 200


def test_product_handler_has_no_provider_before_final_confirm():
    source = inspect.getsource(bot.handle_video_dubbing_callback)
    preconfirm = source.split("    confirm_modes = {", 1)[0]
    assert "execute_video_dubbing_pipeline" not in preconfirm
    assert "video_dubbing_transcribe_bytes" not in preconfirm
    assert "translate_subtitle_text" not in preconfirm
    assert "video_dubbing_tts_bytes" not in preconfirm
    assert "spend_fixed_credit_info" not in preconfirm
