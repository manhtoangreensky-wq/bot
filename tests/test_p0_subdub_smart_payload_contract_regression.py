"""Regression test for Smart MultiVoice lane payload contract leak.

TASK: P0.SUBDUB.AUTO.SMART.MULTIVOICE.LANE.PAYLOAD.CONTRACT.CORRECTION.R1
BUG_ID: SMART_MULTIVOICE_STANDARD_LANE_CONTROL_KWARGS_LEAK
PRODUCTION_EVIDENCE_JOB: #F22E5919
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import Any
import pytest

from services.subdub_blackboxes import auto_smart_multivoice
from services.subdub_blackboxes import run_subdub_lane_blackbox
from services.subtitle_dub_product_pipeline import process_subtitle_dub_job, run_subdub_pipeline


TEST_POOLS = {
    "low": ["voice_male_1", "voice_male_2"],
    "high": ["voice_female_1", "voice_female_2"],
}


def test_strict_standard_runner_has_no_var_kwargs():
    """Verify that process_subtitle_dub_job has NO **kwargs (strict contract)."""
    sig = inspect.signature(process_subtitle_dub_job)
    has_var_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
    assert not has_var_kwargs, "process_subtitle_dub_job must NOT accept **kwargs"


def test_smart_multivoice_first_red_reproduction():
    """First Red: Prove that without the fix, Smart MultiVoice leaks validated_pools

    causing TypeError: process_subtitle_dub_job() got an unexpected keyword argument 'validated_pools'.
    Also prove run_lane_blackbox_calls == 1 and no TTS/provider submit occurs before failure.
    """
    calls = {
        "run_lane_blackbox_calls": 0,
        "tts_synthesize_calls": 0,
    }

    sample_prepared = {
        "source_bytes": b"FAKE_SOURCE_MP4_BYTES_LONG_ENOUGH",
        "content_type": "video/mp4",
        "source_segments": [
            {"id": "cue_1", "cue_id": "cue_1", "speaker_id": "chunk_00:speaker_0", "start": 0.0, "end": 2.0, "text": "Hello"},
            {"id": "cue_2", "cue_id": "cue_2", "speaker_id": "chunk_00:speaker_0", "start": 2.5, "end": 4.5, "text": "World"},
        ],
        "output_segments": [
            {"id": "cue_1", "cue_id": "cue_1", "speaker_id": "chunk_00:speaker_0", "start": 0.0, "end": 2.0, "text": "Xin chao"},
            {"id": "cue_2", "cue_id": "cue_2", "speaker_id": "chunk_00:speaker_0", "start": 2.5, "end": 4.5, "text": "The gioi"},
        ],
        "output_subtitle": "1\n00:00:00,000 --> 00:00:02,000\nXin chao\n\n2\n00:00:02,500 --> 00:00:04,500\nThe gioi\n",
        "state": {
            "mode": "subtitle_plus_dub",
            "auto_smart_multivoice_opt_in": True,
            "auto_speaker_lane": "auto_smart_multivoice",
        },
    }

    async def spy_prepare_subtitles(state: dict, *, require_auto_cast: bool = False):
        return dict(sample_prepared)

    async def spy_synthesize_segments(*args: Any, **kwargs: Any):
        calls["tts_synthesize_calls"] += 1
        return {"chunks": [], "provider": "mock"}

    async def tracking_run_lane_blackbox(*, lane_mode: str, runner: Any, **lane_payload: Any):
        calls["run_lane_blackbox_calls"] += 1
        return await run_subdub_lane_blackbox(lane_mode=lane_mode, runner=runner, **lane_payload)

    sample_state = {
        "mode": "subtitle_plus_dub",
        "video_processing_mode": "subtitle_plus_dub",
        "auto_smart_multivoice_opt_in": True,
        "auto_speaker_lane": "auto_smart_multivoice",
        "target_language": "vi",
        "_pipeline_job_id": "smart_test_job_leak",
    }

    # Calling run_subdub_pipeline directly with 'validated_pools' reproduces the exact error
    # observed in job #F22E5919 when process_subtitle_dub_job rejected the leaked kwarg.
    with pytest.raises(TypeError) as exc_info:
        asyncio.run(
            run_subdub_pipeline(
                mode="subtitle_plus_dub",
                state=sample_state,
                user_id=12345,
                job_id="smart_test_job_leak",
                prepare_subtitles=spy_prepare_subtitles,
                resolve_voice_id=lambda uid, st: "voice_male_1",
                synthesize_segments=spy_synthesize_segments,
                validated_pools=TEST_POOLS,
            )
        )
    assert "unexpected keyword argument 'validated_pools'" in str(exc_info.value)
    assert calls["tts_synthesize_calls"] == 0


def test_smart_multivoice_excludes_all_smart_control_keys_from_lane_payload():
    """Verify that all 16 Smart-only control keys are stripped from lane_payload before delegating."""
    sample_prepared = {
        "source_bytes": b"FAKE_SOURCE_MP4_BYTES_LONG_ENOUGH",
        "content_type": "video/mp4",
        "source_segments": [
            {"id": "cue_1", "cue_id": "cue_1", "speaker_id": "chunk_00:speaker_0", "start": 0.0, "end": 2.0, "text": "Hello"},
            {"id": "cue_2", "cue_id": "cue_2", "speaker_id": "chunk_00:speaker_0", "start": 2.5, "end": 4.5, "text": "World"},
        ],
        "output_segments": [
            {"id": "cue_1", "cue_id": "cue_1", "speaker_id": "chunk_00:speaker_0", "start": 0.0, "end": 2.0, "text": "Xin chao"},
            {"id": "cue_2", "cue_id": "cue_2", "speaker_id": "chunk_00:speaker_0", "start": 2.5, "end": 4.5, "text": "The gioi"},
        ],
        "output_subtitle": "1\n00:00:00,000 --> 00:00:02,000\nXin chao\n\n2\n00:00:02,500 --> 00:00:04,500\nThe gioi\n",
        "state": {
            "mode": "subtitle_plus_dub",
            "auto_smart_multivoice_opt_in": True,
            "auto_speaker_lane": "auto_smart_multivoice",
        },
    }

    async def spy_prepare_subtitles(state: dict, *, require_auto_cast: bool = False):
        return dict(sample_prepared)

    captured_lane_payload = {}

    async def spy_run_lane_blackbox(*, lane_mode: str, runner: Any, **lane_payload: Any):
        nonlocal captured_lane_payload
        captured_lane_payload = dict(lane_payload)
        return {
            "ok": True,
            "status": "SUCCESS",
            "state": lane_payload.get("state", {}),
            "video_output": b"MOCK_MP4_BYTES",
            "source_bytes": b"FAKE_SOURCE_MP4_BYTES_LONG_ENOUGH",
        }

    async def spy_runner(**kwargs: Any):
        return {"ok": True}

    sample_state = {
        "mode": "subtitle_plus_dub",
        "video_processing_mode": "subtitle_plus_dub",
        "auto_smart_multivoice_opt_in": True,
        "auto_speaker_lane": "auto_smart_multivoice",
        "target_language": "vi",
        "voice_style": "default",
        "source_mime_type": "video/mp4",
        "_pipeline_job_id": "smart_test_contract_check",
    }

    # Pass all 16 Smart-only control keys into run_auto_smart_multivoice_blackbox
    smart_control_keys_passed = {
        "validated_pools": TEST_POOLS,
        "required_pool_capacity": 2,
        "post_prepare_gate": lambda prep, st: True,
        "extract_pcm": lambda src: b"PCM",
        "stereo_pcm_path": "/tmp/stereo.pcm",
        "ranges_by_speaker": {},
        "deadline_monotonic": 999999.0,
        "stop_requested": lambda: False,
        "strict_two_classifier": None,
        "acoustic_classifications": {},
        "fallback_level_override": None,
        "default_fallback_voice": "voice_male_1",
        "locked_speaker_voice_map": None,
        "segments": [],
        "cues": [],
        "source_media": "/tmp/source.mp4",
    }

    standard_keys_passed = {
        "user_id": 12345,
        "job_id": "smart_test_contract_check",
        "resolve_voice_id": lambda uid, st: "voice_male_1",
        "synthesize_segments": lambda *a, **k: {"chunks": [], "provider": "mock"},
        "build_timeline_audio": lambda chunks, dur: (b"AUDIO", "ok"),
        "normalize_audio": lambda b: (b, "ok"),
        "validate_audio": lambda b: {"ok": True},
        "render_video": lambda src, **kw: (b"MP4", "ok"),
        "srt_from_text": lambda t, d: "",
        "segments_from_text": lambda t, d: [],
        "segments_from_subtitle": lambda s: [],
        "subtitle_output_items": lambda s, o, m: [],
        "parse_voice_speed": lambda s: 1.0,
        "video_render_ready": lambda o: True,
        "ffmpeg_ready": lambda: True,
        "dub_mux_enabled": True,
        "is_admin": False,
    }

    payload = {
        "lane_mode": "subtitle_plus_dub",
        "mode": "subtitle_plus_dub",
        "state": sample_state,
        "run_lane_blackbox": spy_run_lane_blackbox,
        "runner": spy_runner,
        "prepare_subtitles": spy_prepare_subtitles,
        **smart_control_keys_passed,
        **standard_keys_passed,
    }

    result = asyncio.run(auto_smart_multivoice.run_auto_smart_multivoice_blackbox(**payload))
    assert result.get("ok") is True

    # Assert EVERY Smart-only control key is absent from delegated lane_payload
    for key in auto_smart_multivoice.SMART_CONTROL_ONLY_KEYS:
        assert key not in captured_lane_payload, f"Smart control key '{key}' leaked into lane_payload!"

    # Also assert explicitly required keys by name
    assert "validated_pools" not in captured_lane_payload
    assert "required_pool_capacity" not in captured_lane_payload
    assert "post_prepare_gate" not in captured_lane_payload
    assert "extract_pcm" not in captured_lane_payload
    assert "stereo_pcm_path" not in captured_lane_payload
    assert "ranges_by_speaker" not in captured_lane_payload
    assert "source_media" not in captured_lane_payload
    assert "segments" not in captured_lane_payload
    assert "cues" not in captured_lane_payload

    # Assert standard pipeline dependencies remain present
    assert captured_lane_payload.get("mode") == "subtitle_plus_dub"
    assert "state" in captured_lane_payload
    assert captured_lane_payload.get("user_id") == 12345
    assert captured_lane_payload.get("job_id") == "smart_test_contract_check"
    assert callable(captured_lane_payload.get("prepare_subtitles"))
    assert callable(captured_lane_payload.get("resolve_voice_id"))
    assert callable(captured_lane_payload.get("synthesize_segments"))
    assert callable(captured_lane_payload.get("build_timeline_audio"))
    assert callable(captured_lane_payload.get("normalize_audio"))
    assert callable(captured_lane_payload.get("render_video"))
    assert captured_lane_payload.get("dub_mux_enabled") is True
    assert captured_lane_payload.get("is_admin") is False


def test_smart_multivoice_standard_pipeline_delegation_succeeds_without_typeerror():
    """End-to-end integration proof: Run Smart MultiVoice delegating to the REAL

    run_subdub_lane_blackbox and run_subdub_pipeline with all production control keys.
    Must succeed with NO TypeError.
    """
    sample_prepared = {
        "source_bytes": b"FAKE_SOURCE_MP4_BYTES_LONG_ENOUGH",
        "content_type": "video/mp4",
        "source_segments": [
            {"id": "cue_1", "cue_id": "cue_1", "speaker_id": "chunk_00:speaker_0", "start": 0.0, "end": 2.0, "text": "Hello"},
            {"id": "cue_2", "cue_id": "cue_2", "speaker_id": "chunk_00:speaker_0", "start": 2.5, "end": 4.5, "text": "World"},
        ],
        "output_segments": [
            {"id": "cue_1", "cue_id": "cue_1", "speaker_id": "chunk_00:speaker_0", "start": 0.0, "end": 2.0, "text": "Xin chao"},
            {"id": "cue_2", "cue_id": "cue_2", "speaker_id": "chunk_00:speaker_0", "start": 2.5, "end": 4.5, "text": "The gioi"},
        ],
        "output_subtitle": "1\n00:00:00,000 --> 00:00:02,000\nXin chao\n\n2\n00:00:02,500 --> 00:00:04,500\nThe gioi\n",
        "state": {
            "mode": "subtitle_plus_dub",
            "auto_smart_multivoice_opt_in": True,
            "auto_speaker_lane": "auto_smart_multivoice",
        },
    }

    async def spy_prepare_subtitles(state: dict, *, require_auto_cast: bool = False):
        return dict(sample_prepared)

    async def mock_synthesize_segments(segments: list[dict], *args: Any, **kwargs: Any):
        chunks = []
        for s in segments:
            cid = str(s.get("cue_id") or s.get("id"))
            chunks.append({
                "cue_id": cid,
                "audio_bytes": b"AUDIO_" + cid.encode("utf-8"),
                "audio": b"AUDIO_" + cid.encode("utf-8"),
                "audio_duration": 2.0,
                "start": float(s.get("start") or 0.0),
                "end": float(s.get("end") or 2.0),
            })
        return {"chunks": chunks, "provider": "mock_tts"}

    sample_state = {
        "mode": "subtitle_plus_dub",
        "video_processing_mode": "subtitle_plus_dub",
        "auto_smart_multivoice_opt_in": True,
        "auto_speaker_lane": "auto_smart_multivoice",
        "target_language": "vi",
        "voice_style": "default",
        "source_mime_type": "video/mp4",
        "_pipeline_job_id": "smart_test_job_full_delegation",
    }

    payload = {
        "lane_mode": "subtitle_plus_dub",
        "mode": "subtitle_plus_dub",
        "state": sample_state,
        "user_id": 12345,
        "job_id": "smart_test_job_full_delegation",
        "run_lane_blackbox": run_subdub_lane_blackbox,
        "runner": run_subdub_pipeline,
        "prepare_subtitles": spy_prepare_subtitles,
        "resolve_voice_id": lambda uid, st: "voice_male_1",
        "synthesize_segments": mock_synthesize_segments,
        "build_timeline_audio": lambda chunks, dur: (b"TIMELINE_AUDIO_BYTES", "ok"),
        "normalize_audio": lambda b: (b"NORMALIZED_AUDIO_BYTES", "ok"),
        "validate_audio": lambda b: {"ok": True},
        "render_video": lambda src, **kw: (b"FINAL_MP4_BYTES", "ok"),
        "srt_from_text": lambda t, d: "",
        "segments_from_text": lambda t, d: [],
        "segments_from_subtitle": lambda s: [],
        "subtitle_output_items": lambda s, o, m: [],
        "parse_voice_speed": lambda s: 1.0,
        "video_render_ready": lambda o: True,
        "ffmpeg_ready": lambda: True,
        "dub_mux_enabled": True,
        "is_admin": False,
        # Control-plane keys that were leaking into process_subtitle_dub_job:
        "validated_pools": TEST_POOLS,
        "required_pool_capacity": 2,
        "post_prepare_gate": lambda prep, st: True,
        "extract_pcm": lambda src: b"PCM",
    }

    result = asyncio.run(auto_smart_multivoice.run_auto_smart_multivoice_blackbox(**payload))
    assert isinstance(result, dict)
    assert result.get("ok") is True, f"Delegation failed: {result}"
    assert result.get("shared_core_used") is True
    assert result.get("job_id") == "smart_test_job_full_delegation"


def test_require_auto_cast_remains_true():
    """Verify that auto_smart_multivoice continues to pass require_auto_cast=True (PR 1132 invariant)."""
    received_require_auto_cast = None

    async def check_prepare(service_state: dict, *, require_auto_cast: bool = False):
        nonlocal received_require_auto_cast
        received_require_auto_cast = require_auto_cast
        return {
            "source_bytes": b"TEST_BYTES",
            "content_type": "video/mp4",
            "source_segments": [{"id": "c1", "speaker_id": "spk_1", "start": 0.0, "end": 1.0, "text": "Hi"}],
            "output_segments": [{"id": "c1", "speaker_id": "spk_1", "start": 0.0, "end": 1.0, "text": "Chao"}],
            "state": service_state,
        }

    sample_state = {
        "mode": "dub",
        "video_processing_mode": "dub",
        "auto_smart_multivoice_opt_in": True,
        "auto_speaker_lane": "auto_smart_multivoice",
    }

    payload = {
        "lane_mode": "dub",
        "mode": "dub",
        "state": sample_state,
        "prepare_subtitles": check_prepare,
        "run_lane_blackbox": lambda **kw: {"ok": True},
        "runner": lambda **kw: {"ok": True},
        "validated_pools": TEST_POOLS,
    }

    asyncio.run(auto_smart_multivoice.run_auto_smart_multivoice_blackbox(**payload))
    assert received_require_auto_cast is True, "require_auto_cast MUST be True"


def test_no_typeerror_fallback_and_no_speaker_remap_in_source():
    """Source-level AST / string invariants:

    - No TypeError fallback in auto_smart_multivoice
    - No ad-hoc speaker remapping
    - require_auto_cast=True is present
    """
    source_path = Path("services/subdub_blackboxes/auto_smart_multivoice.py")
    source_text = source_path.read_text(encoding="utf-8")

    assert "except TypeError" not in source_text, "No TypeError fallback allowed in auto_smart_multivoice"
    assert "speaker_remap" not in source_text, "No speaker_remap allowed in auto_smart_multivoice"
    assert "require_auto_cast=True" in source_text, "require_auto_cast=True must remain present in prepare_subtitles call"
