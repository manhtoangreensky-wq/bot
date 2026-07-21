import inspect
import json

import bot


def _fresh_db(monkeypatch, tmp_path):
    db_path = tmp_path / "p0_finance2a2b.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    bot.init_db()
    return db_path


def _scenario_config(cit_enabled=True):
    return {
        "vat_enabled": True,
        "vat_rate": 0.10,
        "vat_mode": "exclusive",
        "cit_enabled": cit_enabled,
        "cit_rate": 0.20,
    }


def test_tax_scenario_cit_20_percent_calculates_amount():
    payload = bot.finance_tax_scenario_report_payload(100_000, _scenario_config(True))

    assert payload["profit_before_cit"] == 20_000
    assert payload["cit_rate_scenario"] == 0.20
    assert payload["cit_scenario_enabled"] is True
    assert payload["cit_scenario_estimated"] == 4_000


def test_tax_scenario_after_cit_profit_subtracts_cit():
    payload = bot.finance_tax_scenario_report_payload(100_000, _scenario_config(True))

    assert payload["profit_after_cit"] == 16_000
    assert payload["profit_after_cit"] == payload["profit_before_cit"] - payload["cit_scenario_estimated"]


def test_tax_scenario_cit_disabled_labels_disabled_not_zero_confusing():
    payload = bot.finance_tax_scenario_report_payload(100_000, _scenario_config(False))
    text = bot.finance_tax_scenario_report_text(100_000)

    disabled_text = "\n".join([
        "• TNDN scenario 20%: <b>0đ</b> (đang tắt dự phòng)",
    ])
    rendered_disabled = bot.finance_tax_scenario_report_payload(100_000, _scenario_config(False))

    assert payload["cit_rate_scenario"] == 0.20
    assert payload["cit_scenario_enabled"] is False
    assert payload["cit_scenario_estimated"] == 0
    assert payload["profit_after_cit"] == 20_000
    assert rendered_disabled["profit_after_cit"] == rendered_disabled["profit_before_cit"]

    original_config = bot.finance_tax_config
    try:
        bot.finance_tax_config = lambda: _scenario_config(False)
        text = bot.finance_tax_scenario_report_text(100_000)
    finally:
        bot.finance_tax_config = original_config
    assert disabled_text in text


def test_cit_never_added_to_public_customer_price(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    bot.create_order("cit-public", "cit-user", 100_000, 1_000)
    invoice = bot.finance_invoice_for_order("cit-public")
    scenario = bot.finance_tax_scenario_report_payload(100_000, _scenario_config(True))

    assert scenario["public_total"] == 100_000
    assert scenario["customer_vat_surcharge"] == 0
    assert invoice["total_amount_vnd"] == 100_000
    assert "cit_amount_vnd" not in invoice


def test_b2c_gross_fixed_price_unchanged(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    bot.create_order("b2c-gross", "b2c-user", 100_000, 1_000)
    invoice = bot.finance_invoice_for_order("b2c-gross")

    assert invoice["price_mode"] == bot.B2C_PRICE_MODE
    assert invoice["subtotal_amount_vnd"] == 100_000
    assert invoice["vat_amount_vnd"] == 0
    assert invoice["total_amount_vnd"] == 100_000


def test_b2b_net_plus_vat_unchanged(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    metadata_json = json.dumps({"customer_type": "business", "invoice_required": True})
    bot.create_order("b2b-vat", "b2b-user", 100_000, 1_000, metadata_json=metadata_json)
    invoice = bot.finance_invoice_for_order("b2b-vat")

    assert invoice["price_mode"] == bot.B2B_PRICE_MODE
    assert invoice["subtotal_amount_vnd"] == 100_000
    assert invoice["vat_amount_vnd"] == 8_000
    assert invoice["total_amount_vnd"] == 108_000


def test_finance_adjust_help_uses_placeholders_not_raw_100000():
    text = bot.finance_adjustment_help_text("vat")
    before_example = text.split("Ví dụ:", 1)[0]

    assert "/finance_adjust vat_add &lt;so_tien_vnd&gt; &lt;ly_do&gt;" in text
    assert "/finance_adjust vat_subtract &lt;so_tien_vnd&gt; &lt;ly_do&gt;" in text
    assert "100000" not in before_example


def test_finance_adjust_help_explains_amount_is_internal_adjustment():
    text = bot.finance_adjustment_help_text("cit")

    assert "<so_tien_vnd> là số tiền bút toán điều chỉnh nội bộ" in text
    assert "không phải thuế suất" in text
    assert "không phải số tiền tự động cộng cho khách" in text


def test_finance_adjust_help_says_not_customer_charge():
    text = bot.finance_adjustment_help_text("vat")
    command_source = inspect.getsource(bot.cmd_finance_adjust)

    for content in (text, command_source):
        assert "không sửa giao dịch gốc" in content
        assert "không cộng thêm tiền khách B2C" in content
        assert "không đổi giá nạp Xu/gói/combo" in content


def test_finance_adjust_help_mentions_vat_rate_and_cit_rate_for_rates():
    text = bot.finance_adjustment_help_text("cit")
    command_source = inspect.getsource(bot.cmd_finance_adjust)

    assert "/vat_rate" in text
    assert "/cit_rate" in text
    assert "/vat_rate" in command_source
    assert "/cit_rate" in command_source


def test_finance_adjust_example_keeps_100000_only_in_example_section():
    text = bot.finance_adjustment_help_text("vat")
    before_example, example = text.split("Ví dụ:", 1)

    assert "100000" not in before_example
    assert "/finance_adjust vat_add 100000 dieu_chinh_du_phong_vat_thang_6" in example
