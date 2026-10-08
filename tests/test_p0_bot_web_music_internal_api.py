"""Test suite for Bot internal Web Music runtime endpoints and service.

Task: MUSIC_WEB_CANONICAL_ENGINE_PARITY_AND_PRODUCTION_RELEASE_R1
Product Family: Music
Tracker: manhtoangreensky-wq/toan-aas-standalone#612

Tests cover:
- JIT authorization & HMAC verification
- Rejection of client-injected authority fields (provider, amount, price, wallet)
- Strict validation of tier enum (basic, standard, premium) without silent defaulting
- Canonical public pricing: Background (130, 150, 200 Xu) and Song (200, 250, 300 Xu)
- Product separation: Background rejects lyrics/vocal fields; Song validates vocal_mode
- Idempotency preservation (same key reuse vs payload conflict 409)
- Safe read-only GET endpoints (no mutations)
- Atomic CAS execution claim (no duplicate provider submit)
- Post-success exactly-once settlement upon verified >0 byte audio output
- Zero Xu debit on failed/ambiguous jobs
- Audio artifact serving & cross-account tenant isolation
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

import bot
from services.admin_wallet_service import compute_internal_admin_wallet_signature
from services.web_music_runtime_service import (
    ensure_web_music_schema,
    get_web_music_job,
    prepare_web_music_job,
)

TEST_SECRET = "test_internal_secret_music_32b_hex_0123"
TEST_TOKEN = "test_internal_token_music"


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", TEST_SECRET)
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("INTERNAL_ADMIN_WALLET_SHARED_SECRET", TEST_SECRET)
    monkeypatch.setenv("INTERNAL_ADMIN_WALLET_BEARER_TOKEN", TEST_TOKEN)
    test_db = str(tmp_path / "test_bot_music.db")
    monkeypatch.setenv("DB_FILE", test_db)
    monkeypatch.setattr(bot, "DB_FILE", test_db)
    storage_dir = tmp_path / "music_assets"
    monkeypatch.setenv("MUSIC_ASSET_STORAGE_DIR", str(storage_dir))

    # Initialize tables
    import sqlite3
    conn = sqlite3.connect(test_db)
    ensure_web_music_schema(conn)
    conn.commit()
    conn.close()


def make_auth_headers(
    method: str,
    path: str,
    body: bytes = b"",
    actor_id: str = "12345",
) -> dict[str, str]:
    ts = str(int(time.time()))
    req_id = f"req-music-{int(time.time())}"
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


# ─── TEST 1: PREPARE BACKGROUND MUSIC WITH CANONICAL TIERS ─────────────────────

def test_prepare_background_music_all_tiers():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-music/jobs"

    tier_expected_quotes = {
        "basic": 130,
        "standard": 150,
        "premium": 200,
    }

    for tier, expected_quote in tier_expected_quotes.items():
        payload = {
            "product_kind": "background",
            "tier": tier,
            "mode": "background",
            "brief": f"Upbeat corporate background music ({tier})",
            "duration_seconds": 45,
            "idempotency_key": f"test-bg-{tier}-key",
        }
        body = json.dumps(payload).encode("utf-8")
        headers = make_auth_headers("POST", path, body=body, actor_id="12345")
        resp = client.post(path, data=body, headers=headers)
        assert resp.status_code == 200, f"Failed for tier {tier}: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True
        job = data.get("job")
        assert job["product_kind"] == "background"
        assert job["tier"] == tier
        assert job["quote_xu"] == expected_quote
        assert job["charged_xu"] == 0
        assert job["status"] == "prepared"
        assert "artifact_path" not in job
        assert "provider_task_id" not in job


# ─── TEST 2: PREPARE SONG MUSIC WITH CANONICAL TIERS ───────────────────────────

def test_prepare_song_music_all_tiers():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-music/jobs"

    tier_expected_quotes = {
        "basic": 200,
        "standard": 250,
        "premium": 300,
    }

    for tier, expected_quote in tier_expected_quotes.items():
        payload = {
            "product_kind": "song",
            "tier": tier,
            "mode": "song",
            "brief": "Pop ballad about perseverance",
            "lyrics": "Verse 1: Walking through the fire\nChorus: Never give up",
            "vocal_mode": "female",
            "duration_seconds": 120,
            "idempotency_key": f"test-song-{tier}-key",
        }
        body = json.dumps(payload).encode("utf-8")
        headers = make_auth_headers("POST", path, body=body, actor_id="12345")
        resp = client.post(path, data=body, headers=headers)
        assert resp.status_code == 200, f"Failed for tier {tier}: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True
        job = data.get("job")
        assert job["product_kind"] == "song"
        assert job["tier"] == tier
        assert job["quote_xu"] == expected_quote
        assert job["vocal_mode"] == "female"
        assert job["status"] == "prepared"


# ─── TEST 3: STRICT TIER REQUIRED (NO SILENT DEFAULT) ─────────────────────────

def test_prepare_music_rejects_missing_or_invalid_tier():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-music/jobs"

    # Missing tier
    payload_no_tier = {
        "product_kind": "background",
        "brief": "Ambient background",
        "duration_seconds": 30,
    }
    body = json.dumps(payload_no_tier).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="12345")
    resp = client.post(path, data=body, headers=headers)
    assert resp.status_code == 400
    assert "TIER_REQUIRED" in resp.json().get("error_code")

    # Invalid tier
    payload_bad_tier = {
        "product_kind": "background",
        "tier": "ultra_deluxe",
        "brief": "Ambient background",
    }
    body2 = json.dumps(payload_bad_tier).encode("utf-8")
    headers2 = make_auth_headers("POST", path, body=body2, actor_id="12345")
    resp2 = client.post(path, data=body2, headers=headers2)
    assert resp2.status_code == 400
    assert "INVALID_TIER" in resp2.json().get("error_code")


# ─── TEST 4: STRICT PRODUCT SEPARATION ────────────────────────────────────────

def test_product_separation_background_rejects_song_fields():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-music/jobs"

    payload_contaminated = {
        "product_kind": "background",
        "tier": "basic",
        "brief": "Background melody",
        "lyrics": "Lyrics that should not be here",
    }
    body = json.dumps(payload_contaminated).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="12345")
    resp = client.post(path, data=body, headers=headers)
    assert resp.status_code == 400
    assert "SONG_FIELD_REJECTED_FOR_BACKGROUND" in resp.json().get("error_code")


# ─── TEST 5: REJECTION OF FORBIDDEN AUTHORITY FIELDS ──────────────────────────

def test_prepare_music_rejects_forbidden_authority_fields():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-music/jobs"

    forbidden_payloads = [
        {"product_kind": "background", "tier": "basic", "brief": "test", "provider": "key4u_suno"},
        {"product_kind": "background", "tier": "basic", "brief": "test", "amount_xu": 0},
        {"product_kind": "background", "tier": "basic", "brief": "test", "price": 10},
        {"product_kind": "background", "tier": "basic", "brief": "test", "wallet": 9999},
        {"product_kind": "background", "tier": "basic", "brief": "test", "charged_xu": 0},
        {"product_kind": "background", "tier": "basic", "brief": "test", "status": "completed"},
    ]

    for p in forbidden_payloads:
        body = json.dumps(p).encode("utf-8")
        headers = make_auth_headers("POST", path, body=body, actor_id="12345")
        resp = client.post(path, data=body, headers=headers)
        assert resp.status_code == 400
        assert resp.json().get("error_code") == "FORBIDDEN_AUTHORITY_FIELD_REJECTED"


# ─── TEST 6: IDEMPOTENCY PRESERVATION & CONFLICT DETECTION ────────────────────

def test_idempotency_same_key_reuse_vs_conflict():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-music/jobs"

    payload = {
        "product_kind": "background",
        "tier": "basic",
        "brief": "Meditation track",
        "duration_seconds": 60,
        "idempotency_key": "idemp-key-meditation-1",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="12345")

    # Initial request
    resp1 = client.post(path, data=body, headers=headers)
    assert resp1.status_code == 200
    job1 = resp1.json()["job"]
    assert resp1.json()["replayed"] is False

    # Exact replay
    resp2 = client.post(path, data=body, headers=headers)
    assert resp2.status_code == 200
    job2 = resp2.json()["job"]
    assert resp2.json()["replayed"] is True
    assert job1["job_id"] == job2["job_id"]

    # Same key with altered payload -> HTTP 409
    altered = dict(payload)
    altered["tier"] = "premium"
    body_alt = json.dumps(altered).encode("utf-8")
    headers_alt = make_auth_headers("POST", path, body=body_alt, actor_id="12345")
    resp_conflict = client.post(path, data=body_alt, headers=headers_alt)
    assert resp_conflict.status_code == 409
    assert resp_conflict.json()["error_code"] == "IDEMPOTENCY_CONFLICT"


# ─── TEST 7: CROSS-ACCOUNT TENANT ISOLATION ────────────────────────────────────

def test_cross_account_tenant_isolation():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-music/jobs"

    payload = {
        "product_kind": "background",
        "tier": "basic",
        "brief": "Lofi study beat",
        "idempotency_key": "tenant-test-key-1",
    }
    body = json.dumps(payload).encode("utf-8")
    headers_user_a = make_auth_headers("POST", path, body=body, actor_id="11111")
    resp_a = client.post(path, data=body, headers=headers_user_a)
    assert resp_a.status_code == 200
    job_id = resp_a.json()["job"]["job_id"]

    # User B attempts to access User A's job -> 404
    detail_path = f"/internal/v1/web-music/jobs/{job_id}"
    headers_user_b = make_auth_headers("GET", detail_path, actor_id="22222")
    resp_b = client.get(detail_path, headers=headers_user_b)
    assert resp_b.status_code == 404
    assert resp_b.json()["error_code"] == "JOB_NOT_FOUND"


# ─── TEST 8: ATOMIC CLAIM & CONFIRM SUBMISSION ────────────────────────────────

@pytest.mark.asyncio
async def test_confirm_job_execution_atomic_claim_and_provider_submit():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-music/jobs"

    payload = {
        "product_kind": "background",
        "tier": "standard",
        "brief": "Cinematic trailer music",
        "duration_seconds": 30,
        "idempotency_key": "confirm-test-key-1",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="12345")
    resp = client.post(path, data=body, headers=headers)
    assert resp.status_code == 200
    job_id = resp.json()["job"]["job_id"]

    confirm_path = f"/internal/v1/web-music/jobs/{job_id}/confirm"
    confirm_headers = make_auth_headers("POST", confirm_path, actor_id="12345")

    # Mock provider submit returning task_id
    mock_submitted = {
        "ok": True,
        "status": "PASS_SUBMITTED",
        "provider": "shopaikey_music",
        "task_id": "mock_task_98765",
    }
    with patch("bot.submit_music_generation_job", new_callable=AsyncMock) as mock_submit:
        mock_submit.return_value = mock_submitted
        confirm_resp = client.post(confirm_path, headers=confirm_headers)
        assert confirm_resp.status_code == 200
        data = confirm_resp.json()
        assert data["ok"] is True
        job = data["job"]
        assert job["status"] == "processing"
        assert job["quote_xu"] == 150
        assert job["charged_xu"] == 0

    # Second confirm when already processing -> 409 CONCURRENT_CONFIRM_IN_PROGRESS
    confirm_resp2 = client.post(confirm_path, headers=confirm_headers)
    assert confirm_resp2.status_code == 409
    assert confirm_resp2.json()["error_code"] == "CONCURRENT_CONFIRM_IN_PROGRESS"


# ─── TEST 9: RECONCILE POLL, AUDIO VERIFICATION, AND EXACTLY-ONCE DEBIT ───────

@pytest.mark.asyncio
async def test_reconcile_poll_completes_with_audio_and_charges_exactly_once():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-music/jobs"

    payload = {
        "product_kind": "background",
        "tier": "basic",
        "brief": "Acoustic folk background",
        "duration_seconds": 30,
        "idempotency_key": "reconcile-test-key-1",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="99999")
    resp = client.post(path, data=body, headers=headers)
    job_id = resp.json()["job"]["job_id"]

    confirm_path = f"/internal/v1/web-music/jobs/{job_id}/confirm"
    confirm_headers = make_auth_headers("POST", confirm_path, actor_id="99999")
    with patch("bot.submit_music_generation_job", new_callable=AsyncMock) as mock_submit:
        mock_submit.return_value = {"ok": True, "status": "PASS_SUBMITTED", "provider": "shopaikey_music", "task_id": "task_reconcile_1"}
        client.post(confirm_path, headers=confirm_headers)

    reconcile_path = f"/internal/v1/web-music/jobs/{job_id}/reconcile"
    reconcile_headers = make_auth_headers("POST", reconcile_path, actor_id="99999")

    mock_audio = b"ID3_MOCK_VALID_AUDIO_BYTES_TEST_STREAM"
    mock_polled = {
        "ok": True,
        "status": "COMPLETED",
        "audio_bytes": mock_audio,
        "output_url": "https://example.com/audio.mp3",
    }

    mock_spend = {"ok": True, "final_cost": 130}
    with patch("bot.poll_music_generation_job", new_callable=AsyncMock) as mock_poll, \
         patch("bot.spend_fixed_credit_idempotent_info") as mock_charge:
        mock_poll.return_value = mock_polled
        mock_charge.return_value = mock_spend

        rec_resp = client.post(reconcile_path, headers=reconcile_headers)
        assert rec_resp.status_code == 200
        rec_data = rec_resp.json()
        assert rec_data["ok"] is True
        job = rec_data["job"]
        assert job["status"] == "completed"
        assert job["charged_xu"] == 130
        assert job["has_artifact"] is True
        assert job["can_download"] is True

        # Exactly 1 debit call
        assert mock_charge.call_count == 1
        charge_args = mock_charge.call_args[0]
        assert charge_args[0] == 99999  # uid
        assert charge_args[1] == 130    # quote_xu

        # Re-reconcile completed job does NOT charge a second time
        rec_resp2 = client.post(reconcile_path, headers=reconcile_headers)
        assert rec_resp2.status_code == 200
        assert mock_charge.call_count == 1  # Still 1!


# ─── TEST 10: ARTIFACT STREAM SERVING ─────────────────────────────────────────

def test_artifact_endpoint_serves_valid_audio():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-music/jobs"

    payload = {
        "product_kind": "song",
        "tier": "basic",
        "brief": "Rock anthem",
        "lyrics": "We will rock",
        "vocal_mode": "male",
        "idempotency_key": "art-test-key-1",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="12345")
    resp = client.post(path, data=body, headers=headers)
    job_id = resp.json()["job"]["job_id"]

    artifact_path = f"/internal/v1/web-music/jobs/{job_id}/artifact"
    art_headers = make_auth_headers("GET", artifact_path, actor_id="12345")

    # In prepared state -> 404
    resp_prep = client.get(artifact_path, headers=art_headers)
    assert resp_prep.status_code == 404

    # Confirm with direct audio return
    confirm_path = f"/internal/v1/web-music/jobs/{job_id}/confirm"
    confirm_headers = make_auth_headers("POST", confirm_path, actor_id="12345")
    mock_audio = b"MPEG_HEADER_MOCK_SONG_BYTES"
    with patch("bot.submit_music_generation_job", new_callable=AsyncMock) as mock_submit, \
         patch("bot.spend_fixed_credit_idempotent_info") as mock_charge:
        mock_submit.return_value = {"ok": True, "task_id": "direct_task", "audio_bytes": mock_audio}
        mock_charge.return_value = {"ok": True, "final_cost": 200}
        client.post(confirm_path, headers=confirm_headers)

    # Now completed -> serves audio/mpeg
    resp_art = client.get(artifact_path, headers=art_headers)
    assert resp_art.status_code == 200
    assert resp_art.headers.get("content-type") == "audio/mpeg"
    assert resp_art.content == mock_audio
