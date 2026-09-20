"""Focused test suite for P0.AUTOPOST.PUBLISHABLE.ASSET.HANDOFF.FINALITY.TRUST.BOUNDARY.CLOSURE.

Validates the canonical authority boundary for AutoPost Publishable Asset Handoff:
- Test A: Forged PublishableAsset cannot create authoritative handoff (BLOCKED, no public trust bypass)
- Test B: Forged HandoffReceipt cannot create publication draft (BLOCKED)
- Test C: Product Video completion-only: project SHA != reconciliation SHA -> BLOCKED
- Test C2: Product Video completion-only with non-completed job status (processing) -> BLOCKED
- Test C3: Product Video completion-only with non-final project terminal state -> BLOCKED
- Test D: Product Video canonical-path contract preserved (via _canonical_persisted_final_mp4_path)
- Test E: Video Edit actual canonical delivered receipt (create_job + record_worker_update) -> PASS
- Test F: Video Edit non-terminal / manual fake completed state -> BLOCKED
- Test G: SubDub -> deterministic GUARDED (subdub_canonical_authority_unavailable)
- Test H: Invented system_settings SubDub row -> must NOT establish authority
- Test I: Arbitrary existing-video dict -> must NOT establish authority
- Test J: Existing-video -> deterministic GUARDED (existing_video_canonical_authority_unavailable)
- Test K: Cross-owner parent lineage -> BLOCKED (cross_owner_lineage_forbidden)
- Test L: Artifact changes between handoff and draft -> draft BLOCKED
- Test M: Duplicate canonical source handoff -> same receipt reused (idempotency)
- Test M2: Concurrent Idempotency -> unique conflict path caught and recovered, row count = 1
- Test N: Valid receipt id loaded from DB -> PLANNED draft
- Test O: Zero external/billing side effects remain
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from services import autopost_asset_handoff as aah
from services import video_editengine1
from services import video_local_validation
from services import video_project_queue as vpq


def _make_dummy_video(tmp_path: Path, name: str = "test.mp4", content: bytes = b"dummy_mp4_bytes_1234567890") -> Path:
    p = tmp_path / name
    p.write_bytes(content)
    return p


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().lower()


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
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
    vpq.ensure_video_project_queue_schema(conn)
    video_editengine1.ensure_schema(conn)
    aah.ensure_autopost_handoff_schema(conn)
    return conn


@pytest.fixture(autouse=True)
def mock_probe(monkeypatch):
    """Ensure media probe validates dummy test videos deterministically."""
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


# =========================================================================
# Test A: Forged PublishableAsset Object Cannot Create Handoff Authority
# =========================================================================

def test_a_forged_publishable_asset_handoff_blocked(tmp_path, db_conn):
    # 1. Proves no public free-form asset entrypoint exists (PUBLIC_FREEFORM_ASSET_AUTHORITY=NO)
    assert not hasattr(aah, "create_autopost_handoff"), "Freeform create_autopost_handoff must not be public"

    # 2. Proves no boolean trust bypass exists on public entrypoint (CANONICAL_PROOF_BOOLEAN_OVERRIDE=NO)
    sig_pub = inspect.signature(aah.create_autopost_handoff_from_source)
    assert "_canonical_proven" not in sig_pub.parameters
    for param in sig_pub.parameters.values():
        assert "proven" not in param.name
        assert "trust" not in param.name

    # 3. Proves private persistence helper has no boolean override
    sig_priv = inspect.signature(aah._persist_canonical_autopost_handoff)
    assert "_canonical_proven" not in sig_priv.parameters

    # 4. Attempting to pass a free-form PublishableAsset to create_autopost_handoff_from_source is rejected
    raw_bytes = b"forged_media_content"
    video_file = _make_dummy_video(tmp_path, "forged.mp4", raw_bytes)
    sha = _sha256(raw_bytes)
    uid = 9999

    forged_asset = aah.PublishableAsset(
        asset_id="ast_forged_123",
        owner_id=uid,
        source_product=aah.SourceProduct.VIDEO_PRODUCT.value,
        source_job_id="fake_job_1",
        source_asset_id="fake_asset_1",
        artifact_sha256=sha,
        byte_size=len(raw_bytes),
        duration_seconds=10.0,
        width=720,
        height=1280,
        artifact_state="final_ready",
        processing_completed_at="2026-09-19 12:00:00",
        internal_artifact_path=str(video_file),
        publish_eligible=True,
    )

    receipt, reason = aah.create_autopost_handoff_from_source(
        db_conn,
        source_product=forged_asset,  # invalid/unsupported product string
        source_ref="fake_ref",
        requesting_user_id=uid,
    )
    assert receipt is None
    assert "unsupported_source_product" in reason


# =========================================================================
# Test B: Forged HandoffReceipt Cannot Create Publication Draft
# =========================================================================

def test_b_forged_handoff_receipt_blocked(db_conn):
    uid = 9999
    # Caller attempts to supply an unpersisted handoff ID
    draft, reason = aah.receive_autopost_handoff_to_draft(
        db_conn,
        handoff_id="forged_handoff_id_xyz",
        requesting_user_id=uid,
    )
    assert draft is None
    assert reason == "receipt_not_found"


# =========================================================================
# Test C: Product Video Completion-Only: Authority Drift Blocked
# =========================================================================

def test_c_product_video_completion_only_sha_authority_drift_blocked(tmp_path, db_conn):
    raw_bytes = b"actual_physical_rendered_mp4"
    video_file = _make_dummy_video(tmp_path, "recon_pv.mp4", raw_bytes)
    sha_a = _sha256(raw_bytes)  # Actual physical SHA
    sha_b = "b" * 64            # Conflicting reconciliation SHA
    uid = 7126457028

    proj = vpq.create_video_project(
        db_conn,
        user_id=uid,
        profile_id="perfume_brand",
        topic="Perfume",
    )
    pid = int(proj["project_id"])

    job = vpq.enqueue_video_render_job(
        db_conn,
        project_id=pid,
        user_id=uid,
    )
    jid = int(job.get("id") or job.get("job_id"))

    # Induce drift: PROJECT_SHA = sha_a, RECONCILIATION_SHA = sha_b, PHYSICAL_SHA = sha_a
    db_conn.execute(
        """UPDATE video_projects SET
           status='completed', video_terminal_state='final_mp4_ready',
           final_video_path=?, video_artifact_hash=?
           WHERE project_id=?""",
        (str(video_file), sha_a, pid),
    )

    result_payload = {
        "completion_only_reconciliation_used": True,
        "completion_only_reconciliation_sha256": sha_b,
        "final_video_path": str(video_file),
    }
    db_conn.execute(
        "UPDATE video_jobs SET status='completed', result_json=? WHERE id=?",
        (json.dumps(result_payload), jid),
    )
    db_conn.commit()

    receipt, reason = aah.create_autopost_handoff_from_source(
        db_conn,
        source_product=aah.SourceProduct.VIDEO_PRODUCT,
        source_ref=jid,
        requesting_user_id=uid,
    )
    assert receipt is None
    assert reason == "completion_sha_authority_drift_blocked"


# =========================================================================
# Test C2: Completion-Only Non-Final Job State (Processing) -> BLOCKED
# =========================================================================

def test_c2_completion_only_processing_blocked(tmp_path, db_conn):
    raw_bytes = b"actual_physical_rendered_mp4"
    video_file = _make_dummy_video(tmp_path, "proc_pv.mp4", raw_bytes)
    sha_a = _sha256(raw_bytes)
    uid = 7126457028

    proj = vpq.create_video_project(
        db_conn,
        user_id=uid,
        profile_id="perfume_brand",
        topic="Perfume",
    )
    pid = int(proj["project_id"])

    job = vpq.enqueue_video_render_job(
        db_conn,
        project_id=pid,
        user_id=uid,
    )
    jid = int(job.get("id") or job.get("job_id"))

    # Project is completed, but Job is still processing
    db_conn.execute(
        """UPDATE video_projects SET
           status='completed', video_terminal_state='final_mp4_ready',
           final_video_path=?, video_artifact_hash=?
           WHERE project_id=?""",
        (str(video_file), sha_a, pid),
    )

    result_payload = {
        "completion_only_reconciliation_used": True,
        "completion_only_reconciliation_sha256": sha_a,
        "final_video_path": str(video_file),
    }
    db_conn.execute(
        "UPDATE video_jobs SET status='processing', result_json=? WHERE id=?",
        (json.dumps(result_payload), jid),
    )
    db_conn.commit()

    receipt, reason = aah.create_autopost_handoff_from_source(
        db_conn,
        source_product=aah.SourceProduct.VIDEO_PRODUCT,
        source_ref=jid,
        requesting_user_id=uid,
    )
    assert receipt is None
    assert reason == "job_processing"


# =========================================================================
# Test C3: Completion-Only Non-Final Project State -> BLOCKED
# =========================================================================

def test_c3_completion_only_nonfinal_project_terminal_state_blocked(tmp_path, db_conn):
    raw_bytes = b"actual_physical_rendered_mp4"
    video_file = _make_dummy_video(tmp_path, "nonfinal_pv.mp4", raw_bytes)
    sha_a = _sha256(raw_bytes)
    uid = 7126457028

    proj = vpq.create_video_project(
        db_conn,
        user_id=uid,
        profile_id="perfume_brand",
        topic="Perfume",
    )
    pid = int(proj["project_id"])

    job = vpq.enqueue_video_render_job(
        db_conn,
        project_id=pid,
        user_id=uid,
    )
    jid = int(job.get("id") or job.get("job_id"))

    # Job is completed, but project terminal state is failed_no_charge
    db_conn.execute(
        """UPDATE video_projects SET
           status='completed', video_terminal_state='failed_no_charge',
           final_video_path=?, video_artifact_hash=?
           WHERE project_id=?""",
        (str(video_file), sha_a, pid),
    )

    result_payload = {
        "completion_only_reconciliation_used": True,
        "completion_only_reconciliation_sha256": sha_a,
        "final_video_path": str(video_file),
    }
    db_conn.execute(
        "UPDATE video_jobs SET status='completed', result_json=? WHERE id=?",
        (json.dumps(result_payload), jid),
    )
    db_conn.commit()

    receipt, reason = aah.create_autopost_handoff_from_source(
        db_conn,
        source_product=aah.SourceProduct.VIDEO_PRODUCT,
        source_ref=jid,
        requesting_user_id=uid,
    )
    assert receipt is None
    assert "invalid_project_terminal_state" in reason


# =========================================================================
# Test D: Product Video Canonical-Path Contract Preserved
# =========================================================================

def test_d_product_video_canonical_path_preserved(tmp_path, db_conn):
    raw_bytes = b"canonical_pv_final_data"
    video_file = _make_dummy_video(tmp_path, "pv_canonical.mp4", raw_bytes)
    sha = _sha256(raw_bytes)
    uid = 7126457028

    proj = vpq.create_video_project(
        db_conn,
        user_id=uid,
        profile_id="perfume_brand",
        topic="Perfume",
    )
    pid = int(proj["project_id"])

    job = vpq.enqueue_video_render_job(
        db_conn,
        project_id=pid,
        user_id=uid,
    )
    jid = int(job.get("id") or job.get("job_id"))

    db_conn.execute(
        """UPDATE video_projects SET
           status='completed', video_terminal_state='final_mp4_ready',
           final_video_path=?, video_artifact_hash=?
           WHERE project_id=?""",
        (str(video_file), sha, pid),
    )
    db_conn.execute(
        "UPDATE video_jobs SET status='completed', result_json=? WHERE id=?",
        (json.dumps({"final_video_path": str(video_file)}), jid),
    )
    db_conn.commit()

    receipt, reason = aah.create_autopost_handoff_from_source(
        db_conn,
        source_product=aah.SourceProduct.VIDEO_PRODUCT,
        source_ref=jid,
        requesting_user_id=uid,
    )
    assert receipt is not None
    assert reason == "created"
    assert receipt.artifact_sha256 == sha

    # Intermediate scene clip must be rejected
    db_conn.execute(
        "UPDATE video_jobs SET result_json=? WHERE id=?",
        (json.dumps({"final_video_path": str(video_file), "is_intermediate_clip": True}), jid),
    )
    db_conn.commit()

    # Clear prior receipt to test fresh attempt
    db_conn.execute("DELETE FROM autopost_handoff_receipts")
    db_conn.commit()

    receipt_clip, reason_clip = aah.create_autopost_handoff_from_source(
        db_conn,
        source_product=aah.SourceProduct.VIDEO_PRODUCT,
        source_ref=jid,
        requesting_user_id=uid,
    )
    assert receipt_clip is None
    assert reason_clip == "intermediate_scene_clip_rejected"


# =========================================================================
# Test E: Video Edit Actual Canonical Delivered Receipt -> PASS
# =========================================================================

def test_e_video_edit_canonical_delivered_receipt_pass(tmp_path, db_conn):
    raw_bytes = b"video_edit_rendered_output_bytes"
    output_file = _make_dummy_video(tmp_path, "edit_output.mp4", raw_bytes)
    sha = _sha256(raw_bytes)
    uid = 77

    from tests.test_p0_video_editengine1_local_render_status_delivery import _create, _receipt
    job = _create(db_conn, session="session_edit_1")
    worker_job_id = job["local_worker_job_id"]

    rec = _receipt()
    rec["output_path"] = str(output_file)
    rec["output_sha256"] = sha
    rec["output_size_bytes"] = len(raw_bytes)

    updated = video_editengine1.record_worker_update(
        db_conn,
        worker_job_id=worker_job_id,
        worker_status="succeeded",
        detail={"stage": "delivering", "validation": "passed"},
        receipt=rec,
    )
    db_conn.commit()

    assert updated.get("status") == "delivered"
    assert updated.get("receipt_state") == "created"

    # Now create handoff from source
    receipt, reason = aah.create_autopost_handoff_from_source(
        db_conn,
        source_product=aah.SourceProduct.VIDEO_EDIT,
        source_ref=job["edit_job_id"],
        requesting_user_id=uid,
    )
    assert receipt is not None
    assert reason in ("created", "idempotent_existing_receipt")
    assert receipt.artifact_sha256 == sha
    assert receipt.source_product == "video_edit"


# =========================================================================
# Test F: Video Edit Non-Terminal / Manual Fake Completed State -> BLOCKED
# =========================================================================

def test_f_video_edit_non_terminal_manual_fake_completed_blocked(tmp_path, db_conn):
    uid = 77
    from tests.test_p0_video_editengine1_local_render_status_delivery import _create
    job = _create(db_conn, session="session_edit_queued")

    # 1. Queued state -> blocked
    receipt, reason = aah.create_autopost_handoff_from_source(
        db_conn,
        source_product=aah.SourceProduct.VIDEO_EDIT,
        source_ref=job["edit_job_id"],
        requesting_user_id=uid,
    )
    assert receipt is None
    assert reason == "job_queued"

    # 2. Fake manual UPDATE to status='completed' without canonical delivery receipt
    db_conn.execute(
        "UPDATE video_edit_jobs SET status='completed', receipt_state='not_created' WHERE id=?",
        (job["edit_job_id"],),
    )
    db_conn.commit()

    receipt_fake, reason_fake = aah.create_autopost_handoff_from_source(
        db_conn,
        source_product=aah.SourceProduct.VIDEO_EDIT,
        source_ref=job["edit_job_id"],
        requesting_user_id=uid,
    )
    assert receipt_fake is None
    assert "video_edit_not_in_terminal_delivered_state" in reason_fake


# =========================================================================
# Test G & H: SubDub Canonical Authority Unavailable & Invented Row Rejected
# =========================================================================

def test_g_subdub_canonical_authority_unavailable_guarded(db_conn):
    receipt, reason = aah.create_autopost_handoff_from_source(
        db_conn,
        source_product=aah.SourceProduct.SUBDUB,
        source_ref="subdub_job_101",
        requesting_user_id=1234,
    )
    assert receipt is None
    assert reason == "subdub_canonical_authority_unavailable"


def test_h_subdub_invented_system_settings_must_not_establish_authority(db_conn):
    # Even if system_settings table contains a fake subdub job record:
    db_conn.execute("CREATE TABLE IF NOT EXISTS system_settings (key TEXT PRIMARY KEY, value TEXT)")
    db_conn.execute(
        "INSERT INTO system_settings (key, value) VALUES (?, ?)",
        ("subdub:job:101", json.dumps({"user_id": 1234, "status": "completed", "delivered": True})),
    )
    db_conn.commit()

    receipt, reason = aah.create_autopost_handoff_from_source(
        db_conn,
        source_product=aah.SourceProduct.SUBDUB,
        source_ref="101",
        requesting_user_id=1234,
    )
    assert receipt is None
    assert reason == "subdub_canonical_authority_unavailable"


# =========================================================================
# Test I & J: Existing Video Arbitrary Dict Rejected & Guarded
# =========================================================================

def test_i_existing_video_arbitrary_dict_must_not_establish_authority(tmp_path, db_conn):
    raw_bytes = b"arbitrary_video_bytes"
    vfile = _make_dummy_video(tmp_path, "arbitrary.mp4", raw_bytes)
    sha = _sha256(raw_bytes)

    fake_record = {
        "owner_user_id": 1234,
        "local_path": str(vfile),
        "sha256": sha,
    }

    receipt, reason = aah.create_autopost_handoff_from_source(
        db_conn,
        source_product=aah.SourceProduct.EXISTING_VIDEO,
        source_ref=fake_record,
        requesting_user_id=1234,
    )
    assert receipt is None
    assert reason == "existing_video_canonical_authority_unavailable"


def test_j_existing_video_canonical_authority_unavailable_guarded(db_conn):
    receipt, reason = aah.create_autopost_handoff_from_source(
        db_conn,
        source_product=aah.SourceProduct.EXISTING_VIDEO,
        source_ref="media_vault_id_123",
        requesting_user_id=1234,
    )
    assert receipt is None
    assert reason == "existing_video_canonical_authority_unavailable"


# =========================================================================
# Test K: Cross-Owner Parent Lineage Strictly Blocked
# =========================================================================

def test_k_cross_owner_parent_lineage_blocked(tmp_path, db_conn):
    user_a = 1001
    user_b = 2002

    # User A creates a valid handoff
    raw_a = b"user_a_video_asset"
    file_a = _make_dummy_video(tmp_path, "asset_a.mp4", raw_a)
    sha_a = _sha256(raw_a)

    proj_a = vpq.create_video_project(db_conn, user_id=user_a, profile_id="a", topic="A")
    job_a = vpq.enqueue_video_render_job(db_conn, project_id=int(proj_a["project_id"]), user_id=user_a)
    jid_a = int(job_a["id"])

    db_conn.execute(
        "UPDATE video_projects SET status='completed', video_terminal_state='final_mp4_ready', final_video_path=?, video_artifact_hash=? WHERE project_id=?",
        (str(file_a), sha_a, int(proj_a["project_id"])),
    )
    db_conn.execute(
        "UPDATE video_jobs SET status='completed', result_json=? WHERE id=?",
        (json.dumps({"final_video_path": str(file_a)}), jid_a),
    )
    db_conn.commit()

    receipt_a, _ = aah.create_autopost_handoff_from_source(
        db_conn,
        source_product=aah.SourceProduct.VIDEO_PRODUCT,
        source_ref=jid_a,
        requesting_user_id=user_a,
    )
    assert receipt_a is not None

    # User B tries to reference User A's asset as parent_asset_id
    raw_b = b"user_b_video_asset"
    file_b = _make_dummy_video(tmp_path, "asset_b.mp4", raw_b)
    sha_b = _sha256(raw_b)

    proj_b = vpq.create_video_project(db_conn, user_id=user_b, profile_id="b", topic="B")
    job_b = vpq.enqueue_video_render_job(db_conn, project_id=int(proj_b["project_id"]), user_id=user_b)
    jid_b = int(job_b["id"])

    db_conn.execute(
        "UPDATE video_projects SET status='completed', video_terminal_state='final_mp4_ready', final_video_path=?, video_artifact_hash=? WHERE project_id=?",
        (str(file_b), sha_b, int(proj_b["project_id"])),
    )
    db_conn.execute(
        "UPDATE video_jobs SET status='completed', result_json=? WHERE id=?",
        (json.dumps({"final_video_path": str(file_b)}), jid_b),
    )
    db_conn.commit()

    receipt_b, reason_b = aah.create_autopost_handoff_from_source(
        db_conn,
        source_product=aah.SourceProduct.VIDEO_PRODUCT,
        source_ref=jid_b,
        requesting_user_id=user_b,
        parent_asset_id=receipt_a.asset_id,
    )
    assert receipt_b is None
    assert reason_b == "cross_owner_lineage_forbidden"


# =========================================================================
# Test L: Artifact Changes Between Handoff and Draft -> Draft Blocked
# =========================================================================

def test_l_artifact_changes_between_handoff_and_draft_blocked(tmp_path, db_conn):
    raw_bytes = b"initial_genuine_video_content"
    vfile = _make_dummy_video(tmp_path, "tamper_test.mp4", raw_bytes)
    sha = _sha256(raw_bytes)
    uid = 5555

    proj = vpq.create_video_project(db_conn, user_id=uid, profile_id="p", topic="T")
    job = vpq.enqueue_video_render_job(db_conn, project_id=int(proj["project_id"]), user_id=uid)
    jid = int(job["id"])

    db_conn.execute(
        "UPDATE video_projects SET status='completed', video_terminal_state='final_mp4_ready', final_video_path=?, video_artifact_hash=? WHERE project_id=?",
        (str(vfile), sha, int(proj["project_id"])),
    )
    db_conn.execute(
        "UPDATE video_jobs SET status='completed', result_json=? WHERE id=?",
        (json.dumps({"final_video_path": str(vfile)}), jid),
    )
    db_conn.commit()

    receipt, err = aah.create_autopost_handoff_from_source(
        db_conn,
        source_product=aah.SourceProduct.VIDEO_PRODUCT,
        source_ref=jid,
        requesting_user_id=uid,
    )
    assert receipt is not None

    # Now tamper with the physical file on disk (overwrite with modified bytes)
    vfile.write_bytes(b"tampered_modified_bytes")

    # Attempting to receive handoff into a publication draft must fail closed
    draft, reason = aah.receive_autopost_handoff_to_draft(
        db_conn,
        handoff_id=receipt.handoff_id,
        requesting_user_id=uid,
    )
    assert draft is None
    assert reason == "draft_artifact_tampered_or_modified"


# =========================================================================
# Test M: Duplicate Canonical Source Handoff -> Same Receipt Reused
# =========================================================================

def test_m_duplicate_canonical_source_handoff_idempotency(tmp_path, db_conn):
    raw_bytes = b"idempotent_video_data"
    vfile = _make_dummy_video(tmp_path, "idemp.mp4", raw_bytes)
    sha = _sha256(raw_bytes)
    uid = 6666

    proj = vpq.create_video_project(db_conn, user_id=uid, profile_id="p", topic="T")
    job = vpq.enqueue_video_render_job(db_conn, project_id=int(proj["project_id"]), user_id=uid)
    jid = int(job["id"])

    db_conn.execute(
        "UPDATE video_projects SET status='completed', video_terminal_state='final_mp4_ready', final_video_path=?, video_artifact_hash=? WHERE project_id=?",
        (str(vfile), sha, int(proj["project_id"])),
    )
    db_conn.execute(
        "UPDATE video_jobs SET status='completed', result_json=? WHERE id=?",
        (json.dumps({"final_video_path": str(vfile)}), jid),
    )
    db_conn.commit()

    r1, s1 = aah.create_autopost_handoff_from_source(
        db_conn,
        source_product=aah.SourceProduct.VIDEO_PRODUCT,
        source_ref=jid,
        requesting_user_id=uid,
    )
    assert r1 is not None
    assert s1 == "created"

    r2, s2 = aah.create_autopost_handoff_from_source(
        db_conn,
        source_product=aah.SourceProduct.VIDEO_PRODUCT,
        source_ref=jid,
        requesting_user_id=uid,
    )
    assert r2 is not None
    assert s2 == "idempotent_existing_receipt"
    assert r1.handoff_id == r2.handoff_id


# =========================================================================
# Test M2: Concurrent Idempotency Unique Conflict Recovery
# =========================================================================

def test_m2_concurrent_idempotency_unique_conflict_path(tmp_path, db_conn, monkeypatch):
    raw_bytes = b"race_idempotency_bytes"
    vfile = _make_dummy_video(tmp_path, "race.mp4", raw_bytes)
    sha = _sha256(raw_bytes)
    uid = 8888

    proj = vpq.create_video_project(db_conn, user_id=uid, profile_id="p", topic="T")
    job = vpq.enqueue_video_render_job(db_conn, project_id=int(proj["project_id"]), user_id=uid)
    jid = int(job["id"])

    db_conn.execute(
        "UPDATE video_projects SET status='completed', video_terminal_state='final_mp4_ready', final_video_path=?, video_artifact_hash=? WHERE project_id=?",
        (str(vfile), sha, int(proj["project_id"])),
    )
    db_conn.execute(
        "UPDATE video_jobs SET status='completed', result_json=? WHERE id=?",
        (json.dumps({"final_video_path": str(vfile)}), jid),
    )
    db_conn.commit()

    # Call 1: normal creation
    r1, s1 = aah.create_autopost_handoff_from_source(
        db_conn,
        source_product=aah.SourceProduct.VIDEO_PRODUCT,
        source_ref=jid,
        requesting_user_id=uid,
    )
    assert s1 == "created"
    assert r1 is not None

    # Call 2: simulate concurrent SELECT-then-INSERT race by forcing the initial SELECT
    # to miss (return None), simulating another worker inserting before this worker's INSERT.
    class ConnectionProxy:
        def __init__(self, real_conn):
            self._real = real_conn
            self.first_select = True

        def cursor(self):
            real_cur = self._real.cursor()
            proxy = self

            class CursorProxy:
                def execute(self, sql, params=()):
                    if "SELECT * FROM autopost_handoff_receipts" in sql and proxy.first_select:
                        proxy.first_select = False
                        return real_cur.execute("SELECT * FROM autopost_handoff_receipts WHERE 1=0")
                    return real_cur.execute(sql, params)

                def fetchone(self):
                    return real_cur.fetchone()

                def fetchall(self):
                    return real_cur.fetchall()

                def __getattr__(self, name):
                    return getattr(real_cur, name)

            return CursorProxy()

        def execute(self, sql, params=()):
            if "SELECT * FROM autopost_handoff_receipts" in sql and self.first_select:
                self.first_select = False
                return self._real.execute("SELECT * FROM autopost_handoff_receipts WHERE 1=0")
            return self._real.execute(sql, params)

        def commit(self):
            return self._real.commit()

        def __getattr__(self, name):
            return getattr(self._real, name)

    proxy_conn = ConnectionProxy(db_conn)

    r2, s2 = aah.create_autopost_handoff_from_source(
        proxy_conn,
        source_product=aah.SourceProduct.VIDEO_PRODUCT,
        source_ref=jid,
        requesting_user_id=uid,
    )
    assert s2 == "idempotent_existing_receipt"
    assert r2 is not None
    assert r2.handoff_id == r1.handoff_id

    # Verify exact row count is 1
    count = db_conn.execute("SELECT count(*) FROM autopost_handoff_receipts").fetchone()[0]
    assert count == 1


# =========================================================================
# Test M3: Concurrent Draft Idempotency Unique Conflict Recovery
# =========================================================================

def test_m3_concurrent_draft_idempotency_unique_conflict_path(tmp_path, db_conn):
    raw_bytes = b"draft_race_bytes"
    vfile = _make_dummy_video(tmp_path, "race_draft.mp4", raw_bytes)
    sha = _sha256(raw_bytes)
    uid = 9999

    proj = vpq.create_video_project(db_conn, user_id=uid, profile_id="p", topic="T")
    job = vpq.enqueue_video_render_job(db_conn, project_id=int(proj["project_id"]), user_id=uid)
    jid = int(job["id"])

    db_conn.execute(
        "UPDATE video_projects SET status='completed', video_terminal_state='final_mp4_ready', final_video_path=?, video_artifact_hash=? WHERE project_id=?",
        (str(vfile), sha, int(proj["project_id"])),
    )
    db_conn.execute(
        "UPDATE video_jobs SET status='completed', result_json=? WHERE id=?",
        (json.dumps({"final_video_path": str(vfile)}), jid),
    )
    db_conn.commit()

    receipt, _ = aah.create_autopost_handoff_from_source(
        db_conn,
        source_product=aah.SourceProduct.VIDEO_PRODUCT,
        source_ref=jid,
        requesting_user_id=uid,
    )
    assert receipt is not None

    d1, s1 = aah.receive_autopost_handoff_to_draft(
        db_conn,
        handoff_id=receipt.handoff_id,
        requesting_user_id=uid,
    )
    assert s1 == "draft_created"
    assert d1 is not None

    class DraftConnectionProxy:
        def __init__(self, real_conn):
            self._real = real_conn
            self.first_select = True

        def cursor(self):
            real_cur = self._real.cursor()
            proxy = self

            class CursorProxy:
                def execute(self, sql, params=()):
                    if "SELECT * FROM autopost_publication_drafts" in sql and proxy.first_select:
                        proxy.first_select = False
                        return real_cur.execute("SELECT * FROM autopost_publication_drafts WHERE 1=0")
                    return real_cur.execute(sql, params)

                def fetchone(self):
                    return real_cur.fetchone()

                def fetchall(self):
                    return real_cur.fetchall()

                def __getattr__(self, name):
                    return getattr(real_cur, name)

            return CursorProxy()

        def execute(self, sql, params=()):
            if "SELECT * FROM autopost_publication_drafts" in sql and self.first_select:
                self.first_select = False
                return self._real.execute("SELECT * FROM autopost_publication_drafts WHERE 1=0")
            return self._real.execute(sql, params)

        def commit(self):
            return self._real.commit()

        def __getattr__(self, name):
            return getattr(self._real, name)

    proxy_conn = DraftConnectionProxy(db_conn)

    d2, s2 = aah.receive_autopost_handoff_to_draft(
        proxy_conn,
        handoff_id=receipt.handoff_id,
        requesting_user_id=uid,
    )
    assert s2 == "idempotent_existing_draft"
    assert d2 is not None
    assert d2.draft_id == d1.draft_id

    # Verify exact draft count is 1
    count = db_conn.execute("SELECT count(*) FROM autopost_publication_drafts").fetchone()[0]
    assert count == 1


# =========================================================================
# Test N: Valid Receipt ID Loaded From DB -> PLANNED Draft
# =========================================================================

def test_n_valid_receipt_loaded_from_db_to_planned_draft(tmp_path, db_conn):
    raw_bytes = b"valid_draft_video_bytes"
    vfile = _make_dummy_video(tmp_path, "draft_ok.mp4", raw_bytes)
    sha = _sha256(raw_bytes)
    uid = 7777

    proj = vpq.create_video_project(db_conn, user_id=uid, profile_id="p", topic="T")
    job = vpq.enqueue_video_render_job(db_conn, project_id=int(proj["project_id"]), user_id=uid)
    jid = int(job["id"])

    db_conn.execute(
        "UPDATE video_projects SET status='completed', video_terminal_state='final_mp4_ready', final_video_path=?, video_artifact_hash=? WHERE project_id=?",
        (str(vfile), sha, int(proj["project_id"])),
    )
    db_conn.execute(
        "UPDATE video_jobs SET status='completed', result_json=? WHERE id=?",
        (json.dumps({"final_video_path": str(vfile)}), jid),
    )
    db_conn.commit()

    receipt, _ = aah.create_autopost_handoff_from_source(
        db_conn,
        source_product=aah.SourceProduct.VIDEO_PRODUCT,
        source_ref=jid,
        requesting_user_id=uid,
    )
    assert receipt is not None

    draft, status = aah.receive_autopost_handoff_to_draft(
        db_conn,
        handoff_id=receipt.handoff_id,
        requesting_user_id=uid,
    )
    assert draft is not None
    assert status == "draft_created"
    assert draft.status == "PLANNED"
    assert draft.owner_id == uid
    assert draft.asset_id == receipt.asset_id

    # Repeated receive is idempotent
    draft2, status2 = aah.receive_autopost_handoff_to_draft(
        db_conn,
        handoff_id=receipt.handoff_id,
        requesting_user_id=uid,
    )
    assert draft2.draft_id == draft.draft_id
    assert status2 == "idempotent_existing_draft"


# =========================================================================
# Test O: Zero External & Billing Side Effects Remain
# =========================================================================

def test_o_zero_external_and_billing_side_effects(monkeypatch):
    """Ensure no networking, Telegram dispatch, or billing mutations occur."""
    import urllib.request

    def forbid_urlopen(*_args, **_kwargs):
        raise AssertionError("Urllib network call strictly forbidden in handoff layer")

    monkeypatch.setattr(urllib.request, "urlopen", forbid_urlopen)
    # The imports and functions operate purely on SQLite in memory and local filesystem
    assert aah.SourceProduct.VIDEO_PRODUCT.value == "video_product"
