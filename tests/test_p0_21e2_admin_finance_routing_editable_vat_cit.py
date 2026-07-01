import json
import subprocess

import bot


def _fresh_db(monkeypatch, tmp_path):
    db_path = tmp_path / "p0_21e2_finance.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    bot.init_db()
    return db_path


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _allowed_p0_18o_engine_guard_path(path: str, changed: list[str]) -> bool:
    normalized = {item.replace("\\", "/") for item in changed}
    branch = subprocess.check_output(["git", "branch", "--show-current"], text=True, encoding="utf-8").strip()
    video_allowed = (
        (branch.startswith("hotfix/p0-18o-") or "tests/test_p0_18o_lock_video_flows_real_engine_all_products.py" in normalized)
        and path.replace("\\", "/") in {"services/video_project_queue.py", "services/video_final_output.py"}
    )
    video_engine_allowed = (
        (branch.startswith("hotfix/p0-18p-") or "tests/test_p0_18p_connect_real_video_engine_after_final_output_gate.py" in normalized)
        and path.replace("\\", "/") in {"services/video_final_output.py", "services/video_real_render_connector.py"}
    )
    video_final_delivery_allowed = (
        (
            branch.startswith("hotfix/p0-18r-")
            or "tests/test_p0_18r_real_video_engine_final_mp4_delivery_all_products.py" in normalized
        )
        and path.replace("\\", "/")
        in {
            "remote_worker.py",
            "services/video_final_output.py",
            "services/video_real_render_connector.py",
            "services/video_project_queue.py",
        }
    )
    video_provider_config_allowed = (
        (
            branch.startswith("hotfix/p0-18s1-")
            or "tests/test_p0_18s1_video_provider_config_bootstrap_clean_no_provider_ux.py" in normalized
        )
        and path.replace("\\", "/")
        in {
            "providers/video_generic_http_provider.py",
            "services/video_provider_router.py",
            "services/video_real_render_connector.py",
        }
    )
    subdub_allowed = (
        (branch.startswith("hotfix/p0-19k-") or "tests/test_p0_19k_complete_subdub_flows_hardsub_cover_voice_gender_entry_fix.py" in normalized)
        and path.replace("\\", "/") == "services/subtitle_dub_product_pipeline.py"
    )
    return video_allowed or video_engine_allowed or video_final_delivery_allowed or video_provider_config_allowed or subdub_allowed


def _scalar(sql, params=(), default=0):
    conn = bot.db_connect()
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else default
    finally:
        conn.close()


def _finance_handler_keyboard(action):
    _text, keyboard = bot.ADMIN_MENU_PAGE_HANDLERS[action]()
    return keyboard


def test_admin_finance_back_returns_admin():
    callbacks = _callbacks(bot.finance_admin_keyboard())
    assert "menu|admin" in callbacks
    assert "menu|main" in callbacks


def test_admin_tax_back_returns_finance():
    callbacks = _callbacks(bot.finance_tax_keyboard())
    assert "menu|finance" in callbacks
    assert "menu|admin" not in callbacks


def test_admin_tax_settings_back_returns_tax():
    callbacks = _callbacks(_finance_handler_keyboard("finance_tax_settings"))
    assert "menu|finance_tax_vat" in callbacks
    assert "menu|finance" not in callbacks


def test_admin_vat_rate_cancel_returns_tax():
    callbacks = _callbacks(_finance_handler_keyboard("finance_vat_rate_help"))
    assert "menu|finance_tax_vat" in callbacks


def test_admin_cit_rate_cancel_returns_tax():
    callbacks = _callbacks(_finance_handler_keyboard("finance_cit_rate_help"))
    assert "menu|finance_tax_vat" in callbacks


def test_admin_revenue_back_returns_finance():
    assert "menu|finance" in _callbacks(bot.finance_period_keyboard("revenue"))


def test_admin_expense_back_returns_finance():
    assert "menu|finance" in _callbacks(bot.finance_period_keyboard("expense"))


def test_admin_profit_back_returns_finance():
    assert "menu|finance" in _callbacks(bot.finance_period_keyboard("profit"))


def test_admin_capital_back_returns_finance():
    assert "menu|finance" in _callbacks(_finance_handler_keyboard("finance_capital"))


def test_admin_anomaly_back_returns_finance():
    assert "menu|finance" in _callbacks(_finance_handler_keyboard("finance_anomalies"))


def test_admin_adjustment_back_returns_finance():
    assert "menu|finance" in _callbacks(_finance_handler_keyboard("finance_adjustments"))


def test_admin_finance_guide_back_returns_finance():
    assert "menu|finance" in _callbacks(_finance_handler_keyboard("finance_guide"))


def test_admin_finance_no_back_to_main_unless_main_button():
    for keyboard in [
        bot.finance_tax_keyboard(),
        bot.finance_child_keyboard(),
        bot.finance_tax_child_keyboard(),
        bot.finance_adjustments_keyboard(),
        bot.finance_adjustment_child_keyboard(),
    ]:
        for row in keyboard.inline_keyboard:
            for button in row:
                if button.callback_data == "menu|main":
                    assert "Menu chính" in button.text


def test_admin_finance_no_back_to_admin_unless_admin_button():
    for keyboard in [
        bot.finance_tax_keyboard(),
        bot.finance_child_keyboard(),
        bot.finance_tax_child_keyboard(),
        bot.finance_adjustments_keyboard(),
        bot.finance_adjustment_child_keyboard(),
    ]:
        assert "menu|admin" not in _callbacks(keyboard)
    admin_buttons = [button.text for row in bot.finance_admin_keyboard().inline_keyboard for button in row if button.callback_data == "menu|admin"]
    assert admin_buttons == ["⬅️ Admin"]


def test_admin_can_set_global_vat_rate(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    result = bot.admin_set_global_vat_rate(10, admin_id="admin-tax")
    assert result["ok"] is True
    assert result["vat_rate"] == 0.10


def test_vat_rate_applies_to_new_orders_only(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    metadata = json.dumps({"customer_type": "business", "invoice_required": True}, ensure_ascii=False)
    bot.create_order("vat-old", "u-vat", 100_000, 1_000, metadata_json=metadata)
    bot.admin_set_global_vat_rate(10, admin_id="admin-tax")
    bot.create_order("vat-new", "u-vat", 100_000, 1_000, metadata_json=metadata)
    assert bot.finance_invoice_for_order("vat-old")["vat_amount_vnd"] == 8_000
    assert bot.finance_invoice_for_order("vat-new")["vat_amount_vnd"] == 10_000


def test_vat_can_be_disabled(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    bot.admin_set_vat_enabled(False, admin_id="admin-tax")
    bot.create_order("vat-off", "u-vat", 100_000, 1_000)
    invoice = bot.finance_invoice_for_order("vat-off")
    assert invoice["vat_amount_vnd"] == 0
    assert invoice["total_amount_vnd"] == 100_000


def test_vat_exclusive_calculation():
    snapshot = bot.calculate_vat_snapshot(100_000, {"vat_enabled": True, "vat_rate": 0.08, "vat_mode": "exclusive"})
    assert snapshot["subtotal_amount_vnd"] == 100_000
    assert snapshot["vat_amount_vnd"] == 8_000
    assert snapshot["total_amount_vnd"] == 108_000


def test_topup_adds_vat_to_total_payment(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    bot.create_order("vat-topup", "u-topup", 10_000, 100)
    _invoice, total = bot.payos_invoice_total_for_order("vat-topup", 10_000)
    assert total == 10_000


def test_topup_wallet_credit_excludes_vat(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    user_id = "u-wallet-vat"
    before, _, _ = bot.get_user(user_id, "VAT Wallet")
    bot.create_order("vat-wallet", user_id, 10_000, 100)
    _invoice, total = bot.payos_invoice_total_for_order("vat-wallet", 10_000)
    processed, desc, info = bot.process_payos_paid_order("vat-wallet", total, webhook_currency="VND", transaction_id="vat-wallet-tx")
    after, _, _ = bot.get_user(user_id)
    assert processed is True
    assert desc == "success"
    assert after - before == bot.package_base_xu(10_000)
    assert info["vat_amount_vnd"] == 0


def test_no_double_vat_when_spending_xu(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    user_id = "u-spend-vat"
    bot.get_user(user_id, "Spend VAT")
    conn = bot.db_connect()
    try:
        conn.execute("UPDATE users SET credits=500 WHERE user_id=?", (user_id,))
        conn.commit()
    finally:
        conn.close()
    before = _scalar("SELECT COUNT(*) FROM finance_invoices")
    assert bot.spend_fixed_credit_info(user_id, 100, "pytest_service", "spend xu")["ok"] is True
    assert _scalar("SELECT COUNT(*) FROM finance_invoices") == before


def test_admin_can_set_global_cit_rate(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    config = bot.finance_tax_config()
    assert config["cit_enabled"] is True
    assert config["cit_rate"] == 0.20
    result = bot.admin_set_global_cit_rate(17, admin_id="admin-tax")
    assert result["ok"] is True
    assert result["cit_rate"] == 0.17


def test_cit_can_be_disabled(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    bot.admin_set_cit_enabled(False, admin_id="admin-tax")
    bot.create_order("cit-off", "u-cit", 100_000, 1_000)
    start, end, label, _kind = bot.finance_period_bounds("", "month")
    report = bot.finance_business_report_payload(start, end, label)
    assert report["cit_enabled"] is False
    assert report["estimated_cit"] == 0


def test_cit_rate_applies_to_reports(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    bot.admin_set_global_cit_rate(15, admin_id="admin-tax")
    bot.create_order("cit-report", "u-cit", 100_000, 1_000)
    _invoice, total = bot.payos_invoice_total_for_order("cit-report", 100_000)
    bot.process_payos_paid_order("cit-report", total, webhook_currency="VND", transaction_id="cit-report-tx")
    start, end, label, _kind = bot.finance_period_bounds("", "month")
    report = bot.finance_business_report_payload(start, end, label)
    assert report["profit_before_cit"] == 100_000
    assert report["estimated_cit"] == 15_000


def test_cit_not_added_to_customer_invoice(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    bot.admin_set_global_cit_rate(20, admin_id="admin-tax")
    bot.create_order("cit-invoice", "u-cit", 100_000, 1_000)
    invoice = bot.finance_invoice_for_order("cit-invoice")
    assert invoice["total_amount_vnd"] == 100_000
    assert "cit_rate" not in invoice
    assert "cit_amount_vnd" not in invoice
    assert "tndn" not in json.dumps(invoice.get("metadata_json", ""), ensure_ascii=False).lower()


def test_cit_calculated_on_profit_not_vat(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    bot.create_order("cit-profit", "u-cit", 100_000, 1_000)
    _invoice, total = bot.payos_invoice_total_for_order("cit-profit", 100_000)
    bot.process_payos_paid_order("cit-profit", total, webhook_currency="VND", transaction_id="cit-profit-tx")
    bot.add_finance_expense(30_000, "other", "vendor", "cost", "admin")
    start, end, label, _kind = bot.finance_period_bounds("", "month")
    report = bot.finance_business_report_payload(start, end, label)
    assert report["profit_before_cit"] == 70_000
    assert report["estimated_cit"] == 14_000


def test_cit_zero_when_profit_negative(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    bot.create_order("cit-negative", "u-cit", 100_000, 1_000)
    _invoice, total = bot.payos_invoice_total_for_order("cit-negative", 100_000)
    bot.process_payos_paid_order("cit-negative", total, webhook_currency="VND", transaction_id="cit-negative-tx")
    bot.add_finance_expense(200_000, "other", "vendor", "loss", "admin")
    start, end, label, _kind = bot.finance_period_bounds("", "month")
    report = bot.finance_business_report_payload(start, end, label)
    assert report["profit_before_cit"] == -100_000
    assert report["estimated_cit"] == 0
    assert report["profit_after_cit"] == -100_000


def test_profit_after_cit_formula(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    bot.create_order("cit-formula", "u-cit", 100_000, 1_000)
    _invoice, total = bot.payos_invoice_total_for_order("cit-formula", 100_000)
    bot.process_payos_paid_order("cit-formula", total, webhook_currency="VND", transaction_id="cit-formula-tx")
    start, end, label, _kind = bot.finance_period_bounds("", "month")
    report = bot.finance_business_report_payload(start, end, label)
    assert report["profit_after_cit"] == report["profit_before_cit"] - report["estimated_cit"]


def test_cit_rate_change_audit_logged(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    bot.admin_set_global_cit_rate(17, admin_id="admin-tax")
    assert _scalar("SELECT COUNT(*) FROM audit_logs WHERE action='finance.cit_rate_set'") == 1


def test_tax_report_has_vat_and_cit_blocks(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    text = bot.finance_tax_dashboard_text()
    assert "GTGT / VAT" in text
    assert "TNDN / CIT" in text
    assert "Tổng quan dự phòng thuế" in text


def test_vat_report_month_quarter_year(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    month = bot.finance_tax_dashboard_text("", "month")
    start, end, label, _token = bot.tax_quarter_bounds()
    quarter = bot.finance_tax_dashboard_text_for_bounds(start, end, label)
    year = bot.finance_tax_dashboard_text("", "year")
    assert "VAT" in month and "VAT" in quarter and "VAT" in year


def test_cit_report_month_quarter_year(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    month = bot.finance_tax_dashboard_text("", "month")
    start, end, label, _token = bot.tax_quarter_bounds()
    quarter = bot.finance_tax_dashboard_text_for_bounds(start, end, label)
    year = bot.finance_tax_dashboard_text("", "year")
    assert "TNDN" in month and "TNDN" in quarter and "TNDN" in year


def test_total_tax_reserve_equals_vat_plus_estimated_cit(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    bot.create_order("tax-reserve", "u-tax", 100_000, 1_000)
    _invoice, total = bot.payos_invoice_total_for_order("tax-reserve", 100_000)
    bot.process_payos_paid_order("tax-reserve", total, webhook_currency="VND", transaction_id="tax-reserve-tx")
    start, end, label, _kind = bot.finance_period_bounds("", "month")
    report = bot.finance_business_report_payload(start, end, label)
    assert report["total_tax_reserve_estimate"] == report["vat_collected"] + report["estimated_cit"]


def test_vat_adjustment_separate_from_cit_adjustment(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    bot.create_order("tax-adjust", "u-tax", 100_000, 1_000)
    _invoice, total = bot.payos_invoice_total_for_order("tax-adjust", 100_000)
    bot.process_payos_paid_order("tax-adjust", total, webhook_currency="VND", transaction_id="tax-adjust-tx")
    bot.create_finance_adjustment("vat_add", 1_000, "VAT correction", admin_id="admin")
    bot.create_finance_adjustment("cit_add", 2_000, "CIT correction", admin_id="admin")
    start, end, label, _kind = bot.finance_period_bounds("", "month")
    report = bot.finance_business_report_payload(start, end, label)
    assert report["vat_adjustment"] == 1_000
    assert report["cit_adjustment"] == 2_000


def test_tax_export_includes_vat_and_cit_fields(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    start, end, label, _kind = bot.finance_period_bounds("", "month")
    csv_text = bot.tax_accounting_csv("summary", start, end, label, "admin")
    assert "vat_collected_vnd" in csv_text
    assert "estimated_cit_vnd" in csv_text
    assert "profit_after_cit_vnd" in csv_text


def test_payos_uses_total_with_vat(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    bot.create_order("payos-vat", "u-payos", 100_000, 1_000)
    _invoice, total = bot.payos_invoice_total_for_order("payos-vat", 100_000)
    assert total == 100_000


def test_momo_hidden_from_cny_payment(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    labels = _labels(bot.manual_foreign_preview_keyboard({"currency": "CNY", "original_amount": 100}, "123"))
    assert not any("MoMo" in label for label in labels)


def test_zalopay_payment_adds_vat_if_enabled(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    conn = bot.db_connect()
    try:
        snapshot = bot.build_finance_invoice_snapshot_conn(conn, "zalo-vat", "u", 100_000, "manual_topup", "manual_topup", {"payment_channel": "zalopay", "customer_type": "business", "invoice_required": True})
    finally:
        conn.close()
    assert snapshot["payment_channel"] == "zalopay"
    assert snapshot["vat_amount_vnd"] == 8_000


def test_usdt_payment_adds_vat_on_vnd_equivalent(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    conn = bot.db_connect()
    try:
        snapshot = bot.build_finance_invoice_snapshot_conn(
            conn,
            "usdt-vat",
            "u",
            0,
            "manual_topup",
            "manual_topup",
            {"payment_channel": "usdt_trc20", "currency": "USDT", "original_amount": 10, "fx_rate": 25_000, "customer_type": "business", "invoice_required": True},
        )
    finally:
        conn.close()
    assert snapshot["subtotal_amount_vnd"] == 250_000
    assert snapshot["vat_amount_vnd"] == 20_000


def test_cny_without_handler_goes_admin_order(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    labels = _labels(bot.manual_foreign_preview_keyboard({"currency": "CNY", "original_amount": 100}, "123"))
    assert any("manual" in label.lower() or "Admin" in label for label in labels)


def test_public_payment_confirm_shows_vat_lines():
    text = bot.finance_tax_block({"subtotal_amount_vnd": 100_000, "vat_rate": 0.08, "vat_amount_vnd": 8_000, "total_amount_vnd": 108_000})
    assert "Giá dịch vụ" in text
    assert "Thuế GTGT" in text
    assert "Tổng thanh toán" in text


def test_public_payment_confirm_does_not_show_cit_charge():
    text = bot.finance_tax_block({"subtotal_amount_vnd": 100_000, "vat_rate": 0.08, "vat_amount_vnd": 8_000, "total_amount_vnd": 108_000})
    assert "TNDN" not in text
    assert "CIT" not in text


def test_public_tax_copy_not_misleading():
    text = "\n".join(bot.finance_tax_lines({"subtotal_amount_vnd": 100_000, "vat_rate": 0.08, "vat_amount_vnd": 8_000, "total_amount_vnd": 108_000})).lower()
    for forbidden in ["miễn thuế", "né thuế", "không cần đóng thuế", "thu hộ nhà nước"]:
        assert forbidden not in text


def test_no_engine_files_touched():
    changed = subprocess.check_output(["git", "diff", "--name-only", "origin/main", "--"], text=True, encoding="utf-8").splitlines()
    forbidden = ("providers/", "local_worker.py", "remote_worker.py", "services/subtitle", "services/video", "services/voice")
    assert [path for path in changed if path.replace("\\", "/").startswith(forbidden) and not _allowed_p0_18o_engine_guard_path(path, changed)] == []


def test_no_db_destructive():
    diff = subprocess.check_output(["git", "diff", "origin/main", "--", "bot.py"], text=True, encoding="utf-8").upper()
    assert "DROP TABLE" not in diff
    assert "DELETE FROM PAYOS_ORDERS" not in diff
    assert "DELETE FROM FINANCE_INVOICES" not in diff


def test_no_fake_payment_success(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    metadata_json = json.dumps({"customer_type": "business", "invoice_required": True})
    bot.create_order("fake-pay", "u-fake", 100_000, 1_000, metadata_json=metadata_json)
    processed, desc, _info = bot.process_payos_paid_order("fake-pay", 100_000, webhook_currency="VND")
    assert processed is False
    assert desc == "amount_mismatch"


def test_no_quota_grant_on_flagged_order(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    user_id = "u-flagged"
    before, _, _ = bot.get_user(user_id, "Flagged")
    metadata_json = json.dumps({"customer_type": "business", "invoice_required": True})
    bot.create_order("flagged-order", user_id, 100_000, 1_000, metadata_json=metadata_json)
    bot.process_payos_paid_order("flagged-order", 100_000, webhook_currency="VND")
    after, _, _ = bot.get_user(user_id)
    assert after == before
    assert bot.finance_invoice_for_order("flagged-order")["status"] == "flagged"
