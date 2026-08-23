from pathlib import Path


BOT_SOURCE = (Path(__file__).parents[2] / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    markers = (f"def {name}(", f"async def {name}(")
    starts = [BOT_SOURCE.find(marker) for marker in markers]
    start = min(value for value in starts if value >= 0)
    next_sync = BOT_SOURCE.find("\ndef ", start + 5)
    next_async = BOT_SOURCE.find("\nasync def ", start + 5)
    ends = [value for value in (next_sync, next_async) if value >= 0]
    return BOT_SOURCE[start : min(ends) if ends else len(BOT_SOURCE)]


def _between(source: str, start_marker: str, end_marker: str) -> str:
    start = source.index(start_marker)
    end = source.index(end_marker, start + len(start_marker))
    return source[start:end]


def test_combo_source_keyboard_keeps_only_existing_subtitle_lane():
    source = _function_source("video_dubbing_source_keyboard")
    combo = _between(
        source,
        "elif mode == VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB:",
        "\n    else:",
    )

    assert "VIDEO_DUBBING_FLOW_HAS_SUBTITLE" in combo
    assert "VIDEO_DUBBING_FLOW_NO_SUBTITLE" not in combo
    assert combo.count("items =") == 1
