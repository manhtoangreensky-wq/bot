import hmac
import hashlib
import os
import tempfile

from fastapi.testclient import TestClient

import bot


def test_env_loader_default(monkeypatch):
    monkeypatch.delenv("TOAN_AAS_TEST_MISSING", raising=False)
    assert bot._env("TOAN_AAS_TEST_MISSING", "fallback") == "fallback"


def test_health_and_runtime_endpoints():
    client = TestClient(bot.fastapi_app)
    assert client.get("/").status_code == 200
    runtime = client.get("/runtime")
    assert runtime.status_code == 200
    assert runtime.json()["service"].startswith("TOAN DAAS")


def test_cost_and_discount_rules():
    assert bot.calculate_dynamic_cost("chat", 0) == 2
    assert bot.calculate_dynamic_cost("download", 0) == 5
    assert bot.apply_discount(0, 100) == (100, 0.0)
    assert bot.apply_discount(5000, 100) == (90, 0.10)
    assert bot.apply_discount(20000, 100) == (80, 0.20)


def test_payos_signature_verification(monkeypatch):
    monkeypatch.setattr(bot, "PAYOS_CHECKSUM_KEY", "checksum-test")
    data = {"orderCode": 123, "amount": 10000, "status": "PAID"}
    raw = "&".join(f"{k}={data[k]}" for k in sorted(data.keys()))
    sig = hmac.new(b"checksum-test", raw.encode("utf-8"), hashlib.sha256).hexdigest()
    assert bot.verify_payos_signature(data, sig)
    assert not bot.verify_payos_signature(data, "bad-signature")


def test_refund_charged_credit_restores_credit_and_total_spent(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    monkeypatch.setattr(bot, "ADMIN_ID", "admin-only")
    try:
        bot.init_db()
        ok, cost, _ = bot.deduct_dynamic_credit("user-1", "download", 0)
        assert ok
        credits_after_spend, spent_after_spend, _ = bot.get_user("user-1")
        assert spent_after_spend == cost

        assert bot.refund_charged_credit("user-1", cost, "refund_test", "", "test", True)
        credits_after_refund, spent_after_refund, _ = bot.get_user("user-1")
        assert credits_after_refund == credits_after_spend + cost
        assert spent_after_refund == 0
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)
