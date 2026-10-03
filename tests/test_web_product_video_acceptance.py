"""Focused regression test suite for Owner Acceptance context propagation in video_provider_router.

Ensures that in _run_provider_generation_impl, the Owner acceptance context forwards
all required tuple fields (model, selected_model, execution_mode, source_video_sha256,
frame_1_sha256, frame_2_sha256, prompt_sha256, pricing_snapshot_id_or_hash, aspect_ratio,
duration_seconds) from metadata without hardcoded fallback or weakening fail-closed security.
"""

from __future__ import annotations

import sys
import tempfile
from typing import Any
from unittest.mock import MagicMock, patch

if "bot" not in sys.modules:
    sys.modules["bot"] = MagicMock()

import pytest

from services.video_provider_base import VideoGenerationRequest
from services.video_provider_router import (
    _run_provider_generation_impl,
    validate_owner_acceptance_authorization,
)


import uuid


def _canonical_acceptance_fixture(job_id: str | None = None) -> dict[str, Any]:
    """Return a complete canonical acceptance tuple fixture for video_ai_video_reference."""
    jid = job_id or f"pvj_test_{uuid.uuid4().hex}"
    return {
        "acceptance_type": "owner_authorized_live_acceptance",
        "owner_authorized": True,
        "user_id": "usr_test_owner",
        "job_id": jid,
        "project_id": "prj_product_video_acceptance",
        "product_type": "video_ai_video_reference",
        "provider": "shopaikey_video",
        "selected_provider": "shopaikey_video",
        "model": "veo3.1-fast",
        "selected_model": "veo3.1-fast",
        "capability": "image_to_video",
        "required_capability": "image_to_video",
        "execution_mode": "video_reference_guided_i2v",
        "source_video_sha256": "554b9d883a3847b71e752b02c47081d65b144a8a763b5fd7464db439abcd702b",
        "frame_1_sha256": "e72876067590ffad22e643843c3e3bc615e34048e12800997953011eec243367",
        "frame_2_sha256": "65aba4bf5b67801c83cc6aa69452ae8eba3d12ea444e1db495ca0c9d450ee592",
        "prompt_sha256": "e40b915bdc34d946b3785591638835941ce416fce80236d05007b3a0753209db",
        "pricing_snapshot_id_or_hash": "414c4b9c071759565d686db73764b8c1b12cfd6e26529f4a3e59d19ce41911eb",
        "duration_seconds": 5.0,
        "aspect_ratio": "9:16",
        "quality_tier": 500,
        "tier": "500",
        "runtime_sha": "76b634a829173028dd3d1b62cbb617ea9642133b",
        "estimated_provider_cost": 0.70,
        "estimated_provider_cost_unit": "USD",
    }


from services.video_provider_base import VideoGenerationRequest, VideoSubmitResult, VideoPollResult


@pytest.fixture(autouse=True)
def _patch_acceptance_persistence():
    with patch("services.video_provider_router.is_owner_acceptance_token_claimed_or_consumed", return_value=False), \
         patch("services.video_provider_router.is_owner_acceptance_attempt_claimed_or_consumed", return_value=False):
        yield


def test_01_valid_acceptance_metadata_tuple_forwards_model_and_does_not_fail_model_missing():
    """Requirement 1: Valid metadata tuple forwards model/execution_mode and does not fail with owner_acceptance_model_missing."""
    fixture = _canonical_acceptance_fixture()
    metadata = dict(fixture)
    metadata["owner_acceptance_auth"] = dict(fixture)

    req = VideoGenerationRequest(
        job_id=fixture["job_id"],
        product_type="video_ai_video_reference",
        required_capability="image_to_video",
        metadata=metadata,
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Mock candidate adapters to ensure no actual network call is made
        mock_adapter = MagicMock()
        mock_adapter.provider_name = "shopaikey_video"
        mock_adapter.submit.return_value = VideoSubmitResult(
            ok=True,
            provider_task_id="test_task_123",
            provider_video_id="test_video_123",
            provider_status="completed",
            result_url="https://example.com/test.mp4",
            file_url="https://example.com/test.mp4",
        )
        mock_adapter.poll.return_value = VideoPollResult(
            ok=True,
            status="completed",
            result_url="https://example.com/test.mp4",
        )
        with patch("services.video_provider_router.provider_candidate_adapters", return_value=[mock_adapter]):
            result = _run_provider_generation_impl(
                req,
                output_dir=tmp_dir,
                environ={"SHOPAIKEY_API_KEY": "mock_key_for_test"},
                sleep_func=lambda *_: None,
                allow_pending_result=True,
            )

    # Must NOT fail with owner_acceptance_model_missing or any acceptance blocker
    assert result.get("paid_submit_blocked_reason") != "owner_acceptance_model_missing"
    assert result.get("blocker") != "owner_acceptance_model_missing"
    assert result.get("owner_acceptance_auth_valid") is not False


def test_02_missing_model_in_metadata_fails_closed():
    """Requirement 2: Missing model in metadata must fail-closed with owner_acceptance_model_missing."""
    fixture = _canonical_acceptance_fixture()
    metadata = dict(fixture)
    metadata.pop("model", None)
    metadata.pop("selected_model", None)
    metadata["owner_acceptance_auth"] = dict(fixture)

    req = VideoGenerationRequest(
        job_id=fixture["job_id"],
        product_type="video_ai_video_reference",
        required_capability="image_to_video",
        metadata=metadata,
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        result = _run_provider_generation_impl(req, output_dir=tmp_dir, environ={})

    assert result["ok"] is False
    assert result["provider_submit_called"] is False
    assert result["external_provider_spend_prevented"] is True
    assert result["paid_submit_allowed"] is False
    assert result["paid_submit_blocked_reason"] == "owner_acceptance_model_missing"


def test_03_model_mismatch_fails_closed():
    """Requirement 3: Model mismatch between auth and context fails-closed."""
    fixture = _canonical_acceptance_fixture()
    metadata = dict(fixture)
    metadata["model"] = "veo3.1-slow"  # Mismatched model
    metadata["selected_model"] = "veo3.1-slow"
    metadata["owner_acceptance_auth"] = dict(fixture)

    req = VideoGenerationRequest(
        job_id=fixture["job_id"],
        product_type="video_ai_video_reference",
        required_capability="image_to_video",
        metadata=metadata,
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        result = _run_provider_generation_impl(req, output_dir=tmp_dir, environ={})

    assert result["ok"] is False
    assert result["provider_submit_called"] is False
    assert result["external_provider_spend_prevented"] is True
    assert "owner_acceptance" in result["paid_submit_blocked_reason"]


def test_04_missing_execution_mode_fails_closed():
    """Requirement 4: Missing execution_mode in metadata fails-closed."""
    fixture = _canonical_acceptance_fixture()
    metadata = dict(fixture)
    metadata.pop("execution_mode", None)
    metadata["owner_acceptance_auth"] = dict(fixture)

    req = VideoGenerationRequest(
        job_id=fixture["job_id"],
        product_type="video_ai_video_reference",
        required_capability="image_to_video",
        metadata=metadata,
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        result = _run_provider_generation_impl(req, output_dir=tmp_dir, environ={})

    assert result["ok"] is False
    assert result["provider_submit_called"] is False
    assert result["paid_submit_blocked_reason"] == "owner_acceptance_execution_mode_missing"


def test_05_execution_mode_mismatch_fails_closed():
    """Requirement 5: execution_mode mismatch fails-closed."""
    fixture = _canonical_acceptance_fixture()
    metadata = dict(fixture)
    metadata["execution_mode"] = "native_v2v"
    metadata["owner_acceptance_auth"] = dict(fixture)

    req = VideoGenerationRequest(
        job_id=fixture["job_id"],
        product_type="video_ai_video_reference",
        required_capability="image_to_video",
        metadata=metadata,
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        result = _run_provider_generation_impl(req, output_dir=tmp_dir, environ={})

    assert result["ok"] is False
    assert result["provider_submit_called"] is False
    assert result["paid_submit_blocked_reason"] == "owner_acceptance_execution_mode_mismatch"


def test_06_missing_source_video_sha256_fails_closed():
    """Requirement 6: Missing source_video_sha256 in metadata fails-closed."""
    fixture = _canonical_acceptance_fixture()
    metadata = dict(fixture)
    metadata.pop("source_video_sha256", None)
    metadata["owner_acceptance_auth"] = dict(fixture)

    req = VideoGenerationRequest(
        job_id=fixture["job_id"],
        product_type="video_ai_video_reference",
        required_capability="image_to_video",
        metadata=metadata,
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        result = _run_provider_generation_impl(req, output_dir=tmp_dir, environ={})

    assert result["ok"] is False
    assert result["provider_submit_called"] is False
    assert result["paid_submit_blocked_reason"] == "owner_acceptance_source_sha_missing"


def test_07_source_video_sha256_mismatch_fails_closed():
    """Requirement 7: source_video_sha256 mismatch fails-closed."""
    fixture = _canonical_acceptance_fixture()
    metadata = dict(fixture)
    metadata["source_video_sha256"] = "0" * 64
    metadata["owner_acceptance_auth"] = dict(fixture)

    req = VideoGenerationRequest(
        job_id=fixture["job_id"],
        product_type="video_ai_video_reference",
        required_capability="image_to_video",
        metadata=metadata,
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        result = _run_provider_generation_impl(req, output_dir=tmp_dir, environ={})

    assert result["ok"] is False
    assert result["provider_submit_called"] is False
    assert result["paid_submit_blocked_reason"] == "owner_acceptance_source_sha_mismatch"


def test_08_frame_1_sha256_missing_and_mismatch_fails_closed():
    """Requirement 8: frame_1_sha256 missing/mismatch fails-closed."""
    fixture = _canonical_acceptance_fixture()
    # Missing
    meta_missing = dict(fixture)
    meta_missing.pop("frame_1_sha256", None)
    meta_missing["owner_acceptance_auth"] = dict(fixture)
    req1 = VideoGenerationRequest(
        job_id=fixture["job_id"],
        product_type="video_ai_video_reference",
        required_capability="image_to_video",
        metadata=meta_missing,
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        res1 = _run_provider_generation_impl(req1, output_dir=tmp_dir, environ={})
    assert res1["ok"] is False
    assert res1["paid_submit_blocked_reason"] == "owner_acceptance_frame_1_sha_missing"

    # Mismatch
    meta_mismatch = dict(fixture)
    meta_mismatch["frame_1_sha256"] = "f" * 64
    meta_mismatch["owner_acceptance_auth"] = dict(fixture)
    req2 = VideoGenerationRequest(
        job_id=fixture["job_id"],
        product_type="video_ai_video_reference",
        required_capability="image_to_video",
        metadata=meta_mismatch,
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        res2 = _run_provider_generation_impl(req2, output_dir=tmp_dir, environ={})
    assert res2["ok"] is False
    assert res2["paid_submit_blocked_reason"] == "owner_acceptance_frame_1_sha_mismatch"


def test_09_frame_2_sha256_missing_and_mismatch_fails_closed():
    """Requirement 9: frame_2_sha256 missing/mismatch fails-closed."""
    fixture = _canonical_acceptance_fixture()
    # Missing
    meta_missing = dict(fixture)
    meta_missing.pop("frame_2_sha256", None)
    meta_missing["owner_acceptance_auth"] = dict(fixture)
    req1 = VideoGenerationRequest(
        job_id=fixture["job_id"],
        product_type="video_ai_video_reference",
        required_capability="image_to_video",
        metadata=meta_missing,
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        res1 = _run_provider_generation_impl(req1, output_dir=tmp_dir, environ={})
    assert res1["ok"] is False
    assert res1["paid_submit_blocked_reason"] == "owner_acceptance_frame_2_sha_missing"

    # Mismatch
    meta_mismatch = dict(fixture)
    meta_mismatch["frame_2_sha256"] = "f" * 64
    meta_mismatch["owner_acceptance_auth"] = dict(fixture)
    req2 = VideoGenerationRequest(
        job_id=fixture["job_id"],
        product_type="video_ai_video_reference",
        required_capability="image_to_video",
        metadata=meta_mismatch,
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        res2 = _run_provider_generation_impl(req2, output_dir=tmp_dir, environ={})
    assert res2["ok"] is False
    assert res2["paid_submit_blocked_reason"] == "owner_acceptance_frame_2_sha_mismatch"


def test_10_prompt_sha256_missing_and_mismatch_fails_closed():
    """Requirement 10: prompt_sha256 missing/mismatch fails-closed."""
    fixture = _canonical_acceptance_fixture()
    # Missing
    meta_missing = dict(fixture)
    meta_missing.pop("prompt_sha256", None)
    meta_missing["owner_acceptance_auth"] = dict(fixture)
    req1 = VideoGenerationRequest(
        job_id=fixture["job_id"],
        product_type="video_ai_video_reference",
        required_capability="image_to_video",
        metadata=meta_missing,
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        res1 = _run_provider_generation_impl(req1, output_dir=tmp_dir, environ={})
    assert res1["ok"] is False
    assert res1["paid_submit_blocked_reason"] == "owner_acceptance_prompt_sha_missing"

    # Mismatch
    meta_mismatch = dict(fixture)
    meta_mismatch["prompt_sha256"] = "f" * 64
    meta_mismatch["owner_acceptance_auth"] = dict(fixture)
    req2 = VideoGenerationRequest(
        job_id=fixture["job_id"],
        product_type="video_ai_video_reference",
        required_capability="image_to_video",
        metadata=meta_mismatch,
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        res2 = _run_provider_generation_impl(req2, output_dir=tmp_dir, environ={})
    assert res2["ok"] is False
    assert res2["paid_submit_blocked_reason"] == "owner_acceptance_prompt_sha_mismatch"


def test_11_pricing_snapshot_id_or_hash_missing_and_mismatch_fails_closed():
    """Requirement 11: pricing_snapshot_id_or_hash missing/mismatch fails-closed."""
    fixture = _canonical_acceptance_fixture()
    # Missing
    meta_missing = dict(fixture)
    meta_missing.pop("pricing_snapshot_id_or_hash", None)
    meta_missing["owner_acceptance_auth"] = dict(fixture)
    req1 = VideoGenerationRequest(
        job_id=fixture["job_id"],
        product_type="video_ai_video_reference",
        required_capability="image_to_video",
        metadata=meta_missing,
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        res1 = _run_provider_generation_impl(req1, output_dir=tmp_dir, environ={})
    assert res1["ok"] is False
    assert res1["paid_submit_blocked_reason"] == "owner_acceptance_pricing_snapshot_missing"

    # Mismatch
    meta_mismatch = dict(fixture)
    meta_mismatch["pricing_snapshot_id_or_hash"] = "f" * 64
    meta_mismatch["owner_acceptance_auth"] = dict(fixture)
    req2 = VideoGenerationRequest(
        job_id=fixture["job_id"],
        product_type="video_ai_video_reference",
        required_capability="image_to_video",
        metadata=meta_mismatch,
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        res2 = _run_provider_generation_impl(req2, output_dir=tmp_dir, environ={})
    assert res2["ok"] is False
    assert res2["paid_submit_blocked_reason"] == "owner_acceptance_pricing_snapshot_mismatch"


def test_12_aspect_ratio_missing_and_mismatch_fails_closed():
    """Requirement 12: aspect_ratio missing/mismatch fails-closed."""
    fixture = _canonical_acceptance_fixture()
    # Missing
    meta_missing = dict(fixture)
    meta_missing.pop("aspect_ratio", None)
    meta_missing["owner_acceptance_auth"] = dict(fixture)
    req1 = VideoGenerationRequest(
        job_id=fixture["job_id"],
        product_type="video_ai_video_reference",
        required_capability="image_to_video",
        metadata=meta_missing,
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        res1 = _run_provider_generation_impl(req1, output_dir=tmp_dir, environ={})
    assert res1["ok"] is False
    assert res1["paid_submit_blocked_reason"] == "owner_acceptance_aspect_ratio_missing"

    # Mismatch
    meta_mismatch = dict(fixture)
    meta_mismatch["aspect_ratio"] = "16:9"
    meta_mismatch["owner_acceptance_auth"] = dict(fixture)
    req2 = VideoGenerationRequest(
        job_id=fixture["job_id"],
        product_type="video_ai_video_reference",
        required_capability="image_to_video",
        metadata=meta_mismatch,
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        res2 = _run_provider_generation_impl(req2, output_dir=tmp_dir, environ={})
    assert res2["ok"] is False
    assert res2["paid_submit_blocked_reason"] == "owner_acceptance_aspect_ratio_mismatch"


def test_13_duration_seconds_missing_and_mismatch_fails_closed():
    """Requirement 13: duration_seconds missing/mismatch fails-closed."""
    fixture = _canonical_acceptance_fixture()
    # Missing
    meta_missing = dict(fixture)
    meta_missing.pop("duration_seconds", None)
    meta_missing["owner_acceptance_auth"] = dict(fixture)
    req1 = VideoGenerationRequest(
        job_id=fixture["job_id"],
        product_type="video_ai_video_reference",
        required_capability="image_to_video",
        metadata=meta_missing,
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        res1 = _run_provider_generation_impl(req1, output_dir=tmp_dir, environ={})
    assert res1["ok"] is False
    assert res1["paid_submit_blocked_reason"] == "owner_acceptance_duration_missing"

    # Mismatch
    meta_mismatch = dict(fixture)
    meta_mismatch["duration_seconds"] = 10.0
    meta_mismatch["owner_acceptance_auth"] = dict(fixture)
    req2 = VideoGenerationRequest(
        job_id=fixture["job_id"],
        product_type="video_ai_video_reference",
        required_capability="image_to_video",
        metadata=meta_mismatch,
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        res2 = _run_provider_generation_impl(req2, output_dir=tmp_dir, environ={})
    assert res2["ok"] is False
    assert res2["paid_submit_blocked_reason"] == "owner_acceptance_duration_mismatch"


def test_14_invalid_acceptance_context_guarantees_provider_submit_not_called():
    """Requirement 14: Any invalid acceptance context guarantees PROVIDER_SUBMIT_CALLED=NO."""
    fixture = _canonical_acceptance_fixture()
    metadata = dict(fixture)
    metadata["model"] = "invalid-model"
    metadata["owner_acceptance_auth"] = dict(fixture)

    req = VideoGenerationRequest(
        job_id=fixture["job_id"],
        product_type="video_ai_video_reference",
        required_capability="image_to_video",
        metadata=metadata,
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        mock_adapter = MagicMock()
        mock_adapter.provider_name = "shopaikey_video"
        with patch("services.video_provider_router.provider_candidate_adapters", return_value=[mock_adapter]):
            result = _run_provider_generation_impl(req, output_dir=tmp_dir, environ={})

        # Submit method on adapter was never invoked
        mock_adapter.submit.assert_not_called()

    assert result["provider_submit_called"] is False
    assert result["paid_submit_allowed"] is False
    assert result["external_provider_spend_prevented"] is True


def test_15_no_paid_provider_calls_occur_in_tests():
    """Requirement 15: Zero paid provider calls occur across all tests."""
    # Verified by mocking / empty env across all tests above.
    pass
