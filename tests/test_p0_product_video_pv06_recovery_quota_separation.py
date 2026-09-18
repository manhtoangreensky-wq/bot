"""Tests for P0.PRODUCT_VIDEO.PV06.RECOVERY.QUOTA.SEPARATION.

Deterministic verification of independent recovery budgets across:
1. provider_poll_recovery_count
2. provider_artifact_recovery_count
3. scene_clip_recovery_count
4. finalizer_recovery_count
5. delivery_recovery_count
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from services import remote_worker_api
from services import video_project_queue as queue


TASK_SCENE_1 = "task-scene-1-HR51"
TASK_SCENE_2 = "task-scene-2-nZHo"


def _seed_pv06_test_job(
    db_path: Path,
    *,
    scene_count: int = 2,
    existing_poll_attempts: int = 0,
    provider_task_completed: bool = False,
    all_clips_downloaded: bool = False,
    final_mp4_valid: bool = False,
    job_status: str = "failed",
    project_status: str = "failed",
    outbox_status: str = "acknowledged",
) -> tuple[sqlite3.Connection, int, int]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)

    project = queue.create_video_project(
        conn,
        user_id=919_013,
        profile_id="video_ai_prompt",
        topic="PV06 recovery quota separation",
        asset_pack={
            "source": "product_video",
            "product_type": "video_ai_prompt",
            "render_mode": "real",
            "public_user": True,
        },
    )
    project_id = int(project["project_id"])
    queue.update_video_project(
        conn,
        project_id,
        status=project_status,
        is_confirmed=1,
        scene_count=scene_count,
        invoice_json={"scene_count": scene_count, "duration_seconds": scene_count * 8},
    )
    job = queue.enqueue_video_render_job(
        conn,
        project_id=project_id,
        user_id=919_013,
        max_attempts=3,
    )
    job_id = int(job["id"])
    queue.update_video_project(
        conn,
        project_id,
        status=project_status,
        job_id=job_id,
    )

    scene_status = "succeeded" if provider_task_completed else "provider_running"
    result: dict = {
        "job_id": job_id,
        "project_id": project_id,
        "source": "product_video",
        "product_video": True,
        "scene_count": scene_count,
        "orchestration_mode": "per_scene_8s",
        "provider_pending_provider": "shopaikey_video",
        "provider_pending_task_id": TASK_SCENE_2,
        "provider_task_ids": [TASK_SCENE_1, TASK_SCENE_2],
        "canonical_scene_index": 1,
        "scene_task_map": {"1": [TASK_SCENE_1], "2": [TASK_SCENE_2]},
        "task_scene_index_map": {TASK_SCENE_1: 1, TASK_SCENE_2: 2},
        "task_to_scene_index": {TASK_SCENE_1: 1, TASK_SCENE_2: 2},
        "scene_active_task_by_index": {"1": TASK_SCENE_1, "2": TASK_SCENE_2},
        "scene_winner_task_by_index": {"1": TASK_SCENE_1, "2": TASK_SCENE_2},
        "scene_status_by_index": {"1": scene_status, "2": scene_status},
        "chat_id": 919_013,
        "user_id": 919_013,
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "charged_xu": 0,
        "charge": 0,
        "wallet_charge_recorded": False,
        "no_charge": True,
        "provider_submit_allowed": False,
        "automatic_retry_allowed": False,
        "automatic_resubmit_allowed": False,
        "automatic_fallback_allowed": False,
        "scene_tasks": [
            {
                "scene_index": 1,
                "provider": "shopaikey_video",
                "status": scene_status,
                "result_url": "https://cdn.example.com/scene1.mp4" if provider_task_completed else "",
                "clip_bytes": 1024 * 1024 if all_clips_downloaded else 0,
                "artifact_valid": all_clips_downloaded,
            },
            {
                "scene_index": 2,
                "provider": "shopaikey_video",
                "status": scene_status,
                "result_url": "https://cdn.example.com/scene2.mp4" if provider_task_completed else "",
                "clip_bytes": 1024 * 1024 if all_clips_downloaded else 0,
                "artifact_valid": all_clips_downloaded,
            },
        ],
    }

    if existing_poll_attempts > 0:
        result["existing_task_recovery_count"] = existing_poll_attempts
        result["provider_poll_recovery_count"] = existing_poll_attempts
        result["recovery_existing_tasks_only"] = True
        result["existing_task_recovery_recovered"] = True
        result["existing_task_recovery_recovered_at"] = "2026-08-04 12:00:00"

    if provider_task_completed:
        result["provider_status"] = "succeeded"
        result["provider_finished"] = True

    if all_clips_downloaded:
        result["scene_clip_coverage_complete"] = True
        result["valid_scene_clip_count"] = scene_count
        result["completed_scene_count"] = scene_count

    if final_mp4_valid:
        result["final_mp4_valid"] = True
        result["concat_output_valid"] = True
        result["concat_attempted"] = True
        result["final_video_path"] = f"/tmp/final_{job_id}.mp4"

    conn.execute(
        """UPDATE video_jobs
              SET status=?, attempts=1, max_attempts=3, result_json=?, progress_percent=40
            WHERE id=?""",
        (job_status, json.dumps(result), job_id),
    )
    outbox = queue.ensure_product_video_dispatch_outbox(
        conn,
        job_id=job_id,
        project_id=project_id,
        scene_indexes=[1, 2],
    )
    conn.execute(
        "UPDATE video_dispatch_outbox SET dispatch_status=? WHERE outbox_id=?",
        (outbox_status, int(outbox["outbox_id"])),
    )
    conn.commit()
    return conn, job_id, project_id


# =========================================================================
# Case 1: Shared legacy counter collision FIRST RED
# =========================================================================
def test_pv06_shared_legacy_counter_collision_first_red(tmp_path: Path):
    """Prove that under unseparated quota, exhausting polling retries (count=3)
    collides with and blocks subsequent artifact download or finalizer recovery,
    even though artifact/finalizer recovery has consumed 0 attempts.
    """
    conn, job_id, project_id = _seed_pv06_test_job(
        tmp_path / "case1_collision.db",
        existing_poll_attempts=3,  # Polling quota exhausted at 3
        provider_task_completed=True,  # Provider task completed successfully
        all_clips_downloaded=False,  # But artifact download failed
    )
    recovery_time = datetime(2026, 8, 4, 13, 0, 0)

    # In the separated quota architecture:
    # Polling exhausted (3/3), but artifact download has 0/3.
    # Therefore, an artifact download recovery MUST BE ELIGIBLE!
    recovered = queue.recover_product_video_existing_tasks(
        conn,
        job_id=job_id,
        recovery_domain="provider_artifact",
        now=recovery_time,
    )
    # FIRST RED assertion: Under unseparated logic, this returns False with
    # 'existing_task_recovery_attempts_exhausted'.
    assert recovered["existing_task_recovery_recovered"] is True, (
        f"SHARED_RECOVERY_COUNTER_COLLISION: artifact recovery blocked by polling quota! "
        f"Block reason: {recovered.get('existing_task_recovery_block_reason')}"
    )


# =========================================================================
# Case 2: Poll retries consume poll quota only
# =========================================================================
def test_pv06_poll_retries_consume_poll_quota_only(tmp_path: Path):
    """Polling retries must increment provider_poll_recovery_count only,
    leaving provider_artifact, scene_clip, finalizer, and delivery quotas unchanged.
    """
    conn, job_id, project_id = _seed_pv06_test_job(
        tmp_path / "case2_poll.db",
        existing_poll_attempts=0,
    )
    base_time = datetime(2026, 8, 4, 12, 0, 0)

    for step in range(1, 4):
        now = base_time + timedelta(minutes=step * 2)
        recovered = queue.recover_product_video_existing_tasks(
            conn,
            job_id=job_id,
            recovery_domain="provider_poll",
            now=now,
        )
        assert recovered["existing_task_recovery_recovered"] is True
        job = queue.get_video_render_job(conn, job_id)
        res = json.loads(job["result_json"])
        assert res["provider_poll_recovery_count"] == step
        assert res.get("provider_artifact_recovery_count", 0) == 0
        assert res.get("scene_clip_recovery_count", 0) == 0
        assert res.get("finalizer_recovery_count", 0) == 0
        assert res.get("delivery_recovery_count", 0) == 0

        # Mark job failed again to simulate next retry
        conn.execute("UPDATE video_jobs SET status='failed' WHERE id=?", (job_id,))
        conn.execute("UPDATE video_projects SET status='failed' WHERE project_id=?", (project_id,))
        conn.commit()


# =========================================================================
# Case 3: Completed-provider artifact failure consumes artifact quota only
# =========================================================================
def test_pv06_artifact_failure_consumes_artifact_quota_only(tmp_path: Path):
    """Provider task completed, but artifact download fails.
    Artifact recovery must increment provider_artifact_recovery_count only.
    """
    conn, job_id, project_id = _seed_pv06_test_job(
        tmp_path / "case3_artifact.db",
        existing_poll_attempts=2,
        provider_task_completed=True,
        all_clips_downloaded=False,
    )
    now = datetime(2026, 8, 4, 12, 5, 0)
    recovered = queue.recover_product_video_existing_tasks(
        conn,
        job_id=job_id,
        recovery_domain="provider_artifact",
        now=now,
    )
    assert recovered["existing_task_recovery_recovered"] is True
    job = queue.get_video_render_job(conn, job_id)
    res = json.loads(job["result_json"])
    assert res["provider_poll_recovery_count"] == 2  # Unchanged
    assert res["provider_artifact_recovery_count"] == 1  # Incremented
    assert res.get("finalizer_recovery_count", 0) == 0
    assert res.get("delivery_recovery_count", 0) == 0


# =========================================================================
# Case 4: Artifact retry does not re-submit provider
# =========================================================================
def test_pv06_artifact_retry_does_not_resubmit_provider(tmp_path: Path):
    """Artifact retry must strictly enforce submit-free read-only recovery:
    provider_submit_allowed=False, automatic_resubmit_allowed=False, no new task IDs.
    """
    conn, job_id, project_id = _seed_pv06_test_job(
        tmp_path / "case4_no_resubmit.db",
        provider_task_completed=True,
    )
    now = datetime(2026, 8, 4, 12, 10, 0)
    recovered = queue.recover_product_video_existing_tasks(
        conn,
        job_id=job_id,
        recovery_domain="provider_artifact",
        now=now,
    )
    assert recovered["existing_task_recovery_recovered"] is True
    job = queue.get_video_render_job(conn, job_id)
    res = json.loads(job["result_json"])
    assert res["provider_submit_allowed"] is False
    assert res["automatic_resubmit_allowed"] is False
    assert res["automatic_retry_allowed"] is False
    assert res["automatic_fallback_allowed"] is False
    assert res["provider_task_ids"] == [TASK_SCENE_1, TASK_SCENE_2]


# =========================================================================
# Case 5: Finalizer retry consumes finalizer quota only
# =========================================================================
def test_pv06_finalizer_retry_consumes_finalizer_quota_only(tmp_path: Path):
    """All clips downloaded, but ffmpeg finalizer failed.
    Finalizer recovery must increment finalizer_recovery_count only.
    """
    conn, job_id, project_id = _seed_pv06_test_job(
        tmp_path / "case5_finalizer.db",
        existing_poll_attempts=1,
        provider_task_completed=True,
        all_clips_downloaded=True,
        final_mp4_valid=False,
    )
    now = datetime(2026, 8, 4, 12, 15, 0)
    recovered = queue.recover_product_video_existing_tasks(
        conn,
        job_id=job_id,
        recovery_domain="finalizer",
        now=now,
    )
    assert recovered["existing_task_recovery_recovered"] is True
    job = queue.get_video_render_job(conn, job_id)
    res = json.loads(job["result_json"])
    assert res["provider_poll_recovery_count"] == 1  # Unchanged
    assert res.get("provider_artifact_recovery_count", 0) == 0  # Unchanged
    assert res["finalizer_recovery_count"] == 1  # Incremented
    assert res.get("delivery_recovery_count", 0) == 0


# =========================================================================
# Case 6: Finalizer failure does not consume provider quota
# =========================================================================
def test_pv06_finalizer_failure_does_not_consume_provider_quota(tmp_path: Path):
    """Repeated finalizer failures consume only finalizer quota, never provider quota."""
    conn, job_id, project_id = _seed_pv06_test_job(
        tmp_path / "case6_finalizer_loop.db",
        existing_poll_attempts=1,
        provider_task_completed=True,
        all_clips_downloaded=True,
    )
    base_time = datetime(2026, 8, 4, 12, 0, 0)
    for attempt in range(1, 4):
        now = base_time + timedelta(minutes=attempt * 2)
        recovered = queue.recover_product_video_existing_tasks(
            conn,
            job_id=job_id,
            recovery_domain="finalizer",
            now=now,
        )
        assert recovered["existing_task_recovery_recovered"] is True
        job = queue.get_video_render_job(conn, job_id)
        res = json.loads(job["result_json"])
        assert res["provider_poll_recovery_count"] == 1  # Untouched
        assert res["finalizer_recovery_count"] == attempt

        conn.execute("UPDATE video_jobs SET status='failed' WHERE id=?", (job_id,))
        conn.execute("UPDATE video_projects SET status='failed' WHERE project_id=?", (project_id,))
        conn.commit()

    # Attempt 4 should exhaust finalizer quota
    exhausted = queue.recover_product_video_existing_tasks(
        conn,
        job_id=job_id,
        recovery_domain="finalizer",
        now=base_time + timedelta(minutes=10),
    )
    assert exhausted["existing_task_recovery_recovered"] is False
    reason = (
        exhausted.get("recovery_domain_block_reason")
        or exhausted.get("existing_task_recovery_block_reason")
    )
    assert "finalizer_recovery_attempts_exhausted" in reason


# =========================================================================
# Case 7: Delivery quota separation
# =========================================================================
def test_pv06_delivery_quota_separation(tmp_path: Path):
    """Delivery failure after valid final MP4 increments delivery quota only.
    Final MP4 remains valid, provider and finalizer counters unchanged.
    """
    conn, job_id, project_id = _seed_pv06_test_job(
        tmp_path / "case7_delivery.db",
        existing_poll_attempts=2,
        provider_task_completed=True,
        all_clips_downloaded=True,
        final_mp4_valid=True,
    )
    conn.execute(
        "UPDATE video_projects SET final_video_path='/tmp/final.mp4' WHERE project_id=?",
        (project_id,),
    )
    conn.commit()

    delivery_res = queue.note_video_delivery_result(
        conn,
        job_id=job_id,
        sent=False,
        reason="telegram_network_timeout",
    )
    assert delivery_res["ok"] is True
    assert delivery_res["sent"] is False

    proj = queue.get_video_project(conn, project_id)
    assert int(proj["delivery_attempt_count"]) == 1

    job = queue.get_video_render_job(conn, job_id)
    res = json.loads(job["result_json"])
    assert res.get("final_mp4_valid") is True
    assert res.get("provider_poll_recovery_count") == 2  # Untouched
    assert res.get("finalizer_recovery_count", 0) == 0  # Untouched


# =========================================================================
# Case 8: Terminal job cannot enter any recovery path
# =========================================================================
def test_pv06_terminal_job_cannot_enter_recovery(tmp_path: Path):
    """Terminal jobs (completed, cancelled, canceled, terminal_failed)
    must reject recovery across all domains.
    """
    for term_status in ("completed", "cancelled", "canceled", "terminal_failed"):
        conn, job_id, project_id = _seed_pv06_test_job(
            tmp_path / f"case8_{term_status}.db",
            job_status=term_status,
            project_status="failed" if term_status != "completed" else "completed",
        )
        for domain in ("provider_poll", "provider_artifact", "finalizer", "delivery"):
            recovered = queue.recover_product_video_existing_tasks(
                conn,
                job_id=job_id,
                recovery_domain=domain,
            )
            assert recovered["existing_task_recovery_recovered"] is False
            assert recovered["existing_task_recovery_block_reason"] in (
                "job_not_failed",
                "project_cancelled",
                "dispatch_outbox_cancelled",
            )


# =========================================================================
# Case 9: Lease/reclaim does not corrupt recovery quotas
# =========================================================================
def test_pv06_lease_reclaim_does_not_corrupt_recovery_quotas(tmp_path: Path):
    """Worker lease expiry and reclaim must not alter domain recovery budgets."""
    conn, job_id, project_id = _seed_pv06_test_job(
        tmp_path / "case9_lease.db",
        existing_poll_attempts=2,
    )
    job = queue.get_video_render_job(conn, job_id)
    res = json.loads(job["result_json"])
    res["provider_poll_recovery_count"] = 2
    res["provider_artifact_recovery_count"] = 1
    res["finalizer_recovery_count"] = 1
    res["delivery_recovery_count"] = 1
    conn.execute(
        "UPDATE video_jobs SET result_json=?, locked_by='worker-1', lease_expires_at='2026-08-04 11:00:00' WHERE id=?",
        (json.dumps(res), job_id),
    )
    conn.commit()

    reclaimed = queue.requeue_stale_video_jobs(conn, now=datetime(2026, 8, 4, 12, 0, 0))
    job_after = queue.get_video_render_job(conn, job_id)
    res_after = json.loads(job_after["result_json"])

    assert res_after["provider_poll_recovery_count"] == 2
    assert res_after["provider_artifact_recovery_count"] == 1
    assert res_after["finalizer_recovery_count"] == 1
    assert res_after["delivery_recovery_count"] == 1


# =========================================================================
# Case 10: Recovery counters survive DB reopen
# =========================================================================
def test_pv06_recovery_counters_survive_db_reopen(tmp_path: Path):
    """Recovery counters must be durably persisted and survive DB close/reopen."""
    db_file = tmp_path / "case10_durability.db"
    conn, job_id, project_id = _seed_pv06_test_job(
        db_file,
        existing_poll_attempts=1,
    )
    recovered = queue.recover_product_video_existing_tasks(
        conn,
        job_id=job_id,
        recovery_domain="provider_poll",
        now=datetime(2026, 8, 4, 12, 5, 0),
    )
    assert recovered["existing_task_recovery_recovered"] is True
    conn.close()

    conn2 = sqlite3.connect(db_file)
    conn2.row_factory = sqlite3.Row
    job = queue.get_video_render_job(conn2, job_id)
    res = json.loads(job["result_json"])
    assert res["provider_poll_recovery_count"] == 2
    assert res.get("provider_artifact_recovery_count", 0) == 0
    conn2.close()


# =========================================================================
# Case 11: Duplicate recovery event does not double increment (Idempotency)
# =========================================================================
def test_pv06_duplicate_recovery_event_idempotency(tmp_path: Path):
    """Replaying the exact same recovery event with identical idempotency token
    must not double-increment the domain counter.
    """
    conn, job_id, project_id = _seed_pv06_test_job(
        tmp_path / "case11_idempotency.db",
        existing_poll_attempts=1,
        provider_task_completed=True,
    )
    now = datetime(2026, 8, 4, 12, 5, 0)
    token = "token-artifact-failure-receipt-123"

    first = queue.recover_product_video_existing_tasks(
        conn,
        job_id=job_id,
        recovery_domain="provider_artifact",
        idempotency_key=token,
        now=now,
    )
    assert first["existing_task_recovery_recovered"] is True

    job1 = queue.get_video_render_job(conn, job_id)
    res1 = json.loads(job1["result_json"])
    assert res1["provider_artifact_recovery_count"] == 1

    second = queue.recover_product_video_existing_tasks(
        conn,
        job_id=job_id,
        recovery_domain="provider_artifact",
        idempotency_key=token,
        now=now,
    )
    assert second.get("duplicate_prevented") is True or second["existing_task_recovery_recovered"] is True

    job2 = queue.get_video_render_job(conn, job_id)
    res2 = json.loads(job2["result_json"])
    assert res2["provider_artifact_recovery_count"] == 1


# =========================================================================
# Case 12: Exhaustion reports correct domain
# =========================================================================
def test_pv06_exhaustion_reports_correct_domain(tmp_path: Path):
    """When a domain exhausts, the failure report must pinpoint the exact domain."""
    conn, job_id, project_id = _seed_pv06_test_job(
        tmp_path / "case12_exhaustion.db",
        existing_poll_attempts=0,
        provider_task_completed=True,
    )
    job = queue.get_video_render_job(conn, job_id)
    res = json.loads(job["result_json"])
    res["provider_artifact_recovery_count"] = 3
    conn.execute("UPDATE video_jobs SET result_json=? WHERE id=?", (json.dumps(res), job_id))
    conn.commit()

    exhausted = queue.recover_product_video_existing_tasks(
        conn,
        job_id=job_id,
        recovery_domain="provider_artifact",
        now=datetime(2026, 8, 4, 12, 0, 0),
    )
    assert exhausted["existing_task_recovery_recovered"] is False
    reason = (
        exhausted.get("recovery_domain_block_reason")
        or exhausted.get("existing_task_recovery_block_reason")
    )
    assert reason == "provider_artifact_recovery_attempts_exhausted"
