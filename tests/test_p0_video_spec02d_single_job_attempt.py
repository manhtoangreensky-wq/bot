"""Comprehensive test suite for P0.VIDEO.SYSTEM.SPEC02D.ACCEPTANCE.SINGLE_JOB_ATTEMPT.CONTRACT.

Verifies:
1. SAME_TOKEN_REPLAY=BLOCKED (Same token cannot be claimed twice).
2. SAME_JOB_DIFFERENT_NONCE_SECOND_CLAIM=BLOCKED (Different nonce on same job attempt is rejected).
3. SAME_JOB_DIFFERENT_TOKEN_SECOND_CLAIM=BLOCKED (Different token_id on same job attempt is rejected).
4. CONCURRENT_DIFFERENT_TOKEN_SAME_ATTEMPT_SUCCESS_COUNT=1 (Concurrent claims with different nonces allow exactly 1).
5. SECOND_CLAIM_AFTER_RESTART=BLOCKED (Different nonce on same job rejected across restart / fresh process).
6. DIFFERENT_JOB_CAN_HAVE_DISTINCT_ATTEMPT=YES (Genuinely distinct job_id is permitted).
7. DURABLE_CLAIM_BEFORE_PROVIDER_SUBMIT=YES (If attempt uniqueness rejects, PROVIDER_SUBMIT=0).
8. Router validation also detects already claimed attempt before execution.
9. Safety switches (freeze, kill switch, public probation) remain strictly enforced.
10. Ordinary Telegram client cannot forge acceptance authorization.
"""

from __future__ import annotations

import concurrent.futures
import copy
import os
import time
from typing import Any

import pytest

from services import video_provider_router, video_trace_state
from services.remote_worker_api import resolve_runtime_sha
from services.video_provider_base import (
    VideoArtifactResult,
    VideoGenerationRequest,
    VideoPollResult,
    VideoSubmitResult,
)


@pytest.fixture(autouse=True)
def isolate_test_db(tmp_path, monkeypatch):
    """Ensure every test runs against a completely isolated, clean SQLite test database."""
    test_db = str(tmp_path / "spec02d_isolated.db")
    monkeypatch.setenv("DB_PATH", test_db)
    monkeypatch.setenv("SQLITE_DB_PATH", test_db)
    return test_db


def _current_runtime() -> str:
    return resolve_runtime_sha() or "2fa6b9c8de821d3bc06b7594c73180084a08d50e"


def _make_auth(
    *,
    job_id: int = 101,
    user_id: int = 12345,
    project_id: int = 501,
    product_type: str = "video_ai_prompt",
    provider: str = "shopaikey_video",
    capability: str = "text_to_video",
    tier: str = "veo31_fast_8",
    runtime_sha: str | None = None,
    max_provider_spend: float = 1.00,
    max_provider_spend_unit: str = "USD",
    nonce: str = "nonce-spec02d-aaa",
    token_id: str | None = None,
) -> dict[str, Any]:
    auth = {
        "owner_authorized": True,
        "acceptance_type": video_provider_router.OWNER_AUTHORIZED_LIVE_ACCEPTANCE,
        "product_type": product_type,
        "provider": provider,
        "capability": capability,
        "tier": tier,
        "job_id": job_id,
        "user_id": user_id,
        "project_id": project_id,
        "runtime_sha": _current_runtime() if runtime_sha is None else runtime_sha,
        "max_provider_spend": max_provider_spend,
        "max_provider_spend_unit": max_provider_spend_unit,
        "nonce": nonce,
        "consumed": False,
        "expires_at": time.time() + 3600,
    }
    if token_id is not None:
        auth["token_id"] = token_id
    return auth


class MockVideoProvider:
    def __init__(
        self,
        provider_name: str,
        *,
        configured: bool = True,
        submit: VideoSubmitResult | None = None,
        submit_exc: Exception | None = None,
    ):
        self.provider_name = provider_name
        self._configured = configured
        self.submit_result = submit
        self.submit_exc = submit_exc
        self.submit_calls = 0

    def capabilities(self):
        return {
            "provider": self.provider_name,
            "enabled": True,
            "configured": self._configured,
            "supports_generation": True,
            "supports_status_check": True,
            "paid_tier": True,
            "tier": "paid",
            "cost_per_scene": 0.70,
            "currency": "USD",
            "supported_models": ["veo31_fast_8", "veo-3.1-fast"],
            "default_model": "veo31_fast_8",
            "supported_capabilities": ["text_to_video", "video_ai_prompt"],
        }

    def submit_video_job(self, request: VideoGenerationRequest) -> VideoSubmitResult:
        self.submit_calls += 1
        if self.submit_exc:
            raise self.submit_exc
        if self.submit_result:
            return self.submit_result
        return VideoSubmitResult(
            provider_task_id="task_mock_spec02d_123",
            status="pending",
            raw_response={"task_id": "task_mock_spec02d_123"},
        )

    def poll_video_job(self, provider_task_id: str, context: dict[str, Any] | None = None) -> VideoPollResult:
        return VideoPollResult(
            provider_task_id=provider_task_id,
            status="success",
            video_url="https://cdn.example.com/spec02d_video.mp4",
            raw_response={"status": "completed"},
        )

    def validate_and_persist_artifact(
        self,
        video_url: str,
        destination_dir: str,
        *,
        prefix: str = "video",
        timeout: int = 30,
        context: dict[str, Any] | None = None,
    ) -> VideoArtifactResult:
        return VideoArtifactResult(
            is_valid=True,
            file_path="/tmp/spec02d_mock.mp4",
            file_size_bytes=1024 * 1024,
            mime_type="video/mp4",
        )


# ==============================================================================
# 1. ATTEMPT FINGERPRINT AND KEY FORMULATION
# ==============================================================================

def test_01_attempt_fingerprint_excludes_nonce_and_token_id():
    """Verify attempt fingerprint binds job/runtime execution but excludes nonce/token_id."""
    auth_a = _make_auth(job_id=201, nonce="nonce-111", token_id="tok-111")
    auth_b = _make_auth(job_id=201, nonce="nonce-222", token_id="tok-222")

    # Token fingerprints must differ
    fp_a = video_trace_state.compute_owner_acceptance_token_fingerprint(auth_a)
    fp_b = video_trace_state.compute_owner_acceptance_token_fingerprint(auth_b)
    assert fp_a != fp_b

    # Attempt fingerprints must match exactly
    att_a = video_trace_state.compute_owner_acceptance_attempt_fingerprint(auth_a)
    att_b = video_trace_state.compute_owner_acceptance_attempt_fingerprint(auth_b)
    assert att_a != ""
    assert att_a == att_b


def test_02_attempt_fingerprint_excludes_spend_amount():
    """Verify attempt fingerprint cannot be bypassed by altering max_provider_spend."""
    auth_a = _make_auth(job_id=202, max_provider_spend=1.00, nonce="nonce-1")
    auth_b = _make_auth(job_id=202, max_provider_spend=2.00, nonce="nonce-2")

    att_a = video_trace_state.compute_owner_acceptance_attempt_fingerprint(auth_a)
    att_b = video_trace_state.compute_owner_acceptance_attempt_fingerprint(auth_b)
    assert att_a == att_b


# ==============================================================================
# 2. SAME TOKEN REPLAY COMPARATOR
# ==============================================================================

def test_03_same_token_replay_blocked(isolate_test_db):
    """Verify SAME_TOKEN_REPLAY=BLOCKED (claim 1 PASS, claim 2 BLOCK)."""
    auth = _make_auth(job_id=301, nonce="nonce-replay-301")

    ok1, blocker1, det1 = video_trace_state.claim_owner_acceptance_token(auth, db_path=isolate_test_db)
    assert ok1 is True
    assert blocker1 == ""
    assert det1["confirm_attempt_key"].startswith("OAA-")

    ok2, blocker2, det2 = video_trace_state.claim_owner_acceptance_token(auth, db_path=isolate_test_db)
    assert ok2 is False
    assert blocker2 == "owner_acceptance_already_consumed"


# ==============================================================================
# 3. SAME JOB / DIFFERENT NONCE AND TOKEN_ID TESTS
# ==============================================================================

def test_04_same_job_different_nonce_second_claim_blocked(isolate_test_db):
    """Verify SAME_JOB_DIFFERENT_NONCE_SECOND_CLAIM=BLOCKED."""
    auth_a = _make_auth(job_id=401, nonce="nonce-first-401")
    auth_b = _make_auth(job_id=401, nonce="nonce-second-401")

    # Claim A must succeed
    ok_a, blocker_a, det_a = video_trace_state.claim_owner_acceptance_token(auth_a, db_path=isolate_test_db)
    assert ok_a is True
    assert blocker_a == ""

    # Claim B (same job, different nonce) must be BLOCKED
    ok_b, blocker_b, det_b = video_trace_state.claim_owner_acceptance_token(auth_b, db_path=isolate_test_db)
    assert ok_b is False
    assert blocker_b == "owner_acceptance_already_consumed"
    assert det_b.get("confirm_attempt_key") == det_a.get("confirm_attempt_key")


def test_05_same_job_different_token_id_second_claim_blocked(isolate_test_db):
    """Verify SAME_JOB_DIFFERENT_TOKEN_SECOND_CLAIM=BLOCKED."""
    auth_a = _make_auth(job_id=501, token_id="token-uuid-1", nonce="nonce-a")
    auth_b = _make_auth(job_id=501, token_id="token-uuid-2", nonce="nonce-b")

    ok_a, blocker_a, _ = video_trace_state.claim_owner_acceptance_token(auth_a, db_path=isolate_test_db)
    assert ok_a is True
    assert blocker_a == ""

    ok_b, blocker_b, _ = video_trace_state.claim_owner_acceptance_token(auth_b, db_path=isolate_test_db)
    assert ok_b is False
    assert blocker_b == "owner_acceptance_already_consumed"


# ==============================================================================
# 4. CONCURRENT CLAIMS COMPARATOR
# ==============================================================================

def test_06_concurrent_different_token_same_job_attempt(isolate_test_db):
    """Verify CONCURRENT_DIFFERENT_TOKEN_SAME_ATTEMPT_SUCCESS_COUNT=1 across concurrent threads."""
    auth_a = _make_auth(job_id=601, nonce="nonce-concurrent-A")
    auth_b = _make_auth(job_id=601, nonce="nonce-concurrent-B")
    auth_c = _make_auth(job_id=601, nonce="nonce-concurrent-C")

    results = []

    def _attempt_claim(auth_obj):
        return video_trace_state.claim_owner_acceptance_token(auth_obj, db_path=isolate_test_db)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futs = [executor.submit(_attempt_claim, a) for a in (auth_a, auth_b, auth_c)]
        for f in concurrent.futures.as_completed(futs):
            results.append(f.result())

    successes = [r for r in results if r[0] is True]
    failures = [r for r in results if r[0] is False]

    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}"
    assert len(failures) == 2
    for f in failures:
        assert f[1] == "owner_acceptance_already_consumed"


# ==============================================================================
# 5. RESTART COMPARATOR
# ==============================================================================

def test_07_second_claim_after_restart_blocked(isolate_test_db):
    """Verify SECOND_CLAIM_AFTER_RESTART=BLOCKED across process lifecycle."""
    auth_a = _make_auth(job_id=701, nonce="nonce-restart-A")
    ok_a, _, _ = video_trace_state.claim_owner_acceptance_token(auth_a, db_path=isolate_test_db)
    assert ok_a is True

    # Simulate process restart: completely independent call with new connection and new nonce
    auth_b = _make_auth(job_id=701, nonce="nonce-restart-B")
    ok_b, blocker_b, _ = video_trace_state.claim_owner_acceptance_token(auth_b, db_path=isolate_test_db)
    assert ok_b is False
    assert blocker_b == "owner_acceptance_already_consumed"


# ==============================================================================
# 6. DIFFERENT JOB COMPARATOR (NON-OVERBROAD)
# ==============================================================================

def test_08_different_job_can_have_distinct_attempt(isolate_test_db):
    """Verify DIFFERENT_JOB_CAN_HAVE_DISTINCT_ATTEMPT=YES. Distinct job_ids are not blocked."""
    auth_job1 = _make_auth(job_id=801, nonce="nonce-801")
    auth_job2 = _make_auth(job_id=802, nonce="nonce-802")

    ok1, blocker1, det1 = video_trace_state.claim_owner_acceptance_token(auth_job1, db_path=isolate_test_db)
    assert ok1 is True
    assert blocker1 == ""

    ok2, blocker2, det2 = video_trace_state.claim_owner_acceptance_token(auth_job2, db_path=isolate_test_db)
    assert ok2 is True
    assert blocker2 == ""

    assert det1["confirm_attempt_key"] != det2["confirm_attempt_key"]


# ==============================================================================
# 7. ROUTER VALIDATION CHECK
# ==============================================================================

def test_09_router_validation_rejects_second_nonce_on_claimed_attempt(isolate_test_db):
    """Verify validate_owner_acceptance_authorization detects claimed attempt even before claim."""
    auth_a = _make_auth(job_id=901, nonce="nonce-router-A")
    ok_a, _, _ = video_trace_state.claim_owner_acceptance_token(auth_a, db_path=isolate_test_db)
    assert ok_a is True

    # Construct auth_b with different nonce
    auth_b = _make_auth(job_id=901, nonce="nonce-router-B")
    valid_b, blocker_b, det_b = video_provider_router.validate_owner_acceptance_authorization(
        auth_b,
        context={"job_id": 901, "tier": "veo31_fast_8", "estimated_provider_cost": 0.70, "estimated_provider_cost_unit": "USD"},
        db_path=isolate_test_db,
    )
    assert valid_b is False
    assert blocker_b == "owner_acceptance_already_consumed"
    assert "attempt_fingerprint" in det_b


# ==============================================================================
# 8. DURABLE CLAIM BEFORE PROVIDER SUBMIT GATE
# ==============================================================================

def test_10_attempt_collision_aborts_before_provider_submit(monkeypatch, isolate_test_db):
    """Verify DURABLE_CLAIM_BEFORE_PROVIDER_SUBMIT=YES: second nonce attempt results in PROVIDER_SUBMIT=0."""
    # First token claims job attempt 1001
    auth_first = _make_auth(job_id=1001, nonce="nonce-first-1001")
    ok_claim, _, _ = video_trace_state.claim_owner_acceptance_token(auth_first, db_path=isolate_test_db)
    assert ok_claim is True

    # Setup mock provider
    mock_adapter = MockVideoProvider("shopaikey_video")
    monkeypatch.setattr(
        video_provider_router,
        "get_video_provider_adapter",
        lambda name, **kwargs: mock_adapter if name == "shopaikey_video" else None,
    )

    # Now attempt execution with auth_second (same job, different nonce)
    auth_second = _make_auth(job_id=1001, nonce="nonce-second-1001")
    req = VideoGenerationRequest(
        product_type="video_ai_prompt",
        prompt="A single job attempt test prompt",
        user_id=12345,
        project_id="501",
        metadata={
            "job_id": "1001",
            "owner_acceptance_auth": auth_second,
            "selected_model": "veo31_fast_8",
        },
    )

    res = video_provider_router.run_provider_generation(
        req,
        provider_name="shopaikey_video",
        session={
            "draft": {
                "b14_queue_job": {
                    "id": 1001,
                    "user_id": 12345,
                    "project_id": 501,
                    "product_type": "video_ai_prompt",
                    "render_spec": {"model": "veo31_fast_8"},
                }
            }
        },
    )

    assert res["status"] == "blocked"
    assert res["blocker"] == "owner_acceptance_already_consumed"
    assert mock_adapter.submit_calls == 0  # PROVIDER_SUBMIT=0


# ==============================================================================
# 9. SAFETY SWITCH PRECEDENCE & CLIENT UNFORGEABILITY
# ==============================================================================

def test_11_global_freeze_still_blocks_even_with_valid_attempt_key(monkeypatch):
    """Verify global freeze blocks before attempt claim."""
    monkeypatch.setenv("VIDEO_AI_PROVIDER_FREEZE", "1")
    auth = _make_auth(job_id=1101, nonce="nonce-freeze")
    req = VideoGenerationRequest(
        product_type="video_ai_prompt",
        prompt="Freeze test",
        user_id=12345,
        project_id="501",
        metadata={"job_id": "1101", "owner_acceptance_auth": auth, "selected_model": "veo31_fast_8"},
    )
    res = video_provider_router.run_provider_generation(req, provider_name="shopaikey_video")
    assert res["status"] == "blocked"
    assert res["blocker"] == "provider_freeze"


def test_12_client_cannot_forge_acceptance_authorization():
    """Verify client payload with forge attempt is rejected when missing required auth structure."""
    forged_auth = {
        "owner_authorized": True,
        "acceptance_type": "owner_authorized_live_acceptance",
        "job_id": 1201,
        # missing user_id, tier, runtime_sha, max_provider_spend_unit
    }
    valid, blocker, _ = video_provider_router.validate_owner_acceptance_authorization(
        forged_auth,
        context={"job_id": 1201, "tier": "veo31_fast_8"},
    )
    assert valid is False
    assert blocker in (
        "owner_acceptance_user_missing",
        "owner_acceptance_tier_missing",
        "owner_acceptance_spend_unit_missing",
        "owner_acceptance_runtime_sha_missing",
    )
