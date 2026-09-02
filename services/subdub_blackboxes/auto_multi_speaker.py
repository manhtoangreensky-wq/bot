"""Multi-speaker acoustic profile adapter for the proven Auto SubDub lane."""

from __future__ import annotations

import asyncio
from bisect import bisect_right
from collections.abc import Callable, Mapping
import hashlib
import json
import math
from pathlib import Path
import threading
import time
from typing import Any

from services import subdub_multi_speaker_asr_fallback
from services import subdub_multi_speaker_embedding_onnx
from services import subdub_multi_speaker_gender_onnx
from services import subdub_speaker_cast as speaker_cast
from services import subdub_two_speaker_gender_onnx

from . import auto_speaker


AUTO_MULTI_SPEAKER_LANE = "multi"
MULTI_PCM_AUDIO_FILTER = "highpass=f=70,lowpass=f=320,afftdn=nr=6:nf=-50"
_MULTI_WINDOW_HOP_SECONDS = 0.02
_MULTI_MAX_ACCEPTED_WINDOWS = 12
_UNDERCLUSTER_PROVIDER_LABEL_COUNT = 2
_UNDERCLUSTER_WINDOWS_PER_CUE = 2
_UNDERCLUSTER_MIN_CUES_PER_REGISTER = 2
_UNDERCLUSTER_MIN_REGISTER_GAP_HZ = 30.0
ACOUSTIC_WALL_TIMEOUT_SECONDS = 300.0
MULTI_ACOUSTIC_STATE_FIELDS = frozenset({
    "multi_acoustic_backend",
    "multi_acoustic_model_sha256",
    "multi_acoustic_algorithm_version",
    "multi_acoustic_speaker_count",
    "multi_acoustic_word_count",
    "multi_acoustic_unit_count",
    "multi_acoustic_embedding_window_count",
    "multi_acoustic_cluster_sizes",
    "multi_acoustic_stability_pass",
    "multi_acoustic_word_coverage_count",
})


def bounded_multi_acoustic_evidence(
    source: Mapping[str, object] | None,
) -> dict[str, object]:
    """Return one exact typed acoustic evidence bundle or fail closed empty."""

    current = source if isinstance(source, Mapping) else {}
    count_fields = (
        "multi_acoustic_speaker_count",
        "multi_acoustic_word_count",
        "multi_acoustic_unit_count",
        "multi_acoustic_embedding_window_count",
        "multi_acoustic_word_coverage_count",
    )
    if any(type(current.get(field)) is not int for field in count_fields):
        return {}
    try:
        speaker_count = int(current.get("multi_acoustic_speaker_count"))
        word_count = int(current.get("multi_acoustic_word_count"))
        unit_count = int(current.get("multi_acoustic_unit_count"))
        window_count = int(current.get("multi_acoustic_embedding_window_count"))
        coverage_count = int(current.get("multi_acoustic_word_coverage_count"))
        cluster_sizes = list(current.get("multi_acoustic_cluster_sizes") or [])
    except (TypeError, ValueError, OverflowError):
        return {}
    if (
        current.get("multi_acoustic_backend")
        != subdub_multi_speaker_embedding_onnx.FIXED_VOCAL_PROVIDER
        or current.get("multi_acoustic_model_sha256")
        != subdub_multi_speaker_embedding_onnx.MODEL_SHA256
        or current.get("multi_acoustic_algorithm_version")
        != subdub_multi_speaker_embedding_onnx.FIXED_VOCAL_ALGORITHM_VERSION
        or not 3 <= speaker_count <= subdub_multi_speaker_embedding_onnx.MAX_SPEAKERS
        or not 0 < word_count <= speaker_cast.MAX_SIDECAR_CUES
        or not subdub_multi_speaker_embedding_onnx.MIN_UNITS
        <= unit_count
        <= subdub_multi_speaker_embedding_onnx.MAX_CLUSTER_UNITS
        or window_count < unit_count * 2
        or window_count > subdub_multi_speaker_embedding_onnx.MAX_CLUSTER_UNITS * 2
        or window_count % 2 != 0
        or coverage_count != word_count
        or len(cluster_sizes) != speaker_count
        or any(type(value) is not int or value < 2 for value in cluster_sizes)
        or sum(cluster_sizes) != window_count // 2
        or current.get("multi_acoustic_stability_pass") is not True
    ):
        return {}
    return {
        "multi_acoustic_backend": (
            subdub_multi_speaker_embedding_onnx.FIXED_VOCAL_PROVIDER
        ),
        "multi_acoustic_model_sha256": (
            subdub_multi_speaker_embedding_onnx.MODEL_SHA256
        ),
        "multi_acoustic_algorithm_version": (
            subdub_multi_speaker_embedding_onnx.FIXED_VOCAL_ALGORITHM_VERSION
        ),
        "multi_acoustic_speaker_count": speaker_count,
        "multi_acoustic_word_count": word_count,
        "multi_acoustic_unit_count": unit_count,
        "multi_acoustic_embedding_window_count": window_count,
        "multi_acoustic_cluster_sizes": cluster_sizes,
        "multi_acoustic_stability_pass": True,
        "multi_acoustic_word_coverage_count": coverage_count,
    }


def acoustic_sidecar_evidence(
    evidence: Mapping[str, object] | None,
) -> dict[str, object]:
    bounded = bounded_multi_acoustic_evidence(evidence)
    if not bounded:
        return {}
    return {
        "algorithm_version": bounded["multi_acoustic_algorithm_version"],
        "backend": bounded["multi_acoustic_backend"],
        "cluster_sizes": list(bounded["multi_acoustic_cluster_sizes"]),
        "embedding_window_count": bounded[
            "multi_acoustic_embedding_window_count"
        ],
        "model_sha256": bounded["multi_acoustic_model_sha256"],
        "speaker_count": bounded["multi_acoustic_speaker_count"],
        "stability_pass": bounded["multi_acoustic_stability_pass"],
        "unit_count": bounded["multi_acoustic_unit_count"],
        "word_count": bounded["multi_acoustic_word_count"],
        "word_coverage_count": bounded["multi_acoustic_word_coverage_count"],
    }


async def run_local_acoustic_diarization_off_event_loop(
    pcm_path: Path,
    word_timeline: list[dict],
    *,
    duration_seconds: float,
    acoustic_diarize: Callable = (
        subdub_multi_speaker_embedding_onnx.diarize_fixed_vocal_word_timeline
    ),
) -> dict[str, object]:
    """Run the local acoustic engine off-loop and clean transient PCM safely."""

    path = Path(pcm_path)
    if (
        not path.is_file()
        or path.stat().st_size <= 0
        or type(word_timeline) is not list
        or not word_timeline
        or type(duration_seconds) not in {int, float}
        or not math.isfinite(float(duration_seconds))
        or float(duration_seconds) <= 0.0
        or not callable(acoustic_diarize)
    ):
        auto_speaker._cleanup_pcm_path(path)
        raise speaker_cast.AutoCastManualRequired()

    pcm_bytes = path.stat().st_size
    pcm_frame_bytes = subdub_two_speaker_gender_onnx.PCM_FRAME_BYTES
    if pcm_bytes % pcm_frame_bytes:
        auto_speaker._cleanup_pcm_path(path)
        raise speaker_cast.AutoCastManualRequired()
    measured_duration_seconds = pcm_bytes / float(
        subdub_two_speaker_gender_onnx.PCM_SAMPLE_RATE * pcm_frame_bytes
    )
    if not math.isfinite(measured_duration_seconds) or measured_duration_seconds <= 0.0:
        auto_speaker._cleanup_pcm_path(path)
        raise speaker_cast.AutoCastManualRequired()

    deadline = time.monotonic() + float(ACOUSTIC_WALL_TIMEOUT_SECONDS)
    stop_event = threading.Event()
    worker = asyncio.create_task(
        asyncio.to_thread(
            acoustic_diarize,
            str(path),
            list(word_timeline),
            duration_seconds=measured_duration_seconds,
            deadline_monotonic=deadline,
            stop_requested=stop_event.is_set,
        )
    )
    drain_attempted = False
    try:
        result = await asyncio.wait_for(
            asyncio.shield(worker),
            max(0.0, deadline - time.monotonic()),
        )
        if not isinstance(result, Mapping) or result.get("ok") is not True:
            raise speaker_cast.AutoCastManualRequired()
        return dict(result)
    except (asyncio.TimeoutError, TimeoutError) as exc:
        stop_event.set()
        await auto_speaker._drain_worker_bounded(worker)
        drain_attempted = True
        raise speaker_cast.AutoCastManualRequired() from exc
    except asyncio.CancelledError:
        stop_event.set()
        await auto_speaker._drain_worker_bounded(worker)
        drain_attempted = True
        raise
    except (speaker_cast.AutoCastUnavailable, speaker_cast.AutoCastManualRequired):
        raise
    except Exception as exc:
        raise speaker_cast.AutoCastManualRequired() from exc
    finally:
        if not worker.done() and not drain_attempted:
            stop_event.set()
            await auto_speaker._drain_worker_bounded(worker)
        if not auto_speaker._cleanup_pcm_path(path):
            raise speaker_cast.AutoCastManualRequired()


def _multi_diarization_debug_fields(source: Mapping[str, object]) -> dict[str, object]:
    current = source if isinstance(source, Mapping) else {}
    if "multi_diarization_attempted" not in current:
        return {}

    def bounded_int(field: str) -> int:
        try:
            return max(0, int(current.get(field) or 0))
        except (TypeError, ValueError, OverflowError):
            return 0

    return {
        "multi_diarization_attempted": bool(current.get("multi_diarization_attempted")),
        "multi_diarization_provider": str(current.get("multi_diarization_provider") or "")[:80],
        "multi_diarization_status": str(current.get("multi_diarization_status") or "")[:80],
        "multi_diarization_detail": str(current.get("multi_diarization_detail") or "")[:180],
        "multi_diarization_http_status": bounded_int("multi_diarization_http_status"),
        "multi_diarization_provider_word_count": bounded_int("multi_diarization_provider_word_count"),
        "multi_diarization_provider_speaker_count": bounded_int("multi_diarization_provider_speaker_count"),
        "multi_diarization_mapped_speaker_count": bounded_int("multi_diarization_mapped_speaker_count"),
        "multi_diarization_raw_annotation_count": bounded_int("multi_diarization_raw_annotation_count"),
        "multi_diarization_terminal_empty": bool(current.get("multi_diarization_terminal_empty") is True),
        "multi_diarization_parse_rejection": str(
            current.get("multi_diarization_parse_rejection") or ""
        )[:80],
        "multi_diarization_dropped_weak_word_count": bounded_int(
            "multi_diarization_dropped_weak_word_count"
        ),
        "multi_diarization_dropped_weak_speaker_count": bounded_int(
            "multi_diarization_dropped_weak_speaker_count"
        ),
        "multi_diarization_weak_label_filter_applied": bool(
            current.get("multi_diarization_weak_label_filter_applied") is True
        ),
    }


def _multi_manual_required_result(
    state: Mapping[str, object],
    error: Exception,
) -> dict[str, Any]:
    evidence = _multi_diarization_debug_fields(state)
    result = auto_speaker._manual_required_result(state, error)
    if not evidence:
        return result
    return {
        **result,
        **evidence,
        "state": {**dict(state), **evidence},
    }


def _dense_window_offsets(
    ranges: object,
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
    max_windows: int,
) -> list[int]:
    if (
        not isinstance(ranges, (list, tuple))
        or len(ranges) > speaker_cast.MAX_SIDECAR_CUES
        or type(max_windows) is not int
        or max_windows < 1
    ):
        raise speaker_cast.AutoCastManualRequired()

    window_seconds = (
        speaker_cast.PCM_WINDOW_SAMPLES / speaker_cast.PCM_SAMPLE_RATE
    )
    runs: list[tuple[float, float, int, int]] = []
    cumulative_counts: list[int] = []
    total_candidates = 0
    previous_start = -1.0
    for position, raw_range in enumerate(ranges):
        if position % 64 == 0:
            speaker_cast._ensure_classifier_active(
                deadline_monotonic,
                stop_requested,
            )
        if not isinstance(raw_range, (list, tuple)) or len(raw_range) != 2:
            raise speaker_cast.AutoCastManualRequired()
        try:
            start = float(raw_range[0])
            end = float(raw_range[1])
        except (TypeError, ValueError, OverflowError) as exc:
            raise speaker_cast.AutoCastManualRequired() from exc
        if (
            not math.isfinite(start)
            or not math.isfinite(end)
            or start < 0.0
            or end <= start
            or start < previous_start
        ):
            raise speaker_cast.AutoCastManualRequired()
        previous_start = start
        available = end - start - window_seconds
        if available < -1e-12:
            continue
        available = max(0.0, available)
        regular_steps = int(
            math.floor((available + 1e-12) / _MULTI_WINDOW_HOP_SECONDS)
        )
        regular_count = regular_steps + 1
        terminal_count = int(
            available - (regular_steps * _MULTI_WINDOW_HOP_SECONDS) > 1e-12
        )
        run_count = regular_count + terminal_count
        total_candidates += run_count
        runs.append((start, available, regular_count, run_count))
        cumulative_counts.append(total_candidates)

    if total_candidates < 1:
        return []
    selected_count = min(total_candidates, max_windows)
    run_quotas = [0] * len(runs)
    if selected_count <= len(runs):
        if selected_count == 1:
            selected_runs = [len(runs) // 2]
        else:
            selected_runs = [
                round(index * (len(runs) - 1) / (selected_count - 1))
                for index in range(selected_count)
            ]
        for run_index in selected_runs:
            run_quotas[run_index] = 1
    else:
        run_quotas = [1] * len(runs)
        remaining = selected_count - len(runs)
        while remaining:
            progressed = False
            for run_index, run in enumerate(runs):
                if run_quotas[run_index] >= run[3]:
                    continue
                run_quotas[run_index] += 1
                remaining -= 1
                progressed = True
                if not remaining:
                    break
            if not progressed:
                raise speaker_cast.AutoCastManualRequired()

    selected_indexes: list[int] = []
    previous_count = 0
    for run_index, run in enumerate(runs):
        run_count = run[3]
        quota = run_quotas[run_index]
        if quota == 1:
            local_indexes = [run_count // 2]
        elif quota > 1:
            local_indexes = [
                round(index * (run_count - 1) / (quota - 1))
                for index in range(quota)
            ]
        else:
            local_indexes = []
        selected_indexes.extend(
            previous_count + local_index for local_index in local_indexes
        )
        previous_count = cumulative_counts[run_index]

    offsets: list[int] = []
    seen_offsets: set[int] = set()
    for selected_index in selected_indexes:
        speaker_cast._ensure_classifier_active(
            deadline_monotonic,
            stop_requested,
        )
        run_index = bisect_right(cumulative_counts, selected_index)
        previous_count = cumulative_counts[run_index - 1] if run_index else 0
        local_index = selected_index - previous_count
        start, available, regular_count, _run_count = runs[run_index]
        if local_index < regular_count:
            cursor = start + min(
                available,
                local_index * _MULTI_WINDOW_HOP_SECONDS,
            )
        else:
            cursor = start + available
        offset = (
            int(round(cursor * speaker_cast.PCM_SAMPLE_RATE)) * 2
        )
        if offset not in seen_offsets:
            seen_offsets.add(offset)
            offsets.append(offset)
    return offsets


def _classify_dense_multi_speaker_registers(
    pcm_path: str,
    ranges_by_speaker: dict[str, list[tuple[float, float]]],
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
) -> dict[str, dict]:
    if not callable(stop_requested):
        raise speaker_cast.AutoCastManualRequired()
    try:
        absolute_deadline = float(deadline_monotonic)
    except (TypeError, ValueError, OverflowError) as exc:
        raise speaker_cast.AutoCastManualRequired() from exc
    if not math.isfinite(absolute_deadline):
        raise speaker_cast.AutoCastManualRequired()

    labels = speaker_cast.ordered_auto_speaker_labels(
        {"speaker_id": speaker_id} for speaker_id in ranges_by_speaker
    )
    if len(labels) != len(ranges_by_speaker):
        raise speaker_cast.AutoCastManualRequired()
    window_seconds = (
        speaker_cast.PCM_WINDOW_SAMPLES / speaker_cast.PCM_SAMPLE_RATE
    )
    maximum_reported_windows = int(
        speaker_cast.MAX_SPEAKER_VOICED_SECONDS / window_seconds
    )
    maximum_job_windows = int(
        speaker_cast.MAX_JOB_SAMPLE_SECONDS / window_seconds
    )
    candidate_windows_per_speaker = max(
        maximum_reported_windows,
        maximum_job_windows // len(labels),
    )
    accepted_windows_per_speaker = min(
        candidate_windows_per_speaker,
        max(maximum_reported_windows, _MULTI_MAX_ACCEPTED_WINDOWS),
    )

    sampled_job_seconds = 0.0
    results: dict[str, dict] = {}
    try:
        with open(str(pcm_path or ""), "rb") as handle:
            for speaker_id in labels:
                offsets = _dense_window_offsets(
                    ranges_by_speaker.get(speaker_id),
                    deadline_monotonic=absolute_deadline,
                    stop_requested=stop_requested,
                    max_windows=candidate_windows_per_speaker,
                )
                frequencies: list[float] = []
                confidences: list[float] = []
                for offset in offsets:
                    sampled_job_seconds += window_seconds
                    if sampled_job_seconds > speaker_cast.MAX_JOB_SAMPLE_SECONDS + 1e-12:
                        raise speaker_cast.AutoCastManualRequired()
                    speaker_cast._ensure_classifier_active(
                        absolute_deadline,
                        stop_requested,
                    )
                    handle.seek(offset)
                    raw = handle.read(speaker_cast.PCM_WINDOW_BYTES)
                    if len(raw) != speaker_cast.PCM_WINDOW_BYTES:
                        raise speaker_cast.AutoCastManualRequired()
                    estimate = speaker_cast._estimate_window_pitch(
                        raw,
                        deadline_monotonic=absolute_deadline,
                        stop_requested=stop_requested,
                    )
                    if estimate is None:
                        continue
                    frequencies.append(float(estimate[0]))
                    confidences.append(float(estimate[1]))
                    if len(frequencies) >= accepted_windows_per_speaker:
                        break

                register, _median_hz, confidence, inlier_count = (
                    speaker_cast._stable_register_evidence(
                        frequencies,
                        confidences,
                    )
                )
                reported_windows = min(
                    inlier_count,
                    maximum_reported_windows,
                )
                results[speaker_id] = {
                    "speaker_id": speaker_id,
                    "voice_register": register,
                    "confidence": round(float(confidence), 6),
                    "voiced_seconds": round(
                        reported_windows * window_seconds,
                        3,
                    ),
                    "sample_count": int(
                        reported_windows * speaker_cast.PCM_WINDOW_SAMPLES
                    ),
                    "reason": "classified",
                }
                speaker_cast._ensure_classifier_active(
                    absolute_deadline,
                    stop_requested,
                )
    except speaker_cast.AutoCastManualRequired:
        raise
    except (OSError, ValueError, TypeError, OverflowError, MemoryError) as exc:
        raise speaker_cast.AutoCastManualRequired() from exc

    if not results:
        raise speaker_cast.AutoCastManualRequired()
    return results


def _cue_register_evidence(
    handle,
    start: float,
    end: float,
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
) -> tuple[tuple[str, float] | None, int]:
    offsets = _dense_window_offsets(
        [(start, end)],
        deadline_monotonic=deadline_monotonic,
        stop_requested=stop_requested,
        max_windows=_UNDERCLUSTER_WINDOWS_PER_CUE,
    )
    frequencies: list[float] = []
    confidences: list[float] = []
    for offset in offsets:
        speaker_cast._ensure_classifier_active(
            deadline_monotonic,
            stop_requested,
        )
        handle.seek(offset)
        raw = handle.read(speaker_cast.PCM_WINDOW_BYTES)
        if len(raw) != speaker_cast.PCM_WINDOW_BYTES:
            raise speaker_cast.AutoCastManualRequired()
        estimate = speaker_cast._estimate_window_pitch(
            raw,
            deadline_monotonic=deadline_monotonic,
            stop_requested=stop_requested,
        )
        if estimate is not None:
            frequencies.append(float(estimate[0]))
            confidences.append(float(estimate[1]))
    try:
        register, median_hz, _confidence, _inlier_count = (
            speaker_cast._stable_register_evidence(
                frequencies,
                confidences,
            )
        )
    except speaker_cast.AutoCastManualRequired:
        return None, len(offsets)
    return (register, float(median_hz)), len(offsets)


def _refine_underclustered_prepared(
    pcm_path: str,
    prepared: dict,
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
) -> dict:
    source_segments = prepared.get("source_segments")
    output_segments = prepared.get("output_segments")
    if (
        not isinstance(source_segments, list)
        or not source_segments
        or not isinstance(output_segments, list)
        or not output_segments
    ):
        raise speaker_cast.AutoCastManualRequired()
    labels = speaker_cast.ordered_auto_speaker_labels(source_segments)
    if len(labels) != _UNDERCLUSTER_PROVIDER_LABEL_COUNT:
        return prepared

    label_identities = {
        label: speaker_cast.validated_speaker_identity(
            {"speaker_id": label}
        )
        for label in labels
    }
    used_by_chunk: dict[int, set[int]] = {}
    for chunk_index, speaker_index, _speaker_id in label_identities.values():
        used_by_chunk.setdefault(chunk_index, set()).add(speaker_index)

    evidence_by_cue: dict[tuple[str, float, float], tuple[str, float] | None] = {}
    sampled_windows = 0
    maximum_job_windows = int(
        speaker_cast.MAX_JOB_SAMPLE_SECONDS
        / (speaker_cast.PCM_WINDOW_SAMPLES / speaker_cast.PCM_SAMPLE_RATE)
    )
    try:
        with open(str(pcm_path or ""), "rb") as handle:
            for raw_segment in source_segments:
                identity = auto_speaker._exact_cue_identity(raw_segment)
                if identity in evidence_by_cue:
                    raise speaker_cast.AutoCastManualRequired()
                speaker_id = raw_segment.get("speaker_id")
                if speaker_id not in label_identities:
                    raise speaker_cast.AutoCastManualRequired()
                evidence, consumed_windows = _cue_register_evidence(
                    handle,
                    identity[1],
                    identity[2],
                    deadline_monotonic=deadline_monotonic,
                    stop_requested=stop_requested,
                )
                sampled_windows += consumed_windows
                if sampled_windows > maximum_job_windows:
                    raise speaker_cast.AutoCastManualRequired()
                evidence_by_cue[identity] = evidence
    except speaker_cast.AutoCastManualRequired:
        raise
    except (OSError, TypeError, ValueError, OverflowError, MemoryError) as exc:
        raise speaker_cast.AutoCastManualRequired() from exc

    split_targets: dict[str, tuple[str, str, int, int]] = {}
    for label in labels:
        grouped: dict[str, list[tuple[tuple[str, float, float], float]]] = {
            "low": [],
            "high": [],
        }
        first_register = ""
        for raw_segment in source_segments:
            if raw_segment.get("speaker_id") != label:
                continue
            identity = auto_speaker._exact_cue_identity(raw_segment)
            evidence = evidence_by_cue.get(identity)
            if evidence is None:
                continue
            register, median_hz = evidence
            grouped[register].append((identity, median_hz))
            if not first_register:
                first_register = register
        if any(
            len(grouped[register]) < _UNDERCLUSTER_MIN_CUES_PER_REGISTER
            for register in ("low", "high")
        ):
            continue
        low_median = speaker_cast._bounded_median(
            [item[1] for item in grouped["low"]]
        )
        high_median = speaker_cast._bounded_median(
            [item[1] for item in grouped["high"]]
        )
        if high_median - low_median < _UNDERCLUSTER_MIN_REGISTER_GAP_HZ:
            continue
        chunk_index = label_identities[label][0]
        available_index = next(
            (
                index
                for index in range(speaker_cast.MAX_SPEAKER_LABELS)
                if index not in used_by_chunk.setdefault(chunk_index, set())
            ),
            None,
        )
        if available_index is None:
            raise speaker_cast.AutoCastManualRequired()
        used_by_chunk[chunk_index].add(available_index)
        split_register = "high" if first_register == "low" else "low"
        split_targets[label] = (
            split_register,
            speaker_cast.normalized_speaker_key(
                chunk_index,
                available_index,
            ),
            chunk_index,
            available_index,
        )

    if not split_targets:
        return prepared

    relabeled_source: list[dict[str, Any]] = []
    assignments: dict[tuple[str, float, float], dict[str, object]] = {}
    for raw_segment in source_segments:
        identity = auto_speaker._exact_cue_identity(raw_segment)
        segment = dict(raw_segment)
        target = split_targets.get(str(segment.get("speaker_id") or ""))
        evidence = evidence_by_cue.get(identity)
        if target is not None and evidence is not None and evidence[0] == target[0]:
            segment.update(
                {
                    "speaker_id": target[1],
                    "chunk_index": target[2],
                    "speaker": target[3],
                }
            )
        assignments[identity] = {
            key: segment[key]
            for key in (
                "speaker",
                "speaker_confidence",
                "speaker_id",
                "chunk_index",
            )
            if key in segment
        }
        relabeled_source.append(segment)

    if not 3 <= len(
        speaker_cast.ordered_auto_speaker_labels(relabeled_source)
    ) <= speaker_cast.MAX_AUTO_SPEAKER_LABELS:
        raise speaker_cast.AutoCastManualRequired()

    relabeled_output: list[dict[str, Any]] = []
    output_identities: set[tuple[str, float, float]] = set()
    for raw_segment in output_segments:
        identity = auto_speaker._exact_cue_identity(raw_segment)
        if identity in output_identities or identity not in assignments:
            raise speaker_cast.AutoCastManualRequired()
        output_identities.add(identity)
        relabeled_output.append(
            {**dict(raw_segment), **assignments[identity]}
        )
    if output_identities != set(assignments):
        raise speaker_cast.AutoCastManualRequired()

    media_sha256 = auto_speaker._prepared_media_sha256(prepared)
    subtitle_sha256 = auto_speaker._prepared_subtitle_sha256(prepared)
    workspace = auto_speaker._nested_receipt_value(
        prepared,
        "_pipeline_workspace",
    ) or auto_speaker._nested_receipt_value(prepared, "workspace")
    speaker_cast._ensure_classifier_active(
        deadline_monotonic,
        stop_requested,
    )
    sidecar = speaker_cast.build_sidecar(
        relabeled_source,
        media_sha256=media_sha256,
        subtitle_sha256=subtitle_sha256,
    )
    receipt = speaker_cast.persist_sidecar(
        sidecar,
        workspace=workspace,
    )
    prepared_state = dict(auto_speaker._prepared_state(prepared))
    prepared_state.update(
        {
            "speaker_sidecar_path": receipt["path"],
            "speaker_sidecar_sha256": receipt["sha256"],
        }
    )
    return {
        **prepared,
        "state": prepared_state,
        "source_segments": relabeled_source,
        "output_segments": relabeled_output,
        "speaker_sidecar_path": receipt["path"],
        "speaker_sidecar_sha256": receipt["sha256"],
    }


def _apply_provider_rediarization(prepared: dict, result: Mapping[str, object]) -> dict:
    """Persist provider-proven multi identities without pitch-based splitting."""

    source_segments = prepared.get("source_segments")
    output_segments = prepared.get("output_segments")
    mapped_segments = result.get("segments")
    if (
        not isinstance(source_segments, list)
        or not source_segments
        or not isinstance(output_segments, list)
        or not output_segments
        or not isinstance(mapped_segments, list)
        or len(mapped_segments) != len(source_segments)
    ):
        raise speaker_cast.AutoCastManualRequired()
    assignments: dict[tuple[str, float, float], dict[str, object]] = {}
    rediarized_source: list[dict[str, Any]] = []
    for original, mapped in zip(source_segments, mapped_segments, strict=True):
        if (
            not isinstance(original, Mapping)
            or not isinstance(mapped, Mapping)
            or auto_speaker._exact_cue_identity(original)
            != auto_speaker._exact_cue_identity(mapped)
        ):
            raise speaker_cast.AutoCastManualRequired()
        segment = dict(original)
        for key in (
            "speaker",
            "speaker_confidence",
            "speaker_id",
            "chunk_index",
        ):
            if key in mapped:
                segment[key] = mapped[key]
        speaker_cast.validated_speaker_identity(segment)
        identity = auto_speaker._exact_cue_identity(segment)
        if identity in assignments:
            raise speaker_cast.AutoCastManualRequired()
        assignments[identity] = {
            key: segment[key]
            for key in (
                "speaker",
                "speaker_confidence",
                "speaker_id",
                "chunk_index",
            )
            if key in segment
        }
        rediarized_source.append(segment)
    labels = speaker_cast.ordered_auto_speaker_labels(rediarized_source)
    if not 3 <= len(labels) <= speaker_cast.MAX_AUTO_SPEAKER_LABELS:
        raise speaker_cast.AutoCastManualRequired()

    rediarized_output: list[dict[str, Any]] = []
    output_identities: set[tuple[str, float, float]] = set()
    for raw_segment in output_segments:
        identity = auto_speaker._exact_cue_identity(raw_segment)
        if identity in output_identities or identity not in assignments:
            raise speaker_cast.AutoCastManualRequired()
        output_identities.add(identity)
        rediarized_output.append(
            {**dict(raw_segment), **assignments[identity]}
        )
    if output_identities != set(assignments):
        raise speaker_cast.AutoCastManualRequired()

    media_sha256 = auto_speaker._prepared_media_sha256(prepared)
    subtitle_sha256 = auto_speaker._prepared_subtitle_sha256(prepared)
    workspace = auto_speaker._nested_receipt_value(
        prepared,
        "_pipeline_workspace",
    ) or auto_speaker._nested_receipt_value(prepared, "workspace")
    sidecar = speaker_cast.build_sidecar(
        rediarized_source,
        media_sha256=media_sha256,
        subtitle_sha256=subtitle_sha256,
    )
    receipt = speaker_cast.persist_sidecar(sidecar, workspace=workspace)
    prepared_state = dict(auto_speaker._prepared_state(prepared))
    prepared_state.update(
        {
            "speaker_sidecar_path": receipt["path"],
            "speaker_sidecar_sha256": receipt["sha256"],
            "multi_diarization_attempted": True,
            "multi_diarization_provider": str(result.get("provider") or "")[:80],
            "multi_diarization_status": str(result.get("status") or "")[:80],
            "multi_diarization_speaker_count": len(labels),
        }
    )
    return {
        **prepared,
        "state": prepared_state,
        "source_segments": rediarized_source,
        "output_segments": rediarized_output,
        "speaker_sidecar_path": receipt["path"],
        "speaker_sidecar_sha256": receipt["sha256"],
    }


async def _refine_underclustered_off_event_loop(
    pcm_path: Path,
    prepared: dict,
) -> dict:
    started = time.monotonic()
    deadline = started + speaker_cast.CLASSIFIER_WALL_TIMEOUT_SECONDS
    stop_event = threading.Event()
    worker = asyncio.create_task(
        asyncio.to_thread(
            _refine_underclustered_prepared,
            str(pcm_path),
            prepared,
            deadline_monotonic=deadline,
            stop_requested=stop_event.is_set,
        )
    )
    try:
        return await asyncio.wait_for(
            asyncio.shield(worker),
            max(0.0, deadline - time.monotonic()),
        )
    except (asyncio.TimeoutError, TimeoutError) as exc:
        stop_event.set()
        await auto_speaker._drain_worker(worker)
        raise speaker_cast.AutoCastManualRequired() from exc
    except asyncio.CancelledError:
        stop_event.set()
        await auto_speaker._drain_worker(worker)
        raise
    finally:
        if not worker.done():
            stop_event.set()
            await auto_speaker._drain_worker(worker)


def is_auto_multi_speaker_state(
    state: Mapping[str, object] | None,
) -> bool:
    current = state or {}
    return bool(
        auto_speaker.is_auto_speaker_state(current)
        and current.get("auto_speaker_lane") == AUTO_MULTI_SPEAKER_LANE
    )


def classify_multi_speaker_registers(
    pcm_path: str,
    ranges_by_speaker: dict[str, list[tuple[float, float]]],
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
) -> dict[str, dict]:
    if (
        not isinstance(ranges_by_speaker, dict)
        or not 3 <= len(ranges_by_speaker) <= speaker_cast.MAX_AUTO_SPEAKER_LABELS
    ):
        raise speaker_cast.AutoCastManualRequired()
    return subdub_multi_speaker_gender_onnx.classify_multi_speaker_genders(
        pcm_path,
        ranges_by_speaker,
        deadline_monotonic=deadline_monotonic,
        stop_requested=stop_requested,
    )


async def _classify_multi_off_event_loop(
    pcm_path: Path,
    ranges_by_speaker: dict[str, list[tuple[float, float]]],
    classify_speakers: Callable[..., dict[str, dict]],
) -> dict[str, dict]:
    if not callable(classify_speakers):
        raise speaker_cast.AutoCastUnavailable()
    classifier_started = time.monotonic()
    classifier_deadline = (
        classifier_started
        + subdub_multi_speaker_gender_onnx.CLASSIFIER_WALL_TIMEOUT_SECONDS
    )
    stop_event = threading.Event()
    worker = asyncio.create_task(
        asyncio.to_thread(
            classify_speakers,
            str(pcm_path),
            ranges_by_speaker,
            deadline_monotonic=classifier_deadline,
            stop_requested=stop_event.is_set,
        )
    )
    remaining_seconds = max(0.0, classifier_deadline - time.monotonic())
    drain_attempted = False
    try:
        return await asyncio.wait_for(
            asyncio.shield(worker),
            remaining_seconds,
        )
    except (asyncio.TimeoutError, TimeoutError) as exc:
        stop_event.set()
        await auto_speaker._drain_worker_bounded(worker)
        drain_attempted = True
        raise speaker_cast.AutoCastManualRequired() from exc
    except asyncio.CancelledError:
        stop_event.set()
        await auto_speaker._drain_worker_bounded(worker)
        drain_attempted = True
        raise
    finally:
        if not worker.done() and not drain_attempted:
            stop_event.set()
            await auto_speaker._drain_worker_bounded(worker)


async def _run_multi_speaker_preflight(
    state: Mapping[str, object],
    *,
    prepare_subtitles: Callable[..., Any],
    post_prepare_gate: Callable[[dict, Mapping[str, object]], Any],
    extract_pcm: Callable[..., Any],
    classify_speakers: Callable[..., dict[str, dict]],
) -> dict[str, Any]:
    current = state if isinstance(state, Mapping) else {}
    pcm_path: Path | None = None
    try:
        if not is_auto_multi_speaker_state(current):
            raise speaker_cast.AutoCastUnavailable()
        prepared = await auto_speaker._maybe_await(
            prepare_subtitles(current, require_auto_cast=True)
        )
        gate_result = await auto_speaker._maybe_await(
            post_prepare_gate(prepared, current)
        )
        if not auto_speaker._gate_continues(gate_result):
            return gate_result

        labels, ranges_by_speaker = auto_speaker._validated_classifier_inputs(
            prepared
        )
        extracted = await auto_speaker._maybe_await(
            extract_pcm(
                prepared,
                current,
                channels=subdub_two_speaker_gender_onnx.PCM_CHANNELS,
                sample_rate=subdub_two_speaker_gender_onnx.PCM_SAMPLE_RATE,
                sample_format="s16le",
            )
        )
        pcm_path = auto_speaker._validated_pcm_path(prepared, extracted)
        classifications = await _classify_multi_off_event_loop(
            pcm_path,
            ranges_by_speaker,
            classify_speakers,
        )
        result = {
            "ok": True,
            "status": auto_speaker.AUTO_SPEAKER_PREFLIGHT_READY,
            "prepared": prepared,
            "speaker_labels": labels,
            "classifications": classifications,
        }
    except asyncio.CancelledError:
        auto_speaker._cleanup_pcm_path(pcm_path)
        raise
    except (
        speaker_cast.AutoCastUnavailable,
        speaker_cast.AutoCastManualRequired,
    ) as exc:
        auto_speaker._cleanup_pcm_path(pcm_path)
        return _multi_manual_required_result(current, exc)
    except Exception:
        auto_speaker._cleanup_pcm_path(pcm_path)
        raise

    if not auto_speaker._cleanup_pcm_path(pcm_path):
        return _multi_manual_required_result(
            current,
            speaker_cast.AutoCastManualRequired(),
        )
    return result


async def _run_isolated_multi_speaker_blackbox(
    *,
    lane_mode: str,
    run_lane_blackbox: Callable[..., Any],
    runner: Callable[..., Any],
    prepare_subtitles: Callable[..., Any],
    resolve_voice_id: Callable[..., Any],
    synthesize_segments: Callable[..., Any],
    post_prepare_gate: Callable[[dict, Mapping[str, object]], Any],
    extract_pcm: Callable[..., Any],
    validated_pools: Mapping[str, object],
    classify_speakers: Callable[..., dict[str, dict]],
    required_pool_capacity: int = 1,
    **payload: Any,
) -> dict[str, Any]:
    """Run the multi-speaker lane without invoking the protected Auto runner."""

    current = payload.get("state")
    if not isinstance(current, Mapping):
        current = {}
    failure_slot: list[Exception] = []

    def record_owned_failure(error: Exception) -> None:
        if not failure_slot:
            failure_slot.append(error)

    try:
        if not callable(run_lane_blackbox) or not callable(runner):
            raise speaker_cast.AutoCastUnavailable()
        if not callable(prepare_subtitles) or not callable(resolve_voice_id):
            raise speaker_cast.AutoCastUnavailable()
        if not callable(synthesize_segments) or not callable(classify_speakers):
            raise speaker_cast.AutoCastUnavailable()
        if (
            type(required_pool_capacity) is not int
            or not 1 <= required_pool_capacity <= speaker_cast.MAX_AUTO_SPEAKER_LABELS
        ):
            raise speaker_cast.AutoCastUnavailable()
        validated_pools = speaker_cast._validated_voice_pools(validated_pools)
        if any(
            len(validated_pools[register]) < required_pool_capacity
            for register in ("low", "high")
        ):
            raise speaker_cast.AutoCastManualRequired()

        preflight = await _run_multi_speaker_preflight(
            current,
            prepare_subtitles=prepare_subtitles,
            post_prepare_gate=post_prepare_gate,
            extract_pcm=extract_pcm,
            classify_speakers=classify_speakers,
        )
        if not isinstance(preflight, Mapping):
            raise speaker_cast.AutoCastUnavailable()
        if not (
            preflight.get("ok") is True
            and preflight.get("status")
            == auto_speaker.AUTO_SPEAKER_PREFLIGHT_READY
        ):
            return dict(preflight)

        prepared = preflight.get("prepared")
        speaker_labels = preflight.get("speaker_labels")
        classifications = preflight.get("classifications")
        if (
            not isinstance(prepared, dict)
            or not isinstance(speaker_labels, list)
            or not isinstance(classifications, dict)
        ):
            raise speaker_cast.AutoCastUnavailable()
        source_segments = prepared.get("source_segments")
        if not isinstance(source_segments, list):
            raise speaker_cast.AutoCastUnavailable()
        source_speaker_order = speaker_cast.ordered_auto_speaker_labels(
            source_segments
        )
        if source_speaker_order != speaker_labels:
            raise speaker_cast.AutoCastUnavailable()
        assignment_seed = auto_speaker._nested_receipt_value(
            prepared,
            "speaker_sidecar_sha256",
        )
        casts = speaker_cast.assign_stable_voices(
            classifications,
            speaker_order=speaker_labels,
            validated_pools=validated_pools,
            assignment_seed=assignment_seed,
        )
        annotated_prepared, assignments = (
            auto_speaker._annotate_prepared_assignments(prepared, casts)
        )
    except asyncio.CancelledError:
        raise
    except (
        speaker_cast.AutoCastUnavailable,
        speaker_cast.AutoCastManualRequired,
    ) as exc:
        return _multi_manual_required_result(current, exc)

    expected_selected_signature: tuple[
        tuple[str, float, float, str], ...
    ] | None = None

    async def already_prepared(_state: dict) -> dict[str, Any]:
        return annotated_prepared

    def multi_resolve_voice_id(
        _user_id: int | str,
        pipeline_state: dict,
    ) -> str:
        nonlocal expected_selected_signature
        try:
            selected = auto_speaker._validated_policy_segments(
                pipeline_state,
                annotated_prepared,
                assignments,
            )
            expected_selected_signature = auto_speaker._selected_voice_signature(
                selected
            )
            return expected_selected_signature[0][3]
        except (
            speaker_cast.AutoCastUnavailable,
            speaker_cast.AutoCastManualRequired,
        ) as exc:
            record_owned_failure(exc)
            raise

    async def multi_synthesize_segments(
        segments: list[dict],
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            if expected_selected_signature is None:
                raise speaker_cast.AutoCastUnavailable()
            selected = auto_speaker._validated_assigned_segments(
                segments,
                assignments,
            )
            actual_signature = auto_speaker._selected_voice_signature(selected)
            if actual_signature != expected_selected_signature:
                raise speaker_cast.AutoCastUnavailable()
            compatibility_voice = kwargs.get("voice_id")
            if compatibility_voice != expected_selected_signature[0][3]:
                raise speaker_cast.AutoCastManualRequired()

            chunks: list[dict[str, Any]] = []
            provider_labels: list[str] = []
            scalar_result_count = 0
            for cue in selected:
                scalar_kwargs = dict(kwargs)
                scalar_kwargs["voice_id"] = cue["tts_voice_id"]
                scalar_result = await auto_speaker._maybe_await(
                    synthesize_segments([cue], *args, **scalar_kwargs)
                )
                scalar_chunks, provider_label = (
                    auto_speaker._validated_scalar_result(scalar_result, cue)
                )
                chunks.extend(scalar_chunks)
                provider_labels.append(provider_label)
                scalar_result_count += 1
            if scalar_result_count != len(selected):
                raise speaker_cast.AutoCastUnavailable()
            return {
                "chunks": chunks,
                "provider": auto_speaker._aggregate_provider_labels(
                    provider_labels
                ),
            }
        except (
            speaker_cast.AutoCastUnavailable,
            speaker_cast.AutoCastManualRequired,
        ) as exc:
            record_owned_failure(exc)
            raise

    lane_payload = dict(payload)
    lane_payload.update(
        {
            "prepare_subtitles": already_prepared,
            "resolve_voice_id": multi_resolve_voice_id,
            "synthesize_segments": multi_synthesize_segments,
        }
    )
    try:
        result = await auto_speaker._maybe_await(
            run_lane_blackbox(
                lane_mode=lane_mode,
                runner=runner,
                **lane_payload,
            )
        )
    except asyncio.CancelledError:
        raise
    except (
        speaker_cast.AutoCastUnavailable,
        speaker_cast.AutoCastManualRequired,
    ) as exc:
        return _multi_manual_required_result(
            current,
            failure_slot[0] if failure_slot else exc,
        )
    except Exception:
        if failure_slot:
            return _multi_manual_required_result(
                current,
                failure_slot[0],
            )
        raise
    if failure_slot:
        return _multi_manual_required_result(current, failure_slot[0])
    if not isinstance(result, dict):
        return _multi_manual_required_result(
            current,
            speaker_cast.AutoCastUnavailable(),
        )
    return result


async def run_auto_multi_speaker_blackbox(
    *,
    extract_pcm: Callable[..., Any],
    state: Mapping[str, object],
    **payload: Any,
) -> dict[str, Any]:
    current = state if isinstance(state, Mapping) else {}
    if not is_auto_multi_speaker_state(current) or not callable(extract_pcm):
        return {
            "ok": False,
            "status": speaker_cast.AUTO_CAST_MANUAL_REQUIRED,
            "reason": speaker_cast.AUTO_CAST_MANUAL_REQUIRED,
            "lane_mode": str(current.get("mode") or current.get("lane_mode") or ""),
            "public_copy_key": "voice_auto_manual_required",
        }

    cached_pcm_path: Path | None = None

    async def extract_filtered_pcm(
        prepared: dict,
        prepared_state: dict,
        **extract_kwargs: Any,
    ) -> Any:
        return await auto_speaker._maybe_await(
            extract_pcm(
                prepared,
                prepared_state,
                **extract_kwargs,
            )
        )

    async def extract_multi_pcm(
        prepared: dict,
        prepared_state: dict,
        **extract_kwargs: Any,
    ) -> Any:
        nonlocal cached_pcm_path
        if cached_pcm_path is not None and cached_pcm_path.is_file():
            target = cached_pcm_path
            cached_pcm_path = None
            return str(target)
        return await extract_filtered_pcm(
            prepared,
            prepared_state,
            **extract_kwargs,
        )

    lane_payload = dict(payload)
    lane_payload.pop("rediarize_underclustered", None)
    base_prepare = lane_payload.get("prepare_subtitles")

    async def prepare_multi_subtitles(*args: Any, **kwargs: Any) -> Any:
        prepared = await auto_speaker._maybe_await(
            base_prepare(*args, **kwargs)
        )
        if not isinstance(prepared, dict):
            return prepared
        labels, _ranges = auto_speaker._validated_classifier_inputs(
            prepared
        )
        prepared_state = auto_speaker._prepared_state(prepared)
        acoustic_evidence = bounded_multi_acoustic_evidence(prepared_state)
        if (
            not acoustic_evidence
            or acoustic_evidence["multi_acoustic_speaker_count"] != len(labels)
        ):
            raise speaker_cast.AutoCastManualRequired()
        if isinstance(current, dict):
            current.update(acoustic_evidence)
        return prepared

    observed_casts: dict[str, str] = {}
    base_synthesize = lane_payload.get("synthesize_segments")
    if callable(base_prepare):
        lane_payload["prepare_subtitles"] = prepare_multi_subtitles
    if callable(base_synthesize):
        async def synthesize_multi_segments(
            segments: list[dict],
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            if not isinstance(segments, list) or not segments:
                raise speaker_cast.AutoCastManualRequired()
            voice_id = kwargs.get("voice_id")
            if type(voice_id) is not str or not voice_id:
                raise speaker_cast.AutoCastManualRequired()
            pending_casts: dict[str, str] = {}
            for raw_segment in segments:
                if not isinstance(raw_segment, Mapping):
                    raise speaker_cast.AutoCastManualRequired()
                speaker_id = raw_segment.get("speaker_id")
                segment_voice_id = raw_segment.get("tts_voice_id")
                if (
                    type(speaker_id) is not str
                    or not speaker_id
                    or type(segment_voice_id) is not str
                    or not segment_voice_id
                    or segment_voice_id != voice_id
                    or observed_casts.get(speaker_id, voice_id) != voice_id
                ):
                    raise speaker_cast.AutoCastManualRequired()
                pending_casts[speaker_id] = voice_id
            synthesized = await auto_speaker._maybe_await(
                base_synthesize(segments, *args, **kwargs)
            )
            observed_casts.update(pending_casts)
            return synthesized

        lane_payload["synthesize_segments"] = synthesize_multi_segments

    try:
        result = await _run_isolated_multi_speaker_blackbox(
            extract_pcm=extract_multi_pcm,
            classify_speakers=classify_multi_speaker_registers,
            state=current,
            **lane_payload,
        )
    except (speaker_cast.AutoCastUnavailable, speaker_cast.AutoCastManualRequired) as exc:
        return _multi_manual_required_result(current, exc)
    finally:
        if cached_pcm_path is not None:
            auto_speaker._cleanup_pcm_path(cached_pcm_path)
    result_state = result.get("state") if isinstance(result, dict) else None
    if (
        isinstance(result, dict)
        and result.get("ok") is True
        and isinstance(result_state, Mapping)
    ):
        proof_fields: dict[str, object] = {}
        if callable(base_synthesize):
            speaker_count = len(observed_casts)
            distinct_voice_count = len(set(observed_casts.values()))
            if (
                not 3 <= speaker_count <= speaker_cast.MAX_AUTO_SPEAKER_LABELS
                or distinct_voice_count != speaker_count
            ):
                return _multi_manual_required_result(
                    current,
                    speaker_cast.AutoCastManualRequired(),
                )
            cast_payload = json.dumps(
                sorted(observed_casts.items()),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            proof_fields = {
                "auto_detected_speaker_count": speaker_count,
                "auto_distinct_voice_count": distinct_voice_count,
                "auto_multi_voice_verified": True,
                "auto_multi_cast_sha256": hashlib.sha256(
                    cast_payload
                ).hexdigest(),
            }
        exact_fields = {
            key: value
            for key, value in current.items()
            if isinstance(key, str) and key.startswith("auto_exact_")
        }
        if proof_fields or exact_fields:
            result = {
                **result,
                "state": {
                    **dict(result_state),
                    **exact_fields,
                    **proof_fields,
                },
            }
    return result
