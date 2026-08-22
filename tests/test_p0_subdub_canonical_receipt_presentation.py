from pathlib import Path


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def _source_between(start: str, end: str) -> str:
    start_at = BOT_SOURCE.index(start)
    end_at = BOT_SOURCE.index(end, start_at)
    return BOT_SOURCE[start_at:end_at]


def test_combo_full_dub_uses_the_canonical_completion_report():
    combo_completion = _source_between(
        '        if action == "combo_full_dub":',
        '        if action == "combo_redub_voice":',
    )

    assert "video_dubbing_receipt_text(" in combo_completion
    assert "video_dubbing_receipt_keyboard(" in combo_completion
    assert "subtitle_plus_dub_completed_text(" not in combo_completion
    assert "subtitle_plus_dub_completed_keyboard(" not in combo_completion


def test_subdub_customer_menu_never_sends_admin_debug_blocks():
    customer_handler = _source_between(
        "async def handle_video_dubbing_callback(",
        "def marketing_pending_key(",
    )

    assert "subdub_job_debug_text(" not in customer_handler
    assert "subtitle_dub_debug_text(" not in customer_handler
    assert "SUBDUB JOB DEBUG" not in customer_handler
