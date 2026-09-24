import asyncio
import base64
import os
from pathlib import Path
from typing import Any

import pytest

from services import subdub_tts_checkpoint
from services.subdub_blackboxes import auto_smart_multivoice as smart

SAMPLE_VALID_MP3 = base64.b64decode(
    "SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjYyLjEyLjEwMQAAAAAAAAAAAAAA//sQxAAABHQTVVSQgDCmCa83GiACAAGtOUAAAVk6PVBQCAYJAfB8HwfKAgCAYRB8H9QIOxOH+INwBJP2wGA4HA4AAAAAACiJKpkUZAjpAkgWo/eFAfATG/AilC+oGhL8JA0qCgAYMAD/+xLEAoPFWB0gHeAAKKSDpIK8AAXMCQC8QASGAOB4Z+72pmMDlmHEESYMAH5gQgYGBSBMYF4DxZq0lflI8wEwETAAA2MDYIQzblDTLrF3ML8H0wWQHTALAtMCUB8wIwG0T59JA5JIAAr/+xDEAoAEtENSuZKAEJcGpuuYMARhEdKhTBbpmtFc+iKq+RLMu79/N5ZP4GFfx4sXwMd+FVAMXYXAAAAmEoRic8ySQagdXkkSQpUtPJRJFBQFYxhTvEt0qC3EqkxBTUUzLjEwMKqqqg=="
)


import inspect

def _sync(fn):
    sig = inspect.signature(fn)
    def wrapper(*args, **kwargs):
        return asyncio.run(fn(*args, **kwargs))
    wrapper.__signature__ = sig
    wrapper.__name__ = fn.__name__
    return wrapper


@_sync
async def test_smart_multivoice_resume_skips_completed_cues(tmp_path: Path):
    """RUN 1: c1 ok, c2 ok, c3 fail.

    RUN 2: c1/c2 reused with 0 provider calls; resume proceeds from c3.
    """
    ws = str(tmp_path / "ws_resume")
    job_id = "job_smart_resume_01"
    quote_fp = "quote_fp_01"

    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Xin chào thế giới", "start": 0.0, "end": 2.0},
        {"cue_id": "c2", "speaker_id": "spk_2", "text": "Chào bạn nhé", "start": 2.0, "end": 4.0},
        {"cue_id": "c3", "speaker_id": "spk_1", "text": "Hẹn gặp lại", "start": 4.0, "end": 6.0},
    ]
    spk_map = {"spk_1": "voice_female", "spk_2": "voice_male"}

    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id=job_id,
        target_language="vi",
        quote_fingerprint=quote_fp,
    )

    provider_calls = {"c1": 0, "c2": 0, "c3": 0}
    run1_should_fail_c3 = True

    async def mock_base_synthesize(cues_arg, *args, **kwargs):
        cue = cues_arg[0]
        cid = cue["cue_id"]
        provider_calls[cid] += 1
        if cid == "c3" and run1_should_fail_c3:
            raise ConnectionResetError("network_timeout_simulated")
        return {
            "chunks": [
                {
                    "cue_id": cid,
                    "audio": SAMPLE_VALID_MP3,
                    "audio_bytes": SAMPLE_VALID_MP3,
                    "audio_duration": 2.0,
                }
            ],
            "provider": "key4u_mock",
        }

    synth_adapter = smart.create_smart_synth_adapter(
        mock_base_synthesize,
        checkpoint_manager=mgr,
    )

    # RUN 1: c1 ok, c2 ok, c3 fail
    with pytest.raises(ConnectionResetError):
        await synth_adapter(cues=cues, speaker_voice_map=spk_map)

    assert provider_calls["c1"] == 1
    assert provider_calls["c2"] == 1
    assert provider_calls["c3"] == 1

    # Verify manifest on disk
    manifest = mgr.entries
    assert manifest[mgr.compute_key(cues[0], "voice_female")]["state"] == subdub_tts_checkpoint.STATE_SUCCEEDED
    assert manifest[mgr.compute_key(cues[1], "voice_male")]["state"] == subdub_tts_checkpoint.STATE_SUCCEEDED
    assert manifest[mgr.compute_key(cues[2], "voice_female")]["state"] == subdub_tts_checkpoint.STATE_AMBIGUOUS

    # RUN 2: Reload checkpoint manager from disk for same job
    mgr_run2 = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id=job_id,
        target_language="vi",
        quote_fingerprint=quote_fp,
    )

    # Clear c3's ambiguous state to allow resume on c3
    del mgr_run2.entries[mgr_run2.compute_key(cues[2], "voice_female")]
    del mgr_run2.cue_id_to_unit_key["c3"]
    mgr_run2._save_manifest_atomic()

    run1_should_fail_c3 = False
    provider_calls_run2 = {"c1": 0, "c2": 0, "c3": 0}

    async def mock_base_synthesize_run2(cues_arg, *args, **kwargs):
        cue = cues_arg[0]
        cid = cue["cue_id"]
        provider_calls_run2[cid] += 1
        return {
            "chunks": [
                {
                    "cue_id": cid,
                    "audio": SAMPLE_VALID_MP3,
                    "audio_bytes": SAMPLE_VALID_MP3,
                    "audio_duration": 2.0,
                }
            ],
            "provider": "key4u_mock",
        }

    synth_adapter_run2 = smart.create_smart_synth_adapter(
        mock_base_synthesize_run2,
        checkpoint_manager=mgr_run2,
    )

    res2 = await synth_adapter_run2(cues=cues, speaker_voice_map=spk_map)

    # Verify completed cues were skipped (0 provider calls)
    assert provider_calls_run2["c1"] == 0, "Completed cue 1 must not call provider on resume"
    assert provider_calls_run2["c2"] == 0, "Completed cue 2 must not call provider on resume"
    assert provider_calls_run2["c3"] == 1, "Unfinished cue 3 must be synthesized"

    chunks = res2.get("chunks", [])
    assert len(chunks) == 3
    assert [c["cue_id"] for c in chunks] == ["c1", "c2", "c3"]
    for ch in chunks:
        assert ch["audio"] == SAMPLE_VALID_MP3
        assert ch["audio_bytes"] == SAMPLE_VALID_MP3


@_sync
async def test_smart_multivoice_ambiguous_restart_fails_closed(tmp_path: Path):
    """RUN 1: c1 ok, c2 fails ambiguously.

    RUN 2: c1 reused, c2 auto-resubmit = NO, provider calls = 0, FAIL_CLOSED.
    """
    ws = str(tmp_path / "ws_ambiguous")
    job_id = "job_smart_ambiguous"
    quote_fp = "quote_fp_ambiguous"

    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Câu một", "start": 0.0, "end": 2.0},
        {"cue_id": "c2", "speaker_id": "spk_2", "text": "Câu hai", "start": 2.0, "end": 4.0},
    ]
    spk_map = {"spk_1": "voice_female", "spk_2": "voice_male"}

    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id=job_id,
        target_language="vi",
        quote_fingerprint=quote_fp,
    )

    async def mock_base_synth_run1(cues_arg, *args, **kwargs):
        cue = cues_arg[0]
        if cue["cue_id"] == "c2":
            raise RuntimeError("provider_connection_dropped_midflight")
        return {
            "chunks": [{"cue_id": cue["cue_id"], "audio": SAMPLE_VALID_MP3, "audio_bytes": SAMPLE_VALID_MP3}],
            "provider": "key4u_mock",
        }

    synth1 = smart.create_smart_synth_adapter(mock_base_synth_run1, checkpoint_manager=mgr)
    with pytest.raises(RuntimeError):
        await synth1(cues=cues, speaker_voice_map=spk_map)

    # RUN 2: Same checkpoint manager on restart
    provider_calls_run2 = 0

    async def mock_base_synth_run2(cues_arg, *args, **kwargs):
        nonlocal provider_calls_run2
        provider_calls_run2 += 1
        return {
            "chunks": [{"cue_id": "c2", "audio": SAMPLE_VALID_MP3, "audio_bytes": SAMPLE_VALID_MP3}],
            "provider": "key4u_mock",
        }

    synth2 = smart.create_smart_synth_adapter(mock_base_synth_run2, checkpoint_manager=mgr)

    with pytest.raises(subdub_tts_checkpoint.SubdubTTSAmbiguousSubmissionError):
        await synth2(cues=cues, speaker_voice_map=spk_map)

    assert provider_calls_run2 == 0, "Ambiguous cue must NEVER be resubmitted automatically"


@_sync
async def test_smart_multivoice_submitting_state_fails_closed(tmp_path: Path):
    """Cue pre-recorded in STATE_SUBMITTING must fail closed with 0 provider calls."""
    ws = str(tmp_path / "ws_submitting")
    job_id = "job_smart_submitting"
    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id=job_id,
        target_language="vi",
        quote_fingerprint="fp_sub",
    )

    cue = {"cue_id": "c1", "speaker_id": "spk_1", "text": "Câu đang gửi", "start": 0.0, "end": 2.0}
    # Pre-seed cue in SUBMITTING
    mgr.prepare_cue_intent(cue, "voice_female")

    provider_called = False

    async def mock_base_synth(cues_arg, *args, **kwargs):
        nonlocal provider_called
        provider_called = True
        return {"chunks": []}

    synth = smart.create_smart_synth_adapter(mock_base_synth, checkpoint_manager=mgr)

    with pytest.raises(subdub_tts_checkpoint.SubdubTTSAmbiguousSubmissionError):
        await synth(cues=[cue], speaker_voice_map={"spk_1": "voice_female"})

    assert provider_called is False, "SUBMITTING state must fail closed without calling provider"


@_sync
async def test_smart_multivoice_corrupt_artifact_fails_closed(tmp_path: Path):
    """Corrupted/tampered artifact must fail closed with 0 provider calls."""
    ws = str(tmp_path / "ws_corrupt")
    job_id = "job_smart_corrupt"
    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id=job_id,
        target_language="vi",
        quote_fingerprint="fp_corrupt",
    )

    cue = {"cue_id": "c1", "speaker_id": "spk_1", "text": "Câu thành công bị sửa", "start": 0.0, "end": 2.0}
    mgr.prepare_cue_intent(cue, "voice_female")
    success_entry = mgr.record_cue_success(cue, "voice_female", SAMPLE_VALID_MP3, duration=2.0)

    # Tamper with the artifact file
    with open(success_entry["artifact_path"], "wb") as f:
        f.write(b"tampered_bad_audio_data")

    provider_called = False

    async def mock_base_synth(cues_arg, *args, **kwargs):
        nonlocal provider_called
        provider_called = True
        return {"chunks": []}

    synth = smart.create_smart_synth_adapter(mock_base_synth, checkpoint_manager=mgr)

    with pytest.raises(subdub_tts_checkpoint.SubdubTTSArtifactCorruptionError):
        await synth(cues=[cue], speaker_voice_map={"spk_1": "voice_female"})

    assert provider_called is False, "Corrupted artifact must fail closed without resynthesis"


@_sync
async def test_smart_multivoice_contract_drift_fails_closed(tmp_path: Path):
    """Text, voice, or speaker drift must fail closed with 0 provider calls."""
    ws = str(tmp_path / "ws_drift")
    job_id = "job_smart_drift"
    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id=job_id,
        target_language="vi",
        quote_fingerprint="fp_drift",
    )

    cue_orig = {"cue_id": "c1", "speaker_id": "spk_1", "text": "Nguyên bản", "start": 0.0, "end": 2.0}
    mgr.prepare_cue_intent(cue_orig, "voice_female")
    mgr.record_cue_success(cue_orig, "voice_female", SAMPLE_VALID_MP3, duration=2.0)

    provider_called = False

    async def mock_base_synth(cues_arg, *args, **kwargs):
        nonlocal provider_called
        provider_called = True
        return {"chunks": []}

    synth = smart.create_smart_synth_adapter(mock_base_synth, checkpoint_manager=mgr)

    # 1. Text drift
    cue_text_drift = dict(cue_orig, text="Nội dung đã bị thay đổi")
    with pytest.raises(subdub_tts_checkpoint.SubdubTTSContractMismatchError):
        await synth(cues=[cue_text_drift], speaker_voice_map={"spk_1": "voice_female"})
    assert provider_called is False

    # 2. Voice drift
    with pytest.raises(subdub_tts_checkpoint.SubdubTTSContractMismatchError):
        await synth(cues=[cue_orig], speaker_voice_map={"spk_1": "voice_male_different"})
    assert provider_called is False

    # 3. Speaker drift
    cue_spk_drift = dict(cue_orig, speaker_id="spk_2")
    with pytest.raises(subdub_tts_checkpoint.SubdubTTSContractMismatchError):
        await synth(cues=[cue_spk_drift], speaker_voice_map={"spk_2": "voice_female"})
    assert provider_called is False


@_sync
async def test_smart_multivoice_success_persisted_before_next_cue(tmp_path: Path):
    """Record success and artifact validation must be committed before next cue is invoked."""
    ws = str(tmp_path / "ws_order")
    job_id = "job_smart_order"
    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id=job_id,
        target_language="vi",
        quote_fingerprint="fp_order",
    )

    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Câu một", "start": 0.0, "end": 2.0},
        {"cue_id": "c2", "speaker_id": "spk_2", "text": "Câu hai", "start": 2.0, "end": 4.0},
    ]

    c1_persisted_when_c2_called = False

    async def mock_base_synth(cues_arg, *args, **kwargs):
        nonlocal c1_persisted_when_c2_called
        cid = cues_arg[0]["cue_id"]
        if cid == "c2":
            # Check if c1 was already committed to manifest as SUCCEEDED
            k1 = mgr.compute_key(cues[0], "voice_f")
            entry1 = mgr.entries.get(k1)
            if entry1 and entry1.get("state") == subdub_tts_checkpoint.STATE_SUCCEEDED:
                if os.path.isfile(entry1.get("artifact_path", "")):
                    c1_persisted_when_c2_called = True
        return {
            "chunks": [{"cue_id": cid, "audio": SAMPLE_VALID_MP3, "audio_bytes": SAMPLE_VALID_MP3, "audio_duration": 2.0}],
            "provider": "key4u_mock",
        }

    synth = smart.create_smart_synth_adapter(mock_base_synth, checkpoint_manager=mgr)
    await synth(cues=cues, speaker_voice_map={"spk_1": "voice_f", "spk_2": "voice_m"})

    assert c1_persisted_when_c2_called is True, "Cue 1 must be durably SUCCEEDED before Cue 2 synthesis is called"


@_sync
async def test_smart_multivoice_blackbox_end_to_end_resume(tmp_path: Path):
    """Test run_auto_smart_multivoice_blackbox end-to-end with persistent workspace and resume."""
    ws = str(tmp_path / "ws_b2b")
    job_id = "job_blackbox_b2b"

    state = {
        "auto_speaker_lane": smart.AUTO_SMART_MULTIVOICE_LANE,
        "_pipeline_workspace": ws,
        "job_id": job_id,
        "target_language": "vi",
        "quote_fingerprint": "quote_b2b",
    }

    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Chào buổi sáng", "start": 0.0, "end": 2.0},
        {"cue_id": "c2", "speaker_id": "spk_2", "text": "Chào buổi chiều", "start": 2.0, "end": 4.0},
    ]

    provider_calls = 0

    async def mock_base_synth(cues_arg, *args, **kwargs):
        nonlocal provider_calls
        provider_calls += 1
        cid = cues_arg[0]["cue_id"]
        return {
            "chunks": [
                {
                    "cue_id": cid,
                    "audio": SAMPLE_VALID_MP3,
                    "audio_bytes": SAMPLE_VALID_MP3,
                    "audio_duration": 2.0,
                }
            ],
            "provider": "key4u_b2b",
        }

    async def mock_render(*args, **kwargs):
        out_p = Path(kwargs["output_path"])
        out_p.write_bytes(b"DUMMY_MP4_RENDER_OUTPUT" * 50)
        return str(out_p)

    def mock_probe(p):
        return {"ok": True}

    src_mp4 = tmp_path / "src.mp4"
    src_mp4.write_bytes(b"DUMMY_MP4_SOURCE_VIDEO_BYTES" * 50)

    # RUN 1
    res1 = await smart.run_auto_smart_multivoice_blackbox(
        state=state,
        cues=cues,
        synthesize_segments=mock_base_synth,
        render_pipeline=mock_render,
        probe_fn=mock_probe,
        validated_pools={"low": ["v1", "v2"], "high": ["v3", "v4"]},
        source_media=str(src_mp4),
    )

    assert res1.get("ok") is True
    assert provider_calls == 2
    assert res1.get("checkpoint_workspace") == ws
    assert res1.get("checkpoint_job_id") == job_id

    # RUN 2: Resume with same state
    provider_calls_run2 = 0

    async def mock_base_synth_run2(cues_arg, *args, **kwargs):
        nonlocal provider_calls_run2
        provider_calls_run2 += 1
        return {"chunks": []}

    res2 = await smart.run_auto_smart_multivoice_blackbox(
        state=state,
        cues=cues,
        synthesize_segments=mock_base_synth_run2,
        render_pipeline=mock_render,
        probe_fn=mock_probe,
        validated_pools={"low": ["v1", "v2"], "high": ["v3", "v4"]},
        source_media=str(src_mp4),
    )

    assert res2.get("ok") is True
    assert provider_calls_run2 == 0, "Resume must reuse all checkpointed cues with 0 provider calls"


@_sync
async def test_smart_multivoice_missing_durable_workspace_blocked(tmp_path: Path):
    """If no durable workspace can be proven, fail closed with BLOCKED_NO_DURABLE_LIVE_JOB_WORKSPACE."""
    src_mp4 = tmp_path / "src_noblock.mp4"
    src_mp4.write_bytes(b"DUMMY_MP4_SOURCE_VIDEO_BYTES" * 50)

    state = {
        "auto_speaker_lane": smart.AUTO_SMART_MULTIVOICE_LANE,
        # No _pipeline_workspace, no workspace, no job_id
    }

    res = await smart.run_auto_smart_multivoice_blackbox(
        state=state,
        cues=[{"cue_id": "c1", "speaker_id": "spk_1", "text": "Test", "start": 0.0, "end": 2.0}],
        synthesize_segments=lambda *a, **kw: None,
        source_media=str(src_mp4),
        job_id="",
        workspace="",
    )

    assert res.get("ok") is False
    assert res.get("blocker") == "BLOCKED_NO_DURABLE_LIVE_JOB_WORKSPACE"
    assert res.get("status") == "BLOCKED_NO_DURABLE_LIVE_JOB_WORKSPACE"


@_sync
async def test_smart_multivoice_workspace_present_job_id_absent_fails_closed(tmp_path: Path):
    """CASE 1: workspace present, job_id absent -> FAIL_CLOSED, provider calls = 0."""
    ws = str(tmp_path / "ws_case1")
    src_mp4 = tmp_path / "src_case1.mp4"
    src_mp4.write_bytes(b"DUMMY_MP4_SOURCE_VIDEO_BYTES" * 50)

    state = {
        "auto_speaker_lane": smart.AUTO_SMART_MULTIVOICE_LANE,
        "_pipeline_workspace": ws,
        # job_id completely absent
    }

    provider_called = False

    async def mock_synth(*args, **kwargs):
        nonlocal provider_called
        provider_called = True
        return {"chunks": []}

    res = await smart.run_auto_smart_multivoice_blackbox(
        state=state,
        cues=[{"cue_id": "c1", "speaker_id": "spk_1", "text": "Test", "start": 0.0, "end": 2.0}],
        synthesize_segments=mock_synth,
        source_media=str(src_mp4),
    )

    assert res.get("ok") is False
    assert res.get("status") == "FAIL_CLOSED_MISSING_CHECKPOINT_JOB_ID"
    assert res.get("blocker") == "FAIL_CLOSED_MISSING_CHECKPOINT_JOB_ID"
    assert res.get("error_code") == "FAIL_CLOSED_MISSING_CHECKPOINT_JOB_ID"
    assert provider_called is False


@_sync
async def test_smart_multivoice_workspace_present_job_id_empty_fails_closed(tmp_path: Path):
    """CASE 2: workspace present, job_id empty string -> FAIL_CLOSED, provider calls = 0."""
    ws = str(tmp_path / "ws_case2")
    src_mp4 = tmp_path / "src_case2.mp4"
    src_mp4.write_bytes(b"DUMMY_MP4_SOURCE_VIDEO_BYTES" * 50)

    state = {
        "auto_speaker_lane": smart.AUTO_SMART_MULTIVOICE_LANE,
        "_pipeline_workspace": ws,
        "job_id": "",
    }

    provider_called = False

    async def mock_synth(*args, **kwargs):
        nonlocal provider_called
        provider_called = True
        return {"chunks": []}

    res = await smart.run_auto_smart_multivoice_blackbox(
        state=state,
        cues=[{"cue_id": "c1", "speaker_id": "spk_1", "text": "Test", "start": 0.0, "end": 2.0}],
        synthesize_segments=mock_synth,
        source_media=str(src_mp4),
        job_id="",
    )

    assert res.get("ok") is False
    assert res.get("status") == "FAIL_CLOSED_MISSING_CHECKPOINT_JOB_ID"
    assert res.get("blocker") == "FAIL_CLOSED_MISSING_CHECKPOINT_JOB_ID"
    assert res.get("error_code") == "FAIL_CLOSED_MISSING_CHECKPOINT_JOB_ID"
    assert provider_called is False


@_sync
async def test_smart_multivoice_workspace_present_job_id_whitespace_fails_closed(tmp_path: Path):
    """CASE 3: workspace present, job_id whitespace-only -> FAIL_CLOSED, provider calls = 0."""
    ws = str(tmp_path / "ws_case3")
    src_mp4 = tmp_path / "src_case3.mp4"
    src_mp4.write_bytes(b"DUMMY_MP4_SOURCE_VIDEO_BYTES" * 50)

    state = {
        "auto_speaker_lane": smart.AUTO_SMART_MULTIVOICE_LANE,
        "_pipeline_workspace": ws,
        "job_id": "   \t  \n  ",
    }

    provider_called = False

    async def mock_synth(*args, **kwargs):
        nonlocal provider_called
        provider_called = True
        return {"chunks": []}

    res = await smart.run_auto_smart_multivoice_blackbox(
        state=state,
        cues=[{"cue_id": "c1", "speaker_id": "spk_1", "text": "Test", "start": 0.0, "end": 2.0}],
        synthesize_segments=mock_synth,
        source_media=str(src_mp4),
        job_id="  \t  ",
    )

    assert res.get("ok") is False
    assert res.get("status") == "FAIL_CLOSED_MISSING_CHECKPOINT_JOB_ID"
    assert res.get("blocker") == "FAIL_CLOSED_MISSING_CHECKPOINT_JOB_ID"
    assert res.get("error_code") == "FAIL_CLOSED_MISSING_CHECKPOINT_JOB_ID"
    assert provider_called is False


@_sync
async def test_smart_multivoice_workspace_present_canonical_job_id_success(tmp_path: Path):
    """CASE 4: workspace present, canonical job_id present -> checkpoint manager constructed, route proceeds."""
    ws = str(tmp_path / "ws_case4")
    src_mp4 = tmp_path / "src_case4.mp4"
    src_mp4.write_bytes(b"DUMMY_MP4_SOURCE_VIDEO_BYTES" * 50)

    job_id = "job_canonical_case4_001"
    state = {
        "auto_speaker_lane": smart.AUTO_SMART_MULTIVOICE_LANE,
        "_pipeline_workspace": ws,
        "job_id": job_id,
        "target_language": "vi",
        "quote_fingerprint": "quote_case4",
    }

    cues = [{"cue_id": "c1", "speaker_id": "spk_1", "text": "Kiểm tra hợp lệ", "start": 0.0, "end": 2.0}]
    provider_calls = 0

    async def mock_synth(cues_arg, *args, **kwargs):
        nonlocal provider_calls
        provider_calls += 1
        return {
            "chunks": [
                {
                    "cue_id": "c1",
                    "audio": SAMPLE_VALID_MP3,
                    "audio_bytes": SAMPLE_VALID_MP3,
                    "audio_duration": 2.0,
                }
            ],
            "provider": "key4u_case4",
        }

    async def mock_render(*args, **kwargs):
        out_p = Path(kwargs["output_path"])
        out_p.write_bytes(b"DUMMY_MP4_RENDER_OUTPUT" * 50)
        return str(out_p)

    def mock_probe(p):
        return {"ok": True}

    res = await smart.run_auto_smart_multivoice_blackbox(
        state=state,
        cues=cues,
        synthesize_segments=mock_synth,
        render_pipeline=mock_render,
        probe_fn=mock_probe,
        validated_pools={"low": ["v1", "v2"], "high": ["v3", "v4"]},
        source_media=str(src_mp4),
    )

    assert res.get("ok") is True
    assert provider_calls == 1
    assert res.get("checkpoint_workspace") == ws
    assert res.get("checkpoint_job_id") == job_id
    manifest_file = Path(ws) / "subdub_tts_manifest.json"
    assert manifest_file.is_file(), "Manifest must be written to durable workspace"


@_sync
async def test_smart_multivoice_job_id_present_workspace_unresolvable_fails_closed(tmp_path: Path):
    """CASE 5: canonical job_id present, durable workspace cannot be resolved -> FAIL_CLOSED, provider calls = 0."""
    src_mp4 = tmp_path / "src_case5.mp4"
    src_mp4.write_bytes(b"DUMMY_MP4_SOURCE_VIDEO_BYTES" * 50)

    state = {
        "auto_speaker_lane": smart.AUTO_SMART_MULTIVOICE_LANE,
        "job_id": "job_canonical_case5_valid",
        # No workspace, no _pipeline_workspace
    }

    provider_called = False

    async def mock_synth(*args, **kwargs):
        nonlocal provider_called
        provider_called = True
        return {"chunks": []}

    res = await smart.run_auto_smart_multivoice_blackbox(
        state=state,
        cues=[{"cue_id": "c1", "speaker_id": "spk_1", "text": "Test", "start": 0.0, "end": 2.0}],
        synthesize_segments=mock_synth,
        source_media=str(src_mp4),
        job_id="job_canonical_case5_valid",
        workspace="",
    )

    assert res.get("ok") is False
    assert res.get("status") == "BLOCKED_NO_DURABLE_LIVE_JOB_WORKSPACE"
    assert res.get("blocker") == "BLOCKED_NO_DURABLE_LIVE_JOB_WORKSPACE"
    assert res.get("error_code") == "BLOCKED_NO_DURABLE_LIVE_JOB_WORKSPACE"
    assert provider_called is False


@_sync
async def test_smart_synth_adapter_base_synthesize_unreachable_with_empty_job_id():
    """Direct adapter invariant: base_synthesize must be unreachable when checkpoint manager cannot be created."""
    provider_called = False

    async def mock_base_synth(*args, **kwargs):
        nonlocal provider_called
        provider_called = True
        return {"chunks": []}

    adapter = smart.create_smart_synth_adapter(
        mock_base_synth,
        checkpoint_manager=None,
        workspace="",
        job_id="",
    )

    with pytest.raises(subdub_tts_checkpoint.SubdubTTSCheckpointError) as exc_info:
        await adapter(
            cues=[{"cue_id": "c1", "speaker_id": "spk_1", "text": "Unreachable", "start": 0.0, "end": 2.0}],
            speaker_voice_map={"spk_1": "v1"},
        )

    assert "missing_checkpoint_identity" in str(exc_info.value)
    assert provider_called is False, "base_synthesize MUST be unreachable with empty job_id"


@_sync
async def test_smart_multivoice_async_submitted_case_a_fails_closed(tmp_path: Path):
    """CASE A: STATE_ASYNC_SUBMITTED with task_id present -> FAIL_CLOSED, provider calls = 0."""
    ws = str(tmp_path / "ws_async_a")
    job_id = "job_async_case_a"
    src_mp4 = tmp_path / "src_async_a.mp4"
    src_mp4.write_bytes(b"DUMMY_MP4_SOURCE_VIDEO_BYTES" * 50)

    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id=job_id,
        target_language="vi",
        quote_fingerprint="quote_async_a",
    )

    cue = {"cue_id": "c1", "speaker_id": "spk_1", "text": "Câu đang chờ xử lý", "start": 0.0, "end": 2.0}
    # Pre-record cue in STATE_ASYNC_SUBMITTED with task_id
    mgr.record_cue_async_submitted(cue, "voice_female", task_id="task_minimax_case_a_001")

    # Verify manifest on disk has STATE_ASYNC_SUBMITTED and task_id
    manifest = mgr.entries
    key = mgr.compute_key(cue, "voice_female")
    assert manifest[key]["state"] == subdub_tts_checkpoint.STATE_ASYNC_SUBMITTED
    assert manifest[key]["task_id"] == "task_minimax_case_a_001"

    provider_called = False

    async def mock_synth(*args, **kwargs):
        nonlocal provider_called
        provider_called = True
        return {"chunks": []}

    state = {
        "auto_speaker_lane": smart.AUTO_SMART_MULTIVOICE_LANE,
        "_pipeline_workspace": ws,
        "job_id": job_id,
        "target_language": "vi",
        "quote_fingerprint": "quote_async_a",
    }

    res = await smart.run_auto_smart_multivoice_blackbox(
        state=state,
        cues=[cue],
        synthesize_segments=mock_synth,
        render_pipeline=lambda **kw: "out.mp4",
        source_media=str(src_mp4),
        checkpoint_manager=mgr,
        validated_pools={"low": ["v1"], "high": ["voice_female"]},
        locked_speaker_voice_map={"spk_1": "voice_female"},
    )

    assert res.get("ok") is False
    assert res.get("status") == smart.FAIL_CLOSED_ASYNC_SUBMITTED_PRIOR_SUBMIT
    assert res.get("blocker") == smart.FAIL_CLOSED_ASYNC_SUBMITTED_PRIOR_SUBMIT
    assert res.get("error_code") == smart.FAIL_CLOSED_ASYNC_SUBMITTED_PRIOR_SUBMIT
    assert res.get("async_task_id") == "task_minimax_case_a_001"
    assert provider_called is False, "Provider must NEVER be called for already-submitted async cue"

    # Disk state must be preserved
    mgr_reload = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id=job_id,
        target_language="vi",
        quote_fingerprint="quote_async_a",
    )
    assert mgr_reload.entries[key]["state"] == subdub_tts_checkpoint.STATE_ASYNC_SUBMITTED
    assert mgr_reload.entries[key]["task_id"] == "task_minimax_case_a_001"


@_sync
async def test_smart_multivoice_async_submitted_case_b_identifiers_preserved(tmp_path: Path):
    """CASE B: STATE_ASYNC_SUBMITTED with task_id and provider_request_id -> FAIL_CLOSED, identifiers preserved."""
    ws = str(tmp_path / "ws_async_b")
    job_id = "job_async_case_b"
    src_mp4 = tmp_path / "src_async_b.mp4"
    src_mp4.write_bytes(b"DUMMY_MP4_SOURCE_VIDEO_BYTES" * 50)

    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id=job_id,
        target_language="vi",
        quote_fingerprint="quote_async_b",
    )

    cue = {"cue_id": "c1", "speaker_id": "spk_1", "text": "Câu có đủ request ID", "start": 0.0, "end": 2.0}
    mgr.record_cue_async_submitted(
        cue,
        "voice_female",
        task_id="task_minimax_case_b_777",
        provider_request_id="req_minimax_tx_999",
    )

    provider_called = False

    async def mock_synth(*args, **kwargs):
        nonlocal provider_called
        provider_called = True
        return {"chunks": []}

    state = {
        "auto_speaker_lane": smart.AUTO_SMART_MULTIVOICE_LANE,
        "_pipeline_workspace": ws,
        "job_id": job_id,
        "target_language": "vi",
        "quote_fingerprint": "quote_async_b",
    }

    res = await smart.run_auto_smart_multivoice_blackbox(
        state=state,
        cues=[cue],
        synthesize_segments=mock_synth,
        render_pipeline=lambda **kw: "out.mp4",
        source_media=str(src_mp4),
        checkpoint_manager=mgr,
        validated_pools={"low": ["v1"], "high": ["voice_female"]},
        locked_speaker_voice_map={"spk_1": "voice_female"},
    )

    assert res.get("ok") is False
    assert res.get("status") == smart.FAIL_CLOSED_ASYNC_SUBMITTED_PRIOR_SUBMIT
    assert res.get("blocker") == smart.FAIL_CLOSED_ASYNC_SUBMITTED_PRIOR_SUBMIT
    assert res.get("async_task_id") == "task_minimax_case_b_777"
    assert res.get("async_provider_request_id") == "req_minimax_tx_999"
    assert res.get("state", {}).get("async_task_id") == "task_minimax_case_b_777"
    assert res.get("state", {}).get("async_provider_request_id") == "req_minimax_tx_999"
    assert provider_called is False

    # Checkpoint on disk must preserve both identifiers and state
    mgr_reload = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id=job_id,
        target_language="vi",
        quote_fingerprint="quote_async_b",
    )
    key = mgr.compute_key(cue, "voice_female")
    entry = mgr_reload.entries[key]
    assert entry["state"] == subdub_tts_checkpoint.STATE_ASYNC_SUBMITTED
    assert entry["task_id"] == "task_minimax_case_b_777"
    assert entry["provider_request_id"] == "req_minimax_tx_999"


@_sync
async def test_smart_multivoice_async_submitted_case_c_prev_succeeded_reused_async_fails_closed(tmp_path: Path):
    """CASE C: previous cue STATE_SUCCEEDED, next cue STATE_ASYNC_SUBMITTED.

    Expected: previous cue reused, async cue fails closed, no new call for either completed or async cue.
    """
    ws = str(tmp_path / "ws_async_c")
    job_id = "job_async_case_c"
    src_mp4 = tmp_path / "src_async_c.mp4"
    src_mp4.write_bytes(b"DUMMY_MP4_SOURCE_VIDEO_BYTES" * 50)

    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id=job_id,
        target_language="vi",
        quote_fingerprint="quote_async_c",
    )

    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Câu một đã xong", "start": 0.0, "end": 2.0},
        {"cue_id": "c2", "speaker_id": "spk_2", "text": "Câu hai đang xử lý bất đồng bộ", "start": 2.0, "end": 4.0},
    ]

    # Pre-record c1 as SUCCEEDED with valid MP3
    mgr.prepare_cue_intent(cues[0], "voice_female")
    mgr.record_cue_success(cues[0], "voice_female", SAMPLE_VALID_MP3, duration=2.0)

    # Pre-record c2 as ASYNC_SUBMITTED
    mgr.record_cue_async_submitted(
        cues[1],
        "voice_male",
        task_id="task_c2_async_in_flight",
        provider_request_id="req_c2_in_flight",
    )

    provider_calls = {"c1": 0, "c2": 0}

    async def mock_synth(cues_arg, *args, **kwargs):
        cid = cues_arg[0]["cue_id"]
        provider_calls[cid] += 1
        return {"chunks": []}

    state = {
        "auto_speaker_lane": smart.AUTO_SMART_MULTIVOICE_LANE,
        "_pipeline_workspace": ws,
        "job_id": job_id,
        "target_language": "vi",
        "quote_fingerprint": "quote_async_c",
    }

    res = await smart.run_auto_smart_multivoice_blackbox(
        state=state,
        cues=cues,
        synthesize_segments=mock_synth,
        render_pipeline=lambda **kw: "out.mp4",
        source_media=str(src_mp4),
        checkpoint_manager=mgr,
        validated_pools={"low": ["voice_male"], "high": ["voice_female"]},
        locked_speaker_voice_map={"spk_1": "voice_female", "spk_2": "voice_male"},
    )

    assert res.get("ok") is False
    assert res.get("status") == smart.FAIL_CLOSED_ASYNC_SUBMITTED_PRIOR_SUBMIT
    assert res.get("blocker") == smart.FAIL_CLOSED_ASYNC_SUBMITTED_PRIOR_SUBMIT
    assert res.get("async_task_id") == "task_c2_async_in_flight"
    assert res.get("async_provider_request_id") == "req_c2_in_flight"
    assert provider_calls["c1"] == 0, "Succeeded cue 1 must be reused without calling provider"
    assert provider_calls["c2"] == 0, "Async submitted cue 2 must fail closed without calling provider"


@_sync
async def test_smart_multivoice_async_submitted_case_d_restart_same_job_still_fails_closed(tmp_path: Path):
    """CASE D: restart same job again -> still fails closed at same async cue, provider calls = 0."""
    ws = str(tmp_path / "ws_async_d")
    job_id = "job_async_case_d"
    src_mp4 = tmp_path / "src_async_d.mp4"
    src_mp4.write_bytes(b"DUMMY_MP4_SOURCE_VIDEO_BYTES" * 50)

    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id=job_id,
        target_language="vi",
        quote_fingerprint="quote_async_d",
    )

    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Câu một thành công", "start": 0.0, "end": 2.0},
        {"cue_id": "c2", "speaker_id": "spk_2", "text": "Câu hai bất đồng bộ", "start": 2.0, "end": 4.0},
    ]

    # Pre-record c1 SUCCEEDED, c2 ASYNC_SUBMITTED
    mgr.prepare_cue_intent(cues[0], "voice_female")
    mgr.record_cue_success(cues[0], "voice_female", SAMPLE_VALID_MP3, duration=2.0)
    mgr.record_cue_async_submitted(cues[1], "voice_male", task_id="task_c2_async_persistent")

    state = {
        "auto_speaker_lane": smart.AUTO_SMART_MULTIVOICE_LANE,
        "_pipeline_workspace": ws,
        "job_id": job_id,
        "target_language": "vi",
        "quote_fingerprint": "quote_async_d",
    }

    total_provider_calls = 0

    async def mock_synth(*args, **kwargs):
        nonlocal total_provider_calls
        total_provider_calls += 1
        return {"chunks": []}

    # RUN 1
    res1 = await smart.run_auto_smart_multivoice_blackbox(
        state=state,
        cues=cues,
        synthesize_segments=mock_synth,
        render_pipeline=lambda **kw: "out.mp4",
        source_media=str(src_mp4),
        checkpoint_manager=mgr,
        validated_pools={"low": ["voice_male"], "high": ["voice_female"]},
        locked_speaker_voice_map={"spk_1": "voice_female", "spk_2": "voice_male"},
    )
    assert res1.get("ok") is False
    assert res1.get("status") == smart.FAIL_CLOSED_ASYNC_SUBMITTED_PRIOR_SUBMIT
    assert res1.get("async_task_id") == "task_c2_async_persistent"
    assert total_provider_calls == 0

    # RUN 2: Reload checkpoint manager from disk for restart of same job
    mgr_reload = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id=job_id,
        target_language="vi",
        quote_fingerprint="quote_async_d",
    )

    res2 = await smart.run_auto_smart_multivoice_blackbox(
        state=state,
        cues=cues,
        synthesize_segments=mock_synth,
        render_pipeline=lambda **kw: "out.mp4",
        source_media=str(src_mp4),
        checkpoint_manager=mgr_reload,
        validated_pools={"low": ["voice_male"], "high": ["voice_female"]},
        locked_speaker_voice_map={"spk_1": "voice_female", "spk_2": "voice_male"},
    )
    assert res2.get("ok") is False
    assert res2.get("status") == smart.FAIL_CLOSED_ASYNC_SUBMITTED_PRIOR_SUBMIT
    assert res2.get("async_task_id") == "task_c2_async_persistent"
    assert total_provider_calls == 0, "Restart of same job must still fail closed with 0 provider calls"


@_sync
async def test_smart_synth_adapter_async_submitted_raises_prior_submit_error(tmp_path: Path):
    """Direct adapter invariant: raises SubdubTTSAsyncSubmittedPriorSubmitError with 0 provider calls."""
    ws = str(tmp_path / "ws_adapter_async")
    job_id = "job_adapter_async"

    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id=job_id,
        target_language="vi",
        quote_fingerprint="quote_adapter_async",
    )

    cue = {"cue_id": "c1", "speaker_id": "spk_1", "text": "Câu adapter async", "start": 0.0, "end": 2.0}
    mgr.record_cue_async_submitted(
        cue,
        "voice_female",
        task_id="task_adapter_123",
        provider_request_id="req_adapter_456",
    )

    provider_called = False

    async def mock_base_synth(*args, **kwargs):
        nonlocal provider_called
        provider_called = True
        return {"chunks": []}

    adapter = smart.create_smart_synth_adapter(
        mock_base_synth,
        checkpoint_manager=mgr,
    )

    with pytest.raises(smart.SubdubTTSAsyncSubmittedPriorSubmitError) as exc_info:
        await adapter(
            cues=[cue],
            speaker_voice_map={"spk_1": "voice_female"},
        )

    err = exc_info.value
    assert err.task_id == "task_adapter_123"
    assert err.provider_request_id == "req_adapter_456"
    assert err.cue_id == "c1"
    assert provider_called is False, "base_synthesize MUST NOT be called for STATE_ASYNC_SUBMITTED cue"


@_sync
async def test_typeerror_post_submit_single_call_and_ambiguous_state(tmp_path: Path):
    """Verify that a TypeError raised after provider boundary makes exactly ONE provider call
    and transitions checkpoint state to STATE_AMBIGUOUS without any auto-resubmit.
    """
    ws = str(tmp_path / "ws_typeerror_single")
    job_id = "job_typeerror_01"
    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id=job_id,
        target_language="vi",
        quote_fingerprint="quote_fp_typeerror",
    )

    call_count = 0

    async def mock_base_synthesize(cues_arg, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise TypeError("post_submit_type_error_simulated")

    adapter = smart.create_smart_synth_adapter(
        mock_base_synthesize,
        checkpoint_manager=mgr,
    )

    cue = {"cue_id": "c1", "speaker_id": "spk_1", "text": "Câu test post-submit TypeError", "start": 0.0, "end": 2.0}

    with pytest.raises(TypeError, match="post_submit_type_error_simulated"):
        await adapter(cues=[cue], speaker_voice_map={"spk_1": "voice_female"})

    assert call_count == 1, f"Expected exactly 1 call, got {call_count} (double submit detected!)"

    # Verify checkpoint state is STATE_AMBIGUOUS
    key = mgr.compute_key(cue, "voice_female")
    assert key in mgr.entries
    assert mgr.entries[key]["state"] == subdub_tts_checkpoint.STATE_AMBIGUOUS
    assert "post_submit_type_error_simulated" in str(mgr.entries[key]["error_detail"])


@_sync
async def test_typeerror_restart_zero_provider_calls(tmp_path: Path):
    """Verify that restarting a job whose prior run failed with TypeError in provider boundary
    fails closed with 0 provider calls on restart. Total calls across both runs remain 1.
    """
    ws = str(tmp_path / "ws_typeerror_restart")
    job_id = "job_typeerror_restart_01"
    mgr1 = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id=job_id,
        target_language="vi",
        quote_fingerprint="quote_fp_typeerror_restart",
    )

    call_count = 0

    async def mock_base_synthesize(cues_arg, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise TypeError("post_submit_type_error_first_run")

    adapter1 = smart.create_smart_synth_adapter(
        mock_base_synthesize,
        checkpoint_manager=mgr1,
    )

    cue = {"cue_id": "c1", "speaker_id": "spk_1", "text": "Câu test restart after TypeError", "start": 0.0, "end": 2.0}

    with pytest.raises(TypeError):
        await adapter1(cues=[cue], speaker_voice_map={"spk_1": "voice_female"})

    assert call_count == 1

    # RUN 2: Restart same job
    mgr2 = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id=job_id,
        target_language="vi",
        quote_fingerprint="quote_fp_typeerror_restart",
    )
    adapter2 = smart.create_smart_synth_adapter(
        mock_base_synthesize,
        checkpoint_manager=mgr2,
    )

    with pytest.raises(subdub_tts_checkpoint.SubdubTTSAmbiguousSubmissionError):
        await adapter2(cues=[cue], speaker_voice_map={"spk_1": "voice_female"})

    assert call_count == 1, "Provider MUST NOT be invoked on restart for STATE_AMBIGUOUS cue"


@_sync
async def test_unproven_signature_zero_provider_calls(tmp_path: Path):
    """Verify that a callable with unsupported signature fails closed BEFORE provider boundary
    with 0 provider calls and raises SubdubTTSUnprovenSynthSignatureError.
    """
    ws = str(tmp_path / "ws_unproven_sig")
    job_id = "job_unproven_01"
    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id=job_id,
        target_language="vi",
        quote_fingerprint="quote_fp_unproven",
    )

    call_count = 0

    def bad_synth(x, y, z):
        nonlocal call_count
        call_count += 1
        return []

    adapter = smart.create_smart_synth_adapter(
        bad_synth,
        checkpoint_manager=mgr,
    )

    cue = {"cue_id": "c1", "speaker_id": "spk_1", "text": "Câu test unproven signature", "start": 0.0, "end": 2.0}

    with pytest.raises(smart.SubdubTTSUnprovenSynthSignatureError) as exc_info:
        await adapter(cues=[cue], speaker_voice_map={"spk_1": "voice_female"})

    assert exc_info.value.error_code == smart.FAIL_CLOSED_UNPROVEN_SYNTH_SIGNATURE
    assert call_count == 0, f"Expected 0 provider calls for invalid signature, got {call_count}"
    assert len(mgr.entries) == 0, "No checkpoint entry should be created for unproven signature"


@_sync
async def test_supported_signature_matrix(tmp_path: Path):
    """Verify that all supported signature forms (A: cues, voice_id=None; B: cues, *, voice_id=None;
    C: *args, **kwargs; D: cues, speaker_voice_map) select call shape pre-submit and invoke once.
    """
    cue = {"cue_id": "c1", "speaker_id": "spk_1", "text": "Câu test signature matrix", "start": 0.0, "end": 2.0}

    # Form A: async synth(cues, voice_id=None)
    calls_a = []
    async def synth_a(cues, voice_id=None):
        calls_a.append((cues, voice_id))
        return {"chunks": [{"cue_id": "c1", "audio": SAMPLE_VALID_MP3, "audio_duration": 2.0}], "provider": "mock_a"}

    mgr_a = subdub_tts_checkpoint.SubdubTTSCheckpointManager(workspace=str(tmp_path / "ws_sig_a"), job_id="job_a")
    adapter_a = smart.create_smart_synth_adapter(synth_a, checkpoint_manager=mgr_a)
    res_a = await adapter_a(cues=[cue], speaker_voice_map={"spk_1": "voice_a"})
    assert len(calls_a) == 1
    assert calls_a[0][1] == "voice_a"
    assert len(res_a["chunks"]) == 1

    # Form B: async synth(cues, *, voice_id=None)
    calls_b = []
    async def synth_b(cues, *, voice_id=None):
        calls_b.append((cues, voice_id))
        return {"chunks": [{"cue_id": "c1", "audio": SAMPLE_VALID_MP3, "audio_duration": 2.0}], "provider": "mock_b"}

    mgr_b = subdub_tts_checkpoint.SubdubTTSCheckpointManager(workspace=str(tmp_path / "ws_sig_b"), job_id="job_b")
    adapter_b = smart.create_smart_synth_adapter(synth_b, checkpoint_manager=mgr_b)
    res_b = await adapter_b(cues=[cue], speaker_voice_map={"spk_1": "voice_b"})
    assert len(calls_b) == 1
    assert calls_b[0][1] == "voice_b"
    assert len(res_b["chunks"]) == 1

    # Form C: Key4U live route wrapper signature (*args, **kwargs)
    calls_c = []
    async def synth_c(*args, **kwargs):
        calls_c.append((args, kwargs))
        return {"chunks": [{"cue_id": "c1", "audio": SAMPLE_VALID_MP3, "audio_duration": 2.0}], "provider": "mock_c"}

    mgr_c = subdub_tts_checkpoint.SubdubTTSCheckpointManager(workspace=str(tmp_path / "ws_sig_c"), job_id="job_c")
    adapter_c = smart.create_smart_synth_adapter(synth_c, checkpoint_manager=mgr_c)
    res_c = await adapter_c(cues=[cue], speaker_voice_map={"spk_1": "voice_c"}, allow_admin=True)
    assert len(calls_c) == 1
    assert calls_c[0][1].get("voice_id") == "voice_c"
    assert calls_c[0][1].get("allow_admin") is True
    # Verify original cues positional argument was NOT duplicated in args
    assert len(calls_c[0][0]) == 1, "args should only contain [cue], not duplicate cues"
    assert len(res_c["chunks"]) == 1

    # Form D: cues, speaker_voice_map
    calls_d = []
    async def synth_d(cues, speaker_voice_map):
        calls_d.append((cues, speaker_voice_map))
        return {"chunks": [{"cue_id": "c1", "audio": SAMPLE_VALID_MP3, "audio_duration": 2.0}], "provider": "mock_d"}

    mgr_d = subdub_tts_checkpoint.SubdubTTSCheckpointManager(workspace=str(tmp_path / "ws_sig_d"), job_id="job_d")
    adapter_d = smart.create_smart_synth_adapter(synth_d, checkpoint_manager=mgr_d)
    res_d = await adapter_d(cues=[cue], speaker_voice_map={"spk_1": "voice_d"})
    assert len(calls_d) == 1
    assert calls_d[0][1].get("spk_1") == "voice_d"
    assert len(res_d["chunks"]) == 1



