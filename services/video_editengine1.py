"""Persistent contract for the canonical local Video Edit engine.

The bot owns admission and billing.  The local worker owns FFmpeg rendering and
Telegram delivery.  This module keeps those two sides joined by an idempotent
job/outbox record without importing Telegram, wallet, or provider code.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime
from typing import Any


PRODUCT_TYPE = "video_edit"
WORKER_JOB_TYPE = "video_local_edit"
ENGINE_ROUTE = "local_worker_ffmpeg"
OUTBOX_OWNER = "local_video_edit"
WORKER_CAPABILITY = "video_edit"
HEARTBEAT_TTL_SECONDS = 90
TERMINAL_JOB_STATES = frozenset({"delivered", "charged", "failed_no_charge"})


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _load(value: Any, default: Any) -> Any:
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return deepcopy(default)


def _ensure_column(conn, table: str, column: str, definition: str) -> None:
    columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def ensure_schema(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS video_edit_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            idempotency_key TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            product_type TEXT NOT NULL DEFAULT 'video_edit',
            worker_job_type TEXT NOT NULL DEFAULT 'video_local_edit',
            engine_route TEXT NOT NULL DEFAULT 'local_worker_ffmpeg',
            worker_owner TEXT NOT NULL DEFAULT 'local_video_edit',
            edit_session_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            source_file_id TEXT NOT NULL,
            source_video_path TEXT NOT NULL DEFAULT '',
            source_sha256 TEXT NOT NULL DEFAULT '',
            source_metadata_json TEXT NOT NULL DEFAULT '{}',
            plan_json TEXT NOT NULL DEFAULT '{}',
            tail_json TEXT NOT NULL DEFAULT '{}',
            quality_tier_id TEXT NOT NULL DEFAULT '',
            price_xu INTEGER NOT NULL DEFAULT 0,
            local_worker_job_id INTEGER NOT NULL UNIQUE,
            progress_percent INTEGER NOT NULL DEFAULT 0,
            blocker TEXT NOT NULL DEFAULT '',
            output_file_id TEXT NOT NULL DEFAULT '',
            output_path TEXT NOT NULL DEFAULT '',
            output_sha256 TEXT NOT NULL DEFAULT '',
            output_size_bytes INTEGER NOT NULL DEFAULT 0,
            ffprobe_json TEXT NOT NULL DEFAULT '{}',
            delivery_message_id TEXT NOT NULL DEFAULT '',
            delivery_file_id TEXT NOT NULL DEFAULT '',
            receipt_state TEXT NOT NULL DEFAULT 'not_created',
            charge_state TEXT NOT NULL DEFAULT 'not_charged',
            charged_xu INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            started_at TEXT NOT NULL DEFAULT '',
            delivered_at TEXT NOT NULL DEFAULT '',
            charged_at TEXT NOT NULL DEFAULT '',
            finished_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        )"""
    )
    _ensure_column(conn, "video_edit_jobs", "worker_job_type", "TEXT NOT NULL DEFAULT 'video_local_edit'")
    _ensure_column(conn, "video_edit_jobs", "worker_owner", "TEXT NOT NULL DEFAULT 'local_video_edit'")
    _ensure_column(conn, "video_edit_jobs", "source_video_path", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "video_edit_jobs", "source_sha256", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "video_edit_jobs", "output_path", "TEXT NOT NULL DEFAULT ''")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS video_edit_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            edit_job_id INTEGER NOT NULL UNIQUE,
            local_worker_job_id INTEGER NOT NULL UNIQUE,
            owner TEXT NOT NULL DEFAULT 'local_video_edit',
            status TEXT NOT NULL DEFAULT 'pending',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            available_at TEXT NOT NULL,
            lease_owner TEXT NOT NULL DEFAULT '',
            lease_expires_at TEXT NOT NULL DEFAULT '',
            terminal_reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video_edit_jobs_user_status ON video_edit_jobs(user_id,status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video_edit_outbox_owner_status ON video_edit_outbox(owner,status,available_at)")


def stable_idempotency_key(*, user_id: Any, edit_session_id: Any, plan: dict, quality_tier_id: Any) -> str:
    material = _json({
        "user_id": str(user_id or ""),
        "edit_session_id": str(edit_session_id or ""),
        "plan": dict(plan or {}),
        "quality_tier_id": str(quality_tier_id or ""),
    })
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def preflight(state: dict, runtime: dict) -> dict[str, Any]:
    """Return exact admission truth; this function has no side effects."""
    current = dict(state or {})
    metadata = dict(current.get("source_metadata") or {})
    worker = dict(runtime or {})
    plan = dict(current.get("manual_edit_plan") or {})
    brightness = plan.get("brightness_percent", 100)
    try:
        brightness_valid = 20 <= int(brightness) <= 200
    except (TypeError, ValueError):
        brightness_valid = False
    try:
        contract_enabled = int(worker.get("heartbeat_contract_version") or 0) >= 1
    except (TypeError, ValueError):
        contract_enabled = False
    capabilities = worker.get("capabilities")
    if isinstance(capabilities, str):
        capabilities = [item.strip() for item in capabilities.split(",") if item.strip()]
    capabilities = {str(item).strip() for item in capabilities or [] if str(item).strip()}
    heartbeat_age = worker.get("heartbeat_age_seconds", worker.get("age_seconds"))
    try:
        heartbeat_fresh = heartbeat_age is not None and 0 <= int(heartbeat_age) <= HEARTBEAT_TTL_SECONDS
    except (TypeError, ValueError):
        heartbeat_fresh = False
    checks = {
        "source_file": bool(str(current.get("source_file_id") or "").strip()),
        "source_probe": bool(current.get("inspection_complete") and metadata.get("ok")),
        "operation": bool(
            str(current.get("selected_tool") or "").strip()
            and (plan or list(current.get("split_ranges") or []))
        ),
        "brightness": brightness_valid,
        "worker_enabled": bool(worker.get("enabled")),
        "poll_enabled": bool(worker.get("poll_enabled")),
        "token_configured": bool(worker.get("token_configured")),
        "heartbeat": bool(worker.get("connected")),
        "ffmpeg": bool(worker.get("ffmpeg_path_configured") or worker.get("ffmpeg_seen")),
        "ffprobe": bool(worker.get("ffprobe_path_configured")),
        "delivery": bool(worker.get("delivery_configured", True)),
    }
    contract_checks = {
        "worker_owner": str(worker.get("worker_owner") or "") == OUTBOX_OWNER,
        "engine_route": str(worker.get("engine_route") or "") == ENGINE_ROUTE,
        "capability": WORKER_CAPABILITY in capabilities,
        "heartbeat_ttl": heartbeat_fresh,
    }
    if contract_enabled:
        checks.update(contract_checks)
    reason_order = [
        ("source_file", "source_file_missing"),
        ("source_probe", "source_probe_missing"),
        ("operation", "edit_operation_missing"),
        ("brightness", "brightness_invalid"),
        ("worker_enabled", "local_worker_disabled"),
        ("poll_enabled", "local_worker_poll_disabled"),
        ("token_configured", "local_worker_token_missing"),
        ("heartbeat", "local_worker_heartbeat_stale"),
        ("ffmpeg", "ffmpeg_missing"),
        ("ffprobe", "ffprobe_missing"),
        ("delivery", "telegram_delivery_unavailable"),
    ]
    if contract_enabled:
        heartbeat_index = reason_order.index(("heartbeat", "local_worker_heartbeat_stale")) + 1
        reason_order[heartbeat_index:heartbeat_index] = [
            ("worker_owner", "local_worker_owner_mismatch"),
            ("engine_route", "local_worker_route_mismatch"),
            ("capability", "local_worker_capability_missing"),
            ("heartbeat_ttl", "local_worker_heartbeat_stale"),
        ]
    reason = next((code for key, code in reason_order if not checks[key]), "ok")
    audio = dict((current.get("video_tail9") or {}).get("audio_config") or {})
    unsupported = [key for key in ("dubbing", "music", "sfx", "subtitles") if audio.get(key)]
    if reason == "ok" and unsupported:
        reason = "local_edit_addon_runtime_unavailable"
    return {
        "ok": reason == "ok",
        "ready": reason == "ok",
        "reason": reason,
        "blocker": "" if reason == "ok" else reason,
        "checks": checks,
        "unsupported_addons": unsupported,
        "product_type": PRODUCT_TYPE,
        "worker_job_type": WORKER_JOB_TYPE,
        "engine_route": ENGINE_ROUTE,
        "owner": OUTBOX_OWNER,
        "queue": "local_worker_jobs",
        "worker_id": str(worker.get("worker_id") or ""),
        "heartbeat_age_seconds": heartbeat_age,
    }


def create_job(
    conn,
    *,
    user_id: Any,
    chat_id: Any,
    edit_session_id: str,
    source_file_id: str,
    source_metadata: dict,
    plan: dict,
    tail: dict,
    quality_tier_id: str,
    price_xu: int,
    worker_payload: dict,
) -> dict[str, Any]:
    """Create edit job, persistent outbox and worker queue row atomically."""
    ensure_schema(conn)
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    token = stable_idempotency_key(
        user_id=user_id,
        edit_session_id=edit_session_id,
        plan=plan,
        quality_tier_id=quality_tier_id,
    )
    existing = conn.execute(
        "SELECT id,local_worker_job_id,status FROM video_edit_jobs WHERE idempotency_key=?",
        (token,),
    ).fetchone()
    if existing:
        outbox = conn.execute(
            "SELECT id FROM video_edit_outbox WHERE edit_job_id=?",
            (int(existing[0]),),
        ).fetchone()
        return {
            "created": False,
            "edit_job_id": int(existing[0]),
            "local_worker_job_id": int(existing[1]),
            "outbox_id": int(outbox[0]) if outbox else 0,
            "status": str(existing[2] or "queued"),
            "idempotency_key": token,
        }
    now = _now()
    worker_payload = dict(worker_payload or {})
    worker_payload["edit_idempotency_key"] = token
    worker_payload["product_type"] = PRODUCT_TYPE
    worker_payload["worker_job_type"] = WORKER_JOB_TYPE
    worker_payload["engine_route"] = ENGINE_ROUTE
    cursor = conn.execute(
        """INSERT INTO local_worker_jobs
           (user_id,command,job_type,status,provider,input_file_id,created_at,xu_cost,admin_only,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            str(user_id or ""), "video_editengine1", WORKER_JOB_TYPE, "queued", ENGINE_ROUTE,
            _json(worker_payload), now, max(0, int(price_xu or 0)), 0, now,
        ),
    )
    worker_job_id = int(cursor.lastrowid)
    cursor = conn.execute(
        """INSERT INTO video_edit_jobs
           (idempotency_key,user_id,chat_id,product_type,worker_job_type,engine_route,worker_owner,
            edit_session_id,status,source_file_id,source_video_path,source_sha256,source_metadata_json,plan_json,
            tail_json,quality_tier_id,price_xu,local_worker_job_id,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            token, str(user_id or ""), str(chat_id or ""), PRODUCT_TYPE, WORKER_JOB_TYPE,
            ENGINE_ROUTE, OUTBOX_OWNER, str(edit_session_id or ""), "queued",
            str(source_file_id or ""), str(worker_payload.get("source_file_name") or "")[:240],
            str(worker_payload.get("source_video_hash") or worker_payload.get("source_sha256") or "")[:128],
            _json(source_metadata or {}), _json(plan or {}), _json(tail or {}),
            str(quality_tier_id or ""), max(0, int(price_xu or 0)), worker_job_id, now, now,
        ),
    )
    edit_job_id = int(cursor.lastrowid)
    outbox_cursor = conn.execute(
        """INSERT INTO video_edit_outbox
           (edit_job_id,local_worker_job_id,owner,status,attempt_count,available_at,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (edit_job_id, worker_job_id, OUTBOX_OWNER, "pending", 0, now, now, now),
    )
    return {
        "created": True,
        "edit_job_id": edit_job_id,
        "local_worker_job_id": worker_job_id,
        "outbox_id": int(outbox_cursor.lastrowid),
        "status": "queued",
        "idempotency_key": token,
    }


def get_job_by_worker_id(conn, worker_job_id: Any) -> dict[str, Any]:
    ensure_schema(conn)
    row = conn.execute(
        """SELECT id,idempotency_key,user_id,chat_id,product_type,worker_job_type,engine_route,
                  worker_owner,status,edit_session_id,quality_tier_id,price_xu,local_worker_job_id,
                  progress_percent,blocker,source_video_path,source_sha256,output_file_id,output_path,output_sha256,
                  output_size_bytes,ffprobe_json,delivery_message_id,delivery_file_id,
                  receipt_state,charge_state,charged_xu,tail_json
           FROM video_edit_jobs WHERE local_worker_job_id=?""",
        (int(worker_job_id or 0),),
    ).fetchone()
    if not row:
        return {}
    fields = (
        "id", "idempotency_key", "user_id", "chat_id", "product_type", "worker_job_type",
        "engine_route", "worker_owner", "status", "edit_session_id", "quality_tier_id",
        "price_xu", "local_worker_job_id", "progress_percent", "blocker", "source_video_path",
        "source_sha256", "output_file_id", "output_path", "output_sha256", "output_size_bytes", "ffprobe_json",
        "delivery_message_id", "delivery_file_id", "receipt_state", "charge_state",
        "charged_xu", "tail_json",
    )
    result = dict(zip(fields, row))
    result["ffprobe"] = _load(result.pop("ffprobe_json"), {})
    result["tail"] = _load(result.pop("tail_json"), {})
    return result


def record_worker_update(conn, *, worker_job_id: Any, worker_status: str, detail: dict, receipt: dict) -> dict[str, Any]:
    ensure_schema(conn)
    current = get_job_by_worker_id(conn, worker_job_id)
    if not current:
        return {}
    if str(current.get("status") or "") in TERMINAL_JOB_STATES:
        return current
    now = _now()
    status = str(worker_status or "").lower()
    detail = dict(detail or {})
    receipt = dict(receipt or {})
    if status == "running":
        stage = str(detail.get("stage") or "rendering")
        progress = {"inspecting_input": 25, "preparing_plan": 35, "processing_video": 55, "validating_output": 80, "delivering": 90}.get(stage, 40)
        conn.execute(
            "UPDATE video_edit_jobs SET status='rendering',progress_percent=?,started_at=CASE WHEN started_at='' THEN ? ELSE started_at END,updated_at=? WHERE id=?",
            (progress, now, now, int(current["id"])),
        )
        conn.execute(
            "UPDATE video_edit_outbox SET status='running',attempt_count=CASE WHEN attempt_count=0 THEN 1 ELSE attempt_count END,updated_at=? WHERE edit_job_id=?",
            (now, int(current["id"])),
        )
    elif status == "succeeded":
        valid = bool(
            detail.get("validation") == "passed"
            and receipt.get("delivery_message_id")
            and receipt.get("delivery_file_id")
            and receipt.get("output_sha256")
            and int(receipt.get("output_size_bytes") or 0) > 0
            and dict(receipt.get("ffprobe") or {}).get("ok")
        )
        if valid:
            conn.execute(
                """UPDATE video_edit_jobs SET status='delivered',progress_percent=100,blocker='',
                   source_video_path=?,source_sha256=?,output_file_id=?,output_path=?,output_sha256=?,output_size_bytes=?,ffprobe_json=?,
                   delivery_message_id=?,delivery_file_id=?,receipt_state='created',
                   delivered_at=?,finished_at=?,updated_at=? WHERE id=?""",
                (
                    str(receipt.get("source_video_path") or current.get("source_video_path") or "")[:240],
                    str(receipt.get("source_sha256") or "")[:128],
                    str(receipt.get("delivery_file_id") or "")[:500],
                    str(receipt.get("output_path") or "")[:500],
                    str(receipt.get("output_sha256") or "")[:128],
                    int(receipt.get("output_size_bytes") or 0),
                    _json(receipt.get("ffprobe") or {}),
                    str(receipt.get("delivery_message_id") or "")[:900],
                    str(receipt.get("delivery_file_id") or "")[:500],
                    now, now, now, int(current["id"]),
                ),
            )
            conn.execute(
                "UPDATE video_edit_outbox SET status='delivered',terminal_reason='',updated_at=? WHERE edit_job_id=?",
                (now, int(current["id"])),
            )
        else:
            status = "failed"
            detail = {**detail, "reason": "delivery_receipt_invalid"}
    if status in {"failed", "cancelled"}:
        reason = str(detail.get("reason") or "local_edit_failed_no_charge")[:180]
        conn.execute(
            """UPDATE video_edit_jobs SET status='failed_no_charge',progress_percent=0,blocker=?,
               charge_state='not_charged',charged_xu=0,finished_at=?,updated_at=? WHERE id=?""",
            (reason, now, now, int(current["id"])),
        )
        conn.execute(
            "UPDATE video_edit_outbox SET status='terminal_failed',terminal_reason=?,updated_at=? WHERE edit_job_id=?",
            (reason, now, int(current["id"])),
        )
    return get_job_by_worker_id(conn, worker_job_id)


def mark_charge_result(conn, *, worker_job_id: Any, ok: bool, charged_xu: int = 0, reason: str = "") -> dict[str, Any]:
    current = get_job_by_worker_id(conn, worker_job_id)
    if not current or current.get("receipt_state") != "created":
        return current
    now = _now()
    if current.get("charge_state") == "charged":
        return current
    if ok:
        conn.execute(
            "UPDATE video_edit_jobs SET status='charged',charge_state='charged',charged_xu=?,charged_at=?,updated_at=? WHERE id=?",
            (max(0, int(charged_xu or 0)), now, now, int(current["id"])),
        )
    else:
        conn.execute(
            "UPDATE video_edit_jobs SET charge_state='charge_failed',blocker=?,updated_at=? WHERE id=?",
            (str(reason or "charge_failed_after_delivery")[:180], now, int(current["id"])),
        )
    return get_job_by_worker_id(conn, worker_job_id)


def claim_charge(conn, *, worker_job_id: Any) -> bool:
    """Atomically grant one post-delivery charge attempt."""

    ensure_schema(conn)
    cursor = conn.execute(
        """UPDATE video_edit_jobs
           SET charge_state='charging',updated_at=?
           WHERE local_worker_job_id=?
             AND status='delivered'
             AND receipt_state='created'
             AND charge_state='not_charged'""",
        (_now(), int(worker_job_id or 0)),
    )
    return int(cursor.rowcount or 0) == 1
