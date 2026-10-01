"""P0 tests for Canonical Bot Core Web Product Video Settlement Bridge.

Validates:
- Atomic exactly-once settlement transaction (users.credits + credit_events + receipt)
- Duplicate settlement returns existing receipt with zero second debit
- Idempotency conflict prevention
- Price re-derivation: caller amount authority disabled, quote mismatch fail closed
- Insufficient balance fail closed
- Admin/Owner exemption: zero deduction, exempt receipt
- Admin ID 7126457028 valid for paid customer acceptance: NO
- Bearer + HMAC CoreBridge authentication
- Zero real provider calls, zero production wallet mutations
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Any
import pytest
from fastapi.testclient import TestClient

from services.admin_wallet_service import compute_internal_admin_wallet_signature
from services.web_product_video_settlement_service import (
    ensure_web_product_video_settlement_schema,
    derive_canonical_product_video_charge,
    execute_web_product_video_settlement,
    is_admin_or_owner_user,
    CANONICAL_PRODUCT_KEY,
)


def _init_test_bot_db(conn: sqlite3.Connection) -> None:
    """Create minimal required Bot SQLite schema for settlement testing."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            credits INTEGER NOT NULL DEFAULT 0,
            total_spent INTEGER NOT NULL DEFAULT 0,
            username TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS credit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            delta INTEGER NOT NULL,
            balance_after INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            ref_id TEXT,
            note TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    ensure_web_product_video_settlement_schema(conn)


@pytest.fixture
def test_db():
    conn = sqlite3.connect(":memory:", isolation_level=None)
    _init_test_bot_db(conn)
    yield conn
    conn.close()


def test_pricing_rederivation_canonical_values():
    """Bot independently derives canonical Product Video customer quote."""
    pricing = derive_canonical_product_video_charge(tier_id=200, scene_count=1)
    assert pricing["total_xu"] == 259
    assert pricing["unit_xu"] == 259
    assert pricing["scene_count"] == 1


def test_valid_completed_settlement_single_debit(test_db):
    """Item 1: Valid completed Web Product Video + non-admin customer -> exactly one debit."""
    test_db.execute("INSERT INTO users (user_id, credits, total_spent, username) VALUES (888888, 500, 0, 'Customer')")

    meta = {
        "duration_seconds": 5.0,
        "width": 720,
        "height": 1280,
        "file_size_bytes": 10240,
        "format": "mp4",
        "video_codec": "h264",
    }
    ok, res, status = execute_web_product_video_settlement(
        web_job_id="pvj_test_001",
        web_request_id="req_test_001",
        canonical_user_id="888888",
        product_key="video_ai_prompt",
        tier_id=200,
        scene_count=1,
        output_url="https://storage.googleapis.com/test-bucket/output.mp4",
        validated_output_metadata=meta,
        conn=test_db,
    )
    assert ok is True
    assert status == 200
    assert res["status"] == "settled"
    assert res["amount_xu"] == 259
    assert res["balance_before"] == 500
    assert res["balance_after"] == 241
    assert res["duplicate"] is False
    assert res["exempt"] is False

    # Verify atomic DB state: users credits decremented, total_spent incremented
    user_row = test_db.execute("SELECT credits, total_spent FROM users WHERE user_id = 888888").fetchone()
    assert user_row[0] == 241
    assert user_row[1] == 259

    # Verify credit_events ledger row
    events = test_db.execute("SELECT user_id, delta, balance_after, event_type, ref_id FROM credit_events").fetchall()
    assert len(events) == 1
    assert events[0][0] == 888888
    assert events[0][1] == -259
    assert events[0][2] == 241
    assert events[0][3] == "web_product_video_final_delivery"

    # Verify web_product_video_settlements receipt
    settlements = test_db.execute("SELECT web_job_id, amount_xu, status FROM web_product_video_settlements").fetchall()
    assert len(settlements) == 1
    assert settlements[0][0] == "pvj_test_001"
    assert settlements[0][1] == 259
    assert settlements[0][2] == "settled"


def test_duplicate_settlement_returns_existing_receipt_zero_second_debit(test_db):
    """Items 2, 3, 15, 16: Duplicate / replay settlement returns same receipt, duplicate wallet debit count = 0."""
    test_db.execute("INSERT INTO users (user_id, credits, total_spent, username) VALUES (888888, 500, 0, 'Customer')")

    meta = {
        "duration_seconds": 5.0,
        "width": 720,
        "height": 1280,
        "file_size_bytes": 10240,
        "format": "mp4",
        "video_codec": "h264",
    }
    # First settlement
    ok1, res1, status1 = execute_web_product_video_settlement(
        web_job_id="pvj_test_dup",
        web_request_id="req_test_dup",
        canonical_user_id="888888",
        product_key="video_ai_prompt",
        tier_id=200,
        scene_count=1,
        output_url="https://storage.googleapis.com/test-bucket/output.mp4",
        validated_output_metadata=meta,
        conn=test_db,
    )
    assert ok1 is True
    assert status1 == 200
    assert res1["duplicate"] is False

    # Second settlement (exact duplicate replay)
    ok2, res2, status2 = execute_web_product_video_settlement(
        web_job_id="pvj_test_dup",
        web_request_id="req_test_dup",
        canonical_user_id="888888",
        product_key="video_ai_prompt",
        tier_id=200,
        scene_count=1,
        output_url="https://storage.googleapis.com/test-bucket/output.mp4",
        validated_output_metadata=meta,
        conn=test_db,
    )
    assert ok2 is True
    assert status2 == 200
    assert res2["duplicate"] is True
    assert res2["settlement_id"] == res1["settlement_id"]
    assert res2["amount_xu"] == res1["amount_xu"]
    assert res2["balance_after"] == res1["balance_after"]

    # Verify duplicate debit count = 0 (balance is still 241, only 1 ledger event)
    user_row = test_db.execute("SELECT credits, total_spent FROM users WHERE user_id = 888888").fetchone()
    assert user_row[0] == 241
    assert user_row[1] == 259

    events = test_db.execute("SELECT COUNT(*) FROM credit_events").fetchone()
    assert events[0] == 1


def test_quote_mismatch_fails_closed(test_db):
    """Items 9, 10: Caller amount cannot override canonical price; quote mismatch fails closed."""
    test_db.execute("INSERT INTO users (user_id, credits, total_spent, username) VALUES (888888, 500, 0, 'Customer')")

    meta = {"duration_seconds": 5.0, "width": 720, "height": 1280, "file_size_bytes": 10240, "format": "mp4", "video_codec": "h264"}

    # Caller attempts to pay 10 Xu instead of canonical 259 Xu
    ok, res, status = execute_web_product_video_settlement(
        web_job_id="pvj_forged_quote",
        web_request_id="req_forged_quote",
        canonical_user_id="888888",
        product_key="video_ai_prompt",
        tier_id=200,
        scene_count=1,
        output_url="https://storage.googleapis.com/test-bucket/output.mp4",
        validated_output_metadata=meta,
        caller_amount_xu=10,
        conn=test_db,
    )
    assert ok is False
    assert status == 400
    assert res["error_code"] == "QUOTE_MISMATCH"

    # Zero wallet debit
    user_row = test_db.execute("SELECT credits FROM users WHERE user_id = 888888").fetchone()
    assert user_row[0] == 500
    assert test_db.execute("SELECT COUNT(*) FROM credit_events").fetchone()[0] == 0


def test_insufficient_balance_fails_closed(test_db):
    """Item 11: Insufficient customer balance -> zero debit."""
    test_db.execute("INSERT INTO users (user_id, credits, total_spent, username) VALUES (888888, 100, 0, 'PoorCustomer')")

    meta = {"duration_seconds": 5.0, "width": 720, "height": 1280, "file_size_bytes": 10240, "format": "mp4", "video_codec": "h264"}

    ok, res, status = execute_web_product_video_settlement(
        web_job_id="pvj_low_bal",
        web_request_id="req_low_bal",
        canonical_user_id="888888",
        product_key="video_ai_prompt",
        tier_id=200,
        scene_count=1,
        output_url="https://storage.googleapis.com/test-bucket/output.mp4",
        validated_output_metadata=meta,
        conn=test_db,
    )
    assert ok is False
    assert status == 402
    assert res["error_code"] == "INSUFFICIENT_BALANCE"

    # Verify zero debit
    user_row = test_db.execute("SELECT credits FROM users WHERE user_id = 888888").fetchone()
    assert user_row[0] == 100
    assert test_db.execute("SELECT COUNT(*) FROM credit_events").fetchone()[0] == 0


def test_admin_owner_exemption_zero_debit(test_db, monkeypatch):
    """Items 12, 13: Admin/Owner is exempt, no customer billing acceptance, 7126457028 valid for paid acceptance=NO."""
    admin_id = 7126457028
    monkeypatch.setenv("ADMIN_ID", str(admin_id))
    monkeypatch.setenv("OWNER_IDS", str(admin_id))

    assert is_admin_or_owner_user(admin_id) is True

    test_db.execute("INSERT INTO users (user_id, credits, total_spent, username) VALUES (?, 500, 0, 'AdminUser')", (admin_id,))

    meta = {"duration_seconds": 5.0, "width": 720, "height": 1280, "file_size_bytes": 10240, "format": "mp4", "video_codec": "h264"}

    ok, res, status = execute_web_product_video_settlement(
        web_job_id="pvj_admin_test",
        web_request_id="req_admin_test",
        canonical_user_id=str(admin_id),
        product_key="video_ai_prompt",
        tier_id=200,
        scene_count=1,
        output_url="https://storage.googleapis.com/test-bucket/output.mp4",
        validated_output_metadata=meta,
        conn=test_db,
    )
    assert ok is True
    assert status == 200
    assert res["status"] == "exempt"
    assert res["amount_xu"] == 0
    assert res["exempt"] is True
    assert res["charge_skip_reason"] == "admin_owner_free"

    # Verify zero debit from admin wallet
    user_row = test_db.execute("SELECT credits, total_spent FROM users WHERE user_id = ?", (admin_id,)).fetchone()
    assert user_row[0] == 500
    assert user_row[1] == 0
    assert test_db.execute("SELECT COUNT(*) FROM credit_events").fetchone()[0] == 0


def test_missing_user_fails_closed(test_db):
    """Non-existent canonical user ID fails closed."""
    meta = {"duration_seconds": 5.0, "width": 720, "height": 1280, "file_size_bytes": 10240, "format": "mp4", "video_codec": "h264"}

    ok, res, status = execute_web_product_video_settlement(
        web_job_id="pvj_no_user",
        web_request_id="req_no_user",
        canonical_user_id="999999999",
        product_key="video_ai_prompt",
        tier_id=200,
        scene_count=1,
        output_url="https://storage.googleapis.com/test-bucket/output.mp4",
        validated_output_metadata=meta,
        conn=test_db,
    )
    assert ok is False
    assert status == 404
    assert res["error_code"] == "USER_NOT_FOUND"


def test_idempotency_conflict_detection(test_db):
    """Reusing same web_job_id or key with different user fails with 409 conflict."""
    test_db.execute("INSERT INTO users (user_id, credits, total_spent, username) VALUES (111111, 500, 0, 'User1')")
    test_db.execute("INSERT INTO users (user_id, credits, total_spent, username) VALUES (222222, 500, 0, 'User2')")

    meta = {"duration_seconds": 5.0, "width": 720, "height": 1280, "file_size_bytes": 10240, "format": "mp4", "video_codec": "h264"}

    ok1, _, _ = execute_web_product_video_settlement(
        web_job_id="pvj_conflict_test",
        web_request_id="req_1",
        canonical_user_id="111111",
        product_key="video_ai_prompt",
        tier_id=200,
        scene_count=1,
        output_url="https://storage.googleapis.com/test-bucket/output.mp4",
        validated_output_metadata=meta,
        conn=test_db,
    )
    assert ok1 is True

    # Same job_id with different user -> conflict!
    ok2, res2, status2 = execute_web_product_video_settlement(
        web_job_id="pvj_conflict_test",
        web_request_id="req_2",
        canonical_user_id="222222",
        product_key="video_ai_prompt",
        tier_id=200,
        scene_count=1,
        output_url="https://storage.googleapis.com/test-bucket/output.mp4",
        validated_output_metadata=meta,
        conn=test_db,
    )
    assert ok2 is False
    assert status2 == 409
    assert res2["error_code"] == "IDEMPOTENCY_CONFLICT"


def test_api_settlement_route_unauthorized_missing_auth():
    """Route rejects unauthenticated requests."""
    from bot import fastapi_app
    client = TestClient(fastapi_app)
    resp = client.post("/internal/v1/web-product-video/settle", json={})
    assert resp.status_code in (401, 503)


def test_api_settlement_route_invalid_signature(monkeypatch):
    """Route rejects invalid HMAC signature."""
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", "test_bridge_token_1234567890")
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", "test_hmac_secret_1234567890")

    from bot import fastapi_app
    client = TestClient(fastapi_app)

    headers = {
        "Authorization": "Bearer test_bridge_token_1234567890",
        "X-Toan-AAS-Signature": "invalid_sig",
        "X-Toan-AAS-Timestamp": str(int(time.time())),
        "X-Toan-AAS-Request-Id": "req_123",
        "X-Toan-AAS-Actor-Id": "888888",
    }
    resp = client.post("/internal/v1/web-product-video/settle", json={"web_job_id": "test"}, headers=headers)
    assert resp.status_code == 401
    err = resp.json().get("error_code") or (resp.json().get("detail", {}) if isinstance(resp.json().get("detail"), dict) else {}).get("error_code")
    assert err == "SIGNATURE_INVALID"


def test_api_settlement_route_valid_auth(monkeypatch, tmp_path):
    """Route accepts signed request and delegates to settlement service."""
    token = "test_bridge_token_1234567890"
    secret = "test_hmac_secret_1234567890"
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", token)
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", secret)

    db_file = str(tmp_path / "test_bot.db")
    monkeypatch.setenv("DB_FILE", db_file)
    import bot
    monkeypatch.setattr(bot, "DB_FILE", db_file)

    conn = sqlite3.connect(db_file, isolation_level=None)
    _init_test_bot_db(conn)
    conn.execute("INSERT INTO users (user_id, credits, total_spent, username) VALUES (888888, 500, 0, 'Customer')")
    conn.close()

    from bot import fastapi_app
    client = TestClient(fastapi_app)

    payload = {
        "web_job_id": "pvj_route_test",
        "web_request_id": "req_route_test",
        "canonical_user_id": "888888",
        "product_key": "video_ai_prompt",
        "tier_id": 200,
        "scene_count": 1,
        "output_url": "https://storage.googleapis.com/test-bucket/output.mp4",
        "validated_output_metadata": {
            "duration_seconds": 5.0,
            "width": 720,
            "height": 1280,
            "file_size_bytes": 10240,
            "format": "mp4",
            "video_codec": "h264",
        },
    }
    body_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ts = str(int(time.time()))
    req_id = str(uuid.uuid4())
    sig = compute_internal_admin_wallet_signature(
        secret=secret,
        timestamp=ts,
        request_id=req_id,
        method="POST",
        path="/internal/v1/web-product-video/settle",
        body_bytes=body_bytes,
        actor_id="888888",
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Toan-AAS-Signature": sig,
        "X-Toan-AAS-Timestamp": ts,
        "X-Toan-AAS-Request-Id": req_id,
        "X-Toan-AAS-Actor-Id": "888888",
        "Content-Type": "application/json",
    }
    resp = client.post("/internal/v1/web-product-video/settle", content=body_bytes, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == "settled"
    assert data["amount_xu"] == 259
    assert data["balance_after"] == 241

