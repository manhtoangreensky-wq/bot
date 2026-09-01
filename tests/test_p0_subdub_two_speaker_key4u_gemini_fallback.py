import asyncio

import bot
import pytest


WHISPER_SEGMENTS = [
    {"index": 1, "start": 0.0, "end": 1.0, "text": "你好"},
    {"index": 2, "start": 1.0, "end": 2.0, "text": "世界"},
    {"index": 3, "start": 2.0, "end": 3.0, "text": "再见"},
    {"index": 4, "start": 3.0, "end": 4.0, "text": "朋友"},
]

GEMINI_WORDS = [
    {"word": "你好", "start": 0.0, "end": 1.0, "speaker": "spk_0"},
    {"word": "世界", "start": 1.0, "end": 2.0, "speaker": "spk_1"},
    {"word": "再见", "start": 2.0, "end": 3.0, "speaker": "spk_0"},
    {"word": "朋友", "start": 3.0, "end": 4.0, "speaker": "spk_1"},
]


def _configure(monkeypatch):
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "deepgram-fixture")
    monkeypatch.setattr(bot, "GEMINI_API_KEY", "gemini-fixture")
    monkeypatch.setattr(bot, "KEY4U_ENABLED", True)
    monkeypatch.setattr(bot, "KEY4U_API_KEY", "key4u-fixture")
    monkeypatch.setattr(bot, "KEY4U_OPENAI_BASE_URL", "https://api.key4u.shop/v1")
    monkeypatch.setattr(bot, "KEY4U_STT_ENDPOINT", "/audio/transcriptions")
    monkeypatch.setattr(bot, "KEY4U_STT_MODEL", "whisper-1")
    monkeypatch.setattr(bot, "save_provider_attempt", lambda *_args, **_kwargs: None)


async def _empty_deepgram(*_args, **_kwargs):
    return {
        "ok": False,
        "status": "deepgram_empty_transcript",
        "transcript": "",
        "transcript_json": {},
        "detail": "empty transcript",
    }


def test_openai_compatible_asr_multipart_is_async_client_compatible(monkeypatch):
    captured = {}
    original_async_client = bot.httpx.AsyncClient

    async def handler(request):
        captured["request"] = request
        captured["body"] = await request.aread()
        return bot.httpx.Response(
            200,
            json={
                "text": "你好世界",
                "language": "chinese",
                "duration": 2.0,
                "segments": [
                    {"start": 0.0, "end": 1.0, "text": "你好"},
                    {"start": 1.0, "end": 2.0, "text": "世界"},
                ],
            },
        )

    transport = bot.httpx.MockTransport(handler)

    def async_client(**kwargs):
        return original_async_client(
            timeout=kwargs.get("timeout"),
            transport=transport,
        )

    monkeypatch.setattr(bot.httpx, "AsyncClient", async_client)

    result = asyncio.run(
        bot.openai_compatible_asr_transcribe(
            b"fixture-audio",
            "audio/mpeg",
            base_url="https://api.key4u.vn/v1",
            api_key="key4u-fixture",
            endpoint="/audio/transcriptions",
            model="whisper-1",
            language="zh",
        )
    )

    assert result["ok"] is True
    assert result["status"] == "PASS"
    assert result["http_status"] == 200
    assert result["provider_timestamps"] is True
    assert len(result["segments"]) == 2
    assert captured["request"].url == "https://api.key4u.vn/v1/audio/transcriptions"
    body = captured["body"]
    assert b'name="response_format"' in body
    assert b"verbose_json" in body
    assert b'name="timestamp_granularities[]"' in body
    assert b"segment" in body


def test_confirmed_two_speaker_empty_deepgram_uses_key4u_cues_and_gemini_speakers(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(bot, "deepgram_asr_adapter", _empty_deepgram)
    calls = {"key4u": [], "gemini": []}

    async def key4u_asr(_audio, _content_type, **kwargs):
        calls["key4u"].append(dict(kwargs))
        return {
            "ok": True,
            "status": "PASS",
            "text": "你好世界再见朋友",
            "segments": [dict(item) for item in WHISPER_SEGMENTS],
            "provider_timestamps": True,
            "language": "chinese",
            "duration_seconds": 4.0,
            "http_status": 200,
            "detail": "fixture whisper pass",
        }

    async def gemini_diarization(_audio, _content_type, **kwargs):
        calls["gemini"].append(dict(kwargs))
        return {
            "ok": True,
            "status": "PASS",
            "provider": "gemini_transcribe",
            "words": [dict(item) for item in GEMINI_WORDS],
            "speaker_ids": ["spk_0", "spk_1"],
            "http_status": 200,
            "detail": "fixture diarization pass",
        }

    monkeypatch.setattr(bot, "openai_compatible_asr_transcribe", key4u_asr)
    monkeypatch.setattr(
        bot.subdub_two_speaker_asr_fallback,
        "gemini_transcribe_diarized_words",
        gemini_diarization,
    )

    result = asyncio.run(
        bot.asr_transcribe_audio(
            b"fixture-audio",
            "audio/mpeg",
            language="zh",
            allow_subdub_public=True,
            allow_confirmed_product=True,
            require_diarization=True,
            allow_two_speaker_key4u_fallback=True,
        )
    )

    assert result["ok"] is True
    assert result["status"] == "PASS"
    assert result["provider"] == "key4u_audio+gemini_diarization"
    assert [item["speaker"] for item in result["segments"]] == [0, 1, 0, 1]
    assert all(item["speaker_confidence"] >= 0.70 for item in result["segments"])
    assert [item["text"] for item in result["segments"]] == ["你好", "世界", "再见", "朋友"]
    assert len(calls["key4u"]) == 1
    assert calls["key4u"][0]["model"] == "whisper-1"
    assert calls["key4u"][0]["base_url"] == "https://api.key4u.vn/v1"
    assert calls["gemini"] == [{"api_key": "gemini-fixture", "language": "zh"}]


def test_diarized_route_without_two_speaker_fallback_stops_after_deepgram(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(bot, "deepgram_asr_adapter", _empty_deepgram)
    calls = []

    async def forbidden_provider(*_args, **_kwargs):
        calls.append("fallback")
        raise AssertionError("multi/default/manual route must not use two-speaker fallback")

    monkeypatch.setattr(bot, "openai_compatible_asr_transcribe", forbidden_provider)
    monkeypatch.setattr(
        bot.subdub_two_speaker_asr_fallback,
        "gemini_transcribe_diarized_words",
        forbidden_provider,
    )

    result = asyncio.run(
        bot.asr_transcribe_audio(
            b"fixture-audio",
            "audio/mpeg",
            language="zh",
            allow_subdub_public=True,
            allow_confirmed_product=True,
            require_diarization=True,
        )
    )

    assert result["ok"] is False
    assert result["status"] == "deepgram_empty_transcript"
    assert result["segments"] == []
    assert calls == []


def test_two_speaker_fallback_rejects_single_speaker_instead_of_forcing_a_pair(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(bot, "deepgram_asr_adapter", _empty_deepgram)

    async def key4u_asr(_audio, _content_type, **_kwargs):
        return {
            "ok": True,
            "status": "PASS",
            "text": "你好世界再见朋友",
            "segments": [dict(item) for item in WHISPER_SEGMENTS],
            "provider_timestamps": True,
            "language": "chinese",
            "duration_seconds": 4.0,
            "http_status": 200,
            "detail": "fixture whisper pass",
        }

    async def unsafe_single_speaker(_audio, _content_type, **_kwargs):
        return {
            "ok": True,
            "status": "PASS",
            "provider": "gemini_transcribe",
            "words": [
                {**item, "speaker": "spk_0"}
                for item in GEMINI_WORDS
            ],
            "speaker_ids": ["spk_0"],
            "http_status": 200,
            "detail": "fixture unsafe single speaker",
        }

    monkeypatch.setattr(bot, "openai_compatible_asr_transcribe", key4u_asr)
    monkeypatch.setattr(
        bot.subdub_two_speaker_asr_fallback,
        "gemini_transcribe_diarized_words",
        unsafe_single_speaker,
    )

    result = asyncio.run(
        bot.asr_transcribe_audio(
            b"fixture-audio",
            "audio/mpeg",
            language="zh",
            allow_subdub_public=True,
            allow_confirmed_product=True,
            require_diarization=True,
            allow_two_speaker_key4u_fallback=True,
        )
    )

    assert result["ok"] is False
    assert result["status"] == bot.AUTO_CAST_UNAVAILABLE
    assert result["segments"] == []


def test_two_speaker_fallback_rejects_text_only_key4u_before_gemini(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(bot, "deepgram_asr_adapter", _empty_deepgram)
    gemini_calls = []

    async def synthetic_key4u(_audio, _content_type, **_kwargs):
        return {
            "ok": True,
            "status": "PASS",
            "text": "你好世界再见朋友",
            "segments": [dict(item) for item in WHISPER_SEGMENTS],
            "provider_timestamps": False,
            "language": "chinese",
            "duration_seconds": 4.0,
            "http_status": 200,
            "detail": "fixture text-only synthetic segments",
        }

    async def forbidden_gemini(*_args, **_kwargs):
        gemini_calls.append("gemini")
        raise AssertionError("text-only Key4U result must stop before Gemini")

    monkeypatch.setattr(bot, "openai_compatible_asr_transcribe", synthetic_key4u)
    monkeypatch.setattr(
        bot.subdub_two_speaker_asr_fallback,
        "gemini_transcribe_diarized_words",
        forbidden_gemini,
    )

    result = asyncio.run(
        bot.asr_transcribe_audio(
            b"fixture-audio",
            "audio/mpeg",
            language="zh",
            allow_subdub_public=True,
            allow_confirmed_product=True,
            require_diarization=True,
            allow_two_speaker_key4u_fallback=True,
        )
    )

    assert result["ok"] is False
    assert result["status"] == bot.AUTO_CAST_UNAVAILABLE
    assert result["segments"] == []
    assert result["detail"] == "key4u_provider_timestamps_required"
    assert gemini_calls == []


def test_two_speaker_long_media_fails_before_any_asr_provider(monkeypatch):
    _configure(monkeypatch)
    calls = []

    def chunk_plan(*_args, **_kwargs):
        return {
            "chunking_enabled": True,
            "chunk_count": 2,
            "chunk_metadata": [
                {"index": 1, "start": 0.0, "end": 180.0},
                {"index": 2, "start": 180.0, "end": 301.0},
            ],
        }

    async def forbidden_provider(*_args, **_kwargs):
        calls.append("provider")
        raise AssertionError("unsupported long fallback must stop before ASR")

    monkeypatch.setattr(bot, "subdub_long_video_chunk_plan", chunk_plan)
    monkeypatch.setattr(bot, "asr_transcribe_audio", forbidden_provider)
    monkeypatch.setattr(bot, "video_dubbing_extract_audio_chunk", forbidden_provider)

    result = asyncio.run(
        bot.transcribe_media_to_segments(
            {
                "bytes": b"fixture-audio",
                "content_type": "audio/mpeg",
                "media_kind": "audio",
                "duration_seconds": 301,
            },
            duration_seconds=301,
            allow_confirmed_product=True,
            require_diarization=True,
            allow_two_speaker_key4u_fallback=True,
        )
    )

    assert result["output_valid"] is False
    assert result["status"] == bot.AUTO_CAST_UNAVAILABLE
    assert result["detail"] == "two_speaker_fallback_long_media_unsupported"
    assert result["chunk_count"] == 2
    assert calls == []


@pytest.mark.parametrize(
    (
        "lane_patch",
        "expected_diarization",
        "expected_fallback",
        "expected_word_timeline",
    ),
    (
        ({}, True, True, False),
        ({"auto_speaker_lane": "multi"}, False, False, True),
    ),
)
def test_prepare_subtitles_scopes_fallback_to_exact_two_and_words_to_multi(
    monkeypatch,
    tmp_path,
    lane_patch,
    expected_diarization,
    expected_fallback,
    expected_word_timeline,
):
    captured = []
    source_srt = "1\n00:00:00,000 --> 00:00:01,000\nhello\n"

    async def fake_resolve(
        *_args,
        require_diarization=False,
        allow_two_speaker_key4u_fallback=False,
        require_auto_multi_word_timeline=False,
        **_kwargs,
    ):
        captured.append(
            (
                require_diarization,
                allow_two_speaker_key4u_fallback,
                require_auto_multi_word_timeline,
            )
        )
        result = {
            "source_kind": "asr",
            "subtitle": source_srt,
            "script": "hello",
            "asr_provider": "fixture",
            "segments": [
                {
                    "index": 1,
                    "start": 0.0,
                    "end": 1.0,
                    "text": "hello",
                    "speaker": 0,
                    "speaker_confidence": 0.9,
                }
            ],
            "detected_language": "en",
        }
        if require_auto_multi_word_timeline:
            result["word_timeline"] = [
                {
                    "index": index,
                    "word": f"word{index}",
                    "start": index * 0.2,
                    "end": index * 0.2 + 0.1,
                }
                for index in range(30)
            ]
            result["duration_seconds"] = 6.0
        return result

    async def fake_extract_pcm(*_args, **_kwargs):
        pcm_path = tmp_path / "multi-acoustic.pcm"
        pcm_path.write_bytes(b"\x01\x00" * 8_000)
        return str(pcm_path)

    async def fake_acoustic(*_args, **_kwargs):
        return {
            "ok": True,
            "status": "PASS",
            "provider": "local_wespeaker_resnet34_spectral",
            "segments": [
                {
                    "cue_id": f"acoustic-{speaker}",
                    "index": speaker + 1,
                    "start": float(speaker * 2),
                    "end": float((speaker + 1) * 2),
                    "text": f"speaker {speaker}",
                    "speaker": speaker,
                    "speaker_id": f"chunk_00:speaker_{speaker}",
                    "speaker_confidence": 0.9,
                    "chunk_index": 0,
                }
                for speaker in range(3)
            ],
            "detected_speaker_count": 3,
            "model_sha256": bot.auto_multi_speaker.subdub_multi_speaker_embedding_onnx.MODEL_SHA256,
            "algorithm_version": bot.auto_multi_speaker.subdub_multi_speaker_embedding_onnx.ALGORITHM_VERSION,
            "word_count": 30,
            "unit_count": 6,
            "embedding_window_count": 12,
            "cluster_sizes": [2, 2, 2],
            "stability_pass": True,
            "word_coverage_count": 30,
        }

    monkeypatch.setattr(bot, "video_dubbing_resolve_source_script", fake_resolve)
    monkeypatch.setattr(bot, "_extract_subdub_auto_pcm", fake_extract_pcm)
    monkeypatch.setattr(
        bot.auto_multi_speaker,
        "run_local_acoustic_diarization_off_event_loop",
        fake_acoustic,
    )
    monkeypatch.setattr(bot, "set_video_dubbing_artifact", lambda *_args: "source-ref")
    monkeypatch.setattr(
        bot,
        "set_video_dubbing_pending",
        lambda _user_id, step, **fields: {"step": step, **fields},
    )
    state = {
        "step": "processing",
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "source_file_id": "media-id",
        "source_media_type": "video",
        "source_mime_type": "video/mp4",
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "_pipeline_workspace": str(tmp_path),
        "_pipeline_source_bytes_override": b"fresh-media",
        "_pipeline_source_content_type_override": "video/mp4",
        **lane_patch,
    }

    asyncio.run(
        bot.video_dubbing_prepare_subtitles(
            None,
            state,
            123,
            allow_confirmed_product=True,
            require_auto_cast=True,
        )
    )

    assert captured == [
        (expected_diarization, expected_fallback, expected_word_timeline)
    ]
