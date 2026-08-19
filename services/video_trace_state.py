"""Video Execution Trace & Three-ID Contract Service.

Provides immutable REQUEST_ID / TRACE_ID generation, event trace recording,
and truthful 3-tier identifier separation (REQUEST_ID != JOB_ID != PROVIDER_TASK_ID).
"""

from __future__ import annotations

import datetime
import hashlib
import html
import os
import secrets
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
) -> dict:
    """Record an ordered execution trace event onto the session draft."""
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
        "current_stage": stage,
        "current_stage_label": STAGE_LABELS.get(stage, stage),
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
    return session
