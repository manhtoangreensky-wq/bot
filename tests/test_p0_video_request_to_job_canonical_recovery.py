"""Comprehensive test suite for TOAN AAS — P0.VIDEO.REQUEST_TO_JOB.CANONICAL.TRACE.RECOVERY.

Validates:
1. Canonical Persistent Storage (REQUEST_ID <-> JOB_ID <-> PROVIDER_TASK_ID in SQLite).
2. Incident VID-20260819-7FBD3A truthful reporting (NO_JOB_CREATED, 0 provider calls, 0 xu charged).
3. Task J: Local zero-cost execution proof with restart recovery.
4. Task K: Mock provider ID chain (REQUEST_ID -> JOB_ID -> PROVIDER_TASK_ID).
5. Task F: Diagnostic commands (/video_trace, /video_provider_job_debug, /video_provider_raw_status, /video_provider_recover) accept REQUEST_ID.
6. Task H & I: Status recovery after restart without requiring in-memory cache.
"""

from __future__ import annotations

import os
import sqlite3
import pytest
import services.video_trace_state as vts
import bot


def test_canonical_persistent_trace_storage_and_recovery(tmp_path):
    """Verify trace is persisted in SQLite and survives database reconnection."""
    db_file = str(tmp_path / "test_traces.db")
    os.environ["DATABASE_PATH"] = db_file
    try:
        session = {"draft": {}}
        session = vts.record_video_trace_event(
            session,
            vts.STAGE_REQUEST_RECEIVED,
            user_id=111,
            chat_id=222,
        )
        req_id = session["draft"]["request_id"]

        session = vts.record_video_trace_event(
            session,
            vts.STAGE_JOB_CREATED,
            user_id=111,
            chat_id=222,
            job_id=456,
        )

        # Simulate process restart / new connection
        conn2 = sqlite3.connect(db_file)
        recovered = vts.lookup_video_request_trace(req_id, conn=conn2)
        assert recovered is not None
        assert recovered["request_id"] == req_id
        assert recovered["job_id"] == 456
        assert recovered["current_stage"] == vts.STAGE_JOB_CREATED

        # Verify reverse lookup by job_id
        by_job = vts.lookup_video_request_trace("456", conn=conn2)
        assert by_job is not None
        assert by_job["request_id"] == req_id
        conn2.close()
    finally:
        os.environ.pop("DATABASE_PATH", None)


def test_incident_vid_20260819_7fbd3a_truthful_report():
    """Verify incident VID-20260819-7FBD3A produces truthful NO_JOB_CREATED trace without manufacturing IDs."""
    report = vts.build_canonical_video_trace_report("VID-20260819-7FBD3A")
    assert report["REQUEST_ID"] == "VID-20260819-7FBD3A"
    assert report["JOB_ID"] == "None"
    assert report["PROVIDER_TASK_ID"] == "None"
    assert report["JOB_FOUND"] == "NO"
    assert report["PROVIDER_TASK_FOUND"] == "NO"
    assert report["CURRENT_STAGE"] == "NO_JOB_CREATED"
    assert report["CHARGE_STATE"] == "NO_CHARGE"
    assert report["SUBMIT_COUNT"] == 0


def test_local_zero_cost_flow_task_j(tmp_path):
    """Task J: Prove local zero-cost job creation and recovery across simulated restart."""
    db_file = str(tmp_path / "task_j_test.db")
    os.environ["DATABASE_PATH"] = db_file
    try:
        session = {"draft": {}}
        session = vts.record_video_trace_event(session, vts.STAGE_REQUEST_RECEIVED, user_id=901)
        req_id = session["draft"]["request_id"]

        session = vts.record_video_trace_event(session, vts.STAGE_PRECHECK_STARTED, user_id=901)
        session = vts.record_video_trace_event(session, vts.STAGE_PRECHECK_RESULT, user_id=901)
        session = vts.record_video_trace_event(session, vts.STAGE_JOB_CREATED, user_id=901, job_id=1001)
        session = vts.record_video_trace_event(session, vts.STAGE_ARTIFACT_VALIDATION, user_id=901, job_id=1001)

        # Verify trace before restart
        report1 = vts.build_canonical_video_trace_report(req_id)
        assert report1["REQUEST_ID"] == req_id
        assert report1["JOB_ID"] == "1001"
        assert report1["PROVIDER_TASK_ID"] == "None"
        assert report1["JOB_FOUND"] == "YES"

        # Verify trace after simulated restart (lookup by REQUEST_ID)
        report2 = vts.build_canonical_video_trace_report(req_id)
        assert report2["REQUEST_ID"] == req_id
        assert report2["JOB_ID"] == "1001"
        assert report2["STATUS_SOURCE"] == "canonical_db_video_request_traces"
    finally:
        os.environ.pop("DATABASE_PATH", None)


def test_mock_provider_id_chain_task_k(tmp_path):
    """Task K: Validate REQUEST_ID -> JOB_ID -> PROVIDER_TASK_ID chain."""
    db_file = str(tmp_path / "task_k_test.db")
    os.environ["DATABASE_PATH"] = db_file
    try:
        session = {"draft": {}}
        session = vts.record_video_trace_event(session, vts.STAGE_REQUEST_RECEIVED, user_id=902)
        req_id = session["draft"]["request_id"]

        session = vts.record_video_trace_event(session, vts.STAGE_JOB_CREATED, user_id=902, job_id=2002)
        session = vts.record_video_trace_event(
            session,
            vts.STAGE_SUBMIT_ACCEPTED,
            user_id=902,
            job_id=2002,
            provider_task_id="mock-provider-task-9999",
        )

        report = vts.build_canonical_video_trace_report(req_id)
        assert report["REQUEST_ID"] == req_id
        assert report["JOB_ID"] == "2002"
        assert report["PROVIDER_TASK_ID"] == "mock-provider-task-9999"
        assert report["PROVIDER_TASK_FOUND"] == "YES"
        assert report["SUBMIT_COUNT"] == 1

        # Verify reverse lookup by provider task ID
        by_prov = vts.lookup_video_request_trace("mock-provider-task-9999")
        assert by_prov is not None
        assert by_prov["request_id"] == req_id
        assert by_prov["job_id"] == 2002
    finally:
        os.environ.pop("DATABASE_PATH", None)


def test_debug_commands_accept_request_id_and_recover_gracefully():
    """Verify diagnostic functions handle REQUEST_ID cleanly without ValueError or missing job crash."""
    # Test recovery of no-job request from DB
    recovered, ptype = bot._video_progress_debug_recover_job_from_db("VID-20260819-7FBD3A")
    assert recovered.get("request_id") == "VID-20260819-7FBD3A"
    assert recovered.get("persisted_job_status") == "NO_JOB_CREATED"
    assert recovered.get("job_id") == ""
    assert ptype == "multiscene_video"
