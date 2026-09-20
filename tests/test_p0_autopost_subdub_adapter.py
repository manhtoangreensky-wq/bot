"""tests/test_p0_autopost_subdub_adapter.py

Tests for P0.AUTOPOST.S5: SubDub -> AutoPost Adapter Integration.
Governed under TOAN AAS Owner-Governed Codex.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

import pytest

from services import autopost_asset_handoff as aah
from services import autopost_scheduler as aps
from services import autopost_subdub_adapter as asda
from services import video_editengine1
from services import video_local_validation
from services import video_project_queue as queue


def _make_dummy_video(tmp_path: Path, name: str = "test_subdub.mp4", content: bytes = b"subdub_s5_canonical_video_bytes_1234567890") -> Path:
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
            "duration": 20.0,
            "duration_ms": 20000,
            "width": 1080,
            "height": 1920,
            "has_video": True,
            "has_audio": True,
            "format_name": "mp4",
        },
    )


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    asda.ensure_autopost_subdub_adapter_schema(conn)
    return conn


def _seed_canonical_subdub_job(
    conn: sqlite3.Connection,
    tmp_path: Path,
    uid: int = 123456,
    internal_job_id: str = "subdub_int_job_001",
    charge_status: str = "charged",
    auto_settlement_pending: bool = False,
    file_id: str = "tg_file_subdub_999",
    message_id: int = 8888,
    raw_bytes: bytes = b"canonical_subdub_video_stream_bytes_777",
) -> tuple[dict[str, Any], Path, str]:
    video_file = _make_dummy_video(tmp_path, f"{internal_job_id}.mp4", raw_bytes)
    sha = _sha256(raw_bytes)

    job_data = {
        "internal_job_id": internal_job_id,
        "job_id": internal_job_id,
        "user_id": uid,
        "feature": "subtitle_dub",
        "terminal_state": "delivered",
        "output_sent": True,
        "delivery_succeeded": True,
        "final_mp4_validated": True,
        "final_mp4_delivered": True,
        "charge_status": charge_status,
        "auto_settlement_pending_recovery": auto_settlement_pending,
        "video_delivery_file_id": file_id,
        "video_delivery_message_id": message_id,
        "video_delivery_sha256": sha,
        "video_delivery_size_bytes": len(raw_bytes),
        "video_delivery_duration_seconds": 20.0,
        "video_delivery_mime_type": "video/mp4",
        "final_mp4": str(video_file),
        "settled_at": "2026-09-20T12:00:00Z",
        "output_validation": {
            "ok": True,
            "width": 1080,
            "height": 1920,
            "duration": 20.0,
            "actual_duration": 20.0,
        },
    }

    conn.execute(
        "INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES (?, ?, '2026-09-20T12:00:00Z')",
        (f"engine_async_job:{internal_job_id}", json.dumps(job_data)),
    )
    conn.commit()
    return job_data, video_file, sha


def test_schema_creation(db_conn):
    tables = [
        r[0]
        for r in db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    ]
    assert "autopost_subdub_intents" in tables
    assert "system_settings" in tables
    assert "autopost_handoff_receipts" in tables
    assert "autopost_publication_drafts" in tables
    assert "autopost_publication_queue" in tables


def test_subdub_canonical_authority_missing_job(db_conn):
    asset, err = aah.adapt_subdub_output(
        db_conn,
        job_id="nonexistent_job",
        requesting_user_id=123456,
    )
    assert asset is None
    assert err == "subdub_canonical_authority_unavailable"


def test_subdub_non_terminal_billing_blocked(db_conn, tmp_path):
    _seed_canonical_subdub_job(
        db_conn,
        tmp_path,
        uid=123456,
        internal_job_id="job_pending_bill",
        charge_status="pending",
    )
    asset, err = aah.adapt_subdub_output(
        db_conn,
        job_id="job_pending_bill",
        requesting_user_id=123456,
    )
    assert asset is None
    assert err == "subdub_billing_not_terminal"

    _seed_canonical_subdub_job(
        db_conn,
        tmp_path,
        uid=123456,
        internal_job_id="job_settle_recovery",
        charge_status="charged",
        auto_settlement_pending=True,
    )
    asset2, err2 = aah.adapt_subdub_output(
        db_conn,
        job_id="job_settle_recovery",
        requesting_user_id=123456,
    )
    assert asset2 is None
    assert err2 == "subdub_billing_not_terminal"


def test_subdub_non_durable_delivery_blocked(db_conn, tmp_path):
    _seed_canonical_subdub_job(
        db_conn,
        tmp_path,
        uid=123456,
        internal_job_id="job_no_file",
        file_id="",
    )
    asset, err = aah.adapt_subdub_output(
        db_conn,
        job_id="job_no_file",
        requesting_user_id=123456,
    )
    assert asset is None
    assert err == "subdub_delivery_not_durable"


def test_subdub_owner_mismatch_blocked(db_conn, tmp_path):
    _seed_canonical_subdub_job(
        db_conn,
        tmp_path,
        uid=123456,
        internal_job_id="job_owner_test",
    )
    asset, err = aah.adapt_subdub_output(
        db_conn,
        job_id="job_owner_test",
        requesting_user_id=999999,
    )
    assert asset is None
    assert err == "owner_mismatch"


def test_subdub_artifact_replacement_detected(db_conn, tmp_path):
    job_data, video_file, sha = _seed_canonical_subdub_job(
        db_conn,
        tmp_path,
        uid=123456,
        internal_job_id="job_tampered",
    )
    # Tamper with video file content
    video_file.write_bytes(b"tampered_corrupted_video_bytes")

    asset, err = aah.adapt_subdub_output(
        db_conn,
        job_id="job_tampered",
        requesting_user_id=123456,
    )
    assert asset is None
    assert err == "subdub_artifact_replacement_detected"


def test_subdub_register_intent_and_idempotency(db_conn, tmp_path):
    _seed_canonical_subdub_job(db_conn, tmp_path, uid=123456, internal_job_id="job_intent_1")

    intent, msg = asda.register_subdub_autopost_intent(
        db_conn,
        owner_id=123456,
        subdub_job_id="job_intent_1",
        mode=asda.SubDubAutoPostMode.DRAFT_ONLY,
        selected_channels=["tiktok", "youtube"],
        caption_override="Test SubDub AutoPost Caption",
    )
    assert intent is not None
    assert msg == "registered"
    assert intent["mode"] == "DRAFT_ONLY"

    # Re-registering with identical parameters is idempotent
    intent2, msg2 = asda.register_subdub_autopost_intent(
        db_conn,
        owner_id=123456,
        subdub_job_id="job_intent_1",
        mode=asda.SubDubAutoPostMode.DRAFT_ONLY,
        selected_channels=["tiktok", "youtube"],
        caption_override="Test SubDub AutoPost Caption",
    )
    assert intent2 is not None
    assert msg2 == "idempotent_existing"

    # Conflicting mode fails closed
    intent_conflict, msg_conflict = asda.register_subdub_autopost_intent(
        db_conn,
        owner_id=123456,
        subdub_job_id="job_intent_1",
        mode=asda.SubDubAutoPostMode.SCHEDULE_NOW,
    )
    assert intent_conflict is None
    assert msg_conflict == "intent_conflict_already_registered"


def test_subdub_adapter_no_intent(db_conn, tmp_path):
    _seed_canonical_subdub_job(db_conn, tmp_path, uid=123456, internal_job_id="job_no_intent")

    diag, err = asda.process_subdub_autopost_handoff(
        db_conn,
        subdub_job_id="job_no_intent",
        requesting_user_id=123456,
    )
    assert diag["attempted"] is False
    assert diag["blocker"] == "no_intent_registered"
    assert err == "no_intent_registered"


def test_subdub_adapter_mode_off(db_conn, tmp_path):
    _seed_canonical_subdub_job(db_conn, tmp_path, uid=123456, internal_job_id="job_mode_off")
    asda.register_subdub_autopost_intent(
        db_conn,
        owner_id=123456,
        subdub_job_id="job_mode_off",
        mode=asda.SubDubAutoPostMode.OFF,
    )

    diag, err = asda.process_subdub_autopost_handoff(
        db_conn,
        subdub_job_id="job_mode_off",
        requesting_user_id=123456,
    )
    assert diag["attempted"] is True
    assert diag["mode"] == "OFF"
    assert err == "off"

    # Verify no draft created
    drafts = db_conn.execute("SELECT COUNT(*) FROM autopost_publication_drafts").fetchone()[0]
    assert drafts == 0


def test_subdub_adapter_mode_draft_only(db_conn, tmp_path):
    _seed_canonical_subdub_job(db_conn, tmp_path, uid=123456, internal_job_id="job_draft_only")
    asda.register_subdub_autopost_intent(
        db_conn,
        owner_id=123456,
        subdub_job_id="job_draft_only",
        mode=asda.SubDubAutoPostMode.DRAFT_ONLY,
        selected_channels=["facebook", "tiktok"],
        caption_override="SubDub Draft Caption",
    )

    diag, err = asda.process_subdub_autopost_handoff(
        db_conn,
        subdub_job_id="job_draft_only",
        requesting_user_id=123456,
    )
    assert diag["attempted"] is True
    assert diag["created_or_reused"] is True
    assert diag["state"] == "PLANNED"
    assert diag["draft_id"] is not None
    assert err == "draft_ready"

    # Verify draft record
    draft = db_conn.execute(
        "SELECT * FROM autopost_publication_drafts WHERE draft_id=?",
        (diag["draft_id"],),
    ).fetchone()
    assert draft["caption_draft"] == "SubDub Draft Caption"
    assert json.loads(draft["selected_channels_json"]) == ["facebook", "tiktok"]

    # Verify queue is empty
    queue_count = db_conn.execute("SELECT COUNT(*) FROM autopost_publication_queue").fetchone()[0]
    assert queue_count == 0


def test_subdub_adapter_mode_schedule_now(db_conn, tmp_path):
    _seed_canonical_subdub_job(db_conn, tmp_path, uid=123456, internal_job_id="job_sched_now")
    asda.register_subdub_autopost_intent(
        db_conn,
        owner_id=123456,
        subdub_job_id="job_sched_now",
        mode=asda.SubDubAutoPostMode.SCHEDULE_NOW,
    )

    diag, err = asda.process_subdub_autopost_handoff(
        db_conn,
        subdub_job_id="job_sched_now",
        requesting_user_id=123456,
    )
    assert diag["attempted"] is True
    assert diag["created_or_reused"] is True
    assert diag["state"] == "SCHEDULED"
    assert diag["publication_id"] is not None
    assert err == "scheduled"

    # Verify queue item
    q = db_conn.execute(
        "SELECT * FROM autopost_publication_queue WHERE publication_id=?",
        (diag["publication_id"],),
    ).fetchone()
    assert q["state"] == "SCHEDULED"
    assert q["owner_id"] == 123456


def test_subdub_adapter_mode_schedule_at(db_conn, tmp_path):
    _seed_canonical_subdub_job(db_conn, tmp_path, uid=123456, internal_job_id="job_sched_at")
    target_utc = "2026-09-25T08:30:00Z"
    asda.register_subdub_autopost_intent(
        db_conn,
        owner_id=123456,
        subdub_job_id="job_sched_at",
        mode=asda.SubDubAutoPostMode.SCHEDULE_AT,
        schedule_at=target_utc,
    )

    diag, err = asda.process_subdub_autopost_handoff(
        db_conn,
        subdub_job_id="job_sched_at",
        requesting_user_id=123456,
    )
    assert diag["attempted"] is True
    assert diag["created_or_reused"] is True
    assert diag["state"] == "SCHEDULED"
    assert err == "scheduled"

    q = db_conn.execute(
        "SELECT * FROM autopost_publication_queue WHERE publication_id=?",
        (diag["publication_id"],),
    ).fetchone()
    assert q["schedule_at"] == target_utc


def test_subdub_adapter_idempotent_replay(db_conn, tmp_path):
    _seed_canonical_subdub_job(db_conn, tmp_path, uid=123456, internal_job_id="job_replay")
    target_utc = "2026-09-25T09:00:00Z"
    asda.register_subdub_autopost_intent(
        db_conn,
        owner_id=123456,
        subdub_job_id="job_replay",
        mode=asda.SubDubAutoPostMode.SCHEDULE_AT,
        schedule_at=target_utc,
    )

    diag1, _ = asda.process_subdub_autopost_handoff(
        db_conn,
        subdub_job_id="job_replay",
        requesting_user_id=123456,
    )

    diag2, _ = asda.process_subdub_autopost_handoff(
        db_conn,
        subdub_job_id="job_replay",
        requesting_user_id=123456,
    )

    assert diag1["publication_id"] == diag2["publication_id"]
    queue_count = db_conn.execute("SELECT COUNT(*) FROM autopost_publication_queue").fetchone()[0]
    assert queue_count == 1


def test_subdub_adapter_schedule_conflict_blocked(db_conn, tmp_path):
    _seed_canonical_subdub_job(db_conn, tmp_path, uid=123456, internal_job_id="job_conflict")
    asda.register_subdub_autopost_intent(
        db_conn,
        owner_id=123456,
        subdub_job_id="job_conflict",
        mode=asda.SubDubAutoPostMode.SCHEDULE_AT,
        schedule_at="2026-09-25T10:00:00Z",
    )

    diag1, _ = asda.process_subdub_autopost_handoff(
        db_conn,
        subdub_job_id="job_conflict",
        requesting_user_id=123456,
    )
    assert diag1["state"] == "SCHEDULED"

    # Force intent update with differing schedule timestamp
    db_conn.execute(
        "UPDATE autopost_subdub_intents SET schedule_at='2026-09-26T10:00:00Z' WHERE subdub_job_id='job_conflict'"
    )
    db_conn.commit()

    diag2, err2 = asda.process_subdub_autopost_handoff(
        db_conn,
        subdub_job_id="job_conflict",
        requesting_user_id=123456,
    )
    assert diag2["created_or_reused"] is False
    assert diag2["blocker"] == "schedule_conflict_different_timestamp"
    assert err2 == "schedule_conflict_different_timestamp"


def test_subdub_adapter_in_transaction_guard(db_conn, tmp_path):
    _seed_canonical_subdub_job(db_conn, tmp_path, uid=123456, internal_job_id="job_in_tx")

    db_conn.execute("BEGIN TRANSACTION")
    diag, err = asda.process_subdub_autopost_handoff(
        db_conn,
        subdub_job_id="job_in_tx",
        requesting_user_id=123456,
    )
    db_conn.rollback()

    assert diag["blocker"] == "caller_in_transaction"
    assert err == "caller_in_transaction"
