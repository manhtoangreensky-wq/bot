import json
import subprocess

import bot


def _fresh_db(monkeypatch, tmp_path):
    db_path = tmp_path / "p0_finance2.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    bot.init_db()
    return db_path


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def test_admin_finance_button_opens_canonical_finance_dashboard():
    text, keyboard = bot.ADMIN_MENU_PAGE_HANDLERS["admin_finance"]()
    assert "Admin Tài chính TOAN AAS" in text
    assert "sổ sách công ty mini" in text
    assert "menu|finance_overview" in _callbacks(keyboard)


def test_legacy_finance_routes_redirect_to_canonical():
    audit = bot.finance_menu_audit_text()
    assert "admin_finance -> finance_menu_text" in audit
    assert "canonical_finance_screen" in audit
    assert "redirected_legacy_routes" in audit
    assert "missing_routes: <code>none</code>" in audit


def test_finance_back_from_subscreen_returns_canonical_dashboard():
    assert "menu|finance" in _callbacks(bot.finance_child_keyboard())
    assert "menu|finance_tax_vat" in _callbacks(bot.finance_tax_child_keyboard())
    assert "menu|finance" in _callbacks(bot.finance_tax_keyboard())


def test_b2c_topup_no_public_vat_surcharge(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    bot.create_order("b2c-topup", "u-b2c", 100_000, 1_000)
    invoice, total = bot.payos_invoice_total_for_order("b2c-topup", 100_000)
    text = bot.finance_tax_block(invoice)

    assert total == 100_000
    assert invoice["vat_amount_vnd"] == 0
    assert invoice["customer_type"] == "individual"
    assert invoice["tax_display"] == bot.B2C_TAX_DISPLAY
    assert "VAT" not in text
    assert "8.00%" not in text
    assert "Giá đã bao gồm phí hệ thống nếu có" in text


def test_b2c_topup_amounts_stay_round(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    for amount in (100_000, 200_000, 500_000):
        order_id = f"round-{amount}"
        bot.create_order(order_id, "u-round", amount, bot.package_base_xu(amount))
        invoice, total = bot.payos_invoice_total_for_order(order_id, amount)
        assert total == amount
        assert invoice["subtotal_amount_vnd"] == amount
        assert invoice["vat_amount_vnd"] == 0


def test_b2c_internal_vat_reserve_configurable(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    bot.create_order("b2c-vat8", "u-b2c", 100_000, 1_000)
    vat8 = bot.finance_invoice_for_order("b2c-vat8")
    assert vat8["vat_amount_vnd"] == 0
    assert json.loads(vat8["metadata_json"])["internal_vat_rate"] == 0.08
    assert json.loads(vat8["metadata_json"])["internal_vat_reserve_vnd"] == 7407

    bot.admin_set_global_vat_rate(10, admin_id="admin-tax")
    bot.create_order("b2c-vat10", "u-b2c", 100_000, 1_000)
    vat10 = json.loads(bot.finance_invoice_for_order("b2c-vat10")["metadata_json"])
    assert vat10["internal_vat_rate"] == 0.10
    assert vat10["internal_vat_reserve_vnd"] == 9091


def test_b2b_invoice_shows_vat_separately(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    metadata = {
        "customer_type": "business",
        "invoice_required": True,
        "company_name": "Cong ty A",
        "tax_code": "0101234567",
    }
    bot.create_order("b2b-order", "u-b2b", 100_000, 1_000, metadata_json=json.dumps(metadata))
    invoice, total = bot.payos_invoice_total_for_order("b2b-order", 100_000)
    text = bot.finance_tax_block(invoice)

    assert total == 108_000
    assert invoice["customer_type"] == "business"
    assert invoice["vat_amount_vnd"] == 8_000
    assert "Thuế GTGT" in text
    assert "Giá dịch vụ" in text


def test_finance_policy_status_and_commands_text():
    policy = bot.finance_policy_status_text()
    assert bot.B2C_PRICE_MODE in policy
    assert "không cộng VAT lẻ" in policy
    assert "TNDN chỉ dùng cho báo cáo" in policy
    assert "/tax_scenario_report" in policy


def test_tax_scenario_report_uses_cogs_50_marketing_30_cit_20():
    payload = bot.finance_tax_scenario_report_payload(100_000, {
        "vat_enabled": True,
        "vat_rate": 0.10,
        "vat_mode": "exclusive",
        "cit_enabled": True,
    })
    assert payload["public_total"] == 100_000
    assert payload["customer_vat_surcharge"] == 0
    assert payload["internal_vat_reserve"] == 9091
    assert payload["cogs_worst_case_rate"] == 0.50
    assert payload["marketing_reserve_rate"] == 0.30
    assert payload["cit_rate_scenario"] == 0.20


def test_provider_cost_tax_status_tracks_fct_metadata():
    payload = bot.provider_cost_tax_status_payload()
    text = bot.provider_cost_tax_status_text()
    assert payload["provider_call"] is False
    assert payload["secret_safe"] is True
    assert "ShopAIKey" in text
    assert "Key4U" in text
    assert "FCT" in text


def test_voice_price_005_becomes_010():
    assert bot.VOICE_TTS_PRODUCT_PRICE_PER_WORD_XU == 0.10
    quote = bot.voice_tts_product_quote(" ".join(["xin"] * 20))
    assert quote["raw_price_xu"] == 2.0
    assert quote["total_xu"] == 2


def test_voice_price_010_becomes_020():
    assert bot.CUSTOM_VOICE_USAGE_PRICE_PER_CHAR_XU == 0.20
    assert bot.custom_voice_usage_price_xu("a" * 11) == 3


def test_subdub_voice_price_uses_new_base():
    assert bot.VIDEO_ONLY_DUB_DEFAULT_RATE_XU == 0.10
    assert bot.VIDEO_ONLY_DUB_CUSTOM_RATE_XU == 0.20
    assert bot.calculate_video_only_char_price(1000, bot.VIDEO_ONLY_DUB_DEFAULT_RATE_XU)["total_xu"] == 90
    assert bot.calculate_video_only_char_price(1000, bot.VIDEO_ONLY_DUB_CUSTOM_RATE_XU)["total_xu"] == 180


def test_volume_discount_cap_30_percent():
    assert bot.finance_volume_discount_percent(100) == 10
    assert bot.finance_volume_discount_percent(1000) == 10
    assert bot.finance_volume_discount_percent(10_000) == 20
    assert bot.finance_discount_cap_percent(80) == 30


def test_no_video_pricing_change():
    assert bot.VIDEO_ONLY_SUBTITLE_TRANSLATE_RATE_XU == 0.1
    assert bot.VIDEO_BASE_COST_XU == 300
    assert bot.VIDEO_PUBLIC_ALLOWED_TIERS == "200,300,400,500,600,800,1000,1200,1500"


def test_no_topup_conversion_change():
    assert bot.package_base_xu(100_000) == 1_000
    assert bot.package_base_xu(200_000) == 2_000


def test_no_payos_webhook_change():
    diff = subprocess.check_output(["git", "diff", "origin/main", "--", "bot.py"], text=True, encoding="utf-8")
    assert "def verify_payos_signature" not in diff
    assert "PAYOS_CHECKSUM_KEY" not in diff
    assert "webhook_payos" not in diff


def test_no_wallet_balance_mutation_from_reports(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    user_id = "u-report-safe"
    bot.get_user(user_id, "Report Safe")
    conn = bot.db_connect()
    try:
        conn.execute("UPDATE users SET credits=1234 WHERE user_id=?", (user_id,))
        conn.commit()
    finally:
        conn.close()

    bot.finance_policy_status_text()
    bot.finance_tax_scenario_report_text()
    bot.provider_cost_tax_status_text()
    credits, _, _ = bot.get_user(user_id)
    assert credits == 1234
