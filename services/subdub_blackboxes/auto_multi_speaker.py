"""Multi-speaker acoustic profile adapter for the proven Auto SubDub lane."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Callable, Mapping
import hashlib
import json
import math
from typing import Any

from services import subdub_speaker_cast as speaker_cast

from . import auto_speaker


AUTO_MULTI_SPEAKER_LANE = "multi"
MULTI_PCM_AUDIO_FILTER = "highpass=f=70,lowpass=f=320,afftdn=nr=6:nf=-50"
_MULTI_WINDOW_HOP_SECONDS = 0.02
_MULTI_MAX_ACCEPTED_WINDOWS = 12


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
    if selected_count == 1:
        selected_indexes = [total_candidates // 2]
    else:
        selected_indexes = [
            round(index * (total_candidates - 1) / (selected_count - 1))
            for index in range(selected_count)
        ]

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
                        allow_single_pitch_frame=True,
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
    try:
        return speaker_cast.classify_speaker_registers(
            pcm_path,
            ranges_by_speaker,
            deadline_monotonic=deadline_monotonic,
            stop_requested=stop_requested,
            allow_single_pitch_frame=True,
        )
    except speaker_cast.AutoCastManualRequired:
        return _classify_dense_multi_speaker_registers(
            pcm_path,
            ranges_by_speaker,
            deadline_monotonic=deadline_monotonic,
            stop_requested=stop_requested,
        )


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

    async def extract_multi_pcm(
        prepared: dict,
        prepared_state: dict,
        **extract_kwargs: Any,
    ) -> Any:
        return await auto_speaker._maybe_await(
            extract_pcm(
                prepared,
                prepared_state,
                **extract_kwargs,
                audio_filter=MULTI_PCM_AUDIO_FILTER,
            )
        )

    observed_casts: dict[str, str] = {}
    base_synthesize = payload.get("synthesize_segments")
    lane_payload = dict(payload)
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
        result = await auto_speaker.run_auto_speaker_blackbox(
            extract_pcm=extract_multi_pcm,
            classify_speakers=classify_multi_speaker_registers,
            state=current,
            **lane_payload,
        )
    except (speaker_cast.AutoCastUnavailable, speaker_cast.AutoCastManualRequired) as exc:
        return auto_speaker._manual_required_result(current, exc)
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
                return auto_speaker._manual_required_result(
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
