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
    ensure_admin_wallet_compensation_schema(conn)


def ensure_admin_wallet_compensation_schema(conn: sqlite3.Connection) -> None:
    """Ensure the durable admin wallet compensation schema exists.

    Additive-only migration: does not alter existing tables.
    Safe to invoke repeatedly across process startups and test setups.
    """
    conn.execute(
        """CREATE TABLE IF NOT EXISTS admin_wallet_compensations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            idempotency_key TEXT NOT NULL UNIQUE,
            source_ledger_event_id INTEGER NOT NULL UNIQUE,
            request_fingerprint TEXT NOT NULL,
            user_id TEXT NOT NULL,
            delta_xu INTEGER NOT NULL,
            reason TEXT DEFAULT '',
            actor_id TEXT DEFAULT '',
            compensation_ledger_event_id INTEGER,
            balance_after INTEGER,
            status TEXT NOT NULL DEFAULT 'completed',
            created_at DATETIME NOT NULL
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_wallet_comp_idem_key ON admin_wallet_compensations(idempotency_key)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_wallet_comp_source_id ON admin_wallet_compensations(source_ledger_event_id)"
    )


ALLOWED_COMPENSABLE_EVENT_TYPES: set[str] = {
    "admin_web_manual_topup",
    "admin_wallet_credit",
    "manual_deposit",
    "admin_add",
}


def compute_compensation_request_fingerprint(
    source_ledger_event_id: int,
    reason: str = "",
    actor_id: str = "",
) -> str:
    """Derive deterministic SHA256 request fingerprint for admin wallet compensation."""
    normalized = (
        f"{int(source_ledger_event_id)}|"
        f"{str(reason or '').strip()}|"
        f"{str(actor_id or '').strip()}"
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


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


def process_internal_wallet_compensation_in_tx(
    conn: sqlite3.Connection,
    source_ledger_event_id: Any,
    idempotency_key: str,
    reason: str = "",
    actor_id: str = "",
    now_str: str | None = None,
) -> tuple[bool, dict[str, Any], int]:
    """Process an admin wallet compensation inside an existing active SQLite transaction.

    Validates:
    - idempotency_key is present and unique
    - source_ledger_event_id exists, has positive delta, belongs to existing user
    - source_ledger_event_id is of an allowed compensable admin event type
    - source_ledger_event_id has not already been compensated
    - target user balance is sufficient (no resulting negative balance)

    Appends:
    - users.credits (-source_event.delta)
    - credit_events (event_type='admin_wallet_compensation', delta=-source_event.delta)
    - admin_wallet_compensations (durable idempotency record)
    - usage_events (best-effort)
    - audit_logs (best-effort)

    Returns:
        (ok, result_dict, http_status_code)
    """
    clean_key = str(idempotency_key or "").strip()
    if not clean_key:
        return False, {
            "ok": False,
            "error_code": "MISSING_IDEMPOTENCY_KEY",
            "message": "idempotency_key is required",
        }, 400

    try:
        source_id = int(source_ledger_event_id)
        if source_id <= 0:
            raise ValueError()
    except (TypeError, ValueError):
        return False, {
            "ok": False,
            "error_code": "INVALID_SOURCE_EVENT_ID",
            "message": "source_ledger_event_id must be a positive integer",
        }, 400

    ensure_admin_wallet_compensation_schema(conn)
    c = conn.cursor()

    clean_actor = str(actor_id or "").strip()
    clean_reason = str(reason or "").strip()
    fp = compute_compensation_request_fingerprint(source_id, clean_reason, clean_actor)
    ts = str(now_str or utc_now_text())

    # 1. Check Idempotency by key
    c.execute(
        """SELECT request_fingerprint, source_ledger_event_id, user_id, delta_xu,
                  compensation_ledger_event_id, balance_after, status
        FROM admin_wallet_compensations WHERE idempotency_key = ?""",
        (clean_key,),
    )
    existing_key = c.fetchone()
    if existing_key:
        ex_fp, ex_source_id, ex_uid, ex_delta, ex_comp_id, ex_bal, ex_status = existing_key
        if ex_fp == fp:
            receipt_str = str(ex_comp_id or "")
            return True, {
                "ok": True,
                "data": {
                    "source_ledger_event_id": int(ex_source_id),
                    "compensation_ledger_event_id": int(ex_comp_id or 0),
                    "tx_id": receipt_str,
                    "user_id": str(ex_uid),
                    "delta_xu": int(ex_delta),
                    "balance_after": int(ex_bal or 0),
                    "replayed": True,
                },
                "source_ledger_event_id": int(ex_source_id),
                "compensation_ledger_event_id": int(ex_comp_id or 0),
                "tx_id": receipt_str,
                "user_id": str(ex_uid),
                "delta_xu": int(ex_delta),
                "balance_after": int(ex_bal or 0),
                "replayed": True,
            }, 200
        else:
            return False, {
                "ok": False,
                "error_code": "IDEMPOTENCY_KEY_CONFLICT",
                "message": "Idempotency key has already been used with different request parameters",
            }, 409

    # 2. Check if source_ledger_event_id already compensated under another key
    c.execute(
        """SELECT idempotency_key, compensation_ledger_event_id
        FROM admin_wallet_compensations WHERE source_ledger_event_id = ?""",
        (source_id,),
    )
    existing_source = c.fetchone()
    if existing_source:
        return False, {
            "ok": False,
            "error_code": "SOURCE_EVENT_ALREADY_COMPENSATED",
            "message": f"Source ledger event {source_id} has already been compensated by key '{existing_source[0]}'",
        }, 409

    # 3. Read & Validate Source Event from credit_events
    c.execute(
        "SELECT id, user_id, delta, balance_after, event_type FROM credit_events WHERE id = ?",
        (source_id,),
    )
    source_row = c.fetchone()
    if not source_row:
        return False, {
            "ok": False,
            "error_code": "SOURCE_EVENT_NOT_FOUND",
            "message": f"Source ledger event {source_id} does not exist in Bot Core",
        }, 404

    _, source_uid_raw, source_delta_raw, _, source_type_raw = source_row
    source_uid = str(source_uid_raw or "").strip()
    source_delta = int(source_delta_raw or 0)
    source_type = str(source_type_raw or "").strip()

    if source_delta <= 0:
        return False, {
            "ok": False,
            "error_code": "INVALID_SOURCE_EVENT_DELTA",
            "message": f"Source ledger event {source_id} delta ({source_delta}) is not positive",
        }, 400

    if source_type not in ALLOWED_COMPENSABLE_EVENT_TYPES:
        return False, {
            "ok": False,
            "error_code": "NON_COMPENSABLE_EVENT_TYPE",
            "message": f"Source event type '{source_type}' is not an allowed compensable administrative credit event type",
        }, 400

    # 4. Validate Target User & Balance Safety
    c.execute("SELECT credits FROM users WHERE user_id = ?", (source_uid,))
    user_row = c.fetchone()
    if not user_row:
        return False, {
            "ok": False,
            "error_code": "ACCOUNT_NOT_FOUND",
            "message": f"User {source_uid} does not exist in Bot Core",
        }, 404

    current_credits = int(user_row[0] or 0)
    compensation_delta = -source_delta
    if current_credits < source_delta:
        return False, {
            "ok": False,
            "error_code": "INSUFFICIENT_BALANCE",
            "message": f"User {source_uid} current balance ({current_credits} Xu) is insufficient to compensate {source_delta} Xu",
        }, 400

    new_balance = current_credits + compensation_delta
    admin_actor = clean_actor or os.environ.get("ADMIN_ID") or DEFAULT_ADMIN_ID
    ref_id = f"compensation:event:{source_id}"
    comp_note = clean_reason or f"Administrative compensation for event {source_id}"

    # 5. Apply Decrement to users.credits
    c.execute(
        "UPDATE users SET credits = credits + ? WHERE user_id = ?",
        (compensation_delta, source_uid),
    )

    # 6. Append New Event to credit_events (Source remains completely immutable)
    c.execute(
        """INSERT INTO credit_events
        (user_id, delta, balance_after, event_type, ref_id, note, created_at)
        VALUES (?, ?, ?, 'admin_wallet_compensation', ?, ?, ?)""",
        (source_uid, compensation_delta, new_balance, ref_id, comp_note, ts),
    )
    comp_ledger_id = int(c.lastrowid)

    # 7. Record Best-Effort usage_events & audit_logs
    try:
        c.execute(
            """INSERT INTO usage_events
            (user_id, event_type, tool_name, status, xu_delta, detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                source_uid,
                "xu_debit",
                "credits",
                "admin_wallet_compensation",
                compensation_delta,
                f"admin_wallet_compensation; ref={ref_id}; {comp_note}",
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
                "credit.compensated",
                "user",
                source_uid,
                json.dumps({"credits": current_credits}),
                json.dumps({
                    "delta": compensation_delta,
                    "credits": new_balance,
                    "source_ledger_event_id": source_id,
                    "compensation_ledger_event_id": comp_ledger_id,
                }),
                str(comp_note)[:1200],
                ts,
            ),
        )
    except Exception:
        pass

    # 8. Record Durable Compensation Idempotency Row
    c.execute(
        """INSERT INTO admin_wallet_compensations
        (idempotency_key, source_ledger_event_id, request_fingerprint, user_id,
         delta_xu, reason, actor_id, compensation_ledger_event_id, balance_after,
         status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?)""",
        (
            clean_key,
            source_id,
            fp,
            source_uid,
            compensation_delta,
            clean_reason,
            clean_actor,
            comp_ledger_id,
            new_balance,
            ts,
        ),
    )

    receipt_str = str(comp_ledger_id)
    return True, {
        "ok": True,
        "data": {
            "source_ledger_event_id": source_id,
            "compensation_ledger_event_id": comp_ledger_id,
            "tx_id": receipt_str,
            "user_id": source_uid,
            "delta_xu": compensation_delta,
            "balance_after": new_balance,
            "replayed": False,
        },
        "source_ledger_event_id": source_id,
        "compensation_ledger_event_id": comp_ledger_id,
        "tx_id": receipt_str,
        "user_id": source_uid,
        "delta_xu": compensation_delta,
        "balance_after": new_balance,
        "replayed": False,
    }, 200


def execute_admin_wallet_compensation(
    source_ledger_event_id: Any,
    idempotency_key: str,
    reason: str = "",
    actor_id: str = "",
    db_path: str = "",
) -> tuple[bool, dict[str, Any], int]:
    """Execute admin wallet compensation with immediate transaction management."""
    target_db = db_path or os.environ.get("DB_FILE") or "toandaas_system.db"
    conn = sqlite3.connect(target_db, timeout=30.0)
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        ok, result, status_code = process_internal_wallet_compensation_in_tx(
            conn=conn,
            source_ledger_event_id=source_ledger_event_id,
            idempotency_key=idempotency_key,
            reason=reason,
            actor_id=actor_id,
        )
        if ok:
            conn.execute("COMMIT")
        else:
            conn.execute("ROLLBACK")
        return ok, result, status_code
    except sqlite3.IntegrityError as exc:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        if "UNIQUE constraint failed" in str(exc):
            try:
                c = conn.cursor()
                c.execute(
                    """SELECT request_fingerprint, source_ledger_event_id, user_id, delta_xu,
                              compensation_ledger_event_id, balance_after, status
                    FROM admin_wallet_compensations WHERE idempotency_key = ?""",
                    (str(idempotency_key or "").strip(),),
                )
                existing = c.fetchone()
                if existing and existing[6] == "completed":
                    fp = compute_compensation_request_fingerprint(int(source_ledger_event_id), reason, actor_id)
                    if existing[0] == fp:
                        receipt_str = str(existing[4] or "")
                        return True, {
                            "ok": True,
                            "data": {
                                "source_ledger_event_id": int(existing[1]),
                                "compensation_ledger_event_id": int(existing[4] or 0),
                                "tx_id": receipt_str,
                                "user_id": str(existing[2]),
                                "delta_xu": int(existing[3]),
                                "balance_after": int(existing[5] or 0),
                                "replayed": True,
                            },
                            "source_ledger_event_id": int(existing[1]),
                            "compensation_ledger_event_id": int(existing[4] or 0),
                            "tx_id": receipt_str,
                            "user_id": str(existing[2]),
                            "delta_xu": int(existing[3]),
                            "balance_after": int(existing[5] or 0),
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
                "message": "Concurrent request conflict on idempotency key or source event",
            }, 409
        logger.error(f"IntegrityError during admin wallet compensation: {exc}", exc_info=True)
        return False, {
            "ok": False,
            "error_code": "TRANSACTION_FAILED",
            "message": f"Database transaction error: {str(exc)}",
        }, 500
    except Exception as exc:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        logger.error(f"Transaction failed during admin wallet compensation: {exc}", exc_info=True)
        return False, {
            "ok": False,
            "error_code": "TRANSACTION_FAILED",
            "message": f"Database transaction error: {str(exc)}",
        }, 500
    finally:
        conn.close()
