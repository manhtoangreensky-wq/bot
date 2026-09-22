"""Test Suite for Web Product Video Bot Worker Consumer Adapter.

P0.WEBAPP.V3.CUSTOMER.PRODUCT_VIDEO.BOT_WORKER.CONSUMER.ADAPTER.R1
Program: P0.WEBAPP.FULL.PRODUCT.TRUTH.REMEDIATION.V1
"""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any
import pytest

from services.web_product_video_worker_consumer import (
    ALLOWED_ASPECT_RATIOS,
    BOT_CANONICAL_PRODUCT_KEY,
    BOT_EXECUTOR_PRODUCT_TYPE,
    DEFAULT_REQUIRED_CAPABILITY,
    PRIMARY_PRODUCT_KEY,
    SUPPORTED_PRODUCTS,
    InvalidJobEnvelopeError,
    PreparedExecutionOutcome,
    WebClaimResponse,
    WebProductVideoDispatcherClient,
    WorkerAuthError,
    WorkerClientError,
    get_web_base_url,
    get_worker_secret,
    map_web_job_to_bot_runtime,
    prepare_and_gate_execution,
    validate_claimed_job,
)

# Reference Web Dispatcher SHA pinned fixture
WEB_DISPATCHER_REFERENCE_SHA = "c62e8b502fa2d8e6b87b4298ba17d345e0e22729"

SAMPLE_VALID_WEB_JOB: dict[str, Any] = {
    "job_id": "pvjob_20260922_abc12345",
    "request_id": "req_video_ai_prompt_001",
    "account_id": "acc_cust_998877",
    "product_key": "video_ai_prompt",
    "status": "processing",
    "payload": {
        "prompt": "Cinematic high-end mechanical wrist watch spinning in water droplets",
        "aspect_ratio": "9:16",
        "duration": 6.0,
        "quality_tier": "standard",
    },
    "attempts": 1,
    "worker_id": "test-bot-worker-01",
    "claimed_at": "2026-09-22T22:00:00Z",
    "lease_expires_at": "2026-09-22T22:05:00Z",
    "output_url": None,
    "created_at": "2026-09-22T21:55:00Z",
    "updated_at": "2026-09-22T22:00:00Z",
}


def test_01_dispatcher_constants_and_configuration() -> None:
    """Verify primary product keys, supported products, and default capabilities."""
    assert PRIMARY_PRODUCT_KEY == "video_ai_prompt"
    assert SUPPORTED_PRODUCTS == frozenset({"video_ai_prompt"})
    assert BOT_CANONICAL_PRODUCT_KEY == "video_ai_prompt"
    assert BOT_EXECUTOR_PRODUCT_TYPE == "video_ai_prompt"
    assert DEFAULT_REQUIRED_CAPABILITY == "text_to_video"
    assert ALLOWED_ASPECT_RATIOS == frozenset({"9:16", "16:9", "1:1"})


def test_02_config_and_secret_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing or invalid worker secret fails closed with WorkerAuthError."""
    monkeypatch.delenv("PRODUCT_VIDEO_WORKER_SECRET", raising=False)
    monkeypatch.delenv("WORKER_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("TOANAAS_WORKER_SECRET", raising=False)

    assert get_worker_secret() == ""

    client = WebProductVideoDispatcherClient(worker_secret="")
    with pytest.raises(WorkerAuthError) as exc_info:
        client.claim()
    assert "MISSING_WORKER_SECRET" in str(exc_info.value)

    # Configurable Web URL without hardcoded production host
    monkeypatch.setenv("WEB_API_URL", "http://internal-web.local:8080")
    assert get_web_base_url() == "http://internal-web.local:8080"


def test_03_claim_serialization_and_empty_queue() -> None:
    """Verify request serialization for claim and graceful empty queue handling."""
    recorded_requests: list[dict[str, Any]] = []

    def mock_transport(req: urllib.request.Request, timeout: int) -> tuple[int, bytes, dict[str, str]]:
        body = json.loads(req.data.decode("utf-8")) if req.data else {}
        recorded_requests.append({
            "url": req.full_url,
            "method": req.get_method(),
            "headers": dict(req.headers),
            "body": body,
        })
        # Return idle queue envelope
        envelope = {
            "ok": True,
            "message": "Không có job nào trong hàng đợi.",
            "data": {"job": None, "idle": True},
            "status": "idle",
        }
        return 200, json.dumps(envelope).encode("utf-8"), {}

    client = WebProductVideoDispatcherClient(
        base_url="http://mock-web",
        worker_id="test-worker-alpha",
        worker_secret="valid_secret_xyz_123",
        transport=mock_transport,
    )

    response = client.claim(lease_seconds=120)
    assert response.ok is True
    assert response.idle is True
    assert response.job is None

    assert len(recorded_requests) == 1
    assert recorded_requests[0]["url"] == "http://mock-web/api/v1/worker/product-video/claim"
    assert recorded_requests[0]["method"] == "POST"
    assert recorded_requests[0]["body"] == {"worker_id": "test-worker-alpha", "lease_seconds": 120}
    assert "Bearer valid_secret_xyz_123" in recorded_requests[0]["headers"]["Authorization"]
    assert recorded_requests[0]["headers"]["X-worker-secret"] == "valid_secret_xyz_123"


def test_04_claim_success_envelope() -> None:
    """Verify claim parses active job payload properly."""
    def mock_transport(req: urllib.request.Request, timeout: int) -> tuple[int, bytes, dict[str, str]]:
        envelope = {
            "ok": True,
            "message": "Nhận job Product Video thành công.",
            "data": {"job": SAMPLE_VALID_WEB_JOB, "idle": False},
            "status": "claimed",
        }
        return 200, json.dumps(envelope).encode("utf-8"), {}

    client = WebProductVideoDispatcherClient(
        base_url="http://mock-web",
        worker_id="test-bot-worker-01",
        worker_secret="valid_secret_xyz_123",
        transport=mock_transport,
    )

    resp = client.claim(lease_seconds=300)
    assert resp.ok is True
    assert resp.idle is False
    assert resp.job is not None
    assert resp.job["job_id"] == "pvjob_20260922_abc12345"
    assert resp.job["product_key"] == "video_ai_prompt"


def test_05_job_envelope_validation_rules() -> None:
    """Reject malformed jobs before runtime mapping."""
    # 1. Valid job passes
    ok, err = validate_claimed_job(SAMPLE_VALID_WEB_JOB)
    assert ok is True
    assert err == ""

    # 2. Missing/short job_id
    bad_job = dict(SAMPLE_VALID_WEB_JOB, job_id="short")
    ok, err = validate_claimed_job(bad_job)
    assert ok is False
    assert err == "INVALID_OR_MISSING_JOB_ID"

    # 3. Missing request_id
    bad_job = dict(SAMPLE_VALID_WEB_JOB, request_id="")
    ok, err = validate_claimed_job(bad_job)
    assert ok is False
    assert err == "MISSING_REQUEST_ID"

    # 4. Wrong product key (outside R1 scope)
    bad_job = dict(SAMPLE_VALID_WEB_JOB, product_key="video_trend")
    ok, err = validate_claimed_job(bad_job)
    assert ok is False
    assert "UNSUPPORTED_PRODUCT" in err

    # 5. Wrong status
    bad_job = dict(SAMPLE_VALID_WEB_JOB, status="queued")
    ok, err = validate_claimed_job(bad_job)
    assert ok is False
    assert "INVALID_CLAIMED_STATUS" in err

    # 6. Malformed payload
    bad_job = dict(SAMPLE_VALID_WEB_JOB, payload="not_a_dict")
    ok, err = validate_claimed_job(bad_job)
    assert ok is False
    assert err == "MALFORMED_PAYLOAD_NOT_OBJECT"

    # 7. Prompt too short
    bad_job = dict(SAMPLE_VALID_WEB_JOB, payload={"prompt": "hi", "aspect_ratio": "9:16", "duration": 5.0})
    ok, err = validate_claimed_job(bad_job)
    assert ok is False
    assert err == "PROMPT_TOO_SHORT"

    # 8. Invalid aspect ratio
    bad_job = dict(SAMPLE_VALID_WEB_JOB, payload={"prompt": "valid prompt", "aspect_ratio": "4:3", "duration": 5.0})
    ok, err = validate_claimed_job(bad_job)
    assert ok is False
    assert "INVALID_ASPECT_RATIO" in err

    # 9. Invalid duration
    bad_job = dict(SAMPLE_VALID_WEB_JOB, payload={"prompt": "valid prompt", "aspect_ratio": "9:16", "duration": -5})
    ok, err = validate_claimed_job(bad_job)
    assert ok is False
    assert "DURATION_OUT_OF_BOUNDS" in err


def test_06_canonical_runtime_mapping() -> None:
    """Map valid Web Product Video job into Bot runtime VideoGenerationRequest."""
    gen_req = map_web_job_to_bot_runtime(SAMPLE_VALID_WEB_JOB)

    assert gen_req.job_id == "pvjob_20260922_abc12345"
    assert gen_req.product_type == "video_ai_prompt"
    assert gen_req.video_flow_type == "video_ai_prompt"
    assert gen_req.prompt == "Cinematic high-end mechanical wrist watch spinning in water droplets"
    assert gen_req.ratio == "9:16"
    assert gen_req.duration_seconds == 6.0
    assert gen_req.quality == "standard"
    assert gen_req.required_capability == "text_to_video"

    # Zero secondary wallet/payment charges
    assert gen_req.metadata.get("no_wallet_charge") is True
    assert gen_req.metadata.get("admin_no_charge") is True
    assert gen_req.metadata.get("web_dispatched") is True
    assert gen_req.metadata.get("account_id") == "acc_cust_998877"
    assert gen_req.metadata.get("web_request_id") == "req_video_ai_prompt_001"


def test_07_provider_free_preparation_boundary_and_gate() -> None:
    """Verify provider-free preparation stops strictly before provider execution."""
    outcome: PreparedExecutionOutcome = prepare_and_gate_execution(SAMPLE_VALID_WEB_JOB)

    assert outcome.ok is True
    assert outcome.status == "PREPARED_PROVIDER_BLOCKED"
    assert outcome.generation_request is not None
    assert outcome.generation_request.job_id == "pvjob_20260922_abc12345"

    # Strict provider-free invariants verified
    assert outcome.provider_submit_called is False
    assert outcome.provider_calls == 0
    assert outcome.paid_provider_calls == 0
    assert outcome.video_renders == 0
    assert outcome.wallet_mutations == 0


def test_08_heartbeat_lifecycle() -> None:
    """Verify heartbeat requests and 404 expired handling."""
    called_routes: list[str] = []

    def mock_transport(req: urllib.request.Request, timeout: int) -> tuple[int, bytes, dict[str, str]]:
        called_routes.append(req.full_url)
        body = json.loads(req.data.decode("utf-8")) if req.data else {}
        if body.get("job_id") == "pvjob_expired":
            return 404, b'{"detail": "Job expired"}', {}
        return 200, b'{"ok": true, "status": "heartbeat_ok", "data": {"lease_extended": true}}', {}

    client = WebProductVideoDispatcherClient(
        base_url="http://mock-web",
        worker_id="test-bot-worker-01",
        worker_secret="valid_secret_xyz",
        transport=mock_transport,
    )

    # 1. Active job heartbeat
    ok = client.heartbeat("pvjob_20260922_abc12345", lease_seconds=180)
    assert ok is True

    # 2. Expired / missing job heartbeat returns False
    expired_ok = client.heartbeat("pvjob_expired", lease_seconds=180)
    assert expired_ok is False


def test_09_fail_reporting_and_pre_provider_rejection() -> None:
    """Verify fail reporting to Web dispatcher when job is rejected pre-provider."""
    fail_payloads: list[dict[str, Any]] = []

    def mock_transport(req: urllib.request.Request, timeout: int) -> tuple[int, bytes, dict[str, str]]:
        if "fail" in req.full_url:
            body = json.loads(req.data.decode("utf-8")) if req.data else {}
            fail_payloads.append(body)
            return 200, b'{"ok": true, "status": "failed", "data": {"status": "failed"}}', {}
        return 200, b'{"ok": true}', {}

    client = WebProductVideoDispatcherClient(
        base_url="http://mock-web",
        worker_id="test-bot-worker-01",
        worker_secret="valid_secret_xyz",
        transport=mock_transport,
    )

    # Job with unsupported product
    unsupported_job = dict(SAMPLE_VALID_WEB_JOB, product_key="video_trend")
    outcome = prepare_and_gate_execution(unsupported_job, client=client)

    assert outcome.ok is False
    assert outcome.status == "INVALID_JOB_REJECTED"
    assert "UNSUPPORTED_PRODUCT" in outcome.blocker_reason

    # Proved client reported failure back to Web dispatcher
    assert len(fail_payloads) == 1
    assert fail_payloads[0]["job_id"] == "pvjob_20260922_abc12345"
    assert fail_payloads[0]["error_code"] == "VALIDATION_FAILED"
    assert "UNSUPPORTED_PRODUCT:video_trend" in fail_payloads[0]["error_message"]
    assert fail_payloads[0]["fatal"] is True


def test_10_complete_contract_schema_serialization() -> None:
    """Verify complete request serialization without fake runtime completion."""
    recorded_completes: list[dict[str, Any]] = []

    def mock_transport(req: urllib.request.Request, timeout: int) -> tuple[int, bytes, dict[str, str]]:
        body = json.loads(req.data.decode("utf-8")) if req.data else {}
        recorded_completes.append(body)
        return 200, b'{"ok": true, "status": "completed", "data": {"status": "completed"}}', {}

    client = WebProductVideoDispatcherClient(
        base_url="http://mock-web",
        worker_id="test-bot-worker-01",
        worker_secret="valid_secret_xyz",
        transport=mock_transport,
    )

    metadata = {
        "duration_seconds": 6.0,
        "width": 720,
        "height": 1280,
        "file_size_bytes": 1048576,
        "format": "video/mp4",
        "codec": "h264",
    }
    res = client.complete(
        job_id="pvjob_20260922_abc12345",
        output_url="https://static.toanaas.vn/video/output_abc123.mp4",
        output_metadata=metadata,
    )
    assert res.get("ok") is True
    assert len(recorded_completes) == 1
    assert recorded_completes[0]["output_url"] == "https://static.toanaas.vn/video/output_abc123.mp4"
    assert recorded_completes[0]["output_metadata"] == metadata


def test_11_client_security_and_transport_fail_closed() -> None:
    """Client handles 401, 500, network error, and non-JSON cleanly."""
    # 401 Unauthorized
    def transport_401(req: urllib.request.Request, timeout: int) -> tuple[int, bytes, dict[str, str]]:
        return 401, b'{"detail": "Unauthorized"}', {}

    client_401 = WebProductVideoDispatcherClient(
        base_url="http://mock-web",
        worker_secret="invalid_token",
        transport=transport_401,
    )
    with pytest.raises(WorkerAuthError):
        client_401.claim()

    # 500 Internal Server Error
    def transport_500(req: urllib.request.Request, timeout: int) -> tuple[int, bytes, dict[str, str]]:
        return 500, b'{"detail": "Internal Server Error"}', {}

    client_500 = WebProductVideoDispatcherClient(
        base_url="http://mock-web",
        worker_secret="valid_secret",
        transport=transport_500,
    )
    with pytest.raises(WorkerClientError):
        client_500.claim()

    # Malformed non-JSON
    def transport_bad_json(req: urllib.request.Request, timeout: int) -> tuple[int, bytes, dict[str, str]]:
        return 200, b'<html>Error</html>', {}

    client_bad_json = WebProductVideoDispatcherClient(
        base_url="http://mock-web",
        worker_secret="valid_secret",
        transport=transport_bad_json,
    )
    with pytest.raises(WorkerClientError):
        client_bad_json.claim()


def test_12_secret_not_exposed_in_logs(caplog: pytest.LogCaptureFixture) -> None:
    """Zero secret exposure in logs during worker operations."""
    caplog.set_level(logging.DEBUG)

    def mock_transport(req: urllib.request.Request, timeout: int) -> tuple[int, bytes, dict[str, str]]:
        envelope = {
            "ok": True,
            "message": "Claimed",
            "data": {"job": SAMPLE_VALID_WEB_JOB, "idle": False},
            "status": "claimed",
        }
        return 200, json.dumps(envelope).encode("utf-8"), {}

    secret_key = "super_confidential_worker_secret_9999"
    client = WebProductVideoDispatcherClient(
        base_url="http://mock-web",
        worker_id="worker-01",
        worker_secret=secret_key,
        transport=mock_transport,
    )

    client.claim()

    # Verify log contents do NOT contain the secret string
    full_log_text = "\n".join(record.message for record in caplog.records)
    assert secret_key not in full_log_text
    assert "Authorization" not in full_log_text


def test_13_first_red_absence_in_legacy_sources() -> None:
    """Prove that legacy remote_worker.py has no Web product-video dispatcher endpoints."""
    import pathlib
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    remote_worker_source = (repo_root / "remote_worker.py").read_text(encoding="utf-8")

    # The legacy worker only called Railway bot /api/v1/worker/claim, not Web product video endpoints
    assert "/api/v1/worker/product-video/claim" not in remote_worker_source
    assert "/api/v1/worker/product-video/heartbeat" not in remote_worker_source
    assert "/api/v1/worker/product-video/complete" not in remote_worker_source
    assert "/api/v1/worker/product-video/fail" not in remote_worker_source


def test_14_duplicate_execution_prevention() -> None:
    """Consumer rejects concurrent/duplicate execution for the same active job."""
    from services.web_product_video_worker_consumer import _ACTIVE_JOB_IDS

    job_id = SAMPLE_VALID_WEB_JOB["job_id"]
    _ACTIVE_JOB_IDS.add(job_id)
    try:
        outcome = prepare_and_gate_execution(SAMPLE_VALID_WEB_JOB)
        assert outcome.ok is False
        assert outcome.status == "DUPLICATE_EXECUTION_BLOCKED"
        assert outcome.blocker_reason == "DUPLICATE_ACTIVE_JOB_EXECUTION"
    finally:
        _ACTIVE_JOB_IDS.discard(job_id)


def test_15_provider_boundary_guarded_against_submission(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch provider submission to prove that provider submit is NEVER called."""
    provider_called = False

    def explode_on_provider_call(*args: Any, **kwargs: Any) -> Any:
        nonlocal provider_called
        provider_called = True
        raise AssertionError("FORBIDDEN: Provider submit must not be called during worker preparation")

    monkeypatch.setattr(
        "services.video_provider_router.run_provider_generation",
        explode_on_provider_call,
        raising=False,
    )

    outcome = prepare_and_gate_execution(SAMPLE_VALID_WEB_JOB)
    assert outcome.ok is True
    assert outcome.status == "PREPARED_PROVIDER_BLOCKED"
    assert provider_called is False
    assert outcome.provider_submit_called is False
    assert outcome.provider_calls == 0
    assert outcome.paid_provider_calls == 0
    assert outcome.video_renders == 0
    assert outcome.wallet_mutations == 0
