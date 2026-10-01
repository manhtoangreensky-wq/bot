"""Unit and contract tests for Bot Core canonical SubDub Web media preflight authority.

SPEC_ID: BOT-SUBDUB-D2-MEDIA-PREFLIGHT
Verifies:
- POST /internal/v1/uploads/{upload_id}/preflight (Media Preflight Authority)
  - Rejects missing/invalid internal auth
  - Requires owner-bound upload from D1 staging
  - Server-probed duration is authority (client duration_seconds is NOT)
  - Corrupt/empty media fail closed with deterministic error_code
  - Probe failure (timeout, ffprobe error) fail closed
  - Cross-owner access rejected (403)
  - Unknown/invalid upload_id fail closed (404/400)
  - Does NOT leak physical filesystem paths or provider internals
  - Returns canonical preflight_passed boolean
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch
import time
import pytest
from fastapi.testclient import TestClient

import bot
from services.admin_wallet_service import compute_internal_admin_wallet_signature


TEST_TOKEN = "test-subdub-bridge-token"
TEST_SECRET = "test-subdub-hmac-secret"

# Valid minimal MP4 sample (ftyp box with isom brand)
SAMPLE_MP4_BYTES = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41\x00\x00\x00\x08free"


@pytest.fixture(autouse=True)
def setup_isolated_test_env(tmp_path: Path, monkeypatch):
    """Setup isolated test database, staging workspace, and bridge credentials."""
    db_file = tmp_path / "test_d2_preflight.db"
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


def _create_upload(client, actor_id="10001", file_bytes=SAMPLE_MP4_BYTES, file_name="test.mp4", content_type="video/mp4"):
    """Helper: create a D1 staged upload and return (upload_id, status_code)."""
    path = "/internal/v1/uploads"
    payload = {
        "file_name": file_name,
        "content_type": content_type,
        "content_base64": base64.b64encode(file_bytes).decode("ascii"),
        "sha256": hashlib.sha256(file_bytes).hexdigest(),
        "idempotency_key": f"test-d2-{time.time_ns()}",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id=actor_id)
    res = client.post(path, content=body, headers=headers)
    if res.status_code == 200:
        return res.json()["upload_id"], res.status_code
    return None, res.status_code


# ---------------------------------------------------------------------------
# FIRST RED: Prove endpoint existence
# ---------------------------------------------------------------------------

def test_first_red_preflight_endpoint_exists():
    """FIRST RED: POST /internal/v1/uploads/{upload_id}/preflight MUST exist (not 404/405)."""
    client = TestClient(bot.fastapi_app)
    upload_id, sc = _create_upload(client)
    assert sc == 200 and upload_id, f"D1 setup failed: {sc}"

    path = f"/internal/v1/uploads/{upload_id}/preflight"
    body = json.dumps({}).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="10001")
    res = client.post(path, content=body, headers=headers)

    assert res.status_code not in (404, 405), (
        f"OWNER_BOUND_MEDIA_PREFLIGHT_CONTRACT_MISSING: got {res.status_code}"
    )


# ---------------------------------------------------------------------------
# Server-probed duration is authority, client duration is NOT
# ---------------------------------------------------------------------------

def test_server_probed_duration_authority_not_client():
    """Client sends duration_seconds=9999 in body, but server MUST use probe result, not client value."""
    client = TestClient(bot.fastapi_app)
    upload_id, sc = _create_upload(client)
    assert sc == 200 and upload_id

    fake_probe_duration = 42.5
    mock_probe_result = {
        "ok": True,
        "detail": "probed",
        "duration": fake_probe_duration,
        "has_video": True,
        "has_audio": True,
        "size": len(SAMPLE_MP4_BYTES),
    }

    path = f"/internal/v1/uploads/{upload_id}/preflight"
    body = json.dumps({"duration_seconds": 9999}).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="10001")

    with patch.object(bot, "subdub_probe_video_bytes", new_callable=AsyncMock, return_value=mock_probe_result):
        res = client.post(path, content=body, headers=headers)

    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    data = res.json()
    assert data.get("ok") is True
    # Server MUST use probed duration, NOT client-sent 9999
    assert data.get("duration_seconds") == 43 or data.get("duration_seconds") == 42, (
        f"Duration should come from server probe (~42-43s), got {data.get('duration_seconds')}"
    )
    assert data.get("duration_seconds") != 9999, "FATAL: Client duration_seconds used as authority!"
    assert data.get("detected_duration_source") == "ffprobe"


# ---------------------------------------------------------------------------
# Cross-owner access rejected
# ---------------------------------------------------------------------------

def test_cross_owner_preflight_rejected():
    """Actor 20002 MUST NOT preflight upload owned by 10001."""
    client = TestClient(bot.fastapi_app)
    upload_id, sc = _create_upload(client, actor_id="10001")
    assert sc == 200 and upload_id

    path = f"/internal/v1/uploads/{upload_id}/preflight"
    body = json.dumps({}).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="20002")
    res = client.post(path, content=body, headers=headers)

    assert res.status_code == 403, f"Expected 403, got {res.status_code}: {res.text}"
    data = res.json()
    assert data.get("ok") is False
    assert "FORBIDDEN" in data.get("error_code", "").upper()


# ---------------------------------------------------------------------------
# Unknown / invalid upload_id
# ---------------------------------------------------------------------------

def test_unknown_upload_id_fail_closed():
    """Nonexistent upload_id MUST return 404, not 200."""
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/uploads/upl_00000000000000000000000000000000/preflight"
    body = json.dumps({}).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="10001")
    res = client.post(path, content=body, headers=headers)

    assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
    data = res.json()
    assert data.get("ok") is False


def test_invalid_upload_id_format_fail_closed():
    """Clearly invalid upload_id MUST return 400."""
    client = TestClient(bot.fastapi_app)
    # Use a very long ID that exceeds the 80-char limit
    long_id = "a" * 100
    path = f"/internal/v1/uploads/{long_id}/preflight"
    body = json.dumps({}).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="10001")
    res = client.post(path, content=body, headers=headers)

    assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"
    data = res.json()
    assert data.get("ok") is False


# ---------------------------------------------------------------------------
# Probe failure fail-closed (NOT duration=0 then pass)
# ---------------------------------------------------------------------------

def test_probe_failure_fail_closed():
    """If ffprobe returns ok=False (probe error), preflight MUST fail closed — NOT pass with duration=0."""
    client = TestClient(bot.fastapi_app)
    upload_id, sc = _create_upload(client)
    assert sc == 200 and upload_id

    mock_probe_result = {
        "ok": False,
        "detail": "ffprobe_error",
        "duration": 0.0,
        "has_video": False,
        "has_audio": False,
        "size": len(SAMPLE_MP4_BYTES),
    }

    path = f"/internal/v1/uploads/{upload_id}/preflight"
    body = json.dumps({}).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="10001")

    with patch.object(bot, "subdub_probe_video_bytes", new_callable=AsyncMock, return_value=mock_probe_result):
        res = client.post(path, content=body, headers=headers)

    assert res.status_code == 422, f"Expected 422, got {res.status_code}: {res.text}"
    data = res.json()
    assert data.get("ok") is False
    assert data.get("error_code"), "Must have deterministic error_code on probe failure"
    assert "PROBE" in data.get("error_code", "").upper() or "MEDIA" in data.get("error_code", "").upper()


def test_probe_timeout_fail_closed():
    """If ffprobe returns detail=ffprobe_timeout, preflight MUST fail closed."""
    client = TestClient(bot.fastapi_app)
    upload_id, sc = _create_upload(client)
    assert sc == 200 and upload_id

    mock_probe_result = {
        "ok": False,
        "detail": "ffprobe_timeout",
        "duration": 0.0,
        "has_video": False,
        "has_audio": False,
        "size": len(SAMPLE_MP4_BYTES),
    }

    path = f"/internal/v1/uploads/{upload_id}/preflight"
    body = json.dumps({}).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="10001")

    with patch.object(bot, "subdub_probe_video_bytes", new_callable=AsyncMock, return_value=mock_probe_result):
        res = client.post(path, content=body, headers=headers)

    assert res.status_code == 422, f"Expected 422, got {res.status_code}: {res.text}"
    data = res.json()
    assert data.get("ok") is False
    assert data.get("error_code"), "Must have deterministic error_code on probe timeout"


def test_empty_media_bytes_fail_closed():
    """Upload with 0-byte content MUST fail closed on preflight, not pass with duration=0."""
    client = TestClient(bot.fastapi_app)
    upload_id, sc = _create_upload(client, file_bytes=b"", file_name="empty.mp4")
    # D1 may reject empty file directly; if it does, the test passes trivially (fail-closed at D1 layer)
    if sc != 200 or not upload_id:
        return  # D1 already fail-closed on empty payload

    mock_probe_result = {
        "ok": False,
        "detail": "empty_video",
        "duration": 0.0,
        "has_video": False,
        "has_audio": False,
        "size": 0,
    }

    path = f"/internal/v1/uploads/{upload_id}/preflight"
    body = json.dumps({}).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="10001")

    with patch.object(bot, "subdub_probe_video_bytes", new_callable=AsyncMock, return_value=mock_probe_result):
        res = client.post(path, content=body, headers=headers)

    assert res.status_code == 422, f"Expected 422 for empty media, got {res.status_code}: {res.text}"
    data = res.json()
    assert data.get("ok") is False


# ---------------------------------------------------------------------------
# No internal path leakage
# ---------------------------------------------------------------------------

def test_preflight_no_internal_path_leakage():
    """Preflight response MUST NOT contain local_path, staging_dir, or any filesystem path."""
    client = TestClient(bot.fastapi_app)
    upload_id, sc = _create_upload(client)
    assert sc == 200 and upload_id

    mock_probe_result = {
        "ok": True,
        "detail": "probed",
        "duration": 10.0,
        "has_video": True,
        "has_audio": True,
        "size": len(SAMPLE_MP4_BYTES),
    }

    path = f"/internal/v1/uploads/{upload_id}/preflight"
    body = json.dumps({}).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="10001")

    with patch.object(bot, "subdub_probe_video_bytes", new_callable=AsyncMock, return_value=mock_probe_result):
        res = client.post(path, content=body, headers=headers)

    raw = res.text
    for leak in ["local_path", "staging_dir", "C:\\", "/tmp/", "\\Users\\", "/home/"]:
        assert leak not in raw, f"FATAL PATH LEAK: '{leak}' found in response"


# ---------------------------------------------------------------------------
# Auth required
# ---------------------------------------------------------------------------

def test_preflight_requires_auth():
    """Preflight MUST reject unauthenticated requests."""
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/uploads/upl_00000000000000000000000000000000/preflight"
    body = json.dumps({}).encode("utf-8")
    # No auth headers at all
    res = client.post(path, content=body, headers={"Content-Type": "application/json"})
    assert res.status_code in (401, 403), f"Expected 401/403 without auth, got {res.status_code}"


# ---------------------------------------------------------------------------
# Preflight returns canonical fields
# ---------------------------------------------------------------------------

def test_preflight_returns_canonical_fields():
    """Preflight response MUST contain ok, upload_id, duration_seconds, preflight_passed, detected_duration_source."""
    client = TestClient(bot.fastapi_app)
    upload_id, sc = _create_upload(client)
    assert sc == 200 and upload_id

    mock_probe_result = {
        "ok": True,
        "detail": "probed",
        "duration": 25.0,
        "has_video": True,
        "has_audio": True,
        "size": len(SAMPLE_MP4_BYTES),
    }

    path = f"/internal/v1/uploads/{upload_id}/preflight"
    body = json.dumps({}).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="10001")

    with patch.object(bot, "subdub_probe_video_bytes", new_callable=AsyncMock, return_value=mock_probe_result):
        res = client.post(path, content=body, headers=headers)

    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    data = res.json()
    assert data.get("ok") is True
    assert data.get("upload_id") == upload_id
    assert "duration_seconds" in data
    assert "preflight_passed" in data
    assert "detected_duration_source" in data
    assert data["preflight_passed"] is True
    assert isinstance(data["duration_seconds"], int)
