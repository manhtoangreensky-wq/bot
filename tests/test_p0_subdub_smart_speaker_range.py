import asyncio
import numpy as np
import pytest
import time

from services import subdub_multi_speaker_embedding_onnx as engine
from services import subdub_speaker_cast as speaker_cast
from services.subdub_blackboxes import auto_multi_speaker
from services.subdub_blackboxes import auto_smart_multivoice as smart


def _speaker_views(count):
    identities = [speaker for speaker in range(count) for _ in range(12)]
    embeddings = np.zeros((len(identities), engine.EMBEDDING_DIM), dtype=np.float32)
    for index, speaker in enumerate(identities):
        embeddings[index, speaker] = 1.0
    return identities, embeddings, [index * 0.75 for index in range(len(identities))]


def _speech_window_fixture(monkeypatch, words, identities):
    rows = np.zeros((len(words), engine.EMBEDDING_DIM), dtype=np.float32)
    for index, identity in enumerate(identities):
        rows[index, identity] = 1.0
    regions = [{"run_index": index, "speech_start_seconds": 0.0,
                "speech_end_seconds": 0.75} for index in range(len(words))]
    windows = [{**region, "window_index": index}
               for index, region in enumerate(regions)]
    views = {"plan": {"regions": regions, "windows": windows},
             "base_embeddings": rows, "shifted_embeddings": rows.copy(),
             "source_positions": [word["start"] for word in words],
             "speech_seconds": np.ones(len(words)), "window_samples": [None] * len(words)}
    monkeypatch.setattr(engine, "_fixed_vocal_speech_window_views", lambda *_a, **_k: views)
    monkeypatch.setattr(engine.multi_gender, "classify_vocal_window_gender_probabilities",
                        lambda *_a, **_k: [0.99 if label % 2 == 0 else 0.01 for label in identities])


@pytest.mark.parametrize("count", range(1, 9))
def test_smart_acoustic_count_accepts_one_to_eight_without_sample_identity(count):
    _identities, embeddings, positions = _speaker_views(count)
    result = engine.build_fixed_vocal_authority(
        embeddings,
        embeddings.copy(),
        np.ones(len(embeddings)),
        positions,
        minimum_speakers=1,
    )

    assert result["speaker_count"] == count
    assert len({item["speaker"] for item in result["core_windows"]}) == count
    assert result["core_partition_stable"] is True


@pytest.mark.parametrize("count", range(1, 9))
def test_smart_register_partition_keeps_each_detected_speaker(count):
    identities, embeddings, positions = _speaker_views(count)
    registers = ["high" if speaker % 2 == 0 else "low" for speaker in range(count)]
    probabilities = [0.99 if registers[speaker] == "high" else 0.01 for speaker in identities]
    result = engine.build_gender_constrained_speech_authority(
        embeddings,
        embeddings.copy(),
        positions,
        np.full(len(embeddings), 1.5),
        probabilities,
        speaker_count=count,
        minimum_speakers=1,
    )

    assert result["speaker_count"] == count
    assert len(set(result["labels"])) == count
    for label, probability in zip(result["labels"], probabilities, strict=True):
        assert result["speaker_registers"][label] == ("high" if probability >= 0.9 else "low")


def test_legacy_multi_still_rejects_two_speaker_authority():
    identities, embeddings, positions = _speaker_views(2)

    def fixed_two(matrix, _positions):
        return 2, np.asarray(identities[:len(matrix)]), np.zeros(len(matrix))

    with pytest.raises(speaker_cast.AutoCastManualRequired) as rejected:
        engine.build_fixed_vocal_authority(
            embeddings, embeddings.copy(), np.ones(len(embeddings)), positions,
            clusterer=fixed_two,
        )
    assert str(rejected.value.__cause__) == "fixed_vocal_cluster_invalid"


@pytest.mark.parametrize("count", range(1, 9))
def test_smart_uncertain_register_keeps_supported_identities_and_all_words(monkeypatch, count):
    words = [
        {"index": speaker * 12 + word, "word": "speech", "start": speaker * 16.0 + word,
         "end": speaker * 16.0 + word + 0.75}
        for speaker in range(count) for word in range(12)
    ]
    duration = words[-1]["end"] + 1.0
    units = engine.build_acoustic_units(words, duration_seconds=duration)
    identities = [int(unit["start"] // 16) for unit in units]
    raw = {
        "speaker_count": count,
        "centroids": np.eye(count, engine.EMBEDDING_DIM, dtype=np.float32),
        "core_windows": [
            {"start": speaker * 16.0, "end": speaker * 16.0 + 12.0, "speaker": speaker}
            for speaker in range(count)
        ],
    }
    word_identities = [int(word["start"] // 16) for word in words]
    _speech_window_fixture(monkeypatch, words, word_identities)
    original_probabilities = [0.99 if speaker == 0 else 0.5 if speaker == 2 else 0.01
                              for speaker in word_identities]
    pcm = np.ones(int(duration * engine.PCM_SAMPLE_RATE), dtype=np.int16)

    result = engine._smart_proven_speech_fallback(
        pcm, pcm, units, words, raw,
        deadline_monotonic=time.monotonic() + 30,
        stop_requested=lambda: False,
        original_probabilities=original_probabilities,
    )

    assert result["detected_speaker_count"] == count
    assert result["word_coverage_count"] == len(words)
    assert len({segment["speaker_id"] for segment in result["segments"]}) == count
    assert sum(len(segment["text"].split()) for segment in result["segments"]) == len(words)
    classes = result["smart_acoustic_classifications"]
    assert classes["chunk_00:speaker_0"]["voice_register"] == "high"
    if count >= 3:
        assert classes["chunk_00:speaker_2"]["voice_register"] == "unknown"
        decision = smart.decide_smart_multivoice(
            result["segments"], acoustic_classifications=classes,
            validated_pools={"low": [f"low-{i}" for i in range(8)], "high": [f"high-{i}" for i in range(8)]},
        )
        assert decision.effective_speaker_count == count
        assert decision.effective_voice_count == count
        assert len(set(decision.speaker_voice_map.values())) == count


def test_smart_proven_fallback_keeps_short_speaker_inside_shared_word_unit(monkeypatch):
    words = [{"index": block * 2 + speaker, "word": "speech",
              "start": block * 4.0 + speaker * 0.8,
              "end": block * 4.0 + speaker * 0.8 + 0.6}
             for block in range(12) for speaker in range(2)]
    duration = words[-1]["end"] + 1
    units = engine.build_acoustic_units(words, duration_seconds=duration)
    assert any(len(unit["word_indexes"]) == 2 for unit in units)
    raw = {
        "speaker_count": 2,
        "centroids": np.eye(2, engine.EMBEDDING_DIM, dtype=np.float32),
        "core_windows": [{"start": block * 4.0 + speaker * 0.75,
                          "end": block * 4.0 + (speaker + 1) * 0.75,
                          "speaker": speaker}
                         for block in range(12) for speaker in range(2)],
    }
    _speech_window_fixture(monkeypatch, words, [0, 1] * 12)
    pcm = np.ones(int(duration * engine.PCM_SAMPLE_RATE), dtype=np.int16)
    result = engine._smart_proven_speech_fallback(
        pcm, pcm, units, words, raw,
        deadline_monotonic=time.monotonic() + 30, stop_requested=lambda: False,
        original_probabilities=[0.5] * len(words),
    )
    assert result["detected_speaker_count"] == 2
    assert result["word_coverage_count"] == len(words)
    assert [segment["speaker"] for segment in result["segments"]] == [0, 1] * 12


def test_smart_five_speaker_strict_result_keeps_v2_route(monkeypatch):
    """A proven five-speaker Smart result must retain the strict multi route."""
    labels = [f"chunk_00:speaker_{index}" for index in range(5)]
    segments = [
        {
            "cue_id": f"cue-{index}",
            "speaker": index,
            "speaker_id": label,
            "chunk_index": 0,
            "start": float(index),
            "end": float(index) + 0.8,
            "text": f"speaker {index}",
        }
        for index, label in enumerate(labels)
    ]
    prepared = {
        "state": {
            "auto_speaker_lane": "auto_smart_multivoice",
            "auto_smart_multivoice_opt_in": True,
        },
        "source_bytes": b"valid-source-bytes",
        "source_segments": segments,
        "output_segments": segments,
    }
    classes = {
        label: {
            "speaker_id": label,
            "voice_register": "high" if index == 0 else "low",
            "confidence": 0.95,
        }
        for index, label in enumerate(labels)
    }
    captured = {}

    async def prepare_subtitles(*_args, **_kwargs):
        return prepared

    async def run_v2(**kwargs):
        captured["state"] = dict(kwargs["state"])
        captured["prepared"] = await kwargs["prepare_subtitles"]()
        return {"ok": True, "state": dict(kwargs["state"])}

    monkeypatch.setattr(
        smart.auto_multi_speaker,
        "acoustic_register_classifications",
        lambda _prepared, speaker_labels: {
            label: classes[label] for label in speaker_labels
        },
    )
    monkeypatch.setattr(
        smart.auto_multi_speaker_v2,
        "run_auto_multi_speaker_v2_blackbox",
        run_v2,
    )

    result = asyncio.run(
        smart.run_auto_smart_multivoice_blackbox(
            state=prepared["state"],
            prepare_subtitles=prepare_subtitles,
            validated_pools={
                "low": [f"low-{index}" for index in range(8)],
                "high": [f"high-{index}" for index in range(8)],
            },
        )
    )

    assert result["ok"] is True
    assert result["auto_smart_dispatch"] == "n3_plus_proven_v2"
    assert captured["state"]["auto_speaker_lane"] == "multi"
    assert captured["state"]["subdub_engine_selected"] == "auto_multi_speaker_v2"
    assert captured["state"].get("auto_smart_generic_acoustic") is not True
    assert {
        segment["speaker_id"] for segment in captured["prepared"]["source_segments"]
    } == set(labels)


@pytest.mark.parametrize("count, count_failure", [
    (1, "acoustic_cluster_unsupported"),
    (2, "acoustic_cluster_unsupported"),
    (2, "fixed_vocal_speaker_count_unstable"),
    (5, None),
])
def test_smart_count_retry_and_unknown_register_reuse_one_acoustic_extraction(
    monkeypatch, tmp_path, count, count_failure,
):
    words = [{"index": i, "word": "hello", "start": float(i), "end": float(i) + 0.8}
             for i in range(20)]
    pcm_path = tmp_path / "source.pcm"
    np.ones(20 * 44_100 * 2, dtype=np.int16).tofile(pcm_path)
    raw = {"speaker_count": count}
    calls = []

    def load(*_a, **_k):
        calls.append("extract")
        return np.ones(20 * engine.PCM_SAMPLE_RATE, dtype=np.int16)

    def raw_authority(*_a, **kwargs):
        calls.append(kwargs.get("minimum_speakers", engine.MIN_SPEAKERS))
        if count < engine.MIN_SPEAKERS and "minimum_speakers" not in kwargs:
            raise speaker_cast.AutoCastManualRequired() from ValueError(
                count_failure
            )
        return raw

    def register_authority(*_a, **_k):
        raise speaker_cast.AutoCastManualRequired() from ValueError(
            "fixed_vocal_gender_evidence_invalid"
        )

    def fallback(_pcm, _gender, _units, _words, authority, **_k):
        assert authority is raw
        return {"ok": True, "smart_acoustic_generic": True,
                "detected_speaker_count": authority["speaker_count"]}

    monkeypatch.setattr(engine, "_load_fixed_vocal_pcm16", load)
    monkeypatch.setattr(engine, "_fixed_vocal_window_views", lambda *_a, **_k: {
        "base_embeddings": [], "shifted_embeddings": [],
        "window_energy": [], "source_positions": [],
    })
    monkeypatch.setattr(engine, "build_fixed_vocal_authority", raw_authority)
    monkeypatch.setattr(engine, "_fixed_vocal_speech_window_views", lambda *_a, **_k: {
        "base_embeddings": [], "shifted_embeddings": [], "source_positions": [],
        "speech_seconds": [], "window_samples": [],
    })
    monkeypatch.setattr(engine.multi_gender, "classify_vocal_window_gender_probabilities",
                        lambda *_a, **_k: [])
    monkeypatch.setattr(engine, "build_gender_constrained_speech_authority", register_authority)
    monkeypatch.setattr(engine, "_smart_proven_speech_fallback", fallback)

    result = asyncio.run(auto_multi_speaker.run_local_acoustic_diarization_off_event_loop(
        pcm_path, words, duration_seconds=20.0,
        gender_source_original=True, minimum_speakers=1,
    ))

    assert result["detected_speaker_count"] == count
    assert result["smart_acoustic_generic"] is True
    assert calls == (["extract", 3, 1] if count < 3 else ["extract", 3])
