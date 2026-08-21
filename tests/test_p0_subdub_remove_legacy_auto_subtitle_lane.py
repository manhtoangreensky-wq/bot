from pathlib import Path


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def test_combo_current_video_cannot_reopen_legacy_auto_subtitle_lane():
    next_screen = BOT_SOURCE.split("def video_dubbing_next_screen_after_source", 1)[1].split(
        "async def _terminalize_subdub_background_failure", 1
    )[0]

    assert '"no_subtitle_menu"' not in next_screen
    assert "subtitle_plus_dub_no_subtitle_menu_text" not in next_screen
    assert "subtitle_plus_dub_no_subtitle_menu_keyboard" not in next_screen


def test_combo_legacy_subtitle_lane_state_is_collapsed_before_rendering():
    normalizer = BOT_SOURCE.split("def normalize_video_dubbing_combo_pending_state", 1)[1].split(
        "def clear_video_dubbing_pending", 1
    )[0]

    assert '"no_subtitle_menu"' in normalizer
    assert '"original_subtitle_confirm"' in normalizer
    assert '"original_subtitle_ready"' in normalizer
    assert '"language" if video_dubbing_has_media(normalized) else "source"' in normalizer


def test_old_combo_message_buttons_cannot_reopen_original_subtitle_screen():
    callback = BOT_SOURCE.split('if action in {"combo_back_original", "combo_back_subtitle_ready"}:', 1)[1].split(
        'if action == "combo_translate":', 1
    )[0]

    assert '"original_subtitle_ready"' not in callback
    assert "subtitle_plus_dub_original_ready_text" not in callback
    assert "subtitle_plus_dub_original_ready_keyboard" not in callback
    assert '"choosing_translation_language"' in callback
