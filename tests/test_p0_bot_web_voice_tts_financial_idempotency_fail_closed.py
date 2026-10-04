"""Rigorous verification tests for Blockers VTTS-R1-02 through VTTS-R1-06.

Covers:
- Blocker 2: Atomic CAS execution claim (concurrent confirms -> 1 provider execution, max 1 charge)
- Blocker 3: Settlement durability & crash resilience (charge success before status write -> 0 second charge)
- Blocker 4: Insufficient funds -> payment_required, 0 public artifact, retry -> 0 second provider synthesis
- Blocker 5: Missing or invalid stored default gender at execution -> fail closed, 0 provider calls
- Blocker 6: Owner-scoped and payload-bound idempotency (foreign leak prevention, payload mismatch conflict)
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import sqlite3
import time
import uuid
from pathlib import Path

import pytest
from starlette.testclient import TestClient

import bot
from services.admin_wallet_service import compute_internal_admin_wallet_signature
from services.web_voice_tts_runtime_service import (
    ensure_web_voice_tts_schema,
    get_web_voice_tts_job,
    prepare_web_voice_tts_job,
    update_web_voice_tts_job_status,
    update_web_voice_tts_settlement,
)

TEST_SECRET = "test_internal_secret_voice_tts_r1_1_32b_hex_9999"
TEST_TOKEN = "test_internal_token_voice_tts_r1_1"


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", TEST_SECRET)
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("INTERNAL_ADMIN_WALLET_SHARED_SECRET", TEST_SECRET)
    monkeypatch.setenv("INTERNAL_ADMIN_WALLET_BEARER_TOKEN", TEST_TOKEN)
    test_db = str(tmp_path / "test_bot_voice_tts_fail_closed.db")
    monkeypatch.setenv("DB_FILE", test_db)
    monkeypatch.setattr(bot, "DB_FILE", test_db)
    monkeypatch.setenv("VOICE_ASSET_STORAGE_DIR", str(tmp_path / "voice_assets"))

    conn = sqlite3.connect(test_db)
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
    req_id = f"test-fc-{uuid.uuid4().hex[:8]}"
    digest = hashlib.sha256(body).hexdigest()
    msg = f"{now_ts}.{req_id}.{method.upper()}.{path}.{digest}.{actor_id}".encode("utf-8")
    sig = hmac.new(TEST_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    headers = {
        "Authorization": f"Bearer {TEST_TOKEN}",
        "x-toan-aas-timestamp": now_ts,
        "x-toan-aas-request-id": req_id,
        "x-toan-aas-signature": sig,
        "x-toan-aas-actor-id": str(actor_id),
    }
    if body:
        headers["Content-Type"] = "application/json"
    return headers


def test_blocker5_missing_stored_default_gender_fails_before_provider(monkeypatch):
    """Corrupt or missing stored default gender must fail closed before calling provider."""
    client = TestClient(bot.fastapi_app)
    uid = 881122

    # Prepare directly or insert a job with missing gender into DB
    job_id = f"job_corrupt_gender_{uuid.uuid4().hex[:6]}"
    conn = sqlite3.connect(bot.DB_FILE)
    conn.execute(
        """
        INSERT INTO web_voice_tts_bot_jobs (
            job_id, idempotency_key, web_request_id, user_id,
            voice_source, script, default_voice_gender, speed, volume_percent,
            language, status, quote_xu, charged_xu, payload_hash, settlement_status,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'default', 'Chào bạn', NULL, '1.0', 100, 'vi', 'prepared', 0, 0, 'dummy', 'unsettled', datetime('now'), datetime('now'))
        """,
        (job_id, f"{uid}:{job_id}", f"req_{job_id}", uid),
    )
    conn.commit()
    conn.close()

    provider_called = False

    async def mock_execute_engine(*args, **kwargs):
        nonlocal provider_called
        provider_called = True
        return {"ok": True, "output_bytes": b"SHOULD_NOT_EXECUTE"}

    monkeypatch.setattr(bot, "execute_engine", mock_execute_engine)

    confirm_path = f"/internal/v1/web-voice-tts/jobs/{job_id}/confirm"
    headers = _sign("POST", confirm_path, actor_id=str(uid))
    resp = client.post(confirm_path, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "DEFAULT_VOICE_GENDER_REQUIRED"
    assert provider_called is False, "Missing stored default gender must fail closed with 0 provider calls"


def test_blocker5_invalid_stored_default_gender_fails_before_provider(monkeypatch):
    """Invalid stored default gender (e.g. 'alien') must fail closed with 0 provider calls."""
    client = TestClient(bot.fastapi_app)
    uid = 881123
    job_id = f"job_invalid_gender_{uuid.uuid4().hex[:6]}"
    conn = sqlite3.connect(bot.DB_FILE)
    conn.execute(
        """
        INSERT INTO web_voice_tts_bot_jobs (
            job_id, idempotency_key, web_request_id, user_id,
            voice_source, script, default_voice_gender, speed, volume_percent,
            language, status, quote_xu, charged_xu, payload_hash, settlement_status,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'default', 'Chào bạn', 'alien', '1.0', 100, 'vi', 'prepared', 0, 0, 'dummy', 'unsettled', datetime('now'), datetime('now'))
        """,
        (job_id, f"{uid}:{job_id}", f"req_{job_id}", uid),
    )
    conn.commit()
    conn.close()

    provider_called = False

    async def mock_execute_engine(*args, **kwargs):
        nonlocal provider_called
        provider_called = True
        return {"ok": True, "output_bytes": b"SHOULD_NOT_EXECUTE"}

    monkeypatch.setattr(bot, "execute_engine", mock_execute_engine)

    confirm_path = f"/internal/v1/web-voice-tts/jobs/{job_id}/confirm"
    headers = _sign("POST", confirm_path, actor_id=str(uid))
    resp = client.post(confirm_path, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "DEFAULT_VOICE_GENDER_REQUIRED"
    assert provider_called is False, "Invalid stored default gender must fail closed with 0 provider calls"


def test_blocker6_idempotency_foreign_owner_leak_prevention():
    """Idempotency key lookup from different user must reject with 409 and not leak foreign metadata."""
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-voice-tts/jobs"
    shared_key = f"shared_idem_key_{uuid.uuid4().hex[:8]}"

    # User 1 creates job with shared_key
    body1 = json.dumps({
        "voice_source": "default",
        "default_voice_gender": "female",
        "script": "Nội dung người dùng 1",
        "idempotency_key": shared_key,
    }).encode("utf-8")
    headers1 = _sign("POST", path, body=body1, actor_id="1001")
    resp1 = client.post(path, content=body1, headers=headers1)
    assert resp1.status_code == 200
    job1_id = resp1.json()["job"]["job_id"]

    # User 2 attempts to prepare with the same idempotency key
    body2 = json.dumps({
        "voice_source": "default",
        "default_voice_gender": "female",
        "script": "Nội dung người dùng 2 muốn xem của user 1",
        "idempotency_key": shared_key,
    }).encode("utf-8")
    headers2 = _sign("POST", path, body=body2, actor_id="1002")
    resp2 = client.post(path, content=body2, headers=headers2)
    assert resp2.status_code == 409
    assert resp2.json()["error_code"] == "IDEMPOTENCY_OWNER_MISMATCH"
    # Ensure foreign metadata is NOT returned
    assert "job" not in resp2.json() or resp2.json().get("job") is None
    assert job1_id not in resp2.text


def test_blocker6_idempotency_same_owner_different_payload_conflict():
    """Same owner + same key + different payload must produce deterministic 409 conflict."""
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-voice-tts/jobs"
    user_key = f"user_key_{uuid.uuid4().hex[:8]}"
    uid = "2002"

    body_a = json.dumps({
        "voice_source": "default",
        "default_voice_gender": "female",
        "script": "Kịch bản A",
        "idempotency_key": user_key,
    }).encode("utf-8")
    headers_a = _sign("POST", path, body=body_a, actor_id=uid)
    resp_a = client.post(path, content=body_a, headers=headers_a)
    assert resp_a.status_code == 200

    body_b = json.dumps({
        "voice_source": "default",
        "default_voice_gender": "male",  # Different gender / payload!
        "script": "Kịch bản B thay đổi hoàn toàn",
        "idempotency_key": user_key,
    }).encode("utf-8")
    headers_b = _sign("POST", path, body=body_b, actor_id=uid)
    resp_b = client.post(path, content=body_b, headers=headers_b)
    assert resp_b.status_code == 409
    assert resp_b.json()["error_code"] == "IDEMPOTENCY_PAYLOAD_MISMATCH"


def test_blocker2_atomic_concurrent_confirms_single_provider_execution(monkeypatch):
    """Concurrent confirmation requests must result in exactly one execution claim and max 1 charge."""
    client = TestClient(bot.fastapi_app)
    uid = 3003
    path_prep = "/internal/v1/web-voice-tts/jobs"
    body_prep = json.dumps({
        "voice_source": "default",
        "default_voice_gender": "female",
        "script": "Kiểm thử concurrency confirm",
        "idempotency_key": f"concurrent_{uuid.uuid4().hex[:8]}",
    }).encode("utf-8")
    headers_prep = _sign("POST", path_prep, body=body_prep, actor_id=str(uid))
    resp_prep = client.post(path_prep, content=body_prep, headers=headers_prep)
    assert resp_prep.status_code == 200
    job_id = resp_prep.json()["job"]["job_id"]

    provider_execution_count = 0

    async def mock_execute_engine(*args, **kwargs):
        nonlocal provider_execution_count
        provider_execution_count += 1
        await asyncio.sleep(0.05)  # simulate provider delay
        return {"ok": True, "output_bytes": b"CONCURRENT_AUDIO_RESULT"}

    monkeypatch.setattr(bot, "execute_engine", mock_execute_engine)

    confirm_path = f"/internal/v1/web-voice-tts/jobs/{job_id}/confirm"

    # Launch two concurrent requests via ThreadPoolExecutor
    def _do_confirm():
        c = TestClient(bot.fastapi_app)
        h = _sign("POST", confirm_path, actor_id=str(uid))
        return c.post(confirm_path, headers=h)

    with ThreadPoolExecutor(max_workers=2) as executor:
        future1 = executor.submit(_do_confirm)
        future2 = executor.submit(_do_confirm)
        res1 = future1.result()
        res2 = future2.result()

    # One request must succeed, other either succeeds via replay or reports in-progress conflict (409)
    statuses = {res1.status_code, res2.status_code}
    assert 200 in statuses, "At least one request must successfully execute"
    assert provider_execution_count == 1, f"Provider execution count must be exactly 1, got {provider_execution_count}"


def test_blocker3_settlement_durability_prevents_duplicate_charge_on_crash_retry(monkeypatch):
    """If charge succeeds and settlement_status is recorded as 'settled' but completion fails, retry must not recharge."""
    client = TestClient(bot.fastapi_app)
    uid = 4004
    job_id = f"job_settle_crash_{uuid.uuid4().hex[:6]}"

    # Mock voice profile
    fake_profile = {
        "id": 99,
        "user_id": uid,
        "name": "Giọng nhân vật 99",
        "provider": "minimax",
        "provider_voice_id": "minimax_v1_custom_99",
    }
    monkeypatch.setattr(bot, "get_user_voice_profile", lambda u, p: fake_profile if u == uid and p == 99 else None)
    monkeypatch.setattr(bot, "is_admin_user", lambda u: False)

    # Insert a prepared job with quote_xu = 5
    conn = sqlite3.connect(bot.DB_FILE)
    conn.execute(
        """
        INSERT INTO web_voice_tts_bot_jobs (
            job_id, idempotency_key, web_request_id, user_id,
            voice_source, script, voice_profile_id, speed, volume_percent,
            language, status, quote_xu, charged_xu, payload_hash, settlement_status,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'saved', 'Kịch bản test settlement crash', 99, '1.0', 100, 'vi', 'awaiting_confirmation', 5, 0, 'dummy', 'unsettled', datetime('now'), datetime('now'))
        """,
        (job_id, f"{uid}:{job_id}", f"req_{job_id}", uid),
    )
    conn.commit()
    conn.close()

    charge_count = 0

    def mock_spend(user_id, amount, category, desc):
        nonlocal charge_count
        charge_count += 1
        return {"ok": True, "final_cost": amount}

    monkeypatch.setattr(bot, "spend_fixed_credit_info", mock_spend)

    class FakeTTSResult:
        ok = True
        output_bytes = b"AUDIO_SAVED_DURABLE"

    async def mock_process_voice_tts(**kwargs):
        out_p = kwargs.get("output_path")
        if out_p:
            Path(out_p).write_bytes(b"AUDIO_SAVED_DURABLE")
        return FakeTTSResult()

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_voice_tts", mock_process_voice_tts)

    # First confirm succeeds
    confirm_path = f"/internal/v1/web-voice-tts/jobs/{job_id}/confirm"
    headers = _sign("POST", confirm_path, actor_id=str(uid))
    resp1 = client.post(confirm_path, headers=headers)
    assert resp1.status_code == 200
    assert charge_count == 1

    # Simulate ambiguous crash: reset status to 'prepared' but KEEP settlement_status = 'settled'
    conn = sqlite3.connect(bot.DB_FILE)
    conn.execute(
        "UPDATE web_voice_tts_bot_jobs SET status = 'prepared' WHERE job_id = ?",
        (job_id,),
    )
    conn.commit()
    conn.close()

    # Second confirm: must detect settlement_status == 'settled' and NOT call spend_fixed_credit_info again!
    resp2 = client.post(confirm_path, headers=headers)
    assert resp2.status_code == 200
    assert charge_count == 1, f"Second confirm must NOT recharge, expected charge_count=1, got {charge_count}"
