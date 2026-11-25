"""P0 Unit & Contract Test Suite for Bot Core Canonical Music Library (Jamendo) Parity (R40 FIX1).

SPEC_ID: BOT-P0-MUSIC-LIBRARY-JAMENDO-CANONICAL-PARITY-FIX1
Verifies:
- SEARCH_VALID: Canonical key `results`, normalized tracks, 0 Xu charged immediately.
- SEARCH_EMPTY: Returns empty list `results: []` without synthetic fallback.
- SEARCH_MISSING_CREDENTIAL_PRENETWORK_FAIL: Fails closed 503 before network call.
- SEARCH_PROVIDER_ERRORS_FAIL_CLOSED: 401, 403, 429, 5XX, timeout, malformed -> JAMENDO_FETCH_FAILED (502).
- SEARCH_OWNER_ISOLATION: Scoped strictly to authenticated actor_id.
- SELECT_VALID: 1-based index selection stores track into SELECTED_MUSIC.
- SELECT_INVALID_INDEX: Index < 1 or out of range fails closed with 422.
- SELECT_FOREIGN_OWNER_BLOCKED: Cross-actor selection fails closed.
- SELECT_STALE_SESSION_BLOCKED: Expired session (>600s) fails with 410.
- SELECTED_TRACK_READBACK: GET /internal/v1/music/library/selected returns active selection.
- PREVIEW_SAFE_SUCCESS: Safe Jamendo CDN URL returned.
- PREVIEW_UNSAFE_URL_BLOCKED: Unsafe schemes, private IPs, untrusted domains blocked.
- LICENSE_METADATA_PRESERVED: CC license and source_url preserved end-to-end.
- PRICING_PARITY: 0 Xu search, 0 Xu select, 0 Xu downstream stock library usage.
- REAL_DOWNSTREAM_HANDOFF: Web select -> Bot SELECTED_MUSIC -> resolve_audio_source -> source=selected_music.
- FOREIGN_ACTOR_HANDOFF_BLOCKED: Foreign actor resolve_audio_source does not receive track.
- EXPIRED_SELECTION_HANDOFF_BLOCKED: Expired selection (>600s) resolve_audio_source returns fallback.
- NO_SYNTHETIC_SUCCESS: Error paths never return fake success.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import time
from unittest.mock import AsyncMock

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


def test_search_valid(monkeypatch):
    """Verify SEARCH_VALID returns canonical `results` key, normalized items, and callback token."""
    monkeypatch.setattr(bot, "fetch_jamendo_tracks", AsyncMock(return_value=SAMPLE_JAMENDO_TRACKS))
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    payload = {"query": "chill acoustic"}
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/music/library/search", body=body, actor_id=owner_id)
    resp = client.post("/internal/v1/music/library/search", content=body, headers=headers)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["count"] == 2
    # Verify CANONICAL_SEARCH_RESULT_KEY=results
    assert "results" in data
    assert len(data["results"]) == 2
    assert data["callback_token"] != ""

    first = data["results"][0]
    assert first["id"] == "1001"
    assert first["title"] == "Summer Breeze"
    assert first["author"] == "Acoustic Band"
    assert first["duration"] == "3:05"
    assert first["provider"] == "Jamendo"
    assert first["license"] == "https://creativecommons.org/licenses/by/4.0/"
    assert first["source_url"] == "https://www.jamendo.com/track/1001/summer-breeze"
    assert "prod-1.storage.jamendo.com" in first["preview_url"]


def test_search_empty(monkeypatch):
    """Verify SEARCH_EMPTY returns empty results list without synthetic fallback."""
    monkeypatch.setattr(bot, "fetch_jamendo_tracks", AsyncMock(return_value=[]))
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    payload = {"query": "nonexistent_track_xyz_9999"}
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/music/library/search", body=body, actor_id=owner_id)
    resp = client.post("/internal/v1/music/library/search", content=body, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["results"] == []
    assert data["count"] == 0
    assert data["charged_xu"] == 0


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
    assert data["charged_xu"] == 0


def test_search_provider_errors_fail_closed(monkeypatch):
    """Verify provider HTTP 401, 403, 429, 5xx, timeout fail closed with 502 JAMENDO_FETCH_FAILED."""
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
        assert data["error_code"] == "JAMENDO_FETCH_FAILED"
        assert data["charged_xu"] == 0


def test_search_owner_isolation(monkeypatch):
    """Verify search sessions are strictly bound to actor_id and isolated across owners."""
    client = TestClient(bot.fastapi_app)
    user_a = "10001"
    user_b = "20002"

    monkeypatch.setattr(bot, "fetch_jamendo_tracks", AsyncMock(side_effect=[[SAMPLE_JAMENDO_TRACKS[0]], [SAMPLE_JAMENDO_TRACKS[1]]]))

    # User A searches
    body_a = json.dumps({"query": "user a music"}).encode("utf-8")
    h_a = make_auth_headers("POST", "/internal/v1/music/library/search", body=body_a, actor_id=user_a)
    r_a = client.post("/internal/v1/music/library/search", content=body_a, headers=h_a)
    assert r_a.status_code == 200
    token_a = r_a.json()["callback_token"]

    # User B searches
    body_b = json.dumps({"query": "user b music"}).encode("utf-8")
    h_b = make_auth_headers("POST", "/internal/v1/music/library/search", body=body_b, actor_id=user_b)
    r_b = client.post("/internal/v1/music/library/search", content=body_b, headers=h_b)
    assert r_b.status_code == 200

    # User B cannot use User A's token
    sel_body = json.dumps({"index": 1, "callback_token": token_a}).encode("utf-8")
    sel_headers = make_auth_headers("POST", "/internal/v1/music/library/select", body=sel_body, actor_id=user_b)
    sel_resp = client.post("/internal/v1/music/library/select", content=sel_body, headers=sel_headers)
    assert sel_resp.status_code in {410, 422}


def test_select_valid(monkeypatch):
    """Verify 1-based index selection stores track into SELECTED_MUSIC."""
    monkeypatch.setattr(bot, "fetch_jamendo_tracks", AsyncMock(return_value=SAMPLE_JAMENDO_TRACKS))
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    # Search first
    s_body = json.dumps({"query": "beats"}).encode("utf-8")
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


def test_select_invalid_index(monkeypatch):
    """Verify index 0, negative, or beyond count fails with 422 INVALID_INDEX."""
    monkeypatch.setattr(bot, "fetch_jamendo_tracks", AsyncMock(return_value=SAMPLE_JAMENDO_TRACKS))
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    s_body = json.dumps({"query": "beats"}).encode("utf-8")
    s_headers = make_auth_headers("POST", "/internal/v1/music/library/search", body=s_body, actor_id=owner_id)
    client.post("/internal/v1/music/library/search", content=s_body, headers=s_headers)

    for bad_idx in [0, -1, 3, 99]:
        sel_body = json.dumps({"index": bad_idx}).encode("utf-8")
        sel_headers = make_auth_headers("POST", "/internal/v1/music/library/select", body=sel_body, actor_id=owner_id)
        resp = client.post("/internal/v1/music/library/select", content=sel_body, headers=sel_headers)
        assert resp.status_code == 422
        assert resp.json()["error_code"] == "INVALID_INDEX"


def test_select_stale_session_blocked(monkeypatch):
    """Verify expired search session (>600s) fails with 410 SEARCH_SESSION_EXPIRED."""
    monkeypatch.setattr(bot, "fetch_jamendo_tracks", AsyncMock(return_value=SAMPLE_JAMENDO_TRACKS))
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    s_body = json.dumps({"query": "beats"}).encode("utf-8")
    s_headers = make_auth_headers("POST", "/internal/v1/music/library/search", body=s_body, actor_id=owner_id)
    client.post("/internal/v1/music/library/search", content=s_body, headers=s_headers)

    # Age the session
    bot.LAST_MUSIC_RESULTS[int(owner_id)]["created_at"] = time.time() - 601

    sel_body = json.dumps({"index": 1}).encode("utf-8")
    sel_headers = make_auth_headers("POST", "/internal/v1/music/library/select", body=sel_body, actor_id=owner_id)
    resp = client.post("/internal/v1/music/library/select", content=sel_body, headers=sel_headers)

    assert resp.status_code == 410
    assert resp.json()["error_code"] == "SEARCH_SESSION_EXPIRED"


def test_selected_track_readback(monkeypatch):
    """Verify GET /internal/v1/music/library/selected returns selected track."""
    monkeypatch.setattr(bot, "fetch_jamendo_tracks", AsyncMock(return_value=SAMPLE_JAMENDO_TRACKS))
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    # Initially None
    h_init = make_auth_headers("GET", "/internal/v1/music/library/selected", actor_id=owner_id)
    r_init = client.get("/internal/v1/music/library/selected", headers=h_init)
    assert r_init.status_code == 200
    assert r_init.json()["selected"] is None

    # Search & Select
    s_body = json.dumps({"query": "beats"}).encode("utf-8")
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


def test_preview_safe_success(monkeypatch):
    """Verify GET /internal/v1/music/library/preview returns safe preview URL."""
    monkeypatch.setattr(bot, "fetch_jamendo_tracks", AsyncMock(return_value=SAMPLE_JAMENDO_TRACKS))
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    s_body = json.dumps({"query": "beats"}).encode("utf-8")
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


def test_license_metadata_preserved(monkeypatch):
    """Verify license metadata and source_url are preserved in search results."""
    monkeypatch.setattr(bot, "fetch_jamendo_tracks", AsyncMock(return_value=SAMPLE_JAMENDO_TRACKS))
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    s_body = json.dumps({"query": "beats"}).encode("utf-8")
    s_headers = make_auth_headers("POST", "/internal/v1/music/library/search", body=s_body, actor_id=owner_id)
    resp = client.post("/internal/v1/music/library/search", content=s_body, headers=s_headers)

    results = resp.json()["results"]
    assert results[0]["license"] == "https://creativecommons.org/licenses/by/4.0/"
    assert results[0]["source_url"] == "https://www.jamendo.com/track/1001/summer-breeze"
    assert results[1]["license"] == "https://creativecommons.org/licenses/by-nc/4.0/"
    assert results[1]["source_url"] == "https://www.jamendo.com/track/1002/corporate-tech"


def test_pricing_parity():
    """Verify immediate intake search and select charge 0 Xu."""
    assert BOT_SEARCH_IMMEDIATE_XU == 0
    assert BOT_SELECT_IMMEDIATE_XU == 0
    assert BOT_DOWNSTREAM_USAGE_XU == 0


def test_downstream_handoff_and_isolation(monkeypatch):
    """Verify real downstream handoff: select -> SELECTED_MUSIC -> resolve_audio_source.

    Proves:
    - WEB_SELECT_TO_BOT_DOWNSTREAM_HANDOFF=PASS
    - FOREIGN_ACTOR_HANDOFF_BLOCKED=PASS
    - EXPIRED_SELECTION_HANDOFF_BLOCKED=PASS
    """
    monkeypatch.setattr(bot, "fetch_jamendo_tracks", AsyncMock(return_value=SAMPLE_JAMENDO_TRACKS))
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"
    foreign_id = "20002"

    # 1. Search
    s_body = json.dumps({"query": "chill"}).encode("utf-8")
    s_headers = make_auth_headers("POST", "/internal/v1/music/library/search", body=s_body, actor_id=owner_id)
    s_resp = client.post("/internal/v1/music/library/search", content=s_body, headers=s_headers)
    assert s_resp.status_code == 200
    token = s_resp.json()["callback_token"]

    # 2. Select track 1 via canonical internal endpoint
    sel_body = json.dumps({"index": 1, "callback_token": token}).encode("utf-8")
    sel_headers = make_auth_headers("POST", "/internal/v1/music/library/select", body=sel_body, actor_id=owner_id)
    sel_resp = client.post("/internal/v1/music/library/select", content=sel_body, headers=sel_headers)
    assert sel_resp.status_code == 200

    # 3. Downstream handoff: resolve_audio_source retrieves SELECTED_MUSIC
    mock_update = AsyncMock()
    mock_update.message.reply_to_message = None
    mock_update.effective_user.id = int(owner_id)
    mock_context = AsyncMock()

    resolved = asyncio.run(bot.resolve_audio_source(mock_update, mock_context, prefer_selected=True))
    assert resolved["source"] == "selected_music"
    assert resolved["title"] == "Summer Breeze"
    assert "prod-1.storage.jamendo.com" in resolved["preview_url"]

    # 4. Foreign actor handoff is blocked
    mock_foreign_update = AsyncMock()
    mock_foreign_update.message.reply_to_message = None
    mock_foreign_update.effective_user.id = int(foreign_id)

    foreign_resolved = asyncio.run(bot.resolve_audio_source(mock_foreign_update, mock_context, prefer_selected=True))
    assert foreign_resolved.get("source") != "selected_music"

    # 5. Expired selection handoff is blocked
    bot.SELECTED_MUSIC[int(owner_id)]["created_at"] = time.time() - 601
    expired_resolved = asyncio.run(bot.resolve_audio_source(mock_update, mock_context, prefer_selected=True))
    assert expired_resolved.get("source") != "selected_music"
