import ast
import asyncio
import html
import re
import sys
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services import pricing_guide_content as public_copy


BOT_SOURCE = (REPO_ROOT / "bot.py").read_text(encoding="utf-8")
SUPPORTED_LOCALES = (
    "vi", "en", "zh", "ja", "ko", "th", "ar", "es", "pt", "fr", "de",
    "hi", "ru", "tr", "fil", "it", "id",
)
NATIVE_FIELDS = (
    "hub_title",
    "hub_intro",
    "image_description",
    "video_description",
    "music_description",
    "voice_description",
    "chat_description",
    "guide_description",
    "support",
    "center",
    "change_language",
    "main_menu",
)
AUXILIARY_FIELDS = (
    "back",
    "manual_topup",
    "packages_label",
    "account_label",
    "topup_label",
    "vietnamese_docx",
    "language_picker_title",
    "language_picker_intro",
)
PACKAGE_NAVIGATION_FIELDS = (
    "monthly_plans",
    "finished_combos",
    "my_packages",
    "large_order",
    "notes",
    "refresh",
    "confirm_purchase",
)
EXACT_ENGLISH_LABEL_WHITELIST = {
    ("fil", "account_label"),
    ("it", "account_label"),
}
SCRIPT_RANGES = {
    "zh": r"[\u3400-\u9fff]",
    "ko": r"[\uac00-\ud7af]",
    "ja": r"[\u3040-\u30ff\u3400-\u9fff]",
    "th": r"[\u0e00-\u0e7f]",
    "ru": r"[\u0400-\u04ff]",
    "ar": r"[\u0600-\u06ff]",
    "hi": r"[\u0900-\u097f]",
}


def _assignment(name: str):
    match = re.search(rf"^\s*{name}\s*=\s*(\{{[\s\S]*?^\s*\}})", BOT_SOURCE, re.MULTILINE)
    assert match is not None, f"missing assignment: {name}"
    return ast.literal_eval(match.group(1))


def _tuple_assignment(name: str):
    match = re.search(rf"^\s*{name}\s*=\s*(\([\s\S]*?\))", BOT_SOURCE, re.MULTILINE)
    assert match is not None, f"missing tuple assignment: {name}"
    return ast.literal_eval(match.group(1))


def _function_source(name: str) -> str:
    start = BOT_SOURCE.index(f"def {name}(")
    following = re.search(r"\n(?:async )?def ", BOT_SOURCE[start + 1 :])
    end = -1 if following is None else start + 1 + following.start()
    return BOT_SOURCE[start:] if end < 0 else BOT_SOURCE[start:end]


def _async_function_source(name: str) -> str:
    start = BOT_SOURCE.index(f"async def {name}(")
    following = re.search(r"\n(?=(?:async )?def |@)", BOT_SOURCE[start + 1 :])
    end = -1 if following is None else start + 1 + following.start()
    return BOT_SOURCE[start:] if end < 0 else BOT_SOURCE[start:end]


class _Button:
    def __init__(self, text: str, callback_data: str | None = None, url: str | None = None, **_kwargs):
        self.text = text
        self.callback_data = callback_data
        self.url = url


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


def _runtime_namespace() -> dict:
    namespace = {
        "__builtins__": __builtins__,
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "TOAN_AAS_COMMUNITY_URL": "https://t.me/toanaas",
        "product_context_callback": lambda *parts: "context|" + "|".join(str(part) for part in parts),
        "PRODUCT_CONTEXT_SHOWROOM": "showroom",
        "public_chat_runtime": SimpleNamespace(CHAT_PRO_RATE_LABEL="5/25 Xu/1K"),
        "public_hub_copy": public_copy.public_hub_copy,
        "get_user": lambda _user_id: (90, 0, False),
        "is_admin_user": lambda _user_id: False,
        "get_role_badge": lambda _user_id: "Newbie",
        "html": html,
    }
    locale_start = BOT_SOURCE.index("USER_LANGUAGE_LABELS =")
    locale_end = BOT_SOURCE.index("\ndef normalize_user_market", locale_start)
    exec(BOT_SOURCE[locale_start:locale_end], namespace)
    for function_name in (
        "user_language_label",
        "language_choice_text",
        "language_choice_keyboard",
        "other_language_choice_text",
        "other_language_choice_keyboard",
        "localized_main_menu_keyboard",
        "localized_start_menu_text",
    ):
        exec(_function_source(function_name), namespace)
    return namespace


def _pricing_runtime_namespace() -> dict:
    namespace = {
        "__builtins__": __builtins__,
        "public_copy_locale": public_copy.public_copy_locale,
        "public_pricing_locale": public_copy.public_copy_locale,
        "public_pricing_context": lambda: {"source": "native-hub-test"},
        "public_pricing_lines": public_copy.pricing_lines,
        "user_is_vietnam_market": lambda _user_id: False,
    }
    locale_start = BOT_SOURCE.index("USER_LANGUAGE_LABELS =")
    locale_end = BOT_SOURCE.index("\ndef normalize_user_market", locale_start)
    exec(BOT_SOURCE[locale_start:locale_end], namespace)
    exec(_function_source("pricing_hub_lines"), namespace)
    return namespace


def _pricing_keyboard_runtime_namespace() -> dict:
    namespace = {
        "__builtins__": __builtins__,
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "public_copy_locale": public_copy.public_copy_locale,
        "public_pricing_locale": public_copy.public_copy_locale,
        "public_hub_copy": public_copy.public_hub_copy,
        "public_page_title": public_copy.public_page_title,
        "user_is_vietnam_market": lambda _user_id: False,
    }
    locale_start = BOT_SOURCE.index("USER_LANGUAGE_LABELS =")
    locale_end = BOT_SOURCE.index("\ndef normalize_user_market", locale_start)
    exec(BOT_SOURCE[locale_start:locale_end], namespace)
    exec(_function_source("pricing_main_keyboard"), namespace)
    exec(_function_source("pricing_catalog_keyboard"), namespace)
    return namespace


def _picker_locale_codes(markup) -> list[str]:
    return [
        button.callback_data.split("|", 1)[1]
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data and button.callback_data.startswith("lang|")
    ]


def test_user_locale_registry_and_main_picker_are_exact_and_deduplicated():
    labels = _assignment("USER_LANGUAGE_LABELS")
    assert set(labels) == set(SUPPORTED_LOCALES)
    assert _tuple_assignment("USER_LANGUAGE_ORDER") == SUPPORTED_LOCALES
    flags = _assignment("USER_LANGUAGE_FLAGS")
    assert set(flags) == set(SUPPORTED_LOCALES)

    runtime = _runtime_namespace()
    picker = runtime["language_choice_keyboard"]()
    picker_codes = _picker_locale_codes(picker)
    assert tuple(picker_codes) == SUPPORTED_LOCALES
    assert len(picker_codes) == len(set(picker_codes))
    assert all(runtime["normalize_user_language"](locale) == locale for locale in SUPPORTED_LOCALES)

    locale_rows = [
        row for row in picker.inline_keyboard
        if any(button.callback_data and button.callback_data.startswith("lang|") for button in row)
    ]
    assert all(len(row) == 2 for row in locale_rows[:-1])
    assert len(locale_rows[-1]) == 1  # 17 supported locales leave one genuine final locale.
    nav_rows = [row for row in picker.inline_keyboard if row not in locale_rows]
    assert len(nav_rows) == 1
    assert all(not (button.callback_data or "").startswith("lang|") for button in nav_rows[0])
    assert [button.callback_data for button in nav_rows[0]] == ["lang_back", "menu|main"]
    for row in locale_rows:
        for button in row:
            locale = button.callback_data.split("|", 1)[1]
            assert button.text.startswith(flags[locale])

    assert runtime["pricing_copy_language"]("vi") == "vi"
    assert runtime["pricing_copy_language"]("zh") == "zh"
    for locale in SUPPORTED_LOCALES:
        if locale not in {"vi", "zh"}:
            assert runtime["pricing_copy_language"](locale) == "en"


def test_hub_layout_has_five_two_button_rows_and_preserves_existing_routes():
    runtime = _runtime_namespace()
    for locale in SUPPORTED_LOCALES:
        markup = runtime["localized_main_menu_keyboard"](False, locale)
        assert len(markup.inline_keyboard) == 5
        assert [len(row) for row in markup.inline_keyboard] == [2, 2, 2, 2, 2]
        assert [button.callback_data for button in markup.inline_keyboard[0]] == [
            "menu|main_image", "menu|main_video",
        ]
        assert markup.inline_keyboard[1][0].callback_data.startswith("context|")
        assert markup.inline_keyboard[1][1].callback_data == "menu|translate"
        assert [button.callback_data for button in markup.inline_keyboard[2]] == [
            "menu|chat_pro", "menu|main_guide",
        ]
        assert markup.inline_keyboard[3][0].callback_data == "menu|support"
        assert markup.inline_keyboard[3][1].url == "https://t.me/toanaas"
        assert [button.callback_data for button in markup.inline_keyboard[4]] == [
            "back_lang", "menu|main",
        ]
        callbacks = [
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.callback_data
        ]
        assert len(callbacks) == len(set(callbacks))
        assert not any("❌" in button.text for row in markup.inline_keyboard for button in row)


def test_public_hub_copy_is_direct_native_copy_not_english_fallback():
    english = public_copy.public_hub_copy("en")
    assert set(english) >= set(NATIVE_FIELDS)

    for locale in SUPPORTED_LOCALES:
        copy = public_copy.public_hub_copy(locale)
        assert set(copy) >= set(NATIVE_FIELDS)
        assert all(str(copy[field]).strip() for field in NATIVE_FIELDS)
        if locale == "en":
            continue
        body_fields = ("hub_intro", "image_description", "video_description", "music_description", "voice_description", "chat_description", "guide_description")
        assert all(copy[field] != english[field] for field in body_fields)

    for locale, pattern in SCRIPT_RANGES.items():
        copy = public_copy.public_hub_copy(locale)
        body = "\n".join(copy[field] for field in NATIVE_FIELDS[:8])
        assert len(re.findall(pattern, body)) >= 8, locale

    for locale in ("vi", "es", "pt", "fr", "de", "tr", "fil", "it", "id"):
        copy = public_copy.public_hub_copy(locale)
        distinct = sum(copy[field].casefold() != english[field].casefold() for field in NATIVE_FIELDS[:8])
        assert distinct >= 6, locale

    for locale in SUPPORTED_LOCALES:
        copy = public_copy.public_hub_copy(locale)
        assert all(copy[field].strip() for field in AUXILIARY_FIELDS)
        if locale == "en":
            continue
        for field in AUXILIARY_FIELDS:
            assert (locale, field) in EXACT_ENGLISH_LABEL_WHITELIST or copy[field].casefold() != english[field].casefold(), (locale, field)

    for locale in SUPPORTED_LOCALES:
        if locale in {"vi", "en", "zh"}:
            continue
        copy = public_copy.public_hub_copy(locale)
        assert all(copy[field].strip() for field in PACKAGE_NAVIGATION_FIELDS), locale


def test_start_hub_uses_the_selected_native_body_and_never_claims_english_fallback():
    runtime = _runtime_namespace()
    for locale in SUPPORTED_LOCALES:
        copy = public_copy.public_hub_copy(locale)
        text = runtime["localized_start_menu_text"](12345, locale)
        assert copy["hub_intro"] in text
        for field in ("image_description", "video_description", "music_description", "voice_description", "chat_description", "guide_description"):
            assert copy[field] in text
        assert "Interface fallback: English" not in text
        assert "English tạm thời" not in text


def test_language_picker_copy_no_longer_promises_temporary_english():
    runtime = _runtime_namespace()
    text = runtime["other_language_choice_text"]()
    assert "English tạm thời" not in text
    assert "Interface fallback" not in text


def test_legacy_lang_more_returns_the_canonical_primary_picker():
    source = _async_function_source("handle_language_callback")
    assert 'if data == "lang_more":' in source
    assert "language_choice_text(current_lang)" in source
    assert "reply_markup=language_choice_keyboard(current_lang)" in source


def test_language_picker_back_route_returns_to_the_existing_localized_hub():
    source = _async_function_source("handle_language_callback")
    assert 'if data == "lang_back":' in source
    assert "localized_start_menu_text(uid, previous_lang)" in source
    assert "localized_main_menu_keyboard(is_admin_user(uid), previous_lang)" in source
    assert 'back_lang|lang_back' in BOT_SOURCE


def test_secondary_public_price_surfaces_use_native_shared_copy_not_english_fallback():
    """A selected secondary locale must not reopen legacy English billing copy."""
    namespace = {
        "__builtins__": __builtins__,
        "normalize_user_language": lambda value: str(value or "").lower() or "vi",
        "public_pricing_locale": public_copy.public_copy_locale,
        "user_is_vietnam_market": lambda _user_id: False,
        "foreign_topup_policy_note": lambda _lang: "policy",
        "public_guide_lines": public_copy.guide_lines,
        "public_pricing_lines": public_copy.pricing_lines,
        "public_pricing_context": lambda: {"member_discount_lines": ["• 0%"]},
        "pricing_copy_language": lambda lang: "vi" if lang == "vi" else ("zh" if lang == "zh" else "en"),
        "MEMBER_TOOL_DISCOUNT_POLICY": {tier: 0 for tier in ("newbie", "silver", "gold", "platinum", "diamond", "vip")},
    }
    for name in (
        "menu_text_main_topup_i18n",
        "pricing_xu_lines_i18n",
        "pricing_packages_lines",
        "pricing_pkgcombo_notes_lines",
        "member_policy_lines",
    ):
        exec(_function_source(name), namespace)

    for locale, pattern in {"es": r"[áéíóúñ]", "ko": SCRIPT_RANGES["ko"], "th": SCRIPT_RANGES["th"], "ar": SCRIPT_RANGES["ar"]}.items():
        topup = namespace["menu_text_main_topup_i18n"](locale, "intl-user")
        xu = "\n".join(namespace["pricing_xu_lines_i18n"](locale, "intl-user"))
        packages = "\n".join(namespace["pricing_packages_lines"](locale))
        notes = "\n".join(namespace["pricing_pkgcombo_notes_lines"](locale))
        member = "\n".join(namespace["member_policy_lines"](locale))
        for rendered in (topup, xu, packages, notes, member):
            assert re.search(pattern, rendered), (locale, rendered)
            assert "INTERNATIONAL XU TOP-UP" not in rendered
            assert "Plans / Combos" not in rendered
            assert "Member tiers" not in rendered


def test_secondary_locale_copy_truthfully_labels_manual_topup_and_vietnamese_docx():
    english = public_copy.public_hub_copy("en")
    for locale, pattern in {"es": None, "ko": SCRIPT_RANGES["ko"], "th": SCRIPT_RANGES["th"], "ar": SCRIPT_RANGES["ar"]}.items():
        copy = public_copy.public_hub_copy(locale)
        if pattern:
            assert re.search(pattern, copy["manual_topup"]), locale
            assert re.search(pattern, copy["vietnamese_docx"]), locale
        else:
            assert copy["manual_topup"].casefold() != english["manual_topup"].casefold()
            assert copy["vietnamese_docx"].casefold() != english["vietnamese_docx"].casefold()
        assert "DOCX • VI" not in copy["vietnamese_docx"]


def test_current_pricing_and_music_basic_130_are_preserved_in_the_public_sources():
    assert re.search(
        r"MUSIC_PRODUCT_BACKGROUND_TIER_PRICES\s*=\s*\{[\s\S]*?MUSIC_PRODUCT_TIER_BASIC\s*:\s*130",
        BOT_SOURCE,
    )
    assert 'MUSIC_PRODUCT_TIER_BASIC: "🎵 Cơ bản — 130 Xu"' in BOT_SOURCE
    for locale in SUPPORTED_LOCALES:
        music_lines = "\n".join(public_copy.pricing_lines("music", lang=locale))
        assert "130" in music_lines


def test_chinese_public_package_video_label_is_native_not_english():
    """A customer-facing Chinese package label must not regress to English."""
    start = BOT_SOURCE.index("_PACKAGE_GROUP_LABELS_I18N =")
    english_start = BOT_SOURCE.index('    "en": {', start)
    chinese_start = BOT_SOURCE.index('    "zh": {', english_start)
    end = BOT_SOURCE.index("\n\n\ndef package_i18n_group_label", chinese_start)
    assert '"video": "🎬 Product Video"' in BOT_SOURCE[english_start:chinese_start]
    assert '"video": "🎬 产品视频"' in BOT_SOURCE[chinese_start:end]


def test_chinese_public_pricing_and_guides_do_not_show_english_product_video():
    """Chinese customer copy must consistently use the localized product name."""
    surfaces = (
        public_copy.all_pricing_lines({}, "zh")
        + public_copy.all_guide_lines("zh")
    )
    assert "Product Video" not in "\n".join(surfaces)


def _secondary_package_runtime_namespace() -> dict:
    """Load package display functions without importing the full bot runtime."""
    entry = {
        "group": "image",
        "items": {"image_standard": 1},
        "default_days": 30,
        "public": True,
    }

    def package_label(_entry, _code, _package_type, lang):
        return f"🖼 {public_copy.public_hub_copy(lang)['image_label']}"

    namespace = {
        "__builtins__": __builtins__,
        "html": html,
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "public_pricing_locale": public_copy.public_copy_locale,
        "public_hub_copy": public_copy.public_hub_copy,
        "public_guide_lines": public_copy.guide_lines,
        "public_page_title": public_copy.public_page_title,
        "pricing_copy_language": lambda lang: "vi" if lang == "vi" else ("zh" if lang == "zh" else "en"),
        "public_video_combo_pricing_payload": lambda: [{"code": "image_combo", **entry}],
        "public_task_package_entries": lambda _group: [("image_monthly", entry)],
        "package_catalog_entry": lambda _code, _package_type: entry,
        "package_i18n_group_label": lambda _group, lang: f"🖼 {public_copy.public_hub_copy(lang)['image_label']}",
        "package_i18n_entry_label": package_label,
        "package_i18n_button_label": package_label,
        "package_i18n_items_summary": lambda _items, lang: public_copy.public_hub_copy(lang)["image_label"],
        "package_i18n_price_text": lambda *_args: "123k",
        "package_purchase_price_vnd": lambda *_args: 123000,
        "package_price_quote": lambda *_args: {"price_vnd": 123000, "retail_vnd": 123000, "discount_percent": 0},
        "package_entry_auto_checkout_enabled": lambda _entry: True,
        "package_detail_back_callback": lambda *_args: "pkgcombo:home",
        "pkgcombo_large_order_callback": lambda *_args, **_kwargs: "pkgcombo:large_order:home",
        "pkgcombo_normalize_group": lambda value: str(value or "").strip().lower(),
        "pricing_plans_lines_i18n": lambda lang: public_copy.guide_lines("packages", lang),
    }
    for function_name in (
        "pricing_combo_lines",
        "pricing_combo_keyboard",
        "pricing_packages_keyboard",
        "pricing_plans_keyboard",
        "my_packages_keyboard",
        "pricing_task_package_group_lines",
        "pricing_task_package_group_keyboard",
        "package_purchase_detail_lines",
        "package_purchase_manual_keyboard",
        "package_purchase_confirm_keyboard",
    ):
        exec(_function_source(function_name), namespace)
    return namespace


def test_secondary_package_routes_keep_native_copy_without_changing_callbacks():
    runtime = _secondary_package_runtime_namespace()

    for locale in (locale for locale in SUPPORTED_LOCALES if locale not in {"vi", "en", "zh"}):
        copy = public_copy.public_hub_copy(locale)
        combo_lines = "\n".join(runtime["pricing_combo_lines"](locale))
        group_lines = "\n".join(runtime["pricing_task_package_group_lines"]("image", locale))
        detail_lines = "\n".join(runtime["package_purchase_detail_lines"]("monthly", "image_monthly", locale))
        for rendered in (combo_lines, group_lines, detail_lines):
            assert copy["packages_label"] in rendered
            assert "Finished Combos" not in rendered
            assert "Benefits" not in rendered
            assert "Retail price" not in rendered

        keyboards = (
            runtime["pricing_combo_keyboard"](locale),
            runtime["my_packages_keyboard"](locale),
            runtime["pricing_task_package_group_keyboard"]("image", locale),
            runtime["package_purchase_manual_keyboard"]("monthly", "image_monthly", locale),
            runtime["package_purchase_confirm_keyboard"]("monthly", "image_monthly", locale),
        )
        for markup in keyboards:
            labels = "\n".join(button.text for row in markup.inline_keyboard for button in row)
            assert copy["packages_label"] in labels or copy["main_menu"] in labels
            assert "Main menu" not in labels
            assert "Confirm purchase" not in labels

    for locale, pattern in {"ko": SCRIPT_RANGES["ko"], "ja": SCRIPT_RANGES["ja"], "th": SCRIPT_RANGES["th"], "ru": SCRIPT_RANGES["ru"], "ar": SCRIPT_RANGES["ar"], "hi": SCRIPT_RANGES["hi"]}.items():
        rendered = "\n".join(runtime["pricing_combo_lines"](locale))
        assert re.search(pattern, rendered), (locale, rendered)

    detail_source = _async_function_source("render_pkgcombo_detail")
    assert "requested_locale = public_pricing_locale(lang)" in detail_source
    assert "package_purchase_detail_lines(package_type, code, requested_locale)" in detail_source


def test_member_command_routes_secondary_locales_to_native_member_policy_copy():
    source = _async_function_source("cmd_member")
    assert "requested_locale = public_pricing_locale(lang)" in source
    assert 'if requested_locale not in {"vi", "en", "zh"}:' in source
    assert "member_policy_lines(requested_locale)" in source


def test_secondary_package_navigation_has_distinct_native_actions():
    runtime = _secondary_package_runtime_namespace()
    for locale, pattern in {"ko": SCRIPT_RANGES["ko"], "es": r"[áéíóúñ]"}.items():
        copy = public_copy.public_hub_copy(locale)
        required_keys = ("monthly_plans", "finished_combos", "my_packages", "large_order", "notes", "refresh", "confirm_purchase")
        assert all(copy.get(key) for key in required_keys), locale

        package_labels = "\n".join(
            button.text
            for row in runtime["pricing_packages_keyboard"](locale).inline_keyboard
            for button in row
        )
        plan_labels = "\n".join(
            button.text
            for row in runtime["pricing_plans_keyboard"](locale).inline_keyboard
            for button in row
        )
        assert copy["monthly_plans"] in package_labels
        assert copy["finished_combos"] in package_labels
        assert copy["my_packages"] in package_labels
        assert copy["large_order"] in package_labels
        assert copy["notes"] in plan_labels
        assert re.search(pattern, package_labels), (locale, package_labels)


def test_secondary_pricing_hub_keeps_the_existing_package_entry_with_native_copy():
    runtime = _pricing_keyboard_runtime_namespace()
    for locale in ("ko", "es"):
        copy = public_copy.public_hub_copy(locale)
        markup = runtime["pricing_main_keyboard"](locale, "intl-user")
        callbacks = [
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.callback_data
        ]
        labels = "\n".join(button.text for row in markup.inline_keyboard for button in row)
        assert "pkgcombo:home" in callbacks
        assert copy["packages_label"] in labels


def test_secondary_pricing_hub_uses_the_existing_native_public_price_copy():
    runtime = _pricing_runtime_namespace()
    for locale, pattern in SCRIPT_RANGES.items():
        text = "\n".join(runtime["pricing_hub_lines"](locale, "intl-user"))
        assert re.search(pattern, text), locale
        assert "International Top-up" not in text
        assert "+30% Xu" not in text

    english = "\n".join(runtime["pricing_hub_lines"]("en", "intl-user"))
    for locale in ("vi", "es", "pt", "fr", "de", "tr", "fil", "it", "id"):
        text = "\n".join(runtime["pricing_hub_lines"](locale, "intl-user"))
        assert text != english


def test_korean_pricing_navigation_uses_native_labels_without_changing_routes():
    runtime = _pricing_keyboard_runtime_namespace()
    main = runtime["pricing_main_keyboard"]("ko", "intl-user")
    catalog = runtime["pricing_catalog_keyboard"]("ko")
    for markup in (main, catalog):
        labels = "\n".join(button.text for row in markup.inline_keyboard for button in row)
        callbacks = [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]
        assert re.search(SCRIPT_RANGES["ko"], labels)
        assert "Pricing" not in labels
        assert len(callbacks) == len(set(callbacks))


def test_public_price_guide_help_and_download_routes_keep_the_requested_locale():
    for name in (
        "download_pricing_markdown",
        "download_guide_markdown",
        "public_pricing_page",
        "public_guide_page",
        "public_help_page",
    ):
        source = _async_function_source(name)
        assert "lang: str = \"vi\"" in source
        assert "requested_locale = public_pricing_locale(lang)" in source

    for name in ("public_pricing_page", "public_guide_page", "public_help_page"):
        source = _async_function_source(name)
        assert "public_page_title" in source


def test_public_routes_render_selected_native_price_and_guide_copy_without_bot_import():
    rendered = {}

    def render_html(value):
        return value

    def render_page(title, lines, **kwargs):
        return {"title": title, "lines": list(lines), "kwargs": kwargs}

    def render_markdown(filename, content):
        return {"filename": filename, "content": content}

    namespace = {
        "HTMLResponse": render_html,
        "markdown_attachment_response": render_markdown,
        "public_pricing_locale": public_copy.public_copy_locale,
        "public_page_title": public_copy.public_page_title,
        "public_pricing_context": lambda: {"source": "native-hub-test"},
        "public_pricing_all_lines": public_copy.all_pricing_lines,
        "public_guide_all_lines": public_copy.all_guide_lines,
        "public_pricing_markdown": public_copy.pricing_markdown,
        "public_guide_markdown": public_copy.guide_markdown,
        "public_lines_to_html_page": render_page,
        "PRICING_DOWNLOAD_FILENAME": "pricing.md",
        "GUIDE_DOWNLOAD_FILENAME": "guide.md",
    }
    for name in (
        "download_pricing_markdown",
        "download_guide_markdown",
        "public_pricing_page",
        "public_guide_page",
        "public_help_page",
    ):
        exec(_async_function_source(name), namespace)

    korean_pricing = asyncio.run(namespace["public_pricing_page"]("ko"))
    korean_guide = asyncio.run(namespace["public_help_page"]("ko"))
    pricing_download = asyncio.run(namespace["download_pricing_markdown"]("ko"))
    guide_download = asyncio.run(namespace["download_guide_markdown"]("ko"))
    assert korean_pricing["title"] == public_copy.public_page_title("pricing", "ko")
    assert korean_guide["title"] == public_copy.public_page_title("guide", "ko")
    assert korean_pricing["kwargs"] == {"lang": "ko", "home_href": "/?lang=ko"}
    assert korean_guide["kwargs"] == {"lang": "ko", "home_href": "/?lang=ko"}
    assert any(re.search(SCRIPT_RANGES["ko"], line) for line in korean_pricing["lines"])
    assert any(re.search(SCRIPT_RANGES["ko"], line) for line in korean_guide["lines"])
    assert re.search(SCRIPT_RANGES["ko"], pricing_download["content"])
    assert re.search(SCRIPT_RANGES["ko"], guide_download["content"])


def test_secondary_guide_hub_imports_and_uses_native_public_copy_before_displaying_actions():
    import_block = BOT_SOURCE[
        BOT_SOURCE.index("from services.pricing_guide_content import ("):
        BOT_SOURCE.index(")\nfrom video_multiscene_engine import (")
    ]
    assert "    guide_index_lines as public_guide_index_lines," in import_block
    assert "public_guide_index_lines(public_pricing_locale(lang))" in _function_source("menu_text_main_guide_i18n")
    assert "public_hub_copy" in _function_source("main_guide_keyboard")
    assert "public_hub_copy" in _function_source("guide_keyboard")


def test_korean_guide_hub_and_actions_render_native_labels_without_full_bot_import():
    namespace = {
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "normalize_user_language": lambda value: str(value or "").lower() or "vi",
        "normalize_guide_section_key": lambda value: str(value or "").lower(),
        "public_pricing_locale": public_copy.public_copy_locale,
        "public_hub_copy": public_copy.public_hub_copy,
        "public_page_title": public_copy.public_page_title,
        "public_guide_index_lines": public_copy.guide_index_lines,
        "effective_public_base_url": lambda: "",
        "menu_text_main_guide": lambda: "Vietnamese guide",
    }
    for name in ("guide_keyboard", "main_guide_keyboard", "menu_text_main_guide_i18n"):
        exec(_function_source(name), namespace)

    text = namespace["menu_text_main_guide_i18n"]("ko")
    root = namespace["main_guide_keyboard"]("ko")
    section = namespace["guide_keyboard"]("quick_start", "ko")
    root_labels = [button.text for row in root.inline_keyboard for button in row]
    section_labels = [button.text for row in section.inline_keyboard for button in row]
    assert re.search(SCRIPT_RANGES["ko"], text)
    assert any(re.search(SCRIPT_RANGES["ko"], label) for label in root_labels)
    assert any(re.search(SCRIPT_RANGES["ko"], label) for label in section_labels)
    assert "Quick start" not in "\n".join(root_labels + section_labels)


def test_chinese_topup_and_guide_navigation_keep_existing_callbacks_with_native_copy():
    """Chinese public entry menus must not fall through the legacy English/Vietnamese labels."""
    namespace = {
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "normalize_user_language": lambda value: str(value or "").lower() or "vi",
        "public_pricing_locale": public_copy.public_copy_locale,
        "public_hub_copy": public_copy.public_hub_copy,
        "public_page_title": public_copy.public_page_title,
        "public_guide_navigation_copy": public_copy.public_guide_navigation_copy,
        "payos_package_callback_data": lambda package, uid: f"payos|{package}|{uid}",
        "manual_package_callback_data": lambda package, uid: f"manual|{package}|{uid}",
        "ui_text": lambda _lang, _key: "主菜单",
        "TOAN_AAS_COMMUNITY_URL": "https://t.me/toanaas",
    }
    for name in ("main_topup_keyboard", "main_guide_keyboard"):
        exec(_function_source(name), namespace)

    topup = namespace["main_topup_keyboard"]("zh", 123)
    guide = namespace["main_guide_keyboard"]("zh")
    topup_labels = "\n".join(button.text for row in topup.inline_keyboard for button in row)
    guide_labels = "\n".join(button.text for row in guide.inline_keyboard for button in row)
    topup_callbacks = [button.callback_data for row in topup.inline_keyboard for button in row if button.callback_data]
    guide_callbacks = [button.callback_data for row in guide.inline_keyboard for button in row if button.callback_data]

    assert "手动充值" in topup_labels
    assert "TOAN AAS 价格" in topup_labels
    assert all(label not in topup_labels for label in ("Nạp thủ công", "Back to pricing"))
    assert all(label not in guide_labels for label in ("Quick start", "Create image", "Create video", "Video music", "Xu & top-up", "FAQ & refunds", "Main menu"))
    assert len(re.findall(SCRIPT_RANGES["zh"], guide_labels)) >= 10
    assert topup_callbacks == [
        "payos|10k|123", "payos|20k|123", "payos|50k|123", "payos|100k|123",
        "payos|200k|123", "payos|500k|123", "manual|manual_custom|123", "pricing|main", "menu|main",
    ]
    assert guide_callbacks == [
        "menu|guide_quick_start", "menu|guide_image_ai", "menu|guide_video_ai", "menu|guide_guided_video",
        "menu|guide_music_add", "menu|guide_credits", "menu|guide_faq", "menu|support",
        "pricing|download_pricing", "pricing|download_guide", "menu|main",
    ]
