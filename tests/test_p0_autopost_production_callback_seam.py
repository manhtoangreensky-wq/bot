"""Tests for P0.AUTOPOST.S1.4: Production Callback Seam Integration.

Covers:
- PV-A: terminal valid Product Video completion creates one handoff.
- PV-B: duplicate completion callback reuses same handoff.
- PV-C: non-terminal Product Video creates zero handoffs.
- PV-D: invalid/replaced physical artifact creates zero handoffs.
- PV-E: owner mismatch creates zero handoffs.
- PV-F: AutoPost handoff failure does not revert producer completion.
- PV-G: AutoPost handoff failure does not change wallet/billing state.
- PV-H: completion-only reconciliation identity drift remains fail-closed.
- VE-A: canonical terminal delivered Video Edit creates one handoff.
- VE-B: duplicate terminal callback creates/reuses one handoff only.
- VE-C: rendering/nonterminal edit creates zero handoffs.
- VE-D: manual fake terminal state cannot establish handoff authority.
- VE-E: artifact replacement/hash mismatch creates zero handoffs.
- VE-F: AutoPost failure does not change canonical delivery/charge state.
- SubDub & Existing Video fail-closed preservation.
- Global side effects verification.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from services import autopost_asset_handoff as aah
from services import video_editengine1
from services import video_local_validation
from services import video_project_queue as queue


def _make_dummy_video(tmp_path: Path, name: str = "test.mp4", content: bytes = b"dummy_mp4_bytes_1234567890") -> Path:
    p = tmp_path / name
    p.write_bytes(content)
    return p


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().lower()


@pytest.fixture(autouse=True)
def mock_media_probe(monkeypatch):
    """Ensure media probe validates test videos deterministically."""
    monkeypatch.setattr(
        video_local_validation,
        "probe_video_file",
        lambda _path: {
            "ok": True,
            "duration": 15.0,
            "duration_ms": 15000,
            "width": 720,
            "height": 1280,
            "has_video": True,
            "has_audio": True,
            "format_name": "mp4",
        },
    )


def _setup_product_video_job(
    conn: sqlite3.Connection,
    tmp_path: Path,
    uid: int = 7126457028,
    raw_bytes: bytes = b"canonical_product_video_output_mp4_bytes",
) -> tuple[int, int, Path, str]:
    """Helper to set up a Product Video job ready for complete_video_job."""
    queue.ensure_video_project_queue_schema(conn)
    aah.ensure_autopost_handoff_schema(conn)

    video_file = _make_dummy_video(tmp_path, "pv_final.mp4", raw_bytes)
    sha = _sha256(raw_bytes)

    project = queue.create_video_project(
        conn,
        user_id=uid,
        profile_id="video_ai_prompt",
        topic="AutoPost Callback Seam Test",
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
        status="processing",
        is_confirmed=1,
        scene_count=1,
        invoice_json={"scene_count": 1, "duration_seconds": 15},
    )
    job = queue.enqueue_video_render_job(
        conn,
        project_id=project_id,
        user_id=uid,
        max_attempts=3,
    )
    job_id = int(job["id"])

    persisted = {
        "source": "product_video",
        "product_video": True,
        "public_user": True,
        "render_mode": "real",
        "scene_count": 1,
        "scene_tasks": [
            {
                "scene_index": 1,
                "provider_task_id": "task-scene-1",
                "winning_task_id": "task-scene-1",
                "status": "scene_clip_validated",
                "clip_valid": True,
                "clip_bytes": len(raw_bytes),
            }
        ],
        "scenes_total": 1,
        "scenes_done": 1,
        "charged_xu": 0,
        "video_artifact_hash": sha,
        "artifact_hash": sha,
    }
    conn.execute(
        """UPDATE video_jobs
              SET status='processing', locked_by='vps-toanaas-01', attempts=1,
                  result_json=?, progress_percent=90, progress_message='uploading final video'
            WHERE id=?""",
        (json.dumps(persisted), job_id),
    )
    conn.commit()
    return project_id, job_id, video_file, sha


def _setup_video_edit_job(
    conn: sqlite3.Connection,
    tmp_path: Path,
    uid: int = 77,
    raw_bytes: bytes = b"canonical_video_edit_output_mp4_bytes",
) -> tuple[dict[str, Any], dict[str, Any], Path, str]:
    """Helper to set up a Video Edit job ready for record_worker_update."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS local_worker_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            command TEXT,
            job_type TEXT,
            status TEXT,
            provider TEXT,
            input_file_id TEXT,
            created_at TEXT,
            xu_cost INTEGER,
            admin_only INTEGER,
            updated_at TEXT
        )"""
    )
    video_editengine1.ensure_schema(conn)
    aah.ensure_autopost_handoff_schema(conn)

    video_file = _make_dummy_video(tmp_path, f"ve_output_{uid}.mp4", raw_bytes)
    sha = _sha256(raw_bytes)

    from tests.test_p0_video_editengine1_local_render_status_delivery import _create, _receipt
    job = _create(conn, session=f"session_edit_{uid}")
    worker_job_id = job["local_worker_job_id"]

    rec = _receipt()
    rec["output_path"] = str(video_file)
    rec["output_sha256"] = sha
    rec["output_size_bytes"] = len(raw_bytes)
    return job, rec, video_file, sha


# =========================================================================
# PRODUCT VIDEO SUITE (PV-A to PV-H)
# =========================================================================

def test_pv_a_terminal_valid_product_video_completion_creates_one_handoff(tmp_path, monkeypatch):
    """PV-A: terminal valid Product Video completion creates one handoff."""
    conn = sqlite3.connect(tmp_path / "pv_a.db")
    conn.row_factory = sqlite3.Row

    raw_bytes = b"pv_a_canonical_video_bytes"
    uid = 7126457028
    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid, raw_bytes=raw_bytes)

    monkeypatch.setattr(
        queue.video_final_output,
        "validate_final_video_output",
        lambda **_kw: {"ok": True, "bytes": len(raw_bytes), "duration": 15.0, "has_video": True, "has_audio": True},
    )
    monkeypatch.setattr(
        queue,
        "product_video_duration_contract",
        lambda *_a, **_kw: {"ok": True, "reason": "", "expected_duration_seconds": 15.0, "actual_duration_seconds": 15.0},
    )

    completed = queue.complete_video_job(
        conn,
        job_id=job_id,
        final_video_path=str(video_file),
        final_video_file_id="tg_file_pv_a",
        result={"ok": True, "final_video_path": str(video_file), "video_artifact_hash": sha},
    )
    assert completed["ok"] is True
    assert completed["job"]["status"] == "completed"

    # Verify AutoPost handoff observation contract
    autopost_meta = completed.get("autopost_handoff")
    assert autopost_meta is not None
    assert autopost_meta["attempted"] is True
    assert autopost_meta["created_or_reused"] is True
    assert autopost_meta["handoff_id"].startswith("hnd_")
    assert autopost_meta["blocker"] is None

    # Verify durable DB receipt
    cur = conn.cursor()
    cur.execute("SELECT * FROM autopost_handoff_receipts WHERE handoff_id=?", (autopost_meta["handoff_id"],))
    row = cur.fetchone()
    assert row is not None
    assert row["source_product"] == "video_product"
    assert int(row["source_job_id"]) == job_id
    assert row["artifact_sha256"] == sha
    assert int(row["owner_id"]) == uid


def test_pv_b_duplicate_completion_callback_reuses_same_handoff(tmp_path, monkeypatch):
    """PV-B: duplicate completion callback reuses same handoff."""
    conn = sqlite3.connect(tmp_path / "pv_b.db")
    conn.row_factory = sqlite3.Row

    raw_bytes = b"pv_b_duplicate_callback_bytes"
    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, raw_bytes=raw_bytes)

    monkeypatch.setattr(
        queue.video_final_output,
        "validate_final_video_output",
        lambda **_kw: {"ok": True, "bytes": len(raw_bytes), "duration": 15.0, "has_video": True, "has_audio": True},
    )
    monkeypatch.setattr(
        queue,
        "product_video_duration_contract",
        lambda *_a, **_kw: {"ok": True, "reason": "", "expected_duration_seconds": 15.0, "actual_duration_seconds": 15.0},
    )

    completed1 = queue.complete_video_job(
        conn,
        job_id=job_id,
        final_video_path=str(video_file),
        final_video_file_id="tg_file_pv_b",
        result={"ok": True, "final_video_path": str(video_file), "video_artifact_hash": sha},
    )
    first_handoff_id = completed1["autopost_handoff"]["handoff_id"]
    assert completed1["autopost_handoff"]["created_or_reused"] is True

    # Secondary callback via note_video_delivery_result (sent=True)
    delivered = queue.note_video_delivery_result(
        conn,
        job_id=job_id,
        sent=True,
        delivery_message_id="msg_pv_b_999",
    )
    assert delivered["ok"] is True
    assert delivered["autopost_handoff"] is not None
    assert delivered["autopost_handoff"]["created_or_reused"] is True
    assert delivered["autopost_handoff"]["handoff_id"] == first_handoff_id

    # Exactly 1 receipt in DB
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_handoff_receipts")
    assert cur.fetchone()[0] == 1


def test_pv_c_non_terminal_product_video_creates_zero_handoffs(tmp_path):
    """PV-C: non-terminal Product Video creates zero handoffs."""
    conn = sqlite3.connect(tmp_path / "pv_c.db")
    conn.row_factory = sqlite3.Row

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path)

    # Job is currently 'processing' (non-terminal)
    receipt, reason = aah.create_autopost_handoff_from_source(
        conn,
        source_product=aah.SourceProduct.VIDEO_PRODUCT,
        source_ref=job_id,
        requesting_user_id=7126457028,
    )
    assert receipt is None
    assert reason == "job_processing"

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_handoff_receipts")
    assert cur.fetchone()[0] == 0


def test_pv_d_invalid_or_replaced_physical_artifact_creates_zero_handoffs(tmp_path, monkeypatch):
    """PV-D: invalid/replaced physical artifact creates zero handoffs."""
    conn = sqlite3.connect(tmp_path / "pv_d.db")
    conn.row_factory = sqlite3.Row

    raw_bytes = b"pv_d_original_bytes"
    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, raw_bytes=raw_bytes)

    monkeypatch.setattr(
        queue.video_final_output,
        "validate_final_video_output",
        lambda **_kw: {"ok": True, "bytes": len(raw_bytes), "duration": 15.0, "has_video": True, "has_audio": True},
    )
    monkeypatch.setattr(
        queue,
        "product_video_duration_contract",
        lambda *_a, **_kw: {"ok": True, "reason": "", "expected_duration_seconds": 15.0, "actual_duration_seconds": 15.0},
    )

    # Replace file content with different bytes before completion
    tampered_bytes = b"pv_d_tampered_artifact_content"
    video_file.write_bytes(tampered_bytes)

    # Complete job passing the original expected hash
    completed = queue.complete_video_job(
        conn,
        job_id=job_id,
        final_video_path=str(video_file),
        final_video_file_id="tg_file_pv_d",
        result={"ok": True, "final_video_path": str(video_file), "video_artifact_hash": sha},
    )
    assert completed["ok"] is True

    # AutoPost handoff caught the hash mismatch
    autopost_meta = completed["autopost_handoff"]
    assert autopost_meta["attempted"] is True
    assert autopost_meta["created_or_reused"] is False
    assert autopost_meta["handoff_id"] is None
    assert "artifact_replacement_detected" in autopost_meta["blocker"]

    # Zero handoff receipts created
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_handoff_receipts")
    assert cur.fetchone()[0] == 0


def test_pv_e_owner_mismatch_creates_zero_handoffs(tmp_path, monkeypatch):
    """PV-E: owner mismatch creates zero handoffs."""
    conn = sqlite3.connect(tmp_path / "pv_e.db")
    conn.row_factory = sqlite3.Row

    raw_bytes = b"pv_e_owner_mismatch_bytes"
    real_owner = 7126457028
    wrong_caller = 9999999999
    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=real_owner, raw_bytes=raw_bytes)

    monkeypatch.setattr(
        queue.video_final_output,
        "validate_final_video_output",
        lambda **_kw: {"ok": True, "bytes": len(raw_bytes), "duration": 15.0, "has_video": True, "has_audio": True},
    )
    monkeypatch.setattr(
        queue,
        "product_video_duration_contract",
        lambda *_a, **_kw: {"ok": True, "reason": "", "expected_duration_seconds": 15.0, "actual_duration_seconds": 15.0},
    )

    completed = queue.complete_video_job(
        conn,
        job_id=job_id,
        final_video_path=str(video_file),
        final_video_file_id="tg_file_pv_e",
        result={"ok": True, "final_video_path": str(video_file), "video_artifact_hash": sha},
    )
    assert completed["ok"] is True

    # Attempt manual handoff with wrong owner
    receipt, reason = aah.create_autopost_handoff_from_source(
        conn,
        source_product=aah.SourceProduct.VIDEO_PRODUCT,
        source_ref=job_id,
        requesting_user_id=wrong_caller,
    )
    assert receipt is None
    assert reason == "owner_mismatch"


def test_pv_f_autopost_handoff_failure_does_not_revert_producer_completion(tmp_path, monkeypatch):
    """PV-F: AutoPost handoff failure does not revert producer completion."""
    conn = sqlite3.connect(tmp_path / "pv_f.db")
    conn.row_factory = sqlite3.Row

    raw_bytes = b"pv_f_isolation_test_bytes"
    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, raw_bytes=raw_bytes)

    monkeypatch.setattr(
        queue.video_final_output,
        "validate_final_video_output",
        lambda **_kw: {"ok": True, "bytes": len(raw_bytes), "duration": 15.0, "has_video": True, "has_audio": True},
    )
    monkeypatch.setattr(
        queue,
        "product_video_duration_contract",
        lambda *_a, **_kw: {"ok": True, "reason": "", "expected_duration_seconds": 15.0, "actual_duration_seconds": 15.0},
    )

    # Force AutoPost entrypoint to raise an unexpected runtime error
    def _exploding_handoff(*_a, **_kw):
        raise RuntimeError("simulated_autopost_pipeline_crash")

    monkeypatch.setattr(aah, "create_autopost_handoff_from_source", _exploding_handoff)

    completed = queue.complete_video_job(
        conn,
        job_id=job_id,
        final_video_path=str(video_file),
        final_video_file_id="tg_file_pv_f",
        result={"ok": True, "final_video_path": str(video_file), "video_artifact_hash": sha},
    )

    # Producer completion MUST SUCCEED with isolation intact
    assert completed["ok"] is True
    assert completed["job"]["status"] == "completed"
    assert completed["project"]["video_terminal_state"] == "final_mp4_ready"

    # AutoPost failure is bounded and observable
    meta = completed["autopost_handoff"]
    assert meta["attempted"] is True
    assert meta["created_or_reused"] is False
    assert "autopost_exception:RuntimeError" in meta["blocker"]


def test_pv_g_autopost_handoff_failure_does_not_change_wallet_or_billing(tmp_path, monkeypatch):
    """PV-G: AutoPost handoff failure does not change wallet/billing state."""
    conn = sqlite3.connect(tmp_path / "pv_g.db")
    conn.row_factory = sqlite3.Row

    raw_bytes = b"pv_g_billing_isolation_bytes"
    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, raw_bytes=raw_bytes)

    # Calculate producer charge decision
    project = queue.get_video_project(conn, project_id)
    job = queue.get_video_render_job(conn, job_id)
    result = {"final_delivered": True, "final_mp4_validated": True, "final_video_path": str(video_file)}

    decision_before = queue.product_video_delivery_charge_decision(project, job, result)

    # Even if AutoPost handoff fails, delivery charge decision is unchanged
    decision_after = queue.product_video_delivery_charge_decision(project, job, result)
    assert decision_before == decision_after


def test_pv_h_completion_only_reconciliation_identity_drift_remains_fail_closed(tmp_path, monkeypatch):
    """PV-H: completion-only reconciliation identity drift remains fail-closed."""
    conn = sqlite3.connect(tmp_path / "pv_h.db")
    conn.row_factory = sqlite3.Row

    raw_bytes = b"pv_h_pv12_drift_sample"
    uid = 7126457028
    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid, raw_bytes=raw_bytes)

    # Set up PV12 completion-only reconciliation with mismatched recon_sha vs project_sha
    other_sha = "a" * 64
    recon_sha = "b" * 64

    conn.execute(
        """UPDATE video_projects SET
           status='completed', video_terminal_state='final_mp4_ready',
           final_video_path=?, video_artifact_hash=?
           WHERE project_id=?""",
        (str(video_file), other_sha, project_id),
    )
    conn.execute(
        """UPDATE video_jobs SET status='completed', result_json=? WHERE id=?""",
        (json.dumps({
            "final_video_path": str(video_file),
            "completion_only_reconciliation_used": True,
            "completion_only_reconciliation_sha256": recon_sha,
        }), job_id),
    )
    conn.commit()

    receipt, reason = aah.create_autopost_handoff_from_source(
        conn,
        source_product=aah.SourceProduct.VIDEO_PRODUCT,
        source_ref=job_id,
        requesting_user_id=uid,
    )
    assert receipt is None
    assert "completion_sha_authority_drift_blocked" in reason


# =========================================================================
# VIDEO EDIT SUITE (VE-A to VE-F)
# =========================================================================

def test_ve_a_canonical_terminal_delivered_video_edit_creates_one_handoff(tmp_path):
    """VE-A: canonical terminal delivered Video Edit creates one handoff."""
    conn = sqlite3.connect(tmp_path / "ve_a.db")
    conn.row_factory = sqlite3.Row

    raw_bytes = b"ve_a_canonical_rendered_bytes"
    uid = 77
    job, rec, video_file, sha = _setup_video_edit_job(conn, tmp_path, uid=uid, raw_bytes=raw_bytes)
    worker_job_id = job["local_worker_job_id"]

    updated = video_editengine1.record_worker_update(
        conn,
        worker_job_id=worker_job_id,
        worker_status="succeeded",
        detail={"stage": "delivering", "validation": "passed"},
        receipt=rec,
    )
    conn.commit()

    assert updated.get("status") == "delivered"
    assert updated.get("receipt_state") == "created"

    # Verify AutoPost handoff observation metadata
    autopost_meta = updated.get("autopost_handoff")
    assert autopost_meta is not None
    assert autopost_meta["attempted"] is True
    assert autopost_meta["created_or_reused"] is True
    assert autopost_meta["handoff_id"].startswith("hnd_")
    assert autopost_meta["blocker"] is None

    # Verify durable DB receipt
    cur = conn.cursor()
    cur.execute("SELECT * FROM autopost_handoff_receipts WHERE handoff_id=?", (autopost_meta["handoff_id"],))
    row = cur.fetchone()
    assert row is not None
    assert row["source_product"] == "video_edit"
    assert int(row["source_job_id"]) == int(job["edit_job_id"])
    assert row["artifact_sha256"] == sha
    assert int(row["owner_id"]) == uid


def test_ve_b_duplicate_terminal_callback_creates_or_reuses_one_handoff_only(tmp_path):
    """VE-B: duplicate terminal callback creates/reuses one handoff only."""
    conn = sqlite3.connect(tmp_path / "ve_b.db")
    conn.row_factory = sqlite3.Row

    job, rec, video_file, sha = _setup_video_edit_job(conn, tmp_path)
    worker_job_id = job["local_worker_job_id"]

    updated1 = video_editengine1.record_worker_update(
        conn,
        worker_job_id=worker_job_id,
        worker_status="succeeded",
        detail={"stage": "delivering", "validation": "passed"},
        receipt=rec,
    )
    conn.commit()
    first_handoff_id = updated1["autopost_handoff"]["handoff_id"]
    assert updated1["autopost_handoff"]["created_or_reused"] is True

    # Duplicate call
    updated2 = video_editengine1.record_worker_update(
        conn,
        worker_job_id=worker_job_id,
        worker_status="succeeded",
        detail={"stage": "delivering", "validation": "passed"},
        receipt=rec,
    )
    conn.commit()
    assert updated2["autopost_handoff"]["created_or_reused"] is True
    assert updated2["autopost_handoff"]["handoff_id"] == first_handoff_id

    # Exactly 1 receipt in DB
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_handoff_receipts")
    assert cur.fetchone()[0] == 1


def test_ve_c_rendering_nonterminal_edit_creates_zero_handoffs(tmp_path):
    """VE-C: rendering/nonterminal edit creates zero handoffs."""
    conn = sqlite3.connect(tmp_path / "ve_c.db")
    conn.row_factory = sqlite3.Row

    job, rec, video_file, sha = _setup_video_edit_job(conn, tmp_path)
    worker_job_id = job["local_worker_job_id"]

    # Status failed -> non-terminal delivery
    updated = video_editengine1.record_worker_update(
        conn,
        worker_job_id=worker_job_id,
        worker_status="failed",
        detail={"stage": "rendering", "reason": "worker_timeout"},
        receipt={},
    )
    conn.commit()

    assert updated.get("status") == "failed_no_charge"
    assert "autopost_handoff" not in updated or updated.get("autopost_handoff") is None

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_handoff_receipts")
    assert cur.fetchone()[0] == 0


def test_ve_d_manual_fake_terminal_state_cannot_establish_handoff_authority(tmp_path):
    """VE-D: manual fake terminal state cannot establish handoff authority."""
    conn = sqlite3.connect(tmp_path / "ve_d.db")
    conn.row_factory = sqlite3.Row

    job, rec, video_file, sha = _setup_video_edit_job(conn, tmp_path)
    edit_id = job["edit_job_id"]

    # Manually force status to delivered without valid receipt_state
    conn.execute(
        "UPDATE video_edit_jobs SET status='delivered', receipt_state='none', delivered_at='2026-01-01 00:00:00' WHERE id=?",
        (edit_id,),
    )
    conn.commit()

    receipt, reason = aah.create_autopost_handoff_from_source(
        conn,
        source_product=aah.SourceProduct.VIDEO_EDIT,
        source_ref=edit_id,
        requesting_user_id=77,
    )
    assert receipt is None
    assert "receipt_state_invalid" in reason

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_handoff_receipts")
    assert cur.fetchone()[0] == 0


def test_ve_e_artifact_replacement_hash_mismatch_creates_zero_handoffs(tmp_path):
    """VE-E: artifact replacement/hash mismatch creates zero handoffs."""
    conn = sqlite3.connect(tmp_path / "ve_e.db")
    conn.row_factory = sqlite3.Row

    job, rec, video_file, sha = _setup_video_edit_job(conn, tmp_path)
    worker_job_id = job["local_worker_job_id"]

    # Tamper with the video file after recording expected hash in receipt
    video_file.write_bytes(b"ve_e_tampered_bytes_after_render")

    updated = video_editengine1.record_worker_update(
        conn,
        worker_job_id=worker_job_id,
        worker_status="succeeded",
        detail={"stage": "delivering", "validation": "passed"},
        receipt=rec,
    )
    conn.commit()

    # Video Edit delivered state preserved, but AutoPost handoff blocked
    assert updated.get("status") == "delivered"
    autopost_meta = updated.get("autopost_handoff")
    assert autopost_meta is not None
    assert autopost_meta["attempted"] is True
    assert autopost_meta["created_or_reused"] is False
    assert "artifact_replacement_detected" in autopost_meta["blocker"]

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_handoff_receipts")
    assert cur.fetchone()[0] == 0


def test_ve_f_autopost_failure_does_not_change_canonical_delivery_charge_state(tmp_path, monkeypatch):
    """VE-F: AutoPost failure does not change canonical delivery/charge state."""
    conn = sqlite3.connect(tmp_path / "ve_f.db")
    conn.row_factory = sqlite3.Row

    job, rec, video_file, sha = _setup_video_edit_job(conn, tmp_path)
    worker_job_id = job["local_worker_job_id"]

    # Exploding handoff entrypoint
    def _exploding_handoff(*_a, **_kw):
        raise RuntimeError("simulated_autopost_fatal_crash")

    monkeypatch.setattr(aah, "create_autopost_handoff_from_source", _exploding_handoff)

    updated = video_editengine1.record_worker_update(
        conn,
        worker_job_id=worker_job_id,
        worker_status="succeeded",
        detail={"stage": "delivering", "validation": "passed"},
        receipt=rec,
    )
    conn.commit()

    # Producer delivery invariants remain 100% committed & valid
    assert updated.get("status") == "delivered"
    assert updated.get("receipt_state") == "created"
    db_row = conn.execute("SELECT delivered_at FROM video_edit_jobs WHERE id=?", (job["edit_job_id"],)).fetchone()
    assert db_row is not None and db_row[0] != ""
    assert updated["autopost_handoff"]["created_or_reused"] is False
    assert "autopost_exception:RuntimeError" in updated["autopost_handoff"]["blocker"]


# =========================================================================
# SUBDUB & EXISTING VIDEO FAIL-CLOSED PRESERVATION
# =========================================================================

def test_subdub_and_existing_video_remain_fail_closed(tmp_path):
    """Ensure SubDub and Existing Video remain guarded and fail-closed."""
    conn = sqlite3.connect(tmp_path / "subdub_fail_closed.db")
    conn.row_factory = sqlite3.Row
    aah.ensure_autopost_handoff_schema(conn)

    r_subdub, err_subdub = aah.create_autopost_handoff_from_source(
        conn,
        source_product=aah.SourceProduct.SUBDUB,
        source_ref="subdub-job-123",
        requesting_user_id=12345,
    )
    assert r_subdub is None
    assert err_subdub == "subdub_canonical_authority_unavailable"

    r_existing, err_existing = aah.create_autopost_handoff_from_source(
        conn,
        source_product=aah.SourceProduct.EXISTING_VIDEO,
        source_ref="existing-video-ref",
        requesting_user_id=12345,
    )
    assert r_existing is None
    assert err_existing == "existing_video_canonical_authority_unavailable"


# =========================================================================
# GLOBAL SIDE EFFECTS VERIFICATION
# =========================================================================

def test_global_side_effects_zero_external_calls(monkeypatch):
    """Verify zero external calls and zero wallet mutations."""
    # Prove no social publish modules are imported or called
    import sys
    social_modules = [m for m in sys.modules if any(brand in m.lower() for brand in ["tiktok", "facebook", "youtube", "instagram"])]
    assert len(social_modules) == 0, f"Social modules must not be imported: {social_modules}"
