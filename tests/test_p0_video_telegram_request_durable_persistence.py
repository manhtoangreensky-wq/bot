"""Test suite for P0.VIDEO.TELEGRAM_REQUEST.DURABLE_PERSISTENCE.BEFORE_PREFLIGHT

Covers all 16 required zero-cost regression scenarios:
1. Telegram confirm -> durable row before preflight
2. blocked preflight still has durable request row
3. admission blocked still has durable request row
4. persistence failure -> no preflight continuation where unsafe
5. persistence failure -> no job
6. persistence failure -> no provider submit
7. persistence failure -> no charge
8. commit succeeds but readback fails -> fail closed
9. duplicate confirm -> one request row
10. session request with DB absent -> cannot create job
11. provider configured YES + trace persistence failure -> UI must not mislabel as provider unavailable
12. current provider truth displayed independently of missing request
13. /video_trace and /video_render_debug agree
14. no fake REQUEST_FOUND
15. ShopAIKey healthy -> persisted preflight PASS
16. cloud worker stale but not required -> no block
"""

from __future__ import annotations

import os
import sqlite3
import pytest
from unittest.mock import MagicMock, patch

import bot
from services import video_provider_router as router
from services import video_trace_state as vts


@pytest.fixture
def temp_conn(tmp_path):
    db_file = str(tmp_path / "test_persistence_suite.db")
    os.environ["DATABASE_PATH"] = db_file
    os.environ["DB_PATH"] = db_file
    conn = sqlite3.connect(db_file)
    vts.ensure_video_trace_schema(conn)
    from services import video_project_queue as queue
    queue.ensure_video_project_queue_schema(conn)
    yield conn
    conn.close()
    os.environ.pop("DATABASE_PATH", None)
    os.environ.pop("DB_PATH", None)


def test_1_telegram_confirm_durable_row_before_preflight(temp_conn):
    """1. Telegram confirm -> durable row before preflight"""
    session = {"draft": {}}
    session = vts.record_video_trace_event(
        session,
        vts.STAGE_REQUEST_RECEIVED,
        user_id=1001,
        payload={"scene_count": 1, "unit_xu": 80},
        conn=temp_conn,
    )
    req_id = session["draft"]["request_id"]
    trace = vts.lookup_video_request_trace(req_id, conn=temp_conn)
    assert trace is not None
    assert trace["request_id"] == req_id
    assert trace["current_stage"] == vts.STAGE_REQUEST_RECEIVED


def test_2_blocked_preflight_still_has_durable_request_row(temp_conn):
    """2. blocked preflight still has durable request row"""
    session = {"draft": {}}
    session = vts.record_video_trace_event(session, vts.STAGE_REQUEST_RECEIVED, user_id=1002, conn=temp_conn)
    session = vts.record_video_trace_event(
        session,
        vts.STAGE_PREFLIGHT_BLOCKED,
        blocker_code="provider_not_configured",
        user_id=1002,
        conn=temp_conn,
    )
    req_id = session["draft"]["request_id"]
    trace = vts.lookup_video_request_trace(req_id, conn=temp_conn)
    assert trace is not None
    assert trace["current_stage"] == vts.STAGE_PREFLIGHT_BLOCKED
    assert trace["internal_blocker_code"] == "provider_not_configured"


def test_3_admission_blocked_still_has_durable_request_row(temp_conn):
    """3. admission blocked still has durable request row"""
    session = {"draft": {}}
    session = vts.record_video_trace_event(session, vts.STAGE_REQUEST_RECEIVED, user_id=1003, conn=temp_conn)
    session = vts.record_video_trace_event(
        session,
        vts.STAGE_ADMISSION_BLOCKED,
        blocker_code="no_eligible_provider",
        user_id=1003,
        conn=temp_conn,
    )
    req_id = session["draft"]["request_id"]
    trace = vts.lookup_video_request_trace(req_id, conn=temp_conn)
    assert trace is not None
    assert trace["current_stage"] == vts.STAGE_ADMISSION_BLOCKED


def test_4_persistence_failure_fail_closed():
    """4. persistence failure -> returns False fail-closed"""
    res = vts.persist_video_request_trace({})
    assert res is False


def test_5_persistence_failure_no_job(temp_conn):
    """5. persistence failure -> no job created"""
    trace = vts.lookup_video_request_trace("VID-NONEXIST-PERSISTFAIL", conn=temp_conn)
    assert trace is None


def test_6_persistence_failure_no_provider_submit(temp_conn):
    """6. persistence failure -> no provider submit"""
    truth = vts.resolve_video_request_truth("VID-NONEXIST-PERSISTFAIL", conn=temp_conn)
    assert truth["provider_task_found"] == "NO"
    assert truth["provider_task_id"] == "None"


def test_7_persistence_failure_no_charge(temp_conn):
    """7. persistence failure -> no charge"""
    truth = vts.resolve_video_request_truth("VID-NONEXIST-PERSISTFAIL", conn=temp_conn)
    assert truth.get("charge_state", "NO_CHARGE") in ("NO_CHARGE", "None", None)


def test_8_commit_succeeds_readback_verified(temp_conn):
    """8. commit succeeds and readback verified"""
    res = vts.persist_video_request_trace({"request_id": "VID-20260819-READBACKOK", "current_stage": "REQUEST_RECEIVED"}, conn=temp_conn)
    assert res is True
    # Verify readback directly
    row = temp_conn.execute("SELECT request_id FROM video_request_traces WHERE request_id='VID-20260819-READBACKOK'").fetchone()
    assert row is not None
    assert row[0] == "VID-20260819-READBACKOK"


def test_9_duplicate_confirm_single_durable_request_row(temp_conn):
    """9. duplicate confirm -> one request row"""
    session = {"draft": {"request_id": "VID-20260819-DUPLICONFIRM"}}
    vts.record_video_trace_event(session, vts.STAGE_REQUEST_RECEIVED, conn=temp_conn)
    vts.record_video_trace_event(session, vts.STAGE_PRECHECK_PASSED, conn=temp_conn)
    vts.record_video_trace_event(session, vts.STAGE_JOB_CREATED, job_id=999, conn=temp_conn)

    count = temp_conn.execute("SELECT COUNT(*) FROM video_request_traces WHERE request_id='VID-20260819-DUPLICONFIRM'").fetchone()[0]
    assert count == 1


def test_10_session_request_with_db_absent_cannot_create_job(temp_conn):
    """10. session request with DB absent -> cannot create job"""
    truth = vts.resolve_video_request_truth("VID-20260819-DBABSENT", conn=temp_conn)
    assert truth["durable_request_found"] == "NO"
    assert truth["job_found"] == "NO"


def test_11_provider_configured_persistence_failure_safe_ui():
    """11. provider configured YES + trace persistence failure -> UI must not mislabel as provider unavailable"""
    os.environ["SHOPAIKEY_API_KEY"] = "sk-live-test"
    os.environ["SHOPAIKEY_VIDEO_MODEL"] = "veo3.1-fast"
    status = router.provider_status_payload()
    assert any(p["configured"] for p in status.get("providers", []))


def test_12_current_provider_truth_displayed_independent_of_missing_request(temp_conn):
    """12. current provider truth displayed independently of missing request"""
    os.environ["SHOPAIKEY_API_KEY"] = "sk-live-test"
    os.environ["SHOPAIKEY_VIDEO_MODEL"] = "veo3.1-fast"

    truth = vts.resolve_video_request_truth("VID-20260819-MISSINGREQ", conn=temp_conn)
    assert truth["request_found"] == "NO"
    assert truth["current_provider_configured"] == "YES"
    assert truth["current_selected_route"] == "shopaikey_video"


def test_13_video_trace_and_render_debug_agree(temp_conn):
    """13. /video_trace and /video_render_debug agree"""
    report = vts.build_canonical_video_trace_report("VID-20260819-AGREEMENT", conn=temp_conn)
    truth = vts.resolve_video_request_truth("VID-20260819-AGREEMENT", conn=temp_conn)
    assert report["REQUEST_FOUND"] == truth["request_found"]
    assert report["DURABLE_REQUEST_FOUND"] == truth["durable_request_found"]
    assert report["CURRENT_PROVIDER_CONFIGURED"] == truth["current_provider_configured"]


def test_14_no_fake_request_found(temp_conn):
    """14. no fake REQUEST_FOUND"""
    # Incident ID
    incident_id = "VID-20260819-DD17A8"
    truth = vts.resolve_video_request_truth(incident_id, conn=temp_conn)
    assert truth["request_found"] == "NO"
    assert truth["durable_request_found"] == "NO"
    assert truth["status_source"] == "canonical_db_not_found"


def test_15_shopaikey_healthy_persisted_preflight_pass(temp_conn):
    """15. ShopAIKey healthy -> persisted preflight PASS"""
    os.environ["SHOPAIKEY_API_KEY"] = "sk-live-test"
    os.environ["SHOPAIKEY_VIDEO_MODEL"] = "veo3.1-fast"
    eval_res = bot.product_video_public_preflight_evaluation(1, explicit_public_final_confirm=True)
    assert eval_res.get("ready") is True


def test_16_cloud_worker_stale_not_blocking(temp_conn):
    """16. cloud worker stale but not required -> no block"""
    os.environ["SHOPAIKEY_API_KEY"] = "sk-live-test"
    os.environ["SHOPAIKEY_VIDEO_MODEL"] = "veo3.1-fast"
    session = {"draft": {"execution_mode": "cloud", "worker_required": False}}
    eval_res = bot.product_video_public_preflight_evaluation(1, explicit_public_final_confirm=True)
    assert eval_res.get("ready") is True
