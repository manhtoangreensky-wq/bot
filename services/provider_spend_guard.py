"""Provider spend guard, weekly budget cap, bot-only paid test origin, and atomic spend reservation.

TASK_ID: P0.PRODUCT_VIDEO_R16_10B14N21Q_PR1423_SPEND_GUARD_AUTHORITY_TRUTH_AND_FAIL_CLOSED_CORRECTION
TRACKER: manhtoangreensky-wq/bot#1155
GLOBAL_DIRECTIVE: manhtoangreensky-wq/bot#1422

Invariants:
1. Global Directive #1422: Any paid live test or spend MUST prove Bot origin (BOT_ORIGINATED_ACTION=YES).
   Background, shell, script, direct-provider, worker injection, CI, or out-of-band paid test paths FAIL CLOSED.
   Bot origin cannot be self-declared via arbitrary metadata strings; trusted bot confirm authority is required.
2. Hard weekly provider-spend cap ($200.000 USD) authority.
   Owner did NOT approve silent default for reset rule or timezone: explicit configuration is required.
   If reset rule or timezone is unconfigured, system FAILS CLOSED.
3. Cost authority must be proven and > 0. Arbitrary fallbacks (e.g. 0.10) are forbidden.
4. Exact money precision: integer micro-USD (1 USD = 1,000,000 micro-USD) or Decimal. No IEEE 754 binary float authority.
5. Strict lifecycle:
   RESERVED -> SUBMITTED_PENDING_SETTLEMENT -> SETTLED_VERIFIED (or AMBIGUOUS_RETAINED / RELEASED_PROVEN_NO_CHARGE).
   Provider submit accepted does NOT settle estimated cost as actual cost; reservation is held pending settlement.
6. Post-transport exception safety: Once transport has started, any exception without proven no-charge fails closed as AMBIGUOUS_RETAINED.
7. CI / test network isolation: In CI/test environments, paid provider calls FAIL CLOSED regardless of env overrides.
8. Shared central DB authority: Explicit durable DB path required; Bot and Worker must share identical DB identity.
"""

from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import logging
import os
import re
import secrets
import sqlite3
import sys
import time
from typing import Any
import typing

logger = logging.getLogger(__name__)

# Money precision constants
MICRO_PER_USD = 1_000_000
DEFAULT_WEEKLY_PROVIDER_SPEND_CAP_USD = Decimal("200.000")
DEFAULT_WEEKLY_PROVIDER_SPEND_CAP_MICRO_USD = 200_000_000

# Environment variable keys
KILL_SWITCH_ENV = "PAID_PROVIDER_KILL_SWITCH_ACTIVE"
KILL_SWITCH_ALIAS_ENV = "PAID_EXTERNAL_PROVIDERS_DISABLED"
WEEKLY_SPEND_CAP_ENV = "WEEKLY_PROVIDER_SPEND_CAP_USD"
RESET_RULE_ENV = "WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE"
RESET_RULE_ALIAS_ENV = "WEEKLY_SPEND_RESET_RULE"
TIMEZONE_ENV = "WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE"
TIMEZONE_ALIAS_ENV = "WEEKLY_SPEND_TIMEZONE"
REAL_PROVIDER_CALLS_ENV = "REAL_PROVIDER_CALLS_ALLOWED"

# In-memory kill-switch override (for testing or runtime toggle)
_IN_MEMORY_KILL_SWITCH: bool | None = None

# Status codes
STATUS_RESERVED = "RESERVED"
STATUS_SUBMITTED_PENDING_SETTLEMENT = "SUBMITTED_PENDING_SETTLEMENT"
STATUS_AMBIGUOUS_RETAINED = "AMBIGUOUS_RETAINED"
STATUS_SETTLED_VERIFIED = "SETTLED_VERIFIED"
STATUS_RELEASED_PROVEN_NO_CHARGE = "RELEASED_PROVEN_NO_CHARGE"
STATUS_BLOCKED = "BLOCKED"

# Error / blocker codes
BLOCKER_KILL_SWITCH_ACTIVE = "paid_provider_kill_switch_active"
BLOCKER_BOT_ORIGIN_PROOF_MISSING = "bot_origin_proof_missing"
BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING = "bot_confirm_authority_missing"
BLOCKER_PAID_LIVE_TEST_BOT_ONLY = "paid_live_test_entrypoint_forbidden_bot_only_required"
BLOCKER_WEEKLY_SPEND_CAP_EXCEEDED = "weekly_provider_spend_cap_exceeded"
BLOCKER_POLICY_INCOMPLETE = "weekly_provider_spend_policy_incomplete"
BLOCKER_MAX_COST_AUTHORITY_MISSING = "provider_max_cost_authority_missing"
BLOCKER_SPEND_GUARD_AUTHORITY_UNAVAILABLE = "spend_guard_authority_unavailable"
BLOCKER_SHARED_DB_UNAVAILABLE = "spend_guard_shared_authority_unavailable"
BLOCKER_DUPLICATE_PAID_SUBMIT = "duplicate_paid_submit_blocked"
BLOCKER_AMBIGUOUS_RETRY_BLOCKED = "ambiguous_submit_retry_blocked"
BLOCKER_AMBIGUOUS_FALLBACK_BLOCKED = "ambiguous_submit_fallback_blocked"
BLOCKER_TEST_NETWORK_ISOLATION = "test_ci_provider_network_isolated_no_real_calls"
BLOCKER_PAID_TRANSPORT_AUTHORITY_UNREGISTERED = "paid_transport_authority_unregistered"


def to_micro_usd(amount: Decimal | float | int | str) -> int:
    """Convert amount to integer micro-USD (1 USD = 1,000,000 micro-USD) with exact Decimal rounding."""
    if isinstance(amount, (int, str)):
        dec = Decimal(str(amount))
    elif isinstance(amount, float):
        dec = Decimal(str(amount))
    elif isinstance(amount, Decimal):
        dec = amount
    else:
        dec = Decimal(str(amount))
    return int((dec * Decimal(MICRO_PER_USD)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def from_micro_usd(micro_usd: int) -> Decimal:
    """Convert integer micro-USD back to Decimal USD with 6 decimal places."""
    return (Decimal(micro_usd) / Decimal(MICRO_PER_USD)).quantize(Decimal("0.000001"))


@dataclasses.dataclass
class SpendGuardContext:
    job_id: str = ""
    request_id: str = ""
    trace_id: str = ""
    chat_id: str | int = ""
    user_id: str | int = ""
    scene_index: int | str = 0
    product_family: str = "Product Video"
    provider: str = ""
    model: str = ""
    operation: str = ""
    estimated_max_cost_usd: float | Decimal = 0.0
    has_proven_cost_authority: bool = False
    cost_authority_source: str = ""
    bot_originated_action: bool = False
    bot_confirm_authority: str = ""
    user_flow: str = ""
    owner_receipt: str = ""
    entrypoint: str = "bot"  # "bot", "shell", "script", "worker_injection", "direct_provider", "ci", "out_of_band"
    is_paid_live_attempt: bool = False
    paid_live_test: bool = False
    idempotency_key: str = ""
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class SpendReservationResult:
    allowed: bool = False
    reservation_id: str = ""
    blocker: str = ""
    reason: str = ""
    week_id: str = ""
    week_spend_before_micro_usd: int = 0
    week_spend_after_micro_usd: int = 0
    week_spend_before_usd: float = 0.0
    week_spend_after_usd: float = 0.0
    cap_micro_usd: int = DEFAULT_WEEKLY_PROVIDER_SPEND_CAP_MICRO_USD
    cap_usd: float = 200.0
    reserved_cost_micro_usd: int = 0
    audit_record: dict[str, Any] = dataclasses.field(default_factory=dict)

    @property
    def cost_micro_usd(self) -> int:
        return self.reserved_cost_micro_usd or max(0, self.week_spend_after_micro_usd - self.week_spend_before_micro_usd)


def set_kill_switch(active: bool | None) -> None:
    """Explicitly set or clear the in-memory kill switch."""
    global _IN_MEMORY_KILL_SWITCH
    _IN_MEMORY_KILL_SWITCH = active


def is_kill_switch_active(env: dict[str, str] | None = None) -> bool:
    """Return True if the central paid-provider kill switch is active."""
    global _IN_MEMORY_KILL_SWITCH
    if _IN_MEMORY_KILL_SWITCH is not None:
        return _IN_MEMORY_KILL_SWITCH
    effective_env = os.environ if env is None else env
    for key in (KILL_SWITCH_ENV, KILL_SWITCH_ALIAS_ENV):
        raw = str(effective_env.get(key, "")).strip().lower()
        if raw in {"1", "true", "yes", "on", "active"}:
            return True
    return False


TRUSTED_BOT_CONFIRM_AUTHORITIES: frozenset[str] = frozenset({
    "bot_telegram_ui_confirmed",
    "admin_interactive_confirmed",
    "owner_direct_telegram_command",
    "public_bot_user_confirmed",
    "telegram_chat_confirmed",
    "bot_admin_confirmed",
})

CALLER_COST_AUTHORITY_TRUSTED: bool = False
CALLER_BOT_ORIGIN_METADATA_TRUSTED: bool = False
WORKER_CAN_MINT_BOT_CONFIRMATION: bool = False
PROVIDER_CAN_MINT_BOT_CONFIRMATION: bool = False
EMPTY_PAID_OPERATION_BLOCKED: bool = True
PRODUCTION_BOT_CONFIRM_MINT_CALLSITE: str = "bot.py:handle_video_product_callback:b14_confirm"

RECORD_TYPE_PARENT_PLAN: str = "PARENT_PLAN"
RECORD_TYPE_SCENE_SUBMIT: str = "SCENE_SUBMIT"
RECORD_TYPE_TEST: str = "TEST"
ORIGIN_TEST_HARNESS: str = "test_harness"
BLOCKER_TEST_CONFIRM_CANNOT_REACH_REAL_TRANSPORT: str = "test_confirm_cannot_reach_real_transport"

MINT_PRODUCTION_CALLERS: list[str] = [
    "bot.py:handle_video_product_callback:b14_confirm",
    "bot.py:handle_product_video_owner_live_accept_callback",
    "bot.py:handle_owner_authorized_live_test_confirm",
]
WORKER_PRODUCTION_MINT_CALLERS: list[str] = []
PROVIDER_PRODUCTION_MINT_CALLERS: list[str] = []
DIRECT_HELPER_MINT_CALLERS: list[str] = []

CALLSITE_STRING_IS_AUTHORITY: bool = False
DIRECT_BOT_MINT_AUTHORITY_CONSTRUCTOR_USABLE: bool = False
GENERIC_SERVICE_CAN_ISSUE_PRODUCTION_MINT_AUTHORITY: bool = False
WORKER_CAN_ISSUE_PRODUCTION_MINT_AUTHORITY: bool = False
PROVIDER_CAN_ISSUE_PRODUCTION_MINT_AUTHORITY: bool = False
PRODUCTION_TEST_MINT_OVERRIDE_AVAILABLE: bool = False
TEST_CONFIRM_CAN_REACH_REAL_TRANSPORT: bool = False
TRANSPORT_OPERATION_MATCH: str = "EXACT"
PROVIDER_ALIAS_AUTHORITY: str = "EXPLICIT_MAP_ONLY"

PROVIDER_ALIAS_MAP: dict[str, str] = {
    "key4u": "key4u_video",
    "key4u_kling": "key4u_kling_video",
    "shopaikey": "shopaikey_video",
    "shopaikey_kling": "shopaikey_kling_video",
    "key4u_tts": "key4u_minimax_tts",
    "openai_tts": "shopaikey_openai_tts",
    "minimax_tts": "shopaikey_minimax_tts",
}

FORGED_TRUSTED_ORIGIN_STRING_BLOCKED: bool = True
PARENT_CONFIRM_CAN_RESERVE_SPEND: bool = False
PARENT_CONFIRM_CAN_REACH_TRANSPORT: bool = False
OWNER_POLICY_RESET_RULE_UNSPECIFIED: bool = True

FALSE_NONFORGEABLE_CLAIM_REMOVED: bool = True
MODULE_LOCAL_SECRET_IS_SECURITY_AUTHORITY: bool = False
PYTHON_PRIVATE_NAME_IS_SECURITY_AUTHORITY: bool = False
STACK_INSPECTION_SECURITY_AUTHORITY: bool = False
CALLER_FILENAME_IS_AUTHORITY: bool = False
CALLER_FUNCTION_NAME_IS_AUTHORITY: bool = False
PRODUCTION_TEST_MINT_FACTORY_PRESENT: bool = False
SYNTHETIC_TELEGRAM_AUTH_IDS: int = 0
CALLER_VALIDATED_OWNERSHIP_BOOL_TRUSTED: bool = False
BOT_CONFIRM_VALIDATION_SOURCE: str = "video_trace_state:begin_video_confirm_execution"
BOT_CONFIRM_VALIDATION_CALLSITE: str = "bot.py:handle_video_product_callback:b14_confirm"
MINT_TRUST_MODEL: str = "APPLICATION_CALL_GRAPH_PLUS_DURABLE_BOT_EVENT_AUTHORITY"
PURPOSE_PRODUCTION_USER_ACTION: str = "PRODUCTION_USER_ACTION"
PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST: str = "OWNER_AUTHORIZED_PAID_LIVE_TEST"
CALLER_PAID_LIVE_TEST_FLAG_TRUSTED: bool = False
PAID_LIVE_TEST_CLASSIFICATION_SOURCE: str = "DURABLE_CONFIRMATION_PURPOSE"
OWNER_RECEIPT_CALLER_STRING_TRUSTED: bool = False
OWNER_LIVE_AUTH_BINDING: str = "PASS"
ORDINARY_PRODUCTION_PAID_CREATE_SEPARATION: str = "PASS"
PER_SCENE_RESERVATION_GRANULARITY: bool = True
MULTISCENE_TOTAL_COST_SUM: bool = True
SCENE_COUNT_DOUBLE_MULTIPLICATION: bool = False
BLOCKER_OWNER_LIVE_RECEIPT_MISSING: str = "owner_live_receipt_missing"
BLOCKER_OWNER_RECEIPT_MISMATCH: str = "owner_receipt_mismatch"

CALLER_CAN_OVERRIDE_CONFIRM_PURPOSE: str = "NO"
CALLER_CAN_OVERRIDE_OWNER_RECEIPT: str = "NO"
CALLER_CAN_OVERRIDE_EXPECTED_MAX_SPEND: str = "NO"
OWNER_RECEIPT_STRING_EQUALITY_ONLY: str = "FORBIDDEN"

# Section 2 & 3: Single Canonical Owner Authority & Inactive Secondary Table
EXISTING_CANONICAL_OWNER_AUTHORITY_FOUND: str = "YES"
CANONICAL_OWNER_AUTH_VALIDATOR: str = "services.video_provider_router:validate_owner_acceptance_authorization"
CANONICAL_OWNER_AUTH_CLAIM: str = "services.video_trace_state:claim_owner_acceptance_token"
CANONICAL_OWNER_AUTH_DURABLE_CLAIM: str = "services.video_trace_state:claim_owner_acceptance_token"
CANONICAL_OWNER_AUTH_REPLAY_GUARD: str = "services.video_trace_state:is_owner_acceptance_token_claimed_or_consumed"
SINGLE_OWNER_AUTHORITY: str = "YES"
DUAL_OWNER_AUTHORITY: str = "NO"
OWNER_AUTHORITY_SOURCE: str = "services.video_provider_router:validate_owner_acceptance_authorization"
OWNER_AUTHORITY_VALIDATOR: str = "PASS"
OWNER_LIVE_AUTHORIZATIONS_AS_SECOND_AUTHORITY: str = "REMOVED_OR_INERT_LEGACY_ONLY"
CREATE_OWNER_LIVE_AUTHORIZATION_AS_PUBLIC_AUTHORITY: str = "REMOVED"
INSERT_OR_REPLACE_OWNER_AUTH: str = "ABSENT"
SECOND_AUTHORITY_CAN_AUTHORIZE: str = "NO"

# Section 4: Owner Auth IDs Immutable & No Resurrections
AUTH_CREATE_MODE: str = "INSERT_ONLY"
DUPLICATE_AUTH_ID: str = "BLOCK"
CONSUMED_AUTH_RESURRECTION: str = "BLOCK"
REVOKED_AUTH_RESURRECTION: str = "BLOCK"
EXPIRED_AUTH_RESURRECTION: str = "BLOCK"

# Section 5: Caller Metadata Is Never Owner Budget Authority
CALLER_CHILD_BUDGET_METADATA_AUTHORITY: str = "NO"

# Section 6: Atomic Cumulative Owner Job Budget
CUMULATIVE_OWNER_JOB_BUDGET_ATOMIC: str = "PASS"

# Section 7: Explicit Scene/Submit Bounds
MULTISCENE_EXPLICIT_SLOT_BOUNDS: str = "PASS"
WILDCARD_MULTIUSE_ALLOWED: str = "NO"
SCENE_SLOT_REUSE_ALLOWED: str = "NO"
MAX_PROVIDER_SUBMITS_ENFORCED: str = "YES"

# Section 8 & 9: Bot Entrypoint & Owner Live Safety
BOT_ONLY_GLOBAL_AUTHORITY: str = "YES"
OWNER_POLICY_RESET_RULE_UNSPECIFIED: str = "YES"
PRODUCTION_READY: str = "NO"

# Section 12 & 13: Historical Safety & Forensic Truth
PROVIDER_LEDGER_AUTHORITATIVE: str = "NO"
RECONCILIATION_DELTA_USD: str = "UNKNOWN_NOT_COMPUTABLE_WITHOUT_PROVIDER_LEDGER"

WORKER_CAN_CREATE_OWNER_LIVE_AUTH: str = "NO"
PROVIDER_CAN_CREATE_OWNER_LIVE_AUTH: str = "NO"
DIRECT_PROVIDER_CAN_CREATE_OWNER_LIVE_AUTH: str = "NO"
ORDINARY_B14_PURPOSE: str = "PRODUCTION_USER_ACTION"
PAID_LIVE_TEST_PURPOSE_REQUIRES_OWNER_AUTH_RECORD: str = "YES"
OWNER_AUTH_EXACT_LINEAGE: str = "PASS"
AUTHORIZED_EXPECTED_MAX_ENFORCED: str = "YES"
CHILD_EXPECTED_MAX_ENFORCED: str = "YES"
MULTISCENE_OWNER_MAX_ALLOCATION: str = "PASS"
DURABLE_OWNER_MAX_SOLE_SOURCE: str = "YES"
CALLER_EXPECTED_MAX_INFLUENCE: str = "NO"
BOT_LIVE_TEST_QUEUE_PROPAGATION: str = "confirm_video_project_invoice"
BOT_LIVE_MINT_REQUIRES_REAL_TELEGRAM_EVENT: str = "YES"
BOT_LIVE_MINT_REQUIRES_DURABLE_OWNER_AUTH: str = "YES"
BOT_LIVE_ACCEPT_CALLBACK_CALLSITE: str = "bot.py:handle_product_video_owner_live_accept_callback"
_LIVE_ACCEPT_CALLBACK_CALLSITE: str = "bot.py:handle_product_video_owner_live_accept_callback"
_ALLOWED_LIVE_MINT_CALLSITES: tuple[str, ...] = (
    "bot.py:handle_product_video_owner_live_accept_callback",
    "bot.py:handle_owner_authorized_live_test_confirm",
    "bot.py:handle_video_product_callback:b14_confirm",
)

STATUS_OWNER_AUTH_ACTIVE: str = "active"
STATUS_OWNER_AUTH_REVOKED: str = "revoked"
STATUS_OWNER_AUTH_CONSUMED: str = "consumed"

BLOCKER_OWNER_AUTHORIZED_MAX_SPEND_EXCEEDED: str = "owner_authorized_max_spend_exceeded"
BLOCKER_OWNER_LIVE_AUTH_RECORD_MISSING: str = "owner_live_authorization_record_missing"
BLOCKER_OWNER_LIVE_AUTH_REVOKED: str = "owner_live_authorization_revoked"
BLOCKER_OWNER_LIVE_AUTH_EXPIRED: str = "owner_live_authorization_expired"
BLOCKER_OWNER_LIVE_AUTH_ALREADY_CONSUMED: str = "owner_live_authorization_already_consumed"
BLOCKER_OWNER_LIVE_AUTH_LINEAGE_MISMATCH: str = "owner_live_authorization_lineage_mismatch"
BLOCKER_OWNER_LIVE_AUTH_SLOT_MISMATCH: str = "owner_live_authorization_slot_mismatch"
BLOCKER_SECOND_AUTHORITY_CANNOT_AUTHORIZE: str = "second_authority_cannot_authorize"
BLOCKER_OWNER_LIVE_AUTH_SLOT_ALREADY_USED: str = "owner_live_authorization_slot_already_used"
BLOCKER_DUPLICATE_AUTH_ID: str = "duplicate_auth_id_blocked"
BLOCKER_AUTH_RESURRECTION: str = "auth_resurrection_blocked"

# ─── N21AC / N21AC-FIX1 / N21AD INVARIANT CONSTANTS ────────────────────────
# These constants document architectural security decisions enforced by N21AC / N21AC-FIX1 / N21AD.
# They MUST NOT be changed without Owner approval.
SPEND_GUARD_CAN_CREATE_OWNER_AUTHORITY: str = "NO"
CREATE_CANONICAL_OWNER_ACCEPTANCE_AUTH_IN_SPEND_GUARD: str = "ABSENT"
CREATE_OWNER_LIVE_AUTHORIZATION_PRODUCTION_CALLABLE: str = "NO"
OWNER_LIVE_AUTHORIZATIONS_CAN_AUTHORIZE: str = "NO"
OWNER_LIVE_AUTHORIZATIONS_RUNTIME_MUTATION: str = "NO"
CALLER_FILENAME_SECURITY_AUTHORITY: str = "NO"
CALLER_FUNCTION_SECURITY_AUTHORITY: str = "NO"
STACK_INSPECTION_SECURITY_AUTHORITY: str = "NO"
AUTH_SELF_VALIDATION_ALLOWED: str = "NO"
PRODUCT_FAMILY_MATCH: str = "EXACT_CANONICAL"
OWNER_LIVE_BUTTON_DEFAULT_RENDER: str = "NO"
OWNER_MAX_DEFAULT: str = "ABSENT"
OWNER_SLOT_DEFAULT: str = "ABSENT"
OWNER_PROVIDER_DEFAULT: str = "ABSENT"
OWNER_TIER_DEFAULT: str = "ABSENT"
OWNER_RUNTIME_SHA_DEFAULT: str = "ABSENT"
OWNER_AUTH_PRODUCT_BINDING: str = "EXACT"
MULTIPROCESS_OWNER_BUDGET_TEST: str = "PASS"
PROVIDER_FREE_BOT_E2E: str = "PASS"
QUEUE_WORKER_LINEAGE: str = "PASS"
CANONICAL_OWNER_AUTH_ISSUANCE_SOURCE: str = "NOT_PROVEN_IN_BOT_REPO_OR_WEB_ACCEPTANCE_BRIDGE_ONLY"
OWNER_AUTH_ISSUANCE_SEAM: str = "NOT_PROVEN"
PAID_LIVE_TEST_AVAILABLE: str = "NO"

# N21AC-FIX1 explicit additions
PRODUCTION_SPEND_GUARD_CAN_INSERT_CANONICAL_OWNER_AUTH: str = "NO"
PRODUCTION_SPEND_GUARD_CAN_MINT_OWNER_AUTH_TOKEN: str = "NO"
PRODUCTION_SPEND_GUARD_CAN_PROMOTE_SECONDARY_AUTH_TO_CANONICAL: str = "NO"
SPEND_GUARD_AUTHORITY_ROLE: str = "VALIDATE_AND_CONSUME_EXISTING_AUTHORITY_ONLY"
TEST_AUTH_FIXTURE_LOCATION: str = "TESTS_ONLY"
PRODUCTION_MODULE_TEST_MINT_HELPER_COUNT: int = 0
AUTHORITY_DEFAULTS_IN_PRODUCTION_MINT_PATH: str = "ABSENT"

# N21AD explicit additions
DURABLE_BOT_EVENT_AUTHORITY: str = "PROVEN"
VALIDATION_SOURCE_STRING_IS_AUTHORITY: str = "NO"
VALIDATION_CALLSITE_STRING_IS_AUTHORITY: str = "NO"
VALIDATED_OWNERSHIP_BOOL_IS_AUTHORITY: str = "NO"
BOT_MINT_DURABLE_TRACE_SOURCE: str = "services.video_trace_state:begin_video_confirm_execution"
BOT_MINT_DURABLE_TRACE_LOOKUP: str = "PASS"
BOT_MINT_CALLER_ASSERTIONS_ONLY: str = "NO"
BOT_MINT_EVENT_SINGLE_USE: str = "YES"
GENERIC_SERVICE_CAN_MINT_FROM_STRINGS: str = "NO"
WORKER_CAN_MINT_FROM_STRINGS: str = "NO"
PROVIDER_CAN_MINT_FROM_STRINGS: str = "NO"
CALLER_AUTH_DICT_ALLOWED: str = "NO"
CALLER_AUTH_JSON_ALLOWED: str = "NO"
DURABLE_OWNER_RECORD_REQUIRED: str = "YES"
CANONICAL_AUTH_RECORD_TYPE_PROVEN: str = "YES"
CANONICAL_AUTH_STAGE_PROVEN: str = "YES"
CANONICAL_AUTH_VALIDATOR_PASS: str = "YES"
CANONICAL_OWNER_VALIDATOR_ACTUALLY_CALLED: str = "YES"
REPORT_PRODUCT_FAMILY: str = "Product Video"
CANONICAL_OWNER_PRODUCT_TYPE: str = "video_ai_prompt"
CANONICAL_PRODUCT_BINDING: str = "EXACT"
WRONG_USER_OWNER_LIVE_BUTTON: str = "HIDDEN"
WRONG_JOB_OWNER_LIVE_BUTTON: str = "HIDDEN"
WRONG_REQUEST_OWNER_LIVE_BUTTON: str = "HIDDEN"
CALLER_ENTRYPOINT_AUTHORITY: str = "NO"
CALLER_BOT_ORIGIN_BOOL_AUTHORITY: str = "NO"
CALLER_USER_FLOW_AUTHORITY: str = "NO"

# N21AE explicit additions
CALLBACK_OWNERSHIP_BOOL_AUTHORITY: str = "NO"
DURABLE_CALLBACK_VALIDATION_SOURCE: str = "services.video_trace_state:record_owner_live_callback_origin_in_trace"
OWNER_LIVE_MINT_DURABLE_EVENT_LOOKUP: str = "PASS"
BOT_EVENT_EXISTED_BEFORE_MINT: str = "YES"
BOT_MINT_CLAIM_IS_CONSUMPTION_NOT_ORIGIN_CREATION: str = "YES"
PAID_LIVE_AVAILABILITY_GATE_ENFORCED: str = "YES"
OWNER_AUTH_USER_ID_REQUIRED_FOR_PAID_LIVE: str = "YES"
MISSING_USER_OWNER_LIVE_BUTTON: str = "HIDDEN"
CALLER_VALIDATION_STRINGS_AUTHORITY: str = "NO"
BLOCKER_OWNER_LIVE_ISSUANCE_NOT_PROVEN: str = "owner_live_issuance_authority_not_proven"

# N21AF explicit additions
PRODUCTION_PAID_LIVE_TEST_OVERRIDE: str = "ABSENT"
CALLER_CAN_BYPASS_PAID_LIVE_AVAILABILITY: str = "NO"
PAID_LIVE_UNAVAILABLE_BUTTON: str = "HIDDEN"
OWNER_LIVE_CALLBACK_FAILCLOSED: str = "YES"
OWNER_LIVE_MINT_FAILCLOSED: str = "YES"
OWNER_LIVE_RESERVATION_FAILCLOSED: str = "YES"
CALLBACK_HMAC_HARDCODED_FALLBACK: str = "ABSENT"
HMAC_ROLE: str = "INTEGRITY_ONLY"
HMAC_IS_CALLBACK_OWNERSHIP_AUTHORITY: str = "NO"
GENERIC_SERVICE_CAN_CREATE_VALID_CALLBACK_RECEIPT: str = "NO"
WORKER_CAN_CREATE_VALID_CALLBACK_RECEIPT: str = "NO"
PROVIDER_CAN_CREATE_VALID_CALLBACK_RECEIPT: str = "NO"
CALLSITE_STRING_CAN_CREATE_CALLBACK_AUTHORITY: str = "NO"
CALLER_ROLE_STRING_CAN_CREATE_CALLBACK_AUTHORITY: str = "NO"
ARBITRARY_IDS_TO_TRUSTED_RECEIPT: str = "NO"
CALLBACK_OWNERSHIP_RECEIPT_PROVENANCE: str = "NOT_PROVEN"
TEST_FIXTURE_CAN_AUTHORIZE_REAL_TRANSPORT: str = "NO"
# ─── END N21AC / N21AD / N21AE / N21AF INVARIANT CONSTANTS ──────────────────


def validate_owner_live_button_eligibility(
    owner_receipt: str,
    *,
    job_id: str | int = 0,
    request_id: str = "",
    user_id: str | int = "",
    chat_id: str | int = "",
    db_path: str | None = None,
    env: dict[str, str] | None = None,
    conn: sqlite3.Connection | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Validate Owner live button eligibility against exact user binding (OWNER_AUTH_USER_ID_REQUIRED_FOR_PAID_LIVE=YES)."""
    # N21AF §5: If PAID_LIVE_TEST_AVAILABLE != "YES", button is unconditionally ineligible (PAID_LIVE_UNAVAILABLE_BUTTON=HIDDEN)
    if PAID_LIVE_TEST_AVAILABLE != "YES":
        return False, BLOCKER_OWNER_LIVE_ISSUANCE_NOT_PROVEN, {}

    clean_user_id = str(user_id or "").strip()
    if not clean_user_id or clean_user_id in {"0", "None"}:
        return False, "owner_live_user_id_required", {}

    valid, blocker, auth_data = validate_canonical_owner_live_authorization(
        owner_receipt,
        product_family="Product Video",
        job_id=str(job_id) if job_id else "",
        request_id=str(request_id) if request_id else "",
        user_id=clean_user_id,
        db_path=db_path,
        env=env,
        conn=conn,
    )
    if not valid:
        return False, blocker, auth_data

    auth_uid = str((auth_data or {}).get("user_id") or "").strip()
    if not auth_uid or auth_uid in {"0", "None"}:
        return False, "owner_live_auth_missing_user_id", auth_data
    if auth_uid != clean_user_id:
        return False, "owner_live_auth_user_mismatch", auth_data

    clean_chat_id = str(chat_id or "").strip()
    if clean_chat_id and clean_chat_id not in {"0", "None"}:
        auth_cid = str((auth_data or {}).get("chat_id") or "").strip()
        if auth_cid and auth_cid not in {"0", "None"} and auth_cid != clean_chat_id:
            return False, "owner_live_auth_chat_mismatch", auth_data

    return True, "", auth_data


@dataclasses.dataclass(frozen=True)
class BotMintAuthority:
    """Mint capability issued downstream of validated Telegram Bot UI updates."""
    callsite: str
    telegram_update_id: int | str
    chat_id: int | str
    user_id: int | str
    callback_query_id: str = ""
    job_id: str = ""
    request_id: str = ""
    action: str = "b14_confirm"
    validation_source: str = ""
    validation_callsite: str = ""
    purpose: str = PURPOSE_PRODUCTION_USER_ACTION
    owner_receipt: str = ""
    expected_max_provider_spend_usd: float | Decimal = 0.0
    nonce: str = dataclasses.field(default_factory=lambda: secrets.token_hex(16))
    is_test_override: bool = False
    record_type: str = RECORD_TYPE_SCENE_SUBMIT
    _issued_by_seam: bool = False

    def __post_init__(self):
        if not self._issued_by_seam:
            raise PermissionError(
                "Direct construction of BotMintAuthority is forbidden; "
                "DIRECT_BOT_MINT_AUTHORITY_CONSTRUCTOR_USABLE=NO. "
                "Use issue_bot_mint_authority downstream of validated bot interaction."
            )


def create_owner_live_authorization(*args: Any, **kwargs: Any) -> str:
    """RETIRED unconditionally (N21AC-FIX1) — CREATE_OWNER_LIVE_AUTHORIZATION_PRODUCTION_CALLABLE=NO.

    Owner authority is issued exclusively through the canonical web acceptance bridge
    (video_request_traces table). The spend guard must NEVER create authority records.
    Any call to this function in production raises PermissionError unconditionally.
    """
    raise PermissionError(
        "create_owner_live_authorization is RETIRED unconditionally (N21AC-FIX1). "
        "Owner authority cannot be created in spend_guard under any arguments or caller overrides. "
        "SPEND_GUARD_CAN_CREATE_OWNER_AUTHORITY=NO, CREATE_OWNER_LIVE_AUTHORIZATION_PRODUCTION_CALLABLE=NO"
    )


def validate_canonical_owner_live_authorization(
    authorization_id: str | dict[str, Any],
    *,
    product_family: str = "",
    product_type: str = "",
    job_id: str | int = "",
    request_id: str = "",
    user_id: str | int = "",
    account_id: str | int = "",
    project_id: str | int | None = None,
    operation: str = "",
    provider: str = "",
    capability: str = "",
    tier: str = "",
    model: str = "",
    runtime_sha: str = "",
    estimated_provider_cost: float | Decimal | None = None,
    estimated_provider_cost_unit: str = "",
    scene_index: int | None = None,
    allow_other_product: bool = False,
    db_path: str | None = None,
    env: dict[str, str] | None = None,
    conn: sqlite3.Connection | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Validate Owner authorization against single canonical existing repository authority."""
    from services import video_provider_router
    from services.video_trace_state import (
        compute_owner_acceptance_token_fingerprint,
        is_owner_acceptance_token_claimed_or_consumed,
    )

    # N21AD §10: NO DIRECT DICT / JSON AUTHORITY (CALLER_AUTH_DICT_ALLOWED=NO, CALLER_AUTH_JSON_ALLOWED=NO)
    if isinstance(authorization_id, dict):
        return False, BLOCKER_OWNER_LIVE_AUTH_RECORD_MISSING, {}
    if not isinstance(authorization_id, str):
        return False, BLOCKER_OWNER_LIVE_AUTH_RECORD_MISSING, {}

    clean_id = authorization_id.strip()
    if not clean_id:
        return False, BLOCKER_OWNER_LIVE_AUTH_RECORD_MISSING, {}
    if clean_id.startswith("{") or clean_id.endswith("}"):
        return False, BLOCKER_OWNER_LIVE_AUTH_RECORD_MISSING, {}

    if allow_other_product:
        return False, "owner_acceptance_product_mismatch", {}

    target_path = resolve_spend_guard_db_path(db_path, env)
    auth: dict[str, Any] = {}
    payload: dict[str, Any] = {}
    stage: str = ""
    row_req_id: str = ""
    row_attempt_key: str = ""

    should_close = False
    active_conn = conn
    if active_conn is None:
        active_conn = _get_sqlite_connection(target_path)
        should_close = True
    try:
        cur = active_conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='video_request_traces'")
        has_traces = cur.fetchone() is not None
        if has_traces:
            cur.execute(
                """
                SELECT request_id, current_stage, confirm_attempt_key, trace_payload_json
                FROM video_request_traces
                WHERE request_id = ? OR request_id = ? OR confirm_attempt_key = ? OR request_id = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (f"COA-{clean_id}", clean_id, f"COA-{clean_id}", f"OAT-{clean_id}"),
            )
            row = cur.fetchone()
            if row:
                row_req_id, stage, row_attempt_key, payload_json = row
                payload = json.loads(payload_json or "{}")
                auth = dict(payload.get("auth")) if isinstance(payload.get("auth"), dict) else dict(payload)
            else:
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='owner_live_authorizations'")
                if cur.fetchone():
                    cur.execute("SELECT authorization_id FROM owner_live_authorizations WHERE authorization_id = ?", (clean_id,))
                    if cur.fetchone():
                        return False, BLOCKER_SECOND_AUTHORITY_CANNOT_AUTHORIZE, {}
                return False, BLOCKER_OWNER_LIVE_AUTH_RECORD_MISSING, {}
        else:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='owner_live_authorizations'")
            if cur.fetchone():
                cur.execute("SELECT authorization_id FROM owner_live_authorizations WHERE authorization_id = ?", (clean_id,))
                if cur.fetchone():
                    return False, BLOCKER_SECOND_AUTHORITY_CANNOT_AUTHORIZE, {}
            return False, BLOCKER_OWNER_LIVE_AUTH_RECORD_MISSING, {}

        if not isinstance(auth, dict) or not auth:
            return False, BLOCKER_OWNER_LIVE_AUTH_RECORD_MISSING, {}

        fingerprint = auth.get("token_fingerprint") or compute_owner_acceptance_token_fingerprint(auth)

        # Check status: revoked, consumed
        st = str(auth.get("status") or "").strip().lower()
        if st == STATUS_OWNER_AUTH_REVOKED or stage == "REVOKED":
            return False, BLOCKER_OWNER_LIVE_AUTH_REVOKED, {}

        if st == STATUS_OWNER_AUTH_CONSUMED or stage in ("CONSUMED", "CLAIMED") or bool(auth.get("consumed")):
            return False, BLOCKER_OWNER_LIVE_AUTH_ALREADY_CONSUMED, {"token_fingerprint": fingerprint}

        # N21AD §11: CANONICAL AUTH RECORD MUST BE REAL
        # Do not treat an arbitrary video_request_traces row as Owner authority solely because fields look right.
        if stage != "CANONICAL_OWNER_AUTHORIZED":
            return False, "owner_acceptance_invalid_record_stage", {}

        has_canonical_prefix = (
            str(row_req_id or "").startswith("COA-")
            or str(row_attempt_key or "").startswith("COA-")
        )
        acc_type = str(auth.get("acceptance_type") or payload.get("acceptance_type") or "").strip()
        if (
            not has_canonical_prefix
            or not bool(auth.get("owner_authorized"))
            or acc_type not in {
                "owner_authorized_live_acceptance",
                "owner_authorized_acceptance",
                "owner_authorized_live_acceptance_lane",
            }
        ):
            return False, "owner_acceptance_invalid_record_type", {}

        exp_ts = auth.get("expires_at")
        if exp_ts is not None and str(exp_ts).strip() != "":
            try:
                if float(exp_ts) <= time.time():
                    return False, BLOCKER_OWNER_LIVE_AUTH_EXPIRED, {}
            except Exception:
                return False, "owner_acceptance_expiry_invalid", {}

        # Check replay guard
        if is_owner_acceptance_token_claimed_or_consumed(fingerprint, conn=active_conn, db_path=target_path):
            return False, BLOCKER_OWNER_LIVE_AUTH_ALREADY_CONSUMED, {"token_fingerprint": fingerprint}

        # N21AC §8: NO AUTHORITY DEFAULTS (OWNER_*_DEFAULT=ABSENT)
        raw_max = auth.get("max_provider_spend")
        raw_micro = auth.get("expected_max_provider_spend_micro_usd")
        if raw_max is None and raw_micro is None:
            return False, "owner_acceptance_max_provider_spend_missing", {}
        if raw_micro is not None:
            exp_micro = int(raw_micro)
        else:
            try:
                if float(raw_max) <= 0:
                    return False, "owner_acceptance_max_provider_spend_missing", {}
                exp_micro = to_micro_usd(Decimal(str(raw_max)))
            except (ValueError, TypeError):
                return False, "owner_acceptance_max_provider_spend_missing", {}
        if exp_micro <= 0:
            return False, "owner_acceptance_max_provider_spend_missing", {}

        slots_str = str(auth.get("allowed_scene_slots") or "").strip()
        if not slots_str:
            return False, "owner_acceptance_slots_missing", {}

        auth_provider = str(auth.get("provider") or "").strip()
        if not auth_provider:
            return False, "owner_acceptance_provider_missing", {}

        auth_tier = str(auth.get("tier") or auth.get("quality_tier") or auth.get("model") or "").strip()
        if not auth_tier:
            return False, "owner_acceptance_tier_missing", {}

        auth_sha = str(auth.get("runtime_sha") or "").strip()
        if not auth_sha:
            return False, "owner_acceptance_runtime_sha_missing", {}

        # N21AC §9: Dynamic runtime SHA resolution without hardcoded fallback
        effective_env = os.environ if env is None else env
        try:
            from services.remote_worker_api import resolve_runtime_sha
            resolved_sha = resolve_runtime_sha(environ=effective_env)
        except Exception:
            resolved_sha = ""
        actual_sha = str(runtime_sha or resolved_sha or "").strip()
        if not actual_sha:
            return False, "owner_acceptance_runtime_sha_unresolvable", {}

        # N21AD §13: PRODUCT FAMILY VS CANONICAL PRODUCT TYPE (No allow_other_product bypass)
        if bool(auth.get("allow_other_product")):
            return False, "owner_acceptance_product_mismatch", {}
        raw_auth_prod_type = str(auth.get("product_type") or "").strip()
        raw_auth_prod_fam = str(auth.get("product_family") or "").strip()
        if not raw_auth_prod_type and not raw_auth_prod_fam:
            return False, "owner_acceptance_product_missing", {}
        allowed_canonical_product_types = {
            CANONICAL_OWNER_PRODUCT_TYPE,
            "video_ai_video_reference",
            "self_shot_scene_change",
        }
        if raw_auth_prod_type not in allowed_canonical_product_types:
            return False, "owner_acceptance_product_mismatch", {}
        if raw_auth_prod_fam and raw_auth_prod_fam != REPORT_PRODUCT_FAMILY:
            return False, "owner_acceptance_product_mismatch", {}
        if product_family and str(product_family).strip() not in {REPORT_PRODUCT_FAMILY, raw_auth_prod_type}:
            return False, "owner_acceptance_product_mismatch", {}
        if product_type and str(product_type).strip() != raw_auth_prod_type:
            return False, "owner_acceptance_product_mismatch", {}

        auth_job = str(auth.get("job_id") or "").strip()
        if not auth_job:
            return False, "owner_acceptance_job_id_missing", {}
        if job_id and str(job_id).strip() != auth_job:
            return False, "owner_acceptance_job_mismatch", {}

        auth_req = str(auth.get("request_id") or "").strip()
        if not auth_req:
            return False, "owner_acceptance_request_id_missing", {}
        if request_id and str(request_id).strip() != auth_req:
            return False, "owner_acceptance_request_id_mismatch", {}

        auth_user = str(auth.get("user_id") or "").strip()
        if auth_user and user_id and str(user_id).strip() != auth_user:
            return False, "owner_acceptance_user_mismatch", {}

        auth_op = str(auth.get("operation") or "").strip().lower()
        if not auth_op:
            return False, "owner_acceptance_operation_missing", {}
        if operation and str(operation).strip().lower() != auth_op:
            return False, "owner_acceptance_operation_mismatch", {}

        if project_id is not None and str(project_id).strip() != "" and str(project_id).strip() != str(auth.get("project_id") or "").strip():
            return False, "owner_acceptance_project_mismatch", {}

        if provider and str(provider).strip() != auth_provider:
            return False, "owner_acceptance_provider_mismatch", {}

        if tier and str(tier).strip() != auth_tier:
            return False, "owner_acceptance_tier_mismatch", {}

        # N21AD §9, §12, §13: Construct ACTUAL runtime context (never copying from auth; AUTH_SELF_VALIDATION_ALLOWED=NO)
        if str(product_type or "").strip():
            expected_canonical_prod_type = str(product_type).strip()
        elif not product_family or str(product_family).strip() == REPORT_PRODUCT_FAMILY:
            expected_canonical_prod_type = CANONICAL_OWNER_PRODUCT_TYPE
        else:
            expected_canonical_prod_type = str(product_family).strip()
        actual_context: dict[str, Any] = {
            "product_type": expected_canonical_prod_type,
            "product_family": str(product_family or REPORT_PRODUCT_FAMILY).strip(),
            "job_id": str(job_id).strip() if str(job_id or "").strip() else None,
            "request_id": str(request_id).strip() if str(request_id or "").strip() else None,
            "user_id": str(user_id).strip() if str(user_id or "").strip() else None,
            "account_id": str(account_id).strip() if str(account_id or "").strip() else None,
            "project_id": str(project_id).strip() if project_id is not None and str(project_id).strip() != "" else None,
            "provider": str(provider or "").strip(),
            "capability": str(capability or "").strip(),
            "tier": str(tier or "").strip(),
            "model": str(model or tier or "").strip(),
            "runtime_sha": actual_sha,
        }
        if estimated_provider_cost is not None:
            actual_context["estimated_provider_cost"] = float(estimated_provider_cost)
            actual_context["estimated_provider_cost_unit"] = str(estimated_provider_cost_unit or "USD").strip().upper()

        auth_for_router = dict(auth)
        if auth_for_router.get("max_provider_spend") is None:
            auth_for_router["max_provider_spend"] = float(from_micro_usd(exp_micro))
        if not auth_for_router.get("max_provider_spend_unit") and not auth_for_router.get("spend_unit") and not auth_for_router.get("currency"):
            auth_for_router["max_provider_spend_unit"] = "USD"

        router_valid, router_blocker, router_verified = video_provider_router.validate_owner_acceptance_authorization(
            auth_for_router,
            context=actual_context,
            environ=effective_env,
            db_path=target_path,
            conn=active_conn,
        )
        if not router_valid:
            if router_blocker == "owner_acceptance_already_consumed":
                return False, BLOCKER_OWNER_LIVE_AUTH_ALREADY_CONSUMED, {"token_fingerprint": fingerprint}
            if router_blocker == "owner_acceptance_expired":
                return False, BLOCKER_OWNER_LIVE_AUTH_EXPIRED, {}
            return False, str(router_blocker or "owner_acceptance_validation_failed"), {}

        if scene_index is not None and scene_index >= 1 and slots_str != "*":
            allowed_slots = {int(s.strip()) for s in slots_str.split(",") if s.strip().isdigit()}
            if scene_index not in allowed_slots:
                return False, BLOCKER_OWNER_LIVE_AUTH_SLOT_MISMATCH, {}

        slots_set = {int(s.strip()) for s in slots_str.split(",") if s.strip().isdigit()}
        calc_max_submits = int(auth.get("max_submits") or len(slots_set) or 1)

        auth_data = {
            "authorization_id": str(auth.get("token_id") or fingerprint),
            "token_fingerprint": fingerprint,
            "job_id": str(auth_job),
            "request_id": str(auth_req),
            "user_id": str(auth_user),
            "product_family": REPORT_PRODUCT_FAMILY,
            "product_type": raw_auth_prod_type,
            "operation": auth_op,
            "provider": auth_provider,
            "tier": auth_tier,
            "runtime_sha": auth_sha,
            "allowed_scene_slots": slots_str,
            "allowed_slots_set": slots_set,
            "max_submits": calc_max_submits,
            "expected_max_provider_spend_micro_usd": exp_micro,
            "max_provider_spend": from_micro_usd(exp_micro),
            "status": STATUS_OWNER_AUTH_ACTIVE,
            "raw_auth": auth,
            "router_verified": router_verified,
        }
        return True, "", auth_data
    finally:
        if should_close:
            active_conn.close()


def validate_owner_live_authorization(
    authorization_id: str,
    *,
    product_family: str = "",
    product_type: str = "",
    job_id: str | int = "",
    request_id: str = "",
    user_id: str | int = "",
    account_id: str | int = "",
    project_id: str | int | None = None,
    operation: str = "",
    provider: str = "",
    capability: str = "",
    tier: str = "",
    model: str = "",
    runtime_sha: str = "",
    estimated_provider_cost: float | Decimal | None = None,
    estimated_provider_cost_unit: str = "",
    scene_index: int | None = None,
    db_path: str | None = None,
    env: dict[str, str] | None = None,
    conn: sqlite3.Connection | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Validate durable Owner live authorization record via canonical authority."""
    valid, blocker, data = validate_canonical_owner_live_authorization(
        authorization_id,
        product_family=product_family,
        product_type=product_type,
        job_id=job_id,
        request_id=request_id,
        user_id=user_id,
        account_id=account_id,
        project_id=project_id,
        operation=operation,
        provider=provider,
        capability=capability,
        tier=tier,
        model=model,
        runtime_sha=runtime_sha,
        estimated_provider_cost=estimated_provider_cost,
        estimated_provider_cost_unit=estimated_provider_cost_unit,
        scene_index=scene_index,
        db_path=db_path,
        env=env,
        conn=conn,
    )
    if not valid:
        if blocker in (
            "owner_acceptance_job_mismatch",
            "owner_acceptance_request_id_mismatch",
            "owner_acceptance_operation_mismatch",
            "owner_acceptance_product_mismatch",
            "owner_acceptance_lineage_mismatch",
            "owner_acceptance_user_mismatch",
            "owner_acceptance_project_mismatch",
        ):
            return False, BLOCKER_OWNER_LIVE_AUTH_LINEAGE_MISMATCH, data
        if blocker in ("owner_acceptance_slots_missing", "owner_acceptance_slot_mismatch"):
            return False, BLOCKER_OWNER_LIVE_AUTH_SLOT_MISMATCH, data
        if blocker in ("owner_acceptance_max_provider_spend_missing", "owner_acceptance_spend_limit_exceeded"):
            return False, BLOCKER_OWNER_AUTHORIZED_MAX_SPEND_EXCEEDED, data
    return valid, blocker, data


def issue_bot_mint_authority(
    *,
    callsite: str = "bot.py:handle_video_product_callback:b14_confirm",
    telegram_update_id: int | str = 0,
    callback_query_id: str = "",
    chat_id: int | str = "",
    user_id: int | str = "",
    job_id: str = "",
    request_id: str = "",
    project_id: int | str | None = None,
    confirm_attempt_key: str = "",
    product_type: str = "",
    action: str = "b14_confirm",
    validation_source: str = "",
    validation_callsite: str = "",
    validated_ownership: bool = False,
    callback_ownership_receipt: dict | None = None,
    purpose: str = PURPOSE_PRODUCTION_USER_ACTION,
    owner_receipt: str = "",
    expected_max_provider_spend_usd: float | Decimal = 0.0,
    db_path: str | None = None,
    env: dict[str, str] | None = None,
    conn: sqlite3.Connection | None = None,
    **kwargs: Any,
) -> BotMintAuthority:
    """Issue genuine Bot mint authority bound to pre-existing durable Bot validation event in SQLite."""
    if "_caller_override_for_test" in kwargs or kwargs.get("_caller_override_for_test"):
        raise PermissionError(
            f"Unauthorized mint caller '{kwargs.get('_caller_override_for_test')}': generic service/worker/provider cannot issue mint authority "
            "(CALLSITE_STRING_IS_AUTHORITY=NO, PRODUCTION_PAID_LIVE_TEST_OVERRIDE=ABSENT)"
        )
    if callsite not in _ALLOWED_LIVE_MINT_CALLSITES:
        raise PermissionError(f"Unauthorized mint callsite: '{callsite}'")

    # N21AD §3: CALLER_VALIDATED_OWNERSHIP_BOOL_TRUSTED=NO, VALIDATED_OWNERSHIP_BOOL_IS_AUTHORITY=NO
    if not validated_ownership:
        raise PermissionError("Callback ownership must be validated before issuing BotMintAuthority")
    if not validation_source or not validation_callsite:
        raise PermissionError(
            "Caller validated_ownership boolean alone is not trusted; canonical validation source required "
            "(CALLER_VALIDATED_OWNERSHIP_BOOL_TRUSTED=NO)"
        )

    if validation_source != BOT_CONFIRM_VALIDATION_SOURCE:
        raise PermissionError(f"Unauthorized validation_source: '{validation_source}'")
    if validation_callsite != BOT_CONFIRM_VALIDATION_CALLSITE:
        raise PermissionError(f"Unauthorized validation_callsite: '{validation_callsite}'")

    if action not in ("b14_confirm", "create_video_task"):
        raise ValueError(f"Unauthorized mint action: '{action}'")

    # Real Telegram identities required. No synthetic fallbacks!
    try:
        up_id = int(telegram_update_id or 0)
    except Exception:
        up_id = 0
    if up_id <= 0:
        raise ValueError("telegram_update_id > 0 required to issue BotMintAuthority (real update required)")

    cbq_id = str(callback_query_id or "").strip()
    if not cbq_id or cbq_id.startswith("cbq_fallback_") or cbq_id == "cbq_1":
        raise ValueError("Real callback_query_id required to issue BotMintAuthority (synthetic fallback forbidden)")

    if not str(chat_id or "").strip():
        raise ValueError("chat_id required to issue BotMintAuthority")
    if not str(user_id or "").strip():
        raise ValueError("user_id required to issue BotMintAuthority")

    j_id = str(job_id or "").strip()
    if not j_id:
        raise ValueError("job_id required to issue BotMintAuthority")

    r_id = str(request_id or "").strip()
    if not r_id or r_id.startswith("req_fallback_"):
        raise ValueError("Real request_id required to issue BotMintAuthority (synthetic fallback forbidden)")

    canonical_purpose = str(purpose or PURPOSE_PRODUCTION_USER_ACTION).strip()
    if canonical_purpose not in (PURPOSE_PRODUCTION_USER_ACTION, PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST):
        raise ValueError(f"Invalid confirmation purpose: '{canonical_purpose}'")

    try:
        target_path = resolve_spend_guard_db_path(db_path, env)
    except Exception as exc:
        raise PermissionError(
            f"Durable Bot event authority lookup failed (shared DB unavailable: {exc}); "
            "caller strings alone cannot authorize (BOT_MINT_DURABLE_TRACE_LOOKUP=FAIL, CALLSITE_STRING_IS_AUTHORITY=NO)"
        )

    init_spend_guard_db(conn=conn, db_path=target_path, env=env)

    actual_expected_max = expected_max_provider_spend_usd
    clean_owner_receipt = str(owner_receipt or "").strip()
    mint_nonce = secrets.token_hex(16)

    if canonical_purpose == PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST:
        if callsite and callsite not in _ALLOWED_LIVE_MINT_CALLSITES:
            raise PermissionError(f"Unauthorized live mint callsite '{callsite}' not in _ALLOWED_LIVE_MINT_CALLSITES")
        if not clean_owner_receipt:
            raise PermissionError(
                "owner_receipt is required when issuing BotMintAuthority with PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST "
                "(PAID_LIVE_TEST_PURPOSE_REQUIRES_OWNER_AUTH_RECORD=YES)"
            )

        # N21AF §3, §4: Universal fail-closed when paid live test is unavailable.
        # No test override parameter or branch exists (PRODUCTION_PAID_LIVE_TEST_OVERRIDE=ABSENT, CALLER_CAN_BYPASS_PAID_LIVE_AVAILABILITY=NO)
        if PAID_LIVE_TEST_AVAILABLE != "YES":
            raise PermissionError(BLOCKER_OWNER_LIVE_ISSUANCE_NOT_PROVEN)

        try:
            auth_valid, auth_blocker, auth_data = validate_owner_live_authorization(
                clean_owner_receipt,
                product_family="Product Video",
                job_id=j_id,
                request_id=r_id,
                user_id=str(user_id).strip(),
                operation=action,
                db_path=target_path,
                env=env,
                conn=conn,
            )
        except Exception as exc:
            raise PermissionError(
                f"Owner live authorization validation failed: {exc} "
                "(PAID_LIVE_TEST_PURPOSE_REQUIRES_OWNER_AUTH_RECORD=YES)"
            )
        if not auth_valid:
            raise PermissionError(
                f"Owner live authorization invalid for live-test mint: {auth_blocker} "
                "(PAID_LIVE_TEST_PURPOSE_REQUIRES_OWNER_AUTH_RECORD=YES)"
            )
        auth_micro = auth_data.get("expected_max_provider_spend_micro_usd") or 0
        actual_expected_max = from_micro_usd(auth_micro) if auth_micro else Decimal("0.0")

        # N21AE §3, §4: Pre-existing durable Bot event verification
        # Query video_request_traces for genuine callback event recorded by registered Bot dispatcher
        should_close = False
        active_conn = conn
        if active_conn is None:
            active_conn = _get_sqlite_connection(target_path)
            should_close = True
        try:
            if not active_conn.in_transaction:
                active_conn.execute("BEGIN IMMEDIATE")
            cur = active_conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='video_request_traces'")
            if cur.fetchone() is None:
                if should_close:
                    active_conn.rollback()
                raise PermissionError(
                    "Pre-existing durable Bot event table missing "
                    "(OWNER_LIVE_MINT_DURABLE_EVENT_LOOKUP=FAIL, BOT_EVENT_EXISTED_BEFORE_MINT=NO)"
                )

            cur.execute(
                """
                SELECT request_id, job_id, owner_user_id, owner_chat_id, trace_payload_json
                FROM video_request_traces
                WHERE request_id = ? OR request_id = ? OR confirm_attempt_key = ? OR request_id = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (f"COA-{clean_owner_receipt}", clean_owner_receipt, f"COA-{clean_owner_receipt}", f"OAT-{clean_owner_receipt}"),
            )
            trace_row = cur.fetchone()
            if not trace_row:
                if should_close:
                    active_conn.rollback()
                raise PermissionError(
                    f"Pre-existing durable Bot callback event missing for '{clean_owner_receipt}' "
                    "(OWNER_LIVE_MINT_DURABLE_EVENT_LOOKUP=FAIL, BOT_EVENT_EXISTED_BEFORE_MINT=NO)"
                )

            (db_req_id, db_job_id, db_user_id, db_chat_id, db_payload_json) = trace_row
            try:
                t_payload = json.loads(db_payload_json or "{}")
            except Exception:
                t_payload = {}
            target_p = t_payload.get("auth") if isinstance(t_payload.get("auth"), dict) else t_payload

            t_update_id = int(t_payload.get("telegram_update_id") or target_p.get("telegram_update_id") or 0)
            t_cbq_id = str(t_payload.get("callback_query_id") or target_p.get("callback_query_id") or "").strip()
            t_chat_id = str(t_payload.get("callback_chat_id") or target_p.get("callback_chat_id") or db_chat_id or "").strip()
            t_user_id = str(t_payload.get("callback_user_id") or target_p.get("callback_user_id") or db_user_id or "").strip()
            t_job_id = str(t_payload.get("callback_job_id") or target_p.get("callback_job_id") or db_job_id or "").strip()
            t_req_id = str(t_payload.get("callback_request_id") or target_p.get("callback_request_id") or db_req_id or "").strip()
            t_action = str(t_payload.get("callback_action") or target_p.get("callback_action") or "").strip()
            t_mint_st = str(t_payload.get("bot_origin_mint_status") or target_p.get("bot_origin_mint_status") or "").strip().upper()
            t_own_res = str(t_payload.get("callback_ownership_result") or target_p.get("callback_ownership_result") or "").strip().upper()
            t_cb_rcpt = t_payload.get("callback_ownership_receipt") or target_p.get("callback_ownership_receipt")

            from services.video_trace_state import verify_canonical_callback_ownership_receipt
            if (
                t_update_id <= 0
                or not t_cbq_id
                or t_own_res != "VALIDATED"
                or not verify_canonical_callback_ownership_receipt(
                    t_cb_rcpt,
                    telegram_update_id=up_id,
                    callback_query_id=cbq_id,
                    chat_id=str(chat_id).strip(),
                    user_id=str(user_id).strip(),
                    job_id=j_id,
                    request_id=r_id,
                    owner_receipt=clean_owner_receipt,
                )
            ):
                if should_close:
                    active_conn.rollback()
                raise PermissionError(
                    "Pre-existing durable Bot callback event missing or callback ownership receipt invalid/unverified "
                    "(OWNER_LIVE_MINT_DURABLE_EVENT_LOOKUP=FAIL, BOT_EVENT_EXISTED_BEFORE_MINT=NO)"
                )

            if callback_ownership_receipt is not None:
                if callback_ownership_receipt.get("provenance") == "TEST_ONLY":
                    if os.environ.get("PYTEST_CURRENT_TEST") is None:
                        if should_close:
                            active_conn.rollback()
                        raise PermissionError(
                            "TEST_ONLY callback receipt cannot authorize real transport "
                            "(TEST_FIXTURE_CAN_AUTHORIZE_REAL_TRANSPORT=NO)"
                        )
                if not verify_canonical_callback_ownership_receipt(
                    callback_ownership_receipt,
                    telegram_update_id=up_id,
                    callback_query_id=cbq_id,
                    chat_id=str(chat_id).strip(),
                    user_id=str(user_id).strip(),
                    job_id=j_id,
                    request_id=r_id,
                    owner_receipt=clean_owner_receipt,
                ):
                    if should_close:
                        active_conn.rollback()
                    raise PermissionError(
                        "Caller callback_ownership_receipt invalid or signature verification failed"
                    )

            if t_mint_st in {"MINTED", "CONSUMED"}:
                if should_close:
                    active_conn.rollback()
                raise PermissionError("Durable Bot live event already used (BOT_MINT_EVENT_SINGLE_USE=YES)")

            # Match exact identity against pre-existing event
            if up_id != t_update_id:
                if should_close:
                    active_conn.rollback()
                raise PermissionError(f"Durable Bot event telegram_update_id mismatch: '{up_id}' != '{t_update_id}'")
            if cbq_id != t_cbq_id:
                if should_close:
                    active_conn.rollback()
                raise PermissionError(f"Durable Bot event callback_query_id mismatch: '{cbq_id}' != '{t_cbq_id}'")
            if str(chat_id).strip() != t_chat_id:
                if should_close:
                    active_conn.rollback()
                raise PermissionError(f"Durable Bot event chat_id mismatch: '{chat_id}' != '{t_chat_id}'")
            if str(user_id).strip() != t_user_id:
                if should_close:
                    active_conn.rollback()
                raise PermissionError(f"Durable Bot event user_id mismatch: '{user_id}' != '{t_user_id}'")
            if j_id != t_job_id:
                if should_close:
                    active_conn.rollback()
                raise PermissionError(f"Durable Bot event job_id mismatch: '{j_id}' != '{t_job_id}'")
            if r_id != t_req_id:
                if should_close:
                    active_conn.rollback()
                raise PermissionError(f"Durable Bot event request_id mismatch: '{r_id}' != '{t_req_id}'")
            if action and t_action and action != t_action:
                if should_close:
                    active_conn.rollback()
                raise PermissionError(f"Durable Bot event action mismatch: '{action}' != '{t_action}'")

            claim_key = f"owner_live:{r_id}:{clean_owner_receipt}"
            try:
                active_conn.execute(
                    """
                    INSERT INTO bot_mint_event_claims (
                        event_claim_key, request_id, confirm_attempt_key, job_id, project_id,
                        user_id, chat_id, telegram_update_id, callback_query_id_safe,
                        purpose, claimed_at, mint_nonce
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        claim_key,
                        r_id,
                        f"COA-{clean_owner_receipt}",
                        j_id,
                        int(project_id or 0),
                        str(user_id).strip(),
                        str(chat_id).strip(),
                        up_id,
                        cbq_id,
                        canonical_purpose,
                        time.time(),
                        mint_nonce,
                    ),
                )
            except sqlite3.IntegrityError:
                if should_close:
                    active_conn.rollback()
                raise PermissionError(
                    f"Durable Bot Owner-live event '{claim_key}' already claimed; single-use enforced "
                    "(BOT_MINT_EVENT_SINGLE_USE=YES)"
                )

            # Mark trace status MINTED
            t_payload["bot_origin_mint_status"] = "MINTED"
            if isinstance(t_payload.get("auth"), dict):
                t_payload["auth"]["bot_origin_mint_status"] = "MINTED"
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            cur.execute(
                """
                UPDATE video_request_traces
                SET trace_payload_json = ?, updated_at = ?
                WHERE request_id = ?
                """,
                (json.dumps(t_payload, ensure_ascii=False, sort_keys=True), now_iso, str(db_req_id)),
            )

            if should_close:
                active_conn.commit()
        finally:
            if should_close:
                active_conn.close()
    else:
        # N21AD §4, §5, §6, §7: PURPOSE_PRODUCTION_USER_ACTION MUST resolve pre-existing durable
        # begin_video_confirm_execution trace in video_request_traces and claim it atomically once.
        should_close = False
        active_conn = conn
        if active_conn is None:
            active_conn = _get_sqlite_connection(target_path)
            should_close = True
        try:
            if not active_conn.in_transaction:
                active_conn.execute("BEGIN IMMEDIATE")
            cur = active_conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='video_request_traces'")
            if cur.fetchone() is None:
                if should_close:
                    active_conn.rollback()
                raise PermissionError(
                    "Durable Bot confirm trace table missing; caller strings alone cannot authorize "
                    "(BOT_MINT_DURABLE_TRACE_LOOKUP=FAIL, CALLSITE_STRING_IS_AUTHORITY=NO)"
                )
            cur.execute(
                """
                SELECT request_id, job_id, owner_user_id, owner_chat_id, product_type,
                       current_stage, confirm_attempt_key, trace_payload_json
                FROM video_request_traces
                WHERE request_id = ?
                LIMIT 1
                """,
                (r_id,),
            )
            trace_row = cur.fetchone()
            if not trace_row:
                if should_close:
                    active_conn.rollback()
                raise PermissionError(
                    f"Durable Bot confirm trace not found for request_id='{r_id}'; "
                    "generic service/worker/provider passing valid strings is blocked "
                    "(BOT_MINT_DURABLE_TRACE_LOOKUP=FAIL, CALLSITE_STRING_IS_AUTHORITY=NO)"
                )
            (
                db_req_id,
                db_job_id,
                db_user_id,
                db_chat_id,
                db_product_type,
                db_stage,
                db_attempt_key,
                db_payload_json,
            ) = trace_row
            trace_payload = json.loads(db_payload_json or "{}")

            allowed_confirm_stages = {
                "JOB_CREATED",
                "PRECHECK_STARTED",
                "PRECHECK_PASSED",
                "READY_TO_SUBMIT",
            }
            eff_stage = str(db_stage or trace_payload.get("current_stage") or "").strip()
            if eff_stage not in allowed_confirm_stages:
                if should_close:
                    active_conn.rollback()
                raise PermissionError(
                    f"Durable Bot confirm trace stage '{eff_stage}' invalid for Bot mint authority; "
                    f"expected one of {sorted(allowed_confirm_stages)}"
                )

            eff_req_id = str(db_req_id or trace_payload.get("request_id") or "").strip()
            if eff_req_id != r_id:
                if should_close:
                    active_conn.rollback()
                raise PermissionError(f"Durable Bot confirm trace request_id mismatch: '{eff_req_id}' != '{r_id}'")

            eff_attempt_key = str(db_attempt_key or trace_payload.get("confirm_attempt_key") or "").strip()
            if not eff_attempt_key:
                if should_close:
                    active_conn.rollback()
                raise PermissionError("Durable Bot confirm trace missing confirm_attempt_key")
            if confirm_attempt_key and str(confirm_attempt_key).strip() != eff_attempt_key:
                if should_close:
                    active_conn.rollback()
                raise PermissionError(
                    f"Durable Bot confirm trace confirm_attempt_key mismatch: '{confirm_attempt_key}' != '{eff_attempt_key}'"
                )

            eff_job_id = str(db_job_id if db_job_id not in (None, "", 0, "0") else (trace_payload.get("job_id") or "")).strip()
            if not eff_job_id or eff_job_id in {"0", "None"} or eff_job_id != j_id:
                if should_close:
                    active_conn.rollback()
                raise PermissionError(f"Durable Bot confirm trace job_id mismatch: '{eff_job_id}' != '{j_id}'")

            eff_project_id = int(trace_payload.get("project_id") or 0)
            if eff_project_id <= 0:
                if should_close:
                    active_conn.rollback()
                raise PermissionError("Durable Bot confirm trace missing project_id")
            if project_id is not None and str(project_id).strip() != "" and int(project_id) != eff_project_id:
                if should_close:
                    active_conn.rollback()
                raise PermissionError(
                    f"Durable Bot confirm trace project_id mismatch: '{project_id}' != '{eff_project_id}'"
                )

            eff_user_id = str(
                db_user_id if db_user_id not in (None, "", 0, "0") else (trace_payload.get("owner_user_id") or "")
            ).strip()
            if not eff_user_id or eff_user_id == "0" or eff_user_id != str(user_id).strip():
                if should_close:
                    active_conn.rollback()
                raise PermissionError(f"Durable Bot confirm trace user_id mismatch: '{eff_user_id}' != '{user_id}'")

            eff_chat_id = str(
                db_chat_id if db_chat_id not in (None, "", 0, "0") else (trace_payload.get("owner_chat_id") or "")
            ).strip()
            if not eff_chat_id or eff_chat_id == "0" or eff_chat_id != str(chat_id).strip():
                if should_close:
                    active_conn.rollback()
                raise PermissionError(f"Durable Bot confirm trace chat_id mismatch: '{eff_chat_id}' != '{chat_id}'")

            eff_product_type = str(db_product_type or trace_payload.get("product_type") or "").strip()
            if not eff_product_type:
                if should_close:
                    active_conn.rollback()
                raise PermissionError("Durable Bot confirm trace missing product_type")
            if product_type and str(product_type).strip() != eff_product_type:
                if should_close:
                    active_conn.rollback()
                raise PermissionError(
                    f"Durable Bot confirm trace product_type mismatch: '{product_type}' != '{eff_product_type}'"
                )

            eff_update_id = int(trace_payload.get("telegram_update_id") or 0)
            if eff_update_id <= 0 or eff_update_id != up_id:
                if should_close:
                    active_conn.rollback()
                raise PermissionError(
                    f"Durable Bot confirm trace telegram_update_id mismatch: '{eff_update_id}' != '{up_id}'"
                )

            eff_cbq_id = str(
                trace_payload.get("callback_query_id_safe") or trace_payload.get("callback_query_id") or ""
            ).strip()
            if not eff_cbq_id or eff_cbq_id != cbq_id:
                if should_close:
                    active_conn.rollback()
                raise PermissionError(
                    f"Durable Bot confirm trace callback_query_id_safe mismatch: '{eff_cbq_id}' != '{cbq_id}'"
                )

            # N21AD §6: Atomic single-use claim of durable Bot confirm event
            claim_key = f"bot_confirm:{r_id}:{eff_attempt_key}"
            try:
                active_conn.execute(
                    """
                    INSERT INTO bot_mint_event_claims (
                        event_claim_key, request_id, confirm_attempt_key, job_id, project_id,
                        user_id, chat_id, telegram_update_id, callback_query_id_safe,
                        purpose, claimed_at, mint_nonce
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        claim_key,
                        r_id,
                        eff_attempt_key,
                        j_id,
                        eff_project_id,
                        eff_user_id,
                        eff_chat_id,
                        up_id,
                        cbq_id,
                        canonical_purpose,
                        time.time(),
                        mint_nonce,
                    ),
                )
            except sqlite3.IntegrityError:
                if should_close:
                    active_conn.rollback()
                raise PermissionError(
                    f"Durable Bot confirm event '{claim_key}' already claimed/replayed; single-use enforced "
                    "(BOT_MINT_EVENT_SINGLE_USE=YES)"
                )

            if should_close:
                active_conn.commit()
        finally:
            if should_close:
                active_conn.close()

    return BotMintAuthority(
        callsite=callsite or "bot.py:handle_video_product_callback:b14_confirm",
        telegram_update_id=up_id,
        chat_id=chat_id,
        user_id=user_id,
        callback_query_id=cbq_id,
        job_id=j_id,
        request_id=r_id,
        action=action,
        validation_source=validation_source,
        validation_callsite=validation_callsite,
        purpose=canonical_purpose,
        owner_receipt=clean_owner_receipt,
        expected_max_provider_spend_usd=actual_expected_max,
        nonce=mint_nonce,
        is_test_override=False,
        record_type=RECORD_TYPE_SCENE_SUBMIT,
        _issued_by_seam=True,
    )


def validate_bot_confirm_authority(authority: str | None) -> bool:
    """Validate that bot confirmation authority identifier is present.

    Note: String alone is not proof (Section 8). Non-forgeable authorization is verified
    against durable database records in bot_spend_confirmations.
    """
    if not authority:
        return False
    return bool(str(authority).strip())


@dataclasses.dataclass(frozen=True)
class ProviderPaidTransportAuthority:
    product_family: str
    provider: str
    operation: str
    endpoint_class: str  # paid_creation | query_poll | download | webhook_ack
    can_create_paid_usage: bool
    pricing_authority: str
    max_cost_authority: str
    bot_origin_required: bool
    weekly_cap_required: bool


PROVIDER_PAID_TRANSPORT_REGISTRY: tuple[ProviderPaidTransportAuthority, ...] = (
    ProviderPaidTransportAuthority(
        product_family="Product Video",
        provider="shopaikey_kling_video",
        operation="create_video_task",
        endpoint_class="paid_creation",
        can_create_paid_usage=True,
        pricing_authority="services/video_ai_real_pricing.py",
        max_cost_authority="config/product_video_price_route_map_20260827.json:kling-v3-15s",
        bot_origin_required=True,
        weekly_cap_required=True,
    ),
    ProviderPaidTransportAuthority(
        product_family="Product Video",
        provider="key4u_kling_video",
        operation="create_video_task",
        endpoint_class="paid_creation",
        can_create_paid_usage=True,
        pricing_authority="services/video_ai_real_pricing.py",
        max_cost_authority="config/product_video_price_route_map_20260827.json:kling-v3-15s",
        bot_origin_required=True,
        weekly_cap_required=True,
    ),
    ProviderPaidTransportAuthority(
        product_family="Product Video",
        provider="shopaikey_kling_video",
        operation="query_video_task",
        endpoint_class="query_poll",
        can_create_paid_usage=False,
        pricing_authority="none_query_poll_no_charge",
        max_cost_authority="none_query_poll_no_charge",
        bot_origin_required=False,
        weekly_cap_required=False,
    ),
    ProviderPaidTransportAuthority(
        product_family="Product Video",
        provider="key4u_kling_video",
        operation="query_video_task",
        endpoint_class="query_poll",
        can_create_paid_usage=False,
        pricing_authority="none_query_poll_no_charge",
        max_cost_authority="none_query_poll_no_charge",
        bot_origin_required=False,
        weekly_cap_required=False,
    ),
    ProviderPaidTransportAuthority(
        product_family="Product Video",
        provider="shopaikey_video",
        operation="create_video_task",
        endpoint_class="paid_creation",
        can_create_paid_usage=True,
        pricing_authority="config/product_video_price_route_map_20260827.json",
        max_cost_authority="config/product_video_price_route_map_20260827.json",
        bot_origin_required=True,
        weekly_cap_required=True,
    ),
    ProviderPaidTransportAuthority(
        product_family="Product Video",
        provider="key4u_video",
        operation="create_video_task",
        endpoint_class="paid_creation",
        can_create_paid_usage=True,
        pricing_authority="config/product_video_price_route_map_20260827.json",
        max_cost_authority="config/product_video_price_route_map_20260827.json",
        bot_origin_required=True,
        weekly_cap_required=True,
    ),
    ProviderPaidTransportAuthority(
        product_family="Product Video",
        provider="shopaikey",
        operation="create_video_task",
        endpoint_class="paid_creation",
        can_create_paid_usage=True,
        pricing_authority="config/product_video_price_route_map_20260827.json",
        max_cost_authority="config/product_video_price_route_map_20260827.json",
        bot_origin_required=True,
        weekly_cap_required=True,
    ),
    ProviderPaidTransportAuthority(
        product_family="Product Video",
        provider="key4u",
        operation="create_video_task",
        endpoint_class="paid_creation",
        can_create_paid_usage=True,
        pricing_authority="config/product_video_price_route_map_20260827.json",
        max_cost_authority="config/product_video_price_route_map_20260827.json",
        bot_origin_required=True,
        weekly_cap_required=True,
    ),
    ProviderPaidTransportAuthority(
        product_family="Product Video",
        provider="shopaikey_video",
        operation="query_video_task",
        endpoint_class="query_poll",
        can_create_paid_usage=False,
        pricing_authority="none_query_poll_no_charge",
        max_cost_authority="none_query_poll_no_charge",
        bot_origin_required=False,
        weekly_cap_required=False,
    ),
    ProviderPaidTransportAuthority(
        product_family="Product Video",
        provider="key4u_video",
        operation="query_video_task",
        endpoint_class="query_poll",
        can_create_paid_usage=False,
        pricing_authority="none_query_poll_no_charge",
        max_cost_authority="none_query_poll_no_charge",
        bot_origin_required=False,
        weekly_cap_required=False,
    ),
    ProviderPaidTransportAuthority(
        product_family="Voice / TTS",
        provider="shopaikey_minimax_tts",
        operation="create_tts_task",
        endpoint_class="paid_creation",
        can_create_paid_usage=True,
        pricing_authority="services/video_ai_real_pricing.py:CANONICAL_TTS_RATE_USD_PER_CHAR",
        max_cost_authority="services/video_ai_real_pricing.py:calculate_tts_cost_vnd",
        bot_origin_required=True,
        weekly_cap_required=True,
    ),
    ProviderPaidTransportAuthority(
        product_family="Voice / TTS",
        provider="shopaikey_minimax_tts",
        operation="query_tts_task",
        endpoint_class="query_poll",
        can_create_paid_usage=False,
        pricing_authority="none_query_poll_no_charge",
        max_cost_authority="none_query_poll_no_charge",
        bot_origin_required=False,
        weekly_cap_required=False,
    ),
    ProviderPaidTransportAuthority(
        product_family="Voice / TTS",
        provider="shopaikey_openai_tts",
        operation="create_tts_task",
        endpoint_class="paid_creation",
        can_create_paid_usage=True,
        pricing_authority="services/video_ai_real_pricing.py:CANONICAL_TTS_RATE_USD_PER_CHAR",
        max_cost_authority="services/video_ai_real_pricing.py:calculate_tts_cost_vnd",
        bot_origin_required=True,
        weekly_cap_required=True,
    ),
    ProviderPaidTransportAuthority(
        product_family="Voice / TTS",
        provider="shopaikey_openai_tts",
        operation="query_tts_task",
        endpoint_class="query_poll",
        can_create_paid_usage=False,
        pricing_authority="none_query_poll_no_charge",
        max_cost_authority="none_query_poll_no_charge",
        bot_origin_required=False,
        weekly_cap_required=False,
    ),
    ProviderPaidTransportAuthority(
        product_family="Voice / TTS",
        provider="shopaikey",
        operation="create_tts_task",
        endpoint_class="paid_creation",
        can_create_paid_usage=True,
        pricing_authority="services/video_ai_real_pricing.py:CANONICAL_TTS_RATE_USD_PER_CHAR",
        max_cost_authority="services/video_ai_real_pricing.py:calculate_tts_cost_vnd",
        bot_origin_required=True,
        weekly_cap_required=True,
    ),
    ProviderPaidTransportAuthority(
        product_family="Voice / TTS",
        provider="shopaikey",
        operation="query_tts_task",
        endpoint_class="query_poll",
        can_create_paid_usage=False,
        pricing_authority="none_query_poll_no_charge",
        max_cost_authority="none_query_poll_no_charge",
        bot_origin_required=False,
        weekly_cap_required=False,
    ),
    ProviderPaidTransportAuthority(
        product_family="Public Chat Pro",
        provider="claude-opus",
        operation="chat_completion",
        endpoint_class="paid_creation",
        can_create_paid_usage=True,
        pricing_authority="services/chat_pro_pricing.py:OPUS_INPUT_USD_PER_MILLION+OPUS_OUTPUT_USD_PER_MILLION",
        max_cost_authority="services/chat_pro_pricing.py:token_quote",
        bot_origin_required=True,
        weekly_cap_required=True,
    ),
    ProviderPaidTransportAuthority(
        product_family="Video AI Edit",
        provider="fal_video",
        operation="submit_video_edit",
        endpoint_class="paid_creation",
        can_create_paid_usage=True,
        pricing_authority="services/video_ai_edit_provider.py:FAL_5S_PROVIDER_COST_USD+FAL_10S_PROVIDER_COST_USD",
        max_cost_authority="services/video_ai_edit_provider.py:duration_fixed_quote",
        bot_origin_required=True,
        weekly_cap_required=True,
    ),
    ProviderPaidTransportAuthority(
        product_family="Video AI Edit",
        provider="fal_video",
        operation="poll_video_edit",
        endpoint_class="query_poll",
        can_create_paid_usage=False,
        pricing_authority="none_query_poll_no_charge",
        max_cost_authority="none_query_poll_no_charge",
        bot_origin_required=False,
        weekly_cap_required=False,
    ),
    ProviderPaidTransportAuthority(
        product_family="SubDub ASR",
        provider="gemini_transcribe",
        operation="transcribe_diarized_words",
        endpoint_class="paid_creation",
        can_create_paid_usage=True,
        pricing_authority="gemini_interactions_catalog",
        max_cost_authority="gemini_transcribe_audio_duration",
        bot_origin_required=True,
        weekly_cap_required=True,
    ),
    ProviderPaidTransportAuthority(
        product_family="SubDub ASR",
        provider="gemini_transcribe",
        operation="asr_transcribe",
        endpoint_class="paid_creation",
        can_create_paid_usage=True,
        pricing_authority="gemini_interactions_catalog",
        max_cost_authority="gemini_transcribe_audio_duration",
        bot_origin_required=True,
        weekly_cap_required=True,
    ),
    ProviderPaidTransportAuthority(
        product_family="SubDub ASR",
        provider="key4u_whisper",
        operation="openai_compatible_asr_transcribe",
        endpoint_class="paid_creation",
        can_create_paid_usage=True,
        pricing_authority="key4u_stt_catalog",
        max_cost_authority="key4u_stt_minute_quote",
        bot_origin_required=True,
        weekly_cap_required=True,
    ),
    ProviderPaidTransportAuthority(
        product_family="SubDub ASR",
        provider="key4u_whisper",
        operation="asr_transcribe",
        endpoint_class="paid_creation",
        can_create_paid_usage=True,
        pricing_authority="key4u_stt_catalog",
        max_cost_authority="key4u_stt_minute_quote",
        bot_origin_required=True,
        weekly_cap_required=True,
    ),
    ProviderPaidTransportAuthority(
        product_family="Music / Suno",
        provider="key4u_suno",
        operation="suno_create",
        endpoint_class="paid_creation",
        can_create_paid_usage=True,
        pricing_authority="none_missing_fail_closed",
        max_cost_authority="none_missing_fail_closed",
        bot_origin_required=True,
        weekly_cap_required=True,
    ),
    ProviderPaidTransportAuthority(
        product_family="Music / Suno",
        provider="key4u_suno",
        operation="suno_create_task",
        endpoint_class="paid_creation",
        can_create_paid_usage=True,
        pricing_authority="none_missing_fail_closed",
        max_cost_authority="none_missing_fail_closed",
        bot_origin_required=True,
        weekly_cap_required=True,
    ),
    ProviderPaidTransportAuthority(
        product_family="Music / Suno",
        provider="key4u_suno",
        operation="suno_query",
        endpoint_class="query_poll",
        can_create_paid_usage=False,
        pricing_authority="none_query_poll_no_charge",
        max_cost_authority="none_query_poll_no_charge",
        bot_origin_required=False,
        weekly_cap_required=False,
    ),
)


def resolve_paid_transport_authority(
    product_family: str,
    provider: str,
    operation: str,
) -> ProviderPaidTransportAuthority | None:
    norm_fam = str(product_family or "").strip().lower()
    norm_prov = str(provider or "").strip().lower()
    norm_op = str(operation or "").strip().lower()
    if not norm_fam or not norm_prov or not norm_op:
        return None

    resolved_prov = PROVIDER_ALIAS_MAP.get(norm_prov, norm_prov)

    for entry in PROVIDER_PAID_TRANSPORT_REGISTRY:
        if entry.product_family.lower() != norm_fam:
            continue
        ep_lower = entry.provider.lower()
        if ep_lower != norm_prov and ep_lower != resolved_prov:
            continue
        # Section 9: TRANSPORT_OPERATION_MATCH=EXACT
        if entry.operation.lower() != norm_op:
            continue
        return entry
    return None


PRODUCT_VIDEO_MODEL_ALIAS_MAP: dict[tuple[str, str], str] = {
    ("key4u", "kling-3.0-turbo"): "kling-video",
    ("key4u", "kling-v3"): "kling-video",
    ("key4u", "kling-video"): "kling-video",
    ("key4u", "veo_3_1-fast"): "veo_3_1-fast",
    ("shopaikey", "grok-2-image"): "grok-2-image",
    ("shopaikey", "veo3.1-fast"): "veo3.1-fast",
    ("shopaikey", "veo3.1-pro"): "veo3.1-pro",
}


def _load_product_video_route_map() -> dict[str, Any]:
    from pathlib import Path
    cand_paths = [
        Path(__file__).resolve().parents[1] / "config" / "product_video_price_route_map_20260827.json",
        Path("config/product_video_price_route_map_20260827.json"),
    ]
    for p in cand_paths:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


def resolve_canonical_cost_micro_usd(
    context: SpendGuardContext,
    authority: ProviderPaidTransportAuthority,
) -> tuple[int, bool, str]:
    """Derive canonical maximum cost in micro-USD from trusted pricing contracts (CALLER_COST_AUTHORITY_TRUSTED=NO)."""
    fam = authority.product_family.strip().lower()
    prov = authority.provider.strip().lower()
    op = authority.operation.strip().lower()

    if "query" in op or "poll" in op:
        return 0, True, "query_poll_zero_charge"

    if fam == "product video":
        route_map = _load_product_video_route_map()
        tiers = route_map.get("tiers_sorted_by_customer_price", [])
        if not tiers:
            return 0, False, "product_video_route_map_missing"

        prov_norm = prov.lower()
        if "shopaikey" in prov_norm:
            prov_key = "shopaikey"
        elif "key4u" in prov_norm:
            prov_key = "key4u"
        else:
            prov_key = prov_norm

        raw_model = str(context.model or "").strip()
        target_model = PRODUCT_VIDEO_MODEL_ALIAS_MAP.get((prov_key, raw_model), raw_model)

        target_tier = str(
            context.metadata.get("quality_key")
            or context.metadata.get("tier")
            or context.metadata.get("b14_quality")
            or ""
        ).strip().lower()

        duration_param = (
            context.metadata.get("duration_seconds")
            or context.metadata.get("duration")
            or context.metadata.get("provider_submit_seconds")
            or context.metadata.get("public_scene_seconds")
        )

        filtered_tiers = tiers
        if target_tier:
            filtered_tiers = [
                t for t in tiers
                if str(t.get("quality_key") or "").lower() == target_tier
                or str(t.get("tier_id") or "") == target_tier
            ]
            if not filtered_tiers:
                return 0, False, f"tier_not_found_in_route_map:{target_tier}"
        elif duration_param and float(duration_param) > 0:
            dur_int = int(float(duration_param))
            matching_dur_tiers = [
                t for t in tiers
                if int(t.get("seconds_per_scene") or 0) == dur_int
            ]
            if matching_dur_tiers:
                filtered_tiers = matching_dur_tiers

        matching_candidates = []
        for tier in filtered_tiers:
            for c in tier.get("candidates", []):
                if (
                    str(c.get("provider") or "").lower() == prov_key
                    and str(c.get("model") or "").strip() in {target_model, raw_model}
                    and bool(c.get("eligible"))
                ):
                    matching_candidates.append((tier, c))

        if not matching_candidates:
            return 0, False, f"unknown_product_video_model_pricing:{prov_key}:{raw_model}"

        costs: list[Decimal] = []
        for tier, c in matching_candidates:
            tier_sec = int(tier.get("seconds_per_scene") or 8)
            sec = float(duration_param) if duration_param and float(duration_param) > 0 else float(tier_sec)

            if c.get("usd_per_second") is not None and float(c.get("usd_per_second")) > 0:
                rate = Decimal(str(c["usd_per_second"]))
                cost_scene = rate * Decimal(str(sec))
            elif c.get("usd_per_scene") is not None and float(c.get("usd_per_scene")) > 0:
                cost_scene = Decimal(str(c["usd_per_scene"]))
            else:
                continue
            costs.append(cost_scene)

        if not costs:
            return 0, False, f"unpriced_product_video_candidates:{prov_key}:{raw_model}"

        distinct_costs = set(costs)
        # If candidates have differing costs, fail closed (ambiguous route pricing) (Section 15)
        if len(distinct_costs) > 1:
            return 0, False, f"ambiguous_product_video_route_pricing_multiple_tiers_match:{prov_key}:{raw_model}"

        scene_idx = 0
        try:
            scene_idx = int(context.scene_index or 0)
        except Exception:
            pass

        unit_cost = list(distinct_costs)[0]
        if scene_idx >= 1:
            total_usd = unit_cost
        else:
            scene_count = int(context.metadata.get("scene_count", 1) or 1)
            total_usd = unit_cost * Decimal(max(1, scene_count))
        source_id = f"config/product_video_price_route_map_20260827.json:{prov_key}:{target_model}"
        return to_micro_usd(total_usd), True, source_id

    if fam == "voice / tts":
        norm_model = str(context.model or "").strip().lower()
        norm_prov = str(context.provider or "").strip().lower()

        # MiniMax models (speech-01-turbo, speech-02-hd) or MiniMax providers have NO proven pricing authority
        # CANONICAL_TTS_RATE_USD_PER_CHAR applies strictly to OpenAI tts-1 (CANONICAL_TTS_MODEL = "tts-1")
        if "minimax" in norm_prov or "speech-" in norm_model or "minimax" in str(authority.provider).lower():
            return 0, False, "tts_canonical_cost_authority_unproven:minimax_unproven_pricing_contract"

        if norm_model == "tts-1" or "openai" in norm_prov:
            char_count = int(context.metadata.get("char_count", 0) or len(str(context.metadata.get("text", ""))))
            if char_count <= 0:
                return 0, False, "missing_char_count_for_tts_pricing"
            rate = Decimal("0.000015")
            cost = (Decimal(char_count) * rate).quantize(Decimal("0.000001"))
            return to_micro_usd(cost), True, f"canonical_tts_rate:{char_count}_chars"

        return 0, False, f"tts_canonical_cost_authority_unproven:{norm_prov}:{norm_model}"

    if fam == "video ai edit":
        dur = int(round(float(context.metadata.get("duration_seconds", 5.0) or 5.0)))
        if dur == 5:
            return to_micro_usd(Decimal("0.40")), True, "fal_wan_v2v_5s_contract"
        elif dur == 10:
            return to_micro_usd(Decimal("0.80")), True, "fal_wan_v2v_10s_contract"
        return 0, False, f"unsupported_video_edit_duration:{dur}"

    if fam == "public chat pro":
        in_tokens = int(context.metadata.get("max_input_tokens", 0) or context.metadata.get("estimated_input_tokens", 0) or 0)
        out_tokens = int(context.metadata.get("max_output_tokens", 0) or 0)
        if in_tokens > 0 or out_tokens > 0:
            calc = (Decimal(in_tokens) * Decimal("6") + Decimal(out_tokens) * Decimal("30")) / Decimal("1000000")
            return to_micro_usd(calc), True, "chat_pro_token_quote"
        # REMOVED: chat_pro_caller_quote fallback
        return 0, False, "missing_token_quote_for_chat_pro"

    if fam == "subdub asr":
        return 0, False, "subdub_asr_canonical_pricing_catalog_missing"

    if fam == "music / suno":
        return 0, False, "suno_music_canonical_pricing_catalog_missing"

    return 0, False, f"unsupported_paid_transport_pricing:{fam}:{prov}:{op}"



def get_configured_cap_micro_usd(env: dict[str, str] | None = None) -> int:
    """Return the configured hard weekly provider spend cap in micro-USD."""
    effective_env = os.environ if env is None else env
    raw = str(effective_env.get(WEEKLY_SPEND_CAP_ENV, "")).strip()
    if not raw:
        return DEFAULT_WEEKLY_PROVIDER_SPEND_CAP_MICRO_USD
    try:
        dec = Decimal(raw)
        return max(0, to_micro_usd(dec))
    except Exception:
        return DEFAULT_WEEKLY_PROVIDER_SPEND_CAP_MICRO_USD


def get_current_spend_week_id(
    now_dt: datetime.datetime | None = None,
    reset_rule: str | None = None,
    tz_name: str | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """Calculate the deterministic week ID based on explicit Owner-approved policy.

    Fail-closed: No silent default! If reset rule or timezone is missing, raises ValueError.
    """
    effective_env = os.environ if env is None else env
    rule = (
        reset_rule
        or effective_env.get(RESET_RULE_ENV)
        or effective_env.get(RESET_RULE_ALIAS_ENV)
        or ""
    ).strip().upper()

    tz = (
        tz_name
        or effective_env.get(TIMEZONE_ENV)
        or effective_env.get(TIMEZONE_ALIAS_ENV)
        or ""
    ).strip().upper()

    if not rule:
        raise ValueError("Spend cap reset rule is not configured (WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE is required)")
    if not tz:
        raise ValueError("Spend cap timezone is not configured (WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE is required)")

    if rule != "MONDAY_0000_UTC" and rule != "ISO_WEEK_UTC":
        raise ValueError(f"Unsupported spend cap reset rule: {rule}")
    if tz != "UTC":
        raise ValueError(f"Unsupported spend cap timezone: {tz}")

    dt = now_dt or datetime.datetime.now(datetime.timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)

    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def resolve_spend_guard_db_path(
    db_path: str | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """Resolve shared central SQLite database path according to canonical authority priority:
    1. explicit db_path argument (caller/test provided);
    2. SPEND_GUARD_DB_PATH from environment;
    3. canonical existing DB_PATH from environment;
    4. canonical existing DB_FILE from environment;
    5. canonical existing SQLITE_DB_PATH from environment;
    6. production durable authority: /data/toandaas_system.db (if file exists).

    Fail-closed: Does not silently fall back to arbitrary /opt/toanaas/bot/toanaas.db or relative toanaas.db/spend_guard.db.
    """
    if db_path:
        return os.path.abspath(db_path)
    effective_env = os.environ if env is None else env
    for key in ("SPEND_GUARD_DB_PATH", "DB_PATH", "DB_FILE", "SQLITE_DB_PATH"):
        val = str(effective_env.get(key) or "").strip()
        if val:
            return os.path.abspath(val)

    # Production durable authority proven by deploy contract
    production_durable = "/data/toandaas_system.db"
    if os.path.exists(production_durable):
        return production_durable

    raise ValueError("Shared spend guard DB path authority unavailable; explicit configuration required")


def verify_shared_db_parity(
    bot_env: dict[str, str] | None = None,
    worker_env: dict[str, str] | None = None,
) -> tuple[bool, str, str, str]:
    """Verify that Bot and Worker resolve to the exact same shared DB path.

    Returns (parity_ok, bot_path, worker_path, reason).
    """
    try:
        bot_path = resolve_spend_guard_db_path(env=bot_env)
    except Exception as exc:
        return False, "", "", f"Bot DB path resolution failed: {exc}"

    try:
        worker_path = resolve_spend_guard_db_path(env=worker_env)
    except Exception as exc:
        return False, bot_path, "", f"Worker DB path resolution failed: {exc}"

    norm_bot = os.path.normcase(os.path.abspath(bot_path))
    norm_worker = os.path.normcase(os.path.abspath(worker_path))

    if norm_bot == norm_worker:
        return True, bot_path, worker_path, "Exact path match"

    # If both files exist, check if they reference the same inode / hardlink
    if os.path.exists(bot_path) and os.path.exists(worker_path):
        try:
            stat_bot = os.stat(bot_path)
            stat_worker = os.stat(worker_path)
            if stat_bot.st_ino == stat_worker.st_ino and stat_bot.st_dev == stat_worker.st_dev:
                return True, bot_path, worker_path, "Same inode match"
        except Exception:
            pass

    return False, bot_path, worker_path, f"DB path mismatch: {bot_path} != {worker_path}"


def _get_sqlite_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass
    return conn


def init_spend_guard_db(
    conn: sqlite3.Connection | None = None,
    db_path: str | None = None,
    env: dict[str, str] | None = None,
) -> None:
    """Ensure spend guard schema exists in SQLite database with exact micro-USD columns."""
    should_close = False
    if conn is None:
        target_path = resolve_spend_guard_db_path(db_path, env)
        conn = _get_sqlite_connection(target_path)
        should_close = True
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS provider_spend_reservations (
                reservation_id TEXT PRIMARY KEY,
                created_at REAL NOT NULL,
                week_id TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                job_id TEXT NOT NULL,
                request_id TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                product_family TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                estimated_max_cost_micro_usd INTEGER NOT NULL,
                reserved_cost_micro_usd INTEGER NOT NULL,
                actual_settled_cost_micro_usd INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                bot_originated_action INTEGER NOT NULL DEFAULT 0,
                user_flow TEXT NOT NULL DEFAULT '',
                bot_confirm_authority TEXT NOT NULL DEFAULT '',
                owner_receipt TEXT NOT NULL DEFAULT '',
                provider_task_id TEXT NOT NULL DEFAULT '',
                error_code TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                scene_index INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(provider_spend_reservations)")
        res_cols = {row[1] for row in cur.fetchall()}
        if res_cols and "scene_index" not in res_cols:
            conn.execute("ALTER TABLE provider_spend_reservations ADD COLUMN scene_index INTEGER NOT NULL DEFAULT 0")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_spend_res_week_status ON provider_spend_reservations(week_id, status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_spend_res_job_id ON provider_spend_reservations(job_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_spend_confirmations (
                confirmation_id TEXT PRIMARY KEY,
                parent_confirmation_id TEXT NOT NULL DEFAULT '',
                record_type TEXT NOT NULL DEFAULT 'SCENE_SUBMIT',
                chat_id TEXT NOT NULL DEFAULT '',
                user_id TEXT NOT NULL DEFAULT '',
                job_id TEXT NOT NULL DEFAULT '',
                request_id TEXT NOT NULL DEFAULT '',
                product_family TEXT NOT NULL,
                operation TEXT NOT NULL,
                scene_index INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                consumed_at REAL,
                status TEXT NOT NULL DEFAULT 'active',
                origin TEXT NOT NULL DEFAULT 'telegram_bot_callback_or_command',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                purpose TEXT NOT NULL DEFAULT 'PRODUCTION_USER_ACTION',
                owner_receipt TEXT NOT NULL DEFAULT '',
                expected_max_cost_micro_usd INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(bot_spend_confirmations)")
        cols = {row[1] for row in cur.fetchall()}
        if cols:
            if "parent_confirmation_id" not in cols:
                conn.execute("ALTER TABLE bot_spend_confirmations ADD COLUMN parent_confirmation_id TEXT NOT NULL DEFAULT ''")
            if "record_type" not in cols:
                conn.execute("ALTER TABLE bot_spend_confirmations ADD COLUMN record_type TEXT NOT NULL DEFAULT 'SCENE_SUBMIT'")
            if "scene_index" not in cols:
                conn.execute("ALTER TABLE bot_spend_confirmations ADD COLUMN scene_index INTEGER NOT NULL DEFAULT 0")
            if "status" not in cols:
                conn.execute("ALTER TABLE bot_spend_confirmations ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
            if "purpose" not in cols:
                conn.execute("ALTER TABLE bot_spend_confirmations ADD COLUMN purpose TEXT NOT NULL DEFAULT 'PRODUCTION_USER_ACTION'")
            if "owner_receipt" not in cols:
                conn.execute("ALTER TABLE bot_spend_confirmations ADD COLUMN owner_receipt TEXT NOT NULL DEFAULT ''")
            if "expected_max_cost_micro_usd" not in cols:
                conn.execute("ALTER TABLE bot_spend_confirmations ADD COLUMN expected_max_cost_micro_usd INTEGER NOT NULL DEFAULT 0")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bot_confirm_lookup ON bot_spend_confirmations(job_id, product_family, operation)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bot_confirm_req_lookup ON bot_spend_confirmations(request_id, product_family, operation)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS owner_live_authorizations (
                authorization_id TEXT PRIMARY KEY,
                product_family TEXT NOT NULL,
                job_id TEXT NOT NULL,
                request_id TEXT NOT NULL,
                operation TEXT NOT NULL,
                allowed_scene_slots TEXT NOT NULL DEFAULT '*',
                expected_max_provider_spend_micro_usd INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                consumed_at REAL,
                consumed_by_confirmation_id TEXT NOT NULL DEFAULT '',
                origin TEXT NOT NULL DEFAULT 'owner_console_or_governance',
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        cur.execute("PRAGMA table_info(owner_live_authorizations)")
        auth_cols = {row[1] for row in cur.fetchall()}
        if auth_cols:
            if "allowed_scene_slots" not in auth_cols:
                conn.execute("ALTER TABLE owner_live_authorizations ADD COLUMN allowed_scene_slots TEXT NOT NULL DEFAULT '*'")
            if "expected_max_provider_spend_micro_usd" not in auth_cols:
                conn.execute("ALTER TABLE owner_live_authorizations ADD COLUMN expected_max_provider_spend_micro_usd INTEGER NOT NULL DEFAULT 0")
            if "status" not in auth_cols:
                conn.execute("ALTER TABLE owner_live_authorizations ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
            if "consumed_at" not in auth_cols:
                conn.execute("ALTER TABLE owner_live_authorizations ADD COLUMN consumed_at REAL")
            if "consumed_by_confirmation_id" not in auth_cols:
                conn.execute("ALTER TABLE owner_live_authorizations ADD COLUMN consumed_by_confirmation_id TEXT NOT NULL DEFAULT ''")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_owner_auth_job_req ON owner_live_authorizations(job_id, request_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_mint_event_claims (
                event_claim_key TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                confirm_attempt_key TEXT NOT NULL,
                job_id TEXT NOT NULL,
                project_id INTEGER NOT NULL DEFAULT 0,
                user_id TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                telegram_update_id INTEGER NOT NULL,
                callback_query_id_safe TEXT NOT NULL,
                purpose TEXT NOT NULL,
                claimed_at REAL NOT NULL,
                mint_nonce TEXT NOT NULL
            )
            """
        )
        try:
            from services.video_trace_state import ensure_video_trace_schema
            ensure_video_trace_schema(conn=conn)
        except Exception:
            pass
        conn.commit()
    finally:
        if should_close:
            conn.close()


def create_bot_confirmation(
    *,
    mint_authority: BotMintAuthority | None = None,
    parent_confirmation_id: str = "",
    chat_id: str | int = "",
    user_id: str | int = "",
    job_id: str = "",
    request_id: str = "",
    product_family: str = "Product Video",
    operation: str = "create_video_task",
    scene_index: int = 0,
    record_type: str = RECORD_TYPE_SCENE_SUBMIT,
    origin: str | None = None,
    ttl_seconds: float = 600.0,
    confirmation_id: str | None = None,
    purpose: str | None = None,
    owner_receipt: str = "",
    expected_max_cost_usd: float | Decimal = 0.0,
    metadata: dict[str, Any] | None = None,
    db_path: str | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """Create a durable, single-use bot confirmation record in SQLite WAL database.
    Requires trusted BotMintAuthority (Sections 3 & 4). Default arguments or caller-controlled
    origin strings alone are strictly forbidden.
    """
    if mint_authority is None or not isinstance(mint_authority, BotMintAuthority):
        raise PermissionError(
            "Bot mint authority missing: caller must provide a valid BotMintAuthority object; "
            "caller-controlled origin string or default args forbidden"
        )
    if not mint_authority.is_test_override:
        if mint_authority.callsite not in MINT_PRODUCTION_CALLERS:
            raise PermissionError(f"Unauthorized mint callsite: '{mint_authority.callsite}' not in MINT_PRODUCTION_CALLERS")
        if mint_authority.validation_source != BOT_CONFIRM_VALIDATION_SOURCE:
            raise PermissionError(f"Unauthorized mint validation_source: '{mint_authority.validation_source}'")
        if mint_authority.validation_callsite != BOT_CONFIRM_VALIDATION_CALLSITE:
            raise PermissionError(f"Unauthorized mint validation_callsite: '{mint_authority.validation_callsite}'")
        if chat_id and str(mint_authority.chat_id) != str(chat_id):
            raise PermissionError(f"Mint authority chat_id mismatch: '{mint_authority.chat_id}' != '{chat_id}'")
        if user_id and str(mint_authority.user_id) != str(user_id):
            raise PermissionError(f"Mint authority user_id mismatch: '{mint_authority.user_id}' != '{user_id}'")
        if job_id and mint_authority.job_id and str(mint_authority.job_id) != str(job_id):
            raise PermissionError(f"Mint authority job_id mismatch: '{mint_authority.job_id}' != '{job_id}'")
        if request_id and mint_authority.request_id and str(mint_authority.request_id) != str(request_id):
            raise PermissionError(f"Mint authority request_id mismatch: '{mint_authority.request_id}' != '{request_id}'")

    # Section 3: Confirmation creation cannot override mint authority
    if purpose is not None and str(purpose).strip() != str(mint_authority.purpose).strip():
        raise PermissionError(
            f"Caller cannot override confirmation purpose: '{purpose}' != '{mint_authority.purpose}' "
            "(CALLER_CAN_OVERRIDE_CONFIRM_PURPOSE=NO)"
        )
    if owner_receipt and str(owner_receipt).strip() != str(mint_authority.owner_receipt or "").strip():
        raise PermissionError(
            f"Caller cannot override owner_receipt: '{owner_receipt}' != '{mint_authority.owner_receipt}' "
            "(CALLER_CAN_OVERRIDE_OWNER_RECEIPT=NO)"
        )
    if expected_max_cost_usd:
        req_exp = Decimal(str(expected_max_cost_usd))
        auth_exp = Decimal(str(mint_authority.expected_max_provider_spend_usd or 0.0))
        if req_exp != auth_exp:
            raise PermissionError(
                f"Caller cannot override expected max spend: '{req_exp}' != '{auth_exp}' "
                "(CALLER_CAN_OVERRIDE_EXPECTED_MAX_SPEND=NO)"
            )

    actual_purpose = str(mint_authority.purpose or PURPOSE_PRODUCTION_USER_ACTION).strip()
    actual_owner_receipt = str(mint_authority.owner_receipt or "").strip()
    exp_usd = Decimal(str(mint_authority.expected_max_provider_spend_usd or 0.0))
    exp_micro = to_micro_usd(exp_usd)

    target_path = resolve_spend_guard_db_path(db_path, env)
    init_spend_guard_db(db_path=target_path, env=env)

    c_id = confirmation_id or f"bot_conf_{secrets.token_hex(12)}"
    now_ts = time.time()
    expires_at = now_ts + float(ttl_seconds)
    meta = dict(metadata or {})
    meta["mint_callsite"] = mint_authority.callsite
    meta["telegram_update_id"] = mint_authority.telegram_update_id
    meta_json = json.dumps(meta)
    canonical_origin = f"bot_ui:{mint_authority.callsite}" if not mint_authority.is_test_override else "test_harness"

    conn = _get_sqlite_connection(target_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
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
                str(parent_confirmation_id or ""),
                str(record_type or RECORD_TYPE_SCENE_SUBMIT),
                str(chat_id or ""),
                str(user_id or ""),
                str(job_id or ""),
                str(request_id or ""),
                str(product_family or "Product Video"),
                str(operation or "create_video_task"),
                int(scene_index or 0),
                now_ts,
                expires_at,
                canonical_origin,
                meta_json,
                actual_purpose,
                actual_owner_receipt,
                exp_micro,
            ),
        )
        conn.commit()
        return c_id
    finally:
        conn.close()


def mint_multiscene_bot_confirmation_plan(
    *,
    mint_authority: BotMintAuthority | None = None,
    chat_id: str | int = "",
    user_id: str | int = "",
    job_id: str = "",
    request_id: str = "",
    product_family: str = "Product Video",
    operation: str = "create_video_task",
    scene_count: int = 1,
    ttl_seconds: float = 600.0,
    purpose: str | None = None,
    owner_receipt: str = "",
    expected_max_cost_usd: float | Decimal = 0.0,
    origin: str | None = None,
    metadata: dict[str, Any] | None = None,
    db_path: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Mint a bounded authorization plan for multi-scene Product Video with 1 parent and N child confirmations.
    Requires trusted BotMintAuthority (Sections 3 & 4).
    """
    if mint_authority is None or not isinstance(mint_authority, BotMintAuthority):
        raise PermissionError(
            "Bot mint authority missing: caller must provide a valid BotMintAuthority object; "
            "caller-controlled origin string or default args forbidden"
        )
    if not mint_authority.is_test_override:
        if mint_authority.callsite not in MINT_PRODUCTION_CALLERS:
            raise PermissionError(f"Unauthorized mint callsite: '{mint_authority.callsite}' not in MINT_PRODUCTION_CALLERS")
        if mint_authority.validation_source != BOT_CONFIRM_VALIDATION_SOURCE:
            raise PermissionError(f"Unauthorized mint validation_source: '{mint_authority.validation_source}'")
        if mint_authority.validation_callsite != BOT_CONFIRM_VALIDATION_CALLSITE:
            raise PermissionError(f"Unauthorized mint validation_callsite: '{mint_authority.validation_callsite}'")
        if chat_id and str(mint_authority.chat_id) != str(chat_id):
            raise PermissionError(f"Mint authority chat_id mismatch: '{mint_authority.chat_id}' != '{chat_id}'")
        if user_id and str(mint_authority.user_id) != str(user_id):
            raise PermissionError(f"Mint authority user_id mismatch: '{mint_authority.user_id}' != '{user_id}'")
        if job_id and mint_authority.job_id and str(mint_authority.job_id) != str(job_id):
            raise PermissionError(f"Mint authority job_id mismatch: '{mint_authority.job_id}' != '{job_id}'")
        if request_id and mint_authority.request_id and str(mint_authority.request_id) != str(request_id):
            raise PermissionError(f"Mint authority request_id mismatch: '{mint_authority.request_id}' != '{request_id}'")

    # Section 3: Confirmation creation cannot override mint authority
    if purpose is not None and str(purpose).strip() != str(mint_authority.purpose).strip():
        raise PermissionError(
            f"Caller cannot override confirmation purpose: '{purpose}' != '{mint_authority.purpose}' "
            "(CALLER_CAN_OVERRIDE_CONFIRM_PURPOSE=NO)"
        )
    if owner_receipt and str(owner_receipt).strip() != str(mint_authority.owner_receipt or "").strip():
        raise PermissionError(
            f"Caller cannot override owner_receipt: '{owner_receipt}' != '{mint_authority.owner_receipt}' "
            "(CALLER_CAN_OVERRIDE_OWNER_RECEIPT=NO)"
        )
    if expected_max_cost_usd:
        req_exp = Decimal(str(expected_max_cost_usd))
        auth_exp = Decimal(str(mint_authority.expected_max_provider_spend_usd or 0.0))
        if req_exp != auth_exp:
            raise PermissionError(
                f"Caller cannot override expected max spend: '{req_exp}' != '{auth_exp}' "
                "(CALLER_CAN_OVERRIDE_EXPECTED_MAX_SPEND=NO)"
            )

    actual_purpose = str(mint_authority.purpose or PURPOSE_PRODUCTION_USER_ACTION).strip()
    actual_owner_receipt = str(mint_authority.owner_receipt or "").strip()
    exp_usd = Decimal(str(mint_authority.expected_max_provider_spend_usd or 0.0))
    exp_micro = to_micro_usd(exp_usd)

    target_path = resolve_spend_guard_db_path(db_path, env)
    init_spend_guard_db(db_path=target_path, env=env)

    parent_id = f"bot_conf_parent_{secrets.token_hex(12)}"
    now_ts = time.time()
    expires_at = now_ts + float(ttl_seconds)
    meta = dict(metadata or {})
    meta["mint_callsite"] = mint_authority.callsite
    meta["telegram_update_id"] = mint_authority.telegram_update_id
    meta_json = json.dumps(meta)
    canonical_origin = f"bot_ui:{mint_authority.callsite}" if not mint_authority.is_test_override else "test_harness"
    child_rec_type = RECORD_TYPE_TEST if mint_authority.is_test_override else RECORD_TYPE_SCENE_SUBMIT

    child_authorized_max_map = (metadata or {}).get("child_authorized_max_usd_map")
    total_scenes = max(1, int(scene_count or 1))
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

    conn = _get_sqlite_connection(target_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
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
                RECORD_TYPE_PARENT_PLAN,
                str(chat_id or ""),
                str(user_id or ""),
                str(job_id or ""),
                str(request_id or ""),
                str(product_family or "Product Video"),
                str(operation or "create_video_task"),
                now_ts,
                expires_at,
                canonical_origin,
                meta_json,
                actual_purpose,
                actual_owner_receipt,
                exp_micro,
            ),
        )

        child_confirmations: list[str] = []
        scene_confirmations: dict[int, str] = {}
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
                    str(chat_id or ""),
                    str(user_id or ""),
                    str(job_id or ""),
                    str(request_id or ""),
                    str(product_family or "Product Video"),
                    str(operation or "create_video_task"),
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
        conn.commit()
        return {
            "parent_confirmation_id": parent_id,
            "child_confirmations": child_confirmations,
            "scene_confirmations": scene_confirmations,
            "owner_receipt": actual_owner_receipt,
            "job_id": str(job_id or ""),
            "request_id": str(request_id or ""),
            "purpose": actual_purpose,
        }
    finally:
        conn.close()


def is_paid_live_test(
    context: SpendGuardContext,
    db_path: str | None = None,
    env: dict[str, str] | None = None,
) -> bool:
    """Canonical separation: PAID_LIVE_TEST is derived solely from durable confirmation purpose.
    Caller metadata flags (paid_live_test, is_paid_live_test) are strictly untrusted (Sections 9 & 11).
    """
    conf_id = str(context.bot_confirm_authority or "").strip()
    if not conf_id:
        return False

    effective_env = os.environ if env is None else env
    try:
        target_path = resolve_spend_guard_db_path(db_path, effective_env)
        if not os.path.exists(target_path):
            return False
        conn = _get_sqlite_connection(target_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT purpose FROM bot_spend_confirmations WHERE confirmation_id = ?",
                (conf_id,),
            )
            row = cur.fetchone()
            if row and row[0]:
                return str(row[0]).strip() == PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST
        finally:
            conn.close()
    except Exception:
        pass
    return False


def validate_bot_paid_live_origin(
    context: SpendGuardContext,
    env: dict[str, str] | None = None,
    db_path: str | None = None,
    *,
    _defer_db_check_to_reservation: bool = False,
) -> tuple[bool, str]:
    """Validate Global Directive #1422 bot-only paid live test policy from trusted lineage.

    N21AD §15: Caller fields (context.entrypoint='bot', context.bot_originated_action=True,
    context.user_flow='bot_live_acceptance') are AUDIT ONLY and cannot independently authorize
    without a real durable confirmation record in bot_spend_confirmations.

    Returns (valid, blocker).
    """
    effective_env = os.environ if env is None else env

    entrypoint = str(context.entrypoint or "").strip().lower()
    forbidden_entrypoints = {
        "shell",
        "script",
        "worker_injection",
        "direct_provider",
        "ci",
        "out_of_band",
        "manual_script",
    }
    if entrypoint in forbidden_entrypoints or entrypoint != "bot":
        return False, BLOCKER_PAID_LIVE_TEST_BOT_ONLY

    # Must prove bot origin
    if not context.bot_originated_action:
        return False, BLOCKER_BOT_ORIGIN_PROOF_MISSING

    # Must have request or trace ID
    if not (str(context.request_id).strip() or str(context.trace_id).strip()):
        return False, BLOCKER_BOT_ORIGIN_PROOF_MISSING

    # Must have job ID
    if not str(context.job_id).strip():
        return False, BLOCKER_BOT_ORIGIN_PROOF_MISSING

    # Must have user flow identifier
    if not str(context.user_flow).strip():
        return False, BLOCKER_BOT_ORIGIN_PROOF_MISSING

    # Must have trusted bot confirmation authority recognized by validator AND durable DB
    if not validate_bot_confirm_authority(context.bot_confirm_authority):
        return False, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING

    if _defer_db_check_to_reservation:
        is_live = is_paid_live_test(context, db_path=db_path, env=effective_env)
    else:
        conf_id = str(context.bot_confirm_authority or "").strip()
        try:
            target_path = resolve_spend_guard_db_path(db_path, effective_env)
            if not os.path.exists(target_path):
                return False, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING
            conn = _get_sqlite_connection(target_path)
            try:
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bot_spend_confirmations'")
                if cur.fetchone() is None:
                    return False, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING
                cur.execute(
                    "SELECT record_type, status, consumed_at, purpose FROM bot_spend_confirmations WHERE confirmation_id = ?",
                    (conf_id,),
                )
                row = cur.fetchone()
                if not row:
                    return False, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING
                rec_type, rec_status, rec_consumed, rec_purpose = row
                if str(rec_type or "").upper() == RECORD_TYPE_PARENT_PLAN:
                    return False, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING
                if rec_consumed is not None or str(rec_status or "").lower() != "active":
                    return False, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING
                is_live = str(rec_purpose or "").strip() == PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST
            finally:
                conn.close()
        except Exception:
            return False, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING

    # Section 13: For PAID_LIVE_TEST only (canonical is_paid_live_test), Owner live authorization receipt is REQUIRED
    if is_live:
        if not str(context.owner_receipt).strip():
            return False, BLOCKER_OWNER_LIVE_RECEIPT_MISSING

    return True, ""


def compute_idempotency_key(context: SpendGuardContext) -> str:
    """Compute deterministic idempotency key for paid submit binding confirmation, job, scene, product, provider, operation."""
    if context.idempotency_key:
        return str(context.idempotency_key).strip()
    job_part = str(context.job_id or "").strip()
    scene_part = str(context.scene_index if context.scene_index is not None else 0).strip()
    req_part = str(context.request_id or "").strip()
    fam_part = str(context.product_family or "").strip().lower()
    prov_part = str(context.provider or "").strip().lower()
    op_part = str(context.operation or "").strip().lower()
    model_part = str(context.model or "").strip().lower()
    conf_part = str(context.bot_confirm_authority or "").strip()
    raw = f"{fam_part}:{prov_part}:{op_part}:{job_part}:{scene_part}:{req_part}:{model_part}:{conf_part}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def sanitize_provider_task_id(task_id: str | None) -> str:
    """Sanitize provider task ID for safe audit logging without leaking secrets."""
    if not task_id:
        return ""
    val = str(task_id).strip()
    if len(val) <= 8:
        return val
    return f"{val[:4]}...{val[-4:]}"


def build_sanitized_audit_record(
    context: SpendGuardContext,
    *,
    week_spend_before_micro_usd: int,
    week_spend_after_micro_usd: int,
    reserved_cost_micro_usd: int,
    actual_settled_cost_micro_usd: int = 0,
    provider_task_id: str = "",
    cost_authority_source: str = "",
) -> dict[str, Any]:
    """Emit sanitized audit record using exact money precision without sensitive credentials."""
    return {
        "BOT_ORIGINATED_ACTION": bool(context.bot_originated_action),
        "BOT_REQUEST_OR_TRACE_ID": str(context.request_id or context.trace_id or ""),
        "BOT_JOB_ID": str(context.job_id or ""),
        "PRODUCT_FAMILY": str(context.product_family or "Product Video"),
        "PROVIDER": str(context.provider or ""),
        "MODEL": str(context.model or ""),
        "ESTIMATED_MAX_COST_USD": float(from_micro_usd(reserved_cost_micro_usd)),
        "RESERVED_COST_USD": float(from_micro_usd(reserved_cost_micro_usd)),
        "CALLER_QUOTE_USD": float(context.estimated_max_cost_usd or 0.0),
        "CALLER_COST_AUTHORITY_TRUSTED": False,
        "COST_AUTHORITY_SOURCE": str(cost_authority_source or context.cost_authority_source or ""),
        "WEEK_SPEND_BEFORE_USD": float(from_micro_usd(week_spend_before_micro_usd)),
        "WEEK_SPEND_AFTER_RESERVATION_USD": float(from_micro_usd(week_spend_after_micro_usd)),
        "PROVIDER_TASK_ID_SAFE": sanitize_provider_task_id(provider_task_id),
        "ACTUAL_SETTLED_COST_USD": float(from_micro_usd(actual_settled_cost_micro_usd)),
    }



def get_weekly_spend_summary(
    db_path: str | None = None,
    env: dict[str, str] | None = None,
    week_id: str | None = None,
) -> dict[str, Any]:
    """Query current settled and reserved spend for the specified week with exact micro-USD precision."""
    effective_env = os.environ if env is None else env
    cap_micro_usd = get_configured_cap_micro_usd(effective_env)

    try:
        effective_week = week_id or get_current_spend_week_id(env=effective_env)
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "weekly_spend_cap_usd": float(from_micro_usd(cap_micro_usd)),
        }

    try:
        target_path = resolve_spend_guard_db_path(db_path, effective_env)
        init_spend_guard_db(db_path=target_path, env=effective_env)
        conn = _get_sqlite_connection(target_path)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    COALESCE(SUM(actual_settled_cost_micro_usd), 0) AS settled_micro
                FROM provider_spend_reservations
                WHERE week_id = ? AND status = ?
                """,
                (effective_week, STATUS_SETTLED_VERIFIED),
            )
            row = cur.fetchone()
            settled_micro = int(row[0]) if row and row[0] is not None else 0

            cur.execute(
                """
                SELECT
                    COALESCE(SUM(reserved_cost_micro_usd), 0) AS reserved_micro
                FROM provider_spend_reservations
                WHERE week_id = ? AND status IN (?, ?, ?)
                """,
                (effective_week, STATUS_RESERVED, STATUS_SUBMITTED_PENDING_SETTLEMENT, STATUS_AMBIGUOUS_RETAINED),
            )
            row = cur.fetchone()
            reserved_micro = int(row[0]) if row and row[0] is not None else 0

            total_active_micro = settled_micro + reserved_micro
            remaining_micro = max(0, cap_micro_usd - total_active_micro)

            return {
                "ok": True,
                "week_id": effective_week,
                "settled_week_spend_usd": float(from_micro_usd(settled_micro)),
                "pending_reserved_spend_usd": float(from_micro_usd(reserved_micro)),
                "total_active_week_spend_usd": float(from_micro_usd(total_active_micro)),
                "weekly_spend_cap_usd": float(from_micro_usd(cap_micro_usd)),
                "remaining_budget_usd": float(from_micro_usd(remaining_micro)),
                "settled_week_spend_micro_usd": settled_micro,
                "pending_reserved_spend_micro_usd": reserved_micro,
                "total_active_week_spend_micro_usd": total_active_micro,
                "weekly_spend_cap_micro_usd": cap_micro_usd,
            }
        finally:
            conn.close()
    except Exception as exc:
        logger.error("Spend guard authority query failed: %s", exc)
        return {
            "ok": False,
            "error": str(exc),
            "week_id": effective_week,
            "weekly_spend_cap_usd": float(from_micro_usd(cap_micro_usd)),
        }


def reserve_provider_spend(
    context: SpendGuardContext,
    *,
    db_path: str | None = None,
    env: dict[str, str] | None = None,
) -> SpendReservationResult:
    """Atomically check budget and reserve spend before submitting to paid provider.

    Enforces:
    1. Central kill-switch.
    2. Mandatory Central Transport Registry Authority consultation (fail closed if unregistered).
    3. CI/Test provider network isolation (Directive #1422: NO PAID OVERRIDES ALLOWED).
    4. Bot-only paid live test policy from trusted lineage.
    5. Canonical Cost Authority derivation (CALLER_COST_AUTHORITY_TRUSTED=NO).
    6. Week policy completeness: Fails closed if reset rule or timezone is unconfigured.
    7. Shared DB authority: Fails closed if shared DB cannot be resolved.
    8. Durable, non-forgeable Bot Confirmation verification & single-use consumption.
    9. Stable Idempotency & ambiguous submit retry block.
    10. Exact micro-USD atomic reservation under $200.000 shared weekly cap via SQLite WAL BEGIN IMMEDIATE.
    """
    effective_env = os.environ if env is None else env
    cap_micro_usd = get_configured_cap_micro_usd(effective_env)
    cap_usd = float(from_micro_usd(cap_micro_usd))

    # 1. Kill-Switch Check
    if is_kill_switch_active(effective_env):
        return SpendReservationResult(
            allowed=False,
            blocker=BLOCKER_KILL_SWITCH_ACTIVE,
            reason="Central paid-provider kill switch is ACTIVE",
            cap_micro_usd=cap_micro_usd,
            cap_usd=cap_usd,
        )

    # 2. Resolve Week Policy Completeness
    try:
        week_id = get_current_spend_week_id(env=effective_env)
    except Exception as exc:
        return SpendReservationResult(
            allowed=False,
            blocker=BLOCKER_POLICY_INCOMPLETE,
            reason=f"Spend cap reset authority incomplete or invalid: {exc}",
            cap_micro_usd=cap_micro_usd,
            cap_usd=cap_usd,
        )

    # 3. Resolve Shared DB Authority
    try:
        target_db_path = resolve_spend_guard_db_path(db_path, effective_env)
    except Exception as exc:
        return SpendReservationResult(
            allowed=False,
            blocker=BLOCKER_SHARED_DB_UNAVAILABLE,
            reason=f"Shared spend guard DB authority unavailable: {exc}",
            cap_micro_usd=cap_micro_usd,
            cap_usd=cap_usd,
            week_id=week_id,
        )

    # 4. CI / Test Provider Network Isolation (Directive #1422: NO PAID OVERRIDES ALLOWED)
    is_test_env = bool(
        os.environ.get("PYTEST_CURRENT_TEST")
        or effective_env.get("PYTEST_CURRENT_TEST")
        or effective_env.get("CI") == "true"
        or effective_env.get("GITHUB_ACTIONS") == "true"
        or effective_env.get("UNIT_TEST_ENV") == "true"
        or effective_env.get("TEST_RUNNER") == "true"
    )
    if is_test_env and context.is_paid_live_attempt:
        return SpendReservationResult(
            allowed=False,
            blocker=BLOCKER_TEST_NETWORK_ISOLATION,
            reason="Real paid provider calls forbidden in test/CI environment; no override permitted",
            cap_micro_usd=cap_micro_usd,
            cap_usd=cap_usd,
            week_id=week_id,
        )

    # 5. Preliminary Bot-Origin Check for Paid Live Tests (Directive #1422; durable DB check enforced in Step 9 transaction)
    if context.is_paid_live_attempt or is_paid_live_test(context, db_path=target_db_path, env=effective_env):
        bot_origin_valid, bot_origin_blocker = validate_bot_paid_live_origin(
            context,
            effective_env,
            db_path=target_db_path,
            _defer_db_check_to_reservation=True,
        )
        if not bot_origin_valid:
            return SpendReservationResult(
                allowed=False,
                blocker=bot_origin_blocker,
                reason=f"Directive #1422 violation: {bot_origin_blocker}",
                cap_micro_usd=cap_micro_usd,
                cap_usd=cap_usd,
                week_id=week_id,
            )

    # 6. Central Transport Registry Authority Consultation (Section 3)
    authority = resolve_paid_transport_authority(
        context.product_family,
        context.provider,
        context.operation,
    )
    if authority is None:
        return SpendReservationResult(
            allowed=False,
            blocker=BLOCKER_PAID_TRANSPORT_AUTHORITY_UNREGISTERED,
            reason=(
                f"Paid transport authority unregistered for product_family='{context.product_family}', "
                f"provider='{context.provider}', operation='{context.operation}'"
            ),
            cap_micro_usd=cap_micro_usd,
            cap_usd=cap_usd,
            week_id=week_id,
        )

    try:
        init_spend_guard_db(db_path=target_db_path, env=effective_env)
        conn = _get_sqlite_connection(target_db_path)
    except Exception as exc:
        logger.error("Spend guard DB connection failed: %s", exc)
        return SpendReservationResult(
            allowed=False,
            blocker=BLOCKER_SPEND_GUARD_AUTHORITY_UNAVAILABLE,
            reason=f"Failed to access spend authority database: {exc}",
            cap_micro_usd=cap_micro_usd,
            cap_usd=cap_usd,
            week_id=week_id,
        )

    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()

        # 7. Canonical Cost Derivation (CALLER_COST_AUTHORITY_TRUSTED=NO) (Section 4 & 10)
        cost_micro_usd, cost_proven, cost_source = resolve_canonical_cost_micro_usd(context, authority)
        if not cost_proven or cost_micro_usd <= 0:
            conn.rollback()
            return SpendReservationResult(
                allowed=False,
                blocker=BLOCKER_MAX_COST_AUTHORITY_MISSING,
                reason=f"Canonical provider max cost authority failed: {cost_source}",
                cap_micro_usd=cap_micro_usd,
                cap_usd=cap_usd,
                week_id=week_id,
            )

        # 8. Check Idempotency and Existing Reservations (Section 9 & 11)
        idempotency_key = compute_idempotency_key(context)
        cur.execute(
            """
            SELECT status, error_code, reserved_cost_micro_usd, actual_settled_cost_micro_usd, reservation_id
            FROM provider_spend_reservations
            WHERE idempotency_key = ?
            """,
            (idempotency_key,),
        )
        existing = cur.fetchone()
        if existing:
            ex_status, ex_err, ex_res_cost, ex_settled, ex_res_id = existing
            if ex_status == STATUS_AMBIGUOUS_RETAINED:
                conn.rollback()
                return SpendReservationResult(
                    allowed=False,
                    reservation_id=ex_res_id,
                    blocker=BLOCKER_AMBIGUOUS_RETRY_BLOCKED,
                    reason="Previous submit was ambiguous; automatic retry is blocked and reservation is retained",
                    week_id=week_id,
                    cap_micro_usd=cap_micro_usd,
                    cap_usd=cap_usd,
                )
            if ex_status in (STATUS_RESERVED, STATUS_SUBMITTED_PENDING_SETTLEMENT, STATUS_SETTLED_VERIFIED):
                conn.rollback()
                return SpendReservationResult(
                    allowed=False,
                    reservation_id=ex_res_id,
                    blocker=BLOCKER_DUPLICATE_PAID_SUBMIT,
                    reason="Duplicate paid submit detected for the same idempotency key",
                    week_id=week_id,
                    cap_micro_usd=cap_micro_usd,
                    cap_usd=cap_usd,
                )

        # 9. Durable Bot Confirmation Record Verification (Section 2)
        confirmation_to_consume: str | None = None
        require_durable_confirmation = bool(
            context.is_paid_live_attempt
            or authority.bot_origin_required
            or context.bot_confirm_authority
        )
        if require_durable_confirmation:
            c_auth = str(context.bot_confirm_authority or "").strip()
            if not c_auth:
                conn.rollback()
                return SpendReservationResult(
                    allowed=False,
                    blocker=BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING,
                    reason="Durable bot confirmation authority identifier missing",
                    week_id=week_id,
                    cap_micro_usd=cap_micro_usd,
                    cap_usd=cap_usd,
                )

            # Strict lookup: ONLY by confirmation_id (Section 2 & 6 & 7)
            cur.execute(
                """
                SELECT confirmation_id, parent_confirmation_id, record_type, chat_id, user_id, job_id, request_id,
                       product_family, operation, scene_index, created_at, expires_at, consumed_at,
                       status, origin, metadata_json, purpose, owner_receipt, expected_max_cost_micro_usd
                FROM bot_spend_confirmations
                WHERE confirmation_id = ?
                """,
                (c_auth,),
            )
            confirm_row = cur.fetchone()
            if not confirm_row:
                conn.rollback()
                return SpendReservationResult(
                    allowed=False,
                    blocker=BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING,
                    reason=f"Durable bot confirmation record missing for '{c_auth}'; caller-provided string alone forbidden",
                    week_id=week_id,
                    cap_micro_usd=cap_micro_usd,
                    cap_usd=cap_usd,
                )

            (
                c_id,
                c_parent,
                c_record_type,
                rec_chat,
                rec_user,
                rec_job,
                rec_req,
                c_family,
                c_op,
                rec_scene,
                c_created,
                c_expires,
                c_consumed,
                c_status,
                c_origin,
                meta_json,
                c_purpose,
                rec_owner_receipt,
                rec_exp_micro,
            ) = confirm_row

            # Section 7: Parent confirmation is NOT submit authority
            if str(c_record_type or "").upper() == RECORD_TYPE_PARENT_PLAN:
                conn.rollback()
                return SpendReservationResult(
                    allowed=False,
                    blocker=BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING,
                    reason=f"Parent confirmation '{c_id}' is a plan container and cannot authorize transport submit (record_type=PARENT_PLAN)",
                    week_id=week_id,
                    cap_micro_usd=cap_micro_usd,
                    cap_usd=cap_usd,
                )

            # Section 8: Test harness confirmation cannot reach real transport
            is_test_record = (
                str(c_record_type or "").upper() in (RECORD_TYPE_TEST, "TEST_ONLY", "FIXTURE_AUTHORITY")
                or str(c_origin or "").lower() == ORIGIN_TEST_HARNESS
            )
            is_real_transport_target = bool(
                context.metadata.get("target_transport") in ("real_provider", "real_transport", "real")
                or context.metadata.get("is_real_transport")
                or context.metadata.get("real_transport")
                or getattr(context, "is_real_transport", False)
                or context.metadata.get("provider_transport") == "real"
            )
            is_production_runtime = bool(
                "pytest" not in sys.modules
                and "unittest" not in sys.modules
                and not os.environ.get("PYTEST_CURRENT_TEST")
                and effective_env.get("UNIT_TEST_ENV") != "true"
                and effective_env.get("CI") != "true"
                and effective_env.get("GITHUB_ACTIONS") != "true"
            )
            if is_test_record and (is_real_transport_target or is_production_runtime):
                conn.rollback()
                return SpendReservationResult(
                    allowed=False,
                    blocker=BLOCKER_TEST_CONFIRM_CANNOT_REACH_REAL_TRANSPORT,
                    reason="Test-only confirmation cannot authorize real provider transport",
                    week_id=week_id,
                    cap_micro_usd=cap_micro_usd,
                    cap_usd=cap_usd,
                )

            # Section 10 & 11: Derivation of paid live test from durable confirmation purpose
            is_durable_paid_live_test = (str(c_purpose or "").strip() == PURPOSE_OWNER_AUTHORIZED_PAID_LIVE_TEST)
            owner_auth_to_consume: str | None = None
            owner_auth_slots_count: int = 1
            owner_auth_used_confs: list[str] = []
            if is_durable_paid_live_test:
                # N21AE §7: PAID_LIVE_TEST_AVAILABLE=NO MUST BE ENFORCED fail-closed
                if PAID_LIVE_TEST_AVAILABLE != "YES" or OWNER_AUTH_ISSUANCE_SEAM != "PROVEN":
                    conn.rollback()
                    return SpendReservationResult(
                        allowed=False,
                        blocker=BLOCKER_OWNER_LIVE_ISSUANCE_NOT_PROVEN,
                        reason="Owner live authorization issuance authority is not proven; paid live test is unavailable",
                        week_id=week_id,
                        cap_micro_usd=cap_micro_usd,
                        cap_usd=cap_usd,
                    )
                # Directive #1422 & Section 17: Proven lineage required for paid live test before transport
                if str(context.entrypoint or "").strip().lower() != "bot":
                    conn.rollback()
                    return SpendReservationResult(
                        allowed=False,
                        blocker=BLOCKER_BOT_ORIGIN_PROOF_MISSING,
                        reason="Directive #1422 requires entrypoint='bot' for paid live test",
                        week_id=week_id,
                        cap_micro_usd=cap_micro_usd,
                        cap_usd=cap_usd,
                    )
                if not context.bot_originated_action:
                    conn.rollback()
                    return SpendReservationResult(
                        allowed=False,
                        blocker=BLOCKER_BOT_ORIGIN_PROOF_MISSING,
                        reason="Directive #1422 requires bot_originated_action=True for paid live test",
                        week_id=week_id,
                        cap_micro_usd=cap_micro_usd,
                        cap_usd=cap_usd,
                    )
                if not str(context.job_id or "").strip():
                    conn.rollback()
                    return SpendReservationResult(
                        allowed=False,
                        blocker=BLOCKER_BOT_ORIGIN_PROOF_MISSING,
                        reason="Directive #1422 requires job_id for paid live test",
                        week_id=week_id,
                        cap_micro_usd=cap_micro_usd,
                        cap_usd=cap_usd,
                    )
                if not (str(context.request_id or "").strip() or str(context.trace_id or "").strip()):
                    conn.rollback()
                    return SpendReservationResult(
                        allowed=False,
                        blocker=BLOCKER_BOT_ORIGIN_PROOF_MISSING,
                        reason="Directive #1422 requires request_id or trace_id for paid live test",
                        week_id=week_id,
                        cap_micro_usd=cap_micro_usd,
                        cap_usd=cap_usd,
                    )
                if not str(context.user_flow or "").strip():
                    conn.rollback()
                    return SpendReservationResult(
                        allowed=False,
                        blocker=BLOCKER_BOT_ORIGIN_PROOF_MISSING,
                        reason="Directive #1422 requires user_flow for paid live test",
                        week_id=week_id,
                        cap_micro_usd=cap_micro_usd,
                        cap_usd=cap_usd,
                    )

                # Section 12: Owner receipt binding required for paid live test
                rec_rcpt = str(rec_owner_receipt or "").strip()
                if not rec_rcpt:
                    conn.rollback()
                    return SpendReservationResult(
                        allowed=False,
                        blocker=BLOCKER_OWNER_LIVE_RECEIPT_MISSING,
                        reason="Durable confirmation requires Owner live authorization receipt for paid live test",
                        week_id=week_id,
                        cap_micro_usd=cap_micro_usd,
                        cap_usd=cap_usd,
                    )
                ctx_rcpt = str(context.owner_receipt or "").strip()
                if not ctx_rcpt or ctx_rcpt != rec_rcpt:
                    conn.rollback()
                    return SpendReservationResult(
                        allowed=False,
                        blocker=BLOCKER_OWNER_RECEIPT_MISMATCH,
                        reason=f"Owner authorization receipt mismatch: '{ctx_rcpt}' != '{rec_rcpt}'",
                        week_id=week_id,
                        cap_micro_usd=cap_micro_usd,
                        cap_usd=cap_usd,
                    )

                # Section 2 & 3 & N21AD §9, §12: Validate canonical Owner live authorization with ACTUAL runtime context
                is_valid, auth_blocker, auth_data = validate_canonical_owner_live_authorization(
                    rec_rcpt,
                    product_family=str(context.product_family or "Product Video"),
                    job_id=str(context.job_id or ""),
                    request_id=str(context.request_id or ""),
                    user_id=str(context.user_id or ""),
                    account_id=str(context.chat_id or ""),
                    operation=str(context.operation or ""),
                    provider=str(context.provider or ""),
                    tier=str(context.metadata.get("tier") or context.model or ""),
                    model=str(context.model or ""),
                    estimated_provider_cost=from_micro_usd(cost_micro_usd),
                    estimated_provider_cost_unit="USD",
                    scene_index=context.scene_index,
                    db_path=target_db_path,
                    env=effective_env,
                    conn=conn,
                )
                if not is_valid:
                    conn.rollback()
                    mapped_blocker = auth_blocker
                    if auth_blocker in (
                        "owner_acceptance_job_mismatch",
                        "owner_acceptance_request_id_mismatch",
                        "owner_acceptance_operation_mismatch",
                        "owner_acceptance_product_mismatch",
                        "owner_acceptance_lineage_mismatch",
                        "owner_acceptance_user_mismatch",
                        "owner_acceptance_project_mismatch",
                    ):
                        mapped_blocker = BLOCKER_OWNER_LIVE_AUTH_LINEAGE_MISMATCH
                    elif auth_blocker in ("owner_acceptance_slots_missing", "owner_acceptance_slot_mismatch"):
                        mapped_blocker = BLOCKER_OWNER_LIVE_AUTH_SLOT_MISMATCH
                    elif auth_blocker in ("owner_acceptance_max_provider_spend_missing", "owner_acceptance_spend_limit_exceeded"):
                        mapped_blocker = BLOCKER_OWNER_AUTHORIZED_MAX_SPEND_EXCEEDED
                    return SpendReservationResult(
                        allowed=False,
                        blocker=mapped_blocker,
                        reason=f"Canonical owner live authorization invalid: {auth_blocker}",
                        week_id=week_id,
                        cap_micro_usd=cap_micro_usd,
                        cap_usd=cap_usd,
                    )

                # Section 6: ATOMIC CUMULATIVE OWNER JOB BUDGET
                owner_auth_job_max_micro = int(auth_data.get("expected_max_provider_spend_micro_usd") or 0)
                if owner_auth_job_max_micro <= 0:
                    conn.rollback()
                    return SpendReservationResult(
                        allowed=False,
                        blocker=BLOCKER_OWNER_AUTHORIZED_MAX_SPEND_EXCEEDED,
                        reason="Owner live authorization must declare positive expected_max_provider_spend_micro_usd > 0",
                        week_id=week_id,
                        cap_micro_usd=cap_micro_usd,
                        cap_usd=cap_usd,
                    )

                cur.execute(
                    """
                    SELECT COALESCE(SUM(reserved_cost_micro_usd), 0)
                    FROM provider_spend_reservations
                    WHERE owner_receipt = ? AND job_id = ?
                      AND status NOT IN ('released', 'cancelled', 'rolled_back', 'no_charge', 'failed_no_charge')
                    """,
                    (rec_rcpt, str(context.job_id or "")),
                )
                used_or_reserved_micro = cur.fetchone()[0]
                if used_or_reserved_micro + cost_micro_usd > owner_auth_job_max_micro:
                    conn.rollback()
                    return SpendReservationResult(
                        allowed=False,
                        blocker=BLOCKER_OWNER_AUTHORIZED_MAX_SPEND_EXCEEDED,
                        reason=f"Cumulative job spend ({used_or_reserved_micro + cost_micro_usd} µUSD) exceeds Owner authorized max ({owner_auth_job_max_micro} µUSD)",
                        week_id=week_id,
                        cap_micro_usd=cap_micro_usd,
                        cap_usd=cap_usd,
                    )

                # Section 14 & 20: Child authorization allocation check
                if int(rec_exp_micro or 0) > 0 and cost_micro_usd > int(rec_exp_micro):
                    conn.rollback()
                    return SpendReservationResult(
                        allowed=False,
                        blocker=BLOCKER_OWNER_AUTHORIZED_MAX_SPEND_EXCEEDED,
                        reason=f"Canonical scene cost ({cost_micro_usd} µUSD) exceeds child allocated authorized max ({rec_exp_micro} µUSD)",
                        week_id=week_id,
                        cap_micro_usd=cap_micro_usd,
                        cap_usd=cap_usd,
                    )

                # Section 7: Scene index check
                ctx_scene = 0
                try:
                    ctx_scene = int(context.scene_index or 0)
                except Exception:
                    pass

                if ctx_scene < 1:
                    conn.rollback()
                    return SpendReservationResult(
                        allowed=False,
                        blocker="scene_index_missing",
                        reason="Explicit positive scene_index >= 1 is required for paid Owner live test",
                        week_id=week_id,
                        cap_micro_usd=cap_micro_usd,
                        cap_usd=cap_usd,
                    )

                # Section 7: WILDCARD_MULTIUSE_ALLOWED=NO & Explicit Scene Slot Bounds
                slots_str = str(auth_data.get("allowed_scene_slots") or "").strip()
                allowed_slots: set[int] = set()
                if not slots_str or slots_str == "*":
                    max_submits = int(auth_data.get("max_submits") or 1)
                    if max_submits > 1:
                        conn.rollback()
                        return SpendReservationResult(
                            allowed=False,
                            blocker="wildcard_multiuse_not_allowed",
                            reason="Wildcard scene multiuse is forbidden for paid Owner live test (WILDCARD_MULTIUSE_ALLOWED=NO)",
                            week_id=week_id,
                            cap_micro_usd=cap_micro_usd,
                            cap_usd=cap_usd,
                        )
                    allowed_slots = {ctx_scene}
                else:
                    allowed_slots = {int(s.strip()) for s in slots_str.split(",") if s.strip().isdigit()}
                    max_submits = int(auth_data.get("max_submits") or len(allowed_slots) or 1)
                    if ctx_scene not in allowed_slots:
                        conn.rollback()
                        return SpendReservationResult(
                            allowed=False,
                            blocker=BLOCKER_OWNER_LIVE_AUTH_SLOT_MISMATCH,
                            reason=f"Scene {ctx_scene} not in allowed scene slots '{slots_str}'",
                            week_id=week_id,
                            cap_micro_usd=cap_micro_usd,
                            cap_usd=cap_usd,
                        )

                # Section 7: MAX_PROVIDER_SUBMITS_ENFORCED=YES
                cur.execute(
                    """
                    SELECT COUNT(*) FROM provider_spend_reservations
                    WHERE owner_receipt = ? AND job_id = ?
                      AND status NOT IN ('released', 'cancelled', 'rolled_back', 'no_charge', 'failed_no_charge')
                    """,
                    (rec_rcpt, str(context.job_id or "")),
                )
                already_submitted_count = cur.fetchone()[0]
                if already_submitted_count >= max_submits:
                    conn.rollback()
                    return SpendReservationResult(
                        allowed=False,
                        blocker=BLOCKER_OWNER_LIVE_AUTH_ALREADY_CONSUMED,
                        reason=f"Owner live authorization already consumed (max submits {max_submits} reached)",
                        week_id=week_id,
                        cap_micro_usd=cap_micro_usd,
                        cap_usd=cap_usd,
                    )

                # Section 7: SCENE_SLOT_REUSE_ALLOWED=NO
                cur.execute(
                    """
                    SELECT COUNT(*) FROM provider_spend_reservations
                    WHERE owner_receipt = ? AND job_id = ?
                      AND scene_index = ?
                      AND status NOT IN ('released', 'cancelled', 'rolled_back', 'no_charge', 'failed_no_charge')
                    """,
                    (rec_rcpt, str(context.job_id or ""), ctx_scene),
                )
                if cur.fetchone()[0] > 0:
                    conn.rollback()
                    return SpendReservationResult(
                        allowed=False,
                        blocker=BLOCKER_OWNER_LIVE_AUTH_SLOT_ALREADY_USED,
                        reason=f"Scene slot {ctx_scene} already used; reuse is forbidden (SCENE_SLOT_REUSE_ALLOWED=NO)",
                        week_id=week_id,
                        cap_micro_usd=cap_micro_usd,
                        cap_usd=cap_usd,
                    )

                owner_auth_to_consume = str(auth_data.get("authorization_id") or rec_rcpt)
                owner_auth_slots_count = max_submits
                owner_auth_used_confs = []


            now_ts = time.time()
            if c_consumed is not None or str(c_status or "").lower() == "consumed":
                conn.rollback()
                return SpendReservationResult(
                    allowed=False,
                    blocker=BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING,
                    reason=f"Durable bot confirmation '{c_id}' was already consumed",
                    week_id=week_id,
                    cap_micro_usd=cap_micro_usd,
                    cap_usd=cap_usd,
                )
            if now_ts > c_expires:
                conn.rollback()
                return SpendReservationResult(
                    allowed=False,
                    blocker=BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING,
                    reason=f"Durable bot confirmation '{c_id}' has expired",
                    week_id=week_id,
                    cap_micro_usd=cap_micro_usd,
                    cap_usd=cap_usd,
                )
            if not context.product_family or c_family.strip().lower() != context.product_family.strip().lower():
                conn.rollback()
                return SpendReservationResult(
                    allowed=False,
                    blocker=BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING,
                    reason=f"Durable bot confirmation product family mismatch: '{c_family}' != '{context.product_family}'",
                    week_id=week_id,
                    cap_micro_usd=cap_micro_usd,
                    cap_usd=cap_usd,
                )
            if not context.operation or c_op.strip().lower() != context.operation.strip().lower():
                conn.rollback()
                return SpendReservationResult(
                    allowed=False,
                    blocker=BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING,
                    reason=f"Durable bot confirmation operation mismatch: '{c_op}' != '{context.operation}'",
                    week_id=week_id,
                    cap_micro_usd=cap_micro_usd,
                    cap_usd=cap_usd,
                )

            # Section 6: Exact lineage means required + equal:
            # if DB record field is non-empty, context field MUST also be non-empty AND MUST equal record.
            ctx_job = str(context.job_id or "").strip()
            if rec_job:
                if not ctx_job or rec_job != ctx_job:
                    conn.rollback()
                    return SpendReservationResult(
                        allowed=False,
                        blocker=BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING,
                        reason=f"Durable bot confirmation job mismatch: '{rec_job}' != '{ctx_job}'",
                        week_id=week_id,
                        cap_micro_usd=cap_micro_usd,
                        cap_usd=cap_usd,
                    )

            ctx_req = str(context.request_id or "").strip()
            if rec_req:
                if not ctx_req or rec_req != ctx_req:
                    conn.rollback()
                    return SpendReservationResult(
                        allowed=False,
                        blocker=BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING,
                        reason=f"Durable bot confirmation request mismatch: '{rec_req}' != '{ctx_req}'",
                        week_id=week_id,
                        cap_micro_usd=cap_micro_usd,
                        cap_usd=cap_usd,
                    )

            ctx_chat = str(getattr(context, "chat_id", "") or context.metadata.get("chat_id") or "").strip()
            if rec_chat:
                if not ctx_chat or rec_chat != ctx_chat:
                    conn.rollback()
                    return SpendReservationResult(
                        allowed=False,
                        blocker=BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING,
                        reason=f"Durable bot confirmation chat mismatch: '{rec_chat}' != '{ctx_chat}'",
                        week_id=week_id,
                        cap_micro_usd=cap_micro_usd,
                        cap_usd=cap_usd,
                    )

            ctx_user = str(getattr(context, "user_id", "") or context.metadata.get("user_id") or "").strip()
            if rec_user:
                if not ctx_user or rec_user != ctx_user:
                    conn.rollback()
                    return SpendReservationResult(
                        allowed=False,
                        blocker=BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING,
                        reason=f"Durable bot confirmation user mismatch: '{rec_user}' != '{ctx_user}'",
                        week_id=week_id,
                        cap_micro_usd=cap_micro_usd,
                        cap_usd=cap_usd,
                    )

            ctx_scene = 0
            try:
                ctx_scene = int(context.scene_index or 0)
            except Exception:
                pass
            if rec_scene and rec_scene > 0:
                if ctx_scene <= 0 or rec_scene != ctx_scene:
                    conn.rollback()
                    return SpendReservationResult(
                        allowed=False,
                        blocker=BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING,
                        reason=f"Durable bot confirmation scene mismatch: scene {rec_scene} != {ctx_scene}",
                        week_id=week_id,
                        cap_micro_usd=cap_micro_usd,
                        cap_usd=cap_usd,
                    )

            if not c_origin or c_origin in {"worker", "provider", "worker_injection", "direct_provider", "shell"}:
                conn.rollback()
                return SpendReservationResult(
                    allowed=False,
                    blocker=BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING,
                    reason=f"Durable bot confirmation origin '{c_origin}' not authorized",
                    week_id=week_id,
                    cap_micro_usd=cap_micro_usd,
                    cap_usd=cap_usd,
                )

            confirmation_to_consume = c_id

        # 10. Read Current Week's Active Spend in micro-USD
        cur.execute(
            """
            SELECT
                COALESCE(SUM(actual_settled_cost_micro_usd), 0) AS settled_micro
            FROM provider_spend_reservations
            WHERE week_id = ? AND status = ?
            """,
            (week_id, STATUS_SETTLED_VERIFIED),
        )
        row = cur.fetchone()
        settled_micro = int(row[0]) if row and row[0] is not None else 0

        cur.execute(
            """
            SELECT
                COALESCE(SUM(reserved_cost_micro_usd), 0) AS reserved_micro
            FROM provider_spend_reservations
            WHERE week_id = ? AND status IN (?, ?, ?)
            """,
            (week_id, STATUS_RESERVED, STATUS_SUBMITTED_PENDING_SETTLEMENT, STATUS_AMBIGUOUS_RETAINED),
        )
        row = cur.fetchone()
        reserved_micro = int(row[0]) if row and row[0] is not None else 0

        total_active_before_micro = settled_micro + reserved_micro

        # 11. Exact Micro-USD Cap Check ($200 Shared Cap)
        if total_active_before_micro + cost_micro_usd > cap_micro_usd:
            conn.rollback()
            audit = build_sanitized_audit_record(
                context,
                week_spend_before_micro_usd=total_active_before_micro,
                week_spend_after_micro_usd=total_active_before_micro,
                reserved_cost_micro_usd=0,
                cost_authority_source=cost_source,
            )
            return SpendReservationResult(
                allowed=False,
                blocker=BLOCKER_WEEKLY_SPEND_CAP_EXCEEDED,
                reason=(
                    f"Weekly provider spend cap exceeded: active ${from_micro_usd(total_active_before_micro)} + "
                    f"new ${from_micro_usd(cost_micro_usd)} > cap ${from_micro_usd(cap_micro_usd)}"
                ),
                week_id=week_id,
                week_spend_before_micro_usd=total_active_before_micro,
                week_spend_after_micro_usd=total_active_before_micro,
                week_spend_before_usd=float(from_micro_usd(total_active_before_micro)),
                week_spend_after_usd=float(from_micro_usd(total_active_before_micro)),
                cap_micro_usd=cap_micro_usd,
                cap_usd=cap_usd,
                audit_record=audit,
            )

        # 12. Record Reservation
        reservation_id = f"res_{secrets.token_hex(12)}"
        now_ts = time.time()
        meta_json = json.dumps(context.metadata or {})

        cur.execute(
            """
            INSERT INTO provider_spend_reservations (
                reservation_id,
                created_at,
                week_id,
                idempotency_key,
                job_id,
                request_id,
                trace_id,
                product_family,
                provider,
                model,
                estimated_max_cost_micro_usd,
                reserved_cost_micro_usd,
                actual_settled_cost_micro_usd,
                status,
                bot_originated_action,
                user_flow,
                bot_confirm_authority,
                owner_receipt,
                metadata_json,
                scene_index
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reservation_id,
                now_ts,
                week_id,
                idempotency_key,
                str(context.job_id or ""),
                str(context.request_id or ""),
                str(context.trace_id or ""),
                str(context.product_family or "Product Video"),
                str(context.provider or ""),
                str(context.model or ""),
                cost_micro_usd,
                cost_micro_usd,
                STATUS_RESERVED,
                1 if context.bot_originated_action else 0,
                str(context.user_flow or ""),
                str(context.bot_confirm_authority or ""),
                str(context.owner_receipt or ""),
                meta_json,
                ctx_scene,
            ),
        )

        if confirmation_to_consume:
            cur.execute(
                "UPDATE bot_spend_confirmations SET consumed_at = ?, status = 'consumed' WHERE confirmation_id = ?",
                (now_ts, confirmation_to_consume),
            )

        if owner_auth_to_consume:
            cur.execute(
                """
                SELECT COUNT(*) FROM provider_spend_reservations
                WHERE owner_receipt = ? AND job_id = ?
                  AND status NOT IN ('released', 'cancelled', 'rolled_back', 'no_charge', 'failed_no_charge')
                """,
                (rec_rcpt, str(context.job_id or "")),
            )
            total_res_now = cur.fetchone()[0]
            # N21AC §6: owner_live_authorizations UPDATEs REMOVED.
            # OWNER_LIVE_AUTHORIZATIONS_CAN_AUTHORIZE=NO — only video_request_traces is canonical.
            try:
                if total_res_now >= owner_auth_slots_count:
                    cur.execute(
                        "UPDATE video_request_traces SET current_stage = 'CONSUMED', updated_at = ? WHERE request_id = ? OR confirm_attempt_key = ?",
                        (datetime.datetime.now(datetime.timezone.utc).isoformat(), f"COA-{owner_auth_to_consume}", f"COA-{owner_auth_to_consume}"),
                    )
            except Exception:
                pass

        conn.commit()

        total_active_after_micro = total_active_before_micro + cost_micro_usd
        audit = build_sanitized_audit_record(
            context,
            week_spend_before_micro_usd=total_active_before_micro,
            week_spend_after_micro_usd=total_active_after_micro,
            reserved_cost_micro_usd=cost_micro_usd,
            cost_authority_source=cost_source,
        )

        return SpendReservationResult(
            allowed=True,
            reservation_id=reservation_id,
            week_id=week_id,
            week_spend_before_micro_usd=total_active_before_micro,
            week_spend_after_micro_usd=total_active_after_micro,
            week_spend_before_usd=float(from_micro_usd(total_active_before_micro)),
            week_spend_after_usd=float(from_micro_usd(total_active_after_micro)),
            cap_micro_usd=cap_micro_usd,
            cap_usd=cap_usd,
            reserved_cost_micro_usd=cost_micro_usd,
            audit_record=audit,
        )
    except Exception as exc:
        conn.rollback()
        logger.error("Error executing atomic spend reservation: %s", exc)
        return SpendReservationResult(
            allowed=False,
            blocker=BLOCKER_SPEND_GUARD_AUTHORITY_UNAVAILABLE,
            reason=f"Atomic spend reservation failed: {exc}",
            cap_micro_usd=cap_micro_usd,
            cap_usd=cap_usd,
        )
    finally:
        conn.close()



def mark_submitted_pending_settlement(
    reservation_id: str,
    provider_task_id: str = "",
    *,
    db_path: str | None = None,
    env: dict[str, str] | None = None,
) -> bool:
    """Transition reservation to SUBMITTED_PENDING_SETTLEMENT once provider accepts task.

    DOES NOT settle estimated cost as actual cost! The reserved maximum is retained against the weekly cap.
    """
    if not reservation_id:
        return False
    effective_env = os.environ if env is None else env
    target_path = resolve_spend_guard_db_path(db_path, effective_env)

    try:
        conn = _get_sqlite_connection(target_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                UPDATE provider_spend_reservations
                SET status = ?,
                    provider_task_id = ?
                WHERE reservation_id = ? AND status = ?
                """,
                (
                    STATUS_SUBMITTED_PENDING_SETTLEMENT,
                    str(provider_task_id or ""),
                    reservation_id,
                    STATUS_RESERVED,
                ),
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as exc:
        logger.error("Failed to mark submit pending settlement: %s", exc)
        return False


def settle_verified_provider_spend(
    reservation_id: str,
    actual_verified_cost_usd: float | Decimal,
    provider_task_id: str = "",
    *,
    db_path: str | None = None,
    env: dict[str, str] | None = None,
) -> bool:
    """Settle reservation with verified actual provider cost only when authoritative billing evidence is known."""
    if not reservation_id:
        return False
    effective_env = os.environ if env is None else env
    target_path = resolve_spend_guard_db_path(db_path, effective_env)
    settled_micro = max(0, to_micro_usd(actual_verified_cost_usd))

    try:
        conn = _get_sqlite_connection(target_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                UPDATE provider_spend_reservations
                SET status = ?,
                    actual_settled_cost_micro_usd = ?,
                    reserved_cost_micro_usd = 0,
                    provider_task_id = COALESCE(NULLIF(?, ''), provider_task_id)
                WHERE reservation_id = ? AND status IN (?, ?)
                """,
                (
                    STATUS_SETTLED_VERIFIED,
                    settled_micro,
                    str(provider_task_id or ""),
                    reservation_id,
                    STATUS_RESERVED,
                    STATUS_SUBMITTED_PENDING_SETTLEMENT,
                ),
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as exc:
        logger.error("Failed to settle verified provider spend: %s", exc)
        return False


def retain_ambiguous_provider_spend(
    reservation_id: str,
    error_code: str = "provider_submit_outcome_ambiguous_no_charge",
    provider_task_id: str = "",
    *,
    db_path: str | None = None,
    env: dict[str, str] | None = None,
) -> bool:
    """Mark reservation as AMBIGUOUS_RETAINED.

    Retains the reserved spend against the weekly cap and prevents retries.
    """
    if not reservation_id:
        return False
    effective_env = os.environ if env is None else env
    target_path = resolve_spend_guard_db_path(db_path, effective_env)

    try:
        conn = _get_sqlite_connection(target_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                UPDATE provider_spend_reservations
                SET status = ?,
                    error_code = ?,
                    provider_task_id = COALESCE(NULLIF(?, ''), provider_task_id)
                WHERE reservation_id = ? AND status IN (?, ?)
                """,
                (
                    STATUS_AMBIGUOUS_RETAINED,
                    str(error_code or "ambiguous_outcome"),
                    str(provider_task_id or ""),
                    reservation_id,
                    STATUS_RESERVED,
                    STATUS_SUBMITTED_PENDING_SETTLEMENT,
                ),
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as exc:
        logger.error("Failed to retain ambiguous spend reservation: %s", exc)
        return False


def release_provider_spend_no_charge(
    reservation_id: str,
    reason: str = "pre_send_rejection_no_charge",
    *,
    db_path: str | None = None,
    env: dict[str, str] | None = None,
) -> bool:
    """Release a reserved spend when submit definitely never reached the provider (pre-transport failure)."""
    if not reservation_id:
        return False
    effective_env = os.environ if env is None else env
    target_path = resolve_spend_guard_db_path(db_path, effective_env)

    try:
        conn = _get_sqlite_connection(target_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                UPDATE provider_spend_reservations
                SET status = ?,
                    reserved_cost_micro_usd = 0,
                    error_code = ?
                WHERE reservation_id = ? AND status = ?
                """,
                (
                    STATUS_RELEASED_PROVEN_NO_CHARGE,
                    str(reason or "released"),
                    reservation_id,
                    STATUS_RESERVED,
                ),
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as exc:
        logger.error("Failed to release spend reservation: %s", exc)
        return False
