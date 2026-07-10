from __future__ import annotations

import asyncio

import bot

from services import subtitle_dub_product_pipeline as pipeline
from services.subdub_tts_language_routing import resolve_subdub_tts_language_route


SUPPORTED = {
    "English": "en-US",
    "Tiếng Việt": "vi-VN",
    "Japanese": "ja-JP",
    "Chinese": "zh-CN",
    "Korean": "ko-KR",
    "Thai": "th-TH",
    "Arabic": "ar-SA",
    "Hindi": "hi-IN",
    "Russian": "ru-RU",
}


def test_required_languages_resolve_supported_voice_routes():
    for language, code in SUPPORTED.items():
        route = resolve_subdub_tts_language_route({
            "target_language": language,
            "voice_kind": "default_female",
        })
        assert route["ok"] is True
        assert route["resolved_tts_language_code"] == code
        assert route["resolved_edge_voice_id"]
        assert route["unsupported_reason"] == ""


def test_vietnamese_and_native_aliases_resolve():
    cases = {
        "tiếng Việt": "vi-VN",
        "日本語": "ja-JP",
        "中文": "zh-CN",
        "한국어": "ko-KR",
        "ไทย": "th-TH",
        "العربية": "ar-SA",
        "हिन्दी": "hi-IN",
        "русский": "ru-RU",
    }
    for label, code in cases.items():
        assert resolve_subdub_tts_language_route({"target_language": label})["resolved_tts_language_code"] == code


def test_unsupported_language_is_blocked_before_any_provider_step():
    calls = {"prepare": 0, "voice": 0, "tts": 0, "render": 0}

    async def prepare(_state):
        calls["prepare"] += 1
        raise AssertionError("prepare must not run")

    def voice(_user_id, _state):
        calls["voice"] += 1
        return "voice"

    async def synthesize(*_args, **_kwargs):
        calls["tts"] += 1
        return {}

    async def render(*_args, **_kwargs):
        calls["render"] += 1
        return b"", ""

    result = asyncio.run(pipeline.process_subtitle_dub_job(
        mode=pipeline.VIDEO_SUBTITLE_MODE_DUB,
        state={"target_language": "Klingon", "content_type": "video/mp4"},
        user_id=1,
        prepare_subtitles=prepare,
        srt_from_text=lambda *_args: "",
        segments_from_text=lambda *_args: [],
        segments_from_subtitle=lambda *_args: [],
        subtitle_output_items=lambda *_args: [],
        resolve_voice_id=voice,
        parse_voice_speed=lambda _value: 1.0,
        synthesize_segments=synthesize,
        build_timeline_audio=lambda *_args: (b"", ""),
        normalize_audio=lambda value: (value, ""),
        render_video=render,
        video_render_ready=lambda _value: True,
        ffmpeg_ready=lambda: True,
        dub_mux_enabled=True,
    ))

    assert result["ok"] is False
    assert result["status"] == "UNSUPPORTED_LANGUAGE_FOR_TTS"
    assert result["unsupported_reason"] == "unsupported_language_for_tts"
    assert result["provider_called"] is False
    assert result["tts_provider_called"] is False
    assert calls == {"prepare": 0, "voice": 0, "tts": 0, "render": 0}


def test_supported_language_metadata_reaches_tts_without_real_provider_call():
    captured = {}

    async def prepare(state):
        segments = [{"index": 1, "start": 0.0, "end": 1.0, "text": "こんにちは"}]
        return {
            "state": dict(state),
            "source_bytes": b"video",
            "content_type": "video/mp4",
            "source_segments": [{"index": 1, "start": 0.0, "end": 1.0, "text": "Hello"}],
            "output_segments": segments,
            "output_script": "こんにちは",
            "output_subtitle": "1\n00:00:00,000 --> 00:00:01,000\nこんにちは\n",
            "translation_provider": "fixture",
        }

    async def synthesize(segments, **kwargs):
        captured.update(kwargs)
        assert segments[0]["text"] == "こんにちは"
        return {
            "provider": "fixture",
            "chunks": [{"index": 1, "start": 0.0, "end": 1.0, "audio_bytes": b"audio"}],
        }

    result = asyncio.run(pipeline.process_subtitle_dub_job(
        mode=pipeline.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        state={
            "target_language": "Japanese",
            "translate_requested": "1",
            "voice_kind": "default_female",
            "voice_speed": "1.0",
        },
        user_id=1,
        prepare_subtitles=prepare,
        srt_from_text=lambda *_args: "",
        segments_from_text=lambda *_args: [],
        segments_from_subtitle=lambda *_args: [],
        subtitle_output_items=lambda *_args: [{"filename": "translated.srt", "bytes": b"srt"}],
        resolve_voice_id=lambda _user_id, state: state.update({
            "_subdub_voice_resolution": {"ok": True, "selected_voice_label": "Giọng nữ"}
        }) or "female-multilingual",
        parse_voice_speed=lambda _value: 1.0,
        synthesize_segments=synthesize,
        build_timeline_audio=lambda *_args: (b"timeline", "fixture"),
        normalize_audio=lambda value: (value, "fixture"),
        render_video=lambda *_args, **_kwargs: (b"final-mp4", "fixture"),
        video_render_ready=lambda _value: True,
        ffmpeg_ready=lambda: True,
        dub_mux_enabled=True,
    ))

    assert result["ok"] is True
    assert captured["tts_language_code"] == "ja-JP"
    assert captured["tts_language_boost"] == "Japanese"
    assert captured["edge_voice_id"] == "ja-JP-NanamiNeural"
    assert result["requested_target_language"] == "Japanese"
    assert result["resolved_tts_language_code"] == "ja-JP"
    assert result["resolved_voice_id_masked"].startswith("fema")
    assert result["unsupported_reason"] == ""


def test_source_mode_uses_detected_source_language_route():
    route = resolve_subdub_tts_language_route({
        "target_language": "Giữ nguyên ngôn ngữ gốc",
        "source_language": "Chinese",
        "voice_kind": "default_male",
    })
    assert route["ok"] is True
    assert route["resolved_tts_language_code"] == "zh-CN"
    assert route["resolved_edge_voice_id"] == "zh-CN-YunxiNeural"


def test_unknown_source_language_can_use_auto_without_fake_specific_locale():
    for source_language in ("", "auto", "unknown"):
        route = resolve_subdub_tts_language_route({
            "target_language": "original",
            "source_language": source_language,
        })
        assert route["ok"] is True
        assert route["resolved_tts_language_code"] == "auto"
        assert route["resolved_edge_voice_id"] == ""


def test_subdub_edge_fallback_uses_resolved_locale_voice_without_network(monkeypatch):
    captured = {}

    async def fake_edge(text, voice_id="", voice_speed="1.0", edge_func=None):
        del edge_func
        captured.update({"text": text, "voice_id": voice_id, "voice_speed": voice_speed})
        return "PASS", b"fixture-audio", "fixture", 200

    monkeypatch.setattr(bot, "TTS_PROVIDER", "edge")
    monkeypatch.setattr(bot, "call_edge_tts_with_speed", fake_edge)
    provider, audio, _detail = asyncio.run(bot.video_dubbing_tts_bytes(
        "こんにちは",
        voice_id="female-multilingual",
        voice_speed="1.0",
        tts_language_code="ja-JP",
        tts_language_boost="Japanese",
        edge_voice_id="ja-JP-NanamiNeural",
    ))

    assert provider == "Edge TTS"
    assert audio == b"fixture-audio"
    assert captured["voice_id"] == "ja-JP-NanamiNeural"


def test_key4u_international_route_never_falls_into_vietnamese_only_payload(monkeypatch):
    calls = {"fallback": 0, "tts": 0}

    class FakeProvider:
        async def voice_tts_fallback(self, *_args, **_kwargs):
            calls["fallback"] += 1
            return {"ok": False, "status": "MISSING", "error_message_safe": "fixture"}

        async def tts(self, *_args, **_kwargs):
            calls["tts"] += 1
            raise AssertionError("Vietnamese-only provider payload must not run")

    monkeypatch.setattr(bot, "key4u_minimax_tts_configured", lambda require_public=True: True)
    monkeypatch.setattr(bot, "key4u_provider_instance", lambda: FakeProvider())
    status, audio, detail, _http = asyncio.run(bot.key4u_minimax_tts_bytes(
        "こんにちは",
        voice_id="female-multilingual",
        tts_language_code="ja-JP",
        tts_language_boost="Japanese",
    ))

    assert status == "UNSUPPORTED_LANGUAGE_ROUTE"
    assert audio == b""
    assert "multilingual_route_unavailable" in detail
    assert calls == {"fallback": 1, "tts": 0}
