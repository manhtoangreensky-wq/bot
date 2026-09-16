from __future__ import annotations

import base64
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest

from services import (
    subdub_canary_harness as canary,
    subdub_tts_checkpoint as checkpoint,
)

# Valid 358-byte MP3 for mock synthesis validation
SAMPLE_VALID_MP3 = base64.b64decode(
    "SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjYyLjEyLjEwMQAAAAAAAAAAAAAA//sQxAAABHQTVVSQgDCmCa83GiACAAGtOUAAAVk6PVBQCAYJAfB8HwfKAgCAYRB8H9QIOxOH+INwBJP2wGA4HA4AAAAAACiJKpkUZAjpAkgWo/eFAfATG/AilC+oGhL8JA0qCgAYMAD/+xLEAoPFWB0gHeAAKKSDpIK8AAXMCQC8QASGAOB4Z+72pmMDlmHEESYMAH5gQgYGBSBMYF4DxZq0lflI8wEwETAAA2MDYIQzblDTLrF3ML8H0wWQHTALAtMCUB8wIwG0T59JA5JIAAr/+xDEAoAEtENSuZKAEJcGpuuYMARhEdKhTBbpmtFc+iKq+RLMu79/N5ZP4GFfx4sXwMd+FVAMXYXAAAAmEoRic8ySQagdXkkSQpUtPJRJFBQFYxhTvEt0qC3EqkxBTUUzLjEwMKqqqg=="
)


def _get_locked_cues() -> tuple[list[dict[str, Any]], dict[str, str]]:
    cues = [
        {
            "cue_id": "cue_001",
            "id": "cue_001",
            "speaker_id": "chunk_00:speaker_0",
            "text": "Lời thoại phụ đề tiếng Việt thứ 1 chuẩn xác",
            "start": 0.0,
            "end": 2.0,
        },
        {
            "cue_id": "cue_002",
            "id": "cue_002",
            "speaker_id": "chunk_00:speaker_1",
            "text": "Lời thoại phụ đề tiếng Việt thứ 2 chuẩn xác",
            "start": 2.5,
            "end": 4.5,
        },
        {
            "cue_id": "cue_003",
            "id": "cue_003",
            "speaker_id": "chunk_00:speaker_2",
            "text": "Lời thoại phụ đề tiếng Việt thứ 3 chuẩn xác",
            "start": 5.0,
            "end": 7.0,
        },
    ]
    voice_map = {
        "chunk_00:speaker_0": "English_ConfidentWoman",
        "chunk_00:speaker_1": "English_DecentYoungMan",
        "chunk_00:speaker_2": "English_PassionateWarrior",
    }
    return cues, voice_map


def test_canary_harness_constants_match_spec06a_manifest():
    assert canary.CANARY_JOB_ID == "c11830a5_canary_spec06b_three_voice"
    assert canary.LOCKED_PROVIDER == "key4u_minimax"
    assert canary.LOCKED_MODEL == "speech-02-hd"
    assert canary.LOCKED_TARGET_LANGUAGE == "vi"
    assert canary.APPROVED_BASE_SHA == "5e5f3bc5ec9435f43af00aac8e1c7eb7a5d7e397"
    assert canary.MAX_PAID_SUBMITS == 3
    assert canary.MAX_AUTO_SUBMITS_PER_UNIT == 1
    assert canary.MAX_PROVIDER_SPEND == 0.05
    assert canary.MAX_PROVIDER_SPEND_UNIT == "USD"
    assert canary.FAIL_FAST_ON_FIRST_AMBIGUOUS is True

    assert len(canary.LOCKED_CANARY_UNITS) == 3
    expected_keys = {
        "unit_44f73b7d827cbb74507537ae",
        "unit_6ec0b605fa5f1ef983c33ed8",
        "unit_c6515b5f8a22fc4245e25266",
    }
    assert set(canary.LOCKED_CANARY_UNITS.keys()) == expected_keys


def test_canary_unauthorized_cue_rejected(tmp_path: Path):
    harness = canary.SubdubCanaryExecutionHarness(workspace=str(tmp_path))
    unauthorized_cue = {
        "cue_id": "cue_999",
        "speaker_id": "chunk_00:speaker_0",
        "text": "Câu nói không được ủy quyền.",
    }
    with pytest.raises(canary.CanaryUnauthorizedUnitError) as exc_info:
        harness.execute_unit(
            cue=unauthorized_cue,
            voice_id="English_ConfidentWoman",
            synthesize_fn=lambda **kwargs: (SAMPLE_VALID_MP3, 1.0, "req_1"),
        )
    assert "not in the locked 3-voice canary allowlist" in str(exc_info.value)
    assert harness.total_submits == 0


def test_canary_contract_drift_rejected(tmp_path: Path):
    harness = canary.SubdubCanaryExecutionHarness(workspace=str(tmp_path))
    # Correct cue_id but mutated voice
    cues, _ = _get_locked_cues()
    with pytest.raises(canary.CanaryUnauthorizedUnitError):
        harness.execute_unit(
            cue=cues[0],
            voice_id="English_WrongVoice",
            synthesize_fn=lambda **kwargs: (SAMPLE_VALID_MP3, 1.0, "req_1"),
        )
    assert harness.total_submits == 0


def test_canary_provider_and_model_mismatch_rejected(tmp_path: Path):
    harness = canary.SubdubCanaryExecutionHarness(workspace=str(tmp_path))
    cues, voice_map = _get_locked_cues()
    cue0 = cues[0]
    voice0 = voice_map[cue0["speaker_id"]]

    # Provider mismatch
    with pytest.raises(canary.CanaryProviderMismatchError) as exc:
        harness.execute_unit(
            cue=cue0,
            voice_id=voice0,
            synthesize_fn=lambda **kwargs: (SAMPLE_VALID_MP3, 1.0, "req_1"),
            provider="elevenlabs",
        )
    assert "unauthorized_provider" in str(exc.value)

    # Model mismatch
    with pytest.raises(canary.CanaryProviderMismatchError) as exc:
        harness.execute_unit(
            cue=cue0,
            voice_id=voice0,
            synthesize_fn=lambda **kwargs: (SAMPLE_VALID_MP3, 1.0, "req_1"),
            model="speech-01",
        )
    assert "unauthorized_model" in str(exc.value)
    assert harness.total_submits == 0


def test_canary_runtime_sha_mismatch_rejected(tmp_path: Path):
    harness = canary.SubdubCanaryExecutionHarness(workspace=str(tmp_path))
    with pytest.raises(canary.CanaryRuntimeSHAMismatchError) as exc:
        harness.verify_runtime_sha(current_sha="deadbeef1234567890abcdef1234567890abcdef")
    assert "runtime_sha_drift" in str(exc.value)


def test_canary_prestate_not_clean_rejected(tmp_path: Path):
    ws = str(tmp_path)
    ckpt = checkpoint.SubdubTTSCheckpointManager(
        workspace=ws,
        job_id=canary.CANARY_JOB_ID,
        target_language="vi",
    )
    # Simulate dirty state on unit 1
    unit1_key = "unit_44f73b7d827cbb74507537ae"
    ckpt.entries[unit1_key] = {
        "tts_unit_key": unit1_key,
        "cue_id": "cue_001",
        "state": checkpoint.STATE_AMBIGUOUS,
    }
    ckpt._save_manifest_atomic()

    harness = canary.SubdubCanaryExecutionHarness(
        workspace=ws,
        checkpoint_mgr=ckpt,
    )
    with pytest.raises(canary.CanaryPrestateError) as exc:
        harness.verify_checkpoint_prestate()
    assert "dirty_canary_prestate" in str(exc.value)


def test_canary_hard_max_3_submits_enforced(tmp_path: Path):
    harness = canary.SubdubCanaryExecutionHarness(workspace=str(tmp_path))
    harness.total_submits = 3
    cues, voice_map = _get_locked_cues()

    with pytest.raises(canary.CanarySubmitLimitExceededError) as exc:
        harness.execute_unit(
            cue=cues[0],
            voice_id=voice_map[cues[0]["speaker_id"]],
            synthesize_fn=lambda **kwargs: (SAMPLE_VALID_MP3, 1.0, "req_1"),
        )
    assert "hard_max_submits_exceeded" in str(exc.value)


def test_canary_unit_resubmit_forbidden(tmp_path: Path):
    harness = canary.SubdubCanaryExecutionHarness(workspace=str(tmp_path))
    cues, voice_map = _get_locked_cues()
    cue0 = cues[0]
    voice0 = voice_map[cue0["speaker_id"]]

    unit_key = "unit_44f73b7d827cbb74507537ae"
    harness.unit_submits[unit_key] = 1

    with pytest.raises(canary.CanarySubmitLimitExceededError) as exc:
        harness.execute_unit(
            cue=cue0,
            voice_id=voice0,
            synthesize_fn=lambda **kwargs: (SAMPLE_VALID_MP3, 1.0, "req_1"),
        )
    assert "unit_resubmit_forbidden" in str(exc.value)


def test_canary_spend_limit_guard_enforced(tmp_path: Path):
    # Set max_spend very low e.g. 0.0001
    harness = canary.SubdubCanaryExecutionHarness(
        workspace=str(tmp_path),
        max_spend=0.0001,
    )
    cues, voice_map = _get_locked_cues()
    with pytest.raises(canary.CanarySpendLimitExceededError) as exc:
        harness.execute_unit(
            cue=cues[0],
            voice_id=voice_map[cues[0]["speaker_id"]],
            synthesize_fn=lambda **kwargs: (SAMPLE_VALID_MP3, 1.0, "req_1"),
        )
    assert "spend_limit_exceeded" in str(exc.value)


def test_canary_fail_fast_on_provider_exception(tmp_path: Path):
    ws = str(tmp_path)
    harness = canary.SubdubCanaryExecutionHarness(workspace=ws)
    cues, voice_map = _get_locked_cues()

    call_count = 0

    def mock_synth(text, voice_id, model, cue_id, target_language):
        nonlocal call_count
        call_count += 1
        if cue_id == "cue_002":
            raise ConnectionResetError("Provider TCP reset simulation")
        return SAMPLE_VALID_MP3, 1.5, f"mock_req_{cue_id}"

    # Unit 1 succeeds
    res1 = harness.execute_unit(cues[0], voice_map[cues[0]["speaker_id"]], mock_synth)
    assert res1["state"] == checkpoint.STATE_SUCCEEDED
    assert harness.total_submits == 1
    assert not harness.aborted

    # Unit 2 raises exception and fail-fast aborts
    with pytest.raises(canary.CanaryAmbiguousAbortError) as exc:
        harness.execute_unit(cues[1], voice_map[cues[1]["speaker_id"]], mock_synth)
    assert "canary_fail_fast_aborted" in str(exc.value)
    assert harness.total_submits == 2
    assert harness.aborted is True

    # Unit 3 MUST NOT execute at all!
    with pytest.raises(canary.CanaryAmbiguousAbortError) as exc:
        harness.execute_unit(cues[2], voice_map[cues[2]["speaker_id"]], mock_synth)
    assert "prior failure halted canary execution" in str(exc.value)

    # Provider was called exactly twice (unit 1 and unit 2), unit 3 was NEVER touched!
    assert call_count == 2
    assert harness.total_submits == 2


def test_canary_fail_fast_on_corrupt_artifact(tmp_path: Path):
    ws = str(tmp_path)
    harness = canary.SubdubCanaryExecutionHarness(workspace=ws)
    cues, voice_map = _get_locked_cues()

    call_count = 0

    def mock_synth(text, voice_id, model, cue_id, target_language):
        nonlocal call_count
        call_count += 1
        if cue_id == "cue_002":
            # Return garbage audio that cannot be decoded as MP3
            return b"corrupt-fake-mp3-payload", 1.5, f"mock_req_{cue_id}"
        return SAMPLE_VALID_MP3, 1.5, f"mock_req_{cue_id}"

    # Unit 1 succeeds
    harness.execute_unit(cues[0], voice_map[cues[0]["speaker_id"]], mock_synth)

    # Unit 2 fails artifact validation and fail-fast aborts
    with pytest.raises(canary.CanaryAmbiguousAbortError) as exc:
        harness.execute_unit(cues[1], voice_map[cues[1]["speaker_id"]], mock_synth)
    assert "failed artifact validation" in str(exc.value)
    assert harness.aborted is True

    # Unit 3 blocked
    with pytest.raises(canary.CanaryAmbiguousAbortError):
        harness.execute_unit(cues[2], voice_map[cues[2]["speaker_id"]], mock_synth)

    assert call_count == 2


def test_canary_mock_batch_happy_path(tmp_path: Path):
    ws = str(tmp_path)
    harness = canary.SubdubCanaryExecutionHarness(
        workspace=ws,
        runtime_sha=canary.APPROVED_BASE_SHA,
    )
    cues, voice_map = _get_locked_cues()

    call_records = []

    def mock_synth(text, voice_id, model, cue_id, target_language):
        call_records.append((cue_id, voice_id, model))
        return SAMPLE_VALID_MP3, 1.8, f"mock_req_{cue_id}"

    batch_res = harness.execute_batch(
        cues=cues,
        voice_map=voice_map,
        synthesize_fn=mock_synth,
        current_sha=canary.APPROVED_BASE_SHA,
    )

    assert batch_res["total_submits"] == 3
    assert batch_res["units_completed"] == 3
    assert batch_res["aborted"] is False
    assert batch_res["accumulated_spend_usd"] <= 0.05
    assert len(call_records) == 3

    # Verify manifest on disk
    manifest_path = os.path.join(ws, "subdub_tts_manifest.json")
    assert os.path.isfile(manifest_path)

    # Re-verify with a new harness instance on same workspace
    new_harness = canary.SubdubCanaryExecutionHarness(workspace=ws)
    # Unit 1 should be recognized as reusable
    cue0 = cues[0]
    voice0 = voice_map[cue0["speaker_id"]]
    res_reuse = new_harness.execute_unit(cue0, voice0, mock_synth)
    assert res_reuse["reused"] is True
    # Zero new submissions made on reuse!
    assert new_harness.total_submits == 0
