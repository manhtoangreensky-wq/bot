"""Comprehensive test suite for P0.VIDEO.SYSTEM.SPEC02C.ACCEPTANCE.AUTHORIZATION.DURABILITY.HARDENING.

Verifies:
1. Dynamic runtime SHA authority (current runtime resolved dynamically, stale rejected, unresolvable rejected).
2. Strict tier binding (CROSS_TIER_REUSE=NO, veo31_fast_8 vs kling_v1 rejected).
3. Spend unit contract (CROSS_UNIT_COMPARISON=NO, USD vs Xu/VND rejected, within budget accepted, over budget rejected).
4. Durable one-time token persistence in SQLite WAL (ATOMIC_ONE_TIME_CLAIM=PASS, TOKEN_REPLAY_AFTER_RESTART=BLOCKED).
5. Bound identity validation (wrong user, job, project, product, provider, capability rejected).
6. Safety switches precedence (freeze, kill switch, public probation remain strictly enforced).
7. Client forgeability prevention (ordinary user cannot forge acceptance authorization).
8. Pre-submit durable claim invariant (DURABLE_CLAIM_BEFORE_PROVIDER_SUBMIT=YES, claim failure prevents provider submit).
"""

from __future__ import annotations

import concurrent.futures
import copy
import os
import socket
import time
from pathlib import Path
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
    test_db = str(tmp_path / "spec02c_isolated.db")
    monkeypatch.setenv("DB_PATH", test_db)
    monkeypatch.setenv("SQLITE_DB_PATH", test_db)
    return test_db


def _current_runtime() -> str:
    return resolve_runtime_sha() or "8dc3cdef83dbb4d19a45f2b4e079dc3ac8adbc71"


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
    nonce: str = "nonce-abc-123",
) -> dict[str, Any]:
    return {
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
            "missing": [] if self._configured else ["api_key"],
            "capabilities": ["text_to_video", "scene_video"],
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
        if self.submit_result is not None:
            return self.submit_result
        return VideoSubmitResult(
            ok=True,
            provider_name=self.provider_name,
            provider_task_id=f"{self.provider_name}-task-999",
            provider_status="running",
            raw={"http_status": 200, "task_id_field_path": "data.task_id"},
        )

    def poll_video_job(self, provider_task_id: str, **kwargs):
        return VideoPollResult(
            ok=True,
            provider_name=self.provider_name,
            status="completed",
            result_url="https://example.com/video.mp4",
            raw={"http_status": 200},
        )

    def download_and_validate_video_artifact(self, result_url: str, output_path: str):
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
        return VideoArtifactResult(
            ok=True,
            local_path=f"data/test_video_outputs/{output_name}.mp4",
            bytes=1024 * 500,
            duration=5.0,
            has_video_stream=True,
            has_audio_stream=True,
            artifact_hash="hash_mock_mp4",
        )


# ===========================================================================
# 1. RUNTIME SHA TESTS
# ===========================================================================

def test_01_current_runtime_sha_dynamically_resolved():
    """Current runtime SHA is dynamically resolved when context omits runtime_sha."""
    auth = _make_auth()
    valid, reason, verified = video_provider_router.validate_owner_acceptance_authorization(
        auth,
        context={"job_id": 101, "user_id": 12345},
    )
    assert valid is True
    assert reason == ""
    assert verified["runtime_sha"] == _current_runtime()
    assert verified["verified"] is True


def test_02_stale_runtime_sha_rejected():
    """Stale runtime SHA (e.g. legacy d2c2d1e1...) is strictly rejected."""
    auth = _make_auth(runtime_sha="d2c2d1e1a82d7bf1452ea51030380f8f00d5990c")
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(
        auth,
        context={"job_id": 101, "user_id": 12345},
    )
    assert valid is False
    assert reason == "owner_acceptance_runtime_sha_mismatch"


def test_03_unresolvable_runtime_sha_rejected(monkeypatch):
    """If runtime SHA cannot be resolved from git or environ, fail-closed."""
    auth = _make_auth(runtime_sha="any_sha_123")
    monkeypatch.setattr("services.remote_worker_api.resolve_runtime_sha", lambda environ=None, cwd=None: "")
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(
        auth,
        context={"job_id": 101, "user_id": 12345},
        environ={},
    )
    assert valid is False
    assert reason == "owner_acceptance_runtime_sha_unresolvable"


def test_04_missing_runtime_sha_in_auth_rejected():
    """Missing runtime SHA in auth dictionary is rejected."""
    auth = _make_auth()
    auth.pop("runtime_sha")
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(
        auth,
        context={"job_id": 101, "user_id": 12345},
    )
    assert valid is False
    assert reason == "owner_acceptance_runtime_sha_missing"


# ===========================================================================
# 2. TIER BINDING TESTS (CROSS_TIER_REUSE=NO)
# ===========================================================================

def test_05_tier_mismatch_rejected():
    """Authorization for veo31_fast_8 rejected when context requests kling_v1."""
    auth = _make_auth(tier="veo31_fast_8")
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(
        auth,
        context={"job_id": 101, "tier": "kling_v1"},
    )
    assert valid is False
    assert reason == "owner_acceptance_tier_mismatch"


def test_06_tier_matching_accepted():
    """Matching tier is accepted and pinned in verified payload."""
    auth = _make_auth(tier="veo31_fast_8")
    valid, reason, verified = video_provider_router.validate_owner_acceptance_authorization(
        auth,
        context={"job_id": 101, "tier": "veo31_fast_8"},
    )
    assert valid is True
    assert reason == ""
    assert verified["pinned_tier"] == "veo31_fast_8"


def test_07_missing_tier_in_auth_rejected_when_context_has_tier():
    """If auth has no tier specified but context has tier, reject to prevent wildcard reuse."""
    auth = _make_auth()
    auth.pop("tier")
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(
        auth,
        context={"job_id": 101, "tier": "kling_v1"},
    )
    assert valid is False
    assert reason == "owner_acceptance_tier_missing"


# ===========================================================================
# 3. SPEND UNIT & BUDGET TESTS (CROSS_UNIT_COMPARISON=NO)
# ===========================================================================

def test_08_missing_spend_unit_rejected():
    """Authorization with max_provider_spend but missing max_provider_spend_unit is rejected."""
    auth = _make_auth(max_provider_spend=1.00)
    auth.pop("max_provider_spend_unit")
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(
        auth,
        context={"job_id": 101, "estimated_provider_cost": 0.70, "estimated_provider_cost_unit": "USD"},
    )
    assert valid is False
    assert reason == "owner_acceptance_spend_unit_missing"


def test_09_unit_mismatch_rejected_xu_vs_usd():
    """80 Xu vs 1.00 USD is rejected fail-closed (cross-unit comparison blocked)."""
    auth = _make_auth(max_provider_spend=1.00, max_provider_spend_unit="USD")
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(
        auth,
        context={"job_id": 101, "estimated_provider_cost": 80.0, "estimated_provider_cost_unit": "XU"},
    )
    assert valid is False
    assert reason == "owner_acceptance_spend_unit_mismatch"


def test_10_unit_mismatch_rejected_vnd_vs_usd():
    """2275 VND vs 1.00 USD is rejected fail-closed (cross-unit comparison blocked)."""
    auth = _make_auth(max_provider_spend=1.00, max_provider_spend_unit="USD")
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(
        auth,
        context={"job_id": 101, "estimated_provider_cost": 2275.0, "estimated_provider_cost_unit": "VND"},
    )
    assert valid is False
    assert reason == "owner_acceptance_spend_unit_mismatch"


def test_11_within_spend_accepted():
    """0.70 USD <= 1.00 USD is accepted."""
    auth = _make_auth(max_provider_spend=1.00, max_provider_spend_unit="USD")
    valid, reason, verified = video_provider_router.validate_owner_acceptance_authorization(
        auth,
        context={"job_id": 101, "estimated_provider_cost": 0.70, "estimated_provider_cost_unit": "USD"},
    )
    assert valid is True
    assert reason == ""
    assert verified["max_provider_spend"] == 1.00
    assert verified["max_provider_spend_unit"] == "USD"


def test_12_over_spend_rejected():
    """1.20 USD > 1.00 USD is rejected with owner_acceptance_spend_limit_exceeded."""
    auth = _make_auth(max_provider_spend=1.00, max_provider_spend_unit="USD")
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(
        auth,
        context={"job_id": 101, "estimated_provider_cost": 1.20, "estimated_provider_cost_unit": "USD"},
    )
    assert valid is False
    assert reason == "owner_acceptance_spend_limit_exceeded"


# ===========================================================================
# 4. DURABLE ONE-TIME CLAIM & REPLAY PROTECTION TESTS
# ===========================================================================

def test_13_durable_claim_first_attempt_succeeds(isolate_test_db):
    """First durable claim of a valid token succeeds and persists row in video_request_traces."""
    auth = _make_auth(nonce="nonce-13")
    fp = video_trace_state.compute_owner_acceptance_token_fingerprint(auth)
    assert bool(fp) is True
    assert video_trace_state.is_owner_acceptance_token_claimed_or_consumed(fp, db_path=isolate_test_db) is False

    ok, blocker, details = video_trace_state.claim_owner_acceptance_token(auth, db_path=isolate_test_db)
    assert ok is True
    assert blocker == ""
    assert details["stage"] == "CLAIMED"
    assert video_trace_state.is_owner_acceptance_token_claimed_or_consumed(fp, db_path=isolate_test_db) is True


def test_14_concurrent_double_claim_atomic_cas(isolate_test_db):
    """Two concurrent workers attempting to claim the same token: exactly one succeeds."""
    video_trace_state.ensure_video_trace_schema(db_path=isolate_test_db)
    auth = _make_auth(nonce="nonce-concurrent-cas")

    def try_claim():
        return video_trace_state.claim_owner_acceptance_token(auth, db_path=isolate_test_db)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(try_claim)
        f2 = executor.submit(try_claim)
        r1 = f1.result()
        r2 = f2.result()

    results = [r1, r2]
    successes = [r for r in results if r[0] is True]
    rejections = [r for r in results if r[0] is False]

    assert len(successes) == 1, "Exactly one worker must succeed in atomic CAS claim"
    assert len(rejections) == 1, "Exactly one worker must be rejected"
    assert rejections[0][1] == "owner_acceptance_already_consumed"


def test_15_process_restart_replay_blocked(isolate_test_db):
    """Token claimed in persistent SQLite store cannot be replayed after process reconstruction."""
    auth = _make_auth(nonce="nonce-restart-replay")
    ok, _, _ = video_trace_state.claim_owner_acceptance_token(auth, db_path=isolate_test_db)
    assert ok is True

    # Simulate process restart: destroy in-memory object, create brand new dict with consumed=False
    reconstructed_auth = _make_auth(nonce="nonce-restart-replay")
    assert reconstructed_auth["consumed"] is False

    # Validator must check persistent DB and block
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(
        reconstructed_auth,
        context={"job_id": 101, "user_id": 12345},
        db_path=isolate_test_db,
    )
    assert valid is False
    assert reason == "owner_acceptance_already_consumed"


# ===========================================================================
# 5. BOUND IDENTITY ATTRIBUTES VALIDATION
# ===========================================================================

def test_16_wrong_user_rejected():
    auth = _make_auth(user_id=12345)
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(
        auth, context={"user_id": 99999}
    )
    assert valid is False
    assert reason == "owner_acceptance_user_mismatch"


def test_17_wrong_job_rejected():
    auth = _make_auth(job_id=101)
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(
        auth, context={"job_id": 999}
    )
    assert valid is False
    assert reason == "owner_acceptance_job_mismatch"


def test_18_wrong_project_rejected():
    auth = _make_auth(project_id=501)
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(
        auth, context={"project_id": 888}
    )
    assert valid is False
    assert reason == "owner_acceptance_project_mismatch"


def test_19_wrong_product_rejected():
    auth = _make_auth(product_type="video_ai_prompt")
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(
        auth, context={"product_type": "talking_avatar"}
    )
    assert valid is False
    assert reason == "owner_acceptance_product_mismatch"


def test_20_wrong_provider_rejected():
    auth = _make_auth(provider="shopaikey_video")
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(
        auth, context={"provider": "key4u_video"}
    )
    assert valid is False
    assert reason == "owner_acceptance_provider_mismatch"


def test_21_wrong_capability_rejected():
    auth = _make_auth(capability="text_to_video")
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(
        auth, context={"required_capability": "image_to_video"}
    )
    assert valid is False
    assert reason == "owner_acceptance_capability_mismatch"


# ===========================================================================
# 6. SAFETY SWITCHES PRECEDENCE
# ===========================================================================

def test_22_global_freeze_still_blocks():
    freeze_truth = video_provider_router.product_video_freeze_truth(
        source=video_provider_router.OWNER_AUTHORIZED_LIVE_ACCEPTANCE,
        job_context={"provider_freeze": True},
    )
    assert freeze_truth["public_live_allowed"] is False
    assert freeze_truth["blocker_code"] == "provider_freeze_active"


def test_23_kill_switch_still_blocks():
    freeze_truth = video_provider_router.product_video_freeze_truth(
        source=video_provider_router.OWNER_AUTHORIZED_LIVE_ACCEPTANCE,
        job_context={"public_submit_enabled": False},
    )
    assert freeze_truth["public_live_allowed"] is False
    assert freeze_truth["blocker_code"] == "public_provider_submit_disabled"


def test_24_ordinary_public_probation_still_blocks():
    decision = video_provider_router.product_video_public_provider_route_decision(
        status={
            "configured": True,
            "credit_ok": True,
            "provider_chain": ["shopaikey_video", "key4u_video"],
            "effective_provider_chain": ["shopaikey_video", "key4u_video"],
            "providers": [
                {"provider": "shopaikey_video", "configured": True, "credit_ok": True, "capabilities": ["text_to_video"]},
                {"provider": "key4u_video", "configured": True, "credit_ok": True, "capabilities": ["text_to_video"]},
            ],
        },
        chain=["shopaikey_video", "key4u_video"],
        degraded_providers={
            "shopaikey_video": {"route_ready": True, "live_healthy": False, "health_status": "unknown", "provider_degraded_for_product_video_public": False},
            "key4u_video": {"route_ready": True, "live_healthy": False, "health_status": "unknown", "provider_degraded_for_product_video_public": False},
        },
        owner_acceptance_auth=None,
    )
    assert decision["ok"] is False
    assert decision["blocker"] == "no_healthy_video_provider_no_charge"
    assert decision["admission_mode"] == "probation_pending_final_confirm"


# ===========================================================================
# 7. CLIENT FORGEABILITY & PRE-SUBMIT CLAIM GATE
# ===========================================================================

def test_25_client_cannot_forge_authorization():
    """Client request dictionary without trusted server-side authorization is rejected."""
    client_payload = {
        "owner_authorized": False,  # Client attempting to spoof or omitting flag
        "acceptance_type": video_provider_router.OWNER_AUTHORIZED_LIVE_ACCEPTANCE,
    }
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(client_payload)
    assert valid is False
    assert reason == "owner_authorization_flag_missing"


def test_26_pre_submit_claim_failure_prevents_provider_submit(tmp_path, isolate_test_db, monkeypatch):
    """If durable claim fails right before submit, current_adapter.submit_video_job is NEVER called (PROVIDER_SUBMIT=0)."""
    shopai_mock = MockVideoProvider("shopaikey_video")
    monkeypatch.setattr(
        video_provider_router,
        "load_video_provider_adapters",
        lambda env=None: [shopai_mock],
    )
    monkeypatch.setattr(
        video_provider_router,
        "provider_status_payload",
        lambda env=None: {
            "configured": True,
            "credit_ok": True,
            "provider_chain": ["shopaikey_video"],
            "effective_provider_chain": ["shopaikey_video"],
            "providers": [{"provider": "shopaikey_video", "configured": True, "credit_ok": True, "capabilities": ["text_to_video"]}],
        },
    )

    auth = _make_auth(job_id=888, nonce="nonce-claim-fail-gate")
    # Pre-claim the token in DB so the pre-submit claim in execute_product_video_render_job will fail!
    video_trace_state.claim_owner_acceptance_token(auth, db_path=isolate_test_db)

    req = VideoGenerationRequest(
        job_id="888",
        prompt="Test mountain sunset",
        required_capability="text_to_video",
        product_type="video_ai_prompt",
        metadata={
            "product_video": True,
            "owner_acceptance_auth": auth,
            "user_id": 12345,
            "job_id": 888,
            "product_type": "video_ai_prompt",
            "provider": "shopaikey_video",
            "tier": "veo31_fast_8",
            "runtime_sha": _current_runtime(),
            "estimated_provider_cost": 0.70,
            "estimated_provider_cost_unit": "USD",
        },
    )

    res = video_provider_router.run_provider_generation(req, output_dir=str(tmp_path))
    assert res["ok"] is False
    assert res["provider_submit_called"] is False
    assert res["provider_attempted"] is False
    assert res["external_provider_spend_prevented"] is True
    assert res["paid_submit_allowed"] is False
    assert res["blocker"] == "owner_acceptance_already_consumed"
    assert shopai_mock.submit_calls == 0, "ZERO provider submit calls must be made if claim fails"
