"""Video execution trace state model, SQLite persistence, and truthful status report.

Three-Tier ID separation:
- REQUEST_ID: Unique customer-facing tracking token (e.g. VID-20260819-A1B2C3).
- JOB_ID: Internal asynchronous rendering queue task ID (e.g. 101).
- PROVIDER_TASK_ID: Upstream external AI provider reference (e.g. task_xyz123).
"""

from __future__ import annotations

import datetime
import html
import json
import os
import secrets
import sqlite3
from pathlib import Path
from typing import Any

STAGE_REQUEST_RECEIVED = "REQUEST_RECEIVED"
STAGE_PRECHECK_STARTED = "PRECHECK_STARTED"
STAGE_PRECHECK_PASSED = "PRECHECK_PASSED"
STAGE_PRECHECK_RESULT = "PRECHECK_PASSED"
STAGE_ROUTE_EVALUATED = "ROUTE_EVALUATED"
STAGE_PREFLIGHT_BLOCKED = "PREFLIGHT_BLOCKED"
STAGE_ADMISSION_BLOCKED = "ADMISSION_BLOCKED"
STAGE_JOB_CREATED = "JOB_CREATED"
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
            cursor = c.execute("SELECT * FROM video_request_traces WHERE job_id = ? ORDER BY updated_at DESC LIMIT 1", (jid,))
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

        # 3. Check by provider_task_id
        cursor = c.execute("SELECT * FROM video_request_traces WHERE provider_task_id = ? ORDER BY updated_at DESC LIMIT 1", (raw,))
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

        return None
    finally:
        if should_close:
            c.close()


def lookup_video_request_trace_by_job_id(job_id: int, conn=None) -> dict | None:
    return lookup_video_request_trace(job_id, conn=conn)


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
        eligible_at_req = trace.get("eligible_route_count", 1 if job_id else 0)
        selected_at_req = trace.get("selected_route") or ("shopaikey_video" if job_id else "None")

        return {
            "identifier_type": "request_id" if raw.startswith("VID-") else "job_id",
            "request_id": req_id or "None",
            "request_found": "YES",
            "request_source": "canonical_db_video_request_traces",
            "durable_request_found": "YES",
            "job_id": str(job_id) if job_id else "None",
            "job_found": "YES" if job_record or (job_id and job_id > 0) else "NO",
            "provider_task_id": str(prov_task_id or "None"),
            "provider_task_found": "YES" if prov_task_id and prov_task_id != "None" else "NO",
            "current_stage": stage,
            "preflight_result": trace.get("preflight_result") or ("PASS" if job_id else "BLOCKED"),
            "admission_result": trace.get("admission_result") or ("PASS" if job_id else "BLOCKED"),
            "exact_blocker_code": blocker,
            "exact_blocker_detail": trace.get("blocker_detail_safe") or blocker,
            "why_no_job": f"Đã tạo tác vụ nội bộ (#{job_id})" if job_id else f"Yêu cầu dừng tại bước kiểm tra ({blocker}); Bot chưa trừ Xu.",
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
        "SUBMIT_COUNT": 1 if truth["job_found"] == "YES" else 0,
        "POLL_COUNT": trace.get("poll_count", 0),
        "ARTIFACT": trace.get("final_video_path", "None"),
        "DELIVERY_RECEIPT": trace.get("delivery_receipt", "None"),
        "CHARGE_STATE": trace.get("charge_state", "NO_CHARGE"),
        "STATUS_SOURCE": truth["status_source"],
        "WHY_NO_JOB": truth["why_no_job"],
    }
