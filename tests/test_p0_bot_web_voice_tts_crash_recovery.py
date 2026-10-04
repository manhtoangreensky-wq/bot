"""Verification tests for Web Voice TTS crash recovery and idempotent debit settlement.

Invariants verified:
- PROCESSING_SETTLING_RECOVERY_PATH_PRESENT = YES
- FAIL_CLOSED_RECOVERY_REQUIRED = YES
- AUTO_PROVIDER_REEXECUTION_ALLOWED = NO
- AUTO_SECOND_DEBIT_ALLOWED = NO
- RECOVERY_SECOND_PROVIDER_EXECUTION_COUNT = 0
- RECOVERY_SECOND_WALLET_DEBIT_COUNT = 0
- WALLET_IDEMPOTENT_REPLAY_ACTIVE = YES
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import sqlite3
import time
import uuid

import pytest
from starlette.testclient import TestClient

import bot
from services.admin_wallet_service import compute_internal_admin_wallet_signature
from services.web_voice_tts_runtime_service import (
    claim_web_voice_tts_job_for_execution,
    ensure_web_voice_tts_schema,
    get_web_voice_tts_job,
    update_web_voice_tts_job_status,
)

TEST_SECRET = "test_internal_secret_voice_tts_crash_recovery_9999"
TEST_TOKEN = "test_internal_token_voice_tts_crash_recovery"


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", TEST_SECRET)
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("INTERNAL_ADMIN_WALLET_SHARED_SECRET", TEST_SECRET)
    monkeypatch.setenv("INTERNAL_ADMIN_WALLET_BEARER_TOKEN", TEST_TOKEN)

    test_db = str(tmp_path / "test_bot_voice_tts_crash_recovery.db")
    monkeypatch.setenv("DB_FILE", test_db)
    monkeypatch.setattr(bot, "DB_FILE", test_db)
    monkeypatch.setenv("VOICE_ASSET_STORAGE_DIR", str(tmp_path / "voice_assets"))
    monkeypatch.setattr(bot, "TRIAL_BONUS_ENABLED", False)

    conn = sqlite3.connect(test_db)
    bot.init_db()
    ensure_web_voice_tts_schema(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_voice_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            profile_name TEXT NOT NULL,
            provider_voice_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()


def _sign(method: str, path: str, body: bytes = b"", actor_id: str = "7126457028") -> dict[str, str]:
    now_ts = str(int(time.time()))
    req_id = f"req_{uuid.uuid4().hex[:12]}"
    sig = compute_internal_admin_wallet_signature(
        secret=TEST_SECRET,
        timestamp=now_ts,
        request_id=req_id,
        method=method,
        path=path,
        body_bytes=body,
        actor_id=actor_id,
    )
    return {
        "authorization": f"Bearer {TEST_TOKEN}",
        "x-toan-aas-signature": sig,
        "x-toan-aas-timestamp": now_ts,
        "x-toan-aas-request-id": req_id,
        "x-toan-aas-actor-id": actor_id,
    }


def test_spend_fixed_credit_idempotent_info_replay_and_atomic_debit():
    """Direct unit verification of spend_fixed_credit_idempotent_info."""
    uid = 5001
    bot.get_user(uid)  # create user in DB
    bot.add_credit(uid, 100, event_type="test_setup")

    ref_id = f"voice_tts_settle:{uid}:job_test_123"

    # 1. First debit: should succeed, mutate balance, idempotent_replay=False
    r1 = bot.spend_fixed_credit_idempotent_info(uid, 20, "web_voice_tts", ref_id=ref_id)
    assert r1["ok"] is True
    assert r1["idempotent_replay"] is False
    assert r1["balance_after"] == 80
    assert r1["final_cost"] == 20

    # Verify user table balance in DB
    conn = bot.db_connect()
    c = conn.cursor()
    c.execute("SELECT credits FROM users WHERE user_id = ?", (str(uid),))
    row = c.fetchone()
    assert row[0] == 80

    # Verify credit_events has exactly 1 entry for this ref_id
    c.execute("SELECT COUNT(*) FROM credit_events WHERE user_id = ? AND ref_id = ?", (str(uid), ref_id))
    assert c.fetchone()[0] == 1
    conn.close()

    # 2. Second debit with identical ref_id: must return idempotent_replay=True, ZERO balance mutation
    r2 = bot.spend_fixed_credit_idempotent_info(uid, 20, "web_voice_tts", ref_id=ref_id)
    assert r2["ok"] is True
    assert r2["idempotent_replay"] is True
    assert r2["balance_after"] == 80
    assert r2["final_cost"] == 20

    # Verify user table balance still 80
    conn = bot.db_connect()
    c = conn.cursor()
    c.execute("SELECT credits FROM users WHERE user_id = ?", (str(uid),))
    assert c.fetchone()[0] == 80

    # Verify credit_events STILL has exactly 1 entry (RECOVERY_SECOND_WALLET_DEBIT_COUNT = 0)
    c.execute("SELECT COUNT(*) FROM credit_events WHERE user_id = ? AND ref_id = ?", (str(uid), ref_id))
    assert c.fetchone()[0] == 1
    conn.close()

    # 3. Insufficient balance test
    r3 = bot.spend_fixed_credit_idempotent_info(uid, 500, "web_voice_tts", ref_id=f"voice_tts_settle:{uid}:job_test_over")
    assert r3["ok"] is False
    assert r3["error_code"] == "INSUFFICIENT_FUNDS"
    assert r3["idempotent_replay"] is False


def test_claim_web_voice_tts_job_allows_processing_settling_recovery():
    """Verify claim_web_voice_tts_job_for_execution supports PROCESSING_SETTLING_RECOVERY_PATH_PRESENT=YES."""
    uid = 6001
    job_id = f"job_claim_rec_{uuid.uuid4().hex[:6]}"

    conn = bot.db_connect()
    conn.execute(
        """
        INSERT INTO web_voice_tts_bot_jobs (
            job_id, idempotency_key, web_request_id, user_id,
            voice_source, script, voice_profile_id, speed, volume_percent,
            language, status, status_reason, quote_xu, charged_xu, payload_hash,
            settlement_status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'saved', 'Kịch bản test claim', 10, '1.0', 100, 'vi', 'processing', 'SETTLEMENT_IN_PROGRESS', 5, 0, 'dummy', 'settling', datetime('now'), datetime('now'))
        """,
        (job_id, f"{uid}:{job_id}", f"req_{job_id}", uid),
    )
    conn.commit()

    # Claim for execution should succeed because status='processing' and settlement_status='settling'
    claimed, job = claim_web_voice_tts_job_for_execution(job_id, uid, conn=conn)
    assert claimed is True
    assert job["status"] == "processing"
    assert job["status_reason"] == "RECOVERING_SETTLEMENT"
    assert job["settlement_status"] == "settling"

    # Immediate second claim should be rejected (prevent duplicate concurrent recovery workers)
    claimed2, _ = claim_web_voice_tts_job_for_execution(job_id, uid, conn=conn)
    assert claimed2 is False
    conn.close()


def test_crash_recovery_with_prior_debit_completes_without_second_provider_or_second_debit(monkeypatch, tmp_path):
    """Crash scenario: audio was written to disk and wallet was debited, but process crashed before completion write.

    Recovery must:
    - Reuse existing audio on disk (RECOVERY_SECOND_PROVIDER_EXECUTION_COUNT = 0).
    - Idempotently replay wallet debit (RECOVERY_SECOND_WALLET_DEBIT_COUNT = 0).
    - Complete job successfully (status='completed', settlement_status='settled').
    """
    client = TestClient(bot.fastapi_app)
    uid = 7001
    bot.get_user(uid)
    bot.add_credit(uid, 50, event_type="initial_deposit")  # Balance = 50

    fake_profile = {
        "id": 88,
        "user_id": uid,
        "name": "Giọng nhân vật 88",
        "provider": "minimax",
        "provider_voice_id": "minimax_v1_custom_88",
    }
    monkeypatch.setattr(bot, "get_user_voice_profile", lambda u, p: fake_profile if u == uid and p == 88 else None)
    monkeypatch.setattr(bot, "is_admin_user", lambda u: False)

    job_id = f"job_crash_rec_{uuid.uuid4().hex[:6]}"
    settle_key = f"voice_tts_settle:{uid}:{job_id}"

    # Setup artifact file on disk
    artifact_file = tmp_path / "voice_assets" / f"web_voice_tts_{uid}_{job_id}.mp3"
    artifact_file.parent.mkdir(parents=True, exist_ok=True)
    audio_content = b"RECOVERED_AUDIO_STREAM_DATA_ABCXYZ"
    artifact_file.write_bytes(audio_content)
    art_len = len(audio_content)

    # Simulate crash state:
    # 1. User wallet was debited: 50 -> 45
    r_debit = bot.spend_fixed_credit_idempotent_info(uid, 5, "web_voice_tts", ref_id=settle_key)
    assert r_debit["ok"] is True
    assert r_debit["balance_after"] == 45

    # 2. Job was in 'processing' + 'settling'
    conn = bot.db_connect()
    conn.execute(
        """
        INSERT INTO web_voice_tts_bot_jobs (
            job_id, idempotency_key, web_request_id, user_id,
            voice_source, script, voice_profile_id, speed, volume_percent,
            language, status, status_reason, quote_xu, charged_xu, payload_hash,
            artifact_path, artifact_bytes, settlement_status, settlement_idempotency_key,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'saved', 'Kịch bản crash recovery', 88, '1.0', 100, 'vi',
                  'processing', 'SETTLEMENT_IN_PROGRESS', 5, 0, 'dummy',
                  ?, ?, 'settling', ?, datetime('now'), datetime('now'))
        """,
        (job_id, f"{uid}:{job_id}", f"req_{job_id}", uid, str(artifact_file), art_len, settle_key),
    )
    conn.commit()
    conn.close()

    # Track provider calls: MUST NOT be called!
    provider_calls = 0

    async def mock_process_voice_tts(**kwargs):
        nonlocal provider_calls
        provider_calls += 1
        return None

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_voice_tts", mock_process_voice_tts)

    # Perform confirm request to trigger crash recovery
    confirm_path = f"/internal/v1/web-voice-tts/jobs/{job_id}/confirm"
    headers = _sign("POST", confirm_path, actor_id=str(uid))
    resp = client.post(confirm_path, headers=headers)

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["ok"] is True
    assert body["job"]["status"] == "completed"
    assert body["job"]["settlement_status"] == "settled"
    assert body["job"]["charged_xu"] == 5

    # Invariant: RECOVERY_SECOND_PROVIDER_EXECUTION_COUNT = 0
    assert provider_calls == 0, f"Provider execution count must be 0 on recovery, got {provider_calls}"

    # Invariant: RECOVERY_SECOND_WALLET_DEBIT_COUNT = 0 (Balance stays 45)
    conn = bot.db_connect()
    c = conn.cursor()
    c.execute("SELECT credits FROM users WHERE user_id = ?", (str(uid),))
    assert c.fetchone()[0] == 45
    c.execute("SELECT COUNT(*) FROM credit_events WHERE user_id = ? AND ref_id = ?", (str(uid), settle_key))
    assert c.fetchone()[0] == 1
    conn.close()

    # Verify public artifact is accessible
    art_path = f"/internal/v1/web-voice-tts/jobs/{job_id}/artifact"
    art_headers = _sign("GET", art_path, actor_id=str(uid))
    art_resp = client.get(art_path, headers=art_headers)
    assert art_resp.status_code == 200
    assert art_resp.content == audio_content


def test_crash_recovery_without_prior_debit_settles_and_completes(monkeypatch, tmp_path):
    """Crash scenario: audio was written to disk, job was 'settling', but crash occurred BEFORE wallet debit.

    Recovery must:
    - Reuse existing audio on disk (provider_calls = 0).
    - Debit wallet exactly once (50 -> 45).
    - Complete job successfully.
    """
    client = TestClient(bot.fastapi_app)
    uid = 7002
    bot.get_user(uid)
    bot.add_credit(uid, 50, event_type="initial_deposit")  # Balance = 50

    fake_profile = {
        "id": 89,
        "user_id": uid,
        "name": "Giọng nhân vật 89",
        "provider": "minimax",
        "provider_voice_id": "minimax_v1_custom_89",
    }
    monkeypatch.setattr(bot, "get_user_voice_profile", lambda u, p: fake_profile if u == uid and p == 89 else None)
    monkeypatch.setattr(bot, "is_admin_user", lambda u: False)

    job_id = f"job_crash_no_debit_{uuid.uuid4().hex[:6]}"
    settle_key = f"voice_tts_settle:{uid}:{job_id}"

    # Setup artifact file on disk
    artifact_file = tmp_path / "voice_assets" / f"web_voice_tts_{uid}_{job_id}.mp3"
    artifact_file.parent.mkdir(parents=True, exist_ok=True)
    audio_content = b"AUDIO_DATA_CRASH_BEFORE_DEBIT"
    artifact_file.write_bytes(audio_content)
    art_len = len(audio_content)

    # Job in 'processing' + 'settling', but wallet NOT debited yet
    conn = bot.db_connect()
    conn.execute(
        """
        INSERT INTO web_voice_tts_bot_jobs (
            job_id, idempotency_key, web_request_id, user_id,
            voice_source, script, voice_profile_id, speed, volume_percent,
            language, status, status_reason, quote_xu, charged_xu, payload_hash,
            artifact_path, artifact_bytes, settlement_status, settlement_idempotency_key,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'saved', 'Kịch bản crash before debit', 89, '1.0', 100, 'vi',
                  'processing', 'SETTLEMENT_IN_PROGRESS', 5, 0, 'dummy',
                  ?, ?, 'settling', ?, datetime('now'), datetime('now'))
        """,
        (job_id, f"{uid}:{job_id}", f"req_{job_id}", uid, str(artifact_file), art_len, settle_key),
    )
    conn.commit()
    conn.close()

    provider_calls = 0

    async def mock_process_voice_tts(**kwargs):
        nonlocal provider_calls
        provider_calls += 1
        return None

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_voice_tts", mock_process_voice_tts)

    confirm_path = f"/internal/v1/web-voice-tts/jobs/{job_id}/confirm"
    headers = _sign("POST", confirm_path, actor_id=str(uid))
    resp = client.post(confirm_path, headers=headers)

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["job"]["status"] == "completed"
    assert resp.json()["job"]["settlement_status"] == "settled"

    # Zero provider calls
    assert provider_calls == 0

    # Debited exactly once (50 -> 45)
    conn = bot.db_connect()
    c = conn.cursor()
    c.execute("SELECT credits FROM users WHERE user_id = ?", (str(uid),))
    assert c.fetchone()[0] == 45
    c.execute("SELECT COUNT(*) FROM credit_events WHERE user_id = ? AND ref_id = ?", (str(uid), settle_key))
    assert c.fetchone()[0] == 1
    conn.close()


def test_crash_recovery_fail_closed_on_missing_artifact(monkeypatch, tmp_path):
    """FAIL_CLOSED_RECOVERY_REQUIRED: If artifact file is missing from disk during recovery.

    Must:
    - Return HTTP 500 SETTLEMENT_RECOVERY_ARTIFACT_INCONSISTENT.
    - AUTO_PROVIDER_REEXECUTION_ALLOWED = NO (provider_calls = 0).
    - AUTO_SECOND_DEBIT_ALLOWED = NO (no wallet debit).
    - Mark job as failed.
    """
    client = TestClient(bot.fastapi_app)
    uid = 7003
    bot.get_user(uid)
    bot.add_credit(uid, 50, event_type="initial_deposit")

    fake_profile = {
        "id": 90,
        "user_id": uid,
        "name": "Giọng nhân vật 90",
        "provider": "minimax",
        "provider_voice_id": "minimax_v1_custom_90",
    }
    monkeypatch.setattr(bot, "get_user_voice_profile", lambda u, p: fake_profile if u == uid and p == 90 else None)
    monkeypatch.setattr(bot, "is_admin_user", lambda u: False)

    job_id = f"job_crash_missing_{uuid.uuid4().hex[:6]}"
    settle_key = f"voice_tts_settle:{uid}:{job_id}"
    missing_path = str(tmp_path / "voice_assets" / "non_existent_audio.mp3")

    conn = bot.db_connect()
    conn.execute(
        """
        INSERT INTO web_voice_tts_bot_jobs (
            job_id, idempotency_key, web_request_id, user_id,
            voice_source, script, voice_profile_id, speed, volume_percent,
            language, status, status_reason, quote_xu, charged_xu, payload_hash,
            artifact_path, artifact_bytes, settlement_status, settlement_idempotency_key,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'saved', 'Kịch bản missing artifact', 90, '1.0', 100, 'vi',
                  'processing', 'SETTLEMENT_IN_PROGRESS', 5, 0, 'dummy',
                  ?, 500, 'settling', ?, datetime('now'), datetime('now'))
        """,
        (job_id, f"{uid}:{job_id}", f"req_{job_id}", uid, missing_path, settle_key),
    )
    conn.commit()
    conn.close()

    provider_calls = 0

    async def mock_process_voice_tts(**kwargs):
        nonlocal provider_calls
        provider_calls += 1
        return None

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_voice_tts", mock_process_voice_tts)

    confirm_path = f"/internal/v1/web-voice-tts/jobs/{job_id}/confirm"
    headers = _sign("POST", confirm_path, actor_id=str(uid))
    resp = client.post(confirm_path, headers=headers)

    assert resp.status_code == 500
    assert resp.json()["error_code"] == "SETTLEMENT_RECOVERY_ARTIFACT_INCONSISTENT"

    # Invariants
    assert provider_calls == 0  # No provider re-execution
    conn = bot.db_connect()
    c = conn.cursor()
    c.execute("SELECT credits FROM users WHERE user_id = ?", (str(uid),))
    assert c.fetchone()[0] == 50  # No wallet debit
    c.execute("SELECT status, status_reason FROM web_voice_tts_bot_jobs WHERE job_id = ?", (job_id,))
    job_row = c.fetchone()
    assert job_row[0] == "failed"
    assert job_row[1] == "SETTLEMENT_RECOVERY_ARTIFACT_INCONSISTENT"
    conn.close()


def test_crash_recovery_fail_closed_on_corrupted_artifact_size_mismatch(monkeypatch, tmp_path):
    """FAIL_CLOSED_RECOVERY_REQUIRED: If artifact file size doesn't match recorded artifact_bytes."""
    client = TestClient(bot.fastapi_app)
    uid = 7004
    bot.get_user(uid)
    bot.add_credit(uid, 50, event_type="initial_deposit")

    fake_profile = {
        "id": 91,
        "user_id": uid,
        "name": "Giọng nhân vật 91",
        "provider": "minimax",
        "provider_voice_id": "minimax_v1_custom_91",
    }
    monkeypatch.setattr(bot, "get_user_voice_profile", lambda u, p: fake_profile if u == uid and p == 91 else None)
    monkeypatch.setattr(bot, "is_admin_user", lambda u: False)

    job_id = f"job_crash_corrupt_{uuid.uuid4().hex[:6]}"
    settle_key = f"voice_tts_settle:{uid}:{job_id}"

    # File on disk has 10 bytes, but job record claims 500 bytes
    corrupt_file = tmp_path / "voice_assets" / f"web_voice_tts_{uid}_{job_id}.mp3"
    corrupt_file.parent.mkdir(parents=True, exist_ok=True)
    corrupt_file.write_bytes(b"CORRUPTED_")

    conn = bot.db_connect()
    conn.execute(
        """
        INSERT INTO web_voice_tts_bot_jobs (
            job_id, idempotency_key, web_request_id, user_id,
            voice_source, script, voice_profile_id, speed, volume_percent,
            language, status, status_reason, quote_xu, charged_xu, payload_hash,
            artifact_path, artifact_bytes, settlement_status, settlement_idempotency_key,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'saved', 'Kịch bản corrupt artifact', 91, '1.0', 100, 'vi',
                  'processing', 'SETTLEMENT_IN_PROGRESS', 5, 0, 'dummy',
                  ?, 500, 'settling', ?, datetime('now'), datetime('now'))
        """,
        (job_id, f"{uid}:{job_id}", f"req_{job_id}", uid, str(corrupt_file), settle_key),
    )
    conn.commit()
    conn.close()

    provider_calls = 0

    async def mock_process_voice_tts(**kwargs):
        nonlocal provider_calls
        provider_calls += 1
        return None

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_voice_tts", mock_process_voice_tts)

    confirm_path = f"/internal/v1/web-voice-tts/jobs/{job_id}/confirm"
    headers = _sign("POST", confirm_path, actor_id=str(uid))
    resp = client.post(confirm_path, headers=headers)

    assert resp.status_code == 500
    assert resp.json()["error_code"] == "SETTLEMENT_RECOVERY_ARTIFACT_INCONSISTENT"
    assert provider_calls == 0

    conn = bot.db_connect()
    c = conn.cursor()
    c.execute("SELECT credits FROM users WHERE user_id = ?", (str(uid),))
    assert c.fetchone()[0] == 50
    c.execute("SELECT status, status_reason FROM web_voice_tts_bot_jobs WHERE job_id = ?", (job_id,))
    job_row = c.fetchone()
    assert job_row[0] == "failed"
    assert job_row[1] == "SETTLEMENT_RECOVERY_ARTIFACT_INCONSISTENT"
    conn.close()
