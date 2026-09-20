"""services/autopost_product_video_adapter.py

Canonical Product Video -> AutoPost Adapter Authority.
Governed under TOAN AAS Owner-Governed Codex (P0.AUTOPOST.S3).

Core Invariants:
1. Canonical Product Video Authority:
   Rereads canonical Product Video truth through existing resolvers only.
   Never trusts caller-supplied artifact paths or hashes.
2. Decoupled Producer Safety:
   Any AutoPost adapter failure or rejection never reverts, fails, or requeues Product Video.
3. Explicit User-Intent Opt-In:
   AutoPost only processes when an explicit durable intent is registered.
   Modes: OFF, DRAFT_ONLY, SCHEDULE_NOW, SCHEDULE_AT.
4. Post-Commit Execution Only:
   Runs only after Product Video durable state is committed.
5. Publish-Only Isolation:
   No producer rerender, no social provider calls, no wallet mutations.
"""

from __future__ import annotations

import datetime
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Optional

from services import autopost_asset_handoff as aah
from services import autopost_scheduler as aps


# =========================================================================
# 1. ENUMS & CONSTANTS
# =========================================================================

class ProductVideoAutoPostMode(str, Enum):
    OFF = "OFF"
    DRAFT_ONLY = "DRAFT_ONLY"
    SCHEDULE_NOW = "SCHEDULE_NOW"
    SCHEDULE_AT = "SCHEDULE_AT"


class AdapterResultStatus(str, Enum):
    PENDING = "PENDING"
    HANDOFF_READY = "HANDOFF_READY"
    DRAFT_READY = "DRAFT_READY"
    SCHEDULED = "SCHEDULED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


ALLOWED_INTENT_MODES = {
    ProductVideoAutoPostMode.OFF.value,
    ProductVideoAutoPostMode.DRAFT_ONLY.value,
    ProductVideoAutoPostMode.SCHEDULE_NOW.value,
    ProductVideoAutoPostMode.SCHEDULE_AT.value,
}

ALLOWED_CHANNELS = {"tiktok", "youtube", "facebook", "instagram", "telegram"}
MAX_CAPTION_LENGTH = 2000


# =========================================================================
# 2. SCHEMA MANAGEMENT
# =========================================================================

def ensure_autopost_product_video_adapter_schema(conn: sqlite3.Connection) -> None:
    """Ensure the durable autopost_product_video_intents table and indexes exist."""
    aah.ensure_autopost_handoff_schema(conn)
    aps.ensure_autopost_scheduler_schema(conn)

    conn.execute(
        """CREATE TABLE IF NOT EXISTS autopost_product_video_intents (
            intent_id TEXT PRIMARY KEY,
            owner_id INTEGER NOT NULL,
            product_video_job_id INTEGER NOT NULL,
            mode TEXT NOT NULL,
            schedule_at TEXT,
            selected_channels_json TEXT NOT NULL DEFAULT '[]',
            caption_override TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING',
            last_blocker_code TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(owner_id, product_video_job_id)
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_apvi_owner ON autopost_product_video_intents (owner_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_apvi_job ON autopost_product_video_intents (product_video_job_id)"
    )
    conn.commit()


# =========================================================================
# 3. INTENT REGISTRATION & LOOKUP
# =========================================================================

def _row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    try:
        return {k: row[k] for k in row.keys()}
    except Exception:
        return dict(row)


def register_product_video_autopost_intent(
    conn: sqlite3.Connection,
    owner_id: int,
    product_video_job_id: int,
    mode: str | ProductVideoAutoPostMode,
    schedule_at: Optional[str] = None,
    selected_channels: Optional[list[str]] = None,
    caption_override: Optional[str] = None,
    now: Optional[str] = None,
) -> tuple[Optional[dict[str, Any]], str]:
    """Register an explicit, durable AutoPost intent for a Product Video job.

    Enforces:
    - owner_id and product_video_job_id must be valid positive integers
    - mode must be in ALLOWED_INTENT_MODES
    - schedule_at validated strictly for SCHEDULE_AT mode (strict canonical UTC)
    - selected_channels bounded to metadata allowlist
    - caption_override bounded length
    - Idempotent: re-registration with identical parameters returns existing record.
    - Conflicting update on existing intent fails closed.
    """
    ensure_autopost_product_video_adapter_schema(conn)

    try:
        norm_owner_id = int(owner_id)
        norm_job_id = int(product_video_job_id)
        if norm_owner_id <= 0 or norm_job_id <= 0:
            return None, "invalid_ids"
    except (ValueError, TypeError):
        return None, "invalid_ids"

    clean_mode = str(getattr(mode, "value", mode) or "").strip().upper()
    if clean_mode not in ALLOWED_INTENT_MODES:
        return None, f"unsupported_mode:{clean_mode}"

    norm_schedule_at: Optional[str] = None
    if clean_mode == ProductVideoAutoPostMode.SCHEDULE_AT.value:
        if not schedule_at:
            return None, "schedule_at_required_for_schedule_at_mode"
        validated_sched, sched_err = aps.parse_and_validate_utc(schedule_at)
        if not validated_sched:
            return None, f"invalid_schedule_at:{sched_err}"
        norm_schedule_at = validated_sched
    elif clean_mode == ProductVideoAutoPostMode.SCHEDULE_NOW.value:
        if schedule_at is not None:
            validated_sched, sched_err = aps.parse_and_validate_utc(schedule_at)
            if not validated_sched:
                return None, f"invalid_schedule_at:{sched_err}"
            norm_schedule_at = validated_sched

    # Bounded channels metadata validation
    norm_channels: list[str] = []
    if selected_channels is not None:
        if not isinstance(selected_channels, (list, tuple)):
            return None, "invalid_selected_channels_format"
        for ch in selected_channels:
            clean_ch = str(ch or "").strip().lower()
            if clean_ch and clean_ch not in ALLOWED_CHANNELS:
                return None, f"unsupported_channel:{clean_ch}"
            if clean_ch and clean_ch not in norm_channels:
                norm_channels.append(clean_ch)
    channels_json = json.dumps(norm_channels)

    # Bounded caption validation
    clean_caption: Optional[str] = None
    if caption_override is not None:
        clean_caption = str(caption_override).strip()[:MAX_CAPTION_LENGTH]

    if now is not None:
        norm_now, time_err = aps.parse_and_validate_utc(now)
        if not norm_now:
            return None, time_err
    else:
        norm_now = aps.canonical_utc_now()

    cur = conn.cursor()
    cur.execute(
        """SELECT * FROM autopost_product_video_intents
           WHERE owner_id=? AND product_video_job_id=? LIMIT 1""",
        (norm_owner_id, norm_job_id),
    )
    existing_row = cur.fetchone()
    if existing_row:
        existing = _row_to_dict(existing_row)
        # Check identical parameters
        channels_match = json.loads(existing.get("selected_channels_json") or "[]") == norm_channels
        mode_match = existing.get("mode") == clean_mode
        sched_match = (existing.get("schedule_at") or None) == norm_schedule_at
        caption_match = (existing.get("caption_override") or None) == clean_caption

        if channels_match and mode_match and sched_match and caption_match:
            return existing, "idempotent_existing"
        return None, "intent_conflict_already_registered"

    intent_hash = hashlib.sha256(f"{norm_owner_id}:{norm_job_id}".encode("utf-8")).hexdigest()[:20]
    intent_id = f"intent_pv_{intent_hash}"

    try:
        conn.execute(
            """INSERT INTO autopost_product_video_intents (
                intent_id, owner_id, product_video_job_id, mode, schedule_at,
                selected_channels_json, caption_override, status, last_blocker_code,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', NULL, ?, ?)""",
            (
                intent_id,
                norm_owner_id,
                norm_job_id,
                clean_mode,
                norm_schedule_at,
                channels_json,
                clean_caption,
                norm_now,
                norm_now,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        cur.execute(
            """SELECT * FROM autopost_product_video_intents
               WHERE owner_id=? AND product_video_job_id=? LIMIT 1""",
            (norm_owner_id, norm_job_id),
        )
        row = cur.fetchone()
        if row:
            return _row_to_dict(row), "idempotent_existing"
        raise

    cur.execute(
        "SELECT * FROM autopost_product_video_intents WHERE intent_id=? LIMIT 1",
        (intent_id,),
    )
    return _row_to_dict(cur.fetchone()), "registered"


def get_product_video_autopost_intent(
    conn: sqlite3.Connection,
    owner_id: int,
    product_video_job_id: int,
) -> Optional[dict[str, Any]]:
    """Retrieve canonical registered intent for (owner_id, product_video_job_id) if any."""
    ensure_autopost_product_video_adapter_schema(conn)
    cur = conn.cursor()
    cur.execute(
        """SELECT * FROM autopost_product_video_intents
           WHERE owner_id=? AND product_video_job_id=? LIMIT 1""",
        (int(owner_id), int(product_video_job_id)),
    )
    row = cur.fetchone()
    return _row_to_dict(row) if row else None


# =========================================================================
# 4. ADAPTER EXECUTION (POST-COMMIT)
# =========================================================================

def _record_intent_blocker(
    conn: sqlite3.Connection,
    intent_id: str,
    blocker_code: str,
) -> None:
    """Safely record adapter blocker code on intent for observability."""
    try:
        conn.execute(
            """UPDATE autopost_product_video_intents
               SET status='BLOCKED', last_blocker_code=?, updated_at=?
               WHERE intent_id=?""",
            (str(blocker_code)[:100], aps.canonical_utc_now(), intent_id),
        )
        conn.commit()
    except Exception:
        pass


def _apply_draft_customizations(
    conn: sqlite3.Connection,
    draft_id: str,
    intent: dict[str, Any],
) -> None:
    """Apply caption override and selected channels from intent onto publication draft."""
    caption_override = intent.get("caption_override")
    channels_json = intent.get("selected_channels_json")

    updates: list[str] = []
    params: list[Any] = []

    if caption_override is not None and str(caption_override).strip():
        updates.append("caption_draft=?")
        params.append(str(caption_override).strip()[:MAX_CAPTION_LENGTH])

    if channels_json:
        try:
            channels = json.loads(channels_json)
            if isinstance(channels, list) and len(channels) > 0:
                updates.append("selected_channels_json=?")
                params.append(json.dumps(channels))
        except Exception:
            pass

    if updates:
        params.append(draft_id)
        conn.execute(
            f"UPDATE autopost_publication_drafts SET {', '.join(updates)} WHERE draft_id=?",
            params,
        )
        conn.commit()


def process_product_video_autopost_handoff(
    conn: sqlite3.Connection,
    product_video_job_id: int,
    owner_id: int,
    handoff_receipt: Optional[dict[str, Any] | aah.HandoffReceipt] = None,
    now: Optional[str] = None,
) -> tuple[dict[str, Any], str]:
    """Execute the Product Video -> AutoPost adapter seam post-producer commit.

    Enforces:
    - Post-commit only: rejects execution if conn.in_transaction is True
    - Rereads canonical Product Video truth via canonical resolver
    - Explicit opt-in only: if no intent registered or mode=OFF, does not create drafts or queue rows
    - Mode DRAFT_ONLY: creates/reuses PLANNED publication draft
    - Mode SCHEDULE_NOW / SCHEDULE_AT: creates/reuses draft, approves, and schedules
    - Schedule conflicts with differing timestamps fail closed
    - Any adapter failure leaves Product Video terminal truth intact
    """
    if conn.in_transaction:
        return {
            "attempted": True,
            "created_or_reused": False,
            "mode": None,
            "intent_id": None,
            "handoff_id": None,
            "draft_id": None,
            "publication_id": None,
            "state": None,
            "blocker": "caller_in_transaction",
        }, "caller_in_transaction"

    ensure_autopost_product_video_adapter_schema(conn)

    # 1. Reread canonical Product Video truth using canonical resolver
    asset, err = aah.adapt_product_video_output(
        conn,
        job_id=int(product_video_job_id),
        requesting_user_id=int(owner_id),
    )
    if not asset:
        return {
            "attempted": True,
            "created_or_reused": False,
            "mode": None,
            "intent_id": None,
            "handoff_id": None,
            "draft_id": None,
            "publication_id": None,
            "state": None,
            "blocker": f"canonical_resolver_failed:{err}",
        }, f"canonical_resolver_failed:{err}"

    # 2. Check for explicit intent
    intent = get_product_video_autopost_intent(
        conn,
        owner_id=int(owner_id),
        product_video_job_id=int(product_video_job_id),
    )

    norm_handoff_id: Optional[str] = None
    if handoff_receipt:
        if isinstance(handoff_receipt, dict):
            norm_handoff_id = handoff_receipt.get("handoff_id")
        else:
            norm_handoff_id = getattr(handoff_receipt, "handoff_id", None)

    if not intent:
        return {
            "attempted": False,
            "mode": "NONE",
            "intent_id": None,
            "handoff_id": norm_handoff_id,
            "draft_id": None,
            "publication_id": None,
            "state": None,
            "blocker": "no_intent_registered",
        }, "no_intent_registered"

    mode = str(intent.get("mode") or "").strip().upper()
    intent_id = str(intent.get("intent_id") or "")

    # 3. MODE: OFF
    if mode == ProductVideoAutoPostMode.OFF.value:
        try:
            conn.execute(
                """UPDATE autopost_product_video_intents
                   SET status='CANCELLED', last_blocker_code=NULL, updated_at=?
                   WHERE intent_id=?""",
                (aps.canonical_utc_now(), intent_id),
            )
            conn.commit()
        except Exception:
            pass

        return {
            "attempted": True,
            "mode": ProductVideoAutoPostMode.OFF.value,
            "intent_id": intent_id,
            "handoff_id": norm_handoff_id,
            "draft_id": None,
            "publication_id": None,
            "state": None,
            "blocker": None,
        }, "off"

    # 4. Ensure canonical handoff exists
    if not norm_handoff_id:
        cur = conn.cursor()
        cur.execute(
            """SELECT handoff_id FROM autopost_handoff_receipts
               WHERE source_product='video_product' AND source_job_id=?
               ORDER BY created_at DESC LIMIT 1""",
            (str(product_video_job_id),),
        )
        h_row = cur.fetchone()
        if h_row:
            norm_handoff_id = h_row[0]
        else:
            h_rec, h_err = aah.create_autopost_handoff_from_source(
                conn,
                source_product="video_product",
                source_ref=int(product_video_job_id),
                requesting_user_id=int(owner_id),
            )
            if not h_rec:
                _record_intent_blocker(conn, intent_id, f"handoff_failed:{h_err}")
                return {
                    "attempted": True,
                    "mode": mode,
                    "intent_id": intent_id,
                    "handoff_id": None,
                    "draft_id": None,
                    "publication_id": None,
                    "state": None,
                    "blocker": f"handoff_failed:{h_err}",
                }, f"handoff_failed:{h_err}"
            norm_handoff_id = h_rec.handoff_id

    # 5. MODE: DRAFT_ONLY
    if mode == ProductVideoAutoPostMode.DRAFT_ONLY.value:
        draft, d_err = aah.receive_autopost_handoff_to_draft(
            conn,
            handoff_id=norm_handoff_id,
            requesting_user_id=int(owner_id),
        )
        if not draft:
            _record_intent_blocker(conn, intent_id, f"draft_failed:{d_err}")
            return {
                "attempted": True,
                "mode": mode,
                "intent_id": intent_id,
                "handoff_id": norm_handoff_id,
                "draft_id": None,
                "publication_id": None,
                "state": None,
                "blocker": f"draft_failed:{d_err}",
            }, f"draft_failed:{d_err}"

        _apply_draft_customizations(conn, draft.draft_id, intent)
        try:
            conn.execute(
                """UPDATE autopost_product_video_intents
                   SET status='DRAFT_READY', last_blocker_code=NULL, updated_at=?
                   WHERE intent_id=?""",
                (aps.canonical_utc_now(), intent_id),
            )
            conn.commit()
        except Exception:
            pass

        return {
            "attempted": True,
            "mode": ProductVideoAutoPostMode.DRAFT_ONLY.value,
            "intent_id": intent_id,
            "handoff_id": norm_handoff_id,
            "draft_id": draft.draft_id,
            "publication_id": None,
            "state": "PLANNED",
            "blocker": None,
        }, "draft_ready"

    # 6. MODE: SCHEDULE_NOW / SCHEDULE_AT
    if mode in (ProductVideoAutoPostMode.SCHEDULE_NOW.value, ProductVideoAutoPostMode.SCHEDULE_AT.value):
        draft, d_err = aah.receive_autopost_handoff_to_draft(
            conn,
            handoff_id=norm_handoff_id,
            requesting_user_id=int(owner_id),
        )
        if not draft:
            _record_intent_blocker(conn, intent_id, f"draft_failed:{d_err}")
            return {
                "attempted": True,
                "mode": mode,
                "intent_id": intent_id,
                "handoff_id": norm_handoff_id,
                "draft_id": None,
                "publication_id": None,
                "state": None,
                "blocker": f"draft_failed:{d_err}",
            }, f"draft_failed:{d_err}"

        _apply_draft_customizations(conn, draft.draft_id, intent)

        # Determine target schedule time
        if mode == ProductVideoAutoPostMode.SCHEDULE_NOW.value:
            if now is not None:
                norm_now, time_err = aps.parse_and_validate_utc(now)
                if not norm_now:
                    _record_intent_blocker(conn, intent_id, f"schedule_time_invalid:{time_err}")
                    return {
                        "attempted": True,
                        "mode": mode,
                        "intent_id": intent_id,
                        "handoff_id": norm_handoff_id,
                        "draft_id": draft.draft_id,
                        "publication_id": None,
                        "state": "PLANNED",
                        "blocker": f"schedule_time_invalid:{time_err}",
                    }, f"schedule_time_invalid:{time_err}"
                target_schedule_at = norm_now
            else:
                target_schedule_at = aps.canonical_utc_now()
        else:  # SCHEDULE_AT
            raw_sched = intent.get("schedule_at")
            target_schedule_at, time_err = aps.parse_and_validate_utc(raw_sched)
            if not target_schedule_at:
                _record_intent_blocker(conn, intent_id, f"schedule_time_invalid:{time_err}")
                return {
                    "attempted": True,
                    "mode": mode,
                    "intent_id": intent_id,
                    "handoff_id": norm_handoff_id,
                    "draft_id": draft.draft_id,
                    "publication_id": None,
                    "state": "PLANNED",
                    "blocker": f"schedule_time_invalid:{time_err}",
                }, f"schedule_time_invalid:{time_err}"

        # Check existing queue item for schedule conflicts or idempotent replay
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM autopost_publication_queue WHERE draft_id=? LIMIT 1",
            (draft.draft_id,),
        )
        q_row = cur.fetchone()
        if q_row:
            q_dict = _row_to_dict(q_row)
            existing_state = q_dict.get("state")
            existing_sched = q_dict.get("schedule_at")
            if existing_state == "SCHEDULED":
                if existing_sched and existing_sched != target_schedule_at:
                    _record_intent_blocker(conn, intent_id, "schedule_conflict_different_timestamp")
                    return {
                        "attempted": True,
                        "mode": mode,
                        "intent_id": intent_id,
                        "handoff_id": norm_handoff_id,
                        "draft_id": draft.draft_id,
                        "publication_id": q_dict.get("publication_id"),
                        "state": "SCHEDULED",
                        "blocker": "schedule_conflict_different_timestamp",
                    }, "schedule_conflict_different_timestamp"
                # Idempotent re-execution of exact schedule
                return {
                    "attempted": True,
                    "mode": mode,
                    "intent_id": intent_id,
                    "handoff_id": norm_handoff_id,
                    "draft_id": draft.draft_id,
                    "publication_id": q_dict.get("publication_id"),
                    "state": "SCHEDULED",
                    "blocker": None,
                }, "scheduled"

        # Approve draft through scheduler authority
        appr_pub, appr_err = aps.approve_publication_draft(
            conn,
            draft_id=draft.draft_id,
            requesting_user_id=int(owner_id),
        )
        if not appr_pub:
            _record_intent_blocker(conn, intent_id, f"approval_failed:{appr_err}")
            return {
                "attempted": True,
                "mode": mode,
                "intent_id": intent_id,
                "handoff_id": norm_handoff_id,
                "draft_id": draft.draft_id,
                "publication_id": None,
                "state": "PLANNED",
                "blocker": f"approval_failed:{appr_err}",
            }, f"approval_failed:{appr_err}"

        # Schedule through scheduler authority
        sched_pub, sched_err = aps.schedule_publication(
            conn,
            draft_id=draft.draft_id,
            requesting_user_id=int(owner_id),
            schedule_at=target_schedule_at,
        )
        if not sched_pub:
            _record_intent_blocker(conn, intent_id, f"schedule_failed:{sched_err}")
            return {
                "attempted": True,
                "mode": mode,
                "intent_id": intent_id,
                "handoff_id": norm_handoff_id,
                "draft_id": draft.draft_id,
                "publication_id": appr_pub.get("publication_id"),
                "state": appr_pub.get("state"),
                "blocker": f"schedule_failed:{sched_err}",
            }, f"schedule_failed:{sched_err}"

        try:
            conn.execute(
                """UPDATE autopost_product_video_intents
                   SET status='SCHEDULED', last_blocker_code=NULL, updated_at=?
                   WHERE intent_id=?""",
                (aps.canonical_utc_now(), intent_id),
            )
            conn.commit()
        except Exception:
            pass

        return {
            "attempted": True,
            "mode": mode,
            "intent_id": intent_id,
            "handoff_id": norm_handoff_id,
            "draft_id": draft.draft_id,
            "publication_id": sched_pub["publication_id"],
            "state": "SCHEDULED",
            "blocker": None,
        }, "scheduled"

    return {
        "attempted": False,
        "mode": mode,
        "intent_id": intent_id,
        "handoff_id": norm_handoff_id,
        "draft_id": None,
        "publication_id": None,
        "state": None,
        "blocker": f"unhandled_mode:{mode}",
    }, f"unhandled_mode:{mode}"
