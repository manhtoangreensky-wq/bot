from __future__ import annotations

import asyncio
from pathlib import Path

import bot
from services import subdub_multi_speaker_gender_onnx
from services import subdub_speaker_cast as speaker_cast
from services.subdub_blackboxes import auto_smart_multivoice as smart


def _prepared_segments() -> list[dict]:
    rows = []
    for index, register in enumerate(("high", "low", "low")):
        rows.append(
            {
                "cue_id": f"cue-{index}",
                "speaker_id": f"chunk_00:speaker_{index}",
                "voice_register": register,
                "text": f"line {index}",
                "start": float(index),
                "end": float(index + 1),
            }
        )
    return rows


def test_smart_blackbox_reuses_prepared_auto_multi_acoustic_registers(
    tmp_path,
    monkeypatch,
):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    pcm = tmp_path / "source.pcm"
    pcm.write_bytes(b"\x01\x00\x01\x00" * (44_100 * 3))
    segments = _prepared_segments()
    captured: dict = {}

    async def prepare(_state, require_auto_cast=False):
        assert require_auto_cast is True
        return {
            "state": {},
            "source_file": str(source),
            "source_segments": [dict(item) for item in segments],
            "output_segments": [dict(item) for item in segments],
        }

    async def capture_runner(**kwargs):
        captured.update(kwargs)
        return {
                "ok": True,
                "strategy": smart.STRATEGY_GENERIC_MULTI,
            "detected_speaker_count": 3,
                "effective_speaker_count": 3,
                "effective_voice_count": 3,
                "speaker_voice_map": {"speaker_0": "v1", "speaker_1": "v2", "speaker_2": "v3"},
            "fallback_level": 1,
            "fallback_reason": "n3_unknown_register_distinct_voice",
                "output_mode": smart.OUTPUT_MODE_DUBBED_MULTI,
                "final_mp4_path": str(source),
                "blocker": None,
                "auto_smart_verified": True,
        }

    monkeypatch.setattr(smart, "run_auto_smart_multivoice", capture_runner)

    result = asyncio.run(
        smart.run_auto_smart_multivoice_blackbox(
            state={
                "auto_smart_multivoice_opt_in": True,
                "source": str(source),
            },
            prepare_subtitles=prepare,
            stereo_pcm_path=str(pcm),
            validated_pools={
                "low": ["voice_male_1", "voice_male_2"],
                "high": ["voice_female_1", "voice_female_2"],
            },
        )
    )

    assert result["ok"] is True
    assert result["state"]["auto_smart_fallback_level"] == 1
    assert result["state"]["auto_smart_fallback_reason"] == (
        "n3_unknown_register_distinct_voice"
    )
    assert result["state"]["auto_smart_register_degraded"] is True
    assert captured["acoustic_classifications"] == {
        "chunk_00:speaker_0": {
            "speaker_id": "chunk_00:speaker_0",
            "voice_register": "high",
            "voice_gender": "female",
            "confidence": subdub_multi_speaker_gender_onnx.MULTI_GENDER_STRONG_CONFIDENCE,
            "reason": "classified_multi_acoustic_gender_onnx",
        },
        "chunk_00:speaker_1": {
            "speaker_id": "chunk_00:speaker_1",
            "voice_register": "low",
            "voice_gender": "male",
            "confidence": subdub_multi_speaker_gender_onnx.MULTI_GENDER_STRONG_CONFIDENCE,
            "reason": "classified_multi_acoustic_gender_onnx",
        },
        "chunk_00:speaker_2": {
            "speaker_id": "chunk_00:speaker_2",
            "voice_register": "low",
            "voice_gender": "male",
            "confidence": subdub_multi_speaker_gender_onnx.MULTI_GENDER_STRONG_CONFIDENCE,
            "reason": "classified_multi_acoustic_gender_onnx",
        },
    }


def test_diarized_deepgram_result_preserves_word_timeline(monkeypatch):
    transcript_json = {
        "metadata": {"duration": 3.0},
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {
                            "transcript": "one two three",
                            "words": [
                                {
                                    "word": "one",
                                    "punctuated_word": "one",
                                    "start": 0.0,
                                    "end": 0.8,
                                    "speaker": 0,
                                    "speaker_confidence": 0.99,
                                },
                                {
                                    "word": "two",
                                    "punctuated_word": "two",
                                    "start": 1.0,
                                    "end": 1.8,
                                    "speaker": 1,
                                    "speaker_confidence": 0.99,
                                },
                                {
                                    "word": "three",
                                    "punctuated_word": "three",
                                    "start": 2.0,
                                    "end": 2.8,
                                    "speaker": 2,
                                    "speaker_confidence": 0.99,
                                },
                            ],
                        }
                    ]
                }
            ]
        },
    }

    async def deepgram(*_args, **_kwargs):
        return {
            "ok": True,
            "status": "PASS",
            "provider": "deepgram",
            "transcript": "one two three",
            "transcript_json": transcript_json,
        }

    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "configured-for-local-test")
    monkeypatch.setattr(bot, "ASR_PROVIDER", "deepgram")
    monkeypatch.setattr(bot, "deepgram_asr_adapter", deepgram)
    monkeypatch.setattr(bot, "save_provider_attempt", lambda *_args, **_kwargs: None)

    result = asyncio.run(
        bot.asr_transcribe_audio(
            b"local-audio",
            "audio/wav",
            require_diarization=True,
            allow_confirmed_product=True,
            media_duration_seconds=3.0,
        )
    )

    assert result["ok"] is True
    assert result["word_timeline"] == [
        {"index": 0, "word": "one", "start": 0.0, "end": 0.8},
        {"index": 1, "word": "two", "start": 1.0, "end": 1.8},
        {"index": 2, "word": "three", "start": 2.0, "end": 2.8},
    ]


def test_smart_n3_prepare_uses_fixed_vocal_acoustic_pipeline(tmp_path, monkeypatch):
    provider_segments = [
        {
            "index": index + 1,
            "start": float(index),
            "end": float(index + 1),
            "text": f"speaker {index}",
            "speaker": index,
            "speaker_confidence": 0.99,
        }
        for index in range(3)
    ]
    acoustic_segments = [
        {
            "cue_id": f"cue-{index}",
            "start": float(index),
            "end": float(index + 1),
            "text": f"speaker {index}",
            "speaker_id": f"chunk_00:speaker_{index}",
            "speaker_confidence": 0.99,
        }
        for index in range(3)
    ]
    word_timeline = [
        {"index": index, "word": f"word{index}", "start": float(index), "end": float(index + 0.8)}
        for index in range(3)
    ]
    evidence = {
        "multi_acoustic_speaker_count": 3,
        "multi_acoustic_speaker_registers": ["high", "low", "low"],
        "multi_acoustic_speaker_register_confidences": [0.91, 0.92, 0.90],
        "multi_acoustic_model_sha256": "a" * 64,
    }
    observed: dict = {}

    async def resolve_source(*_args, require_diarization=False, **_kwargs):
        observed["require_diarization"] = require_diarization
        return {
            "source_kind": "asr",
            "subtitle": bot.video_dubbing_srt_from_segments(provider_segments),
            "script": "speaker 0 speaker 1 speaker 2",
            "segments": provider_segments,
            "word_timeline": word_timeline,
            "duration_seconds": 3,
            "asr_provider": "deepgram",
        }

    async def extract_pcm(*_args, **_kwargs):
        return str(tmp_path / "prepared.pcm")

    async def diarize(pcm_path, words, *, duration_seconds):
        observed["pcm_path"] = str(pcm_path)
        observed["word_timeline"] = words
        observed["duration_seconds"] = duration_seconds
        return {
            "segments": acoustic_segments,
            "provider": "fixed_vocal_onnx",
            "model_sha256": "a" * 64,
            "algorithm_version": "fixed-vocal-test",
            "detected_speaker_count": 3,
            "speaker_registers": ["high", "low", "low"],
            "speaker_register_confidences": [0.91, 0.92, 0.90],
        }

    monkeypatch.setattr(bot, "video_dubbing_resolve_source_script", resolve_source)
    monkeypatch.setattr(bot, "_extract_subdub_auto_pcm", extract_pcm)
    monkeypatch.setattr(
        bot.auto_multi_speaker,
        "run_local_acoustic_diarization_off_event_loop",
        diarize,
    )
    monkeypatch.setattr(
        bot.auto_multi_speaker,
        "bounded_multi_acoustic_evidence",
        lambda _state: evidence,
    )
    monkeypatch.setattr(
        bot.auto_multi_speaker,
        "acoustic_sidecar_evidence",
        lambda _state: {"backend": "fixed_vocal_onnx"},
    )
    monkeypatch.setattr(
        bot.subdub_speaker_cast,
        "persist_sidecar",
        lambda *_args, **_kwargs: {"path": str(tmp_path / "sidecar.json"), "sha256": "b" * 64},
    )
    monkeypatch.setattr(bot, "set_video_dubbing_artifact", lambda *_args, **_kwargs: "artifact-ref")
    monkeypatch.setattr(
        bot,
        "video_dubbing_sync_state_fields",
        lambda state, *, exclude=None: {
            key: value
            for key, value in state.items()
            if key not in (set(exclude or ()) | {"step"})
        },
    )
    monkeypatch.setattr(
        bot,
        "set_video_dubbing_pending",
        lambda _user_id, step, **fields: {**fields, "step": step},
    )
    monkeypatch.setattr(bot, "subdub_mode_requests_translation", lambda *_args: False)

    prepared = asyncio.run(
        bot.video_dubbing_prepare_subtitles(
            None,
            {
                "auto_smart_multivoice_opt_in": True,
                "mode": "dub",
                "source_media_type": "video",
                "source_duration": 3,
                "_pipeline_source_bytes_override": b"video-bytes",
                "_pipeline_source_content_type_override": "video/mp4",
                "_pipeline_workspace": str(tmp_path),
            },
            user_id=123,
            allow_confirmed_product=True,
            require_auto_cast=True,
        )
    )

    assert observed["require_diarization"] is True
    assert observed["word_timeline"] == word_timeline
    assert observed["duration_seconds"] == 3.0
    assert len(prepared["source_segments"]) == 3
    assert prepared["state"]["multi_acoustic_speaker_registers"] == [
        "high",
        "low",
        "low",
    ]


def test_c580_prepared_registers_cast_three_voices_without_classifier_replay():
    segments = _prepared_segments()
    labels = [segment["speaker_id"] for segment in segments]
    prepared = {"state": {}, "source_segments": segments}
    acoustic_classifications = (
        bot.auto_multi_speaker.acoustic_register_classifications(prepared, labels)
    )

    def forbidden_classifier(*_args, **_kwargs):
        raise AssertionError("prepared fixed-vocal registers must be reused")

    decision = smart.decide_smart_multivoice(
        segments,
        validated_pools={
            "low": ["voice_male_1", "voice_male_2"],
            "high": ["voice_female_1", "voice_female_2"],
        },
        acoustic_classifications=acoustic_classifications,
        multi_speaker_classifier=forbidden_classifier,
    )

    assert decision.detected_speaker_count == 3
    assert decision.effective_speaker_count == 3
    assert set(decision.speaker_voice_map) == set(labels)
    assert len(set(decision.speaker_voice_map.values())) == 3


def test_c580_unknown_register_uses_distinct_approved_voice_and_marks_degraded():
    segments = _prepared_segments()
    labels = [segment["speaker_id"] for segment in segments]
    classifications = {
        labels[0]: {"voice_register": "high", "confidence": 0.91},
        labels[1]: {"voice_register": "low", "confidence": 0.92},
        labels[2]: {"voice_register": "unknown", "confidence": 0.50},
    }

    decision = smart.decide_smart_multivoice(
        segments,
        validated_pools={
            "low": ["voice_male_1", "voice_male_2"],
            "high": ["voice_female_1", "voice_female_2"],
        },
        acoustic_classifications=classifications,
        assignment_seed="c580-unknown-register",
    )

    assert decision.output_mode == smart.OUTPUT_MODE_DUBBED_MULTI
    assert decision.effective_speaker_count == 3
    assert decision.effective_voice_count == 3
    assert len(set(decision.speaker_voice_map.values())) == 3
    assert set(decision.speaker_voice_map.values()) <= {
        "voice_male_1",
        "voice_male_2",
        "voice_female_1",
        "voice_female_2",
    }
    assert decision.fallback_level == 1
    assert decision.fallback_reason == "n3_unknown_register_distinct_voice"


def test_c580_unknown_register_still_fails_closed_when_distinct_pool_is_too_small():
    segments = _prepared_segments()
    labels = [segment["speaker_id"] for segment in segments]
    classifications = {
        labels[0]: {"voice_register": "high", "confidence": 0.91},
        labels[1]: {"voice_register": "low", "confidence": 0.92},
        labels[2]: {"voice_register": "unknown", "confidence": 0.50},
    }

    try:
        smart.decide_smart_multivoice(
            segments,
            validated_pools={"low": ["voice_male_1"], "high": ["voice_female_1"]},
            acoustic_classifications=classifications,
            assignment_seed="c580-small-pool",
            raise_manual_required=True,
        )
    except speaker_cast.AutoCastManualRequired:
        pass
    else:
        raise AssertionError("Smart N>=3 must not reuse voices when the approved pool is too small")


def test_c580_unknown_register_tries_existing_local_pitch_fallback_first(tmp_path, monkeypatch):
    segments = _prepared_segments()
    labels = [segment["speaker_id"] for segment in segments]
    pcm = tmp_path / "speaker_audio.pcm"
    pcm.write_bytes(b"\x01\x00\x01\x00" * 8)
    observed = {}

    def pitch_fallback(pcm_path, ranges, **_kwargs):
        observed["pcm_path"] = str(pcm_path)
        observed["ranges"] = ranges
        return {labels[2]: {"voice_register": "low", "confidence": 0.82}}

    monkeypatch.setattr(smart, "estimate_speaker_pitches_from_pcm", pitch_fallback)
    decision = smart.decide_smart_multivoice(
        segments,
        validated_pools={
            "low": ["voice_male_1", "voice_male_2"],
            "high": ["voice_female_1", "voice_female_2"],
        },
        acoustic_classifications={
            labels[0]: {"voice_register": "high", "confidence": 0.91},
            labels[1]: {"voice_register": "low", "confidence": 0.92},
            labels[2]: {"voice_register": "unknown", "confidence": 0.50},
        },
        stereo_pcm_path=pcm,
        ranges_by_speaker={label: [(float(index), float(index + 1))] for index, label in enumerate(labels)},
        assignment_seed="c580-pitch-refine",
    )

    assert observed["pcm_path"] == str(pcm)
    assert labels[2] in observed["ranges"]
    assert decision.fallback_level == 0
    assert decision.fallback_reason is None
    assert decision.effective_voice_count == 3
