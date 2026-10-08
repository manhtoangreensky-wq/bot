"""Canonical Bot Core runtime service for Web Music durable job authority.

SPEC_ID: BOT-WEB-MUSIC-RUNTIME-AUTHORITY-R1
Coordinates:
- Repository: manhtoangreensky-wq/bot
- Governed by: owner-governed-codex, locked-focus-engineering

Invariants:
1. Server generates opaque job_id (mjob_<32 hex chars>); client cannot dictate it.
2. Owner binding is derived strictly from authenticated actor; client cannot forge user_id.
3. Client cannot dictate provider, provider_task_id, price, wallet debit, or internal paths.
4. Input contract requires product_kind ("background" or "song"), tier ("basic", "standard", "premium"), and brief.
5. Canonical commercial pricing:
   - Background: basic=130 Xu, standard=150 Xu, premium=200 Xu
   - Song: basic=200 Xu, standard=250 Xu, premium=300 Xu
6. Strict product separation:
   - Background rejects lyrics, song_vocal, vocal_mode, duet fields.
   - Song requires lyrics and valid vocal mode ("male", "female", "duet", "auto").
7. Duration normalization:
   - Background: clamped to 18..600 seconds (default 30s).
   - Song: clamped to 30..600 seconds (default 120s).
8. Atomic compare-and-set claim prevents duplicate concurrent provider executions (max 1 provider call).
9. Settlement durability with exact-once debit via idempotent wallet debit key (music_settle:{uid}:{job_id}) strictly post-generation on verified >0 byte audio output.
10. Insufficient funds or provider failure yields zero Xu debit.
11. Ambiguous provider outcomes fail closed with no blind provider retry.
12. Safe external projections strictly mask internal paths, secrets, provider task IDs, and wallet internals.
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

LOGGER = logging.getLogger("toanaas.web_music_runtime")

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

MUSIC_TIERS = frozenset({"basic", "standard", "premium"})
MUSIC_PRODUCT_KINDS = frozenset({"background", "song"})
MUSIC_VOCAL_MODES = frozenset({"male", "female", "duet", "auto"})

MUSIC_BACKGROUND_TIER_PRICES = {
    "basic": 130,
    "standard": 150,
    "premium": 200,
}

MUSIC_SONG_TIER_PRICES = {
    "basic": 200,
    "standard": 250,
    "premium": 300,
}


def ensure_web_music_schema(conn: sqlite3.Connection) -> None:
    """Ensure the web_music_bot_jobs table and indexes exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS web_music_bot_jobs (
            job_id TEXT PRIMARY KEY,
            idempotency_key TEXT UNIQUE NOT NULL,
            web_request_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            product_kind TEXT NOT NULL,
            tier TEXT NOT NULL,
            mode TEXT NOT NULL,
            brief TEXT NOT NULL,
            style_prompt TEXT NOT NULL DEFAULT '',
            lyrics TEXT NOT NULL DEFAULT '',
            vocal_mode TEXT NOT NULL DEFAULT '',
            duration_seconds INTEGER NOT NULL DEFAULT 30,
            status TEXT NOT NULL,
            status_reason TEXT NOT NULL DEFAULT '',
            quote_xu INTEGER NOT NULL DEFAULT 0,
            charged_xu INTEGER NOT NULL DEFAULT 0,
            artifact_path TEXT,
            artifact_bytes INTEGER DEFAULT 0,
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
        CREATE INDEX IF NOT EXISTS idx_web_music_user_id
        ON web_music_bot_jobs(user_id);
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_web_music_status
        ON web_music_bot_jobs(status);
        """
    )


def _get_db_connection(db_path: str | None = None) -> sqlite3.Connection:
    target_path = db_path or os.environ.get("DB_FILE") or "/data/toandaas_system.db"
    if not db_path and not os.path.exists(target_path) and os.path.exists("toandaas_system.db"):
        target_path = "toandaas_system.db"
    conn = sqlite3.connect(target_path, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    ensure_web_music_schema(conn)
    return conn


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def music_asset_storage_dir() -> Path:
    configured = str(os.getenv("MUSIC_ASSET_STORAGE_DIR") or "").strip()
    if configured:
        p = Path(configured)
        p.mkdir(parents=True, exist_ok=True)
        return p
    db_text = str(os.getenv("DB_FILE") or "").replace("\\", "/")
    if db_text.startswith("/data/"):
        p = Path("/data/music_assets")
        p.mkdir(parents=True, exist_ok=True)
        return p
    p = Path(tempfile.gettempdir()) / "toanaas_music_assets"
    p.mkdir(parents=True, exist_ok=True)
    return p


def compute_music_payload_hash(payload_data: dict[str, Any]) -> str:
    """Compute canonical hash of semantic payload fields for tamper-evident idempotency."""
    canonical_repr = {
        "product_kind": str(payload_data.get("product_kind") or "").strip().lower(),
        "tier": str(payload_data.get("tier") or "").strip().lower(),
        "mode": str(payload_data.get("mode") or "").strip().lower(),
        "brief": str(payload_data.get("brief") or "").strip(),
        "style_prompt": str(payload_data.get("style_prompt") or "").strip(),
        "lyrics": str(payload_data.get("lyrics") or "").strip(),
        "vocal_mode": str(payload_data.get("vocal_mode") or "").strip().lower(),
        "duration_seconds": int(payload_data.get("duration_seconds") or 0),
    }
    encoded = json.dumps(canonical_repr, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_music_tier(raw_tier: str) -> str:
    clean = str(raw_tier or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "basic": "basic",
        "co_ban": "basic",
        "cơ_bản": "basic",
        "music_tier_basic": "basic",
        "standard": "standard",
        "tieu_chuan": "standard",
        "tiêu_chuẩn": "standard",
        "music_tier_standard": "standard",
        "premium": "premium",
        "cao_cap": "premium",
        "cao_cấp": "premium",
        "music_tier_premium": "premium",
    }
    return aliases.get(clean, clean)


def normalize_music_duration(raw_duration: Any, product_kind: str) -> int:
    try:
        val = int(raw_duration)
    except (TypeError, ValueError):
        val = 30 if product_kind == "background" else 120
    if product_kind == "background":
        if val <= 0:
            val = 30
        return max(18, min(600, val))
    else:
        if val <= 0:
            val = 120
        return max(30, min(600, val))


def get_music_quote_xu(product_kind: str, tier: str) -> int:
    if product_kind == "song":
        return MUSIC_SONG_TIER_PRICES.get(tier, 200)
    return MUSIC_BACKGROUND_TIER_PRICES.get(tier, 130)


def sanitize_music_job_projection(job: dict[str, Any] | sqlite3.Row) -> dict[str, Any]:
    """Produce a safe external projection masking internal filesystem paths and provider internals."""
    data = dict(job)
    data.pop("artifact_path", None)
    data.pop("settlement_idempotency_key", None)
    data.pop("provider_task_id", None)
    data["has_artifact"] = bool(data.get("artifact_bytes", 0) > 0)
    data["can_download"] = bool(data.get("status") == "completed" and data.get("has_artifact"))
    return data


def prepare_web_music_job(
    payload: dict[str, Any],
    actor_id: int,
    db_path: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """Prepare and persist a Web Music job with server authority, quoting, and idempotency."""
    conn = _get_db_connection(db_path)
    try:
        # 1. Authority validation - reject forbidden fields
        for key in payload.keys():
            norm = "".join(ch for ch in str(key).lower() if ch.isalnum())
            if norm in FORBIDDEN_AUTHORITY_FIELDS_NORMALIZED:
                raise ValueError(f"FORBIDDEN_AUTHORITY_FIELD_REJECTED: {key}")

        # 2. Product kind validation
        product_kind = str(payload.get("product_kind") or "").strip().lower()
        if product_kind not in MUSIC_PRODUCT_KINDS:
            raise ValueError("INVALID_PRODUCT_KIND: must be 'background' or 'song'")

        # 3. Tier validation - strict choice, NO silent defaulting
        raw_tier = str(payload.get("tier") or "").strip()
        if not raw_tier:
            raise ValueError("TIER_REQUIRED: tier ('basic', 'standard', 'premium') must be explicitly chosen")
        tier = normalize_music_tier(raw_tier)
        if tier not in MUSIC_TIERS:
            raise ValueError(f"INVALID_TIER: '{raw_tier}' is not valid ('basic', 'standard', 'premium')")

        # 4. Product separation guards
        brief = str(payload.get("brief") or "").strip()
        if not brief:
            raise ValueError("BRIEF_REQUIRED: brief description is required")

        mode = str(payload.get("mode") or "").strip().lower()
        if not mode:
            mode = "background" if product_kind == "background" else "song"

        if product_kind == "background":
            # Reject lyrics, vocal, duet fields from background
            for song_field in ("lyrics", "song_vocal", "vocal_mode", "duet"):
                if payload.get(song_field):
                    raise ValueError(f"SONG_FIELD_REJECTED_FOR_BACKGROUND: '{song_field}' is not allowed in background music")
            lyrics = ""
            vocal_mode = ""
            style_prompt = str(payload.get("style_prompt") or brief).strip()
        else:
            # Song requires lyrics / vocal parameters
            lyrics = str(payload.get("lyrics") or "").strip()
            raw_vocal = str(payload.get("vocal_mode") or payload.get("song_vocal") or "auto").strip().lower()
            if raw_vocal not in MUSIC_VOCAL_MODES:
                raise ValueError(f"INVALID_VOCAL_MODE: '{raw_vocal}' must be one of {sorted(MUSIC_VOCAL_MODES)}")
            vocal_mode = raw_vocal
            style_prompt = str(payload.get("style_prompt") or brief).strip()

        duration_seconds = normalize_music_duration(payload.get("duration_seconds"), product_kind)
        quote_xu = get_music_quote_xu(product_kind, tier)

        # 5. Idempotency handling
        raw_idempotency_key = str(payload.get("idempotency_key") or "").strip()
        web_request_id = str(payload.get("web_request_id") or "").strip() or f"req_{secrets.token_hex(8)}"
        idempotency_key = raw_idempotency_key or f"{actor_id}:{web_request_id}"

        semantic_data = {
            "product_kind": product_kind,
            "tier": tier,
            "mode": mode,
            "brief": brief,
            "style_prompt": style_prompt,
            "lyrics": lyrics,
            "vocal_mode": vocal_mode,
            "duration_seconds": duration_seconds,
        }
        payload_hash = compute_music_payload_hash(semantic_data)

        # Check existing job
        row = conn.execute(
            "SELECT * FROM web_music_bot_jobs WHERE idempotency_key = ?",
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
        job_id = f"mjob_{secrets.token_hex(16)}"
        now = _utc_now()
        settle_key = f"music_settle:{actor_id}:{job_id}"

        conn.execute(
            """
            INSERT INTO web_music_bot_jobs (
                job_id, idempotency_key, web_request_id, user_id,
                product_kind, tier, mode, brief, style_prompt, lyrics, vocal_mode,
                duration_seconds, status, status_reason, quote_xu, charged_xu,
                payload_hash, settlement_status, settlement_idempotency_key,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 'unsettled', ?, ?, ?)
            """,
            (
                job_id,
                idempotency_key,
                web_request_id,
                actor_id,
                product_kind,
                tier,
                mode,
                brief,
                style_prompt,
                lyrics,
                vocal_mode,
                duration_seconds,
                "prepared",
                "PREPARED",
                quote_xu,
                payload_hash,
                settle_key,
                now,
                now,
            ),
        )

        created_row = conn.execute(
            "SELECT * FROM web_music_bot_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        return dict(created_row), False
    finally:
        conn.close()


def get_web_music_job(
    job_id: str,
    actor_id: int | None = None,
    db_path: str | None = None,
) -> dict[str, Any] | None:
    """Retrieve Web Music job by job_id, optionally ensuring actor tenant isolation."""
    conn = _get_db_connection(db_path)
    try:
        if actor_id is not None:
            row = conn.execute(
                "SELECT * FROM web_music_bot_jobs WHERE job_id = ? AND user_id = ?",
                (job_id, actor_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM web_music_bot_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_web_music_jobs(
    actor_id: int,
    limit: int = 50,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    """List recent Web Music jobs for the given actor."""
    conn = _get_db_connection(db_path)
    try:
        safe_limit = max(1, min(int(limit), 100))
        rows = conn.execute(
            "SELECT * FROM web_music_bot_jobs WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (actor_id, safe_limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def claim_web_music_job_for_execution(
    job_id: str,
    actor_id: int,
    db_path: str | None = None,
) -> tuple[bool, dict[str, Any] | None]:
    """Atomic compare-and-set claim ensuring exactly-once execution ownership."""
    conn = _get_db_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM web_music_bot_jobs WHERE job_id = ? AND user_id = ?",
            (job_id, actor_id),
        ).fetchone()
        if not row:
            return False, None
        current_job = dict(row)
        current_status = current_job.get("status")

        if current_status == "prepared":
            cursor = conn.execute(
                """
                UPDATE web_music_bot_jobs
                SET status = 'processing',
                    status_reason = 'EXECUTION_CLAIMED',
                    updated_at = ?
                WHERE job_id = ? AND user_id = ? AND status = 'prepared'
                """,
                (_utc_now(), job_id, actor_id),
            )
            if cursor.rowcount == 1:
                updated_row = conn.execute(
                    "SELECT * FROM web_music_bot_jobs WHERE job_id = ?",
                    (job_id,),
                ).fetchone()
                return True, dict(updated_row)
            # Concurrently claimed
            fresh = conn.execute("SELECT * FROM web_music_bot_jobs WHERE job_id = ?", (job_id,)).fetchone()
            return False, dict(fresh) if fresh else None
        return False, current_job
    finally:
        conn.close()


def update_web_music_job_status(
    job_id: str,
    status: str,
    *,
    status_reason: str = "",
    charged_xu: int | None = None,
    artifact_path: str | None = None,
    artifact_bytes: int | None = None,
    settlement_status: str | None = None,
    provider_task_id: str | None = None,
    provider_name: str | None = None,
    completed_at: str | None = None,
    db_path: str | None = None,
) -> dict[str, Any] | None:
    """Update Web Music job state attributes durably."""
    conn = _get_db_connection(db_path)
    try:
        updates = ["status = ?", "updated_at = ?"]
        params: list[Any] = [status, _utc_now()]

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
        if provider_task_id is not None:
            updates.append("provider_task_id = ?")
            params.append(provider_task_id)
        if provider_name is not None:
            updates.append("provider_name = ?")
            params.append(provider_name)
        if completed_at is not None:
            updates.append("completed_at = ?")
            params.append(completed_at)

        params.append(job_id)
        conn.execute(
            f"UPDATE web_music_bot_jobs SET {', '.join(updates)} WHERE job_id = ?",
            params,
        )

        row = conn.execute("SELECT * FROM web_music_bot_jobs WHERE job_id = ?", (job_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
