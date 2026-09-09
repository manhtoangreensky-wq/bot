from __future__ import annotations

import hashlib
import json

import pytest

import bot


def _valid_acoustic_state() -> dict:
    engine = bot.auto_multi_speaker.subdub_multi_speaker_embedding_onnx
    gender = bot.auto_multi_speaker.subdub_multi_speaker_gender_onnx
    return {
        "multi_acoustic_backend": engine.FIXED_VOCAL_PROVIDER,
        "multi_acoustic_model_sha256": engine.MODEL_SHA256,
        "multi_acoustic_algorithm_version": engine.FIXED_VOCAL_ALGORITHM_VERSION,
        "multi_acoustic_speaker_count": 5,
        "multi_acoustic_word_count": 145,
        "multi_acoustic_unit_count": 35,
        "multi_acoustic_embedding_window_count": 118,
        "multi_acoustic_cluster_sizes": [16, 11, 13, 12, 7],
        "multi_acoustic_stability_pass": True,
        "multi_acoustic_word_coverage_count": 145,
        "multi_acoustic_overlap_mapped_count": 35,
        "multi_acoustic_centroid_mapped_count": 0,
        "multi_acoustic_speaker_unit_counts": [8, 6, 11, 5, 5],
        "multi_acoustic_word_overlap_mapped_count": 145,
        "multi_acoustic_word_fallback_mapped_count": 0,
        "multi_acoustic_word_centroid_mapped_count": 0,
        "multi_acoustic_raw_speaker_count": 5,
        "multi_acoustic_raw_embedding_window_count": 178,
        "multi_acoustic_raw_cluster_sizes": [9, 18, 26, 25, 11],
        "multi_acoustic_raw_speaker_unit_counts": [0, 9, 9, 11, 6],
        "multi_acoustic_raw_overlap_speaker_unit_counts": [0, 7, 8, 10, 4],
        "multi_acoustic_speech_supported_speaker_labels": [0, 1, 2, 3, 4],
        "multi_acoustic_dropped_non_speech_speaker_labels": [],
        "multi_acoustic_dropped_non_speech_speaker_count": 0,
        "multi_acoustic_speaker_registers": ["high", "low", "low", "high", "low"],
        "multi_acoustic_speaker_register_confidences": [0.99998, 0.995783, 0.999678, 0.999999, 0.999805],
        "multi_acoustic_female_speaker_count": 2,
        "multi_acoustic_male_speaker_count": 3,
        "multi_acoustic_gender_model_sha256": gender.MULTI_GENDER_MODEL_SHA256,
        "multi_acoustic_gender_ambiguous_window_count": 0,
        "multi_acoustic_speaker_count_authority_asr_independent": True,
        "multi_acoustic_word_attribution_uses_asr_timeline": True,
    }


def _exact_multi_cache(tmp_path, monkeypatch) -> tuple[dict, dict]:
    media = b"customer-exact-multi-media"
    media_path = tmp_path / "normalized_source.mp4"
    source_path = tmp_path / "auto_exact_source.srt"
    translated_path = tmp_path / "auto_exact_translated.srt"
    metadata_path = tmp_path / "auto_exact_cache.json"
    media_path.write_bytes(media)

    registers = ["high", "low", "low", "high", "low"]
    cues = []
    translated = []
    for index, register in enumerate(registers):
        start = float(index * 4)
        end = start + 3.8
        cues.append({
            "cue_id": f"cue-{index + 1:04d}-signed",
            "index": index + 1,
            "start": start,
            "end": end,
            "source_start_ms": int(start * 1000),
            "source_end_ms": int(end * 1000),
            "text": " ".join(f"source_{index}_{word}" for word in range(10)),
            "speaker": index,
            "chunk_index": 0,
            "speaker_id": f"chunk_00:speaker_{index}",
            "speaker_confidence": 0.99,
            "voice_register": register,
        })
        translated.append({
            "index": index + 1,
            "start": start,
            "end": end,
            "text": " ".join(f"target_{index}_{word}" for word in range(10)),
        })

    source_srt = bot.video_dubbing_srt_from_segments(cues)
    translated_srt = bot.video_dubbing_srt_from_segments(translated)
    source_path.write_text(source_srt, encoding="utf-8")
    translated_path.write_text(translated_srt, encoding="utf-8")
    sidecar = bot.subdub_speaker_cast.build_sidecar(
        cues,
        media_sha256=hashlib.sha256(media).hexdigest(),
        subtitle_sha256=bot.subdub_speaker_sidecar_subtitle_sha256(source_srt),
    )
    sidecar["acoustic"] = bot.auto_multi_speaker.acoustic_sidecar_evidence(
        _valid_acoustic_state()
    )
    sidecar_receipt = bot.subdub_speaker_cast.persist_sidecar(
        sidecar,
        workspace=str(tmp_path),
    )
    stored_cache = {
        "version": bot.SUBDUB_AUTO_EXACT_RECEIPT_VERSION,
        "source_file": source_path.name,
        "translated_file": translated_path.name,
        "source_media_file": media_path.name,
        "source_subtitle_sha256": bot._subdub_auto_text_sha256(source_srt),
        "translated_subtitle_sha256": bot._subdub_auto_text_sha256(translated_srt),
        "dub_text_source": "translated",
        "target_language": "Vietnamese",
    }
    metadata_path.write_text(
        json.dumps(stored_cache, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    cache = {**stored_cache, "metadata_file": metadata_path.name}
    lost_structured_state = {
        key: value
        for key, value in _valid_acoustic_state().items()
        if isinstance(value, (str, int, float, bool)) or value is None
    }
    state = {
        **lost_structured_state,
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "auto_speaker_lane": "multi",
        "_pipeline_workspace": str(tmp_path),
        "speaker_sidecar_path": sidecar_receipt["path"],
        "speaker_sidecar_sha256": sidecar_receipt["sha256"],
        "source_mime_type": "video/mp4",
        "target_language": "Vietnamese",
        "translate_requested": "1",
    }
    job = {
        "workspace": str(tmp_path),
        "auto_exact_cache": cache,
        "auto_exact_receipt": {
            "version": bot.SUBDUB_AUTO_EXACT_RECEIPT_VERSION,
            "media_sha256": hashlib.sha256(media).hexdigest(),
        },
    }
    monkeypatch.setattr(
        bot,
        "subtitle_dub_workspace_path_safety",
        lambda _workspace: {"allowed": True},
    )
    return job, state


def test_exact_resume_state_preserves_validated_multi_acoustic_bundle():
    state = {
        **_valid_acoustic_state(),
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "auto_speaker_lane": "multi",
    }

    resumed = bot._subdub_auto_resume_state(state)

    assert bot.auto_multi_speaker.bounded_multi_acoustic_evidence(resumed) == (
        _valid_acoustic_state()
    )


def test_non_multi_resume_never_enters_acoustic_restore(monkeypatch):
    class ForbiddenAcousticModule:
        def is_auto_multi_speaker_state(self, _state):
            raise AssertionError("non-Multi resume must not touch acoustic restore")

    monkeypatch.setattr(bot, "auto_multi_speaker", ForbiddenAcousticModule())

    resumed = bot._subdub_auto_resume_state({
        "keep_original_audio": "1",
        "original_audio_volume_percent": 20,
        "dubbed_voice_volume_percent": 100,
    })

    assert resumed == {
        "keep_original_audio": "1",
        "original_audio_volume_percent": 20,
        "dubbed_voice_volume_percent": 100,
    }


def test_customer_exact_resume_rehydrates_acoustic_bundle_from_signed_sidecar(
    monkeypatch,
    tmp_path,
):
    job, state = _exact_multi_cache(tmp_path, monkeypatch)

    prepared = bot._subdub_auto_load_cached_prepared(job, state)

    assert bot.auto_multi_speaker.bounded_multi_acoustic_evidence(
        prepared["state"]
    ) == _valid_acoustic_state()
    labels, _ranges = bot.auto_multi_speaker.auto_speaker._validated_classifier_inputs(
        prepared
    )
    classifications = bot.auto_multi_speaker.acoustic_register_classifications(
        prepared,
        labels,
    )
    assert [classifications[label]["voice_register"] for label in labels] == [
        "high",
        "low",
        "low",
        "high",
        "low",
    ]


def test_customer_exact_resume_rejects_semantically_invalid_acoustic_sidecar(
    monkeypatch,
    tmp_path,
):
    job, state = _exact_multi_cache(tmp_path, monkeypatch)
    sidecar = bot.subdub_speaker_cast.load_sidecar(
        state["speaker_sidecar_path"],
        expected_sha256=state["speaker_sidecar_sha256"],
        workspace=str(tmp_path),
    )
    sidecar["acoustic"]["speaker_registers"] = ["high"]
    updated = bot.subdub_speaker_cast.persist_sidecar(sidecar, workspace=str(tmp_path))
    state.update({
        "speaker_sidecar_path": updated["path"],
        "speaker_sidecar_sha256": updated["sha256"],
    })

    with pytest.raises(bot.subdub_speaker_cast.AutoCastUnavailable):
        bot._subdub_auto_load_cached_prepared(job, state)
