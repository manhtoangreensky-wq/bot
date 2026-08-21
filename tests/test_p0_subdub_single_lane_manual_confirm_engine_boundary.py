from pathlib import Path


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def test_manual_combo_is_confirmed_before_entering_existing_engine():
    callback = BOT_SOURCE.split('if action == "combo_full_dub":', 1)[1].split(
        'if action == "combo_redub_voice":', 1
    )[0]
    manual_branch = callback.split("            else:", 1)[1]

    assert "subdub_final_confirmed=True" in manual_branch
    assert 'subdub_confirmation_source="videodub|combo_full_dub"' in manual_branch
    assert "pending_video_action=action" in manual_branch


def test_combo_remains_single_lane_and_auto_voice_stays_isolated():
    source_keyboard = BOT_SOURCE.split("def video_dubbing_source_keyboard", 1)[1].split(
        "def video_dubbing_recent_source", 1
    )[0]

    assert "items = [(copy['send'], \"videodub|source_upload\")]" in source_keyboard
    assert "videodub|voice|auto_speaker_gender" in BOT_SOURCE
    assert "videodub|path|has_subtitle" not in source_keyboard


def test_single_lane_voice_does_not_reopen_original_subtitle_step():
    callback = BOT_SOURCE.split("async def handle_video_dubbing_callback", 1)[1]
    guard = callback.split(
        'action in {"combo_dub_translated", "voice", "combo_full_dub"}', 1
    )[1].split("):", 1)[0]

    assert "not subtitle_plus_dub_single_lane_pending(state)" in guard


def test_confirmed_manual_combo_uses_status_panel_and_passes_engine_gate():
    callback = BOT_SOURCE.split('if action == "combo_full_dub":', 1)[1].split(
        'if action == "combo_redub_voice":', 1
    )[0]
    readiness = BOT_SOURCE.split("def _product_engine_readiness", 1)[1].split(
        "def can_user_access_product_engine", 1
    )[0]

    assert 'subdub_progress_text("received_file", "", lang)' in callback
    assert 'subdub_progress_keyboard("", lang)' in callback
    assert "and not subdub_final_confirmed_state(state)" in readiness
