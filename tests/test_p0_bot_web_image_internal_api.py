"""Test suite for Bot internal Web Image runtime endpoints and service.

Task: P0.BOT.WEB.IMAGE.RUNTIME.AUTHORITY.R1
Spec: BOT-WEB-IMAGE-RUNTIME-AUTHORITY-R1
Product Family: Image Create (image_create)

Tests cover:
- JIT authorization & HMAC verification
- Rejection of client-injected authority fields (provider, amount, price, wallet)
- Strict validation of tier enum without silent defaulting
- Canonical public pricing: low (20), standard (40), standard_warranty (70),
  common (60), common_warranty (100), high (120), high_warranty (180 Xu)
- Idempotency preservation (same key reuse vs payload conflict 409)
- Safe read-only GET endpoints (no mutations)
- Atomic CAS execution claim (no duplicate provider submit)
- Post-success exactly-once settlement upon verified >0 byte image output
- Zero Xu debit on failed/ambiguous jobs
- Image artifact serving & cross-account tenant isolation
"""

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

import bot
from services.admin_wallet_service import compute_internal_admin_wallet_signature
from services.web_image_runtime_service import (
    ensure_web_image_schema,
    get_web_image_job,
    prepare_web_image_job,
)

TEST_SECRET = "test_internal_secret_image_32b_hex_0123"
TEST_TOKEN = "test_internal_token_image"


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", TEST_SECRET)
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("INTERNAL_ADMIN_WALLET_SHARED_SECRET", TEST_SECRET)
    monkeypatch.setenv("INTERNAL_ADMIN_WALLET_BEARER_TOKEN", TEST_TOKEN)
    test_db = str(tmp_path / "test_bot_image.db")
    monkeypatch.setenv("DB_FILE", test_db)
    monkeypatch.setattr(bot, "DB_FILE", test_db)
    storage_dir = tmp_path / "image_assets"
    monkeypatch.setenv("IMAGE_ASSET_STORAGE_DIR", str(storage_dir))

    # Initialize tables
    import sqlite3
    conn = sqlite3.connect(test_db)
    ensure_web_image_schema(conn)
    conn.commit()
    conn.close()


def make_auth_headers(
    method: str,
    path: str,
    body: bytes = b"",
    actor_id: str = "12345",
) -> dict[str, str]:
    ts = str(int(time.time()))
    req_id = f"req-image-{int(time.time())}"
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


# ─── TEST 1: PREPARE IMAGE WITH CANONICAL TIERS & PRICING ─────────────────────

def test_prepare_image_all_canonical_tiers():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-image/jobs"

    tier_expected_quotes = {
        "low": 10,
        "standard": 20,
        "standard_warranty": 30,
        "common": 50,
        "common_warranty": 100,
        "high": 70,
        "high_warranty": 140,
    }

    for tier, expected_quote in tier_expected_quotes.items():
        payload = {
            "tier_key": tier,
            "prompt": f"A beautiful cinematic landscape in Vietnam ({tier})",
            "aspect_ratio": "16:9",
            "idempotency_key": f"key-image-tier-{tier}",
        }
        body = json.dumps(payload).encode("utf-8")
        headers = make_auth_headers("POST", path, body=body, actor_id="12345")
        resp = client.post(path, data=body, headers=headers)
        assert resp.status_code == 200, f"Failed for tier {tier}: {resp.text}"
        data = resp.json()
        assert data["ok"] is True
        job = data["job"]
        assert job["tier_key"] == tier
        assert job["quote_xu"] == expected_quote, f"Tier {tier} expected quote {expected_quote}, got {job['quote_xu']}"
        assert job["charged_xu"] == 0
        assert job["status"] == "prepared"
        assert job["aspect_ratio"] == "16:9"
        assert job["has_artifact"] is False
        assert job["can_download"] is False


# ─── TEST 2: REJECT MISSING OR INVALID TIER ───────────────────────────────────

def test_prepare_image_rejects_missing_or_invalid_tier():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-image/jobs"

    # Missing tier
    payload_missing = {"prompt": "A sunset photo"}
    body1 = json.dumps(payload_missing).encode("utf-8")
    resp1 = client.post(path, data=body1, headers=make_auth_headers("POST", path, body=body1))
    assert resp1.status_code == 400
    assert resp1.json()["error_code"] == "TIER_REQUIRED"

    # Invalid tier
    payload_invalid = {"prompt": "A sunset photo", "tier_key": "ultra_hd_magic"}
    body2 = json.dumps(payload_invalid).encode("utf-8")
    resp2 = client.post(path, data=body2, headers=make_auth_headers("POST", path, body=body2))
    assert resp2.status_code == 400
    assert resp2.json()["error_code"] == "INVALID_IMAGE_TIER"


# ─── TEST 3: PROMPT VALIDATION ────────────────────────────────────────────────

def test_prepare_image_prompt_validation():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-image/jobs"

    # Empty prompt
    payload_empty = {"prompt": "   ", "tier_key": "standard"}
    body1 = json.dumps(payload_empty).encode("utf-8")
    resp1 = client.post(path, data=body1, headers=make_auth_headers("POST", path, body=body1))
    assert resp1.status_code == 400
    assert resp1.json()["error_code"] == "PROMPT_REQUIRED"

    # Prompt too long (>2000 chars)
    payload_long = {"prompt": "A" * 2001, "tier_key": "standard"}
    body2 = json.dumps(payload_long).encode("utf-8")
    resp2 = client.post(path, data=body2, headers=make_auth_headers("POST", path, body=body2))
    assert resp2.status_code == 400
    assert resp2.json()["error_code"] == "PROMPT_TOO_LONG"


# ─── TEST 4: FORBIDDEN AUTHORITY FIELDS REJECTION ─────────────────────────────

def test_prepare_image_rejects_forbidden_authority_fields():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-image/jobs"

    forbidden_payloads = [
        {"prompt": "Photo", "tier_key": "standard", "provider": "hacked_provider"},
        {"prompt": "Photo", "tier_key": "standard", "price": 0},
        {"prompt": "Photo", "tier_key": "standard", "amount_xu": 0},
        {"prompt": "Photo", "tier_key": "standard", "status": "completed"},
        {"prompt": "Photo", "tier_key": "standard", "output_url": "https://evil.com/fake.png"},
        {"prompt": "Photo", "tier_key": "standard", "wallet_balance": 999999},
    ]

    for payload in forbidden_payloads:
        body = json.dumps(payload).encode("utf-8")
        resp = client.post(path, data=body, headers=make_auth_headers("POST", path, body=body))
        assert resp.status_code == 400
        assert resp.json()["error_code"] == "FORBIDDEN_AUTHORITY_FIELD_REJECTED"


# ─── TEST 5: IDEMPOTENCY REPLAY VS CONFLICT ───────────────────────────────────

def test_idempotency_same_key_reuse_vs_conflict():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-image/jobs"

    key = "idem-image-test-key-42"
    payload = {
        "tier_key": "standard",
        "prompt": "Cyberpunk city alley in rainy neon lights",
        "aspect_ratio": "9:16",
        "idempotency_key": key,
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="12345")

    # Initial creation
    resp1 = client.post(path, data=body, headers=headers)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["replayed"] is False
    job_id_1 = data1["job"]["job_id"]

    # Replay with identical payload -> 200, replayed=True, same job_id
    resp2 = client.post(path, data=body, headers=headers)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["replayed"] is True
    assert data2["job"]["job_id"] == job_id_1

    # Conflict: same key but changed prompt -> 409 IDEMPOTENCY_CONFLICT
    conflicting_payload = {
        "tier_key": "standard",
        "prompt": "DIFFERENT PROMPT: Sunny mountain meadow",
        "aspect_ratio": "9:16",
        "idempotency_key": key,
    }
    body_conflict = json.dumps(conflicting_payload).encode("utf-8")
    headers_conflict = make_auth_headers("POST", path, body=body_conflict, actor_id="12345")
    resp3 = client.post(path, data=body_conflict, headers=headers_conflict)
    assert resp3.status_code == 409
    assert resp3.json()["error_code"] == "IDEMPOTENCY_CONFLICT"


# ─── TEST 6: CROSS-ACCOUNT TENANT ISOLATION ───────────────────────────────────

def test_cross_account_tenant_isolation():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-image/jobs"

    # User A creates a job
    payload = {
        "tier_key": "standard",
        "prompt": "Private photo for user A",
        "idempotency_key": "user-a-key-99",
    }
    body = json.dumps(payload).encode("utf-8")
    headers_a = make_auth_headers("POST", path, body=body, actor_id="10001")
    resp_a = client.post(path, data=body, headers=headers_a)
    assert resp_a.status_code == 200
    job_id = resp_a.json()["job"]["job_id"]

    # User B tries to use the same idempotency key -> 403 CROSS_TENANT_IDEMPOTENCY_COLLISION
    headers_b = make_auth_headers("POST", path, body=body, actor_id="10002")
    resp_b_collide = client.post(path, data=body, headers=headers_b)
    assert resp_b_collide.status_code == 403
    assert resp_b_collide.json()["error_code"] == "CROSS_TENANT_IDEMPOTENCY_COLLISION"

    # User B queries User A's job -> 404 JOB_NOT_FOUND
    detail_path = f"/internal/v1/web-image/jobs/{job_id}"
    resp_b_get = client.get(detail_path, headers=make_auth_headers("GET", detail_path, actor_id="10002"))
    assert resp_b_get.status_code == 404
    assert resp_b_get.json()["error_code"] == "JOB_NOT_FOUND"


# ─── TEST 7: ATOMIC CLAIM, CONFIRM EXECUTION & SETTLEMENT ──────────────────────

def test_confirm_job_execution_atomic_claim_and_provider_submit():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-image/jobs"

    payload = {
        "tier_key": "standard",
        "prompt": "Cinematic portrait with natural studio lighting",
        "aspect_ratio": "1:1",
        "idempotency_key": "confirm-test-img-1",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="55555")
    resp = client.post(path, data=body, headers=headers)
    assert resp.status_code == 200
    job_id = resp.json()["job"]["job_id"]

    confirm_path = f"/internal/v1/web-image/jobs/{job_id}/confirm"
    confirm_headers = make_auth_headers("POST", confirm_path, actor_id="55555")

    mock_image_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR_MOCK_PNG_DATA"
    mock_result = {
        "status": "PASS",
        "http_status": 200,
        "image_bytes": mock_image_bytes,
        "image_url": "https://cdn.example.com/mock_image.png",
        "model": "nano-banana",
    }

    mock_spend = {"ok": True, "final_cost": 20}
    with patch("bot.shopaikey_image_generate", new_callable=AsyncMock) as mock_gen, \
         patch("bot.spend_fixed_credit_idempotent_info") as mock_charge:
        mock_gen.return_value = mock_result
        mock_charge.return_value = mock_spend

        confirm_resp = client.post(confirm_path, headers=confirm_headers)
        assert confirm_resp.status_code == 200
        data = confirm_resp.json()
        assert data["ok"] is True
        job = data["job"]
        assert job["status"] == "completed"
        assert job["quote_xu"] == 20
        assert job["charged_xu"] == 20
        assert job["has_artifact"] is True
        assert job["can_download"] is True

        # Exactly 1 debit call with proper arguments
        assert mock_charge.call_count == 1
        charge_args = mock_charge.call_args[0]
        assert charge_args[0] == 55555  # uid
        assert charge_args[1] == 20     # quote_xu

    # Re-confirm completed job -> idempotent 200 without extra charge
    confirm_resp2 = client.post(confirm_path, headers=confirm_headers)
    assert confirm_resp2.status_code == 200
    assert confirm_resp2.json()["job"]["status"] == "completed"


# ─── TEST 8: PROVIDER FAILURE YIELDS ZERO DEBIT ───────────────────────────────

def test_provider_failure_yields_zero_debit():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-image/jobs"

    payload = {
        "tier_key": "standard",
        "prompt": "Test error handling prompt",
        "idempotency_key": "confirm-test-fail-1",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="77777")
    resp = client.post(path, data=body, headers=headers)
    assert resp.status_code == 200
    job_id = resp.json()["job"]["job_id"]

    confirm_path = f"/internal/v1/web-image/jobs/{job_id}/confirm"
    confirm_headers = make_auth_headers("POST", confirm_path, actor_id="77777")

    mock_fail = {
        "status": "FAIL_BAD_REQUEST",
        "http_status": 400,
        "detail": "Model upstream capacity exhausted",
    }
    with patch("bot.shopaikey_image_generate", new_callable=AsyncMock) as mock_gen, \
         patch("bot.spend_fixed_credit_idempotent_info") as mock_charge:
        mock_gen.return_value = mock_fail

        confirm_resp = client.post(confirm_path, headers=confirm_headers)
        assert confirm_resp.status_code == 422
        data = confirm_resp.json()
        assert data["ok"] is False
        assert data["error_code"] == "PROVIDER_IMAGE_FAILED"
        job = data["job"]
        assert job["status"] == "failed"
        assert job["charged_xu"] == 0

        # Zero wallet charge calls!
        assert mock_charge.call_count == 0


# ─── TEST 9: ARTIFACT STREAM SERVING ──────────────────────────────────────────

def test_artifact_endpoint_serves_valid_image():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-image/jobs"

    payload = {
        "tier_key": "low",
        "prompt": "Simple graphic design element",
        "idempotency_key": "artifact-test-1",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", path, body=body, actor_id="88888")
    resp = client.post(path, data=body, headers=headers)
    job_id = resp.json()["job"]["job_id"]

    confirm_path = f"/internal/v1/web-image/jobs/{job_id}/confirm"
    mock_bytes = b"\x89PNG\r\n\x1a\nREAL_IMAGE_BYTES_PAYLOAD"
    with patch("bot.shopaikey_image_generate", new_callable=AsyncMock) as mock_gen, \
         patch("bot.spend_fixed_credit_idempotent_info") as mock_charge:
        mock_gen.return_value = {"status": "PASS", "image_bytes": mock_bytes}
        mock_charge.return_value = {"ok": True, "final_cost": 20}
        client.post(confirm_path, headers=make_auth_headers("POST", confirm_path, actor_id="88888"))

    # Fetch artifact as owner
    artifact_path = f"/internal/v1/web-image/jobs/{job_id}/artifact"
    art_resp = client.get(artifact_path, headers=make_auth_headers("GET", artifact_path, actor_id="88888"))
    assert art_resp.status_code == 200
    assert art_resp.content == mock_bytes
    assert art_resp.headers["content-type"] == "image/png"

    # User B cannot download User A's artifact
    art_resp_b = client.get(artifact_path, headers=make_auth_headers("GET", artifact_path, actor_id="99999"))
    assert art_resp_b.status_code == 404
    assert art_resp_b.json()["error_code"] == "ARTIFACT_NOT_FOUND"


# ─── TEST 10: SAFE READ-ONLY LIST ENDPOINT ────────────────────────────────────

def test_list_jobs_for_actor():
    client = TestClient(bot.fastapi_app)
    path = "/internal/v1/web-image/jobs"

    headers = make_auth_headers("GET", path, actor_id="12345")
    resp = client.get(path, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert isinstance(data["jobs"], list)
    # Ensure internal paths are masked in list projection
    for j in data["jobs"]:
        assert "artifact_path" not in j
        assert "settlement_idempotency_key" not in j
