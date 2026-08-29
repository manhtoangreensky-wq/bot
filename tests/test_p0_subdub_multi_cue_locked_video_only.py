import asyncio

import pytest

from services import subtitle_dub_product_pipeline


def _srt_from_text(text, _duration):
    return f"1\n00:00:00,000 --> 00:00:02,000\n{text}\n"


def _segments_from_text(text, duration):
    return [{"index": 1, "start": 0.0, "end": float(duration), "text": text}]


def _segments_from_subtitle(_subtitle):
    return []


def _subtitle_output_items(_srt, _output_type, _mode):
    return []


def test_multi_pipeline_reuses_cue_locked_timing_and_source_duration():
    calls = {}

    async def prepare(state):
        return {
            "state": state,
            "source_bytes": b"source-video",
            "content_type": "video/mp4",
            "source_segments": [
                {
                    "cue_id": "cue-1",
                    "index": 1,
                    "start": 0.0,
                    "end": 2.0,
                    "text": "go now",
                    "speaker_id": "speaker_0",
                },
                {
                    "cue_id": "cue-2",
                    "index": 2,
                    "start": 2.5,
                    "end": 3.5,
                    "text": "wait",
                    "speaker_id": "speaker_1",
                },
                {
                    "cue_id": "cue-3",
                    "index": 3,
                    "start": 4.0,
                    "end": 6.0,
                    "text": "yes",
                    "speaker_id": "speaker_2",
                },
            ],
            "output_segments": [
                {
                    "cue_id": "cue-1",
                    "index": 1,
                    "start": 0.0,
                    "end": 2.0,
                    "source_text": "go now",
                    "text": "please go right now",
                    "speaker_id": "speaker_0",
                    "tts_voice_id": "multi-voice-0",
                },
                {
                    "cue_id": "cue-2",
                    "index": 2,
                    "start": 2.5,
                    "end": 3.5,
                    "source_text": "wait",
                    "text": "please wait right there",
                    "speaker_id": "speaker_1",
                    "tts_voice_id": "multi-voice-1",
                },
                {
                    "cue_id": "cue-3",
                    "index": 3,
                    "start": 4.0,
                    "end": 6.0,
                    "source_text": "yes",
                    "text": "yes",
                    "speaker_id": "speaker_2",
                    "tts_voice_id": "multi-voice-2",
                },
            ],
            "output_script": "please go right now\nplease wait right there\nyes",
            "output_subtitle": (
                "1\n00:00:00,000 --> 00:00:02,000\nplease go right now\n\n"
                "2\n00:00:02,500 --> 00:00:03,500\nplease wait right there\n\n"
                "3\n00:00:04,000 --> 00:00:06,000\nyes\n"
            ),
        }

    async def synthesize(segments, **kwargs):
        calls["synthesize"] = dict(kwargs)
        calls["cue_locked"] = bool(kwargs.get("cue_locked_timing"))
        generated_durations = (3.6, 2.4, 0.8)
        return {
            "provider": "fixture-tts",
            "chunks": [
                {
                    **segment,
                    "audio_bytes": b"spoken",
                    "audio_duration": generated_durations[index],
                    "source_speech_window_seconds": (
                        float(segment["end"]) - float(segment["start"])
                    ),
                    "speech_rate_basis": "asr_cue_timestamps",
                    "source_text_units": len(str(segment["source_text"]).split()),
                    "translated_text_units": len(str(segment["text"]).split()),
                    "source_speech_rate": 1.0,
                    "required_target_speech_rate": 2.0,
                }
                for index, segment in enumerate(segments)
            ],
        }

    async def timeline(chunks, duration):
        calls["timeline"] = (chunks, duration)
        return b"timeline-audio", "fixture-timeline"

    async def normalize(audio):
        return audio, "normalized"

    async def validate_audio(_audio):
        return {
            "ok": True,
            "detail": "speech_activity_ok",
            "duration": 6.0 if calls.get("cue_locked") else 6.8,
        }

    async def render(_source, **kwargs):
        calls["render"] = dict(kwargs)
        return b"final-mp4", "rendered"

    result = asyncio.run(
        subtitle_dub_product_pipeline.process_subtitle_dub_job(
            mode="subtitle_plus_dub",
            state={
                "video_duration": 6.0,
                "output_type": "video_subtitle",
                "target_language": "English",
                "translate_requested": True,
                "voice_kind": "auto_speaker_gender",
                "voice_selection_mode": "auto_speaker",
                "auto_speaker_lane": "multi",
            },
            user_id=42,
            prepare_subtitles=prepare,
            srt_from_text=_srt_from_text,
            segments_from_text=_segments_from_text,
            segments_from_subtitle=_segments_from_subtitle,
            subtitle_output_items=_subtitle_output_items,
            resolve_voice_id=lambda *_args: "multi-voice-0",
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
    assert calls["timeline"][1] == pytest.approx(6.0)
    assert calls["render"]["target_duration_seconds"] == pytest.approx(6.0)
    assert result["cue_locked_timing"] is True
    assert result["final_video_expected_duration"] == pytest.approx(6.0)
    assert result["speech_rate_cue_count"] == 3
    assert result["speech_rate_max_drift_seconds"] == pytest.approx(0.0)
    assert [
        (chunk["speaker_id"], chunk["start"], chunk["end"])
        for chunk in result["tts_chunks"]
    ] == [
        ("speaker_0", pytest.approx(0.0), pytest.approx(2.0)),
        ("speaker_1", pytest.approx(2.5), pytest.approx(3.5)),
        ("speaker_2", pytest.approx(4.0), pytest.approx(6.0)),
    ]
