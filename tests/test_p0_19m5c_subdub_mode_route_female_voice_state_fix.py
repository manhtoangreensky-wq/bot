import subprocess

import bot


def test_subtitle_only_entrypoint_resolves_subtitle_only_mode():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "source_entry": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "active_flow": "subtitle_translate",
    }
    debug = bot.subdub_route_state_debug_fields(bot.VIDEO_SUBTITLE_MODE_TRANSLATE, state)

    assert bot.subdub_product_type_from_mode(bot.VIDEO_SUBTITLE_MODE_TRANSLATE, state) == "subtitle_only"
    assert debug["expected_product_type"] == "subtitle_only"
    assert debug["resolved_product_type"] == "subtitle_only"
    assert debug["resolved_mode"] == bot.VIDEO_SUBTITLE_MODE_TRANSLATE
    assert debug["route_state_stale_detected"] is False


def test_subtitle_plus_dub_entrypoint_resolves_dub_mode():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "requested_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "active_flow": bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
        "source_entry": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "product_type": "subtitle_only",
    }
    debug = bot.subdub_route_state_debug_fields(bot.VIDEO_SUBTITLE_MODE_TRANSLATE, state)

    assert bot.subdub_product_type_from_mode(bot.VIDEO_SUBTITLE_MODE_TRANSLATE, state) == "subtitle_dub"
    assert debug["expected_product_type"] == "subtitle_dub"
    assert debug["resolved_product_type"] == "subtitle_dub"
    assert debug["resolved_mode"] == bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB
    assert bot.video_dubbing_requires_voice(debug["resolved_mode"]) is True
    assert debug["route_state_stale_detected"] is True


def test_female_default_voice_selected_for_dub_when_requested(monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "female-real-voice")
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "male-real-voice")
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "voice_kind": "default_female",
        "voice_style": "Giọng nữ mặc định",
    }

    voice_id = bot.resolve_video_dub_tts_voice_id(1, state)

    assert voice_id == "female-real-voice"
    assert state["selected_voice_gender"] == "female"
    assert state["resolved_gender"] == "female"
    assert state["tts_payload_voice_id"] == "female-real-voice"
    assert state["voice_fallback_used"] is False


def test_stale_route_state_cleared_when_user_switches_subdub_product():
    uid = 195500
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "language",
        mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        process_type=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        product_type="subtitle_only",
    )
    state = bot.set_video_dubbing_pending(
        uid,
        "language",
        mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        process_type=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        requested_mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        active_flow=bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
    )

    assert state["product_type"] == "subtitle_dub"
    assert bot.subdub_route_state_debug_fields(bot.VIDEO_SUBTITLE_MODE_TRANSLATE, state)["route_state_stale_detected"] is False
    bot.clear_video_dubbing_pending(uid)


def test_back_button_returns_exact_previous_subdub_screen():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "requested_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "active_flow": bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
        "step": "confirm",
    }

    assert bot.video_dubbing_back_route(state, "back_confirm") == "voice"
    assert bot.video_dubbing_back_route(state, "back_voice") == "language"
    assert bot.subdub_missing_origin_back_callback({}) == "videodub|back_type"


def test_public_labels_short_no_debug_terms():
    text = bot.video_dubbing_menu_text("vi", "translation")
    keyboard = bot.video_dubbing_menu_keyboard("vi", "translation")
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    public = " ".join([text, *labels]).lower()

    assert labels
    assert all(len(label) <= 32 for label in labels)
    assert not any(term in public for term in ("provider", "api", "handler", "callback", "debug", "asr", "tts", "mux", "ffmpeg"))


def test_no_product_video_music_payos_changes():
    changed = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True).splitlines()
    allowed = {
        "bot.py",
        "tests/test_p0_19m5a_subdub_large_telegram_media_input_save_fix.py",
        "tests/test_p0_19m5c_subdub_mode_route_female_voice_state_fix.py",
    }

    assert set(changed) <= allowed
