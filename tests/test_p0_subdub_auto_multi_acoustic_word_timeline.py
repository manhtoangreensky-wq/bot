from __future__ import annotations

import asyncio
import copy
import math

import pytest

import bot


def deepgram_payload() -> dict:
    return {
        "metadata": {"duration": 2.0},
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {
                            "transcript": "Hello world",
                            "words": [
                                {
                                    "word": "hello",
                                    "punctuated_word": "Hello",
                                    "start": 0.1,
                                    "end": 0.4,
                                    "speaker": 19,
                                    "speaker_confidence": 0.99,
                                },
                                {
                                    "word": "world",
                                    "punctuated_word": "world",
                                    "start": 0.5,
                                    "end": 0.9,
                                    "speaker": 77,
                                    "speaker_confidence": 0.01,
                                },
                            ],
                        }
                    ]
                }
            ]
        },
    }


EXPECTED_WORDS = [
    {"index": 0, "word": "Hello", "start": 0.1, "end": 0.4},
    {"index": 1, "word": "world", "start": 0.5, "end": 0.9},
]


def test_acoustic_word_extractor_uses_strict_text_and_times_without_speaker_labels():
    assert bot.deepgram_acoustic_word_items(
        deepgram_payload(),
        duration_seconds=2.0,
    ) == EXPECTED_WORDS


@pytest.mark.parametrize(
    "mutation",
    (
        "payload_not_dict",
        "channels_not_list",
        "alternatives_not_list",
        "words_not_list",
        "empty_words",
        "word_not_dict",
        "missing_text",
        "text_not_string",
        "start_bool",
        "start_nan",
        "start_inf",
        "end_nan",
        "negative_start",
        "nonpositive_duration",
        "decreasing_start",
        "past_source_duration",
        "duplicate_identity",
        "invalid_source_duration",
    ),
)
def test_acoustic_word_extractor_rejects_entire_malformed_timeline(mutation):
    payload = copy.deepcopy(deepgram_payload())
    duration = 2.0
    words = payload["results"]["channels"][0]["alternatives"][0]["words"]
    if mutation == "payload_not_dict":
        payload = []
    elif mutation == "channels_not_list":
        payload["results"]["channels"] = {}
    elif mutation == "alternatives_not_list":
        payload["results"]["channels"][0]["alternatives"] = {}
    elif mutation == "words_not_list":
        payload["results"]["channels"][0]["alternatives"][0]["words"] = {}
    elif mutation == "empty_words":
        words.clear()
    elif mutation == "word_not_dict":
        words[0] = "hello"
    elif mutation == "missing_text":
        words[0].pop("word")
        words[0].pop("punctuated_word")
    elif mutation == "text_not_string":
        words[0]["punctuated_word"] = 123
        words[0]["word"] = 123
    elif mutation == "start_bool":
        words[0]["start"] = True
    elif mutation == "start_nan":
        words[0]["start"] = math.nan
    elif mutation == "start_inf":
        words[0]["start"] = math.inf
    elif mutation == "end_nan":
        words[0]["end"] = math.nan
    elif mutation == "negative_start":
        words[0]["start"] = -0.1
    elif mutation == "nonpositive_duration":
        words[0]["end"] = words[0]["start"]
    elif mutation == "decreasing_start":
        words[1]["start"] = 0.05
    elif mutation == "past_source_duration":
        words[1]["end"] = 2.1
    elif mutation == "duplicate_identity":
        words.append(dict(words[1]))
    else:
        duration = math.nan

    assert bot.deepgram_acoustic_word_items(payload, duration_seconds=duration) == []


def configure_deepgram_route(monkeypatch):
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "configured")
    monkeypatch.setattr(bot, "ASR_PROVIDER", "key4u")
    monkeypatch.setattr(bot, "save_provider_attempt", lambda *_args, **_kwargs: None)


def test_acoustic_word_routing_uses_confirmed_nondiarized_deepgram(monkeypatch):
    configure_deepgram_route(monkeypatch)
    captured = []

    async def fake_deepgram(
        audio_bytes,
        content_type,
        *,
        require_diarization=False,
        timeout_seconds=60.0,
    ):
        captured.append(
            {
                "audio_bytes": audio_bytes,
                "content_type": content_type,
                "require_diarization": require_diarization,
                "timeout_seconds": timeout_seconds,
            }
        )
        return {
            "ok": True,
            "status": "PASS",
            "transcript": "Hello world",
            "transcript_json": deepgram_payload(),
            "http_status": 200,
            "detail": "fixture",
        }

    monkeypatch.setattr(bot, "deepgram_asr_adapter", fake_deepgram)
    result = asyncio.run(
        bot.asr_transcribe_audio(
            b"wav",
            "audio/wav",
            allow_confirmed_product=True,
            require_auto_multi_word_timeline=True,
            timeout_seconds=17.0,
        )
    )

    assert captured == [
        {
            "audio_bytes": b"wav",
            "content_type": "audio/wav",
            "require_diarization": False,
            "timeout_seconds": 17.0,
        }
    ]
    assert result["ok"] is True
    assert result["provider"] == "deepgram"
    assert result["word_timeline"] == EXPECTED_WORDS
    assert all("speaker" not in item for item in result["word_timeline"])


def test_acoustic_word_routing_requires_confirmation_before_provider(monkeypatch):
    configure_deepgram_route(monkeypatch)

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("provider call must be gated")

    monkeypatch.setattr(bot, "deepgram_asr_adapter", forbidden)
    result = asyncio.run(
        bot.asr_transcribe_audio(
            b"wav",
            "audio/wav",
            require_auto_multi_word_timeline=True,
        )
    )

    assert result["ok"] is False
    assert result["status"] == bot.AUTO_CAST_UNAVAILABLE
    assert result["word_timeline"] == []


def test_acoustic_word_routing_rejects_missing_strict_words(monkeypatch):
    configure_deepgram_route(monkeypatch)
    payload = deepgram_payload()
    payload["results"]["channels"][0]["alternatives"][0]["words"] = []

    async def fake_deepgram(*_args, **_kwargs):
        return {
            "ok": True,
            "status": "PASS",
            "transcript": "Hello world",
            "transcript_json": payload,
            "http_status": 200,
            "detail": "fixture",
        }

    monkeypatch.setattr(bot, "deepgram_asr_adapter", fake_deepgram)
    result = asyncio.run(
        bot.asr_transcribe_audio(
            b"wav",
            "audio/wav",
            allow_confirmed_product=True,
            require_auto_multi_word_timeline=True,
        )
    )

    assert result["ok"] is False
    assert result["status"] == bot.AUTO_CAST_UNAVAILABLE
    assert result["provider"] == "deepgram"
    assert result["word_timeline"] == []
    assert result["detail"] == "ACOUSTIC_WORD_TIMELINE_REQUIRED"


def test_acoustic_word_routing_rejects_conflicting_authorities(monkeypatch):
    configure_deepgram_route(monkeypatch)

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("conflicting authority must fail before provider")

    monkeypatch.setattr(bot, "deepgram_asr_adapter", forbidden)
    result = asyncio.run(
        bot.asr_transcribe_audio(
            b"wav",
            "audio/wav",
            allow_confirmed_product=True,
            require_diarization=True,
            require_auto_multi_word_timeline=True,
        )
    )

    assert result == {
        "ok": False,
        "status": bot.AUTO_CAST_UNAVAILABLE,
        "provider": "",
        "text": "",
        "segments": [],
        "word_timeline": [],
        "detail": "acoustic_word_timeline_conflict",
    }


def test_normal_deepgram_route_keeps_old_result_shape(monkeypatch):
    configure_deepgram_route(monkeypatch)
    monkeypatch.setattr(bot, "ASR_PROVIDER", "deepgram")

    async def fake_deepgram(audio_bytes, content_type):
        assert audio_bytes == b"wav"
        assert content_type == "audio/wav"
        return {
            "ok": True,
            "status": "PASS",
            "transcript": "Hello world",
            "transcript_json": deepgram_payload(),
            "http_status": 200,
        }

    monkeypatch.setattr(bot, "deepgram_asr_adapter", fake_deepgram)
    result = asyncio.run(
        bot.asr_transcribe_audio(
            b"wav",
            "audio/wav",
            allow_confirmed_product=True,
        )
    )

    assert result["ok"] is True
    assert "word_timeline" not in result


def test_acoustic_word_timeline_propagates_through_media_transcription(monkeypatch):
    captured = []

    async def fake_asr(*_args, **kwargs):
        captured.append(dict(kwargs))
        return {
            "ok": True,
            "status": "PASS",
            "provider": "deepgram",
            "text": "Hello world",
            "segments": [{"start": 0.1, "end": 0.9, "text": "Hello world"}],
            "word_timeline": list(EXPECTED_WORDS),
            "detail": "fixture",
            "duration_seconds": 2.0,
        }

    monkeypatch.setattr(bot, "asr_transcribe_audio", fake_asr)
    result = asyncio.run(
        bot.transcribe_media_to_segments(
            {
                "bytes": b"wav",
                "content_type": "audio/wav",
                "media_kind": "audio",
                "duration_seconds": 2,
            },
            duration_seconds=2,
            allow_confirmed_product=True,
            require_auto_multi_word_timeline=True,
        )
    )

    assert captured[0]["require_auto_multi_word_timeline"] is True
    assert captured[0].get("require_diarization") is None
    assert result["output_valid"] is True
    assert result["word_timeline"] == EXPECTED_WORDS


def test_acoustic_word_timeline_fails_closed_before_chunk_estimation(monkeypatch):
    monkeypatch.setattr(
        bot,
        "subdub_long_video_chunk_plan",
        lambda *_args, **_kwargs: {
            "chunking_enabled": True,
            "chunk_count": 2,
            "chunk_metadata": [],
        },
    )

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("acoustic word timing must not be estimated per chunk")

    monkeypatch.setattr(bot, "asr_transcribe_audio", forbidden)
    result = asyncio.run(
        bot.transcribe_media_to_segments(
            {
                "bytes": b"wav",
                "content_type": "audio/wav",
                "media_kind": "audio",
                "duration_seconds": 301,
            },
            duration_seconds=301,
            allow_confirmed_product=True,
            require_auto_multi_word_timeline=True,
        )
    )

    assert result["output_valid"] is False
    assert result["status"] == bot.AUTO_CAST_UNAVAILABLE
    assert result["word_timeline"] == []
    assert result["chunk_strategy"] == "acoustic_word_timeline_long_media_guard"


def test_acoustic_resolver_bypasses_embedded_subtitle_and_returns_words(monkeypatch):
    captured = []

    async def fake_embedded(*_args, **_kwargs):
        return "1\n00:00:00,000 --> 00:00:01,000\nEmbedded\n", "embedded"

    async def fake_transcribe(*_args, **kwargs):
        captured.append(dict(kwargs))
        return {
            "output_valid": True,
            "status": "PASS",
            "transcript_text": "Hello world",
            "segments": [{"start": 0.1, "end": 0.9, "text": "Hello world"}],
            "word_timeline": list(EXPECTED_WORDS),
            "detected_language": "en",
            "duration_seconds": 2,
            "provider": "deepgram",
            "detail": "fixture",
            "chunk_count": 1,
            "chunk_strategy": "single_pass",
            "global_timing_preserved": True,
        }

    monkeypatch.setattr(bot, "video_dubbing_extract_embedded_subtitle", fake_embedded)
    monkeypatch.setattr(bot, "transcribe_media_to_segments", fake_transcribe)
    result = asyncio.run(
        bot.video_dubbing_resolve_source_script(
            b"wav",
            "audio/wav",
            None,
            duration_seconds=2,
            allow_confirmed_product=True,
            require_auto_multi_word_timeline=True,
        )
    )

    assert captured[0]["require_auto_multi_word_timeline"] is True
    assert result["source_kind"] == "asr"
    assert result["word_timeline"] == EXPECTED_WORDS


def test_acoustic_resolver_rejects_success_without_word_timeline(monkeypatch):
    async def forbidden_embedded(*_args, **_kwargs):
        raise AssertionError("acoustic resolver must bypass embedded subtitles")

    async def fake_transcribe(*_args, **_kwargs):
        return {
            "output_valid": True,
            "status": "PASS",
            "transcript_text": "Hello world",
            "segments": [{"start": 0.1, "end": 0.9, "text": "Hello world"}],
            "detected_language": "en",
            "duration_seconds": 2,
            "provider": "deepgram",
            "detail": "fixture",
        }

    monkeypatch.setattr(
        bot,
        "video_dubbing_extract_embedded_subtitle",
        forbidden_embedded,
    )
    monkeypatch.setattr(bot, "transcribe_media_to_segments", fake_transcribe)

    with pytest.raises(bot.subdub_speaker_cast.AutoCastUnavailable):
        asyncio.run(
            bot.video_dubbing_resolve_source_script(
                b"wav",
                "audio/wav",
                None,
                duration_seconds=2,
                allow_confirmed_product=True,
                require_auto_multi_word_timeline=True,
            )
        )


def test_normal_resolver_still_prefers_embedded_subtitle(monkeypatch):
    async def fake_embedded(*_args, **_kwargs):
        return "1\n00:00:00,000 --> 00:00:01,000\nEmbedded\n", "embedded"

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("normal resolver must retain embedded shortcut")

    monkeypatch.setattr(bot, "video_dubbing_extract_embedded_subtitle", fake_embedded)
    monkeypatch.setattr(bot, "transcribe_media_to_segments", forbidden)
    result = asyncio.run(
        bot.video_dubbing_resolve_source_script(
            b"video",
            "video/mp4",
            None,
        )
    )

    assert result["source_kind"] == "embedded_subtitle"
    assert "word_timeline" not in result
