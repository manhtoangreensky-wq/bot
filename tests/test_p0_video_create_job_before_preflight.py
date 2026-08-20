import hashlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import video_project_queue as queue
from services import video_trace_state as trace_state


USER_ID = 71001
CHAT_ID = 71002
ATTEMPT_KEY = "video-confirm:71001:project:invoice-attestation"
BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def _confirm_handler_block() -> str:
    start = BOT_SOURCE.index('    if action == "b14_confirm":')
    end = BOT_SOURCE.index('    if action == "b14_job_status":', start)
    return BOT_SOURCE[start:end]


def _status_step_rows_function():
    labels_start = BOT_SOURCE.index("VIDEO_B14_STATUS_STEP_LABELS = (")
    labels_end = BOT_SOURCE.index("\n)\n", labels_start) + 3
    function_start = BOT_SOURCE.index("def video_b14_status_step_rows(")
    function_end = BOT_SOURCE.index("\n\ndef video_b14_status_steps_text(", function_start)
    namespace = {
        "safe_int": lambda value, default=0: int(value or default),
        "video_project_queue": SimpleNamespace(
            VIDEO_JOB_PRECHECK_RUNNING=queue.VIDEO_JOB_PRECHECK_RUNNING,
            VIDEO_JOB_PRECHECK_BLOCKED=queue.VIDEO_JOB_PRECHECK_BLOCKED,
            VIDEO_JOB_READY_TO_SUBMIT=queue.VIDEO_JOB_READY_TO_SUBMIT,
        ),
        "VIDEO_B14_SELFSHOT_STATUS_STEP_LABELS": {},
    }
    exec(BOT_SOURCE[labels_start:labels_end], namespace)
    exec(BOT_SOURCE[function_start:function_end], namespace)
    return namespace["video_b14_status_step_rows"]


def _source_block(start_marker: str, end_marker: str) -> str:
    start = BOT_SOURCE.index(start_marker)
    end = BOT_SOURCE.index(end_marker, start)
    return BOT_SOURCE[start:end]


def _idempotency_key_function():
    block = _source_block(
        "def video_confirm_execution_idempotency_key(",
        "\n\ndef video_uiflow3_update_invoice_message_id(",
    )
    namespace = {
        "hashlib": hashlib,
        "json": json,
        "safe_int": lambda value, default=0: int(value or default),
    }
    exec(block, namespace)
    return namespace["video_confirm_execution_idempotency_key"]


@pytest.fixture
def confirm_db(tmp_path):
    db_path = tmp_path / "video_confirm.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    trace_state.ensure_video_trace_schema(conn)
    queue.ensure_video_project_queue_schema(conn)
    project = queue.create_video_project(
        conn,
        user_id=USER_ID,
        profile_id="storytelling",
        topic="video confirm intake",
        ratio="9:16",
        asset_pack={"source": "product_video", "render_mode": "real"},
    )
    project = queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="draft_invoice",
        invoice_json={
            "source": "product_video",
            "render_mode": "real",
            "scene_count": 1,
            "duration_seconds": 8,
            "total_xu": 80,
        },
        scene_count=1,
        total_xu_estimated=80,
    )
    yield conn, str(db_path), project
    conn.close()


def _begin(conn, project, session=None):
    return trace_state.begin_video_confirm_execution(
        session or {"draft": {}},
        user_id=USER_ID,
        chat_id=CHAT_ID,
        project_id=int(project["project_id"]),
        idempotency_key=ATTEMPT_KEY,
        payload={"scene_count": 1, "seconds_per_scene": 8, "unit_xu": 80},
        conn=conn,
    )


def test_valid_confirm_atomically_creates_real_request_and_internal_job(confirm_db):
    conn, _db_path, project = confirm_db

    result = _begin(conn, project)

    assert result["ok"] is True
    assert result["request_id"].startswith("VID-")
    assert result["job_id"] > 0
    trace_row = conn.execute(
        "SELECT request_id, job_id, project_id, confirm_attempt_key, current_stage "
        "FROM video_request_traces WHERE request_id=?",
        (result["request_id"],),
    ).fetchone()
    job_row = conn.execute(
        "SELECT id, project_id, user_id, status, result_json FROM video_jobs WHERE id=?",
        (result["job_id"],),
    ).fetchone()
    project_row = conn.execute(
        "SELECT job_id, is_confirmed, status FROM video_projects WHERE project_id=?",
        (int(project["project_id"]),),
    ).fetchone()

    assert trace_row["job_id"] == result["job_id"]
    assert trace_row["project_id"] == int(project["project_id"])
    assert trace_row["confirm_attempt_key"] == ATTEMPT_KEY
    assert trace_row["current_stage"] == trace_state.STAGE_JOB_CREATED
    assert job_row["id"] == result["job_id"]
    assert job_row["project_id"] == int(project["project_id"])
    assert job_row["user_id"] == USER_ID
    assert job_row["status"] == "precheck_running"
    assert project_row["job_id"] == result["job_id"]
    assert project_row["is_confirmed"] == 0
    assert project_row["status"] == "draft_invoice"

    job_payload = json.loads(job_row["result_json"])
    assert job_payload["request_id"] == result["request_id"]
    assert job_payload["confirm_attempt_key"] == ATTEMPT_KEY
    assert job_payload["chat_id"] == CHAT_ID
    assert job_payload["provider_task_id"] is None
    assert job_payload["submit_count"] == 0
    assert job_payload["poll_count"] == 0
    assert job_payload["charge_count"] == 0
    assert conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox").fetchone()[0] == 0


def test_duplicate_confirm_and_session_restart_resume_exactly_one_job(confirm_db):
    conn, _db_path, project = confirm_db
    first = _begin(conn, project)

    duplicate = _begin(conn, project, session={"draft": {}})

    assert duplicate["ok"] is True
    assert duplicate["duplicate_prevented"] is True
    assert duplicate["request_id"] == first["request_id"]
    assert duplicate["job_id"] == first["job_id"]
    assert conn.execute(
        "SELECT COUNT(*) FROM video_request_traces WHERE confirm_attempt_key=?",
        (ATTEMPT_KEY,),
    ).fetchone()[0] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM video_jobs WHERE project_id=?",
        (int(project["project_id"]),),
    ).fetchone()[0] == 1


def test_duplicate_confirm_preserves_blocked_and_ready_trace_state(confirm_db):
    conn, _db_path, project = confirm_db
    started = _begin(conn, project)
    blocked = trace_state.record_video_confirm_precheck_result(
        started["session"],
        user_id=USER_ID,
        chat_id=CHAT_ID,
        job_id=started["job_id"],
        preflight_result="BLOCKED",
        admission_result="NOT_RUN",
        blocker_code="provider_unavailable",
        conn=conn,
    )

    duplicate_blocked = _begin(conn, project, session={"draft": {}})
    blocked_trace = trace_state.lookup_video_request_trace(started["request_id"], conn=conn)

    assert duplicate_blocked["job_id"] == started["job_id"]
    assert duplicate_blocked["duplicate_prevented"] is True
    assert blocked_trace["current_stage"] == trace_state.STAGE_PREFLIGHT_BLOCKED
    assert blocked_trace["preflight_result"] == "BLOCKED"
    assert blocked_trace["admission_result"] == "NOT_RUN"
    assert blocked_trace["internal_blocker_code"] == "provider_unavailable"

    ready = trace_state.record_video_confirm_precheck_result(
        blocked["session"],
        user_id=USER_ID,
        chat_id=CHAT_ID,
        job_id=started["job_id"],
        preflight_result="PASS",
        admission_result="PASS",
        blocker_code="",
        conn=conn,
    )
    duplicate_ready = _begin(conn, project, session={"draft": {}})
    ready_trace = trace_state.lookup_video_request_trace(started["request_id"], conn=conn)

    assert ready["job"]["status"] == queue.VIDEO_JOB_READY_TO_SUBMIT
    assert duplicate_ready["job_id"] == started["job_id"]
    assert duplicate_ready["duplicate_prevented"] is True
    assert ready_trace["current_stage"] == trace_state.STAGE_READY_TO_SUBMIT
    assert ready_trace["preflight_result"] == "PASS"
    assert ready_trace["admission_result"] == "PASS"
    assert ready_trace["internal_blocker_code"] is None


def test_blocked_precheck_keeps_same_job_and_zero_side_effects(confirm_db):
    conn, _db_path, project = confirm_db
    started = _begin(conn, project)

    blocked = trace_state.record_video_confirm_precheck_result(
        started["session"],
        user_id=USER_ID,
        chat_id=CHAT_ID,
        job_id=started["job_id"],
        preflight_result="BLOCKED",
        admission_result="NOT_RUN",
        blocker_code="provider_unavailable",
        conn=conn,
    )

    assert blocked["ok"] is True
    assert blocked["request_id"] == started["request_id"]
    assert blocked["job_id"] == started["job_id"]
    assert blocked["job"]["status"] == "precheck_blocked"
    trace = trace_state.lookup_video_request_trace(started["request_id"], conn=conn)
    assert trace["job_id"] == started["job_id"]
    assert trace["internal_blocker_code"] == "provider_unavailable"
    payload = json.loads(blocked["job"]["result_json"])
    assert payload["chat_id"] == CHAT_ID
    assert payload["provider_task_id"] is None
    assert payload["submit_count"] == 0
    assert payload["poll_count"] == 0
    assert payload["charge_count"] == 0
    assert conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox").fetchone()[0] == 0


def test_passed_precheck_stops_at_ready_to_submit_without_outbox(confirm_db):
    conn, _db_path, project = confirm_db
    started = _begin(conn, project)

    ready = trace_state.record_video_confirm_precheck_result(
        started["session"],
        user_id=USER_ID,
        chat_id=CHAT_ID,
        job_id=started["job_id"],
        preflight_result="PASS",
        admission_result="PASS",
        blocker_code="",
        conn=conn,
    )

    assert ready["ok"] is True
    assert ready["job_id"] == started["job_id"]
    assert ready["job"]["status"] == "ready_to_submit"
    payload = json.loads(ready["job"]["result_json"])
    assert payload["chat_id"] == CHAT_ID
    assert payload["preflight_result"] == "PASS"
    assert payload["admission_result"] == "PASS"
    assert payload["provider_task_id"] is None
    assert payload["submit_count"] == 0
    assert payload["charge_count"] == 0
    assert conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox").fetchone()[0] == 0


def test_public_confirm_orders_identity_then_job_then_preflight():
    block = _confirm_handler_block()

    identity_guard = block.index("confirmation_guard = video_uiflow3_validate_invoice_confirmation")
    intake = block.index("video_trace_state.begin_video_confirm_execution")
    provider_preflight = block.index("product_video_public_preflight_evaluation")

    assert identity_guard < intake < provider_preflight
    assert "video_trace_state.begin_video_confirm_attempt" not in block
    assert "TOAN AAS chưa tạo tác vụ" not in block[intake:]


def test_confirm_readback_failure_with_real_job_never_renders_no_job_status():
    block = _confirm_handler_block()
    failure_start = block.index('if not intake_result.get("ok"):')
    failure_end = block.index("save_video_session(uid, session)", failure_start)
    failure_branch = block[failure_start:failure_end]

    assert "video_uiflow3_prepare_existing_job_precheck_status" in failure_branch
    assert failure_branch.index("video_uiflow3_prepare_existing_job_precheck_status") < failure_branch.index(
        "video_uiflow3_prepare_no_job_status"
    )


def test_provider_blocked_updates_existing_job_instead_of_no_job_status():
    block = _confirm_handler_block()
    blocked_start = block.index("if not admission_evaluation.get(\"ready\"):")
    blocked_end = block.index("provider_preflight =", blocked_start)
    blocked_branch = block[blocked_start:blocked_end]

    assert "video_uiflow3_prepare_existing_job_precheck_status" in blocked_branch
    assert "video_uiflow3_prepare_no_job_status" not in blocked_branch
    assert blocked_branch.index("video_uiflow3_prepare_existing_job_precheck_status") < blocked_branch.index(
        "if is_uiflow3_confirmation:"
    )


def test_missing_scene_count_blocks_existing_job_before_product_specific_render():
    block = _confirm_handler_block()
    blocked_start = block.index('if not draft.get("b14_scene_count_selected"):')
    blocked_end = block.index("project_id = safe_int", blocked_start)
    blocked_branch = block[blocked_start:blocked_end]

    assert "video_uiflow3_prepare_existing_job_precheck_status" in blocked_branch
    assert blocked_branch.index("video_uiflow3_prepare_existing_job_precheck_status") < blocked_branch.index(
        "if is_uiflow3_confirmation:"
    )


def test_trial_limit_blocks_existing_job_before_product_specific_render():
    block = _confirm_handler_block()
    blocked_start = block.index("if video_b14_is_trial_quality(")
    blocked_end = block.index("is_internal =", blocked_start)
    blocked_branch = block[blocked_start:blocked_end]

    assert "video_uiflow3_prepare_existing_job_precheck_status" in blocked_branch
    assert blocked_branch.index("video_uiflow3_prepare_existing_job_precheck_status") < blocked_branch.index(
        "if is_uiflow3_confirmation:"
    )


def test_zero_cost_confirm_stops_before_submit_and_outbox_creation():
    block = _confirm_handler_block()

    assert "confirm_video_project_invoice(" not in block
    assert "kickoff_product_video_job_after_confirm" not in block
    assert "dispatch_outbox" not in block
    assert 'preflight_result="PASS"' in block
    assert 'admission_result="PASS"' in block


def test_invoice_rerender_token_does_not_change_durable_attempt_key():
    key_for = _idempotency_key_function()
    base = {
        "draft": {
            "uiflow3_invoice_attestation": {
                "draft_id": "draft-stable",
                "config_hash": "config-stable",
                "token": "first-token",
            },
            "b14_invoice": {"scene_count": 2, "quality_xu": 200},
        }
    }
    rerendered = json.loads(json.dumps(base))
    rerendered["draft"]["uiflow3_invoice_attestation"]["token"] = "second-token"

    assert key_for(base, USER_ID, 9123) == key_for(rerendered, USER_ID, 9123)


def test_duplicate_terminal_job_returns_status_without_rewriting_precheck():
    block = _confirm_handler_block()
    duplicate_start = block.index('if (\n            intake_result.get("duplicate_prevented")')
    duplicate_end = block.index("session = video_trace_state.record_video_trace_event", duplicate_start)
    duplicate_branch = block[duplicate_start:duplicate_end]

    assert "VIDEO_JOB_PRECHECK_RUNNING" in duplicate_branch
    assert "video_b14_send_or_edit_status_panel" in duplicate_branch


def test_debug_report_distinguishes_internal_job_from_provider_submit(confirm_db):
    conn, _db_path, project = confirm_db
    started = _begin(conn, project)
    blocked = trace_state.record_video_confirm_precheck_result(
        started["session"],
        user_id=USER_ID,
        chat_id=CHAT_ID,
        job_id=started["job_id"],
        preflight_result="BLOCKED",
        admission_result="NOT_RUN",
        blocker_code="provider_unavailable",
        conn=conn,
    )

    report = trace_state.build_canonical_video_trace_report(blocked["request_id"], conn=conn)

    assert report["REQUEST_FOUND"] == "YES"
    assert report["DURABLE_REQUEST_FOUND"] == "YES"
    assert report["JOB_FOUND"] == "YES"
    assert report["JOB_ID"] == str(started["job_id"])
    assert report["PREFLIGHT_RESULT"] == "BLOCKED"
    assert report["EXACT_BLOCKER_CODE"] == "provider_unavailable"
    assert report["PROVIDER_TASK_ID"] == "None"
    assert report["SUBMIT_COUNT"] == 0
    assert report["POLL_COUNT"] == 0
    assert report["CHARGE_COUNT"] == 0
    assert report["CHARGE_STATE"] == "NO_CHARGE"


def test_status_identity_recovers_real_job_id_from_durable_trace(confirm_db):
    conn, _db_path, project = confirm_db
    started = _begin(conn, project)
    blocked = trace_state.record_video_confirm_precheck_result(
        started["session"],
        user_id=USER_ID,
        chat_id=CHAT_ID,
        job_id=started["job_id"],
        preflight_result="BLOCKED",
        admission_result="NOT_RUN",
        blocker_code="provider_unavailable",
        conn=conn,
    )
    stale_session = json.loads(json.dumps(blocked["session"]))
    stale_session["draft"].pop("b14_queue_job", None)
    stale_session["draft"].pop("b14_queue_job_id", None)

    identity = trace_state.resolve_video_status_identity(
        stale_session,
        result=None,
        user_id=USER_ID,
        conn=conn,
    )

    assert identity["request_id"] == started["request_id"]
    assert identity["job_id"] == started["job_id"]
    assert identity["job"]["id"] == started["job_id"]
    assert identity["trace"]["job_id"] == started["job_id"]


def test_status_panel_uses_durable_identity_resolver_before_job_render():
    start = BOT_SOURCE.index("def video_b14_queue_status_text(")
    end = BOT_SOURCE.index("\ndef video_b14_queue_status_keyboard(", start)
    block = BOT_SOURCE[start:end]

    resolver = block.index("video_trace_state.resolve_video_status_identity")
    job_id = block.index("job_id =", resolver)
    assert resolver < job_id


def test_status_steps_show_job_created_before_precheck_state():
    rows_for = _status_step_rows_function()

    assert rows_for(queue.VIDEO_JOB_PRECHECK_RUNNING, 5)[:4] == [
        ("✅", "Nhận yêu cầu"),
        ("✅", "Tạo tác vụ"),
        ("⏳", "Kiểm tra cấu hình"),
        ("⬜", "Dựng video"),
    ]
    assert rows_for(queue.VIDEO_JOB_PRECHECK_BLOCKED, 5)[:4] == [
        ("✅", "Nhận yêu cầu"),
        ("✅", "Tạo tác vụ"),
        ("⚠️", "Kiểm tra cấu hình"),
        ("⬜", "Dựng video"),
    ]
    assert rows_for(queue.VIDEO_JOB_READY_TO_SUBMIT, 10)[:4] == [
        ("✅", "Nhận yêu cầu"),
        ("✅", "Tạo tác vụ"),
        ("✅", "Kiểm tra cấu hình"),
        ("⏸", "Dựng video"),
    ]


@pytest.mark.parametrize("blocker_code", ["provider_unavailable", "provider_not_configured"])
def test_provider_readiness_blockers_keep_real_job(confirm_db, blocker_code):
    conn, _db_path, project = confirm_db
    started = _begin(conn, project)

    blocked = trace_state.record_video_confirm_precheck_result(
        started["session"],
        user_id=USER_ID,
        chat_id=CHAT_ID,
        job_id=started["job_id"],
        preflight_result="BLOCKED",
        admission_result="NOT_RUN",
        blocker_code=blocker_code,
        conn=conn,
    )

    assert blocked["job_id"] == started["job_id"]
    assert blocked["job"]["status"] == queue.VIDEO_JOB_PRECHECK_BLOCKED
    assert blocked["trace"]["internal_blocker_code"] == blocker_code
    assert conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0] == 1


def test_admission_blocked_keeps_real_job(confirm_db):
    conn, _db_path, project = confirm_db
    started = _begin(conn, project)

    blocked = trace_state.record_video_confirm_precheck_result(
        started["session"],
        user_id=USER_ID,
        chat_id=CHAT_ID,
        job_id=started["job_id"],
        preflight_result="PASS",
        admission_result="BLOCKED",
        blocker_code="admission_blocked",
        conn=conn,
    )

    assert blocked["job_id"] == started["job_id"]
    assert blocked["trace"]["current_stage"] == trace_state.STAGE_ADMISSION_BLOCKED
    assert blocked["trace"]["preflight_result"] == "PASS"
    assert blocked["trace"]["admission_result"] == "BLOCKED"


def test_job_creation_failure_is_explicit_and_keeps_zero_job_rows(confirm_db, monkeypatch):
    conn, _db_path, project = confirm_db

    def fail_job_insert(*_args, **_kwargs):
        raise sqlite3.OperationalError("injected job insert failure")

    monkeypatch.setattr(queue, "begin_video_precheck_job", fail_job_insert)
    failed = _begin(conn, project)

    assert failed["ok"] is False
    assert failed["reason"] == "job_create_failed"
    assert failed["request_id"].startswith("VID-")
    assert failed["job_id"] == 0
    assert failed["durable_persisted"] is True
    trace = trace_state.lookup_video_request_trace(failed["request_id"], conn=conn)
    assert trace["current_stage"] == trace_state.STAGE_JOB_CREATE_FAILED
    assert trace["internal_blocker_code"] == "job_create_failed"
    assert trace["job_id"] is None
    assert conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0] == 0


def test_postcommit_readback_failure_preserves_committed_job_identity(confirm_db, monkeypatch):
    conn, _db_path, project = confirm_db
    monkeypatch.setattr(trace_state, "lookup_video_request_trace", lambda *_args, **_kwargs: None)

    failed = _begin(conn, project)
    job_row = conn.execute(
        "SELECT id, status FROM video_jobs WHERE project_id=?",
        (int(project["project_id"]),),
    ).fetchone()
    trace_row = conn.execute(
        "SELECT request_id, job_id, current_stage, internal_blocker_code "
        "FROM video_request_traces WHERE project_id=?",
        (int(project["project_id"]),),
    ).fetchone()

    assert failed["ok"] is False
    assert failed["reason"] == "request_job_readback_failed"
    assert failed["durable_persisted"] is True
    assert failed["request_id"].startswith("VID-")
    assert failed["job_id"] == job_row["id"]
    assert job_row["status"] == queue.VIDEO_JOB_PRECHECK_RUNNING
    assert trace_row["request_id"] == failed["request_id"]
    assert trace_row["job_id"] == failed["job_id"]
    assert trace_row["current_stage"] == trace_state.STAGE_JOB_CREATED
    assert trace_row["internal_blocker_code"] is None


def test_wrong_project_owner_creates_neither_request_nor_job(confirm_db):
    conn, _db_path, project = confirm_db

    rejected = trace_state.begin_video_confirm_execution(
        {"draft": {}},
        user_id=USER_ID + 1,
        chat_id=CHAT_ID,
        project_id=int(project["project_id"]),
        idempotency_key="wrong-owner-attempt",
        conn=conn,
    )

    assert rejected["ok"] is False
    assert rejected["reason"] == "project_user_mismatch"
    assert conn.execute("SELECT COUNT(*) FROM video_request_traces").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0] == 0


def test_request_and_job_debug_resolvers_agree_on_same_job(confirm_db):
    conn, _db_path, project = confirm_db
    started = _begin(conn, project)

    by_request = trace_state.resolve_video_request_truth(started["request_id"], conn=conn)
    by_job = trace_state.resolve_video_request_truth(started["job_id"], conn=conn)
    report = trace_state.build_canonical_video_trace_report(started["request_id"], conn=conn)

    assert by_request["job_id"] == str(started["job_id"])
    assert by_job["job_id"] == str(started["job_id"])
    assert report["JOB_ID"] == str(started["job_id"])
    assert by_request["request_id"] == started["request_id"]
    assert by_job["request_id"] == started["request_id"]


def test_canonical_sql_job_id_overrides_stale_null_trace_json(confirm_db):
    conn, _db_path, project = confirm_db
    started = _begin(conn, project)
    trace = trace_state.lookup_video_request_trace(started["request_id"], conn=conn)
    trace["job_id"] = None
    conn.execute(
        "UPDATE video_request_traces SET trace_payload_json=? WHERE request_id=?",
        (json.dumps(trace), started["request_id"]),
    )
    conn.commit()

    recovered = trace_state.lookup_video_request_trace(started["request_id"], conn=conn)
    report = trace_state.build_canonical_video_trace_report(started["request_id"], conn=conn)

    assert recovered["job_id"] == started["job_id"]
    assert report["JOB_FOUND"] == "YES"
    assert report["JOB_ID"] == str(started["job_id"])


def test_ready_transition_clears_old_blocker_on_same_job(confirm_db):
    conn, _db_path, project = confirm_db
    started = _begin(conn, project)
    blocked = trace_state.record_video_confirm_precheck_result(
        started["session"],
        user_id=USER_ID,
        chat_id=CHAT_ID,
        job_id=started["job_id"],
        preflight_result="BLOCKED",
        admission_result="NOT_RUN",
        blocker_code="provider_unavailable",
        conn=conn,
    )

    ready = trace_state.record_video_confirm_precheck_result(
        blocked["session"],
        user_id=USER_ID,
        chat_id=CHAT_ID,
        job_id=started["job_id"],
        preflight_result="PASS",
        admission_result="PASS",
        blocker_code="",
        conn=conn,
    )

    raw_blocker = conn.execute(
        "SELECT internal_blocker_code FROM video_request_traces WHERE request_id=?",
        (started["request_id"],),
    ).fetchone()[0]
    assert ready["job_id"] == started["job_id"]
    assert ready["job"]["status"] == queue.VIDEO_JOB_READY_TO_SUBMIT
    assert ready["trace"]["internal_blocker_code"] is None
    assert raw_blocker is None


def test_status_identity_prefers_durable_job_state_over_stale_session_cache(confirm_db):
    conn, _db_path, project = confirm_db
    started = _begin(conn, project)
    blocked = trace_state.record_video_confirm_precheck_result(
        started["session"],
        user_id=USER_ID,
        chat_id=CHAT_ID,
        job_id=started["job_id"],
        preflight_result="BLOCKED",
        admission_result="NOT_RUN",
        blocker_code="provider_unavailable",
        conn=conn,
    )
    stale_session = json.loads(json.dumps(blocked["session"]))
    stale_session["draft"]["b14_queue_job"] = {
        "id": started["job_id"],
        "status": "queued",
        "result_json": json.dumps({"submit_count": 1, "provider_task_id": "stale-provider-task"}),
    }

    identity = trace_state.resolve_video_status_identity(
        stale_session,
        user_id=USER_ID,
        conn=conn,
    )
    durable_payload = json.loads(identity["job"]["result_json"])

    assert identity["job"]["status"] == queue.VIDEO_JOB_PRECHECK_BLOCKED
    assert durable_payload["provider_task_id"] is None
    assert durable_payload["submit_count"] == 0


def test_precheck_payload_cannot_override_zero_cost_trace_invariants(confirm_db):
    conn, _db_path, project = confirm_db
    started = _begin(conn, project)

    blocked = trace_state.record_video_confirm_precheck_result(
        started["session"],
        user_id=USER_ID,
        chat_id=CHAT_ID,
        job_id=started["job_id"],
        preflight_result="BLOCKED",
        admission_result="NOT_RUN",
        blocker_code="provider_unavailable",
        payload={
            "job_id": started["job_id"] + 100,
            "owner_user_id": USER_ID + 100,
            "preflight_result": "PASS",
            "admission_result": "PASS",
            "provider_task_id": "forbidden-provider-task",
            "submit_count": 4,
            "poll_count": 5,
            "charge_count": 6,
            "charge_state": "CHARGED",
        },
        conn=conn,
    )

    assert blocked["ok"] is True
    assert blocked["trace"]["job_id"] == started["job_id"]
    assert blocked["trace"]["owner_user_id"] == USER_ID
    assert blocked["trace"]["preflight_result"] == "BLOCKED"
    assert blocked["trace"]["admission_result"] == "NOT_RUN"
    assert blocked["trace"]["provider_task_id"] is None
    assert blocked["trace"]["submit_count"] == 0
    assert blocked["trace"]["poll_count"] == 0
    assert blocked["trace"]["charge_count"] == 0
    assert blocked["trace"]["charge_state"] == "NO_CHARGE"


def test_precheck_cannot_rewrite_terminal_job_state(confirm_db):
    conn, _db_path, project = confirm_db
    started = _begin(conn, project)
    conn.execute(
        "UPDATE video_jobs SET status='completed',progress_percent=100 WHERE id=?",
        (started["job_id"],),
    )
    conn.commit()

    rejected = trace_state.record_video_confirm_precheck_result(
        started["session"],
        user_id=USER_ID,
        chat_id=CHAT_ID,
        job_id=started["job_id"],
        preflight_result="PASS",
        admission_result="PASS",
        conn=conn,
    )

    assert rejected["ok"] is False
    assert rejected["reason"] == "job_not_in_precheck_state"
    assert conn.execute(
        "SELECT status FROM video_jobs WHERE id=?",
        (started["job_id"],),
    ).fetchone()[0] == "completed"


def test_blocked_status_copy_does_not_promise_unsubmitted_video():
    block = _source_block(
        "def video_b14_queue_status_text(",
        "\n\ndef video_b14_queue_status_keyboard(",
    )
    blocked_copy = block.index("elif status == video_project_queue.VIDEO_JOB_PRECHECK_BLOCKED:")
    generic_copy = block.index("TOAN AAS sẽ tự cập nhật khi có video hoàn chỉnh.")

    assert blocked_copy < generic_copy
    assert "Hệ thống chưa gửi lệnh dựng và chưa trừ Xu." in block[blocked_copy:generic_copy]


def test_all_three_debug_commands_share_canonical_request_job_identity():
    helper = _source_block(
        "def video_request_debug_identity(",
        "\n\ndef product_progress_debug_text(",
    )
    progress_command = _source_block(
        "async def cmd_progress_status_debug(",
        "\n\nasync def cmd_progress_auto_refresh_status(",
    )
    render_command = _source_block(
        "async def cmd_video_render_debug(",
        "\n\nasync def cmd_video_trace(",
    )
    trace_command = _source_block(
        "async def cmd_video_trace(",
        "\n\nasync def cmd_video_provider_job_debug(",
    )

    for field in (
        "REQUEST_ID",
        "REQUEST_FOUND",
        "DURABLE_REQUEST_FOUND",
        "JOB_FOUND",
        "JOB_ID",
        "PREFLIGHT_RESULT",
        "ADMISSION_RESULT",
        "EXACT_BLOCKER_CODE",
        "PROVIDER_TASK_ID",
        "SUBMIT_COUNT",
        "POLL_COUNT",
        "CHARGE_COUNT",
    ):
        assert field in helper
    assert "video_request_debug_identity" in progress_command
    assert "resolved_job_id" in progress_command
    assert progress_command.index("video_request_debug_identity") < progress_command.index(
        "product_progress_debug_text"
    )
    assert "video_request_debug_identity" in render_command
    assert render_command.index("video_request_debug_identity") < render_command.index(
        "video_render_debug_text"
    )
    assert "build_canonical_video_trace_report" in trace_command
    assert "POLL_COUNT" in trace_command
    assert "CHARGE_COUNT" in trace_command


def test_debug_truth_does_not_claim_missing_job_row(confirm_db):
    conn, _db_path, project = confirm_db
    started = _begin(conn, project)
    conn.execute("DELETE FROM video_jobs WHERE id=?", (started["job_id"],))
    conn.commit()

    truth = trace_state.resolve_video_request_truth(started["request_id"], conn=conn)

    assert truth["request_found"] == "YES"
    assert truth["durable_request_found"] == "YES"
    assert truth["job_id"] == str(started["job_id"])
    assert truth["job_found"] == "NO"


def test_precheck_debug_has_no_invented_selected_provider(confirm_db):
    conn, _db_path, project = confirm_db
    started = _begin(conn, project)

    truth = trace_state.resolve_video_request_truth(started["request_id"], conn=conn)

    assert truth["eligible_route_count_at_request"] == 0
    assert truth["selected_route_at_request"] == "None"
