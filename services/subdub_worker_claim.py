"""Canonical Bot Core SubDub Durable Worker Claim Authority (BOT-SUBDUB-D4).

Governed by owner-governed-codex, locked-focus-engineering.
Enforces:
1. Atomic durable claim with SQLite BEGIN IMMEDIATE.
2. Fencing / worker token invariant: every claim issues a unique claim_token; stale workers rejected.
3. Monotonic transition: queued -> processing -> completed / failed / cancelled.
4. Duplicate execution prevention: concurrent claims yield exactly one winner.
5. Worker crash recovery: expired leases automatically requeued; max_attempts bounded.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
import logging
import sqlite3
import uuid
from typing import Any

logger = logging.getLogger("subdub_worker_claim")


def now_utc_str(dt: datetime | None = None) -> str:
    """Return ISO-like UTC timestamp string with microsecond precision."""
    target = dt or datetime.now(timezone.utc)
    return target.strftime("%Y-%m-%d %H:%M:%S.%f")


def ensure_subdub_worker_queue_schema(conn: sqlite3.Connection) -> None:
    """Create subdub_worker_jobs table and indexes if not exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS subdub_worker_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE NOT NULL,
            owner_id TEXT NOT NULL,
            mode TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            priority INTEGER DEFAULT 10,
            attempts INTEGER DEFAULT 0,
            max_attempts INTEGER DEFAULT 3,
            worker_id TEXT DEFAULT '',
            claim_token TEXT DEFAULT '',
            locked_at TEXT,
            lease_expires_at TEXT,
            last_error TEXT DEFAULT '',
            payload_json TEXT DEFAULT '{}',
            result_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_subdub_worker_jobs_claim ON subdub_worker_jobs(status, priority, created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_subdub_worker_jobs_lease ON subdub_worker_jobs(status, lease_expires_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_subdub_worker_jobs_owner ON subdub_worker_jobs(owner_id, status)"
    )


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    # Parse payload and result JSON safely
    try:
        record["payload"] = json.loads(record.get("payload_json") or "{}")
    except Exception:
        record["payload"] = {}
    try:
        record["result"] = json.loads(record.get("result_json") or "{}")
    except Exception:
        record["result"] = {}
    return record


def enqueue_subdub_job(
    owner_id: str | int,
    mode: str,
    payload: dict[str, Any] | None = None,
    *,
    priority: int = 10,
    max_attempts: int = 3,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Enqueue a new SubDub job into the durable worker queue."""
    import bot
    owned = conn is None
    db = conn or bot.db_connect()
    try:
        ensure_subdub_worker_queue_schema(db)
        clean_owner = str(owner_id or "").strip()
        from services.subdub_voice_resolution import normalize_subdub_mode
        clean_mode = normalize_subdub_mode(mode) or "dub"

        job_id = f"subdub_{uuid.uuid4().hex[:18]}"
        now_str = now_utc_str()
        payload_str = json.dumps(payload or {}, ensure_ascii=False)

        cur = db.execute(
            """
            INSERT INTO subdub_worker_jobs (
                job_id, owner_id, mode, status, priority, attempts, max_attempts,
                payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, 'queued', ?, 0, ?, ?, ?, ?)
            """,
            (
                job_id,
                clean_owner,
                clean_mode,
                int(priority),
                max(1, int(max_attempts)),
                payload_str,
                now_str,
                now_str,
            ),
        )
        db.commit()
        return get_subdub_worker_job(job_id, conn=db) or {}
    finally:
        if owned:
            db.close()


def requeue_stale_subdub_jobs(
    conn: sqlite3.Connection,
    *,
    now_dt: datetime | None = None,
) -> int:
    """Requeue jobs whose leases have expired (worker crash recovery).
    
    Jobs that exceed max_attempts are failed permanently.
    """
    ensure_subdub_worker_queue_schema(conn)
    current_dt = now_dt or datetime.now(timezone.utc)
    current_str = now_utc_str(current_dt)

    # 1. Permanently fail jobs exceeding max_attempts
    conn.execute(
        """
        UPDATE subdub_worker_jobs
        SET status='failed', updated_at=?, completed_at=?, last_error='max_attempts_exceeded', lease_expires_at=NULL
        WHERE status='processing'
          AND lease_expires_at IS NOT NULL
          AND lease_expires_at <= ?
          AND attempts >= max_attempts
        """,
        (current_str, current_str, current_str),
    )

    # 2. Requeue recoverable jobs (attempts < max_attempts)
    cur = conn.execute(
        """
        UPDATE subdub_worker_jobs
        SET status='queued', worker_id='', claim_token='', locked_at=NULL, lease_expires_at=NULL,
            updated_at=?, last_error='worker_lease_expired'
        WHERE status='processing'
          AND lease_expires_at IS NOT NULL
          AND lease_expires_at <= ?
          AND attempts < max_attempts
        """,
        (current_str, current_str),
    )
    return int(cur.rowcount or 0)


def claim_next_subdub_job(
    worker_id: str,
    *,
    lease_seconds: int = 600,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Atomically claim the next queued SubDub job with a unique fencing token."""
    import bot
    owned = conn is None
    db = conn or bot.db_connect()
    db.row_factory = sqlite3.Row
    try:
        ensure_subdub_worker_queue_schema(db)
        clean_worker = str(worker_id or "worker").strip()[:80]
        now_dt = datetime.now(timezone.utc)
        now_str = now_utc_str(now_dt)
        lease_exp_dt = now_dt + timedelta(seconds=max(1, int(lease_seconds)))
        lease_exp_str = now_utc_str(lease_exp_dt)

        db.execute("BEGIN IMMEDIATE")
        requeue_stale_subdub_jobs(db, now_dt=now_dt)

        row = db.execute(
            """
            SELECT * FROM subdub_worker_jobs
            WHERE status='queued'
            ORDER BY priority ASC, created_at ASC, id ASC
            LIMIT 1
            """
        ).fetchone()

        if not row:
            db.commit()
            return None

        job_pk = row["id"]
        job_id = row["job_id"]
        fencing_token = f"claim_{uuid.uuid4().hex[:18]}"

        cur = db.execute(
            """
            UPDATE subdub_worker_jobs
            SET status='processing', worker_id=?, claim_token=?, locked_at=?, lease_expires_at=?,
                attempts=attempts+1, started_at=COALESCE(started_at, ?), updated_at=?
            WHERE id=? AND status='queued'
            """,
            (clean_worker, fencing_token, now_str, lease_exp_str, now_str, now_str, job_pk),
        )

        if cur.rowcount != 1:
            db.rollback()
            return None

        db.commit()
        return get_subdub_worker_job(job_id, conn=db)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        if owned:
            db.close()


def heartbeat_subdub_job(
    job_id: str,
    worker_id: str,
    claim_token: str,
    *,
    lease_seconds: int = 600,
    conn: sqlite3.Connection | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Extend lease on a currently processing job (verifying fencing token)."""
    import bot
    owned = conn is None
    db = conn or bot.db_connect()
    db.row_factory = sqlite3.Row
    try:
        ensure_subdub_worker_queue_schema(db)
        clean_job = str(job_id or "").strip()
        clean_worker = str(worker_id or "").strip()
        clean_token = str(claim_token or "").strip()

        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM subdub_worker_jobs WHERE job_id=?", (clean_job,)).fetchone()
        if not row:
            db.rollback()
            return False, "JOB_NOT_FOUND", {}

        r = dict(row)
        if r["status"] != "processing":
            db.rollback()
            return False, "JOB_NOT_PROCESSING", {}

        if r["worker_id"] != clean_worker or r["claim_token"] != clean_token:
            db.rollback()
            return False, "FENCING_TOKEN_MISMATCH", {}

        now_dt = datetime.now(timezone.utc)
        now_str = now_utc_str(now_dt)
        lease_exp_dt = now_dt + timedelta(seconds=max(1, int(lease_seconds)))
        lease_exp_str = now_utc_str(lease_exp_dt)

        db.execute(
            """
            UPDATE subdub_worker_jobs
            SET lease_expires_at=?, updated_at=?
            WHERE job_id=? AND status='processing' AND claim_token=?
            """,
            (lease_exp_str, now_str, clean_job, clean_token),
        )
        db.commit()
        return True, "OK", {"job_id": clean_job, "lease_expires_at": lease_exp_str}
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        return False, f"HEARTBEAT_ERROR:{type(exc).__name__}", {}
    finally:
        if owned:
            db.close()


def complete_subdub_job(
    job_id: str,
    worker_id: str,
    claim_token: str,
    result: dict[str, Any] | None = None,
    *,
    conn: sqlite3.Connection | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Monotonically mark job as completed (verifying fencing token)."""
    import bot
    owned = conn is None
    db = conn or bot.db_connect()
    db.row_factory = sqlite3.Row
    try:
        ensure_subdub_worker_queue_schema(db)
        clean_job = str(job_id or "").strip()
        clean_worker = str(worker_id or "").strip()
        clean_token = str(claim_token or "").strip()

        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM subdub_worker_jobs WHERE job_id=?", (clean_job,)).fetchone()
        if not row:
            db.rollback()
            return False, "JOB_NOT_FOUND", {}

        r = dict(row)
        if r["status"] != "processing":
            db.rollback()
            return False, "JOB_NOT_PROCESSING", {}

        if r["worker_id"] != clean_worker or r["claim_token"] != clean_token:
            db.rollback()
            return False, "FENCING_TOKEN_MISMATCH", {}

        now_str = now_utc_str()
        result_str = json.dumps(result or {}, ensure_ascii=False)

        db.execute(
            """
            UPDATE subdub_worker_jobs
            SET status='completed', result_json=?, completed_at=?, updated_at=?, lease_expires_at=NULL
            WHERE job_id=? AND status='processing' AND claim_token=?
            """,
            (result_str, now_str, now_str, clean_job, clean_token),
        )
        db.commit()
        return True, "OK", {"job_id": clean_job, "status": "completed"}
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        return False, f"COMPLETE_ERROR:{type(exc).__name__}", {}
    finally:
        if owned:
            db.close()


def fail_subdub_job(
    job_id: str,
    worker_id: str,
    claim_token: str,
    error_code: str = "",
    message: str = "",
    *,
    conn: sqlite3.Connection | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Monotonically mark job as failed (verifying fencing token)."""
    import bot
    owned = conn is None
    db = conn or bot.db_connect()
    db.row_factory = sqlite3.Row
    try:
        ensure_subdub_worker_queue_schema(db)
        clean_job = str(job_id or "").strip()
        clean_worker = str(worker_id or "").strip()
        clean_token = str(claim_token or "").strip()

        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM subdub_worker_jobs WHERE job_id=?", (clean_job,)).fetchone()
        if not row:
            db.rollback()
            return False, "JOB_NOT_FOUND", {}

        r = dict(row)
        if r["status"] != "processing":
            db.rollback()
            return False, "JOB_NOT_PROCESSING", {}

        if r["worker_id"] != clean_worker or r["claim_token"] != clean_token:
            db.rollback()
            return False, "FENCING_TOKEN_MISMATCH", {}

        now_str = now_utc_str()
        err_msg = f"{error_code}: {message}".strip(" :") or "worker_failed"

        db.execute(
            """
            UPDATE subdub_worker_jobs
            SET status='failed', last_error=?, completed_at=?, updated_at=?, lease_expires_at=NULL
            WHERE job_id=? AND status='processing' AND claim_token=?
            """,
            (err_msg, now_str, now_str, clean_job, clean_token),
        )
        db.commit()
        return True, "OK", {"job_id": clean_job, "status": "failed", "last_error": err_msg}
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        return False, f"FAIL_ERROR:{type(exc).__name__}", {}
    finally:
        if owned:
            db.close()


def get_subdub_worker_job(
    job_id: str,
    *,
    actor_id: str | int | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Retrieve SubDub worker job, enforcing owner check if actor_id provided."""
    import bot
    owned = conn is None
    db = conn or bot.db_connect()
    db.row_factory = sqlite3.Row
    try:
        ensure_subdub_worker_queue_schema(db)
        clean_job = str(job_id or "").strip()
        row = db.execute("SELECT * FROM subdub_worker_jobs WHERE job_id=?", (clean_job,)).fetchone()
        if not row:
            return None
        record = _row_to_dict(row)
        if actor_id is not None:
            clean_actor = str(actor_id).strip()
            if clean_actor and str(record.get("owner_id")) != clean_actor:
                return None
        return record
    finally:
        if owned:
            db.close()
