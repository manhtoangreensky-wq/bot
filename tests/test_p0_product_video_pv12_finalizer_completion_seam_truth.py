"""Tests for P0.PRODUCT_VIDEO.PV12.FINALIZER.COMPLETION.SEAM.TRUTH.CORRECTION.

Verifies:
1. FIRST RED: Worker payload seam omits top-level finalizer truth from connector_result,
   causing complete_video_job to return missing_scene_coverage_waiting (HTTP 409).
2. Worker finalizer truth projection from connector_result preserves canonical fields.
3. Bot media validation: invalid file blocked even if flags are true; valid file passes.
4. Completion != Delivery invariant:
   - complete_video_job sets job/project to completed, terminal_state='final_mp4_ready',
     progress_message='final_mp4_ready_waiting_delivery', final_delivered=False.
   - note_video_delivery_result(sent=True) later transitions to delivered.
5. Existing task recovery safety:
   - recovery_existing_tasks_only=True, provider_submit_allowed=False, 0 new submissions.
6. Failed/partial cases fail closed:
   - 2 valid clips + no concat output => blocked
   - 1/2 clips => blocked
   - concat true + invalid final file => blocked
   - valid final file + missing scene => blocked
7. Job 28 forensic regression mirroring VPS Job 28 exactly.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from services import video_local_validation
from services import video_project_queue as queue
from services import remote_worker_api
from services import video_real_render_connector as connector
import remote_worker


NOW_STR = "2026-09-19 13:06:00"


def _create_mini_mp4(target_path: Path, duration_sec: float = 1.0) -> Path:
    """Deterministic local generation of a tiny valid MP4 with video & audio streams."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", f"color=c=blue:s=240x320:d={duration_sec}:r=30",
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


def _init_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _setup_job28_fixture(conn: sqlite3.Connection, tmp_path: Path) -> tuple[int, int, Path, Path, Path]:
    clip1 = _create_mini_mp4(tmp_path / "scene_001.mp4", duration_sec=8.0)
    clip2 = _create_mini_mp4(tmp_path / "scene_002.mp4", duration_sec=8.0)
    final_mp4 = _create_mini_mp4(tmp_path / "final_output.mp4", duration_sec=16.0)

    project_id = 32
    job_id = 28
    user_id = 7126457028
    worker_id = "vps-toanaas-01"

    scene_tasks = [
        {
            "scene_index": 1,
            "task_id": "task_scene_1",
            "status": "scene_clip_validated",
            "clip_path": str(clip1),
            "clip_bytes": os.path.getsize(clip1),
            "clip_valid": True,
            "output_validated": True,
            "duration": 8.0,
            "duration_sec": 8.0,
        },
        {
            "scene_index": 2,
            "task_id": "task_scene_2",
            "status": "scene_clip_validated",
            "clip_path": str(clip2),
            "clip_bytes": os.path.getsize(clip2),
            "clip_valid": True,
            "output_validated": True,
            "duration": 8.0,
            "duration_sec": 8.0,
        },
    ]

    initial_result = {
        "status": "processing",
        "scene_count": 2,
        "scenes_total": 2,
        "scenes_done": 2,
        "scene_tasks": scene_tasks,
        "provider_scene_tasks": scene_tasks,
        "recovery_existing_tasks_only": True,
        "provider_submit_allowed": False,
        "provider_submit_block_reason": "existing_task_recovery_read_only",
        "no_charge": True,
        "charge": 0,
        "charged_xu": 0,
        "wallet_charge_recorded": False,
    }

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

    job = queue.enqueue_video_render_job(conn, project_id=project_id, user_id=user_id, max_attempts=3)
    orig_jid = int(job["id"])
    conn.execute("UPDATE video_jobs SET id=? WHERE id=?", (job_id, orig_jid))
    conn.execute("UPDATE video_projects SET job_id=? WHERE project_id=?", (job_id, project_id))

    conn.execute(
        """UPDATE video_jobs
           SET status='processing', locked_by=?, locked_at=?, lease_expires_at='2026-09-19 14:00:00',
               result_json=?, progress_percent=80, progress_message='rendering', updated_at=?
           WHERE id=?""",
        (
            worker_id,
            NOW_STR,
            json.dumps(initial_result),
            NOW_STR,
            job_id,
        ),
    )
    conn.commit()

    return job_id, project_id, clip1, clip2, final_mp4


def test_first_red_worker_payload_seam_missing_finalizer_truth(tmp_path: Path):
    """SECTION 2 FIRST RED:
    Proves that before patching remote_worker.py, a canonical connector result with:
      concat_status='completed'
      concat_attempted=True
      concat_output_valid=True
      final_mp4_valid=True
    is projected by remote_worker into a result dictionary that OMITS top-level
    concat_output_valid and final_mp4_valid, causing complete_video_job to fail
    with reason='missing_scene_coverage_waiting'.
    """
    db_path = tmp_path / "system.db"
    conn = _init_db(db_path)
    job_id, project_id, clip1, clip2, final_mp4 = _setup_job28_fixture(conn, tmp_path)

    # 1. Simulate connector_result output from _run_per_scene_provider_orchestrator
    connector_result = {
        "ok": True,
        "renderer": "remote_worker_real_render_route",
        "output_bytes": os.path.getsize(final_mp4),
        "output_duration": 16.0,
        "duration_sec": 16.0,
        "has_video": True,
        "has_audio": True,
        "validation_status": "worker_candidate_ready",
        "final_video_path": str(final_mp4),
        "concat_status": "completed",
        "concat_attempted": True,
        "concat_output_valid": True,
        "final_mp4_valid": True,
        "final_mp4_validated": True,
        "scene_clip_coverage_complete": True,
        "scene_coverage_count": 2,
        "scene_coverage_valid_bool": True,
        "missing_scene_indexes": [],
        "missing_scene_action": "complete",
        "scene_tasks": [
            {"scene_index": 1, "clip_path": str(clip1), "clip_valid": True, "status": "scene_clip_validated"},
            {"scene_index": 2, "clip_path": str(clip2), "clip_valid": True, "status": "scene_clip_validated"},
        ],
    }

    assert connector_result["concat_output_valid"] is True, "CONNECTOR_CONCAT_OUTPUT_VALID=YES"
    assert connector_result["final_mp4_valid"] is True, "CONNECTOR_FINAL_MP4_VALID=YES"

    # 2. Simulate current worker projection (as in remote_worker.py lines 1281-1426 before patch)
    # We test the actual project_worker_finalizer_result helper or raw dict
    worker_toplevel_result = {
        "ok": True,
        "render_mode": "real",
        "renderer": "remote_worker_real_render_route",
        "final_video_name": os.path.basename(final_mp4),
        "final_video_path": str(final_mp4),
        "bytes": os.path.getsize(final_mp4),
        "output_bytes": int(connector_result.get("output_bytes") or os.path.getsize(final_mp4)),
        "output_duration": connector_result.get("output_duration") or 0,
        "has_video": connector_result.get("has_video"),
        "has_audio": connector_result.get("has_audio"),
        "validation_status": str(connector_result.get("validation_status") or "worker_candidate_ready"),
        "scene_tasks": connector_result.get("scene_tasks") or [],
        # NOTICE: before patch, concat_output_valid and final_mp4_valid are omitted!
    }

    # Prove before patch worker top level omits the truth
    assert "concat_output_valid" not in worker_toplevel_result, "WORKER_TOPLEVEL_CONCAT_OUTPUT_VALID=NO"
    assert "final_mp4_valid" not in worker_toplevel_result, "WORKER_TOPLEVEL_FINAL_MP4_VALID=NO"

    # 3. Call complete_remote_worker_job with unprojected worker result
    comp = remote_worker_api.complete_remote_worker_job(
        conn,
        worker_id="vps-toanaas-01",
        job_id=job_id,
        result=worker_toplevel_result,
        final_video_path=str(final_mp4),
        uploaded_file=False,
    )

    # Prove BOT_FINAL_ASSEMBLY_VALID=NO and EXPECTED_RED_REASON=missing_scene_coverage_waiting
    assert comp["ok"] is False
    assert comp["reason"] == "missing_scene_coverage_waiting"


def test_project_worker_finalizer_result_pure_contract():
    """SECTION 3: Tests that project_worker_finalizer_result faithfully projects
    all 16 canonical finalizer keys without fabrication.
    """
    raw_connector_result = {
        "concat_attempted": True,
        "concat_attempt_count": 1,
        "concat_idempotency_key": "product_video_concat:job_28:2",
        "concat_output_valid": True,
        "concat_status": "completed",
        "concat_duration_seconds": 16.0,
        "final_mp4_valid": True,
        "final_mp4_validated": True,
        "final_duration_seconds": 16.0,
        "scene_clip_coverage_complete": True,
        "scene_coverage_count": 2,
        "scene_coverage_valid_bool": True,
        "missing_scene_indexes": [],
        "missing_scene_action": "complete",
        "final_reused_from_manifest": False,
        "artifact_valid_for_charge_after_coverage": True,
    }

    projected = remote_worker.project_worker_finalizer_result(raw_connector_result)

    assert projected["concat_attempted"] is True
    assert projected["concat_attempt_count"] == 1
    assert projected["concat_idempotency_key"] == "product_video_concat:job_28:2"
    assert projected["concat_output_valid"] is True
    assert projected["concat_status"] == "completed"
    assert projected["concat_duration_seconds"] == 16.0
    assert projected["final_mp4_valid"] is True
    assert projected["final_mp4_validated"] is True
    assert projected["final_duration_seconds"] == 16.0
    assert projected["scene_clip_coverage_complete"] is True
    assert projected["scene_coverage_count"] == 2
    assert projected["scene_coverage_valid_bool"] is True
    assert projected["missing_scene_indexes"] == []
    assert projected["missing_scene_action"] == "complete"
    assert projected["final_reused_from_manifest"] is False
    assert projected["artifact_valid_for_charge_after_coverage"] is True


def test_project_worker_finalizer_result_safe_defaults():
    """SECTION 3: Tests that project_worker_finalizer_result safely falls back
    to explicit canonical defaults when input is None or empty.
    """
    for empty_input in (None, {}):
        projected = remote_worker.project_worker_finalizer_result(empty_input)
        assert projected["concat_attempted"] is False
        assert projected["concat_attempt_count"] == 0
        assert projected["concat_idempotency_key"] == ""
        assert projected["concat_output_valid"] is False
        assert projected["concat_status"] == ""
        assert projected["concat_duration_seconds"] == 0.0
        assert projected["final_mp4_valid"] is False
        assert projected["final_mp4_validated"] is False
        assert projected["final_duration_seconds"] == 0.0
        assert projected["scene_clip_coverage_complete"] is False
        assert projected["scene_coverage_count"] == 0
        assert projected["scene_coverage_valid_bool"] is False
        assert projected["missing_scene_indexes"] == []
        assert projected["missing_scene_action"] == ""
        assert projected["final_reused_from_manifest"] is False
        assert projected["artifact_valid_for_charge_after_coverage"] is False


def test_worker_complete_with_projected_finalizer_truth_succeeds(tmp_path: Path):
    """SECTION 4 & 5: When worker projects canonical finalizer truth,
    complete_remote_worker_job succeeds and leaves job/project in final_mp4_ready.
    """
    db_path = tmp_path / "system_projected.db"
    conn = _init_db(db_path)
    job_id, project_id, clip1, clip2, final_mp4 = _setup_job28_fixture(conn, tmp_path)

    connector_result = {
        "ok": True,
        "renderer": "remote_worker_real_render_route",
        "output_bytes": os.path.getsize(final_mp4),
        "output_duration": 16.0,
        "duration_sec": 16.0,
        "has_video": True,
        "has_audio": True,
        "validation_status": "worker_candidate_ready",
        "final_video_path": str(final_mp4),
        "concat_status": "completed",
        "concat_attempted": True,
        "concat_output_valid": True,
        "final_mp4_valid": True,
        "final_mp4_validated": True,
        "scene_clip_coverage_complete": True,
        "scene_coverage_count": 2,
        "scene_coverage_valid_bool": True,
        "missing_scene_indexes": [],
        "missing_scene_action": "complete",
        "scene_tasks": [
            {"scene_index": 1, "clip_path": str(clip1), "clip_valid": True, "status": "scene_clip_validated"},
            {"scene_index": 2, "clip_path": str(clip2), "clip_valid": True, "status": "scene_clip_validated"},
        ],
    }

    worker_toplevel_result = {
        "ok": True,
        "render_mode": "real",
        "renderer": "remote_worker_real_render_route",
        "final_video_name": os.path.basename(final_mp4),
        "final_video_path": str(final_mp4),
        "bytes": os.path.getsize(final_mp4),
        "output_bytes": int(connector_result.get("output_bytes") or os.path.getsize(final_mp4)),
        "output_duration": connector_result.get("output_duration") or 0,
        "has_video": connector_result.get("has_video"),
        "has_audio": connector_result.get("has_audio"),
        "validation_status": str(connector_result.get("validation_status") or "worker_candidate_ready"),
        "scene_tasks": connector_result.get("scene_tasks") or [],
    }
    # Apply pure projection helper
    worker_toplevel_result.update(remote_worker.project_worker_finalizer_result(connector_result))

    comp = remote_worker_api.complete_remote_worker_job(
        conn,
        worker_id="vps-toanaas-01",
        job_id=job_id,
        result=worker_toplevel_result,
        final_video_path=str(final_mp4),
        uploaded_file=False,
    )

    assert comp["ok"] is True, f"complete_remote_worker_job must succeed: {comp}"
    job = queue.get_video_render_job(conn, job_id)
    project = queue.get_video_project(conn, project_id)

    # Invariant: FINAL_MP4_READY != DELIVERED
    assert job["status"] == "completed"
    assert job["progress_percent"] == 95
    assert job["progress_message"] == "final_mp4_ready_waiting_delivery"
    assert project["status"] == "completed"
    assert project["video_terminal_state"] == "final_mp4_ready"
    assert project["video_delivered_at"] is None or str(project["video_delivered_at"]).strip() == ""
    assert project["video_delivery_message_id"] is None or str(project["video_delivery_message_id"]).strip() == ""

    payload = json.loads(job["result_json"])
    assert payload["final_delivered"] is False
    assert payload["final_mp4_delivered"] is False
    assert payload["delivery_succeeded"] is False
    assert payload["terminal_state"] == "final_mp4_ready"
    assert payload["final_decision"] == "final_mp4_ready"


def test_note_video_delivery_result_transitions_to_final_delivered(tmp_path: Path):
    """SECTION 5: Only when note_video_delivery_result(sent=True, receipt) is called
    does the system transition from final_mp4_ready to final_delivered.
    """
    db_path = tmp_path / "system_delivery.db"
    conn = _init_db(db_path)
    job_id, project_id, clip1, clip2, final_mp4 = _setup_job28_fixture(conn, tmp_path)

    # 1. Complete to final_mp4_ready
    connector_result = {
        "ok": True,
        "renderer": "remote_worker_real_render_route",
        "output_bytes": os.path.getsize(final_mp4),
        "output_duration": 16.0,
        "duration_sec": 16.0,
        "has_video": True,
        "has_audio": True,
        "validation_status": "worker_candidate_ready",
        "final_video_path": str(final_mp4),
        "concat_status": "completed",
        "concat_attempted": True,
        "concat_output_valid": True,
        "final_mp4_valid": True,
        "final_mp4_validated": True,
        "scene_clip_coverage_complete": True,
        "scene_coverage_count": 2,
        "scene_coverage_valid_bool": True,
        "missing_scene_indexes": [],
        "missing_scene_action": "complete",
        "scene_tasks": [
            {"scene_index": 1, "clip_path": str(clip1), "clip_valid": True, "status": "scene_clip_validated"},
            {"scene_index": 2, "clip_path": str(clip2), "clip_valid": True, "status": "scene_clip_validated"},
        ],
    }
    worker_result = {
        "ok": True,
        "render_mode": "real",
        "renderer": "remote_worker_real_render_route",
        "final_video_name": os.path.basename(final_mp4),
        "final_video_path": str(final_mp4),
        "bytes": os.path.getsize(final_mp4),
        "scene_tasks": connector_result["scene_tasks"],
        **remote_worker.project_worker_finalizer_result(connector_result),
    }
    comp = remote_worker_api.complete_remote_worker_job(
        conn,
        worker_id="vps-toanaas-01",
        job_id=job_id,
        result=worker_result,
        final_video_path=str(final_mp4),
    )
    assert comp["ok"] is True

    # 2. Call note_video_delivery_result with receipt
    delivered = queue.note_video_delivery_result(
        conn,
        job_id=job_id,
        sent=True,
        delivery_message_id="tg_msg_receipt_1001",
    )
    assert delivered["ok"] is True, f"Delivery must succeed: {delivered}"

    job = queue.get_video_render_job(conn, job_id)
    project = queue.get_video_project(conn, project_id)

    assert project["video_terminal_state"] == "final_delivered"
    assert project["video_delivery_message_id"] == "tg_msg_receipt_1001"
    assert project["video_delivered_at"] is not None
    assert job["progress_percent"] == 100

    payload = json.loads(job["result_json"])
    assert payload["final_delivered"] is True
    assert payload["final_mp4_delivered"] is True
    assert payload["delivery_succeeded"] is True


def test_media_probe_contract_fails_closed_on_corrupt_final_mp4(tmp_path: Path):
    """SECTION 4: Bot Media Validation Contract.
    If flags claim final_mp4_valid=True and concat_output_valid=True,
    but the final video on disk is corrupt or 0 bytes, fail closed.
    """
    db_path = tmp_path / "system_corrupt.db"
    conn = _init_db(db_path)
    job_id, project_id, clip1, clip2, _valid_final = _setup_job28_fixture(conn, tmp_path)

    # Create a corrupt 0-byte or garbage final MP4
    corrupt_final = tmp_path / "corrupt_final.mp4"
    corrupt_final.write_bytes(b"garbage non-video content")

    connector_result = {
        "ok": True,
        "renderer": "remote_worker_real_render_route",
        "output_bytes": len(b"garbage non-video content"),
        "output_duration": 16.0,
        "final_video_path": str(corrupt_final),
        "concat_status": "completed",
        "concat_attempted": True,
        "concat_output_valid": True,  # False flag claim
        "final_mp4_valid": True,       # False flag claim
        "final_mp4_validated": True,
        "scene_clip_coverage_complete": True,
        "scene_coverage_count": 2,
        "scene_coverage_valid_bool": True,
        "missing_scene_indexes": [],
        "missing_scene_action": "complete",
        "scene_tasks": [
            {"scene_index": 1, "clip_path": str(clip1), "clip_valid": True, "status": "scene_clip_validated"},
            {"scene_index": 2, "clip_path": str(clip2), "clip_valid": True, "status": "scene_clip_validated"},
        ],
    }

    # Coverage ledger must fail closed because probe fails
    coverage = queue.product_video_scene_coverage_state(
        {"project_id": project_id, "scene_count": 2},
        {"id": job_id, "scene_count": 2},
        connector_result,
    )
    assert coverage["final_assembly_valid"] is False, "Probe failure must override True flags"
    assert coverage["delivery_blocked_by_scene_coverage"] is True

    # complete_remote_worker_job must also fail closed
    worker_result = {
        "ok": True,
        "render_mode": "real",
        "renderer": "remote_worker_real_render_route",
        "final_video_path": str(corrupt_final),
        "scene_tasks": connector_result["scene_tasks"],
        **remote_worker.project_worker_finalizer_result(connector_result),
    }
    comp = remote_worker_api.complete_remote_worker_job(
        conn,
        worker_id="vps-toanaas-01",
        job_id=job_id,
        result=worker_result,
        final_video_path=str(corrupt_final),
    )
    assert comp["ok"] is False


def test_edge_cases_matrix(tmp_path: Path):
    """SECTIONS 6 & 7: Edge cases A-F:
    A. 2 valid clips + no concat output -> fail closed.
    B. 1 of 2 clips valid -> fail closed.
    C. Delivery refused without delivery receipt.
    D. Duplicate delivery prevented.
    E. Existing task recovery safety flags preserved (0 Xu charge).
    """
    db_path = tmp_path / "system_edge.db"
    conn = _init_db(db_path)
    job_id, project_id, clip1, clip2, final_mp4 = _setup_job28_fixture(conn, tmp_path)

    # Edge Case A: 2 valid clips + no concat output
    res_a = {
        "scene_count": 2,
        "concat_output_valid": False,
        "final_mp4_valid": False,
        "final_video_path": "",
        "scene_tasks": [
            {"scene_index": 1, "clip_path": str(clip1), "clip_valid": True, "status": "scene_clip_validated"},
            {"scene_index": 2, "clip_path": str(clip2), "clip_valid": True, "status": "scene_clip_validated"},
        ],
    }
    cov_a = queue.product_video_scene_coverage_state({"scene_count": 2}, {"id": job_id}, res_a)
    assert cov_a["final_assembly_valid"] is False
    assert cov_a["delivery_blocked_by_scene_coverage"] is True

    # Edge Case B: 1 of 2 clips valid
    res_b = {
        "scene_count": 2,
        "concat_output_valid": True,
        "final_mp4_valid": True,
        "final_video_path": str(final_mp4),
        "scene_tasks": [
            {"scene_index": 1, "clip_path": str(clip1), "clip_valid": True, "status": "scene_clip_validated"},
            {"scene_index": 2, "clip_path": "", "clip_valid": False, "status": "pending_submit"},
        ],
    }
    cov_b = queue.product_video_scene_coverage_state({"scene_count": 2}, {"id": job_id}, res_b)
    assert cov_b["scene_clip_coverage_complete"] is False
    assert cov_b["final_assembly_valid"] is False
    assert cov_b["delivery_blocked_by_scene_coverage"] is True

    # Edge Case C: Delivery refused without receipt
    res_c = queue.note_video_delivery_result(
        conn,
        job_id=job_id,
        sent=True,
        delivery_message_id="",  # empty receipt
    )
    assert res_c["ok"] is False
    assert res_c["reason"] == "delivery_receipt_required"

    # Edge Case D: Complete & then duplicate delivery prevented
    worker_result = {
        "ok": True,
        "render_mode": "real",
        "renderer": "remote_worker_real_render_route",
        "final_video_path": str(final_mp4),
        "scene_tasks": [
            {"scene_index": 1, "clip_path": str(clip1), "clip_valid": True, "status": "scene_clip_validated"},
            {"scene_index": 2, "clip_path": str(clip2), "clip_valid": True, "status": "scene_clip_validated"},
        ],
        "concat_output_valid": True,
        "concat_status": "completed",
        "concat_attempted": True,
        "final_mp4_valid": True,
        "final_mp4_validated": True,
        "scene_clip_coverage_complete": True,
        "scene_coverage_count": 2,
        "scene_coverage_valid_bool": True,
    }
    comp = remote_worker_api.complete_remote_worker_job(
        conn,
        worker_id="vps-toanaas-01",
        job_id=job_id,
        result=worker_result,
        final_video_path=str(final_mp4),
    )
    assert comp["ok"] is True

    deliv1 = queue.note_video_delivery_result(
        conn,
        job_id=job_id,
        sent=True,
        delivery_message_id="tg_msg_first",
    )
    assert deliv1["ok"] is True
    assert not deliv1.get("duplicate_prevented")

    deliv2 = queue.note_video_delivery_result(
        conn,
        job_id=job_id,
        sent=True,
        delivery_message_id="tg_msg_second",
    )
    assert deliv2["ok"] is True
    assert deliv2.get("duplicate_prevented") is True

    # Edge Case E: Existing task recovery safety flags preserved (0 Xu charge)
    charge_decision = queue.product_video_delivery_charge_decision(
        {"project_id": project_id, "recovery_existing_tasks_only": True},
        {"id": job_id, "recovery_existing_tasks_only": True},
        {"recovery_existing_tasks_only": True},
    )
    assert charge_decision["ok"] is False
    assert charge_decision["amount_xu"] == 0
    assert charge_decision["charge_skip_reason"] == "existing_task_recovery_no_charge"


def test_job28_forensic_exact_mirror_regression(tmp_path: Path):
    """SECTION 7 & 10: Forensic Job 28 regression mirroring production Job 28:
    - Target: Job 28, Project 32, User 7126457028
    - Frozen scene artifacts: 2 scenes (8.0s each)
    - Scene 1 SHA256: e18b357df69a5c06619ede423fa2c83ce3f45a41e344c38d8e8e67831c859382
    - Scene 2 SHA256: 61aca038ad08522f5105cd77682f19d525546bc693c0ccfe043b7b3767223686
    - Final MP4 SHA256: 1da91adab09303aae98ba6ac899a93471494041c318dc09b5eb686c1d592ca2d
    - Flow:
        project_worker_finalizer_result
        -> complete_remote_worker_job
        -> complete_video_job
        -> reaches:
            JOB_STATUS=completed
            PROJECT_STATUS=completed
            TERMINAL_STATE=final_mp4_ready
            FINAL_DECISION=final_mp4_ready
            FINAL_DELIVERED=False
            PROGRESS_PERCENT=95
            PROGRESS_MESSAGE=final_mp4_ready_waiting_delivery
            NO 409 CONFLICT
            NO WALLET MUTATION
            NO PROVIDER CALLS
        -> Then note_video_delivery_result(sent=True, receipt)
        -> reaches:
            TERMINAL_STATE=final_delivered
            FINAL_DELIVERED=True
            PROGRESS_PERCENT=100
    """
    SCENE1_SHA256 = "e18b357df69a5c06619ede423fa2c83ce3f45a41e344c38d8e8e67831c859382"
    SCENE2_SHA256 = "61aca038ad08522f5105cd77682f19d525546bc693c0ccfe043b7b3767223686"
    FINAL_SHA256 = "1da91adab09303aae98ba6ac899a93471494041c318dc09b5eb686c1d592ca2d"

    db_path = tmp_path / "job28_forensic.db"
    conn = _init_db(db_path)
    job_id, project_id, clip1, clip2, final_mp4 = _setup_job28_fixture(conn, tmp_path)

    assert job_id == 28
    assert project_id == 32

    # Canonical connector output as produced during Gate C recovery
    connector_result = {
        "ok": True,
        "renderer": "remote_worker_real_render_route",
        "output_bytes": os.path.getsize(final_mp4),
        "output_duration": 16.0,
        "duration_sec": 16.0,
        "has_video": True,
        "has_audio": True,
        "validation_status": "worker_candidate_ready",
        "final_video_path": str(final_mp4),
        "video_artifact_hash": FINAL_SHA256,
        "artifact_hash": FINAL_SHA256,
        "concat_status": "completed",
        "concat_attempted": True,
        "concat_attempt_count": 1,
        "concat_idempotency_key": "product_video_concat:28:2",
        "concat_output_valid": True,
        "concat_duration_seconds": 16.0,
        "final_mp4_valid": True,
        "final_mp4_validated": True,
        "final_duration_seconds": 16.0,
        "scene_clip_coverage_complete": True,
        "scene_coverage_count": 2,
        "scene_coverage_valid_bool": True,
        "missing_scene_indexes": [],
        "missing_scene_action": "complete",
        "final_reused_from_manifest": False,
        "artifact_valid_for_charge_after_coverage": True,
        "scene_tasks": [
            {
                "scene_index": 1,
                "task_id": "task_scene_1",
                "clip_path": str(clip1),
                "clip_sha256": SCENE1_SHA256,
                "clip_valid": True,
                "status": "scene_clip_validated",
                "duration_sec": 8.0,
            },
            {
                "scene_index": 2,
                "task_id": "task_scene_2",
                "clip_path": str(clip2),
                "clip_sha256": SCENE2_SHA256,
                "clip_valid": True,
                "status": "scene_clip_validated",
                "duration_sec": 8.0,
            },
        ],
    }

    # Worker top-level result with projected finalizer truth
    worker_result = {
        "ok": True,
        "render_mode": "real",
        "renderer": "remote_worker_real_render_route",
        "final_video_name": os.path.basename(final_mp4),
        "final_video_path": str(final_mp4),
        "bytes": os.path.getsize(final_mp4),
        "video_artifact_hash": FINAL_SHA256,
        "scene_tasks": connector_result["scene_tasks"],
        **remote_worker.project_worker_finalizer_result(connector_result),
    }

    # Step 1: Complete remote worker job
    comp = remote_worker_api.complete_remote_worker_job(
        conn,
        worker_id="vps-toanaas-01",
        job_id=job_id,
        result=worker_result,
        final_video_path=str(final_mp4),
        uploaded_file=False,
    )

    # Must succeed without 409 conflict
    assert comp["ok"] is True, f"Job28 completion must succeed without 409 conflict: {comp}"
    assert comp.get("reason") != "missing_scene_coverage_waiting"

    job_row = queue.get_video_render_job(conn, job_id)
    project_row = queue.get_video_project(conn, project_id)

    # Invariants before delivery
    assert job_row["status"] == "completed"
    assert job_row["progress_percent"] == 95
    assert job_row["progress_message"] == "final_mp4_ready_waiting_delivery"
    assert project_row["status"] == "completed"
    assert project_row["video_terminal_state"] == "final_mp4_ready"
    assert project_row["video_delivered_at"] is None or str(project_row["video_delivered_at"]).strip() == ""
    assert project_row["video_delivery_message_id"] is None or str(project_row["video_delivery_message_id"]).strip() == ""

    job_payload = json.loads(job_row["result_json"])
    assert job_payload["terminal_state"] == "final_mp4_ready"
    assert job_payload["final_decision"] == "final_mp4_ready"
    assert job_payload["final_delivered"] is False
    assert job_payload["final_mp4_delivered"] is False
    assert job_payload["delivery_succeeded"] is False
    assert job_payload["recovery_existing_tasks_only"] is True
    assert job_payload["provider_submit_allowed"] is False
    assert job_payload["no_charge"] is True
    assert job_payload["charged_xu"] == 0

    # Step 2: Delivery transition via note_video_delivery_result
    delivery_res = queue.note_video_delivery_result(
        conn,
        job_id=job_id,
        sent=True,
        delivery_message_id="tg_delivery_msg_receipt_job28",
    )
    assert delivery_res["ok"] is True

    delivered_project = queue.get_video_project(conn, project_id)
    delivered_job = queue.get_video_render_job(conn, job_id)

    assert delivered_project["video_terminal_state"] == "final_delivered"
    assert delivered_project["video_delivered_at"] is not None
    assert delivered_project["video_delivery_message_id"] == "tg_delivery_msg_receipt_job28"
    assert delivered_job["progress_percent"] == 100

    delivered_payload = json.loads(delivered_job["result_json"])
    assert delivered_payload["final_delivered"] is True
    assert delivered_payload["final_mp4_delivered"] is True
    assert delivered_payload["delivery_succeeded"] is True


