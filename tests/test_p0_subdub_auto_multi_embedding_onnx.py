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
