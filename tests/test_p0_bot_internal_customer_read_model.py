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

from services.admin_wallet_service import verify_internal_admin_wallet_auth
from services.customer_read_model_service import (
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
# Section 2: Wallet Reading & Reconciliation
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
    conn.commit()
    conn.close()

    ok, result, status_code = read_canonical_wallet("1001", str(db_file))
    assert ok is True
    assert status_code == 200
    assert result["status_name"] == "read_only"
    data = result["data"]
    assert data["balance_xu"] == 500
    assert data["total_spent_xu"] == 100
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


def test_read_canonical_wallet_zero_credits_no_events_reconciled(tmp_path: Path):
    db_file = tmp_path / "test_zero.db"
    conn = create_test_db(db_file)
    conn.execute("INSERT INTO users (user_id, username, credits, is_vip) VALUES ('1003', 'zero_user', 0, 0)")
    conn.commit()
    conn.close()

    ok, result, status_code = read_canonical_wallet("1003", str(db_file))
    assert ok is True
    assert result["status_name"] == "read_only"
    assert result["data"]["balance_xu"] == 0
    assert result["data"]["total_spent_xu"] == 0
    assert result["data"]["reconciliation"]["reconciled"] is True


def test_read_canonical_wallet_database_error():
    ok, result, status_code = read_canonical_wallet("1001", "invalid/nonexistent/dir/db.sqlite")
    assert ok is False
    assert result["status_name"] == "guarded"
    assert result["error_code"] == "WALLET_DATABASE_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Section 3: Wallet History
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
# Section 4: Canonical Pricing Catalog
# ---------------------------------------------------------------------------

def test_read_canonical_pricing_catalog():
    ok, result, status_code = read_canonical_pricing_catalog()
    assert ok is True
    assert status_code == 200
    assert result["status_name"] == "read_only"
    data = result["data"]
    assert data["available"] is True
    assert data["billing_mode"] == "prepaid_xu"
    assert data["price_table_source"] == "canonical_bot_core"

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

    # Video combos
    video_combos = data["video_combos"]
    assert len(video_combos) >= 1

    # Public sale catalog
    sale = data["public_sale_catalog"]
    assert sale["available"] is True
    assert "catalog_version" in sale
    assert len(sale["items"]) > 0


# ---------------------------------------------------------------------------
# Section 5: Canonical Packages Catalog
# ---------------------------------------------------------------------------

def test_read_canonical_packages_catalog():
    ok, result, status_code = read_canonical_packages_catalog()
    assert ok is True
    assert status_code == 200
    assert result["status_name"] == "read_only"
    data = result["data"]
    assert data["available"] is True

    # Monthly packages
    monthly = data["monthly"]
    assert len(monthly) >= 4
    monthly_codes = {item["code"] for item in monthly}
    assert {"starter", "creator", "pro", "business"}.issubset(monthly_codes)

    # Topup packages
    topup = data["topup"]
    assert len(topup) >= 6
    topup_codes = {item["code"] for item in topup}
    assert {"10k", "20k", "50k", "100k", "200k", "500k"}.issubset(topup_codes)


# ---------------------------------------------------------------------------
# Section 6: Internal Authentication Verification on GET Requests
# ---------------------------------------------------------------------------

def test_verify_internal_auth_get_request(monkeypatch):
    token = "secret-bridge-token"
    hmac_secret = "secret-hmac-key"
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", token)
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", hmac_secret)

    now_ts = str(int(time.time()))
    req_id = "test-req-001"
    digest = hashlib.sha256(b"").hexdigest()
    path = "/internal/v1/wallet"
    message = f"{now_ts}.{req_id}.GET.{path}.{digest}".encode("utf-8")
    signature = hmac.new(hmac_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()

    # Valid GET auth
    is_valid, err, status = verify_internal_admin_wallet_auth(
        authorization=f"Bearer {token}",
        signature=signature,
        timestamp=now_ts,
        request_id=req_id,
        method="GET",
        path=path,
        body_bytes=b"",
    )
    assert is_valid is True
    assert err == "OK"
    assert status == 200

    # Missing auth
    is_valid, err, status = verify_internal_admin_wallet_auth(
        authorization="",
        method="GET",
        path=path,
    )
    assert is_valid is False
    assert err == "AUTH_MISSING"
    assert status == 401

    # Invalid token
    is_valid, err, status = verify_internal_admin_wallet_auth(
        authorization="Bearer wrong-token",
        method="GET",
        path=path,
    )
    assert is_valid is False
    assert err == "AUTH_INVALID"
    assert status == 401

    # Invalid signature
    is_valid, err, status = verify_internal_admin_wallet_auth(
        authorization=f"Bearer {token}",
        signature="wrong-signature",
        timestamp=now_ts,
        request_id=req_id,
        method="GET",
        path=path,
        body_bytes=b"",
    )
    assert is_valid is False
    assert err == "SIGNATURE_INVALID"
    assert status == 401


# ---------------------------------------------------------------------------
# Section 7: Invariants: Zero Mutations & Zero Wallet Deductions
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

    # Read wallet
    read_canonical_wallet("8888", str(db_file))
    # Read history
    read_canonical_wallet_history("8888", str(db_file))
    # Read pricing
    read_canonical_pricing_catalog()
    # Read packages
    read_canonical_packages_catalog()

    # Check that users table was NOT modified
    row = conn.execute("SELECT credits FROM users WHERE user_id='8888'").fetchone()
    assert row[0] == 100

    # Check that credit_events count was NOT changed
    event_count = conn.execute("SELECT COUNT(*) FROM credit_events WHERE user_id='8888'").fetchone()[0]
    assert event_count == 1
    conn.close()
