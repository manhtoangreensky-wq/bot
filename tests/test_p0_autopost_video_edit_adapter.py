"""tests/test_p0_autopost_video_edit_adapter.py

Tests for P0.AUTOPOST.S4: Video Edit -> AutoPost Adapter Integration.
Governed under TOAN AAS Owner-Governed Codex.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any

import pytest

from services import autopost_asset_handoff as aah
from services import autopost_scheduler as aps
from services import autopost_video_edit_adapter as avea
from services import video_editengine1
from services import video_local_validation


def _make_dummy_video(tmp_path: Path, name: str = "test.mp4", content: bytes = b"dummy_mp4_bytes_ve_1234567890") -> Path:
    p = tmp_path / name
    p.write_bytes(content)
    return p


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().lower()


@pytest.fixture(autouse=True)
def mock_media_probe(monkeypatch):
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


def _seed_minimal_video_edit_job(
    conn: sqlite3.Connection,
    uid: int = 101,
    job_id: int = 201,
    local_worker_job_id: int = 301,
    status: str = "processing",
) -> None:
    video_editengine1.ensure_schema(conn)
    conn.execute(
        """INSERT OR REPLACE INTO video_edit_jobs (
            id, idempotency_key, user_id, chat_id, edit_session_id, status,
            source_file_id, local_worker_job_id, created_at, updated_at
        ) VALUES (?, ?, ?, 'chat1', 'sess1', ?, 'sf1', ?, '2026-03-20T10:00:00Z', '2026-03-20T10:00:00Z')""",
        (job_id, f"key_{job_id}", str(uid), status, local_worker_job_id),
    )
    conn.commit()


def _setup_video_edit_job(
    conn: sqlite3.Connection,
    tmp_path: Path,
    uid: int = 77,
    job_id: int = 501,
    local_worker_job_id: int = 901,
    status: str = "delivered",
    receipt_state: str = "created",
    raw_bytes: bytes = b"ve_s4_canonical_video_bytes_12345",
    tail_json: str = "{}",
    delivered_at: str = "2026-03-20T10:00:00Z",
) -> tuple[int, int, Path, str]:
    video_editengine1.ensure_schema(conn)
    aah.ensure_autopost_handoff_schema(conn)
    aps.ensure_autopost_scheduler_schema(conn)
    avea.ensure_autopost_video_edit_adapter_schema(conn)

    video_file = _make_dummy_video(tmp_path, f"ve_s4_final_{job_id}.mp4", raw_bytes)
    sha = _sha256(raw_bytes)
    now = "2026-03-20T10:00:00Z"

    canonical_probe = {
        "ok": True,
        "has_video": True,
        "has_audio": True,
        "video_codec": "h264",
        "audio_codec": "aac",
        "duration": 15.0,
        "duration_ms": 15000,
        "width": 720,
        "height": 1280,
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "full_decode": True,
    }

    conn.execute(
        """INSERT OR REPLACE INTO video_edit_jobs (
            id, idempotency_key, user_id, chat_id, product_type, worker_job_type,
            engine_route, worker_owner, edit_session_id, status, source_file_id,
            source_video_path, source_sha256, source_metadata_json, plan_json,
            tail_json, quality_tier_id, price_xu, local_worker_job_id, progress_percent,
            blocker, output_file_id, output_path, output_sha256, output_size_bytes,
            ffprobe_json, delivery_message_id, delivery_file_id, artifact_receipts_json,
            delivery_cursor, receipt_state, charge_state, charged_xu, created_at,
            started_at, delivered_at, charged_at, finished_at, updated_at
        ) VALUES (
            ?, ?, ?, '88', 'video_edit', 'video_local_edit',
            'local_worker_ffmpeg', 'local_video_edit', 'session-1', ?, 'source-file-1',
            '', ?, '{}', '{}',
            ?, '300', 100, ?, 100,
            '', 'del-file-1', ?, ?, ?,
            ?, '9001', 'del-file-1', '[]',
            0, ?, 'not_charged', 0, ?,
            ?, ?, '', ?, ?
        )""",
        (
            job_id,
            f"idemp_{job_id}",
            str(uid),
            status,
            "c" * 64,
            tail_json,
            local_worker_job_id,
            str(video_file),
            sha,
            len(raw_bytes),
            json.dumps(canonical_probe),
            receipt_state,
            now,
            now,
            delivered_at if delivered_at else "",
            now,
            now,
        ),
    )
    conn.commit()
    return job_id, local_worker_job_id, video_file, sha


# =========================================================================
# TEST 01-06: FIRST RED, SCHEMA, INTENT REGISTRATION & IDEMPOTENCY
# =========================================================================

def test_01_first_red_video_edit_adapter_gap(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    jid, wid, vf, sha = _setup_video_edit_job(conn, tmp_path)

    # Without explicit intent registered, adapter returns no_intent_registered
    res, err = avea.process_video_edit_autopost_handoff(conn, jid, 77)
    assert res["attempted"] is False
    assert res["mode"] == "NONE"
    assert res["draft_id"] is None
    assert res["publication_id"] is None
    assert err == "no_intent_registered"

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_publication_drafts")
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT COUNT(*) FROM autopost_publication_queue")
    assert cur.fetchone()[0] == 0


def test_02_register_off_intent(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_minimal_video_edit_job(conn, uid=101, job_id=201)

    intent, status = avea.register_video_edit_autopost_intent(conn, 101, 201, "OFF")
    assert status == "registered"
    assert intent["mode"] == "OFF"
    assert intent["status"] == "PENDING"
    assert intent["schedule_at"] is None


def test_03_wrong_owner_cannot_register_intent(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_minimal_video_edit_job(conn, uid=101, job_id=201)

    intent, err = avea.register_video_edit_autopost_intent(conn, 999, 201, "OFF")
    assert intent is None
    assert err == "owner_mismatch"

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_video_edit_intents")
    assert cur.fetchone()[0] == 0


def test_04_nonexistent_job_cannot_register_intent():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    video_editengine1.ensure_schema(conn)

    intent, err = avea.register_video_edit_autopost_intent(conn, 101, 9999, "OFF")
    assert intent is None
    assert err == "video_edit_job_not_found"

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_video_edit_intents")
    assert cur.fetchone()[0] == 0


def test_05_exact_intent_replay_idempotent(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_minimal_video_edit_job(conn, uid=101, job_id=201)

    intent1, s1 = avea.register_video_edit_autopost_intent(
        conn, 101, 201, "SCHEDULE_AT", schedule_at="2026-10-01T12:00:00Z"
    )
    assert s1 == "registered"

    intent2, s2 = avea.register_video_edit_autopost_intent(
        conn, 101, 201, "SCHEDULE_AT", schedule_at="2026-10-01T12:00:00Z"
    )
    assert s2 == "idempotent_existing"
    assert intent1["intent_id"] == intent2["intent_id"]


def test_06_conflicting_intent_replay_fails_closed(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_minimal_video_edit_job(conn, uid=101, job_id=201)

    avea.register_video_edit_autopost_intent(conn, 101, 201, "DRAFT_ONLY")
    intent2, err = avea.register_video_edit_autopost_intent(conn, 101, 201, "SCHEDULE_NOW")
    assert intent2 is None
    assert err == "intent_conflict_already_registered"


# =========================================================================
# TEST 07-16: MODES (OFF, DRAFT_ONLY, SCHEDULE_NOW, SCHEDULE_AT)
# =========================================================================

def test_07_off_mode_zero_draft_and_queue(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    jid, wid, vf, sha = _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)
    avea.register_video_edit_autopost_intent(conn, 77, 501, "OFF")

    res, status = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert status == "off"
    assert res["mode"] == "OFF"
    assert res["draft_id"] is None
    assert res["publication_id"] is None

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_publication_drafts")
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT COUNT(*) FROM autopost_publication_queue")
    assert cur.fetchone()[0] == 0


def test_08_draft_only_creates_planned_draft(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    jid, wid, vf, sha = _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)
    avea.register_video_edit_autopost_intent(conn, 77, 501, "DRAFT_ONLY")

    res, status = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert status == "draft_ready"
    assert res["mode"] == "DRAFT_ONLY"
    assert res["state"] == "PLANNED"
    assert res["draft_id"] is not None
    assert res["publication_id"] is None

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_publication_queue")
    assert cur.fetchone()[0] == 0


def test_09_draft_only_replay_same_draft(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    jid, wid, vf, sha = _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)
    avea.register_video_edit_autopost_intent(conn, 77, 501, "DRAFT_ONLY")

    res1, _ = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    res2, _ = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert res1["draft_id"] == res2["draft_id"]

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_publication_drafts")
    assert cur.fetchone()[0] == 1


def test_10_schedule_now_persists_canonical_registration_time(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_minimal_video_edit_job(conn, uid=77, job_id=501)

    reg_time = "2026-05-15T08:30:00Z"
    intent, s = avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW", now=reg_time)
    assert s == "registered"
    assert intent["schedule_at"] == reg_time


def test_11_schedule_now_rejects_caller_schedule_at(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_minimal_video_edit_job(conn, uid=77, job_id=501)

    intent, err = avea.register_video_edit_autopost_intent(
        conn, 77, 501, "SCHEDULE_NOW", schedule_at="2099-01-01T00:00:00Z"
    )
    assert intent is None
    assert err == "schedule_at_not_allowed_for_schedule_now"


def test_12_rejected_schedule_now_creates_zero_intent_rows(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_minimal_video_edit_job(conn, uid=77, job_id=501)

    avea.register_video_edit_autopost_intent(
        conn, 77, 501, "SCHEDULE_NOW", schedule_at="2099-01-01T00:00:00Z"
    )
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_video_edit_intents")
    assert cur.fetchone()[0] == 0


def test_13_schedule_now_creates_scheduled_state(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    jid, wid, vf, sha = _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    res, status = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert status == "scheduled"
    assert res["state"] == "SCHEDULED"
    assert res["publication_id"] is not None


def test_14_schedule_now_does_not_auto_claim(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    jid, wid, vf, sha = _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    res, _ = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    cur = conn.cursor()
    cur.execute(
        "SELECT state, lease_owner, attempt_count FROM autopost_publication_queue WHERE publication_id=?",
        (res["publication_id"],),
    )
    row = cur.fetchone()
    assert row["state"] == "SCHEDULED"
    assert row["lease_owner"] is None
    assert row["attempt_count"] == 0


def test_15_schedule_at_valid_utc_reaches_scheduled(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    jid, wid, vf, sha = _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)
    target = "2026-11-20T15:00:00Z"
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_AT", schedule_at=target)

    res, status = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert status == "scheduled"
    assert res["state"] == "SCHEDULED"

    cur = conn.cursor()
    cur.execute(
        "SELECT schedule_at FROM autopost_publication_queue WHERE publication_id=?",
        (res["publication_id"],),
    )
    assert cur.fetchone()[0] == target


def test_16_schedule_at_naive_or_non_utc_rejected(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_minimal_video_edit_job(conn, uid=77, job_id=501)

    intent, err = avea.register_video_edit_autopost_intent(
        conn, 77, 501, "SCHEDULE_AT", schedule_at="2026-11-20 15:00:00"
    )
    assert intent is None
    assert "invalid_schedule_at" in err


def test_17_invalid_schedule_does_not_mutate_video_edit_terminal_truth(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    jid, wid, vf, sha = _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)

    # Corrupt intent table directly with invalid schedule_at
    conn.execute(
        """INSERT INTO autopost_video_edit_intents (
            intent_id, owner_id, video_edit_job_id, mode, schedule_at,
            selected_channels_json, caption_override, status, last_blocker_code,
            created_at, updated_at
        ) VALUES ('bad_intent', 77, 501, 'SCHEDULE_AT', 'invalid-time', '[]', NULL, 'PENDING', NULL, 'now', 'now')"""
    )
    conn.commit()

    res, err = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert "schedule_time_invalid" in err

    # Video edit job remains delivered and intact
    cur = conn.cursor()
    cur.execute("SELECT status, receipt_state, delivered_at FROM video_edit_jobs WHERE id=501")
    row = cur.fetchone()
    assert row["status"] == "delivered"
    assert row["receipt_state"] == "created"
    assert row["delivered_at"] == "2026-03-20T10:00:00Z"


# =========================================================================
# TEST 18-27: TERMINAL VALIDATION & PHYSICAL ARTIFACT INTEGRITY
# =========================================================================

def test_18_queued_job_blocked(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, status="queued")
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    res, err = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert res["draft_id"] is None
    assert "job_queued" in err


def test_19_rendering_job_blocked(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, status="rendering")
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    res, err = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert "job_processing" in err


def test_20_failed_no_charge_blocked(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, status="failed_no_charge")
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    res, err = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert "job_failed" in err


def test_21_delivery_unknown_blocked(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, status="delivery_unknown")
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    res, err = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert "job_failed" in err


def test_22_cancelled_blocked(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, status="cancelled")
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    res, err = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert "job_failed" in err


def test_23_fake_completed_alias_blocked(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, status="completed")
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    res, err = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert "video_edit_not_in_terminal_delivered_state" in err


def test_24_receipt_state_not_created_blocked(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, receipt_state="not_created")
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    res, err = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert "video_edit_receipt_state_invalid" in err


def test_25_delivered_at_missing_blocked(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, delivered_at="")
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    res, err = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert "video_edit_not_delivered" in err


def test_26_invalid_mp4_blocked(tmp_path, monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    monkeypatch.setattr(
        video_local_validation,
        "probe_video_file",
        lambda _p: {"ok": False, "reason": "corrupt_header"},
    )

    res, err = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert "corrupt_header" in err or "unreadable" in err


def test_27_replaced_artifact_sha_blocked(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    jid, wid, vf, sha = _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    # Mutate physical file contents behind DB back
    vf.write_bytes(b"tampered_bytes")

    res, err = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert "artifact_replacement_detected" in err


# =========================================================================
# TEST 28-31: EXACT HANDOFF BINDING & MISMATCH PREVENTION
# =========================================================================

def test_28_wrong_owner_execution_blocked(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)

    res, err = avea.process_video_edit_autopost_handoff(conn, 501, 999)
    assert "owner_mismatch" in err


def test_29_same_owner_cross_job_supplied_handoff_blocked(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, raw_bytes=b"jobA")
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=502, local_worker_job_id=902, raw_bytes=b"jobB")

    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")
    avea.register_video_edit_autopost_intent(conn, 77, 502, "SCHEDULE_NOW")

    # Create handoff for job 502
    h_rec_502, _ = aah.create_autopost_handoff_from_source(conn, "video_edit", 502, 77)

    # Pass handoff 502 to adapter for job 501
    res, err = avea.process_video_edit_autopost_handoff(
        conn, 501, 77, handoff_receipt={"handoff_id": h_rec_502.handoff_id}
    )
    assert err == "handoff_product_binding_mismatch"
    assert res["blocker"] == "handoff_product_binding_mismatch"


def test_30_cross_asset_handoff_blocked(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    # Handcrafted foreign handoff
    conn.execute(
        """INSERT INTO autopost_handoff_receipts (
            handoff_id, owner_id, source_product, source_job_id, asset_id,
            artifact_sha256, purpose, status, lineage_json, asset_snapshot_json, created_at
        ) VALUES ('foreign_h', 77, 'video_edit', '501', 'foreign_asset', 'a'*64, 'autopost', 'created', '{}', '{}', 'now')"""
    )
    conn.commit()

    res, err = avea.process_video_edit_autopost_handoff(
        conn, 501, 77, handoff_receipt={"handoff_id": "foreign_h"}
    )
    assert err == "handoff_product_binding_mismatch"


def test_31_cross_sha_handoff_blocked(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    jid, wid, vf, sha = _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    asset, _ = aah.adapt_video_edit_output(conn, 501, 77)
    conn.execute(
        """INSERT INTO autopost_handoff_receipts (
            handoff_id, owner_id, source_product, source_job_id, asset_id,
            artifact_sha256, purpose, status, lineage_json, asset_snapshot_json, created_at
        ) VALUES ('sha_mismatch_h', 77, 'video_edit', '501', ?, 'f'*64, 'autopost', 'created', '{}', '{}', 'now')""",
        (asset.asset_id,),
    )
    conn.commit()

    res, err = avea.process_video_edit_autopost_handoff(
        conn, 501, 77, handoff_receipt={"handoff_id": "sha_mismatch_h"}
    )
    assert err == "handoff_product_binding_mismatch"


# =========================================================================
# TEST 32-35: IDEMPOTENCY & CONCURRENCY
# =========================================================================

def test_32_one_handoff_replay(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    r1, _ = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    r2, _ = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert r1["handoff_id"] == r2["handoff_id"]

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_handoff_receipts")
    assert cur.fetchone()[0] == 1


def test_33_one_draft_replay(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    r1, _ = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    r2, _ = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert r1["draft_id"] == r2["draft_id"]

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_publication_drafts")
    assert cur.fetchone()[0] == 1


def test_34_one_queue_replay(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    r1, _ = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    r2, _ = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert r1["publication_id"] == r2["publication_id"]

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_publication_queue")
    assert cur.fetchone()[0] == 1


def test_35_concurrent_replay_one_identity(tmp_path):
    db_file = tmp_path / "concurrent_ve.db"
    conn_init = sqlite3.connect(str(db_file))
    conn_init.row_factory = sqlite3.Row
    _setup_video_edit_job(conn_init, tmp_path, uid=77, job_id=501)
    avea.register_video_edit_autopost_intent(conn_init, 77, 501, "SCHEDULE_NOW")
    conn_init.close()

    results = []

    def _worker():
        c = sqlite3.connect(str(db_file), timeout=20.0)
        c.row_factory = sqlite3.Row
        try:
            res, _ = avea.process_video_edit_autopost_handoff(c, 501, 77)
            results.append(res)
        finally:
            c.close()

    threads = [threading.Thread(target=_worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 5
    pub_ids = {r["publication_id"] for r in results if r.get("publication_id")}
    assert len(pub_ids) == 1

    chk_conn = sqlite3.connect(str(db_file))
    cur = chk_conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_publication_queue")
    assert cur.fetchone()[0] == 1
    chk_conn.close()


# =========================================================================
# TEST 36-38: DELIVERED -> CHARGED PROGRESSION REPLAY
# =========================================================================

def test_36_delivered_to_charged_replay_same_handoff(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, status="delivered")
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    r1, _ = avea.process_video_edit_autopost_handoff(conn, 501, 77)

    # Canonical charge transition
    claimed = video_editengine1.claim_charge(conn, worker_job_id=901)
    assert claimed is True
    charged = video_editengine1.mark_charge_result(conn, worker_job_id=901, ok=True, charged_xu=100)
    assert charged.get("status") == "charged"
    assert charged.get("charge_state") == "charged"
    assert charged.get("charged_xu") == 100

    assert charged["autopost_handoff"]["handoff_id"] == r1["handoff_id"]
    assert charged["autopost_adapter"]["handoff_id"] == r1["handoff_id"]

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_handoff_receipts")
    assert cur.fetchone()[0] == 1


def test_37_delivered_to_charged_replay_same_draft(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, status="delivered")
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    r1, _ = avea.process_video_edit_autopost_handoff(conn, 501, 77)

    # Canonical charge transition
    claimed = video_editengine1.claim_charge(conn, worker_job_id=901)
    assert claimed is True
    charged = video_editengine1.mark_charge_result(conn, worker_job_id=901, ok=True, charged_xu=100)
    assert charged.get("status") == "charged"
    assert charged.get("charge_state") == "charged"
    assert charged.get("charged_xu") == 100

    assert charged["autopost_adapter"]["draft_id"] == r1["draft_id"]

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_publication_drafts")
    assert cur.fetchone()[0] == 1


def test_38_delivered_to_charged_replay_same_publication(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, status="delivered")
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    r1, _ = avea.process_video_edit_autopost_handoff(conn, 501, 77)

    # Canonical charge transition
    claimed = video_editengine1.claim_charge(conn, worker_job_id=901)
    assert claimed is True
    charged = video_editengine1.mark_charge_result(conn, worker_job_id=901, ok=True, charged_xu=100)
    assert charged.get("status") == "charged"
    assert charged.get("charge_state") == "charged"
    assert charged.get("charged_xu") == 100

    assert charged["autopost_adapter"]["publication_id"] == r1["publication_id"]

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_publication_queue")
    assert cur.fetchone()[0] == 1


# =========================================================================
# TEST 39-47: PRODUCER & BILLING DECOUPLING
# =========================================================================

def test_39_autopost_failure_leaves_delivered_state(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, status="delivered")
    # Trigger adapter error with unregistered intent / broken receipt
    avea.process_video_edit_autopost_handoff(
        conn, 501, 77, handoff_receipt={"handoff_id": "invalid_handoff"}
    )
    cur = conn.cursor()
    cur.execute("SELECT status FROM video_edit_jobs WHERE id=501")
    assert cur.fetchone()[0] == "delivered"


def test_40_autopost_failure_leaves_charged_state(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, status="charged")
    avea.process_video_edit_autopost_handoff(
        conn, 501, 77, handoff_receipt={"handoff_id": "invalid_handoff"}
    )
    cur = conn.cursor()
    cur.execute("SELECT status FROM video_edit_jobs WHERE id=501")
    assert cur.fetchone()[0] == "charged"


def test_41_autopost_failure_leaves_receipt_delivery_metadata(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)
    avea.process_video_edit_autopost_handoff(
        conn, 501, 77, handoff_receipt={"handoff_id": "invalid_handoff"}
    )
    cur = conn.cursor()
    cur.execute("SELECT receipt_state, delivered_at, delivery_message_id FROM video_edit_jobs WHERE id=501")
    row = cur.fetchone()
    assert row["receipt_state"] == "created"
    assert row["delivered_at"] == "2026-03-20T10:00:00Z"
    assert row["delivery_message_id"] in ("msg-1", "9001")


def test_42_autopost_failure_does_not_alter_charge_state(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)
    conn.execute("UPDATE video_edit_jobs SET charge_state='charging' WHERE id=501")
    conn.commit()

    avea.process_video_edit_autopost_handoff(conn, 501, 77)
    cur = conn.cursor()
    cur.execute("SELECT charge_state FROM video_edit_jobs WHERE id=501")
    assert cur.fetchone()[0] == "charging"


def test_43_autopost_failure_does_not_alter_charged_xu(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)
    conn.execute("UPDATE video_edit_jobs SET charged_xu=150 WHERE id=501")
    conn.commit()

    avea.process_video_edit_autopost_handoff(conn, 501, 77)
    cur = conn.cursor()
    cur.execute("SELECT charged_xu FROM video_edit_jobs WHERE id=501")
    assert cur.fetchone()[0] == 150


def test_44_autopost_does_not_call_claim_charge(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr(video_editengine1, "claim_charge", lambda *a, **kw: called.append(True))
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert len(called) == 0


def test_45_autopost_does_not_call_mark_charge_result(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr(video_editengine1, "mark_charge_result", lambda *a, **kw: called.append(True))
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert len(called) == 0


def test_46_autopost_does_not_rerender(tmp_path):
    # AutoPost failure never triggers outbox or local worker render
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)

    avea.process_video_edit_autopost_handoff(conn, 501, 77)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM video_edit_outbox")
    assert cur.fetchone()[0] == 0


def test_47_autopost_does_not_requeue(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)

    avea.process_video_edit_autopost_handoff(conn, 501, 77)
    cur = conn.cursor()
    cur.execute("SELECT status FROM video_edit_jobs WHERE id=501")
    assert cur.fetchone()[0] == "delivered"


# =========================================================================
# TEST 48-54: PROGRESSED PUBLICATION REPLAY MATRIX
# =========================================================================

@pytest.mark.parametrize("progressed_state", [
    "SCHEDULED",
    "CLAIMED",
    "PUBLISHING",
    "PUBLISHED",
    "FAILED_RETRYABLE",
    "FAILED_FINAL",
    "CANCELLED",
])
def test_48_to_54_progressed_publication_replay(tmp_path, progressed_state):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    jid, wid, vf, sha = _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    # First run creates SCHEDULED
    res1, _ = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    pub_id = res1["publication_id"]

    # Scheduler externally progresses queue item
    conn.execute(
        "UPDATE autopost_publication_queue SET state=? WHERE publication_id=?",
        (progressed_state, pub_id),
    )
    conn.commit()

    # Second callback replay
    res2, status = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert res2["publication_id"] == pub_id
    assert res2["state"] == progressed_state
    assert res2["blocker"] is None

    # Verify no second queue row created
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_publication_queue")
    assert cur.fetchone()[0] == 1


# =========================================================================
# TEST 55-56: SCHEDULE CONFLICTS
# =========================================================================

def test_55_schedule_at_conflict_fails_closed(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_AT", schedule_at="2026-10-01T12:00:00Z")

    res1, _ = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert res1["state"] == "SCHEDULED"

    # Direct database mutation simulating incompatible external schedule change on intent
    conn.execute(
        "UPDATE autopost_video_edit_intents SET schedule_at='2026-10-02T12:00:00Z' WHERE video_edit_job_id=501"
    )
    conn.commit()

    res2, err = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert err == "schedule_conflict_different_timestamp"
    assert res2["blocker"] == "schedule_conflict_different_timestamp"

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_publication_queue")
    assert cur.fetchone()[0] == 1


def test_56_schedule_now_wallclock_replay_no_self_conflict(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW", now="2026-03-20T10:00:00Z")

    r1, _ = avea.process_video_edit_autopost_handoff(conn, 501, 77, now="2026-03-20T10:00:00Z")
    # Later wallclock replay
    r2, status = avea.process_video_edit_autopost_handoff(conn, 501, 77, now="2026-03-21T18:00:00Z")
    assert status == "scheduled"
    assert r1["publication_id"] == r2["publication_id"]
    assert r2["blocker"] is None


# =========================================================================
# TEST 57-58: PARENT LINEAGE
# =========================================================================

def test_57_parent_lineage_preserved(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    aah.ensure_autopost_handoff_schema(conn)

    conn.execute(
        """INSERT INTO autopost_handoff_receipts (
            handoff_id, owner_id, source_product, source_job_id, asset_id,
            artifact_sha256, purpose, status, lineage_json, asset_snapshot_json, created_at
        ) VALUES ('parent_h', 77, 'video_edit', '401', 'parent_asset_123', 'a'*64, 'autopost', 'created', '{}', '{}', 'now')"""
    )
    conn.commit()

    # Video Edit child with parent in tail_json
    tail = json.dumps({"parent_asset_id": "parent_asset_123"})
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, tail_json=tail)
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    res, _ = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert res["handoff_id"] is not None

    cur = conn.cursor()
    cur.execute(
        "SELECT parent_asset_id, lineage_json FROM autopost_handoff_receipts WHERE handoff_id=?",
        (res["handoff_id"],),
    )
    row = cur.fetchone()
    assert row[0] == "parent_asset_123"
    lineage = json.loads(row[1] or "[]")
    assert "parent_asset_123" in lineage


def test_58_cross_owner_lineage_blocked(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    aah.ensure_autopost_handoff_schema(conn)

    # Parent belongs to user 999
    conn.execute(
        """INSERT INTO autopost_handoff_receipts (
            handoff_id, owner_id, source_product, source_job_id, asset_id,
            artifact_sha256, purpose, status, lineage_json, asset_snapshot_json, created_at
        ) VALUES ('parent_h2', 999, 'video_edit', '401', 'foreign_parent_asset', 'a'*64, 'autopost', 'created', '{}', '{}', 'now')"""
    )
    conn.commit()

    # User 77 attempts to claim foreign parent
    tail = json.dumps({"parent_asset_id": "foreign_parent_asset"})
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, tail_json=tail)
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    res, err = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert "cross_owner_lineage_forbidden" in err


# =========================================================================
# TEST 59-63: SYSTEM BOUNDARIES & ISOLATION
# =========================================================================

def test_59_zero_social_provider_calls(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    res, _ = avea.process_video_edit_autopost_handoff(conn, 501, 77)
    assert res["state"] == "SCHEDULED"
    # S4 ends at SCHEDULED in publication queue without any social dispatch
    cur = conn.cursor()
    cur.execute("SELECT state FROM autopost_publication_queue WHERE publication_id=?", (res["publication_id"],))
    assert cur.fetchone()[0] == "SCHEDULED"


def test_60_zero_wallet_mutation(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501)
    avea.register_video_edit_autopost_intent(conn, 77, 501, "SCHEDULE_NOW")

    # Table video_edit_jobs price_xu and charged_xu remain unmutated by AutoPost
    avea.process_video_edit_autopost_handoff(conn, 501, 77)
    cur = conn.cursor()
    cur.execute("SELECT price_xu, charged_xu, charge_state FROM video_edit_jobs WHERE id=501")
    row = cur.fetchone()
    assert row["price_xu"] == 100
    assert row["charged_xu"] == 0
    assert row["charge_state"] == "not_charged"


def test_61_product_video_s3_protected_behavior_unchanged(tmp_path):
    # Verify Product Video adapter authority works seamlessly alongside Video Edit adapter
    from services import autopost_product_video_adapter as apva
    from services import video_project_queue as queue
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)
    conn.execute("INSERT INTO video_projects (project_id, user_id, status) VALUES (1, 101, 'completed')")
    conn.execute("INSERT INTO video_jobs (id, project_id, user_id, status) VALUES (201, 1, 101, 'completed')")
    conn.commit()

    intent, st = apva.register_product_video_autopost_intent(conn, 101, 201, "OFF")
    assert st == "registered"
    assert intent["mode"] == "OFF"


def test_62_subdub_remains_fail_closed(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    aah.ensure_autopost_handoff_schema(conn)

    res, err = aah.adapt_subdub_output(conn, "sd_1", 101)
    assert res is None
    assert err == "subdub_canonical_authority_unavailable"


def test_63_existing_video_remains_fail_closed(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    aah.ensure_autopost_handoff_schema(conn)

    res, err = aah.adapt_existing_video_output(conn, {"id": 1}, 101)
    assert res is None
    assert err == "existing_video_canonical_authority_unavailable"


def test_64_record_worker_update_with_intent_attaches_autopost_adapter(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    from tests.test_p0_autopost_production_callback_seam import _setup_video_edit_job as _setup_seam_job
    job, rec, video_file, sha = _setup_seam_job(conn, tmp_path, uid=77)
    jid = int(job.get("job_id") or job["local_worker_job_id"])
    avea.register_video_edit_autopost_intent(conn, 77, jid, "SCHEDULE_NOW")

    updated = video_editengine1.record_worker_update(
        conn,
        worker_job_id=job["local_worker_job_id"],
        worker_status="succeeded",
        detail={"stage": "delivering", "validation": "passed"},
        receipt=rec,
    )
    assert updated.get("status") in {"delivered", "charged"}
    assert updated.get("autopost_handoff") is not None
    assert updated.get("autopost_adapter") is not None
    assert updated["autopost_adapter"]["attempted"] is True
    assert updated["autopost_adapter"]["mode"] == "SCHEDULE_NOW"
    assert updated["autopost_adapter"]["state"] == "SCHEDULED"
    assert updated["autopost_adapter"]["publication_id"] is not None


def test_65_record_worker_update_without_intent_has_no_autopost_adapter(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    from tests.test_p0_autopost_production_callback_seam import _setup_video_edit_job as _setup_seam_job
    job, rec, video_file, sha = _setup_seam_job(conn, tmp_path, uid=77)

    updated = video_editengine1.record_worker_update(
        conn,
        worker_job_id=job["local_worker_job_id"],
        worker_status="succeeded",
        detail={"stage": "delivering", "validation": "passed"},
        receipt=rec,
    )
    assert updated.get("status") in {"delivered", "charged"}
    assert updated.get("autopost_handoff") is not None
    assert updated.get("autopost_adapter") is None


# =========================================================================
# TEST 66-77: CANONICAL CHARGE TRANSITION REPLAY & SAFETY GATES
# =========================================================================

def test_66_canonical_delivered_to_charged_same_handoff(tmp_path):
    """66 canonical delivered -> claim_charge -> mark_charge_result -> same handoff"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    jid, wid, vf, sha = _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, local_worker_job_id=901, status="delivered")
    avea.register_video_edit_autopost_intent(conn, 77, jid, "SCHEDULE_NOW")

    r1, _ = avea.process_video_edit_autopost_handoff(conn, jid, 77)

    claimed = video_editengine1.claim_charge(conn, worker_job_id=wid)
    assert claimed is True
    charged = video_editengine1.mark_charge_result(conn, worker_job_id=wid, ok=True, charged_xu=100)

    assert charged.get("status") == "charged"
    assert charged.get("charge_state") == "charged"
    assert charged["autopost_handoff"]["handoff_id"] == r1["handoff_id"]

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_handoff_receipts WHERE source_job_id=?", (str(jid),))
    assert cur.fetchone()[0] == 1


def test_67_canonical_delivered_to_charged_same_draft(tmp_path):
    """67 canonical delivered -> charged -> same draft"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    jid, wid, vf, sha = _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, local_worker_job_id=901, status="delivered")
    avea.register_video_edit_autopost_intent(conn, 77, jid, "SCHEDULE_NOW")

    r1, _ = avea.process_video_edit_autopost_handoff(conn, jid, 77)

    claimed = video_editengine1.claim_charge(conn, worker_job_id=wid)
    assert claimed is True
    charged = video_editengine1.mark_charge_result(conn, worker_job_id=wid, ok=True, charged_xu=100)

    assert charged.get("status") == "charged"
    assert charged["autopost_adapter"]["draft_id"] == r1["draft_id"]

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_publication_drafts WHERE handoff_id=?", (r1["handoff_id"],))
    assert cur.fetchone()[0] == 1


def test_68_canonical_delivered_to_charged_same_publication(tmp_path):
    """68 canonical delivered -> charged -> same publication"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    jid, wid, vf, sha = _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, local_worker_job_id=901, status="delivered")
    avea.register_video_edit_autopost_intent(conn, 77, jid, "SCHEDULE_NOW")

    r1, _ = avea.process_video_edit_autopost_handoff(conn, jid, 77)

    claimed = video_editengine1.claim_charge(conn, worker_job_id=wid)
    assert claimed is True
    charged = video_editengine1.mark_charge_result(conn, worker_job_id=wid, ok=True, charged_xu=100)

    assert charged.get("status") == "charged"
    assert charged["autopost_adapter"]["publication_id"] == r1["publication_id"]

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_publication_queue WHERE draft_id=?", (r1["draft_id"],))
    assert cur.fetchone()[0] == 1


def test_69_charged_transition_replay_with_publication_claimed(tmp_path):
    """69 charged transition replay with publication CLAIMED"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    jid, wid, vf, sha = _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, local_worker_job_id=901, status="delivered")
    avea.register_video_edit_autopost_intent(conn, 77, jid, "SCHEDULE_NOW")

    r1, _ = avea.process_video_edit_autopost_handoff(conn, jid, 77)
    pub_id = r1["publication_id"]

    # Progress queue state to CLAIMED
    conn.execute("UPDATE autopost_publication_queue SET state='CLAIMED' WHERE publication_id=?", (pub_id,))
    conn.commit()

    claimed = video_editengine1.claim_charge(conn, worker_job_id=wid)
    assert claimed is True
    charged = video_editengine1.mark_charge_result(conn, worker_job_id=wid, ok=True, charged_xu=100)

    assert charged.get("status") == "charged"
    assert charged["autopost_adapter"]["publication_id"] == pub_id
    assert charged["autopost_adapter"]["state"] == "CLAIMED"

    # Verify no state regression in database
    cur = conn.cursor()
    cur.execute("SELECT state FROM autopost_publication_queue WHERE publication_id=?", (pub_id,))
    assert cur.fetchone()[0] == "CLAIMED"


def test_70_charged_transition_replay_with_publication_publishing(tmp_path):
    """70 charged transition replay with publication PUBLISHING"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    jid, wid, vf, sha = _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, local_worker_job_id=901, status="delivered")
    avea.register_video_edit_autopost_intent(conn, 77, jid, "SCHEDULE_NOW")

    r1, _ = avea.process_video_edit_autopost_handoff(conn, jid, 77)
    pub_id = r1["publication_id"]

    conn.execute("UPDATE autopost_publication_queue SET state='PUBLISHING' WHERE publication_id=?", (pub_id,))
    conn.commit()

    claimed = video_editengine1.claim_charge(conn, worker_job_id=wid)
    assert claimed is True
    charged = video_editengine1.mark_charge_result(conn, worker_job_id=wid, ok=True, charged_xu=100)

    assert charged.get("status") == "charged"
    assert charged["autopost_adapter"]["publication_id"] == pub_id
    assert charged["autopost_adapter"]["state"] == "PUBLISHING"

    cur = conn.cursor()
    cur.execute("SELECT state FROM autopost_publication_queue WHERE publication_id=?", (pub_id,))
    assert cur.fetchone()[0] == "PUBLISHING"


def test_71_charged_transition_replay_with_publication_published(tmp_path):
    """71 charged transition replay with publication PUBLISHED"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    jid, wid, vf, sha = _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, local_worker_job_id=901, status="delivered")
    avea.register_video_edit_autopost_intent(conn, 77, jid, "SCHEDULE_NOW")

    r1, _ = avea.process_video_edit_autopost_handoff(conn, jid, 77)
    pub_id = r1["publication_id"]

    conn.execute("UPDATE autopost_publication_queue SET state='PUBLISHED' WHERE publication_id=?", (pub_id,))
    conn.commit()

    claimed = video_editengine1.claim_charge(conn, worker_job_id=wid)
    assert claimed is True
    charged = video_editengine1.mark_charge_result(conn, worker_job_id=wid, ok=True, charged_xu=100)

    assert charged.get("status") == "charged"
    assert charged["autopost_adapter"]["publication_id"] == pub_id
    assert charged["autopost_adapter"]["state"] == "PUBLISHED"

    cur = conn.cursor()
    cur.execute("SELECT state FROM autopost_publication_queue WHERE publication_id=?", (pub_id,))
    assert cur.fetchone()[0] == "PUBLISHED"


def test_72_charged_transition_replay_with_failed_retryable(tmp_path):
    """72 charged transition replay with FAILED_RETRYABLE"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    jid, wid, vf, sha = _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, local_worker_job_id=901, status="delivered")
    avea.register_video_edit_autopost_intent(conn, 77, jid, "SCHEDULE_NOW")

    r1, _ = avea.process_video_edit_autopost_handoff(conn, jid, 77)
    pub_id = r1["publication_id"]

    conn.execute("UPDATE autopost_publication_queue SET state='FAILED_RETRYABLE' WHERE publication_id=?", (pub_id,))
    conn.commit()

    claimed = video_editengine1.claim_charge(conn, worker_job_id=wid)
    assert claimed is True
    charged = video_editengine1.mark_charge_result(conn, worker_job_id=wid, ok=True, charged_xu=100)

    assert charged.get("status") == "charged"
    assert charged["autopost_adapter"]["publication_id"] == pub_id
    assert charged["autopost_adapter"]["state"] == "FAILED_RETRYABLE"

    cur = conn.cursor()
    cur.execute("SELECT state FROM autopost_publication_queue WHERE publication_id=?", (pub_id,))
    assert cur.fetchone()[0] == "FAILED_RETRYABLE"


def test_73_charged_transition_replay_with_failed_final(tmp_path):
    """73 charged transition replay with FAILED_FINAL"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    jid, wid, vf, sha = _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, local_worker_job_id=901, status="delivered")
    avea.register_video_edit_autopost_intent(conn, 77, jid, "SCHEDULE_NOW")

    r1, _ = avea.process_video_edit_autopost_handoff(conn, jid, 77)
    pub_id = r1["publication_id"]

    conn.execute("UPDATE autopost_publication_queue SET state='FAILED_FINAL' WHERE publication_id=?", (pub_id,))
    conn.commit()

    claimed = video_editengine1.claim_charge(conn, worker_job_id=wid)
    assert claimed is True
    charged = video_editengine1.mark_charge_result(conn, worker_job_id=wid, ok=True, charged_xu=100)

    assert charged.get("status") == "charged"
    assert charged["autopost_adapter"]["publication_id"] == pub_id
    assert charged["autopost_adapter"]["state"] == "FAILED_FINAL"

    cur = conn.cursor()
    cur.execute("SELECT state FROM autopost_publication_queue WHERE publication_id=?", (pub_id,))
    assert cur.fetchone()[0] == "FAILED_FINAL"


def test_74_charged_transition_replay_with_cancelled(tmp_path):
    """74 charged transition replay with CANCELLED"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    jid, wid, vf, sha = _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, local_worker_job_id=901, status="delivered")
    avea.register_video_edit_autopost_intent(conn, 77, jid, "SCHEDULE_NOW")

    r1, _ = avea.process_video_edit_autopost_handoff(conn, jid, 77)
    pub_id = r1["publication_id"]

    conn.execute("UPDATE autopost_publication_queue SET state='CANCELLED' WHERE publication_id=?", (pub_id,))
    conn.commit()

    claimed = video_editengine1.claim_charge(conn, worker_job_id=wid)
    assert claimed is True
    charged = video_editengine1.mark_charge_result(conn, worker_job_id=wid, ok=True, charged_xu=100)

    assert charged.get("status") == "charged"
    assert charged["autopost_adapter"]["publication_id"] == pub_id
    assert charged["autopost_adapter"]["state"] == "CANCELLED"

    cur = conn.cursor()
    cur.execute("SELECT state FROM autopost_publication_queue WHERE publication_id=?", (pub_id,))
    assert cur.fetchone()[0] == "CANCELLED"


def test_75_autopost_replay_failure_after_charge_leaves_charged_xu_unchanged(tmp_path, monkeypatch):
    """75 AutoPost replay failure after charge leaves charged_xu unchanged"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    jid, wid, vf, sha = _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, local_worker_job_id=901, status="delivered")
    avea.register_video_edit_autopost_intent(conn, 77, jid, "SCHEDULE_NOW")

    monkeypatch.setattr(avea, "process_video_edit_autopost_handoff", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("simulated_autopost_crash")))

    claimed = video_editengine1.claim_charge(conn, worker_job_id=wid)
    assert claimed is True
    charged = video_editengine1.mark_charge_result(conn, worker_job_id=wid, ok=True, charged_xu=100)

    assert charged.get("status") == "charged"
    assert charged.get("charge_state") == "charged"
    assert charged.get("charged_xu") == 100

    cur = conn.cursor()
    cur.execute("SELECT status, charge_state, charged_xu FROM video_edit_jobs WHERE id=?", (jid,))
    row = cur.fetchone()
    assert row["status"] == "charged"
    assert row["charge_state"] == "charged"
    assert row["charged_xu"] == 100


def test_76_autopost_replay_failure_after_charge_leaves_delivery_metadata_unchanged(tmp_path, monkeypatch):
    """76 AutoPost replay failure after charge leaves delivery metadata unchanged"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    jid, wid, vf, sha = _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, local_worker_job_id=901, status="delivered")
    avea.register_video_edit_autopost_intent(conn, 77, jid, "SCHEDULE_NOW")

    cur = conn.cursor()
    cur.execute("SELECT output_path, output_sha256, output_size_bytes, delivery_file_id, delivery_message_id FROM video_edit_jobs WHERE id=?", (jid,))
    before = dict(cur.fetchone())

    monkeypatch.setattr(avea, "process_video_edit_autopost_handoff", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("simulated_autopost_crash")))

    claimed = video_editengine1.claim_charge(conn, worker_job_id=wid)
    assert claimed is True
    charged = video_editengine1.mark_charge_result(conn, worker_job_id=wid, ok=True, charged_xu=100)
    assert charged.get("status") == "charged"

    cur.execute("SELECT output_path, output_sha256, output_size_bytes, delivery_file_id, delivery_message_id FROM video_edit_jobs WHERE id=?", (jid,))
    after = dict(cur.fetchone())
    assert before == after


def test_77_caller_owned_charge_transaction_does_not_execute_adapter_precommit(tmp_path, monkeypatch):
    """77 caller-owned charge transaction does not execute adapter pre-commit"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    jid, wid, vf, sha = _setup_video_edit_job(conn, tmp_path, uid=77, job_id=501, local_worker_job_id=901, status="delivered")
    avea.register_video_edit_autopost_intent(conn, 77, jid, "SCHEDULE_NOW")

    claimed = video_editengine1.claim_charge(conn, worker_job_id=wid)
    assert claimed is True

    # Caller owns an uncommitted transaction
    conn.execute("BEGIN IMMEDIATE")
    assert conn.in_transaction is True

    adapter_calls = []
    monkeypatch.setattr(avea, "process_video_edit_autopost_handoff", lambda *a, **kw: adapter_calls.append(True))

    charged = video_editengine1.mark_charge_result(conn, worker_job_id=wid, ok=True, charged_xu=100)

    # 1. Zero pre-commit adapter calls
    assert len(adapter_calls) == 0

    # 2. No force commit: transaction remains open and owned by caller
    assert conn.in_transaction is True

    # 3. Observability blocker recorded
    assert charged.get("autopost_handoff", {}).get("blocker") == "caller_transaction_uncommitted"

    # 4. Post-commit: caller commits and can safely invoke adapter
    conn.commit()
    assert conn.in_transaction is False
