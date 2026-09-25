"""Integration contract test suite for Smart MultiVoice Standard Pipeline Orchestrator.

TASK: P0.SUBDUB.RUNTIME.SMART.MULTIVOICE.STANDARD.PIPELINE.ORCHESTRATOR.LOCAL.R1
PROGRAM: P0.SUBDUB.RUNTIME.RELIABILITY.V1
BUG_ID: SUBDUB_SMART_RENDER_CONTRACT_MISMATCH
"""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path
import tempfile
from typing import Any
import pytest

from services.subdub_blackboxes import auto_smart_multivoice
from services import subdub_blackboxes

SAMPLE_VALID_MP3 = base64.b64decode(
    "SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjYyLjEyLjEwMQAAAAAAAAAAAAAA//sQxAAABHQTVVSQgDCmCa83GiACAAGtOUAAAVk6PVBQCAYJAfB8HwfKAgCAYRB8H9QIOxOH+INwBJP2wGA4HA4AAAAAACiJKpkUZAjpAkgWo/eFAfATG/AilC+oGhL8JA0qCgAYMAD/+xLEAoPFWB0gHeAAKKSDpIK8AAXMCQC8QASGAOB4Z+72pmMDlmHEESYMAH5gQgYGBSBMYF4DxZq0lflI8wEwETAAA2MDYIQzblDTLrF3ML8H0wWQHTALAtMCUB8wIwG0T59JA5JIAAr/+xDEAoAEtENSuZKAEJcGpuuYMARhEdKhTBbpmtFc+iKq+RLMu79/N5ZP4GFfx4sXwMd+FVAMXYXAAAAmEoRic8ySQagdXkkSQpUtPJRJFBQFYxhTvEt0qC3EqkxBTUUzLjEwMKqqqg=="
)

TEST_POOLS = {
    "low": ["voice_male_1", "voice_male_2"],
    "high": ["voice_female_1", "voice_female_2"],
}


def _create_standard_harness():
    spies = {
        "run_lane_blackbox_calls": 0,
        "build_timeline_calls": 0,
        "normalize_audio_calls": 0,
        "validate_audio_calls": 0,
        "standard_render_calls": 0,
        "render_invalid_kwargs": [],
        "tts_submitted_cues": [],
        "tts_used_voices": set(),
    }

    async def strict_render_video(
        source_bytes: bytes,
        dubbed_audio: bytes = b"",
        subtitle_bytes: bytes = b"",
        **kwargs: Any,
    ):
        spies["standard_render_calls"] += 1
        # Check forbidden direct render kwargs
        forbidden = [k for k in ("source_media", "output_path", "tts_chunks") if k in kwargs]
        if forbidden:
            spies["render_invalid_kwargs"].extend(forbidden)
            raise TypeError(
                f"render_video called with forbidden direct Smart kwargs: {forbidden}"
            )
        if not isinstance(source_bytes, (bytes, bytearray)) or not source_bytes:
            raise TypeError("render_video missing required positional argument: 'source_bytes'")
        return b"VALID_FINAL_MP4_BYTES", "ffmpeg_render_ok"

    async def spy_build_timeline_audio(tts_chunks: list[dict], duration: float):
        spies["build_timeline_calls"] += 1
        return b"RAW_TIMELINE_AUDIO_BYTES", "timeline_built_ok"

    async def spy_normalize_audio(raw_audio: bytes):
        spies["normalize_audio_calls"] += 1
        return b"NORMALIZED_AUDIO_BYTES", "normalized_48k_ok"

    async def spy_validate_audio(audio_bytes: bytes):
        spies["validate_audio_calls"] += 1
        return {"ok": True, "duration": 5.0, "detail": "qc_passed"}

    async def spy_synthesize_segments(segments: list[dict] | None = None, *args: Any, **kwargs: Any):
        segs = segments if segments is not None else kwargs.get("cues") or []
        chunks = []
        for seg in segs:
            cid = str(seg.get("cue_id") or seg.get("id"))
            vid = str(seg.get("tts_voice_id") or kwargs.get("voice_id") or "")
            spies["tts_submitted_cues"].append(cid)
            if vid:
                spies["tts_used_voices"].add(vid)
            chunks.append({
                "cue_id": cid,
                "audio_bytes": SAMPLE_VALID_MP3,
                "audio": SAMPLE_VALID_MP3,
                "audio_duration": 2.0,
                "start": float(seg.get("start") or 0.0),
                "end": float(seg.get("end") or 2.0),
            })
        return {"chunks": chunks, "provider": "test_tts"}

    sample_prepared = {
        "source_bytes": b"FAKE_SOURCE_MP4_BYTES_LONG_ENOUGH",
        "content_type": "video/mp4",
        "source_segments": [
            {"id": "cue_1", "cue_id": "cue_1", "speaker_id": "spk_1", "start": 0.0, "end": 2.0, "text": "Hello world"},
            {"id": "cue_2", "cue_id": "cue_2", "speaker_id": "spk_2", "start": 2.5, "end": 4.5, "text": "How are you"},
        ],
        "output_segments": [
            {"id": "cue_1", "cue_id": "cue_1", "speaker_id": "spk_1", "start": 0.0, "end": 2.0, "text": "Xin chào thế giới"},
            {"id": "cue_2", "cue_id": "cue_2", "speaker_id": "spk_2", "start": 2.5, "end": 4.5, "text": "Bạn khỏe không"},
        ],
        "output_subtitle": "1\n00:00:00,000 --> 00:00:02,000\nXin chào\n\n2\n00:00:02,500 --> 00:00:04,500\nKhỏe không\n",
        "state": {
            "mode": "dub",
            "auto_smart_multivoice_opt_in": True,
            "auto_speaker_lane": "auto_smart_multivoice",
        },
    }

    async def spy_prepare_subtitles(state: dict, *, require_auto_cast: bool = False):
        return dict(sample_prepared)

    async def fake_runner(**kwargs: Any) -> dict[str, Any]:
        # Emulates standard subtitle_dub_product_pipeline behavior
        prep_fn = kwargs.get("prepare_subtitles")
        prep = await prep_fn(kwargs.get("state") or {}) if callable(prep_fn) else sample_prepared
        out_segs = prep.get("output_segments") or []

        synth_fn = kwargs.get("synthesize_segments")
        synth_res = await synth_fn(out_segs, voice_id=kwargs.get("resolve_voice_id", lambda *a: "v1")(1, {}))
        chunks = synth_res.get("chunks") if isinstance(synth_res, dict) else synth_res

        build_fn = kwargs.get("build_timeline_audio")
        raw_audio, _ = await build_fn(chunks, 5.0)

        norm_fn = kwargs.get("normalize_audio")
        norm_audio, _ = await norm_fn(raw_audio)

        val_fn = kwargs.get("validate_audio")
        if callable(val_fn):
            await val_fn(norm_audio)

        render_fn = kwargs.get("render_video")
        video_out, _ = await render_fn(
            prep.get("source_bytes"),
            dubbed_audio=norm_audio,
            subtitle_bytes=b"SRT_BYTES",
        )

        return {
            "ok": True,
            "status": "SUCCESS",
            "source_bytes": prep.get("source_bytes"),
            "audio_bytes": norm_audio,
            "video_output": video_out,
            "state": kwargs.get("state") or {},
            "output_segments": out_segs,
        }

    async def spy_run_lane_blackbox(*, lane_mode: str, runner: Any, **lane_payload: Any):
        spies["run_lane_blackbox_calls"] += 1
        return await runner(lane_mode=lane_mode, **lane_payload)

    td = tempfile.mkdtemp(prefix="smart_orch_")
    sample_state = {
        "mode": "dub",
        "video_processing_mode": "dub",
        "auto_smart_multivoice_opt_in": True,
        "auto_speaker_lane": "auto_smart_multivoice",
        "target_language": "vi",
        "_pipeline_job_id": "smart_test_job_1",
        "_pipeline_workspace": td,
        "job_id": "smart_test_job_1",
        "checkpoint_workspace": td,
    }

    return spies, {
        "lane_mode": "dub",
        "run_lane_blackbox": spy_run_lane_blackbox,
        "runner": fake_runner,
        "prepare_subtitles": spy_prepare_subtitles,
        "resolve_voice_id": lambda uid, st: "voice_male_1",
        "synthesize_segments": spy_synthesize_segments,
        "build_timeline_audio": spy_build_timeline_audio,
        "normalize_audio": spy_normalize_audio,
        "validate_audio": spy_validate_audio,
        "render_video": strict_render_video,
        "validated_pools": TEST_POOLS,
        "state": sample_state,
        "mode": "dub",
        "checkpoint_workspace": td,
        "job_id": "smart_test_job_1",
    }


def test_case_a_delegation_to_standard_lane():
    """Case A: Under standalone execution, run_auto_smart_multivoice_blackbox does NOT delegate to run_lane_blackbox."""
    spies, payload = _create_standard_harness()
    result = asyncio.run(auto_smart_multivoice.run_auto_smart_multivoice_blackbox(**payload))

    # STALE_ARCHITECTURE_ASSERTION updated: standalone execution does not delegate to run_lane_blackbox
    assert spies["run_lane_blackbox_calls"] == 0, (
        f"Expected standalone execution without run_lane_blackbox, got {spies['run_lane_blackbox_calls']}"
    )
    assert result.get("ok") is True, f"Expected successful result, got {result}"


def test_case_b_no_direct_render_from_smart(tmp_path):
    """Case B: Smart adapter must NOT call renderer directly with path/chunk arguments."""
    spies, payload = _create_standard_harness()
    fake_source = tmp_path / "source.mp4"
    fake_source.write_bytes(b"FAKE_SOURCE_VIDEO_CONTENT")
    payload["source_media"] = str(fake_source)
    payload["state"]["source_file"] = str(fake_source)
    payload["state"]["_pipeline_saved_source_path"] = str(fake_source)

    result = asyncio.run(auto_smart_multivoice.run_auto_smart_multivoice_blackbox(**payload))

    assert not spies["render_invalid_kwargs"], (
        f"Smart called renderer directly with invalid kwargs: {spies['render_invalid_kwargs']}"
    )
    assert result.get("ok") is True


def test_case_c_standard_audio_seams_reached():
    """Case C: Standard pipeline audio seams must all be reached in order."""
    spies, payload = _create_standard_harness()
    result = asyncio.run(auto_smart_multivoice.run_auto_smart_multivoice_blackbox(**payload))

    assert result.get("ok") is True
    assert spies["build_timeline_calls"] == 1
    assert spies["normalize_audio_calls"] == 1
    assert spies["validate_audio_calls"] >= 1
    assert spies["standard_render_calls"] == 1


def test_case_d_bytes_output_contract():
    """Case D: Successful product result must return bytes for source, audio, and video."""
    spies, payload = _create_standard_harness()
    result = asyncio.run(auto_smart_multivoice.run_auto_smart_multivoice_blackbox(**payload))

    assert result.get("ok") is True
    assert isinstance(result.get("source_bytes"), (bytes, bytearray))
    assert len(result["source_bytes"]) > 0
    assert isinstance(result.get("audio_bytes"), (bytes, bytearray))
    assert len(result["audio_bytes"]) > 0
    assert isinstance(result.get("video_output"), (bytes, bytearray))
    assert len(result["video_output"]) > 0
    assert not isinstance(result.get("video_output"), str), "video_output must NOT be a string path"


def test_case_e_smart_voice_assignment_preserved():
    """Case E: Multi-speaker cues must receive distinct approved voices from Smart decision."""
    spies, payload = _create_standard_harness()
    result = asyncio.run(auto_smart_multivoice.run_auto_smart_multivoice_blackbox(**payload))

    assert result.get("ok") is True
    # spk_1 and spk_2 should have distinct voices assigned from TEST_POOLS
    assert len(spies["tts_used_voices"]) >= 2, (
        f"Expected at least 2 distinct voices for 2 distinct speakers, got {spies['tts_used_voices']}"
    )


def test_case_f_non_speech_preservation():
    """Case F: Preserved music/singing cues must not be sent to TTS synthesis."""
    spies, payload = _create_standard_harness()
    # Add a music cue to prepared output segments
    music_cue = {
        "id": "cue_music_1",
        "cue_id": "cue_music_1",
        "speaker_id": "spk_1",
        "start": 5.0,
        "end": 7.0,
        "text": "[Music - Đàn bầu]",
        "is_music": True,
    }
    speech_cue = {
        "id": "cue_speech_2",
        "cue_id": "cue_speech_2",
        "speaker_id": "spk_2",
        "start": 7.5,
        "end": 9.5,
        "text": "Lời nói bình thường",
    }

    async def prepare_with_music(st: dict, *, require_auto_cast: bool = False):
        return {
            "source_bytes": b"FAKE_SOURCE_MP4_BYTES",
            "content_type": "video/mp4",
            "source_segments": [music_cue, speech_cue],
            "output_segments": [music_cue, speech_cue],
            "output_subtitle": "1\n00:00:05,000 --> 00:00:07,000\n[Music]\n\n2\n00:00:07,500 --> 00:00:09,500\nLời nói\n",
            "state": payload["state"],
        }

    payload["prepare_subtitles"] = prepare_with_music
    result = asyncio.run(auto_smart_multivoice.run_auto_smart_multivoice_blackbox(**payload))

    assert result.get("ok") is True
    # Music cue must NOT be submitted to TTS
    assert "cue_music_1" not in spies["tts_submitted_cues"], (
        "Music/Preserved cue was submitted to TTS synthesis!"
    )
    # Speech cue must be submitted
    assert "cue_speech_2" in spies["tts_submitted_cues"]


def test_case_g_no_manual_fallback_for_speaker_ambiguity():
    """Case G: Smart adapter never drops to AUTO_CAST_MANUAL_REQUIRED for normal speaker ambiguity."""
    spies, payload = _create_standard_harness()
    # 1 speaker cue: Auto-2 or Auto-Multi would fail with AUTO_CAST_MANUAL_REQUIRED. Smart must succeed with single voice.
    single_cue = {
        "id": "cue_single_1",
        "cue_id": "cue_single_1",
        "speaker_id": "spk_1",
        "start": 0.0,
        "end": 2.0,
        "text": "Chỉ có một người nói",
    }

    async def prepare_single(st: dict, *, require_auto_cast: bool = False):
        return {
            "source_bytes": b"FAKE_SOURCE_MP4_BYTES",
            "content_type": "video/mp4",
            "source_segments": [single_cue],
            "output_segments": [single_cue],
            "output_subtitle": "1\n00:00:00,000 --> 00:00:02,000\nChỉ có một người nói\n",
            "state": payload["state"],
        }

    payload["prepare_subtitles"] = prepare_single
    result = asyncio.run(auto_smart_multivoice.run_auto_smart_multivoice_blackbox(**payload))

    assert result.get("status") != "AUTO_CAST_MANUAL_REQUIRED", (
        "Smart dropped to AUTO_CAST_MANUAL_REQUIRED instead of fallback ladder!"
    )
    assert result.get("ok") is True


def test_case_h_missing_standard_wiring_fails_closed():
    """Case H: Under standalone execution, missing run_lane_blackbox/runner is safely permitted."""
    spies, payload = _create_standard_harness()
    payload.pop("run_lane_blackbox", None)
    payload.pop("runner", None)

    # STALE_ARCHITECTURE_ASSERTION updated: standalone execution does not require standard lane wiring
    result = asyncio.run(auto_smart_multivoice.run_auto_smart_multivoice_blackbox(**payload))

    assert result.get("ok") is True
    assert spies["run_lane_blackbox_calls"] == 0


def test_case_i_no_successful_path_string_output():
    """Case I: Successful delegated blackbox output must be bytes, never a str filesystem path."""
    spies, payload = _create_standard_harness()
    result = asyncio.run(auto_smart_multivoice.run_auto_smart_multivoice_blackbox(**payload))

    assert result.get("ok") is True
    assert isinstance(result.get("video_output"), (bytes, bytearray))
    assert not isinstance(result.get("video_output"), str), "video_output must never be string path"
    assert isinstance(result.get("source_bytes"), (bytes, bytearray))
    assert not isinstance(result.get("source_bytes"), str)
    assert isinstance(result.get("audio_bytes"), (bytes, bytearray))
    assert not isinstance(result.get("audio_bytes"), str)


def test_case_j_standard_lane_exactly_once():
    """Case J: Under standalone execution, run_lane_blackbox is 0 and audio/render seams execute."""
    spies, payload = _create_standard_harness()
    result = asyncio.run(auto_smart_multivoice.run_auto_smart_multivoice_blackbox(**payload))

    assert result.get("ok") is True
    # STALE_ARCHITECTURE_ASSERTION updated: standalone execution does not delegate to run_lane_blackbox
    assert spies["run_lane_blackbox_calls"] == 0
    assert spies["standard_render_calls"] == 1
    assert spies["build_timeline_calls"] == 1
    assert spies["normalize_audio_calls"] == 1
    assert spies["validate_audio_calls"] >= 1


def test_case_k_source_path_fix_through_delegated_path(tmp_path):
    """Case K: _pipeline_saved_source_path and _pipeline_source_path_override work under standalone execution."""
    fake_source = tmp_path / "fixture_video.mp4"
    fake_bytes = b"FIXTURE_VIDEO_CONTENT_FOR_SMART_DELEGATION"
    fake_source.write_bytes(fake_bytes)

    spies, payload = _create_standard_harness()
    payload["state"]["_pipeline_saved_source_path"] = str(fake_source)
    payload["state"]["_pipeline_source_path_override"] = str(fake_source)

    # Empty source_bytes in prepare_subtitles to verify fallback to source_media file loading
    async def prepare_without_bytes(st: dict, *, require_auto_cast: bool = False):
        base = await _create_standard_harness()[1]["prepare_subtitles"](st, require_auto_cast=require_auto_cast)
        base.pop("source_bytes", None)
        return base

    payload["prepare_subtitles"] = prepare_without_bytes

    result = asyncio.run(auto_smart_multivoice.run_auto_smart_multivoice_blackbox(**payload))

    assert result.get("ok") is True
    # STALE_ARCHITECTURE_ASSERTION updated: standalone execution does not delegate to run_lane_blackbox
    assert spies["run_lane_blackbox_calls"] == 0
    assert result.get("source_bytes") == fake_bytes


def test_smart_multivoice_lane_payload_contract_strict_runner():
    """Prove Smart MultiVoice delegates clean payload to strict standard runner without kwargs leakage.

    Reproduces production job #F22E5919 where process_subtitle_dub_job rejected 'validated_pools'.
    """
    spies, payload = _create_standard_harness()

    captured_kwargs = {}

    async def strict_standard_runner(
        *,
        mode: str,
        state: dict,
        prepare_subtitles: Any,
        resolve_voice_id: Any,
        synthesize_segments: Any,
        build_timeline_audio: Any = None,
        normalize_audio: Any = None,
        validate_audio: Any = None,
        render_video: Any = None,
        job_id: str = "",
        user_id: int | str = 0,
        srt_from_text: Any = None,
        segments_from_text: Any = None,
        segments_from_subtitle: Any = None,
        subtitle_output_items: Any = None,
        parse_voice_speed: Any = None,
        video_render_ready: Any = None,
        ffmpeg_ready: Any = None,
        dub_mux_enabled: bool = True,
        is_admin: bool = False,
    ) -> dict[str, Any]:
        nonlocal captured_kwargs
        captured_kwargs = {
            "mode": mode,
            "state": state,
            "prepare_subtitles": prepare_subtitles,
            "resolve_voice_id": resolve_voice_id,
            "synthesize_segments": synthesize_segments,
            "build_timeline_audio": build_timeline_audio,
            "normalize_audio": normalize_audio,
            "validate_audio": validate_audio,
            "render_video": render_video,
            "job_id": job_id,
            "user_id": user_id,
            "srt_from_text": srt_from_text,
            "segments_from_text": segments_from_text,
            "segments_from_subtitle": segments_from_subtitle,
            "subtitle_output_items": subtitle_output_items,
            "parse_voice_speed": parse_voice_speed,
            "video_render_ready": video_render_ready,
            "ffmpeg_ready": ffmpeg_ready,
            "dub_mux_enabled": dub_mux_enabled,
            "is_admin": is_admin,
        }
        return {
            "ok": True,
            "status": "SUCCESS",
            "state": state,
            "video_output": b"VALID_FINAL_MP4_BYTES",
            "source_bytes": b"FAKE_SOURCE_MP4_BYTES_LONG_ENOUGH",
            "audio_bytes": b"NORMALIZED_AUDIO_BYTES",
            "output_segments": [],
        }

    async def spy_run_lane_blackbox(*, lane_mode: str, runner: Any, **lane_payload: Any):
        spies["run_lane_blackbox_calls"] += 1
        return await subdub_blackboxes.run_subdub_lane_blackbox(
            lane_mode=lane_mode,
            runner=runner,
            **lane_payload,
        )

    payload["runner"] = strict_standard_runner
    payload["run_lane_blackbox"] = spy_run_lane_blackbox

    # Realistic production kwargs from bot.py
    payload["validated_pools"] = TEST_POOLS
    payload["required_pool_capacity"] = 2
    payload["post_prepare_gate"] = lambda *a, **k: True
    payload["stereo_pcm_path"] = "/tmp/stereo.pcm"
    payload["ranges_by_speaker"] = {}
    payload["deadline_monotonic"] = 999999.0
    payload["stop_requested"] = lambda: False
    payload["strict_two_classifier"] = None
    payload["acoustic_classifications"] = {}
    payload["fallback_level_override"] = None
    payload["default_fallback_voice"] = "voice_male_1"
    payload["locked_speaker_voice_map"] = None
    payload["segments"] = []
    payload["cues"] = []
    payload["source_media"] = "/tmp/media.mp4"

    result = asyncio.run(auto_smart_multivoice.run_auto_smart_multivoice_blackbox(**payload))
    assert result.get("ok") is True

    # STALE_ARCHITECTURE_ASSERTION updated: under standalone execution, Smart executes directly
    # without delegating to standard runner, maintaining clean state and verified flag
    assert spies["run_lane_blackbox_calls"] == 0
    assert result.get("state", {}).get("subdub_engine_selected") == "auto_smart_multivoice"
    assert result.get("auto_smart_verified") is True
    # Verify SMART_CONTROL_ONLY_KEYS filtering invariant remains intact
    assert len(auto_smart_multivoice.SMART_CONTROL_ONLY_KEYS) >= 15

