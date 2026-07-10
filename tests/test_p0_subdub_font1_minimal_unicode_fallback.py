import inspect

import bot


SCRIPT_CASES = (
    ("Vietnamese", "Xin chào Việt Nam", "latin"),
    ("English", "Hello world", "latin"),
    ("Japanese", "こんにちは世界", "japanese"),
    ("Chinese", "你好世界", "chinese"),
    ("Korean", "안녕하세요 세계", "korean"),
    ("Thai", "สวัสดีชาวโลก", "thai"),
    ("Arabic", "مرحبا بالعالم", "arabic"),
    ("Hindi", "नमस्ते दुनिया", "devanagari"),
    ("Russian", "Привет мир", "cyrillic"),
)


def _srt(text: str) -> str:
    return f"1\n00:00:01,250 --> 00:00:03,750\n{text}\n"


def _enable_fixture_fonts(monkeypatch):
    bot.SUBDUB_SUBTITLE_FONT_RESOLUTION_CACHE.clear()
    monkeypatch.setattr(bot, "subdub_font_path_available", lambda path="": bool(path))


def test_font1_detects_supported_unicode_scripts():
    for language, text, expected in SCRIPT_CASES:
        assert bot.subdub_detect_subtitle_script(text, language) == expected


def test_font1_selects_script_specific_font_without_real_system_fonts(monkeypatch):
    _enable_fixture_fonts(monkeypatch)

    for language, text, expected_script in SCRIPT_CASES:
        resolved = bot.resolve_subdub_subtitle_font(
            {"target_language": language, "subtitle_text": text, "font": "Arial"}
        )
        assert resolved["ok"] is True, (language, resolved)
        assert resolved["script"] == expected_script
        assert resolved["font_selected"]
        if expected_script in {"japanese", "chinese", "korean"}:
            assert resolved["supports_cjk"] is True
            assert resolved["family"] != "Arial"


def test_font1_ass_uses_unicode_font_and_preserves_timing(monkeypatch):
    _enable_fixture_fonts(monkeypatch)

    for language, text, expected_script in SCRIPT_CASES:
        ass = bot.subdub_generate_ass_from_srt(
            _srt(text),
            {"target_language": language, "output_type": "burn", "font": "Arial"},
        )
        assert text in ass
        assert f"; subtitle_font_script: {expected_script}" in ass
        assert "Dialogue: 0,0:00:01.25,0:00:03.75" in ass
        if expected_script != "latin":
            assert "Style: Default,Arial," not in ass


def test_font1_missing_script_font_blocks_cleanly(monkeypatch):
    bot.SUBDUB_SUBTITLE_FONT_RESOLUTION_CACHE.clear()
    monkeypatch.setattr(bot, "subdub_font_path_available", lambda _path="": False)
    monkeypatch.setattr(bot.shutil, "which", lambda _name: None)

    resolved = bot.resolve_subdub_subtitle_font(
        {"target_language": "Japanese", "subtitle_text": "こんにちは", "font": "Arial"}
    )

    assert resolved["ok"] is False
    assert resolved["blocker"] == "subtitle_font_missing"
    assert resolved["font_fallback_reason"] == "no_font_with_required_script"


def test_font1_does_not_touch_pacing_volume_or_provider_paths():
    source = "\n".join(
        (
            inspect.getsource(bot.subdub_detect_subtitle_script),
            inspect.getsource(bot._subdub_font_candidates_for_script),
            inspect.getsource(bot.resolve_subdub_subtitle_font),
        )
    )

    assert "SUBDUB_DUB" not in source
    assert "subtitle_pacing" not in source
    assert "requests." not in source
    assert "httpx." not in source
    assert "synthesize" not in source
