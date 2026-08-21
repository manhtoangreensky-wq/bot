from pathlib import Path


BOT_SOURCE = Path(__file__).resolve().parents[1] / "bot.py"


def test_combo_voice_guard_does_not_reopen_original_subtitle_for_single_lane():
    source = BOT_SOURCE.read_text(encoding="utf-8")
    start = source.index("async def handle_video_dubbing_callback(")
    block = source[start:]
    legacy_guard = (
        'if action in {"combo_dub_translated", "voice", "combo_full_dub"} '
        'and not state.get("translated_subtitle_ref"):'
    )

    assert legacy_guard not in block
    assert "and not subtitle_plus_dub_single_lane_pending(state)" in block
