"""Canonical Bot Core runtime service for Web Voice TTS jobs.

Provides server-to-server internal API lifecycle for Web-initiated Voice TTS
requests, handling input authority, pricing quotes, execution, atomic settlement,
and safe audio artifact retrieval.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("toanaas.web_voice_tts_runtime")

FORBIDDEN_AUTHORITY_FIELDS_NORMALIZED = frozenset({
    "provider",
    "providervoiceid",
    "providervoice",
    "providerid",
    "amount",
    "amountxu",
    "price",
    "cost",
    "walletbalance",
    "balance",
    "wallet",
    "walletid",
    "outputurl",
    "chargedxu",
    "quotexu",
    "ispaidjob",
    "confirmpaid",
    "status",
    "statusreason",
})

DEFAULT_VOICE_GENDERS = frozenset({"female", "male"})


def ensure_web_voice_tts_schema(conn: sqlite3.Connection) -> None:
    """Ensure the web_voice_tts_bot_jobs table and indexes exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS web_voice_tts_bot_jobs (
            job_id TEXT PRIMARY KEY,
            idempotency_key TEXT UNIQUE NOT NULL,
            web_request_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            voice_source TEXT NOT NULL,
            script TEXT NOT NULL,
            default_voice_gender TEXT,
            voice_profile_id INTEGER,
            speed TEXT NOT NULL,
            volume_percent INTEGER NOT NULL,
            language TEXT NOT NULL,
            status TEXT NOT NULL,
            status_reason TEXT NOT NULL DEFAULT '',
            quote_xu INTEGER NOT NULL DEFAULT 0,
            charged_xu INTEGER NOT NULL DEFAULT 0,
            artifact_path TEXT,
            artifact_bytes INTEGER DEFAULT 0,
            payload_hash TEXT NOT NULL DEFAULT '',
            settlement_status TEXT NOT NULL DEFAULT 'unsettled',
            settlement_idempotency_key TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT
        );
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_web_voice_tts_user_id
        ON web_voice_tts_bot_jobs(user_id);
        """
    )
    # Ensure migration columns for existing tables
    for col_name, col_def in (
        ("payload_hash", "TEXT NOT NULL DEFAULT ''"),
        ("settlement_status", "TEXT NOT NULL DEFAULT 'unsettled'"),
        ("settlement_idempotency_key", "TEXT"),
    ):
        try:
            conn.execute(f"ALTER TABLE web_voice_tts_bot_jobs ADD COLUMN {col_name} {col_def};")
        except sqlite3.OperationalError:
            pass


def _get_db_connection(db_path: str | None = None) -> sqlite3.Connection:
    target_path = db_path or os.environ.get("DB_FILE") or "/data/toandaas_system.db"
    if not db_path and not os.path.exists(target_path) and os.path.exists("toandaas_system.db"):
        target_path = "toandaas_system.db"
    conn = sqlite3.connect(target_path, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    ensure_web_voice_tts_schema(conn)
    return conn


def _contains_forbidden_authority(payload: dict) -> bool:
    for key in payload.keys():
        norm = "".join(ch for ch in str(key).lower() if ch.isalnum())
        if norm in FORBIDDEN_AUTHORITY_FIELDS_NORMALIZED:
            return True
    return False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def compute_voice_tts_payload_hash(payload_data: dict[str, Any]) -> str:
    """Compute canonical hash of semantic payload fields for tamper-evident idempotency."""
    canonical_repr = {
        "voice_source": str(payload_data.get("voice_source") or "").strip().lower(),
        "script": str(payload_data.get("script") or "").strip(),
        "default_voice_gender": str(payload_data.get("default_voice_gender") or "").strip().lower(),
        "voice_profile_id": int(payload_data.get("voice_profile_id")) if payload_data.get("voice_profile_id") else None,
        "speed": str(payload_data.get("speed") or "1.0").strip(),
        "volume_percent": int(payload_data.get("volume_percent") or 100),
        "language": str(payload_data.get("language") or "vi").strip().lower(),
    }
    encoded = json.dumps(canonical_repr, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def get_web_voice_tts_job(job_id: str, user_id: int, *, conn: sqlite3.Connection | None = None) -> dict[str, Any] | None:
    """Retrieve job by job_id ensuring actor ownership."""
    local_conn = conn or _get_db_connection()
    try:
        cur = local_conn.execute(
            """
            SELECT * FROM web_voice_tts_bot_jobs
            WHERE job_id = ? AND user_id = ?
            """,
            (job_id, int(user_id)),
        )
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        if conn is None:
            local_conn.close()


def prepare_web_voice_tts_job(
    *,
    web_job_id: str,
    web_request_id: str,
    canonical_user_id: int,
    voice_source: str,
    script: str,
    default_voice_gender: str = "",
    voice_profile_id: int | None = None,
    speed: str = "1.0",
    volume_percent: int = 100,
    language: str = "vi",
    idempotency_key: str = "",
    quote_xu: int = 0,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Prepare and record a Web Voice TTS job with strict owner and payload idempotency binding."""
    local_conn = conn or _get_db_connection()
    now_ts = _utc_now()
    payload_dict = {
        "voice_source": voice_source,
        "script": script,
        "default_voice_gender": default_voice_gender,
        "voice_profile_id": voice_profile_id,
        "speed": speed,
        "volume_percent": volume_percent,
        "language": language,
    }
    payload_hash = compute_voice_tts_payload_hash(payload_dict)

    try:
        # Check idempotency with owner and payload binding
        if idempotency_key:
            cur = local_conn.execute(
                "SELECT * FROM web_voice_tts_bot_jobs WHERE idempotency_key = ?",
                (idempotency_key,),
            )
            existing = cur.fetchone()
            if existing:
                # 1. Foreign owner leak prevention (Blocker 6)
                if int(existing["user_id"]) != int(canonical_user_id):
                    return {
                        "ok": False,
                        "error_code": "IDEMPOTENCY_OWNER_MISMATCH",
                        "message": "Idempotency key belongs to another user account",
                    }
                # 2. Same owner + different payload -> deterministic conflict
                existing_hash = existing["payload_hash"] or ""
                if existing_hash and existing_hash != payload_hash:
                    return {
                        "ok": False,
                        "error_code": "IDEMPOTENCY_PAYLOAD_MISMATCH",
                        "message": "Idempotency key reused with different payload parameters",
                    }
                # 3. Same owner + same key + same payload -> identical replay
                return {"ok": True, "job": dict(existing), "idempotent_replay": True}

        status = "awaiting_confirmation" if quote_xu > 0 else "prepared"
        local_conn.execute(
            """
            INSERT INTO web_voice_tts_bot_jobs (
                job_id, idempotency_key, web_request_id, user_id,
                voice_source, script, default_voice_gender, voice_profile_id,
                speed, volume_percent, language, status, status_reason,
                quote_xu, charged_xu, payload_hash, settlement_status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                web_job_id,
                idempotency_key,
                web_request_id,
                int(canonical_user_id),
                voice_source,
                script,
                default_voice_gender or None,
                int(voice_profile_id) if voice_profile_id else None,
                str(speed),
                int(volume_percent),
                language,
                status,
                "AWAITING_CUSTOMER_CONFIRMATION" if quote_xu > 0 else "PREPARED",
                int(quote_xu),
                0,
                payload_hash,
                "unsettled",
                now_ts,
                now_ts,
            ),
        )
        cur = local_conn.execute("SELECT * FROM web_voice_tts_bot_jobs WHERE job_id = ?", (web_job_id,))
        row = cur.fetchone()
        return {"ok": True, "job": dict(row) if row else {}, "idempotent_replay": False}
    finally:
        if conn is None:
            local_conn.close()


def claim_web_voice_tts_job_for_execution(
    job_id: str,
    user_id: int,
    *,
    conn: sqlite3.Connection | None = None,
) -> tuple[bool, dict[str, Any] | None]:
    """Atomic compare-and-set claim ensuring exactly-once execution (Blocker 2 & Crash Recovery).

    Supports:
    1. Fresh / retryable states: 'prepared', 'awaiting_confirmation', 'payment_required'
    2. Crash recovery state: 'processing' with settlement_status = 'settling'

    Returns:
        (claimed: bool, job: dict | None)
    """
    local_conn = conn or _get_db_connection()
    now_ts = _utc_now()
    try:
        # Atomic CAS: transition to 'processing' from ready states or claim settling crash recovery
        cur = local_conn.execute(
            """
            UPDATE web_voice_tts_bot_jobs
            SET status = 'processing',
                status_reason = CASE
                    WHEN status = 'processing' AND settlement_status = 'settling' THEN 'RECOVERING_SETTLEMENT'
                    ELSE 'CLAIMED_FOR_EXECUTION'
                END,
                updated_at = ?
            WHERE job_id = ? AND user_id = ?
              AND (
                  status IN ('prepared', 'awaiting_confirmation', 'payment_required')
                  OR (status = 'processing' AND settlement_status = 'settling' AND status_reason != 'RECOVERING_SETTLEMENT')
              )
            """,
            (now_ts, job_id, int(user_id)),
        )
        claimed = (cur.rowcount == 1)

        cur = local_conn.execute(
            "SELECT * FROM web_voice_tts_bot_jobs WHERE job_id = ? AND user_id = ?",
            (job_id, int(user_id)),
        )
        row = cur.fetchone()
        if not row:
            return claimed, None
        if isinstance(row, sqlite3.Row):
            job_dict = dict(row)
        else:
            cols = [col[0] for col in cur.description]
            job_dict = dict(zip(cols, row))
        return claimed, job_dict
    finally:
        if conn is None:
            local_conn.close()


def update_web_voice_tts_settlement(
    job_id: str,
    settlement_status: str,
    *,
    settlement_idempotency_key: str | None = None,
    charged_xu: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Record durable settlement state to prevent duplicate charges upon ambiguous crash/retry (Blocker 3)."""
    local_conn = conn or _get_db_connection()
    now_ts = _utc_now()
    try:
        updates = ["settlement_status = ?", "updated_at = ?"]
        params: list[Any] = [settlement_status, now_ts]
        if settlement_idempotency_key is not None:
            updates.append("settlement_idempotency_key = ?")
            params.append(settlement_idempotency_key)
        if charged_xu is not None:
            updates.append("charged_xu = ?")
            params.append(int(charged_xu))
        params.append(job_id)
        local_conn.execute(
            f"UPDATE web_voice_tts_bot_jobs SET {', '.join(updates)} WHERE job_id = ?",
            params,
        )
        cur = local_conn.execute("SELECT * FROM web_voice_tts_bot_jobs WHERE job_id = ?", (job_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        if conn is None:
            local_conn.close()


def update_web_voice_tts_job_status(
    job_id: str,
    status: str,
    *,
    status_reason: str = "",
    charged_xu: int | None = None,
    artifact_path: str | None = None,
    artifact_bytes: int | None = None,
    settlement_status: str | None = None,
    settlement_idempotency_key: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Update job status and completion metadata."""
    local_conn = conn or _get_db_connection()
    now_ts = _utc_now()
    try:
        updates = ["status = ?", "updated_at = ?"]
        params: list[Any] = [status, now_ts]
        if status_reason:
            updates.append("status_reason = ?")
            params.append(status_reason)
        if charged_xu is not None:
            updates.append("charged_xu = ?")
            params.append(int(charged_xu))
        if artifact_path is not None:
            updates.append("artifact_path = ?")
            params.append(artifact_path)
        if artifact_bytes is not None:
            updates.append("artifact_bytes = ?")
            params.append(int(artifact_bytes))
        if settlement_status is not None:
            updates.append("settlement_status = ?")
            params.append(settlement_status)
        if settlement_idempotency_key is not None:
            updates.append("settlement_idempotency_key = ?")
            params.append(settlement_idempotency_key)
        if status in ("completed", "failed"):
            updates.append("completed_at = ?")
            params.append(now_ts)

        params.append(job_id)
        local_conn.execute(
            f"UPDATE web_voice_tts_bot_jobs SET {', '.join(updates)} WHERE job_id = ?",
            params,
        )
        cur = local_conn.execute("SELECT * FROM web_voice_tts_bot_jobs WHERE job_id = ?", (job_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        if conn is None:
            local_conn.close()
