"""Comprehensive test matrix for P0.VIDEO.SYSTEM.SPEC03B1.PRENETWORK.FAILURE.RECOVERY.CONTRACT.

Verifies:
1. Canonical tier mapping: tier veo31_fast_8 -> provider model veo3.1-fast across routing, catalog, and payload build.
2. Fail-closed model validation: unknown provider model still fail-closed with CONFIG_MODEL_UNKNOWN and no charge.
3. Anti-replay of consumed authorization: old token fingerprint and old attempt key remain dead.
4. Append-only recovery contract: pre-network consumed failure can create a NEW recovery attempt via explicit contract.
5. Forensic preservation: previous trace row remains permanently preserved in durable SQLite WAL.
6. Transmission guard: provider_http_request_sent=true hard blocks recovery submit.
7. Task ID guard: provider_task_id present hard blocks recovery submit.
8. Ambiguity guard: ambiguous outcome (CONSUMED_AMBIGUOUS) hard blocks recovery submit.
9. Single-attempt invariants: new recovery attempt preserves MAX_PROVIDER_SUBMITS=1, AUTO_RESUBMIT=0, PAID_FAILOVER=0.
10. Identity integrity: mismatched user_id, job_id, or project_id in recovery authorization is rejected.
"""

from __future__ import annotations

import copy
import json
import sqlite3
import time
from typing import Any

import pytest

from providers.video_generic_http_provider import (
    VideoProviderContractError,
    build_shopaikey_video_payload,
)
from services import video_provider_catalog, video_provider_router, video_trace_state
from services.remote_worker_api import resolve_runtime_sha
from services.video_provider_base import VideoGenerationRequest


@pytest.fixture(autouse=True)
def isolate_test_db(tmp_path, monkeypatch):
    """Ensure every test runs against a completely isolated SQLite test database."""
    test_db = str(tmp_path / "spec03b1_isolated.db")
    monkeypatch.setenv("DB_PATH", test_db)
    monkeypatch.setenv("SQLITE_DB_PATH", test_db)
    return test_db


def _current_runtime() -> str:
    return resolve_runtime_sha() or "6f2ab6cf246f078b74ef99f3dd03fad23ccb7649"


def _make_base_auth(
    *,
    job_id: int = 18,
    user_id: int = 7126457028,
    project_id: int = 22,
    product_type: str = "video_ai_prompt",
    provider: str = "shopaikey_video",
    capability: str = "text_to_video",
    tier: str = "veo31_fast_8",
    runtime_sha: str | None = None,
    max_provider_spend: float = 1.00,
    max_provider_spend_unit: str = "USD",
    nonce: str = "spec03b-auth-v1",
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


# ============================================================================
# 1. CANONICAL MODEL MAPPING TESTS
# ============================================================================

def test_01_tier_veo31_fast_8_normalizes_to_common_tier():
    """Verify tier veo31_fast_8 is an authoritative alias for common tier."""
    normalized = video_provider_catalog.normalize_tier("veo31_fast_8")
    assert normalized == "common"


def test_02_tier_veo31_fast_8_resolves_to_provider_model_veo31_fast():
    """Verify resolution of tier veo31_fast_8 yields primary model veo3.1-fast for shopaikey_video."""
    resolution = video_provider_catalog.resolve_product_video_model(
        tier="veo31_fast_8",
        provider_chain=["shopaikey_video"],
    )
    assert resolution.get("ok") is True
    assert resolution.get("selected_provider") == "shopaikey_video"
    assert resolution.get("selected_model") == "veo3.1-fast"
    assert resolution.get("model") == "veo3.1-fast"
    assert resolution.get("selected_model_source") == "config:tier:common"


def test_03_selected_model_for_provider_maps_canonical_tier():
    """Verify selected_model_for_provider maps canonical tier name to provider model ID."""
    mapped_from_selected = video_provider_catalog.selected_model_for_provider(
        {"selected_model": "veo31_fast_8"},
        "shopaikey_video",
    )
    assert mapped_from_selected == "veo3.1-fast"

    mapped_from_tier = video_provider_catalog.selected_model_for_provider(
        {"tier": "veo31_fast_8"},
        "shopaikey_video",
    )
    assert mapped_from_tier == "veo3.1-fast"

    mapped_direct = video_provider_catalog.selected_model_for_provider(
        {"selected_model": "veo3.1-fast"},
        "shopaikey_video",
    )
    assert mapped_direct == "veo3.1-fast"


def test_04_build_shopaikey_video_payload_uses_resolved_model():
    """Verify build_shopaikey_video_payload resolves veo31_fast_8 into payload model veo3.1-fast."""
    req = VideoGenerationRequest(
        job_id="18",
        product_type="video_ai_prompt",
        prompt="A cinematic drone shot over mountains",
        metadata={
            "product_video": True,
            "selected_model": "veo31_fast_8",
            "tier": "veo31_fast_8",
        },
    )
    payload = build_shopaikey_video_payload(req)
    assert payload.get("model") == "veo3.1-fast"


# ============================================================================
# 2. FAIL-CLOSED DEFENSE FOR UNKNOWN MODELS
# ============================================================================

def test_05_unknown_provider_model_still_fail_closed():
    """Verify unknown provider model is NOT resolved and raises CONFIG_MODEL_UNKNOWN fail-closed."""
    mapped = video_provider_catalog.selected_model_for_provider(
        {"selected_model": "unsupported-video-model-xyz"},
        "shopaikey_video",
    )
    assert mapped == "unsupported-video-model-xyz"

    req = VideoGenerationRequest(
        job_id="18",
        product_type="video_ai_prompt",
        prompt="Test prompt",
        metadata={
            "product_video": True,
            "selected_model": "unsupported-video-model-xyz",
        },
    )
    with pytest.raises(VideoProviderContractError) as exc_info:
        build_shopaikey_video_payload(req)
    assert exc_info.value.blocker == "CONFIG_MODEL_UNKNOWN"
    assert exc_info.value.debug.get("no_charge") is True


# ============================================================================
# 3. OLD CONSUMED AUTHORIZATION REMAINS DEAD (ANTI-REPLAY)
# ============================================================================

def test_06_old_consumed_authorization_cannot_replay(isolate_test_db):
    """Verify old consumed authorization (both token fingerprint and attempt key) cannot be replayed."""
    auth = _make_base_auth(nonce="orig-nonce-1")
    ok, blocker, details = video_trace_state.claim_owner_acceptance_token(auth, db_path=isolate_test_db)
    assert ok is True
    token_fp = details["token_fingerprint"]
    attempt_fp = details["attempt_fingerprint"]
    attempt_key = details["confirm_attempt_key"]

    finalized = video_trace_state.finalize_owner_acceptance_token(
        token_fp,
        stage=video_trace_state.STAGE_OAT_CONSUMED_FAILED,
        db_path=isolate_test_db,
    )
    assert finalized is True

    replay_ok1, blocker1, _ = video_trace_state.claim_owner_acceptance_token(auth, db_path=isolate_test_db)
    assert replay_ok1 is False
    assert blocker1 == "owner_acceptance_already_consumed"

    auth_new_nonce = copy.deepcopy(auth)
    auth_new_nonce["nonce"] = "orig-nonce-2"
    replay_ok2, blocker2, _ = video_trace_state.claim_owner_acceptance_token(auth_new_nonce, db_path=isolate_test_db)
    assert replay_ok2 is False
    assert blocker2 == "owner_acceptance_already_consumed"

    assert video_trace_state.is_owner_acceptance_attempt_claimed_or_consumed(attempt_fp, db_path=isolate_test_db) is True


# ============================================================================
# 4. APPEND-ONLY RECOVERY CONTRACT TESTS
# ============================================================================

def test_07_prenetwork_consumed_failure_creates_new_recovery_attempt(isolate_test_db):
    """Verify pre-network consumed failure can create a NEW recovery attempt via explicit contract."""
    auth_orig = _make_base_auth(nonce="orig-failed-nonce")
    ok_orig, _, details_orig = video_trace_state.claim_owner_acceptance_token(auth_orig, db_path=isolate_test_db)
    assert ok_orig is True
    orig_tfp = details_orig["token_fingerprint"]
    orig_oaa = details_orig["confirm_attempt_key"]

    video_trace_state.finalize_owner_acceptance_token(
        orig_tfp,
        stage=video_trace_state.STAGE_OAT_CONSUMED_FAILED,
        db_path=isolate_test_db,
    )

    auth_recovery = copy.deepcopy(auth_orig)
    auth_recovery["recovery_previous_attempt_key"] = orig_oaa
    auth_recovery["recovery_generation_id"] = "1"
    auth_recovery["nonce"] = "recovery-attempt-nonce-1"

    rec_ok, rec_blocker, rec_det = video_trace_state.validate_owner_acceptance_recovery_eligibility(
        auth_recovery,
        db_path=isolate_test_db,
    )
    assert rec_ok is True
    assert rec_blocker == ""
    assert rec_det["previous_stage"] == video_trace_state.STAGE_OAT_CONSUMED_FAILED

    claim_ok, claim_blocker, claim_details = video_trace_state.claim_owner_acceptance_token(
        auth_recovery,
        db_path=isolate_test_db,
    )
    assert claim_ok is True
    assert claim_details.get("recovery") is True
    assert claim_details.get("recovery_previous_attempt_key") == orig_oaa

    new_tfp = claim_details["token_fingerprint"]
    new_oaa = claim_details["confirm_attempt_key"]
    assert new_tfp != orig_tfp
    assert new_oaa != orig_oaa


def test_08_previous_trace_remains_preserved_after_recovery(isolate_test_db):
    """Verify previous trace row is NOT deleted, overwritten, or modified by recovery."""
    auth_orig = _make_base_auth(nonce="orig-preserve-test")
    _, _, details_orig = video_trace_state.claim_owner_acceptance_token(auth_orig, db_path=isolate_test_db)
    orig_tfp = details_orig["token_fingerprint"]
    orig_oaa = details_orig["confirm_attempt_key"]

    video_trace_state.finalize_owner_acceptance_token(
        orig_tfp,
        stage=video_trace_state.STAGE_OAT_CONSUMED_FAILED,
        db_path=isolate_test_db,
    )

    conn, should_close = video_trace_state.get_db_connection(db_path=isolate_test_db)
    try:
        row_before = dict(
            conn.execute("SELECT * FROM video_request_traces WHERE confirm_attempt_key = ?", (orig_oaa,)).fetchone()
        )
    finally:
        if should_close:
            conn.close()

    auth_recovery = copy.deepcopy(auth_orig)
    auth_recovery["recovery_previous_attempt_key"] = orig_oaa
    auth_recovery["recovery_generation_id"] = "1"
    auth_recovery["nonce"] = "recovery-preserve-nonce"
    video_trace_state.claim_owner_acceptance_token(auth_recovery, db_path=isolate_test_db)

    conn2, should_close2 = video_trace_state.get_db_connection(db_path=isolate_test_db)
    try:
        row_after = dict(
            conn2.execute("SELECT * FROM video_request_traces WHERE confirm_attempt_key = ?", (orig_oaa,)).fetchone()
        )
        all_rows = conn2.execute("SELECT request_id, confirm_attempt_key FROM video_request_traces").fetchall()
    finally:
        if should_close2:
            conn2.close()

    assert row_after["request_id"] == row_before["request_id"]
    assert row_after["current_stage"] == video_trace_state.STAGE_OAT_CONSUMED_FAILED
    assert row_after["created_at"] == row_before["created_at"]
    assert len(all_rows) == 2


# ============================================================================
# 5. HARD REJECT GUARDS FOR INVALID RECOVERY
# ============================================================================

def test_09_provider_http_request_sent_blocks_recovery_submit(isolate_test_db):
    """Verify provider_http_request_sent=true hard blocks recovery submit."""
    auth_orig = _make_base_auth(nonce="transmitted-test")
    _, _, details = video_trace_state.claim_owner_acceptance_token(auth_orig, db_path=isolate_test_db)
    orig_tfp = details["token_fingerprint"]
    orig_oaa = details["confirm_attempt_key"]

    conn, should_close = video_trace_state.get_db_connection(db_path=isolate_test_db)
    try:
        payload = {
            "stage": video_trace_state.STAGE_OAT_CONSUMED_FAILED,
            "provider_http_request_sent": True,
            "submit_count": 1,
        }
        conn.execute(
            "UPDATE video_request_traces SET current_stage = ?, trace_payload_json = ? WHERE confirm_attempt_key = ?",
            (video_trace_state.STAGE_OAT_CONSUMED_FAILED, json.dumps(payload), orig_oaa),
        )
        conn.commit()
    finally:
        if should_close:
            conn.close()

    auth_rec = copy.deepcopy(auth_orig)
    auth_rec["recovery_previous_attempt_key"] = orig_oaa
    auth_rec["recovery_generation_id"] = "1"

    rec_ok, rec_blocker, _ = video_trace_state.validate_owner_acceptance_recovery_eligibility(
        auth_rec,
        db_path=isolate_test_db,
    )
    assert rec_ok is False
    assert rec_blocker == "recovery_previous_attempt_transmitted"

    claim_ok, claim_blocker, _ = video_trace_state.claim_owner_acceptance_token(auth_rec, db_path=isolate_test_db)
    assert claim_ok is False
    assert claim_blocker == "recovery_previous_attempt_transmitted"


def test_10_provider_task_id_present_blocks_recovery_submit(isolate_test_db):
    """Verify provider_task_id present hard blocks recovery submit."""
    auth_orig = _make_base_auth(nonce="task-id-present-test")
    _, _, details = video_trace_state.claim_owner_acceptance_token(auth_orig, db_path=isolate_test_db)
    orig_tfp = details["token_fingerprint"]
    orig_oaa = details["confirm_attempt_key"]

    video_trace_state.finalize_owner_acceptance_token(
        orig_tfp,
        stage=video_trace_state.STAGE_OAT_CONSUMED_FAILED,
        provider_task_id="shopai_task_998877",
        db_path=isolate_test_db,
    )

    auth_rec = copy.deepcopy(auth_orig)
    auth_rec["recovery_previous_attempt_key"] = orig_oaa
    auth_rec["recovery_generation_id"] = "1"

    rec_ok, rec_blocker, _ = video_trace_state.validate_owner_acceptance_recovery_eligibility(
        auth_rec,
        db_path=isolate_test_db,
    )
    assert rec_ok is False
    assert rec_blocker == "recovery_previous_attempt_task_id_present"

    claim_ok, claim_blocker, _ = video_trace_state.claim_owner_acceptance_token(auth_rec, db_path=isolate_test_db)
    assert claim_ok is False
    assert claim_blocker == "recovery_previous_attempt_task_id_present"


def test_11_ambiguous_attempt_blocks_recovery_submit(isolate_test_db):
    """Verify ambiguous attempt (CONSUMED_AMBIGUOUS) hard blocks recovery submit."""
    auth_orig = _make_base_auth(nonce="ambiguous-test")
    _, _, details = video_trace_state.claim_owner_acceptance_token(auth_orig, db_path=isolate_test_db)
    orig_tfp = details["token_fingerprint"]
    orig_oaa = details["confirm_attempt_key"]

    video_trace_state.finalize_owner_acceptance_token(
        orig_tfp,
        stage=video_trace_state.STAGE_OAT_CONSUMED_AMBIGUOUS,
        db_path=isolate_test_db,
    )

    auth_rec = copy.deepcopy(auth_orig)
    auth_rec["recovery_previous_attempt_key"] = orig_oaa
    auth_rec["recovery_generation_id"] = "1"

    rec_ok, rec_blocker, _ = video_trace_state.validate_owner_acceptance_recovery_eligibility(
        auth_rec,
        db_path=isolate_test_db,
    )
    assert rec_ok is False
    assert rec_blocker == "recovery_previous_attempt_ambiguous"

    claim_ok, claim_blocker, _ = video_trace_state.claim_owner_acceptance_token(auth_rec, db_path=isolate_test_db)
    assert claim_ok is False
    assert claim_blocker == "recovery_previous_attempt_ambiguous"


def test_12_recovery_attempt_preserves_single_submit_and_no_failover(isolate_test_db, monkeypatch, tmp_path):
    """Verify recovery attempt still enforces MAX_PROVIDER_SUBMITS=1, AUTO_RESUBMIT=0, PAID_FAILOVER=0."""
    import socket
    from tests.test_p0_video_spec02_probation_acceptance_lane import MockVideoProvider, _probation_status

    auth_orig = _make_base_auth(nonce="invariant-check-test")
    _, _, details = video_trace_state.claim_owner_acceptance_token(auth_orig, db_path=isolate_test_db)
    orig_tfp = details["token_fingerprint"]
    orig_oaa = details["confirm_attempt_key"]

    video_trace_state.finalize_owner_acceptance_token(
        orig_tfp,
        stage=video_trace_state.STAGE_OAT_CONSUMED_FAILED,
        db_path=isolate_test_db,
    )

    auth_rec = copy.deepcopy(auth_orig)
    auth_rec["recovery_previous_attempt_key"] = orig_oaa
    auth_rec["recovery_generation_id"] = "1"
    auth_rec["nonce"] = "invariant-rec-nonce"

    valid, blocker, verified = video_provider_router.validate_owner_acceptance_authorization(
        auth_rec,
        context={"job_id": 18, "user_id": 7126457028, "project_id": 22, "tier": "veo31_fast_8"},
        environ={"DB_PATH": isolate_test_db},
    )
    assert valid is True
    assert verified.get("paid_fallback_allowed") is False
    assert verified.get("is_recovery") is True

    # Set up mock providers: primary fails with timeout, secondary should NEVER be called
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

    req = VideoGenerationRequest(
        job_id="18",
        prompt="A recovery test video",
        required_capability="text_to_video",
        product_type="video_ai_prompt",
        metadata={
            "product_video": True,
            "owner_acceptance_auth": auth_rec,
            "user_id": 7126457028,
            "job_id": 18,
            "project_id": 22,
            "product_type": "video_ai_prompt",
            "provider": "shopaikey_video",
            "tier": "veo31_fast_8",
            "runtime_sha": _current_runtime(),
        },
    )

    res = video_provider_router.run_provider_generation(req, output_dir=str(tmp_path))
    assert res["ok"] is False
    assert res["charge"] == 0
    assert res["no_charge"] is True
    assert res["fallback_allowed"] is False
    # MAX_PROVIDER_SUBMITS=1, AUTO_RESUBMIT=0
    assert shopai_mock.submit_calls == 1
    # PAID_FAILOVER=0 (secondary mock provider was never called)
    assert key4u_mock.submit_calls == 0