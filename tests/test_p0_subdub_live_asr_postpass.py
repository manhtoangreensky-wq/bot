from pathlib import Path


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    start = BOT_SOURCE.index(f"async def {name}(")
    end = BOT_SOURCE.index("\nasync def ", start + 1)
    return BOT_SOURCE[start:end]


def test_original_subtitle_post_asr_exception_is_logged_safely():
    block = _function_source("video_dubbing_create_original_subtitle_for_next_step")

    assert "subdub original subtitle prepare failed" in block
    assert "type(exc).__name__" in block
    assert "sanitize_log_text(str(exc))" in block
