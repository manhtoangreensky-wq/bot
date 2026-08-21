import asyncio
from array import array
import copy
import hashlib
import importlib
import inspect
import json
import math
import os
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import unicodedata

import pytest

import bot


DEEPGRAM_TWO_SPEAKERS = {
    "metadata": {"duration": 0.9},
    "results": {
        "channels": [
            {
                "detected_language": "en",
                "alternatives": [
                    {
                        "transcript": "hello there",
                        "confidence": 0.95,
                        "words": [
                            {
                                "word": "hello",
                                "start": 0.0,
                                "end": 0.4,
                                "speaker": 0,
                                "speaker_confidence": 0.91,
                            },
                            {
                                "word": "there",
                                "start": 0.5,
                                "end": 0.9,
                                "speaker": 1,
                                "speaker_confidence": 0.88,
                            },
                        ],
                    }
                ],
            }
        ]
    },
}


def _speaker_cast_module():
    return importlib.import_module("services.subdub_speaker_cast")


def _subtitle_sha256(value: str) -> str:
    normalized = unicodedata.normalize("NFC", str(value or ""))
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8", errors="strict")).hexdigest()


def _speaker_metadata(item: dict) -> dict:
    fields = (
        "cue_id",
        "speaker",
        "speaker_confidence",
        "speaker_id",
        "chunk_index",
        "voice_register",
        "tts_voice_id",
    )
    return {key: item.get(key) for key in fields}


def test_deepgram_speaker_fields_survive_and_split_on_change():
    words = bot.deepgram_word_items(DEEPGRAM_TWO_SPEAKERS)
    segments = bot.deepgram_segments_from_response(DEEPGRAM_TWO_SPEAKERS)

    assert [item["speaker"] for item in words] == [0, 1]
    assert all(type(item["speaker"]) is int for item in words)
    assert [item["speaker_confidence"] for item in words] == pytest.approx([0.91, 0.88])
    assert all(0.0 <= item["speaker_confidence"] <= 1.0 for item in words)
    assert [item["speaker"] for item in segments] == [0, 1]
    assert [item["speaker_confidence"] for item in segments] == pytest.approx([0.91, 0.88])

    out_of_range = copy.deepcopy(DEEPGRAM_TWO_SPEAKERS)
    raw_words = out_of_range["results"]["channels"][0]["alternatives"][0]["words"]
    raw_words[0]["speaker_confidence"] = 1.5
    raw_words[1]["speaker_confidence"] = -0.25
    assert [item["speaker_confidence"] for item in bot.deepgram_word_items(out_of_range)] == [1.0, 0.0]


def test_deepgram_nan_speaker_confidence_falls_back_to_zero():
    payload = copy.deepcopy(DEEPGRAM_TWO_SPEAKERS)
    payload["results"]["channels"][0]["alternatives"][0]["words"][0]["speaker_confidence"] = float("nan")

    words = bot.deepgram_word_items(payload)

    assert words[0]["speaker_confidence"] == 0.0


def test_auto_diarization_request_is_call_scoped():
    request_params_object = bot.AgentDeepgram.REQUEST_PARAMS
    before = copy.deepcopy(request_params_object)

    default_params = bot.subdub_deepgram_request_params()
    auto_params = bot.subdub_deepgram_request_params(require_diarization=True)

    assert default_params == before
    assert default_params is not request_params_object
    assert auto_params["diarize_model"] == "latest"
    assert auto_params["utterances"] == "true"
    assert "diarize" not in auto_params
    assert bot.AgentDeepgram.REQUEST_PARAMS is request_params_object
    assert bot.AgentDeepgram.REQUEST_PARAMS == before


def test_auto_diarization_without_deepgram_fails_before_provider(monkeypatch):
    calls = []

    async def forbidden_diagnostic(*_args, **_kwargs):
        calls.append("deepgram")
        raise AssertionError("provider must not be called without Deepgram capability")

    monkeypatch.setattr(bot, "ASR_PROVIDER", "key4u")
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "")
    monkeypatch.setattr(bot.AgentDeepgram, "diagnostic", forbidden_diagnostic)

    result = asyncio.run(
        bot.asr_transcribe_audio(
            b"audio",
            "audio/wav",
            require_diarization=True,
            allow_confirmed_product=True,
        )
    )

    assert result["ok"] is False
    assert result["status"] == "AUTO_CAST_UNAVAILABLE"
    assert calls == []


def test_auto_diarization_without_confirmation_makes_zero_provider_calls(monkeypatch):
    calls = {"provider": 0, "diagnostic": 0}

    async def forbidden_adapter(*_args, **_kwargs):
        calls["provider"] += 1
        raise AssertionError("unconfirmed automatic speaker mode must stop before the provider")

    async def forbidden_diagnostic(*_args, **_kwargs):
        calls["diagnostic"] += 1
        raise AssertionError("unconfirmed automatic speaker mode must stop before diagnostics")

    monkeypatch.setattr(bot, "ASR_PROVIDER", "deepgram")
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "deepgram-key")
    monkeypatch.setattr(bot, "deepgram_asr_adapter", forbidden_adapter)
    monkeypatch.setattr(bot.AgentDeepgram, "diagnostic", forbidden_diagnostic)

    result = asyncio.run(
        bot.asr_transcribe_audio(
            b"audio",
            "audio/wav",
            require_diarization=True,
            allow_confirmed_product=False,
        )
    )

    assert result["ok"] is False
    assert result["status"] == "AUTO_CAST_UNAVAILABLE"
    assert calls == {"provider": 0, "diagnostic": 0}


def test_auto_diarization_missing_speakers_stops_after_one_deepgram_call(monkeypatch):
    calls = []
    response_without_speakers = copy.deepcopy(DEEPGRAM_TWO_SPEAKERS)
    for word in response_without_speakers["results"]["channels"][0]["alternatives"][0]["words"]:
        word.pop("speaker", None)
        word.pop("speaker_confidence", None)

    async def fake_diagnostic(*_args, require_diarization=False, **_kwargs):
        calls.append(require_diarization)
        return {
            "status": "PASS",
            "http_status": 200,
            "transcript": "hello there",
            "transcript_json": response_without_speakers,
        }

    async def forbidden_openai_route(*_args, **_kwargs):
        raise AssertionError("automatic speaker mode must force the scoped Deepgram route")

    monkeypatch.setattr(bot, "ASR_PROVIDER", "key4u")
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "deepgram-key")
    monkeypatch.setattr(bot.AgentDeepgram, "diagnostic", fake_diagnostic)
    monkeypatch.setattr(bot, "openai_compatible_asr_transcribe", forbidden_openai_route)
    monkeypatch.setattr(bot, "save_provider_attempt", lambda *_args, **_kwargs: None)

    result = asyncio.run(
        bot.asr_transcribe_audio(
            b"audio",
            "audio/wav",
            require_diarization=True,
            allow_confirmed_product=True,
        )
    )

    assert result["ok"] is False
    assert result["status"] == "AUTO_CAST_UNAVAILABLE"
    assert result["segments"] == []
    assert calls == [True]


def test_transcribe_media_forwards_scoped_diarization_and_preserves_boundary(monkeypatch):
    forwarded = []

    async def fake_asr(*_args, require_diarization=False, **_kwargs):
        forwarded.append(require_diarization)
        return {
            "ok": False,
            "status": "AUTO_CAST_UNAVAILABLE",
            "provider": "deepgram",
            "text": "",
            "segments": [],
            "detail": "deepgram_speaker_labels_missing",
        }

    async def forbidden_legacy_transcriber(*_args, **_kwargs):
        raise AssertionError("scoped diarization must not use the legacy ASR override")

    monkeypatch.setattr(bot, "asr_transcribe_audio", fake_asr)
    monkeypatch.setattr(bot, "video_dubbing_transcribe_bytes", forbidden_legacy_transcriber)

    result = asyncio.run(
        bot.transcribe_media_to_segments(
            {
                "bytes": b"audio",
                "content_type": "audio/wav",
                "media_kind": "audio",
            },
            allow_confirmed_product=True,
            require_diarization=True,
        )
    )

    assert result["output_valid"] is False
    assert result["status"] == "AUTO_CAST_UNAVAILABLE"
    assert forwarded == [True]


def test_long_media_transcription_forwards_scoped_diarization(monkeypatch):
    forwarded = []

    async def fake_asr(*_args, require_diarization=False, **_kwargs):
        forwarded.append(require_diarization)
        return {
            "ok": True,
            "status": "PASS",
            "provider": "deepgram",
            "text": "hello",
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
            "language": "en",
            "duration_seconds": 1.0,
            "detail": "scoped_deepgram",
        }

    async def forbidden_legacy_transcriber(*_args, **_kwargs):
        raise AssertionError("scoped long-media diarization must not use the legacy ASR override")

    async def fake_long_media(*_args, transcribe_chunk, **_kwargs):
        chunk = await transcribe_chunk(b"chunk-audio", "audio/wav")
        return {
            **chunk,
            "chunk_count": 1,
            "chunk_strategy": "asr_audio_chunks",
            "global_timing_preserved": True,
            "skipped_chunk_count": 0,
            "skipped_chunk_indices": [],
            "speech_chunk_count": 1,
        }

    monkeypatch.setattr(
        bot,
        "subdub_long_video_chunk_plan",
        lambda *_args, **_kwargs: {
            "chunking_enabled": True,
            "chunk_metadata": [{"index": 1, "start": 0.0, "end": 1.0}],
            "chunk_count": 1,
        },
    )
    monkeypatch.setattr(bot.subdub_long_media, "transcribe_long_media_chunks", fake_long_media)
    monkeypatch.setattr(bot, "asr_transcribe_audio", fake_asr)
    monkeypatch.setattr(bot, "video_dubbing_transcribe_bytes", forbidden_legacy_transcriber)

    result = asyncio.run(
        bot.transcribe_media_to_segments(
            {
                "bytes": b"audio",
                "content_type": "audio/wav",
                "media_kind": "audio",
                "duration_seconds": 120,
            },
            duration_seconds=120,
            allow_confirmed_product=True,
            require_diarization=True,
        )
    )

    assert result["output_valid"] is True
    assert result["provider"] == "deepgram"
    assert forwarded == [True]


def test_sidecar_requires_media_subtitle_and_exact_timeline_identity():
    speaker_cast = _speaker_cast_module()
    cues = [
        {
            "cue_id": "cue-1",
            "start": 0.0,
            "end": 1.0,
            "speaker": 0,
            "speaker_id": "chunk_00:speaker_0",
            "speaker_confidence": float("nan"),
        },
        {
            "cue_id": "cue-2",
            "start": 1.0,
            "end": 2.0,
            "speaker": 1,
            "speaker_id": "chunk_00:speaker_1",
            "speaker_confidence": 1.8,
        },
    ]
    media_hash = "a" * 64
    subtitle_hash = "b" * 64

    sidecar = speaker_cast.build_sidecar(
        cues,
        media_sha256=media_hash,
        subtitle_sha256=subtitle_hash,
    )

    assert speaker_cast.normalized_speaker_key(3, 1) == "chunk_03:speaker_1"
    with pytest.raises(speaker_cast.AutoCastUnavailable, match="^AUTO_CAST_UNAVAILABLE$"):
        speaker_cast.normalized_speaker_key(-3, -1)
    assert sidecar["version"] == 1
    assert [item["speaker_confidence"] for item in sidecar["cues"]] == [0.0, 1.0]
    assert speaker_cast.sidecar_matches(
        sidecar,
        cues,
        media_sha256=media_hash,
        subtitle_sha256=subtitle_hash,
    )
    assert sidecar["timeline_signature"] == speaker_cast.cue_timeline_signature(cues)

    identity_mutations = [
        {**sidecar, "version": 2},
        {**sidecar, "media_sha256": "c" * 64},
        {**sidecar, "subtitle_sha256": "d" * 64},
        {**sidecar, "timeline_signature": "0" * 64},
        {**sidecar, "cues": list(sidecar["cues"][:-1])},
    ]
    for stale in identity_mutations:
        assert not speaker_cast.sidecar_matches(
            stale,
            cues,
            media_sha256=media_hash,
            subtitle_sha256=subtitle_hash,
        )
    assert not speaker_cast.sidecar_matches(
        sidecar,
        [{**cues[0], "end": 1.001}, cues[1]],
        media_sha256=media_hash,
        subtitle_sha256=subtitle_hash,
    )
    assert not speaker_cast.sidecar_matches(
        sidecar,
        cues,
        media_sha256="not-a-sha256",
        subtitle_sha256=subtitle_hash,
    )


def test_speaker_identity_caps_labels_and_canonical_key_length():
    speaker_cast = _speaker_cast_module()
    long_media = importlib.import_module("services.subdub_long_media")

    assert speaker_cast.normalized_speaker_key(3, 15) == "chunk_03:speaker_15"
    assert long_media._valid_speaker_value(15)
    assert not long_media._valid_speaker_value(16)
    with pytest.raises(speaker_cast.AutoCastUnavailable, match="^AUTO_CAST_UNAVAILABLE$"):
        speaker_cast.normalized_speaker_key(3, 16)
    with pytest.raises(speaker_cast.AutoCastUnavailable, match="^AUTO_CAST_UNAVAILABLE$"):
        speaker_cast.normalized_speaker_key(3, 10**1000)
    with pytest.raises(speaker_cast.AutoCastUnavailable, match="^AUTO_CAST_UNAVAILABLE$"):
        speaker_cast.normalized_speaker_key(10**200, 1)


def test_sidecar_enforces_chunk_scoped_speaker_identity():
    speaker_cast = _speaker_cast_module()
    cues = [
        {
            "cue_id": "cue-1",
            "start": 0.0,
            "end": 1.0,
            "text": "hello",
            "speaker": 1,
            "chunk_index": 3,
            "speaker_id": "chunk_03:speaker_1",
            "speaker_confidence": 0.9,
        }
    ]
    media_hash = "a" * 64
    subtitle_hash = "b" * 64

    sidecar = speaker_cast.build_sidecar(
        cues,
        media_sha256=media_hash,
        subtitle_sha256=subtitle_hash,
    )
    tampered = copy.deepcopy(sidecar)
    tampered["cues"][0]["speaker_id"] = "speaker_1"

    assert sidecar["cues"][0]["speaker_id"] == "chunk_03:speaker_1"
    assert speaker_cast.sidecar_matches(
        sidecar,
        cues,
        media_sha256=media_hash,
        subtitle_sha256=subtitle_hash,
    )
    assert not speaker_cast.sidecar_matches(
        tampered,
        cues,
        media_sha256=media_hash,
        subtitle_sha256=subtitle_hash,
    )
    with pytest.raises(speaker_cast.AutoCastUnavailable, match="^AUTO_CAST_UNAVAILABLE$"):
        speaker_cast.join_sidecar(tampered, cues)


def test_speaker_id_only_sidecar_requires_canonical_chunk_namespace():
    speaker_cast = _speaker_cast_module()
    invalid_cues = [
        {
            "cue_id": "cue-1",
            "start": 0.0,
            "end": 1.0,
            "text": "hello",
            "speaker_id": "speaker_1",
            "speaker_confidence": 0.9,
        }
    ]
    valid_cues = [
        {
            **invalid_cues[0],
            "speaker_id": "chunk_03:speaker_1",
        }
    ]
    media_hash = "a" * 64
    subtitle_hash = "b" * 64

    with pytest.raises(speaker_cast.AutoCastUnavailable, match="^AUTO_CAST_UNAVAILABLE$"):
        speaker_cast.build_sidecar(
            invalid_cues,
            media_sha256=media_hash,
            subtitle_sha256=subtitle_hash,
        )

    sidecar = speaker_cast.build_sidecar(
        valid_cues,
        media_sha256=media_hash,
        subtitle_sha256=subtitle_hash,
    )
    assert speaker_cast.sidecar_matches(
        sidecar,
        valid_cues,
        media_sha256=media_hash,
        subtitle_sha256=subtitle_hash,
    )

    sidecar["cues"][0]["speaker_id"] = "speaker_1"
    assert not speaker_cast.sidecar_matches(
        sidecar,
        valid_cues,
        media_sha256=media_hash,
        subtitle_sha256=subtitle_hash,
    )


@pytest.mark.parametrize(
    "identity",
    [
        {"chunk_index": 3, "speaker_id": "chunk_04:speaker_1"},
        {"speaker": 1, "speaker_id": "chunk_03:speaker_2"},
        {"chunk_index": -1, "speaker_id": "chunk_00:speaker_0"},
        {"speaker": -1, "speaker_id": "chunk_00:speaker_0"},
        {"chunk_index": "3", "speaker_id": "chunk_03:speaker_0"},
        {"speaker": 1.0, "speaker_id": "chunk_00:speaker_1"},
        {"chunk_index": False, "speaker_id": "chunk_00:speaker_0"},
        {"speaker": True, "speaker_id": "chunk_00:speaker_1"},
    ],
    ids=(
        "chunk-mismatch-without-speaker",
        "speaker-mismatch-without-chunk",
        "negative-chunk",
        "negative-speaker",
        "string-chunk",
        "float-speaker",
        "boolean-chunk",
        "boolean-speaker",
    ),
)
def test_sidecar_rejects_unproven_numeric_speaker_identity(identity):
    speaker_cast = _speaker_cast_module()
    cue = {
        "cue_id": "cue-1",
        "start": 0.0,
        "end": 1.0,
        "text": "hello",
        "speaker_confidence": 0.9,
        **identity,
    }

    with pytest.raises(speaker_cast.AutoCastUnavailable, match="^AUTO_CAST_UNAVAILABLE$"):
        speaker_cast.build_sidecar(
            [cue],
            media_sha256="a" * 64,
            subtitle_sha256="b" * 64,
        )


def test_stored_sidecar_rejects_chunk_mismatch_without_numeric_speaker():
    speaker_cast = _speaker_cast_module()
    cues = [
        {
            "cue_id": "cue-1",
            "start": 0.0,
            "end": 1.0,
            "text": "hello",
            "speaker_id": "chunk_04:speaker_1",
            "speaker_confidence": 0.9,
        }
    ]
    media_hash = "a" * 64
    subtitle_hash = "b" * 64
    sidecar = speaker_cast.build_sidecar(
        cues,
        media_sha256=media_hash,
        subtitle_sha256=subtitle_hash,
    )
    sidecar["cues"][0]["chunk_index"] = 3

    assert not speaker_cast.sidecar_matches(
        sidecar,
        cues,
        media_sha256=media_hash,
        subtitle_sha256=subtitle_hash,
    )
    with pytest.raises(speaker_cast.AutoCastUnavailable, match="^AUTO_CAST_UNAVAILABLE$"):
        speaker_cast.join_sidecar(sidecar, cues)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("cue_id", " cue-1 "),
        ("cue_id", 1),
        ("start_ms", True),
        ("start_ms", "0"),
        ("start_ms", 0.0),
        ("end_ms", True),
        ("end_ms", "1000"),
        ("end_ms", 1000.0),
        ("speaker_confidence", True),
        ("speaker_confidence", "0.9"),
        ("speaker_confidence", 1),
    ],
)
def test_stored_sidecar_requires_exact_json_identity_types(field, value):
    speaker_cast = _speaker_cast_module()
    sidecar = speaker_cast.build_sidecar(
        [
            {
                "cue_id": "cue-1",
                "start": 0.0,
                "end": 1.0,
                "text": "hello",
                "speaker_id": "chunk_03:speaker_1",
                "speaker_confidence": 0.9,
            }
        ],
        media_sha256="a" * 64,
        subtitle_sha256="b" * 64,
    )
    sidecar["cues"][0][field] = value

    with pytest.raises(speaker_cast.AutoCastUnavailable, match="^AUTO_CAST_UNAVAILABLE$"):
        speaker_cast._sidecar_rows(sidecar)


@pytest.mark.parametrize(
    "identity",
    [
        {"speaker": True},
        {"speaker": "1"},
        {"speaker": 1.0},
        {"speaker": -1},
        {"speaker": 1, "chunk_index": True},
        {"speaker": 1, "chunk_index": "3"},
        {"speaker": 1, "chunk_index": 3.0},
        {"speaker": 1, "chunk_index": -1},
    ],
)
def test_single_pass_auto_rejects_non_integer_numeric_speaker_identity(identity):
    with pytest.raises(bot.subdub_speaker_cast.AutoCastUnavailable, match="^AUTO_CAST_UNAVAILABLE$"):
        bot.subdub_canonical_auto_speaker_segments(
            [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "hello",
                    "speaker_confidence": 0.9,
                    **identity,
                }
            ],
            extraction_source="fixture",
        )


def test_single_pass_auto_accepts_canonical_speaker_id_only():
    segments = bot.subdub_canonical_auto_speaker_segments(
        [
            {
                "start": 0.0,
                "end": 1.0,
                "text": "hello",
                "speaker_id": "chunk_03:speaker_1",
                "speaker_confidence": 0.9,
            }
        ],
        extraction_source="fixture",
    )

    assert segments[0]["speaker"] == 1
    assert segments[0]["chunk_index"] == 3
    assert segments[0]["speaker_id"] == "chunk_03:speaker_1"


def test_sidecar_join_uses_only_cue_id_and_exact_timestamps():
    speaker_cast = _speaker_cast_module()
    source = [
        {
            "cue_id": "cue-1",
            "start": 0.0,
            "end": 1.0,
            "text": "one",
            "speaker": 0,
            "speaker_id": "chunk_00:speaker_0",
            "speaker_confidence": 0.91,
            "chunk_index": 0,
            "voice_register": "female",
            "tts_voice_id": "private-voice-a",
        },
        {
            "cue_id": "cue-2",
            "start": 1.0,
            "end": 2.0,
            "text": "two",
            "speaker": 1,
            "speaker_id": "chunk_00:speaker_1",
            "speaker_confidence": 0.88,
            "chunk_index": 0,
            "voice_register": "male",
            "tts_voice_id": "private-voice-b",
        },
    ]
    sidecar = speaker_cast.build_sidecar(
        source,
        media_sha256="a" * 64,
        subtitle_sha256="b" * 64,
    )
    cast_fields = {
        "speaker",
        "speaker_confidence",
        "speaker_id",
        "chunk_index",
        "voice_register",
        "tts_voice_id",
    }
    cues_without_metadata = [
        {key: value for key, value in source[1].items() if key not in cast_fields},
        {key: value for key, value in source[0].items() if key not in cast_fields},
    ]

    joined = speaker_cast.join_sidecar(sidecar, cues_without_metadata)

    assert [item["cue_id"] for item in joined] == ["cue-2", "cue-1"]
    assert _speaker_metadata(joined[0]) == _speaker_metadata(source[1])
    assert _speaker_metadata(joined[1]) == _speaker_metadata(source[0])
    with pytest.raises(speaker_cast.AutoCastUnavailable, match="^AUTO_CAST_UNAVAILABLE$"):
        speaker_cast.join_sidecar(
            sidecar,
            [{**cues_without_metadata[0], "start": 1.001}, cues_without_metadata[1]],
        )
    with pytest.raises(speaker_cast.AutoCastUnavailable, match="^AUTO_CAST_UNAVAILABLE$"):
        speaker_cast.join_sidecar(
            sidecar,
            [{**cues_without_metadata[0], "cue_id": "cue-missing"}, cues_without_metadata[1]],
        )


def test_cached_srt_without_matching_sidecar_raises_exact_auto_unavailable():
    speaker_cast = _speaker_cast_module()
    cues = [{"cue_id": "cue-1", "start": 0.0, "end": 1.0, "text": "hello"}]

    with pytest.raises(speaker_cast.AutoCastUnavailable, match="^AUTO_CAST_UNAVAILABLE$"):
        speaker_cast.require_matching_sidecar(
            {},
            cues,
            media_sha256="a" * 64,
            subtitle_sha256="b" * 64,
        )


def test_sidecar_lifecycle_is_bounded_hashed_and_workspace_scoped(tmp_path):
    speaker_cast = _speaker_cast_module()
    cues = [
        {
            "cue_id": "cue-1",
            "start": 0.0,
            "end": 1.0,
            "speaker": 0,
            "speaker_id": "chunk_00:speaker_0",
            "speaker_confidence": 0.9,
        }
    ]
    sidecar = speaker_cast.build_sidecar(
        cues,
        media_sha256="a" * 64,
        subtitle_sha256="b" * 64,
    )

    receipt = speaker_cast.persist_sidecar(sidecar, workspace=str(tmp_path))
    payload = json.loads((tmp_path / "speaker_cast.sidecar.json").read_text(encoding="utf-8"))

    assert set(receipt) == {"path", "sha256"}
    assert receipt["path"] == str(tmp_path / "speaker_cast.sidecar.json")
    assert len(receipt["sha256"]) == 64
    assert (tmp_path / "speaker_cast.sidecar.json").stat().st_size <= speaker_cast.MAX_SIDECAR_BYTES
    assert payload == sidecar
    assert speaker_cast.load_sidecar(
        receipt["path"],
        expected_sha256=receipt["sha256"],
        workspace=str(tmp_path),
    ) == sidecar
    with pytest.raises(speaker_cast.AutoCastUnavailable, match="^AUTO_CAST_UNAVAILABLE$"):
        speaker_cast.load_sidecar(
            receipt["path"],
            expected_sha256="0" * 64,
            workspace=str(tmp_path),
        )
    with pytest.raises(speaker_cast.AutoCastUnavailable, match="^AUTO_CAST_UNAVAILABLE$"):
        speaker_cast.load_sidecar(
            __file__,
            expected_sha256="0" * 64,
            workspace=str(tmp_path),
        )


def test_long_media_auto_namespaces_speakers_and_preserves_cue_metadata(tmp_path):
    _speaker_cast_module()
    ranges = [
        {
            "index": 3,
            "chunk_id": "chunk-three",
            "extract_start_ms": 0,
            "extract_end_ms": 10_000,
            "ownership_start_ms": 0,
            "ownership_end_ms": 10_000,
        },
        {
            "index": 4,
            "chunk_id": "chunk-four",
            "extract_start_ms": 10_000,
            "extract_end_ms": 20_000,
            "ownership_start_ms": 10_000,
            "ownership_end_ms": 20_000,
        },
    ]

    async def extract(_source, _content_type, start, _duration):
        return (b"chunk-three" if start == 0 else b"chunk-four"), "audio/mpeg", "fixture"

    async def transcribe(payload, _content_type):
        return {
            "ok": True,
            "status": "PASS",
            "provider": "fixture",
            "text": "three" if payload == b"chunk-three" else "four",
            "segments": [
                {
                    "index": 1,
                    "start": 0.5,
                    "end": 1.5,
                    "text": "three" if payload == b"chunk-three" else "four",
                    "speaker": 1,
                    "speaker_confidence": 0.9,
                    "voice_register": "unknown",
                    "tts_voice_id": "private-voice-id",
                }
            ],
        }

    checkpoint = tmp_path / "auto-checkpoint.json"
    result = asyncio.run(
        bot.subdub_long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            ranges,
            extract_chunk=extract,
            transcribe_chunk=transcribe,
            input_duration_seconds=20,
            source_hash="a" * 64,
            checkpoint_path=str(checkpoint),
            require_diarization=True,
        )
    )

    assert result["ok"] is True
    assert [item["speaker_id"] for item in result["segments"]] == [
        "chunk_03:speaker_1",
        "chunk_04:speaker_1",
    ]
    assert [item["chunk_index"] for item in result["segments"]] == [3, 4]
    assert all(item["speaker"] == 1 for item in result["segments"])
    assert all(item["speaker_confidence"] == pytest.approx(0.9) for item in result["segments"])
    assert all(str(item["cue_id"]).startswith("cue-") for item in result["segments"])
    assert len({item["cue_id"] for item in result["segments"]}) == 2
    assert all(item["voice_register"] == "unknown" for item in result["segments"])
    assert all(item["tts_voice_id"] == "private-voice-id" for item in result["segments"])
    checkpoint_payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert checkpoint_payload["metadata_contract"] == "subdub.diarized_cues.v1"
    stored = [
        segment
        for chunk in checkpoint_payload["chunks"].values()
        for segment in chunk["segments"]
    ]
    assert sorted(
        (_speaker_metadata(item) for item in stored),
        key=lambda item: item["chunk_index"],
    ) == sorted(
        (_speaker_metadata(item) for item in result["segments"]),
        key=lambda item: item["chunk_index"],
    )


def test_manual_long_media_offset_is_unchanged_when_metadata_is_absent():
    _speaker_cast_module()

    result = bot.subdub_long_media.offset_chunk_segments(
        [{"start": 0.5, "end": 1.5, "text": "hello"}],
        chunk_start=10.0,
        chunk_end=20.0,
    )

    assert result == [{"start": 10.5, "end": 11.5, "text": "hello"}]


def test_auto_long_checkpoint_refuses_non_diarized_receipt_then_reuses_auto(tmp_path):
    _speaker_cast_module()
    ranges = [
        {
            "index": 1,
            "chunk_id": "same-chunk",
            "extract_start_ms": 0,
            "extract_end_ms": 10_000,
            "ownership_start_ms": 0,
            "ownership_end_ms": 10_000,
        }
    ]
    submissions = []

    async def extract(*_args):
        return b"audio", "audio/mpeg", "fixture"

    async def transcribe_manual(*_args):
        submissions.append("manual")
        return {
            "ok": True,
            "status": "PASS",
            "text": "hello",
            "segments": [{"start": 0.0, "end": 1.0, "text": "hello"}],
        }

    async def transcribe_auto(*_args):
        submissions.append("auto")
        return {
            "ok": True,
            "status": "PASS",
            "text": "hello",
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "hello",
                    "speaker": 0,
                    "speaker_confidence": 0.9,
                }
            ],
        }

    checkpoint = tmp_path / "mode-guard.json"
    manual = asyncio.run(
        bot.subdub_long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            ranges,
            extract_chunk=extract,
            transcribe_chunk=transcribe_manual,
            source_hash="a" * 64,
            checkpoint_path=str(checkpoint),
        )
    )
    auto = asyncio.run(
        bot.subdub_long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            ranges,
            extract_chunk=extract,
            transcribe_chunk=transcribe_auto,
            source_hash="a" * 64,
            checkpoint_path=str(checkpoint),
            require_diarization=True,
        )
    )

    async def no_extract(*_args):
        raise AssertionError("matching diarized checkpoint must be reused")

    async def no_submit(*_args):
        raise AssertionError("matching diarized checkpoint must not submit ASR again")

    reused = asyncio.run(
        bot.subdub_long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            ranges,
            extract_chunk=no_extract,
            transcribe_chunk=no_submit,
            source_hash="a" * 64,
            checkpoint_path=str(checkpoint),
            require_diarization=True,
        )
    )

    assert manual["ok"] is True
    assert auto["ok"] is True
    assert auto["checkpoint_reused_count"] == 0
    assert auto["provider_submit_count"] == 1
    assert auto["segments"][0]["speaker_id"] == "chunk_01:speaker_0"
    assert reused["ok"] is True
    assert reused["checkpoint_reused_count"] == 1
    assert submissions == ["manual", "auto"]


@pytest.mark.parametrize("value", [True, "0", 0.0, -1, None])
def test_long_media_speaker_value_requires_exact_nonnegative_int(value):
    long_media = importlib.import_module("services.subdub_long_media")

    assert not long_media._valid_speaker_value(value)
    assert long_media._valid_speaker_value(0)
    assert long_media._valid_speaker_value(3)


def test_auto_long_checkpoint_rejects_unproven_chunk_speaker_identity(tmp_path):
    long_media = importlib.import_module("services.subdub_long_media")
    checkpoint = tmp_path / "malformed-auto-checkpoint.json"
    checkpoint.write_text(
        json.dumps(
            {
                "schema_version": "subdub.asr_chunks.v1",
                "source_hash": "a" * 64,
                "metadata_contract": "subdub.diarized_cues.v1",
                "chunks": {
                    "chunk-three": {
                        "status": "COMPLETED",
                        "segments": [
                            {
                                "cue_id": "cue-1",
                                "start": 0.5,
                                "end": 1.5,
                                "text": "hello",
                                "speaker": True,
                                "chunk_index": "3",
                                "speaker_id": "chunk_04:speaker_1",
                                "speaker_confidence": 0.9,
                            }
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    calls = {"extractor": 0, "provider": 0}

    async def no_extract(*_args):
        calls["extractor"] += 1
        raise AssertionError("malformed checkpoint must fail before extraction")

    async def no_submit(*_args):
        calls["provider"] += 1
        raise AssertionError("malformed checkpoint must fail before provider submission")

    result = asyncio.run(
        long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            [
                {
                    "index": 3,
                    "chunk_id": "chunk-three",
                    "extract_start_ms": 0,
                    "extract_end_ms": 10_000,
                    "ownership_start_ms": 0,
                    "ownership_end_ms": 10_000,
                }
            ],
            extract_chunk=no_extract,
            transcribe_chunk=no_submit,
            source_hash="a" * 64,
            checkpoint_path=str(checkpoint),
            require_diarization=True,
        )
    )

    assert result["ok"] is False
    assert result["status"] == "AUTO_CAST_UNAVAILABLE"
    assert result["provider_submit_count"] == 0
    assert calls == {"extractor": 0, "provider": 0}


def test_auto_long_checkpoint_rejects_completed_empty_segments(tmp_path):
    long_media = importlib.import_module("services.subdub_long_media")
    checkpoint = tmp_path / "empty-completed-auto-checkpoint.json"
    checkpoint.write_text(
        json.dumps(
            {
                "schema_version": "subdub.asr_chunks.v1",
                "source_hash": "a" * 64,
                "metadata_contract": "subdub.diarized_cues.v1",
                "chunks": {
                    "chunk-three": {
                        "status": "COMPLETED",
                        "transcript": "hello",
                        "segments": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    calls = {"extractor": 0, "provider": 0}

    async def no_extract(*_args):
        calls["extractor"] += 1
        raise AssertionError("empty completed checkpoint must fail before extraction")

    async def no_submit(*_args):
        calls["provider"] += 1
        raise AssertionError("empty completed checkpoint must fail before provider submission")

    result = asyncio.run(
        long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            [
                {
                    "index": 3,
                    "chunk_id": "chunk-three",
                    "extract_start_ms": 0,
                    "extract_end_ms": 10_000,
                    "ownership_start_ms": 0,
                    "ownership_end_ms": 10_000,
                }
            ],
            extract_chunk=no_extract,
            transcribe_chunk=no_submit,
            source_hash="a" * 64,
            checkpoint_path=str(checkpoint),
            require_diarization=True,
        )
    )

    assert result["ok"] is False
    assert result["status"] == "AUTO_CAST_UNAVAILABLE"
    assert result["provider_submit_count"] == 0
    assert calls == {"extractor": 0, "provider": 0}


def test_auto_long_checkpoint_accepts_canonical_speaker_id_only(tmp_path):
    long_media = importlib.import_module("services.subdub_long_media")
    checkpoint = tmp_path / "speaker-id-only-auto-checkpoint.json"
    checkpoint.write_text(
        json.dumps(
            {
                "schema_version": "subdub.asr_chunks.v1",
                "source_hash": "a" * 64,
                "metadata_contract": "subdub.diarized_cues.v1",
                "chunks": {
                    "chunk-three": {
                        "status": "COMPLETED",
                        "transcript": "hello",
                        "segments": [
                            {
                                "cue_id": "cue-1",
                                "start": 0.5,
                                "end": 1.5,
                                "text": "hello",
                                "speaker_id": "chunk_03:speaker_1",
                                "speaker_confidence": 0.9,
                            }
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    calls = {"extractor": 0, "provider": 0}

    async def no_extract(*_args):
        calls["extractor"] += 1
        raise AssertionError("canonical checkpoint must be reused without extraction")

    async def no_submit(*_args):
        calls["provider"] += 1
        raise AssertionError("canonical checkpoint must be reused without provider submission")

    result = asyncio.run(
        long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            [
                {
                    "index": 3,
                    "chunk_id": "chunk-three",
                    "extract_start_ms": 0,
                    "extract_end_ms": 10_000,
                    "ownership_start_ms": 0,
                    "ownership_end_ms": 10_000,
                }
            ],
            extract_chunk=no_extract,
            transcribe_chunk=no_submit,
            source_hash="a" * 64,
            checkpoint_path=str(checkpoint),
            require_diarization=True,
        )
    )

    assert result["ok"] is True
    assert result["status"] == "PASS"
    assert result["checkpoint_reused_count"] == 1
    assert result["provider_submit_count"] == 0
    assert result["segments"][0]["speaker_id"] == "chunk_03:speaker_1"
    assert calls == {"extractor": 0, "provider": 0}


def test_auto_long_checkpoint_rejects_non_mapping_segment_shape(tmp_path):
    long_media = importlib.import_module("services.subdub_long_media")
    checkpoint = tmp_path / "malformed-shape-auto-checkpoint.json"
    checkpoint.write_text(
        json.dumps(
            {
                "schema_version": "subdub.asr_chunks.v1",
                "source_hash": "a" * 64,
                "metadata_contract": "subdub.diarized_cues.v1",
                "chunks": {
                    "chunk-three": {
                        "status": "COMPLETED",
                        "transcript": "hello",
                        "segments": "not-a-segment",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    calls = {"extractor": 0, "provider": 0}

    async def no_extract(*_args):
        calls["extractor"] += 1
        raise AssertionError("malformed checkpoint must fail before extraction")

    async def no_submit(*_args):
        calls["provider"] += 1
        raise AssertionError("malformed checkpoint must fail before provider submission")

    result = asyncio.run(
        long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            [
                {
                    "index": 3,
                    "chunk_id": "chunk-three",
                    "extract_start_ms": 0,
                    "extract_end_ms": 10_000,
                    "ownership_start_ms": 0,
                    "ownership_end_ms": 10_000,
                }
            ],
            extract_chunk=no_extract,
            transcribe_chunk=no_submit,
            source_hash="a" * 64,
            checkpoint_path=str(checkpoint),
            require_diarization=True,
        )
    )

    assert result["ok"] is False
    assert result["status"] == "AUTO_CAST_UNAVAILABLE"
    assert result["provider_submit_count"] == 0
    assert calls == {"extractor": 0, "provider": 0}


@pytest.mark.parametrize(
    "case",
    [
        "malformed-json",
        "missing-schema",
        "wrong-schema",
        "wrong-source-hash",
        "missing-contract",
        "wrong-contract",
        "missing-chunks",
        "wrong-chunks-shape",
    ],
)
def test_existing_auto_checkpoint_requires_exact_root_receipt(case, tmp_path):
    long_media = importlib.import_module("services.subdub_long_media")
    checkpoint = tmp_path / f"invalid-root-{case}.json"
    payload = {
        "schema_version": "subdub.asr_chunks.v1",
        "source_hash": "a" * 64,
        "metadata_contract": "subdub.diarized_cues.v1",
        "chunks": {},
    }
    if case == "malformed-json":
        serialized = "{not-json"
    else:
        if case == "missing-schema":
            payload.pop("schema_version")
        elif case == "wrong-schema":
            payload["schema_version"] = "subdub.asr_chunks.v0"
        elif case == "wrong-source-hash":
            payload["source_hash"] = "b" * 64
        elif case == "missing-contract":
            payload.pop("metadata_contract")
        elif case == "wrong-contract":
            payload["metadata_contract"] = "subdub.default_cues.v1"
        elif case == "missing-chunks":
            payload.pop("chunks")
        elif case == "wrong-chunks-shape":
            payload["chunks"] = []
        serialized = json.dumps(payload)
    checkpoint.write_text(serialized, encoding="utf-8")
    calls = {"extractor": 0, "provider": 0}

    async def no_extract(*_args):
        calls["extractor"] += 1
        raise AssertionError("invalid Auto checkpoint must fail before extraction")

    async def no_submit(*_args):
        calls["provider"] += 1
        raise AssertionError("invalid Auto checkpoint must fail before provider submission")

    result = asyncio.run(
        long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            [
                {
                    "index": 3,
                    "chunk_id": "chunk-three",
                    "extract_start_ms": 0,
                    "extract_end_ms": 10_000,
                    "ownership_start_ms": 0,
                    "ownership_end_ms": 10_000,
                }
            ],
            extract_chunk=no_extract,
            transcribe_chunk=no_submit,
            source_hash="a" * 64,
            checkpoint_path=str(checkpoint),
            require_diarization=True,
        )
    )

    assert result["ok"] is False
    assert result["status"] == "AUTO_CAST_UNAVAILABLE"
    assert result["provider_submit_count"] == 0
    assert calls == {"extractor": 0, "provider": 0}


def test_auto_checkpoint_rejects_non_mapping_chunk_receipt(tmp_path):
    long_media = importlib.import_module("services.subdub_long_media")
    checkpoint = tmp_path / "malformed-chunk-receipt.json"
    checkpoint.write_text(
        json.dumps(
            {
                "schema_version": "subdub.asr_chunks.v1",
                "source_hash": "a" * 64,
                "metadata_contract": "subdub.diarized_cues.v1",
                "chunks": {"chunk-three": "not-a-chunk-receipt"},
            }
        ),
        encoding="utf-8",
    )
    calls = {"extractor": 0, "provider": 0}

    async def no_extract(*_args):
        calls["extractor"] += 1
        raise AssertionError("malformed chunk receipt must fail before extraction")

    async def no_submit(*_args):
        calls["provider"] += 1
        raise AssertionError("malformed chunk receipt must fail before provider submission")

    result = asyncio.run(
        long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            [
                {
                    "index": 3,
                    "chunk_id": "chunk-three",
                    "extract_start_ms": 0,
                    "extract_end_ms": 10_000,
                    "ownership_start_ms": 0,
                    "ownership_end_ms": 10_000,
                }
            ],
            extract_chunk=no_extract,
            transcribe_chunk=no_submit,
            source_hash="a" * 64,
            checkpoint_path=str(checkpoint),
            require_diarization=True,
        )
    )

    assert result["ok"] is False
    assert result["status"] == "AUTO_CAST_UNAVAILABLE"
    assert result["provider_submit_count"] == 0
    assert calls == {"extractor": 0, "provider": 0}


@pytest.mark.parametrize(
    "unused_chunk",
    [
        "not-a-chunk-receipt",
        {"status": "COMPLETED", "segments": "not-a-segment-list"},
        {"status": "COMPLETED", "segments": ["not-a-segment"]},
    ],
)
def test_auto_checkpoint_preflights_chunks_outside_current_ranges(unused_chunk, tmp_path):
    long_media = importlib.import_module("services.subdub_long_media")
    checkpoint = tmp_path / "malformed-unused-chunk.json"
    checkpoint.write_text(
        json.dumps(
            {
                "schema_version": "subdub.asr_chunks.v1",
                "source_hash": "a" * 64,
                "metadata_contract": "subdub.diarized_cues.v1",
                "chunks": {
                    "chunk-three": {
                        "status": "COMPLETED",
                        "transcript": "hello",
                        "segments": [
                            {
                                "cue_id": "cue-1",
                                "start": 0.5,
                                "end": 1.5,
                                "text": "hello",
                                "speaker_id": "chunk_03:speaker_1",
                                "speaker_confidence": 0.9,
                            }
                        ],
                    },
                    "unused-chunk": unused_chunk,
                },
            }
        ),
        encoding="utf-8",
    )
    calls = {"extractor": 0, "provider": 0}

    async def no_extract(*_args):
        calls["extractor"] += 1
        raise AssertionError("invalid checkpoint must fail before extraction")

    async def no_submit(*_args):
        calls["provider"] += 1
        raise AssertionError("invalid checkpoint must fail before provider submission")

    result = asyncio.run(
        long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            [
                {
                    "index": 3,
                    "chunk_id": "chunk-three",
                    "extract_start_ms": 0,
                    "extract_end_ms": 10_000,
                    "ownership_start_ms": 0,
                    "ownership_end_ms": 10_000,
                }
            ],
            extract_chunk=no_extract,
            transcribe_chunk=no_submit,
            source_hash="a" * 64,
            checkpoint_path=str(checkpoint),
            require_diarization=True,
        )
    )

    assert result["ok"] is False
    assert result["status"] == "AUTO_CAST_UNAVAILABLE"
    assert result["provider_submit_count"] == 0
    assert calls == {"extractor": 0, "provider": 0}


@pytest.mark.parametrize("segments", ["not-a-segment-list", ["not-a-segment"]])
def test_fresh_auto_rejects_malformed_provider_segment_shape(segments):
    long_media = importlib.import_module("services.subdub_long_media")
    calls = {"extractor": 0, "provider": 0}

    async def extract(*_args):
        calls["extractor"] += 1
        return b"audio", "audio/mpeg", "fixture"

    async def transcribe(*_args):
        calls["provider"] += 1
        return {
            "ok": True,
            "status": "PASS",
            "text": "hello",
            "segments": segments,
        }

    result = asyncio.run(
        long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            [
                {
                    "index": 3,
                    "chunk_id": "chunk-three",
                    "extract_start_ms": 0,
                    "extract_end_ms": 10_000,
                    "ownership_start_ms": 0,
                    "ownership_end_ms": 10_000,
                }
            ],
            extract_chunk=extract,
            transcribe_chunk=transcribe,
            source_hash="a" * 64,
            require_diarization=True,
        )
    )

    assert result["ok"] is False
    assert result["status"] == "AUTO_CAST_UNAVAILABLE"
    assert result["provider_submit_count"] == 1
    assert calls == {"extractor": 1, "provider": 1}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("cue_id", True),
        ("cue_id", " cue-1 "),
        ("start", "0.5"),
        ("start", True),
        ("start", float("inf")),
        ("start", float("nan")),
        ("start", 10**1000),
        ("start", -0.1),
        ("start", 2.0),
        ("end", "1.5"),
        ("end", True),
        ("end", float("inf")),
        ("end", float("nan")),
        ("end", 10**1000),
        ("end", 0.5),
        ("end", 0.4),
        ("speaker_confidence", "0.9"),
        ("speaker_confidence", True),
        ("speaker_confidence", 1),
        ("speaker_confidence", float("inf")),
        ("speaker_confidence", float("nan")),
        ("speaker_confidence", -0.1),
        ("speaker_confidence", 1.1),
    ],
)
def test_reused_auto_checkpoint_requires_exact_segment_receipt(field, value, tmp_path):
    long_media = importlib.import_module("services.subdub_long_media")
    checkpoint = tmp_path / "invalid-segment-receipt.json"
    segment = {
        "cue_id": "cue-1",
        "start": 0.5,
        "end": 1.5,
        "text": "hello",
        "speaker_id": "chunk_03:speaker_1",
        "speaker_confidence": 0.9,
    }
    segment[field] = value
    checkpoint.write_text(
        json.dumps(
            {
                "schema_version": "subdub.asr_chunks.v1",
                "source_hash": "a" * 64,
                "metadata_contract": "subdub.diarized_cues.v1",
                "chunks": {
                    "chunk-three": {
                        "status": "COMPLETED",
                        "transcript": "hello",
                        "segments": [segment],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    calls = {"extractor": 0, "provider": 0}

    async def no_extract(*_args):
        calls["extractor"] += 1
        raise AssertionError("invalid checkpoint must fail before extraction")

    async def no_submit(*_args):
        calls["provider"] += 1
        raise AssertionError("invalid checkpoint must fail before provider submission")

    result = asyncio.run(
        long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            [
                {
                    "index": 3,
                    "chunk_id": "chunk-three",
                    "extract_start_ms": 0,
                    "extract_end_ms": 10_000,
                    "ownership_start_ms": 0,
                    "ownership_end_ms": 10_000,
                }
            ],
            extract_chunk=no_extract,
            transcribe_chunk=no_submit,
            source_hash="a" * 64,
            checkpoint_path=str(checkpoint),
            require_diarization=True,
        )
    )

    assert result["ok"] is False
    assert result["status"] == "AUTO_CAST_UNAVAILABLE"
    assert result["provider_submit_count"] == 0
    assert calls == {"extractor": 0, "provider": 0}


def test_auto_source_hash_must_match_actual_source_bytes():
    long_media = importlib.import_module("services.subdub_long_media")
    calls = {"extractor": 0, "provider": 0}

    async def no_extract(*_args):
        calls["extractor"] += 1
        raise AssertionError("source hash mismatch must fail before extraction")

    async def no_submit(*_args):
        calls["provider"] += 1
        raise AssertionError("source hash mismatch must fail before provider submission")

    result = asyncio.run(
        long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            [
                {
                    "index": 3,
                    "chunk_id": "chunk-three",
                    "extract_start_ms": 0,
                    "extract_end_ms": 10_000,
                    "ownership_start_ms": 0,
                    "ownership_end_ms": 10_000,
                }
            ],
            extract_chunk=no_extract,
            transcribe_chunk=no_submit,
            source_hash="a" * 64,
            require_diarization=True,
        )
    )

    assert result["status"] == "AUTO_CAST_UNAVAILABLE"
    assert result["provider_submit_count"] == 0
    assert calls == {"extractor": 0, "provider": 0}


@pytest.mark.parametrize(
    "case",
    [
        "status-bool",
        "status-empty",
        "status-unknown",
        "stale-index",
        "stale-bounds",
        "stale-source",
        "missing-artifact",
        "invalid-artifact",
        "completed-missing-transcript",
        "completed-empty-segments",
        "no-speech-has-segments",
        "acceptance-unknown-has-segments",
        "missing-updated-at",
        "extra-off-range-chunk",
    ],
)
def test_existing_auto_chunk_receipt_requires_exact_status_contract(case, tmp_path):
    long_media = importlib.import_module("services.subdub_long_media")
    source_bytes = b"source"
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    segment = {
        "cue_id": "cue-1",
        "start": 0.5,
        "end": 1.5,
        "text": "hello",
        "speaker_id": "chunk_03:speaker_1",
        "speaker_confidence": 0.9,
    }
    receipt = {
        "index": 3,
        "chunk_id": "chunk-three",
        "extract_start_ms": 0,
        "extract_end_ms": 10_000,
        "ownership_start_ms": 0,
        "ownership_end_ms": 10_000,
        "source_hash": source_hash,
        "status": "COMPLETED",
        "artifact_hash": "c" * 64,
        "transcript": "hello",
        "segments": [segment],
        "provider": "fixture",
        "language": "en",
        "updated_at": 1.0,
    }
    chunks = {"chunk-three": receipt}
    if case == "status-bool":
        receipt["status"] = True
    elif case == "status-empty":
        receipt["status"] = ""
    elif case == "status-unknown":
        receipt["status"] = "UNKNOWN"
    elif case == "stale-index":
        receipt["index"] = 4
    elif case == "stale-bounds":
        receipt["ownership_end_ms"] = 9_000
    elif case == "stale-source":
        receipt["source_hash"] = "d" * 64
    elif case == "missing-artifact":
        receipt.pop("artifact_hash")
    elif case == "invalid-artifact":
        receipt["artifact_hash"] = "not-a-sha256"
    elif case == "completed-missing-transcript":
        receipt.pop("transcript")
    elif case == "completed-empty-segments":
        receipt["segments"] = []
    elif case == "no-speech-has-segments":
        receipt["status"] = "NO_SPEECH"
    elif case == "acceptance-unknown-has-segments":
        receipt["status"] = "ACCEPTANCE_UNKNOWN"
    elif case == "missing-updated-at":
        receipt.pop("updated_at")
    elif case == "extra-off-range-chunk":
        chunks["chunk-four"] = {
            **receipt,
            "index": 4,
            "chunk_id": "chunk-four",
        }
    checkpoint = tmp_path / f"invalid-chunk-{case}.json"
    checkpoint.write_text(
        json.dumps(
            {
                "schema_version": "subdub.asr_chunks.v1",
                "source_hash": source_hash,
                "metadata_contract": "subdub.diarized_cues.v1",
                "chunks": chunks,
            }
        ),
        encoding="utf-8",
    )
    calls = {"extractor": 0, "provider": 0}

    async def no_extract(*_args):
        calls["extractor"] += 1
        raise AssertionError("invalid receipt must fail before extraction")

    async def no_submit(*_args):
        calls["provider"] += 1
        raise AssertionError("invalid receipt must fail before provider submission")

    result = asyncio.run(
        long_media.transcribe_long_media_chunks(
            source_bytes,
            "video/mp4",
            [
                {
                    "index": 3,
                    "chunk_id": "chunk-three",
                    "extract_start_ms": 0,
                    "extract_end_ms": 10_000,
                    "ownership_start_ms": 0,
                    "ownership_end_ms": 10_000,
                }
            ],
            extract_chunk=no_extract,
            transcribe_chunk=no_submit,
            source_hash=source_hash,
            checkpoint_path=str(checkpoint),
            require_diarization=True,
        )
    )

    assert result["status"] == "AUTO_CAST_UNAVAILABLE"
    assert result["provider_submit_count"] == 0
    assert calls == {"extractor": 0, "provider": 0}


def test_qc_retime_and_translation_preserve_canonical_speaker_metadata(monkeypatch):
    _speaker_cast_module()
    source = {
        "index": 1,
        "start": 0.0,
        "end": 1.0,
        "text": "hello",
        "cue_id": "cue-1",
        "speaker": 0,
        "speaker_confidence": 0.91,
        "speaker_id": "chunk_00:speaker_0",
        "chunk_index": 0,
        "voice_register": "female",
        "tts_voice_id": "private-voice-id",
    }

    qc = bot.video_dubbing_qc_segments([source], preserve_timestamps=True)
    retimed = bot.subdub_retime_translated_segments_to_source(
        [source],
        [{"index": 1, "start": 9.0, "end": 10.0, "text": "cached translation"}],
    )

    async def translate(_text, _target_language, **_kwargs):
        return {"text": "translated", "provider": "fixture"}

    monkeypatch.setattr(bot, "translate_subtitle_text", translate)
    translated = asyncio.run(bot.translate_subtitle_segments([source], "vi"))["segments"]

    assert _speaker_metadata(qc[0]) == _speaker_metadata(source)
    assert _speaker_metadata(retimed[0]) == _speaker_metadata(source)
    assert _speaker_metadata(translated[0]) == _speaker_metadata(source)
    assert retimed[0]["text"] == "cached translation"
    assert (retimed[0]["start"], retimed[0]["end"]) == (0.0, 1.0)


@pytest.mark.parametrize(
    ("mode", "active_flow"),
    (
        ("dub", "dub_audio"),
        ("subtitle_plus_dub", "subtitle_plus_dub"),
    ),
)
def test_cached_auto_srt_without_sidecar_bootstraps_one_confirmed_diarized_asr(
    monkeypatch,
    tmp_path,
    mode,
    active_flow,
):
    calls = []
    source_srt = "1\n00:00:00,000 --> 00:00:01,000\nhello\n"

    async def diarized_asr(*_args, require_diarization=False, **kwargs):
        calls.append((require_diarization, kwargs.get("allow_confirmed_product")))
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
                "speaker_confidence": 0.95,
            }],
            "detected_language": "en",
        }

    monkeypatch.setattr(bot, "USER_PENDING", {})
    monkeypatch.setattr(bot, "get_video_dubbing_artifact", lambda *_args: source_srt)
    monkeypatch.setattr(bot, "set_video_dubbing_artifact", lambda *_args: "fresh-source")
    monkeypatch.setattr(bot, "video_dubbing_has_media", lambda *_args: True)
    monkeypatch.setattr(bot, "video_dubbing_resolve_source_script", diarized_asr)
    monkeypatch.setattr(bot, "subdub_mode_requests_translation", lambda *_args: False)
    state = {
        "pending_action": "video_dubbing",
        "step": "processing",
        "video_processing_mode": mode,
        "mode": mode,
        "active_flow": active_flow,
        "subtitle_ref": "cached-source",
        "source_file_id": "media-id",
        "source_media_type": "video",
        "source_mime_type": "video/mp4",
        "dub_source": "original_subtitle",
        "_pipeline_workspace": str(tmp_path),
        "_pipeline_source_bytes_override": b"media",
        "_pipeline_source_content_type_override": "video/mp4",
    }

    prepared = asyncio.run(
        bot.video_dubbing_prepare_subtitles(
            None,
            state,
            123,
            allow_confirmed_product=True,
            require_auto_cast=True,
        )
    )

    assert calls == [(True, True)]
    assert prepared["source_segments"][0]["speaker_id"] == "chunk_00:speaker_0"
    assert Path(prepared["state"]["speaker_sidecar_path"]).is_file()
    assert len(prepared["state"]["speaker_sidecar_sha256"]) == 64


def test_cached_auto_media_download_failure_never_asr_subtitle_bytes(monkeypatch):
    speaker_cast = _speaker_cast_module()
    source_srt = "1\n00:00:00,000 --> 00:00:01,000\nhello\n"
    calls = {"download": 0, "asr": 0}

    async def failed_media_download(*_args, **_kwargs):
        calls["download"] += 1
        raise RuntimeError("fixture media unavailable")

    async def forbidden_asr(*_args, **_kwargs):
        calls["asr"] += 1
        raise AssertionError("subtitle bytes must never be submitted as Auto media")

    monkeypatch.setattr(bot, "USER_PENDING", {})
    monkeypatch.setattr(bot, "get_video_dubbing_artifact", lambda *_args: source_srt)
    monkeypatch.setattr(bot, "set_video_dubbing_artifact", lambda *_args: "cached-source")
    monkeypatch.setattr(bot, "video_dubbing_has_media", lambda *_args: True)
    monkeypatch.setattr(bot, "video_dubbing_download_source", failed_media_download)
    monkeypatch.setattr(bot, "video_dubbing_resolve_source_script", forbidden_asr)
    monkeypatch.setattr(bot, "subdub_mode_requests_translation", lambda *_args: False)
    state = {
        "pending_action": "video_dubbing",
        "step": "processing",
        "video_processing_mode": "dub",
        "mode": "dub",
        "active_flow": "dub_audio",
        "subtitle_ref": "cached-source",
        "source_file_id": "media-id",
        "source_media_type": "video",
        "source_mime_type": "video/mp4",
        "target_language": "original",
    }

    with pytest.raises(speaker_cast.AutoCastUnavailable):
        asyncio.run(
            bot.video_dubbing_prepare_subtitles(
                None,
                dict(state),
                123,
                allow_confirmed_product=True,
                require_auto_cast=True,
            )
        )
    assert calls == {"download": 1, "asr": 0}

    manual = asyncio.run(
        bot.video_dubbing_prepare_subtitles(
            None,
            dict(state),
            123,
            allow_confirmed_product=True,
            require_auto_cast=False,
        )
    )
    assert calls == {"download": 2, "asr": 0}
    assert manual["source_bytes"] == source_srt.encode("utf-8")
    assert manual["source_subtitle"] == source_srt
    assert manual["asr_provider"] == "cached_subtitle"


def test_matching_cached_auto_sidecar_reuses_srt_without_asr(monkeypatch, tmp_path):
    speaker_cast = _speaker_cast_module()
    source_srt = "1\n00:00:00,000 --> 00:00:01,000\nhello\n"
    source_segments = bot.video_dubbing_segments_from_subtitle(source_srt)
    sidecar = speaker_cast.build_sidecar(
        [
            {
                **source_segments[0],
                "speaker": 0,
                "speaker_id": "chunk_00:speaker_0",
                "speaker_confidence": 0.9,
            }
        ],
        media_sha256=hashlib.sha256(b"media").hexdigest(),
        subtitle_sha256=_subtitle_sha256(source_srt),
    )
    receipt = speaker_cast.persist_sidecar(sidecar, workspace=str(tmp_path))

    async def forbidden_asr(*_args, **_kwargs):
        raise AssertionError("matching cached sidecar must not call ASR")

    monkeypatch.setattr(bot, "get_video_dubbing_artifact", lambda *_args: source_srt)
    monkeypatch.setattr(bot, "video_dubbing_has_media", lambda *_args: True)
    monkeypatch.setattr(bot, "video_dubbing_resolve_source_script", forbidden_asr)
    state = {
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "subtitle_ref": "cached-source",
        "source_file_id": "media-id",
        "source_media_type": "video",
        "source_mime_type": "video/mp4",
        "_pipeline_workspace": str(tmp_path),
        "_pipeline_source_bytes_override": b"media",
        "_pipeline_source_content_type_override": "video/mp4",
        "speaker_sidecar_path": receipt["path"],
        "speaker_sidecar_sha256": receipt["sha256"],
    }

    prepared = asyncio.run(
        bot.video_dubbing_prepare_subtitles(
            None,
            state,
            123,
            allow_confirmed_product=True,
            require_auto_cast=True,
        )
    )

    assert prepared["asr_provider"] == "cached_subtitle"
    assert prepared["source_segments"][0]["speaker_id"] == "chunk_00:speaker_0"
    assert prepared["source_segments"][0]["speaker_confidence"] == pytest.approx(0.9)


def test_fresh_auto_asr_persists_only_sidecar_path_and_hash_in_state(monkeypatch, tmp_path):
    speaker_cast = _speaker_cast_module()
    captured = {"require_diarization": [], "pending": {}}
    source_srt = "1\n00:00:00,000 --> 00:00:01,000\nhello\n"

    async def fake_resolve(
        *_args,
        require_diarization=False,
        **_kwargs,
    ):
        captured["require_diarization"].append(require_diarization)
        return {
            "source_kind": "asr",
            "subtitle": source_srt,
            "script": "hello",
            "asr_provider": "deepgram",
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

    def fake_pending(_user_id, step, **fields):
        captured["pending"] = {"step": step, **fields}
        return dict(captured["pending"])

    monkeypatch.setattr(bot, "video_dubbing_resolve_source_script", fake_resolve)
    monkeypatch.setattr(bot, "set_video_dubbing_artifact", lambda *_args: "source-ref")
    monkeypatch.setattr(bot, "set_video_dubbing_pending", fake_pending)
    state = {
        "step": "processing",
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "source_file_id": "media-id",
        "source_media_type": "video",
        "source_mime_type": "video/mp4",
        "_pipeline_workspace": str(tmp_path),
        "_pipeline_source_bytes_override": b"fresh-media",
        "_pipeline_source_content_type_override": "video/mp4",
    }

    prepared = asyncio.run(
        bot.video_dubbing_prepare_subtitles(
            None,
            state,
            123,
            allow_confirmed_product=True,
            require_auto_cast=True,
        )
    )

    assert captured["require_diarization"] == [True]
    assert captured["pending"]["speaker_sidecar_path"] == str(tmp_path / "speaker_cast.sidecar.json")
    assert len(captured["pending"]["speaker_sidecar_sha256"]) == 64
    assert "speaker_sidecar" not in captured["pending"]
    assert "speaker" not in captured["pending"]
    assert prepared["source_segments"][0]["cue_id"].startswith("cue-")
    assert prepared["source_segments"][0]["speaker_id"] == "chunk_00:speaker_0"
    assert speaker_cast.load_sidecar(
        captured["pending"]["speaker_sidecar_path"],
        expected_sha256=captured["pending"]["speaker_sidecar_sha256"],
        workspace=str(tmp_path),
    )["cues"][0]["speaker_id"] == "chunk_00:speaker_0"


def test_video_dubbing_state_accepts_sidecar_receipt_but_rejects_raw_metadata(monkeypatch):
    _speaker_cast_module()
    monkeypatch.setattr(bot, "USER_PENDING", {})

    state = bot.set_video_dubbing_pending(
        987,
        "processing",
        speaker_sidecar_path="C:/job/speaker_cast.sidecar.json",
        speaker_sidecar_sha256="a" * 64,
        speaker_sidecar={"cues": [{"speaker_id": "private"}]},
        speaker_pcm=[1, 2, 3],
        provider_voice_ids=["private-voice"],
    )

    assert state["speaker_sidecar_path"] == "C:/job/speaker_cast.sidecar.json"
    assert state["speaker_sidecar_sha256"] == "a" * 64
    assert "speaker_sidecar" not in state
    assert "speaker_pcm" not in state
    assert "provider_voice_ids" not in state


def _task4_pcm_bytes(kind, *, seconds=3.0):
    sample_rate = 16_000
    total = int(round(sample_rate * float(seconds)))
    samples = array("h")
    noise_state = 0x13579BDF
    for index in range(total):
        elapsed = index / sample_rate
        if isinstance(kind, (int, float)):
            value = 12_000.0 * math.sin(2.0 * math.pi * float(kind) * elapsed)
        elif kind == "silence":
            value = 0.0
        elif kind == "noise":
            noise_state = (1_103_515_245 * noise_state + 12_345) & 0x7FFFFFFF
            value = float(((noise_state >> 8) & 0xFFFF) - 32_768) * 0.45
        elif kind == "overlap":
            value = 7_000.0 * (
                math.sin(2.0 * math.pi * 120.0 * elapsed)
                + math.sin(2.0 * math.pi * 220.0 * elapsed)
            )
        elif kind == "unstable":
            frequency = 120.0 if (index // 8_000) % 2 == 0 else 220.0
            value = 12_000.0 * math.sin(2.0 * math.pi * frequency * elapsed)
        else:
            raise AssertionError(f"unknown PCM fixture: {kind}")
        samples.append(max(-32_768, min(32_767, int(round(value)))))
    if sys.byteorder != "little":
        samples.byteswap()
    return samples.tobytes()


def _task4_prepared(tmp_path, *, labels=("chunk_00:speaker_0",)):
    speaker_cast = _speaker_cast_module()
    cues = []
    if len(labels) == 1:
        timings = [(0, 3_000)]
    else:
        timings = [(index * 100, (index + 1) * 100) for index in range(len(labels))]
    for index, (speaker_id, (start_ms, end_ms)) in enumerate(zip(labels, timings)):
        chunk_index = int(speaker_id.split(":", 1)[0].split("_", 1)[1])
        speaker = int(speaker_id.rsplit("_", 1)[1])
        cues.append(
            {
                "text": f"cue {index}",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "speaker": speaker,
                "chunk_index": chunk_index,
                "speaker_id": speaker_id,
                "speaker_confidence": 0.99,
            }
        )
    source_bytes = b"canonical-auto-prepare-media"
    source_subtitle = "1\r\n00:00:00,000 --> 00:00:03,000\r\nCafe\u0301\r\n"
    media_sha256 = hashlib.sha256(source_bytes).hexdigest()
    subtitle_sha256 = _subtitle_sha256(source_subtitle)
    sidecar = speaker_cast.build_sidecar(
        cues,
        media_sha256=media_sha256,
        subtitle_sha256=subtitle_sha256,
    )
    receipt = speaker_cast.persist_sidecar(sidecar, workspace=str(tmp_path))
    return {
        "state": {
            "_pipeline_workspace": str(tmp_path),
            "speaker_sidecar_path": receipt["path"],
            "speaker_sidecar_sha256": receipt["sha256"],
        },
        "source_bytes": source_bytes,
        "source_subtitle": source_subtitle,
        "source_segments": cues,
    }


def test_exact_state_requires_only_the_central_exact_pair():
    auto_speaker = importlib.import_module("services.subdub_blackboxes.auto_speaker")
    exact = {
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
    }
    false_states = [
        None,
        {},
        {"voice_kind": "auto_speaker_gender"},
        {"voice_selection_mode": "auto_speaker"},
        {**exact, "voice_kind": "female"},
        {**exact, "voice_selection_mode": "manual"},
        {"voice_kind": True, "voice_selection_mode": "auto_speaker"},
        {"voice_kind": "auto_speaker_gender", "voice_selection_mode": True},
        {"auto_exact_receipt": {"stale": True}},
    ]

    assert auto_speaker.is_auto_speaker_state(exact)
    assert auto_speaker.is_auto_speaker_state({**exact, "unrelated": "kept"})
    assert all(not auto_speaker.is_auto_speaker_state(state) for state in false_states)


@pytest.mark.parametrize(
    ("frequency", "expected_register"),
    (
        (120.0, "low"),
        (155.0, "low"),
        (165.0, "high"),
        (170.0, "high"),
        (185.0, "high"),
        (220.0, "high"),
    ),
)
def test_register_classifier_reads_synthetic_pcm_tones(tmp_path, frequency, expected_register):
    speaker_cast = _speaker_cast_module()
    pcm_path = tmp_path / f"tone-{frequency}.pcm"
    pcm_path.write_bytes(_task4_pcm_bytes(frequency))

    result = speaker_cast.classify_speaker_registers(
        str(pcm_path),
        {"chunk_00:speaker_0": [(0.0, 3.0)]},
        deadline_monotonic=time.monotonic() + 10.0,
        stop_requested=lambda: False,
    )

    assert speaker_cast.pitch_register(154.9, confidence=0.75) == "low"
    assert speaker_cast.pitch_register(165.0, confidence=0.75) == "high"
    assert speaker_cast.pitch_register(185.0, confidence=0.75) == "high"
    assert speaker_cast.pitch_register(120.0, confidence=0.7499) == "unknown"
    assert result["chunk_00:speaker_0"]["voice_register"] == expected_register
    assert result["chunk_00:speaker_0"]["confidence"] >= 0.75


@pytest.mark.parametrize(
    ("kind", "seconds", "range_end"),
    (
        (160.0, 3.0, 3.0),
        ("noise", 3.0, 3.0),
        ("overlap", 3.0, 3.0),
        ("silence", 3.0, 3.0),
        (120.0, 0.25, 0.25),
        ("unstable", 3.0, 3.0),
    ),
)
def test_manual_required_for_ambiguous_or_insufficient_pcm(tmp_path, kind, seconds, range_end):
    speaker_cast = _speaker_cast_module()
    pcm_path = tmp_path / f"manual-{kind}.pcm"
    pcm_path.write_bytes(_task4_pcm_bytes(kind, seconds=seconds))

    with pytest.raises(
        speaker_cast.AutoCastManualRequired,
        match="^AUTO_CAST_MANUAL_REQUIRED$",
    ):
        speaker_cast.classify_speaker_registers(
            str(pcm_path),
            {"chunk_00:speaker_0": [(0.0, range_end)]},
            deadline_monotonic=time.monotonic() + 10.0,
            stop_requested=lambda: False,
        )


def test_manual_required_when_classifier_deadline_or_stop_is_reached(tmp_path):
    speaker_cast = _speaker_cast_module()
    pcm_path = tmp_path / "deadline.pcm"
    pcm_path.write_bytes(_task4_pcm_bytes(120.0, seconds=0.5))

    for deadline, stop_requested in (
        (time.monotonic(), lambda: False),
        (time.monotonic() + 10.0, lambda: True),
    ):
        with pytest.raises(
            speaker_cast.AutoCastManualRequired,
            match="^AUTO_CAST_MANUAL_REQUIRED$",
        ):
            speaker_cast.classify_speaker_registers(
                str(pcm_path),
                {"chunk_00:speaker_0": [(0.0, 0.5)]},
                deadline_monotonic=deadline,
                stop_requested=stop_requested,
            )


def test_pcm_streaming_and_resource_caps_are_enforced(monkeypatch):
    speaker_cast = _speaker_cast_module()
    window = _task4_pcm_bytes(120.0, seconds=0.5)
    read_sizes = []
    seek_offsets = []

    class ControlledReader:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def seek(self, offset):
            seek_offsets.append(offset)

        def read(self, size):
            read_sizes.append(size)
            return window

    monkeypatch.setattr(speaker_cast, "open", lambda *_args, **_kwargs: ControlledReader(), raising=False)

    result = speaker_cast.classify_speaker_registers(
        "fixture.pcm",
        {"chunk_00:speaker_0": [(0.0, 4.0)]},
        deadline_monotonic=time.monotonic() + 10.0,
        stop_requested=lambda: False,
    )
    item = result["chunk_00:speaker_0"]

    assert speaker_cast.PCM_SAMPLE_RATE == 16_000
    assert speaker_cast.PCM_WINDOW_SAMPLES == 8_000
    assert speaker_cast.PCM_WINDOW_BYTES == 16_000
    assert speaker_cast.MAX_AUTO_SPEAKER_LABELS == 16
    assert speaker_cast.MAX_SPEAKER_VOICED_SECONDS == 3.0
    assert speaker_cast.MAX_JOB_SAMPLE_SECONDS == 48.0
    assert speaker_cast.MAX_WORK_BUFFER_BYTES == 1_048_576
    assert speaker_cast.CLASSIFIER_WALL_TIMEOUT_SECONDS == 30.0
    assert read_sizes == [speaker_cast.PCM_WINDOW_BYTES] * 6
    assert len(seek_offsets) == 6
    assert item["sample_count"] == 48_000
    assert item["voiced_seconds"] == 3.0
    assert set(item) == {
        "speaker_id",
        "voice_register",
        "confidence",
        "voiced_seconds",
        "sample_count",
        "reason",
    }
    assert not any(key in item for key in ("pcm", "samples", "embedding", "fft", "autocorrelation"))
    json.dumps(result, allow_nan=False)


def test_speaker_limit_fails_before_pcm_reader(monkeypatch):
    speaker_cast = _speaker_cast_module()
    sixteen = [
        {"speaker_id": f"chunk_{index:02d}:speaker_0"}
        for index in range(16)
    ]
    seventeen = sixteen + [{"speaker_id": "chunk_16:speaker_0"}]
    opened = []
    monkeypatch.setattr(
        speaker_cast,
        "open",
        lambda *_args, **_kwargs: opened.append(True),
        raising=False,
    )

    assert speaker_cast.ordered_auto_speaker_labels(sixteen) == [
        item["speaker_id"] for item in sixteen
    ]
    with pytest.raises(speaker_cast.AutoCastManualRequired, match="^AUTO_CAST_MANUAL_REQUIRED$"):
        speaker_cast.ordered_auto_speaker_labels(seventeen)
    with pytest.raises(speaker_cast.AutoCastManualRequired, match="^AUTO_CAST_MANUAL_REQUIRED$"):
        speaker_cast.classify_speaker_registers(
            "must-not-open.pcm",
            {item["speaker_id"]: [(0.0, 0.5)] for item in seventeen},
            deadline_monotonic=time.monotonic() + 10.0,
            stop_requested=lambda: False,
        )
    assert opened == []


def test_preflight_gate_pause_is_returned_before_pcm_extraction(tmp_path, monkeypatch):
    auto_speaker = importlib.import_module("services.subdub_blackboxes.auto_speaker")
    speaker_cast = _speaker_cast_module()
    state = {
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "mode": "dub_only",
    }
    prepared = _task4_prepared(tmp_path)
    pause = {"ok": False, "status": "AUTO_EXACT_CONFIRMATION_REQUIRED", "receipt": {"v": 1}}
    calls = {"prepare": [], "gate": [], "extract": 0, "classify": 0}

    async def prepare_subtitles(received_state, *, require_auto_cast):
        calls["prepare"].append((received_state, require_auto_cast))
        return prepared

    async def post_prepare_gate(received_prepared, received_state):
        calls["gate"].append((received_prepared, received_state))
        return pause

    async def extract_pcm(*_args, **_kwargs):
        calls["extract"] += 1
        raise AssertionError("gate pause must precede PCM extraction")

    def classify(*_args, **_kwargs):
        calls["classify"] += 1
        raise AssertionError("gate pause must precede classification")

    monkeypatch.setattr(speaker_cast, "classify_speaker_registers", classify)

    result = asyncio.run(
        auto_speaker.run_auto_speaker_preflight(
            state,
            prepare_subtitles=prepare_subtitles,
            post_prepare_gate=post_prepare_gate,
            extract_pcm=extract_pcm,
        )
    )

    assert result is pause
    assert calls == {
        "prepare": [(state, True)],
        "gate": [(prepared, state)],
        "extract": 0,
        "classify": 0,
    }


def test_speaker_limit_preflight_gate_fails_before_extraction(tmp_path, monkeypatch):
    auto_speaker = importlib.import_module("services.subdub_blackboxes.auto_speaker")
    speaker_cast = _speaker_cast_module()
    labels = tuple(f"chunk_{index:02d}:speaker_0" for index in range(17))
    prepared = _task4_prepared(tmp_path, labels=labels)
    state = {
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "mode": "subtitle_plus_dub",
    }
    calls = {"extract": 0, "classify": 0}

    async def prepare_subtitles(_state, *, require_auto_cast):
        assert require_auto_cast is True
        return prepared

    async def post_prepare_gate(_prepared, _state):
        return {"continue": True}

    async def extract_pcm(*_args, **_kwargs):
        calls["extract"] += 1
        return str(tmp_path / "never.pcm")

    def classify(*_args, **_kwargs):
        calls["classify"] += 1
        raise AssertionError("17th label must fail before classifier")

    monkeypatch.setattr(speaker_cast, "classify_speaker_registers", classify)
    result = asyncio.run(
        auto_speaker.run_auto_speaker_preflight(
            state,
            prepare_subtitles=prepare_subtitles,
            post_prepare_gate=post_prepare_gate,
            extract_pcm=extract_pcm,
        )
    )

    assert result["status"] == "AUTO_CAST_MANUAL_REQUIRED"
    assert result["reason"] == "AUTO_CAST_MANUAL_REQUIRED"
    assert calls == {"extract": 0, "classify": 0}


def test_preflight_gate_consumes_canonical_prepare_receipt_shape(tmp_path, monkeypatch):
    auto_speaker = importlib.import_module("services.subdub_blackboxes.auto_speaker")
    speaker_cast = _speaker_cast_module()
    prepared = _task4_prepared(tmp_path)
    pcm_path = tmp_path / "canonical-shape.pcm"
    pcm_path.write_bytes(_task4_pcm_bytes(120.0, seconds=0.5))
    state = {
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
    }
    calls = {"extract": 0, "classify": 0}

    assert "_pipeline_workspace" not in prepared
    assert "speaker_sidecar_path" not in prepared
    assert "speaker_sidecar_sha256" not in prepared
    assert "media_sha256" not in prepared
    assert "subtitle_sha256" not in prepared

    async def prepare_subtitles(_state, *, require_auto_cast):
        assert require_auto_cast is True
        return prepared

    async def post_prepare_gate(_prepared, _state):
        return {"continue": True}

    async def extract_pcm(*_args, **_kwargs):
        calls["extract"] += 1
        return str(pcm_path)

    def classify(_path, ranges, *, deadline_monotonic, stop_requested):
        calls["classify"] += 1
        assert deadline_monotonic > time.monotonic()
        assert stop_requested() is False
        assert ranges == {"chunk_00:speaker_0": [(0.0, 3.0)]}
        return {
            "chunk_00:speaker_0": {
                "speaker_id": "chunk_00:speaker_0",
                "voice_register": "low",
                "confidence": 0.99,
                "voiced_seconds": 3.0,
                "sample_count": 48_000,
                "reason": "classified",
            }
        }

    monkeypatch.setattr(speaker_cast, "classify_speaker_registers", classify)
    result = asyncio.run(
        auto_speaker.run_auto_speaker_preflight(
            state,
            prepare_subtitles=prepare_subtitles,
            post_prepare_gate=post_prepare_gate,
            extract_pcm=extract_pcm,
        )
    )

    assert result["ok"] is True
    assert result["status"] == "AUTO_SPEAKER_PREFLIGHT_READY"
    assert calls == {"extract": 1, "classify": 1}
    assert not pcm_path.exists()


@pytest.mark.parametrize(
    "mutation",
    ("missing_source_bytes", "media_mismatch", "subtitle_mismatch", "missing_receipt"),
)
def test_preflight_gate_canonical_prepare_receipt_mismatch_fails_closed(
    tmp_path,
    monkeypatch,
    mutation,
):
    auto_speaker = importlib.import_module("services.subdub_blackboxes.auto_speaker")
    speaker_cast = _speaker_cast_module()
    prepared = _task4_prepared(tmp_path)
    if mutation == "missing_source_bytes":
        prepared.pop("source_bytes")
    elif mutation == "media_mismatch":
        prepared["source_bytes"] = b"different-media"
    elif mutation == "subtitle_mismatch":
        prepared["source_subtitle"] = str(prepared["source_subtitle"]) + "changed"
    else:
        prepared["state"].pop("speaker_sidecar_sha256")
    state = {
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
    }
    calls = {"extract": 0, "classify": 0}

    async def prepare_subtitles(_state, *, require_auto_cast):
        assert require_auto_cast is True
        return prepared

    async def post_prepare_gate(_prepared, _state):
        return {"continue": True}

    async def extract_pcm(*_args, **_kwargs):
        calls["extract"] += 1
        raise AssertionError("invalid canonical receipt must fail before PCM extraction")

    def classify(*_args, **_kwargs):
        calls["classify"] += 1
        raise AssertionError("invalid canonical receipt must fail before classification")

    monkeypatch.setattr(speaker_cast, "classify_speaker_registers", classify)
    result = asyncio.run(
        auto_speaker.run_auto_speaker_preflight(
            state,
            prepare_subtitles=prepare_subtitles,
            post_prepare_gate=post_prepare_gate,
            extract_pcm=extract_pcm,
        )
    )

    assert result["status"] == "AUTO_CAST_MANUAL_REQUIRED"
    assert result["reason"] == "AUTO_CAST_UNAVAILABLE"
    assert calls == {"extract": 0, "classify": 0}


def test_pcm_cleanup_oserror_after_success_fails_closed(tmp_path, monkeypatch):
    auto_speaker = importlib.import_module("services.subdub_blackboxes.auto_speaker")
    speaker_cast = _speaker_cast_module()
    prepared = _task4_prepared(tmp_path)
    pcm_path = tmp_path / "cleanup-failure.pcm"
    pcm_path.write_bytes(_task4_pcm_bytes(120.0, seconds=0.5))
    state = {
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
    }
    cleanup_attempts = []
    original_unlink = Path.unlink

    async def prepare_subtitles(_state, *, require_auto_cast):
        assert require_auto_cast is True
        return prepared

    async def post_prepare_gate(_prepared, _state):
        return {"continue": True}

    async def extract_pcm(*_args, **_kwargs):
        return str(pcm_path)

    def classify(*_args, **_kwargs):
        return {
            "chunk_00:speaker_0": {
                "speaker_id": "chunk_00:speaker_0",
                "voice_register": "low",
                "confidence": 0.99,
                "voiced_seconds": 3.0,
                "sample_count": 48_000,
                "reason": "classified",
            }
        }

    def unlink(self, *args, **kwargs):
        if self == pcm_path:
            cleanup_attempts.append(self)
            raise OSError("fixture_pcm_cleanup_failed")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(speaker_cast, "classify_speaker_registers", classify)
    monkeypatch.setattr(Path, "unlink", unlink)
    result = asyncio.run(
        auto_speaker.run_auto_speaker_preflight(
            state,
            prepare_subtitles=prepare_subtitles,
            post_prepare_gate=post_prepare_gate,
            extract_pcm=extract_pcm,
        )
    )

    assert result == {
        "ok": False,
        "status": "AUTO_CAST_MANUAL_REQUIRED",
        "reason": "AUTO_CAST_MANUAL_REQUIRED",
        "lane_mode": "",
        "public_copy_key": "voice_auto_manual_required",
    }
    assert cleanup_attempts == [pcm_path]
    assert pcm_path.exists()


def test_cancellation_pcm_cleanup_oserror_preserves_cancelled_error(tmp_path, monkeypatch):
    auto_speaker = importlib.import_module("services.subdub_blackboxes.auto_speaker")
    speaker_cast = _speaker_cast_module()
    prepared = _task4_prepared(tmp_path)
    pcm_path = tmp_path / "cancel-cleanup-failure.pcm"
    pcm_path.write_bytes(_task4_pcm_bytes(120.0, seconds=0.5))
    state = {
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
    }
    worker_started = threading.Event()
    worker_exited = threading.Event()
    cleanup_attempts = []
    original_unlink = Path.unlink

    async def prepare_subtitles(_state, *, require_auto_cast):
        assert require_auto_cast is True
        return prepared

    async def post_prepare_gate(_prepared, _state):
        return {"continue": True}

    async def extract_pcm(*_args, **_kwargs):
        return str(pcm_path)

    def classify(_path, _ranges, *, deadline_monotonic, stop_requested):
        assert deadline_monotonic > time.monotonic()
        worker_started.set()
        while not stop_requested():
            time.sleep(0.001)
        worker_exited.set()
        raise speaker_cast.AutoCastManualRequired()

    def unlink(self, *args, **kwargs):
        if self == pcm_path:
            cleanup_attempts.append(self)
            raise OSError("fixture_pcm_cleanup_failed")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(speaker_cast, "classify_speaker_registers", classify)
    monkeypatch.setattr(Path, "unlink", unlink)

    async def scenario():
        task = asyncio.create_task(
            auto_speaker.run_auto_speaker_preflight(
                state,
                prepare_subtitles=prepare_subtitles,
                post_prepare_gate=post_prepare_gate,
                extract_pcm=extract_pcm,
            )
        )
        while not worker_started.is_set():
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())

    assert worker_exited.is_set()
    assert cleanup_attempts == [pcm_path]
    assert pcm_path.exists()


def test_event_loop_preflight_uses_exact_deadline_and_stops_at_classification(tmp_path, monkeypatch):
    auto_speaker = importlib.import_module("services.subdub_blackboxes.auto_speaker")
    speaker_cast = _speaker_cast_module()
    prepared = _task4_prepared(tmp_path)
    pcm_path = tmp_path / "worker.pcm"
    pcm_path.write_bytes(_task4_pcm_bytes(120.0, seconds=0.5))
    state = {
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "mode": "dub_only",
    }
    captured = {}
    worker_started = threading.Event()

    class FixedTime:
        @staticmethod
        def monotonic():
            return 100.0

    async def prepare_subtitles(_state, *, require_auto_cast):
        assert require_auto_cast is True
        return prepared

    async def post_prepare_gate(_prepared, _state):
        return {"continue": True}

    async def extract_pcm(_prepared, _state, *, channels, sample_rate, sample_format):
        assert (channels, sample_rate, sample_format) == (1, 16_000, "s16le")
        return str(pcm_path)

    def classify(_path, ranges, *, deadline_monotonic, stop_requested):
        captured["thread_id"] = threading.get_ident()
        captured["deadline"] = deadline_monotonic
        captured["ranges"] = ranges
        captured["stop_requested"] = stop_requested
        worker_started.set()
        time.sleep(0.06)
        return {
            "chunk_00:speaker_0": {
                "speaker_id": "chunk_00:speaker_0",
                "voice_register": "low",
                "confidence": 0.99,
                "voiced_seconds": 3.0,
                "sample_count": 48_000,
                "reason": "classified",
            }
        }

    monkeypatch.setattr(auto_speaker, "time", FixedTime)
    monkeypatch.setattr(speaker_cast, "classify_speaker_registers", classify)

    async def scenario():
        loop_thread_id = threading.get_ident()
        heartbeat = 0
        finished = False

        async def beat():
            nonlocal heartbeat
            while not finished:
                heartbeat += 1
                await asyncio.sleep(0)

        heartbeat_task = asyncio.create_task(beat())
        try:
            result = await auto_speaker.run_auto_speaker_preflight(
                state,
                prepare_subtitles=prepare_subtitles,
                post_prepare_gate=post_prepare_gate,
                extract_pcm=extract_pcm,
            )
        finally:
            finished = True
            await heartbeat_task
        return result, heartbeat, loop_thread_id

    result, heartbeat, loop_thread_id = asyncio.run(scenario())

    assert worker_started.is_set()
    assert captured["thread_id"] != loop_thread_id
    assert captured["deadline"] - 100.0 == pytest.approx(30.0)
    assert heartbeat > 2
    assert not pcm_path.exists()
    assert result["ok"] is True
    assert result["classifications"]["chunk_00:speaker_0"]["voice_register"] == "low"
    assert not {
        "speaker_assignments",
        "assigned_segments",
        "resolve_voice_id",
        "synthesize_segments",
        "lane_runner",
        "failure_slot",
    }.intersection(result)
    parameters = inspect.signature(auto_speaker.run_auto_speaker_preflight).parameters
    assert not {"lane_runner", "runner", "resolve_voice_id", "synthesize_segments"}.intersection(parameters)


def test_cancellation_signals_worker_before_pcm_cleanup(tmp_path, monkeypatch):
    auto_speaker = importlib.import_module("services.subdub_blackboxes.auto_speaker")
    speaker_cast = _speaker_cast_module()
    prepared = _task4_prepared(tmp_path)
    pcm_path = tmp_path / "cancel.pcm"
    pcm_path.write_bytes(_task4_pcm_bytes(120.0, seconds=0.5))
    state = {
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
    }
    worker_started = threading.Event()
    worker_exited = threading.Event()
    observed = {}

    async def prepare_subtitles(_state, *, require_auto_cast):
        assert require_auto_cast is True
        return prepared

    async def post_prepare_gate(_prepared, _state):
        return {"continue": True}

    async def extract_pcm(*_args, **_kwargs):
        return str(pcm_path)

    def classify(_path, _ranges, *, deadline_monotonic, stop_requested):
        assert deadline_monotonic > time.monotonic()
        worker_started.set()
        while not stop_requested():
            time.sleep(0.001)
        observed["pcm_exists_at_worker_exit"] = pcm_path.exists()
        worker_exited.set()
        raise speaker_cast.AutoCastManualRequired()

    monkeypatch.setattr(speaker_cast, "classify_speaker_registers", classify)

    async def scenario():
        task = asyncio.create_task(
            auto_speaker.run_auto_speaker_preflight(
                state,
                prepare_subtitles=prepare_subtitles,
                post_prepare_gate=post_prepare_gate,
                extract_pcm=extract_pcm,
            )
        )
        while not worker_started.is_set():
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())

    assert worker_exited.is_set()
    assert observed["pcm_exists_at_worker_exit"] is True
    assert not pcm_path.exists()


def test_manual_required_timeout_waits_for_worker_before_pcm_cleanup(tmp_path, monkeypatch):
    auto_speaker = importlib.import_module("services.subdub_blackboxes.auto_speaker")
    speaker_cast = _speaker_cast_module()
    prepared = _task4_prepared(tmp_path)
    pcm_path = tmp_path / "timeout.pcm"
    pcm_path.write_bytes(_task4_pcm_bytes(120.0, seconds=0.5))
    state = {
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
    }
    worker_exited = threading.Event()
    observed = {}

    async def prepare_subtitles(_state, *, require_auto_cast):
        assert require_auto_cast is True
        return prepared

    async def post_prepare_gate(_prepared, _state):
        return {"continue": True}

    async def extract_pcm(*_args, **_kwargs):
        return str(pcm_path)

    def classify(_path, _ranges, *, deadline_monotonic, stop_requested):
        while not stop_requested() and time.monotonic() < deadline_monotonic:
            time.sleep(0.001)
        observed["pcm_exists_at_worker_exit"] = pcm_path.exists()
        worker_exited.set()
        raise speaker_cast.AutoCastManualRequired()

    monkeypatch.setattr(speaker_cast, "CLASSIFIER_WALL_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(speaker_cast, "classify_speaker_registers", classify)

    result = asyncio.run(
        auto_speaker.run_auto_speaker_preflight(
            state,
            prepare_subtitles=prepare_subtitles,
            post_prepare_gate=post_prepare_gate,
            extract_pcm=extract_pcm,
        )
    )

    assert result["status"] == "AUTO_CAST_MANUAL_REQUIRED"
    assert result["reason"] == "AUTO_CAST_MANUAL_REQUIRED"
    assert worker_exited.is_set()
    assert observed["pcm_exists_at_worker_exit"] is True
    assert not pcm_path.exists()


def _task5_classifications():
    return {
        "chunk_00:speaker_0": {
            "speaker_id": "chunk_00:speaker_0",
            "voice_register": "low",
            "confidence": 0.90,
        },
        "chunk_00:speaker_1": {
            "speaker_id": "chunk_00:speaker_1",
            "voice_register": "low",
            "confidence": 0.88,
        },
        "chunk_01:speaker_0": {
            "speaker_id": "chunk_01:speaker_0",
            "voice_register": "high",
            "confidence": 0.91,
        },
        "chunk_01:speaker_1": {
            "speaker_id": "chunk_01:speaker_1",
            "voice_register": "high",
            "confidence": 0.89,
        },
    }


def _task5_voice_pools():
    return {
        "low": ["low-a", "low-b"],
        "high": ["high-a", "high-b"],
    }


def _task5_prepared_segments():
    source = [
        {
            "cue_id": "cue-a",
            "start": 0.0,
            "end": 1.0,
            "start_ms": 0,
            "end_ms": 1_000,
            "index": 1,
            "text": "source a",
            "speaker_id": "chunk_00:speaker_0",
        },
        {
            "cue_id": "cue-b",
            "start": 1.0,
            "end": 2.0,
            "start_ms": 1_000,
            "end_ms": 2_000,
            "index": 2,
            "text": "source b",
            "speaker_id": "chunk_01:speaker_0",
        },
        {
            "cue_id": "cue-c",
            "start": 2.0,
            "end": 3.0,
            "start_ms": 2_000,
            "end_ms": 3_000,
            "index": 3,
            "text": "source c",
            "speaker_id": "chunk_00:speaker_0",
        },
    ]
    by_id = {item["cue_id"]: item for item in source}
    output = [
        {**by_id["cue-b"], "text": "translated b"},
        {**by_id["cue-a"], "text": "translated a"},
        {**by_id["cue-c"], "text": "translated c"},
    ]
    return source, output


def _task5_auto_harness(
    monkeypatch,
    *,
    mode="dub",
    provider_labels=None,
    prepared_mutator=None,
    selected_mutator=None,
    scalar_chunks="one",
    swallow_auto_error=False,
    cue_limit=None,
    validated_pools=None,
    two_low_speakers=False,
):
    auto_speaker = importlib.import_module("services.subdub_blackboxes.auto_speaker")
    speaker_cast = _speaker_cast_module()
    shared_pipeline = importlib.import_module("services.subtitle_dub_product_pipeline")
    source, output = _task5_prepared_segments()
    if cue_limit is not None:
        source = source[: int(cue_limit)]
        kept_ids = {item["cue_id"] for item in source}
        output = [item for item in output if item["cue_id"] in kept_ids]
    state = {
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "mode": mode,
        "dub_text_source": "source" if mode == "dub" else "translated",
        "target_language": "auto" if mode == "dub" else "en",
        "translate_requested": mode != "dub",
    }
    prepared = {
        "state": {
            **state,
            "speaker_sidecar_sha256": "a" * 64,
        },
        "source_segments": copy.deepcopy(source),
        "output_segments": copy.deepcopy(output),
    }
    if prepared_mutator is not None:
        prepared_mutator(prepared)

    labels = ["chunk_00:speaker_0", "chunk_01:speaker_0"]
    classifications = {
        "chunk_01:speaker_0": {
            "speaker_id": "chunk_01:speaker_0",
            "voice_register": "high",
            "confidence": 0.91,
        },
        "chunk_00:speaker_0": {
            "speaker_id": "chunk_00:speaker_0",
            "voice_register": "low",
            "confidence": 0.90,
        },
    }
    if two_low_speakers:
        classifications["chunk_01:speaker_0"]["voice_register"] = "low"
    calls = {
        "prepare": 0,
        "gate": 0,
        "lane": 0,
        "lane_prepare": 0,
        "manual_resolver": 0,
        "scalar": [],
        "annotated": None,
        "compatibility_voice": "",
        "selected": [],
    }

    async def prepare_subtitles(received_state, *, require_auto_cast):
        calls["prepare"] += 1
        assert received_state is state
        assert require_auto_cast is True
        return prepared

    async def post_prepare_gate(received_prepared, received_state):
        calls["gate"] += 1
        assert received_prepared is prepared
        assert received_state is state
        return {"continue": True}

    async def extract_pcm(*_args, **_kwargs):
        raise AssertionError("Task 5 harness stubs the already-proven classifier seam")

    async def fake_preflight(
        received_state,
        *,
        prepare_subtitles,
        post_prepare_gate,
        extract_pcm,
    ):
        del extract_pcm
        received_prepared = await prepare_subtitles(
            received_state,
            require_auto_cast=True,
        )
        gate = await post_prepare_gate(received_prepared, received_state)
        assert gate == {"continue": True}
        return {
            "ok": True,
            "status": "AUTO_SPEAKER_PREFLIGHT_READY",
            "prepared": received_prepared,
            "speaker_labels": labels,
            "classifications": classifications,
        }

    def forbidden_manual_resolver(*_args, **_kwargs):
        calls["manual_resolver"] += 1
        raise AssertionError("Auto must not query the manual/live voice resolver")

    labels_for_calls = list(provider_labels or ["provider-a"] * 3)

    async def scalar_synth(segments, **kwargs):
        cue = dict(segments[0])
        call_index = len(calls["scalar"])
        calls["scalar"].append(
            {
                "segments": copy.deepcopy(segments),
                "kwargs": dict(kwargs),
            }
        )
        if scalar_chunks == "raise_generic":
            raise RuntimeError("fixture_provider_failed")
        if scalar_chunks == "cancel":
            raise asyncio.CancelledError()
        chunk = {
            "index": cue["index"],
            "start": cue["start"],
            "end": cue["end"],
            "text": cue["text"],
            "audio_bytes": f"audio-{cue['cue_id']}".encode("utf-8"),
            "marker": f"{cue['cue_id']}-1",
        }
        if scalar_chunks == "missing":
            chunks = []
        elif scalar_chunks == "malformed":
            chunks = [{"start": cue["start"], "end": cue["end"]}]
        elif scalar_chunks == "multi" and cue["cue_id"] == "cue-a":
            midpoint = (float(cue["start"]) + float(cue["end"])) / 2.0
            chunks = [
                {**chunk, "end": midpoint, "marker": "A1"},
                {**chunk, "start": midpoint, "marker": "A2"},
            ]
        elif scalar_chunks == "multi" and cue["cue_id"] == "cue-b":
            chunks = [{**chunk, "marker": "B1"}]
        else:
            chunks = [chunk]
        return {
            "chunks": chunks,
            "provider": labels_for_calls[call_index] if call_index < len(labels_for_calls) else "",
        }

    async def runner_token(**_kwargs):
        raise AssertionError("fake lane owns this focused runner seam")

    async def run_lane_blackbox(*, lane_mode, runner, **payload):
        calls["lane"] += 1
        assert lane_mode == mode
        assert runner is runner_token
        assert payload["mode"] == mode
        assert payload["unrelated_dependency"] is _task5_auto_harness
        calls["lane_prepare"] += 1
        annotated = await payload["prepare_subtitles"](payload["state"])
        calls["annotated"] = annotated
        if selected_mutator is not None:
            selected_mutator(annotated, state)
        try:
            compatibility_voice = payload["resolve_voice_id"](
                payload["user_id"],
                payload["state"],
            )
            calls["compatibility_voice"] = compatibility_voice
            policy = shared_pipeline.resolve_subdub_dub_audio_policy(
                payload["state"],
                annotated,
            )
            selected = list(policy.get("tts_segments") or [])
            calls["selected"] = copy.deepcopy(selected)
            aggregate = await payload["synthesize_segments"](
                selected,
                voice_style="style-kept",
                voice_id=compatibility_voice,
                base_speed=0.9,
                max_speed=0.9,
                tts_language_code="ja",
                tts_language_boost="Japanese",
                edge_voice_id="edge-kept",
            )
        except (speaker_cast.AutoCastUnavailable, speaker_cast.AutoCastManualRequired):
            if swallow_auto_error:
                return {"ok": False, "status": "GENERIC_PIPELINE_FAILURE"}
            raise
        return {
            "ok": True,
            "status": "OK",
            "aggregate": aggregate,
            "compatibility_voice": compatibility_voice,
        }

    monkeypatch.setattr(auto_speaker, "run_auto_speaker_preflight", fake_preflight)
    result = asyncio.run(
        auto_speaker.run_auto_speaker_blackbox(
            lane_mode=mode,
            run_lane_blackbox=run_lane_blackbox,
            runner=runner_token,
            prepare_subtitles=prepare_subtitles,
            resolve_voice_id=forbidden_manual_resolver,
            synthesize_segments=scalar_synth,
            post_prepare_gate=post_prepare_gate,
            extract_pcm=extract_pcm,
            validated_pools=validated_pools or _task5_voice_pools(),
            mode=mode,
            state=state,
            user_id=7,
            unrelated_dependency=_task5_auto_harness,
        )
    )
    return result, calls, source, output


def test_stable_voice_assignment_is_deterministic_in_first_cue_order():
    speaker_cast = _speaker_cast_module()
    speaker_order = list(_task5_classifications())
    classifications = _task5_classifications()

    casts_a = speaker_cast.assign_stable_voices(
        classifications,
        speaker_order=speaker_order,
        validated_pools=_task5_voice_pools(),
        assignment_seed="a" * 64,
    )
    casts_b = speaker_cast.assign_stable_voices(
        dict(reversed(list(classifications.items()))),
        speaker_order=speaker_order,
        validated_pools={
            "high": ["high-b", "high-a"],
            "low": ["low-b", "low-a"],
        },
        assignment_seed="a" * 64,
    )

    assert casts_a == casts_b
    assert list(casts_a) == speaker_order
    assert len({casts_a[speaker_order[0]]["voice_id"], casts_a[speaker_order[1]]["voice_id"]}) == 2
    assert len({casts_a[speaker_order[2]]["voice_id"], casts_a[speaker_order[3]]["voice_id"]}) == 2
    assert {item["voice_register"] for item in casts_a.values()} == {"low", "high"}


@pytest.mark.parametrize(
    ("classifications", "speaker_order", "pools", "seed"),
    (
        ({}, [], _task5_voice_pools(), "a" * 64),
        (_task5_classifications(), list(_task5_classifications()) + ["chunk_02:speaker_0"], _task5_voice_pools(), "a" * 64),
        (_task5_classifications(), list(_task5_classifications()), {"low": [], "high": ["high-a", "high-b"]}, "a" * 64),
        (_task5_classifications(), list(_task5_classifications()), {"low": ["low-a"], "high": ["high-a", "high-b"]}, "a" * 64),
        (_task5_classifications(), list(_task5_classifications()), {"low": ["low-a", "low-a"], "high": ["high-a", "high-b"]}, "a" * 64),
        (_task5_classifications(), list(_task5_classifications()), {"low": ["bad voice", "low-b"], "high": ["high-a", "high-b"]}, "a" * 64),
        (_task5_classifications(), list(_task5_classifications()), {"low": ["shared", "low-b"], "high": ["shared", "high-b"]}, "a" * 64),
        (_task5_classifications(), list(_task5_classifications()), _task5_voice_pools(), "not-a-sidecar-sha"),
    ),
)
def test_voice_pool_validation_fails_closed_before_assignment(
    classifications,
    speaker_order,
    pools,
    seed,
):
    speaker_cast = _speaker_cast_module()

    with pytest.raises(
        speaker_cast.AutoCastManualRequired,
        match="^AUTO_CAST_MANUAL_REQUIRED$",
    ):
        speaker_cast.assign_stable_voices(
            classifications,
            speaker_order=speaker_order,
            validated_pools=pools,
            assignment_seed=seed,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("voice_register", "unknown"),
        ("voice_register", "LOW"),
        ("confidence", 0.7499),
        ("confidence", float("nan")),
    ),
)
def test_stable_voice_assignment_rejects_unusable_classification(field, value):
    speaker_cast = _speaker_cast_module()
    classifications = _task5_classifications()
    classifications["chunk_00:speaker_0"][field] = value

    with pytest.raises(
        speaker_cast.AutoCastManualRequired,
        match="^AUTO_CAST_MANUAL_REQUIRED$",
    ):
        speaker_cast.assign_stable_voices(
            classifications,
            speaker_order=list(classifications),
            validated_pools=_task5_voice_pools(),
            assignment_seed="a" * 64,
        )


def test_voice_pool_insufficient_capacity_fails_before_lane_or_tts(monkeypatch):
    result, calls, _source, _output = _task5_auto_harness(
        monkeypatch,
        validated_pools={
            "low": ["low-a"],
            "high": ["high-a", "high-b"],
        },
        two_low_speakers=True,
    )

    assert result["status"] == "AUTO_CAST_MANUAL_REQUIRED"
    assert calls["lane"] == 0
    assert calls["scalar"] == []


@pytest.mark.parametrize("mode", ("dub", "subtitle_plus_dub"))
def test_per_cue_auto_wrapper_identity_joins_both_policy_lists_and_delegates_once(
    monkeypatch,
    mode,
):
    result, calls, source, output = _task5_auto_harness(monkeypatch, mode=mode)

    assert result["ok"] is True
    assert calls["prepare"] == 1
    assert calls["gate"] == 1
    assert calls["lane"] == 1
    assert calls["lane_prepare"] == 1
    assert calls["manual_resolver"] == 0
    annotated = calls["annotated"]
    assert [
        (item["cue_id"], item["start"], item["end"])
        for item in annotated["source_segments"]
    ] == [(item["cue_id"], item["start"], item["end"]) for item in source]
    assert [
        (item["cue_id"], item["start"], item["end"])
        for item in annotated["output_segments"]
    ] == [(item["cue_id"], item["start"], item["end"]) for item in output]
    source_voices = {
        item["cue_id"]: (item["voice_register"], item["tts_voice_id"])
        for item in annotated["source_segments"]
    }
    output_voices = {
        item["cue_id"]: (item["voice_register"], item["tts_voice_id"])
        for item in annotated["output_segments"]
    }
    assert output_voices == source_voices
    expected_selected = (
        [item["cue_id"] for item in source]
        if mode == "dub"
        else [item["cue_id"] for item in output]
    )
    assert [item["cue_id"] for item in calls["selected"]] == expected_selected
    assert [entry["segments"][0]["cue_id"] for entry in calls["scalar"]] == expected_selected
    assert calls["compatibility_voice"] == calls["selected"][0]["tts_voice_id"]
    for entry in calls["scalar"]:
        cue = entry["segments"][0]
        kwargs = entry["kwargs"]
        assert kwargs == {
            "voice_style": "style-kept",
            "voice_id": cue["tts_voice_id"],
            "base_speed": 0.9,
            "max_speed": 0.9,
            "tts_language_code": "ja",
            "tts_language_boost": "Japanese",
            "edge_voice_id": "edge-kept",
        }


@pytest.mark.parametrize(
    ("labels", "expected"),
    (
        (["provider-a", "provider-a", "provider-a"], "provider-a"),
        (["provider-a", "provider-b", "provider-a"], "mixed"),
        (["", "", ""], ""),
    ),
)
def test_provider_aggregation_is_deterministic_and_internal(monkeypatch, labels, expected):
    result, calls, _source, _output = _task5_auto_harness(
        monkeypatch,
        provider_labels=labels,
    )

    assert result["aggregate"]["provider"] == expected
    assert len(result["aggregate"]["chunks"]) == 3
    assert [item["cue_id"] for item in calls["selected"]] == ["cue-a", "cue-b", "cue-c"]
    assert "provider" not in str(result.get("public_copy_key") or "").lower()
    assert "mixed" not in str(result.get("public_copy_key") or "").lower()


@pytest.mark.parametrize("replacement", (None, "", "not-in-pool"))
def test_per_cue_voice_id_must_be_nonempty_and_in_validated_pool_before_tts(
    monkeypatch,
    replacement,
):
    def mutate_selected(prepared, _state):
        if replacement is None:
            prepared["source_segments"][0].pop("tts_voice_id", None)
        else:
            prepared["source_segments"][0]["tts_voice_id"] = replacement

    result, calls, _source, _output = _task5_auto_harness(
        monkeypatch,
        selected_mutator=mutate_selected,
        swallow_auto_error=True,
    )

    assert result["status"] == "AUTO_CAST_MANUAL_REQUIRED"
    assert result["public_copy_key"] == "voice_auto_manual_required"
    assert calls["scalar"] == []
    assert calls["manual_resolver"] == 0


@pytest.mark.parametrize("scalar_chunks", ("missing", "malformed"))
def test_per_cue_scalar_result_count_fails_closed(monkeypatch, scalar_chunks):
    result, calls, _source, _output = _task5_auto_harness(
        monkeypatch,
        scalar_chunks=scalar_chunks,
        swallow_auto_error=True,
    )

    assert result["status"] == "AUTO_CAST_MANUAL_REQUIRED"
    assert result["public_copy_key"] == "voice_auto_manual_required"
    assert len(calls["scalar"]) == 1


def test_per_cue_multi_chunk_result_flattens_in_cue_then_chunk_order(monkeypatch):
    result, calls, _source, _output = _task5_auto_harness(
        monkeypatch,
        scalar_chunks="multi",
        cue_limit=2,
    )

    assert result["ok"] is True
    assert len(calls["scalar"]) == 2
    assert [item["marker"] for item in result["aggregate"]["chunks"]] == [
        "A1",
        "A2",
        "B1",
    ]
    assert [
        (item["start"], item["end"])
        for item in result["aggregate"]["chunks"]
    ] == [(0.0, 0.5), (0.5, 1.0), (1.0, 2.0)]


def test_per_cue_unrelated_scalar_failure_is_not_relabelled(monkeypatch):
    with pytest.raises(RuntimeError, match="^fixture_provider_failed$"):
        _task5_auto_harness(
            monkeypatch,
            scalar_chunks="raise_generic",
        )


def test_per_cue_external_cancellation_is_not_intercepted(monkeypatch):
    with pytest.raises(asyncio.CancelledError):
        _task5_auto_harness(
            monkeypatch,
            scalar_chunks="cancel",
        )


@pytest.mark.parametrize(
    "prepared_mutator",
    (
        lambda prepared: prepared.pop("source_segments"),
        lambda prepared: prepared.pop("output_segments"),
        lambda prepared: prepared["output_segments"].append(copy.deepcopy(prepared["output_segments"][0])),
        lambda prepared: prepared["output_segments"][0].__setitem__("start", 1.001),
        lambda prepared: prepared["output_segments"][0].pop("cue_id"),
    ),
)
def test_per_cue_identity_join_fails_before_lane_or_tts(monkeypatch, prepared_mutator):
    result, calls, _source, _output = _task5_auto_harness(
        monkeypatch,
        prepared_mutator=prepared_mutator,
    )

    assert result["status"] == "AUTO_CAST_MANUAL_REQUIRED"
    assert calls["lane"] == 0
    assert calls["scalar"] == []


def test_catalog_is_never_queried_and_environment_is_unchanged(monkeypatch):
    provider_contract = importlib.import_module("services.subdub_provider_contract")
    before_environment = dict(os.environ)
    catalog_calls = []

    def forbidden_catalog(*_args, **_kwargs):
        catalog_calls.append(True)
        raise AssertionError("live voice catalog must not be queried during an Auto job")

    monkeypatch.setattr(
        provider_contract,
        "load_shopaikey_minimax_voice_catalog",
        forbidden_catalog,
    )
    result, calls, _source, _output = _task5_auto_harness(monkeypatch)

    assert result["ok"] is True
    assert catalog_calls == []
    assert calls["manual_resolver"] == 0
    assert dict(os.environ) == before_environment


def _task6_callbacks(markup):
    return [
        str(button.callback_data or "")
        for row in markup.inline_keyboard
        for button in row
    ]


@pytest.mark.parametrize(
    "state",
    (
        {"mode": "dub"},
        {
            "mode": "subtitle_plus_dub",
            "active_flow": "subtitle_plus_dub",
            "requested_mode": "subtitle_plus_dub",
        },
    ),
)
def test_auto_button_is_built_for_both_lanes_but_activation_closed(monkeypatch, state):
    monkeypatch.setattr(bot, "SUBDUB_AUTO_SPEAKER_ACTIVATION_ENABLED", False)

    hidden = bot.video_dubbing_voice_keyboard("ja", state)
    assert "videodub|voice|auto_speaker_gender" not in _task6_callbacks(hidden)

    monkeypatch.setattr(bot, "SUBDUB_AUTO_SPEAKER_ACTIVATION_ENABLED", True)
    visible = bot.video_dubbing_voice_keyboard("ja", state)
    buttons = [button for row in visible.inline_keyboard for button in row]
    auto_buttons = [
        button for button in buttons
        if button.callback_data == "videodub|voice|auto_speaker_gender"
    ]
    assert [button.text for button in auto_buttons] == [
        "👥 音声を自動割り当て（最大 16）"
    ]
    assert "人物の特定や個人の性別判定は行いません" in bot.video_dubbing_voice_text(state, "ja")


def test_voice_state_reset_is_bidirectional_and_reset_before_assign():
    manual = {
        "keep": "yes",
        "voice_kind": "saved_voice",
        "voice_selection_mode": "legacy-manual",
        "voice_style": "saved",
        "voice_id": "saved-id",
        "voice_profile_id": 7,
        "selected_voice": "saved-id",
        "selected_voice_label": "Saved",
        "selected_voice_gender": "female",
        "selected_voice_id": "saved-id",
        "requested_voice_gender": "female",
        "dub_voice_gender": "female",
        "provider_voice_id": "saved-id",
        "selected_tts_voice_id": "saved-id",
        "tts_payload_voice_id": "saved-id",
        "resolved_voice_id": "saved-id",
        "resolved_gender": "female",
        "_subdub_voice_resolution": {"ok": True},
    }
    reset_for_auto = bot.reset_subdub_voice_selection(manual, selecting_auto=True)
    assert reset_for_auto == {"keep": "yes"}

    selected_auto = bot.subdub_apply_voice_choice(
        manual,
        "auto_speaker_gender",
        lang="ja",
        activation_enabled=True,
    )
    assert selected_auto["keep"] == "yes"
    assert selected_auto["voice_kind"] == "auto_speaker_gender"
    assert selected_auto["voice_selection_mode"] == "auto_speaker"
    assert not (set(bot.SUBDUB_MANUAL_VOICE_FIELDS) & set(selected_auto))

    selected_auto.update({
        "speaker_sidecar_path": "C:/job/speaker_cast.sidecar.json",
        "speaker_sidecar_sha256": "a" * 64,
        "speaker_classifications": {"speaker": "internal"},
        "speaker_casts": {"speaker": "internal"},
        "per_cue_voice_assignments": [{"cue": "internal"}],
        "auto_exact_receipt_version": "v1",
        "auto_exact_actual_billable_words": "42",
    })
    reset_for_manual = bot.reset_subdub_voice_selection(
        selected_auto,
        selecting_auto=False,
    )
    assert reset_for_manual == {"keep": "yes"}

    selected_manual = bot.subdub_apply_voice_choice(
        selected_auto,
        "default_male",
        lang="en",
        activation_enabled=True,
    )
    assert selected_manual["voice_kind"] == "default_male"
    assert selected_manual["selected_voice_gender"] == "male"
    assert "voice_selection_mode" not in selected_manual
    assert not (set(bot.SUBDUB_AUTO_VOICE_FIELDS) & set(selected_manual))


def test_manual_modes_remain_scalar_and_auto_activation_cannot_be_inferred_from_state():
    auto_speaker = importlib.import_module("services.subdub_blackboxes.auto_speaker")
    auto_state = {
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
    }

    assert bot.subdub_apply_voice_choice(
        auto_state,
        "auto_speaker_gender",
        activation_enabled=False,
    ) is None
    for choice in ("default_female", "default_male", "custom prompt"):
        selected = bot.subdub_apply_voice_choice(
            auto_state,
            choice,
            lang="en",
            activation_enabled=False,
        )
        assert selected is not None
        assert not auto_speaker.is_auto_speaker_state(selected)
        assert "voice_selection_mode" not in selected


def test_route_gate_requires_activation_and_exact_pair(monkeypatch):
    matrix = (
        ({}, False),
        ({"voice_kind": "auto_speaker_gender"}, False),
        ({"voice_selection_mode": "auto_speaker"}, False),
        ({"voice_kind": "auto_speaker", "voice_selection_mode": "auto_speaker"}, False),
        ({"voice_kind": "auto_speaker_gender", "voice_selection_mode": "manual"}, False),
        ({"voice_kind": "auto_speaker_gender", "voice_selection_mode": "auto_speaker"}, True),
    )
    for enabled in (False, True):
        monkeypatch.setattr(bot, "SUBDUB_AUTO_SPEAKER_ACTIVATION_ENABLED", enabled)
        for state, exact in matrix:
            assert bot.subdub_auto_speaker_route_enabled(state) is (enabled and exact)


def test_exact_pair_dispatch_and_default_blackbox_source_contract():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert "if subdub_auto_speaker_route_enabled(state):" in source
    route_source = inspect.getsource(bot.subdub_auto_speaker_route_enabled)
    assert "SUBDUB_AUTO_SPEAKER_ACTIVATION_ENABLED" in route_source
    assert "auto_speaker.is_auto_speaker_state(state)" in route_source
    assert "product_result = await auto_speaker.run_auto_speaker_blackbox(" in source
    assert "run_lane_blackbox=subdub_blackboxes.run_subdub_lane_blackbox" in source
    assert "runner=subtitle_dub_product_pipeline.run_subdub_pipeline" in source
    assert "post_prepare_gate=_subdub_auto_post_prepare_gate" in source
    assert "extract_pcm=_extract_subdub_auto_pcm" in source
    assert "else:\n        product_result = await subdub_blackboxes.run_subdub_lane_blackbox(" in source
    assert "async def _prepare_subtitles_for_blackbox(\n        service_state: dict,\n        *,\n        require_auto_cast: bool = False," in source
    assert "require_auto_cast=bool(require_auto_cast)" in source
    assert "prepared_state = dict(prepared_dict.get(\"state\") or service_state or {})" in source
    assert "if require_auto_cast:\n            # set_video_dubbing_pending intentionally omits private pipeline" in source


@pytest.mark.parametrize(
    ("activation", "voice_state", "expected_route", "expected_auto_prepare"),
    (
        pytest.param(
            True,
            {"voice_kind": "auto_speaker_gender", "voice_selection_mode": "auto_speaker"},
            "auto",
            True,
            id="exact-auto",
        ),
        pytest.param(
            False,
            {"voice_kind": "auto_speaker_gender", "voice_selection_mode": "auto_speaker"},
            "manual",
            False,
            id="closed-exact-pair",
        ),
        pytest.param(
            True,
            {},
            "manual",
            False,
            id="default-empty",
        ),
        pytest.param(
            True,
            {"voice_kind": "auto_speaker_gender"},
            "manual",
            False,
            id="partial-kind",
        ),
        pytest.param(
            True,
            {"voice_selection_mode": "auto_speaker"},
            "manual",
            False,
            id="partial-mode",
        ),
        pytest.param(
            True,
            {"voice_kind": "default_female", "voice_style": "Default female"},
            "manual",
            False,
            id="manual",
        ),
        pytest.param(
            True,
            {"voice_kind": "saved_voice", "voice_style": "Saved voice"},
            "manual",
            False,
            id="saved-manual",
        ),
        pytest.param(
            True,
            {"voice_kind": "custom_prompt", "voice_style": "Custom voice"},
            "manual",
            False,
            id="custom-manual",
        ),
        pytest.param(
            True,
            {"voice_kind": "auto_speaker_gender", "voice_selection_mode": "manual"},
            "manual",
            False,
            id="malformed-auto-kind-manual-mode",
        ),
        pytest.param(
            True,
            {"voice_kind": "default_male", "voice_selection_mode": "auto_speaker"},
            "manual",
            False,
            id="malformed-manual-kind-auto-mode",
        ),
        pytest.param(
            True,
            {"voice_kind": "auto_speaker", "voice_selection_mode": "malformed"},
            "manual",
            False,
            id="malformed",
        ),
    ),
)
def test_dispatch_matrix_calls_one_blackbox_and_prepares_once(
    monkeypatch,
    tmp_path,
    activation,
    voice_state,
    expected_route,
    expected_auto_prepare,
):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    route_calls = {"auto": 0, "manual": 0}
    prepare_flags = []
    asr_calls = []
    dependency_checks = []

    monkeypatch.setattr(bot, "SUBDUB_AUTO_SPEAKER_ACTIVATION_ENABLED", activation)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(
        bot,
        "video_dubbing_engine_access_decision",
        lambda *_args, **_kwargs: {"allowed": True},
    )
    monkeypatch.setattr(
        bot,
        "video_dubbing_product_gate_matrix",
        lambda *_args, **_kwargs: {"product_route_allowed": True, "gate_blockers": []},
    )
    monkeypatch.setattr(
        bot,
        "video_dubbing_product_gate_allows_pipeline",
        lambda *_args, **_kwargs: True,
    )

    async def fake_save_input(*_args, **_kwargs):
        return {
            "ok": True,
            "path": str(source),
            "source_bytes": b"video",
            "content_type": "video/mp4",
            "size": source.stat().st_size,
            "duration": 1,
            "file_saved": True,
            "exists": True,
        }

    async def fake_media_preflight(video_bytes, *, content_type="video/mp4"):
        return {
            "ok": True,
            "normalized": False,
            "normalization_count": 0,
            "source_bytes": bytes(video_bytes),
            "content_type": content_type,
            "source_sha256": "fixture-source",
            "normalized_sha256": "fixture-source",
            "source_duration": 1.0,
            "source_probe": {
                "ok": True,
                "duration": 1.0,
                "normalization_required": False,
            },
        }

    async def fake_duration_gate(*_args, **_kwargs):
        return {
            "input_duration": 1,
            "telegram_duration": 1,
            "ffprobe_duration": 1,
            "detected_duration_source": "fixture",
            "duration_gate_result": "pass",
            "duration_limit": 3600,
        }

    async def fake_prepare(
        _context,
        service_state,
        _user_id,
        allow_admin=False,
        progress_callback=None,
        allow_confirmed_product=False,
        require_auto_cast=False,
    ):
        del allow_admin, progress_callback, allow_confirmed_product
        prepare_flags.append(bool(require_auto_cast))
        asr_calls.append("asr")
        srt = "1\n00:00:00,000 --> 00:00:01,000\nhello\n"
        segments = [{"index": 1, "start": 0.0, "end": 1.0, "text": "hello"}]
        return {
            "state": dict(service_state),
            "source_bytes": b"video",
            "content_type": "video/mp4",
            "source_subtitle": srt,
            "source_segments": segments,
            "source_script": "hello",
            "output_subtitle": srt,
            "output_segments": segments,
            "output_script": "hello",
            "asr_provider": "fixture",
            "duration_seconds": 1,
        }

    def common_dependency_identity(kwargs):
        return (
            kwargs["runner"] is bot.subtitle_dub_product_pipeline.run_subdub_pipeline,
            getattr(kwargs["prepare_subtitles"], "__name__", "") == "_prepare_subtitles_for_blackbox",
            getattr(kwargs["resolve_voice_id"], "__name__", "") == "_resolve_voice_id_for_blackbox",
            getattr(kwargs["synthesize_segments"], "__name__", "") == "_synthesize_dub_segments_for_blackbox",
            getattr(kwargs["render_video"], "__name__", "") == "_render_video_for_blackbox",
            kwargs["srt_from_text"] is bot.video_dubbing_srt_from_text,
            kwargs["segments_from_text"] is bot.video_dubbing_segments_from_text,
            kwargs["segments_from_subtitle"] is bot.video_dubbing_segments_from_subtitle,
            kwargs["subtitle_output_items"] is bot.video_dubbing_subtitle_output_items,
            kwargs["parse_voice_speed"] is bot.parse_video_dubbing_voice_speed,
            kwargs["build_timeline_audio"] is bot.build_dub_timeline_audio,
            kwargs["normalize_audio"] is bot.normalize_dub_audio_bytes,
            kwargs["validate_audio"] is bot.subdub_validate_tts_timeline_audio_bytes,
            callable(kwargs["video_render_ready"]),
            callable(kwargs["ffmpeg_ready"]),
        )

    async def manual_spy(**kwargs):
        route_calls["manual"] += 1
        dependency_checks.append(("manual", *common_dependency_identity(kwargs)))
        await kwargs["prepare_subtitles"](kwargs["state"])
        return {
            "ok": False,
            "status": "AUTO_CAST_MANUAL_REQUIRED",
            "state": dict(kwargs["state"]),
        }

    async def auto_spy(**kwargs):
        route_calls["auto"] += 1
        dependency_checks.append(
            (
                "auto",
                *common_dependency_identity(kwargs),
                kwargs["run_lane_blackbox"] is manual_spy,
                kwargs["post_prepare_gate"] is bot._subdub_auto_post_prepare_gate,
                kwargs["extract_pcm"] is bot._extract_subdub_auto_pcm,
                kwargs["validated_pools"]
                == bot.subdub_auto_validated_voice_pools(bot.subdub_tts_provider_name()),
            )
        )
        await kwargs["prepare_subtitles"](kwargs["state"], require_auto_cast=True)
        return {
            "ok": False,
            "status": "AUTO_CAST_MANUAL_REQUIRED",
            "state": dict(kwargs["state"]),
        }

    monkeypatch.setattr(bot, "video_dubbing_save_input_for_pipeline", fake_save_input)
    monkeypatch.setattr(bot, "subdub_normalize_video_bytes_if_needed", fake_media_preflight)
    monkeypatch.setattr(bot, "subdub_duration_gate_payload_for_saved_input", fake_duration_gate)
    monkeypatch.setattr(bot, "video_dubbing_prepare_subtitles", fake_prepare)
    monkeypatch.setattr(bot.subdub_blackboxes, "run_subdub_lane_blackbox", manual_spy)
    monkeypatch.setattr(bot.auto_speaker, "run_auto_speaker_blackbox", auto_spy)
    monkeypatch.setattr(
        bot,
        "subdub_auto_manual_required_recovery",
        lambda _uid, state, **_kwargs: {
            "ok": False,
            "status": "AUTO_CAST_MANUAL_REQUIRED",
            "state": dict(state),
            "text": "manual",
            "reply_markup": None,
            "charge_status": "not_charged",
        },
    )

    class Query:
        from_user = SimpleNamespace(id=97_175)
        message = SimpleNamespace(chat_id=97_175)

    state = {
        "mode": "dub",
        "process_type": "dub",
        "video_processing_mode": "dub",
        "active_flow": "dub_audio",
        "source_file_id": "source",
        "source_mime_type": "video/mp4",
        "source_media_type": "video",
        "video_duration": 1,
        "source_duration": 1,
        "target_language": "original",
        "subdub_final_confirmed": True,
        "_pipeline_workspace": str(tmp_path / "workspace"),
        **voice_state,
    }
    result = asyncio.run(
        bot._execute_video_dubbing_pipeline_core(
            Query(),
            SimpleNamespace(),
            state,
            "vi",
            admin_interactive_confirm=True,
        )
    )

    assert result["status"] == "AUTO_CAST_MANUAL_REQUIRED"
    assert route_calls[expected_route] == 1
    assert route_calls[{"auto": "manual", "manual": "auto"}[expected_route]] == 0
    assert prepare_flags == [expected_auto_prepare]
    assert asr_calls == ["asr"]
    assert dependency_checks
    assert all(all(check[1:]) for check in dependency_checks)


def test_default_blackbox_pcm_extractor_uses_bounded_existing_ffmpeg_runner(tmp_path, monkeypatch):
    source_path = tmp_path / "source.mp4"
    source_path.write_bytes(b"source")
    calls = []

    monkeypatch.setattr(bot, "subtitle_dub_workspace_path_safety", lambda _workspace: {"allowed": True})
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(
        bot.subdub_media_preflight,
        "timeout_for_stage",
        lambda *args, **kwargs: 77.0,
    )

    async def fake_run(command, timeout):
        calls.append((list(command), timeout))
        Path(command[-1]).write_bytes(b"\x00\x00" * 8_000)
        return True, "ok"

    monkeypatch.setattr(bot, "run_subdub_ffmpeg_command", fake_run)
    result = asyncio.run(
        bot._extract_subdub_auto_pcm(
            {
                "state": {
                    "_pipeline_workspace": str(tmp_path),
                    "_pipeline_saved_source_path": str(source_path),
                },
                "source_bytes": b"source",
                "content_type": "video/mp4",
                "duration_seconds": 12,
            },
            {},
            channels=1,
            sample_rate=16_000,
            sample_format="s16le",
        )
    )

    assert result == str(tmp_path / "auto_speaker_16000_mono_s16le.pcm")
    assert calls == [
        ([
            "ffmpeg", "-y", "-i", str(source_path), "-t", "12", "-vn", "-ac", "1",
            "-ar", "16000", "-f", "s16le",
            str(tmp_path / "auto_speaker_16000_mono_s16le.pcm"),
        ], 77.0)
    ]


@pytest.mark.parametrize("failure_kind", ("error", "cancel"))
def test_pcm_extractor_cleans_partial_output_on_runner_error_or_cancel(
    tmp_path,
    monkeypatch,
    failure_kind,
):
    source_path = tmp_path / "source.mp4"
    source_path.write_bytes(b"source")
    pcm_path = tmp_path / "auto_speaker_16000_mono_s16le.pcm"
    monkeypatch.setattr(bot, "subtitle_dub_workspace_path_safety", lambda _workspace: {"allowed": True})
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(bot.subdub_media_preflight, "timeout_for_stage", lambda *_args, **_kwargs: 1.0)

    async def fail_after_partial(command, timeout):
        del command, timeout
        pcm_path.write_bytes(b"partial")
        if failure_kind == "cancel":
            raise asyncio.CancelledError()
        raise RuntimeError("fixture failure")

    monkeypatch.setattr(bot, "run_subdub_ffmpeg_command", fail_after_partial)
    expected_error = asyncio.CancelledError if failure_kind == "cancel" else RuntimeError
    with pytest.raises(expected_error):
        asyncio.run(
            bot._extract_subdub_auto_pcm(
                {
                    "state": {
                        "_pipeline_workspace": str(tmp_path),
                        "_pipeline_saved_source_path": str(source_path),
                    },
                    "duration_seconds": 12,
                },
                {},
                channels=1,
                sample_rate=16_000,
                sample_format="s16le",
            )
        )
    assert not pcm_path.exists()


def test_pcm_extractor_caps_duration_and_rejects_oversized_output(tmp_path, monkeypatch):
    speaker_cast = _speaker_cast_module()
    source_path = tmp_path / "source.mp4"
    source_path.write_bytes(b"source")
    calls = []
    monkeypatch.setattr(bot, "subtitle_dub_workspace_path_safety", lambda _workspace: {"allowed": True})
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(bot.subdub_media_preflight, "timeout_for_stage", lambda *_args, **_kwargs: 1.0)

    async def no_output(command, timeout):
        calls.append((list(command), timeout))
        return False, "fixture"

    monkeypatch.setattr(bot, "run_subdub_ffmpeg_command", no_output)
    with pytest.raises(speaker_cast.AutoCastUnavailable):
        asyncio.run(
            bot._extract_subdub_auto_pcm(
                {
                    "state": {
                        "_pipeline_workspace": str(tmp_path),
                        "_pipeline_saved_source_path": str(source_path),
                    },
                    "duration_seconds": 99_999,
                },
                {},
                channels=1,
                sample_rate=16_000,
                sample_format="s16le",
            )
        )
    assert calls[0][0][calls[0][0].index("-t") + 1] == "1800"

    async def oversized(command, timeout):
        del timeout
        Path(command[-1]).write_bytes(b"x" * 32_001)
        return True, "fixture"

    monkeypatch.setattr(bot, "run_subdub_ffmpeg_command", oversized)
    with pytest.raises(speaker_cast.AutoCastUnavailable):
        asyncio.run(
            bot._extract_subdub_auto_pcm(
                {
                    "state": {
                        "_pipeline_workspace": str(tmp_path),
                        "_pipeline_saved_source_path": str(source_path),
                    },
                    "duration_seconds": 1,
                },
                {},
                channels=1,
                sample_rate=16_000,
                sample_format="s16le",
            )
        )
    assert not (tmp_path / "auto_speaker_16000_mono_s16le.pcm").exists()


def test_external_pcm_workspace_fails_before_source_write_or_ffmpeg(tmp_path, monkeypatch):
    speaker_cast = _speaker_cast_module()
    allowed_root = tmp_path / "allowed-root"
    external_workspace = tmp_path / "external-workspace"
    external_workspace.mkdir()
    source = external_workspace / "source.mp4"
    source.write_bytes(b"source")
    calls = {"write": 0, "ffmpeg_path": 0, "runner": 0}

    monkeypatch.setattr(bot, "PIPELINE_TEMP_ROOT", str(allowed_root))

    def forbidden_write(*_args, **_kwargs):
        calls["write"] += 1
        raise AssertionError("external workspace must fail before source write")

    def forbidden_ffmpeg_path():
        calls["ffmpeg_path"] += 1
        raise AssertionError("external workspace must fail before FFmpeg lookup")

    async def forbidden_runner(*_args, **_kwargs):
        calls["runner"] += 1
        raise AssertionError("external workspace must fail before FFmpeg runner")

    monkeypatch.setattr(bot, "write_subtitle_dub_pipeline_artifact", forbidden_write)
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", forbidden_ffmpeg_path)
    monkeypatch.setattr(bot, "run_subdub_ffmpeg_command", forbidden_runner)

    with pytest.raises(speaker_cast.AutoCastUnavailable):
        asyncio.run(
            bot._extract_subdub_auto_pcm(
                {
                    "state": {
                        "_pipeline_workspace": str(external_workspace),
                        "_pipeline_saved_source_path": str(source),
                    },
                    "source_bytes": b"source",
                    "duration_seconds": 1,
                },
                {},
                channels=1,
                sample_rate=16_000,
                sample_format="s16le",
            )
        )

    assert calls == {"write": 0, "ffmpeg_path": 0, "runner": 0}


def test_documented_voice_pools_support_sixteen_same_register_speakers(monkeypatch):
    speaker_cast = _speaker_cast_module()
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "ConfiguredMaleSentinel")
    monkeypatch.setattr(bot, "MINIMAX_DEFAULT_MALE_VOICE_ID", "LegacyMaleSentinel")
    monkeypatch.setattr(bot, "SHOPAIKEY_TTS_MALE_VOICE", "ShopMaleSentinel")
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "ConfiguredFemaleSentinel")
    monkeypatch.setattr(bot, "MINIMAX_DEFAULT_FEMALE_VOICE_ID", "LegacyFemaleSentinel")
    monkeypatch.setattr(bot, "SHOPAIKEY_TTS_FEMALE_VOICE", "ShopFemaleSentinel")
    pools = bot.subdub_auto_validated_voice_pools("key4u_minimax")
    assert pools == {
        "low": list(bot.SUBDUB_AUTO_DOCUMENTED_LOW_VOICE_IDS),
        "high": list(bot.SUBDUB_AUTO_DOCUMENTED_HIGH_VOICE_IDS),
    }
    assert len(set(pools["low"])) == 16
    assert len(set(pools["high"])) == 16
    assert not any("Sentinel" in voice_id for values in pools.values() for voice_id in values)

    labels = [f"chunk_00:speaker_{index}" for index in range(16)]
    for register in ("low", "high"):
        classifications = {
            label: {
                "speaker_id": label,
                "voice_register": register,
                "confidence": 0.99,
            }
            for label in labels
        }
        casts = speaker_cast.assign_stable_voices(
            classifications,
            speaker_order=labels,
            validated_pools=pools,
            assignment_seed="a" * 64,
        )
        assert len({item["voice_id"] for item in casts.values()}) == 16


def test_auto_job_key_isolated_from_byte_stable_manual_key(monkeypatch):
    monkeypatch.setattr(bot, "SUBTITLE_DUB_PIPELINE_JOBS", {})
    monkeypatch.setattr(bot, "persist_subtitle_dub_pipeline_job_snapshot", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(bot, "_prune_subtitle_dub_pipeline_jobs", lambda *_args, **_kwargs: None)
    state = {
        "source_file_unique_id": "source",
        "mode": "dub",
        "active_flow": "dub_audio",
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
    }

    monkeypatch.setattr(bot, "SUBDUB_AUTO_SPEAKER_ACTIVATION_ENABLED", True)
    auto_key = bot.subtitle_dub_pipeline_job_key(7, 8, state)
    assert auto_key == "7|8|source|dub_audio|auto_speaker"
    acquired, auto_job = bot.acquire_subtitle_dub_pipeline_job(auto_key, mode="dub")
    assert acquired is True
    bot.update_subtitle_dub_pipeline_job(
        auto_key,
        status="failed",
        terminal_state="failed_no_charge",
        charge_status="not_charged",
        charged_xu=0,
    )

    manual_state = bot.subdub_apply_voice_choice(
        state,
        "default_male",
        activation_enabled=True,
    )
    manual_key = bot.subtitle_dub_pipeline_job_key(7, 8, manual_state)
    assert manual_key == "7|8|source|dub_audio"
    assert manual_key != auto_key
    manual_acquired, manual_job = bot.acquire_subtitle_dub_pipeline_job(manual_key, mode="dub")
    assert manual_acquired is True
    assert manual_job["job_id"] != auto_job["job_id"]


@pytest.mark.parametrize(
    ("callback", "step", "mode", "active_flow", "expected_step", "expected_text"),
    (
        ("videodub|back_speed", "voice_speed", "dub", "dub_audio", "voice", "音声"),
        ("videodub|settings_back", "dubbing_output", "dub", "dub_audio", "voice", "音声"),
        ("videodub|back_confirm", "confirm", "dub", "dub_audio", "voice", "音声"),
        ("videodub|redub_voice", "completed", "dub", "dub_audio", "voice", "音声"),
        (
            "videodub|combo_redub_voice",
            "completed",
            "subtitle_plus_dub",
            "subtitle_plus_dub",
            "choosing_voice",
            "音声",
        ),
        ("videodub|retry_media", "completed", "dub", "dub_audio", "await_video", ""),
        (
            "videodub|retry_media",
            "completed",
            "subtitle_plus_dub",
            "subtitle_plus_dub",
            "waiting_media",
            "",
        ),
    ),
)
def test_navigation_callbacks_clear_auto_state(
    monkeypatch,
    callback,
    step,
    mode,
    active_flow,
    expected_step,
    expected_text,
):
    user_id = 97_100
    monkeypatch.setattr(bot, "SUBDUB_AUTO_SPEAKER_ACTIVATION_ENABLED", True)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "ja")
    bot.USER_PENDING[bot.video_dubbing_pending_key(user_id)] = {
        "pending_action": "video_dubbing",
        "step": step,
        "current_step": step,
        "mode": mode,
        "process_type": mode,
        "video_processing_mode": mode,
        "requested_mode": mode,
        "active_flow": active_flow,
        "source_file_id": "source",
        "target_language": "ja",
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "speaker_sidecar_path": "C:/job/speaker_cast.sidecar.json",
        "speaker_sidecar_sha256": "a" * 64,
        "auto_exact_receipt_version": "v1",
        "voice_speed": "1.0",
    }
    captured = {}

    async def safe_edit(_query, text, **kwargs):
        captured.update({"text": text, **kwargs})
        return captured

    monkeypatch.setattr(bot, "safe_edit_or_send", safe_edit)

    class Query:
        data = callback
        from_user = SimpleNamespace(id=user_id)
        message = SimpleNamespace(chat_id=user_id)

        async def answer(self):
            return None

    asyncio.run(
        bot.handle_video_dubbing_callback(
            SimpleNamespace(callback_query=Query()),
            SimpleNamespace(),
        )
    )

    recovered = bot.get_video_dubbing_pending(user_id)
    assert recovered["step"] == expected_step
    assert "voice_kind" not in recovered
    assert "voice_selection_mode" not in recovered
    assert not (set(bot.SUBDUB_AUTO_VOICE_FIELDS) & set(recovered))
    if expected_text:
        assert expected_text in str(captured.get("text") or "")
    bot.USER_PENDING.pop(bot.video_dubbing_pending_key(user_id), None)


@pytest.mark.parametrize(
    ("mode", "active_flow", "step"),
    (
        ("dub", "dub_audio", "voice"),
        ("subtitle_plus_dub", "subtitle_plus_dub", "choosing_voice"),
    ),
)
def test_closed_auto_callback_clears_stale_exact_pair_before_render(
    monkeypatch,
    mode,
    active_flow,
    step,
):
    user_id = 97_150
    monkeypatch.setattr(bot, "SUBDUB_AUTO_SPEAKER_ACTIVATION_ENABLED", False)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "ja")
    bot.USER_PENDING[bot.video_dubbing_pending_key(user_id)] = {
        "pending_action": "video_dubbing",
        "step": step,
        "current_step": step,
        "mode": mode,
        "process_type": mode,
        "video_processing_mode": mode,
        "requested_mode": mode,
        "active_flow": active_flow,
        "source_file_id": "source",
        "target_language": "ja",
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "speaker_sidecar_path": "C:/job/speaker_cast.sidecar.json",
        "speaker_sidecar_sha256": "a" * 64,
        "speaker_classifications": {"internal": True},
        "speaker_casts": {"internal": True},
        "per_cue_voice_assignments": [{"internal": True}],
        "auto_exact_receipt_version": "v1",
    }
    rendered = {}

    async def safe_edit(_query, text, **kwargs):
        rendered.update({"text": text, **kwargs})
        return rendered

    monkeypatch.setattr(bot, "safe_edit_or_send", safe_edit)

    class Query:
        data = "videodub|voice|auto_speaker_gender"
        from_user = SimpleNamespace(id=user_id)
        message = SimpleNamespace(chat_id=user_id)

        async def answer(self):
            return None

    asyncio.run(
        bot.handle_video_dubbing_callback(
            SimpleNamespace(callback_query=Query()),
            SimpleNamespace(),
        )
    )

    recovered = bot.get_video_dubbing_pending(user_id)
    assert recovered["step"] == step
    assert "voice_kind" not in recovered
    assert "voice_selection_mode" not in recovered
    assert not (set(bot.SUBDUB_AUTO_VOICE_FIELDS) & set(recovered))
    assert "videodub|voice|auto_speaker_gender" not in _task6_callbacks(
        rendered["reply_markup"]
    )
    bot.USER_PENDING.pop(bot.video_dubbing_pending_key(user_id), None)


@pytest.mark.parametrize(
    ("mode", "active_flow", "expected_step"),
    (
        ("dub", "dub_audio", "voice"),
        ("subtitle_plus_dub", "subtitle_plus_dub", "choosing_voice"),
    ),
)
def test_manual_failure_mapping_clears_auto_mirror_and_returns_same_lane_native_screen(
    monkeypatch,
    mode,
    active_flow,
    expected_step,
):
    user_id = 97_001
    bot.USER_PENDING.pop(bot.video_dubbing_pending_key(user_id), None)
    monkeypatch.setattr(bot, "SUBDUB_AUTO_SPEAKER_ACTIVATION_ENABLED", True)
    state = {
        "pending_action": "video_dubbing",
        "mode": mode,
        "process_type": mode,
        "video_processing_mode": mode,
        "active_flow": active_flow,
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "speaker_sidecar_path": "C:/job/speaker_cast.sidecar.json",
        "speaker_sidecar_sha256": "a" * 64,
        "speaker_classifications": {"internal": True},
        "speaker_casts": {"internal": True},
        "per_cue_voice_assignments": [{"internal": True}],
        "auto_exact_receipt_version": "v1",
        "unrelated": "keep",
    }
    bot.USER_PENDING[bot.video_dubbing_pending_key(user_id)] = dict(state)

    result = bot.subdub_auto_manual_required_recovery(
        user_id,
        state,
        mode=mode,
        lang="ja",
    )

    assert result["status"] == "AUTO_CAST_MANUAL_REQUIRED"
    assert result["public_copy_key"] == "voice_auto_manual_required"
    assert "音声を手動で選択してください" in result["text"]
    assert result["state"]["step"] == expected_step
    assert result["state"]["unrelated"] == "keep"
    assert not (set(bot.SUBDUB_AUTO_VOICE_FIELDS) & set(result["state"]))
    assert "voice_kind" not in result["state"]
    assert "voice_selection_mode" not in result["state"]
    assert "videodub|voice|auto_speaker_gender" not in _task6_callbacks(result["reply_markup"])
    bot.USER_PENDING.pop(bot.video_dubbing_pending_key(user_id), None)


def test_combo_full_dub_confirms_auto_before_pipeline_and_recovers_to_manual(monkeypatch):
    user_id = 97_200
    monkeypatch.setattr(bot, "SUBDUB_AUTO_SPEAKER_ACTIVATION_ENABLED", True)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "ja")
    bot.USER_PENDING[bot.video_dubbing_pending_key(user_id)] = {
        "pending_action": "video_dubbing",
        "step": "dub_confirmation",
        "current_step": "dub_confirmation",
        "mode": "subtitle_plus_dub",
        "process_type": "subtitle_plus_dub",
        "video_processing_mode": "subtitle_plus_dub",
        "requested_mode": "subtitle_plus_dub",
        "active_flow": "subtitle_plus_dub",
        "source_file_id": "source",
        "target_language": "ja",
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "voice_speed": "1.0",
        "processing": "0",
    }
    pipeline_states = []
    rendered = []

    async def fake_full(_query, _context, state, _lang):
        pipeline_states.append(dict(state))
        return {
            "ok": False,
            "status": "AUTO_CAST_MANUAL_REQUIRED",
            "state": dict(state),
        }

    async def safe_edit(_query, text, **kwargs):
        rendered.append({"text": text, **kwargs})
        return rendered[-1]

    monkeypatch.setattr(bot, "execute_subtitle_plus_dub_full_from_callback", fake_full)
    monkeypatch.setattr(bot, "safe_edit_or_send", safe_edit)

    class Message:
        chat_id = user_id

        async def reply_text(self, text, **kwargs):
            rendered.append({"text": text, **kwargs})
            return rendered[-1]

    class Query:
        data = "videodub|combo_full_dub"
        from_user = SimpleNamespace(id=user_id)
        message = Message()

        async def answer(self):
            return None

    asyncio.run(
        bot.handle_video_dubbing_callback(
            SimpleNamespace(callback_query=Query()),
            SimpleNamespace(),
        )
    )

    assert len(pipeline_states) == 1
    confirmed = pipeline_states[0]
    assert bot.subdub_final_confirmed_state(confirmed) is True
    assert confirmed["subdub_confirmation_source"] == "videodub|combo_full_dub"
    assert bot.subdub_auto_speaker_route_enabled(confirmed) is True
    recovered = bot.get_video_dubbing_pending(user_id)
    assert recovered["step"] == "choosing_voice"
    assert "voice_kind" not in recovered
    assert "voice_selection_mode" not in recovered
    for field in (
        "subdub_final_confirmed",
        "subdub_confirmation_source",
        "subdub_confirmed_at_ts",
        "pending_video_action",
    ):
        assert field not in recovered
    manual = bot.subdub_apply_voice_choice(
        recovered,
        "default_female",
        lang="ja",
        activation_enabled=False,
    )
    assert manual is not None
    assert bot.subdub_final_confirmed_state(manual) is False
    assert "videodub|voice|auto_speaker_gender" not in _task6_callbacks(
        rendered[-1]["reply_markup"]
    )
    assert "音声を手動で選択してください" in rendered[-1]["text"]
    bot.USER_PENDING.pop(bot.video_dubbing_pending_key(user_id), None)


def test_combo_full_dub_manual_callback_does_not_add_auto_confirmation(monkeypatch):
    user_id = 97_201
    monkeypatch.setattr(bot, "SUBDUB_AUTO_SPEAKER_ACTIVATION_ENABLED", False)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    bot.USER_PENDING[bot.video_dubbing_pending_key(user_id)] = {
        "pending_action": "video_dubbing",
        "step": "dub_confirmation",
        "current_step": "dub_confirmation",
        "mode": "subtitle_plus_dub",
        "process_type": "subtitle_plus_dub",
        "video_processing_mode": "subtitle_plus_dub",
        "requested_mode": "subtitle_plus_dub",
        "active_flow": "subtitle_plus_dub",
        "source_file_id": "source",
        "target_language": "vi",
        "voice_kind": "default_female",
        "voice_style": "Giọng nữ mặc định",
        "voice_speed": "1.0",
        "processing": "0",
    }
    pipeline_states = []
    engine_calls = []
    rendered = []

    async def fake_pipeline(
        _query,
        _context,
        state,
        _lang,
        *,
        admin_interactive_confirm=False,
    ):
        pipeline_states.append(
            {
                "state": dict(state),
                "admin_interactive_confirm": bool(admin_interactive_confirm),
            }
        )
        return {
            "ok": True,
            "has_subtitle": True,
            "has_audio": True,
            "has_video": True,
        }

    async def fake_engine(feature, payload, engine_context):
        engine_calls.append(
            {
                "feature": feature,
                "payload": dict(payload),
                "context": dict(engine_context),
            }
        )
        runner_result = await payload["runner"]()
        return {"ok": True, "runner_result": runner_result}

    async def safe_edit(_query, text, **kwargs):
        rendered.append({"text": text, **kwargs})
        return rendered[-1]

    monkeypatch.setattr(bot, "execute_video_dubbing_pipeline", fake_pipeline)
    monkeypatch.setattr(bot, "execute_engine", fake_engine)
    monkeypatch.setattr(bot, "safe_edit_or_send", safe_edit)

    class Message:
        chat_id = user_id

        async def reply_text(self, text, **kwargs):
            rendered.append({"text": text, **kwargs})
            return rendered[-1]

    class Query:
        data = "videodub|combo_full_dub"
        from_user = SimpleNamespace(id=user_id)
        message = Message()

        async def answer(self):
            return None

    asyncio.run(
        bot.handle_video_dubbing_callback(
            SimpleNamespace(callback_query=Query()),
            SimpleNamespace(),
        )
    )

    assert len(engine_calls) == 1
    assert engine_calls[0]["feature"] == "subtitle_plus_dub"
    assert engine_calls[0]["context"] == {
        "user_id": user_id,
        "entry_source": bot.ENGINE_ENTRY_SOURCE_PRODUCT,
        "confirm_paid": True,
        "admin_interactive_confirm": True,
        "is_paid_job": True,
    }
    assert callable(engine_calls[0]["payload"]["runner"])
    assert engine_calls[0]["payload"]["mode"] == "subtitle_plus_dub"
    assert len(pipeline_states) == 1
    assert pipeline_states[0]["admin_interactive_confirm"] is True
    manual_state = pipeline_states[0]["state"]
    assert manual_state["voice_kind"] == "default_female"
    assert manual_state["voice_style"] == "Giọng nữ mặc định"
    assert "subdub_final_confirmed" not in manual_state
    assert "subdub_confirmation_source" not in manual_state
    assert "subdub_confirmed_at_ts" not in manual_state
    assert "pending_video_action" not in manual_state
    bot.USER_PENDING.pop(bot.video_dubbing_pending_key(user_id), None)


def test_task7_auto_route_and_exact_receipt_callbacks_are_atomically_enabled():
    assert bot.SUBDUB_AUTO_SPEAKER_ACTIVATION_ENABLED is True
    state = {
        "mode": "dub",
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
    }
    callbacks = _task6_callbacks(bot.video_dubbing_voice_keyboard("en", state))
    assert "videodub|voice|auto_speaker_gender" in callbacks
    _label, auto_callback = bot.subdub_auto_voice_choice("en")
    assert auto_callback == "videodub|voice|auto_speaker_gender"
    receipt_callbacks = _task6_callbacks(
        bot.subdub_auto_exact_confirmation_keyboard(_task7_durable_job(), "en")
    )
    assert any(item.startswith("videodub|auto_exact_confirm|") for item in receipt_callbacks)
    assert any(item.startswith("videodub|auto_exact_cancel|") for item in receipt_callbacks)


def _task7_pause_fixture(
    workspace: Path,
    *,
    job_id: str = "task7-job-001",
    job_key: str = "97100|97100|source|dub_audio|auto_speaker",
    user_id: int = 97_100,
    chat_id: int = 97_100,
):
    speaker_cast = _speaker_cast_module()
    workspace.mkdir(parents=True, exist_ok=True)
    source_bytes = b"task7-source-media"
    source_path = workspace / "source.mp4"
    source_path.write_bytes(source_bytes)
    source_srt = (
        "1\n00:00:00,000 --> 00:00:01,000\nhello world\n"
    )
    source_segments = bot.subdub_canonical_cues.canonicalize_segments(
        bot.video_dubbing_segments_from_subtitle(source_srt),
        extraction_source="cached_auto_exact_receipt",
        source_language="auto",
    )
    sidecar = speaker_cast.build_sidecar(
        [
            {
                **source_segments[0],
                "speaker": 0,
                "speaker_id": "chunk_00:speaker_0",
                "speaker_confidence": 0.99,
            }
        ],
        media_sha256=hashlib.sha256(source_bytes).hexdigest(),
        subtitle_sha256=bot.subdub_speaker_sidecar_subtitle_sha256(source_srt),
    )
    sidecar_receipt = speaker_cast.persist_sidecar(
        sidecar,
        workspace=str(workspace),
    )
    state = {
        "mode": "dub",
        "process_type": "dub",
        "video_processing_mode": "dub",
        "active_flow": "dub_audio",
        "source_file_id": "source",
        "source_mime_type": "video/mp4",
        "target_language": "original",
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "auto_quote_version": bot.SUBDUB_AUTO_EXACT_QUOTE_VERSION,
        "auto_quote_exact_known": False,
        "auto_quote_billable_words": None,
        "auto_exact_session_nonce": "nonce12345678",
        "speaker_sidecar_path": sidecar_receipt["path"],
        "speaker_sidecar_sha256": sidecar_receipt["sha256"],
        "_pipeline_workspace": str(workspace),
        "_pipeline_saved_source_path": str(source_path),
        "_pipeline_job_id": job_id,
        "_pipeline_job_key": job_key,
        "_pipeline_owner_user_id": str(user_id),
        "_pipeline_chat_id": str(chat_id),
        "_pipeline_is_admin": True,
    }
    prepared = {
        "state": dict(state),
        "source_bytes": source_bytes,
        "content_type": "video/mp4",
        "source_subtitle": source_srt,
        "source_segments": source_segments,
        "source_script": "hello world",
        "output_subtitle": source_srt,
        "output_segments": source_segments,
        "output_script": "hello world",
    }
    return state, prepared


def _task7_durable_job(
    *,
    job_id: str = "task7-job-001",
    job_key: str = "97100|97100|source|dub_audio|auto_speaker",
    user_id: int = 97_100,
    chat_id: int = 97_100,
):
    receipt = {
        "version": bot.SUBDUB_AUTO_EXACT_RECEIPT_VERSION,
        "quote_version": bot.SUBDUB_AUTO_EXACT_QUOTE_VERSION,
        "internal_job_id": job_id,
        "job_key_sha256": hashlib.sha256(job_key.encode("utf-8")).hexdigest(),
        "session_nonce": "nonce12345678",
        "owner_user_id": str(user_id),
        "chat_id": str(chat_id),
        "mode": "dub",
        "source_sha256": "1" * 64,
        "media_sha256": "1" * 64,
        "subtitle_sha256": "2" * 64,
        "selected_tts_text_sha256": "3" * 64,
        "translated_selected_text_sha256": "",
        "sidecar_sha256": "4" * 64,
        "timeline_signature": "5" * 64,
        "actual_billable_words": 2,
        "actual_auto_xu": 1,
        "actual_subtitle_xu": 0,
        "actual_total_xu": 1,
        "expires_at": time.time() + 3_600,
        "consumed": False,
        "claim_state": "unconsumed",
    }
    return {
        "feature": "subtitle_dub",
        "internal_job_id": job_id,
        "job_id": job_id,
        "job_key": job_key,
        "public_code": "AUTO1234",
        "user_id": str(user_id),
        "chat_id": str(chat_id),
        "mode": "dub",
        "mapped_mode": "dub",
        "status": "awaiting_auto_exact_confirmation",
        "terminal_state": "",
        "charge_status": "not_charged",
        "auto_exact_receipt": receipt,
    }


def _task7_seed_sqlite_job(tmp_path: Path, job: dict) -> Path:
    db_path = tmp_path / f"{job['internal_job_id']}.sqlite3"
    conn = bot.sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """CREATE TABLE system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            note TEXT,
            updated_at TEXT,
            updated_by TEXT
            )"""
        )
        conn.execute(
            "INSERT INTO system_settings(key, value, note, updated_at, updated_by) VALUES (?, ?, '', '', '')",
            (
                bot._engine_async_job_key(job["internal_job_id"]),
                json.dumps(job, ensure_ascii=False, separators=(",", ":")),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


@pytest.mark.parametrize("persist_success", (True, False), ids=("persisted", "persist-failed"))
def test_task7_durable_receipt_pause_is_persisted_nonterminal_before_generic_failure(
    monkeypatch,
    tmp_path,
    persist_success,
):
    user_id = 97_100
    chat_id = 97_100
    job_id = "task7-pause-job"
    job_key = "task7-pause-key"
    workspace = tmp_path / "workspace"
    state, prepared = _task7_pause_fixture(
        workspace,
        job_id=job_id,
        job_key=job_key,
        user_id=user_id,
        chat_id=chat_id,
    )
    job = {
        "job_id": job_id,
        "internal_job_id": job_id,
        "job_key": job_key,
        "user_id": str(user_id),
        "chat_id": str(chat_id),
        "mode": "dub",
        "status": "running",
        "terminal_state": "",
        "charge_status": "not_charged",
        "progress_percent": 0,
    }
    persisted = []
    monkeypatch.setattr(bot, "SUBDUB_AUTO_SPEAKER_ACTIVATION_ENABLED", True)
    monkeypatch.setattr(bot, "SUBTITLE_DUB_PIPELINE_JOBS", {job_key: dict(job)})
    monkeypatch.setattr(bot, "subtitle_dub_pipeline_job_key", lambda *_args, **_kwargs: job_key)
    monkeypatch.setattr(
        bot,
        "acquire_subtitle_dub_pipeline_job",
        lambda *_args, **_kwargs: (True, dict(job)),
    )
    monkeypatch.setattr(
        bot.subdub_blackboxes,
        "normalize_standalone_video_lane_entry_state",
        lambda value: dict(value),
    )
    monkeypatch.setattr(
        bot,
        "create_subtitle_dub_pipeline_workspace",
        lambda *_args, **_kwargs: str(workspace),
    )
    monkeypatch.setattr(
        bot,
        "subtitle_dub_workspace_path_safety",
        lambda _workspace: {"allowed": True},
    )

    async def no_progress(*_args, **_kwargs):
        return None

    async def pause_core(_query, _context, pipeline_state, _lang, **_kwargs):
        pipeline_state.update(state)
        prepared["state"] = dict(pipeline_state)
        control = await bot._subdub_auto_post_prepare_gate(prepared, pipeline_state)
        return {**control, "state": pipeline_state}

    def capture_persist(key, snapshot=None, *, reason=""):
        persisted.append((key, copy.deepcopy(snapshot or {}), reason))
        if str((snapshot or {}).get("status") or "") == "awaiting_auto_exact_confirmation":
            return persist_success
        return True

    monkeypatch.setattr(bot, "subdub_send_progress_update", no_progress)
    monkeypatch.setattr(bot, "_execute_video_dubbing_pipeline_core", pause_core)
    monkeypatch.setattr(bot, "persist_subtitle_dub_pipeline_job_snapshot", capture_persist)

    query = SimpleNamespace(
        from_user=SimpleNamespace(id=user_id),
        message=SimpleNamespace(chat_id=chat_id),
    )
    result = asyncio.run(
        bot.execute_video_dubbing_pipeline(
            query,
            SimpleNamespace(),
            state,
            "vi",
            admin_interactive_confirm=True,
        )
    )

    paused = persisted[-1][1]
    receipt = paused["auto_exact_receipt"]
    if not persist_success:
        assert result.get("status") != "AUTO_EXACT_CONFIRMATION_REQUIRED"
        assert result.get("resume_required") is not True
        return
    expected_receipt_fields = {
        "version",
        "quote_version",
        "internal_job_id",
        "job_key_sha256",
        "session_nonce",
        "owner_user_id",
        "chat_id",
        "mode",
        "source_sha256",
        "media_sha256",
        "subtitle_sha256",
        "selected_tts_text_sha256",
        "translated_selected_text_sha256",
        "sidecar_sha256",
        "timeline_signature",
        "actual_billable_words",
        "actual_auto_xu",
        "actual_subtitle_xu",
        "actual_total_xu",
        "expires_at",
        "consumed",
        "claim_state",
    }
    assert result["status"] == "AUTO_EXACT_CONFIRMATION_REQUIRED"
    assert paused["status"] == "awaiting_auto_exact_confirmation"
    assert paused["terminal_state"] == ""
    assert paused["charge_status"] == "not_charged"
    assert paused["workspace"] == str(workspace)
    assert bot.is_workspace_active_status(paused["status"]) is True
    assert set(receipt) == expected_receipt_fields
    assert not (
        {
            "prepared",
            "segments",
            "speaker_casts",
            "per_cue_voice_assignments",
            "provider_payload",
            "credentials",
            "wallet",
        }
        & set(receipt)
    )


def test_task7_exact_known_quote_still_persists_consumed_auto_receipt(
    monkeypatch,
    tmp_path,
):
    workspace = tmp_path / "exact-known-workspace"
    state, prepared = _task7_pause_fixture(workspace, job_id="task7-exact-known")
    state.update({
        "auto_quote_exact_known": True,
        "auto_quote_billable_words": 2,
        "auto_quote_total_xu": 1,
    })
    updates = []
    persisted = []

    def capture_update(job_key, **fields):
        current = {
            "feature": "subtitle_dub",
            "internal_job_id": state["_pipeline_job_id"],
            "job_id": state["_pipeline_job_id"],
            "job_key": job_key,
            "user_id": state["_pipeline_owner_user_id"],
            "chat_id": state["_pipeline_chat_id"],
            "mode": "dub",
            **fields,
        }
        updates.append(current)
        return current

    def capture_persist(job_key, snapshot=None, *, reason=""):
        persisted.append((job_key, copy.deepcopy(snapshot or {}), reason))
        return True

    monkeypatch.setattr(bot, "update_subtitle_dub_pipeline_job", capture_update)
    monkeypatch.setattr(
        bot,
        "persist_subtitle_dub_pipeline_job_snapshot",
        capture_persist,
    )

    result = asyncio.run(bot._subdub_auto_post_prepare_gate(prepared, state))

    receipt = dict(state.get("auto_exact_receipt") or {})
    assert result == {"continue": True}
    assert receipt["consumed"] is True
    assert receipt["claim_state"] == "resuming"
    assert receipt["claim_token"]
    assert state["auto_exact_receipt_confirmed"] is True
    assert updates[-1]["voice_kind"] == "auto_speaker_gender"
    assert updates[-1]["voice_selection_mode"] == "auto_speaker"
    assert persisted[-1][2] == "auto_exact_known_receipt_claimed"


def test_task7_cached_prepare_restart_resume_has_zero_asr_and_translation(
    monkeypatch,
    tmp_path,
):
    workspace = tmp_path / "workspace"
    state, prepared = _task7_pause_fixture(workspace)
    monkeypatch.setattr(
        bot,
        "subtitle_dub_workspace_path_safety",
        lambda _workspace: {"allowed": True},
    )
    pause = asyncio.run(bot._subdub_auto_post_prepare_gate(prepared, state))
    assert pause["status"] == "AUTO_EXACT_CONFIRMATION_REQUIRED"
    claimed_receipt = {
        **pause["receipt"],
        "consumed": True,
        "claim_state": "resuming",
        "claimed_at": time.time(),
        "claim_token": "claimtoken123456",
    }
    resume_state = {
        **state,
        "auto_exact_resume": True,
        "auto_exact_receipt": claimed_receipt,
        "auto_exact_cache": dict(state["auto_exact_cache"]),
    }
    job = {
        **_task7_durable_job(),
        "workspace": str(workspace),
        "auto_exact_receipt": claimed_receipt,
        "auto_exact_cache": dict(state["auto_exact_cache"]),
    }
    calls = {"asr": 0, "translation": 0}

    async def forbidden_asr(*_args, **_kwargs):
        calls["asr"] += 1
        raise AssertionError("durable resume must not call ASR")

    async def forbidden_translation(*_args, **_kwargs):
        calls["translation"] += 1
        raise AssertionError("durable resume must not call translation")

    monkeypatch.setattr(bot, "video_dubbing_prepare_subtitles", forbidden_asr)
    monkeypatch.setattr(bot, "translate_subtitle_text", forbidden_translation)

    cached = bot._subdub_auto_load_cached_prepared(job, resume_state)
    gate = asyncio.run(bot._subdub_auto_post_prepare_gate(cached, resume_state))

    assert calls == {"asr": 0, "translation": 0}
    assert gate == {"continue": True}
    assert cached["source_bytes"] == b"task7-source-media"
    assert cached["asr_provider"] == "cached_auto_exact_receipt"
    assert cached["translation_provider"] == ""
    assert cached["source_segments"][0]["speaker_id"] == "chunk_00:speaker_0"
    for field, expected in (
        ("auto_exact_actual_billable_words", 2),
        ("auto_exact_actual_auto_xu", 1),
        ("auto_exact_actual_subtitle_xu", 0),
        ("auto_exact_actual_total_xu", 1),
        ("auto_exact_receipt_confirmed", True),
    ):
        assert resume_state[field] == expected
        assert cached["state"][field] == expected


def test_task7_cached_prepare_exception_after_cas_fails_closed_terminal(
    monkeypatch,
    tmp_path,
):
    job = _task7_durable_job(job_id="task7-broken-cache-job")
    receipt = {
        **job["auto_exact_receipt"],
        "consumed": True,
        "claim_state": "resuming",
        "claim_token": "claimtoken123456",
    }
    job.update({
        "status": "resuming_auto_exact_confirmation",
        "workspace": str(tmp_path / "missing-cache-workspace"),
        "auto_exact_receipt": receipt,
        "auto_exact_resume_state": {
            "mode": "dub",
            "voice_kind": "auto_speaker_gender",
            "voice_selection_mode": "auto_speaker",
        },
    })
    updates = []

    def broken_cache(*_args, **_kwargs):
        raise _speaker_cast_module().AutoCastUnavailable()

    def capture_update(key, **fields):
        current = {**job, **fields, "job_key": key}
        updates.append(current)
        return current

    def forbidden_wallet(*_args, **_kwargs):
        raise AssertionError("invalid cached resume must not touch the wallet")

    monkeypatch.setattr(
        bot.subdub_blackboxes,
        "normalize_standalone_video_lane_entry_state",
        lambda value: dict(value),
    )
    monkeypatch.setattr(bot, "_subdub_auto_load_cached_prepared", broken_cache)
    monkeypatch.setattr(bot, "update_subtitle_dub_pipeline_job", capture_update)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", forbidden_wallet)
    monkeypatch.setattr(bot, "refund_charged_credit", forbidden_wallet)

    query = SimpleNamespace(
        from_user=SimpleNamespace(id=97_100),
        message=SimpleNamespace(chat_id=97_100),
    )
    result = asyncio.run(
        bot.execute_video_dubbing_pipeline(
            query,
            SimpleNamespace(),
            job["auto_exact_resume_state"],
            "vi",
            admin_interactive_confirm=True,
            resume_job=job,
        )
    )

    assert result["ok"] is False
    assert updates
    assert updates[-1]["terminal_state"] == "failed_no_charge"
    assert updates[-1]["charge_status"] == "not_charged"
    assert updates[-1].get("charged_xu") == 0


def test_task7_sqlite_concurrent_confirm_cancel_has_exactly_one_cas_winner(
    monkeypatch,
    tmp_path,
):
    job = _task7_durable_job(job_id="task7-race-job")
    db_path = _task7_seed_sqlite_job(tmp_path, job)
    monkeypatch.setattr(
        bot,
        "db_connect",
        lambda: bot.sqlite3.connect(str(db_path), timeout=5.0),
    )
    monkeypatch.setattr(bot, "ENGINE_ASYNC_MEMORY_JOBS", {})
    barrier = threading.Barrier(3)
    outcomes = []
    errors = []

    def compete(cancel):
        try:
            barrier.wait(timeout=5.0)
            claimed, current = bot._subdub_auto_engine_job_cas(
                job["internal_job_id"],
                user_id=job["user_id"],
                chat_id=job["chat_id"],
                session_nonce=job["auto_exact_receipt"]["session_nonce"],
                cancel=cancel,
            )
            outcomes.append((cancel, claimed, current))
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=compete, args=(False,)),
        threading.Thread(target=compete, args=(True,)),
    ]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=5.0)
    for thread in threads:
        thread.join(timeout=7.0)

    assert not errors
    assert not any(thread.is_alive() for thread in threads)
    assert len(outcomes) == 2
    assert sum(1 for _cancel, claimed, _current in outcomes if claimed) == 1
    conn = bot.sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT value FROM system_settings WHERE key=?",
            (bot._engine_async_job_key(job["internal_job_id"]),),
        ).fetchone()
    finally:
        conn.close()
    durable = json.loads(row[0])
    assert durable["auto_exact_receipt"]["consumed"] is True
    assert durable["auto_exact_receipt"]["claim_state"] in {"resuming", "cancelled"}


@pytest.mark.parametrize(
    "case",
    ("missing", "stale", "expired", "mismatched-job-key"),
)
def test_task7_missing_stale_expired_or_mismatched_receipt_fails_closed(case):
    job = _task7_durable_job()
    receipt = dict(job["auto_exact_receipt"])
    if case == "missing":
        job.pop("auto_exact_receipt")
    elif case == "stale":
        receipt["version"] = "stale-version"
        job["auto_exact_receipt"] = receipt
    elif case == "expired":
        receipt["expires_at"] = time.time() - 1
        job["auto_exact_receipt"] = receipt
    else:
        receipt["job_key_sha256"] = "0" * 64
        job["auto_exact_receipt"] = receipt

    assert bot._subdub_auto_receipt_transition_matches(
        job,
        user_id=job["user_id"],
        chat_id=job["chat_id"],
        session_nonce="nonce12345678",
    ) is False


def test_task7_cancel_receipt_is_terminal_and_explicitly_zero_charge(
    monkeypatch,
    tmp_path,
):
    job = _task7_durable_job(job_id="task7-cancel-job")
    db_path = _task7_seed_sqlite_job(tmp_path, job)
    monkeypatch.setattr(
        bot,
        "db_connect",
        lambda: bot.sqlite3.connect(str(db_path), timeout=5.0),
    )
    monkeypatch.setattr(bot, "ENGINE_ASYNC_MEMORY_JOBS", {})

    def forbidden_wallet(*_args, **_kwargs):
        raise AssertionError("cancel must not mutate the wallet")

    monkeypatch.setattr(bot, "spend_fixed_credit_info", forbidden_wallet)
    monkeypatch.setattr(bot, "refund_charged_credit", forbidden_wallet)

    transitioned, cancelled = bot._subdub_auto_engine_job_cas(
        job["internal_job_id"],
        user_id=job["user_id"],
        chat_id=job["chat_id"],
        session_nonce=job["auto_exact_receipt"]["session_nonce"],
        cancel=True,
    )

    assert transitioned is True
    assert cancelled["status"] == "failed_no_charge"
    assert cancelled["terminal_state"] == "failed_no_charge"
    assert cancelled["charge_status"] == "not_charged"
    assert cancelled.get("charged_xu") == 0
    assert cancelled["auto_exact_receipt"]["claim_state"] == "cancelled"
    assert cancelled["auto_exact_receipt"]["consumed"] is True


def test_task7_status_read_only_refresh_has_zero_claim_or_charge(monkeypatch):
    job = _task7_durable_job(job_id="task7-status-job")
    side_effects = []
    rendered = {}
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "get_video_dubbing_pending", lambda _uid: {})
    monkeypatch.setattr(bot, "subdub_progress_job_for_user", lambda *_args: dict(job))

    def forbidden_sync(name):
        def fail(*_args, **_kwargs):
            side_effects.append(name)
            raise AssertionError(f"status refresh must not call {name}")

        return fail

    def forbidden_async(name):
        async def fail(*_args, **_kwargs):
            side_effects.append(name)
            raise AssertionError(f"status refresh must not call {name}")

        return fail

    async def safe_edit(_query, text, **kwargs):
        rendered.update({"text": text, **kwargs})
        return rendered

    monkeypatch.setattr(bot, "_subdub_auto_read_balance_xu", forbidden_sync("balance"))
    monkeypatch.setattr(bot, "spend_fixed_credit_info", forbidden_sync("spend"))
    monkeypatch.setattr(bot, "refund_charged_credit", forbidden_sync("refund"))
    monkeypatch.setattr(bot, "_subdub_auto_exact_transition", forbidden_async("claim"))
    monkeypatch.setattr(bot, "video_dubbing_prepare_subtitles", forbidden_async("asr"))
    monkeypatch.setattr(bot, "translate_subtitle_text", forbidden_async("translation"))
    monkeypatch.setattr(
        bot.auto_speaker,
        "run_auto_speaker_blackbox",
        forbidden_async("classifier"),
    )
    monkeypatch.setattr(bot, "execute_video_dubbing_pipeline", forbidden_async("render"))
    monkeypatch.setattr(
        bot,
        "send_public_subtitle_dub_final_outputs",
        forbidden_async("delivery"),
    )
    monkeypatch.setattr(bot, "safe_edit_or_send", safe_edit)

    class Query:
        data = "videodub|subdub_status|AUTO1234"
        from_user = SimpleNamespace(id=97_100)
        message = SimpleNamespace(chat_id=97_100)

        async def answer(self):
            return None

    asyncio.run(
        bot.handle_video_dubbing_callback(
            SimpleNamespace(callback_query=Query()),
            SimpleNamespace(),
        )
    )

    assert side_effects == []
    assert rendered["text"] == bot.subdub_auto_exact_confirmation_text(job, "vi")


def test_task7_one_shot_settlement_source_contract_is_after_durable_delivery():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    validation_at = source.index(
        "canonical_validation = await subdub_validate_video_output("
    )
    pricing_at = source.index(
        "auto_pricing_active = auto_speaker.is_auto_speaker_state(state)"
    )
    auto_defer_at = source.index(
        "if auto_pricing_active:\n        charged = 0", pricing_at
    )
    manual_charge_at = source.index("charge = spend_fixed_credit_info(", auto_defer_at)
    delivery_at = source.index(
        "delivery = await send_public_subtitle_dub_final_outputs("
    )
    durable_delivery_at = source.index(
        "mark_subtitle_dub_pipeline_output_sent(", delivery_at
    )
    settlement_at = source.index(
        "subdub_auto_settlement.settle_after_delivery(", durable_delivery_at
    )

    assert validation_at < pricing_at < auto_defer_at < manual_charge_at < delivery_at
    assert delivery_at < durable_delivery_at < settlement_at
    assert source.count("subdub_auto_settlement.settle_after_delivery(") == 1
    assert "apply_member_discount_flag=False" not in source[auto_defer_at:delivery_at]


@pytest.mark.parametrize(
    "partial_pair",
    (
        {"voice_kind": "auto_speaker_gender"},
        {"voice_selection_mode": "auto_speaker"},
    ),
)
def test_task7_manual_mode_partial_pair_with_stale_receipt_remains_manual(
    monkeypatch,
    partial_pair,
):
    monkeypatch.setattr(bot, "SUBDUB_AUTO_SPEAKER_ACTIVATION_ENABLED", True)
    state = {
        "mode": "dub",
        "video_processing_mode": "dub",
        "billing_chars": 1_250,
        "auto_quote_billable_words": 2,
        "auto_quote_auto_xu": 1,
        "auto_quote_total_xu": 1,
        "auto_exact_receipt": _task7_durable_job()["auto_exact_receipt"],
        **partial_pair,
    }
    manual_invoice = bot._video_dubbing_manual_invoice_breakdown(state)

    assert bot.subdub_auto_speaker_route_enabled(state) is False
    assert bot.subdub_auto_quote_fields(97_100, state) == {}
    assert bot.video_dubbing_invoice_breakdown(state) == manual_invoice


def test_task7_public_pricing_copy_discloses_auto_word_rate_and_tiers():
    text = bot.video_dubbing_pricing_text("vi")

    assert all(fragment in text for fragment in ("0.5 Xu/từ", "1.000", "10.000"))
