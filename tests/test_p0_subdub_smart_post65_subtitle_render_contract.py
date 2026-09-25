"""Regression test suite for Smart MultiVoice post-65 subtitle/render contract.

TASK: P0.SUBDUB.AUTO.SMART.MULTIVOICE.POST65.RENDER.SUBTITLE.CONTRACT.REGRESSION.R1
PROGRAM: P0.SUBDUB
"""

import asyncio
import base64
import os
from pathlib import Path
import tempfile
from typing import Any
import pytest

from services import subdub_tts_checkpoint
from services.subdub_blackboxes import auto_smart_multivoice as smart

SAMPLE_VALID_MP3 = base64.b64decode(
    "SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjYyLjEyLjEwMQAAAAAAAAAAAAAA//sQxAAABHQTVVSQgDCmCa83GiACAAGtOUAAAVk6PVBQCAYJAfB8HwfKAgCAYRB8H9QIOxOH+INwBJP2wGA4HA4AAAAAACiJKpkUZAjpAkgWo/eFAfATG/AilC+oGhL8JA0qCgAYMAD/+xLEAoPFWB0gHeAAKKSDpIK8AAXMCQC8QASGAOB4Z+72pmMDlmHEESYMAH5gQgYGBSBMYF4DxZq0lflI8wEwETAAA2MDYIQzblDTLrF3ML8H0wWQHTALAtMCUB8wIwG0T59JA5JIAAr/+xDEAoAEtENSuZKAEJcGpuuYMARhEdKhTBbpmtFc+iKq+RLMu79/N5ZP4GFfx4sXwMd+FVAMXYXAAAAmEoRic8ySQagdXkkSQpUtPJRJFBQFYxhTvEt0qC3EqkxBTUUzLjEwMKqqqg=="
)

TEST_POOLS = {
    "low": ["English_magnetic_voiced_man", "English_MaturePartner"],
    "high": ["English_Whispering_girl", "English_radiant_girl"],
}

VALID_SRT_TEXT = (
    "1\n"
    "00:00:01,000 --> 00:00:03,000\n"
    "Xin chào các bạn.\n\n"
    "2\n"
    "00:00:04,000 --> 00:00:06,000\n"
    "Hẹn gặp lại.\n\n"
)


MOCK_ACOUSTIC = {
    "spk_0": {"voice_register": "low", "confidence": 1.0},
    "spk_1": {"voice_register": "low", "confidence": 1.0},
    "spk_2": {"voice_register": "high", "confidence": 1.0},
}


def _sync(fn):
    def wrapper():
        return asyncio.run(fn())
    wrapper.__name__ = fn.__name__
    return wrapper


@_sync
async def test_case_1_subtitle_plus_dub_receives_nonempty_subtitle_bytes():
    """CASE 1: In subtitle_plus_dub mode, renderer must receive non-empty subtitle_bytes."""
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        render_received = {}
        ws = str(tmp_path / "ws_case1")

        dummy_source = tmp_path / "source.mp4"
        dummy_source.write_bytes(b"DUMMY_MP4_HEADER_BYTES_FOR_TESTING" * 50)

        async def fake_render_video(src_bytes: bytes, dubbed_audio: bytes = b"", subtitle_bytes: bytes = b"", **kw):
            render_received["subtitle_bytes"] = subtitle_bytes
            render_received["dubbed_audio"] = dubbed_audio
            return (b"RENDERED_VIDEO_WITH_SUBTITLES", "success")

        async def fake_build_timeline_audio(tts_chunks: list, duration: float):
            return SAMPLE_VALID_MP3, {"duration": duration}

        async def fake_synthesize(cues, *args, **kwargs):
            return {
                "chunks": [
                    {"cue_id": c.get("cue_id", "c1"), "audio": SAMPLE_VALID_MP3, "audio_bytes": SAMPLE_VALID_MP3, "audio_duration": 2.0}
                    for c in cues
                ],
                "provider": "key4u_mock",
            }

        cues = [
            {"cue_id": "c1", "speaker_id": "spk_1", "text": "Xin chào các bạn.", "start": 1.0, "end": 3.0, "start_ms": 1000, "end_ms": 3000},
            {"cue_id": "c2", "speaker_id": "spk_2", "text": "Hẹn gặp lại.", "start": 4.0, "end": 6.0, "start_ms": 4000, "end_ms": 6000},
        ]

        async def fake_prepare(st: dict, *, require_auto_cast: bool = False):
            return {
                "source_bytes": dummy_source.read_bytes(),
                "source_file": str(dummy_source),
                "output_subtitle": VALID_SRT_TEXT,
                "output_script": "Xin chào các bạn. Hẹn gặp lại.",
                "output_segments": cues,
                "content_type": "video/mp4",
            }

        state = {
            "mode": "subtitle_plus_dub",
            "video_processing_mode": "subtitle_plus_dub",
            "auto_smart_multivoice_opt_in": True,
            "auto_speaker_lane": "auto_smart_multivoice",
            "source": str(dummy_source),
            "source_bytes": dummy_source.read_bytes(),
            "input_duration": 10.0,
            "video_duration": 10.0,
            "_pipeline_job_id": "job_case1",
            "_pipeline_workspace": ws,
        }

        payload = {
            "lane_mode": "subtitle_plus_dub",
            "state": state,
            "job_id": "job_case1",
            "checkpoint_workspace": ws,
            "prepare_subtitles": fake_prepare,
            "synthesize_segments": fake_synthesize,
            "render_video": fake_render_video,
            "build_timeline_audio": fake_build_timeline_audio,
            "validated_pools": TEST_POOLS,
            "segments": cues,
            "acoustic_classifications": MOCK_ACOUSTIC,
        }

        result = await smart.run_auto_smart_multivoice_blackbox(**payload)

        assert result.get("ok") is True, f"Expected ok=True, got {result}"
        # FIRST RED: before patch, subtitle_bytes is hardcoded to b""
        assert render_received.get("subtitle_bytes") != b"", "RENDER_RECEIVED_SUBTITLE_BYTES was empty (expected non-empty SRT bytes)"
        assert VALID_SRT_TEXT.encode("utf-8") in render_received["subtitle_bytes"] or render_received["subtitle_bytes"] == VALID_SRT_TEXT.encode("utf-8")


@_sync
async def test_case_2_canonical_response_contract_fields_present():
    """CASE 2: Successful Smart result must expose canonical response fields to avoid outer delivery failure."""
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        import bot
        ws = str(tmp_path / "ws_case2")
        dummy_source = tmp_path / "source.mp4"
        dummy_source.write_bytes(b"DUMMY_MP4_HEADER_BYTES_FOR_TESTING" * 50)

        async def fake_render_video(src_bytes: bytes, dubbed_audio: bytes = b"", subtitle_bytes: bytes = b"", **kw):
            return (b"RENDERED_VIDEO_BYTES", "success")

        async def fake_build_timeline_audio(tts_chunks: list, duration: float):
            return SAMPLE_VALID_MP3, {"duration": duration}

        async def fake_synthesize(cues, *args, **kwargs):
            return {
                "chunks": [{"cue_id": "c1", "audio": SAMPLE_VALID_MP3, "audio_bytes": SAMPLE_VALID_MP3, "audio_duration": 2.0}],
                "provider": "key4u_mock",
            }

        cues = [{"cue_id": "c1", "speaker_id": "spk_1", "text": "Xin chào các bạn.", "start": 1.0, "end": 3.0, "start_ms": 1000, "end_ms": 3000}]

        async def fake_prepare(st: dict, *, require_auto_cast: bool = False):
            return {
                "source_bytes": dummy_source.read_bytes(),
                "source_file": str(dummy_source),
                "output_subtitle": VALID_SRT_TEXT,
                "output_script": "Xin chào các bạn.",
                "output_segments": cues,
                "content_type": "video/mp4",
            }

        state = {
            "mode": "subtitle_plus_dub",
            "auto_smart_multivoice_opt_in": True,
            "auto_speaker_lane": "auto_smart_multivoice",
            "source": str(dummy_source),
            "source_bytes": dummy_source.read_bytes(),
            "input_duration": 10.0,
            "video_duration": 10.0,
            "_pipeline_job_id": "job_case2",
            "_pipeline_workspace": ws,
        }

        payload = {
            "lane_mode": "subtitle_plus_dub",
            "state": state,
            "job_id": "job_case2",
            "checkpoint_workspace": ws,
            "prepare_subtitles": fake_prepare,
            "synthesize_segments": fake_synthesize,
            "render_video": fake_render_video,
            "build_timeline_audio": fake_build_timeline_audio,
            "validated_pools": TEST_POOLS,
            "segments": cues,
            "acoustic_classifications": MOCK_ACOUSTIC,
        }

        result = await smart.run_auto_smart_multivoice_blackbox(**payload)

        assert result.get("ok") is True

        # FIRST RED: before patch, these canonical fields are missing from response
        assert result.get("prepared") is not None, "result['prepared'] missing"
        assert result.get("output_subtitle") == VALID_SRT_TEXT, "result['output_subtitle'] missing/empty"
        assert result.get("output_text") == "Xin chào các bạn.", "result['output_text'] missing/empty"
        assert result.get("output_segments") == cues, "result['output_segments'] missing/empty"
        assert result.get("srt_text") == VALID_SRT_TEXT, "result['srt_text'] missing/empty"
        assert result.get("srt_bytes") == VALID_SRT_TEXT.encode("utf-8"), "result['srt_bytes'] missing/empty"

        # Outer bot delivery validator check: MUST PASS
        sub_val = bot.subdub_validate_subtitle_text_for_delivery(result.get("srt_text") or result.get("output_subtitle") or "")
        assert sub_val.get("ok") is True, f"Outer validation failed: {sub_val}"


@_sync
async def test_case_3_timeline_duration_dynamic_parity():
    """CASE 3: Timeline duration passed to build_timeline_audio must NOT be hardcoded to 5.0."""
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        ws = str(tmp_path / "ws_case3")
        dummy_source = tmp_path / "source.mp4"
        dummy_source.write_bytes(b"DUMMY_MP4_HEADER_BYTES_FOR_TESTING" * 50)

        captured_timeline_durations = []

        async def fake_render_video(src_bytes: bytes, dubbed_audio: bytes = b"", subtitle_bytes: bytes = b"", **kw):
            return (b"RENDERED_VIDEO_BYTES", "success")

        async def fake_build_timeline_audio(tts_chunks: list, duration: float):
            captured_timeline_durations.append(duration)
            return SAMPLE_VALID_MP3, {"duration": duration}

        async def fake_synthesize(cues, *args, **kwargs):
            return {
                "chunks": [{"cue_id": "c1", "audio": SAMPLE_VALID_MP3, "audio_bytes": SAMPLE_VALID_MP3, "audio_duration": 2.0}],
                "provider": "key4u_mock",
            }

        cues = [{"cue_id": "c1", "speaker_id": "spk_1", "text": "Hi", "start": 10.0, "end": 14.5, "start_ms": 10000, "end_ms": 14500}]

        async def fake_prepare(st: dict, *, require_auto_cast: bool = False):
            return {
                "source_bytes": dummy_source.read_bytes(),
                "source_file": str(dummy_source),
                "output_subtitle": "1\n00:00:10,000 --> 00:00:14,500\nHi\n\n",
                "output_script": "Hi",
                "output_segments": cues,
                "content_type": "video/mp4",
            }

        # Video duration is 25.0 seconds
        state = {
            "mode": "dub",
            "auto_smart_multivoice_opt_in": True,
            "auto_speaker_lane": "auto_smart_multivoice",
            "source": str(dummy_source),
            "source_bytes": dummy_source.read_bytes(),
            "input_duration": 25.0,
            "video_duration": 25.0,
            "_pipeline_job_id": "job_case3",
            "_pipeline_workspace": ws,
        }

        payload = {
            "lane_mode": "dub",
            "state": state,
            "job_id": "job_case3",
            "checkpoint_workspace": ws,
            "prepare_subtitles": fake_prepare,
            "synthesize_segments": fake_synthesize,
            "render_video": fake_render_video,
            "build_timeline_audio": fake_build_timeline_audio,
            "validated_pools": TEST_POOLS,
            "segments": cues,
            "acoustic_classifications": MOCK_ACOUSTIC,
        }

        result = await smart.run_auto_smart_multivoice_blackbox(**payload)
        assert result.get("ok") is True

        assert len(captured_timeline_durations) == 1
        # FIRST RED: before patch, duration passed is hardcoded 5.0
        assert captured_timeline_durations[0] > 5.0, f"TIMELINE_DURATION_ARGUMENT was hardcoded {captured_timeline_durations[0]} (expected >= 14.5 or 25.0)"
        assert captured_timeline_durations[0] >= 14.5


@_sync
async def test_case_4_pure_dub_mode_keeps_subtitle_bytes_empty():
    """Pure dub mode must NOT burn subtitles into video (subtitle_bytes == b'')."""
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        render_received = {}
        ws = str(tmp_path / "ws_case4")
        dummy_source = tmp_path / "source.mp4"
        dummy_source.write_bytes(b"DUMMY_MP4_HEADER_BYTES_FOR_TESTING" * 50)

        async def fake_render_video(src_bytes: bytes, dubbed_audio: bytes = b"", subtitle_bytes: bytes = b"", **kw):
            render_received["subtitle_bytes"] = subtitle_bytes
            return (b"RENDERED_VIDEO_BYTES", "success")

        async def fake_build_timeline_audio(tts_chunks: list, duration: float):
            return SAMPLE_VALID_MP3, {"duration": duration}

        async def fake_synthesize(cues, *args, **kwargs):
            return {
                "chunks": [{"cue_id": "c1", "audio": SAMPLE_VALID_MP3, "audio_bytes": SAMPLE_VALID_MP3, "audio_duration": 2.0}],
                "provider": "key4u_mock",
            }

        cues = [{"cue_id": "c1", "speaker_id": "spk_1", "text": "Hi", "start": 0.0, "end": 2.0, "start_ms": 0, "end_ms": 2000}]

        async def fake_prepare(st: dict, *, require_auto_cast: bool = False):
            return {
                "source_bytes": dummy_source.read_bytes(),
                "source_file": str(dummy_source),
                "output_subtitle": VALID_SRT_TEXT,
                "output_script": "Hi",
                "output_segments": cues,
                "content_type": "video/mp4",
            }

        state = {
            "mode": "dub",
            "auto_smart_multivoice_opt_in": True,
            "auto_speaker_lane": "auto_smart_multivoice",
            "source": str(dummy_source),
            "source_bytes": dummy_source.read_bytes(),
            "input_duration": 5.0,
            "_pipeline_job_id": "job_case4",
            "_pipeline_workspace": ws,
        }

        payload = {
            "lane_mode": "dub",
            "state": state,
            "job_id": "job_case4",
            "checkpoint_workspace": ws,
            "prepare_subtitles": fake_prepare,
            "synthesize_segments": fake_synthesize,
            "render_video": fake_render_video,
            "build_timeline_audio": fake_build_timeline_audio,
            "validated_pools": TEST_POOLS,
            "segments": cues,
            "acoustic_classifications": MOCK_ACOUSTIC,
        }

        result = await smart.run_auto_smart_multivoice_blackbox(**payload)
        assert result.get("ok") is True
        assert render_received.get("subtitle_bytes") == b"", "Pure dub must not burn subtitles into video"


def _format_srt_timestamp(seconds_float: float) -> str:
    total_ms = int(round(seconds_float * 1000))
    hours = total_ms // 3600000
    rem = total_ms % 3600000
    minutes = rem // 60000
    rem = rem % 60000
    seconds = rem // 1000
    millis = rem % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


@_sync
async def test_case_5_incident_shape_77_cue_checkpoint_reuse_and_render():
    """Section I: 77-cue incident-shape checkpoint reuse with 0 provider calls and valid post-65 render."""
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        ws = str(tmp_path / "ws_77_cues")
        dummy_source = tmp_path / "source.mp4"
        dummy_source.write_bytes(b"DUMMY_MP4_HEADER_BYTES_FOR_TESTING" * 50)

        # 1. Pre-populate 77 cues in checkpoint
        total_cues = 77
        cues = []
        lines = []
        for i in range(total_cues):
            start_s = i * 2.0
            end_s = start_s + 1.8
            cid = f"cue_{i+1:04d}"
            cues.append({
                "cue_id": cid,
                "speaker_id": f"spk_{i % 3}",
                "text": f"Câu thoại thử nghiệm số {i+1}.",
                "start": start_s,
                "end": end_s,
                "start_ms": int(start_s * 1000),
                "end_ms": int(end_s * 1000),
            })
            lines.append(f"{i+1}\n{_format_srt_timestamp(start_s)} --> {_format_srt_timestamp(end_s)}\nCâu thoại thử nghiệm số {i+1}.\n")

        full_srt = "\n".join(lines) + "\n"

        # Verify incident timestamps roll correctly past minute boundary
        assert "00:01:00,000" in full_srt, "Timestamp must roll past minute boundary (not 00:00:60,000)"
        assert "00:00:60,000" not in full_srt, "Malformed minute timestamp detected"

        mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
            workspace=ws,
            job_id="job_77_incident",
            target_language="vi",
            quote_fingerprint="quote_77",
        )

        speaker_voices = {
            "spk_0": "English_magnetic_voiced_man",
            "spk_1": "English_MaturePartner",
            "spk_2": "English_Whispering_girl",
        }
        for cue in cues:
            voice_id = speaker_voices[cue["speaker_id"]]
            mgr.record_cue_success(
                cue,
                voice_id,
                audio_bytes=SAMPLE_VALID_MP3,
                duration=1.8,
                provider_label="mock_key4u",
            )

        provider_calls = 0

        async def fail_if_called_synth(*args, **kwargs):
            nonlocal provider_calls
            provider_calls += 1
            raise RuntimeError("Provider call forbidden when checkpoint is pre-populated")

        render_call_count = 0
        render_received_subtitles = []

        async def fake_render_video(src_bytes: bytes, dubbed_audio: bytes = b"", subtitle_bytes: bytes = b"", **kw):
            nonlocal render_call_count
            render_call_count += 1
            render_received_subtitles.append(subtitle_bytes)
            return (b"RENDERED_77_CUE_VIDEO", "success")

        captured_timeline_durations = []

        async def fake_build_timeline_audio(tts_chunks: list, duration: float):
            captured_timeline_durations.append(duration)
            return SAMPLE_VALID_MP3, {"duration": duration}

        async def fake_prepare(st: dict, *, require_auto_cast: bool = False):
            return {
                "source_bytes": dummy_source.read_bytes(),
                "source_file": str(dummy_source),
                "output_subtitle": full_srt,
                "output_script": " ".join([c["text"] for c in cues]),
                "output_segments": cues,
                "content_type": "video/mp4",
            }

        total_duration = total_cues * 2.0 + 5.0
        state = {
            "mode": "subtitle_plus_dub",
            "auto_smart_multivoice_opt_in": True,
            "auto_speaker_lane": "auto_smart_multivoice",
            "source": str(dummy_source),
            "source_bytes": dummy_source.read_bytes(),
            "input_duration": total_duration,
            "video_duration": total_duration,
            "_pipeline_job_id": "job_77_incident",
            "_pipeline_workspace": ws,
        }

        payload = {
            "lane_mode": "subtitle_plus_dub",
            "state": state,
            "job_id": "job_77_incident",
            "checkpoint_workspace": ws,
            "checkpoint_manager": mgr,
            "prepare_subtitles": fake_prepare,
            "synthesize_segments": fail_if_called_synth,
            "render_video": fake_render_video,
            "build_timeline_audio": fake_build_timeline_audio,
            "validated_pools": TEST_POOLS,
            "segments": cues,
            "acoustic_classifications": MOCK_ACOUSTIC,
            "locked_speaker_voice_map": speaker_voices,
        }

        result = await smart.run_auto_smart_multivoice_blackbox(**payload)

        assert provider_calls == 0, f"Expected 0 provider calls, got {provider_calls}"
        assert result.get("ok") is True, f"Expected result.ok=True, got {result}"
        assert render_call_count == 1, f"Expected render_call_count=1, got {render_call_count}"
        assert b"RENDERED_77_CUE_VIDEO" in result.get("video_output")
        assert result.get("srt_text") == full_srt
        assert render_received_subtitles[0] != b"", "Render received empty subtitle_bytes on 77-cue incident resume"


@_sync
async def test_case_6_plain_output_text_materializes_valid_srt():
    """CASE 6: When output_subtitle is empty but output_script is plain text,
    canonical SRT containing '-->' must be materialized and passed to renderer.
    """
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        render_received = {}
        ws = str(tmp_path / "ws_case6")
        dummy_source = tmp_path / "source.mp4"
        dummy_source.write_bytes(b"DUMMY_MP4_HEADER_BYTES_FOR_TESTING" * 50)

        async def fake_render_video(src_bytes: bytes, dubbed_audio: bytes = b"", subtitle_bytes: bytes = b"", **kw):
            render_received["subtitle_bytes"] = subtitle_bytes
            render_received["dubbed_audio"] = dubbed_audio
            return (b"RENDERED_VIDEO_WITH_SUBTITLES", "success")

        async def fake_build_timeline_audio(tts_chunks: list, duration: float):
            return SAMPLE_VALID_MP3, {"duration": duration}

        async def fake_synthesize(cues, *args, **kwargs):
            return {
                "chunks": [{"cue_id": "c1", "audio": SAMPLE_VALID_MP3, "audio_bytes": SAMPLE_VALID_MP3, "audio_duration": 2.0}],
                "provider": "key4u_mock",
            }

        cues = [{"cue_id": "c1", "speaker_id": "spk_1", "text": "Xin chào", "start": 1.0, "end": 3.0, "start_ms": 1000, "end_ms": 3000}]

        async def fake_prepare(st: dict, *, require_auto_cast: bool = False):
            return {
                "source_bytes": dummy_source.read_bytes(),
                "source_file": str(dummy_source),
                "output_subtitle": "",  # Empty subtitle
                "output_script": "Xin chào",  # Plain text script
                "output_segments": cues,
                "content_type": "video/mp4",
            }

        state = {
            "mode": "subtitle_plus_dub",
            "video_processing_mode": "subtitle_plus_dub",
            "auto_smart_multivoice_opt_in": True,
            "auto_speaker_lane": "auto_smart_multivoice",
            "source": str(dummy_source),
            "source_bytes": dummy_source.read_bytes(),
            "input_duration": 10.0,
            "video_duration": 10.0,
            "_pipeline_job_id": "job_case6",
            "_pipeline_workspace": ws,
        }

        payload = {
            "lane_mode": "subtitle_plus_dub",
            "state": state,
            "job_id": "job_case6",
            "checkpoint_workspace": ws,
            "prepare_subtitles": fake_prepare,
            "synthesize_segments": fake_synthesize,
            "render_video": fake_render_video,
            "build_timeline_audio": fake_build_timeline_audio,
            "validated_pools": TEST_POOLS,
            "segments": cues,
            "acoustic_classifications": MOCK_ACOUSTIC,
        }

        result = await smart.run_auto_smart_multivoice_blackbox(**payload)

        assert result.get("ok") is True, f"Expected ok=True, got {result}"
        assert "-->" in result.get("srt_text", ""), "SRT_TEXT does not contain '-->'"
        assert b"-->" in render_received.get("subtitle_bytes", b""), "RENDER_SUBTITLE_BYTES does not contain b'-->'"


@_sync
async def test_case_7_input_duration_seconds_authority():
    """CASE 7: prepared['state']['input_duration_seconds'] = 30.0 must take authority over latest cue end = 14.5."""
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        ws = str(tmp_path / "ws_case7")
        dummy_source = tmp_path / "source.mp4"
        dummy_source.write_bytes(b"DUMMY_MP4_HEADER_BYTES_FOR_TESTING" * 50)

        captured_timeline_durations = []

        async def fake_render_video(src_bytes: bytes, dubbed_audio: bytes = b"", subtitle_bytes: bytes = b"", **kw):
            return (b"RENDERED_VIDEO_BYTES", "success")

        async def fake_build_timeline_audio(tts_chunks: list, duration: float):
            captured_timeline_durations.append(duration)
            return SAMPLE_VALID_MP3, {"duration": duration}

        async def fake_synthesize(cues, *args, **kwargs):
            return {
                "chunks": [{"cue_id": "c1", "audio": SAMPLE_VALID_MP3, "audio_bytes": SAMPLE_VALID_MP3, "audio_duration": 2.0}],
                "provider": "key4u_mock",
            }

        cues = [{"cue_id": "c1", "speaker_id": "spk_1", "text": "Hi", "start": 10.0, "end": 14.5, "start_ms": 10000, "end_ms": 14500}]

        async def fake_prepare(st: dict, *, require_auto_cast: bool = False):
            return {
                "source_bytes": dummy_source.read_bytes(),
                "source_file": str(dummy_source),
                "output_subtitle": "1\n00:00:10,000 --> 00:00:14,500\nHi\n\n",
                "output_script": "Hi",
                "output_segments": cues,
                "content_type": "video/mp4",
                "state": {
                    "input_duration_seconds": 30.0,
                    "mode": "dub",
                },
            }

        state = {
            "mode": "dub",
            "auto_smart_multivoice_opt_in": True,
            "auto_speaker_lane": "auto_smart_multivoice",
            "source": str(dummy_source),
            "source_bytes": dummy_source.read_bytes(),
            "input_duration": 10.0,
            "_pipeline_job_id": "job_case7",
            "_pipeline_workspace": ws,
        }

        payload = {
            "lane_mode": "dub",
            "state": state,
            "job_id": "job_case7",
            "checkpoint_workspace": ws,
            "prepare_subtitles": fake_prepare,
            "synthesize_segments": fake_synthesize,
            "render_video": fake_render_video,
            "build_timeline_audio": fake_build_timeline_audio,
            "validated_pools": TEST_POOLS,
            "segments": cues,
            "acoustic_classifications": MOCK_ACOUSTIC,
        }

        result = await smart.run_auto_smart_multivoice_blackbox(**payload)
        assert result.get("ok") is True

        assert len(captured_timeline_durations) == 1
        assert captured_timeline_durations[0] == 30.0, f"Expected timeline duration 30.0, got {captured_timeline_durations[0]}"


@_sync
async def test_case_8_render_policy_parity():
    """CASE 8: Verify keep_original_audio and target_duration_seconds propagation,
    and subtitle_bytes parity (non-empty for subtitle_plus_dub, empty for dub).
    """
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        dummy_source = tmp_path / "source.mp4"
        dummy_source.write_bytes(b"DUMMY_MP4_HEADER_BYTES_FOR_TESTING" * 50)

        cues = [{"cue_id": "c1", "speaker_id": "spk_1", "text": "Hi", "start": 0.0, "end": 2.0, "start_ms": 0, "end_ms": 2000}]

        async def fake_build_timeline_audio(tts_chunks: list, duration: float):
            return SAMPLE_VALID_MP3, {"duration": duration}

        async def fake_synthesize(cues, *args, **kwargs):
            return {
                "chunks": [{"cue_id": "c1", "audio": SAMPLE_VALID_MP3, "audio_bytes": SAMPLE_VALID_MP3, "audio_duration": 2.0}],
                "provider": "key4u_mock",
            }

        # 1. subtitle_plus_dub with keep_original_audio=True
        render_captured_subdub = {}

        async def fake_render_subdub(src_bytes: bytes, dubbed_audio: bytes = b"", subtitle_bytes: bytes = b"", **kw):
            render_captured_subdub.update(kw)
            render_captured_subdub["subtitle_bytes"] = subtitle_bytes
            render_captured_subdub["dubbed_audio"] = dubbed_audio
            return (b"RENDERED_SUBDUB_MP4", "success")

        async def fake_prepare_subdub(st: dict, *, require_auto_cast: bool = False):
            return {
                "source_bytes": dummy_source.read_bytes(),
                "source_file": str(dummy_source),
                "output_subtitle": VALID_SRT_TEXT,
                "output_script": "Hi",
                "output_segments": cues,
                "content_type": "video/mp4",
                "keep_original_audio": True,
                "state": {
                    "input_duration_seconds": 12.0,
                    "keep_original_audio": True,
                },
            }

        res_subdub = await smart.run_auto_smart_multivoice_blackbox(
            lane_mode="subtitle_plus_dub",
            state={
                "mode": "subtitle_plus_dub",
                "auto_smart_multivoice_opt_in": True,
                "auto_speaker_lane": "auto_smart_multivoice",
                "source": str(dummy_source),
                "source_bytes": dummy_source.read_bytes(),
                "keep_original_audio": True,
                "_pipeline_job_id": "job_case8_subdub",
                "_pipeline_workspace": str(tmp_path / "ws_subdub"),
            },
            job_id="job_case8_subdub",
            checkpoint_workspace=str(tmp_path / "ws_subdub"),
            prepare_subtitles=fake_prepare_subdub,
            synthesize_segments=fake_synthesize,
            render_video=fake_render_subdub,
            build_timeline_audio=fake_build_timeline_audio,
            validated_pools=TEST_POOLS,
            segments=cues,
            acoustic_classifications=MOCK_ACOUSTIC,
        )
        assert res_subdub.get("ok") is True
        assert render_captured_subdub.get("keep_original_audio") is True
        assert render_captured_subdub.get("target_duration_seconds") == 12.0
        assert render_captured_subdub.get("subtitle_bytes") != b""

        # 2. pure dub with keep_original_audio=False
        render_captured_dub = {}

        async def fake_render_dub(src_bytes: bytes, dubbed_audio: bytes = b"", subtitle_bytes: bytes = b"", **kw):
            render_captured_dub.update(kw)
            render_captured_dub["subtitle_bytes"] = subtitle_bytes
            render_captured_dub["dubbed_audio"] = dubbed_audio
            return (b"RENDERED_DUB_MP4", "success")

        async def fake_prepare_dub(st: dict, *, require_auto_cast: bool = False):
            return {
                "source_bytes": dummy_source.read_bytes(),
                "source_file": str(dummy_source),
                "output_subtitle": VALID_SRT_TEXT,
                "output_script": "Hi",
                "output_segments": cues,
                "content_type": "video/mp4",
                "keep_original_audio": False,
                "state": {
                    "input_duration_seconds": 15.0,
                    "keep_original_audio": False,
                },
            }

        res_dub = await smart.run_auto_smart_multivoice_blackbox(
            lane_mode="dub",
            state={
                "mode": "dub",
                "auto_smart_multivoice_opt_in": True,
                "auto_speaker_lane": "auto_smart_multivoice",
                "source": str(dummy_source),
                "source_bytes": dummy_source.read_bytes(),
                "keep_original_audio": False,
                "_pipeline_job_id": "job_case8_dub",
                "_pipeline_workspace": str(tmp_path / "ws_dub"),
            },
            job_id="job_case8_dub",
            checkpoint_workspace=str(tmp_path / "ws_dub"),
            prepare_subtitles=fake_prepare_dub,
            synthesize_segments=fake_synthesize,
            render_video=fake_render_dub,
            build_timeline_audio=fake_build_timeline_audio,
            validated_pools=TEST_POOLS,
            segments=cues,
            acoustic_classifications=MOCK_ACOUSTIC,
        )
        assert res_dub.get("ok") is True
        assert render_captured_dub.get("keep_original_audio") is False
        assert render_captured_dub.get("target_duration_seconds") == 15.0
        assert render_captured_dub.get("subtitle_bytes") == b""

