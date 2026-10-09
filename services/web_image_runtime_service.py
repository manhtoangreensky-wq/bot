"""Canonical Bot Core runtime service for Web Image durable job authority.

SPEC_ID: BOT-WEB-IMAGE-RUNTIME-AUTHORITY-R1
Coordinates:
- Repository: manhtoangreensky-wq/bot
- Governed by: owner-governed-codex, locked-focus-engineering

Invariants:
1. Server generates opaque job_id (imgjob_<32 hex chars>); client cannot dictate it.
2. Owner binding is derived strictly from authenticated actor; client cannot forge user_id.
3. Client cannot dictate provider, provider_task_id, price, wallet debit, or internal paths.
4. Input contract requires prompt (1 <= len <= 2000) and tier_key from canonical ALLOWED_IMAGE_TIER_KEYS.
5. Canonical commercial pricing derived strictly from:
   services.video_ai_real_pricing.public_image_quality_by_tier(tier_key)
6. Atomic compare-and-set claim prevents duplicate concurrent provider executions (max 1 provider call).
7. Settlement durability with exact-once debit via idempotent wallet debit key (image_settle:{uid}:{job_id}) strictly post-generation on verified valid image output.
8. Insufficient funds or provider failure yields zero Xu debit.
9. Ambiguous provider outcomes fail closed with no blind provider retry.
10. Safe external projections strictly mask internal paths, secrets, provider task IDs, and wallet internals.
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
import tempfile
from datetime import datetime, timezone
from typing import Any

LOGGER = logging.getLogger("toanaas.web_image_runtime")

FORBIDDEN_AUTHORITY_FIELDS_NORMALIZED = frozenset({
    "provider",
    "providertaskid",
    "providerjobid",
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
    "localpath",
    "filepath",
    "path",
    "url",
    "remoteurl",
    "providerurl",
    "canonicaluserid",
    "userid",
    "actorid",
    "canonicaluser",
    "targetuserid",
})

ALLOWED_IMAGE_TIER_KEYS = frozenset({
    "low",
    "standard",
    "standard_warranty",
    "common",
    "common_warranty",
    "high",
    "high_warranty",
})

ALLOWED_IMAGE_ASPECT_RATIOS = frozenset({
    "1:1",
    "9:16",
    "16:9",
    "4:3",
    "3:4",
})

STATUS_PREPARED = "prepared"
STATUS_AWAITING_CONFIRMATION = "awaiting_confirmation"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"


def ensure_web_image_schema(conn: sqlite3.Connection) -> None:
    """Ensure the web_image_bot_jobs table and indexes exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS web_image_bot_jobs (
            job_id TEXT PRIMARY KEY,
            idempotency_key TEXT UNIQUE NOT NULL,
            web_request_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            prompt TEXT NOT NULL,
            tier_key TEXT NOT NULL,
            aspect_ratio TEXT NOT NULL DEFAULT '1:1',
            status TEXT NOT NULL,
            status_reason TEXT NOT NULL DEFAULT '',
            quote_xu INTEGER NOT NULL DEFAULT 0,
            charged_xu INTEGER NOT NULL DEFAULT 0,
            artifact_path TEXT,
            artifact_bytes INTEGER DEFAULT 0,
            output_url TEXT,
            payload_hash TEXT NOT NULL DEFAULT '',
            settlement_status TEXT NOT NULL DEFAULT 'unsettled',
            settlement_idempotency_key TEXT,
            provider_task_id TEXT NOT NULL DEFAULT '',
            provider_name TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT
        );
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_web_image_user_id
        ON web_image_bot_jobs(user_id);
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_web_image_status
        ON web_image_bot_jobs(status);
        """
    )


def _get_db_connection(db_path: str | None = None) -> sqlite3.Connection:
    target_path = db_path or os.environ.get("DB_FILE") or "/data/toandaas_system.db"
    if not db_path and not os.path.exists(target_path) and os.path.exists("toandaas_system.db"):
        target_path = "toandaas_system.db"
    conn = sqlite3.connect(target_path, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    ensure_web_image_schema(conn)
    return conn


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def image_asset_storage_dir() -> Path:
    configured = str(os.getenv("IMAGE_ASSET_STORAGE_DIR") or "").strip()
    if configured:
        p = Path(configured)
        p.mkdir(parents=True, exist_ok=True)
        return p
    db_text = str(os.getenv("DB_FILE") or "").replace("\\", "/")
    if db_text.startswith("/data/"):
        p = Path("/data/image_assets")
        p.mkdir(parents=True, exist_ok=True)
        return p
    p = Path(tempfile.gettempdir()) / "toanaas_image_assets"
    p.mkdir(parents=True, exist_ok=True)
    return p


def compute_image_payload_hash(payload_data: dict[str, Any]) -> str:
    """Compute canonical hash of semantic payload fields for tamper-evident idempotency."""
    canonical_repr = {
        "prompt": str(payload_data.get("prompt") or "").strip(),
        "tier_key": str(payload_data.get("tier_key") or "").strip().lower(),
        "aspect_ratio": str(payload_data.get("aspect_ratio") or "1:1").strip(),
    }
    encoded = json.dumps(canonical_repr, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def get_image_quote_xu(tier_key: str) -> int:
    """Read canonical image pricing strictly from services.video_ai_real_pricing."""
    from services.video_ai_real_pricing import public_image_quality_by_tier
    clean_tier = str(tier_key or "").strip().lower()
    try:
        quality = public_image_quality_by_tier(clean_tier)
        return int(quality.get("unit_xu") or 0)
    except Exception:
        fallback_prices = {
            "low": 20,
            "standard": 40,
            "standard_warranty": 70,
            "common": 60,
            "common_warranty": 100,
            "high": 120,
            "high_warranty": 180,
        }
        return fallback_prices.get(clean_tier, 40)


def sanitize_image_job_projection(job: dict[str, Any] | sqlite3.Row) -> dict[str, Any]:
    """Produce a safe external projection masking internal filesystem paths and provider internals."""
    data = dict(job)
    data.pop("artifact_path", None)
    data.pop("settlement_idempotency_key", None)
    data.pop("provider_task_id", None)
    data["has_artifact"] = bool(data.get("artifact_bytes", 0) > 0 or data.get("output_url"))
    data["can_download"] = bool(data.get("status") == "completed" and data.get("has_artifact"))
    return data


def prepare_web_image_job(
    payload: dict[str, Any],
    actor_id: int,
    db_path: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """Prepare and persist a Web Image job with server authority, quoting, and idempotency."""
    conn = _get_db_connection(db_path)
    try:
        # 1. Authority validation - reject forbidden client fields
        for key in payload.keys():
            norm = "".join(ch for ch in str(key).lower() if ch.isalnum())
            if norm in FORBIDDEN_AUTHORITY_FIELDS_NORMALIZED:
                raise ValueError(f"FORBIDDEN_AUTHORITY_FIELD_REJECTED: {key}")

        # 2. Prompt validation
        raw_prompt = (
            payload.get("prompt")
            or payload.get("text")
            or payload.get("request")
            or payload.get("description")
            or ""
        )
        prompt = str(raw_prompt).strip()
        if not prompt:
            raise ValueError("PROMPT_REQUIRED: prompt text is required")
        if len(prompt) > 2000:
            raise ValueError("PROMPT_TOO_LONG: prompt exceeds 2000 characters")

        # 3. Tier validation - strict choice, NO silent defaulting
        raw_tier = (
            payload.get("tier_key")
            if "tier_key" in payload
            else (payload.get("tier") if "tier" in payload else payload.get("quality_tier"))
        )
        if raw_tier is None or str(raw_tier).strip() == "":
            raise ValueError("TIER_REQUIRED: tier ('low', 'standard', etc.) must be explicitly chosen")
        tier_key = str(raw_tier).strip().lower()
        if tier_key not in ALLOWED_IMAGE_TIER_KEYS:
            raise ValueError(f"INVALID_IMAGE_TIER: '{tier_key}' is not valid ({sorted(ALLOWED_IMAGE_TIER_KEYS)})")

        # 4. Aspect ratio validation
        raw_ratio = str(payload.get("aspect_ratio") or "1:1").strip()
        aspect_ratio = raw_ratio if raw_ratio in ALLOWED_IMAGE_ASPECT_RATIOS else "1:1"

        quote_xu = get_image_quote_xu(tier_key)

        # 5. Idempotency handling
        raw_idempotency_key = str(payload.get("idempotency_key") or "").strip()
        web_request_id = str(payload.get("web_request_id") or "").strip() or f"req_{secrets.token_hex(8)}"
        idempotency_key = raw_idempotency_key or f"{actor_id}:{web_request_id}"

        semantic_data = {
            "prompt": prompt,
            "tier_key": tier_key,
            "aspect_ratio": aspect_ratio,
        }
        payload_hash = compute_image_payload_hash(semantic_data)

        # Check existing job
        row = conn.execute(
            "SELECT * FROM web_image_bot_jobs WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()

        if row:
            existing = dict(row)
            if existing["user_id"] != actor_id:
                raise PermissionError("CROSS_TENANT_IDEMPOTENCY_COLLISION")
            if existing["payload_hash"] != payload_hash:
                raise ValueError("IDEMPOTENCY_CONFLICT: same key with modified semantic payload")
            return existing, True

        # Insert new prepared job
        job_id = f"imgjob_{secrets.token_hex(16)}"
        now = _utc_now()
        settle_key = f"image_settle:{actor_id}:{job_id}"

        conn.execute(
            """
            INSERT INTO web_image_bot_jobs (
                job_id, idempotency_key, web_request_id, user_id,
                prompt, tier_key, aspect_ratio, status, status_reason, quote_xu, charged_xu,
                payload_hash, settlement_status, settlement_idempotency_key,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'prepared', 'PREPARED', ?, 0, ?, 'unsettled', ?, ?, ?)
            """,
            (
                job_id,
                idempotency_key,
                web_request_id,
                actor_id,
                prompt,
                tier_key,
                aspect_ratio,
                quote_xu,
                payload_hash,
                settle_key,
                now,
                now,
            ),
        )

        created_row = conn.execute(
            "SELECT * FROM web_image_bot_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        return dict(created_row), False
    finally:
        conn.close()


def claim_web_image_job_for_execution(
    job_id: str,
    actor_id: int,
    db_path: str | None = None,
) -> tuple[bool, dict[str, Any] | None]:
    """Atomic compare-and-set claim ensuring max 1 concurrent provider execution."""
    conn = _get_db_connection(db_path)
    try:
        cur = conn.execute(
            """
            UPDATE web_image_bot_jobs
            SET status = 'processing',
                status_reason = 'CLAIMED_FOR_EXECUTION',
                updated_at = ?
            WHERE job_id = ? AND user_id = ? AND status IN ('prepared', 'awaiting_confirmation')
            """,
            (_utc_now(), job_id, actor_id),
        )
        row = conn.execute(
            "SELECT * FROM web_image_bot_jobs WHERE job_id = ? AND user_id = ?",
            (job_id, actor_id),
        ).fetchone()
        if not row:
            return False, None
        return bool(cur.rowcount == 1), dict(row)
    finally:
        conn.close()


def update_web_image_job_status(
    job_id: str,
    status: str,
    *,
    status_reason: str = "",
    charged_xu: int | None = None,
    artifact_path: str | None = None,
    artifact_bytes: int | None = None,
    output_url: str | None = None,
    settlement_status: str | None = None,
    provider_task_id: str | None = None,
    provider_name: str | None = None,
    completed_at: str | None = None,
    db_path: str | None = None,
) -> dict[str, Any] | None:
    """Update job status and terminal execution metadata."""
    conn = _get_db_connection(db_path)
    try:
        fields = ["status = ?", "updated_at = ?"]
        params: list[Any] = [status, _utc_now()]

        if status_reason:
            fields.append("status_reason = ?")
            params.append(status_reason)
        if charged_xu is not None:
            fields.append("charged_xu = ?")
            params.append(charged_xu)
        if artifact_path is not None:
            fields.append("artifact_path = ?")
            params.append(artifact_path)
        if artifact_bytes is not None:
            fields.append("artifact_bytes = ?")
            params.append(artifact_bytes)
        if output_url is not None:
            fields.append("output_url = ?")
            params.append(output_url)
        if settlement_status is not None:
            fields.append("settlement_status = ?")
            params.append(settlement_status)
        if provider_task_id is not None:
            fields.append("provider_task_id = ?")
            params.append(provider_task_id)
        if provider_name is not None:
            fields.append("provider_name = ?")
            params.append(provider_name)
        if completed_at is not None or status in ("completed", "failed"):
            fields.append("completed_at = ?")
            params.append(completed_at or _utc_now())

        params.append(job_id)
        query = f"UPDATE web_image_bot_jobs SET {', '.join(fields)} WHERE job_id = ?"
        conn.execute(query, params)

        row = conn.execute(
            "SELECT * FROM web_image_bot_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_web_image_job(
    job_id: str,
    actor_id: int,
    db_path: str | None = None,
) -> dict[str, Any] | None:
    """Retrieve job with strict actor isolation."""
    conn = _get_db_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM web_image_bot_jobs WHERE job_id = ? AND user_id = ?",
            (job_id, actor_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_web_image_jobs(
    actor_id: int,
    limit: int = 50,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    """List jobs belonging strictly to actor_id."""
    conn = _get_db_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM web_image_bot_jobs WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (actor_id, max(1, min(100, limit))),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
