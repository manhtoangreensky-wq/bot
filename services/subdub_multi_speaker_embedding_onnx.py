"""Hash-locked local acoustic authority for the SubDub Auto Multi lane."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
import threading
import time
from typing import Callable

import numpy as np

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
PCM_SAMPLE_RATE = 16_000
PCM_BYTES_PER_SAMPLE = 2
UNIT_MAX_SECONDS = 2.5
UNIT_SPLIT_GAP_SECONDS = 0.35
UNIT_MIN_FEATURE_SECONDS = 0.5
MIN_UNITS = 6
MIN_SPEAKERS = 3
MAX_SPEAKERS = 8
MAX_SOURCE_SECONDS = 300.0
FBANK_FRAME_LENGTH = 400
FBANK_FRAME_SHIFT = 160
FBANK_FFT_POINTS = 512
FBANK_FFT_BINS = FBANK_FFT_POINTS // 2

_HAMMING_WINDOW: np.ndarray | None = None
_MEL_FILTER_MATRIX: np.ndarray | None = None
_EMBEDDING_LOCK = threading.Lock()
_REAL_SESSION = None


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


def validate_word_timeline(
    words: object,
    *,
    duration_seconds: float,
) -> list[dict]:
    """Validate the same-timeline word authority without sorting or repair."""

    try:
        if type(duration_seconds) not in {int, float}:
            raise ValueError("acoustic_duration_invalid")
        duration = float(duration_seconds)
        if not math.isfinite(duration) or not 0.0 < duration <= MAX_SOURCE_SECONDS:
            raise ValueError("acoustic_duration_invalid")
        if (
            type(words) is not list
            or not words
            or len(words) > speaker_cast.MAX_SIDECAR_CUES
        ):
            raise ValueError("acoustic_word_timeline_invalid")

        validated: list[dict] = []
        identities: set[tuple[float, float, str]] = set()
        previous_start = -math.inf
        previous_end = -math.inf
        for expected_index, item in enumerate(words):
            if type(item) is not dict or type(item.get("index")) is not int:
                raise ValueError("acoustic_word_record_invalid")
            if item["index"] != expected_index:
                raise ValueError("acoustic_word_index_invalid")
            raw_word = item.get("word")
            if not isinstance(raw_word, str):
                raise ValueError("acoustic_word_text_invalid")
            word = " ".join(raw_word.split())
            if not word or word != raw_word:
                raise ValueError("acoustic_word_text_invalid")
            start_value = item.get("start")
            end_value = item.get("end")
            if (
                type(start_value) not in {int, float}
                or type(end_value) not in {int, float}
            ):
                raise ValueError("acoustic_word_time_invalid")
            start = float(start_value)
            end = float(end_value)
            if (
                not math.isfinite(start)
                or not math.isfinite(end)
                or start < 0.0
                or start >= end
                or end > duration
                or start < previous_start
                or start < previous_end
            ):
                raise ValueError("acoustic_word_time_invalid")
            identity = (start, end, word.casefold())
            if identity in identities:
                raise ValueError("acoustic_word_duplicate")
            identities.add(identity)
            validated.append(
                {
                    "index": expected_index,
                    "word": word,
                    "start": start,
                    "end": end,
                }
            )
            previous_start = start
            previous_end = end
        return validated
    except speaker_cast.AutoCastManualRequired:
        raise
    except Exception as exc:
        raise _manual_required(exc)


def build_acoustic_units(
    words: object,
    *,
    duration_seconds: float,
) -> list[dict]:
    """Group strict words into bounded acoustic units without timing mutation."""

    validated = validate_word_timeline(words, duration_seconds=duration_seconds)
    grouped: list[list[dict]] = []
    current: list[dict] = []
    for item in validated:
        if current:
            gap = round(
                float(item["start"]) - float(current[-1]["end"]),
                6,
            )
            proposed_duration = float(item["end"]) - float(current[0]["start"])
            if (
                gap > UNIT_SPLIT_GAP_SECONDS
                or proposed_duration > UNIT_MAX_SECONDS
            ):
                grouped.append(current)
                current = []
        current.append(item)
    if current:
        grouped.append(current)
    if not MIN_UNITS <= len(grouped) <= speaker_cast.MAX_SIDECAR_CUES:
        raise _manual_required(ValueError("acoustic_unit_count_invalid"))

    units: list[dict] = []
    covered_indexes: list[int] = []
    for unit_index, items in enumerate(grouped):
        word_indexes = [int(item["index"]) for item in items]
        covered_indexes.extend(word_indexes)
        original_speech_seconds = round(
            sum(float(item["end"]) - float(item["start"]) for item in items),
            6,
        )
        if not math.isfinite(original_speech_seconds) or original_speech_seconds <= 0.0:
            raise _manual_required(ValueError("acoustic_unit_speech_invalid"))
        units.append(
            {
                "unit_index": unit_index,
                "word_indexes": word_indexes,
                "start": float(items[0]["start"]),
                "end": float(items[-1]["end"]),
                "original_speech_seconds": original_speech_seconds,
            }
        )
    if covered_indexes != list(range(len(validated))):
        raise _manual_required(ValueError("acoustic_word_coverage_invalid"))
    return units


def _fbank_hamming_window() -> np.ndarray:
    global _HAMMING_WINDOW
    if _HAMMING_WINDOW is None:
        indexes = np.arange(FBANK_FRAME_LENGTH, dtype=np.float64)
        window = np.asarray(
            0.54
            - 0.46
            * np.cos(
                2.0 * np.pi * indexes / float(FBANK_FRAME_LENGTH - 1)
            ),
            dtype=np.float32,
        )
        window.setflags(write=False)
        _HAMMING_WINDOW = window
    return _HAMMING_WINDOW


def _fbank_mel_scale(frequency: float) -> np.float32:
    return np.float32(1_127.0) * np.float32(
        math.log1p(float(np.float32(frequency) / np.float32(700.0)))
    )


def _fbank_mel_filter_matrix() -> np.ndarray:
    global _MEL_FILTER_MATRIX
    if _MEL_FILTER_MATRIX is not None:
        return _MEL_FILTER_MATRIX

    matrix = np.zeros((FBANK_FFT_BINS, MEL_BINS), dtype=np.float32)
    fft_bin_width = np.float32(PCM_SAMPLE_RATE / FBANK_FFT_POINTS)
    low_mel = _fbank_mel_scale(20.0)
    high_mel = _fbank_mel_scale(PCM_SAMPLE_RATE / 2)
    delta = np.float32((high_mel - low_mel) / np.float32(MEL_BINS + 1))
    for mel_index in range(MEL_BINS):
        left = np.float32(low_mel + np.float32(mel_index) * delta)
        center = np.float32(low_mel + np.float32(mel_index + 1) * delta)
        right = np.float32(low_mel + np.float32(mel_index + 2) * delta)
        for fft_index in range(FBANK_FFT_BINS):
            mel = _fbank_mel_scale(float(np.float32(fft_bin_width * fft_index)))
            if not left < mel < right:
                continue
            if mel <= center:
                weight = np.float32((mel - left) / (center - left))
            else:
                weight = np.float32((right - mel) / (right - center))
            matrix[fft_index, mel_index] = weight
    if np.any(np.count_nonzero(matrix, axis=0) == 0):
        raise _manual_required(ValueError("acoustic_mel_filter_invalid"))
    matrix.setflags(write=False)
    _MEL_FILTER_MATRIX = matrix
    return _MEL_FILTER_MATRIX


def compute_fbank(pcm_samples: np.ndarray) -> np.ndarray:
    """Compute the bounded WeSpeaker-compatible NumPy fbank frontend."""

    try:
        if (
            not isinstance(pcm_samples, np.ndarray)
            or pcm_samples.ndim != 1
            or pcm_samples.dtype != np.dtype(np.int16)
            or pcm_samples.size < FBANK_FRAME_LENGTH
        ):
            raise ValueError("acoustic_pcm_contract_invalid")
        source_sample_count = int(pcm_samples.size)
        if source_sample_count > int(MAX_SOURCE_SECONDS * PCM_SAMPLE_RATE):
            raise ValueError("acoustic_pcm_duration_invalid")

        wave = pcm_samples.astype(np.float32, copy=True) / np.float32(2**15)
        minimum_feature_samples = int(UNIT_MIN_FEATURE_SECONDS * PCM_SAMPLE_RATE)
        if wave.size < minimum_feature_samples:
            wave = np.pad(
                wave,
                (0, minimum_feature_samples - int(wave.size)),
                mode="constant",
            )
        sample_count = int(wave.size)
        frame_count = 1 + (sample_count - FBANK_FRAME_LENGTH) // FBANK_FRAME_SHIFT
        shape = (frame_count, FBANK_FRAME_LENGTH)
        strides = (
            wave.strides[0] * FBANK_FRAME_SHIFT,
            wave.strides[0],
        )
        frames = np.lib.stride_tricks.as_strided(
            wave,
            shape=shape,
            strides=strides,
            writeable=False,
        ).copy()
        frames -= np.mean(frames, axis=1, dtype=np.float32, keepdims=True)
        emphasized = frames.copy()
        emphasized[:, 1:] = (
            frames[:, 1:] - np.float32(0.97) * frames[:, :-1]
        )
        emphasized[:, 0] = frames[:, 0] - np.float32(0.97) * frames[:, 0]
        emphasized *= _fbank_hamming_window()[None, :]

        padded = np.zeros((frame_count, FBANK_FFT_POINTS), dtype=np.float32)
        padded[:, :FBANK_FRAME_LENGTH] = emphasized
        spectrum = np.fft.rfft(padded.astype(np.float64), axis=1)[
            :, :FBANK_FFT_BINS
        ]
        power = np.asarray(
            spectrum.real * spectrum.real + spectrum.imag * spectrum.imag,
            dtype=np.float32,
        )
        mel_energy = np.asarray(
            power @ _fbank_mel_filter_matrix(),
            dtype=np.float32,
        )
        mel_energy = np.maximum(mel_energy, np.finfo(np.float32).eps)
        features = np.asarray(np.log(mel_energy), dtype=np.float32)
        features -= np.mean(features, axis=0, dtype=np.float32, keepdims=True)
        if (
            features.shape != (frame_count, MEL_BINS)
            or not np.isfinite(features).all()
        ):
            raise ValueError("acoustic_feature_invalid")
        return np.asarray(features, dtype=np.float32)
    except speaker_cast.AutoCastManualRequired:
        raise
    except Exception as exc:
        raise _manual_required(exc)


def _embedding_boundary_check(
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
) -> None:
    if type(deadline_monotonic) not in {int, float}:
        raise _manual_required(ValueError("acoustic_deadline_invalid"))
    deadline = float(deadline_monotonic)
    if not math.isfinite(deadline) or time.monotonic() >= deadline:
        raise _manual_required(TimeoutError("acoustic_embedding_timeout"))
    if not callable(stop_requested) or bool(stop_requested()):
        raise _manual_required(RuntimeError("acoustic_embedding_cancelled"))


def _embedding_session(session_factory: Callable | None):
    global _REAL_SESSION
    if session_factory is not None:
        if not callable(session_factory):
            raise _manual_required(ValueError("acoustic_session_factory_invalid"))
        session = session_factory(
            str(MODEL_PATH),
            providers=["CPUExecutionProvider"],
        )
    else:
        if _REAL_SESSION is None:
            _REAL_SESSION = _create_real_session()
        session = _REAL_SESSION
    model_preflight(session_factory=lambda *_args, **_kwargs: session)
    return session


def _validated_embedding_units(
    units: object,
    *,
    pcm_duration_seconds: float,
) -> list[dict]:
    if (
        type(units) is not list
        or not MIN_UNITS <= len(units) <= speaker_cast.MAX_SIDECAR_CUES
    ):
        raise _manual_required(ValueError("acoustic_embedding_units_invalid"))
    validated: list[dict] = []
    previous_end = -math.inf
    for expected_index, item in enumerate(units):
        if type(item) is not dict or type(item.get("unit_index")) is not int:
            raise _manual_required(ValueError("acoustic_embedding_unit_invalid"))
        if item["unit_index"] != expected_index:
            raise _manual_required(ValueError("acoustic_embedding_unit_index_invalid"))
        word_indexes = item.get("word_indexes")
        if (
            type(word_indexes) is not list
            or not word_indexes
            or any(type(value) is not int or value < 0 for value in word_indexes)
        ):
            raise _manual_required(ValueError("acoustic_embedding_words_invalid"))
        start_value = item.get("start")
        end_value = item.get("end")
        speech_value = item.get("original_speech_seconds")
        if (
            type(start_value) not in {int, float}
            or type(end_value) not in {int, float}
            or type(speech_value) not in {int, float}
        ):
            raise _manual_required(ValueError("acoustic_embedding_time_invalid"))
        start = float(start_value)
        end = float(end_value)
        speech_seconds = float(speech_value)
        if (
            not math.isfinite(start)
            or not math.isfinite(end)
            or not math.isfinite(speech_seconds)
            or start < 0.0
            or start >= end
            or start < previous_end
            or end > pcm_duration_seconds + 1e-6
            or speech_seconds <= 0.0
            or speech_seconds > end - start + 1e-6
        ):
            raise _manual_required(ValueError("acoustic_embedding_time_invalid"))
        validated.append(
            {
                "unit_index": expected_index,
                "word_indexes": list(word_indexes),
                "start": start,
                "end": end,
                "original_speech_seconds": speech_seconds,
            }
        )
        previous_end = end
    return validated


def extract_unit_embeddings(
    pcm_path: str,
    units: object,
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
    session_factory: Callable | None = None,
) -> np.ndarray:
    """Run bounded CPU-only inference over exact acoustic unit ranges."""

    acquired = _EMBEDDING_LOCK.acquire(blocking=False)
    if not acquired:
        raise _manual_required(RuntimeError("acoustic_embedding_busy"))
    try:
        _embedding_boundary_check(
            deadline_monotonic=deadline_monotonic,
            stop_requested=stop_requested,
        )
        path = Path(str(pcm_path or ""))
        if not path.is_file():
            raise ValueError("acoustic_pcm_missing")
        pcm_bytes = path.stat().st_size
        maximum_bytes = int(
            MAX_SOURCE_SECONDS * PCM_SAMPLE_RATE * PCM_BYTES_PER_SAMPLE
        )
        if (
            pcm_bytes <= 0
            or pcm_bytes % PCM_BYTES_PER_SAMPLE
            or pcm_bytes > maximum_bytes
        ):
            raise ValueError("acoustic_pcm_size_invalid")
        pcm_sample_count = pcm_bytes // PCM_BYTES_PER_SAMPLE
        pcm_duration_seconds = pcm_sample_count / float(PCM_SAMPLE_RATE)
        validated_units = _validated_embedding_units(
            units,
            pcm_duration_seconds=pcm_duration_seconds,
        )

        unit_samples: list[np.ndarray] = []
        with path.open("rb") as handle:
            for unit in validated_units:
                _embedding_boundary_check(
                    deadline_monotonic=deadline_monotonic,
                    stop_requested=stop_requested,
                )
                start_sample = int(round(float(unit["start"]) * PCM_SAMPLE_RATE))
                end_sample = int(round(float(unit["end"]) * PCM_SAMPLE_RATE))
                if (
                    start_sample < 0
                    or end_sample <= start_sample
                    or end_sample > pcm_sample_count
                ):
                    raise ValueError("acoustic_pcm_range_invalid")
                byte_count = (end_sample - start_sample) * PCM_BYTES_PER_SAMPLE
                handle.seek(start_sample * PCM_BYTES_PER_SAMPLE)
                raw = handle.read(byte_count)
                if len(raw) != byte_count:
                    raise ValueError("acoustic_pcm_range_short_read")
                samples = np.frombuffer(raw, dtype="<i2").astype(np.int16, copy=True)
                if samples.size != end_sample - start_sample or not np.any(samples):
                    raise ValueError("acoustic_pcm_energy_invalid")
                unit_samples.append(samples)

        _embedding_boundary_check(
            deadline_monotonic=deadline_monotonic,
            stop_requested=stop_requested,
        )
        session = _embedding_session(session_factory)
        embeddings: list[np.ndarray] = []
        for samples in unit_samples:
            _embedding_boundary_check(
                deadline_monotonic=deadline_monotonic,
                stop_requested=stop_requested,
            )
            features = compute_fbank(samples)
            _embedding_boundary_check(
                deadline_monotonic=deadline_monotonic,
                stop_requested=stop_requested,
            )
            output = session.run(
                [MODEL_OUTPUT_NAME],
                {MODEL_INPUT_NAME: features[None, :, :]},
            )
            if type(output) not in {list, tuple} or len(output) != 1:
                raise ValueError("acoustic_embedding_output_invalid")
            array = output[0]
            if (
                not isinstance(array, np.ndarray)
                or array.dtype != np.dtype(np.float32)
                or array.shape != (1, EMBEDDING_DIM)
                or not np.isfinite(array).all()
            ):
                raise ValueError("acoustic_embedding_output_invalid")
            row = array[0].astype(np.float32, copy=True)
            norm = float(np.linalg.norm(row.astype(np.float64)))
            if not math.isfinite(norm) or norm <= np.finfo(np.float32).eps:
                raise ValueError("acoustic_embedding_norm_invalid")
            embeddings.append(np.asarray(row / np.float32(norm), dtype=np.float32))
        result = np.stack(embeddings, axis=0).astype(np.float32, copy=False)
        if (
            result.shape != (len(validated_units), EMBEDDING_DIM)
            or not np.isfinite(result).all()
        ):
            raise ValueError("acoustic_embeddings_invalid")
        return result
    except speaker_cast.AutoCastManualRequired:
        raise
    except Exception as exc:
        raise _manual_required(exc)
    finally:
        _EMBEDDING_LOCK.release()
