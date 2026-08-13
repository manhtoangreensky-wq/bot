from pathlib import Path
from types import SimpleNamespace


BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"


def _source() -> str:
    return BOT_PATH.read_text(encoding="utf-8")


def _source_between(start: str, end: str) -> str:
    source = _source()
    return source[source.index(start):source.index(end)]


def _function_source(name: str) -> str:
    source = _source()
    start = source.index(f"def {name}(")
    end = source.find("\ndef ", start + 1)
    return source[start:] if end < 0 else source[start:end]


def test_international_manual_topup_renderers_use_the_imported_policy_alias():
    account_copy = {
        "manual_topup_section": "Manual top-up",
        "select_topup": "Select the amount",
        "manual_topup_rules": "Admin verifies received funds before crediting Xu.",
        "topup_verified_base": "Verified base Xu only.",
        "topup_benefits_remain": "Non-top-up benefits remain available.",
    }
    namespace = {
        "__builtins__": __builtins__,
        "html": SimpleNamespace(escape=str),
        "show_domestic_topup_promotion": lambda _uid, _lang: False,
        "public_copy_locale": lambda lang: str(lang or "en"),
        "public_account_flow_copy": lambda _lang: dict(account_copy),
        "manual_topup_rules_text": lambda: "manual rules",
        "public_international_topup_policy_lines": lambda lang: [f"{lang}: base Xu only"],
        "public_topup_deep_copy": lambda _lang: {"manual_channels": "ZaloPay; Binance / USDT TRC20"},
    }
    exec(_function_source("manual_payment_menu_text"), namespace)
    exec(_function_source("manual_domestic_amount_text"), namespace)

    menu = namespace["manual_payment_menu_text"]("intl-user", "en")
    amount = namespace["manual_domestic_amount_text"]("intl-user", "en")

    assert "en: base Xu only" in menu
    assert "en: base Xu only" in amount


def test_all_international_locales_own_complete_native_topup_deep_copy():
    from services.pricing_guide_content import PUBLIC_COPY_LOCALES, public_topup_deep_copy

    international = PUBLIC_COPY_LOCALES - {"vi"}
    assert international == {
        "en", "zh", "ja", "ko", "th", "ar", "es", "pt", "fr", "de",
        "hi", "ru", "tr", "fil", "it", "id",
    }
    required = {
        "manual_channels", "payos_unavailable_title", "denomination", "amount",
        "test_order_id", "order_cancelled_no_xu", "retry_or_manual", "safety_note",
        "retry_payos", "auto_paused_title", "web_invoice_created", "expected_xu",
        "web_order_id", "credited_after_webhook", "pay_now", "payos_invoice_created",
        "base_xu", "order_id", "expires_in", "minutes_unit", "scan_qr_instruction", "scan_qr",
        "invalid_amount", "vnd_bill_image_only", "txid_too_short", "duplicate_txid",
        "txid_save_failed", "bill_txid_title", "bill_txid_body", "manual_history",
        "promo_error", "generic_topup_error", "payment_price", "service_price",
        "total_payment", "included_tax_note", "separate_tax_note",
        "gift_received_title", "gift_code_label", "gift_xu_received",
        "gift_already_received", "gift_invalid",
        "gift_assignment_required", "gift_request_pending",
        "gift_support_instruction", "gift_reason_label",
    }
    english = public_topup_deep_copy("en")
    vietnamese = public_topup_deep_copy("vi")
    assert required <= english.keys()
    assert "ZaloPay" in english["manual_channels"]
    assert "Binance / USDT TRC20" in english["manual_channels"]
    for locale in sorted(international):
        copy = public_topup_deep_copy(locale)
        assert required <= copy.keys(), locale
        assert all(str(copy[key]).strip() for key in required), locale
        if locale != "en":
            assert copy["generic_topup_error"] not in {
                english["generic_topup_error"], vietnamese["generic_topup_error"],
            }, locale
            assert copy["bill_txid_body"] not in {
                english["bill_txid_body"], vietnamese["bill_txid_body"],
            }, locale
            for key in (
                "gift_received_title", "gift_xu_received", "gift_already_received",
                "gift_invalid", "gift_assignment_required", "gift_request_pending",
            ):
                assert copy[key] not in {english[key], vietnamese[key]}, (locale, key)


def test_topup_callbacks_preserve_active_locale_through_every_deep_surface():
    source = _source()
    import_block = _source_between(
        "from services.pricing_guide_content import (",
        ")\nfrom video_multiscene_engine import (",
    )
    package_handler = _source_between(
        "async def handle_package_choice(",
        "async def handle_manual_package_choice(",
    )
    pending_handler = _source_between(
        "async def handle_manual_topup_pending_text(",
        "def finance_admin_keyboard(",
    )
    error_handler = _source_between(
        "async def on_telegram_error(",
        "async def handle_message(",
    )

    assert "    public_topup_deep_copy," in import_block
    assert "deep_copy = public_topup_deep_copy(lang)" in package_handler
    assert "payos_checkout_unavailable_text(" in package_handler
    assert "lang=lang" in package_handler
    assert "finance_tax_block_i18n(invoice, lang)" in package_handler
    assert "deep_copy['minutes_unit']" in package_handler
    assert "lang = get_user_language(uid) or \"vi\"" in pending_handler
    assert "manual_foreign_preview_text(preview, lang)" in pending_handler
    assert "manual_foreign_preview_keyboard(preview, uid, lang)" in pending_handler
    assert "manual_pending_user_text(deposit, lang)" in pending_handler
    assert "topup_error_copy = public_topup_deep_copy" in error_handler
    assert "generic_topup_error" in error_handler


def test_scoped_topup_error_handler_uses_active_locale_copy_for_commands_and_callbacks():
    error_handler = _source_between(
        "async def on_telegram_error(",
        "async def safe_edit_query_message(",
    )

    # Keep the global error handler generic for unrelated features, but make every
    # public top-up/promotion entry point opt into the locale-owned safe error.
    for callback_prefix in (
        '"manual|"',
        '"payos_pkg|"',
        '"pricing|promotions"',
        '"pricing|promo_apply"',
    ):
        assert callback_prefix in error_handler
    for command in (
        '"/naptien"',
        '"/thucong"',
        '"/promo"',
        '"/khuyenmai"',
        '"/my_promos"',
    ):
        assert command in error_handler

    assert "topup_error_copy = public_topup_deep_copy(" in error_handler
    assert "get_user_language(" in error_handler
    assert 'error_key = "promo_error"' in error_handler
    assert 'else "generic_topup_error"' in error_handler
    assert "topup_error_copy[error_key]" in error_handler


def test_cmd_promo_exception_uses_native_promo_error_for_non_vietnamese_locale():
    promo_handler = _source_between(
        "async def cmd_promo(",
        "async def cmd_promo_guide(",
    )

    assert "get_user_language(" in promo_handler
    assert "public_copy_locale(" in promo_handler
    assert "public_topup_deep_copy(" in promo_handler
    assert 'deep_copy["promo_error"]' in promo_handler or "deep_copy['promo_error']" in promo_handler
    assert 'locale == "vi"' in promo_handler


def test_payos_non_vietnamese_guard_never_renders_raw_vietnamese_block_message():
    package_handler = _source_between(
        "async def handle_package_choice(",
        "async def handle_manual_package_choice(",
    )
    guard = package_handler[
        package_handler.index("topup_guard = payos_auto_topup_guard"):
        package_handler.index("get_user(uid", package_handler.index("topup_guard = payos_auto_topup_guard"))
    ]

    assert "blocked_message =" in guard
    assert "guard_message =" in guard
    assert 'blocked_message if locale == "vi"' in guard
    assert 'deep_copy["retry_or_manual"]' in guard or "deep_copy['retry_or_manual']" in guard
    rendered = guard[guard.index("return await query.edit_message_text"):]
    assert "html.escape(guard_message)" in rendered
    assert "html.escape(blocked_message)" not in rendered


def test_international_manual_intro_lists_existing_payment_channels_in_active_locale_copy():
    menu_renderer = _source_between(
        "def manual_payment_menu_text(",
        "def manual_payment_menu_keyboard(",
    )

    assert "deep_copy = public_topup_deep_copy(locale)" in menu_renderer
    assert 'deep_copy["manual_channels"]' in menu_renderer or "deep_copy['manual_channels']" in menu_renderer
    assert menu_renderer.index("deep_copy = public_topup_deep_copy(locale)") < menu_renderer.index("deep_copy['manual_channels']")
    assert 'if locale != "vi" else ""' in menu_renderer


def test_manual_and_payos_nested_handlers_reload_and_forward_the_active_locale():
    package_handler = _source_between(
        "async def handle_package_choice(",
        "async def handle_manual_package_choice(",
    )
    manual_handler = _source_between(
        "async def handle_manual_package_choice(",
        "async def cmd_naptien(",
    )
    pending_handler = _source_between(
        "async def handle_manual_topup_pending_text(",
        "def finance_admin_keyboard(",
    )

    assert 'lang = get_user_language(uid) or "vi"' in package_handler
    assert "deep_copy = public_topup_deep_copy(lang)" in package_handler
    assert "lang=lang" in package_handler

    assert 'lang = get_user_language(query.from_user.id) or "vi"' in manual_handler
    for call in (
        "manual_payment_menu_keyboard(uid, lang)",
        "manual_domestic_amount_text(uid, lang)",
        "manual_domestic_amount_keyboard(uid, lang)",
        "manual_foreign_amount_text(currency, lang)",
        "manual_foreign_preview_text(preview, lang)",
        "manual_payment_method_text(uid, method, get_active_manual_bill_state(uid), lang)",
    ):
        assert call in manual_handler

    assert 'lang = get_user_language(uid) or "vi"' in pending_handler
    assert "deep_copy = public_topup_deep_copy(locale)" in pending_handler
    assert "manual_pending_user_text(deposit, lang)" in pending_handler


def test_public_gift_commands_use_shared_native_customer_renderers_without_touching_admin_copy():
    promo_handler = _source_between(
        "async def _cmd_promo_impl(",
        "async def cmd_promo(",
    )
    gift_handler = _source_between(
        "async def cmd_gift(",
        "async def cmd_gift_create(",
    )

    for handler in (promo_handler, gift_handler):
        assert "get_user_language(uid)" in handler
        assert "gift_customer_result_text(" in handler
        assert "lang=lang" in handler
    assert "public_copy_locale(" in gift_handler

    # Admin grant/create responses are a protected Vietnamese operator surface;
    # only the normal customer branch must delegate to localized renderers.
    admin_start = gift_handler.index("if is_admin_user(update.effective_user.id) and len(context.args) >= 2:")
    customer_start = gift_handler.index("ok, status, info = redeem_gift_code", admin_start)
    admin_branch = gift_handler[admin_start:customer_start]
    customer_branch = gift_handler[customer_start:]
    assert "Đã cấp gift code cho user" in admin_branch
    assert "gift_customer_result_text(" not in admin_branch
    assert "Bạn đã nhận quà TOAN AAS" not in customer_branch
    assert "Mã quà tặng này đã được nhận" not in customer_branch
    assert "Mã quà tặng không hợp lệ" not in customer_branch


def test_gift_assignment_pending_and_support_helpers_accept_and_forward_active_locale():
    source = _source()
    assignment_helper = _source_between(
        "def gift_needs_assignment_message(",
        "def gift_beta_request_pending_message(",
    )
    pending_helper = _source_between(
        "def gift_beta_request_pending_message(",
        "def beta_gift_support_keyboard(",
    )
    support_helper = _source_between(
        "def beta_gift_support_keyboard(",
        "async def notify_admin_beta_gift_request(",
    )

    assert "lang: str = \"vi\"" in assignment_helper
    assert "public_topup_deep_copy(" in assignment_helper
    assert "lang: str = \"vi\"" in pending_helper
    assert "public_topup_deep_copy(" in pending_helper
    assert "lang: str = \"vi\"" in support_helper
    assert "public_hub_copy(" in support_helper or "public_topup_deep_copy(" in support_helper

    promo_handler = _source_between("async def _cmd_promo_impl(", "async def cmd_promo(")
    gift_handler = _source_between("async def cmd_gift(", "async def cmd_gift_create(")
    for handler in (promo_handler, gift_handler):
        assert "gift_beta_request_pending_message(update.effective_user, code, lang)" in handler
        assert "gift_needs_assignment_message(update.effective_user, code, lang)" in handler
        assert "beta_gift_support_keyboard(lang)" in handler


def test_vietnamese_gift_customer_output_remains_byte_for_byte_compatible():
    namespace = {
        "__builtins__": __builtins__,
        "html": SimpleNamespace(escape=str),
        "public_copy_locale": lambda lang: str(lang or "vi"),
        "public_topup_deep_copy": lambda _lang: {
            "gift_received_title": "Đã nhận quà tặng",
            "gift_code_label": "Mã quà tặng",
            "gift_xu_received": "Xu quà tặng đã nhận",
            "gift_already_received": "Bạn đã nhận quà tặng này rồi.",
            "gift_invalid": "Quà tặng không hợp lệ hoặc đã hết hạn.",
            "gift_reason_label": "Lý do tặng quà",
        },
        "public_account_flow_copy": lambda _lang: {"new_balance": "Số dư mới"},
        "normalize_promo_code": lambda code: str(code).upper(),
    }
    exec(_function_source("gift_customer_result_text"), namespace)
    render = namespace["gift_customer_result_text"]

    assert render("redeemed", "gift10", {"code": "GIFT10", "xu": 10, "balance": 210}, "vi") == (
        "✅ <b>Bạn đã nhận quà TOAN AAS</b>\n\n"
        "• Mã: <code>GIFT10</code>\n"
        "• Xu dịch vụ nhận: <b>+10 Xu</b>\n"
        "• Số dư mới: <b>210 Xu dịch vụ</b>"
    )
    assert render("already_applied", "gift10", {}, "vi") == (
        "ℹ️ Mã quà tặng này đã được nhận trên tài khoản của bạn, hệ thống không cộng trùng."
    )
    assert render("expired", "gift10", {}, "vi") == (
        "❌ Mã quà tặng không hợp lệ, đã hết lượt hoặc chưa được kích hoạt.\n\n"
        "Lý do: <code>expired</code>"
    )


def test_international_invalid_gift_copy_never_exposes_internal_english_status_codes():
    from services.pricing_guide_content import public_topup_deep_copy

    namespace = {
        "__builtins__": __builtins__,
        "html": SimpleNamespace(escape=str),
        "public_copy_locale": lambda lang: str(lang or "en"),
        "public_topup_deep_copy": public_topup_deep_copy,
        "public_account_flow_copy": lambda _lang: {"new_balance": "balance"},
        "normalize_promo_code": lambda code: str(code).upper(),
    }
    exec(_function_source("gift_customer_result_text"), namespace)
    render = namespace["gift_customer_result_text"]

    internal_statuses = ("not_found", "inactive", "usage_limit", "expired", "owner_only")
    for locale in ("en", "zh", "ja", "ko", "th", "ar", "es", "pt", "fr", "de", "hi", "ru", "tr", "fil", "it", "id"):
        for status in internal_statuses:
            text = render(status, "gift10", {}, locale)
            assert f"<code>{status}</code>" not in text, (locale, status, text)
            assert "<code>" not in text, (locale, status, text)


def test_vietnamese_manual_pending_amount_keeps_legacy_dong_suffix():
    source = _function_source("manual_pending_user_text")
    assert 'if locale != "vi" else f"{int(deposit.get(\'amount_vnd\') or 0):,}đ"' in source
    assert 'if locale != "vi" else f"{int(deposit.get(\'amount_vnd\') or 0):,} VND"' not in source


def test_manual_vnd_amount_label_is_native_for_vietnamese_and_neutral_for_international_locales():
    namespace = {
        "__builtins__": __builtins__,
        "format_public_integer": lambda value: f"{int(value or 0):,}".replace(",", "."),
        "public_copy_locale": lambda lang: str(lang or "vi"),
    }
    exec(_function_source("format_manual_vnd_amount"), namespace)
    render = namespace["format_manual_vnd_amount"]

    assert render(100_000, "vi") == "100.000đ"
    for locale in ("en", "zh", "ja", "ko", "th", "ar", "es", "pt", "fr", "de", "hi", "ru", "tr", "fil", "it", "id"):
        assert render(100_000, locale) == "100.000 VND", locale

    handler = _source_between(
        "async def handle_manual_package_choice(",
        "async def handle_payos_alert_callback(",
    )
    assert handler.count("format_manual_vnd_amount(preview['amount_vnd'], lang)") == 2


def test_legacy_manual_package_callback_uses_canonical_localized_manual_presentation():
    package_handler = _source_between(
        "async def handle_package_choice(",
        "async def handle_manual_package_choice(",
    )
    branch = package_handler[
        package_handler.index('if pkg_key.startswith("manual_"):'):
        package_handler.index("if pkg_key not in PAYMENT_PACKAGES:")
    ]

    assert 'if locale != "vi":' in branch
    international_start = branch.index('if locale != "vi":')
    international_end = branch.find("\n            await query.edit_message_text(", international_start)
    assert international_end > international_start
    international_branch = branch[international_start:international_end]
    assert "manual_payment_menu_text(uid, lang)" in international_branch or "manual_payment_method_text(" in international_branch
    assert "manual_payment_menu_keyboard(uid, lang)" in international_branch or "manual_method_keyboard(uid, lang)" in international_branch
    for vietnamese_literal in (
        "Bạn đã chọn nạp thủ công.",
        "QR thủ công theo đúng số tiền và nội dung chuyển khoản.",
    ):
        assert vietnamese_literal not in international_branch


def test_existing_locale_callback_bridge_imports_public_copy_authorities():
    """Pricing and manual top-up both use this existing public-copy helper."""

    import_block = _source_between(
        "from services.pricing_guide_content import (",
        ")\nfrom video_multiscene_engine import (",
    )
    assert "    public_copy_locale," in import_block
    assert "    public_hub_copy," in import_block


def test_existing_main_menu_keeps_language_entry_in_the_compact_hub_layout():
    menu_source = _source_between(
        "def localized_main_menu_keyboard",
        "def localized_start_menu_text",
    )
    picker_source = _source_between(
        "def language_choice_keyboard",
        "def other_language_choice_text",
    )

    assert "copy = public_hub_copy(lang)" in menu_source
    assert 'callback_data="menu|support"' in menu_source
    assert 'callback_data="back_lang"' in menu_source
    assert 'callback_data="menu|main"' in menu_source
    assert "for locale in USER_LANGUAGE_ORDER" in picker_source
    assert "rows.append([" in picker_source
    assert 'callback_data="lang_back"' in picker_source


def test_existing_background_music_price_is_130_in_button_and_runtime_map():
    source = _source()

    assert 'MUSIC_PRODUCT_TIER_BASIC: "🎵 Cơ bản — 130 Xu"' in source
    assert "MUSIC_PRODUCT_BACKGROUND_TIER_PRICES = {\n    MUSIC_PRODUCT_TIER_BASIC: 130," in source
