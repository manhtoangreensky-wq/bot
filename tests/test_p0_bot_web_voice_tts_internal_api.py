"""Test suite for Bot internal Web Voice TTS runtime endpoints and service.

Tests cover:
- JIT authorization & HMAC verification
- Rejection of client-injected authority fields (provider, amount, price, wallet)
- Strict validation of default_voice_gender enum (female, male) without silent fallback
- Voice profile ownership validation (saved voice)
- Idempotency preservation
- Safe read-only GET endpoints (no mutations)
- Execution, post-success settlement, and audio artifact serving
- Cross-account tenant isolation
"""

import json
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

import bot
from services.admin_wallet_service import compute_internal_admin_wallet_signature
from services.web_voice_tts_runtime_service import (
    ensure_web_voice_tts_schema,
    get_web_voice_tts_job,
    prepare_web_voice_tts_job,
)

TEST_SECRET = "test_internal_secret_voice_tts_32b_hex_0123"
TEST_TOKEN = "test_internal_token_voice_tts"


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", TEST_SECRET)
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("INTERNAL_ADMIN_WALLET_SHARED_SECRET", TEST_SECRET)
    monkeypatch.setenv("INTERNAL_ADMIN_WALLET_BEARER_TOKEN", TEST_TOKEN)
    test_db = str(tmp_path / "test_bot_voice_tts.db")
    monkeypatch.setenv("DB_FILE", test_db)
    monkeypatch.setattr(bot, "DB_FILE", test_db)
    monkeypatch.setenv("VOICE_ASSET_STORAGE_DIR", str(tmp_path / "voice_assets"))

    # Initialize tables
    import sqlite3
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


def make_auth_headers(
    method: str,
    path: str,
    body: bytes = b"",
    actor_id: str = "12345",
) -> dict[str, str]:
    ts = str(int(time.time()))
    req_id = f"req-voice-tts-{int(time.time())}"
    sig = compute_internal_admin_wallet_signature(
        secret=TEST_SECRET,
        timestamp=ts,
        request_id=req_id,
        method=method,
        path=path,
        body_bytes=body,
        actor_id=actor_id,
    )
    headers = {
        "authorization": f"Bearer {TEST_TOKEN}",
        "x-toan-aas-signature": sig,
        "x-toan-aas-timestamp": ts,
        "x-toan-aas-request-id": req_id,
        "content-type": "application/json",
    }
    if actor_id:
        headers["x-toan-aas-actor-id"] = actor_id
    return headers


def test_prepare_job_default_voice_female():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-voice-tts/jobs"
    payload = {
        "voice_source": "default",
        "default_voice_gender": "female",
        "script": "Xin chào đây là bản ghi âm thử giọng nữ mặc định.",
        "speed": "1.0",
        "volume_percent": 100,
        "idempotency_key": "user_12345:job_default_female_1",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="12345")

    response = client.post(path, content=body, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    job = data["job"]
    assert job["voice_source"] == "default"
    assert job["default_voice_gender"] == "female"
    assert job["quote_xu"] == 0
    assert job["status"] == "prepared"
    assert job["user_id"] == 12345


def test_prepare_job_default_voice_male():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-voice-tts/jobs"
    payload = {
        "voice_source": "default",
        "default_voice_gender": "male",
        "script": "Xin chào đây là bản ghi âm thử giọng nam mặc định.",
        "speed": "1.2",
        "volume_percent": 110,
        "idempotency_key": "user_12345:job_default_male_1",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="12345")

    response = client.post(path, content=body, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    job = data["job"]
    assert job["default_voice_gender"] == "male"
    assert job["quote_xu"] == 0
    assert job["status"] == "prepared"


def test_prepare_job_rejects_missing_or_invalid_default_gender():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-voice-tts/jobs"

    # Missing gender
    payload1 = {
        "voice_source": "default",
        "script": "Script without gender",
    }
    b1 = json.dumps(payload1).encode("utf-8")
    h1 = make_auth_headers("POST", path, body=b1, actor_id="12345")
    r1 = client.post(path, content=b1, headers=h1)
    assert r1.status_code == 400
    assert r1.json()["error_code"] == "DEFAULT_VOICE_GENDER_REQUIRED"

    # Invalid gender
    payload2 = {
        "voice_source": "default",
        "default_voice_gender": "neutral",
        "script": "Script with invalid gender",
    }
    b2 = json.dumps(payload2).encode("utf-8")
    h2 = make_auth_headers("POST", path, body=b2, actor_id="12345")
    r2 = client.post(path, content=b2, headers=h2)
    assert r2.status_code == 400
    assert r2.json()["error_code"] == "DEFAULT_VOICE_GENDER_REQUIRED"


def test_prepare_job_strictly_rejects_forbidden_authority_fields():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-voice-tts/jobs"

    for forbidden_field in ["provider", "provider_voice_id", "amount", "price", "wallet_balance", "quote_xu", "charged_xu"]:
        payload = {
            "voice_source": "default",
            "default_voice_gender": "female",
            "script": "Test forbidden field",
            forbidden_field: "injected_value",
        }
        body = json.dumps(payload).encode("utf-8")
        headers = make_auth_headers("POST", path, body=body, actor_id="12345")
        res = client.post(path, content=body, headers=headers)
        assert res.status_code == 400, f"Expected 400 for forbidden field: {forbidden_field}"
        assert res.json()["error_code"] == "FORBIDDEN_AUTHORITY_FIELD_REJECTED"


def test_prepare_job_saved_voice_unauthorized_profile():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-voice-tts/jobs"
    payload = {
        "voice_source": "saved",
        "voice_profile_id": 99999,  # Does not exist for actor 12345
        "script": "Xin chào đây là một kịch bản kiểm tra giọng đã lưu.",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="12345")
    res = client.post(path, content=body, headers=headers)
    assert res.status_code == 403
    assert res.json()["error_code"] == "VOICE_PROFILE_UNAUTHORIZED"


def test_prepare_job_saved_voice_success_quote(monkeypatch):
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-voice-tts/jobs"

    # Mock get_user_voice_profile to return valid profile for actor 12345
    fake_profile = {
        "id": 101,
        "user_id": 12345,
        "name": "Giọng thuyết minh chuyên nghiệp",
        "provider": "minimax",
        "provider_voice_id": "minimax_v1_voice",
    }
    monkeypatch.setattr(bot, "get_user_voice_profile", lambda uid, pid: fake_profile if uid == 12345 and pid == 101 else None)

    # 30 words script -> 3 Xu quote
    words_30 = " ".join(["từ"] * 30)
    payload = {
        "voice_source": "saved",
        "voice_profile_id": 101,
        "script": words_30,
        "idempotency_key": "user_12345:job_saved_voice_1",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="12345")
    res = client.post(path, content=body, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    job = data["job"]
    assert job["quote_xu"] == 3
    assert job["status"] == "awaiting_confirmation"


def test_idempotency_returns_identical_job():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-voice-tts/jobs"
    payload = {
        "voice_source": "default",
        "default_voice_gender": "female",
        "script": "Xin chào đây là bài kiểm tra tính bất biến idempotent.",
        "idempotency_key": "user_12345:job_idem_unique_key_01",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="12345")

    # Call 1
    r1 = client.post(path, content=body, headers=headers)
    assert r1.status_code == 200
    j1 = r1.json()["job"]

    # Call 2 with identical key
    r2 = client.post(path, content=body, headers=headers)
    assert r2.status_code == 200
    j2 = r2.json()["job"]

    assert j1["job_id"] == j2["job_id"]
    assert j1["idempotency_key"] == j2["idempotency_key"]


def test_get_job_detail_read_only_and_isolation():
    client = TestClient(bot.fastapi_app)
    # Prepare a job first
    path = "/internal/v1/web-voice-tts/jobs"
    payload = {
        "voice_source": "default",
        "default_voice_gender": "female",
        "script": "Kịch bản đọc chi tiết",
        "idempotency_key": "user_12345:job_get_detail_test",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="12345")
    r1 = client.post(path, content=body, headers=headers)
    job_id = r1.json()["job"]["job_id"]

    # GET detail by owner
    get_path = f"/internal/v1/web-voice-tts/jobs/{job_id}"
    get_headers = make_auth_headers("GET", get_path, actor_id="12345")
    r_get = client.get(get_path, headers=get_headers)
    assert r_get.status_code == 200
    job_detail = r_get.json()["job"]
    assert job_detail["job_id"] == job_id
    assert "artifact_path" not in job_detail  # Server internal filesystem path stripped
    assert job_detail["has_artifact"] is False

    # GET detail by another tenant (actor 99999) -> 404
    foreign_headers = make_auth_headers("GET", get_path, actor_id="99999")
    r_foreign = client.get(get_path, headers=foreign_headers)
    assert r_foreign.status_code == 404
    assert r_foreign.json()["error_code"] == "JOB_NOT_FOUND"


def test_confirm_job_default_voice_synthesis_flow(monkeypatch, tmp_path):
    client = TestClient(bot.fastapi_app)
    # Prepare a job
    path = "/internal/v1/web-voice-tts/jobs"
    payload = {
        "voice_source": "default",
        "default_voice_gender": "female",
        "script": "Thử nghiệm xác nhận tạo audio mặc định",
        "idempotency_key": "user_12345:job_confirm_default_test",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="12345")
    r1 = client.post(path, content=body, headers=headers)
    job_id = r1.json()["job"]["job_id"]

    # Mock execute_engine to return mock mp3 bytes without live provider calls
    fake_mp3 = b"FAKE_MP3_AUDIO_STREAM_HEADER_BYTE_CONTENT_DATA"
    async def mock_execute_engine(engine_name, params, context):
        assert engine_name == "voice_tts"
        assert params["voice_id"] == "default_female"
        return {"ok": True, "output_bytes": fake_mp3}

    monkeypatch.setattr(bot, "execute_engine", mock_execute_engine)

    # Confirm job
    confirm_path = f"/internal/v1/web-voice-tts/jobs/{job_id}/confirm"
    confirm_headers = make_auth_headers("POST", confirm_path, actor_id="12345")
    r_confirm = client.post(confirm_path, headers=confirm_headers)
    assert r_confirm.status_code == 200
    c_data = r_confirm.json()
    assert c_data["ok"] is True
    c_job = c_data["job"]
    assert c_job["status"] == "completed"
    assert c_job["charged_xu"] == 0
    assert c_job["has_artifact"] is True

    # Retrieve artifact
    artifact_path = f"/internal/v1/web-voice-tts/jobs/{job_id}/artifact"
    artifact_headers = make_auth_headers("GET", artifact_path, actor_id="12345")
    r_artifact = client.get(artifact_path, headers=artifact_headers)
    assert r_artifact.status_code == 200
    assert r_artifact.headers["content-type"] == "audio/mpeg"
    assert r_artifact.content == fake_mp3

    # Cross-tenant cannot retrieve artifact
    foreign_artifact_headers = make_auth_headers("GET", artifact_path, actor_id="88888")
    r_foreign_art = client.get(artifact_path, headers=foreign_artifact_headers)
    assert r_foreign_art.status_code == 404


def test_confirm_job_saved_voice_insufficient_funds_fails_closed(monkeypatch):
    client = TestClient(bot.fastapi_app)
    # Mock voice profile
    fake_profile = {
        "id": 202,
        "user_id": 12345,
        "name": "Giọng nhân vật 202",
        "provider": "minimax",
        "provider_voice_id": "minimax_v1_custom_202",
    }
    monkeypatch.setattr(bot, "get_user_voice_profile", lambda uid, pid: fake_profile if uid == 12345 and pid == 202 else None)
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: False)

    # Prepare saved voice job with quote
    words_30 = " ".join(["từ"] * 30)
    path = "/internal/v1/web-voice-tts/jobs"
    payload = {
        "voice_source": "saved",
        "voice_profile_id": 202,
        "script": words_30,
        "idempotency_key": "user_12345:job_saved_insufficient_funds",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="12345")
    r_prep = client.post(path, content=body, headers=headers)
    assert r_prep.status_code == 200
    job_id = r_prep.json()["job"]["job_id"]

    # Mock synthesis to succeed
    class FakeTTSResult:
        ok = True
        output_bytes = b"MOCK_SAVED_AUDIO_BYTES"

    async def mock_process_voice_tts(**kwargs):
        out_p = kwargs.get("output_path")
        if out_p:
            Path(out_p).write_bytes(b"MOCK_SAVED_AUDIO_BYTES")
        return FakeTTSResult()

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_voice_tts", mock_process_voice_tts)

    # Mock spend_fixed_credit_info to fail with insufficient funds
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda uid, amt, cat, desc: {"ok": False, "error": "insufficient_funds"})

    confirm_path = f"/internal/v1/web-voice-tts/jobs/{job_id}/confirm"
    confirm_headers = make_auth_headers("POST", confirm_path, actor_id="12345")
    r_confirm = client.post(confirm_path, headers=confirm_headers)
    assert r_confirm.status_code == 402
    assert r_confirm.json()["error_code"] == "INSUFFICIENT_FUNDS"

    # Verify job is failed, not completed
    get_path = f"/internal/v1/web-voice-tts/jobs/{job_id}"
    get_headers = make_auth_headers("GET", get_path, actor_id="12345")
    r_get = client.get(get_path, headers=get_headers)
    assert r_get.status_code == 200
    assert r_get.json()["job"]["status"] == "failed"
    assert r_get.json()["job"]["status_reason"] == "INSUFFICIENT_FUNDS"
