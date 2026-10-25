"""P0 Unit & Contract Test Suite for Bot Core Canonical Music Library (Jamendo) Parity (R40).

SPEC_ID: BOT-P0-MUSIC-LIBRARY-JAMENDO-CANONICAL-PARITY-R1
Verifies:
- SEARCH_VALID
- SEARCH_EMPTY
- SEARCH_MISSING_CREDENTIAL_PRENETWORK_FAIL
- SEARCH_401_403
- SEARCH_429
- SEARCH_5XX
- SEARCH_TIMEOUT
- SEARCH_MALFORMED_RESPONSE
- SEARCH_NO_SYNTHETIC_FALLBACK
- SEARCH_OWNER_ISOLATION
- SELECT_VALID
- SELECT_INVALID_INDEX
- SELECT_FOREIGN_OWNER_BLOCKED
- SELECT_STALE_SESSION_BLOCKED
- SELECTED_TRACK_READBACK
- PREVIEW_SAFE_SUCCESS
- PREVIEW_UNSAFE_URL_BLOCKED
- LICENSE_METADATA_PRESERVED
- PRICING_PARITY
- DOWNSTREAM_HANDOFF_IF_PUBLIC
"""

from __future__ import annotations

import json
from pathlib import Path
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import bot
from services.admin_wallet_service import compute_internal_admin_wallet_signature
from services.music_library_service import (
    BOT_SEARCH_IMMEDIATE_XU,
    BOT_SELECT_IMMEDIATE_XU,
    BOT_DOWNSTREAM_USAGE_XU,
    validate_preview_url_safety,
)

TEST_TOKEN = "test-music-lib-token"
TEST_SECRET = "test-music-lib-hmac-secret"


@pytest.fixture(autouse=True)
def setup_isolated_test_env(tmp_path: Path, monkeypatch):
    """Setup isolated test database and bridge credentials."""
    db_file = tmp_path / "test_r40_music.db"

    monkeypatch.setattr(bot, "DB_FILE", str(db_file))
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", TEST_SECRET)
    monkeypatch.setattr(bot, "JAMENDO_CLIENT_ID", "test_jamendo_client_id_123")

    bot.LAST_MUSIC_RESULTS.clear()
    bot.SELECTED_MUSIC.clear()
    bot.init_db()
    return {"db_file": str(db_file)}


def make_auth_headers(
    method: str,
    path: str,
    body: bytes = b"",
    actor_id: str = "",
) -> dict[str, str]:
    ts = str(int(time.time()))
    req_id = "req-music-lib-test"
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


SAMPLE_JAMENDO_TRACKS = [
    {
        "id": "1001",
        "name": "Summer Breeze",
        "artist_name": "Acoustic Band",
        "duration": 185,
        "license_ccurl": "https://creativecommons.org/licenses/by/4.0/",
        "shareurl": "https://www.jamendo.com/track/1001/summer-breeze",
        "audio": "https://prod-1.storage.jamendo.com/download/track/1001/mp32/",
    },
    {
        "id": "1002",
        "name": "Corporate Tech",
        "artist_name": "Digital Synth",
        "duration": 120,
        "license_ccurl": "https://creativecommons.org/licenses/by-nc/4.0/",
        "shareurl": "https://www.jamendo.com/track/1002/corporate-tech",
        "audio": "https://prod-1.storage.jamendo.com/download/track/1002/mp32/",
    },
]


def test_search_valid():
    """Verify SEARCH_VALID returns normalized items, 1-based session, and callback token."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    payload = {"query": "chill acoustic", "mock_results": SAMPLE_JAMENDO_TRACKS}
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/music/library/search", body=body, actor_id=owner_id)
    resp = client.post("/internal/v1/music/library/search", content=body, headers=headers)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["count"] == 2
    assert len(data["items"]) == 2
    assert data["callback_token"] != ""

    first = data["items"][0]
    assert first["title"] == "Summer Breeze"
    assert first["author"] == "Acoustic Band"
    assert first["duration"] == "3:05"
    assert first["provider"] == "Jamendo"
    assert "prod-1.storage.jamendo.com" in first["preview_url"]


def test_search_empty():
    """Verify SEARCH_EMPTY returns empty items list without synthetic fallback."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    payload = {"query": "nonexistent_track_xyz_9999", "mock_results": []}
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/music/library/search", body=body, actor_id=owner_id)
    resp = client.post("/internal/v1/music/library/search", content=body, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["items"] == []
    assert data["count"] == 0


def test_search_missing_credential_prenetwork_fail(monkeypatch):
    """Verify SEARCH_MISSING_CREDENTIAL_PRENETWORK_FAIL fails closed with 503 before any network call."""
    monkeypatch.setattr(bot, "JAMENDO_CLIENT_ID", None)

    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    payload = {"query": "piano"}
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/music/library/search", body=body, actor_id=owner_id)
    resp = client.post("/internal/v1/music/library/search", content=body, headers=headers)

    assert resp.status_code == 503
    data = resp.json()
    assert data["ok"] is False
    assert data["error_code"] == "JAMENDO_CREDENTIALS_MISSING"


def test_search_provider_errors_fail_closed(monkeypatch):
    """Verify provider HTTP 401, 403, 429, 5xx, timeout fail closed with 502 PROVIDER_ERROR."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    error_cases = [
        RuntimeError("Jamendo HTTP 401"),
        RuntimeError("Jamendo HTTP 403"),
        RuntimeError("Jamendo HTTP 429"),
        RuntimeError("Jamendo HTTP 500"),
        TimeoutError("Connection timed out"),
        ValueError("malformed JSON from provider"),
    ]

    for err in error_cases:
        async def mock_fetch(*a, **k):
            raise err

        monkeypatch.setattr(bot, "fetch_jamendo_tracks", mock_fetch)

        payload = {"query": "guitar"}
        body = json.dumps(payload).encode("utf-8")
        headers = make_auth_headers("POST", "/internal/v1/music/library/search", body=body, actor_id=owner_id)
        resp = client.post("/internal/v1/music/library/search", content=body, headers=headers)

        assert resp.status_code == 502, f"Failed for {err}"
        data = resp.json()
        assert data["ok"] is False
        assert data["error_code"] == "PROVIDER_ERROR"


def test_search_owner_isolation():
    """Verify search sessions are strictly bound to actor_id and isolated across owners."""
    client = TestClient(bot.fastapi_app)
    user_a = "10001"
    user_b = "20002"

    tracks_a = [SAMPLE_JAMENDO_TRACKS[0]]
    tracks_b = [SAMPLE_JAMENDO_TRACKS[1]]

    # User A searches
    body_a = json.dumps({"query": "user a music", "mock_results": tracks_a}).encode("utf-8")
    h_a = make_auth_headers("POST", "/internal/v1/music/library/search", body=body_a, actor_id=user_a)
    r_a = client.post("/internal/v1/music/library/search", content=body_a, headers=h_a)
    assert r_a.status_code == 200
    token_a = r_a.json()["callback_token"]

    # User B searches
    body_b = json.dumps({"query": "user b music", "mock_results": tracks_b}).encode("utf-8")
    h_b = make_auth_headers("POST", "/internal/v1/music/library/search", body=body_b, actor_id=user_b)
    r_b = client.post("/internal/v1/music/library/search", content=body_b, headers=h_b)
    assert r_b.status_code == 200

    # User B cannot use User A's token
    sel_body = json.dumps({"index": 1, "callback_token": token_a}).encode("utf-8")
    sel_headers = make_auth_headers("POST", "/internal/v1/music/library/select", body=sel_body, actor_id=user_b)
    sel_resp = client.post("/internal/v1/music/library/select", content=sel_body, headers=sel_headers)
    assert sel_resp.status_code in {410, 422}


def test_select_valid():
    """Verify 1-based index selection stores track into SELECTED_MUSIC."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    # Search first
    s_body = json.dumps({"query": "beats", "mock_results": SAMPLE_JAMENDO_TRACKS}).encode("utf-8")
    s_headers = make_auth_headers("POST", "/internal/v1/music/library/search", body=s_body, actor_id=owner_id)
    s_resp = client.post("/internal/v1/music/library/search", content=s_body, headers=s_headers)
    token = s_resp.json()["callback_token"]

    # Select track 1
    sel_body = json.dumps({"index": 1, "callback_token": token}).encode("utf-8")
    sel_headers = make_auth_headers("POST", "/internal/v1/music/library/select", body=sel_body, actor_id=owner_id)
    resp = client.post("/internal/v1/music/library/select", content=sel_body, headers=sel_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["selected"]["title"] == "Summer Breeze"
    assert int(owner_id) in bot.SELECTED_MUSIC
    assert bot.SELECTED_MUSIC[int(owner_id)]["title"] == "Summer Breeze"


def test_select_invalid_index():
    """Verify index 0, negative, or beyond count fails with 422 INVALID_INDEX."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    s_body = json.dumps({"query": "beats", "mock_results": SAMPLE_JAMENDO_TRACKS}).encode("utf-8")
    s_headers = make_auth_headers("POST", "/internal/v1/music/library/search", body=s_body, actor_id=owner_id)
    client.post("/internal/v1/music/library/search", content=s_body, headers=s_headers)

    for bad_idx in [0, -1, 3, 99]:
        sel_body = json.dumps({"index": bad_idx}).encode("utf-8")
        sel_headers = make_auth_headers("POST", "/internal/v1/music/library/select", body=sel_body, actor_id=owner_id)
        resp = client.post("/internal/v1/music/library/select", content=sel_body, headers=sel_headers)
        assert resp.status_code == 422
        assert resp.json()["error_code"] == "INVALID_INDEX"


def test_select_stale_session_blocked():
    """Verify expired search session (>600s) fails with 410 SEARCH_SESSION_EXPIRED."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    s_body = json.dumps({"query": "beats", "mock_results": SAMPLE_JAMENDO_TRACKS}).encode("utf-8")
    s_headers = make_auth_headers("POST", "/internal/v1/music/library/search", body=s_body, actor_id=owner_id)
    client.post("/internal/v1/music/library/search", content=s_body, headers=s_headers)

    # Age the session
    bot.LAST_MUSIC_RESULTS[int(owner_id)]["created_at"] = time.time() - 601

    sel_body = json.dumps({"index": 1}).encode("utf-8")
    sel_headers = make_auth_headers("POST", "/internal/v1/music/library/select", body=sel_body, actor_id=owner_id)
    resp = client.post("/internal/v1/music/library/select", content=sel_body, headers=sel_headers)

    assert resp.status_code == 410
    assert resp.json()["error_code"] == "SEARCH_SESSION_EXPIRED"


def test_selected_track_readback():
    """Verify GET /internal/v1/music/library/selected returns selected track."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    # Initially None
    h_init = make_auth_headers("GET", "/internal/v1/music/library/selected", actor_id=owner_id)
    r_init = client.get("/internal/v1/music/library/selected", headers=h_init)
    assert r_init.status_code == 200
    assert r_init.json()["selected"] is None

    # Search & Select
    s_body = json.dumps({"query": "beats", "mock_results": SAMPLE_JAMENDO_TRACKS}).encode("utf-8")
    s_headers = make_auth_headers("POST", "/internal/v1/music/library/search", body=s_body, actor_id=owner_id)
    client.post("/internal/v1/music/library/search", content=s_body, headers=s_headers)

    sel_body = json.dumps({"index": 2}).encode("utf-8")
    sel_headers = make_auth_headers("POST", "/internal/v1/music/library/select", body=sel_body, actor_id=owner_id)
    client.post("/internal/v1/music/library/select", content=sel_body, headers=sel_headers)

    # Readback
    h_read = make_auth_headers("GET", "/internal/v1/music/library/selected", actor_id=owner_id)
    r_read = client.get("/internal/v1/music/library/selected", headers=h_read)
    assert r_read.status_code == 200
    assert r_read.json()["selected"]["title"] == "Corporate Tech"


def test_preview_safe_success():
    """Verify GET /internal/v1/music/library/preview returns safe preview URL."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    s_body = json.dumps({"query": "beats", "mock_results": SAMPLE_JAMENDO_TRACKS}).encode("utf-8")
    s_headers = make_auth_headers("POST", "/internal/v1/music/library/search", body=s_body, actor_id=owner_id)
    client.post("/internal/v1/music/library/search", content=s_body, headers=s_headers)

    h_prev = make_auth_headers("GET", "/internal/v1/music/library/preview", actor_id=owner_id)
    resp = client.get("/internal/v1/music/library/preview?index=1", headers=h_prev)

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "prod-1.storage.jamendo.com" in data["preview_url"]
    assert data["title"] == "Summer Breeze"


def test_preview_unsafe_url_blocked():
    """Verify preview URL safety validation blocks unsafe schemes, private hosts, and untrusted domains."""
    unsafe_urls = [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "http://127.0.0.1:8000/internal",
        "http://192.168.1.1/admin",
        "http://evil-attacker.com/malicious.mp3",
    ]
    for bad_url in unsafe_urls:
        ok, reason = validate_preview_url_safety(bad_url)
        assert ok is False, f"Expected unsafe for {bad_url}, got safe ({reason})"


def test_license_metadata_preserved():
    """Verify license metadata is preserved in search results."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    s_body = json.dumps({"query": "beats", "mock_results": SAMPLE_JAMENDO_TRACKS}).encode("utf-8")
    s_headers = make_auth_headers("POST", "/internal/v1/music/library/search", body=s_body, actor_id=owner_id)
    resp = client.post("/internal/v1/music/library/search", content=s_body, headers=s_headers)

    items = resp.json()["items"]
    assert items[0]["license"] == "https://creativecommons.org/licenses/by/4.0/"
    assert items[1]["license"] == "https://creativecommons.org/licenses/by-nc/4.0/"


def test_pricing_parity():
    """Verify immediate intake search and select charge 0 Xu."""
    assert BOT_SEARCH_IMMEDIATE_XU == 0
    assert BOT_SELECT_IMMEDIATE_XU == 0
    assert BOT_DOWNSTREAM_USAGE_XU == 0


def test_downstream_handoff():
    """Verify selected music is accessible to downstream resolve_audio_source."""
    import asyncio
    owner_id = 99999
    selected_item = {
        "provider": "Jamendo",
        "title": "Ambient Chill",
        "preview_url": "https://storage.jamendo.com/ambient.mp3",
        "created_at": time.time(),
    }
    bot.SELECTED_MUSIC[owner_id] = selected_item

    mock_update = AsyncMock()
    mock_update.message.reply_to_message = None
    mock_update.effective_user.id = owner_id
    mock_context = AsyncMock()

    resolved = asyncio.run(bot.resolve_audio_source(mock_update, mock_context, prefer_selected=True))
    assert resolved["source"] == "selected_music"
    assert resolved["title"] == "Ambient Chill"
    assert resolved["preview_url"] == "https://storage.jamendo.com/ambient.mp3"
