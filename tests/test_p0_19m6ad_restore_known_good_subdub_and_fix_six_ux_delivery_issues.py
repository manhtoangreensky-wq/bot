import asyncio
import inspect
from pathlib import Path

import bot


ROOT = Path(__file__).resolve().parents[1]


def _source(name: str) -> str:
    return inspect.getsource(getattr(bot, name))


def test_ambiguous_telegram_video_metadata_still_reaches_asr(monkeypatch):
    calls = []
    monkeypatch.setattr(bot, "video_dubbing_audio_extract_ready", lambda: True)

    async def fake_extract(source_bytes, content_type="application/octet-stream", max_seconds=0):
        calls.append(("extract", bytes(source_bytes), content_type, max_seconds))
        return b"audio-from-video", "audio/mpeg", "ffmpeg_audio_extract"

    async def fake_transcribe(audio_bytes, _context, content_type="application/octet-stream", **_kwargs):
        calls.append(("asr", bytes(audio_bytes), content_type))
        return "unit_asr", "xin chao tu video", "ok"

    monkeypatch.setattr(bot, "video_dubbing_extract_audio", fake_extract)
    monkeypatch.setattr(bot, "video_dubbing_transcribe_bytes", fake_transcribe)

    result = asyncio.run(bot.transcribe_media_to_segments({
        "bytes": b"telegram-video-bytes",
        "content_type": "application/octet-stream",
        "media_kind": "media",
        "file_name": "media",
        "duration_seconds": 9,
    }))

    assert result["output_valid"] is True
    assert result["provider"] == "unit_asr"
    assert calls[0] == ("extract", b"telegram-video-bytes", "video/mp4", 0)
    assert calls[1] == ("asr", b"audio-from-video", "audio/mpeg")


def test_translate_cache_fix_kept_for_international_subtitle_translation():
    source = _source("video_dubbing_prepare_subtitles")

    assert 'translated_ref = str(state.get("translated_subtitle_ref") or "").strip()' in source
    assert 'output_subtitle = get_video_dubbing_artifact(user_id, translated_ref) if translated_ref else ""' in source
    assert 'state.get("translated_subtitle_ref") or "translated_subtitle"' not in source


def test_audio_mix_controls_remain_split_and_numeric():
    assert "audio_original" in _source("subdub_audio_mix_keyboard")
    assert "audio_dub" in _source("subdub_audio_mix_keyboard")
    handler = _source("handle_video_dubbing_pending_text")
    assert "subdub_original_volume_input" in handler
    assert "subdub_dub_volume_input" in handler
    assert 'maximum = 100 if layer == "original" else 200' in handler


def test_subtitle_style_stays_moderate_bottom_center():
    assert "base + 4" in _source("subdub_render_subtitle_size")
    assert "subdub_ass_alignment" in _source("subdub_generate_ass_from_srt")
    assert "subdub_ass_wrap_text" in _source("subdub_generate_ass_from_srt")


def test_late_public_failure_suppression_kept_after_success():
    assert "subdub_should_suppress_late_public_failure(job)" in _source("send_subdub_fail_once")
    assert "late_error_after_video_success" in _source("subdub_should_suppress_outer_error")


def test_final_receipt_and_full_green_status_kept():
    callback = _source("handle_video_dubbing_callback")
    receipt = _source("video_dubbing_receipt_text")

    assert 'subdub_progress_text("delivered"' in callback
    assert "panel_final_percent=100" in callback
    assert "• Kết quả:" in receipt
    assert "• Thời lượng:" in receipt
