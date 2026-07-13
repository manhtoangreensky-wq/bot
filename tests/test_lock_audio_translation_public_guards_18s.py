import inspect
from pathlib import Path

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _public_texts():
    return [
        bot.music_ai_public_guard_text("vi"),
        bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_CREATE, {}, "vi", admin=False),
        bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_TRANSLATE, {}, "vi", admin=False),
        bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_DUB, {}, "vi", admin=False),
        bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, {}, "vi", admin=False),
    ]


def test_music_ai_public_action_guarded_if_not_full_ready():
    assert not bot.music_ai_public_processing_ready({
        "ready": True,
        "public_enabled": True,
        "full_result_ok": False,
        "cost_gate_ok": True,
    })


def test_suno_pass_submitted_not_public_ready():
    readiness = {
        "ready": True,
        "public_enabled": True,
        "full_result_smoke": "PASS_SUBMITTED",
        "full_result_ok": False,
        "cost_gate_ok": True,
    }
    assert bot.music_ai_public_processing_ready(readiness) is False


def test_music_public_guard_no_admin_blocker():
    text = bot.music_ai_public_guard_text("vi")
    assert "Admin blocker" not in text
    assert text == "Dịch vụ đang được kiểm tra. TOAN AAS chưa xử lý và chưa trừ Xu. Vui lòng thử lại sau."


def test_music_public_guard_no_xu_charge():
    source = inspect.getsource(bot.handle_music_quick_callback)
    confirm = source[source.index('if action == "music_ai_confirm":'):source.index('if action == "music_ai_status":')]
    assert confirm.index("can_user_access_product_engine") < confirm.index("spend_fixed_credit_info")


def test_music_menu_still_visible():
    labels = _labels(bot.music_hub_keyboard("vi"))
    assert any("Tạo nhạc nền" in label for label in labels)
    assert any("Bài hát có lời" in label for label in labels)
    assert any("Kho nhạc" in label for label in labels)
    assert any("Cắt/ghép nhạc" in label for label in labels)


def test_video_subtitle_public_action_allows_real_srt_without_mux(monkeypatch):
    monkeypatch.setattr(bot, "video_dubbing_capability", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(bot, "is_asr_ready", lambda: True)
    monkeypatch.setattr(bot, "local_worker_status_payload", lambda: {"connected": False, "ffmpeg_path_configured": True})
    assert bot.video_dubbing_public_processing_ready(bot.VIDEO_SUBTITLE_MODE_CREATE)


def test_video_dub_public_action_allows_real_audio_without_mux(monkeypatch):
    monkeypatch.setattr(bot, "video_dubbing_capability", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(bot, "is_asr_ready", lambda: True)
    monkeypatch.setattr(bot, "is_dub_ready", lambda: True)
    monkeypatch.setattr(bot, "local_worker_status_payload", lambda: {"connected": False, "ffmpeg_path_configured": True})
    assert bot.video_dubbing_public_processing_ready(bot.VIDEO_SUBTITLE_MODE_DUB)


def test_subtitle_plus_dub_public_action_allows_partial_outputs_without_mux(monkeypatch):
    monkeypatch.setattr(bot, "video_dubbing_capability", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(bot, "is_asr_ready", lambda: True)
    monkeypatch.setattr(bot, "is_translate_ready", lambda: True)
    monkeypatch.setattr(bot, "is_dub_ready", lambda: True)
    monkeypatch.setattr(bot, "local_worker_status_payload", lambda: {"connected": False, "ffmpeg_path_configured": True})
    assert bot.video_dubbing_public_processing_ready(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB)


def test_translation_public_ready_does_not_require_mux_for_partial_outputs(monkeypatch):
    monkeypatch.setattr(bot, "video_dubbing_capability", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(bot, "is_asr_ready", lambda: True)
    monkeypatch.setattr(bot, "is_translate_ready", lambda: True)
    monkeypatch.setattr(bot, "is_dub_ready", lambda: True)
    monkeypatch.setattr(bot, "frame_video_worker_connected", lambda: True)
    monkeypatch.setattr(bot, "local_worker_status_payload", lambda: {
        "connected": True,
        "ffmpeg_path_configured": True,
        "ffmpeg_test_status": "PASS",
    })
    monkeypatch.setattr(bot, "is_subtitle_burn_ready", lambda: True)
    monkeypatch.setattr(bot, "is_voice_mux_ready", lambda: True)
    monkeypatch.setattr(bot, "preferred_tool_test_status_text", lambda *_args: "NOT_TESTED")
    assert bot.video_dubbing_public_processing_ready(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB)

    monkeypatch.setattr(bot, "preferred_tool_test_status_text", lambda *_args: "PASS")
    assert bot.video_dubbing_public_processing_ready(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB)

    monkeypatch.setattr(bot, "is_voice_mux_ready", lambda: False)
    assert bot.video_dubbing_public_processing_ready(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB)


def test_translation_public_guard_no_admin_blocker():
    for text in _public_texts()[1:]:
        assert "Admin blocker" not in text


def test_translation_public_guard_no_provider_text():
    joined = "\n".join(_public_texts()).lower()
    for term in ("provider", "api", "env", "key4u", "shopaikey", "curl", "smoke"):
        assert term not in joined


def test_translation_public_guard_no_xu_charge():
    source = inspect.getsource(bot.handle_video_dubbing_callback)
    assert source.index("video_dubbing_engine_access_decision") < source.index("execute_video_dubbing_pipeline")


def test_translation_menu_still_visible():
    labels = _labels(bot.video_dubbing_menu_keyboard("vi", "translation"))
    for label in (
        "🎬 Tạo phụ đề tự động",
        "🌐 Dịch phụ đề video",
        "🎙 Lồng tiếng video",
        "🎞 Phụ đề + Lồng tiếng",
    ):
        assert label in labels
    assert "📄 Dịch file phụ đề" not in labels
    assert "🧾 Bóc lời thoại" not in labels
    assert "🔗 Tải video từ link" not in labels


def test_completed_add_voice_guard_if_mux_unready():
    assert "bảo trì/nâng cấp" in bot.VIDEO_COMPLETED_ADDON_GUARD_TEXTS["voice"]
    assert "chưa xử lý" in bot.VIDEO_COMPLETED_ADDON_GUARD_TEXTS["voice"]
    assert "chưa trừ Xu" in bot.VIDEO_COMPLETED_ADDON_GUARD_TEXTS["voice"]


def test_completed_add_music_guard_if_mux_unready():
    assert "bảo trì/nâng cấp" in bot.VIDEO_COMPLETED_ADDON_GUARD_TEXTS["music"]


def test_completed_add_subtitle_guard_if_pipeline_unready():
    assert "bảo trì/nâng cấp" in bot.VIDEO_COMPLETED_ADDON_GUARD_TEXTS["subtitle"]


def test_feedback_still_works():
    source = inspect.getsource(bot.handle_shopaikey_video_job_callback)
    assert 'if completed_addon_kind == "feedback":' in source
    assert "set_feedback_pending" in source


def test_music_default_duration_18_not_15():
    assert bot.MUSIC_AI_SHORT_DURATION_SECONDS == 18
    assert [item[0] for item in bot.MUSIC_GUIDED_DURATIONS][:3] == ["18s", "30s", "60s"]
    assert _labels(bot.music_song_duration_keyboard("vi"))[:3] == ["18 giây", "30 giây", "60 giây"]


def test_voice_default_duration_18_not_15():
    assert bot.VOICE_DEFAULT_DURATION_SECONDS == 18
    text = bot.voice_text_input_text("vi")
    assert "Mặc định sản phẩm: 18 giây" in text
    assert "Mặc định sản phẩm: 15 giây" not in text


def test_video_standard_duration_3_scenes_18():
    assert bot.VIDEO_FINAL_DEFAULT_SCENES == 3
    assert bot.VIDEO_FINAL_DEFAULT_SECONDS == 18


def test_preview_6_seconds_not_changed():
    assert bot.paid_preview_seconds(120) == 6
    assert bot.VOICE_TTS_PREVIEW_MAX_SECONDS == 6


def test_product_video_scene_uses_canonical_eight_seconds():
    assert bot.TASK3D_SCENE_SECONDS == 8
    assert "1 cảnh khoảng <b>8 giây</b>" in bot.video_finalization_scene_count_text({"selected_video_tier": "basic"}, "vi")


def test_no_public_15_second_product_default_remaining():
    surfaces = "\n".join([
        bot.music_song_product_text("vi"),
        "\n".join(_labels(bot.music_guided_step_keyboard("duration", "vi"))),
        "\n".join(_labels(bot.music_song_duration_keyboard("vi"))),
        bot.voice_text_input_text("vi"),
    ])
    assert "15 giây" not in surfaces
    assert "15/30/60" not in surfaces


def test_public_product_guard_status_admin_only():
    source = inspect.getsource(bot.cmd_public_product_guard_status)
    app_source = Path(bot.__file__).read_text(encoding="utf-8")
    assert "is_admin_user" in source
    assert 'CommandHandler("public_product_guard_status", cmd_public_product_guard_status)' in app_source


def test_public_product_guard_status_no_key_leak(monkeypatch):
    monkeypatch.setattr(bot, "get_suno_music_readiness", lambda: {
        "ready": True, "public_enabled": False, "full_result_ok": False, "cost_gate_ok": True
    })
    monkeypatch.setattr(bot, "get_minimax_voice_clone_readiness", lambda: {"public_enabled": False})
    monkeypatch.setattr(bot, "video_dubbing_public_processing_ready", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(bot, "video_completed_addon_status_payload", lambda: {
        "voice_mux_ready": False, "music_mux_ready": False, "subtitle_mux_ready": False
    })
    text = bot.public_product_guard_status_text().lower()
    for term in ("api_key", "token=", "secret=", "bearer ", "shopaikey", "key4u"):
        assert term not in text


def test_public_product_guard_status_matches_completed_addon_hard_guards(monkeypatch):
    monkeypatch.setattr(bot, "get_suno_music_readiness", lambda: {
        "ready": True, "public_enabled": True, "full_result_ok": True, "cost_gate_ok": True
    })
    monkeypatch.setattr(bot, "get_minimax_voice_clone_readiness", lambda: {
        "ready": True, "public_enabled": True
    })
    monkeypatch.setattr(bot, "video_dubbing_public_processing_ready", lambda *_args, **_kwargs: True)
    payload = bot.public_product_guard_status_payload()
    assert payload["voice_clone"] is True
    assert payload["ai_music"] is True
    assert payload["video_subtitle"] is True
    assert payload["completed_video_add_voice"] is False
    assert payload["completed_video_add_music"] is False
    assert payload["completed_video_add_subtitle"] is False


def test_video_export_core_not_touched():
    source = inspect.getsource(bot.handle_video_export_confirm)
    assert "handle_shopaikey_public_callback(update, context, canonical_callback)" in source


def test_video_flow_not_redesigned():
    assert bot.VIDEO_FLOW_LOCKED_AFTER_TASK3D7 is True


def test_package_list_not_touched():
    assert "package" not in inspect.getsource(bot.public_product_guard_status_payload).lower()


def test_payos_not_touched():
    source = inspect.getsource(bot.public_product_guard_status_payload).lower()
    assert "payos" not in source and "naptien" not in source


def test_task1_provider_internals_not_touched():
    source = inspect.getsource(bot.music_ai_public_processing_ready).lower()
    assert "client.post" not in source and "httpx" not in source


def test_task2_provider_internals_not_touched():
    source = inspect.getsource(bot.video_dubbing_public_processing_ready).lower()
    assert "translate_subtitle_text" not in source and "video_dubbing_tts_bytes" not in source


def test_no_fake_output():
    joined = "\n".join(_public_texts()).lower()
    assert "http://" not in joined and "https://" not in joined
    assert "đã tạo" not in joined and "hoàn tất" not in joined
