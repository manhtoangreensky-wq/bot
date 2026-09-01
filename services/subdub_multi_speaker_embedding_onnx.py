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
MIN_CLUSTER_UNPADDED_SECONDS = 0.8
MIN_CLUSTER_UNITS = 2
MAX_CLUSTER_UNITS = 1_000
KMEANS_MAX_ITERATIONS = 30
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
    _feature_shift_samples: int = 0,
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
        if (
            type(_feature_shift_samples) is not int
            or _feature_shift_samples < 0
            or _feature_shift_samples >= FBANK_FRAME_SHIFT
        ):
            raise ValueError("acoustic_feature_shift_invalid")

        unit_samples: list[np.ndarray] = []
        with path.open("rb") as handle:
            for unit in validated_units:
                _embedding_boundary_check(
                    deadline_monotonic=deadline_monotonic,
                    stop_requested=stop_requested,
                )
                start_sample = int(round(float(unit["start"]) * PCM_SAMPLE_RATE))
                end_sample = int(round(float(unit["end"]) * PCM_SAMPLE_RATE))
                if _feature_shift_samples:
                    available_shift = max(0, end_sample - start_sample - 1)
                    start_sample += min(_feature_shift_samples, available_shift)
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


def _cluster_payload(value: object) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if type(value) is dict:
        raw_embeddings = value.get("embeddings")
        raw_positions = value.get("source_positions")
        raw_speech = value.get("speech_seconds")
    else:
        raw_embeddings = value
        raw_positions = None
        raw_speech = None
    if not isinstance(raw_embeddings, np.ndarray):
        raise _manual_required(ValueError("acoustic_cluster_embeddings_invalid"))
    embeddings = np.asarray(raw_embeddings)
    if (
        embeddings.ndim != 2
        or embeddings.dtype.kind not in {"f", "i", "u"}
        or not MIN_UNITS <= embeddings.shape[0] <= MAX_CLUSTER_UNITS
        or embeddings.shape[1] <= 0
        or not np.isfinite(embeddings).all()
    ):
        raise _manual_required(ValueError("acoustic_cluster_embeddings_invalid"))
    matrix = embeddings.astype(np.float64, copy=True)
    norms = np.linalg.norm(matrix, axis=1)
    if not np.isfinite(norms).all() or np.any(norms <= np.finfo(np.float32).eps):
        raise _manual_required(ValueError("acoustic_cluster_embedding_norm_invalid"))
    matrix /= norms[:, None]

    count = matrix.shape[0]
    if raw_positions is None:
        positions = np.arange(count, dtype=np.float64)
    else:
        if type(raw_positions) not in {list, tuple} or len(raw_positions) != count:
            raise _manual_required(ValueError("acoustic_cluster_positions_invalid"))
        if any(type(value) not in {int, float} for value in raw_positions):
            raise _manual_required(ValueError("acoustic_cluster_positions_invalid"))
        positions = np.asarray(raw_positions, dtype=np.float64)
    if (
        not np.isfinite(positions).all()
        or np.any(positions < 0.0)
        or len(np.unique(positions)) != count
    ):
        raise _manual_required(ValueError("acoustic_cluster_positions_invalid"))

    if raw_speech is None:
        speech_seconds = np.full(count, UNIT_MIN_FEATURE_SECONDS, dtype=np.float64)
    else:
        if type(raw_speech) not in {list, tuple} or len(raw_speech) != count:
            raise _manual_required(ValueError("acoustic_cluster_speech_invalid"))
        if any(type(value) not in {int, float} for value in raw_speech):
            raise _manual_required(ValueError("acoustic_cluster_speech_invalid"))
        speech_seconds = np.asarray(raw_speech, dtype=np.float64)
    if not np.isfinite(speech_seconds).all() or np.any(speech_seconds <= 0.0):
        raise _manual_required(ValueError("acoustic_cluster_speech_invalid"))
    return matrix, positions, speech_seconds


def _pruned_similarity(embeddings: np.ndarray) -> np.ndarray:
    similarity = 0.5 * (1.0 + embeddings @ embeddings.T)
    if not np.isfinite(similarity).all():
        raise _manual_required(ValueError("acoustic_similarity_invalid"))
    count = similarity.shape[0]
    low_count = max(2, count - 10) if count < 1_000 else int(count * 0.99)
    if not 0 < low_count < count:
        raise _manual_required(ValueError("acoustic_pruning_invalid"))
    pruned = np.empty_like(similarity)
    for row_index in range(count):
        indexes = np.argsort(similarity[row_index], kind="stable")
        pruned[row_index] = 1.0
        pruned[row_index, indexes[:low_count]] = 0.0
    pruned = 0.5 * (pruned + pruned.T)
    np.fill_diagonal(pruned, 0.0)
    if not np.isfinite(pruned).all():
        raise _manual_required(ValueError("acoustic_pruning_invalid"))
    return pruned


def _canonical_cluster_labels(
    labels: np.ndarray,
    source_positions: np.ndarray,
) -> np.ndarray:
    raw_labels = sorted(set(int(value) for value in labels.tolist()))
    ordered = sorted(
        raw_labels,
        key=lambda label: (
            float(np.min(source_positions[labels == label])),
            label,
        ),
    )
    mapping = {label: canonical for canonical, label in enumerate(ordered)}
    return np.asarray([mapping[int(label)] for label in labels], dtype=np.int64)


def _deterministic_kmeans(
    data: np.ndarray,
    speaker_count: int,
    source_positions: np.ndarray,
) -> np.ndarray:
    if KMEANS_MAX_ITERATIONS <= 0:
        raise _manual_required(ValueError("acoustic_cluster_nonconvergent"))
    count = data.shape[0]
    source_order = np.lexsort((np.arange(count), source_positions))
    seed_indexes = [int(source_order[0])]
    while len(seed_indexes) < speaker_count:
        distances = np.stack(
            [
                np.sum((data - data[index]) ** 2, axis=1)
                for index in seed_indexes
            ],
            axis=1,
        )
        minimum = np.min(distances, axis=1)
        minimum[np.asarray(seed_indexes, dtype=np.int64)] = -1.0
        maximum = float(np.max(minimum))
        if not math.isfinite(maximum) or maximum <= np.finfo(np.float64).eps:
            raise _manual_required(ValueError("acoustic_cluster_seed_invalid"))
        candidates = np.flatnonzero(np.isclose(minimum, maximum, rtol=0.0, atol=1e-12))
        next_index = min(
            candidates.tolist(),
            key=lambda index: (float(source_positions[index]), int(index)),
        )
        seed_indexes.append(int(next_index))
    centroids = data[np.asarray(seed_indexes, dtype=np.int64)].copy()
    previous_labels: np.ndarray | None = None
    for _iteration in range(KMEANS_MAX_ITERATIONS):
        distances = np.sum(
            (data[:, None, :] - centroids[None, :, :]) ** 2,
            axis=2,
        )
        if not np.isfinite(distances).all():
            raise _manual_required(ValueError("acoustic_cluster_distance_invalid"))
        labels = np.argmin(distances, axis=1).astype(np.int64)
        if len(set(labels.tolist())) != speaker_count:
            raise _manual_required(ValueError("acoustic_cluster_empty"))
        updated = np.stack(
            [np.mean(data[labels == label], axis=0) for label in range(speaker_count)],
            axis=0,
        )
        if not np.isfinite(updated).all():
            raise _manual_required(ValueError("acoustic_cluster_centroid_invalid"))
        if previous_labels is not None and np.array_equal(labels, previous_labels):
            return _canonical_cluster_labels(labels, source_positions)
        previous_labels = labels
        centroids = updated
    raise _manual_required(ValueError("acoustic_cluster_nonconvergent"))


def _stable_cluster_view(
    embeddings: np.ndarray,
    source_positions: np.ndarray,
) -> tuple[int, np.ndarray, np.ndarray]:
    pruned = _pruned_similarity(embeddings)
    laplacian = np.diag(np.sum(np.abs(pruned), axis=1)) - pruned
    eigenvalues, eigenvectors = np.linalg.eigh(laplacian)
    if (
        not np.isfinite(eigenvalues).all()
        or not np.isfinite(eigenvectors).all()
        or eigenvalues.shape[0] != embeddings.shape[0]
    ):
        raise _manual_required(ValueError("acoustic_eigendecomposition_invalid"))
    search_count = min(eigenvalues.shape[0], MAX_SPEAKERS + 2)
    differences = np.diff(eigenvalues[:search_count])
    if differences.size == 0 or not np.isfinite(differences).all():
        raise _manual_required(ValueError("acoustic_eigengap_invalid"))
    speaker_count = int(np.argmax(differences)) + 1
    if not MIN_SPEAKERS <= speaker_count <= MAX_SPEAKERS:
        raise _manual_required(ValueError("acoustic_cluster_count_out_of_range"))
    spectral = eigenvectors[:, :speaker_count]
    labels = _deterministic_kmeans(spectral, speaker_count, source_positions)
    return speaker_count, labels, eigenvalues


def _validate_cluster_support(
    labels: np.ndarray,
    speech_seconds: np.ndarray,
    speaker_count: int,
) -> list[int]:
    cluster_sizes: list[int] = []
    for label in range(speaker_count):
        membership = labels == label
        unit_count = int(np.count_nonzero(membership))
        speech_total = float(np.sum(speech_seconds[membership]))
        if (
            unit_count < MIN_CLUSTER_UNITS
            or not math.isfinite(speech_total)
            or speech_total < MIN_CLUSTER_UNPADDED_SECONDS
        ):
            raise _manual_required(ValueError("acoustic_cluster_unsupported"))
        cluster_sizes.append(unit_count)
    return cluster_sizes


def _cluster_unit_confidences(
    embeddings: np.ndarray,
    labels: np.ndarray,
    speaker_count: int,
) -> list[float]:
    centroids = np.stack(
        [np.mean(embeddings[labels == label], axis=0) for label in range(speaker_count)],
        axis=0,
    )
    centroid_norms = np.linalg.norm(centroids, axis=1)
    if not np.isfinite(centroid_norms).all() or np.any(
        centroid_norms <= np.finfo(np.float64).eps
    ):
        raise _manual_required(ValueError("acoustic_cluster_centroid_invalid"))
    centroids /= centroid_norms[:, None]
    similarities = embeddings @ centroids.T
    if not np.isfinite(similarities).all():
        raise _manual_required(ValueError("acoustic_cluster_confidence_invalid"))
    confidences: list[float] = []
    for index, label in enumerate(labels.tolist()):
        assigned = float(similarities[index, int(label)])
        competitors = np.delete(similarities[index], int(label))
        strongest_competitor = float(np.max(competitors)) if competitors.size else -1.0
        margin = max(0.0, min(2.0, assigned - strongest_competitor))
        confidences.append(round(max(0.0, min(1.0, margin / 2.0)), 6))
    return confidences


def spectral_cluster_embeddings(
    base_embeddings: object,
    shifted_embeddings: object,
) -> dict[str, object]:
    """Select and validate one stable deterministic 3-8 speaker partition."""

    base, positions, speech_seconds = _cluster_payload(base_embeddings)
    shifted, shifted_positions, shifted_speech = _cluster_payload(shifted_embeddings)
    if (
        base.shape != shifted.shape
        or not np.array_equal(positions, shifted_positions)
        or not np.array_equal(speech_seconds, shifted_speech)
    ):
        raise _manual_required(ValueError("acoustic_cluster_view_mismatch"))
    base_count, base_labels, eigenvalues = _stable_cluster_view(base, positions)
    shifted_count, shifted_labels, _shifted_eigenvalues = _stable_cluster_view(
        shifted,
        positions,
    )
    if base_count != shifted_count or not np.array_equal(base_labels, shifted_labels):
        raise _manual_required(ValueError("acoustic_cluster_unstable"))
    cluster_sizes = _validate_cluster_support(
        base_labels,
        speech_seconds,
        base_count,
    )
    unit_confidences = _cluster_unit_confidences(
        base,
        base_labels,
        base_count,
    )
    return {
        "ok": True,
        "status": "PASS",
        "speaker_count": base_count,
        "labels": [int(value) for value in base_labels.tolist()],
        "cluster_sizes": cluster_sizes,
        "unit_confidences": unit_confidences,
        "eigenvalues": [
            round(float(value), 8)
            for value in eigenvalues[: min(len(eigenvalues), MAX_SPEAKERS + 2)]
        ],
        "stability_pass": True,
        "algorithm_version": ALGORITHM_VERSION,
    }


def build_clustered_segments(
    words: object,
    units: object,
    cluster_result: object,
) -> list[dict]:
    """Assign every strict word once and group adjacent acoustic labels."""

    if type(words) is not list or not words:
        raise _manual_required(ValueError("acoustic_segment_words_invalid"))
    maximum_end = max(
        float(item.get("end") or 0.0) if type(item) is dict else 0.0
        for item in words
    )
    validated_words = validate_word_timeline(
        words,
        duration_seconds=max(maximum_end, np.finfo(np.float32).eps),
    )
    if type(units) is not list or not units:
        raise _manual_required(ValueError("acoustic_segment_units_invalid"))
    validated_units = _validated_embedding_units(
        units,
        pcm_duration_seconds=max(maximum_end, np.finfo(np.float32).eps),
    )
    if type(cluster_result) is not dict:
        raise _manual_required(ValueError("acoustic_segment_clusters_invalid"))
    labels = cluster_result.get("labels")
    confidences = cluster_result.get("unit_confidences")
    if (
        type(labels) is not list
        or type(confidences) is not list
        or len(labels) != len(validated_units)
        or len(confidences) != len(validated_units)
        or any(type(label) is not int or not 0 <= label < MAX_SPEAKERS for label in labels)
        or any(
            type(value) not in {int, float}
            or not math.isfinite(float(value))
            or not 0.0 <= float(value) <= 1.0
            for value in confidences
        )
    ):
        raise _manual_required(ValueError("acoustic_segment_clusters_invalid"))

    word_assignments: list[tuple[int, float] | None] = [None] * len(validated_words)
    for unit_index, unit in enumerate(validated_units):
        for word_index in unit["word_indexes"]:
            if (
                word_index >= len(word_assignments)
                or word_assignments[word_index] is not None
            ):
                raise _manual_required(ValueError("acoustic_segment_coverage_invalid"))
            word_assignments[word_index] = (
                int(labels[unit_index]),
                float(confidences[unit_index]),
            )
    if any(item is None for item in word_assignments):
        raise _manual_required(ValueError("acoustic_segment_coverage_invalid"))

    grouped: list[dict] = []
    current_words: list[dict] = []
    current_label = -1
    current_confidences: list[float] = []

    def flush_current() -> None:
        nonlocal current_words, current_label, current_confidences
        if not current_words:
            return
        word_identity = ",".join(str(item["index"]) for item in current_words)
        start = float(current_words[0]["start"])
        end = float(current_words[-1]["end"])
        cue_digest = hashlib.sha256(
            f"{word_identity}|{start:.6f}|{end:.6f}".encode("ascii")
        ).hexdigest()[:12]
        try:
            speaker_id = speaker_cast.normalized_speaker_key(0, current_label)
        except Exception as exc:
            raise _manual_required(exc)
        grouped.append(
            {
                "cue_id": f"cue-{len(grouped) + 1:04d}-{cue_digest}",
                "index": len(grouped) + 1,
                "start": start,
                "end": end,
                "text": " ".join(str(item["word"]) for item in current_words),
                "speaker": current_label,
                "speaker_id": speaker_id,
                "speaker_confidence": round(min(current_confidences), 6),
                "chunk_index": 0,
            }
        )
        current_words = []
        current_label = -1
        current_confidences = []

    for word, assignment in zip(validated_words, word_assignments):
        if assignment is None:
            raise _manual_required(ValueError("acoustic_segment_coverage_invalid"))
        label, confidence = assignment
        if current_words and label != current_label:
            flush_current()
        if not current_words:
            current_label = label
        current_words.append(word)
        current_confidences.append(confidence)
    flush_current()
    if (
        not grouped
        or sum(len(item["text"].split()) for item in grouped)
        != sum(len(item["word"].split()) for item in validated_words)
    ):
        raise _manual_required(ValueError("acoustic_segment_coverage_invalid"))
    return grouped


def diarize_word_timeline(
    pcm_path: str,
    words: object,
    *,
    duration_seconds: float,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
    session_factory: Callable | None = None,
) -> dict[str, object]:
    """Compose strict words, two embedding views, clustering and source cues."""

    validated_words = validate_word_timeline(
        words,
        duration_seconds=duration_seconds,
    )
    units = build_acoustic_units(
        validated_words,
        duration_seconds=duration_seconds,
    )
    base = extract_unit_embeddings(
        pcm_path,
        units,
        deadline_monotonic=deadline_monotonic,
        stop_requested=stop_requested,
        session_factory=session_factory,
        _feature_shift_samples=0,
    )
    shifted = extract_unit_embeddings(
        pcm_path,
        units,
        deadline_monotonic=deadline_monotonic,
        stop_requested=stop_requested,
        session_factory=session_factory,
        _feature_shift_samples=FBANK_FRAME_SHIFT // 2,
    )
    positions = [float(unit["start"]) for unit in units]
    speech_seconds = [float(unit["original_speech_seconds"]) for unit in units]
    cluster_result = spectral_cluster_embeddings(
        {
            "embeddings": base,
            "source_positions": positions,
            "speech_seconds": speech_seconds,
        },
        {
            "embeddings": shifted,
            "source_positions": positions,
            "speech_seconds": speech_seconds,
        },
    )
    segments = build_clustered_segments(
        validated_words,
        units,
        cluster_result,
    )
    speaker_count = int(cluster_result["speaker_count"])
    if len({item["speaker_id"] for item in segments}) != speaker_count:
        raise _manual_required(ValueError("acoustic_segment_speaker_coverage_invalid"))
    return {
        "ok": True,
        "status": "PASS",
        "provider": "local_wespeaker_resnet34_spectral",
        "segments": segments,
        "detected_speaker_count": speaker_count,
        "model_sha256": MODEL_SHA256,
        "algorithm_version": ALGORITHM_VERSION,
        "word_count": len(validated_words),
        "unit_count": len(units),
        "embedding_window_count": len(units) * 2,
        "cluster_sizes": sorted(int(value) for value in cluster_result["cluster_sizes"]),
        "stability_pass": bool(cluster_result["stability_pass"]),
        "word_coverage_count": len(validated_words),
    }
