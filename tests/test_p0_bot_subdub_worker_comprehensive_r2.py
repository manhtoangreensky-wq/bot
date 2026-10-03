"""Comprehensive Provider-Free Focused Tests for SubDub Dedicated Worker & Settlement (R2).

Governed by owner-governed-codex, locked-focus-engineering.
Zero network calls, zero real provider calls, zero production DB mutations.
"""

import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import pytest

from services.subdub_worker_claim import (
    ensure_subdub_worker_queue_schema,
    enqueue_subdub_job,
    claim_next_subdub_job,
    complete_subdub_job,
    fail_subdub_job,
    get_subdub_worker_job,
)
from services.subdub_worker_daemon import SubDubWorkerDaemon
from services.web_subdub_settlement_service import (
    ensure_web_subdub_settlement_schema,
    derive_canonical_subdub_charge,
    execute_web_subdub_settlement,
)


@pytest.fixture
def test_db():
    """Create in-memory SQLite database initialized with system schemas."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_subdub_worker_queue_schema(conn)
    ensure_web_subdub_settlement_schema(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            credits INTEGER DEFAULT 0,
            total_spent INTEGER DEFAULT 0,
            username TEXT,
            first_name TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ledger_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE,
            user_id INTEGER,
            delta INTEGER,
            balance_after INTEGER,
            reason TEXT,
            created_at TEXT,
            reference_id TEXT,
            product_key TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    yield conn
    conn.close()


@pytest.fixture
def staged_media_file():
    """Create a temporary dummy media file."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41")
        f.flush()
        yield Path(f.name)
    try:
        Path(f.name).unlink(missing_ok=True)
    except Exception:
        pass


def test_01_worker_mode_coverage_all_four_modes(test_db, staged_media_file, tmp_path):
    """Ensure all 4 modes are dispatched without falling into MODE_NOT_IMPLEMENTED_YET."""
    upload_id = "upl_test_all_modes_123"
    owner_id = "12345678"

    # Stage upload in system_settings
    test_db.execute(
        "INSERT INTO system_settings (key, value) VALUES (?, ?)",
        (
            f"subdub_upload:{upload_id}",
            json.dumps({"upload_id": upload_id, "owner_id": owner_id, "local_path": str(staged_media_file)}),
        ),
    )
    test_db.commit()

    modes = ["subtitle_create", "subtitle_translate", "dub", "subtitle_plus_dub"]
    for m in modes:
        job = enqueue_subdub_job(
            owner_id=owner_id,
            mode=m,
            payload={
                "upload_id": upload_id,
                "target_language": "vi",
                "source_language": "en",
            },
            conn=test_db,
        )
        assert job["status"] == "queued"

    daemon = SubDubWorkerDaemon(
        artifact_dir=tmp_path,
        db_conn=test_db,
        transcriber_fn=lambda path, p: [{"text": "Hello world", "start": 0.0, "end": 2.0}],
        translator_fn=lambda segs, lang, p: [{"text": "Xin chào thế giới", "start": 0.0, "end": 2.0}],
        voice_resolver_fn=lambda uid, p: (True, "OK", 200, {"_internal_provider_voice_id": "vi-VN-HoaiMyNeural", "voice_speed": 1.0}),
        tts_fn=lambda segs, vr, p: b"RIFF....WAVEfmt ....data....fakeaudio",
        muxer_fn=lambda vpath, apath, spath, p: (b"\x00\x00\x00\x20ftypisomfakevideomuxed", "mp4"),
        probe_fn=lambda path: (True, {"duration": 2.0}),
    )

    for _ in range(4):
        claimed = daemon.process_one_job()
        assert claimed is True

    # Verify no job failed with MODE_NOT_IMPLEMENTED_YET
    rows = test_db.execute("SELECT job_id, mode, status, last_error FROM subdub_worker_jobs").fetchall()
    assert len(rows) == 4
    for r in rows:
        assert r["status"] == "completed", f"Mode {r['mode']} failed with: {r['last_error']}"


def test_02_subtitle_translate_missing_target_lang_fails_closed(test_db, staged_media_file, tmp_path):
    """subtitle_translate must fail closed if target_language is absent."""
    upload_id = "upl_test_missing_lang"
    owner_id = "12345678"
    test_db.execute(
        "INSERT INTO system_settings (key, value) VALUES (?, ?)",
        (f"subdub_upload:{upload_id}", json.dumps({"upload_id": upload_id, "owner_id": owner_id, "local_path": str(staged_media_file)})),
    )
    test_db.commit()

    enqueue_subdub_job(
        owner_id=owner_id,
        mode="subtitle_translate",
        payload={"upload_id": upload_id},  # No target_language
        conn=test_db,
    )

    daemon = SubDubWorkerDaemon(artifact_dir=tmp_path, db_conn=test_db)
    daemon.process_one_job()

    row = test_db.execute("SELECT status, last_error FROM subdub_worker_jobs LIMIT 1").fetchone()
    assert row["status"] == "failed"
    assert "MISSING_TARGET_LANGUAGE" in row["last_error"]


def test_03_dub_voice_resolution_failure_fails_closed(test_db, staged_media_file, tmp_path):
    """dub must fail closed if voice resolution fails."""
    upload_id = "upl_test_dub_voice"
    owner_id = "12345678"
    test_db.execute(
        "INSERT INTO system_settings (key, value) VALUES (?, ?)",
        (f"subdub_upload:{upload_id}", json.dumps({"upload_id": upload_id, "owner_id": owner_id, "local_path": str(staged_media_file)})),
    )
    test_db.commit()

    enqueue_subdub_job(
        owner_id=owner_id,
        mode="dub",
        payload={"upload_id": upload_id, "target_language": "vi"},
        conn=test_db,
    )

    daemon = SubDubWorkerDaemon(
        artifact_dir=tmp_path,
        db_conn=test_db,
        voice_resolver_fn=lambda uid, p: (False, "PROFILE_NOT_FOUND", 422, {}),
    )
    daemon.process_one_job()

    row = test_db.execute("SELECT status, last_error FROM subdub_worker_jobs LIMIT 1").fetchone()
    assert row["status"] == "failed"
    assert "PROFILE_NOT_FOUND" in row["last_error"]


def test_04_provider_disabled_fail_closed(test_db, staged_media_file, tmp_path, monkeypatch):
    """Without injected mock, worker must fail closed if PROVIDER_CALLS is disabled."""
    monkeypatch.setenv("WEBAPP_PROVIDER_CALLS_ENABLED", "0")
    monkeypatch.setenv("PROVIDER_CALLS_ENABLED", "0")

    upload_id = "upl_test_gate_off"
    owner_id = "12345678"
    test_db.execute(
        "INSERT INTO system_settings (key, value) VALUES (?, ?)",
        (f"subdub_upload:{upload_id}", json.dumps({"upload_id": upload_id, "owner_id": owner_id, "local_path": str(staged_media_file)})),
    )
    test_db.commit()

    enqueue_subdub_job(
        owner_id=owner_id,
        mode="subtitle_translate",
        payload={"upload_id": upload_id, "target_language": "vi"},
        conn=test_db,
    )

    daemon = SubDubWorkerDaemon(artifact_dir=tmp_path, db_conn=test_db)
    daemon.process_one_job()

    row = test_db.execute("SELECT status, last_error FROM subdub_worker_jobs LIMIT 1").fetchone()
    assert row["status"] == "failed"
    assert "PROVIDER_CALLS_DISABLED" in row["last_error"]


def test_05_cross_owner_upload_rejected(test_db, staged_media_file, tmp_path):
    """Worker must strictly reject upload belonging to a different owner."""
    upload_id = "upl_cross_owner"
    test_db.execute(
        "INSERT INTO system_settings (key, value) VALUES (?, ?)",
        (f"subdub_upload:{upload_id}", json.dumps({"upload_id": upload_id, "owner_id": "owner_A", "local_path": str(staged_media_file)})),
    )
    test_db.commit()

    enqueue_subdub_job(
        owner_id="owner_B",
        mode="subtitle_create",
        payload={"upload_id": upload_id},
        conn=test_db,
    )

    daemon = SubDubWorkerDaemon(artifact_dir=tmp_path, db_conn=test_db)
    daemon.process_one_job()

    row = test_db.execute("SELECT status, last_error FROM subdub_worker_jobs LIMIT 1").fetchone()
    assert row["status"] == "failed"
    assert "FORBIDDEN_CROSS_OWNER" in row["last_error"]


def test_06_settlement_subtitle_create_free_policy(test_db):
    """subtitle_create must settle with 0 Xu without deducting user wallet."""
    test_db.execute("INSERT INTO users (user_id, credits, total_spent) VALUES (1111, 200, 0)")
    test_db.commit()

    ok, res, code = execute_web_subdub_settlement(
        web_job_id="sdj_free_01",
        web_request_id="REQ-FREE-01",
        canonical_user_id="1111",
        subdub_mode="subtitle_create",
        output_url="https://tg.toanaas.vn/artifacts/subdub/sdj_free_01.vtt",
        validated_output_metadata={"char_count": 500, "duration_seconds": 30.0},
        conn=test_db,
    )

    assert ok is True
    assert code == 200
    assert res["status"] == "exempt_free"
    assert res["amount_xu"] == 0
    assert res["balance_after"] == 200

    u = test_db.execute("SELECT credits FROM users WHERE user_id = 1111").fetchone()
    assert u["credits"] == 200


def test_07_settlement_paid_lanes_deduct_balance(test_db):
    """Paid lanes (subtitle_translate, dub, subtitle_plus_dub) must debit correct Xu."""
    test_db.execute("INSERT INTO users (user_id, credits, total_spent) VALUES (2222, 1000, 0)")
    test_db.commit()

    # 1. subtitle_translate (500 chars * 0.1 Xu = 50 Xu, discount 5% = 47.5 -> 48 Xu)
    ok, res, code = execute_web_subdub_settlement(
        web_job_id="sdj_trans_01",
        web_request_id="REQ-TRANS-01",
        canonical_user_id="2222",
        subdub_mode="subtitle_translate",
        output_url="https://tg.toanaas.vn/artifacts/subdub/sdj_trans_01.vtt",
        validated_output_metadata={"char_count": 500},
        conn=test_db,
    )
    assert ok is True
    assert code == 200
    assert res["status"] == "settled"
    assert res["amount_xu"] > 0
    bal_after = res["balance_after"]
    assert bal_after == 1000 - res["amount_xu"]

    # 2. Duplicate settlement replay must be idempotent
    ok2, res2, code2 = execute_web_subdub_settlement(
        web_job_id="sdj_trans_01",
        web_request_id="REQ-TRANS-01",
        canonical_user_id="2222",
        subdub_mode="subtitle_translate",
        output_url="https://tg.toanaas.vn/artifacts/subdub/sdj_trans_01.vtt",
        validated_output_metadata={"char_count": 500},
        conn=test_db,
    )
    assert ok2 is True
    assert code2 == 200
    assert res2["duplicate"] is True
    assert res2["amount_xu"] == res["amount_xu"]
    # Ensure no second deduction
    u = test_db.execute("SELECT credits FROM users WHERE user_id = 2222").fetchone()
    assert u["credits"] == bal_after


def test_08_settlement_insufficient_funds_fails_closed(test_db):
    """Settlement must return 402 INSUFFICIENT_FUNDS when user balance is inadequate."""
    test_db.execute("INSERT INTO users (user_id, credits, total_spent) VALUES (3333, 5, 0)")
    test_db.commit()

    ok, res, code = execute_web_subdub_settlement(
        web_job_id="sdj_insuf_01",
        web_request_id="REQ-INSUF-01",
        canonical_user_id="3333",
        subdub_mode="dub",
        output_url="https://tg.toanaas.vn/artifacts/subdub/sdj_insuf_01.mp4",
        validated_output_metadata={"char_count": 1000},  # ~90 Xu
        conn=test_db,
    )

    assert ok is False
    assert code == 402
    assert res["error_code"] == "INSUFFICIENT_FUNDS"

    u = test_db.execute("SELECT credits FROM users WHERE user_id = 3333").fetchone()
    assert u["credits"] == 5


def test_09_settlement_exact_canonical_wire_schema_and_failures(test_db):
    """Prove exact canonical wire schema is accepted and each missing field fails closed."""
    test_db.execute("INSERT INTO users (user_id, credits, total_spent) VALUES (4444, 500, 0)")
    test_db.commit()

    base_payload = {
        "web_job_id": "sdj_wire_01",
        "web_request_id": "SDB-20261003-ABCD",
        "canonical_user_id": "4444",
        "subdub_mode": "dub",
        "output_url": "https://tg.toanaas.vn/artifacts/subdub/sdj_wire_01.mp4",
        "validated_output_metadata": {"character_count": 500, "duration": 30.0},
        "idempotency_key": "subdub_settle:sdj_wire_01:dub",
    }

    # 1. Missing web_job_id
    p = dict(base_payload)
    p["web_job_id"] = ""
    ok, res, code = execute_web_subdub_settlement(**p, conn=test_db)
    assert ok is False and code == 400 and res["error_code"] == "WEB_JOB_ID_REQUIRED"

    # 2. Missing web_request_id
    p = dict(base_payload)
    p["web_request_id"] = ""
    ok, res, code = execute_web_subdub_settlement(**p, conn=test_db)
    assert ok is False and code == 400 and res["error_code"] == "WEB_REQUEST_ID_REQUIRED"

    # 3. Missing canonical_user_id
    p = dict(base_payload)
    p["canonical_user_id"] = ""
    ok, res, code = execute_web_subdub_settlement(**p, conn=test_db)
    assert ok is False and code == 400 and res["error_code"] == "CANONICAL_USER_ID_REQUIRED"

    # 4. Invalid mode
    p = dict(base_payload)
    p["subdub_mode"] = "invalid_mode_xyz"
    ok, res, code = execute_web_subdub_settlement(**p, conn=test_db)
    assert ok is False and code == 400 and res["error_code"] == "INVALID_SUBDUB_MODE"

    # 5. Missing output_url
    p = dict(base_payload)
    p["output_url"] = ""
    ok, res, code = execute_web_subdub_settlement(**p, conn=test_db)
    assert ok is False and code == 400 and res["error_code"] == "OUTPUT_URL_REQUIRED"

    # 6. Missing validated_output_metadata
    p = dict(base_payload)
    p["validated_output_metadata"] = None
    ok, res, code = execute_web_subdub_settlement(**p, conn=test_db)
    assert ok is False and code == 400 and res["error_code"] == "VALIDATED_OUTPUT_METADATA_REQUIRED"

    # 7. Valid full payload succeeds
    ok, res, code = execute_web_subdub_settlement(**base_payload, conn=test_db)
    assert ok is True and code == 200 and res["status"] == "settled"
    assert res["idempotency_key"] == "subdub_settle:sdj_wire_01:dub"

    # 8. Duplicate idempotency returns duplicate=True and does not debit again
    ok2, res2, code2 = execute_web_subdub_settlement(**base_payload, conn=test_db)
    assert ok2 is True and code2 == 200 and res2["duplicate"] is True
