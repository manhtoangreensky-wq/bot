from pathlib import Path

import bot


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    marker = f"def {name}("
    async_marker = f"async def {name}("
    start = BOT_SOURCE.find(marker)
    if start < 0:
        start = BOT_SOURCE.index(async_marker)
    next_def = BOT_SOURCE.find("\ndef ", start + len(marker))
    next_async = BOT_SOURCE.find("\nasync def ", start + len(marker))
    candidates = [item for item in (next_def, next_async) if item >= 0]
    next_start = min(candidates) if candidates else -1
    return BOT_SOURCE[start:] if next_start < 0 else BOT_SOURCE[start:next_start]


def test_m4live8b_subtitle_ass_runtime_matches_m4live7_chunked_baseline():
    source = _function_source("subdub_generate_ass_from_srt")

    assert "subdub_ass_text_chunks" in source
    assert "total_weight" in source
    assert "elapsed_weight" in source
    assert "chunk_start = block_start + ((block_end - block_start)" in source
    assert "subdub_ass_timestamp(chunk_start)" in source
    assert "subdub_ass_timestamp(chunk_end)" in source
    assert "subtitle_timing_preserved: yes" not in source
    assert "subtitle_text_length_duration_split: no" not in source


def test_m4live8b_subtitle_translate_ass_splits_long_text_like_m4live7():
    srt = (
        "1\n"
        "00:00:01,000 --> 00:00:05,000\n"
        "Mot cau phu de dich rat dai can duoc chia nhip theo baseline M4LIVE7 de khong lam hong video phu de rieng\n"
    )
    ass = bot.subdub_generate_ass_from_srt(
        srt,
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            "show_subtitles": True,
            "subtitle_font_resolution_ok": True,
            "font": "Arial",
            "play_res_x": 1280,
            "play_res_y": 720,
            "render_size": 34,
            "max_lines": 2,
            "m4live1_style_renderer_only": True,
        },
    )

    assert ass
    dialogue_lines = [line for line in ass.splitlines() if line.startswith("Dialogue: 0,")]
    assert dialogue_lines
    assert all(line.count("\\N") <= 1 for line in dialogue_lines)
    assert "subtitle_timing_preserved: yes" not in ass
    assert "subtitle_text_length_duration_split: no" not in ass


def test_m4live8b_subtitle_receipt_and_buttons_stay_on_m4live7_success_contract():
    assert "✅ <b>Đã tạo video phụ đề thành công.</b>" in BOT_SOURCE
    assert "• Trạng thái: <b>Đã gửi video</b>" in BOT_SOURCE
    assert "Tải video phụ đề dịch" in BOT_SOURCE
    assert "Tải SRT dịch" in BOT_SOURCE


def test_m4live8b_generic_fail_guard_does_not_override_subtitle_success_contract():
    fail_source = _function_source("send_subdub_fail_once")

    assert "subdub_should_suppress_generic_fail_for_active_job" in fail_source
    assert "public_error_sent" in fail_source
    assert "TOAN AAS chưa dịch được phụ đề lúc này" in BOT_SOURCE


def test_m4live8b_no_forbidden_cross_product_runtime_changes():
    changed_contract = "\n".join(
        [
            _function_source("subdub_generate_ass_from_srt"),
            _function_source("send_subdub_fail_once"),
        ]
    )

    assert "music_song" not in changed_contract.lower()
    assert "payos" not in changed_contract.lower()
    assert "wallet" not in changed_contract.lower()
    assert "product_video" not in changed_contract.lower()
