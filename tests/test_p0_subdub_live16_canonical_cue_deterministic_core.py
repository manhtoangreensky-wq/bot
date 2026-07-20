import asyncio
import re
from pathlib import Path

import bot
from services import subdub_canonical_cues as canonical
from services import subtitle_dub_product_pipeline as product_pipeline


REPO = Path(__file__).resolve().parents[1]
BOT_SOURCE = (REPO / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    pattern = rf"(?ms)^(?:async )?def {re.escape(name)}\b.*?(?=^(?:async )?def |\Z)"
    match = re.search(pattern, BOT_SOURCE)
    assert match, f"missing function source: {name}"
    return match.group(0)


def _source_cue() -> list[dict]:
    return canonical.canonicalize_segments(
        [{"index": 1, "start": 1.25, "end": 3.75, "text": "Cau goc"}],
        extraction_source="subtitle_stream",
        source_language="vi",
    )


def test_live16_render_wrap_never_truncates_semantic_tts_text():
    source = _source_cue()
    full = "A deliberately long translated sentence whose complete semantic content must reach TTS"
    translated = canonical.apply_translations(
        source,
        [{"cue_id": source[0]["cue_id"], "translated_text": full}],
        target_language="en",
        max_chars=18,
        max_lines=2,
    )

    cue = translated[0]
    assert canonical.same_timeline(source, translated)
    assert cue["translated_text_full"] == full
    assert cue["tts_text"] == full
    assert canonical.cue_tts_text(cue) == full
    assert len(cue["render_text"].splitlines()) <= 2
    assert cue["render_text"] != full


def test_live16_translated_dub_uses_full_text_and_original_cue_window():
    full = "Translated voice content must remain complete after visual wrapping"
    prepared = {
        "source_segments": [{"index": 1, "start": 2.0, "end": 4.5, "text": "Source"}],
        "output_segments": [{
            "index": 1,
            "start": 2.0,
            "end": 4.5,
            "text": "Translated voice...",
            "translated_text_full": full,
            "translate_missing": False,
        }],
    }
    policy = product_pipeline.resolve_subdub_dub_audio_policy(
        {"target_language": "English", "translate_requested": True},
        prepared,
    )

    assert policy["dub_text_source"] == "translated"
    assert policy["tts_tracks_count"] == 1
    assert policy["source_tts_rendered"] is False
    assert policy["target_tts_rendered"] is True
    assert policy["tts_segments"][0]["text"] == full
    assert (policy["tts_segments"][0]["start"], policy["tts_segments"][0]["end"]) == (2.0, 4.5)


def test_live16_qc_preserves_cue_identity_and_full_tts_text():
    source = [{
        "cue_id": "cue-0001-test",
        "index": 1,
        "start": 0.5,
        "end": 2.0,
        "text": "A long visual translation that needs balanced wrapping inside one cue",
        "translated_text_full": "A long visual translation that needs balanced wrapping inside one cue",
        "source_text": "Source cue",
    }]
    output = bot.video_dubbing_qc_segments(source, preserve_timestamps=True)

    assert len(output) == 1
    assert output[0]["cue_id"] == source[0]["cue_id"]
    assert output[0]["translated_text_full"] == source[0]["translated_text_full"]
    assert (output[0]["start"], output[0]["end"]) == (0.5, 2.0)
    assert len(output[0]["text"].splitlines()) <= 2


def test_live16_translation_rejects_numeric_garbage_without_shifting_cues(monkeypatch):
    source = [
        {"cue_id": "one", "index": 1, "start": 0.0, "end": 1.5, "text": "source one"},
        {"cue_id": "two", "index": 2, "start": 2.0, "end": 3.5, "text": "source two"},
    ]

    async def fake_translate(text, _target_language, **_kwargs):
        if text.endswith("one"):
            return {"text": "00007 00000 00111", "provider": "fixture"}
        return {"text": "valid translation", "provider": "fixture"}

    monkeypatch.setattr(bot, "translate_subtitle_text", fake_translate)
    result = asyncio.run(bot.translate_subtitle_segments(source, "English"))

    assert [(item["start"], item["end"]) for item in result["segments"]] == [(0.0, 1.5), (2.0, 3.5)]
    assert result["segments"][0]["text"] == "source one"
    assert result["segments"][0]["translate_missing"] is True
    assert result["segments"][1]["translated_text_full"] == "valid translation"


def test_live16_srt_output_has_utf8_bom_and_round_trips_unicode():
    text = "1\n00:00:00,000 --> 00:00:01,000\nTiếng Việt 日本語 한국어\n"
    payload = canonical.encode_srt_utf8_bom(text)

    assert payload.startswith(b"\xef\xbb\xbf")
    assert payload.decode("utf-8-sig") == text


def test_live16_every_visible_subdub_callback_has_a_handler_action():
    keyboard_sources = "\n".join(
        _function_source(name)
        for name in (
            "video_dubbing_menu_keyboard",
            "video_dubbing_source_keyboard",
            "video_dubbing_language_keyboard",
            "video_dubbing_voice_keyboard",
            "subdub_audio_mix_keyboard",
            "subdub_audio_layer_keyboard",
        )
    )
    actions = set(re.findall(r"videodub\|([a-z0-9_]+)", keyboard_sources))
    handler = _function_source("handle_video_dubbing_callback")

    assert actions
    assert not {action for action in actions if f'"{action}"' not in handler}
    assert 'callback_data="menu|main"' in keyboard_sources
    assert "menu|translation_media_file" not in keyboard_sources
    assert "menu|translation_media_audio" not in keyboard_sources


def test_live16_subdub_numeric_volume_is_owned_before_product_video_scene_input():
    dispatch = _function_source("handle_message")
    pending = _function_source("handle_video_dubbing_pending_text")
    owner = _function_source("subdub_text_input_owns_message")

    assert dispatch.index("handle_video_dubbing_pending_text(update, context)") < dispatch.index(
        "handle_video_product_pending_text"
    )
    assert '"subdub_original_volume_input"' in pending
    assert '"subdub_dub_volume_input"' in pending
    assert "VIDEO_DUBBING_PENDING_TEXT_STEPS" in owner
    assert "scene_count" not in pending
