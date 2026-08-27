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
