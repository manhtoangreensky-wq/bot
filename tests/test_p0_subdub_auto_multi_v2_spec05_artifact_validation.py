from __future__ import annotations

import asyncio
import base64
import inspect
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

import bot
from services import subdub_speaker_cast as speaker_cast
from services import subdub_tts_artifact_validator as validator
from services import subdub_tts_checkpoint
from services.subdub_blackboxes import auto_multi_speaker_v2, auto_speaker


# Deterministic 358-byte valid MP3 (duration ~0.0783s, 44.1kHz mono, LAME encoder)
SAMPLE_VALID_MP3 = base64.b64decode(
    "SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjYyLjEyLjEwMQAAAAAAAAAAAAAA//sQxAAABHQTVVSQgDCmCa83GiACAAGtOUAAAVk6PVBQCAYJAfB8HwfKAgCAYRB8H9QIOxOH+INwBJP2wGA4HA4AAAAAACiJKpkUZAjpAkgWo/eFAfATG/AilC+oGhL8JA0qCgAYMAD/+xLEAoPFWB0gHeAAKKSDpIK8AAXMCQC8QASGAOB4Z+72pmMDlmHEESYMAH5gQgYGBSBMYF4DxZq0lflI8wEwETAAA2MDYIQzblDTLrF3ML8H0wWQHTALAtMCUB8wIwG0T59JA5JIAAr/+xDEAoAEtENSuZKAEJcGpuuYMARhEdKhTBbpmtFc+iKq+RLMu79/N5ZP4GFfx4sXwMd+FVAMXYXAAAAmEoRic8ySQagdXkkSQpUtPJRJFBQFYxhTvEt0qC3EqkxBTUUzLjEwMKqqqg=="
)


def _sync(fn):
    sig = inspect.signature(fn)

    def inner(*args, **kwargs):
        return asyncio.run(fn(*args, **kwargs))

    inner.__signature__ = sig
    inner.__name__ = fn.__name__
    return inner


def _setup_multi_v2_fixture(monkeypatch, tmp_path: Path, job_id: str):
    ws = str(tmp_path)
    state = {
        "job_id": job_id,
        "_pipeline_job_id": job_id,
        "_pipeline_workspace": ws,
        "workspace": ws,
        "target_language": "vi",
        "quote_fingerprint": "quote_spec05_valid",
    }
    cues = []
    speakers = ["chunk_00:speaker_0", "chunk_00:speaker_1", "chunk_00:speaker_2"]
    for i in range(1, 69):
        cid = f"cue_{i:03d}"
        spk = speakers[(i - 1) % len(speakers)]
        st = round((i - 1) * 2.5, 3)
        et = round(st + 2.0, 3)
        cues.append({
            "cue_id": cid,
            "id": cid,
            "index": i,
            "start": st,
            "end": et,
            "text": f"Lời thoại kiểm thử chuẩn xác số {i}",
            "speaker_id": spk,
        })

    classifications = {
        "chunk_00:speaker_0": {"speaker_id": "chunk_00:speaker_0", "voice_register": "high", "confidence": 0.95},
        "chunk_00:speaker_1": {"speaker_id": "chunk_00:speaker_1", "voice_register": "low", "confidence": 0.95},
        "chunk_00:speaker_2": {"speaker_id": "chunk_00:speaker_2", "voice_register": "low", "confidence": 0.95},
    }
    labels = ["chunk_00:speaker_0", "chunk_00:speaker_1", "chunk_00:speaker_2"]
    prepared = {
        "_pipeline_workspace": ws,
        "workspace": ws,
        "speaker_sidecar_sha256": "0" * 64,
        "source_segments": [dict(c) for c in cues],
        "output_segments": [dict(c) for c in cues],
    }

    async def fake_preflight(_state, **_kwargs):
        return {
            "ok": True,
            "status": auto_speaker.AUTO_SPEAKER_PREFLIGHT_READY,
            "prepared": prepared,
            "speaker_labels": labels,
            "classifications": classifications,
        }

    monkeypatch.setattr(
        auto_multi_speaker_v2.auto_multi_speaker,
        "_run_multi_speaker_preflight",
        fake_preflight,
    )
    pools = {
        "low": ["English_DecentYoungMan", "English_PassionateWarrior", "English_TrustworthyMan"],
        "high": ["English_ConfidentWoman", "English_CalmWoman", "English_GracefulLady"],
    }
    casts = speaker_cast.assign_stable_voices(
        classifications,
        speaker_order=labels,
        validated_pools=pools,
        assignment_seed="0" * 64,
    )
    assigned_voices = {spk: cast["voice_id"] for spk, cast in casts.items()}
    return ws, state, cues, pools, assigned_voices


# =========================================================================
# Unit Tests for Validator Output Matrix
# =========================================================================

def test_validator_valid_mp3(tmp_path: Path):
    path = tmp_path / "valid.mp3"
    path.write_bytes(SAMPLE_VALID_MP3)
    res = validator.validate_tts_audio_artifact(path)
    assert res.ok is True
    assert res.status == validator.STATUS_VALID
    assert res.duration > 0.0
    assert "mp3" in res.container
    assert res.codec in ("mp3", "mp3float")
    assert res.channels >= 1
    assert res.sample_rate > 0


def test_validator_empty_file(tmp_path: Path):
    path = tmp_path / "empty.mp3"
    path.write_bytes(b"")
    res = validator.validate_tts_audio_artifact(path)
    assert res.ok is False
    assert res.status == validator.STATUS_EMPTY_AUDIO


def test_validator_too_small(tmp_path: Path):
    path = tmp_path / "small.mp3"
    path.write_bytes(b"12345678")
    res = validator.validate_tts_audio_artifact(path, min_bytes=16)
    assert res.ok is False
    assert res.status == validator.STATUS_EMPTY_AUDIO


def test_validator_nonexistent_file(tmp_path: Path):
    path = tmp_path / "nonexistent.mp3"
    res = validator.validate_tts_audio_artifact(path)
    assert res.ok is False
    assert res.status == validator.STATUS_EMPTY_AUDIO


def test_validator_json_error_payload(tmp_path: Path):
    path = tmp_path / "error.mp3"
    path.write_bytes(b'{"error": {"code": 401, "message": "Unauthorized"}}\n' + b" " * 50)
    res = validator.validate_tts_audio_artifact(path)
    assert res.ok is False
    assert res.status == validator.STATUS_INVALID_CONTAINER
    assert "text_or_json_payload" in res.detail


def test_validator_html_error_payload(tmp_path: Path):
    path = tmp_path / "gateway_error.mp3"
    path.write_bytes(b"<html><head><title>502 Bad Gateway</title></head><body>502</body></html>")
    res = validator.validate_tts_audio_artifact(path)
    assert res.ok is False
    assert res.status == validator.STATUS_INVALID_CONTAINER


def test_validator_random_garbage_bytes(tmp_path: Path):
    path = tmp_path / "random.mp3"
    path.write_bytes(os.urandom(256))
    res = validator.validate_tts_audio_artifact(path)
    assert res.ok is False
    assert res.status in (validator.STATUS_INVALID_CONTAINER, validator.STATUS_DECODE_FAILED)


def test_validator_corrupted_frame_decode_failure(tmp_path: Path):
    data = bytearray(SAMPLE_VALID_MP3)
    # Corrupt audio frame payload
    for i in range(120, min(len(data), 240)):
        data[i] = 0xFF
    path = tmp_path / "corrupt_frame.mp3"
    path.write_bytes(bytes(data))
    res = validator.validate_tts_audio_artifact(path)
    assert res.ok is False
    assert res.status in (validator.STATUS_DECODE_FAILED, validator.STATUS_INVALID_CONTAINER)


# =========================================================================
# Gating Invariant Tests (SUCCEEDED_BEFORE_DECODE = NO)
# =========================================================================

def test_checkpoint_record_success_requires_valid_decode(tmp_path: Path):
    ws = str(tmp_path)
    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id="job_gate_test",
        target_language="vi",
    )
    cue = {"cue_id": "cue_001", "speaker_id": "spk_0", "text": "Câu 1", "start": 0.0, "end": 2.0}
    mgr.prepare_cue_intent(cue, "voice_01")

    # Attempting to record corrupted / invalid bytes must fail closed
    corrupt_bytes = os.urandom(128)
    with pytest.raises(subdub_tts_checkpoint.SubdubTTSArtifactCorruptionError):
        mgr.record_cue_success(cue, "voice_01", corrupt_bytes, duration=2.0)

    # Invariant check: manifest state MUST NOT be SUCCEEDED
    manifest_path = os.path.join(ws, "subdub_tts_manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        mdata = json.load(f)
    unit_key = mgr.compute_key(cue, "voice_01")
    entry = mdata["entries"][unit_key]
    assert entry["state"] != subdub_tts_checkpoint.STATE_SUCCEEDED
    assert entry["state"] == subdub_tts_checkpoint.STATE_AMBIGUOUS
    assert entry["completed_at"] is None


def test_checkpoint_record_success_with_valid_mp3_succeeds(tmp_path: Path):
    ws = str(tmp_path)
    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id="job_valid_success",
        target_language="vi",
    )
    cue = {"cue_id": "cue_001", "speaker_id": "spk_0", "text": "Câu 1", "start": 0.0, "end": 2.0}
    mgr.prepare_cue_intent(cue, "voice_01")

    res = mgr.record_cue_success(cue, "voice_01", SAMPLE_VALID_MP3, duration=2.0)
    assert res["state"] == subdub_tts_checkpoint.STATE_SUCCEEDED
    assert res["validation_status"] == validator.STATUS_VALID
    assert res["duration"] > 0.0
    assert abs(res["duration"] - 0.0783) < 0.02


def test_checkpoint_duration_comes_from_bitstream(tmp_path: Path):
    ws = str(tmp_path)
    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id="job_dur_source",
        target_language="vi",
    )
    cue = {"cue_id": "cue_001", "speaker_id": "spk_0", "text": "Câu 1", "start": 0.0, "end": 2.0}
    mgr.prepare_cue_intent(cue, "voice_01")

    # Pass an inflated mock provider duration (999.0s)
    res = mgr.record_cue_success(cue, "voice_01", SAMPLE_VALID_MP3, duration=999.0)
    # The recorded duration must come from probed bitstream (~0.078s), NOT 999.0
    assert res["duration"] < 1.0
    assert abs(res["duration"] - 0.0783) < 0.02


def test_checkpoint_reuse_validates_container_decode(tmp_path: Path):
    ws = str(tmp_path)
    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id="job_reuse_validation",
        target_language="vi",
    )
    cue = {"cue_id": "cue_001", "speaker_id": "spk_0", "text": "Câu 1", "start": 0.0, "end": 2.0}
    mgr.prepare_cue_intent(cue, "voice_01")
    res = mgr.record_cue_success(cue, "voice_01", SAMPLE_VALID_MP3, duration=2.0)
    art_path = res["artifact_path"]

    # Verify initial reuse succeeds
    mgr2 = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id="job_reuse_validation",
        target_language="vi",
    )
    is_reused, p, d, e = mgr2.prepare_cue_intent(cue, "voice_01")
    assert is_reused is True
    assert d == SAMPLE_VALID_MP3

    # Tamper artifact on disk with random bytes
    with open(art_path, "wb") as f:
        f.write(os.urandom(256))

    # Second reuse attempt must fail closed (REUSE=NO, FAIL_CLOSED=YES)
    mgr3 = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id="job_reuse_validation",
        target_language="vi",
    )
    with pytest.raises(subdub_tts_checkpoint.SubdubTTSArtifactCorruptionError):
        mgr3.prepare_cue_intent(cue, "voice_01")


# =========================================================================
# 68-Cue Pipeline Integration Regression with Validator Enabled
# =========================================================================

@_sync
async def test_spec05_68_cues_end_to_end_with_validation(monkeypatch, tmp_path: Path):
    ws, state, cues, pools, assigned_voices = _setup_multi_v2_fixture(monkeypatch, tmp_path, "job_spec05_68")

    provider_call_count = 0

    async def mock_synthesize_segments(segments, *args, **kwargs):
        nonlocal provider_call_count
        provider_call_count += 1
        seg = segments[0]
        return {
            "chunks": [
                {
                    "index": seg.get("index"),
                    "start": seg["start"],
                    "end": seg["end"],
                    "text": seg["text"],
                    "audio_bytes": SAMPLE_VALID_MP3,
                    "audio_duration": seg["end"] - seg["start"],
                }
            ],
            "provider": "mock_minimax_v2",
        }

    async def mock_runner(*args, **kwargs):
        return {"ok": True, "status": "PASS"}

    async def mock_run_lane(lane_mode, runner, **payload):
        synth = payload["synthesize_segments"]
        annotated = await payload["prepare_subtitles"](payload["state"])
        compat_voice = payload["resolve_voice_id"](1, payload["state"])
        tts_res = await synth(annotated["output_segments"], voice_id=compat_voice)
        return await runner(tts_res=tts_res)

    result = await auto_multi_speaker_v2._run_isolated_multi_speaker_v2_blackbox(
        lane_mode="subtitle_plus_dub",
        run_lane_blackbox=mock_run_lane,
        runner=mock_runner,
        prepare_subtitles=lambda *a, **kw: None,
        resolve_voice_id=lambda *a, **kw: None,
        synthesize_segments=mock_synthesize_segments,
        post_prepare_gate=lambda p, s: {"ok": True, "status": auto_speaker.AUTO_SPEAKER_PREFLIGHT_READY},
        extract_pcm=lambda *a, **kw: {"pcm_path": "audio.pcm"},
        validated_pools=pools,
        classify_speakers=lambda *a, **kw: {},
        state=state,
    )

    assert result.get("ok") is True
    assert provider_call_count == 68

    manifest_path = os.path.join(ws, "subdub_tts_manifest.json")
    assert os.path.isfile(manifest_path)
    with open(manifest_path, "r", encoding="utf-8") as f:
        mdata = json.load(f)
    assert len(mdata["entries"]) == 68
    for entry in mdata["entries"].values():
        assert entry["state"] == subdub_tts_checkpoint.STATE_SUCCEEDED
        assert entry["validation_status"] == validator.STATUS_VALID
        assert os.path.isfile(entry["artifact_path"])
        assert os.path.getsize(entry["artifact_path"]) > 0

    # Resume run: 0 new provider calls!
    provider_call_count_run2 = 0

    async def mock_synthesize_segments_run2(segments, *args, **kwargs):
        nonlocal provider_call_count_run2
        provider_call_count_run2 += 1
        return {"chunks": [], "provider": "mock"}

    result2 = await auto_multi_speaker_v2._run_isolated_multi_speaker_v2_blackbox(
        lane_mode="subtitle_plus_dub",
        run_lane_blackbox=mock_run_lane,
        runner=mock_runner,
        prepare_subtitles=lambda *a, **kw: None,
        resolve_voice_id=lambda *a, **kw: None,
        synthesize_segments=mock_synthesize_segments_run2,
        post_prepare_gate=lambda p, s: {"ok": True, "status": auto_speaker.AUTO_SPEAKER_PREFLIGHT_READY},
        extract_pcm=lambda *a, **kw: {"pcm_path": "audio.pcm"},
        validated_pools=pools,
        classify_speakers=lambda *a, **kw: {},
        state=state,
    )

    assert result2.get("ok") is True
    assert provider_call_count_run2 == 0
