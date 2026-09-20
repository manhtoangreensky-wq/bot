"""FIRST RED test suite for B01.C1: Canonical Product Authority Reconciliation.

Proves against current main (fe511f5d1a410b5fc1c82680682c7fb3fdaad55e):
1. Admin collection contains canonical customer key: script_image_video (currently FAILS)
2. Admin collection contains canonical customer key: video_idea (currently FAILS)
3. Admin collection does NOT expose executor alias script_to_video as separate product (currently FAILS)
4. Admin collection does NOT expose executor alias video_idea_to_product as separate product (currently FAILS)
5. Effective admin read model for video_local_edit has execution_enabled=False (currently FAILS)
6. Product Video supported tiers equals canonical commercial_contract truth (currently FAILS)
7. Product Video supported ratios equals canonical product authority (currently FAILS)
8. execution_enabled cannot be overridden by admin_product_overrides (currently FAILS)
9. provider_capability comes from canonical engine contract, not hardcoded strings (currently FAILS)
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import time
import pytest
from fastapi.testclient import TestClient

import bot
from services.admin_product_service import ensure_admin_product_schema
from services.admin_wallet_service import compute_internal_admin_wallet_signature
from services import video_tail9, video_uifreeze1, video_project_queue


def create_test_db(db_path: Path) -> sqlite3.Connection:
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
    request_id: str = "req-red-c1-01",
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
    db_file = tmp_path / "b01_reconciliation_test.db"
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
    return {"client": client, "db_file": db_file, "secret": secret, "token": token}


def test_red_01_collection_contains_canonical_script_image_video(test_env):
    """RED 1: Admin collection contains canonical customer key: script_image_video."""
    client = test_env["client"]
    path = "/internal/v1/admin/products"
    headers = build_auth_headers("GET", path, b"")
    resp = client.get(path, headers=headers)
    assert resp.status_code == 200
    products = resp.json().get("products", [])
    product_keys = [p["product_key"] for p in products]
    assert "script_image_video" in product_keys, "Canonical customer key 'script_image_video' must be in admin products"


def test_red_02_collection_contains_canonical_video_idea(test_env):
    """RED 2: Admin collection contains canonical customer key: video_idea."""
    client = test_env["client"]
    path = "/internal/v1/admin/products"
    headers = build_auth_headers("GET", path, b"")
    resp = client.get(path, headers=headers)
    assert resp.status_code == 200
    products = resp.json().get("products", [])
    product_keys = [p["product_key"] for p in products]
    assert "video_idea" in product_keys, "Canonical customer key 'video_idea' must be in admin products"


def test_red_03_collection_does_not_expose_script_to_video_as_customer_product(test_env):
    """RED 3: Admin collection does NOT expose executor alias script_to_video as separate product."""
    client = test_env["client"]
    path = "/internal/v1/admin/products"
    headers = build_auth_headers("GET", path, b"")
    resp = client.get(path, headers=headers)
    assert resp.status_code == 200
    products = resp.json().get("products", [])
    product_keys = [p["product_key"] for p in products]
    assert "script_to_video" not in product_keys, "Executor alias 'script_to_video' must NOT be exposed as customer product"


def test_red_04_collection_does_not_expose_video_idea_to_product_as_customer_product(test_env):
    """RED 4: Admin collection does NOT expose executor alias video_idea_to_product as separate product."""
    client = test_env["client"]
    path = "/internal/v1/admin/products"
    headers = build_auth_headers("GET", path, b"")
    resp = client.get(path, headers=headers)
    assert resp.status_code == 200
    products = resp.json().get("products", [])
    product_keys = [p["product_key"] for p in products]
    assert "video_idea_to_product" not in product_keys, "Executor alias 'video_idea_to_product' must NOT be exposed as customer product"


def test_red_05_video_local_edit_execution_disabled_truth(test_env):
    """RED 5: Effective admin read model for video_local_edit has execution_enabled=False."""
    client = test_env["client"]
    path = "/internal/v1/admin/products/video_local_edit"
    headers = build_auth_headers("GET", path, b"")
    resp = client.get(path, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    effective = data.get("effective", {})
    assert effective.get("execution_enabled") is False, (
        f"video_local_edit must have execution_enabled=False per canonical lock, got {effective.get('execution_enabled')}"
    )


def test_red_06_product_video_supported_tiers_equals_canonical_contract(test_env):
    """RED 6: Product Video supported tiers equals canonical commercial_contract truth."""
    client = test_env["client"]
    path = "/internal/v1/admin/products/video_trend"
    headers = build_auth_headers("GET", path, b"")
    resp = client.get(path, headers=headers)
    assert resp.status_code == 200
    effective = resp.json().get("effective", {})
    
    canonical = video_tail9.commercial_contract("video_trend")
    canonical_tiers = list(canonical["supported_quality_tiers"])
    assert effective.get("supported_tiers") == canonical_tiers, (
        f"supported_tiers {effective.get('supported_tiers')} must equal canonical truth {canonical_tiers}"
    )


def test_red_07_product_video_supported_ratios_canonical_truth(test_env):
    """RED 7: Product Video supported ratios equals canonical product authority."""
    client = test_env["client"]
    path = "/internal/v1/admin/products/video_trend"
    headers = build_auth_headers("GET", path, b"")
    resp = client.get(path, headers=headers)
    assert resp.status_code == 200
    effective = resp.json().get("effective", {})
    
    # Canonical ratios per package_compatibility are ('9:16', '16:9', '1:1', '4:5')
    assert set(effective.get("supported_ratios", [])) == {"9:16", "16:9", "1:1", "4:5"}


def test_red_08_execution_enabled_dynamic_and_cannot_be_overridden(test_env):
    """RED 8: execution_enabled is dynamically derived from canonical authority and cannot be overridden."""
    client = test_env["client"]
    path = "/internal/v1/admin/products/video_local_edit"
    payload = {
        "expected_version": 1,
        "changes": {"commercial_enabled": True, "display_name": "Local Edit Activated"},
        "reason": "Attempting to enable deferred product",
    }
    body = json.dumps(payload).encode("utf-8")
    resp = client.patch(path, content=body, headers=build_auth_headers("PATCH", path, body))
    assert resp.status_code == 200
    res_data = resp.json()
    effective = res_data.get("effective_product", {})
    assert effective.get("commercial_enabled") is True
    assert effective.get("execution_enabled") is False, (
        "commercial_enabled=True MUST NEVER override execution_enabled=False for deferred products"
    )


def test_red_09_provider_capability_comes_from_canonical_contract(test_env):
    """RED 9: provider_capability comes from canonical engine contract, not hardcoded B01 string."""
    client = test_env["client"]
    path = "/internal/v1/admin/products/video_trend"
    headers = build_auth_headers("GET", path, b"")
    resp = client.get(path, headers=headers)
    assert resp.status_code == 200
    effective = resp.json().get("effective", {})
    
    engine_contract = video_project_queue.product_video_engine_contract("video_trend")
    expected_cap = engine_contract["required_capability"]
    assert effective.get("provider_capability") == expected_cap
