"""Durable AutoPost Adapter Integration for SubDub.

Manages explicit AutoPost intent registration, canonical handoff resolution,
and decoupled publication scheduling for completed SubDub jobs.

Invariants:
1. Re-resolves authoritative durable job truth from SQLite system_settings.
2. Enforces canonical delivery predicate via services.subdub_auto_settlement._durable_video_delivery.
3. Enforces terminal billing requirement before drafting/scheduling.
4. AutoPost errors never revert or mutate SubDub delivery, billing, or rendering truth.
5. Strictly zero social publishing calls, zero paid provider calls, zero wallet mutations.
"""

from __future__ import annotations

import datetime
from enum import Enum
import json
import re
import sqlite3
from typing import Any, Optional
import uuid

from services import autopost_asset_handoff as aah
from services.autopost_asset_handoff import SourceProduct
from services import autopost_scheduler as aps
from services.subdub_auto_settlement import _durable_video_delivery


# =========================================================================
# 1. CONSTANTS & ENUMS
# =========================================================================

class SubDubAutoPostMode(str, Enum):
    OFF = "OFF"
    DRAFT_ONLY = "DRAFT_ONLY"
    SCHEDULE_NOW = "SCHEDULE_NOW"
    SCHEDULE_AT = "SCHEDULE_AT"


ALLOWED_INTENT_MODES = {
    SubDubAutoPostMode.OFF.value,
    SubDubAutoPostMode.DRAFT_ONLY.value,
    SubDubAutoPostMode.SCHEDULE_NOW.value,
    SubDubAutoPostMode.SCHEDULE_AT.value,
}

ALLOWED_CHANNEL_METADATA = {"facebook", "instagram", "tiktok", "youtube"}
MAX_CAPTION_LENGTH = 5000


# =========================================================================
# 2. SCHEMA MANAGEMENT
# =========================================================================

def ensure_autopost_subdub_adapter_schema(conn: sqlite3.Connection) -> None:
    """Ensure system_settings, autopost_subdub_intents, and dependencies exist."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT,
            updated_by TEXT,
            note TEXT
        )"""
    )
    aah.ensure_autopost_handoff_schema(conn)
    aps.ensure_autopost_scheduler_schema(conn)

    conn.execute(
        """CREATE TABLE IF NOT EXISTS autopost_subdub_intents (
            intent_id TEXT PRIMARY KEY,
            owner_id INTEGER NOT NULL,
            subdub_job_id TEXT NOT NULL,
            mode TEXT NOT NULL,
            schedule_at TEXT,
            selected_channels_json TEXT NOT NULL DEFAULT '[]',
            caption_override TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING',
            last_blocker_code TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(owner_id, subdub_job_id)
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_asdi_owner ON autopost_subdub_intents (owner_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_asdi_job ON autopost_subdub_intents (subdub_job_id)"
    )
    conn.commit()


# =========================================================================
# 3. JOB RESOLVER & INTENT MANAGEMENT
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


def _get_durable_subdub_job(conn: sqlite3.Connection, subdub_job_id: str) -> tuple[Optional[dict[str, Any]], str]:
    safe_id = str(subdub_job_id or "").strip()
    if not safe_id:
        return None, "subdub_job_id_missing"

    try:
        row = conn.execute(
            "SELECT value FROM system_settings WHERE key=? LIMIT 1",
            (f"engine_async_job:{safe_id}",),
        ).fetchone()
    except Exception:
        return None, "subdub_query_failed"

    if not row:
        return None, "subdub_job_not_found"

    try:
        job = json.loads(str(row[0] or ""))
    except Exception:
        return None, "subdub_durable_job_invalid"

    if not isinstance(job, dict):
        return None, "subdub_durable_job_invalid"

    feature = str(job.get("feature") or "").strip().lower()
    if feature not in {"subtitle_dub", "video_dub"}:
        return None, "subdub_feature_mismatch"

    canon_id = str(job.get("internal_job_id") or job.get("job_id") or "").strip()
    if canon_id != safe_id:
        return None, "subdub_job_id_mismatch"

    return job, ""


def register_subdub_autopost_intent(
    conn: sqlite3.Connection,
    owner_id: int,
    subdub_job_id: str,
    mode: str | SubDubAutoPostMode,
    schedule_at: Optional[str] = None,
    selected_channels: Optional[list[str]] = None,
    caption_override: Optional[str] = None,
    now: Optional[str] = None,
) -> tuple[Optional[dict[str, Any]], str]:
    """Register an explicit, durable AutoPost intent for a SubDub job."""
    ensure_autopost_subdub_adapter_schema(conn)

    try:
        safe_owner = int(owner_id)
        if safe_owner <= 0:
            return None, "invalid_owner_id"
    except (TypeError, ValueError):
        return None, "invalid_owner_id"

    safe_job_id = str(subdub_job_id or "").strip()
    if not safe_job_id:
        return None, "invalid_subdub_job_id"

    job, err = _get_durable_subdub_job(conn, safe_job_id)
    if not job:
        return None, err

    try:
        job_owner = int(job.get("user_id") or 0)
    except (TypeError, ValueError):
        job_owner = 0

    if job_owner <= 0 or job_owner != safe_owner:
        return None, "owner_mismatch"

    norm_mode = str(getattr(mode, "value", mode)).strip().upper()
    if norm_mode not in ALLOWED_INTENT_MODES:
        return None, f"invalid_mode:{norm_mode}"

    norm_now = str(now or aps.canonical_utc_now()).strip()

    norm_schedule_at: Optional[str] = None
    if norm_mode == SubDubAutoPostMode.SCHEDULE_NOW.value:
        if schedule_at is not None:
            return None, "schedule_at_not_allowed_for_schedule_now"
        norm_schedule_at = norm_now
    elif norm_mode == SubDubAutoPostMode.SCHEDULE_AT.value:
        if not schedule_at:
            return None, "schedule_at_required_for_schedule_at"
        norm_schedule_at, time_err = aps.parse_and_validate_utc(schedule_at)
        if not norm_schedule_at:
            return None, f"invalid_utc_schedule_at:{time_err}"

    clean_channels: list[str] = []
    if selected_channels:
        for ch in selected_channels:
            ch_str = str(ch).strip().lower()
            if ch_str not in ALLOWED_CHANNEL_METADATA:
                return None, f"unsupported_channel:{ch_str}"
            if ch_str not in clean_channels:
                clean_channels.append(ch_str)
    channels_json = json.dumps(sorted(clean_channels), separators=(",", ":"))

    caption_clean = str(caption_override).strip() if caption_override else None

    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM autopost_subdub_intents WHERE owner_id=? AND subdub_job_id=?",
        (safe_owner, safe_job_id),
    )
    existing = cur.fetchone()
    if existing:
        ex_dict = _row_to_dict(existing)
        if (
            ex_dict.get("mode") == norm_mode
            and ex_dict.get("schedule_at") == norm_schedule_at
            and ex_dict.get("selected_channels_json") == channels_json
            and ex_dict.get("caption_override") == caption_clean
        ):
            return ex_dict, "idempotent_existing"
        return None, "intent_conflict_already_registered"

    intent_id = f"subdub_intent_{uuid.uuid4().hex[:16]}"
    cur.execute(
        """INSERT INTO autopost_subdub_intents (
            intent_id, owner_id, subdub_job_id, mode, schedule_at,
            selected_channels_json, caption_override, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)""",
        (
            intent_id,
            safe_owner,
            safe_job_id,
            norm_mode,
            norm_schedule_at,
            channels_json,
            caption_clean,
            norm_now,
            norm_now,
        ),
    )
    conn.commit()

    cur.execute(
        "SELECT * FROM autopost_subdub_intents WHERE intent_id=?",
        (intent_id,),
    )
    row = cur.fetchone()
    return _row_to_dict(row), "registered"


def get_subdub_autopost_intent(
    conn: sqlite3.Connection,
    owner_id: int,
    subdub_job_id: str,
) -> Optional[dict[str, Any]]:
    """Retrieve explicit registered intent for a SubDub job."""
    ensure_autopost_subdub_adapter_schema(conn)
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM autopost_subdub_intents WHERE owner_id=? AND subdub_job_id=?",
        (int(owner_id), str(subdub_job_id).strip()),
    )
    row = cur.fetchone()
    return _row_to_dict(row) if row else None


def _record_intent_blocker(
    conn: sqlite3.Connection,
    intent_id: str,
    blocker_code: str,
) -> None:
    """Safely record adapter blocker code on intent for observability."""
    try:
        conn.execute(
            """UPDATE autopost_subdub_intents
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


# =========================================================================
# 4. HANDOFF & SCHEDULING PIPELINE
# =========================================================================

def process_subdub_autopost_handoff(
    conn: sqlite3.Connection,
    subdub_job_id: str,
    requesting_user_id: int,
    handoff_receipt: Optional[dict[str, Any] | aah.HandoffReceipt] = None,
    now: Optional[str] = None,
) -> tuple[dict[str, Any], str]:
    """Execute the SubDub -> AutoPost adapter seam post-producer commit.

    Enforces:
    - Post-commit only: rejects execution if conn.in_transaction is True
    - Rereads canonical SubDub truth via canonical resolver
    - Explicit opt-in only: if no intent registered or mode=OFF, does not create drafts or queue rows
    - Mode DRAFT_ONLY: creates/reuses PLANNED publication draft
    - Mode SCHEDULE_NOW / SCHEDULE_AT: creates/reuses draft, approves, and schedules
    - Schedule conflicts with differing timestamps fail closed
    - Any adapter failure leaves SubDub terminal truth, delivery, and billing intact
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

    ensure_autopost_subdub_adapter_schema(conn)

    safe_job_id = str(subdub_job_id or "").strip()
    safe_user_id = int(requesting_user_id)

    # 1. Reread canonical SubDub truth using canonical resolver
    asset, err = aah.adapt_subdub_output(
        conn,
        job_id=safe_job_id,
        requesting_user_id=safe_user_id,
    )
    if not asset:
        intent = get_subdub_autopost_intent(conn, safe_user_id, safe_job_id)
        if intent:
            _record_intent_blocker(conn, intent["intent_id"], f"canonical_resolver_failed:{err}")
        return {
            "attempted": True,
            "created_or_reused": False,
            "mode": intent.get("mode") if intent else None,
            "intent_id": intent.get("intent_id") if intent else None,
            "handoff_id": None,
            "draft_id": None,
            "publication_id": None,
            "state": None,
            "blocker": f"canonical_resolver_failed:{err}",
        }, f"canonical_resolver_failed:{err}"

    canonical_job_id = str(asset.source_job_id)

    # 2. Check for explicit intent
    intent = get_subdub_autopost_intent(
        conn,
        owner_id=safe_user_id,
        subdub_job_id=canonical_job_id,
    )

    candidate_handoff_id: Optional[str] = None
    if handoff_receipt:
        if isinstance(handoff_receipt, dict):
            candidate_handoff_id = handoff_receipt.get("handoff_id")
        else:
            candidate_handoff_id = getattr(handoff_receipt, "handoff_id", None)

    if not intent:
        return {
            "attempted": False,
            "created_or_reused": False,
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
    if mode == SubDubAutoPostMode.OFF.value:
        try:
            conn.execute(
                """UPDATE autopost_subdub_intents
                   SET status='CANCELLED', last_blocker_code=NULL, updated_at=?
                   WHERE intent_id=?""",
                (aps.canonical_utc_now(), intent_id),
            )
            conn.commit()
        except Exception:
            pass

        return {
            "attempted": True,
            "created_or_reused": False,
            "mode": SubDubAutoPostMode.OFF.value,
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
                "created_or_reused": False,
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
            int(rec.get("owner_id") or 0) != safe_user_id
            or str(rec.get("source_product") or "") != SourceProduct.SUBDUB.value
            or str(rec.get("source_job_id") or "") != canonical_job_id
            or str(rec.get("asset_id") or "") != str(asset.asset_id)
            or str(rec.get("artifact_sha256") or "").lower() != str(asset.artifact_sha256).lower()
            or str(rec.get("purpose") or "") != "autopost"
            or str(rec.get("status") or "") != "created"
        ):
            _record_intent_blocker(conn, intent_id, "handoff_product_binding_mismatch")
            return {
                "attempted": True,
                "created_or_reused": False,
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
               WHERE source_product='subdub'
                 AND source_job_id=?
                 AND owner_id=?
                 AND asset_id=?
                 AND artifact_sha256=?
                 AND purpose='autopost'
                 AND status='created'
               ORDER BY created_at DESC LIMIT 1""",
            (canonical_job_id, safe_user_id, str(asset.asset_id), str(asset.artifact_sha256)),
        )
        h_row = cur.fetchone()
        if h_row:
            norm_handoff_id = _row_to_dict(h_row)["handoff_id"]
        else:
            h_rec, h_err = aah.create_autopost_handoff_from_source(
                conn,
                source_product=SourceProduct.SUBDUB.value,
                source_ref=canonical_job_id,
                requesting_user_id=safe_user_id,
            )
            if not h_rec:
                _record_intent_blocker(conn, intent_id, f"handoff_failed:{h_err}")
                return {
                    "attempted": True,
                    "created_or_reused": False,
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
    if mode == SubDubAutoPostMode.DRAFT_ONLY.value:
        draft, d_err = aah.receive_autopost_handoff_to_draft(
            conn,
            handoff_id=norm_handoff_id,
            requesting_user_id=safe_user_id,
        )
        if not draft:
            _record_intent_blocker(conn, intent_id, f"draft_failed:{d_err}")
            return {
                "attempted": True,
                "created_or_reused": False,
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
                """UPDATE autopost_subdub_intents
                   SET status='DRAFT_READY', last_blocker_code=NULL, updated_at=?
                   WHERE intent_id=?""",
                (aps.canonical_utc_now(), intent_id),
            )
            conn.commit()
        except Exception:
            pass

        return {
            "attempted": True,
            "created_or_reused": True,
            "mode": SubDubAutoPostMode.DRAFT_ONLY.value,
            "intent_id": intent_id,
            "handoff_id": norm_handoff_id,
            "draft_id": draft.draft_id,
            "publication_id": None,
            "state": "PLANNED",
            "blocker": None,
        }, "draft_ready"

    # 6. MODE: SCHEDULE_NOW / SCHEDULE_AT
    if mode in (SubDubAutoPostMode.SCHEDULE_NOW.value, SubDubAutoPostMode.SCHEDULE_AT.value):
        draft, d_err = aah.receive_autopost_handoff_to_draft(
            conn,
            handoff_id=norm_handoff_id,
            requesting_user_id=safe_user_id,
        )
        if not draft:
            _record_intent_blocker(conn, intent_id, f"draft_failed:{d_err}")
            return {
                "attempted": True,
                "created_or_reused": False,
                "mode": mode,
                "intent_id": intent_id,
                "handoff_id": norm_handoff_id,
                "draft_id": None,
                "publication_id": None,
                "state": None,
                "blocker": f"draft_failed:{d_err}",
            }, f"draft_failed:{d_err}"

        _apply_draft_customizations(conn, draft.draft_id, intent)

        if mode == SubDubAutoPostMode.SCHEDULE_NOW.value:
            intent_sched = intent.get("schedule_at")
            if intent_sched:
                target_schedule_at = intent_sched
            elif now is not None:
                norm_now, time_err = aps.parse_and_validate_utc(now)
                if not norm_now:
                    _record_intent_blocker(conn, intent_id, f"schedule_time_invalid:{time_err}")
                    return {
                        "attempted": True,
                        "created_or_reused": False,
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

            if not intent_sched:
                try:
                    conn.execute(
                        "UPDATE autopost_subdub_intents SET schedule_at=? WHERE intent_id=?",
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
                    "created_or_reused": False,
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

            q_owner = int(q_dict.get("owner_id") or 0)
            q_handoff = q_dict.get("handoff_id")
            q_asset = q_dict.get("asset_id")
            q_sha = q_dict.get("artifact_sha256")
            if (
                q_owner != safe_user_id
                or q_handoff != norm_handoff_id
                or q_asset != asset.asset_id
                or q_sha != asset.artifact_sha256
            ):
                _record_intent_blocker(conn, intent_id, "handoff_product_binding_mismatch")
                return {
                    "attempted": True,
                    "created_or_reused": False,
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
                        "created_or_reused": False,
                        "mode": mode,
                        "intent_id": intent_id,
                        "handoff_id": norm_handoff_id,
                        "draft_id": draft.draft_id,
                        "publication_id": pub_id,
                        "state": "SCHEDULED",
                        "blocker": "schedule_conflict_different_timestamp",
                    }, "schedule_conflict_different_timestamp"
                return {
                    "attempted": True,
                    "created_or_reused": True,
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
                        "created_or_reused": False,
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
                    "created_or_reused": True,
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
            requesting_user_id=safe_user_id,
        )
        if not appr_pub:
            _record_intent_blocker(conn, intent_id, f"approval_failed:{appr_err}")
            return {
                "attempted": True,
                "created_or_reused": False,
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
            requesting_user_id=safe_user_id,
            schedule_at=target_schedule_at,
        )
        if not sched_pub:
            _record_intent_blocker(conn, intent_id, f"schedule_failed:{sched_err}")
            return {
                "attempted": True,
                "created_or_reused": False,
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
                """UPDATE autopost_subdub_intents
                   SET status='SCHEDULED', last_blocker_code=NULL, updated_at=?
                   WHERE intent_id=?""",
                (aps.canonical_utc_now(), intent_id),
            )
            conn.commit()
        except Exception:
            pass

        return {
            "attempted": True,
            "created_or_reused": True,
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
        "created_or_reused": False,
        "mode": mode,
        "intent_id": intent_id,
        "handoff_id": norm_handoff_id,
        "draft_id": None,
        "publication_id": None,
        "state": None,
        "blocker": f"unhandled_mode:{mode}",
    }, f"unhandled_mode:{mode}"
