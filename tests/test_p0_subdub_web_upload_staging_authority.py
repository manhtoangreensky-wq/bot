"""Unit and contract tests for Bot Core canonical SubDub Web upload staging authority.

SPEC_ID: BOT-SUBDUB-D1-UPLOAD-STAGING-AUTHORITY
Verifies:
- POST /internal/v1/uploads (CREATE upload staging contract)
  - Rejects missing/invalid internal auth
  - Requires authenticated server actor, rejects client owner forge
  - Generates opaque, server-controlled upload_id
  - Rejects empty payload
  - Validates MIME type and content signatures (mp4, webm, mov, mp3, wav, srt, etc.)
  - Validates size limits
  - Rejects raw browser filesystem paths and unverified remote URLs
  - Does NOT leak physical filesystem paths
- GET /internal/v1/uploads/{upload_id} (Owner-bound LOOKUP / CONSUME contract)
  - Rejects missing/invalid internal auth
  - Allows same-owner lookup and returns verified staged metadata
  - Rejects cross-owner access (403 Forbidden)
  - Fail-closed on missing / invalid upload_id (404 / 400)
  - Does NOT leak physical filesystem paths
- Persistence and lifecycle:
  - Staged upload survives DB re-read and points to real staged bytes
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import time
import pytest
from fastapi.testclient import TestClient

import bot
from services.admin_wallet_service import compute_internal_admin_wallet_signature


TEST_TOKEN = "test-subdub-bridge-token"
TEST_SECRET = "test-subdub-hmac-secret"

# Valid minimal MP4 sample (ftyp box with isom brand)
SAMPLE_MP4_BYTES = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41\x00\x00\x00\x08free"
# Valid minimal WAV sample (RIFF WAVE)
SAMPLE_WAV_BYTES = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
# Valid minimal SRT sample
SAMPLE_SRT_BYTES = "1\n00:00:01,000 --> 00:00:03,000\nXin chào TOAN AAS\n".encode("utf-8")


@pytest.fixture(autouse=True)
def setup_isolated_test_env(tmp_path: Path, monkeypatch):
    """Setup isolated test database, staging workspace, and bridge credentials."""
    db_file = tmp_path / "test_subdub_staging.db"
    staging_dir = tmp_path / "staging_media"
    staging_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(bot, "DB_FILE", str(db_file))
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", TEST_SECRET)
    monkeypatch.setenv("SUBDUB_UPLOAD_STAGING_DIR", str(staging_dir))
    monkeypatch.setenv("SUBDUB_UPLOAD_MAX_MB", "50")

    bot.init_db()
    return {"db_file": str(db_file), "staging_dir": str(staging_dir)}


def make_auth_headers(
    method: str,
    path: str,
    body: bytes = b"",
    actor_id: str = "",
    token: str = TEST_TOKEN,
    secret: str = TEST_SECRET,
    timestamp: str | None = None,
    request_id: str | None = None,
) -> dict[str, str]:
    """Helper to compute valid canonical HMAC authentication headers."""
    ts = timestamp if timestamp is not None else str(int(time.time()))
    req_id = request_id if request_id is not None else f"req-test-{time.time_ns()}"
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


# ---------------------------------------------------------------------------
# FIRST RED Assertion: Endpoints MUST exist and adhere to contract
# ---------------------------------------------------------------------------

def test_first_red_post_internal_upload_contract_missing():
    """Prove that POST /internal/v1/uploads exists and is not 404."""
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/uploads"
    payload = {
        "file_name": "test.mp4",
        "content_type": "video/mp4",
        "content_base64": base64.b64encode(SAMPLE_MP4_BYTES).decode("ascii"),
        "sha256": hashlib.sha256(SAMPLE_MP4_BYTES).hexdigest(),
        "idempotency_key": "test-idem-001",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="10001")

    res = client.post(path, content=body, headers=headers)
    # FIRST RED assertion: on current base this will fail because the route does not exist (returns 404)
    assert res.status_code != 404, f"POST_INTERNAL_UPLOAD_CONTRACT_MISSING: got {res.status_code}"
    assert res.status_code == 200, f"Expected 200 from CREATE, got {res.status_code}: {res.text}"
    data = res.json()
    assert data.get("ok") is True
    assert "upload_id" in data
    assert data["upload_id"].startswith("upl_")


def test_first_red_owner_bound_upload_consume_missing():
    """Prove that GET /internal/v1/uploads/{id} exists and is not 404."""
    client = TestClient(bot.fastapi_app)
    # First create
    create_path = "/internal/v1/uploads"
    payload = {
        "file_name": "test_audio.wav",
        "content_type": "audio/wav",
        "content_base64": base64.b64encode(SAMPLE_WAV_BYTES).decode("ascii"),
        "sha256": hashlib.sha256(SAMPLE_WAV_BYTES).hexdigest(),
        "idempotency_key": "test-idem-consume-001",
    }
    create_body = json.dumps(payload).encode("utf-8")
    create_headers = make_auth_headers("POST", create_path, body=create_body, actor_id="10001")
    res_create = client.post(create_path, content=create_body, headers=create_headers)

    assert res_create.status_code == 200, f"Setup upload failed: {res_create.status_code}: {res_create.text}"
    upload_id = res_create.json()["upload_id"]

    # Now consume / lookup
    consume_path = f"/internal/v1/uploads/{upload_id}"
    consume_headers = make_auth_headers("GET", consume_path, actor_id="10001")
    res_get = client.get(consume_path, headers=consume_headers)

    # FIRST RED assertion: on current base this will fail
    assert res_get.status_code != 404, f"OWNER_BOUND_UPLOAD_CONSUME_MISSING: got {res_get.status_code}"
    assert res_get.status_code == 200
    consume_data = res_get.json()
    assert consume_data.get("ok") is True
    assert consume_data.get("upload_id") == upload_id
    assert consume_data.get("owner_id") == "10001"
    # Never leak internal server paths
    assert "local_path" not in consume_data
    assert "internal_path" not in consume_data


# ---------------------------------------------------------------------------
# Section 2: Security, Owner-Binding, and Fail-Closed Tests
# ---------------------------------------------------------------------------

def test_upload_unauthenticated_requests():
    """Unauthenticated requests must be rejected fail-closed with 401."""
    client = TestClient(bot.fastapi_app)
    # POST without auth
    res_post = client.post("/internal/v1/uploads", json={"file_name": "x.mp4"})
    assert res_post.status_code == 401

    # GET without auth
    res_get = client.get("/internal/v1/uploads/upl_test123")
    assert res_get.status_code == 401


def test_upload_cross_owner_access_denied():
    """A user cannot lookup or consume another user's staged upload (403 Forbidden)."""
    client = TestClient(bot.fastapi_app)
    # User 10001 creates upload
    path = "/internal/v1/uploads"
    payload = {
        "file_name": "private.mp4",
        "content_type": "video/mp4",
        "content_base64": base64.b64encode(SAMPLE_MP4_BYTES).decode("ascii"),
        "sha256": hashlib.sha256(SAMPLE_MP4_BYTES).hexdigest(),
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="10001")
    res = client.post(path, content=body, headers=headers)
    assert res.status_code == 200
    upload_id = res.json()["upload_id"]

    # User 10002 attempts to access user 10001's upload
    lookup_path = f"/internal/v1/uploads/{upload_id}"
    lookup_headers = make_auth_headers("GET", lookup_path, actor_id="10002")
    res_other = client.get(lookup_path, headers=lookup_headers)
    assert res_other.status_code == 403, f"Expected 403 for cross-owner access, got {res_other.status_code}"
    assert res_other.json().get("error_code") in {"FORBIDDEN_CROSS_OWNER", "OWNER_MISMATCH"}


def test_upload_client_owner_forge_rejected():
    """Client attempting to forge/supply a conflicting user_id in body must be rejected."""
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/uploads"
    payload = {
        "file_name": "forged.mp4",
        "content_type": "video/mp4",
        "content_base64": base64.b64encode(SAMPLE_MP4_BYTES).decode("ascii"),
        "sha256": hashlib.sha256(SAMPLE_MP4_BYTES).hexdigest(),
        "user_id": "99999",  # Attempting to forge owner
    }
    body = json.dumps(payload).encode("utf-8")
    # Authenticated actor is 10001
    headers = make_auth_headers("POST", path, body=body, actor_id="10001")
    res = client.post(path, content=body, headers=headers)
    assert res.status_code in {401, 403}, f"Forged user_id should be rejected, got {res.status_code}"


def test_upload_unknown_or_invalid_id_fail_closed():
    """Unknown upload_id yields 404, invalid characters yield 400 or 404."""
    client = TestClient(bot.fastapi_app)
    # Unknown ID
    unknown_path = "/internal/v1/uploads/upl_nonexistent_999999"
    headers_unknown = make_auth_headers("GET", unknown_path, actor_id="10001")
    res_unk = client.get(unknown_path, headers=headers_unknown)
    assert res_unk.status_code == 404

    # Invalid path traversal or malformed ID
    bad_path = "/internal/v1/uploads/..%2F..%2Fetc%2Fpasswd"
    headers_bad = make_auth_headers("GET", bad_path, actor_id="10001")
    res_bad = client.get(bad_path, headers=headers_bad)
    assert res_bad.status_code in {400, 404}


# ---------------------------------------------------------------------------
# Section 3: MIME & Size Validation Tests
# ---------------------------------------------------------------------------

def test_upload_reject_empty_payload():
    """Empty payload or 0-byte file must be rejected fail-closed (400 or 422)."""
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/uploads"
    payload = {
        "file_name": "empty.mp4",
        "content_type": "video/mp4",
        "content_base64": "",  # Empty
        "sha256": hashlib.sha256(b"").hexdigest(),
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="10001")
    res = client.post(path, content=body, headers=headers)
    assert res.status_code in {400, 422}
    assert res.json().get("error_code") in {"EMPTY_PAYLOAD", "INVALID_FILE_SIZE"}


def test_upload_reject_invalid_mime():
    """Executable or forbidden MIME types must be rejected (400 or 422)."""
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/uploads"
    payload = {
        "file_name": "malicious.exe",
        "content_type": "application/x-msdownload",
        "content_base64": base64.b64encode(b"MZ\x90\x00binary").decode("ascii"),
        "sha256": hashlib.sha256(b"MZ\x90\x00binary").hexdigest(),
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="10001")
    res = client.post(path, content=body, headers=headers)
    assert res.status_code in {400, 422}
    assert "MIME" in res.json().get("error_code", "") or "TYPE" in res.json().get("error_code", "")


def test_upload_reject_size_exceeded(monkeypatch):
    """File exceeding SUBDUB_UPLOAD_MAX_MB must be rejected (413 or 400)."""
    monkeypatch.setenv("SUBDUB_UPLOAD_MAX_MB", "1")  # 1 MB limit
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/uploads"
    oversized_bytes = SAMPLE_MP4_BYTES + (b"\x00" * (2 * 1024 * 1024))  # 2 MB
    payload = {
        "file_name": "large.mp4",
        "content_type": "video/mp4",
        "content_base64": base64.b64encode(oversized_bytes).decode("ascii"),
        "sha256": hashlib.sha256(oversized_bytes).hexdigest(),
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="10001")
    res = client.post(path, content=body, headers=headers)
    assert res.status_code in {413, 400}


# ---------------------------------------------------------------------------
# Section 4: Authority Boundary Tests (D1-08)
# ---------------------------------------------------------------------------

def test_upload_reject_browser_local_path_as_authority():
    """Client cannot supply a local file path instead of uploading actual media bytes."""
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/uploads"
    payload = {
        "file_name": "video.mp4",
        "content_type": "video/mp4",
        "local_path": "C:\\Users\\Administrator\\Desktop\\secret.mp4",  # Fake authority attempt
        "file_path": "/etc/passwd",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="10001")
    res = client.post(path, content=body, headers=headers)
    assert res.status_code in {400, 422}


def test_upload_reject_arbitrary_remote_url_as_authority():
    """Client cannot supply an arbitrary external media URL as storage authority."""
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/uploads"
    payload = {
        "file_name": "video.mp4",
        "content_type": "video/mp4",
        "url": "https://youtube.com/watch?v=12345",  # Fake authority attempt
        "remote_url": "https://malicious.site/video.mp4",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="10001")
    res = client.post(path, content=body, headers=headers)
    assert res.status_code in {400, 422}


# ---------------------------------------------------------------------------
# Section 5: Persistence and Lifecycle (D1-09)
# ---------------------------------------------------------------------------

def test_upload_persistence_across_connections():
    """Staged upload record is stored durably in system_settings and resolved across connection restarts."""
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/uploads"
    payload = {
        "file_name": "subtitle.srt",
        "content_type": "text/plain",
        "content_base64": base64.b64encode(SAMPLE_SRT_BYTES).decode("ascii"),
        "sha256": hashlib.sha256(SAMPLE_SRT_BYTES).hexdigest(),
        "idempotency_key": "srt-idem-persist-01",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="10001")
    res = client.post(path, content=body, headers=headers)
    assert res.status_code == 200
    upload_id = res.json()["upload_id"]

    # Read direct from DB system_settings to verify durability
    setting_val = bot.get_system_setting(f"subdub_upload:{upload_id}")
    assert setting_val, "Upload metadata must be stored in system_settings"
    persisted = json.loads(setting_val)
    assert persisted["upload_id"] == upload_id
    assert persisted["owner_id"] == "10001"
    assert persisted["sha256"] == hashlib.sha256(SAMPLE_SRT_BYTES).hexdigest()
    assert Path(persisted["local_path"]).exists()
    assert Path(persisted["local_path"]).read_bytes() == SAMPLE_SRT_BYTES

    # Re-read via GET endpoint
    lookup_headers = make_auth_headers("GET", f"/internal/v1/uploads/{upload_id}", actor_id="10001")
    res_get = client.get(f"/internal/v1/uploads/{upload_id}", headers=lookup_headers)
    assert res_get.status_code == 200
    assert res_get.json()["sha256"] == persisted["sha256"]
