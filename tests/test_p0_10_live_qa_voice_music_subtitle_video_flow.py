from pathlib import Path

import inspect

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _source_between(start_marker: str, end_marker: str) -> str:
    source = Path(bot.__file__).resolve().read_text(encoding="utf-8")
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def test_public_voice_labels_use_nghe_not_nghe_xem():
    labels = _labels(bot.voice_clone_preview_entry_keyboard(1, "vi"))
    labels += _labels(bot.audio_voice_preview_keyboard("vi"))
    joined = "\n".join(labels)
    assert "▶️ Nghe thử 6 giây" in labels
    assert "✅ Tạo giọng đọc" in labels
    assert "✏️ Sửa nội dung" in labels
    assert "nghe/xem" not in joined.lower()


def test_public_video_labels_use_xem_not_nghe_xem(monkeypatch):
    monkeypatch.setattr(bot, "video_paid_preview_worker_available", lambda: True)
    markup = bot.video_addon_confirm_keyboard(
        "tok",
        "basic",
        "vi",
        {"pending_payload": {"video_tier": "basic", "duration_seconds": 18, "scene_count": 3}},
    )
    labels = _labels(markup)
    assert "🎬 Xuất video" in labels
    assert "⚙️ Đổi tùy chọn" in labels
    assert not any("nghe/xem" in label.lower() for label in labels)


def test_public_no_slash_combo_labels_for_preview():
    surfaces = "\n".join([
        bot.video_paid_preview_text({"pending_payload": {"video_tier": "basic", "duration_seconds": 18}}, "vi"),
        bot.video_dubbing_confirm_text({"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "video_duration": 30, "voice_style": "Giọng nữ"}, "vi"),
        "\n".join(_labels(bot.video_dubbing_confirm_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_DUB}))),
    ]).lower()
    assert "nghe/xem" not in surfaces
    assert "giọng/nhạc" not in surfaces
    assert "phụ đề/lồng tiếng" not in surfaces


def test_public_no_provider_terms():
    surfaces = "\n".join([
        bot.voice_profile_not_ready_text({"display_name": "Giọng 1", "status": "failed"}, "vi"),
        bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_TRANSLATE, {}, "vi", admin=False),
        bot.video_preview_locked_text({"video_tier": "low"}, "vi"),
        bot.suno_user_guard_text("vi"),
    ]).lower()
    for term in ("provider", "api", "smoke", "ready=false", "admin blocker", "key4u", "shopaikey", "minimax", "gemini"):
        assert term not in surfaces


def test_minimax_admin_status_has_readiness():
    text = bot.voice_status_text()
    for label in (
        "MiniMax configured",
        "MiniMax base URL present",
        "MiniMax API key present",
        "MiniMax group/project id",
        "TTS endpoint ready",
        "Voice clone endpoint ready",
        "Saved voice_id available",
        "Last TTS smoke result",
        "Last clone smoke result",
        "Last error sanitized",
    ):
        assert label in text


def test_minimax_public_guard_clean():
    text = bot.get_minimax_voice_readiness()["safe_user_message"].lower()
    for term in ("provider", "api", "smoke", "key4u", "shopaikey", "minimax"):
        assert term not in text


def test_paid_voice_real_route_or_admin_blocker_only():
    source = _source_between("async def shopaikey_minimax_tts_bytes", "async def direct_minimax_tts_bytes")
    assert "direct_minimax_tts_bytes" in source
    assert "shopaikey_official_tts_payload" in source
    assert "httpx.AsyncClient" in source
    public_guard = bot.voice_profile_not_ready_text({"display_name": "Lỗi", "status": "failed"}, "vi")
    assert "API" not in public_guard
    assert "provider" not in public_guard.lower()


def test_voice_preview_failure_copy_voice_specific():
    source = inspect.getsource(bot.voice_clone_product_failure_text)
    assert "TOAN AAS chưa tạo được voice hợp lệ" in source
    assert "dùng giọng nam/nữ mặc định" in source


def test_custom_voice_no_600_label():
    surfaces = "\n".join([
        bot.voice_clone_quote_text({"id": 0, "user_id": "test", "display_name": "Giọng mới"}, "vi"),
        "\n".join(_labels(bot.video_finalization_voice_keyboard("vi"))),
        bot.voice_profile_policy_label("vi"),
    ])
    assert "600 Xu" not in surfaces
    assert str(int(bot.VOICE_PROFILE_PRICE_XU or 0)) in surfaces


def test_background_music_guided_flow_purpose_style_mood_duration_options():
    purpose = _labels(bot.music_guided_step_keyboard("purpose", "vi"))
    style = _labels(bot.music_guided_step_keyboard("style", "vi"))
    mood = _labels(bot.music_guided_step_keyboard("mood", "vi"))
    duration = _labels(bot.music_guided_step_keyboard("duration", "vi"))
    for label in ("Video bán hàng", "Reels/TikTok", "Podcast", "Thiền/thư giãn", "Game/intro", "Nhập mục đích khác"):
        assert label in purpose
    for label in ("Cinematic", "Lo-fi", "EDM", "Acoustic", "Corporate", "Luxury", "Nhập style khác"):
        assert label in style
    for label in ("Vui", "Sang trọng", "Cảm xúc", "Bí ẩn", "Năng lượng", "Thư giãn", "Nhập mood khác"):
        assert label in mood
    for label in ("18 giây", "30 giây", "60 giây", "Nhập thời lượng khác"):
        assert label in duration


def test_song_seconds_half_full_guided_flow_complete():
    mode_labels = _labels(bot.music_song_product_keyboard("vi"))
    assert "⏱ Theo số giây" not in mode_labels
    assert "🎤 Bài hát có lời AI" in mode_labels
    assert "1️⃣ Nửa bài" not in mode_labels
    genre_labels = _labels(bot.music_song_options_keyboard("genre", "vi"))
    mood_labels = _labels(bot.music_song_options_keyboard("mood", "vi"))
    vocal_labels = _labels(bot.music_song_options_keyboard("vocal", "vi"))
    assert {"Pop", "Ballad", "Rap", "EDM", "Acoustic", "Bolero", "Tự nhập thể loại"}.issubset(set(genre_labels))
    assert {"Vui", "Buồn", "Truyền cảm hứng", "Sang trọng", "Hài hước", "Tự nhập cảm xúc"}.issubset(set(mood_labels))
    assert {"Giọng nam", "Giọng nữ", "Song ca", "Không lời", "Tự nhập giọng hát"}.issubset(set(vocal_labels))


def test_song_preview_12s_not_duration():
    result = {"song_product": "full", "guided_duration": "120s"}
    assert bot.music_result_duration_seconds(result) == 120
    assert bot.music_preview_seconds() == 12


def test_music_preview_labels_match_selected_product():
    background = {"song_product": ""}
    song = {"song_product": "full"}
    assert "▶️ Nghe thử 12 giây" in _labels(bot.music_ai_preview_keyboard("vi", preview_seen=False, result=background))
    assert "✅ Dùng bản đầy đủ" in _labels(bot.music_ai_preview_keyboard("vi", preview_seen=True, result=background))
    assert "▶️ Nghe thử 12 giây" in _labels(bot.music_ai_preview_keyboard("vi", preview_seen=False, result=song))
    assert "✅ Dùng bản đầy đủ 800 Xu" in _labels(bot.music_ai_preview_keyboard("vi", preview_seen=True, result=song))
    public_music_text = bot.suno_user_guard_text("vi").lower()
    assert "nhạc/giọng" not in public_music_text
    assert "nghe thử/guard" not in public_music_text


def test_subtitle_and_translation_flow_no_voice_selection():
    assert not bot.video_dubbing_requires_voice(bot.VIDEO_SUBTITLE_MODE_CREATE)
    assert not bot.video_dubbing_requires_voice(bot.VIDEO_SUBTITLE_MODE_TRANSLATE)
    subtitle_labels = _labels(bot.video_dubbing_confirm_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}))
    translate_labels = _labels(bot.video_dubbing_confirm_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE}))
    assert "👁 Xem thử" not in subtitle_labels
    assert "👁 Xem thử" not in translate_labels
    assert "✅ Tạo phụ đề gốc" in subtitle_labels
    assert "✅ Xác nhận dịch" in translate_labels
    assert "✅ Xác nhận tạo đầy đủ" in _labels(bot.video_dubbing_preview_ready_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}))
    assert "✅ Xác nhận tạo đầy đủ" in _labels(bot.video_dubbing_preview_ready_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE}))
    assert not any("giọng" in label.lower() for label in subtitle_labels)
    assert not any("giọng" in label.lower() for label in translate_labels)


def test_dubbing_flow_requires_voice_selection_and_clean_guard():
    assert bot.video_dubbing_requires_voice(bot.VIDEO_SUBTITLE_MODE_DUB)
    labels = _labels(bot.video_dubbing_voice_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_DUB}))
    assert any("Giọng nữ" in label for label in labels)
    assert any("Giọng nam" in label for label in labels)
    assert not any("Kho voice" in label for label in labels)
    admin_labels = _labels(bot.video_dubbing_voice_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "entry_surface": "admin_test_mode"}))
    assert any("Kho voice" in label for label in admin_labels)
    confirm_labels = _labels(bot.video_dubbing_confirm_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_DUB}))
    assert "▶️ Nghe thử" not in confirm_labels
    assert "✅ Xác nhận lồng tiếng" in confirm_labels
    assert "✅ Xác nhận tạo đầy đủ" in _labels(bot.video_dubbing_preview_ready_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_DUB}))
    guard = bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_DUB, {}, "vi", admin=False)
    assert "Admin blocker" not in guard
    assert "provider" not in guard.lower()


def test_video_default_final_duration_18s_3_scenes(monkeypatch):
    monkeypatch.setattr(bot, "video_paid_preview_worker_available", lambda: True)
    model = bot.video_final_duration_model({}, {}, "basic")
    assert model["scene_count"] == 3
    assert model["scene_duration_seconds"] == 6
    assert model["final_duration_seconds"] == 18
    assert model["preview_duration_seconds"] == 6


def test_preview_disabled_under_18s(monkeypatch):
    monkeypatch.setattr(bot, "video_paid_preview_worker_available", lambda: True)
    model = bot.video_final_duration_model({"duration_seconds": 17}, {}, "basic")
    assert model["final_duration_seconds"] >= 18
    assert model["preview_enabled"] is False
    assert model["preview_locked_reason"] == "under_18s"


def test_preview_locked_for_200_but_full_export_active(monkeypatch):
    monkeypatch.setattr(bot, "video_paid_preview_worker_available", lambda: True)
    state = {"video_tier": "low", "pending_payload": {"video_tier": "low", "duration_seconds": 18, "scene_count": 3}}
    markup = bot.video_addon_confirm_keyboard("tok", "low", "vi", state)
    labels = _labels(markup)
    callbacks = _callbacks(markup)
    assert "🔒 Xem thử video" not in labels
    assert "videoaddon|preview_locked|tok" not in callbacks
    assert "🎬 Xuất video" in labels
    assert "videoaddon|export|tok" in callbacks


def test_full_export_does_not_route_to_preview():
    assert not bot.video_paid_preview_required({"job_type": "video", "base_cost": 200})
    source = _source_between("async def handle_shopaikey_public_callback", "async def cmd_video_price_test")
    assert "preview_required" in _source_between("def video_paid_preview_required", "PAID_PREVIEW_REQUIRED_TASKS")
    assert source.index("video_paid_preview_required(pending)") < source.index("spend_fixed_credit_info")


def test_video_backstack_labels_match_business_steps():
    invoice = bot.video_addon_confirm_keyboard("tok", "basic", "vi")
    package = bot.video_finalization_tier_keyboard("vi")
    addons = bot.video_finalization_menu_keyboard("vi")
    assert "⬅️ Quay lại" in _labels(invoice)
    assert "videoaddon|back" in _callbacks(invoice)
    assert "vfinal|back" in _callbacks(package)
    assert "vfinal|back" in _callbacks(addons)
    handler = _source_between("async def handle_video_addon_callback", "async def cmd_video_price_test")
    assert 'finalization_state["step"] = "scene_count"' in handler
    assert 'finalization_state["origin_screen"] = "invoice_back_to_scene_count"' in handler


def test_200_no_paid_addons_can_full_export():
    state = {
        "video_tier": "low",
        "current_video_duration_seconds": 18,
        "current_video_music_option": "none",
        "current_video_music_choice": "none",
        "current_video_voice_choice": "default_female",
        "current_video_subtitle_option": "none",
        "current_video_dubbing_option": "none",
        "translation_enabled": False,
        "video_project": {"scene_count": 3},
    }
    guard = bot.validate_video_tier_selection(state, "low")
    assert guard["ok"] is True
    assert guard["blocked"] is False


def test_200_paid_addon_blocked_with_upgrade_or_back():
    state = {
        "video_tier": "low",
        "current_video_duration_seconds": 18,
        "current_video_music_option": "ai_music",
        "current_video_music_choice": "ai_music",
        "current_video_voice_choice": "none",
        "current_video_subtitle_option": "none",
        "current_video_dubbing_option": "none",
        "translation_enabled": False,
        "video_project": {"scene_count": 3},
    }
    guard = bot.validate_video_tier_selection(state, "low")
    assert guard["blocked"] is True
    assert "paid_music" in guard["reasons"]
    callbacks = _callbacks(bot.video_experience_tier_lock_keyboard("vi"))
    assert callbacks == ["videoaddon|upgrade_300", "videoaddon|export_back"]
