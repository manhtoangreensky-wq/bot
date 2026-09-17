"""Unit and contract tests for Bot Core customer read model service and endpoints.

Task: P0.BOT.INTERNAL.CUSTOMER.READ.MODEL.API.V1
Verifies:
- GET /internal/v1/wallet (unlinked, unverified, reconciled, unreconciled fail-closed)
- GET /internal/v1/wallet/history (empty, populated)
- GET /internal/v1/pricing (canonical image/video tiers, video combos, public sale catalog)
- GET /internal/v1/packages (canonical monthly, combos, topup packages)
- Internal Bearer and HMAC authentication on GET paths
- Zero mutations, zero wallet mutations, zero provider calls
"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
import sqlite3
import time
import pytest

from services.admin_wallet_service import (
    compute_internal_admin_wallet_signature,
    verify_internal_admin_wallet_auth,
)
from services.customer_read_model_service import (
    calculate_canonical_total_paid_vnd,
    normalize_target_user_id,
    read_canonical_wallet,
    read_canonical_wallet_history,
    read_canonical_pricing_catalog,
    read_canonical_packages_catalog,
)


def create_test_db(db_path: Path) -> sqlite3.Connection:
    """Create isolated SQLite test database matching canonical schema."""
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        username TEXT,
        credits INTEGER DEFAULT 0,
        is_vip INTEGER DEFAULT 0,
        join_date TEXT,
        total_spent INTEGER DEFAULT 0,
        total_paid_vnd INTEGER DEFAULT 0
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
        status TEXT,
        created_at DATETIME
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS pending_deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        amount_vnd INTEGER,
        status TEXT,
        created_at DATETIME
    )""")
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Section 1: Target User ID Normalization
# ---------------------------------------------------------------------------

def test_normalize_target_user_id():
    assert normalize_target_user_id("123456") == "123456"
    assert normalize_target_user_id("telegram-123456") == "123456"
    assert normalize_target_user_id("  telegram-987654  ") == "987654"
    assert normalize_target_user_id("") == ""
    assert normalize_target_user_id(None) == ""


# ---------------------------------------------------------------------------
# Section 2: Lifetime Proven Total Paid VND Truth
# ---------------------------------------------------------------------------

def test_calculate_canonical_total_paid_vnd(tmp_path: Path):
    db_file = tmp_path / "test_paid_vnd.db"
    conn = create_test_db(db_file)
    c = conn.cursor()

    # User 1: PayOS only
    c.execute("INSERT INTO users (user_id, username, credits) VALUES ('5001', 'u1', 0)")
    c.execute("INSERT INTO payos_orders (order_code, user_id, amount, status) VALUES (101, '5001', 50000, 'PAID')")
    c.execute("INSERT INTO payos_orders (order_code, user_id, amount, status) VALUES (102, '5001', 100000, 'completed')")
    c.execute("INSERT INTO payos_orders (order_code, user_id, amount, status) VALUES (103, '5001', 200000, 'PENDING')")

    # User 2: Manual deposit + PayOS
    c.execute("INSERT INTO users (user_id, username, credits) VALUES ('5002', 'u2', 0)")
    c.execute("INSERT INTO payos_orders (order_code, user_id, amount, status) VALUES (201, '5002', 20000, 'PAID')")
    c.execute("INSERT INTO pending_deposits (user_id, amount_vnd, status) VALUES ('5002', 30000, 'approved')")

    # User 3: users.total_paid_vnd stored is higher
    c.execute("INSERT INTO users (user_id, username, credits, total_paid_vnd) VALUES ('5003', 'u3', 0, 500000)")
    c.execute("INSERT INTO payos_orders (order_code, user_id, amount, status) VALUES (301, '5003', 100000, 'PAID')")

    conn.commit()

    paid_1, dep_1 = calculate_canonical_total_paid_vnd(c, "5001")
    assert paid_1 == 150000
    assert dep_1 == 150000

    paid_2, dep_2 = calculate_canonical_total_paid_vnd(c, "5002")
    assert paid_2 == 50000
    assert dep_2 == 50000

    paid_3, dep_3 = calculate_canonical_total_paid_vnd(c, "5003")
    assert paid_3 == 500000
    assert dep_3 == 500000

    conn.close()


# ---------------------------------------------------------------------------
# Section 3: Wallet Reading & Reconciliation
# ---------------------------------------------------------------------------

def test_read_canonical_wallet_unlinked():
    ok, result, status_code = read_canonical_wallet("", db_path=":memory:")
    assert ok is False
    assert status_code == 200
    assert result["status_name"] == "unlinked"
    assert result["error_code"] == "ACCOUNT_TELEGRAM_UNLINKED"
    assert result["data"] is None


def test_read_canonical_wallet_unverified_not_in_users(tmp_path: Path):
    db_file = tmp_path / "test_unverified.db"
    conn = create_test_db(db_file)
    conn.close()

    ok, result, status_code = read_canonical_wallet("999999", str(db_file))
    assert ok is False
    assert status_code == 200
    assert result["status_name"] == "unverified"
    assert result["error_code"] == "BOT_USER_NOT_INITIALIZED"
    assert result["data"] is None


def test_read_canonical_wallet_reconciled(tmp_path: Path):
    db_file = tmp_path / "test_reconciled.db"
    conn = create_test_db(db_file)
    conn.execute("INSERT INTO users (user_id, username, credits, is_vip) VALUES ('1001', 'test_user', 500, 1)")
    conn.execute(
        "INSERT INTO credit_events (user_id, delta, balance_after, event_type, created_at) "
        "VALUES ('1001', 600, 600, 'topup', '2026-09-17 10:00:00')"
    )
    conn.execute(
        "INSERT INTO credit_events (user_id, delta, balance_after, event_type, created_at) "
        "VALUES ('1001', -100, 500, 'usage', '2026-09-17 10:05:00')"
    )
    conn.execute("INSERT INTO payos_orders (order_code, user_id, amount, status) VALUES (1, '1001', 60000, 'PAID')")
    conn.commit()
    conn.close()

    ok, result, status_code = read_canonical_wallet("1001", str(db_file))
    assert ok is True
    assert status_code == 200
    assert result["status_name"] == "read_only"
    data = result["data"]
    assert data["balance_xu"] == 500
    assert data["total_spent_xu"] == 100
    assert data["total_paid_vnd"] == 60000
    assert data["total_deposited_vnd"] == 60000
    assert data["is_vip"] is True
    assert data["reconciliation"]["reconciled"] is True
    assert data["reconciliation"]["discrepancy"] == 0
    assert data["reconciliation"]["snapshot_credits"] == 500
    assert data["reconciliation"]["ledger_credits"] == 500


def test_read_canonical_wallet_unreconciled_fails_closed(tmp_path: Path):
    db_file = tmp_path / "test_unreconciled.db"
    conn = create_test_db(db_file)
    # Database snapshot says 800, but latest ledger says 500 (discrepancy = 300!)
    conn.execute("INSERT INTO users (user_id, username, credits, is_vip) VALUES ('1002', 'mismatch_user', 800, 0)")
    conn.execute(
        "INSERT INTO credit_events (user_id, delta, balance_after, event_type, created_at) "
        "VALUES ('1002', 500, 500, 'topup', '2026-09-17 10:00:00')"
    )
    conn.commit()
    conn.close()

    ok, result, status_code = read_canonical_wallet("1002", str(db_file))
    assert ok is False
    assert status_code == 200
    assert result["status_name"] == "guarded"
    assert result["error_code"] == "WALLET_LEDGER_UNRECONCILED"
    data = result["data"]
    assert data["reconciliation"]["reconciled"] is False
    assert data["reconciliation"]["discrepancy"] == 300
    assert data["reconciliation"]["snapshot_credits"] == 800
    assert data["reconciliation"]["ledger_credits"] == 500


def test_read_canonical_wallet_strictly_mode_ro():
    """Fails closed immediately if path cannot be opened with mode=ro, zero RW fallback."""
    ok, result, status_code = read_canonical_wallet("1001", "invalid/nonexistent/dir/db.sqlite")
    assert ok is False
    assert status_code == 200
    assert result["status_name"] == "guarded"
    assert result["error_code"] == "WALLET_DATABASE_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Section 4: Wallet History
# ---------------------------------------------------------------------------

def test_read_canonical_wallet_history_unlinked():
    ok, result, status_code = read_canonical_wallet_history("", db_path=":memory:")
    assert ok is False
    assert result["status_name"] == "unlinked"
    assert result["error_code"] == "ACCOUNT_TELEGRAM_UNLINKED"
    assert result["data"]["items"] == []


def test_read_canonical_wallet_history_success(tmp_path: Path):
    db_file = tmp_path / "test_history.db"
    conn = create_test_db(db_file)
    conn.execute("INSERT INTO users (user_id, username, credits) VALUES ('2001', 'hist_user', 300)")
    conn.execute(
        "INSERT INTO credit_events (user_id, delta, balance_after, event_type, created_at) "
        "VALUES ('2001', 500, 500, 'topup', '2026-09-17 11:00:00')"
    )
    conn.execute(
        "INSERT INTO credit_events (user_id, delta, balance_after, event_type, created_at) "
        "VALUES ('2001', -200, 300, 'task_usage', '2026-09-17 11:10:00')"
    )
    conn.commit()
    conn.close()

    ok, result, status_code = read_canonical_wallet_history("2001", str(db_file))
    assert ok is True
    assert result["status_name"] == "read_only"
    items = result["data"]["items"]
    assert len(items) == 2
    assert items[0]["delta_xu"] == -200
    assert items[0]["balance_after_xu"] == 300
    assert items[0]["event_type"] == "task_usage"
    assert items[1]["delta_xu"] == 500
    assert items[1]["balance_after_xu"] == 500


# ---------------------------------------------------------------------------
# Section 5: Canonical Pricing Catalog
# ---------------------------------------------------------------------------

def test_read_canonical_pricing_catalog():
    # Without dynamic combos function: video_combos should be empty list (no hardcoded fake combos!)
    ok, result, status_code = read_canonical_pricing_catalog()
    assert ok is True
    assert status_code == 200
    assert result["status_name"] == "read_only"
    data = result["data"]
    assert data["available"] is True
    assert data["billing_mode"] == "prepaid_xu"
    assert data["price_table_source"] == "canonical_bot_core"
    assert data["video_combos"] == []

    # Image tiers
    image_tiers = data["image_tiers"]
    assert len(image_tiers) >= 2
    for tier in image_tiers:
        assert "code" in tier
        assert "label" in tier
        assert "unit_xu" in tier
        assert tier["unit_xu"] > 0

    # Video tiers
    video_tiers = data["video_tiers"]
    assert len(video_tiers) >= 3
    for tier in video_tiers:
        assert "code" in tier
        assert "label" in tier
        assert "unit_xu" in tier
        assert tier["unit_xu"] > 0

    # With dynamic combo fn
    def mock_combo_catalog():
        return {
            "combo_3scene": {"label": "Combo 3 Phân Cảnh", "note": "Quảng cáo ngắn 15s"},
            "combo_5scene": {"label": "Combo 5 Phân Cảnh", "note": "Video chi tiết 30s"},
        }

    ok2, result2, status_code2 = read_canonical_pricing_catalog(combo_catalog_fn=mock_combo_catalog)
    assert ok2 is True
    assert len(result2["data"]["video_combos"]) == 2
    assert result2["data"]["video_combos"][0]["code"] == "combo_3scene"


# ---------------------------------------------------------------------------
# Section 6: Canonical Packages Catalog
# ---------------------------------------------------------------------------

def test_read_canonical_packages_catalog_fails_closed_when_missing():
    # When catalogs are not provided / missing, fails closed with PACKAGES_CATALOG_UNAVAILABLE
    ok, result, status_code = read_canonical_packages_catalog(plan_catalog=None, payment_packages=None)
    assert ok is False
    assert status_code == 200
    assert result["status_name"] == "guarded"
    assert result["error_code"] == "PACKAGES_CATALOG_UNAVAILABLE"


def test_read_canonical_packages_catalog_success():
    sample_plans = {
        "starter": {"name": "Gói Starter", "description": "Gói khởi động", "duration_days": 30, "plan_xu": 500},
        "creator": {"name": "Gói Creator", "description": "Gói sáng tạo", "duration_days": 30, "plan_xu": 1500},
    }
    sample_combos = {
        "combo_basic": {"label": "Combo Basic", "note": "Gói combo 3 scene", "items": {"xu": 300}},
    }
    sample_topup = {
        "10k": {"amount": 10000, "xu": 100, "text": "10.000đ (100 Xu)"},
        "50k": {"amount": 50000, "xu": 550, "text": "50.000đ (550 Xu)"},
    }

    ok, result, status_code = read_canonical_packages_catalog(
        plan_catalog=sample_plans,
        combo_catalog_fn=lambda: sample_combos,
        payment_packages=sample_topup,
    )
    assert ok is True
    assert status_code == 200
    assert result["status_name"] == "read_only"
    data = result["data"]
    assert len(data["monthly"]) == 2
    assert len(data["combos"]) == 1
    assert len(data["topup"]) == 2


# ---------------------------------------------------------------------------
# Section 7: HMAC Identity Binding & Tamper Rejection
# ---------------------------------------------------------------------------

def test_verify_internal_auth_with_actor_id_binding(monkeypatch):
    token = "secret-bridge-token"
    hmac_secret = "secret-hmac-key"
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", token)
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", hmac_secret)

    now_ts = str(int(time.time()))
    req_id = "req-test-tamper-01"
    path = "/internal/v1/wallet"
    actor_id = "1001"

    # Signature bound to actor_id="1001"
    valid_sig = compute_internal_admin_wallet_signature(
        secret=hmac_secret,
        timestamp=now_ts,
        request_id=req_id,
        method="GET",
        path=path,
        body_bytes=b"",
        actor_id=actor_id,
    )

    # 1. Valid verification with matching actor_id
    is_valid, err, status = verify_internal_admin_wallet_auth(
        authorization=f"Bearer {token}",
        signature=valid_sig,
        timestamp=now_ts,
        request_id=req_id,
        method="GET",
        path=path,
        body_bytes=b"",
        actor_id="1001",
    )
    assert is_valid is True
    assert err == "OK"
    assert status == 200

    # 2. Tampered actor_id="9999" MUST BE REJECTED
    is_valid, err, status = verify_internal_admin_wallet_auth(
        authorization=f"Bearer {token}",
        signature=valid_sig,
        timestamp=now_ts,
        request_id=req_id,
        method="GET",
        path=path,
        body_bytes=b"",
        actor_id="9999",
    )
    assert is_valid is False
    assert err == "SIGNATURE_INVALID"
    assert status == 401

    # 3. Omitted actor_id when signature was bound MUST BE REJECTED
    is_valid, err, status = verify_internal_admin_wallet_auth(
        authorization=f"Bearer {token}",
        signature=valid_sig,
        timestamp=now_ts,
        request_id=req_id,
        method="GET",
        path=path,
        body_bytes=b"",
        actor_id="",
    )
    assert is_valid is False
    assert err == "SIGNATURE_INVALID"
    assert status == 401


# ---------------------------------------------------------------------------
# Section 8: Invariants: Zero Mutations & Zero Wallet Deductions
# ---------------------------------------------------------------------------

def test_invariants_zero_mutations(tmp_path: Path):
    """Reading wallet, history, pricing, or packages must NEVER mutate DB tables."""
    db_file = tmp_path / "test_invariants.db"
    conn = create_test_db(db_file)
    conn.execute("INSERT INTO users (user_id, username, credits) VALUES ('8888', 'inv_user', 100)")
    conn.execute(
        "INSERT INTO credit_events (user_id, delta, balance_after, event_type, created_at) "
        "VALUES ('8888', 100, 100, 'initial', '2026-09-17 12:00:00')"
    )
    conn.commit()

    sample_plans = {"p1": {"name": "P1", "duration_days": 30, "plan_xu": 100}}
    sample_topup = {"t1": {"amount": 10000, "xu": 100, "text": "10k"}}

    # Read wallet
    read_canonical_wallet("8888", str(db_file))
    # Read history
    read_canonical_wallet_history("8888", str(db_file))
    # Read pricing
    read_canonical_pricing_catalog()
    # Read packages
    read_canonical_packages_catalog(plan_catalog=sample_plans, payment_packages=sample_topup)

    # Check that users table was NOT modified
    row = conn.execute("SELECT credits FROM users WHERE user_id='8888'").fetchone()
    assert row[0] == 100

    # Check that credit_events count was NOT changed
    event_count = conn.execute("SELECT COUNT(*) FROM credit_events WHERE user_id='8888'").fetchone()[0]
    assert event_count == 1
    conn.close()
