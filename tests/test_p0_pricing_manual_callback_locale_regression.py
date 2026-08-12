from pathlib import Path


BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"


def _source() -> str:
    return BOT_PATH.read_text(encoding="utf-8")


def _source_between(start: str, end: str) -> str:
    source = _source()
    return source[source.index(start):source.index(end)]


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
