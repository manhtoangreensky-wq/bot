from __future__ import annotations

import asyncio
import copy
import hashlib
import math
from pathlib import Path

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


def acoustic_pipeline_words() -> list[dict]:
    return [
        {
            "index": index,
            "word": f"word{index}",
            "start": round(index * 0.4, 3),
            "end": round(index * 0.4 + 0.2, 3),
        }
        for index in range(30)
    ]


def acoustic_pipeline_segments() -> list[dict]:
    segments = []
    for index, speaker in enumerate((0, 1, 2)):
        start = float(index * 4)
        end = float((index + 1) * 4 - 0.2)
        segments.append(
            {
                "cue_id": f"acoustic-{index}",
                "index": index + 1,
                "start": start,
                "end": end,
                "text": " ".join(f"word{word}" for word in range(index * 10, (index + 1) * 10)),
                "speaker": speaker,
                "speaker_id": f"chunk_00:speaker_{speaker}",
                "speaker_confidence": 0.9,
                "chunk_index": 0,
            }
        )
    return segments


def acoustic_state_fields() -> dict:
    return {
        "multi_acoustic_backend": "local_wespeaker_resnet34_spectral",
        "multi_acoustic_model_sha256": (
            "9fea6516d7ad6bf0a76c7689f5a49b65d330fad6dde96c91bb4435ffbfe056a1"
        ),
        "multi_acoustic_algorithm_version": "wespeaker-resnet34-spectral-v1",
        "multi_acoustic_speaker_count": 3,
        "multi_acoustic_word_count": 30,
        "multi_acoustic_unit_count": 12,
        "multi_acoustic_embedding_window_count": 24,
        "multi_acoustic_cluster_sizes": [4, 4, 4],
        "multi_acoustic_stability_pass": True,
        "multi_acoustic_word_coverage_count": 30,
    }


def test_acoustic_failure_evidence_is_bounded_and_contains_no_raw_words():
    error = bot.subdub_speaker_cast.AutoCastManualRequired()
    error.__cause__ = ValueError("acoustic_cluster_unstable")
    words = acoustic_pipeline_words()

    evidence = bot.subdub_multi_acoustic_failure_evidence(
        error,
        words,
        duration_seconds=12.0,
    )

    assert evidence == {
        "multi_acoustic_failure_code": "acoustic_cluster_unstable",
        "multi_acoustic_failure_word_count": 30,
        "multi_acoustic_failure_duration_ms": 12_000,
    }
    serialized = repr(evidence)
    assert "word0" not in serialized
    assert "speaker" not in serialized


def test_exact_multi_persists_bounded_failure_evidence_before_reraising(
    monkeypatch,
    tmp_path,
):
    words = acoustic_pipeline_words()
    updates = []

    async def resolve(*_args, **_kwargs):
        return {
            "source_kind": "asr",
            "subtitle": "1\n00:00:00,000 --> 00:00:12,000\nsource\n",
            "script": "source",
            "asr_provider": "deepgram",
            "segments": [{"index": 1, "start": 0.0, "end": 12.0, "text": "source"}],
            "word_timeline": words,
            "duration_seconds": 12.0,
        }

    async def extract(*_args, **_kwargs):
        path = tmp_path / "acoustic.pcm"
        path.write_bytes(b"\x01\x00" * 8_000)
        return str(path)

    async def fail(*_args, **_kwargs):
        error = bot.subdub_speaker_cast.AutoCastManualRequired()
        error.__cause__ = ValueError("acoustic_cluster_unstable")
        raise error

    monkeypatch.setattr(bot, "video_dubbing_resolve_source_script", resolve)
    monkeypatch.setattr(bot, "_extract_subdub_auto_pcm", extract)
    monkeypatch.setattr(bot.auto_multi_speaker, "run_local_acoustic_diarization_off_event_loop", fail)
    monkeypatch.setattr(bot, "set_video_dubbing_artifact", lambda *_args: "source-ref")
    pending = {
        "_pipeline_job_key": "exact-job-key",
        "_pipeline_workspace": str(tmp_path),
    }

    def preserve_pending(_uid, step, **fields):
        pending.update(fields)
        pending["step"] = step
        return dict(pending)

    monkeypatch.setattr(bot, "set_video_dubbing_pending", preserve_pending)
    monkeypatch.setattr(bot, "update_subtitle_dub_pipeline_job", lambda key, **fields: updates.append((key, fields)) or fields)

    with pytest.raises(bot.subdub_speaker_cast.AutoCastManualRequired):
        asyncio.run(
            bot.video_dubbing_prepare_subtitles(
                None,
                {
                    "step": "processing",
                    "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
                    "source_file_id": "fixture",
                    "source_media_type": "video",
                    "source_mime_type": "video/mp4",
                    "voice_kind": "auto_speaker_gender",
                    "voice_selection_mode": "auto_speaker",
                    "auto_speaker_lane": "multi",
                    "_pipeline_job_key": "exact-job-key",
                    "_pipeline_workspace": str(tmp_path),
                    "_pipeline_source_bytes_override": b"source",
                    "_pipeline_source_content_type_override": "video/mp4",
                },
                7,
                allow_confirmed_product=True,
                require_auto_cast=True,
            )
        )

    assert updates == [("exact-job-key", {
        "multi_acoustic_failure_code": "acoustic_cluster_unstable",
        "multi_acoustic_failure_word_count": 30,
        "multi_acoustic_failure_duration_ms": 12_000,
    })]


def test_pending_state_preserves_bounded_acoustic_field_types(monkeypatch):
    monkeypatch.setattr(bot, "USER_PENDING", {})

    state = bot.set_video_dubbing_pending(
        7126457028,
        "processing",
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        voice_kind="auto_speaker_gender",
        voice_selection_mode="auto_speaker",
        auto_speaker_lane="multi",
        **acoustic_state_fields(),
    )

    for field, expected in acoustic_state_fields().items():
        assert state[field] == expected
        assert type(state[field]) is type(expected)


@pytest.mark.parametrize(
    ("field", "invalid"),
    (
        ("multi_acoustic_speaker_count", 9),
        ("multi_acoustic_word_count", -1),
        ("multi_acoustic_unit_count", 1_001),
        ("multi_acoustic_embedding_window_count", 7),
        ("multi_acoustic_cluster_sizes", [1, 2, 3]),
        ("multi_acoustic_stability_pass", "true"),
    ),
)
def test_pending_state_rejects_invalid_acoustic_field_values(
    monkeypatch,
    field,
    invalid,
):
    monkeypatch.setattr(bot, "USER_PENDING", {})
    fields = acoustic_state_fields()
    fields[field] = invalid

    state = bot.set_video_dubbing_pending(
        7126457028,
        "processing",
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        **fields,
    )

    assert field not in state


def test_exact_multi_prepare_runs_local_acoustics_before_translation(
    monkeypatch,
    tmp_path,
):
    source_bytes = b"exact-multi-source"
    source_srt = "1\n00:00:00,000 --> 00:00:12,000\nsource words\n"
    words = acoustic_pipeline_words()
    acoustic_segments = acoustic_pipeline_segments()
    calls = []
    artifacts = []
    pending_state = {
        "step": "processing",
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "source_file_id": "fixture",
        "source_media_type": "video",
        "source_mime_type": "video/mp4",
        "source_duration": 12,
        "target_language": "English",
        "translate_requested": "1",
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "auto_speaker_lane": "multi",
        "_pipeline_workspace": str(tmp_path),
        "_pipeline_source_bytes_override": source_bytes,
        "_pipeline_source_content_type_override": "video/mp4",
    }

    async def resolve(
        *_args,
        require_auto_multi_word_timeline=False,
        require_diarization=False,
        **kwargs,
    ):
        calls.append(
            (
                "resolve",
                {
                    **dict(kwargs),
                    "require_auto_multi_word_timeline": (
                        require_auto_multi_word_timeline
                    ),
                    **(
                        {"require_diarization": True}
                        if require_diarization
                        else {}
                    ),
                },
            )
        )
        return {
            "source_kind": "asr",
            "subtitle": source_srt,
            "script": "source words",
            "asr_provider": "deepgram",
            "segments": [{"index": 1, "start": 0.0, "end": 12.0, "text": "source words"}],
            "word_timeline": list(words),
            "detected_language": "en",
            "duration_seconds": 12,
        }

    async def extract_pcm(prepared, received_state, **kwargs):
        calls.append(("extract", dict(kwargs), list(prepared["source_segments"])))
        assert received_state["auto_speaker_lane"] == "multi"
        path = tmp_path / "acoustic.pcm"
        path.write_bytes(b"\x01\x00" * 8_000)
        return str(path)

    async def acoustic(pcm_path, word_timeline, *, duration_seconds):
        calls.append(("acoustic", list(word_timeline), duration_seconds, str(pcm_path)))
        Path(pcm_path).unlink(missing_ok=True)
        return {
            "ok": True,
            "status": "PASS",
            "provider": "local_wespeaker_resnet34_spectral",
            "segments": [dict(item) for item in acoustic_segments],
            "detected_speaker_count": 3,
            "model_sha256": (
                "9fea6516d7ad6bf0a76c7689f5a49b65d330fad6dde96c91bb4435ffbfe056a1"
            ),
            "algorithm_version": "wespeaker-resnet34-spectral-v1",
            "word_count": 30,
            "unit_count": 12,
            "embedding_window_count": 24,
            "cluster_sizes": [4, 4, 4],
            "stability_pass": True,
            "word_coverage_count": 30,
        }

    async def translate(segments, target_language, **_kwargs):
        calls.append(("translate", [dict(item) for item in segments], target_language))
        translated = [{**item, "text": f"English {item['text']}"} for item in segments]
        return {
            "segments": translated,
            "provider": "fixture",
            "translation_missing_count": 0,
            "srt": bot.video_dubbing_srt_from_segments(translated),
        }

    def pending(_user_id, step, **fields):
        pending_state.update(fields)
        pending_state["step"] = step
        return dict(pending_state)

    def artifact(_user_id, kind, value):
        reference = f"artifact-ref-{len(artifacts) + 1}"
        artifacts.append((reference, kind, value))
        return reference

    monkeypatch.setattr(bot, "video_dubbing_resolve_source_script", resolve)
    monkeypatch.setattr(bot, "_extract_subdub_auto_pcm", extract_pcm)
    monkeypatch.setattr(
        bot.auto_multi_speaker,
        "run_local_acoustic_diarization_off_event_loop",
        acoustic,
        raising=False,
    )
    monkeypatch.setattr(bot, "translate_subtitle_segments", translate)
    monkeypatch.setattr(bot, "set_video_dubbing_artifact", artifact)
    monkeypatch.setattr(bot, "set_video_dubbing_pending", pending)

    prepared = asyncio.run(
        bot.video_dubbing_prepare_subtitles(
            None,
            dict(pending_state),
            7126457028,
            allow_confirmed_product=True,
            require_auto_cast=True,
        )
    )

    resolve_call = calls[0]
    assert resolve_call[0] == "resolve"
    assert resolve_call[1]["require_auto_multi_word_timeline"] is True
    assert resolve_call[1].get("require_diarization") is None
    assert [item[0] for item in calls] == ["resolve", "extract", "acoustic", "translate"]
    assert calls[1][1] == {"channels": 1, "sample_rate": 16_000, "sample_format": "s16le"}
    translated_input = calls[3][1]
    assert [item["speaker_id"] for item in translated_input] == [
        "chunk_00:speaker_0",
        "chunk_00:speaker_1",
        "chunk_00:speaker_2",
    ]
    assert [(item["start"], item["end"]) for item in prepared["output_segments"]] == [
        (0.0, 3.8),
        (4.0, 7.8),
        (8.0, 11.8),
    ]
    assert prepared["state"]["multi_acoustic_speaker_count"] == 3
    assert prepared["state"]["multi_acoustic_word_coverage_count"] == 30
    assert prepared["state"]["multi_acoustic_cluster_sizes"] == [4, 4, 4]
    source_artifacts = [item for item in artifacts if item[1] == "source_subtitle"]
    assert len(source_artifacts) == 2
    assert source_artifacts[-1][2] == prepared["source_subtitle"]
    assert prepared["state"]["subtitle_ref"] == source_artifacts[-1][0]
    assert prepared["state"]["source_subtitle_ref"] == source_artifacts[-1][0]
    sidecar = bot.subdub_speaker_cast.load_sidecar(
        prepared["state"]["speaker_sidecar_path"],
        expected_sha256=prepared["state"]["speaker_sidecar_sha256"],
        workspace=str(tmp_path),
    )
    assert bot.subdub_speaker_cast.ordered_auto_speaker_labels(sidecar["cues"]) == [
        "chunk_00:speaker_0",
        "chunk_00:speaker_1",
        "chunk_00:speaker_2",
    ]
    assert sidecar["acoustic"] == {
        "algorithm_version": "wespeaker-resnet34-spectral-v1",
        "backend": "local_wespeaker_resnet34_spectral",
        "cluster_sizes": [4, 4, 4],
        "embedding_window_count": 24,
        "model_sha256": (
            "9fea6516d7ad6bf0a76c7689f5a49b65d330fad6dde96c91bb4435ffbfe056a1"
        ),
        "speaker_count": 3,
        "stability_pass": True,
        "unit_count": 12,
        "word_count": 30,
        "word_coverage_count": 30,
    }
    assert "embeddings" not in sidecar
    assert "pcm" not in sidecar
    assert hashlib.sha256(source_bytes).hexdigest() == sidecar["media_sha256"]


@pytest.mark.parametrize(
    "state_patch",
    (
        {},
        {"auto_speaker_lane": ""},
        {"voice_selection_mode": "manual", "auto_speaker_lane": "multi"},
    ),
)
def test_non_multi_prepare_never_requests_acoustic_word_timeline(
    monkeypatch,
    tmp_path,
    state_patch,
):
    source_srt = "1\n00:00:00,000 --> 00:00:01,000\nhello\n"
    captured = []

    async def resolve(*_args, **kwargs):
        captured.append(dict(kwargs))
        return {
            "source_kind": "asr",
            "subtitle": source_srt,
            "script": "hello",
            "asr_provider": "fixture",
            "segments": [{
                "index": 1,
                "start": 0.0,
                "end": 1.0,
                "text": "hello",
                "speaker": 0,
                "speaker_confidence": 0.9,
            }],
        }

    monkeypatch.setattr(bot, "video_dubbing_resolve_source_script", resolve)
    monkeypatch.setattr(bot, "set_video_dubbing_artifact", lambda *_args: "source-ref")
    monkeypatch.setattr(bot, "USER_PENDING", {})
    monkeypatch.setattr(bot, "subdub_mode_requests_translation", lambda *_args: False)
    base = {
        "step": "processing",
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "source_file_id": "fixture",
        "source_media_type": "video",
        "source_mime_type": "video/mp4",
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "_pipeline_workspace": str(tmp_path),
        "_pipeline_source_bytes_override": b"source",
        "_pipeline_source_content_type_override": "video/mp4",
        **state_patch,
    }
    require_auto = base.get("voice_selection_mode") == "auto_speaker"
    prepared = asyncio.run(
        bot.video_dubbing_prepare_subtitles(
            None,
            base,
            1,
            allow_confirmed_product=True,
            require_auto_cast=require_auto,
        )
    )

    assert "require_auto_multi_word_timeline" not in captured[0]
    assert not any(key.startswith("multi_acoustic_") for key in prepared["state"])


def test_exact_multi_legacy_cached_sidecar_forces_fresh_acoustic_authority(
    monkeypatch,
    tmp_path,
):
    old_srt = "1\n00:00:00,000 --> 00:00:01,000\nlegacy\n"
    old_segments = bot.subdub_canonical_auto_speaker_segments(
        [
            {
                "index": index + 1,
                "start": float(index),
                "end": float(index + 1),
                "text": f"legacy {index}",
                "speaker": index % 2,
                "speaker_confidence": 0.9,
            }
            for index in range(2)
        ],
        extraction_source="legacy",
    )
    source_bytes = b"legacy-source"
    sidecar = bot.subdub_speaker_cast.build_sidecar(
        old_segments,
        media_sha256=hashlib.sha256(source_bytes).hexdigest(),
        subtitle_sha256=bot.subdub_speaker_sidecar_subtitle_sha256(old_srt),
    )
    receipt = bot.subdub_speaker_cast.persist_sidecar(sidecar, workspace=str(tmp_path))
    calls = []

    async def resolve(
        *_args,
        require_auto_multi_word_timeline=False,
        require_diarization=False,
        **_kwargs,
    ):
        calls.append((require_auto_multi_word_timeline, require_diarization))
        raise bot.subdub_speaker_cast.AutoCastUnavailable()

    monkeypatch.setattr(bot, "get_video_dubbing_artifact", lambda *_args: old_srt)
    monkeypatch.setattr(bot, "video_dubbing_has_media", lambda *_args: True)
    monkeypatch.setattr(bot, "video_dubbing_resolve_source_script", resolve)
    state = {
        "step": "processing",
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "subtitle_ref": "legacy-ref",
        "source_file_id": "fixture",
        "source_media_type": "video",
        "source_mime_type": "video/mp4",
        "source_duration": 2,
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "auto_speaker_lane": "multi",
        "_pipeline_workspace": str(tmp_path),
        "_pipeline_source_bytes_override": source_bytes,
        "_pipeline_source_content_type_override": "video/mp4",
        "speaker_sidecar_path": receipt["path"],
        "speaker_sidecar_sha256": receipt["sha256"],
    }

    with pytest.raises(bot.subdub_speaker_cast.AutoCastUnavailable):
        asyncio.run(
            bot.video_dubbing_prepare_subtitles(
                None,
                state,
                7,
                allow_confirmed_product=True,
                require_auto_cast=True,
            )
        )

    assert calls == [(True, False)]


def test_exact_multi_cached_acoustic_state_without_sidecar_authority_forces_fresh_asr(
    monkeypatch,
    tmp_path,
):
    source_bytes = b"acoustic-cache-source"
    old_srt = "1\n00:00:00,000 --> 00:00:01,000\nlegacy\n"
    old_segments = bot.subdub_canonical_auto_speaker_segments(
        [
            {
                "index": index + 1,
                "start": float(index),
                "end": float(index + 1),
                "text": f"legacy {index}",
                "speaker": index,
                "speaker_confidence": 0.9,
            }
            for index in range(3)
        ],
        extraction_source="legacy",
    )
    sidecar = bot.subdub_speaker_cast.build_sidecar(
        old_segments,
        media_sha256=hashlib.sha256(source_bytes).hexdigest(),
        subtitle_sha256=bot.subdub_speaker_sidecar_subtitle_sha256(old_srt),
    )
    receipt = bot.subdub_speaker_cast.persist_sidecar(sidecar, workspace=str(tmp_path))
    calls = []

    async def resolve(
        *_args,
        require_auto_multi_word_timeline=False,
        **_kwargs,
    ):
        calls.append(require_auto_multi_word_timeline)
        raise bot.subdub_speaker_cast.AutoCastUnavailable()

    monkeypatch.setattr(bot, "get_video_dubbing_artifact", lambda *_args: old_srt)
    monkeypatch.setattr(bot, "video_dubbing_has_media", lambda *_args: True)
    monkeypatch.setattr(bot, "video_dubbing_resolve_source_script", resolve)
    state = {
        "step": "processing",
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "subtitle_ref": "legacy-ref",
        "source_file_id": "fixture",
        "source_media_type": "video",
        "source_mime_type": "video/mp4",
        "source_duration": 3,
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "auto_speaker_lane": "multi",
        "_pipeline_workspace": str(tmp_path),
        "_pipeline_source_bytes_override": source_bytes,
        "_pipeline_source_content_type_override": "video/mp4",
        "speaker_sidecar_path": receipt["path"],
        "speaker_sidecar_sha256": receipt["sha256"],
        **acoustic_state_fields(),
    }

    with pytest.raises(bot.subdub_speaker_cast.AutoCastUnavailable):
        asyncio.run(
            bot.video_dubbing_prepare_subtitles(
                None,
                state,
                7,
                allow_confirmed_product=True,
                require_auto_cast=True,
            )
        )

    assert calls == [True]


def test_exact_multi_matching_acoustic_sidecar_reuses_without_asr(
    monkeypatch,
    tmp_path,
):
    source_bytes = b"matching-acoustic-source"
    segments = acoustic_pipeline_segments()
    source_srt = bot.video_dubbing_srt_from_segments(segments)
    evidence = acoustic_state_fields()
    sidecar = bot.subdub_speaker_cast.build_sidecar(
        segments,
        media_sha256=hashlib.sha256(source_bytes).hexdigest(),
        subtitle_sha256=bot.subdub_speaker_sidecar_subtitle_sha256(source_srt),
    )
    sidecar["acoustic"] = bot.auto_multi_speaker.acoustic_sidecar_evidence(evidence)
    receipt = bot.subdub_speaker_cast.persist_sidecar(sidecar, workspace=str(tmp_path))

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("matching acoustic resume must not call ASR")

    monkeypatch.setattr(bot, "get_video_dubbing_artifact", lambda *_args: source_srt)
    monkeypatch.setattr(bot, "video_dubbing_has_media", lambda *_args: True)
    monkeypatch.setattr(bot, "video_dubbing_resolve_source_script", forbidden)
    monkeypatch.setattr(bot, "subdub_mode_requests_translation", lambda *_args: False)
    state = {
        "step": "processing",
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "subtitle_ref": "acoustic-ref",
        "source_subtitle_ref": "acoustic-ref",
        "source_file_id": "fixture",
        "source_media_type": "video",
        "source_mime_type": "video/mp4",
        "source_duration": 12,
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "auto_speaker_lane": "multi",
        "_pipeline_workspace": str(tmp_path),
        "_pipeline_source_bytes_override": source_bytes,
        "_pipeline_source_content_type_override": "video/mp4",
        "speaker_sidecar_path": receipt["path"],
        "speaker_sidecar_sha256": receipt["sha256"],
        **evidence,
    }

    prepared = asyncio.run(
        bot.video_dubbing_prepare_subtitles(
            None,
            state,
            7,
            allow_confirmed_product=True,
            require_auto_cast=True,
        )
    )

    assert [item["speaker_id"] for item in prepared["source_segments"]] == [
        "chunk_00:speaker_0",
        "chunk_00:speaker_1",
        "chunk_00:speaker_2",
    ]
    assert prepared["state"]["multi_acoustic_speaker_count"] == 3
    assert prepared["asr_provider"] == "cached_subtitle"
