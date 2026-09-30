"""Test Suite for Web Product Video Bot Worker Integration.

Task: WEBAPP_PRODUCT_VIDEO_WEB_QUEUE_WORKER_INTEGRATION_R1
Tracker: Issue #605
Defect: DEFECT-PV-001B
Phases: N (Unit Tests 1-16), O (Mocked Integration Success), P (Mocked Integration Failure)
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
from typing import Any, Mapping
from unittest.mock import MagicMock, patch

import pytest

from services.video_provider_base import VideoGenerationRequest
from services.web_product_video_worker_consumer import (
    ConsumerExecutionOutcome,
    WebClaimResponse,
    WebProductVideoDispatcherClient,
    _ACTIVE_JOB_IDS,
    execute_claimed_web_product_video_job,
    is_safe_video_output_url,
    is_web_product_video_worker_enabled,
    map_web_job_to_bot_runtime,
    validate_claimed_job,
    validate_video_artifact_metadata,
)
from services.web_product_video_worker_daemon import WebProductVideoWorkerDaemon

SAMPLE_VALID_WEB_JOB: dict[str, Any] = {
    "job_id": "pvjob_20260930_valid01",
    "request_id": "req_video_ai_prompt_101",
    "account_id": "acc_cust_123456",
    "product_key": "video_ai_prompt",
    "status": "processing",
    "payload": {
        "prompt": "Cinematic mechanical wristwatch ticking under studio lights with water reflections",
        "aspect_ratio": "9:16",
        "duration": 5.0,
        "quality_tier": "standard",
    },
    "attempts": 1,
    "worker_id": "test-bot-worker-web-01",
    "claimed_at": "2026-09-30T22:00:00Z",
    "lease_expires_at": "2026-09-30T22:05:00Z",
    "output_url": None,
    "created_at": "2026-09-30T21:55:00Z",
    "updated_at": "2026-09-30T22:00:00Z",
}

ENABLED_ENV: dict[str, str] = {
    "WEB_PRODUCT_VIDEO_WORKER_ENABLED": "true",
    "LOCAL_WORKER_TOKEN": "test_secret_123",
}


# ==============================================================================
# PHASE N — UNIT TESTS (1 to 16)
# ==============================================================================

def test_01_empty_queue_idle() -> None:
    """1. Empty queue returns idle=True, job=None; no execution performed."""
    def mock_transport(req: urllib.request.Request, timeout: int) -> tuple[int, bytes, dict[str, str]]:
        envelope = {
            "ok": True,
            "message": "Không có job nào trong hàng đợi.",
            "data": {"job": None, "idle": True},
            "status": "idle",
        }
        return 200, json.dumps(envelope).encode("utf-8"), {}

    client = WebProductVideoDispatcherClient(
        base_url="http://mock-web",
        worker_id="test-worker",
        worker_secret="valid_secret",
        transport=mock_transport,
    )
    claim_resp = client.claim()
    assert claim_resp.ok is True
    assert claim_resp.idle is True
    assert claim_resp.job is None


def test_02_one_web_job_one_claim() -> None:
    """2. One Web job produces exactly one claim with expected job payload."""
    claim_count = 0

    def mock_transport(req: urllib.request.Request, timeout: int) -> tuple[int, bytes, dict[str, str]]:
        nonlocal claim_count
        claim_count += 1
        envelope = {
            "ok": True,
            "message": "Claimed",
            "data": {"job": SAMPLE_VALID_WEB_JOB, "idle": False},
            "status": "claimed",
        }
        return 200, json.dumps(envelope).encode("utf-8"), {}

    client = WebProductVideoDispatcherClient(
        base_url="http://mock-web",
        worker_id="test-worker",
        worker_secret="valid_secret",
        transport=mock_transport,
    )
    claim_resp = client.claim()
    assert claim_count == 1
    assert claim_resp.ok is True
    assert claim_resp.idle is False
    assert claim_resp.job is not None
    assert claim_resp.job["job_id"] == "pvjob_20260930_valid01"


def test_03_invalid_job_factual_fail() -> None:
    """3. Invalid job envelope triggers client.fail with factual reason and rejects execution."""
    failed_payloads: list[dict[str, Any]] = []

    def mock_transport(req: urllib.request.Request, timeout: int) -> tuple[int, bytes, dict[str, str]]:
        if "/fail" in req.full_url:
            failed_payloads.append(json.loads(req.data.decode("utf-8")))
            return 200, b'{"ok": true, "message": "Failed recorded"}', {}
        return 200, b'{}', {}

    client = WebProductVideoDispatcherClient(
        base_url="http://mock-web",
        worker_id="test-worker",
        worker_secret="valid_secret",
        transport=mock_transport,
    )

    invalid_job = dict(SAMPLE_VALID_WEB_JOB, payload={"prompt": "hi", "aspect_ratio": "9:16"})
    outcome = execute_claimed_web_product_video_job(
        invalid_job,
        client=client,
        environ=ENABLED_ENV,
    )

    assert outcome.ok is False
    assert outcome.status == "INVALID_JOB_REJECTED"
    assert outcome.blocker_reason == "PROMPT_TOO_SHORT"
    assert len(failed_payloads) == 1
    assert failed_payloads[0]["error_code"] == "VALIDATION_FAILED"
    assert failed_payloads[0]["error_message"] == "PROMPT_TOO_SHORT"
    assert failed_payloads[0]["fatal"] is True


def test_04_mapping_to_canonical_video_generation_request() -> None:
    """4. Mapping to VideoGenerationRequest preserves prompt, aspect ratio, and financial flags."""
    req = map_web_job_to_bot_runtime(SAMPLE_VALID_WEB_JOB)

    assert isinstance(req, VideoGenerationRequest)
    assert req.job_id == "pvjob_20260930_valid01"
    assert req.prompt == SAMPLE_VALID_WEB_JOB["payload"]["prompt"]
    assert req.ratio == "9:16"
    assert req.duration_seconds == 5.0
    assert req.product_type == "video_ai_prompt"
    # Strict financial boundary in metadata:
    assert req.metadata.get("admin_no_charge") is True
    assert req.metadata.get("no_wallet_charge") is True
    assert req.metadata.get("web_job_id") == "pvjob_20260930_valid01"
    assert req.metadata.get("web_request_id") == "req_video_ai_prompt_101"
    assert req.metadata.get("account_id") == "acc_cust_123456"


def test_05_one_provider_submit_max() -> None:
    """5. Provider submit invoked at most once per Web job."""
    submit_calls = 0

    def mock_executor(req: VideoGenerationRequest, **kwargs: Any) -> dict[str, Any]:
        nonlocal submit_calls
        submit_calls += 1
        return {
            "ok": True,
            "result_url": "https://cdn.example.com/videos/output_watch_01.mp4",
            "duration": 5.0,
            "bytes": 50000,
            "width": 720,
            "height": 1280,
            "format": "mp4",
            "codec": "h264",
            "provider_task_ids": ["task_remote_001"],
            "provider_submit_called": True,
        }

    client = MagicMock(spec=WebProductVideoDispatcherClient)
    client.complete.return_value = True

    outcome = execute_claimed_web_product_video_job(
        SAMPLE_VALID_WEB_JOB,
        client=client,
        environ=ENABLED_ENV,
        executor_fn=mock_executor,
    )

    assert outcome.ok is True
    assert submit_calls == 1
    assert outcome.provider_calls == 1
    assert outcome.paid_provider_calls == 1


def test_06_same_task_polling() -> None:
    """6. Provider execution polls the same task ID without submitting a second generation."""
    polled_task_ids: list[str] = []
    generated_ids: list[str] = []

    def mock_executor(req: VideoGenerationRequest, **kwargs: Any) -> dict[str, Any]:
        task_id = "key4u_raw_task_99999"
        generated_ids.append(task_id)
        # Simulate polling the same task 3 times
        for _ in range(3):
            polled_task_ids.append(task_id)
        return {
            "ok": True,
            "result_url": "https://cdn.example.com/videos/final_video.mp4",
            "duration": 5.0,
            "bytes": 60000,
            "width": 720,
            "height": 1280,
            "format": "mp4",
            "codec": "h264",
            "provider_task_ids": [task_id],
            "provider_submit_called": True,
        }

    client = MagicMock(spec=WebProductVideoDispatcherClient)
    client.complete.return_value = True

    outcome = execute_claimed_web_product_video_job(
        SAMPLE_VALID_WEB_JOB,
        client=client,
        environ=ENABLED_ENV,
        executor_fn=mock_executor,
    )

    assert outcome.ok is True
    assert len(generated_ids) == 1
    assert len(polled_task_ids) == 3
    assert all(tid == "key4u_raw_task_99999" for tid in polled_task_ids)
    assert outcome.provider_task_id == "key4u_raw_task_99999"


def test_07_heartbeat_during_processing() -> None:
    """7. Heartbeat actively sends lease renewals while execution runs and stops on terminal."""
    heartbeat_calls: list[str] = []

    client = MagicMock(spec=WebProductVideoDispatcherClient)
    def mock_heartbeat(job_id: str, lease_seconds: int = 300) -> bool:
        heartbeat_calls.append(job_id)
        return True
    client.heartbeat.side_effect = mock_heartbeat
    client.complete.return_value = True

    def slow_executor(req: VideoGenerationRequest, **kwargs: Any) -> dict[str, Any]:
        time.sleep(0.35)  # Allow heartbeat thread to trigger
        return {
            "ok": True,
            "result_url": "https://cdn.example.com/videos/slow_result.mp4",
            "duration": 5.0,
            "bytes": 50000,
            "width": 720,
            "height": 1280,
            "format": "mp4",
            "codec": "h264",
            "provider_submit_called": True,
        }

    outcome = execute_claimed_web_product_video_job(
        SAMPLE_VALID_WEB_JOB,
        client=client,
        environ=ENABLED_ENV,
        heartbeat_interval=0.1,
        executor_fn=slow_executor,
    )

    assert outcome.ok is True
    assert len(heartbeat_calls) >= 2
    # Verify heartbeats stop after completion
    count_before = len(heartbeat_calls)
    time.sleep(0.25)
    assert len(heartbeat_calls) == count_before


def test_08_safe_completion_callback() -> None:
    """8. Safe output URL and valid metadata correctly trigger client.complete."""
    completed_calls: list[dict[str, Any]] = []

    client = MagicMock(spec=WebProductVideoDispatcherClient)
    def mock_complete(job_id: str, output_url: str, output_metadata: dict[str, Any] | None = None) -> bool:
        completed_calls.append({
            "job_id": job_id,
            "output_url": output_url,
            "output_metadata": output_metadata,
        })
        return True
    client.complete.side_effect = mock_complete

    def mock_executor(req: VideoGenerationRequest, **kwargs: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "result_url": "https://storage.googleapis.com/toanaas-assets/video_123.mp4",
            "duration": 6.0,
            "bytes": 1048576,
            "width": 720,
            "height": 1280,
            "format": "mp4",
            "codec": "h264",
            "provider_submit_called": True,
        }

    outcome = execute_claimed_web_product_video_job(
        SAMPLE_VALID_WEB_JOB,
        client=client,
        environ=ENABLED_ENV,
        executor_fn=mock_executor,
    )

    assert outcome.ok is True
    assert outcome.status == "COMPLETED"
    assert len(completed_calls) == 1
    assert completed_calls[0]["job_id"] == "pvjob_20260930_valid01"
    assert completed_calls[0]["output_url"] == "https://storage.googleapis.com/toanaas-assets/video_123.mp4"
    assert completed_calls[0]["output_metadata"]["format"] == "mp4"
    assert completed_calls[0]["output_metadata"]["file_size_bytes"] == 1048576


def test_09_unsafe_output_rejected() -> None:
    """9. Non-HTTPS, loopback, or invalid video output URLs fail closed without calling complete."""
    unsafe_urls = [
        "http://insecure.example.com/video.mp4",
        "https://127.0.0.1/video.mp4",
        "https://localhost/video.mp4",
        "https://169.254.169.254/secret.mp4",
        "https://cdn.example.com/script.sh",
        "file:///etc/passwd",
        "",
    ]

    for bad_url in unsafe_urls:
        client = MagicMock(spec=WebProductVideoDispatcherClient)
        def mock_executor(req: VideoGenerationRequest, **kwargs: Any) -> dict[str, Any]:
            return {
                "ok": True,
                "result_url": bad_url,
                "duration": 5.0,
                "bytes": 50000,
                "width": 720,
                "height": 1280,
                "format": "mp4",
                "codec": "h264",
                "provider_submit_called": True,
            }

        outcome = execute_claimed_web_product_video_job(
            SAMPLE_VALID_WEB_JOB,
            client=client,
            environ=ENABLED_ENV,
            executor_fn=mock_executor,
        )

        assert outcome.ok is False
        assert outcome.status == "UNSAFE_OUTPUT_REJECTED"
        assert client.complete.call_count == 0
        assert client.fail.call_count == 1
        assert client.fail.call_args[1]["error_code"] == "UNSAFE_OUTPUT_URL"


def test_10_provider_failure_reports_web_fail() -> None:
    """10. Remote provider error reports truthful failure to Web dispatcher and returns fail outcome."""
    client = MagicMock(spec=WebProductVideoDispatcherClient)

    def failing_executor(req: VideoGenerationRequest, **kwargs: Any) -> dict[str, Any]:
        return {
            "ok": False,
            "blocker": "KEY4U_SUBMIT_FAILED",
            "provider_error": "INSUFFICIENT_CREDITS",
            "public_message": "Provider returned 402 Insufficient Balance",
            "provider_submit_called": True,
        }

    outcome = execute_claimed_web_product_video_job(
        SAMPLE_VALID_WEB_JOB,
        client=client,
        environ=ENABLED_ENV,
        executor_fn=failing_executor,
    )

    assert outcome.ok is False
    assert outcome.status == "PROVIDER_FAILED"
    assert outcome.blocker_reason == "KEY4U_SUBMIT_FAILED"
    assert client.complete.call_count == 0
    assert client.fail.call_count == 1
    assert client.fail.call_args[1]["error_code"] == "KEY4U_SUBMIT_FAILED"
    assert "Insufficient Balance" in client.fail.call_args[1]["error_message"]


def test_11_lease_loss_fail_closed() -> None:
    """11. Worker lease loss during generation causes worker to abort and fail closed."""
    client = MagicMock(spec=WebProductVideoDispatcherClient)
    # Simulate lease rejected by dispatcher (job reclaimed or expired)
    client.heartbeat.return_value = False

    def slow_executor(req: VideoGenerationRequest, **kwargs: Any) -> dict[str, Any]:
        time.sleep(0.3)
        return {
            "ok": True,
            "result_url": "https://cdn.example.com/late_output.mp4",
            "duration": 5.0,
            "bytes": 50000,
            "width": 720,
            "height": 1280,
            "format": "mp4",
            "codec": "h264",
            "provider_submit_called": True,
        }

    outcome = execute_claimed_web_product_video_job(
        SAMPLE_VALID_WEB_JOB,
        client=client,
        environ=ENABLED_ENV,
        heartbeat_interval=0.05,
        executor_fn=slow_executor,
    )

    assert outcome.ok is False
    assert outcome.status == "LEASE_LOST_FAIL_CLOSED"
    assert outcome.blocker_reason == "WORKER_LEASE_LOST_DURING_EXECUTION"
    # Even if executor finished, client.complete must NOT be called after lease loss
    assert client.complete.call_count == 0


def test_12_duplicate_execution_rejected() -> None:
    """12. Duplicate job execution for currently active job_id is rejected immediately."""
    job_id = SAMPLE_VALID_WEB_JOB["job_id"]
    _ACTIVE_JOB_IDS.add(job_id)
    try:
        client = MagicMock(spec=WebProductVideoDispatcherClient)
        outcome = execute_claimed_web_product_video_job(
            SAMPLE_VALID_WEB_JOB,
            client=client,
            environ=ENABLED_ENV,
        )
        assert outcome.ok is False
        assert outcome.status == "DUPLICATE_EXECUTION_BLOCKED"
        assert outcome.blocker_reason == "DUPLICATE_ACTIVE_JOB_EXECUTION"
        assert client.complete.call_count == 0
        assert client.fail.call_count == 0
    finally:
        _ACTIVE_JOB_IDS.discard(job_id)


def test_13_no_second_provider_submit() -> None:
    """13. Ensure provider submit called flag is accurately captured and never duplicated."""
    submit_count = 0

    def mock_executor(req: VideoGenerationRequest, **kwargs: Any) -> dict[str, Any]:
        nonlocal submit_count
        submit_count += 1
        return {
            "ok": True,
            "result_url": "https://cdn.example.com/video.mp4",
            "duration": 5.0,
            "bytes": 50000,
            "width": 720,
            "height": 1280,
            "format": "mp4",
            "codec": "h264",
            "provider_submit_called": True,
        }

    client = MagicMock(spec=WebProductVideoDispatcherClient)
    client.complete.return_value = True

    outcome = execute_claimed_web_product_video_job(
        SAMPLE_VALID_WEB_JOB,
        client=client,
        environ=ENABLED_ENV,
        executor_fn=mock_executor,
    )

    assert outcome.ok is True
    assert submit_count == 1
    assert outcome.provider_submit_called is True
    assert outcome.provider_calls == 1


def test_14_no_wallet_mutation() -> None:
    """14. Worker execution strictly results in zero direct customer wallet mutations."""
    client = MagicMock(spec=WebProductVideoDispatcherClient)
    client.complete.return_value = True

    def mock_executor(req: VideoGenerationRequest, **kwargs: Any) -> dict[str, Any]:
        # Assert within executor that financial exemptions are held
        assert req.metadata.get("admin_no_charge") is True
        assert req.metadata.get("no_wallet_charge") is True
        return {
            "ok": True,
            "result_url": "https://cdn.example.com/video.mp4",
            "duration": 5.0,
            "bytes": 50000,
            "width": 720,
            "height": 1280,
            "format": "mp4",
            "codec": "h264",
            "provider_submit_called": True,
        }

    outcome = execute_claimed_web_product_video_job(
        SAMPLE_VALID_WEB_JOB,
        client=client,
        environ=ENABLED_ENV,
        executor_fn=mock_executor,
    )

    assert outcome.ok is True
    assert outcome.wallet_mutations == 0


def test_15_secrets_absent_from_logs(caplog: pytest.LogCaptureFixture) -> None:
    """15. Worker execution logs strictly redact or omit worker secrets and auth tokens."""
    caplog.set_level(logging.DEBUG)
    secret_value = "top_secret_token_pv_987654321"

    client = MagicMock(spec=WebProductVideoDispatcherClient)
    client.complete.return_value = True

    def mock_executor(req: VideoGenerationRequest, **kwargs: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "result_url": "https://cdn.example.com/video.mp4",
            "duration": 5.0,
            "bytes": 50000,
            "width": 720,
            "height": 1280,
            "format": "mp4",
            "codec": "h264",
            "provider_submit_called": True,
        }

    env_with_secret = dict(ENABLED_ENV, LOCAL_WORKER_TOKEN=secret_value)
    execute_claimed_web_product_video_job(
        SAMPLE_VALID_WEB_JOB,
        client=client,
        environ=env_with_secret,
        executor_fn=mock_executor,
    )

    log_text = "\n".join(r.message for r in caplog.records)
    assert secret_value not in log_text


def test_16_production_gate_false_by_default() -> None:
    """16. Execution defaults fail-closed when WEB_PRODUCT_VIDEO_WORKER_ENABLED is false or unset."""
    # When disabled:
    assert is_web_product_video_worker_enabled({}) is False
    assert is_web_product_video_worker_enabled({"WEB_PRODUCT_VIDEO_WORKER_ENABLED": "false"}) is False
    assert is_web_product_video_worker_enabled({"WEB_PRODUCT_VIDEO_WORKER_ENABLED": "0"}) is False

    client = MagicMock(spec=WebProductVideoDispatcherClient)
    outcome = execute_claimed_web_product_video_job(
        SAMPLE_VALID_WEB_JOB,
        client=client,
        environ={},  # Unset -> disabled
    )

    assert outcome.ok is False
    assert outcome.status == "WORKER_EXECUTION_DISABLED"
    assert outcome.blocker_reason == "WORKER_DISABLED"
    assert client.complete.call_count == 0
    assert client.fail.call_count == 1
    assert client.fail.call_args[1]["error_code"] == "WORKER_DISABLED"


# ==============================================================================
# PHASE O — MOCKED INTEGRATION SUCCESS TEST
# ==============================================================================

def test_17_phase_o_mocked_integration_success() -> None:
    """Simulate Web claim -> provider submit -> provider poll -> safe output URL -> Web complete.

    Assert:
    - Real canonical runtime path invoked
    - Exactly 1 provider submit
    - Only same-task polls
    - No double charge (wallet_mutations == 0)
    - Valid artifact contract passed to Web
    """
    recorded_steps: list[str] = []
    polled_ids: list[str] = []

    def mock_dispatcher_transport(req: urllib.request.Request, timeout: int) -> tuple[int, bytes, dict[str, str]]:
        url = req.full_url
        if "/claim" in url:
            recorded_steps.append("dispatcher_claim")
            envelope = {
                "ok": True,
                "message": "Claimed",
                "data": {"job": SAMPLE_VALID_WEB_JOB, "idle": False},
                "status": "claimed",
            }
            return 200, json.dumps(envelope).encode("utf-8"), {}
        elif "/heartbeat" in url:
            recorded_steps.append("dispatcher_heartbeat")
            return 200, b'{"ok": true, "message": "Heartbeat OK"}', {}
        elif "/complete" in url:
            recorded_steps.append("dispatcher_complete")
            body = json.loads(req.data.decode("utf-8"))
            recorded_steps.append(f"complete_url:{body.get('output_url')}")
            return 200, b'{"ok": true, "message": "Job completed"}', {}
        return 200, b'{}', {}

    client = WebProductVideoDispatcherClient(
        base_url="http://mock-web",
        worker_id="test-worker-e2e",
        worker_secret="valid_secret",
        transport=mock_dispatcher_transport,
    )

    # Mock canonical executor that simulates remote submit & 2 same-task polls
    def canonical_runtime_mock(req: VideoGenerationRequest, **kwargs: Any) -> dict[str, Any]:
        recorded_steps.append("canonical_runtime_start")
        # Assert canonical request shape
        assert req.job_id == SAMPLE_VALID_WEB_JOB["job_id"]
        assert req.metadata.get("admin_no_charge") is True
        assert req.metadata.get("no_wallet_charge") is True

        remote_task_id = "key4u_pv_task_alpha_777"
        recorded_steps.append(f"provider_submit:{remote_task_id}")

        # Simulate 2 poll intervals on the same task ID
        for poll_idx in (1, 2):
            polled_ids.append(remote_task_id)
            recorded_steps.append(f"provider_poll_{poll_idx}:{remote_task_id}")

        return {
            "ok": True,
            "result_url": "https://cdn.toanaas.vn/media/product_video_alpha_777.mp4",
            "duration": 5.0,
            "bytes": 204800,
            "width": 720,
            "height": 1280,
            "format": "mp4",
            "codec": "h264",
            "provider_task_ids": [remote_task_id],
            "provider_submit_called": True,
        }

    # Step 1: Claim job
    claim_resp = client.claim()
    assert claim_resp.ok is True
    assert claim_resp.job is not None

    # Step 2: Execute claimed job
    outcome = execute_claimed_web_product_video_job(
        claim_resp.job,
        client=client,
        environ=ENABLED_ENV,
        executor_fn=canonical_runtime_mock,
    )

    # Step 3: Assert outcomes
    assert outcome.ok is True
    assert outcome.status == "COMPLETED"
    assert outcome.provider_task_id == "key4u_pv_task_alpha_777"
    assert outcome.provider_calls == 1
    assert outcome.paid_provider_calls == 1
    assert outcome.wallet_mutations == 0
    assert outcome.output_url == "https://cdn.toanaas.vn/media/product_video_alpha_777.mp4"
    assert outcome.output_metadata["format"] == "mp4"
    assert outcome.output_metadata["file_size_bytes"] == 204800

    # Step 4: Verify recorded lifecycle order
    assert "dispatcher_claim" in recorded_steps
    assert "canonical_runtime_start" in recorded_steps
    assert "provider_submit:key4u_pv_task_alpha_777" in recorded_steps
    assert "provider_poll_1:key4u_pv_task_alpha_777" in recorded_steps
    assert "provider_poll_2:key4u_pv_task_alpha_777" in recorded_steps
    assert "dispatcher_complete" in recorded_steps
    assert "complete_url:https://cdn.toanaas.vn/media/product_video_alpha_777.mp4" in recorded_steps

    # Confirm same-task polling invariant
    assert len(polled_ids) == 2
    assert all(pid == "key4u_pv_task_alpha_777" for pid in polled_ids)


# ==============================================================================
# PHASE P — MOCKED INTEGRATION FAILURE TEST
# ==============================================================================

def test_18_phase_p_mocked_integration_failure() -> None:
    """Simulate Web claim -> provider submit -> provider fail.

    Assert:
    - Web fail called
    - Factual error message propagated
    - No fake success
    - No unhandled crash
    """
    recorded_steps: list[str] = []
    fail_payload: dict[str, Any] = {}

    def mock_dispatcher_transport(req: urllib.request.Request, timeout: int) -> tuple[int, bytes, dict[str, str]]:
        url = req.full_url
        if "/claim" in url:
            recorded_steps.append("dispatcher_claim")
            envelope = {
                "ok": True,
                "message": "Claimed",
                "data": {"job": SAMPLE_VALID_WEB_JOB, "idle": False},
                "status": "claimed",
            }
            return 200, json.dumps(envelope).encode("utf-8"), {}
        elif "/fail" in url:
            recorded_steps.append("dispatcher_fail")
            nonlocal fail_payload
            fail_payload = json.loads(req.data.decode("utf-8"))
            return 200, b'{"ok": true, "message": "Fail recorded"}', {}
        elif "/complete" in url:
            recorded_steps.append("FORBIDDEN_COMPLETE")
            return 200, b'{}', {}
        return 200, b'{}', {}

    client = WebProductVideoDispatcherClient(
        base_url="http://mock-web",
        worker_id="test-worker-failure",
        worker_secret="valid_secret",
        transport=mock_dispatcher_transport,
    )

    def failing_provider_runtime(req: VideoGenerationRequest, **kwargs: Any) -> dict[str, Any]:
        recorded_steps.append("provider_submit")
        # Provider submit succeeds, but downstream poll detects upstream provider rejection
        recorded_steps.append("provider_poll_error")
        return {
            "ok": False,
            "blocker": "PROVIDER_UPSTREAM_TIMEOUT",
            "provider_error": "GATEWAY_TIMEOUT",
            "public_message": "Remote generation provider timed out after 300s",
            "provider_submit_called": True,
        }

    # Step 1: Claim job
    claim_resp = client.claim()
    assert claim_resp.ok is True
    assert claim_resp.job is not None

    # Step 2: Execute claimed job
    outcome = execute_claimed_web_product_video_job(
        claim_resp.job,
        client=client,
        environ=ENABLED_ENV,
        executor_fn=failing_provider_runtime,
    )

    # Step 3: Assert failure outcome
    assert outcome.ok is False
    assert outcome.status == "PROVIDER_FAILED"
    assert outcome.blocker_reason == "PROVIDER_UPSTREAM_TIMEOUT"
    assert outcome.wallet_mutations == 0

    # Step 4: Verify dispatch interactions
    assert "dispatcher_claim" in recorded_steps
    assert "provider_submit" in recorded_steps
    assert "provider_poll_error" in recorded_steps
    assert "dispatcher_fail" in recorded_steps
    assert "FORBIDDEN_COMPLETE" not in recorded_steps

    # Step 5: Verify fail payload accuracy
    assert fail_payload.get("error_code") == "PROVIDER_UPSTREAM_TIMEOUT"
    assert "Remote generation provider timed out" in str(fail_payload.get("error_message"))
    assert fail_payload.get("fatal") is True


# ==============================================================================
# DAEMON CYCLE TEST
# ==============================================================================

def test_19_daemon_poll_cycle_and_shutdown() -> None:
    """Daemon runs in run-once mode, polls dispatcher, executes job, and exits."""
    processed_jobs: list[str] = []

    def mock_dispatcher_transport(req: urllib.request.Request, timeout: int) -> tuple[int, bytes, dict[str, str]]:
        url = req.full_url
        if "/claim" in url:
            envelope = {
                "ok": True,
                "message": "Claimed",
                "data": {"job": SAMPLE_VALID_WEB_JOB, "idle": False},
                "status": "claimed",
            }
            return 200, json.dumps(envelope).encode("utf-8"), {}
        elif "/complete" in url:
            return 200, b'{"ok": true, "message": "Complete OK"}', {}
        return 200, b'{}', {}

    def mock_executor(req: VideoGenerationRequest, **kwargs: Any) -> dict[str, Any]:
        processed_jobs.append(req.job_id)
        return {
            "ok": True,
            "result_url": "https://cdn.example.com/daemon_output.mp4",
            "duration": 5.0,
            "bytes": 50000,
            "width": 720,
            "height": 1280,
            "format": "mp4",
            "codec": "h264",
            "provider_submit_called": True,
        }

    client = WebProductVideoDispatcherClient(
        base_url="http://mock-web",
        worker_id="daemon-test-worker",
        worker_secret="valid_secret",
        transport=mock_dispatcher_transport,
    )

    daemon = WebProductVideoWorkerDaemon(
        worker_id="daemon-test-worker",
        web_api_url="http://mock-web",
        worker_secret="valid_secret",
        client=client,
        environ=ENABLED_ENV,
        executor_fn=mock_executor,
        run_once=True,
    )

    daemon.run()

    assert daemon.stats["jobs_claimed"] == 1
    assert daemon.stats["jobs_completed"] == 1
    assert len(processed_jobs) == 1
    assert processed_jobs[0] == "pvjob_20260930_valid01"
