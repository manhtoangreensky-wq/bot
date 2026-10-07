"""B14N11 — R05A Owner Acceptance Native Authority Source Verification Test Suite.

TASK_ID=P0.PRODUCT_VIDEO_R16_10B14N11_R05A_OWNER_ACCEPTANCE_NATIVE_AUTHORITY_SOURCE_CORRECTION
TRACKER=manhtoangreensky-wq/bot#1155
BASE_SHA=76f0454fbab5e467f9ca71a0135b6fd05d8d70c4

Verifies all 18 minimum provider-free requirements:
01 exact R05A tuple passes WITHOUT escape flags
02 allow_other_product absent, allow_secondary_provider absent -> PASS
03 tier != 700 -> DENY
04 provider=shopaikey_video -> DENY
05 provider=key4u_video + model != kling-v3 -> DENY
06 capability != image_to_video -> DENY
07 engine_adapter mismatch -> DENY
08 context product mismatch -> DENY
09 context provider mismatch -> DENY
10 job binding mismatch -> DENY
11 project binding mismatch -> DENY
12 user binding mismatch -> DENY
13 consumed token replay -> DENY
14 consumed attempt fingerprint replay -> DENY
15 self_shot_cinematic_transform -> DENY
16 Storyboard/R06 -> DENY
17 existing video_ai_prompt valid cases -> PASS
18 video_ai_video_reference -> no regression
"""

from __future__ import annotations

import copy
import os
import time
from typing import Any
import pytest

from services import video_provider_router, video_trace_state
from services.remote_worker_api import resolve_runtime_sha


@pytest.fixture(autouse=True)
def isolate_test_db(tmp_path, monkeypatch):
    """Ensure every test runs against a clean, isolated SQLite test database."""
    test_db = str(tmp_path / "n11_owner_acceptance_isolated.db")
    monkeypatch.setenv("DB_PATH", test_db)
    monkeypatch.setenv("SQLITE_DB_PATH", test_db)
    return test_db


def _current_runtime() -> str:
    return resolve_runtime_sha() or "76f0454fbab5e467f9ca71a0135b6fd05d8d70c4"


def _make_r05a_auth(
    *,
    job_id: Any = 101,
    user_id: Any = 12345,
    project_id: Any = 501,
    product_type: Any = "self_shot_scene_change",
    provider: Any = "key4u_video",
    capability: Any = "image_to_video",
    tier: Any = 700,
    model: Any = "kling-v3",
    engine_adapter: Any = "controlled_keyframe_image_to_video",
    runtime_sha: str | None = None,
    max_provider_spend: float | None = 1.00,
    max_provider_spend_unit: str | None = "USD",
    nonce: str = "nonce-r05a-test",
    allow_other_product: bool | None = None,
    allow_secondary_provider: bool | None = None,
) -> dict[str, Any]:
    auth: dict[str, Any] = {
        "owner_authorized": True,
        "acceptance_type": video_provider_router.OWNER_AUTHORIZED_LIVE_ACCEPTANCE,
        "nonce": nonce,
        "consumed": False,
        "expires_at": time.time() + 3600,
    }
    if product_type is not None:
        auth["product_type"] = product_type
    if provider is not None:
        auth["provider"] = provider
    if capability is not None:
        auth["capability"] = capability
    if tier is not None:
        auth["tier"] = tier
        auth["quality_tier"] = tier
    if model is not None:
        auth["model"] = model
    if engine_adapter is not None:
        auth["engine_adapter"] = engine_adapter
    if job_id is not None:
        auth["job_id"] = job_id
    if user_id is not None:
        auth["user_id"] = user_id
    if project_id is not None:
        auth["project_id"] = project_id
    if runtime_sha is not None:
        auth["runtime_sha"] = runtime_sha
    elif runtime_sha is None and runtime_sha != "":
        auth["runtime_sha"] = _current_runtime()
    if max_provider_spend is not None:
        auth["max_provider_spend"] = max_provider_spend
    if max_provider_spend_unit is not None:
        auth["max_provider_spend_unit"] = max_provider_spend_unit
    if allow_other_product is not None:
        auth["allow_other_product"] = allow_other_product
    if allow_secondary_provider is not None:
        auth["allow_secondary_provider"] = allow_secondary_provider
    return auth


def _make_r05a_ctx(
    *,
    job_id: Any = 101,
    user_id: Any = 12345,
    account_id: Any = None,
    project_id: Any = 501,
    product_type: Any = "self_shot_scene_change",
    provider: Any = "key4u_video",
    capability: Any = "image_to_video",
    tier: Any = 700,
    model: Any = "kling-v3",
    engine_adapter: Any = "controlled_keyframe_image_to_video",
    runtime_sha: str | None = None,
    estimated_provider_cost: float | None = 0.50,
    estimated_provider_cost_unit: str | None = "USD",
) -> dict[str, Any]:
    ctx: dict[str, Any] = {}
    if job_id is not None:
        ctx["job_id"] = job_id
    if user_id is not None:
        ctx["user_id"] = user_id
    if account_id is not None:
        ctx["account_id"] = account_id
    if project_id is not None:
        ctx["project_id"] = project_id
    if product_type is not None:
        ctx["product_type"] = product_type
    if provider is not None:
        ctx["provider"] = provider
        ctx["selected_provider"] = provider
    if capability is not None:
        ctx["capability"] = capability
        ctx["required_capability"] = capability
    if tier is not None:
        ctx["tier"] = tier
        ctx["quality_tier"] = tier
    if model is not None:
        ctx["model"] = model
        ctx["selected_model"] = model
    if engine_adapter is not None:
        ctx["engine_adapter"] = engine_adapter
    if runtime_sha is not None:
        ctx["runtime_sha"] = runtime_sha
    elif runtime_sha is None and runtime_sha != "":
        ctx["runtime_sha"] = _current_runtime()
    if estimated_provider_cost is not None:
        ctx["estimated_provider_cost"] = estimated_provider_cost
    if estimated_provider_cost_unit is not None:
        ctx["estimated_provider_cost_unit"] = estimated_provider_cost_unit
    return ctx


def test_01_exact_r05a_tuple_passes_without_escape_flags():
    """01 exact R05A tuple passes WITHOUT escape flags."""
    auth = _make_r05a_auth()
    assert "allow_other_product" not in auth
    assert "allow_secondary_provider" not in auth

    ctx = _make_r05a_ctx()
    valid, reason, verified = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is True
    assert reason == ""
    assert verified.get("verified") is True
    assert verified.get("pinned_product") == "self_shot_scene_change"
    assert verified.get("pinned_provider") == "key4u_video"
    assert verified.get("pinned_tier") == "700"
    assert verified.get("model") == "kling-v3"
    assert verified.get("engine_adapter") == "controlled_keyframe_image_to_video"
    assert verified.get("required_capability") == "image_to_video"
    assert verified.get("provider_order") == ["key4u_video"]
    assert verified.get("effective_provider_chain") == ["key4u_video"]
    assert verified.get("automatic_fallback_allowed") is False
    assert verified.get("automatic_resubmit_allowed") is False
    assert verified.get("max_provider_submits") == 1


def test_02_allow_other_product_and_secondary_provider_absent_passes():
    """02 allow_other_product absent and allow_secondary_provider absent -> PASS."""
    auth = _make_r05a_auth()
    ctx = _make_r05a_ctx()
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is True
    assert reason == ""


def test_03_tier_not_700_denied():
    """03 tier != 700 -> DENY."""
    for bad_tier in [500, 600, 800, "500", "standard", "veo31_fast_8", "long", "kling_long_audio_15"]:
        auth = _make_r05a_auth(tier=bad_tier)
        ctx = _make_r05a_ctx(tier=bad_tier)
        valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
        assert valid is False, f"Bad tier {bad_tier} must be rejected"
        assert reason == "owner_acceptance_tier_mismatch"


def test_04_provider_shopaikey_video_denied():
    """04 provider=shopaikey_video -> DENY."""
    auth = _make_r05a_auth(provider="shopaikey_video")
    ctx = _make_r05a_ctx(provider="shopaikey_video")
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is False
    assert reason == "owner_acceptance_provider_mismatch"


def test_05_provider_key4u_model_not_kling_v3_denied():
    """05 provider=key4u_video + model != kling-v3 -> DENY."""
    for bad_model in ["kling-v2", "veo3.1-fast", "sora", "kling_v1"]:
        auth = _make_r05a_auth(model=bad_model)
        ctx = _make_r05a_ctx(model=bad_model)
        valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
        assert valid is False, f"Bad model {bad_model} must be rejected"
        assert reason == "owner_acceptance_model_mismatch"


def test_06_capability_not_image_to_video_denied():
    """06 capability != image_to_video -> DENY."""
    for bad_cap in ["text_to_video", "scene_video", "video_to_video"]:
        auth = _make_r05a_auth(capability=bad_cap)
        ctx = _make_r05a_ctx(capability=bad_cap)
        valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
        assert valid is False, f"Bad capability {bad_cap} must be rejected"
        assert reason == "owner_acceptance_capability_mismatch"


def test_07_engine_adapter_mismatch_denied():
    """07 engine_adapter mismatch -> DENY."""
    for bad_engine in ["text_to_video", "text_to_video_or_scene_engine", "script_scene_engine"]:
        auth = _make_r05a_auth(engine_adapter=bad_engine)
        ctx = _make_r05a_ctx(engine_adapter=bad_engine)
        valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
        assert valid is False, f"Bad engine adapter {bad_engine} must be rejected"
        assert reason == "owner_acceptance_engine_adapter_mismatch"


def test_08_context_product_mismatch_denied():
    """08 context product mismatch -> DENY."""
    auth = _make_r05a_auth(product_type="self_shot_scene_change")
    ctx = _make_r05a_ctx(product_type="video_ai_prompt")
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is False
    assert reason == "owner_acceptance_product_mismatch"


def test_09_context_provider_mismatch_denied():
    """09 context provider mismatch -> DENY."""
    auth = _make_r05a_auth(provider="key4u_video")
    ctx = _make_r05a_ctx(provider="shopaikey_video")
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is False
    assert reason == "owner_acceptance_provider_mismatch"


def test_10_job_binding_mismatch_denied():
    """10 job binding mismatch -> DENY."""
    auth = _make_r05a_auth(job_id=101)
    ctx = _make_r05a_ctx(job_id=999)
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is False
    assert reason == "owner_acceptance_job_mismatch"


def test_11_project_binding_mismatch_denied():
    """11 project binding mismatch -> DENY."""
    auth = _make_r05a_auth(project_id=501)
    ctx = _make_r05a_ctx(project_id=888)
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is False
    assert reason == "owner_acceptance_project_mismatch"


def test_12_user_binding_mismatch_denied():
    """12 user binding mismatch -> DENY."""
    auth = _make_r05a_auth(user_id=12345)
    ctx = _make_r05a_ctx(user_id=99999)
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is False
    assert reason == "owner_acceptance_user_mismatch"


def test_13_consumed_token_replay_denied(isolate_test_db):
    """13 consumed token replay -> DENY."""
    auth = _make_r05a_auth(nonce="nonce-consumed-test-13")
    ctx = _make_r05a_ctx()

    # Claim token in durable DB
    ok, blocker, details = video_trace_state.claim_owner_acceptance_token(auth, db_path=isolate_test_db)
    assert ok is True

    # Attempt to validate replay with reconstructed token
    reconstructed_auth = _make_r05a_auth(nonce="nonce-consumed-test-13")
    assert reconstructed_auth["consumed"] is False

    valid, reason, details = video_provider_router.validate_owner_acceptance_authorization(
        reconstructed_auth, context=ctx, db_path=isolate_test_db
    )
    assert valid is False
    assert reason == "owner_acceptance_already_consumed"


def test_14_consumed_attempt_fingerprint_replay_denied(isolate_test_db):
    """14 consumed attempt fingerprint replay -> DENY."""
    auth1 = _make_r05a_auth(nonce="nonce-first-attempt")
    ctx = _make_r05a_ctx()

    # Claim first attempt
    ok, blocker, details = video_trace_state.claim_owner_acceptance_token(auth1, db_path=isolate_test_db)
    assert ok is True

    # New nonce, same job attempt
    auth2 = _make_r05a_auth(nonce="nonce-second-attempt-replay")
    valid, reason, details = video_provider_router.validate_owner_acceptance_authorization(
        auth2, context=ctx, db_path=isolate_test_db
    )
    assert valid is False
    assert reason == "owner_acceptance_already_consumed"


def test_15_self_shot_cinematic_transform_denied():
    """15 self_shot_cinematic_transform -> DENY."""
    auth = _make_r05a_auth(product_type="self_shot_cinematic_transform")
    ctx = _make_r05a_ctx(product_type="self_shot_cinematic_transform")
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is False
    assert reason == "owner_acceptance_product_mismatch"


def test_16_storyboard_r06_denied():
    """16 Storyboard/R06 -> DENY."""
    for bad_product in ["storyboard_prompt", "storyboard", "multi_scene_film"]:
        auth = _make_r05a_auth(product_type=bad_product)
        ctx = _make_r05a_ctx(product_type=bad_product)
        valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
        assert valid is False, f"Storyboard product {bad_product} must be rejected"
        assert reason == "owner_acceptance_product_mismatch"


def test_17_existing_video_ai_prompt_valid_cases():
    """17 existing video_ai_prompt valid cases -> PASS."""
    auth = {
        "owner_authorized": True,
        "acceptance_type": video_provider_router.OWNER_AUTHORIZED_LIVE_ACCEPTANCE,
        "product_type": "video_ai_prompt",
        "provider": "shopaikey_video",
        "capability": "text_to_video",
        "tier": "veo31_fast_8",
        "job_id": 101,
        "user_id": 12345,
        "project_id": 501,
        "runtime_sha": _current_runtime(),
        "max_provider_spend": 1.00,
        "max_provider_spend_unit": "USD",
        "nonce": "nonce-v-ai-prompt-valid",
        "consumed": False,
        "expires_at": time.time() + 3600,
    }
    ctx = {
        "job_id": 101,
        "user_id": 12345,
        "project_id": 501,
        "product_type": "video_ai_prompt",
        "provider": "shopaikey_video",
        "selected_provider": "shopaikey_video",
        "capability": "text_to_video",
        "tier": "veo31_fast_8",
        "runtime_sha": _current_runtime(),
        "estimated_provider_cost": 0.50,
        "estimated_provider_cost_unit": "USD",
    }
    valid, reason, verified = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is True
    assert reason == ""
    assert verified.get("pinned_product") == "video_ai_prompt"
    assert verified.get("pinned_provider") == "shopaikey_video"


def test_18_video_ai_video_reference_no_regression():
    """18 video_ai_video_reference -> no regression."""
    # Invalid without required fields
    auth_incomplete = {
        "owner_authorized": True,
        "acceptance_type": video_provider_router.OWNER_AUTHORIZED_LIVE_ACCEPTANCE,
        "product_type": "video_ai_video_reference",
        "user_id": 12345,
        "job_id": 101,
        "runtime_sha": _current_runtime(),
    }
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(
        auth_incomplete, context={"user_id": 12345, "job_id": 101}
    )
    assert valid is False
    assert reason in {"owner_acceptance_provider_missing", "owner_acceptance_capability_missing"}


# ==============================================================================
# PHASE G — 20 MANDATORY PROVIDER-FREE TEST CASES (R16.10B14N11A)
# ==============================================================================


def test_phase_g_01_auth_missing_user_id_denied():
    """01 auth missing user_id -> DENY."""
    auth = _make_r05a_auth(user_id=None)
    assert "user_id" not in auth
    ctx = _make_r05a_ctx()
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is False
    assert reason == "owner_acceptance_user_id_missing"


def test_phase_g_02_auth_missing_job_id_denied():
    """02 auth missing job_id -> DENY."""
    auth = _make_r05a_auth(job_id=None)
    assert "job_id" not in auth
    ctx = _make_r05a_ctx()
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is False
    assert reason == "owner_acceptance_job_id_missing"


def test_phase_g_03_auth_missing_project_id_denied():
    """03 auth missing project_id -> DENY."""
    auth = _make_r05a_auth(project_id=None)
    assert "project_id" not in auth
    ctx = _make_r05a_ctx()
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is False
    assert reason == "owner_acceptance_project_id_missing"


def test_phase_g_04_ctx_missing_user_id_and_account_id_denied():
    """04 ctx missing user_id/account_id -> DENY."""
    auth = _make_r05a_auth()
    ctx = _make_r05a_ctx(user_id=None, account_id=None)
    assert "user_id" not in ctx and "account_id" not in ctx
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is False
    assert reason == "owner_acceptance_user_id_missing"


def test_phase_g_05_ctx_missing_job_id_denied():
    """05 ctx missing job_id -> DENY."""
    auth = _make_r05a_auth()
    ctx = _make_r05a_ctx(job_id=None)
    assert "job_id" not in ctx
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is False
    assert reason == "owner_acceptance_job_id_missing"


def test_phase_g_06_ctx_missing_project_id_denied():
    """06 ctx missing project_id -> DENY."""
    auth = _make_r05a_auth()
    ctx = _make_r05a_ctx(project_id=None)
    assert "project_id" not in ctx
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is False
    assert reason == "owner_acceptance_project_id_missing"


def test_phase_g_07_ctx_missing_provider_denied():
    """07 ctx missing provider -> DENY."""
    auth = _make_r05a_auth()
    ctx = _make_r05a_ctx(provider=None)
    assert "provider" not in ctx and "selected_provider" not in ctx
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is False
    assert reason == "owner_acceptance_provider_missing"


def test_phase_g_08_ctx_missing_capability_denied():
    """08 ctx missing capability -> DENY."""
    auth = _make_r05a_auth()
    ctx = _make_r05a_ctx(capability=None)
    assert "capability" not in ctx and "required_capability" not in ctx
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is False
    assert reason == "owner_acceptance_capability_missing"


def test_phase_g_09_ctx_missing_tier_denied():
    """09 ctx missing tier -> DENY."""
    auth = _make_r05a_auth()
    ctx = _make_r05a_ctx(tier=None)
    assert "tier" not in ctx and "quality_tier" not in ctx
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is False
    assert reason == "owner_acceptance_tier_missing"


def test_phase_g_10_ctx_missing_model_denied():
    """10 ctx missing model -> DENY."""
    auth = _make_r05a_auth()
    ctx = _make_r05a_ctx(model=None)
    assert "model" not in ctx and "selected_model" not in ctx
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is False
    assert reason == "owner_acceptance_model_missing"


def test_phase_g_11_ctx_missing_engine_denied():
    """11 ctx missing engine -> DENY."""
    auth = _make_r05a_auth()
    ctx = _make_r05a_ctx(engine_adapter=None)
    assert "engine_adapter" not in ctx
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is False
    assert reason == "owner_acceptance_engine_adapter_mismatch"


def test_phase_g_12_auth_tier_long_denied():
    """12 auth tier="long" -> DENY."""
    auth = _make_r05a_auth(tier="long")
    ctx = _make_r05a_ctx(tier=700)
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is False
    assert reason == "owner_acceptance_tier_mismatch"


def test_phase_g_13_auth_tier_kling_long_audio_15_denied():
    """13 auth tier="kling_long_audio_15" -> DENY."""
    auth = _make_r05a_auth(tier="kling_long_audio_15")
    ctx = _make_r05a_ctx(tier=700)
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is False
    assert reason == "owner_acceptance_tier_mismatch"


def test_phase_g_14_ctx_tier_long_denied():
    """14 ctx tier="long" -> DENY."""
    auth = _make_r05a_auth(tier=700)
    ctx = _make_r05a_ctx(tier="long")
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is False
    assert reason == "owner_acceptance_tier_mismatch"


def test_phase_g_15_ctx_tier_kling_long_audio_15_denied():
    """15 ctx tier="kling_long_audio_15" -> DENY."""
    auth = _make_r05a_auth(tier=700)
    ctx = _make_r05a_ctx(tier="kling_long_audio_15")
    valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is False
    assert reason == "owner_acceptance_tier_mismatch"


def test_phase_g_16_wrong_provider_with_allow_secondary_provider_denied():
    """16 wrong provider + allow_secondary_provider=True -> DENY."""
    for bad_provider in ["shopaikey_video", "fal_video", "fal.ai"]:
        auth = _make_r05a_auth(provider=bad_provider, allow_secondary_provider=True)
        ctx = _make_r05a_ctx(provider=bad_provider)
        valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
        assert valid is False, f"Provider {bad_provider} with allow_secondary_provider=True must be rejected"
        assert reason == "owner_acceptance_provider_mismatch"


def test_phase_g_17_wrong_product_with_allow_other_product_denied():
    """17 wrong product + allow_other_product=True -> DENY."""
    for bad_product in ["self_shot_cinematic_transform", "storyboard", "video_ai_prompt"]:
        auth = _make_r05a_auth(product_type=bad_product, allow_other_product=True)
        ctx = _make_r05a_ctx(product_type=bad_product)
        valid, reason, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
        assert valid is False, f"Product {bad_product} with allow_other_product=True must be rejected"
        assert reason == "owner_acceptance_product_mismatch"


def test_phase_g_18_exact_canonical_auth_ctx_tuple_passes():
    """18 exact canonical auth+ctx tuple -> PASS."""
    auth = _make_r05a_auth()
    ctx = _make_r05a_ctx()
    valid, reason, verified = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is True
    assert reason == ""
    assert verified.get("verified") is True


def test_phase_g_19_account_id_alias_supported_when_user_id_absent():
    """19 account_id alias chỉ được dùng nếu đây là documented canonical runtime identity source."""
    auth = _make_r05a_auth(user_id=12345)
    ctx = _make_r05a_ctx(user_id=None, account_id=12345)
    assert "user_id" not in ctx
    assert ctx.get("account_id") == 12345
    valid, reason, verified = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is True
    assert reason == ""

    # Mismatch with account_id -> DENY
    ctx_mismatch = _make_r05a_ctx(user_id=None, account_id=99999)
    valid_m, reason_m, _ = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx_mismatch)
    assert valid_m is False
    assert reason_m == "owner_acceptance_user_mismatch"


def test_phase_g_20_verified_output_remains_canonical():
    """20 verified output remains exactly canonical."""
    auth = _make_r05a_auth()
    ctx = _make_r05a_ctx()
    valid, reason, verified = video_provider_router.validate_owner_acceptance_authorization(auth, context=ctx)
    assert valid is True
    assert reason == ""
    assert verified["pinned_product"] == "self_shot_scene_change"
    assert verified["pinned_provider"] == "key4u_video"
    assert verified["pinned_tier"] == "700"
    assert verified["model"] == "kling-v3"
    assert verified["engine_adapter"] == "controlled_keyframe_image_to_video"
    assert verified["required_capability"] == "image_to_video"
    assert verified["provider_order"] == ["key4u_video"]
    assert verified["effective_provider_chain"] == ["key4u_video"]
    assert verified["automatic_fallback_allowed"] is False
    assert verified["automatic_resubmit_allowed"] is False
    assert verified["max_provider_submits"] == 1
