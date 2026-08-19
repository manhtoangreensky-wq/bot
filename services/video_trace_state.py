"""Video Execution Trace & Three-ID Contract Service.

Provides immutable REQUEST_ID / TRACE_ID generation, event trace recording,
persistent SQLite request-to-job mapping, and truthful 3-tier identifier separation
(REQUEST_ID != JOB_ID != PROVIDER_TASK_ID).
"""

from __future__ import annotations

import datetime
import hashlib
import html
import json
import os
import secrets
import sqlite3
import time
from typing import Any, Mapping


STAGE_REQUEST_RECEIVED = "REQUEST_RECEIVED"
STAGE_PRECHECK_STARTED = "PRECHECK_STARTED"
STAGE_PRECHECK_RESULT = "PRECHECK_RESULT"
STAGE_ROUTE_EVALUATED = "ROUTE_EVALUATED"
STAGE_ADMISSION_BLOCKED = "ADMISSION_BLOCKED"
STAGE_JOB_CREATED = "JOB_CREATED"
STAGE_SUBMIT_STARTED = "SUBMIT_STARTED"
STAGE_SUBMIT_ACCEPTED = "SUBMIT_ACCEPTED"
STAGE_POLL_RESULT = "POLL_RESULT"
STAGE_ARTIFACT_VALIDATION = "ARTIFACT_VALIDATION"
STAGE_DELIVERING = "DELIVERING"
STAGE_DELIVERED = "DELIVERED"
STAGE_FAILED_NO_CHARGE = "FAILED_NO_CHARGE"

STAGE_LABELS = {
    STAGE_REQUEST_RECEIVED: "Đã nhận yêu cầu",
    STAGE_PRECHECK_STARTED: "Đang kiểm tra cấu hình",
    STAGE_PRECHECK_RESULT: "Đã kiểm tra cấu hình",
    STAGE_ROUTE_EVALUATED: "Đã phân bổ luồng xử lý",
    STAGE_ADMISSION_BLOCKED: "Tạm dừng tại bước kiểm tra",
    STAGE_JOB_CREATED: "Đã tạo tác vụ nội bộ",
    STAGE_SUBMIT_STARTED: "Đang gửi sang kênh dựng",
    STAGE_SUBMIT_ACCEPTED: "Kênh dựng đã nhận tác vụ",
    STAGE_POLL_RESULT: "Đang theo dõi tiến độ",
    STAGE_ARTIFACT_VALIDATION: "Đang kiểm tra file video",
    STAGE_DELIVERING: "Đang gửi kết quả",
    STAGE_DELIVERED: "Đã gửi video hoàn chỉnh",
    STAGE_FAILED_NO_CHARGE: "Chưa hoàn tất (chưa trừ Xu)",
}


def get_db_connection(conn=None):
    if conn is not None:
        return conn, False
    db_path = os.getenv("DATABASE_PATH", "toandaas_system.db")
    connection = sqlite3.connect(db_path, timeout=30.0)
    connection.row_factory = sqlite3.Row
    return connection, True


def ensure_video_trace_schema(conn=None) -> None:
    c, should_close = get_db_connection(conn)
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS video_request_traces (
                request_id TEXT PRIMARY KEY,
                job_id INTEGER NULL,
                provider_task_id TEXT NULL,
                owner_user_id INTEGER NOT NULL DEFAULT 0,
                owner_chat_id INTEGER NOT NULL DEFAULT 0,
                product_type TEXT NOT NULL DEFAULT 'video_ai_real',
                current_stage TEXT NOT NULL DEFAULT 'REQUEST_RECEIVED',
                internal_blocker_code TEXT NULL,
                trace_payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_video_request_traces_job_id ON video_request_traces(job_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_video_request_traces_user_id ON video_request_traces(owner_user_id);")
        c.commit()
    finally:
        if should_close:
            c.close()


def generate_video_request_id(prefix: str = "VID") -> str:
    """Generate an immutable, customer-safe, truthful REQUEST_ID."""
    date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
    random_hex = secrets.token_hex(3).upper()
    return f"{prefix}-{date_str}-{random_hex}"


def get_or_create_video_request_id(session: dict | None = None, user_id: int = 0) -> str:
    """Return existing REQUEST_ID from session/draft or generate a fresh one."""
    session = dict(session or {})
    draft = dict(session.get("draft") or {})
    existing = str(
        draft.get("request_id")
        or draft.get("trace_id")
        or (draft.get("video_trace") or {}).get("request_id")
        or ""
    ).strip()
    if existing and existing != "Không có" and existing != "-":
        return existing
    return generate_video_request_id()


def persist_video_request_trace(trace: dict, conn=None) -> bool:
    """Persist the canonical request trace to SQLite."""
    if not isinstance(trace, dict):
        return False
    request_id = str(trace.get("request_id") or "").strip()
    if not request_id or request_id in {"Không có", "-"}:
        return False
    ensure_video_trace_schema(conn)
    c, should_close = get_db_connection(conn)
    try:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        created_at = str(trace.get("created_at") or now_iso)
        updated_at = str(trace.get("updated_at") or now_iso)
        job_id = trace.get("job_id")
        if job_id is not None:
            try:
                job_id = int(job_id) if int(job_id) > 0 else None
            except (ValueError, TypeError):
                job_id = None
        provider_task_id = str(trace.get("provider_task_id") or "").strip() or None
        owner_user_id = int(trace.get("owner_user_id") or 0)
        owner_chat_id = int(trace.get("owner_chat_id") or 0)
        product_type = str(trace.get("product_type") or "video_ai_real")
        current_stage = str(trace.get("current_stage") or "REQUEST_RECEIVED")
        internal_blocker_code = str(trace.get("internal_blocker_code") or "").strip() or None
        trace_json = json.dumps(trace, ensure_ascii=False)

        c.execute("""
            INSERT INTO video_request_traces (
                request_id, job_id, provider_task_id, owner_user_id, owner_chat_id,
                product_type, current_stage, internal_blocker_code, trace_payload_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(request_id) DO UPDATE SET
                job_id=COALESCE(excluded.job_id, video_request_traces.job_id),
                provider_task_id=COALESCE(excluded.provider_task_id, video_request_traces.provider_task_id),
                owner_user_id=CASE WHEN excluded.owner_user_id > 0 THEN excluded.owner_user_id ELSE video_request_traces.owner_user_id END,
                owner_chat_id=CASE WHEN excluded.owner_chat_id > 0 THEN excluded.owner_chat_id ELSE video_request_traces.owner_chat_id END,
                product_type=excluded.product_type,
                current_stage=excluded.current_stage,
                internal_blocker_code=COALESCE(excluded.internal_blocker_code, video_request_traces.internal_blocker_code),
                trace_payload_json=excluded.trace_payload_json,
                updated_at=excluded.updated_at
        """, (
            request_id, job_id, provider_task_id, owner_user_id, owner_chat_id,
            product_type, current_stage, internal_blocker_code, trace_json,
            created_at, updated_at
        ))
        c.commit()
        return True
    except Exception:
        return False
    finally:
        if should_close:
            c.close()


def lookup_video_request_trace(identifier: str | int, conn=None) -> dict | None:
    """Look up canonical trace by REQUEST_ID, JOB_ID, or PROVIDER_TASK_ID."""
    raw = str(identifier or "").strip()
    if not raw:
        return None
    ensure_video_trace_schema(conn)
    c, should_close = get_db_connection(conn)
    try:
        c.row_factory = sqlite3.Row
        # 1. Exact match on request_id
        cursor = c.execute("SELECT * FROM video_request_traces WHERE request_id = ? LIMIT 1", (raw,))
        row = cursor.fetchone()
        if row:
            data = dict(row)
            try:
                payload = json.loads(data.get("trace_payload_json") or "{}")
            except Exception:
                payload = {}
            payload.setdefault("request_id", data["request_id"])
            payload.setdefault("job_id", data["job_id"])
            payload.setdefault("provider_task_id", data["provider_task_id"])
            payload.setdefault("owner_user_id", data["owner_user_id"])
            payload.setdefault("owner_chat_id", data["owner_chat_id"])
            payload.setdefault("current_stage", data["current_stage"])
            payload.setdefault("internal_blocker_code", data["internal_blocker_code"])
            payload.setdefault("created_at", data["created_at"])
            payload.setdefault("updated_at", data["updated_at"])
            return payload

        # 2. Check by job_id
        try:
            jid = int(raw)
        except ValueError:
            jid = 0
        if jid > 0:
            cursor = c.execute("SELECT * FROM video_request_traces WHERE job_id = ? LIMIT 1", (jid,))
            row = cursor.fetchone()
            if row:
                data = dict(row)
                try:
                    payload = json.loads(data.get("trace_payload_json") or "{}")
                except Exception:
                    payload = {}
                payload.setdefault("request_id", data["request_id"])
                payload.setdefault("job_id", data["job_id"])
                payload.setdefault("provider_task_id", data["provider_task_id"])
                return payload

            # Check video_jobs table if trace not yet written
            try:
                cursor2 = c.execute("SELECT * FROM video_jobs WHERE id = ? LIMIT 1", (jid,))
                job_row = cursor2.fetchone()
                if job_row:
                    job_data = dict(job_row)
                    try:
                        res_json = json.loads(job_data.get("result_json") or "{}")
                    except Exception:
                        res_json = {}
                    req_id = str(res_json.get("request_id") or f"VID-JOB-{jid}")
                    synth_trace = {
                        "request_id": req_id,
                        "job_id": jid,
                        "provider_task_id": str(res_json.get("task_id") or res_json.get("canonical_task_id") or "").strip() or None,
                        "current_stage": str(job_data.get("status") or "JOB_CREATED"),
                        "internal_blocker_code": None,
                        "created_at": str(job_data.get("created_at") or ""),
                        "updated_at": str(job_data.get("updated_at") or ""),
                        "recovered_from_job_table": True,
                    }
                    return synth_trace
            except Exception:
                pass

        # 3. Check by provider_task_id
        cursor = c.execute("SELECT * FROM video_request_traces WHERE provider_task_id = ? LIMIT 1", (raw,))
        row = cursor.fetchone()
        if row:
            data = dict(row)
            try:
                payload = json.loads(data.get("trace_payload_json") or "{}")
            except Exception:
                payload = {}
            return payload

        return None
    except Exception:
        return None
    finally:
        if should_close:
            c.close()


def record_video_trace_event(
    session: dict | None,
    stage: str,
    *,
    payload: dict | None = None,
    user_id: int = 0,
    chat_id: int = 0,
    job_id: int | None = None,
    provider_task_id: str | None = None,
    blocker_code: str = "",
    product_type: str = "video_ai_real",
    conn=None,
) -> dict:
    """Record an ordered execution trace event and persist it to SQLite."""
    session = dict(session or {})
    draft = dict(session.get("draft") or {})
    trace = dict(draft.get("video_trace") or {})

    request_id = str(
        trace.get("request_id")
        or draft.get("request_id")
        or draft.get("trace_id")
        or ""
    ).strip()
    if not request_id or request_id in {"Không có", "-"}:
        request_id = generate_video_request_id()

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    events = list(trace.get("events") or [])

    event_entry = {
        "stage": stage,
        "timestamp": now_iso,
        "payload": dict(payload or {}),
    }
    if blocker_code:
        event_entry["blocker_code"] = blocker_code
    events.append(event_entry)

    current_job_id = job_id if job_id is not None else trace.get("job_id")
    current_provider_task_id = provider_task_id if provider_task_id is not None else trace.get("provider_task_id")

    trace.update({
        "request_id": request_id,
        "owner_user_id": int(user_id or trace.get("owner_user_id") or 0),
        "owner_chat_id": int(chat_id or trace.get("owner_chat_id") or 0),
        "product_type": str(product_type or trace.get("product_type") or "video_ai_real"),
        "current_stage": stage,
        "current_stage_label": STAGE_LABELS.get(stage, stage),
        "created_at": str(trace.get("created_at") or now_iso),
        "updated_at": now_iso,
        "job_id": current_job_id if current_job_id and int(current_job_id) > 0 else None,
        "provider_task_id": str(current_provider_task_id or "").strip() or None,
        "internal_blocker_code": str(blocker_code or trace.get("internal_blocker_code") or "").strip() or None,
        "events": events,
    })

    draft["video_trace"] = trace
    draft["request_id"] = request_id
    draft["public_processing_code"] = request_id
    session["draft"] = draft

    # Write to SQLite
    persist_video_request_trace(trace, conn=conn)
    return session


def build_canonical_video_trace_report(identifier: str | int, conn=None) -> dict:
    """Build standardized diagnostic report dictionary for /video_trace."""
    trace = lookup_video_request_trace(identifier, conn=conn)
    if not trace:
        raw_str = str(identifier or "").strip()
        is_req = raw_str.startswith("VID-")
        return {
            "REQUEST_ID": raw_str if is_req else "None",
            "JOB_ID": "None" if is_req else raw_str,
            "PROVIDER_TASK_ID": "None",
            "REQUEST_FOUND": "YES" if is_req else "NO",
            "JOB_FOUND": "NO",
            "PROVIDER_TASK_FOUND": "NO",
            "CURRENT_STAGE": "NO_JOB_CREATED" if is_req else "NOT_FOUND",
            "INTERNAL_BLOCKER": "request_stopped_before_job_creation" if is_req else "not_found",
            "PUBLIC_STATUS": "Chưa tạo tác vụ" if is_req else "Không tìm thấy",
            "ROUTE": "video_ai_real",
            "EXECUTION_MODE": "multiscene",
            "PROVIDER": "None",
            "MODEL": "None",
            "CAPABILITY": "None",
            "SCENES_TOTAL": 0,
            "SCENE_TASKS_CREATED": 0,
            "SCENE_TASKS_SUBMITTED": 0,
            "SUBMIT_COUNT": 0,
            "POLL_COUNT": 0,
            "ARTIFACT": "None",
            "DELIVERY_RECEIPT": "None",
            "CHARGE_STATE": "NO_CHARGE",
            "STATUS_SOURCE": "canonical_db_lookup_empty",
        }

    req_id = trace.get("request_id") or "None"
    job_id = trace.get("job_id")
    job_id_str = str(job_id) if job_id and int(job_id) > 0 else "None"
    prov_id = trace.get("provider_task_id") or "None"
    stage = trace.get("current_stage") or "REQUEST_RECEIVED"
    blocker = trace.get("internal_blocker_code") or "None"

    return {
        "REQUEST_ID": req_id,
        "JOB_ID": job_id_str,
        "PROVIDER_TASK_ID": prov_id,
        "REQUEST_FOUND": "YES",
        "JOB_FOUND": "YES" if job_id_str != "None" else "NO",
        "PROVIDER_TASK_FOUND": "YES" if prov_id != "None" else "NO",
        "CURRENT_STAGE": stage,
        "INTERNAL_BLOCKER": blocker,
        "PUBLIC_STATUS": STAGE_LABELS.get(stage, stage),
        "ROUTE": trace.get("product_type") or "video_ai_real",
        "EXECUTION_MODE": "multiscene",
        "PROVIDER": trace.get("provider") or "None",
        "MODEL": trace.get("model") or "None",
        "CAPABILITY": trace.get("capability") or "None",
        "SCENES_TOTAL": trace.get("scene_count") or 0,
        "SCENE_TASKS_CREATED": trace.get("scene_tasks_created") or 0,
        "SCENE_TASKS_SUBMITTED": trace.get("scene_tasks_submitted") or 0,
        "SUBMIT_COUNT": 1 if job_id_str != "None" else 0,
        "POLL_COUNT": trace.get("poll_count") or 0,
        "ARTIFACT": trace.get("final_video_path") or "None",
        "DELIVERY_RECEIPT": trace.get("delivery_receipt") or "None",
        "CHARGE_STATE": trace.get("charge_state") or "NO_CHARGE",
        "STATUS_SOURCE": "canonical_db_video_request_traces",
    }
