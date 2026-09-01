from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

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
