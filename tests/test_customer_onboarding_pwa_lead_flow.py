import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

import bot


def repo_root() -> Path:
    return Path(bot.__file__).resolve().parent


def onboarding_html() -> str:
    return (repo_root() / "onboarding.html").read_text(encoding="utf-8")


def bot_source_text() -> str:
    return (repo_root() / "bot.py").read_text(encoding="utf-8")


def source_between(source: str, start_marker: str, end_marker: str) -> str:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def configure_temp_db(monkeypatch, tmp_path, full_init=False) -> Path:
    db_path = tmp_path / "customer_onboarding.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "DB_STARTUP_BACKUP_ENABLED", False)
    monkeypatch.setattr(bot, "DB_MIGRATION_DRY_RUN", False)
    monkeypatch.setattr(bot, "DATA_PERSISTENCE_MODE", "sqlite")
    monkeypatch.setattr(bot, "DATABASE_URL", "")
    monkeypatch.setattr(bot, "DATA_PERSISTENCE_WARNINGS", [])
    monkeypatch.setattr(bot, "DB_STARTUP_PREP_RESULT", {"status": "not_run", "path": "", "created_at": "", "reason": ""})
    monkeypatch.setattr(bot, "DB_STARTUP_BACKUP_RESULT", {"status": "not_run", "path": "", "created_at": "", "reason": ""})
    if full_init:
        bot.init_db()
    return db_path


def accepted_lead_payload(ref_code="AFF_2026"):
    return {
        "name": "Nguyen Van A",
        "contact": "lead@example.com",
        "telegram_username": "@toanlead",
        "need_type": "Tạo video bán hàng",
        "industry": "mỹ phẩm",
        "note": "Cần video bán hàng có voice và phụ đề.",
        "ref_code": ref_code,
        "source_url": "https://app.toanaas.vn/onboarding?ref=AFF_2026",
        "terms_accepted": True,
        "privacy_accepted": True,
        "terms_accepted_at": "2026-06-23T00:00:00.000Z",
        "privacy_accepted_at": "2026-06-23T00:00:00.000Z",
        "notification_permission": "granted",
    }


def test_onboarding_page_exists():
    client = TestClient(bot.fastapi_app)
    response = client.get("/onboarding")
    assert response.status_code == 200
    assert "TOAN AAS — AI Automation System" in response.text
    assert "Customer onboarding V1" in response.text
    assert 'rel="manifest"' in response.text
    assert client.get("/app").status_code == 200
    assert client.get("/welcome").status_code == 200
    assert client.get("/manifest.webmanifest").status_code == 200
    assert client.get("/sw.js").status_code == 200


def test_add_to_home_screen_guide_contains_ios_android():
    html = onboarding_html()
    assert "iPhone Safari" in html
    assert "Mở Safari vào app.toanaas.vn" in html
    assert "Thêm vào Màn hình chính" in html
    assert "Android Chrome" in html
    assert "Mở Chrome vào app.toanaas.vn" in html
    assert "Thêm vào màn hình chính" in html


def test_notification_opt_in_copy():
    html = onboarding_html()
    assert "Bật thông báo để nhận kết quả khi ảnh/video/voice tạo xong" in html
    assert "Notification.requestPermission" in html
    assert "Bạn vẫn có thể nhận kết quả qua Telegram bot" in html


def test_terms_acceptance_required(monkeypatch, tmp_path):
    configure_temp_db(monkeypatch, tmp_path)
    client = TestClient(bot.fastapi_app)
    payload = accepted_lead_payload()
    payload["terms_accepted"] = False
    response = client.post("/api/customer-leads", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "terms_required"
    html = onboarding_html()
    assert "Bạn cần đồng ý điều khoản để sử dụng dịch vụ TOAN AAS." in html
    for link in ["/legal", "/privacy", "/dieukhoan_xu", "/refund_policy"]:
        assert link in html
    assert "Sở hữu trí tuệ" in html


def test_lead_form_fields():
    html = onboarding_html()
    for text in [
        "Họ tên",
        "Số điện thoại hoặc email",
        "Telegram username",
        "Bạn muốn dùng TOAN AAS để làm gì?",
        "Tạo video bán hàng",
        "Tạo video TikTok/Reels",
        "Affiliate",
        "Tạo ảnh sản phẩm",
        "Tạo voice/lồng tiếng",
        "Phụ đề/dịch video",
        "Tài liệu/PDF",
        "Ngành nghề",
        "Ghi chú nhu cầu",
        "Ref code",
        "🎁 Nhận mã dùng thử",
    ]:
        assert text in html


def test_lead_table_create_if_not_exists():
    conn = sqlite3.connect(":memory:")
    try:
        bot.ensure_customer_leads_table(conn)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(customer_leads)").fetchall()}
        assert {
            "id",
            "created_at",
            "name",
            "contact",
            "telegram_username",
            "telegram_user_id",
            "need_type",
            "industry",
            "note",
            "ref_code",
            "source_url",
            "status",
            "assigned_admin_id",
            "promo_code",
            "terms_accepted_at",
            "privacy_accepted_at",
            "user_agent",
        }.issubset(columns)
    finally:
        conn.close()


def test_lead_submission_stores_ref_code(monkeypatch, tmp_path):
    db_path = configure_temp_db(monkeypatch, tmp_path)
    client = TestClient(bot.fastapi_app)
    response = client.post("/api/customer-leads", json=accepted_lead_payload("bad ref!ABC_123-xyz"))
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["promo_code"] is None
    assert data["telegram_handoff_url"].endswith("?start=ref_badrefABC_123-xyz")
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT ref_code, status, promo_code FROM customer_leads WHERE id=?", (data["lead_id"],)).fetchone()
        assert row == ("badrefABC_123-xyz", "new", "")
    finally:
        conn.close()


def test_lead_submission_notifies_admin(monkeypatch, tmp_path):
    configure_temp_db(monkeypatch, tmp_path)
    sent = []

    class FakeBot:
        async def send_message(self, **kwargs):
            sent.append(kwargs)

    class FakeApp:
        bot = FakeBot()

    monkeypatch.setattr(bot, "tg_app", FakeApp())
    monkeypatch.setattr(bot, "ADMIN_ID", "7126457028")
    client = TestClient(bot.fastapi_app)
    response = client.post("/api/customer-leads", json=accepted_lead_payload())
    assert response.status_code == 200
    assert response.json()["admin_notified"] is True
    assert sent
    assert "📥 <b>Lead mới TOAN AAS" in sent[0]["text"]
    assert "Tạo video bán hàng" in sent[0]["text"]
    callbacks = [button.callback_data for row in sent[0]["reply_markup"].inline_keyboard for button in row]
    assert any(callback.startswith("lead|promo|") and callback.endswith("|200") for callback in callbacks)
    assert any(callback.startswith("lead|contacted|") for callback in callbacks)


def test_admin_lead_actions_admin_only():
    source = bot_source_text()
    assert 'CommandHandler("leads", admin_internal_command(cmd_customer_leads))' in source
    assert 'CommandHandler("lead", admin_internal_command(cmd_customer_lead_detail))' in source
    assert 'CommandHandler("lead_contacted", admin_internal_command(cmd_customer_lead_contacted))' in source
    assert 'CommandHandler("lead_promo", admin_internal_command(cmd_customer_lead_promo))' in source
    assert 'CommandHandler("lead_reject", admin_internal_command(cmd_customer_lead_reject))' in source
    callback_source = source_between(source, "async def handle_customer_lead_callback", "class OperatorTaskCompleteRequest")
    assert "is_admin_user(query.from_user.id)" in callback_source


def test_promo_request_does_not_auto_credit_without_admin(monkeypatch, tmp_path):
    db_path = configure_temp_db(monkeypatch, tmp_path, full_init=True)
    client = TestClient(bot.fastapi_app)
    response = client.post("/api/customer-leads", json=accepted_lead_payload())
    assert response.status_code == 200
    lead_id = response.json()["lead_id"]
    conn = sqlite3.connect(db_path)
    try:
        lead_row = conn.execute("SELECT promo_code, status FROM customer_leads WHERE id=?", (lead_id,)).fetchone()
        assert lead_row == ("", "new")
        assert conn.execute("SELECT COUNT(*) FROM gift_redemptions").fetchone()[0] == 0
    finally:
        conn.close()

    ok, status, lead = bot.create_customer_lead_promo_code(lead_id, 200, "admin-test")
    assert ok is True
    assert status == "created"
    assert str(lead["promo_code"]).startswith("LEAD")
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM gift_redemptions").fetchone()[0] == 0
        assert conn.execute("SELECT status FROM customer_leads WHERE id=?", (lead_id,)).fetchone()[0] == "promo_sent"
    finally:
        conn.close()


def test_pricing_mapping_1_xu_100_vnd():
    pricing = bot.customer_onboarding_pricing_payload()
    assert pricing["unit"] == "1 Xu = 100đ"
    topups = {(item["xu"], item["vnd"]) for item in pricing["topups"]}
    assert {(200, 20000), (300, 30000), (400, 40000), (600, 60000), (1000, 100000)}.issubset(topups)
    html = onboarding_html()
    assert "1 Xu = 100đ" in html
    assert "200 Xu — 20.000đ" in html
    assert "300 Xu — 30.000đ" in html
    assert "400 Xu — 40.000đ" in html


def test_pricing_does_not_use_20000_credit_confusion():
    text = onboarding_html().lower()
    assert "20k credit" not in text
    assert "20000 credit" not in text
    assert "20.000 credit" not in text


def test_telegram_handoff_link_contains_ref():
    assert bot.customer_onboarding_telegram_link("AFF-abc_123") == "https://t.me/toanaasbot?start=ref_AFF-abc_123"
    assert bot.customer_onboarding_telegram_link("", 42) == "https://t.me/toanaasbot?start=ref_lead_42"


def test_no_payos_wallet_changes():
    source = bot_source_text()
    onboarding_source = source_between(source, "class CustomerLeadRequest", "class OperatorTaskCompleteRequest")
    forbidden = ["payos_orders", "pending_deposits", "wallet", "payment webhook", "UPDATE users SET credits"]
    assert not any(item.lower() in onboarding_source.lower() for item in forbidden)
    assert "redeem_gift_code(" not in onboarding_source
