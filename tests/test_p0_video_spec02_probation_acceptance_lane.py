"""Tests for P0 SPEC-02: Probation Admission Controlled Acceptance Lane.

Enforces:
1. Ordinary probation blocked for public job
2. Authorized acceptance allowed for matching job
3. Wrong provider blocked
4. Wrong product blocked
5. Wrong user blocked
6. Wrong job blocked
7. Authorization reuse blocked (one-time use)
8. Global freeze still blocks acceptance job
9. Provider freeze still blocks acceptance job
10. Kill switch still blocks acceptance job
11. Capability mismatch still blocks acceptance job
12. Over-budget still blocks acceptance job
13. Ambiguous submit still fail-closed with zero charge
14. Task-id present still polls without duplicate submit
15. Poll timeout still fail-closed without fallback
16. Failed acceptance does not mark provider healthy
17. Mocked valid delivered artifact flows through normal health evaluator to transition provider to healthy
18. No global public admission open
"""

import time
import socket
import pytest

from services import video_provider_router
from services.video_provider_base import (
    BLOCKER_AMBIGUOUS_SUBMIT,
    SUBMIT_OUTCOME_AMBIGUOUS,
    VideoArtifactResult,
    VideoGenerationRequest,
    VideoPollResult,
    VideoSubmitResult,
)


try:
    from services.remote_worker_api import resolve_runtime_sha
    CURRENT_TEST_RUNTIME_SHA = resolve_runtime_sha() or "8dc3cdef83dbb4d19a45f2b4e079dc3ac8adbc71"
except Exception:
    CURRENT_TEST_RUNTIME_SHA = "8dc3cdef83dbb4d19a45f2b4e079dc3ac8adbc71"

CANONICAL_ACCEPTANCE_RUNTIME_SHA = CURRENT_TEST_RUNTIME_SHA


@pytest.fixture(autouse=True)
def isolate_test_db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_spec02.db")
    monkeypatch.setenv("DB_PATH", test_db)
    monkeypatch.setenv("SQLITE_DB_PATH", test_db)


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
    ):
        self.provider_name = provider_name
        self._configured = configured
        self.submit_result = submit
        self.submit_exc = submit_exc
        self.poll_result = poll
        self.poll_exc = poll_exc
        self.artifact_result = artifact
        self.submit_calls = 0
        self.poll_calls = 0

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
            provider_name=self.provider_name,
            status="completed",
            result_url="https://example.com/video.mp4",
            raw={"http_status": 200},
        )

    def download_and_validate_video_artifact(self, result_url: str, output_path: str):
        if self.artifact_result is not None:
            return self.artifact_result
        return VideoArtifactResult(
            ok=True,
            local_path=output_path,
            bytes=1024 * 500,
            duration=5.0,
            has_video_stream=True,
            has_audio_stream=True,
            artifact_hash="hash_mock_mp4",
        )

    def materialize_result(self, poll_result: VideoPollResult, output_name: str) -> VideoArtifactResult:
        if self.artifact_result is not None:
            return self.artifact_result
        return VideoArtifactResult(
            ok=True,
            local_path=f"data/test_video_outputs/{output_name}.mp4",
            bytes=1024 * 500,
            duration=5.0,
            has_video_stream=True,
            has_audio_stream=True,
            artifact_hash="hash_mock_mp4",
        )


def _base_valid_auth(*, job_id=101, user_id=12345, project_id=501):
    return {
        "owner_authorized": True,
        "acceptance_type": video_provider_router.OWNER_AUTHORIZED_LIVE_ACCEPTANCE,
        "product_type": "video_ai_prompt",
        "provider": "shopaikey_video",
        "capability": "text_to_video",
        "tier": "veo31_fast_8",
        "job_id": job_id,
        "user_id": user_id,
        "project_id": project_id,
        "runtime_sha": CANONICAL_ACCEPTANCE_RUNTIME_SHA,
        "max_provider_spend": 1.00,
        "max_provider_spend_unit": "USD",
        "consumed": False,
        "expires_at": time.time() + 3600,
    }


def _probation_degraded_providers():
    return {
        "shopaikey_video": {
            "route_ready": True,
            "live_healthy": False,
            "health_status": "unknown",
            "provider_degraded_for_product_video_public": False,
        },
        "key4u_video": {
            "route_ready": True,
            "live_healthy": False,
            "health_status": "unknown",
            "provider_degraded_for_product_video_public": False,
        },
    }


def _probation_status():
    return {
        "configured": True,
        "credit_ok": True,
        "provider_chain": ["shopaikey_video", "key4u_video"],
        "effective_provider_chain": ["shopaikey_video", "key4u_video"],
        "providers": [
            {
                "provider": "shopaikey_video",
                "configured": True,
                "credit_ok": True,
                "capabilities": ["text_to_video"],
            },
            {
                "provider": "key4u_video",
                "configured": True,
                "credit_ok": True,
                "capabilities": ["text_to_video"],
            },
        ],
    }


def test_01_ordinary_probation_blocked_for_public_job():
    """Scenario 1: Ordinary public job with owner_acceptance_auth=None remains strictly blocked by probation."""
    decision = video_provider_router.product_video_public_provider_route_decision(
        status=_probation_status(),
        chain=["shopaikey_video", "key4u_video"],
        degraded_providers=_probation_degraded_providers(),
        owner_acceptance_auth=None,
    )
    assert decision["ok"] is False
    assert decision["selected_provider"] == ""
    assert decision["blocker"] == "no_healthy_video_provider_no_charge"
    assert decision["admission_mode"] == "probation_pending_final_confirm"


def test_02_authorized_acceptance_allowed_for_matching_job():
    """Scenario 2: Matching Owner-authorized acceptance lane allows pinned provider through probation."""
    auth = _base_valid_auth(job_id=101, user_id=12345)
    decision = video_provider_router.product_video_public_provider_route_decision(
        status=_probation_status(),
        chain=["shopaikey_video", "key4u_video"],
        degraded_providers=_probation_degraded_providers(),
        owner_acceptance_auth=auth,
        acceptance_context={"job_id": 101, "user_id": 12345, "product_type": "video_ai_prompt"},
    )
    assert decision["ok"] is True
    assert decision["selected_provider"] == "shopaikey_video"
    assert decision["effective_provider_chain"] == ["shopaikey_video"]
    assert decision["owner_acceptance_valid"] is True
    assert decision["admission_mode"] == "owner_authorized_acceptance"
    assert decision["primary_selected_due_to_health"] == "owner_authorized_acceptance_lane"


def test_03_wrong_provider_blocked():
    """Scenario 3: Attempting to authorize an unsupported or mismatched provider is blocked."""
    auth = _base_valid_auth()
    auth["provider"] = "key4u_video"  # First acceptance lane is pinned to shopaikey_video only
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(
        auth, context={"provider": "key4u_video"}
    )
    assert valid is False
    assert reason in {"owner_acceptance_provider_mismatch", "owner_acceptance_provider_not_authorized"}

    # Context provider mismatch
    auth2 = _base_valid_auth()
    valid2, reason2, _ = video_provider_router.validate_owner_acceptance_authorization(
        auth2, context={"provider": "key4u_video"}
    )
    assert valid2 is False
    assert reason2 == "owner_acceptance_provider_mismatch"


def test_04_wrong_product_blocked():
    """Scenario 4: Wrong product type is rejected by validation."""
    auth = _base_valid_auth()
    auth["product_type"] = "image_generation"
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(
        auth, context={"product_type": "image_generation"}
    )
    assert valid is False
    assert reason == "owner_acceptance_product_mismatch"

    # Context product mismatch
    auth2 = _base_valid_auth()
    valid2, reason2, _ = video_provider_router.validate_owner_acceptance_authorization(
        auth2, context={"product_type": "video_talking_head"}
    )
    assert valid2 is False
    assert reason2 == "owner_acceptance_product_mismatch"


def test_05_wrong_user_blocked():
    """Scenario 5: Authorization bound to user A is rejected when executed by user B."""
    auth = _base_valid_auth(user_id=12345)
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(
        auth, context={"user_id": 99999}
    )
    assert valid is False
    assert reason == "owner_acceptance_user_mismatch"


def test_06_wrong_job_blocked():
    """Scenario 6: Authorization bound to job A is rejected when executed for job B."""
    auth = _base_valid_auth(job_id=101)
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(
        auth, context={"job_id": 202}
    )
    assert valid is False
    assert reason == "owner_acceptance_job_mismatch"


def test_07_authorization_reuse_blocked_one_time_use(tmp_path, monkeypatch):
    """Scenario 7: Authorization is marked consumed on terminal state and cannot be reused."""
    shopai_mock = MockVideoProvider("shopaikey_video")
    key4u_mock = MockVideoProvider("key4u_video")
    monkeypatch.setattr(
        video_provider_router,
        "load_video_provider_adapters",
        lambda env=None: [shopai_mock, key4u_mock],
    )
    monkeypatch.setattr(
        video_provider_router,
        "provider_status_payload",
        lambda env=None: _probation_status(),
    )

    auth = _base_valid_auth(job_id=101, user_id=12345)
    req = VideoGenerationRequest(
        job_id="101",
        prompt="A serene sunset over mountains",
        required_capability="text_to_video",
        product_type="video_ai_prompt",
        metadata={
            "product_video": True,
            "owner_acceptance_auth": auth,
            "user_id": 12345,
            "job_id": 101,
            "product_type": "video_ai_prompt",
            "provider": "shopaikey_video",
            "runtime_sha": CANONICAL_ACCEPTANCE_RUNTIME_SHA,
        },
    )

    # First run succeeds and consumes the authorization
    res1 = video_provider_router.run_provider_generation(req, output_dir=str(tmp_path))
    assert res1["ok"] is True
    assert res1.get("owner_acceptance_consumed") is True
    assert auth.get("consumed") is True

    # Second run with same auth dictionary fails immediately with already consumed
    res2 = video_provider_router.run_provider_generation(req, output_dir=str(tmp_path))
    assert res2["ok"] is False
    assert res2["blocker"] == "owner_acceptance_already_consumed"
    assert res2["external_provider_spend_prevented"] is True
    assert res2["charge"] == 0


def test_08_global_freeze_still_blocks_acceptance_job(monkeypatch):
    """Scenario 8: Global freeze still blocks acceptance job."""
    freeze_truth = video_provider_router.product_video_freeze_truth(
        source=video_provider_router.OWNER_AUTHORIZED_LIVE_ACCEPTANCE,
        job_context={"provider_freeze": True},
    )
    assert freeze_truth["public_live_allowed"] is False
    assert freeze_truth["blocker_code"] == "provider_freeze_active"

    spend_freeze = video_provider_router.product_video_freeze_truth(
        source=video_provider_router.OWNER_AUTHORIZED_LIVE_ACCEPTANCE,
        job_context={"provider_spend_freeze": True},
    )
    assert spend_freeze["public_live_allowed"] is False
    assert spend_freeze["blocker_code"] == "provider_spend_freeze_active"


def test_09_provider_freeze_still_blocks_acceptance_job():
    """Scenario 9: Explicit provider freeze still blocks acceptance job."""
    freeze_truth = video_provider_router.product_video_freeze_truth(
        source=video_provider_router.OWNER_AUTHORIZED_LIVE_ACCEPTANCE,
        job_context={"public_provider_freeze": True},
    )
    assert freeze_truth["public_live_allowed"] is False
    assert freeze_truth["blocker_code"] == "public_provider_freeze_active"


def test_10_kill_switch_still_blocks_acceptance_job():
    """Scenario 10: Kill switch (submit disabled) still blocks acceptance job."""
    freeze_truth = video_provider_router.product_video_freeze_truth(
        source=video_provider_router.OWNER_AUTHORIZED_LIVE_ACCEPTANCE,
        job_context={"public_submit_enabled": False},
    )
    assert freeze_truth["public_live_allowed"] is False
    assert freeze_truth["blocker_code"] == "public_provider_submit_disabled"

    policy = video_provider_router.product_video_provider_submit_source_policy(
        {"submit_source": video_provider_router.OWNER_AUTHORIZED_LIVE_ACCEPTANCE},
        public_submit_enabled=False,
    )
    assert policy["provider_submit_allowed"] is False
    assert policy["provider_submit_block_reason"] == "public_provider_submit_disabled"


def test_11_capability_mismatch_still_blocks_acceptance_job():
    """Scenario 11: Capability mismatch between authorization and request is blocked."""
    auth = _base_valid_auth()
    auth["capability"] = "text_to_video"
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(
        auth, context={"required_capability": "image_to_video"}
    )
    assert valid is False
    assert reason == "owner_acceptance_capability_mismatch"


def test_12_over_budget_still_blocks_acceptance_job():
    """Scenario 12: Estimated provider spend exceeding authorization ceiling is blocked."""
    auth = _base_valid_auth()
    auth["max_provider_spend"] = 0.50
    auth["max_provider_spend_unit"] = "USD"
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(
        auth, context={"estimated_provider_cost": 0.80, "estimated_provider_cost_unit": "USD"}
    )
    assert valid is False
    assert reason == "owner_acceptance_spend_limit_exceeded"


def test_13_ambiguous_submit_still_fail_closed_with_zero_charge(tmp_path, monkeypatch):
    """Scenario 13: Network timeout on submit fail-closed with zero charge and no fallback."""
    shopai_mock = MockVideoProvider(
        "shopaikey_video",
        submit_exc=socket.timeout("Connection timed out to ShopAIKey"),
    )
    key4u_mock = MockVideoProvider("key4u_video")
    monkeypatch.setattr(
        video_provider_router,
        "load_video_provider_adapters",
        lambda env=None: [shopai_mock, key4u_mock],
    )
    monkeypatch.setattr(
        video_provider_router,
        "provider_status_payload",
        lambda env=None: _probation_status(),
    )

    auth = _base_valid_auth(job_id=103)
    req = VideoGenerationRequest(
        job_id="103",
        prompt="A serene sunset over mountains",
        required_capability="text_to_video",
        product_type="video_ai_prompt",
        metadata={
            "product_video": True,
            "owner_acceptance_auth": auth,
            "user_id": 12345,
            "job_id": 103,
            "product_type": "video_ai_prompt",
            "provider": "shopaikey_video",
            "runtime_sha": CANONICAL_ACCEPTANCE_RUNTIME_SHA,
        },
    )

    res = video_provider_router.run_provider_generation(req, output_dir=str(tmp_path))
    assert res["ok"] is False
    assert res["charge"] == 0
    assert res["no_charge"] is True
    assert res["fallback_allowed"] is False
    assert res["blocker"] == BLOCKER_AMBIGUOUS_SUBMIT
    # Key4U must NEVER be attempted
    assert key4u_mock.submit_calls == 0


def test_14_task_id_present_still_polls_without_duplicate_submit(tmp_path, monkeypatch):
    """Scenario 14: Existing task_id triggers polling only without re-submitting."""
    shopai_mock = MockVideoProvider("shopaikey_video")
    monkeypatch.setattr(
        video_provider_router,
        "load_video_provider_adapters",
        lambda env=None: [shopai_mock],
    )
    monkeypatch.setattr(
        video_provider_router,
        "provider_status_payload",
        lambda env=None: _probation_status(),
    )

    auth = _base_valid_auth(job_id=104)
    req = VideoGenerationRequest(
        job_id="104",
        prompt="A serene sunset over mountains",
        required_capability="text_to_video",
        product_type="video_ai_prompt",
        metadata={
            "product_video": True,
            "owner_acceptance_auth": auth,
            "user_id": 12345,
            "job_id": 104,
            "product_type": "video_ai_prompt",
            "provider": "shopaikey_video",
            "provider_pending_task_id": "shopaikey-task-existing-456",
            "provider_pending_provider": "shopaikey_video",
            "runtime_sha": CANONICAL_ACCEPTANCE_RUNTIME_SHA,
        },
    )

    res = video_provider_router.run_provider_generation(req, output_dir=str(tmp_path))
    assert res["ok"] is True
    # Submit was NOT called because task_id was already present
    assert shopai_mock.submit_calls == 0
    assert shopai_mock.poll_calls == 1


def test_15_poll_timeout_still_fail_closed_without_fallback(tmp_path, monkeypatch):
    """Scenario 15: Polling timeout terminates fail-closed with zero charge and no Key4U fallback."""
    shopai_mock = MockVideoProvider(
        "shopaikey_video",
        poll=VideoPollResult(
            ok=False,
            provider_name="shopaikey_video",
            status="running",
            error_code="provider_poll_timeout",
            raw={"http_status": 200},
        ),
    )
    key4u_mock = MockVideoProvider("key4u_video")
    monkeypatch.setattr(
        video_provider_router,
        "load_video_provider_adapters",
        lambda env=None: [shopai_mock, key4u_mock],
    )
    monkeypatch.setattr(
        video_provider_router,
        "provider_status_payload",
        lambda env=None: _probation_status(),
    )

    auth = _base_valid_auth(job_id=105)
    req = VideoGenerationRequest(
        job_id="105",
        prompt="A serene sunset over mountains",
        required_capability="text_to_video",
        product_type="video_ai_prompt",
        metadata={
            "product_video": True,
            "owner_acceptance_auth": auth,
            "user_id": 12345,
            "job_id": 105,
            "product_type": "video_ai_prompt",
            "provider": "shopaikey_video",
            "runtime_sha": CANONICAL_ACCEPTANCE_RUNTIME_SHA,
        },
    )

    res = video_provider_router.run_provider_generation(
        req,
        output_dir=str(tmp_path),
        sleep_func=lambda s: None,
        allow_pending_result=False,
    )
    assert res["ok"] is False
    assert res["charge"] == 0
    assert res["no_charge"] is True
    assert res["status"] == "failed_no_charge"
    assert res["terminal_state"] == "failed_no_charge"
    assert res["fallback_allowed"] is False
    assert key4u_mock.submit_calls == 0


def test_16_failed_acceptance_does_not_mark_provider_healthy():
    """Scenario 16: An acceptance run that failed does not produce valid output evidence, keeping provider unhealthy."""
    # Attempt evidence has only failed attempt
    attempts = [
        {
            "provider": "shopaikey_video",
            "status": "failed_no_charge",
            "delivered": False,
            "has_valid_mp4": False,
            "created_at": time.time(),
        }
    ]
    degradation = video_provider_router.product_video_provider_public_degradation(
        "shopaikey_video",
        attempts,
        route_ready=True,
    )
    assert degradation["live_healthy"] is False
    assert degradation["recent_valid_output"] is False


def test_17_mocked_valid_delivered_artifact_transitions_provider_to_healthy():
    """Scenario 17: Mock valid delivered MP4 output transitions provider to healthy through authoritative degradation evaluator."""
    attempts = [
        {
            "provider": "shopaikey_video",
            "status": "downloaded",
            "delivered": True,
            "delivery_message_id": 99991,
            "has_valid_mp4": True,
            "valid_mp4": True,
            "artifact_size": 1024 * 1000,
            "result_url": "https://example.com/valid.mp4",
            "created_at": time.time(),
            "updated_at": time.time(),
        }
    ]
    degradation = video_provider_router.product_video_provider_public_degradation(
        "shopaikey_video",
        attempts,
        route_ready=True,
    )
    assert degradation["live_healthy"] is True
    assert degradation["recent_valid_output"] is True
    assert degradation["health_status"] == "healthy"


def test_18_no_global_public_admission_open():
    """Scenario 18: Normal public users with unauthenticated requests cannot bypass probation."""
    normal_request_auth = None
    decision = video_provider_router.product_video_public_provider_route_decision(
        status=_probation_status(),
        chain=["shopaikey_video", "key4u_video"],
        degraded_providers=_probation_degraded_providers(),
        owner_acceptance_auth=normal_request_auth,
    )
    assert decision["ok"] is False
    assert decision["selected_provider"] == ""
    assert decision["owner_acceptance_valid"] is False
    assert decision["admission_mode"] == "probation_pending_final_confirm"

    # Forged auth without owner_authorized flag
    forged_auth = {"owner_authorized": False, "acceptance_type": "owner_authorized_live_acceptance"}
    decision2 = video_provider_router.product_video_public_provider_route_decision(
        status=_probation_status(),
        chain=["shopaikey_video", "key4u_video"],
        degraded_providers=_probation_degraded_providers(),
        owner_acceptance_auth=forged_auth,
    )
    assert decision2["ok"] is False
    assert decision2["owner_acceptance_valid"] is False
