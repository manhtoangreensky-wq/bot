"""Deterministic local gender authority for the exact-two SubDub lane."""

from __future__ import annotations

import hashlib
import math
import os
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from services import subdub_speaker_cast as speaker_cast


ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "assets" / "models" / "subdub_auto_gender"
UVR_MODEL_PATH = MODEL_DIR / "UVR_MDXNET_3_9662.onnx"
PANN_MODEL_PATH = MODEL_DIR / "panns_mobilenetv1_audioset.onnx"
UVR_LICENSE_PATH = MODEL_DIR / "UVR_MDXNET_3_9662.LICENSE"
PANN_LICENSE_PATH = MODEL_DIR / "PANNs.LICENSE.MIT"
PANN_MODEL_LICENSE_PATH = MODEL_DIR / "PANNs.MODEL.LICENSE.CC-BY-4.0"
THIRD_PARTY_NOTICES_PATH = MODEL_DIR / "THIRD_PARTY_NOTICES.md"

UVR_MODEL_SHA256 = "e02220e80d8253f4c2209f8924298b2b686bbdf2868b788ff5500fb9bd94aadc"
PANN_MODEL_SHA256 = "0da2c433751fd5aac39593476e9a4b7a92b41d8492eb8ddb28d7eae8d7bd7bcd"

PCM_SAMPLE_RATE = 44_100
PCM_CHANNELS = 2
PCM_BYTES_PER_SAMPLE = 2
PCM_FRAME_BYTES = PCM_CHANNELS * PCM_BYTES_PER_SAMPLE
PANN_SAMPLE_RATE = 32_000
MAX_JOB_EVIDENCE_SECONDS = 48.0
MAX_CUES_PER_SPEAKER = 12
MIN_CLASSIFIED_CUES_PER_SPEAKER = 4
MIN_VOTE_DOMINANCE = 0.75
CLASSIFIER_WALL_TIMEOUT_SECONDS = 300.0

_N_FFT = 6_144
_HOP = 1_024
_DIM_F = 2_048
_SEGMENT_SIZE = 256
_TRIM = _N_FFT // 2
_CHUNK_SIZE = _HOP * (_SEGMENT_SIZE - 1)
_GEN_SIZE = _CHUNK_SIZE - 2 * _TRIM
_OVERLAP = 0.25

_MALE_SPEECH_INDEX = 1
_FEMALE_SPEECH_INDEX = 2
_MALE_SINGING_INDEX = 32
_FEMALE_SINGING_INDEX = 33
_CLASSIFIER_LOCK = threading.Lock()


def _manual_required(error: Exception | None = None) -> speaker_cast.AutoCastManualRequired:
    result = speaker_cast.AutoCastManualRequired()
    if error is not None:
        result.__cause__ = error
    return result


def _ensure_active(
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
) -> None:
    try:
        deadline = float(deadline_monotonic)
        stopped = bool(stop_requested())
    except Exception as exc:
        raise _manual_required(exc)
    if not math.isfinite(deadline) or stopped or time.monotonic() >= deadline:
        raise _manual_required()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _validated_model_paths() -> tuple[Path, Path]:
    try:
        required_notices = (
            UVR_LICENSE_PATH,
            PANN_LICENSE_PATH,
            PANN_MODEL_LICENSE_PATH,
            THIRD_PARTY_NOTICES_PATH,
        )
        if any(not path.is_file() or path.stat().st_size <= 0 for path in required_notices):
            raise ValueError("model_notice_missing")
        if not UVR_MODEL_PATH.is_file() or _sha256(UVR_MODEL_PATH) != UVR_MODEL_SHA256:
            raise ValueError("uvr_model_hash_mismatch")
        if not PANN_MODEL_PATH.is_file() or _sha256(PANN_MODEL_PATH) != PANN_MODEL_SHA256:
            raise ValueError("panns_model_hash_mismatch")
    except (OSError, ValueError, TypeError) as exc:
        raise _manual_required(exc)
    return UVR_MODEL_PATH, PANN_MODEL_PATH


def _validated_ranges(
    ranges_by_speaker: Mapping[str, object],
) -> dict[str, list[dict[str, float]]]:
    if not isinstance(ranges_by_speaker, Mapping) or len(ranges_by_speaker) != 2:
        raise _manual_required()
    validated: dict[str, list[dict[str, float]]] = {}
    total_input_cues = 0
    for speaker_id, raw_ranges in ranges_by_speaker.items():
        if type(speaker_id) is not str or not speaker_id.strip():
            raise _manual_required()
        if not isinstance(raw_ranges, (list, tuple)) or not (
            MIN_CLASSIFIED_CUES_PER_SPEAKER
            <= len(raw_ranges)
            <= speaker_cast.MAX_SIDECAR_CUES
        ):
            raise _manual_required()
        total_input_cues += len(raw_ranges)
        if total_input_cues > speaker_cast.MAX_SIDECAR_CUES:
            raise _manual_required()
        items: list[dict[str, float]] = []
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
            items.append({"start": start, "end": end})
        items.sort(key=lambda item: (item["start"], item["end"]))
        validated[speaker_id] = items
    return validated


def _union_seconds(items: list[dict[str, float]]) -> float:
    intervals = sorted((item["start"], item["end"]) for item in items)
    if not intervals:
        return 0.0
    total = 0.0
    current_start, current_end = intervals[0]
    for start, end in intervals[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
        else:
            total += current_end - current_start
            current_start, current_end = start, end
    return total + current_end - current_start


def _has_overlap(items: list[dict[str, Any]]) -> bool:
    intervals = sorted((float(item["start"]), float(item["end"])) for item in items)
    return any(start < previous_end for (_, previous_end), (start, _) in zip(intervals, intervals[1:]))


def _select_bounded_cues(
    ranges_by_speaker: Mapping[str, object],
) -> dict[str, list[dict[str, float]]]:
    validated = _validated_ranges(ranges_by_speaker)
    selected: dict[str, list[dict[str, float]]] = {
        speaker_id: [] for speaker_id in validated
    }
    candidates: list[
        tuple[float, float, float, str, int, dict[str, float]]
    ] = []
    for speaker_id, items in validated.items():
        for index, item in enumerate(items):
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
    candidates.sort(key=lambda candidate: candidate[:5])
    selected_ids: set[tuple[str, int]] = set()

    def add_candidate(speaker_id: str, index: int, item: dict[str, float]) -> bool:
        flattened = [
            current for values in selected.values() for current in values
        ]
        proposed = flattened + [item]
        if _has_overlap(proposed):
            return False
        if _union_seconds(proposed) > MAX_JOB_EVIDENCE_SECONDS + 1e-9:
            return False
        selected[speaker_id].append(dict(item))
        selected_ids.add((speaker_id, index))
        return True

    for _duration, _end, _start, speaker_id, index, item in candidates:
        if len(selected[speaker_id]) >= MIN_CLASSIFIED_CUES_PER_SPEAKER:
            continue
        add_candidate(speaker_id, index, item)
    if any(len(items) < MIN_CLASSIFIED_CUES_PER_SPEAKER for items in selected.values()):
        raise _manual_required()

    for _duration, _end, _start, speaker_id, index, item in candidates:
        if (
            (speaker_id, index) in selected_ids
            or len(selected[speaker_id]) >= MAX_CUES_PER_SPEAKER
        ):
            continue
        add_candidate(speaker_id, index, item)

    for values in selected.values():
        values.sort(key=lambda item: (item["start"], item["end"]))
    return selected


def _aggregate_gender_results(
    scores_by_speaker: Mapping[str, object],
) -> dict[str, dict[str, Any]]:
    if not isinstance(scores_by_speaker, Mapping) or len(scores_by_speaker) != 2:
        raise _manual_required()
    all_rows: list[dict[str, float]] = []
    results: dict[str, dict[str, Any]] = {}
    for speaker_id, raw_rows in scores_by_speaker.items():
        if type(speaker_id) is not str or not speaker_id.strip():
            raise _manual_required()
        if not isinstance(raw_rows, (list, tuple)) or not (
            MIN_CLASSIFIED_CUES_PER_SPEAKER
            <= len(raw_rows)
            <= MAX_CUES_PER_SPEAKER
        ):
            raise _manual_required()
        rows: list[dict[str, float]] = []
        male_votes = 0
        female_votes = 0
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
                not all(math.isfinite(value) for value in (start, end, male_score, female_score))
                or start < 0.0
                or end <= start
                or male_score < 0.0
                or female_score < 0.0
                or male_score == female_score
            ):
                raise _manual_required()
            if male_score > female_score:
                male_votes += 1
            else:
                female_votes += 1
            rows.append({"start": start, "end": end})
        winner_votes = max(male_votes, female_votes)
        dominance = winner_votes / len(rows)
        if dominance < MIN_VOTE_DOMINANCE:
            raise _manual_required()
        gender = "male" if male_votes > female_votes else "female"
        voiced_seconds = _union_seconds(rows)
        if voiced_seconds <= 0.0:
            raise _manual_required()
        all_rows.extend(rows)
        results[speaker_id] = {
            "speaker_id": speaker_id,
            "voice_gender": gender,
            "voice_register": "low" if gender == "male" else "high",
            "confidence": round(float(dominance), 6),
            "voiced_seconds": round(float(voiced_seconds), 6),
            "sample_count": int(round(voiced_seconds * PCM_SAMPLE_RATE)),
            "cue_count": len(rows),
            "male_votes": male_votes,
            "female_votes": female_votes,
            "reason": "classified_panns_audioset_after_uvr",
        }
    if _union_seconds(all_rows) > MAX_JOB_EVIDENCE_SECONDS + 1e-9:
        raise _manual_required()
    return results


def _stft(np: Any, chunk: Any) -> Any:
    periodic_hann = np.hanning(_N_FFT + 1)[:-1].astype(np.float32)
    padded = np.pad(chunk, ((0, 0), (_TRIM, _TRIM)), mode="reflect")
    frames = np.lib.stride_tricks.sliding_window_view(
        padded,
        window_shape=_N_FFT,
        axis=-1,
    )[:, ::_HOP, :]
    if frames.shape[1] != _SEGMENT_SIZE:
        raise ValueError("unexpected_stft_frames")
    spectrum = np.fft.rfft(frames * periodic_hann, n=_N_FFT, axis=-1)
    spectrum = spectrum.transpose(0, 2, 1)
    packed = np.stack((spectrum.real, spectrum.imag), axis=1)
    return packed.reshape(1, 4, _N_FFT // 2 + 1, _SEGMENT_SIZE)[
        ..., :_DIM_F, :
    ].astype(np.float32)


def _istft(np: Any, packed: Any) -> Any:
    periodic_hann = np.hanning(_N_FFT + 1)[:-1].astype(np.float64)
    missing_bins = (_N_FFT // 2 + 1) - packed.shape[-2]
    padded = np.pad(packed, ((0, 0), (0, 0), (0, missing_bins), (0, 0)))
    reshaped = padded.reshape(1, 2, 2, _N_FFT // 2 + 1, _SEGMENT_SIZE)
    complex_frames = reshaped[:, :, 0] + (1.0j * reshaped[:, :, 1])
    time_frames = np.fft.irfft(complex_frames, n=_N_FFT, axis=2)
    output_length = _N_FFT + _HOP * (_SEGMENT_SIZE - 1)
    output = np.zeros((1, 2, output_length), dtype=np.float64)
    divider = np.zeros(output_length, dtype=np.float64)
    window_square = periodic_hann * periodic_hann
    for frame_index in range(_SEGMENT_SIZE):
        start = frame_index * _HOP
        output[:, :, start : start + _N_FFT] += (
            time_frames[:, :, :, frame_index] * periodic_hann
        )
        divider[start : start + _N_FFT] += window_square
    valid = divider > 1e-12
    output[:, :, valid] /= divider[valid]
    return output[:, :, _TRIM:-_TRIM].astype(np.float32)


def _demix_vocals(
    np: Any,
    mix: Any,
    session: Any,
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
) -> Any:
    sample_count = mix.shape[-1]
    pad = _GEN_SIZE + _TRIM - (sample_count % _GEN_SIZE)
    mixture = np.concatenate(
        (
            np.zeros((2, _TRIM), dtype=np.float32),
            mix,
            np.zeros((2, pad), dtype=np.float32),
        ),
        axis=1,
    )
    step = int((1.0 - _OVERLAP) * _CHUNK_SIZE)
    result = np.zeros((1, 2, mixture.shape[-1]), dtype=np.float32)
    divider = np.zeros((1, 2, mixture.shape[-1]), dtype=np.float32)
    for start in range(0, mixture.shape[-1], step):
        _ensure_active(deadline_monotonic, stop_requested)
        end = min(start + _CHUNK_SIZE, mixture.shape[-1])
        actual = end - start
        part = mixture[:, start:end]
        if actual < _CHUNK_SIZE:
            part = np.pad(part, ((0, 0), (0, _CHUNK_SIZE - actual)))
        spectrum = _stft(np, part)
        spectrum[:, :, :3, :] = 0.0
        predicted = session.run(None, {"input": spectrum})[0]
        time_domain = _istft(np, predicted)
        window = np.hanning(actual).astype(np.float32).reshape(1, 1, -1)
        time_domain[:, :, :actual] *= window
        divider[:, :, start:end] += window
        result[:, :, start:end] += time_domain[:, :, :actual]
    safe = divider > 1e-10
    result[safe] /= divider[safe]
    return result[:, :, _TRIM:-_TRIM][:, :, :sample_count][0]


def _read_montage(np: Any, pcm_path: Path, selected: Mapping[str, list[dict]]) -> tuple[Any, dict[str, list[dict]]]:
    entries = sorted(
        (item["start"], item["end"], speaker_id)
        for speaker_id, items in selected.items()
        for item in items
    )
    pieces = []
    mapped: dict[str, list[dict]] = {speaker_id: [] for speaker_id in selected}
    montage_offset = 0
    file_size = pcm_path.stat().st_size
    with pcm_path.open("rb") as handle:
        for start, end, speaker_id in entries:
            first_frame = int(round(start * PCM_SAMPLE_RATE))
            frame_count = int(round((end - start) * PCM_SAMPLE_RATE))
            byte_offset = first_frame * PCM_FRAME_BYTES
            byte_count = frame_count * PCM_FRAME_BYTES
            if frame_count <= 0 or byte_offset + byte_count > file_size:
                raise ValueError("pcm_range_outside_file")
            handle.seek(byte_offset)
            raw = handle.read(byte_count)
            if len(raw) != byte_count:
                raise ValueError("pcm_range_truncated")
            values = np.frombuffer(raw, dtype="<i2")
            if values.size != frame_count * PCM_CHANNELS:
                raise ValueError("pcm_frame_shape_invalid")
            piece = values.reshape(-1, PCM_CHANNELS).T.astype(np.float32) / 32768.0
            pieces.append(piece)
            mapped[speaker_id].append(
                {
                    "start": start,
                    "end": end,
                    "montage_start": montage_offset,
                    "montage_end": montage_offset + frame_count,
                }
            )
            montage_offset += frame_count
    if not pieces:
        raise ValueError("pcm_montage_empty")
    return np.concatenate(pieces, axis=1), mapped


def _resample_for_panns(np: Any, signal: Any) -> Any:
    target_count = int(round(len(signal) * PANN_SAMPLE_RATE / PCM_SAMPLE_RATE))
    if len(signal) < 2 or target_count < 2:
        raise ValueError("panns_signal_too_short")
    source_positions = np.arange(len(signal), dtype=np.float64)
    target_positions = (
        np.arange(target_count, dtype=np.float64) * PCM_SAMPLE_RATE / PANN_SAMPLE_RATE
    )
    return np.interp(target_positions, source_positions, signal).astype(np.float32)


def _session(ort: Any, model_path: Path) -> Any:
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    return ort.InferenceSession(
        str(model_path),
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )


def _infer_selected_cues(
    pcm_path: Path,
    selected: Mapping[str, list[dict]],
    model_paths: tuple[Path, Path],
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
) -> dict[str, list[dict[str, float]]]:
    _ensure_active(deadline_monotonic, stop_requested)
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    import numpy as np
    import onnxruntime as ort

    mix, mapped = _read_montage(np, pcm_path, selected)
    peak = float(np.max(np.abs(mix)))
    if not math.isfinite(peak) or peak <= 0.0:
        raise ValueError("pcm_montage_silent")
    normalized = mix.copy()
    if peak > 0.9:
        normalized *= 0.9 / peak
    uvr_session = _session(ort, model_paths[0])
    vocals = _demix_vocals(
        np,
        normalized,
        uvr_session,
        deadline_monotonic=deadline_monotonic,
        stop_requested=stop_requested,
    )
    vocals *= peak
    del uvr_session
    pann_session = _session(ort, model_paths[1])
    results: dict[str, list[dict[str, float]]] = {
        speaker_id: [] for speaker_id in selected
    }
    for speaker_id, rows in mapped.items():
        for row in rows:
            _ensure_active(deadline_monotonic, stop_requested)
            cue = vocals[:, row["montage_start"] : row["montage_end"]].mean(axis=0)
            signal = _resample_for_panns(np, cue)
            scores = pann_session.run(
                ["clipwise_output"],
                {"input_values": signal.reshape(1, -1)},
            )[0][0]
            if len(scores) <= _FEMALE_SINGING_INDEX:
                raise ValueError("panns_output_shape_invalid")
            results[speaker_id].append(
                {
                    "start": float(row["start"]),
                    "end": float(row["end"]),
                    "male_score": float(
                        max(scores[_MALE_SPEECH_INDEX], scores[_MALE_SINGING_INDEX])
                    ),
                    "female_score": float(
                        max(scores[_FEMALE_SPEECH_INDEX], scores[_FEMALE_SINGING_INDEX])
                    ),
                }
            )
    return results


def classify_two_speaker_genders(
    stereo_pcm_path: str,
    ranges_by_speaker: Mapping[str, object],
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
) -> dict[str, dict[str, Any]]:
    """Classify exactly two diarized speaker groups without pairing heuristics."""

    if not _CLASSIFIER_LOCK.acquire(blocking=False):
        raise _manual_required()
    try:
        try:
            _ensure_active(deadline_monotonic, stop_requested)
            selected = _select_bounded_cues(ranges_by_speaker)
            path = Path(str(stereo_pcm_path or ""))
            if not path.is_file() or path.stat().st_size <= 0:
                raise ValueError("stereo_pcm_missing")
            if path.stat().st_size % PCM_FRAME_BYTES:
                raise ValueError("stereo_pcm_shape_invalid")
            model_paths = _validated_model_paths()
            scores = _infer_selected_cues(
                path,
                selected,
                model_paths,
                deadline_monotonic=deadline_monotonic,
                stop_requested=stop_requested,
            )
            _ensure_active(deadline_monotonic, stop_requested)
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
        _CLASSIFIER_LOCK.release()
