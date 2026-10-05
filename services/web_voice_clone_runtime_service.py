"""Canonical Bot Core runtime service for Web Voice Clone durable job authority.

SPEC_ID: BOT-WEB-VOICE-CLONE-RUNTIME-AUTHORITY-R1
Coordinates:
- Repository: manhtoangreensky-wq/bot
- Governed by: owner-governed-codex, locked-focus-engineering

Invariants:
1. Server generates opaque job_id (vcjob_<32 hex chars>); client cannot dictate it.
2. Owner binding is derived strictly from authenticated actor; client cannot forge user_id.
3. Client cannot dictate provider, provider_voice_id, provider_file_id, price, wallet debit, or internal paths.
4. Input contract requires exactly 1 canonical staged upload_id, consent=True, and display_name <= 120 chars.
5. Canonical commercial authority derives strictly from Bot Core (50 Xu base price, first free when eligible).
6. Atomic compare-and-set claim prevents duplicate concurrent provider executions (max 1 provider call).
7. Settlement durability with exact-once debit via idempotent wallet debit key before profile activation.
8. Insufficient funds preserves provider result in payment_required without secondary provider execution.
9. Ambiguous network or provider outcomes fail closed with no blind provider retry.
10. Safe external projections strictly mask internal paths, secrets, provider file IDs, and wallet internals.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any

from services.voice_clone_pipeline import (
    CUSTOM_VOICE_ALLOWED_EXTENSIONS,
    CUSTOM_VOICE_MAX_SAMPLE_BYTES,
    CUSTOM_VOICE_MIN_DETECTABLE_SECONDS,
    PUBLIC_CUSTOM_VOICE_FAILED,
    PUBLIC_CUSTOM_VOICE_NOT_READY,
    PUBLIC_CUSTOM_VOICE_SAMPLE_TOO_LARGE,
    PUBLIC_CUSTOM_VOICE_SAMPLE_TOO_SHORT,
    PUBLIC_CUSTOM_VOICE_UNSUPPORTED_AUDIO,
    _detect_sample_duration_seconds,
)

LOGGER = logging.getLogger("toanaas.web_voice_clone_runtime")

FORBIDDEN_AUTHORITY_FIELDS_NORMALIZED = frozenset({
    "provider",
    "providervoiceid",
    "providervoice",
    "providerid",
    "providerfileid",
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
    "localpath",
    "filepath",
    "path",
    "url",
    "remoteurl",
    "providerurl",
    "profileid",
    "canonicalprofileid",
})


def ensure_web_voice_clone_schema(conn: sqlite3.Connection) -> None:
    """Ensure the web_voice_clone_jobs table and indexes exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS web_voice_clone_jobs (
            job_id TEXT PRIMARY KEY,
            idempotency_key TEXT UNIQUE NOT NULL,
            web_request_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            payload_hash TEXT NOT NULL,
            upload_id TEXT NOT NULL,
            consent_snapshot INTEGER NOT NULL DEFAULT 1,
            display_name TEXT NOT NULL,
            quote_xu INTEGER NOT NULL DEFAULT 50,
            pricing_state TEXT NOT NULL DEFAULT 'paid_50_xu',
            status TEXT NOT NULL,
            status_reason TEXT NOT NULL DEFAULT '',
            execution_claim TEXT,
            provider_execution_count INTEGER NOT NULL DEFAULT 0,
            provider_outcome_state TEXT DEFAULT 'unattempted',
            provider_ambiguity_state TEXT DEFAULT '',
            settlement_status TEXT NOT NULL DEFAULT 'unsettled',
            settlement_idempotency_key TEXT,
            canonical_profile_id INTEGER,
            provider_voice_id TEXT DEFAULT '',
            provider_file_id TEXT DEFAULT '',
            provider_route TEXT DEFAULT '',
            preview_audio_path TEXT,
            preview_audio_bytes INTEGER DEFAULT 0,
            charged_xu INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            recovery_markers TEXT DEFAULT '{}'
        );
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_web_voice_clone_user_id
        ON web_voice_clone_jobs(user_id);
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_web_voice_clone_status
        ON web_voice_clone_jobs(status);
        """
    )


def _get_db_connection(db_path: str | None = None) -> sqlite3.Connection:
    target_path = db_path or os.environ.get("DB_FILE") or "/data/toandaas_system.db"
    if not db_path and not os.path.exists(target_path) and os.path.exists("toandaas_system.db"):
        target_path = "toandaas_system.db"
    conn = sqlite3.connect(target_path, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    ensure_web_voice_clone_schema(conn)
    return conn


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def contains_forbidden_authority_fields(payload: dict[str, Any]) -> tuple[bool, str]:
    """Check if client payload contains any forbidden server-owned authority field."""
    for key in payload.keys():
        norm = "".join(ch for ch in str(key).lower() if ch.isalnum())
        if norm in FORBIDDEN_AUTHORITY_FIELDS_NORMALIZED:
            return True, str(key)
    return False, ""


def compute_voice_clone_payload_hash(
    upload_id: str,
    consent: bool,
    display_name: str,
) -> str:
    """Compute canonical hash of client-controlled semantic payload fields."""
    canonical_repr = {
        "consent": bool(consent),
        "display_name": str(display_name or "").strip()[:120],
        "upload_id": str(upload_id or "").strip(),
    }
    encoded = json.dumps(canonical_repr, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_voice_clone_sample(sample_path: Path) -> tuple[bool, str, str]:
    """Validate sample audio against canonical Voice Clone constraints."""
    if not sample_path.exists() or not sample_path.is_file():
        return False, "sample_missing_or_empty", PUBLIC_CUSTOM_VOICE_FAILED

    clean_suffix = sample_path.suffix.lower()
    if clean_suffix not in CUSTOM_VOICE_ALLOWED_EXTENSIONS:
        return False, "unsupported_audio_extension", PUBLIC_CUSTOM_VOICE_UNSUPPORTED_AUDIO

    size_bytes = int(sample_path.stat().st_size or 0)
    if size_bytes <= 0:
        return False, "sample_missing_or_empty", PUBLIC_CUSTOM_VOICE_FAILED
    if size_bytes > CUSTOM_VOICE_MAX_SAMPLE_BYTES:
        return False, "sample_too_large", PUBLIC_CUSTOM_VOICE_SAMPLE_TOO_LARGE

    duration_seconds = _detect_sample_duration_seconds(sample_path)
    if 0 < duration_seconds < CUSTOM_VOICE_MIN_DETECTABLE_SECONDS:
        return False, "sample_duration_too_short", PUBLIC_CUSTOM_VOICE_SAMPLE_TOO_SHORT

    return True, "OK", ""


def get_web_voice_clone_job(
    job_id: str,
    user_id: int | str,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Retrieve job by job_id ensuring actor ownership."""
    local_conn = conn or _get_db_connection()
    try:
        cur = local_conn.execute(
            """
            SELECT * FROM web_voice_clone_jobs
            WHERE job_id = ? AND user_id = ?
            """,
            (str(job_id), int(user_id)),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        if conn is None:
            local_conn.close()


def prepare_web_voice_clone_job(
    *,
    web_job_id: str,
    web_request_id: str,
    canonical_user_id: int,
    upload_id: str,
    consent: bool,
    display_name: str,
    idempotency_key: str = "",
    quote_xu: int = 50,
    pricing_state: str = "paid_50_xu",
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Prepare and record a Web Voice Clone job with strict owner and payload binding."""
    local_conn = conn or _get_db_connection()
    now_ts = _utc_now()
    clean_display_name = re.sub(r"\s+", " ", str(display_name or "")).strip()[:120]
    payload_hash = compute_voice_clone_payload_hash(
        upload_id=upload_id,
        consent=consent,
        display_name=clean_display_name,
    )

    try:
        # Check idempotency with owner and payload binding
        if idempotency_key:
            cur = local_conn.execute(
                "SELECT * FROM web_voice_clone_jobs WHERE idempotency_key = ?",
                (idempotency_key,),
            )
            existing = cur.fetchone()
            if existing:
                # Foreign owner leak prevention
                if int(existing["user_id"]) != int(canonical_user_id):
                    return {
                        "ok": False,
                        "error_code": "IDEMPOTENCY_OWNER_MISMATCH",
                        "http_status": 403,
                        "message": "Idempotency key belongs to another user account",
                    }
                # Same owner + different payload -> deterministic conflict
                existing_hash = existing["payload_hash"] or ""
                if existing_hash and existing_hash != payload_hash:
                    return {
                        "ok": False,
                        "error_code": "IDEMPOTENCY_PAYLOAD_MISMATCH",
                        "http_status": 409,
                        "message": "Idempotency key reused with different payload parameters",
                    }
                # Same owner + same payload -> identical replay
                return {"ok": True, "job": dict(existing), "idempotent_replay": True}

        status = "awaiting_confirmation" if quote_xu > 0 else "prepared"
        status_reason = "AWAITING_CUSTOMER_CONFIRMATION" if quote_xu > 0 else "PREPARED"

        local_conn.execute(
            """
            INSERT INTO web_voice_clone_jobs (
                job_id, idempotency_key, web_request_id, user_id,
                payload_hash, upload_id, consent_snapshot, display_name,
                quote_xu, pricing_state, status, status_reason,
                provider_execution_count, provider_outcome_state,
                settlement_status, charged_xu, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'unattempted', 'unsettled', 0, ?, ?)
            """,
            (
                web_job_id,
                idempotency_key,
                web_request_id,
                int(canonical_user_id),
                payload_hash,
                str(upload_id),
                1 if consent else 0,
                clean_display_name,
                int(quote_xu),
                str(pricing_state),
                status,
                status_reason,
                now_ts,
                now_ts,
            ),
        )
        cur = local_conn.execute("SELECT * FROM web_voice_clone_jobs WHERE job_id = ?", (web_job_id,))
        row = cur.fetchone()
        return {"ok": True, "job": dict(row) if row else {}, "idempotent_replay": False}
    finally:
        if conn is None:
            local_conn.close()


def claim_web_voice_clone_job_for_execution(
    job_id: str,
    user_id: int,
    *,
    conn: sqlite3.Connection | None = None,
) -> tuple[bool, dict[str, Any] | None]:
    """Atomic compare-and-set claim ensuring exactly-once execution.

    Supports:
    1. Ready states: 'prepared', 'awaiting_confirmation', 'payment_required'
    2. Crash recovery state: 'processing' with settlement_status = 'settling'

    Returns:
        (claimed: bool, job: dict | None)
    """
    local_conn = conn or _get_db_connection()
    now_ts = _utc_now()
    claim_token = f"claim_{secrets.token_hex(8)}"
    try:
        cur = local_conn.execute(
            """
            UPDATE web_voice_clone_jobs
            SET status = 'processing',
                execution_claim = ?,
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
            (claim_token, now_ts, str(job_id), int(user_id)),
        )
        claimed = (cur.rowcount == 1)

        cur = local_conn.execute(
            "SELECT * FROM web_voice_clone_jobs WHERE job_id = ? AND user_id = ?",
            (str(job_id), int(user_id)),
        )
        row = cur.fetchone()
        if not row:
            return claimed, None
        return claimed, dict(row)
    finally:
        if conn is None:
            local_conn.close()


def update_web_voice_clone_job(
    job_id: str,
    *,
    status: str | None = None,
    status_reason: str | None = None,
    execution_claim: str | None = None,
    provider_execution_count: int | None = None,
    provider_outcome_state: str | None = None,
    provider_ambiguity_state: str | None = None,
    settlement_status: str | None = None,
    settlement_idempotency_key: str | None = None,
    canonical_profile_id: int | None = None,
    provider_voice_id: str | None = None,
    provider_file_id: str | None = None,
    provider_route: str | None = None,
    preview_audio_path: str | None = None,
    preview_audio_bytes: int | None = None,
    charged_xu: int | None = None,
    quote_xu: int | None = None,
    pricing_state: str | None = None,
    recovery_markers: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Update job state and persist progress transitions durably."""
    local_conn = conn or _get_db_connection()
    now_ts = _utc_now()
    updates: list[str] = ["updated_at = ?"]
    params: list[Any] = [now_ts]

    if status is not None:
        updates.append("status = ?")
        params.append(str(status))
        if status in ("completed", "failed"):
            updates.append("completed_at = ?")
            params.append(now_ts)
    if status_reason is not None:
        updates.append("status_reason = ?")
        params.append(str(status_reason))
    if execution_claim is not None:
        updates.append("execution_claim = ?")
        params.append(str(execution_claim))
    if provider_execution_count is not None:
        updates.append("provider_execution_count = ?")
        params.append(int(provider_execution_count))
    if provider_outcome_state is not None:
        updates.append("provider_outcome_state = ?")
        params.append(str(provider_outcome_state))
    if provider_ambiguity_state is not None:
        updates.append("provider_ambiguity_state = ?")
        params.append(str(provider_ambiguity_state))
    if settlement_status is not None:
        updates.append("settlement_status = ?")
        params.append(str(settlement_status))
    if settlement_idempotency_key is not None:
        updates.append("settlement_idempotency_key = ?")
        params.append(str(settlement_idempotency_key))
    if canonical_profile_id is not None:
        updates.append("canonical_profile_id = ?")
        params.append(int(canonical_profile_id))
    if provider_voice_id is not None:
        updates.append("provider_voice_id = ?")
        params.append(str(provider_voice_id))
    if provider_file_id is not None:
        updates.append("provider_file_id = ?")
        params.append(str(provider_file_id))
    if provider_route is not None:
        updates.append("provider_route = ?")
        params.append(str(provider_route))
    if preview_audio_path is not None:
        updates.append("preview_audio_path = ?")
        params.append(str(preview_audio_path))
    if preview_audio_bytes is not None:
        updates.append("preview_audio_bytes = ?")
        params.append(int(preview_audio_bytes))
    if charged_xu is not None:
        updates.append("charged_xu = ?")
        params.append(int(charged_xu))
    if quote_xu is not None:
        updates.append("quote_xu = ?")
        params.append(int(quote_xu))
    if pricing_state is not None:
        updates.append("pricing_state = ?")
        params.append(str(pricing_state))
    if recovery_markers is not None:
        updates.append("recovery_markers = ?")
        params.append(str(recovery_markers))

    params.append(str(job_id))
    try:
        local_conn.execute(
            f"UPDATE web_voice_clone_jobs SET {', '.join(updates)} WHERE job_id = ?",
            params,
        )
        cur = local_conn.execute("SELECT * FROM web_voice_clone_jobs WHERE job_id = ?", (str(job_id),))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        if conn is None:
            local_conn.close()


def to_safe_voice_clone_job_projection(job: dict[str, Any]) -> dict[str, Any]:
    """Sanitize job dict for external/Web callers, strictly omitting secrets and paths."""
    status = str(job.get("status") or "")
    profile_id = job.get("canonical_profile_id")
    # Only expose canonical profile ID if completed or profile actively ready
    expose_profile_id = int(profile_id) if profile_id and status in ("completed", "ready") else None

    return {
        "ok": True,
        "job_id": str(job.get("job_id") or ""),
        "idempotency_key": str(job.get("idempotency_key") or ""),
        "user_id": int(job.get("user_id") or 0),
        "upload_id": str(job.get("upload_id") or ""),
        "display_name": str(job.get("display_name") or ""),
        "status": status,
        "status_reason": str(job.get("status_reason") or ""),
        "quote_xu": int(job.get("quote_xu") or 0),
        "charged_xu": int(job.get("charged_xu") or 0),
        "pricing_state": str(job.get("pricing_state") or ""),
        "canonical_profile_id": expose_profile_id,
        "has_preview_audio": bool(int(job.get("preview_audio_bytes") or 0) > 0),
        "preview_audio_bytes": int(job.get("preview_audio_bytes") or 0),
        "provider_execution_count": int(job.get("provider_execution_count") or 0),
        "created_at": str(job.get("created_at") or ""),
        "updated_at": str(job.get("updated_at") or ""),
        "completed_at": str(job.get("completed_at") or "") if job.get("completed_at") else None,
    }
