"""Focused Test Suite for R16_09C: V2V Product Bridge & Generic Worker Race Guard.

P0.PRODUCT_VIDEO_VIDEO_AI_VIDEO_REFERENCE_FAL_V2V_ONE_SHOT_PRODUCT_BRIDGE_RACE_GUARD_SOURCE_REMEDIATION_R16_09C
Issue: #1155
Repo: manhtoangreensky-wq/bot

FOCUSED TEST MATRIX:
1. normal video_ai_prompt mapping remains unchanged
2. generic daemon rejects video_ai_video_reference without Owner acceptance authority
3. owner-acceptance V2V job passes product validation
4. V2V maps product_type=video_ai_video_reference
5. V2V maps required_capability=video_to_video
6. exact Fal provider and model are locked
7. source_video_path is retained
8. missing source video fails before provider
9. V2V contains no image input contamination
10. forged customer Owner auth remains ignored/rejected
11. wrong Owner job ID fails closed
12. wrong product/provider/model authority fails closed
13. generic worker active blocks one-shot runner before claim
14. unknown service state blocks before claim
15. generic worker inactive permits progression to mocked targeted claim
16. exact job mismatch still blocks
17. provider calls remain zero in all guard/negative tests
18. wallet mutations remain zero
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from scripts.vps.run_web_product_video_live_acceptance_once import (
    run_live_acceptance_once,
)
from services.web_product_video_worker_consumer import (
    InvalidJobEnvelopeError,
    WebClaimResponse,
    WebProductVideoDispatcherClient,
    map_web_job_to_bot_runtime,
    validate_claimed_job,
)


@pytest.fixture(autouse=True)
def isolate_test_db(tmp_path, monkeypatch):
    """Ensure every test runs against a clean SQLite test database."""
    test_db = str(tmp_path / "bridge_test_isolated.db")
    monkeypatch.setenv("DB_PATH", test_db)
    monkeypatch.setenv("SQLITE_DB_PATH", test_db)
    monkeypatch.setenv("WEB_PRODUCT_VIDEO_WORKER_ENABLED", "true")
    monkeypatch.setenv("PROVIDER_SPEND_FREEZE", "1")
    return test_db


def _canonical_v2v_job(
    job_id: str = "pvj_v2v_canonical_001",
    product_key: str = "video_ai_video_reference",
    source_video_path: str = "https://fal.media/files/input_canonical.mp4",
) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "request_id": f"req_{job_id}",
        "product_key": product_key,
        "account_id": "acc_owner_test",
        "status": "processing",
        "payload": {
            "prompt": "Cinematic transformation with high fidelity",
            "aspect_ratio": "9:16",
            "duration": 5.0,
            "quality_tier": "advanced",
            "source_video_path": source_video_path,
        },
    }


def _canonical_owner_auth(
    job_id: str = "pvj_v2v_canonical_001",
    product_type: str = "video_ai_video_reference",
    provider: str = "fal_video",
    model: str = "fal-ai/wan/v2.2-a14b/video-to-video",
    capability: str = "video_to_video",
    tier: str = "500",
    runtime_sha: str | None = None,
) -> dict[str, Any]:
    from services.remote_worker_api import resolve_runtime_sha
    sha = runtime_sha or resolve_runtime_sha() or "d057cc6b4350ebcc09fbff6f03e3c1870995099f"
    return {
        "owner_authorized": True,
        "acceptance_type": "owner_authorized_live_acceptance",
        "job_id": job_id,
        "user_id": "acc_owner_test",
        "product_type": product_type,
        "provider": provider,
        "model": model,
        "capability": capability,
        "tier": tier,
        "max_provider_spend": 0.40,
        "max_provider_spend_unit": "USD",
        "spend_unit": "USD",
        "expected_duration_seconds": 5,
        "max_provider_submits": 1,
        "runtime_sha": sha,
        "expires_at": time.time() + 3600,
    }


# ---------------------------------------------------------------------------
# 1. Normal video_ai_prompt mapping remains unchanged
# ---------------------------------------------------------------------------
def test_1_normal_video_ai_prompt_mapping_unchanged():
    normal_job = {
        "job_id": "pvj_normal_prompt_001",
        "request_id": "req_normal_prompt_001",
        "product_key": "video_ai_prompt",
        "account_id": "acc_user_normal",
        "status": "processing",
        "payload": {
            "prompt": "A scenic sunset over misty mountains",
            "aspect_ratio": "16:9",
            "duration": 5.0,
            "quality_tier": "standard",
        },
    }
    is_valid, reason = validate_claimed_job(normal_job)
    assert is_valid is True, f"Normal prompt job validation failed: {reason}"

    req = map_web_job_to_bot_runtime(normal_job)
    assert req.product_type == "video_ai_prompt"
    assert req.video_flow_type == "video_ai_prompt"
    assert req.required_capability == "text_to_video"
    assert req.prompt == "A scenic sunset over misty mountains"
    assert req.ratio == "16:9"
    assert req.duration_seconds == 5.0
    assert req.source_video_path == ""
    assert req.metadata["admin_no_charge"] is True
    assert req.metadata["no_wallet_charge"] is True


# ---------------------------------------------------------------------------
# 2. Generic daemon rejects video_ai_video_reference without Owner auth
# ---------------------------------------------------------------------------
def test_2_generic_daemon_rejects_video_ai_video_reference_without_owner_auth():
    job = _canonical_v2v_job()
    # Call without owner_acceptance_auth (generic daemon execution path)
    is_valid, reason = validate_claimed_job(job)
    assert is_valid is False
    assert "UNSUPPORTED_PRODUCT" in reason
    assert "video_ai_video_reference" in reason


# ---------------------------------------------------------------------------
# 3. Owner-acceptance V2V job passes product validation
# ---------------------------------------------------------------------------
def test_3_owner_acceptance_v2v_job_passes_product_validation():
    job = _canonical_v2v_job()
    auth = _canonical_owner_auth()
    is_valid, reason = validate_claimed_job(job, owner_acceptance_auth=auth)
    assert is_valid is True, f"V2V job with owner auth failed validation: {reason}"


# ---------------------------------------------------------------------------
# 4. V2V maps product_type=video_ai_video_reference
# ---------------------------------------------------------------------------
def test_4_v2v_maps_product_type_video_ai_video_reference():
    job = _canonical_v2v_job()
    auth = _canonical_owner_auth()
    req = map_web_job_to_bot_runtime(job, owner_acceptance_auth=auth)
    assert req.product_type == "video_ai_video_reference"
    assert req.video_flow_type == "video_ai_video_reference"


# ---------------------------------------------------------------------------
# 5. V2V maps required_capability=video_to_video
# ---------------------------------------------------------------------------
def test_5_v2v_maps_required_capability_video_to_video():
    job = _canonical_v2v_job()
    auth = _canonical_owner_auth()
    req = map_web_job_to_bot_runtime(job, owner_acceptance_auth=auth)
    assert req.required_capability == "video_to_video"


# ---------------------------------------------------------------------------
# 6. Exact Fal provider and model are locked
# ---------------------------------------------------------------------------
def test_6_exact_fal_provider_and_model_locked():
    job = _canonical_v2v_job()
    auth = _canonical_owner_auth()
    req = map_web_job_to_bot_runtime(job, owner_acceptance_auth=auth)
    assert req.metadata["provider"] == "fal_video"
    assert req.metadata["model"] == "fal-ai/wan/v2.2-a14b/video-to-video"
    assert req.metadata["selected_provider"] == "fal_video"
    assert req.metadata["selected_model"] == "fal-ai/wan/v2.2-a14b/video-to-video"


# ---------------------------------------------------------------------------
# 7. source_video_path is retained
# ---------------------------------------------------------------------------
def test_7_source_video_path_retained():
    job = _canonical_v2v_job(source_video_path="https://fal.media/files/source_wan.mp4")
    auth = _canonical_owner_auth()
    req = map_web_job_to_bot_runtime(job, owner_acceptance_auth=auth)
    assert req.source_video_path == "https://fal.media/files/source_wan.mp4"


# ---------------------------------------------------------------------------
# 8. Missing source video fails before provider
# ---------------------------------------------------------------------------
def test_8_missing_source_video_fails_before_provider():
    job_no_src = _canonical_v2v_job(source_video_path="")
    auth = _canonical_owner_auth()
    is_valid, reason = validate_claimed_job(job_no_src, owner_acceptance_auth=auth)
    assert is_valid is False
    assert "SOURCE_VIDEO" in reason or "MISSING_SOURCE_VIDEO" in reason

    with pytest.raises(InvalidJobEnvelopeError, match="SOURCE_VIDEO"):
        map_web_job_to_bot_runtime(job_no_src, owner_acceptance_auth=auth)


# ---------------------------------------------------------------------------
# 9. V2V contains no image input contamination
# ---------------------------------------------------------------------------
def test_9_v2v_contains_no_image_input_contamination():
    job = _canonical_v2v_job()
    job["payload"]["image_paths"] = ["https://example.com/fake_contaminant.png"]
    job["payload"]["images"] = ["https://example.com/fake_contaminant.png"]
    auth = _canonical_owner_auth()
    req = map_web_job_to_bot_runtime(job, owner_acceptance_auth=auth)
    assert req.image_paths == []


# ---------------------------------------------------------------------------
# 10. Forged customer Owner auth remains ignored/rejected
# ---------------------------------------------------------------------------
def test_10_forged_customer_owner_auth_remains_ignored_or_rejected():
    job = _canonical_v2v_job()
    # Customer attempts to self-authorize by injecting owner_acceptance_auth inside payload
    job["payload"]["owner_acceptance_auth"] = _canonical_owner_auth()
    job["owner_acceptance_auth"] = _canonical_owner_auth()

    # Generic daemon validates without external auth argument
    is_valid, reason = validate_claimed_job(job)
    assert is_valid is False
    assert "UNSUPPORTED_PRODUCT" in reason


# ---------------------------------------------------------------------------
# 11. Wrong Owner job ID fails closed
# ---------------------------------------------------------------------------
def test_11_wrong_owner_job_id_fails_closed():
    job = _canonical_v2v_job(job_id="pvj_job_actual_111")
    auth_wrong_job = _canonical_owner_auth(job_id="pvj_job_different_999")
    is_valid, reason = validate_claimed_job(job, owner_acceptance_auth=auth_wrong_job)
    assert is_valid is False
    assert "MISMATCH" in reason or "JOB_ID" in reason


# ---------------------------------------------------------------------------
# 12. Wrong product/provider/model authority fails closed
# ---------------------------------------------------------------------------
def test_12_wrong_product_provider_model_authority_fails_closed():
    job = _canonical_v2v_job()

    # Wrong product
    auth_bad_prod = _canonical_owner_auth(product_type="video_ai_prompt")
    is_valid, reason = validate_claimed_job(job, owner_acceptance_auth=auth_bad_prod)
    assert is_valid is False
    assert "PRODUCT_MISMATCH" in reason

    # Wrong provider
    auth_bad_prov = _canonical_owner_auth(provider="shopaikey_video")
    is_valid, reason = validate_claimed_job(job, owner_acceptance_auth=auth_bad_prov)
    assert is_valid is False
    assert "PROVIDER_MISMATCH" in reason

    # Wrong model
    auth_bad_model = _canonical_owner_auth(model="unauthorized-v2v-model")
    is_valid, reason = validate_claimed_job(job, owner_acceptance_auth=auth_bad_model)
    assert is_valid is False
    assert "MODEL_MISMATCH" in reason


# ---------------------------------------------------------------------------
# 13. Generic worker active blocks one-shot runner before claim
# ---------------------------------------------------------------------------
def test_13_generic_worker_active_blocks_one_shot_runner_before_claim(tmp_path, capsys):
    auth_file = tmp_path / "owner_auth.json"
    auth_file.write_text(json.dumps(_canonical_owner_auth(job_id="pvj_race_001")), encoding="utf-8")

    mock_client = MagicMock(spec=WebProductVideoDispatcherClient)
    # Service checker reports active
    mock_checker = MagicMock(return_value=(False, "active"))

    exit_code = run_live_acceptance_once(
        expected_job_id="pvj_race_001",
        owner_auth_file=auth_file,
        client=mock_client,
        service_checker=mock_checker,
    )

    assert exit_code != 0
    # Must NOT call claim() when generic worker is active!
    mock_client.claim.assert_not_called()

    captured = capsys.readouterr()
    combined_out = captured.out + captured.err
    assert "STATUS=BLOCKED_GENERIC_WEB_PRODUCT_VIDEO_WORKER_ACTIVE" in combined_out
    assert "TARGET_JOB_CLAIM=0" in combined_out
    assert "PROVIDER_CALLS=0" in combined_out


# ---------------------------------------------------------------------------
# 14. Unknown service state blocks before claim
# ---------------------------------------------------------------------------
def test_14_unknown_service_state_blocks_before_claim(tmp_path, capsys):
    auth_file = tmp_path / "owner_auth.json"
    auth_file.write_text(json.dumps(_canonical_owner_auth(job_id="pvj_race_002")), encoding="utf-8")

    mock_client = MagicMock(spec=WebProductVideoDispatcherClient)
    # Service checker reports unknown / activating state
    mock_checker = MagicMock(return_value=(False, "activating"))

    exit_code = run_live_acceptance_once(
        expected_job_id="pvj_race_002",
        owner_auth_file=auth_file,
        client=mock_client,
        service_checker=mock_checker,
    )

    assert exit_code != 0
    mock_client.claim.assert_not_called()

    captured = capsys.readouterr()
    combined_out = captured.out + captured.err
    assert "STATUS=BLOCKED_UNKNOWN_SERVICE_STATE" in combined_out
    assert "TARGET_JOB_CLAIM=0" in combined_out
    assert "PROVIDER_CALLS=0" in combined_out


# ---------------------------------------------------------------------------
# 15. Generic worker inactive permits progression to mocked targeted claim
# ---------------------------------------------------------------------------
def test_15_generic_worker_inactive_permits_progression_to_mocked_targeted_claim(tmp_path):
    auth_file = tmp_path / "owner_auth.json"
    auth_file.write_text(json.dumps(_canonical_owner_auth(job_id="pvj_race_003")), encoding="utf-8")

    mock_client = MagicMock(spec=WebProductVideoDispatcherClient)
    mock_client.claim.return_value = WebClaimResponse(
        ok=True,
        idle=False,
        job=_canonical_v2v_job(job_id="pvj_race_003"),
    )
    mock_checker = MagicMock(return_value=(True, "inactive"))

    exit_code = run_live_acceptance_once(
        expected_job_id="pvj_race_003",
        owner_auth_file=auth_file,
        dry_run=True,
        client=mock_client,
        service_checker=mock_checker,
    )

    assert exit_code == 0
    mock_client.claim.assert_called_once_with(lease_seconds=300, target_job_id="pvj_race_003")


# ---------------------------------------------------------------------------
# 16. Exact job mismatch still blocks
# ---------------------------------------------------------------------------
def test_16_exact_job_mismatch_still_blocks(tmp_path, capsys):
    auth_file = tmp_path / "owner_auth.json"
    auth_file.write_text(json.dumps(_canonical_owner_auth(job_id="pvj_target_expected")), encoding="utf-8")

    mock_client = MagicMock(spec=WebProductVideoDispatcherClient)
    # Claim returns a different job_id
    mock_client.claim.return_value = WebClaimResponse(
        ok=True,
        idle=False,
        job=_canonical_v2v_job(job_id="pvj_mismatched_claimed"),
    )
    mock_checker = MagicMock(return_value=(True, "inactive"))

    exit_code = run_live_acceptance_once(
        expected_job_id="pvj_target_expected",
        owner_auth_file=auth_file,
        client=mock_client,
        service_checker=mock_checker,
    )

    assert exit_code != 0
    captured = capsys.readouterr()
    combined_out = captured.out + captured.err
    assert "STATUS=BLOCKED_TARGET_JOB_ID_MISMATCH" in combined_out
    assert "PROVIDER_CALLS=0" in combined_out


# ---------------------------------------------------------------------------
# 17. Provider calls remain zero in all guard/negative tests
# ---------------------------------------------------------------------------
def test_17_provider_calls_remain_zero_in_all_guard_negative_tests(tmp_path, capsys):
    # Case A: Missing source video
    job_no_src = _canonical_v2v_job(source_video_path="")
    auth = _canonical_owner_auth()
    is_valid, _ = validate_claimed_job(job_no_src, owner_acceptance_auth=auth)
    assert is_valid is False

    # Case B: Inactive worker but unclaimable / idle target
    auth_file = tmp_path / "owner_auth_idle.json"
    auth_file.write_text(json.dumps(_canonical_owner_auth(job_id="pvj_idle_job")), encoding="utf-8")
    mock_client = MagicMock(spec=WebProductVideoDispatcherClient)
    mock_client.claim.return_value = WebClaimResponse(ok=True, idle=True, job=None)
    mock_checker = MagicMock(return_value=(True, "inactive"))

    exit_code = run_live_acceptance_once(
        expected_job_id="pvj_idle_job",
        owner_auth_file=auth_file,
        client=mock_client,
        service_checker=mock_checker,
    )
    assert exit_code != 0
    captured = capsys.readouterr()
    assert "STATUS=BLOCKED_TARGET_JOB_NOT_CLAIMABLE" in captured.out
    assert "PROVIDER_CALLS=0" in captured.out


# ---------------------------------------------------------------------------
# 18. Wallet mutations remain zero
# ---------------------------------------------------------------------------
def test_18_wallet_mutations_remain_zero():
    job = _canonical_v2v_job()
    auth = _canonical_owner_auth()
    req = map_web_job_to_bot_runtime(job, owner_acceptance_auth=auth)
    assert req.metadata["admin_no_charge"] is True
    assert req.metadata["no_wallet_charge"] is True
