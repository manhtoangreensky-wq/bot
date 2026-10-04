"""Canonical Bot Core runtime service for Web Voice TTS jobs.

Provides server-to-server internal API lifecycle for Web-initiated Voice TTS
requests, handling input authority, pricing quotes, execution, atomic settlement,
and safe audio artifact retrieval.
"""

from __future__ import annotations

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
    """Prepare and record a Web Voice TTS job."""
    local_conn = conn or _get_db_connection()
    now_ts = _utc_now()
    try:
        # Check idempotency
        cur = local_conn.execute(
            "SELECT * FROM web_voice_tts_bot_jobs WHERE idempotency_key = ?",
            (idempotency_key,),
        )
        existing = cur.fetchone()
        if existing:
            return dict(existing)

        status = "awaiting_confirmation" if quote_xu > 0 else "prepared"
        local_conn.execute(
            """
            INSERT INTO web_voice_tts_bot_jobs (
                job_id, idempotency_key, web_request_id, user_id,
                voice_source, script, default_voice_gender, voice_profile_id,
                speed, volume_percent, language, status, status_reason,
                quote_xu, charged_xu, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                now_ts,
                now_ts,
            ),
        )
        cur = local_conn.execute("SELECT * FROM web_voice_tts_bot_jobs WHERE job_id = ?", (web_job_id,))
        return dict(cur.fetchone())
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
