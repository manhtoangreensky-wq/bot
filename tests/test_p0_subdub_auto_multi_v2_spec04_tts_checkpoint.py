from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

import bot
from services import subdub_speaker_cast as speaker_cast
from services import subdub_tts_checkpoint
from services.subdub_blackboxes import auto_multi_speaker_v2, auto_speaker


def _sync(fn):
    sig = inspect.signature(fn)

    def inner(*args, **kwargs):
        return asyncio.run(fn(*args, **kwargs))

    inner.__signature__ = sig
    inner.__name__ = fn.__name__
    return inner


def _make_68_cues() -> list[dict[str, Any]]:
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
            "text": f"Lời thoại phụ đề tiếng Việt thứ {i} chuẩn xác",
            "speaker_id": spk,
        })
    return cues


def _base_state(workspace: str, job_id: str = "job_test_001") -> dict[str, Any]:
    return {
        "job_id": job_id,
        "_pipeline_job_id": job_id,
        "_pipeline_workspace": workspace,
        "workspace": workspace,
        "target_language": "vi",
        "quote_fingerprint": "quote_spec04_valid",
        "subdub_mode": "subtitle_plus_dub",
        "source": os.path.join(workspace, "input.mp4"),
        "input_save": {"original_filename": "test_spec04.mp4"},
    }


def _setup_multi_v2_fixture(monkeypatch, tmp_path: Path, job_id: str = "job_test"):
    ws = str(tmp_path)
    state = _base_state(ws, job_id)
    cues = _make_68_cues()
    labels = ["chunk_00:speaker_0", "chunk_00:speaker_1", "chunk_00:speaker_2"]
    classifications = {
        "chunk_00:speaker_0": {"speaker_id": "chunk_00:speaker_0", "voice_register": "high", "confidence": 0.95},
        "chunk_00:speaker_1": {"speaker_id": "chunk_00:speaker_1", "voice_register": "low", "confidence": 0.95},
        "chunk_00:speaker_2": {"speaker_id": "chunk_00:speaker_2", "voice_register": "low", "confidence": 0.95},
    }
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
# Unit Tests for SubdubTTSCheckpointManager
# =========================================================================

def test_checkpoint_manager_unit_key_determinism():
    k1 = subdub_tts_checkpoint.compute_tts_unit_key(
        job_id="job1",
        cue_id="cue_001",
        speaker_id="spk_0",
        voice_id="voice_1",
        text="Xin chào",
        target_language="vi",
    )
    k2 = subdub_tts_checkpoint.compute_tts_unit_key(
        job_id="job1",
        cue_id="cue_001",
        speaker_id="spk_0",
        voice_id="voice_1",
        text="Xin chào",
        target_language="vi",
    )
    assert k1 == k2
    assert k1.startswith("unit_")


def test_checkpoint_manager_save_and_reload(tmp_path: Path):
    ws = str(tmp_path)
    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id="job_reload",
        target_language="vi",
        quote_fingerprint="quote_hash_1",
    )
    cue = {"cue_id": "cue_001", "speaker_id": "spk_0", "text": "Câu 1", "start": 0.0, "end": 2.0}
    is_reused, path, data, entry = mgr.prepare_cue_intent(cue, "voice_01")
    assert is_reused is False
    assert path == ""
    assert data == b""
    assert entry is None

    audio = b"dummy_mp3_bytes_12345"
    res = mgr.record_cue_success(
        cue,
        "voice_01",
        audio,
        duration=2.0,
        provider_label="mock_minimax",
    )
    assert res["state"] == subdub_tts_checkpoint.STATE_SUCCEEDED

    mgr2 = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id="job_reload",
        target_language="vi",
        quote_fingerprint="quote_hash_1",
    )
    is_reused2, path2, data2, entry2 = mgr2.prepare_cue_intent(cue, "voice_01")
    assert is_reused2 is True
    assert data2 == audio
    assert os.path.isfile(path2)
    assert entry2 is not None
    assert entry2["state"] == subdub_tts_checkpoint.STATE_SUCCEEDED


def test_checkpoint_manager_ambiguous_submission_detected(tmp_path: Path):
    ws = str(tmp_path)
    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id="job_crash",
        target_language="vi",
    )
    cue = {"cue_id": "cue_001", "speaker_id": "spk_0", "text": "Câu 1", "start": 0.0, "end": 2.0}
    mgr.prepare_cue_intent(cue, "voice_01")

    mgr_restart = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id="job_crash",
        target_language="vi",
    )
    with pytest.raises(subdub_tts_checkpoint.SubdubTTSAmbiguousSubmissionError):
        mgr_restart.prepare_cue_intent(cue, "voice_01")


def test_checkpoint_manager_corrupted_artifact_detected(tmp_path: Path):
    ws = str(tmp_path)
    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id="job_corrupt",
        target_language="vi",
    )
    cue = {"cue_id": "cue_001", "speaker_id": "spk_0", "text": "Câu 1", "start": 0.0, "end": 2.0}
    mgr.prepare_cue_intent(cue, "voice_01")
    res = mgr.record_cue_success(cue, "voice_01", b"original_audio", duration=2.0)
    art_path = res["artifact_path"]

    with open(art_path, "wb") as f:
        f.write(b"tampered_audio")

    mgr_check = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id="job_corrupt",
        target_language="vi",
    )
    with pytest.raises(subdub_tts_checkpoint.SubdubTTSArtifactCorruptionError):
        mgr_check.prepare_cue_intent(cue, "voice_01")


def test_checkpoint_manager_quote_mismatch_rejected(tmp_path: Path):
    ws = str(tmp_path)
    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id="job_quote",
        target_language="vi",
        quote_fingerprint="quote_aaa",
    )
    cue = {"cue_id": "cue_001", "speaker_id": "spk_0", "text": "Câu 1", "start": 0.0, "end": 2.0}
    mgr.prepare_cue_intent(cue, "voice_01")
    mgr.record_cue_success(cue, "voice_01", b"audio", duration=2.0)

    with pytest.raises(subdub_tts_checkpoint.SubdubTTSQuoteMismatchError):
        subdub_tts_checkpoint.SubdubTTSCheckpointManager(
            workspace=ws,
            job_id="job_quote",
            target_language="vi",
            quote_fingerprint="quote_bbb",
        )


def test_checkpoint_manager_contract_drift_rejected(tmp_path: Path):
    ws = str(tmp_path)
    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id="job_drift",
        target_language="vi",
    )
    cue_v1 = {"cue_id": "cue_001", "speaker_id": "spk_0", "text": "Text A", "start": 0.0, "end": 2.0}
    mgr.prepare_cue_intent(cue_v1, "voice_01")
    mgr.record_cue_success(cue_v1, "voice_01", b"audio", duration=2.0)

    cue_v2 = {"cue_id": "cue_001", "speaker_id": "spk_0", "text": "Text MODIFIED", "start": 0.0, "end": 2.0}
    with pytest.raises(subdub_tts_checkpoint.SubdubTTSContractMismatchError):
        mgr.prepare_cue_intent(cue_v2, "voice_01")


# =========================================================================
# Integration Tests with auto_multi_speaker_v2 Blackbox
# =========================================================================

@_sync
async def test_auto_multi_v2_spec04_happy_path_68_cues(monkeypatch, tmp_path: Path):
    ws, state, cues, pools, assigned_voices = _setup_multi_v2_fixture(monkeypatch, tmp_path, "job_happy_68")

    provider_call_count = 0
    sample_mp3 = b"ID3\x03\x00\x00\x00\x00\x00#TSSE\x00\x00\x00\x0f\x00\x00\x03Lavf58.76.100" + b"\x00" * 200

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
                    "audio_bytes": sample_mp3,
                    "audio_duration": seg["end"] - seg["start"],
                }
            ],
            "provider": "mock_tts_v2",
        }

    async def mock_runner(*args, **kwargs):
        return {
            "ok": True,
            "status": "PASS",
            "video_path": os.path.join(ws, "final_dubbed.mp4"),
        }

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
        assert os.path.isfile(entry["artifact_path"])
        assert os.path.getsize(entry["artifact_path"]) > 0


@_sync
async def test_auto_multi_v2_spec04_partial_resume_skips_prior_cues(monkeypatch, tmp_path: Path):
    ws, state, cues, pools, assigned_voices = _setup_multi_v2_fixture(monkeypatch, tmp_path, "job_resume_partial")

    provider_call_count = 0
    sample_mp3 = b"ID3\x03\x00\x00\x00\x00\x00#TSSE\x00\x00\x00\x0f\x00\x00\x03Lavf58.76.100" + b"\x00" * 200

    # Simulate cues 1..27 were completed in run 1
    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id="job_resume_partial",
        target_language="vi",
        quote_fingerprint="quote_spec04_valid",
    )
    for cue in cues[:27]:
        v = assigned_voices[cue["speaker_id"]]
        mgr.prepare_cue_intent(cue, v)
        mgr.record_cue_success(
            cue,
            v,
            sample_mp3,
            duration=cue["end"] - cue["start"],
            provider_label="mock_tts_v2",
            chunks_meta=[{
                "index": cue["index"],
                "start": cue["start"],
                "end": cue["end"],
                "text": cue["text"],
                "audio_duration": cue["end"] - cue["start"],
            }],
        )

    # In run 2 (resume): only cues 28..68 should invoke synthesize_segments!
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
                    "audio_bytes": sample_mp3,
                    "audio_duration": seg["end"] - seg["start"],
                }
            ],
            "provider": "mock_tts_v2",
        }

    collected_chunks = []
    async def mock_runner(*args, **kwargs):
        nonlocal collected_chunks
        collected_chunks = kwargs.get("tts_res", {}).get("chunks", [])
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
    # 68 - 27 = 41 provider calls
    assert provider_call_count == 41
    # Full 68 chunks delivered seamlessly
    assert len(collected_chunks) == 68


@_sync
async def test_auto_multi_v2_spec04_ambiguous_submission_fail_closed(monkeypatch, tmp_path: Path):
    ws, state, cues, pools, assigned_voices = _setup_multi_v2_fixture(monkeypatch, tmp_path, "job_ambiguous_crash")

    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id="job_ambiguous_crash",
        target_language="vi",
        quote_fingerprint="quote_spec04_valid",
    )
    # Pre-seed cue 1 in SUBMITTING state using assigned voice
    mgr.prepare_cue_intent(cues[0], assigned_voices[cues[0]["speaker_id"]])

    provider_called = False

    async def mock_synthesize_segments(segments, *args, **kwargs):
        nonlocal provider_called
        provider_called = True
        return {"chunks": [], "provider": "mock"}

    async def mock_run_lane(lane_mode, runner, **payload):
        synth = payload["synthesize_segments"]
        annotated = await payload["prepare_subtitles"](payload["state"])
        compat_voice = payload["resolve_voice_id"](1, payload["state"])
        return await synth(annotated["output_segments"], voice_id=compat_voice)

    result = await auto_multi_speaker_v2._run_isolated_multi_speaker_v2_blackbox(
        lane_mode="subtitle_plus_dub",
        run_lane_blackbox=mock_run_lane,
        runner=lambda *a, **kw: None,
        prepare_subtitles=lambda *a, **kw: None,
        resolve_voice_id=lambda *a, **kw: None,
        synthesize_segments=mock_synthesize_segments,
        post_prepare_gate=lambda p, s: {"ok": True, "status": auto_speaker.AUTO_SPEAKER_PREFLIGHT_READY},
        extract_pcm=lambda *a, **kw: {"pcm_path": "audio.pcm"},
        validated_pools=pools,
        classify_speakers=lambda *a, **kw: {},
        state=state,
    )

    assert result.get("ok") is False
    assert result.get("auto_multi_failure_stage") == "tts_checkpoint"
    assert result.get("auto_multi_failure_code") == "tts_ambiguous_submission"
    assert provider_called is False


@_sync
async def test_auto_multi_v2_spec04_corrupted_artifact_fail_closed(monkeypatch, tmp_path: Path):
    ws, state, cues, pools, assigned_voices = _setup_multi_v2_fixture(monkeypatch, tmp_path, "job_corrupt_artifact")

    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id="job_corrupt_artifact",
        target_language="vi",
        quote_fingerprint="quote_spec04_valid",
    )
    v0 = assigned_voices[cues[0]["speaker_id"]]
    mgr.prepare_cue_intent(cues[0], v0)
    res = mgr.record_cue_success(cues[0], v0, b"audio_valid_content", duration=2.0)
    with open(res["artifact_path"], "wb") as f:
        f.write(b"corrupted_bad_hash")

    provider_called = False

    async def mock_synthesize_segments(segments, *args, **kwargs):
        nonlocal provider_called
        provider_called = True
        return {"chunks": [], "provider": "mock"}

    async def mock_run_lane(lane_mode, runner, **payload):
        synth = payload["synthesize_segments"]
        annotated = await payload["prepare_subtitles"](payload["state"])
        compat_voice = payload["resolve_voice_id"](1, payload["state"])
        return await synth(annotated["output_segments"], voice_id=compat_voice)

    result = await auto_multi_speaker_v2._run_isolated_multi_speaker_v2_blackbox(
        lane_mode="subtitle_plus_dub",
        run_lane_blackbox=mock_run_lane,
        runner=lambda *a, **kw: None,
        prepare_subtitles=lambda *a, **kw: None,
        resolve_voice_id=lambda *a, **kw: None,
        synthesize_segments=mock_synthesize_segments,
        post_prepare_gate=lambda p, s: {"ok": True, "status": auto_speaker.AUTO_SPEAKER_PREFLIGHT_READY},
        extract_pcm=lambda *a, **kw: {"pcm_path": "audio.pcm"},
        validated_pools=pools,
        classify_speakers=lambda *a, **kw: {},
        state=state,
    )

    assert result.get("ok") is False
    assert result.get("auto_multi_failure_stage") == "tts_checkpoint"
    assert result.get("auto_multi_failure_code") == "tts_artifact_corruption"
    assert provider_called is False


@_sync
async def test_auto_multi_v2_spec04_contract_drift_fail_closed(monkeypatch, tmp_path: Path):
    ws, state, cues, pools, assigned_voices = _setup_multi_v2_fixture(monkeypatch, tmp_path, "job_drift_fail")

    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id="job_drift_fail",
        target_language="vi",
        quote_fingerprint="quote_spec04_valid",
    )
    v0 = assigned_voices[cues[0]["speaker_id"]]
    mgr.prepare_cue_intent(cues[0], v0)
    mgr.record_cue_success(cues[0], v0, b"audio_valid", duration=2.0)

    # Now modify cue 1's text in the pipeline input
    cues[0]["text"] = "Lời thoại đã bị thay đổi không còn khớp hợp đồng cũ"

    provider_called = False

    async def mock_synthesize_segments(segments, *args, **kwargs):
        nonlocal provider_called
        provider_called = True
        return {"chunks": [], "provider": "mock"}

    async def mock_run_lane(lane_mode, runner, **payload):
        synth = payload["synthesize_segments"]
        annotated = await payload["prepare_subtitles"](payload["state"])
        compat_voice = payload["resolve_voice_id"](1, payload["state"])
        annotated["output_segments"][0]["text"] = "Lời thoại đã bị thay đổi không còn khớp hợp đồng cũ"
        return await synth(annotated["output_segments"], voice_id=compat_voice)

    result = await auto_multi_speaker_v2._run_isolated_multi_speaker_v2_blackbox(
        lane_mode="subtitle_plus_dub",
        run_lane_blackbox=mock_run_lane,
        runner=lambda *a, **kw: None,
        prepare_subtitles=lambda *a, **kw: None,
        resolve_voice_id=lambda *a, **kw: None,
        synthesize_segments=mock_synthesize_segments,
        post_prepare_gate=lambda p, s: {"ok": True, "status": auto_speaker.AUTO_SPEAKER_PREFLIGHT_READY},
        extract_pcm=lambda *a, **kw: {"pcm_path": "audio.pcm"},
        validated_pools=pools,
        classify_speakers=lambda *a, **kw: {},
        state=state,
    )

    assert result.get("ok") is False
    assert result.get("auto_multi_failure_stage") == "tts_checkpoint"
    assert result.get("auto_multi_failure_code") == "tts_contract_mismatch"
    assert provider_called is False


@_sync
async def test_auto_multi_v2_spec04_quote_mismatch_fail_closed(monkeypatch, tmp_path: Path):
    ws, state, cues, pools, assigned_voices = _setup_multi_v2_fixture(monkeypatch, tmp_path, "job_quote_mismatch")

    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id="job_quote_mismatch",
        target_language="vi",
        quote_fingerprint="quote_original_alpha",
    )
    v0 = assigned_voices[cues[0]["speaker_id"]]
    mgr.prepare_cue_intent(cues[0], v0)

    # State has different quote fingerprint
    state["quote_fingerprint"] = "quote_different_beta"

    provider_called = False

    async def mock_synthesize_segments(segments, *args, **kwargs):
        nonlocal provider_called
        provider_called = True
        return {"chunks": [], "provider": "mock"}

    async def mock_run_lane(lane_mode, runner, **payload):
        synth = payload["synthesize_segments"]
        annotated = await payload["prepare_subtitles"](payload["state"])
        compat_voice = payload["resolve_voice_id"](1, payload["state"])
        return await synth(annotated["output_segments"], voice_id=compat_voice)

    result = await auto_multi_speaker_v2._run_isolated_multi_speaker_v2_blackbox(
        lane_mode="subtitle_plus_dub",
        run_lane_blackbox=mock_run_lane,
        runner=lambda *a, **kw: None,
        prepare_subtitles=lambda *a, **kw: None,
        resolve_voice_id=lambda *a, **kw: None,
        synthesize_segments=mock_synthesize_segments,
        post_prepare_gate=lambda p, s: {"ok": True, "status": auto_speaker.AUTO_SPEAKER_PREFLIGHT_READY},
        extract_pcm=lambda *a, **kw: {"pcm_path": "audio.pcm"},
        validated_pools=pools,
        classify_speakers=lambda *a, **kw: {},
        state=state,
    )

    assert result.get("ok") is False
    assert result.get("auto_multi_failure_stage") == "tts_checkpoint"
    assert result.get("auto_multi_failure_code") == "tts_quote_mismatch"
    assert provider_called is False


def test_auto_multi_v2_spec04_canonical_invariants():
    assert hasattr(subdub_tts_checkpoint, "SubdubTTSCheckpointManager")
    assert hasattr(subdub_tts_checkpoint, "SubdubTTSAmbiguousSubmissionError")
    assert hasattr(subdub_tts_checkpoint, "SubdubTTSArtifactCorruptionError")
    assert hasattr(subdub_tts_checkpoint, "SubdubTTSContractMismatchError")
    assert hasattr(subdub_tts_checkpoint, "SubdubTTSQuoteMismatchError")
    assert hasattr(subdub_tts_checkpoint, "STATE_SUBMITTING")
    assert hasattr(subdub_tts_checkpoint, "STATE_SUCCEEDED")
    assert hasattr(subdub_tts_checkpoint, "STATE_AMBIGUOUS")
