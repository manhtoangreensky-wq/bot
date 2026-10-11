"""Provider spend guard, weekly budget cap, bot-only paid test origin, and atomic spend reservation.

TASK_ID: P0.PRODUCT_VIDEO_R16_10B14N21P_KEY4U_ACCOUNT_SPEND_FORENSIC_DEFECT_CORRECTION_AND_PAID_SPEND_GUARD_PR
TRACKER: manhtoangreensky-wq/bot#1155
GLOBAL_DIRECTIVE: manhtoangreensky-wq/bot#1422

Invariants:
1. Global Directive #1422: Any paid live test or spend MUST prove Bot origin (BOT_ORIGINATED_ACTION=YES).
   Background, shell, script, direct-provider, worker injection, CI, or out-of-band paid test paths FAIL CLOSED.
2. Hard weekly provider-spend cap ($200.000 USD) authority.
3. Atomic pre-submit spend reservation in SQLite WAL to prevent race-condition overruns.
4. Ambiguous submit safety: Ambiguous outcomes (timeouts, network drops) RETAIN their spend reservation;
   automatic retry, automatic resubmit, and automatic paid fallback are strictly blocked.
5. Paid idempotency guard: Duplicate submits for the same job/scene/request line are blocked.
6. Central paid-provider kill switch blocks new paid submits while preserving read-only status reconciliation.
7. Sanitized audit record emitted for every paid attempt without raw credentials.
"""

from __future__ import annotations

import dataclasses
import datetime
import decimal
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

# Default configurations
DEFAULT_WEEKLY_PROVIDER_SPEND_CAP_USD = 200.000
DEFAULT_RESET_RULE = "MONDAY_0000_UTC"
DEFAULT_TIMEZONE = "UTC"

KILL_SWITCH_ENV = "PAID_PROVIDER_KILL_SWITCH_ACTIVE"
WEEKLY_SPEND_CAP_ENV = "WEEKLY_PROVIDER_SPEND_CAP_USD"
RESET_RULE_ENV = "WEEKLY_PROVIDER_SPEND_CAP_RESET_RULE"
TIMEZONE_ENV = "WEEKLY_PROVIDER_SPEND_CAP_TIMEZONE"
REAL_PROVIDER_CALLS_ENV = "REAL_PROVIDER_CALLS_ALLOWED"

# In-memory kill-switch override (for testing or runtime toggle)
_IN_MEMORY_KILL_SWITCH: bool | None = None

# Status codes
STATUS_RESERVED = "RESERVED"
STATUS_SETTLED = "SETTLED"
STATUS_AMBIGUOUS_RETAINED = "AMBIGUOUS_RETAINED"
STATUS_RELEASED_NO_CHARGE = "RELEASED_NO_CHARGE"
STATUS_BLOCKED = "BLOCKED"

# Error / blocker codes
BLOCKER_KILL_SWITCH_ACTIVE = "paid_provider_kill_switch_active"
BLOCKER_BOT_ORIGIN_PROOF_MISSING = "bot_origin_proof_missing"
BLOCKER_PAID_LIVE_TEST_BOT_ONLY = "paid_live_test_entrypoint_forbidden_bot_only_required"
BLOCKER_WEEKLY_SPEND_CAP_EXCEEDED = "weekly_provider_spend_cap_exceeded"
BLOCKER_SPEND_GUARD_AUTHORITY_UNAVAILABLE = "spend_guard_authority_unavailable"
BLOCKER_DUPLICATE_PAID_SUBMIT = "duplicate_paid_submit_blocked"
BLOCKER_AMBIGUOUS_RETRY_BLOCKED = "ambiguous_submit_retry_blocked"
BLOCKER_AMBIGUOUS_FALLBACK_BLOCKED = "ambiguous_submit_fallback_blocked"
BLOCKER_TEST_NETWORK_ISOLATION = "test_ci_provider_network_isolated_no_real_calls"


@dataclasses.dataclass
class SpendGuardContext:
    job_id: str = ""
    request_id: str = ""
    trace_id: str = ""
    scene_index: int | str = 0
    product_family: str = "Product Video"
    provider: str = ""
    model: str = ""
    estimated_max_cost_usd: float = 0.0
    bot_originated_action: bool = False
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
    week_spend_before_usd: float = 0.0
    week_spend_after_usd: float = 0.0
    cap_usd: float = DEFAULT_WEEKLY_PROVIDER_SPEND_CAP_USD
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


def get_configured_cap_usd(env: dict[str, str] | None = None) -> float:
    """Return the configured hard weekly provider spend cap in USD."""
    effective_env = os.environ if env is None else env
    raw = str(effective_env.get(WEEKLY_SPEND_CAP_ENV, "")).strip()
    if not raw:
        return DEFAULT_WEEKLY_PROVIDER_SPEND_CAP_USD
    try:
        val = float(raw)
        return max(0.0, val)
    except ValueError:
        return DEFAULT_WEEKLY_PROVIDER_SPEND_CAP_USD


def get_current_spend_week_id(
    now_dt: datetime.datetime | None = None,
    reset_rule: str | None = None,
    tz_name: str | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """Calculate the deterministic week ID based on UTC Monday 00:00.

    Fail-closed: If reset_rule is specified but invalid, raises ValueError.
    """
    effective_env = os.environ if env is None else env
    rule = (
        reset_rule
        or effective_env.get(RESET_RULE_ENV)
        or DEFAULT_RESET_RULE
    ).strip().upper()

    tz = (
        tz_name
        or effective_env.get(TIMEZONE_ENV)
        or DEFAULT_TIMEZONE
    ).strip().upper()

    if rule != "MONDAY_0000_UTC" and rule != "ISO_WEEK_UTC":
        raise ValueError(f"Unsupported spend cap reset rule: {rule}")
    if tz != "UTC":
        raise ValueError(f"Unsupported spend cap timezone: {tz}")

    dt = now_dt or datetime.datetime.now(datetime.timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)

    # Calculate Monday of current ISO week
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def resolve_spend_guard_db_path(
    db_path: str | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """Resolve sqlite database path."""
    if db_path:
        return db_path
    effective_env = os.environ if env is None else env
    return (
        effective_env.get("SPEND_GUARD_DB_PATH")
        or effective_env.get("DB_PATH")
        or effective_env.get("SQLITE_DB_PATH")
        or "toanaas.db"
    )


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
) -> None:
    """Ensure spend guard schema exists in SQLite database."""
    should_close = False
    if conn is None:
        target_path = resolve_spend_guard_db_path(db_path)
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
                estimated_max_cost_usd REAL NOT NULL,
                reserved_cost_usd REAL NOT NULL,
                actual_settled_cost_usd REAL NOT NULL DEFAULT 0.0,
                status TEXT NOT NULL,
                bot_originated_action INTEGER NOT NULL DEFAULT 0,
                user_flow TEXT NOT NULL DEFAULT '',
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
    """Validate Global Directive #1422 bot-only paid live test policy.

    Returns (valid, blocker).
    """
    effective_env = os.environ if env is None else env

    # If it is not a paid live attempt, bot-origin check is not required for zero-cost mocks
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

    # If owner acceptance flow, must have owner receipt
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
    week_spend_before_usd: float,
    week_spend_after_usd: float,
    reserved_cost_usd: float,
    actual_settled_cost_usd: float = 0.0,
    provider_task_id: str = "",
) -> dict[str, Any]:
    """Emit sanitized audit record without sensitive credentials."""
    return {
        "BOT_ORIGINATED_ACTION": bool(context.bot_originated_action),
        "BOT_REQUEST_OR_TRACE_ID": str(context.request_id or context.trace_id or ""),
        "BOT_JOB_ID": str(context.job_id or ""),
        "PRODUCT_FAMILY": str(context.product_family or "Product Video"),
        "PROVIDER": str(context.provider or ""),
        "MODEL": str(context.model or ""),
        "ESTIMATED_MAX_COST_USD": round(float(context.estimated_max_cost_usd), 4),
        "RESERVED_COST_USD": round(float(reserved_cost_usd), 4),
        "WEEK_SPEND_BEFORE_USD": round(float(week_spend_before_usd), 4),
        "WEEK_SPEND_AFTER_RESERVATION_USD": round(float(week_spend_after_usd), 4),
        "PROVIDER_TASK_ID_SAFE": sanitize_provider_task_id(provider_task_id),
        "ACTUAL_SETTLED_COST_USD": round(float(actual_settled_cost_usd), 4),
    }


def get_weekly_spend_summary(
    db_path: str | None = None,
    env: dict[str, str] | None = None,
    week_id: str | None = None,
) -> dict[str, Any]:
    """Query current settled and reserved spend for the specified week."""
    effective_env = os.environ if env is None else env
    target_path = resolve_spend_guard_db_path(db_path, effective_env)
    cap_usd = get_configured_cap_usd(effective_env)
    effective_week = week_id or get_current_spend_week_id(env=effective_env)

    try:
        init_spend_guard_db(db_path=target_path)
        conn = _get_sqlite_connection(target_path)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    COALESCE(SUM(actual_settled_cost_usd), 0.0) AS settled_usd
                FROM provider_spend_reservations
                WHERE week_id = ? AND status = ?
                """,
                (effective_week, STATUS_SETTLED),
            )
            row = cur.fetchone()
            settled_usd = float(row[0]) if row and row[0] is not None else 0.0

            cur.execute(
                """
                SELECT
                    COALESCE(SUM(reserved_cost_usd), 0.0) AS reserved_usd
                FROM provider_spend_reservations
                WHERE week_id = ? AND status IN (?, ?)
                """,
                (effective_week, STATUS_RESERVED, STATUS_AMBIGUOUS_RETAINED),
            )
            row = cur.fetchone()
            reserved_usd = float(row[0]) if row and row[0] is not None else 0.0

            total_active_usd = settled_usd + reserved_usd
            remaining_usd = max(0.0, cap_usd - total_active_usd)

            return {
                "ok": True,
                "week_id": effective_week,
                "settled_week_spend_usd": round(settled_usd, 4),
                "pending_reserved_spend_usd": round(reserved_usd, 4),
                "total_active_week_spend_usd": round(total_active_usd, 4),
                "weekly_spend_cap_usd": round(cap_usd, 4),
                "remaining_budget_usd": round(remaining_usd, 4),
            }
        finally:
            conn.close()
    except Exception as exc:
        logger.error("Spend guard authority query failed: %s", exc)
        return {
            "ok": False,
            "error": str(exc),
            "week_id": effective_week,
            "weekly_spend_cap_usd": cap_usd,
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
    2. Global Directive #1422 (Bot-only paid live origin).
    3. Test / CI provider network isolation.
    4. Duplicate / idempotency check.
    5. Ambiguous submit retry block.
    6. Hard weekly $200.000 USD spend cap with atomic SQLite lock.
    """
    effective_env = os.environ if env is None else env
    cap_usd = get_configured_cap_usd(effective_env)

    # 1. Kill-Switch Check
    if is_kill_switch_active(effective_env):
        return SpendReservationResult(
            allowed=False,
            blocker=BLOCKER_KILL_SWITCH_ACTIVE,
            reason="Central paid-provider kill switch is ACTIVE",
            cap_usd=cap_usd,
        )

    # 2. Bot-Origin Check for Paid Live Tests (Directive #1422)
    bot_origin_valid, bot_origin_blocker = validate_bot_paid_live_origin(context, effective_env)
    if not bot_origin_valid:
        return SpendReservationResult(
            allowed=False,
            blocker=bot_origin_blocker,
            reason=f"Directive #1422 violation: {bot_origin_blocker}",
            cap_usd=cap_usd,
        )

    # 3. Test / CI Provider Network Isolation
    # If running inside unit tests or CI, real paid provider calls must be forbidden
    is_test_env = (
        bool(os.environ.get("PYTEST_CURRENT_TEST"))
        or bool(effective_env.get("CI") == "true")
        or bool(effective_env.get("GITHUB_ACTIONS") == "true")
    )
    real_calls_allowed = int(effective_env.get(REAL_PROVIDER_CALLS_ENV, "0") or "0")
    if is_test_env and real_calls_allowed == 0 and context.is_paid_live_attempt:
        return SpendReservationResult(
            allowed=False,
            blocker=BLOCKER_TEST_NETWORK_ISOLATION,
            reason="Real provider calls forbidden in test/CI environment",
            cap_usd=cap_usd,
        )

    # 4. Resolve Week and DB Path
    try:
        week_id = get_current_spend_week_id(env=effective_env)
    except Exception as exc:
        return SpendReservationResult(
            allowed=False,
            blocker=BLOCKER_SPEND_GUARD_AUTHORITY_UNAVAILABLE,
            reason=f"Spend cap reset authority error: {exc}",
            cap_usd=cap_usd,
        )

    target_db_path = resolve_spend_guard_db_path(db_path, effective_env)
    idempotency_key = compute_idempotency_key(context)
    cost = max(0.0, float(context.estimated_max_cost_usd or 0.0))

    try:
        init_spend_guard_db(db_path=target_db_path)
        conn = _get_sqlite_connection(target_db_path)
    except Exception as exc:
        logger.error("Spend guard DB connection failed: %s", exc)
        return SpendReservationResult(
            allowed=False,
            blocker=BLOCKER_SPEND_GUARD_AUTHORITY_UNAVAILABLE,
            reason=f"Failed to access spend authority database: {exc}",
            cap_usd=cap_usd,
        )

    try:
        # Atomic SQLite transaction with IMMEDIATE lock
        conn.execute("BEGIN IMMEDIATE")

        # 5. Check Idempotency and Existing Reservations
        cur = conn.cursor()
        cur.execute(
            """
            SELECT status, error_code, reserved_cost_usd, actual_settled_cost_usd, reservation_id
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
                    cap_usd=cap_usd,
                )
            if ex_status in (STATUS_RESERVED, STATUS_SETTLED):
                conn.rollback()
                return SpendReservationResult(
                    allowed=False,
                    reservation_id=ex_res_id,
                    blocker=BLOCKER_DUPLICATE_PAID_SUBMIT,
                    reason="Duplicate paid submit detected for the same idempotency key",
                    week_id=week_id,
                    cap_usd=cap_usd,
                )

        # 6. Read Current Week's Active Spend
        cur.execute(
            """
            SELECT
                COALESCE(SUM(actual_settled_cost_usd), 0.0) AS settled_usd
            FROM provider_spend_reservations
            WHERE week_id = ? AND status = ?
            """,
            (week_id, STATUS_SETTLED),
        )
        row = cur.fetchone()
        settled_usd = float(row[0]) if row and row[0] is not None else 0.0

        cur.execute(
            """
            SELECT
                COALESCE(SUM(reserved_cost_usd), 0.0) AS reserved_usd
            FROM provider_spend_reservations
            WHERE week_id = ? AND status IN (?, ?)
            """,
            (week_id, STATUS_RESERVED, STATUS_AMBIGUOUS_RETAINED),
        )
        row = cur.fetchone()
        reserved_usd = float(row[0]) if row and row[0] is not None else 0.0

        total_active_before = settled_usd + reserved_usd

        # 7. Check Cap Overrun
        # Must strictly satisfy: total_active_before + cost <= cap_usd
        if total_active_before + cost > cap_usd:
            conn.rollback()
            audit = build_sanitized_audit_record(
                context,
                week_spend_before_usd=total_active_before,
                week_spend_after_usd=total_active_before,
                reserved_cost_usd=0.0,
            )
            return SpendReservationResult(
                allowed=False,
                blocker=BLOCKER_WEEKLY_SPEND_CAP_EXCEEDED,
                reason=(
                    f"Weekly provider spend cap exceeded: active ${total_active_before:.3f} + "
                    f"new ${cost:.3f} > cap ${cap_usd:.3f}"
                ),
                week_id=week_id,
                week_spend_before_usd=total_active_before,
                week_spend_after_usd=total_active_before,
                cap_usd=cap_usd,
                audit_record=audit,
            )

        # 8. Create Reservation
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
                estimated_max_cost_usd,
                reserved_cost_usd,
                actual_settled_cost_usd,
                status,
                bot_originated_action,
                user_flow,
                owner_receipt,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?, ?, ?, ?)
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
                cost,
                cost,
                STATUS_RESERVED,
                1 if context.bot_originated_action else 0,
                str(context.user_flow or ""),
                str(context.owner_receipt or ""),
                meta_json,
            ),
        )
        conn.commit()

        total_active_after = total_active_before + cost
        audit = build_sanitized_audit_record(
            context,
            week_spend_before_usd=total_active_before,
            week_spend_after_usd=total_active_after,
            reserved_cost_usd=cost,
        )

        return SpendReservationResult(
            allowed=True,
            reservation_id=reservation_id,
            week_id=week_id,
            week_spend_before_usd=total_active_before,
            week_spend_after_usd=total_active_after,
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
            cap_usd=cap_usd,
        )
    finally:
        conn.close()


def settle_provider_spend(
    reservation_id: str,
    actual_cost_usd: float,
    provider_task_id: str = "",
    *,
    db_path: str | None = None,
    env: dict[str, str] | None = None,
) -> bool:
    """Settle an active reservation with the actual verified cost from provider."""
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
                    actual_settled_cost_usd = ?,
                    provider_task_id = ?
                WHERE reservation_id = ? AND status = ?
                """,
                (
                    STATUS_SETTLED,
                    max(0.0, float(actual_cost_usd)),
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
        logger.error("Failed to settle provider spend: %s", exc)
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
                    provider_task_id = ?
                WHERE reservation_id = ? AND status = ?
                """,
                (
                    STATUS_AMBIGUOUS_RETAINED,
                    str(error_code or "ambiguous_outcome"),
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
        logger.error("Failed to retain ambiguous spend reservation: %s", exc)
        return False


def release_provider_spend_no_charge(
    reservation_id: str,
    reason: str = "pre_send_rejection_no_charge",
    *,
    db_path: str | None = None,
    env: dict[str, str] | None = None,
) -> bool:
    """Release a reserved spend when submit definitely never reached the provider."""
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
                    reserved_cost_usd = 0.0,
                    error_code = ?
                WHERE reservation_id = ? AND status = ?
                """,
                (
                    STATUS_RELEASED_NO_CHARGE,
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
