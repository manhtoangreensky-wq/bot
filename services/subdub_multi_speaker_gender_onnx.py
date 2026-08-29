"""Multi-speaker gender/register adapter over the proven exact-two ONNX engine."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from services import subdub_speaker_cast as speaker_cast
from services import subdub_two_speaker_gender_onnx as exact_gender


MIN_MULTI_SPEAKERS = 3
MAX_MULTI_SPEAKERS = speaker_cast.MAX_AUTO_SPEAKER_LABELS
MIN_CLASSIFIED_CUES_PER_SPEAKER = 2
MAX_CUES_PER_SPEAKER = exact_gender.MAX_CUES_PER_SPEAKER
MIN_VOTE_DOMINANCE = exact_gender.MIN_VOTE_DOMINANCE
MAX_JOB_EVIDENCE_SECONDS = exact_gender.MAX_JOB_EVIDENCE_SECONDS
CLASSIFIER_WALL_TIMEOUT_SECONDS = exact_gender.CLASSIFIER_WALL_TIMEOUT_SECONDS


def _manual_required(error: Exception | None = None) -> speaker_cast.AutoCastManualRequired:
    result = speaker_cast.AutoCastManualRequired()
    if error is not None:
        result.__cause__ = error
    return result


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
            rows.append({"start": start, "end": end})
        winner_votes = max(male_votes, female_votes)
        dominance = winner_votes / len(rows)
        if dominance < MIN_VOTE_DOMINANCE:
            raise _manual_required()
        gender = "male" if male_votes > female_votes else "female"
        voiced_seconds = exact_gender._union_seconds(rows)
        if voiced_seconds <= 0.0:
            raise _manual_required()
        all_rows.extend(rows)
        results[speaker_id] = {
            "speaker_id": speaker_id,
            "voice_gender": gender,
            "voice_register": "low" if gender == "male" else "high",
            "confidence": round(float(dominance), 6),
            "voiced_seconds": round(float(voiced_seconds), 6),
            "sample_count": int(round(voiced_seconds * exact_gender.PCM_SAMPLE_RATE)),
            "cue_count": len(rows),
            "male_votes": male_votes,
            "female_votes": female_votes,
            "reason": "classified_panns_multi_after_uvr",
        }
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
