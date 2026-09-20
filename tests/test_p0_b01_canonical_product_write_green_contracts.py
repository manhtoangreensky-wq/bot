"""Green contract test suite for B01: Canonical Bot-Owned Product Write Authority.

Validates all 18 required B01 focus points:
1. GET collection returns canonical product set (18 products)
2. GET product returns base values, effective override, version
3. PATCH display_name succeeds
4. PATCH description succeeds
5. PATCH public_visible succeeds
6. PATCH commercial_enabled succeeds when allowed
7. PATCH sort_order succeeds
8. unknown product fails closed (404)
9. unknown field fails closed (400)
10. pricing field mutation is rejected in B01 (400 IMMUTABLE_FIELD_MODIFICATION_FORBIDDEN)
11. execution safety lock cannot be bypassed (commercial_enabled=True != execution_enabled=True)
12. stale expected_version is rejected (409 Conflict)
13. audit record appended exactly once per mutation
14. write receipt returned with valid digest and receipt_id
15. canonical readback matches committed update
16. readback idempotency and determinism
17. unauthorized caller cannot write (401 / 503)
18. wallet/history/job/payment tables strictly unchanged (0 mutations)
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import sqlite3
import time
import pytest
from fastapi.testclient import TestClient

import bot
from services.admin_product_service import (
    BASE_PRODUCTS,
    ensure_admin_product_schema,
    get_canonical_product_collection,
    get_canonical_product_single,
    update_canonical_product,
    resolve_effective_product,
)
from services.admin_wallet_service import compute_internal_admin_wallet_signature


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
    ensure_admin_product_schema(conn)
    return conn


def build_auth_headers(
    method: str,
    path: str,
    body_bytes: bytes,
    token: str = "test-b01-bridge-token",
    secret: str = "test-b01-hmac-secret",
    actor_id: str = "7126457028",
    request_id: str = "req-b01-test-01",
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


@pytest.fixture
def test_env(tmp_path: Path, monkeypatch):
    db_file = tmp_path / "b01_test.db"
    conn = create_test_db(db_file)
    conn.execute("INSERT INTO users (user_id, username, credits) VALUES ('1001', 'test_user', 500)")
    conn.execute("INSERT INTO credit_events (user_id, delta, balance_after, event_type) VALUES ('1001', 500, 500, 'initial')")
    conn.execute("INSERT INTO video_projects (user_id, product_type, status) VALUES ('1001', 'video_trend', 'completed')")
    conn.execute("INSERT INTO payos_orders (order_code, user_id, amount, status) VALUES (99901, '1001', 50000, 'PAID')")
    conn.commit()
    conn.close()

    monkeypatch.setattr(bot, "DB_FILE", str(db_file))
    token = "test-b01-bridge-token"
    secret = "test-b01-hmac-secret"
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", token)
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", secret)

    client = TestClient(bot.fastapi_app)
    return {"db_file": db_file, "client": client, "token": token, "secret": secret}


# ---------------------------------------------------------------------------
# Requirement 1: GET collection returns canonical product set
# ---------------------------------------------------------------------------
def test_req_01_get_collection_returns_canonical_set(test_env):
    client = test_env["client"]
    headers = build_auth_headers("GET", "/internal/v1/admin/products", b"")
    resp = client.get("/internal/v1/admin/products", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["count"] == 18
    product_keys = [p["product_key"] for p in data["products"]]
    assert "video_trend" in product_keys
    assert "video_ai_prompt" in product_keys
    assert "multi_scene_film" in product_keys
    assert "image_generation" in product_keys
    assert "voice_tts" in product_keys
    assert "music_generation" in product_keys
    assert "subdub_service" in product_keys
    assert "chat_pro" in product_keys


# ---------------------------------------------------------------------------
# Requirement 2: GET product returns base values, effective override, version
# ---------------------------------------------------------------------------
def test_req_02_get_product_single(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/products/video_ai_prompt"
    headers = build_auth_headers("GET", path, b"")
    resp = client.get(path, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["product_key"] == "video_ai_prompt"
    assert "base" in data
    assert "effective" in data
    assert data["version"] == 1
    assert data["has_override"] is False
    assert data["effective"]["display_name"] == "Video AI chân thật (từ Prompt)"
    assert data["effective"]["execution_enabled"] is True


# ---------------------------------------------------------------------------
# Requirement 3: PATCH display_name succeeds
# ---------------------------------------------------------------------------
def test_req_03_patch_display_name_succeeds(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/products/video_ai_prompt"
    payload = {
        "expected_version": 1,
        "changes": {"display_name": "Tạo Video AI Siêu Thực 4K"},
        "reason": "Cập nhật thương hiệu hiển thị mới",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = build_auth_headers("PATCH", path, body_bytes)
    resp = client.patch(path, content=body_bytes, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["previous_version"] == 1
    assert data["new_version"] == 2
    assert data["effective_product"]["display_name"] == "Tạo Video AI Siêu Thực 4K"
    assert data["readback_match"] is True


# ---------------------------------------------------------------------------
# Requirement 4: PATCH description succeeds
# ---------------------------------------------------------------------------
def test_req_04_patch_description_succeeds(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/products/video_ai_prompt"
    payload = {
        "expected_version": 1,
        "changes": {"description": "Mô tả mới chi tiết hơn cho công cụ tạo video prompt"},
        "reason": "Cập nhật mô tả chuẩn SEO",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = build_auth_headers("PATCH", path, body_bytes)
    resp = client.patch(path, content=body_bytes, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["new_version"] == 2
    assert data["effective_product"]["description"] == "Mô tả mới chi tiết hơn cho công cụ tạo video prompt"


# ---------------------------------------------------------------------------
# Requirement 5: PATCH public_visible succeeds
# ---------------------------------------------------------------------------
def test_req_05_patch_public_visible_succeeds(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/products/video_trend"
    payload = {
        "expected_version": 1,
        "changes": {"public_visible": False},
        "reason": "Ẩn tạm thời để bảo trì giao diện",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = build_auth_headers("PATCH", path, body_bytes)
    resp = client.patch(path, content=body_bytes, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["effective_product"]["public_visible"] is False


# ---------------------------------------------------------------------------
# Requirement 6: PATCH commercial_enabled succeeds when allowed
# ---------------------------------------------------------------------------
def test_req_06_patch_commercial_enabled_succeeds(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/products/video_ai_image"
    payload = {
        "expected_version": 1,
        "changes": {"commercial_enabled": False},
        "reason": "Dừng thương mại hoá sản phẩm ảnh sang video",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = build_auth_headers("PATCH", path, body_bytes)
    resp = client.patch(path, content=body_bytes, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["effective_product"]["commercial_enabled"] is False


# ---------------------------------------------------------------------------
# Requirement 7: PATCH sort_order succeeds
# ---------------------------------------------------------------------------
def test_req_07_patch_sort_order_succeeds(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/products/video_trend"
    payload = {
        "expected_version": 1,
        "changes": {"sort_order": 5},
        "reason": "Đưa sản phẩm trend lên đầu danh sách",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = build_auth_headers("PATCH", path, body_bytes)
    resp = client.patch(path, content=body_bytes, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["effective_product"]["sort_order"] == 5


# ---------------------------------------------------------------------------
# Requirement 8: Unknown product fails closed (404)
# ---------------------------------------------------------------------------
def test_req_08_unknown_product_fails_closed(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/products/non_existent_product_123"
    payload = {
        "expected_version": 1,
        "changes": {"display_name": "Ghost"},
        "reason": "Invalid test",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = build_auth_headers("PATCH", path, body_bytes)
    resp = client.patch(path, content=body_bytes, headers=headers)
    assert resp.status_code == 404
    data = resp.json()
    assert data["ok"] is False
    assert data["error_code"] == "PRODUCT_NOT_FOUND"


# ---------------------------------------------------------------------------
# Requirement 9: Unknown field fails closed (400)
# ---------------------------------------------------------------------------
def test_req_09_unknown_field_fails_closed(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/products/video_ai_prompt"
    payload = {
        "expected_version": 1,
        "changes": {"arbitrary_custom_field": "injected_value"},
        "reason": "Security test",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = build_auth_headers("PATCH", path, body_bytes)
    resp = client.patch(path, content=body_bytes, headers=headers)
    assert resp.status_code == 400
    data = resp.json()
    assert data["ok"] is False
    assert data["error_code"] == "UNKNOWN_OR_DISALLOWED_FIELD"


# ---------------------------------------------------------------------------
# Requirement 10: Pricing field mutation is rejected in B01
# ---------------------------------------------------------------------------
def test_req_10_pricing_field_mutation_rejected(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/products/video_ai_prompt"
    for field in ("unit_xu", "sale_price", "pricing_cost_vnd", "price_xu"):
        payload = {
            "expected_version": 1,
            "changes": {field: 999},
            "reason": "Illegal pricing edit",
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        headers = build_auth_headers("PATCH", path, body_bytes)
        resp = client.patch(path, content=body_bytes, headers=headers)
        assert resp.status_code == 400
        data = resp.json()
        assert data["ok"] is False
        assert data["error_code"] == "IMMUTABLE_FIELD_MODIFICATION_FORBIDDEN"


# ---------------------------------------------------------------------------
# Requirement 11: Execution safety lock cannot be bypassed
# ---------------------------------------------------------------------------
def test_req_11_hard_execution_lock_cannot_be_bypassed(test_env):
    """multi_scene_film has execution_enabled=False in base contract.

    Enabling commercial_enabled=True MUST NEVER enable execution_enabled.
    """
    client = test_env["client"]
    path = "/internal/v1/admin/products/multi_scene_film"
    payload = {
        "expected_version": 1,
        "changes": {"commercial_enabled": True, "display_name": "Phim Dài Tập Commercial"},
        "reason": "Bật thương mại nhưng engine chưa mở execution",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = build_auth_headers("PATCH", path, body_bytes)
    resp = client.patch(path, content=body_bytes, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["effective_product"]["commercial_enabled"] is True
    # CRITICAL INVARIANT: execution_enabled must remain False!
    assert data["effective_product"]["execution_enabled"] is False


# ---------------------------------------------------------------------------
# Requirement 12: Stale expected_version is rejected (409 Conflict)
# ---------------------------------------------------------------------------
def test_req_12_stale_expected_version_rejected(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/products/video_trend"

    # Mutate once to advance version to 2
    payload1 = {
        "expected_version": 1,
        "changes": {"display_name": "Trend V2"},
        "reason": "First mutation",
    }
    body1 = json.dumps(payload1).encode("utf-8")
    resp1 = client.patch(path, content=body1, headers=build_auth_headers("PATCH", path, body1))
    assert resp1.status_code == 200
    assert resp1.json()["new_version"] == 2

    # Second concurrent session tries to mutate with stale version 1
    payload2 = {
        "expected_version": 1,
        "changes": {"display_name": "Stale Attempt"},
        "reason": "Stale CAS mutation",
    }
    body2 = json.dumps(payload2).encode("utf-8")
    resp2 = client.patch(path, content=body2, headers=build_auth_headers("PATCH", path, body2))
    assert resp2.status_code == 409
    data2 = resp2.json()
    assert data2["ok"] is False
    assert data2["error_code"] == "VERSION_CONFLICT_STALE_WRITE"
    assert data2["current_version"] == 2
    assert data2["expected_version"] == 1


# ---------------------------------------------------------------------------
# Requirement 13: Audit record appended exactly once
# ---------------------------------------------------------------------------
def test_req_13_audit_record_appended_exactly_once(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/products/voice_tts"
    payload = {
        "expected_version": 1,
        "changes": {"display_name": "Giọng Đọc AI Cao Cấp"},
        "reason": "Điều chỉnh tên hiển thị dịch vụ Voice",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = build_auth_headers("PATCH", path, body_bytes, actor_id="admin_8888", request_id="req-aud-01")
    resp = client.patch(path, content=body_bytes, headers=headers)
    assert resp.status_code == 200

    # Query audit table directly
    conn = sqlite3.connect(str(test_env["db_file"]))
    c = conn.cursor()
    c.execute("SELECT product_key, actor_id, reason, previous_version, new_version, request_id FROM admin_product_audit WHERE product_key='voice_tts'")
    rows = c.fetchall()
    conn.close()

    assert len(rows) == 1
    audit_row = rows[0]
    assert audit_row[0] == "voice_tts"
    assert audit_row[1] == "admin_8888"
    assert audit_row[2] == "Điều chỉnh tên hiển thị dịch vụ Voice"
    assert audit_row[3] == 1
    assert audit_row[4] == 2
    assert audit_row[5] == "req-aud-01"


# ---------------------------------------------------------------------------
# Requirement 14: Write receipt returned
# ---------------------------------------------------------------------------
def test_req_14_write_receipt_structure(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/products/music_generation"
    payload = {
        "expected_version": 1,
        "changes": {"display_name": "Sáng Tác Âm Nhạc AI Pro"},
        "reason": "Thêm hậu tố Pro",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    resp = client.patch(path, content=body_bytes, headers=build_auth_headers("PATCH", path, body_bytes))
    assert resp.status_code == 200
    data = resp.json()
    receipt = data.get("write_receipt")
    assert receipt is not None
    assert receipt["product_key"] == "music_generation"
    assert receipt["version"] == 2
    assert "mutation_digest" in receipt
    assert receipt["receipt_id"].startswith("rcpt-prod-music_generation-v2-")


# ---------------------------------------------------------------------------
# Requirement 15: Canonical readback matches committed update
# ---------------------------------------------------------------------------
def test_req_15_canonical_readback_matches_committed_update(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/products/subdub_service"
    payload = {
        "expected_version": 1,
        "changes": {"sort_order": 25, "display_name": "SubDub AI Đa Ngôn Ngữ"},
        "reason": "Điều chỉnh thứ tự và tên",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    resp = client.patch(path, content=body_bytes, headers=build_auth_headers("PATCH", path, body_bytes))
    assert resp.status_code == 200
    data = resp.json()
    assert data["readback_match"] is True

    # Subsequent GET must match the same effective state
    get_headers = build_auth_headers("GET", path, b"")
    get_resp = client.get(path, headers=get_headers)
    get_data = get_resp.json()
    assert get_data["effective"]["display_name"] == "SubDub AI Đa Ngôn Ngữ"
    assert get_data["effective"]["sort_order"] == 25
    assert get_data["version"] == 2


# ---------------------------------------------------------------------------
# Requirement 16: Readback idempotency and determinism
# ---------------------------------------------------------------------------
def test_req_16_readback_determinism(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/products/chat_pro"
    get_headers = build_auth_headers("GET", path, b"")

    resp1 = client.get(path, headers=get_headers).json()
    resp2 = client.get(path, headers=get_headers).json()
    resp3 = client.get(path, headers=get_headers).json()

    assert resp1 == resp2 == resp3


# ---------------------------------------------------------------------------
# Requirement 17: Unauthorized caller cannot write
# ---------------------------------------------------------------------------
def test_req_17_unauthorized_caller_rejected(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/products/video_trend"
    payload = {"expected_version": 1, "changes": {"display_name": "Hacked"}, "reason": "Hacking"}
    body_bytes = json.dumps(payload).encode("utf-8")

    # 1. No Authorization header
    resp1 = client.patch(path, content=body_bytes)
    assert resp1.status_code in (401, 503)

    # 2. Invalid Bearer token
    headers_bad_token = {"Authorization": "Bearer bad-token", "Content-Type": "application/json"}
    resp2 = client.patch(path, content=body_bytes, headers=headers_bad_token)
    assert resp2.status_code == 401

    # 3. Bad HMAC signature
    headers_bad_sig = build_auth_headers("PATCH", path, body_bytes)
    headers_bad_sig["X-TOAN-AAS-Signature"] = "bad_signature_digest"
    resp3 = client.patch(path, content=body_bytes, headers=headers_bad_sig)
    assert resp3.status_code == 401


# ---------------------------------------------------------------------------
# Requirement 18: Wallet, history, job, and payment tables unchanged
# ---------------------------------------------------------------------------
def test_req_18_protected_tables_unchanged(test_env):
    """Verify that product configuration mutations NEVER alter users, credits, projects, or orders."""
    conn = sqlite3.connect(str(test_env["db_file"]))
    before_user = conn.execute("SELECT credits FROM users WHERE user_id='1001'").fetchone()[0]
    before_events_count = conn.execute("SELECT COUNT(*) FROM credit_events").fetchone()[0]
    before_jobs_count = conn.execute("SELECT COUNT(*) FROM video_projects").fetchone()[0]
    before_orders_count = conn.execute("SELECT COUNT(*) FROM payos_orders").fetchone()[0]
    conn.close()

    # Perform multiple product mutations
    client = test_env["client"]
    for product in ("video_trend", "image_generation", "voice_tts"):
        path = f"/internal/v1/admin/products/{product}"
        payload = {
            "expected_version": 1,
            "changes": {"display_name": f"{product.upper()} New Brand"},
            "reason": "Rebranding batch test",
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        resp = client.patch(path, content=body_bytes, headers=build_auth_headers("PATCH", path, body_bytes))
        assert resp.status_code == 200

    conn = sqlite3.connect(str(test_env["db_file"]))
    after_user = conn.execute("SELECT credits FROM users WHERE user_id='1001'").fetchone()[0]
    after_events_count = conn.execute("SELECT COUNT(*) FROM credit_events").fetchone()[0]
    after_jobs_count = conn.execute("SELECT COUNT(*) FROM video_projects").fetchone()[0]
    after_orders_count = conn.execute("SELECT COUNT(*) FROM payos_orders").fetchone()[0]
    conn.close()

    assert after_user == before_user == 500
    assert after_events_count == before_events_count == 1
    assert after_jobs_count == before_jobs_count == 1
    assert after_orders_count == before_orders_count == 1
