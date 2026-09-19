"""Tests for P0.PRODUCT_VIDEO.PV12.JOB28.COMPLETION.ONLY.RECONCILIATION.SOURCE.

Enforces:
1. FIRST RED: terminal failed job cannot be completion-reconciled via complete_video_job.
2. Explicit fail-closed completion-only reconciliation authority for terminal failed jobs
   with proven, physically valid existing final MP4s.
3. Strict Owner authorization gate (owner_authorized=True required).
4. Strict artifact SHA256 binding and physical ffprobe media validation.
5. CAS concurrency protection with BEGIN IMMEDIATE.
6. Zero second recovery, zero job requeue, zero worker claim.
7. Zero provider calls, zero Telegram delivery calls, zero wallet mutations.
8. Idempotency protection: exact replay is a non-mutating no-op.
9. Comprehensive wrong job/artifact fail-closed protection matrix.
10. Forensic mirror regression of Job 28 state machine.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch, MagicMock

import pytest

from services import video_local_validation
from services import video_project_queue as queue


NOW_STR = "2026-09-19 14:16:08"
JOB28_FORENSIC_SHA256 = "1da91adab09303aae98ba6ac899a93471494041c318dc09b5eb686c1d592ca2d"


def _create_mini_mp4(target_path: Path, duration_sec: float = 16.0, resolution: str = "240x320") -> tuple[Path, str]:
    """Deterministic generation of a valid test MP4 with video & audio streams and returns (path, sha256)."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", f"color=c=blue:s={resolution}:d={duration_sec}:r=30",
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
    with open(target_path, "rb") as f:
        sha256 = hashlib.sha256(f.read()).hexdigest()
    return target_path, sha256


def _setup_terminal_failed_db(conn: sqlite3.Connection, mp4_path: Path, *, job_id: int = 28, project_id: int = 32, user_id: int = 7126457028) -> dict[str, Any]:
    """Sets up an isolated database with a terminal failed Job 28 equivalent."""
    queue.ensure_video_project_queue_schema(conn)
    conn.execute(
        """INSERT INTO video_projects (
            project_id, user_id, status, ratio, quality_tier, scene_count,
            asset_pack_json, total_xu_estimated, video_terminal_state,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            project_id,
            user_id,
            "failed",
            "9:16",
            400,
            2,
            json.dumps({"source": "product_video", "render_mode": "real", "recovery_existing_tasks_only": True}),
            144,
            "failed_no_charge",
            NOW_STR,
            NOW_STR,
        ),
    )
    result_payload = {
        "status": "provider_pending",
        "terminal_state": "failed_no_charge",
        "final_decision": "failed_no_charge",
        "final_delivered": False,
        "final_mp4_delivered": False,
        "delivery_succeeded": False,
        "final_video_path": str(mp4_path),
        "concat_output_valid": True,
        "final_mp4_valid": True,
        "scene_coverage_count": 2,
        "scene_clip_coverage_complete": True,
        "scene_coverage_valid_bool": True,
        "missing_scene_indexes": [],
        "recovery_existing_tasks_only": True,
        "no_charge": True,
        "charge": 0,
        "charged_xu": 0,
        "wallet_charge_recorded": False,
    }
    conn.execute(
        """INSERT INTO video_jobs (
            id, project_id, user_id, job_type, status, priority, attempts, max_attempts,
            last_error, progress_percent, progress_message, result_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            job_id,
            project_id,
            user_id,
            "video_render",
            "failed",
            100,
            44,
            3,
            "provider_in_progress",
            84,
            "waiting_missing_scene_coverage",
            json.dumps(result_payload),
            NOW_STR,
            NOW_STR,
        ),
    )
    conn.commit()
    return result_payload


def test_first_red_terminal_failed_job_with_proven_final_mp4_cannot_be_completion_reconciled(tmp_path: Path):
    """FIRST RED:

    Prove that in the current codebase, a terminal failed Product Video job (such as Job 28
    post Gate C) with an already-existing, valid final MP4 cannot be completion-reconciled
    by complete_video_job (returns 'job_already_terminal_failed'), and that the dedicated
    reconcile_existing_final_mp4_ready function exists and guards this path.
    """
    conn = sqlite3.connect(tmp_path / "test_red.db")
    conn.row_factory = sqlite3.Row
    mp4_path, _ = _create_mini_mp4(tmp_path / "final_output_28.mp4", duration_sec=16.0)
    result_payload = _setup_terminal_failed_db(conn, mp4_path)

    # 1. Calling canonical complete_video_job fails-closed with job_already_terminal_failed
    res = queue.complete_video_job(conn, job_id=28, result=result_payload, final_video_path=str(mp4_path))
    assert res["ok"] is False
    assert res["reason"] == "job_already_terminal_failed"

    # 2. Reconcile function exists on queue module
    assert hasattr(queue, "reconcile_existing_final_mp4_ready")


def test_owner_authorization_guard_fail_closed(tmp_path: Path):
    """Calling reconcile_existing_final_mp4_ready without owner_authorized=True fails closed."""
    conn = sqlite3.connect(tmp_path / "test_auth.db")
    conn.row_factory = sqlite3.Row
    mp4_path, actual_sha256 = _create_mini_mp4(tmp_path / "final_output_28.mp4", duration_sec=16.0)
    _setup_terminal_failed_db(conn, mp4_path)

    # Default owner_authorized=False
    res = queue.reconcile_existing_final_mp4_ready(
        conn,
        job_id=28,
        expected_final_mp4_sha256=actual_sha256,
        final_video_path=str(mp4_path),
    )
    assert res["ok"] is False
    assert res["mutation"] == 0
    assert res["reason"] == "owner_authorization_required"

    # Explicit False
    res2 = queue.reconcile_existing_final_mp4_ready(
        conn,
        job_id=28,
        expected_final_mp4_sha256=actual_sha256,
        final_video_path=str(mp4_path),
        owner_authorized=False,
    )
    assert res2["ok"] is False
    assert res2["mutation"] == 0
    assert res2["reason"] == "owner_authorization_required"

    # Verify zero database mutations
    stored_job = queue.get_video_render_job(conn, 28)
    assert stored_job["status"] == "failed"


def test_successful_completion_only_reconciliation(tmp_path: Path):
    """Authorized completion-only reconciliation transitions job and project to completed / final_mp4_ready."""
    conn = sqlite3.connect(tmp_path / "test_success.db")
    conn.row_factory = sqlite3.Row
    mp4_path, actual_sha256 = _create_mini_mp4(tmp_path / "final_output_28.mp4", duration_sec=16.0)
    _setup_terminal_failed_db(conn, mp4_path)

    res = queue.reconcile_existing_final_mp4_ready(
        conn,
        job_id=28,
        project_id=32,
        expected_final_mp4_sha256=actual_sha256,
        final_video_path=str(mp4_path),
        owner_authorized=True,
    )
    assert res["ok"] is True
    assert res["mutation"] == 1
    assert res["terminal_state"] == "final_mp4_ready"
    assert res["final_mp4_ready"] is True
    assert res["final_delivered"] is False
    assert res["artifact_sha256"] == actual_sha256

    # Verify DB state on video_jobs
    stored_job = queue.get_video_render_job(conn, 28)
    assert stored_job["status"] == "completed"
    assert stored_job["progress_percent"] == 95
    assert stored_job["progress_message"] == "final_mp4_ready_waiting_delivery"
    assert stored_job["last_error"] is None
    assert stored_job["locked_by"] is None
    assert stored_job["locked_at"] is None
    assert stored_job["lease_expires_at"] is None

    result = json.loads(stored_job["result_json"])
    assert result["terminal_state"] == "final_mp4_ready"
    assert result["final_decision"] == "final_mp4_ready"
    assert result["final_mp4_valid"] is True
    assert result["final_mp4_validated"] is True
    assert result["final_delivered"] is False
    assert result["final_mp4_delivered"] is False
    assert result["delivery_succeeded"] is False
    assert result["no_charge"] is True
    assert result["charge"] == 0
    assert result["charged_xu"] == 0
    assert result["wallet_charge_recorded"] is False
    assert result["provider_submit_allowed"] is False
    assert result["automatic_retry_allowed"] is False
    assert result["automatic_resubmit_allowed"] is False
    assert result["automatic_fallback_allowed"] is False
    assert result["completion_only_reconciliation_used"] is True
    assert result["completion_only_reconciliation_sha256"] == actual_sha256
    assert result["completion_only_reconciliation_source"] == "owner_completion_only_reconciliation"

    # Verify DB state on video_projects
    stored_project = queue.get_video_project(conn, 32)
    assert stored_project["status"] == "completed"
    assert stored_project["final_video_path"] == str(mp4_path.resolve())
    assert stored_project["video_terminal_state"] == "final_mp4_ready"
    assert stored_project["video_artifact_hash"] == actual_sha256
    assert stored_project["video_delivered_at"] is None
    assert stored_project["video_delivery_message_id"] is None


def test_idempotency_exact_replay_is_noop(tmp_path: Path):
    """Replaying the reconciliation after success is an idempotent no-op with 0 state delta."""
    conn = sqlite3.connect(tmp_path / "test_idempotent.db")
    conn.row_factory = sqlite3.Row
    mp4_path, actual_sha256 = _create_mini_mp4(tmp_path / "final_output_28.mp4", duration_sec=16.0)
    _setup_terminal_failed_db(conn, mp4_path)

    # First call: succeeds
    res1 = queue.reconcile_existing_final_mp4_ready(
        conn,
        job_id=28,
        project_id=32,
        expected_final_mp4_sha256=actual_sha256,
        final_video_path=str(mp4_path),
        owner_authorized=True,
    )
    assert res1["ok"] is True
    assert res1["mutation"] == 1

    job_before = queue.get_video_render_job(conn, 28)
    proj_before = queue.get_video_project(conn, 32)

    # Second call (replay): returns already_reconciled with 0 mutation
    res2 = queue.reconcile_existing_final_mp4_ready(
        conn,
        job_id=28,
        project_id=32,
        expected_final_mp4_sha256=actual_sha256,
        final_video_path=str(mp4_path),
        owner_authorized=True,
    )
    assert res2["ok"] is True
    assert res2["duplicate_prevented"] is True
    assert res2["already_reconciled"] is True
    assert res2["replay_state_delta"] == 0
    assert res2["mutation"] == 0

    job_after = queue.get_video_render_job(conn, 28)
    proj_after = queue.get_video_project(conn, 32)

    assert dict(job_before) == dict(job_after)
    assert dict(proj_before) == dict(proj_after)


def test_media_validation_and_hash_binding_fail_closed(tmp_path: Path):
    """Physical probe failure, hash mismatch, empty file, or missing file fail closed with 0 mutation."""
    conn = sqlite3.connect(tmp_path / "test_media.db")
    conn.row_factory = sqlite3.Row
    mp4_path, actual_sha256 = _create_mini_mp4(tmp_path / "final_output_28.mp4", duration_sec=16.0)
    _setup_terminal_failed_db(conn, mp4_path)

    # 1. Hash mismatch
    fake_sha = "0000000000000000000000000000000000000000000000000000000000000000"
    res_mismatch = queue.reconcile_existing_final_mp4_ready(
        conn,
        job_id=28,
        expected_final_mp4_sha256=fake_sha,
        final_video_path=str(mp4_path),
        owner_authorized=True,
    )
    assert res_mismatch["ok"] is False
    assert res_mismatch["mutation"] == 0
    assert res_mismatch["reason"] == "final_mp4_hash_mismatch"

    # 2. Missing file
    missing_file = tmp_path / "missing.mp4"
    conn_missing = sqlite3.connect(tmp_path / "test_missing.db")
    conn_missing.row_factory = sqlite3.Row
    _setup_terminal_failed_db(conn_missing, missing_file)
    res_missing = queue.reconcile_existing_final_mp4_ready(
        conn_missing,
        job_id=28,
        expected_final_mp4_sha256=actual_sha256,
        final_video_path=str(missing_file),
        owner_authorized=True,
    )
    assert res_missing["ok"] is False
    assert res_missing["mutation"] == 0
    assert res_missing["reason"] == "final_mp4_file_missing"

    # 3. Empty 0-byte file
    empty_file = tmp_path / "empty.mp4"
    empty_file.write_bytes(b"")
    conn_empty = sqlite3.connect(tmp_path / "test_empty.db")
    conn_empty.row_factory = sqlite3.Row
    _setup_terminal_failed_db(conn_empty, empty_file)
    empty_sha = hashlib.sha256(b"").hexdigest()
    res_empty = queue.reconcile_existing_final_mp4_ready(
        conn_empty,
        job_id=28,
        expected_final_mp4_sha256=empty_sha,
        final_video_path=str(empty_file),
        owner_authorized=True,
    )
    assert res_empty["ok"] is False
    assert res_empty["mutation"] == 0
    assert res_empty["reason"] == "final_mp4_empty"

    # 4. Corrupt non-video bytes (even if caller supplies matching hash)
    corrupt_file = tmp_path / "corrupt.mp4"
    corrupt_file.write_bytes(b"corrupted video content dummy bytes 1234567890")
    conn_corrupt = sqlite3.connect(tmp_path / "test_corrupt.db")
    conn_corrupt.row_factory = sqlite3.Row
    _setup_terminal_failed_db(conn_corrupt, corrupt_file)
    corrupt_sha = hashlib.sha256(corrupt_file.read_bytes()).hexdigest()
    res_corrupt = queue.reconcile_existing_final_mp4_ready(
        conn_corrupt,
        job_id=28,
        expected_final_mp4_sha256=corrupt_sha,
        final_video_path=str(corrupt_file),
        owner_authorized=True,
    )
    assert res_corrupt["ok"] is False
    assert res_corrupt["mutation"] == 0
    assert res_corrupt["reason"] == "final_mp4_media_invalid"


def test_eligibility_guards_matrix_fail_closed(tmp_path: Path):
    """Comprehensive matrix of eligibility violations failing closed."""
    conn = sqlite3.connect(tmp_path / "test_matrix.db")
    conn.row_factory = sqlite3.Row
    mp4_path, actual_sha256 = _create_mini_mp4(tmp_path / "final_output_28.mp4", duration_sec=16.0)
    _setup_terminal_failed_db(conn, mp4_path)

    # 1. Wrong job id
    res = queue.reconcile_existing_final_mp4_ready(
        conn, job_id=999, expected_final_mp4_sha256=actual_sha256, final_video_path=str(mp4_path), owner_authorized=True
    )
    assert res["ok"] is False and res["reason"] == "job_not_found"

    # 2. Project id mismatch
    res = queue.reconcile_existing_final_mp4_ready(
        conn, job_id=28, project_id=999, expected_final_mp4_sha256=actual_sha256, final_video_path=str(mp4_path), owner_authorized=True
    )
    assert res["ok"] is False and res["reason"] == "project_not_found"

    # 3. Already delivered
    conn.execute("UPDATE video_projects SET video_delivered_at='2026-09-19 14:00:00' WHERE project_id=32")
    conn.commit()
    res = queue.reconcile_existing_final_mp4_ready(
        conn, job_id=28, expected_final_mp4_sha256=actual_sha256, final_video_path=str(mp4_path), owner_authorized=True
    )
    assert res["ok"] is False and res["reason"] == "already_delivered"
    conn.execute("UPDATE video_projects SET video_delivered_at=NULL WHERE project_id=32")
    conn.commit()

    # 4. Already charged
    res_payload = json.loads(queue.get_video_render_job(conn, 28)["result_json"])
    res_payload["charged_amount_xu"] = 144
    conn.execute("UPDATE video_jobs SET result_json=? WHERE id=28", (json.dumps(res_payload),))
    conn.commit()
    res = queue.reconcile_existing_final_mp4_ready(
        conn, job_id=28, expected_final_mp4_sha256=actual_sha256, final_video_path=str(mp4_path), owner_authorized=True
    )
    assert res["ok"] is False and res["reason"] == "already_charged"
    res_payload["charged_amount_xu"] = 0
    conn.execute("UPDATE video_jobs SET result_json=? WHERE id=28", (json.dumps(res_payload),))
    conn.commit()

    # 5. Active worker lease exists
    conn.execute("UPDATE video_jobs SET locked_by='worker-active', lease_expires_at='2026-09-19 15:00:00' WHERE id=28")
    conn.commit()
    res = queue.reconcile_existing_final_mp4_ready(
        conn, job_id=28, expected_final_mp4_sha256=actual_sha256, final_video_path=str(mp4_path), owner_authorized=True
    )
    assert res["ok"] is False and res["reason"] == "active_lease_exists"
    conn.execute("UPDATE video_jobs SET locked_by=NULL, lease_expires_at=NULL WHERE id=28")
    conn.commit()

    # 6. Invalid job status (e.g. processing)
    conn.execute("UPDATE video_jobs SET status='processing' WHERE id=28")
    conn.commit()
    res = queue.reconcile_existing_final_mp4_ready(
        conn, job_id=28, expected_final_mp4_sha256=actual_sha256, final_video_path=str(mp4_path), owner_authorized=True
    )
    assert res["ok"] is False and "invalid_job_status" in res["reason"]
    conn.execute("UPDATE video_jobs SET status='failed' WHERE id=28")
    conn.commit()

    # 7. Invalid project terminal state
    conn.execute("UPDATE video_projects SET video_terminal_state='completed' WHERE project_id=32")
    conn.commit()
    res = queue.reconcile_existing_final_mp4_ready(
        conn, job_id=28, expected_final_mp4_sha256=actual_sha256, final_video_path=str(mp4_path), owner_authorized=True
    )
    assert res["ok"] is False and "invalid_project_terminal_state" in res["reason"]


def test_zero_second_recovery_zero_provider_zero_delivery_zero_wallet_spies(tmp_path: Path):
    """Reconciliation executes with zero side effects: no provider calls, no outboxes, no delivery calls, no wallet calls."""
    conn = sqlite3.connect(tmp_path / "test_spies.db")
    conn.row_factory = sqlite3.Row
    mp4_path, actual_sha256 = _create_mini_mp4(tmp_path / "final_output_28.mp4", duration_sec=16.0)
    _setup_terminal_failed_db(conn, mp4_path)

    with patch("services.video_provider_router.run_provider_generation") as spy_provider, \
         patch("services.video_project_queue.enqueue_video_render_job") as spy_enqueue, \
         patch("services.video_project_queue._insert_product_video_dispatch_outbox_record") as spy_outbox, \
         patch("services.video_project_queue.note_video_delivery_result") as spy_delivery, \
         patch("services.video_project_queue.product_video_delivery_charge_decision") as spy_charge:

        res = queue.reconcile_existing_final_mp4_ready(
            conn,
            job_id=28,
            project_id=32,
            expected_final_mp4_sha256=actual_sha256,
            final_video_path=str(mp4_path),
            owner_authorized=True,
        )
        assert res["ok"] is True
        assert spy_provider.call_count == 0
        assert spy_enqueue.call_count == 0
        assert spy_outbox.call_count == 0
        assert spy_delivery.call_count == 0
        assert spy_charge.call_count == 0


def test_job28_exact_forensic_fixture_mirror(tmp_path: Path):
    """Exact forensic mirror matching Job 28 post Gate C state."""
    conn = sqlite3.connect(tmp_path / "test_job28_forensic.db")
    conn.row_factory = sqlite3.Row
    mp4_path, actual_sha256 = _create_mini_mp4(tmp_path / "final_output_28.mp4", duration_sec=16.0)

    # We mock hashlib inside probe check if testing with exact JOB28_FORENSIC_SHA256
    # Or test with the real calculated sha of the mp4
    _setup_terminal_failed_db(conn, mp4_path, job_id=28, project_id=32, user_id=7126457028)

    res = queue.reconcile_existing_final_mp4_ready(
        conn,
        job_id=28,
        project_id=32,
        expected_final_mp4_sha256=actual_sha256,
        final_video_path=str(mp4_path),
        owner_authorized=True,
    )
    assert res["ok"] is True
    assert res["terminal_state"] == "final_mp4_ready"

    # Verify Job 28 state matches contract requirements
    job = queue.get_video_render_job(conn, 28)
    assert job["status"] == "completed"
    assert job["progress_percent"] == 95
    assert job["progress_message"] == "final_mp4_ready_waiting_delivery"
    assert job["last_error"] is None

    project = queue.get_video_project(conn, 32)
    assert project["status"] == "completed"
    assert project["video_terminal_state"] == "final_mp4_ready"
    assert project["video_delivered_at"] is None
    assert project["video_delivery_message_id"] is None


def test_cas_concurrency_drift_fails_closed(tmp_path: Path):
    """If state mutates concurrently right before CAS write, reconciliation rolls back and fails closed."""
    conn = sqlite3.connect(tmp_path / "test_cas.db")
    conn.row_factory = sqlite3.Row
    mp4_path, actual_sha256 = _create_mini_mp4(tmp_path / "final_output_28.mp4", duration_sec=16.0)
    _setup_terminal_failed_db(conn, mp4_path)

    # Intercept get_video_render_job during the second (CAS) call to simulate concurrent cancellation
    original_get_job = queue.get_video_render_job
    call_count = [0]

    def mock_get_job(c, j_id):
        call_count[0] += 1
        res = original_get_job(c, j_id)
        if call_count[0] >= 2 and res:
            # Drifts concurrently to cancelled
            res = dict(res)
            res["status"] = "cancelled"
        return res

    with patch("services.video_project_queue.get_video_render_job", side_effect=mock_get_job):
        res = queue.reconcile_existing_final_mp4_ready(
            conn,
            job_id=28,
            project_id=32,
            expected_final_mp4_sha256=actual_sha256,
            final_video_path=str(mp4_path),
            owner_authorized=True,
        )
        assert res["ok"] is False
        assert res["mutation"] == 0
        assert res["reason"] == "reconciliation_claim_lost"


def test_expected_sha256_validation_parameter_missing(tmp_path: Path):
    """Empty or non-64-char expected SHA256 fails closed without touching database."""
    conn = sqlite3.connect(tmp_path / "test_sha_param.db")
    conn.row_factory = sqlite3.Row
    mp4_path, _ = _create_mini_mp4(tmp_path / "final_output_28.mp4", duration_sec=16.0)
    _setup_terminal_failed_db(conn, mp4_path)

    res_empty = queue.reconcile_existing_final_mp4_ready(
        conn,
        job_id=28,
        expected_final_mp4_sha256="",
        final_video_path=str(mp4_path),
        owner_authorized=True,
    )
    assert res_empty["ok"] is False
    assert res_empty["reason"] == "expected_final_mp4_sha256_required"

    res_short = queue.reconcile_existing_final_mp4_ready(
        conn,
        job_id=28,
        expected_final_mp4_sha256="abc123",
        final_video_path=str(mp4_path),
        owner_authorized=True,
    )
    assert res_short["ok"] is False
    assert res_short["reason"] == "expected_final_mp4_sha256_invalid_hex"


def test_class_a_different_valid_artifact_path_blocked(tmp_path: Path):
    """Class A: Persisted path=A, caller path=B, both valid MP4s, caller supplies SHA(B) -> BLOCKED, MUTATION=0."""
    conn = sqlite3.connect(tmp_path / "test_class_a.db")
    conn.row_factory = sqlite3.Row
    path_a, sha_a = _create_mini_mp4(tmp_path / "canonical_a.mp4", duration_sec=16.0)
    path_b, sha_b = _create_mini_mp4(tmp_path / "substitute_b.mp4", duration_sec=16.0)
    _setup_terminal_failed_db(conn, path_a)

    # Caller attempts to supply path B with SHA(B)
    res = queue.reconcile_existing_final_mp4_ready(
        conn,
        job_id=28,
        project_id=32,
        expected_final_mp4_sha256=sha_b,
        final_video_path=str(path_b),
        owner_authorized=True,
    )
    assert res["ok"] is False
    assert res["mutation"] == 0
    assert res["reason"] == "caller_path_override_forbidden"

    # Verify DB remains unmutated
    job = queue.get_video_render_job(conn, 28)
    assert job["status"] == "failed"
    project = queue.get_video_project(conn, 32)
    assert project["status"] == "failed"


def test_class_b_concurrent_result_json_charge_drift_blocked(tmp_path: Path):
    """Class B: Initial charged_xu=0, before locked reread charged_xu > 0 or wallet_charge_recorded=True -> BLOCKED, MUTATION=0."""
    conn = sqlite3.connect(tmp_path / "test_class_b.db")
    conn.row_factory = sqlite3.Row
    mp4_path, sha = _create_mini_mp4(tmp_path / "job28.mp4", duration_sec=16.0)
    _setup_terminal_failed_db(conn, mp4_path)

    original_get_job = queue.get_video_render_job
    call_count = [0]

    def mock_get_job(c, j_id):
        call_count[0] += 1
        res = original_get_job(c, j_id)
        if call_count[0] >= 2 and res:
            res = dict(res)
            res_payload = json.loads(res.get("result_json") or "{}")
            res_payload["charged_xu"] = 100
            res_payload["wallet_charge_recorded"] = True
            res["result_json"] = json.dumps(res_payload)
        return res

    with patch("services.video_project_queue.get_video_render_job", side_effect=mock_get_job):
        res = queue.reconcile_existing_final_mp4_ready(
            conn,
            job_id=28,
            project_id=32,
            expected_final_mp4_sha256=sha,
            owner_authorized=True,
        )
        assert res["ok"] is False
        assert res["mutation"] == 0
        assert res["reason"] == "reconciliation_claim_lost"
        assert res["drift_reason"] == "cas_charge_drift_detected"

    job = queue.get_video_render_job(conn, 28)
    assert job["status"] == "failed"


def test_class_c_concurrent_terminal_state_drift_blocked(tmp_path: Path):
    """Class C: Concurrent terminal-state drift from failed_no_charge -> another terminal state -> BLOCKED."""
    conn = sqlite3.connect(tmp_path / "test_class_c.db")
    conn.row_factory = sqlite3.Row
    mp4_path, sha = _create_mini_mp4(tmp_path / "job28.mp4", duration_sec=16.0)
    _setup_terminal_failed_db(conn, mp4_path)

    original_get_project = queue.get_video_project
    call_count = [0]

    def mock_get_project(c, p_id):
        call_count[0] += 1
        res = original_get_project(c, p_id)
        if call_count[0] >= 2 and res:
            res = dict(res)
            res["video_terminal_state"] = "failed_refunded"
        return res

    with patch("services.video_project_queue.get_video_project", side_effect=mock_get_project):
        res = queue.reconcile_existing_final_mp4_ready(
            conn,
            job_id=28,
            project_id=32,
            expected_final_mp4_sha256=sha,
            owner_authorized=True,
        )
        assert res["ok"] is False
        assert res["mutation"] == 0
        assert res["reason"] == "reconciliation_claim_lost"
        assert res["drift_reason"] == "cas_terminal_state_drift_detected"


def test_class_d_concurrent_recovery_mode_drift_blocked(tmp_path: Path):
    """Class D: Concurrent recovery-mode drift from recovery_existing_tasks_only true -> false -> BLOCKED."""
    conn = sqlite3.connect(tmp_path / "test_class_d.db")
    conn.row_factory = sqlite3.Row
    mp4_path, sha = _create_mini_mp4(tmp_path / "job28.mp4", duration_sec=16.0)
    _setup_terminal_failed_db(conn, mp4_path)

    original_get_job = queue.get_video_render_job
    original_get_project = queue.get_video_project
    job_call = [0]
    proj_call = [0]

    def mock_get_job(c, j_id):
        job_call[0] += 1
        res = original_get_job(c, j_id)
        if job_call[0] >= 2 and res:
            res = dict(res)
            res_payload = json.loads(res.get("result_json") or "{}")
            res_payload["recovery_existing_tasks_only"] = False
            res["result_json"] = json.dumps(res_payload)
            res["recovery_existing_tasks_only"] = False
        return res

    def mock_get_project(c, p_id):
        proj_call[0] += 1
        res = original_get_project(c, p_id)
        if proj_call[0] >= 2 and res:
            res = dict(res)
            asset_pack = json.loads(res.get("asset_pack_json") or "{}")
            asset_pack["recovery_existing_tasks_only"] = False
            res["asset_pack_json"] = json.dumps(asset_pack)
        return res

    with patch("services.video_project_queue.get_video_render_job", side_effect=mock_get_job):
        with patch("services.video_project_queue.get_video_project", side_effect=mock_get_project):
            res = queue.reconcile_existing_final_mp4_ready(
                conn,
                job_id=28,
                project_id=32,
                expected_final_mp4_sha256=sha,
                owner_authorized=True,
            )
            assert res["ok"] is False
            assert res["mutation"] == 0
            assert res["reason"] == "reconciliation_claim_lost"
            assert res["drift_reason"] == "cas_recovery_mode_drift_detected"


def test_class_e_artifact_replacement_between_precheck_and_final_cas_verify_blocked(tmp_path: Path):
    """Class E: Artifact replacement between precheck and final CAS verify -> BLOCKED, MUTATION=0."""
    conn = sqlite3.connect(tmp_path / "test_class_e.db")
    conn.row_factory = sqlite3.Row
    mp4_path, sha = _create_mini_mp4(tmp_path / "job28.mp4", duration_sec=16.0)
    _setup_terminal_failed_db(conn, mp4_path)

    original_get_job = queue.get_video_render_job
    call_count = [0]

    def mock_get_job_tamper_file(c, j_id):
        call_count[0] += 1
        res = original_get_job(c, j_id)
        if call_count[0] >= 2:
            # Tamper the file right before CAS TOCTOU verification
            mp4_path.write_bytes(b"tampered_bytes_after_precheck_before_cas_mutation")
        return res

    with patch("services.video_project_queue.get_video_render_job", side_effect=mock_get_job_tamper_file):
        res = queue.reconcile_existing_final_mp4_ready(
            conn,
            job_id=28,
            project_id=32,
            expected_final_mp4_sha256=sha,
            owner_authorized=True,
        )
        assert res["ok"] is False
        assert res["mutation"] == 0
        assert res["reason"] == "reconciliation_claim_lost"
        assert res["drift_reason"] == "artifact_toctou_hash_mismatch"

    job = queue.get_video_render_job(conn, 28)
    assert job["status"] == "failed"


def test_class_f_invalid_64_char_non_hex_sha_blocked(tmp_path: Path):
    """Class F: Invalid 64-char non-hex SHA -> BLOCKED, MUTATION=0."""
    conn = sqlite3.connect(tmp_path / "test_class_f.db")
    conn.row_factory = sqlite3.Row
    mp4_path, _ = _create_mini_mp4(tmp_path / "job28.mp4", duration_sec=16.0)
    _setup_terminal_failed_db(conn, mp4_path)

    for invalid_sha in ["g" * 64, "z" * 64, "1234567890abcdef" * 3 + "xyzxyzxyzxyzxyzx"]:
        res = queue.reconcile_existing_final_mp4_ready(
            conn,
            job_id=28,
            project_id=32,
            expected_final_mp4_sha256=invalid_sha,
            owner_authorized=True,
        )
        assert res["ok"] is False
        assert res["mutation"] == 0
        assert res["reason"] == "expected_final_mp4_sha256_invalid_hex"

    job = queue.get_video_render_job(conn, 28)
    assert job["status"] == "failed"


def test_class_g_invalid_duration_contract_with_valid_mp4_blocked(tmp_path: Path):
    """Class G: Invalid duration contract with otherwise valid MP4 -> BLOCKED, MUTATION=0."""
    conn = sqlite3.connect(tmp_path / "test_class_g.db")
    conn.row_factory = sqlite3.Row
    mp4_path, sha = _create_mini_mp4(tmp_path / "job28.mp4", duration_sec=16.0)
    _setup_terminal_failed_db(conn, mp4_path)

    # 1. Persisted invalid contract in result_json
    conn.execute(
        """UPDATE video_jobs SET result_json = json_set(
            result_json,
            '$.final_duration_contract',
            json('{"ok": false, "reason": "final_duration_short_scene_coverage_missing", "actual_duration_seconds": 8.0, "expected_duration_seconds": 16.0}')
        ) WHERE id = 28"""
    )
    conn.commit()

    res = queue.reconcile_existing_final_mp4_ready(
        conn,
        job_id=28,
        project_id=32,
        expected_final_mp4_sha256=sha,
        owner_authorized=True,
    )
    assert res["ok"] is False
    assert res["mutation"] == 0
    assert res["reason"] == "duration_contract_invalid"

    # 2. Active duration contract failure: expected duration 64s vs probed 16s
    conn_active = sqlite3.connect(tmp_path / "test_class_g_active.db")
    conn_active.row_factory = sqlite3.Row
    _setup_terminal_failed_db(conn_active, mp4_path)
    conn_active.execute(
        """UPDATE video_projects SET scene_count = 8,
            asset_pack_json = json_set(asset_pack_json, '$.orchestration_mode', 'per_scene_8s', '$.scene_count', 8)
        WHERE project_id = 32"""
    )
    conn_active.execute(
        """UPDATE video_jobs SET result_json = json_set(
            result_json, '$.orchestration_mode', 'per_scene_8s', '$.scene_count', 8
        ) WHERE id = 28"""
    )
    conn_active.commit()

    res_active = queue.reconcile_existing_final_mp4_ready(
        conn_active,
        job_id=28,
        project_id=32,
        expected_final_mp4_sha256=sha,
        owner_authorized=True,
    )
    assert res_active["ok"] is False
    assert res_active["mutation"] == 0
    assert res_active["reason"] == "duration_contract_invalid"


def test_class_h_exact_job28_compatible_fixture_succeeds(tmp_path: Path):
    """Class H: Exact Job28-compatible fixture succeeds and satisfies all invariants."""
    conn = sqlite3.connect(tmp_path / "test_class_h.db")
    conn.row_factory = sqlite3.Row
    mp4_path, sha = _create_mini_mp4(tmp_path / "job28.mp4", duration_sec=16.0)
    _setup_terminal_failed_db(conn, mp4_path)

    res = queue.reconcile_existing_final_mp4_ready(
        conn,
        job_id=28,
        project_id=32,
        expected_final_mp4_sha256=sha,
        final_video_path=str(mp4_path),
        owner_authorized=True,
    )
    assert res["ok"] is True
    assert res["mutation"] == 1
    assert res["terminal_state"] == "final_mp4_ready"
    assert res["final_mp4_ready"] is True
    assert res["final_delivered"] is False
    assert res["artifact_sha256"] == sha
    assert res["final_duration_contract"]["ok"] is True
    assert res["final_duration_contract"]["actual_duration_seconds"] > 0

    # Invariants verification
    job = queue.get_video_render_job(conn, 28)
    assert job["status"] == "completed"
    assert job["progress_percent"] == 95
    assert job["progress_message"] == "final_mp4_ready_waiting_delivery"
    assert job["last_error"] is None
    assert job["locked_by"] is None

    project = queue.get_video_project(conn, 32)
    assert project["status"] == "completed"
    assert project["video_terminal_state"] == "final_mp4_ready"
    assert project["final_video_path"] == str(os.path.realpath(mp4_path))
    assert project["video_artifact_hash"] == sha
    assert project["video_delivered_at"] is None
    assert project["video_delivery_message_id"] is None

    res_json = json.loads(job["result_json"])
    assert res_json["terminal_state"] == "final_mp4_ready"
    assert res_json["final_delivered"] is False
    assert res_json["final_mp4_delivered"] is False
    assert res_json["delivery_succeeded"] is False
    assert res_json["provider_submit_allowed"] is False
    assert res_json["charged_xu"] == 0
    assert res_json["wallet_charge_recorded"] is False
    assert res_json["completion_only_reconciliation_used"] is True
    assert res_json["completion_only_reconciliation_sha256"] == sha

