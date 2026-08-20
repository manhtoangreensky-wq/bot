from __future__ import annotations

import datetime
import html
import json
import logging
import os
import secrets
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
"""Video execution trace state model, SQLite persistence, and truthful status report.

Three-Tier ID separation:
- REQUEST_ID: Unique customer-facing tracking token (e.g. VID-20260819-A1B2C3).
- JOB_ID: Internal asynchronous rendering queue task ID (e.g. 101).
- PROVIDER_TASK_ID: Upstream external AI provider reference (e.g. task_xyz123).
"""

STAGE_REQUEST_RECEIVED = "REQUEST_RECEIVED"
STAGE_PRECHECK_STARTED = "PRECHECK_STARTED"
STAGE_PRECHECK_PASSED = "PRECHECK_PASSED"
STAGE_PRECHECK_RESULT = "PRECHECK_PASSED"
STAGE_ROUTE_EVALUATED = "ROUTE_EVALUATED"
STAGE_PREFLIGHT_BLOCKED = "PREFLIGHT_BLOCKED"
STAGE_ADMISSION_BLOCKED = "ADMISSION_BLOCKED"
STAGE_JOB_CREATED = "JOB_CREATED"
STAGE_JOB_CREATE_FAILED = "JOB_CREATE_FAILED"
STAGE_READY_TO_SUBMIT = "READY_TO_SUBMIT"
STAGE_SUBMIT_STARTED = "SUBMIT_STARTED"
STAGE_SUBMIT_ACCEPTED = "SUBMIT_ACCEPTED"
STAGE_PROVIDER_SUBMITTED = "SUBMIT_ACCEPTED"
STAGE_POLL_RESULT = "POLL_RESULT"
STAGE_ARTIFACT_VALIDATION = "ARTIFACT_VALIDATION"
STAGE_DELIVERING = "DELIVERING"
STAGE_DELIVERED = "DELIVERED"
STAGE_FAILED_NO_CHARGE = "FAILED_NO_CHARGE"

STAGE_LABELS = {
    STAGE_REQUEST_RECEIVED: "Đã nhận yêu cầu",
    STAGE_PRECHECK_STARTED: "Đang kiểm tra hệ thống",
    STAGE_PRECHECK_PASSED: "Hệ thống sẵn sàng",
    STAGE_PREFLIGHT_BLOCKED: "Tạm dừng tại bước kiểm tra",
    STAGE_ADMISSION_BLOCKED: "Tạm dừng tại bước kiểm tra",
    STAGE_JOB_CREATED: "Đã tạo tác vụ nội bộ",
    STAGE_JOB_CREATE_FAILED: "Không thể tạo tác vụ nội bộ",
    STAGE_READY_TO_SUBMIT: "Sẵn sàng gửi kênh dựng",
    STAGE_SUBMIT_STARTED: "Đang gửi sang kênh dựng",
    STAGE_SUBMIT_ACCEPTED: "Kênh dựng đã nhận tác vụ",
    STAGE_POLL_RESULT: "Đang theo dõi tiến độ",
    STAGE_ARTIFACT_VALIDATION: "Đang kiểm tra file video",
    STAGE_DELIVERING: "Đang gửi kết quả",
    STAGE_DELIVERED: "Đã gửi video hoàn chỉnh",
    STAGE_FAILED_NO_CHARGE: "Chưa hoàn tất (chưa trừ Xu)",
}


def get_canonical_db_path() -> str:
    """Return the one canonical database path used across all processes."""
    return (
        os.getenv("DB_PATH")
        or os.getenv("DB_FILE")
        or os.getenv("DATABASE_PATH")
        or os.getenv("SQLITE_DB_PATH")
        or "toandaas_system.db"
    ).strip()


def get_db_connection(conn=None):
    if conn is not None:
        return conn, False
    db_path = get_canonical_db_path()
    parent_dir = os.path.dirname(os.path.abspath(db_path))
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=30.0)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=30000")
    connection.row_factory = sqlite3.Row
    return connection, True


def ensure_video_trace_schema(conn=None) -> None:
    c, should_close = get_db_connection(conn)
    caller_transaction_active = bool(c.in_transaction)
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS video_request_traces (
                request_id TEXT PRIMARY KEY,
                job_id INTEGER NULL,
                project_id INTEGER NULL,
                confirm_attempt_key TEXT NULL,
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
        columns = {str(row[1]) for row in c.execute("PRAGMA table_info(video_request_traces)").fetchall()}
        if "project_id" not in columns:
            c.execute("ALTER TABLE video_request_traces ADD COLUMN project_id INTEGER NULL")
        if "confirm_attempt_key" not in columns:
            c.execute("ALTER TABLE video_request_traces ADD COLUMN confirm_attempt_key TEXT NULL")
        c.execute("CREATE INDEX IF NOT EXISTS idx_video_request_traces_job_id ON video_request_traces(job_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_video_request_traces_project_id ON video_request_traces(project_id);")
        c.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_video_request_traces_confirm_attempt
               ON video_request_traces(confirm_attempt_key)
               WHERE confirm_attempt_key IS NOT NULL AND confirm_attempt_key != ''"""
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_video_request_traces_user_id ON video_request_traces(owner_user_id);")
        if not caller_transaction_active:
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


def persist_video_request_trace(trace: dict, conn=None, *, commit: bool = True) -> bool:
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
        project_id = trace.get("project_id")
        if project_id is not None:
            try:
                project_id = int(project_id) if int(project_id) > 0 else None
            except (ValueError, TypeError):
                project_id = None
        confirm_attempt_key = str(trace.get("confirm_attempt_key") or "").strip() or None
        provider_task_id = str(trace.get("provider_task_id") or "").strip() or None
        owner_user_id = int(trace.get("owner_user_id") or 0)
        owner_chat_id = int(trace.get("owner_chat_id") or 0)
        product_type = str(trace.get("product_type") or "video_ai_real")
        current_stage = str(trace.get("current_stage") or "REQUEST_RECEIVED")
        internal_blocker_code = str(trace.get("internal_blocker_code") or "").strip() or None
        trace_json = json.dumps(trace, ensure_ascii=False)

        c.execute("""
            INSERT INTO video_request_traces (
                request_id, job_id, project_id, confirm_attempt_key, provider_task_id, owner_user_id, owner_chat_id,
                product_type, current_stage, internal_blocker_code, trace_payload_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(request_id) DO UPDATE SET
                job_id=COALESCE(excluded.job_id, video_request_traces.job_id),
                project_id=COALESCE(excluded.project_id, video_request_traces.project_id),
                confirm_attempt_key=COALESCE(excluded.confirm_attempt_key, video_request_traces.confirm_attempt_key),
                provider_task_id=COALESCE(excluded.provider_task_id, video_request_traces.provider_task_id),
                owner_user_id=CASE WHEN excluded.owner_user_id > 0 THEN excluded.owner_user_id ELSE video_request_traces.owner_user_id END,
                owner_chat_id=CASE WHEN excluded.owner_chat_id > 0 THEN excluded.owner_chat_id ELSE video_request_traces.owner_chat_id END,
                product_type=excluded.product_type,
                current_stage=excluded.current_stage,
                internal_blocker_code=excluded.internal_blocker_code,
                trace_payload_json=excluded.trace_payload_json,
                updated_at=excluded.updated_at
        """, (
            request_id, job_id, project_id, confirm_attempt_key, provider_task_id, owner_user_id, owner_chat_id,
            product_type, current_stage, internal_blocker_code, trace_json,
            created_at, updated_at
        ))
        if commit:
            c.commit()
        # Readback verification
        cursor = c.execute("SELECT request_id FROM video_request_traces WHERE request_id = ? LIMIT 1", (request_id,))
        row = cursor.fetchone()
        return bool(row and row[0] == request_id)
    except Exception:
        return False
    finally:
        if should_close:
            c.close()


def _trace_payload_from_row(row: sqlite3.Row | tuple) -> dict:
    data = dict(row)
    try:
        payload = json.loads(data.get("trace_payload_json") or "{}")
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload.update(
        {
            "request_id": data["request_id"],
            "job_id": data["job_id"],
            "project_id": data.get("project_id"),
            "confirm_attempt_key": data.get("confirm_attempt_key"),
            "provider_task_id": data["provider_task_id"],
            "owner_user_id": data["owner_user_id"],
            "owner_chat_id": data["owner_chat_id"],
            "product_type": data["product_type"],
            "current_stage": data["current_stage"],
            "internal_blocker_code": data["internal_blocker_code"],
            "created_at": data["created_at"],
            "updated_at": data["updated_at"],
        }
    )
    return payload


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
            return _trace_payload_from_row(row)

        # 2. Check by job_id
        try:
            jid = int(raw)
        except ValueError:
            jid = 0
        if jid > 0:
            cursor = c.execute("SELECT * FROM video_request_traces WHERE job_id = ? ORDER BY updated_at DESC LIMIT 1", (jid,))
            row = cursor.fetchone()
            if row:
                return _trace_payload_from_row(row)

        # 3. Check by provider_task_id
        cursor = c.execute("SELECT * FROM video_request_traces WHERE provider_task_id = ? ORDER BY updated_at DESC LIMIT 1", (raw,))
        row = cursor.fetchone()
        if row:
            return _trace_payload_from_row(row)

        return None
    finally:
        if should_close:
            c.close()


def lookup_video_request_trace_by_job_id(job_id: int, conn=None) -> dict | None:
    return lookup_video_request_trace(job_id, conn=conn)


def lookup_video_request_trace_by_attempt_key(confirm_attempt_key: str, conn=None) -> dict | None:
    key = str(confirm_attempt_key or "").strip()
    if not key:
        return None
    ensure_video_trace_schema(conn)
    c, should_close = get_db_connection(conn)
    try:
        row = c.execute(
            "SELECT request_id FROM video_request_traces WHERE confirm_attempt_key=? LIMIT 1",
            (key,),
        ).fetchone()
        return lookup_video_request_trace(str(row[0]), conn=c) if row else None
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

    payload_data = dict(payload or {})
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
        "project_id": payload_data.get("project_id") or trace.get("project_id") or draft.get("b14_project_id"),
        "confirm_attempt_key": payload_data.get("confirm_attempt_key") or trace.get("confirm_attempt_key"),
        "provider_task_id": str(current_provider_task_id or "").strip() or None,
        "internal_blocker_code": str(blocker_code or trace.get("internal_blocker_code") or "").strip() or None,
        "preflight_result": payload_data.get("preflight_result") or trace.get("preflight_result"),
        "admission_result": payload_data.get("admission_result") or trace.get("admission_result"),
        "required_capability": payload_data.get("required_capability") or trace.get("required_capability") or "text_to_video_or_scene_video",
        "route_candidates": payload_data.get("route_candidates") or trace.get("route_candidates") or ["shopaikey_video", "key4u_video", "toanaas_video", "veo", "kling", "generic_http"],
        "eligible_route_count": payload_data.get("eligible_route_count") if payload_data.get("eligible_route_count") is not None else trace.get("eligible_route_count", 0),
        "worker_required": payload_data.get("worker_required") if payload_data.get("worker_required") is not None else trace.get("worker_required", False),
        "worker_ready": payload_data.get("worker_ready") if payload_data.get("worker_ready") is not None else trace.get("worker_ready", True),
        "provider_configured": payload_data.get("provider_configured") if payload_data.get("provider_configured") is not None else trace.get("provider_configured", False),
        "provider_ready": payload_data.get("provider_ready") if payload_data.get("provider_ready") is not None else trace.get("provider_ready", False),
        "events": events,
    })

    draft["video_trace"] = trace
    draft["request_id"] = request_id
    draft["public_processing_code"] = request_id
    session["draft"] = draft

    # Write to SQLite
    persist_video_request_trace(trace, conn=conn)
    return session


def resolve_video_status_identity(
    session: dict | None,
    result: dict | None = None,
    *,
    user_id: int = 0,
    conn=None,
) -> dict[str, Any]:
    """Resolve truthful request/job identity for a read-only status render."""

    from services import video_project_queue

    session = dict(session or {})
    result = dict(result or {})
    draft = dict(session.get("draft") or {})
    cached_trace = dict(draft.get("video_trace") or {})
    result_job = dict(result.get("job") or {})
    cached_job = dict(draft.get("b14_queue_job") or {})
    request_id = str(
        draft.get("request_id")
        or cached_trace.get("request_id")
        or draft.get("public_processing_code")
        or ""
    ).strip()
    cached_job_id = int(
        result_job.get("id")
        or cached_job.get("id")
        or draft.get("b14_queue_job_id")
        or 0
    )

    connection, should_close = get_db_connection(conn)
    try:
        trace = None
        if request_id and request_id not in {"Không có", "-"}:
            trace = lookup_video_request_trace(request_id, conn=connection)
        if trace is None and cached_job_id > 0:
            trace = lookup_video_request_trace_by_job_id(cached_job_id, conn=connection)
        if trace and int(trace.get("owner_user_id") or 0) not in {0, int(user_id or 0)}:
            trace = None
        trace = dict(trace or cached_trace or {})
        request_id = str(trace.get("request_id") or request_id or "").strip()
        job_id = int(trace.get("job_id") or cached_job_id or 0)

        durable_job = video_project_queue.get_video_render_job(connection, job_id) if job_id > 0 else {}
        if durable_job and int(durable_job.get("user_id") or 0) != int(user_id or 0):
            durable_job = {}
            job_id = 0
        job = dict(durable_job or {})
        if not durable_job:
            if cached_job and int(cached_job.get("id") or 0) == job_id:
                job.update(cached_job)
            if result_job and int(result_job.get("id") or 0) == job_id:
                job.update(result_job)
        return {
            "request_id": request_id if request_id not in {"Không có", "-"} else "",
            "job_id": job_id,
            "trace": trace,
            "job": job,
            "durable_trace_found": bool(trace and trace.get("request_id")),
            "durable_job_found": bool(durable_job),
        }
    finally:
        if should_close:
            connection.close()


def resolve_video_request_truth(identifier: str | int, conn=None) -> dict[str, Any]:
    """Single canonical resolver for request / job diagnostics.

    Guarantees no false positive REQUEST_FOUND and unifies durable vs session truth.
    """
    raw = str(identifier or "").strip()
    c, should_close = get_db_connection(conn)
    try:
        ensure_video_trace_schema(c)
        trace = lookup_video_request_trace(raw, conn=c)
        job_record = None
        job_id = None
        if trace and trace.get("job_id"):
            job_id = int(trace.get("job_id"))
        elif raw.isdigit() and int(raw) > 0:
            job_id = int(raw)
            if not trace:
                trace = lookup_video_request_trace_by_job_id(job_id, conn=c)

        # If job_id exists, look up video_jobs
        if job_id and job_id > 0:
            try:
                row = c.execute("SELECT * FROM video_jobs WHERE id=?", (job_id,)).fetchone()
                if row:
                    job_record = dict(row)
            except Exception:
                job_record = None

        durable_found = trace is not None
        req_id = trace.get("request_id") if trace else (raw if raw.startswith("VID-") else None)
        prov_task_id = trace.get("provider_task_id") if trace else (job_record.get("provider_task_id") if job_record else None)

        # Check current runtime provider status
        try:
            from services import video_provider_router
            curr_status = video_provider_router.provider_status_payload()
            curr_ready = [p["provider"] for p in curr_status.get("providers", []) if p.get("configured") and p.get("credit_ok", True)]
            curr_prov_configured = bool(curr_ready)
            curr_prov_ready = bool(curr_ready)
            curr_eligible_count = len(curr_ready)
            curr_selected_route = curr_ready[0] if curr_ready else "None"
        except Exception:
            curr_prov_configured = False
            curr_prov_ready = False
            curr_eligible_count = 0
            curr_selected_route = "None"

        if not durable_found:
            return {
                "identifier_type": "request_id" if raw.startswith("VID-") else ("job_id" if raw.isdigit() else "unknown"),
                "request_id": req_id or "None",
                "request_found": "NO",
                "request_source": "none",
                "durable_request_found": "NO",
                "job_id": str(job_id) if job_id else "None",
                "job_found": "YES" if job_record else "NO",
                "provider_task_id": str(prov_task_id or "None"),
                "provider_task_found": "YES" if prov_task_id else "NO",
                "current_stage": "NOT_FOUND",
                "preflight_result": "NOT_FOUND",
                "admission_result": "NOT_FOUND",
                "exact_blocker_code": "not_found",
                "exact_blocker_detail": "Không tìm thấy yêu cầu trong cơ sở dữ liệu",
                "why_no_job": "Yêu cầu không tìm thấy trong dữ liệu lưu trữ bền vững (durable DB)",
                "provider_configured_at_request": "UNKNOWN",
                "provider_ready_at_request": "UNKNOWN",
                "current_provider_configured": "YES" if curr_prov_configured else "NO",
                "current_provider_ready": "YES" if curr_prov_ready else "NO",
                "current_eligible_route_count": curr_eligible_count,
                "current_selected_route": curr_selected_route,
                "worker_required": "NO",
                "worker_ready": "YES",
                "trace_record": None,
                "job_record": job_record,
                "status_source": "canonical_db_not_found",
            }

        # Durable record found
        stage = trace.get("current_stage") or "REQUEST_RECEIVED"
        blocker = trace.get("internal_blocker_code") or "None"
        prov_cfg_at_req = "YES" if trace.get("provider_configured") else "NO"
        prov_ready_at_req = "YES" if trace.get("provider_ready") else "NO"
        eligible_at_req = trace.get("eligible_route_count", 0)
        selected_at_req = trace.get("selected_route") or "None"

        return {
            "identifier_type": "request_id" if raw.startswith("VID-") else "job_id",
            "request_id": req_id or "None",
            "request_found": "YES",
            "request_source": "canonical_db_video_request_traces",
            "durable_request_found": "YES",
            "job_id": str(job_id) if job_id else "None",
            "job_found": "YES" if job_record else "NO",
            "provider_task_id": str(prov_task_id or "None"),
            "provider_task_found": "YES" if prov_task_id and prov_task_id != "None" else "NO",
            "current_stage": stage,
            "preflight_result": trace.get("preflight_result") or ("PASS" if job_id else "BLOCKED"),
            "admission_result": trace.get("admission_result") or ("PASS" if job_id else "BLOCKED"),
            "exact_blocker_code": blocker,
            "exact_blocker_detail": trace.get("blocker_detail_safe") or blocker,
            "why_no_job": (
                f"Đã tạo tác vụ nội bộ (#{job_id})"
                if job_record
                else f"Trace tham chiếu tác vụ #{job_id} nhưng không còn tìm thấy row video_jobs"
                if job_id
                else f"Yêu cầu dừng tại bước kiểm tra ({blocker}); Bot chưa trừ Xu."
            ),
            "provider_configured_at_request": prov_cfg_at_req,
            "provider_ready_at_request": prov_ready_at_req,
            "eligible_route_count_at_request": eligible_at_req,
            "selected_route_at_request": selected_at_req,
            "current_provider_configured": "YES" if curr_prov_configured else "NO",
            "current_provider_ready": "YES" if curr_prov_ready else "NO",
            "current_eligible_route_count": curr_eligible_count,
            "current_selected_route": curr_selected_route,
            "product_type": trace.get("product_type") or "video_ai_real",
            "package": trace.get("package") or "8s_per_scene",
            "worker_required": "YES" if trace.get("worker_required") else "NO",
            "worker_ready": "YES" if trace.get("worker_ready", True) else "NO",
            "job_ever_created": "YES" if job_id else "NO",
            "provider_ever_submitted": "YES" if prov_task_id and prov_task_id != "None" else "NO",
            "trace_record": trace,
            "job_record": job_record,
            "status_source": "canonical_db_video_request_traces",
        }
    finally:
        if should_close:
            c.close()


def build_canonical_video_trace_report(identifier: str | int, conn=None) -> dict:
    """Build standardized diagnostic report dictionary for /video_trace."""
    truth = resolve_video_request_truth(identifier, conn=conn)
    candidates = ["shopaikey_video", "key4u_video", "toanaas_video", "veo", "kling", "generic_http"]
    candidate_str = ", ".join(candidates)
    trace = truth.get("trace_record") or {}

    return {
        "REQUEST_ID": truth["request_id"],
        "JOB_ID": truth["job_id"],
        "PROVIDER_TASK_ID": truth["provider_task_id"],
        "REQUEST_FOUND": truth["request_found"],
        "DURABLE_REQUEST_FOUND": truth["durable_request_found"],
        "JOB_FOUND": truth["job_found"],
        "PROVIDER_TASK_FOUND": truth["provider_task_found"],
        "CURRENT_STAGE": truth["current_stage"],
        "PREFLIGHT_RESULT": truth["preflight_result"],
        "ADMISSION_RESULT": truth["admission_result"],
        "EXACT_BLOCKER_CODE": truth["exact_blocker_code"],
        "EXACT_BLOCKER_DETAIL": truth["exact_blocker_detail"],
        "INTERNAL_BLOCKER": truth["exact_blocker_code"],
        "PUBLIC_STATUS": STAGE_LABELS.get(truth["current_stage"], truth["current_stage"]),
        "PRODUCT_TYPE": truth.get("product_type", "video_ai_real"),
        "PACKAGE": truth.get("package", "8s_per_scene"),
        "REQUIRED_CAPABILITY": trace.get("required_capability", "text_to_video_or_scene_video"),
        "ROUTE": truth.get("product_type", "video_ai_real"),
        "ROUTE_CANDIDATES": candidate_str,
        "ELIGIBLE_ROUTE_COUNT_AT_REQUEST": truth.get("eligible_route_count_at_request", 0),
        "SELECTED_ROUTE_AT_REQUEST": truth.get("selected_route_at_request", "None"),
        "PROVIDER_CONFIGURED_AT_REQUEST": truth.get("provider_configured_at_request", "NO"),
        "PROVIDER_READY_AT_REQUEST": truth.get("provider_ready_at_request", "NO"),
        "CURRENT_PROVIDER_CONFIGURED": truth["current_provider_configured"],
        "CURRENT_PROVIDER_READY": truth["current_provider_ready"],
        "CURRENT_ELIGIBLE_ROUTE_COUNT": truth["current_eligible_route_count"],
        "CURRENT_SELECTED_ROUTE": truth["current_selected_route"],
        "EXECUTION_MODE": trace.get("execution_mode", "cloud"),
        "PROVIDER": truth["current_selected_route"],
        "MODEL": trace.get("model", "None"),
        "CAPABILITY": trace.get("capability", "text_to_video_or_scene_video"),
        "WORKER_REQUIRED": truth["worker_required"],
        "WORKER_READY": truth["worker_ready"],
        "JOB_EVER_CREATED": truth["job_ever_created"] if "job_ever_created" in truth else "NO",
        "PROVIDER_EVER_SUBMITTED": truth["provider_ever_submitted"] if "provider_ever_submitted" in truth else "NO",
        "SCENES_TOTAL": trace.get("scene_count", 0),
        "SCENE_TASKS_CREATED": trace.get("scene_tasks_created", 0),
        "SCENE_TASKS_SUBMITTED": trace.get("scene_tasks_submitted", 0),
        "SUBMIT_COUNT": int(trace.get("submit_count") or 0),
        "POLL_COUNT": trace.get("poll_count", 0),
        "CHARGE_COUNT": int(trace.get("charge_count") or 0),
        "ARTIFACT": trace.get("final_video_path", "None"),
        "DELIVERY_RECEIPT": trace.get("delivery_receipt", "None"),
        "CHARGE_STATE": trace.get("charge_state", "NO_CHARGE"),
        "STATUS_SOURCE": truth["status_source"],
        "WHY_NO_JOB": truth["why_no_job"],
    }


def begin_video_confirm_attempt(session: dict | None, *, user_id: int = 0, chat_id: int = 0, payload: dict | None = None, conn=None) -> dict:
    """Canonical intake function: allocate REQUEST_ID, persist minimal request trace row with commit readback before any preflight/admission check."""
    session = dict(session or {})
    draft = dict(session.get("draft") or {})
    request_id = get_or_create_video_request_id(session, user_id=user_id)
    draft["request_id"] = request_id
    draft["public_processing_code"] = request_id
    session["draft"] = draft

    try:
        # Persist STAGE_REQUEST_RECEIVED event with commit & readback verification
        updated_session = record_video_trace_event(
            session,
            STAGE_REQUEST_RECEIVED,
            user_id=user_id,
            chat_id=chat_id,
            payload=payload or {},
            conn=conn,
        )

        # Readback verification
        trace = lookup_video_request_trace(request_id, conn=conn)
        if not trace:
            return {
                "ok": False,
                "request_id": request_id,
                "session": updated_session,
                "reason": "trace_persistence_failed",
                "durable_persisted": False,
            }
        return {
            "ok": True,
            "request_id": request_id,
            "session": updated_session,
            "reason": "",
            "durable_persisted": True,
        }
    except Exception as exc:
        logger.warning("begin_video_confirm_attempt failed: %s", exc)
        return {
            "ok": False,
            "request_id": request_id,
            "session": session,
            "reason": "trace_persistence_failed",
            "durable_persisted": False,
        }


def _append_trace_event(trace: dict, stage: str, payload: dict | None = None, blocker_code: str = "") -> dict:
    updated = dict(trace or {})
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    events = list(updated.get("events") or [])
    event = {"stage": str(stage), "timestamp": now_iso, "payload": dict(payload or {})}
    if blocker_code:
        event["blocker_code"] = str(blocker_code)
    events.append(event)
    updated.update(
        {
            "current_stage": str(stage),
            "current_stage_label": STAGE_LABELS.get(str(stage), str(stage)),
            "created_at": str(updated.get("created_at") or now_iso),
            "updated_at": now_iso,
            "events": events,
        }
    )
    return updated


def _begin_sqlite_transaction(connection: sqlite3.Connection) -> str:
    if connection.in_transaction:
        savepoint = f"video_confirm_{secrets.token_hex(4)}"
        connection.execute(f"SAVEPOINT {savepoint}")
        return savepoint
    connection.execute("BEGIN IMMEDIATE")
    return ""


def _commit_sqlite_transaction(connection: sqlite3.Connection, savepoint: str) -> None:
    if savepoint:
        connection.execute(f"RELEASE SAVEPOINT {savepoint}")
    else:
        connection.commit()


def _rollback_sqlite_transaction(connection: sqlite3.Connection, savepoint: str) -> None:
    if savepoint:
        connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        connection.execute(f"RELEASE SAVEPOINT {savepoint}")
    else:
        connection.rollback()


def begin_video_confirm_execution(
    session: dict | None,
    *,
    user_id: int,
    chat_id: int,
    project_id: int,
    idempotency_key: str,
    payload: dict | None = None,
    product_type: str = "video_ai_real",
    conn=None,
) -> dict:
    """Atomically persist one request and one non-claimable internal job."""

    from services import video_project_queue

    session = dict(session or {})
    draft = dict(session.get("draft") or {})
    clean_project_id = int(project_id or 0)
    clean_user_id = int(user_id or 0)
    clean_chat_id = int(chat_id or 0)
    attempt_key = str(idempotency_key or "").strip()[:240]
    if clean_project_id <= 0 or clean_user_id <= 0 or not attempt_key:
        return {
            "ok": False,
            "request_id": "",
            "job_id": 0,
            "session": session,
            "reason": "invalid_confirm_identity",
            "durable_persisted": False,
        }

    connection, should_close = get_db_connection(conn)
    savepoint = ""
    identity_valid = False
    request_id = ""
    job_id = 0
    job: dict[str, Any] = {}
    transaction_committed = False
    try:
        ensure_video_trace_schema(connection)
        video_project_queue.ensure_video_project_queue_schema(connection)
        savepoint = _begin_sqlite_transaction(connection)

        project_row = connection.execute(
            "SELECT project_id,user_id FROM video_projects WHERE project_id=? LIMIT 1",
            (clean_project_id,),
        ).fetchone()
        if not project_row:
            raise ValueError("project_not_found")
        if int(project_row[1]) != clean_user_id:
            raise PermissionError("project_user_mismatch")
        identity_valid = True

        existing = lookup_video_request_trace_by_attempt_key(attempt_key, conn=connection)
        if existing and int(existing.get("owner_user_id") or 0) not in {0, clean_user_id}:
            raise PermissionError("confirm_attempt_owner_mismatch")
        request_id = str(
            (existing or {}).get("request_id")
            or draft.get("request_id")
            or draft.get("trace_id")
            or generate_video_request_id()
        ).strip()
        trace = dict(existing or draft.get("video_trace") or {})
        prior_job_id = int(trace.get("job_id") or 0)
        trace.update(
            {
                **dict(payload or {}),
                "request_id": request_id,
                "project_id": clean_project_id,
                "confirm_attempt_key": attempt_key,
                "owner_user_id": clean_user_id,
                "owner_chat_id": clean_chat_id,
                "product_type": str(product_type or trace.get("product_type") or "video_ai_real"),
            }
        )
        if not existing:
            trace.update(
                {
                    "provider_task_id": None,
                    "preflight_result": "RUNNING",
                    "admission_result": "NOT_RUN",
                    "submit_count": 0,
                    "poll_count": 0,
                    "charge_count": 0,
                    "charge_state": "NO_CHARGE",
                }
            )
        if not trace.get("events"):
            trace = _append_trace_event(trace, STAGE_REQUEST_RECEIVED, payload)
        if not persist_video_request_trace(trace, conn=connection, commit=False):
            raise RuntimeError("trace_persistence_failed")

        job = video_project_queue.begin_video_precheck_job(
            connection,
            project_id=clean_project_id,
            user_id=clean_user_id,
            chat_id=clean_chat_id,
            request_id=request_id,
            confirm_attempt_key=attempt_key,
        )
        job_id = int(job.get("id") or 0)
        if job_id <= 0:
            raise RuntimeError("job_create_failed")
        trace["job_id"] = job_id
        if prior_job_id <= 0:
            trace["internal_blocker_code"] = None
            trace = _append_trace_event(
                trace,
                STAGE_JOB_CREATED,
                {"project_id": clean_project_id, "job_id": job_id},
            )
        if not persist_video_request_trace(trace, conn=connection, commit=False):
            raise RuntimeError("request_job_link_failed")
        _commit_sqlite_transaction(connection, savepoint)
        savepoint = ""
        transaction_committed = True

        trace_readback = lookup_video_request_trace(request_id, conn=connection)
        job_readback = video_project_queue.get_video_render_job(connection, job_id)
        if not trace_readback or int(trace_readback.get("job_id") or 0) != job_id or not job_readback:
            raise RuntimeError("request_job_readback_failed")
        draft.update(
            {
                "request_id": request_id,
                "public_processing_code": request_id,
                "video_trace": trace_readback,
                "b14_project_id": clean_project_id,
                "b14_queue_job_id": job_id,
                "b14_queue_job": job_readback,
                "b14_duplicate_prevented": bool(job.get("duplicate_prevented")),
                "b14_submit_attempted": True,
                "provider_called": False,
                "job_created": True,
                "outbox_created": False,
                "xu_charged": 0,
            }
        )
        session["draft"] = draft
        return {
            "ok": True,
            "request_id": request_id,
            "job_id": job_id,
            "job": job_readback,
            "session": session,
            "reason": "",
            "durable_persisted": True,
            "duplicate_prevented": bool(job.get("duplicate_prevented")),
        }
    except Exception as exc:
        try:
            _rollback_sqlite_transaction(connection, savepoint)
        except Exception:
            pass
        reason = str(exc or "job_create_failed")
        if transaction_committed and job_id > 0 and reason == "request_job_readback_failed":
            draft.update(
                {
                    "request_id": request_id,
                    "public_processing_code": request_id,
                    "b14_project_id": clean_project_id,
                    "b14_queue_job_id": job_id,
                    "b14_queue_job": dict(job or {}),
                    "b14_duplicate_prevented": bool(job.get("duplicate_prevented")),
                    "b14_submit_attempted": True,
                    "provider_called": False,
                    "job_created": True,
                    "outbox_created": False,
                    "xu_charged": 0,
                }
            )
            session["draft"] = draft
            logger.warning("begin_video_confirm_execution committed but readback failed")
            return {
                "ok": False,
                "request_id": request_id,
                "job_id": job_id,
                "job": dict(job or {}),
                "session": session,
                "reason": "request_job_readback_failed",
                "durable_persisted": True,
                "duplicate_prevented": bool(job.get("duplicate_prevented")),
            }
        if reason not in {
            "project_not_found",
            "project_user_mismatch",
            "confirm_attempt_owner_mismatch",
            "trace_persistence_failed",
        }:
            reason = "job_create_failed"
        durable_failure = False
        if identity_valid and reason == "job_create_failed":
            request_id = request_id or str(draft.get("request_id") or generate_video_request_id())
            failure_trace = {
                "request_id": request_id,
                "project_id": clean_project_id,
                "confirm_attempt_key": attempt_key,
                "owner_user_id": clean_user_id,
                "owner_chat_id": clean_chat_id,
                "product_type": str(product_type or "video_ai_real"),
                "job_id": None,
                "provider_task_id": None,
                "internal_blocker_code": "job_create_failed",
                "preflight_result": "NOT_RUN",
                "admission_result": "NOT_RUN",
                "submit_count": 0,
                "poll_count": 0,
                "charge_count": 0,
                "charge_state": "NO_CHARGE",
            }
            failure_trace = _append_trace_event(
                failure_trace,
                STAGE_JOB_CREATE_FAILED,
                {"project_id": clean_project_id},
                "job_create_failed",
            )
            durable_failure = persist_video_request_trace(failure_trace, conn=connection)
            draft.update(
                {
                    "request_id": request_id,
                    "public_processing_code": request_id,
                    "video_trace": failure_trace,
                    "b14_queue_job_id": 0,
                    "b14_queue_job": {},
                    "provider_called": False,
                    "job_created": False,
                    "outbox_created": False,
                    "xu_charged": 0,
                }
            )
            session["draft"] = draft
        logger.warning("begin_video_confirm_execution failed: %s", reason)
        return {
            "ok": False,
            "request_id": request_id,
            "job_id": 0,
            "session": session,
            "reason": reason,
            "durable_persisted": bool(durable_failure),
        }
    finally:
        if should_close:
            connection.close()


def record_video_confirm_precheck_result(
    session: dict | None,
    *,
    user_id: int,
    chat_id: int,
    job_id: int,
    preflight_result: str,
    admission_result: str,
    blocker_code: str = "",
    payload: dict | None = None,
    conn=None,
) -> dict:
    """Update the same durable job after preflight without submitting it."""

    from services import video_project_queue

    session = dict(session or {})
    draft = dict(session.get("draft") or {})
    clean_job_id = int(job_id or 0)
    clean_user_id = int(user_id or 0)
    connection, should_close = get_db_connection(conn)
    savepoint = ""
    try:
        ensure_video_trace_schema(connection)
        video_project_queue.ensure_video_project_queue_schema(connection)
        savepoint = _begin_sqlite_transaction(connection)
        trace = lookup_video_request_trace_by_job_id(clean_job_id, conn=connection)
        if not trace:
            raise ValueError("request_trace_not_found")
        if int(trace.get("owner_user_id") or 0) not in {0, clean_user_id}:
            raise PermissionError("request_owner_mismatch")

        preflight = str(preflight_result or "NOT_RUN").strip().upper()
        admission = str(admission_result or "NOT_RUN").strip().upper()
        effective_chat_id = int(chat_id or trace.get("owner_chat_id") or 0)
        precheck_payload = dict(payload or {})
        if effective_chat_id > 0:
            precheck_payload["chat_id"] = effective_chat_id
        job = video_project_queue.record_video_precheck_job_result(
            connection,
            job_id=clean_job_id,
            user_id=clean_user_id,
            preflight_result=preflight,
            admission_result=admission,
            blocker_code=blocker_code,
            payload=precheck_payload,
        )
        if preflight == "PASS" and admission == "PASS":
            stage = STAGE_READY_TO_SUBMIT
        elif admission == "BLOCKED":
            stage = STAGE_ADMISSION_BLOCKED
        else:
            stage = STAGE_PREFLIGHT_BLOCKED
        trace.update(
            {
                **precheck_payload,
                "job_id": clean_job_id,
                "owner_user_id": clean_user_id,
                "owner_chat_id": effective_chat_id,
                "preflight_result": preflight,
                "admission_result": admission,
                "internal_blocker_code": str(blocker_code or "").strip() or None,
                "provider_task_id": None,
                "submit_count": 0,
                "poll_count": 0,
                "charge_count": 0,
                "charge_state": "NO_CHARGE",
            }
        )
        trace = _append_trace_event(
            trace,
            stage,
            {
                **precheck_payload,
                "job_id": clean_job_id,
                "preflight_result": preflight,
                "admission_result": admission,
            },
            blocker_code,
        )
        if not persist_video_request_trace(trace, conn=connection, commit=False):
            raise RuntimeError("precheck_trace_persistence_failed")
        _commit_sqlite_transaction(connection, savepoint)
        savepoint = ""

        trace_readback = lookup_video_request_trace_by_job_id(clean_job_id, conn=connection)
        job_readback = video_project_queue.get_video_render_job(connection, clean_job_id)
        draft.update(
            {
                "request_id": str(trace_readback.get("request_id") or ""),
                "public_processing_code": str(trace_readback.get("request_id") or ""),
                "video_trace": trace_readback,
                "b14_queue_job_id": clean_job_id,
                "b14_queue_job": job_readback,
                "b14_submit_attempted": True,
                "provider_called": False,
                "job_created": True,
                "outbox_created": False,
                "xu_charged": 0,
            }
        )
        session["draft"] = draft
        return {
            "ok": True,
            "request_id": str(trace_readback.get("request_id") or ""),
            "job_id": clean_job_id,
            "job": job_readback,
            "trace": trace_readback,
            "session": session,
            "reason": "",
        }
    except Exception as exc:
        try:
            _rollback_sqlite_transaction(connection, savepoint)
        except Exception:
            pass
        return {
            "ok": False,
            "request_id": str(draft.get("request_id") or ""),
            "job_id": clean_job_id,
            "job": {},
            "session": session,
            "reason": str(exc or "precheck_persistence_failed"),
        }
    finally:
        if should_close:
            connection.close()
