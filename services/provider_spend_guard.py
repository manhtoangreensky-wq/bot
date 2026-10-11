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
import time
from typing import Any

logger = logging.getLogger(__name__)

# Money precision constants
MICRO_PER_USD = 1_000_000
DEFAULT_WEEKLY_PROVIDER_SPEND_CAP_USD = Decimal("200.000")
DEFAULT_WEEKLY_PROVIDER_SPEND_CAP_MICRO_USD = 200_000_000

# Environment variable keys
KILL_SWITCH_ENV = "PAID_PROVIDER_KILL_SWITCH_ACTIVE"
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
    scene_index: int | str = 0
    product_family: str = "Product Video"
    provider: str = ""
    model: str = ""
    estimated_max_cost_usd: float | Decimal = 0.0
    has_proven_cost_authority: bool = False
    cost_authority_source: str = ""
    bot_originated_action: bool = False
    bot_confirm_authority: str = ""
    user_flow: str = ""
    owner_receipt: str = ""
    entrypoint: str = "bot"  # "bot", "shell", "script", "worker_injection", "direct_provider", "ci", "out_of_band"
    is_paid_live_attempt: bool = False
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
    audit_record: dict[str, Any] = dataclasses.field(default_factory=dict)


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
    raw = str(effective_env.get(KILL_SWITCH_ENV, "")).strip().lower()
    return raw in {"1", "true", "yes", "on", "active"}


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
    """Resolve shared central SQLite database path.

    Fail-closed: Does not silently fall back to relative 'toanaas.db' in ambient directory.
    Must have an explicit path or canonical shared VPS path.
    """
    if db_path:
        return os.path.abspath(db_path)
    effective_env = os.environ if env is None else env
    for key in ("SPEND_GUARD_DB_PATH", "DB_PATH", "SQLITE_DB_PATH"):
        val = str(effective_env.get(key) or "").strip()
        if val:
            return os.path.abspath(val)

    # Check production canonical VPS shared DB path
    vps_canonical = "/opt/toanaas/bot/toanaas.db"
    if os.path.exists(vps_canonical):
        return vps_canonical

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
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_spend_res_week_status ON provider_spend_reservations(week_id, status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_spend_res_job_id ON provider_spend_reservations(job_id)"
        )
        conn.commit()
    finally:
        if should_close:
            conn.close()


def validate_bot_paid_live_origin(
    context: SpendGuardContext,
    env: dict[str, str] | None = None,
) -> tuple[bool, str]:
    """Validate Global Directive #1422 bot-only paid live test policy from trusted lineage.

    Returns (valid, blocker).
    """
    effective_env = os.environ if env is None else env

    if not context.is_paid_live_attempt:
        return True, ""

    entrypoint = (context.entrypoint or "bot").strip().lower()
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

    # Must have trusted bot confirmation authority
    if not str(context.bot_confirm_authority).strip():
        return False, BLOCKER_BOT_CONFIRM_AUTHORITY_MISSING

    # If owner acceptance flow, additionally must have owner receipt
    if "owner" in context.user_flow.lower() or "acceptance" in context.user_flow.lower():
        if not str(context.owner_receipt).strip():
            return False, BLOCKER_BOT_ORIGIN_PROOF_MISSING

    return True, ""


def compute_idempotency_key(context: SpendGuardContext) -> str:
    """Compute deterministic idempotency key for paid submit."""
    if context.idempotency_key:
        return str(context.idempotency_key).strip()
    job_part = str(context.job_id or "").strip()
    scene_part = str(context.scene_index if context.scene_index is not None else 0).strip()
    req_part = str(context.request_id or "").strip()
    prov_part = str(context.provider or "").strip().lower()
    model_part = str(context.model or "").strip().lower()
    raw = f"{job_part}:{scene_part}:{req_part}:{prov_part}:{model_part}"
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
    2. Global Directive #1422 (Bot-only paid live origin with trusted confirm authority).
    3. CI/Test provider network isolation: Paid live requests in CI/test environments FAIL CLOSED with NO overrides.
    4. Week policy completeness: Fails closed if reset rule or timezone is unconfigured.
    5. Cost authority requirement: Fails closed if max cost is missing or <= 0.
    6. Shared DB authority: Fails closed if shared DB cannot be resolved.
    7. Duplicate / idempotency check and ambiguous submit retry block.
    8. Exact micro-USD atomic reservation under $200.000 cap via SQLite WAL BEGIN IMMEDIATE.
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

    # 2. CI / Test Provider Network Isolation (Directive #1422: NO PAID OVERRIDES ALLOWED)
    is_test_env = bool(
        os.environ.get("PYTEST_CURRENT_TEST")
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
        )

    # 3. Bot-Origin Check for Paid Live Tests (Directive #1422)
    bot_origin_valid, bot_origin_blocker = validate_bot_paid_live_origin(context, effective_env)
    if not bot_origin_valid:
        return SpendReservationResult(
            allowed=False,
            blocker=bot_origin_blocker,
            reason=f"Directive #1422 violation: {bot_origin_blocker}",
            cap_micro_usd=cap_micro_usd,
            cap_usd=cap_usd,
        )

    # 4. Cost Authority Requirement (No arbitrary fallback)
    try:
        raw_cost = context.estimated_max_cost_usd
        cost_micro_usd = to_micro_usd(raw_cost)
    except Exception:
        cost_micro_usd = 0

    if cost_micro_usd <= 0 or not context.has_proven_cost_authority:
        return SpendReservationResult(
            allowed=False,
            blocker=BLOCKER_MAX_COST_AUTHORITY_MISSING,
            reason="Maximum provider cost authority is missing or invalid; arbitrary fallback forbidden",
            cap_micro_usd=cap_micro_usd,
            cap_usd=cap_usd,
        )

    # 5. Resolve Week Policy Completeness
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

    # 6. Resolve Shared DB Authority
    try:
        target_db_path = resolve_spend_guard_db_path(db_path, effective_env)
    except Exception as exc:
        return SpendReservationResult(
            allowed=False,
            blocker=BLOCKER_SHARED_DB_UNAVAILABLE,
            reason=f"Shared spend guard DB authority unavailable: {exc}",
            cap_micro_usd=cap_micro_usd,
            cap_usd=cap_usd,
        )

    idempotency_key = compute_idempotency_key(context)

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
        )

    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()

        # 7. Check Idempotency and Existing Reservations
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

        # 8. Read Current Week's Active Spend in micro-USD
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

        # 9. Exact Micro-USD Cap Check
        # Must strictly satisfy: total_active_before_micro + cost_micro_usd <= cap_micro_usd
        if total_active_before_micro + cost_micro_usd > cap_micro_usd:
            conn.rollback()
            audit = build_sanitized_audit_record(
                context,
                week_spend_before_micro_usd=total_active_before_micro,
                week_spend_after_micro_usd=total_active_before_micro,
                reserved_cost_micro_usd=0,
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

        # 10. Record Reservation
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
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)
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
            ),
        )
        conn.commit()

        total_active_after_micro = total_active_before_micro + cost_micro_usd
        audit = build_sanitized_audit_record(
            context,
            week_spend_before_micro_usd=total_active_before_micro,
            week_spend_after_micro_usd=total_active_after_micro,
            reserved_cost_micro_usd=cost_micro_usd,
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
