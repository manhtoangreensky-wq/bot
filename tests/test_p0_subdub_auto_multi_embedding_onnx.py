from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path

import numpy as np
import pytest

from services import subdub_multi_speaker_embedding_onnx as service
from services import subdub_speaker_cast as speaker_cast


@dataclass
class FakeIO:
    name: str
    shape: list[object]
    type: str


class FakeSession:
    def __init__(self, *, inputs, outputs, providers):
        self._inputs = list(inputs)
        self._outputs = list(outputs)
        self._providers = list(providers)

    def get_inputs(self):
        return list(self._inputs)

    def get_outputs(self):
        return list(self._outputs)

    def get_providers(self):
        return list(self._providers)


def write_exact_asset_fixture(tmp_path: Path):
    model = tmp_path / "voxceleb_resnet34.onnx"
    model.write_bytes(b"exact-test-model")
    notices = tuple(
        tmp_path / name
        for name in (
            "WESPEAKER.LICENSE.APACHE-2.0",
            "VOXCELEB.MODEL.LICENSE.CC-BY-4.0",
            "THIRD_PARTY_NOTICES.md",
        )
    )
    for notice in notices:
        notice.write_text("nonempty license fixture", encoding="utf-8")
    return model, notices


def valid_fake_session():
    return FakeSession(
        inputs=[FakeIO("feats", ["B", "T", 80], "tensor(float)")],
        outputs=[FakeIO("embs", ["B", 256], "tensor(float)")],
        providers=["CPUExecutionProvider"],
    )


def configure_test_assets(monkeypatch, tmp_path: Path):
    model, notices = write_exact_asset_fixture(tmp_path)
    monkeypatch.setattr(service, "MODEL_PATH", model)
    monkeypatch.setattr(service, "NOTICE_PATHS", notices)
    monkeypatch.setattr(
        service,
        "MODEL_SHA256",
        hashlib.sha256(model.read_bytes()).hexdigest(),
    )
    return model, notices


def test_acoustic_model_preflight_accepts_exact_assets(monkeypatch, tmp_path):
    model, _notices = configure_test_assets(monkeypatch, tmp_path)

    result = service.model_preflight(
        session_factory=lambda *_args, **_kwargs: valid_fake_session()
    )

    assert result == {
        "ok": True,
        "status": "PASS",
        "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
        "model_bytes": len(model.read_bytes()),
        "input_name": "feats",
        "output_name": "embs",
        "embedding_dim": 256,
        "providers": ["CPUExecutionProvider"],
    }


@pytest.mark.parametrize(
    "mutation",
    ("missing_model", "empty_model", "wrong_hash", "missing_notice", "empty_notice"),
)
def test_acoustic_model_preflight_rejects_invalid_assets(
    monkeypatch,
    tmp_path,
    mutation,
):
    model, notices = configure_test_assets(monkeypatch, tmp_path)
    if mutation == "missing_model":
        model.unlink()
    elif mutation == "empty_model":
        model.write_bytes(b"")
    elif mutation == "wrong_hash":
        monkeypatch.setattr(service, "MODEL_SHA256", "0" * 64)
    elif mutation == "missing_notice":
        notices[0].unlink()
    else:
        notices[0].write_bytes(b"")

    called = []

    def forbidden_session(*_args, **_kwargs):
        called.append(True)
        return valid_fake_session()

    with pytest.raises(speaker_cast.AutoCastManualRequired):
        service.model_preflight(session_factory=forbidden_session)
    assert called == []


@pytest.mark.parametrize(
    "schema",
    (
        "missing_input",
        "extra_input",
        "wrong_input_name",
        "wrong_input_rank",
        "wrong_input_type",
        "wrong_mel_bins",
        "missing_output",
        "extra_output",
        "wrong_output_name",
        "wrong_output_rank",
        "wrong_output_type",
        "wrong_dim",
        "non_cpu_provider",
        "extra_provider",
    ),
)
def test_acoustic_model_preflight_rejects_schema_or_provider(
    monkeypatch,
    tmp_path,
    schema,
):
    configure_test_assets(monkeypatch, tmp_path)
    input_name = "wrong" if schema == "wrong_input_name" else "feats"
    input_shape = (
        ["B", 80]
        if schema == "wrong_input_rank"
        else ["B", "T", 40]
        if schema == "wrong_mel_bins"
        else ["B", "T", 80]
    )
    input_type = "tensor(double)" if schema == "wrong_input_type" else "tensor(float)"
    output_name = "wrong" if schema == "wrong_output_name" else "embs"
    output_shape = (
        [256]
        if schema == "wrong_output_rank"
        else ["B", 128]
        if schema == "wrong_dim"
        else ["B", 256]
    )
    output_type = "tensor(double)" if schema == "wrong_output_type" else "tensor(float)"
    inputs = [FakeIO(input_name, input_shape, input_type)]
    outputs = [FakeIO(output_name, output_shape, output_type)]
    if schema == "missing_input":
        inputs = []
    elif schema == "extra_input":
        inputs.append(FakeIO("extra", ["B", 1], "tensor(float)"))
    if schema == "missing_output":
        outputs = []
    elif schema == "extra_output":
        outputs.append(FakeIO("extra", ["B", 1], "tensor(float)"))
    providers = (
        ["CUDAExecutionProvider"]
        if schema == "non_cpu_provider"
        else ["CPUExecutionProvider", "AzureExecutionProvider"]
        if schema == "extra_provider"
        else ["CPUExecutionProvider"]
    )
    fake = FakeSession(inputs=inputs, outputs=outputs, providers=providers)

    with pytest.raises(speaker_cast.AutoCastManualRequired):
        service.model_preflight(session_factory=lambda *_args, **_kwargs: fake)


def test_repository_acoustic_model_and_notices_are_exact():
    assert service.MODEL_PATH.is_file()
    assert service.MODEL_PATH.stat().st_size == 26_534_127
    assert hashlib.sha256(service.MODEL_PATH.read_bytes()).hexdigest() == service.MODEL_SHA256
    assert service.MODEL_SHA256 == (
        "9fea6516d7ad6bf0a76c7689f5a49b65d330fad6dde96c91bb4435ffbfe056a1"
    )
    assert all(path.is_file() and path.stat().st_size > 0 for path in service.NOTICE_PATHS)


def test_acoustic_model_imports_onnxruntime_only_for_real_session(
    monkeypatch,
    tmp_path,
):
    configure_test_assets(monkeypatch, tmp_path)
    imported = []
    monkeypatch.setattr(service, "_load_onnxruntime", lambda: imported.append(True))

    service.model_preflight(
        session_factory=lambda *_args, **_kwargs: valid_fake_session()
    )

    assert imported == []


def acoustic_words() -> list[dict]:
    return [
        {"index": 0, "word": "one", "start": 0.0, "end": 0.2},
        {"index": 1, "word": "two", "start": 0.55, "end": 0.75},
        {"index": 2, "word": "three", "start": 1.2, "end": 1.4},
        {"index": 3, "word": "four", "start": 1.9, "end": 2.1},
        {"index": 4, "word": "five", "start": 2.6, "end": 2.8},
        {"index": 5, "word": "six", "start": 3.3, "end": 3.5},
        {"index": 6, "word": "seven", "start": 4.0, "end": 4.2},
    ]


def test_acoustic_word_timeline_and_units_preserve_every_word_once():
    words = acoustic_words()

    validated = service.validate_word_timeline(words, duration_seconds=5.0)
    units = service.build_acoustic_units(validated, duration_seconds=5.0)

    assert validated == words
    assert [index for unit in units for index in unit["word_indexes"]] == list(
        range(len(words))
    )
    assert len(units) == 6
    assert units[0] == {
        "unit_index": 0,
        "word_indexes": [0, 1],
        "start": 0.0,
        "end": 0.75,
        "original_speech_seconds": 0.4,
    }


def test_acoustic_units_split_only_after_gap_strictly_greater_than_350ms():
    words = acoustic_words()

    units = service.build_acoustic_units(words, duration_seconds=5.0)

    assert units[0]["word_indexes"] == [0, 1]
    assert units[1]["word_indexes"] == [2]


def test_acoustic_units_split_before_word_that_would_exceed_2_5_seconds():
    words = [
        {"index": 0, "word": "a", "start": 0.0, "end": 0.8},
        {"index": 1, "word": "b", "start": 0.9, "end": 1.7},
        {"index": 2, "word": "c", "start": 1.8, "end": 2.6},
        {"index": 3, "word": "d", "start": 3.1, "end": 3.3},
        {"index": 4, "word": "e", "start": 3.8, "end": 4.0},
        {"index": 5, "word": "f", "start": 4.5, "end": 4.7},
        {"index": 6, "word": "g", "start": 5.2, "end": 5.4},
        {"index": 7, "word": "h", "start": 5.9, "end": 6.1},
    ]

    units = service.build_acoustic_units(words, duration_seconds=7.0)

    assert units[0]["word_indexes"] == [0, 1]
    assert units[0]["start"] == 0.0
    assert units[0]["end"] == 1.7
    assert units[1]["word_indexes"] == [2]
    assert units[1]["start"] == 1.8
    assert units[1]["end"] == 2.6


def test_short_acoustic_unit_keeps_original_timing_for_later_zero_padding():
    units = service.build_acoustic_units(acoustic_words(), duration_seconds=5.0)

    short_unit = units[1]
    assert short_unit["start"] == 1.2
    assert short_unit["end"] == 1.4
    assert short_unit["original_speech_seconds"] == 0.2


@pytest.mark.parametrize(
    "mutation",
    (
        "not_list",
        "too_few_units",
        "wrong_index",
        "empty_text",
        "bool_time",
        "nan_time",
        "overlap",
        "past_duration",
        "duplicate_identity",
    ),
)
def test_acoustic_word_timeline_rejects_malformed_or_unsupported_input(mutation):
    words = acoustic_words()
    value: object = words
    if mutation == "not_list":
        value = {}
    elif mutation == "too_few_units":
        value = [
            {"index": index, "word": str(index), "start": index * 0.2, "end": index * 0.2 + 0.1}
            for index in range(6)
        ]
    elif mutation == "wrong_index":
        words[2]["index"] = 99
    elif mutation == "empty_text":
        words[2]["word"] = "  "
    elif mutation == "bool_time":
        words[2]["start"] = True
    elif mutation == "nan_time":
        words[2]["end"] = math.nan
    elif mutation == "overlap":
        words[2]["start"] = 0.7
    elif mutation == "past_duration":
        words[-1]["end"] = 5.1
    else:
        words.append(dict(words[-1]))

    with pytest.raises(speaker_cast.AutoCastManualRequired):
        service.build_acoustic_units(value, duration_seconds=5.0)


def test_acoustic_word_timeline_rejects_more_than_sidecar_bound():
    count = speaker_cast.MAX_SIDECAR_CUES + 1
    words = [
        {
            "index": index,
            "word": f"w{index}",
            "start": index * 0.001,
            "end": index * 0.001 + 0.0005,
        }
        for index in range(count)
    ]

    with pytest.raises(speaker_cast.AutoCastManualRequired):
        service.validate_word_timeline(words, duration_seconds=count * 0.001 + 1.0)


FBANK_GOLDEN_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "subdub_auto_multi_fbank_golden.npz"
)
FBANK_GOLDEN_SHA256 = (
    "4ce1c8bebc35ca0141bc88831672a93f9e654173cf40e0dddcd4cc664d9a7c32"
)


def deterministic_fbank_pcm() -> np.ndarray:
    indexes = np.arange(12_000, dtype=np.int64)
    return (((indexes * 7_919 + 12_345) % 65_536) - 32_768).astype(np.int16)


def test_fbank_matches_hash_locked_wespeaker_reference_fixture():
    assert hashlib.sha256(FBANK_GOLDEN_PATH.read_bytes()).hexdigest() == (
        FBANK_GOLDEN_SHA256
    )
    with np.load(FBANK_GOLDEN_PATH, allow_pickle=False) as golden:
        assert int(golden["sample_rate"]) == 16_000
        assert int(golden["sample_formula_version"]) == 1
        expected = np.asarray(golden["features"], dtype=np.float32)

    actual = service.compute_fbank(deterministic_fbank_pcm())

    assert actual.dtype == np.float32
    assert actual.shape == expected.shape == (73, 80)
    np.testing.assert_allclose(actual, expected, rtol=2e-4, atol=2e-4)
    np.testing.assert_allclose(actual.mean(axis=0), 0.0, atol=2e-5)


@pytest.mark.parametrize(
    "samples",
    (
        np.zeros((1, 400), dtype=np.int16),
        np.zeros(400, dtype=np.int32),
        np.asarray([], dtype=np.int16),
        np.zeros(399, dtype=np.int16),
        np.asarray([math.nan] + [0.0] * 399, dtype=np.float32),
        np.asarray([math.inf] + [0.0] * 399, dtype=np.float32),
    ),
)
def test_fbank_rejects_invalid_pcm_contract(samples):
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        service.compute_fbank(samples)


def test_fbank_is_deterministic_and_does_not_mutate_pcm():
    pcm = deterministic_fbank_pcm()
    before = pcm.copy()

    first = service.compute_fbank(pcm)
    second = service.compute_fbank(pcm)

    assert np.array_equal(pcm, before)
    assert np.array_equal(first, second)


def test_fbank_zero_pads_short_unit_without_mutating_authoritative_timing():
    short_unit = service.build_acoustic_units(
        acoustic_words(),
        duration_seconds=5.0,
    )[1]
    authoritative = dict(short_unit)
    pcm = deterministic_fbank_pcm()[:3_200].copy()
    pcm_before = pcm.copy()
    explicit_padding = np.pad(pcm, (0, 8_000 - pcm.size))

    actual = service.compute_fbank(pcm)
    padded_reference = service.compute_fbank(explicit_padding)

    assert actual.shape == (48, 80)
    assert np.array_equal(actual, padded_reference)
    assert np.array_equal(pcm, pcm_before)
    assert short_unit == authoritative
    assert short_unit["start"] == 1.2
    assert short_unit["end"] == 1.4


class EmbeddingFakeSession(FakeSession):
    def __init__(self, outputs, *, exception: Exception | None = None):
        super().__init__(
            inputs=[FakeIO("feats", ["B", "T", 80], "tensor(float)")],
            outputs=[FakeIO("embs", ["B", 256], "tensor(float)")],
            providers=["CPUExecutionProvider"],
        )
        self.embedding_outputs = list(outputs)
        self.exception = exception
        self.run_calls: list[tuple[list[str], dict[str, np.ndarray]]] = []

    def run(self, output_names, feeds):
        self.run_calls.append((list(output_names), dict(feeds)))
        if self.exception is not None:
            raise self.exception
        return [self.embedding_outputs[len(self.run_calls) - 1]]


def embedding_units() -> list[dict]:
    return [
        {
            "unit_index": index,
            "word_indexes": [index],
            "start": round(index * 0.6, 3),
            "end": round(index * 0.6 + 0.5, 3),
            "original_speech_seconds": 0.5,
        }
        for index in range(6)
    ]


def write_embedding_pcm(tmp_path: Path, *, zero: bool = False) -> Path:
    sample_count = 4 * service.PCM_SAMPLE_RATE
    if zero:
        samples = np.zeros(sample_count, dtype=np.int16)
    else:
        indexes = np.arange(sample_count, dtype=np.int64)
        samples = (((indexes * 3_571 + 913) % 60_000) - 30_000).astype(np.int16)
    path = tmp_path / "source.pcm"
    path.write_bytes(samples.astype("<i2", copy=False).tobytes())
    return path


def embedding_vectors(count: int = 6) -> list[np.ndarray]:
    outputs = []
    for index in range(count):
        value = np.zeros((1, service.EMBEDDING_DIM), dtype=np.float32)
        value[0, index] = np.float32(index + 1)
        outputs.append(value)
    return outputs


def test_embedding_runner_reads_each_unit_and_returns_l2_normalized_rows(
    monkeypatch,
    tmp_path,
):
    configure_test_assets(monkeypatch, tmp_path)
    pcm_path = write_embedding_pcm(tmp_path)
    session = EmbeddingFakeSession(embedding_vectors())
    factories = []

    def factory(*args, **kwargs):
        factories.append((args, kwargs))
        return session

    result = service.extract_unit_embeddings(
        str(pcm_path),
        embedding_units(),
        deadline_monotonic=10**12,
        stop_requested=lambda: False,
        session_factory=factory,
    )

    assert result.shape == (6, service.EMBEDDING_DIM)
    assert result.dtype == np.float32
    np.testing.assert_allclose(np.linalg.norm(result, axis=1), 1.0, atol=1e-6)
    assert len(factories) == 1
    assert len(session.run_calls) == 6
    for output_names, feeds in session.run_calls:
        assert output_names == [service.MODEL_OUTPUT_NAME]
        assert list(feeds) == [service.MODEL_INPUT_NAME]
        features = feeds[service.MODEL_INPUT_NAME]
        assert features.dtype == np.float32
        assert features.ndim == 3
        assert features.shape[0] == 1
        assert features.shape[2] == service.MEL_BINS


@pytest.mark.parametrize(
    "mutation",
    (
        "zero_norm",
        "nan",
        "inf",
        "wrong_rank",
        "wrong_dimension",
        "inconsistent_dimension",
    ),
)
def test_embedding_runner_rejects_invalid_model_outputs(monkeypatch, tmp_path, mutation):
    configure_test_assets(monkeypatch, tmp_path)
    pcm_path = write_embedding_pcm(tmp_path)
    outputs = embedding_vectors()
    if mutation == "zero_norm":
        outputs[0] = np.zeros((1, service.EMBEDDING_DIM), dtype=np.float32)
    elif mutation == "nan":
        outputs[0][0, 0] = np.nan
    elif mutation == "inf":
        outputs[0][0, 0] = np.inf
    elif mutation == "wrong_rank":
        outputs[0] = np.zeros(service.EMBEDDING_DIM, dtype=np.float32)
    elif mutation == "wrong_dimension":
        outputs[0] = np.ones((1, 128), dtype=np.float32)
    else:
        outputs[1] = np.ones((1, 255), dtype=np.float32)
    session = EmbeddingFakeSession(outputs)

    with pytest.raises(speaker_cast.AutoCastManualRequired):
        service.extract_unit_embeddings(
            str(pcm_path),
            embedding_units(),
            deadline_monotonic=10**12,
            stop_requested=lambda: False,
            session_factory=lambda *_args, **_kwargs: session,
        )

    assert service._EMBEDDING_LOCK.acquire(blocking=False)
    service._EMBEDDING_LOCK.release()


@pytest.mark.parametrize(
    "mutation",
    ("missing_pcm", "misaligned_pcm", "zero_energy", "invalid_units"),
)
def test_embedding_runner_rejects_invalid_pcm_or_units_before_inference(
    monkeypatch,
    tmp_path,
    mutation,
):
    configure_test_assets(monkeypatch, tmp_path)
    pcm_path = write_embedding_pcm(tmp_path, zero=mutation == "zero_energy")
    units: object = embedding_units()
    if mutation == "missing_pcm":
        pcm_path.unlink()
    elif mutation == "misaligned_pcm":
        pcm_path.write_bytes(b"\x00")
    elif mutation == "invalid_units":
        units = []
    called = []

    with pytest.raises(speaker_cast.AutoCastManualRequired):
        service.extract_unit_embeddings(
            str(pcm_path),
            units,
            deadline_monotonic=10**12,
            stop_requested=lambda: False,
            session_factory=lambda *_args, **_kwargs: called.append(True),
        )

    assert called == []


@pytest.mark.parametrize("boundary", ("deadline", "stopped", "lock_busy"))
def test_embedding_runner_fails_before_session_at_resource_boundary(
    monkeypatch,
    tmp_path,
    boundary,
):
    configure_test_assets(monkeypatch, tmp_path)
    pcm_path = write_embedding_pcm(tmp_path)
    called = []
    acquired = False
    if boundary == "lock_busy":
        acquired = service._EMBEDDING_LOCK.acquire(blocking=False)
        assert acquired
    try:
        with pytest.raises(speaker_cast.AutoCastManualRequired):
            service.extract_unit_embeddings(
                str(pcm_path),
                embedding_units(),
                deadline_monotonic=-1.0 if boundary == "deadline" else 10**12,
                stop_requested=lambda: boundary == "stopped",
                session_factory=lambda *_args, **_kwargs: called.append(True),
            )
    finally:
        if acquired:
            service._EMBEDDING_LOCK.release()
    assert called == []


def test_embedding_runner_releases_lock_after_session_exception(monkeypatch, tmp_path):
    configure_test_assets(monkeypatch, tmp_path)
    pcm_path = write_embedding_pcm(tmp_path)
    session = EmbeddingFakeSession([], exception=RuntimeError("fixture failure"))

    with pytest.raises(speaker_cast.AutoCastManualRequired):
        service.extract_unit_embeddings(
            str(pcm_path),
            embedding_units(),
            deadline_monotonic=10**12,
            stop_requested=lambda: False,
            session_factory=lambda *_args, **_kwargs: session,
        )

    assert service._EMBEDDING_LOCK.acquire(blocking=False)
    service._EMBEDDING_LOCK.release()


def clustering_payload(
    speaker_count: int,
    *,
    rows_per_speaker: int = 10,
    speech_seconds: list[float] | None = None,
    source_positions: list[float] | None = None,
) -> dict:
    rows = []
    for speaker in range(speaker_count):
        center = np.zeros(max(8, speaker_count), dtype=np.float32)
        center[speaker] = 1.0
        rows.extend([center.copy() for _ in range(rows_per_speaker)])
    count = len(rows)
    return {
        "embeddings": np.stack(rows),
        "source_positions": list(source_positions or range(count)),
        "speech_seconds": list(speech_seconds or [0.5] * count),
        "expected_speaker_count": 99,
        "provider_speaker_labels": ["fabricated"] * count,
    }


@pytest.mark.parametrize("speaker_count", (3, 5, 8))
def test_cluster_selects_literal_supported_speaker_count(speaker_count):
    payload = clustering_payload(speaker_count)
    expected_labels = [
        speaker
        for speaker in range(speaker_count)
        for _ in range(10)
    ]

    result = service.spectral_cluster_embeddings(payload, payload)

    assert result["ok"] is True
    assert result["status"] == "PASS"
    assert result["speaker_count"] == speaker_count
    assert result["labels"] == expected_labels
    assert result["cluster_sizes"] == [10] * speaker_count
    assert result["stability_pass"] is True
    assert result["algorithm_version"] == service.ALGORITHM_VERSION


@pytest.mark.parametrize("speaker_count", (2, 9))
def test_cluster_rejects_count_outside_three_to_eight(speaker_count):
    payload = clustering_payload(speaker_count)

    with pytest.raises(speaker_cast.AutoCastManualRequired):
        service.spectral_cluster_embeddings(payload, payload)


@pytest.mark.parametrize("mutation", ("too_few", "nan", "inf", "zero_norm", "shape_mismatch"))
def test_cluster_rejects_invalid_embedding_matrix(mutation):
    base = clustering_payload(3)
    shifted = clustering_payload(3)
    if mutation == "too_few":
        base["embeddings"] = base["embeddings"][:5]
        base["source_positions"] = base["source_positions"][:5]
        base["speech_seconds"] = base["speech_seconds"][:5]
        shifted = base
    elif mutation == "nan":
        base["embeddings"][0, 0] = np.nan
    elif mutation == "inf":
        base["embeddings"][0, 0] = np.inf
    elif mutation == "zero_norm":
        base["embeddings"][0] = 0.0
    else:
        shifted["embeddings"] = shifted["embeddings"][:-1]
        shifted["source_positions"] = shifted["source_positions"][:-1]
        shifted["speech_seconds"] = shifted["speech_seconds"][:-1]

    with pytest.raises(speaker_cast.AutoCastManualRequired):
        service.spectral_cluster_embeddings(base, shifted)


def test_cluster_rejects_matrix_above_bounded_unit_limit(monkeypatch):
    matrix = np.ones((1_001, 8), dtype=np.float32)
    called = []

    def forbidden(_embeddings):
        called.append(True)
        raise AssertionError("oversized O(N^2) matrix must not be allocated")

    monkeypatch.setattr(service, "_pruned_similarity", forbidden)

    with pytest.raises(speaker_cast.AutoCastManualRequired):
        service.spectral_cluster_embeddings(matrix, matrix)
    assert called == []


def test_cluster_rejects_base_shifted_k_disagreement():
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        service.spectral_cluster_embeddings(
            clustering_payload(3),
            clustering_payload(5),
        )


def test_cluster_rejects_base_shifted_assignment_disagreement():
    base = clustering_payload(3)
    shifted = clustering_payload(3)
    shifted["embeddings"][0] = shifted["embeddings"][10]

    with pytest.raises(speaker_cast.AutoCastManualRequired):
        service.spectral_cluster_embeddings(base, shifted)


def test_cluster_rejects_tiny_speech_support():
    speech = [0.05] * 10 + [0.5] * 20
    payload = clustering_payload(
        3,
        rows_per_speaker=10,
        speech_seconds=speech,
    )

    with pytest.raises(speaker_cast.AutoCastManualRequired):
        service.spectral_cluster_embeddings(payload, payload)


@pytest.mark.parametrize(
    "labels",
    (
        np.asarray([0] + [1] * 10 + [2] * 10, dtype=np.int64),
        np.asarray([0] * 10 + [2] * 10, dtype=np.int64),
    ),
)
def test_cluster_support_rejects_singleton_or_empty_cluster(labels):
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        service._validate_cluster_support(
            labels,
            np.full(labels.shape[0], 0.5, dtype=np.float64),
            3,
        )


def test_cluster_canonical_labels_follow_source_position_after_permutation():
    original = clustering_payload(3)
    permutation = np.asarray(
        [20, 10, 0]
        + [index for index in range(30) if index not in {0, 10, 20}],
        dtype=np.int64,
    )
    permuted = {
        "embeddings": original["embeddings"][permutation],
        "source_positions": [original["source_positions"][index] for index in permutation],
        "speech_seconds": [original["speech_seconds"][index] for index in permutation],
    }

    original_result = service.spectral_cluster_embeddings(original, original)
    permuted_result = service.spectral_cluster_embeddings(permuted, permuted)
    restored = np.empty(30, dtype=np.int64)
    restored[permutation] = np.asarray(permuted_result["labels"])

    assert restored.tolist() == original_result["labels"]


def test_cluster_ignores_provider_labels_and_expected_count_hints():
    payload = clustering_payload(5)
    clean = {
        key: value
        for key, value in payload.items()
        if key in {"embeddings", "source_positions", "speech_seconds"}
    }

    hinted = service.spectral_cluster_embeddings(payload, payload)
    unhinted = service.spectral_cluster_embeddings(clean, clean)

    assert hinted == unhinted


def test_cluster_rejects_nonconvergence(monkeypatch):
    monkeypatch.setattr(service, "KMEANS_MAX_ITERATIONS", 0)
    payload = clustering_payload(3)

    with pytest.raises(speaker_cast.AutoCastManualRequired):
        service.spectral_cluster_embeddings(payload, payload)


def test_cluster_replay_is_byte_deterministic():
    payload = clustering_payload(5)

    first = service.spectral_cluster_embeddings(payload, payload)
    second = service.spectral_cluster_embeddings(payload, payload)

    assert first == second


def test_cluster_eigengap_selects_only_within_three_to_eight():
    measured = np.asarray(
        [
            0.0,
            0.71285373,
            2.15419693,
            2.34119563,
            2.60387157,
            3.63415394,
            3.76249787,
            4.39807630,
            4.73579320,
            5.32348514,
        ],
        dtype=np.float64,
    )

    assert service._select_speaker_count_from_eigenvalues(measured) == 5


def test_cluster_returns_bounded_acoustic_unit_confidences():
    payload = clustering_payload(3)

    result = service.spectral_cluster_embeddings(payload, payload)

    assert len(result["unit_confidences"]) == 30
    assert all(0.0 <= value <= 1.0 for value in result["unit_confidences"])
    assert "embeddings" not in result
    assert "centroids" not in result


def test_clustered_segments_preserve_word_order_coverage_and_boundaries():
    words = acoustic_words()
    units = service.build_acoustic_units(words, duration_seconds=5.0)
    cluster_result = {
        "labels": [0, 1, 1, 2, 0, 2],
        "unit_confidences": [0.91, 0.82, 0.79, 0.88, 0.77, 0.93],
    }

    segments = service.build_clustered_segments(words, units, cluster_result)

    assert [item["text"] for item in segments] == [
        "one two",
        "three four",
        "five",
        "six",
        "seven",
    ]
    assert [(item["start"], item["end"]) for item in segments] == [
        (0.0, 0.75),
        (1.2, 2.1),
        (2.6, 2.8),
        (3.3, 3.5),
        (4.0, 4.2),
    ]
    assert [item["speaker"] for item in segments] == [0, 1, 2, 0, 2]
    assert [item["speaker_id"] for item in segments] == [
        "chunk_00:speaker_0",
        "chunk_00:speaker_1",
        "chunk_00:speaker_2",
        "chunk_00:speaker_0",
        "chunk_00:speaker_2",
    ]
    assert [item["speaker_confidence"] for item in segments] == [
        0.91,
        0.79,
        0.88,
        0.77,
        0.93,
    ]
    assert [item["index"] for item in segments] == [1, 2, 3, 4, 5]
    assert len({item["cue_id"] for item in segments}) == len(segments)
    assert all(item["chunk_index"] == 0 for item in segments)


@pytest.mark.parametrize(
    "mutation",
    ("missing_label", "extra_label", "invalid_label", "missing_word", "bad_confidence"),
)
def test_clustered_segments_fail_closed_on_coverage_or_label_mismatch(mutation):
    words = acoustic_words()
    units = service.build_acoustic_units(words, duration_seconds=5.0)
    labels: object = {
        "labels": [0, 1, 1, 2, 0, 2],
        "unit_confidences": [0.9] * 6,
    }
    if mutation == "missing_label":
        labels["labels"] = labels["labels"][:-1]
    elif mutation == "extra_label":
        labels["labels"] = labels["labels"] + [1]
    elif mutation == "invalid_label":
        labels["labels"][0] = -1
    elif mutation == "missing_word":
        units[0]["word_indexes"] = [0]
    else:
        labels["unit_confidences"][0] = math.nan

    with pytest.raises(speaker_cast.AutoCastManualRequired):
        service.build_clustered_segments(words, units, labels)


def thirty_acoustic_words() -> list[dict]:
    return [
        {
            "index": index,
            "word": f"word{index}",
            "start": round(index * 0.6, 3),
            "end": round(index * 0.6 + 0.2, 3),
        }
        for index in range(30)
    ]


def test_diarize_word_timeline_composes_two_views_and_bounded_result(monkeypatch):
    words = thirty_acoustic_words()
    matrix = clustering_payload(3)["embeddings"]
    calls = []

    def fake_extract(
        pcm_path,
        plan,
        *,
        deadline_monotonic,
        stop_requested,
        session_factory=None,
        feature_shift_samples=0,
    ):
        calls.append(
            {
                "pcm_path": pcm_path,
                "unit_count": len(plan["windows"]),
                "deadline": deadline_monotonic,
                "stopped": stop_requested(),
                "session_factory": session_factory,
                "shift": feature_shift_samples,
            }
        )
        return matrix.copy()

    monkeypatch.setattr(
        service,
        "extract_acoustic_subsegment_embeddings",
        fake_extract,
    )
    result = service.diarize_word_timeline(
        "fixture.pcm",
        words,
        duration_seconds=18.0,
        deadline_monotonic=10**12,
        stop_requested=lambda: False,
        session_factory="fixture-session",
    )

    assert [item["shift"] for item in calls] == [0, 5]
    assert all(item["unit_count"] == 30 for item in calls)
    assert result["ok"] is True
    assert result["status"] == "PASS"
    assert result["provider"] == "local_wespeaker_resnet34_spectral"
    assert result["detected_speaker_count"] == 3
    assert result["model_sha256"] == service.MODEL_SHA256
    assert result["algorithm_version"] == service.ALGORITHM_VERSION
    assert result["word_count"] == 30
    assert result["unit_count"] == 30
    assert result["embedding_window_count"] == 60
    assert result["cluster_sizes"] == [10, 10, 10]
    assert result["stability_pass"] is True
    assert result["word_coverage_count"] == 30
    assert len(result["segments"]) == 3
    assert len({item["speaker_id"] for item in result["segments"]}) == 3
    for forbidden in ("embeddings", "centroids", "pcm_path", "word_timeline"):
        assert forbidden not in result


def test_diarize_word_timeline_propagates_fail_closed_embedding_boundary(monkeypatch):
    def fail(*_args, **_kwargs):
        raise speaker_cast.AutoCastManualRequired()

    monkeypatch.setattr(service, "extract_unit_embeddings", fail)

    with pytest.raises(speaker_cast.AutoCastManualRequired):
        service.diarize_word_timeline(
            "fixture.pcm",
            thirty_acoustic_words(),
            duration_seconds=18.0,
            deadline_monotonic=10**12,
            stop_requested=lambda: False,
        )


def test_acoustic_subsegments_match_wespeaker_window_period_and_short_repeat():
    regions = [
        {"index": 0, "start": 0.0, "end": 0.5},
        {"index": 1, "start": 1.0, "end": 2.0},
        {"index": 2, "start": 2.2, "end": 4.2},
    ]

    plan = service.build_acoustic_subsegment_plan(
        regions,
        duration_seconds=5.0,
    )

    assert plan["region_count"] == 3
    assert plan["run_count"] == 2
    assert plan["window_seconds"] == 1.5
    assert plan["period_seconds"] == 0.75
    assert plan["runs"][0]["region_indexes"] == [0]
    assert plan["runs"][0]["speech_seconds"] == 0.5
    assert plan["windows"][0] == {
        "window_index": 0,
        "run_index": 0,
        "speech_start_seconds": 0.0,
        "speech_end_seconds": 0.5,
        "feature_seconds": 1.5,
        "repeat_to_fill": True,
        "source_position": 0.0,
    }
    assert plan["runs"][1]["region_indexes"] == [1, 2]
    assert plan["runs"][1]["speech_seconds"] == 3.0
    assert [
        (item["speech_start_seconds"], item["speech_end_seconds"])
        for item in plan["windows"][1:]
    ] == [(0.0, 1.5), (0.75, 2.25), (1.5, 3.0)]


def test_acoustic_subsegment_plan_rejects_overlapping_regions():
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        service.build_acoustic_subsegment_plan(
            [
                {"index": 0, "start": 0.0, "end": 1.0},
                {"index": 1, "start": 0.9, "end": 1.5},
            ],
            duration_seconds=2.0,
        )


def test_region_labels_use_nearest_subsegment_center_without_majority_override():
    plan = {
        "regions": [
            {"index": 0, "run_index": 0, "speech_start_seconds": 0.0, "speech_end_seconds": 0.5},
            {"index": 1, "run_index": 0, "speech_start_seconds": 1.0, "speech_end_seconds": 2.0},
            {"index": 2, "run_index": 0, "speech_start_seconds": 2.0, "speech_end_seconds": 2.5},
        ],
        "windows": [
            {"window_index": 0, "run_index": 0, "speech_start_seconds": 0.0, "speech_end_seconds": 1.5},
            {"window_index": 1, "run_index": 0, "speech_start_seconds": 0.75, "speech_end_seconds": 2.25},
            {"window_index": 2, "run_index": 0, "speech_start_seconds": 1.5, "speech_end_seconds": 2.5},
        ],
    }
    cluster_result = {
        "speaker_count": 3,
        "labels": [0, 1, 2],
        "unit_confidences": [0.8, 0.7, 0.9],
    }

    mapped = service.map_subsegment_clusters_to_regions(plan, cluster_result)

    assert mapped == {
        "labels": [0, 1, 2],
        "unit_confidences": [0.8, 0.7, 0.9],
        "speaker_count": 3,
    }


def test_subsegment_embedding_runner_executes_every_planned_window(
    monkeypatch,
    tmp_path,
):
    configure_test_assets(monkeypatch, tmp_path)
    pcm_path = write_embedding_pcm(tmp_path)
    regions = [
        {"index": index, "start": index * 0.6, "end": index * 0.6 + 0.5}
        for index in range(6)
    ]
    plan = service.build_acoustic_subsegment_plan(
        regions,
        duration_seconds=4.0,
    )
    outputs = embedding_vectors(plan["window_count"])
    session = EmbeddingFakeSession(outputs)

    result = service.extract_acoustic_subsegment_embeddings(
        str(pcm_path),
        plan,
        deadline_monotonic=10**12,
        stop_requested=lambda: False,
        session_factory=lambda *_args, **_kwargs: session,
        feature_shift_samples=0,
    )

    assert result.shape == (plan["window_count"], service.EMBEDDING_DIM)
    assert result.dtype == np.float32
    assert len(session.run_calls) == plan["window_count"]
    np.testing.assert_allclose(np.linalg.norm(result, axis=1), 1.0, atol=1e-6)


def test_shifted_subsegment_frontend_does_not_append_repeated_tail(
    monkeypatch,
    tmp_path,
):
    configure_test_assets(monkeypatch, tmp_path)
    pcm_path = write_embedding_pcm(tmp_path)
    regions = [
        {"index": index, "start": index * 0.6, "end": index * 0.6 + 0.5}
        for index in range(6)
    ]
    plan = service.build_acoustic_subsegment_plan(
        regions,
        duration_seconds=4.0,
    )
    outputs = embedding_vectors(plan["window_count"])
    session = EmbeddingFakeSession(outputs)
    sample_lengths = []

    def capture_fbank(samples):
        sample_lengths.append(len(samples))
        return np.ones((10, service.MEL_BINS), dtype=np.float32)

    monkeypatch.setattr(service, "compute_fbank", capture_fbank)

    service.extract_acoustic_subsegment_embeddings(
        str(pcm_path),
        plan,
        deadline_monotonic=10**12,
        stop_requested=lambda: False,
        session_factory=lambda *_args, **_kwargs: session,
        feature_shift_samples=80,
    )

    assert sample_lengths == [23_920] * plan["window_count"]


def test_two_views_accept_window_differences_when_every_region_is_stable(monkeypatch):
    plan = {
        "regions": [
            {"index": 0, "run_index": 0, "speech_start_seconds": 0.0, "speech_end_seconds": 0.3},
            {"index": 1, "run_index": 0, "speech_start_seconds": 1.4, "speech_end_seconds": 1.6},
            {"index": 2, "run_index": 0, "speech_start_seconds": 2.7, "speech_end_seconds": 3.0},
            {"index": 3, "run_index": 0, "speech_start_seconds": 3.2, "speech_end_seconds": 3.5},
        ],
        "windows": [
            {"window_index": 0, "run_index": 0, "speech_start_seconds": 0.0, "speech_end_seconds": 0.8, "source_position": 0.0},
            {"window_index": 1, "run_index": 0, "speech_start_seconds": 0.5, "speech_end_seconds": 1.3, "source_position": 0.5},
            {"window_index": 2, "run_index": 0, "speech_start_seconds": 1.1, "speech_end_seconds": 1.9, "source_position": 1.1},
            {"window_index": 3, "run_index": 0, "speech_start_seconds": 1.7, "speech_end_seconds": 2.5, "source_position": 1.7},
            {"window_index": 4, "run_index": 0, "speech_start_seconds": 2.2, "speech_end_seconds": 3.0, "source_position": 2.2},
            {"window_index": 5, "run_index": 0, "speech_start_seconds": 3.0, "speech_end_seconds": 3.5, "source_position": 3.0},
        ],
    }
    labels = iter(
        (
            np.asarray([0, 1, 1, 2, 2, 2], dtype=np.int64),
            np.asarray([0, 0, 1, 1, 2, 2], dtype=np.int64),
        )
    )
    monkeypatch.setattr(
        service,
        "_stable_cluster_view",
        lambda *_args, **_kwargs: (3, next(labels), np.arange(6, dtype=np.float64)),
    )
    monkeypatch.setattr(service, "_validate_cluster_support", lambda *_args: [2, 2, 1])
    monkeypatch.setattr(service, "_cluster_unit_confidences", lambda _m, _l, _k: [0.8] * 6)
    matrix = np.eye(6, dtype=np.float32)

    result = service.stable_cluster_acoustic_regions(plan, matrix, matrix)

    assert result["speaker_count"] == 3
    assert result["region_labels"] == [0, 1, 2, 2]
    assert result["region_confidences"] == [0.8, 0.8, 0.8, 0.8]
    assert result["stability_pass"] is True


def test_two_views_align_numeric_label_permutation_before_stability_check(
    monkeypatch,
):
    plan = {
        "regions": [
            {"index": index, "run_index": 0, "speech_start_seconds": index, "speech_end_seconds": index + 0.2}
            for index in range(6)
        ],
        "windows": [
            {"window_index": index, "run_index": 0, "speech_start_seconds": index, "speech_end_seconds": index + 0.8, "source_position": index}
            for index in range(6)
        ],
    }
    labels = iter(
        (
            np.asarray([0, 0, 1, 1, 2, 2], dtype=np.int64),
            np.asarray([1, 1, 2, 2, 0, 0], dtype=np.int64),
        )
    )
    monkeypatch.setattr(
        service,
        "_stable_cluster_view",
        lambda *_args, **_kwargs: (3, next(labels), np.arange(6, dtype=np.float64)),
    )
    monkeypatch.setattr(service, "_validate_cluster_support", lambda *_args: [2, 2, 2])
    monkeypatch.setattr(service, "_cluster_unit_confidences", lambda _m, _l, _k: [0.8] * 6)
    matrix = np.eye(6, dtype=np.float32)

    result = service.stable_cluster_acoustic_regions(plan, matrix, matrix)

    assert result["speaker_count"] == 3
    assert result["region_labels"] == [0, 0, 1, 1, 2, 2]
    assert result["stability_pass"] is True


def test_two_views_reject_any_region_assignment_difference(monkeypatch):
    plan = {
        "regions": [
            {"index": 0, "run_index": 0, "speech_start_seconds": 0.0, "speech_end_seconds": 0.3},
            {"index": 1, "run_index": 0, "speech_start_seconds": 1.4, "speech_end_seconds": 1.6},
            {"index": 2, "run_index": 0, "speech_start_seconds": 2.7, "speech_end_seconds": 3.0},
            {"index": 3, "run_index": 0, "speech_start_seconds": 3.2, "speech_end_seconds": 3.5},
        ],
        "windows": [
            {"window_index": 0, "run_index": 0, "speech_start_seconds": 0.0, "speech_end_seconds": 0.8, "source_position": 0.0},
            {"window_index": 1, "run_index": 0, "speech_start_seconds": 0.5, "speech_end_seconds": 1.3, "source_position": 0.5},
            {"window_index": 2, "run_index": 0, "speech_start_seconds": 1.1, "speech_end_seconds": 1.9, "source_position": 1.1},
            {"window_index": 3, "run_index": 0, "speech_start_seconds": 1.7, "speech_end_seconds": 2.5, "source_position": 1.7},
            {"window_index": 4, "run_index": 0, "speech_start_seconds": 2.2, "speech_end_seconds": 3.0, "source_position": 2.2},
            {"window_index": 5, "run_index": 0, "speech_start_seconds": 3.0, "speech_end_seconds": 3.5, "source_position": 3.0},
        ],
    }
    labels = iter(
        (
            np.asarray([0, 1, 1, 2, 2, 2], dtype=np.int64),
            np.asarray([0, 0, 2, 1, 2, 2], dtype=np.int64),
        )
    )
    monkeypatch.setattr(
        service,
        "_stable_cluster_view",
        lambda *_args, **_kwargs: (3, next(labels), np.arange(6, dtype=np.float64)),
    )
    monkeypatch.setattr(service, "_validate_cluster_support", lambda *_args: [2, 2, 1])
    monkeypatch.setattr(service, "_cluster_unit_confidences", lambda _m, _l, _k: [0.8] * 6)
    matrix = np.eye(6, dtype=np.float32)

    with pytest.raises(speaker_cast.AutoCastManualRequired):
        service.stable_cluster_acoustic_regions(plan, matrix, matrix)
