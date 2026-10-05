"""Comprehensive provider-free test suite for Bot Web Voice Clone runtime authority.

SPEC_ID: BOT-WEB-VOICE-CLONE-RUNTIME-AUTHORITY-R1
Covering Phase N 40 required test cases:
01 valid prepare — first-free quote
02 valid prepare — paid subsequent quote = canonical 50 Xu
03 consent missing
04 consent false
05 zero uploads
06 multiple uploads
07 foreign-owner upload
08 invalid upload
09 empty sample
10 unsupported sample type
11 oversized sample
12 sample too short
13 forbidden client provider fields
14 forbidden client price field
15 forbidden client wallet/charge fields
16 forbidden client output/profile authority fields
17 same idempotency key + same payload -> same job
18 same idempotency key + conflicting payload -> fail closed
19 foreign-owner idempotency isolation
20 duplicate confirm
21 concurrent confirm -> one provider execution maximum
22 first-free/price changes between prepare and confirm -> zero provider execution
23 provider deterministic failure -> zero charge
24 provider ambiguous result -> no blind provider replay
25 first-free provider success -> exactly zero debit + one valid profile
26 paid provider success -> exactly one debit
27 insufficient funds after provider success -> no active profile + no second provider execution
28 settlement retry -> at most one charge
29 completed duplicate confirm -> zero provider/debit delta
30 duplicate reconcile -> zero provider/debit delta
31 crash before claim
32 crash after claim/before provider
33 crash after provider result boundary
34 crash after profile persistence
35 crash after debit/before completed state
36 cross-account job detail forbidden
37 cross-account confirm forbidden
38 cross-account reconcile forbidden
39 missing/invalid HMAC forbidden
40 safe response contains no secrets/provider-file/local-path leakage
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid
import wave
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import bot
from services.admin_wallet_service import compute_internal_admin_wallet_signature
from services import voice_clone_pipeline
from services.voice_clone_pipeline import (
    CustomVoiceCreateResult,
    CUSTOM_VOICE_MAX_SAMPLE_BYTES,
)
from services.web_voice_clone_runtime_service import (
    acquire_voice_clone_first_free_reservation,
    claim_web_voice_clone_job_for_execution,
    contains_forbidden_authority_fields,
    ensure_web_voice_clone_schema,
    get_voice_clone_first_free_entitlement,
    get_web_voice_clone_job,
    prepare_web_voice_clone_job,
    release_voice_clone_first_free_reservation,
    to_safe_voice_clone_job_projection,
    transition_voice_clone_first_free_state,
    update_web_voice_clone_job,
    validate_voice_clone_sample,
)

TEST_SECRET = "test_internal_secret_voice_clone_32b_hex_9999"
TEST_TOKEN = "test_internal_token_voice_clone"
DEFAULT_TEST_UID = "50001"


def _make_wav_bytes(duration_seconds: float = 12.0) -> bytes:
    """Generate a valid WAV audio in bytes with specified duration."""
    sample_rate = 16000
    n_frames = int(sample_rate * duration_seconds)
    import io
    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n_frames)
    return bio.getvalue()


@pytest.fixture(autouse=True)
def setup_test_env(tmp_path: Path, monkeypatch):
    """Setup isolated test environment for Bot Web Voice Clone runtime."""
    test_db = str(tmp_path / "test_bot_voice_clone.db")
    monkeypatch.setenv("DB_FILE", test_db)
    monkeypatch.setattr(bot, "DB_FILE", test_db)
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", TEST_SECRET)
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("INTERNAL_ADMIN_WALLET_SHARED_SECRET", TEST_SECRET)
    monkeypatch.setenv("INTERNAL_ADMIN_WALLET_BEARER_TOKEN", TEST_TOKEN)

    staging_dir = tmp_path / "staging_media"
    staging_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SUBDUB_UPLOAD_STAGING_DIR", str(staging_dir))
    monkeypatch.setenv("SUBDUB_UPLOAD_MAX_MB", "50")

    voice_assets_dir = tmp_path / "voice_assets"
    voice_assets_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VOICE_ASSET_STORAGE_DIR", str(voice_assets_dir))

    # Disable trial bonus so wallets have exact deterministic balance
    monkeypatch.setattr(bot, "TRIAL_BONUS_ENABLED", False)

    bot.init_db()
    conn = sqlite3.connect(test_db)
    ensure_web_voice_clone_schema(conn)
    conn.close()

    # Non-admin by default so billing and quota behave normally
    monkeypatch.setattr(bot, "is_admin_user", lambda u: False)

    # Default readiness mocks: provider-free ready
    monkeypatch.setattr(
        bot,
        "get_minimax_voice_clone_readiness",
        lambda: {"ready": True, "public_enabled": True, "active_custom_voice_route": "minimax_test"},
    )
    monkeypatch.setattr(
        bot,
        "voice_clone_ready_for_processing",
        lambda r, admin_access=False: True,
    )


def setup_user_wallet(uid: int | str, balance: int = 0) -> None:
    """Helper to ensure user exists and has exact credit balance."""
    bot.get_user(int(uid))
    with bot.db_connect() as conn:
        conn.execute("UPDATE users SET credits = ? WHERE user_id = ?", (int(balance), str(uid)))


def make_auth_headers(
    method: str,
    path: str,
    body: bytes = b"",
    actor_id: str = DEFAULT_TEST_UID,
    token: str = TEST_TOKEN,
    secret: str = TEST_SECRET,
    timestamp: str | None = None,
    request_id: str | None = None,
) -> dict[str, str]:
    """Helper to compute valid canonical HMAC authentication headers."""
    ts = timestamp if timestamp is not None else str(int(time.time()))
    req_id = request_id if request_id is not None else f"req-vc-{time.time_ns()}"
    sig = compute_internal_admin_wallet_signature(
        secret=secret,
        timestamp=ts,
        request_id=req_id,
        method=method,
        path=path,
        body_bytes=body,
        actor_id=actor_id,
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "X-TOAN-AAS-Signature": sig,
        "X-TOAN-AAS-Timestamp": ts,
        "X-TOAN-AAS-Request-ID": req_id,
        "Content-Type": "application/json",
    }
    if actor_id:
        headers["X-TOAN-AAS-Actor-ID"] = actor_id
    return headers


def post_json_auth(client: TestClient, path: str, payload: dict | None = None, actor_id: str = DEFAULT_TEST_UID):
    """Helper for reliable JSON POST with canonical HMAC signature."""
    body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    headers = make_auth_headers("POST", path, body=body, actor_id=actor_id)
    return client.post(path, content=body, headers=headers)


def get_auth(client: TestClient, path: str, actor_id: str = DEFAULT_TEST_UID):
    """Helper for reliable GET with canonical HMAC signature."""
    headers = make_auth_headers("GET", path, body=b"", actor_id=actor_id)
    return client.get(path, headers=headers)


def stage_test_upload(
    client: TestClient,
    file_bytes: bytes,
    file_name: str = "sample.wav",
    content_type: str = "audio/wav",
    actor_id: str = DEFAULT_TEST_UID,
) -> str:
    """Helper to stage an upload via POST /internal/v1/uploads and return upload_id."""
    path = "/internal/v1/uploads"
    payload = {
        "file_name": file_name,
        "content_type": content_type,
        "content_base64": base64.b64encode(file_bytes).decode("ascii"),
        "sha256": hashlib.sha256(file_bytes).hexdigest(),
        "idempotency_key": f"stage_idem_{uuid.uuid4().hex[:12]}",
    }
    res = post_json_auth(client, path, payload, actor_id=actor_id)
    assert res.status_code == 200, f"Staging upload failed: {res.text}"
    return res.json()["upload_id"]


# ---------------------------------------------------------------------------
# 01-16: PREPARE, VALIDATION, AND CONTRACT TESTS
# ---------------------------------------------------------------------------

def test_01_valid_prepare_first_free_quote(monkeypatch):
    """01: Valid prepare when user is eligible for first-free clone (quote_xu = 0)."""
    client = TestClient(bot.fastapi_app)
    uid = "50001"
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=uid)

    path = "/internal/v1/web-voice-clone/jobs"
    payload = {
        "upload_id": upload_id,
        "consent": True,
        "display_name": "Giọng đọc truyền cảm",
        "idempotency_key": f"idem_01_{uuid.uuid4().hex[:8]}",
    }
    res = post_json_auth(client, path, payload, actor_id=uid)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["job_id"].startswith("vcjob_")
    assert data["quote_xu"] == 0
    assert data["pricing_state"] == "first_free"
    assert data["status"] == "prepared"
    assert data["status_reason"] == "PREPARED"
    assert data["upload_id"] == upload_id
    assert data["display_name"] == "Giọng đọc truyền cảm"


def test_02_valid_prepare_paid_subsequent_quote_canonical_50_xu(monkeypatch):
    """02: Valid prepare when user has already consumed free quota (quote_xu = 50)."""
    client = TestClient(bot.fastapi_app)
    uid = "50002"
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 50)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=uid)

    path = "/internal/v1/web-voice-clone/jobs"
    payload = {
        "upload_id": upload_id,
        "consent": True,
        "display_name": "Giọng Clone Thứ Hai",
        "idempotency_key": f"idem_02_{uuid.uuid4().hex[:8]}",
    }
    res = post_json_auth(client, path, payload, actor_id=uid)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["quote_xu"] == 50
    assert data["pricing_state"] == "paid_50_xu"
    assert data["status"] == "awaiting_confirmation"
    assert data["status_reason"] == "AWAITING_CUSTOMER_CONFIRMATION"


def test_03_consent_missing():
    """03: Prepare fails when consent field is missing from payload."""
    client = TestClient(bot.fastapi_app)
    uid = "50003"
    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=uid)

    path = "/internal/v1/web-voice-clone/jobs"
    payload = {
        "upload_id": upload_id,
        "display_name": "Giọng test",
    }
    res = post_json_auth(client, path, payload, actor_id=uid)
    assert res.status_code == 400
    data = res.json()
    assert data["ok"] is False
    assert data["error_code"] == "VOICE_CLONE_CONSENT_REQUIRED"


def test_04_consent_false():
    """04: Prepare fails when consent is explicitly False."""
    client = TestClient(bot.fastapi_app)
    uid = "50004"
    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=uid)

    path = "/internal/v1/web-voice-clone/jobs"
    payload = {
        "upload_id": upload_id,
        "consent": False,
        "display_name": "Giọng test",
    }
    res = post_json_auth(client, path, payload, actor_id=uid)
    assert res.status_code == 400
    data = res.json()
    assert data["ok"] is False
    assert data["error_code"] == "VOICE_CLONE_CONSENT_REQUIRED"


def test_05_zero_uploads():
    """05: Prepare fails when upload_id is missing or empty list."""
    client = TestClient(bot.fastapi_app)
    uid = "50005"
    path = "/internal/v1/web-voice-clone/jobs"
    for empty_val in ["", [], None]:
        payload = {
            "upload_id": empty_val,
            "consent": True,
            "display_name": "Giọng test",
        }
        res = post_json_auth(client, path, payload, actor_id=uid)
        assert res.status_code == 400
        assert res.json()["error_code"] in ("UPLOAD_REQUIRED", "SINGLE_UPLOAD_REQUIRED")


def test_06_multiple_uploads():
    """06: Prepare fails when multiple uploads are provided."""
    client = TestClient(bot.fastapi_app)
    uid = "50006"
    path = "/internal/v1/web-voice-clone/jobs"
    payload = {
        "upload_ids": ["upl_12345", "upl_67890"],
        "consent": True,
        "display_name": "Giọng test",
    }
    res = post_json_auth(client, path, payload, actor_id=uid)
    assert res.status_code == 400
    data = res.json()
    assert data["ok"] is False
    assert data["error_code"] == "SINGLE_UPLOAD_REQUIRED"


def test_07_foreign_owner_upload():
    """07: Prepare fails when staged upload belongs to a different user."""
    client = TestClient(bot.fastapi_app)
    user_a = "10001"
    user_b = "10002"

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=user_a)

    path = "/internal/v1/web-voice-clone/jobs"
    payload = {
        "upload_id": upload_id,
        "consent": True,
        "display_name": "Giọng đánh cắp",
    }
    res = post_json_auth(client, path, payload, actor_id=user_b)
    assert res.status_code == 403
    data = res.json()
    assert data["ok"] is False
    assert data["error_code"] in ("FORBIDDEN_CROSS_OWNER", "FORBIDDEN")


def test_08_invalid_upload():
    """08: Prepare fails when upload_id does not exist."""
    client = TestClient(bot.fastapi_app)
    uid = "50008"

    path = "/internal/v1/web-voice-clone/jobs"
    payload = {
        "upload_id": "upl_nonexistent_999999",
        "consent": True,
        "display_name": "Giọng test",
    }
    res = post_json_auth(client, path, payload, actor_id=uid)
    assert res.status_code == 404
    data = res.json()
    assert data["ok"] is False


def test_09_empty_sample(tmp_path):
    """09: Prepare fails when sample file on disk is empty (0 bytes)."""
    client = TestClient(bot.fastapi_app)
    uid = "50009"

    empty_file = tmp_path / "staging_media" / "empty.wav"
    empty_file.write_bytes(b"")

    upload_id = f"upl_empty_{uuid.uuid4().hex[:8]}"
    record = {
        "upload_id": upload_id,
        "owner_id": str(uid),
        "file_name": "empty.wav",
        "content_type": "audio/wav",
        "local_path": str(empty_file),
        "byte_size": 0,
        "sha256": hashlib.sha256(b"").hexdigest(),
        "status": "staged",
        "created_at": "2026-10-05T00:00:00Z",
        "updated_at": "2026-10-05T00:00:00Z",
    }
    bot.set_system_setting(f"subdub_upload:{upload_id}", json.dumps(record))

    path = "/internal/v1/web-voice-clone/jobs"
    payload = {
        "upload_id": upload_id,
        "consent": True,
        "display_name": "Giọng 0 byte",
    }
    res = post_json_auth(client, path, payload, actor_id=uid)
    assert res.status_code == 400
    data = res.json()
    assert data["ok"] is False
    assert data["error_code"] == "sample_missing_or_empty"


def test_10_unsupported_sample_type(tmp_path):
    """10: Prepare fails when sample file has unsupported audio format."""
    client = TestClient(bot.fastapi_app)
    uid = "50010"

    unsupported_file = tmp_path / "staging_media" / "sample.ogg"
    unsupported_file.write_bytes(b"OGGS_FAKE_DATA")

    upload_id = f"upl_unsupported_{uuid.uuid4().hex[:8]}"
    record = {
        "upload_id": upload_id,
        "owner_id": str(uid),
        "file_name": "sample.ogg",
        "content_type": "audio/ogg",
        "local_path": str(unsupported_file),
        "byte_size": 14,
        "sha256": hashlib.sha256(b"OGGS_FAKE_DATA").hexdigest(),
        "status": "staged",
        "created_at": "2026-10-05T00:00:00Z",
        "updated_at": "2026-10-05T00:00:00Z",
    }
    bot.set_system_setting(f"subdub_upload:{upload_id}", json.dumps(record))

    path = "/internal/v1/web-voice-clone/jobs"
    payload = {
        "upload_id": upload_id,
        "consent": True,
        "display_name": "Giọng Ogg",
    }
    res = post_json_auth(client, path, payload, actor_id=uid)
    assert res.status_code == 400
    data = res.json()
    assert data["ok"] is False
    assert data["error_code"] == "unsupported_audio_extension"


def test_11_oversized_sample(tmp_path):
    """11: Prepare fails when sample file exceeds CUSTOM_VOICE_MAX_SAMPLE_BYTES (20MB)."""
    client = TestClient(bot.fastapi_app)
    uid = "50011"

    large_file = tmp_path / "staging_media" / "large.wav"
    with open(large_file, "wb") as f:
        f.seek(CUSTOM_VOICE_MAX_SAMPLE_BYTES + 1024)
        f.write(b"\x00")

    upload_id = f"upl_oversized_{uuid.uuid4().hex[:8]}"
    record = {
        "upload_id": upload_id,
        "owner_id": str(uid),
        "file_name": "large.wav",
        "content_type": "audio/wav",
        "local_path": str(large_file),
        "byte_size": CUSTOM_VOICE_MAX_SAMPLE_BYTES + 1025,
        "sha256": "fake_sha",
        "status": "staged",
        "created_at": "2026-10-05T00:00:00Z",
        "updated_at": "2026-10-05T00:00:00Z",
    }
    bot.set_system_setting(f"subdub_upload:{upload_id}", json.dumps(record))

    path = "/internal/v1/web-voice-clone/jobs"
    payload = {
        "upload_id": upload_id,
        "consent": True,
        "display_name": "Giọng Quá Lớn",
    }
    res = post_json_auth(client, path, payload, actor_id=uid)
    assert res.status_code == 400
    data = res.json()
    assert data["ok"] is False
    assert data["error_code"] == "sample_too_large"


def test_12_sample_too_short(tmp_path):
    """12: Prepare fails when sample duration is less than 10.0 seconds."""
    client = TestClient(bot.fastapi_app)
    uid = "50012"

    short_wav = _make_wav_bytes(3.0)  # 3 seconds < 10.0 seconds
    upload_id = stage_test_upload(client, short_wav, actor_id=uid)

    path = "/internal/v1/web-voice-clone/jobs"
    payload = {
        "upload_id": upload_id,
        "consent": True,
        "display_name": "Giọng Ngắn Quá",
    }
    res = post_json_auth(client, path, payload, actor_id=uid)
    assert res.status_code == 400
    data = res.json()
    assert data["ok"] is False
    assert data["error_code"] == "sample_duration_too_short"


def test_13_forbidden_client_provider_fields():
    """13: Client cannot dictate provider or provider_voice_id."""
    client = TestClient(bot.fastapi_app)
    uid = "50013"
    path = "/internal/v1/web-voice-clone/jobs"
    for forbidden_dict in [{"provider": "minimax"}, {"provider_voice_id": "v_fake"}]:
        payload = {
            "upload_id": "upl_any",
            "consent": True,
            "display_name": "Giọng test",
            **forbidden_dict,
        }
        res = post_json_auth(client, path, payload, actor_id=uid)
        assert res.status_code == 400
        assert res.json()["error_code"] == "FORBIDDEN_AUTHORITY_FIELD_REJECTED"


def test_14_forbidden_client_price_field():
    """14: Client cannot dictate price or quote."""
    client = TestClient(bot.fastapi_app)
    uid = "50014"
    path = "/internal/v1/web-voice-clone/jobs"
    for forbidden_dict in [{"price": 0}, {"quote_xu": 0}, {"cost": 0}]:
        payload = {
            "upload_id": "upl_any",
            "consent": True,
            "display_name": "Giọng test",
            **forbidden_dict,
        }
        res = post_json_auth(client, path, payload, actor_id=uid)
        assert res.status_code == 400
        assert res.json()["error_code"] == "FORBIDDEN_AUTHORITY_FIELD_REJECTED"


def test_15_forbidden_client_wallet_charge_fields():
    """15: Client cannot dictate wallet or charge authority."""
    client = TestClient(bot.fastapi_app)
    uid = "50015"
    path = "/internal/v1/web-voice-clone/jobs"
    for forbidden_dict in [{"charged_xu": 0}, {"wallet_id": "w_123"}, {"balance": 9999}]:
        payload = {
            "upload_id": "upl_any",
            "consent": True,
            "display_name": "Giọng test",
            **forbidden_dict,
        }
        res = post_json_auth(client, path, payload, actor_id=uid)
        assert res.status_code == 400
        assert res.json()["error_code"] == "FORBIDDEN_AUTHORITY_FIELD_REJECTED"


def test_16_forbidden_client_output_profile_authority_fields():
    """16: Client cannot dictate profile_id or local/remote output paths."""
    client = TestClient(bot.fastapi_app)
    uid = "50016"
    path = "/internal/v1/web-voice-clone/jobs"
    for forbidden_dict in [{"profile_id": 123}, {"output_url": "http://evil.com"}, {"local_path": "/tmp/evil"}]:
        payload = {
            "upload_id": "upl_any",
            "consent": True,
            "display_name": "Giọng test",
            **forbidden_dict,
        }
        res = post_json_auth(client, path, payload, actor_id=uid)
        assert res.status_code == 400
        assert res.json()["error_code"] == "FORBIDDEN_AUTHORITY_FIELD_REJECTED"


# ---------------------------------------------------------------------------
# 17-19: IDEMPOTENCY & TENANT ISOLATION
# ---------------------------------------------------------------------------

def test_17_same_idempotency_key_same_payload_same_job(monkeypatch):
    """17: Same idempotency key and same semantic payload returns existing job."""
    client = TestClient(bot.fastapi_app)
    uid = "50017"
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=uid)

    path = "/internal/v1/web-voice-clone/jobs"
    idem_key = f"idem_replay_{uuid.uuid4().hex[:8]}"
    payload = {
        "upload_id": upload_id,
        "consent": True,
        "display_name": "Giọng Idempotent",
        "idempotency_key": idem_key,
    }
    res1 = post_json_auth(client, path, payload, actor_id=uid)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["idempotent_replay"] is False

    res2 = post_json_auth(client, path, payload, actor_id=uid)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["idempotent_replay"] is True
    assert data2["job_id"] == data1["job_id"]


def test_18_same_idempotency_key_conflicting_payload_fail_closed(monkeypatch):
    """18: Same idempotency key with conflicting payload fails closed with 409."""
    client = TestClient(bot.fastapi_app)
    uid = "50018"
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=uid)

    path = "/internal/v1/web-voice-clone/jobs"
    idem_key = f"idem_conflict_{uuid.uuid4().hex[:8]}"

    payload_a = {
        "upload_id": upload_id,
        "consent": True,
        "display_name": "Tên Ban Đầu",
        "idempotency_key": idem_key,
    }
    res_a = post_json_auth(client, path, payload_a, actor_id=uid)
    assert res_a.status_code == 200

    payload_b = {
        "upload_id": upload_id,
        "consent": True,
        "display_name": "Tên Khác Hoàn Toàn",
        "idempotency_key": idem_key,
    }
    res_b = post_json_auth(client, path, payload_b, actor_id=uid)
    assert res_b.status_code == 409
    data_b = res_b.json()
    assert data_b["error_code"] == "IDEMPOTENCY_PAYLOAD_MISMATCH"


def test_19_foreign_owner_idempotency_isolation(monkeypatch):
    """19: Reusing an idempotency key created by a different account fails with 403."""
    client = TestClient(bot.fastapi_app)
    user_a = "10001"
    user_b = "10002"
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)

    wav_bytes = _make_wav_bytes(12.0)
    upload_a = stage_test_upload(client, wav_bytes, actor_id=user_a)
    upload_b = stage_test_upload(client, wav_bytes, actor_id=user_b)

    path = "/internal/v1/web-voice-clone/jobs"
    shared_key = f"shared_idem_{uuid.uuid4().hex[:8]}"

    payload_a = {
        "upload_id": upload_a,
        "consent": True,
        "display_name": "Giọng User A",
        "idempotency_key": shared_key,
    }
    res_a = post_json_auth(client, path, payload_a, actor_id=user_a)
    assert res_a.status_code == 200

    payload_b = {
        "upload_id": upload_b,
        "consent": True,
        "display_name": "Giọng User B",
        "idempotency_key": shared_key,
    }
    res_b = post_json_auth(client, path, payload_b, actor_id=user_b)
    assert res_b.status_code == 403
    assert res_b.json()["error_code"] == "IDEMPOTENCY_OWNER_MISMATCH"


# ---------------------------------------------------------------------------
# 20-30: EXECUTION, CONCURRENCY, FINANCIAL SETTLEMENT, AND HEALING
# ---------------------------------------------------------------------------

def test_20_duplicate_confirm(monkeypatch):
    """20: Calling confirm on already completed job returns completed projection without re-execution."""
    client = TestClient(bot.fastapi_app)
    uid = "50020"
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)

    provider_calls = 0

    async def fake_create(**kwargs):
        nonlocal provider_calls
        provider_calls += 1
        return CustomVoiceCreateResult(
            ok=True,
            status="SUCCESS",
            profile_id=kwargs.get("profile_id"),
            provider="minimax",
            provider_voice_id="vox_custom_20",
            provider_file_id="pfile_20",
            preview_audio_path=str(kwargs.get("sample_path")),
            preview_audio_bytes=1000,
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_create)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=uid)

    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Test 20"},
        actor_id=uid,
    )
    job_id = res_prep.json()["job_id"]

    confirm_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/confirm"

    res1 = post_json_auth(client, confirm_path, None, actor_id=uid)
    assert res1.status_code == 200
    assert res1.json()["status"] == "completed"
    assert provider_calls == 1

    # Second confirm call
    res2 = post_json_auth(client, confirm_path, None, actor_id=uid)
    assert res2.status_code == 200
    assert res2.json()["status"] == "completed"
    assert provider_calls == 1  # ZERO delta!


def test_21_concurrent_confirm_one_provider_execution_maximum(monkeypatch):
    """21: Concurrent confirm attempt on job currently in processing receives 409 CONCURRENT_CONFIRM_IN_PROGRESS."""
    client = TestClient(bot.fastapi_app)
    uid = "50021"
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=uid)

    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Test 21"},
        actor_id=uid,
    )
    job_id = res_prep.json()["job_id"]

    # Transition job to 'processing' manually to simulate in-flight execution
    claimed, job = claim_web_voice_clone_job_for_execution(job_id, int(uid))
    assert claimed is True
    assert job["status"] == "processing"

    # Second confirm while processing
    confirm_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/confirm"
    res_concurrent = post_json_auth(client, confirm_path, None, actor_id=uid)
    assert res_concurrent.status_code == 409
    data = res_concurrent.json()
    assert data["error_code"] == "CONCURRENT_CONFIRM_IN_PROGRESS"


def test_22_first_free_price_changes_between_prepare_and_confirm_zero_provider_execution(monkeypatch):
    """22: If commercial pricing changes from free to paid between prepare and confirm, fails closed with 409 QUOTE_REFRESH_REQUIRED."""
    client = TestClient(bot.fastapi_app)
    uid = "50022"

    # Prepared when price is 0
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)
    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=uid)

    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Test 22"},
        actor_id=uid,
    )
    job_id = res_prep.json()["job_id"]
    assert res_prep.json()["quote_xu"] == 0

    # User consumes quota in another session before confirming this job! Price is now 50.
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 50)

    provider_called = False

    async def fake_create(**kwargs):
        nonlocal provider_called
        provider_called = True
        return CustomVoiceCreateResult(ok=True, status="SUCCESS")

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_create)

    confirm_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/confirm"
    res_confirm = post_json_auth(client, confirm_path, None, actor_id=uid)
    assert res_confirm.status_code == 409
    data = res_confirm.json()
    assert data["error_code"] == "QUOTE_REFRESH_REQUIRED"
    assert data["quote_xu"] == 50
    assert provider_called is False  # ZERO provider calls!


def test_23_provider_deterministic_failure_zero_charge(monkeypatch):
    """23: Deterministic provider failure results in failed job and exactly zero wallet charges."""
    client = TestClient(bot.fastapi_app)
    uid = 50023
    setup_user_wallet(uid, balance=100)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 50)

    async def fake_create(**kwargs):
        return CustomVoiceCreateResult(
            ok=False,
            status="FAIL",
            error_code="SAMPLE_AUDIO_UNSUITABLE",
            safe_public_message="Audio sample rejected by engine",
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_create)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))

    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Test 23"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]

    confirm_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/confirm"
    res_confirm = post_json_auth(client, confirm_path, None, actor_id=str(uid))
    assert res_confirm.status_code == 422
    assert res_confirm.json()["error_code"] == "SAMPLE_AUDIO_UNSUITABLE"

    job = get_web_voice_clone_job(job_id, uid)
    assert job["status"] == "failed"
    assert job["charged_xu"] == 0

    # User balance was NOT deducted
    with bot.db_connect() as conn:
        bal = conn.execute("SELECT credits FROM users WHERE user_id = ?", (str(uid),)).fetchone()[0]
        assert bal == 100


def test_24_provider_ambiguous_result_no_blind_provider_replay(monkeypatch):
    """24: Ambiguous provider timeout marks job failed with ambiguity state; no automatic second provider execution."""
    client = TestClient(bot.fastapi_app)
    uid = "50024"
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)

    exec_count = 0

    async def fake_create(**kwargs):
        nonlocal exec_count
        exec_count += 1
        return CustomVoiceCreateResult(
            ok=False,
            status="TIMEOUT",
            error_code="NETWORK_GATEWAY_TIMEOUT",
            safe_public_message="Provider upstream timed out",
            outcome_certainty="AMBIGUOUS",
            clone_dispatched=True,
            clone_submit_count=1,
            metadata={"ambiguity_reason": "NETWORK_AMBIGUOUS"},
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_create)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=uid)

    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Test 24"},
        actor_id=uid,
    )
    job_id = res_prep.json()["job_id"]

    confirm_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/confirm"
    res_confirm = post_json_auth(client, confirm_path, None, actor_id=uid)
    assert res_confirm.status_code == 504
    assert exec_count == 1

    job = get_web_voice_clone_job(job_id, int(uid))
    assert job["status"] == "failed"
    assert job["provider_ambiguity_state"] == "NETWORK_AMBIGUOUS"
    assert job["provider_execution_count"] == 1


def test_25_first_free_provider_success_zero_debit_one_valid_profile(monkeypatch):
    """25: First free provider success activates profile to 'ready' with exactly 0 Xu charged and 0 debits."""
    client = TestClient(bot.fastapi_app)
    uid = 50025
    setup_user_wallet(uid, balance=50)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)

    async def fake_create(**kwargs):
        return CustomVoiceCreateResult(
            ok=True,
            status="SUCCESS",
            profile_id=kwargs.get("profile_id"),
            provider="minimax",
            provider_voice_id="vox_free_25",
            provider_file_id="pfile_25",
            preview_audio_path=str(kwargs.get("sample_path")),
            preview_audio_bytes=1200,
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_create)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))

    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "First Free Profile"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]

    confirm_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/confirm"
    res_confirm = post_json_auth(client, confirm_path, None, actor_id=str(uid))
    assert res_confirm.status_code == 200
    data = res_confirm.json()
    assert data["status"] == "completed"
    assert data["charged_xu"] == 0
    assert data["canonical_profile_id"] is not None

    pid = data["canonical_profile_id"]
    with bot.db_connect() as conn:
        profile = conn.execute("SELECT status, provider_voice_id FROM voice_profiles WHERE id = ?", (pid,)).fetchone()
        assert profile[0] == "ready"
        assert profile[1] == "vox_free_25"

        bal = conn.execute("SELECT credits FROM users WHERE user_id = ?", (str(uid),)).fetchone()[0]
        assert bal == 50  # unchanged!


def test_26_paid_provider_success_exactly_one_debit(monkeypatch):
    """26: Paid provider success debits exactly 50 Xu once and activates profile."""
    client = TestClient(bot.fastapi_app)
    uid = 50026
    setup_user_wallet(uid, balance=100)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 50)

    async def fake_create(**kwargs):
        return CustomVoiceCreateResult(
            ok=True,
            status="SUCCESS",
            profile_id=kwargs.get("profile_id"),
            provider="minimax",
            provider_voice_id="vox_paid_26",
            provider_file_id="pfile_26",
            preview_audio_path=str(kwargs.get("sample_path")),
            preview_audio_bytes=1500,
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_create)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))

    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Paid Profile"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]

    confirm_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/confirm"
    res_confirm = post_json_auth(client, confirm_path, None, actor_id=str(uid))
    assert res_confirm.status_code == 200
    data = res_confirm.json()
    assert data["status"] == "completed"
    assert data["charged_xu"] == 50

    with bot.db_connect() as conn:
        bal = conn.execute("SELECT credits FROM users WHERE user_id = ?", (str(uid),)).fetchone()[0]
        assert bal == 50  # 100 - 50 = 50


def test_27_insufficient_funds_after_provider_success_no_active_profile_no_second_provider_execution(monkeypatch):
    """27: If user has insufficient funds after provider success, job is payment_required and profile is pending_charge."""
    client = TestClient(bot.fastapi_app)
    uid = 50027
    setup_user_wallet(uid, balance=10)  # Balance 10 < 50 required
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 50)

    provider_count = 0

    async def fake_create(**kwargs):
        nonlocal provider_count
        provider_count += 1
        return CustomVoiceCreateResult(
            ok=True,
            status="SUCCESS",
            profile_id=kwargs.get("profile_id"),
            provider="minimax",
            provider_voice_id="vox_pending_27",
            provider_file_id="pfile_27",
            preview_audio_path=str(kwargs.get("sample_path")),
            preview_audio_bytes=1000,
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_create)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))

    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Test 27"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]

    confirm_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/confirm"
    res_confirm = post_json_auth(client, confirm_path, None, actor_id=str(uid))
    assert res_confirm.status_code == 402
    assert res_confirm.json()["error_code"] == "INSUFFICIENT_FUNDS"

    job = get_web_voice_clone_job(job_id, uid)
    assert job["status"] == "payment_required"
    assert job["provider_execution_count"] == 1

    pid = job["canonical_profile_id"]
    with bot.db_connect() as conn:
        prof_status = conn.execute("SELECT status FROM voice_profiles WHERE id = ?", (pid,)).fetchone()[0]
        assert prof_status == "pending_charge"  # NOT READY!

    # Re-calling confirm while still insufficient funds does NOT invoke provider a second time
    res_confirm2 = post_json_auth(client, confirm_path, None, actor_id=str(uid))
    assert res_confirm2.status_code == 402
    assert provider_count == 1  # ZERO SECOND PROVIDER CALL!


def test_28_settlement_retry_at_most_one_charge(monkeypatch):
    """28: Settlement retry after topup activates profile with at most 1 charge."""
    client = TestClient(bot.fastapi_app)
    uid = 50028
    setup_user_wallet(uid, balance=10)  # Balance 10
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 50)

    async def fake_create(**kwargs):
        return CustomVoiceCreateResult(
            ok=True,
            status="SUCCESS",
            profile_id=kwargs.get("profile_id"),
            provider="minimax",
            provider_voice_id="vox_settle_28",
            provider_file_id="pfile_28",
            preview_audio_path=str(kwargs.get("sample_path")),
            preview_audio_bytes=1000,
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_create)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))

    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Test 28"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]
    confirm_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/confirm"

    # Confirm 1: insufficient funds
    post_json_auth(client, confirm_path, None, actor_id=str(uid))

    # User tops up 100 Xu
    bot.add_credit(uid, 100, event_type="topup")  # Balance now 110

    # Confirm 2: settlement retry succeeds
    res_retry = post_json_auth(client, confirm_path, None, actor_id=str(uid))
    assert res_retry.status_code == 200
    data = res_retry.json()
    assert data["status"] == "completed"
    assert data["charged_xu"] == 50

    with bot.db_connect() as conn:
        bal = conn.execute("SELECT credits FROM users WHERE user_id = ?", (str(uid),)).fetchone()[0]
        assert bal == 60  # 110 - 50 = 60


def test_29_completed_duplicate_confirm_zero_provider_debit_delta(monkeypatch):
    """29: Repeated confirm on completed job has 0 provider delta and 0 debit delta."""
    client = TestClient(bot.fastapi_app)
    uid = 50029
    setup_user_wallet(uid, balance=100)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 50)

    provider_calls = 0

    async def fake_create(**kwargs):
        nonlocal provider_calls
        provider_calls += 1
        return CustomVoiceCreateResult(
            ok=True,
            status="SUCCESS",
            profile_id=kwargs.get("profile_id"),
            provider="minimax",
            provider_voice_id="vox_29",
            provider_file_id="pfile_29",
            preview_audio_path=str(kwargs.get("sample_path")),
            preview_audio_bytes=1000,
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_create)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))

    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Test 29"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]
    confirm_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/confirm"

    # Confirm 1
    res1 = post_json_auth(client, confirm_path, None, actor_id=str(uid))
    assert res1.status_code == 200

    with bot.db_connect() as conn:
        bal_after_first = conn.execute("SELECT credits FROM users WHERE user_id = ?", (str(uid),)).fetchone()[0]

    # Confirm 2
    res2 = post_json_auth(client, confirm_path, None, actor_id=str(uid))
    assert res2.status_code == 200

    with bot.db_connect() as conn:
        bal_after_second = conn.execute("SELECT credits FROM users WHERE user_id = ?", (str(uid),)).fetchone()[0]

    assert provider_calls == 1
    assert bal_after_first == bal_after_second == 50


def test_30_duplicate_reconcile_zero_provider_debit_delta(monkeypatch):
    """30: Repeated reconcile on completed job has 0 provider delta and 0 debit delta."""
    client = TestClient(bot.fastapi_app)
    uid = 50030
    setup_user_wallet(uid, balance=100)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 50)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))

    prep_result = prepare_web_voice_clone_job(
        web_job_id=f"vcjob_rec_{uuid.uuid4().hex[:8]}",
        web_request_id="req_rec_30",
        canonical_user_id=uid,
        upload_id=upload_id,
        consent=True,
        display_name="Test 30",
        quote_xu=50,
        pricing_state="paid_50_xu",
    )
    job_id = prep_result["job"]["job_id"]

    # Mark completed
    update_web_voice_clone_job(
        job_id,
        status="completed",
        status_reason="COMPLETED",
        settlement_status="settled",
        charged_xu=50,
        canonical_profile_id=999,
    )

    reconcile_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/reconcile"
    res1 = post_json_auth(client, reconcile_path, None, actor_id=str(uid))
    assert res1.status_code == 200

    res2 = post_json_auth(client, reconcile_path, None, actor_id=str(uid))
    assert res2.status_code == 200

    with bot.db_connect() as conn:
        bal = conn.execute("SELECT credits FROM users WHERE user_id = ?", (str(uid),)).fetchone()[0]
        assert bal == 100  # No debit during reconcile on completed job!


# ---------------------------------------------------------------------------
# 31-35: CRASH RECOVERY AND FAULT INJECTION BOUNDARIES
# ---------------------------------------------------------------------------

def test_31_crash_before_claim():
    """31: Job crashed before claim remains in prepared/awaiting_confirmation and is fully claimable."""
    uid = 50031
    prep_result = prepare_web_voice_clone_job(
        web_job_id=f"vcjob_31_{uuid.uuid4().hex[:8]}",
        web_request_id="req_31",
        canonical_user_id=uid,
        upload_id="upl_31",
        consent=True,
        display_name="Crash Before Claim",
        quote_xu=0,
        pricing_state="first_free",
    )
    job_id = prep_result["job"]["job_id"]
    assert prep_result["job"]["status"] == "prepared"

    # Process restarted: claim succeeds normally
    claimed, job = claim_web_voice_clone_job_for_execution(job_id, uid)
    assert claimed is True
    assert job["status"] == "processing"


def test_32_crash_after_claim_before_provider():
    """32: Crash after claim but before provider execution leaves provider_execution_count=0; second confirm rejected."""
    uid = 50032
    client = TestClient(bot.fastapi_app)

    prep_result = prepare_web_voice_clone_job(
        web_job_id=f"vcjob_32_{uuid.uuid4().hex[:8]}",
        web_request_id="req_32",
        canonical_user_id=uid,
        upload_id="upl_32",
        consent=True,
        display_name="Crash After Claim",
        quote_xu=0,
        pricing_state="first_free",
    )
    job_id = prep_result["job"]["job_id"]

    # Claim for execution, but crash occurs before calling provider
    claimed, job = claim_web_voice_clone_job_for_execution(job_id, uid)
    assert claimed is True
    assert job["provider_execution_count"] == 0

    # In-flight concurrent claim attempt is rejected
    confirm_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/confirm"
    res = post_json_auth(client, confirm_path, None, actor_id=str(uid))
    assert res.status_code == 409
    assert res.json()["error_code"] == "CONCURRENT_CONFIRM_IN_PROGRESS"


def test_33_crash_after_provider_result_boundary(monkeypatch):
    """33: Crash after provider result boundary reclaims recovery without second provider execution."""
    client = TestClient(bot.fastapi_app)
    uid = 50033
    setup_user_wallet(uid, balance=100)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 50)

    # Simulate provider result persisted in DB with settlement_status='settling'
    pid = bot.save_user_voice_profile(uid, "upl_33", display_name="Crash After Provider")
    job_id = f"vcjob_33_{uuid.uuid4().hex[:8]}"
    settle_key = f"voice_clone_settle:{uid}:{job_id}"

    with bot.db_connect() as conn:
        conn.execute(
            """
            INSERT INTO web_voice_clone_jobs (
                job_id, idempotency_key, web_request_id, user_id,
                payload_hash, upload_id, consent_snapshot, display_name,
                quote_xu, pricing_state, status, status_reason,
                provider_execution_count, provider_outcome_state,
                settlement_status, settlement_idempotency_key, canonical_profile_id,
                provider_voice_id, preview_audio_bytes, charged_xu, created_at, updated_at
            ) VALUES (?, 'idem_33', 'req_33', ?, 'hash', 'upl_33', 1, 'Crash After Provider', 50, 'paid_50_xu', 'processing', 'CLAIMED_FOR_EXECUTION', 1, 'provider_success', 'settling', ?, ?, 'vox_33', 1000, 0, datetime('now'), datetime('now'))
            """,
            (job_id, uid, settle_key, pid),
        )

    provider_called = False

    async def fake_create(**kwargs):
        nonlocal provider_called
        provider_called = True
        return CustomVoiceCreateResult(ok=True, status="SUCCESS")

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_create)

    # Confirm reclaims settlement recovery without calling provider
    confirm_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/confirm"
    res = post_json_auth(client, confirm_path, None, actor_id=str(uid))
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "completed"
    assert data["charged_xu"] == 50
    assert provider_called is False  # ZERO SECOND PROVIDER EXECUTION!


def test_34_crash_after_profile_persistence():
    """34: Crash after profile saved in pending_charge recovers and activates profile to ready."""
    client = TestClient(bot.fastapi_app)
    uid = 50034
    setup_user_wallet(uid, balance=100)

    pid = bot.save_user_voice_profile(uid, "upl_34", display_name="Test 34")
    bot.update_user_voice_profile(uid, pid, status="pending_charge", provider_voice_id="vox_34")

    job_id = f"vcjob_34_{uuid.uuid4().hex[:8]}"
    settle_key = f"voice_clone_settle:{uid}:{job_id}"

    with bot.db_connect() as conn:
        conn.execute(
            """
            INSERT INTO web_voice_clone_jobs (
                job_id, idempotency_key, web_request_id, user_id,
                payload_hash, upload_id, consent_snapshot, display_name,
                quote_xu, pricing_state, status, status_reason,
                provider_execution_count, provider_outcome_state,
                settlement_status, settlement_idempotency_key, canonical_profile_id,
                provider_voice_id, preview_audio_bytes, charged_xu, created_at, updated_at
            ) VALUES (?, 'idem_34', 'req_34', ?, 'hash', 'upl_34', 1, 'Test 34', 50, 'paid_50_xu', 'payment_required', 'INSUFFICIENT_FUNDS', 1, 'provider_success', 'unsettled', ?, ?, 'vox_34', 1000, 0, datetime('now'), datetime('now'))
            """,
            (job_id, uid, settle_key, pid),
        )

    # Reconcile settles payment and activates profile
    reconcile_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/reconcile"
    res = post_json_auth(client, reconcile_path, None, actor_id=str(uid))
    assert res.status_code == 200
    assert res.json()["status"] == "completed"

    with bot.db_connect() as conn:
        prof_status = conn.execute("SELECT status FROM voice_profiles WHERE id = ?", (pid,)).fetchone()[0]
        assert prof_status == "ready"


def test_35_crash_after_debit_before_completed_state():
    """35: Crash after debit but before completed state completes idempotently without second debit."""
    client = TestClient(bot.fastapi_app)
    uid = 50035
    setup_user_wallet(uid, balance=100)

    job_id = f"vcjob_35_{uuid.uuid4().hex[:8]}"
    settle_key = f"voice_clone_settle:{uid}:{job_id}"
    pid = bot.save_user_voice_profile(uid, "upl_35", display_name="Test 35")

    # Perform debit in wallet before crash
    charge = bot.spend_fixed_credit_idempotent_info(
        uid, 50, "web_voice_clone", ref_id=settle_key, note=f"job_id={job_id}"
    )
    assert charge["ok"] is True
    assert charge["balance_after"] == 50

    with bot.db_connect() as conn:
        conn.execute(
            """
            INSERT INTO web_voice_clone_jobs (
                job_id, idempotency_key, web_request_id, user_id,
                payload_hash, upload_id, consent_snapshot, display_name,
                quote_xu, pricing_state, status, status_reason,
                provider_execution_count, provider_outcome_state,
                settlement_status, settlement_idempotency_key, canonical_profile_id,
                provider_voice_id, preview_audio_bytes, charged_xu, created_at, updated_at
            ) VALUES (?, 'idem_35', 'req_35', ?, 'hash', 'upl_35', 1, 'Test 35', 50, 'paid_50_xu', 'processing', 'CLAIMED_FOR_EXECUTION', 1, 'provider_success', 'settling', ?, ?, 'vox_35', 1000, 0, datetime('now'), datetime('now'))
            """,
            (job_id, uid, settle_key, pid),
        )

    # Reconcile completes the job without second debit
    reconcile_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/reconcile"
    res = post_json_auth(client, reconcile_path, None, actor_id=str(uid))
    assert res.status_code == 200
    assert res.json()["status"] == "completed"

    with bot.db_connect() as conn:
        bal = conn.execute("SELECT credits FROM users WHERE user_id = ?", (str(uid),)).fetchone()[0]
        assert bal == 50  # ZERO SECOND DEBIT!


# ---------------------------------------------------------------------------
# 36-40: SECURITY, ACCESS CONTROL, AND SAFE RESPONSE LEAK PREVENTION
# ---------------------------------------------------------------------------

def test_36_cross_account_job_detail_forbidden():
    """36: Querying job detail with a different actor returns 404."""
    client = TestClient(bot.fastapi_app)
    uid_a = 10001
    uid_b = 10002

    prep = prepare_web_voice_clone_job(
        web_job_id=f"vcjob_36_{uuid.uuid4().hex[:8]}",
        web_request_id="req_36",
        canonical_user_id=uid_a,
        upload_id="upl_36",
        consent=True,
        display_name="User A Job",
        quote_xu=0,
        pricing_state="first_free",
    )
    job_id = prep["job"]["job_id"]

    detail_path = f"/internal/v1/web-voice-clone/jobs/{job_id}"
    res = get_auth(client, detail_path, actor_id=str(uid_b))
    assert res.status_code == 404


def test_37_cross_account_confirm_forbidden():
    """37: Attempting to confirm a foreign job returns 404."""
    client = TestClient(bot.fastapi_app)
    uid_a = 10001
    uid_b = 10002

    prep = prepare_web_voice_clone_job(
        web_job_id=f"vcjob_37_{uuid.uuid4().hex[:8]}",
        web_request_id="req_37",
        canonical_user_id=uid_a,
        upload_id="upl_37",
        consent=True,
        display_name="User A Job",
        quote_xu=0,
        pricing_state="first_free",
    )
    job_id = prep["job"]["job_id"]

    confirm_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/confirm"
    res = post_json_auth(client, confirm_path, None, actor_id=str(uid_b))
    assert res.status_code == 404


def test_38_cross_account_reconcile_forbidden():
    """38: Attempting to reconcile a foreign job returns 404."""
    client = TestClient(bot.fastapi_app)
    uid_a = 10001
    uid_b = 10002

    prep = prepare_web_voice_clone_job(
        web_job_id=f"vcjob_38_{uuid.uuid4().hex[:8]}",
        web_request_id="req_38",
        canonical_user_id=uid_a,
        upload_id="upl_38",
        consent=True,
        display_name="User A Job",
        quote_xu=0,
        pricing_state="first_free",
    )
    job_id = prep["job"]["job_id"]

    reconcile_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/reconcile"
    res = post_json_auth(client, reconcile_path, None, actor_id=str(uid_b))
    assert res.status_code == 404


def test_39_missing_invalid_hmac_forbidden():
    """39: Requests without valid HMAC signature or bearer token are rejected."""
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-voice-clone/jobs"

    # Missing all auth headers
    res1 = client.post(path, json={"upload_id": "upl_1", "consent": True})
    assert res1.status_code == 401

    # Bad token
    headers_bad_token = make_auth_headers("POST", path, token="invalid_token")
    res2 = client.post(path, json={"upload_id": "upl_1", "consent": True}, headers=headers_bad_token)
    assert res2.status_code == 401

    # Bad HMAC signature
    headers_bad_sig = make_auth_headers("POST", path)
    headers_bad_sig["X-TOAN-AAS-Signature"] = "0" * 64
    res3 = client.post(path, json={"upload_id": "upl_1", "consent": True}, headers=headers_bad_sig)
    assert res3.status_code == 401


def test_40_safe_response_contains_no_secrets_provider_file_local_path_leakage(monkeypatch):
    """40: Safe projection returned to client contains ZERO secrets, provider file IDs, or physical file paths."""
    client = TestClient(bot.fastapi_app)
    uid = 50040
    setup_user_wallet(uid, balance=100)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 50)

    secret_path = "/var/secrets/super_secret_file.mp3"
    secret_pfile = "provider_sensitive_file_token_9999"

    async def fake_create(**kwargs):
        return CustomVoiceCreateResult(
            ok=True,
            status="SUCCESS",
            profile_id=kwargs.get("profile_id"),
            provider="minimax",
            provider_voice_id="vox_40",
            provider_file_id=secret_pfile,
            preview_audio_path=secret_path,
            preview_audio_bytes=1000,
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_create)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))

    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Safe Projection Test"},
        actor_id=str(uid),
    )
    assert res_prep.status_code == 200
    job_id = res_prep.json()["job_id"]
    confirm_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/confirm"
    res_confirm = post_json_auth(client, confirm_path, None, actor_id=str(uid))

    assert res_confirm.status_code == 200
    body_text = res_confirm.text

    # Strict leakage checks
    assert secret_path not in body_text, "Physical file path leaked in response body!"
    assert secret_pfile not in body_text, "Provider internal file ID leaked in response body!"
    assert TEST_SECRET not in body_text, "Secret key leaked in response body!"
    assert TEST_TOKEN not in body_text, "Token leaked in response body!"

    # Verify keys present in json
    data = res_confirm.json()
    forbidden_keys = {"local_path", "preview_audio_path", "provider_file_id", "execution_claim", "recovery_markers", "payload_hash"}
    intersection = forbidden_keys.intersection(data.keys())
    assert len(intersection) == 0, f"Response contains forbidden internal keys: {intersection}"


# ---------------------------------------------------------------------------
# 41-46: FIRST-FREE PRICING RACE GUARD & RESERVATION STATE MACHINE TESTS
# ---------------------------------------------------------------------------


def test_41_concurrent_first_free_race_guard_second_job_rejected(monkeypatch):
    """41: Two 0-Xu jobs prepared for same user; launched concurrently via threads; exactly 1 provider execution, 1 winner (200), 1 loser (409)."""
    import concurrent.futures
    import threading
    import time

    client = TestClient(bot.fastapi_app)
    uid = 50041
    setup_user_wallet(uid, balance=0)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)

    # Job 1 prepared
    wav_bytes1 = _make_wav_bytes(12.0)
    upload_id1 = stage_test_upload(client, wav_bytes1, actor_id=str(uid))
    res_prep1 = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id1, "consent": True, "display_name": "Job 1"},
        actor_id=str(uid),
    )
    assert res_prep1.status_code == 200
    job_id1 = res_prep1.json()["job_id"]
    assert res_prep1.json()["quote_xu"] == 0

    # Job 2 prepared
    wav_bytes2 = _make_wav_bytes(12.0)
    upload_id2 = stage_test_upload(client, wav_bytes2, actor_id=str(uid))
    res_prep2 = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id2, "consent": True, "display_name": "Job 2"},
        actor_id=str(uid),
    )
    assert res_prep2.status_code == 200
    job_id2 = res_prep2.json()["job_id"]
    assert res_prep2.json()["quote_xu"] == 0

    provider_calls = 0
    provider_lock = threading.Lock()

    async def fake_create(**kwargs):
        nonlocal provider_calls
        with provider_lock:
            provider_calls += 1
        # Brief pause to guarantee actual overlap window while in provider execution
        time.sleep(0.05)
        return CustomVoiceCreateResult(
            ok=True,
            status="SUCCESS",
            profile_id=kwargs.get("profile_id"),
            provider="minimax",
            provider_voice_id="vox_concurrent_41",
            preview_audio_path=str(kwargs.get("sample_path")),
            preview_audio_bytes=1000,
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_create)

    # Launch confirm A + confirm B with actual concurrent overlap
    confirm_path1 = f"/internal/v1/web-voice-clone/jobs/{job_id1}/confirm"
    confirm_path2 = f"/internal/v1/web-voice-clone/jobs/{job_id2}/confirm"

    barrier = threading.Barrier(2)

    def do_confirm(path):
        barrier.wait()
        return post_json_auth(client, path, None, actor_id=str(uid))

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(do_confirm, confirm_path1)
        f2 = executor.submit(do_confirm, confirm_path2)
        r1 = f1.result()
        r2 = f2.result()

    statuses = sorted([r1.status_code, r2.status_code])
    assert statuses == [200, 409], f"Expected exactly one 200 and one 409, got {statuses}"
    assert provider_calls == 1, f"Expected exactly 1 provider execution, got {provider_calls}"

    loser_resp = r1 if r1.status_code == 409 else r2
    winner_resp = r1 if r1.status_code == 200 else r2
    assert loser_resp.json()["error_code"] in ("FIRST_FREE_RESERVED", "FIRST_FREE_CONSUMED")
    assert winner_resp.json()["status"] == "completed"

    # Confirm entitlement table has winner in settled
    ent = get_voice_clone_first_free_entitlement(uid)
    assert ent is not None
    assert ent["state"] == "settled"



def test_42_first_free_consumed_second_job_requires_quote_refresh_paid_50_xu(monkeypatch):
    """42: When first job settles under first-free, second prepared 0-Xu job gets 409 QUOTE_REFRESH_REQUIRED with quote_xu=50."""
    client = TestClient(bot.fastapi_app)
    uid = 50042
    setup_user_wallet(uid, balance=0)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)

    # Job 1 prepared
    wav_bytes1 = _make_wav_bytes(12.0)
    upload_id1 = stage_test_upload(client, wav_bytes1, actor_id=str(uid))
    res_prep1 = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id1, "consent": True, "display_name": "Job 1"},
        actor_id=str(uid),
    )
    job_id1 = res_prep1.json()["job_id"]

    # Job 2 prepared
    wav_bytes2 = _make_wav_bytes(12.0)
    upload_id2 = stage_test_upload(client, wav_bytes2, actor_id=str(uid))
    res_prep2 = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id2, "consent": True, "display_name": "Job 2"},
        actor_id=str(uid),
    )
    job_id2 = res_prep2.json()["job_id"]

    # Mock provider success for Job 1
    async def fake_create(**kwargs):
        return CustomVoiceCreateResult(
            ok=True,
            status="SUCCESS",
            profile_id=kwargs.get("profile_id"),
            provider="minimax",
            provider_voice_id="vox_42",
            preview_audio_path="/tmp/vox_42.mp3",
            preview_audio_bytes=500,
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_create)

    # Job 1 confirms and settles
    res_confirm1 = post_json_auth(client, f"/internal/v1/web-voice-clone/jobs/{job_id1}/confirm", None, actor_id=str(uid))
    assert res_confirm1.status_code == 200
    assert res_confirm1.json()["status"] == "completed"

    ent = get_voice_clone_first_free_entitlement(uid)
    assert ent is not None
    assert ent["state"] == "settled"

    # Now Job 2 confirms: should be rejected because first-free is consumed
    res_confirm2 = post_json_auth(client, f"/internal/v1/web-voice-clone/jobs/{job_id2}/confirm", None, actor_id=str(uid))
    assert res_confirm2.status_code == 409
    data2 = res_confirm2.json()
    assert data2["error_code"] == "QUOTE_REFRESH_REQUIRED"
    assert data2["quote_xu"] == 50
    assert data2["pricing_state"] == "paid_50_xu"


def test_43_pre_provider_failure_releases_first_free_reservation_for_retry(monkeypatch):
    """43: Pre-provider failure releases reservation so user can retry first-free clone legitimately."""
    client = TestClient(bot.fastapi_app)
    uid = 50043
    setup_user_wallet(uid, balance=0)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)

    # Prepare job with valid upload
    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))
    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Job 43"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]

    # Invalidate sample file before confirm to trigger pre-provider validation failure
    from services.subdub_upload_staging import get_staged_upload
    ok, reason, code, staged = get_staged_upload(upload_id, actor_id=str(uid))
    assert ok is True
    Path(staged["local_path"]).write_bytes(b"")

    # Confirm fails on pre-provider sample check
    res_confirm = post_json_auth(client, f"/internal/v1/web-voice-clone/jobs/{job_id}/confirm", None, actor_id=str(uid))
    assert res_confirm.status_code == 400
    assert res_confirm.json()["error_code"] == "sample_missing_or_empty"

    # Reservation state must be released
    ent = get_voice_clone_first_free_entitlement(uid)
    assert ent is not None
    assert ent["state"] == "released"

    # Now user prepares a second job with a good sample
    wav_bytes2 = _make_wav_bytes(12.0)
    upload_id2 = stage_test_upload(client, wav_bytes2, actor_id=str(uid))
    res_prep2 = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id2, "consent": True, "display_name": "Job 43 Retry"},
        actor_id=str(uid),
    )
    job_id2 = res_prep2.json()["job_id"]
    assert res_prep2.json()["quote_xu"] == 0

    async def fake_create(**kwargs):
        return CustomVoiceCreateResult(
            ok=True,
            status="SUCCESS",
            profile_id=kwargs.get("profile_id"),
            provider="minimax",
            provider_voice_id="vox_43",
            preview_audio_path="/tmp/vox_43.mp3",
            preview_audio_bytes=500,
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_create)

    # Retry succeeds and re-acquires reservation
    res_confirm2 = post_json_auth(client, f"/internal/v1/web-voice-clone/jobs/{job_id2}/confirm", None, actor_id=str(uid))
    assert res_confirm2.status_code == 200
    assert res_confirm2.json()["status"] == "completed"

    ent2 = get_voice_clone_first_free_entitlement(uid)
    assert ent2["job_id"] == job_id2
    assert ent2["state"] == "settled"


def test_44_deterministic_provider_failure_releases_first_free_reservation_for_retry(monkeypatch):
    """44: Deterministic provider failure releases reservation so user can re-use first-free entitlement."""
    client = TestClient(bot.fastapi_app)
    uid = 50044
    setup_user_wallet(uid, balance=0)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)

    # Job 1 prepared
    wav_bytes1 = _make_wav_bytes(12.0)
    upload_id1 = stage_test_upload(client, wav_bytes1, actor_id=str(uid))
    res_prep1 = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id1, "consent": True, "display_name": "Job 44 Fail"},
        actor_id=str(uid),
    )
    job_id1 = res_prep1.json()["job_id"]

    async def fake_fail(**kwargs):
        return CustomVoiceCreateResult(
            ok=False,
            status="FAIL",
            error_code="AUDIO_QUALITY_TOO_LOW",
            safe_public_message="Background noise too high",
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_fail)

    res_confirm1 = post_json_auth(client, f"/internal/v1/web-voice-clone/jobs/{job_id1}/confirm", None, actor_id=str(uid))
    assert res_confirm1.status_code == 422
    assert res_confirm1.json()["error_code"] == "AUDIO_QUALITY_TOO_LOW"

    # Verify reservation is released
    ent = get_voice_clone_first_free_entitlement(uid)
    assert ent is not None
    assert ent["state"] == "released"

    # User retries with new job
    wav_bytes2 = _make_wav_bytes(12.0)
    upload_id2 = stage_test_upload(client, wav_bytes2, actor_id=str(uid))
    res_prep2 = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id2, "consent": True, "display_name": "Job 44 Retry"},
        actor_id=str(uid),
    )
    job_id2 = res_prep2.json()["job_id"]
    assert res_prep2.json()["quote_xu"] == 0

    async def fake_success(**kwargs):
        return CustomVoiceCreateResult(
            ok=True,
            status="SUCCESS",
            profile_id=kwargs.get("profile_id"),
            provider="minimax",
            provider_voice_id="vox_44",
            preview_audio_path="/tmp/vox_44.mp3",
            preview_audio_bytes=500,
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_success)

    res_confirm2 = post_json_auth(client, f"/internal/v1/web-voice-clone/jobs/{job_id2}/confirm", None, actor_id=str(uid))
    assert res_confirm2.status_code == 200
    assert res_confirm2.json()["status"] == "completed"

    ent2 = get_voice_clone_first_free_entitlement(uid)
    assert ent2["job_id"] == job_id2
    assert ent2["state"] == "settled"


def test_45_ambiguous_provider_timeout_quarantines_first_free_reservation(monkeypatch):
    """45: Ambiguous provider timeout marks reservation provider_ambiguous (quarantined); subsequent attempts locked."""
    client = TestClient(bot.fastapi_app)
    uid = 50045
    setup_user_wallet(uid, balance=0)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)

    wav_bytes1 = _make_wav_bytes(12.0)
    upload_id1 = stage_test_upload(client, wav_bytes1, actor_id=str(uid))
    res_prep1 = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id1, "consent": True, "display_name": "Job 45 Timeout"},
        actor_id=str(uid),
    )
    job_id1 = res_prep1.json()["job_id"]

    async def fake_timeout(**kwargs):
        return CustomVoiceCreateResult(
            ok=False,
            status="TIMEOUT",
            error_code="NETWORK_GATEWAY_TIMEOUT",
            safe_public_message="Gateway timeout",
            outcome_certainty="AMBIGUOUS",
            clone_dispatched=True,
            clone_submit_count=1,
            metadata={"ambiguity_reason": "NETWORK_AMBIGUOUS"},
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_timeout)

    res_confirm1 = post_json_auth(client, f"/internal/v1/web-voice-clone/jobs/{job_id1}/confirm", None, actor_id=str(uid))
    assert res_confirm1.status_code == 504

    # Entitlement must be quarantined in provider_ambiguous
    ent = get_voice_clone_first_free_entitlement(uid)
    assert ent is not None
    assert ent["state"] == "provider_ambiguous"

    # Second job prepare and confirm must NOT acquire first-free reservation
    wav_bytes2 = _make_wav_bytes(12.0)
    upload_id2 = stage_test_upload(client, wav_bytes2, actor_id=str(uid))
    res_prep2 = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id2, "consent": True, "display_name": "Job 45 Other"},
        actor_id=str(uid),
    )
    job_id2 = res_prep2.json()["job_id"]

    res_confirm2 = post_json_auth(client, f"/internal/v1/web-voice-clone/jobs/{job_id2}/confirm", None, actor_id=str(uid))
    assert res_confirm2.status_code == 409
    assert res_confirm2.json()["error_code"] == "FIRST_FREE_QUARANTINED"


def test_46_reconcile_first_free_job_transitions_to_settled(monkeypatch):
    """46: Reconciling a first-free completed job durably marks entitlement as settled."""
    client = TestClient(bot.fastapi_app)
    uid = 50046
    setup_user_wallet(uid, balance=0)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)

    # Create job in processing state with quote 0, profile_id already created
    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))
    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Job 46"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]

    # Acquire reservation and advance to provider_succeeded
    acquire_voice_clone_first_free_reservation(uid, job_id)
    transition_voice_clone_first_free_state(uid, job_id, "provider_succeeded", reason="PROVIDER_SUCCESS")

    # Put job in processing with canonical profile AND durable provider success authority
    prof_id = bot.save_user_voice_profile(uid, "upl_46", display_name="test_46_profile")
    settle_key = f"voice_clone_settle:{uid}:{job_id}"
    update_web_voice_clone_job(
        job_id,
        status="processing",
        canonical_profile_id=prof_id,
        quote_xu=0,
        provider_outcome_state="provider_success",
        provider_execution_count=1,
        provider_voice_id="vox_46",
        settlement_idempotency_key=settle_key,
    )

    # Reconcile endpoint called
    reconcile_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/reconcile"
    res_rec = post_json_auth(client, reconcile_path, None, actor_id=str(uid))
    assert res_rec.status_code == 200
    assert res_rec.json()["status"] == "completed"

    # Entitlement must be settled
    ent = get_voice_clone_first_free_entitlement(uid)
    assert ent is not None
    assert ent["state"] == "settled"


# ---------------------------------------------------------------------------
# 47-58: MANDATORY PROVIDER-FREE RECONCILIATION GUARD TEST MATRIX (PHASE G)
# ---------------------------------------------------------------------------


def test_47_first_free_processing_draft_profile_unattempted_reconcile_fails_closed(monkeypatch):
    """47 (Phase G-01): first-free processing + draft profile + provider_unattempted -> reconcile cannot complete."""
    client = TestClient(bot.fastapi_app)
    uid = 50047
    setup_user_wallet(uid, balance=0)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))
    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Job 47"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]

    # Entitlement reserved, draft profile created, status processing, but provider unattempted
    acquire_voice_clone_first_free_reservation(uid, job_id)
    prof_id = bot.save_user_voice_profile(uid, "upl_47", display_name="draft_prof_47")
    update_web_voice_clone_job(
        job_id,
        status="processing",
        canonical_profile_id=prof_id,
        quote_xu=0,
        provider_outcome_state="unattempted",
        provider_execution_count=0,
    )

    reconcile_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/reconcile"
    res_rec = post_json_auth(client, reconcile_path, None, actor_id=str(uid))
    assert res_rec.status_code == 200
    data = res_rec.json()
    assert data["status"] == "processing", "Unattempted job must not be marked completed by reconcile!"
    assert data.get("charged_xu", 0) == 0

    # Profile must remain draft/pending, NOT ready
    with bot.db_connect() as conn:
        p_row = conn.execute("SELECT status FROM voice_profiles WHERE id = ?", (prof_id,)).fetchone()
        assert p_row[0] != "ready"

    # Entitlement must remain reserved, NOT settled
    ent = get_voice_clone_first_free_entitlement(uid)
    assert ent is not None
    assert ent["state"] == "reserved"


def test_48_first_free_reserved_entitlement_reconcile_cannot_settle(monkeypatch):
    """48 (Phase G-02): first-free reserved entitlement -> reconcile cannot settle."""
    client = TestClient(bot.fastapi_app)
    uid = 50048
    setup_user_wallet(uid, balance=0)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))
    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Job 48"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]

    acquire_voice_clone_first_free_reservation(uid, job_id)
    prof_id = bot.save_user_voice_profile(uid, "upl_48", display_name="prof_48")
    update_web_voice_clone_job(
        job_id,
        status="processing",
        canonical_profile_id=prof_id,
        quote_xu=0,
    )

    reconcile_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/reconcile"
    res_rec = post_json_auth(client, reconcile_path, None, actor_id=str(uid))
    assert res_rec.status_code == 200
    assert res_rec.json()["status"] == "processing"

    ent = get_voice_clone_first_free_entitlement(uid)
    assert ent is not None
    assert ent["state"] == "reserved"


def test_49_first_free_provider_started_reconcile_cannot_settle(monkeypatch):
    """49 (Phase G-03): first-free provider_started -> reconcile cannot settle."""
    client = TestClient(bot.fastapi_app)
    uid = 50049
    setup_user_wallet(uid, balance=0)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))
    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Job 49"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]

    acquire_voice_clone_first_free_reservation(uid, job_id)
    transition_voice_clone_first_free_state(uid, job_id, "provider_started", reason="STARTING_PROVIDER")

    prof_id = bot.save_user_voice_profile(uid, "upl_49", display_name="prof_49")
    update_web_voice_clone_job(
        job_id,
        status="processing",
        canonical_profile_id=prof_id,
        quote_xu=0,
        provider_outcome_state="provider_started",
        provider_execution_count=1,
    )

    reconcile_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/reconcile"
    res_rec = post_json_auth(client, reconcile_path, None, actor_id=str(uid))
    assert res_rec.status_code == 200
    assert res_rec.json()["status"] == "processing"

    ent = get_voice_clone_first_free_entitlement(uid)
    assert ent is not None
    assert ent["state"] == "provider_started"


def test_50_first_free_provider_ambiguous_reconcile_cannot_settle_nor_release(monkeypatch):
    """50 (Phase G-04): first-free provider_ambiguous -> reconcile cannot settle, cannot release, cannot provider replay."""
    client = TestClient(bot.fastapi_app)
    uid = 50050
    setup_user_wallet(uid, balance=0)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))
    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Job 50"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]

    acquire_voice_clone_first_free_reservation(uid, job_id)
    transition_voice_clone_first_free_state(uid, job_id, "provider_ambiguous", reason="NETWORK_TIMEOUT")

    prof_id = bot.save_user_voice_profile(uid, "upl_50", display_name="prof_50")
    update_web_voice_clone_job(
        job_id,
        status="processing",
        canonical_profile_id=prof_id,
        quote_xu=0,
        provider_outcome_state="provider_ambiguous",
        provider_execution_count=1,
    )

    reconcile_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/reconcile"
    res_rec = post_json_auth(client, reconcile_path, None, actor_id=str(uid))
    assert res_rec.status_code == 200
    assert res_rec.json()["status"] == "processing"

    ent = get_voice_clone_first_free_entitlement(uid)
    assert ent is not None
    assert ent["state"] == "provider_ambiguous"

    # Attempting to release a provider_ambiguous entitlement is rejected
    released = release_voice_clone_first_free_reservation(uid, job_id, reason="TEST_AMBIGUOUS_RELEASE")
    assert released is False
    ent_after = get_voice_clone_first_free_entitlement(uid)
    assert ent_after["state"] == "provider_ambiguous"


def test_51_paid_processing_draft_profile_unattempted_reconcile_fails_closed(monkeypatch):
    """51 (Phase G-06): paid processing + draft profile + provider_unattempted -> wallet delta 0, profile not ready."""
    client = TestClient(bot.fastapi_app)
    uid = 50051
    setup_user_wallet(uid, balance=100)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 50)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))
    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Job 51"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]

    prof_id = bot.save_user_voice_profile(uid, "upl_51", display_name="prof_51")
    update_web_voice_clone_job(
        job_id,
        status="processing",
        canonical_profile_id=prof_id,
        quote_xu=50,
        provider_outcome_state="unattempted",
        provider_execution_count=0,
    )

    reconcile_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/reconcile"
    res_rec = post_json_auth(client, reconcile_path, None, actor_id=str(uid))
    assert res_rec.status_code == 200
    assert res_rec.json()["status"] == "processing"

    # Wallet balance MUST remain exactly 100 (delta 0)
    with bot.db_connect() as conn:
        bal = conn.execute("SELECT credits FROM users WHERE user_id = ?", (str(uid),)).fetchone()[0]
        assert bal == 100
        prof_row = conn.execute("SELECT status FROM voice_profiles WHERE id = ?", (prof_id,)).fetchone()
        assert prof_row[0] != "ready"


def test_52_paid_provider_started_unproven_reconcile_fails_closed(monkeypatch):
    """52 (Phase G-07): paid provider_started but no proven success -> wallet delta 0, profile not ready."""
    client = TestClient(bot.fastapi_app)
    uid = 50052
    setup_user_wallet(uid, balance=100)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 50)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))
    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Job 52"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]

    prof_id = bot.save_user_voice_profile(uid, "upl_52", display_name="prof_52")
    update_web_voice_clone_job(
        job_id,
        status="processing",
        canonical_profile_id=prof_id,
        quote_xu=50,
        provider_outcome_state="provider_started",
        provider_execution_count=1,
        provider_voice_id="",
    )

    reconcile_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/reconcile"
    res_rec = post_json_auth(client, reconcile_path, None, actor_id=str(uid))
    assert res_rec.status_code == 200
    assert res_rec.json()["status"] == "processing"

    with bot.db_connect() as conn:
        bal = conn.execute("SELECT credits FROM users WHERE user_id = ?", (str(uid),)).fetchone()[0]
        assert bal == 100
        prof_row = conn.execute("SELECT status FROM voice_profiles WHERE id = ?", (prof_id,)).fetchone()
        assert prof_row[0] != "ready"


def test_53_paid_durable_provider_success_unsettled_reconcile_settles_once(monkeypatch):
    """53 (Phase G-08): paid durable provider_success + unsettled -> reconcile settles exactly once."""
    client = TestClient(bot.fastapi_app)
    uid = 50053
    setup_user_wallet(uid, balance=100)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 50)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))
    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Job 53"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]

    prof_id = bot.save_user_voice_profile(uid, "upl_53", display_name="prof_53")
    settle_key = f"voice_clone_settle:{uid}:{job_id}"
    update_web_voice_clone_job(
        job_id,
        status="processing",
        canonical_profile_id=prof_id,
        quote_xu=50,
        provider_outcome_state="provider_success",
        provider_execution_count=1,
        provider_voice_id="vox_53",
        settlement_idempotency_key=settle_key,
        settlement_status="unsettled",
    )

    reconcile_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/reconcile"
    res_rec = post_json_auth(client, reconcile_path, None, actor_id=str(uid))
    assert res_rec.status_code == 200
    assert res_rec.json()["status"] == "completed"
    assert res_rec.json()["charged_xu"] == 50

    with bot.db_connect() as conn:
        bal = conn.execute("SELECT credits FROM users WHERE user_id = ?", (str(uid),)).fetchone()[0]
        assert bal == 50  # exactly 1 debit of 50 Xu
        prof_row = conn.execute("SELECT status FROM voice_profiles WHERE id = ?", (prof_id,)).fetchone()
        assert prof_row[0] == "ready"


def test_54_paid_duplicate_reconcile_second_debit_zero(monkeypatch):
    """54 (Phase G-09): paid duplicate reconcile -> second debit 0."""
    client = TestClient(bot.fastapi_app)
    uid = 50054
    setup_user_wallet(uid, balance=100)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 50)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))
    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Job 54"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]

    prof_id = bot.save_user_voice_profile(uid, "upl_54", display_name="prof_54")
    settle_key = f"voice_clone_settle:{uid}:{job_id}"
    update_web_voice_clone_job(
        job_id,
        status="processing",
        canonical_profile_id=prof_id,
        quote_xu=50,
        provider_outcome_state="provider_success",
        provider_execution_count=1,
        provider_voice_id="vox_54",
        settlement_idempotency_key=settle_key,
        settlement_status="unsettled",
    )

    reconcile_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/reconcile"
    # Reconcile 1
    res1 = post_json_auth(client, reconcile_path, None, actor_id=str(uid))
    assert res1.status_code == 200
    assert res1.json()["status"] == "completed"

    with bot.db_connect() as conn:
        bal1 = conn.execute("SELECT credits FROM users WHERE user_id = ?", (str(uid),)).fetchone()[0]
        assert bal1 == 50

    # Reconcile 2
    res2 = post_json_auth(client, reconcile_path, None, actor_id=str(uid))
    assert res2.status_code == 200
    assert res2.json()["status"] == "completed"

    with bot.db_connect() as conn:
        bal2 = conn.execute("SELECT credits FROM users WHERE user_id = ?", (str(uid),)).fetchone()[0]
        assert bal2 == 50  # ZERO SECOND DEBIT!


def test_55_crash_after_draft_profile_before_provider_fail_closed(monkeypatch):
    """55 (Phase G-10): crash after draft profile before provider -> fail closed."""
    client = TestClient(bot.fastapi_app)
    uid = 50055
    setup_user_wallet(uid, balance=100)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 50)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))
    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Job 55"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]

    prof_id = bot.save_user_voice_profile(uid, "upl_55", display_name="prof_55")
    update_web_voice_clone_job(
        job_id,
        status="processing",
        canonical_profile_id=prof_id,
        quote_xu=50,
        provider_outcome_state="unattempted",
        provider_execution_count=0,
    )

    reconcile_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/reconcile"
    res_rec = post_json_auth(client, reconcile_path, None, actor_id=str(uid))
    assert res_rec.status_code == 200
    assert res_rec.json()["status"] == "processing"

    with bot.db_connect() as conn:
        bal = conn.execute("SELECT credits FROM users WHERE user_id = ?", (str(uid),)).fetchone()[0]
        assert bal == 100  # no debit


def test_56_crash_after_provider_started_marker_before_result_fail_closed(monkeypatch):
    """56 (Phase G-11): crash after provider_started marker before result -> fail closed."""
    client = TestClient(bot.fastapi_app)
    uid = 50056
    setup_user_wallet(uid, balance=100)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 50)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))
    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Job 56"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]

    prof_id = bot.save_user_voice_profile(uid, "upl_56", display_name="prof_56")
    update_web_voice_clone_job(
        job_id,
        status="processing",
        canonical_profile_id=prof_id,
        quote_xu=50,
        provider_outcome_state="provider_started",
        provider_execution_count=1,
        provider_voice_id="",
    )

    reconcile_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/reconcile"
    res_rec = post_json_auth(client, reconcile_path, None, actor_id=str(uid))
    assert res_rec.status_code == 200
    assert res_rec.json()["status"] == "processing"

    with bot.db_connect() as conn:
        bal = conn.execute("SELECT credits FROM users WHERE user_id = ?", (str(uid),)).fetchone()[0]
        assert bal == 100


def test_57_valid_completed_job_duplicate_reconcile_idempotent(monkeypatch):
    """57 (Phase G-12): valid completed job duplicate reconcile -> idempotent."""
    client = TestClient(bot.fastapi_app)
    uid = 50057
    setup_user_wallet(uid, balance=50)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))
    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Job 57"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]

    prof_id = bot.save_user_voice_profile(uid, "upl_57", display_name="prof_57")
    bot.update_user_voice_profile(uid, prof_id, status="ready", provider_voice_id="vox_57")
    settle_key = f"voice_clone_settle:{uid}:{job_id}"
    update_web_voice_clone_job(
        job_id,
        status="completed",
        status_reason="COMPLETED",
        canonical_profile_id=prof_id,
        quote_xu=50,
        charged_xu=50,
        settlement_status="settled",
        provider_outcome_state="provider_success",
        provider_execution_count=1,
        provider_voice_id="vox_57",
        settlement_idempotency_key=settle_key,
    )

    reconcile_path = f"/internal/v1/web-voice-clone/jobs/{job_id}/reconcile"
    res_rec = post_json_auth(client, reconcile_path, None, actor_id=str(uid))
    assert res_rec.status_code == 200
    data = res_rec.json()
    assert data["status"] == "completed"
    assert data["charged_xu"] == 50

    with bot.db_connect() as conn:
        bal = conn.execute("SELECT credits FROM users WHERE user_id = ?", (str(uid),)).fetchone()[0]
        assert bal == 50


def test_58_fsm_transition_guard_matrix():
    """58 (Phase F): state transition guard matrix:
    reserved -> settled = DENIED
    provider_started -> settled = DENIED
    provider_ambiguous -> settled = DENIED
    provider_failed -> settled = DENIED
    released -> settled = DENIED
    provider_succeeded -> settled = ALLOWED
    """
    uid_base = 60000
    test_cases = [
        ("reserved", False),
        ("provider_started", False),
        ("provider_ambiguous", False),
        ("provider_failed", False),
        ("released", False),
        ("provider_succeeded", True),
    ]

    for idx, (initial_state, should_succeed) in enumerate(test_cases):
        uid = uid_base + idx
        jid = f"job_fsm_{idx}"
        # Seed entitlement
        acquire_voice_clone_first_free_reservation(uid, jid)
        if initial_state != "reserved":
            # Force set initial state directly in DB
            with bot.db_connect() as conn:
                conn.execute(
                    "UPDATE web_voice_clone_first_free_entitlements SET state = ? WHERE user_id = ? AND job_id = ?",
                    (initial_state, uid, jid),
                )

        ok = transition_voice_clone_first_free_state(uid, jid, "settled", reason="TEST_FSM_GUARD")
        assert ok is should_succeed, f"Transition from {initial_state} to settled expected {should_succeed}, got {ok}"


# ---------------------------------------------------------------------------
# 59-70: BODY ACTOR AUTHORITY FALLBACK CORRECTION MATRIX (PHASE E / R1.3)
# ---------------------------------------------------------------------------


def test_59_no_actor_header_no_body_identity_rejected_401():
    """59 (Phase E-01): no actor header + no body identity -> 401 ACTOR_ID_REQUIRED."""
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-voice-clone/jobs"
    payload = {"upload_id": "upl_59", "consent": True, "display_name": "Test 59"}
    headers = make_auth_headers("POST", path, body=json.dumps(payload).encode("utf-8"), actor_id="50059")
    headers.pop("X-TOAN-AAS-Actor-ID", None)
    headers.pop("X-Actor-User-ID", None)

    res = client.post(path, json=payload, headers=headers)
    assert res.status_code == 401
    assert res.json()["error_code"] == "ACTOR_ID_REQUIRED"


def test_60_no_actor_header_body_canonical_user_id_rejected_zero_job():
    """60 (Phase E-02): no actor header + body canonical_user_id + otherwise correctly signed internal request -> rejected -> zero job creation."""
    client = TestClient(bot.fastapi_app)
    uid_a = 50060
    setup_user_wallet(uid_a, balance=100)
    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid_a))

    path = "/internal/v1/web-voice-clone/jobs"
    payload = {
        "upload_id": upload_id,
        "consent": True,
        "display_name": "Test 60",
        "canonical_user_id": uid_a,
    }
    raw_body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=raw_body, actor_id=str(uid_a))
    headers.pop("X-TOAN-AAS-Actor-ID", None)
    headers.pop("X-Actor-User-ID", None)

    res = client.post(path, content=raw_body, headers=headers)
    assert res.status_code == 401
    assert res.json()["error_code"] == "ACTOR_ID_REQUIRED"

    with bot.db_connect() as conn:
        job_count = conn.execute("SELECT COUNT(*) FROM web_voice_clone_jobs WHERE user_id = ?", (uid_a,)).fetchone()[0]
        assert job_count == 0


def test_61_no_actor_header_body_user_id_rejected_zero_job():
    """61 (Phase E-03): no actor header + body user_id + otherwise correctly signed internal request -> rejected -> zero job creation."""
    client = TestClient(bot.fastapi_app)
    uid_a = 50061
    setup_user_wallet(uid_a, balance=100)
    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid_a))

    path = "/internal/v1/web-voice-clone/jobs"
    payload = {
        "upload_id": upload_id,
        "consent": True,
        "display_name": "Test 61",
        "user_id": uid_a,
    }
    raw_body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=raw_body, actor_id=str(uid_a))
    headers.pop("X-TOAN-AAS-Actor-ID", None)
    headers.pop("X-Actor-User-ID", None)

    res = client.post(path, content=raw_body, headers=headers)
    assert res.status_code == 401
    assert res.json()["error_code"] == "ACTOR_ID_REQUIRED"

    with bot.db_connect() as conn:
        job_count = conn.execute("SELECT COUNT(*) FROM web_voice_clone_jobs WHERE user_id = ?", (uid_a,)).fetchone()[0]
        assert job_count == 0


def test_62_valid_actor_header_body_canonical_user_id_same_user_rejected_400():
    """62 (Phase E-04): valid actor header A + body canonical_user_id=A -> body identity field rejected as forbidden authority."""
    client = TestClient(bot.fastapi_app)
    uid_a = 50062
    setup_user_wallet(uid_a, balance=100)
    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid_a))

    path = "/internal/v1/web-voice-clone/jobs"
    payload = {
        "upload_id": upload_id,
        "consent": True,
        "display_name": "Test 62",
        "canonical_user_id": uid_a,
    }
    res = post_json_auth(client, path, payload, actor_id=str(uid_a))
    assert res.status_code == 400
    assert res.json()["error_code"] == "FORBIDDEN_AUTHORITY_FIELD_REJECTED"

    with bot.db_connect() as conn:
        job_count = conn.execute("SELECT COUNT(*) FROM web_voice_clone_jobs WHERE user_id = ?", (uid_a,)).fetchone()[0]
        assert job_count == 0


def test_63_valid_actor_header_body_user_id_same_user_rejected_400():
    """63 (Phase E-05): valid actor header A + body user_id=A -> rejected."""
    client = TestClient(bot.fastapi_app)
    uid_a = 50063
    setup_user_wallet(uid_a, balance=100)
    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid_a))

    path = "/internal/v1/web-voice-clone/jobs"
    payload = {
        "upload_id": upload_id,
        "consent": True,
        "display_name": "Test 63",
        "user_id": uid_a,
    }
    res = post_json_auth(client, path, payload, actor_id=str(uid_a))
    assert res.status_code == 400
    assert res.json()["error_code"] == "FORBIDDEN_AUTHORITY_FIELD_REJECTED"

    with bot.db_connect() as conn:
        job_count = conn.execute("SELECT COUNT(*) FROM web_voice_clone_jobs WHERE user_id = ?", (uid_a,)).fetchone()[0]
        assert job_count == 0


def test_64_valid_actor_header_body_canonical_user_id_different_user_rejected():
    """64 (Phase E-06): valid actor header A + body canonical_user_id=B -> rejected, no B ownership effect, no leak."""
    client = TestClient(bot.fastapi_app)
    uid_a = 50064
    uid_b = 60064
    setup_user_wallet(uid_a, balance=100)
    setup_user_wallet(uid_b, balance=100)
    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid_a))

    path = "/internal/v1/web-voice-clone/jobs"
    payload = {
        "upload_id": upload_id,
        "consent": True,
        "display_name": "Test 64",
        "canonical_user_id": uid_b,
    }
    res = post_json_auth(client, path, payload, actor_id=str(uid_a))
    assert res.status_code == 400
    assert res.json()["error_code"] == "FORBIDDEN_AUTHORITY_FIELD_REJECTED"

    with bot.db_connect() as conn:
        job_count_b = conn.execute("SELECT COUNT(*) FROM web_voice_clone_jobs WHERE user_id = ?", (uid_b,)).fetchone()[0]
        assert job_count_b == 0
        job_count_a = conn.execute("SELECT COUNT(*) FROM web_voice_clone_jobs WHERE user_id = ?", (uid_a,)).fetchone()[0]
        assert job_count_a == 0


def test_65_valid_actor_header_body_user_id_different_user_rejected():
    """65 (Phase E-07): valid actor header A + body user_id=B -> rejected, no B ownership effect."""
    client = TestClient(bot.fastapi_app)
    uid_a = 50065
    uid_b = 60065
    setup_user_wallet(uid_a, balance=100)
    setup_user_wallet(uid_b, balance=100)
    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid_a))

    path = "/internal/v1/web-voice-clone/jobs"
    payload = {
        "upload_id": upload_id,
        "consent": True,
        "display_name": "Test 65",
        "user_id": uid_b,
    }
    res = post_json_auth(client, path, payload, actor_id=str(uid_a))
    assert res.status_code == 400
    assert res.json()["error_code"] == "FORBIDDEN_AUTHORITY_FIELD_REJECTED"

    with bot.db_connect() as conn:
        job_count_b = conn.execute("SELECT COUNT(*) FROM web_voice_clone_jobs WHERE user_id = ?", (uid_b,)).fetchone()[0]
        assert job_count_b == 0
        job_count_a = conn.execute("SELECT COUNT(*) FROM web_voice_clone_jobs WHERE user_id = ?", (uid_a,)).fetchone()[0]
        assert job_count_a == 0


def test_66_valid_actor_header_no_body_identity_succeeds_normally(monkeypatch):
    """66 (Phase E-08): valid actor header A + no body identity fields -> prepare succeeds normally."""
    client = TestClient(bot.fastapi_app)
    uid_a = 50066
    setup_user_wallet(uid_a, balance=100)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 50)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid_a))

    path = "/internal/v1/web-voice-clone/jobs"
    payload = {
        "upload_id": upload_id,
        "consent": True,
        "display_name": "Clean Header Actor Job",
    }
    res = post_json_auth(client, path, payload, actor_id=str(uid_a))
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["status"] in ("prepared", "awaiting_confirmation")
    assert data["user_id"] == uid_a

    job = get_web_voice_clone_job(data["job_id"], uid_a)
    assert job is not None
    assert job["user_id"] == uid_a


def test_67_valid_actor_header_foreign_owner_upload_rejected():
    """67 (Phase E-09): valid actor header A + foreign-owner upload -> existing cross-account upload denial remains intact."""
    client = TestClient(bot.fastapi_app)
    uid_a = 50067
    uid_b = 60067
    setup_user_wallet(uid_a, balance=100)
    setup_user_wallet(uid_b, balance=100)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id_b = stage_test_upload(client, wav_bytes, actor_id=str(uid_b))

    path = "/internal/v1/web-voice-clone/jobs"
    payload = {
        "upload_id": upload_id_b,
        "consent": True,
        "display_name": "Foreign Upload Test",
    }
    res = post_json_auth(client, path, payload, actor_id=str(uid_a))
    assert res.status_code == 403
    assert res.json()["error_code"] == "FORBIDDEN_CROSS_OWNER"


def test_68_missing_invalid_hmac_with_valid_actor_header_rejected():
    """68 (Phase E-10): missing/invalid HMAC + valid actor header -> existing auth rejection remains intact."""
    client = TestClient(bot.fastapi_app)
    uid = "50068"
    path = "/internal/v1/web-voice-clone/jobs"
    payload = {"upload_id": "upl_68", "consent": True, "display_name": "Bad HMAC"}

    headers = make_auth_headers("POST", path, actor_id=uid)
    headers["X-TOAN-AAS-Signature"] = "bad" * 16
    res = client.post(path, json=payload, headers=headers)
    assert res.status_code == 401
    assert res.json()["error_code"] == "SIGNATURE_INVALID"


def test_69_detail_confirm_reconcile_preview_require_header_actor():
    """69 (Phase E-11): detail / confirm / reconcile / preview continue requiring actor header; no regression."""
    client = TestClient(bot.fastapi_app)
    uid = 50069
    setup_user_wallet(uid, balance=100)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))

    prep = prepare_web_voice_clone_job(
        web_job_id=f"vcjob_69_{uuid.uuid4().hex[:8]}",
        web_request_id="req_69",
        canonical_user_id=uid,
        upload_id=upload_id,
        consent=True,
        display_name="Job 69",
        quote_xu=50,
        pricing_state="paid_50_xu",
    )
    job_id = prep["job"]["job_id"]

    routes = [
        ("GET", f"/internal/v1/web-voice-clone/jobs/{job_id}"),
        ("POST", f"/internal/v1/web-voice-clone/jobs/{job_id}/confirm"),
        ("POST", f"/internal/v1/web-voice-clone/jobs/{job_id}/reconcile"),
        ("GET", f"/internal/v1/web-voice-clone/jobs/{job_id}/preview"),
    ]

    for method, path in routes:
        headers = make_auth_headers(method, path, actor_id=str(uid))
        headers.pop("X-TOAN-AAS-Actor-ID", None)
        headers.pop("X-Actor-User-ID", None)

        if method == "GET":
            res = client.get(path, headers=headers)
        else:
            res = client.post(path, headers=headers)

        assert res.status_code == 401, f"{method} {path} expected 401 without actor header, got {res.status_code}"
        assert res.json()["error_code"] == "ACTOR_ID_REQUIRED"


def test_70_idempotent_prepare_replay_remains_owner_bound(monkeypatch):
    """70 (Phase E-12): idempotent prepare replay remains strictly owner-bound."""
    client = TestClient(bot.fastapi_app)
    uid_a = 50070
    uid_b = 60070
    setup_user_wallet(uid_a, balance=100)
    setup_user_wallet(uid_b, balance=100)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 50)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid_a))

    path = "/internal/v1/web-voice-clone/jobs"
    idem_key = f"idem_70_{uuid.uuid4().hex[:8]}"
    payload = {
        "upload_id": upload_id,
        "consent": True,
        "display_name": "Idempotent Owner Job",
        "idempotency_key": idem_key,
    }

    # Owner A creates job
    res1 = post_json_auth(client, path, payload, actor_id=str(uid_a))
    assert res1.status_code == 200
    job_id = res1.json()["job_id"]

    # Replay by Owner A returns same job
    res_replay_a = post_json_auth(client, path, payload, actor_id=str(uid_a))
    assert res_replay_a.status_code == 200
    assert res_replay_a.json()["idempotent_replay"] is True
    assert res_replay_a.json()["job_id"] == job_id

    # Foreign actor B attempting same idempotency key fails closed (403 IDEMPOTENCY_OWNER_MISMATCH)
    upload_id_b = stage_test_upload(client, wav_bytes, actor_id=str(uid_b))
    payload_b = {
        "upload_id": upload_id_b,
        "consent": True,
        "display_name": "Idempotent Foreign Attempt",
        "idempotency_key": idem_key,
    }
    res_foreign = post_json_auth(client, path, payload_b, actor_id=str(uid_b))
    assert res_foreign.status_code == 403
    assert res_foreign.json()["error_code"] == "IDEMPOTENCY_OWNER_MISMATCH"


# ==============================================================================
# PHASE H: R1.4 STRUCTURED PROVIDER OUTCOME CERTAINTY & REPLAY GUARD TESTS (71-86)
# ==============================================================================


def test_71_clone_submit_success_single_submit_and_success_certainty(tmp_path):
    """71: Clone submit success yields outcome_certainty='SUCCESS' and clone_submit_count=1."""
    async def _run():
        wav_path = tmp_path / "sample_71.wav"
        wav_path.write_bytes(_make_wav_bytes(12.0))

        async def mock_upload(b):
            return "PASS", "file_71", "ok", 200

        async def mock_clone(fid, seed):
            return "PASS", {"voice_id": "v_succ_71"}, "ok", 200

        async def mock_tts(t, voice_id=""):
            return "PASS", b"audio_preview", "ok", 200

        routes = [("minimax_primary", mock_upload, mock_clone, mock_tts)]

        res = await voice_clone_pipeline.process_custom_voice_create(
            user_id=70071,
            sample_path=str(wav_path),
            display_name="Voice 71",
            product_context="showroom",
            profile_id=71001,
            route_attempts_func=lambda r, admin_access=False: routes,
            access_allowed_func=lambda *a, **k: True,
            ready_for_processing_func=lambda *a, **k: True,
            readiness={"ready": True},
            output_dir=str(tmp_path),
            make_provider_voice_id_func=lambda u, profile_id=0: "v_succ_71",
        )
        assert res.ok is True
        assert res.outcome_certainty == "SUCCESS"
        assert res.clone_submit_count == 1
        assert res.clone_dispatched is True
        assert res.provider_voice_id == "v_succ_71"

    asyncio.run(_run())


def test_72_clone_submit_504_gateway_timeout_ambiguous_no_second_route(tmp_path):
    """72: First clone submit returning HTTP 504 is classified as AMBIGUOUS and halts cross-route replay."""
    async def _run():
        wav_path = tmp_path / "sample_72.wav"
        wav_path.write_bytes(_make_wav_bytes(12.0))

        r2_clone_called = 0

        async def mock_up_1(b):
            return "PASS", "file_72_1", "ok", 200

        async def mock_clone_1(fid, seed):
            return "FAIL", {}, "504 Gateway Time-out", 504

        async def mock_up_2(b):
            return "PASS", "file_72_2", "ok", 200

        async def mock_clone_2(fid, seed):
            nonlocal r2_clone_called
            r2_clone_called += 1
            return "PASS", {"voice_id": "v_72_2"}, "ok", 200

        routes = [
            ("route_1", mock_up_1, mock_clone_1, None),
            ("route_2", mock_up_2, mock_clone_2, None),
        ]

        res = await voice_clone_pipeline.process_custom_voice_create(
            user_id=70072,
            sample_path=str(wav_path),
            display_name="Voice 72",
            product_context="showroom",
            profile_id=72001,
            route_attempts_func=lambda r, admin_access=False: routes,
            access_allowed_func=lambda *a, **k: True,
            ready_for_processing_func=lambda *a, **k: True,
            readiness={"ready": True},
            output_dir=str(tmp_path),
            make_provider_voice_id_func=lambda u, profile_id=0: "v_72_seed",
        )
        assert res.ok is False
        assert res.outcome_certainty == "AMBIGUOUS"
        assert res.clone_submit_count == 1
        assert res.clone_dispatched is True
        assert r2_clone_called == 0

    asyncio.run(_run())


def test_73_clone_submit_502_503_bad_gateway_ambiguous_no_second_route(tmp_path):
    """73: First clone submit returning HTTP 502/503 is classified as AMBIGUOUS with zero route 2 submits."""
    async def _run():
        wav_path = tmp_path / "sample_73.wav"
        wav_path.write_bytes(_make_wav_bytes(12.0))

        r2_clone_called = 0

        async def mock_up_1(b):
            return "PASS", "file_73_1", "ok", 200

        async def mock_clone_1(fid, seed):
            return "FAIL", {}, "502 Bad Gateway", 502

        async def mock_up_2(b):
            return "PASS", "file_73_2", "ok", 200

        async def mock_clone_2(fid, seed):
            nonlocal r2_clone_called
            r2_clone_called += 1
            return "PASS", {"voice_id": "v_73_2"}, "ok", 200

        routes = [
            ("route_1", mock_up_1, mock_clone_1, None),
            ("route_2", mock_up_2, mock_clone_2, None),
        ]

        res = await voice_clone_pipeline.process_custom_voice_create(
            user_id=70073,
            sample_path=str(wav_path),
            display_name="Voice 73",
            product_context="showroom",
            profile_id=73001,
            route_attempts_func=lambda r, admin_access=False: routes,
            access_allowed_func=lambda *a, **k: True,
            ready_for_processing_func=lambda *a, **k: True,
            readiness={"ready": True},
            output_dir=str(tmp_path),
            make_provider_voice_id_func=lambda u, profile_id=0: "v_73_seed",
        )
        assert res.ok is False
        assert res.outcome_certainty == "AMBIGUOUS"
        assert res.clone_submit_count == 1
        assert r2_clone_called == 0

    asyncio.run(_run())


def test_74_clone_submit_connection_reset_ambiguous_no_second_route(tmp_path):
    """74: First clone submit raising ConnectionResetError is classified as AMBIGUOUS with zero route 2 submits."""
    async def _run():
        wav_path = tmp_path / "sample_74.wav"
        wav_path.write_bytes(_make_wav_bytes(12.0))

        r2_clone_called = 0

        async def mock_up_1(b):
            return "PASS", "file_74_1", "ok", 200

        async def mock_clone_1(fid, seed):
            raise ConnectionResetError("Connection forcibly closed by remote host")

        async def mock_up_2(b):
            return "PASS", "file_74_2", "ok", 200

        async def mock_clone_2(fid, seed):
            nonlocal r2_clone_called
            r2_clone_called += 1
            return "PASS", {"voice_id": "v_74_2"}, "ok", 200

        routes = [
            ("route_1", mock_up_1, mock_clone_1, None),
            ("route_2", mock_up_2, mock_clone_2, None),
        ]

        res = await voice_clone_pipeline.process_custom_voice_create(
            user_id=70074,
            sample_path=str(wav_path),
            display_name="Voice 74",
            product_context="showroom",
            profile_id=74001,
            route_attempts_func=lambda r, admin_access=False: routes,
            access_allowed_func=lambda *a, **k: True,
            ready_for_processing_func=lambda *a, **k: True,
            readiness={"ready": True},
            output_dir=str(tmp_path),
            make_provider_voice_id_func=lambda u, profile_id=0: "v_74_seed",
        )
        assert res.ok is False
        assert res.outcome_certainty == "AMBIGUOUS"
        assert res.clone_submit_count == 1
        assert r2_clone_called == 0

    asyncio.run(_run())


def test_75_clone_submit_runtime_error_upstream_closed_ambiguous_no_string_heuristic(tmp_path):
    """75: Generic transport exception without 'timeout' or 'network' is classified as AMBIGUOUS."""
    async def _run():
        wav_path = tmp_path / "sample_75.wav"
        wav_path.write_bytes(_make_wav_bytes(12.0))

        r2_clone_called = 0

        async def mock_up_1(b):
            return "PASS", "file_75_1", "ok", 200

        async def mock_clone_1(fid, seed):
            raise RuntimeError("upstream closed")

        async def mock_up_2(b):
            return "PASS", "file_75_2", "ok", 200

        async def mock_clone_2(fid, seed):
            nonlocal r2_clone_called
            r2_clone_called += 1
            return "PASS", {"voice_id": "v_75_2"}, "ok", 200

        routes = [
            ("route_1", mock_up_1, mock_clone_1, None),
            ("route_2", mock_up_2, mock_clone_2, None),
        ]

        res = await voice_clone_pipeline.process_custom_voice_create(
            user_id=70075,
            sample_path=str(wav_path),
            display_name="Voice 75",
            product_context="showroom",
            profile_id=75001,
            route_attempts_func=lambda r, admin_access=False: routes,
            access_allowed_func=lambda *a, **k: True,
            ready_for_processing_func=lambda *a, **k: True,
            readiness={"ready": True},
            output_dir=str(tmp_path),
            make_provider_voice_id_func=lambda u, profile_id=0: "v_75_seed",
        )
        assert res.ok is False
        assert res.outcome_certainty == "AMBIGUOUS"
        assert res.clone_submit_count == 1
        assert r2_clone_called == 0

    asyncio.run(_run())


def test_76_clone_submit_200_missing_provider_voice_id_ambiguous_no_fallback(tmp_path):
    """76: HTTP 200 without valid provider_voice_id defaults to AMBIGUOUS with no cross-route fallback."""
    async def _run():
        wav_path = tmp_path / "sample_76.wav"
        wav_path.write_bytes(_make_wav_bytes(12.0))

        r2_clone_called = 0

        async def mock_up_1(b):
            return "PASS", "file_76_1", "ok", 200

        async def mock_clone_1(fid, seed):
            return "PASS", {"detail": "voice created but id omitted"}, "ok", 200

        async def mock_up_2(b):
            return "PASS", "file_76_2", "ok", 200

        async def mock_clone_2(fid, seed):
            nonlocal r2_clone_called
            r2_clone_called += 1
            return "PASS", {"voice_id": "v_76_2"}, "ok", 200

        routes = [
            ("route_generic", mock_up_1, mock_clone_1, None),
            ("route_2", mock_up_2, mock_clone_2, None),
        ]

        res = await voice_clone_pipeline.process_custom_voice_create(
            user_id=70076,
            sample_path=str(wav_path),
            display_name="Voice 76",
            product_context="showroom",
            profile_id=76001,
            route_attempts_func=lambda r, admin_access=False: routes,
            access_allowed_func=lambda *a, **k: True,
            ready_for_processing_func=lambda *a, **k: True,
            readiness={"ready": True},
            output_dir=str(tmp_path),
            make_provider_voice_id_func=lambda u, profile_id=0: "v_76_seed",
        )
        assert res.ok is False
        assert res.outcome_certainty == "AMBIGUOUS"
        assert res.clone_submit_count == 1
        assert res.metadata.get("ambiguity_reason") == "MISSING_DURABLE_VOICE_ID"
        assert r2_clone_called == 0

    asyncio.run(_run())


def test_77_explicit_deterministic_no_create_rejection_no_second_clone_submit(tmp_path):
    """77: Explicit 4xx provider rejection with deterministic proof sets DETERMINISTIC_FAILURE."""
    async def _run():
        wav_path = tmp_path / "sample_77.wav"
        wav_path.write_bytes(_make_wav_bytes(12.0))

        r2_clone_called = 0

        async def mock_up_1(b):
            return "PASS", "file_77_1", "ok", 200

        async def mock_clone_1(fid, seed):
            return "FAIL", {"error": "audio format corrupt", "deterministic": True}, "Bad Request", 400

        async def mock_up_2(b):
            return "PASS", "file_77_2", "ok", 200

        async def mock_clone_2(fid, seed):
            nonlocal r2_clone_called
            r2_clone_called += 1
            return "PASS", {"voice_id": "v_77_2"}, "ok", 200

        routes = [
            ("route_1", mock_up_1, mock_clone_1, None),
            ("route_2", mock_up_2, mock_clone_2, None),
        ]

        res = await voice_clone_pipeline.process_custom_voice_create(
            user_id=70077,
            sample_path=str(wav_path),
            display_name="Voice 77",
            product_context="showroom",
            profile_id=77001,
            route_attempts_func=lambda r, admin_access=False: routes,
            access_allowed_func=lambda *a, **k: True,
            ready_for_processing_func=lambda *a, **k: True,
            readiness={"ready": True},
            output_dir=str(tmp_path),
            make_provider_voice_id_func=lambda u, profile_id=0: "v_77_seed",
        )
        assert res.ok is False
        assert res.outcome_certainty == "DETERMINISTIC_FAILURE"
        assert res.clone_submit_count == 1
        assert r2_clone_called == 0

    asyncio.run(_run())


def test_78_pre_clone_sample_validation_failure_zero_clone_submits(tmp_path):
    """78: Pre-clone sample validation failure yields clone_submit_count=0."""
    async def _run():
        short_wav = tmp_path / "sample_short_78.wav"
        short_wav.write_bytes(_make_wav_bytes(3.0))

        clone_called = 0

        async def mock_clone(fid, seed):
            nonlocal clone_called
            clone_called += 1
            return "PASS", {"voice_id": "v_78"}, "ok", 200

        routes = [("route_1", None, mock_clone, None)]

        res = await voice_clone_pipeline.process_custom_voice_create(
            user_id=70078,
            sample_path=str(short_wav),
            display_name="Voice 78",
            product_context="showroom",
            profile_id=78001,
            route_attempts_func=lambda r, admin_access=False: routes,
            access_allowed_func=lambda *a, **k: True,
            ready_for_processing_func=lambda *a, **k: True,
            readiness={"ready": True},
            output_dir=str(tmp_path),
        )
        assert res.ok is False
        assert res.outcome_certainty == "DETERMINISTIC_FAILURE"
        assert res.clone_submit_count == 0
        assert res.clone_dispatched is False
        assert clone_called == 0

    asyncio.run(_run())


def test_79_provider_readiness_fail_before_clone_zero_clone_submits(tmp_path):
    """79: Provider readiness failure before clone yields clone_submit_count=0."""
    async def _run():
        wav_path = tmp_path / "sample_79.wav"
        wav_path.write_bytes(_make_wav_bytes(12.0))

        clone_called = 0

        async def mock_clone(fid, seed):
            nonlocal clone_called
            clone_called += 1
            return "PASS", {"voice_id": "v_79"}, "ok", 200

        routes = [("route_1", None, mock_clone, None)]

        res = await voice_clone_pipeline.process_custom_voice_create(
            user_id=70079,
            sample_path=str(wav_path),
            display_name="Voice 79",
            product_context="showroom",
            profile_id=79001,
            route_attempts_func=lambda r, admin_access=False: routes,
            access_allowed_func=lambda *a, **k: True,
            ready_for_processing_func=lambda *a, **k: False,
            readiness={"ready": False},
            output_dir=str(tmp_path),
        )
        assert res.ok is False
        assert res.outcome_certainty == "DETERMINISTIC_FAILURE"
        assert res.clone_submit_count == 0
        assert res.clone_dispatched is False
        assert clone_called == 0

    asyncio.run(_run())


def test_80_first_free_ambiguous_result_quarantined_release_denied(monkeypatch):
    """80: Ambiguous provider result quarantines first-free entitlement and forbids auto-release."""
    client = TestClient(bot.fastapi_app)
    uid = 50080
    setup_user_wallet(uid, balance=0)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)

    async def fake_create(**kwargs):
        return CustomVoiceCreateResult(
            ok=False,
            status="CLONE_NOT_READY",
            error_code="UPSTREAM_504",
            safe_public_message="Upstream gateway timeout",
            outcome_certainty="AMBIGUOUS",
            clone_submit_count=1,
            clone_dispatched=True,
            metadata={"ambiguity_reason": "HTTP_504"},
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_create)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))

    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Free Ambiguous 80"},
        actor_id=str(uid),
    )
    assert res_prep.status_code == 200
    job_id = res_prep.json()["job_id"]

    res_confirm = post_json_auth(client, f"/internal/v1/web-voice-clone/jobs/{job_id}/confirm", None, actor_id=str(uid))
    assert res_confirm.status_code == 504

    ent = get_voice_clone_first_free_entitlement(uid)
    assert ent is not None
    assert ent["state"] == "provider_ambiguous"
    assert ent["released_at"] is None

    job = get_web_voice_clone_job(job_id, uid)
    assert job["status"] == "failed"
    assert job["provider_outcome_state"] == "provider_ambiguous"


def test_81_first_free_ambiguous_result_blocks_subsequent_free_job_zero_second_free_submit(monkeypatch):
    """81: Ambiguous first-free entitlement prevents subsequent job from submitting a second free clone."""
    client = TestClient(bot.fastapi_app)
    uid = 50081
    setup_user_wallet(uid, balance=0)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)

    submits = 0

    async def fake_create(**kwargs):
        nonlocal submits
        submits += 1
        return CustomVoiceCreateResult(
            ok=False,
            status="CLONE_NOT_READY",
            error_code="UPSTREAM_504",
            outcome_certainty="AMBIGUOUS",
            clone_submit_count=1,
            clone_dispatched=True,
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_create)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))

    # Job 1
    res1 = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Job 81-1"},
        actor_id=str(uid),
    )
    j1 = res1.json()["job_id"]
    post_json_auth(client, f"/internal/v1/web-voice-clone/jobs/{j1}/confirm", None, actor_id=str(uid))
    assert submits == 1

    # Job 2 by same user
    upload_id_2 = stage_test_upload(client, wav_bytes, actor_id=str(uid))
    res2 = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id_2, "consent": True, "display_name": "Job 81-2"},
        actor_id=str(uid),
    )
    assert res2.status_code == 200
    j2 = res2.json()["job_id"]

    # Confirm job 2 fails closed before provider dispatch
    res_confirm_2 = post_json_auth(client, f"/internal/v1/web-voice-clone/jobs/{j2}/confirm", None, actor_id=str(uid))
    assert res_confirm_2.status_code == 409
    assert res_confirm_2.json()["error_code"] == "FIRST_FREE_QUARANTINED"
    assert submits == 1  # ZERO second provider clone submit


def test_82_paid_ambiguous_result_zero_wallet_debit_profile_not_ready(monkeypatch):
    """82: Paid job ambiguous result charges 0 Xu and leaves profile in non-ready state."""
    client = TestClient(bot.fastapi_app)
    uid = 50082
    setup_user_wallet(uid, balance=100)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 50)

    async def fake_create(**kwargs):
        return CustomVoiceCreateResult(
            ok=False,
            status="CLONE_NOT_READY",
            error_code="CONNECTION_RESET",
            outcome_certainty="AMBIGUOUS",
            clone_submit_count=1,
            clone_dispatched=True,
            metadata={"ambiguity_reason": "POST_DISPATCH_EXCEPTION:ConnectionResetError"},
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_create)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))

    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Paid Ambiguous 82"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]

    res_confirm = post_json_auth(client, f"/internal/v1/web-voice-clone/jobs/{job_id}/confirm", None, actor_id=str(uid))
    assert res_confirm.status_code == 504

    # Wallet not debited
    with bot.db_connect() as conn:
        bal = conn.execute("SELECT credits FROM users WHERE user_id = ?", (str(uid),)).fetchone()[0]
        assert bal == 100

    job = get_web_voice_clone_job(job_id, uid)
    assert job["status"] == "failed"
    assert job["charged_xu"] == 0
    assert job["provider_outcome_state"] == "provider_ambiguous"


def test_83_reconcile_ambiguous_first_free_no_settle_no_release_no_provider_replay(monkeypatch):
    """83: Reconcile on ambiguous first-free job does not settle, release, or invoke provider."""
    client = TestClient(bot.fastapi_app)
    uid = 50083
    setup_user_wallet(uid, balance=0)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)

    calls = 0

    async def fake_create(**kwargs):
        nonlocal calls
        calls += 1
        return CustomVoiceCreateResult(
            ok=False,
            status="CLONE_NOT_READY",
            error_code="HTTP_504",
            outcome_certainty="AMBIGUOUS",
            clone_submit_count=1,
            clone_dispatched=True,
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_create)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))

    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Reconcile Free 83"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]

    post_json_auth(client, f"/internal/v1/web-voice-clone/jobs/{job_id}/confirm", None, actor_id=str(uid))
    assert calls == 1

    # Call reconcile
    res_rec = post_json_auth(client, f"/internal/v1/web-voice-clone/jobs/{job_id}/reconcile", None, actor_id=str(uid))
    assert res_rec.status_code == 200
    assert calls == 1  # No second provider call

    ent = get_voice_clone_first_free_entitlement(uid)
    assert ent["state"] == "provider_ambiguous"  # Not settled, not released
    assert ent["released_at"] is None


def test_84_reconcile_ambiguous_paid_no_debit_no_provider_replay(monkeypatch):
    """84: Reconcile on ambiguous paid job does not debit wallet or replay provider."""
    client = TestClient(bot.fastapi_app)
    uid = 50084
    setup_user_wallet(uid, balance=100)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 50)

    calls = 0

    async def fake_create(**kwargs):
        nonlocal calls
        calls += 1
        return CustomVoiceCreateResult(
            ok=False,
            status="FAIL",
            error_code="UPSTREAM_502",
            outcome_certainty="AMBIGUOUS",
            clone_submit_count=1,
            clone_dispatched=True,
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_create)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))

    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Reconcile Paid 84"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]

    post_json_auth(client, f"/internal/v1/web-voice-clone/jobs/{job_id}/confirm", None, actor_id=str(uid))
    assert calls == 1

    # Reconcile
    res_rec = post_json_auth(client, f"/internal/v1/web-voice-clone/jobs/{job_id}/reconcile", None, actor_id=str(uid))
    assert res_rec.status_code == 200
    assert calls == 1  # Zero provider replay

    with bot.db_connect() as conn:
        bal = conn.execute("SELECT credits FROM users WHERE user_id = ?", (str(uid),)).fetchone()[0]
        assert bal == 100  # Zero wallet debit


def test_85_pipeline_configured_with_two_clone_routes_total_submits_at_most_one(tmp_path):
    """85: Pipeline with two configured routes dispatches at most one clone submit per job."""
    async def _run():
        wav_path = tmp_path / "sample_85.wav"
        wav_path.write_bytes(_make_wav_bytes(12.0))

        r1_clone_submits = 0
        r2_clone_submits = 0

        async def up_1(b):
            return "PASS", "f_85_1", "ok", 200

        async def clone_1(fid, seed):
            nonlocal r1_clone_submits
            r1_clone_submits += 1
            return "FAIL", {}, "Internal Error", 500

        async def up_2(b):
            return "PASS", "f_85_2", "ok", 200

        async def clone_2(fid, seed):
            nonlocal r2_clone_submits
            r2_clone_submits += 1
            return "PASS", {"voice_id": "v_85_2"}, "ok", 200

        routes = [
            ("shopaikey_minimax", up_1, clone_1, None),
            ("key4u_minimax", up_2, clone_2, None),
        ]

        res = await voice_clone_pipeline.process_custom_voice_create(
            user_id=70085,
            sample_path=str(wav_path),
            display_name="Voice 85",
            product_context="showroom",
            profile_id=85001,
            route_attempts_func=lambda r, admin_access=False: routes,
            access_allowed_func=lambda *a, **k: True,
            ready_for_processing_func=lambda *a, **k: True,
            readiness={"ready": True},
            output_dir=str(tmp_path),
            make_provider_voice_id_func=lambda u, profile_id=0: "v_85_seed",
        )
        assert res.ok is False
        assert r1_clone_submits == 1
        assert r2_clone_submits == 0
        assert res.clone_submit_count == 1
        assert res.clone_submit_count <= 1

    asyncio.run(_run())


def test_86_provider_execution_count_and_clone_submit_count_coherent(monkeypatch):
    """86: provider_execution_count and provider_clone_submit_count remain coherent on success and failure."""
    client = TestClient(bot.fastapi_app)
    uid = 50086
    setup_user_wallet(uid, balance=100)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 50)

    # 1. Success case: both counters are 1
    async def fake_success(**kwargs):
        return CustomVoiceCreateResult(
            ok=True,
            status="SUCCESS",
            profile_id=kwargs.get("profile_id"),
            provider="minimax",
            provider_voice_id="vox_86",
            provider_file_id="pfile_86",
            preview_audio_path="/tmp/p_86.mp3",
            preview_audio_bytes=1000,
            outcome_certainty="SUCCESS",
            clone_submit_count=1,
            clone_dispatched=True,
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_success)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))

    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Job 86 Success"},
        actor_id=str(uid),
    )
    j1 = res_prep.json()["job_id"]
    res_confirm = post_json_auth(client, f"/internal/v1/web-voice-clone/jobs/{j1}/confirm", None, actor_id=str(uid))
    assert res_confirm.status_code == 200
    job1 = get_web_voice_clone_job(j1, uid)
    assert job1["provider_execution_count"] == 1
    assert job1["provider_clone_submit_count"] == 1
    assert job1["provider_execution_count"] == job1["provider_clone_submit_count"]

    # 2. Pre-dispatch fail case: both counters are 0
    async def fake_predispatch_fail(**kwargs):
        return CustomVoiceCreateResult(
            ok=False,
            status="FAIL",
            error_code="sample_missing_or_empty",
            outcome_certainty="DETERMINISTIC_FAILURE",
            clone_submit_count=0,
            clone_dispatched=False,
            failure_stage="PRE_DISPATCH",
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_predispatch_fail)

    upload_id_2 = stage_test_upload(client, wav_bytes, actor_id=str(uid))
    res_prep_2 = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id_2, "consent": True, "display_name": "Job 86 Pre-Fail"},
        actor_id=str(uid),
    )
    j2 = res_prep_2.json()["job_id"]
    res_confirm_2 = post_json_auth(client, f"/internal/v1/web-voice-clone/jobs/{j2}/confirm", None, actor_id=str(uid))
    assert res_confirm_2.status_code == 422
    job2 = get_web_voice_clone_job(j2, uid)
    assert job2["provider_execution_count"] == 0
    assert job2["provider_clone_submit_count"] == 0
    assert job2["provider_execution_count"] == job2["provider_clone_submit_count"]



# ---------------------------------------------------------------------------
# 87-104: R1.4A PROVIDER CERTAINTY AUTHORITY FINALIZATION TESTS
# ---------------------------------------------------------------------------

def test_87_r1_4a_text_contains_timeout_clone_dispatched_false_submit_count_zero():
    """87: Text containing 'timeout' with clone_dispatched=False keeps clone_submit_count=0."""
    res = CustomVoiceCreateResult(
        ok=False,
        status="TIMEOUT",
        safe_public_message="Operation timed out",
        clone_dispatched=False,
        clone_submit_count=0,
    )
    assert res.clone_submit_count == 0
    assert res.clone_dispatched is False
    assert res.outcome_certainty == "DETERMINISTIC_FAILURE"


def test_88_r1_4a_text_contains_network_clone_dispatched_false_submit_count_zero():
    """88: Text containing 'network' with clone_dispatched=False keeps clone_submit_count=0."""
    res = CustomVoiceCreateResult(
        ok=False,
        status="NETWORK_ERROR",
        error_code="network_failure",
        safe_public_message="Network glitch",
        clone_dispatched=False,
        clone_submit_count=0,
    )
    assert res.clone_submit_count == 0
    assert res.clone_dispatched is False
    assert res.outcome_certainty == "DETERMINISTIC_FAILURE"


def test_89_r1_4a_structured_ambiguous_neutral_error_text_quarantine(monkeypatch):
    """89: Structured AMBIGUOUS with neutral error text quarantines first-free entitlement."""
    client = TestClient(bot.fastapi_app)
    uid = 50089
    setup_user_wallet(uid, balance=0)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)

    async def fake_create(**kwargs):
        return CustomVoiceCreateResult(
            ok=False,
            status="FAIL",
            error_code="PROCESSING_UNCONFIRMED",
            safe_public_message="Something unexpected happened",
            outcome_certainty="AMBIGUOUS",
            clone_dispatched=True,
            clone_submit_count=1,
            metadata={"ambiguity_reason": "PROVIDER_OUTCOME_AMBIGUOUS"},
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_create)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))

    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Job 89 Neutral"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]

    res_confirm = post_json_auth(client, f"/internal/v1/web-voice-clone/jobs/{job_id}/confirm", None, actor_id=str(uid))
    assert res_confirm.status_code == 504

    ent = get_voice_clone_first_free_entitlement(uid)
    assert ent["state"] == "provider_ambiguous"
    assert ent["released_at"] is None


def test_90_r1_4a_unknown_certainty_clone_dispatched_true_defaults_ambiguous():
    """90: Unknown certainty with clone_dispatched=True defaults to AMBIGUOUS."""
    res = CustomVoiceCreateResult(
        ok=False,
        status="FAIL",
        outcome_certainty="UNKNOWN",
        clone_dispatched=True,
    )
    assert res.outcome_certainty == "AMBIGUOUS"
    assert res.failure_stage == "POST_DISPATCH"


def test_91_r1_4a_unknown_certainty_clone_submit_count_1_defaults_ambiguous():
    """91: Unknown certainty with clone_submit_count=1 defaults to AMBIGUOUS."""
    res = CustomVoiceCreateResult(
        ok=False,
        status="FAIL",
        outcome_certainty="",
        clone_submit_count=1,
    )
    assert res.outcome_certainty == "AMBIGUOUS"
    assert res.failure_stage == "POST_DISPATCH"


def test_92_r1_4a_http_400_after_dispatch_no_no_create_evidence_ambiguous(tmp_path):
    """92: HTTP 400 after dispatch without explicit no-create evidence defaults to AMBIGUOUS."""
    async def _run():
        wav_path = tmp_path / "sample_92.wav"
        wav_path.write_bytes(_make_wav_bytes(12.0))

        async def up_1(b):
            return "PASS", "f_92", "ok", 200

        async def clone_1(fid, seed):
            return "FAIL", {"error": "bad request"}, "Bad Request", 400

        routes = [("route_1", up_1, clone_1, None)]

        res = await voice_clone_pipeline.process_custom_voice_create(
            user_id=70092,
            sample_path=str(wav_path),
            display_name="Voice 92",
            product_context="showroom",
            profile_id=92001,
            route_attempts_func=lambda r, admin_access=False: routes,
            access_allowed_func=lambda *a, **k: True,
            ready_for_processing_func=lambda *a, **k: True,
            readiness={"ready": True},
            output_dir=str(tmp_path),
            make_provider_voice_id_func=lambda u, profile_id=0: "v_92_seed",
        )
        assert res.ok is False
        assert res.outcome_certainty == "AMBIGUOUS"
        assert res.clone_submit_count == 1

    asyncio.run(_run())


def test_93_r1_4a_http_422_after_dispatch_no_no_create_evidence_ambiguous(tmp_path):
    """93: HTTP 422 after dispatch without explicit no-create evidence defaults to AMBIGUOUS."""
    async def _run():
        wav_path = tmp_path / "sample_93.wav"
        wav_path.write_bytes(_make_wav_bytes(12.0))

        async def up_1(b):
            return "PASS", "f_93", "ok", 200

        async def clone_1(fid, seed):
            return "FAIL", {}, "Unprocessable Entity", 422

        routes = [("route_1", up_1, clone_1, None)]

        res = await voice_clone_pipeline.process_custom_voice_create(
            user_id=70093,
            sample_path=str(wav_path),
            display_name="Voice 93",
            product_context="showroom",
            profile_id=93001,
            route_attempts_func=lambda r, admin_access=False: routes,
            access_allowed_func=lambda *a, **k: True,
            ready_for_processing_func=lambda *a, **k: True,
            readiness={"ready": True},
            output_dir=str(tmp_path),
            make_provider_voice_id_func=lambda u, profile_id=0: "v_93_seed",
        )
        assert res.ok is False
        assert res.outcome_certainty == "AMBIGUOUS"
        assert res.clone_submit_count == 1

    asyncio.run(_run())


def test_94_r1_4a_explicit_structured_no_create_http_400_deterministic_failure(tmp_path):
    """94: Explicit structured no-create with HTTP 400 yields DETERMINISTIC_FAILURE."""
    async def _run():
        wav_path = tmp_path / "sample_94.wav"
        wav_path.write_bytes(_make_wav_bytes(12.0))

        async def up_1(b):
            return "PASS", "f_94", "ok", 200

        async def clone_1(fid, seed):
            return "FAIL", {"no_create_authoritative": True}, "Audio format rejected before clone creation", 400

        routes = [("route_1", up_1, clone_1, None)]

        res = await voice_clone_pipeline.process_custom_voice_create(
            user_id=70094,
            sample_path=str(wav_path),
            display_name="Voice 94",
            product_context="showroom",
            profile_id=94001,
            route_attempts_func=lambda r, admin_access=False: routes,
            access_allowed_func=lambda *a, **k: True,
            ready_for_processing_func=lambda *a, **k: True,
            readiness={"ready": True},
            output_dir=str(tmp_path),
            make_provider_voice_id_func=lambda u, profile_id=0: "v_94_seed",
        )
        assert res.ok is False
        assert res.outcome_certainty == "DETERMINISTIC_FAILURE"
        assert res.failure_stage == "CLONE_REJECTED"
        assert res.clone_submit_count == 1

    asyncio.run(_run())


def test_95_r1_4a_explicit_structured_no_create_no_http_status_deterministic_failure(tmp_path):
    """95: Explicit structured no-create without HTTP status yields DETERMINISTIC_FAILURE."""
    async def _run():
        wav_path = tmp_path / "sample_95.wav"
        wav_path.write_bytes(_make_wav_bytes(12.0))

        async def up_1(b):
            return "PASS", "f_95", "ok", 200

        async def clone_1(fid, seed):
            return "DETERMINISTIC_NO_CREATE", {}, "Explicit no-create business rejection", 0

        routes = [("route_1", up_1, clone_1, None)]

        res = await voice_clone_pipeline.process_custom_voice_create(
            user_id=70095,
            sample_path=str(wav_path),
            display_name="Voice 95",
            product_context="showroom",
            profile_id=95001,
            route_attempts_func=lambda r, admin_access=False: routes,
            access_allowed_func=lambda *a, **k: True,
            ready_for_processing_func=lambda *a, **k: True,
            readiness={"ready": True},
            output_dir=str(tmp_path),
            make_provider_voice_id_func=lambda u, profile_id=0: "v_95_seed",
        )
        assert res.ok is False
        assert res.outcome_certainty == "DETERMINISTIC_FAILURE"
        assert res.failure_stage == "CLONE_REJECTED"
        assert res.clone_submit_count == 1

    asyncio.run(_run())


def test_96_r1_4a_shopaikey_pass_200_missing_durable_result_identity_ambiguous(tmp_path):
    """96: ShopAIKey PASS/200 with missing durable result identity defaults to AMBIGUOUS."""
    async def _run():
        wav_path = tmp_path / "sample_96.wav"
        wav_path.write_bytes(_make_wav_bytes(12.0))

        async def up_1(b):
            return "PASS", "f_96", "ok", 200

        async def clone_1(fid, seed):
            return "PASS", {"status": "ok"}, "ok", 200

        routes = [("shopaikey_minimax", up_1, clone_1, None)]

        res = await voice_clone_pipeline.process_custom_voice_create(
            user_id=70096,
            sample_path=str(wav_path),
            display_name="Voice 96",
            product_context="showroom",
            profile_id=96001,
            route_attempts_func=lambda r, admin_access=False: routes,
            access_allowed_func=lambda *a, **k: True,
            ready_for_processing_func=lambda *a, **k: True,
            readiness={"ready": True},
            output_dir=str(tmp_path),
            make_provider_voice_id_func=lambda u, profile_id=0: "v_96_seed",
        )
        assert res.ok is False
        assert res.outcome_certainty == "AMBIGUOUS"
        assert res.clone_submit_count == 1
        assert res.metadata.get("ambiguity_reason") == "MISSING_DURABLE_VOICE_ID"

    asyncio.run(_run())


def test_97_r1_4a_generic_route_pass_200_missing_result_identity_ambiguous(tmp_path):
    """97: Generic route PASS/200 with missing durable result identity defaults to AMBIGUOUS."""
    async def _run():
        wav_path = tmp_path / "sample_97.wav"
        wav_path.write_bytes(_make_wav_bytes(12.0))

        async def up_1(b):
            return "PASS", "f_97", "ok", 200

        async def clone_1(fid, seed):
            return "PASS", {}, "ok", 200

        routes = [("generic_provider", up_1, clone_1, None)]

        res = await voice_clone_pipeline.process_custom_voice_create(
            user_id=70097,
            sample_path=str(wav_path),
            display_name="Voice 97",
            product_context="showroom",
            profile_id=97001,
            route_attempts_func=lambda r, admin_access=False: routes,
            access_allowed_func=lambda *a, **k: True,
            ready_for_processing_func=lambda *a, **k: True,
            readiness={"ready": True},
            output_dir=str(tmp_path),
            make_provider_voice_id_func=lambda u, profile_id=0: "v_97_seed",
        )
        assert res.ok is False
        assert res.outcome_certainty == "AMBIGUOUS"
        assert res.clone_submit_count == 1
        assert res.metadata.get("ambiguity_reason") == "MISSING_DURABLE_VOICE_ID"

    asyncio.run(_run())


def test_98_r1_4a_shopaikey_structured_authoritative_requested_id_success(tmp_path):
    """98: ShopAIKey with structured authoritative requested-ID evidence yields SUCCESS."""
    async def _run():
        wav_path = tmp_path / "sample_98.wav"
        wav_path.write_bytes(_make_wav_bytes(12.0))

        auth_voice_id = "toanaas-custom-user-98authvoice"

        async def up_1(b):
            return "PASS", "f_98", "ok", 200

        async def clone_1(fid, seed):
            return "PASS", {"provider_result_identity_authoritative": True, "provider_result_identity": auth_voice_id}, "ok", 200

        routes = [("shopaikey_minimax", up_1, clone_1, None)]

        res = await voice_clone_pipeline.process_custom_voice_create(
            user_id=70098,
            sample_path=str(wav_path),
            display_name="Voice 98",
            product_context="showroom",
            profile_id=98001,
            route_attempts_func=lambda r, admin_access=False: routes,
            access_allowed_func=lambda *a, **k: True,
            ready_for_processing_func=lambda *a, **k: True,
            readiness={"ready": True},
            output_dir=str(tmp_path),
            make_provider_voice_id_func=lambda u, profile_id=0: auth_voice_id,
        )
        assert res.ok is True
        assert res.outcome_certainty == "SUCCESS"
        assert res.provider_voice_id == auth_voice_id

    asyncio.run(_run())


def test_99_r1_4a_bot_confirm_structured_ambiguous_no_timeout_network_words(monkeypatch):
    """99: Bot confirm with structured AMBIGUOUS and no timeout/network words marks provider_ambiguous."""
    client = TestClient(bot.fastapi_app)
    uid = 50099
    setup_user_wallet(uid, balance=0)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)

    async def fake_create(**kwargs):
        return CustomVoiceCreateResult(
            ok=False,
            status="GENERIC_FAILURE",
            error_code="CLONE_HALTED",
            safe_public_message="Service interrupted",
            outcome_certainty="AMBIGUOUS",
            clone_dispatched=True,
            clone_submit_count=1,
            metadata={"ambiguity_reason": "PROVIDER_OUTCOME_AMBIGUOUS"},
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_create)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))

    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Job 99 No-String"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]

    res_confirm = post_json_auth(client, f"/internal/v1/web-voice-clone/jobs/{job_id}/confirm", None, actor_id=str(uid))
    assert res_confirm.status_code == 504

    job = get_web_voice_clone_job(job_id, uid)
    assert job["provider_outcome_state"] == "provider_ambiguous"


def test_100_r1_4a_explicit_deterministic_failure_with_timeout_word_remains_deterministic(monkeypatch):
    """100: Explicit deterministic failure with 'timeout' in message remains deterministic (string cannot override)."""
    client = TestClient(bot.fastapi_app)
    uid = 50100
    setup_user_wallet(uid, balance=0)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)

    async def fake_create(**kwargs):
        return CustomVoiceCreateResult(
            ok=False,
            status="DETERMINISTIC_FAILURE",
            error_code="SAMPLE_TIMEOUT_POLICY_REJECTED",
            safe_public_message="Audio sample processing timeout exceeded validation rule",
            outcome_certainty="DETERMINISTIC_FAILURE",
            clone_dispatched=False,
            clone_submit_count=0,
            failure_stage="PRE_DISPATCH",
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_create)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))

    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Job 100 Det-Timeout"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]

    res_confirm = post_json_auth(client, f"/internal/v1/web-voice-clone/jobs/{job_id}/confirm", None, actor_id=str(uid))
    assert res_confirm.status_code == 422

    job = get_web_voice_clone_job(job_id, uid)
    assert job["provider_outcome_state"] == "provider_failed"

    ent = get_voice_clone_first_free_entitlement(uid)
    assert ent["state"] == "released"


def test_101_r1_4a_max_provider_clone_submits_per_job_enforced_single_submit(tmp_path):
    """101: MAX_PROVIDER_CLONE_SUBMITS_PER_JOB=1 strictly enforced across multiple routes."""
    async def _run():
        wav_path = tmp_path / "sample_101.wav"
        wav_path.write_bytes(_make_wav_bytes(12.0))

        route1_clone_called = 0
        route2_clone_called = 0
        route3_clone_called = 0

        async def up(b):
            return "PASS", "f_101", "ok", 200

        async def clone_1(fid, seed):
            nonlocal route1_clone_called
            route1_clone_called += 1
            return "FAIL", {}, "Upstream fail", 500

        async def clone_2(fid, seed):
            nonlocal route2_clone_called
            route2_clone_called += 1
            return "PASS", {"voice_id": "v_101_2"}, "ok", 200

        async def clone_3(fid, seed):
            nonlocal route3_clone_called
            route3_clone_called += 1
            return "PASS", {"voice_id": "v_101_3"}, "ok", 200

        routes = [
            ("route_1", up, clone_1, None),
            ("route_2", up, clone_2, None),
            ("route_3", up, clone_3, None),
        ]

        res = await voice_clone_pipeline.process_custom_voice_create(
            user_id=70101,
            sample_path=str(wav_path),
            display_name="Voice 101",
            product_context="showroom",
            profile_id=101001,
            route_attempts_func=lambda r, admin_access=False: routes,
            access_allowed_func=lambda *a, **k: True,
            ready_for_processing_func=lambda *a, **k: True,
            readiness={"ready": True},
            output_dir=str(tmp_path),
            make_provider_voice_id_func=lambda u, profile_id=0: "v_101_seed",
        )
        assert res.ok is False
        assert res.clone_submit_count == 1
        assert route1_clone_called == 1
        assert route2_clone_called == 0
        assert route3_clone_called == 0

    asyncio.run(_run())


def test_102_r1_4a_first_free_ambiguous_entitlement_remains_quarantined(monkeypatch):
    """102: First-free ambiguous entitlement remains quarantined, preventing release and new jobs."""
    client = TestClient(bot.fastapi_app)
    uid = 50102
    setup_user_wallet(uid, balance=0)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 0)

    async def fake_create(**kwargs):
        return CustomVoiceCreateResult(
            ok=False,
            status="TIMEOUT",
            error_code="UPSTREAM_504",
            outcome_certainty="AMBIGUOUS",
            clone_dispatched=True,
            clone_submit_count=1,
            metadata={"ambiguity_reason": "HTTP_504"},
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_create)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))

    res_prep1 = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Job 102 First"},
        actor_id=str(uid),
    )
    j1 = res_prep1.json()["job_id"]
    post_json_auth(client, f"/internal/v1/web-voice-clone/jobs/{j1}/confirm", None, actor_id=str(uid))

    ent = get_voice_clone_first_free_entitlement(uid)
    assert ent["state"] == "provider_ambiguous"
    assert ent["released_at"] is None

    # New job attempt for same user must be rejected
    upload_id2 = stage_test_upload(client, wav_bytes, actor_id=str(uid))
    res_prep2 = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id2, "consent": True, "display_name": "Job 102 Second"},
        actor_id=str(uid),
    )
    j2 = res_prep2.json()["job_id"]
    res_confirm2 = post_json_auth(client, f"/internal/v1/web-voice-clone/jobs/{j2}/confirm", None, actor_id=str(uid))
    assert res_confirm2.status_code == 409
    assert res_confirm2.json()["error_code"] == "FIRST_FREE_QUARANTINED"


def test_103_r1_4a_paid_ambiguous_wallet_debit_zero(monkeypatch):
    """103: Ambiguous paid job results in exactly zero wallet debit and profile not activated."""
    client = TestClient(bot.fastapi_app)
    uid = 50103
    setup_user_wallet(uid, balance=100)
    monkeypatch.setattr(bot, "voice_profile_storage_price_xu", lambda u: 50)

    async def fake_create(**kwargs):
        return CustomVoiceCreateResult(
            ok=False,
            status="GATEWAY_TIMEOUT",
            error_code="UPSTREAM_504",
            outcome_certainty="AMBIGUOUS",
            clone_dispatched=True,
            clone_submit_count=1,
            metadata={"ambiguity_reason": "HTTP_504"},
        )

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_custom_voice_create", fake_create)

    wav_bytes = _make_wav_bytes(12.0)
    upload_id = stage_test_upload(client, wav_bytes, actor_id=str(uid))

    res_prep = post_json_auth(
        client,
        "/internal/v1/web-voice-clone/jobs",
        {"upload_id": upload_id, "consent": True, "display_name": "Job 103 Paid"},
        actor_id=str(uid),
    )
    job_id = res_prep.json()["job_id"]

    res_confirm = post_json_auth(client, f"/internal/v1/web-voice-clone/jobs/{job_id}/confirm", None, actor_id=str(uid))
    assert res_confirm.status_code == 504

    with bot.db_connect() as conn:
        bal = conn.execute("SELECT credits FROM users WHERE user_id = ?", (str(uid),)).fetchone()[0]
        assert bal == 100

    job = get_web_voice_clone_job(job_id, uid)
    assert job["status"] == "failed"
    assert job["charged_xu"] == 0
    assert job["provider_outcome_state"] == "provider_ambiguous"


def test_104_r1_4a_real_concurrent_first_free_regression_remains_pass():
    """104: Real concurrent first-free reservation race allows exactly 1 reservation winner."""
    import threading
    uid = 50104
    job_ids = [f"job_104_{i}" for i in range(10)]
    results = []

    def _acquire(jid):
        ok, reason, rec = acquire_voice_clone_first_free_reservation(
            user_id=uid,
            job_id=jid,
            claim_token=f"claim_{jid}",
        )
        results.append((jid, ok, reason))

    threads = [threading.Thread(target=_acquire, args=(jid,)) for jid in job_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    winners = [r for r in results if r[1] is True]
    losers = [r for r in results if r[1] is False]
    assert len(winners) == 1
    assert len(losers) == 9


