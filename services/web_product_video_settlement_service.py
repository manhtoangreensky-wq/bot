"""Canonical Bot Core settlement bridge service for Web Product Video jobs.

Provides an atomic, exactly-once server-to-server financial settlement transaction
between Web Product Video completion and Bot Core SQLite wallet ledger.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from services.video_ai_real_pricing import (
    public_quality_by_tier,
    video_multiscene_price,
)

LOGGER = logging.getLogger("toanaas.web_pv_settlement")

CANONICAL_PRODUCT_KEY = "video_ai_prompt"


def ensure_web_product_video_settlement_schema(conn: sqlite3.Connection) -> None:
    """Ensure the web_product_video_settlements table and unique indexes exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS web_product_video_settlements (
            id TEXT PRIMARY KEY,
            idempotency_key TEXT UNIQUE NOT NULL,
            web_job_id TEXT UNIQUE NOT NULL,
            web_request_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            product_key TEXT NOT NULL,
            tier_id INTEGER NOT NULL,
            scene_count INTEGER NOT NULL,
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
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_web_pv_settlements_job ON web_product_video_settlements(web_job_id)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_web_pv_settlements_idemp ON web_product_video_settlements(idempotency_key)"
    )


def is_admin_or_owner_user(user_id: Any) -> bool:
    """Check whether a user_id belongs to Admin or Owner."""
    uid = str(user_id or "").strip()
    if not uid:
        return False
    # If bot module is loaded, defer to canonical functions
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


def derive_canonical_product_video_charge(
    tier_id: int, scene_count: int = 1, product_key: str = CANONICAL_PRODUCT_KEY
) -> dict[str, Any]:
    """Independently calculate canonical customer quote for Product Video.

    Caller amount authority is strictly disabled.
    """
    if str(product_key).strip() != CANONICAL_PRODUCT_KEY:
        raise ValueError(
            f"Unsupported product_key '{product_key}'. Expected '{CANONICAL_PRODUCT_KEY}'"
        )
    quality = public_quality_by_tier(int(tier_id))
    unit_xu = int(quality.get("unit_xu") or 0)
    pricing = video_multiscene_price(unit_xu, scene_count)
    return pricing


def execute_web_product_video_settlement(
    *,
    web_job_id: str,
    web_request_id: str,
    canonical_user_id: Any,
    product_key: str,
    tier_id: Any,
    scene_count: Any = 1,
    output_url: str,
    validated_output_metadata: dict[str, Any] | None,
    caller_amount_xu: Any = None,
    idempotency_key: str | None = None,
    db_path: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> tuple[bool, dict[str, Any], int]:
    """Atomically settle a validated Web Product Video delivery.

    Guarantees:
    - ATOMIC_WALLET_AND_RECEIPT_TRANSACTION=YES
    - DUPLICATE_SETTLEMENT_RETURNS_EXISTING_RECEIPT=YES
    - DUPLICATE_WALLET_DEBIT_COUNT=0
    - CRASH_WINDOW_DOUBLE_CHARGE=NO
    - CALLER_AMOUNT_AUTHORITY=NO
    - BOT_REDERIVES_CHARGE_AMOUNT=YES
    - QUOTE_MISMATCH_FAIL_CLOSED=YES
    - ADMIN_OWNER_PAID_CUSTOMER_CHARGE=NO

    Returns:
        (ok, response_dict, http_status_code)
    """
    # 1. Validate mandatory fields
    clean_job_id = str(web_job_id or "").strip()
    if not clean_job_id:
        return (
            False,
            {
                "ok": False,
                "error_code": "WEB_JOB_ID_REQUIRED",
                "message": "web_job_id is required",
            },
            400,
        )

    clean_req_id = str(web_request_id or "").strip()
    if not clean_req_id:
        return (
            False,
            {
                "ok": False,
                "error_code": "WEB_REQUEST_ID_REQUIRED",
                "message": "web_request_id is required",
            },
            400,
        )

    clean_uid = str(canonical_user_id or "").replace("telegram-", "").strip()
    if not clean_uid:
        return (
            False,
            {
                "ok": False,
                "error_code": "CANONICAL_USER_ID_REQUIRED",
                "message": "canonical_user_id is required",
            },
            400,
        )
    try:
        numeric_user_id = int(clean_uid)
    except ValueError:
        return (
            False,
            {
                "ok": False,
                "error_code": "INVALID_CANONICAL_USER_ID",
                "message": "canonical_user_id must be numeric",
            },
            400,
        )

    clean_prod_key = str(product_key or "").strip()
    if clean_prod_key != CANONICAL_PRODUCT_KEY:
        return (
            False,
            {
                "ok": False,
                "error_code": "INVALID_PRODUCT_KEY",
                "message": f"product_key must be '{CANONICAL_PRODUCT_KEY}', got '{clean_prod_key}'",
            },
            400,
        )

    clean_url = str(output_url or "").strip()
    if not clean_url:
        return (
            False,
            {
                "ok": False,
                "error_code": "OUTPUT_URL_REQUIRED",
                "message": "output_url is required",
            },
            400,
        )

    if (
        not isinstance(validated_output_metadata, dict)
        or not validated_output_metadata
    ):
        return (
            False,
            {
                "ok": False,
                "error_code": "VALIDATED_OUTPUT_METADATA_REQUIRED",
                "message": "validated_output_metadata is required",
            },
            400,
        )

    try:
        numeric_tier = int(tier_id)
        numeric_scenes = max(1, int(scene_count or 1))
    except (TypeError, ValueError):
        return (
            False,
            {
                "ok": False,
                "error_code": "INVALID_TIER_OR_SCENES",
                "message": "tier_id and scene_count must be integers",
            },
            400,
        )

    # 2. Derive canonical Product Video quote (CALLER_AMOUNT_AUTHORITY=NO)
    try:
        pricing = derive_canonical_product_video_charge(
            tier_id=numeric_tier,
            scene_count=numeric_scenes,
            product_key=clean_prod_key,
        )
        canonical_amount_xu = int(pricing.get("total_xu") or 0)
    except Exception as exc:
        return (
            False,
            {
                "ok": False,
                "error_code": "CANONICAL_PRICING_FAILED",
                "message": f"Failed to derive canonical price: {exc}",
            },
            400,
        )

    # 3. Caller quote mismatch check (QUOTE_MISMATCH_FAIL_CLOSED=YES)
    if caller_amount_xu is not None:
        try:
            caller_int = int(caller_amount_xu)
            if caller_int != canonical_amount_xu:
                return (
                    False,
                    {
                        "ok": False,
                        "error_code": "QUOTE_MISMATCH",
                        "message": (
                            f"Caller amount {caller_int} Xu does not match canonical quote "
                            f"{canonical_amount_xu} Xu"
                        ),
                        "canonical_amount_xu": canonical_amount_xu,
                        "caller_amount_xu": caller_int,
                    },
                    400,
                )
        except (TypeError, ValueError):
            return (
                False,
                {
                    "ok": False,
                    "error_code": "INVALID_CALLER_AMOUNT",
                    "message": "caller_amount_xu must be an integer",
                },
                400,
            )

    canonical_key = f"web_product_video_final_delivery:{clean_job_id}:{canonical_amount_xu}"
    effective_idempotency_key = (
        str(idempotency_key or "").strip() or canonical_key
    )

    # If caller provided key that specifies an amount, verify it matches
    if ":" in effective_idempotency_key:
        parts = effective_idempotency_key.split(":")
        if len(parts) >= 3 and parts[-1].isdigit():
            key_amount = int(parts[-1])
            if key_amount != canonical_amount_xu:
                return (
                    False,
                    {
                        "ok": False,
                        "error_code": "QUOTE_MISMATCH",
                        "message": (
                            f"Idempotency key amount {key_amount} Xu does not match canonical quote "
                            f"{canonical_amount_xu} Xu"
                        ),
                        "canonical_amount_xu": canonical_amount_xu,
                    },
                    400,
                )

    # 4. Atomic settlement transaction
    owns_conn = conn is None
    target_path = (
        db_path or os.environ.get("DB_FILE") or "/data/toandaas_system.db"
    )
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

        ensure_web_product_video_settlement_schema(active_conn)

        # Check existing settlement by job_id or idempotency_key
        existing_row = active_conn.execute(
            """
            SELECT id, idempotency_key, web_job_id, web_request_id, user_id,
                   product_key, tier_id, scene_count, amount_xu, balance_before,
                   balance_after, ledger_event_id, output_url, validated_output_metadata,
                   status, settled_at, created_at
            FROM web_product_video_settlements
            WHERE web_job_id = ? OR idempotency_key = ?
            """,
            (clean_job_id, effective_idempotency_key),
        ).fetchone()

        if existing_row:
            # Existing settlement found! Check for conflict vs replay
            ex_id = str(existing_row[0])
            ex_idemp = str(existing_row[1])
            ex_job = str(existing_row[2])
            ex_uid = str(existing_row[4])
            ex_amount = int(existing_row[8])
            ex_status = str(existing_row[14])
            ex_settled_at = str(existing_row[15])
            ex_bal_before = int(existing_row[9])
            ex_bal_after = int(existing_row[10])
            ex_ledger_id = existing_row[11]

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
                    "amount_xu": ex_amount,
                    "balance_before": ex_bal_before,
                    "balance_after": ex_bal_after,
                    "ledger_event_id": ex_ledger_id,
                    "idempotency_key": ex_idemp,
                    "settled_at": ex_settled_at,
                    "duplicate": True,
                    "exempt": ex_status == "exempt",
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
        settlement_id = f"wpvs_{uuid.uuid4().hex}"
        meta_json = json.dumps(
            validated_output_metadata, separators=(",", ":")
        )

        # Check Admin / Owner Exemption (Phase E)
        is_admin = is_admin_or_owner_user(numeric_user_id)
        if is_admin:
            # Admin/Owner is exempt: 0 Xu charged, no wallet deduction
            active_conn.execute(
                """
                INSERT INTO web_product_video_settlements (
                    id, idempotency_key, web_job_id, web_request_id, user_id,
                    product_key, tier_id, scene_count, amount_xu, balance_before,
                    balance_after, ledger_event_id, output_url, validated_output_metadata,
                    status, settled_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, NULL, ?, ?, 'exempt', ?, ?)
                """,
                (
                    settlement_id,
                    effective_idempotency_key,
                    clean_job_id,
                    clean_req_id,
                    str(numeric_user_id),
                    clean_prod_key,
                    numeric_tier,
                    numeric_scenes,
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
                    "amount_xu": 0,
                    "balance_before": current_balance,
                    "balance_after": current_balance,
                    "ledger_event_id": None,
                    "idempotency_key": effective_idempotency_key,
                    "settled_at": now_iso,
                    "duplicate": False,
                    "exempt": True,
                    "charge_skip_reason": "admin_owner_free",
                },
                200,
            )

        # Non-admin paid customer: balance check
        if current_balance < canonical_amount_xu:
            active_conn.execute("ROLLBACK")
            return (
                False,
                {
                    "ok": False,
                    "error_code": "INSUFFICIENT_BALANCE",
                    "message": (
                        f"Customer balance {current_balance} Xu is less than canonical quote "
                        f"{canonical_amount_xu} Xu"
                    ),
                    "balance_xu": current_balance,
                    "required_xu": canonical_amount_xu,
                },
                402,
            )

        # Atomic debit
        new_balance = current_balance - canonical_amount_xu
        new_spent = current_spent + canonical_amount_xu

        update_cur = active_conn.execute(
            """
            UPDATE users
            SET credits = ?, total_spent = ?
            WHERE user_id = ? AND credits >= ?
            """,
            (new_balance, new_spent, numeric_user_id, canonical_amount_xu),
        )
        if update_cur.rowcount != 1:
            active_conn.execute("ROLLBACK")
            return (
                False,
                {
                    "ok": False,
                    "error_code": "CONCURRENT_WALLET_MUTATION",
                    "message": "Atomic balance decrement failed due to concurrent modification",
                },
                409,
            )

        # Record in credit_events ledger
        event_type = "web_product_video_final_delivery"
        note = f"Web Product Video job #{clean_job_id} tier {numeric_tier} final MP4 delivered"
        ledger_cur = active_conn.execute(
            """
            INSERT INTO credit_events (user_id, delta, balance_after, event_type, ref_id, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                numeric_user_id,
                -canonical_amount_xu,
                new_balance,
                event_type,
                effective_idempotency_key,
                note,
                now_iso,
            ),
        )
        ledger_event_id = str(ledger_cur.lastrowid or "")

        # Persist settlement receipt
        active_conn.execute(
            """
            INSERT INTO web_product_video_settlements (
                id, idempotency_key, web_job_id, web_request_id, user_id,
                product_key, tier_id, scene_count, amount_xu, balance_before,
                balance_after, ledger_event_id, output_url, validated_output_metadata,
                status, settled_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'settled', ?, ?)
            """,
            (
                settlement_id,
                effective_idempotency_key,
                clean_job_id,
                clean_req_id,
                str(numeric_user_id),
                clean_prod_key,
                numeric_tier,
                numeric_scenes,
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
        return (
            True,
            {
                "ok": True,
                "status": "settled",
                "settlement_id": settlement_id,
                "web_job_id": clean_job_id,
                "web_request_id": clean_req_id,
                "canonical_user_id": str(numeric_user_id),
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
        LOGGER.exception(
            "Unexpected error in execute_web_product_video_settlement: %s", exc
        )
        return (
            False,
            {
                "ok": False,
                "error_code": "INTERNAL_SETTLEMENT_ERROR",
                "message": f"Settlement failed unexpectedly: {exc}",
            },
            500,
        )
    finally:
        if owns_conn:
            try:
                active_conn.close()
            except Exception:
                pass
