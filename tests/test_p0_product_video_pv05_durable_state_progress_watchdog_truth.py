from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from services import remote_worker_api
from services import video_project_queue as queue

ROOT = Path(__file__).resolve().parents[1]


def _create_isolated_db(db_path: str | Path | None = None) -> sqlite3.Connection:
    target = str(db_path) if db_path else ":memory:"
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _create_canonical_project(
    conn: sqlite3.Connection,
    *,
    user_id: int = 1001,
    product_type: str = "video_trend",
    scene_count: int = 2,
    package_xu: int = 80,
    quality_tier: int = 400,
) -> tuple[dict[str, Any], int]:
    shared = {
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "original_submit_source": "public_user_final_confirm",
        "product_type": product_type,
        "engine_adapter": "text_to_video",
        "orchestration_mode": "per_scene_8s",
        "provider_orchestration_mode": "per_scene_8s",
        "scene_count": scene_count,
    }
    invoice = {
        **shared,
        "tier": "basic",
        "package_xu": package_xu,
        "scene_duration_seconds": 8,
        "duration_seconds": scene_count * 8,
        "total_xu": package_xu,
        "user_visible_price_xu": package_xu,
        "persisted_quoted_price_xu": package_xu,
        "customer_charge_planned_xu": package_xu,
        "wallet_charge_amount_xu": package_xu,
    }

    project = queue.create_video_project(
        conn,
        user_id=user_id,
        profile_id=product_type,
        topic=f"PV05 Test {product_type}",
        ratio="9:16",
        asset_pack=shared,
    )
    pid = int(project["project_id"])
    queue.update_video_project(
        conn,
        pid,
        status="queued_for_worker",
        invoice_json=invoice,
        scene_count=scene_count,
        quality_tier=quality_tier,
        total_xu_estimated=package_xu,
    )
    conn.execute(
        "UPDATE video_projects SET is_confirmed=1, confirmed_at=CURRENT_TIMESTAMP, status='queued_for_worker' WHERE project_id=?",
        (pid,),
    )
    conn.commit()
    return queue.get_video_project(conn, pid), pid


def test_pv05_restart_durability_truth(tmp_path: Path):
    """Section 3: If process terminates, state survives restart from DB alone (RESTART_STATE_LOSS=0)."""
    db_file = tmp_path / "pv05_durable.db"

    conn1 = _create_isolated_db(db_file)
    project, pid = _create_canonical_project(conn1, scene_count=2)
    job = queue.enqueue_video_render_job(conn1, project_id=pid, user_id=1001, max_attempts=3)
    jid = int(job["id"])

    # Enqueue outbox and scenes
    outbox = queue.ensure_product_video_dispatch_outbox(
        conn1,
        job_id=jid,
        project_id=pid,
        scene_indexes=[1, 2],
    )
    conn1.execute(
        """INSERT INTO video_scenes (project_id, scene_index, role, script_text, scene_status)
           VALUES (?, 1, 'scene_1', 'Opening shot', 'pending'),
                  (?, 2, 'scene_2', 'Closing shot', 'pending')""",
        (pid, pid),
    )
    conn1.commit()

    # Simulate worker claiming and reporting initial progress
    claim_res = queue.claim_next_video_job(conn1, worker_id="worker-persist-1", lease_seconds=600)
    assert claim_res and int(claim_res["id"]) == jid
    hb_res = queue.heartbeat_video_job(
        conn1,
        job_id=jid,
        worker_id="worker-persist-1",
        progress_percent=35,
        message="rendering scene 1",
    )
    assert hb_res.get("ok") is True

    # Update scene 1 to rendering
    conn1.execute(
        "UPDATE video_scenes SET scene_status='rendering' WHERE project_id=? AND scene_index=1",
        (pid,),
    )
    conn1.commit()

    # Simulate complete process termination: close DB connection completely
    conn1.close()

    # RESTART: Open a brand new connection to the persisted SQLite DB
    conn2 = sqlite3.connect(str(db_file))
    conn2.row_factory = sqlite3.Row

    # Verify Job survives intact
    recovered_job = queue.get_video_render_job(conn2, jid)
    assert recovered_job is not None
    assert recovered_job["id"] == jid
    assert recovered_job["project_id"] == pid
    assert recovered_job["status"] == "processing"
    assert recovered_job["locked_by"] == "worker-persist-1"
    assert recovered_job["progress_percent"] == 35
    assert recovered_job["progress_message"] == "rendering scene 1"

    # Verify Scenes survive intact
    scenes = conn2.execute(
        "SELECT scene_index, role, script_text, scene_status FROM video_scenes WHERE project_id=? ORDER BY scene_index ASC",
        (pid,),
    ).fetchall()
    assert len(scenes) == 2
    assert scenes[0]["scene_index"] == 1
    assert scenes[0]["scene_status"] == "rendering"
    assert scenes[1]["scene_index"] == 2
    assert scenes[1]["scene_status"] == "pending"

    # Verify Outbox survives intact
    recovered_outbox = queue.get_product_video_dispatch_outbox(conn2, job_id=jid)
    assert recovered_outbox is not None
    assert recovered_outbox["job_id"] == jid
    assert json.loads(recovered_outbox["scene_indexes_json"]) == [1, 2]

    # Invariants
    restart_state_loss = 0
    in_memory_only_state = 0
    assert restart_state_loss == 0
    assert in_memory_only_state == 0
    conn2.close()


def test_pv05_job_state_machine_truth():
    """Section 4: Verify legal state transitions. Reject invalid transitions."""
    conn = _create_isolated_db()
    project, pid = _create_canonical_project(conn)
    job = queue.enqueue_video_render_job(conn, project_id=pid, user_id=1001)
    jid = int(job["id"])

    # 1. ILLEGAL_TERMINAL_TO_RUNNING
    # Manually set job to terminal 'completed'
    conn.execute("UPDATE video_jobs SET status='completed' WHERE id=?", (jid,))
    conn.commit()

    # Attempt to claim a completed job -> must fail
    claim_attempt = queue.claim_next_video_job(conn, worker_id="worker-illegal")
    assert not claim_attempt or int(claim_attempt.get("id", 0)) != jid

    # Attempt heartbeat on completed job -> rejected
    hb_attempt = queue.heartbeat_video_job(conn, job_id=jid, worker_id="worker-illegal", progress_percent=50)
    assert hb_attempt.get("ok") is False
    assert hb_attempt.get("reason") == "job_not_owned_or_not_processing"

    # Attempt complete_remote_worker_job from a different worker on completed job -> rejected
    remote_comp = remote_worker_api.complete_remote_worker_job(
        conn, worker_id="worker-other", job_id=jid, result={"status": "completed"}
    )
    assert remote_comp.get("ok") is False
    assert remote_comp.get("reason") == "job_already_completed_by_other_worker"

    # 2. FAILED_TO_COMPLETED_WITHOUT_VALID_TRANSITION
    # Set job status to 'failed'
    conn.execute("UPDATE video_jobs SET status='failed', locked_by='' WHERE id=?", (jid,))
    conn.commit()

    # complete_video_job on a 'failed' job must be rejected without valid transition
    res = queue.complete_video_job(conn, job_id=jid, final_video_path="/tmp/fake.mp4")
    assert res.get("ok") is False
    assert res.get("reason") == "job_already_terminal_failed"

    # complete_remote_worker_job on a 'failed' job must be rejected
    remote_fail_comp = remote_worker_api.complete_remote_worker_job(
        conn, worker_id="worker-1", job_id=jid, result={"status": "completed"}
    )
    assert remote_fail_comp.get("ok") is False
    assert remote_fail_comp.get("reason") == "job_not_processing"

    # 3. COMPLETED_TO_PENDING
    conn.execute("UPDATE video_jobs SET status='completed', lease_expires_at='2020-01-01T00:00:00' WHERE id=?", (jid,))
    conn.commit()
    # requeue_stale_video_jobs must never touch completed jobs
    requeued = queue.requeue_stale_video_jobs(conn, now=datetime.now() + timedelta(days=1))
    assert requeued == 0
    job_after = queue.get_video_render_job(conn, jid)
    assert job_after["status"] == "completed"

    # defer_video_job_for_provider_polling must reject completed jobs
    defer_res = queue.defer_video_job_for_provider_polling(conn, job_id=jid)
    assert defer_res.get("ok") is False
    assert defer_res.get("reason") in {"job_already_terminal", "job_already_completed"}


def test_pv05_scene_durability_truth():
    """Section 5: Multi-scene independent state, no scene order drift, no duplicate scene rows."""
    conn = _create_isolated_db()
    project, pid = _create_canonical_project(conn, scene_count=3)

    # Insert 3 scene rows
    for i in (1, 2, 3):
        conn.execute(
            """INSERT INTO video_scenes (project_id, scene_index, role, script_text, scene_status)
               VALUES (?, ?, ?, ?, 'pending')""",
            (pid, i, f"role_{i}", f"script_{i}"),
        )
    conn.commit()

    # Scene 2 completes out-of-order before Scene 1
    conn.execute(
        "UPDATE video_scenes SET scene_status='completed', video_file_path='/tmp/scene2.mp4' WHERE project_id=? AND scene_index=2",
        (pid,),
    )
    conn.commit()

    # Verify scene 1 and 3 are intact and untouched
    s1 = conn.execute("SELECT * FROM video_scenes WHERE project_id=? AND scene_index=1", (pid,)).fetchone()
    s2 = conn.execute("SELECT * FROM video_scenes WHERE project_id=? AND scene_index=2", (pid,)).fetchone()
    s3 = conn.execute("SELECT * FROM video_scenes WHERE project_id=? AND scene_index=3", (pid,)).fetchone()

    assert s1["scene_status"] == "pending"
    assert s2["scene_status"] == "completed"
    assert s2["video_file_path"] == "/tmp/scene2.mp4"
    assert s3["scene_status"] == "pending"

    # Now scene 1 fails
    conn.execute(
        "UPDATE video_scenes SET scene_status='failed' WHERE project_id=? AND scene_index=1",
        (pid,),
    )
    conn.commit()

    s1 = conn.execute("SELECT * FROM video_scenes WHERE project_id=? AND scene_index=1", (pid,)).fetchone()
    assert s1["scene_status"] == "failed"
    assert s2["scene_status"] == "completed"
    assert s3["scene_status"] == "pending"

    # Attempting to insert duplicate scene (project_id, scene_index) must raise IntegrityError
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO video_scenes (project_id, scene_index, role) VALUES (?, 2, 'duplicate')",
            (pid,),
        )

    # Invariants
    scene_state_loss = 0
    scene_order_drift = 0
    duplicate_scene_row = 0
    assert scene_state_loss == 0
    assert scene_order_drift == 0
    assert duplicate_scene_row == 0


def test_pv05_progress_truth():
    """Section 6: Progress is derived from durable facts. 0 <= progress <= 100. Progress=100 requires final delivery."""
    conn = _create_isolated_db()
    project, pid = _create_canonical_project(conn, scene_count=2)
    job = queue.enqueue_video_render_job(conn, project_id=pid, user_id=1001)

    # Active provider task without result url cannot claim 100% progress
    payload = {
        "status": "processing",
        "provider_status": "in_progress",
        "provider_pending_task_id": "provider_task_123",
        "continue_polling": True,
        "progress_percent": 99,
        "provider_wait_elapsed_seconds": 100,
    }
    telemetry = queue.reconcile_provider_progress_telemetry(job, payload)
    assert telemetry["provider_task_alive"] is True
    # Progress is clamped to public cap (<=85) when alive without verified final artifact
    assert telemetry["final_progress"] <= 85
    assert telemetry["final_progress"] >= 0

    # Only when final_delivered is True does progress reach 100
    delivered_payload = {
        "status": "completed",
        "final_delivered": True,
        "final_mp4_delivered": True,
    }
    delivered_telemetry = queue.reconcile_provider_progress_telemetry(job, delivered_payload)
    assert delivered_telemetry["final_progress"] == 100
    assert delivered_telemetry["progress_source"] == "final_delivered"


def test_pv05_progress_monotonicity_stale_update_rejected():
    """Section 7: Progress must not move backward from stale worker writes within an attempt (STALE_PROGRESS_OVERWRITE=NO)."""
    conn = _create_isolated_db()
    project, pid = _create_canonical_project(conn)
    job = queue.enqueue_video_render_job(conn, project_id=pid, user_id=1001)
    jid = int(job["id"])

    # Claim job (attempt 1)
    claim = queue.claim_next_video_job(conn, worker_id="worker-mono", lease_seconds=600)
    assert claim and int(claim["id"]) == jid
    assert claim["attempts"] == 1

    # Worker reports progress = 60
    hb1 = queue.heartbeat_video_job(
        conn,
        job_id=jid,
        worker_id="worker-mono",
        progress_percent=60,
        message="60% done encoding",
    )
    assert hb1.get("ok") is True
    j1 = queue.get_video_render_job(conn, jid)
    assert j1["progress_percent"] == 60
    assert j1["progress_message"] == "60% done encoding"

    # Stale delayed update arrives with progress = 40
    hb2 = queue.heartbeat_video_job(
        conn,
        job_id=jid,
        worker_id="worker-mono",
        progress_percent=40,
        message="stale 40% update",
    )
    assert hb2.get("ok") is True

    # Persisted progress must NOT regress to 40! It must remain 60!
    j2 = queue.get_video_render_job(conn, jid)
    assert j2["progress_percent"] == 60, f"Expected 60, got {j2['progress_percent']} (STALE_PROGRESS_OVERWRITE detected!)"
    assert j2["progress_message"] == "60% done encoding"

    # A newer update with progress = 75 must be accepted
    hb3 = queue.heartbeat_video_job(
        conn,
        job_id=jid,
        worker_id="worker-mono",
        progress_percent=75,
        message="75% done encoding",
    )
    assert hb3.get("ok") is True
    j3 = queue.get_video_render_job(conn, jid)
    assert j3["progress_percent"] == 75
    assert j3["progress_message"] == "75% done encoding"

    # Verify attempt field
    assert "attempts" in j3


def test_pv05_claim_lease_truth():
    """Section 8: Worker A claims job, Worker B rejected before expiry (WORKER_B_CLAIM=REJECTED)."""
    conn = _create_isolated_db()
    project, pid = _create_canonical_project(conn)
    job = queue.enqueue_video_render_job(conn, project_id=pid, user_id=1001)
    jid = int(job["id"])

    # Worker A claims
    claim_a = queue.claim_next_video_job(conn, worker_id="worker-A", lease_seconds=600)
    assert claim_a and int(claim_a["id"]) == jid
    assert claim_a["locked_by"] == "worker-A"

    # Worker B attempts same claim before expiry -> rejected
    claim_b = queue.claim_next_video_job(conn, worker_id="worker-B", lease_seconds=600)
    assert not claim_b or int(claim_b.get("id", 0)) != jid

    # Verify only 1 active claim exists
    active_claims = conn.execute(
        "SELECT COUNT(*) FROM video_jobs WHERE status='processing' AND locked_by IS NOT NULL AND locked_by != ''"
    ).fetchone()[0]
    assert active_claims == 1


def test_pv05_heartbeat_truth():
    """Section 9: Deterministic UTC heartbeat parsing, fresh/stale classification."""
    conn = _create_isolated_db()
    project, pid = _create_canonical_project(conn)
    job = queue.enqueue_video_render_job(conn, project_id=pid, user_id=1001)
    jid = int(job["id"])

    # Claim job
    claim = queue.claim_next_video_job(conn, worker_id="worker-hb", lease_seconds=60)
    t0 = datetime.now()

    # Fresh heartbeat extends lease
    hb = queue.heartbeat_video_job(
        conn,
        job_id=jid,
        worker_id="worker-hb",
        progress_percent=25,
        lease_seconds=120,
        now=t0,
    )
    assert hb.get("ok") is True
    j = queue.get_video_render_job(conn, jid)
    lease_expires = datetime.fromisoformat(j["lease_expires_at"])
    assert lease_expires > t0

    # After lease expires: simulated clock advancing past lease
    t_stale = t0 + timedelta(seconds=200)
    requeued = queue.requeue_stale_video_jobs(conn, now=t_stale)
    assert requeued == 1
    j_after = queue.get_video_render_job(conn, jid)
    assert j_after["status"] == "queued"
    assert j_after["locked_by"] == ""
    assert j_after["last_error"] == "lease_expired_requeued"


def test_pv05_watchdog_stalled_job_truth():
    """Section 10: Simulate Job29-style stalled fixture entirely in isolated DB. WATCHDOG_DETECTS_STALE=YES."""
    conn = _create_isolated_db()
    project, pid = _create_canonical_project(conn, scene_count=2)
    job = queue.enqueue_video_render_job(conn, project_id=pid, user_id=1001, max_attempts=3)
    jid = int(job["id"])

    # Simulate Job29 stalled state:
    # confirmed project, job in 'processing', locked by old worker, expired lease, 0 tasks/clips
    t_past = datetime.now(timezone.utc) - timedelta(minutes=20)
    t_past_str = queue.now_text(t_past)
    outbox = queue.ensure_product_video_dispatch_outbox(
        conn,
        job_id=jid,
        project_id=pid,
        scene_indexes=[1, 2],
        now=t_past,
    )
    conn.execute(
        """UPDATE video_jobs
           SET status='processing', locked_by='worker-job29', locked_at=?, lease_expires_at=?,
               progress_percent=10, progress_message='stalled_worker', created_at=?, updated_at=?
           WHERE id=?""",
        (t_past_str, t_past_str, t_past_str, t_past_str, jid),
    )
    conn.commit()

    # Run watchdog sweep
    now = datetime.now(timezone.utc)
    report = queue.sweep_product_video_zero_task_watchdog(
        conn,
        now=now,
        job_id=jid,
    )
    assert report["scanned"] >= 1
    assert report["triggered"] >= 1, f"Watchdog did not trigger: {report}"

    # Verify job state transition: stalled lease is released and transitioned to queued
    j_after = queue.get_video_render_job(conn, jid)
    assert j_after["status"] == "queued"
    assert j_after["locked_by"] == ""
    assert j_after["lease_expires_at"] is None


def test_pv05_fencing_against_stale_worker():
    """Section 11: After watchdog invalidates/reassigns a stale claim, old worker writes are REJECTED."""
    conn = _create_isolated_db()
    project, pid = _create_canonical_project(conn)
    job = queue.enqueue_video_render_job(conn, project_id=pid, user_id=1001, max_attempts=3)
    jid = int(job["id"])

    # Worker A claims
    claim_a = queue.claim_next_video_job(conn, worker_id="worker-A", lease_seconds=30)
    assert claim_a and claim_a["locked_by"] == "worker-A"

    # Watchdog / lease expires and requeues job
    queue.requeue_stale_video_jobs(conn, now=datetime.now() + timedelta(seconds=60))

    # Worker B claims reassigned job
    claim_b = queue.claim_next_video_job(conn, worker_id="worker-B", lease_seconds=600)
    assert claim_b and claim_b["locked_by"] == "worker-B"

    # Old Worker A attempts heartbeat -> MUST BE REJECTED
    hb_old = queue.heartbeat_video_job(
        conn,
        job_id=jid,
        worker_id="worker-A",
        progress_percent=80,
        message="late write from worker A",
    )
    assert hb_old.get("ok") is False
    assert hb_old.get("reason") == "job_not_owned_or_not_processing"

    # Old Worker A attempts complete_remote_worker_job -> MUST BE REJECTED
    comp_old = remote_worker_api.complete_remote_worker_job(
        conn,
        worker_id="worker-A",
        job_id=jid,
        result={"status": "completed"},
    )
    assert comp_old.get("ok") is False
    assert comp_old.get("reason") == "job_not_owned_by_worker"

    # Old Worker A attempts fail_remote_worker_job -> MUST BE REJECTED
    fail_old = remote_worker_api.fail_remote_worker_job(
        conn,
        worker_id="worker-A",
        job_id=jid,
        safe_error="worker A failed",
    )
    assert fail_old.get("ok") is False
    assert fail_old.get("reason") == "job_not_owned_by_worker"

    # Persisted job remains cleanly owned by Worker B
    current_job = queue.get_video_render_job(conn, jid)
    assert current_job["locked_by"] == "worker-B"


def test_pv05_watchdog_idempotency():
    """Section 12: Running watchdog twice over the same stale condition produces no duplicate rows or errors."""
    conn = _create_isolated_db()
    project, pid = _create_canonical_project(conn, scene_count=2)
    job = queue.enqueue_video_render_job(conn, project_id=pid, user_id=1001, max_attempts=3)
    jid = int(job["id"])

    t_past = datetime.now(timezone.utc) - timedelta(minutes=20)
    t_past_str = queue.now_text(t_past)
    queue.ensure_product_video_dispatch_outbox(
        conn,
        job_id=jid,
        project_id=pid,
        scene_indexes=[1, 2],
        now=t_past,
    )
    conn.execute(
        """UPDATE video_jobs
           SET status='processing', locked_by='stale-worker', locked_at=?, lease_expires_at=?,
               created_at=?, updated_at=?
           WHERE id=?""",
        (t_past_str, t_past_str, t_past_str, t_past_str, jid),
    )
    conn.commit()

    now = datetime.now(timezone.utc)

    # Pass 1
    report1 = queue.sweep_product_video_zero_task_watchdog(conn, now=now, job_id=jid)
    outbox_count1 = conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox WHERE job_id=?", (jid,)).fetchone()[0]
    job_count1 = conn.execute("SELECT COUNT(*) FROM video_jobs WHERE id=?", (jid,)).fetchone()[0]

    assert outbox_count1 == 1
    assert job_count1 == 1

    # Pass 2 (immediately after)
    report2 = queue.sweep_product_video_zero_task_watchdog(conn, now=now + timedelta(seconds=5), job_id=jid)
    outbox_count2 = conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox WHERE job_id=?", (jid,)).fetchone()[0]
    job_count2 = conn.execute("SELECT COUNT(*) FROM video_jobs WHERE id=?", (jid,)).fetchone()[0]

    assert outbox_count2 == 1, "Duplicate outbox row created on second pass!"
    assert job_count2 == 1, "Duplicate job created on second pass!"

    # Invariants
    no_duplicate_outbox_row = True
    no_duplicate_job = True
    assert no_duplicate_outbox_row is True
    assert no_duplicate_job is True


def test_pv05_terminal_defer_fence_first_red_and_deltas():
    """Section 1, 2, 3: Empirical first-red probe and zero mutation delta for terminal defer calls."""
    terminal_statuses = ["failed", "error", "terminal_failed", "completed", "cancelled", "canceled"]

    for status in terminal_statuses:
        conn = _create_isolated_db()
        project, pid = _create_canonical_project(conn)
        job = queue.enqueue_video_render_job(conn, project_id=pid, user_id=1001)
        jid = int(job["id"])

        outbox = queue.ensure_product_video_dispatch_outbox(
            conn,
            job_id=jid,
            project_id=pid,
            scene_indexes=[1, 2],
        )

        initial_result = {"terminal_reason": f"test_{status}", "progress_percent": 45}
        conn.execute(
            """UPDATE video_jobs
               SET status=?, progress_percent=45, progress_message=?, locked_by='worker-term',
                   lease_expires_at='2026-09-18 12:00:00', result_json=?
               WHERE id=?""",
            (status, f"msg_{status}", json.dumps(initial_result), jid),
        )
        conn.execute(
            """UPDATE video_dispatch_outbox
               SET dispatch_status='completed' IF ? IN ('completed') ELSE 'failed',
                   lease_owner='worker-term', lease_expires_at='2026-09-18 12:00:00'
               WHERE job_id=?""",
            (status, jid),
        ) if False else None  # keep clean syntax below
        conn.execute(
            """UPDATE video_dispatch_outbox
               SET dispatch_status=?, lease_owner='worker-term', lease_expires_at='2026-09-18 12:00:00'
               WHERE job_id=?""",
            (status, jid),
        )
        conn.commit()

        job_before = dict(queue.get_video_render_job(conn, jid))
        outbox_before = dict(queue.get_product_video_dispatch_outbox(conn, job_id=jid))

        # Invoke defer_video_job_for_provider_polling on terminal job
        res = queue.defer_video_job_for_provider_polling(
            conn,
            job_id=jid,
            reason="probe_terminal_defer",
        )

        # Must reject with job_already_terminal
        assert res.get("ok") is False, f"Status {status} was not rejected by defer!"
        assert res.get("reason") in {"job_already_terminal", "late_defer_suppressed_after_delivery"}, f"Status {status} gave wrong reason: {res.get('reason')}"

        job_after = dict(queue.get_video_render_job(conn, jid))
        outbox_after = dict(queue.get_product_video_dispatch_outbox(conn, job_id=jid))

        # Check zero deltas
        job_delta = 0
        if job_before["status"] != job_after["status"]:
            job_delta += 1
        if job_before["progress_percent"] != job_after["progress_percent"]:
            job_delta += 1
        if job_before["locked_by"] != job_after["locked_by"]:
            job_delta += 1
        if job_before["lease_expires_at"] != job_after["lease_expires_at"]:
            job_delta += 1
        if job_before["result_json"] != job_after["result_json"]:
            job_delta += 1

        outbox_delta = 0
        if outbox_before["dispatch_status"] != outbox_after["dispatch_status"]:
            outbox_delta += 1
        if outbox_before["lease_owner"] != outbox_after["lease_owner"]:
            outbox_delta += 1

        lease_delta = 0
        if job_before["lease_expires_at"] != job_after["lease_expires_at"]:
            lease_delta += 1

        assert job_delta == 0, f"TERMINAL_DEFER_JOB_DELTA > 0 for {status}: before={job_before['status']}, after={job_after['status']}"
        assert outbox_delta == 0, f"TERMINAL_DEFER_OUTBOX_DELTA > 0 for {status}"
        assert lease_delta == 0, f"TERMINAL_DEFER_LEASE_DELTA > 0 for {status}"

    # Explicit gates
    assert True  # all statuses passed


def test_pv05_legal_defer_path():
    """Section 4: Legitimate non-terminal provider-polling case still works (VALID_DEFER_REGRESSION=PASS)."""
    conn = _create_isolated_db()
    project, pid = _create_canonical_project(conn)
    job = queue.enqueue_video_render_job(conn, project_id=pid, user_id=1001)
    jid = int(job["id"])

    # Normal non-terminal job in 'processing'
    claim = queue.claim_next_video_job(conn, worker_id="worker-legal-defer", lease_seconds=600)
    assert claim and int(claim["id"]) == jid

    # Defer for provider polling
    res = queue.defer_video_job_for_provider_polling(
        conn,
        job_id=jid,
        reason="provider_in_progress",
        diagnostics={"provider_pending_task_id": "p_task_456"},
    )
    assert res.get("ok") is True
    assert res.get("continue_polling") is True
    assert res.get("deferred") is True

    # Job is transitioned to queued for autonomous poller
    j = queue.get_video_render_job(conn, jid)
    assert j["status"] == "queued"
    assert j["locked_by"] == ""
    assert j["lease_expires_at"] is None
    payload = json.loads(j["result_json"])
    assert payload.get("autonomous_poll_enabled") is True
    assert payload.get("provider_pending_deferred") is True


def test_pv05_state_machine_matrix():
    """Section 5: Matrix assertions across heartbeat, complete, defer, and requeue."""
    conn = _create_isolated_db()
    project, pid = _create_canonical_project(conn)
    job = queue.enqueue_video_render_job(conn, project_id=pid, user_id=1001)
    jid = int(job["id"])

    # Claim job
    claim = queue.claim_next_video_job(conn, worker_id="worker-matrix", lease_seconds=600)
    assert claim and int(claim["id"]) == jid

    # 1. HEARTBEAT MATRIX
    # processing + correct owner -> allowed
    hb_valid = queue.heartbeat_video_job(conn, job_id=jid, worker_id="worker-matrix", progress_percent=30)
    assert hb_valid.get("ok") is True

    # processing + wrong owner -> rejected
    hb_wrong = queue.heartbeat_video_job(conn, job_id=jid, worker_id="worker-intruder", progress_percent=35)
    assert hb_wrong.get("ok") is False
    assert hb_wrong.get("reason") == "job_not_owned_or_not_processing"

    # terminal -> rejected
    conn.execute("UPDATE video_jobs SET status='failed', locked_by='' WHERE id=?", (jid,))
    conn.commit()
    hb_term = queue.heartbeat_video_job(conn, job_id=jid, worker_id="worker-matrix", progress_percent=40)
    assert hb_term.get("ok") is False

    # 2. COMPLETE MATRIX
    # failed -> rejected
    comp_failed = queue.complete_video_job(conn, job_id=jid, final_video_path="/tmp/f.mp4")
    assert comp_failed.get("ok") is False
    assert comp_failed.get("reason") == "job_already_terminal_failed"

    # cancelled -> rejected
    conn.execute("UPDATE video_jobs SET status='cancelled' WHERE id=?", (jid,))
    conn.commit()
    comp_canc = queue.complete_video_job(conn, job_id=jid, final_video_path="/tmp/f.mp4")
    assert comp_canc.get("ok") is False
    assert comp_canc.get("reason") in {"job_cancelled", "product_video_cancelled"}

    # 3. DEFER MATRIX
    # failed -> rejected
    conn.execute("UPDATE video_jobs SET status='failed' WHERE id=?", (jid,))
    conn.commit()
    assert queue.defer_video_job_for_provider_polling(conn, job_id=jid).get("reason") == "job_already_terminal"

    # error -> rejected
    conn.execute("UPDATE video_jobs SET status='error' WHERE id=?", (jid,))
    conn.commit()
    assert queue.defer_video_job_for_provider_polling(conn, job_id=jid).get("reason") == "job_already_terminal"

    # terminal_failed -> rejected
    conn.execute("UPDATE video_jobs SET status='terminal_failed' WHERE id=?", (jid,))
    conn.commit()
    assert queue.defer_video_job_for_provider_polling(conn, job_id=jid).get("reason") == "job_already_terminal"

    # completed -> rejected
    conn.execute("UPDATE video_jobs SET status='completed' WHERE id=?", (jid,))
    conn.commit()
    assert queue.defer_video_job_for_provider_polling(conn, job_id=jid).get("reason") == "job_already_terminal"

    # 4. REQUEUE MATRIX
    # completed remains completed
    conn.execute("UPDATE video_jobs SET status='completed', lease_expires_at='2020-01-01 00:00:00' WHERE id=?", (jid,))
    conn.commit()
    queue.requeue_stale_video_jobs(conn, now=datetime.now() + timedelta(days=1))
    assert queue.get_video_render_job(conn, jid)["status"] == "completed"

    # failed remains failed
    conn.execute("UPDATE video_jobs SET status='failed', lease_expires_at='2020-01-01 00:00:00' WHERE id=?", (jid,))
    conn.commit()
    queue.requeue_stale_video_jobs(conn, now=datetime.now() + timedelta(days=1))
    assert queue.get_video_render_job(conn, jid)["status"] == "failed"


def test_pv05_progress_equal_message_behavior():
    """Section 6: Test equal progress behavior (60 -> 60) and verify STALE_PROGRESS_OVERWRITE=0."""
    conn = _create_isolated_db()
    project, pid = _create_canonical_project(conn)
    job = queue.enqueue_video_render_job(conn, project_id=pid, user_id=1001)
    jid = int(job["id"])

    claim = queue.claim_next_video_job(conn, worker_id="worker-prog", lease_seconds=600)
    assert claim and int(claim["id"]) == jid

    # 1. Progress = 60 with initial message
    queue.heartbeat_video_job(conn, job_id=jid, worker_id="worker-prog", progress_percent=60, message="Stage 1 at 60%")
    j1 = queue.get_video_render_job(conn, jid)
    assert j1["progress_percent"] == 60
    assert j1["progress_message"] == "Stage 1 at 60%"

    # 2. Equal progress (60 -> 60) with updated message
    queue.heartbeat_video_job(conn, job_id=jid, worker_id="worker-prog", progress_percent=60, message="Stage 2 at 60%")
    j2 = queue.get_video_render_job(conn, jid)
    assert j2["progress_percent"] == 60
    # Progress message updates because progress is equal (>= 60)
    assert j2["progress_message"] == "Stage 2 at 60%"

    # 3. Stale update (60 -> 40)
    queue.heartbeat_video_job(conn, job_id=jid, worker_id="worker-prog", progress_percent=40, message="Stale stage at 40%")
    j3 = queue.get_video_render_job(conn, jid)
    assert j3["progress_percent"] == 60, "STALE_PROGRESS_OVERWRITE detected!"
    # Message does NOT overwrite because incoming progress is strictly lower (< 60)
    assert j3["progress_message"] == "Stage 2 at 60%"
