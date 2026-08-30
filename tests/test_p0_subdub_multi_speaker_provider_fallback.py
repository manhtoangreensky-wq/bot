from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace

import pytest

from services import subdub_multi_speaker_asr_fallback as fallback
from services import subdub_multi_speaker_gender_onnx as multi_gender
from services import subdub_speaker_cast as speaker_cast
from services import subdub_two_speaker_gender_onnx as exact_gender
from services.subdub_blackboxes import auto_multi_speaker


def _load_asr_transcribe_audio_surface(namespace: dict):
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(
        encoding="utf-8",
        errors="replace",
    )
    start = source.index("async def asr_transcribe_audio(")
    end = source.index(
        "\ndef shopaikey_provider_error_from_payload(",
        start,
    )
    import_lines = [
        line
        for line in source[:start].splitlines()
        if line.startswith("from services import ")
        and "subdub_multi_speaker_asr_fallback" in line
    ]
    assert len(import_lines) == 1
    exec(
        "from services import subdub_multi_speaker_asr_fallback",
        namespace,
    )
    exec(compile(source[start:end], "bot.py", "exec"), namespace)
    return namespace["asr_transcribe_audio"]


def _gemini_payload(labels=("spk_1", "spk_2", "spk_3")) -> dict:
    annotations = []
    cursor = 0.0
    for label in labels:
        for index in range(2):
            annotations.append(
                {
                    "type": "word_info",
                    "text": f"word-{label}-{index}",
                    "speaker": label,
                    "start_offset": f"{cursor:.1f}s",
                    "end_offset": f"{cursor + 0.4:.1f}s",
                }
            )
            cursor += 0.5
    return {"steps": [{"content": [{"annotations": annotations}]}]}


def _segments(label_count: int = 2) -> list[dict]:
    return [
        {
            "cue_id": f"cue-{index + 1}",
            "index": index + 1,
            "start": float(index),
            "end": float(index + 1),
            "text": f"speaker {index + 1}",
            "speaker": index % label_count,
            "speaker_confidence": 0.9,
            "speaker_id": f"chunk_00:speaker_{index % label_count}",
            "chunk_index": 0,
        }
        for index in range(6)
    ]


def _prepared(tmp_path: Path) -> dict:
    source = _segments(2)
    sidecar = speaker_cast.build_sidecar(
        source,
        media_sha256="a" * 64,
        subtitle_sha256="b" * 64,
    )
    receipt = speaker_cast.persist_sidecar(sidecar, workspace=str(tmp_path))
    return {
        "source_segments": source,
        "output_segments": [dict(item) for item in source],
        "media_sha256": "a" * 64,
        "subtitle_sha256": "b" * 64,
        "state": {
            "_pipeline_workspace": str(tmp_path),
            "speaker_sidecar_path": receipt["path"],
            "speaker_sidecar_sha256": receipt["sha256"],
            "voice_kind": "auto_speaker_gender",
            "voice_selection_mode": "auto_speaker",
            "auto_speaker_lane": "multi",
        },
    }


def test_multi_gemini_parser_accepts_three_labels_without_expected_count():
    words = fallback.extract_gemini_multi_diarized_words(_gemini_payload())

    assert len(words) == 6
    assert list(dict.fromkeys(item["speaker"] for item in words)) == [
        "spk_1",
        "spk_2",
        "spk_3",
    ]


def test_multi_gemini_parser_rejects_two_or_more_than_eight_labels():
    assert not fallback.extract_gemini_multi_diarized_words(
        _gemini_payload(("spk_1", "spk_2"))
    )


def test_multi_gemini_request_does_not_hint_or_force_speaker_count(monkeypatch):
    captured = {}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, url, **kwargs):
            captured["url"] = url
            captured["json"] = json.loads(kwargs["content"].decode("utf-8"))
            return SimpleNamespace(
                status_code=200,
                json=lambda: _gemini_payload(),
            )

    monkeypatch.setattr(
        fallback.httpx,
        "AsyncClient",
        lambda **_kwargs: Client(),
    )
    result = asyncio.run(
        fallback.gemini_transcribe_multi_diarized_words(
            b"wav",
            "audio/mpeg",
            api_key="configured",
        )
    )

    mode = captured["json"]["generation_config"]["transcription_config"]["mode"]
    serialized = str(captured["json"]).lower()
    assert result["ok"] is True
    assert mode == {
        "type": "verbatim",
        "diarization_mode": "speaker",
        "timestamp_granularities": ["word"],
    }
    assert "expected_speaker" not in serialized
    assert "speaker_count" not in serialized
    assert captured["json"]["input"][0]["mime_type"] == "audio/mpeg"
    assert not fallback.extract_gemini_multi_diarized_words(
        _gemini_payload(tuple(f"spk_{index}" for index in range(1, 10)))
    )


def test_multi_gemini_polls_same_in_progress_interaction_without_second_post(
    monkeypatch,
):
    post_calls = []
    get_calls = []
    sleep_calls = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, url, **_kwargs):
            post_calls.append(url)
            return SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "id": "v1_in_progress_fixture",
                    "status": "in_progress",
                },
            )

        async def get(self, url, **_kwargs):
            get_calls.append(url)
            return SimpleNamespace(
                status_code=200,
                json=lambda: {
                    **_gemini_payload(),
                    "id": "v1_in_progress_fixture",
                    "status": "completed",
                },
            )

    async def no_wait(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(fallback.httpx, "AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr(fallback.asyncio, "sleep", no_wait)

    result = asyncio.run(
        fallback.gemini_transcribe_multi_diarized_words(
            b"wav",
            "audio/wav",
            api_key="configured",
        )
    )

    assert result["ok"] is True
    assert result["status"] == "PASS"
    assert len(post_calls) == 1
    assert get_calls == [
        f"{fallback.GEMINI_INTERACTIONS_URL}/v1_in_progress_fixture"
    ]
    assert sleep_calls == [fallback.GEMINI_INTERACTION_POLL_SECONDS]


def test_multi_gemini_retries_one_terminal_http_200_empty_response(monkeypatch):
    post_calls = []
    get_calls = []
    sleep_calls = []
    responses = [
        {
            "id": "v1_empty_fixture",
            "status": "completed",
            "steps": [],
        },
        {
            **_gemini_payload(),
            "id": "v1_valid_fixture",
            "status": "completed",
        },
    ]

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, url, **_kwargs):
            post_calls.append(url)
            payload = responses[len(post_calls) - 1]
            return SimpleNamespace(status_code=200, json=lambda: payload)

        async def get(self, url, **_kwargs):
            get_calls.append(url)
            raise AssertionError("completed interactions must not be polled")

    async def no_wait(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(fallback.httpx, "AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr(fallback.asyncio, "sleep", no_wait)

    result = asyncio.run(
        fallback.gemini_transcribe_multi_diarized_words(
            b"wav",
            "audio/wav",
            api_key="configured",
        )
    )

    assert result["ok"] is True
    assert result["status"] == "PASS"
    assert len(post_calls) == 2
    assert get_calls == []
    assert sleep_calls == [fallback.GEMINI_EMPTY_RESULT_RETRY_DELAY_SECONDS]


def test_multi_parser_deduplicates_exact_rows_before_minimum_word_gate():
    payload = _gemini_payload()
    annotations = payload["steps"][0]["content"][0]["annotations"]
    third = [item for item in annotations if item["speaker"] == "spk_3"]
    annotations.remove(third[1])
    annotations.append(dict(third[0]))

    assert fallback.extract_gemini_multi_diarized_words(payload) == []


def test_multi_parser_rejects_conflicting_speaker_for_same_word_identity():
    payload = _gemini_payload()
    annotations = payload["steps"][0]["content"][0]["annotations"]
    conflict = dict(annotations[0])
    conflict["speaker"] = "spk_3"
    annotations.append(conflict)

    assert fallback.extract_gemini_multi_diarized_words(payload) == []


def test_mapper_independently_rejects_duplicate_only_third_label():
    words = fallback.extract_gemini_multi_diarized_words(_gemini_payload())
    third = [item for item in words if item["speaker"] == "spk_3"]
    injected = [item for item in words if item is not third[1]]
    injected.append(dict(third[0]))

    assert fallback.apply_multi_diarized_words_to_segments(
        _segments(3)[:3],
        injected,
    ) == []


def test_mapper_independently_rejects_conflicting_word_identity():
    words = fallback.extract_gemini_multi_diarized_words(_gemini_payload())
    conflict = dict(words[0])
    conflict["speaker"] = "spk_3"

    assert fallback.apply_multi_diarized_words_to_segments(
        _segments(3)[:3],
        [*words, conflict],
    ) == []


def test_multi_word_evidence_maps_three_labels_to_existing_cues():
    words = fallback.extract_gemini_multi_diarized_words(_gemini_payload())
    mapped = fallback.apply_multi_diarized_words_to_segments(
        _segments(3)[:3],
        words,
    )

    assert [item["speaker"] for item in mapped] == [0, 1, 2]
    assert [item["speaker_id"] for item in mapped] == [
        "chunk_00:speaker_0",
        "chunk_00:speaker_1",
        "chunk_00:speaker_2",
    ]
    assert all(item["speaker_confidence"] == 1.0 for item in mapped)


def test_deepgram_empty_multi_uses_key4u_gemini_fallback_once(monkeypatch):
    provider_attempts = []
    key4u_calls = []
    gemini_calls = []
    timed_segments = [
        {"index": 1, "start": 0.0, "end": 1.0, "text": "speaker one"},
        {"index": 2, "start": 1.0, "end": 2.0, "text": "speaker two"},
        {"index": 3, "start": 2.0, "end": 3.0, "text": "speaker three"},
    ]

    async def deepgram(*_args, **_kwargs):
        return {
            "ok": False,
            "status": "DEEPGRAM_EMPTY_TRANSCRIPT",
            "detail": "All connection attempts failed",
            "transcript": "",
            "transcript_json": {},
        }

    async def key4u(*_args, **_kwargs):
        key4u_calls.append(True)
        return {
            "ok": True,
            "status": "PASS",
            "text": "speaker one speaker two speaker three",
            "segments": timed_segments,
            "provider_timestamps": True,
            "http_status": 200,
        }

    async def gemini(*_args, **_kwargs):
        gemini_calls.append(True)
        return {
            "ok": True,
            "status": "PASS",
            "words": fallback.extract_gemini_multi_diarized_words(
                _gemini_payload()
            ),
            "speaker_ids": ["spk_1", "spk_2", "spk_3"],
        }

    monkeypatch.setattr(
        fallback,
        "gemini_transcribe_multi_diarized_words",
        gemini,
    )
    namespace = {
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "AUTO_CAST_UNAVAILABLE": "AUTO_CAST_UNAVAILABLE",
        "ASR_PROVIDER": "auto",
        "DEEPGRAM_API_KEY": "configured",
        "KEY4U_API_KEY": "key4u-configured",
        "KEY4U_STT_ENDPOINT": "/audio/transcriptions",
        "GEMINI_API_KEY": "gemini-configured",
        "SHOPAIKEY_API_KEY": "",
        "SHOPAIKEY_AUDIO_TRANSCRIPTION_ENDPOINT": "",
        "deepgram_asr_adapter": deepgram,
        "deepgram_segments_from_response": lambda _payload: [],
        "save_provider_attempt": lambda key, value, _updated_by: (
            provider_attempts.append((key, dict(value)))
        ),
        "subdub_long_media": SimpleNamespace(
            is_no_speech_result=lambda _result, _transcript: True
        ),
        "subdub_two_speaker_asr_fallback": SimpleNamespace(
            run_two_speaker_fallback=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("exact-two fallback must stay isolated")
            )
        ),
        "openai_compatible_asr_transcribe": key4u,
    }
    asr = _load_asr_transcribe_audio_surface(namespace)

    result = asyncio.run(
        asr(
            b"audio",
            "audio/wav",
            require_diarization=True,
            allow_multi_speaker_key4u_fallback=True,
            allow_confirmed_product=True,
            media_duration_seconds=3,
        )
    )

    assert result["ok"] is True
    assert result["provider"] == "key4u_audio+gemini_multi_diarization"
    assert [item["speaker"] for item in result["segments"]] == [0, 1, 2]
    assert key4u_calls == [True]
    assert gemini_calls == [True]
    assert provider_attempts[-1][1]["route"] == "multi_speaker_fallback"


def test_multi_key4u_permanent_401_is_not_retried():
    calls = []

    async def key4u(*_args, **_kwargs):
        calls.append(True)
        return {
            "ok": False,
            "status": "FAIL_PROVIDER_ERROR",
            "http_status": 401,
            "text": "",
            "segments": [],
        }

    result = asyncio.run(
        fallback.run_multi_speaker_fallback(
            b"audio",
            "audio/mpeg",
            key4u_transcribe=key4u,
            key4u_api_key="configured",
            key4u_endpoint="/audio/transcriptions",
            gemini_api_key="configured",
            duration_seconds=10,
        )
    )

    assert result["ok"] is False
    assert result["key4u_attempt_count"] == 1
    assert result["key4u_retry_used"] is False
    assert calls == [True]


@pytest.mark.parametrize("duration_seconds", (0, 301))
def test_multi_fallback_rejects_unbounded_media_before_provider(
    duration_seconds,
):
    calls = []

    async def key4u(*_args, **_kwargs):
        calls.append(True)
        return {}

    result = asyncio.run(
        fallback.run_multi_speaker_fallback(
            b"audio",
            "audio/mpeg",
            key4u_transcribe=key4u,
            key4u_api_key="configured",
            key4u_endpoint="/audio/transcriptions",
            gemini_api_key="configured",
            duration_seconds=duration_seconds,
        )
    )

    assert result["detail"] == "multi_speaker_fallback_media_out_of_bounds"
    assert result["key4u_attempt_count"] == 0
    assert calls == []


def test_multi_fallback_busy_and_cancel_release_global_lock():
    calls = []

    async def key4u(*_args, **_kwargs):
        calls.append(True)
        raise asyncio.CancelledError()

    assert fallback._REDIARIZATION_LOCK.acquire(blocking=False)
    try:
        busy = asyncio.run(
            fallback.run_multi_speaker_fallback(
                b"audio",
                "audio/mpeg",
                key4u_transcribe=key4u,
                key4u_api_key="configured",
                key4u_endpoint="/audio/transcriptions",
                gemini_api_key="configured",
                duration_seconds=10,
            )
        )
    finally:
        fallback._REDIARIZATION_LOCK.release()
    assert busy["detail"] == "multi_speaker_fallback_busy"
    assert calls == []

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            fallback.run_multi_speaker_fallback(
                b"audio",
                "audio/mpeg",
                key4u_transcribe=key4u,
                key4u_api_key="configured",
                key4u_endpoint="/audio/transcriptions",
                gemini_api_key="configured",
                duration_seconds=10,
            )
        )
    assert fallback._REDIARIZATION_LOCK.acquire(blocking=False)
    fallback._REDIARIZATION_LOCK.release()


def test_multi_rediarization_missing_key_makes_zero_provider_calls(tmp_path):
    pcm_path = tmp_path / "source.pcm"
    pcm_path.write_bytes(b"\0" * 32_000)
    calls = []

    async def gemini(*_args, **_kwargs):
        calls.append("gemini")
        return {}

    result = asyncio.run(
        fallback.rediarize_underclustered_segments(
            _segments(2),
            pcm_path=str(pcm_path),
            sample_rate=16_000,
            channels=1,
            api_key="",
            provider_call_allowed=True,
            gemini_diarize=gemini,
        )
    )

    assert result["ok"] is False
    assert result["status"] == fallback.AUTO_CAST_UNAVAILABLE
    assert calls == []


def test_multi_rediarization_requires_final_product_confirmation(tmp_path):
    pcm_path = tmp_path / "source.pcm"
    pcm_path.write_bytes(b"\0" * (16_000 * 2 * 6))
    calls = []

    async def gemini(*_args, **_kwargs):
        calls.append("gemini")
        return {}

    result = asyncio.run(
        fallback.rediarize_underclustered_segments(
            _segments(1)[:3],
            pcm_path=str(pcm_path),
            sample_rate=16_000,
            channels=1,
            api_key="configured",
            provider_call_allowed=False,
            gemini_diarize=gemini,
        )
    )

    assert result["ok"] is False
    assert result["detail"] == "multi_rediarization_confirmation_required"
    assert calls == []


def test_single_label_primary_result_also_enters_multi_rediarization(tmp_path):
    pcm_path = tmp_path / "source.pcm"
    pcm_path.write_bytes(b"\0" * (16_000 * 2 * 6))
    calls = []

    async def gemini(*_args, **_kwargs):
        calls.append("gemini")
        return {
            "ok": True,
            "status": "PASS",
            "words": fallback.extract_gemini_multi_diarized_words(
                _gemini_payload()
            ),
        }

    result = asyncio.run(
        fallback.rediarize_underclustered_segments(
            _segments(1)[:3],
            pcm_path=str(pcm_path),
            sample_rate=16_000,
            channels=1,
            api_key="configured",
            provider_call_allowed=True,
            gemini_diarize=gemini,
        )
    )

    assert result["ok"] is True
    assert result["detected_speaker_count"] == 3
    assert calls == ["gemini"]


def test_multi_rediarization_uses_threaded_conversion_and_one_gemini_call(
    tmp_path,
    monkeypatch,
):
    pcm_path = tmp_path / "source.pcm"
    pcm_path.write_bytes(b"\0" * (44_100 * 2 * 2 * 3))
    calls = []
    threaded = []

    async def to_thread(function, *args, **kwargs):
        threaded.append(function.__name__)
        return function(*args, **kwargs)

    monkeypatch.setattr(fallback.asyncio, "to_thread", to_thread)

    async def gemini(audio_bytes, content_type, **_kwargs):
        calls.append((len(audio_bytes), audio_bytes[:4], content_type))
        return {
            "ok": True,
            "status": "PASS",
            "words": fallback.extract_gemini_multi_diarized_words(
                _gemini_payload()
            ),
            "speaker_ids": ["spk_1", "spk_2", "spk_3"],
        }

    result = asyncio.run(
        fallback.rediarize_underclustered_segments(
            _segments(2)[:3],
            pcm_path=str(pcm_path),
            sample_rate=44_100,
            channels=2,
            api_key="configured",
            provider_call_allowed=True,
            gemini_diarize=gemini,
        )
    )

    assert result["ok"] is True
    assert result["detected_speaker_count"] == 3
    assert result["provider_status"] == "PASS"
    assert result["provider_http_status"] == 0
    assert result["provider_word_count"] == 6
    assert result["provider_speaker_count"] == 3
    assert result["mapped_speaker_count"] == 3
    assert [item["speaker_id"] for item in result["segments"]] == [
        "chunk_00:speaker_0",
        "chunk_00:speaker_1",
        "chunk_00:speaker_2",
    ]
    assert len(calls) == 1
    assert calls[0] == (96_044, b"RIFF", "audio/wav")
    assert threaded == ["_pcm_as_mono_wav"]


def test_multi_rediarization_failure_preserves_exact_provider_status_and_counts(
    tmp_path,
):
    pcm_path = tmp_path / "source.pcm"
    pcm_path.write_bytes(b"\0" * (16_000 * 2 * 6))

    async def gemini(*_args, **_kwargs):
        return {
            "ok": False,
            "status": "FAIL_TIMEOUT",
            "words": [],
            "speaker_ids": [],
            "http_status": 504,
            "detail": "bounded-provider-detail",
        }

    result = asyncio.run(
        fallback.rediarize_underclustered_segments(
            _segments(2),
            pcm_path=str(pcm_path),
            sample_rate=16_000,
            channels=1,
            api_key="configured-test-key",
            provider_call_allowed=True,
            gemini_diarize=gemini,
        )
    )

    assert result["ok"] is False
    assert result["status"] == fallback.AUTO_CAST_UNAVAILABLE
    assert result["provider_status"] == "FAIL_TIMEOUT"
    assert result["provider_http_status"] == 504
    assert result["provider_word_count"] == 0
    assert result["provider_speaker_count"] == 0
    assert result["mapped_speaker_count"] == 0
    assert result["detail"] == "bounded-provider-detail"


def test_multi_rediarization_busy_fails_before_conversion_or_provider(tmp_path):
    pcm_path = tmp_path / "source.pcm"
    pcm_path.write_bytes(b"\0" * (16_000 * 2 * 6))
    calls = []

    async def gemini(*_args, **_kwargs):
        calls.append("gemini")
        return {}

    assert fallback._REDIARIZATION_LOCK.acquire(blocking=False)
    try:
        result = asyncio.run(
            fallback.rediarize_underclustered_segments(
                _segments(1)[:3],
                pcm_path=str(pcm_path),
                sample_rate=16_000,
                channels=1,
                api_key="configured",
                provider_call_allowed=True,
                gemini_diarize=gemini,
            )
        )
    finally:
        fallback._REDIARIZATION_LOCK.release()

    assert result["ok"] is False
    assert result["detail"] == "multi_rediarization_busy"
    assert calls == []


def test_multi_pcm_stream_rejects_oversized_sparse_file_before_read(tmp_path):
    pcm_path = tmp_path / "too-large.pcm"
    maximum = (
        fallback.MAX_REDIARIZATION_SECONDS * 44_100 * 2 * 2
    )
    with pcm_path.open("wb") as handle:
        handle.truncate(maximum + 4)

    assert fallback._pcm_as_mono_wav(
        str(pcm_path),
        sample_rate=44_100,
        channels=2,
    ) == b""


def test_underclustered_multi_adapter_ignores_stale_receipt_and_rediarizes_once(
    tmp_path,
    monkeypatch,
):
    prepared = _prepared(tmp_path)
    prepared["state"].update({
        "auto_exact_receipt": {"session_nonce": "stale-session"},
        "auto_exact_receipt_confirmed": True,
        "auto_exact_session_nonce": "stale-session",
    })
    stereo_pcm = tmp_path / "multi-stereo.pcm"
    stereo_pcm.write_bytes(b"\0" * 64)
    calls = {"extract": 0, "rediarize": 0}

    async def base_prepare(_state, *, require_auto_cast):
        assert require_auto_cast is True
        return prepared

    async def base_extract(_prepared, _state, **kwargs):
        calls["extract"] += 1
        assert kwargs == {
            "channels": exact_gender.PCM_CHANNELS,
            "sample_rate": exact_gender.PCM_SAMPLE_RATE,
            "sample_format": "s16le",
        }
        return str(stereo_pcm)

    async def rediarize(source_segments, **kwargs):
        calls["rediarize"] += 1
        assert kwargs["pcm_path"] == str(stereo_pcm)
        assert kwargs["provider_call_allowed"] is True
        mapped = []
        for index, segment in enumerate(source_segments):
            mapped.append(
                {
                    **segment,
                    "speaker": index % 3,
                    "speaker_id": f"chunk_00:speaker_{index % 3}",
                    "speaker_confidence": 0.95,
                }
            )
        return {
            "ok": True,
            "status": "PASS",
            "provider": "gemini_transcribe_multi_diarization",
            "segments": mapped,
            "detected_speaker_count": 3,
        }

    async def isolated(**kwargs):
        refined = await kwargs["prepare_subtitles"](
            kwargs["state"],
            require_auto_cast=True,
        )
        return {"ok": True, "status": "fixture", "prepared": refined}

    monkeypatch.setattr(
        auto_multi_speaker,
        "_run_isolated_multi_speaker_blackbox",
        isolated,
    )
    result = asyncio.run(
        auto_multi_speaker.run_auto_multi_speaker_blackbox(
            lane_mode="subtitle_plus_dub",
            extract_pcm=base_extract,
            prepare_subtitles=base_prepare,
            rediarize_underclustered=rediarize,
            state={
                "voice_kind": "auto_speaker_gender",
                "voice_selection_mode": "auto_speaker",
                "auto_speaker_lane": "multi",
                "subdub_final_confirmed": "1",
                "auto_exact_session_nonce": "fresh-session",
            },
        )
    )

    refined = result["prepared"]
    assert speaker_cast.ordered_auto_speaker_labels(
        refined["source_segments"]
    ) == [
        "chunk_00:speaker_0",
        "chunk_00:speaker_1",
        "chunk_00:speaker_2",
    ]
    assert [item["speaker_id"] for item in refined["output_segments"]] == [
        item["speaker_id"] for item in refined["source_segments"]
    ]
    assert refined["state"]["multi_diarization_provider"] == (
        "gemini_transcribe_multi_diarization"
    )
    assert calls == {"extract": 1, "rediarize": 1}


def test_underclustered_multi_genuine_resume_skips_rediarization(
    tmp_path,
    monkeypatch,
):
    prepared = _prepared(tmp_path)
    prepared["state"].update({
        "auto_exact_receipt": {"session_nonce": "active-session"},
        "auto_exact_receipt_confirmed": True,
        "auto_exact_session_nonce": "active-session",
        "auto_exact_resume": True,
    })
    calls = []

    async def base_prepare(_state, *, require_auto_cast):
        assert require_auto_cast is True
        return prepared

    async def rediarize(*_args, **_kwargs):
        calls.append(True)
        return {"ok": False}

    async def isolated(**kwargs):
        current = await kwargs["prepare_subtitles"](
            kwargs["state"],
            require_auto_cast=True,
        )
        return {"ok": True, "status": "fixture", "prepared": current}

    monkeypatch.setattr(
        auto_multi_speaker,
        "_run_isolated_multi_speaker_blackbox",
        isolated,
    )
    result = asyncio.run(
        auto_multi_speaker.run_auto_multi_speaker_blackbox(
            lane_mode="subtitle_plus_dub",
            extract_pcm=lambda *_args, **_kwargs: "unused-by-this-wrapper-test.pcm",
            prepare_subtitles=base_prepare,
            rediarize_underclustered=rediarize,
            state={
                "voice_kind": "auto_speaker_gender",
                "voice_selection_mode": "auto_speaker",
                "auto_speaker_lane": "multi",
                "subdub_final_confirmed": "1",
                "auto_exact_resume": True,
            },
        )
    )

    assert result["prepared"] is prepared
    # This focused wrapper test certifies only that a genuine resume does not
    # submit a new re-diarization provider call. The downstream classifier may
    # still load its cached/prepared PCM through the full preflight path.
    assert calls == []


def test_underclustered_multi_failure_preserves_provider_diagnostics(
    tmp_path,
    monkeypatch,
):
    prepared = _prepared(tmp_path)
    stereo_pcm = tmp_path / "multi-failure-stereo.pcm"
    stereo_pcm.write_bytes(b"\0" * 64)

    async def base_prepare(_state, *, require_auto_cast):
        assert require_auto_cast is True
        return prepared

    async def base_extract(_prepared, _state, **_kwargs):
        return str(stereo_pcm)

    async def rediarize(*_args, **_kwargs):
        return {
            "ok": False,
            "status": speaker_cast.AUTO_CAST_UNAVAILABLE,
            "provider": "gemini_transcribe_multi_diarization",
            "provider_status": "FAIL_TIMEOUT",
            "detail": "gemini_multi_transcribe_timeout",
            "provider_http_status": 0,
            "provider_word_count": 0,
            "provider_speaker_count": 0,
            "mapped_speaker_count": 0,
        }

    state = {
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "auto_speaker_lane": "multi",
        "subdub_final_confirmed": "1",
    }
    result = asyncio.run(
        auto_multi_speaker.run_auto_multi_speaker_blackbox(
            lane_mode="subtitle_plus_dub",
            run_lane_blackbox=lambda **_kwargs: {},
            runner=lambda **_kwargs: {},
            extract_pcm=base_extract,
            prepare_subtitles=base_prepare,
            rediarize_underclustered=rediarize,
            resolve_voice_id=lambda *_args, **_kwargs: "unused",
            synthesize_segments=lambda *_args, **_kwargs: {},
            post_prepare_gate=lambda *_args, **_kwargs: {"continue": True},
            validated_pools={
                "low": [f"low-{index}" for index in range(16)],
                "high": [f"high-{index}" for index in range(16)],
            },
            required_pool_capacity=16,
            state=state,
        )
    )

    expected = {
        "multi_diarization_attempted": True,
        "multi_diarization_provider": "gemini_transcribe_multi_diarization",
        "multi_diarization_status": "FAIL_TIMEOUT",
        "multi_diarization_detail": "gemini_multi_transcribe_timeout",
        "multi_diarization_http_status": 0,
        "multi_diarization_provider_word_count": 0,
        "multi_diarization_provider_speaker_count": 0,
        "multi_diarization_mapped_speaker_count": 0,
    }
    assert result["status"] == speaker_cast.AUTO_CAST_MANUAL_REQUIRED
    assert {key: result[key] for key in expected} == expected
    assert {key: result["state"][key] for key in expected} == expected


def test_multi_gender_classifier_supports_same_gender_and_mixed_groups(
    tmp_path,
    monkeypatch,
):
    pcm_path = tmp_path / "stereo.pcm"
    pcm_path.write_bytes(b"\0" * 64)
    ranges = {
        "chunk_00:speaker_0": [(0.0, 1.0), (1.0, 2.0)],
        "chunk_00:speaker_1": [(2.0, 3.0), (3.0, 4.0)],
        "chunk_00:speaker_2": [(4.0, 5.0), (5.0, 6.0), (6.0, 7.0)],
    }
    monkeypatch.setattr(
        exact_gender,
        "_validated_model_paths",
        lambda: (Path("uvr.onnx"), Path("panns.onnx")),
    )
    monkeypatch.setattr(
        exact_gender,
        "_infer_selected_cues",
        lambda *_args, **_kwargs: {
            "chunk_00:speaker_0": [
                {"start": 0.0, "end": 1.0, "male_score": 0.9, "female_score": 0.1},
                {"start": 1.0, "end": 2.0, "male_score": 0.8, "female_score": 0.2},
            ],
            "chunk_00:speaker_1": [
                {"start": 2.0, "end": 3.0, "male_score": 0.8, "female_score": 0.2},
                {"start": 3.0, "end": 4.0, "male_score": 0.9, "female_score": 0.1},
            ],
            "chunk_00:speaker_2": [
                {"start": 4.0, "end": 5.0, "male_score": 0.1, "female_score": 0.9},
                {"start": 5.0, "end": 6.0, "male_score": 0.2, "female_score": 0.8},
                {"start": 6.0, "end": 7.0, "male_score": 0.1, "female_score": 0.9},
            ],
        },
    )

    result = multi_gender.classify_multi_speaker_genders(
        str(pcm_path),
        ranges,
        deadline_monotonic=10**12,
        stop_requested=lambda: False,
    )

    assert [result[label]["voice_gender"] for label in ranges] == [
        "male",
        "male",
        "female",
    ]
    assert [result[label]["voice_register"] for label in ranges] == [
        "low",
        "low",
        "high",
    ]


def test_multi_gender_classifier_rejects_two_labels_without_inference(
    tmp_path,
    monkeypatch,
):
    pcm_path = tmp_path / "stereo.pcm"
    pcm_path.write_bytes(b"\0" * 64)
    called = []
    monkeypatch.setattr(
        exact_gender,
        "_infer_selected_cues",
        lambda *_args, **_kwargs: called.append(True),
    )

    with pytest.raises(speaker_cast.AutoCastManualRequired):
        multi_gender.classify_multi_speaker_genders(
            str(pcm_path),
            {
                "chunk_00:speaker_0": [(0.0, 1.0), (1.0, 2.0)],
                "chunk_00:speaker_1": [(2.0, 3.0), (3.0, 4.0)],
            },
            deadline_monotonic=10**12,
            stop_requested=lambda: False,
        )
    assert called == []


def test_multi_classifier_timeout_uses_bounded_worker_drain(
    tmp_path,
    monkeypatch,
):
    pcm_path = tmp_path / "stereo.pcm"
    pcm_path.write_bytes(b"\0" * 64)
    drains = []

    def classifier(*_args, stop_requested, **_kwargs):
        while not stop_requested():
            time.sleep(0.001)
        return {}

    async def bounded_drain(worker):
        drains.append(worker)
        return False

    monkeypatch.setattr(
        multi_gender,
        "CLASSIFIER_WALL_TIMEOUT_SECONDS",
        0.01,
    )
    monkeypatch.setattr(
        auto_multi_speaker.auto_speaker,
        "_drain_worker_bounded",
        bounded_drain,
    )

    with pytest.raises(speaker_cast.AutoCastManualRequired):
        asyncio.run(
            auto_multi_speaker._classify_multi_off_event_loop(
                pcm_path,
                {
                    "chunk_00:speaker_0": [(0.0, 1.0), (1.0, 2.0)],
                    "chunk_00:speaker_1": [(2.0, 3.0), (3.0, 4.0)],
                    "chunk_00:speaker_2": [(4.0, 5.0), (5.0, 6.0)],
                },
                classifier,
            )
        )
    assert len(drains) == 1


def test_exact_two_authority_files_remain_byte_locked():
    root = Path(__file__).resolve().parents[1]

    assert hashlib.sha256(
        (root / "services" / "subdub_speaker_cast.py").read_bytes()
    ).hexdigest() == "de93620f3f038b5759a53e696c5c85d3553fcee758686df56c70e6b11bac145b"
    assert hashlib.sha256(
        (root / "services" / "subdub_two_speaker_asr_fallback.py").read_bytes()
    ).hexdigest() == "94748def11c38d76952192a996fa42231d75b39d4d9ecd3407ff671d92e1177e"
