import json
import os
import tempfile

from fastapi.testclient import TestClient

import bot


def test_payos_standard_webhook_route_exists_and_rejects_invalid_signature(monkeypatch):
    monkeypatch.setattr(bot, "PAYOS_CHECKSUM_KEY", "test-checksum")
    routes = {getattr(route, "path", "") for route in bot.fastapi_app.routes}
    assert "/api/v1/billing/webhook/payos" in routes
    assert "/webhook/payos" in routes

    client = TestClient(bot.fastapi_app)
    response = client.post(
        "/api/v1/billing/webhook/payos",
        json={"success": True, "data": {"orderCode": "123456", "amount": 10000, "status": "PAID"}, "signature": "bad"},
    )
    assert response.status_code == 400


def test_billing_bridge_payload_and_status_hide_token(monkeypatch):
    monkeypatch.setattr(bot, "WEB_BILLING_ENABLED", True)
    monkeypatch.setattr(bot, "WEB_BILLING_APPLY_CONFIRMED", True)
    monkeypatch.setattr(bot, "WEB_BILLING_API_BASE_URL", "https://app.toanaas.vn/api/v1")
    monkeypatch.setattr(bot, "WEB_BILLING_API_TOKEN", "super-secret-token")
    payload = bot.build_web_billing_payment_payload(
        "777",
        "storage_addon",
        "storage_50mb",
        10000,
        {"quota_mb": 50, "days": 30},
    )
    assert payload["source"] == "telegram"
    assert payload["user_id"] == "777"
    assert payload["payment_type"] == "storage_addon"
    assert payload["package_id"] == "storage_50mb"
    assert payload["amount"] == 10000
    assert payload["metadata"]["quota_mb"] == 50
    assert payload["metadata"]["bot"] == "toanaas"
    assert bot.web_billing_checkout_enabled("storage_addon") is True
    status_text = "\n".join(bot.billing_bridge_status_lines())
    assert "super-secret-token" not in status_text
    assert "API token: <code>configured</code>" in status_text


def test_web_billing_checkout_url_key_compatibility():
    assert bot.normalize_billing_checkout_response({"success": True, "checkout_url": "https://pay.example/a"})["checkout_url"] == "https://pay.example/a"
    assert bot.normalize_billing_checkout_response({"code": "00", "data": {"checkoutUrl": "https://pay.example/b", "paymentLinkId": "p1"}})["payment_link_id"] == "p1"


def test_storage_addon_paid_creates_entitlement_event_not_xu(monkeypatch):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(bot, "DB_FILE", db_path)
    try:
        bot.init_db()
        user_id = "bridge-storage-user"
        bot.get_user(user_id, "Storage Bridge")
        before_credits, before_spent, _ = bot.get_user(user_id)
        metadata = {
            "payment_type": "storage_addon",
            "item_id": "50mb",
            "addon_mb": 50,
            "months": 1,
        }
        bot.create_order(
            "930001",
            user_id,
            10000,
            0,
            order_type="storage_addon",
            plan_id="50mb",
            plan_name="+50MB/tháng",
            duration_days=30,
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        )
        _invoice, total = bot.payos_invoice_total_for_order("930001", 10000)
        processed, desc, info = bot.process_payos_paid_order("930001", total)
        assert processed is True
        assert desc == "storage_addon_success"
        assert info["payment_type"] == "storage_addon"
        after_credits, after_spent, _ = bot.get_user(user_id)
        assert after_credits == before_credits
        assert after_spent == before_spent
        conn = bot.db_connect()
        try:
            entitlement = conn.execute("SELECT quota_mb, package_id FROM storage_entitlements WHERE user_id=?", (user_id,)).fetchone()
            event = conn.execute("SELECT event_type, delta_mb FROM storage_events WHERE user_id=?", (user_id,)).fetchone()
            processed_row = conn.execute("SELECT payment_type, apply_status FROM payos_processed WHERE order_code=?", ("930001",)).fetchone()
        finally:
            conn.close()
        assert entitlement == (50, "storage_50mb")
        assert event == ("storage_addon_granted", 50)
        assert processed_row == ("storage_addon", "success")
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)
