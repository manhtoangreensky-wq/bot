"""Multi-speaker gender/register adapter over the proven exact-two ONNX engine."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Mapping
from pathlib import Path
import threading
from typing import Any

import numpy as np

from services import subdub_speaker_cast as speaker_cast
from services import subdub_two_speaker_gender_onnx as exact_gender


MIN_MULTI_SPEAKERS = 3
MAX_MULTI_SPEAKERS = speaker_cast.MAX_AUTO_SPEAKER_LABELS
MIN_CLASSIFIED_CUES_PER_SPEAKER = 2
MAX_CUES_PER_SPEAKER = exact_gender.MAX_CUES_PER_SPEAKER
MIN_VOTE_DOMINANCE = exact_gender.MIN_VOTE_DOMINANCE
MAX_JOB_EVIDENCE_SECONDS = exact_gender.MAX_JOB_EVIDENCE_SECONDS
CLASSIFIER_WALL_TIMEOUT_SECONDS = exact_gender.CLASSIFIER_WALL_TIMEOUT_SECONDS

ROOT = Path(__file__).resolve().parents[1]
MULTI_GENDER_MODEL_PATH = (
    ROOT / "assets" / "models" / "subdub_auto_multi" / "gender_classifier_200k.onnx"
)
MULTI_GENDER_LICENSE_PATH = (
    ROOT
    / "assets"
    / "models"
    / "subdub_auto_multi"
    / "GENDER_CLASSIFIER.MODEL.LICENSE.MIT"
)
MULTI_GENDER_NOTICE_PATH = (
    ROOT / "assets" / "models" / "subdub_auto_multi" / "THIRD_PARTY_NOTICES.md"
)
MULTI_GENDER_MODEL_SHA256 = (
    "e98f8bc6d7960a8a2169368fe4533636903e712790e96dbff81b679ede5de252"
)
MULTI_GENDER_MODEL_BYTES = 670_311
MULTI_GENDER_MODEL_INPUT = "mfcc"
MULTI_GENDER_MODEL_OUTPUT = "logits"
MULTI_GENDER_SAMPLE_RATE = 16_000
MULTI_GENDER_CLIP_SAMPLES = 48_000
MULTI_GENDER_MFCC_COUNT = 40
MULTI_GENDER_MEL_COUNT = 80
MULTI_GENDER_FFT_SIZE = 512
MULTI_GENDER_HOP_SAMPLES = 160
MULTI_GENDER_STRONG_CONFIDENCE = 0.90

_MULTI_GENDER_SESSION = None
_MULTI_GENDER_LOCK = threading.Lock()
_MULTI_GENDER_MEL_FILTER: np.ndarray | None = None
_MULTI_GENDER_DCT: np.ndarray | None = None


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


def _create_multi_gender_session():
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.inter_op_num_threads = 1
    options.intra_op_num_threads = 1
    return ort.InferenceSession(
        str(MULTI_GENDER_MODEL_PATH),
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )


def multi_gender_model_preflight(
    *,
    session_factory: Callable | None = None,
) -> dict[str, object]:
    """Validate the small hash-locked CPU ONNX register-routing model."""

    try:
        if (
            not MULTI_GENDER_MODEL_PATH.is_file()
            or MULTI_GENDER_MODEL_PATH.stat().st_size != MULTI_GENDER_MODEL_BYTES
            or _sha256(MULTI_GENDER_MODEL_PATH) != MULTI_GENDER_MODEL_SHA256
            or not MULTI_GENDER_LICENSE_PATH.is_file()
            or MULTI_GENDER_LICENSE_PATH.stat().st_size <= 0
            or not MULTI_GENDER_NOTICE_PATH.is_file()
            or MULTI_GENDER_NOTICE_PATH.stat().st_size <= 0
        ):
            raise ValueError("multi_gender_model_asset_invalid")
        session = (
            session_factory(
                str(MULTI_GENDER_MODEL_PATH),
                providers=["CPUExecutionProvider"],
            )
            if session_factory is not None
            else _create_multi_gender_session()
        )
        inputs = list(session.get_inputs())
        outputs = list(session.get_outputs())
        if (
            len(inputs) != 1
            or inputs[0].name != MULTI_GENDER_MODEL_INPUT
            or inputs[0].type != "tensor(float)"
            or len(list(inputs[0].shape)) != 3
            or inputs[0].shape[1] != MULTI_GENDER_MFCC_COUNT
            or len(outputs) != 1
            or outputs[0].name != MULTI_GENDER_MODEL_OUTPUT
            or outputs[0].type != "tensor(float)"
            or len(list(outputs[0].shape)) != 2
            or outputs[0].shape[1] != 1
            or list(session.get_providers()) != ["CPUExecutionProvider"]
        ):
            raise ValueError("multi_gender_model_schema_invalid")
        return {
            "ok": True,
            "model_sha256": MULTI_GENDER_MODEL_SHA256,
            "model_bytes": MULTI_GENDER_MODEL_BYTES,
            "providers": ["CPUExecutionProvider"],
        }
    except speaker_cast.AutoCastManualRequired:
        raise
    except Exception as exc:
        raise _manual_required(exc)


def _multi_gender_session(session_factory: Callable | None = None):
    global _MULTI_GENDER_SESSION
    if session_factory is not None:
        if not callable(session_factory):
            raise _manual_required(ValueError("multi_gender_session_invalid"))
        session = session_factory(
            str(MULTI_GENDER_MODEL_PATH),
            providers=["CPUExecutionProvider"],
        )
    else:
        if _MULTI_GENDER_SESSION is None:
            _MULTI_GENDER_SESSION = _create_multi_gender_session()
        session = _MULTI_GENDER_SESSION
    multi_gender_model_preflight(
        session_factory=lambda *_args, **_kwargs: session
    )
    return session


def _hz_to_slaney_mel(frequencies: np.ndarray) -> np.ndarray:
    values = np.asarray(frequencies, dtype=np.float64)
    result = values / (200.0 / 3.0)
    logarithmic = values >= 1000.0
    result[logarithmic] = 15.0 + np.log(values[logarithmic] / 1000.0) / (
        np.log(6.4) / 27.0
    )
    return result


def _slaney_mel_to_hz(mels: np.ndarray) -> np.ndarray:
    values = np.asarray(mels, dtype=np.float64)
    result = (200.0 / 3.0) * values
    logarithmic = values >= 15.0
    result[logarithmic] = 1000.0 * np.exp(
        (np.log(6.4) / 27.0) * (values[logarithmic] - 15.0)
    )
    return result


def _multi_gender_mel_filter() -> np.ndarray:
    global _MULTI_GENDER_MEL_FILTER
    if _MULTI_GENDER_MEL_FILTER is not None:
        return _MULTI_GENDER_MEL_FILTER
    fft_frequencies = np.linspace(
        0.0,
        MULTI_GENDER_SAMPLE_RATE / 2.0,
        MULTI_GENDER_FFT_SIZE // 2 + 1,
    )
    edge_mels = np.linspace(
        float(_hz_to_slaney_mel(np.asarray([0.0]))[0]),
        float(
            _hz_to_slaney_mel(
                np.asarray([MULTI_GENDER_SAMPLE_RATE / 2.0])
            )[0]
        ),
        MULTI_GENDER_MEL_COUNT + 2,
    )
    edge_hz = _slaney_mel_to_hz(edge_mels)
    ramps = edge_hz[:, None] - fft_frequencies[None, :]
    differences = np.diff(edge_hz)
    lower = -ramps[:-2] / differences[:-1, None]
    upper = ramps[2:] / differences[1:, None]
    weights = np.maximum(0.0, np.minimum(lower, upper))
    weights *= (
        2.0
        / (
            edge_hz[2 : MULTI_GENDER_MEL_COUNT + 2]
            - edge_hz[:MULTI_GENDER_MEL_COUNT]
        )
    )[:, None]
    if (
        weights.shape
        != (MULTI_GENDER_MEL_COUNT, MULTI_GENDER_FFT_SIZE // 2 + 1)
        or not np.isfinite(weights).all()
        or np.any(np.sum(weights, axis=1) <= 0.0)
    ):
        raise _manual_required(ValueError("multi_gender_mel_filter_invalid"))
    _MULTI_GENDER_MEL_FILTER = np.asarray(weights, dtype=np.float64)
    _MULTI_GENDER_MEL_FILTER.setflags(write=False)
    return _MULTI_GENDER_MEL_FILTER


def _multi_gender_dct() -> np.ndarray:
    global _MULTI_GENDER_DCT
    if _MULTI_GENDER_DCT is not None:
        return _MULTI_GENDER_DCT
    mel_indexes = np.arange(MULTI_GENDER_MEL_COUNT, dtype=np.float64)
    coefficient_indexes = np.arange(
        MULTI_GENDER_MFCC_COUNT,
        dtype=np.float64,
    )[:, None]
    basis = np.cos(
        np.pi
        / MULTI_GENDER_MEL_COUNT
        * (mel_indexes + 0.5)
        * coefficient_indexes
    )
    basis[0] *= math.sqrt(1.0 / MULTI_GENDER_MEL_COUNT)
    basis[1:] *= math.sqrt(2.0 / MULTI_GENDER_MEL_COUNT)
    _MULTI_GENDER_DCT = np.asarray(basis, dtype=np.float64)
    _MULTI_GENDER_DCT.setflags(write=False)
    return _MULTI_GENDER_DCT


def multi_gender_mfcc(samples: object) -> np.ndarray:
    """NumPy-only librosa-compatible 40-MFCC frontend for one 3s clip."""

    try:
        values = np.asarray(samples, dtype=np.float32)
        if (
            values.shape != (MULTI_GENDER_CLIP_SAMPLES,)
            or not np.isfinite(values).all()
        ):
            raise ValueError("multi_gender_clip_invalid")
        padded = np.pad(
            values.astype(np.float64),
            MULTI_GENDER_FFT_SIZE // 2,
            mode="constant",
        )
        frames = np.lib.stride_tricks.sliding_window_view(
            padded,
            MULTI_GENDER_FFT_SIZE,
        )[::MULTI_GENDER_HOP_SAMPLES]
        window = np.hanning(MULTI_GENDER_FFT_SIZE + 1)[:-1]
        spectrum = np.abs(
            np.fft.rfft(
                frames * window,
                n=MULTI_GENDER_FFT_SIZE,
                axis=1,
            )
        ) ** 2
        mel_power = np.maximum(
            spectrum @ _multi_gender_mel_filter().T,
            1e-10,
        )
        decibels = 10.0 * np.log10(mel_power)
        decibels = np.maximum(decibels, float(np.max(decibels)) - 80.0)
        mfcc = _multi_gender_dct() @ decibels.T
        mfcc = (mfcc - np.mean(mfcc, axis=1, keepdims=True)) / (
            np.std(mfcc, axis=1, keepdims=True) + 1e-8
        )
        if (
            mfcc.shape
            != (
                MULTI_GENDER_MFCC_COUNT,
                MULTI_GENDER_CLIP_SAMPLES // MULTI_GENDER_HOP_SAMPLES + 1,
            )
            or not np.isfinite(mfcc).all()
        ):
            raise ValueError("multi_gender_mfcc_invalid")
        return mfcc[np.newaxis].astype(np.float32)
    except speaker_cast.AutoCastManualRequired:
        raise
    except Exception as exc:
        raise _manual_required(exc)


def classify_vocal_window_gender_probabilities(
    windows: object,
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
    session_factory: Callable | None = None,
) -> list[float]:
    """Classify bounded 16k vocal windows, repeating only their own samples."""

    if (
        type(windows) is not list
        or not windows
        or len(windows) > speaker_cast.MAX_SIDECAR_CUES
        or not _MULTI_GENDER_LOCK.acquire(blocking=False)
    ):
        raise _manual_required(ValueError("multi_gender_windows_invalid"))
    try:
        session = _multi_gender_session(session_factory)
        results: list[float] = []
        for raw_window in windows:
            exact_gender._ensure_active(deadline_monotonic, stop_requested)
            samples = np.asarray(raw_window)
            if (
                samples.dtype != np.dtype(np.int16)
                or samples.ndim != 1
                or not MULTI_GENDER_SAMPLE_RATE // 2
                <= len(samples)
                <= MULTI_GENDER_CLIP_SAMPLES
                or not np.any(samples)
            ):
                raise ValueError("multi_gender_window_invalid")
            repeated = np.resize(
                samples.astype(np.float32) / np.float32(32768.0),
                MULTI_GENDER_CLIP_SAMPLES,
            )
            output = session.run(
                [MULTI_GENDER_MODEL_OUTPUT],
                {MULTI_GENDER_MODEL_INPUT: multi_gender_mfcc(repeated)},
            )
            if (
                type(output) not in {list, tuple}
                or len(output) != 1
                or not isinstance(output[0], np.ndarray)
                or output[0].shape != (1, 1)
                or not np.isfinite(output[0]).all()
            ):
                raise ValueError("multi_gender_output_invalid")
            logit = float(output[0][0, 0])
            probability = (
                1.0 / (1.0 + math.exp(-logit))
                if logit >= 0.0
                else math.exp(logit) / (1.0 + math.exp(logit))
            )
            results.append(round(float(probability), 6))
        return results
    except speaker_cast.AutoCastManualRequired:
        raise
    except Exception as exc:
        raise _manual_required(exc)
    finally:
        _MULTI_GENDER_LOCK.release()


def _validated_ranges(
    ranges_by_speaker: Mapping[str, object],
) -> dict[str, list[dict[str, float]]]:
    if not isinstance(ranges_by_speaker, Mapping) or not (
        MIN_MULTI_SPEAKERS <= len(ranges_by_speaker) <= MAX_MULTI_SPEAKERS
    ):
        raise _manual_required()
    validated: dict[str, list[dict[str, float]]] = {}
    total_cues = 0
    for speaker_id, raw_ranges in ranges_by_speaker.items():
        if type(speaker_id) is not str or not speaker_id.strip():
            raise _manual_required()
        if not isinstance(raw_ranges, (list, tuple)) or not (
            MIN_CLASSIFIED_CUES_PER_SPEAKER
            <= len(raw_ranges)
            <= speaker_cast.MAX_SIDECAR_CUES
        ):
            raise _manual_required()
        total_cues += len(raw_ranges)
        if total_cues > speaker_cast.MAX_SIDECAR_CUES:
            raise _manual_required()
        rows: list[dict[str, float]] = []
        for raw_range in raw_ranges:
            if not isinstance(raw_range, (list, tuple)) or len(raw_range) != 2:
                raise _manual_required()
            try:
                start = float(raw_range[0])
                end = float(raw_range[1])
            except (TypeError, ValueError, OverflowError) as exc:
                raise _manual_required(exc)
            if (
                not math.isfinite(start)
                or not math.isfinite(end)
                or start < 0.0
                or end <= start
            ):
                raise _manual_required()
            rows.append({"start": start, "end": end})
        rows.sort(key=lambda item: (item["start"], item["end"]))
        validated[speaker_id] = rows
    return validated


def _select_bounded_cues(
    ranges_by_speaker: Mapping[str, object],
) -> dict[str, list[dict[str, float]]]:
    validated = _validated_ranges(ranges_by_speaker)
    selected: dict[str, list[dict[str, float]]] = {
        speaker_id: [] for speaker_id in validated
    }
    candidates: list[tuple[float, float, float, str, int, dict[str, float]]] = []
    for speaker_id, rows in validated.items():
        for index, item in enumerate(rows):
            candidates.append(
                (
                    item["end"] - item["start"],
                    item["end"],
                    item["start"],
                    speaker_id,
                    index,
                    item,
                )
            )
    candidates.sort(key=lambda item: item[:5])
    selected_ids: set[tuple[str, int]] = set()

    def add(speaker_id: str, index: int, item: dict[str, float]) -> bool:
        flattened = [row for values in selected.values() for row in values]
        proposed = flattened + [item]
        if exact_gender._has_overlap(proposed):
            return False
        if exact_gender._union_seconds(proposed) > MAX_JOB_EVIDENCE_SECONDS + 1e-9:
            return False
        selected[speaker_id].append(dict(item))
        selected_ids.add((speaker_id, index))
        return True

    for _duration, _end, _start, speaker_id, index, item in candidates:
        if len(selected[speaker_id]) < MIN_CLASSIFIED_CUES_PER_SPEAKER:
            add(speaker_id, index, item)
    if any(
        len(rows) < MIN_CLASSIFIED_CUES_PER_SPEAKER
        for rows in selected.values()
    ):
        raise _manual_required()
    for _duration, _end, _start, speaker_id, index, item in candidates:
        if (
            (speaker_id, index) in selected_ids
            or len(selected[speaker_id]) >= MAX_CUES_PER_SPEAKER
        ):
            continue
        add(speaker_id, index, item)
    for rows in selected.values():
        rows.sort(key=lambda item: (item["start"], item["end"]))
    return selected


def _aggregate_one_gender_result(
    speaker_id: object,
    raw_rows: object,
) -> tuple[dict[str, Any], list[dict[str, float]]]:
    if type(speaker_id) is not str or not speaker_id.strip():
        raise _manual_required()
    if not isinstance(raw_rows, (list, tuple)) or not (
        MIN_CLASSIFIED_CUES_PER_SPEAKER
        <= len(raw_rows)
        <= MAX_CUES_PER_SPEAKER
    ):
        raise _manual_required()
    male_votes = 0
    female_votes = 0
    score_margins: list[float] = []
    rows: list[dict[str, float]] = []
    for raw_row in raw_rows:
        if not isinstance(raw_row, Mapping):
            raise _manual_required()
        try:
            start = float(raw_row.get("start"))
            end = float(raw_row.get("end"))
            male_score = float(raw_row.get("male_score"))
            female_score = float(raw_row.get("female_score"))
        except (TypeError, ValueError, OverflowError) as exc:
            raise _manual_required(exc)
        if (
            not all(
                math.isfinite(value)
                for value in (start, end, male_score, female_score)
            )
            or start < 0.0
            or end <= start
            or male_score < 0.0
            or female_score < 0.0
            or male_score == female_score
        ):
            raise _manual_required()
        male_votes += int(male_score > female_score)
        female_votes += int(female_score > male_score)
        score_total = male_score + female_score
        score_margins.append(
            abs(male_score - female_score) / score_total
            if score_total > 0.0
            else 0.0
        )
        rows.append({"start": start, "end": end})
    winner_votes = max(male_votes, female_votes)
    dominance = winner_votes / len(rows)
    if dominance < MIN_VOTE_DOMINANCE:
        raise _manual_required()
    gender = "male" if male_votes > female_votes else "female"
    voiced_seconds = exact_gender._union_seconds(rows)
    if voiced_seconds <= 0.0:
        raise _manual_required()
    return (
        {
            "speaker_id": speaker_id,
            "voice_gender": gender,
            "voice_register": "low" if gender == "male" else "high",
            "confidence": round(float(dominance), 6),
            "voiced_seconds": round(float(voiced_seconds), 6),
            "sample_count": int(
                round(voiced_seconds * exact_gender.PCM_SAMPLE_RATE)
            ),
            "cue_count": len(rows),
            "male_votes": male_votes,
            "female_votes": female_votes,
            "pann_score_margin": round(
                float(sorted(score_margins)[len(score_margins) // 2]),
                6,
            ),
            "reason": "classified_panns_multi_after_uvr",
        },
        rows,
    )


def _aggregate_gender_results(
    scores_by_speaker: Mapping[str, object],
) -> dict[str, dict[str, Any]]:
    if not isinstance(scores_by_speaker, Mapping) or not (
        MIN_MULTI_SPEAKERS <= len(scores_by_speaker) <= MAX_MULTI_SPEAKERS
    ):
        raise _manual_required()
    results: dict[str, dict[str, Any]] = {}
    all_rows: list[dict[str, float]] = []
    for speaker_id, raw_rows in scores_by_speaker.items():
        result, rows = _aggregate_one_gender_result(speaker_id, raw_rows)
        results[str(speaker_id)] = result
        all_rows.extend(rows)
    if exact_gender._union_seconds(all_rows) > MAX_JOB_EVIDENCE_SECONDS + 1e-9:
        raise _manual_required()
    return results


def classify_multi_speaker_genders(
    stereo_pcm_path: str,
    ranges_by_speaker: Mapping[str, object],
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
) -> dict[str, dict[str, Any]]:
    """Classify every provider speaker independently; same-gender sets are valid."""

    if not exact_gender._CLASSIFIER_LOCK.acquire(blocking=False):
        raise _manual_required()
    try:
        try:
            exact_gender._ensure_active(deadline_monotonic, stop_requested)
            selected = _select_bounded_cues(ranges_by_speaker)
            path = Path(str(stereo_pcm_path or ""))
            if not path.is_file() or path.stat().st_size <= 0:
                raise ValueError("stereo_pcm_missing")
            if path.stat().st_size % exact_gender.PCM_FRAME_BYTES:
                raise ValueError("stereo_pcm_shape_invalid")
            model_paths = exact_gender._validated_model_paths()
            scores = exact_gender._infer_selected_cues(
                path,
                selected,
                model_paths,
                deadline_monotonic=deadline_monotonic,
                stop_requested=stop_requested,
            )
            exact_gender._ensure_active(deadline_monotonic, stop_requested)
            return _aggregate_gender_results(scores)
        except speaker_cast.AutoCastManualRequired:
            raise
        except (
            ImportError,
            IndexError,
            MemoryError,
            OSError,
            OverflowError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            raise _manual_required(exc)
    finally:
        exact_gender._CLASSIFIER_LOCK.release()
