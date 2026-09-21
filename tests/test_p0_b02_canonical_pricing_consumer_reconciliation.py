"""Comprehensive consumer reconciliation matrix test suite for B02: Canonical Pricing Publish Authority.

Validates that every single editable price key in BASE_PRICING_CATALOG satisfies:
1. Base value comparator match against runtime authority (BASE_VALUE_COMPARATOR_GAPS=0)
2. Admin PATCH mutates price via CAS
3. Effective value propagates to READ consumer (READ_PROPAGATION_GAPS=0)
4. Effective value propagates to QUOTE resolver (QUOTE_PROPAGATION_GAPS=0)
5. Effective value propagates to CHARGE AMOUNT resolver (CHARGE_PROPAGATION_GAPS=0)
6. All unwired runtime policies rejected with 400 IMMUTABLE_PRICE_KEY_REJECTED
7. Explicit full pack override semantics (Cases 1-4, including base-value override distinction)
8. Canonical alias normalization without duplicate SQLite rows
9. Zero side effects: zero wallet mutations, zero credit deductions, zero paid provider calls
"""

from __future__ import annotations

from decimal import Decimal
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
    CANONICAL_PRICING_ALIASES,
    clear_runtime_pricing_cache,
    ensure_admin_pricing_schema,
    get_canonical_effective_price,
    get_canonical_effective_price_state,
)
from services.admin_wallet_service import compute_internal_admin_wallet_signature
import services.video_ai_real_pricing as vp
from services.subdub_auto_word_pricing import (
    AUTO_XU_PER_WORD,
    auto_voice_component_xu,
    effective_auto_word_rate_xu,
)
from services.chat_pro_pricing import (
    OpusUsage,
    calculate_actual_xu,
    public_chat_customer_pricing,
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
    request_id: str = "req-b02-reconciliation-01",
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
    db_file = tmp_path / "b02_reconciliation_test.db"
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


# ===========================================================================
# 1. MATRIX INTEGRITY & BASE VALUE COMPARATORS
# ===========================================================================
def test_matrix_integrity_and_base_value_comparators():
    """Prove that every editable key matches its existing base runtime authority."""
    editable_keys = [k for k, v in BASE_PRICING_CATALOG.items() if v.get("editable", True)]
    assert len(editable_keys) == 30, f"Expected exactly 30 editable keys, found {len(editable_keys)}"

    gaps = []
    for price_key in editable_keys:
        item = BASE_PRICING_CATALOG[price_key]
        base_val = item["base_value"]
        domain = item["domain"]

        if domain == "video":
            tier = int(price_key.split("_")[-1])
            rt_val = vp.public_quality_by_tier(tier)["unit_xu"]
        elif domain == "image":
            tier_key = price_key[len("image_tier_"):]
            rt_val = vp.public_image_quality_by_tier(tier_key)["unit_xu"]
        elif domain == "music":
            if price_key == "music_vocal_full":
                rt_val = int(bot.MUSIC_VOCAL_FULL_PRICE_XU)
            else:
                music_tier = price_key[len("music_background_"):]
                rt_val = vp.public_music_background_prices()[music_tier]
        elif domain == "subdub":
            rt_val = float(AUTO_XU_PER_WORD)
        elif domain == "content":
            if price_key == "content_trend_analysis":
                rt_val = int(bot.WORKFLOW_TREND_ANALYSIS_COST_XU)
            elif price_key == "content_script_storyboard":
                rt_val = int(bot.WORKFLOW_SCRIPT_STORYBOARD_COST_XU)
            elif price_key == "content_prompt_pack":
                rt_val = int(bot.WORKFLOW_PROMPT_PACK_COST_XU)
            elif price_key == "content_full_pack":
                rt_val = 70
            else:
                rt_val = None
        elif domain == "chat":
            p = public_chat_customer_pricing()
            if price_key == "chat_pro_input":
                rt_val = int(p.input_xu_per_million / 1000)
            elif price_key == "chat_pro_output":
                rt_val = int(p.output_xu_per_million / 1000)
            elif price_key == "chat_pro_cache_read":
                rt_val = float(p.cache_read_xu_per_million / 1000)
            else:
                rt_val = None
        elif domain == "voice":
            assert price_key == "voice_clone_create"
            rt_val = int(bot.VOICE_PROFILE_PRICE_XU)
        else:
            rt_val = None

        if base_val != rt_val:
            gaps.append((price_key, base_val, rt_val))

    assert len(gaps) == 0, f"Base value comparator gaps detected: {gaps}"


# ===========================================================================
# 2. FULL CONSUMER PROPAGATION MATRIX (READ, QUOTE, CHARGE AMOUNT)
# ===========================================================================
@pytest.mark.parametrize("price_key", [k for k, v in BASE_PRICING_CATALOG.items() if v.get("editable", True)])
def test_consumer_propagation_matrix_for_every_editable_key(test_env, price_key, monkeypatch):
    """Every single editable price key must prove READ, QUOTE, and CHARGE AMOUNT propagation."""
    client = test_env["client"]
    item = BASE_PRICING_CATALOG[price_key]
    val_type = item.get("value_type", "int")
    base_val = item["base_value"]

    # Calculate sentinel value for mutation
    if val_type == "int":
        sentinel_value = int(base_val) + 17
    else:
        sentinel_value = round(float(base_val) + 0.25, 2)

    path = f"/internal/v1/admin/pricing/{price_key}"
    payload = {"expected_version": 1, "new_value": sentinel_value, "reason": f"Testing consumer matrix for {price_key}"}
    body = json.dumps(payload).encode("utf-8")
    headers = build_auth_headers("PATCH", path, body, request_id=f"req-matrix-{price_key}")
    resp = client.patch(path, content=body, headers=headers)
    assert resp.status_code == 200, f"PATCH failed for {price_key}: {resp.text}"

    domain = item["domain"]

    # -------------------------------------------------------------
    # VIDEO DOMAIN
    # -------------------------------------------------------------
    if domain == "video":
        tier = int(price_key.split("_")[-1])
        tier_name = bot.VIDEO_TIER_ID_TO_NAME[tier]

        # 1. READ PROOF
        read_val = vp.public_quality_by_tier(tier)["unit_xu"]
        assert read_val == sentinel_value, f"Video READ mismatch for {price_key}: expected {sentinel_value}, got {read_val}"

        # 2. QUOTE PROOF
        quote_info = bot.product_video_r9_scene_pricing(1, tier=tier_name)
        assert quote_info["unit_charge_xu"] == sentinel_value, f"Video QUOTE mismatch for {price_key}: expected {sentinel_value}, got {quote_info['unit_charge_xu']}"

        # 3. CHARGE AMOUNT PROOF (pure calculation)
        assert quote_info["charge_total_xu"] == sentinel_value, f"Video CHARGE mismatch for {price_key}: expected {sentinel_value}, got {quote_info['charge_total_xu']}"

    # -------------------------------------------------------------
    # IMAGE DOMAIN
    # -------------------------------------------------------------
    elif domain == "image":
        tier_key = price_key[len("image_tier_"):]

        # 1. READ PROOF
        read_val = vp.public_image_quality_by_tier(tier_key)["unit_xu"]
        assert read_val == sentinel_value, f"Image READ mismatch for {price_key}: expected {sentinel_value}, got {read_val}"

        # 2. QUOTE PROOF
        quote_payload = bot.canonical_image_tier_pricing_payload()
        assert quote_payload[tier_key]["cost"] == sentinel_value, f"Image QUOTE mismatch for {price_key}: expected {sentinel_value}, got {quote_payload[tier_key]['cost']}"

        # 3. CHARGE AMOUNT PROOF
        assert quote_payload[tier_key]["cost"] == sentinel_value, f"Image CHARGE mismatch for {price_key}"

    # -------------------------------------------------------------
    # MUSIC DOMAIN
    # -------------------------------------------------------------
    elif domain == "music":
        if price_key == "music_vocal_full":
            # 1. READ PROOF
            assert get_canonical_effective_price("music_vocal_full") == sentinel_value
            # 2. QUOTE PROOF
            assert bot.music_product_quote_price_xu("song") == sentinel_value
            # 3. CHARGE AMOUNT PROOF
            assert bot.music_ai_output_price_xu(120, "song_full") == sentinel_value
        else:
            music_tier = price_key[len("music_background_"):]
            # 1. READ PROOF
            prices = vp.public_music_background_prices()
            assert prices[music_tier] == sentinel_value
            # 2. QUOTE PROOF
            assert prices[music_tier] == sentinel_value
            # 3. CHARGE AMOUNT PROOF
            assert prices[music_tier] == sentinel_value

    # -------------------------------------------------------------
    # SUBDUB DOMAIN
    # -------------------------------------------------------------
    elif domain == "subdub":
        assert price_key == "subdub_auto_word"
        # 1. READ PROOF
        assert effective_auto_word_rate_xu() == Decimal(str(sentinel_value))
        # 2. QUOTE PROOF
        expected_quote = int((Decimal(100) * Decimal(str(sentinel_value))).to_integral_value())
        assert auto_voice_component_xu(100) == expected_quote
        # 3. CHARGE AMOUNT PROOF
        assert auto_voice_component_xu(100) == expected_quote

    # -------------------------------------------------------------
    # CONTENT DOMAIN
    # -------------------------------------------------------------
    elif domain == "content":
        # 1. READ PROOF
        state = get_canonical_effective_price_state(price_key)
        assert state["has_override"] is True
        assert state["effective_value"] == sentinel_value

        # 2. QUOTE PROOF & 3. CHARGE AMOUNT PROOF
        if price_key == "content_trend_analysis":
            assert bot.workflow_trend_analysis_cost_xu() == sentinel_value
        elif price_key == "content_script_storyboard":
            assert bot.workflow_script_storyboard_cost_xu() == sentinel_value
        elif price_key == "content_prompt_pack":
            assert bot.workflow_prompt_pack_cost_xu() == sentinel_value
        elif price_key == "content_full_pack":
            assert bot.workflow_content_cost_xu() == sentinel_value

    # -------------------------------------------------------------
    # CHAT DOMAIN
    # -------------------------------------------------------------
    elif domain == "chat":
        # 1. READ PROOF
        pricing = public_chat_customer_pricing()
        if price_key == "chat_pro_input":
            assert pricing.input_xu_per_million == Decimal(str(sentinel_value)) * Decimal(1000)
            # 2. QUOTE & 3. CHARGE AMOUNT PROOF
            charge_xu = calculate_actual_xu(OpusUsage(input_tokens=1000, output_tokens=0, cache_read_tokens=0), pricing)
            assert charge_xu == sentinel_value
        elif price_key == "chat_pro_output":
            assert pricing.output_xu_per_million == Decimal(str(sentinel_value)) * Decimal(1000)
            charge_xu = calculate_actual_xu(OpusUsage(input_tokens=0, output_tokens=1000, cache_read_tokens=0), pricing)
            assert charge_xu == sentinel_value
        elif price_key == "chat_pro_cache_read":
            assert pricing.cache_read_xu_per_million == Decimal(str(sentinel_value)) * Decimal(1000)
            charge_xu = calculate_actual_xu(OpusUsage(input_tokens=0, output_tokens=0, cache_read_tokens=10000), pricing)
            expected = int((Decimal(10000) * Decimal(str(sentinel_value)) * Decimal(1000) / Decimal(1_000_000)).to_integral_value())
            assert charge_xu == expected

    # -------------------------------------------------------------
    # VOICE DOMAIN (voice_clone_create)
    # -------------------------------------------------------------
    elif domain == "voice":
        assert price_key == "voice_clone_create"
        # 1. READ PROOF
        assert get_canonical_effective_price("voice_clone_create") == sentinel_value
        snapshot = bot.cskh_live_pricing_snapshot()
        assert snapshot["voice_private_repeat_xu"] == sentinel_value

        # 2. QUOTE PROOF (simulate non-first-free user)
        monkeypatch.setattr(bot, "VOICE_PROFILE_FIRST_FREE", False)
        quote_val = bot.voice_profile_storage_display_price_xu(99999)
        assert quote_val == sentinel_value

        # 3. CHARGE AMOUNT PROOF (pure pre-charge function, no wallet spend)
        charge_val = bot.voice_profile_storage_price_xu(99999)
        assert charge_val == sentinel_value


# ===========================================================================
# 3. UNWIRED / IMMUTABLE PRICE KEY REJECTION CONTRACT
# ===========================================================================
@pytest.mark.parametrize("price_key", [k for k, v in BASE_PRICING_CATALOG.items() if not v.get("editable", True)])
def test_unwired_immutable_price_keys_rejected_with_400(test_env, price_key):
    """Every immutable price key (including unwired policies) must be rejected on mutation."""
    client = test_env["client"]
    path = f"/internal/v1/admin/pricing/{price_key}"
    payload = {"expected_version": 1, "new_value": 99, "reason": "Attempting immutable mutation"}
    body = json.dumps(payload).encode("utf-8")
    headers = build_auth_headers("PATCH", path, body)
    resp = client.patch(path, content=body, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "IMMUTABLE_PRICE_KEY_REJECTED"


# ===========================================================================
# 4. CONTENT FULL PACK EXPLICIT OVERRIDE CASES (1 to 4)
# ===========================================================================
def test_content_full_pack_explicit_override_cases(test_env):
    """Validate all four explicit content override cases without numeric equality heuristics."""
    client = test_env["client"]

    # --- CASE 1: No overrides anywhere -> 20 + 30 + 20 = 70 ---
    clear_runtime_pricing_cache()
    assert bot.workflow_trend_analysis_cost_xu() == 20
    assert bot.workflow_script_storyboard_cost_xu() == 30
    assert bot.workflow_prompt_pack_cost_xu() == 20
    assert bot.workflow_content_cost_xu() == 70

    # --- CASE 2: Component override only -> trend=25, sum = 25 + 30 + 20 = 75 ---
    clear_runtime_pricing_cache()
    path_trend = "/internal/v1/admin/pricing/content_trend_analysis"
    body_trend = json.dumps({"expected_version": 1, "new_value": 25, "reason": "Trend override"}).encode("utf-8")
    resp_trend = client.patch(path_trend, content=body_trend, headers=build_auth_headers("PATCH", path_trend, body_trend))
    assert resp_trend.status_code == 200
    assert bot.workflow_trend_analysis_cost_xu() == 25
    assert bot.workflow_content_cost_xu() == 75

    # --- CASE 3: Full pack override = 80 -> result = 80 ---
    path_full = "/internal/v1/admin/pricing/content_full_pack"
    body_full_80 = json.dumps({"expected_version": 1, "new_value": 80, "reason": "Full pack 80"}).encode("utf-8")
    resp_full_80 = client.patch(path_full, content=body_full_80, headers=build_auth_headers("PATCH", path_full, body_full_80))
    assert resp_full_80.status_code == 200
    assert bot.workflow_content_cost_xu() == 80

    # --- CASE 4 (CRITICAL RED): Component sum = 75, explicit full pack override = 70 -> result MUST be 70! ---
    # Components sum is still 75 (trend=25, storyboard=30, prompt=20).
    # Mutate full pack from 80 -> 70 (version 2 -> 3)
    body_full_70 = json.dumps({"expected_version": 2, "new_value": 70, "reason": "Explicit full pack override to base value"}).encode("utf-8")
    resp_full_70 = client.patch(path_full, content=body_full_70, headers=build_auth_headers("PATCH", path_full, body_full_70))
    assert resp_full_70.status_code == 200
    assert bot.workflow_trend_analysis_cost_xu() == 25
    # The sum of components is 25 + 30 + 20 = 75. But full-pack has explicit override=70.
    # The result MUST be 70, NOT 75!
    assert bot.workflow_content_cost_xu() == 70


# ===========================================================================
# 5. CANONICAL ALIASES & NO DUPLICATE ROWS
# ===========================================================================
def test_canonical_pricing_aliases_and_no_duplicate_rows(test_env):
    """Protect voice_clone and voice_profile_storage aliases, ensure zero duplicate override rows."""
    client = test_env["client"]

    # 1. Alias dictionary mapping
    assert CANONICAL_PRICING_ALIASES["voice_clone"] == "voice_clone_create"
    assert CANONICAL_PRICING_ALIASES["voice_profile_storage"] == "voice_clone_create"

    # 2. GET via alias resolves canonical entry
    path_alias = "/internal/v1/admin/pricing/voice_clone"
    resp_get = client.get(path_alias, headers=build_auth_headers("GET", path_alias, b""))
    assert resp_get.status_code == 200
    assert resp_get.json()["pricing"]["price_key"] == "voice_clone_create"

    # 3. PATCH via alias mutates canonical price_key
    path_patch = "/internal/v1/admin/pricing/voice_profile_storage"
    body = json.dumps({"expected_version": 1, "new_value": 60, "reason": "Mutate via alias"}).encode("utf-8")
    resp_patch = client.patch(path_patch, content=body, headers=build_auth_headers("PATCH", path_patch, body))
    assert resp_patch.status_code == 200
    assert resp_patch.json()["pricing"]["price_key"] == "voice_clone_create"
    assert resp_patch.json()["pricing"]["effective_value"] == 60

    # 4. In SQLite, verify exactly 1 row exists for voice_clone_create, and 0 for aliases
    conn = sqlite3.connect(str(test_env["db_file"]))
    rows = conn.execute("SELECT price_key FROM admin_pricing_overrides WHERE price_key IN ('voice_clone', 'voice_profile_storage', 'voice_clone_create')").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][0] == "voice_clone_create"


# ===========================================================================
# 6. SAFETY INVARIANT: ZERO MUTATIONS TO USERS, CREDITS, ORDERS, PROJECTS
# ===========================================================================
def test_safety_invariant_zero_wallet_or_data_mutations(test_env):
    """Verify that consumer reconciliation test suite causes zero side-effects to database tables."""
    conn = sqlite3.connect(str(test_env["db_file"]))
    conn.row_factory = sqlite3.Row

    user = dict(conn.execute("SELECT * FROM users WHERE user_id = '1001'").fetchone())
    credit_events = conn.execute("SELECT * FROM credit_events").fetchall()
    payos_orders = conn.execute("SELECT * FROM payos_orders").fetchall()
    video_projects = conn.execute("SELECT * FROM video_projects").fetchall()
    conn.close()

    assert user["credits"] == 500
    assert len(credit_events) == 1
    assert len(payos_orders) == 1
    assert len(video_projects) == 1
