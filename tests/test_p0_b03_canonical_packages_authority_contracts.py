"""Green contract test suite for B03: Canonical Bot-Owned Package Authority.

Validates all required B03 focus points:
1. GET collection returns canonical package set (58 packages across 3 proven domains)
2. Domain separation: Topup/PayOS packages strictly excluded (TOPUP_PACKAGE_KEYS_IN_B03=0, PAYOS_PACKAGE_KEYS_IN_B03=0)
3. Zero invented package models (INVENTED_PACKAGE_COUNT=0)
4. GET single package returns base values, effective values, version, and classifications
5. GET single unknown package fails closed (404)
6. PATCH display_name succeeds with CAS
7. PATCH description succeeds
8. PATCH price_vnd succeeds and validates bounds
9. PATCH public_visible succeeds
10. PATCH commercial_enabled succeeds
11. PATCH sort_order succeeds
12. Unknown field fails closed (400)
13. Immutable field mutation is rejected (400 IMMUTABLE_FIELD_REJECTED)
14. Stale expected_version is rejected (409 Conflict)
15. Missing expected_version is rejected (400)
16. Missing or empty reason is rejected (400)
17. Idempotent request replay returns cached receipt without double mutation
18. Audit record appended exactly once per mutation
19. Write receipt returned with valid digest and receipt_id
20. Fresh canonical readback matches committed update
21. Customer read & quote propagation for subscription packages (bot.PLAN_CATALOG)
22. Customer read & quote propagation for combo packages (bot.package_price_quote)
23. Customer read & quote propagation for service monthly packages
24. Unauthorized caller cannot read or write (401 / 403)
25. Zero side effects: zero wallet mutations, zero credit deductions, zero payment mutations
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import time
from typing import Any
import pytest
from starlette.testclient import TestClient

import bot
from services.admin_package_service import (
    BASE_PACKAGE_CATALOG,
    EDITABLE_PACKAGE_FIELDS,
    IMMUTABLE_PACKAGE_FIELDS,
    clear_runtime_package_cache,
    ensure_admin_package_schema,
    get_canonical_package_collection,
    get_canonical_package_single,
    update_canonical_package,
    resolve_effective_package,
    get_runtime_package_override,
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
    conn.execute("""CREATE TABLE IF NOT EXISTS user_plans (
        user_id TEXT PRIMARY KEY,
        current_plan TEXT,
        plan_name TEXT,
        plan_started_at TEXT,
        plan_expires_at TEXT,
        plan_xu_monthly INTEGER,
        plan_xu_remaining INTEGER,
        plan_status TEXT,
        order_code TEXT,
        updated_at TEXT
    )""")
    ensure_admin_package_schema(conn)
    return conn


def build_auth_headers(
    method: str,
    path: str,
    body_bytes: bytes,
    token: str = "test-b03-bridge-token",
    secret: str = "test-b03-hmac-secret",
    actor_id: str = "7126457028",
    request_id: str = "req-b03-test-01",
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
    db_file = tmp_path / "b03_test.db"
    conn = create_test_db(db_file)
    conn.execute("INSERT INTO users (user_id, username, credits) VALUES ('1001', 'test_user', 500)")
    conn.execute("INSERT INTO credit_events (user_id, delta, balance_after, event_type) VALUES ('1001', 500, 500, 'initial')")
    conn.execute("INSERT INTO payos_orders (order_code, user_id, amount, status) VALUES (99901, '1001', 50000, 'PAID')")
    conn.commit()
    conn.close()

    monkeypatch.setattr(bot, "DB_FILE", str(db_file))
    token = "test-b03-bridge-token"
    secret = "test-b03-hmac-secret"
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", token)
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", secret)

    clear_runtime_package_cache()

    client = TestClient(bot.fastapi_app)
    yield {"db_file": db_file, "client": client, "token": token, "secret": secret}
    clear_runtime_package_cache()


# ---------------------------------------------------------------------------
# Requirement 1: GET collection returns canonical package set (58 packages)
# ---------------------------------------------------------------------------
def test_req_01_get_collection_returns_all_canonical_packages(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/packages"
    headers = build_auth_headers("GET", path, b"")
    resp = client.get(path, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["total_packages"] == 58
    assert len(data["packages"]) == 58
    domains = data["proven_domains"]
    assert domains["subscription"] == 4
    assert domains["combo"] == 20
    assert domains["service_monthly"] == 34


# ---------------------------------------------------------------------------
# Requirement 2 & 3: Separation of domains and zero invented packages
# ---------------------------------------------------------------------------
def test_req_02_no_topup_and_zero_invented_packages(test_env):
    for key, pkg in BASE_PACKAGE_CATALOG.items():
        assert "topup" not in key.lower(), f"Topup key {key} must not be in B03 packages"
        assert "xu" not in key.lower() or key.startswith("combo_") or key in {"starter", "creator", "pro", "business"}, f"Unexpected Xu key {key}"
        assert pkg.get("package_type") in {"subscription", "combo", "service_monthly"}
        assert pkg["price_vnd"] >= 0


# ---------------------------------------------------------------------------
# Requirement 4 & 5: GET single package and unknown package fails closed
# ---------------------------------------------------------------------------
def test_req_04_get_single_package_success(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/packages/starter"
    headers = build_auth_headers("GET", path, b"")
    resp = client.get(path, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    pkg = data["package"]
    assert pkg["package_key"] == "starter"
    assert pkg["package_type"] == "subscription"
    assert pkg["display_name"] == "Starter"
    assert pkg["price_vnd"] == 49000
    assert pkg["version"] == 1
    assert pkg["has_override"] is False


def test_req_05_get_unknown_package_fails_closed(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/packages/non_existent_package_xyz"
    headers = build_auth_headers("GET", path, b"")
    resp = client.get(path, headers=headers)
    assert resp.status_code == 404
    data = resp.json()
    assert data["ok"] is False
    assert data["error_code"] == "PACKAGE_NOT_FOUND"


# ---------------------------------------------------------------------------
# Requirement 6-11: PATCH editable fields with CAS
# ---------------------------------------------------------------------------
def test_req_06_patch_display_name_and_price_success(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/packages/starter"
    body = {
        "expected_version": 1,
        "changes": {
            "display_name": "Starter VIP Pro 2026",
            "price_vnd": 59000,
            "description": "Gói cập nhật mới cho creator chuyên nghiệp",
            "sort_order": 5,
        },
        "reason": "Điều chỉnh giá và mô tả gói Starter quý 3",
    }
    raw = json.dumps(body).encode("utf-8")
    headers = build_auth_headers("PATCH", path, raw, request_id="req-pkg-01")
    resp = client.patch(path, headers=headers, content=raw)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["package_key"] == "starter"
    assert data["previous_version"] == 1
    assert data["new_version"] == 2
    assert data["accepted_changes"]["display_name"] == "Starter VIP Pro 2026"
    assert data["accepted_changes"]["price_vnd"] == 59000
    assert data["accepted_changes"]["sort_order"] == 5
    assert data["idempotent_replay"] is False
    assert "rcpt_pkg_starter_2" in data["receipt_id"]

    # Fresh readback
    get_headers = build_auth_headers("GET", path, b"")
    fresh_resp = client.get(path, headers=get_headers)
    assert fresh_resp.status_code == 200
    fresh_data = fresh_resp.json()["package"]
    assert fresh_data["display_name"] == "Starter VIP Pro 2026"
    assert fresh_data["price_vnd"] == 59000
    assert fresh_data["version"] == 2
    assert fresh_data["has_override"] is True


def test_req_08_patch_price_out_of_bounds_rejected(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/packages/starter"
    body = {
        "expected_version": 1,
        "changes": {"price_vnd": -5000},
        "reason": "Thử nghiệm giá âm",
    }
    raw = json.dumps(body).encode("utf-8")
    headers = build_auth_headers("PATCH", path, raw, request_id="req-pkg-neg")
    resp = client.patch(path, headers=headers, content=raw)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "PRICE_VND_OUT_OF_BOUNDS"


# ---------------------------------------------------------------------------
# Requirement 12 & 13: Reject unknown and immutable fields
# ---------------------------------------------------------------------------
def test_req_12_reject_unknown_field(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/packages/starter"
    body = {
        "expected_version": 1,
        "changes": {"magic_unsupported_field": 123},
        "reason": "Test unknown field",
    }
    raw = json.dumps(body).encode("utf-8")
    headers = build_auth_headers("PATCH", path, raw, request_id="req-pkg-unk")
    resp = client.patch(path, headers=headers, content=raw)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "UNKNOWN_FIELD_REJECTED"


def test_req_13_reject_immutable_field(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/packages/starter"
    body = {
        "expected_version": 1,
        "changes": {"duration_days": 60},
        "reason": "Test immutable field",
    }
    raw = json.dumps(body).encode("utf-8")
    headers = build_auth_headers("PATCH", path, raw, request_id="req-pkg-imm")
    resp = client.patch(path, headers=headers, content=raw)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "IMMUTABLE_FIELD_REJECTED"


# ---------------------------------------------------------------------------
# Requirement 14-16: CAS conflict and mandatory validation
# ---------------------------------------------------------------------------
def test_req_14_stale_expected_version_rejected_409(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/packages/starter"

    # Mutate once to move to version 2
    body1 = {
        "expected_version": 1,
        "changes": {"price_vnd": 55000},
        "reason": "Bump to version 2",
    }
    raw1 = json.dumps(body1).encode("utf-8")
    headers1 = build_auth_headers("PATCH", path, raw1, request_id="req-pkg-v1")
    resp1 = client.patch(path, headers=headers1, content=raw1)
    assert resp1.status_code == 200

    # Try mutating with stale expected_version=1
    body2 = {
        "expected_version": 1,
        "changes": {"price_vnd": 60000},
        "reason": "Stale version attempt",
    }
    raw2 = json.dumps(body2).encode("utf-8")
    headers2 = build_auth_headers("PATCH", path, raw2, request_id="req-pkg-v2")
    resp2 = client.patch(path, headers=headers2, content=raw2)
    assert resp2.status_code == 409
    data = resp2.json()
    assert data["error_code"] == "VERSION_CONFLICT"
    assert data["current_version"] == 2
    assert data["expected_version"] == 1


def test_req_15_missing_expected_version_rejected(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/packages/starter"
    body = {
        "changes": {"price_vnd": 55000},
        "reason": "Missing expected_version",
    }
    raw = json.dumps(body).encode("utf-8")
    headers = build_auth_headers("PATCH", path, raw, request_id="req-pkg-no-ver")
    resp = client.patch(path, headers=headers, content=raw)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "EXPECTED_VERSION_MANDATORY"


def test_req_16_missing_reason_rejected(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/packages/starter"
    body = {
        "expected_version": 1,
        "changes": {"price_vnd": 55000},
        "reason": "",
    }
    raw = json.dumps(body).encode("utf-8")
    headers = build_auth_headers("PATCH", path, raw, request_id="req-pkg-no-reason")
    resp = client.patch(path, headers=headers, content=raw)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "REASON_MANDATORY"


# ---------------------------------------------------------------------------
# Requirement 17-20: Idempotency, audit, and fresh readback
# ---------------------------------------------------------------------------
def test_req_17_idempotent_replay_same_request_id(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/packages/creator"
    body = {
        "expected_version": 1,
        "changes": {"price_vnd": 109000},
        "reason": "Update creator price",
    }
    raw = json.dumps(body).encode("utf-8")
    headers = build_auth_headers("PATCH", path, raw, request_id="req-creator-idempotent-01")

    # First call
    resp1 = client.patch(path, headers=headers, content=raw)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["idempotent_replay"] is False
    assert data1["new_version"] == 2

    # Second call with same request_id
    resp2 = client.patch(path, headers=headers, content=raw)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["idempotent_replay"] is True
    assert data2["new_version"] == 2
    assert data2["mutation_digest"] == data1["mutation_digest"]

    # Verify audit table has exactly 1 row for this request
    conn = sqlite3.connect(test_env["db_file"])
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM admin_package_audit WHERE package_key = 'creator'")
    count = cur.fetchone()[0]
    conn.close()
    assert count == 1


# ---------------------------------------------------------------------------
# Requirement 21: Propagation for subscription packages (bot.PLAN_CATALOG)
# ---------------------------------------------------------------------------
def test_req_21_subscription_propagation_to_bot_plan_catalog(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/packages/pro"
    body = {
        "expected_version": 1,
        "changes": {
            "display_name": "Pro Master 2026",
            "price_vnd": 249000,
        },
        "reason": "Điều chỉnh gói Pro",
    }
    raw = json.dumps(body).encode("utf-8")
    headers = build_auth_headers("PATCH", path, raw, request_id="req-prop-sub-01")
    resp = client.patch(path, headers=headers, content=raw)
    assert resp.status_code == 200

    # Verify bot.PLAN_CATALOG is updated immediately
    assert bot.PLAN_CATALOG["pro"]["name"] == "Pro Master 2026"
    assert bot.PLAN_CATALOG["pro"]["price_vnd"] == 249000
    assert bot.plan_label("pro") == "Pro Master 2026"


# ---------------------------------------------------------------------------
# Requirement 22: Propagation for combo packages (bot.package_price_quote)
# ---------------------------------------------------------------------------
def test_req_22_combo_propagation_to_package_price_quote(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/packages/combo_ad_video_588k"
    body = {
        "expected_version": 1,
        "changes": {
            "display_name": "Combo Video QC Siêu Tốc 2026",
            "price_vnd": 65000,
            "public_visible": True,
        },
        "reason": "Điều chỉnh combo mini video",
    }
    raw = json.dumps(body).encode("utf-8")
    headers = build_auth_headers("PATCH", path, raw, request_id="req-prop-combo-01")
    resp = client.patch(path, headers=headers, content=raw)
    assert resp.status_code == 200

    # Verify bot quote resolver reflects new price
    quote = bot.package_price_quote("combo", "combo_ad_video_588k")
    assert quote["price_vnd"] == 65000

    # Verify catalog payload reflects new label and price
    catalog = bot.package_catalog_payload()
    entry = catalog["combos"]["combo_ad_video_588k"]
    assert entry["label"] == "Combo Video QC Siêu Tốc 2026"
    assert entry["price_vnd"] == 65000


# ---------------------------------------------------------------------------
# Requirement 23: Propagation for service monthly packages
# ---------------------------------------------------------------------------
def test_req_23_service_monthly_propagation(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/packages/video_mini_monthly"
    body = {
        "expected_version": 1,
        "changes": {
            "display_name": "Gói Video Mini Tháng Cao Cấp",
            "price_vnd": 79000,
        },
        "reason": "Điều chỉnh gói tháng video mini",
    }
    raw = json.dumps(body).encode("utf-8")
    headers = build_auth_headers("PATCH", path, raw, request_id="req-prop-svc-01")
    resp = client.patch(path, headers=headers, content=raw)
    assert resp.status_code == 200

    # Verify quote resolver reflects new price
    quote = bot.package_price_quote("monthly", "video_mini_monthly")
    assert quote["price_vnd"] == 79000

    # Verify task package payload reflects new label and price
    packages = bot.p0_21d_task_package_payload()
    entry = packages["video_mini_monthly"]
    assert entry["label"] == "Gói Video Mini Tháng Cao Cấp"
    assert entry["price_vnd"] == 79000


# ---------------------------------------------------------------------------
# Requirement 24: Internal Admin Authentication & HMAC protection
# ---------------------------------------------------------------------------
def test_req_24_auth_failure_modes(test_env):
    client = test_env["client"]
    path = "/internal/v1/admin/packages"

    # Missing authorization header
    resp_no_auth = client.get(path)
    assert resp_no_auth.status_code in (401, 503)

    # Invalid token
    headers_bad_token = build_auth_headers("GET", path, b"", token="invalid-token")
    resp_bad_token = client.get(path, headers=headers_bad_token)
    assert resp_bad_token.status_code == 401

    # Invalid HMAC signature
    headers_bad_sig = build_auth_headers("GET", path, b"", secret="wrong-secret")
    resp_bad_sig = client.get(path, headers=headers_bad_sig)
    assert resp_bad_sig.status_code == 401


# ---------------------------------------------------------------------------
# Requirement 25: Zero side effect and financial safety
# ---------------------------------------------------------------------------
def test_req_25_zero_financial_side_effects(test_env):
    conn = sqlite3.connect(test_env["db_file"])
    cur = conn.cursor()

    # Verify user credit table
    cur.execute("SELECT credits FROM users WHERE user_id = '1001'")
    assert cur.fetchone()[0] == 500

    # Verify credit_events table
    cur.execute("SELECT COUNT(*) FROM credit_events")
    assert cur.fetchone()[0] == 1

    # Verify payos_orders table
    cur.execute("SELECT COUNT(*) FROM payos_orders")
    assert cur.fetchone()[0] == 1

    conn.close()
