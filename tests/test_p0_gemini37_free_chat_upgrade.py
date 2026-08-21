from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_free_chat_runtime_metadata_and_public_copy_use_gemini_37_flash() -> None:
    provider_source = (ROOT / "providers" / "gemini_public_chat_provider.py").read_text(encoding="utf-8")
    store_source = (ROOT / "services" / "public_chat_store.py").read_text(encoding="utf-8")
    guide_source = (ROOT / "services" / "pricing_guide_content.py").read_text(encoding="utf-8")
    bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")

    assert "gemini-3.6-flash" not in provider_source
    assert "gemini-3.6-flash" not in store_source
    assert "Gemini 3.6 Flash" not in guide_source
    assert "Gemini 3.6 Flash" not in bot_source
    assert 'GEMINI_FREE_MODEL = "gemini-3.7-flash"' in provider_source
    assert store_source.count('"gemini-3.7-flash"') >= 2
    assert guide_source.count("Gemini 3.7 Flash") >= 3
    assert bot_source.count("Gemini 3.7 Flash") >= 3
