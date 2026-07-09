from pathlib import Path

import bot


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    markers = (f"def {name}(", f"async def {name}(")
    starts = [BOT_SOURCE.find(marker) for marker in markers if BOT_SOURCE.find(marker) >= 0]
    assert starts, name
    start = min(starts)
    next_def = BOT_SOURCE.find("\ndef ", start + 1)
    next_async = BOT_SOURCE.find("\nasync def ", start + 1)
    endings = [item for item in (next_def, next_async) if item >= 0]
    return BOT_SOURCE[start:min(endings)] if endings else BOT_SOURCE[start:]


def _srt(text: str, start: str = "00:00:00,000", end: str = "00:00:01,000") -> str:
    return f"1\n{start} --> {end}\n{text}\n"


def _ass_seconds(value: str) -> float:
    hours, minutes, rest = value.split(":", 2)
    seconds, centis = rest.split(".", 1)
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(centis) / 100.0


def _dialogue_times(ass: str) -> list[tuple[float, float]]:
    result = []
    for line in ass.splitlines():
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 3)
        result.append((_ass_seconds(parts[1]), _ass_seconds(parts[2])))
    return result


def test_i18n_font_fallback_matrix_resolves_unicode_groups():
    samples = [
        ("vi", "Xin chào", "latin", False),
        ("en", "Hello", "latin", False),
        ("ja", "こんにちは世界", "japanese", True),
        ("zh-Hans", "你好世界", "chinese", True),
        ("zh-Hant", "你好世界", "chinese", True),
        ("ko", "안녕하세요 세계", "korean", True),
        ("th", "สวัสดีโลก", "thai", False),
        ("ar", "مرحبا بالعالم", "arabic", False),
        ("hi", "नमस्ते दुनिया", "devanagari", False),
        ("ru", "Привет мир", "cyrillic", False),
        ("es", "Hola mundo", "latin", False),
        ("fr", "Bonjour le monde", "latin", False),
        ("de", "Hallo Welt", "latin", False),
    ]

    for language, text, script, needs_cjk in samples:
        resolved = bot.resolve_subdub_subtitle_font(
            {"subtitle_text": text, "target_language": language, "font": ""}
        )
        assert resolved["ok"] is True, (language, resolved)
        assert resolved["family"], (language, resolved)
        assert resolved["script"] == script, (language, resolved)
        if needs_cjk:
            assert resolved["supports_cjk"] is True or "CJK" in resolved["family"], (language, resolved)


def test_unicode_ass_style_does_not_force_latin_only_font():
    ass = bot.subdub_generate_ass_from_srt(
        _srt("こんにちは世界"),
        {"output_type": "burn", "target_language": "ja", "font": ""},
    )

    assert "こんにちは世界" in ass
    assert "Style: Default,Arial," not in ass
    assert "; subtitle_font_script: japanese" in ass


def test_subtitle_only_and_combo_use_same_i18n_font_fallback():
    subtitle_ass = bot.subdub_generate_ass_from_srt(
        _srt("你好世界"),
        {"output_type": "burn", "target_language": "zh-Hans", "font": ""},
    )
    combo_ass = bot.subdub_generate_ass_from_srt(
        _srt("안녕하세요 세계"),
        {
            "output_type": "video_subtitle",
            "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            "target_language": "ko",
            "font": "",
        },
    )

    assert "; subtitle_font_script: chinese" in subtitle_ass
    assert "; subtitle_font_script: korean" in combo_ass
    assert "Style: Default,Arial," not in subtitle_ass + combo_ass


def test_long_no_space_unicode_wraps_max_two_lines():
    text = "こんにちは世界" * 8
    style = bot.subdub_normalize_style(
        {
            "output_type": "burn",
            "target_language": "ja",
            "subtitle_text": text,
            "video_width": 1280,
            "video_height": 720,
        }
    )
    wrapped = bot.subdub_ass_wrap_text(text, style, 2)

    assert wrapped
    assert wrapped.count(r"\N") <= 1
    assert len(wrapped.replace(r"\N", "")) == len(text)


def test_subtitle_pacing_extends_only_inside_safe_gap():
    first = "This translated subtitle is long enough to need a little more readable display time"
    ass = bot.subdub_generate_ass_from_srt(
        (
            f"1\n00:00:00,000 --> 00:00:00,400\n{first}\n\n"
            "2\n00:00:02,000 --> 00:00:03,000\nNext cue\n"
        ),
        {"output_type": "burn", "target_language": "en"},
    )
    times = _dialogue_times(ass)

    assert times[0][1] > 0.4
    assert times[0][1] <= 1.95
    assert times[0][1] < times[1][0]
    assert "; subtitle_pacing_adjusted_events: 1" in ass


def test_subtitle_pacing_does_not_overlap_next_cue():
    ass = bot.subdub_generate_ass_from_srt(
        (
            "1\n00:00:00,000 --> 00:00:00,400\n"
            "A very long translated line cannot steal time from the next cue\n\n"
            "2\n00:00:00,450 --> 00:00:01,000\nNext cue\n"
        ),
        {"output_type": "burn", "target_language": "en"},
    )
    first, second = _dialogue_times(ass)[:2]

    assert first[1] <= second[0]


def test_dub_only_and_combo_volume_gain_x2_debug():
    debug = bot.subdub_dub_audio_gain_debug()

    assert bot.SUBDUB_DUB_VOLUME_GAIN == 2.0
    assert bot.SUBDUB_DUB_VOICE_GAIN == 2.0
    assert debug["dub_volume_gain"] == 2.0
    assert "volume=2.000" in debug["filter"]


def test_female_voice_and_routes_are_preserved_static():
    voice_source = _function_source("resolve_video_dub_tts_voice")
    callback_source = _function_source("handle_video_dubbing_callback")

    assert "subdub_default_tts_voice_for_gender(gender)" in voice_source
    assert "selected_voice_gender_unavailable" in voice_source
    assert "public_failure_overridden_by_video_delivery=True" in callback_source
    assert "run_subdub_pipeline" not in _function_source("subdub_generate_ass_from_srt")


def test_no_real_provider_calls_in_i18n_style_volume_helpers():
    touched = "\n".join(
        [
            _function_source("resolve_subdub_subtitle_font"),
            _function_source("subdub_ass_wrap_text"),
            _function_source("subdub_generate_ass_from_srt"),
            _function_source("subdub_dub_audio_filter_chain"),
            _function_source("subdub_dub_audio_gain_debug"),
        ]
    )

    assert "requests." not in touched
    assert "httpx." not in touched
    assert "synthesize_text_to_audio" not in touched
