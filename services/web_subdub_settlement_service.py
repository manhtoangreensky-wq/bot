"""Canonical Bot Core settlement bridge service for Web SubDub jobs.

Provides an atomic, exactly-once server-to-server financial settlement transaction
between Web SubDub completion and Bot Core SQLite wallet ledger.
"""

from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

LOGGER = logging.getLogger("toanaas.web_subdub_settlement")

CANONICAL_PRODUCT_KEY = "subdub"
CANONICAL_SUBDUB_MODES = frozenset({
    "subtitle_create",
    "subtitle_translate",
    "dub",
    "subtitle_plus_dub",
})

DEFAULT_SUBTITLE_TRANSLATE_RATE_XU = 0.10
DEFAULT_DUB_PRESET_RATE_XU = 0.10
DEFAULT_DUB_CUSTOM_RATE_XU = 0.20


def ensure_web_subdub_settlement_schema(conn: sqlite3.Connection) -> None:
    """Ensure the web_subdub_settlements table and unique indexes exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS web_subdub_settlements (
            id TEXT PRIMARY KEY,
            idempotency_key TEXT UNIQUE NOT NULL,
            web_job_id TEXT UNIQUE NOT NULL,
            web_request_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            subdub_mode TEXT NOT NULL,
            char_count INTEGER NOT NULL,
            amount_xu INTEGER NOT NULL,
            balance_before INTEGER NOT NULL,
            balance_after INTEGER NOT NULL,
            ledger_event_id TEXT,
            output_url TEXT NOT NULL,
            validated_output_metadata TEXT NOT NULL,
            status TEXT NOT NULL,
            settled_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_web_subdub_settlements_job ON web_subdub_settlements(web_job_id)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_web_subdub_settlements_idemp ON web_subdub_settlements(idempotency_key)"
    )


def is_admin_or_owner_user(user_id: Any) -> bool:
    """Check whether a user_id belongs to Admin or Owner."""
    uid = str(user_id or "").strip()
    if not uid:
        return False
    try:
        import bot

        if hasattr(bot, "video_b14_is_admin_or_owner"):
            return bool(bot.video_b14_is_admin_or_owner(uid))
        if hasattr(bot, "is_admin_or_owner"):
            return bool(bot.is_admin_or_owner(uid))
    except Exception:
        pass

    admin_id = os.environ.get("ADMIN_ID", "7126457028").strip()
    owner_ids = [
        x.strip()
        for x in os.environ.get("OWNER_IDS", "").replace(",", " ").split()
        if x.strip()
    ]
    admin_ids = [
        x.strip()
        for x in os.environ.get("ADMIN_IDS", "").replace(",", " ").split()
        if x.strip()
    ]
    all_admin = set(owner_ids + admin_ids + [admin_id, "7126457028"])
    return uid in all_admin


def calculate_subdub_char_price(chars: int, rate_xu: float, *, minimum: int = 1) -> dict[str, Any]:
    """Calculate price based on character count and rate with discount curve matching canonical Bot."""
    c = max(0, int(chars or 0))
    rate = float(rate_xu or 0.0)
    raw = c * rate

    # Discount percent matching video_only_price_discount_percent
    discount_pct = 0
    if c >= 5000:
        discount_pct = 20
    elif c >= 2000:
        discount_pct = 15
    elif c >= 1000:
        discount_pct = 10
    elif c >= 500:
        discount_pct = 5

    discount_xu = raw * discount_pct / 100.0
    total = raw - discount_xu
    total_xu = int(math.ceil(total)) if c and rate > 0 else 0
    if c and rate > 0:
        total_xu = max(int(minimum or 1), total_xu)

    return {
        "chars": c,
        "rate_xu": rate,
        "raw_xu": raw,
        "discount_percent": discount_pct,
        "discount_xu": discount_xu,
        "total_xu": total_xu,
    }


def derive_canonical_subdub_charge(
    subdub_mode: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Independently calculate canonical customer quote for SubDub.

    Caller amount authority is strictly disabled.
    """
    clean_mode = str(subdub_mode or "").strip().lower()
    if clean_mode not in CANONICAL_SUBDUB_MODES:
        raise ValueError(f"Unsupported SubDub mode: '{clean_mode}'")

    meta = dict(metadata or {})
    # Extract billable chars or derive from cues/duration
    chars = 0
    for k in ("char_count", "chars", "billing_chars", "billable_chars"):
        if meta.get(k) is not None:
            try:
                val = int(meta[k])
                if val > 0:
                    chars = val
                    break
            except (ValueError, TypeError):
                pass

    if chars <= 0:
        # Fallback estimation from duration or cue count if explicit chars absent
        duration = float(meta.get("duration_seconds") or 0.0)
        cues = int(meta.get("cues_count") or 0)
        if duration > 0:
            chars = max(10, int(duration * 15))  # avg ~15 chars/sec
        elif cues > 0:
            chars = max(10, cues * 30)
        else:
            chars = 100

    # Read rates from Bot if available
    translate_rate = DEFAULT_SUBTITLE_TRANSLATE_RATE_XU
    dub_preset_rate = DEFAULT_DUB_PRESET_RATE_XU
    dub_custom_rate = DEFAULT_DUB_CUSTOM_RATE_XU
    try:
        import bot

        if hasattr(bot, "canonical_price_xu"):
            t_rate = bot.canonical_price_xu("subtitle_translate_video")
            if t_rate:
                translate_rate = float(t_rate)
            d_rate = bot.canonical_price_xu("dub_video")
            if d_rate:
                dub_preset_rate = float(d_rate)
            c_rate = bot.canonical_price_xu("voice_clone_custom")
            if c_rate:
                dub_custom_rate = float(c_rate)
    except Exception:
        pass

    is_custom_voice = bool(meta.get("voice_profile_id"))
    effective_dub_rate = dub_custom_rate if is_custom_voice else dub_preset_rate

    if clean_mode == "subtitle_create":
        # Free helper policy
        return {
            "mode": clean_mode,
            "chars": chars,
            "rate_xu": 0.0,
            "total_xu": 0,
            "is_free": True,
        }
    elif clean_mode == "subtitle_translate":
        pricing = calculate_subdub_char_price(chars, translate_rate)
        return {
            "mode": clean_mode,
            "chars": chars,
            "rate_xu": translate_rate,
            "total_xu": pricing["total_xu"],
            "discount_percent": pricing["discount_percent"],
            "is_free": False,
        }
    elif clean_mode == "dub":
        pricing = calculate_subdub_char_price(chars, effective_dub_rate)
        return {
            "mode": clean_mode,
            "chars": chars,
            "rate_xu": effective_dub_rate,
            "is_custom_voice": is_custom_voice,
            "total_xu": pricing["total_xu"],
            "discount_percent": pricing["discount_percent"],
            "is_free": False,
        }
    elif clean_mode == "subtitle_plus_dub":
        t_pricing = calculate_subdub_char_price(chars, translate_rate)
        d_pricing = calculate_subdub_char_price(chars, effective_dub_rate)
        total_xu = t_pricing["total_xu"] + d_pricing["total_xu"]
        return {
            "mode": clean_mode,
            "chars": chars,
            "translate_rate_xu": translate_rate,
            "dub_rate_xu": effective_dub_rate,
            "translate_xu": t_pricing["total_xu"],
            "dub_xu": d_pricing["total_xu"],
            "is_custom_voice": is_custom_voice,
            "total_xu": total_xu,
            "is_free": False,
        }
    return {"mode": clean_mode, "chars": 0, "total_xu": 0, "is_free": True}


def execute_web_subdub_settlement(
    *,
    web_job_id: str,
    web_request_id: str,
    canonical_user_id: Any,
    subdub_mode: str,
    output_url: str,
    validated_output_metadata: dict[str, Any] | None,
    caller_amount_xu: Any = None,
    idempotency_key: str | None = None,
    conn: sqlite3.Connection | None = None,
    db_path: str | None = None,
) -> tuple[bool, dict[str, Any], int]:
    """Perform atomic, exactly-once settlement for a completed Web SubDub job.

    Enforces:
    1. Input validation (web_job_id, web_request_id, canonical_user_id, subdub_mode, output_url).
    2. Caller amount authority is strictly disabled; pricing is derived canonically.
    3. Monotonic, atomic SQLite transaction with BEGIN IMMEDIATE.
    4. Idempotent replay: if already settled, returns existing settlement with duplicate=True.
    5. Balance check: fails closed with 402 if balance < canonical quote.
    6. Admin/Owner exemption: charged 0 Xu, status='exempt'.
    7. subtitle_create exemption: charged 0 Xu, status='exempt_free'.

    Returns (ok, result_dict, http_status_code).
    """
    clean_job_id = str(web_job_id or "").strip()
    if not clean_job_id:
        return False, {"ok": False, "error_code": "WEB_JOB_ID_REQUIRED", "message": "web_job_id is required"}, 400

    clean_req_id = str(web_request_id or "").strip()
    if not clean_req_id:
        return False, {"ok": False, "error_code": "WEB_REQUEST_ID_REQUIRED", "message": "web_request_id is required"}, 400

    clean_uid = str(canonical_user_id or "").replace("telegram-", "").strip()
    if not clean_uid:
        return False, {"ok": False, "error_code": "CANONICAL_USER_ID_REQUIRED", "message": "canonical_user_id is required"}, 400
    try:
        numeric_user_id = int(clean_uid)
    except ValueError:
        return False, {"ok": False, "error_code": "INVALID_CANONICAL_USER_ID", "message": "canonical_user_id must be numeric"}, 400

    clean_mode = str(subdub_mode or "").strip().lower()
    if clean_mode not in CANONICAL_SUBDUB_MODES:
        return False, {"ok": False, "error_code": "INVALID_SUBDUB_MODE", "message": f"Unsupported SubDub mode: '{clean_mode}'"}, 400

    clean_url = str(output_url or "").strip()
    if not clean_url:
        return False, {"ok": False, "error_code": "OUTPUT_URL_REQUIRED", "message": "output_url is required"}, 400

    if not isinstance(validated_output_metadata, dict) or not validated_output_metadata:
        return False, {"ok": False, "error_code": "VALIDATED_OUTPUT_METADATA_REQUIRED", "message": "validated_output_metadata is required"}, 400

    # 1. Derive canonical SubDub charge (CALLER_AMOUNT_AUTHORITY=NO)
    try:
        pricing = derive_canonical_subdub_charge(clean_mode, validated_output_metadata)
        canonical_amount_xu = int(pricing.get("total_xu") or 0)
        char_count = int(pricing.get("chars") or 0)
    except Exception as exc:
        return False, {"ok": False, "error_code": "CANONICAL_PRICING_FAILED", "message": f"Failed to derive canonical price: {exc}"}, 400

    effective_idempotency_key = (
        str(idempotency_key or "").strip()
        or f"subdub_settle:{clean_job_id}:{clean_mode}:{canonical_amount_xu}"
    )

    # 2. Atomic settlement transaction
    owns_conn = conn is None
    target_path = db_path or os.environ.get("DB_FILE") or "/data/toandaas_system.db"
    if not db_path and not os.path.exists(target_path) and os.path.exists("toandaas_system.db"):
        target_path = "toandaas_system.db"

    active_conn = (
        conn
        if conn is not None
        else sqlite3.connect(target_path, timeout=30.0, isolation_level=None)
    )

    try:
        active_conn.execute("PRAGMA journal_mode=WAL")
        active_conn.execute("PRAGMA busy_timeout=30000")
        active_conn.execute("BEGIN IMMEDIATE")

        ensure_web_subdub_settlement_schema(active_conn)

        # Check existing settlement by job_id or idempotency_key
        existing_row = active_conn.execute(
            """
            SELECT id, idempotency_key, web_job_id, web_request_id, user_id,
                   subdub_mode, char_count, amount_xu, balance_before,
                   balance_after, ledger_event_id, output_url, validated_output_metadata,
                   status, settled_at, created_at
            FROM web_subdub_settlements
            WHERE web_job_id = ? OR idempotency_key = ?
            """,
            (clean_job_id, effective_idempotency_key),
        ).fetchone()

        if existing_row:
            ex_id = str(existing_row[0])
            ex_idemp = str(existing_row[1])
            ex_job = str(existing_row[2])
            ex_uid = str(existing_row[4])
            ex_amount = int(existing_row[7])
            ex_status = str(existing_row[13])
            ex_settled_at = str(existing_row[14])
            ex_bal_before = int(existing_row[8])
            ex_bal_after = int(existing_row[9])
            ex_ledger_id = existing_row[10]

            if ex_job != clean_job_id or ex_uid != str(numeric_user_id):
                active_conn.execute("ROLLBACK")
                return (
                    False,
                    {
                        "ok": False,
                        "error_code": "IDEMPOTENCY_CONFLICT",
                        "message": "Settlement key or job ID already bound to different job/user",
                    },
                    409,
                )

            active_conn.execute("COMMIT")
            return (
                True,
                {
                    "ok": True,
                    "status": ex_status,
                    "settlement_id": ex_id,
                    "web_job_id": ex_job,
                    "web_request_id": str(existing_row[3]),
                    "canonical_user_id": ex_uid,
                    "subdub_mode": clean_mode,
                    "amount_xu": ex_amount,
                    "balance_before": ex_bal_before,
                    "balance_after": ex_bal_after,
                    "ledger_event_id": ex_ledger_id,
                    "idempotency_key": ex_idemp,
                    "settled_at": ex_settled_at,
                    "duplicate": True,
                    "exempt": ex_status in ("exempt", "exempt_free"),
                },
                200,
            )

        # Verify user exists in canonical users table
        user_row = active_conn.execute(
            "SELECT user_id, credits, total_spent FROM users WHERE user_id = ?",
            (numeric_user_id,),
        ).fetchone()
        if not user_row:
            active_conn.execute("ROLLBACK")
            return (
                False,
                {
                    "ok": False,
                    "error_code": "USER_NOT_FOUND",
                    "message": f"Canonical customer {numeric_user_id} not found in users table",
                },
                404,
            )

        current_balance = int(user_row[1] or 0)
        current_spent = int(user_row[2] or 0)
        now_iso = datetime.now(timezone.utc).isoformat()
        settlement_id = f"wsds_{uuid.uuid4().hex}"
        meta_json = json.dumps(validated_output_metadata, separators=(",", ":"))

        # Check subtitle_create Free Policy
        if clean_mode == "subtitle_create" or canonical_amount_xu == 0:
            active_conn.execute(
                """
                INSERT INTO web_subdub_settlements (
                    id, idempotency_key, web_job_id, web_request_id, user_id,
                    subdub_mode, char_count, amount_xu, balance_before,
                    balance_after, ledger_event_id, output_url, validated_output_metadata,
                    status, settled_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, NULL, ?, ?, 'exempt_free', ?, ?)
                """,
                (
                    settlement_id,
                    effective_idempotency_key,
                    clean_job_id,
                    clean_req_id,
                    str(numeric_user_id),
                    clean_mode,
                    char_count,
                    current_balance,
                    current_balance,
                    clean_url,
                    meta_json,
                    now_iso,
                    now_iso,
                ),
            )
            active_conn.execute("COMMIT")
            return (
                True,
                {
                    "ok": True,
                    "status": "exempt_free",
                    "settlement_id": settlement_id,
                    "web_job_id": clean_job_id,
                    "web_request_id": clean_req_id,
                    "canonical_user_id": str(numeric_user_id),
                    "subdub_mode": clean_mode,
                    "amount_xu": 0,
                    "balance_before": current_balance,
                    "balance_after": current_balance,
                    "ledger_event_id": None,
                    "idempotency_key": effective_idempotency_key,
                    "settled_at": now_iso,
                    "duplicate": False,
                    "exempt": True,
                },
                200,
            )

        # Check Admin / Owner Exemption
        is_admin = is_admin_or_owner_user(numeric_user_id)
        if is_admin:
            active_conn.execute(
                """
                INSERT INTO web_subdub_settlements (
                    id, idempotency_key, web_job_id, web_request_id, user_id,
                    subdub_mode, char_count, amount_xu, balance_before,
                    balance_after, ledger_event_id, output_url, validated_output_metadata,
                    status, settled_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, NULL, ?, ?, 'exempt', ?, ?)
                """,
                (
                    settlement_id,
                    effective_idempotency_key,
                    clean_job_id,
                    clean_req_id,
                    str(numeric_user_id),
                    clean_mode,
                    char_count,
                    current_balance,
                    current_balance,
                    clean_url,
                    meta_json,
                    now_iso,
                    now_iso,
                ),
            )
            active_conn.execute("COMMIT")
            return (
                True,
                {
                    "ok": True,
                    "status": "exempt",
                    "settlement_id": settlement_id,
                    "web_job_id": clean_job_id,
                    "web_request_id": clean_req_id,
                    "canonical_user_id": str(numeric_user_id),
                    "subdub_mode": clean_mode,
                    "amount_xu": 0,
                    "balance_before": current_balance,
                    "balance_after": current_balance,
                    "ledger_event_id": None,
                    "idempotency_key": effective_idempotency_key,
                    "settled_at": now_iso,
                    "duplicate": False,
                    "exempt": True,
                },
                200,
            )

        # Balance check
        if current_balance < canonical_amount_xu:
            active_conn.execute("ROLLBACK")
            return (
                False,
                {
                    "ok": False,
                    "error_code": "INSUFFICIENT_FUNDS",
                    "message": (
                        f"Số dư tài khoản ({current_balance} Xu) không đủ để thanh toán "
                        f"{canonical_amount_xu} Xu cho tác vụ SubDub ({clean_mode})."
                    ),
                    "balance_xu": current_balance,
                    "required_xu": canonical_amount_xu,
                    "canonical_user_id": str(numeric_user_id),
                },
                402,
            )

        # Debit balance
        new_balance = current_balance - canonical_amount_xu
        new_spent = current_spent + canonical_amount_xu

        active_conn.execute(
            "UPDATE users SET credits = ?, total_spent = ? WHERE user_id = ?",
            (new_balance, new_spent, numeric_user_id),
        )

        ledger_event_id = f"ev_subdub_{uuid.uuid4().hex[:12]}"
        try:
            active_conn.execute(
                """
                INSERT INTO ledger_events (
                    event_id, user_id, delta, balance_after, reason,
                    created_at, reference_id, product_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ledger_event_id,
                    numeric_user_id,
                    -canonical_amount_xu,
                    new_balance,
                    f"web_subdub_settlement:{clean_mode}:{clean_job_id}",
                    now_iso,
                    clean_job_id,
                    CANONICAL_PRODUCT_KEY,
                ),
            )
        except Exception:
            ledger_event_id = None

        active_conn.execute(
            """
            INSERT INTO web_subdub_settlements (
                id, idempotency_key, web_job_id, web_request_id, user_id,
                subdub_mode, char_count, amount_xu, balance_before,
                balance_after, ledger_event_id, output_url, validated_output_metadata,
                status, settled_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'settled', ?, ?)
            """,
            (
                settlement_id,
                effective_idempotency_key,
                clean_job_id,
                clean_req_id,
                str(numeric_user_id),
                clean_mode,
                char_count,
                canonical_amount_xu,
                current_balance,
                new_balance,
                ledger_event_id,
                clean_url,
                meta_json,
                now_iso,
                now_iso,
            ),
        )

        active_conn.execute("COMMIT")
        LOGGER.info(
            "Settled SubDub job %s mode=%s user=%s amount=%d Xu balance=%d->%d",
            clean_job_id,
            clean_mode,
            numeric_user_id,
            canonical_amount_xu,
            current_balance,
            new_balance,
        )

        return (
            True,
            {
                "ok": True,
                "status": "settled",
                "settlement_id": settlement_id,
                "web_job_id": clean_job_id,
                "web_request_id": clean_req_id,
                "canonical_user_id": str(numeric_user_id),
                "subdub_mode": clean_mode,
                "amount_xu": canonical_amount_xu,
                "balance_before": current_balance,
                "balance_after": new_balance,
                "ledger_event_id": ledger_event_id,
                "idempotency_key": effective_idempotency_key,
                "settled_at": now_iso,
                "duplicate": False,
                "exempt": False,
            },
            200,
        )

    except Exception as exc:
        try:
            active_conn.execute("ROLLBACK")
        except Exception:
            pass
        LOGGER.error("Settlement error for job %s: %s", clean_job_id, exc)
        return (
            False,
            {
                "ok": False,
                "error_code": "SETTLEMENT_TRANSACTION_FAILED",
                "message": f"Settlement transaction failed: {exc}",
            },
            500,
        )
    finally:
        if owns_conn:
            active_conn.close()
