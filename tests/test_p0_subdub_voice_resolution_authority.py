"""Unit and contract tests for Bot Core canonical SubDub Voice Resolution Authority.

SPEC_ID: BOT-SUBDUB-D3-VOICE-RESOLUTION-AUTHORITY
Verifies:
- GET /internal/v1/voice/profiles (Owner-Bound Voice Vault List)
  - Requires valid internal auth
  - Returns only owner's profiles; cross-owner access blocked
  - Redacts raw provider_voice_id and internal storage paths
  - Calculates tts_ready and preview_ready canonical flags
- POST /internal/v1/voice/resolve (SubDub Canonical Voice Resolution Authority)
  - Owner profile accepted when ready
  - Foreign profile rejected (403 FORBIDDEN_CROSS_OWNER)
  - Missing profile rejected (422/404 PROFILE_NOT_FOUND)
  - Forged client provider voice ID rejected / ignored as authority
  - Safe response redaction (no provider_voice_id leaked)
  - Mode contract preserved:
    * dub / dubbing / subtitle_plus_dub / subtitle_plus_dubbing require voice
    * subtitle_create / subtitle_translate do NOT require voice (ok=True, needs_voice=False)
  - Unsupported language for preset TTS fails closed
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

import bot
from services.admin_wallet_service import compute_internal_admin_wallet_signature


TEST_TOKEN = "test-subdub-bridge-token"
TEST_SECRET = "test-subdub-hmac-secret"


@pytest.fixture(autouse=True)
def setup_isolated_test_env(tmp_path: Path, monkeypatch):
    """Setup isolated test database and bridge credentials."""
    db_file = tmp_path / "test_d3_voice.db"

    monkeypatch.setattr(bot, "DB_FILE", str(db_file))
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", TEST_SECRET)

    bot.init_db()
    return {"db_file": str(db_file)}


def make_auth_headers(
    method: str,
    path: str,
    body: bytes = b"",
    actor_id: str = "",
) -> dict[str, str]:
    import time
    ts = str(int(time.time()))
    req_id = "req-subdub-d3-test"
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


def insert_test_voice_profile(
    user_id: str,
    display_name: str = "Giọng Mẫu",
    provider: str = "shopaikey_minimax",
    provider_voice_id: str = "voice-provider-abc-12345",
    status: str = "active",
    is_default: int = 0,
    deleted: bool = False,
) -> int:
    with bot.db_connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO voice_profiles (
                user_id, display_name, provider, provider_voice_id,
                status, is_default, consent_status, created_at, updated_at, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'granted', '2026-09-29 00:00:00', '2026-09-29 00:00:00', ?)
            """,
            (
                str(user_id),
                display_name,
                provider,
                provider_voice_id,
                status,
                is_default,
                "2026-09-29 00:00:00" if deleted else None,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def test_first_red_voice_resolution_endpoints_exist():
    """FIRST RED: Check that voice resolution endpoints exist on FastAPI app."""
    client = TestClient(bot.fastapi_app)

    # Profiles endpoint
    headers_get = make_auth_headers("GET", "/internal/v1/voice/profiles", actor_id="user_owner")
    resp_get = client.get("/internal/v1/voice/profiles", headers=headers_get)
    assert resp_get.status_code != 404, "Endpoint GET /internal/v1/voice/profiles must exist"

    # Resolve endpoint
    body = json.dumps({"mode": "dubbing", "target_language": "vi"}).encode("utf-8")
    headers_post = make_auth_headers("POST", "/internal/v1/voice/resolve", body=body, actor_id="user_owner")
    resp_post = client.post("/internal/v1/voice/resolve", content=body, headers=headers_post)
    assert resp_post.status_code != 404, "Endpoint POST /internal/v1/voice/resolve must exist"


def test_voice_profiles_owner_bound_and_redacted():
    """Verify GET /internal/v1/voice/profiles returns only owner profiles without provider_voice_id leakage."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"
    other_id = "20002"

    pid1 = insert_test_voice_profile(owner_id, display_name="Giọng Owner 1", provider_voice_id="secret-provider-111")
    insert_test_voice_profile(other_id, display_name="Giọng Other", provider_voice_id="secret-provider-222")

    headers = make_auth_headers("GET", "/internal/v1/voice/profiles", actor_id=owner_id)
    resp = client.get("/internal/v1/voice/profiles", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    items = data.get("items") or data.get("data", {}).get("items", [])
    assert len(items) == 1
    profile = items[0]
    assert profile["id"] == pid1
    assert profile["display_name"] == "Giọng Owner 1"
    assert profile["tts_ready"] is True
    # CRITICAL: provider_voice_id MUST NOT be leaked to client
    assert "provider_voice_id" not in profile
    assert "secret-provider-111" not in resp.text
    assert "secret-provider-222" not in resp.text


def test_voice_resolution_owner_profile_accepted():
    """Verify owner profile is successfully resolved for dubbing mode."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"
    pid = insert_test_voice_profile(owner_id, display_name="Giọng Hay", provider_voice_id="provider-voice-xyz-789")

    payload = {
        "mode": "dubbing",
        "target_language": "vi",
        "voice_profile_id": pid,
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/voice/resolve", body=body, actor_id=owner_id)
    resp = client.post("/internal/v1/voice/resolve", content=body, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["needs_voice"] is True
    assert data["voice_selection_mode"] == "manual"
    assert data["voice_profile_id"] == pid
    assert data["resolved_voice_name"] == "Giọng Hay"


def test_voice_resolution_foreign_profile_rejected():
    """Verify foreign user's voice profile is rejected with 403 FORBIDDEN_CROSS_OWNER."""
    client = TestClient(bot.fastapi_app)
    victim_id = "20002"
    attacker_id = "10001"
    pid = insert_test_voice_profile(victim_id, display_name="Giọng Nạn Nhân", provider_voice_id="victim-secret-voice")

    payload = {
        "mode": "dubbing",
        "target_language": "vi",
        "voice_profile_id": pid,
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/voice/resolve", body=body, actor_id=attacker_id)
    resp = client.post("/internal/v1/voice/resolve", content=body, headers=headers)

    assert resp.status_code in {403, 422}
    data = resp.json()
    assert data["ok"] is False
    assert data["error_code"] in {"FORBIDDEN_CROSS_OWNER", "PROFILE_NOT_FOUND"}


def test_voice_resolution_missing_profile_rejected():
    """Verify nonexistent profile_id fails closed."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    payload = {
        "mode": "dubbing",
        "target_language": "vi",
        "voice_profile_id": 999999,
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/voice/resolve", body=body, actor_id=owner_id)
    resp = client.post("/internal/v1/voice/resolve", content=body, headers=headers)

    assert resp.status_code in {404, 422}
    data = resp.json()
    assert data["ok"] is False
    assert data["error_code"] == "PROFILE_NOT_FOUND"


def test_voice_resolution_forged_provider_voice_rejected():
    """Verify client-supplied provider voice ID is completely ignored and rejected as authority."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    # Client tries to send an arbitrary provider voice ID directly
    payload = {
        "mode": "dubbing",
        "target_language": "vi",
        "provider_voice_id": "malicious-injected-provider-voice-id",
        "voice_id": "malicious-injected-voice-id",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/voice/resolve", body=body, actor_id=owner_id)
    resp = client.post("/internal/v1/voice/resolve", content=body, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    # Server must have resolved to canonical preset, NOT the injected ID
    assert data["voice_selection_mode"] == "preset"
    assert "malicious-injected" not in resp.text


def test_voice_resolution_safe_response_redaction():
    """Verify endpoint response never leaks raw provider_voice_id."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"
    pid = insert_test_voice_profile(owner_id, display_name="Giọng Test", provider_voice_id="secret-provider-long-id-8888")

    payload = {
        "mode": "dubbing",
        "target_language": "vi",
        "voice_profile_id": pid,
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/voice/resolve", body=body, actor_id=owner_id)
    resp = client.post("/internal/v1/voice/resolve", content=body, headers=headers)

    assert resp.status_code == 200
    assert "secret-provider-long-id-8888" not in resp.text
    data = resp.json()
    assert "provider_voice_id" not in data
    # Masked representation is allowed
    if "resolved_voice_id_masked" in data:
        assert data["resolved_voice_id_masked"] != "secret-provider-long-id-8888"


def test_voice_resolution_mode_contract_preserved():
    """Verify non-dubbing modes succeed without requiring voice, while dubbing modes require it."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    # 1. Non-dubbing: subtitle_create
    p1 = {"mode": "subtitle_create"}
    b1 = json.dumps(p1).encode("utf-8")
    h1 = make_auth_headers("POST", "/internal/v1/voice/resolve", body=b1, actor_id=owner_id)
    r1 = client.post("/internal/v1/voice/resolve", content=b1, headers=h1)
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["ok"] is True
    assert d1["needs_voice"] is False

    # 2. Non-dubbing: subtitle_translate
    p2 = {"mode": "subtitle_translate", "target_language": "en"}
    b2 = json.dumps(p2).encode("utf-8")
    h2 = make_auth_headers("POST", "/internal/v1/voice/resolve", body=b2, actor_id=owner_id)
    r2 = client.post("/internal/v1/voice/resolve", content=b2, headers=h2)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["ok"] is True
    assert d2["needs_voice"] is False

    # 3. Dubbing: subtitle_plus_dubbing requires voice
    p3 = {"mode": "subtitle_plus_dubbing", "target_language": "vi"}
    b3 = json.dumps(p3).encode("utf-8")
    h3 = make_auth_headers("POST", "/internal/v1/voice/resolve", body=b3, actor_id=owner_id)
    r3 = client.post("/internal/v1/voice/resolve", content=b3, headers=h3)
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["ok"] is True
    assert d3["needs_voice"] is True
    assert d3["voice_selection_mode"] == "preset"


def test_voice_resolution_unsupported_language_fail_closed():
    """Verify unsupported target language fails closed in dubbing mode."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    payload = {
        "mode": "dubbing",
        "target_language": "klingon-nonexistent",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/voice/resolve", body=body, actor_id=owner_id)
    resp = client.post("/internal/v1/voice/resolve", content=body, headers=headers)

    assert resp.status_code == 422
    data = resp.json()
    assert data["ok"] is False
    assert data["error_code"] == "UNSUPPORTED_LANGUAGE"
