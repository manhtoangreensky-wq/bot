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
    """RED 7: Product Video supported ratios equals canonical product authority directly (or NOT_EXPOSED)."""
    client = test_env["client"]
    path = "/internal/v1/admin/products/video_trend"
    headers = build_auth_headers("GET", path, b"")
    resp = client.get(path, headers=headers)
    assert resp.status_code == 200
    effective = resp.json().get("effective", {})

    comm = video_tail9.commercial_contract("video_trend")
    if "supported_ratios" in comm and comm["supported_ratios"] is not None:
        expected = list(comm["supported_ratios"])
    elif hasattr(video_tail9, "supported_ratios") and callable(getattr(video_tail9, "supported_ratios")):
        expected = list(video_tail9.supported_ratios("video_trend"))
    else:
        expected = "NOT_EXPOSED"

    assert effective.get("supported_ratios") == expected


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


def test_red_10_product_count_static_inventory(monkeypatch, test_env):
    """RED 10: Dynamic discovery must discover newly added canonical source products."""
    monkeypatch.setitem(
        video_tail9.PRODUCT_ADAPTERS,
        "video_dynamic_test_product",
        {
            "flow_owner": "test",
            "engine_route": "test",
            "executor_product_type": "video_dynamic_test_product",
            "source_audio_available": False,
            "return_to": "test",
            "required_capability": "text_to_video",
            "input_type": "text",
            "worker_owner": "product_video",
            "supported_quality_tiers": (100, 200),
            "execution_enabled": True,
        }
    )
    client = test_env["client"]
    resp = client.get("/internal/v1/admin/products", headers=build_auth_headers("GET", "/internal/v1/admin/products", b""))
    assert resp.status_code == 200
    product_keys = [p["product_key"] for p in resp.json().get("products", [])]
    assert "video_dynamic_test_product" in product_keys, "Dynamic source product must appear in admin collection without editing static tuples"


def test_red_11_product_video_ratios_hardcoded(monkeypatch, test_env):
    """RED 11: Admin product video ratios must dynamically reflect canonical authority when exposed, without hardcoding."""
    monkeypatch.setattr(video_tail9, "supported_ratios", lambda p: ["9:16"], raising=False)

    client = test_env["client"]
    resp = client.get("/internal/v1/admin/products/video_trend", headers=build_auth_headers("GET", "/internal/v1/admin/products/video_trend", b""))
    assert resp.status_code == 200
    ratios = resp.json()["effective"]["supported_ratios"]
    assert ratios == ["9:16"], f"Admin ratios must dynamically derive from canonical authority, got {ratios}"


def test_red_12_image_technical_fallback_fail_open(monkeypatch, test_env):
    """RED 12: Image authority failure must fail closed, NOT invent tiers or ready=True."""
    from services import video_ai_real_pricing
    def broken_catalog():
        raise RuntimeError("Image authority catalog unavailable")
    monkeypatch.setattr(video_ai_real_pricing, "public_image_quality_catalog", broken_catalog)

    client = test_env["client"]
    resp = client.get("/internal/v1/admin/products/image_generation", headers=build_auth_headers("GET", "/internal/v1/admin/products/image_generation", b""))
    assert resp.status_code == 200
    effective = resp.json()["effective"]
    assert effective["execution_enabled"] is False, "Image must fail closed (execution_enabled=False) on authority failure"
    assert effective["supported_tiers"] == [], f"Image must NOT invent tiers on authority failure, got {effective['supported_tiers']}"


def test_red_13_tts_authority_failure_fail_open(monkeypatch, test_env):
    """RED 13: Voice TTS authority failure must fail closed, NOT invent voices or ready=True."""
    def broken_tts(**kwargs):
        raise RuntimeError("TTS readiness check failed")
    monkeypatch.setattr(bot, "get_tts_provider_readiness", broken_tts)

    client = test_env["client"]
    resp = client.get("/internal/v1/admin/products/voice_tts", headers=build_auth_headers("GET", "/internal/v1/admin/products/voice_tts", b""))
    assert resp.status_code == 200
    effective = resp.json()["effective"]
    assert effective["execution_enabled"] is False, "Voice TTS must fail closed (execution_enabled=False) on authority failure"
    assert effective["supported_tiers"] == [], f"Voice TTS must NOT invent voices on authority failure, got {effective['supported_tiers']}"


def test_red_14_voice_clone_source_authority_not_called(monkeypatch, test_env):
    """RED 14: Voice clone must actually invoke bot.get_minimax_voice_clone_readiness."""
    invoked = []
    def mock_clone_readiness():
        invoked.append(True)
        return {"ready": False, "public_enabled": False, "reason": "clone_offline"}
    monkeypatch.setattr(bot, "get_minimax_voice_clone_readiness", mock_clone_readiness)

    client = test_env["client"]
    resp = client.get("/internal/v1/admin/products/voice_clone", headers=build_auth_headers("GET", "/internal/v1/admin/products/voice_clone", b""))
    assert resp.status_code == 200
    effective = resp.json()["effective"]
    assert len(invoked) > 0, "Claimed authority bot.get_minimax_voice_clone_readiness was not invoked"
    assert effective["execution_enabled"] is False
    assert effective["execution_blocker"] == "clone_offline"
    assert effective["supported_tiers"] == [], "Unproven voice clone tiers must not be invented"


def test_red_15_music_authority_failure_invents_technical_truth(monkeypatch, test_env):
    """RED 15: Music authority failure must fail closed, NOT invent fallback tiers."""
    from services import video_ai_real_pricing
    def broken_music():
        raise RuntimeError("Music catalog unavailable")
    monkeypatch.setattr(video_ai_real_pricing, "music_model_catalog", broken_music)

    client = test_env["client"]
    resp = client.get("/internal/v1/admin/products/music_generation", headers=build_auth_headers("GET", "/internal/v1/admin/products/music_generation", b""))
    assert resp.status_code == 200
    effective = resp.json()["effective"]
    assert effective["execution_enabled"] is False, "Music must fail closed on authority failure"
    assert effective["supported_tiers"] == [], f"Music must NOT invent fallback tiers on authority failure, got {effective['supported_tiers']}"


def test_red_16_subdub_partial_authority_with_hardcoded_capability(test_env):
    """RED 16: SubDub unproven capability fields must be NOT_EXPOSED and execution_enabled must reflect real readiness."""
    client = test_env["client"]
    resp = client.get("/internal/v1/admin/products/subdub_service", headers=build_auth_headers("GET", "/internal/v1/admin/products/subdub_service", b""))
    assert resp.status_code == 200
    effective = resp.json()["effective"]
    assert effective["provider_capability"] == "NOT_EXPOSED", (
        f"Unproven SubDub provider_capability must be NOT_EXPOSED, got {effective.get('provider_capability')}"
    )
    assert effective["execution_enabled"] is False, "SubDub execution_enabled must reflect live readiness (which is currently False/requires smoke)"


def test_red_17_chat_partial_authority_with_hardcoded_capability(test_env):
    """RED 17: Chat Pro unproven capability fields must be NOT_EXPOSED and execution_enabled must be False (fail closed)."""
    client = test_env["client"]
    resp = client.get("/internal/v1/admin/products/chat_pro", headers=build_auth_headers("GET", "/internal/v1/admin/products/chat_pro", b""))
    assert resp.status_code == 200
    effective = resp.json()["effective"]
    assert effective["provider_capability"] == "NOT_EXPOSED", (
        f"Unproven Chat Pro provider_capability must be NOT_EXPOSED, got {effective.get('provider_capability')}"
    )
    assert effective["execution_enabled"] is False, "Chat Pro has no live readiness authority and must fail closed (execution_enabled=False)"


def test_red_18_base_products_import_snapshot_stale(monkeypatch):
    """RED 18: BASE_PRODUCTS must NOT be a static import-time snapshot of live technical truth."""
    import services.admin_product_service as aps
    monkeypatch.setattr(bot, "get_tts_provider_readiness", lambda **kw: {"public_ready": False, "supported_voices": [], "reason": "offline"})
    fresh_base = aps.resolve_canonical_technical_contract("voice_tts")
    assert fresh_base["execution_enabled"] is False
    assert aps.BASE_PRODUCTS["voice_tts"]["execution_enabled"] is False, (
        "BASE_PRODUCTS holds a stale import-time snapshot that does not reflect live technical truth"
    )


def test_red_19_discovery_adapters_exist():
    """RED 19: Explicit dynamic discovery adapters must exist and be callable."""
    import services.admin_product_service as aps
    assert hasattr(aps, "discover_canonical_products"), "admin_product_service must provide discover_canonical_products"
    assert hasattr(aps, "discover_product_video_products"), "admin_product_service must provide discover_product_video_products"
    assert callable(aps.discover_canonical_products)


def test_red_20_image_unproven_technical_fields(test_env):
    """RED 20: Image unproven capability and routing fields must be NOT_EXPOSED."""
    client = test_env["client"]
    resp = client.get("/internal/v1/admin/products/image_generation", headers=build_auth_headers("GET", "/internal/v1/admin/products/image_generation", b""))
    assert resp.status_code == 200
    effective = resp.json()["effective"]
    for field in (
        "required_capability",
        "provider_capability",
        "modality",
        "executor_product_type",
        "engine_route",
        "flow_owner",
        "worker_owner",
    ):
        assert effective.get(field) == "NOT_EXPOSED", (
            f"Image field {field} is unproven by image authority and must be NOT_EXPOSED, got {effective.get(field)}"
        )


def test_red_21_tts_unproven_technical_fields(test_env):
    """RED 21: TTS unproven capability and routing fields must be NOT_EXPOSED."""
    client = test_env["client"]
    resp = client.get("/internal/v1/admin/products/voice_tts", headers=build_auth_headers("GET", "/internal/v1/admin/products/voice_tts", b""))
    assert resp.status_code == 200
    effective = resp.json()["effective"]
    for field in (
        "required_capability",
        "provider_capability",
        "modality",
        "executor_product_type",
        "engine_route",
        "flow_owner",
        "worker_owner",
    ):
        assert effective.get(field) == "NOT_EXPOSED", (
            f"TTS field {field} is unproven by get_tts_provider_readiness and must be NOT_EXPOSED, got {effective.get(field)}"
        )


def test_red_22_voice_clone_unproven_technical_fields(test_env):
    """RED 22: Voice clone unproven capability and routing fields must be NOT_EXPOSED."""
    client = test_env["client"]
    resp = client.get("/internal/v1/admin/products/voice_clone", headers=build_auth_headers("GET", "/internal/v1/admin/products/voice_clone", b""))
    assert resp.status_code == 200
    effective = resp.json()["effective"]
    for field in (
        "required_capability",
        "provider_capability",
        "modality",
        "executor_product_type",
        "engine_route",
        "flow_owner",
        "worker_owner",
    ):
        assert effective.get(field) == "NOT_EXPOSED", (
            f"Voice clone field {field} is unproven by get_minimax_voice_clone_readiness and must be NOT_EXPOSED, got {effective.get(field)}"
        )


def test_red_23_music_unproven_technical_fields(test_env):
    """RED 23: Music unproven capability and routing fields must be NOT_EXPOSED."""
    client = test_env["client"]
    resp = client.get("/internal/v1/admin/products/music_generation", headers=build_auth_headers("GET", "/internal/v1/admin/products/music_generation", b""))
    assert resp.status_code == 200
    effective = resp.json()["effective"]
    for field in (
        "required_capability",
        "provider_capability",
        "modality",
        "executor_product_type",
        "engine_route",
        "flow_owner",
        "worker_owner",
    ):
        assert effective.get(field) == "NOT_EXPOSED", (
            f"Music field {field} is unproven by music_model_catalog and must be NOT_EXPOSED, got {effective.get(field)}"
        )


def test_red_24_product_video_new_ratio_discovery(monkeypatch, test_env):
    """RED 24: Monkeypatching canonical ratio authority with a new ratio ('2:1') must be discovered without editing admin_product_service."""
    orig_compat = video_tail9.package_compatibility
    def mock_compat(product_type, **kwargs):
        res = orig_compat(product_type, **kwargs)
        if kwargs.get("ratio") == "2:1":
            res["ok"] = True
            res["blockers"] = [b for b in res.get("blockers", []) if b != "ratio_not_supported"]
        return res

    monkeypatch.setattr(video_tail9, "package_compatibility", mock_compat)
    monkeypatch.setattr(video_tail9, "supported_ratios", lambda p: ["9:16", "16:9", "1:1", "4:5", "2:1"], raising=False)

    client = test_env["client"]
    resp = client.get("/internal/v1/admin/products/video_trend", headers=build_auth_headers("GET", "/internal/v1/admin/products/video_trend", b""))
    assert resp.status_code == 200
    effective = resp.json()["effective"]
    ratios = effective.get("supported_ratios")
    assert isinstance(ratios, list) and "2:1" in ratios, (
        f"Admin must discover newly supported canonical ratio '2:1' dynamically, got {ratios}"
    )


def test_red_25_ratio_test_not_self_comparator(test_env):
    """RED 25: When canonical authority exposes NO ratio inventory, Admin must return NOT_EXPOSED rather than filtering hardcoded candidates."""
    client = test_env["client"]
    resp = client.get("/internal/v1/admin/products/video_trend", headers=build_auth_headers("GET", "/internal/v1/admin/products/video_trend", b""))
    assert resp.status_code == 200
    effective = resp.json()["effective"]
    assert effective.get("supported_ratios") == "NOT_EXPOSED", (
        f"When canonical authority has only admission predicate and no ratio inventory, supported_ratios must be NOT_EXPOSED, got {effective.get('supported_ratios')}"
    )
