import asyncio
import math
import subprocess
from array import array
from pathlib import Path
from types import SimpleNamespace

import pytest

import bot
from services import subtitle_dub_product_pipeline


def test_translated_cue_keeps_source_text_for_speech_rate_measurement():
    policy = subtitle_dub_product_pipeline.resolve_subdub_dub_audio_policy(
        {"target_language": "English", "translate_requested": True},
        {
            "source_segments": [
                {"cue_id": "cue-1", "index": 1, "start": 1.0, "end": 3.0, "text": "Đi ngay"}
            ],
            "output_segments": [
                {"cue_id": "cue-1", "index": 1, "start": 1.0, "end": 3.0, "text": "Please go right now"}
            ],
        },
    )

    cue = policy["tts_segments"][0]
    assert cue["source_text"] == "Đi ngay"
    assert cue["text"] == "Please go right now"
    assert (cue["start"], cue["end"]) == (1.0, 3.0)


def test_tts_measures_source_and_translation_rates_before_generation(monkeypatch):
    requested_speeds = []

    async def tts(_text, _voice_style, _voice_id, speed, **_kwargs):
        requested_speeds.append(float(speed))
        return "fixture-tts", b"real-audio-bytes", "ok"

    async def qc(*_args, **_kwargs):
        return {
            "ok": True,
            "detail": "speech_activity_ok",
            "duration": 3.6,
            "leading_silence_seconds": 0.0,
            "trailing_silence_seconds": 0.0,
            "non_silent_seconds": 3.6,
        }

    monkeypatch.setattr(bot, "video_dubbing_tts_bytes", tts)
    monkeypatch.setattr(bot, "subdub_validate_tts_audio_bytes", qc)

    result = asyncio.run(
        bot.synthesize_dub_segment_chunks(
            [
                {
                    "cue_id": "cue-1",
                    "index": 1,
                    "start": 0.0,
                    "end": 2.0,
                    "source_text": "go now",
                    "text": "please go right now",
                }
            ],
            voice_id="fixture-voice",
            base_speed=1.0,
            max_speed=1.8,
            allow_admin=True,
            require_speech_qc=True,
            cue_locked_timing=True,
        )
    )

    chunk = result["chunks"][0]
    assert requested_speeds == [1.8]
    assert chunk["cue_window_seconds"] == pytest.approx(2.0)
    assert chunk["source_text_units"] == 2
    assert chunk["translated_text_units"] == 4
    assert chunk["source_speech_rate"] == pytest.approx(1.0)
    assert chunk["required_target_speech_rate"] == pytest.approx(2.0)
    assert chunk["generated_audio_seconds"] == pytest.approx(3.6)


def test_cue_locked_plan_fits_each_measured_cue_without_cumulative_drift():
    plan = bot.subdub_plan_dub_timeline(
        [
            {
                "cue_id": "cue-1",
                "start": 0.0,
                "end": 2.0,
                "source_text": "go now",
                "text": "please go right now",
                "audio_duration": 4.0,
                "cue_locked_timing": True,
            },
            {
                "cue_id": "cue-2",
                "start": 2.0,
                "end": 4.0,
                "source_text": "stay here",
                "text": "please remain right here",
                "audio_duration": 3.0,
                "cue_locked_timing": True,
            },
        ],
        4.0,
    )

    assert plan["ok"] is True
    assert plan["timeline_duration"] == pytest.approx(4.0)
    assert plan["timeline_extended"] is False
    assert plan["shifted_cue_count"] == 0
    first, second = plan["scheduled"]
    assert (first["scheduled_start"], first["scheduled_end"]) == pytest.approx((0.0, 2.0))
    assert (second["scheduled_start"], second["scheduled_end"]) == pytest.approx((2.0, 4.0))
    assert first["fit_ratio"] == pytest.approx(2.0)
    assert second["fit_ratio"] == pytest.approx(1.5)
    assert first["post_fit_audio_seconds"] <= first["cue_window_seconds"] + 0.001
    assert second["post_fit_audio_seconds"] <= second["cue_window_seconds"] + 0.001
    assert first["drift_seconds"] == pytest.approx(0.0)
    assert second["drift_seconds"] == pytest.approx(0.0)


def _tone(ffmpeg: str, path: Path, frequency: int, duration: float) -> bytes:
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:sample_rate=32000:duration={duration}",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path.read_bytes()


def _pcm_window_rms(samples: array, start: float, end: float, sample_rate: int = 32000) -> float:
    left = max(0, int(round(start * sample_rate)))
    right = min(len(samples), int(round(end * sample_rate)))
    window = samples[left:right]
    return math.sqrt(sum(float(value) ** 2 for value in window) / max(1, len(window)))


def test_real_ffmpeg_timeline_is_source_bounded_after_per_cue_fit(tmp_path):
    ffmpeg = bot.frame_video_ffmpeg_path()
    if not ffmpeg:
        pytest.skip("ffmpeg unavailable")
    first = _tone(ffmpeg, tmp_path / "first.mp3", 440, 2.4)
    second = _tone(ffmpeg, tmp_path / "second.mp3", 880, 1.8)

    audio, detail = asyncio.run(
        bot.build_dub_timeline_audio(
            [
                {
                    "cue_id": "cue-1",
                    "start": 0.0,
                    "end": 0.8,
                    "audio_duration": 2.4,
                    "audio_bytes": first,
                    "cue_locked_timing": True,
                },
                {
                    "cue_id": "cue-2",
                    "start": 1.4,
                    "end": 2.2,
                    "audio_duration": 1.8,
                    "audio_bytes": second,
                    "cue_locked_timing": True,
                },
            ],
            3.0,
        )
    )
    output = tmp_path / "cue-locked.mp3"
    output.write_bytes(audio)
    decoded = subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-i",
            str(output),
            "-ac",
            "1",
            "-ar",
            "32000",
            "-f",
            "s16le",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
    ).stdout
    samples = array("h")
    samples.frombytes(decoded)
    qc = asyncio.run(bot.subdub_validate_tts_timeline_audio_bytes(audio))
    first_rms = _pcm_window_rms(samples, 0.20, 0.60)
    second_rms = _pcm_window_rms(samples, 1.60, 2.00)

    assert audio
    assert "cue_locked=yes" in detail
    assert "shifted_cues=0" in detail
    assert qc["ok"] is True
    assert qc["duration"] == pytest.approx(3.0, abs=0.08)
    assert first_rms > 0
    assert second_rms > 0
    assert first_rms / second_rms == pytest.approx(1.0, abs=0.20)


def test_auto_product_pipeline_enables_meter_and_keeps_source_duration():
    calls = {}

    async def prepare(state):
        return {
            "state": state,
            "source_bytes": b"source-video",
            "content_type": "video/mp4",
            "source_segments": [
                {"cue_id": "cue-1", "index": 1, "start": 0.0, "end": 2.0, "text": "go now"}
            ],
            "output_segments": [
                {
                    "cue_id": "cue-1",
                    "index": 1,
                    "start": 0.0,
                    "end": 2.0,
                    "source_text": "go now",
                    "text": "please go right now",
                }
            ],
            "output_script": "please go right now",
            "output_subtitle": "1\n00:00:00,000 --> 00:00:02,000\nplease go right now\n",
        }

    async def synthesize(segments, **kwargs):
        calls["synthesize"] = dict(kwargs)
        return {
            "provider": "fixture-tts",
            "chunks": [
                {
                    **segments[0],
                    "audio_bytes": b"spoken",
                    "audio_duration": 3.6,
                    "source_speech_window_seconds": 2.0,
                    "speech_rate_basis": "asr_cue_timestamps",
                    "source_text_units": 2,
                    "translated_text_units": 4,
                    "source_speech_rate": 1.0,
                    "required_target_speech_rate": 2.0,
                }
            ],
        }

    async def timeline(chunks, duration):
        calls["timeline"] = (chunks, duration)
        return b"cue-locked-audio", "cue_locked=yes;shifted_cues=0"

    async def normalize(audio):
        return audio, "normalized"

    async def validate_audio(_audio):
        return {"ok": True, "detail": "speech_activity_ok", "duration": 2.0}

    async def render(_source, **kwargs):
        calls["render"] = dict(kwargs)
        return b"final-mp4", "rendered"

    result = asyncio.run(
        subtitle_dub_product_pipeline.process_subtitle_dub_job(
            mode="subtitle_plus_dub",
            state={
                "video_duration": 2.0,
                "output_type": "video_subtitle",
                "target_language": "English",
                "translate_requested": True,
                "voice_kind": "auto_speaker_gender",
                "voice_selection_mode": "auto_speaker",
            },
            user_id=42,
            prepare_subtitles=prepare,
            srt_from_text=bot.video_dubbing_srt_from_text,
            segments_from_text=bot.video_dubbing_segments_from_text,
            segments_from_subtitle=bot.video_dubbing_segments_from_subtitle,
            subtitle_output_items=bot.video_dubbing_subtitle_output_items,
            resolve_voice_id=lambda *_args: "fixture-voice",
            parse_voice_speed=lambda *_args: 1.0,
            synthesize_segments=synthesize,
            build_timeline_audio=timeline,
            normalize_audio=normalize,
            validate_audio=validate_audio,
            render_video=render,
            video_render_ready=lambda *_args: True,
            ffmpeg_ready=lambda: True,
            dub_mux_enabled=True,
        )
    )

    assert calls["synthesize"]["cue_locked_timing"] is True
    assert calls["synthesize"]["max_speed"] == pytest.approx(1.8)
    assert calls["timeline"][1] == pytest.approx(2.0)
    assert calls["render"]["target_duration_seconds"] == pytest.approx(2.0)
    assert result["cue_locked_timing"] is True
    assert result["final_video_expected_duration"] == pytest.approx(2.0)
    assert result["speech_rate_cue_count"] == 1
    assert result["speech_rate_max_fit_ratio"] == pytest.approx(1.8)
    assert result["speech_rate_max_drift_seconds"] == pytest.approx(0.0)
    assert result["speech_rate_measurements"][0]["speech_rate_basis"] == "asr_cue_timestamps"


@pytest.mark.parametrize("mode", ["dub", "subtitle_plus_dub"])
def test_successful_dub_video_auto_delivery_sends_only_mp4(monkeypatch, mode):
    job_key = f"video-only-{mode}"
    events = []

    class Message:
        async def reply_document(self, **_kwargs):
            events.append("document")
            raise AssertionError("successful dub video must not auto-send a document")

        async def reply_audio(self, **_kwargs):
            events.append("audio")
            raise AssertionError("successful dub video must not auto-send audio")

    async def deliver_video(*_args, **_kwargs):
        events.append("video")
        return {
            "sent": True,
            "delivery_method": "video",
            "telegram_message_id": "901",
            "file_id": "video-file-901",
            "file_size_mb": 1.0,
            "size_limit_used": 500.0,
        }

    monkeypatch.setattr(
        bot,
        "SUBTITLE_DUB_PIPELINE_JOBS",
        {
            job_key: {
                "job_key": job_key,
                "mode": mode,
                "voice_kind": "auto_speaker_gender",
                "voice_selection_mode": "auto_speaker",
                "status": "running",
            }
        },
    )
    monkeypatch.setattr(bot, "send_generated_video_bytes_for_delivery", deliver_video)
    monkeypatch.setattr(bot, "update_subtitle_dub_pipeline_job", lambda *_args, **_kwargs: {})

    result = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            Message(),
            mode=mode,
            active_flow=mode,
            requested_mode=mode,
            subtitle_items=[
                {
                    "output_type": "srt",
                    "filename": "internal-only.srt",
                    "bytes": b"1\n00:00:00,000 --> 00:00:01,000\nHello\n",
                }
            ],
            srt_text="1\n00:00:00,000 --> 00:00:01,000\nHello\n",
            audio_bytes=b"internal-dub-audio",
            video_bytes=b"mp4-bytes",
            include_subtitle_outputs=True,
            job_key=job_key,
        )
    )

    assert events == ["video"]
    assert result["final_mp4_delivered"] is True
    assert result["documents"] == 0
    assert result["audio"] == 0
    assert result["srt_delivery_message_id"] == ""
    assert result["srt_auto_send_suppressed"] is True
    assert result["explicit_srt_download_available"] is True


@pytest.mark.parametrize("mode", ["dub", "subtitle_plus_dub"])
def test_multi_speaker_delivery_sends_only_mp4(monkeypatch, mode):
    job_key = f"multi-video-only-{mode}"
    events = []

    class Message:
        async def reply_document(self, **_kwargs):
            events.append("srt")
            raise AssertionError("successful multi video must not auto-send SRT")

    async def deliver_video(*_args, **_kwargs):
        events.append("video")
        return {
            "sent": True,
            "delivery_method": "video",
            "telegram_message_id": "901",
            "file_id": "video-file-901",
            "file_size_mb": 1.0,
            "size_limit_used": 500.0,
        }

    monkeypatch.setattr(
        bot,
        "SUBTITLE_DUB_PIPELINE_JOBS",
        {
            job_key: {
                "job_key": job_key,
                "mode": mode,
                "voice_kind": "auto_speaker_gender",
                "voice_selection_mode": "auto_speaker",
                "auto_speaker_lane": "multi",
                "status": "running",
            }
        },
    )
    monkeypatch.setattr(bot, "send_generated_video_bytes_for_delivery", deliver_video)
    monkeypatch.setattr(bot, "update_subtitle_dub_pipeline_job", lambda *_args, **_kwargs: {})

    result = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            Message(),
            mode=mode,
            active_flow=mode,
            requested_mode=mode,
            subtitle_items=[
                {
                    "output_type": "srt",
                    "filename": "multi.srt",
                    "bytes": b"1\n00:00:00,000 --> 00:00:01,000\nHello\n",
                }
            ],
            srt_text="1\n00:00:00,000 --> 00:00:01,000\nHello\n",
            audio_bytes=b"internal-dub-audio",
            video_bytes=b"mp4-bytes",
            include_subtitle_outputs=True,
            job_key=job_key,
        )
    )

    assert events == ["video"]
    assert result["documents"] == 0
    assert result["audio"] == 0
    assert result["srt_delivery_message_id"] == ""
    assert result["srt_auto_send_suppressed"] is True
    assert result["explicit_srt_download_available"] is True
