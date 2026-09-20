"""services/autopost_scheduler.py

Durable AutoPost Scheduler, Lease Management, Retry, and Recovery Layer.
Governed under TOAN AAS Owner-Governed Codex (P0.AUTOPOST.S2).

Core Invariants:
1. Strict Canonical State Machine:
   PLANNED -> APPROVED -> SCHEDULED -> CLAIMED -> PUBLISHING -> PUBLISHED
   or FAILED_RETRYABLE -> CLAIMED
   or FAILED_FINAL / CANCELLED.
   Terminal states are strictly immutable.
2. Publish-Only Retry:
   AutoPost scheduler retries only the publication unit.
   NEVER re-renders, re-generates, or re-queues producer pipelines (Product Video, Video Edit, SubDub).
3. Ambiguous External Effect Fail-Closed:
   If a worker crashes while PUBLISHING, never blindly re-schedule.
   Requires external reconciliation before any further action.
4. Zero External Social Provider API Calls:
   S2 establishes the durable scheduler boundary without implementing live social publishing adapters.
5. Canonical UTC Clock & Timezone Invariant:
   All scheduler timestamps are normalized canonical UTC ISO-8601 strings.
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
from services import video_local_validation


# =========================================================================
# 1. STATE MACHINE CONTRACT
# =========================================================================

class PublicationState(str, Enum):
    PLANNED = "PLANNED"
    APPROVED = "APPROVED"
    SCHEDULED = "SCHEDULED"
    CLAIMED = "CLAIMED"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"
    CANCELLED = "CANCELLED"


TERMINAL_STATES = {
    PublicationState.PUBLISHED,
    PublicationState.FAILED_FINAL,
    PublicationState.CANCELLED,
}

VALID_TRANSITIONS: dict[PublicationState, set[PublicationState]] = {
    PublicationState.PLANNED: {PublicationState.APPROVED, PublicationState.CANCELLED},
    PublicationState.APPROVED: {PublicationState.SCHEDULED, PublicationState.CANCELLED},
    PublicationState.SCHEDULED: {PublicationState.CLAIMED, PublicationState.CANCELLED},
    PublicationState.CLAIMED: {
        PublicationState.PUBLISHING,
        PublicationState.FAILED_RETRYABLE,
        PublicationState.CANCELLED,
    },
    PublicationState.PUBLISHING: {
        PublicationState.PUBLISHED,
        PublicationState.FAILED_RETRYABLE,
        PublicationState.FAILED_FINAL,
    },
    PublicationState.FAILED_RETRYABLE: {
        PublicationState.CLAIMED,
        PublicationState.CANCELLED,
    },
    PublicationState.PUBLISHED: set(),
    PublicationState.FAILED_FINAL: set(),
    PublicationState.CANCELLED: set(),
}


def validate_transition(
    current: str | PublicationState,
    target: str | PublicationState,
) -> tuple[bool, str]:
    """Validate whether current -> target state transition is allowed."""
    try:
        curr_enum = PublicationState(str(getattr(current, "value", current)).strip().upper())
        tgt_enum = PublicationState(str(getattr(target, "value", target)).strip().upper())
    except ValueError:
        return False, f"invalid_state:{current}->{target}"

    if curr_enum in TERMINAL_STATES:
        return False, f"terminal_state_immutable:{curr_enum.value}"

    if tgt_enum not in VALID_TRANSITIONS.get(curr_enum, set()):
        return False, f"illegal_transition:{curr_enum.value}->{tgt_enum.value}"

    return True, ""


# =========================================================================
# 2. CANONICAL UTC TIME UTILITIES
# =========================================================================

def canonical_utc_now() -> str:
    """Return current timestamp in canonical UTC ISO-8601 string (%Y-%m-%dT%H:%M:%SZ)."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_and_validate_utc(ts: str) -> tuple[Optional[str], str]:
    """Parse and strictly validate an ISO-8601 UTC timestamp.

    Rejects naive timestamps, missing timestamps, and non-UTC offsets.
    Returns normalized '%Y-%m-%dT%H:%M:%SZ'.
    """
    if not ts or not isinstance(ts, str):
        return None, "missing_timestamp"
    raw = ts.strip()
    if not raw:
        return None, "empty_timestamp"

    # Strict UTC indicator check
    if not (raw.endswith("Z") or raw.endswith("+00:00") or raw.endswith("-00:00")):
        return None, "non_utc_or_naive_timestamp"

    clean_str = raw
    if clean_str.endswith("Z"):
        clean_str = clean_str[:-1] + "+00:00"

    try:
        dt = datetime.datetime.fromisoformat(clean_str)
    except (ValueError, TypeError):
        return None, "invalid_iso8601_format"

    if dt.tzinfo is None:
        return None, "naive_timestamp_rejected"

    # Convert to pure UTC and format canonical
    utc_dt = dt.astimezone(datetime.timezone.utc)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ"), ""


def add_seconds_to_utc(base_utc_ts: str, seconds: int) -> str:
    """Add integer seconds to canonical UTC timestamp."""
    norm_ts, _ = parse_and_validate_utc(base_utc_ts)
    if not norm_ts:
        norm_ts = canonical_utc_now()
    dt = datetime.datetime.strptime(norm_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    new_dt = dt + datetime.timedelta(seconds=max(0, int(seconds)))
    return new_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def calculate_backoff_seconds(
    attempt_count: int,
    base_seconds: int = 60,
    max_seconds: int = 3600,
) -> int:
    """Calculate deterministic bounded exponential backoff delay."""
    attempts = max(1, int(attempt_count))
    # 2^(attempts-1) * base, capped at max_seconds
    delay = int(base_seconds * (2 ** (attempts - 1)))
    return max(base_seconds, min(max_seconds, delay))


# =========================================================================
# 3. DURABLE SCHEDULER STORAGE SCHEMA
# =========================================================================

def ensure_autopost_scheduler_schema(conn: sqlite3.Connection) -> None:
    """Ensure the durable autopost_publication_queue table and indexes exist."""
    aah.ensure_autopost_handoff_schema(conn)

    conn.execute(
        """CREATE TABLE IF NOT EXISTS autopost_publication_queue (
            publication_id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL,
            handoff_id TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            owner_id INTEGER NOT NULL,
            artifact_sha256 TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'APPROVED',
            schedule_at TEXT,
            next_attempt_at TEXT,
            lease_owner TEXT,
            lease_expires_at TEXT,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            idempotency_key TEXT NOT NULL UNIQUE,
            revision INTEGER NOT NULL DEFAULT 1,
            last_error_code TEXT,
            last_error_at TEXT,
            publish_started_at TEXT,
            published_at TEXT,
            cancelled_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_apq_due ON autopost_publication_queue (state, schedule_at, next_attempt_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_apq_owner ON autopost_publication_queue (owner_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_apq_draft ON autopost_publication_queue (draft_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_apq_handoff ON autopost_publication_queue (handoff_id)")
    conn.commit()


def _row_to_dict(row: Any) -> Optional[dict[str, Any]]:
    if not row:
        return None
    if isinstance(row, dict):
        return dict(row)
    return {k: row[k] for k in row.keys()}


# =========================================================================
# 4. APPROVAL
# =========================================================================

def approve_publication_draft(
    conn: sqlite3.Connection,
    draft_id: str,
    requesting_user_id: int,
) -> tuple[Optional[dict[str, Any]], str]:
    """Approve a PLANNED publication draft into APPROVED state.

    Enforces:
    - Draft exists and belongs to requesting_user_id
    - Associated handoff exists and belongs to requesting_user_id
    - Asset ID and artifact SHA bindings match exactly
    - Draft is not terminal or cancelled
    - Idempotent: approving an already approved draft returns the existing record.
    """
    ensure_autopost_scheduler_schema(conn)

    cur = conn.cursor()
    cur.execute("SELECT * FROM autopost_publication_drafts WHERE draft_id=? LIMIT 1", (draft_id,))
    draft_row = cur.fetchone()
    if not draft_row:
        return None, "draft_not_found"
    draft = _row_to_dict(draft_row)

    # Owner binding check
    if int(draft["owner_id"]) != int(requesting_user_id):
        return None, "owner_mismatch"

    # Verify handoff authority
    cur.execute(
        "SELECT * FROM autopost_handoff_receipts WHERE handoff_id=? LIMIT 1",
        (draft["handoff_id"],),
    )
    handoff_row = cur.fetchone()
    if not handoff_row:
        return None, "handoff_not_found"
    handoff = _row_to_dict(handoff_row)

    if int(handoff["owner_id"]) != int(requesting_user_id):
        return None, "handoff_owner_mismatch"

    if handoff["asset_id"] != draft["asset_id"]:
        return None, "asset_id_mismatch"

    artifact_sha = str(handoff.get("artifact_sha256") or "").strip().lower()
    if len(artifact_sha) != 64:
        return None, "artifact_sha_invalid"

    # Draft terminal check
    draft_status = str(draft["status"] or "").strip().upper()
    if draft_status == PublicationState.APPROVED.value:
        # Check if queue entry exists
        cur.execute("SELECT * FROM autopost_publication_queue WHERE draft_id=? LIMIT 1", (draft_id,))
        existing_q = cur.fetchone()
        if existing_q:
            return _row_to_dict(existing_q), "idempotent_already_approved"
    elif draft_status in (PublicationState.PUBLISHED.value, PublicationState.FAILED_FINAL.value, PublicationState.CANCELLED.value):
        return None, f"draft_terminal_cannot_approve:{draft_status}"
    elif draft_status != PublicationState.PLANNED.value and draft_status != PublicationState.APPROVED.value:
        return None, f"draft_state_invalid_for_approval:{draft_status}"

    now_ts = canonical_utc_now()
    idempotency_key = f"sched_{draft_id}"
    pub_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:24]
    publication_id = f"pub_{pub_hash}"

    try:
        conn.execute(
            """INSERT INTO autopost_publication_queue (
                publication_id, draft_id, handoff_id, asset_id, owner_id,
                artifact_sha256, state, schedule_at, next_attempt_at,
                lease_owner, lease_expires_at, attempt_count, max_attempts,
                idempotency_key, revision, last_error_code, last_error_at,
                publish_started_at, published_at, cancelled_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                publication_id,
                draft_id,
                draft["handoff_id"],
                draft["asset_id"],
                int(requesting_user_id),
                artifact_sha,
                PublicationState.APPROVED.value,
                None,
                None,
                None,
                None,
                0,
                3,
                idempotency_key,
                1,
                None,
                None,
                None,
                None,
                None,
                now_ts,
                now_ts,
            ),
        )
        conn.execute(
            "UPDATE autopost_publication_drafts SET status='APPROVED' WHERE draft_id=?",
            (draft_id,),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        # Unique idempotency conflict: load and return canonical queue row
        cur.execute("SELECT * FROM autopost_publication_queue WHERE idempotency_key=? LIMIT 1", (idempotency_key,))
        q_row = cur.fetchone()
        if q_row:
            return _row_to_dict(q_row), "idempotent_approved"
        raise

    cur.execute("SELECT * FROM autopost_publication_queue WHERE publication_id=? LIMIT 1", (publication_id,))
    return _row_to_dict(cur.fetchone()), "approved"


# =========================================================================
# 5. SCHEDULING
# =========================================================================

def schedule_publication(
    conn: sqlite3.Connection,
    draft_id: str,
    requesting_user_id: int,
    schedule_at: str,
) -> tuple[Optional[dict[str, Any]], str]:
    """Schedule an APPROVED publication draft for canonical execution at schedule_at.

    Enforces:
    - schedule_at must be strict canonical UTC ISO-8601
    - Publication must be APPROVED before entering SCHEDULED
    - Owner must match
    - Idempotent: re-scheduling with identical parameters returns existing record.
    """
    ensure_autopost_scheduler_schema(conn)

    norm_schedule_at, err = parse_and_validate_utc(schedule_at)
    if not norm_schedule_at:
        return None, err

    cur = conn.cursor()
    cur.execute("SELECT * FROM autopost_publication_queue WHERE draft_id=? LIMIT 1", (draft_id,))
    q_row = cur.fetchone()
    if not q_row:
        return None, "publication_not_approved"
    item = _row_to_dict(q_row)

    if int(item["owner_id"]) != int(requesting_user_id):
        return None, "owner_mismatch"

    curr_state = item["state"]
    if curr_state == PublicationState.SCHEDULED.value:
        if item["schedule_at"] == norm_schedule_at:
            return item, "idempotent_already_scheduled"
    elif curr_state != PublicationState.APPROVED.value:
        return None, f"cannot_schedule_in_state:{curr_state}"

    ok, reason = validate_transition(curr_state, PublicationState.SCHEDULED)
    if not ok:
        return None, reason

    now_ts = canonical_utc_now()
    cur.execute(
        """UPDATE autopost_publication_queue SET
            state=?,
            schedule_at=?,
            revision=revision+1,
            updated_at=?
        WHERE publication_id=? AND revision=?""",
        (
            PublicationState.SCHEDULED.value,
            norm_schedule_at,
            now_ts,
            item["publication_id"],
            int(item["revision"]),
        ),
    )
    if cur.rowcount != 1:
        # Concurrent conflict: re-read
        cur.execute("SELECT * FROM autopost_publication_queue WHERE publication_id=? LIMIT 1", (item["publication_id"],))
        return _row_to_dict(cur.fetchone()), "concurrent_schedule_conflict"

    conn.execute(
        "UPDATE autopost_publication_drafts SET status='SCHEDULED', schedule_at=? WHERE draft_id=?",
        (norm_schedule_at, draft_id),
    )
    conn.commit()

    cur.execute("SELECT * FROM autopost_publication_queue WHERE publication_id=? LIMIT 1", (item["publication_id"],))
    return _row_to_dict(cur.fetchone()), "scheduled"


# =========================================================================
# 6. ATOMIC DUE CLAIM
# =========================================================================

def claim_due_publication(
    conn: sqlite3.Connection,
    worker_id: str,
    now: Optional[str] = None,
    lease_seconds: int = 600,
) -> tuple[Optional[dict[str, Any]], str]:
    """Atomically claim one due publication (SCHEDULED or FAILED_RETRYABLE) for execution.

    Enforces:
    - Only due items (schedule_at <= now or next_attempt_at <= now) are eligible.
    - Zero double claim under concurrency via atomic CAS.
    - Increments attempt_count and establishes strict lease.
    """
    ensure_autopost_scheduler_schema(conn)

    clean_worker = str(worker_id or "").strip()
    if not clean_worker:
        return None, "worker_id_missing"

    norm_now = canonical_utc_now() if now is None else parse_and_validate_utc(now)[0] or canonical_utc_now()
    lease_sec = max(30, min(3600, int(lease_seconds)))
    lease_expires = add_seconds_to_utc(norm_now, lease_sec)

    cur = conn.cursor()
    # Candidate selection: due SCHEDULED or due FAILED_RETRYABLE
    cur.execute(
        """SELECT * FROM autopost_publication_queue
        WHERE (
            (state='SCHEDULED' AND schedule_at <= ?)
            OR
            (state='FAILED_RETRYABLE' AND next_attempt_at <= ?)
        )
        ORDER BY
            COALESCE(schedule_at, next_attempt_at) ASC,
            publication_id ASC
        LIMIT 1""",
        (norm_now, norm_now),
    )
    candidate = cur.fetchone()
    if not candidate:
        return None, "no_due_publications"
    item = _row_to_dict(candidate)

    # Validate transition
    ok, reason = validate_transition(item["state"], PublicationState.CLAIMED)
    if not ok:
        return None, reason

    # Atomic CAS claim
    cur.execute(
        """UPDATE autopost_publication_queue SET
            state=?,
            lease_owner=?,
            lease_expires_at=?,
            attempt_count=attempt_count+1,
            revision=revision+1,
            updated_at=?
        WHERE publication_id=?
          AND revision=?
          AND (
              (state='SCHEDULED' AND schedule_at <= ?)
              OR
              (state='FAILED_RETRYABLE' AND next_attempt_at <= ?)
          )""",
        (
            PublicationState.CLAIMED.value,
            clean_worker,
            lease_expires,
            norm_now,
            item["publication_id"],
            int(item["revision"]),
            norm_now,
            norm_now,
        ),
    )
    if cur.rowcount != 1:
        return None, "claim_race_conflict"

    conn.commit()

    cur.execute("SELECT * FROM autopost_publication_queue WHERE publication_id=? LIMIT 1", (item["publication_id"],))
    return _row_to_dict(cur.fetchone()), "claimed"


# =========================================================================
# 7. LEASE MANAGEMENT
# =========================================================================

def renew_publication_lease(
    conn: sqlite3.Connection,
    publication_id: str,
    worker_id: str,
    now: Optional[str] = None,
    lease_seconds: int = 600,
) -> tuple[Optional[dict[str, Any]], str]:
    """Renew the active lease of a CLAIMED or PUBLISHING publication.

    Enforces:
    - Only exact current lease_owner may renew
    - Lease must not already be expired
    - Cannot resurrect terminal states
    """
    ensure_autopost_scheduler_schema(conn)

    clean_worker = str(worker_id or "").strip()
    norm_now = canonical_utc_now() if now is None else parse_and_validate_utc(now)[0] or canonical_utc_now()
    lease_sec = max(30, min(3600, int(lease_seconds)))
    new_expires = add_seconds_to_utc(norm_now, lease_sec)

    cur = conn.cursor()
    cur.execute("SELECT * FROM autopost_publication_queue WHERE publication_id=? LIMIT 1", (publication_id,))
    item_row = cur.fetchone()
    if not item_row:
        return None, "publication_not_found"
    item = _row_to_dict(item_row)

    if item["state"] in TERMINAL_STATES:
        return None, f"terminal_state_cannot_renew_lease:{item['state']}"

    if item["state"] not in (PublicationState.CLAIMED.value, PublicationState.PUBLISHING.value):
        return None, f"state_not_leased:{item['state']}"

    if str(item.get("lease_owner") or "").strip() != clean_worker:
        return None, "lease_owner_mismatch"

    existing_expires = str(item.get("lease_expires_at") or "").strip()
    if not existing_expires or existing_expires < norm_now:
        return None, "lease_already_expired"

    cur.execute(
        """UPDATE autopost_publication_queue SET
            lease_expires_at=?,
            revision=revision+1,
            updated_at=?
        WHERE publication_id=?
          AND lease_owner=?
          AND revision=?
          AND state IN ('CLAIMED', 'PUBLISHING')
          AND lease_expires_at >= ?""",
        (
            new_expires,
            norm_now,
            publication_id,
            clean_worker,
            int(item["revision"]),
            norm_now,
        ),
    )
    if cur.rowcount != 1:
        return None, "lease_renewal_conflict"

    conn.commit()
    cur.execute("SELECT * FROM autopost_publication_queue WHERE publication_id=? LIMIT 1", (publication_id,))
    return _row_to_dict(cur.fetchone()), "lease_renewed"


# =========================================================================
# 8. PUBLISHING LIFECYCLE BOUNDARY
# =========================================================================

def mark_publication_started(
    conn: sqlite3.Connection,
    publication_id: str,
    worker_id: str,
    now: Optional[str] = None,
) -> tuple[Optional[dict[str, Any]], str]:
    """Transition CLAIMED -> PUBLISHING before attempting external dispatch.

    Enforces exact lease ownership and unexpired lease.
    """
    ensure_autopost_scheduler_schema(conn)

    clean_worker = str(worker_id or "").strip()
    norm_now = canonical_utc_now() if now is None else parse_and_validate_utc(now)[0] or canonical_utc_now()

    cur = conn.cursor()
    cur.execute("SELECT * FROM autopost_publication_queue WHERE publication_id=? LIMIT 1", (publication_id,))
    item_row = cur.fetchone()
    if not item_row:
        return None, "publication_not_found"
    item = _row_to_dict(item_row)

    if item["state"] != PublicationState.CLAIMED.value:
        return None, f"cannot_start_publishing_in_state:{item['state']}"

    if str(item.get("lease_owner") or "").strip() != clean_worker:
        return None, "lease_owner_mismatch"

    existing_expires = str(item.get("lease_expires_at") or "").strip()
    if not existing_expires or existing_expires < norm_now:
        return None, "lease_expired"

    ok, reason = validate_transition(item["state"], PublicationState.PUBLISHING)
    if not ok:
        return None, reason

    cur.execute(
        """UPDATE autopost_publication_queue SET
            state=?,
            publish_started_at=?,
            revision=revision+1,
            updated_at=?
        WHERE publication_id=?
          AND lease_owner=?
          AND revision=?
          AND state='CLAIMED'""",
        (
            PublicationState.PUBLISHING.value,
            norm_now,
            norm_now,
            publication_id,
            clean_worker,
            int(item["revision"]),
        ),
    )
    if cur.rowcount != 1:
        return None, "start_publishing_conflict"

    conn.commit()
    cur.execute("SELECT * FROM autopost_publication_queue WHERE publication_id=? LIMIT 1", (publication_id,))
    return _row_to_dict(cur.fetchone()), "publishing_started"


def record_publication_result(
    conn: sqlite3.Connection,
    publication_id: str,
    worker_id: str,
    outcome: str,
    error_code: str = "",
    now: Optional[str] = None,
    backoff_base_seconds: int = 60,
    max_backoff_seconds: int = 3600,
) -> tuple[Optional[dict[str, Any]], str]:
    """Record execution result for a PUBLISHING publication.

    Supported outcomes:
    - 'succeeded': transitions PUBLISHING -> PUBLISHED (terminal)
    - 'failed_retryable':
      transitions PUBLISHING -> FAILED_RETRYABLE with deterministic backoff
      OR FAILED_FINAL if attempt_count >= max_attempts
    - 'failed_final':
      transitions PUBLISHING -> FAILED_FINAL (terminal)
    """
    ensure_autopost_scheduler_schema(conn)

    clean_worker = str(worker_id or "").strip()
    norm_now = canonical_utc_now() if now is None else parse_and_validate_utc(now)[0] or canonical_utc_now()
    norm_outcome = str(outcome or "").strip().lower()

    cur = conn.cursor()
    cur.execute("SELECT * FROM autopost_publication_queue WHERE publication_id=? LIMIT 1", (publication_id,))
    item_row = cur.fetchone()
    if not item_row:
        return None, "publication_not_found"
    item = _row_to_dict(item_row)

    if item["state"] != PublicationState.PUBLISHING.value:
        return None, f"cannot_record_result_in_state:{item['state']}"

    if str(item.get("lease_owner") or "").strip() != clean_worker:
        return None, "lease_owner_mismatch"

    existing_expires = str(item.get("lease_expires_at") or "").strip()
    if not existing_expires or existing_expires < norm_now:
        return None, "lease_expired"

    attempt_count = int(item.get("attempt_count") or 1)
    max_attempts = int(item.get("max_attempts") or 3)

    if norm_outcome == "succeeded":
        ok, reason = validate_transition(item["state"], PublicationState.PUBLISHED)
        if not ok:
            return None, reason

        cur.execute(
            """UPDATE autopost_publication_queue SET
                state=?,
                published_at=?,
                lease_owner=NULL,
                lease_expires_at=NULL,
                revision=revision+1,
                updated_at=?
            WHERE publication_id=? AND revision=?""",
            (
                PublicationState.PUBLISHED.value,
                norm_now,
                norm_now,
                publication_id,
                int(item["revision"]),
            ),
        )
        if cur.rowcount != 1:
            return None, "record_result_conflict"

        conn.execute(
            "UPDATE autopost_publication_drafts SET status='PUBLISHED' WHERE draft_id=?",
            (item["draft_id"],),
        )
        conn.commit()

        cur.execute("SELECT * FROM autopost_publication_queue WHERE publication_id=? LIMIT 1", (publication_id,))
        return _row_to_dict(cur.fetchone()), "published"

    elif norm_outcome == "failed_retryable":
        if attempt_count < max_attempts:
            ok, reason = validate_transition(item["state"], PublicationState.FAILED_RETRYABLE)
            if not ok:
                return None, reason

            backoff_sec = calculate_backoff_seconds(attempt_count, base_seconds=backoff_base_seconds, max_seconds=max_backoff_seconds)
            next_attempt = add_seconds_to_utc(norm_now, backoff_sec)

            cur.execute(
                """UPDATE autopost_publication_queue SET
                    state=?,
                    next_attempt_at=?,
                    last_error_code=?,
                    last_error_at=?,
                    lease_owner=NULL,
                    lease_expires_at=NULL,
                    revision=revision+1,
                    updated_at=?
                WHERE publication_id=? AND revision=?""",
                (
                    PublicationState.FAILED_RETRYABLE.value,
                    next_attempt,
                    str(error_code or "retryable_failure"),
                    norm_now,
                    norm_now,
                    publication_id,
                    int(item["revision"]),
                ),
            )
            if cur.rowcount != 1:
                return None, "record_result_conflict"

            conn.commit()
            cur.execute("SELECT * FROM autopost_publication_queue WHERE publication_id=? LIMIT 1", (publication_id,))
            return _row_to_dict(cur.fetchone()), "failed_retryable"
        else:
            # Max attempts reached -> FAILED_FINAL
            ok, reason = validate_transition(item["state"], PublicationState.FAILED_FINAL)
            if not ok:
                return None, reason

            cur.execute(
                """UPDATE autopost_publication_queue SET
                    state=?,
                    last_error_code=?,
                    last_error_at=?,
                    lease_owner=NULL,
                    lease_expires_at=NULL,
                    revision=revision+1,
                    updated_at=?
                WHERE publication_id=? AND revision=?""",
                (
                    PublicationState.FAILED_FINAL.value,
                    str(error_code or "max_attempts_exhausted"),
                    norm_now,
                    norm_now,
                    publication_id,
                    int(item["revision"]),
                ),
            )
            if cur.rowcount != 1:
                return None, "record_result_conflict"

            conn.commit()
            cur.execute("SELECT * FROM autopost_publication_queue WHERE publication_id=? LIMIT 1", (publication_id,))
            return _row_to_dict(cur.fetchone()), "failed_final"

    elif norm_outcome == "failed_final":
        ok, reason = validate_transition(item["state"], PublicationState.FAILED_FINAL)
        if not ok:
            return None, reason

        cur.execute(
            """UPDATE autopost_publication_queue SET
                state=?,
                last_error_code=?,
                last_error_at=?,
                lease_owner=NULL,
                lease_expires_at=NULL,
                revision=revision+1,
                updated_at=?
            WHERE publication_id=? AND revision=?""",
            (
                PublicationState.FAILED_FINAL.value,
                str(error_code or "fatal_failure"),
                norm_now,
                norm_now,
                publication_id,
                int(item["revision"]),
            ),
        )
        if cur.rowcount != 1:
            return None, "record_result_conflict"

        conn.commit()
        cur.execute("SELECT * FROM autopost_publication_queue WHERE publication_id=? LIMIT 1", (publication_id,))
        return _row_to_dict(cur.fetchone()), "failed_final"

    else:
        return None, f"unsupported_outcome:{outcome}"


# =========================================================================
# 9. CRASH RECOVERY
# =========================================================================

def recover_expired_claimed_publication(
    conn: sqlite3.Connection,
    publication_id: str,
    now: Optional[str] = None,
    backoff_base_seconds: int = 60,
    max_backoff_seconds: int = 3600,
) -> tuple[Optional[dict[str, Any]], str]:
    """Recover a CLAIMED publication whose lease expired before publish_started_at.

    Safe recovery rule:
    Since publish_started_at is empty, external dispatch was never started.
    Moves publication to FAILED_RETRYABLE (or FAILED_FINAL if max attempts exhausted).
    Zero producer re-render or re-queue.
    """
    ensure_autopost_scheduler_schema(conn)

    norm_now = canonical_utc_now() if now is None else parse_and_validate_utc(now)[0] or canonical_utc_now()

    cur = conn.cursor()
    cur.execute("SELECT * FROM autopost_publication_queue WHERE publication_id=? LIMIT 1", (publication_id,))
    item_row = cur.fetchone()
    if not item_row:
        return None, "publication_not_found"
    item = _row_to_dict(item_row)

    if item["state"] != PublicationState.CLAIMED.value:
        return None, f"cannot_recover_claimed_in_state:{item['state']}"

    expires = str(item.get("lease_expires_at") or "")
    if expires and expires >= norm_now:
        return None, "lease_not_expired"

    started_at = str(item.get("publish_started_at") or "").strip()
    if started_at:
        return None, "publication_started_ambiguous"

    attempt_count = int(item.get("attempt_count") or 1)
    max_attempts = int(item.get("max_attempts") or 3)

    if attempt_count < max_attempts:
        backoff_sec = calculate_backoff_seconds(attempt_count, base_seconds=backoff_base_seconds, max_seconds=max_backoff_seconds)
        next_attempt = add_seconds_to_utc(norm_now, backoff_sec)

        cur.execute(
            """UPDATE autopost_publication_queue SET
                state=?,
                next_attempt_at=?,
                last_error_code=?,
                last_error_at=?,
                lease_owner=NULL,
                lease_expires_at=NULL,
                revision=revision+1,
                updated_at=?
            WHERE publication_id=? AND revision=?""",
            (
                PublicationState.FAILED_RETRYABLE.value,
                next_attempt,
                "claimed_lease_expired_recovered",
                norm_now,
                norm_now,
                publication_id,
                int(item["revision"]),
            ),
        )
        if cur.rowcount != 1:
            return None, "recover_claimed_conflict"

        conn.commit()
        cur.execute("SELECT * FROM autopost_publication_queue WHERE publication_id=? LIMIT 1", (publication_id,))
        return _row_to_dict(cur.fetchone()), "recovered_to_retryable"
    else:
        cur.execute(
            """UPDATE autopost_publication_queue SET
                state=?,
                last_error_code=?,
                last_error_at=?,
                lease_owner=NULL,
                lease_expires_at=NULL,
                revision=revision+1,
                updated_at=?
            WHERE publication_id=? AND revision=?""",
            (
                PublicationState.FAILED_FINAL.value,
                "claimed_lease_expired_max_attempts",
                norm_now,
                norm_now,
                publication_id,
                int(item["revision"]),
            ),
        )
        if cur.rowcount != 1:
            return None, "recover_claimed_conflict"

        conn.commit()
        cur.execute("SELECT * FROM autopost_publication_queue WHERE publication_id=? LIMIT 1", (publication_id,))
        return _row_to_dict(cur.fetchone()), "recovered_to_final"


def inspect_ambiguous_publishing_publication(
    conn: sqlite3.Connection,
    publication_id: str,
    now: Optional[str] = None,
) -> tuple[Optional[dict[str, Any]], str]:
    """Inspect and fail-closed guard a PUBLISHING publication whose lease expired.

    Critical invariant:
    DO NOT AUTO-REPUBLISH. An external provider call may have already succeeded.
    Exposes durable blocker 'external_reconciliation_required' without blind retry.
    """
    ensure_autopost_scheduler_schema(conn)

    norm_now = canonical_utc_now() if now is None else parse_and_validate_utc(now)[0] or canonical_utc_now()

    cur = conn.cursor()
    cur.execute("SELECT * FROM autopost_publication_queue WHERE publication_id=? LIMIT 1", (publication_id,))
    item_row = cur.fetchone()
    if not item_row:
        return None, "publication_not_found"
    item = _row_to_dict(item_row)

    if item["state"] != PublicationState.PUBLISHING.value:
        return None, f"not_in_publishing_state:{item['state']}"

    expires = str(item.get("lease_expires_at") or "")
    if expires and expires >= norm_now:
        return None, "lease_not_expired"

    # Block blind retry: expose reconciliation required
    cur.execute(
        """UPDATE autopost_publication_queue SET
            last_error_code=?,
            last_error_at=?,
            lease_owner=NULL,
            lease_expires_at=NULL,
            revision=revision+1,
            updated_at=?
        WHERE publication_id=? AND revision=?""",
        (
            "external_reconciliation_required",
            norm_now,
            norm_now,
            publication_id,
            int(item["revision"]),
        ),
    )
    conn.commit()

    cur.execute("SELECT * FROM autopost_publication_queue WHERE publication_id=? LIMIT 1", (publication_id,))
    return _row_to_dict(cur.fetchone()), "external_reconciliation_required"


# =========================================================================
# 10. CANONICAL ARTIFACT REVALIDATION
# =========================================================================

def revalidate_publication_artifact(
    conn: sqlite3.Connection,
    publication_id: str,
) -> tuple[bool, str]:
    """Reread durable canonical handoff & physical artifact truth before dispatch.

    Enforces:
    - Rereads from SQLite (never trusts client cache)
    - Validates owner binding
    - Verifies artifact_sha256 matches recorded handoff
    - Probes physical file with zero write lock held
    """
    ensure_autopost_scheduler_schema(conn)

    cur = conn.cursor()
    cur.execute("SELECT * FROM autopost_publication_queue WHERE publication_id=? LIMIT 1", (publication_id,))
    q_row = cur.fetchone()
    if not q_row:
        return False, "publication_not_found"
    item = _row_to_dict(q_row)

    cur.execute(
        "SELECT * FROM autopost_handoff_receipts WHERE handoff_id=? LIMIT 1",
        (item["handoff_id"],),
    )
    handoff_row = cur.fetchone()
    if not handoff_row:
        return False, "handoff_receipt_missing"
    handoff = _row_to_dict(handoff_row)

    if int(handoff["owner_id"]) != int(item["owner_id"]):
        return False, "owner_mismatch"

    if handoff["asset_id"] != item["asset_id"]:
        return False, "asset_id_mismatch"

    if handoff["artifact_sha256"] != item["artifact_sha256"]:
        return False, "artifact_sha_mismatch"

    # Extract internal physical artifact path from snapshot
    try:
        snapshot = json.loads(handoff.get("asset_snapshot_json") or "{}")
    except Exception:
        snapshot = {}

    internal_path = str(snapshot.get("internal_artifact_path") or "").strip()
    if not internal_path or not os.path.isfile(internal_path):
        return False, "artifact_file_not_found"

    # Media validation & SHA computation (outside DB write lock)
    valid, probe, reason = aah._validate_final_mp4(internal_path)
    if not valid:
        return False, f"media_probe_failed:{reason}"

    physical_sha = hashlib.sha256(Path(internal_path).read_bytes()).hexdigest().lower()
    if physical_sha != item["artifact_sha256"]:
        return False, "artifact_replacement_detected"

    return True, ""


# =========================================================================
# 11. CANCELLATION
# =========================================================================

def cancel_publication(
    conn: sqlite3.Connection,
    publication_id: str,
    requesting_user_id: int,
    reason: str = "",
) -> tuple[Optional[dict[str, Any]], str]:
    """Explicit owner-bound publication cancellation.

    Allowed from: PLANNED, APPROVED, SCHEDULED, FAILED_RETRYABLE.
    PUBLISHED cannot be cancelled.
    PUBLISHING cannot be cancelled (ambiguous external effect).
    """
    ensure_autopost_scheduler_schema(conn)

    norm_now = canonical_utc_now()
    cur = conn.cursor()
    cur.execute("SELECT * FROM autopost_publication_queue WHERE publication_id=? LIMIT 1", (publication_id,))
    item_row = cur.fetchone()
    if not item_row:
        return None, "publication_not_found"
    item = _row_to_dict(item_row)

    if int(item["owner_id"]) != int(requesting_user_id):
        return None, "owner_mismatch"

    curr_state = item["state"]
    if curr_state == PublicationState.PUBLISHED.value:
        return None, "published_cannot_cancel"

    if curr_state == PublicationState.PUBLISHING.value:
        return None, "ambiguous_publishing_cannot_cancel"

    if curr_state in (PublicationState.CANCELLED.value, PublicationState.FAILED_FINAL.value):
        return item, "already_cancelled_or_final"

    ok, trans_err = validate_transition(curr_state, PublicationState.CANCELLED)
    if not ok:
        return None, trans_err

    cur.execute(
        """UPDATE autopost_publication_queue SET
            state=?,
            cancelled_at=?,
            last_error_code=?,
            last_error_at=?,
            lease_owner=NULL,
            lease_expires_at=NULL,
            revision=revision+1,
            updated_at=?
        WHERE publication_id=? AND revision=?""",
        (
            PublicationState.CANCELLED.value,
            norm_now,
            str(reason or "user_cancelled"),
            norm_now,
            norm_now,
            publication_id,
            int(item["revision"]),
        ),
    )
    if cur.rowcount != 1:
        return None, "cancel_conflict"

    conn.execute(
        "UPDATE autopost_publication_drafts SET status='CANCELLED' WHERE draft_id=?",
        (item["draft_id"],),
    )
    conn.commit()

    cur.execute("SELECT * FROM autopost_publication_queue WHERE publication_id=? LIMIT 1", (publication_id,))
    return _row_to_dict(cur.fetchone()), "cancelled"
