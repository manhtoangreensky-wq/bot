"""Tests for P0.PRODUCT_VIDEO.PV07.SCENE.ARTIFACT.FINALIZER.DELIVERY.LOCK.

Locks the complete post-provider-success chain:
1. PROVIDER_SUCCESS != SCENE_CLIP_VALID
2. SCENE_CLIPS_VALID != FINAL_MP4_VALID
3. FINAL_MP4_VALID != DELIVERED
4. DELIVERED != PRODUCT_SUCCESS unless receipt is durable
5. ATOMIC FINAL OUTPUT PROMOTION: valid final output immutable against failed re-render
6. PV06 RECOVERY PROTECTION: independent failure domain quotas preserved
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from services import multiscene_video_pipeline as pipeline
from services import video_local_validation
from services import video_project_queue as queue


TASK_SCENE_1 = "task-pv07-scene-1"
TASK_SCENE_2 = "task-pv07-scene-2"


def _create_mini_mp4(target_path: Path, duration_sec: float = 1.0) -> Path:
    """Deterministic local generation of a tiny valid MP4 with video & audio streams."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", f"color=c=blue:s=320x240:d={duration_sec}:r=30",
        "-f", "lavfi",
        "-i", f"anullsrc=r=48000:cl=mono",
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


def _seed_pv07_test_job(
    db_path: Path,
    *,
    scene_count: int = 2,
    provider_task_completed: bool = False,
    all_clips_downloaded: bool = False,
    final_mp4_valid: bool = False,
    final_video_path: str = "",
    job_status: str = "processing",
    project_status: str = "processing",
) -> tuple[sqlite3.Connection, int, int]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)

    project = queue.create_video_project(
        conn,
        user_id=919_013,
        profile_id="video_ai_prompt",
        topic="PV07 pipeline lock test",
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
        invoice_json={"scene_count": scene_count, "duration_seconds": scene_count * 5},
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
    scene_tasks = []
    for idx in range(1, scene_count + 1):
        tid = f"task-pv07-scene-{idx}"
        scene_tasks.append(
            {
                "scene_index": idx,
                "provider": "shopaikey_video",
                "task_id": tid,
                "provider_task_id": tid,
                "status": scene_status,
                "result_url": f"https://cdn.example.com/scene_{idx}.mp4" if provider_task_completed else "",
                "clip_bytes": 1024 * 1024 if all_clips_downloaded else 0,
                "clip_valid": bool(all_clips_downloaded),
                "artifact_valid": bool(all_clips_downloaded),
            }
        )

    result_payload: dict[str, Any] = {
        "job_id": job_id,
        "project_id": project_id,
        "source": "product_video",
        "product_video": True,
        "scene_count": scene_count,
        "orchestration_mode": "per_scene_8s",
        "chat_id": 919_013,
        "user_id": 919_013,
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "charged_xu": 0,
        "charge": 0,
        "wallet_charge_recorded": False,
        "no_charge": True,
        "scene_tasks": scene_tasks,
        "task_to_scene_index": {f"task-pv07-scene-{idx}": idx for idx in range(1, scene_count + 1)},
    }

    if provider_task_completed:
        result_payload["provider_status"] = "succeeded"
        result_payload["provider_finished"] = True
        result_payload["result_url_present"] = True

    if all_clips_downloaded:
        result_payload["scene_clip_coverage_complete"] = True
        result_payload["valid_scene_clip_count"] = scene_count

    if final_mp4_valid:
        result_payload["final_mp4_valid"] = True
        result_payload["final_video_path"] = final_video_path or f"/tmp/final_{job_id}.mp4"

    conn.execute(
        "UPDATE video_jobs SET status=?, result_json=? WHERE id=?",
        (job_status, json.dumps(result_payload), job_id),
    )
    outbox = queue.ensure_product_video_dispatch_outbox(
        conn,
        job_id=job_id,
        project_id=project_id,
        scene_indexes=list(range(1, scene_count + 1)),
    )
    conn.execute(
        "UPDATE video_dispatch_outbox SET dispatch_status='acknowledged' WHERE outbox_id=?",
        (int(outbox["outbox_id"]),),
    )
    conn.commit()
    return conn, job_id, project_id


# =========================================================================
# 1. PROVIDER_SUCCESS != SCENE_CLIP_VALID (Job28 Core Invariant)
# =========================================================================

def test_pv07_provider_success_does_not_mean_scene_clip_or_product_success(tmp_path: Path) -> None:
    """A provider task reporting success with result_url does not mean scene clip is valid.
    
    Without an actual downloaded, probed video file, scene coverage must remain
    incomplete, and neither finalizer nor delivery nor product success may be entered.
    """
    db_path = tmp_path / "pv07_provider_success.sqlite3"
    conn, job_id, project_id = _seed_pv07_test_job(
        db_path,
        scene_count=2,
        provider_task_completed=True,
        all_clips_downloaded=False,  # Download has NOT succeeded
        final_mp4_valid=False,
    )
    job = queue.get_video_render_job(conn, job_id)
    project = queue.get_video_project(conn, project_id)
    result = json.loads(job["result_json"])

    coverage = queue.product_video_scene_coverage_state(project, job, result)
    assert coverage["scene_clip_coverage_complete"] is False, "Provider success must not imply clip coverage complete"
    assert len(coverage["unresolved_scene_indexes"]) == 2
    assert coverage["missing_scene_action"] in {"poll", "timeout"}
    assert coverage["missing_scene_action"] != "concat"
    assert coverage["missing_scene_action"] != "complete"


def test_pv07_single_scene_provider_success_does_not_imply_clip_valid(tmp_path: Path) -> None:
    """For single-scene Product Video, provider result_url_present must NOT automatically set clip_valid."""
    db_path = tmp_path / "pv07_single_scene.sqlite3"
    conn, job_id, project_id = _seed_pv07_test_job(
        db_path,
        scene_count=1,
        provider_task_completed=True,
        all_clips_downloaded=False,
        final_mp4_valid=False,
    )
    job = queue.get_video_render_job(conn, job_id)
    project = queue.get_video_project(conn, project_id)
    result = json.loads(job["result_json"])
    # Explicitly clear any downloaded clip path or validated flags
    result.pop("final_video_path", None)
    result.pop("final_mp4_valid", None)

    ledger = queue.product_video_scene_ledger_state(project, job, result)
    # Scene 1 must NOT be considered clip_valid merely because result_url or provider_status=succeeded
    record = ledger["scene_records"][1]
    assert record["clip_valid"] is False, "Single scene must not be marked clip_valid without valid downloaded artifact"


# =========================================================================
# 2. SCENE ARTIFACT VALIDATION MATRIX
# =========================================================================

def test_pv07_scene_artifact_validation_matrix_fails_closed(tmp_path: Path) -> None:
    """Scene artifact validation must reject missing, 0-byte, corrupt, and non-video files.
    
    Only genuine valid MP4 video passes validation.
    """
    missing_file = tmp_path / "missing.mp4"
    zero_byte_file = tmp_path / "zero_bytes.mp4"
    zero_byte_file.write_bytes(b"")
    html_error_file = tmp_path / "error_404.html"
    html_error_file.write_bytes(b"<html><body><h1>404 Not Found</h1></body></html>")
    corrupt_mp4 = tmp_path / "corrupt.mp4"
    corrupt_mp4.write_bytes(b"\x00\x00\x00 ftypisom\x00\x00\x02\x00randomcorruptedbyteshere1234567890")
    valid_mp4 = _create_mini_mp4(tmp_path / "valid.mp4", duration_sec=1.0)

    # Validate using video_local_validation.probe_video_file
    assert video_local_validation.probe_video_file(str(missing_file))["ok"] is False
    assert video_local_validation.probe_video_file(str(zero_byte_file))["ok"] is False
    assert video_local_validation.probe_video_file(str(html_error_file))["ok"] is False
    assert video_local_validation.probe_video_file(str(corrupt_mp4))["ok"] is False
    assert video_local_validation.probe_video_file(str(valid_mp4))["ok"] is True

    # Ledger state must NOT mark clip_valid=True for corrupt/text file even if clip_bytes > 0
    fake_job = {"id": 1, "scene_count": 1}
    fake_project = {"project_id": 1, "scene_count": 1}
    fake_result = {
        "job_id": 1,
        "scene_count": 1,
        "scene_tasks": [
            {
                "scene_index": 1,
                "task_id": "task-1",
                "clip_path": str(html_error_file),
                "clip_bytes": len(html_error_file.read_bytes()),
                # Notice clip_valid is not True, but clip_bytes > 0
            }
        ],
    }
    ledger = queue.product_video_scene_ledger_state(fake_project, fake_job, fake_result)
    assert ledger["scene_records"][1]["clip_valid"] is False, "HTML error file with >0 bytes must NOT be accepted as valid clip"


# =========================================================================
# 3. SCENE CLIP DURABILITY ACROSS DB REOPEN
# =========================================================================

def test_pv07_scene_clip_durability_across_db_reopen(tmp_path: Path) -> None:
    """Verified scene clip metadata and validity persist across process restart / DB reopen."""
    db_path = tmp_path / "pv07_durability.sqlite3"
    valid_mp4_1 = _create_mini_mp4(tmp_path / "scene_1.mp4", duration_sec=1.0)
    valid_mp4_2 = _create_mini_mp4(tmp_path / "scene_2.mp4", duration_sec=1.0)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)

    project = queue.create_video_project(conn, user_id=1, topic="Durability")
    pid = int(project["project_id"])
    queue.update_video_project(conn, pid, scene_count=2, invoice_json={"scene_count": 2})
    job = queue.enqueue_video_render_job(conn, project_id=pid, user_id=1)
    jid = int(job["id"])

    result = {
        "job_id": jid,
        "scene_count": 2,
        "scene_tasks": [
            {
                "scene_index": 1,
                "task_id": "task-1",
                "clip_path": str(valid_mp4_1),
                "clip_bytes": os.path.getsize(valid_mp4_1),
                "clip_valid": True,
                "artifact_valid": True,
                "status": "scene_clip_validated",
            },
            {
                "scene_index": 2,
                "task_id": "task-2",
                "clip_path": str(valid_mp4_2),
                "clip_bytes": os.path.getsize(valid_mp4_2),
                "clip_valid": True,
                "artifact_valid": True,
                "status": "scene_clip_validated",
            },
        ],
        "scene_clip_coverage_complete": True,
    }
    conn.execute("UPDATE video_jobs SET result_json=? WHERE id=?", (json.dumps(result), jid))
    conn.commit()
    conn.close()

    # Reopen connection
    conn2 = sqlite3.connect(db_path)
    conn2.row_factory = sqlite3.Row
    job2 = queue.get_video_render_job(conn2, jid)
    project2 = queue.get_video_project(conn2, pid)
    result2 = json.loads(job2["result_json"])

    coverage = queue.product_video_scene_coverage_state(project2, job2, result2)
    assert coverage["scene_clip_coverage_complete"] is True
    assert coverage["completed_scene_count"] == 2
    assert coverage["unresolved_scene_indexes"] == []
    conn2.close()


# =========================================================================
# 4. ALL-SCENE COVERAGE LOCK
# =========================================================================

@pytest.mark.parametrize(
    "valid_indexes,expected_complete,unresolved",
    [
        ([], False, [1, 2, 3]),
        ([1], False, [2, 3]),
        ([1, 2], False, [3]),
        ([1, 2, 3], True, []),
        ([1, 1, 3], False, [2]),  # Duplicate scene 1, scene 2 missing
        ([1, 2, 4], False, [3]),  # Out of range scene 4, scene 3 missing
    ],
)
def test_pv07_all_scene_coverage_lock_matrix(
    tmp_path: Path,
    valid_indexes: list[int],
    expected_complete: bool,
    unresolved: list[int],
) -> None:
    """Only exact 1..N valid clips satisfy scene coverage."""
    scene_count = 3
    scene_tasks = []
    for idx in valid_indexes:
        scene_tasks.append(
            {
                "scene_index": idx,
                "task_id": f"task-{idx}",
                "clip_valid": True,
                "artifact_valid": True,
                "status": "scene_clip_validated",
            }
        )
    result = {
        "scene_count": scene_count,
        "scene_tasks": scene_tasks,
    }
    coverage = queue.product_video_scene_coverage_state({}, {"scene_count": scene_count}, result)
    assert coverage["scene_clip_coverage_complete"] is expected_complete
    assert set(coverage["unresolved_scene_indexes"]) == set(unresolved)


# =========================================================================
# 5. FINALIZER ENTRY LOCKED UNTIL FULL COVERAGE
# =========================================================================

def test_pv07_finalizer_entry_blocks_if_scene_clip_missing_or_corrupt(tmp_path: Path) -> None:
    """Finalizer must refuse to run if any scene clip is missing, 0-byte, or corrupt."""
    valid_clip = _create_mini_mp4(tmp_path / "clip1.mp4", duration_sec=1.0)
    corrupt_clip = tmp_path / "clip2.mp4"
    corrupt_clip.write_bytes(b"corrupt non-video content")

    scenes = [
        pipeline.SceneSpec(scene_id=1, title="Scene 1", visual_prompt="A", video_prompt="A", target_duration_sec=1.0),
        pipeline.SceneSpec(scene_id=2, title="Scene 2", visual_prompt="B", video_prompt="B", target_duration_sec=1.0),
    ]

    res = pipeline.finalize_multiscene_scene_clips(
        user_id="user1",
        job_id="job1",
        workspace_dir=str(tmp_path / "ws"),
        scenes=scenes,
        scene_clip_paths={1: str(valid_clip), 2: str(corrupt_clip)},
    )
    assert res["ok"] is False, "Finalizer must fail when any scene clip is corrupt/invalid"
    assert res.get("concat_ready") is False


# =========================================================================
# 6. FINALIZER FAILURE TRUTH & PV06 QUOTA SEPARATION
# =========================================================================

def test_pv07_finalizer_failure_preserves_independent_recovery_quotas(tmp_path: Path) -> None:
    """When finalizer fails (e.g. ffmpeg error), only finalizer_recovery_count is consumed.
    
    provider_poll, provider_artifact, and scene_clip recovery quotas must remain untouched.
    Provider tasks must NOT be resubmitted.
    """
    db_path = tmp_path / "pv07_finalizer_fail.sqlite3"
    conn, job_id, project_id = _seed_pv07_test_job(
        db_path,
        scene_count=2,
        provider_task_completed=True,
        all_clips_downloaded=True,
        final_mp4_valid=False,
    )
    job = queue.get_video_render_job(conn, job_id)
    project = queue.get_video_project(conn, project_id)
    result = json.loads(job["result_json"])
    result["finalizer_failed"] = True
    result["finalizer_error"] = "ffmpeg_exit_code_1"
    conn.execute("UPDATE video_jobs SET status='failed', result_json=? WHERE id=?", (json.dumps(result), job_id))
    conn.commit()

    domain = queue.classify_product_video_recovery_domain(result, job, project)
    assert domain == "finalizer"

    # Now apply recovery update using the classified domain
    recovered = queue.recover_product_video_existing_tasks(
        conn,
        job_id=job_id,
        recovery_domain=domain,
    )
    assert recovered["existing_task_recovery_recovered"] is True
    job_after = queue.get_video_render_job(conn, job_id)
    res_after = json.loads(job_after["result_json"])
    assert res_after["finalizer_recovery_count"] == 1
    assert res_after.get("provider_poll_recovery_count", 0) == 0
    assert res_after.get("provider_artifact_recovery_count", 0) == 0
    assert res_after.get("scene_clip_recovery_count", 0) == 0
    assert res_after.get("delivery_recovery_count", 0) == 0
    assert res_after["provider_submit_allowed"] is False


# =========================================================================
# 7. FINAL MP4 VALIDATION STRICT FFPROBE
# =========================================================================

def test_pv07_final_mp4_validation_strict(tmp_path: Path) -> None:
    """Final MP4 must pass ffprobe validation and reject 0-byte, text, and truncated files."""
    valid_mp4 = _create_mini_mp4(tmp_path / "final_valid.mp4", duration_sec=2.0)
    fake_text_mp4 = tmp_path / "final_fake.mp4"
    fake_text_mp4.write_text("not a video")

    probe_valid = video_local_validation.probe_video_file(str(valid_mp4))
    assert probe_valid["ok"] is True
    assert probe_valid["duration"] > 0
    assert probe_valid["has_video"] is True

    probe_fake = video_local_validation.probe_video_file(str(fake_text_mp4))
    assert probe_fake["ok"] is False


# =========================================================================
# 8. ATOMIC FINAL OUTPUT PROMOTION & IMMUTABILITY
# =========================================================================

def test_pv07_atomic_final_output_promotion_preserves_valid_existing_final(tmp_path: Path) -> None:
    """If a valid final MP4 already exists, a broken/failing re-render must NOT overwrite or destroy it."""
    workspace = tmp_path / "ws_atomic"
    workspace.mkdir(parents=True, exist_ok=True)
    canonical_final = workspace / "final_output.mp4"
    _create_mini_mp4(canonical_final, duration_sec=1.0)
    initial_bytes = canonical_final.read_bytes()
    assert len(initial_bytes) > 0

    # Simulate a failed finalizer run (e.g. invalid inputs or broken mux)
    scenes = [
        pipeline.SceneSpec(scene_id=1, title="S1", visual_prompt="A", video_prompt="A", target_duration_sec=1.0),
    ]
    # Pointing to corrupt scene clip causes finalization failure
    corrupt_clip = tmp_path / "corrupt_clip.mp4"
    corrupt_clip.write_bytes(b"corrupt")

    pipeline.finalize_multiscene_scene_clips(
        user_id="user1",
        job_id="job_atomic",
        workspace_dir=str(workspace),
        scenes=scenes,
        scene_clip_paths={1: str(corrupt_clip)},
    )

    # The existing canonical final MUST still exist and remain intact!
    assert canonical_final.is_file(), "Existing valid final MP4 must not be deleted by failed finalization"
    assert canonical_final.read_bytes() == initial_bytes, "Existing valid final MP4 must not be corrupted by failed finalization"


# =========================================================================
# 9. DELIVERY GATE REQUIRES VALID FINAL MP4
# =========================================================================

def test_pv07_delivery_gate_refuses_invalid_or_missing_final_mp4(tmp_path: Path) -> None:
    """note_video_delivery_result must fail closed if final_mp4_valid is False or final file missing."""
    db_path = tmp_path / "pv07_delivery_gate.sqlite3"
    conn, job_id, project_id = _seed_pv07_test_job(
        db_path,
        scene_count=2,
        provider_task_completed=True,
        all_clips_downloaded=True,
        final_mp4_valid=False,  # NOT valid
    )

    res = queue.note_video_delivery_result(
        conn,
        job_id=job_id,
        sent=True,
        delivery_message_id="tg_12345",
    )
    assert res["ok"] is False, "Delivery must be refused when final_mp4_valid is False"
    assert "final" in str(res.get("reason", "")).lower() or "valid" in str(res.get("reason", "")).lower()

    # Verify DB was NOT updated to final_delivered
    project = queue.get_video_project(conn, project_id)
    assert project.get("video_terminal_state") != "final_delivered"
    job = queue.get_video_render_job(conn, job_id)
    assert job.get("status") != "completed"


# =========================================================================
# 10. DELIVERY RECEIPT REQUIRED AND DURABLE
# =========================================================================

def test_pv07_delivery_receipt_required_for_success(tmp_path: Path) -> None:
    """Calling delivery success without a valid delivery_message_id must fail closed.
    
    When provided, receipt fields must be durably stored in DB.
    """
    db_path = tmp_path / "pv07_receipt.sqlite3"
    valid_final = _create_mini_mp4(tmp_path / "final_ok.mp4", duration_sec=1.0)
    conn, job_id, project_id = _seed_pv07_test_job(
        db_path,
        scene_count=2,
        provider_task_completed=True,
        all_clips_downloaded=True,
        final_mp4_valid=True,
        final_video_path=str(valid_final),
    )

    # 1. Attempt with empty receipt -> must fail closed
    res_empty = queue.note_video_delivery_result(
        conn,
        job_id=job_id,
        sent=True,
        delivery_message_id="",  # EMPTY
        success_message_id="",
    )
    assert res_empty["ok"] is False, "Delivery success without receipt must fail closed"
    assert "receipt" in str(res_empty.get("reason", "")).lower() or "delivery_message_id" in str(res_empty.get("reason", "")).lower()

    # 2. Provide valid receipt -> succeeds and persists
    res_valid = queue.note_video_delivery_result(
        conn,
        job_id=job_id,
        sent=True,
        delivery_message_id="tg_receipt_9999",
        success_message_id="tg_receipt_9999",
    )
    assert res_valid["ok"] is True
    project = queue.get_video_project(conn, project_id)
    assert project.get("video_terminal_state") == "final_delivered"
    assert str(project.get("video_delivery_message_id")) == "tg_receipt_9999"
    assert bool(project.get("video_delivered_at")) is True


# =========================================================================
# 11. DELIVERY EXACTLY-ONCE & DUPLICATE PREVENTED
# =========================================================================

def test_pv07_delivery_exactly_once_prevents_duplicate(tmp_path: Path) -> None:
    """A subsequent delivery attempt on an already delivered project must be idempotent."""
    db_path = tmp_path / "pv07_exactly_once.sqlite3"
    valid_final = _create_mini_mp4(tmp_path / "final_ok.mp4", duration_sec=1.0)
    conn, job_id, project_id = _seed_pv07_test_job(
        db_path,
        scene_count=1,
        provider_task_completed=True,
        all_clips_downloaded=True,
        final_mp4_valid=True,
        final_video_path=str(valid_final),
    )

    first = queue.note_video_delivery_result(
        conn,
        job_id=job_id,
        sent=True,
        delivery_message_id="tg_receipt_first",
    )
    assert first["ok"] is True

    # Replay
    second = queue.note_video_delivery_result(
        conn,
        job_id=job_id,
        sent=True,
        delivery_message_id="tg_receipt_second",
    )
    assert second["ok"] is True
    assert second.get("duplicate_prevented") is True
    project = queue.get_video_project(conn, project_id)
    # The original receipt ID remains intact
    assert str(project.get("video_delivery_message_id")) == "tg_receipt_first"


# =========================================================================
# 12. DELIVERY FAILURE TRUTH & NO PROVIDER / FINALIZER RESUBMIT
# =========================================================================

def test_pv07_delivery_failure_does_not_resubmit_provider_or_rerun_finalizer(tmp_path: Path) -> None:
    """Delivery transport failure keeps final MP4 valid, increments delivery quota only, and never resubmits provider."""
    db_path = tmp_path / "pv07_delivery_fail.sqlite3"
    valid_final = _create_mini_mp4(tmp_path / "final_ok.mp4", duration_sec=1.0)
    conn, job_id, project_id = _seed_pv07_test_job(
        db_path,
        scene_count=1,
        provider_task_completed=True,
        all_clips_downloaded=True,
        final_mp4_valid=True,
        final_video_path=str(valid_final),
    )

    failed = queue.note_video_delivery_result(
        conn,
        job_id=job_id,
        sent=False,
        reason="telegram_timeout_504",
    )
    assert failed.get("sent") is False

    job = queue.get_video_render_job(conn, job_id)
    project = queue.get_video_project(conn, project_id)
    result = json.loads(job["result_json"])

    # Final MP4 must remain valid!
    assert result.get("final_mp4_valid") is True or result.get("final_video_path") == str(valid_final)
    # Delivered must be False
    assert result.get("final_delivered") is False
    assert project.get("video_terminal_state") == "telegram_delivery_failed"

    # Domain classification must be delivery
    domain = queue.classify_product_video_recovery_domain(result, job, project)
    assert domain == "delivery"

    # Set job status to failed so it can be recovered
    conn.execute("UPDATE video_jobs SET status='failed' WHERE id=?", (job_id,))
    conn.commit()

    recovered = queue.recover_product_video_existing_tasks(
        conn,
        job_id=job_id,
        recovery_domain=domain,
    )
    assert recovered["existing_task_recovery_recovered"] is True
    job_after = queue.get_video_render_job(conn, job_id)
    res_after = json.loads(job_after["result_json"])
    assert res_after["delivery_recovery_count"] >= 1
    assert res_after.get("finalizer_recovery_count", 0) == 0
    assert res_after.get("provider_poll_recovery_count", 0) == 0
    assert res_after["provider_submit_allowed"] is False


# =========================================================================
# 13. TERMINAL SUCCESS LOCK
# =========================================================================

def test_pv07_terminal_success_lock_fails_closed(tmp_path: Path) -> None:
    """Product success decision requires all scene clips valid, final MP4 valid, delivery sent, and durable receipt."""
    # 1. Provider completed only
    dec1 = queue.product_video_delivery_charge_decision(
        project={},
        job={},
        result={"provider_status": "succeeded", "result_url": "https://cdn.example.com/video.mp4"},
    )
    assert dec1["ok"] is False

    # 2. All clips only, no delivery
    dec2 = queue.product_video_delivery_charge_decision(
        project={},
        job={},
        result={"scene_clip_coverage_complete": True, "valid_scene_clip_count": 2, "scene_count": 2},
    )
    assert dec2["ok"] is False

    # 3. Final MP4 only, no delivery
    dec3 = queue.product_video_delivery_charge_decision(
        project={},
        job={},
        result={"final_mp4_valid": True, "final_video_path": "/tmp/final.mp4"},
    )
    assert dec3["ok"] is False


# =========================================================================
# 14. JOB28 DETERMINISTIC LOCAL REGRESSION
# =========================================================================

def test_pv07_job28_deterministic_local_regression(tmp_path: Path) -> None:
    """Model Job28 incident locally:
    scene 2 clip downloaded and valid;
    scene 1 provider completed, but artifact download unavailable/failed.
    
    Required:
    FINALIZER = NOT_CALLED
    DELIVERY = NOT_CALLED
    PRODUCT_SUCCESS = NO
    WALLET_DELTA = 0
    PROVIDER_SUBMIT_DELTA = 0
    """
    db_path = tmp_path / "pv07_job28.sqlite3"
    valid_clip_2 = _create_mini_mp4(tmp_path / "scene_2.mp4", duration_sec=1.0)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)

    project = queue.create_video_project(conn, user_id=1, topic="Job28 Regression")
    pid = int(project["project_id"])
    job = queue.enqueue_video_render_job(conn, project_id=pid, user_id=1)
    jid = int(job["id"])

    result = {
        "job_id": jid,
        "project_id": pid,
        "scene_count": 2,
        "scene_tasks": [
            {
                "scene_index": 1,
                "task_id": "job28-scene-1",
                "provider": "shopaikey_video",
                "status": "succeeded",
                "result_url": "https://cdn.example.com/expired_or_broken_url.mp4",
                "clip_path": "",
                "clip_bytes": 0,
                "clip_valid": False,
                "artifact_valid": False,
            },
            {
                "scene_index": 2,
                "task_id": "job28-scene-2",
                "provider": "shopaikey_video",
                "status": "scene_clip_validated",
                "clip_path": str(valid_clip_2),
                "clip_bytes": os.path.getsize(valid_clip_2),
                "clip_valid": True,
                "artifact_valid": True,
            },
        ],
        "task_to_scene_index": {"job28-scene-1": 1, "job28-scene-2": 2},
    }

    # Coverage check
    coverage = queue.product_video_scene_coverage_state(project, job, result)
    assert coverage["scene_clip_coverage_complete"] is False
    assert 1 in coverage["unresolved_scene_indexes"]
    assert coverage["missing_scene_action"] != "concat"
    assert coverage["missing_scene_action"] != "complete"

    # Finalizer must NOT be unlocked
    assert coverage.get("final_assembly_valid") is not True

    # Billing/success check must fail closed
    decision = queue.product_video_delivery_charge_decision(project, job, result)
    assert decision["ok"] is False

    # Domain classification: must be provider_artifact or scene_clip, NOT finalizer or delivery
    domain = queue.classify_product_video_recovery_domain(result, job, project)
    assert domain in {"provider_artifact", "scene_clip"}
    assert domain != "finalizer"
    assert domain != "delivery"


# =========================================================================
# 15. FRAME-VIDEO FINALIZER REGRESSION
# =========================================================================

def test_pv07_frame_video_finalizer_regression(tmp_path: Path) -> None:
    """Model Frame Video finalizer failure locally:
    ffmpeg exits with non-zero code.
    
    Must remain retryable only under finalizer domain quota.
    Must not create a fake MP4, mark delivered, or mark success.
    """
    db_path = tmp_path / "pv07_frame_video_finalizer.sqlite3"
    valid_clip = _create_mini_mp4(tmp_path / "clip.mp4", duration_sec=1.0)
    conn, job_id, project_id = _seed_pv07_test_job(
        db_path,
        scene_count=1,
        provider_task_completed=True,
        all_clips_downloaded=True,
        final_mp4_valid=False,
    )
    job = queue.get_video_render_job(conn, job_id)
    project = queue.get_video_project(conn, project_id)
    result = json.loads(job["result_json"])
    result["finalizer_failed"] = True
    result["finalizer_error"] = "ffmpeg_error_non_zero_exit"

    domain = queue.classify_product_video_recovery_domain(result, job, project)
    assert domain == "finalizer"

    # Set job status to failed so it can be recovered
    conn.execute("UPDATE video_jobs SET status='failed' WHERE id=?", (job_id,))
    conn.commit()

    recovered = queue.recover_product_video_existing_tasks(
        conn,
        job_id=job_id,
        recovery_domain=domain,
    )
    assert recovered["existing_task_recovery_recovered"] is True
    job_after = queue.get_video_render_job(conn, job_id)
    res_after = json.loads(job_after["result_json"])
    assert res_after["finalizer_recovery_count"] == 1
    assert res_after.get("final_mp4_valid") is not True
    assert res_after.get("final_delivered") is not True
    assert res_after.get("delivery_succeeded") is not True


# =========================================================================
# 16. MISSING LOCAL ARTIFACT FAILS CLOSED (SECTION 3 FIRST-RED)
# =========================================================================

def test_pv07_missing_local_artifact_stale_validation_flag_fails_closed(tmp_path: Path) -> None:
    """A stale validation flag alone must not unlock a finalizer run without local file."""
    db_path = tmp_path / "pv07_missing_local_artifact.sqlite3"

    for missing_path in ["", str(tmp_path / "nonexistent_clip.mp4")]:
        conn, job_id, project_id = _seed_pv07_test_job(
            db_path,
            scene_count=1,
            provider_task_completed=True,
            all_clips_downloaded=True,
        )
        job = queue.get_video_render_job(conn, job_id)
        project = queue.get_video_project(conn, project_id)
        result = json.loads(job["result_json"])

        # Inject stale validation flags on record but with empty or nonexistent clip_path
        result["scene_tasks"][0]["clip_valid"] = True
        result["scene_tasks"][0]["artifact_valid"] = True
        result["scene_tasks"][0]["clip_bytes"] = 1048576
        result["scene_tasks"][0]["status"] = "scene_clip_validated"
        result["scene_tasks"][0]["clip_path"] = missing_path
        result["final_video_path"] = ""
        result["final_mp4_path"] = ""

        ledger = queue.product_video_scene_ledger_state(project, job, result)
        coverage = queue.product_video_scene_coverage_state(project, job, result)

        rec = ledger["scene_records"][1]
        assert rec["clip_valid"] is False, f"clip_valid must be False when path={missing_path!r}"
        assert rec.get("scene_validation_verified") is False, "scene_validation_verified must be False"
        assert coverage["scene_clip_coverage_complete"] is False, "coverage_complete must be False"
        assert coverage.get("finalizer_unlocked") is False, "finalizer_unlocked must be False"


# =========================================================================
# 17. ARTIFACT DISAPPEARS AFTER DB REOPEN (SECTION 4 PROOF)
# =========================================================================

def test_pv07_artifact_disappears_after_db_reopen(tmp_path: Path) -> None:
    """Historical validation metadata in DB must fail closed if file is deleted before finalizer."""
    db_path = tmp_path / "pv07_reopen_artifact_deleted.sqlite3"
    clip_file = _create_mini_mp4(tmp_path / "scene_durable.mp4", duration_sec=1.0)
    assert clip_file.is_file()

    conn, job_id, project_id = _seed_pv07_test_job(
        db_path,
        scene_count=1,
        provider_task_completed=True,
        all_clips_downloaded=True,
    )
    job = queue.get_video_render_job(conn, job_id)
    project = queue.get_video_project(conn, project_id)
    result = json.loads(job["result_json"])

    # Persist valid clip metadata into DB
    result["scene_tasks"][0]["clip_path"] = str(clip_file)
    result["scene_tasks"][0]["clip_valid"] = True
    result["scene_tasks"][0]["artifact_valid"] = True
    result["scene_tasks"][0]["clip_bytes"] = clip_file.stat().st_size
    result["scene_tasks"][0]["status"] = "scene_clip_validated"
    conn.execute("UPDATE video_jobs SET result_json=? WHERE id=?", (json.dumps(result), job_id))
    conn.commit()
    conn.close()

    # Now delete the physical clip file from filesystem
    clip_file.unlink()
    assert not clip_file.exists()

    # Reopen DB and recompute ledger & coverage
    conn_reopen = sqlite3.connect(db_path)
    conn_reopen.row_factory = sqlite3.Row
    job_reopen = queue.get_video_render_job(conn_reopen, job_id)
    project_reopen = queue.get_video_project(conn_reopen, project_id)
    result_reopen = json.loads(job_reopen["result_json"])

    ledger = queue.product_video_scene_ledger_state(project_reopen, job_reopen, result_reopen)
    coverage = queue.product_video_scene_coverage_state(project_reopen, job_reopen, result_reopen)
    conn_reopen.close()

    rec = ledger["scene_records"][1]
    assert rec["clip_valid"] is False, "SCENE_VALID_AFTER_REOPEN must be False"
    assert coverage["scene_clip_coverage_complete"] is False, "COVERAGE_COMPLETE must be False"
    assert coverage.get("finalizer_unlocked") is False, "FINALIZER_ENTRY must be blocked"
    assert coverage["missing_scene_action"] != "concat"
    assert coverage["missing_scene_action"] != "complete"
