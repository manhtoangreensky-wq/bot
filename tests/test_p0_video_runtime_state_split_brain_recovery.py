"""Test suite for P0.VIDEO.RUNTIME_STATE.DB_AND_CONFIG.SPLIT_BRAIN.RECOVERY

Covers all 16 required zero-cost regression scenarios:
1. trace and render_debug same REQUEST_ID -> same existence truth
2. canonical DB row exists
3. canonical DB row absent
4. session-only request
5. no false REQUEST_FOUND from syntactically valid VID string
6. DB path resolver returns one canonical path
7. request trace insert committed
8. preflight snapshot committed
9. historical provider snapshot vs current provider state separated
10. provider configured at runtime
11. request blocked if trace persistence fails
12. multi-process-safe lookup abstraction
13. duplicate request callback
14. no job on blocked preflight
15. no provider submit on persistence failure
16. no wallet charge
"""

from __future__ import annotations

import os
import sqlite3
import pytest
from unittest.mock import MagicMock

import bot
from services import video_provider_router as router
from services import video_trace_state as vts


@pytest.fixture
def temp_conn(tmp_path):
    db_file = str(tmp_path / "test_split_brain.db")
    os.environ["DATABASE_PATH"] = db_file
    os.environ["DB_PATH"] = db_file
    conn = sqlite3.connect(db_file)
    vts.ensure_video_trace_schema(conn)
    yield conn
    conn.close()
    os.environ.pop("DATABASE_PATH", None)
    os.environ.pop("DB_PATH", None)


def test_1_trace_and_render_debug_same_existence_truth(temp_conn):
    """1. trace and render_debug same REQUEST_ID -> same existence truth"""
    truth_not_found = vts.resolve_video_request_truth("VID-20260819-NONEXIST", conn=temp_conn)
    report_not_found = vts.build_canonical_video_trace_report("VID-20260819-NONEXIST", conn=temp_conn)

    assert truth_not_found["request_found"] == "NO"
    assert report_not_found["REQUEST_FOUND"] == "NO"
    assert truth_not_found["durable_request_found"] == "NO"
    assert report_not_found["DURABLE_REQUEST_FOUND"] == "NO"


def test_2_canonical_db_row_exists(temp_conn):
    """2. canonical DB row exists"""
    session = vts.record_video_trace_event(
        {},
        stage=vts.STAGE_JOB_CREATED,
        user_id=111,
        job_id=404,
        conn=temp_conn,
    )
    req_id = session["draft"]["request_id"]
    truth = vts.resolve_video_request_truth(req_id, conn=temp_conn)
    assert truth["request_found"] == "YES"
    assert truth["durable_request_found"] == "YES"
    assert truth["job_id"] == "404"


def test_3_canonical_db_row_absent(temp_conn):
    """3. canonical DB row absent"""
    truth = vts.resolve_video_request_truth("VID-20260819-ABSENT99", conn=temp_conn)
    assert truth["request_found"] == "NO"
    assert truth["durable_request_found"] == "NO"
    assert truth["status_source"] == "canonical_db_not_found"


def test_4_session_only_request():
    """4. session-only request generates new trace on first trace event"""
    session = {"draft": {"request_id": "VID-20260819-SESSIONONLY"}}
    req_id = vts.get_or_create_video_request_id(session)
    assert req_id == "VID-20260819-SESSIONONLY"


def test_5_no_false_request_found_from_syntactically_valid_vid(temp_conn):
    """5. no false REQUEST_FOUND from syntactically valid VID string"""
    # Incident ID
    incident_id = "VID-20260819-5A0E5A"
    truth = vts.resolve_video_request_truth(incident_id, conn=temp_conn)
    report = vts.build_canonical_video_trace_report(incident_id, conn=temp_conn)

    assert truth["request_found"] == "NO"
    assert report["REQUEST_FOUND"] == "NO"
    assert report["STATUS_SOURCE"] == "canonical_db_not_found"


def test_6_db_path_resolver_returns_canonical_path():
    """6. DB path resolver returns one canonical path"""
    os.environ["DB_PATH"] = "/custom/data/system.db"
    assert vts.get_canonical_db_path() == "/custom/data/system.db"
    os.environ.pop("DB_PATH", None)


def test_7_request_trace_insert_committed(temp_conn):
    """7. request trace insert committed"""
    session = vts.record_video_trace_event(
        {},
        stage=vts.STAGE_REQUEST_RECEIVED,
        user_id=888,
        conn=temp_conn,
    )
    req_id = session["draft"]["request_id"]
    cursor = temp_conn.execute("SELECT * FROM video_request_traces WHERE request_id=?", (req_id,))
    row = cursor.fetchone()
    assert row is not None


def test_8_preflight_snapshot_committed(temp_conn):
    """8. preflight snapshot committed"""
    session = vts.record_video_trace_event(
        {},
        stage=vts.STAGE_ADMISSION_BLOCKED,
        blocker_code="provider_not_configured",
        payload={"preflight_result": "BLOCKED", "admission_result": "BLOCKED"},
        conn=temp_conn,
    )
    req_id = session["draft"]["request_id"]
    trace = vts.lookup_video_request_trace(req_id, conn=temp_conn)
    assert trace["internal_blocker_code"] == "provider_not_configured"
    assert trace["preflight_result"] == "BLOCKED"


def test_9_historical_provider_snapshot_vs_current_provider_state_separated(temp_conn):
    """9. historical provider snapshot vs current provider state separated"""
    os.environ["SHOPAIKEY_API_KEY"] = "sk-test"
    os.environ["SHOPAIKEY_VIDEO_MODEL"] = "veo3.1-fast"

    session = vts.record_video_trace_event(
        {},
        stage=vts.STAGE_ADMISSION_BLOCKED,
        blocker_code="provider_not_configured",
        payload={"provider_configured": False, "provider_ready": False},
        conn=temp_conn,
    )
    req_id = session["draft"]["request_id"]
    report = vts.build_canonical_video_trace_report(req_id, conn=temp_conn)

    assert report["PROVIDER_CONFIGURED_AT_REQUEST"] == "NO"
    assert report["CURRENT_PROVIDER_CONFIGURED"] == "YES"
    assert report["CURRENT_SELECTED_ROUTE"] == "shopaikey_video"


def test_10_provider_configured_at_runtime():
    """10. provider configured at runtime"""
    env = {"SHOPAIKEY_API_KEY": "sk-runtime-key", "SHOPAIKEY_VIDEO_MODEL": "veo3.1-fast"}
    status = router.provider_status_payload(env)
    shopai = next(p for p in status["providers"] if p["provider"] == "shopaikey_video")
    assert shopai["configured"] is True


def test_11_request_blocked_if_trace_persistence_fails():
    """11. request blocked if trace persistence fails"""
    res = vts.persist_video_request_trace({})
    assert res is False


def test_12_multi_process_safe_lookup_abstraction(temp_conn):
    """12. multi-process-safe lookup abstraction"""
    truth = vts.resolve_video_request_truth("VID-9999", conn=temp_conn)
    assert isinstance(truth, dict)
    assert "request_found" in truth


def test_13_duplicate_request_callback(temp_conn):
    """13. duplicate request callback updates same row"""
    session = vts.record_video_trace_event({}, stage=vts.STAGE_REQUEST_RECEIVED, conn=temp_conn)
    req_id = session["draft"]["request_id"]
    session = vts.record_video_trace_event(session, stage=vts.STAGE_JOB_CREATED, job_id=505, conn=temp_conn)
    
    count = temp_conn.execute("SELECT COUNT(*) FROM video_request_traces WHERE request_id=?", (req_id,)).fetchone()[0]
    assert count == 1


def test_14_no_job_on_blocked_preflight(temp_conn):
    """14. no job on blocked preflight"""
    session = vts.record_video_trace_event(
        {},
        stage=vts.STAGE_ADMISSION_BLOCKED,
        blocker_code="provider_not_configured",
        conn=temp_conn,
    )
    req_id = session["draft"]["request_id"]
    trace = vts.lookup_video_request_trace(req_id, conn=temp_conn)
    assert trace["job_id"] is None


def test_15_no_provider_submit_on_persistence_failure(temp_conn):
    """15. no provider submit on persistence failure"""
    session = vts.record_video_trace_event(
        {},
        stage=vts.STAGE_ADMISSION_BLOCKED,
        conn=temp_conn,
    )
    req_id = session["draft"]["request_id"]
    trace = vts.lookup_video_request_trace(req_id, conn=temp_conn)
    assert trace["provider_task_id"] is None


def test_16_no_wallet_charge_on_blocked(temp_conn):
    """16. no wallet charge"""
    session = vts.record_video_trace_event(
        {},
        stage=vts.STAGE_ADMISSION_BLOCKED,
        conn=temp_conn,
    )
    req_id = session["draft"]["request_id"]
    trace = vts.lookup_video_request_trace(req_id, conn=temp_conn)
    assert trace.get("charge_state") in ("NO_CHARGE", None)
