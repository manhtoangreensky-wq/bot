"""Targeted provider-free test suite for Bot Core canonical admin wallet compensation capability.

Validates:
- Source event validation (must exist, must have positive delta, must belong to existing user)
- Server-side derived negative delta (no arbitrary client amount accepted)
- Append-only ledger invariant (source event completely immutable, never updated or deleted)
- Unique source event compensation (one source event compensated at most once)
- Durable idempotency (unique idempotency key, safe replay with 0 second delta, conflict on mismatch)
- Balance safety (insufficient balance rejected, negative resulting balance forbidden)
- Fail-closed auth (Bearer token, HMAC signature, timestamp skew)
- Transactional atomicity (all-or-nothing rollback on ledger failure)
- Unchanged positive-only semantics on existing credit endpoint
- Event 19 simulation test in isolated temporary database
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import time
import pytest
from starlette.testclient import TestClient

from services.admin_wallet_service import (
    ensure_admin_wallet_schema,
    ensure_admin_wallet_compensation_schema,
    compute_compensation_request_fingerprint,
    verify_internal_admin_wallet_auth,
    process_internal_wallet_compensation_in_tx,
    execute_admin_wallet_compensation,
    execute_admin_wallet_credit,
    ALLOWED_COMPENSABLE_EVENT_TYPES,
)
import bot


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
    ensure_admin_wallet_compensation_schema(conn)
    conn.commit()
    return conn


@pytest.fixture
def test_db(tmp_path: Path):
    db_file = tmp_path / "test_bot_core_comp.db"
    conn = create_test_db(db_file)
    conn.execute(
        "INSERT INTO users (user_id, username, credits, total_spent) VALUES ('1001', 'test_user', 500, 0)"
    )
    # Insert a canonical admin credit event (source event)
    conn.execute(
        """INSERT INTO credit_events (id, user_id, delta, balance_after, event_type, ref_id, note, created_at)
        VALUES (19, '1001', 100, 500, 'admin_web_manual_topup', 'Manual topup MANUAL-1 test probe', 'Manual topup MANUAL-1 test probe', '2026-09-16 12:17:15')"""
    )
    conn.commit()
    conn.close()
    return str(db_file)


def make_auth_headers(
    body_bytes: bytes,
    token: str = "secret-token-123",
    hmac_secret: str = "secret-hmac-456",
    path: str = "/internal/v1/admin/wallet/compensate",
    timestamp_offset: int = 0,
    actor_id: str = "admin-tester",
) -> dict[str, str]:
    now_ts = str(int(time.time()) + timestamp_offset)
    req_id = f"req-{int(time.time() * 1000)}"
    digest = hashlib.sha256(body_bytes).hexdigest()
    normalized_path = "/" + path.lstrip("/")
    msg = f"{now_ts}.{req_id}.POST.{normalized_path}.{digest}".encode("utf-8")
    sig = hmac.new(hmac_secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return {
        "Authorization": f"Bearer {token}",
        "X-TOAN-AAS-Signature": sig,
        "X-TOAN-AAS-Timestamp": now_ts,
        "X-TOAN-AAS-Request-ID": req_id,
        "X-TOAN-AAS-Actor-ID": actor_id,
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Section 14: Dedicated Tests
# ---------------------------------------------------------------------------

def test_compensation_requires_existing_positive_source_event(test_db):
    """Source event must exist and have positive delta."""
    # 1. Non-existent source event
    ok, res, status = execute_admin_wallet_compensation(
        source_ledger_event_id=99999,
        idempotency_key="comp-key-nonexistent",
        reason="Test",
        actor_id="admin",
        db_path=test_db,
    )
    assert not ok
    assert status == 404
    assert res["error_code"] == "SOURCE_EVENT_NOT_FOUND"

    # 2. Source event with delta <= 0
    conn = sqlite3.connect(test_db)
    conn.execute(
        "INSERT INTO credit_events (id, user_id, delta, balance_after, event_type, created_at) VALUES (50, '1001', -50, 450, 'video_charge', '2026-09-16 12:00:00')"
    )
    conn.commit()
    conn.close()

    ok2, res2, status2 = execute_admin_wallet_compensation(
        source_ledger_event_id=50,
        idempotency_key="comp-key-negative-source",
        reason="Test",
        actor_id="admin",
        db_path=test_db,
    )
    assert not ok2
    assert status2 == 400
    assert res2["error_code"] == "INVALID_SOURCE_EVENT_DELTA"


def test_compensation_derives_negative_delta_from_source_event(test_db):
    """Server derives negative delta directly from source event (+100 -> -100)."""
    ok, res, status = execute_admin_wallet_compensation(
        source_ledger_event_id=19,
        idempotency_key="comp-key-derived-delta",
        reason="Test compensation",
        actor_id="admin",
        db_path=test_db,
    )
    assert ok
    assert status == 200
    assert res["delta_xu"] == -100
    assert res["balance_after"] == 400

    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute("SELECT credits FROM users WHERE user_id = '1001'")
    assert cur.fetchone()[0] == 400
    conn.close()


def test_compensation_rejects_arbitrary_negative_amount_input(monkeypatch, test_db):
    """HTTP endpoint rejects client attempts to supply arbitrary amount."""
    monkeypatch.setattr(bot, "DB_FILE", test_db)
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", "test-token")
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", "test-secret")

    client = TestClient(bot.fastapi_app)
    body = json.dumps({
        "source_ledger_event_id": 19,
        "idempotency_key": "comp-key-arbitrary-amount",
        "amount_xu": -50,
        "reason": "arbitrary attempt",
        "actor_id": "admin-tester",
    }).encode("utf-8")
    headers = make_auth_headers(body, token="test-token", hmac_secret="test-secret")

    resp = client.post("/internal/v1/admin/wallet/compensate", content=body, headers=headers)
    assert resp.status_code == 400
    data = resp.json()
    assert data["error_code"] == "ARBITRARY_AMOUNT_NOT_PERMITTED"


def test_compensation_appends_new_ledger_event_without_mutating_source(test_db):
    """Source event in credit_events remains strictly immutable; compensation is append-only."""
    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute("SELECT * FROM credit_events WHERE id = 19")
    source_before = cur.fetchone()
    conn.close()

    ok, res, status = execute_admin_wallet_compensation(
        source_ledger_event_id=19,
        idempotency_key="comp-key-immutability",
        reason="Preserve source immutability",
        actor_id="admin",
        db_path=test_db,
    )
    assert ok
    assert status == 200

    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute("SELECT * FROM credit_events WHERE id = 19")
    source_after = cur.fetchone()
    assert source_before == source_after

    cur.execute("SELECT id, user_id, delta, balance_after, event_type, ref_id, note FROM credit_events WHERE id = ?", (res["compensation_ledger_event_id"],))
    comp_row = cur.fetchone()
    assert comp_row is not None
    assert comp_row[2] == -100
    assert comp_row[3] == 400
    assert comp_row[4] == "admin_wallet_compensation"
    assert comp_row[5] == "compensation:event:19"
    conn.close()


def test_compensation_source_event_unique(test_db):
    """One positive source event can be compensated at most once."""
    ok1, res1, status1 = execute_admin_wallet_compensation(
        source_ledger_event_id=19,
        idempotency_key="comp-key-first",
        reason="First compensation",
        actor_id="admin",
        db_path=test_db,
    )
    assert ok1
    assert status1 == 200

    ok2, res2, status2 = execute_admin_wallet_compensation(
        source_ledger_event_id=19,
        idempotency_key="comp-key-second",
        reason="Second compensation attempt",
        actor_id="admin",
        db_path=test_db,
    )
    assert not ok2
    assert status2 == 409
    assert res2["error_code"] == "SOURCE_EVENT_ALREADY_COMPENSATED"


def test_compensation_idempotency_key_unique(test_db):
    """Durable admin_wallet_compensations enforces UNIQUE(idempotency_key)."""
    conn = sqlite3.connect(test_db)
    ensure_admin_wallet_compensation_schema(conn)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO admin_wallet_compensations
        (idempotency_key, source_ledger_event_id, request_fingerprint, user_id, delta_xu, reason, actor_id, compensation_ledger_event_id, balance_after, status, created_at)
        VALUES ('dup-key', 19, 'fp1', '1001', -100, 'r1', 'a1', 101, 400, 'completed', '2026-09-16 12:00:00')"""
    )
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        cur.execute(
            """INSERT INTO admin_wallet_compensations
            (idempotency_key, source_ledger_event_id, request_fingerprint, user_id, delta_xu, reason, actor_id, compensation_ledger_event_id, balance_after, status, created_at)
            VALUES ('dup-key', 20, 'fp2', '1001', -100, 'r2', 'a2', 102, 300, 'completed', '2026-09-16 12:05:00')"""
        )
        conn.commit()
    conn.close()


def test_compensation_safe_replay_second_delta_zero(test_db):
    """Replaying exact same compensation request returns identical receipt and delta = 0."""
    ok1, res1, status1 = execute_admin_wallet_compensation(
        source_ledger_event_id=19,
        idempotency_key="comp-key-replay",
        reason="Replay test",
        actor_id="admin",
        db_path=test_db,
    )
    assert ok1
    assert status1 == 200
    assert not res1["replayed"]
    bal1 = res1["balance_after"]
    comp_id1 = res1["compensation_ledger_event_id"]

    ok2, res2, status2 = execute_admin_wallet_compensation(
        source_ledger_event_id=19,
        idempotency_key="comp-key-replay",
        reason="Replay test",
        actor_id="admin",
        db_path=test_db,
    )
    assert ok2
    assert status2 == 200
    assert res2["replayed"]
    assert res2["balance_after"] == bal1
    assert res2["compensation_ledger_event_id"] == comp_id1

    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute("SELECT credits FROM users WHERE user_id = '1001'")
    assert cur.fetchone()[0] == bal1
    conn.close()


def test_compensation_same_key_different_payload_conflict(test_db):
    """Same idempotency key with different payload returns 409 conflict."""
    ok1, res1, status1 = execute_admin_wallet_compensation(
        source_ledger_event_id=19,
        idempotency_key="comp-key-conflict",
        reason="Original reason",
        actor_id="admin1",
        db_path=test_db,
    )
    assert ok1
    assert status1 == 200

    ok2, res2, status2 = execute_admin_wallet_compensation(
        source_ledger_event_id=19,
        idempotency_key="comp-key-conflict",
        reason="Different reason",
        actor_id="admin2",
        db_path=test_db,
    )
    assert not ok2
    assert status2 == 409
    assert res2["error_code"] == "IDEMPOTENCY_KEY_CONFLICT"


def test_compensation_different_key_same_source_rejected(test_db):
    """Different idempotency key targeting already compensated source event returns 409."""
    ok1, res1, status1 = execute_admin_wallet_compensation(
        source_ledger_event_id=19,
        idempotency_key="comp-key-A",
        reason="First compensation",
        actor_id="admin",
        db_path=test_db,
    )
    assert ok1
    assert status1 == 200

    ok2, res2, status2 = execute_admin_wallet_compensation(
        source_ledger_event_id=19,
        idempotency_key="comp-key-B",
        reason="Second compensation with diff key",
        actor_id="admin",
        db_path=test_db,
    )
    assert not ok2
    assert status2 == 409
    assert res2["error_code"] == "SOURCE_EVENT_ALREADY_COMPENSATED"


def test_compensation_rejects_insufficient_balance(test_db):
    """Compensation fails closed if user balance is lower than source event delta."""
    conn = sqlite3.connect(test_db)
    conn.execute("UPDATE users SET credits = 50 WHERE user_id = '1001'")
    conn.commit()
    conn.close()

    ok, res, status = execute_admin_wallet_compensation(
        source_ledger_event_id=19,
        idempotency_key="comp-key-insufficient",
        reason="Insufficient balance test",
        actor_id="admin",
        db_path=test_db,
    )
    assert not ok
    assert status == 400
    assert res["error_code"] == "INSUFFICIENT_BALANCE"

    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute("SELECT credits FROM users WHERE user_id = '1001'")
    assert cur.fetchone()[0] == 50
    conn.close()


def test_compensation_never_creates_negative_balance(test_db):
    """Compensation never creates a negative resulting balance."""
    conn = sqlite3.connect(test_db)
    conn.execute("UPDATE users SET credits = 0 WHERE user_id = '1001'")
    conn.commit()
    conn.close()

    ok, res, status = execute_admin_wallet_compensation(
        source_ledger_event_id=19,
        idempotency_key="comp-key-zero-bal",
        reason="Zero balance test",
        actor_id="admin",
        db_path=test_db,
    )
    assert not ok
    assert status == 400
    assert res["error_code"] == "INSUFFICIENT_BALANCE"

    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute("SELECT credits FROM users WHERE user_id = '1001'")
    assert cur.fetchone()[0] == 0
    conn.close()


def test_compensation_unknown_user_fails_closed(test_db):
    """If source event user is missing from users table, fail closed."""
    conn = sqlite3.connect(test_db)
    conn.execute("DELETE FROM users WHERE user_id = '1001'")
    conn.commit()
    conn.close()

    ok, res, status = execute_admin_wallet_compensation(
        source_ledger_event_id=19,
        idempotency_key="comp-key-missing-user",
        reason="Missing user test",
        actor_id="admin",
        db_path=test_db,
    )
    assert not ok
    assert status == 404
    assert res["error_code"] == "ACCOUNT_NOT_FOUND"


def test_compensation_auth_missing_zero_delta(monkeypatch, test_db):
    """Missing auth header rejects with 401 and wallet delta is 0."""
    monkeypatch.setattr(bot, "DB_FILE", test_db)
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", "valid-token")
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", "valid-secret")

    client = TestClient(bot.fastapi_app)
    body = json.dumps({
        "source_ledger_event_id": 19,
        "idempotency_key": "comp-key-no-auth",
        "reason": "No auth",
    }).encode("utf-8")

    resp = client.post("/internal/v1/admin/wallet/compensate", content=body)
    assert resp.status_code == 401

    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute("SELECT credits FROM users WHERE user_id = '1001'")
    assert cur.fetchone()[0] == 500
    conn.close()


def test_compensation_bad_bearer_zero_delta(monkeypatch, test_db):
    """Bad bearer token rejects with 401 and wallet delta is 0."""
    monkeypatch.setattr(bot, "DB_FILE", test_db)
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", "valid-token")
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", "valid-secret")

    client = TestClient(bot.fastapi_app)
    body = json.dumps({
        "source_ledger_event_id": 19,
        "idempotency_key": "comp-key-bad-bearer",
        "reason": "Bad bearer",
    }).encode("utf-8")
    headers = make_auth_headers(body, token="wrong-token", hmac_secret="valid-secret")

    resp = client.post("/internal/v1/admin/wallet/compensate", content=body, headers=headers)
    assert resp.status_code == 401

    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute("SELECT credits FROM users WHERE user_id = '1001'")
    assert cur.fetchone()[0] == 500
    conn.close()


def test_compensation_bad_hmac_zero_delta(monkeypatch, test_db):
    """Bad HMAC signature rejects with 401 and wallet delta is 0."""
    monkeypatch.setattr(bot, "DB_FILE", test_db)
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", "valid-token")
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", "valid-secret")

    client = TestClient(bot.fastapi_app)
    body = json.dumps({
        "source_ledger_event_id": 19,
        "idempotency_key": "comp-key-bad-hmac",
        "reason": "Bad HMAC",
    }).encode("utf-8")
    headers = make_auth_headers(body, token="valid-token", hmac_secret="wrong-secret")

    resp = client.post("/internal/v1/admin/wallet/compensate", content=body, headers=headers)
    assert resp.status_code == 401

    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute("SELECT credits FROM users WHERE user_id = '1001'")
    assert cur.fetchone()[0] == 500
    conn.close()


def test_compensation_stale_timestamp_zero_delta(monkeypatch, test_db):
    """Stale timestamp (> 300s skew) rejects with 401 and wallet delta is 0."""
    monkeypatch.setattr(bot, "DB_FILE", test_db)
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", "valid-token")
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", "valid-secret")

    client = TestClient(bot.fastapi_app)
    body = json.dumps({
        "source_ledger_event_id": 19,
        "idempotency_key": "comp-key-stale-ts",
        "reason": "Stale timestamp",
    }).encode("utf-8")
    headers = make_auth_headers(body, token="valid-token", hmac_secret="valid-secret", timestamp_offset=-600)

    resp = client.post("/internal/v1/admin/wallet/compensate", content=body, headers=headers)
    assert resp.status_code == 401

    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute("SELECT credits FROM users WHERE user_id = '1001'")
    assert cur.fetchone()[0] == 500
    conn.close()


def test_compensation_transaction_rollback_on_ledger_failure(monkeypatch, test_db):
    """Ledger write failure triggers full rollback; balance unchanged and no idempotency row created."""
    conn = sqlite3.connect(test_db)
    conn.execute(
        """CREATE TRIGGER fail_comp_insert BEFORE INSERT ON credit_events
        WHEN NEW.event_type = 'admin_wallet_compensation'
        BEGIN
            SELECT RAISE(FAIL, 'simulated ledger disk error');
        END;"""
    )
    conn.commit()
    conn.close()

    ok, res, status = execute_admin_wallet_compensation(
        source_ledger_event_id=19,
        idempotency_key="comp-key-rollback-test",
        reason="Rollback test",
        actor_id="admin",
        db_path=test_db,
    )
    assert not ok
    assert status == 500

    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute("SELECT credits FROM users WHERE user_id = '1001'")
    assert cur.fetchone()[0] == 500

    cur.execute("SELECT COUNT(*) FROM admin_wallet_compensations WHERE idempotency_key = 'comp-key-rollback-test'")
    assert cur.fetchone()[0] == 0
    conn.close()


def test_existing_credit_endpoint_still_rejects_negative_amount(test_db):
    """POST /internal/v1/admin/wallet/credit still rejects amount_xu <= 0."""
    ok, res, status = execute_admin_wallet_credit(
        user_id="1001",
        amount_xu=-100,
        idempotency_key="credit-key-neg-amount",
        reason="Should fail",
        reference="ref",
        actor_id="admin",
        db_path=test_db,
    )
    assert not ok
    assert status == 400
    assert res["error_code"] == "INVALID_AMOUNT"

    ok2, res2, status2 = execute_admin_wallet_credit(
        user_id="1001",
        amount_xu=0,
        idempotency_key="credit-key-zero-amount",
        reason="Should fail",
        reference="ref",
        actor_id="admin",
        db_path=test_db,
    )
    assert not ok2
    assert status2 == 400
    assert res2["error_code"] == "INVALID_AMOUNT"


def test_existing_credit_endpoint_positive_replay_semantics_unchanged(test_db):
    """Existing credit endpoint positive credit and replay semantics remain completely intact."""
    ok1, res1, status1 = execute_admin_wallet_credit(
        user_id="1001",
        amount_xu=50,
        idempotency_key="credit-key-positive-unchanged",
        reason="Topup 50",
        reference="ref50",
        actor_id="admin",
        db_path=test_db,
    )
    assert ok1
    assert status1 == 200
    assert res1["balance_after"] == 550
    assert not res1["replayed"]

    ok2, res2, status2 = execute_admin_wallet_credit(
        user_id="1001",
        amount_xu=50,
        idempotency_key="credit-key-positive-unchanged",
        reason="Topup 50",
        reference="ref50",
        actor_id="admin",
        db_path=test_db,
    )
    assert ok2
    assert status2 == 200
    assert res2["balance_after"] == 550
    assert res2["replayed"]


# ---------------------------------------------------------------------------
# Section 15: Event 19 Simulation Test
# ---------------------------------------------------------------------------

def test_event19_simulation(tmp_path: Path):
    """Simulate Event 19 lifecycle strictly in temporary SQLite database.

    Initial balance: 200
    Source Event 19: +100 -> balance = 300
    Manual-1 Event 20: +100 -> balance = 400
    Compensate Source Event 19: -100 -> balance = 300
    Replay Compensation: balance = 300, second_delta = 0
    """
    sim_db = tmp_path / "sim_event19.db"
    conn = create_test_db(sim_db)
    conn.execute(
        "INSERT INTO users (user_id, username, credits, total_spent) VALUES ('sim-user', 'sim_user', 200, 0)"
    )
    conn.execute(
        """INSERT INTO credit_events (id, user_id, delta, balance_after, event_type, ref_id, note, created_at)
        VALUES (3, 'sim-user', 200, 200, 'trial_grant', '', 'Trial grant 200', '2026-07-18 16:54:47')"""
    )

    # Source Event 19: +100
    conn.execute(
        "UPDATE users SET credits = credits + 100 WHERE user_id = 'sim-user'"
    )
    conn.execute(
        """INSERT INTO credit_events (id, user_id, delta, balance_after, event_type, ref_id, note, created_at)
        VALUES (19, 'sim-user', 100, 300, 'admin_web_manual_topup', 'Manual topup MANUAL-1 test probe', 'Manual topup MANUAL-1 test probe', '2026-09-16 12:17:15')"""
    )

    # Authorized MANUAL-like Event 20: +100
    conn.execute(
        "UPDATE users SET credits = credits + 100 WHERE user_id = 'sim-user'"
    )
    conn.execute(
        """INSERT INTO credit_events (id, user_id, delta, balance_after, event_type, ref_id, note, created_at)
        VALUES (20, 'sim-user', 100, 400, 'admin_web_manual_topup', 'Manual topup MANUAL-1', 'Manual topup MANUAL-1', '2026-09-16 12:33:44')"""
    )
    conn.commit()
    conn.close()

    # Step 1: Compensate source event 19
    ok, res, status = execute_admin_wallet_compensation(
        source_ledger_event_id=19,
        idempotency_key="admin:wallet:compensation:event19:simulation",
        reason="Administrative compensation for unauthorized test probe event 19",
        actor_id="owner-authorized-admin",
        db_path=str(sim_db),
    )
    assert ok
    assert status == 200
    assert res["delta_xu"] == -100
    assert res["balance_after"] == 300
    assert not res["replayed"]

    # Step 2: Replay compensation
    ok_rep, res_rep, status_rep = execute_admin_wallet_compensation(
        source_ledger_event_id=19,
        idempotency_key="admin:wallet:compensation:event19:simulation",
        reason="Administrative compensation for unauthorized test probe event 19",
        actor_id="owner-authorized-admin",
        db_path=str(sim_db),
    )
    assert ok_rep
    assert status_rep == 200
    assert res_rep["replayed"]
    assert res_rep["balance_after"] == 300

    # Step 3: Verify counts and final balance
    conn = sqlite3.connect(str(sim_db))
    cur = conn.cursor()
    cur.execute("SELECT credits FROM users WHERE user_id = 'sim-user'")
    final_balance = cur.fetchone()[0]
    assert final_balance == 300

    cur.execute("SELECT COUNT(*) FROM credit_events WHERE id = 19")
    source_event_count = cur.fetchone()[0]
    assert source_event_count == 1

    cur.execute("SELECT COUNT(*) FROM credit_events WHERE id = 20")
    manual_event_count = cur.fetchone()[0]
    assert manual_event_count == 1

    cur.execute("SELECT COUNT(*) FROM credit_events WHERE event_type = 'admin_wallet_compensation'")
    comp_event_count = cur.fetchone()[0]
    assert comp_event_count == 1

    cur.execute("SELECT actor_id, reason FROM admin_wallet_compensations WHERE source_ledger_event_id = 19")
    rec = cur.fetchone()
    assert rec is not None
    assert rec[0] == "owner-authorized-admin"
    assert rec[1] == "Administrative compensation for unauthorized test probe event 19"
    assert bool(rec[0] and rec[0].strip())
    assert bool(rec[1] and rec[1].strip())

    conn.close()



# ---------------------------------------------------------------------------
# Section 16: Contract Hardening Tests (Actor / Reason / Allowlist Boundaries)
# ---------------------------------------------------------------------------

def test_compensation_missing_reason_fails_closed(monkeypatch, test_db):
    """Missing or blank reason fails closed with 400 MISSING_REASON and wallet delta = 0."""
    monkeypatch.setattr(bot, "DB_FILE", test_db)
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", "test-token")
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", "test-secret")

    client = TestClient(bot.fastapi_app)

    # 1. HTTP endpoint missing reason
    body_missing = json.dumps({
        "source_ledger_event_id": 19,
        "idempotency_key": "comp-key-no-reason",
        "actor_id": "admin-tester",
    }).encode("utf-8")
    headers = make_auth_headers(body_missing, token="test-token", hmac_secret="test-secret", actor_id="admin-tester")
    resp = client.post("/internal/v1/admin/wallet/compensate", content=body_missing, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "MISSING_REASON"

    # 2. HTTP endpoint blank reason
    body_blank = json.dumps({
        "source_ledger_event_id": 19,
        "idempotency_key": "comp-key-blank-reason",
        "reason": "   ",
        "actor_id": "admin-tester",
    }).encode("utf-8")
    headers = make_auth_headers(body_blank, token="test-token", hmac_secret="test-secret", actor_id="admin-tester")
    resp = client.post("/internal/v1/admin/wallet/compensate", content=body_blank, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "MISSING_REASON"

    # 3. Direct service call with empty reason
    ok, res, status = execute_admin_wallet_compensation(
        source_ledger_event_id=19,
        idempotency_key="comp-key-srv-no-reason",
        reason="",
        actor_id="admin-tester",
        db_path=test_db,
    )
    assert not ok
    assert status == 400
    assert res["error_code"] == "MISSING_REASON"

    # 4. Verify wallet balance unchanged and 0 compensations stored
    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute("SELECT credits FROM users WHERE user_id = '1001'")
    assert cur.fetchone()[0] == 500
    cur.execute("SELECT COUNT(*) FROM admin_wallet_compensations")
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT COUNT(*) FROM credit_events WHERE event_type = 'admin_wallet_compensation'")
    assert cur.fetchone()[0] == 0
    conn.close()


def test_compensation_missing_actor_id_fails_closed(monkeypatch, test_db):
    """Missing or blank actor_id fails closed with 400 MISSING_ACTOR_ID and wallet delta = 0."""
    monkeypatch.setattr(bot, "DB_FILE", test_db)
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", "test-token")
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", "test-secret")

    client = TestClient(bot.fastapi_app)

    # 1. HTTP endpoint missing actor_id
    body_missing = json.dumps({
        "source_ledger_event_id": 19,
        "idempotency_key": "comp-key-no-actor",
        "reason": "Valid reason",
    }).encode("utf-8")
    headers = make_auth_headers(body_missing, token="test-token", hmac_secret="test-secret")
    resp = client.post("/internal/v1/admin/wallet/compensate", content=body_missing, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "MISSING_ACTOR_ID"

    # 2. HTTP endpoint blank actor_id
    body_blank = json.dumps({
        "source_ledger_event_id": 19,
        "idempotency_key": "comp-key-blank-actor",
        "reason": "Valid reason",
        "actor_id": "   ",
    }).encode("utf-8")
    headers = make_auth_headers(body_blank, token="test-token", hmac_secret="test-secret")
    resp = client.post("/internal/v1/admin/wallet/compensate", content=body_blank, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "MISSING_ACTOR_ID"

    # 3. Direct service call with empty actor_id
    ok, res, status = execute_admin_wallet_compensation(
        source_ledger_event_id=19,
        idempotency_key="comp-key-srv-no-actor",
        reason="Valid reason",
        actor_id="",
        db_path=test_db,
    )
    assert not ok
    assert status == 400
    assert res["error_code"] == "MISSING_ACTOR_ID"

    # 4. Verify wallet balance unchanged and 0 compensations stored
    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute("SELECT credits FROM users WHERE user_id = '1001'")
    assert cur.fetchone()[0] == 500
    cur.execute("SELECT COUNT(*) FROM admin_wallet_compensations")
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT COUNT(*) FROM credit_events WHERE event_type = 'admin_wallet_compensation'")
    assert cur.fetchone()[0] == 0
    conn.close()


def test_compensation_actor_id_is_bound_to_signed_payload(monkeypatch, test_db):
    """actor_id is cryptographically bound to signed payload; header mismatch is rejected with 400."""
    monkeypatch.setattr(bot, "DB_FILE", test_db)
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", "test-token")
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", "test-secret")

    client = TestClient(bot.fastapi_app)

    # 1. Header actor_id mismatches payload actor_id -> rejected
    body = json.dumps({
        "source_ledger_event_id": 19,
        "idempotency_key": "comp-key-actor-binding-fail",
        "reason": "Audit bound actor",
        "actor_id": "signed-owner-actor",
    }).encode("utf-8")
    headers = make_auth_headers(
        body,
        token="test-token",
        hmac_secret="test-secret",
        actor_id="different-untrusted-actor",
    )
    resp = client.post("/internal/v1/admin/wallet/compensate", content=body, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "ACTOR_ID_MISMATCH"

    # 2. Matching header actor_id -> passes and persists exact signed payload actor_id
    headers_matching = make_auth_headers(
        body,
        token="test-token",
        hmac_secret="test-secret",
        actor_id="signed-owner-actor",
    )
    resp2 = client.post("/internal/v1/admin/wallet/compensate", content=body, headers=headers_matching)
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["ok"] is True

    # 3. Verify durable row has exact signed payload actor_id and reason (Section 8 receipt assertion)
    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute("SELECT actor_id, reason FROM admin_wallet_compensations WHERE idempotency_key = 'comp-key-actor-binding-fail'")
    row = cur.fetchone()
    assert row is not None
    assert row[0] == "signed-owner-actor"
    assert row[1] == "Audit bound actor"
    assert bool(row[0].strip())
    assert bool(row[1].strip())
    conn.close()


def test_compensation_does_not_fallback_to_default_admin_actor(monkeypatch, test_db):
    """Compensation never falls back to ADMIN_ID or DEFAULT_ADMIN_ID when actor_id is missing or explicit."""
    monkeypatch.setattr(bot, "DB_FILE", test_db)
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", "test-token")
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", "test-secret")
    monkeypatch.setenv("ADMIN_ID", "fallback-env-admin")

    client = TestClient(bot.fastapi_app)

    # 1. Omitting actor_id must NOT fall back to fallback-env-admin
    body_missing = json.dumps({
        "source_ledger_event_id": 19,
        "idempotency_key": "comp-key-fallback-attempt",
        "reason": "Testing fallback guard",
    }).encode("utf-8")
    headers = make_auth_headers(body_missing, token="test-token", hmac_secret="test-secret")
    resp = client.post("/internal/v1/admin/wallet/compensate", content=body_missing, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "MISSING_ACTOR_ID"

    # 2. Providing explicit actor_id records explicit actor_id, never fallback-env-admin
    body_explicit = json.dumps({
        "source_ledger_event_id": 19,
        "idempotency_key": "comp-key-explicit-actor",
        "reason": "Explicit actor test",
        "actor_id": "strictly-authorized-actor",
    }).encode("utf-8")
    headers_exp = make_auth_headers(body_explicit, token="test-token", hmac_secret="test-secret", actor_id="strictly-authorized-actor")
    resp2 = client.post("/internal/v1/admin/wallet/compensate", content=body_explicit, headers=headers_exp)
    assert resp2.status_code == 200

    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute("SELECT actor_id FROM admin_wallet_compensations WHERE idempotency_key = 'comp-key-explicit-actor'")
    durable_actor = cur.fetchone()[0]
    assert durable_actor == "strictly-authorized-actor"
    assert durable_actor != "fallback-env-admin"
    assert durable_actor != "admin"
    conn.close()


def test_compensation_does_not_use_reference_as_reason(monkeypatch, test_db):
    """payload['reference'] is NEVER substituted for reason; reason must be explicit."""
    monkeypatch.setattr(bot, "DB_FILE", test_db)
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", "test-token")
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", "test-secret")

    client = TestClient(bot.fastapi_app)

    # 1. Payload with reference but missing reason fails closed
    body = json.dumps({
        "source_ledger_event_id": 19,
        "idempotency_key": "comp-key-ref-as-reason-attempt",
        "reference": "should-not-become-reason",
        "actor_id": "test-admin",
    }).encode("utf-8")
    headers = make_auth_headers(body, token="test-token", hmac_secret="test-secret", actor_id="test-admin")
    resp = client.post("/internal/v1/admin/wallet/compensate", content=body, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "MISSING_REASON"

    # 2. Payload with both explicit reason and reference stores the exact reason
    body_with_both = json.dumps({
        "source_ledger_event_id": 19,
        "idempotency_key": "comp-key-both-ref-and-reason",
        "reference": "some-ref-value",
        "reason": "explicit-audit-reason-string",
        "actor_id": "test-admin",
    }).encode("utf-8")
    headers_both = make_auth_headers(body_with_both, token="test-token", hmac_secret="test-secret", actor_id="test-admin")
    resp2 = client.post("/internal/v1/admin/wallet/compensate", content=body_with_both, headers=headers_both)
    assert resp2.status_code == 200

    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute("SELECT reason FROM admin_wallet_compensations WHERE idempotency_key = 'comp-key-both-ref-and-reason'")
    durable_reason = cur.fetchone()[0]
    assert durable_reason == "explicit-audit-reason-string"
    assert durable_reason != "some-ref-value"
    conn.close()


def test_positive_non_admin_event_is_not_compensable(test_db):
    """Positive source event with non-allowed event_type (e.g. trial_grant) fails closed with 400 NON_COMPENSABLE_EVENT_TYPE."""
    conn = sqlite3.connect(test_db)
    conn.execute(
        """INSERT INTO credit_events (id, user_id, delta, balance_after, event_type, ref_id, note, created_at)
        VALUES (777, '1001', 100, 600, 'trial_grant', 'trial:probe:777', 'Trial grant bonus', '2026-09-16 12:00:00')"""
    )
    conn.execute("UPDATE users SET credits = 600 WHERE user_id = '1001'")
    conn.commit()
    conn.close()

    ok, res, status = execute_admin_wallet_compensation(
        source_ledger_event_id=777,
        idempotency_key="comp-key-trial-grant-target",
        reason="Attempting to compensate trial grant",
        actor_id="admin-auditor",
        db_path=test_db,
    )
    assert not ok
    assert status == 400
    assert res["error_code"] == "NON_COMPENSABLE_EVENT_TYPE"

    # Verify wallet delta = 0
    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute("SELECT credits FROM users WHERE user_id = '1001'")
    assert cur.fetchone()[0] == 600

    # Verify 0 compensation rows
    cur.execute("SELECT COUNT(*) FROM admin_wallet_compensations WHERE source_ledger_event_id = 777")
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT COUNT(*) FROM credit_events WHERE ref_id = 'compensation:event:777'")
    assert cur.fetchone()[0] == 0
    conn.close()


def test_initial_compensable_event_allowlist_is_bounded():
    """Initial compensable event type allowlist is bounded strictly to admin_web_manual_topup."""
    assert ALLOWED_COMPENSABLE_EVENT_TYPES == {"admin_web_manual_topup"}
    assert "admin_wallet_credit" not in ALLOWED_COMPENSABLE_EVENT_TYPES
    assert "manual_deposit" not in ALLOWED_COMPENSABLE_EVENT_TYPES
    assert "admin_add" not in ALLOWED_COMPENSABLE_EVENT_TYPES
    assert "trial_grant" not in ALLOWED_COMPENSABLE_EVENT_TYPES
