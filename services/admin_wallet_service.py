"""Canonical Bot Core admin wallet credit service (SPEC-B).

Provides durable, idempotent, and atomic Xu credit semantics for internal admin requests.
Guarantees:
- Exactly-once wallet credit per idempotency_key
- Replay safety (returns same durable credit_events receipt, wallet delta = 0)
- Conflict safety (same key with different payload returns 409, wallet delta = 0)
- Fail-closed internal auth (rejects missing or invalid credentials)
- Full atomic transaction rollback on failure
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import logging
import os
import sqlite3
import time
from typing import Any

logger = logging.getLogger("admin_wallet_service")

DEFAULT_ADMIN_ID = "7126457028"


def utc_now_text() -> str:
    """Format current UTC time as YYYY-MM-DD HH:MM:SS."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def ensure_admin_wallet_schema(conn: sqlite3.Connection) -> None:
    """Ensure the durable admin wallet idempotency schema exists.

    Additive-only migration: does not alter existing tables.
    Safe to invoke repeatedly across process startups and test setups.
    """
    conn.execute(
        """CREATE TABLE IF NOT EXISTS admin_wallet_idempotency (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            idempotency_key TEXT NOT NULL UNIQUE,
            request_fingerprint TEXT NOT NULL,
            user_id TEXT NOT NULL,
            amount_xu INTEGER NOT NULL,
            reason TEXT DEFAULT '',
            reference TEXT DEFAULT '',
            actor_id TEXT DEFAULT '',
            ledger_event_id INTEGER,
            balance_after INTEGER,
            status TEXT NOT NULL DEFAULT 'completed',
            created_at DATETIME NOT NULL
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_wallet_idem_key ON admin_wallet_idempotency(idempotency_key)"
    )


def compute_credit_request_fingerprint(
    user_id: str,
    amount_xu: int,
    reason: str = "",
    reference: str = "",
) -> str:
    """Derive deterministic SHA256 request fingerprint from canonical request fields."""
    norm_user = str(user_id or "").strip()
    if norm_user.startswith("telegram-"):
        norm_user = norm_user[len("telegram-"):].strip()
    normalized = (
        f"{norm_user}|"
        f"{int(amount_xu)}|"
        f"{str(reason or '').strip()}|"
        f"{str(reference or '').strip()}"
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def verify_internal_admin_wallet_auth(
    authorization: str = "",
    signature: str = "",
    timestamp: str = "",
    request_id: str = "",
    method: str = "POST",
    path: str = "/internal/v1/admin/wallet/credit",
    body_bytes: bytes = b"",
    token_override: str | None = None,
    secret_override: str | None = None,
    clock_skew_seconds: int = 300,
) -> tuple[bool, str, int]:
    """Verify incoming internal admin request credentials against bridge config.

    Returns:
        (is_valid, error_code, http_status)
    """
    bridge_token = (
        token_override
        if token_override is not None
        else (
            os.environ.get("CORE_BRIDGE_TOKEN", "").strip()
            or os.environ.get("WEBAPP_LINK_CALLBACK_TOKEN", "").strip()
            or os.environ.get("INTERNAL_API_SECRET", "").strip()
            or os.environ.get("BOT_INTERNAL_SECRET", "").strip()
        )
    )
    hmac_secret = (
        secret_override
        if secret_override is not None
        else (
            os.environ.get("CORE_BRIDGE_HMAC_SECRET", "").strip()
            or os.environ.get("WEBAPP_LINK_CALLBACK_HMAC_SECRET", "").strip()
            or os.environ.get("INTERNAL_API_SECRET", "").strip()
            or os.environ.get("BOT_INTERNAL_SECRET", "").strip()
        )
    )

    if not bridge_token:
        return False, "BRIDGE_NOT_CONFIGURED", 503

    raw_auth = str(authorization or "").strip()
    if not raw_auth:
        return False, "AUTH_MISSING", 401

    bearer = (
        raw_auth.replace("Bearer ", "", 1).strip()
        if raw_auth.lower().startswith("bearer ")
        else raw_auth
    )
    if not bearer or not hmac.compare_digest(bearer, bridge_token):
        return False, "AUTH_INVALID", 401

    if hmac_secret:
        clean_sig = str(signature or "").strip()
        clean_ts = str(timestamp or "").strip()
        clean_req_id = str(request_id or "").strip()

        if not clean_sig or not clean_ts or not clean_req_id:
            return False, "SIGNATURE_MISSING", 401

        try:
            ts_int = int(clean_ts)
            current_ts = int(time.time())
            if abs(current_ts - ts_int) > clock_skew_seconds:
                return False, "TIMESTAMP_OUT_OF_BOUNDS", 401
        except (ValueError, TypeError):
            return False, "INVALID_TIMESTAMP", 401

        digest = hashlib.sha256(body_bytes or b"").hexdigest()
        normalized_path = "/" + path.lstrip("/")
        message = f"{clean_ts}.{clean_req_id}.{method.upper()}.{normalized_path}.{digest}".encode("utf-8")
        expected_sig = hmac.new(hmac_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()

        if not hmac.compare_digest(clean_sig, expected_sig):
            return False, "SIGNATURE_INVALID", 401

    return True, "OK", 200


def apply_canonical_wallet_credit_conn(
    conn: sqlite3.Connection,
    user_id: str,
    amount_xu: int,
    event_type: str = "admin_web_manual_topup",
    ref_id: str = "",
    note: str = "",
    actor_id: str | None = None,
    now_str: str | None = None,
) -> tuple[int, int]:
    """Execute canonical wallet balance credit and ledger write within an open transaction.

    Mutates:
    - users.credits (+amount_xu)
    - credit_events (canonical ledger row)
    - usage_events (if table exists)
    - audit_logs (if table exists)

    Returns:
        (ledger_event_id, balance_after)
    """
    clean_uid = str(user_id).strip()
    delta = int(amount_xu)
    ts = str(now_str or utc_now_text())
    admin_actor = str(actor_id or os.environ.get("ADMIN_ID") or DEFAULT_ADMIN_ID)

    c = conn.cursor()

    c.execute(
        "UPDATE users SET credits = credits + ? WHERE user_id = ?",
        (delta, clean_uid),
    )

    c.execute("SELECT credits FROM users WHERE user_id = ?", (clean_uid,))
    bal_row = c.fetchone()
    balance_after = int(bal_row[0]) if bal_row else delta

    c.execute(
        """INSERT INTO credit_events
        (user_id, delta, balance_after, event_type, ref_id, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (clean_uid, delta, balance_after, event_type, str(ref_id), str(note), ts),
    )
    ledger_event_id = int(c.lastrowid)

    try:
        c.execute(
            """INSERT INTO usage_events
            (user_id, event_type, tool_name, status, xu_delta, detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                clean_uid,
                "xu_credit",
                "credits",
                event_type,
                delta,
                f"{event_type}; ref={ref_id}; {note}",
                ts,
            ),
        )
    except Exception:
        pass

    try:
        c.execute(
            """INSERT INTO audit_logs
            (actor_id, actor_type, action, object_type, object_id, before_json, after_json, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                admin_actor,
                "admin",
                "credit.added",
                "user",
                clean_uid,
                None,
                json.dumps({
                    "delta": delta,
                    "event_type": event_type,
                    "ref_id": ref_id,
                    "ledger_event_id": ledger_event_id,
                }),
                str(note)[:1200],
                ts,
            ),
        )
    except Exception:
        pass

    return ledger_event_id, balance_after


def process_internal_wallet_credit_in_tx(
    conn: sqlite3.Connection,
    user_id: str,
    amount_xu: int,
    idempotency_key: str,
    reason: str = "",
    reference: str = "",
    actor_id: str = "",
    now_str: str | None = None,
) -> tuple[bool, dict[str, Any], int]:
    """Process an admin wallet credit inside an existing active SQLite transaction."""
    clean_user_id = str(user_id or "").strip()
    if clean_user_id.startswith("telegram-"):
        clean_user_id = clean_user_id[len("telegram-"):].strip()
    if not clean_user_id:
        return False, {
            "ok": False,
            "error_code": "INVALID_ACCOUNT",
            "message": "user_id is required",
        }, 400

    try:
        amount = int(amount_xu)
    except (TypeError, ValueError):
        return False, {
            "ok": False,
            "error_code": "INVALID_AMOUNT",
            "message": "amount_xu must be an integer",
        }, 400

    if amount <= 0:
        return False, {
            "ok": False,
            "error_code": "INVALID_AMOUNT",
            "message": "amount_xu must be greater than 0",
        }, 400

    clean_key = str(idempotency_key or "").strip()
    if not clean_key:
        return False, {
            "ok": False,
            "error_code": "MISSING_IDEMPOTENCY_KEY",
            "message": "idempotency_key is required",
        }, 400

    ensure_admin_wallet_schema(conn)
    c = conn.cursor()

    fp = compute_credit_request_fingerprint(clean_user_id, amount, reason, reference)
    ts = str(now_str or utc_now_text())

    # 1. Check Idempotency Record
    c.execute(
        """SELECT request_fingerprint, ledger_event_id, balance_after, status
        FROM admin_wallet_idempotency WHERE idempotency_key = ?""",
        (clean_key,),
    )
    existing = c.fetchone()

    if existing:
        existing_fp, ledger_event_id, balance_after, status = existing
        if existing_fp == fp:
            receipt_str = str(ledger_event_id or "")
            return True, {
                "ok": True,
                "data": {
                    "ledger_event_id": receipt_str,
                    "tx_id": receipt_str,
                    "user_id": clean_user_id,
                    "amount_xu": amount,
                    "balance_after": int(balance_after or 0),
                    "replayed": True,
                },
                "ledger_event_id": receipt_str,
                "tx_id": receipt_str,
                "user_id": clean_user_id,
                "amount_xu": amount,
                "balance_after": int(balance_after or 0),
                "replayed": True,
            }, 200
        else:
            return False, {
                "ok": False,
                "error_code": "IDEMPOTENCY_KEY_CONFLICT",
                "message": "Idempotency key has already been used with different request parameters",
            }, 409

    # 2. Account Existence Validation
    c.execute("SELECT credits FROM users WHERE user_id = ?", (clean_user_id,))
    user_row = c.fetchone()
    if not user_row:
        return False, {
            "ok": False,
            "error_code": "ACCOUNT_NOT_FOUND",
            "message": f"User {clean_user_id} does not exist in Bot Core",
        }, 404

    # 3. Reserve Idempotency Key (in_flight)
    c.execute(
        """INSERT INTO admin_wallet_idempotency
        (idempotency_key, request_fingerprint, user_id, amount_xu, reason, reference, actor_id, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'in_flight', ?)""",
        (
            clean_key,
            fp,
            clean_user_id,
            amount,
            str(reason or ""),
            str(reference or ""),
            str(actor_id or ""),
            ts,
        ),
    )
    idem_id = c.lastrowid

    # 4. Atomic Ledger Credit Execution
    ledger_event_id, balance_after = apply_canonical_wallet_credit_conn(
        conn,
        user_id=clean_user_id,
        amount_xu=amount,
        event_type="admin_web_manual_topup",
        ref_id=str(reference or clean_key),
        note=str(reason or f"Admin manual topup credit {clean_key}"),
        actor_id=actor_id,
        now_str=ts,
    )

    # 5. Finalize Idempotency Record to completed
    c.execute(
        """UPDATE admin_wallet_idempotency
        SET ledger_event_id = ?, balance_after = ?, status = 'completed'
        WHERE id = ?""",
        (ledger_event_id, balance_after, idem_id),
    )

    receipt_str = str(ledger_event_id)
    return True, {
        "ok": True,
        "data": {
            "ledger_event_id": receipt_str,
            "tx_id": receipt_str,
            "user_id": clean_user_id,
            "amount_xu": amount,
            "balance_after": balance_after,
            "replayed": False,
        },
        "ledger_event_id": receipt_str,
        "tx_id": receipt_str,
        "user_id": clean_user_id,
        "amount_xu": amount,
        "balance_after": balance_after,
        "replayed": False,
    }, 200


def execute_admin_wallet_credit(
    user_id: str,
    amount_xu: int,
    idempotency_key: str,
    reason: str = "",
    reference: str = "",
    actor_id: str = "",
    db_path: str | None = None,
    now_str: str | None = None,
) -> tuple[bool, dict[str, Any], int]:
    """Top-level entrypoint with BEGIN IMMEDIATE transaction boundary and concurrency resilience."""
    path = db_path or os.environ.get("DB_FILE", "toandaas_system.db")
    conn = sqlite3.connect(path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")

    try:
        conn.execute("BEGIN IMMEDIATE")
        ok, res, status = process_internal_wallet_credit_in_tx(
            conn,
            user_id=user_id,
            amount_xu=amount_xu,
            idempotency_key=idempotency_key,
            reason=reason,
            reference=reference,
            actor_id=actor_id,
            now_str=now_str,
        )
        if ok:
            conn.commit()
        else:
            conn.rollback()
        return ok, res, status
    except sqlite3.IntegrityError:
        conn.rollback()
        try:
            conn.execute("BEGIN IMMEDIATE")
            ensure_admin_wallet_schema(conn)
            c = conn.cursor()
            existing = c.execute(
                """SELECT request_fingerprint, ledger_event_id, balance_after, status
                FROM admin_wallet_idempotency WHERE idempotency_key = ?""",
                (str(idempotency_key).strip(),),
            ).fetchone()
            conn.rollback()

            if existing and existing[3] == "completed":
                clean_uid = str(user_id or "").strip()
                if clean_uid.startswith("telegram-"):
                    clean_uid = clean_uid[len("telegram-"):].strip()
                fp = compute_credit_request_fingerprint(clean_uid, int(amount_xu), reason, reference)
                if existing[0] == fp:
                    receipt_str = str(existing[1] or "")
                    return True, {
                        "ok": True,
                        "data": {
                            "ledger_event_id": receipt_str,
                            "tx_id": receipt_str,
                            "user_id": clean_uid,
                            "amount_xu": int(amount_xu),
                            "balance_after": int(existing[2] or 0),
                            "replayed": True,
                        },
                        "ledger_event_id": receipt_str,
                        "tx_id": receipt_str,
                        "user_id": clean_uid,
                        "amount_xu": int(amount_xu),
                        "balance_after": int(existing[2] or 0),
                        "replayed": True,
                    }, 200
                else:
                    return False, {
                        "ok": False,
                        "error_code": "IDEMPOTENCY_KEY_CONFLICT",
                        "message": "Idempotency key has already been used with different request parameters",
                    }, 409
        except Exception:
            pass

        return False, {
            "ok": False,
            "error_code": "CONCURRENT_REQUEST_CONFLICT",
            "message": "Concurrent request conflict on idempotency key",
        }, 409
    except Exception as exc:
        conn.rollback()
        logger.error(f"Transaction failed during admin wallet credit: {exc}", exc_info=True)
        return False, {
            "ok": False,
            "error_code": "TRANSACTION_FAILED",
            "message": f"Database transaction error: {str(exc)}",
        }, 500
    finally:
        conn.close()
