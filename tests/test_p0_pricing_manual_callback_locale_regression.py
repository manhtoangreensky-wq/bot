from pathlib import Path


BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"


def _source() -> str:
    return BOT_PATH.read_text(encoding="utf-8")


def _source_between(start: str, end: str) -> str:
    source = _source()
    return source[source.index(start):source.index(end)]


def test_existing_locale_callback_bridge_imports_public_copy_locale():
    """Pricing and manual top-up both use this existing public-copy helper."""

    import_block = _source_between(
        "from services.pricing_guide_content import (",
        ")\nfrom video_multiscene_engine import (",
    )
    assert "    public_copy_locale," in import_block


def test_existing_main_menu_restores_language_entry_and_two_column_picker():
    menu_source = _source_between(
        "def localized_main_menu_keyboard",
        "def localized_start_menu_text",
    )
    picker_source = _source_between(
        "def language_choice_keyboard",
        "def other_language_choice_text",
    )

    assert menu_source.count('callback_data="back_lang"') == 3
    assert '[InlineKeyboardButton("🇻🇳 Tiếng Việt", callback_data="lang|vi"), InlineKeyboardButton("🇺🇸 English", callback_data="lang|en")]' in picker_source
    assert '[InlineKeyboardButton("🇨🇳 中文", callback_data="lang|zh"), InlineKeyboardButton("🌍 Ngôn ngữ khác / More languages", callback_data="lang_more")]' in picker_source


def test_existing_background_music_price_is_130_in_button_and_runtime_map():
    source = _source()

    assert 'MUSIC_PRODUCT_TIER_BASIC: "🎵 Cơ bản — 130 Xu"' in source
    assert "MUSIC_PRODUCT_BACKGROUND_TIER_PRICES = {\n    MUSIC_PRODUCT_TIER_BASIC: 130," in source
