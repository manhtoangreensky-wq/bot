import inspect
from pathlib import Path

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def test_translation_gateway_two_buttons():
    text = bot.translation_menu_text("vi")
    markup = bot.translation_menu_keyboard("vi")
    labels = _labels(markup)
    assert "Trung tâm dịch" in text
    assert markup.inline_keyboard[0][0].text == "🌐 Dịch ngôn ngữ"
    assert markup.inline_keyboard[0][1].text == "🎬 Dịch phụ đề, lồng tiếng"
    assert "menu|translation_language_hub" in _callbacks(markup)
    assert "menu|translation_video_factory" in _callbacks(markup)


def test_language_translation_menu_preserves_existing_tools():
    labels = _labels(bot.translation_language_hub_keyboard("vi"))
    for label in ["🔁 Dịch 2 chiều", "💬 Hội thoại", "📝 Văn bản", "📄 Tài liệu", "🎧 Audio", "⚙️ Ngôn ngữ", "🌐 Dịch tự động"]:
        assert label in labels
    assert "⬅️ Trung tâm" in labels


def test_no_language_translation_tools_deleted():
    callbacks = set(_callbacks(bot.translation_language_hub_keyboard("vi")))
    assert {
        "menu|translation_two_way",
        "menu|translation_live_conversation",
        "menu|translation_text",
        "menu|translation_document",
        "menu|translation_voice",
        "menu|translation_language",
        "menu|translation_auto_target",
    }.issubset(callbacks)
    assert "menu|translation_stop_session" not in callbacks


def test_video_translation_menu_labels_auto():
    labels = _labels(bot.video_dubbing_menu_keyboard("vi", "translation"))
    assert labels[:6] == [
        "👁 Tạo phụ đề tự động",
        "🌐 Dịch phụ đề",
        "🎙 Lồng tiếng",
        "🎬 Phụ đề + lồng tiếng",
        "📂 Media",
        "📝 Chỉnh phụ đề",
    ]
    assert "🔗 Tải video từ link" not in labels
    assert "menu|translation_video_factory" not in _callbacks(bot.video_dubbing_menu_keyboard("vi", "translation"))


def test_subtitle_auto_no_translation_no_voice():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}
    labels = _labels(bot.video_dubbing_output_keyboard("vi", state))
    assert "👁 Xem thử" in labels
    assert "🗣 Lồng tiếng" not in labels
    assert not any("giọng" in label.lower() for label in labels)
    assert not bot.video_dubbing_requires_voice(bot.VIDEO_SUBTITLE_MODE_CREATE)


def test_subtitle_output_preview_dub_srt_burn():
    callbacks = _callbacks(bot.video_dubbing_output_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}))
    assert callbacks[:4] == [
        "videodub|confirm_subtitle_create",
        "videodub|final",
        "videodub|output_back",
        "menu|main",
    ]
    assert "videodub|output|srt" not in callbacks
    assert "videodub|output|burn" not in callbacks
    assert "videodub|continue_dubbing" not in callbacks


def test_dubbing_requires_voice_only_in_dubbing():
    assert not bot.video_dubbing_requires_voice(bot.VIDEO_SUBTITLE_MODE_CREATE)
    assert not bot.video_dubbing_requires_voice(bot.VIDEO_SUBTITLE_MODE_TRANSLATE)
    assert bot.video_dubbing_requires_voice(bot.VIDEO_SUBTITLE_MODE_DUB)
    labels = _labels(bot.video_dubbing_voice_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_DUB}))
    for label in ["👩 Giọng nữ mặc định", "👨 Giọng nam mặc định", "📂 Kho voice", "🎙 Tạo voice riêng"]:
        assert label in labels


def test_subtitle_plus_dubbing_export_before_voice(monkeypatch):
    monkeypatch.setattr(bot, "video_dubbing_capability", lambda *_args, **_kwargs: {"ok": True})
    uid = "task2-plus-export"
    bot.clear_video_dubbing_pending(uid)
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "video_file_id": "video-file",
        "source_file_id": "video-file",
    }
    state, text, markup = bot.video_dubbing_next_screen_after_source(uid, state, "vi")
    labels = _labels(markup)
    assert state["step"] == "language"
    assert "Dịch phụ đề sang ngôn ngữ nào" in text
    state = bot.set_video_dubbing_pending(uid, "language", target_language="Tiếng Việt")
    state, text, markup = bot.video_dubbing_next_screen_after_source(uid, state, "vi")
    labels = _labels(markup)
    assert state["step"] == "output"
    assert "Video đã sẵn sàng tạo phụ đề dịch" in text
    assert "✅ Xác nhận tạo đầy đủ" in labels
    assert "📄 Xuất SRT" not in labels
    assert "🗣 Tiếp tục lồng tiếng" not in labels
    assert not any("Giọng" in label for label in labels)


def test_link_import_moved_to_video_studio():
    assert "🔗 Tải video từ link" not in _labels(bot.video_dubbing_menu_keyboard("vi", "translation"))
    assert "videodub|link_start" not in _callbacks(bot.video_dubbing_menu_keyboard("vi", "translation"))
    assert "📥 Tải video từ link" in _labels(bot.main_video_keyboard("vi"))
    assert "vdownload|start" in _callbacks(bot.main_video_keyboard("vi"))
    for mode in [
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    ]:
        source = bot.video_dubbing_source_keyboard("vi", {"mode": mode})
        assert not any("link" in label.lower() for label in _labels(source))
        assert "videodub|link_start" not in _callbacks(source)


def test_no_copied_source_menu_inside_product_flows():
    for mode in [
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    ]:
        labels = _labels(bot.video_dubbing_source_keyboard("vi", {"mode": mode}))
        assert labels[:2] == ["📎 Gửi video/audio", "📂 Chọn từ Media"]
        assert "🔗 Tải link" not in labels


def test_auto_subtitle_input_and_output_are_basic_product():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}
    assert "Tạo phụ đề tự động" in bot.video_dubbing_source_text(state, "vi")
    assert "không dịch và không hỏi voice" in bot.video_dubbing_upload_text(state, "vi")
    labels = _labels(bot.video_dubbing_output_keyboard("vi", state))
    assert "🗣 Lồng tiếng" not in labels
    assert "🗣 Tiếp tục lồng tiếng" not in labels
    assert "👁 Xem thử" in labels
    assert "✅ Xác nhận tạo đầy đủ" in labels
    assert "📄 Xuất SRT" not in labels


def test_auto_dubbing_language_voice_speed_numeric():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_DUB}
    assert "Chọn ngôn ngữ lồng tiếng" in bot.video_dubbing_language_text(state, "vi")
    assert "🇰🇷 한국어" in _labels(bot.video_dubbing_language_keyboard("vi", state))
    assert "Nhập tốc độ mong muốn" in bot.video_dubbing_voice_speed_text(state, "vi")
    labels = _labels(bot.video_dubbing_voice_speed_keyboard("vi"))
    assert labels == ["1.0 mặc định", "⬅️ Quay lại", "🏠 Menu chính"]
    assert bot.parse_video_dubbing_voice_speed("0.9") == "0.9"
    assert bot.parse_video_dubbing_voice_speed("1") == "1.0"
    assert bot.parse_video_dubbing_voice_speed("1.0") == "1.0"
    assert bot.parse_video_dubbing_voice_speed("1.5") == "1.5"


def test_subtitle_dubbing_continue_voice_after_output():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "requested_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "target_language": "Tiếng Việt",
        "translated_subtitle_ref": "video_dubbing_artifact:test:translated",
    }
    labels = _labels(bot.video_dubbing_output_keyboard("vi", state))
    assert "🗣 Tiếp tục lồng tiếng" in labels
    assert not any("Giọng nữ" in label for label in labels)


def test_link_import_10_xu_success_only_if_existing(monkeypatch):
    calls = []
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: calls.append((args, kwargs)) or {"ok": True, "final_cost": 10})
    uid = "task2-link-success"
    bot.set_video_dubbing_pending(uid, "link_processing", link_import_job_id="200")
    bot.handle_social_link_import_worker_job_update(
        {"id": "200", "job_type": "social_link_import", "status": "running"},
        {
            "id": "200",
            "job_type": "social_link_import",
            "status": "succeeded",
            "user_id": uid,
            "output_file_id": "tg-video",
            "input_file_id": '{"user_id":"task2-link-success","source_url":"https://youtu.be/x","source_platform":"YouTube"}',
        },
    )
    state = bot.get_video_dubbing_pending(uid)
    assert calls and calls[0][0][1] == 10
    assert state["step"] == "link_ready"
    assert state["link_import_status"] == "succeeded"
    assert "📂 Lưu Media" in _labels(bot.social_link_import_ready_keyboard("vi"))

    calls.clear()
    fail_uid = "task2-link-fail"
    bot.set_video_dubbing_pending(fail_uid, "link_processing", link_import_job_id="201")
    bot.handle_social_link_import_worker_job_update(
        {"id": "201", "job_type": "social_link_import", "status": "running"},
        {"id": "201", "job_type": "social_link_import", "status": "failed", "user_id": fail_uid, "input_file_id": '{"user_id":"task2-link-fail"}'},
    )
    assert calls == []
    assert bot.get_video_dubbing_pending(fail_uid)["link_import_status"] == "failed"


def test_back_translation_center_exact():
    assert "menu|main" in _callbacks(bot.translation_menu_keyboard("vi"))
    language_callbacks = _callbacks(bot.translation_language_hub_keyboard("vi"))
    video_callbacks = _callbacks(bot.video_dubbing_menu_keyboard("vi", "translation"))
    assert "menu|translate" in language_callbacks
    assert "menu|translate" in video_callbacks
    assert "videodub|back_type" in _callbacks(bot.video_dubbing_source_keyboard("vi", {}))
    assert "videodub|output_back" in _callbacks(bot.video_dubbing_output_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}))


def test_key4u_asr_adapter_or_guard():
    assert bot.KEY4U_STT_ENDPOINT == "/audio/transcriptions"
    assert bot.KEY4U_STT_MODEL == "whisper-1"
    assert hasattr(bot.key4u_provider_instance(), "stt")
    assert "bảo trì/nâng cấp" not in bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_CREATE, {}, "vi")


def test_key4u_translation_adapter_or_guard():
    assert bot.KEY4U_TRANSLATION_MODEL == "qwen-mt-turbo"
    assert hasattr(bot.key4u_provider_instance(), "translate")
    source = inspect.getsource(bot.translate_subtitle_text)
    assert "KEY4U_TRANSLATION_MODEL" in source
    assert "qwen-mt-turbo" in source or bot.KEY4U_TRANSLATION_MODEL == "qwen-mt-turbo"


def test_key4u_minimax_tts_for_dubbing_or_guard():
    source = inspect.getsource(bot.video_dubbing_tts_bytes)
    assert "key4u_minimax_tts_public_ready" in source
    assert "key4u_minimax_tts_bytes" in source
    guard = bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_DUB, {}, "vi")
    assert "bảo trì/nâng cấp" not in guard


def test_shopaikey_base_url_no_double_v1():
    assert bot.join_shopaikey_url("https://api.shopaikey.com/v1", "/audio/speech") == "https://api.shopaikey.com/v1/audio/speech"
    assert bot.join_shopaikey_url("https://api.shopaikey.com/v1", "/v1/audio/speech") == "https://api.shopaikey.com/v1/audio/speech"


def test_shopaikey_tts_fallback_guarded(monkeypatch):
    monkeypatch.setattr(bot, "SHOPAIKEY_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_TTS_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "test-key")
    monkeypatch.setattr(bot, "SHOPAIKEY_TTS_ENDPOINT", "/audio/speech")
    monkeypatch.setattr(bot, "shopaikey_tts_public_smoke_ready", lambda: False)
    assert bot.shopaikey_tts_fallback_public_ready() is False


def test_shopaikey_stt_probe_not_hardcoded():
    source = inspect.getsource(bot.asr_transcribe_audio)
    assert "shopaikey_stt_public_ready" in source
    assert "allow_admin" in source
    assert bot.SHOPAIKEY_AUDIO_TRANSCRIPTION_ENDPOINT == "/audio/transcriptions"


def test_translation_provider_status_admin_only():
    source = inspect.getsource(bot.cmd_translation_provider_status)
    assert "is_translation_admin" in source
    app_source = Path(bot.__file__).resolve().read_text(encoding="utf-8")
    assert 'CommandHandler("translation_provider_status", cmd_translation_provider_status)' in app_source
    assert 'CommandHandler("translation_provider_curl", cmd_translation_provider_curl)' in app_source
    assert 'CommandHandler("tool_test_translation_factory", cmd_tool_test_translation_factory)' in app_source
    status = bot.translation_provider_status_text()
    for marker in ["Key4U ASR", "Key4U translation", "Key4U MiniMax TTS", "ShopAIKey base", "ShopAIKey TTS", "ShopAIKey STT", "ffmpeg/local worker", "Last call status", "Last blocker"]:
        assert marker in status
    curls = "\n".join(bot.translation_provider_curl_appendix_chunks())
    for marker in [
        "https://api.key4u.shop/v1/audio/transcriptions",
        "qwen-mt-turbo",
        "https://api.key4u.shop/minimax/v1/t2a_v2",
        "$SHOPAIKEY_BASE_URL/audio/speech",
        "$SHOPAIKEY_BASE_URL/audio/transcriptions",
        "$SHOPAIKEY_BASE_URL/chat/completions",
    ]:
        assert marker in curls


def test_public_translation_guard_no_provider_terms():
    public_text = "\n".join([
        bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_CREATE, {}, "vi"),
        bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_TRANSLATE, {}, "vi"),
        bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_DUB, {}, "vi"),
        bot.translation_menu_text("vi"),
        "\n".join(_labels(bot.video_dubbing_menu_keyboard("vi", "translation"))),
    ]).lower()
    for term in ("key4u", "shopaikey", "api", "provider", "minimax", "env", "traceback", "smoke"):
        assert term not in public_text
