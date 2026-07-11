import asyncio
import inspect

import bot
from services.subdub_tts_language_routing import resolve_subdub_tts_language_route


def test_live_renderer_passes_real_subtitle_text_to_font_resolution():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert 'render_state["subtitle_text"] = subdub_normalize_subtitle_text(subtitle_payload)' in source


def test_all_public_translation_languages_have_tts_locale_routes():
    expected = {
        "vi": "vi-VN", "en": "en-US", "zh": "zh-CN", "ja": "ja-JP",
        "ko": "ko-KR", "th": "th-TH", "fr": "fr-FR", "de": "de-DE",
        "es": "es-ES", "id": "id-ID", "ms": "ms-MY", "pt": "pt-BR",
        "ru": "ru-RU", "ar": "ar-SA", "hi": "hi-IN", "lo": "lo-LA",
        "km": "km-KH", "my": "my-MM", "fil": "fil-PH",
    }
    for language, code in expected.items():
        route = resolve_subdub_tts_language_route({
            "target_language": language,
            "voice_kind": "default_female",
        })
        assert route["ok"] is True, (language, route)
        assert route["resolved_tts_language_code"] == code
        assert route["resolved_edge_voice_id"]


def test_native_language_labels_normalize_for_translation():
    cases = {
        "ไทย": "th",
        "العربية": "ar",
        "हिन्दी": "hi",
        "русский": "ru",
        "ລາວ": "lo",
        "ខ្មែរ": "km",
        "မြန်မာ": "my",
    }
    for label, expected in cases.items():
        assert bot.normalize_translate_target(label) == expected


def test_international_tts_prefers_resolved_locale_voice_without_network(monkeypatch):
    calls = []

    async def fake_edge(text, voice_id="", voice_speed="1.0", edge_func=None):
        del edge_func
        calls.append((text, voice_id, voice_speed))
        return "PASS", b"locale-audio", "fixture", 200

    async def forbidden_paid(*_args, **_kwargs):
        raise AssertionError("paid fallback must not run before the resolved locale voice")

    monkeypatch.setattr(bot, "TTS_PROVIDER", "auto")
    monkeypatch.setattr(bot, "call_edge_tts_with_speed", fake_edge)
    monkeypatch.setattr(bot, "key4u_minimax_tts_public_ready", lambda: True)
    monkeypatch.setattr(bot, "call_key4u_minimax_tts_bytes_with_speed", forbidden_paid)

    provider, audio, _detail = asyncio.run(bot.video_dubbing_tts_bytes(
        "こんにちは",
        voice_style="Giọng nữ",
        voice_id="female-selected",
        voice_speed="1.0",
        tts_language_code="ja-JP",
        tts_language_boost="Japanese",
        edge_voice_id="ja-JP-NanamiNeural",
    ))

    assert provider == "Edge TTS"
    assert audio == b"locale-audio"
    assert calls == [("こんにちは", "ja-JP-NanamiNeural", "1.0")]
