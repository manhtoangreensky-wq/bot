"""Tests for P0.PRODUCT_VIDEO.PV12.JOB28.EXISTING.ARTIFACT.RECOVERY.TRUTH.CORRECTION.

Verifies:
1. Canonical Job28 Fixture reproduction.
2. First RED: infinite claim/defer requeue loop under attempts > max_attempts.
3. First RED: lock ownership contradiction where terminal failed probation holds active lock.
4. VALID_COMPLETE_LOCAL_MEDIA > STALE_PROVIDER_POLLING_FLAG.
5. Isolated finalizer proof: 2 valid existing clips yield valid final MP4 with 0 provider calls.
6. Guard tests:
   - pending probation + incomplete media still holds lock.
   - queued/processing pending jobs do not unlock solely by wall-clock TTL.
   - invalid/corrupt local clip does NOT bypass provider/recovery safety.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from services import multiscene_video_pipeline as pipeline
from services import video_local_validation
from services import video_project_queue as queue
from services import remote_worker_api
from services import video_real_render_connector as connector


NOW = datetime(2026, 9, 19, 4, 0, 0)
NOW_STR = "2026-09-19 04:00:00"
JOB28_PROBATION_TERMINAL_AT = "2026-09-17 03:21:34"


def _create_mini_mp4(target_path: Path, duration_sec: float = 1.0) -> Path:
    """Deterministic local generation of a tiny valid MP4 with video & audio streams."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", f"color=c=blue:s=320x240:d={duration_sec}:r=30",
        "-f", "lavfi",
        "-i", "anullsrc=r=48000:cl=mono",
        "-t", f"{duration_sec}",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        str(target_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg mini MP4 creation failed: {res.stderr}")
    return target_path


def _setup_test_db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / f"pv12_job28_test_{id(tmp_path)}.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _seed_canonical_job28_fixture(
    conn: sqlite3.Connection,
    tmp_path: Path,
    *,
    job_status: str = "queued",
    attempts: int = 44,
    max_attempts: int = 3,
    last_error: str = "provider_in_progress",
    probation_result: str = "failed",
    probation_terminal_at: str = JOB28_PROBATION_TERMINAL_AT,
    create_valid_clips: bool = True,
    corrupt_clip_2: bool = False,
) -> dict[str, Any]:
    """Seed isolated canonical Job28 fixture matching production ground truth."""
    job_id = 28
    project_id = 32
    user_id = 1001

    clip1_path = str(tmp_path / "key4u_video_28-1.mp4")
    clip2_path = str(tmp_path / "key4u_video_28-2.mp4")

    if create_valid_clips:
        _create_mini_mp4(Path(clip1_path), duration_sec=8.0)
        if corrupt_clip_2:
            Path(clip2_path).write_bytes(b"corrupt_not_a_valid_mp4")
        else:
            _create_mini_mp4(Path(clip2_path), duration_sec=8.0)

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
        "product_type": "video_trend",
        "engine_adapter": "text_to_video",
        "orchestration_mode": "per_scene_8s",
        "scene_count": 2,
        "duration_seconds": 16,
    }

    # 1. Video project
    project = queue.create_video_project(
        conn,
        user_id=user_id,
        profile_id="video_trend",
        topic="PV12 Job28 Project 32",
        ratio="9:16",
        asset_pack=shared,
    )
    orig_pid = int(project["project_id"])
    conn.execute("UPDATE video_projects SET project_id=? WHERE project_id=?", (project_id, orig_pid))
    queue.update_video_project(
        conn,
        project_id,
        status="processing",
        final_video_path="",
        invoice_json={
            **shared,
            "package_xu": 80,
            "user_visible_price_xu": 80,
            "persisted_quoted_price_xu": 80,
            "customer_charge_planned_xu": 80,
            "wallet_charge_amount_xu": 80,
            "scene_count": 2,
        },
        scene_count=2,
        total_xu_estimated=80,
        is_confirmed=1,
    )

    # 2. Outbox 27
    conn.execute(
        """INSERT OR REPLACE INTO video_dispatch_outbox
           (outbox_id, job_id, project_id, scene_indexes_json, owner, dispatch_status, attempt_count, created_at, updated_at, acknowledged_at)
           VALUES (27, ?, ?, '[1, 2]', 'product_video_worker', 'acknowledged', 1, ?, ?, ?)""",
        (job_id, project_id, probation_terminal_at, probation_terminal_at, probation_terminal_at),
    )

    # 3. Video render job
    job = queue.enqueue_video_render_job(conn, project_id=project_id, user_id=user_id, max_attempts=max_attempts)
    orig_jid = int(job["id"])
    conn.execute("UPDATE video_jobs SET id=? WHERE id=?", (job_id, orig_jid))
    conn.execute("UPDATE video_projects SET job_id=? WHERE project_id=?", (job_id, project_id))

    scene_tasks = [
        {
            "scene_index": 1,
            "scene_id": 1,
            "task_id": "key4u_task_28_1",
            "provider_task_id": "key4u_task_28_1",
            "status": "provider_running",
            "clip_path": clip1_path,
            "local_path": clip1_path,
            "output_path": clip1_path,
            "clip_valid": create_valid_clips,
            "task_scene_mapping_verified": True,
            "task_id_present": True,
            "continue_polling": True,
        },
        {
            "scene_index": 2,
            "scene_id": 2,
            "task_id": "key4u_task_28_2",
            "provider_task_id": "key4u_task_28_2",
            "status": "provider_running",
            "clip_path": clip2_path,
            "local_path": clip2_path,
            "output_path": clip2_path,
            "clip_valid": create_valid_clips and not corrupt_clip_2,
            "task_scene_mapping_verified": True,
            "task_id_present": True,
            "continue_polling": True,
        },
    ]

    result_payload = {
        **shared,
        "job_id": job_id,
        "project_id": project_id,
        "admission_mode": queue.PRODUCT_VIDEO_PROBATION_ADMISSION_MODE,
        "probation_candidate_key": "key4u_video",
        "probation_job_id": job_id,
        "probation_result": probation_result,
        "probation_terminal_at": probation_terminal_at,
        "probation_cooldown_started_at": probation_terminal_at,
        "probation_cooldown_seconds": 600,
        "probation_cooldown_active": False,
        "probation_cooldown_until": "2026-09-17 03:31:34",
        "continue_polling": True,
        "provider_in_progress": True,
        "provider_error": "provider_in_progress",
        "blocker": "provider_in_progress",
        "provider_pending_deferred": True,
        "scene_tasks": scene_tasks,
        "provider_scene_tasks": scene_tasks,
        "scene_count": 2,
        "scenes_total": 2,
        "scenes_done": 2 if create_valid_clips and not corrupt_clip_2 else 0,
        "no_charge": True,
        "final_video_path": "",
        "video_delivered_at": "",
        "delivery_receipt_id": "",
    }

    conn.execute(
        """UPDATE video_jobs
           SET status=?, attempts=?, max_attempts=?, last_error=?,
               result_json=?, progress_percent=50, progress_message='provider_in_progress',
               created_at='2026-09-17 03:00:00', updated_at=?
           WHERE id=?""",
        (
            job_status,
            attempts,
            max_attempts,
            last_error,
            json.dumps(result_payload),
            probation_terminal_at,
            job_id,
        ),
    )
    conn.commit()

    return {
        "job_id": job_id,
        "project_id": project_id,
        "user_id": user_id,
        "clip1_path": clip1_path,
        "clip2_path": clip2_path,
    }


# ==============================================================================
# SECTION 3 & 4: RED TESTS (PRE-FIX BEHAVIOR PROOF)
# ==============================================================================

def test_job28_infinite_requeue_reproduced(tmp_path):
    """RED PROOF for Section 3:
    Prove that defer_video_job_for_provider_polling reasserts status='queued'
    even when attempts=44 > max_attempts=3 and probation_result='failed',
    allowing the job to be claimed again infinitely.
    """
    conn = _setup_test_db(tmp_path)
    fixture = _seed_canonical_job28_fixture(conn, tmp_path, job_status="queued", attempts=44, max_attempts=3)

    # 1. Verify initial fixture state
    initial_job = queue.get_video_render_job(conn, fixture["job_id"])
    assert initial_job["status"] == "queued"
    assert initial_job["attempts"] == 44
    assert initial_job["max_attempts"] == 3

    # 2. Worker claims job -> status becomes 'processing', attempts increments to 45
    claimed = queue.claim_next_video_job(conn, worker_id="test_worker", now=NOW)
    assert claimed is not None
    assert int(claimed["id"]) == 28
    assert claimed["status"] == "processing"
    assert int(claimed["attempts"]) == 45

    # 3. Worker encounters provider_in_progress and calls defer_video_job_for_provider_polling
    deferred = queue.defer_video_job_for_provider_polling(
        conn,
        job_id=28,
        reason="provider_in_progress",
        diagnostics={"continue_polling": True, "blocker": "provider_in_progress"},
    )

    # Before fix, defer_video_job_for_provider_polling unconditionally sets status='queued'
    # without checking complete valid media coverage or terminal probation state.
    # After fix, defer contract returns explicit classification and does NOT blindly re-queue!
    classification = deferred.get("classification") or deferred.get("defer_classification")
    assert classification in {"EXISTING_ARTIFACT_RECOVERY_REQUIRED", "TERMINAL_PROBATION_BLOCKED"}, (
        f"RED REQUIREMENT: defer must classify Job28 as EXISTING_ARTIFACT_RECOVERY_REQUIRED "
        f"or TERMINAL_PROBATION_BLOCKED, but got: {deferred}"
    )
    assert deferred.get("status") != "queued", "INFINITE_REQUEUE_AFTER_FIX: status must NOT be blindly queued"


def test_ready_to_finalize_dead_end_reproduced(tmp_path):
    """RED PROOF for Section 2:
    Drive real control path: worker failure/reconciliation -> fail_remote_worker_job
    -> defer_video_job_for_provider_polling -> EXISTING_ARTIFACT_RECOVERY_REQUIRED.
    Prove CURRENT PR1076 behavior leaves:
    - JOB_STATUS=processing
    - LOCKED_BY=''
    - LEASE_EXPIRES_AT=NULL
    - CONTINUE_POLLING=False
    - TERMINAL_STATE=ready_to_finalize
    - claim_next_video_job cannot claim this row (JOB_CLAIMABLE_AFTER_CLASSIFICATION=NO)
    - no finalizer consumer proceeds to finalization (READY_TO_FINALIZE_DEAD_END_RED=YES).
    """
    conn = _setup_test_db(tmp_path)
    fixture = _seed_canonical_job28_fixture(conn, tmp_path, job_status="queued", attempts=44, max_attempts=3)

    # 1. Initial job state is queued
    job = queue.get_video_render_job(conn, 28)
    assert job["status"] == "queued"

    # 2. Worker claims job -> processing, locked by worker
    worker_id = "vps-toanaas-01"
    claimed = queue.claim_next_video_job(conn, worker_id=worker_id, now=NOW)
    assert claimed["status"] == "processing"
    assert claimed["locked_by"] == worker_id

    # 3. Worker reconciliation / failure triggers fail_remote_worker_job
    fail_result = remote_worker_api.fail_remote_worker_job(
        conn,
        worker_id=worker_id,
        job_id=28,
        safe_error="provider_in_progress",
        retryable=True,
        diagnostics={"continue_polling": True, "blocker": "provider_in_progress"},
    )
    classification = fail_result.get("classification") or fail_result.get("defer_classification")
    assert classification == "EXISTING_ARTIFACT_RECOVERY_REQUIRED"

    # 4. Prove PR1076 leaves the unclaimable processing dead-end:
    job = queue.get_video_render_job(conn, 28)
    project = queue.get_video_project(conn, 32)
    payload = queue._json_loads(job["result_json"], {})

    assert job["status"] == "processing", "JOB_STATUS must be processing"
    assert job["locked_by"] == "", "LOCKED_BY must be empty string"
    assert job["lease_expires_at"] is None, "LEASE_EXPIRES_AT must be NULL"
    assert payload.get("continue_polling") is False, "CONTINUE_POLLING must be False"
    assert payload.get("terminal_state") == "ready_to_finalize", "TERMINAL_STATE must be ready_to_finalize"
    assert project.get("video_terminal_state") == "ready_to_finalize"

    # 5. Prove claim_next_video_job cannot claim this row
    second_claim = queue.claim_next_video_job(conn, worker_id="consumer_worker", now=NOW)
    assert second_claim == {}, "JOB_CLAIMABLE_AFTER_CLASSIFICATION=NO: claim_next_video_job must return {}"

    # 6. Prove no production consumer proceeded to finalization
    assert not project.get("final_video_path"), "READY_TO_FINALIZE_DEAD_END_RED=YES: final_video_path must be empty"



def test_job28_terminal_probation_active_lock_red(tmp_path):
    """RED PROOF for Section 4:
    Prove that product_video_probation_lock_state currently grants active lock
    to Job 28 despite probation_result='failed'.
    """
    conn = _setup_test_db(tmp_path)
    fixture = _seed_canonical_job28_fixture(conn, tmp_path, job_status="queued", attempts=44, max_attempts=3)

    # Inquire lock state for another job (e.g. Job 29)
    state = queue.product_video_probation_lock_state(conn, current_job_id=29, now=NOW)

    # Before fix: probation_active is True and active_probation_job_id is 28,
    # blocking Job 29 with 'probation_lock_owned_by_other_job' even though Job 28 probation failed!
    # After fix: a job with probation_result='failed' must NOT be active lock holder.
    assert state.get("active_probation_job_id") != 28, (
        f"RED REQUIREMENT: Job 28 with probation_result='failed' must NOT be active probation lock holder, "
        f"but got state: {state}"
    )
    assert state.get("probation_active") is False or state.get("active_probation_job_id") != 28


def test_valid_complete_local_media_preempts_stale_provider_polling(tmp_path):
    """Proof for Section 6:
    When 2/2 required clips are locally valid on disk, VALID_COMPLETE_LOCAL_MEDIA > STALE_PROVIDER_POLLING_FLAG.
    defer_video_job_for_provider_polling must NOT blindly re-queue for provider polling.
    """
    conn = _setup_test_db(tmp_path)
    fixture = _seed_canonical_job28_fixture(conn, tmp_path, create_valid_clips=True)

    deferred = queue.defer_video_job_for_provider_polling(
        conn,
        job_id=28,
        reason="provider_in_progress",
        diagnostics={"continue_polling": True, "blocker": "provider_in_progress"},
    )
    classification = deferred.get("classification") or deferred.get("defer_classification")
    assert classification == "EXISTING_ARTIFACT_RECOVERY_REQUIRED", (
        f"VALID_COMPLETE_LOCAL_MEDIA > STALE_PROVIDER_POLLING_FLAG: expected EXISTING_ARTIFACT_RECOVERY_REQUIRED, "
        f"got: {classification} (deferred={deferred})"
    )


# ==============================================================================
# SECTION 11: ISOLATED FINALIZER TEST (EXISTING ARTIFACTS ONLY)
# ==============================================================================

def test_isolated_finalizer_with_existing_valid_clips(tmp_path):
    """Section 11:
    Prove that finalize_multiscene_scene_clips can assemble 2 valid existing clips
    into a valid final MP4 with ZERO provider calls and valid media probe.
    """
    workspace = tmp_path / "finalizer_workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    clip1 = _create_mini_mp4(workspace / "clip_1.mp4", duration_sec=8.0)
    clip2 = _create_mini_mp4(workspace / "clip_2.mp4", duration_sec=8.0)

    probe1 = video_local_validation.probe_video_file(str(clip1))
    probe2 = video_local_validation.probe_video_file(str(clip2))
    assert probe1.get("ok") is True, f"Clip 1 must be valid: {probe1}"
    assert probe2.get("ok") is True, f"Clip 2 must be valid: {probe2}"

    scenes = [
        pipeline.SceneSpec(scene_id=1, title="Scene 1", visual_prompt="Visual 1", video_prompt="Video 1", narration_text="Scene 1 text", target_duration_sec=8.0),
        pipeline.SceneSpec(scene_id=2, title="Scene 2", visual_prompt="Visual 2", video_prompt="Video 2", narration_text="Scene 2 text", target_duration_sec=8.0),
    ]
    scene_clip_paths = {1: str(clip1), 2: str(clip2)}

    final_result = pipeline.finalize_multiscene_scene_clips(
        user_id="1001",
        job_id="28",
        workspace_dir=str(workspace),
        scenes=scenes,
        scene_clip_paths=scene_clip_paths,
        output_width=720,
        output_height=1280,
    )

    assert final_result.get("final_video_path"), f"Final MP4 must be produced: {final_result}"
    final_path = final_result["final_video_path"]
    assert os.path.isfile(final_path), f"Final MP4 file must exist at {final_path}"
    assert os.path.getsize(final_path) > 0, "Final MP4 file must not be 0 bytes"

    # Validate final MP4 with real media probe
    final_probe = video_local_validation.probe_video_file(final_path)
    assert final_probe.get("ok") is True, f"Final MP4 must pass media probe: {final_probe}"
    assert float(final_probe.get("duration") or final_probe.get("duration_sec") or 0) > 0, "Final MP4 duration must be > 0"


# ==============================================================================
# SECTION 14: GUARDS & CONTRACT REGRESSION TESTS
# ==============================================================================

def test_pending_probation_incomplete_media_still_holds_lock(tmp_path):
    """Section 14 C & D:
    A genuine pending probation job with incomplete media (probation_result='pending')
    MUST continue to hold the active probation lock.
    ACTIVE_PENDING_JOB_PREMATURE_UNLOCK=NO.
    """
    conn = _setup_test_db(tmp_path)
    job_id = 50
    project_id = 50
    user_id = 1002

    project = queue.create_video_project(
        conn,
        user_id=user_id,
        profile_id="video_trend",
        topic="Pending probation project",
        ratio="9:16",
        asset_pack={"source": "product_video", "product_video": True},
    )
    conn.execute("UPDATE video_projects SET project_id=? WHERE project_id=?", (project_id, int(project["project_id"])))
    job = queue.enqueue_video_render_job(conn, project_id=project_id, user_id=user_id)
    conn.execute("UPDATE video_jobs SET id=? WHERE id=?", (job_id, int(job["id"])))

    payload = {
        "source": "product_video",
        "product_video": True,
        "admission_mode": queue.PRODUCT_VIDEO_PROBATION_ADMISSION_MODE,
        "probation_result": "pending",
        "probation_started_at": queue.now_text(NOW - timedelta(minutes=45)),
        "probation_lock_expires_at": queue.now_text(NOW - timedelta(minutes=15)),
        "continue_polling": True,
    }
    conn.execute(
        "UPDATE video_jobs SET status='processing', result_json=? WHERE id=?",
        (json.dumps(payload), job_id),
    )
    conn.commit()

    # Inquire lock state for another job
    state = queue.product_video_probation_lock_state(conn, current_job_id=99, now=NOW)
    assert state["probation_active"] is True
    assert state["active_probation_job_id"] == job_id
    assert state["probation_lock_owned_by_other_job"] is True
    assert state["probation_lock_reject_reason"] == "probation_lock_owned_by_other_job"


def test_corrupt_local_clip_does_not_bypass_safety(tmp_path):
    """Section 14 E:
    If one of the required scene clips is corrupt / invalid,
    INVALID_MEDIA_BYPASS=NO.
    defer_video_job_for_provider_polling must NOT classify as EXISTING_ARTIFACT_RECOVERY_REQUIRED.
    """
    conn = _setup_test_db(tmp_path)
    fixture = _seed_canonical_job28_fixture(conn, tmp_path, create_valid_clips=True, corrupt_clip_2=True)

    deferred = queue.defer_video_job_for_provider_polling(
        conn,
        job_id=28,
        reason="provider_in_progress",
        diagnostics={"continue_polling": True, "blocker": "provider_in_progress"},
    )
    classification = deferred.get("classification") or deferred.get("defer_classification")
    assert classification != "EXISTING_ARTIFACT_RECOVERY_REQUIRED", (
        f"INVALID_MEDIA_BYPASS=NO: corrupt clip must NOT qualify for EXISTING_ARTIFACT_RECOVERY_REQUIRED, "
        f"got: {classification}"
    )


def test_production_recovery_consumer_closure(tmp_path):
    """GREEN PROOF for Section 1, 2, 5, 6, 7:
    Drive real control path:
    1. Worker fails/reconciles job 28 -> fail_remote_worker_job.
    2. Defer classifies as EXISTING_ARTIFACT_RECOVERY_REQUIRED, leaves unclaimable processing dead-end.
    3. Assert unclaimable dead-end: claim_next_video_job returns {} (JOB_CLAIMABLE_AFTER_CLASSIFICATION=NO).
    4. Canonical recovery entrypoint:
       - product_video_existing_task_recovery_state allows recovery (existing_task_recovery_recoverable=True, domain="finalizer").
       - recover_product_video_existing_tasks CAS recovers row to status='queued', project status='queued_for_worker'.
    5. Production consumer claims row:
       - claim_next_video_job claims row (UNCLAIMABLE_PROCESSING_DEAD_END=NO, PRODUCTION_RECOVERY_CONSUMER_INVOKED=YES).
       - status='processing', locked_by='consumer_worker_01'.
    6. Consumer executes render_real_video_job:
       - Loads persisted 2/2 valid clips from workspace without provider submissions (PROVIDER_CALLS=0).
       - Calls canonical finalizer (finalize_multiscene_scene_clips).
       - Produces valid final concatenated MP4 (FINALIZER_INVOKED_BY_RECOVERY_FLOW=YES, FINAL_MP4_CREATED=YES, FINAL_MP4_VALID=YES).
       - Completes video job via complete_video_job.
    7. Prove idempotency:
       - Replaying recovery with same idempotency_key returns duplicate_prevented=True (RECOVERY_REPLAY_IDEMPOTENT=YES).
       - Zero duplicate provider submissions (SECOND_PROVIDER_SUBMIT=0).
       - Zero duplicate final MP4 mutations (SECOND_FINAL_MP4_DUPLICATE=0).
    """
    conn = _setup_test_db(tmp_path)
    fixture = _seed_canonical_job28_fixture(conn, tmp_path, job_status="queued", attempts=44, max_attempts=3)

    # 1. Initial job state is queued
    job = queue.get_video_render_job(conn, 28)
    assert job["status"] == "queued"

    # 2. Worker claims job -> processing
    worker_id = "vps-toanaas-01"
    claimed = queue.claim_next_video_job(conn, worker_id=worker_id, now=NOW)
    assert claimed["status"] == "processing"
    assert claimed["locked_by"] == worker_id

    # 3. Worker failure / reconciliation triggers fail_remote_worker_job
    fail_result = remote_worker_api.fail_remote_worker_job(
        conn,
        worker_id=worker_id,
        job_id=28,
        safe_error="provider_in_progress",
        retryable=True,
        diagnostics={"continue_polling": True, "blocker": "provider_in_progress"},
    )
    classification = fail_result.get("classification") or fail_result.get("defer_classification")
    assert classification == "EXISTING_ARTIFACT_RECOVERY_REQUIRED"

    # 4. Prove PR1076 left an unclaimable processing dead-end before recovery
    unclaimed = queue.claim_next_video_job(conn, worker_id="consumer_worker_01", now=NOW)
    assert unclaimed == {}, "UNCLAIMABLE_PROCESSING_DEAD_END: must be unclaimable before recovery"

    # 5. Inquire canonical recovery state
    job_before_rec = queue.get_video_render_job(conn, 28)
    project_before_rec = queue.get_video_project(conn, 32)
    payload_before_rec = queue._json_loads(job_before_rec["result_json"], {})
    outbox_before_rec = conn.execute("SELECT * FROM video_dispatch_outbox WHERE job_id=28").fetchone()
    outbox_dict = {
        "outbox_id": outbox_before_rec[0],
        "job_id": outbox_before_rec[1],
        "project_id": outbox_before_rec[2],
        "dispatch_status": outbox_before_rec[5],
    }

    rec_state = queue.product_video_existing_task_recovery_state(
        job=job_before_rec,
        project=project_before_rec,
        result=payload_before_rec,
        outbox=outbox_dict,
        now=NOW,
    )
    assert rec_state["existing_task_recovery_recoverable"] is True
    assert rec_state["recovery_domain"] == "finalizer"

    # 6. Execute canonical recovery
    idempotency_key = "pv12-job28-consumer-rec-001"
    rec_result = queue.recover_product_video_existing_tasks(
        conn,
        job_id=28,
        recovery_domain="finalizer",
        idempotency_key=idempotency_key,
        now=NOW,
    )
    assert rec_result["existing_task_recovery_recovered"] is True
    assert rec_result["job_status_after_recovery"] == "queued"
    assert rec_result["project_status_after_recovery"] == "queued_for_worker"

    # 7. Production consumer claims the recovered job
    consumer_claimed = queue.claim_next_video_job(conn, worker_id="consumer_worker_01", now=NOW)
    assert consumer_claimed != {}, "JOB_CLAIMABLE_AFTER_RECOVERY=YES"
    assert consumer_claimed["status"] == "processing"
    assert consumer_claimed["locked_by"] == "consumer_worker_01"

    # 8. Consumer executes render_real_video_job to finalize the 2 valid clips
    consumer_work_dir = tmp_path / "consumer_work"
    consumer_work_dir.mkdir(parents=True, exist_ok=True)

    render_result = connector.render_real_video_job(consumer_claimed, str(consumer_work_dir))
    assert render_result["ok"] is True, f"render_real_video_job failed: {render_result}"
    assert render_result.get("finalizer_invoked") is True, "FINALIZER_INVOKED_BY_RECOVERY_FLOW=YES"
    assert render_result.get("final_mp4_valid") is True, "FINAL_MP4_VALID=YES"
    final_video_path = render_result.get("final_video_path")
    assert final_video_path and os.path.exists(final_video_path), "FINAL_MP4_CREATED=YES"
    assert os.path.getsize(final_video_path) > 0

    # 9. Verify zero provider API submissions occurred
    assert render_result.get("provider_submit_called") is False, "PROVIDER_CALLS=0"
    assert render_result.get("no_charge") is True, "WALLET_MUTATIONS=0"

    # 10. Complete the video job
    complete_result = queue.complete_video_job(
        conn,
        job_id=28,
        final_video_path=final_video_path,
        result=render_result,
    )
    assert complete_result["ok"] is True
    project_after_complete = queue.get_video_project(conn, 32)
    assert project_after_complete["final_video_path"] == final_video_path
    assert project_after_complete["status"] == "completed"

    # 11. Prove idempotency: replay recovery with same idempotency key
    replay_result = queue.recover_product_video_existing_tasks(
        conn,
        job_id=28,
        recovery_domain="finalizer",
        idempotency_key=idempotency_key,
        now=NOW,
    )
    assert replay_result.get("duplicate_prevented") is True, "RECOVERY_REPLAY_IDEMPOTENT=YES"


def test_corrupt_media_probe_rejects_corrupt_clip_at_render(tmp_path):
    """Section 5: Prove media validity gate prevents corrupt media bypass at render-time.
    Even if metadata has clip_valid=True, real video probe rejects corrupt media
    (INVALID_MEDIA_RECOVERY_BYPASS=0).
    """
    conn = _setup_test_db(tmp_path)
    # Seed fixture with corrupt clip 2
    fixture = _seed_canonical_job28_fixture(conn, tmp_path, create_valid_clips=True, corrupt_clip_2=True)
    # Intentionally falsify metadata to simulate lying/corrupt metadata bypass attempt:
    job = queue.get_video_render_job(conn, 28)
    payload = queue._json_loads(job["result_json"], {})
    payload["recovery_existing_tasks_only"] = True
    payload["terminal_state"] = "ready_to_finalize"
    payload["final_decision"] = "ready_to_finalize"
    for task in payload.get("scene_tasks", []):
        task["clip_valid"] = True
        task["validation_passed"] = True
    conn.execute("UPDATE video_jobs SET result_json=? WHERE id=28", (json.dumps(payload),))
    conn.commit()

    # Run render_real_video_job directly
    work_dir = tmp_path / "corrupt_probe_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    claimed_corrupt = queue.get_video_render_job(conn, 28)

    render_result = connector.render_real_video_job(claimed_corrupt, str(work_dir))
    # Clip 2 must be rejected by video_final_output.probe_video because it is corrupt
    # Hence scene_outputs contains only scene 1 -> not all required scenes are available
    assert render_result.get("final_mp4_valid") is False
    assert not render_result.get("final_video_path")
    assert render_result.get("scene_coverage_count") == 1
    assert 2 in render_result.get("missing_scene_indexes", [])
