"""Source-only contract for Audio Studio root presentation.

It deliberately excludes audio/music providers, jobs and payment paths.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
COPY_SOURCE = (ROOT / "services" / "pricing_guide_content.py").read_text(encoding="utf-8")

SUPPORTED_LOCALES = (
    "vi", "en", "zh", "es", "pt", "fr", "de", "ja", "ko", "hi", "ar",
    "ru", "tr", "th", "fil", "it", "id",
)

SCRIPT_RANGES = {
    "zh": r"[\u3400-\u9fff]", "ko": r"[\uac00-\ud7af]",
    "ja": r"[\u3040-\u30ff\u3400-\u9fff]", "th": r"[\u0e00-\u0e7f]",
    "ru": r"[\u0400-\u04ff]", "ar": r"[\u0600-\u06ff]", "hi": r"[\u0900-\u097f]",
}


def _literal_mapping(name: str) -> dict:
    module = ast.parse(COPY_SOURCE)
    for statement in module.body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in statement.targets
        ):
            return ast.literal_eval(statement.value)
    raise AssertionError(f"missing literal mapping: {name}")


def _function_source(name: str) -> str:
    start = BOT_SOURCE.index(f"def {name}(")
    following = re.search(r"\n(?:async )?def ", BOT_SOURCE[start + 1 :])
    end = -1 if following is None else start + 1 + following.start()
    return BOT_SOURCE[start:] if end < 0 else BOT_SOURCE[start:end]


def test_audio_root_copy_is_direct_and_native_for_every_supported_locale():
    table = _literal_mapping("_PUBLIC_AUDIO_ROOT_COPY")
    english = table["en"]
    required = (
        "audio_root_voice", "audio_root_music", "audio_root_back", "voice_hub_title",
        "voice_hub_body", "voice_text_to_speech", "voice_speech_to_text", "voice_default_female",
        "voice_default_male", "voice_default_neutral", "voice_vault", "voice_create_custom",
        "music_hub_title", "music_hub_body", "music_background", "music_song", "music_vault", "music_edit",
    )
    assert tuple(table) == SUPPORTED_LOCALES
    for locale in SUPPORTED_LOCALES:
        copy = table[locale]
        assert not [key for key in required if not str(copy.get(key) or "").strip()], locale
        if locale != "en":
            assert copy["voice_hub_body"] != english["voice_hub_body"], locale
            assert copy["music_hub_body"] != english["music_hub_body"], locale
    for locale, pattern in SCRIPT_RANGES.items():
        text = "\n".join(table[locale][key] for key in ("voice_hub_body", "music_hub_body", "voice_text_to_speech", "music_background"))
        assert re.search(pattern, text), locale


def test_audio_root_renderers_preserve_existing_callback_and_engine_boundaries():
    for name in ("music_tools_keyboard", "voice_hub_text", "voice_hub_keyboard", "music_hub_text", "music_hub_keyboard"):
        source = _function_source(name)
        assert "public_hub_copy" in source, name
        assert "call_" not in source, name
        assert "record_credit_event" not in source, name
    handler = _function_source("handle_music_quick_callback")
    for action in ("root", "voice_hub", "music_hub"):
        assert f'action == "{action}"' in handler


def test_audio_copy_does_not_rewire_video_addon_rendering():
    source = _function_source("music_tools_keyboard")
    assert 'ctx == PRODUCT_CONTEXT_VIDEO_ADDON' in source
    assert '"vfinal|voice"' in source
    assert '"vfinal|music"' in source
    assert '"vfinal|addon"' in source
