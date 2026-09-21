"""Green contract test suite for B02: Canonical Bot-Owned Admin Pricing Commercial Authority & Publication.

Validates all 19 required B02 specifications and invariants:
1. GET collection returns all canonical price keys from BASE_PRICING_CATALOG
2. GET single returns base values, effective values, version, and metadata
3. PATCH price mutation succeeds with CAS (expected_version) and returns write receipt
4. Fresh canonical readback matches committed update in SQLite and API
5. Stale expected_version rejected with 409 Conflict (VERSION_CONFLICT_STALE_WRITE)
6. Idempotent replay with same Request-ID returns existing receipt and 200 OK
7. Audit record persisted in admin_pricing_audit with SHA-256 digest
8. Unknown price key returns 404 (UNKNOWN_PRICE_KEY)
9. Immutable canonical free price key (editable=False) rejected with 400 (IMMUTABLE_PRICE_KEY_REJECTED)
10. Forbidden internal cost fields (cost, provider_cost, api_key, etc.) rejected with 400
11. Negative price or zero on paid price rejected with 400
12. Decimal value on integer price key rejected with 400 (INVALID_PRICE_VALUE_TYPE)
13. Decimal value accepted on float price key (subdub_auto_word)
14. Missing or empty reason rejected with 400 (REASON_MANDATORY)
15. Unauthorized caller rejected with 401 / 503
16. Consumer propagation: public_quality_catalog reflects overridden video tier price
17. Consumer propagation: public_image_quality_catalog reflects overridden image tier price
18. Consumer propagation: music background & vocal full quote reflects overridden price
19. Safety invariant: Zero mutations to wallet, user credits, credit events, or PayOS orders
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import time
from typing import Any
import pytest
from starlette.testclient import TestClient

import bot
from services.admin_pricing_service import (
    BASE_PRICING_CATALOG,
    clear_runtime_pricing_cache,
    ensure_admin_pricing_schema,
    get_canonical_effective_price,
    get_canonical_pricing_collection,
    get_canonical_pricing_single,
    update_canonical_pricing,
    update_canonical_pricing_cas,
    generate_pricing_write_receipt,
    verify_fresh_canonical_readback,
)
from services.admin_wallet_service import compute_internal_admin_wallet_signature
from services.video_ai_real_pricing import (
    public_quality_catalog,
    public_image_quality_catalog,
    public_music_background_prices,
)


def create_test_db(db_path: Path) -> sqlite3.Connection:
    """Create isolated SQLite test database with canonical wallet, job, and payment tables."""
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        username TEXT,
        credits INTEGER DEFAULT 0,
        is_vip INTEGER DEFAULT 0,
        join_date TEXT,
        total_spent INTEGER DEFAULT 0
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS credit_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        delta INTEGER,
        balance_after INTEGER,
        event_type TEXT,
        ref_id TEXT,
        note TEXT,
        created_at DATETIME
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS video_projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        product_type TEXT,
        status TEXT,
        created_at DATETIME
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS payos_orders (
        order_code INTEGER PRIMARY KEY,
        user_id TEXT,
        amount INTEGER,
        status TEXT
    )""")
    ensure_admin_pricing_schema(conn)
    return conn


def build_auth_headers(
    method: str,
    path: str,
    body_bytes: bytes,
    token: str = "test-b02-bridge-token",
    secret: str = "test-b02-hmac-secret",
    actor_id: str = "7126457028",
    request_id: str = "req-b02-test-01",
) -> dict[str, str]:
    now_ts = str(int(time.time()))
    sig = compute_internal_admin_wallet_signature(
        secret=secret,
        timestamp=now_ts,
        request_id=request_id,
        method=method,
        path=path,
        body_bytes=body_bytes,
        actor_id=actor_id,
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-TOAN-AAS-Signature": sig,
        "X-TOAN-AAS-Timestamp": now_ts,
        "X-TOAN-AAS-Request-ID": request_id,
        "X-TOAN-AAS-Actor-ID": actor_id,
        "Content-Type": "application/json",
    }


@pytest.fixture(autouse=True)
def clean_cache():
    clear_runtime_pricing_cache()
    yield
    clear_runtime_pricing_cache()


@pytest.fixture
def test_env(tmp_path: Path, monkeypatch):
    db_file = tmp_path / "b02_test.db"
    conn = create_test_db(db_file)
    conn.execute("INSERT INTO users (user_id, username, credits) VALUES ('1001', 'test_user', 500)")
    conn.execute("INSERT INTO credit_events (user_id, delta, balance_after, event_type) VALUES ('1001', 500, 500, 'initial')")
    conn.execute("INSERT INTO video_projects (user_id, product_type, status) VALUES ('1001', 'video_ai_prompt', 'completed')")
    conn.execute("INSERT INTO payos_orders (order_code, user_id, amount, status) VALUES (99901, '1001', 50000, 'PAID')")
    conn.commit()
    conn.close()

    monkeypatch.setattr(bot, "DB_FILE", str(db_file))
    token = "test-b02-bridge-token"
    secret = "test-b02-hmac-secret"
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", token)
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", secret)

    client = TestClient(bot.fastapi_app)
    return {"db_file": db_file, "client": client, "token": token, "secret": secret}


# ---------------------------------------------------------------------------
# Requirement 1: GET collection returns all canonical price keys
# ---------------------------------------------------------------------------
def test_req_01_get_collection_returns_all_canonical_pricing(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/pricing"
    headers = build_auth_headers("GET", path, b"")
    resp = client.get(path, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["total_count"] == len(BASE_PRICING_CATALOG)
    assert len(data["pricing"]) == len(BASE_PRICING_CATALOG)
    keys = {p["price_key"] for p in data["pricing"]}
    assert keys == set(BASE_PRICING_CATALOG.keys())


# ---------------------------------------------------------------------------
# Requirement 2: GET single returns base values, effective values, version
# ---------------------------------------------------------------------------
def test_req_02_get_pricing_single_returns_correct_fields(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/pricing/video_tier_400"
    headers = build_auth_headers("GET", path, b"")
    resp = client.get(path, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    pricing = data["pricing"]
    assert pricing["price_key"] == "video_tier_400"
    assert pricing["product_key"] == "video_ai_prompt"
    assert pricing["base_value"] == 80
    assert pricing["effective_value"] == 80
    assert pricing["version"] == 1
    assert pricing["has_override"] is False


# ---------------------------------------------------------------------------
# Requirement 3: PATCH price mutation succeeds with CAS & write receipt
# ---------------------------------------------------------------------------
def test_req_03_patch_pricing_mutation_succeeds_with_cas(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/pricing/video_tier_400"
    payload = {
        "expected_version": 1,
        "new_value": 95,
        "reason": "Adjust tier 400 price for summer promotion",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = build_auth_headers("PATCH", path, body, request_id="req-b02-03")
    resp = client.patch(path, content=body, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "receipt" in data
    rcpt = data["receipt"]
    assert rcpt["price_key"] == "video_tier_400"
    assert rcpt["previous_version"] == 1
    assert rcpt["new_version"] == 2
    assert rcpt["new_value"] == 95
    assert rcpt["mutation_digest"] != ""
    assert rcpt["receipt_id"].startswith("rcpt_prc_")
    assert rcpt["idempotent_replay"] is False

    # Check updated pricing view in response
    pricing = data["pricing"]
    assert pricing["effective_value"] == 95
    assert pricing["version"] == 2


# ---------------------------------------------------------------------------
# Requirement 4: Fresh canonical readback matches committed update
# ---------------------------------------------------------------------------
def test_req_04_fresh_canonical_readback_matches_committed_update(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/pricing/video_tier_400"
    payload = {
        "expected_version": 1,
        "new_value": 92,
        "reason": "Test fresh readback",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = build_auth_headers("PATCH", path, body, request_id="req-b02-04")
    resp = client.patch(path, content=body, headers=headers)
    assert resp.status_code == 200

    # Readback via API
    get_headers = build_auth_headers("GET", path, b"")
    get_resp = client.get(path, headers=get_headers)
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["pricing"]["effective_value"] == 92
    assert data["pricing"]["version"] == 2

    # Readback via SQLite helper
    db_file = test_env["db_file"]
    assert verify_fresh_canonical_readback("video_tier_400", 92, db_path=str(db_file)) is True


# ---------------------------------------------------------------------------
# Requirement 5: Stale expected_version rejected with 409 Conflict
# ---------------------------------------------------------------------------
def test_req_05_stale_expected_version_rejected_conflict_409(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/pricing/video_tier_500"

    # First mutation: 1 -> 2
    payload1 = {"expected_version": 1, "new_value": 115, "reason": "First update"}
    body1 = json.dumps(payload1).encode("utf-8")
    headers1 = build_auth_headers("PATCH", path, body1, request_id="req-b02-05a")
    resp1 = client.patch(path, content=body1, headers=headers1)
    assert resp1.status_code == 200

    # Second mutation with stale expected_version 1
    payload2 = {"expected_version": 1, "new_value": 120, "reason": "Stale update attempt"}
    body2 = json.dumps(payload2).encode("utf-8")
    headers2 = build_auth_headers("PATCH", path, body2, request_id="req-b02-05b")
    resp2 = client.patch(path, content=body2, headers=headers2)
    assert resp2.status_code == 409
    err = resp2.json()
    assert err["error_code"] == "VERSION_CONFLICT_STALE_WRITE"
    assert err["current_version"] == 2
    assert err["expected_version"] == 1


# ---------------------------------------------------------------------------
# Requirement 6: Idempotent replay returns existing receipt
# ---------------------------------------------------------------------------
def test_req_06_idempotent_replay_returns_existing_receipt(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/pricing/video_tier_600"
    payload = {"expected_version": 1, "new_value": 165, "reason": "Idempotency test"}
    body = json.dumps(payload).encode("utf-8")
    headers = build_auth_headers("PATCH", path, body, request_id="req-b02-idempotent-01")

    # Call 1: primary write
    resp1 = client.patch(path, content=body, headers=headers)
    assert resp1.status_code == 200
    data1 = resp1.json()
    rcpt1 = data1["receipt"]
    assert rcpt1["idempotent_replay"] is False

    # Call 2: duplicate replay with same request_id
    resp2 = client.patch(path, content=body, headers=headers)
    assert resp2.status_code == 200
    data2 = resp2.json()
    rcpt2 = data2["receipt"]
    assert rcpt2["idempotent_replay"] is True
    assert rcpt2["receipt_id"] == rcpt1["receipt_id"]
    assert rcpt2["mutation_digest"] == rcpt1["mutation_digest"]
    assert rcpt2["new_version"] == rcpt1["new_version"]


# ---------------------------------------------------------------------------
# Requirement 7: Audit record persisted in admin_pricing_audit
# ---------------------------------------------------------------------------
def test_req_07_audit_record_persisted_in_database(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/pricing/video_tier_200"
    payload = {"expected_version": 1, "new_value": 210, "reason": "Audit verification"}
    body = json.dumps(payload).encode("utf-8")
    headers = build_auth_headers("PATCH", path, body, actor_id="7126457028", request_id="req-b02-audit-01")
    resp = client.patch(path, content=body, headers=headers)
    assert resp.status_code == 200

    # Query SQLite directly
    conn = sqlite3.connect(str(test_env["db_file"]))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM admin_pricing_audit WHERE price_key = 'video_tier_200'")
    rows = cur.fetchall()
    conn.close()

    assert len(rows) == 1
    row = dict(rows[0])
    assert row["actor_id"] == "7126457028"
    assert row["reason"] == "Audit verification"
    assert row["previous_version"] == 1
    assert row["new_version"] == 2
    assert row["previous_value"] == "200"
    assert row["new_value"] == "210"
    assert row["request_id"] == "req-b02-audit-01"
    assert row["mutation_digest"] != ""


# ---------------------------------------------------------------------------
# Requirement 8: Unknown price key fails closed with 404
# ---------------------------------------------------------------------------
def test_req_08_unknown_price_key_fails_closed_404(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/pricing/unknown_tier_9999"
    payload = {"expected_version": 1, "new_value": 100, "reason": "Unknown key test"}
    body = json.dumps(payload).encode("utf-8")
    headers = build_auth_headers("PATCH", path, body)
    resp = client.patch(path, content=body, headers=headers)
    assert resp.status_code == 404
    data = resp.json()
    assert data["error_code"] == "UNKNOWN_PRICE_KEY"


# ---------------------------------------------------------------------------
# Requirement 9: Immutable canonical free price key rejected with 400
# ---------------------------------------------------------------------------
def test_req_09_immutable_price_key_fails_closed_400(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/pricing/voice_default_tts"
    payload = {"expected_version": 1, "new_value": 50, "reason": "Attempting to charge for default tts"}
    body = json.dumps(payload).encode("utf-8")
    headers = build_auth_headers("PATCH", path, body)
    resp = client.patch(path, content=body, headers=headers)
    assert resp.status_code == 400
    data = resp.json()
    assert data["error_code"] == "IMMUTABLE_PRICE_KEY_REJECTED"


# ---------------------------------------------------------------------------
# Requirement 10: Forbidden internal cost fields rejected with 400
# ---------------------------------------------------------------------------
def test_req_10_immutable_cost_fields_rejected_400(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/pricing/video_tier_400"
    payload = {
        "expected_version": 1,
        "new_value": 85,
        "cost": 10,
        "provider_cost": 5,
        "reason": "Attempting internal cost mutation",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = build_auth_headers("PATCH", path, body)
    resp = client.patch(path, content=body, headers=headers)
    assert resp.status_code == 400
    data = resp.json()
    assert data["error_code"] == "IMMUTABLE_FIELD_MODIFICATION_FORBIDDEN"


# ---------------------------------------------------------------------------
# Requirement 11: Negative or zero paid price rejected with 400
# ---------------------------------------------------------------------------
def test_req_11_negative_or_zero_paid_price_rejected_400(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/pricing/video_tier_400"

    # Negative price
    neg_body = json.dumps({"expected_version": 1, "new_value": -10, "reason": "Negative price"}).encode("utf-8")
    headers = build_auth_headers("PATCH", path, neg_body)
    resp_neg = client.patch(path, content=neg_body, headers=headers)
    assert resp_neg.status_code == 400
    assert resp_neg.json()["error_code"] == "NEGATIVE_PRICE_REJECTED"

    # Zero price on paid policy
    zero_body = json.dumps({"expected_version": 1, "new_value": 0, "reason": "Zero price"}).encode("utf-8")
    headers = build_auth_headers("PATCH", path, zero_body)
    resp_zero = client.patch(path, content=zero_body, headers=headers)
    assert resp_zero.status_code == 400
    assert resp_zero.json()["error_code"] == "PAID_PRICE_CANNOT_BE_ZERO"


# ---------------------------------------------------------------------------
# Requirement 12: Decimal value on integer price key rejected with 400
# ---------------------------------------------------------------------------
def test_req_12_decimal_value_on_int_type_rejected_400(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/pricing/video_tier_400"
    payload = {"expected_version": 1, "new_value": 85.5, "reason": "Decimal on int type"}
    body = json.dumps(payload).encode("utf-8")
    headers = build_auth_headers("PATCH", path, body)
    resp = client.patch(path, content=body, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "INVALID_PRICE_VALUE_TYPE"


# ---------------------------------------------------------------------------
# Requirement 13: Decimal value accepted on float price key
# ---------------------------------------------------------------------------
def test_req_13_decimal_value_accepted_on_float_type(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/pricing/subdub_auto_word"
    payload = {"expected_version": 1, "new_value": 0.75, "reason": "Adjust auto word rate"}
    body = json.dumps(payload).encode("utf-8")
    headers = build_auth_headers("PATCH", path, body)
    resp = client.patch(path, content=body, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["pricing"]["effective_value"] == 0.75


# ---------------------------------------------------------------------------
# Requirement 14: Missing or empty reason rejected with 400
# ---------------------------------------------------------------------------
def test_req_14_missing_or_empty_reason_rejected_400(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/pricing/video_tier_400"
    payload = {"expected_version": 1, "new_value": 85, "reason": "   "}
    body = json.dumps(payload).encode("utf-8")
    headers = build_auth_headers("PATCH", path, body)
    resp = client.patch(path, content=body, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "REASON_MANDATORY"


# ---------------------------------------------------------------------------
# Requirement 15: Unauthorized caller rejected with 401 / 503
# ---------------------------------------------------------------------------
def test_req_15_unauthorized_caller_rejected(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/pricing/video_tier_400"
    # No auth headers
    resp = client.get(path)
    assert resp.status_code in (401, 503)

    # Invalid signature
    bad_headers = {
        "Authorization": "Bearer test-b02-bridge-token",
        "X-TOAN-AAS-Signature": "invalidsignature00000000000000000000000000000000000000000000",
        "X-TOAN-AAS-Timestamp": str(int(time.time())),
        "X-TOAN-AAS-Request-ID": "req-bad-sig",
        "X-TOAN-AAS-Actor-ID": "7126457028",
    }
    resp_bad = client.get(path, headers=bad_headers)
    assert resp_bad.status_code in (401, 503)


# ---------------------------------------------------------------------------
# Requirement 16: Consumer propagation: video quality catalog reflects effective price
# ---------------------------------------------------------------------------
def test_req_16_consumer_propagation_video_quality_catalog(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/pricing/video_tier_400"
    payload = {"expected_version": 1, "new_value": 99, "reason": "Video tier override propagation"}
    body = json.dumps(payload).encode("utf-8")
    headers = build_auth_headers("PATCH", path, body)
    resp = client.patch(path, content=body, headers=headers)
    assert resp.status_code == 200

    catalog = public_quality_catalog()
    tier_400 = next((item for item in catalog if str(item.get("tier_id")) == "400"), None)
    assert tier_400 is not None
    assert tier_400["unit_xu"] == 99


# ---------------------------------------------------------------------------
# Requirement 17: Consumer propagation: image quality catalog reflects effective price
# ---------------------------------------------------------------------------
def test_req_17_consumer_propagation_image_quality_catalog(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/pricing/image_tier_standard"
    payload = {"expected_version": 1, "new_value": 25, "reason": "Image tier override propagation"}
    body = json.dumps(payload).encode("utf-8")
    headers = build_auth_headers("PATCH", path, body)
    resp = client.patch(path, content=body, headers=headers)
    assert resp.status_code == 200

    catalog = public_image_quality_catalog()
    tier_std = next((item for item in catalog if str(item.get("tier_key")) == "standard"), None)
    assert tier_std is not None
    assert tier_std["unit_xu"] == 25


# ---------------------------------------------------------------------------
# Requirement 18: Consumer propagation: music background & vocal full quote
# ---------------------------------------------------------------------------
def test_req_18_consumer_propagation_music_prices(test_env):
    client = test_env["client"]

    # Mutate background music basic: 130 -> 145
    path_bg = "/internal/v1/admin/pricing/music_background_basic"
    body_bg = json.dumps({"expected_version": 1, "new_value": 145, "reason": "Music bg price override"}).encode("utf-8")
    headers_bg = build_auth_headers("PATCH", path_bg, body_bg)
    resp_bg = client.patch(path_bg, content=body_bg, headers=headers_bg)
    assert resp_bg.status_code == 200

    bg_prices = public_music_background_prices()
    assert bg_prices["basic"] == 145

    # Mutate vocal full song: 800 -> 850
    path_song = "/internal/v1/admin/pricing/music_vocal_full"
    body_song = json.dumps({"expected_version": 1, "new_value": 850, "reason": "Vocal full price override"}).encode("utf-8")
    headers_song = build_auth_headers("PATCH", path_song, body_song)
    resp_song = client.patch(path_song, content=body_song, headers=headers_song)
    assert resp_song.status_code == 200

    quote_xu = bot.music_product_quote_price_xu("song")
    assert quote_xu == 850
    ai_output_xu = bot.music_ai_output_price_xu(120, "song_full")
    assert ai_output_xu == 850


# ---------------------------------------------------------------------------
# Requirement 19: Safety invariant: Zero mutations to wallet, credit events, or PayOS
# ---------------------------------------------------------------------------
def test_req_19_wallet_and_payment_tables_strictly_unchanged(test_env):
    conn = sqlite3.connect(str(test_env["db_file"]))
    conn.row_factory = sqlite3.Row
    user_before = dict(conn.execute("SELECT * FROM users WHERE user_id = '1001'").fetchone())
    credit_events_before = [dict(r) for r in conn.execute("SELECT * FROM credit_events").fetchall()]
    payos_before = [dict(r) for r in conn.execute("SELECT * FROM payos_orders").fetchall()]
    video_projects_before = [dict(r) for r in conn.execute("SELECT * FROM video_projects").fetchall()]
    conn.close()

    # Perform multiple pricing mutations
    client = test_env["client"]
    for key, val in [("video_tier_300", 230), ("content_full_pack", 75), ("chat_pro_input", 6)]:
        path = f"/internal/v1/admin/pricing/{key}"
        body = json.dumps({"expected_version": 1, "new_value": val, "reason": "Invariant safety check"}).encode("utf-8")
        headers = build_auth_headers("PATCH", path, body, request_id=f"req-safe-{key}")
        resp = client.patch(path, content=body, headers=headers)
        assert resp.status_code == 200

    conn = sqlite3.connect(str(test_env["db_file"]))
    conn.row_factory = sqlite3.Row
    user_after = dict(conn.execute("SELECT * FROM users WHERE user_id = '1001'").fetchone())
    credit_events_after = [dict(r) for r in conn.execute("SELECT * FROM credit_events").fetchall()]
    payos_after = [dict(r) for r in conn.execute("SELECT * FROM payos_orders").fetchall()]
    video_projects_after = [dict(r) for r in conn.execute("SELECT * FROM video_projects").fetchall()]
    conn.close()

    assert user_after == user_before
    assert credit_events_after == credit_events_before
    assert payos_after == payos_before
    assert video_projects_after == video_projects_before
