"""Tests for P0 SPEC-01: Paid Submit Exactly-Once & Failover Safety.

Eliminates all 4 crash windows:
- Crash Window A: request reaches provider but response is lost.
- Crash Window B: provider returns task_id but local save crashes or caller retries.
- Crash Window C: submit times out, caller falls back to another paid provider.
- Crash Window D: worker restarts while provider job is in flight.

Enforces:
- PAID_SUBMIT_COUNT <= 1 per job/provider attempt.
- AMBIGUOUS_SUBMIT_AUTO_RESUBMIT = NO
- AMBIGUOUS_SUBMIT_AUTO_FAILOVER = NO
- AMBIGUOUS_SUBMIT_USER_CHARGE = 0
- TASK_ID_PRESENT_AUTO_RESUBMIT = NO (poll existing task only)
- POLL_TIMEOUT_AUTO_RESUBMIT = NO
- WORKER_RESTART_AUTO_RESUBMIT = NO
- PAID_FAILOVER_SAFE = YES
"""

import socket
import urllib.error
import pytest

from services import video_provider_router
from services.video_provider_base import (
    BLOCKER_AMBIGUOUS_SUBMIT,
    SUBMIT_OUTCOME_ACCEPTED,
    SUBMIT_OUTCOME_AMBIGUOUS,
    VideoArtifactResult,
    VideoGenerationRequest,
    VideoPollResult,
    VideoSubmitResult,
)


class MockVideoProvider:
    def __init__(
        self,
        provider_name: str,
        *,
        configured: bool = True,
        submit: VideoSubmitResult | None = None,
        submit_exc: Exception | None = None,
        poll: VideoPollResult | None = None,
        poll_exc: Exception | None = None,
        artifact: VideoArtifactResult | None = None,
        artifact_exc: Exception | None = None,
    ):
        self.provider_name = provider_name
        self._configured = configured
        self.submit_result = submit
        self.submit_exc = submit_exc
        self.poll_result = poll
        self.poll_exc = poll_exc
        self.artifact_result = artifact
        self.artifact_exc = artifact_exc
        self.submit_calls = 0
        self.poll_calls = 0
        self.materialize_calls = 0

    def capabilities(self):
        return {
            "provider": self.provider_name,
            "enabled": True,
            "configured": self._configured,
            "missing": [] if self._configured else ["api_key"],
            "capabilities": ["text_to_video", "scene_video", "multi_scene_video"],
            "endpoint_configured": self._configured,
            "submit_url_configured": self._configured,
            "poll_url_configured": self._configured,
            "auth_configured": self._configured,
            "model_configured": True,
            "provider_auth_value_present": self._configured,
            "provider_model_present": True,
            "provider_payload_model": "veo3.1-fast",
            "provider_config_source": f"env:{self.provider_name}",
        }

    def submit_video_job(self, request):
        self.submit_calls += 1
        if self.submit_exc is not None:
            raise self.submit_exc
        if not self._configured:
            return VideoSubmitResult(
                ok=False,
                provider_name=self.provider_name,
                error_code="provider_config_missing_at_submit",
                raw={"provider_submit_blocker": "provider_config_missing_at_submit", "pre_send_failure": True},
            )
        if self.submit_result is not None:
            return self.submit_result
        return VideoSubmitResult(
            ok=True,
            provider_name=self.provider_name,
            provider_task_id=f"{self.provider_name}-task-123",
            provider_status="running",
            raw={"http_status": 200, "task_id_field_path": "data.task_id"},
        )

    def poll_video_job(self, provider_task_id: str, **kwargs):
        self.poll_calls += 1
        if self.poll_exc is not None:
            raise self.poll_exc
        if self.poll_result is not None:
            return self.poll_result
        return VideoPollResult(
            ok=True,
            status="succeeded",
            provider_name=self.provider_name,
            provider_task_id=provider_task_id,
            result_url="https://example.test/completed_video.mp4",
            raw={"poll_http_status": 200, "provider_status_raw": "succeeded"},
        )

    def materialize_result(self, result, job_id: str):
        self.materialize_calls += 1
        if self.artifact_exc is not None:
            raise self.artifact_exc
        if self.artifact_result is not None:
            return self.artifact_result
        return VideoArtifactResult(
            ok=True,
            local_path="/tmp/test_video.mp4",
            bytes=1024 * 1024,
            duration=6.0,
            has_video_stream=True,
            has_audio_stream=True,
            artifact_hash="hash123",
        )


def _request(metadata=None, **kwargs):
    base_meta = {
        "product_video": True,
        "allow_provider_pending": True,
        "wallet_charge": False,
        "user_final_confirmed": True,
        "public_user_confirmed": True,
    }
    base_meta.update(metadata or {})
    params = {
        "job_id": "job-spec01-777",
        "product_type": "video_ai_prompt",
        "video_flow_type": "video_ai_prompt",
        "prompt": "Cinematic mountain sunset",
        "ratio": "9:16",
        "duration_seconds": 6.0,
        "required_capability": "text_to_video",
        "metadata": base_meta,
    }
    params.update(kwargs)
    return VideoGenerationRequest(**params)


def _env(**updates):
    data = {
        "VIDEO_PROVIDER_CHAIN": "shopaikey_video,key4u_video",
        "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "2",
        "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS": "0",
        "PRODUCT_VIDEO_PROVIDER_SUBMIT_ENABLED": "1",
    }
    data.update({key: str(value) for key, value in updates.items()})
    return data


def _run(monkeypatch, tmp_path, providers, *, metadata=None, env=None, req_kwargs=None):
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: providers)
    return video_provider_router.run_provider_generation(
        _request(metadata, **(req_kwargs or {})),
        output_dir=str(tmp_path),
        environ=env or _env(),
        sleep_func=lambda _sec: None,
    )


# ==============================================================================
# 1. Normal ShopAIKey success
# ==============================================================================
def test_scenario_01_normal_shopaikey_success(monkeypatch, tmp_path):
    shop = MockVideoProvider("shopaikey_video")
    key4u = MockVideoProvider("key4u_video")
    result = _run(monkeypatch, tmp_path, [shop, key4u])

    assert result["ok"] is True
    assert shop.submit_calls == 1
    assert shop.poll_calls == 1
    assert shop.materialize_calls == 1
    assert key4u.submit_calls == 0
    assert result["selected_provider"] == "shopaikey_video"


# ==============================================================================
# 2. Normal Key4U success
# ==============================================================================
def test_scenario_02_normal_key4u_success(monkeypatch, tmp_path):
    key4u = MockVideoProvider("key4u_video")
    result = _run(
        monkeypatch,
        tmp_path,
        [key4u],
        env=_env(VIDEO_PROVIDER_CHAIN="key4u_video"),
    )

    assert result["ok"] is True
    assert key4u.submit_calls == 1
    assert key4u.poll_calls == 1
    assert result["selected_provider"] == "key4u_video"


# ==============================================================================
# 3. Pre-send config failure (safe failover allowed)
# ==============================================================================
def test_scenario_03_presend_config_failure_allows_safe_failover(monkeypatch, tmp_path):
    shop = MockVideoProvider("shopaikey_video", configured=False)
    key4u = MockVideoProvider("key4u_video", configured=True)
    result = _run(monkeypatch, tmp_path, [shop, key4u])

    assert shop.submit_calls == 0
    assert key4u.submit_calls == 1
    assert result["ok"] is True
    assert result["selected_provider"] == "key4u_video"


# ==============================================================================
# 4. Pre-send DNS/connection failure (safe failover allowed)
# ==============================================================================
def test_scenario_04_presend_dns_failure_allows_safe_failover(monkeypatch, tmp_path):
    shop = MockVideoProvider(
        "shopaikey_video",
        submit=VideoSubmitResult(
            ok=False,
            provider_name="shopaikey_video",
            error_code="provider_submit_dns_failed",
            raw={"http_status": 0, "is_dns_error": True, "pre_send_failure": True},
        ),
    )
    key4u = MockVideoProvider("key4u_video")
    result = _run(
        monkeypatch,
        tmp_path,
        [shop, key4u],
        metadata={"paid_provider_retry_confirmed": True},
    )

    assert shop.submit_calls == 1
    assert key4u.submit_calls == 1
    assert result["ok"] is True
    assert result["selected_provider"] == "key4u_video"


# ==============================================================================
# 5. Ambiguous timeout after send (FAILOVER=NO, RESUBMIT=NO, CHARGE=0)
# ==============================================================================
def test_scenario_05_ambiguous_timeout_blocks_failover_and_no_charge(monkeypatch, tmp_path):
    shop = MockVideoProvider(
        "shopaikey_video",
        submit_exc=TimeoutError("Connection to shopaikey timed out during POST"),
    )
    key4u = MockVideoProvider("key4u_video")
    result = _run(
        monkeypatch,
        tmp_path,
        [shop, key4u],
        metadata={
            "paid_provider_retry_confirmed": True,
            "paid_fallback_confirmed": True,
        },
    )

    assert result["ok"] is False
    assert shop.submit_calls == 1
    assert key4u.submit_calls == 0  # FAILOVER STRICTLY BLOCKED
    assert result["blocker"] == BLOCKER_AMBIGUOUS_SUBMIT
    assert result["fallback_allowed"] is False
    assert result["no_charge"] is True
    assert result["charge"] == 0
    assert result["ambiguous_submit_prevented_duplicate_paid_call"] is True


def test_scenario_05b_ambiguous_timeout_in_submit_result_blocks_failover(monkeypatch, tmp_path):
    shop = MockVideoProvider(
        "shopaikey_video",
        submit=VideoSubmitResult(
            ok=False,
            provider_name="shopaikey_video",
            error_code=BLOCKER_AMBIGUOUS_SUBMIT,
            raw={"is_timeout": True, "ambiguous_submit": True, "provider_http_request_sent": True},
        ),
    )
    key4u = MockVideoProvider("key4u_video")
    result = _run(
        monkeypatch,
        tmp_path,
        [shop, key4u],
        metadata={
            "paid_provider_retry_confirmed": True,
            "paid_fallback_confirmed": True,
        },
    )

    assert result["ok"] is False
    assert shop.submit_calls == 1
    assert key4u.submit_calls == 0  # FAILOVER STRICTLY BLOCKED
    assert result["blocker"] == BLOCKER_AMBIGUOUS_SUBMIT
    assert result["fallback_allowed"] is False
    assert result["no_charge"] is True
    assert result["charge"] == 0


# ==============================================================================
# 6. Lost HTTP response after provider accepted (504 Gateway Timeout, CHARGE=0)
# ==============================================================================
def test_scenario_06_lost_http_response_gateway_timeout_blocks_failover(monkeypatch, tmp_path):
    shop = MockVideoProvider(
        "shopaikey_video",
        submit=VideoSubmitResult(
            ok=False,
            provider_name="shopaikey_video",
            error_code="provider_submit_outcome_ambiguous_no_charge",
            raw={"http_status": 504, "submit_http_status": 504, "provider_http_request_sent": True},
        ),
    )
    key4u = MockVideoProvider("key4u_video")
    result = _run(
        monkeypatch,
        tmp_path,
        [shop, key4u],
        metadata={"paid_provider_retry_confirmed": True},
    )

    assert result["ok"] is False
    assert shop.submit_calls == 1
    assert key4u.submit_calls == 0  # FAILOVER STRICTLY BLOCKED
    assert result["blocker"] == BLOCKER_AMBIGUOUS_SUBMIT
    assert result["no_charge"] is True
    assert result["charge"] == 0


# ==============================================================================
# 7. Task ID received then crash (recovers & polls same task)
# ==============================================================================
def test_scenario_07_task_id_received_polls_same_task_without_resubmit(monkeypatch, tmp_path):
    shop = MockVideoProvider("shopaikey_video")
    key4u = MockVideoProvider("key4u_video")
    result = _run(
        monkeypatch,
        tmp_path,
        [shop, key4u],
        metadata={
            "provider_pending_provider": "shopaikey_video",
            "provider_pending_task_id": "shop-existing-task-777",
            "provider_pending_request_job_id": "job-spec01-777",
        },
    )

    assert result["ok"] is True
    assert shop.submit_calls == 0  # NO RESUBMIT
    assert shop.poll_calls == 1   # Polled existing task
    assert key4u.submit_calls == 0


# ==============================================================================
# 8. Task ID persisted then crash (polls same task)
# ==============================================================================
def test_scenario_08_task_id_persisted_in_result_json_polls_same_task(monkeypatch, tmp_path):
    shop = MockVideoProvider("shopaikey_video")
    key4u = MockVideoProvider("key4u_video")
    result = _run(
        monkeypatch,
        tmp_path,
        [shop, key4u],
        metadata={
            "persisted_result_json": {
                "provider_task_ids": ["shop-persisted-task-888"],
            },
        },
    )

    assert result["ok"] is True
    assert shop.submit_calls == 0  # NO RESUBMIT
    assert shop.poll_calls == 1   # Polled persisted task
    assert key4u.submit_calls == 0


# ==============================================================================
# 9. Poll timeout (no new submit, no failover)
# ==============================================================================
def test_scenario_09_poll_timeout_blocks_failover_and_no_duplicate_submit(monkeypatch, tmp_path):
    shop = MockVideoProvider(
        "shopaikey_video",
        poll=VideoPollResult(
            ok=True,
            status="running",
            provider_name="shopaikey_video",
            provider_task_id="shop-task-999",
            raw={"provider_status_raw": "running"},
        ),
    )
    key4u = MockVideoProvider("key4u_video")
    result = _run(
        monkeypatch,
        tmp_path,
        [shop, key4u],
        metadata={
            "paid_provider_retry_confirmed": True,
            "product_video": False,
            "allow_provider_pending": False,
        },
        env=_env(VIDEO_PROVIDER_MAX_POLL_ATTEMPTS="2"),
    )

    assert result["ok"] is False
    assert shop.submit_calls == 1
    assert shop.poll_calls == 2
    assert key4u.submit_calls == 0  # FAILOVER STRICTLY BLOCKED ON IN-FLIGHT TIMEOUT
    assert result["fallback_allowed"] is False
    assert result["no_charge"] is True


# ==============================================================================
# 10. Worker restart with active task (polls same task)
# ==============================================================================
def test_scenario_10_worker_restart_polls_active_task_no_resubmit(monkeypatch, tmp_path):
    shop = MockVideoProvider("shopaikey_video")
    result = _run(
        monkeypatch,
        tmp_path,
        [shop],
        metadata={
            "submit_source": "worker_poll_existing_task",
            "provider_pending_task_id": "shop-active-task-1010",
        },
    )

    assert result["ok"] is True
    assert shop.submit_calls == 0  # NO NEW SUBMISSION
    assert shop.poll_calls == 1
    assert result["provider_submit_called"] is False


# ==============================================================================
# 11. Result download transient failure (no paid resubmit)
# ==============================================================================
def test_scenario_11_download_transient_failure_does_not_resubmit_paid_fallback(monkeypatch, tmp_path):
    shop = MockVideoProvider(
        "shopaikey_video",
        artifact=VideoArtifactResult(ok=False, error_code="provider_download_failed", bytes=0),
    )
    key4u = MockVideoProvider("key4u_video")
    result = _run(
        monkeypatch,
        tmp_path,
        [shop, key4u],
        metadata={"paid_provider_retry_confirmed": True},
    )

    assert shop.submit_calls == 1
    assert shop.poll_calls == 1
    assert shop.materialize_calls == 1
    assert key4u.submit_calls == 0  # DO NOT RESUBMIT TO KEY4U
    assert result["no_charge"] is True


# ==============================================================================
# 12. Terminal provider failure (no charge)
# ==============================================================================
def test_scenario_12_terminal_provider_failure_ensures_zero_charge(monkeypatch, tmp_path):
    shop = MockVideoProvider(
        "shopaikey_video",
        poll=VideoPollResult(
            ok=False,
            status="failed",
            error_code="generation_failed_safety_filter",
            provider_name="shopaikey_video",
        ),
    )
    key4u = MockVideoProvider("key4u_video")
    result = _run(
        monkeypatch,
        tmp_path,
        [shop, key4u],
        env=_env(VIDEO_PROVIDER_CHAIN="shopaikey_video"),
    )

    assert result["ok"] is False
    assert shop.submit_calls == 1
    assert shop.poll_calls == 1
    assert result["no_charge"] is True
    assert result["charge"] == 0


# ==============================================================================
# 13. Manual retry with existing task_id vs ambiguous submit
# ==============================================================================
def test_scenario_13_manual_retry_behavior_matrix(monkeypatch, tmp_path):
    # Part A: With existing task_id, retry only polls
    shop = MockVideoProvider("shopaikey_video")
    res_with_task = _run(
        monkeypatch,
        tmp_path,
        [shop],
        metadata={"provider_pending_task_id": "existing-task-13A"},
    )
    assert shop.submit_calls == 0
    assert shop.poll_calls == 1
    assert res_with_task["ok"] is True

    # Part B: Ambiguous submit cannot auto-resubmit
    shop_ambiguous = MockVideoProvider(
        "shopaikey_video",
        submit_exc=TimeoutError("Request timed out waiting for headers"),
    )
    key4u = MockVideoProvider("key4u_video")
    res_ambiguous = _run(
        monkeypatch,
        tmp_path,
        [shop_ambiguous, key4u],
        metadata={"paid_provider_retry_confirmed": True},
    )
    assert res_ambiguous["ok"] is False
    assert res_ambiguous["blocker"] == BLOCKER_AMBIGUOUS_SUBMIT
    assert key4u.submit_calls == 0
