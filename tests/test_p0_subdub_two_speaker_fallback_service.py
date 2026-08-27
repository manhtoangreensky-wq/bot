import asyncio
from types import SimpleNamespace

from services import subdub_two_speaker_asr_fallback as fallback


DOCUMENTED_RESPONSE = {
    "steps": [
        {
            "content": [
                {
                    "annotations": [
                        {
                            "type": "word_info",
                            "text": "one",
                            "speaker": "spk:0",
                            "start_offset": "0.100s",
                            "end_offset": "0.500s",
                        },
                        {
                            "type": "word_info",
                            "text": "two",
                            "speaker": "spk:0",
                            "start_offset": "0.500s",
                            "end_offset": "1s",
                        },
                        {
                            "type": "word_info",
                            "text": "three",
                            "speaker": "spk:1",
                            "start_offset": "1s",
                            "end_offset": "1.500s",
                        },
                        {
                            "type": "word_info",
                            "text": "four",
                            "speaker": "spk:1",
                            "start_offset": "1.500s",
                            "end_offset": "2s",
                        },
                    ]
                }
            ]
        }
    ]
}


def test_parser_accepts_only_observed_annotation_container():
    words = fallback.extract_gemini_diarized_words(DOCUMENTED_RESPONSE)

    assert len(words) == 4
    assert [item["speaker"] for item in words] == ["spk:0", "spk:0", "spk:1", "spk:1"]
    assert fallback.extract_gemini_diarized_words(
        {
            "metadata": {
                "annotations": [
                    {"speaker": "spk:0", "text": "a", "start_offset": "0s", "end_offset": "1s"},
                    {"speaker": "spk:0", "text": "b", "start_offset": "1s", "end_offset": "2s"},
                    {"speaker": "spk:1", "text": "c", "start_offset": "2s", "end_offset": "3s"},
                    {"speaker": "spk:1", "text": "d", "start_offset": "3s", "end_offset": "4s"},
                ]
            }
        }
    ) == []


def test_parser_rejects_malformed_offsets_and_missing_second_speaker():
    malformed = {
        "steps": [
            {
                "content": [
                    {
                        "annotations": [
                            {
                                "text": "bad",
                                "speaker": "spk:0",
                                "start_offset": "nan",
                                "end_offset": "1s",
                            },
                            {
                                "text": "one",
                                "speaker": "spk:0",
                                "start_offset": "0s",
                                "end_offset": "1s",
                            },
                            {
                                "text": "two",
                                "speaker": "spk:0",
                                "start_offset": "1s",
                                "end_offset": "2s",
                            },
                        ]
                    }
                ]
            }
        ]
    }

    assert fallback.extract_gemini_diarized_words(malformed) == []


def test_cue_mapping_rejects_below_dominance_threshold():
    segments = [{"index": 1, "start": 0.0, "end": 1.0, "text": "cue"}]
    words = [
        {"word": "a", "speaker": "spk:0", "start": 0.0, "end": 0.6},
        {"word": "b", "speaker": "spk:1", "start": 0.4, "end": 1.0},
        {"word": "c", "speaker": "spk:0", "start": 2.0, "end": 2.5},
        {"word": "d", "speaker": "spk:1", "start": 2.5, "end": 3.0},
    ]

    assert fallback.apply_diarized_words_to_segments(segments, words) == []


def test_gemini_request_uses_verbatim_diarization_and_word_timestamps(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return DOCUMENTED_RESPONSE

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            captured["client"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, url, **kwargs):
            captured["url"] = url
            captured["request"] = kwargs
            return FakeResponse()

    monkeypatch.setattr(fallback.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(
        fallback.gemini_transcribe_diarized_words(
            b"audio",
            "audio/mpeg",
            api_key="fixture-secret",
            language="zh",
        )
    )

    request = captured["request"]
    config = request["json"]["generation_config"]["transcription_config"]
    assert captured["url"] == fallback.GEMINI_INTERACTIONS_URL
    assert request["json"]["model"] == "gemini-3.5-transcribe"
    assert config["language_codes"] == ["zh-CN"]
    assert config["mode"] == {
        "type": "verbatim",
        "diarization_mode": "speaker",
        "timestamp_granularities": ["word"],
    }
    assert request["headers"]["x-goog-api-key"] == "fixture-secret"
    assert result["ok"] is True
    assert result["speaker_ids"] == ["spk:0", "spk:1"]


def test_gemini_non_200_is_fail_closed_without_raw_body(monkeypatch):
    class FakeResponse:
        status_code = 429

        def json(self):
            return {"error": {"status": "RESOURCE_EXHAUSTED", "message": "private body"}}

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(fallback.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(
        fallback.gemini_transcribe_diarized_words(
            b"audio",
            "audio/mpeg",
            api_key="fixture-secret",
        )
    )

    assert result["ok"] is False
    assert result["status"] == fallback.AUTO_CAST_UNAVAILABLE
    assert "private body" not in result["detail"]


def test_retryable_empty_key4u_transcript_retries_once_then_continues_to_gemini(
    monkeypatch,
):
    key4u_calls = []
    monkeypatch.setattr(
        fallback,
        "KEY4U_TRANSCRIPT_RETRY_DELAY_SECONDS",
        0.0,
        raising=False,
    )

    async def key4u_transcribe(_audio, _content_type, **kwargs):
        key4u_calls.append(dict(kwargs))
        if len(key4u_calls) == 1:
            return {
                "ok": False,
                "status": "FAIL_PROVIDER_ERROR",
                "http_status": 503,
                "text": "",
                "segments": [],
                "detail": "temporary upstream failure",
            }
        return {
            "ok": True,
            "status": "PASS",
            "http_status": 200,
            "text": "one two three four",
            "segments": [
                {"start": 0.0, "end": 1.0, "text": "one"},
                {"start": 1.0, "end": 2.0, "text": "two"},
                {"start": 2.0, "end": 3.0, "text": "three"},
                {"start": 3.0, "end": 4.0, "text": "four"},
            ],
            "provider_timestamps": True,
        }

    async def gemini_words(*_args, **_kwargs):
        return {
            "ok": True,
            "status": "PASS",
            "words": [
                {"word": "one", "start": 0.1, "end": 0.8, "speaker": "spk:0"},
                {"word": "two", "start": 1.1, "end": 1.8, "speaker": "spk:0"},
                {"word": "three", "start": 2.1, "end": 2.8, "speaker": "spk:1"},
                {"word": "four", "start": 3.1, "end": 3.8, "speaker": "spk:1"},
            ],
            "speaker_ids": ["spk:0", "spk:1"],
        }

    monkeypatch.setattr(fallback, "gemini_transcribe_diarized_words", gemini_words)

    result = asyncio.run(
        fallback.run_two_speaker_fallback(
            b"audio",
            "audio/mpeg",
            key4u_transcribe=key4u_transcribe,
            key4u_api_key="key4u-fixture",
            key4u_endpoint="/audio/transcriptions",
            gemini_api_key="gemini-fixture",
            language="zh",
        )
    )

    assert result["ok"] is True
    assert result["status"] == "PASS"
    assert result["key4u_attempt_count"] == 2
    assert result["key4u_retry_used"] is True
    assert len(key4u_calls) == 2
    assert all(call["base_url"] == "https://api.key4u.vn/v1" for call in key4u_calls)
    assert all(call["model"] == "whisper-1" for call in key4u_calls)


def test_permanent_key4u_401_fails_closed_without_retry_or_gemini(monkeypatch):
    key4u_calls = []
    gemini_calls = []

    async def key4u_transcribe(_audio, _content_type, **kwargs):
        key4u_calls.append(dict(kwargs))
        return {
            "ok": False,
            "status": "FAIL_AUTH",
            "http_status": 401,
            "text": "",
            "segments": [],
            "detail": "private upstream body",
        }

    async def forbidden_gemini(*_args, **_kwargs):
        gemini_calls.append("called")
        raise AssertionError("permanent Key4U failure must stop before Gemini")

    monkeypatch.setattr(
        fallback,
        "gemini_transcribe_diarized_words",
        forbidden_gemini,
    )

    result = asyncio.run(
        fallback.run_two_speaker_fallback(
            b"audio",
            "audio/mpeg",
            key4u_transcribe=key4u_transcribe,
            key4u_api_key="key4u-fixture",
            key4u_endpoint="/audio/transcriptions",
            gemini_api_key="gemini-fixture",
        )
    )

    assert result["ok"] is False
    assert result["status"] == fallback.AUTO_CAST_UNAVAILABLE
    assert result["key4u_attempt_count"] == 1
    assert result["key4u_retry_used"] is False
    assert len(key4u_calls) == 1
    assert gemini_calls == []
    assert "private upstream body" not in result["detail"]
