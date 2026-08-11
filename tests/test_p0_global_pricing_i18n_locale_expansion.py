import asyncio
import ast
import json
import re
import shutil
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services import video_ai_real_pricing as canonical
from services import pricing_guide_content as public_copy
from services.pricing_guide_content import guide_lines as shared_public_guide_lines

BOT_SOURCE = (REPO_ROOT / "bot.py").read_text(encoding="utf-8")
LANDING_SOURCE = (REPO_ROOT / "index.html").read_text(encoding="utf-8")

REQUESTED_LOCALES = (
    "vi", "en", "zh", "es", "pt", "fr", "de", "ja", "ko", "hi", "ar",
    "ru", "tr", "th", "fil", "it", "id",
)
NEW_LOCALES = ("es", "pt", "fr", "de", "hi", "ru", "tr", "fil", "it", "id")
EXISTING_LOCALES = ("vi", "en", "zh", "ja", "ko", "th", "ar")
PRICING_FALLBACK_SURFACES = (
    "pricing_catalog_keyboard",
    "pricing_packages_keyboard",
    "pricing_plans_keyboard",
    "pricing_pkgcombo_notes_lines",
    "pricing_pkgcombo_notes_keyboard",
    "pricing_package_summary_lines",
    "pricing_package_summary_keyboard",
    "pricing_hub_lines",
    "billing_promotions_lines",
    "billing_promotions_keyboard",
    "billing_promo_apply_lines",
    "member_policy_lines",
    "member_policy_keyboard",
)


def _function_source(name: str) -> str:
    start = BOT_SOURCE.index(f"def {name}(")
    following = re.search(r"\n(?:async )?def ", BOT_SOURCE[start + 1:])
    end = -1 if following is None else start + 1 + following.start()
    return BOT_SOURCE[start:] if end < 0 else BOT_SOURCE[start:end]


def _async_function_source(name: str) -> str:
    start = BOT_SOURCE.index(f"async def {name}(")
    following = re.search(r"\n(?:async )?def ", BOT_SOURCE[start + 1:])
    end = -1 if following is None else start + 1 + following.start()
    return BOT_SOURCE[start:] if end < 0 else BOT_SOURCE[start:end]


def _literal_assignment(name: str):
    match = re.search(rf"^\s*{name}\s*=\s*(\{{[\s\S]*?^\s*\}})", BOT_SOURCE, re.MULTILINE)
    assert match is not None
    return ast.literal_eval(match.group(1))


class _Button:
    def __init__(self, text: str, callback_data: str | None = None, **_kwargs):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class _Html:
    @staticmethod
    def escape(value):
        return str(value)


def _runtime_namespace() -> dict:
    namespace = {
        "__builtins__": __builtins__,
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "html": _Html,
        "MEMBER_TOOL_DISCOUNT_POLICY": {tier: 0 for tier in ("newbie", "silver", "gold", "platinum", "diamond", "vip")},
        "MEMBER_TIER_THRESHOLDS": {tier: 0 for tier in ("silver", "gold", "platinum", "diamond", "vip")},
        "MEMBER_BIRTHDAY_GIFT_XU": {tier: 0 for tier in ("silver", "gold", "platinum", "diamond", "vip")},
        "user_is_vietnam_market": lambda user_id: str(user_id) == "vn-user",
        "package_catalog_payload": lambda: {"monthly": {}},
        "package_purchase_display_price": lambda _kind, _code: "-",
        "public_video_combo_pricing_payload": lambda: [],
    }
    locale_start = BOT_SOURCE.index("USER_LANGUAGE_LABELS =")
    locale_end = BOT_SOURCE.index("\ndef normalize_user_market", locale_start)
    exec(BOT_SOURCE[locale_start:locale_end], namespace)
    for function_name in (
        "normalize_user_market",
        "canonical_user_market_snapshot_conn",
        "language_choice_keyboard",
        "other_language_choice_keyboard",
        "pricing_main_keyboard",
        "pricing_catalog_keyboard",
        "pricing_packages_keyboard",
        "pricing_plans_keyboard",
        "member_policy_keyboard",
        "pricing_hub_lines",
        "billing_promotions_lines",
        "billing_promotions_keyboard",
        "billing_promo_apply_lines",
        "pricing_catalog_lines",
        "pricing_packages_lines",
        "pricing_pkgcombo_notes_lines",
        "pricing_pkgcombo_notes_keyboard",
        "pricing_package_summary_lines",
        "pricing_package_summary_keyboard",
        "public_pricing_markdown",
        "pricing_combo_keyboard",
        "my_packages_keyboard",
        "member_policy_lines",
    ):
        exec(_function_source(function_name), namespace)
    return namespace


def _guide_i18n_runtime_namespace() -> dict:
    namespace = {
        "__builtins__": __builtins__,
        "normalize_user_language": lambda value: str(value or "").lower() or "vi",
        "normalize_guide_section_key": lambda value: str(value or "").lower(),
        "guide_section_text": lambda _value: "Vietnamese guide",
        "guide_index_text_i18n": lambda _lang: "Guide index",
        "public_pricing_locale": lambda lang: str(lang or "vi"),
        "public_guide_lines": shared_public_guide_lines,
        "video_ai_real_pricing": canonical,
    }
    exec(_function_source("guide_section_text_i18n"), namespace)
    return namespace


def _guide_keyboard_runtime_namespace() -> dict:
    namespace = {
        "__builtins__": __builtins__,
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "normalize_user_language": lambda value: str(value or "").lower() or "vi",
        "normalize_guide_section_key": lambda value: str(value or "").lower(),
        "effective_public_base_url": lambda: "https://public.example",
    }
    exec(_function_source("guide_keyboard"), namespace)
    return namespace


def _shared_pricing_runtime_namespace() -> dict:
    namespace = {
        "__builtins__": __builtins__,
        "pricing_copy_language": lambda lang: "vi" if lang == "vi" else "en",
        "public_pricing_locale": lambda lang: str(lang or "vi"),
        "public_pricing_context": lambda: {"source": "test"},
        "public_pricing_lines": lambda section, _context, lang="vi": [f"{section}:{lang}"],
        "public_guide_all_lines": lambda lang="vi": [f"guide:{lang}"],
    }
    for function_name in (
        "pricing_free_lines",
        "pricing_voice_lines",
        "pricing_music_lines",
        "pricing_subtitle_lines",
        "pricing_guide_lines",
        "pricing_docs_lines",
        "pricing_main_lines",
        "pricing_image_lines",
        "pricing_video_lines",
    ):
        exec(_function_source(function_name), namespace)
    return namespace


def _public_pricing_markdown_runtime_namespace() -> dict:
    namespace = {
        "__builtins__": __builtins__,
        "pricing_copy_language": lambda lang: "vi" if lang == "vi" else ("zh" if lang == "zh" else "en"),
        "public_pricing_locale": lambda lang: str(lang or "vi"),
        "public_pricing_context": lambda: {"source": "runtime"},
        "shared_pricing_markdown": lambda context, lang="vi": f"{context['source']}:{lang}",
    }
    exec(_function_source("public_pricing_markdown"), namespace)
    return namespace


def _domestic_topup_promotion_runtime_namespace() -> dict:
    namespace = {
        "__builtins__": __builtins__,
        "user_is_vietnam_market": lambda user_id: str(user_id) == "vn-user",
        "public_copy_locale": lambda lang: str(lang or "vi").lower(),
    }
    exec(_function_source("show_domestic_topup_promotion"), namespace)
    return namespace


def _promo_command_runtime_namespace() -> dict:
    class _Connection:
        def close(self):
            return None

    namespace = {
        "__builtins__": __builtins__,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "Update": object,
        "record_usage_event": lambda *_args, **_kwargs: None,
        "normalize_promo_code": lambda value: str(value or "").strip().upper(),
        "user_is_vietnam_market": lambda _user_id: False,
        "show_domestic_topup_promotion": lambda _user_id, _lang: False,
        "get_user_language": lambda _user_id: "en",
        "billing_promo_apply_lines": lambda _lang, _user_id: ["🌍 <b>International account</b>"],
        "get_user_promo_summary": lambda _user_id: (_ for _ in ()).throw(AssertionError("domestic promo guide must not run")),
        "db_connect": _Connection,
        "get_promo_code_dict": lambda _conn, _code: {"promo_type": "percent_bonus"},
        "is_gift_promo": lambda _promo: False,
        "activate_promo_for_user": lambda *_args: (_ for _ in ()).throw(AssertionError("domestic promo activation must not run")),
    }
    exec(_async_function_source("_cmd_promo_impl"), namespace)
    return namespace


def _package_i18n_runtime_namespace() -> dict:
    namespace = {
        "__builtins__": __builtins__,
        "pricing_copy_language": lambda lang: "vi" if lang == "vi" else ("zh" if lang == "zh" else "en"),
        "normalize_package_item_type": lambda value: str(value or "").strip().lower(),
        "PACKAGE_ITEM_LABELS": {"image_standard": "Ảnh tiêu chuẩn"},
        "PACKAGE_TASK_GROUP_LABELS": {"image": "🖼 Gói Ảnh"},
        "PACKAGE_COMBO_GROUP_LABELS": {},
        "package_task_group_label": lambda group: {"image": "🖼 Gói Ảnh"}.get(group, "📦 Gói tháng"),
        "package_combo_group_label": lambda _group: "🎁 Combo thành phẩm",
        "package_item_display_name": lambda item_type: {"image_standard": "Ảnh tiêu chuẩn"}.get(item_type, item_type),
        "package_purchase_price_vnd": lambda _package_type, _code: 123000,
        "package_purchase_display_price": lambda _package_type, _code: "123k",
        "_PACKAGE_ITEM_LABELS_I18N": {
            "en": {"image_standard": "Balanced image"},
            "zh": {"image_standard": "平衡图片"},
        },
        "_PACKAGE_GROUP_LABELS_I18N": {
            "en": {"image": "🖼 Image"},
            "zh": {"image": "🖼 图片"},
        },
    }
    for function_name in (
        "package_i18n_group_label",
        "package_i18n_item_label",
        "package_i18n_items_summary",
        "package_i18n_entry_label",
        "package_i18n_price_text",
    ):
        exec(_function_source(function_name), namespace)
    return namespace


def test_requested_locale_catalog_and_aliases_preserve_existing_locales():
    labels = _literal_assignment("USER_LANGUAGE_LABELS")
    assert set(REQUESTED_LOCALES) <= set(labels)
    assert set(EXISTING_LOCALES) <= set(labels)

    aliases = _literal_assignment("aliases")
    for alias, locale in {
        "spanish": "es",
        "portuguese": "pt",
        "french": "fr",
        "german": "de",
        "hindi": "hi",
        "russian": "ru",
        "turkish": "tr",
        "filipino": "fil",
        "italian": "it",
        "indonesian": "id",
    }.items():
        assert aliases[alias] == locale


def test_language_picker_exposes_every_requested_locale_and_accepts_filipino_callback():
    picker_source = _function_source("language_choice_keyboard") + _function_source("other_language_choice_keyboard")
    assert {f"lang|{locale}" for locale in REQUESTED_LOCALES} <= set(
        re.findall(r'callback_data="([^"]+)"', picker_source)
    )

    match = re.search(
        r'CallbackQueryHandler\(handle_language_callback, pattern=r"([^"]+)"\)',
        BOT_SOURCE,
    )
    assert match is not None
    assert re.fullmatch(match.group(1), "lang|fil")


def test_secondary_locales_use_the_english_copy_fallback_on_pricing_surfaces():
    fallback_source = _function_source("pricing_copy_language")
    assert 'normalized in {"vi", "zh"}' in fallback_source
    assert 'else "en"' in fallback_source
    for surface in PRICING_FALLBACK_SURFACES:
        assert "pricing_copy_language(lang)" in _function_source(surface)


def test_public_pricing_and_guide_renderers_keep_all_supported_locale_codes():
    source = _function_source("public_pricing_locale")
    assert "public_copy_locale" in source

    for function_name in (
        "pricing_free_lines",
        "pricing_voice_lines",
        "pricing_music_lines",
        "pricing_subtitle_lines",
        "pricing_guide_lines",
        "pricing_docs_lines",
        "pricing_main_lines",
        "pricing_image_lines",
        "pricing_video_lines",
        "public_pricing_markdown",
    ):
        assert "public_pricing_locale(lang)" in _function_source(function_name)


def test_secondary_public_guides_use_native_tier_labels_and_duration_words():
    english_image_labels = set(public_copy._IMAGE_LABELS["en"].values())
    english_video_labels = set(public_copy._PRODUCT_VIDEO_LABELS["en"].values())

    for locale in REQUESTED_LOCALES:
        if locale in {"vi", "en", "zh"}:
            continue
        image_text = "\n".join(public_copy.canonical_image_price_lines(locale))
        video_text = "\n".join(public_copy.canonical_product_video_price_lines(locale))
        assert not any(label in image_text for label in english_image_labels)
        assert not any(label in video_text for label in english_video_labels)
        assert " seconds." not in video_text
        for price in ("10", "20", "30", "50", "80", "110", "150"):
            assert price in image_text
        for price in ("200", "220", "80", "110", "160", "370", "1.260", "2.360"):
            assert price in video_text


def test_help_route_keeps_the_selected_public_locale_for_its_title():
    source = _async_function_source("public_help_page")
    assert "public_page_title(\"guide\", requested_locale)" in source
    assert "pricing_copy_language" not in source


def test_pricing_callback_keeps_selected_locale_for_guides_and_downloads():
    source = _async_function_source("handle_pricing_callback")
    assert source.count("public_pricing_locale(lang)") >= 3
    assert "public_page_title('pricing', pricing_locale)" in source
    assert "public_page_title('guide', guide_locale)" in source


def test_secondary_language_guide_sections_delegate_to_shared_public_copy():
    source = _function_source("guide_section_text_i18n")
    assert "public_guide_lines" in source
    assert "public_pricing_locale(lang)" in source


def test_secondary_language_guide_index_delegates_to_shared_public_copy():
    source = _function_source("guide_index_text_i18n")
    assert "public_guide_index_lines" in source
    assert "public_pricing_locale(lang)" in source


def test_runtime_copy_harness_renders_new_and_existing_secondary_locales_in_english():
    runtime = _runtime_namespace()
    visible_callbacks = {
        button.callback_data
        for markup in (runtime["language_choice_keyboard"](), runtime["other_language_choice_keyboard"]())
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }
    assert {f"lang|{locale}" for locale in REQUESTED_LOCALES} <= visible_callbacks

    english_catalog_callbacks = [
        button.callback_data
        for row in runtime["pricing_catalog_keyboard"]("en").inline_keyboard
        for button in row
    ]
    for locale in (*NEW_LOCALES, "ja", "ko", "th", "ar"):
        assert runtime["normalize_user_language"](locale) == locale
        assert runtime["pricing_copy_language"](locale) == "en"
        assert [
            button.callback_data
            for row in runtime["pricing_catalog_keyboard"](locale).inline_keyboard
            for button in row
        ] == english_catalog_callbacks
        assert any(
            "Image plans" in button.text
            for row in runtime["pricing_plans_keyboard"](locale).inline_keyboard
            for button in row
        )
        assert "Plans / Combos Notes" in "\n".join(runtime["pricing_pkgcombo_notes_lines"](locale))
        assert "TOAN AAS Plans / Combos" in "\n".join(runtime["pricing_package_summary_lines"](locale))
        assert "TOAN AAS Top-up / Pricing" in "\n".join(runtime["pricing_hub_lines"](locale))
        promotions = "\n".join(runtime["billing_promotions_lines"](locale))
        assert "International Benefits" in promotions
        assert "+30% Xu" not in promotions
        assert "+20% Xu" not in promotions
        assert "Service discounts" in "\n".join(runtime["member_policy_lines"](locale))


def test_market_authority_keeps_vietnam_promotions_separate_from_new_international_locales():
    runtime = _runtime_namespace()
    vietnam_promotions = "\n".join(runtime["billing_promotions_lines"]("vi"))
    assert "+30% Xu" in vietnam_promotions
    assert "+20% Xu" in vietnam_promotions

    conn = sqlite3.connect(":memory:")
    try:
        conn.execute(
            """CREATE TABLE users (
                user_id TEXT,
                user_market TEXT,
                country_code TEXT,
                account_region TEXT,
                international_account INTEGER,
                user_language TEXT,
                initial_user_language TEXT
            )"""
        )
        conn.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("vn-user", "VN", "VN", "VIETNAM", 0, "es", "vi"),
        )
        conn.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("intl-user", "", "", "", 0, "fil", "fil"),
        )
        assert runtime["canonical_user_market_snapshot_conn"](conn, "vn-user")["user_market"] == "VN"
        assert runtime["canonical_user_market_snapshot_conn"](conn, "intl-user")["user_market"] == "INTL"
    finally:
        conn.close()


def test_domestic_topup_promotion_is_visible_only_to_vietnamese_ui():
    runtime = _domestic_topup_promotion_runtime_namespace()
    visible = runtime["show_domestic_topup_promotion"]

    assert visible("vn-user", "vi") is True
    assert visible("vn-user", "en") is False
    assert visible("vn-user", "es") is False
    assert visible("intl-user", "vi") is False
    for locale in REQUESTED_LOCALES:
        assert visible("intl-user", locale) is False

    for function_name in (
        "manual_domestic_amount_text",
        "manual_vnd_method_notice",
        "handle_package_choice",
        "cmd_naptien",
        "_cmd_promo_impl",
        "cmd_promo_guide",
    ):
        source = _async_function_source(function_name) if function_name.startswith(("handle_", "cmd_", "_cmd_")) else _function_source(function_name)
        assert "show_domestic_topup_promotion(" in source


def test_non_vietnamese_member_surfaces_do_not_expose_topup_promo_codes():
    member_source = _async_function_source("cmd_member")
    assert "show_domestic_topup_promotion(uid, lang)" in member_source
    assert "promo_section" in member_source

    policy_source = _async_function_source("cmd_vip_policy")
    assert 'normalize_user_language(lang) != "vi"' in policy_source

    my_promos_source = _async_function_source("cmd_my_promos")
    assert "show_domestic_topup_promotion(uid, lang)" in my_promos_source


def test_international_promotion_route_hides_domestic_offer_and_promo_code_copy():
    runtime = _runtime_namespace()

    english = "\n".join(runtime["billing_promo_apply_lines"]("es")).lower()
    chinese = "\n".join(runtime["billing_promo_apply_lines"]("zh"))
    for domestic_term in ("promotion", "bonus", "code", "vietnam"):
        assert domestic_term not in english
    for domestic_term in ("优惠码", "充值活动", "奖励", "越南"):
        assert domestic_term not in chinese
    assert "international account" in english
    assert "国际账户" in chinese

    visible_callbacks = {
        button.callback_data
        for markup in (runtime["pricing_main_keyboard"]("es"), runtime["billing_promotions_keyboard"]("es"))
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }
    assert "pricing|promotions" not in visible_callbacks
    assert "pricing|promo_apply" not in visible_callbacks


def test_vietnamese_copy_respects_market_when_showing_domestic_promotion_entry():
    runtime = _runtime_namespace()

    vietnam_callbacks = {
        button.callback_data
        for row in runtime["pricing_main_keyboard"]("vi", "vn-user").inline_keyboard
        for button in row
    }
    international_callbacks = {
        button.callback_data
        for row in runtime["pricing_main_keyboard"]("vi", "intl-user").inline_keyboard
        for button in row
    }

    assert "pricing|promotions" in vietnam_callbacks
    assert "pricing|promotions" not in international_callbacks

    vietnamese_market_foreign_ui_callbacks = {
        button.callback_data
        for row in runtime["pricing_main_keyboard"]("en", "vn-user").inline_keyboard
        for button in row
    }
    assert "pricing|promotions" not in vietnamese_market_foreign_ui_callbacks
    assert "pricing|promo_apply" not in {
        button.callback_data
        for row in runtime["billing_promotions_keyboard"]("en", "vn-user").inline_keyboard
        for button in row
    }
    foreign_ui_benefits = "\n".join(runtime["billing_promotions_lines"]("en", "vn-user"))
    assert "<b>Member Benefits</b>" in foreign_ui_benefits
    assert "International Benefits" not in foreign_ui_benefits
    foreign_ui_promo = "\n".join(runtime["billing_promo_apply_lines"]("en", "vn-user"))
    assert "<b>Member Benefits</b>" in foreign_ui_promo
    assert "International account" not in foreign_ui_promo


def test_international_member_copy_keeps_service_discounts_without_domestic_topup_campaign_copy():
    runtime = _runtime_namespace()

    english = "\n".join(runtime["member_policy_lines"]("es")).lower()
    chinese = "\n".join(runtime["member_policy_lines"]("zh"))

    assert "service discounts" in english
    assert "vietnam domestic campaigns" not in english
    assert "deposit or launch bonuses" not in english
    assert "服务折扣" in chinese
    assert "越南本地充值活动" not in chinese
    assert "首次活动奖励" not in chinese


def test_pricing_member_callback_passes_the_selected_locale_to_public_copy():
    source = _async_function_source("handle_pricing_callback")
    assert 'public_pricing_lines("member", public_pricing_context(), lang)' in source


def test_international_promo_command_stops_before_domestic_guide_or_activation():
    runtime = _promo_command_runtime_namespace()
    source = _async_function_source("_cmd_promo_impl")

    class Message:
        def __init__(self):
            self.replies = []

        async def reply_text(self, text, **_kwargs):
            self.replies.append(text)
            return "sent"

    message = Message()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id="intl-user", username="intl-user", first_name="Intl"),
        message=message,
    )

    assert asyncio.run(runtime["_cmd_promo_impl"](update, SimpleNamespace(args=[]))) == "sent"
    assert asyncio.run(runtime["_cmd_promo_impl"](update, SimpleNamespace(args=["WEEKLY10"]))) == "sent"
    assert message.replies == [
        "🌍 <b>International account</b>",
        "🌍 <b>International account</b>",
    ]
    gift_branch = source.index("if promo and is_gift_promo(promo):")
    market_guard_after_gift = source.index("if not show_domestic_topup_promotion(uid, lang):", gift_branch)
    assert gift_branch < market_guard_after_gift < source.index("ok, status, info = activate_promo_for_user")


def test_international_guides_use_current_canonical_image_and_product_video_prices():
    runtime = _guide_i18n_runtime_namespace()
    image_prices = [str(int(item["unit_xu"])) for item in canonical.public_image_quality_catalog()]
    video_prices = [
        f"{int(item['unit_xu']):,}".replace(",", ".")
        for item in public_copy.public_product_video_catalog()
    ]

    for locale in ("en", "zh", "es", "fil"):
        image_guide = runtime["guide_section_text_i18n"]("image_ai", locale)
        video_guide = runtime["guide_section_text_i18n"]("video_ai", locale)
        for price in image_prices:
            assert price in image_guide
        for price in video_prices:
            assert price in video_guide
        assert "50, 150, 200, 300, 400, 500, 600" not in image_guide
        assert "200, 300, 400, 500, 600, 800, 1000, 1200, 1500" not in video_guide


def test_international_legacy_credit_guide_uses_neutral_topup_copy():
    runtime = _guide_i18n_runtime_namespace()

    for locale in ("en", "es", "fil"):
        text = runtime["guide_section_text_i18n"]("credits", locale)
        assert text
        assert "1 Xu = 100đ" not in text
        assert "PayOS" not in text
        assert "Vietnamese bank" not in text

    chinese = runtime["guide_section_text_i18n"]("credits", "zh")
    assert "国际充值只获得经核验的基础 Xu。" in chinese
    assert "1 Xu = 100đ" not in chinese
    assert "PayOS" not in chinese
    assert "越南银行" not in chinese


def test_chinese_guide_navigation_is_localized_and_discloses_the_vietnamese_only_docx():
    runtime = _guide_keyboard_runtime_namespace()

    chinese_root = "\n".join(
        button.text
        for row in runtime["guide_keyboard"]("", "zh").inline_keyboard
        for button in row
    )
    assert "下载价格表" in chinese_root
    assert "下载使用指南" in chinese_root
    assert "越南语使用指南（DOCX）" in chinese_root
    assert "返回指南" in chinese_root

    chinese_image = "\n".join(
        button.text
        for row in runtime["guide_keyboard"]("image_ai", "zh").inline_keyboard
        for button in row
    )
    assert "创建图片" in chinese_image
    assert "价格表" in chinese_image

    english_root = "\n".join(
        button.text
        for row in runtime["guide_keyboard"]("", "es").inline_keyboard
        for button in row
    )
    assert "Vietnamese guide (DOCX)" in english_root


def test_telegram_public_pricing_and_guide_copy_passes_locale_to_shared_renderers():
    runtime = _shared_pricing_runtime_namespace()
    assert runtime["pricing_main_lines"]("es") == ["total:es"]
    assert runtime["pricing_image_lines"]("es") == ["image:es"]
    assert runtime["pricing_video_lines"]("es") == ["video:es"]
    assert runtime["pricing_voice_lines"]("es") == ["voice:es"]
    assert runtime["pricing_music_lines"]("es") == ["music:es"]
    assert runtime["pricing_subtitle_lines"]("es") == ["subtitle:es"]
    assert runtime["pricing_docs_lines"]("es") == ["docs:es"]
    assert runtime["pricing_free_lines"]("es") == ["free:es"]
    assert runtime["pricing_guide_lines"]("es") == ["guide:es"]

    callback_source = _function_source("handle_pricing_callback")
    for call in (
        "pricing_main_lines(lang)",
        "pricing_image_lines(lang)",
        "pricing_video_lines(lang)",
        "pricing_voice_lines(lang)",
        "pricing_music_lines(lang)",
        "pricing_subtitle_lines(lang)",
        "pricing_docs_lines(lang)",
        "pricing_free_lines(lang)",
        "pricing_guide_lines(lang)",
    ):
        assert call in callback_source
    assert "pricing_locale = public_pricing_locale(lang)" in callback_source
    assert "public_pricing_markdown(public_pricing_context(), pricing_locale)" in callback_source
    assert "guide_locale = public_pricing_locale(lang)" in callback_source
    assert "public_guide_markdown(guide_locale)" in callback_source


def test_public_pricing_markdown_wrapper_accepts_locale_for_telegram_and_website_downloads():
    runtime = _public_pricing_markdown_runtime_namespace()

    assert runtime["public_pricing_markdown"]({"source": "provided"}, "es") == "provided:es"
    assert runtime["public_pricing_markdown"]() == "runtime:vi"


def test_package_and_combo_screens_use_locale_copy_without_repricing_catalog_entries():
    assert "package_i18n_entry_label" in _function_source("pricing_package_summary_lines")
    assert "package_i18n_entry_label" in _function_source("pricing_task_package_group_lines")
    assert "package_i18n_entry_label" in _function_source("pricing_combo_lines")
    assert "package_i18n_items_summary" in _function_source("package_purchase_detail_lines")

    callback_source = _function_source("handle_pkgcombo_callback")
    assert "pricing_task_package_group_lines(group, lang)" in callback_source
    assert "pricing_combo_lines(lang)" in callback_source
    assert 'render_pkgcombo_detail(query, "monthly", parts[2], lang)' in callback_source
    assert 'render_pkgcombo_detail(query, "combo", parts[2], lang)' in callback_source

    runtime = _package_i18n_runtime_namespace()
    entry = {
        "label": "🖼 Ảnh Cơ bản",
        "group": "image",
        "items": {"image_standard": 20},
        "default_days": 30,
    }
    assert runtime["package_i18n_entry_label"](entry, "image_basic_monthly", "monthly", "es") == "🖼 Image monthly plan — Balanced image ×20 / 30 days"
    assert runtime["package_i18n_entry_label"](entry, "image_basic_monthly", "monthly", "zh") == "🖼 图片 月度套餐 — 平衡图片 ×20 / 30 天"
    assert runtime["package_i18n_entry_label"](entry, "image_basic_monthly", "monthly", "vi") == "🖼 Ảnh Cơ bản"
    assert runtime["package_i18n_price_text"]("monthly", "image_basic_monthly", "es") == "123k"


def test_landing_has_native_copy_for_every_supported_locale_and_selector():
    match = re.search(
        r"const SUPPORTED_LOCALES = Object\.freeze\((\[[\s\S]*?\])\);",
        LANDING_SOURCE,
    )
    assert match is not None
    supported = set(json.loads(match.group(1)))
    assert set(REQUESTED_LOCALES) <= supported
    assert "data-locale-select" in LANDING_SOURCE
    assert 'const LOCALE_ALIASES = Object.freeze({' in LANDING_SOURCE
    assert '"zh-cn": "zh"' in LANDING_SOURCE
    assert '"pt-br": "pt"' in LANDING_SOURCE
    assert 'document.documentElement.dir = locale === "ar" ? "rtl" : "ltr";' in LANDING_SOURCE

    node = shutil.which("node")
    assert node is not None
    script = """
        const fs = require('fs');
        const html = fs.readFileSync(process.argv[1], 'utf8');
        const source = [...html.matchAll(/<script>([\\s\\S]*?)<\\/script>/g)].map((match) => match[1]).join('\\n');
        const start = source.indexOf('const PUBLIC_COPY =');
        const end = source.indexOf('const SUPPORTED_LOCALES =');
        if (start < 0 || end < 0) throw new Error('landing copy constants missing');
        const copy = new Function(`${source.slice(start, end)}; return { PUBLIC_COPY, ADDITIONAL_COPY };`)();
        process.stdout.write(JSON.stringify(copy));
    """
    result = subprocess.run([node, "-e", script, str(REPO_ROOT / "index.html")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    copy = json.loads(result.stdout)
    for key in ("PUBLIC_COPY", "ADDITIONAL_COPY"):
        assert set(REQUESTED_LOCALES) <= set(copy[key])
        base_keys = set(copy[key]["vi"])
        for locale in REQUESTED_LOCALES:
            assert set(copy[key][locale]) == base_keys
    for locale in REQUESTED_LOCALES:
        if locale in {"vi", "en", "zh"}:
            continue
        assert copy["PUBLIC_COPY"][locale]["hero.title"] != copy["PUBLIC_COPY"]["en"]["hero.title"]
        assert copy["ADDITIONAL_COPY"][locale]["companion.mapTitle"] != copy["ADDITIONAL_COPY"]["en"]["companion.mapTitle"]


def test_changed_copy_functions_parse_without_importing_the_full_bot_module():
    for function_name in (
        "normalize_user_language",
        "pricing_copy_language",
        "public_pricing_locale",
        "show_domestic_topup_promotion",
        "menu_text_main_topup_i18n",
        "other_language_choice_keyboard",
        "pricing_main_keyboard",
        "pricing_catalog_keyboard",
        "pricing_packages_keyboard",
        "pricing_plans_keyboard",
        "member_policy_keyboard",
        "pricing_hub_lines",
        "billing_promotions_lines",
        "billing_promotions_keyboard",
        "billing_promo_apply_lines",
        "_cmd_promo_impl",
        "pricing_catalog_lines",
        "pricing_packages_lines",
        "pricing_pkgcombo_notes_lines",
        "pricing_pkgcombo_notes_keyboard",
        "pricing_package_summary_lines",
        "pricing_package_summary_keyboard",
        "pricing_combo_keyboard",
        "my_packages_keyboard",
        "member_policy_lines",
        "pricing_xu_lines_i18n",
        "guide_section_text_i18n",
        "package_i18n_group_label",
        "package_i18n_item_label",
        "package_i18n_items_summary",
        "package_i18n_entry_label",
        "package_i18n_price_text",
        "pricing_combo_lines",
        "pricing_task_package_group_lines",
        "pricing_task_package_group_keyboard",
        "package_purchase_detail_lines",
        "package_purchase_manual_keyboard",
        "package_purchase_confirm_keyboard",
        "guide_keyboard",
    ):
        ast.parse(_function_source(function_name))

    for function_name in (
        "handle_package_choice",
        "cmd_naptien",
        "cmd_member",
        "cmd_vip_policy",
        "cmd_my_promos",
    ):
        ast.parse(_async_function_source(function_name))


def test_landing_inline_javascript_parses():
    node = shutil.which("node")
    assert node is not None
    script = """
        const fs = require('fs');
        const html = fs.readFileSync(process.argv[1], 'utf8');
        const scripts = [...html.matchAll(/<script>([\\s\\S]*?)<\\/script>/g)].map((match) => match[1]);
        if (!scripts.length) throw new Error('no inline scripts');
        scripts.forEach((source) => new Function(source));
    """
    result = subprocess.run([node, "-e", script, str(REPO_ROOT / "index.html")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


if __name__ == "__main__":
    direct_tests = [
        test_requested_locale_catalog_and_aliases_preserve_existing_locales,
        test_language_picker_exposes_every_requested_locale_and_accepts_filipino_callback,
        test_secondary_locales_use_the_english_copy_fallback_on_pricing_surfaces,
        test_secondary_public_guides_use_native_tier_labels_and_duration_words,
        test_help_route_keeps_the_selected_public_locale_for_its_title,
        test_runtime_copy_harness_renders_new_and_existing_secondary_locales_in_english,
        test_market_authority_keeps_vietnam_promotions_separate_from_new_international_locales,
        test_domestic_topup_promotion_is_visible_only_to_vietnamese_ui,
        test_non_vietnamese_member_surfaces_do_not_expose_topup_promo_codes,
        test_international_promotion_route_hides_domestic_offer_and_promo_code_copy,
        test_vietnamese_copy_respects_market_when_showing_domestic_promotion_entry,
        test_pricing_member_callback_passes_the_selected_locale_to_public_copy,
        test_international_promo_command_stops_before_domestic_guide_or_activation,
        test_international_guides_use_current_canonical_image_and_product_video_prices,
        test_international_legacy_credit_guide_uses_neutral_topup_copy,
        test_chinese_guide_navigation_is_localized_and_discloses_the_vietnamese_only_docx,
        test_telegram_public_pricing_and_guide_copy_passes_locale_to_shared_renderers,
        test_public_pricing_markdown_wrapper_accepts_locale_for_telegram_and_website_downloads,
        test_package_and_combo_screens_use_locale_copy_without_repricing_catalog_entries,
        test_landing_has_native_copy_for_every_supported_locale_and_selector,
        test_changed_copy_functions_parse_without_importing_the_full_bot_module,
        test_landing_inline_javascript_parses,
    ]
    for direct_test in direct_tests:
        direct_test()
    print(f"{len(direct_tests)} direct locale checks passed")
