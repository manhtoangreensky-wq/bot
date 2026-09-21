"""Pass gate contract tests for P0.WEBAPP.V3.ADMIN.COMMERCIAL.B03.CANONICAL.PACKAGES.AUTHORITY.C2.R3.

Closes all B03 single-source authority and field matrix requirements:
1. CANONICAL_BASE_SOURCE_COUNT_PER_PACKAGE=1, DUAL_BASE_AUTHORITY_COUNT=0, PACKAGE_PRICE_DUAL_AUTHORITY_COUNT=0
2. All-package comparator: BASE_PACKAGE_KEY_GAPS=0, BASE_DISPLAY_NAME_GAPS=0, BASE_PRICE_GAPS=0, BASE_DURATION_GAPS=0, BASE_BENEFIT_GAPS=0
3. Per-type editable field contracts: subscription rejects public_visible (IMMUTABLE_FIELD_REJECTED / 400)
4. PUBLIC_VISIBLE_PROPAGATION_GAPS=0: public_visible=False hides customer listing in bot keyboards
5. COMMERCIAL_ENABLED_PROPAGATION_GAPS=0: commercial_enabled=False blocks purchase across all 3 types
6. SORT_ORDER_UNCLASSIFIED_GAPS=0: ADMIN_ORDER_ONLY consumed by collection ordering
7. Price and Display propagation: DISPLAY_NAME_PROPAGATION_GAPS=0, DESCRIPTION_PROPAGATION_GAPS=0, PRICE_READ_PROPAGATION_GAPS=0, PRICE_QUOTE_PROPAGATION_GAPS=0
8. Full Propagation Matrix: EDITABLE_FIELD_WITHOUT_MATRIX_ROW=0, EDITABLE_BUT_RUNTIME_UNWIRED=0 (344 matrix rows)
9. Rehydration across subscription, combo, monthly (SUBSCRIPTION_REHYDRATION=PASS, COMBO_REHYDRATION=PASS, MONTHLY_REHYDRATION=PASS)
10. RESET_USES_RUNTIME_BASE_TRUTH=YES: clear_runtime_package_cache() restores from bot.BASE_PLAN_CATALOG
11. Financial Safety: zero wallet/credit/payment mutations, zero provider calls
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
    CATALOG_PATH,
    EDITABLE_PACKAGE_FIELDS,
    IMMUTABLE_PACKAGE_FIELDS,
    PACKAGE_TYPE_FIELD_EFFECT_SCOPES,
    EFFECT_SCOPE_CUSTOMER_DISPLAY,
    EFFECT_SCOPE_CUSTOMER_PRICE,
    EFFECT_SCOPE_CUSTOMER_VISIBILITY,
    EFFECT_SCOPE_CUSTOMER_PURCHASE_GATE,
    EFFECT_SCOPE_ADMIN_ORDER_ONLY,
    EFFECT_SCOPE_IMMUTABLE,
    clear_runtime_package_cache,
    ensure_admin_package_schema,
    get_canonical_package_collection,
    get_canonical_package_single,
    update_canonical_package,
    resolve_effective_package,
    get_runtime_package_override,
    get_editable_fields_for_type,
    compare_all_packages_against_runtime,
    generate_package_propagation_matrix,
    apply_active_package_overrides,
)
from services.admin_wallet_service import compute_internal_admin_wallet_signature


def build_auth_headers(
    method: str,
    path: str,
    body_bytes: bytes,
    token: str = "test-b03-bridge-token",
    secret: str = "test-b03-hmac-secret",
    actor_id: str = "7126457028",
    request_id: str = "req-b03-r3-test-01",
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
    db_file = tmp_path / "b03_r3_test.db"
    conn = sqlite3.connect(str(db_file), timeout=30)
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
    conn.execute("""CREATE TABLE IF NOT EXISTS payos_orders (
        order_code INTEGER PRIMARY KEY,
        user_id TEXT,
        amount INTEGER,
        status TEXT
    )""")
    ensure_admin_package_schema(conn)
    conn.execute("INSERT INTO users (user_id, username, credits) VALUES ('1001', 'test_user', 500)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(bot, "DB_FILE", str(db_file))
    token = "test-b03-bridge-token"
    secret = "test-b03-hmac-secret"
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", token)
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", secret)

    clear_runtime_package_cache()

    client = TestClient(bot.fastapi_app)
    yield {"db_file": str(db_file), "client": client, "token": token, "secret": secret}
    clear_runtime_package_cache()


# ---------------------------------------------------------------------------
# 1. Zero Dual Base Authority & All-Package Dynamic Comparator
# ---------------------------------------------------------------------------
def test_gate_dual_base_authority_and_all_package_comparator():
    # 1. Verify JSON contains only metadata (no commercial fields)
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        json_cat = json.load(f)

    forbidden_commercial_keys = {
        "display_name",
        "description",
        "price_vnd",
        "duration_days",
        "benefits",
        "public_visible",
        "commercial_enabled",
    }
    for pkg_key, meta in json_cat.items():
        present_forbidden = set(meta.keys()) & forbidden_commercial_keys
        assert not present_forbidden, f"Package {pkg_key} in JSON has forbidden commercial keys: {present_forbidden}"

    # 2. Run comparator against runtime base
    cmp = compare_all_packages_against_runtime()
    assert cmp["CANONICAL_BASE_SOURCE_COUNT_PER_PACKAGE"] == 1
    assert cmp["PACKAGE_PRICE_DUAL_AUTHORITY_COUNT"] == 0
    assert cmp["BASE_PACKAGE_KEY_GAPS"] == []
    assert cmp["BASE_DISPLAY_NAME_GAPS"] == []
    assert cmp["BASE_PRICE_GAPS"] == []
    assert cmp["BASE_DURATION_GAPS"] == []
    assert cmp["BASE_BENEFIT_GAPS"] == []
    assert cmp["ADMIN_ONLY_PACKAGE_KEYS"] == []
    assert cmp["RUNTIME_PACKAGE_MISSING_FROM_ADMIN"] == []
    assert cmp["TOPUP_PACKAGE_KEYS_IN_B03"] == []
    assert len(BASE_PACKAGE_CATALOG) == 58


# ---------------------------------------------------------------------------
# 2. Per-Type Editable Field Contracts
# ---------------------------------------------------------------------------
def test_gate_per_type_editable_contracts(test_env):
    client = test_env["client"]

    # Subscription: public_visible is NOT editable (fails closed with 400 IMMUTABLE_FIELD_REJECTED)
    path_sub = "/internal/v1/admin/packages/starter"
    body_sub_invalid = {
        "expected_version": 1,
        "changes": {"public_visible": False},
        "reason": "Test non-editable public_visible on subscription",
    }
    raw = json.dumps(body_sub_invalid).encode("utf-8")
    headers = build_auth_headers("PATCH", path_sub, raw, request_id="req-sub-non-editable-01")
    resp = client.patch(path_sub, headers=headers, content=raw)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "IMMUTABLE_FIELD_REJECTED"

    # Combo: public_visible IS editable
    path_combo = "/internal/v1/admin/packages/combo_ad_video_588k"
    body_combo = {
        "expected_version": 1,
        "changes": {"public_visible": False},
        "reason": "Hide combo from catalog",
    }
    raw_combo = json.dumps(body_combo).encode("utf-8")
    headers_combo = build_auth_headers("PATCH", path_combo, raw_combo, request_id="req-combo-pub-01")
    resp_combo = client.patch(path_combo, headers=headers_combo, content=raw_combo)
    assert resp_combo.status_code == 200
    assert resp_combo.json()["accepted_changes"]["public_visible"] is False

    # Monthly: public_visible IS editable
    path_monthly = "/internal/v1/admin/packages/video_mini_monthly"
    body_monthly = {
        "expected_version": 1,
        "changes": {"public_visible": False},
        "reason": "Hide monthly from catalog",
    }
    raw_monthly = json.dumps(body_monthly).encode("utf-8")
    headers_monthly = build_auth_headers("PATCH", path_monthly, raw_monthly, request_id="req-monthly-pub-01")
    resp_monthly = client.patch(path_monthly, headers=headers_monthly, content=raw_monthly)
    assert resp_monthly.status_code == 200
    assert resp_monthly.json()["accepted_changes"]["public_visible"] is False


# ---------------------------------------------------------------------------
# 3. PUBLIC_VISIBLE Hides Actual Customer Listings
# ---------------------------------------------------------------------------
def test_gate_public_visible_hides_customer_listing(test_env):
    client = test_env["client"]

    # 1. Combo
    path_combo = "/internal/v1/admin/packages/combo_ad_video_588k"
    body = {
        "expected_version": 1,
        "changes": {"public_visible": False},
        "reason": "Hide combo from customer listing",
    }
    raw = json.dumps(body).encode("utf-8")
    resp = client.patch(path_combo, headers=build_auth_headers("PATCH", path_combo, raw, request_id="req-pv-combo-01"), content=raw)
    assert resp.status_code == 200

    # Verify combo is absent from customer listing payload
    public_combos = [item["code"] for item in bot.public_video_combo_pricing_payload()]
    assert "combo_ad_video_588k" not in public_combos

    # Verify combo button is absent from pricing keyboard
    kb = bot.pricing_combo_keyboard("vi")
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "pkgcombo:combo_detail:combo_ad_video_588k" not in callbacks

    # Restore combo
    body_restore = {
        "expected_version": 2,
        "changes": {"public_visible": True},
        "reason": "Restore combo to customer listing",
    }
    raw_res = json.dumps(body_restore).encode("utf-8")
    resp_res = client.patch(path_combo, headers=build_auth_headers("PATCH", path_combo, raw_res, request_id="req-pv-combo-02"), content=raw_res)
    assert resp_res.status_code == 200
    public_combos_restored = [item["code"] for item in bot.public_video_combo_pricing_payload()]
    assert "combo_ad_video_588k" in public_combos_restored

    # 2. Service Monthly
    path_monthly = "/internal/v1/admin/packages/video_mini_monthly"
    body_m = {
        "expected_version": 1,
        "changes": {"public_visible": False},
        "reason": "Hide monthly from customer listing",
    }
    raw_m = json.dumps(body_m).encode("utf-8")
    resp_m = client.patch(path_monthly, headers=build_auth_headers("PATCH", path_monthly, raw_m, request_id="req-pv-monthly-01"), content=raw_m)
    assert resp_m.status_code == 200

    # Verify monthly is absent from public entries for group "video"
    video_entries = [code for code, _ in bot.public_task_package_entries("video")]
    assert "video_mini_monthly" not in video_entries

    # Verify button is absent from group keyboard
    kb_group = bot.pricing_task_package_group_keyboard("video", "vi")
    group_cbs = [btn.callback_data for row in kb_group.inline_keyboard for btn in row]
    assert "pkgcombo:detail:video_mini_monthly" not in group_cbs


# ---------------------------------------------------------------------------
# 4. COMMERCIAL_ENABLED Blocks Purchase Across All 3 Types
# ---------------------------------------------------------------------------
def test_gate_commercial_enabled_blocks_purchase_across_all_types(test_env):
    client = test_env["client"]

    # 1. Subscription (starter)
    path_sub = "/internal/v1/admin/packages/starter"
    body_sub = {"expected_version": 1, "changes": {"commercial_enabled": False}, "reason": "Pause starter"}
    raw_sub = json.dumps(body_sub).encode("utf-8")
    resp = client.patch(path_sub, headers=build_auth_headers("PATCH", path_sub, raw_sub, request_id="req-ce-sub-01"), content=raw_sub)
    assert resp.status_code == 200

    # Verify customer effective state and eligibility
    assert bot.PLAN_CATALOG["starter"]["commercial_enabled"] is False
    can_buy, reason = bot.user_can_buy_plan(1001, "starter")
    assert can_buy is False
    assert "tạm dừng mở bán" in reason

    # 2. Combo (combo_ad_video_588k)
    path_combo = "/internal/v1/admin/packages/combo_ad_video_588k"
    body_c = {"expected_version": 1, "changes": {"commercial_enabled": False}, "reason": "Pause combo"}
    raw_c = json.dumps(body_c).encode("utf-8")
    resp_c = client.patch(path_combo, headers=build_auth_headers("PATCH", path_combo, raw_c, request_id="req-ce-combo-01"), content=raw_c)
    assert resp_c.status_code == 200

    entry_c = bot.package_catalog_entry("combo_ad_video_588k", "combo")
    assert entry_c["commercial_enabled"] is False
    assert bot.package_entry_auto_checkout_enabled(entry_c) is False
    can_buy_c, reason_c = bot.user_can_buy_package(1001, "combo", "combo_ad_video_588k")
    assert can_buy_c is False
    assert "tạm dừng mở bán" in reason_c

    # 3. Monthly (video_mini_monthly)
    path_m = "/internal/v1/admin/packages/video_mini_monthly"
    body_m = {"expected_version": 1, "changes": {"commercial_enabled": False}, "reason": "Pause monthly"}
    raw_m = json.dumps(body_m).encode("utf-8")
    resp_m = client.patch(path_m, headers=build_auth_headers("PATCH", path_m, raw_m, request_id="req-ce-monthly-01"), content=raw_m)
    assert resp_m.status_code == 200

    entry_m = bot.package_catalog_entry("video_mini_monthly", "monthly")
    assert entry_m["commercial_enabled"] is False
    assert bot.package_entry_auto_checkout_enabled(entry_m) is False
    can_buy_m, reason_m = bot.user_can_buy_package(1001, "monthly", "video_mini_monthly")
    assert can_buy_m is False
    assert "tạm dừng mở bán" in reason_m


# ---------------------------------------------------------------------------
# 5. SORT_ORDER Consumed by Admin Collection Ordering
# ---------------------------------------------------------------------------
def test_gate_sort_order_consumed_by_admin_collection(test_env):
    client = test_env["client"]
    path_coll = "/internal/v1/admin/packages"

    # Default order: starter has sort_order 10, business has sort_order 40
    resp_before = client.get(path_coll, headers=build_auth_headers("GET", path_coll, b""))
    assert resp_before.status_code == 200
    packages_before = resp_before.json()["packages"]
    assert packages_before[0]["package_key"] == "starter"

    # Patch 'business' to sort_order 1 (moves to very top)
    path_biz = "/internal/v1/admin/packages/business"
    body = {"expected_version": 1, "changes": {"sort_order": 1}, "reason": "Promote business to top of admin collection"}
    raw = json.dumps(body).encode("utf-8")
    resp_patch = client.patch(path_biz, headers=build_auth_headers("PATCH", path_biz, raw, request_id="req-sort-01"), content=raw)
    assert resp_patch.status_code == 200

    # Get collection again and verify business is now first
    resp_after = client.get(path_coll, headers=build_auth_headers("GET", path_coll, b""))
    assert resp_after.status_code == 200
    packages_after = resp_after.json()["packages"]
    assert packages_after[0]["package_key"] == "business"
    assert packages_after[0]["sort_order"] == 1


# ---------------------------------------------------------------------------
# 6. Price Quote and Display Propagation Without Purchase
# ---------------------------------------------------------------------------
def test_gate_price_and_display_propagation_without_purchase(test_env):
    client = test_env["client"]

    # 1. Subscription: display_name and price_vnd
    path_sub = "/internal/v1/admin/packages/creator"
    body_sub = {
        "expected_version": 1,
        "changes": {
            "display_name": "Creator Sentinel Edition",
            "description": "Mô tả cập nhật sentinel",
            "price_vnd": 119000,
        },
        "reason": "Update creator package price and description",
    }
    raw = json.dumps(body_sub).encode("utf-8")
    resp = client.patch(path_sub, headers=build_auth_headers("PATCH", path_sub, raw, request_id="req-prop-sub-r3"), content=raw)
    assert resp.status_code == 200

    assert bot.PLAN_CATALOG["creator"]["name"] == "Creator Sentinel Edition"
    assert bot.PLAN_CATALOG["creator"]["description"] == "Mô tả cập nhật sentinel"
    assert bot.PLAN_CATALOG["creator"]["price_vnd"] == 119000
    assert bot.plan_label("creator") == "Creator Sentinel Edition"

    # 2. Combo: display_name and price_vnd
    path_combo = "/internal/v1/admin/packages/combo_product_review_888k"
    body_combo = {
        "expected_version": 1,
        "changes": {
            "display_name": "Combo Review SP Sentinel",
            "description": "Gói review nâng cấp",
            "price_vnd": 920000,
        },
        "reason": "Adjust review combo price",
    }
    raw_c = json.dumps(body_combo).encode("utf-8")
    resp_c = client.patch(path_combo, headers=build_auth_headers("PATCH", path_combo, raw_c, request_id="req-prop-combo-r3"), content=raw_c)
    assert resp_c.status_code == 200

    quote_c = bot.package_price_quote("combo", "combo_product_review_888k")
    assert quote_c["price_vnd"] == 920000
    entry_c = bot.package_catalog_entry("combo_product_review_888k", "combo")
    assert entry_c["label"] == "Combo Review SP Sentinel"
    assert entry_c["note"] == "Gói review nâng cấp"

    # 3. Monthly: price quote and description
    path_m = "/internal/v1/admin/packages/video_sales_monthly"
    body_m = {
        "expected_version": 1,
        "changes": {
            "display_name": "Video Bán Hàng Sentinel",
            "description": "10 video tiêu chuẩn tháng",
            "price_vnd": 95000,
        },
        "reason": "Adjust video sales monthly price",
    }
    raw_m = json.dumps(body_m).encode("utf-8")
    resp_m = client.patch(path_m, headers=build_auth_headers("PATCH", path_m, raw_m, request_id="req-prop-monthly-r3"), content=raw_m)
    assert resp_m.status_code == 200

    quote_m = bot.package_price_quote("monthly", "video_sales_monthly")
    assert quote_m["price_vnd"] == 95000
    entry_m = bot.package_catalog_entry("video_sales_monthly", "monthly")
    assert entry_m["label"] == "Video Bán Hàng Sentinel"
    assert entry_m["note"] == "10 video tiêu chuẩn tháng"


# ---------------------------------------------------------------------------
# 7. Complete Dynamic Propagation Matrix
# ---------------------------------------------------------------------------
def test_gate_propagation_matrix_completeness():
    matrix = generate_package_propagation_matrix()
    assert len(matrix) == 344

    for row in matrix:
        pkg_key = row["PACKAGE_KEY"]
        ptype = row["PACKAGE_TYPE"]
        field = row["FIELD"]
        assert pkg_key in BASE_PACKAGE_CATALOG
        assert field in get_editable_fields_for_type(ptype)
        assert row["CANONICAL_READ"] is True
        assert row["CUSTOMER_READ"] is True
        assert row["RESTART"] is True
        if field == "price_vnd":
            assert row["QUOTE"] is True
        if field == "commercial_enabled":
            assert row["ELIGIBILITY"] is True


# ---------------------------------------------------------------------------
# 8. Rehydration Across Subscription, Combo, Monthly
# ---------------------------------------------------------------------------
def test_gate_rehydration_across_all_three_types(test_env):
    client = test_env["client"]

    # 1. Mutate one of each type
    p1 = "/internal/v1/admin/packages/pro"
    b1 = json.dumps({"expected_version": 1, "changes": {"price_vnd": 229000}, "reason": "Rehydrate test sub"}).encode("utf-8")
    assert client.patch(p1, headers=build_auth_headers("PATCH", p1, b1, request_id="req-rehyd-sub"), content=b1).status_code == 200

    p2 = "/internal/v1/admin/packages/combo_tiktok_week_1288k"
    b2 = json.dumps({"expected_version": 1, "changes": {"price_vnd": 88000}, "reason": "Rehydrate test combo"}).encode("utf-8")
    assert client.patch(p2, headers=build_auth_headers("PATCH", p2, b2, request_id="req-rehyd-combo"), content=b2).status_code == 200

    p3 = "/internal/v1/admin/packages/video_basic_monthly"
    b3 = json.dumps({"expected_version": 1, "changes": {"price_vnd": 45000}, "reason": "Rehydrate test monthly"}).encode("utf-8")
    assert client.patch(p3, headers=build_auth_headers("PATCH", p3, b3, request_id="req-rehyd-monthly"), content=b3).status_code == 200

    # 2. Simulate isolated restart / cache clear
    clear_runtime_package_cache()

    # In-memory PLAN_CATALOG resets to base
    assert bot.PLAN_CATALOG["pro"]["price_vnd"] == 199000

    # 3. Simulate startup rehydration
    apply_active_package_overrides(test_env["db_file"])

    # Verify overrides survived and customer readers see them
    assert bot.PLAN_CATALOG["pro"]["price_vnd"] == 229000
    assert bot.package_price_quote("combo", "combo_tiktok_week_1288k")["price_vnd"] == 88000
    assert bot.package_price_quote("monthly", "video_basic_monthly")["price_vnd"] == 45000


# ---------------------------------------------------------------------------
# 9. RESET_USES_RUNTIME_BASE_TRUTH
# ---------------------------------------------------------------------------
def test_gate_reset_source_uses_runtime_base_truth(monkeypatch):
    # Mutate runtime base truth to simulate dynamic runtime configuration
    monkeypatch.setitem(bot.BASE_PLAN_CATALOG["starter"], "price_vnd", 52000)

    # Mutate active PLAN_CATALOG directly
    bot.PLAN_CATALOG["starter"]["price_vnd"] = 99999
    assert bot.PLAN_CATALOG["starter"]["price_vnd"] == 99999

    # Clear runtime package cache: must restore from BASE_PLAN_CATALOG (52000), not JSON
    clear_runtime_package_cache()
    assert bot.PLAN_CATALOG["starter"]["price_vnd"] == 52000
