import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace

import bot


def _valid_input_save():
    return {
        "file_saved": True,
        "exists": True,
        "size": 1024,
        "path": str(Path(__file__)),
    }


def test_pipeline_blocker_keeps_no_speech_and_missing_audio_truth():
    gate = {"product_route_allowed": True, "gate_blockers": []}

    assert bot.video_dubbing_pipeline_blocker(
        input_save=_valid_input_save(),
        gate_matrix=gate,
        detail="long_media_no_speech",
        pipeline_attempted=True,
    ) == "long_media_no_speech"
    assert bot.video_dubbing_pipeline_blocker(
        input_save=_valid_input_save(),
        gate_matrix=gate,
        detail="source_audio_missing",
        pipeline_attempted=True,
    ) == "source_audio_missing"
    assert bot.video_dubbing_pipeline_blocker(
        input_save=_valid_input_save(),
        gate_matrix=gate,
        detail="deepgram_empty_transcript",
        pipeline_attempted=True,
    ) == "no_speech_detected"
    assert bot.video_dubbing_pipeline_blocker(
        input_save=_valid_input_save(),
        gate_matrix=gate,
        detail="audio_stream_missing",
        pipeline_attempted=True,
    ) == "final_audio_missing"


def test_final_mp4_audio_requirement_matches_all_four_lanes():
    source_with_audio = {"ok": True, "has_audio": True}
    source_without_audio = {"ok": True, "has_audio": False}

    assert bot.subdub_final_video_audio_required(
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        source_with_audio,
    ) is True
    assert bot.subdub_final_video_audio_required(
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        source_with_audio,
    ) is True
    assert bot.subdub_final_video_audio_required(
        bot.VIDEO_SUBTITLE_MODE_DUB,
        source_without_audio,
    ) is True
    assert bot.subdub_final_video_audio_required(
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        source_without_audio,
    ) is True
    assert bot.subdub_final_video_audio_required(
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        source_without_audio,
    ) is False

    executor_source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert executor_source.count("require_audio=final_audio_required") == 2


def test_delivery_revalidates_required_audio_before_sending(monkeypatch):
    captured = []

    async def fake_validate(_payload, *, require_audio=False, **_kwargs):
        captured.append(require_audio)
        return {
            "ok": False,
            "detail": "audio_stream_missing",
            "has_video": True,
            "has_audio": False,
            "duration": 10.0,
        }

    monkeypatch.setattr(bot, "subdub_validate_video_output", fake_validate)

    result = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            SimpleNamespace(),
            mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            video_bytes=b"candidate-mp4",
            include_subtitle_outputs=False,
            strict_validation=True,
            expected_duration_seconds=10,
            require_final_audio=True,
        )
    )

    assert captured == [True]
    assert result["final_mp4_delivered"] is False
    assert result["final_mp4_validated"] is False
    assert result["success_blocked_reason"] == "audio_stream_missing"


def test_video_without_audio_stops_before_asr(monkeypatch):
    calls = {"extract": 0, "asr": 0}

    async def fake_probe(_payload):
        return {
            "ok": True,
            "has_video": True,
            "has_audio": False,
            "duration": 10.0,
            "width": 720,
            "height": 1280,
        }

    async def extract_must_not_run(*_args, **_kwargs):
        calls["extract"] += 1
        raise AssertionError("audio extraction must not run for a video without audio")

    async def asr_must_not_run(*_args, **_kwargs):
        calls["asr"] += 1
        raise AssertionError("ASR must not run for a video without audio")

    monkeypatch.setattr(bot, "subdub_probe_video_bytes", fake_probe)
    monkeypatch.setattr(bot, "video_dubbing_audio_extract_ready", lambda: True)
    monkeypatch.setattr(bot, "video_dubbing_extract_audio", extract_must_not_run)
    monkeypatch.setattr(bot, "asr_transcribe_audio", asr_must_not_run)

    result = asyncio.run(
        bot.transcribe_media_to_segments(
            {
                "bytes": b"silent-video",
                "content_type": "video/mp4",
                "media_kind": "video",
                "duration_seconds": 10,
            }
        )
    )

    assert result["output_valid"] is False
    assert result["status"] == "source_audio_missing"
    assert result["segments"] == []
    assert calls == {"extract": 0, "asr": 0}


def test_asr_router_preserves_deepgram_no_speech_status(monkeypatch):
    async def fake_deepgram(_audio, _content_type):
        return {
            "ok": False,
            "status": "deepgram_empty_transcript",
            "detail": "empty transcript",
        }

    monkeypatch.setattr(bot, "ASR_PROVIDER", "deepgram")
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "fixture-key")
    monkeypatch.setattr(bot, "deepgram_asr_adapter", fake_deepgram)
    monkeypatch.setattr(bot, "save_provider_attempt", lambda *_args, **_kwargs: None)

    result = asyncio.run(bot.asr_transcribe_audio(b"silence", "audio/mpeg"))

    assert result["ok"] is False
    assert result["status"] == "deepgram_empty_transcript"
    assert result["text"] == ""
    assert result["segments"] == []


def test_embedded_subtitle_is_used_before_video_audio_gate(monkeypatch):
    subtitle = "1\n00:00:00,000 --> 00:00:02,000\nHello\n"

    async def fake_embedded(_source, _content_type):
        return subtitle, "embedded-fixture"

    async def transcribe_must_not_run(*_args, **_kwargs):
        raise AssertionError("embedded subtitle must bypass ASR")

    monkeypatch.setattr(bot, "video_dubbing_extract_embedded_subtitle", fake_embedded)
    monkeypatch.setattr(bot, "transcribe_media_to_segments", transcribe_must_not_run)

    result = asyncio.run(
        bot.video_dubbing_resolve_source_script(
            b"silent-video-with-subtitle",
            "video/mp4",
            SimpleNamespace(),
            duration_seconds=10,
        )
    )

    assert result["source_kind"] == "embedded_subtitle"
    assert result["subtitle"] == subtitle
    assert result["script"] == "Hello"


def test_public_asr_engine_skips_silent_chunk_and_reaches_later_speech(monkeypatch):
    async def fake_probe(_payload):
        return {
            "ok": True,
            "has_video": True,
            "has_audio": True,
            "duration": 60.0,
            "width": 1080,
            "height": 1920,
        }

    async def fake_extract(_source, _content_type, start, _duration):
        return f"chunk-{int(start)}".encode(), "audio/mpeg", "fixture"

    async def fake_asr(audio, _content_type, **_kwargs):
        if audio == b"chunk-0":
            return {
                "ok": False,
                "status": "deepgram_empty_transcript",
                "text": "",
                "segments": [],
            }
        return {
            "ok": True,
            "status": "PASS",
            "provider": "fixture-asr",
            "text": "Speech after silence",
            "segments": [
                {"index": 1, "start": 1.0, "end": 3.0, "text": "Speech after silence"}
            ],
            "language": "en",
        }

    monkeypatch.setattr(bot, "subdub_probe_video_bytes", fake_probe)
    monkeypatch.setattr(
        bot,
        "subdub_long_video_chunk_plan",
        lambda _duration: {
            "chunking_enabled": True,
            "chunk_count": 2,
            "chunk_ranges": [
                {"index": 1, "start": 0.0, "end": 30.0},
                {"index": 2, "start": 30.0, "end": 60.0},
            ],
        },
    )
    monkeypatch.setattr(bot, "video_dubbing_extract_audio_chunk", fake_extract)
    monkeypatch.setattr(bot, "asr_transcribe_audio", fake_asr)

    result = asyncio.run(
        bot.transcribe_media_to_segments(
            {
                "bytes": b"long-video",
                "content_type": "video/mp4",
                "media_kind": "video",
                "duration_seconds": 60,
            },
            duration_seconds=60,
        )
    )

    assert result["output_valid"] is True
    assert result["status"] == "PASS"
    assert result["skipped_chunk_count"] == 1
    assert result["skipped_chunk_indices"] == [1]
    assert result["speech_chunk_count"] == 1
    assert [(cue["start"], cue["end"]) for cue in result["segments"]] == [(31.0, 33.0)]
    assert result["global_timing_preserved"] is True


def test_public_asr_engine_reports_all_silent_chunks_truthfully(monkeypatch):
    async def fake_probe(_payload):
        return {
            "ok": True,
            "has_video": True,
            "has_audio": True,
            "duration": 60.0,
        }

    async def fake_extract(_source, _content_type, _start, _duration):
        return b"silence", "audio/mpeg", "fixture"

    async def fake_asr(_audio, _content_type, **_kwargs):
        return {
            "ok": False,
            "status": "deepgram_empty_transcript",
            "text": "",
            "segments": [],
        }

    monkeypatch.setattr(bot, "subdub_probe_video_bytes", fake_probe)
    monkeypatch.setattr(
        bot,
        "subdub_long_video_chunk_plan",
        lambda _duration: {
            "chunking_enabled": True,
            "chunk_count": 2,
            "chunk_ranges": [
                {"index": 1, "start": 0.0, "end": 30.0},
                {"index": 2, "start": 30.0, "end": 60.0},
            ],
        },
    )
    monkeypatch.setattr(bot, "video_dubbing_extract_audio_chunk", fake_extract)
    monkeypatch.setattr(bot, "asr_transcribe_audio", fake_asr)

    result = asyncio.run(
        bot.transcribe_media_to_segments(
            {
                "bytes": b"long-silent-video",
                "content_type": "video/mp4",
                "media_kind": "video",
                "duration_seconds": 60,
            },
            duration_seconds=60,
        )
    )

    assert result["output_valid"] is False
    assert result["status"] == "long_media_no_speech"
    assert result["skipped_chunk_count"] == 2
    assert result["skipped_chunk_indices"] == [1, 2]
    assert result["speech_chunk_count"] == 0
    assert result["global_timing_preserved"] is True


def test_terminal_failure_sends_replacement_when_panel_edit_fails(monkeypatch):
    job_key = "991001|991001|terminal-panel-fixture"
    bot.SUBTITLE_DUB_PIPELINE_JOBS[job_key] = {
        "job_key": job_key,
        "job_id": "fixture-job",
        "user_id": 991001,
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "status": "processing",
        "terminal_state": "",
        "progress_stage": "transcribing",
        "progress_percent": 35,
        "status_panel_message_id": "3501",
    }
    monkeypatch.setattr(bot, "persist_subtitle_dub_pipeline_job_snapshot", lambda *_args, **_kwargs: None)

    class Message:
        chat_id = 991001

        async def reply_text(self, _text, **_kwargs):
            return SimpleNamespace(message_id=3599, chat_id=self.chat_id)

    class Query:
        message = Message()

        async def edit_message_text(self, _text, **_kwargs):
            raise RuntimeError("stored panel cannot be edited")

    try:
        result = asyncio.run(
            bot.send_subdub_fail_once(
                Query(),
                job_key,
                mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
                reason="deepgram_http_503",
                terminalize_active=True,
            )
        )
        job = bot.SUBTITLE_DUB_PIPELINE_JOBS[job_key]

        assert result["sent"] is True
        assert job["terminal_state"] == "failed_no_charge"
        assert job["status_panel_terminalized"] is True
        assert job["status_panel_terminal_edit_confirmed"] is True
        assert job["status_panel_terminal_edit_method"] == "replacement_status_message"
        assert job["status_panel_replacement_sent"] is True
        assert job["panel_final_message_id"] == "3599"
        assert job["refresh_stopped_after_terminal"] is True
    finally:
        bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(job_key, None)


def test_terminal_failure_does_not_claim_panel_success_when_all_sends_fail(monkeypatch):
    job_key = "991002|991002|terminal-panel-send-fails"
    bot.SUBTITLE_DUB_PIPELINE_JOBS[job_key] = {
        "job_key": job_key,
        "job_id": "fixture-job-fail",
        "user_id": 991002,
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "status": "processing",
        "terminal_state": "",
        "progress_stage": "transcribing",
        "progress_percent": 35,
        "status_panel_message_id": "3502",
    }
    monkeypatch.setattr(bot, "persist_subtitle_dub_pipeline_job_snapshot", lambda *_args, **_kwargs: None)

    class Message:
        chat_id = 991002

        async def reply_text(self, _text, **_kwargs):
            raise RuntimeError("replacement send failed")

    class Query:
        message = Message()

        async def edit_message_text(self, _text, **_kwargs):
            raise RuntimeError("stored panel cannot be edited")

    try:
        result = asyncio.run(
            bot.send_subdub_fail_once(
                Query(),
                job_key,
                mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
                reason="deepgram_http_503",
                terminalize_active=True,
            )
        )
        job = bot.SUBTITLE_DUB_PIPELINE_JOBS[job_key]

        assert result["sent"] is False
        assert job["terminal_state"] == "failed_no_charge"
        assert job["status_panel_terminalized"] is False
        assert job["status_panel_terminal_edit_confirmed"] is False
        assert job["status_panel_terminal_edit_failed"] is True
        assert job["terminal_public_outcome_sent"] is False
        assert job["terminal_public_outcome_type"] == ""
        assert job["refresh_stopped_after_terminal"] is True
    finally:
        bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(job_key, None)
