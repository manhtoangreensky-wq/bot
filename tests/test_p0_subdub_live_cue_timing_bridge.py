import asyncio

import bot


def test_live_asr_segments_keep_exact_start_and_end(monkeypatch):
    source = [
        {"index": 1, "start": 0.125, "end": 0.625, "text": "first cue"},
        {"index": 2, "start": 1.875, "end": 2.225, "text": "second cue"},
        {"index": 3, "start": 4.5, "end": 8.75, "text": "third cue"},
    ]

    async def fake_asr(*_args, **_kwargs):
        return {
            "ok": True,
            "provider": "fixture",
            "text": "first cue second cue third cue",
            "segments": source,
            "duration_seconds": 9,
            "subtitle_timing_source": "provider_segments",
            "global_timing_preserved": True,
        }

    monkeypatch.setattr(bot, "asr_transcribe_audio", fake_asr)
    result = asyncio.run(
        bot.transcribe_media_to_segments(
            {"bytes": b"fixture-audio", "content_type": "audio/mpeg", "duration_seconds": 9},
            duration_seconds=9,
        )
    )

    assert result["output_valid"] is True
    assert result["subtitle_timing_source"] == "provider_segments"
    assert result["global_timing_preserved"] is True
    assert [(item["start"], item["end"]) for item in result["segments"]] == [
        (item["start"], item["end"]) for item in source
    ]


def test_estimated_transcript_timeline_is_not_reported_as_provider_locked(monkeypatch):
    async def fake_asr(*_args, **_kwargs):
        return {
            "ok": True,
            "provider": "fixture",
            "text": "one two three four five six",
            "segments": [],
            "duration_seconds": 6,
            "subtitle_timing_source": "estimated_transcript_distribution",
            "global_timing_preserved": False,
        }

    monkeypatch.setattr(bot, "asr_transcribe_audio", fake_asr)
    result = asyncio.run(
        bot.transcribe_media_to_segments(
            {"bytes": b"fixture-audio", "content_type": "audio/mpeg", "duration_seconds": 6},
            duration_seconds=6,
        )
    )

    assert result["output_valid"] is True
    assert result["subtitle_timing_source"] == "estimated_transcript_distribution"
    assert result["global_timing_preserved"] is False


def test_translated_live_cues_keep_provider_timeline(monkeypatch):
    source = [
        {"index": 1, "start": 0.2, "end": 1.1, "text": "source one"},
        {"index": 2, "start": 2.4, "end": 3.7, "text": "source two"},
    ]

    async def fake_translate(text, _target_language, **_kwargs):
        return {"text": f"translated {text}", "provider": "fixture"}

    monkeypatch.setattr(bot, "translate_subtitle_text", fake_translate)
    translated = asyncio.run(bot.translate_subtitle_segments(source, "English"))

    assert [(item["start"], item["end"]) for item in translated["segments"]] == [
        (0.2, 1.1),
        (2.4, 3.7),
    ]
