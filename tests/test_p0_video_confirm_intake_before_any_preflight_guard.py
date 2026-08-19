import sqlite3
import pytest
from services import video_trace_state as vts
from services import video_project_queue as queue


@pytest.fixture
def temp_conn(tmp_path):
    db_path = str(tmp_path / "test_intake.db")
    conn = sqlite3.connect(db_path)
    vts.ensure_video_trace_schema(conn)
    queue.ensure_video_project_queue_schema(conn)
    yield conn
    conn.close()


def test_1_confirm_allocates_request_before_scene_guard(temp_conn):
    session = {"draft": {"b14_scene_count": 999}}
    res = vts.begin_video_confirm_attempt(session, user_id=12345, conn=temp_conn)
    assert res["ok"] is True
    assert res["request_id"].startswith("VID-")
    trace = vts.lookup_video_request_trace(res["request_id"], conn=temp_conn)
    assert trace is not None
    assert trace["current_stage"] == vts.STAGE_REQUEST_RECEIVED


def test_2_confirm_allocates_request_before_trial_guard(temp_conn):
    session = {"draft": {"b14_is_trial": True}}
    res = vts.begin_video_confirm_attempt(session, user_id=12345, conn=temp_conn)
    assert res["ok"] is True
    assert res["request_id"].startswith("VID-")


def test_3_confirm_allocates_request_before_probation_guard(temp_conn):
    session = {"draft": {}}
    res = vts.begin_video_confirm_attempt(session, user_id=12345, conn=temp_conn)
    assert res["ok"] is True
    trace = vts.lookup_video_request_trace(res["request_id"], conn=temp_conn)
    assert trace is not None


def test_4_confirm_allocates_request_before_provider_readiness(temp_conn):
    session = {"draft": {}}
    res = vts.begin_video_confirm_attempt(session, user_id=12345, conn=temp_conn)
    assert res["ok"] is True
    assert res["durable_persisted"] is True


def test_5_confirm_allocates_request_before_preflight(temp_conn):
    session = {"draft": {}}
    res = vts.begin_video_confirm_attempt(session, user_id=12345, conn=temp_conn)
    assert res["ok"] is True
    trace = vts.lookup_video_request_trace(res["request_id"], conn=temp_conn)
    assert trace["current_stage"] == vts.STAGE_REQUEST_RECEIVED


def test_6_blocked_preflight_still_has_durable_request_id(temp_conn):
    session = {"draft": {}}
    res = vts.begin_video_confirm_attempt(session, user_id=12345, conn=temp_conn)
    req_id = res["request_id"]
    updated = vts.record_video_trace_event(
        res["session"],
        vts.STAGE_ADMISSION_BLOCKED,
        user_id=12345,
        blocker_code="provider_unavailable",
        conn=temp_conn,
    )
    trace = vts.lookup_video_request_trace(req_id, conn=temp_conn)
    assert trace is not None
    assert trace["request_id"] == req_id
    assert trace["current_stage"] == vts.STAGE_ADMISSION_BLOCKED
    assert trace["internal_blocker_code"] == "provider_unavailable"
    assert trace["job_id"] is None


def test_7_no_job_status_still_shows_durable_request_id(temp_conn):
    from bot import video_b14_queue_status_text
    session = {"draft": {"request_id": "VID-20260819-A1B2C3", "b14_submit_attempted": True, "b14_queue_job_id": 0}}
    vts.record_video_trace_event(
        session,
        vts.STAGE_REQUEST_RECEIVED,
        user_id=12345,
        conn=temp_conn,
    )
    vts.record_video_trace_event(
        session,
        vts.STAGE_ADMISSION_BLOCKED,
        user_id=12345,
        blocker_code="test_blocker",
        conn=temp_conn,
    )
    text = video_b14_queue_status_text(session, None, 12345, "vi")
    assert "VID-20260819-A1B2C3" in text
    assert "Chưa tạo" in text


def test_8_renderer_never_allocates_request():
    from bot import video_b14_queue_status_text
    empty_session = {"draft": {}}
    text = video_b14_queue_status_text(empty_session, None, 12345, "vi")
    assert "Mã yêu cầu:" not in text
    assert "Chưa tạo" in text


def test_9_intake_readback_failure_stops_execution(temp_conn):
    # Mocking broken DB connection
    class BrokenConn:
        def cursor(self):
            raise sqlite3.OperationalError("disk I/O error")
        def execute(self, *args, **kwargs):
            raise sqlite3.OperationalError("disk I/O error")
    
    res = vts.begin_video_confirm_attempt({"draft": {}}, user_id=12345, conn=BrokenConn())
    assert res["ok"] is False
    assert res["reason"] == "trace_persistence_failed"


def test_10_provider_healthy_and_admission_pass_creates_job(temp_conn):
    session = {"draft": {}}
    res = vts.begin_video_confirm_attempt(session, user_id=12345, conn=temp_conn)
    req_id = res["request_id"]
    
    # Simulate job creation
    job_id = 998877
    vts.record_video_trace_event(
        res["session"],
        vts.STAGE_JOB_CREATED,
        job_id=job_id,
        user_id=12345,
        conn=temp_conn,
    )
    trace = vts.lookup_video_request_trace(req_id, conn=temp_conn)
    assert trace is not None
    assert trace["job_id"] == job_id
    assert trace["current_stage"] == vts.STAGE_JOB_CREATED


def test_11_request_to_job_link_persisted(temp_conn):
    session = {"draft": {}}
    res = vts.begin_video_confirm_attempt(session, user_id=12345, conn=temp_conn)
    req_id = res["request_id"]
    job_id = 123456
    vts.record_video_trace_event(res["session"], vts.STAGE_JOB_CREATED, job_id=job_id, conn=temp_conn)
    trace = vts.lookup_video_request_trace(req_id, conn=temp_conn)
    assert trace["job_id"] == job_id


def test_12_job_create_failure_explicit(temp_conn):
    session = {"draft": {}}
    res = vts.begin_video_confirm_attempt(session, user_id=12345, conn=temp_conn)
    req_id = res["request_id"]
    vts.record_video_trace_event(
        res["session"],
        vts.STAGE_ADMISSION_BLOCKED,
        user_id=12345,
        blocker_code="job_create_failed",
        conn=temp_conn,
    )
    trace = vts.lookup_video_request_trace(req_id, conn=temp_conn)
    assert trace["internal_blocker_code"] == "job_create_failed"
    assert trace["job_id"] is None


def test_13_duplicate_confirm_one_request(temp_conn):
    session = {"draft": {}}
    res1 = vts.begin_video_confirm_attempt(session, user_id=12345, conn=temp_conn)
    session["draft"]["request_id"] = res1["request_id"]
    res2 = vts.begin_video_confirm_attempt(session, user_id=12345, conn=temp_conn)
    assert res1["request_id"] == res2["request_id"]
    rows = temp_conn.execute("SELECT COUNT(*) FROM video_request_traces WHERE request_id = ?", (res1["request_id"],)).fetchone()[0]
    assert rows == 1


def test_14_duplicate_confirm_one_job(temp_conn):
    session = {"draft": {}}
    res = vts.begin_video_confirm_attempt(session, user_id=12345, conn=temp_conn)
    req_id = res["request_id"]
    job_id = 456789
    vts.record_video_trace_event(res["session"], vts.STAGE_JOB_CREATED, job_id=job_id, conn=temp_conn)
    vts.record_video_trace_event(res["session"], vts.STAGE_JOB_CREATED, job_id=job_id, conn=temp_conn)
    trace = vts.lookup_video_request_trace(req_id, conn=temp_conn)
    assert trace["job_id"] == job_id
    rows = temp_conn.execute("SELECT COUNT(*) FROM video_request_traces WHERE request_id = ?", (req_id,)).fetchone()[0]
    assert rows == 1


def test_15_zero_paid_stop_happens_after_job_created(temp_conn):
    session = {"draft": {}}
    res = vts.begin_video_confirm_attempt(session, user_id=12345, conn=temp_conn)
    req_id = res["request_id"]
    job_id = 888888
    vts.record_video_trace_event(res["session"], vts.STAGE_JOB_CREATED, job_id=job_id, conn=temp_conn)
    trace = vts.lookup_video_request_trace(req_id, conn=temp_conn)
    report = vts.build_canonical_video_trace_report(req_id, conn=temp_conn)
    assert trace["current_stage"] == vts.STAGE_JOB_CREATED
    assert trace["provider_task_id"] is None
    assert report["CHARGE_STATE"] == "NO_CHARGE"


def test_16_no_provider_calls(temp_conn):
    session = {"draft": {}}
    res = vts.begin_video_confirm_attempt(session, user_id=12345, conn=temp_conn)
    req_id = res["request_id"]
    trace = vts.lookup_video_request_trace(req_id, conn=temp_conn)
    assert trace["provider_task_id"] is None


def test_17_no_charge(temp_conn):
    session = {"draft": {}}
    res = vts.begin_video_confirm_attempt(session, user_id=12345, conn=temp_conn)
    req_id = res["request_id"]
    report = vts.build_canonical_video_trace_report(req_id, conn=temp_conn)
    assert report["CHARGE_STATE"] == "NO_CHARGE"
