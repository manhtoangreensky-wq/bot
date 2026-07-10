import hashlib
import hmac
import json
import sqlite3
import time
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from webapp_core_bridge import build_core_bridge_router, confirm_web_link_from_telegram


def make_app(tmp_path, monkeypatch):
    db_path = tmp_path / "bridge.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE users (user_id TEXT PRIMARY KEY, username TEXT, credits INTEGER, total_spent INTEGER, is_vip INTEGER, join_date TEXT);
        INSERT INTO users VALUES ('u-1', 'User', 321, 9, 0, '2026-01-01');
        CREATE TABLE credit_events (id INTEGER PRIMARY KEY, user_id TEXT, delta INTEGER, balance_after INTEGER, event_type TEXT, ref_id TEXT, note TEXT, created_at TEXT);
        INSERT INTO credit_events VALUES (1, 'u-1', 10, 321, 'topup', 'order-1', 'ok', '2026-01-01');
        CREATE TABLE shopaikey_jobs (id INTEGER PRIMARY KEY, user_id TEXT, job_type TEXT, status TEXT, created_at TEXT, updated_at TEXT, xu_cost_planned INTEGER, xu_deducted INTEGER, result_url TEXT);
        INSERT INTO shopaikey_jobs VALUES (1, 'u-1', 'video_single', 'success', '2026-01-01', '2026-01-01', 20, 20, 'https://private.example.invalid/output.mp4');
        CREATE TABLE payos_orders (order_code TEXT PRIMARY KEY, user_id TEXT, amount INTEGER, xu INTEGER, order_type TEXT, status TEXT, created_at TEXT, paid_at TEXT);
        CREATE TABLE feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, username TEXT, category TEXT, content TEXT, context TEXT, status TEXT, timestamp TEXT);
        """
    )
    conn.commit()
    conn.close()

    def db_connect():
        return sqlite3.connect(db_path)

    core = {
        "db_connect": db_connect,
        "is_admin_user": lambda user_id: str(user_id) == "admin-1",
        "engine_readiness_registry": lambda: {"video_single": {"configured": True, "public_ready": True, "reason": "ready", "missing": [], "adapter": "video"}},
    }
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", "test-token")
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", "test-secret")
    monkeypatch.setenv("WEBAPP_PROVIDER_CALLS_ENABLED", "false")
    app = FastAPI()
    app.include_router(build_core_bridge_router(core))
    return TestClient(app)


def signed_headers(method, path, body=b"", actor="u-1", request_id=None):
    request_id = request_id or str(uuid.uuid4())
    timestamp = str(int(time.time()))
    digest = hashlib.sha256(body).hexdigest()
    material = f"{timestamp}.{request_id}.{method}.{path}.{digest}".encode()
    signature = hmac.new(b"test-secret", material, hashlib.sha256).hexdigest()
    return {
        "Authorization": "Bearer test-token",
        "X-TOAN-AAS-Timestamp": timestamp,
        "X-TOAN-AAS-Request-ID": request_id,
        "X-TOAN-AAS-Signature": signature,
        "X-TOAN-AAS-Actor-ID": actor,
        "Content-Type": "application/json",
    }


def test_wallet_jobs_and_feature_draft_are_private_and_canonical(tmp_path, monkeypatch):
    with make_app(tmp_path, monkeypatch) as client:
        wallet = client.get("/internal/v1/wallet?user_id=u-1", headers=signed_headers("GET", "/internal/v1/wallet"))
        assert wallet.status_code == 200
        assert wallet.json()["data"]["balance_xu"] == 321
        jobs = client.get("/internal/v1/jobs?user_id=u-1", headers=signed_headers("GET", "/internal/v1/jobs"))
        assert jobs.json()["data"]["items"][0]["id"] == "shopaikey_jobs:1"
        delivery = client.get("/internal/v1/assets/shopaikey_jobs:1/download?user_id=u-1", headers=signed_headers("GET", "/internal/v1/assets/shopaikey_jobs:1/download"))
        assert delivery.json()["status"] == "guarded"
        assert delivery.json()["error_code"] == "SIGNED_DELIVERY_ADAPTER_REQUIRED"
        assert "private.example.invalid" not in delivery.text
        body = json.dumps({"user_id": "u-1", "input": {"prompt": "x"}}, separators=(",", ":")).encode()
        draft = client.post("/internal/v1/features/video_single/draft", content=body, headers=signed_headers("POST", "/internal/v1/features/video_single/draft", body))
        assert draft.json()["status"] == "draft"


def test_confirm_is_guarded_and_signature_rejects_tampering(tmp_path, monkeypatch):
    with make_app(tmp_path, monkeypatch) as client:
        body = json.dumps({"user_id": "u-1", "input": {}, "idempotency_key": "confirm-bridge-0001"}, separators=(",", ":")).encode()
        confirmed = client.post("/internal/v1/features/video_single/confirm", content=body, headers=signed_headers("POST", "/internal/v1/features/video_single/confirm", body))
        assert confirmed.json()["status"] == "guarded"
        denied = client.get("/internal/v1/wallet?user_id=u-1", headers={"Authorization": "Bearer test-token"})
        assert denied.status_code == 401
        assert denied.json()["ok"] is False
        assert denied.json()["error_code"] == "CORE_BRIDGE_UNAUTHORIZED"


def test_signed_request_id_is_a_one_time_nonce(tmp_path, monkeypatch):
    with make_app(tmp_path, monkeypatch) as client:
        headers = signed_headers("GET", "/internal/v1/wallet", request_id="nonce-replay-test-0001")
        first = client.get("/internal/v1/wallet?user_id=u-1", headers=headers)
        assert first.status_code == 200
        replay = client.get("/internal/v1/wallet?user_id=u-1", headers=headers)
        assert replay.status_code == 409
        assert replay.json()["ok"] is False
        assert replay.json()["error_code"] == "CORE_BRIDGE_REPLAYED_REQUEST"


def test_tickets_are_canonical_and_idempotent(tmp_path, monkeypatch):
    with make_app(tmp_path, monkeypatch) as client:
        body = json.dumps({"user_id": "u-1", "subject": "Need help", "detail": "Ticket from web", "idempotency_key": "ticket-bridge-0001"}, separators=(",", ":")).encode()
        created = client.post("/internal/v1/support/tickets", content=body, headers=signed_headers("POST", "/internal/v1/support/tickets", body))
        assert created.json()["status"] == "queued"
        repeated = client.post("/internal/v1/support/tickets", content=body, headers=signed_headers("POST", "/internal/v1/support/tickets", body))
        assert repeated.json()["data"]["id"] == created.json()["data"]["id"]
        tickets = client.get("/internal/v1/support/tickets?user_id=u-1", headers=signed_headers("GET", "/internal/v1/support/tickets"))
        assert tickets.json()["data"]["items"][0]["subject"] == "Need help"


@pytest.mark.anyio
async def test_telegram_web_link_requires_private_callback_configuration(monkeypatch):
    monkeypatch.delenv("WEBAPP_LINK_CALLBACK_URL", raising=False)
    monkeypatch.delenv("WEBAPP_LINK_CALLBACK_TOKEN", raising=False)
    result = await confirm_web_link_from_telegram({}, "u-1", "LinkCode1234")
    assert result["status"] == "guarded"
    assert result["error_code"] == "TELEGRAM_LINK_CALLBACK_NOT_CONFIGURED"


def test_bot_registers_safe_telegram_link_entrypoints():
    source = (Path(__file__).parents[1] / "bot.py").read_text(encoding="utf-8")
    assert 'CommandHandler("linkweb",     cmd_linkweb)' in source
    assert 'context.args[0]).startswith("web_")' in source
