import bot


def _fresh_db(monkeypatch, tmp_path, *, init=True):
    db_path = tmp_path / "finance2d.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    if init:
        bot.init_db()
    return db_path


def test_finance_adjustments_text_empty_state_without_existing_table(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path, init=False)

    text = bot.finance_adjustments_text()

    assert "🧮 <b>Sổ điều chỉnh</b>" in text
    assert "Chưa có bút toán điều chỉnh." in text
    assert "Có lỗi khi xử lý lệnh" not in text
    assert "Bot chưa trừ Xu" not in text


def test_finance_adjustments_button_handler_routes_to_clean_ledger(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path, init=False)

    text, keyboard = bot.ADMIN_MENU_PAGE_HANDLERS["finance_adjustments"]()

    assert "Chưa có bút toán điều chỉnh." in text
    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
    ]
    assert "menu|finance_adjust_revenue_help" in callbacks
    assert "menu|finance" in callbacks


def test_product_price_audit_shows_editable_keys_and_aliases():
    text = "\n".join(bot.product_price_audit_lines("video"))

    assert "Video 300 Xu" in text
    assert "[key=video_beta_300, alias=video_300]" in text
    assert "editable" in text


def test_subdub_pricing_audit_shows_derived_formula():
    text = "\n".join(bot.product_price_audit_lines("subdub"))

    assert "[key=subtitle_translate_video, alias=subtitle]" in text
    assert "[key=dub_video, alias=dub]" in text
    assert "[derived=subtitle_translate_video+dub_video]" in text
    assert "derived" in text


def test_price_keys_lines_show_labels_current_unit_and_examples():
    text = "\n".join(bot.price_keys_lines())

    assert "🔑 <b>Price keys</b>" in text
    assert "Video 300 Xu" in text
    assert "[key=video_beta_300]" in text
    assert "alias: <code>video_300</code>" in text
    assert "unit: <code>Xu</code>" in text
    assert "/price_set video_300 300" in text
    assert "Chỉ owner được đổi giá" in text


def test_price_set_alias_video_300_updates_canonical(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)

    bot.set_canonical_price_value("video_300", 308, updated_by="owner-test")

    assert bot.canonical_price_xu("video_beta_300") == 308
    assert bot.canonical_price_xu("video_300") == 308


def test_price_keys_command_exists_and_is_admin_view_only():
    assert callable(bot.cmd_price_keys)
    assert "/price_set video_300 300" in bot.price_set_help_text()
    assert "Admin mặc định chỉ xem audit/key" in bot.price_set_help_text()


def test_no_payos_wallet_provider_runtime_files_needed_for_finance2d():
    # This task is deliberately a finance/pricing copy and routing fix.
    lines = "\n".join(bot.price_keys_lines() + bot.product_price_audit_lines("all"))
    forbidden = ("PAYOS_CHECKSUM_KEY", "provider secret", "wallet conversion")
    assert not any(token in lines for token in forbidden)
