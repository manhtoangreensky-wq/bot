import asyncio
from types import SimpleNamespace

import bot


def _labels(markup):
    return [[button.text for button in row] for row in markup.inline_keyboard]


def _callbacks(markup):
    return [[button.callback_data for button in row] for row in markup.inline_keyboard]


class FakeQuery:
    def __init__(self, uid: int, data: str):
        self.data = data
        self.from_user = SimpleNamespace(id=uid, username="tester", first_name="Tester")
        self.message = SimpleNamespace(chat_id=uid)
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


def test_admin_main_menu_compact():
    text = bot.menu_text_admin()
    labels = [label for row in _labels(bot.menu_nav_keyboard("admin", True)) for label in row]

    assert "📊 <b>Quản trị TOAN AAS</b>" in text
    assert "Đây là bảng điều khiển nội bộ" in text
    assert len(labels) <= 12
    assert "/add" not in text
    assert "/pending" not in text
    assert "/queue_status" not in text
    assert "/shopaikey_status" not in text


def test_admin_main_menu_has_grouped_modules():
    rows = _labels(bot.menu_nav_keyboard("admin", True))

    assert ["👤 User / Xu", "💳 Bill / PayOS"] in rows
    assert ["🎁 Gói / Combo", "🧊 Queue / Freeze"] in rows
    assert ["🛡 Bảo mật / DB", "🖥 Hệ thống"] in rows
    assert ["🤖 Provider / Worker", "💰 Tài chính"] in rows
    assert ["🎧 CSKH / Góp ý", "📘 Hướng dẫn Admin"] in rows
    assert ["🏠 Menu chính"] in rows


def test_admin_main_menu_no_giant_command_dump():
    text = bot.menu_text_admin()

    assert len(text) < 700
    assert text.count("<code>/") == 0
    assert "ShopAIKey / Provider" not in text


def test_admin_user_wallet_page_has_purpose_and_commands():
    text = bot.admin_module_page_text("users")

    assert "👤 User / Xu" in text
    assert "Dùng để làm gì?" in text
    assert "Khi nào dùng?" in text
    assert "Thao tác nhanh" in text
    assert "Lệnh chi tiết" in text
    assert "Lưu ý an toàn" in text
    assert "/profile_user &lt;ID&gt;" in text
    assert "/ledger_user &lt;ID&gt;" in text
    assert "/add &lt;ID&gt; &lt;Xu&gt;" in text
    assert "Không dùng /add để thay thế PayOS tự động" in text


def test_admin_user_wallet_buttons_present():
    labels = [label for row in _labels(bot.admin_module_keyboard("users")) for label in row]

    for label in ["🔎 Tra user", "📒 Ledger user", "➕ Cộng Xu", "➖ Trừ Xu", "⭐ Set VIP/Tier", "📘 Hướng dẫn"]:
        assert label in labels


def test_admin_billing_page_has_payos_risk_buttons():
    text = bot.admin_module_page_text("billing")
    labels = [label for row in _labels(bot.admin_module_keyboard("billing")) for label in row]

    assert "💳 Bill / PayOS" in text
    assert "/payos_risk_user &lt;ID&gt;" in text
    assert "/payos_risk_cancel &lt;order&gt;" in text
    assert "🛡 Rủi ro nạp tiền" in labels


def test_admin_billing_page_has_safety_notes():
    text = bot.admin_module_page_text("billing")

    assert "Không duyệt bill nếu chưa đối soát tiền thật" in text
    assert "Không sửa core PayOS" in text
    assert "checksum/token/bank raw data" in text


def test_admin_packages_page_has_guide():
    text = bot.admin_module_page_text("packages")

    assert "🎁 Gói / Combo" in text
    assert "/package_catalog" in text
    assert "/grant_combo &lt;ID&gt; &lt;combo&gt;" in text
    assert "Chỉ cấp gói khi có giao dịch" in text


def test_admin_queue_freeze_page_has_refund_and_lock_guidance():
    text = bot.admin_module_page_text("queue")

    assert "Queue / Freeze / Refund" in text
    assert "/refund_job &lt;job_id&gt;" in text
    assert "/clear_job_lock &lt;job_id&gt;" in text
    assert "Freeze là công cụ chống cháy" in text


def test_admin_security_db_page_has_c4_buttons():
    text = bot.admin_module_page_text("security_db")
    labels = [label for row in _labels(bot.admin_module_keyboard("security_db")) for label in row]

    assert "/db_status" in text
    assert "/backup_db_now" in text
    assert "/security_log" in text
    assert "🗄 DB trạng thái" in labels
    assert "💾 Sao lưu DB" in labels
    assert "🛡 Nhật ký bảo mật" in labels


def test_admin_security_db_page_no_secret_leak():
    text = bot.admin_module_page_text("security_db")

    assert "TELEGRAM_TOKEN" not in text
    assert "PAYOS_CHECKSUM_KEY" not in text
    assert "C:\\Users\\" not in text
    assert "/data/" not in text


def test_admin_system_page_has_runtime_and_telegram_tools():
    text = bot.admin_module_page_text("system_ops")

    assert "/runtime" in text
    assert "/telegram_status" in text
    assert "/telegram_takeover" in text
    assert "Cleanup" in text or "cleanup" in text


def test_admin_provider_worker_page_has_provider_groups():
    text = bot.admin_module_page_text("provider_worker")

    assert "/shopaikey_status" in text
    assert "/key4u_status" in text
    assert "/tool_test_asr" in text
    assert "/tool_test_video_dub" in text


def test_admin_provider_worker_page_warns_about_cost():
    assert "Smoke test có thể tốn provider cost" in bot.admin_module_page_text("provider_worker")


def test_admin_finance_page_has_all_quick_buttons():
    labels = [label for row in _labels(bot.admin_module_keyboard("finance")) for label in row]

    for label in ["📊 Tổng quan", "💵 Doanh thu", "🧾 Chi phí", "📈 Lợi nhuận", "➕ Thêm chi phí", "📤 Xuất báo cáo"]:
        assert label in labels


def test_admin_finance_page_has_usage_guide():
    text = bot.admin_module_page_text("finance")

    assert "/finance_dashboard" in text
    assert "/revenue_report" in text
    assert "/expense_report" in text
    assert "/profit_report" in text
    assert "Số liệu nội bộ" in text


def test_admin_support_page_has_ticket_and_notes():
    text = bot.admin_module_page_text("support")
    labels = [label for row in _labels(bot.admin_module_keyboard("support")) for label in row]

    assert "CSKH / Góp ý / Ticket" in text
    assert "/admin_gopy" in text
    assert "🎧 Ticket admin" in labels
    assert "📌 Admin notes" in labels


def test_admin_handbook_menu_exists():
    text = bot.admin_handbook_menu_text()
    labels = [label for row in _labels(bot.admin_handbook_menu_keyboard()) for label in row]

    assert "📘 <b>Hướng dẫn Admin TOAN AAS</b>" in text
    assert "Quy tắc an toàn khi thao tác Xu" in text
    assert any("Nạp tiền" in label for label in labels)
    assert any("Quyền hạn" in label for label in labels)


def test_admin_handbook_has_payment_refund_freeze_backup_runtime_guides():
    joined = "\n".join(
        bot.admin_handbook_section_text(kind)
        for kind in ["payment", "refund", "freeze", "backup", "runtime", "roles"]
    )

    assert "User gửi bill hoặc PayOS callback" in joined
    assert "/refund_job &lt;job_id&gt;" in joined
    assert "/provider_freeze" in joined
    assert "Không đưa backup lên public/static" in joined
    assert "/telegram_status" in joined
    assert "Owner: toàn quyền" in joined


def test_new_admin_callbacks_route(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", {"999"})
    monkeypatch.setattr(bot, "OWNER_IDS", set())

    for action in [
        "admin_users",
        "admin_billing",
        "admin_packages",
        "admin_queue",
        "admin_security_db",
        "admin_system_ops",
        "admin_provider_worker",
        "admin_finance",
        "admin_support",
        "admin_handbook",
    ]:
        query = FakeQuery(999, f"menu|{action}")
        asyncio.run(bot.handle_menu_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
        assert query.edits, action


def test_old_admin_callbacks_still_route(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "ADMIN_IDS", {"999"})
    monkeypatch.setattr(bot, "OWNER_IDS", set())
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "a1-old-callbacks.db"))
    bot.init_db()

    for action in ["finance", "freeze_queue", "payos_risk", "admin_db_status", "smoke_test", "admin_provider"]:
        query = FakeQuery(999, f"menu|{action}")
        asyncio.run(bot.handle_menu_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
        assert query.edits, action


def test_admin_back_buttons_work():
    callbacks = [callback for row in _callbacks(bot.admin_module_keyboard("billing")) for callback in row]

    assert "menu|admin" in callbacks
    assert "menu|main" in callbacks
    assert "admin_help|payment" in callbacks


def test_public_user_cannot_open_admin_menu(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", {"999"})
    monkeypatch.setattr(bot, "OWNER_IDS", set())
    query = FakeQuery(123, "menu|admin_users")

    asyncio.run(bot.handle_menu_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert not query.edits
    assert query.answers[-1][1].get("show_alert") is True
    assert "Admin" in query.answers[-1][0][0]


def test_public_blocked_from_admin_security_db(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", {"999"})
    monkeypatch.setattr(bot, "OWNER_IDS", set())
    query = FakeQuery(123, "menu|admin_security_db")

    asyncio.run(bot.handle_menu_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert not query.edits
    assert query.answers[-1][1].get("show_alert") is True


def test_admin_handbook_public_blocked(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", {"999"})
    monkeypatch.setattr(bot, "OWNER_IDS", set())
    query = FakeQuery(123, "admin_help|payment")

    asyncio.run(bot.handle_admin_help_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert not query.edits
    assert query.answers[-1][1].get("show_alert") is True
