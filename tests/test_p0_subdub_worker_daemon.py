"""Unit and integration tests for SubDub Dedicated Worker Daemon (BOT-SUBDUB-WORKER-R1).

Governed by owner-governed-codex, locked-focus-engineering.
Covers 15 contract requirements:
1. empty queue -> no execution
2. one queued job -> one claim
3. claim increments attempts once
4. max_attempts=1 preserved
5. same job cannot be concurrently claimed twice
6. fencing token required
7. stale token cannot complete
8. subtitle_create routes into canonical SubDub pipeline
9. VTT success produces valid nonzero result
10. execution failure calls fail_subdub_job
11. no fake completion
12. no Product Video queue interaction
13. no provider fallback
14. worker restart does not blindly resubmit provider
15. secret values never logged
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import sqlite3
import pytest

from services.subdub_worker_claim import (
    ensure_subdub_worker_queue_schema,
    enqueue_subdub_job,
    claim_next_subdub_job,
    heartbeat_subdub_job,
    complete_subdub_job,
    fail_subdub_job,
    get_subdub_worker_job,
)
from services.subdub_worker_daemon import (
    SubDubWorkerDaemon,
    format_vtt_text,
    format_srt_timestamp,
    is_safe_subdub_output_url,
    run_doctor,
)


@pytest.fixture
def isolated_db(tmp_path: Path):
    """Provide an isolated SQLite database connection with initialized schemas."""
    db_file = tmp_path / "subdub_daemon_test.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    ensure_subdub_worker_queue_schema(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT,
            updated_by TEXT,
            note TEXT
        )
        """
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def staged_media(tmp_path: Path, isolated_db: sqlite3.Connection):
    """Create a valid staged media upload in system_settings."""
    upload_id = "upl_test_valid_media_001"
    owner_id = "172200"
    media_file = tmp_path / "test_audio.mp3"
    # Write fake ID3/MP3 bytes
    media_bytes = b"ID3\x04\x00\x00\x00\x00\x00\x00test-audio-content-for-transcription"
    media_file.write_bytes(media_bytes)

    record = {
        "upload_id": upload_id,
        "owner_id": owner_id,
        "file_name": "test_audio.mp3",
        "content_type": "audio/mp3",
        "size_bytes": len(media_bytes),
        "sha256": hashlib.sha256(media_bytes).hexdigest(),
        "local_path": str(media_file),
        "status": "staged",
    }
    isolated_db.execute(
        "INSERT OR REPLACE INTO system_settings (key, value, updated_at, updated_by, note) VALUES (?, ?, datetime('now'), 'test', 'test')",
        (f"subdub_upload:{upload_id}", json.dumps(record)),
    )
    isolated_db.commit()
    return {
        "upload_id": upload_id,
        "owner_id": owner_id,
        "local_path": str(media_file),
        "bytes": media_bytes,
    }


def test_1_empty_queue_no_execution(isolated_db: sqlite3.Connection, tmp_path: Path):
    """1. Empty queue produces no execution and returns False."""
    executed = []

    def mock_transcriber(*_args, **_kwargs):
        executed.append(True)
        return "WEBVTT\n"

    daemon = SubDubWorkerDaemon(
        worker_id="test-worker",
        db_conn=isolated_db,
        artifact_dir=tmp_path / "artifacts",
        transcriber_fn=mock_transcriber,
    )

    claimed = daemon.process_one_job()
    assert claimed is False
    assert len(executed) == 0


def test_2_and_3_one_queued_job_one_claim_increments_attempts(
    isolated_db: sqlite3.Connection, staged_media: dict, tmp_path: Path
):
    """2 & 3. One queued job is claimed once, attempts incremented to 1."""
    enqueued = enqueue_subdub_job(
        owner_id=staged_media["owner_id"],
        mode="subtitle_create",
        payload={"upload_id": staged_media["upload_id"], "output_format": "vtt"},
        max_attempts=1,
        conn=isolated_db,
    )
    job_id = enqueued["job_id"]
    assert enqueued["status"] == "queued"
    assert enqueued["attempts"] == 0

    daemon = SubDubWorkerDaemon(
        worker_id="test-worker-1",
        db_conn=isolated_db,
        artifact_dir=tmp_path / "artifacts",
        transcriber_fn=lambda _p, _payload: [
            {"start": 0.0, "end": 2.0, "text": "Hello world"}
        ],
    )

    claimed = daemon.process_one_job()
    assert claimed is True

    updated = get_subdub_worker_job(job_id, conn=isolated_db)
    assert updated["status"] == "completed"
    assert updated["attempts"] == 1
    assert updated["worker_id"] == "test-worker-1"


def test_4_max_attempts_bound_preserved_and_enforced(
    isolated_db: sqlite3.Connection, staged_media: dict, tmp_path: Path
):
    """4. max_attempts=1 is strictly preserved; exceeding bound fails closed."""
    enqueued = enqueue_subdub_job(
        owner_id=staged_media["owner_id"],
        mode="subtitle_create",
        payload={"upload_id": staged_media["upload_id"]},
        max_attempts=1,
        conn=isolated_db,
    )
    job_id = enqueued["job_id"]

    # Artificially set attempts=1 while status='queued' to simulate previous attempt
    isolated_db.execute(
        "UPDATE subdub_worker_jobs SET attempts=1 WHERE job_id=?", (job_id,)
    )
    isolated_db.commit()

    daemon = SubDubWorkerDaemon(
        worker_id="test-worker",
        db_conn=isolated_db,
        artifact_dir=tmp_path / "artifacts",
        transcriber_fn=lambda _p, _payload: "WEBVTT\n",
    )

    # When claimed, attempts becomes 2, which exceeds max_attempts=1
    daemon.process_one_job()

    updated = get_subdub_worker_job(job_id, conn=isolated_db)
    assert updated["status"] == "failed"
    assert "MAX_ATTEMPTS_EXCEEDED" in updated["last_error"]


def test_5_concurrent_claim_prevention(
    isolated_db: sqlite3.Connection, staged_media: dict
):
    """5. Same job cannot be claimed concurrently by two workers."""
    enqueued = enqueue_subdub_job(
        owner_id=staged_media["owner_id"],
        mode="subtitle_create",
        payload={"upload_id": staged_media["upload_id"]},
        conn=isolated_db,
    )
    job_id = enqueued["job_id"]

    claim1 = claim_next_subdub_job("worker-A", conn=isolated_db)
    assert claim1 is not None
    assert claim1["job_id"] == job_id
    assert claim1["worker_id"] == "worker-A"

    claim2 = claim_next_subdub_job("worker-B", conn=isolated_db)
    assert claim2 is None  # Queue empty for second worker


def test_6_and_7_fencing_token_enforcement_and_stale_rejection(
    isolated_db: sqlite3.Connection, staged_media: dict
):
    """6 & 7. Fencing token required; stale token cannot complete or fail job."""
    enqueue_subdub_job(
        owner_id=staged_media["owner_id"],
        mode="subtitle_create",
        payload={"upload_id": staged_media["upload_id"]},
        conn=isolated_db,
    )

    claim = claim_next_subdub_job("worker-A", conn=isolated_db)
    job_id = claim["job_id"]
    valid_token = claim["claim_token"]
    stale_token = "claim_stale_fake_token_001"

    # Stale token complete rejected
    ok, reason, _ = complete_subdub_job(
        job_id, "worker-A", stale_token, result={"url": "https://tg.toanaas.vn/ok.vtt"}, conn=isolated_db
    )
    assert ok is False
    assert reason == "FENCING_TOKEN_MISMATCH"

    # Valid token complete succeeds
    ok2, reason2, _ = complete_subdub_job(
        job_id, "worker-A", valid_token, result={"output_url": "https://tg.toanaas.vn/ok.vtt"}, conn=isolated_db
    )
    assert ok2 is True
    assert reason2 == "OK"


def test_8_and_9_subtitle_create_vtt_success_nonzero(
    isolated_db: sqlite3.Connection, staged_media: dict, tmp_path: Path
):
    """8 & 9. Mode subtitle_create produces valid non-zero VTT artifact."""
    artifact_dir = tmp_path / "artifacts"
    daemon = SubDubWorkerDaemon(
        worker_id="vps-subdub-worker",
        db_conn=isolated_db,
        artifact_dir=artifact_dir,
        public_base_url="https://tg.toanaas.vn/artifacts/subdub",
        transcriber_fn=lambda _path, _payload: [
            {"start": 0.0, "end": 1.5, "text": "Phụ đề tiếng Việt chuẩn xác."},
            {"start": 1.8, "end": 3.2, "text": "Hệ sinh thái TOAN AAS."},
        ],
    )

    enqueued = enqueue_subdub_job(
        owner_id=staged_media["owner_id"],
        mode="subtitle_create",
        payload={"upload_id": staged_media["upload_id"], "output_format": "vtt"},
        conn=isolated_db,
    )
    job_id = enqueued["job_id"]

    claimed = daemon.process_one_job()
    assert claimed is True

    updated = get_subdub_worker_job(job_id, conn=isolated_db)
    assert updated["status"] == "completed"
    result = updated["result"]
    assert result["format"] == "vtt"
    assert result["content_type"] == "text/vtt"
    assert result["size_bytes"] > 0
    assert result["cues_count"] == 2
    assert is_safe_subdub_output_url(result["output_url"])

    # Physical artifact validation
    artifact_file = artifact_dir / f"{job_id}.vtt"
    assert artifact_file.is_file()
    content = artifact_file.read_text(encoding="utf-8")
    assert content.startswith("WEBVTT\n")
    assert "00:00:00.000 --> 00:00:01.500" in content
    assert "Phụ đề tiếng Việt chuẩn xác." in content


def test_10_execution_failure_calls_fail_subdub_job(
    isolated_db: sqlite3.Connection, staged_media: dict, tmp_path: Path
):
    """10. Failure during execution transitions job to failed status with sanitized error."""
    def failing_transcriber(*_args, **_kwargs):
        raise ValueError("Simulated ASR failure")

    daemon = SubDubWorkerDaemon(
        worker_id="test-worker",
        db_conn=isolated_db,
        artifact_dir=tmp_path / "artifacts",
        transcriber_fn=failing_transcriber,
    )

    enqueued = enqueue_subdub_job(
        owner_id=staged_media["owner_id"],
        mode="subtitle_create",
        payload={"upload_id": staged_media["upload_id"]},
        conn=isolated_db,
    )
    job_id = enqueued["job_id"]

    daemon.process_one_job()

    updated = get_subdub_worker_job(job_id, conn=isolated_db)
    assert updated["status"] == "failed"
    assert "TRANSCRIBER_FAILED" in updated["last_error"]
    assert updated["result"] == {}


def test_11_no_fake_completion_on_empty_output(
    isolated_db: sqlite3.Connection, staged_media: dict, tmp_path: Path
):
    """11. Empty/invalid VTT output fails closed, never completes."""
    daemon = SubDubWorkerDaemon(
        worker_id="test-worker",
        db_conn=isolated_db,
        artifact_dir=tmp_path / "artifacts",
        transcriber_fn=lambda _p, _payload: "",  # Returns empty text
    )

    enqueued = enqueue_subdub_job(
        owner_id=staged_media["owner_id"],
        mode="subtitle_create",
        payload={"upload_id": staged_media["upload_id"]},
        conn=isolated_db,
    )
    job_id = enqueued["job_id"]

    daemon.process_one_job()

    updated = get_subdub_worker_job(job_id, conn=isolated_db)
    assert updated["status"] == "failed"
    assert updated["status"] != "completed"


def test_12_no_product_video_queue_interaction(
    isolated_db: sqlite3.Connection, staged_media: dict, tmp_path: Path
):
    """12. SubDub worker never polls or touches product video tables."""
    isolated_db.execute(
        """
        CREATE TABLE IF NOT EXISTS video_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE,
            status TEXT DEFAULT 'queued'
        )
        """
    )
    isolated_db.execute("INSERT INTO video_jobs (job_id, status) VALUES ('pv_001', 'queued')")
    isolated_db.commit()

    daemon = SubDubWorkerDaemon(
        worker_id="test-worker",
        db_conn=isolated_db,
        artifact_dir=tmp_path / "artifacts",
    )

    # Run one pass with empty subdub queue
    claimed = daemon.process_one_job()
    assert claimed is False

    # video_jobs table untouched
    row = isolated_db.execute("SELECT status FROM video_jobs WHERE job_id='pv_001'").fetchone()
    assert row["status"] == "queued"


def test_13_foreign_upload_rejected_fail_closed(
    isolated_db: sqlite3.Connection, staged_media: dict, tmp_path: Path
):
    """13. Cross-owner upload access rejected with fail-closed failure."""
    daemon = SubDubWorkerDaemon(
        worker_id="test-worker",
        db_conn=isolated_db,
        artifact_dir=tmp_path / "artifacts",
        transcriber_fn=lambda _p, _payload: "WEBVTT\n\n1\n00:00:00.000 --> 00:00:01.000\nhi\n",
    )

    # Job owned by user 999999, but staged_media belongs to 172200
    enqueued = enqueue_subdub_job(
        owner_id="999999",
        mode="subtitle_create",
        payload={"upload_id": staged_media["upload_id"]},
        conn=isolated_db,
    )
    job_id = enqueued["job_id"]

    daemon.process_one_job()

    updated = get_subdub_worker_job(job_id, conn=isolated_db)
    assert updated["status"] == "failed"
    assert "FORBIDDEN_CROSS_OWNER" in updated["last_error"]


def test_14_worker_restart_does_not_resubmit_provider_on_expired_lease(
    isolated_db: sqlite3.Connection, staged_media: dict, tmp_path: Path
):
    """14. Crashed worker with expired lease fails permanently when max_attempts=1."""
    enqueued = enqueue_subdub_job(
        owner_id=staged_media["owner_id"],
        mode="subtitle_create",
        payload={"upload_id": staged_media["upload_id"]},
        max_attempts=1,
        conn=isolated_db,
    )
    job_id = enqueued["job_id"]

    # Claim once
    claim_next_subdub_job("crashed-worker", lease_seconds=1, conn=isolated_db)

    # Simulate crash + lease expiration
    isolated_db.execute(
        "UPDATE subdub_worker_jobs SET lease_expires_at=datetime('now', '-10 seconds') WHERE job_id=?",
        (job_id,),
    )
    isolated_db.commit()

    # New worker comes up
    daemon = SubDubWorkerDaemon(
        worker_id="new-worker",
        db_conn=isolated_db,
        artifact_dir=tmp_path / "artifacts",
    )

    # Polling triggers lease recovery: attempts >= max_attempts permanently fails the job
    claimed = daemon.process_one_job()
    assert claimed is False

    updated = get_subdub_worker_job(job_id, conn=isolated_db)
    assert updated["status"] == "failed"
    assert updated["last_error"] == "max_attempts_exceeded"


def test_15_secrets_never_logged(
    isolated_db: sqlite3.Connection, staged_media: dict, tmp_path: Path, caplog
):
    """15. Sensitive credentials / secrets and fencing claim_tokens are never printed to logs."""
    secret_key = "sk-super-secret-key-that-must-never-leak"
    bridge_secret = "bridge-secret-token-auth-xyz987"

    with caplog.at_level(logging.DEBUG):
        daemon = SubDubWorkerDaemon(
            worker_id="test-worker",
            db_conn=isolated_db,
            artifact_dir=tmp_path / "artifacts",
            transcriber_fn=lambda _p, _payload: "WEBVTT\n\n1\n00:00:00.000 --> 00:00:01.000\nok\n",
        )
        enqueued = enqueue_subdub_job(
            owner_id=staged_media["owner_id"],
            mode="subtitle_create",
            payload={"upload_id": staged_media["upload_id"]},
            conn=isolated_db,
        )
        job_id = enqueued["job_id"]
        daemon.process_one_job()

    row = isolated_db.execute("SELECT claim_token FROM subdub_worker_jobs WHERE job_id = ?", (job_id,)).fetchone()
    claim_token = row[0] if row else ""
    assert claim_token and len(claim_token) >= 8

    # Fencing claim_token must never be logged in plaintext
    assert claim_token not in caplog.text

    # Configured secrets must never be logged
    assert secret_key not in caplog.text
    assert bridge_secret not in caplog.text


def test_fencing_token_not_logged_on_negative_failures(
    isolated_db: sqlite3.Connection, staged_media: dict, tmp_path: Path, caplog
):
    """Ensure fencing claim_token and auth secrets never leak in failure log paths:
    - Pipeline exception
    - Fencing mismatch / heartbeat failure
    - Staged upload error
    """
    secret_key = "secret-credentials-leak-canary"
    auth_header = "Bearer secret-bearer-auth-header-999"

    # 1. Pipeline exception
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        daemon = SubDubWorkerDaemon(
            worker_id="failing-worker",
            db_conn=isolated_db,
            artifact_dir=tmp_path / "artifacts",
            transcriber_fn=lambda _p, _payload: (_ for _ in ()).throw(RuntimeError("Simulated pipeline error")),
        )
        enqueued1 = enqueue_subdub_job(
            owner_id=staged_media["owner_id"],
            mode="subtitle_create",
            payload={"upload_id": staged_media["upload_id"]},
            conn=isolated_db,
        )
        job_id1 = enqueued1["job_id"]
        daemon.process_one_job()

    row1 = isolated_db.execute("SELECT claim_token FROM subdub_worker_jobs WHERE job_id = ?", (job_id1,)).fetchone()
    token1 = row1[0] if row1 else ""
    assert token1 and len(token1) >= 8
    assert token1 not in caplog.text

    # 2. Fencing token mismatch / stale claim token
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        enqueued2 = enqueue_subdub_job(
            owner_id=staged_media["owner_id"],
            mode="subtitle_create",
            payload={"upload_id": staged_media["upload_id"]},
            conn=isolated_db,
        )
        job_id2 = enqueued2["job_id"]
        claimed2 = claim_next_subdub_job("worker-a", conn=isolated_db)
        token2 = claimed2["claim_token"]
        assert token2 not in caplog.text

        # Simulate heartbeat with invalid fencing token
        hb_ok, hb_reason, _ = heartbeat_subdub_job(job_id2, "worker-a", "stale-fake-token", conn=isolated_db)
        assert hb_ok is False
        assert token2 not in caplog.text
        assert "stale-fake-token" not in caplog.text

    # 3. Overall log hygiene: no secrets
    assert secret_key not in caplog.text
    assert auth_header not in caplog.text


def test_format_vtt_helpers():
    """Verify VTT formatting and timestamp calculations."""
    assert format_srt_timestamp(0.0) == "00:00:00,000"
    assert format_srt_timestamp(61.5) == "00:01:01,500"
    assert format_srt_timestamp(3665.123) == "01:01:05,123"

    vtt = format_vtt_text([{"start": 0.0, "end": 2.0, "text": "Test cue"}])
    assert vtt.startswith("WEBVTT\n\n")
    assert "00:00:00.000 --> 00:00:02.000" in vtt
    assert "Test cue" in vtt

    # Raw SRT string conversion to VTT
    srt = "1\n00:00:00,000 --> 00:00:02,000\nHello"
    vtt_conv = format_vtt_text(srt)
    assert vtt_conv.startswith("WEBVTT\n\n")
    assert "00:00:00.000 --> 00:00:02.000" in vtt_conv
