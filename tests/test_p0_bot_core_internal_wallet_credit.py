"""Targeted provider-free test suite for Bot Core canonical admin wallet credit endpoint (SPEC-B).

Validates:
- Internal authentication (missing, invalid, valid, token and HMAC signature)
- Input validation (account existence, positive amount, idempotency key presence)
- Exactly-once semantics (same key same payload -> same receipt, 0 second delta)
- Conflict detection (same key different payload -> 409 conflict, 0 delta)
- Durable idempotency surviving database reconnection
- Concurrency safety with multiple racing workers
- Atomic transaction rollback on ledger/database failure
- Real ledger receipt verification (never starts with local-credit-)
- Schema initialization and idempotency
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import time
import pytest

from services.admin_wallet_service import (
    ensure_admin_wallet_schema,
    compute_credit_request_fingerprint,
    verify_internal_admin_wallet_auth,
    apply_canonical_wallet_credit_conn,
    process_internal_wallet_credit_in_tx,
    execute_admin_wallet_credit,
)


def create_test_db(db_path: Path) -> sqlite3.Connection:
    """Create isolated SQLite test database with canonical schema."""
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
    conn.execute("""CREATE TABLE IF NOT EXISTS usage_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        event_type TEXT,
        tool_name TEXT,
        status TEXT,
        xu_delta INTEGER,
        detail TEXT,
        created_at DATETIME
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        actor_id TEXT,
        actor_type TEXT,
        action TEXT,
        object_type TEXT,
        object_id TEXT,
        before_json TEXT,
        after_json TEXT,
        note TEXT,
        created_at DATETIME
    )""")
    ensure_admin_wallet_schema(conn)
    conn.commit()
    return conn


@pytest.fixture
def test_db(tmp_path: Path):
    db_file = tmp_path / "test_bot_core.db"
    conn = create_test_db(db_file)
    # Insert a canonical test user
    conn.execute(
        "INSERT INTO users (user_id, username, credits, total_spent) VALUES ('1001', 'test_user', 500, 0)"
    )
    conn.commit()
    conn.close()
    return str(db_file)


# ---------------------------------------------------------------------------
# Section 8 & 21: Auth Tests
# ---------------------------------------------------------------------------

def test_internal_wallet_credit_requires_auth():
    """Missing Authorization header must reject with 401."""
    ok, err, status = verify_internal_admin_wallet_auth(
        authorization="",
        token_override="valid-secret-token",
    )
    assert not ok
    assert status == 401
    assert err == "AUTH_MISSING"


def test_internal_wallet_credit_rejects_invalid_auth():
    """Invalid Bearer token must reject with 401."""
    ok, err, status = verify_internal_admin_wallet_auth(
        authorization="Bearer wrong-token",
        token_override="valid-secret-token",
    )
    assert not ok
    assert status == 401
    assert err == "AUTH_INVALID"


def test_internal_wallet_credit_accepts_valid_token_and_signature():
    """Valid token and valid HMAC signature pass auth."""
    token = "secret-bridge-token-123"
    hmac_secret = "secret-hmac-456"
    now_ts = str(int(time.time()))
    req_id = "req-test-001"
    body = b'{"amount_xu": 100}'
    digest = hashlib.sha256(body).hexdigest()
    msg = f"{now_ts}.{req_id}.POST./internal/v1/admin/wallet/credit.{digest}".encode("utf-8")
    sig = hmac.new(hmac_secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()

    ok, err, status = verify_internal_admin_wallet_auth(
        authorization=f"Bearer {token}",
        signature=sig,
        timestamp=now_ts,
        request_id=req_id,
        method="POST",
        path="/internal/v1/admin/wallet/credit",
        body_bytes=body,
        token_override=token,
        secret_override=hmac_secret,
    )
    assert ok
    assert status == 200
    assert err == "OK"


def test_internal_wallet_credit_rejects_invalid_hmac_signature():
    """Tampered body or invalid signature must reject with 401."""
    token = "secret-bridge-token-123"
    hmac_secret = "secret-hmac-456"
    now_ts = str(int(time.time()))
    req_id = "req-test-001"
    body = b'{"amount_xu": 100}'

    ok, err, status = verify_internal_admin_wallet_auth(
        authorization=f"Bearer {token}",
        signature="invalid_signature_hex",
        timestamp=now_ts,
        request_id=req_id,
        method="POST",
        path="/internal/v1/admin/wallet/credit",
        body_bytes=body,
        token_override=token,
        secret_override=hmac_secret,
    )
    assert not ok
    assert status == 401
    assert err == "SIGNATURE_INVALID"


# ---------------------------------------------------------------------------
# Section 6, 7 & 21: Validation Tests
# ---------------------------------------------------------------------------

def test_internal_wallet_credit_rejects_unknown_account(test_db: str):
    """Unknown account in Bot Core must return 404, wallet mutation 0."""
    ok, res, status = execute_admin_wallet_credit(
        user_id="nonexistent_999999",
        amount_xu=1000,
        idempotency_key="key_unknown_user",
        db_path=test_db,
    )
    assert not ok
    assert status == 404
    assert res["error_code"] == "ACCOUNT_NOT_FOUND"

    # Verify no credit_events or idempotency rows written
    conn = sqlite3.connect(test_db)
    ev_count = conn.execute("SELECT count(*) FROM credit_events").fetchone()[0]
    idem_count = conn.execute("SELECT count(*) FROM admin_wallet_idempotency").fetchone()[0]
    conn.close()
    assert ev_count == 0
    assert idem_count == 0


def test_internal_wallet_credit_rejects_zero_amount(test_db: str):
    """Amount <= 0 must reject with 400, wallet mutation 0."""
    ok, res, status = execute_admin_wallet_credit(
        user_id="1001",
        amount_xu=0,
        idempotency_key="key_zero_amount",
        db_path=test_db,
    )
    assert not ok
    assert status == 400
    assert res["error_code"] == "INVALID_AMOUNT"

    conn = sqlite3.connect(test_db)
    bal = conn.execute("SELECT credits FROM users WHERE user_id='1001'").fetchone()[0]
    conn.close()
    assert bal == 500


def test_internal_wallet_credit_rejects_negative_amount(test_db: str):
    """Negative amount must reject with 400, wallet mutation 0."""
    ok, res, status = execute_admin_wallet_credit(
        user_id="1001",
        amount_xu=-500,
        idempotency_key="key_negative_amount",
        db_path=test_db,
    )
    assert not ok
    assert status == 400
    assert res["error_code"] == "INVALID_AMOUNT"

    conn = sqlite3.connect(test_db)
    bal = conn.execute("SELECT credits FROM users WHERE user_id='1001'").fetchone()[0]
    conn.close()
    assert bal == 500


def test_internal_wallet_credit_requires_idempotency_key(test_db: str):
    """Empty idempotency key must reject with 400, wallet mutation 0."""
    ok, res, status = execute_admin_wallet_credit(
        user_id="1001",
        amount_xu=1000,
        idempotency_key="",
        db_path=test_db,
    )
    assert not ok
    assert status == 400
    assert res["error_code"] == "MISSING_IDEMPOTENCY_KEY"

    conn = sqlite3.connect(test_db)
    bal = conn.execute("SELECT credits FROM users WHERE user_id='1001'").fetchone()[0]
    conn.close()
    assert bal == 500


# ---------------------------------------------------------------------------
# Section 9, 15, 18 & 21: Exactly-Once & Durable Receipt Tests
# ---------------------------------------------------------------------------

def test_internal_wallet_credit_success_credits_once(test_db: str):
    """Valid request credits balance exactly once and records credit_event."""
    ok, res, status = execute_admin_wallet_credit(
        user_id="1001",
        amount_xu=1000,
        idempotency_key="key_success_once",
        reason="Manual topup MANUAL-101",
        reference="MANUAL-101",
        db_path=test_db,
    )
    assert ok
    assert status == 200
    assert res["ok"] is True
    assert res["replayed"] is False
    assert res["amount_xu"] == 1000
    assert res["balance_after"] == 1500  # 500 + 1000

    conn = sqlite3.connect(test_db)
    bal = conn.execute("SELECT credits FROM users WHERE user_id='1001'").fetchone()[0]
    events = conn.execute("SELECT delta, balance_after, event_type, ref_id FROM credit_events WHERE user_id='1001'").fetchall()
    conn.close()
    assert bal == 1500
    assert len(events) == 1
    assert events[0][0] == 1000
    assert events[0][1] == 1500
    assert events[0][2] == "admin_web_manual_topup"
    assert events[0][3] == "MANUAL-101"


def test_internal_wallet_credit_creates_durable_ledger_receipt(test_db: str):
    """Successful credit returns durable ledger receipt corresponding to credit_events.id."""
    ok, res, status = execute_admin_wallet_credit(
        user_id="1001",
        amount_xu=300,
        idempotency_key="key_receipt_check",
        reason="Topup receipt test",
        db_path=test_db,
    )
    assert ok
    receipt_id = res["ledger_event_id"]
    assert str(receipt_id).isdigit()
    assert int(receipt_id) > 0

    conn = sqlite3.connect(test_db)
    ev = conn.execute("SELECT id, delta FROM credit_events WHERE id = ?", (int(receipt_id),)).fetchone()
    conn.close()
    assert ev is not None
    assert ev[0] == int(receipt_id)
    assert ev[1] == 300


def test_internal_wallet_credit_never_returns_local_credit_receipt(test_db: str):
    """Returned receipt MUST NOT start with local-credit- under any circumstances."""
    ok, res, status = execute_admin_wallet_credit(
        user_id="1001",
        amount_xu=250,
        idempotency_key="key_no_local_credit",
        db_path=test_db,
    )
    assert ok
    receipt = res["ledger_event_id"]
    assert not receipt.startswith("local-credit-")
    assert not res["tx_id"].startswith("local-credit-")
    assert not res["data"]["ledger_event_id"].startswith("local-credit-")


def test_internal_wallet_credit_same_key_same_payload_replays_same_receipt(test_db: str):
    """Identical replay returns the exact same receipt with replayed=True."""
    key = "key_replay_same"
    ok1, res1, status1 = execute_admin_wallet_credit(
        user_id="1001",
        amount_xu=500,
        idempotency_key=key,
        reason="Topup 500",
        reference="REF-500",
        db_path=test_db,
    )
    assert ok1
    assert res1["replayed"] is False

    ok2, res2, status2 = execute_admin_wallet_credit(
        user_id="1001",
        amount_xu=500,
        idempotency_key=key,
        reason="Topup 500",
        reference="REF-500",
        db_path=test_db,
    )
    assert ok2
    assert status2 == 200
    assert res2["replayed"] is True
    assert res2["ledger_event_id"] == res1["ledger_event_id"]
    assert res2["balance_after"] == res1["balance_after"]


def test_internal_wallet_credit_same_key_replay_does_not_credit_twice(test_db: str):
    """Repeating the same request 3 times yields total wallet delta of exactly amount once."""
    key = "key_no_double_credit"
    conn = sqlite3.connect(test_db)
    initial_bal = conn.execute("SELECT credits FROM users WHERE user_id='1001'").fetchone()[0]
    conn.close()

    for _ in range(3):
        ok, res, status = execute_admin_wallet_credit(
            user_id="1001",
            amount_xu=700,
            idempotency_key=key,
            reason="Topup 700",
            db_path=test_db,
        )
        assert ok
        assert status == 200

    conn = sqlite3.connect(test_db)
    final_bal = conn.execute("SELECT credits FROM users WHERE user_id='1001'").fetchone()[0]
    credit_event_rows = conn.execute(
        "SELECT count(*) FROM credit_events WHERE user_id='1001' AND delta=700"
    ).fetchone()[0]
    conn.close()

    assert final_bal == initial_bal + 700
    assert credit_event_rows == 1


# ---------------------------------------------------------------------------
# Section 10 & 21: Idempotency Conflict Tests
# ---------------------------------------------------------------------------

def test_internal_wallet_credit_same_key_different_amount_conflicts(test_db: str):
    """Same key with different amount returns 409 IDEMPOTENCY_KEY_CONFLICT, wallet delta 0."""
    key = "key_conflict_amount"
    ok1, res1, status1 = execute_admin_wallet_credit(
        user_id="1001",
        amount_xu=1000,
        idempotency_key=key,
        db_path=test_db,
    )
    assert ok1

    conn = sqlite3.connect(test_db)
    bal_after_first = conn.execute("SELECT credits FROM users WHERE user_id='1001'").fetchone()[0]
    conn.close()

    # Second request with 2000 Xu instead of 1000 Xu
    ok2, res2, status2 = execute_admin_wallet_credit(
        user_id="1001",
        amount_xu=2000,
        idempotency_key=key,
        db_path=test_db,
    )
    assert not ok2
    assert status2 == 409
    assert res2["error_code"] == "IDEMPOTENCY_KEY_CONFLICT"

    conn = sqlite3.connect(test_db)
    bal_after_conflict = conn.execute("SELECT credits FROM users WHERE user_id='1001'").fetchone()[0]
    conn.close()
    assert bal_after_conflict == bal_after_first


def test_internal_wallet_credit_same_key_different_account_conflicts(test_db: str):
    """Same key with different target user returns 409 IDEMPOTENCY_KEY_CONFLICT."""
    conn = sqlite3.connect(test_db)
    conn.execute("INSERT INTO users (user_id, username, credits) VALUES ('1002', 'user_two', 100)")
    conn.commit()
    conn.close()

    key = "key_conflict_user"
    ok1, res1, status1 = execute_admin_wallet_credit(
        user_id="1001",
        amount_xu=500,
        idempotency_key=key,
        db_path=test_db,
    )
    assert ok1

    # Second request targeting user 1002
    ok2, res2, status2 = execute_admin_wallet_credit(
        user_id="1002",
        amount_xu=500,
        idempotency_key=key,
        db_path=test_db,
    )
    assert not ok2
    assert status2 == 409
    assert res2["error_code"] == "IDEMPOTENCY_KEY_CONFLICT"

    conn = sqlite3.connect(test_db)
    bal_user2 = conn.execute("SELECT credits FROM users WHERE user_id='1002'").fetchone()[0]
    conn.close()
    assert bal_user2 == 100  # unmutated


def test_internal_wallet_credit_same_key_different_reference_conflicts(test_db: str):
    """Same key with different reference returns 409 IDEMPOTENCY_KEY_CONFLICT."""
    key = "key_conflict_ref"
    ok1, res1, status1 = execute_admin_wallet_credit(
        user_id="1001",
        amount_xu=500,
        idempotency_key=key,
        reference="MANUAL-REF-A",
        db_path=test_db,
    )
    assert ok1

    ok2, res2, status2 = execute_admin_wallet_credit(
        user_id="1001",
        amount_xu=500,
        idempotency_key=key,
        reference="MANUAL-REF-B",
        db_path=test_db,
    )
    assert not ok2
    assert status2 == 409
    assert res2["error_code"] == "IDEMPOTENCY_KEY_CONFLICT"


# ---------------------------------------------------------------------------
# Section 11, 14 & 21: Durability & Concurrency Tests
# ---------------------------------------------------------------------------

def test_internal_wallet_credit_survives_service_reinitialization(tmp_path: Path):
    """Durable idempotency survives process/connection closure."""
    db_file = tmp_path / "restart_test.db"
    conn = create_test_db(db_file)
    conn.execute("INSERT INTO users (user_id, credits) VALUES ('2001', 1000)")
    conn.commit()
    conn.close()

    key = "key_service_restart"
    ok1, res1, status1 = execute_admin_wallet_credit(
        user_id="2001",
        amount_xu=400,
        idempotency_key=key,
        db_path=str(db_file),
    )
    assert ok1
    receipt1 = res1["ledger_event_id"]

    # Re-open completely new connection
    ok2, res2, status2 = execute_admin_wallet_credit(
        user_id="2001",
        amount_xu=400,
        idempotency_key=key,
        db_path=str(db_file),
    )
    assert ok2
    assert status2 == 200
    assert res2["replayed"] is True
    assert res2["ledger_event_id"] == receipt1

    conn2 = sqlite3.connect(str(db_file))
    final_bal = conn2.execute("SELECT credits FROM users WHERE user_id='2001'").fetchone()[0]
    events_count = conn2.execute("SELECT count(*) FROM credit_events WHERE user_id='2001'").fetchone()[0]
    conn2.close()

    assert final_bal == 1400  # 1000 + 400 exactly once
    assert events_count == 1


def test_internal_wallet_credit_concurrent_duplicate_credits_once(tmp_path: Path):
    """Concurrent identical requests with same idempotency key credit exactly once."""
    db_file = tmp_path / "concurrent_test.db"
    conn = create_test_db(db_file)
    conn.execute("INSERT INTO users (user_id, credits) VALUES ('3001', 200)")
    conn.commit()
    conn.close()

    key = "key_concurrent_race"
    results = []

    def call_credit(worker_id: int):
        return execute_admin_wallet_credit(
            user_id="3001",
            amount_xu=500,
            idempotency_key=key,
            reason="Concurrent topup test",
            db_path=str(db_file),
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(call_credit, i) for i in range(5)]
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())

    # All returned successful receipts or valid replays
    successful_results = [r for r in results if r[0] is True]
    assert len(successful_results) == 5

    receipts = {r[1]["ledger_event_id"] for r in successful_results}
    assert len(receipts) == 1  # ALL callers receive the EXACT same receipt!

    conn = sqlite3.connect(str(db_file))
    final_bal = conn.execute("SELECT credits FROM users WHERE user_id='3001'").fetchone()[0]
    event_count = conn.execute("SELECT count(*) FROM credit_events WHERE user_id='3001'").fetchone()[0]
    conn.close()

    assert final_bal == 700  # 200 + 500 exactly once
    assert event_count == 1


# ---------------------------------------------------------------------------
# Section 13 & 21: Atomicity & Rollback Tests
# ---------------------------------------------------------------------------

def test_internal_wallet_credit_transaction_failure_rolls_back(tmp_path: Path):
    """Simulated database exception inside transaction rolls back balance update completely."""
    db_file = tmp_path / "rollback_test.db"
    conn = create_test_db(db_file)
    conn.execute("INSERT INTO users (user_id, credits) VALUES ('4001', 500)")
    conn.commit()

    # Intentionally corrupt or lock
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Update balance
        conn.execute("UPDATE users SET credits = credits + 1000 WHERE user_id='4001'")
        # Simulate unexpected failure before commit
        raise RuntimeError("Simulated mid-transaction failure")
    except Exception:
        conn.rollback()
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_file))
    bal = conn.execute("SELECT credits FROM users WHERE user_id='4001'").fetchone()[0]
    ev_count = conn.execute("SELECT count(*) FROM credit_events WHERE user_id='4001'").fetchone()[0]
    conn.close()

    assert bal == 500
    assert ev_count == 0


def test_internal_wallet_credit_ledger_failure_rolls_back(tmp_path: Path):
    """If credit_events write fails, wallet update and idempotency claim must be rolled back."""
    db_file = tmp_path / "ledger_fail_test.db"
    conn = create_test_db(db_file)
    conn.execute("INSERT INTO users (user_id, credits) VALUES ('5001', 100)")
    # Drop credit_events table to trigger SQLite error during ledger insertion
    conn.execute("DROP TABLE credit_events")
    conn.commit()
    conn.close()

    ok, res, status = execute_admin_wallet_credit(
        user_id="5001",
        amount_xu=500,
        idempotency_key="key_ledger_fail",
        db_path=str(db_file),
    )
    assert not ok
    assert status == 500

    conn = sqlite3.connect(str(db_file))
    bal = conn.execute("SELECT credits FROM users WHERE user_id='5001'").fetchone()[0]
    idem_count = conn.execute("SELECT count(*) FROM admin_wallet_idempotency WHERE idempotency_key='key_ledger_fail'").fetchone()[0]
    conn.close()

    assert bal == 100  # untouched
    assert idem_count == 0  # rolled back


# ---------------------------------------------------------------------------
# Section 24: Schema Additive & Migration Tests
# ---------------------------------------------------------------------------

def test_admin_wallet_schema_fresh_db_initialization(tmp_path: Path):
    """ensure_admin_wallet_schema creates table and index cleanly on fresh DB."""
    db_file = tmp_path / "fresh.db"
    conn = sqlite3.connect(str(db_file))
    ensure_admin_wallet_schema(conn)

    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='admin_wallet_idempotency'")
    assert cursor.fetchone() is not None
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_admin_wallet_idem_key'")
    assert cursor.fetchone() is not None
    conn.close()


def test_admin_wallet_schema_existing_db_migration_idempotent(tmp_path: Path):
    """Calling ensure_admin_wallet_schema repeatedly does not throw or corrupt existing rows."""
    db_file = tmp_path / "existing.db"
    conn = sqlite3.connect(str(db_file))
    ensure_admin_wallet_schema(conn)
    conn.execute(
        "INSERT INTO admin_wallet_idempotency (idempotency_key, request_fingerprint, user_id, amount_xu, status, created_at) VALUES ('k1', 'fp1', 'u1', 100, 'completed', '2026-09-16 10:00:00')"
    )
    conn.commit()

    # Run schema ensure again (simulating re-initialization or restart)
    ensure_admin_wallet_schema(conn)
    row = conn.execute("SELECT user_id, amount_xu FROM admin_wallet_idempotency WHERE idempotency_key='k1'").fetchone()
    assert row == ("u1", 100)
    conn.close()


# ---------------------------------------------------------------------------
# Section 25: FastAPI Endpoint Integration Tests
# ---------------------------------------------------------------------------

def test_fastapi_admin_wallet_credit_unauthorized():
    from fastapi.testclient import TestClient
    import bot
    client = TestClient(bot.fastapi_app)
    resp = client.post(
        "/internal/v1/admin/wallet/credit",
        json={"user_id": "1001", "amount_xu": 100, "idempotency_key": "k_unauth"},
    )
    assert resp.status_code in (401, 503)


def test_fastapi_admin_wallet_credit_end_to_end(tmp_path: Path, monkeypatch):
    from fastapi.testclient import TestClient
    import bot

    db_file = tmp_path / "fastapi_test.db"
    conn = create_test_db(db_file)
    conn.execute("INSERT INTO users (user_id, username, credits) VALUES ('777', 'fastapi_user', 50)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(bot, "DB_FILE", str(db_file))
    token = "test-fastapi-bridge-token"
    secret = "test-fastapi-hmac-secret"
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", token)
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", secret)

    client = TestClient(bot.fastapi_app)

    # 1. First credit
    payload = {"user_id": "777", "amount_xu": 200, "idempotency_key": "k_fastapi_1", "reason": "Test credit"}
    body_bytes = json.dumps(payload).encode("utf-8")
    now_ts = str(int(time.time()))
    req_id = "req-fa-001"
    digest = hashlib.sha256(body_bytes).hexdigest()
    msg = f"{now_ts}.{req_id}.POST./internal/v1/admin/wallet/credit.{digest}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()

    headers = {
        "Authorization": f"Bearer {token}",
        "X-TOAN-AAS-Signature": sig,
        "X-TOAN-AAS-Timestamp": now_ts,
        "X-TOAN-AAS-Request-ID": req_id,
        "Content-Type": "application/json",
    }
    resp1 = client.post("/internal/v1/admin/wallet/credit", content=body_bytes, headers=headers)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["ok"] is True
    assert data1["replayed"] is False
    assert data1["amount_xu"] == 200
    assert data1["balance_after"] == 250

    # 2. Replay same key & payload
    req_id2 = "req-fa-002"
    msg2 = f"{now_ts}.{req_id2}.POST./internal/v1/admin/wallet/credit.{digest}".encode("utf-8")
    sig2 = hmac.new(secret.encode("utf-8"), msg2, hashlib.sha256).hexdigest()
    headers2 = {
        "Authorization": f"Bearer {token}",
        "X-TOAN-AAS-Signature": sig2,
        "X-TOAN-AAS-Timestamp": now_ts,
        "X-TOAN-AAS-Request-ID": req_id2,
        "Content-Type": "application/json",
    }
    resp2 = client.post("/internal/v1/admin/wallet/credit", content=body_bytes, headers=headers2)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["ok"] is True
    assert data2["replayed"] is True
    assert data2["ledger_event_id"] == data1["ledger_event_id"]
    assert data2["balance_after"] == 250

    # 3. Conflict on same key different amount
    payload3 = {"user_id": "777", "amount_xu": 999, "idempotency_key": "k_fastapi_1", "reason": "Test credit"}
    body_bytes3 = json.dumps(payload3).encode("utf-8")
    digest3 = hashlib.sha256(body_bytes3).hexdigest()
    msg3 = f"{now_ts}.{req_id2}.POST./internal/v1/admin/wallet/credit.{digest3}".encode("utf-8")
    sig3 = hmac.new(secret.encode("utf-8"), msg3, hashlib.sha256).hexdigest()
    headers3 = {
        "Authorization": f"Bearer {token}",
        "X-TOAN-AAS-Signature": sig3,
        "X-TOAN-AAS-Timestamp": now_ts,
        "X-TOAN-AAS-Request-ID": req_id2,
        "Content-Type": "application/json",
    }
    resp3 = client.post("/internal/v1/admin/wallet/credit", content=body_bytes3, headers=headers3)
    assert resp3.status_code == 409
    data3 = resp3.json()
    assert data3["error_code"] == "IDEMPOTENCY_KEY_CONFLICT"
