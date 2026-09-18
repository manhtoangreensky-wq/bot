from __future__ import annotations

import json
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from services import video_project_queue as queue
from services import video_provider_router as router
from services import remote_worker_api


NOW = datetime(2026, 9, 19, 0, 0, 0)


def _setup_test_db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / f"pv12_test_{id(tmp_path)}.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _create_probation_job(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    project_id: int,
    user_id: int = 1001,
    status: str = "completed",
    probation_result: str = "pending",
    probation_started_at: str = "",
    probation_lock_expires_at: str = "",
    completed_at: str = "",
    delivery_state: str = "pending",
    final_delivered: bool = False,
    delivery_succeeded: bool = False,
    blocker: str = "",
    final_video_path: str = "",
    admission_mode: str = queue.PRODUCT_VIDEO_PROBATION_ADMISSION_MODE,
) -> None:
    shared = {
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "product_type": "video_trend",
        "engine_adapter": "text_to_video",
        "orchestration_mode": "per_scene_8s",
        "scene_count": 2,
        "duration_seconds": 16,
    }
    project = queue.create_video_project(
        conn,
        user_id=user_id,
        profile_id="video_trend",
        topic=f"PV12 project {project_id}",
        ratio="9:16",
        asset_pack=shared,
    )
    orig_pid = int(project["project_id"])
    conn.execute("UPDATE video_projects SET project_id=? WHERE project_id=?", (project_id, orig_pid))
    queue.update_video_project(
        conn,
        project_id,
        status="completed" if status == "completed" else "processing",
        final_video_path=final_video_path,
        invoice_json={
            **shared,
            "package_xu": 300,
            "user_visible_price_xu": 300,
            "persisted_quoted_price_xu": 300,
            "customer_charge_planned_xu": 300,
            "wallet_charge_amount_xu": 300,
        },
        scene_count=2,
        total_xu_estimated=300,
        is_confirmed=1,
    )
    job = queue.enqueue_video_render_job(conn, project_id=project_id, user_id=user_id, max_attempts=3)
    orig_jid = int(job["id"])
    conn.execute("UPDATE video_jobs SET id=? WHERE id=?", (job_id, orig_jid))
    conn.execute("UPDATE video_projects SET job_id=? WHERE project_id=?", (job_id, project_id))

    payload = {
        **shared,
        "admission_mode": admission_mode,
        "probation_candidate_key": "shopaikey_video",
        "probation_job_id": job_id,
        "probation_result": probation_result,
        "probation_started_at": probation_started_at,
        "probation_lock_expires_at": probation_lock_expires_at,
        "delivery_state": delivery_state,
        "final_delivered": final_delivered,
        "delivery_succeeded": delivery_succeeded,
        "final_mp4_valid": True,
        "output_bytes": 2841834,
        "download_url": "https://example.com/video.mp4",
        "scene_clip_coverage_complete": True,
        "scene_coverage_expected": 2,
        "scene_coverage_count": 2,
        "scenes_total": 2,
        "scenes_done": 2,
        "final_video_path": final_video_path,
        "scene_tasks": queue.product_video_initial_scene_tasks(job_id, 2),
    }
    if blocker:
        payload["probation_result_validation_blocker"] = blocker

    conn.execute(
        """UPDATE video_jobs
           SET status=?, result_json=?, progress_percent=?, progress_message=?,
               completed_at=?, updated_at=?, created_at=?
           WHERE id=?""",
        (
            status,
            json.dumps(payload),
            95 if status == "completed" and not final_delivered else 100,
            "final_mp4_ready_waiting_delivery" if status == "completed" and not final_delivered else "delivered",
            completed_at,
            completed_at or probation_started_at,
            probation_started_at or queue.now_text(NOW),
            job_id,
        ),
    )
    conn.commit()


def test_pv12_completed_pending_delivery_within_ttl_holds_lock(tmp_path):
    """Test 1: completed + pending_delivery without expiry asserts current lock behavior."""
    conn = _setup_test_db(tmp_path)
    started_at = queue.now_text(NOW - timedelta(minutes=5))
    _create_probation_job(
        conn,
        job_id=29,
        project_id=33,
        status="completed",
        probation_result="pending",
        probation_started_at=started_at,
        probation_lock_expires_at=queue.now_text(NOW + timedelta(minutes=25)),
        completed_at=queue.now_text(NOW - timedelta(minutes=2)),
        delivery_state="pending",
    )

    state = queue.product_video_probation_lock_state(conn, current_job_id=28, now=NOW)
    assert state["probation_active"] is True
    assert state["probation_lock_clear"] is False
    assert state["active_probation_job_id"] == 29
    assert state["probation_lock_owner_job"] == 29
    assert state["probation_lock_owned_by_other_job"] is True
    assert state["probation_lock_clear_for_current_job"] is False
    assert state["probation_lock_reject_reason"] == "probation_lock_owned_by_other_job"

    same_job_state = queue.product_video_probation_lock_state(conn, current_job_id=29, now=NOW)
    assert same_job_state["probation_active"] is True
    assert same_job_state["current_job_matches_lock"] is True
    assert same_job_state["probation_lock_clear_for_current_job"] is True


def test_pv12_completed_missing_delivery_lock_expires_after_ttl(tmp_path):
    """Test 2: completed + valid MP4 + missing delivery -> lock TTL / expiration behavior."""
    conn = _setup_test_db(tmp_path)
    started_at = queue.now_text(NOW - timedelta(hours=36))
    completed_at = queue.now_text(NOW - timedelta(hours=28))
    _create_probation_job(
        conn,
        job_id=29,
        project_id=33,
        status="completed",
        probation_result="pending",
        probation_started_at=started_at,
        probation_lock_expires_at="",  # empty on VPS
        completed_at=completed_at,
        delivery_state="pending",
        final_delivered=False,
        delivery_succeeded=False,
        blocker="valid_result_scene_coverage_final_mp4_delivery_message_required",
    )

    state = queue.product_video_probation_lock_state(conn, current_job_id=28, now=NOW)
    assert state["probation_active"] is False
    assert state["probation_lock_clear"] is True
    assert state["probation_lock_status"] == "clear"
    assert state["active_probation_job_id"] == 0
    assert state["probation_lock_owner_job"] == 0
    assert state["probation_lock_owned_by_other_job"] is False
    assert state["probation_lock_clear_for_current_job"] is True


def test_pv12_delivered_terminal_releases_lock(tmp_path):
    """Test 3: delivered terminal releases lock."""
    conn = _setup_test_db(tmp_path)
    started_at = queue.now_text(NOW - timedelta(minutes=10))

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"mock_mp4_content" * 100)
        temp_mp4 = f.name

    try:
        _create_probation_job(
            conn,
            job_id=29,
            project_id=33,
            status="completed",
            probation_result="pending",
            probation_started_at=started_at,
            probation_lock_expires_at=queue.now_text(NOW + timedelta(minutes=20)),
            completed_at=queue.now_text(NOW - timedelta(minutes=5)),
            delivery_state="pending",
            final_video_path=temp_mp4,
        )

        from services import video_local_validation
        from _pytest.monkeypatch import MonkeyPatch
        mp = MonkeyPatch()
        mp.setattr(video_local_validation, "probe_video_file", lambda p: {"ok": True, "duration": 16.0, "has_video": True, "has_audio": True})

        res = queue.note_video_delivery_result(
            conn,
            job_id=29,
            sent=True,
            delivery_message_id="tg_delivery_msg_1001",
        )
        assert res["ok"] is True

        state = queue.product_video_probation_lock_state(conn, current_job_id=28, now=NOW)
        assert state["probation_active"] is False
        assert state["probation_lock_clear"] is True
        assert state["probation_last_result"] == "success"
        mp.undo()
    finally:
        Path(temp_mp4).unlink(missing_ok=True)


def test_pv12_failed_or_cancelled_releases_lock(tmp_path):
    """Test 4: failed / cancelled releases lock."""
    conn = _setup_test_db(tmp_path)
    started_at = queue.now_text(NOW - timedelta(minutes=10))

    # Case A: failed
    _create_probation_job(
        conn,
        job_id=30,
        project_id=34,
        status="failed",
        probation_result="failed",
        probation_started_at=started_at,
        probation_lock_expires_at=queue.now_text(NOW + timedelta(minutes=20)),
    )
    state_a = queue.product_video_probation_lock_state(conn, current_job_id=28, now=NOW)
    assert state_a["probation_active"] is False
    assert state_a["active_probation_job_id"] == 0

    # Case B: cancelled
    _create_probation_job(
        conn,
        job_id=31,
        project_id=35,
        status="cancelled",
        probation_result="pending",
        probation_started_at=started_at,
        probation_lock_expires_at=queue.now_text(NOW + timedelta(minutes=20)),
    )
    state_b = queue.product_video_probation_lock_state(conn, current_job_id=28, now=NOW)
    assert state_b["probation_active"] is False
    assert state_b["active_probation_job_id"] == 0


def test_pv12_explicit_or_derived_expiry_clears_lock(tmp_path):
    """Test 5: expired lock is not active (probation_lock_clear = True)."""
    conn = _setup_test_db(tmp_path)

    # Sub-case A: Explicit expiry in past
    _create_probation_job(
        conn,
        job_id=32,
        project_id=36,
        status="processing",
        probation_result="pending",
        probation_started_at=queue.now_text(NOW - timedelta(hours=2)),
        probation_lock_expires_at=queue.now_text(NOW - timedelta(seconds=1)),
    )
    state_a = queue.product_video_probation_lock_state(conn, current_job_id=99, now=NOW)
    assert state_a["probation_active"] is False
    assert state_a["probation_lock_clear"] is True

    # Sub-case B: Missing probation_lock_expires_at, but probation_started_at > default TTL
    _create_probation_job(
        conn,
        job_id=33,
        project_id=37,
        status="completed",
        probation_result="pending",
        probation_started_at=queue.now_text(NOW - timedelta(hours=2)),
        probation_lock_expires_at="",
        completed_at=queue.now_text(NOW - timedelta(hours=1)),
    )
    state_b = queue.product_video_probation_lock_state(conn, current_job_id=99, now=NOW)
    assert state_b["probation_active"] is False
    assert state_b["probation_lock_clear"] is True


def test_pv12_no_provider_submit_during_delivery_recovery():
    """Test 6: no provider submit during delivery recovery."""
    job = {
        "id": 29,
        "project_id": 33,
        "status": "failed",
    }
    project = {
        "project_id": 33,
        "status": "completed",
        "is_confirmed": 1,
        "delivery_attempt_count": 1,
    }
    result = {
        "product_video": True,
        "public_user_confirmed": True,
        "delivery_recovery_count": 1,
        "recovery_existing_tasks_only": True,
    }
    outbox = {
        "outbox_id": 10,
        "dispatch_status": "completed",
    }
    state = queue.product_video_existing_task_recovery_state(
        job,
        project,
        result,
        outbox,
        recovery_domain="delivery",
        now=NOW,
    )
    assert state["provider_submit_allowed"] is False
    assert state["automatic_retry_allowed"] is False
    assert state["automatic_resubmit_allowed"] is False
    assert state["automatic_fallback_allowed"] is False


def test_pv12_job28_untouched_and_router_eligibility_simulation(tmp_path):
    """Test 7: Job 28 untouched and router eligibility simulation after Job 29 reconciliation."""
    conn = _setup_test_db(tmp_path)

    # Job 29: Completed with expired probation lock
    _create_probation_job(
        conn,
        job_id=29,
        project_id=33,
        status="completed",
        probation_result="pending",
        probation_started_at=queue.now_text(NOW - timedelta(hours=36)),
        probation_lock_expires_at="",
        completed_at=queue.now_text(NOW - timedelta(hours=28)),
        delivery_state="pending",
    )

    # Job 28: Queued, untouched (regular production job)
    _create_probation_job(
        conn,
        job_id=28,
        project_id=32,
        status="queued",
        admission_mode="healthy",
        probation_started_at=queue.now_text(NOW - timedelta(hours=48)),
        probation_lock_expires_at="",
    )
    conn.execute("UPDATE video_jobs SET last_error='provider_in_progress', attempts=1 WHERE id=28")
    conn.commit()

    # Capture Job 28 exact row before
    job28_before = dict(conn.execute("SELECT * FROM video_jobs WHERE id=28").fetchone())

    # Check lock state for candidate evaluation
    lock_state = queue.product_video_probation_lock_state(conn, current_job_id=28, now=NOW)
    assert lock_state["probation_lock_clear"] is True

    # Verify Job 28 exact row after is 100% untouched
    job28_after = dict(conn.execute("SELECT * FROM video_jobs WHERE id=28").fetchone())
    assert job28_before == job28_after
