from __future__ import annotations

import json
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services import video_project_queue as queue
from services import video_provider_router as router
from services import remote_worker_api


NOW = datetime(2026, 9, 19, 0, 0, 0)
NOW_UTC = datetime(2026, 9, 18, 17, 0, 0, tzinfo=timezone.utc)
NOW_PLUS7 = datetime(2026, 9, 19, 0, 0, 0, tzinfo=timezone(timedelta(hours=7)))


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
    probation_delivery_expires_at: str = "",
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
        "probation_delivery_expires_at": probation_delivery_expires_at,
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
            95 if status == "completed" and not final_delivered else (70 if status == "processing" else 10),
            "final_mp4_ready_waiting_delivery" if status == "completed" and not final_delivered else (
                "provider_in_progress" if status == "processing" else "queued_waiting"
            ),
            completed_at,
            completed_at or probation_started_at,
            probation_started_at or queue.now_text(NOW),
            job_id,
        ),
    )
    conn.commit()


def test_pv12_active_processing_job_age_gt_30m_never_prematurely_unlocks(tmp_path):
    """Section 1: processing job with age > 30 minutes must NOT release probation lock solely by wall clock."""
    conn = _setup_test_db(tmp_path)
    started_at = queue.now_text(NOW - timedelta(minutes=45))
    _create_probation_job(
        conn,
        job_id=40,
        project_id=40,
        status="processing",
        probation_result="pending",
        probation_started_at=started_at,
        probation_lock_expires_at="",
        completed_at="",
        delivery_state="pending",
    )

    state = queue.product_video_probation_lock_state(conn, current_job_id=28, now=NOW)
    assert state["probation_active"] is True
    assert state["probation_lock_clear"] is False
    assert state["active_probation_job_id"] == 40
    assert state["probation_lock_owner_job"] == 40
    assert state["probation_lock_owned_by_other_job"] is True
    assert state["probation_lock_clear_for_current_job"] is False
    assert state["probation_lock_reject_reason"] == "probation_lock_owned_by_other_job"


def test_pv12_completed_pending_delivery_within_ttl_holds_lock(tmp_path):
    """Section 2: completed + pending_delivery within 600s TTL holds probation lock."""
    conn = _setup_test_db(tmp_path)
    started_at = queue.now_text(NOW - timedelta(minutes=8))
    completed_at = queue.now_text(NOW - timedelta(minutes=5))
    _create_probation_job(
        conn,
        job_id=29,
        project_id=33,
        status="completed",
        probation_result="pending",
        probation_started_at=started_at,
        probation_delivery_expires_at=queue.now_text(NOW + timedelta(minutes=5)),
        completed_at=completed_at,
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
    """Section 2: completed + missing delivery after >= 600s TTL releases probation lock."""
    conn = _setup_test_db(tmp_path)
    started_at = queue.now_text(NOW - timedelta(minutes=25))
    completed_at = queue.now_text(NOW - timedelta(minutes=15))
    _create_probation_job(
        conn,
        job_id=29,
        project_id=33,
        status="completed",
        probation_result="pending",
        probation_started_at=started_at,
        probation_delivery_expires_at=queue.now_text(NOW - timedelta(minutes=5)),
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
    assert state["probation_last_result"] == "expired"
    assert state["probation_lock_clear_for_current_job"] is True


def test_pv12_delivered_terminal_releases_lock(tmp_path):
    """Section 2: delivered success releases probation lock normally."""
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
            probation_delivery_expires_at=queue.now_text(NOW + timedelta(minutes=5)),
            completed_at=queue.now_text(NOW - timedelta(minutes=2)),
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
    """Section 2: failed or cancelled jobs release probation lock normally."""
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
    )
    state_b = queue.product_video_probation_lock_state(conn, current_job_id=28, now=NOW)
    assert state_b["probation_active"] is False
    assert state_b["active_probation_job_id"] == 0


def test_pv12_separated_persisted_delivery_expiry_semantics(tmp_path):
    """Section 3: separate probation_delivery_expires_at from admission execution TTL."""
    conn = _setup_test_db(tmp_path)

    # Job A: has explicit probation_delivery_expires_at in the past
    _create_probation_job(
        conn,
        job_id=51,
        project_id=51,
        status="completed",
        probation_result="pending",
        probation_started_at=queue.now_text(NOW - timedelta(minutes=15)),
        probation_delivery_expires_at=queue.now_text(NOW - timedelta(seconds=1)),
        completed_at=queue.now_text(NOW - timedelta(minutes=5)),
    )
    state_a = queue.product_video_probation_lock_state(conn, current_job_id=99, now=NOW)
    assert state_a["probation_active"] is False
    assert state_a["probation_lock_clear"] is True

    # Job B: has NO probation_delivery_expires_at field (legacy), derived from completed_at + 600s
    _create_probation_job(
        conn,
        job_id=52,
        project_id=52,
        status="completed",
        probation_result="pending",
        probation_started_at=queue.now_text(NOW - timedelta(minutes=30)),
        probation_delivery_expires_at="",
        probation_lock_expires_at="",
        completed_at=queue.now_text(NOW - timedelta(seconds=601)),
    )
    state_b = queue.product_video_probation_lock_state(conn, current_job_id=99, now=NOW)
    assert state_b["probation_active"] is False
    assert state_b["probation_lock_clear"] is True


def test_pv12_timezone_invariance_utc_vs_plus7_vs_naive(tmp_path):
    """Section 4: identical physical instant represented as UTC, +07:00, or naive yields identical decisions."""
    conn = _setup_test_db(tmp_path)
    _create_probation_job(
        conn,
        job_id=29,
        project_id=33,
        status="completed",
        probation_result="pending",
        probation_started_at="2026-09-18 19:10:00",
        completed_at="2026-09-18 19:11:38",
    )

    # 601 seconds after completion (19:21:39 local / 12:21:39 UTC): lock must be expired
    t_utc = datetime(2026, 9, 18, 12, 21, 39, tzinfo=timezone.utc)
    t_plus7 = datetime(2026, 9, 18, 19, 21, 39, tzinfo=timezone(timedelta(hours=7)))
    t_naive = datetime(2026, 9, 18, 19, 21, 39)

    s_utc = queue.product_video_probation_lock_state(conn, now=t_utc)
    s_plus7 = queue.product_video_probation_lock_state(conn, now=t_plus7)
    s_naive = queue.product_video_probation_lock_state(conn, now=t_naive)

    # Exactly identical decisions
    assert s_utc["probation_active"] is False
    assert s_utc["probation_lock_clear"] is True
    assert s_utc["probation_last_result"] == "expired"

    assert s_plus7["probation_active"] is False
    assert s_plus7["probation_lock_clear"] is True
    assert s_plus7["probation_last_result"] == "expired"

    assert s_naive["probation_active"] is False
    assert s_naive["probation_lock_clear"] is True
    assert s_naive["probation_last_result"] == "expired"

    # Within TTL instant (19:15:00 local / 12:15:00 UTC): lock must be held
    t_utc_locked = datetime(2026, 9, 18, 12, 15, 0, tzinfo=timezone.utc)
    t_plus7_locked = datetime(2026, 9, 18, 19, 15, 0, tzinfo=timezone(timedelta(hours=7)))
    t_naive_locked = datetime(2026, 9, 18, 19, 15, 0)

    sl_utc = queue.product_video_probation_lock_state(conn, now=t_utc_locked)
    sl_plus7 = queue.product_video_probation_lock_state(conn, now=t_plus7_locked)
    sl_naive = queue.product_video_probation_lock_state(conn, now=t_naive_locked)

    assert sl_utc["probation_active"] is True
    assert sl_utc["probation_lock_clear"] is False

    assert sl_plus7["probation_active"] is True
    assert sl_plus7["probation_lock_clear"] is False

    assert sl_naive["probation_active"] is True
    assert sl_naive["probation_lock_clear"] is False


def test_pv12_preserve_specific_rejection_reason(tmp_path):
    """Section 5: preserve specific rejection reason in _confirm_product_video_invoice_atomic."""
    conn = _setup_test_db(tmp_path)
    _create_probation_job(
        conn,
        job_id=29,
        project_id=33,
        status="completed",
        probation_result="pending",
        probation_started_at=queue.now_text(NOW - timedelta(minutes=3)),
        probation_delivery_expires_at=queue.now_text(NOW + timedelta(minutes=7)),
        completed_at=queue.now_text(NOW - timedelta(minutes=1)),
    )

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
    proj = queue.create_video_project(
        conn,
        user_id=1002,
        profile_id="video_trend",
        topic="PV12 candidate project",
        asset_pack=shared,
    )
    queue.update_video_project(
        conn,
        int(proj["project_id"]),
        status="draft_invoice",
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
    )
    fresh_proj = queue.get_video_project(conn, int(proj["project_id"]))
    admission = {
        "ok": True,
        "admission_passed": True,
        "admission_result": "PASS",
        "admission_mode": queue.PRODUCT_VIDEO_PROBATION_ADMISSION_MODE,
        "admission_candidate_keys": ["shopaikey_video"],
        "admission_candidate_count": 1,
        "runtime_candidate_keys": ["shopaikey_video"],
        "probation_candidate_key": "shopaikey_video",
    }
    res = queue._confirm_product_video_invoice_atomic(
        conn,
        project=fresh_proj,
        user_id=1002,
        admission=admission,
        require_provider_admission=True,
        now=NOW,
    )
    assert res["ok"] is False
    assert res["reason"] == "probation_lock_owned_by_other_job"


def test_pv12_legacy_job29_proof(tmp_path):
    """Section 6: exact reproduction of VPS Job 29 evidence: completed, progress=95, delivery absent, old completed_at."""
    conn = _setup_test_db(tmp_path)
    _create_probation_job(
        conn,
        job_id=29,
        project_id=33,
        status="completed",
        probation_result="pending",
        probation_started_at="2026-09-18 19:10:00",
        probation_lock_expires_at="",
        probation_delivery_expires_at="",
        completed_at="2026-09-18 19:11:38",
        delivery_state="pending",
        final_delivered=False,
        delivery_succeeded=False,
        blocker="valid_result_scene_coverage_final_mp4_delivery_message_required",
    )

    current_vps_time = datetime(2026, 9, 19, 0, 25, 0)
    state = queue.product_video_probation_lock_state(conn, now=current_vps_time)

    assert state["probation_active"] is False
    assert state["probation_lock_clear"] is True
    assert state["probation_last_result"] == "expired"
    assert state["active_probation_job_id"] == 0


def test_pv12_job28_non_action_proof(tmp_path):
    """Section 7: Job 28 remains byte/row-equivalent before/after lock read, zero mutations, zero calls."""
    conn = _setup_test_db(tmp_path)

    _create_probation_job(
        conn,
        job_id=29,
        project_id=33,
        status="completed",
        probation_result="pending",
        probation_started_at="2026-09-18 19:10:00",
        probation_lock_expires_at="",
        probation_delivery_expires_at="",
        completed_at="2026-09-18 19:11:38",
        delivery_state="pending",
    )

    _create_probation_job(
        conn,
        job_id=28,
        project_id=32,
        status="queued",
        admission_mode="healthy",
        probation_started_at="2026-09-18 18:00:00",
        probation_lock_expires_at="",
    )
    conn.execute("UPDATE video_jobs SET last_error='provider_in_progress', attempts=1 WHERE id=28")
    conn.commit()

    job28_before = dict(conn.execute("SELECT * FROM video_jobs WHERE id=28").fetchone())

    lock_state = queue.product_video_probation_lock_state(conn, current_job_id=28, now=NOW)
    assert lock_state["probation_lock_clear"] is True

    job28_after = dict(conn.execute("SELECT * FROM video_jobs WHERE id=28").fetchone())
    assert job28_before == job28_after


def test_pv12_no_provider_submit_during_delivery_recovery():
    """Section 9: no provider submit calls allowed during delivery recovery."""
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
