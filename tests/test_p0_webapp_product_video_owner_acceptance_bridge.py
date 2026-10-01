"""Test suite for Web Product Video Worker Owner Acceptance Bridge.

Task: WEBAPP_PRODUCT_VIDEO_WORKER_OWNER_ACCEPTANCE_BRIDGE_REMEDIATION_R1
Tracker: Issue #605
Defect: DEFECT-PV-001

Phase F Requirements:
1. Ordinary fail-closed: without owner acceptance auth, ordinary Web Product Video jobs fail-closed at router gate.
2. Customer payload owner auth forgery ignored: payload.owner_acceptance_auth is ignored and treated as ordinary job.
3. Top-level envelope owner auth forgery ignored: job.owner_acceptance_auth is ignored and treated as ordinary job.
4. Customer public_user_confirmed forgery ignored: cannot self-confirm via payload or job dict.
5. Valid Owner acceptance authorization binding: correctly validates job, user, project, provider, capability, tier, runtime SHA, spend.
6. Wrong job_id rejected (owner_acceptance_job_mismatch).
7. Wrong user_id / account_id rejected (owner_acceptance_user_mismatch).
8. Wrong product_type rejected (owner_acceptance_product_mismatch).
9. Wrong provider rejected (owner_acceptance_provider_mismatch).
10. Wrong capability rejected (owner_acceptance_capability_mismatch).
11. Wrong tier / cross-tier reuse rejected (owner_acceptance_tier_mismatch).
12. Wrong / stale runtime SHA rejected (owner_acceptance_runtime_sha_mismatch).
13. Unresolvable runtime SHA rejected (owner_acceptance_runtime_sha_unresolvable).
14. Spend limit exceeded rejected (owner_acceptance_spend_limit_exceeded).
15. Currency unit mismatch rejected (owner_acceptance_spend_unit_mismatch).
16. Expired authorization rejected (owner_acceptance_expired).
17. Consumed authorization rejected (owner_acceptance_already_consumed).
18. Global spend freeze preserved: PROVIDER_SPEND_FREEZE=1 in env remains active for ordinary jobs.
19. Scoped bypass allows submit gate pass without real provider network call.
20. Zero wallet mutations, admin_no_charge=True, and no_wallet_charge=True maintained.
"""

from __future__ import annotations

import copy
import os
import time
from typing import Any, Mapping
from unittest.mock import MagicMock

import pytest

from services import video_provider_router
from services.remote_worker_api import resolve_runtime_sha
from services.web_product_video_worker_consumer import (
    BOT_CANONICAL_PRODUCT_KEY,
    DEFAULT_REQUIRED_CAPABILITY,
    ConsumerExecutionOutcome,
    InvalidJobEnvelopeError,
    PreparedExecutionOutcome,
    WebProductVideoDispatcherClient,
    derive_canonical_tier_route,
    execute_claimed_web_product_video_job,
    map_web_job_to_bot_runtime,
    prepare_and_gate_execution,
)
from services.web_product_video_worker_daemon import WebProductVideoWorkerDaemon


@pytest.fixture(autouse=True)
def isolate_test_db(tmp_path, monkeypatch):
    """Ensure every test runs against a clean SQLite test database."""
    test_db = str(tmp_path / "bridge_test_isolated.db")
    monkeypatch.setenv("DB_PATH", test_db)
    monkeypatch.setenv("SQLITE_DB_PATH", test_db)
    monkeypatch.setenv("WEB_PRODUCT_VIDEO_WORKER_ENABLED", "true")
    monkeypatch.setenv("PROVIDER_SPEND_FREEZE", "1")
    return test_db


def _current_runtime() -> str:
    return resolve_runtime_sha() or "8dc3cdef83dbb4d19a45f2b4e079dc3ac8adbc71"


def _make_web_job(
    *,
    job_id: str = "web_pv_job_test_001",
    request_id: str = "req_test_001",
    account_id: str = "7126457028",
    project_id: str = "proj_test_001",
    prompt: str = "A cinematic product advertisement for premium green tea",
    quality_tier: str = "standard",
    duration: float = 5.0,
    aspect_ratio: str = "9:16",
    extra_payload: dict[str, Any] | None = None,
    extra_job: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "prompt": prompt,
        "quality_tier": quality_tier,
        "duration": duration,
        "aspect_ratio": aspect_ratio,
    }
    if extra_payload:
        payload.update(extra_payload)

    job: dict[str, Any] = {
        "job_id": job_id,
        "request_id": request_id,
        "product_key": BOT_CANONICAL_PRODUCT_KEY,
        "account_id": account_id,
        "project_id": project_id,
        "status": "processing",
        "attempts": 1,
        "worker_id": "test-worker",
        "payload": payload,
    }
    if extra_job:
        job.update(extra_job)
    return job


def _make_valid_owner_auth(
    *,
    job_id: str = "web_pv_job_test_001",
    user_id: str = "7126457028",
    project_id: str = "proj_test_001",
    product_type: str = "video_ai_prompt",
    provider: str = "shopaikey_video",
    capability: str = "text_to_video",
    tier: str = "200",
    runtime_sha: str | None = None,
    max_provider_spend: float = 1.00,
    max_provider_spend_unit: str = "USD",
    nonce: str = "nonce_bridge_test_001",
    consumed: bool = False,
    expires_at: float | None = None,
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
        "consumed": consumed,
        "expires_at": (time.time() + 3600) if expires_at is None else expires_at,
    }


# ===========================================================================
# 1. ORDINARY FAIL-CLOSED & CLIENT FORGERY PREVENTION
# ===========================================================================

def test_01_ordinary_web_product_video_job_fail_closed(monkeypatch):
    """Ordinary Web Product Video job without owner auth must fail-closed at router gate."""
    monkeypatch.setenv("PROVIDER_SPEND_FREEZE", "1")
    job = _make_web_job()
    outcome = prepare_and_gate_execution(job)

    assert outcome.ok is True
    assert outcome.generation_request is not None
    assert outcome.generation_request.metadata.get("source") == "web_dispatcher"
    assert outcome.generation_request.metadata.get("owner_authorized") is not True

    # When fed to router policy, provider submit is strictly forbidden
    policy = video_provider_router.product_video_provider_submit_source_policy(
        outcome.generation_request.metadata,
        public_submit_enabled=True,
    )
    assert policy.get("provider_submit_allowed") is False
    assert policy.get("provider_submit_block_reason") == "submit_source_not_public_final_confirm"


def test_02_customer_payload_owner_auth_forgery_ignored():
    """Customer putting owner_acceptance_auth in payload is completely ignored."""
    job = _make_web_job(
        extra_payload={
            "owner_acceptance_auth": {
                "owner_authorized": True,
                "acceptance_type": video_provider_router.OWNER_AUTHORIZED_LIVE_ACCEPTANCE,
            }
        }
    )
    gen_request = map_web_job_to_bot_runtime(job)
    assert gen_request.metadata.get("owner_authorized") is not True
    assert gen_request.metadata.get("source") == "web_dispatcher"
    assert "owner_acceptance_auth" not in gen_request.metadata


def test_03_customer_top_level_owner_auth_forgery_ignored():
    """Top-level job dict carrying owner_acceptance_auth is completely ignored."""
    job = _make_web_job(
        extra_job={
            "owner_acceptance_auth": {
                "owner_authorized": True,
                "acceptance_type": video_provider_router.OWNER_AUTHORIZED_LIVE_ACCEPTANCE,
            }
        }
    )
    gen_request = map_web_job_to_bot_runtime(job)
    assert gen_request.metadata.get("owner_authorized") is not True
    assert gen_request.metadata.get("source") == "web_dispatcher"


def test_04_customer_public_user_confirmed_forgery_ignored():
    """Customer putting public_user_confirmed=True is ignored."""
    job = _make_web_job(extra_payload={"public_user_confirmed": True})
    gen_request = map_web_job_to_bot_runtime(job)
    assert gen_request.metadata.get("public_user_confirmed") is not True


# ===========================================================================
# 2. VALID SERVER-SIDE OWNER ACCEPTANCE AUTHORIZATION BINDING
# ===========================================================================

def test_05_valid_owner_acceptance_auth_binds_and_verifies():
    """Valid server-side owner_acceptance_auth successfully validates and injects metadata."""
    job = _make_web_job()
    auth = _make_valid_owner_auth()
    gen_request = map_web_job_to_bot_runtime(
        job,
        owner_acceptance_auth=auth,
        acceptance_context={"acceptance_bypass_scope": "probation_liveness_only"},
    )

    assert gen_request.metadata.get("owner_authorized") is True
    assert gen_request.metadata.get("acceptance_lane_active") is True
    assert gen_request.metadata.get("source") == video_provider_router.OWNER_AUTHORIZED_LIVE_ACCEPTANCE
    assert gen_request.metadata.get("submit_source") == video_provider_router.OWNER_AUTHORIZED_LIVE_ACCEPTANCE
    assert gen_request.metadata.get("pinned_provider") == "shopaikey_video"
    assert gen_request.metadata.get("user_id") == "7126457028"
    assert gen_request.metadata.get("tier") == "200"
    assert gen_request.metadata.get("acceptance_bypass_scope") == "probation_liveness_only"


# ===========================================================================
# 3. IDENTITY & BOUND REJECTION TESTS
# ===========================================================================

def test_06_wrong_job_id_blocked():
    """Authorization bound to job A cannot be used for job B."""
    job = _make_web_job(job_id="job_real_456")
    auth = _make_valid_owner_auth(job_id="job_authorized_123")
    with pytest.raises(InvalidJobEnvelopeError, match="owner_acceptance_job_mismatch"):
        map_web_job_to_bot_runtime(job, owner_acceptance_auth=auth)


def test_07_wrong_user_id_blocked():
    """Authorization bound to user A cannot be used for user B."""
    job = _make_web_job(account_id="9999999999")
    auth = _make_valid_owner_auth(user_id="7126457028")
    with pytest.raises(InvalidJobEnvelopeError, match="owner_acceptance_user_mismatch"):
        map_web_job_to_bot_runtime(job, owner_acceptance_auth=auth)


def test_08_wrong_product_type_blocked():
    """Authorization bound to video_ai_prompt cannot authorize another product."""
    auth = _make_valid_owner_auth(product_type="video_dubbing_unauthorized")
    valid, blocker, _ = video_provider_router.validate_owner_acceptance_authorization(auth)
    assert valid is False
    assert blocker == "owner_acceptance_product_mismatch"


def test_09_wrong_provider_blocked():
    """Authorization bound to shopaikey_video cannot be used for unpinned provider."""
    job = _make_web_job()
    auth = _make_valid_owner_auth(provider="unknown_provider_video")
    with pytest.raises(InvalidJobEnvelopeError, match="owner_acceptance_provider_mismatch"):
        map_web_job_to_bot_runtime(job, owner_acceptance_auth=auth)


def test_10_wrong_capability_blocked():
    """Authorization bound to text_to_video cannot authorize image_to_video."""
    job = _make_web_job()
    auth = _make_valid_owner_auth(capability="image_to_video")
    with pytest.raises(InvalidJobEnvelopeError, match="owner_acceptance_capability_mismatch"):
        map_web_job_to_bot_runtime(job, owner_acceptance_auth=auth)


def test_11_wrong_tier_cross_tier_reuse_blocked():
    """Authorization for Tier 400 cannot be reused for Tier 200."""
    job = _make_web_job(quality_tier="standard")  # resolves to Tier 200
    auth = _make_valid_owner_auth(tier="400")
    with pytest.raises(InvalidJobEnvelopeError, match="owner_acceptance_tier_mismatch"):
        map_web_job_to_bot_runtime(job, owner_acceptance_auth=auth)


def test_12_wrong_runtime_sha_blocked():
    """Authorization carrying stale or mismatched SHA is rejected."""
    job = _make_web_job()
    auth = _make_valid_owner_auth(runtime_sha="deadbeef00000000000000000000000000000000")
    with pytest.raises(InvalidJobEnvelopeError, match="owner_acceptance_runtime_sha_mismatch"):
        map_web_job_to_bot_runtime(job, owner_acceptance_auth=auth)


def test_13_unresolvable_runtime_sha_blocked(monkeypatch):
    """When runtime SHA cannot be resolved from git or environ, fail-closed."""
    monkeypatch.setattr("services.remote_worker_api.resolve_runtime_sha", lambda environ=None, cwd=None: "")
    job = _make_web_job()
    auth = _make_valid_owner_auth(runtime_sha="some_valid_looking_sha")
    with pytest.raises(InvalidJobEnvelopeError, match="owner_acceptance_runtime_sha_unresolvable"):
        map_web_job_to_bot_runtime(job, owner_acceptance_auth=auth, environ={})


# ===========================================================================
# 4. SPEND CEILING & TIMING SAFETY
# ===========================================================================

def test_14_spend_limit_exceeded_blocked():
    """Cost exceeding max_provider_spend ceiling is rejected."""
    job = _make_web_job()
    # Tier 200 estimated cost is ~0.40 USD; auth with 0.10 USD ceiling must fail
    auth = _make_valid_owner_auth(max_provider_spend=0.10)
    with pytest.raises(InvalidJobEnvelopeError, match="owner_acceptance_spend_limit_exceeded"):
        map_web_job_to_bot_runtime(job, owner_acceptance_auth=auth)


def test_15_spend_currency_mismatch_blocked():
    """Currency unit comparison must match USD; VND/Xu rejected."""
    job = _make_web_job()
    auth = _make_valid_owner_auth(max_provider_spend=500.0, max_provider_spend_unit="VND")
    with pytest.raises(InvalidJobEnvelopeError, match="owner_acceptance_spend_unit_mismatch"):
        map_web_job_to_bot_runtime(job, owner_acceptance_auth=auth)


def test_16_expired_authorization_blocked():
    """Expired authorization rejected."""
    job = _make_web_job()
    auth = _make_valid_owner_auth(expires_at=time.time() - 300)
    with pytest.raises(InvalidJobEnvelopeError, match="owner_acceptance_expired"):
        map_web_job_to_bot_runtime(job, owner_acceptance_auth=auth)


def test_17_consumed_authorization_blocked():
    """Consumed authorization rejected."""
    job = _make_web_job()
    auth = _make_valid_owner_auth(consumed=True)
    with pytest.raises(InvalidJobEnvelopeError, match="owner_acceptance_already_consumed"):
        map_web_job_to_bot_runtime(job, owner_acceptance_auth=auth)


# ===========================================================================
# 5. GLOBAL SPEND FREEZE & SCOPED BYPASS INTEGRATION
# ===========================================================================

def test_18_global_spend_freeze_remains_active(monkeypatch):
    """Global PROVIDER_SPEND_FREEZE=1 in env remains strictly active for non-authorized jobs."""
    monkeypatch.setenv("PROVIDER_SPEND_FREEZE", "1")
    job = _make_web_job()

    # Without owner auth: ordinary web job source is blocked from submit
    outcome = prepare_and_gate_execution(job)
    freeze_truth = video_provider_router.product_video_freeze_truth(
        str(outcome.generation_request.metadata.get("source") or ""),
        {"public_submit_enabled": True},
        environ=os.environ,
    )
    assert freeze_truth.get("blocker_code") == "hidden_submit_source_blocked"

    # Even with owner_authorized_live_acceptance source, if auth is missing/invalid, spend freeze blocks submit
    unauth_freeze_truth = video_provider_router.product_video_freeze_truth(
        video_provider_router.OWNER_AUTHORIZED_LIVE_ACCEPTANCE,
        {"public_submit_enabled": True, "owner_acceptance_auth_valid": False},
        environ=os.environ,
    )
    assert unauth_freeze_truth.get("public_live_allowed") is False
    assert unauth_freeze_truth.get("blocker_code") == "provider_spend_freeze_active"


def test_19_scoped_bypass_allows_submit_without_real_network(monkeypatch):
    """Scoped bypass allows submit boundary in router while preventing real network calls."""
    monkeypatch.setenv("PROVIDER_SPEND_FREEZE", "1")
    job = _make_web_job()
    auth = _make_valid_owner_auth()

    executed_env = {}

    def mock_executor(request, *, output_dir, environ):
        nonlocal executed_env
        executed_env = dict(environ)
        # Verify that inside the executor, the scoped bypass was applied
        assert environ.get("PROVIDER_SPEND_FREEZE") == "0"
        assert environ.get("ACCEPTANCE_BYPASS_SCOPE") == "probation_liveness_only"
        # Return mock outcome without making any HTTP request
        return {
            "ok": True,
            "result_url": "https://example.com/mock_video.mp4",
            "output_path": "/tmp/mock.mp4",
            "bytes": 500000,
            "duration": 5.0,
            "provider_task_id": "mock_task_001",
            "provider_submit_called": True,
        }

    mock_client = MagicMock()
    mock_client.claim.return_value = MagicMock(idle=False, job=job)
    mock_client.heartbeat.return_value = True

    outcome = execute_claimed_web_product_video_job(
        job=job,
        client=mock_client,
        executor_fn=mock_executor,
        owner_acceptance_auth=auth,
        acceptance_context={"acceptance_bypass_scope": "probation_liveness_only"},
        acceptance_bypass_scope="probation_liveness_only",
    )

    assert outcome.ok is True
    assert outcome.status == "COMPLETED"
    assert outcome.provider_calls == 1
    assert outcome.paid_provider_calls == 1
    assert outcome.video_renders == 1
    assert outcome.wallet_mutations == 0
    assert executed_env.get("PROVIDER_SPEND_FREEZE") == "0"
    # But global environment was never modified!
    assert os.getenv("PROVIDER_SPEND_FREEZE") == "1"


def test_20_zero_wallet_mutations_maintained():
    """All executions strictly maintain admin_no_charge=True and zero wallet mutations."""
    job = _make_web_job()
    auth = _make_valid_owner_auth()
    gen_request = map_web_job_to_bot_runtime(job, owner_acceptance_auth=auth)

    assert gen_request.metadata.get("admin_no_charge") is True
    assert gen_request.metadata.get("no_wallet_charge") is True

    outcome = prepare_and_gate_execution(job, owner_acceptance_auth=auth)
    assert outcome.wallet_mutations == 0
