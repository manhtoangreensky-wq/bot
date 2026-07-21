import asyncio

import pytest

import bot


SOURCE_SRT = """1
00:00:00,000 --> 00:00:01,000
Source line
"""

SOURCE_SEGMENTS = [{"start": 0.0, "end": 1.0, "text": "Source line"}]


def test_live19_embedded_subtitle_wins_before_ocr_and_asr(monkeypatch):
    calls = []

    async def embedded(*_args, **_kwargs):
        calls.append("stream")
        return SOURCE_SRT, "embedded_ok"

    async def forbidden_ocr(*_args, **_kwargs):
        raise AssertionError("OCR must not run after a valid subtitle stream")

    async def forbidden_asr(*_args, **_kwargs):
        raise AssertionError("ASR must not run after a valid subtitle stream")

    monkeypatch.setattr(bot, "video_dubbing_extract_embedded_subtitle", embedded)
    monkeypatch.setattr(bot, "video_dubbing_extract_visual_subtitle", forbidden_ocr)
    monkeypatch.setattr(bot, "transcribe_media_to_segments", forbidden_asr)
    trace = {}

    result = asyncio.run(
        bot._video_dubbing_resolve_source_script_with_trace(
            b"fixture-video",
            "video/mp4",
            None,
            prefer_visual_subtitles=True,
            execution_trace=trace,
        )
    )

    assert calls == ["stream"]
    assert result["source_kind"] == "embedded_subtitle"
    assert result["segments"]
    assert trace["source_acquisition_method"] == "embedded_subtitle"
    assert trace["source_acquisition_completed"] is True
    assert trace["canonical_cue_count"] == 1


def test_live19_wrong_ocr_falls_through_to_asr_with_exact_trace(monkeypatch):
    async def no_stream(*_args, **_kwargs):
        return "", "no_stream"

    async def rejected_ocr(*_args, **_kwargs):
        return {
            "ok": False,
            "status": "ocr_wrong_script",
            "rejection_reason": "ocr_wrong_script",
            "subtitle": "",
            "segments": [],
        }

    async def asr(*_args, **_kwargs):
        return {
            "output_valid": True,
            "transcript_text": "Source line",
            "segments": list(SOURCE_SEGMENTS),
            "detected_language": "en",
            "provider": "fixture",
            "global_timing_preserved": True,
        }

    monkeypatch.setattr(bot, "video_dubbing_extract_embedded_subtitle", no_stream)
    monkeypatch.setattr(bot, "video_dubbing_extract_visual_subtitle", rejected_ocr)
    monkeypatch.setattr(bot, "transcribe_media_to_segments", asr)
    trace = {}

    result = asyncio.run(
        bot._video_dubbing_resolve_source_script_with_trace(
            b"fixture-video",
            "video/mp4",
            None,
            prefer_visual_subtitles=True,
            execution_trace=trace,
        )
    )

    assert result["source_kind"] == "asr"
    assert result["segments"] == SOURCE_SEGMENTS
    assert trace["ocr_completed"] is True
    assert trace["ocr_accepted"] is False
    assert trace["ocr_rejected"] is True
    assert trace["ocr_rejection_reason"] == "ocr_wrong_script"
    assert trace["asr_fallback_used"] is True
    assert trace["asr_completed"] is True
    assert trace["source_acquisition_method"] == "asr"


def test_live19_auto_subtitle_uses_audio_asr_only(monkeypatch):
    async def asr(*_args, **_kwargs):
        return {
            "output_valid": True,
            "transcript_text": "Nguon am thanh",
            "segments": [{"start": 0.0, "end": 1.0, "text": "Nguon am thanh"}],
            "detected_language": "vi",
            "provider": "fixture",
            "global_timing_preserved": True,
        }

    monkeypatch.setattr(bot, "transcribe_media_to_segments", asr)
    trace = {}

    result = asyncio.run(
        bot.video_dubbing_resolve_auto_subtitle_script(
            b"fixture-video",
            "video/mp4",
            None,
            execution_trace=trace,
        )
    )

    assert result["source_kind"] == "asr"
    assert result["extraction_source"] == "audio_asr"
    assert result["detected_language"] == "vi"
    assert trace["source_acquisition_method"] == "audio_asr"
    assert trace["asr_completed"] is True
    assert trace["translation_started"] is False


@pytest.mark.parametrize(
    ("job", "expected_stage", "expected_blocker"),
    [
        (
            {"route_attempts": {"canonical_cue_count": 0, "translation_started": False}},
            "source_acquisition",
            "no_usable_subtitle_or_audio_source",
        ),
        (
            {"route_attempts": {"canonical_cue_count": 2, "translation_started": False}},
            "translation",
            "translation_not_attempted",
        ),
        (
            {"route_attempts": {"canonical_cue_count": 2, "translation_started": True}},
            "translation",
            "translation_missing",
        ),
    ],
)
def test_live19_translation_missing_requires_cues_and_attempt(job, expected_stage, expected_blocker):
    fields = bot.subdub_failure_stage_fields("translation_missing", job=job)

    assert fields["last_error_stage"] == expected_stage
    assert fields["pipeline_blocker"] == expected_blocker
    assert fields["input_save_blocker"] == ""


def test_live19_persisted_string_zero_does_not_fake_translation_attempt():
    fields = bot.subdub_failure_stage_fields(
        "translation_missing",
        job={"canonical_cue_count": 2, "translation_started": "0"},
    )

    assert fields["last_error_stage"] == "translation"
    assert fields["pipeline_blocker"] == "translation_not_attempted"
    assert fields["translation_blocker"] == "translation_not_attempted"


def test_live19_persisted_top_level_wins_stale_nested_debug_snapshot():
    merged = bot.subdub_merge_debug_job(
        {
            "job_id": "live19-persisted",
            "status": "FAILED_NO_CHARGE",
            "terminal_state": "failed_no_charge",
            "progress_percent": 95,
            "current_stage": "failed_no_charge",
            "pipeline_blocker": "no_usable_subtitle_or_audio_source",
            "debug_job": {
                "status": "RUNNING",
                "terminal_state": "",
                "progress_percent": 35,
                "current_stage": "recognizing_speech",
                "pipeline_blocker": "",
            },
        }
    )

    assert merged["status"] == "FAILED_NO_CHARGE"
    assert merged["terminal_state"] == "failed_no_charge"
    assert merged["progress_percent"] == 95
    assert merged["current_stage"] == "failed_no_charge"
    assert merged["exact_blocker"] == "no_usable_subtitle_or_audio_source"
