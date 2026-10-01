from __future__ import annotations

import asyncio
from pathlib import Path

import bot
import pytest
from services import subdub_multi_speaker_gender_onnx
from services import subdub_speaker_cast as speaker_cast
from services.subdub_blackboxes import auto_smart_multivoice as smart
from services.subdub_blackboxes import auto_multi_speaker_v2


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


def test_smart_blackbox_dispatches_strong_prepared_registers_to_v2(
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

    async def capture_v2(*, state, **kwargs):
        captured.update(kwargs)
        captured["state"] = dict(state)
        return {
            "ok": True,
            "state": {
                "auto_multi_voice_verified": True,
                "auto_detected_speaker_count": 3,
                "auto_distinct_voice_count": 3,
            },
            "video_output": b"v2-video-output",
        }

    monkeypatch.setattr(
        auto_multi_speaker_v2,
        "run_auto_multi_speaker_v2_blackbox",
        capture_v2,
    )

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
    assert result["state"]["subdub_engine_selected"] == "auto_multi_speaker_v2"
    assert result["state"]["auto_smart_dispatch"] == "n3_plus_proven_v2"
    assert captured["state"]["auto_speaker_lane"] == "multi"
    assert captured["state"]["auto_multi_engine"] == "v2"


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


def _valid_three_speaker_acoustic_result(segments: list[dict]) -> dict:
    engine = bot.auto_multi_speaker.subdub_multi_speaker_embedding_onnx
    return {
        "segments": segments,
        "provider": engine.FIXED_VOCAL_PROVIDER,
        "model_sha256": engine.MODEL_SHA256,
        "algorithm_version": engine.FIXED_VOCAL_ALGORITHM_VERSION,
        "detected_speaker_count": 3,
        "word_count": 6,
        "unit_count": 6,
        "embedding_window_count": 12,
        "cluster_sizes": [2, 2, 2],
        "stability_pass": True,
        "word_coverage_count": 6,
        "overlap_mapped_count": 6,
        "centroid_mapped_count": 0,
        "speaker_unit_counts": [2, 2, 2],
        "raw_speaker_count": 3,
        "raw_embedding_window_count": 12,
        "raw_cluster_sizes": [2, 2, 2],
        "raw_speaker_unit_counts": [2, 2, 2],
        "raw_overlap_speaker_unit_counts": [2, 2, 2],
        "speech_supported_speaker_labels": [0, 1, 2],
        "dropped_non_speech_speaker_labels": [],
        "speaker_count_authority_asr_independent": True,
        "word_attribution_uses_asr_timeline": True,
        "speaker_registers": ["high", "low", "low"],
        "speaker_register_confidences": [0.91, 0.92, 0.90],
        "female_speaker_count": 1,
        "male_speaker_count": 2,
        "gender_model_sha256": subdub_multi_speaker_gender_onnx.MULTI_GENDER_MODEL_SHA256,
        "gender_ambiguous_window_count": 0,
    }


def test_smart_n3_bypasses_embedded_subtitle_for_acoustic_asr(tmp_path, monkeypatch):
    words = [
        {
            "word": f"word{index}",
            "punctuated_word": f"word{index}",
            "start": float(index),
            "end": float(index + 0.8),
            "speaker": index // 2,
            "speaker_confidence": 0.99,
        }
        for index in range(6)
    ]
    transcript_json = {
        "metadata": {"duration": 6.0},
        "results": {"channels": [{"alternatives": [{
            "transcript": " ".join(word["word"] for word in words),
            "words": words,
        }]}]},
    }
    observed = {}
    acoustic_segments = [
        {
            "cue_id": f"cue-{index}",
            "start": float(index * 2),
            "end": float(index * 2 + 1.8),
            "text": f"word{index * 2} word{index * 2 + 1}",
            "speaker": index,
            "speaker_id": f"chunk_00:speaker_{index}",
            "speaker_confidence": 0.99,
            "voice_register": ("high", "low", "low")[index],
        }
        for index in range(3)
    ]
    pcm = tmp_path / "source.pcm"
    pcm.write_bytes(b"\x01\x00\x01\x00" * 8)

    async def deepgram(*_args, **_kwargs):
        return {
            "ok": True,
            "status": "PASS",
            "provider": "deepgram",
            "transcript": " ".join(word["word"] for word in words),
            "transcript_json": transcript_json,
        }

    async def embedded_subtitle(*_args, **_kwargs):
        return "1\n00:00:00,000 --> 00:00:01,000\nvisible subtitle", "embedded"

    async def video_probe(*_args, **_kwargs):
        return {"ok": True, "has_video": True, "has_audio": True, "duration": 6.0}

    async def extract_audio(*_args, **_kwargs):
        return b"local-audio", "audio/wav", "local-extract"

    async def extract_pcm(*_args, **_kwargs):
        return str(pcm)

    async def diarize(_pcm_path, word_timeline, *, duration_seconds):
        observed["word_timeline"] = word_timeline
        observed["duration_seconds"] = duration_seconds
        return _valid_three_speaker_acoustic_result(acoustic_segments)

    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "configured-for-local-test")
    monkeypatch.setattr(bot, "ASR_PROVIDER", "deepgram")
    monkeypatch.setattr(bot, "deepgram_asr_adapter", deepgram)
    monkeypatch.setattr(bot, "save_provider_attempt", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bot, "video_dubbing_extract_embedded_subtitle", embedded_subtitle)
    monkeypatch.setattr(bot, "subdub_probe_video_bytes", video_probe)
    monkeypatch.setattr(bot, "video_dubbing_audio_extract_ready", lambda: True)
    monkeypatch.setattr(bot, "video_dubbing_extract_audio", extract_audio)
    monkeypatch.setattr(bot, "_extract_subdub_auto_pcm", extract_pcm)
    monkeypatch.setattr(bot.auto_multi_speaker, "run_local_acoustic_diarization_off_event_loop", diarize)
    monkeypatch.setattr(bot, "set_video_dubbing_artifact", lambda *_args, **_kwargs: "artifact-ref")
    monkeypatch.setattr(bot, "set_video_dubbing_pending", lambda _user_id, step, **fields: {**fields, "step": step})
    monkeypatch.setattr(bot, "subdub_mode_requests_translation", lambda *_args: False)

    prepared = asyncio.run(bot.video_dubbing_prepare_subtitles(
        None,
        {
            "auto_smart_multivoice_opt_in": True,
            "mode": "dub",
            "source_media_type": "video",
            "source_duration": 6,
            "_pipeline_source_bytes_override": b"local-video",
            "_pipeline_source_content_type_override": "video/mp4",
            "_pipeline_workspace": str(tmp_path),
        },
        user_id=123,
        allow_confirmed_product=True,
        require_auto_cast=True,
    ))

    assert observed["duration_seconds"] == 6.0
    assert observed["word_timeline"] == [
        {"index": index, "word": f"word{index}", "start": float(index), "end": float(index + 0.8)}
        for index in range(6)
    ]
    assert [cue["speaker_id"] for cue in prepared["source_segments"]] == [
        f"chunk_00:speaker_{index}" for index in range(3)
    ]
    assert [cue["speaker_confidence"] for cue in prepared["source_segments"]] == [0.99] * 3
    assert prepared["state"]["multi_acoustic_speaker_registers"] == ["high", "low", "low"]


def test_smart_blackbox_recovers_one_weak_prepared_register_without_classifier_replay(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    pcm = tmp_path / "source.pcm"
    pcm.write_bytes(b"\x01\x00\x01\x00" * (44_100 * 3))
    segments = _prepared_segments()
    acoustic_result = _valid_three_speaker_acoustic_result(segments)
    acoustic_result["speaker_register_confidences"] = [0.91, 0.92, 0.60]
    state = {
        "multi_acoustic_backend": acoustic_result["provider"],
        "multi_acoustic_model_sha256": acoustic_result["model_sha256"],
        "multi_acoustic_algorithm_version": acoustic_result["algorithm_version"],
        "multi_acoustic_speaker_count": acoustic_result["detected_speaker_count"],
        **{
            f"multi_acoustic_{name}": acoustic_result[name]
            for name in (
                "word_count", "unit_count", "embedding_window_count",
                "cluster_sizes", "stability_pass", "word_coverage_count",
                "overlap_mapped_count", "centroid_mapped_count", "speaker_unit_counts",
                "raw_speaker_count", "raw_embedding_window_count", "raw_cluster_sizes",
                "raw_speaker_unit_counts", "raw_overlap_speaker_unit_counts",
                "speaker_count_authority_asr_independent", "word_attribution_uses_asr_timeline",
                "speaker_registers", "speaker_register_confidences", "female_speaker_count",
                "male_speaker_count", "gender_model_sha256", "gender_ambiguous_window_count",
            )
        },
        "multi_acoustic_speech_supported_speaker_labels": [0, 1, 2],
        "multi_acoustic_dropped_non_speech_speaker_labels": [],
        "multi_acoustic_dropped_non_speech_speaker_count": 0,
    }
    assert bot.auto_multi_speaker.bounded_multi_acoustic_evidence(state)

    async def prepare(_state, *, require_auto_cast=False):
        assert require_auto_cast
        return {
            "state": state,
            "source_file": str(source),
            "source_segments": segments,
            "output_segments": segments,
        }

    captured = {}

    async def capture_runner(**kwargs):
        captured.update(kwargs)
        captured["decision"] = smart.decide_smart_multivoice(
            kwargs["segments"],
            validated_pools=kwargs["validated_pools"],
            assignment_seed=kwargs["assignment_seed"],
            stereo_pcm_path=kwargs["stereo_pcm_path"],
            ranges_by_speaker=kwargs["ranges_by_speaker"],
            acoustic_classifications=kwargs["acoustic_classifications"],
        )
        return {"ok": False, "fallback_reason": "test_stop_before_tts"}

    monkeypatch.setattr(smart, "estimate_speaker_pitches_from_pcm", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(smart, "run_auto_smart_multivoice", capture_runner)
    asyncio.run(smart.run_auto_smart_multivoice_blackbox(
        state={"auto_smart_multivoice_opt_in": True, "source": str(source)},
        prepare_subtitles=prepare,
        stereo_pcm_path=str(pcm),
        validated_pools={
            "low": ["voice_male_1", "voice_male_2"],
            "high": ["voice_female_1", "voice_female_2"],
        },
    ))

    labels = [segment["speaker_id"] for segment in segments]
    assert captured["acoustic_classifications"] == {
        labels[0]: {"speaker_id": labels[0], "voice_register": "high", "confidence": 0.91},
        labels[1]: {"speaker_id": labels[1], "voice_register": "low", "confidence": 0.92},
        labels[2]: {"speaker_id": labels[2], "voice_register": "unknown", "confidence": 0.60},
    }
    assert captured["decision"].fallback_reason == "n3_unknown_register_distinct_voice"
    assert len(set(captured["decision"].speaker_voice_map.values())) == 3

    captured.clear()
    state["multi_acoustic_model_sha256"] = "0" * 64
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        asyncio.run(smart.run_auto_smart_multivoice_blackbox(
            state={"auto_smart_multivoice_opt_in": True, "source": str(source)},
            prepare_subtitles=prepare,
            stereo_pcm_path=str(pcm),
        ))
    assert captured == {}


def test_smart_n3_dispatches_prepared_state_to_proven_v2_once(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-video")
    pcm = tmp_path / "source.pcm"
    pcm.write_bytes(b"\x01\x00\x01\x00" * (44_100 * 4))
    segments = _prepared_segments()
    prepared = {
        "state": {
            "auto_smart_multivoice_opt_in": True,
            "_pipeline_workspace": str(tmp_path),
            "_pipeline_job_id": "smart-n3-v2",
        },
        "source_file": str(source),
        "source_bytes": source.read_bytes(),
        "source_segments": segments,
        "output_segments": segments,
    }
    observed = {"prepare_calls": 0, "v2_calls": 0}

    async def prepare(_state, *, require_auto_cast=False):
        assert require_auto_cast is True
        observed["prepare_calls"] += 1
        return prepared

    async def extract_pcm(*_args, **_kwargs):
        return str(pcm)

    async def run_v2(*, state, extract_pcm, **payload):
        observed["v2_calls"] += 1
        observed["state"] = dict(state)
        assert callable(extract_pcm)
        reused = await payload["prepare_subtitles"](
            dict(state),
            require_auto_cast=True,
        )
        assert reused is prepared
        return {
            "ok": True,
            "state": {
                "auto_multi_voice_verified": True,
                "auto_detected_speaker_count": 3,
                "auto_distinct_voice_count": 3,
            },
            "video_output": b"real-v2-output-boundary",
        }

    async def forbid_smart_runner(**_kwargs):
        raise AssertionError("Smart N>=3 must reuse the proven V2 downstream engine")

    monkeypatch.setattr(
        auto_multi_speaker_v2,
        "run_auto_multi_speaker_v2_blackbox",
        run_v2,
    )
    monkeypatch.setattr(smart, "run_auto_smart_multivoice", forbid_smart_runner)

    result = asyncio.run(smart.run_auto_smart_multivoice_blackbox(
        state={
            "auto_smart_multivoice_opt_in": True,
            "source": str(source),
            "_pipeline_workspace": str(tmp_path),
            "_pipeline_job_id": "smart-n3-v2",
        },
        lane_mode="subtitle_plus_dub",
        prepare_subtitles=prepare,
        extract_pcm=extract_pcm,
        run_lane_blackbox=lambda **_kwargs: {},
        runner=lambda **_kwargs: {},
    ))

    assert observed["prepare_calls"] == 1
    assert observed["v2_calls"] == 1
    assert observed["state"]["auto_speaker_lane"] == "multi"
    assert observed["state"]["auto_multi_engine"] == "v2"
    assert observed["state"]["auto_smart_multivoice_opt_in"] is True
    assert result["ok"] is True
    assert result["state"]["subdub_engine_selected"] == "auto_multi_speaker_v2"
    assert result["state"]["auto_smart_dispatch"] == "n3_plus_proven_v2"
