import asyncio
from types import SimpleNamespace

import bot


GENERIC_CUSTOMER_ERROR = "Có lỗi khi xử lý lệnh. Bot chưa trừ Xu. Vui lòng thử lại sau."


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append({"text": text, "kwargs": kwargs})
        return SimpleNamespace()


def _fresh_db(monkeypatch, tmp_path):
    db_path = tmp_path / "p0_finance2c.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    bot.init_db()
    monkeypatch.setattr(bot, "is_admin_user", lambda _user_id: True)
    return db_path


def _run_finance_adjust(args, monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    message = FakeMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=12345), message=message)
    context = SimpleNamespace(args=list(args))
    asyncio.run(bot.cmd_finance_adjust(update, context))
    assert message.replies
    return message.replies[-1]["text"], message.replies[-1]["kwargs"]


def _scalar(sql, params=()):
    conn = bot.db_connect()
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def test_finance_adjust_no_args_shows_help_not_generic_error(monkeypatch, tmp_path):
    text, kwargs = _run_finance_adjust([], monkeypatch, tmp_path)

    assert "Điều chỉnh thuế / tài chính nội bộ" in text
    assert "/finance_adjust vat_add &lt;so_tien_vnd&gt; &lt;ly_do&gt;" in text
    assert "Lệnh này chỉ tạo bút toán điều chỉnh nội bộ" in text
    assert GENERIC_CUSTOMER_ERROR not in text
    assert "Bot chưa trừ Xu" not in text
    assert kwargs["parse_mode"] == "HTML"


def test_finance_adjust_missing_type_shows_allowed_types(monkeypatch, tmp_path):
    text, _kwargs = _run_finance_adjust(["10000", "nopthue"], monkeypatch, tmp_path)

    assert "Thiếu loại bút toán điều chỉnh" in text
    for expected in ("vat_add", "vat_subtract", "cit_add", "cit_subtract", "tax_manual_correction"):
        assert expected in text


def test_finance_adjust_unknown_type_shows_validation_message(monkeypatch, tmp_path):
    text, _kwargs = _run_finance_adjust(["abc", "10000", "ly_do"], monkeypatch, tmp_path)

    assert "Loại bút toán không hợp lệ: abc" in text
    assert "vat_add" in text
    assert "tax_manual_correction" in text


def test_finance_adjust_missing_amount_shows_validation_message(monkeypatch, tmp_path):
    text, _kwargs = _run_finance_adjust(["vat_add"], monkeypatch, tmp_path)

    assert "Thiếu số tiền điều chỉnh" in text
    assert GENERIC_CUSTOMER_ERROR not in text


def test_finance_adjust_invalid_amount_shows_validation_message(monkeypatch, tmp_path):
    text, _kwargs = _run_finance_adjust(["vat_add", "abc", "ly_do"], monkeypatch, tmp_path)

    assert "Số tiền điều chỉnh không hợp lệ. Vui lòng nhập số VND." in text
    assert GENERIC_CUSTOMER_ERROR not in text


def test_finance_adjust_missing_reason_shows_validation_message(monkeypatch, tmp_path):
    text, _kwargs = _run_finance_adjust(["vat_add", "100000"], monkeypatch, tmp_path)

    assert "Thiếu lý do điều chỉnh" in text
    assert GENERIC_CUSTOMER_ERROR not in text


def test_finance_adjust_valid_vat_add_creates_internal_adjustment(monkeypatch, tmp_path):
    text, _kwargs = _run_finance_adjust(["vat_add", "100000", "dieu_chinh_du_phong_vat_thang_6"], monkeypatch, tmp_path)

    assert "Đã ghi bút toán điều chỉnh nội bộ" in text
    assert "Loại: <code>vat_add</code>" in text
    assert "Số tiền: <b>100.000đ</b>" in text
    assert "không sửa giao dịch gốc" in text
    assert "không cộng thêm tiền khách B2C" in text
    assert "không đổi giá nạp Xu/gói/combo" in text
    assert _scalar("SELECT COUNT(*) FROM finance_adjustments WHERE adjustment_type='vat_add' AND amount_vnd=100000") == 1


def test_finance_adjust_valid_cit_subtract_creates_internal_adjustment(monkeypatch, tmp_path):
    text, _kwargs = _run_finance_adjust(["cit_subtract", "50000", "dieu_chinh_lai_du_phong_tndn"], monkeypatch, tmp_path)

    assert "Đã ghi bút toán điều chỉnh nội bộ" in text
    assert "Loại: <code>cit_subtract</code>" in text
    assert _scalar("SELECT COUNT(*) FROM finance_adjustments WHERE adjustment_type='cit_subtract' AND amount_vnd=50000") == 1


def test_finance_adjust_does_not_modify_original_transaction(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    bot.create_order("adjust-safe-order", "customer-1", 100_000, 1_000)
    before = bot.finance_invoice_for_order("adjust-safe-order")

    message = FakeMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=12345), message=message)
    context = SimpleNamespace(args=["tax_manual_correction", "20000", "sua_but_toan_noi_bo"])
    asyncio.run(bot.cmd_finance_adjust(update, context))

    after = bot.finance_invoice_for_order("adjust-safe-order")
    assert after["total_amount_vnd"] == before["total_amount_vnd"]
    assert after["vat_amount_vnd"] == before["vat_amount_vnd"]
    assert after["price_mode"] == before["price_mode"]


def test_finance_adjust_does_not_charge_customer(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    bot.create_order("no-charge-order", "customer-2", 100_000, 1_000)
    before_orders = _scalar("SELECT COUNT(*) FROM payos_orders")

    message = FakeMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=12345), message=message)
    context = SimpleNamespace(args=["vat_add", "100000", "dieu_chinh_vat_test"])
    asyncio.run(bot.cmd_finance_adjust(update, context))

    assert _scalar("SELECT COUNT(*) FROM payos_orders") == before_orders
    assert "không cộng thêm tiền khách" in message.replies[-1]["text"]


def test_finance_adjust_does_not_change_b2c_public_price(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    bot.create_order("b2c-public-price", "customer-3", 100_000, 1_000)
    before = bot.finance_invoice_for_order("b2c-public-price")

    message = FakeMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=12345), message=message)
    context = SimpleNamespace(args=["cit_add", "100000", "du_phong_noi_bo"])
    asyncio.run(bot.cmd_finance_adjust(update, context))

    after = bot.finance_invoice_for_order("b2c-public-price")
    assert before["price_mode"] == bot.B2C_PRICE_MODE
    assert after["total_amount_vnd"] == 100_000
    assert after["vat_amount_vnd"] == 0


def test_finance_adjust_help_uses_placeholders():
    text = bot.finance_adjust_command_help_text()

    assert "&lt;so_tien_vnd&gt;" in text
    assert "&lt;ly_do&gt;" in text
    assert "<so_tien_vnd>" not in text


def test_finance_adjust_100000_only_in_example_section():
    text = bot.finance_adjust_command_help_text()
    before_example, example = text.split("Ví dụ:", 1)

    assert "100000" not in before_example
    assert "/finance_adjust vat_add 100000 dieu_chinh_du_phong_vat_thang_6" in example


def test_finance_adjust_no_generic_customer_error_for_validation_cases(monkeypatch, tmp_path):
    cases = [
        [],
        ["10000", "nopthue"],
        ["10000"],
        ["abc", "10000", "ly_do"],
        ["vat_add"],
        ["vat_add", "abc", "ly_do"],
        ["vat_add", "100000"],
    ]

    for index, args in enumerate(cases):
        text, _kwargs = _run_finance_adjust(args, monkeypatch, tmp_path / f"case_{index}")
        assert "Có lỗi khi xử lý lệnh" not in text
        assert "Bot chưa trừ Xu" not in text


def test_tax_scenario_cit_disabled_label_preserved(monkeypatch):
    monkeypatch.setattr(bot, "finance_tax_config", lambda: {
        "vat_enabled": True,
        "vat_rate": 0.10,
        "vat_mode": "exclusive",
        "cit_enabled": False,
        "cit_rate": 0.20,
    })

    text = bot.finance_tax_scenario_report_text(100_000)
    assert "TNDN scenario 20%: <b>0đ</b> (đang tắt dự phòng)" in text


def test_tax_scenario_cit_enabled_calculates_20_percent():
    payload = bot.finance_tax_scenario_report_payload(100_000, {
        "vat_enabled": True,
        "vat_rate": 0.10,
        "vat_mode": "exclusive",
        "cit_enabled": True,
        "cit_rate": 0.20,
    })

    assert payload["profit_before_cit"] == 20_000
    assert payload["cit_scenario_estimated"] == 4_000
    assert payload["profit_after_cit"] == 16_000
