"""Hash-locked local acoustic authority for the SubDub Auto Multi lane."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

from services import subdub_speaker_cast as speaker_cast


ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "assets" / "models" / "subdub_auto_multi"
MODEL_PATH = MODEL_DIR / "voxceleb_resnet34.onnx"
NOTICE_PATHS = (
    MODEL_DIR / "WESPEAKER.LICENSE.APACHE-2.0",
    MODEL_DIR / "VOXCELEB.MODEL.LICENSE.CC-BY-4.0",
    MODEL_DIR / "THIRD_PARTY_NOTICES.md",
)

MODEL_SHA256 = "9fea6516d7ad6bf0a76c7689f5a49b65d330fad6dde96c91bb4435ffbfe056a1"
ALGORITHM_VERSION = "wespeaker-resnet34-spectral-v1"
MODEL_INPUT_NAME = "feats"
MODEL_OUTPUT_NAME = "embs"
MEL_BINS = 80
EMBEDDING_DIM = 256


def _manual_required(error: Exception | None = None) -> speaker_cast.AutoCastManualRequired:
    result = speaker_cast.AutoCastManualRequired()
    if error is not None:
        result.__cause__ = error
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _load_onnxruntime():
    import onnxruntime as ort

    return ort


def _create_real_session():
    ort = _load_onnxruntime()
    options = ort.SessionOptions()
    options.inter_op_num_threads = 1
    options.intra_op_num_threads = 1
    return ort.InferenceSession(
        str(MODEL_PATH),
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )


def model_preflight(
    *,
    session_factory: Callable | None = None,
) -> dict[str, object]:
    """Validate immutable assets and the exact CPU ONNX schema."""

    try:
        if not MODEL_PATH.is_file() or MODEL_PATH.stat().st_size <= 0:
            raise ValueError("acoustic_model_missing")
        model_sha256 = _sha256(MODEL_PATH)
        if model_sha256 != MODEL_SHA256:
            raise ValueError("acoustic_model_hash_mismatch")
        if any(not path.is_file() or path.stat().st_size <= 0 for path in NOTICE_PATHS):
            raise ValueError("acoustic_notice_missing")

        session = (
            session_factory(
                str(MODEL_PATH),
                providers=["CPUExecutionProvider"],
            )
            if session_factory is not None
            else _create_real_session()
        )
        inputs = list(session.get_inputs())
        outputs = list(session.get_outputs())
        providers = list(session.get_providers())
        if len(inputs) != 1 or len(outputs) != 1:
            raise ValueError("acoustic_model_schema_count")
        model_input = inputs[0]
        model_output = outputs[0]
        input_shape = list(model_input.shape)
        output_shape = list(model_output.shape)
        if (
            model_input.name != MODEL_INPUT_NAME
            or model_input.type != "tensor(float)"
            or len(input_shape) != 3
            or input_shape[-1] != MEL_BINS
        ):
            raise ValueError("acoustic_model_input_schema")
        if (
            model_output.name != MODEL_OUTPUT_NAME
            or model_output.type != "tensor(float)"
            or len(output_shape) != 2
            or output_shape[-1] != EMBEDDING_DIM
        ):
            raise ValueError("acoustic_model_output_schema")
        if providers != ["CPUExecutionProvider"]:
            raise ValueError("acoustic_model_provider_schema")
        return {
            "ok": True,
            "status": "PASS",
            "model_sha256": model_sha256,
            "model_bytes": MODEL_PATH.stat().st_size,
            "input_name": model_input.name,
            "output_name": model_output.name,
            "embedding_dim": EMBEDDING_DIM,
            "providers": providers,
        }
    except speaker_cast.AutoCastManualRequired:
        raise
    except Exception as exc:
        raise _manual_required(exc)
