import json
import subprocess

import bot


def _fresh_db(monkeypatch, tmp_path):
    db_path = tmp_path / "p0_21e_finance.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    bot.init_db()
    return db_path


def _rows(sql, params=()):
    conn = bot.db_connect()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _scalar(sql, params=(), default=0):
    rows = _rows(sql, params)
    return rows[0][0] if rows else default


def _allowed_p0_18o_engine_guard_path(path: str, changed: list[str]) -> bool:
    normalized = {item.replace("\\", "/") for item in changed}
    branch = subprocess.check_output(["git", "branch", "--show-current"], text=True, encoding="utf-8").strip()
    return (
        (branch.startswith("hotfix/p0-18o-") or "tests/test_p0_18o_lock_video_flows_real_engine_all_products.py" in normalized)
        and path.replace("\\", "/") in {"services/video_project_queue.py", "services/video_final_output.py"}
    )


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def test_admin_can_set_global_vat_rate(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)

    default_config = bot.finance_tax_config()
    assert default_config["vat_enabled"] is True
    assert default_config["vat_rate"] == 0.08
    assert default_config["vat_mode"] == "exclusive"

    result = bot.admin_set_global_vat_rate(10, admin_id="admin-tax")
    assert result["ok"] is True
    assert result["vat_enabled"] is True
    assert result["vat_rate"] == 0.10
    assert bot.admin_set_global_vat_rate(25, admin_id="admin-tax")["reason"] == "rate_out_of_safe_range"


def test_vat_rate_applies_to_new_orders_only(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)

    bot.create_order("vat-old", "vat-user", 100_000, 1_000)
    old_invoice = bot.finance_invoice_for_order("vat-old")
    assert old_invoice["vat_amount_vnd"] == 8_000
    assert old_invoice["total_amount_vnd"] == 108_000

    bot.admin_set_global_vat_rate(10, admin_id="admin-tax")
    bot.create_order("vat-new", "vat-user", 100_000, 1_000)
    new_invoice = bot.finance_invoice_for_order("vat-new")

    assert bot.finance_invoice_for_order("vat-old")["vat_amount_vnd"] == 8_000
    assert new_invoice["vat_amount_vnd"] == 10_000
    assert new_invoice["total_amount_vnd"] == 110_000


def test_vat_can_be_disabled(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)

    result = bot.admin_set_vat_enabled(False, admin_id="admin-tax")
    assert result["ok"] is True
    assert result["vat_enabled"] is False

    bot.create_order("vat-off", "vat-user", 100_000, 1_000)
    invoice = bot.finance_invoice_for_order("vat-off")
    assert invoice["vat_amount_vnd"] == 0
    assert invoice["total_amount_vnd"] == 100_000


def test_vat_exclusive_calculation():
    snapshot = bot.calculate_vat_snapshot(
        100_000,
        {
            "vat_enabled": True,
            "vat_rate": 0.08,
            "vat_mode": "exclusive",
            "vat_label": bot.VAT_DEFAULT_LABEL,
            "vat_note": bot.VAT_DEFAULT_NOTE,
        },
    )
    assert snapshot["subtotal_amount_vnd"] == 100_000
    assert snapshot["vat_amount_vnd"] == 8_000
    assert snapshot["total_amount_vnd"] == 108_000


def test_topup_adds_vat_to_total_payment_and_wallet_credit_excludes_vat(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)

    user_id = "vat-topup-user"
    before, _, _ = bot.get_user(user_id, "VAT Topup")
    bot.create_order("vat-topup", user_id, 10_000, 100)
    invoice, total = bot.payos_invoice_total_for_order("vat-topup", 10_000)

    assert invoice["subtotal_amount_vnd"] == 10_000
    assert invoice["vat_amount_vnd"] == 800
    assert total == 10_800

    processed, desc, info = bot.process_payos_paid_order("vat-topup", total, webhook_currency="VND", transaction_id="vat-topup-tx")
    after, _, _ = bot.get_user(user_id)

    assert processed is True
    assert desc == "success"
    assert after - before == bot.package_base_xu(10_000)
    assert info["subtotal_amount_vnd"] == 10_000
    assert info["vat_amount_vnd"] == 800
    assert bot.finance_invoice_for_order("vat-topup")["status"] == "paid"


def test_no_double_vat_when_spending_xu(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)

    user_id = "vat-spend-user"
    bot.get_user(user_id, "VAT Spend")
    conn = bot.db_connect()
    try:
        conn.execute("UPDATE users SET credits=1000 WHERE user_id=?", (user_id,))
        conn.commit()
    finally:
        conn.close()

    before_invoices = _scalar("SELECT COUNT(*) FROM finance_invoices")
    charge = bot.spend_fixed_credit_info(user_id, 100, "spend_test_service", "pytest spend")
    after_invoices = _scalar("SELECT COUNT(*) FROM finance_invoices")

    assert charge["ok"] is True
    assert after_invoices == before_invoices


def test_payment_channels_store_vat_and_momo_hidden_from_cny(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)

    conn = bot.db_connect()
    try:
        zalo = bot.build_finance_invoice_snapshot_conn(
            conn,
            "zalo-vat",
            "user-zalo",
            100_000,
            "manual_topup",
            "manual_topup",
            {"payment_channel": "zalopay", "currency": "VND"},
        )
        usdt = bot.build_finance_invoice_snapshot_conn(
            conn,
            "usdt-vat",
            "user-usdt",
            0,
            "manual_topup",
            "manual_topup",
            {"payment_channel": "usdt_trc20", "currency": "USDT", "original_amount": 10, "fx_rate": 25_000},
        )
    finally:
        conn.close()

    assert zalo["payment_channel"] == "zalopay"
    assert zalo["vat_amount_vnd"] == 8_000
    assert usdt["payment_channel"] == "usdt"
    assert usdt["subtotal_amount_vnd"] == 250_000
    assert usdt["vat_amount_vnd"] == 20_000

    labels = _labels(bot.manual_foreign_preview_keyboard({"currency": "CNY", "original_amount": 100}, "123"))
    assert not any("MoMo" in label for label in labels)
    assert any("ZaloPay" in label for label in labels)
    assert any("USDT" in label for label in labels)


def test_payos_callback_validates_total_after_vat_and_flags_anomaly(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)

    user_id = "vat-mismatch-user"
    before, _, _ = bot.get_user(user_id, "VAT Mismatch")
    bot.create_order("vat-mismatch", user_id, 100_000, 1_000)

    processed, desc, info = bot.process_payos_paid_order("vat-mismatch", 100_000, webhook_currency="VND")
    after, _, _ = bot.get_user(user_id)

    assert processed is False
    assert desc == "amount_mismatch"
    assert after == before
    assert info["total_amount_vnd"] == 108_000
    assert _scalar("SELECT COUNT(*) FROM finance_anomalies WHERE order_id='vat-mismatch'") == 1
    assert _scalar("SELECT status FROM payos_orders WHERE order_code='vat-mismatch'") == bot.PAYOS_STATUS_PENDING_ADMIN_REVIEW
    assert bot.finance_invoice_for_order("vat-mismatch")["status"] == "flagged"


def test_duplicate_callback_does_not_double_grant_and_logs_anomaly(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)

    user_id = "vat-duplicate-user"
    before, _, _ = bot.get_user(user_id, "VAT Duplicate")
    bot.create_order("vat-duplicate", user_id, 10_000, 100)
    _invoice, total = bot.payos_invoice_total_for_order("vat-duplicate", 10_000)

    first = bot.process_payos_paid_order("vat-duplicate", total, webhook_currency="VND", transaction_id="dup-tx")
    second = bot.process_payos_paid_order("vat-duplicate", total, webhook_currency="VND", transaction_id="dup-tx")
    after, _, _ = bot.get_user(user_id)

    assert first[0] is True
    assert second[0] is False
    assert second[1] == "already_paid"
    assert after - before == bot.package_base_xu(10_000)
    assert _scalar("SELECT COUNT(*) FROM finance_anomalies WHERE order_id='vat-duplicate' AND anomaly_type='duplicate_callback'") == 1


def test_package_combo_tax_lines_and_quota_excludes_vat(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)

    metadata = {
        "type": "package_purchase",
        "payment_type": "combo_purchase",
        "package_type": "combo",
        "package_code": "combo_ad_video_588k",
    }
    bot.create_order(
        "combo-vat",
        "combo-vat-user",
        588_000,
        0,
        order_type="package_purchase",
        plan_id="combo_ad_video_588k",
        plan_name="Combo Video Quảng Cáo",
        metadata_json=json.dumps(metadata, ensure_ascii=False),
    )
    invoice, total = bot.payos_invoice_total_for_order("combo-vat", 588_000)
    text = bot.finance_tax_block(invoice)

    assert invoice["subtotal_amount_vnd"] == 588_000
    assert invoice["vat_amount_vnd"] == 47_040
    assert total == 635_040
    assert "Phần thuế không quy đổi thành Xu hoặc lượt sử dụng dịch vụ" in text

    processed, desc, info = bot.process_payos_paid_order("combo-vat", total, webhook_currency="VND", transaction_id="combo-vat-tx")
    assert processed is True
    assert desc == "package_success"
    assert info["xu"] == 0
    assert bot.active_package_item_for_user("combo-vat-user", "video_standard") is not None


def test_accounting_adjustment_requires_reason_and_never_deletes_original_order(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)

    bot.create_order("adjust-order", "adjust-user", 100_000, 1_000)
    before_order = _rows("SELECT order_code, amount, status FROM payos_orders WHERE order_code='adjust-order'")[0]

    assert bot.create_finance_adjustment("revenue_subtract", 10_000, "", admin_id="admin")["reason"] == "reason_required"
    result = bot.create_finance_adjustment("revenue_subtract", 10_000, "Khách chuyển nhầm cần điều chỉnh", admin_id="admin", related_order_id="adjust-order")
    after_order = _rows("SELECT order_code, amount, status FROM payos_orders WHERE order_code='adjust-order'")[0]

    assert result["ok"] is True
    assert after_order == before_order
    assert _scalar("SELECT COUNT(*) FROM finance_adjustments WHERE related_order_id='adjust-order'") == 1


def test_refund_and_capital_adjustments_feed_reports(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)

    bot.create_order("report-order", "report-user", 100_000, 1_000)
    _invoice, total = bot.payos_invoice_total_for_order("report-order", 100_000)
    bot.process_payos_paid_order("report-order", total, webhook_currency="VND", transaction_id="report-tx")
    bot.create_finance_adjustment("refund", 10_000, "Hoàn tiền một phần", admin_id="admin", related_order_id="report-order")
    bot.create_finance_adjustment("tax_add", 1_000, "Điều chỉnh VAT", admin_id="admin")
    bot.create_finance_adjustment("expense_add", 20_000, "Chi phí vận hành", admin_id="admin")
    bot.create_finance_adjustment("capital_add", 500_000, "Ghi nhận vốn ban đầu", admin_id="admin")

    start, end, label, _kind = bot.finance_period_bounds("", "month")
    report = bot.finance_business_report_payload(start, end, label)

    assert report["revenue_before_tax"] == 90_000
    assert report["vat_collected"] == 9_000
    assert report["cash_in"] == 99_000
    assert report["expenses"] >= 20_000
    assert report["profit_before_tax_reserve"] == report["revenue_before_tax"] - report["expenses"]
    assert report["capital_total"] == 500_000


def test_admin_finance_menu_and_guide_cover_required_blocks():
    labels = _labels(bot.finance_admin_keyboard())
    callbacks = _callbacks(bot.finance_admin_keyboard())
    for expected in ["📊 Tổng quan", "💰 Doanh thu", "🧾 Thuế / VAT", "💸 Chi phí", "📈 Lợi nhuận", "🏦 Vốn & Hòa vốn", "🧮 Sổ điều chỉnh", "📘 Hướng dẫn tài chính"]:
        assert expected in labels
    for expected in ["menu|finance_tax_vat", "menu|finance_anomalies", "menu|finance_adjustments", "menu|finance_guide"]:
        assert expected in callbacks

    guide = bot.finance_admin_guide_text()
    assert "không sửa/xóa giao dịch gốc" in guide.lower()
    assert "/vat_rate 8" in guide


def test_public_tax_copy_not_misleading():
    text = "\n".join(bot.finance_tax_lines({
        "subtotal_amount_vnd": 100_000,
        "vat_rate": 0.08,
        "vat_amount_vnd": 8_000,
        "total_amount_vnd": 108_000,
        "vat_mode": "exclusive",
    })).lower()
    assert "giá trước thuế" in text
    assert "tổng thanh toán" in text
    assert "không quy đổi thành xu" in text
    for forbidden in ["miễn thuế", "không cần đóng thuế", "né thuế", "thu hộ nhà nước"]:
        assert forbidden not in text


def test_no_engine_files_touched_and_no_db_destructive():
    try:
        changed = subprocess.check_output(
            ["git", "diff", "--name-only", "origin/main", "--"],
            text=True,
            encoding="utf-8",
        ).splitlines()
        bot_diff = subprocess.check_output(
            ["git", "diff", "origin/main", "--", "bot.py"],
            text=True,
            encoding="utf-8",
        )
    except Exception as exc:  # pragma: no cover
        import pytest

        pytest.skip(f"git diff unavailable: {exc}")

    forbidden_paths = (
        "providers/",
        "local_worker.py",
        "remote_worker.py",
        "services/subtitle",
        "services/video",
        "services/voice",
    )
    assert [path for path in changed if path.replace("\\", "/").startswith(forbidden_paths) and not _allowed_p0_18o_engine_guard_path(path, changed)] == []
    upper_diff = bot_diff.upper()
    assert "DROP TABLE" not in upper_diff
    assert "DELETE FROM PAYOS_ORDERS" not in upper_diff
    assert "DELETE FROM FINANCE_INVOICES" not in upper_diff
