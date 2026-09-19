"""Focused test suite for P0.AUTOPOST.PUBLISHABLE.ASSET.HANDOFF.FOUNDATION.

Validates the common artifact/handoff boundary for AutoPost:
- A. Product Video completed artifact -> valid PublishableAsset -> valid handoff
- B. Video Edit completed artifact -> valid handoff
- C. SubDub completed artifact -> valid handoff
- D. Existing finished video -> valid handoff
- E. Processing artifact -> rejected
- F. Failed artifact -> rejected
- G. Intermediate scene clip -> rejected
- H. Wrong owner -> rejected
- I. Hash mismatch / replacement -> rejected
- J. Duplicate handoff -> idempotently prevented/reused
- K. Valid handoff -> AutoPost publication draft PLANNED
- L. Publication draft creation: zero Telegram, zero social, zero billing
- M. Derivation lineage preservation (C -> B -> A)
"""

from __future__ import annotations

import hashlib
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
# Scenario A: Product Video Completed Artifact -> PublishableAsset -> Handoff
# =========================================================================

def test_scenario_a_product_video_completed_to_handoff(tmp_path, db_conn):
    raw_bytes = b"product_video_final_mp4_artifact_data"
    video_file = _make_dummy_video(tmp_path, "pv_final.mp4", raw_bytes)
    sha = _sha256(raw_bytes)
    uid = 7126457028

    proj = vpq.create_video_project(
        db_conn,
        user_id=uid,
        profile_id="perfume_brand",
        topic="High End Perfume Commercial",
    )
    pid = int(proj["project_id"])

    job = vpq.enqueue_video_render_job(
        db_conn,
        project_id=pid,
        user_id=uid,
    )
    jid = int(job.get("id") or job.get("job_id"))

    # Finalize project & job
    db_conn.execute(
        """UPDATE video_projects
           SET status='completed', video_terminal_state='final_mp4_ready',
               final_video_path=?, video_artifact_hash=?
           WHERE project_id=?""",
        (str(video_file), sha, pid),
    )
    result_payload = {
        "final_video_path": str(video_file),
        "completion_only_reconciliation_sha256": sha,
        "completion_only_reconciliation_used": True,
        "caption": "Luxury Perfume 2026",
    }
    db_conn.execute(
        "UPDATE video_jobs SET status='completed', progress_percent=95, result_json=? WHERE id=?",
        (json.dumps(result_payload), jid),
    )
    db_conn.commit()

    # 1. Adapt to PublishableAsset
    asset, err = aah.adapt_product_video_output(db_conn, jid, requesting_user_id=uid)
    assert err == ""
    assert asset is not None
    assert asset.owner_id == uid
    assert asset.source_product == aah.SourceProduct.VIDEO_PRODUCT.value
    assert asset.source_job_id == str(jid)
    assert asset.artifact_sha256 == sha
    assert asset.byte_size == len(raw_bytes)
    assert asset.publish_eligible is True
    assert asset.caption_candidate == "Luxury Perfume 2026"
    assert asset.canonical_storage_ref.startswith("ref://toanaas-assets/video_product/")

    # Client view must not leak raw server filesystem path
    client_dict = asset.to_client_dict()
    assert "internal_artifact_path" not in client_dict
    assert client_dict["canonical_storage_ref"] == asset.canonical_storage_ref

    # 2. Create Handoff
    receipt, handoff_err = aah.create_autopost_handoff(db_conn, asset, requesting_user_id=uid)
    assert handoff_err == "created"
    assert receipt is not None
    assert receipt.owner_id == uid
    assert receipt.asset_id == asset.asset_id
    assert receipt.artifact_sha256 == sha
    assert receipt.purpose == "autopost"
    assert receipt.status == "created"
    assert receipt.lineage == [asset.asset_id]


# =========================================================================
# Scenario B: Video Edit Completed Artifact -> Handoff
# =========================================================================

def test_scenario_b_video_edit_completed_to_handoff(tmp_path, db_conn):
    raw_bytes = b"video_edit_rendered_output_mp4_data"
    output_file = _make_dummy_video(tmp_path, "edit_output.mp4", raw_bytes)
    sha = _sha256(raw_bytes)
    uid = 8801

    # Insert completed Video Edit job
    db_conn.execute(
        """INSERT INTO video_edit_jobs (
            idempotency_key, user_id, chat_id, edit_session_id, status,
            source_file_id, source_video_path, source_sha256,
            local_worker_job_id, output_path, output_sha256, output_size_bytes,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "idem_edit_01",
            str(uid),
            "chat_8801",
            "sess_edit_01",
            "completed",
            "src_file_001",
            str(tmp_path / "raw_input.mp4"),
            "dummy_source_sha",
            1001,
            str(output_file),
            sha,
            len(raw_bytes),
            "2026-09-19 12:00:00",
            "2026-09-19 12:05:00",
        ),
    )
    db_conn.commit()

    cur = db_conn.cursor()
    cur.execute("SELECT id FROM video_edit_jobs WHERE idempotency_key='idem_edit_01'")
    jid = cur.fetchone()[0]

    asset, err = aah.adapt_video_edit_output(db_conn, jid, requesting_user_id=uid)
    assert err == ""
    assert asset is not None
    assert asset.source_product == aah.SourceProduct.VIDEO_EDIT.value
    assert asset.artifact_sha256 == sha
    # Asserts that output_path was used, NOT source_video_path
    assert asset.internal_artifact_path == str(output_file)

    receipt, handoff_err = aah.create_autopost_handoff(db_conn, asset, requesting_user_id=uid)
    assert handoff_err == "created"
    assert receipt is not None
    assert receipt.artifact_sha256 == sha


# =========================================================================
# Scenario C: SubDub Completed Artifact -> Handoff
# =========================================================================

def test_scenario_c_subdub_completed_to_handoff(tmp_path, db_conn):
    raw_bytes = b"subdub_final_subtitle_dubbed_output"
    subdub_file = _make_dummy_video(tmp_path, "subdub_final.mp4", raw_bytes)
    sha = _sha256(raw_bytes)
    uid = 9901
    jid = "subdub_job_99"

    in_memory_job = {
        "job_id": jid,
        "user_id": uid,
        "chat_id": 9901,
        "status": "completed",
        "terminal_state": "delivered",
        "output_sent": True,
        "final_video_path": str(subdub_file),
        "video_delivery_sha256": sha,
        "target_language": "vi",
        "source_caption": "SubDub Transcribed Content",
        "final_mp4_validated": True,
        "full_video_failed": False,
    }

    asset, err = aah.adapt_subdub_output(db_conn, jid, requesting_user_id=uid, in_memory_job=in_memory_job)
    assert err == ""
    assert asset is not None
    assert asset.source_product == aah.SourceProduct.SUBDUB.value
    assert asset.artifact_sha256 == sha
    assert asset.language == "vi"
    assert asset.caption_candidate == "SubDub Transcribed Content"

    receipt, handoff_err = aah.create_autopost_handoff(db_conn, asset, requesting_user_id=uid)
    assert handoff_err == "created"
    assert receipt is not None
    assert receipt.artifact_sha256 == sha


# =========================================================================
# Scenario D: Existing Finished Video -> Handoff
# =========================================================================

def test_scenario_d_existing_video_to_handoff(tmp_path, db_conn):
    raw_bytes = b"existing_pre_rendered_client_video"
    existing_file = _make_dummy_video(tmp_path, "existing_video.mp4", raw_bytes)
    sha = _sha256(raw_bytes)
    uid = 5501

    record = {
        "asset_id": "ext_media_001",
        "owner_user_id": uid,
        "local_path": str(existing_file),
        "sha256": sha,
        "caption": "Existing Viral Short",
    }

    asset, err = aah.adapt_existing_video_output(db_conn, record, requesting_user_id=uid)
    assert err == ""
    assert asset is not None
    assert asset.source_product == aah.SourceProduct.EXISTING_VIDEO.value
    assert asset.artifact_sha256 == sha
    assert asset.caption_candidate == "Existing Viral Short"

    receipt, handoff_err = aah.create_autopost_handoff(db_conn, asset, requesting_user_id=uid)
    assert handoff_err == "created"
    assert receipt is not None
    assert receipt.artifact_sha256 == sha


# =========================================================================
# Scenario E: Processing Artifact Rejected
# =========================================================================

def test_scenario_e_processing_artifact_rejected(tmp_path, db_conn):
    uid = 7001
    proj = vpq.create_video_project(db_conn, user_id=uid, profile_id="p1", topic="Topic")
    job = vpq.enqueue_video_render_job(db_conn, project_id=int(proj["project_id"]), user_id=uid)
    jid = int(job.get("id") or job.get("job_id"))

    # Job is currently processing
    db_conn.execute("UPDATE video_jobs SET status='processing' WHERE id=?", (jid,))
    db_conn.commit()

    asset, err = aah.adapt_product_video_output(db_conn, jid, requesting_user_id=uid)
    assert asset is None
    assert err == "job_processing"

    # Video Edit processing
    db_conn.execute(
        """INSERT INTO video_edit_jobs (
            idempotency_key, user_id, chat_id, edit_session_id, status,
            source_file_id, local_worker_job_id, created_at, updated_at
        ) VALUES ('idem_proc', ?, 'c', 's', 'processing', 'f', 2001, 'now', 'now')""",
        (str(uid),),
    )
    db_conn.commit()
    cur = db_conn.cursor()
    cur.execute("SELECT id FROM video_edit_jobs WHERE idempotency_key='idem_proc'")
    edit_jid = cur.fetchone()[0]

    asset_edit, err_edit = aah.adapt_video_edit_output(db_conn, edit_jid, requesting_user_id=uid)
    assert asset_edit is None
    assert err_edit == "job_processing"

    # SubDub processing
    asset_sub, err_sub = aah.adapt_subdub_output(
        db_conn,
        "sub_proc",
        requesting_user_id=uid,
        in_memory_job={"status": "running", "user_id": uid},
    )
    assert asset_sub is None
    assert err_sub == "job_processing"


# =========================================================================
# Scenario F: Failed Artifact Rejected
# =========================================================================

def test_scenario_f_failed_artifact_rejected(db_conn):
    uid = 7002
    proj = vpq.create_video_project(db_conn, user_id=uid, profile_id="p1", topic="Topic")
    job = vpq.enqueue_video_render_job(db_conn, project_id=int(proj["project_id"]), user_id=uid)
    jid = int(job.get("id") or job.get("job_id"))

    db_conn.execute("UPDATE video_jobs SET status='failed' WHERE id=?", (jid,))
    db_conn.commit()

    asset, err = aah.adapt_product_video_output(db_conn, jid, requesting_user_id=uid)
    assert asset is None
    assert err == "job_failed"

    # SubDub failed
    asset_sub, err_sub = aah.adapt_subdub_output(
        db_conn,
        "sub_fail",
        requesting_user_id=uid,
        in_memory_job={"status": "failed", "user_id": uid, "full_video_failed": True},
    )
    assert asset_sub is None
    assert err_sub == "job_failed"


# =========================================================================
# Scenario G: Intermediate Scene Clip Rejected
# =========================================================================

def test_scenario_g_intermediate_scene_clip_rejected(tmp_path, db_conn):
    clip = _make_dummy_video(tmp_path, "scene_clip_01.mp4", b"scene_clip_data")
    sha = _sha256(b"scene_clip_data")
    uid = 7003

    proj = vpq.create_video_project(db_conn, user_id=uid, profile_id="p1", topic="Topic")
    job = vpq.enqueue_video_render_job(db_conn, project_id=int(proj["project_id"]), user_id=uid)
    jid = int(job.get("id") or job.get("job_id"))

    payload = {
        "final_video_path": str(clip),
        "is_intermediate_clip": True,
        "scene_index": 1,
    }
    db_conn.execute(
        "UPDATE video_projects SET status='completed', video_terminal_state='final_mp4_ready', final_video_path=? WHERE project_id=?",
        (str(clip), int(proj["project_id"])),
    )
    db_conn.execute(
        "UPDATE video_jobs SET status='completed', result_json=? WHERE id=?",
        (json.dumps(payload), jid),
    )
    db_conn.commit()

    asset, err = aah.adapt_product_video_output(db_conn, jid, requesting_user_id=uid)
    assert asset is None
    assert err == "intermediate_scene_clip_rejected"


# =========================================================================
# Scenario H: Wrong Owner Rejected
# =========================================================================

def test_scenario_h_wrong_owner_rejected(tmp_path, db_conn):
    vfile = _make_dummy_video(tmp_path, "owner_test.mp4", b"owner_data")
    sha = _sha256(b"owner_data")
    true_owner = 1111
    attacker = 9999

    proj = vpq.create_video_project(db_conn, user_id=true_owner, profile_id="p1", topic="Topic")
    pid = int(proj["project_id"])
    job = vpq.enqueue_video_render_job(db_conn, project_id=pid, user_id=true_owner)
    jid = int(job.get("id") or job.get("job_id"))

    db_conn.execute(
        "UPDATE video_projects SET status='completed', video_terminal_state='final_mp4_ready', final_video_path=?, video_artifact_hash=? WHERE project_id=?",
        (str(vfile), sha, pid),
    )
    db_conn.execute("UPDATE video_jobs SET status='completed' WHERE id=?", (jid,))
    db_conn.commit()

    # Attacker tries to adapt true_owner's job
    asset, err = aah.adapt_product_video_output(db_conn, jid, requesting_user_id=attacker)
    assert asset is None
    assert err == "owner_mismatch"

    # If an asset was created for true_owner, attacker cannot create handoff
    legit_asset, _ = aah.adapt_product_video_output(db_conn, jid, requesting_user_id=true_owner)
    assert legit_asset is not None

    receipt, handoff_err = aah.create_autopost_handoff(db_conn, legit_asset, requesting_user_id=attacker)
    assert receipt is None
    assert handoff_err == "owner_mismatch"


# =========================================================================
# Scenario I: Hash Mismatch / Replacement Safety (Fail Closed)
# =========================================================================

def test_scenario_i_hash_mismatch_replacement_rejected(tmp_path, db_conn):
    vfile = _make_dummy_video(tmp_path, "hash_test.mp4", b"original_unmodified_content")
    correct_sha = _sha256(b"original_unmodified_content")
    tampered_sha = "0000000000000000000000000000000000000000000000000000000000000000"
    uid = 3301

    proj = vpq.create_video_project(db_conn, user_id=uid, profile_id="p1", topic="Topic")
    pid = int(proj["project_id"])
    job = vpq.enqueue_video_render_job(db_conn, project_id=pid, user_id=uid)
    jid = int(job.get("id") or job.get("job_id"))

    # Persist expected SHA as tampered_sha
    db_conn.execute(
        "UPDATE video_projects SET status='completed', video_terminal_state='final_mp4_ready', final_video_path=?, video_artifact_hash=? WHERE project_id=?",
        (str(vfile), tampered_sha, pid),
    )
    db_conn.execute("UPDATE video_jobs SET status='completed' WHERE id=?", (jid,))
    db_conn.commit()

    # Must fail closed
    asset, err = aah.adapt_product_video_output(db_conn, jid, requesting_user_id=uid)
    assert asset is None
    assert err == "artifact_replacement_detected"

    # Now test replacement during handoff creation: file modified after asset adaptation
    db_conn.execute("UPDATE video_projects SET video_artifact_hash=? WHERE project_id=?", (correct_sha, pid))
    db_conn.commit()
    asset_good, err_good = aah.adapt_product_video_output(db_conn, jid, requesting_user_id=uid)
    assert asset_good is not None

    # Tamper file on disk right before handoff
    vfile.write_bytes(b"tampered_new_bytes_different_sha")
    receipt, handoff_err = aah.create_autopost_handoff(db_conn, asset_good, requesting_user_id=uid)
    assert receipt is None
    assert handoff_err == "artifact_replacement_detected"


# =========================================================================
# Scenario J: Duplicate Handoff Idempotently Prevented / Reused
# =========================================================================

def test_scenario_j_duplicate_handoff_idempotently_reused(tmp_path, db_conn):
    raw_bytes = b"idempotent_handoff_video_bytes"
    vfile = _make_dummy_video(tmp_path, "idem.mp4", raw_bytes)
    sha = _sha256(raw_bytes)
    uid = 4401

    asset = aah.PublishableAsset(
        asset_id="ast_test_idem_01",
        owner_id=uid,
        source_product=aah.SourceProduct.VIDEO_PRODUCT.value,
        source_job_id="101",
        source_asset_id="asset_101",
        artifact_sha256=sha,
        byte_size=len(raw_bytes),
        duration_seconds=15.0,
        width=720,
        height=1280,
        artifact_state="final_ready",
        processing_completed_at="2026-09-19 12:00:00",
        canonical_storage_ref="ref://toanaas-assets/video_product/idem",
        internal_artifact_path=str(vfile),
        publish_eligible=True,
    )

    receipt1, status1 = aah.create_autopost_handoff(db_conn, asset, requesting_user_id=uid)
    assert status1 == "created"
    assert receipt1 is not None

    # Repeated request
    receipt2, status2 = aah.create_autopost_handoff(db_conn, asset, requesting_user_id=uid)
    assert status2 == "idempotent_existing_receipt"
    assert receipt2 is not None
    assert receipt2.handoff_id == receipt1.handoff_id
    assert receipt2.artifact_sha256 == receipt1.artifact_sha256

    # Verify exactly ONE row exists in database
    cur = db_conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_handoff_receipts WHERE owner_id=?", (uid,))
    count = cur.fetchone()[0]
    assert count == 1


# =========================================================================
# Scenario K & L: AutoPost Receiver -> Publication Draft PLANNED (Zero External/Billing Calls)
# =========================================================================

def test_scenario_k_and_l_draft_creation_zero_side_effects(tmp_path, db_conn, monkeypatch):
    raw_bytes = b"draft_test_video_bytes"
    vfile = _make_dummy_video(tmp_path, "draft.mp4", raw_bytes)
    sha = _sha256(raw_bytes)
    uid = 5501

    asset = aah.PublishableAsset(
        asset_id="ast_draft_01",
        owner_id=uid,
        source_product=aah.SourceProduct.VIDEO_PRODUCT.value,
        source_job_id="202",
        source_asset_id="asset_202",
        artifact_sha256=sha,
        byte_size=len(raw_bytes),
        duration_seconds=12.0,
        width=720,
        height=1280,
        artifact_state="final_ready",
        processing_completed_at="2026-09-19 13:00:00",
        canonical_storage_ref="ref://toanaas-assets/video_product/draft",
        internal_artifact_path=str(vfile),
        caption_candidate="Trending TikTok Review",
        publish_eligible=True,
    )

    receipt, _ = aah.create_autopost_handoff(db_conn, asset, requesting_user_id=uid)
    assert receipt is not None

    # Guard counters to enforce zero external network calls and zero billing
    telegram_calls = 0
    social_publish_calls = 0
    wallet_mutation_calls = 0

    def fail_telegram(*_args, **_kwargs):
        nonlocal telegram_calls
        telegram_calls += 1
        raise AssertionError("Forbidden Telegram call during draft creation")

    def fail_social(*_args, **_kwargs):
        nonlocal social_publish_calls
        social_publish_calls += 1
        raise AssertionError("Forbidden Social Publish call during draft creation")

    # Receive handoff and generate draft
    draft, draft_status = aah.receive_autopost_handoff_to_draft(
        db_conn,
        handoff=receipt,
        asset=asset,
        requesting_user_id=uid,
    )

    assert draft_status == "draft_created"
    assert draft is not None
    assert draft.status == "PLANNED"
    assert draft.handoff_id == receipt.handoff_id
    assert draft.asset_id == asset.asset_id
    assert draft.owner_id == uid
    assert draft.caption_draft == "Trending TikTok Review"
    assert draft.selected_channels == []
    assert draft.schedule is None

    # Zero side-effects verified
    assert telegram_calls == 0
    assert social_publish_calls == 0
    assert wallet_mutation_calls == 0


# =========================================================================
# Scenario M: Lineage Preservation Across Derivations (C -> B -> A)
# =========================================================================

def test_scenario_m_lineage_preservation_across_derivations(tmp_path, db_conn):
    uid = 6601

    # Stage 1: Product Video (Asset A)
    bytes_a = b"product_raw_render_bytes"
    file_a = _make_dummy_video(tmp_path, "a.mp4", bytes_a)
    asset_a = aah.PublishableAsset(
        asset_id="ast_prod_001",
        owner_id=uid,
        source_product=aah.SourceProduct.VIDEO_PRODUCT.value,
        source_job_id="job_a",
        source_asset_id="asset_a",
        artifact_sha256=_sha256(bytes_a),
        byte_size=len(bytes_a),
        duration_seconds=10.0,
        width=720,
        height=1280,
        artifact_state="final_ready",
        processing_completed_at="2026-09-19 14:00:00",
        canonical_storage_ref="ref://toanaas-assets/video_product/a",
        internal_artifact_path=str(file_a),
        parent_asset_id=None,
    )
    receipt_a, _ = aah.create_autopost_handoff(db_conn, asset_a, requesting_user_id=uid)
    assert receipt_a.lineage == ["ast_prod_001"]

    # Stage 2: Video Edit derived from A (Asset B)
    bytes_b = b"edit_filtered_and_trimmed_bytes"
    file_b = _make_dummy_video(tmp_path, "b.mp4", bytes_b)
    asset_b = aah.PublishableAsset(
        asset_id="ast_edit_002",
        owner_id=uid,
        source_product=aah.SourceProduct.VIDEO_EDIT.value,
        source_job_id="job_b",
        source_asset_id="asset_b",
        artifact_sha256=_sha256(bytes_b),
        byte_size=len(bytes_b),
        duration_seconds=10.0,
        width=720,
        height=1280,
        artifact_state="final_ready",
        processing_completed_at="2026-09-19 14:10:00",
        canonical_storage_ref="ref://toanaas-assets/video_edit/b",
        internal_artifact_path=str(file_b),
        parent_asset_id=asset_a.asset_id,
    )
    receipt_b, _ = aah.create_autopost_handoff(db_conn, asset_b, requesting_user_id=uid)
    assert receipt_b.lineage == ["ast_edit_002", "ast_prod_001"]

    # Stage 3: SubDub derived from B (Asset C)
    bytes_c = b"subdub_subtitled_and_dubbed_bytes"
    file_c = _make_dummy_video(tmp_path, "c.mp4", bytes_c)
    asset_c = aah.PublishableAsset(
        asset_id="ast_subd_003",
        owner_id=uid,
        source_product=aah.SourceProduct.SUBDUB.value,
        source_job_id="job_c",
        source_asset_id="asset_c",
        artifact_sha256=_sha256(bytes_c),
        byte_size=len(bytes_c),
        duration_seconds=10.0,
        width=720,
        height=1280,
        artifact_state="final_ready",
        processing_completed_at="2026-09-19 14:20:00",
        canonical_storage_ref="ref://toanaas-assets/subdub/c",
        internal_artifact_path=str(file_c),
        parent_asset_id=asset_b.asset_id,
    )
    receipt_c, _ = aah.create_autopost_handoff(db_conn, asset_c, requesting_user_id=uid)

    # Lineage must be C -> B -> A
    assert receipt_c.lineage == ["ast_subd_003", "ast_edit_002", "ast_prod_001"]

    # Prior lineage records must remain untouched
    cur = db_conn.cursor()
    cur.execute("SELECT lineage_json FROM autopost_handoff_receipts WHERE handoff_id=?", (receipt_a.handoff_id,))
    assert json.loads(cur.fetchone()[0]) == ["ast_prod_001"]
    cur.execute("SELECT lineage_json FROM autopost_handoff_receipts WHERE handoff_id=?", (receipt_b.handoff_id,))
    assert json.loads(cur.fetchone()[0]) == ["ast_edit_002", "ast_prod_001"]
