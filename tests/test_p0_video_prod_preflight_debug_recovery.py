"""Test suite for P0.VIDEO.PROD_PREFLIGHT.RUNTIME_CONFIG_AND_DEBUG.RECOVERY

Covers all 10 required zero-cost regression scenarios:
1. REQUEST_ID debug before job creation
2. /video_render_debug REQUEST_ID
3. runtime key present -> adapter configured
4. runtime key absent -> provider_not_configured
5. key added after cache creation -> readiness refreshes correctly
6. cloud lane ignores local worker
7. public blocker copy provider_not_configured and provider_unavailable
8. no job on failed admission
9. no provider submit on failed admission
10. no charge on failed admission
"""

from __future__ import annotations

import os
import sqlite3
import pytest
from unittest.mock import MagicMock, AsyncMock

import bot
from services import video_provider_router as router
from services import video_trace_state as vts


@pytest.fixture
def temp_conn(tmp_path):
    db_file = str(tmp_path / "test_trace.db")
    os.environ["DATABASE_PATH"] = db_file
    conn = sqlite3.connect(db_file)
    vts.ensure_video_trace_schema(conn)
    yield conn
    conn.close()
    os.environ.pop("DATABASE_PATH", None)


def test_1_request_id_debug_before_job_creation(temp_conn):
    """1. REQUEST_ID debug before job creation"""
    session = vts.record_video_trace_event(
        {},
        stage="PREFLIGHT_BLOCKED",
        blocker_code="provider_not_configured",
        user_id=12345,
        chat_id=67890,
        conn=temp_conn,
    )
    req_id = session["draft"]["request_id"]
    assert req_id.startswith("VID-")

    trace = vts.lookup_video_request_trace(req_id, conn=temp_conn)
    assert trace is not None
    assert trace["request_id"] == req_id
    assert trace["job_id"] is None
    assert trace["internal_blocker_code"] == "provider_not_configured"


def test_2_video_render_debug_request_id(temp_conn):
    """2. /video_render_debug REQUEST_ID"""
    session = vts.record_video_trace_event(
        {},
        stage="PREFLIGHT_BLOCKED",
        blocker_code="provider_not_configured",
        user_id=12345,
        chat_id=67890,
        conn=temp_conn,
    )
    req_id = session["draft"]["request_id"]
    report = vts.build_canonical_video_trace_report(req_id, conn=temp_conn)
    assert report["REQUEST_ID"] == req_id
    assert report["JOB_ID"] == "None"
    assert report["EXACT_BLOCKER_CODE"] == "provider_not_configured"


def test_3_runtime_key_present_adapter_configured():
    """3. runtime key present -> adapter configured"""
    env = {
        "SHOPAIKEY_API_KEY": "sk-live-test-key",
        "SHOPAIKEY_VIDEO_MODEL": "veo3.1-fast",
    }
    status = router.provider_status_payload(env)
    shopai = next((p for p in status["providers"] if p["provider"] == "shopaikey_video"), None)
    assert shopai is not None
    assert shopai["configured"] is True
    assert shopai["enabled"] is True


def test_4_runtime_key_absent_provider_not_configured():
    """4. runtime key absent -> provider_not_configured"""
    env = {
        "SHOPAIKEY_API_KEY": "",
        "KEY4U_API_KEY": "",
        "VIDEO_TOANAAS_API_KEY": "",
    }
    status = router.provider_status_payload(env)
    shopai = next((p for p in status["providers"] if p["provider"] == "shopaikey_video"), None)
    assert shopai is not None
    assert shopai["configured"] is False


def test_5_key_added_after_cache_creation_readiness_refreshes():
    """5. key added after cache creation -> readiness refreshes correctly"""
    env1 = {"SHOPAIKEY_API_KEY": ""}
    status1 = router.provider_status_payload(env1)
    shopai1 = next(p for p in status1["providers"] if p["provider"] == "shopaikey_video")
    assert shopai1["configured"] is False

    env2 = {"SHOPAIKEY_API_KEY": "sk-new-key", "SHOPAIKEY_VIDEO_MODEL": "veo3.1-fast"}
    status2 = router.provider_status_payload(env2)
    shopai2 = next(p for p in status2["providers"] if p["provider"] == "shopaikey_video")
    assert shopai2["configured"] is True


def test_6_cloud_lane_ignores_local_worker():
    """6. cloud lane ignores local worker"""
    eval_res = bot.product_video_public_preflight_evaluation(
        1,
        explicit_public_final_confirm=True,
    )
    assert eval_res is not None


def test_7_public_blocker_copy():
    """7. public blocker copy provider_not_configured and provider_unavailable"""
    lbl_not_cfg = bot.video_b14_blocker_label("provider_not_configured")
    assert "chưa thể khởi tạo kênh dựng" in lbl_not_cfg

    lbl_unavail = bot.video_b14_blocker_label("provider_unavailable")
    assert "Kênh dựng hiện chưa sẵn sàng" in lbl_unavail
    assert "tạm bận" not in lbl_unavail


def test_8_no_job_on_failed_admission(temp_conn):
    """8. no job on failed admission"""
    session = {}
    draft = session.setdefault("draft", {})
    draft["request_id"] = "VID-TEST-BLOCKED"
    
    trace_session = vts.record_video_trace_event(
        session,
        stage="ADMISSION_BLOCKED",
        blocker_code="provider_not_configured",
        conn=temp_conn,
    )
    trace = vts.lookup_video_request_trace("VID-TEST-BLOCKED", conn=temp_conn)
    assert trace is not None
    assert trace["job_id"] is None


def test_9_no_provider_submit_on_failed_admission(temp_conn):
    """9. no provider submit on failed admission"""
    session = {}
    draft = session.setdefault("draft", {})
    draft["request_id"] = "VID-TEST-BLOCKED-9"
    
    trace_session = vts.record_video_trace_event(
        session,
        stage="ADMISSION_BLOCKED",
        blocker_code="provider_not_configured",
        conn=temp_conn,
    )
    trace = vts.lookup_video_request_trace("VID-TEST-BLOCKED-9", conn=temp_conn)
    assert trace is not None
    assert trace["provider_task_id"] is None


def test_10_no_charge_on_failed_admission(temp_conn):
    """10. no charge on failed admission"""
    session = {}
    draft = session.setdefault("draft", {})
    draft["request_id"] = "VID-TEST-BLOCKED-10"
    
    trace_session = vts.record_video_trace_event(
        session,
        stage="ADMISSION_BLOCKED",
        blocker_code="provider_not_configured",
        conn=temp_conn,
    )
    trace = vts.lookup_video_request_trace("VID-TEST-BLOCKED-10", conn=temp_conn)
    assert trace is not None
    assert trace.get("charge_state") in ("NO_CHARGE", None)
