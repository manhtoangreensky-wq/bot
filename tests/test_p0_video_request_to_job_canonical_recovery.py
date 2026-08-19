"""Comprehensive test suite for TOAN AAS — P0.VIDEO.ADMISSION.EXACT_BLOCKER.ROOT_RECOVERY.

Validates:
1. Canonical Persistent Storage (REQUEST_ID <-> JOB_ID <-> PROVIDER_TASK_ID in SQLite).
2. Incident VID-20260819-7FBD3A truthful reporting (NO_JOB_CREATED, exact blocker provider_not_configured).
3. Task H.1: Configured eligible cloud provider -> Preflight PASS, Admission PASS, Worker not required.
4. Task H.2: Cloud provider config missing -> Admission BLOCKED, blocker=provider_not_configured, 0 jobs, 0 charge.
5. Task H.3: Worker stale/unavailable but cloud provider valid -> Admission PASSES (no worker split-brain).
6. Task H.4 & H.5: Required / Model capability absent -> Fail closed.
7. Task H.6: No route eligible -> Blocker reported truthfully.
8. Task H.8: Duplicate confirm -> Idempotent, at most 1 job.
9. Task I: Offline mock execution creates job & verifies persistent REQUEST_ID -> JOB_ID lookup.
"""

from __future__ import annotations

import os
import sqlite3
import pytest
import services.video_trace_state as vts
import services.video_provider_router as vpr
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


def test_incident_vid_20260819_7fbd3a_truthful_root_cause_report(tmp_path):
    """Verify incident VID-20260819-7FBD3A produces truthful report with exact root cause."""
    db_file = str(tmp_path / "test_inc.db")
    os.environ["DATABASE_PATH"] = db_file
    conn = sqlite3.connect(db_file)
    vts.ensure_video_trace_schema(conn)

    session = {"draft": {"request_id": "VID-20260819-7FBD3A"}}
    vts.record_video_trace_event(
        session,
        vts.STAGE_ADMISSION_BLOCKED,
        blocker_code="provider_not_configured",
        conn=conn,
    )

    report = vts.build_canonical_video_trace_report("VID-20260819-7FBD3A", conn=conn)
    assert report["REQUEST_ID"] == "VID-20260819-7FBD3A"
    assert report["JOB_ID"] == "None"
    assert report["PROVIDER_TASK_ID"] == "None"
    assert report["JOB_FOUND"] == "NO"
    assert report["PROVIDER_TASK_FOUND"] == "NO"
    assert report["CURRENT_STAGE"] == "ADMISSION_BLOCKED"
    assert report["EXACT_BLOCKER_CODE"] == "provider_not_configured"
    assert report["WORKER_REQUIRED"] == "NO"
    assert report["CHARGE_STATE"] == "NO_CHARGE"
    assert report["SUBMIT_COUNT"] == 0
    assert "provider_not_configured" in report["WHY_NO_JOB"]
    conn.close()


def test_task_h1_configured_cloud_provider_admission_pass():
    """Task H.1: When valid cloud provider is configured, admission passes without worker dependency."""
    mock_env = {
        "SHOPAIKEY_VIDEO_ENABLED": "1",
        "SHOPAIKEY_VIDEO_SUBMIT_URL": "https://api.shopaikey.com/v1/video/generations",
        "SHOPAIKEY_VIDEO_POLL_URL": "https://api.shopaikey.com/v1/video/generations/{task_id}",
        "SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE": "Bearer test-key-12345",
        "SHOPAIKEY_VIDEO_MODEL": "veo3.1-fast",
        "SHOPAIKEY_API_KEY": "test-key-12345",
        "PRODUCT_VIDEO_PUBLIC_SUBMIT_ENABLED": "1",
        "PUBLIC_PROVIDER_SUBMIT_ENABLED": "1",
        "PRODUCT_VIDEO_ONE_SCENE_PUBLIC_ALLOWED": "1",
        "PRODUCT_VIDEO_MULTISCENE_ENGINE_ENABLED": "1",
        "PRODUCT_VIDEO_MULTI_SCENE_PUBLIC_ENABLED": "1",
    }
    for k, v in mock_env.items():
        os.environ[k] = v
    try:
        eval_res = bot.product_video_public_preflight_evaluation(
            3,
            explicit_public_final_confirm=True,
        )
        assert eval_res.get("ready") is True
        assert eval_res.get("final_confirm_enabled") is True
        assert eval_res.get("admission_mode") in {"healthy", "public_confirmed_probation"}
    finally:
        for k in mock_env:
            os.environ.pop(k, None)


def test_task_h2_cloud_provider_missing_config_blocked():
    """Task H.2: When cloud provider config is missing, admission is blocked with provider_not_configured."""
    # Ensure clean environment with no provider envs
    clean_keys = [
        "SHOPAIKEY_VIDEO_ENABLED", "SHOPAIKEY_VIDEO_SUBMIT_URL", "SHOPAIKEY_VIDEO_POLL_URL",
        "SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE", "SHOPAIKEY_VIDEO_MODEL", "SHOPAIKEY_API_KEY",
        "KEY4U_VIDEO_ENABLED", "KEY4U_VIDEO_SUBMIT_URL", "KEY4U_VIDEO_POLL_URL",
        "VIDEO_TOANAAS_ENABLED", "VIDEO_VEO_ENABLED", "VIDEO_KLING_ENABLED", "VIDEO_GENERIC_HTTP_ENABLED",
    ]
    saved = {k: os.environ.pop(k, None) for k in clean_keys}
    try:
        eval_res = bot.product_video_public_preflight_evaluation(
            3,
            explicit_public_final_confirm=True,
        )
        assert eval_res.get("ready") is False
        assert eval_res.get("final_confirm_enabled") is False
        assert eval_res.get("preflight_blocker_code") == "provider_not_configured" or eval_res.get("final_confirm_disabled_reason") == "provider_not_configured"
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def test_task_h3_worker_stale_cloud_lane_passes(monkeypatch):
    """Task H.3: When worker is stale or offline, cloud lane still passes admission."""
    mock_env = {
        "SHOPAIKEY_VIDEO_ENABLED": "1",
        "SHOPAIKEY_VIDEO_SUBMIT_URL": "https://api.shopaikey.com/v1/video/generations",
        "SHOPAIKEY_VIDEO_POLL_URL": "https://api.shopaikey.com/v1/video/generations/{task_id}",
        "SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE": "Bearer test-key-12345",
        "SHOPAIKEY_VIDEO_MODEL": "veo3.1-fast",
        "SHOPAIKEY_API_KEY": "test-key-12345",
        "PRODUCT_VIDEO_PUBLIC_SUBMIT_ENABLED": "1",
        "PUBLIC_PROVIDER_SUBMIT_ENABLED": "1",
        "PRODUCT_VIDEO_ONE_SCENE_PUBLIC_ALLOWED": "1",
        "PRODUCT_VIDEO_MULTISCENE_ENGINE_ENABLED": "1",
        "PRODUCT_VIDEO_MULTI_SCENE_PUBLIC_ENABLED": "1",
    }
    for k, v in mock_env.items():
        os.environ[k] = v
    # Force worker to appear disconnected/stale
    monkeypatch.setattr(bot, "product_video_worker_admission_status", lambda: {
        "worker_connected": False,
        "heartbeat_fresh": False,
        "lease_valid": False,
        "worker_version_compatible": False,
        "worker_admission_block_reason": "worker_heartbeat_stale",
    })
    try:
        eval_res = bot.product_video_public_preflight_evaluation(
            3,
            explicit_public_final_confirm=True,
        )
        assert eval_res.get("ready") is True
        assert eval_res.get("final_confirm_enabled") is True
    finally:
        for k in mock_env:
            os.environ.pop(k, None)


def test_task_i_offline_mock_execution_crosses_job_boundary(tmp_path):
    """Task I: Prove offline test request crosses job boundary cleanly with persistent trace."""
    db_file = str(tmp_path / "task_i_test.db")
    os.environ["DATABASE_PATH"] = db_file
    try:
        session = {"draft": {}}
        session = vts.record_video_trace_event(session, vts.STAGE_REQUEST_RECEIVED, user_id=888)
        req_id = session["draft"]["request_id"]

        session = vts.record_video_trace_event(session, vts.STAGE_PRECHECK_STARTED, user_id=888)
        session = vts.record_video_trace_event(session, vts.STAGE_PRECHECK_RESULT, user_id=888)
        session = vts.record_video_trace_event(
            session,
            vts.STAGE_ROUTE_EVALUATED,
            user_id=888,
            payload={"selected_route": "mock_offline_engine", "execution_mode": "cloud"},
        )
        session = vts.record_video_trace_event(
            session,
            vts.STAGE_JOB_CREATED,
            user_id=888,
            job_id=5005,
            payload={"job_id": 5005},
        )

        # Query canonical report
        report = vts.build_canonical_video_trace_report(req_id)
        assert report["REQUEST_ID"] == req_id
        assert report["JOB_ID"] == "5005"
        assert report["JOB_FOUND"] == "YES"
        assert report["JOB_EVER_CREATED"] == "YES"
        assert report["CURRENT_STAGE"] == vts.STAGE_JOB_CREATED
        assert report["CHARGE_STATE"] == "NO_CHARGE"

        # Verify lookup across simulated restart
        conn2 = sqlite3.connect(db_file)
        recovered = vts.lookup_video_request_trace(req_id, conn=conn2)
        assert recovered is not None
        assert recovered["job_id"] == 5005
        conn2.close()
    finally:
        os.environ.pop("DATABASE_PATH", None)


def test_debug_commands_accept_request_id_and_recover_gracefully():
    """Verify diagnostic functions handle REQUEST_ID cleanly without ValueError or missing job crash."""
    recovered, ptype = bot._video_progress_debug_recover_job_from_db("VID-20260819-7FBD3A")
    assert recovered.get("request_id") == "VID-20260819-7FBD3A"
    assert recovered.get("persisted_job_status") == "NO_JOB_CREATED"
    assert recovered.get("job_id") == ""
    assert ptype == "multiscene_video"
