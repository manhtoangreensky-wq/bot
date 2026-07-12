import asyncio
from pathlib import Path

import bot


def test_dub_and_combo_translate_when_target_language_is_selected_without_stale_flag():
    for mode in (bot.VIDEO_SUBTITLE_MODE_DUB, bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB):
        assert bot.subdub_mode_requests_translation(mode, {"target_language": "English"}) is True
        assert bot.subdub_mode_requests_translation(mode, {"target_language": "日本語"}) is True
        assert bot.subdub_mode_requests_translation(mode, {"target_language": "Tiếng Việt"}) is True


def test_original_source_selection_never_creates_target_translation():
    for token in ("source", "original", "nguyên bản", "Giữ nguyên ngôn ngữ gốc"):
        assert bot.subdub_mode_requests_translation(
            bot.VIDEO_SUBTITLE_MODE_DUB,
            {"target_language": token, "dub_text_source": token},
        ) is False


def test_timeline_audio_hard_stops_each_tts_track_before_next_cue(monkeypatch):
    captured = {}

    async def fake_run(command, timeout=0):
        captured["command"] = list(command)
        captured["timeout"] = timeout
        Path(command[-1]).write_bytes(b"timeline-audio")
        return True, "fixture"

    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(bot, "run_ffmpeg_command", fake_run)
    chunks = [
        {"index": 1, "start": 0.0, "end": 1.0, "audio_duration": 3.0, "audio_bytes": b"one"},
        {"index": 2, "start": 1.5, "end": 2.5, "audio_duration": 2.0, "audio_bytes": b"two"},
    ]

    audio, detail = asyncio.run(bot.build_dub_timeline_audio(chunks, 3.0))

    assert audio == b"timeline-audio"
    assert detail == "ffmpeg_timeline_audio"
    filters = captured["command"][captured["command"].index("-filter_complex") + 1]
    assert "atrim=duration=1.000" in filters
    assert "adelay=0|0" in filters
    assert "adelay=1500|1500" in filters
    assert filters.count("atrim=duration=") == 3


def test_target_tts_policy_has_one_track_and_never_source_tts():
    prepared = {
        "source_segments": [{"index": 1, "start": 0, "end": 1, "text": "原文"}],
        "output_segments": [{"index": 1, "start": 0, "end": 1, "text": "Bản dịch"}],
    }
    policy = bot.subtitle_dub_product_pipeline.resolve_subdub_dub_audio_policy(
        {"target_language": "Tiếng Việt"},
        prepared,
    )
    assert [item["text"] for item in policy["tts_segments"]] == ["Bản dịch"]
    assert policy["tts_tracks_count"] == 1
    assert policy["source_tts_rendered"] is False
    assert policy["target_tts_rendered"] is True
