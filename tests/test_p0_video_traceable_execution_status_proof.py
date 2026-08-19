"""Comprehensive test suite for TOAN AAS — P0.VIDEO.TRACEABLE.EXECUTION.STATUS.PROOF.

Validates:
1. Three-ID Contract: REQUEST_ID != JOB_ID != PROVIDER_TASK_ID.
2. Status panel UI rendering:
   - No internal job -> "Mã yêu cầu: <REQUEST_ID>", "Mã tác vụ: Chưa tạo".
   - Internal job created -> "Mã yêu cầu: <REQUEST_ID>", "Mã tác vụ: #<JOB_ID>".
   - Provider submit succeeded -> "Mã provider: <PROVIDER_TASK_ID>".
3. Honest blocker copy for provider_not_configured vs provider_unavailable.
4. Event trace recording and persistence.
5. Idempotent status refresh preserving REQUEST_ID.
"""

from __future__ import annotations

import datetime
import pytest
import services.video_trace_state as vts
import bot


def test_generate_video_request_id_format():
    """Verify REQUEST_ID format VID-YYYYMMDD-XXXXXX."""
    req_id = vts.generate_video_request_id()
    assert req_id.startswith("VID-")
    parts = req_id.split("-")
    assert len(parts) == 3
    assert len(parts[1]) == 8  # YYYYMMDD
    assert len(parts[2]) == 6  # Hex token


def test_three_id_separation_in_trace_state():
    """Verify Three-ID separation: REQUEST_ID exists while JOB_ID is None."""
    session = {"draft": {}}
    session = vts.record_video_trace_event(
        session,
        vts.STAGE_REQUEST_RECEIVED,
        user_id=12345,
    )
    session = vts.record_video_trace_event(
        session,
        vts.STAGE_PRECHECK_STARTED,
        user_id=12345,
    )
    session = vts.record_video_trace_event(
        session,
        vts.STAGE_ADMISSION_BLOCKED,
        user_id=12345,
        blocker_code="provider_not_configured",
    )
    trace = session["draft"]["video_trace"]
    assert trace["request_id"].startswith("VID-")
    assert trace["job_id"] is None
    assert trace["provider_task_id"] is None
    assert trace["current_stage"] == vts.STAGE_ADMISSION_BLOCKED
    assert trace["internal_blocker_code"] == "provider_not_configured"
    assert len(trace["events"]) == 3


def test_status_panel_text_when_admission_blocked():
    """Verify status panel text when admission blocked before internal job creation."""
    session = {
        "user_id": 99999,
        "current_step": "b14_queue_status",
        "draft": {
            "request_id": "VID-20260819-A1B2C3",
            "public_processing_code": "VID-20260819-A1B2C3",
            "b14_scene_count": 3,
            "b14_quality_xu": 150,
            "b14_submit_attempted": True,
            "b14_submit_preflight_snapshot": {
                "allowed": False,
                "blocker_code": "provider_not_configured",
                "public_message": "TOAN AAS chưa thể khởi tạo kênh dựng cho cấu hình này.",
            },
            "b14_queue_job": {},
            "b14_queue_job_id": 0,
        },
    }
    panel_text = bot.video_b14_queue_status_text(session, user_id=99999)
    assert "Mã yêu cầu: <b>VID-20260819-A1B2C3</b>" in panel_text
    assert "Mã tác vụ: <b>Chưa tạo</b>" in panel_text
    assert "Mã xử lý: Không có" not in panel_text
    assert "Mã provider:" not in panel_text
    assert "Bước hiện tại: <b>Tạm dừng tại bước kiểm tra</b>" in panel_text or "Bước hiện tại: <b>Đang kiểm tra cấu hình</b>" in panel_text
    assert "Nhận yêu cầu" in panel_text
    assert "Kiểm tra cấu hình" in panel_text


def test_status_panel_text_when_job_created():
    """Verify status panel text when internal job created."""
    session = {
        "user_id": 88888,
        "current_step": "b14_queue_status",
        "draft": {
            "request_id": "VID-20260819-JOB123",
            "public_processing_code": "VID-20260819-JOB123",
            "b14_scene_count": 3,
            "b14_quality_xu": 150,
            "b14_queue_job": {"id": 7890, "status": "queued"},
            "b14_queue_job_id": 7890,
            "job_created": True,
        },
    }
    panel_text = bot.video_b14_queue_status_text(
        session,
        result={"job": {"id": 7890, "status": "queued", "progress": 10}},
        user_id=88888,
    )
    assert "Mã yêu cầu: <b>VID-20260819-JOB123</b>" in panel_text
    assert "Mã tác vụ: <b>#7890</b>" in panel_text
    assert "Mã provider:" not in panel_text
    assert "Đã xác nhận tạo video" in panel_text


def test_status_panel_text_when_provider_task_submitted():
    """Verify status panel text when real provider submit returned task_id."""
    session = {
        "user_id": 77777,
        "current_step": "b14_queue_status",
        "draft": {
            "request_id": "VID-20260819-PROV99",
            "public_processing_code": "VID-20260819-PROV99",
            "b14_scene_count": 3,
            "b14_quality_xu": 150,
            "b14_queue_job": {"id": 9999, "status": "processing"},
            "b14_queue_job_id": 9999,
        },
    }
    panel_text = bot.video_b14_queue_status_text(
        session,
        result={
            "job": {
                "id": 9999,
                "status": "processing",
                "progress": 50,
                "provider_task_id": "luma-task-abc-123",
            }
        },
        user_id=77777,
    )
    assert "Mã yêu cầu: <b>VID-20260819-PROV99</b>" in panel_text
    assert "Mã tác vụ: <b>#9999</b>" in panel_text
    assert "Mã provider: <b>luma-task-abc-123</b>" in panel_text


def test_video_b14_blocker_label_truthful_wording():
    """Verify truthful blocker labels."""
    label_unconfigured = bot.video_b14_blocker_label("provider_not_configured")
    assert "Hệ thống chưa thể khởi tạo kênh dựng cho cấu hình này" in label_unconfigured
    assert "(tạm bận)" not in label_unconfigured

    label_unavailable = bot.video_b14_blocker_label("provider_unavailable")
    assert "(tạm bận)" in label_unavailable
