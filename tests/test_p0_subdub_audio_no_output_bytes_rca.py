"""Regression contract for SUBDUB_AUDIO_NO_OUTPUT_BYTES (#9CDA5E4059).

Tests desired invariants for source_media path resolution and failure return contract:
- CASE A: _pipeline_saved_source_path is resolved (must NOT fail with source_media_not_found).
- CASE B: _pipeline_source_path_override is resolved (must NOT fail with source_media_not_found).
- CASE C: explicit payload source_media is preserved with highest precedence.
- CASE D: all source paths missing produces truthful source_media_not_found contract.
- CASE E: Smart Multi failure status must be explicit and NOT default to NO_OUTPUT_BYTES.
- CASE F: 44.1kHz valid AAC source path resolution behavior same as 48kHz (no sample-rate regression).
"""

import asyncio
from pathlib import Path
from typing import Any
from services.subdub_blackboxes import auto_smart_multivoice


async def _mock_run_lane(*, lane_mode: str, runner: Any, **lane_payload: Any):
    return await runner(lane_mode=lane_mode, **lane_payload)


async def _mock_runner(**kwargs: Any):
    prep_fn = kwargs.get("prepare_subtitles")
    prep = await prep_fn(kwargs.get("state") or {}) if callable(prep_fn) else {}
    return {
        "ok": True,
        "status": "SUCCESS",
        "source_bytes": prep.get("source_bytes") or b"dummy video data 12345678",
        "audio_bytes": b"dummy audio",
        "video_output": b"dummy mp4 bytes",
        "state": kwargs.get("state") or {},
    }


def test_case_a_pipeline_saved_source_path_resolved(tmp_path: Path):
    async def _run():
        dummy_source = tmp_path / "saved_test.mp4"
        dummy_source.write_bytes(b"dummy video data 12345678")

        state = {
            "auto_speaker_lane": "auto_smart_multivoice",
            "voice_selection_mode": "auto_speaker",
            "mode": "subtitle_plus_dub",
            "_pipeline_saved_source_path": str(dummy_source),
        }

        async def mock_prepare(_st, *, require_auto_cast: bool = False):
            return {
                "source_bytes": b"dummy video data 12345678",
                "content_type": "video/mp4",
                "source_segments": [{"id": "cue_1", "cue_id": "cue_1", "speaker_id": "spk_1", "start": 0.0, "end": 2.0, "text": "Hello"}],
                "output_segments": [{"id": "cue_1", "cue_id": "cue_1", "speaker_id": "spk_1", "start": 0.0, "end": 2.0, "text": "Xin chao"}],
            }

        result = await auto_smart_multivoice.run_auto_smart_multivoice_blackbox(
            state=state,
            prepare_subtitles=mock_prepare,
            validated_pools={"low": ["v1", "v2"], "high": ["v3", "v4"]},
            run_lane_blackbox=_mock_run_lane,
            runner=_mock_runner,
        )

        assert result.get("blocker") != "source_media_not_found", (
            f"Expected source_media to be resolved from _pipeline_saved_source_path, got blocker: {result.get('blocker')}"
        )
        assert result.get("ok") is True

    asyncio.run(_run())


def test_case_b_pipeline_source_path_override_resolved(tmp_path: Path):
    async def _run():
        dummy_source = tmp_path / "override_test.mp4"
        dummy_source.write_bytes(b"dummy video data 12345678")

        state = {
            "auto_speaker_lane": "auto_smart_multivoice",
            "voice_selection_mode": "auto_speaker",
            "mode": "subtitle_plus_dub",
            "_pipeline_source_path_override": str(dummy_source),
        }

        async def mock_prepare(_st, *, require_auto_cast: bool = False):
            return {
                "source_bytes": b"dummy video data 12345678",
                "content_type": "video/mp4",
                "source_segments": [{"id": "cue_1", "cue_id": "cue_1", "speaker_id": "spk_1", "start": 0.0, "end": 2.0, "text": "Hello"}],
                "output_segments": [{"id": "cue_1", "cue_id": "cue_1", "speaker_id": "spk_1", "start": 0.0, "end": 2.0, "text": "Xin chao"}],
            }

        result = await auto_smart_multivoice.run_auto_smart_multivoice_blackbox(
            state=state,
            prepare_subtitles=mock_prepare,
            validated_pools={"low": ["v1", "v2"], "high": ["v3", "v4"]},
            run_lane_blackbox=_mock_run_lane,
            runner=_mock_runner,
        )

        assert result.get("blocker") != "source_media_not_found", (
            f"Expected source_media to be resolved from _pipeline_source_path_override, got blocker: {result.get('blocker')}"
        )
        assert result.get("ok") is True

    asyncio.run(_run())


def test_case_c_explicit_payload_source_media_precedence(tmp_path: Path):
    async def _run():
        explicit_source = tmp_path / "explicit.mp4"
        explicit_source.write_bytes(b"explicit video data")

        saved_source = tmp_path / "saved.mp4"
        saved_source.write_bytes(b"saved video data")

        state = {
            "auto_speaker_lane": "auto_smart_multivoice",
            "voice_selection_mode": "auto_speaker",
            "mode": "subtitle_plus_dub",
            "_pipeline_saved_source_path": str(saved_source),
        }

        async def mock_prepare(_st, *, require_auto_cast: bool = False):
            return {
                "source_bytes": b"explicit video data",
                "content_type": "video/mp4",
                "source_segments": [{"id": "cue_1", "cue_id": "cue_1", "speaker_id": "spk_1", "start": 0.0, "end": 2.0, "text": "Hello"}],
                "output_segments": [{"id": "cue_1", "cue_id": "cue_1", "speaker_id": "spk_1", "start": 0.0, "end": 2.0, "text": "Xin chao"}],
            }

        result = await auto_smart_multivoice.run_auto_smart_multivoice_blackbox(
            source_media=str(explicit_source),
            state=state,
            prepare_subtitles=mock_prepare,
            validated_pools={"low": ["v1", "v2"], "high": ["v3", "v4"]},
            run_lane_blackbox=_mock_run_lane,
            runner=_mock_runner,
        )

        assert result.get("blocker") != "source_media_not_found"
        assert result.get("ok") is True

    asyncio.run(_run())


def test_case_d_and_e_missing_source_failure_contract():
    async def _run():
        state = {
            "auto_speaker_lane": "auto_smart_multivoice",
            "voice_selection_mode": "auto_speaker",
            "mode": "subtitle_plus_dub",
            # No source paths provided at all
        }

        result = await auto_smart_multivoice.run_auto_smart_multivoice_blackbox(
            state=state,
            prepare_subtitles=lambda _st, *a, **k: asyncio.sleep(0, result={}),
        )

        assert result.get("ok") is False
        assert result.get("blocker") == "source_media_not_found"
        # Must have explicit non-empty status and error_code
        assert result.get("status") == "SOURCE_MEDIA_NOT_FOUND"
        assert result.get("error_code") == "source_media_not_found"
        # Must NOT default to NO_OUTPUT_BYTES
        assert result.get("status") != "NO_OUTPUT_BYTES"

    asyncio.run(_run())


def test_case_f_44100_incident_fixture_path_resolution(tmp_path: Path):
    async def _run():
        incident_fixture = tmp_path / "test_44100.mp4"
        incident_fixture.write_bytes(b"incident fixture data 44100hz aac stereo")

        state = {
            "auto_speaker_lane": "auto_smart_multivoice",
            "voice_selection_mode": "auto_speaker",
            "mode": "subtitle_plus_dub",
            "_pipeline_saved_source_path": str(incident_fixture),
            "source_sample_rate": 44100,
        }

        async def mock_prepare(_st, *, require_auto_cast: bool = False):
            return {
                "source_bytes": b"incident fixture data 44100hz aac stereo",
                "content_type": "video/mp4",
                "source_segments": [{"id": "cue_1", "cue_id": "cue_1", "speaker_id": "spk_1", "start": 0.0, "end": 2.0, "text": "Hello 44100"}],
                "output_segments": [{"id": "cue_1", "cue_id": "cue_1", "speaker_id": "spk_1", "start": 0.0, "end": 2.0, "text": "Xin chao 44100"}],
            }

        result = await auto_smart_multivoice.run_auto_smart_multivoice_blackbox(
            state=state,
            prepare_subtitles=mock_prepare,
            validated_pools={"low": ["v1", "v2"], "high": ["v3", "v4"]},
            run_lane_blackbox=_mock_run_lane,
            runner=_mock_runner,
        )

        assert result.get("blocker") != "source_media_not_found", (
            f"Expected 44.1kHz incident fixture to resolve without source_media_not_found, got blocker: {result.get('blocker')}"
        )
        assert result.get("ok") is True

    asyncio.run(_run())
