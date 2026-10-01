"""Test Suite for Web Product Video Output URL Propagation & Artifact Contract Validation.

Task: WEBAPP_PRODUCT_VIDEO_OUTPUT_URL_PROPAGATION_REMEDIATION_R1
Tracker: Issue #605
Parent Live Receipt: #605 comment 5928044516
Contract: #605 comment 5928410734

Verifies:
1. Router propagates exact validated result_url
2. Router propagates same file_url
3. URL never derived from artifact.local_path
4. Missing URL fails closed
5. Unsafe/non-HTTPS URL fails closed
6. Safe HTTPS MP4 accepted
7. Local-path-only result rejected
8. Consumer uses actual probe duration/width/height
9. Requested 9:16 + actual 1280x720 rejected
10. Invalid duration rejected
11. Valid vertical fixture passes
12. Artifact mismatch = zero wallet mutation
13. Zero real provider/network calls
"""

from __future__ import annotations

import os
import tempfile
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from services.video_provider_base import VideoArtifactResult, VideoGenerationRequest, VideoPollResult, VideoSubmitResult
from services.web_product_video_worker_consumer import (
    ConsumerExecutionOutcome,
    WebProductVideoDispatcherClient,
    execute_claimed_web_product_video_job,
    is_safe_video_output_url,
    validate_aspect_ratio_match,
    validate_duration_contract,
    probe_artifact_file,
)


SAMPLE_JOB: dict[str, Any] = {
    "job_id": "pvjob_url_remediation_001",
    "request_id": "req_url_rem_001",
    "account_id": "acc_cust_test_494e",
    "product_key": "video_ai_prompt",
    "status": "processing",
    "payload": {
        "prompt": "Premium perfume product video 5s",
        "aspect_ratio": "9:16",
        "duration": 5.0,
        "quality_tier": "200",
    },
    "attempts": 1,
    "worker_id": "vps-web-product-video-worker",
}

ENABLED_ENV: dict[str, str] = {
    "WEB_PRODUCT_VIDEO_WORKER_ENABLED": "true",
    "LOCAL_WORKER_TOKEN": "valid_token_test",
}


# ==============================================================================
# PHASE G — 13 FOCUSED TESTS
# ==============================================================================

def test_01_router_propagates_exact_validated_result_url() -> None:
    """1. Router propagates exact validated result_url in success payload."""
    from services.video_provider_router import _run_provider_generation_impl

    validated_url = "https://cdn.shopaikey.com/videos/output_task_8899.mp4"
    mock_adapter = MagicMock()
    mock_adapter.provider_name = "shopaikey_video"
    mock_adapter.submit_video_job.return_value = VideoSubmitResult(
        ok=True,
        provider_name="shopaikey_video",
        provider_task_id="task_8899",
        provider_status="submitted",
    )
    mock_adapter.poll_video_job.return_value = VideoPollResult(
        ok=True,
        provider_name="shopaikey_video",
        provider_task_id="task_8899",
        status="succeeded",
        result_url=validated_url,
        file_url=validated_url,
    )
    mock_adapter.materialize_result.return_value = VideoArtifactResult(
        ok=True,
        local_path="/opt/toanaas/bot/video_outputs/shopaikey_video_pvj_test.mp4",
        bytes=2048000,
        duration=5.0,
        has_video_stream=True,
        has_audio_stream=True,
        artifact_hash="hash_abc123",
    )

    req = VideoGenerationRequest(
        job_id="pvj_test",
        product_type="video_ai_prompt",
        prompt="Test perfume video",
        ratio="9:16",
        duration_seconds=5.0,
        metadata={"product_video": True, "job_id": "pvj_test"},
    )

    with patch("services.video_provider_router.provider_candidate_adapters", return_value=[mock_adapter]), \
         patch("services.video_provider_router._failed_result_url_diagnostic", return_value={"result_url_valid": True}):
        res = _run_provider_generation_impl(req, output_dir="/tmp", environ={"SHOPAIKEY_VIDEO_ENABLED": "true"}, sleep_func=lambda *a, **kw: None)

    assert res["ok"] is True
    assert res.get("result_url") == validated_url


def test_02_router_propagates_same_file_url() -> None:
    """2. Router propagates same file_url matching result_url."""
    from services.video_provider_router import _run_provider_generation_impl

    validated_url = "https://cdn.shopaikey.com/videos/output_task_8899.mp4"
    mock_adapter = MagicMock()
    mock_adapter.provider_name = "shopaikey_video"
    mock_adapter.submit_video_job.return_value = VideoSubmitResult(
        ok=True,
        provider_name="shopaikey_video",
        provider_task_id="task_8899",
        provider_status="submitted",
    )
    mock_adapter.poll_video_job.return_value = VideoPollResult(
        ok=True,
        provider_name="shopaikey_video",
        provider_task_id="task_8899",
        status="succeeded",
        result_url=validated_url,
        file_url=validated_url,
    )
    mock_adapter.materialize_result.return_value = VideoArtifactResult(
        ok=True,
        local_path="/opt/toanaas/bot/video_outputs/shopaikey_video_pvj_test.mp4",
        bytes=2048000,
        duration=5.0,
        has_video_stream=True,
        has_audio_stream=True,
        artifact_hash="hash_abc123",
    )

    req = VideoGenerationRequest(
        job_id="pvj_test_02",
        product_type="video_ai_prompt",
        prompt="Test perfume video",
        ratio="9:16",
        duration_seconds=5.0,
        metadata={"product_video": True, "job_id": "pvj_test_02"},
    )

    with patch("services.video_provider_router.provider_candidate_adapters", return_value=[mock_adapter]), \
         patch("services.video_provider_router._failed_result_url_diagnostic", return_value={"result_url_valid": True}):
        res = _run_provider_generation_impl(req, output_dir="/tmp", environ={"SHOPAIKEY_VIDEO_ENABLED": "true"}, sleep_func=lambda *a, **kw: None)

    assert res["ok"] is True
    assert res.get("file_url") == validated_url
    assert res.get("file_url") == res.get("result_url")


def test_03_url_never_derived_from_local_path() -> None:
    """3. Router result_url is sourced directly from provider result, never from artifact.local_path."""
    from services.video_provider_router import _run_provider_generation_impl

    provider_remote_url = "https://cdn.shopaikey.com/remote/generated.mp4"
    local_artifact_path = "/tmp/downloads/local_file_on_disk.mp4"

    mock_adapter = MagicMock()
    mock_adapter.provider_name = "shopaikey_video"
    mock_adapter.submit_video_job.return_value = VideoSubmitResult(
        ok=True,
        provider_name="shopaikey_video",
        provider_task_id="task_123",
        provider_status="submitted",
    )
    mock_adapter.poll_video_job.return_value = VideoPollResult(
        ok=True,
        provider_name="shopaikey_video",
        provider_task_id="task_123",
        status="succeeded",
        result_url=provider_remote_url,
        file_url=provider_remote_url,
    )
    mock_adapter.materialize_result.return_value = VideoArtifactResult(
        ok=True,
        local_path=local_artifact_path,
        bytes=1000000,
        duration=5.0,
        has_video_stream=True,
        has_audio_stream=True,
        artifact_hash="hash_xyz",
    )

    req = VideoGenerationRequest(
        job_id="pvj_test_03",
        product_type="video_ai_prompt",
        prompt="Test prompt",
        ratio="9:16",
        duration_seconds=5.0,
        metadata={"product_video": True, "job_id": "pvj_test_03"},
    )

    with patch("services.video_provider_router.provider_candidate_adapters", return_value=[mock_adapter]), \
         patch("services.video_provider_router._failed_result_url_diagnostic", return_value={"result_url_valid": True}):
        res = _run_provider_generation_impl(req, output_dir="/tmp", environ={"SHOPAIKEY_VIDEO_ENABLED": "true"}, sleep_func=lambda *a, **kw: None)

    assert res["ok"] is True
    assert res["result_url"] == provider_remote_url
    assert res["result_url"] != local_artifact_path
    assert not res["result_url"].startswith("/")
    assert not res["result_url"].startswith("file://")


def test_04_missing_url_fails_closed() -> None:
    """4. Missing provider result URL causes router to fail closed."""
    from services.video_provider_router import _run_provider_generation_impl

    mock_adapter = MagicMock()
    mock_adapter.provider_name = "shopaikey_video"
    mock_adapter.submit_video_job.return_value = VideoSubmitResult(
        ok=True,
        provider_name="shopaikey_video",
        provider_task_id="task_empty_url",
        provider_status="submitted",
    )
    mock_adapter.poll_video_job.return_value = VideoPollResult(
        ok=True,
        provider_name="shopaikey_video",
        provider_task_id="task_empty_url",
        status="succeeded",
        result_url="",
        file_url="",
    )

    req = VideoGenerationRequest(
        job_id="pvj_test_04",
        product_type="video_ai_prompt",
        prompt="Test prompt",
        ratio="9:16",
        duration_seconds=5.0,
        metadata={"product_video": True, "job_id": "pvj_test_04"},
    )

    with patch("services.video_provider_router.provider_candidate_adapters", return_value=[mock_adapter]):
        res = _run_provider_generation_impl(req, output_dir="/tmp", environ={"SHOPAIKEY_VIDEO_ENABLED": "true"}, sleep_func=lambda *a, **kw: None)

    assert res["ok"] is False
    assert res.get("blocker") in {"provider_result_url_missing", "provider_timeout"}


def test_05_unsafe_non_https_url_fails_closed() -> None:
    """5. Unsafe or non-HTTPS URLs fail closed in consumer with UNSAFE_OUTPUT_URL."""
    bad_urls = [
        "http://insecure.example.com/video.mp4",
        "file:///etc/passwd",
        "https://127.0.0.1/video.mp4",
        "https://localhost/video.mp4",
        "https://169.254.169.254/latest/meta-data/",
        "https://192.168.1.10/video.mp4",
        "https://cdn.example.com/not_a_video.exe",
        "",
    ]

    for bad_url in bad_urls:
        client = MagicMock(spec=WebProductVideoDispatcherClient)
        def bad_executor(req: VideoGenerationRequest, **kwargs: Any) -> dict[str, Any]:
            return {
                "ok": True,
                "result_url": bad_url,
                "file_url": bad_url,
                "duration": 5.0,
                "width": 720,
                "height": 1280,
                "format": "mp4",
                "codec": "h264",
                "provider_submit_called": True,
            }

        outcome = execute_claimed_web_product_video_job(
            SAMPLE_JOB,
            client=client,
            environ=ENABLED_ENV,
            executor_fn=bad_executor,
        )

        assert outcome.ok is False
        assert outcome.status == "UNSAFE_OUTPUT_REJECTED"
        assert outcome.blocker_reason == "UNSAFE_OUTPUT_URL"
        assert client.complete.call_count == 0
        assert client.fail.call_count == 1
        assert client.fail.call_args[1]["error_code"] == "UNSAFE_OUTPUT_URL"


def test_06_safe_https_mp4_accepted() -> None:
    """6. Safe HTTPS MP4 URLs are accepted by is_safe_video_output_url."""
    safe_urls = [
        "https://storage.googleapis.com/toanaas-assets/output_123.mp4",
        "https://cdn.shopaikey.com/videos/grok_5s_720p.mp4",
        "https://s3.amazonaws.com/bucket-prod/rendered_video.mov",
    ]
    for url in safe_urls:
        assert is_safe_video_output_url(url) is True


def test_07_local_path_only_result_rejected() -> None:
    """7. Result providing only local_path without safe HTTPS result_url is rejected."""
    client = MagicMock(spec=WebProductVideoDispatcherClient)

    def local_only_executor(req: VideoGenerationRequest, **kwargs: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "output_path": "/opt/toanaas/bot/video_outputs/sample.mp4",
            "local_path": "/opt/toanaas/bot/video_outputs/sample.mp4",
            "result_url": "",
            "file_url": "",
            "duration": 5.0,
            "width": 720,
            "height": 1280,
            "format": "mp4",
            "codec": "h264",
            "provider_submit_called": True,
        }

    outcome = execute_claimed_web_product_video_job(
        SAMPLE_JOB,
        client=client,
        environ=ENABLED_ENV,
        executor_fn=local_only_executor,
    )

    assert outcome.ok is False
    assert outcome.status == "UNSAFE_OUTPUT_REJECTED"
    assert client.complete.call_count == 0
    assert client.fail.call_count == 1


def test_08_consumer_uses_actual_probe_truth() -> None:
    """8. Consumer uses actual ffprobe probed dimensions and duration instead of requested values."""
    client = MagicMock(spec=WebProductVideoDispatcherClient)
    client.complete.return_value = True

    # Job requests 9:16, 5.0s
    job = {
        **SAMPLE_JOB,
        "payload": {
            "prompt": "Test perfume",
            "aspect_ratio": "9:16",
            "duration": 5.0,
        },
    }

    # Probed file truth: actual 720x1280 (vertical), actual duration 5.2s, actual size 2048500
    mock_probe = {
        "ok": True,
        "width": 720,
        "height": 1280,
        "duration": 5.2,
        "duration_seconds": 5.2,
        "file_size_bytes": 2048500,
        "bytes": 2048500,
        "format": "mp4",
        "codec": "h264",
        "has_audio": True,
    }

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
        tf.write(b"mock_mp4_bytes")
        tf_path = tf.name

    try:
        def executor_with_file(req: VideoGenerationRequest, **kwargs: Any) -> dict[str, Any]:
            return {
                "ok": True,
                "result_url": "https://cdn.shopaikey.com/videos/output_probed.mp4",
                "file_url": "https://cdn.shopaikey.com/videos/output_probed.mp4",
                "output_path": tf_path,
                "provider_submit_called": True,
            }

        with patch("services.web_product_video_worker_consumer.probe_artifact_file", return_value=mock_probe):
            outcome = execute_claimed_web_product_video_job(
                job,
                client=client,
                environ=ENABLED_ENV,
                executor_fn=executor_with_file,
            )

        assert outcome.ok is True
        assert outcome.status == "COMPLETED"
        assert client.complete.call_count == 1
        complete_meta = client.complete.call_args[1]["output_metadata"]
        # Truth must come from probe: 5.2s, 720x1280, 2048500 bytes
        assert complete_meta["duration_seconds"] == 5.2
        assert complete_meta["width"] == 720
        assert complete_meta["height"] == 1280
        assert complete_meta["file_size_bytes"] == 2048500
        assert complete_meta["has_audio"] is True
    finally:
        if os.path.exists(tf_path):
            os.remove(tf_path)


def test_09_requested_9_16_actual_1280x720_rejected() -> None:
    """9. Requested 9:16 + actual 1280x720 (horizontal) artifact is rejected with ARTIFACT_CONTRACT_MISMATCH."""
    client = MagicMock(spec=WebProductVideoDispatcherClient)

    # Historical live defect reproduction: requested 9:16, but grok-video-3 produced 1280x720 horizontal
    mock_probe = {
        "ok": True,
        "width": 1280,
        "height": 720,
        "duration": 5.0,
        "file_size_bytes": 2048690,
        "format": "mp4",
        "codec": "h264",
        "has_audio": True,
    }

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
        tf.write(b"mock_mp4_bytes")
        tf_path = tf.name

    try:
        def executor_with_horizontal_artifact(req: VideoGenerationRequest, **kwargs: Any) -> dict[str, Any]:
            return {
                "ok": True,
                "result_url": "https://cdn.shopaikey.com/videos/grok_horizontal.mp4",
                "file_url": "https://cdn.shopaikey.com/videos/grok_horizontal.mp4",
                "output_path": tf_path,
                "provider_submit_called": True,
            }

        with patch("services.web_product_video_worker_consumer.probe_artifact_file", return_value=mock_probe):
            outcome = execute_claimed_web_product_video_job(
                SAMPLE_JOB,  # requested aspect_ratio is 9:16
                client=client,
                environ=ENABLED_ENV,
                executor_fn=executor_with_horizontal_artifact,
            )

        assert outcome.ok is False
        assert outcome.status == "ARTIFACT_CONTRACT_MISMATCH"
        assert "ACTUAL_ASPECT_RATIO_MISMATCH" in outcome.blocker_reason
        assert client.complete.call_count == 0
        assert client.fail.call_count == 1
        assert client.fail.call_args[1]["error_code"] == "ARTIFACT_CONTRACT_MISMATCH"
    finally:
        if os.path.exists(tf_path):
            os.remove(tf_path)


def test_10_invalid_duration_rejected() -> None:
    """10. Artifact with duration out of tolerance is rejected with ARTIFACT_CONTRACT_MISMATCH."""
    client = MagicMock(spec=WebProductVideoDispatcherClient)

    # Requested duration is 5.0s. Historical live output duration was 6.041667s (outside 1.0s tolerance)
    mock_probe = {
        "ok": True,
        "width": 720,
        "height": 1280,
        "duration": 6.041667,
        "file_size_bytes": 2048690,
        "format": "mp4",
        "codec": "h264",
        "has_audio": True,
    }

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
        tf.write(b"mock_mp4_bytes")
        tf_path = tf.name

    try:
        def executor_with_bad_duration(req: VideoGenerationRequest, **kwargs: Any) -> dict[str, Any]:
            return {
                "ok": True,
                "result_url": "https://cdn.shopaikey.com/videos/grok_bad_dur.mp4",
                "file_url": "https://cdn.shopaikey.com/videos/grok_bad_dur.mp4",
                "output_path": tf_path,
                "provider_submit_called": True,
            }

        with patch("services.web_product_video_worker_consumer.probe_artifact_file", return_value=mock_probe):
            outcome = execute_claimed_web_product_video_job(
                SAMPLE_JOB,  # requested duration is 5.0s
                client=client,
                environ=ENABLED_ENV,
                executor_fn=executor_with_bad_duration,
            )

        assert outcome.ok is False
        assert outcome.status == "ARTIFACT_CONTRACT_MISMATCH"
        assert "DURATION_OUT_OF_TOLERANCE" in outcome.blocker_reason
        assert client.complete.call_count == 0
        assert client.fail.call_count == 1
        assert client.fail.call_args[1]["error_code"] == "ARTIFACT_CONTRACT_MISMATCH"
    finally:
        if os.path.exists(tf_path):
            os.remove(tf_path)


def test_11_valid_vertical_fixture_passes() -> None:
    """11. Valid vertical fixture (720x1280, 5.0s, safe HTTPS URL) passes all gates and completes."""
    client = MagicMock(spec=WebProductVideoDispatcherClient)
    client.complete.return_value = True

    mock_probe = {
        "ok": True,
        "width": 720,
        "height": 1280,
        "duration": 5.0,
        "file_size_bytes": 1500000,
        "format": "mp4",
        "codec": "h264",
        "has_audio": True,
    }

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
        tf.write(b"mock_mp4_bytes")
        tf_path = tf.name

    try:
        def valid_executor(req: VideoGenerationRequest, **kwargs: Any) -> dict[str, Any]:
            return {
                "ok": True,
                "result_url": "https://cdn.shopaikey.com/videos/valid_vertical.mp4",
                "file_url": "https://cdn.shopaikey.com/videos/valid_vertical.mp4",
                "output_path": tf_path,
                "provider_submit_called": True,
            }

        with patch("services.web_product_video_worker_consumer.probe_artifact_file", return_value=mock_probe):
            outcome = execute_claimed_web_product_video_job(
                SAMPLE_JOB,
                client=client,
                environ=ENABLED_ENV,
                executor_fn=valid_executor,
            )

        assert outcome.ok is True
        assert outcome.status == "COMPLETED"
        assert client.complete.call_count == 1
        assert client.fail.call_count == 0
    finally:
        if os.path.exists(tf_path):
            os.remove(tf_path)


def test_12_artifact_mismatch_zero_wallet_mutation() -> None:
    """12. Artifact mismatch results in zero wallet mutation and zero charge."""
    client = MagicMock(spec=WebProductVideoDispatcherClient)

    # 1280x720 horizontal mismatch
    mock_probe = {
        "ok": True,
        "width": 1280,
        "height": 720,
        "duration": 5.0,
        "file_size_bytes": 2000000,
        "format": "mp4",
        "codec": "h264",
        "has_audio": True,
    }

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
        tf.write(b"mock_mp4_bytes")
        tf_path = tf.name

    try:
        def mismatch_executor(req: VideoGenerationRequest, **kwargs: Any) -> dict[str, Any]:
            return {
                "ok": True,
                "result_url": "https://cdn.shopaikey.com/videos/mismatch.mp4",
                "file_url": "https://cdn.shopaikey.com/videos/mismatch.mp4",
                "output_path": tf_path,
                "provider_submit_called": True,
            }

        with patch("services.web_product_video_worker_consumer.probe_artifact_file", return_value=mock_probe):
            outcome = execute_claimed_web_product_video_job(
                SAMPLE_JOB,
                client=client,
                environ=ENABLED_ENV,
                executor_fn=mismatch_executor,
            )

        assert outcome.ok is False
        assert outcome.wallet_mutations == 0
        assert client.complete.call_count == 0
        assert client.fail.call_count == 1
    finally:
        if os.path.exists(tf_path):
            os.remove(tf_path)


def test_13_zero_real_provider_network_calls() -> None:
    """13. Pure unit tests execute completely offline without outbound HTTP calls."""
    with patch("urllib.request.urlopen") as mock_urlopen, \
         patch("urllib.request.Request") as mock_req:
        mock_req.side_effect = AssertionError("Outbound network call forbidden in unit test")
        # Run aspect ratio and duration pure validators
        match, err = validate_aspect_ratio_match(720, 1280, "9:16")
        assert match is True
        assert err == ""

        match, err = validate_aspect_ratio_match(1280, 720, "9:16")
        assert match is False
        assert "ACTUAL_ASPECT_RATIO_MISMATCH" in err

        match, err = validate_duration_contract(5.0, 5.0)
        assert match is True
        assert err == ""

        match, err = validate_duration_contract(6.5, 5.0)
        assert match is False
        assert "DURATION_OUT_OF_TOLERANCE" in err

        assert mock_urlopen.call_count == 0
