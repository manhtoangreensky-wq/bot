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


