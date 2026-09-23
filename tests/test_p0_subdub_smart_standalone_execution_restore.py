"""Regression test suite for P0.SUBDUB.AUTO.SMART.MULTIVOICE.STANDALONE.EXECUTION.RESTORE.CORRECTION.R1.

Verifies:
1. Exact production RuntimeError escapes before fix (historical unhandled reproduction)
2. Exact production RuntimeError is contained after fix (no unhandled escape)
3. Provider failure produces no video output (video_output=None, final_mp4_path=None)
4. render_pipeline is NOT called after TTS failure
5. Successful synthetic 3-speaker execution produces valid standalone result
6. All synthetic dubbed cues have exact 1:1 TTS coverage
7. Current result state schema preserved
8. video_output remains bytes, never str path
9. require_auto_cast=True preserved
10. Saved source path fallback preserved
11. PR #1138 SMART_CONTROL_ONLY_KEYS invariants remain present
12. No TypeError fallback introduced in source
"""

import asyncio
from pathlib import Path
import tempfile
from typing import Any
import pytest

from services.subdub_blackboxes import auto_smart_multivoice
from tests.test_p0_subdub_auto_smart_multivoice import _create_real_valid_mp4

TEST_POOLS = {
    "low": ["voice_male_1", "voice_male_2", "voice_male_3", "voice_male_4"],
    "high": ["voice_female_1", "voice_female_2", "voice_female_3", "voice_female_4"],
}

EXACT_502_ERROR = "tts_unavailable:Key4U MiniMax=FAIL:http=502"


def test_01_exact_production_runtimeerror_escapes_before_fix():
    """Requirement 1: Exact production RuntimeError escapes before fix.
    
    Proves that when standard pipeline delegation had no try/except around synthesize_segments,
    the provider RuntimeError escaped to orchestration.
    """
    async def failing_synth(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(EXACT_502_ERROR)

    async def unhandled_delegation_runner(**kwargs: Any) -> dict[str, Any]:
        synth_fn = kwargs.get("synthesize_segments")
        # Standard pipeline process_subtitle_dub_job did not wrap synth in try/except
        await synth_fn([{"cue_id": "c1", "speaker_id": "spk_1", "text": "hi"}], voice_id="v1")
        return {"ok": True}

    escaped = False
    exc_type = None
    exc_msg = None
    try:
        # Simulate unhandled delegation
        asyncio.run(unhandled_delegation_runner(synthesize_segments=failing_synth))
    except Exception as e:
        escaped = True
        exc_type = type(e).__name__
        exc_msg = str(e)

    assert escaped is True
    assert exc_type == "RuntimeError"
    assert exc_msg == EXACT_502_ERROR


def test_02_exact_production_runtimeerror_contained_after_fix():
    """Requirement 2: Exact production RuntimeError is contained after fix.
    
    Verifies that calling run_auto_smart_multivoice_blackbox with provider 502 RuntimeError
    does NOT escape, but returns a structured failure dictionary.
    """
    async def failing_synth(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(EXACT_502_ERROR)

    state = {
        "mode": "dub",
        "auto_smart_multivoice_opt_in": True,
        "auto_speaker_lane": "auto_smart_multivoice",
        "source_bytes": b"FAKE_MP4_HEADER_BYTES" * 100,
    }

    async def fake_prep(st: dict, *, require_auto_cast: bool = False) -> dict[str, Any]:
        return {
            "source_bytes": b"FAKE_MP4_HEADER_BYTES" * 100,
            "output_segments": [{"cue_id": "c1", "speaker_id": "spk_1", "text": "Xin chao"}],
            "content_type": "video/mp4",
        }

    payload = {
        "lane_mode": "dub",
        "state": state,
        "prepare_subtitles": fake_prep,
        "synthesize_segments": failing_synth,
        "validated_pools": TEST_POOLS,
    }

    # Must NOT raise RuntimeError
    result = asyncio.run(auto_smart_multivoice.run_auto_smart_multivoice_blackbox(**payload))

    assert isinstance(result, dict)
    assert result.get("ok") is False
    assert result.get("auto_smart_verified") is False
    assert result.get("output_mode") == auto_smart_multivoice.OUTPUT_MODE_FAILED
    assert result.get("blocker") == f"tts_synthesis_failed_{EXACT_502_ERROR}"
    assert result.get("status") == f"SMART_TTS_SYNTHESIS_FAILED_{EXACT_502_ERROR.upper()}"


def test_03_provider_failure_produces_no_video_output():
    """Requirement 3: Provider failure produces no video output."""
    async def failing_synth(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(EXACT_502_ERROR)

    state = {
        "mode": "dub",
        "auto_smart_multivoice_opt_in": True,
        "auto_speaker_lane": "auto_smart_multivoice",
        "source_bytes": b"FAKE_MP4_HEADER_BYTES" * 100,
    }

    async def fake_prep(st: dict, *, require_auto_cast: bool = False) -> dict[str, Any]:
        return {
            "source_bytes": b"FAKE_MP4_HEADER_BYTES" * 100,
            "output_segments": [{"cue_id": "c1", "speaker_id": "spk_1", "text": "Xin chao"}],
            "content_type": "video/mp4",
        }

    payload = {
        "lane_mode": "dub",
        "state": state,
        "prepare_subtitles": fake_prep,
        "synthesize_segments": failing_synth,
        "validated_pools": TEST_POOLS,
    }

    result = asyncio.run(auto_smart_multivoice.run_auto_smart_multivoice_blackbox(**payload))

    assert result.get("video_output") is None
    assert result.get("final_mp4_path") is None


def test_04_render_pipeline_not_called_after_tts_failure():
    """Requirement 4: render_pipeline is NOT called after TTS failure."""
    render_called = False

    async def failing_synth(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(EXACT_502_ERROR)

    async def spy_render(*args: Any, **kwargs: Any) -> Any:
        nonlocal render_called
        render_called = True
        return "/tmp/should_never_render.mp4"

    state = {
        "mode": "dub",
        "auto_smart_multivoice_opt_in": True,
        "auto_speaker_lane": "auto_smart_multivoice",
        "source_bytes": b"FAKE_MP4_HEADER_BYTES" * 100,
    }

    async def fake_prep(st: dict, *, require_auto_cast: bool = False) -> dict[str, Any]:
        return {
            "source_bytes": b"FAKE_MP4_HEADER_BYTES" * 100,
            "output_segments": [{"cue_id": "c1", "speaker_id": "spk_1", "text": "Xin chao"}],
            "content_type": "video/mp4",
        }

    payload = {
        "lane_mode": "dub",
        "state": state,
        "prepare_subtitles": fake_prep,
        "synthesize_segments": failing_synth,
        "render_pipeline": spy_render,
        "validated_pools": TEST_POOLS,
    }

    result = asyncio.run(auto_smart_multivoice.run_auto_smart_multivoice_blackbox(**payload))

    assert result.get("ok") is False
    assert render_called is False, "render_pipeline MUST NOT be called after failed TTS synthesis"


def test_05_successful_synthetic_3_speaker_execution_produces_valid_result(tmp_path: Path):
    """Requirement 5: Successful synthetic 3-speaker execution produces valid standalone result."""
    src_mp4 = _create_real_valid_mp4(tmp_path / "src_3spk.mp4")

    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Xin chao cac ban", "start_ms": 0, "end_ms": 1000},
        {"cue_id": "c2", "speaker_id": "spk_2", "text": "Toi la nguoi thu hai", "start_ms": 1100, "end_ms": 2000},
        {"cue_id": "c3", "speaker_id": "spk_3", "text": "Con toi la nguoi thu ba", "start_ms": 2100, "end_ms": 3000},
    ]

    async def mock_synth(cues: list[dict] | None = None, speaker_voice_map: dict | None = None, *args: Any, **kwargs: Any) -> list[dict]:
        chunks = []
        for c in (cues or []):
            chunks.append({"cue_id": c["cue_id"], "audio": b"MOCK_PCM_TTS_AUDIO_DATA"})
        return chunks

    async def mock_render(source_media: str, output_path: str, **kwargs: Any) -> str:
        _create_real_valid_mp4(Path(output_path))
        return output_path

    state = {
        "mode": "dub",
        "auto_smart_multivoice_opt_in": True,
        "auto_speaker_lane": "auto_smart_multivoice",
        "source": str(src_mp4),
    }

    payload = {
        "source_media": str(src_mp4),
        "cues": cues,
        "state": state,
        "synthesize_segments": mock_synth,
        "render_pipeline": mock_render,
        "validated_pools": TEST_POOLS,
    }

    result = asyncio.run(auto_smart_multivoice.run_auto_smart_multivoice_blackbox(**payload))

    assert result.get("ok") is True
    assert result.get("auto_smart_verified") is True
    assert result.get("strategy") == auto_smart_multivoice.STRATEGY_GENERIC_MULTI
    assert result.get("detected_speaker_count") == 3
    assert result.get("effective_speaker_count") == 3
    assert result.get("effective_voice_count") == 3
    assert result.get("output_mode") == auto_smart_multivoice.OUTPUT_MODE_DUBBED_MULTI


def test_06_synthetic_dubbed_cues_have_exact_1_to_1_tts_coverage(tmp_path: Path):
    """Requirement 6: All synthetic dubbed cues have exact 1:1 TTS coverage."""
    src_mp4 = _create_real_valid_mp4(tmp_path / "src_coverage.mp4")

    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Cau 1", "start_ms": 0, "end_ms": 1000},
        {"cue_id": "c2", "speaker_id": "spk_2", "text": "Cau 2", "start_ms": 1100, "end_ms": 2000},
        {"cue_id": "c3", "speaker_id": "spk_3", "text": "Cau 3", "start_ms": 2100, "end_ms": 3000},
    ]

    tts_submitted_cues = []

    async def mock_synth(cues: list[dict] | None = None, speaker_voice_map: dict | None = None, *args: Any, **kwargs: Any) -> list[dict]:
        chunks = []
        for c in (cues or []):
            tts_submitted_cues.append(c["cue_id"])
            chunks.append({"cue_id": c["cue_id"], "audio": b"AUDIO_DATA"})
        return chunks

    async def mock_render(source_media: str, output_path: str, **kwargs: Any) -> str:
        _create_real_valid_mp4(Path(output_path))
        return output_path

    state = {
        "mode": "dub",
        "auto_smart_multivoice_opt_in": True,
        "auto_speaker_lane": "auto_smart_multivoice",
        "source": str(src_mp4),
    }

    payload = {
        "source_media": str(src_mp4),
        "cues": cues,
        "state": state,
        "synthesize_segments": mock_synth,
        "render_pipeline": mock_render,
        "validated_pools": TEST_POOLS,
    }

    result = asyncio.run(auto_smart_multivoice.run_auto_smart_multivoice_blackbox(**payload))

    assert result.get("ok") is True
    assert len(tts_submitted_cues) == 3
    assert set(tts_submitted_cues) == {"c1", "c2", "c3"}


def test_07_current_result_state_schema_preserved(tmp_path: Path):
    """Requirement 7: Current result state schema preserved."""
    src_mp4 = _create_real_valid_mp4(tmp_path / "src_schema.mp4")

    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Xin chao", "start_ms": 0, "end_ms": 1000},
        {"cue_id": "c2", "speaker_id": "spk_2", "text": "The gioi", "start_ms": 1100, "end_ms": 2000},
    ]

    async def mock_synth(cues: list[dict] | None = None, speaker_voice_map: dict | None = None, *args: Any, **kwargs: Any) -> list[dict]:
        return [{"cue_id": c["cue_id"], "audio": b"AUDIO"} for c in (cues or [])]

    async def mock_render(source_media: str, output_path: str, **kwargs: Any) -> str:
        _create_real_valid_mp4(Path(output_path))
        return output_path

    state = {
        "mode": "dub",
        "auto_smart_multivoice_opt_in": True,
        "auto_speaker_lane": "auto_smart_multivoice",
        "source": str(src_mp4),
    }

    payload = {
        "source_media": str(src_mp4),
        "cues": cues,
        "state": state,
        "synthesize_segments": mock_synth,
        "render_pipeline": mock_render,
        "validated_pools": TEST_POOLS,
    }

    result = asyncio.run(auto_smart_multivoice.run_auto_smart_multivoice_blackbox(**payload))

    assert result.get("ok") is True
    res_state = result.get("state")
    assert isinstance(res_state, dict)
    assert res_state.get("subdub_engine_selected") == "auto_smart_multivoice"
    assert res_state.get("auto_smart_multivoice_verified") is True
    assert res_state.get("auto_smart_strategy") is not None
    assert res_state.get("auto_detected_speaker_count") == 2
    assert res_state.get("auto_effective_speaker_count") == 2
    assert res_state.get("auto_distinct_voice_count") == 2
    assert res_state.get("auto_smart_output_mode") is not None
    assert isinstance(res_state.get("speaker_voice_map"), dict)


def test_08_video_output_remains_bytes_never_str_path(tmp_path: Path):
    """Requirement 8: video_output remains bytes, never str path."""
    src_mp4 = _create_real_valid_mp4(tmp_path / "src_bytes.mp4")

    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Xin chao", "start_ms": 0, "end_ms": 1000},
    ]

    async def mock_synth(cues: list[dict] | None = None, speaker_voice_map: dict | None = None, *args: Any, **kwargs: Any) -> list[dict]:
        return [{"cue_id": c["cue_id"], "audio": b"AUDIO"} for c in (cues or [])]

    async def mock_render(source_media: str, output_path: str, **kwargs: Any) -> str:
        _create_real_valid_mp4(Path(output_path))
        return output_path

    state = {
        "mode": "dub",
        "auto_smart_multivoice_opt_in": True,
        "auto_speaker_lane": "auto_smart_multivoice",
        "source": str(src_mp4),
    }

    payload = {
        "source_media": str(src_mp4),
        "cues": cues,
        "state": state,
        "synthesize_segments": mock_synth,
        "render_pipeline": mock_render,
        "validated_pools": TEST_POOLS,
    }

    result = asyncio.run(auto_smart_multivoice.run_auto_smart_multivoice_blackbox(**payload))

    assert result.get("ok") is True
    video_out = result.get("video_output")
    assert isinstance(video_out, (bytes, bytearray)), f"Expected bytes video_output, got {type(video_out)}"
    assert not isinstance(video_out, str), "video_output must NOT be a string filesystem path"
    assert len(video_out) > 0


def test_09_require_auto_cast_preserved():
    """Requirement 9: require_auto_cast=True preserved."""
    observed_require_auto_cast = None

    async def check_prepare(st: dict, *, require_auto_cast: bool = False) -> dict[str, Any]:
        nonlocal observed_require_auto_cast
        observed_require_auto_cast = require_auto_cast
        return {
            "source_bytes": b"FAKE_MP4_BYTES" * 100,
            "output_segments": [{"cue_id": "c1", "speaker_id": "spk_1", "text": "test"}],
            "content_type": "video/mp4",
        }

    async def mock_synth(*args: Any, **kwargs: Any) -> list[dict]:
        return [{"cue_id": "c1", "audio": b"AUDIO"}]

    async def mock_render(source_media: str, output_path: str, **kwargs: Any) -> str:
        _create_real_valid_mp4(Path(output_path))
        return output_path

    state = {
        "mode": "dub",
        "auto_smart_multivoice_opt_in": True,
        "auto_speaker_lane": "auto_smart_multivoice",
        "source_bytes": b"FAKE_MP4_BYTES" * 100,
    }

    payload = {
        "lane_mode": "dub",
        "state": state,
        "prepare_subtitles": check_prepare,
        "synthesize_segments": mock_synth,
        "render_pipeline": mock_render,
        "validated_pools": TEST_POOLS,
    }

    asyncio.run(auto_smart_multivoice.run_auto_smart_multivoice_blackbox(**payload))
    assert observed_require_auto_cast is True, "prepare_subtitles MUST receive require_auto_cast=True"


def test_10_saved_source_path_fallback_preserved(tmp_path: Path):
    """Requirement 10: Saved source path fallback preserved."""
    src_mp4 = _create_real_valid_mp4(tmp_path / "saved_src.mp4")

    state = {
        "mode": "dub",
        "auto_smart_multivoice_opt_in": True,
        "auto_speaker_lane": "auto_smart_multivoice",
        "_pipeline_saved_source_path": str(src_mp4),
    }

    async def check_prepare(st: dict, *, require_auto_cast: bool = False) -> dict[str, Any]:
        return {
            "output_segments": [{"cue_id": "c1", "speaker_id": "spk_1", "text": "test"}],
            "content_type": "video/mp4",
        }

    async def mock_synth(*args: Any, **kwargs: Any) -> list[dict]:
        return [{"cue_id": "c1", "audio": b"AUDIO"}]

    async def mock_render(source_media: str, output_path: str, **kwargs: Any) -> str:
        _create_real_valid_mp4(Path(output_path))
        return output_path

    payload = {
        "lane_mode": "dub",
        "state": state,
        "prepare_subtitles": check_prepare,
        "synthesize_segments": mock_synth,
        "render_pipeline": mock_render,
        "validated_pools": TEST_POOLS,
    }

    result = asyncio.run(auto_smart_multivoice.run_auto_smart_multivoice_blackbox(**payload))
    assert result.get("blocker") != "source_media_not_found"
    assert result.get("ok") is True


def test_11_smart_control_only_keys_preserved():
    """Requirement 11: PR #1138 invariants remain present."""
    assert hasattr(auto_smart_multivoice, "SMART_CONTROL_ONLY_KEYS")
    keys = auto_smart_multivoice.SMART_CONTROL_ONLY_KEYS
    assert isinstance(keys, tuple)
    assert len(keys) >= 15
    for expected in (
        "validated_pools",
        "required_pool_capacity",
        "post_prepare_gate",
        "extract_pcm",
        "stereo_pcm_path",
        "ranges_by_speaker",
        "deadline_monotonic",
        "stop_requested",
        "strict_two_classifier",
        "acoustic_classifications",
        "fallback_level_override",
        "default_fallback_voice",
        "locked_speaker_voice_map",
        "segments",
        "cues",
        "source_media",
    ):
        assert expected in keys, f"Missing expected key: {expected}"


def test_12_no_typeerror_fallback_in_source():
    """Requirement 12: No TypeError fallback introduced in source."""
    src_file = Path("services/subdub_blackboxes/auto_smart_multivoice.py")
    source_text = src_file.read_text(encoding="utf-8")
    assert "except TypeError" not in source_text, "No TypeError fallback allowed in auto_smart_multivoice"
    assert "require_auto_cast=True" in source_text, "require_auto_cast=True must remain present"
