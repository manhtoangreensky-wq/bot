"""Verification tests for Bot Core Web Voice TTS internal runtime endpoints.

Task: VOICE_TTS_WEB_RUNTIME_PARITY_SOURCE_REMEDIATION_R1
Product Family: Voice TTS
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
from pathlib import Path
import time
import uuid

import pytest
from starlette.testclient import TestClient

import bot
from services.web_voice_tts_runtime_service import (
    ensure_web_voice_tts_schema,
    get_web_voice_tts_job,
)


TEST_SHARED_SECRET = "test_internal_token_secret_123"
TEST_HMAC_SECRET = "test_internal_hmac_secret_456"
TEST_USER_ID = 7126457028


@pytest.fixture(autouse=True)
def setup_env(monkeypatch, tmp_path):
    monkeypatch.setenv("INTERNAL_ADMIN_WALLET_SHARED_SECRET", TEST_SHARED_SECRET)
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", TEST_SHARED_SECRET)
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", TEST_HMAC_SECRET)
    monkeypatch.setenv("INTERNAL_ADMIN_WALLET_HMAC_SECRET", TEST_HMAC_SECRET)
    monkeypatch.setenv("INTERNAL_API_SECRET", TEST_SHARED_SECRET)
    monkeypatch.setenv("BOT_INTERNAL_SECRET", TEST_SHARED_SECRET)
    test_db = tmp_path / "test_bot.db"
    monkeypatch.setenv("DB_FILE", str(test_db))
    monkeypatch.setattr(bot, "DB_FILE", str(test_db))
    import sqlite3
    conn = sqlite3.connect(str(test_db))
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


def _sign(method: str, path: str, body: bytes, actor_id: str = str(TEST_USER_ID)) -> dict[str, str]:
    now_ts = str(int(time.time()))
    req_id = f"test-req-{uuid.uuid4().hex[:8]}"
    digest = hashlib.sha256(body).hexdigest()
    if actor_id:
        msg = f"{now_ts}.{req_id}.{method.upper()}.{path}.{digest}.{actor_id}".encode("utf-8")
    else:
        msg = f"{now_ts}.{req_id}.{method.upper()}.{path}.{digest}".encode("utf-8")
    sig = hmac.new(TEST_HMAC_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    headers = {
        "Authorization": f"Bearer {TEST_SHARED_SECRET}",
        "x-toan-aas-timestamp": now_ts,
        "x-toan-aas-request-id": req_id,
        "x-toan-aas-signature": sig,
        "x-toan-aas-actor-id": str(actor_id),
    }
    if body:
        headers["Content-Type"] = "application/json"
    return headers


def test_prepare_default_female_voice():
    """Verify default female voice job preparation succeeds at 0 Xu."""
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-voice-tts/jobs"
    payload = {
        "voice_source": "default",
        "default_voice_gender": "female",
        "script": "Xin chào quý khách, đây là giọng đọc thử.",
        "speed": "1.0",
        "volume_percent": 100,
    }
    body = json.dumps(payload).encode("utf-8")
    headers = _sign("POST", path, body)

    resp = client.post(path, content=body, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    job = data["job"]
    assert job["voice_source"] == "default"
    assert job["default_voice_gender"] == "female"
    assert job["quote_xu"] == 0
    assert job["status"] == "prepared"


def test_prepare_default_male_voice():
    """Verify default male voice job preparation succeeds at 0 Xu."""
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-voice-tts/jobs"
    payload = {
        "voice_source": "default",
        "default_voice_gender": "male",
        "script": "Xin chào quý khách, đây là giọng nam đọc thử.",
        "speed": "1.2",
        "volume_percent": 90,
    }
    body = json.dumps(payload).encode("utf-8")
    headers = _sign("POST", path, body)

    resp = client.post(path, content=body, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    job = data["job"]
    assert job["default_voice_gender"] == "male"
    assert job["speed"] == "1.2"
    assert job["volume_percent"] == 90
    assert job["quote_xu"] == 0


def test_prepare_default_gender_required_no_silent_fallback():
    """Verify missing or invalid gender rejects with 400 DEFAULT_VOICE_GENDER_REQUIRED."""
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-voice-tts/jobs"

    # Missing gender
    payload_missing = {"voice_source": "default", "script": "Xin chào"}
    body1 = json.dumps(payload_missing).encode("utf-8")
    resp1 = client.post(path, content=body1, headers=_sign("POST", path, body1))
    assert resp1.status_code == 400
    assert resp1.json()["error_code"] == "DEFAULT_VOICE_GENDER_REQUIRED"

    # Invalid gender
    payload_inv = {"voice_source": "default", "default_voice_gender": "neutral", "script": "Xin chào"}
    body2 = json.dumps(payload_inv).encode("utf-8")
    resp2 = client.post(path, content=body2, headers=_sign("POST", path, body2))
    assert resp2.status_code == 400
    assert resp2.json()["error_code"] == "DEFAULT_VOICE_GENDER_REQUIRED"


def test_prepare_rejects_forbidden_authority_fields():
    """Verify client-supplied financial or authority fields are rejected with 400."""
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-voice-tts/jobs"
    forbidden_keys = [
        "amount", "price", "wallet_balance", "provider", "output_url",
        "charged_xu", "quote_xu", "is_paid_job", "confirm_paid", "status"
    ]
    for key in forbidden_keys:
        payload = {
            "voice_source": "default",
            "default_voice_gender": "female",
            "script": "Xin chào",
            key: 100 if "xu" in key or "amount" in key else "hacked",
        }
        body = json.dumps(payload).encode("utf-8")
        resp = client.post(path, content=body, headers=_sign("POST", path, body))
        assert resp.status_code == 400, f"Field {key} should be rejected"
        assert resp.json()["error_code"] == "FORBIDDEN_AUTHORITY_FIELD_REJECTED"


def test_prepare_saved_voice_checks_profile_ownership(monkeypatch):
    """Verify saved voice checks server-side profile ownership."""
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-voice-tts/jobs"

    # Profile not found or not owned -> 403
    monkeypatch.setattr(bot, "get_user_voice_profile", lambda uid, pid: None)
    payload_unauth = {
        "voice_source": "saved",
        "voice_profile_id": 999,
        "script": "Lời thoại dài mười từ để kiểm tra tính phí",
    }
    body1 = json.dumps(payload_unauth).encode("utf-8")
    resp1 = client.post(path, content=body1, headers=_sign("POST", path, body1))
    assert resp1.status_code == 403
    assert resp1.json()["error_code"] == "VOICE_PROFILE_UNAUTHORIZED"

    # Owned profile -> 200 with quote_xu
    monkeypatch.setattr(bot, "get_user_voice_profile", lambda uid, pid: {"id": 1, "user_id": uid, "name": "Giọng test"})
    body2 = json.dumps(payload_unauth).encode("utf-8")
    resp2 = client.post(path, content=body2, headers=_sign("POST", path, body2))
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["ok"] is True
    job = data["job"]
    assert job["status"] == "awaiting_confirmation"
    assert job["quote_xu"] >= 1


def test_confirm_default_voice_executes_and_charges_zero(monkeypatch, tmp_path):
    """Verify confirming default voice executes engine and charges 0 Xu."""
    client = TestClient(bot.fastapi_app)
    # Prepare job first
    prep_path = "/internal/v1/web-voice-tts/jobs"
    payload = {"voice_source": "default", "default_voice_gender": "female", "script": "Chào mừng quý khách"}
    body = json.dumps(payload).encode("utf-8")
    prep_res = client.post(prep_path, content=body, headers=_sign("POST", prep_path, body)).json()
    job_id = prep_res["job"]["job_id"]

    # Mock execute_engine returning mock audio bytes
    async def mock_execute_engine(engine_name, params, context):
        assert engine_name == "voice_tts"
        return {"ok": True, "output_bytes": b"ID3_MOCK_MP3_AUDIO_BYTES_DEFAULT"}

    monkeypatch.setattr(bot, "execute_engine", mock_execute_engine)
    monkeypatch.setattr(bot, "voice_asset_storage_dir", lambda: tmp_path)

    confirm_path = f"/internal/v1/web-voice-tts/jobs/{job_id}/confirm"
    resp = client.post(confirm_path, content=b"{}", headers=_sign("POST", confirm_path, b"{}"))
    assert resp.status_code == 200
    job = resp.json()["job"]
    assert job["status"] == "completed"
    assert job["charged_xu"] == 0
    assert job["has_artifact"] is True
    assert "artifact_path" not in job  # Filesystem path is sanitized


def test_confirm_duplicate_zero_second_charge(monkeypatch, tmp_path):
    """Verify duplicate confirm short-circuits and never executes or charges twice."""
    client = TestClient(bot.fastapi_app)
    # Prepare job
    prep_path = "/internal/v1/web-voice-tts/jobs"
    payload = {"voice_source": "default", "default_voice_gender": "female", "script": "Kiểm tra duplicate confirm"}
    body = json.dumps(payload).encode("utf-8")
    prep_res = client.post(prep_path, content=body, headers=_sign("POST", prep_path, body)).json()
    job_id = prep_res["job"]["job_id"]

    exec_count = 0
    async def mock_execute_engine(*_args, **_kwargs):
        nonlocal exec_count
        exec_count += 1
        return {"ok": True, "output_bytes": b"MOCK_AUDIO_DATA"}

    monkeypatch.setattr(bot, "execute_engine", mock_execute_engine)
    monkeypatch.setattr(bot, "voice_asset_storage_dir", lambda: tmp_path)

    confirm_path = f"/internal/v1/web-voice-tts/jobs/{job_id}/confirm"
    # First confirm
    r1 = client.post(confirm_path, content=b"{}", headers=_sign("POST", confirm_path, b"{}"))
    assert r1.status_code == 200
    assert exec_count == 1

    # Second confirm -> Idempotent replay, zero second engine execution
    r2 = client.post(confirm_path, content=b"{}", headers=_sign("POST", confirm_path, b"{}"))
    assert r2.status_code == 200
    assert exec_count == 1
    assert r2.json()["job"]["status"] == "completed"


def test_artifact_streaming_and_cross_account_isolation(monkeypatch, tmp_path):
    """Verify audio streaming returns audio/mpeg and blocks other users."""
    client = TestClient(bot.fastapi_app)
    # Prepare and complete a job
    prep_path = "/internal/v1/web-voice-tts/jobs"
    payload = {"voice_source": "default", "default_voice_gender": "female", "script": "Tải tệp âm thanh"}
    body = json.dumps(payload).encode("utf-8")
    prep_res = client.post(prep_path, content=body, headers=_sign("POST", prep_path, body)).json()
    job_id = prep_res["job"]["job_id"]

    async def mock_execute_engine(*_args, **_kwargs):
        return {"ok": True, "output_bytes": b"VALID_MP3_STREAMING_BYTES"}

    monkeypatch.setattr(bot, "execute_engine", mock_execute_engine)
    monkeypatch.setattr(bot, "voice_asset_storage_dir", lambda: tmp_path)

    confirm_path = f"/internal/v1/web-voice-tts/jobs/{job_id}/confirm"
    client.post(confirm_path, content=b"{}", headers=_sign("POST", confirm_path, b"{}"))

    art_path = f"/internal/v1/web-voice-tts/jobs/{job_id}/artifact"

    # Authenticated owner downloads
    r_owner = client.get(art_path, headers=_sign("GET", art_path, b"", actor_id=str(TEST_USER_ID)))
    assert r_owner.status_code == 200
    assert r_owner.headers["content-type"] == "audio/mpeg"
    assert r_owner.content == b"VALID_MP3_STREAMING_BYTES"

    # Unauthenticated / different user -> 404 / 401
    other_user = 9999999
    r_other = client.get(art_path, headers=_sign("GET", art_path, b"", actor_id=str(other_user)))
    assert r_other.status_code == 404
