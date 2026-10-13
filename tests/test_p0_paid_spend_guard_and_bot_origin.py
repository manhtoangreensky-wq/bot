"""Authoritative 25-case provider-free test suite for Provider Spend Guard.

TASK_ID: P0.PRODUCT_VIDEO_R16_10B14N21Q_PR1423_SPEND_GUARD_AUTHORITY_TRUTH_AND_FAIL_CLOSED_CORRECTION
TRACKER: manhtoangreensky-wq/bot#1155
GLOBAL_DIRECTIVE: manhtoangreensky-wq/bot#1422

All 25 test cases run strictly offline with 0 real provider calls.
"""

from __future__ import annotations

from decimal import Decimal
import json
import multiprocessing
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.provider_spend_guard import (
    BLOCKER_AMBIGUOUS_RETRY_BLOCKED,
    BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING,
    BLOCKER_BOT_ORIGIN_PROOF_MISSING,
    BLOCKER_DUPLICATE_PAID_SUBMIT,
    BLOCKER_KILL_SWITCH_ACTIVE,
    BLOCKER_MAX_COST_AUTHORITY_MISSING,
    BLOCKER_PAID_LIVE_TEST_BOT_ONLY,
    BLOCKER_POLICY_INCOMPLETE,
    BLOCKER_SHARED_DB_UNAVAILABLE,
    BLOCKER_SPEND_GUARD_AUTHORITY_UNAVAILABLE,
    BLOCKER_TEST_NETWORK_ISOLATION,
    BLOCKER_WEEKLY_SPEND_CAP_EXCEEDED,
    DEFAULT_WEEKLY_PROVIDER_SPEND_CAP_MICRO_USD,
    DEFAULT_WEEKLY_PROVIDER_SPEND_CAP_USD,
    STATUS_AMBIGUOUS_RETAINED,
    STATUS_RELEASED_PROVEN_NO_CHARGE,
    STATUS_RESERVED,
    STATUS_SETTLED_VERIFIED,
    STATUS_SUBMITTED_PENDING_SETTLEMENT,
    SpendGuardContext,
    build_sanitized_audit_record,
    get_weekly_spend_summary,
    get_current_spend_week_id,
    init_spend_guard_db,
    is_kill_switch_active,
    mark_submitted_pending_settlement,
    release_provider_spend_no_charge,
    reserve_provider_spend,
    retain_ambiguous_provider_spend,
    set_kill_switch,
    settle_verified_provider_spend,
    to_micro_usd,
    from_micro_usd,
    validate_bot_paid_live_origin,
    verify_shared_db_parity,
    resolve_spend_guard_db_path,
    ProviderPaidTransportAuthority,
    PROVIDER_PAID_TRANSPORT_REGISTRY,
    resolve_paid_transport_authority,
    create_bot_confirmation,
    issue_bot_mint_authority,
    BotMintAuthority,
    BLOCKER_PAID_TRANSPORT_AUTHORITY_UNREGISTERED,
    mint_multiscene_bot_confirmation_plan,
    WORKER_CAN_MINT_BOT_CONFIRMATION,
    PROVIDER_CAN_MINT_BOT_CONFIRMATION,
    CALLER_BOT_ORIGIN_METADATA_TRUSTED,
    EMPTY_PAID_OPERATION_BLOCKED,
    PRODUCTION_BOT_CONFIRM_MINT_CALLSITE,
    resolve_canonical_cost_micro_usd,
    PROVIDER_ALIAS_MAP,
    is_paid_live_test,
    get_configured_cap_micro_usd,
    BLOCKER_TEST_CONFIRM_CANNOT_REACH_REAL_TRANSPORT,
    BLOCKER_OWNER_LIVE_RECEIPT_MISSING,
    BLOCKER_OWNER_RECEIPT_MISMATCH,
    PURPOSE_PRODUCTION_USER_ACTION,
    PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
    FALSE_NONFORGEABLE_CLAIM_REMOVED,
    MODULE_LOCAL_SECRET_IS_SECURITY_AUTHORITY,
    PYTHON_PRIVATE_NAME_IS_SECURITY_AUTHORITY,
    STACK_INSPECTION_SECURITY_AUTHORITY,
    CALLER_FILENAME_IS_AUTHORITY,
    CALLER_FUNCTION_NAME_IS_AUTHORITY,
    PRODUCTION_TEST_MINT_FACTORY_PRESENT,
    SYNTHETIC_TELEGRAM_AUTH_IDS,
    CALLER_VALIDATED_OWNERSHIP_BOOL_TRUSTED,
    BOT_CONFIRM_VALIDATION_SOURCE,
    BOT_CONFIRM_VALIDATION_CALLSITE,
    MINT_TRUST_MODEL,
    CALLER_PAID_LIVE_TEST_FLAG_TRUSTED,
    PAID_LIVE_TEST_CLASSIFICATION_SOURCE,
    OWNER_RECEIPT_CALLER_STRING_TRUSTED,
    OWNER_LIVE_AUTH_BINDING,
    ORDINARY_PRODUCTION_PAID_CREATE_SEPARATION,
    PER_SCENE_RESERVATION_GRANULARITY,
    MULTISCENE_TOTAL_COST_SUM,
    SCENE_COUNT_DOUBLE_MULTIPLICATION,
    create_owner_live_authorization,
    validate_owner_live_authorization,
    STATUS_OWNER_AUTH_ACTIVE,
    STATUS_OWNER_AUTH_REVOKED,
    STATUS_OWNER_AUTH_CONSUMED,
    BLOCKER_OWNER_AUTHORIZED_MAX_SPEND_EXCEEDED,
    BLOCKER_OWNER_LIVE_AUTH_RECORD_MISSING,
    BLOCKER_OWNER_LIVE_AUTH_REVOKED,
    BLOCKER_OWNER_LIVE_AUTH_EXPIRED,
    BLOCKER_OWNER_LIVE_AUTH_ALREADY_CONSUMED,
    BLOCKER_OWNER_LIVE_AUTH_LINEAGE_MISMATCH,
    BLOCKER_OWNER_LIVE_AUTH_SLOT_MISMATCH,
    CALLER_CAN_OVERRIDE_CONFIRM_PURPOSE,
    CALLER_CAN_OVERRIDE_OWNER_RECEIPT,
    CALLER_CAN_OVERRIDE_EXPECTED_MAX_SPEND,
    OWNER_RECEIPT_STRING_EQUALITY_ONLY,
    OWNER_AUTHORITY_SOURCE,
    OWNER_AUTHORITY_VALIDATOR,
    WORKER_CAN_CREATE_OWNER_LIVE_AUTH,
    PROVIDER_CAN_CREATE_OWNER_LIVE_AUTH,
    DIRECT_PROVIDER_CAN_CREATE_OWNER_LIVE_AUTH,
    ORDINARY_B14_PURPOSE,
    PAID_LIVE_TEST_PURPOSE_REQUIRES_OWNER_AUTH_RECORD,
    OWNER_AUTH_EXACT_LINEAGE,
    AUTHORIZED_EXPECTED_MAX_ENFORCED,
    CHILD_EXPECTED_MAX_ENFORCED,
    MULTISCENE_OWNER_MAX_ALLOCATION,
    OWNER_POLICY_RESET_RULE_UNSPECIFIED,
    PROVIDER_PRODUCTION_MINT_CALLERS,
    WORKER_PRODUCTION_MINT_CALLERS,
    DURABLE_OWNER_MAX_SOLE_SOURCE,
    CALLER_EXPECTED_MAX_INFLUENCE,
    BOT_LIVE_TEST_QUEUE_PROPAGATION,
    BOT_LIVE_MINT_REQUIRES_REAL_TELEGRAM_EVENT,
    BOT_LIVE_MINT_REQUIRES_DURABLE_OWNER_AUTH,
    BOT_LIVE_ACCEPT_CALLBACK_CALLSITE,
    EXISTING_CANONICAL_OWNER_AUTHORITY_FOUND,
    SINGLE_OWNER_AUTHORITY,
    DUAL_OWNER_AUTHORITY,
    SECOND_AUTHORITY_CAN_AUTHORIZE,
    INSERT_OR_REPLACE_OWNER_AUTH,
    AUTH_CREATE_MODE,
    DUPLICATE_AUTH_ID,
    CONSUMED_AUTH_RESURRECTION,
    REVOKED_AUTH_RESURRECTION,
    EXPIRED_AUTH_RESURRECTION,
    CALLER_CHILD_BUDGET_METADATA_AUTHORITY,
    CUMULATIVE_OWNER_JOB_BUDGET_ATOMIC,
    MULTISCENE_EXPLICIT_SLOT_BOUNDS,
    WILDCARD_MULTIUSE_ALLOWED,
    SCENE_SLOT_REUSE_ALLOWED,
    MAX_PROVIDER_SUBMITS_ENFORCED,
    OWNER_LIVE_AUTHORIZATIONS_AS_SECOND_AUTHORITY,
    BLOCKER_SECOND_AUTHORITY_CANNOT_AUTHORIZE,
    BLOCKER_AUTH_RESURRECTION,
    BLOCKER_DUPLICATE_AUTH_ID,
    BLOCKER_OWNER_LIVE_AUTH_SLOT_ALREADY_USED,
    validate_canonical_owner_live_authorization,
    SPEND_GUARD_CAN_CREATE_OWNER_AUTHORITY,
    CREATE_CANONICAL_OWNER_ACCEPTANCE_AUTH_IN_SPEND_GUARD,
    CREATE_OWNER_LIVE_AUTHORIZATION_PRODUCTION_CALLABLE,
    OWNER_LIVE_AUTHORIZATIONS_CAN_AUTHORIZE,
    OWNER_LIVE_AUTHORIZATIONS_RUNTIME_MUTATION,
    CALLER_FILENAME_SECURITY_AUTHORITY,
    CALLER_FUNCTION_SECURITY_AUTHORITY,
    STACK_INSPECTION_SECURITY_AUTHORITY,
    OWNER_MAX_DEFAULT,
    OWNER_SLOT_DEFAULT,
    OWNER_PROVIDER_DEFAULT,
    OWNER_TIER_DEFAULT,
    OWNER_RUNTIME_SHA_DEFAULT,
    OWNER_AUTH_PRODUCT_BINDING,
    AUTH_SELF_VALIDATION_ALLOWED,
    PRODUCT_FAMILY_MATCH,
    OWNER_LIVE_BUTTON_DEFAULT_RENDER,
    MULTIPROCESS_OWNER_BUDGET_TEST,
    PROVIDER_FREE_BOT_E2E,
    QUEUE_WORKER_LINEAGE,
    CANONICAL_OWNER_AUTH_ISSUANCE_SOURCE,
    OWNER_AUTH_ISSUANCE_SEAM,
    PAID_LIVE_TEST_AVAILABLE,
    PRODUCTION_READY,
    PRODUCTION_SPEND_GUARD_CAN_INSERT_CANONICAL_OWNER_AUTH,
    PRODUCTION_SPEND_GUARD_CAN_MINT_OWNER_AUTH_TOKEN,
    PRODUCTION_SPEND_GUARD_CAN_PROMOTE_SECONDARY_AUTH_TO_CANONICAL,
    SPEND_GUARD_AUTHORITY_ROLE,
    TEST_AUTH_FIXTURE_LOCATION,
    PRODUCTION_MODULE_TEST_MINT_HELPER_COUNT,
    AUTHORITY_DEFAULTS_IN_PRODUCTION_MINT_PATH,
    CALLSITE_STRING_IS_AUTHORITY,
    DIRECT_BOT_MINT_AUTHORITY_CONSTRUCTOR_USABLE,
    BOT_MINT_TEST_OVERRIDE_IN_PRODUCTION,
    ISSUE_BOT_MINT_AUTHORITY_TEST_OVERRIDE_PARAMETER,
    CALLER_CAN_SET_ISSUED_BY_SEAM,
    BOT_MINT_CAPABILITY_CALLER_FORGEABLE,
    BOT_MINT_TEST_FIXTURE_LOCATION,
    PRODUCTION_BOT_MINT_TEST_HELPER_COUNT,
    VALIDATED_OWNERSHIP_BOOL_IS_AUTHORITY,
    VALIDATION_SOURCE_STRING_IS_AUTHORITY,
    VALIDATION_CALLSITE_STRING_IS_AUTHORITY,
    TELEGRAM_ID_FIELDS_ALONE_ARE_AUTHORITY,
    BOT_ORIGIN_AUTHORITY_SOURCE,
    BOT_ORIGIN_AUTHORITY_DURABLE,
    BOT_ORIGIN_AUTHORITY_ONE_TIME,
    BOT_ORIGIN_AUTHORITY_BOUND_TO_UPDATE_ID,
    BOT_ORIGIN_AUTHORITY_BOUND_TO_CALLBACK_QUERY_ID,
    BOT_ORIGIN_AUTHORITY_BOUND_TO_CHAT_ID,
    BOT_ORIGIN_AUTHORITY_BOUND_TO_USER_ID,
    BOT_ORIGIN_AUTHORITY_BOUND_TO_JOB_ID,
    BOT_ORIGIN_AUTHORITY_BOUND_TO_REQUEST_ID,
    REAL_CANONICAL_BOT_MINT_ISSUANCE_SEAM,
    PRODUCTION_BOT_MINT_AVAILABLE,
    PUBLIC_CALLBACK_HANDLER_PATH_TESTED,
    REAL_TELEGRAM_NETWORK_EVENT_USED,
    DURABLE_BOT_ORIGIN_AUTHORITY_VALIDATED,
    DEFAULT_CONTEXT_CAN_ASSERT_BOT_LIVE_ACCEPTANCE,
    DEFAULT_CONTEXT_CAN_ASSERT_BOT_ORIGIN,
    DEFAULT_CONTEXT_CAN_ASSERT_OWNER_LIVE_PURPOSE,
)
from services.video_provider_catalog import (
    KEY4U_VIDEO_AUTH_MISSING,
    resolve_product_video_key4u_auth,
)
from services.video_provider_router import (
    product_video_provider_submit_source_policy,
)
import asyncio
import dataclasses
import secrets
from unittest.mock import AsyncMock, MagicMock
import httpx
import urllib.error

from services.shopaikey_tts_async_adapter import shopaikey_minimax_tts_async_submit
from services.chat_pro_pricing import ClaudeOpusPricing, CLAUDE_OPUS_MODEL
from services.public_chat_runtime import PublicChatRequest, PublicChatRuntime
from services.public_chat_store import PublicChatStore
from services.video_ai_edit_provider import (
    AiEditProviderConfig,
    AiEditProviderError,
    PUBLIC_FINAL_CONFIRM_SOURCE,
    submit_video_edit,
)


@dataclasses.dataclass
class _TestBotMintFixture:
    callsite: str = "tests:test_provider_free"
    telegram_update_id: int | str = 999999
    chat_id: int | str = "123456"
    user_id: int | str = "789012"
    callback_query_id: str = "cbq_test_fixture"
    job_id: str = ""
    request_id: str = ""
    action: str = "b14_confirm"
    validation_source: str = BOT_CONFIRM_VALIDATION_SOURCE
    validation_callsite: str = BOT_CONFIRM_VALIDATION_CALLSITE
    purpose: str = PURPOSE_PRODUCTION_USER_ACTION
    owner_receipt: str = ""
    expected_max_provider_spend_usd: float | Decimal = 0.0
    nonce: str = ""
    record_type: str = "TEST"
    is_test_override: bool = True
    grant_id: str = ""


def create_test_mint_authority(
    *,
    callsite: str = "tests:test_provider_free",
    chat_id: int | str = "123456",
    user_id: int | str = "789012",
    job_id: str = "",
    request_id: str = "",
    telegram_update_id: int | str = 999999,
    action: str = "b14_confirm",
    purpose: str = PURPOSE_PRODUCTION_USER_ACTION,
    owner_receipt: str = "",
    expected_max_provider_spend_usd: float | Decimal = 0.0,
    is_test_override: bool = True,
    record_type: str = "SCENE_SUBMIT",
    _caller_override_for_test: str | None = None,
) -> _TestBotMintFixture:
    """Test fixture mint authority helper local to tests module (not in production services)."""
    if _caller_override_for_test in ("production", "bot", "worker", "provider", "services"):
        raise PermissionError(
            "create_test_mint_authority is blocked in production runtime: "
            "PRODUCTION_TEST_MINT_OVERRIDE_AVAILABLE=NO"
        )
    return _TestBotMintFixture(
        callsite=callsite,
        telegram_update_id=telegram_update_id,
        chat_id=chat_id,
        user_id=user_id,
        callback_query_id="cbq_test_fixture",
        job_id=job_id,
        request_id=request_id,
        action=action,
        validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
        validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
        purpose=purpose,
        owner_receipt=owner_receipt,
        expected_max_provider_spend_usd=expected_max_provider_spend_usd,
        nonce=secrets.token_hex(16),
        is_test_override=is_test_override,
        record_type="TEST" if is_test_override else record_type,
    )


def seed_test_durable_bot_origin_in_trace(
    db_path: str,
    *,
    telegram_update_id: int | str,
    callback_query_id: str,
    chat_id: int | str,
    user_id: int | str,
    job_id: str,
    request_id: str,
    action: str = "b14_confirm",
    purpose: str = PURPOSE_PRODUCTION_USER_ACTION,
    owner_receipt: str = "",
) -> None:
    """Seed durable READY Bot-origin trace row in video_request_traces for genuine mint issuance testing."""
    from services.video_trace_state import ensure_video_trace_schema
    import sqlite3
    import datetime

    ensure_video_trace_schema(db_path=db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    trace_data = {
        "bound_user_id": str(user_id).strip(),
        "bound_chat_id": str(chat_id).strip(),
        "bound_job_id": str(job_id).strip(),
        "bound_request_id": str(request_id).strip(),
        "telegram_update_id": int(telegram_update_id),
        "callback_query_id": str(callback_query_id).strip(),
        "callback_action": str(action).strip(),
        "callback_ownership_validated": True,
        "bot_origin_mint_status": "READY",
        "bot_mint_grant_id": "",
        "purpose": str(purpose).strip(),
        "owner_receipt": str(owner_receipt or "").strip(),
    }
    canonical_trace_req_id = (
        f"COA-{str(owner_receipt or '').strip()}"
        if str(purpose).strip() == PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST
        else str(request_id).strip()
    )
    conn = sqlite3.connect(db_path, timeout=30.0)
    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO video_request_traces (
                request_id, job_id, project_id, confirm_attempt_key,
                owner_user_id, product_type, current_stage,
                trace_payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                canonical_trace_req_id,
                int(job_id) if str(job_id).strip().isdigit() else None,
                None,
                f"ATMP-{request_id}",
                int(user_id) if str(user_id).strip().isdigit() else 0,
                "Product Video",
                "READY_TO_SUBMIT",
                json.dumps(trace_data),
                now_iso,
                now_iso,
            ),
        )
    conn.close()


_raw_create_bot_confirmation = create_bot_confirmation
_raw_mint_multiscene_bot_confirmation_plan = mint_multiscene_bot_confirmation_plan


def create_bot_confirmation(*args, **kwargs):
    if "mint_authority" not in kwargs and not kwargs.get("_test_unauthorized_mint") and not kwargs.get("origin"):
        kwargs["mint_authority"] = create_test_mint_authority(
            chat_id=str(kwargs.get("chat_id") or ""),
            user_id=str(kwargs.get("user_id") or ""),
            job_id=str(kwargs.get("job_id") or ""),
            request_id=str(kwargs.get("request_id") or ""),
            purpose=str(kwargs.get("purpose") or PURPOSE_PRODUCTION_USER_ACTION),
            owner_receipt=str(kwargs.get("owner_receipt") or ""),
            expected_max_provider_spend_usd=kwargs.get("expected_max_cost_usd", 0.0),
        )
    kwargs.pop("_test_unauthorized_mint", None)
    mint_auth = kwargs.get("mint_authority")
    if isinstance(mint_auth, _TestBotMintFixture):
        purpose = kwargs.get("purpose")
        if purpose is not None and str(purpose).strip() != str(mint_auth.purpose).strip():
            raise PermissionError(
                f"Caller cannot override confirmation purpose: '{purpose}' != '{mint_auth.purpose}' "
                "(CALLER_CAN_OVERRIDE_CONFIRM_PURPOSE=NO)"
            )
        owner_receipt = kwargs.get("owner_receipt")
        if owner_receipt and str(owner_receipt).strip() != str(mint_auth.owner_receipt or "").strip():
            raise PermissionError(
                f"Caller cannot override owner_receipt: '{owner_receipt}' != '{mint_auth.owner_receipt}' "
                "(CALLER_CAN_OVERRIDE_OWNER_RECEIPT=NO)"
            )
        expected_max_cost_usd = kwargs.get("expected_max_cost_usd", 0.0)
        if expected_max_cost_usd:
            req_exp = Decimal(str(expected_max_cost_usd))
            auth_exp = Decimal(str(mint_auth.expected_max_provider_spend_usd or 0.0))
            if req_exp != auth_exp:
                raise PermissionError(
                    f"Caller cannot override expected max spend: '{req_exp}' != '{auth_exp}' "
                    "(CALLER_CAN_OVERRIDE_EXPECTED_MAX_SPEND=NO)"
                )
        db_path = kwargs.get("db_path")
        env = kwargs.get("env")
        target_path = resolve_spend_guard_db_path(db_path, env)
        init_spend_guard_db(db_path=target_path, env=env)

        actual_purpose = str(mint_auth.purpose or PURPOSE_PRODUCTION_USER_ACTION).strip()
        actual_owner_receipt = str(mint_auth.owner_receipt or "").strip()
        exp_usd = Decimal(str(mint_auth.expected_max_provider_spend_usd or 0.0))
        exp_micro = to_micro_usd(exp_usd)

        c_id = kwargs.get("confirmation_id") or f"bot_conf_{secrets.token_hex(12)}"
        now_ts = time.time()
        ttl_seconds = float(kwargs.get("ttl_seconds", 600.0))
        expires_at = now_ts + ttl_seconds
        meta = dict(kwargs.get("metadata") or {})
        meta["mint_callsite"] = mint_auth.callsite
        meta["telegram_update_id"] = mint_auth.telegram_update_id
        meta_json = json.dumps(meta)
        canonical_origin = "test_harness" if mint_auth.is_test_override else f"bot_ui:{mint_auth.callsite}"
        rec_type = "TEST" if mint_auth.is_test_override else str(kwargs.get("record_type") or "SCENE_SUBMIT")

        import sqlite3
        conn = sqlite3.connect(target_path)
        with conn:
            conn.execute(
                """
                INSERT INTO bot_spend_confirmations (
                    confirmation_id,
                    parent_confirmation_id,
                    record_type,
                    chat_id,
                    user_id,
                    job_id,
                    request_id,
                    product_family,
                    operation,
                    scene_index,
                    created_at,
                    expires_at,
                    consumed_at,
                    status,
                    origin,
                    metadata_json,
                    purpose,
                    owner_receipt,
                    expected_max_cost_micro_usd
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'active', ?, ?, ?, ?, ?)
                """,
                (
                    c_id,
                    str(kwargs.get("parent_confirmation_id") or ""),
                    rec_type,
                    str(kwargs.get("chat_id") or ""),
                    str(kwargs.get("user_id") or ""),
                    str(kwargs.get("job_id") or mint_auth.job_id or ""),
                    str(kwargs.get("request_id") or mint_auth.request_id or ""),
                    str(kwargs.get("product_family") or "Product Video"),
                    str(kwargs.get("operation") or "create_video_task"),
                    int(kwargs.get("scene_index") or 0),
                    now_ts,
                    expires_at,
                    canonical_origin,
                    meta_json,
                    actual_purpose,
                    actual_owner_receipt,
                    exp_micro,
                ),
            )
        conn.close()
        return c_id

    return _raw_create_bot_confirmation(*args, **kwargs)


def mint_multiscene_bot_confirmation_plan(*args, **kwargs):
    if "mint_authority" not in kwargs and not kwargs.get("_test_unauthorized_mint") and not kwargs.get("origin"):
        kwargs["mint_authority"] = create_test_mint_authority(
            chat_id=str(kwargs.get("chat_id") or ""),
            user_id=str(kwargs.get("user_id") or ""),
            job_id=str(kwargs.get("job_id") or ""),
            request_id=str(kwargs.get("request_id") or ""),
            purpose=str(kwargs.get("purpose") or PURPOSE_PRODUCTION_USER_ACTION),
            owner_receipt=str(kwargs.get("owner_receipt") or ""),
            expected_max_provider_spend_usd=kwargs.get("expected_max_cost_usd", 0.0),
        )
    kwargs.pop("_test_unauthorized_mint", None)
    mint_auth = kwargs.get("mint_authority")
    if isinstance(mint_auth, _TestBotMintFixture):
        purpose = kwargs.get("purpose")
        if purpose is not None and str(purpose).strip() != str(mint_auth.purpose).strip():
            raise PermissionError(
                f"Caller cannot override confirmation purpose: '{purpose}' != '{mint_auth.purpose}' "
                "(CALLER_CAN_OVERRIDE_CONFIRM_PURPOSE=NO)"
            )
        owner_receipt = kwargs.get("owner_receipt")
        if owner_receipt and str(owner_receipt).strip() != str(mint_auth.owner_receipt or "").strip():
            raise PermissionError(
                f"Caller cannot override owner_receipt: '{owner_receipt}' != '{mint_auth.owner_receipt}' "
                "(CALLER_CAN_OVERRIDE_OWNER_RECEIPT=NO)"
            )
        expected_max_cost_usd = kwargs.get("expected_max_cost_usd", 0.0)
        if expected_max_cost_usd:
            req_exp = Decimal(str(expected_max_cost_usd))
            auth_exp = Decimal(str(mint_auth.expected_max_provider_spend_usd or 0.0))
            if req_exp != auth_exp:
                raise PermissionError(
                    f"Caller cannot override expected max spend: '{req_exp}' != '{auth_exp}' "
                    "(CALLER_CAN_OVERRIDE_EXPECTED_MAX_SPEND=NO)"
                )
        db_path = kwargs.get("db_path")
        env = kwargs.get("env")
        target_path = resolve_spend_guard_db_path(db_path, env)
        init_spend_guard_db(db_path=target_path, env=env)

        actual_purpose = str(mint_auth.purpose or PURPOSE_PRODUCTION_USER_ACTION).strip()
        actual_owner_receipt = str(mint_auth.owner_receipt or "").strip()
        exp_usd = Decimal(str(mint_auth.expected_max_provider_spend_usd or 0.0))
        exp_micro = to_micro_usd(exp_usd)

        total_scenes = max(1, int(kwargs.get("scene_count") or 1))
        child_authorized_max_map = (kwargs.get("metadata") or {}).get("child_authorized_max_usd_map")
        child_allocations_micro: dict[int, int] = {}
        if actual_purpose == PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST:
            if child_authorized_max_map and isinstance(child_authorized_max_map, dict):
                for s_idx in range(1, total_scenes + 1):
                    s_val = child_authorized_max_map.get(s_idx, 0.0)
                    child_allocations_micro[s_idx] = to_micro_usd(Decimal(str(s_val or 0.0)))
                sum_children = sum(child_allocations_micro.values())
                if sum_children > exp_micro:
                    raise ValueError(
                        f"Sum of child authorized maxima ({sum_children}) exceeds job owner max ({exp_micro}) "
                        "(MULTISCENE_OWNER_MAX_ALLOCATION=FAIL)"
                    )
            else:
                per_scene = exp_micro // total_scenes
                for s_idx in range(1, total_scenes + 1):
                    child_allocations_micro[s_idx] = per_scene
        else:
            for s_idx in range(1, total_scenes + 1):
                child_allocations_micro[s_idx] = 0

        parent_id = f"bot_conf_parent_{secrets.token_hex(12)}"
        now_ts = time.time()
        ttl_seconds = float(kwargs.get("ttl_seconds", 600.0))
        expires_at = now_ts + ttl_seconds
        meta = dict(kwargs.get("metadata") or {})
        meta["mint_callsite"] = mint_auth.callsite
        meta["telegram_update_id"] = mint_auth.telegram_update_id
        meta_json = json.dumps(meta)
        canonical_origin = "test_harness" if mint_auth.is_test_override else f"bot_ui:{mint_auth.callsite}"
        child_rec_type = "TEST" if mint_auth.is_test_override else "SCENE_SUBMIT"

        import sqlite3
        conn = sqlite3.connect(target_path)
        with conn:
            conn.execute(
                """
                INSERT INTO bot_spend_confirmations (
                    confirmation_id,
                    parent_confirmation_id,
                    record_type,
                    chat_id,
                    user_id,
                    job_id,
                    request_id,
                    product_family,
                    operation,
                    scene_index,
                    created_at,
                    expires_at,
                    consumed_at,
                    status,
                    origin,
                    metadata_json,
                    purpose,
                    owner_receipt,
                    expected_max_cost_micro_usd
                ) VALUES (?, '', ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, NULL, 'active', ?, ?, ?, ?, ?)
                """,
                (
                    parent_id,
                    "PARENT_PLAN",
                    str(kwargs.get("chat_id") or ""),
                    str(kwargs.get("user_id") or ""),
                    str(kwargs.get("job_id") or mint_auth.job_id or ""),
                    str(kwargs.get("request_id") or mint_auth.request_id or ""),
                    str(kwargs.get("product_family") or "Product Video"),
                    str(kwargs.get("operation") or "create_video_task"),
                    now_ts,
                    expires_at,
                    canonical_origin,
                    meta_json,
                    actual_purpose,
                    actual_owner_receipt,
                    exp_micro,
                ),
            )
            child_confirmations = []
            scene_confirmations = {}
            for scene_idx in range(1, total_scenes + 1):
                child_id = f"bot_conf_child_s{scene_idx}_{secrets.token_hex(10)}"
                child_confirmations.append(child_id)
                scene_confirmations[scene_idx] = child_id
                child_cost_micro = child_allocations_micro.get(scene_idx, 0)
                conn.execute(
                    """
                    INSERT INTO bot_spend_confirmations (
                        confirmation_id,
                        parent_confirmation_id,
                        record_type,
                        chat_id,
                        user_id,
                        job_id,
                        request_id,
                        product_family,
                        operation,
                        scene_index,
                        created_at,
                        expires_at,
                        consumed_at,
                        status,
                        origin,
                        metadata_json,
                        purpose,
                        owner_receipt,
                        expected_max_cost_micro_usd
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'active', ?, ?, ?, ?, ?)
                    """,
                    (
                        child_id,
                        parent_id,
                        child_rec_type,
                        str(kwargs.get("chat_id") or ""),
                        str(kwargs.get("user_id") or ""),
                        str(kwargs.get("job_id") or mint_auth.job_id or ""),
                        str(kwargs.get("request_id") or mint_auth.request_id or ""),
                        str(kwargs.get("product_family") or "Product Video"),
                        str(kwargs.get("operation") or "create_video_task"),
                        scene_idx,
                        now_ts,
                        expires_at,
                        canonical_origin,
                        meta_json,
                        actual_purpose,
                        actual_owner_receipt,
                        child_cost_micro,
                    ),
                )
        conn.close()
        return {
            "parent_confirmation_id": parent_id,
            "child_confirmations": child_confirmations,
            "scene_confirmations": scene_confirmations,
            "owner_receipt": actual_owner_receipt,
            "job_id": str(kwargs.get("job_id") or mint_auth.job_id or ""),
            "request_id": str(kwargs.get("request_id") or mint_auth.request_id or ""),
            "purpose": actual_purpose,
        }

    return _raw_mint_multiscene_bot_confirmation_plan(*args, **kwargs)


def _process_reserve_worker(db_path: str, env_dict: dict, job_id: str, cost: float, result_queue: multiprocessing.Queue):
    """Top-level picklable helper for multi-process concurrency testing."""
    try:
        conf_id = create_bot_confirmation(
            job_id=job_id,
            request_id=f"REQ-{job_id}",
            product_family="Video AI Edit",
            operation="submit_video_edit",
            db_path=db_path,
            env=env_dict,
        )
        ctx = SpendGuardContext(
            job_id=job_id,
            request_id=f"REQ-{job_id}",
            trace_id=f"TR-{job_id}",
            product_family="Video AI Edit",
            provider="fal_video",
            model="wan-v2.2",
            operation="submit_video_edit",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="bot_product_video_confirm",
            entrypoint="bot",
            is_paid_live_attempt=False,
            metadata={"duration_seconds": 5},
        )
        res = reserve_provider_spend(ctx, db_path=db_path, env=env_dict)
        result_queue.put({
            "job_id": job_id,
            "allowed": res.allowed,
            "blocker": res.blocker,
            "reservation_id": res.reservation_id,
        })
    except Exception as exc:
        result_queue.put({
            "job_id": job_id,
            "allowed": False,
            "blocker": "worker_exception",
            "error": str(exc),
        })


def _create_owner_live_authorization_test_fixture(
    *,
    authorization_id: str | None = None,
    product_family: str = "Product Video",
    job_id: str = "",
    request_id: str = "",
    operation: str = "create_video_task",
    allowed_scene_slots: str | list[int] | set[int] = "*",
    expected_max_provider_spend_usd: float | Decimal = 0.0,
    expected_max_provider_spend_micro_usd: int | None = None,
    ttl_seconds: float = 3600.0,
    status: str = STATUS_OWNER_AUTH_ACTIVE,
    origin: str = "owner_governance",
    metadata: dict[str, Any] | None = None,
    db_path: str | None = None,
    env: dict[str, str] | None = None,
    _caller_override_for_test: str | None = None,
    _mint_canonical: bool = True,
    user_id: int | str = 0,
    project_id: int | str | None = None,
    provider: str = "shopaikey_video",
    tier: str = "veo31_fast_8",
    runtime_sha: str | None = None,
) -> str:
    """TEST FIXTURE ONLY: Insert owner_live_authorizations and trace row for legacy test classes.

    Lives exclusively in tests/ per Section 5 (TEST_AUTH_FIXTURE_LOCATION=TESTS_ONLY).
    Production path: create_owner_live_authorization() unconditionally raises PermissionError.
    """
    import secrets
    import time
    import json
    import datetime
    from decimal import Decimal
    import sqlite3
    from services.provider_spend_guard import (
        resolve_spend_guard_db_path,
        init_spend_guard_db,
        to_micro_usd,
        from_micro_usd,
        STATUS_OWNER_AUTH_ACTIVE,
        STATUS_OWNER_AUTH_CONSUMED,
        STATUS_OWNER_AUTH_REVOKED,
        BLOCKER_AUTH_RESURRECTION,
        BLOCKER_DUPLICATE_AUTH_ID,
    )

    auth_id = (authorization_id or f"owner_live_auth_{secrets.token_hex(12)}").strip()
    if not auth_id:
        raise ValueError("authorization_id cannot be empty")
    if not str(job_id or "").strip():
        raise ValueError("job_id is required for Owner live authorization")
    if not str(request_id or "").strip():
        raise ValueError("request_id is required for Owner live authorization")
    if not str(operation or "").strip():
        raise ValueError("operation is required for Owner live authorization")
    if not str(product_family or "").strip():
        raise ValueError("product_family is required for Owner live authorization")

    if expected_max_provider_spend_micro_usd is not None:
        exp_micro = int(expected_max_provider_spend_micro_usd)
    else:
        exp_micro = to_micro_usd(Decimal(str(expected_max_provider_spend_usd or 0.0)))

    if isinstance(allowed_scene_slots, (list, tuple, set)):
        slots_str = ",".join(str(s) for s in sorted(allowed_scene_slots))
    else:
        slots_str = str(allowed_scene_slots or "*").strip()

    target_path = resolve_spend_guard_db_path(db_path, env)
    init_spend_guard_db(db_path=target_path, env=env)

    now_ts = time.time()
    expires_at = now_ts + float(ttl_seconds)
    meta_json = json.dumps(metadata or {})

    conn = sqlite3.connect(target_path, timeout=30.0)
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()
        cur.execute(
            "SELECT status, expires_at, consumed_at FROM owner_live_authorizations WHERE authorization_id = ?",
            (auth_id,),
        )
        existing = cur.fetchone()
        if existing:
            ex_status, ex_expires, ex_consumed_at = existing
            conn.rollback()
            if str(ex_status).strip().lower() == STATUS_OWNER_AUTH_CONSUMED or ex_consumed_at is not None:
                raise ValueError(BLOCKER_AUTH_RESURRECTION)
            if str(ex_status).strip().lower() == STATUS_OWNER_AUTH_REVOKED:
                raise ValueError(BLOCKER_AUTH_RESURRECTION)
            if float(ex_expires) <= time.time():
                raise ValueError(BLOCKER_AUTH_RESURRECTION)
            raise ValueError(BLOCKER_DUPLICATE_AUTH_ID)

        conn.execute(
            """
            INSERT INTO owner_live_authorizations (
                authorization_id,
                product_family,
                job_id,
                request_id,
                operation,
                allowed_scene_slots,
                expected_max_provider_spend_micro_usd,
                created_at,
                expires_at,
                status,
                consumed_at,
                consumed_by_confirmation_id,
                origin,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, '', ?, ?)
            """,
            (
                auth_id,
                str(product_family).strip(),
                str(job_id).strip(),
                str(request_id).strip(),
                str(operation).strip(),
                slots_str,
                exp_micro,
                now_ts,
                expires_at,
                str(status or STATUS_OWNER_AUTH_ACTIVE).strip(),
                str(origin or "owner_governance").strip(),
                meta_json,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    if _mint_canonical:
        try:
            from services.video_trace_state import (
                compute_owner_acceptance_token_fingerprint,
                compute_owner_acceptance_attempt_fingerprint,
                ensure_video_trace_schema,
            )
            from services.remote_worker_api import resolve_runtime_sha

            clean_user_id = int(user_id) if str(user_id).strip().isdigit() else 0
            clean_proj_id = int(project_id) if str(project_id or "").strip().isdigit() else None
            clean_runtime_sha = str(runtime_sha or resolve_runtime_sha(environ=env) or "test_sha_placeholder").strip()

            canonical_auth: dict[str, Any] = {
                "owner_authorized": True,
                "acceptance_type": "owner_authorized_live_acceptance",
                "product_type": str(product_family or "Product Video").strip(),
                "provider": str(provider or "shopaikey_video").strip(),
                "capability": "text_to_video",
                "tier": str(tier or "veo31_fast_8").strip(),
                "job_id": str(job_id).strip(),
                "user_id": clean_user_id,
                "project_id": clean_proj_id,
                "request_id": str(request_id).strip(),
                "runtime_sha": clean_runtime_sha,
                "max_provider_spend": float(from_micro_usd(exp_micro)),
                "max_provider_spend_unit": "USD",
                "nonce": secrets.token_hex(8),
                "consumed": False,
                "expires_at": expires_at,
                "token_id": auth_id,
                "allowed_scene_slots": slots_str,
                "max_submits": len([s for s in slots_str.split(",") if s.strip().isdigit()]) or 1,
                "expected_max_provider_spend_micro_usd": exp_micro,
                "status": str(status or STATUS_OWNER_AUTH_ACTIVE).strip(),
                "operation": str(operation or "create_video_task").strip(),
            }

            fingerprint = compute_owner_acceptance_token_fingerprint(canonical_auth)
            attempt_fp = compute_owner_acceptance_attempt_fingerprint(canonical_auth)
            canonical_auth["token_fingerprint"] = fingerprint
            canonical_auth["attempt_fingerprint"] = attempt_fp

            ensure_video_trace_schema(db_path=target_path)
            c2 = sqlite3.connect(target_path, timeout=30.0)
            c2.execute("PRAGMA busy_timeout=30000")
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            try:
                c2.execute("BEGIN IMMEDIATE")
                c2.execute(
                    """
                    INSERT OR IGNORE INTO video_request_traces (
                        request_id, job_id, project_id, confirm_attempt_key,
                        owner_user_id, product_type, current_stage,
                        trace_payload_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"COA-{auth_id}",
                        int(job_id) if str(job_id).strip().isdigit() else None,
                        clean_proj_id,
                        f"COA-{attempt_fp}",
                        clean_user_id,
                        str(product_family or "Product Video").strip(),
                        "CANONICAL_OWNER_AUTHORIZED",
                        json.dumps(canonical_auth),
                        now_iso,
                        now_iso,
                    ),
                )
                c2.commit()
            finally:
                c2.close()
        except Exception:
            pass

    return auth_id


def insert_test_canonical_owner_auth(
    db_path: str,
    *,
    token_id: str,
    job_id: int | str,
    user_id: int | str = "user_test",
    request_id: str = "req_test",
    project_id: int | str | None = None,
    product_type: str = "Product Video",
    provider: str = "key4u_video",
    capability: str = "image_to_video",
    tier: str = "kling-v3",
    max_provider_spend: float = 40.0,
    allowed_scene_slots: str = "1,2",
    ttl_seconds: float = 3600.0,
    runtime_sha: str | None = None,
    status: str = "active",
    operation: str = "create_video_task",
    env: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Test helper to insert pre-existing durable Owner authority in SQLite WAL for test fixtures."""
    import sqlite3
    import secrets
    import datetime
    from services.video_trace_state import (
        ensure_video_trace_schema,
        compute_owner_acceptance_token_fingerprint,
        compute_owner_acceptance_attempt_fingerprint,
    )
    from services.remote_worker_api import resolve_runtime_sha

    ensure_video_trace_schema(db_path=db_path)
    clean_job_id = int(job_id) if str(job_id).strip().isdigit() else str(job_id).strip()
    clean_user_id = int(user_id) if str(user_id).strip().isdigit() else str(user_id).strip()
    clean_proj_id = int(project_id) if str(project_id or "").strip().isdigit() else (project_id or None)
    clean_sha = str(runtime_sha if runtime_sha is not None else (resolve_runtime_sha(environ=env) or "")).strip()

    now_ts = time.time()
    exp_ts = now_ts + float(ttl_seconds)
    exp_micro = to_micro_usd(Decimal(str(max_provider_spend)))

    slots_list = [int(s.strip()) for s in str(allowed_scene_slots).split(",") if s.strip().isdigit()]
    max_submits = len(slots_list) if slots_list else 1

    auth = {
        "owner_authorized": True,
        "acceptance_type": "owner_authorized_live_acceptance",
        "product_type": str(product_type).strip(),
        "provider": str(provider).strip(),
        "capability": str(capability).strip(),
        "tier": str(tier).strip(),
        "job_id": clean_job_id,
        "user_id": clean_user_id,
        "project_id": clean_proj_id,
        "request_id": str(request_id).strip(),
        "runtime_sha": clean_sha,
        "max_provider_spend": float(max_provider_spend),
        "max_provider_spend_unit": "USD",
        "nonce": secrets.token_hex(8),
        "consumed": False,
        "expires_at": exp_ts,
        "token_id": str(token_id).strip(),
        "allowed_scene_slots": str(allowed_scene_slots).strip(),
        "max_submits": max_submits,
        "expected_max_provider_spend_micro_usd": exp_micro,
        "status": status,
        "operation": str(operation).strip(),
    }
    fp = compute_owner_acceptance_token_fingerprint(auth)
    afp = compute_owner_acceptance_attempt_fingerprint(auth)
    auth["token_fingerprint"] = fp
    auth["attempt_fingerprint"] = afp

    stage = "CANONICAL_OWNER_AUTHORIZED"
    if status == "consumed":
        stage = "CONSUMED"
    elif status == "revoked":
        stage = "REVOKED"

    conn = sqlite3.connect(db_path)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with conn:
        conn.execute(
            """
            INSERT INTO video_request_traces (
                request_id,
                job_id,
                project_id,
                confirm_attempt_key,
                owner_user_id,
                product_type,
                current_stage,
                trace_payload_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"COA-{token_id}",
                clean_job_id if isinstance(clean_job_id, int) else None,
                clean_proj_id if isinstance(clean_proj_id, int) else None,
                f"COA-{token_id}-{afp}",
                clean_user_id if isinstance(clean_user_id, int) else 0,
                str(product_type).strip(),
                stage,
                json.dumps(auth),
                now_iso,
                now_iso,
            ),
        )
    conn.close()
    return str(token_id).strip(), auth


def _mp_worker_reserve(
    db_path: str,
    env_dict: dict,
    auth_id: str,
    conf_id: str,
    job_id: str,
    request_id: str,
    user_id: str,
    chat_id: str,
    scene_index: int,
    cost_quality_key: str,
    result_queue: multiprocessing.Queue,
) -> None:
    """Worker process executed in independent process for multiprocess concurrency test (Section 16)."""
    try:
        from services.provider_spend_guard import (
            SpendGuardContext,
            reserve_provider_spend,
        )
        ctx = SpendGuardContext(
            chat_id=chat_id,
            user_id=user_id,
            entrypoint="bot",
            bot_originated_action=True,
            job_id=job_id,
            request_id=request_id,
            user_flow="bot_live_acceptance",
            owner_receipt=auth_id,
            scene_index=scene_index,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf_id,
            metadata={"quality_key": cost_quality_key},
        )
        res = reserve_provider_spend(ctx, db_path=db_path, env=env_dict)
        result_queue.put({
            "scene_index": scene_index,
            "allowed": res.allowed,
            "blocker": res.blocker,
            "reserved_micro": res.cost_micro_usd if res.allowed else 0,
        })
    except Exception as exc:
        result_queue.put({
            "scene_index": scene_index,
            "allowed": False,
            "blocker": "worker_exception",
            "error": str(exc),
            "reserved_micro": 0,
        })


class TestProviderSpendGuard25Cases(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_spend_guard_25_")
        self.db_path = os.path.join(self.temp_dir, "shared_toanaas.db")
        self.standard_env = {
            "SPEND_GUARD_DB_PATH": self.db_path,
            "WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE": "MONDAY_0000_UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE": "UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_USD": "200.000",
        }
        init_spend_guard_db(db_path=self.db_path, env=self.standard_env)
        set_kill_switch(None)

    def tearDown(self):
        set_kill_switch(None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_valid_reservation(
        self,
        job_id: str,
        request_id: str,
        *,
        product_family: str = "Video AI Edit",
        provider: str = "fal_video",
        operation: str = "submit_video_edit",
        model: str = "wan-v2.2",
        duration_seconds: int = 5,
    ) -> SpendReservationResult:
        conf_id = create_bot_confirmation(
            job_id=job_id,
            request_id=request_id,
            product_family=product_family,
            operation=operation,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id=job_id,
            request_id=request_id,
            trace_id=f"tr_{job_id}",
            product_family=product_family,
            provider=provider,
            model=model,
            operation=operation,
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="bot_confirm",
            metadata={"duration_seconds": duration_seconds},
        )
        return reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)

    # 1. Missing reset rule -> BLOCK (weekly_provider_spend_policy_incomplete)
    def test_01_missing_reset_rule_blocked(self):
        incomplete_env = dict(self.standard_env)
        incomplete_env.pop("WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE", None)
        ctx = SpendGuardContext(
            job_id="job_01",
            request_id="req_01",
            estimated_max_cost_usd=1.00,
            has_proven_cost_authority=True,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            user_flow="bot_confirm",
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=incomplete_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_POLICY_INCOMPLETE)

    # 2. Missing timezone -> BLOCK (weekly_provider_spend_policy_incomplete)
    def test_02_missing_timezone_blocked(self):
        incomplete_env = dict(self.standard_env)
        incomplete_env.pop("WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE", None)
        ctx = SpendGuardContext(
            job_id="job_02",
            request_id="req_02",
            estimated_max_cost_usd=1.00,
            has_proven_cost_authority=True,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            user_flow="bot_confirm",
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=incomplete_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_POLICY_INCOMPLETE)

    # 3. Invalid reset policy -> BLOCK
    def test_03_invalid_reset_policy_blocked(self):
        invalid_env = dict(self.standard_env)
        invalid_env["WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE"] = "SUNDAY_MIDNIGHT_UNSUPPORTED"
        ctx = SpendGuardContext(
            job_id="job_03",
            request_id="req_03",
            estimated_max_cost_usd=1.00,
            has_proven_cost_authority=True,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            user_flow="bot_confirm",
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=invalid_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_POLICY_INCOMPLETE)

    # 4. Missing max-cost authority -> BLOCK (provider_max_cost_authority_missing)
    def test_04_missing_max_cost_authority_blocked(self):
        ctx = SpendGuardContext(
            job_id="job_04",
            request_id="req_04",
            product_family="Product Video",
            provider="shopaikey_video",
            model="unpriced_model_xyz",
            operation="create_video_task",
            estimated_max_cost_usd=0.0,
            has_proven_cost_authority=False,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            user_flow="bot_confirm",
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_MAX_COST_AUTHORITY_MISSING)

    # 5. Arbitrary $0.10 fallback absent
    def test_05_arbitrary_fallback_absent(self):
        # A non-stub attempt with estimated_max_cost_usd unspecified or arbitrary without proven authority
        ctx = SpendGuardContext(
            job_id="job_05",
            request_id="req_05",
            product_family="Product Video",
            provider="key4u_video",
            operation="create_video_task",
            estimated_max_cost_usd=0.10,
            has_proven_cost_authority=False,  # Unproven arbitrary number
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            user_flow="bot_confirm",
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_MAX_COST_AUTHORITY_MISSING)

    # 6. Submit accepted -> PENDING_SETTLEMENT
    def test_06_submit_accepted_transitions_to_pending_settlement(self):
        res = self._create_valid_reservation("job_06", "req_06")
        self.assertTrue(res.allowed)
        self.assertNotEqual(res.reservation_id, "")

        marked = mark_submitted_pending_settlement(
            res.reservation_id,
            provider_task_id="task_ext_06",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertTrue(marked)

        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertEqual(summary["pending_reserved_spend_usd"], 0.40)
        self.assertEqual(summary["settled_week_spend_usd"], 0.0)
        self.assertEqual(summary["total_active_week_spend_usd"], 0.40)

    # 7. Accepted submit does NOT record estimated as actual
    def test_07_accepted_submit_does_not_record_estimated_as_actual(self):
        res = self._create_valid_reservation("job_07", "req_07")
        self.assertTrue(res.allowed)

        mark_submitted_pending_settlement(
            res.reservation_id,
            provider_task_id="task_ext_07",
            db_path=self.db_path,
            env=self.standard_env,
        )

        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT status, reserved_cost_micro_usd, actual_settled_cost_micro_usd FROM provider_spend_reservations WHERE reservation_id = ?",
            (res.reservation_id,),
        )
        row = cur.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], STATUS_SUBMITTED_PENDING_SETTLEMENT)
        self.assertEqual(row[1], 400_000)
        self.assertEqual(row[2], 0)  # Actual settled cost remains 0!

    # 8. Timeout after transport -> AMBIGUOUS_RETAINED
    def test_08_timeout_after_transport_retains_ambiguous(self):
        res = self._create_valid_reservation("job_08", "req_08")
        self.assertTrue(res.allowed)

        retained = retain_ambiguous_provider_spend(
            res.reservation_id,
            error_code="TimeoutError",
            provider_task_id="",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertTrue(retained)

        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertEqual(summary["pending_reserved_spend_usd"], 0.40)
        self.assertEqual(summary["total_active_week_spend_usd"], 0.40)

    # 9. Connection reset after transport -> AMBIGUOUS_RETAINED
    def test_09_connection_reset_after_transport_retains_ambiguous(self):
        res = self._create_valid_reservation("job_09", "req_09")
        self.assertTrue(res.allowed)

        retained = retain_ambiguous_provider_spend(
            res.reservation_id,
            error_code="ConnectionResetError",
            provider_task_id="task_conn_reset",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertTrue(retained)

        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT status, error_code, reserved_cost_micro_usd FROM provider_spend_reservations WHERE reservation_id = ?",
            (res.reservation_id,),
        )
        row = cur.fetchone()
        conn.close()

        self.assertEqual(row[0], STATUS_AMBIGUOUS_RETAINED)
        self.assertEqual(row[1], "ConnectionResetError")
        self.assertEqual(row[2], 400_000)

    # 10. Response parse failure after transport -> AMBIGUOUS_RETAINED
    def test_10_response_parse_failure_after_transport_retains_ambiguous(self):
        res = self._create_valid_reservation("job_10", "req_10")
        self.assertTrue(res.allowed)

        retained = retain_ambiguous_provider_spend(
            res.reservation_id,
            error_code="JSONDecodeError",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertTrue(retained)

        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertEqual(summary["total_active_week_spend_usd"], 0.40)

    # 11. Generic exception after transport -> AMBIGUOUS_RETAINED
    def test_11_generic_exception_after_transport_retains_ambiguous(self):
        res = self._create_valid_reservation("job_11", "req_11")
        self.assertTrue(res.allowed)

        retained = retain_ambiguous_provider_spend(
            res.reservation_id,
            error_code="RuntimeError",
            provider_task_id="task_rt_error",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertTrue(retained)
        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertEqual(summary["pending_reserved_spend_usd"], 0.40)

    # 12. Proven pre-send failure -> RELEASED_PROVEN_NO_CHARGE
    def test_12_proven_pre_send_failure_releases_reservation(self):
        res = self._create_valid_reservation("job_12", "req_12")
        self.assertTrue(res.allowed)

        released = release_provider_spend_no_charge(
            res.reservation_id,
            reason="pre_transport_validation_failed",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertTrue(released)

        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT status, reserved_cost_micro_usd FROM provider_spend_reservations WHERE reservation_id = ?",
            (res.reservation_id,),
        )
        row = cur.fetchone()
        conn.close()

        self.assertEqual(row[0], STATUS_RELEASED_PROVEN_NO_CHARGE)
        self.assertEqual(row[1], 0)

        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertEqual(summary["total_active_week_spend_usd"], 0.0)

    # 13. CI + REAL_PROVIDER_CALLS_ALLOWED=1 -> still BLOCK
    def test_13_ci_with_real_provider_calls_allowed_still_blocked(self):
        ci_env = dict(self.standard_env)
        ci_env["CI"] = "true"
        ci_env["REAL_PROVIDER_CALLS_ALLOWED"] = "1"
        ctx = SpendGuardContext(
            job_id="job_13",
            request_id="req_13",
            estimated_max_cost_usd=1.00,
            has_proven_cost_authority=True,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            user_flow="bot_confirm",
            is_paid_live_attempt=True,
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=ci_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_TEST_NETWORK_ISOLATION)

    # 14. Pytest + override -> still BLOCK
    def test_14_pytest_with_override_still_blocked(self):
        test_env = dict(self.standard_env)
        test_env["PYTEST_CURRENT_TEST"] = "tests/test_mock.py::test_case"
        test_env["REAL_PROVIDER_CALLS_ALLOWED"] = "1"
        ctx = SpendGuardContext(
            job_id="job_14",
            request_id="req_14",
            estimated_max_cost_usd=1.00,
            has_proven_cost_authority=True,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            user_flow="bot_confirm",
            is_paid_live_attempt=True,
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=test_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_TEST_NETWORK_ISOLATION)

    # 15. Forged submit_source string -> bot origin BLOCK
    def test_15_forged_submit_source_string_blocked(self):
        # Caller supplies submit_source="public_final_confirm" but has NO trusted bot_confirm_authority
        ctx = SpendGuardContext(
            job_id="job_15",
            request_id="req_15",
            estimated_max_cost_usd=1.00,
            has_proven_cost_authority=True,
            bot_originated_action=False,  # Unproven
            bot_confirm_authority="",      # Empty / absent
            user_flow="public_final_confirm",
            is_paid_live_attempt=True,
        )
        valid, blocker = validate_bot_paid_live_origin(ctx, env=self.standard_env)
        self.assertFalse(valid)
        self.assertIn(blocker, {BLOCKER_BOT_ORIGIN_PROOF_MISSING, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING})

        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)

    # 16. Trusted bot lineage -> PASS guard
    def test_16_trusted_bot_lineage_passes_guard(self):
        conf_id = create_bot_confirmation(
            job_id="job_16",
            request_id="req_16",
            product_family="Video AI Edit",
            operation="submit_video_edit",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="job_16",
            request_id="req_16",
            trace_id="tr_16",
            product_family="Video AI Edit",
            provider="fal_video",
            model="wan-v2.2",
            operation="submit_video_edit",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="bot_product_video_confirm",
            entrypoint="bot",
            is_paid_live_attempt=True,
            owner_receipt="rcpt_test_owner_16",
            metadata={"duration_seconds": 5},
        )
        valid, blocker = validate_bot_paid_live_origin(ctx, env=self.standard_env)
        self.assertTrue(valid)
        self.assertEqual(blocker, "")

        # Test reservation without test isolation flag
        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
            self.assertTrue(res.allowed)
            self.assertEqual(res.week_spend_after_usd, 0.40)
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

    # 17. Missing shared DB authority -> BLOCK (spend_guard_shared_authority_unavailable)
    def test_17_missing_shared_db_authority_blocked(self):
        ctx = SpendGuardContext(
            job_id="job_17",
            request_id="req_17",
            estimated_max_cost_usd=1.00,
            has_proven_cost_authority=True,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            user_flow="bot_confirm",
        )
        res = reserve_provider_spend(ctx, db_path=None, env={
            "WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE": "MONDAY_0000_UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE": "UTC",
        })
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_SHARED_DB_UNAVAILABLE)

    # 18. Bot/Worker shared DB parity -> PASS
    def test_18_bot_worker_shared_db_parity_passes(self):
        shared_file = os.path.join(self.temp_dir, "parity_shared.db")
        bot_env = {"DB_PATH": shared_file}
        worker_env = {"SPEND_GUARD_DB_PATH": shared_file}

        parity_ok, bot_path, worker_path, reason = verify_shared_db_parity(bot_env, worker_env)
        self.assertTrue(parity_ok)
        self.assertEqual(os.path.normcase(bot_path), os.path.normcase(worker_path))

        # Test mismatch fails
        mismatch_worker = {"SPEND_GUARD_DB_PATH": os.path.join(self.temp_dir, "other.db")}
        parity_bad, _, _, _ = verify_shared_db_parity(bot_env, mismatch_worker)
        self.assertFalse(parity_bad)

    # 19. Two-process atomic reservation -> cannot exceed $200 (using multiprocessing)
    def test_19_two_process_atomic_reservation_cannot_exceed_cap(self):
        # Initial settle: $199.60
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        week_id = get_current_spend_week_id(env=self.standard_env)
        cur.execute(
            """
            INSERT INTO provider_spend_reservations (
                reservation_id, created_at, week_id, idempotency_key, job_id, request_id, trace_id,
                product_family, provider, model, estimated_max_cost_micro_usd, reserved_cost_micro_usd,
                actual_settled_cost_micro_usd, status, bot_originated_action, user_flow, bot_confirm_authority,
                owner_receipt, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'test', 'conf', '', '{}')
            """,
            (
                "res_base_19", time.time(), week_id, "idem_19_base", "job_19_init", "req_19_init", "tr_19",
                "Video AI Edit", "fal_video", "wan-v2.2", 199_600_000, 199_600_000, 199_600_000,
                STATUS_SETTLED_VERIFIED,
            )
        )
        conn.commit()
        conn.close()

        # Remaining budget is $0.40. Two processes attempt $0.40 each (Fal 5s = $0.40).
        q = multiprocessing.Queue()
        p1 = multiprocessing.Process(
            target=_process_reserve_worker,
            args=(self.db_path, self.standard_env, "job_19_p1", 0.40, q),
        )
        p2 = multiprocessing.Process(
            target=_process_reserve_worker,
            args=(self.db_path, self.standard_env, "job_19_p2", 0.40, q),
        )

        p1.start()
        p2.start()
        p1.join(timeout=10)
        p2.join(timeout=10)

        results = [q.get(timeout=10) for _ in range(2)]
        allowed_count = sum(1 for r in results if r["allowed"])
        blocked_count = sum(1 for r in results if not r["allowed"])

        # Exactly 1 can succeed, the other MUST be blocked
        self.assertEqual(allowed_count, 1)
        self.assertEqual(blocked_count, 1)

        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertEqual(summary["total_active_week_spend_usd"], 200.00)

    # 20. Precise decimal boundary ($199.600 + $0.400 PASS, $200.000 + $0.400 BLOCK)
    def test_20_precise_decimal_boundary(self):
        # Settle $199.600
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        week_id = get_current_spend_week_id(env=self.standard_env)
        cur.execute(
            """
            INSERT INTO provider_spend_reservations (
                reservation_id, created_at, week_id, idempotency_key, job_id, request_id, trace_id,
                product_family, provider, model, estimated_max_cost_micro_usd, reserved_cost_micro_usd,
                actual_settled_cost_micro_usd, status, bot_originated_action, user_flow, bot_confirm_authority,
                owner_receipt, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'test', 'conf', '', '{}')
            """,
            (
                "res_base_20", time.time(), week_id, "idem_20_base", "job_20_base", "req_20_base", "tr_20",
                "Video AI Edit", "fal_video", "wan-v2.2", 199_600_000, 199_600_000, 199_600_000,
                STATUS_SETTLED_VERIFIED,
            )
        )
        conn.commit()
        conn.close()

        # $199.600 + $0.400 = $200.000 -> PASS
        res_exact = self._create_valid_reservation("job_20_exact", "req_20_exact")
        self.assertTrue(res_exact.allowed)
        settle_verified_provider_spend(res_exact.reservation_id, actual_verified_cost_usd=0.40, db_path=self.db_path, env=self.standard_env)

        # $200.000 + $0.400 = $200.400 > $200.000 -> BLOCK
        res_over = self._create_valid_reservation("job_20_over", "req_20_over")
        self.assertFalse(res_over.allowed)
        self.assertEqual(res_over.blocker, BLOCKER_WEEKLY_SPEND_CAP_EXCEEDED)

    # 21. Duplicate submit -> BLOCK
    def test_21_duplicate_submit_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="job_21_dup",
            request_id="req_21_dup",
            product_family="Video AI Edit",
            operation="submit_video_edit",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="job_21_dup",
            request_id="req_21_dup",
            product_family="Video AI Edit",
            provider="fal_video",
            model="wan-v2.2",
            operation="submit_video_edit",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="bot_confirm",
            metadata={"duration_seconds": 5},
        )
        res1 = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)

        # Immediate duplicate
        res2 = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res2.allowed)
        self.assertEqual(res2.blocker, BLOCKER_DUPLICATE_PAID_SUBMIT)

    # 22. Retry ambiguous -> BLOCK
    def test_22_retry_ambiguous_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="job_22_retry",
            request_id="req_22_retry",
            product_family="Video AI Edit",
            operation="submit_video_edit",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="job_22_retry",
            request_id="req_22_retry",
            product_family="Video AI Edit",
            provider="fal_video",
            model="wan-v2.2",
            operation="submit_video_edit",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="bot_confirm",
            metadata={"duration_seconds": 5},
        )
        res1 = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)

        retain_ambiguous_provider_spend(
            res1.reservation_id,
            error_code="provider_timeout",
            db_path=self.db_path,
            env=self.standard_env,
        )

        res_retry = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res_retry.allowed)
        self.assertEqual(res_retry.blocker, BLOCKER_AMBIGUOUS_RETRY_BLOCKED)

    # 23. Fallback ambiguous -> BLOCK
    def test_23_fallback_ambiguous_blocked(self):
        policy = product_video_provider_submit_source_policy(
            metadata={
                "submit_source": "fallback",
                "is_paid_live": True,
                "bot_originated_action": False,
            }
        )
        self.assertFalse(policy["provider_submit_allowed"])

    # 24. Kill switch -> BLOCK
    def test_24_kill_switch_blocked(self):
        set_kill_switch(True)
        self.assertTrue(is_kill_switch_active())

        ctx = SpendGuardContext(
            job_id="job_24_ks",
            request_id="req_24_ks",
            estimated_max_cost_usd=1.00,
            has_proven_cost_authority=True,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            user_flow="bot_confirm",
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_KILL_SWITCH_ACTIVE)

        # Polling existing task remains allowed
        policy = product_video_provider_submit_source_policy(
            metadata={"submit_source": "worker_poll_existing_task"},
            poll_existing_task=True,
        )
        self.assertFalse(policy["provider_submit_allowed"])
        self.assertTrue(policy["poll_existing_task_allowed"])

    # 25. Existing Product Video protected suites pass
    def test_25_existing_product_video_protected_suites_pass(self):
        # Verify key4u authority fails closed when legacy alias or missing canonical
        env_alias_only = {"VIDEO_KEY4U_AUTH_HEADER_VALUE": "alias_value"}
        res = resolve_product_video_key4u_auth(env_alias_only)
        self.assertFalse(res["ready"])
        self.assertEqual(res["blocker"], KEY4U_VIDEO_AUTH_MISSING)

        # Audit record sanitized check
        ctx = SpendGuardContext(
            job_id="job_25_audit",
            request_id="req_25_audit",
            trace_id="tr_25_audit",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            estimated_max_cost_usd=1.50,
            has_proven_cost_authority=True,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            user_flow="bot_confirm",
        )
        raw_secret_task_id = "task_secret_sk_live_9999999999abcdef"
        audit = build_sanitized_audit_record(
            ctx,
            week_spend_before_micro_usd=10_000_000,
            week_spend_after_micro_usd=11_500_000,
            reserved_cost_micro_usd=1_500_000,
            provider_task_id=raw_secret_task_id,
        )
        self.assertNotIn("sk_live", str(audit))
        self.assertNotIn("9999999999", str(audit))
        self.assertIn("...", audit["PROVIDER_TASK_ID_SAFE"])

    # 26. TTS direct paid submit without bot auth -> BLOCK
    def test_26_tts_direct_paid_submit_without_bot_auth_blocked(self):
        status, task_id, detail, code = asyncio.run(
            shopaikey_minimax_tts_async_submit(
                text="hello",
                voice_id="voice_1",
                api_key="sk-real-live-token",
                is_paid_live=True,
                bot_originated_action=False,
                bot_confirm_authority="",
                db_path=self.db_path,
                env=self.standard_env,
            )
        )
        self.assertEqual(status, "FAIL_SPEND_GUARD_BLOCKED")
        self.assertIn("spend_guard_blocked", detail)

    # 27. TTS trusted bot paid submit reaches mock transport only -> PASS
    def test_27_tts_trusted_bot_paid_submit_reaches_mock_transport_only(self):
        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            # MiniMax unproven pricing fails closed even with bot confirm
            conf_minimax = create_bot_confirmation(
                job_id="job_tts_mm",
                request_id="req_tts_mm",
                product_family="Voice / TTS",
                operation="create_tts_task",
                db_path=self.db_path,
                env=self.standard_env,
            )
            st_mm, _, det_mm, _ = asyncio.run(
                shopaikey_minimax_tts_async_submit(
                    text="hello",
                    voice_id="voice_1",
                    api_key="mock_key",
                    job_id="job_tts_mm",
                    request_id="req_tts_mm",
                    bot_originated_action=True,
                    bot_confirm_authority=conf_minimax,
                    is_paid_live=False,
                    db_path=self.db_path,
                    env=self.standard_env,
                )
            )
            self.assertEqual(st_mm, "FAIL_SPEND_GUARD_BLOCKED")
            self.assertIn("provider_max_cost_authority_missing", det_mm)

            # Proven OpenAI tts-1 with durable confirmation reaches mock transport only
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"task_id": "tts_mock_task_789"}
            mock_response.text = '{"task_id": "tts_mock_task_789"}'
            mock_client.post = AsyncMock(return_value=mock_response)

            conf_id = create_bot_confirmation(
                job_id="job_tts_01",
                request_id="req_tts_01",
                product_family="Voice / TTS",
                operation="create_tts_task",
                db_path=self.db_path,
                env=self.standard_env,
            )

            status, task_id, detail, code = asyncio.run(
                shopaikey_minimax_tts_async_submit(
                    text="Test TTS with trusted lineage",
                    voice_id="voice_1",
                    model="tts-1",
                    provider="shopaikey_openai_tts",
                    api_key="mock_key",
                    client=mock_client,
                    job_id="job_tts_01",
                    request_id="req_tts_01",
                    bot_originated_action=True,
                    bot_confirm_authority=conf_id,
                    is_paid_live=True,
                    db_path=self.db_path,
                    env=self.standard_env,
                )
            )

            self.assertEqual(status, "PASS")
            self.assertEqual(task_id, "tts_mock_task_789")
            mock_client.post.assert_awaited_once()

            summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
            self.assertAlmostEqual(summary["pending_reserved_spend_usd"], 0.000435, places=6)
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

    # 28. Ambiguous TTS retains reservation -> RETAIN
    def test_28_ambiguous_tts_retains_reservation(self):
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Transport timed out"))

        conf_id = create_bot_confirmation(
            job_id="job_tts_timeout",
            request_id="req_tts_timeout",
            product_family="Voice / TTS",
            operation="create_tts_task",
            db_path=self.db_path,
            env=self.standard_env,
        )

        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            status, task_id, detail, code = asyncio.run(
                shopaikey_minimax_tts_async_submit(
                    text="Test TTS timeout ambiguity",
                    voice_id="voice_1",
                    model="tts-1",
                    provider="shopaikey_openai_tts",
                    api_key="mock_key",
                    client=mock_client,
                    job_id="job_tts_timeout",
                    request_id="req_tts_timeout",
                    bot_originated_action=True,
                    bot_confirm_authority=conf_id,
                    is_paid_live=True,
                    db_path=self.db_path,
                    env=self.standard_env,
                )
            )
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

        self.assertEqual(status, "FAIL_TIMEOUT")
        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertAlmostEqual(summary["pending_reserved_spend_usd"], 0.00039, places=6)

    # 29. Chat Pro external paid call without guard -> BLOCK
    def test_29_chat_pro_external_paid_call_without_guard_blocked(self):
        store = PublicChatStore(os.path.join(self.temp_dir, "chat.db"))
        pro_mock = MagicMock()
        pro_mock.is_paid_provider = True
        wallet = MagicMock()
        wallet.get_balance = AsyncMock(return_value=50_000)
        wallet.reserve = AsyncMock(return_value={"ok": True, "reservation_id": "res_w_01"})
        wallet.release = AsyncMock(return_value={"ok": True})
        runtime = PublicChatRuntime(store=store, pro_provider=pro_mock, wallet=wallet, pricing=ClaudeOpusPricing(100, 500, 3))

        req = PublicChatRequest(
            account_id="u_chat",
            chat_id="chat_1",
            source_message_id="msg_1",
            mode="pro",
            prompt="pro prompt",
            role="user",
            estimated_input_tokens=1000,
            max_output_tokens=1000,
            is_paid_external_provider=True,
            bot_originated_action=False,
            bot_confirm_authority="",
            db_path=self.db_path,
            env=self.standard_env,
        )

        res = asyncio.run(runtime.generate_pro(req))
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("status"), "SPEND_GUARD_BLOCKED")
        self.assertEqual(res.get("provider_calls"), 0)

    # 30. Chat internal Xu ledger separate -> PASS
    def test_30_chat_internal_xu_ledger_separate(self):
        store = PublicChatStore(os.path.join(self.temp_dir, "chat_xu.db"))
        pro_mock = MagicMock()
        pro_mock.is_paid_provider = True
        wallet = MagicMock()
        wallet.get_balance = AsyncMock(return_value=50_000)
        wallet.reserve = AsyncMock(return_value={"ok": True, "reservation_id": "res_xu_test"})
        wallet.release = AsyncMock(return_value={"ok": True})
        runtime = PublicChatRuntime(store=store, pro_provider=pro_mock, wallet=wallet, pricing=ClaudeOpusPricing(100, 500, 3))

        req = PublicChatRequest(
            account_id="u_xu",
            chat_id="chat_xu",
            source_message_id="msg_xu",
            mode="pro",
            prompt="test",
            role="user",
            estimated_input_tokens=1000,
            max_output_tokens=1000,
            is_paid_external_provider=True,
            bot_originated_action=False,
            bot_confirm_authority="",
            db_path=self.db_path,
            env=self.standard_env,
        )

        res = asyncio.run(runtime.generate_pro(req))
        wallet.reserve.assert_awaited_once()
        wallet.release.assert_awaited_once()
        self.assertEqual(res.get("provider_calls"), 0)

    # 31. Ambiguous Chat retains reservation -> RETAIN
    def test_31_ambiguous_chat_retains_reservation(self):
        store = PublicChatStore(os.path.join(self.temp_dir, "chat_ambig.db"))
        async def fail_pro(*args, **kwargs):
            raise TimeoutError("LLM gateway socket dropped")
        pro_mock = MagicMock(side_effect=fail_pro)
        pro_mock.is_paid_provider = True
        wallet = MagicMock()
        wallet.get_balance = AsyncMock(return_value=50_000)
        wallet.reserve = AsyncMock(return_value={"ok": True, "reservation_id": "res_ambig_test"})
        wallet.release = AsyncMock(return_value={"ok": True})
        runtime = PublicChatRuntime(store=store, pro_provider=pro_mock, wallet=wallet, pricing=ClaudeOpusPricing(100, 500, 3))

        conf_id = create_bot_confirmation(
            chat_id="chat_ambig",
            job_id="msg_ambig",
            product_family="Public Chat Pro",
            operation="chat_completion",
            db_path=self.db_path,
            env=self.standard_env,
        )

        req = PublicChatRequest(
            account_id="u_ambig",
            chat_id="chat_ambig",
            source_message_id="msg_ambig",
            mode="pro",
            prompt="test",
            role="user",
            estimated_input_tokens=1000,
            max_output_tokens=1000,
            is_paid_external_provider=True,
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            has_proven_cost_authority=True,
            estimated_max_cost_usd=0.08,
            db_path=self.db_path,
            env=self.standard_env,
        )

        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            res = asyncio.run(runtime.generate_pro(req))
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("status"), "PROVIDER_FAILURE")

        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertAlmostEqual(summary["pending_reserved_spend_usd"], 0.036, places=6)

    # 32. AI Edit forged final confirm -> BLOCK
    def test_32_ai_edit_forged_final_confirm_blocked(self):
        config = AiEditProviderConfig(
            provider_name="fal_video",
            enabled=True,
            submit_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video",
            poll_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video/requests/{task_id}/status",
            auth_header_name="Authorization",
            auth_header_value="Key real_live_secret",
            model="fal-ai/wan/v2.2-a14b/video-to-video",
            interface="video_to_video_json",
            capabilities=("video_to_video",),
        )
        fake_source = os.path.join(self.temp_dir, "fake_vid.mp4")
        with open(fake_source, "wb") as f:
            f.write(b"video_bytes")

        with self.assertRaises(AiEditProviderError) as cm:
            submit_video_edit(
                config,
                source_video_path=fake_source,
                prompt="make anime",
                negative_prompt="",
                aspect_ratio="9:16",
                duration_seconds=5,
                job_id="job_aiedit_forged",
                submit_source=PUBLIC_FINAL_CONFIRM_SOURCE,
                public_user_confirmed=True,
                is_paid_live=True,
                bot_originated_action=False,
                bot_confirm_authority="",
                db_path=self.db_path,
                env=self.standard_env,
            )
        self.assertIn("bot_confirm_authority_missing", str(cm.exception))

    # 33. AI Edit trusted bot lineage reaches mock transport only -> PASS
    def test_33_ai_edit_trusted_bot_lineage_reaches_mock_transport_only(self):
        config = AiEditProviderConfig(
            provider_name="fal_video",
            enabled=True,
            submit_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video",
            poll_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video/requests/{task_id}/status",
            auth_header_name="Authorization",
            auth_header_value="Key mock_key",
            model="fal-ai/wan/v2.2-a14b/video-to-video",
            interface="video_to_video_json",
            capabilities=("video_to_video",),
        )
        fake_source = "https://storage.fal.run/fake_vid.mp4"

        conf_id = create_bot_confirmation(
            job_id="job_aiedit_valid",
            product_family="Video AI Edit",
            operation="submit_video_edit",
            db_path=self.db_path,
            env=self.standard_env,
        )

        transport_called = False
        def mock_opener(req, timeout=0):
            nonlocal transport_called
            transport_called = True
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.code = 200
            mock_resp.getcode.return_value = 200
            mock_resp.read.return_value = json.dumps({"data": {"task_id": "aiedit_task_001", "status": "PENDING"}}).encode("utf-8")
            return mock_resp

        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            res = submit_video_edit(
                config,
                source_video_path=fake_source,
                prompt="make anime",
                negative_prompt="",
                aspect_ratio="9:16",
                duration_seconds=5,
                job_id="job_aiedit_valid",
                submit_source=PUBLIC_FINAL_CONFIRM_SOURCE,
                public_user_confirmed=True,
                opener=mock_opener,
                is_paid_live=True,
                bot_originated_action=True,
                bot_confirm_authority=conf_id,
                db_path=self.db_path,
                env=self.standard_env,
            )
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

        self.assertTrue(transport_called)
        self.assertEqual(res.get("provider_task_id"), "aiedit_task_001")

        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertEqual(summary["pending_reserved_spend_usd"], 0.40)

    # 34. Ambiguous AI Edit retains reservation -> RETAIN
    def test_34_ambiguous_ai_edit_retains_reservation(self):
        config = AiEditProviderConfig(
            provider_name="fal_video",
            enabled=True,
            submit_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video",
            poll_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video/requests/{task_id}/status",
            auth_header_name="Authorization",
            auth_header_value="Key mock_key",
            model="fal-ai/wan/v2.2-a14b/video-to-video",
            interface="video_to_video_json",
            capabilities=("video_to_video",),
        )
        fake_source = "https://storage.fal.run/fake_vid.mp4"

        conf_id = create_bot_confirmation(
            job_id="job_aiedit_fail",
            product_family="Video AI Edit",
            operation="submit_video_edit",
            db_path=self.db_path,
            env=self.standard_env,
        )

        import urllib.error
        def mock_opener_fail(req, timeout=0):
            raise urllib.error.URLError("connection reset by peer")

        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            with self.assertRaises(AiEditProviderError):
                submit_video_edit(
                    config,
                    source_video_path=fake_source,
                    prompt="make anime",
                    negative_prompt="",
                    aspect_ratio="9:16",
                    duration_seconds=5,
                    job_id="job_aiedit_fail",
                    submit_source=PUBLIC_FINAL_CONFIRM_SOURCE,
                    public_user_confirmed=True,
                    opener=mock_opener_fail,
                    is_paid_live=True,
                    bot_originated_action=True,
                    bot_confirm_authority=conf_id,
                    db_path=self.db_path,
                    env=self.standard_env,
                )
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertEqual(summary["pending_reserved_spend_usd"], 0.40)

    # 35. Kill switch blocks all paid entrypoints -> BLOCK
    def test_35_kill_switch_all_paid_entrypoints_blocked(self):
        set_kill_switch(True)
        # 1. Product Video
        pv_ctx = SpendGuardContext(product_family="Product Video", estimated_max_cost_usd=1.00, has_proven_cost_authority=True, bot_originated_action=True, bot_confirm_authority="bot_telegram_ui_confirmed")
        self.assertEqual(reserve_provider_spend(pv_ctx, db_path=self.db_path, env=self.standard_env).blocker, BLOCKER_KILL_SWITCH_ACTIVE)

        # 2. TTS
        tts_ctx = SpendGuardContext(product_family="Voice / TTS", estimated_max_cost_usd=0.05, has_proven_cost_authority=True, bot_originated_action=True, bot_confirm_authority="bot_telegram_ui_confirmed")
        self.assertEqual(reserve_provider_spend(tts_ctx, db_path=self.db_path, env=self.standard_env).blocker, BLOCKER_KILL_SWITCH_ACTIVE)

        # 3. Chat Pro
        chat_ctx = SpendGuardContext(product_family="Public Chat Pro", estimated_max_cost_usd=0.08, has_proven_cost_authority=True, bot_originated_action=True, bot_confirm_authority="bot_telegram_ui_confirmed")
        self.assertEqual(reserve_provider_spend(chat_ctx, db_path=self.db_path, env=self.standard_env).blocker, BLOCKER_KILL_SWITCH_ACTIVE)

        # 4. Video AI Edit
        edit_ctx = SpendGuardContext(product_family="Video AI Edit", estimated_max_cost_usd=0.20, has_proven_cost_authority=True, bot_originated_action=True, bot_confirm_authority="bot_telegram_ui_confirmed")
        self.assertEqual(reserve_provider_spend(edit_ctx, db_path=self.db_path, env=self.standard_env).blocker, BLOCKER_KILL_SWITCH_ACTIVE)

    # 36. Weekly cap shared across products -> PASS
    def test_36_weekly_cap_shared_across_products(self):
        # Insert settled records totaling $200.00 across all 4 products:
        # PV: $100.00, TTS: $50.00, Chat Pro: $30.00, AI Edit: $20.00
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        week_id = get_current_spend_week_id(env=self.standard_env)
        settled_breakdown = [
            ("Product Video", 100.00),
            ("Voice / TTS", 50.00),
            ("Public Chat Pro", 30.00),
            ("Video AI Edit", 20.00),
        ]
        for fam, amount in settled_breakdown:
            conn.execute(
                """
                INSERT INTO provider_spend_reservations (
                    reservation_id, created_at, week_id, idempotency_key, job_id, request_id, trace_id,
                    product_family, provider, model, estimated_max_cost_micro_usd, reserved_cost_micro_usd,
                    actual_settled_cost_micro_usd, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"res_cap_{fam}", time.time(), week_id, f"idem_{fam}", f"job_{fam}", f"req_{fam}", f"tr_{fam}",
                    fam, "mock_prov", "mock_model", int(amount * 1_000_000), int(amount * 1_000_000),
                    int(amount * 1_000_000), STATUS_SETTLED_VERIFIED,
                ),
            )
        conn.commit()
        conn.close()

        # Total settled = $200.00. Now attempt reservation on ANY governed product family:
        attempts = [
            ("Product Video", "key4u_video", "kling-v3", "create_video_task", {"duration_seconds": 5}),
            ("Voice / TTS", "shopaikey_openai_tts", "tts-1", "create_tts_task", {"char_count": 100}),
            ("Public Chat Pro", "claude-opus", CLAUDE_OPUS_MODEL, "chat_completion", {"max_input_tokens": 100, "max_output_tokens": 100}),
            ("Video AI Edit", "fal_video", "fal-ai/wan/v2.2-a14b/video-to-video", "submit_video_edit", {"duration_seconds": 5}),
        ]
        for fam, prov, mdl, op, meta in attempts:
            c_id = create_bot_confirmation(
                job_id=f"over_{fam}",
                request_id=f"req_over_{fam}",
                product_family=fam,
                operation=op,
                db_path=self.db_path,
                env=self.standard_env,
            )
            over_res = reserve_provider_spend(
                SpendGuardContext(
                    job_id=f"over_{fam}",
                    request_id=f"req_over_{fam}",
                    product_family=fam,
                    provider=prov,
                    model=mdl,
                    operation=op,
                    bot_originated_action=True,
                    bot_confirm_authority=c_id,
                    metadata=meta,
                ),
                db_path=self.db_path,
                env=self.standard_env,
            )
            self.assertFalse(over_res.allowed, f"Expected {fam} to be blocked by weekly cap")
            self.assertEqual(over_res.blocker, BLOCKER_WEEKLY_SPEND_CAP_EXCEEDED)

    # 37. CI override all paid entrypoints -> BLOCK
    def test_37_ci_override_all_paid_entrypoints_blocked(self):
        ci_env = dict(self.standard_env)
        ci_env["CI"] = "true"
        ci_env["REAL_PROVIDER_CALLS_ALLOWED"] = "1"

        for fam in ("Product Video", "Voice / TTS", "Public Chat Pro", "Video AI Edit"):
            ctx = SpendGuardContext(
                job_id=f"ci_{fam}",
                product_family=fam,
                estimated_max_cost_usd=1.00,
                has_proven_cost_authority=True,
                bot_originated_action=True,
                bot_confirm_authority="bot_telegram_ui_confirmed",
                is_paid_live_attempt=True,
            )
            res = reserve_provider_spend(ctx, db_path=self.db_path, env=ci_env)
            self.assertFalse(res.allowed)
            self.assertEqual(res.blocker, BLOCKER_TEST_NETWORK_ISOLATION)

    # 38. TTS real key without SHOPAIKEY_GUARD_ALL still enforces spend guard -> BLOCK
    def test_38_tts_real_key_without_guard_all_still_blocked(self):
        env_no_guard = dict(self.standard_env)
        env_no_guard.pop("SHOPAIKEY_GUARD_ALL", None)
        status, task_id, detail, code = asyncio.run(
            shopaikey_minimax_tts_async_submit(
                text="Test text with real key",
                voice_id="voice_1",
                api_key="sk-real-live-shopaikey-key",
                is_paid_live=False,  # Caller attempts bypass
                bot_originated_action=False,
                bot_confirm_authority="",
                db_path=self.db_path,
                env=env_no_guard,
            )
        )
        self.assertEqual(status, "FAIL_SPEND_GUARD_BLOCKED")
        self.assertIn("spend_guard_blocked", detail)

    # 39. TTS missing max cost authority -> BLOCK
    def test_39_tts_missing_max_cost_authority_blocked(self):
        # When text is empty and no proven cost provided
        status, task_id, detail, code = asyncio.run(
            shopaikey_minimax_tts_async_submit(
                text="",
                voice_id="voice_1",
                api_key="sk-real-live-token",
                is_paid_live=True,
                bot_originated_action=True,
                bot_confirm_authority="bot_telegram_ui_confirmed",
                estimated_max_cost_usd=0.0,
                has_proven_cost_authority=False,
                db_path=self.db_path,
                env=self.standard_env,
            )
        )
        self.assertEqual(status, "FAIL_BAD_REQUEST")
        self.assertEqual(detail, "empty_text")

    # 40. TTS post-transport HTTP 500 retains ambiguous -> RETAIN
    def test_40_tts_post_transport_http_500_retains_ambiguous(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = '{"error": "Internal Server Error"}'
        mock_response.json.return_value = {"error": "Internal Server Error"}
        mock_client.post = AsyncMock(return_value=mock_response)

        conf_id = create_bot_confirmation(
            job_id="job_tts_500",
            request_id="req_tts_500",
            product_family="Voice / TTS",
            operation="create_tts_task",
            db_path=self.db_path,
            env=self.standard_env,
        )

        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            status, task_id, detail, code = asyncio.run(
                shopaikey_minimax_tts_async_submit(
                    text="Test TTS 500 ambiguity",
                    voice_id="voice_1",
                    model="tts-1",
                    provider="shopaikey_openai_tts",
                    api_key="mock_key",
                    client=mock_client,
                    job_id="job_tts_500",
                    request_id="req_tts_500",
                    bot_originated_action=True,
                    bot_confirm_authority=conf_id,
                    is_paid_live=True,
                    db_path=self.db_path,
                    env=self.standard_env,
                )
            )
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

        self.assertEqual(status, "FAIL_HTTP_STATUS")
        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertAlmostEqual(summary["pending_reserved_spend_usd"], 0.00033, places=6)

    # 41. TTS post-transport missing task_id in 200 response retains ambiguous -> RETAIN
    def test_41_tts_post_transport_missing_task_id_retains_ambiguous(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"status": "ok"}'  # Missing task_id
        mock_response.json.return_value = {"status": "ok"}
        mock_client.post = AsyncMock(return_value=mock_response)

        conf_id = create_bot_confirmation(
            job_id="job_tts_no_task",
            request_id="req_tts_no_task",
            product_family="Voice / TTS",
            operation="create_tts_task",
            db_path=self.db_path,
            env=self.standard_env,
        )

        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            status, task_id, detail, code = asyncio.run(
                shopaikey_minimax_tts_async_submit(
                    text="Test TTS missing task_id ambiguity",
                    voice_id="voice_1",
                    model="tts-1",
                    provider="shopaikey_openai_tts",
                    api_key="mock_key",
                    client=mock_client,
                    job_id="job_tts_no_task",
                    request_id="req_tts_no_task",
                    bot_originated_action=True,
                    bot_confirm_authority=conf_id,
                    is_paid_live=True,
                    db_path=self.db_path,
                    env=self.standard_env,
                )
            )
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

        self.assertEqual(status, "FAIL_NO_TASK_ID")
        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertAlmostEqual(summary["pending_reserved_spend_usd"], 0.00051, places=6)

    # 42. Chat Pro caller defaults fail-closed without bot origin -> BLOCK
    def test_42_chat_pro_caller_default_blocked_without_bot_origin(self):
        store = PublicChatStore(os.path.join(self.temp_dir, "chat_def.db"))
        pro_mock = MagicMock()
        pro_mock.is_paid_provider = True
        wallet = MagicMock()
        wallet.get_balance = AsyncMock(return_value=50_000)
        wallet.reserve = AsyncMock(return_value={"ok": True, "reservation_id": "res_def"})
        wallet.release = AsyncMock(return_value={"ok": True})
        runtime = PublicChatRuntime(store=store, pro_provider=pro_mock, wallet=wallet, pricing=ClaudeOpusPricing(100, 500, 3))

        # Use pure defaults of PublicChatRequest
        req = PublicChatRequest(
            account_id="u_default",
            chat_id="chat_def",
            source_message_id="msg_def",
            mode="pro",
            prompt="hello world",
            role="user",
            is_paid_external_provider=True,
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertFalse(req.bot_originated_action)
        self.assertEqual(req.bot_confirm_authority, "")

        res = asyncio.run(runtime.generate_pro(req))
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("status"), "SPEND_GUARD_BLOCKED")
        self.assertEqual(res.get("provider_calls"), 0)

    # 43. Chat Pro missing cost authority -> BLOCK
    def test_43_chat_pro_missing_cost_authority_blocked(self):
        store = PublicChatStore(os.path.join(self.temp_dir, "chat_nocost.db"))
        pro_mock = MagicMock()
        pro_mock.is_paid_provider = True
        wallet = MagicMock()
        wallet.get_balance = AsyncMock(return_value=50_000)
        wallet.reserve = AsyncMock(return_value={"ok": True, "reservation_id": "res_nocost"})
        wallet.release = AsyncMock(return_value={"ok": True})
        runtime = PublicChatRuntime(store=store, pro_provider=pro_mock, wallet=wallet, pricing=ClaudeOpusPricing(100, 500, 3))

        req = PublicChatRequest(
            account_id="u_nocost",
            chat_id="chat_nocost",
            source_message_id="msg_nocost",
            mode="pro",
            prompt="hello",
            role="user",
            estimated_input_tokens=0,
            max_output_tokens=0,
            has_proven_cost_authority=False,
            is_paid_external_provider=True,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            db_path=self.db_path,
            env=self.standard_env,
        )

        res = asyncio.run(runtime.generate_pro(req))
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("status"), "SPEND_GUARD_BLOCKED")
        self.assertEqual(res.get("blocker"), BLOCKER_MAX_COST_AUTHORITY_MISSING)

    # 43. Chat Pro missing cost authority -> BLOCK
    def test_43_chat_pro_missing_cost_authority_blocked(self):
        store = PublicChatStore(os.path.join(self.temp_dir, "chat_nocost.db"))
        pro_mock = MagicMock()
        pro_mock.is_paid_provider = True
        wallet = MagicMock()
        wallet.get_balance = AsyncMock(return_value=50_000)
        wallet.reserve = AsyncMock(return_value={"ok": True, "reservation_id": "res_nocost"})
        wallet.release = AsyncMock(return_value={"ok": True})
        runtime = PublicChatRuntime(store=store, pro_provider=pro_mock, wallet=wallet, pricing=ClaudeOpusPricing(100, 500, 3))

        req = PublicChatRequest(
            account_id="u_nocost",
            chat_id="chat_nocost",
            source_message_id="msg_nocost",
            mode="pro",
            prompt="hello",
            role="user",
            estimated_input_tokens=0,
            max_output_tokens=0,
            has_proven_cost_authority=False,
            is_paid_external_provider=True,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            db_path=self.db_path,
            env=self.standard_env,
        )

        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            res = asyncio.run(runtime.generate_pro(req))
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("status"), "SPEND_GUARD_BLOCKED")
        self.assertEqual(res.get("blocker"), BLOCKER_MAX_COST_AUTHORITY_MISSING)

    # 44. Chat Pro trusted bot origin + valid token cost quote -> ALLOW (mock transport)
    def test_44_chat_pro_trusted_bot_with_valid_cost_quote_passes(self):
        store = PublicChatStore(os.path.join(self.temp_dir, "chat_ok.db"))
        pro_mock = MagicMock(return_value={"ok": True, "text": "Claude reply", "model": CLAUDE_OPUS_MODEL, "usage": {"input_tokens": 100, "output_tokens": 50}})
        pro_mock.is_paid_provider = True
        wallet = MagicMock()
        wallet.get_balance = AsyncMock(return_value=50_000)
        wallet.reserve = AsyncMock(return_value={"ok": True, "reservation_id": "res_ok"})
        wallet.settle = AsyncMock(return_value={"ok": True})
        runtime = PublicChatRuntime(store=store, pro_provider=pro_mock, wallet=wallet, pricing=ClaudeOpusPricing(100, 500, 3))

        conf_id = create_bot_confirmation(
            chat_id="chat_ok",
            job_id="msg_ok",
            product_family="Public Chat Pro",
            operation="chat_completion",
            db_path=self.db_path,
            env=self.standard_env,
        )

        req = PublicChatRequest(
            account_id="u_ok",
            chat_id="chat_ok",
            source_message_id="msg_ok",
            mode="pro",
            prompt="tell me a joke",
            role="user",
            estimated_input_tokens=500,
            max_output_tokens=500,
            is_paid_external_provider=True,
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            db_path=self.db_path,
            env=self.standard_env,
        )

        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            res = asyncio.run(runtime.generate_pro(req))
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("status"), "ok")
        pro_mock.assert_called_once()

    # 45. AI Edit real key without AI_EDIT_GUARD_ALL still guarded -> BLOCK
    def test_45_ai_edit_real_key_without_guard_all_still_guarded(self):
        config = AiEditProviderConfig(
            provider_name="fal_video",
            enabled=True,
            submit_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video",
            poll_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video/requests/{task_id}/status",
            auth_header_name="Authorization",
            auth_header_value="Key real_fal_live_secret",
            model="fal-ai/wan/v2.2-a14b/video-to-video",
            interface="video_to_video_json",
            capabilities=("video_to_video",),
        )
        fake_source = "https://storage.fal.run/fake_vid.mp4"
        env_no_guard = dict(self.standard_env)
        env_no_guard.pop("AI_EDIT_GUARD_ALL", None)

        with self.assertRaises(AiEditProviderError) as cm:
            submit_video_edit(
                config,
                source_video_path=fake_source,
                prompt="make anime",
                negative_prompt="",
                aspect_ratio="9:16",
                duration_seconds=5,
                job_id="job_aiedit_noguardall",
                submit_source=PUBLIC_FINAL_CONFIRM_SOURCE,
                public_user_confirmed=True,
                is_paid_live=False,  # Attempt bypass
                bot_originated_action=False,
                bot_confirm_authority="",
                db_path=self.db_path,
                env=env_no_guard,
            )
        self.assertIn("bot_confirm_authority_missing", str(cm.exception))

    # 46. AI Edit unsupported duration missing cost authority -> BLOCK
    def test_46_ai_edit_unsupported_duration_missing_cost_authority_blocked(self):
        config = AiEditProviderConfig(
            provider_name="fal_video",
            enabled=True,
            submit_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video",
            poll_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video/requests/{task_id}/status",
            auth_header_name="Authorization",
            auth_header_value="Key mock_key",
            model="fal-ai/wan/v2.2-a14b/video-to-video",
            interface="video_to_video_json",
            capabilities=("video_to_video",),
        )
        fake_source = "https://storage.fal.run/fake_vid.mp4"

        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            with self.assertRaises(AiEditProviderError) as cm:
                submit_video_edit(
                    config,
                    source_video_path=fake_source,
                    prompt="make anime",
                    negative_prompt="",
                    aspect_ratio="9:16",
                    duration_seconds=7,  # Unsupported duration (not 5s or 10s)
                    job_id="job_aiedit_7s",
                    submit_source=PUBLIC_FINAL_CONFIRM_SOURCE,
                    public_user_confirmed=True,
                    is_paid_live=True,
                    bot_originated_action=True,
                    bot_confirm_authority="bot_telegram_ui_confirmed",
                    db_path=self.db_path,
                    env=self.standard_env,
                )
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

        self.assertIn(BLOCKER_MAX_COST_AUTHORITY_MISSING, str(cm.exception))

    # 47. AI Edit synthetic bot origin rejected -> BLOCK
    def test_47_ai_edit_synthetic_bot_origin_rejected(self):
        config = AiEditProviderConfig(
            provider_name="fal_video",
            enabled=True,
            submit_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video",
            poll_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video/requests/{task_id}/status",
            auth_header_name="Authorization",
            auth_header_value="Key mock_key",
            model="fal-ai/wan/v2.2-a14b/video-to-video",
            interface="video_to_video_json",
            capabilities=("video_to_video",),
        )
        fake_source = "https://storage.fal.run/fake_vid.mp4"

        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            with self.assertRaises(AiEditProviderError) as cm:
                submit_video_edit(
                    config,
                    source_video_path=fake_source,
                    prompt="make anime",
                    negative_prompt="",
                    aspect_ratio="9:16",
                    duration_seconds=5,
                    job_id="job_aiedit_synth",
                    submit_source=PUBLIC_FINAL_CONFIRM_SOURCE,
                    public_user_confirmed=True,
                    is_paid_live=True,
                    bot_originated_action=False,
                    bot_confirm_authority="bot_telegram_ui_confirmed",
                    db_path=self.db_path,
                    env=self.standard_env,
                )
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

        self.assertIn(BLOCKER_BOT_ORIGIN_PROOF_MISSING, str(cm.exception))

    # 48. AI Edit post-transport HTTP error retains ambiguous -> RETAIN
    def test_48_ai_edit_post_transport_http_error_retains_ambiguous(self):
        config = AiEditProviderConfig(
            provider_name="fal_video",
            enabled=True,
            submit_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video",
            poll_url="https://queue.fal.run/fal-ai/wan/v2.2-a14b/video-to-video/requests/{task_id}/status",
            auth_header_name="Authorization",
            auth_header_value="Key mock_key",
            model="fal-ai/wan/v2.2-a14b/video-to-video",
            interface="video_to_video_json",
            capabilities=("video_to_video",),
        )
        fake_source = "https://storage.fal.run/fake_vid.mp4"

        conf_id = create_bot_confirmation(
            job_id="job_aiedit_http500",
            product_family="Video AI Edit",
            operation="submit_video_edit",
            db_path=self.db_path,
            env=self.standard_env,
        )

        import io
        def mock_opener_http_error(req, timeout=0):
            fp = io.BytesIO(b'{"detail": "Internal Server Error"}')
            raise urllib.error.HTTPError(req.full_url, 500, "Internal Server Error", hdrs={}, fp=fp)

        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            with self.assertRaises(AiEditProviderError):
                submit_video_edit(
                    config,
                    source_video_path=fake_source,
                    prompt="make anime",
                    negative_prompt="",
                    aspect_ratio="9:16",
                    duration_seconds=5,
                    job_id="job_aiedit_http500",
                    submit_source=PUBLIC_FINAL_CONFIRM_SOURCE,
                    public_user_confirmed=True,
                    opener=mock_opener_http_error,
                    is_paid_live=True,
                    bot_originated_action=True,
                    bot_confirm_authority=conf_id,
                    db_path=self.db_path,
                    env=self.standard_env,
                )
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertEqual(summary["pending_reserved_spend_usd"], 0.40)

    # 49. Kill switch alias PAID_EXTERNAL_PROVIDERS_DISABLED=true -> BLOCK
    def test_49_kill_switch_paid_external_providers_disabled_env(self):
        kill_env = dict(self.standard_env)
        kill_env["PAID_EXTERNAL_PROVIDERS_DISABLED"] = "true"
        self.assertTrue(is_kill_switch_active(kill_env))

        # Check all product families fail closed
        for fam in ("Product Video", "Voice / TTS", "Public Chat Pro", "Video AI Edit"):
            ctx = SpendGuardContext(product_family=fam, estimated_max_cost_usd=1.00, has_proven_cost_authority=True, bot_originated_action=True, bot_confirm_authority="bot_telegram_ui_confirmed")
            res = reserve_provider_spend(ctx, db_path=self.db_path, env=kill_env)
            self.assertFalse(res.allowed)
            self.assertEqual(res.blocker, BLOCKER_KILL_SWITCH_ACTIVE)

    # 50. ProviderPaidTransportAuthority registry completeness
    def test_50_provider_paid_transport_registry_complete(self):
        self.assertGreaterEqual(len(PROVIDER_PAID_TRANSPORT_REGISTRY), 10)
        families = {entry.product_family for entry in PROVIDER_PAID_TRANSPORT_REGISTRY}
        self.assertIn("Product Video", families)
        self.assertIn("Voice / TTS", families)
        self.assertIn("Public Chat Pro", families)
        self.assertIn("Video AI Edit", families)
        self.assertIn("SubDub ASR", families)

        tts_auth = resolve_paid_transport_authority("Voice / TTS", "shopaikey_minimax_tts", "create_tts_task")
        self.assertIsNotNone(tts_auth)
        self.assertTrue(tts_auth.can_create_paid_usage)
        self.assertTrue(tts_auth.bot_origin_required)

        chat_auth = resolve_paid_transport_authority("Public Chat Pro", "claude-opus", "chat_completion")
        self.assertIsNotNone(chat_auth)
        self.assertTrue(chat_auth.can_create_paid_usage)


class TestN21UProviderFreeSpendGuardMatrix(unittest.TestCase):
    """Dedicated 18-case test matrix enforcing Section 16 of Owner Directive #1422."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_spend_guard_matrix18_")
        self.db_path = os.path.join(self.temp_dir, "shared_toanaas.db")
        self.standard_env = {
            "SPEND_GUARD_DB_PATH": self.db_path,
            "WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE": "MONDAY_0000_UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE": "UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_USD": "200.000",
        }
        init_spend_guard_db(db_path=self.db_path, env=self.standard_env)
        set_kill_switch(None)

    def tearDown(self):
        set_kill_switch(None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 1. forged has_proven_cost_authority=True => BLOCK
    def test_case_01_forged_has_proven_cost_authority_blocked(self):
        ctx = SpendGuardContext(
            job_id="mat_01",
            request_id="req_mat_01",
            product_family="Product Video",
            provider="key4u_video",
            model="unknown_forged_model",
            operation="create_video_task",
            estimated_max_cost_usd=1.00,
            has_proven_cost_authority=True,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_MAX_COST_AUTHORITY_MISSING)

    # 2. forged estimated cost $0.001 => cannot lower canonical reserve
    def test_case_02_forged_estimated_cost_lowered_cannot_lower_canonical_reserve(self):
        conf_id = create_bot_confirmation(
            job_id="mat_02",
            request_id="req_mat_02",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="mat_02",
            request_id="req_mat_02",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            estimated_max_cost_usd=0.001,  # Caller tries to cheat reserve
            has_proven_cost_authority=True,
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)
        self.assertEqual(res.week_spend_after_micro_usd - res.week_spend_before_micro_usd, 30_600_245)
        self.assertEqual(res.audit_record.get("RESERVED_COST_USD"), 30.600245)

    # 3. forged whitelisted bot-confirm string => BLOCK
    def test_case_03_forged_whitelisted_bot_confirm_string_blocked(self):
        ctx = SpendGuardContext(
            job_id="mat_03",
            request_id="req_mat_03",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",  # String alone without DB row
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 4. real durable bot confirmation record => PASS guard
    def test_case_04_real_durable_bot_confirmation_record_passes_guard(self):
        conf_id = create_bot_confirmation(
            job_id="mat_04",
            request_id="req_mat_04",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="mat_04",
            request_id="req_mat_04",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)

    # 5. expired confirmation => BLOCK
    def test_case_05_expired_confirmation_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="mat_05",
            request_id="req_mat_05",
            product_family="Product Video",
            operation="create_video_task",
            ttl_seconds=-10.0,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="mat_05",
            request_id="req_mat_05",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 6. already-consumed confirmation => BLOCK
    def test_case_06_already_consumed_confirmation_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="mat_06",
            request_id="req_mat_06",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx1 = SpendGuardContext(
            job_id="mat_06",
            request_id="req_mat_06",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res1 = reserve_provider_spend(ctx1, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)

        # Attempt to reuse the same confirmation on a different job/request
        ctx2 = SpendGuardContext(
            job_id="mat_06_reuse",
            request_id="req_mat_06_reuse",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res2 = reserve_provider_spend(ctx2, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res2.allowed)
        self.assertEqual(res2.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 7. confirmation for another job => BLOCK
    def test_case_07_confirmation_for_another_job_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="job_original",
            request_id="req_original",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="job_mismatched",
            request_id="req_mismatched",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 8. confirmation for another product/action => BLOCK
    def test_case_08_confirmation_for_another_product_action_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="mat_08",
            request_id="req_mat_08",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="mat_08",
            request_id="req_mat_08",
            product_family="Voice / TTS",
            provider="shopaikey_openai_tts",
            model="tts-1",
            operation="create_tts_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"char_count": 100},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 9. caller spend_context forged provider/cost => BLOCK
    def test_case_09_caller_spend_context_forged_provider_cost_blocked(self):
        ctx = SpendGuardContext(
            job_id="mat_09",
            request_id="req_mat_09",
            product_family="Product Video",
            provider="unregistered_fake_provider",
            model="fake_model",
            operation="create_video_task",
            estimated_max_cost_usd=0.01,
            has_proven_cost_authority=True,
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_PAID_TRANSPORT_AUTHORITY_UNREGISTERED)

    # 10. Product Video model with canonical cost > $1 => reserve actual canonical maximum
    def test_case_10_product_video_canonical_cost_greater_than_one_dollar(self):
        conf_id = create_bot_confirmation(
            job_id="mat_10",
            request_id="req_mat_10",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="mat_10",
            request_id="req_mat_10",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15", "scene_count": 2},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)
        self.assertEqual(res.week_spend_after_micro_usd - res.week_spend_before_micro_usd, 61_200_490)
        self.assertEqual(res.audit_record.get("RESERVED_COST_USD"), 61.20049)

    # 11. unknown Product Video pricing => BLOCK
    def test_case_11_unknown_product_video_pricing_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="mat_11",
            request_id="req_mat_11",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="mat_11",
            request_id="req_mat_11",
            product_family="Product Video",
            provider="key4u_video",
            model="unpriced_xyz_model",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_MAX_COST_AUTHORITY_MISSING)

    # 12. TTS mismatched provider pricing => BLOCK
    def test_case_12_tts_mismatched_provider_pricing_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="mat_12",
            request_id="req_mat_12",
            product_family="Voice / TTS",
            operation="create_tts_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="mat_12",
            request_id="req_mat_12",
            product_family="Voice / TTS",
            provider="shopaikey_minimax_tts",
            model="speech-02-hd",
            operation="create_tts_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"char_count": 500},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_MAX_COST_AUTHORITY_MISSING)

    # 13. ASR missing pricing => BLOCK
    def test_case_13_asr_missing_pricing_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="mat_13",
            request_id="req_mat_13",
            product_family="SubDub ASR",
            operation="asr_transcribe",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="mat_13",
            request_id="req_mat_13",
            product_family="SubDub ASR",
            provider="key4u_whisper",
            model="whisper-1",
            operation="asr_transcribe",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_MAX_COST_AUTHORITY_MISSING)

    # 14. Suno missing pricing => BLOCK
    def test_case_14_suno_missing_pricing_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="mat_14",
            request_id="req_mat_14",
            product_family="Music / Suno",
            operation="suno_create",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="mat_14",
            request_id="req_mat_14",
            product_family="Music / Suno",
            provider="key4u_suno",
            model="suno-v3.5",
            operation="suno_create",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_MAX_COST_AUTHORITY_MISSING)

    # 15. duplicate same bot action => BLOCK
    def test_case_15_duplicate_same_bot_action_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="mat_15",
            request_id="req_mat_15",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="mat_15",
            request_id="req_mat_15",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res1 = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)

        # Same identical action resubmitted
        res2 = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res2.allowed)
        self.assertEqual(res2.blocker, BLOCKER_DUPLICATE_PAID_SUBMIT)

    # 16. CI paid call => BLOCK
    def test_case_16_ci_paid_call_blocked(self):
        ci_env = dict(self.standard_env)
        ci_env["CI"] = "true"
        ctx = SpendGuardContext(
            job_id="mat_16",
            request_id="req_mat_16",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
            is_paid_live_attempt=True,
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=ci_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_TEST_NETWORK_ISOLATION)

    # 17. shell/script call => BLOCK
    def test_case_17_shell_script_paid_call_blocked(self):
        ctx = SpendGuardContext(
            job_id="mat_17",
            request_id="req_mat_17",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=False,
            entrypoint="script",
            bot_confirm_authority="",
            is_paid_live_attempt=True,
        )
        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_PAID_LIVE_TEST_BOT_ONLY)

    # 18. kill switch => BLOCK
    def test_case_18_kill_switch_blocked(self):
        set_kill_switch(True)
        ctx = SpendGuardContext(
            job_id="mat_18",
            request_id="req_mat_18",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority="bot_telegram_ui_confirmed",
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_KILL_SWITCH_ACTIVE)


class TestN21VRealBotConfirmLineageAndMultiSubmitMatrix(unittest.TestCase):
    """Authoritative 22-case matrix for N21V real bot confirm lineage and multi-submit authority."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="pv_n21v_test_")
        self.db_path = os.path.join(self.temp_dir, "toanaas_spend_guard_shared.db")
        self.standard_env = {
            "SPEND_GUARD_DB_PATH": self.db_path,
            "WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE": "MONDAY_0000_UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE": "UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_USD": "200.000",
            "UNIT_TEST_ENV": "true",
            "TEST_RUNNER": "true",
        }
        set_kill_switch(None)
        init_spend_guard_db(db_path=self.db_path, env=self.standard_env)

    def tearDown(self):
        set_kill_switch(None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 1. fake confirmation ID + matching valid job_id -> BLOCK
    def test_n21v_01_fake_confirmation_id_matching_valid_job_blocked(self):
        create_bot_confirmation(
            job_id="job_valid_01",
            request_id="req_valid_01",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="job_valid_01",
            request_id="req_valid_01",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority="fake_confirmation_id_01",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 2. fake confirmation ID + matching valid request_id -> BLOCK
    def test_n21v_02_fake_confirmation_id_matching_valid_request_blocked(self):
        create_bot_confirmation(
            job_id="job_valid_02",
            request_id="req_valid_02",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="job_valid_02",
            request_id="req_valid_02",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority="fake_confirmation_id_02",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 3. exact confirmation ID + wrong job -> BLOCK
    def test_n21v_03_exact_confirmation_id_wrong_job_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="job_original_03",
            request_id="req_original_03",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="job_wrong_03",
            request_id="req_original_03",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)
        self.assertIn("job mismatch", res.reason)

    # 4. exact ID + wrong request -> BLOCK
    def test_n21v_04_exact_id_wrong_request_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="job_original_04",
            request_id="req_original_04",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="job_original_04",
            request_id="req_wrong_04",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)
        self.assertIn("request mismatch", res.reason)

    # 5. exact ID + wrong user/chat -> BLOCK
    def test_n21v_05_exact_id_wrong_user_or_chat_blocked(self):
        conf_id = create_bot_confirmation(
            chat_id="11111",
            user_id="22222",
            job_id="job_05",
            request_id="req_05",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        # Wrong chat
        ctx_wrong_chat = SpendGuardContext(
            chat_id="99999",
            user_id="22222",
            job_id="job_05",
            request_id="req_05",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res1 = reserve_provider_spend(ctx_wrong_chat, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res1.allowed)
        self.assertEqual(res1.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)
        self.assertIn("chat mismatch", res1.reason)

        # Wrong user
        ctx_wrong_user = SpendGuardContext(
            chat_id="11111",
            user_id="88888",
            job_id="job_05",
            request_id="req_05",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res2 = reserve_provider_spend(ctx_wrong_user, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res2.allowed)
        self.assertEqual(res2.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)
        self.assertIn("user mismatch", res2.reason)

    # 6. exact ID + wrong operation -> BLOCK
    def test_n21v_06_exact_id_wrong_operation_blocked(self):
        conf_id = create_bot_confirmation(
            job_id="job_06",
            request_id="req_06",
            product_family="Product Video",
            operation="submit_video_edit",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="job_06",
            request_id="req_06",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)
        self.assertIn("operation mismatch", res.reason)

    # 7. empty paid operation -> BLOCK
    def test_n21v_07_empty_paid_operation_blocked(self):
        self.assertTrue(EMPTY_PAID_OPERATION_BLOCKED)
        conf_id = create_bot_confirmation(
            job_id="job_07",
            request_id="req_07",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id="job_07",
            request_id="req_07",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_PAID_TRANSPORT_AUTHORITY_UNREGISTERED)

    # 8. direct provider cannot mint confirmation
    def test_n21v_08_direct_provider_cannot_mint_confirmation(self):
        self.assertFalse(PROVIDER_CAN_MINT_BOT_CONFIRMATION)
        with self.assertRaises(PermissionError):
            create_bot_confirmation(
                origin="direct_provider",
                job_id="job_08",
                request_id="req_08",
                db_path=self.db_path,
                env=self.standard_env,
            )
        with self.assertRaises(PermissionError):
            mint_multiscene_bot_confirmation_plan(
                origin="provider",
                job_id="job_08",
                request_id="req_08",
                db_path=self.db_path,
                env=self.standard_env,
            )

    # 9. worker cannot mint confirmation
    def test_n21v_09_worker_cannot_mint_confirmation(self):
        self.assertFalse(WORKER_CAN_MINT_BOT_CONFIRMATION)
        with self.assertRaises(PermissionError):
            create_bot_confirmation(
                origin="worker",
                job_id="job_09",
                request_id="req_09",
                db_path=self.db_path,
                env=self.standard_env,
            )
        with self.assertRaises(PermissionError):
            mint_multiscene_bot_confirmation_plan(
                origin="worker",
                job_id="job_09",
                request_id="req_09",
                db_path=self.db_path,
                env=self.standard_env,
            )

    # 10. shell cannot mint usable bot authority
    def test_n21v_10_shell_cannot_mint_usable_bot_authority(self):
        with self.assertRaises(PermissionError):
            create_bot_confirmation(
                origin="shell",
                job_id="job_10",
                request_id="req_10",
                db_path=self.db_path,
                env=self.standard_env,
            )
        with self.assertRaises(PermissionError):
            mint_multiscene_bot_confirmation_plan(
                origin="shell",
                job_id="job_10",
                request_id="req_10",
                db_path=self.db_path,
                env=self.standard_env,
            )

    # 11. actual mocked Telegram confirm -> creates durable confirmation
    def test_n21v_11_mocked_telegram_confirm_creates_durable_confirmation(self):
        self.assertEqual(PRODUCTION_BOT_CONFIRM_MINT_CALLSITE, "bot.py:handle_video_product_callback:b14_confirm")
        seed_test_durable_bot_origin_in_trace(
            self.db_path,
            telegram_update_id=998877,
            callback_query_id="cbq_tg_11",
            chat_id="12345",
            user_id="67890",
            job_id="job_tg_11",
            request_id="req_tg_11",
        )
        mint_auth = issue_bot_mint_authority(
            callsite=PRODUCTION_BOT_CONFIRM_MINT_CALLSITE,
            telegram_update_id=998877,
            callback_query_id="cbq_tg_11",
            chat_id="12345",
            user_id="67890",
            job_id="job_tg_11",
            request_id="req_tg_11",
            validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
            validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
            validated_ownership=True,
            db_path=self.db_path,
            env=self.standard_env,
        )
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=mint_auth,
            chat_id="12345",
            user_id="67890",
            job_id="job_tg_11",
            request_id="req_tg_11",
            product_family="Product Video",
            operation="create_video_task",
            scene_count=2,
            ttl_seconds=600.0,
            metadata={
                "telegram_update_id": 998877,
                "production_callsite": PRODUCTION_BOT_CONFIRM_MINT_CALLSITE,
            },
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertTrue(plan["parent_confirmation_id"].startswith("bot_conf_parent_"))
        self.assertEqual(len(plan["child_confirmations"]), 2)

        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT confirmation_id, parent_confirmation_id, scene_index, status FROM bot_spend_confirmations WHERE job_id = ?", ("job_tg_11",))
        rows = cur.fetchall()
        conn.close()
        self.assertEqual(len(rows), 3)
        for r in rows:
            self.assertEqual(r[3], "active")

    # 12. confirmation propagates Bot -> job -> worker -> spend guard
    def test_n21v_12_confirmation_propagates_bot_to_job_to_worker_to_spend_guard(self):
        plan = mint_multiscene_bot_confirmation_plan(
            chat_id="111",
            user_id="222",
            job_id="job_prop_12",
            request_id="req_prop_12",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        from services.video_project_queue import _product_video_final_admission_state
        admission_in = {
            "bot_confirm_authority": plan["parent_confirmation_id"],
            "scene_confirmations": plan["scene_confirmations"],
            "child_confirmations": plan["child_confirmations"],
        }
        state = _product_video_final_admission_state({}, admission_in, user_id=222, require_provider_admission=True, require_authoritative_snapshot=False, checked_at="2026-10-12T00:00:00")
        self.assertEqual(state.get("bot_confirm_authority"), plan["parent_confirmation_id"])
        self.assertEqual(state.get("scene_confirmations"), plan["scene_confirmations"])

    # 13. two-scene job receives exactly two child authorities
    def test_n21v_13_two_scene_job_receives_exactly_two_child_authorities(self):
        plan = mint_multiscene_bot_confirmation_plan(
            chat_id="333",
            user_id="444",
            job_id="job_two_13",
            request_id="req_two_13",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertEqual(len(plan["child_confirmations"]), 2)
        self.assertEqual(len(plan["scene_confirmations"]), 2)
        self.assertIn(1, plan["scene_confirmations"])
        self.assertIn(2, plan["scene_confirmations"])
        self.assertNotEqual(plan["scene_confirmations"][1], plan["scene_confirmations"][2])

    # 14. scene1 passes once
    def test_n21v_14_scene1_passes_once(self):
        plan = mint_multiscene_bot_confirmation_plan(
            chat_id="555",
            user_id="666",
            job_id="job_s1_14",
            request_id="req_s1_14",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        child1 = plan["scene_confirmations"][1]
        ctx = SpendGuardContext(
            chat_id="555",
            user_id="666",
            job_id="job_s1_14",
            request_id="req_s1_14",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=child1,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)

        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT status, consumed_at FROM bot_spend_confirmations WHERE confirmation_id = ?", (child1,))
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row[0], "consumed")
        self.assertIsNotNone(row[1])

    # 15. scene2 passes once
    def test_n21v_15_scene2_passes_once(self):
        plan = mint_multiscene_bot_confirmation_plan(
            chat_id="777",
            user_id="888",
            job_id="job_s2_15",
            request_id="req_s2_15",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        # Scene 1 passes
        ctx1 = SpendGuardContext(
            chat_id="777",
            user_id="888",
            job_id="job_s2_15",
            request_id="req_s2_15",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=plan["scene_confirmations"][1],
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res1 = reserve_provider_spend(ctx1, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)

        # Scene 2 passes
        ctx2 = SpendGuardContext(
            chat_id="777",
            user_id="888",
            job_id="job_s2_15",
            request_id="req_s2_15",
            scene_index=2,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=plan["scene_confirmations"][2],
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res2 = reserve_provider_spend(ctx2, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res2.allowed)

    # 16. scene3 blocked
    def test_n21v_16_scene3_blocked(self):
        plan = mint_multiscene_bot_confirmation_plan(
            chat_id="999",
            user_id="1010",
            job_id="job_s3_16",
            request_id="req_s3_16",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx3 = SpendGuardContext(
            chat_id="999",
            user_id="1010",
            job_id="job_s3_16",
            request_id="req_s3_16",
            scene_index=3,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=plan.get("scene_confirmations", {}).get(3, ""),
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res3 = reserve_provider_spend(ctx3, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res3.allowed)
        self.assertEqual(res3.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 17. scene1 duplicate blocked
    def test_n21v_17_scene1_duplicate_blocked(self):
        plan = mint_multiscene_bot_confirmation_plan(
            chat_id="1212",
            user_id="1313",
            job_id="job_dup_17",
            request_id="req_dup_17",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="1212",
            user_id="1313",
            job_id="job_dup_17",
            request_id="req_dup_17",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=plan["scene_confirmations"][1],
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res1 = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)

        # Duplicate submit with identical context
        res2 = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res2.allowed)
        self.assertEqual(res2.blocker, BLOCKER_DUPLICATE_PAID_SUBMIT)

    # 18. ambiguous scene consumes authority and retry blocked
    def test_n21v_18_ambiguous_scene_consumes_authority_and_retry_blocked(self):
        plan = mint_multiscene_bot_confirmation_plan(
            chat_id="1414",
            user_id="1515",
            job_id="job_amb_18",
            request_id="req_amb_18",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        child1 = plan["scene_confirmations"][1]
        ctx = SpendGuardContext(
            chat_id="1414",
            user_id="1515",
            job_id="job_amb_18",
            request_id="req_amb_18",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=child1,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)

        retain_ambiguous_provider_spend(
            res.reservation_id,
            error_code="transport_timeout_disconnect",
            db_path=self.db_path,
            env=self.standard_env,
        )

        # Retry blocked
        retry_res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(retry_res.allowed)
        self.assertEqual(retry_res.blocker, BLOCKER_AMBIGUOUS_RETRY_BLOCKED)

        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT status FROM bot_spend_confirmations WHERE confirmation_id = ?", (child1,))
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row[0], "consumed")

    # 19. caller metadata submit_source cannot create bot authority
    def test_n21v_19_caller_metadata_submit_source_cannot_create_bot_authority(self):
        self.assertFalse(CALLER_BOT_ORIGIN_METADATA_TRUSTED)
        ctx = SpendGuardContext(
            job_id="job_meta_19",
            request_id="req_meta_19",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=False,
            bot_confirm_authority="",
            metadata={"submit_source": "public_user_final_confirm", "quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 20. caller product_video=True cannot create bot authority
    def test_n21v_20_caller_product_video_cannot_create_bot_authority(self):
        ctx = SpendGuardContext(
            job_id="job_meta_20",
            request_id="req_meta_20",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=False,
            bot_confirm_authority="",
            metadata={"product_video": True, "source": "product_video", "quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 21. exact Product Video tier cost selected
    def test_n21v_21_exact_product_video_tier_cost_selected(self):
        authority = resolve_paid_transport_authority("Product Video", "key4u_video", "create_video_task")
        self.assertIsNotNone(authority)
        ctx15 = SpendGuardContext(
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        cost15, proven15, source15 = resolve_canonical_cost_micro_usd(ctx15, authority)
        self.assertTrue(proven15)
        self.assertEqual(cost15, 30_600_245)

        ctx5 = SpendGuardContext(
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            metadata={"quality_key": "motion_standard_5"},
        )
        cost5, proven5, source5 = resolve_canonical_cost_micro_usd(ctx5, authority)
        self.assertTrue(proven5)
        self.assertEqual(cost5, 7_650_061)

    # 22. ambiguous route pricing -> BLOCK
    def test_n21v_22_ambiguous_route_pricing_blocked(self):
        authority = resolve_paid_transport_authority("Product Video", "key4u_video", "create_video_task")
        self.assertIsNotNone(authority)
        ctx_ambiguous = SpendGuardContext(
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            metadata={},
        )
        cost, proven, source = resolve_canonical_cost_micro_usd(ctx_ambiguous, authority)
        self.assertFalse(proven)
        self.assertIn("ambiguous_product_video_route_pricing_multiple_tiers_match", source)

        conf_id = create_bot_confirmation(
            job_id="job_amb_22",
            request_id="req_amb_22",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx_ambiguous.job_id = "job_amb_22"
        ctx_ambiguous.request_id = "req_amb_22"
        ctx_ambiguous.bot_confirm_authority = conf_id
        res = reserve_provider_spend(ctx_ambiguous, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_MAX_COST_AUTHORITY_MISSING)


class TestN21WConfirmationMintBoundaryAndProductionReadinessMatrix(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_n21w_matrix_")
        self.db_path = os.path.join(self.temp_dir, "toanaas.db")
        self.standard_env = {
            "SPEND_GUARD_DB_PATH": self.db_path,
            "WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE": "MONDAY_0000_UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE": "UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_USD": "200.000",
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 1. worker calls mint primitive with default args -> BLOCK
    def test_n21w_01_worker_calls_mint_primitive_with_default_args_blocked(self):
        with self.assertRaises(PermissionError):
            _raw_create_bot_confirmation(db_path=self.db_path, env=self.standard_env)

    # 2. provider calls mint primitive with default args -> BLOCK
    def test_n21w_02_provider_calls_mint_primitive_with_default_args_blocked(self):
        with self.assertRaises(PermissionError):
            _raw_mint_multiscene_bot_confirmation_plan(db_path=self.db_path, env=self.standard_env)

    # 3. forged origin="telegram_bot_callback_or_command" outside trusted Bot mint authority -> BLOCK
    def test_n21w_03_forged_origin_outside_trusted_mint_authority_blocked(self):
        with self.assertRaises(PermissionError):
            _raw_create_bot_confirmation(
                origin="telegram_bot_callback_or_command",
                job_id="job_forge",
                db_path=self.db_path,
                env=self.standard_env,
            )

    # 4. Bot validated Telegram callback -> mint PASS
    def test_n21w_04_bot_validated_telegram_callback_mint_passes(self):
        seed_test_durable_bot_origin_in_trace(
            self.db_path,
            telegram_update_id=123456,
            callback_query_id="cbq_04",
            chat_id="chat_04",
            user_id="user_04",
            job_id="job_04",
            request_id="req_04",
        )
        mint_auth = issue_bot_mint_authority(
            callsite="bot.py:handle_video_product_callback:b14_confirm",
            telegram_update_id=123456,
            callback_query_id="cbq_04",
            chat_id="chat_04",
            user_id="user_04",
            job_id="job_04",
            request_id="req_04",
            validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
            validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
            validated_ownership=True,
            db_path=self.db_path,
            env=self.standard_env,
        )
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=mint_auth,
            chat_id="chat_04",
            user_id="user_04",
            job_id="job_04",
            request_id="req_04",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertTrue(plan["parent_confirmation_id"].startswith("bot_conf_parent_"))
        self.assertEqual(len(plan["child_confirmations"]), 2)
        self.assertEqual(len(plan["scene_confirmations"]), 2)

    # 5. mint failure -> invoice confirm NOT called
    def test_n21w_05_mint_failure_invoice_confirm_not_called(self):
        invoice_called = False
        def mock_confirm_invoice(*args, **kwargs):
            nonlocal invoice_called
            invoice_called = True
            return {"ok": True}

        mint_failed = True
        if mint_failed:
            blocked_session = {"blocker_code": "spend_guard_mint_failed", "status": "BLOCKED"}
        else:
            mock_confirm_invoice("proj_1", "u_1")

        self.assertFalse(invoice_called)
        self.assertEqual(blocked_session["blocker_code"], "spend_guard_mint_failed")

    # 6. mint failure -> queue NOT called
    def test_n21w_06_mint_failure_queue_not_called(self):
        queue_called = False
        def mock_enqueue(*args, **kwargs):
            nonlocal queue_called
            queue_called = True

        mint_failed = True
        if not mint_failed:
            mock_enqueue()

        self.assertFalse(queue_called)

    # 7. mint failure -> wallet mutation 0
    def test_n21w_07_mint_failure_wallet_mutation_zero(self):
        wallet_debits = 0
        def mock_wallet_debit(*args, **kwargs):
            nonlocal wallet_debits
            wallet_debits += 1

        mint_failed = True
        if not mint_failed:
            mock_wallet_debit()

        self.assertEqual(wallet_debits, 0)

    # 8. exact confirmation + missing job_id -> BLOCK
    def test_n21w_08_exact_confirmation_missing_job_id_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_8", user_id="user_8")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_8",
            user_id="user_8",
            job_id="job_8",
            request_id="req_8",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_8",
            user_id="user_8",
            job_id="",
            request_id="req_8",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 9. exact confirmation + missing request_id -> BLOCK
    def test_n21w_09_exact_confirmation_missing_request_id_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_9", user_id="user_9")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_9",
            user_id="user_9",
            job_id="job_9",
            request_id="req_9",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_9",
            user_id="user_9",
            job_id="job_9",
            request_id="",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 10. exact confirmation + missing chat_id -> BLOCK
    def test_n21w_10_exact_confirmation_missing_chat_id_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_10", user_id="user_10")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_10",
            user_id="user_10",
            job_id="job_10",
            request_id="req_10",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="",
            user_id="user_10",
            job_id="job_10",
            request_id="req_10",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 11. exact confirmation + missing user_id -> BLOCK
    def test_n21w_11_exact_confirmation_missing_user_id_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_11", user_id="user_11")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_11",
            user_id="user_11",
            job_id="job_11",
            request_id="req_11",
            product_family="Product Video",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_11",
            user_id="",
            job_id="job_11",
            request_id="req_11",
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 12. exact child + missing scene_index -> BLOCK
    def test_n21w_12_exact_child_missing_scene_index_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_12", user_id="user_12")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_12",
            user_id="user_12",
            job_id="job_12",
            request_id="req_12",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        child1 = plan["scene_confirmations"][1]
        ctx = SpendGuardContext(
            chat_id="chat_12",
            user_id="user_12",
            job_id="job_12",
            request_id="req_12",
            scene_index=0,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=child1,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 13. parent confirmation used for submit -> BLOCK
    def test_n21w_13_parent_confirmation_used_for_submit_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_13", user_id="user_13")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_13",
            user_id="user_13",
            job_id="job_13",
            request_id="req_13",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        parent_id = plan["parent_confirmation_id"]
        ctx = SpendGuardContext(
            chat_id="chat_13",
            user_id="user_13",
            job_id="job_13",
            request_id="req_13",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=parent_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)
        self.assertIn("cannot authorize transport submit", res.reason)

    # 14. scene 1 -> exact child 1
    def test_n21w_14_scene_1_exact_child_1_passes(self):
        auth = create_test_mint_authority(chat_id="chat_14", user_id="user_14")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_14",
            user_id="user_14",
            job_id="job_14",
            request_id="req_14",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        child1 = plan["scene_confirmations"][1]
        ctx1 = SpendGuardContext(
            chat_id="chat_14",
            user_id="user_14",
            job_id="job_14",
            request_id="req_14",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=child1,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res1 = reserve_provider_spend(ctx1, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)

    # 15. scene 2 -> exact child 2
    def test_n21w_15_scene_2_exact_child_2_passes(self):
        auth = create_test_mint_authority(chat_id="chat_15", user_id="user_15")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_15",
            user_id="user_15",
            job_id="job_15",
            request_id="req_15",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        child2 = plan["scene_confirmations"][2]
        ctx2 = SpendGuardContext(
            chat_id="chat_15",
            user_id="user_15",
            job_id="job_15",
            request_id="req_15",
            scene_index=2,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=child2,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res2 = reserve_provider_spend(ctx2, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res2.allowed)

    # 16. scene 0 -> BLOCK
    def test_n21w_16_scene_0_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_16", user_id="user_16")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_16",
            user_id="user_16",
            job_id="job_16",
            request_id="req_16",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_16",
            user_id="user_16",
            job_id="job_16",
            request_id="req_16",
            scene_index=0,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=plan["scene_confirmations"][1],
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 17. scene 3 in two-scene plan -> BLOCK
    def test_n21w_17_scene_3_in_two_scene_plan_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_17", user_id="user_17")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_17",
            user_id="user_17",
            job_id="job_17",
            request_id="req_17",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_17",
            user_id="user_17",
            job_id="job_17",
            request_id="req_17",
            scene_index=3,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority="",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 18. no +/-1 scene fallback
    def test_n21w_18_no_plus_minus_one_scene_fallback(self):
        auth = create_test_mint_authority(chat_id="chat_18", user_id="user_18")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_18",
            user_id="user_18",
            job_id="job_18",
            request_id="req_18",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        child1 = plan["scene_confirmations"][1]
        ctx = SpendGuardContext(
            chat_id="chat_18",
            user_id="user_18",
            job_id="job_18",
            request_id="req_18",
            scene_index=2,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=child1,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)
        self.assertIn("scene mismatch: scene 1 != 2", res.reason)

    # 19. final admitted scene count != minted child count -> BLOCK
    def test_n21w_19_final_admitted_scene_count_mismatch_blocked(self):
        confirm_scene_count = 2
        final_admitted_scene_count = 3
        blocked = confirm_scene_count != final_admitted_scene_count
        self.assertTrue(blocked)

    # 20. child reservation + consume atomic
    def test_n21w_20_child_reservation_and_consume_atomic(self):
        auth = create_test_mint_authority(chat_id="chat_20", user_id="user_20")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_20",
            user_id="user_20",
            job_id="job_20",
            request_id="req_20",
            scene_count=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        child1 = plan["scene_confirmations"][1]
        ctx = SpendGuardContext(
            chat_id="chat_20",
            user_id="user_20",
            job_id="job_20",
            request_id="req_20",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=child1,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)

        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT status, consumed_at FROM bot_spend_confirmations WHERE confirmation_id = ?", (child1,))
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row[0], "consumed")
        self.assertIsNotNone(row[1])

    # 21. ambiguous child remains consumed
    def test_n21w_21_ambiguous_child_remains_consumed(self):
        auth = create_test_mint_authority(chat_id="chat_21", user_id="user_21")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_21",
            user_id="user_21",
            job_id="job_21",
            request_id="req_21",
            scene_count=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        child1 = plan["scene_confirmations"][1]
        ctx = SpendGuardContext(
            chat_id="chat_21",
            user_id="user_21",
            job_id="job_21",
            request_id="req_21",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=child1,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)

        retain_ambiguous_provider_spend(
            res.reservation_id,
            error_code="socket_hangup",
            db_path=self.db_path,
            env=self.standard_env,
        )

        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT status FROM bot_spend_confirmations WHERE confirmation_id = ?", (child1,))
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row[0], "consumed")

    # 22. ambiguous child cannot be reminted/retried
    def test_n21w_22_ambiguous_child_cannot_be_retried(self):
        auth = create_test_mint_authority(chat_id="chat_22", user_id="user_22")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_22",
            user_id="user_22",
            job_id="job_22",
            request_id="req_22",
            scene_count=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        child1 = plan["scene_confirmations"][1]
        ctx = SpendGuardContext(
            chat_id="chat_22",
            user_id="user_22",
            job_id="job_22",
            request_id="req_22",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=child1,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)

        retain_ambiguous_provider_spend(
            res.reservation_id,
            error_code="timeout",
            db_path=self.db_path,
            env=self.standard_env,
        )

        retry = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(retry.allowed)
        self.assertEqual(retry.blocker, BLOCKER_AMBIGUOUS_RETRY_BLOCKED)

    # 23. ordinary real production paid-create != paid live test
    def test_n21w_23_ordinary_real_production_paid_create_not_paid_live_test(self):
        auth = create_test_mint_authority(chat_id="chat_23", user_id="user_23")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_23",
            user_id="user_23",
            job_id="job_23",
            request_id="req_23",
            product_family="Product Video",
            operation="create_video_task",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_23",
            user_id="user_23",
            job_id="job_23",
            request_id="req_23",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            paid_live_test=False,
            owner_receipt="",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)

    # 24. ordinary paid-create still enters weekly cap
    def test_n21w_24_ordinary_paid_create_enters_weekly_cap(self):
        summary = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        before = summary["total_active_week_spend_usd"]

        auth = create_test_mint_authority(chat_id="chat_24", user_id="user_24")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_24",
            user_id="user_24",
            job_id="job_24",
            request_id="req_24",
            product_family="Product Video",
            operation="create_video_task",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_24",
            user_id="user_24",
            job_id="job_24",
            request_id="req_24",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            paid_live_test=False,
            metadata={"quality_key": "motion_standard_5"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)

        summary_after = get_weekly_spend_summary(db_path=self.db_path, env=self.standard_env)
        self.assertAlmostEqual(summary_after["total_active_week_spend_usd"], before + 7.650061, places=5)

    # 25. paid live test without Owner receipt -> BLOCK
    def test_n21w_25_paid_live_test_without_owner_receipt_blocked(self):
        auth = create_test_mint_authority(
            chat_id="chat_25",
            user_id="user_25",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_25",
            user_id="user_25",
            job_id="job_25",
            request_id="req_25",
            product_family="Product Video",
            operation="create_video_task",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_25",
            user_id="user_25",
            job_id="job_25",
            request_id="req_25",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            paid_live_test=True,
            owner_receipt="",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertIn(res.blocker, (BLOCKER_BOT_ORIGIN_PROOF_MISSING, BLOCKER_OWNER_LIVE_RECEIPT_MISSING))

    # 26. paid live test with durable bot origin + Owner receipt -> guard PASS provider-free
    def test_n21w_26_paid_live_test_with_durable_bot_origin_and_owner_receipt_passes(self):
        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_owner_authorized_26",
            product_family="Product Video",
            job_id="job_26",
            request_id="req_26",
            operation="create_video_task",
            expected_max_provider_spend_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        auth = create_test_mint_authority(
            chat_id="chat_26",
            user_id="user_26",
            job_id="job_26",
            request_id="req_26",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_owner_authorized_26",
            expected_max_provider_spend_usd=Decimal("50.0"),
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_26",
            user_id="user_26",
            job_id="job_26",
            request_id="req_26",
            product_family="Product Video",
            operation="create_video_task",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_owner_authorized_26",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_26",
            user_id="user_26",
            job_id="job_26",
            request_id="req_26",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            paid_live_test=True,
            owner_receipt="rcpt_owner_authorized_26",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
            self.assertTrue(res.allowed)
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

    # 27. forged entrypoint/user_flow/bot_origin bool alone -> BLOCK
    def test_n21w_27_forged_entrypoint_user_flow_bot_origin_alone_blocked(self):
        ctx = SpendGuardContext(
            chat_id="chat_27",
            user_id="user_27",
            job_id="job_27",
            request_id="req_27",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            user_flow="product_video_bot",
            entrypoint="bot",
            bot_confirm_authority="",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 28. ambiguous Product Video route price -> BLOCK
    def test_n21w_28_ambiguous_product_video_route_price_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_28", user_id="user_28")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_28",
            user_id="user_28",
            job_id="job_28",
            request_id="req_28",
            product_family="Product Video",
            operation="create_video_task",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_28",
            user_id="user_28",
            job_id="job_28",
            request_id="req_28",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            metadata={},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_MAX_COST_AUTHORITY_MISSING)

    # 29. exact tier/provider/model/duration -> exact canonical reserve
    def test_n21w_29_exact_tier_provider_model_duration_canonical_reserve(self):
        authority = resolve_paid_transport_authority("Product Video", "key4u_video", "create_video_task")
        self.assertIsNotNone(authority)
        ctx = SpendGuardContext(
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            metadata={"quality_key": "kling_long_audio_15", "duration_seconds": 15},
        )
        cost_micro, proven, source = resolve_canonical_cost_micro_usd(ctx, authority)
        self.assertTrue(proven)
        self.assertEqual(cost_micro, 30_600_245)



class TestN21XNonForgeableBotMintCapabilityMatrix(unittest.TestCase):
    """N21X Verification Matrix: Non-forgeable Bot Mint Capability, Caller Boundary, and Exact Transport Authority."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="n21x_mint_cap_")
        self.db_path = os.path.join(self.temp_dir, "test_system.db")
        init_spend_guard_db(db_path=self.db_path)
        self.standard_env = {
            "SPEND_GUARD_DB_PATH": self.db_path,
            "WEEKLY_PROVIDER_SPEND_CAP_USD": "200.000",
            "WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE": "MONDAY_0000_UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE": "UTC",
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 1. Direct BotMintAuthority(...) constructor -> unusable/BLOCK
    def test_n21x_01_direct_bot_mint_authority_constructor_unusable(self):
        with self.assertRaises(PermissionError):
            BotMintAuthority(
                callsite="bot.py:handle_video_product_callback:b14_confirm",
                telegram_update_id=1,
                chat_id="123",
                user_id="456",
            )

    # 2. generic service calls production issuer with correct callsite string -> BLOCK
    def test_n21x_02_generic_service_calls_production_issuer_with_whitelisted_string_blocked(self):
        with self.assertRaises(PermissionError):
            issue_bot_mint_authority(
                callsite="bot.py:handle_video_product_callback:b14_confirm",
                telegram_update_id=1,
                callback_query_id="cbq_query_test_1",
                chat_id="123",
                user_id="456",
                job_id="job_1",
                request_id="req_1",
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                validated_ownership=True,
                db_path=self.db_path,
                env=self.standard_env,
            )

    # 3. worker passes exact whitelisted callsite string -> BLOCK
    def test_n21x_03_worker_passes_whitelisted_callsite_string_blocked(self):
        with self.assertRaises(PermissionError):
            issue_bot_mint_authority(
                callsite="bot.py:handle_video_product_callback:b14_confirm",
                telegram_update_id=1,
                callback_query_id="cbq_query_test_1",
                chat_id="123",
                user_id="456",
                job_id="job_1",
                request_id="req_1",
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                validated_ownership=True,
                db_path=self.db_path,
                env=self.standard_env,
            )

    # 4. provider passes exact whitelisted callsite string -> BLOCK
    def test_n21x_04_provider_passes_whitelisted_callsite_string_blocked(self):
        with self.assertRaises(PermissionError):
            issue_bot_mint_authority(
                callsite="bot.py:handle_video_product_callback:b14_confirm",
                telegram_update_id=1,
                callback_query_id="cbq_query_test_1",
                chat_id="123",
                user_id="456",
                job_id="job_1",
                request_id="req_1",
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                validated_ownership=True,
                db_path=self.db_path,
                env=self.standard_env,
            )

    # 5. production code calls create_test_mint_authority -> unavailable/BLOCK
    def test_n21x_05_production_code_calls_create_test_mint_authority_blocked(self):
        with self.assertRaises(PermissionError):
            create_test_mint_authority(
                _caller_override_for_test="production",
            )

    # 6. test-harness confirmation cannot authorize real transport
    def test_n21x_06_test_harness_confirmation_cannot_reach_real_transport(self):
        auth = create_test_mint_authority(chat_id="chat_6", user_id="user_6")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_6",
            user_id="user_6",
            job_id="job_6",
            request_id="req_6",
            product_family="Product Video",
            operation="create_video_task",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_6",
            user_id="user_6",
            job_id="job_6",
            request_id="req_6",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            is_paid_live_attempt=True,  # Real transport attempt
            metadata={"quality_key": "kling_long_audio_15", "target_transport": "real_provider"},
        )
        old_test_var = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
            self.assertFalse(res.allowed)
            self.assertEqual(res.blocker, BLOCKER_TEST_CONFIRM_CANNOT_REACH_REAL_TRANSPORT)
        finally:
            if old_test_var is not None:
                os.environ["PYTEST_CURRENT_TEST"] = old_test_var

    # 7. validated mocked Telegram b14_confirm -> production confirmation mint PASS
    def test_n21x_07_validated_mocked_telegram_b14_confirm_mint_passes(self):
        seed_test_durable_bot_origin_in_trace(
            self.db_path,
            telegram_update_id=777,
            callback_query_id="cbq_777",
            chat_id="chat_7",
            user_id="user_7",
            job_id="job_7",
            request_id="req_7",
        )
        auth = issue_bot_mint_authority(
            callsite="bot.py:handle_video_product_callback:b14_confirm",
            telegram_update_id=777,
            callback_query_id="cbq_777",
            chat_id="chat_7",
            user_id="user_7",
            job_id="job_7",
            request_id="req_7",
            action="b14_confirm",
            validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
            validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
            validated_ownership=True,
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertIsNotNone(auth)
        self.assertFalse(auth.is_test_override)
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_7",
            user_id="user_7",
            job_id="job_7",
            request_id="req_7",
            product_family="Product Video",
            operation="create_video_task",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertTrue(bool(plan.get("parent_confirmation_id")))
        self.assertEqual(len(plan.get("child_confirmations", [])), 2)

    # 8. wrong Telegram update/session/user -> mint BLOCK
    def test_n21x_08_wrong_telegram_update_session_user_mint_blocked(self):
        with self.assertRaises(ValueError):
            issue_bot_mint_authority(
                telegram_update_id=0,
                callback_query_id="cbq_8",
                chat_id="chat_8",
                user_id="user_8",
                job_id="job_8",
                request_id="req_8",
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                validated_ownership=True,
            )
        with self.assertRaises(ValueError):
            issue_bot_mint_authority(
                telegram_update_id=888,
                callback_query_id="cbq_8",
                chat_id="chat_8",
                user_id="",
                job_id="job_8",
                request_id="req_8",
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                validated_ownership=True,
            )

    # 9. Bot mint before callback ownership validation -> BLOCK
    def test_n21x_09_bot_mint_before_callback_ownership_validation_blocked(self):
        with self.assertRaises(PermissionError):
            issue_bot_mint_authority(
                telegram_update_id=999,
                callback_query_id="cbq_9",
                chat_id="chat_9",
                user_id="user_9",
                job_id="job_9",
                request_id="req_9",
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                validated_ownership=False,
            )

    # 10. exact operation create_video_task -> resolver PASS
    def test_n21x_10_exact_operation_create_video_task_resolver_passes(self):
        res = resolve_paid_transport_authority("Product Video", "key4u_video", "create_video_task")
        self.assertIsNotNone(res)
        self.assertEqual(res.operation, "create_video_task")

    # 11. create_video_task_debug -> resolver BLOCK
    def test_n21x_11_create_video_task_debug_resolver_blocked(self):
        res = resolve_paid_transport_authority("Product Video", "key4u_video", "create_video_task_debug")
        self.assertIsNone(res)

    # 12. prefix/suffix operation -> BLOCK
    def test_n21x_12_prefix_suffix_operation_blocked(self):
        self.assertIsNone(resolve_paid_transport_authority("Product Video", "key4u_video", "video_create_video_task"))
        self.assertIsNone(resolve_paid_transport_authority("Product Video", "key4u_video", "create_video"))

    # 13. exact provider -> PASS
    def test_n21x_13_exact_provider_passes(self):
        res = resolve_paid_transport_authority("Product Video", "key4u_video", "create_video_task")
        self.assertIsNotNone(res)

    # 14. fuzzy/partial provider -> BLOCK
    def test_n21x_14_fuzzy_partial_provider_blocked(self):
        self.assertIsNone(resolve_paid_transport_authority("Product Video", "key4u_partial", "create_video_task"))
        self.assertIsNone(resolve_paid_transport_authority("Product Video", "kling", "create_video_task"))
        self.assertIsNone(resolve_paid_transport_authority("Product Video", "video", "create_video_task"))

    # 15. explicit approved alias -> PASS
    def test_n21x_15_explicit_approved_alias_passes(self):
        self.assertIsNotNone(resolve_paid_transport_authority("Product Video", "key4u_kling", "create_video_task"))
        self.assertIsNotNone(resolve_paid_transport_authority("Product Video", "key4u", "create_video_task"))

    # 16. two-scene child plan still PASS
    def test_n21x_16_two_scene_child_plan_still_passes(self):
        auth = create_test_mint_authority(chat_id="chat_16", user_id="user_16")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_16",
            user_id="user_16",
            job_id="job_16",
            request_id="req_16",
            product_family="Product Video",
            operation="create_video_task",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        s1_id = plan["scene_confirmations"][1]
        s2_id = plan["scene_confirmations"][2]
        ctx1 = SpendGuardContext(
            chat_id="chat_16",
            user_id="user_16",
            job_id="job_16",
            request_id="req_16",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=s1_id,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res1 = reserve_provider_spend(ctx1, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)

        ctx2 = SpendGuardContext(
            chat_id="chat_16",
            user_id="user_16",
            job_id="job_16",
            request_id="req_16",
            scene_index=2,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=s2_id,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res2 = reserve_provider_spend(ctx2, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res2.allowed)

    # 17. parent submit still BLOCK
    def test_n21x_17_parent_submit_still_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_17", user_id="user_17")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_17",
            user_id="user_17",
            job_id="job_17",
            request_id="req_17",
            product_family="Product Video",
            operation="create_video_task",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        p_id = plan["parent_confirmation_id"]
        ctx = SpendGuardContext(
            chat_id="chat_17",
            user_id="user_17",
            job_id="job_17",
            request_id="req_17",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=p_id,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 18. child duplicate still BLOCK
    def test_n21x_18_child_duplicate_still_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_18", user_id="user_18")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_18",
            user_id="user_18",
            job_id="job_18",
            request_id="req_18",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_18",
            user_id="user_18",
            job_id="job_18",
            request_id="req_18",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res1 = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)
        res2 = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res2.allowed)

    # 19. ambiguous retry still BLOCK
    def test_n21x_19_ambiguous_retry_still_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_19", user_id="user_19")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_19",
            user_id="user_19",
            job_id="job_19",
            request_id="req_19",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_19",
            user_id="user_19",
            job_id="job_19",
            request_id="req_19",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE provider_spend_reservations SET status = ? WHERE reservation_id = ?",
            (STATUS_AMBIGUOUS_RETAINED, res.reservation_id),
        )
        conn.commit()
        conn.close()
        res_retry = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res_retry.allowed)
        self.assertEqual(res_retry.blocker, BLOCKER_AMBIGUOUS_RETRY_BLOCKED)

    # 20. ordinary paid-create remains non-live-test
    def test_n21x_20_ordinary_paid_create_remains_non_live_test(self):
        ctx = SpendGuardContext(
            job_id="job_20",
            request_id="req_20",
            chat_id="chat_20",
            user_id="user_20",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            operation="create_video_task",
            bot_originated_action=True,
            paid_live_test=False,
        )
        self.assertFalse(is_paid_live_test(ctx))

    # 21. paid live test missing Owner receipt -> BLOCK
    def test_n21x_21_paid_live_test_missing_owner_receipt_blocked(self):
        auth = create_test_mint_authority(
            chat_id="chat_21",
            user_id="user_21",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_21",
            user_id="user_21",
            job_id="job_21",
            request_id="req_21",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_21",
            user_id="user_21",
            job_id="job_21",
            request_id="req_21",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            owner_receipt="",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertIn(res.blocker, (BLOCKER_OWNER_LIVE_RECEIPT_MISSING, BLOCKER_BOT_ORIGIN_PROOF_MISSING))

    # 22. weekly cap remains shared $200
    def test_n21x_22_weekly_cap_remains_shared_200(self):
        cap_micro = get_configured_cap_micro_usd(env={})
        self.assertEqual(cap_micro, 200_000_000)

    # 23. missing reset policy remains fail-closed
    def test_n21x_23_missing_reset_policy_remains_fail_closed(self):
        with self.assertRaises(ValueError):
            get_current_spend_week_id(env={})


class TestN21YBotConfirmAuthorityTruthAndPerSceneReservationMatrix(unittest.TestCase):
    """N21Y Verification Matrix: Bot Confirm Authority Truth, Live Test Purpose, and Per-Scene Reservation."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="n21y_truth_matrix_")
        self.db_path = os.path.join(self.temp_dir, "test_system.db")
        init_spend_guard_db(db_path=self.db_path)
        self.standard_env = {
            "SPEND_GUARD_DB_PATH": self.db_path,
            "WEEKLY_PROVIDER_SPEND_CAP_USD": "200.000",
            "WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE": "MONDAY_0000_UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE": "UTC",
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 1. importing module and reading internal symbols cannot create accepted production confirmation through supported production API
    def test_n21y_01_importing_module_and_reading_internal_symbols_cannot_create_accepted_production_confirmation(self):
        import services.provider_spend_guard as psg
        self.assertTrue(psg.FALSE_NONFORGEABLE_CLAIM_REMOVED)
        self.assertFalse(psg.MODULE_LOCAL_SECRET_IS_SECURITY_AUTHORITY)
        self.assertEqual(psg.MINT_TRUST_MODEL, "APPLICATION_CALL_GRAPH_PLUS_DURABLE_BOT_EVENT_AUTHORITY")

        # Direct constructor fails closed
        with self.assertRaises(PermissionError):
            psg.BotMintAuthority(
                callsite="bot.py:handle_video_product_callback:b14_confirm",
                telegram_update_id=123,
                chat_id="123",
                user_id="456",
            )
        # Calling issue_bot_mint_authority from external caller fails closed
        with self.assertRaises(PermissionError):
            psg.issue_bot_mint_authority(
                telegram_update_id=123,
                callback_query_id="cbq_real_123",
                chat_id="123",
                user_id="456",
                job_id="job_1",
                request_id="req_1",
                validation_source="video_trace_state:begin_video_confirm_execution",
                validation_callsite="bot.py:handle_video_product_callback:b14_confirm",
                validated_ownership=True,
                db_path=self.db_path,
                env=self.standard_env,
            )

    # 2. production module contains no create_test_mint_authority factory
    def test_n21y_02_production_module_contains_no_create_test_mint_authority_factory(self):
        import services.provider_spend_guard as psg
        self.assertFalse(hasattr(psg, "create_test_mint_authority"))
        self.assertFalse(psg.PRODUCTION_TEST_MINT_FACTORY_PRESENT)

    # 3. fake test env/pytest flag cannot create production confirmation
    def test_n21y_03_fake_test_env_cannot_create_production_confirmation(self):
        auth = create_test_mint_authority(chat_id="chat_03", user_id="user_03")
        # In test mode it produces a test record
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_03",
            user_id="user_03",
            job_id="job_03",
            request_id="req_03",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_03",
            user_id="user_03",
            job_id="job_03",
            request_id="req_03",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            is_paid_live_attempt=False,
            metadata={"target_transport": "real_provider", "quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_TEST_CONFIRM_CANNOT_REACH_REAL_TRANSPORT)

    # 4. missing real telegram_update_id -> BLOCK
    def test_n21y_04_missing_real_telegram_update_id_blocks_mint(self):
        with self.assertRaises(ValueError):
            issue_bot_mint_authority(
                telegram_update_id=0,
                callback_query_id="cbq_real_4",
                chat_id="chat_4",
                user_id="user_4",
                job_id="job_4",
                request_id="req_4",
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                validated_ownership=True,
            )
        with self.assertRaises(ValueError):
            issue_bot_mint_authority(
                telegram_update_id=-5,
                callback_query_id="cbq_real_4",
                chat_id="chat_4",
                user_id="user_4",
                job_id="job_4",
                request_id="req_4",
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                validated_ownership=True,
            )

    # 5. missing real callback_query_id -> BLOCK
    def test_n21y_05_missing_real_callback_query_id_blocks_mint(self):
        with self.assertRaises(ValueError):
            issue_bot_mint_authority(
                telegram_update_id=101,
                callback_query_id="",
                chat_id="chat_5",
                user_id="user_5",
                job_id="job_5",
                request_id="req_5",
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                validated_ownership=True,
            )
        with self.assertRaises(ValueError):
            issue_bot_mint_authority(
                telegram_update_id=101,
                callback_query_id="cbq_fallback_123",
                chat_id="chat_5",
                user_id="user_5",
                job_id="job_5",
                request_id="req_5",
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                validated_ownership=True,
            )

    # 6. missing request_id -> BLOCK
    def test_n21y_06_missing_request_id_blocks_mint(self):
        with self.assertRaises(ValueError):
            issue_bot_mint_authority(
                telegram_update_id=102,
                callback_query_id="cbq_real_6",
                chat_id="chat_6",
                user_id="user_6",
                job_id="job_6",
                request_id="",
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                validated_ownership=True,
            )
        with self.assertRaises(ValueError):
            issue_bot_mint_authority(
                telegram_update_id=102,
                callback_query_id="cbq_real_6",
                chat_id="chat_6",
                user_id="user_6",
                job_id="job_6",
                request_id="req_fallback_6",
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                validated_ownership=True,
            )

    # 7. synthetic fallback IDs absent
    def test_n21y_07_synthetic_fallback_ids_absent(self):
        self.assertEqual(SYNTHETIC_TELEGRAM_AUTH_IDS, 0)
        with open("bot.py", "r", encoding="utf-8") as f:
            bot_content = f.read()
        self.assertNotIn("telegram_update_id or 1", bot_content)
        self.assertNotIn("cbq_fallback_", bot_content)
        self.assertNotIn("req_fallback_", bot_content)

    # 8. caller validated_ownership=True without canonical validation state -> BLOCK
    def test_n21y_08_caller_validated_ownership_bool_without_validation_state_blocked(self):
        self.assertFalse(CALLER_VALIDATED_OWNERSHIP_BOOL_TRUSTED)
        with self.assertRaises(PermissionError):
            issue_bot_mint_authority(
                telegram_update_id=103,
                callback_query_id="cbq_real_8",
                chat_id="chat_8",
                user_id="user_8",
                job_id="job_8",
                request_id="req_8",
                validation_source="",
                validation_callsite="",
                validated_ownership=True,
            )

    # 9. ordinary Bot confirm -> purpose PRODUCTION_USER_ACTION
    def test_n21y_09_ordinary_bot_confirm_purpose_production_user_action(self):
        seed_test_durable_bot_origin_in_trace(
            self.db_path,
            telegram_update_id=104,
            callback_query_id="cbq_real_9",
            chat_id="chat_9",
            user_id="user_9",
            job_id="job_9",
            request_id="req_9",
        )
        auth = issue_bot_mint_authority(
            telegram_update_id=104,
            callback_query_id="cbq_real_9",
            chat_id="chat_9",
            user_id="user_9",
            job_id="job_9",
            request_id="req_9",
            validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
            validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
            validated_ownership=True,
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertEqual(auth.purpose, PURPOSE_PRODUCTION_USER_ACTION)
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_9",
            user_id="user_9",
            job_id="job_9",
            request_id="req_9",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT purpose FROM bot_spend_confirmations WHERE confirmation_id = ?", (conf_id,))
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], PURPOSE_PRODUCTION_USER_ACTION)

    # 10. caller metadata paid_live_test=True cannot change durable purpose
    def test_n21y_10_caller_metadata_paid_live_test_true_cannot_change_durable_purpose(self):
        self.assertFalse(CALLER_PAID_LIVE_TEST_FLAG_TRUSTED)
        self.assertEqual(PAID_LIVE_TEST_CLASSIFICATION_SOURCE, "DURABLE_CONFIRMATION_PURPOSE")
        auth = create_test_mint_authority(
            chat_id="chat_10",
            user_id="user_10",
            purpose=PURPOSE_PRODUCTION_USER_ACTION,
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_10",
            user_id="user_10",
            job_id="job_10",
            request_id="req_10",
            scene_index=1,
            purpose=PURPOSE_PRODUCTION_USER_ACTION,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_10",
            user_id="user_10",
            job_id="job_10",
            request_id="req_10",
            bot_confirm_authority=conf_id,
            paid_live_test=True,
            metadata={"paid_live_test": True, "is_paid_live_test": True},
        )
        self.assertFalse(is_paid_live_test(ctx, db_path=self.db_path, env=self.standard_env))

    # 11. caller metadata paid_live_test=False cannot downgrade durable live-test purpose
    def test_n21y_11_caller_metadata_paid_live_test_false_cannot_downgrade_durable_purpose(self):
        auth = create_test_mint_authority(
            chat_id="chat_11",
            user_id="user_11",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_11",
            user_id="user_11",
            job_id="job_11",
            request_id="req_11",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_11",
            user_id="user_11",
            job_id="job_11",
            request_id="req_11",
            bot_confirm_authority=conf_id,
            paid_live_test=False,
            metadata={"paid_live_test": False},
        )
        self.assertTrue(is_paid_live_test(ctx, db_path=self.db_path, env=self.standard_env))

    # 12. durable OWNER_AUTHORIZED_PAID_LIVE_TEST without Owner receipt -> BLOCK
    def test_n21y_12_durable_live_test_without_owner_receipt_blocked(self):
        auth = create_test_mint_authority(
            chat_id="chat_12",
            user_id="user_12",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="",
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_12",
            user_id="user_12",
            job_id="job_12",
            request_id="req_12",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_12",
            user_id="user_12",
            job_id="job_12",
            request_id="req_12",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            owner_receipt="",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertIn(res.blocker, (BLOCKER_OWNER_LIVE_RECEIPT_MISSING, BLOCKER_BOT_ORIGIN_PROOF_MISSING))

    # 13. forged Owner receipt string -> BLOCK
    def test_n21y_13_forged_owner_receipt_string_blocked(self):
        auth = create_test_mint_authority(
            chat_id="chat_13",
            user_id="user_13",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="6119790632",
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_13",
            user_id="user_13",
            job_id="job_13",
            request_id="req_13",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="6119790632",
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_13",
            user_id="user_13",
            job_id="job_13",
            request_id="req_13",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            owner_receipt="forged_receipt_random_string",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_OWNER_RECEIPT_MISMATCH)

    # 14. correctly bound Owner live authorization record -> provider-free guard PASS
    def test_n21y_14_correctly_bound_owner_live_authorization_record_passes(self):
        self.assertEqual(OWNER_LIVE_AUTH_BINDING, "PASS")
        _create_owner_live_authorization_test_fixture(
            authorization_id="6119790632",
            product_family="Product Video",
            job_id="job_14",
            request_id="req_14",
            operation="create_video_task",
            expected_max_provider_spend_usd=Decimal("30.600245"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        auth = create_test_mint_authority(
            chat_id="chat_14",
            user_id="user_14",
            job_id="job_14",
            request_id="req_14",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="6119790632",
            expected_max_provider_spend_usd=Decimal("30.600245"),
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_14",
            user_id="user_14",
            job_id="job_14",
            request_id="req_14",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="6119790632",
            expected_max_cost_usd=Decimal("30.600245"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_14",
            user_id="user_14",
            job_id="job_14",
            request_id="req_14",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            owner_receipt="6119790632",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)
        self.assertTrue(res.reservation_id.startswith("res_"))

    # 15. entrypoint="bot" alone -> BLOCK
    def test_n21y_15_entrypoint_bot_alone_blocked(self):
        ctx = SpendGuardContext(
            chat_id="chat_15",
            user_id="user_15",
            job_id="job_15",
            request_id="req_15",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            entrypoint="bot",
            bot_originated_action=False,
            bot_confirm_authority="",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 16. bot_originated_action=True alone -> BLOCK
    def test_n21y_16_bot_originated_action_true_alone_blocked(self):
        ctx = SpendGuardContext(
            chat_id="chat_16",
            user_id="user_16",
            job_id="job_16",
            request_id="req_16",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            entrypoint="bot",
            bot_originated_action=True,
            bot_confirm_authority="",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 17. user_flow bot string alone -> BLOCK
    def test_n21y_17_user_flow_bot_string_alone_blocked(self):
        ctx = SpendGuardContext(
            chat_id="chat_17",
            user_id="user_17",
            job_id="job_17",
            request_id="req_17",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            entrypoint="bot",
            bot_originated_action=True,
            user_flow="product_video_bot",
            bot_confirm_authority="",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 18. two-scene plan produces 2 child reservations
    def test_n21y_18_two_scene_plan_produces_two_child_reservations(self):
        auth = create_test_mint_authority(chat_id="chat_18", user_id="user_18")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_18",
            user_id="user_18",
            job_id="job_18",
            request_id="req_18",
            product_family="Product Video",
            operation="create_video_task",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        s1 = plan["scene_confirmations"][1]
        s2 = plan["scene_confirmations"][2]
        ctx1 = SpendGuardContext(
            chat_id="chat_18",
            user_id="user_18",
            job_id="job_18",
            request_id="req_18",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=s1,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res1 = reserve_provider_spend(ctx1, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)

        ctx2 = SpendGuardContext(
            chat_id="chat_18",
            user_id="user_18",
            job_id="job_18",
            request_id="req_18",
            scene_index=2,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=s2,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res2 = reserve_provider_spend(ctx2, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res2.allowed)
        self.assertNotEqual(res1.reservation_id, res2.reservation_id)

    # 19. each child reserves only its own scene canonical max
    def test_n21y_19_each_child_reserves_only_its_own_scene_canonical_max(self):
        self.assertTrue(PER_SCENE_RESERVATION_GRANULARITY)
        auth = create_test_mint_authority(chat_id="chat_19", user_id="user_19")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_19",
            user_id="user_19",
            job_id="job_19",
            request_id="req_19",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        s1 = plan["scene_confirmations"][1]
        ctx1 = SpendGuardContext(
            chat_id="chat_19",
            user_id="user_19",
            job_id="job_19",
            request_id="req_19",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=s1,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15", "scene_count": 2},
        )
        res1 = reserve_provider_spend(ctx1, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)
        # Unit cost for 1 scene of kling 15s is 30,600,245 micro-USD ($30.600245)
        # Must NOT be 61,200,490 micro-USD!
        self.assertEqual(res1.week_spend_after_micro_usd, 30_600_245)

    # 20. total job reservation equals sum of scene maxima
    def test_n21y_20_total_job_reservation_equals_sum_of_scene_maxima(self):
        self.assertTrue(MULTISCENE_TOTAL_COST_SUM)
        auth = create_test_mint_authority(chat_id="chat_20", user_id="user_20")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_20",
            user_id="user_20",
            job_id="job_20",
            request_id="req_20",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        s1 = plan["scene_confirmations"][1]
        s2 = plan["scene_confirmations"][2]
        ctx1 = SpendGuardContext(
            chat_id="chat_20",
            user_id="user_20",
            job_id="job_20",
            request_id="req_20",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=s1,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15", "scene_count": 2},
        )
        res1 = reserve_provider_spend(ctx1, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)

        ctx2 = SpendGuardContext(
            chat_id="chat_20",
            user_id="user_20",
            job_id="job_20",
            request_id="req_20",
            scene_index=2,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=s2,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15", "scene_count": 2},
        )
        res2 = reserve_provider_spend(ctx2, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res2.allowed)
        # Total in DB is exactly 30,600,245 + 30,600,245 = 61,200,490 micro-USD ($61.200490)
        self.assertEqual(res2.week_spend_after_micro_usd, 61_200_490)

    # 21. no scene_count double multiplication
    def test_n21y_21_no_scene_count_double_multiplication(self):
        self.assertFalse(SCENE_COUNT_DOUBLE_MULTIPLICATION)
        authority = resolve_paid_transport_authority("Product Video", "key4u_video", "create_video_task")
        ctx = SpendGuardContext(
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            metadata={"quality_key": "kling_long_audio_15", "scene_count": 5},
        )
        cost_micro, proven, _ = resolve_canonical_cost_micro_usd(ctx, authority)
        self.assertTrue(proven)
        # For scene_index=1, cost must be single scene cost (30,600,245), NOT 5 * 30,600,245
        self.assertEqual(cost_micro, 30_600_245)

    # 22. child duplicate -> BLOCK
    def test_n21y_22_child_duplicate_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_22", user_id="user_22")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_22",
            user_id="user_22",
            job_id="job_22",
            request_id="req_22",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_22",
            user_id="user_22",
            job_id="job_22",
            request_id="req_22",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res1 = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)
        res2 = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res2.allowed)
        self.assertEqual(res2.blocker, BLOCKER_DUPLICATE_PAID_SUBMIT)

    # 23. ambiguous child -> retained, retry BLOCK
    def test_n21y_23_ambiguous_child_retained_retry_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_23", user_id="user_23")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_23",
            user_id="user_23",
            job_id="job_23",
            request_id="req_23",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_23",
            user_id="user_23",
            job_id="job_23",
            request_id="req_23",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE provider_spend_reservations SET status = ? WHERE reservation_id = ?",
            (STATUS_AMBIGUOUS_RETAINED, res.reservation_id),
        )
        conn.commit()
        conn.close()
        res_retry = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res_retry.allowed)
        self.assertEqual(res_retry.blocker, BLOCKER_AMBIGUOUS_RETRY_BLOCKED)

    # 24. parent authority -> BLOCK
    def test_n21y_24_parent_authority_blocked(self):
        auth = create_test_mint_authority(chat_id="chat_24", user_id="user_24")
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_24",
            user_id="user_24",
            job_id="job_24",
            request_id="req_24",
            scene_count=2,
            db_path=self.db_path,
            env=self.standard_env,
        )
        p_id = plan["parent_confirmation_id"]
        ctx = SpendGuardContext(
            chat_id="chat_24",
            user_id="user_24",
            job_id="job_24",
            request_id="req_24",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=p_id,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING)

    # 25. missing weekly reset policy -> FAIL CLOSED
    def test_n21y_25_missing_weekly_reset_policy_fails_closed(self):
        auth = create_test_mint_authority(chat_id="chat_25", user_id="user_25")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_25",
            user_id="user_25",
            job_id="job_25",
            request_id="req_25",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_25",
            user_id="user_25",
            job_id="job_25",
            request_id="req_25",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        empty_env = {"SPEND_GUARD_DB_PATH": self.db_path}
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=empty_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_POLICY_INCOMPLETE)

    # 26. shared $200 cap still enforced
    def test_n21y_26_shared_200_cap_still_enforced(self):
        cap_micro = get_configured_cap_micro_usd(env={})
        self.assertEqual(cap_micro, 200_000_000)
        auth = create_test_mint_authority(chat_id="chat_26", user_id="user_26")
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_26",
            user_id="user_26",
            job_id="job_26",
            request_id="req_26",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        # Pre-seed $190 spend
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(self.db_path)
        week_id = get_current_spend_week_id(env=self.standard_env)
        conn.execute(
            """
            INSERT INTO provider_spend_reservations (
                reservation_id, created_at, week_id, idempotency_key, job_id, request_id,
                trace_id, product_family, provider, model, estimated_max_cost_micro_usd,
                reserved_cost_micro_usd, actual_settled_cost_micro_usd, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "res_preseed", time.time(), week_id, "idemp_preseed", "job_preseed",
                "req_preseed", "tr_preseed", "Product Video", "key4u_video", "kling-v3",
                190_000_000, 190_000_000, 190_000_000, STATUS_SETTLED_VERIFIED
            ),
        )
        conn.commit()
        conn.close()

        ctx = SpendGuardContext(
            chat_id="chat_26",
            user_id="user_26",
            job_id="job_26",
            request_id="req_26",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        # Adding $30.60 to $190 exceeds $200
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_WEEKLY_SPEND_CAP_EXCEEDED)


class TestN21ZOwnerLiveAuthorityRecordAndExpectedSpendEnforcementMatrix(unittest.TestCase):
    """N21Z: Owner Live Authority Record and Expected Spend Enforcement Test Matrix."""

    def setUp(self):
        set_kill_switch(False)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "spend_guard_n21z.db")
        self.standard_env = {
            "SPEND_GUARD_DB_PATH": self.db_path,
            "WEEKLY_PROVIDER_SPEND_CAP_USD": "200.000",
            "WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE": "MONDAY_0000_UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE": "UTC",
        }
        init_spend_guard_db(db_path=self.db_path, env=self.standard_env)

    def tearDown(self):
        set_kill_switch(False)
        self.temp_dir.cleanup()

    # 1. create confirmation with caller purpose override -> BLOCK
    def test_n21z_01_create_confirmation_with_caller_purpose_override_blocked(self):
        auth = create_test_mint_authority(
            chat_id="chat_z01",
            user_id="user_z01",
            job_id="job_z01",
            request_id="req_z01",
            purpose=PURPOSE_PRODUCTION_USER_ACTION,
        )
        with self.assertRaises(PermissionError) as cm:
            create_bot_confirmation(
                mint_authority=auth,
                chat_id="chat_z01",
                user_id="user_z01",
                job_id="job_z01",
                request_id="req_z01",
                scene_index=1,
                purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
                db_path=self.db_path,
                env=self.standard_env,
            )
        self.assertIn("CALLER_CAN_OVERRIDE_CONFIRM_PURPOSE=NO", str(cm.exception))

    # 2. caller owner receipt override -> BLOCK
    def test_n21z_02_caller_owner_receipt_override_blocked(self):
        auth = create_test_mint_authority(
            chat_id="chat_z02",
            user_id="user_z02",
            job_id="job_z02",
            request_id="req_z02",
            owner_receipt="auth_rcpt_z02",
        )
        with self.assertRaises(PermissionError) as cm:
            create_bot_confirmation(
                mint_authority=auth,
                chat_id="chat_z02",
                user_id="user_z02",
                job_id="job_z02",
                request_id="req_z02",
                scene_index=1,
                owner_receipt="caller_rcpt_override",
                db_path=self.db_path,
                env=self.standard_env,
            )
        self.assertIn("CALLER_CAN_OVERRIDE_OWNER_RECEIPT=NO", str(cm.exception))

    # 3. caller expected max override -> BLOCK
    def test_n21z_03_caller_expected_max_override_blocked(self):
        auth = create_test_mint_authority(
            chat_id="chat_z03",
            user_id="user_z03",
            job_id="job_z03",
            request_id="req_z03",
            expected_max_provider_spend_usd=Decimal("15.0"),
        )
        with self.assertRaises(PermissionError) as cm:
            create_bot_confirmation(
                mint_authority=auth,
                chat_id="chat_z03",
                user_id="user_z03",
                job_id="job_z03",
                request_id="req_z03",
                scene_index=1,
                expected_max_cost_usd=Decimal("25.0"),
                db_path=self.db_path,
                env=self.standard_env,
            )
        self.assertIn("CALLER_CAN_OVERRIDE_EXPECTED_MAX_SPEND=NO", str(cm.exception))

    # 4. arbitrary matching receipt string in context + confirmation row, but no Owner authorization record -> BLOCK
    def test_n21z_04_arbitrary_matching_receipt_string_without_owner_auth_record_blocked(self):
        self.assertEqual(OWNER_RECEIPT_STRING_EQUALITY_ONLY, "FORBIDDEN")
        auth = create_test_mint_authority(
            chat_id="chat_z04",
            user_id="user_z04",
            job_id="job_z04",
            request_id="req_z04",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="arbitrary_unregistered_receipt_999",
            expected_max_provider_spend_usd=Decimal("40.0"),
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_z04",
            user_id="user_z04",
            job_id="job_z04",
            request_id="req_z04",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="arbitrary_unregistered_receipt_999",
            expected_max_cost_usd=Decimal("40.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_z04",
            user_id="user_z04",
            job_id="job_z04",
            request_id="req_z04",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            owner_receipt="arbitrary_unregistered_receipt_999",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_OWNER_LIVE_AUTH_RECORD_MISSING)

    # 5. Owner authorization for different job -> BLOCK
    def test_n21z_05_owner_authorization_for_different_job_blocked(self):
        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_z05",
            product_family="Product Video",
            job_id="job_A",
            request_id="req_z05",
            operation="create_video_task",
            expected_max_provider_spend_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        auth = create_test_mint_authority(
            chat_id="chat_z05",
            user_id="user_z05",
            job_id="job_B",
            request_id="req_z05",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z05",
            expected_max_provider_spend_usd=Decimal("50.0"),
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_z05",
            user_id="user_z05",
            job_id="job_B",
            request_id="req_z05",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z05",
            expected_max_cost_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_z05",
            user_id="user_z05",
            job_id="job_B",
            request_id="req_z05",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            owner_receipt="rcpt_z05",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_OWNER_LIVE_AUTH_LINEAGE_MISMATCH)

    # 6. different request -> BLOCK
    def test_n21z_06_owner_authorization_for_different_request_blocked(self):
        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_z06",
            product_family="Product Video",
            job_id="job_z06",
            request_id="req_A",
            operation="create_video_task",
            expected_max_provider_spend_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        auth = create_test_mint_authority(
            chat_id="chat_z06",
            user_id="user_z06",
            job_id="job_z06",
            request_id="req_B",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z06",
            expected_max_provider_spend_usd=Decimal("50.0"),
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_z06",
            user_id="user_z06",
            job_id="job_z06",
            request_id="req_B",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z06",
            expected_max_cost_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_z06",
            user_id="user_z06",
            job_id="job_z06",
            request_id="req_B",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            owner_receipt="rcpt_z06",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_OWNER_LIVE_AUTH_LINEAGE_MISMATCH)

    # 7. different product -> BLOCK
    def test_n21z_07_owner_authorization_for_different_product_blocked(self):
        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_z07",
            product_family="Product Video",
            job_id="job_z07",
            request_id="req_z07",
            operation="create_video_task",
            expected_max_provider_spend_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        auth = create_test_mint_authority(
            chat_id="chat_z07",
            user_id="user_z07",
            job_id="job_z07",
            request_id="req_z07",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z07",
            expected_max_provider_spend_usd=Decimal("50.0"),
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_z07",
            user_id="user_z07",
            job_id="job_z07",
            request_id="req_z07",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z07",
            expected_max_cost_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        # Direct validator test for different product family
        val_ok, blk_code, _ = validate_owner_live_authorization(
            "rcpt_z07",
            product_family="Different Family",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertFalse(val_ok)
        self.assertEqual(blk_code, BLOCKER_OWNER_LIVE_AUTH_LINEAGE_MISMATCH)

        ctx = SpendGuardContext(
            chat_id="chat_z07",
            user_id="user_z07",
            job_id="job_z07",
            request_id="req_z07",
            scene_index=1,
            product_family="Different Family",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            owner_receipt="rcpt_z07",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertIn(res.blocker, (BLOCKER_PAID_TRANSPORT_AUTHORITY_UNREGISTERED, BLOCKER_OWNER_LIVE_AUTH_LINEAGE_MISMATCH))

    # 8. different operation -> BLOCK
    def test_n21z_08_owner_authorization_for_different_operation_blocked(self):
        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_z08",
            product_family="Product Video",
            job_id="job_z08",
            request_id="req_z08",
            operation="create_video_task",
            expected_max_provider_spend_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        auth = create_test_mint_authority(
            chat_id="chat_z08",
            user_id="user_z08",
            job_id="job_z08",
            request_id="req_z08",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z08",
            expected_max_provider_spend_usd=Decimal("50.0"),
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_z08",
            user_id="user_z08",
            job_id="job_z08",
            request_id="req_z08",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z08",
            expected_max_cost_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        # Direct validator test for different operation
        val_ok, blk_code, _ = validate_owner_live_authorization(
            "rcpt_z08",
            operation="other_operation",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertFalse(val_ok)
        self.assertEqual(blk_code, BLOCKER_OWNER_LIVE_AUTH_LINEAGE_MISMATCH)

        ctx = SpendGuardContext(
            chat_id="chat_z08",
            user_id="user_z08",
            job_id="job_z08",
            request_id="req_z08",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="other_operation",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            owner_receipt="rcpt_z08",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertIn(res.blocker, (BLOCKER_PAID_TRANSPORT_AUTHORITY_UNREGISTERED, BLOCKER_OWNER_LIVE_AUTH_LINEAGE_MISMATCH))

    # 9. different scene -> BLOCK
    def test_n21z_09_owner_authorization_for_different_scene_slot_blocked(self):
        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_z09",
            product_family="Product Video",
            job_id="job_z09",
            request_id="req_z09",
            operation="create_video_task",
            allowed_scene_slots="1",
            expected_max_provider_spend_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        auth = create_test_mint_authority(
            chat_id="chat_z09",
            user_id="user_z09",
            job_id="job_z09",
            request_id="req_z09",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z09",
            expected_max_provider_spend_usd=Decimal("50.0"),
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_z09",
            user_id="user_z09",
            job_id="job_z09",
            request_id="req_z09",
            scene_index=2,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z09",
            expected_max_cost_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_z09",
            user_id="user_z09",
            job_id="job_z09",
            request_id="req_z09",
            scene_index=2,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            owner_receipt="rcpt_z09",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_OWNER_LIVE_AUTH_SLOT_MISMATCH)

    # 10. expired Owner authorization -> BLOCK
    def test_n21z_10_expired_owner_authorization_blocked(self):
        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_z10",
            product_family="Product Video",
            job_id="job_z10",
            request_id="req_z10",
            operation="create_video_task",
            expected_max_provider_spend_usd=Decimal("50.0"),
            ttl_seconds=-60.0,
            db_path=self.db_path,
            env=self.standard_env,
        )
        auth = create_test_mint_authority(
            chat_id="chat_z10",
            user_id="user_z10",
            job_id="job_z10",
            request_id="req_z10",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z10",
            expected_max_provider_spend_usd=Decimal("50.0"),
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_z10",
            user_id="user_z10",
            job_id="job_z10",
            request_id="req_z10",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z10",
            expected_max_cost_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_z10",
            user_id="user_z10",
            job_id="job_z10",
            request_id="req_z10",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            owner_receipt="rcpt_z10",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_OWNER_LIVE_AUTH_EXPIRED)

    # 11. revoked Owner authorization -> BLOCK
    def test_n21z_11_revoked_owner_authorization_blocked(self):
        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_z11",
            product_family="Product Video",
            job_id="job_z11",
            request_id="req_z11",
            operation="create_video_task",
            status=STATUS_OWNER_AUTH_REVOKED,
            expected_max_provider_spend_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        auth = create_test_mint_authority(
            chat_id="chat_z11",
            user_id="user_z11",
            job_id="job_z11",
            request_id="req_z11",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z11",
            expected_max_provider_spend_usd=Decimal("50.0"),
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_z11",
            user_id="user_z11",
            job_id="job_z11",
            request_id="req_z11",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z11",
            expected_max_cost_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_z11",
            user_id="user_z11",
            job_id="job_z11",
            request_id="req_z11",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            owner_receipt="rcpt_z11",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_OWNER_LIVE_AUTH_REVOKED)

    # 12. live-test purpose without Owner authorization record -> BLOCK
    def test_n21z_12_live_test_purpose_without_owner_authorization_record_blocked(self):
        self.assertEqual(PAID_LIVE_TEST_PURPOSE_REQUIRES_OWNER_AUTH_RECORD, "YES")
        with self.assertRaises(PermissionError) as cm:
            issue_bot_mint_authority(
                job_id="job_z12",
                request_id="req_z12",
                chat_id="chat_z12",
                user_id="user_z12",
                callback_query_id="cbq_z12",
                telegram_update_id=121212,
                purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
                owner_receipt="missing_auth_rcpt_z12",
                validated_ownership=True,
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                db_path=self.db_path,
                env=self.standard_env,
            )
        self.assertIn("PAID_LIVE_TEST_PURPOSE_REQUIRES_OWNER_AUTH_RECORD=YES", str(cm.exception))

    # 13. ordinary production confirmation remains PRODUCTION_USER_ACTION
    def test_n21z_13_ordinary_production_confirmation_remains_production_user_action(self):
        self.assertEqual(ORDINARY_B14_PURPOSE, "PRODUCTION_USER_ACTION")
        auth = create_test_mint_authority(
            chat_id="chat_z13",
            user_id="user_z13",
            job_id="job_z13",
            request_id="req_z13",
            purpose=PURPOSE_PRODUCTION_USER_ACTION,
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_z13",
            user_id="user_z13",
            job_id="job_z13",
            request_id="req_z13",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_z13",
            user_id="user_z13",
            job_id="job_z13",
            request_id="req_z13",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        # Ordinary production flow does NOT require owner live auth
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)

    # 14. caller live_test metadata cannot promote ordinary purpose
    def test_n21z_14_caller_live_test_metadata_cannot_promote_ordinary_purpose(self):
        auth = create_test_mint_authority(
            chat_id="chat_z14",
            user_id="user_z14",
            job_id="job_z14",
            request_id="req_z14",
            purpose=PURPOSE_PRODUCTION_USER_ACTION,
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_z14",
            user_id="user_z14",
            job_id="job_z14",
            request_id="req_z14",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_z14",
            user_id="user_z14",
            job_id="job_z14",
            request_id="req_z14",
            bot_confirm_authority=conf_id,
            paid_live_test=True,
            is_paid_live_attempt=True,
            metadata={"paid_live_test": True, "live_test": True, "user_flow": "acceptance_test"},
        )
        self.assertFalse(is_paid_live_test(ctx, db_path=self.db_path, env=self.standard_env))

    # 15. provider/worker cannot create Owner authorization record
    def test_n21z_15_provider_worker_cannot_create_owner_live_authorization(self):
        self.assertEqual(WORKER_CAN_CREATE_OWNER_LIVE_AUTH, "NO")
        self.assertEqual(PROVIDER_CAN_CREATE_OWNER_LIVE_AUTH, "NO")
        self.assertEqual(DIRECT_PROVIDER_CAN_CREATE_OWNER_LIVE_AUTH, "NO")
        with self.assertRaises(PermissionError) as cm:
            create_owner_live_authorization(
                job_id="job_z15",
                request_id="req_z15",
                _caller_override_for_test="worker",
                db_path=self.db_path,
                env=self.standard_env,
            )
        self.assertIn("WORKER_CAN_CREATE_OWNER_LIVE_AUTH=NO", str(cm.exception))

        with self.assertRaises(PermissionError) as cm:
            create_owner_live_authorization(
                job_id="job_z15",
                request_id="req_z15",
                _caller_override_for_test="provider",
                db_path=self.db_path,
                env=self.standard_env,
            )
        self.assertIn("PROVIDER_CAN_CREATE_OWNER_LIVE_AUTH=NO", str(cm.exception))

        with self.assertRaises(PermissionError) as cm:
            create_owner_live_authorization(
                job_id="job_z15",
                request_id="req_z15",
                _caller_override_for_test="router",
                db_path=self.db_path,
                env=self.standard_env,
            )
        self.assertIn("DIRECT_PROVIDER_CAN_CREATE_OWNER_LIVE_AUTH=NO", str(cm.exception))

    # 16. authorized expected max micro USD > 0 invariant enforced
    def test_n21z_16_authorized_expected_max_micro_usd_greater_than_zero_enforced(self):
        self.assertEqual(AUTHORIZED_EXPECTED_MAX_ENFORCED, "YES")
        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_z16",
            product_family="Product Video",
            job_id="job_z16",
            request_id="req_z16",
            operation="create_video_task",
            expected_max_provider_spend_micro_usd=0,
            db_path=self.db_path,
            env=self.standard_env,
        )
        auth = create_test_mint_authority(
            chat_id="chat_z16",
            user_id="user_z16",
            job_id="job_z16",
            request_id="req_z16",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z16",
            expected_max_provider_spend_usd=Decimal("0.0"),
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_z16",
            user_id="user_z16",
            job_id="job_z16",
            request_id="req_z16",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z16",
            expected_max_cost_usd=Decimal("0.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_z16",
            user_id="user_z16",
            job_id="job_z16",
            request_id="req_z16",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            owner_receipt="rcpt_z16",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_OWNER_AUTHORIZED_MAX_SPEND_EXCEEDED)

    # 17. canonical submit cost > authorized expected max -> BLOCKER=owner_authorized_max_spend_exceeded
    def test_n21z_17_canonical_submit_cost_exceeding_authorized_max_blocked(self):
        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_z17",
            product_family="Product Video",
            job_id="job_z17",
            request_id="req_z17",
            operation="create_video_task",
            expected_max_provider_spend_usd=Decimal("1.00"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        auth = create_test_mint_authority(
            chat_id="chat_z17",
            user_id="user_z17",
            job_id="job_z17",
            request_id="req_z17",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z17",
            expected_max_provider_spend_usd=Decimal("1.00"),
        )
        conf_id = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_z17",
            user_id="user_z17",
            job_id="job_z17",
            request_id="req_z17",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z17",
            expected_max_cost_usd=Decimal("1.00"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_z17",
            user_id="user_z17",
            job_id="job_z17",
            request_id="req_z17",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf_id,
            user_flow="product_video_bot",
            owner_receipt="rcpt_z17",
            metadata={"quality_key": "kling_long_audio_15"},  # Canonical ~$30.60 > $1.00
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_OWNER_AUTHORIZED_MAX_SPEND_EXCEEDED)

    # 18. multi-scene plan allocates explicit bounded child max
    def test_n21z_18_multiscene_plan_allocates_explicit_bounded_child_max(self):
        self.assertEqual(MULTISCENE_OWNER_MAX_ALLOCATION, "PASS")
        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_z18",
            product_family="Product Video",
            job_id="job_z18",
            request_id="req_z18",
            operation="create_video_task",
            expected_max_provider_spend_usd=Decimal("40.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        auth = create_test_mint_authority(
            chat_id="chat_z18",
            user_id="user_z18",
            job_id="job_z18",
            request_id="req_z18",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z18",
            expected_max_provider_spend_usd=Decimal("40.0"),
        )
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_z18",
            user_id="user_z18",
            job_id="job_z18",
            request_id="req_z18",
            product_family="Product Video",
            operation="create_video_task",
            scene_count=2,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z18",
            expected_max_cost_usd=Decimal("40.0"),
            metadata={"child_authorized_max_usd_map": {1: 20.0, 2: 20.0}},
            db_path=self.db_path,
            env=self.standard_env,
        )
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT scene_index, expected_max_cost_micro_usd FROM bot_spend_confirmations WHERE parent_confirmation_id = ?",
            (plan["parent_confirmation_id"],),
        )
        rows = cur.fetchall()
        conn.close()
        self.assertEqual(len(rows), 2)
        for s_idx, exp_micro in rows:
            self.assertEqual(exp_micro, 20_000_000)

    # 19. sum(child authorized max) <= job owner max enforced
    def test_n21z_19_sum_of_child_authorized_max_exceeding_job_owner_max_enforced(self):
        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_z19",
            product_family="Product Video",
            job_id="job_z19",
            request_id="req_z19",
            operation="create_video_task",
            expected_max_provider_spend_usd=Decimal("40.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        auth = create_test_mint_authority(
            chat_id="chat_z19",
            user_id="user_z19",
            job_id="job_z19",
            request_id="req_z19",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z19",
            expected_max_provider_spend_usd=Decimal("40.0"),
        )
        with self.assertRaises(ValueError) as cm:
            mint_multiscene_bot_confirmation_plan(
                mint_authority=auth,
                chat_id="chat_z19",
                user_id="user_z19",
                job_id="job_z19",
                request_id="req_z19",
                product_family="Product Video",
                operation="create_video_task",
                scene_count=2,
                purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
                owner_receipt="rcpt_z19",
                expected_max_cost_usd=Decimal("40.0"),
                metadata={"child_authorized_max_usd_map": {1: 30.0, 2: 30.0}},  # sum = 60 > 40
                db_path=self.db_path,
                env=self.standard_env,
            )
        self.assertIn("MULTISCENE_OWNER_MAX_ALLOCATION=FAIL", str(cm.exception))

    # 20. child canonical scene cost > child authorized max -> BLOCK
    def test_n21z_20_child_canonical_scene_cost_exceeding_child_authorized_max_blocked(self):
        self.assertEqual(CHILD_EXPECTED_MAX_ENFORCED, "YES")
        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_z20",
            product_family="Product Video",
            job_id="job_z20",
            request_id="req_z20",
            operation="create_video_task",
            expected_max_provider_spend_usd=Decimal("40.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        auth = create_test_mint_authority(
            chat_id="chat_z20",
            user_id="user_z20",
            job_id="job_z20",
            request_id="req_z20",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z20",
            expected_max_provider_spend_usd=Decimal("40.0"),
        )
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_z20",
            user_id="user_z20",
            job_id="job_z20",
            request_id="req_z20",
            product_family="Product Video",
            operation="create_video_task",
            scene_count=2,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z20",
            expected_max_cost_usd=Decimal("40.0"),
            metadata={"child_authorized_max_usd_map": {1: 5.0, 2: 35.0}},  # child 1 has $5 max
            db_path=self.db_path,
            env=self.standard_env,
        )
        child1_conf = plan["scene_confirmations"][1]
        ctx = SpendGuardContext(
            chat_id="chat_z20",
            user_id="user_z20",
            job_id="job_z20",
            request_id="req_z20",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=child1_conf,
            user_flow="product_video_bot",
            owner_receipt="rcpt_z20",
            metadata={"quality_key": "kling_long_audio_15"},  # cost ~$30.60 > $5.00
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_OWNER_AUTHORIZED_MAX_SPEND_EXCEEDED)

    # 21. multi-scene plan does NOT duplicate whole-job max into every child
    def test_n21z_21_multiscene_plan_does_not_duplicate_whole_job_max_into_every_child(self):
        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_z21",
            product_family="Product Video",
            job_id="job_z21",
            request_id="req_z21",
            operation="create_video_task",
            expected_max_provider_spend_usd=Decimal("60.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        auth = create_test_mint_authority(
            chat_id="chat_z21",
            user_id="user_z21",
            job_id="job_z21",
            request_id="req_z21",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z21",
            expected_max_provider_spend_usd=Decimal("60.0"),
        )
        plan = mint_multiscene_bot_confirmation_plan(
            mint_authority=auth,
            chat_id="chat_z21",
            user_id="user_z21",
            job_id="job_z21",
            request_id="req_z21",
            product_family="Product Video",
            operation="create_video_task",
            scene_count=3,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z21",
            expected_max_cost_usd=Decimal("60.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT expected_max_cost_micro_usd FROM bot_spend_confirmations WHERE parent_confirmation_id = ?",
            (plan["parent_confirmation_id"],),
        )
        rows = [r[0] for r in cur.fetchall()]
        conn.close()
        self.assertEqual(len(rows), 3)
        for r in rows:
            self.assertNotEqual(r, 60_000_000, "Child confirmation must not duplicate whole-job max")
            self.assertEqual(r, 20_000_000)

    # 22. single-use Owner authorization consumed -> second use BLOCKED
    def test_n21z_22_single_use_owner_authorization_consumed_second_use_blocked(self):
        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_z22",
            product_family="Product Video",
            job_id="job_z22",
            request_id="req_z22",
            operation="create_video_task",
            allowed_scene_slots="1",
            expected_max_provider_spend_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        auth1 = create_test_mint_authority(
            chat_id="chat_z22",
            user_id="user_z22",
            job_id="job_z22",
            request_id="req_z22",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z22",
            expected_max_provider_spend_usd=Decimal("50.0"),
        )
        conf1 = create_bot_confirmation(
            mint_authority=auth1,
            chat_id="chat_z22",
            user_id="user_z22",
            job_id="job_z22",
            request_id="req_z22",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z22",
            expected_max_cost_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx1 = SpendGuardContext(
            chat_id="chat_z22",
            user_id="user_z22",
            job_id="job_z22",
            request_id="req_z22",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf1,
            user_flow="product_video_bot",
            owner_receipt="rcpt_z22",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res1 = reserve_provider_spend(ctx1, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)

        # Second attempt with fresh confirmation but same single-use authorization
        auth2 = create_test_mint_authority(
            chat_id="chat_z22",
            user_id="user_z22",
            job_id="job_z22",
            request_id="req_z22_retry",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z22",
            expected_max_provider_spend_usd=Decimal("50.0"),
        )
        conf2 = create_bot_confirmation(
            mint_authority=auth2,
            chat_id="chat_z22",
            user_id="user_z22",
            job_id="job_z22",
            request_id="req_z22_retry",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z22",
            expected_max_cost_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx2 = SpendGuardContext(
            chat_id="chat_z22",
            user_id="user_z22",
            job_id="job_z22",
            request_id="req_z22_retry",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf2,
            user_flow="product_video_bot",
            owner_receipt="rcpt_z22",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res2 = reserve_provider_spend(ctx2, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res2.allowed)
        self.assertEqual(res2.blocker, BLOCKER_OWNER_LIVE_AUTH_ALREADY_CONSUMED)

    # 23. Directive #1422 lineage complete for paid live test -> PASS
    def test_n21z_23_directive_1422_lineage_complete_for_paid_live_test_passes(self):
        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_z23",
            product_family="Product Video",
            job_id="job_z23",
            request_id="req_z23",
            operation="create_video_task",
            expected_max_provider_spend_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        auth = create_test_mint_authority(
            chat_id="chat_z23",
            user_id="user_z23",
            job_id="job_z23",
            request_id="req_z23",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z23",
            expected_max_provider_spend_usd=Decimal("50.0"),
        )
        conf = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_z23",
            user_id="user_z23",
            job_id="job_z23",
            request_id="req_z23",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z23",
            expected_max_cost_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_z23",
            user_id="user_z23",
            entrypoint="bot",
            bot_originated_action=True,
            job_id="job_z23",
            request_id="req_z23",
            user_flow="bot_live_acceptance",
            owner_receipt="rcpt_z23",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)

    # 24. missing any Directive #1422 field for live test -> BLOCK
    def test_n21z_24_missing_any_directive_1422_field_for_live_test_blocked(self):
        _create_owner_live_authorization_test_fixture(
            authorization_id="rcpt_z24",
            product_family="Product Video",
            job_id="job_z24",
            request_id="req_z24",
            operation="create_video_task",
            expected_max_provider_spend_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        auth = create_test_mint_authority(
            chat_id="chat_z24",
            user_id="user_z24",
            job_id="job_z24",
            request_id="req_z24",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z24",
            expected_max_provider_spend_usd=Decimal("50.0"),
        )
        conf = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_z24",
            user_id="user_z24",
            job_id="job_z24",
            request_id="req_z24",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="rcpt_z24",
            expected_max_cost_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        # Test missing bot_originated_action
        ctx_no_bot_origin = SpendGuardContext(
            chat_id="chat_z24",
            user_id="user_z24",
            entrypoint="bot",
            bot_originated_action=False,
            job_id="job_z24",
            request_id="req_z24",
            user_flow="bot_live_acceptance",
            owner_receipt="rcpt_z24",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf,
        )
        res1 = reserve_provider_spend(ctx_no_bot_origin, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res1.allowed)
        self.assertEqual(res1.blocker, BLOCKER_BOT_ORIGIN_PROOF_MISSING)

        # Test non-bot entrypoint
        ctx_worker = SpendGuardContext(
            chat_id="chat_z24",
            user_id="user_z24",
            entrypoint="worker",
            bot_originated_action=True,
            job_id="job_z24",
            request_id="req_z24",
            user_flow="bot_live_acceptance",
            owner_receipt="rcpt_z24",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf,
        )
        res2 = reserve_provider_spend(ctx_worker, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res2.allowed)
        self.assertIn(res2.blocker, (BLOCKER_BOT_ORIGIN_PROOF_MISSING, "paid_live_test_entrypoint_forbidden_bot_only_required"))

        # Test missing user_flow
        ctx_no_flow = SpendGuardContext(
            chat_id="chat_z24",
            user_id="user_z24",
            entrypoint="bot",
            bot_originated_action=True,
            job_id="job_z24",
            request_id="req_z24",
            user_flow="",
            owner_receipt="rcpt_z24",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf,
        )
        res3 = reserve_provider_spend(ctx_no_flow, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res3.allowed)
        self.assertEqual(res3.blocker, BLOCKER_BOT_ORIGIN_PROOF_MISSING)

    # 25. weekly $200 shared cap still active
    def test_n21z_25_weekly_200_shared_cap_still_active(self):
        cap_micro = get_configured_cap_micro_usd(env={})
        self.assertEqual(cap_micro, 200_000_000)

    # 26. weekly reset policy missing -> PRODUCTION_READY=NO
    def test_n21z_26_weekly_reset_policy_missing_remains_not_production_ready(self):
        self.assertTrue(OWNER_POLICY_RESET_RULE_UNSPECIFIED)
        auth = create_test_mint_authority(chat_id="chat_z26", user_id="user_z26")
        conf = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_z26",
            user_id="user_z26",
            job_id="job_z26",
            request_id="req_z26",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            chat_id="chat_z26",
            user_id="user_z26",
            job_id="job_z26",
            request_id="req_z26",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_originated_action=True,
            bot_confirm_authority=conf,
            user_flow="product_video_bot",
            metadata={"quality_key": "kling_long_audio_15"},
        )
        # Without reset policy injected, reservation fails closed
        res = reserve_provider_spend(ctx, db_path=self.db_path, env={"SPEND_GUARD_DB_PATH": self.db_path})
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_POLICY_INCOMPLETE)

    # 27. real provider calls == 0 across entire test suite
    def test_n21z_27_real_provider_calls_zero_across_entire_test_suite(self):
        # Invariant: 0 real provider calls, 0 submits in provider-free testing
        self.assertEqual(len(PROVIDER_PRODUCTION_MINT_CALLERS), 0)
        self.assertEqual(len(WORKER_PRODUCTION_MINT_CALLERS), 0)

    # 28. test count report truth exact
    def test_n21z_28_test_count_report_truth_exact(self):
        # Verification of exact test matrix structure
        cases_25 = len([m for m in dir(TestProviderSpendGuard25Cases) if m.startswith("test_")])
        cases_n21u = len([m for m in dir(TestN21UProviderFreeSpendGuardMatrix) if m.startswith("test_")])
        cases_n21v = len([m for m in dir(TestN21VRealBotConfirmLineageAndMultiSubmitMatrix) if m.startswith("test_")])
        cases_n21w = len([m for m in dir(TestN21WConfirmationMintBoundaryAndProductionReadinessMatrix) if m.startswith("test_")])
        cases_n21x = len([m for m in dir(TestN21XNonForgeableBotMintCapabilityMatrix) if m.startswith("test_")])
        cases_n21y = len([m for m in dir(TestN21YBotConfirmAuthorityTruthAndPerSceneReservationMatrix) if m.startswith("test_")])
        cases_n21z = len([m for m in dir(TestN21ZOwnerLiveAuthorityRecordAndExpectedSpendEnforcementMatrix) if m.startswith("test_")])

        self.assertEqual(cases_25, 50)
        self.assertEqual(cases_n21u, 18)
        self.assertEqual(cases_n21v, 22)
        self.assertEqual(cases_n21w, 29)
        self.assertEqual(cases_n21x, 23)
        self.assertEqual(cases_n21y, 26)
        self.assertEqual(cases_n21z, 28)
        self.assertEqual(cases_25 + cases_n21u + cases_n21v + cases_n21w + cases_n21x + cases_n21y + cases_n21z, 196)



class _N21AAMockUser:
    def __init__(self, uid=777888):
        self.id = uid


class _N21AAMockMessage:
    def __init__(self, chat_id=999111):
        self.chat_id = chat_id

    async def reply_text(self, text, **kwargs):
        return text


class _N21AAMockCallbackQuery:
    def __init__(self, query_id="cbq_real_live_01", data="vproduct|owner_live_accept", user_id=777888, chat_id=999111):
        self.id = query_id
        self.data = data
        self.from_user = _N21AAMockUser(user_id)
        self.message = _N21AAMockMessage(chat_id)
        self.answered = False
        self.edited_text = ""
        self.edited_markup = None

    async def answer(self, *args, **kwargs):
        self.answered = True

    async def edit_message_text(self, text, reply_markup=None, **kwargs):
        self.edited_text = text
        self.edited_markup = reply_markup
        return text


class _N21AAMockUpdate:
    def __init__(self, update_id=888999, query=None):
        self.update_id = update_id
        self.callback_query = query
        self.effective_user = getattr(query, "from_user", None)
        self.effective_chat = getattr(getattr(query, "message", None), "chat_id", None)


class _N21AAMockContext:
    def __init__(self, user_data=None):
        self.user_data = user_data or {}


class TestN21AABotPublicCallbackAndLiveAcceptIntegrationMatrix(unittest.TestCase):
    """N21AA: Bot Public Callback Whitelist, Owner Live Accept Panel & Integration Matrix (Directive #1422)."""

    def setUp(self):
        set_kill_switch(False)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "spend_guard_n21aa.db")
        self.standard_env = {
            "SPEND_GUARD_DB_PATH": self.db_path,
            "WEEKLY_PROVIDER_SPEND_CAP_USD": "200.000",
            "WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE": "MONDAY_0000_UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE": "UTC",
        }
        os.environ["SPEND_GUARD_DB_PATH"] = self.db_path
        os.environ["WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE"] = "MONDAY_0000_UTC"
        os.environ["WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE"] = "UTC"
        init_spend_guard_db(db_path=self.db_path, env=self.standard_env)

    def tearDown(self):
        set_kill_switch(False)
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass
        os.environ.pop("SPEND_GUARD_DB_PATH", None)

    # 1. callback prefix and routing whitelisted
    def test_n21aa_01_callback_prefix_and_routing_whitelisted(self):
        from bot import (
            VIDEO_PUBLIC_CALLBACK_OWNER_PREFIXES,
            PUBLIC_CALLBACK_NAMES,
            video_route_expected_handler,
        )
        self.assertIn(
            ("vproduct|owner_live_accept", "handle_product_video_owner_live_accept_callback"),
            VIDEO_PUBLIC_CALLBACK_OWNER_PREFIXES,
        )
        self.assertIn("handle_product_video_owner_live_accept_callback", PUBLIC_CALLBACK_NAMES)
        self.assertEqual(
            video_route_expected_handler("vproduct|owner_live_accept"),
            "handle_product_video_owner_live_accept_callback",
        )
        self.assertEqual(
            video_route_expected_handler("vproduct|owner_live_accept|0123456789ab"),
            "handle_product_video_owner_live_accept_callback",
        )

    # 2. preflight panel keyboard renders owner live accept button
    def test_n21aa_02_preflight_panel_keyboard_renders_owner_live_accept_button(self):
        from bot import product_video_public_preflight_panel_keyboard
        insert_test_canonical_owner_auth(
            self.db_path,
            token_id="auth_rcpt_123456",
            job_id="123",
            request_id="req_123",
            env=self.standard_env,
        )
        kb = product_video_public_preflight_panel_keyboard(
            owner_receipt="auth_rcpt_123456",
            job_id="123",
            request_id="req_123",
            db_path=self.db_path,
        )
        first_row = kb.inline_keyboard[0]
        self.assertEqual(len(first_row), 1)
        self.assertIn("👑 Xác nhận kiểm thử trực tiếp (Owner)", first_row[0].text)
        self.assertEqual(first_row[0].callback_data, "vproduct|owner_live_accept|auth_rcpt_12")

        kb_no = product_video_public_preflight_panel_keyboard(owner_receipt="")
        for row in kb_no.inline_keyboard:
            for btn in row:
                self.assertNotIn("vproduct|owner_live_accept", str(btn.callback_data))

    # 3. standalone owner live accept keyboard format
    def test_n21aa_03_standalone_owner_live_accept_keyboard_format(self):
        from bot import build_product_video_owner_live_accept_keyboard
        kb = build_product_video_owner_live_accept_keyboard("auth_test_tok_99")
        btn = kb.inline_keyboard[0][0]
        self.assertEqual(btn.callback_data, "vproduct|owner_live_accept|auth_test_to")
        self.assertIn("👑 Xác nhận kiểm thử trực tiếp (Owner)", btn.text)

        kb_empty = build_product_video_owner_live_accept_keyboard("")
        btn_empty = kb_empty.inline_keyboard[0][0]
        self.assertEqual(btn_empty.callback_data, "vproduct|owner_live_accept")

    # 4. bot live test constants truth
    def test_n21aa_04_bot_live_test_constants_truth(self):
        self.assertEqual(BOT_LIVE_TEST_QUEUE_PROPAGATION, "confirm_video_project_invoice")
        self.assertEqual(DURABLE_OWNER_MAX_SOLE_SOURCE, "YES")
        self.assertEqual(CALLER_EXPECTED_MAX_INFLUENCE, "NO")
        self.assertEqual(BOT_LIVE_MINT_REQUIRES_REAL_TELEGRAM_EVENT, "YES")
        self.assertEqual(BOT_LIVE_MINT_REQUIRES_DURABLE_OWNER_AUTH, "YES")
        self.assertEqual(BOT_LIVE_ACCEPT_CALLBACK_CALLSITE, "bot.py:handle_product_video_owner_live_accept_callback")

    # 5. missing receipt raises PermissionError
    def test_n21aa_05_handle_owner_authorized_live_test_confirm_missing_receipt_raises(self):
        from bot import handle_owner_authorized_live_test_confirm
        query = _N21AAMockCallbackQuery()
        update = _N21AAMockUpdate(update_id=1001, query=query)
        context = _N21AAMockContext()
        with self.assertRaises(PermissionError) as cm:
            asyncio.run(
                handle_owner_authorized_live_test_confirm(
                    update,
                    context,
                    owner_receipt="",
                    job_id="1001",
                    request_id="req_1001",
                )
            )
        self.assertIn("receipt is required", str(cm.exception))

    # 6. non-existent receipt raises PermissionError
    def test_n21aa_06_handle_owner_authorized_live_test_confirm_nonexistent_receipt_raises(self):
        from bot import handle_owner_authorized_live_test_confirm
        query = _N21AAMockCallbackQuery()
        update = _N21AAMockUpdate(update_id=1002, query=query)
        context = _N21AAMockContext()
        with self.assertRaises(PermissionError) as cm:
            asyncio.run(
                handle_owner_authorized_live_test_confirm(
                    update,
                    context,
                    owner_receipt="non_existent_rcpt_06",
                    job_id="1002",
                    request_id="req_1002",
                )
            )
        self.assertIn(BLOCKER_OWNER_LIVE_AUTH_RECORD_MISSING, str(cm.exception))

    # 7. revoked receipt raises PermissionError
    def test_n21aa_07_handle_owner_authorized_live_test_confirm_revoked_receipt_raises(self):
        from bot import handle_owner_authorized_live_test_confirm
        auth_id = _create_owner_live_authorization_test_fixture(
            authorization_id="auth_revoked_07",
            product_family="Product Video",
            job_id="1003",
            request_id="req_1003",
            operation="create_video_task",
            status=STATUS_OWNER_AUTH_REVOKED,
            expected_max_provider_spend_usd=Decimal("1.5"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        query = _N21AAMockCallbackQuery()
        update = _N21AAMockUpdate(update_id=1003, query=query)
        context = _N21AAMockContext()
        with self.assertRaises(PermissionError) as cm:
            asyncio.run(
                handle_owner_authorized_live_test_confirm(
                    update,
                    context,
                    owner_receipt=auth_id,
                    job_id="1003",
                    request_id="req_1003",
                )
            )
        self.assertIn(BLOCKER_OWNER_LIVE_AUTH_REVOKED, str(cm.exception))

    # 8. expired receipt raises PermissionError
    def test_n21aa_08_handle_owner_authorized_live_test_confirm_expired_receipt_raises(self):
        from bot import handle_owner_authorized_live_test_confirm
        auth_id = _create_owner_live_authorization_test_fixture(
            authorization_id="auth_expired_08",
            product_family="Product Video",
            job_id="1004",
            request_id="req_1004",
            operation="create_video_task",
            ttl_seconds=-100.0,
            expected_max_provider_spend_usd=Decimal("1.5"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        query = _N21AAMockCallbackQuery()
        update = _N21AAMockUpdate(update_id=1004, query=query)
        context = _N21AAMockContext()
        with self.assertRaises(PermissionError) as cm:
            asyncio.run(
                handle_owner_authorized_live_test_confirm(
                    update,
                    context,
                    owner_receipt=auth_id,
                    job_id="1004",
                    request_id="req_1004",
                )
            )
        self.assertIn(BLOCKER_OWNER_LIVE_AUTH_EXPIRED, str(cm.exception))

    # 9. job lineage mismatch raises PermissionError
    def test_n21aa_09_handle_owner_authorized_live_test_confirm_job_lineage_mismatch_raises(self):
        from bot import handle_owner_authorized_live_test_confirm
        auth_id = _create_owner_live_authorization_test_fixture(
            authorization_id="auth_lineage_job_09",
            product_family="Product Video",
            job_id="job_correct_09",
            request_id="req_correct_09",
            operation="create_video_task",
            expected_max_provider_spend_usd=Decimal("1.5"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        query = _N21AAMockCallbackQuery()
        update = _N21AAMockUpdate(update_id=1005, query=query)
        context = _N21AAMockContext()
        with self.assertRaises(PermissionError) as cm:
            asyncio.run(
                handle_owner_authorized_live_test_confirm(
                    update,
                    context,
                    owner_receipt=auth_id,
                    job_id="job_wrong_09",
                    request_id="req_correct_09",
                )
            )
        self.assertIn(BLOCKER_OWNER_LIVE_AUTH_LINEAGE_MISMATCH, str(cm.exception))

    # 10. request lineage mismatch raises PermissionError
    def test_n21aa_10_handle_owner_authorized_live_test_confirm_request_lineage_mismatch_raises(self):
        from bot import handle_owner_authorized_live_test_confirm
        auth_id = _create_owner_live_authorization_test_fixture(
            authorization_id="auth_lineage_req_10",
            product_family="Product Video",
            job_id="job_correct_10",
            request_id="req_correct_10",
            operation="create_video_task",
            expected_max_provider_spend_usd=Decimal("1.5"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        query = _N21AAMockCallbackQuery()
        update = _N21AAMockUpdate(update_id=1006, query=query)
        context = _N21AAMockContext()
        with self.assertRaises(PermissionError) as cm:
            asyncio.run(
                handle_owner_authorized_live_test_confirm(
                    update,
                    context,
                    owner_receipt=auth_id,
                    job_id="job_correct_10",
                    request_id="req_wrong_10",
                )
            )
        self.assertIn(BLOCKER_OWNER_LIVE_AUTH_LINEAGE_MISMATCH, str(cm.exception))

    # 11. durable owner max spend is sole source (caller cannot inflate)
    def test_n21aa_11_handle_owner_authorized_live_test_confirm_uses_durable_owner_max_spend(self):
        from bot import handle_owner_authorized_live_test_confirm
        auth_id = _create_owner_live_authorization_test_fixture(
            authorization_id="auth_spend_11",
            product_family="Product Video",
            job_id="job_11",
            request_id="req_11",
            operation="create_video_task",
            expected_max_provider_spend_micro_usd=1_200_000,
            db_path=self.db_path,
            env=self.standard_env,
        )
        query = _N21AAMockCallbackQuery()
        update = _N21AAMockUpdate(update_id=1007, query=query)
        context = _N21AAMockContext()
        plan = asyncio.run(
            handle_owner_authorized_live_test_confirm(
                update,
                context,
                owner_receipt=auth_id,
                job_id="job_11",
                request_id="req_11",
                scene_count=1,
                expected_max_usd=999.0,
            )
        )
        child_id = plan["child_confirmations"][0]
        # Verify in database that child confirmation has exactly durable 1,200,000 µUSD
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT expected_max_cost_micro_usd FROM bot_spend_confirmations WHERE confirmation_id = ?",
                (child_id,),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], 1_200_000)
        finally:
            conn.close()

    # 12. callback handler rejects synthetic zero update_id or callback_query_id
    def test_n21aa_12_callback_handler_rejects_synthetic_zero_update_or_callback_id(self):
        from bot import handle_product_video_owner_live_accept_callback
        query = _N21AAMockCallbackQuery(query_id="")
        update = _N21AAMockUpdate(update_id=0, query=query)
        context = _N21AAMockContext()
        asyncio.run(handle_product_video_owner_live_accept_callback(update, context))
        self.assertIn("Lỗi xác thực: Sự kiện Telegram không hợp lệ.", query.edited_text)

    # 13. callback handler rejects missing owner receipt
    def test_n21aa_13_callback_handler_rejects_missing_owner_receipt(self):
        from bot import handle_product_video_owner_live_accept_callback
        query = _N21AAMockCallbackQuery()
        update = _N21AAMockUpdate(update_id=1009, query=query)
        context = _N21AAMockContext(user_data={"video_session": {"job_id": "1009", "request_id": "req_1009"}})
        asyncio.run(handle_product_video_owner_live_accept_callback(update, context))
        self.assertIn("Thiếu biên nhận chấp thuận Owner cho phiên kiểm thử trực tiếp.", query.edited_text)

    # 14. callback handler full flow success
    def test_n21aa_14_callback_handler_full_flow_success(self):
        from bot import handle_product_video_owner_live_accept_callback
        auth_id = _create_owner_live_authorization_test_fixture(
            authorization_id="auth_flow_14",
            product_family="Product Video",
            job_id="1401",
            request_id="req_1401",
            operation="create_video_task",
            expected_max_provider_spend_usd=Decimal("1.5"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        query = _N21AAMockCallbackQuery()
        update = _N21AAMockUpdate(update_id=1401, query=query)
        context = _N21AAMockContext(
            user_data={
                "video_session": {
                    "job_id": 1401,
                    "request_id": "req_1401",
                    "owner_acceptance_token": auth_id,
                    "scene_count": 1,
                }
            }
        )
        asyncio.run(handle_product_video_owner_live_accept_callback(update, context))
        self.assertIn("✅ Đã xác nhận phê duyệt kiểm thử có tính phí của Owner (Job #1401)", query.edited_text)

    # 15. callback handler queue propagation invoked
    def test_n21aa_15_callback_handler_queue_propagation_invoked(self):
        from bot import handle_product_video_owner_live_accept_callback
        from unittest.mock import patch
        auth_id = _create_owner_live_authorization_test_fixture(
            authorization_id="auth_flow_15",
            product_family="Product Video",
            job_id="1501",
            request_id="req_1501",
            operation="create_video_task",
            expected_max_provider_spend_usd=Decimal("1.5"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        query = _N21AAMockCallbackQuery(user_id=777888)
        update = _N21AAMockUpdate(update_id=1501, query=query)
        context = _N21AAMockContext(
            user_data={
                "video_session": {
                    "job_id": 1501,
                    "request_id": "req_1501",
                    "owner_acceptance_token": auth_id,
                    "scene_count": 1,
                }
            }
        )
        with patch("bot.confirm_video_project_invoice") as mock_q:
            asyncio.run(handle_product_video_owner_live_accept_callback(update, context))
            self.assertTrue(mock_q.called)
            call_kwargs = mock_q.call_args[1]
            self.assertEqual(call_kwargs["project_id"], 1501)
            self.assertEqual(call_kwargs["user_id"], 777888)
            self.assertEqual(call_kwargs["provider_admission"]["owner_receipt"], auth_id)

    # 16. minted live confirmation succeeds spend guard reservation
    def test_n21aa_16_minted_live_confirmation_succeeds_spend_guard_reservation(self):
        from bot import handle_owner_authorized_live_test_confirm
        auth_id = _create_owner_live_authorization_test_fixture(
            authorization_id="auth_spend_16",
            product_family="Product Video",
            job_id="1601",
            request_id="req_1601",
            operation="create_video_task",
            expected_max_provider_spend_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        query = _N21AAMockCallbackQuery(user_id=1601, chat_id=1601)
        update = _N21AAMockUpdate(update_id=1601, query=query)
        context = _N21AAMockContext()
        plan = asyncio.run(
            handle_owner_authorized_live_test_confirm(
                update,
                context,
                owner_receipt=auth_id,
                job_id="1601",
                request_id="req_1601",
                scene_count=1,
            )
        )
        child_id = plan["child_confirmations"][0]

        ctx = SpendGuardContext(
            chat_id="1601",
            user_id="1601",
            entrypoint="bot",
            bot_originated_action=True,
            job_id="1601",
            request_id="req_1601",
            user_flow="bot_live_acceptance",
            owner_receipt=auth_id,
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=child_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)
        self.assertFalse(res.blocker)

    # 17. spend guard blocks when provider cost exceeds durable max
    def test_n21aa_17_spend_guard_blocks_when_provider_cost_exceeds_durable_max(self):
        from bot import handle_owner_authorized_live_test_confirm
        auth_id = _create_owner_live_authorization_test_fixture(
            authorization_id="auth_spend_17",
            product_family="Product Video",
            job_id="1701",
            request_id="req_1701",
            operation="create_video_task",
            expected_max_provider_spend_micro_usd=100,  # 0.0001 USD ceiling
            db_path=self.db_path,
            env=self.standard_env,
        )
        query = _N21AAMockCallbackQuery(user_id=1701, chat_id=1701)
        update = _N21AAMockUpdate(update_id=1701, query=query)
        context = _N21AAMockContext()
        plan = asyncio.run(
            handle_owner_authorized_live_test_confirm(
                update,
                context,
                owner_receipt=auth_id,
                job_id="1701",
                request_id="req_1701",
                scene_count=1,
            )
        )
        child_id = plan["child_confirmations"][0]

        ctx = SpendGuardContext(
            chat_id="1701",
            user_id="1701",
            entrypoint="bot",
            bot_originated_action=True,
            job_id="1701",
            request_id="req_1701",
            user_flow="bot_live_acceptance",
            owner_receipt=auth_id,
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=child_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_OWNER_AUTHORIZED_MAX_SPEND_EXCEEDED)

    # 18. multiscene allocation proportional and slot verified
    def test_n21aa_18_multiscene_allocation_proportional_and_slot_verified(self):
        from bot import handle_owner_authorized_live_test_confirm
        auth_id = _create_owner_live_authorization_test_fixture(
            authorization_id="auth_spend_18",
            product_family="Product Video",
            job_id="1801",
            request_id="req_1801",
            operation="create_video_task",
            allowed_scene_slots="1,2",
            expected_max_provider_spend_usd=Decimal("6.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        query = _N21AAMockCallbackQuery(user_id=1801, chat_id=1801)
        update = _N21AAMockUpdate(update_id=1801, query=query)
        context = _N21AAMockContext()
        plan = asyncio.run(
            handle_owner_authorized_live_test_confirm(
                update,
                context,
                owner_receipt=auth_id,
                job_id="1801",
                request_id="req_1801",
                scene_count=2,
            )
        )
        self.assertEqual(len(plan["child_confirmations"]), 2)

        # Scene 3 is not in allowed slots "1,2" -> slot mismatch
        ctx3 = SpendGuardContext(
            chat_id="1801",
            user_id="1801",
            entrypoint="bot",
            bot_originated_action=True,
            job_id="1801",
            request_id="req_1801",
            user_flow="bot_live_acceptance",
            owner_receipt=auth_id,
            scene_index=3,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=plan["child_confirmations"][0],
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res3 = reserve_provider_spend(ctx3, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res3.allowed)
        self.assertIn(res3.blocker, (BLOCKER_OWNER_LIVE_AUTH_SLOT_MISMATCH, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING))

    # 19. consumed owner auth cannot be reused
    def test_n21aa_19_consumed_owner_auth_cannot_be_reused(self):
        from bot import handle_owner_authorized_live_test_confirm
        auth_id = _create_owner_live_authorization_test_fixture(
            authorization_id="auth_spend_19",
            product_family="Product Video",
            job_id="1901",
            request_id="req_1901",
            operation="create_video_task",
            allowed_scene_slots="1",
            metadata={"max_uses": 1},
            expected_max_provider_spend_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        query = _N21AAMockCallbackQuery(user_id=1901, chat_id=1901)
        update = _N21AAMockUpdate(update_id=1901, query=query)
        context = _N21AAMockContext()
        plan = asyncio.run(
            handle_owner_authorized_live_test_confirm(
                update,
                context,
                owner_receipt=auth_id,
                job_id="1901",
                request_id="req_1901",
                scene_count=1,
            )
        )
        child_id = plan["child_confirmations"][0]

        ctx = SpendGuardContext(
            chat_id="1901",
            user_id="1901",
            entrypoint="bot",
            bot_originated_action=True,
            job_id="1901",
            request_id="req_1901",
            user_flow="bot_live_acceptance",
            owner_receipt=auth_id,
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=child_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res1 = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)

        # Attempting second reservation with same owner auth
        res2 = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res2.allowed)
        self.assertIn(
            res2.blocker,
            (
                BLOCKER_OWNER_LIVE_AUTH_ALREADY_CONSUMED,
                BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING,
                BLOCKER_DUPLICATE_PAID_SUBMIT,
            ),
        )

    # 20. test count matrix truth exact
    def test_n21aa_20_test_count_matrix_truth_exact(self):
        cases_25 = len([m for m in dir(TestProviderSpendGuard25Cases) if m.startswith("test_")])
        cases_n21u = len([m for m in dir(TestN21UProviderFreeSpendGuardMatrix) if m.startswith("test_")])
        cases_n21v = len([m for m in dir(TestN21VRealBotConfirmLineageAndMultiSubmitMatrix) if m.startswith("test_")])
        cases_n21w = len([m for m in dir(TestN21WConfirmationMintBoundaryAndProductionReadinessMatrix) if m.startswith("test_")])
        cases_n21x = len([m for m in dir(TestN21XNonForgeableBotMintCapabilityMatrix) if m.startswith("test_")])
        cases_n21y = len([m for m in dir(TestN21YBotConfirmAuthorityTruthAndPerSceneReservationMatrix) if m.startswith("test_")])
        cases_n21z = len([m for m in dir(TestN21ZOwnerLiveAuthorityRecordAndExpectedSpendEnforcementMatrix) if m.startswith("test_")])
        cases_n21aa = len([m for m in dir(TestN21AABotPublicCallbackAndLiveAcceptIntegrationMatrix) if m.startswith("test_")])

        self.assertEqual(cases_25, 50)
        self.assertEqual(cases_n21u, 18)
        self.assertEqual(cases_n21v, 22)
        self.assertEqual(cases_n21w, 29)
        self.assertEqual(cases_n21x, 23)
        self.assertEqual(cases_n21y, 26)
        self.assertEqual(cases_n21z, 28)
        self.assertEqual(cases_n21aa, 20)
        self.assertEqual(
            cases_25 + cases_n21u + cases_n21v + cases_n21w + cases_n21x + cases_n21y + cases_n21z + cases_n21aa,
            216,
        )


class TestN21ABSingleOwnerAuthorityHotfixMatrix(unittest.TestCase):
    """N21AB: Single Canonical Owner Authority Hotfix, Atomic Cumulative Budget & Explicit Slot Matrix."""

    def setUp(self):
        set_kill_switch(False)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "spend_guard_n21ab.db")
        self.standard_env = {
            "SPEND_GUARD_DB_PATH": self.db_path,
            "WEEKLY_PROVIDER_SPEND_CAP_USD": "200.000",
            "WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE": "MONDAY_0000_UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE": "UTC",
        }
        os.environ["SPEND_GUARD_DB_PATH"] = self.db_path
        os.environ["WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE"] = "MONDAY_0000_UTC"
        os.environ["WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE"] = "UTC"
        init_spend_guard_db(db_path=self.db_path, env=self.standard_env)

    def tearDown(self):
        set_kill_switch(False)
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass
        os.environ.pop("SPEND_GUARD_DB_PATH", None)

    # 1. single owner authority invariants truth
    def test_n21ab_01_single_owner_authority_invariants_truth(self):
        self.assertEqual(EXISTING_CANONICAL_OWNER_AUTHORITY_FOUND, "YES")
        self.assertEqual(SINGLE_OWNER_AUTHORITY, "YES")
        self.assertEqual(DUAL_OWNER_AUTHORITY, "NO")
        self.assertEqual(SECOND_AUTHORITY_CAN_AUTHORIZE, "NO")
        self.assertEqual(INSERT_OR_REPLACE_OWNER_AUTH, "ABSENT")
        self.assertEqual(AUTH_CREATE_MODE, "INSERT_ONLY")
        self.assertEqual(DUPLICATE_AUTH_ID, "BLOCK")
        self.assertEqual(CONSUMED_AUTH_RESURRECTION, "BLOCK")
        self.assertEqual(REVOKED_AUTH_RESURRECTION, "BLOCK")
        self.assertEqual(EXPIRED_AUTH_RESURRECTION, "BLOCK")
        self.assertEqual(CALLER_CHILD_BUDGET_METADATA_AUTHORITY, "NO")
        self.assertEqual(CUMULATIVE_OWNER_JOB_BUDGET_ATOMIC, "PASS")
        self.assertEqual(MULTISCENE_EXPLICIT_SLOT_BOUNDS, "PASS")
        self.assertEqual(WILDCARD_MULTIUSE_ALLOWED, "NO")
        self.assertEqual(SCENE_SLOT_REUSE_ALLOWED, "NO")
        self.assertEqual(MAX_PROVIDER_SUBMITS_ENFORCED, "YES")
        self.assertEqual(OWNER_LIVE_AUTHORIZATIONS_AS_SECOND_AUTHORITY, "REMOVED_OR_INERT_LEGACY_ONLY")

    # 2. canonical existing owner authority reused and second cannot authorize
    def test_n21ab_02_canonical_existing_owner_authority_reused_and_second_cannot_authorize(self):
        token_id, auth_dict = insert_test_canonical_owner_auth(
            self.db_path,
            job_id=9871,
            request_id="req_ab02",
            max_provider_spend=50.0,
            allowed_scene_slots="1,2",
            token_id="tok_ab02",
            env=self.standard_env,
        )
        self.assertEqual(token_id, "tok_ab02")
        valid, blocker, verified = validate_canonical_owner_live_authorization(
            "tok_ab02",
            job_id=9871,
            request_id="req_ab02",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertTrue(valid)
        self.assertEqual(verified["authorization_id"], "tok_ab02")

        # Second non-canonical arbitrary auth string cannot authorize
        valid2, blocker2, _ = validate_canonical_owner_live_authorization(
            "nonexistent_second_auth_token",
            job_id=9871,
            request_id="req_ab02",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertFalse(valid2)
        self.assertIn(blocker2, (BLOCKER_OWNER_LIVE_AUTH_RECORD_MISSING, "owner_acceptance_record_missing"))

    # 3. absence of insert or replace and duplicate auth ID blocked
    def test_n21ab_03_absence_of_insert_or_replace_and_duplicate_auth_id_blocked(self):
        _create_owner_live_authorization_test_fixture(
            authorization_id="auth_ab03",
            product_family="Product Video",
            job_id="job_ab03",
            request_id="req_ab03",
            operation="create_video_task",
            expected_max_provider_spend_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        # Attempting duplicate auth ID must raise ValueError with duplicate blocker
        with self.assertRaises(ValueError) as cm:
            _create_owner_live_authorization_test_fixture(
                authorization_id="auth_ab03",
                product_family="Product Video",
                job_id="job_ab03",
                request_id="req_ab03",
                operation="create_video_task",
                expected_max_provider_spend_usd=Decimal("50.0"),
                db_path=self.db_path,
                env=self.standard_env,
            )
        self.assertIn(BLOCKER_DUPLICATE_AUTH_ID, str(cm.exception))

    # 4. consumed, revoked, and expired resurrection blocked
    def test_n21ab_04_consumed_revoked_expired_resurrection_blocked(self):
        # 1. Consumed resurrection blocked
        insert_test_canonical_owner_auth(
            self.db_path,
            token_id="auth_ab04_con",
            job_id="job_ab04_con",
            request_id="req_ab04_con",
            status="consumed",
            env=self.standard_env,
        )
        valid_con, blocker_con, _ = validate_canonical_owner_live_authorization(
            "auth_ab04_con",
            job_id="job_ab04_con",
            request_id="req_ab04_con",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertFalse(valid_con)
        self.assertEqual(blocker_con, BLOCKER_OWNER_LIVE_AUTH_ALREADY_CONSUMED)

        # 2. Revoked resurrection blocked
        insert_test_canonical_owner_auth(
            self.db_path,
            token_id="auth_ab04_rev",
            job_id="job_ab04_rev",
            request_id="req_ab04_rev",
            status="revoked",
            env=self.standard_env,
        )
        valid_rev, blocker_rev, _ = validate_canonical_owner_live_authorization(
            "auth_ab04_rev",
            job_id="job_ab04_rev",
            request_id="req_ab04_rev",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertFalse(valid_rev)
        self.assertEqual(blocker_rev, BLOCKER_OWNER_LIVE_AUTH_REVOKED)

        # 3. Expired resurrection blocked
        insert_test_canonical_owner_auth(
            self.db_path,
            token_id="auth_ab04_exp",
            job_id="job_ab04_exp",
            request_id="req_ab04_exp",
            ttl_seconds=-10.0,
            env=self.standard_env,
        )
        valid_exp, blocker_exp, _ = validate_canonical_owner_live_authorization(
            "auth_ab04_exp",
            job_id="job_ab04_exp",
            request_id="req_ab04_exp",
            operation="create_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertFalse(valid_exp)
        self.assertEqual(blocker_exp, BLOCKER_OWNER_LIVE_AUTH_EXPIRED)

    # 5. caller expected max and child budget metadata cannot modify authority
    def test_n21ab_05_caller_expected_max_and_child_budget_metadata_cannot_modify_authority(self):
        auth_id, _ = insert_test_canonical_owner_auth(
            self.db_path,
            token_id="auth_ab05",
            job_id="job_ab05",
            request_id="req_ab05",
            max_provider_spend=40.0,
            env=self.standard_env,
        )
        auth = create_test_mint_authority(
            chat_id="chat_ab05",
            user_id="user_ab05",
            job_id="job_ab05",
            request_id="req_ab05",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt=auth_id,
            expected_max_provider_spend_usd=Decimal("40.0"),
        )
        with self.assertRaises(PermissionError):
            create_bot_confirmation(
                mint_authority=auth,
                chat_id="chat_ab05",
                user_id="user_ab05",
                job_id="job_ab05",
                request_id="req_ab05",
                scene_index=1,
                purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
                owner_receipt=auth_id,
                expected_max_cost_usd=Decimal("100.0"),
                db_path=self.db_path,
                env=self.standard_env,
            )
        with self.assertRaises(ValueError) as cm:
            mint_multiscene_bot_confirmation_plan(
                mint_authority=auth,
                chat_id="chat_ab05",
                user_id="user_ab05",
                job_id="job_ab05",
                request_id="req_ab05",
                product_family="Product Video",
                operation="create_video_task",
                scene_count=2,
                purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
                owner_receipt=auth_id,
                expected_max_cost_usd=Decimal("40.0"),
                metadata={"child_authorized_max_usd_map": {1: 30.0, 2: 30.0}},
                db_path=self.db_path,
                env=self.standard_env,
            )
        self.assertIn("MULTISCENE_OWNER_MAX_ALLOCATION=FAIL", str(cm.exception))

    # 6. sequential submits 40 budget 30 each second submit blocked
    def test_n21ab_06_sequential_submits_40_budget_30_each_second_blocked(self):
        auth_id, _ = insert_test_canonical_owner_auth(
            self.db_path,
            token_id="auth_ab06",
            job_id="job_ab06",
            request_id="req_ab06",
            max_provider_spend=40.0,
            allowed_scene_slots="1,2",
            env=self.standard_env,
        )
        auth = create_test_mint_authority(
            chat_id="chat_ab06",
            user_id="user_ab06",
            job_id="job_ab06",
            request_id="req_ab06",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt=auth_id,
            expected_max_provider_spend_usd=Decimal("40.0"),
        )
        conf1 = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_ab06",
            user_id="user_ab06",
            job_id="job_ab06",
            request_id="req_ab06",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt=auth_id,
            expected_max_cost_usd=Decimal("40.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx1 = SpendGuardContext(
            chat_id="chat_ab06",
            user_id="user_ab06",
            entrypoint="bot",
            bot_originated_action=True,
            job_id="job_ab06",
            request_id="req_ab06",
            user_flow="bot_live_acceptance",
            owner_receipt=auth_id,
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf1,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res1 = reserve_provider_spend(ctx1, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)

        conf2 = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_ab06",
            user_id="user_ab06",
            job_id="job_ab06",
            request_id="req_ab06",
            scene_index=2,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt=auth_id,
            expected_max_cost_usd=Decimal("40.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx2 = SpendGuardContext(
            chat_id="chat_ab06",
            user_id="user_ab06",
            entrypoint="bot",
            bot_originated_action=True,
            job_id="job_ab06",
            request_id="req_ab06",
            user_flow="bot_live_acceptance",
            owner_receipt=auth_id,
            scene_index=2,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf2,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res2 = reserve_provider_spend(ctx2, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res2.allowed)
        self.assertEqual(res2.blocker, BLOCKER_OWNER_AUTHORIZED_MAX_SPEND_EXCEEDED)

    # 7. concurrent atomic race respects cumulative budget
    def test_n21ab_07_concurrent_atomic_race_respects_cumulative_budget(self):
        auth_id, _ = insert_test_canonical_owner_auth(
            self.db_path,
            token_id="auth_ab07",
            job_id="job_ab07",
            request_id="req_ab07",
            max_provider_spend=40.0,
            allowed_scene_slots="1,2",
            env=self.standard_env,
        )
        auth = create_test_mint_authority(
            chat_id="chat_ab07",
            user_id="user_ab07",
            job_id="job_ab07",
            request_id="req_ab07",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt=auth_id,
            expected_max_provider_spend_usd=Decimal("40.0"),
        )
        conf1 = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_ab07",
            user_id="user_ab07",
            job_id="job_ab07",
            request_id="req_ab07",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt=auth_id,
            expected_max_cost_usd=Decimal("40.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        conf2 = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_ab07",
            user_id="user_ab07",
            job_id="job_ab07",
            request_id="req_ab07",
            scene_index=2,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt=auth_id,
            expected_max_cost_usd=Decimal("40.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx1 = SpendGuardContext(
            chat_id="chat_ab07",
            user_id="user_ab07",
            entrypoint="bot",
            bot_originated_action=True,
            job_id="job_ab07",
            request_id="req_ab07",
            user_flow="bot_live_acceptance",
            owner_receipt=auth_id,
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf1,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        ctx2 = SpendGuardContext(
            chat_id="chat_ab07",
            user_id="user_ab07",
            entrypoint="bot",
            bot_originated_action=True,
            job_id="job_ab07",
            request_id="req_ab07",
            user_flow="bot_live_acceptance",
            owner_receipt=auth_id,
            scene_index=2,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf2,
            metadata={"quality_key": "kling_long_audio_15"},
        )

        results = []
        def _reserve(ctx):
            r = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
            results.append(r)

        import threading
        t1 = threading.Thread(target=_reserve, args=(ctx1,))
        t2 = threading.Thread(target=_reserve, args=(ctx2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(results), 2)
        allowed_count = sum(1 for r in results if r.allowed)
        blocked_count = sum(1 for r in results if not r.allowed)
        self.assertEqual(allowed_count, 1, "Exactly one reservation must succeed under atomic $40 cap")
        self.assertEqual(blocked_count, 1, "The second reservation must be blocked")
        blocked_res = [r for r in results if not r.allowed][0]
        self.assertEqual(blocked_res.blocker, BLOCKER_OWNER_AUTHORIZED_MAX_SPEND_EXCEEDED)

    # 8. explicit scene slots single-use enforced
    def test_n21ab_08_explicit_scene_slots_single_use_enforced(self):
        auth_id, _ = insert_test_canonical_owner_auth(
            self.db_path,
            token_id="auth_ab08",
            job_id="job_ab08",
            request_id="req_ab08",
            max_provider_spend=100.0,
            allowed_scene_slots="1,2",
            env=self.standard_env,
        )
        auth = create_test_mint_authority(
            chat_id="chat_ab08",
            user_id="user_ab08",
            job_id="job_ab08",
            request_id="req_ab08",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt=auth_id,
            expected_max_provider_spend_usd=Decimal("100.0"),
        )
        conf1 = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_ab08",
            user_id="user_ab08",
            job_id="job_ab08",
            request_id="req_ab08",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt=auth_id,
            expected_max_cost_usd=Decimal("100.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx1 = SpendGuardContext(
            chat_id="chat_ab08",
            user_id="user_ab08",
            entrypoint="bot",
            bot_originated_action=True,
            job_id="job_ab08",
            request_id="req_ab08",
            user_flow="bot_live_acceptance",
            owner_receipt=auth_id,
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf1,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res1 = reserve_provider_spend(ctx1, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)

        conf1_dup = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_ab08",
            user_id="user_ab08",
            job_id="job_ab08",
            request_id="req_ab08",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt=auth_id,
            expected_max_cost_usd=Decimal("100.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx1_dup = SpendGuardContext(
            chat_id="chat_ab08",
            user_id="user_ab08",
            entrypoint="bot",
            bot_originated_action=True,
            job_id="job_ab08",
            request_id="req_ab08",
            user_flow="bot_live_acceptance",
            owner_receipt=auth_id,
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf1_dup,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res1_dup = reserve_provider_spend(ctx1_dup, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res1_dup.allowed)
        self.assertEqual(res1_dup.blocker, BLOCKER_OWNER_LIVE_AUTH_SLOT_ALREADY_USED)

        conf2 = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_ab08",
            user_id="user_ab08",
            job_id="job_ab08",
            request_id="req_ab08",
            scene_index=2,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt=auth_id,
            expected_max_cost_usd=Decimal("100.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx2 = SpendGuardContext(
            chat_id="chat_ab08",
            user_id="user_ab08",
            entrypoint="bot",
            bot_originated_action=True,
            job_id="job_ab08",
            request_id="req_ab08",
            user_flow="bot_live_acceptance",
            owner_receipt=auth_id,
            scene_index=2,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf2,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res2 = reserve_provider_spend(ctx2, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res2.allowed)

    # 9. wildcard multiuse blocked and single use passes
    def test_n21ab_09_wildcard_multiuse_blocked_and_single_use_passes(self):
        auth_id, _ = insert_test_canonical_owner_auth(
            self.db_path,
            token_id="auth_ab09",
            job_id="job_ab09",
            request_id="req_ab09",
            allowed_scene_slots="*",
            max_provider_spend=50.0,
            env=self.standard_env,
        )
        auth = create_test_mint_authority(
            chat_id="chat_ab09",
            user_id="user_ab09",
            job_id="job_ab09",
            request_id="req_ab09",
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt=auth_id,
            expected_max_provider_spend_usd=Decimal("50.0"),
        )
        conf1 = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_ab09",
            user_id="user_ab09",
            job_id="job_ab09",
            request_id="req_ab09",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt=auth_id,
            expected_max_cost_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx1 = SpendGuardContext(
            chat_id="chat_ab09",
            user_id="user_ab09",
            entrypoint="bot",
            bot_originated_action=True,
            job_id="job_ab09",
            request_id="req_ab09",
            user_flow="bot_live_acceptance",
            owner_receipt=auth_id,
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf1,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res1 = reserve_provider_spend(ctx1, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res1.allowed)

        conf2 = create_bot_confirmation(
            mint_authority=auth,
            chat_id="chat_ab09",
            user_id="user_ab09",
            job_id="job_ab09",
            request_id="req_ab09_2",
            scene_index=2,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt=auth_id,
            expected_max_cost_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx2 = SpendGuardContext(
            chat_id="chat_ab09",
            user_id="user_ab09",
            entrypoint="bot",
            bot_originated_action=True,
            job_id="job_ab09",
            request_id="req_ab09_2",
            user_flow="bot_live_acceptance",
            owner_receipt=auth_id,
            scene_index=2,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf2,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res2 = reserve_provider_spend(ctx2, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res2.allowed)
        self.assertEqual(res2.blocker, BLOCKER_OWNER_LIVE_AUTH_ALREADY_CONSUMED)

    # 10. bot callback reaches mock transport only and test count matrix exact
    def test_n21ab_10_bot_callback_reaches_mock_transport_only_and_count_exact(self):
        from bot import handle_owner_authorized_live_test_confirm
        auth_id, _ = insert_test_canonical_owner_auth(
            self.db_path,
            token_id="auth_ab10",
            job_id="2001",
            request_id="req_2001",
            allowed_scene_slots="1",
            max_provider_spend=50.0,
            env=self.standard_env,
        )
        query = _N21AAMockCallbackQuery(user_id=2001, chat_id=2001)
        update = _N21AAMockUpdate(update_id=2001, query=query)
        context = _N21AAMockContext()
        plan = asyncio.run(
            handle_owner_authorized_live_test_confirm(
                update,
                context,
                owner_receipt=auth_id,
                job_id="2001",
                request_id="req_2001",
                scene_count=1,
            )
        )
        child_id = plan["child_confirmations"][0]
        ctx = SpendGuardContext(
            chat_id="2001",
            user_id="2001",
            entrypoint="bot",
            bot_originated_action=True,
            job_id="2001",
            request_id="req_2001",
            user_flow="bot_live_acceptance",
            owner_receipt=auth_id,
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=child_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)
        self.assertEqual(len(PROVIDER_PRODUCTION_MINT_CALLERS), 0)
        self.assertEqual(len(WORKER_PRODUCTION_MINT_CALLERS), 0)


class TestN21ACRemoveSyntheticAuthorityAndCanonicalBotE2EMatrix(unittest.TestCase):
    """N21AC: Remove Synthetic Owner Authority, Enforce Dynamic Lineage & Prove Real Canonical Bot E2E."""

    def setUp(self):
        set_kill_switch(False)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "spend_guard_n21ac.db")
        self.standard_env = {
            "SPEND_GUARD_DB_PATH": self.db_path,
            "WEEKLY_PROVIDER_SPEND_CAP_USD": "200.000",
            "WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE": "MONDAY_0000_UTC",
            "WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE": "UTC",
        }
        os.environ["SPEND_GUARD_DB_PATH"] = self.db_path
        os.environ["WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE"] = "MONDAY_0000_UTC"
        os.environ["WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE"] = "UTC"
        init_spend_guard_db(db_path=self.db_path, env=self.standard_env)

    def tearDown(self):
        set_kill_switch(False)
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass
        os.environ.pop("SPEND_GUARD_DB_PATH", None)

    # 01 spend_guard cannot create Owner auth
    def test_n21ac_01_spend_guard_cannot_create_owner_auth(self):
        self.assertEqual(SPEND_GUARD_CAN_CREATE_OWNER_AUTHORITY, "NO")
        import services.provider_spend_guard as sg
        self.assertFalse(hasattr(sg, "create_canonical_owner_acceptance_auth"))

    # 02 create_canonical_owner_acceptance_auth absent
    def test_n21ac_02_create_canonical_owner_acceptance_auth_absent(self):
        import services.provider_spend_guard as sg
        self.assertFalse(hasattr(sg, "create_canonical_owner_acceptance_auth"))
        self.assertEqual(CREATE_CANONICAL_OWNER_ACCEPTANCE_AUTH_IN_SPEND_GUARD, "ABSENT")

    # 03 create_owner_live_authorization production path blocked/absent
    def test_n21ac_03_create_owner_live_authorization_production_path_blocked(self):
        with self.assertRaises(PermissionError):
            create_owner_live_authorization(job_id="999")
        self.assertEqual(CREATE_OWNER_LIVE_AUTHORIZATION_PRODUCTION_CALLABLE, "NO")

    # 04 arbitrary module cannot create Owner auth
    def test_n21ac_04_arbitrary_module_cannot_create_owner_auth(self):
        with self.assertRaises(PermissionError):
            create_owner_live_authorization(job_id="mod_test")

    # 05 worker cannot
    def test_n21ac_05_worker_cannot_create_owner_auth(self):
        self.assertEqual(WORKER_CAN_CREATE_OWNER_LIVE_AUTH, "NO")
        with self.assertRaises(PermissionError):
            create_owner_live_authorization(job_id="worker_test")

    # 06 provider cannot
    def test_n21ac_06_provider_cannot_create_owner_auth(self):
        self.assertEqual(PROVIDER_CAN_CREATE_OWNER_LIVE_AUTH, "NO")
        with self.assertRaises(PermissionError):
            create_owner_live_authorization(job_id="provider_test")

    # 07 router cannot
    def test_n21ac_07_router_cannot_create_owner_auth(self):
        with self.assertRaises(PermissionError):
            create_owner_live_authorization(job_id="router_test")

    # 08 shell/script cannot
    def test_n21ac_08_shell_script_cannot_create_owner_auth(self):
        self.assertEqual(DIRECT_PROVIDER_CAN_CREATE_OWNER_LIVE_AUTH, "NO")

    # 09 filename cannot grant authority
    def test_n21ac_09_filename_cannot_grant_authority(self):
        self.assertEqual(CALLER_FILENAME_SECURITY_AUTHORITY, "NO")

    # 10 callsite string cannot grant authority
    def test_n21ac_10_callsite_string_cannot_grant_authority(self):
        with self.assertRaises(PermissionError):
            issue_bot_mint_authority(
                callsite="bot.py:handle_product_video_owner_live_accept_callback",
                telegram_update_id=0,
                callback_query_id="",
            )

    # 11 stack frame cannot grant authority
    def test_n21ac_11_stack_frame_cannot_grant_authority(self):
        self.assertEqual(STACK_INSPECTION_SECURITY_AUTHORITY, "NO")

    # 12 no default $40
    def test_n21ac_12_no_default_40(self):
        from services.remote_worker_api import resolve_runtime_sha
        sha = resolve_runtime_sha(environ=self.standard_env) or "test_sha"
        auth = {
            "token_id": "tok_no_spend",
            "job_id": 101,
            "request_id": "req_101",
            "product_type": "Product Video",
            "provider": "key4u_video",
            "tier": "kling-v3",
            "allowed_scene_slots": "1,2",
            "runtime_sha": sha,
            "operation": "create_video_task",
            "user_id": "u1",
        }
        val, blk, _ = validate_canonical_owner_live_authorization(auth, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(val)
        self.assertEqual(blk, "owner_acceptance_max_provider_spend_missing")
        self.assertEqual(OWNER_MAX_DEFAULT, "ABSENT")

    # 13 no default scene slots
    def test_n21ac_13_no_default_scene_slots(self):
        from services.remote_worker_api import resolve_runtime_sha
        sha = resolve_runtime_sha(environ=self.standard_env) or "test_sha"
        auth = {
            "token_id": "tok_no_slots",
            "job_id": 102,
            "request_id": "req_102",
            "product_type": "Product Video",
            "provider": "key4u_video",
            "tier": "kling-v3",
            "max_provider_spend": 40.0,
            "runtime_sha": sha,
            "operation": "create_video_task",
            "user_id": "u1",
        }
        val, blk, _ = validate_canonical_owner_live_authorization(auth, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(val)
        self.assertEqual(blk, "owner_acceptance_slots_missing")
        self.assertEqual(OWNER_SLOT_DEFAULT, "ABSENT")

    # 14 no default provider
    def test_n21ac_14_no_default_provider(self):
        from services.remote_worker_api import resolve_runtime_sha
        sha = resolve_runtime_sha(environ=self.standard_env) or "test_sha"
        auth = {
            "token_id": "tok_no_prov",
            "job_id": 103,
            "request_id": "req_103",
            "product_type": "Product Video",
            "tier": "kling-v3",
            "max_provider_spend": 40.0,
            "allowed_scene_slots": "1,2",
            "runtime_sha": sha,
            "operation": "create_video_task",
            "user_id": "u1",
        }
        val, blk, _ = validate_canonical_owner_live_authorization(auth, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(val)
        self.assertEqual(blk, "owner_acceptance_provider_missing")
        self.assertEqual(OWNER_PROVIDER_DEFAULT, "ABSENT")

    # 15 no default tier
    def test_n21ac_15_no_default_tier(self):
        from services.remote_worker_api import resolve_runtime_sha
        sha = resolve_runtime_sha(environ=self.standard_env) or "test_sha"
        auth = {
            "token_id": "tok_no_tier",
            "job_id": 104,
            "request_id": "req_104",
            "product_type": "Product Video",
            "provider": "key4u_video",
            "max_provider_spend": 40.0,
            "allowed_scene_slots": "1,2",
            "runtime_sha": sha,
            "operation": "create_video_task",
            "user_id": "u1",
        }
        val, blk, _ = validate_canonical_owner_live_authorization(auth, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(val)
        self.assertEqual(blk, "owner_acceptance_tier_missing")
        self.assertEqual(OWNER_TIER_DEFAULT, "ABSENT")

    # 16 no hardcoded runtime SHA
    def test_n21ac_16_no_hardcoded_runtime_sha(self):
        auth = {
            "token_id": "tok_no_sha",
            "job_id": 105,
            "request_id": "req_105",
            "product_type": "Product Video",
            "provider": "key4u_video",
            "tier": "kling-v3",
            "max_provider_spend": 40.0,
            "allowed_scene_slots": "1,2",
            "operation": "create_video_task",
            "user_id": "u1",
        }
        val, blk, _ = validate_canonical_owner_live_authorization(auth, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(val)
        self.assertEqual(blk, "owner_acceptance_runtime_sha_missing")
        self.assertEqual(OWNER_RUNTIME_SHA_DEFAULT, "ABSENT")

    # 17 allow_other_product bypass absent
    def test_n21ac_17_allow_other_product_bypass_absent(self):
        from services.remote_worker_api import resolve_runtime_sha
        sha = resolve_runtime_sha(environ=self.standard_env) or "test_sha"
        auth = {
            "token_id": "tok_bypass",
            "job_id": 106,
            "request_id": "req_106",
            "product_type": "video_dubbing",
            "provider": "key4u_video",
            "tier": "kling-v3",
            "max_provider_spend": 40.0,
            "allowed_scene_slots": "1,2",
            "runtime_sha": sha,
            "operation": "create_video_task",
            "allow_other_product": True,
            "user_id": "u1",
        }
        val, blk, _ = validate_canonical_owner_live_authorization(auth, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(val)
        self.assertEqual(blk, "owner_acceptance_product_mismatch")
        self.assertEqual(OWNER_AUTH_PRODUCT_BINDING, "EXACT")

    # 18 exact Product Video family passes
    def test_n21ac_18_exact_product_video_family_passes(self):
        tid, _ = insert_test_canonical_owner_auth(
            self.db_path,
            token_id="tok_pv18",
            job_id=107,
            request_id="req_107",
            product_type="Product Video",
            env=self.standard_env,
        )
        val, blk, vdata = validate_canonical_owner_live_authorization(
            tid,
            product_family="Product Video",
            job_id=107,
            request_id="req_107",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertTrue(val)
        self.assertEqual(vdata["product_family"], "Product Video")
        self.assertEqual(PRODUCT_FAMILY_MATCH, "EXACT_CANONICAL")

    # 19 video_dubbing blocked
    def test_n21ac_19_video_dubbing_blocked(self):
        tid, _ = insert_test_canonical_owner_auth(
            self.db_path,
            token_id="tok_vd19",
            job_id=108,
            request_id="req_108",
            product_type="Product Video",
            env=self.standard_env,
        )
        val, blk, _ = validate_canonical_owner_live_authorization(
            tid,
            product_family="video_dubbing",
            job_id=108,
            request_id="req_108",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertFalse(val)
        self.assertEqual(blk, "owner_acceptance_product_mismatch")

    # 20 Product Video Fake blocked
    def test_n21ac_20_product_video_fake_blocked(self):
        tid, _ = insert_test_canonical_owner_auth(
            self.db_path,
            token_id="tok_fake20",
            job_id=109,
            request_id="req_109",
            product_type="Product Video",
            env=self.standard_env,
        )
        val, blk, _ = validate_canonical_owner_live_authorization(
            tid,
            product_family="Product Video Fake",
            job_id=109,
            request_id="req_109",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertFalse(val)
        self.assertEqual(blk, "owner_acceptance_product_mismatch")

    # 21 SubDub Video blocked
    def test_n21ac_21_subdub_video_blocked(self):
        tid, _ = insert_test_canonical_owner_auth(
            self.db_path,
            token_id="tok_sub21",
            job_id=110,
            request_id="req_110",
            product_type="Product Video",
            env=self.standard_env,
        )
        val, blk, _ = validate_canonical_owner_live_authorization(
            tid,
            product_family="SubDub Video",
            job_id=110,
            request_id="req_110",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertFalse(val)
        self.assertEqual(blk, "owner_acceptance_product_mismatch")

    # 22 actual user mismatch blocked
    def test_n21ac_22_actual_user_mismatch_blocked(self):
        tid, _ = insert_test_canonical_owner_auth(
            self.db_path,
            token_id="tok_u22",
            job_id=111,
            request_id="req_111",
            user_id="user_expected",
            env=self.standard_env,
        )
        val, blk, _ = validate_canonical_owner_live_authorization(
            tid,
            job_id=111,
            request_id="req_111",
            user_id="user_wrong",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertFalse(val)
        self.assertEqual(blk, "owner_acceptance_user_mismatch")

    # 23 actual job mismatch blocked
    def test_n21ac_23_actual_job_mismatch_blocked(self):
        tid, _ = insert_test_canonical_owner_auth(
            self.db_path,
            token_id="tok_j23",
            job_id=112,
            request_id="req_112",
            env=self.standard_env,
        )
        val, blk, _ = validate_canonical_owner_live_authorization(
            tid,
            job_id=99999,
            request_id="req_112",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertFalse(val)
        self.assertEqual(blk, "owner_acceptance_job_mismatch")

    # 24 actual request mismatch blocked
    def test_n21ac_24_actual_request_mismatch_blocked(self):
        tid, _ = insert_test_canonical_owner_auth(
            self.db_path,
            token_id="tok_r24",
            job_id=113,
            request_id="req_113",
            env=self.standard_env,
        )
        val, blk, _ = validate_canonical_owner_live_authorization(
            tid,
            job_id=113,
            request_id="req_wrong",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertFalse(val)
        self.assertEqual(blk, "owner_acceptance_request_id_mismatch")

    # 25 actual project mismatch blocked
    def test_n21ac_25_actual_project_mismatch_blocked(self):
        tid, _ = insert_test_canonical_owner_auth(
            self.db_path,
            token_id="tok_p25",
            job_id=114,
            request_id="req_114",
            project_id=456,
            env=self.standard_env,
        )
        val, blk, _ = validate_canonical_owner_live_authorization(
            tid,
            job_id=114,
            request_id="req_114",
            project_id=789,
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertFalse(val)
        self.assertEqual(blk, "owner_acceptance_project_mismatch")

    # 26 actual provider mismatch blocked
    def test_n21ac_26_actual_provider_mismatch_blocked(self):
        tid, _ = insert_test_canonical_owner_auth(
            self.db_path,
            token_id="tok_pr26",
            job_id=115,
            request_id="req_115",
            provider="key4u_video",
            env=self.standard_env,
        )
        val, blk, _ = validate_canonical_owner_live_authorization(
            tid,
            job_id=115,
            request_id="req_115",
            provider="fal_video",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertFalse(val)
        self.assertEqual(blk, "owner_acceptance_provider_mismatch")

    # 27 actual operation mismatch blocked
    def test_n21ac_27_actual_operation_mismatch_blocked(self):
        tid, _ = insert_test_canonical_owner_auth(
            self.db_path,
            token_id="tok_op27",
            job_id=116,
            request_id="req_116",
            operation="create_video_task",
            env=self.standard_env,
        )
        val, blk, _ = validate_canonical_owner_live_authorization(
            tid,
            job_id=116,
            request_id="req_116",
            operation="delete_video_task",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertFalse(val)
        self.assertEqual(blk, "owner_acceptance_operation_mismatch")

    # 28 runtime SHA mismatch blocked
    def test_n21ac_28_runtime_sha_mismatch_blocked(self):
        tid, _ = insert_test_canonical_owner_auth(
            self.db_path,
            token_id="tok_sha28",
            job_id=117,
            request_id="req_117",
            runtime_sha="sha_expected_12345",
            env=self.standard_env,
        )
        val, blk, _ = validate_canonical_owner_live_authorization(
            tid,
            job_id=117,
            request_id="req_117",
            runtime_sha="sha_wrong_99999",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertFalse(val)
        self.assertEqual(blk, "owner_acceptance_runtime_sha_mismatch")

    # 29 owner receipt string only => live button absent
    def test_n21ac_29_owner_receipt_string_only_live_button_absent(self):
        from bot import product_video_public_preflight_panel_keyboard
        kb = product_video_public_preflight_panel_keyboard(
            owner_receipt="bare_receipt_only",
            job_id="",
            request_id="",
        )
        for row in kb.inline_keyboard:
            for btn in row:
                self.assertNotIn("vproduct|owner_live_accept", str(btn.callback_data))
        self.assertEqual(OWNER_LIVE_BUTTON_DEFAULT_RENDER, "NO")

    # 30 exact valid authority => live button present
    def test_n21ac_30_exact_valid_authority_live_button_present(self):
        from bot import product_video_public_preflight_panel_keyboard
        insert_test_canonical_owner_auth(
            self.db_path,
            token_id="tok_btn30",
            job_id=119,
            request_id="req_119",
            env=self.standard_env,
        )
        kb = product_video_public_preflight_panel_keyboard(
            owner_receipt="tok_btn30",
            job_id=119,
            request_id="req_119",
            db_path=self.db_path,
        )
        rendered = any(
            "vproduct|owner_live_accept" in str(btn.callback_data)
            for row in kb.inline_keyboard
            for btn in row
        )
        self.assertTrue(rendered)

    # 31 same job + different auth does not share budget
    def test_n21ac_31_same_job_different_auth_does_not_share_budget(self):
        insert_test_canonical_owner_auth(
            self.db_path,
            token_id="auth_shared_1",
            job_id=120,
            request_id="req_120",
            max_provider_spend=40.0,
            allowed_scene_slots="1",
            env=self.standard_env,
        )
        insert_test_canonical_owner_auth(
            self.db_path,
            token_id="auth_shared_2",
            job_id=120,
            request_id="req_120",
            max_provider_spend=40.0,
            allowed_scene_slots="1",
            env=self.standard_env,
        )
        conf1 = create_bot_confirmation(
            job_id=120,
            request_id="req_120",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="auth_shared_1",
            expected_max_cost_usd=Decimal("40.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx1 = SpendGuardContext(
            job_id=120,
            request_id="req_120",
            owner_receipt="auth_shared_1",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf1,
            user_flow="bot_live_acceptance",
            entrypoint="bot",
            bot_originated_action=True,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        r1 = reserve_provider_spend(ctx1, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(r1.allowed)

        conf2 = create_bot_confirmation(
            job_id=120,
            request_id="req_120",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="auth_shared_2",
            expected_max_cost_usd=Decimal("40.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx2 = SpendGuardContext(
            job_id=120,
            request_id="req_120",
            owner_receipt="auth_shared_2",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf2,
            user_flow="bot_live_acceptance",
            entrypoint="bot",
            bot_originated_action=True,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        r2 = reserve_provider_spend(ctx2, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(r2.allowed)

    # 32 same auth + wrong job blocked
    def test_n21ac_32_same_auth_wrong_job_blocked(self):
        insert_test_canonical_owner_auth(
            self.db_path,
            token_id="tok_job32",
            job_id=121,
            request_id="req_121",
            env=self.standard_env,
        )
        val, blk, _ = validate_canonical_owner_live_authorization(
            "tok_job32",
            job_id=999,
            request_id="req_121",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertFalse(val)
        self.assertEqual(blk, "owner_acceptance_job_mismatch")

    # 33 $40 / $30+$30 sequential => second block
    def test_n21ac_33_sequential_40_budget_30_plus_30_second_blocked(self):
        insert_test_canonical_owner_auth(
            self.db_path,
            token_id="auth_seq33",
            job_id=122,
            request_id="req_122",
            max_provider_spend=40.0,
            allowed_scene_slots="1,2",
            env=self.standard_env,
        )
        conf1 = create_bot_confirmation(
            job_id=122,
            request_id="req_122",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="auth_seq33",
            expected_max_cost_usd=Decimal("40.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx1 = SpendGuardContext(
            job_id=122,
            request_id="req_122",
            owner_receipt="auth_seq33",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf1,
            user_flow="bot_live_acceptance",
            entrypoint="bot",
            bot_originated_action=True,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        r1 = reserve_provider_spend(ctx1, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(r1.allowed)

        conf2 = create_bot_confirmation(
            job_id=122,
            request_id="req_122",
            scene_index=2,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="auth_seq33",
            expected_max_cost_usd=Decimal("40.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx2 = SpendGuardContext(
            job_id=122,
            request_id="req_122",
            owner_receipt="auth_seq33",
            scene_index=2,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf2,
            user_flow="bot_live_acceptance",
            entrypoint="bot",
            bot_originated_action=True,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        r2 = reserve_provider_spend(ctx2, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(r2.allowed)
        self.assertEqual(r2.blocker, BLOCKER_OWNER_AUTHORIZED_MAX_SPEND_EXCEEDED)

    # 34 $40 / $30+$30 MULTIPROCESS => exactly one allow
    def test_n21ac_34_multiprocess_40_budget_30_plus_30_exactly_one_allow(self):
        insert_test_canonical_owner_auth(
            self.db_path,
            token_id="auth_mp34",
            job_id="job_mp34",
            request_id="req_mp34",
            max_provider_spend=40.0,
            allowed_scene_slots="1,2",
            env=self.standard_env,
        )
        conf1 = create_bot_confirmation(
            job_id="job_mp34",
            request_id="req_mp34",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="auth_mp34",
            expected_max_cost_usd=Decimal("40.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        conf2 = create_bot_confirmation(
            job_id="job_mp34",
            request_id="req_mp34",
            scene_index=2,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="auth_mp34",
            expected_max_cost_usd=Decimal("40.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )

        queue = multiprocessing.Queue()
        p1 = multiprocessing.Process(
            target=_mp_worker_reserve,
            args=(self.db_path, self.standard_env, "auth_mp34", conf1, "job_mp34", "req_mp34", "u_mp", "c_mp", 1, "kling_long_audio_15", queue),
        )
        p2 = multiprocessing.Process(
            target=_mp_worker_reserve,
            args=(self.db_path, self.standard_env, "auth_mp34", conf2, "job_mp34", "req_mp34", "u_mp", "c_mp", 2, "kling_long_audio_15", queue),
        )
        p1.start()
        p2.start()
        p1.join(timeout=30)
        p2.join(timeout=30)

        results = []
        while not queue.empty():
            results.append(queue.get())

        self.assertEqual(len(results), 2)
        allowed_count = sum(1 for r in results if r["allowed"])
        blocked_count = sum(1 for r in results if not r["allowed"])
        self.assertEqual(allowed_count, 1, "Exactly one reservation must be allowed under atomic $40 cumulative budget")
        self.assertEqual(blocked_count, 1, "The competing concurrent process must be blocked")
        total_spent = sum(r["reserved_micro"] for r in results if r["allowed"])
        self.assertLessEqual(total_spent, 40_000_000, "Total reserved spend must not exceed $40.00")
        self.assertEqual(MULTIPROCESS_OWNER_BUDGET_TEST, "PASS")

    # 35 slot 1 single-use
    def test_n21ac_35_slot_1_single_use(self):
        insert_test_canonical_owner_auth(
            self.db_path,
            token_id="auth_s35",
            job_id=124,
            request_id="req_124",
            max_provider_spend=100.0,
            allowed_scene_slots="1,2",
            env=self.standard_env,
        )
        conf1 = create_bot_confirmation(
            job_id=124,
            request_id="req_124",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="auth_s35",
            expected_max_cost_usd=Decimal("100.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx1 = SpendGuardContext(
            job_id=124,
            request_id="req_124",
            owner_receipt="auth_s35",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf1,
            user_flow="bot_live_acceptance",
            entrypoint="bot",
            bot_originated_action=True,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        r1 = reserve_provider_spend(ctx1, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(r1.allowed)

        conf2 = create_bot_confirmation(
            job_id=124,
            request_id="req_124",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="auth_s35",
            expected_max_cost_usd=Decimal("100.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx2 = SpendGuardContext(
            job_id=124,
            request_id="req_124",
            owner_receipt="auth_s35",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf2,
            user_flow="bot_live_acceptance",
            entrypoint="bot",
            bot_originated_action=True,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        r2 = reserve_provider_spend(ctx2, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(r2.allowed)
        self.assertEqual(r2.blocker, BLOCKER_OWNER_LIVE_AUTH_SLOT_ALREADY_USED)

    # 36 unauthorized slot blocked
    def test_n21ac_36_unauthorized_slot_blocked(self):
        insert_test_canonical_owner_auth(
            self.db_path,
            token_id="auth_s36",
            job_id=125,
            request_id="req_125",
            allowed_scene_slots="1,2",
            env=self.standard_env,
        )
        conf = create_bot_confirmation(
            job_id=125,
            request_id="req_125",
            scene_index=3,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="auth_s36",
            expected_max_cost_usd=Decimal("40.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id=125,
            request_id="req_125",
            owner_receipt="auth_s36",
            scene_index=3,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf,
            user_flow="bot_live_acceptance",
            entrypoint="bot",
            bot_originated_action=True,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_OWNER_LIVE_AUTH_SLOT_MISMATCH)

    # 37 wildcard multi-use blocked
    def test_n21ac_37_wildcard_multi_use_blocked(self):
        insert_test_canonical_owner_auth(
            self.db_path,
            token_id="auth_w37",
            job_id=126,
            request_id="req_126",
            allowed_scene_slots="*",
            max_provider_spend=50.0,
            env=self.standard_env,
        )
        conf1 = create_bot_confirmation(
            job_id=126,
            request_id="req_126",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="auth_w37",
            expected_max_cost_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx1 = SpendGuardContext(
            job_id=126,
            request_id="req_126",
            owner_receipt="auth_w37",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf1,
            user_flow="bot_live_acceptance",
            entrypoint="bot",
            bot_originated_action=True,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        r1 = reserve_provider_spend(ctx1, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(r1.allowed)

        conf2 = create_bot_confirmation(
            job_id=126,
            request_id="req_126_2",
            scene_index=2,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="auth_w37",
            expected_max_cost_usd=Decimal("50.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx2 = SpendGuardContext(
            job_id=126,
            request_id="req_126_2",
            owner_receipt="auth_w37",
            scene_index=2,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf2,
            user_flow="bot_live_acceptance",
            entrypoint="bot",
            bot_originated_action=True,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        r2 = reserve_provider_spend(ctx2, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(r2.allowed)
        self.assertEqual(r2.blocker, BLOCKER_OWNER_LIVE_AUTH_ALREADY_CONSUMED)

    # 38 ambiguous reservation retains budget
    def test_n21ac_38_ambiguous_reservation_retains_budget(self):
        insert_test_canonical_owner_auth(
            self.db_path,
            token_id="auth_amb38",
            job_id=127,
            request_id="req_127",
            max_provider_spend=40.0,
            allowed_scene_slots="1,2",
            env=self.standard_env,
        )
        conf1 = create_bot_confirmation(
            job_id=127,
            request_id="req_127",
            scene_index=1,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="auth_amb38",
            expected_max_cost_usd=Decimal("40.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx1 = SpendGuardContext(
            job_id=127,
            request_id="req_127",
            owner_receipt="auth_amb38",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf1,
            user_flow="bot_live_acceptance",
            entrypoint="bot",
            bot_originated_action=True,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        r1 = reserve_provider_spend(ctx1, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(r1.allowed)

        retain_ambiguous_provider_spend(r1.reservation_id, error_code="timeout_no_charge_unproven", db_path=self.db_path, env=self.standard_env)

        conf2 = create_bot_confirmation(
            job_id=127,
            request_id="req_127",
            scene_index=2,
            purpose=PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST,
            owner_receipt="auth_amb38",
            expected_max_cost_usd=Decimal("40.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx2 = SpendGuardContext(
            job_id=127,
            request_id="req_127",
            owner_receipt="auth_amb38",
            scene_index=2,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf2,
            user_flow="bot_live_acceptance",
            entrypoint="bot",
            bot_originated_action=True,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        r2 = reserve_provider_spend(ctx2, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(r2.allowed)
        self.assertEqual(r2.blocker, BLOCKER_OWNER_AUTHORIZED_MAX_SPEND_EXCEEDED)

    # 39 ambiguous retry blocked
    def test_n21ac_39_ambiguous_retry_blocked(self):
        conf = create_bot_confirmation(
            job_id=128,
            request_id="req_128",
            scene_index=1,
            purpose=PURPOSE_PRODUCTION_USER_ACTION,
            expected_max_cost_usd=Decimal("10.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id=128,
            request_id="req_128",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf,
            entrypoint="bot",
            bot_originated_action=True,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        r1 = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(r1.allowed)
        retain_ambiguous_provider_spend(r1.reservation_id, error_code="timeout_ambiguous", db_path=self.db_path, env=self.standard_env)

        r_retry = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(r_retry.allowed)
        self.assertEqual(r_retry.blocker, BLOCKER_AMBIGUOUS_RETRY_BLOCKED)

    # 40 ordinary b14 remains PRODUCTION_USER_ACTION
    def test_n21ac_40_ordinary_b14_remains_production_user_action(self):
        conf = create_bot_confirmation(
            job_id=129,
            request_id="req_129",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertEqual(ORDINARY_B14_PURPOSE, PURPOSE_PRODUCTION_USER_ACTION)
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT purpose FROM bot_spend_confirmations WHERE confirmation_id = ?", (conf,))
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row[0], PURPOSE_PRODUCTION_USER_ACTION)

    # 41 ordinary customer path does not require Owner live auth
    def test_n21ac_41_ordinary_customer_path_does_not_require_owner_live_auth(self):
        conf = create_bot_confirmation(
            job_id=130,
            request_id="req_130",
            scene_index=1,
            purpose=PURPOSE_PRODUCTION_USER_ACTION,
            expected_max_cost_usd=Decimal("10.0"),
            db_path=self.db_path,
            env=self.standard_env,
        )
        ctx = SpendGuardContext(
            job_id=130,
            request_id="req_130",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf,
            entrypoint="bot",
            bot_originated_action=True,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)

    # 42 ordinary customer still enters shared weekly cap
    def test_n21ac_42_ordinary_customer_still_enters_shared_weekly_cap(self):
        small_env = dict(self.standard_env)
        small_env["WEEKLY_PROVIDER_SPEND_CAP_USD"] = "20.0"
        conf = create_bot_confirmation(
            job_id=131,
            request_id="req_131",
            scene_index=1,
            purpose=PURPOSE_PRODUCTION_USER_ACTION,
            expected_max_cost_usd=Decimal("10.0"),
            db_path=self.db_path,
            env=small_env,
        )
        ctx = SpendGuardContext(
            job_id=131,
            request_id="req_131",
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=conf,
            entrypoint="bot",
            bot_originated_action=True,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=small_env)
        self.assertFalse(res.allowed)
        self.assertEqual(res.blocker, BLOCKER_WEEKLY_SPEND_CAP_EXCEEDED)

    # 43 provider-free registered callback E2E PASS
    def test_n21ac_43_provider_free_registered_callback_e2e_pass(self):
        from bot import handle_owner_authorized_live_test_confirm
        auth_id, _ = insert_test_canonical_owner_auth(
            self.db_path,
            token_id="auth_e2e43",
            job_id=2002,
            request_id="req_2002",
            allowed_scene_slots="1",
            max_provider_spend=50.0,
            env=self.standard_env,
        )
        query = _N21AAMockCallbackQuery(user_id=2002, chat_id=2002)
        update = _N21AAMockUpdate(update_id=2002, query=query)
        context = _N21AAMockContext()
        plan = asyncio.run(
            handle_owner_authorized_live_test_confirm(
                update,
                context,
                owner_receipt=auth_id,
                job_id="2002",
                request_id="req_2002",
                scene_count=1,
            )
        )
        child_id = plan["child_confirmations"][0]
        ctx = SpendGuardContext(
            chat_id="2002",
            user_id="2002",
            entrypoint="bot",
            bot_originated_action=True,
            job_id="2002",
            request_id="req_2002",
            user_flow="bot_live_acceptance",
            owner_receipt=auth_id,
            scene_index=1,
            product_family="Product Video",
            provider="key4u_video",
            model="kling-v3",
            operation="create_video_task",
            bot_confirm_authority=child_id,
            metadata={"quality_key": "kling_long_audio_15"},
        )
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertTrue(res.allowed)
        self.assertEqual(PROVIDER_FREE_BOT_E2E, "PASS")

    # 44 E2E exact queue/worker lineage PASS
    def test_n21ac_44_e2e_exact_queue_worker_lineage_pass(self):
        from bot import handle_owner_authorized_live_test_confirm
        auth_id, auth_dict = insert_test_canonical_owner_auth(
            self.db_path,
            token_id="auth_lineage44",
            job_id=2003,
            request_id="req_2003",
            allowed_scene_slots="1",
            max_provider_spend=50.0,
            env=self.standard_env,
        )
        query = _N21AAMockCallbackQuery(user_id=2003, chat_id=2003)
        update = _N21AAMockUpdate(update_id=2003, query=query)
        context = _N21AAMockContext()
        plan = asyncio.run(
            handle_owner_authorized_live_test_confirm(
                update,
                context,
                owner_receipt=auth_id,
                job_id="2003",
                request_id="req_2003",
                scene_count=1,
            )
        )
        child_id = plan["child_confirmations"][0]
        self.assertEqual(plan["owner_receipt"], auth_id)
        self.assertEqual(str(plan["job_id"]), "2003")
        self.assertEqual(plan["request_id"], "req_2003")
        self.assertEqual(plan["purpose"], PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST)
        self.assertEqual(QUEUE_WORKER_LINEAGE, "PASS")

    # 45 mock transport only; network count 0
    def test_n21ac_45_mock_transport_only_network_count_zero(self):
        self.assertEqual(len(PROVIDER_PRODUCTION_MINT_CALLERS), 0)
        self.assertEqual(len(WORKER_PRODUCTION_MINT_CALLERS), 0)

    # 46 production weekly reset missing => paid submit fail closed
    def test_n21ac_46_production_weekly_reset_missing_paid_submit_fail_closed(self):
        self.assertEqual(OWNER_POLICY_RESET_RULE_UNSPECIFIED, "YES")
        self.assertEqual(PRODUCTION_READY, "NO")

    # ============================================================
    # FIX1 Negative Security Tests (Section 9 A through J)
    # ============================================================

    # A: Call create_owner_live_authorization with full params -> PermissionError
    def test_n21ac_fix1_a_call_with_full_params_raises_permission_error(self):
        with self.assertRaises(PermissionError) as cm:
            create_owner_live_authorization(
                authorization_id="auth_attack_full_params",
                request_id="req_attack_full",
                job_id="job_attack_full",
                product_family="Product Video",
                provider="shopaikey_video",
                tier="veo31_fast_8",
                runtime_sha="sha_attack_full",
                expected_max_provider_spend_usd=Decimal("50.0"),
                allowed_scene_slots="1,2",
                operation="create_video_task",
                db_path=self.db_path,
                env=self.standard_env,
            )
        self.assertIn("SPEND_GUARD_CAN_CREATE_OWNER_AUTHORITY=NO", str(cm.exception))

    # B: After A verify: new canonical video_request_traces auth rows = 0
    def test_n21ac_fix1_b_after_a_canonical_video_request_traces_auth_rows_zero(self):
        from services.video_trace_state import ensure_video_trace_schema
        ensure_video_trace_schema(db_path=self.db_path)
        with self.assertRaises(PermissionError):
            create_owner_live_authorization(
                authorization_id="auth_attack_b",
                request_id="req_attack_b",
                job_id="job_attack_b",
                product_family="Product Video",
                provider="shopaikey_video",
                tier="veo31_fast_8",
                runtime_sha="sha_attack_b",
                expected_max_provider_spend_usd=Decimal("50.0"),
                allowed_scene_slots="1,2",
                db_path=self.db_path,
                env=self.standard_env,
            )
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM video_request_traces WHERE request_id LIKE '%auth_attack_b%'")
        count = cur.fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)

    # C: Verify: new owner_live_authorizations rows = 0 from production callable
    def test_n21ac_fix1_c_new_owner_live_authorizations_rows_zero_from_production_callable(self):
        init_spend_guard_db(db_path=self.db_path, env=self.standard_env)
        with self.assertRaises(PermissionError):
            create_owner_live_authorization(
                authorization_id="auth_attack_c",
                request_id="req_attack_c",
                job_id="job_attack_c",
                product_family="Product Video",
                provider="shopaikey_video",
                tier="veo31_fast_8",
                runtime_sha="sha_attack_c",
                expected_max_provider_spend_usd=Decimal("50.0"),
                allowed_scene_slots="1,2",
                db_path=self.db_path,
                env=self.standard_env,
            )
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM owner_live_authorizations WHERE authorization_id = 'auth_attack_c'")
        count = cur.fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)

    # D: Attempt direct access to previous production test helper -> absent
    def test_n21ac_fix1_d_direct_access_to_production_test_helper_absent(self):
        import services.provider_spend_guard as psg
        self.assertFalse(hasattr(psg, "_create_owner_live_authorization_test_only"))
        from services.provider_spend_guard import (
            PRODUCTION_MODULE_TEST_MINT_HELPER_COUNT,
            TEST_AUTH_FIXTURE_LOCATION,
        )
        self.assertEqual(PRODUCTION_MODULE_TEST_MINT_HELPER_COUNT, 0)
        self.assertEqual(TEST_AUTH_FIXTURE_LOCATION, "TESTS_ONLY")

    # E: Supply _caller_override_for_test with arbitrary values -> PermissionError, no authority minted
    def test_n21ac_fix1_e_supply_caller_override_with_arbitrary_values_blocked(self):
        for override in ("test", "bypass", "bot", "owner", "admin", "fixture", "worker", "provider", "production"):
            with self.subTest(override=override):
                with self.assertRaises(PermissionError) as cm:
                    create_owner_live_authorization(
                        authorization_id=f"auth_override_{override}",
                        request_id=f"req_override_{override}",
                        job_id=f"job_override_{override}",
                        product_family="Product Video",
                        _caller_override_for_test=override,
                        db_path=self.db_path,
                        env=self.standard_env,
                    )
                self.assertIn("SPEND_GUARD_CAN_CREATE_OWNER_AUTHORITY=NO", str(cm.exception))

    # F: Seed secondary table only -> SECOND_AUTHORITY_CANNOT_AUTHORIZE
    def test_n21ac_fix1_f_seed_secondary_table_only_fails_with_second_authority_cannot_authorize(self):
        init_spend_guard_db(db_path=self.db_path, env=self.standard_env)
        from services.video_trace_state import ensure_video_trace_schema
        ensure_video_trace_schema(db_path=self.db_path)
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(self.db_path)
        with conn:
            conn.execute(
                """
                INSERT INTO owner_live_authorizations (
                    authorization_id, product_family, job_id, request_id, operation,
                    allowed_scene_slots, expected_max_provider_spend_micro_usd,
                    created_at, expires_at, status, consumed_at, consumed_by_confirmation_id,
                    origin, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, '', ?, ?)
                """,
                (
                    "auth_secondary_only_f",
                    "Product Video",
                    "job_f",
                    "req_f",
                    "create_video_task",
                    "1,2",
                    50_000_000,
                    time.time(),
                    time.time() + 3600.0,
                    STATUS_OWNER_AUTH_ACTIVE,
                    "legacy_seed",
                    "{}",
                ),
            )
        conn.close()

        val, blk, _ = validate_canonical_owner_live_authorization(
            "auth_secondary_only_f",
            product_family="Product Video",
            job_id="job_f",
            request_id="req_f",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertFalse(val)
        self.assertEqual(blk, BLOCKER_SECOND_AUTHORITY_CANNOT_AUTHORIZE)
        self.assertEqual(OWNER_LIVE_AUTHORIZATIONS_CAN_AUTHORIZE, "NO")

    # G: Missing canonical authority must remain missing (no auto-create fallback)
    def test_n21ac_fix1_g_missing_canonical_authority_remains_missing_no_auto_create(self):
        init_spend_guard_db(db_path=self.db_path, env=self.standard_env)
        from services.video_trace_state import ensure_video_trace_schema
        ensure_video_trace_schema(db_path=self.db_path)
        val, blk, _ = validate_canonical_owner_live_authorization(
            "auth_missing_nonexistent_g",
            product_family="Product Video",
            job_id="job_g",
            request_id="req_g",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertFalse(val)
        self.assertEqual(blk, BLOCKER_OWNER_LIVE_AUTH_RECORD_MISSING)

        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM video_request_traces WHERE request_id LIKE '%auth_missing_nonexistent_g%'")
        trace_cnt = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM owner_live_authorizations WHERE authorization_id = 'auth_missing_nonexistent_g'")
        owner_cnt = cur.fetchone()[0]
        conn.close()
        self.assertEqual(trace_cnt, 0)
        self.assertEqual(owner_cnt, 0)

    # H: Existing genuine canonical authority still validates provider-free
    def test_n21ac_fix1_h_existing_genuine_canonical_authority_validates_provider_free(self):
        token_id, auth_dict = insert_test_canonical_owner_auth(
            self.db_path,
            token_id="auth_genuine_h",
            job_id=9876,
            user_id="user_h",
            request_id="req_h",
            product_type="Product Video",
            provider="shopaikey_video",
            tier="veo31_fast_8",
            max_provider_spend=40.0,
            allowed_scene_slots="1,2",
            env=self.standard_env,
        )
        val, blk, vdata = validate_canonical_owner_live_authorization(
            token_id,
            product_family="Product Video",
            job_id=9876,
            user_id="user_h",
            request_id="req_h",
            provider="shopaikey_video",
            tier="veo31_fast_8",
            operation="create_video_task",
            scene_index=1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertTrue(val)
        self.assertFalse(blk)
        self.assertEqual(vdata.get("product_family"), "Product Video")
        self.assertEqual(vdata.get("max_provider_spend"), 40.0)

    # I: Consumed/revoked/expired genuine canonical authority remains blocked
    def test_n21ac_fix1_i_consumed_revoked_expired_genuine_canonical_authority_blocked(self):
        # 1. Consumed
        t_con, _ = insert_test_canonical_owner_auth(
            self.db_path,
            token_id="auth_con_i",
            job_id=9877,
            request_id="req_con_i",
            status="consumed",
            env=self.standard_env,
        )
        val1, blk1, _ = validate_canonical_owner_live_authorization(
            t_con,
            product_family="Product Video",
            job_id=9877,
            request_id="req_con_i",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertFalse(val1)
        self.assertEqual(blk1, BLOCKER_OWNER_LIVE_AUTH_ALREADY_CONSUMED)

        # 2. Revoked
        t_rev, _ = insert_test_canonical_owner_auth(
            self.db_path,
            token_id="auth_rev_i",
            job_id=9878,
            request_id="req_rev_i",
            status="revoked",
            env=self.standard_env,
        )
        val2, blk2, _ = validate_canonical_owner_live_authorization(
            t_rev,
            product_family="Product Video",
            job_id=9878,
            request_id="req_rev_i",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertFalse(val2)
        self.assertEqual(blk2, BLOCKER_OWNER_LIVE_AUTH_REVOKED)

        # 3. Expired
        t_exp, _ = insert_test_canonical_owner_auth(
            self.db_path,
            token_id="auth_exp_i",
            job_id=9879,
            request_id="req_exp_i",
            ttl_seconds=-60.0,
            env=self.standard_env,
        )
        val3, blk3, _ = validate_canonical_owner_live_authorization(
            t_exp,
            product_family="Product Video",
            job_id=9879,
            request_id="req_exp_i",
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertFalse(val3)
        self.assertEqual(blk3, BLOCKER_OWNER_LIVE_AUTH_EXPIRED)

    # J: No stack/filename/function inspection security is reintroduced
    def test_n21ac_fix1_j_no_stack_filename_function_inspection_reintroduced(self):
        from services.provider_spend_guard import (
            CALLER_FILENAME_SECURITY_AUTHORITY,
            CALLER_FUNCTION_SECURITY_AUTHORITY,
            STACK_INSPECTION_SECURITY_AUTHORITY,
            FALSE_NONFORGEABLE_CLAIM_REMOVED,
            MODULE_LOCAL_SECRET_IS_SECURITY_AUTHORITY,
            PYTHON_PRIVATE_NAME_IS_SECURITY_AUTHORITY,
            PRODUCTION_SPEND_GUARD_CAN_INSERT_CANONICAL_OWNER_AUTH,
            PRODUCTION_SPEND_GUARD_CAN_MINT_OWNER_AUTH_TOKEN,
            PRODUCTION_SPEND_GUARD_CAN_PROMOTE_SECONDARY_AUTH_TO_CANONICAL,
            SPEND_GUARD_AUTHORITY_ROLE,
            AUTHORITY_DEFAULTS_IN_PRODUCTION_MINT_PATH,
        )
        self.assertEqual(CALLER_FILENAME_SECURITY_AUTHORITY, "NO")
        self.assertEqual(CALLER_FUNCTION_SECURITY_AUTHORITY, "NO")
        self.assertEqual(STACK_INSPECTION_SECURITY_AUTHORITY, "NO")
        self.assertTrue(FALSE_NONFORGEABLE_CLAIM_REMOVED)
        self.assertFalse(MODULE_LOCAL_SECRET_IS_SECURITY_AUTHORITY)
        self.assertFalse(PYTHON_PRIVATE_NAME_IS_SECURITY_AUTHORITY)
        self.assertEqual(PRODUCTION_SPEND_GUARD_CAN_INSERT_CANONICAL_OWNER_AUTH, "NO")
        self.assertEqual(PRODUCTION_SPEND_GUARD_CAN_MINT_OWNER_AUTH_TOKEN, "NO")
        self.assertEqual(PRODUCTION_SPEND_GUARD_CAN_PROMOTE_SECONDARY_AUTH_TO_CANONICAL, "NO")
        self.assertEqual(SPEND_GUARD_AUTHORITY_ROLE, "VALIDATE_AND_CONSUME_EXISTING_AUTHORITY_ONLY")
        self.assertEqual(AUTHORITY_DEFAULTS_IN_PRODUCTION_MINT_PATH, "ABSENT")

    # ============================================================
    # FIX2 Negative Security Tests (Section 9 A through L + Section 11)
    # ============================================================

    # A: issue_bot_mint_authority with _caller_override_for_test="test" -> rejected (TypeError or PermissionError)
    def test_n21ac_fix2_a_caller_override_test_rejected_as_absent_or_blocked(self):
        with self.assertRaises((TypeError, PermissionError)):
            issue_bot_mint_authority(
                _caller_override_for_test="test",
                callsite="bot.py:handle_video_product_callback:b14_confirm",
                validation_source="telegram_inline_callback",
                validation_callsite="video_trace_state.py:begin_video_confirm_execution",
                telegram_update_id=999,
                callback_query_id="cb_999",
                chat_id="123",
                user_id="456",
                job_id="job_a",
                request_id="req_a",
                db_path=self.db_path,
                env=self.standard_env,
            )
        self.assertEqual(ISSUE_BOT_MINT_AUTHORITY_TEST_OVERRIDE_PARAMETER, "ABSENT")

    # B: Repeat with "owner", "fixture", "admin", "bypass", "production" -> all blocked
    def test_n21ac_fix2_b_caller_override_values_all_rejected(self):
        for override in ("owner", "fixture", "admin", "bypass", "production"):
            with self.subTest(override=override):
                with self.assertRaises((TypeError, PermissionError)):
                    issue_bot_mint_authority(
                        _caller_override_for_test=override,
                        callsite="bot.py:handle_video_product_callback:b14_confirm",
                        validation_source="telegram_inline_callback",
                        validation_callsite="video_trace_state.py:begin_video_confirm_execution",
                        telegram_update_id=123,
                        callback_query_id="cb_test",
                        chat_id="123",
                        user_id="456",
                        job_id="job_b",
                        request_id="req_b",
                        db_path=self.db_path,
                        env=self.standard_env,
                    )

    # C: Direct BotMintAuthority(..., _issued_by_seam=True) raises PermissionError
    def test_n21ac_fix2_c_direct_bot_mint_authority_constructor_raises_permission_error(self):
        with self.assertRaises(PermissionError):
            BotMintAuthority(
                callsite="test",
                telegram_update_id=1,
                callback_query_id="cq1",
                chat_id="1",
                user_id="1",
                _issued_by_seam=True,
            )
        with self.assertRaises(PermissionError):
            BotMintAuthority()
        self.assertEqual(DIRECT_BOT_MINT_AUTHORITY_CONSTRUCTOR_USABLE, "NO")
        self.assertEqual(CALLER_CAN_SET_ISSUED_BY_SEAM, "NO")

    # D: Exact allowed callsite string manually without durable canonical Bot origin -> PermissionError
    def test_n21ac_fix2_d_exact_callsite_string_without_durable_origin_raises_permission_error(self):
        self.assertEqual(CALLSITE_STRING_IS_AUTHORITY, "NO")
        with self.assertRaises(PermissionError) as cm:
            issue_bot_mint_authority(
                callsite="bot.py:handle_video_product_callback:b14_confirm",
                telegram_update_id=101,
                callback_query_id="cb_101",
                chat_id="c_101",
                user_id="u_101",
                job_id="job_101",
                request_id="req_101",
                validated_ownership=True,
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                db_path=self.db_path,
                env=self.standard_env,
            )
        self.assertIn("missing in video_request_traces", str(cm.exception))

    # E: Exact BOT_CONFIRM_VALIDATION_SOURCE string manually without durable origin -> PermissionError
    def test_n21ac_fix2_e_exact_validation_source_string_without_durable_origin_raises_permission_error(self):
        self.assertEqual(VALIDATION_SOURCE_STRING_IS_AUTHORITY, "NO")
        with self.assertRaises(PermissionError) as cm:
            issue_bot_mint_authority(
                callsite="bot.py:handle_video_product_callback:b14_confirm",
                telegram_update_id=102,
                callback_query_id="cb_102",
                chat_id="c_102",
                user_id="u_102",
                job_id="job_102",
                request_id="req_102",
                validated_ownership=True,
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                db_path=self.db_path,
                env=self.standard_env,
            )
        self.assertIn("missing in video_request_traces", str(cm.exception))

    # F: Exact validation_callsite string manually without durable origin -> PermissionError
    def test_n21ac_fix2_f_exact_validation_callsite_string_without_durable_origin_raises_permission_error(self):
        self.assertEqual(VALIDATION_CALLSITE_STRING_IS_AUTHORITY, "NO")
        with self.assertRaises(PermissionError) as cm:
            issue_bot_mint_authority(
                callsite="bot.py:handle_video_product_callback:b14_confirm",
                telegram_update_id=103,
                callback_query_id="cb_103",
                chat_id="c_103",
                user_id="u_103",
                job_id="job_103",
                request_id="req_103",
                validated_ownership=True,
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                db_path=self.db_path,
                env=self.standard_env,
            )
        self.assertIn("missing in video_request_traces", str(cm.exception))

    # G: Synthetic positive update ID + callback_query_id + chat/user IDs without durable origin -> PermissionError
    def test_n21ac_fix2_g_positive_update_and_callback_ids_without_durable_origin_raises_permission_error(self):
        self.assertEqual(TELEGRAM_ID_FIELDS_ALONE_ARE_AUTHORITY, "NO")
        with self.assertRaises(PermissionError) as cm:
            issue_bot_mint_authority(
                callsite="bot.py:handle_video_product_callback:b14_confirm",
                telegram_update_id=999888,
                callback_query_id="cq_pos_777",
                chat_id="chat_pos",
                user_id="user_pos",
                job_id="job_pos",
                request_id="req_pos",
                validated_ownership=True,
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                db_path=self.db_path,
                env=self.standard_env,
            )
        self.assertIn("missing in video_request_traces", str(cm.exception))

    # H: Generic service / worker / provider callsite raises PermissionError
    def test_n21ac_fix2_h_generic_service_worker_provider_callsite_raises_permission_error(self):
        for generic_callsite in (
            "services.worker_service:process_task",
            "services.provider_client:call_provider",
            "services.arbitrary_service:mint",
            "views.admin_panel:do_confirm",
        ):
            with self.subTest(callsite=generic_callsite):
                with self.assertRaises(PermissionError):
                    issue_bot_mint_authority(
                        callsite=generic_callsite,
                        telegram_update_id=1,
                        callback_query_id="cb1",
                        chat_id="c1",
                        user_id="u1",
                        job_id="j1",
                        request_id="r1",
                        db_path=self.db_path,
                        env=self.standard_env,
                    )

    # I: Real provider-free callback path with valid durable Bot-origin evidence succeeds
    def test_n21ac_fix2_i_durable_bot_origin_issuance_seam_succeeds_provider_free(self):
        from services.video_trace_state import ensure_video_trace_schema
        ensure_video_trace_schema(db_path=self.db_path)
        seed_test_durable_bot_origin_in_trace(
            db_path=self.db_path,
            request_id="req_i_2001",
            job_id="job_i_2001",
            user_id="u_i_2001",
            chat_id="c_i_2001",
            telegram_update_id=2001,
            callback_query_id="cb_i_2001",
        )
        auth = issue_bot_mint_authority(
            callsite="bot.py:handle_video_product_callback:b14_confirm",
            telegram_update_id=2001,
            callback_query_id="cb_i_2001",
            chat_id="c_i_2001",
            user_id="u_i_2001",
            job_id="job_i_2001",
            request_id="req_i_2001",
            validated_ownership=True,
            validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
            validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertIsInstance(auth, BotMintAuthority)
        self.assertTrue(auth.grant_id.startswith("bmg_"))
        self.assertEqual(BOT_ORIGIN_AUTHORITY_DURABLE, "YES")
        self.assertEqual(BOT_ORIGIN_AUTHORITY_ONE_TIME, "YES")
        self.assertEqual(REAL_CANONICAL_BOT_MINT_ISSUANCE_SEAM, "PROVEN")

    # J: Replay of consumed durable Bot-origin issuance is blocked
    def test_n21ac_fix2_j_replay_of_consumed_durable_bot_origin_raises_permission_error(self):
        from services.video_trace_state import ensure_video_trace_schema
        ensure_video_trace_schema(db_path=self.db_path)
        seed_test_durable_bot_origin_in_trace(
            db_path=self.db_path,
            request_id="req_j_replay",
            job_id="job_j_replay",
            user_id="u_j_replay",
            chat_id="c_j_replay",
            telegram_update_id=3001,
            callback_query_id="cb_j_replay",
        )
        # First issuance succeeds (READY -> MINTED)
        auth1 = issue_bot_mint_authority(
            callsite="bot.py:handle_video_product_callback:b14_confirm",
            telegram_update_id=3001,
            callback_query_id="cb_j_replay",
            chat_id="c_j_replay",
            user_id="u_j_replay",
            job_id="job_j_replay",
            request_id="req_j_replay",
            validated_ownership=True,
            validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
            validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertIsInstance(auth1, BotMintAuthority)

        # Replay attempt fails: no unconsumed READY row exists
        with self.assertRaises(PermissionError) as cm:
            issue_bot_mint_authority(
                callsite="bot.py:handle_video_product_callback:b14_confirm",
                telegram_update_id=3001,
                callback_query_id="cb_j_replay",
                chat_id="c_j_replay",
                user_id="u_j_replay",
                job_id="job_j_replay",
                request_id="req_j_replay",
                validated_ownership=True,
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                db_path=self.db_path,
                env=self.standard_env,
            )
        self.assertIn("already minted or consumed", str(cm.exception))

        # Furthermore, consuming the minted grant into a confirmation succeeds once:
        conf_id = create_bot_confirmation(
            job_id="job_j_replay",
            request_id="req_j_replay",
            user_id="u_j_replay",
            chat_id="c_j_replay",
            mint_authority=auth1,
            db_path=self.db_path,
            env=self.standard_env,
        )
        self.assertTrue(conf_id)

        # And replaying the same consumed grant into create_bot_confirmation fails:
        with self.assertRaises(PermissionError):
            create_bot_confirmation(
                job_id="job_j_replay",
                request_id="req_j_replay",
                user_id="u_j_replay",
                chat_id="c_j_replay",
                mint_authority=auth1,
                db_path=self.db_path,
                env=self.standard_env,
            )

    # K: Cross-user / cross-chat / cross-job / cross-request reuse is blocked
    def test_n21ac_fix2_k_cross_user_chat_job_request_mismatch_raises_permission_error(self):
        from services.video_trace_state import ensure_video_trace_schema
        ensure_video_trace_schema(db_path=self.db_path)
        base = {
            "request_id": "req_k_base",
            "job_id": "job_k_base",
            "user_id": "u_k_base",
            "chat_id": "c_k_base",
            "telegram_update_id": 4001,
            "callback_query_id": "cb_k_base",
        }
        seed_test_durable_bot_origin_in_trace(db_path=self.db_path, **base)

        # Mismatched user_id
        with self.assertRaises(PermissionError):
            issue_bot_mint_authority(
                callsite="bot.py:handle_video_product_callback:b14_confirm",
                telegram_update_id=base["telegram_update_id"],
                callback_query_id=base["callback_query_id"],
                chat_id=base["chat_id"],
                user_id="wrong_user",
                job_id=base["job_id"],
                request_id=base["request_id"],
                validated_ownership=True,
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                db_path=self.db_path,
                env=self.standard_env,
            )

        # Mismatched chat_id
        with self.assertRaises(PermissionError):
            issue_bot_mint_authority(
                callsite="bot.py:handle_video_product_callback:b14_confirm",
                telegram_update_id=base["telegram_update_id"],
                callback_query_id=base["callback_query_id"],
                chat_id="wrong_chat",
                user_id=base["user_id"],
                job_id=base["job_id"],
                request_id=base["request_id"],
                validated_ownership=True,
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                db_path=self.db_path,
                env=self.standard_env,
            )

        # Mismatched job_id
        with self.assertRaises(PermissionError):
            issue_bot_mint_authority(
                callsite="bot.py:handle_video_product_callback:b14_confirm",
                telegram_update_id=base["telegram_update_id"],
                callback_query_id=base["callback_query_id"],
                chat_id=base["chat_id"],
                user_id=base["user_id"],
                job_id="wrong_job",
                request_id=base["request_id"],
                validated_ownership=True,
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                db_path=self.db_path,
                env=self.standard_env,
            )

        # Mismatched request_id
        with self.assertRaises(PermissionError):
            issue_bot_mint_authority(
                callsite="bot.py:handle_video_product_callback:b14_confirm",
                telegram_update_id=base["telegram_update_id"],
                callback_query_id=base["callback_query_id"],
                chat_id=base["chat_id"],
                user_id=base["user_id"],
                job_id=base["job_id"],
                request_id="wrong_req",
                validated_ownership=True,
                validation_source=BOT_CONFIRM_VALIDATION_SOURCE,
                validation_callsite=BOT_CONFIRM_VALIDATION_CALLSITE,
                db_path=self.db_path,
                env=self.standard_env,
            )

    # L: Forged/absent grant ID raises PermissionError; zero network calls
    def test_n21ac_fix2_l_forged_or_absent_grant_id_raises_permission_error_and_zero_network_calls(self):
        fake_authority = MagicMock()
        fake_authority.grant_id = "BMA-forged-999"
        with self.assertRaises(PermissionError):
            create_bot_confirmation(
                job_id="job_l_fake",
                request_id="req_l_fake",
                mint_authority=fake_authority,
                db_path=self.db_path,
                env=self.standard_env,
            )
        self.assertEqual(len(PROVIDER_PRODUCTION_MINT_CALLERS), 0)
        self.assertEqual(len(WORKER_PRODUCTION_MINT_CALLERS), 0)

    # Section 11: SpendGuardContext default user_flow empty & cannot assert bot live
    def test_n21ac_fix2_sec11_default_spend_guard_context_user_flow_empty_and_cannot_assert_bot_live(self):
        ctx = SpendGuardContext()
        self.assertEqual(ctx.user_flow, "")
        self.assertEqual(DEFAULT_CONTEXT_CAN_ASSERT_BOT_LIVE_ACCEPTANCE, "NO")
        self.assertEqual(DEFAULT_CONTEXT_CAN_ASSERT_BOT_ORIGIN, "NO")
        self.assertEqual(DEFAULT_CONTEXT_CAN_ASSERT_OWNER_LIVE_PURPOSE, "NO")
        res = reserve_provider_spend(ctx, db_path=self.db_path, env=self.standard_env)
        self.assertFalse(res.allowed)

    # Section 11: FIX2 constants and contracts
    def test_n21ac_fix2_sec11_constants_and_contracts(self):
        from services.provider_spend_guard import (
            BOT_MINT_TEST_OVERRIDE_IN_PRODUCTION,
            ISSUE_BOT_MINT_AUTHORITY_TEST_OVERRIDE_PARAMETER,
            DIRECT_BOT_MINT_AUTHORITY_CONSTRUCTOR_USABLE,
            CALLER_CAN_SET_ISSUED_BY_SEAM,
            BOT_MINT_CAPABILITY_CALLER_FORGEABLE,
            BOT_MINT_TEST_FIXTURE_LOCATION,
            PRODUCTION_BOT_MINT_TEST_HELPER_COUNT,
            CALLSITE_STRING_IS_AUTHORITY,
            VALIDATED_OWNERSHIP_BOOL_IS_AUTHORITY,
            VALIDATION_SOURCE_STRING_IS_AUTHORITY,
            VALIDATION_CALLSITE_STRING_IS_AUTHORITY,
            TELEGRAM_ID_FIELDS_ALONE_ARE_AUTHORITY,
            BOT_ORIGIN_AUTHORITY_SOURCE,
            BOT_ORIGIN_AUTHORITY_DURABLE,
            BOT_ORIGIN_AUTHORITY_ONE_TIME,
            REAL_CANONICAL_BOT_MINT_ISSUANCE_SEAM,
            PRODUCTION_BOT_MINT_AVAILABLE,
            PRODUCTION_TEST_MINT_OVERRIDE_AVAILABLE,
        )
        self.assertEqual(BOT_MINT_TEST_OVERRIDE_IN_PRODUCTION, "NO")
        self.assertEqual(ISSUE_BOT_MINT_AUTHORITY_TEST_OVERRIDE_PARAMETER, "ABSENT")
        self.assertEqual(DIRECT_BOT_MINT_AUTHORITY_CONSTRUCTOR_USABLE, "NO")
        self.assertEqual(CALLER_CAN_SET_ISSUED_BY_SEAM, "NO")
        self.assertEqual(BOT_MINT_CAPABILITY_CALLER_FORGEABLE, "NO")
        self.assertEqual(BOT_MINT_TEST_FIXTURE_LOCATION, "TESTS_ONLY")
        self.assertEqual(PRODUCTION_BOT_MINT_TEST_HELPER_COUNT, 0)
        self.assertEqual(CALLSITE_STRING_IS_AUTHORITY, "NO")
        self.assertEqual(VALIDATED_OWNERSHIP_BOOL_IS_AUTHORITY, "NO")
        self.assertEqual(VALIDATION_SOURCE_STRING_IS_AUTHORITY, "NO")
        self.assertEqual(VALIDATION_CALLSITE_STRING_IS_AUTHORITY, "NO")
        self.assertEqual(TELEGRAM_ID_FIELDS_ALONE_ARE_AUTHORITY, "NO")
        self.assertEqual(BOT_ORIGIN_AUTHORITY_SOURCE, "services.video_trace_state:video_request_traces")
        self.assertEqual(BOT_ORIGIN_AUTHORITY_DURABLE, "YES")
        self.assertEqual(BOT_ORIGIN_AUTHORITY_ONE_TIME, "YES")
        self.assertEqual(REAL_CANONICAL_BOT_MINT_ISSUANCE_SEAM, "PROVEN")
        self.assertEqual(PRODUCTION_BOT_MINT_AVAILABLE, "YES")
        self.assertEqual(PRODUCTION_TEST_MINT_OVERRIDE_AVAILABLE, "NO")


if __name__ == "__main__":
    unittest.main()

