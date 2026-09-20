"""services/autopost_video_edit_adapter.py

Canonical Video Edit -> AutoPost Adapter Authority.
Governed under TOAN AAS Owner-Governed Codex (P0.AUTOPOST.S4).

Core Invariants:
1. Canonical Video Edit Authority:
   Rereads canonical Video Edit truth through existing resolvers only.
   Never trusts caller-supplied artifact paths or hashes.
2. Decoupled Producer Safety:
   Any AutoPost adapter failure or rejection never reverts, fails, or requeues Video Edit.
3. Explicit User-Intent Opt-In:
   AutoPost only processes when an explicit durable intent is registered.
   Modes: OFF, DRAFT_ONLY, SCHEDULE_NOW, SCHEDULE_AT.
4. Post-Commit Execution Only:
   Runs only after Video Edit durable state is committed.
5. Publish-Only Isolation:
   No producer rerender, no social provider calls, no wallet mutations.
6. Delivery & Charge Isolation:
   AutoPost adapter never controls delivery or billing of Video Edit.
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
from services import video_editengine1


# =========================================================================
# 1. ENUMS & CONSTANTS
# =========================================================================

class VideoEditAutoPostMode(str, Enum):
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
    VideoEditAutoPostMode.OFF.value,
    VideoEditAutoPostMode.DRAFT_ONLY.value,
    VideoEditAutoPostMode.SCHEDULE_NOW.value,
    VideoEditAutoPostMode.SCHEDULE_AT.value,
}

ALLOWED_CHANNELS = {"tiktok", "youtube", "facebook", "instagram", "telegram"}
MAX_CAPTION_LENGTH = 2000


# =========================================================================
# 2. SCHEMA MANAGEMENT
# =========================================================================

def ensure_autopost_video_edit_adapter_schema(conn: sqlite3.Connection) -> None:
    """Ensure the durable autopost_video_edit_intents table and indexes exist."""
    video_editengine1.ensure_schema(conn)
    aah.ensure_autopost_handoff_schema(conn)
    aps.ensure_autopost_scheduler_schema(conn)

    conn.execute(
        """CREATE TABLE IF NOT EXISTS autopost_video_edit_intents (
            intent_id TEXT PRIMARY KEY,
            owner_id INTEGER NOT NULL,
            video_edit_job_id INTEGER NOT NULL,
            mode TEXT NOT NULL,
            schedule_at TEXT,
            selected_channels_json TEXT NOT NULL DEFAULT '[]',
            caption_override TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING',
            last_blocker_code TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(owner_id, video_edit_job_id)
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_avei_owner ON autopost_video_edit_intents (owner_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_avei_job ON autopost_video_edit_intents (video_edit_job_id)"
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


def register_video_edit_autopost_intent(
    conn: sqlite3.Connection,
    owner_id: int,
    video_edit_job_id: int,
    mode: str | VideoEditAutoPostMode,
    schedule_at: Optional[str] = None,
    selected_channels: Optional[list[str]] = None,
    caption_override: Optional[str] = None,
    now: Optional[str] = None,
) -> tuple[Optional[dict[str, Any]], str]:
    """Register an explicit, durable AutoPost intent for a Video Edit job.

    Enforces:
    - owner_id and video_edit_job_id must be valid positive integers
    - canonical Video Edit job exists in DB (checked by id or local_worker_job_id)
    - canonical owner matches requesting owner_id
    - mode must be in ALLOWED_INTENT_MODES
    - for SCHEDULE_NOW: caller-supplied schedule_at is forbidden; durable effective
      schedule_at is locked to canonical registration time
    - for SCHEDULE_AT: schedule_at validated strictly (strict canonical UTC)
    - selected_channels bounded to metadata allowlist
    - caption_override bounded length
    - Idempotent: re-registration with identical parameters returns existing record.
    - Conflicting update on existing intent fails closed.
    """
    ensure_autopost_video_edit_adapter_schema(conn)

    try:
        norm_owner_id = int(owner_id)
        raw_job_id = int(video_edit_job_id)
        if norm_owner_id <= 0 or raw_job_id <= 0:
            return None, "invalid_ids"
    except (ValueError, TypeError):
        return None, "invalid_ids"

    clean_mode = str(getattr(mode, "value", mode) or "").strip().upper()
    if clean_mode not in ALLOWED_INTENT_MODES:
        return None, f"unsupported_mode:{clean_mode}"

    if now is not None:
        norm_now, time_err = aps.parse_and_validate_utc(now)
        if not norm_now:
            return None, time_err
    else:
        norm_now = aps.canonical_utc_now()

    norm_schedule_at: Optional[str] = None
    if clean_mode == VideoEditAutoPostMode.SCHEDULE_AT.value:
        if not schedule_at:
            return None, "schedule_at_required_for_schedule_at_mode"
        validated_sched, sched_err = aps.parse_and_validate_utc(schedule_at)
        if not validated_sched:
            return None, f"invalid_schedule_at:{sched_err}"
        norm_schedule_at = validated_sched
    elif clean_mode == VideoEditAutoPostMode.SCHEDULE_NOW.value:
        if schedule_at is not None:
            return None, "schedule_at_not_allowed_for_schedule_now"
        norm_schedule_at = norm_now

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

    # Canonical Video Edit job ownership verification BEFORE INSERT
    cur = conn.cursor()
    cur.execute(
        "SELECT id, user_id FROM video_edit_jobs WHERE id=? OR local_worker_job_id=?",
        (raw_job_id, raw_job_id),
    )
    job_row = cur.fetchone()
    if not job_row:
        return None, "video_edit_job_not_found"

    canonical_job_id = int(job_row["id"] if hasattr(job_row, "keys") else job_row[0])
    job_user_id = int(job_row["user_id"] if hasattr(job_row, "keys") else job_row[1])

    if job_user_id != norm_owner_id:
        return None, "owner_mismatch"

    cur.execute(
        """SELECT * FROM autopost_video_edit_intents
           WHERE owner_id=? AND video_edit_job_id=? LIMIT 1""",
        (norm_owner_id, canonical_job_id),
    )
    existing_row = cur.fetchone()
    if existing_row:
        existing = _row_to_dict(existing_row)
        # Check identical parameters
        channels_match = json.loads(existing.get("selected_channels_json") or "[]") == norm_channels
        mode_match = existing.get("mode") == clean_mode
        if clean_mode == VideoEditAutoPostMode.SCHEDULE_NOW.value:
            if schedule_at is None:
                sched_match = True
            else:
                sched_match = (existing.get("schedule_at") or None) == norm_schedule_at
        else:
            sched_match = (existing.get("schedule_at") or None) == norm_schedule_at
        caption_match = (existing.get("caption_override") or None) == clean_caption

        if channels_match and mode_match and sched_match and caption_match:
            return existing, "idempotent_existing"
        return None, "intent_conflict_already_registered"

    intent_hash = hashlib.sha256(f"{norm_owner_id}:{canonical_job_id}".encode("utf-8")).hexdigest()[:20]
    intent_id = f"intent_ve_{intent_hash}"

    try:
        conn.execute(
            """INSERT INTO autopost_video_edit_intents (
                intent_id, owner_id, video_edit_job_id, mode, schedule_at,
                selected_channels_json, caption_override, status, last_blocker_code,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', NULL, ?, ?)""",
            (
                intent_id,
                norm_owner_id,
                canonical_job_id,
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
            """SELECT * FROM autopost_video_edit_intents
               WHERE owner_id=? AND video_edit_job_id=? LIMIT 1""",
            (norm_owner_id, canonical_job_id),
        )
        row = cur.fetchone()
        if row:
            return _row_to_dict(row), "idempotent_existing"
        raise

    cur.execute(
        "SELECT * FROM autopost_video_edit_intents WHERE intent_id=? LIMIT 1",
        (intent_id,),
    )
    return _row_to_dict(cur.fetchone()), "registered"


def get_video_edit_autopost_intent(
    conn: sqlite3.Connection,
    owner_id: int,
    video_edit_job_id: int,
) -> Optional[dict[str, Any]]:
    """Retrieve canonical registered intent for (owner_id, video_edit_job_id) if any."""
    ensure_autopost_video_edit_adapter_schema(conn)
    cur = conn.cursor()

    # Resolve canonical internal id if raw video_edit_job_id is an alias
    norm_job_id = int(video_edit_job_id)
    cur.execute(
        "SELECT id FROM video_edit_jobs WHERE id=? OR local_worker_job_id=? LIMIT 1",
        (norm_job_id, norm_job_id),
    )
    j_row = cur.fetchone()
    if j_row:
        canonical_id = int(j_row["id"] if hasattr(j_row, "keys") else j_row[0])
    else:
        canonical_id = norm_job_id

    cur.execute(
        """SELECT * FROM autopost_video_edit_intents
           WHERE owner_id=? AND video_edit_job_id=? LIMIT 1""",
        (int(owner_id), canonical_id),
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
            """UPDATE autopost_video_edit_intents
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


def process_video_edit_autopost_handoff(
    conn: sqlite3.Connection,
    video_edit_job_id: int,
    owner_id: int,
    handoff_receipt: Optional[dict[str, Any] | aah.HandoffReceipt] = None,
    now: Optional[str] = None,
) -> tuple[dict[str, Any], str]:
    """Execute the Video Edit -> AutoPost adapter seam post-producer commit.

    Enforces:
    - Post-commit only: rejects execution if conn.in_transaction is True
    - Rereads canonical Video Edit truth via canonical resolver
    - Explicit opt-in only: if no intent registered or mode=OFF, does not create drafts or queue rows
    - Mode DRAFT_ONLY: creates/reuses PLANNED publication draft
    - Mode SCHEDULE_NOW / SCHEDULE_AT: creates/reuses draft, approves, and schedules
    - Schedule conflicts with differing timestamps fail closed
    - Any adapter failure leaves Video Edit terminal truth and billing intact
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

    ensure_autopost_video_edit_adapter_schema(conn)

    # 1. Reread canonical Video Edit truth using canonical resolver
    asset, err = aah.adapt_video_edit_output(
        conn,
        job_id=int(video_edit_job_id),
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

    canonical_job_id = int(asset.source_job_id)

    # 2. Check for explicit intent
    intent = get_video_edit_autopost_intent(
        conn,
        owner_id=int(owner_id),
        video_edit_job_id=canonical_job_id,
    )

    norm_handoff_id: Optional[str] = None
    candidate_handoff_id: Optional[str] = None
    if handoff_receipt:
        if isinstance(handoff_receipt, dict):
            candidate_handoff_id = handoff_receipt.get("handoff_id")
        else:
            candidate_handoff_id = getattr(handoff_receipt, "handoff_id", None)

    if not intent:
        return {
            "attempted": False,
            "mode": "NONE",
            "intent_id": None,
            "handoff_id": candidate_handoff_id,
            "draft_id": None,
            "publication_id": None,
            "state": None,
            "blocker": "no_intent_registered",
        }, "no_intent_registered"

    mode = str(intent.get("mode") or "").strip().upper()
    intent_id = str(intent.get("intent_id") or "")

    # 3. MODE: OFF
    if mode == VideoEditAutoPostMode.OFF.value:
        try:
            conn.execute(
                """UPDATE autopost_video_edit_intents
                   SET status='CANCELLED', last_blocker_code=NULL, updated_at=?
                   WHERE intent_id=?""",
                (aps.canonical_utc_now(), intent_id),
            )
            conn.commit()
        except Exception:
            pass

        return {
            "attempted": True,
            "mode": VideoEditAutoPostMode.OFF.value,
            "intent_id": intent_id,
            "handoff_id": candidate_handoff_id,
            "draft_id": None,
            "publication_id": None,
            "state": None,
            "blocker": None,
        }, "off"

    # 4. Strict handoff verification and binding
    cur = conn.cursor()
    if candidate_handoff_id:
        cur.execute(
            "SELECT * FROM autopost_handoff_receipts WHERE handoff_id=? LIMIT 1",
            (str(candidate_handoff_id).strip(),),
        )
        rec_row = cur.fetchone()
        if not rec_row:
            _record_intent_blocker(conn, intent_id, "handoff_product_binding_mismatch")
            return {
                "attempted": True,
                "mode": mode,
                "intent_id": intent_id,
                "handoff_id": candidate_handoff_id,
                "draft_id": None,
                "publication_id": None,
                "state": None,
                "blocker": "handoff_product_binding_mismatch",
            }, "handoff_product_binding_mismatch"

        rec = _row_to_dict(rec_row)
        if (
            int(rec.get("owner_id") or 0) != int(owner_id)
            or str(rec.get("source_product") or "") != "video_edit"
            or str(rec.get("source_job_id") or "") != str(canonical_job_id)
            or str(rec.get("asset_id") or "") != str(asset.asset_id)
            or str(rec.get("artifact_sha256") or "").lower() != str(asset.artifact_sha256).lower()
            or str(rec.get("purpose") or "") != "autopost"
            or str(rec.get("status") or "") != "created"
        ):
            _record_intent_blocker(conn, intent_id, "handoff_product_binding_mismatch")
            return {
                "attempted": True,
                "mode": mode,
                "intent_id": intent_id,
                "handoff_id": candidate_handoff_id,
                "draft_id": None,
                "publication_id": None,
                "state": None,
                "blocker": "handoff_product_binding_mismatch",
            }, "handoff_product_binding_mismatch"

        norm_handoff_id = str(candidate_handoff_id).strip()
    else:
        cur.execute(
            """SELECT * FROM autopost_handoff_receipts
               WHERE source_product='video_edit'
                 AND source_job_id=?
                 AND owner_id=?
                 AND asset_id=?
                 AND artifact_sha256=?
                 AND purpose='autopost'
                 AND status='created'
               ORDER BY created_at DESC LIMIT 1""",
            (str(canonical_job_id), int(owner_id), str(asset.asset_id), str(asset.artifact_sha256)),
        )
        h_row = cur.fetchone()
        if h_row:
            norm_handoff_id = _row_to_dict(h_row)["handoff_id"]
        else:
            h_rec, h_err = aah.create_autopost_handoff_from_source(
                conn,
                source_product="video_edit",
                source_ref=canonical_job_id,
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
    if mode == VideoEditAutoPostMode.DRAFT_ONLY.value:
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
                """UPDATE autopost_video_edit_intents
                   SET status='DRAFT_READY', last_blocker_code=NULL, updated_at=?
                   WHERE intent_id=?""",
                (aps.canonical_utc_now(), intent_id),
            )
            conn.commit()
        except Exception:
            pass

        return {
            "attempted": True,
            "mode": VideoEditAutoPostMode.DRAFT_ONLY.value,
            "intent_id": intent_id,
            "handoff_id": norm_handoff_id,
            "draft_id": draft.draft_id,
            "publication_id": None,
            "state": "PLANNED",
            "blocker": None,
        }, "draft_ready"

    # 6. MODE: SCHEDULE_NOW / SCHEDULE_AT
    if mode in (VideoEditAutoPostMode.SCHEDULE_NOW.value, VideoEditAutoPostMode.SCHEDULE_AT.value):
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
        if mode == VideoEditAutoPostMode.SCHEDULE_NOW.value:
            intent_sched = intent.get("schedule_at")
            if intent_sched:
                target_schedule_at = intent_sched
            elif now is not None:
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

            # Ensure schedule_at is locked into intent for subsequent replays
            if not intent_sched:
                try:
                    conn.execute(
                        "UPDATE autopost_video_edit_intents SET schedule_at=? WHERE intent_id=?",
                        (target_schedule_at, intent_id),
                    )
                    conn.commit()
                except Exception:
                    pass
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
            existing_state = str(q_dict.get("state") or "").upper()
            existing_sched = q_dict.get("schedule_at")
            pub_id = q_dict.get("publication_id")

            # Check owner and artifact binding
            q_owner = int(q_dict.get("owner_id") or 0)
            q_handoff = q_dict.get("handoff_id")
            q_asset = q_dict.get("asset_id")
            q_sha = q_dict.get("artifact_sha256")
            if (
                q_owner != int(owner_id)
                or q_handoff != norm_handoff_id
                or q_asset != asset.asset_id
                or q_sha != asset.artifact_sha256
            ):
                _record_intent_blocker(conn, intent_id, "handoff_product_binding_mismatch")
                return {
                    "attempted": True,
                    "mode": mode,
                    "intent_id": intent_id,
                    "handoff_id": norm_handoff_id,
                    "draft_id": draft.draft_id,
                    "publication_id": pub_id,
                    "state": existing_state,
                    "blocker": "handoff_product_binding_mismatch",
                }, "handoff_product_binding_mismatch"

            if existing_state == "SCHEDULED":
                if existing_sched and existing_sched != target_schedule_at:
                    _record_intent_blocker(conn, intent_id, "schedule_conflict_different_timestamp")
                    return {
                        "attempted": True,
                        "mode": mode,
                        "intent_id": intent_id,
                        "handoff_id": norm_handoff_id,
                        "draft_id": draft.draft_id,
                        "publication_id": pub_id,
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
                    "publication_id": pub_id,
                    "state": "SCHEDULED",
                    "blocker": None,
                }, "scheduled"

            if existing_state in (
                "CLAIMED",
                "PUBLISHING",
                "PUBLISHED",
                "FAILED_RETRYABLE",
                "FAILED_FINAL",
                "CANCELLED",
            ):
                if existing_sched and existing_sched != target_schedule_at:
                    _record_intent_blocker(conn, intent_id, "schedule_conflict_different_timestamp")
                    return {
                        "attempted": True,
                        "mode": mode,
                        "intent_id": intent_id,
                        "handoff_id": norm_handoff_id,
                        "draft_id": draft.draft_id,
                        "publication_id": pub_id,
                        "state": existing_state,
                        "blocker": "schedule_conflict_different_timestamp",
                    }, "schedule_conflict_different_timestamp"

                return {
                    "attempted": True,
                    "mode": mode,
                    "intent_id": intent_id,
                    "handoff_id": norm_handoff_id,
                    "draft_id": draft.draft_id,
                    "publication_id": pub_id,
                    "state": existing_state,
                    "blocker": None,
                }, existing_state.lower()

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
                """UPDATE autopost_video_edit_intents
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
