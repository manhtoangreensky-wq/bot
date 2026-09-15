"""Multi-speaker V2 blackbox engine with tolerant cue parity and robust TTS verification."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
import hashlib
import json
import math
from pathlib import Path
import shutil
from typing import Any

from services import subdub_media_preflight
from services import subdub_speaker_cast as speaker_cast
from services.subdub_blackboxes import auto_multi_speaker
from services.subdub_blackboxes import auto_speaker

AUTO_MULTI_SPEAKER_LANE = auto_multi_speaker.AUTO_MULTI_SPEAKER_LANE
MULTI_ACOUSTIC_STATE_FIELDS = auto_multi_speaker.MULTI_ACOUSTIC_STATE_FIELDS
MULTI_V2_CUE_ROUNDING_TOLERANCE_SECONDS = 0.001

bounded_multi_acoustic_evidence = auto_multi_speaker.bounded_multi_acoustic_evidence
acoustic_sidecar_evidence = auto_multi_speaker.acoustic_sidecar_evidence
validate_auto_multi_output_geometry = auto_multi_speaker.validate_auto_multi_output_geometry
probe_auto_multi_video_bytes_off_event_loop = auto_multi_speaker.probe_auto_multi_video_bytes_off_event_loop
classify_multi_speaker_registers = auto_multi_speaker.classify_multi_speaker_registers
acoustic_register_classifications = auto_multi_speaker.acoustic_register_classifications

AUTO_MULTI_V2_FAILURE_STAGES = frozenset({
    "entry_validation",
    "voice_pool_capacity",
    "prepare_subtitles",
    "post_prepare_gate",
    "classifier_inputs",
    "speaker_classification",
    "voice_assignment",
    "cue_assignment",
    "voice_policy",
    "tts_scalar",
    "lane_runner",
    "output_validation",
    "unknown",
})

AUTO_MULTI_V2_FAILURE_CODES = frozenset({
    "auto_cast_unavailable",
    "auto_cast_manual_required",
    "voice_pool_capacity_insufficient",
    "scalar_audio_missing",
})


def _bounded_auto_multi_v2_failure(
    error: Exception,
    *,
    stage: str,
    code: str = "",
) -> dict[str, str]:
    bounded_stage = str(stage or "unknown").strip().lower()
    if bounded_stage not in AUTO_MULTI_V2_FAILURE_STAGES:
        bounded_stage = "unknown"
    bounded_code = str(code or "").strip().lower()
    if not bounded_code:
        bounded_code = (
            "auto_cast_unavailable"
            if isinstance(error, speaker_cast.AutoCastUnavailable)
            else "auto_cast_manual_required"
        )
    if bounded_code not in AUTO_MULTI_V2_FAILURE_CODES:
        bounded_code = "auto_cast_manual_required"
    return {
        "auto_multi_failure_stage": bounded_stage,
        "auto_multi_failure_code": bounded_code,
    }


def _multi_v2_manual_required_result(
    state: Mapping[str, object],
    error: Exception,
    *,
    stage: str = "unknown",
    code: str = "",
) -> dict[str, Any]:
    evidence = auto_multi_speaker._multi_diarization_debug_fields(state)
    result = auto_speaker._manual_required_result(state, error)
    bounded_failure = _bounded_auto_multi_v2_failure(
        error,
        stage=stage,
        code=code,
    )
    result = {
        **result,
        "reason": speaker_cast.AUTO_CAST_MANUAL_REQUIRED,
        **bounded_failure,
    }
    if not evidence:
        return result
    return {
        **result,
        **evidence,
        "state": {**dict(state), **evidence, **bounded_failure},
    }


def _extract_multi_v2_cue_identity(item: object) -> tuple[str, float, float]:
    if not isinstance(item, Mapping):
        raise speaker_cast.AutoCastUnavailable()
    cue_id = item.get("cue_id")
    start = item.get("start")
    end = item.get("end")
    if (
        type(cue_id) is not str
        or not cue_id
        or cue_id != cue_id.strip()
        or isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, (int, float))
        or not isinstance(end, (int, float))
    ):
        raise speaker_cast.AutoCastUnavailable()
    normalized_start = float(start)
    normalized_end = float(end)
    if (
        not math.isfinite(normalized_start)
        or not math.isfinite(normalized_end)
        or normalized_start < 0.0
        or normalized_end <= normalized_start
    ):
        raise speaker_cast.AutoCastUnavailable()
    return cue_id, normalized_start, normalized_end


def _annotate_multi_v2_prepared_assignments(
    prepared: object,
    casts: Mapping[str, object],
) -> tuple[dict[str, Any], dict[str, tuple[str, str, float, float]]]:
    if not isinstance(prepared, dict) or not isinstance(casts, Mapping) or not casts:
        raise speaker_cast.AutoCastUnavailable()
    raw_source = prepared.get("source_segments")
    raw_output = prepared.get("output_segments")
    if (
        not isinstance(raw_source, list)
        or not raw_source
        or not isinstance(raw_output, list)
        or not raw_output
    ):
        raise speaker_cast.AutoCastUnavailable()

    assignments: dict[str, tuple[str, str, float, float]] = {}
    annotated_source: list[dict[str, Any]] = []
    for raw_segment in raw_source:
        cue_id, start, end = _extract_multi_v2_cue_identity(raw_segment)
        if cue_id in assignments:
            raise speaker_cast.AutoCastUnavailable()
        segment = dict(raw_segment)
        speaker_id = segment.get("speaker_id")
        if type(speaker_id) is not str or not speaker_id or speaker_id != speaker_id.strip():
            raise speaker_cast.AutoCastUnavailable()
        cast = casts.get(speaker_id)
        if not isinstance(cast, Mapping):
            raise speaker_cast.AutoCastManualRequired()
        voice_register = cast.get("voice_register")
        voice_id = cast.get("voice_id")
        if voice_register not in {"low", "high"} or type(voice_id) is not str or not voice_id:
            raise speaker_cast.AutoCastManualRequired()
        assignments[cue_id] = (str(voice_register), str(voice_id), start, end)
        annotated_source.append(
            {
                **segment,
                "voice_register": voice_register,
                "tts_voice_id": voice_id,
            }
        )

    annotated_output: list[dict[str, Any]] = []
    output_cue_ids: set[str] = set()
    for raw_segment in raw_output:
        cue_id, out_start, out_end = _extract_multi_v2_cue_identity(raw_segment)
        if cue_id in output_cue_ids:
            raise speaker_cast.AutoCastUnavailable()
        output_cue_ids.add(cue_id)
        assignment = assignments.get(cue_id)
        if assignment is None:
            raise speaker_cast.AutoCastUnavailable()
        voice_register, voice_id, src_start, src_end = assignment
        if (
            abs(out_start - src_start) > MULTI_V2_CUE_ROUNDING_TOLERANCE_SECONDS
            or abs(out_end - src_end) > MULTI_V2_CUE_ROUNDING_TOLERANCE_SECONDS
        ):
            raise speaker_cast.AutoCastUnavailable()
        annotated_output.append(
            {
                **dict(raw_segment),
                "voice_register": voice_register,
                "tts_voice_id": voice_id,
            }
        )

    if output_cue_ids != set(assignments.keys()):
        raise speaker_cast.AutoCastUnavailable()

    annotated_prepared = {
        **prepared,
        "source_segments": annotated_source,
        "output_segments": annotated_output,
    }
    return annotated_prepared, assignments


def _multi_v2_selected_voice_signature(
    segments: list[dict[str, Any]],
) -> tuple[tuple[str, str], ...]:
    signature: list[tuple[str, str]] = []
    seen: set[str] = set()
    for segment in segments:
        cue_id, _, _ = _extract_multi_v2_cue_identity(segment)
        if cue_id in seen:
            raise speaker_cast.AutoCastUnavailable()
        seen.add(cue_id)
        voice_id = segment.get("tts_voice_id")
        if type(voice_id) is not str or not voice_id:
            raise speaker_cast.AutoCastManualRequired()
        signature.append((cue_id, voice_id))
    if not signature:
        raise speaker_cast.AutoCastManualRequired()
    return tuple(signature)


def _validated_multi_v2_assigned_segments(
    raw_segments: object,
    assignments: Mapping[str, tuple[str, str, float, float]],
) -> list[dict[str, Any]]:
    if not isinstance(raw_segments, list) or not raw_segments:
        raise speaker_cast.AutoCastManualRequired()

    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_segment in raw_segments:
        cue_id, seg_start, seg_end = _extract_multi_v2_cue_identity(raw_segment)
        if cue_id in seen:
            raise speaker_cast.AutoCastUnavailable()
        seen.add(cue_id)
        expected = assignments.get(cue_id)
        if expected is None:
            raise speaker_cast.AutoCastUnavailable()
        expected_register, expected_voice_id, src_start, src_end = expected
        if (
            abs(seg_start - src_start) > MULTI_V2_CUE_ROUNDING_TOLERANCE_SECONDS
            or abs(seg_end - src_end) > MULTI_V2_CUE_ROUNDING_TOLERANCE_SECONDS
        ):
            raise speaker_cast.AutoCastUnavailable()
        voice_register = raw_segment.get("voice_register")
        voice_id = raw_segment.get("tts_voice_id")
        if (
            voice_register != expected_register
            or type(voice_id) is not str
            or not voice_id
            or voice_id != expected_voice_id
        ):
            raise speaker_cast.AutoCastManualRequired()
        selected.append(dict(raw_segment))
    return selected


def _validated_multi_v2_policy_segments(
    pipeline_state: object,
    prepared: dict[str, Any],
    assignments: Mapping[str, tuple[str, str, float, float]],
) -> list[dict[str, Any]]:
    if not isinstance(pipeline_state, dict):
        raise speaker_cast.AutoCastUnavailable()
    policy = auto_speaker.subtitle_dub_product_pipeline.resolve_subdub_dub_audio_policy(
        pipeline_state,
        prepared,
    )
    raw_segments = policy.get("tts_segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise speaker_cast.AutoCastManualRequired()
    return _validated_multi_v2_assigned_segments(raw_segments, assignments)


def is_auto_multi_speaker_v2_state(
    state: Mapping[str, object] | None,
) -> bool:
    return auto_multi_speaker.is_auto_multi_speaker_state(state)


async def _run_isolated_multi_speaker_v2_blackbox(
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
    current = payload.get("state")
    if not isinstance(current, Mapping):
        current = {}
    failure_slot: list[tuple[Exception, str, str]] = []
    failure_stage = "entry_validation"

    def record_owned_failure(
        error: Exception,
        *,
        stage: str,
        code: str = "",
    ) -> None:
        if not failure_slot:
            failure_slot.append((error, stage, code))

    def owned_failure_result(error: Exception) -> dict[str, Any]:
        if failure_slot:
            owned_error, owned_stage, owned_code = failure_slot[0]
            return _multi_v2_manual_required_result(
                current,
                owned_error,
                stage=owned_stage,
                code=owned_code,
            )
        return _multi_v2_manual_required_result(
            current,
            error,
            stage=failure_stage,
        )

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
        failure_stage = "voice_pool_capacity"
        validated_pools = speaker_cast._validated_voice_pools(validated_pools)
        if any(
            len(validated_pools[register]) < required_pool_capacity
            for register in ("low", "high")
        ):
            raise speaker_cast.AutoCastManualRequired()

        failure_stage = "prepare_subtitles"
        preflight = await auto_multi_speaker._run_multi_speaker_preflight(
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
        failure_stage = "voice_assignment"
        casts = speaker_cast.assign_stable_voices(
            classifications,
            speaker_order=speaker_labels,
            validated_pools=validated_pools,
            assignment_seed=assignment_seed,
        )
        failure_stage = "cue_assignment"
        annotated_prepared, assignments = (
            _annotate_multi_v2_prepared_assignments(prepared, casts)
        )
    except asyncio.CancelledError:
        raise
    except (
        speaker_cast.AutoCastUnavailable,
        speaker_cast.AutoCastManualRequired,
    ) as exc:
        return _multi_v2_manual_required_result(
            current,
            exc,
            stage=failure_stage,
        )

    expected_selected_signature: tuple[
        tuple[str, str], ...
    ] | None = None

    async def already_prepared(_state: dict) -> dict[str, Any]:
        return annotated_prepared

    def multi_resolve_voice_id(
        _user_id: int | str,
        pipeline_state: dict,
    ) -> str:
        nonlocal expected_selected_signature
        try:
            selected = _validated_multi_v2_policy_segments(
                pipeline_state,
                annotated_prepared,
                assignments,
            )
            expected_selected_signature = _multi_v2_selected_voice_signature(
                selected
            )
            return expected_selected_signature[0][1]
        except (
            speaker_cast.AutoCastUnavailable,
            speaker_cast.AutoCastManualRequired,
        ) as exc:
            record_owned_failure(exc, stage="voice_policy")
            raise

    async def multi_synthesize_segments(
        segments: list[dict],
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            if expected_selected_signature is None:
                raise speaker_cast.AutoCastUnavailable()
            selected = _validated_multi_v2_assigned_segments(
                segments,
                assignments,
            )
            actual_signature = _multi_v2_selected_voice_signature(selected)
            if actual_signature != expected_selected_signature:
                raise speaker_cast.AutoCastUnavailable()
            compatibility_voice = kwargs.get("voice_id")
            if compatibility_voice != expected_selected_signature[0][1]:
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
                try:
                    scalar_chunks, provider_label = (
                        auto_speaker._validated_scalar_result(scalar_result, cue)
                    )
                except (
                    speaker_cast.AutoCastUnavailable,
                    speaker_cast.AutoCastManualRequired,
                ) as exc:
                    raw_chunks = (
                        scalar_result.get("chunks")
                        if isinstance(scalar_result, Mapping)
                        else None
                    )
                    scalar_audio_missing = (
                        isinstance(raw_chunks, list)
                        and bool(raw_chunks)
                        and any(
                            not isinstance(chunk, Mapping)
                            or not isinstance(
                                chunk.get("audio_bytes"),
                                (bytes, bytearray),
                            )
                            or not chunk.get("audio_bytes")
                            for chunk in raw_chunks
                        )
                    )
                    record_owned_failure(
                        exc,
                        stage="tts_scalar",
                        code=(
                            "scalar_audio_missing"
                            if scalar_audio_missing
                            else ""
                        ),
                    )
                    raise
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
            record_owned_failure(exc, stage="tts_scalar")
            raise

    lane_payload = dict(payload)
    lane_payload.update(
        {
            "prepare_subtitles": already_prepared,
            "resolve_voice_id": multi_resolve_voice_id,
            "synthesize_segments": multi_synthesize_segments,
        }
    )
    failure_stage = "lane_runner"
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
        return owned_failure_result(exc)
    except Exception:
        if failure_slot:
            return owned_failure_result(failure_slot[0][0])
        raise
    if failure_slot:
        return owned_failure_result(failure_slot[0][0])
    if not isinstance(result, dict):
        return _multi_v2_manual_required_result(
            current,
            speaker_cast.AutoCastUnavailable(),
            stage="output_validation",
        )
    return result


async def run_auto_multi_speaker_v2_blackbox(
    *,
    extract_pcm: Callable[..., Any],
    state: Mapping[str, object],
    **payload: Any,
) -> dict[str, Any]:
    current = state if isinstance(state, Mapping) else {}
    if not is_auto_multi_speaker_v2_state(current) or not callable(extract_pcm):
        return {
            "ok": False,
            "status": speaker_cast.AUTO_CAST_MANUAL_REQUIRED,
            "reason": speaker_cast.AUTO_CAST_MANUAL_REQUIRED,
            "lane_mode": str(current.get("mode") or current.get("lane_mode") or ""),
            "public_copy_key": "voice_auto_manual_required",
        }
    if not callable(payload.get("probe_video")) and not shutil.which("ffprobe"):
        return _multi_v2_manual_required_result(
            current,
            speaker_cast.AutoCastUnavailable(),
            stage="entry_validation",
        )

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
    source_video_probe = lane_payload.pop("source_video_probe", None)
    probe_video = lane_payload.pop("probe_video", None)
    base_prepare = lane_payload.get("prepare_subtitles")
    acoustic_speaker_ids: set[str] = set()

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
        acoustic_speaker_ids.clear()
        acoustic_speaker_ids.update(labels)
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
        result = await _run_isolated_multi_speaker_v2_blackbox(
            extract_pcm=extract_multi_pcm,
            classify_speakers=classify_multi_speaker_registers,
            state=current,
            **lane_payload,
        )
    except (speaker_cast.AutoCastUnavailable, speaker_cast.AutoCastManualRequired) as exc:
        return _multi_v2_manual_required_result(current, exc, stage="lane_runner")
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
        video_output = result.get("video_output")
        if video_output:
            async def geometry_probe(payload: bytes) -> object:
                if callable(probe_video):
                    return await auto_speaker._maybe_await(probe_video(payload))
                return await probe_auto_multi_video_bytes_off_event_loop(payload)

            try:
                if not isinstance(source_video_probe, Mapping):
                    source_video_probe = await geometry_probe(
                        bytes(result.get("source_bytes") or b"")
                    )
                output_probe = await geometry_probe(bytes(video_output))
            except asyncio.CancelledError:
                raise
            except Exception:
                return _multi_v2_manual_required_result(
                    current,
                    speaker_cast.AutoCastManualRequired(),
                    stage="output_validation",
                )
            geometry = validate_auto_multi_output_geometry(
                source_video_probe,
                output_probe,
            )
            if geometry.get("ok") is not True:
                return _multi_v2_manual_required_result(
                    current,
                    speaker_cast.AutoCastManualRequired(),
                    stage="output_validation",
                )
            proof_fields.update(
                {
                    "auto_multi_geometry_verified": True,
                    "auto_multi_source_display_width": geometry[
                        "source_display_width"
                    ],
                    "auto_multi_source_display_height": geometry[
                        "source_display_height"
                    ],
                    "auto_multi_output_display_width": geometry[
                        "output_display_width"
                    ],
                    "auto_multi_output_display_height": geometry[
                        "output_display_height"
                    ],
                    "auto_multi_output_rotation": geometry[
                        "output_rotation"
                    ],
                }
            )
        if callable(base_synthesize):
            speaker_count = len(observed_casts)
            distinct_voice_count = len(set(observed_casts.values()))
            if (
                not 3 <= speaker_count <= speaker_cast.MAX_AUTO_SPEAKER_LABELS
                or distinct_voice_count != speaker_count
                or set(observed_casts) != acoustic_speaker_ids
            ):
                return _multi_v2_manual_required_result(
                    current,
                    speaker_cast.AutoCastManualRequired(),
                    stage="output_validation",
                )
            cast_payload = json.dumps(
                sorted(observed_casts.items()),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            proof_fields.update(
                {
                    "auto_detected_speaker_count": speaker_count,
                    "auto_distinct_voice_count": distinct_voice_count,
                    "auto_multi_voice_verified": True,
                    "auto_multi_attribution_verified": True,
                    "auto_multi_cast_sha256": hashlib.sha256(
                        cast_payload
                    ).hexdigest(),
                    "auto_multi_v2_engine": True,
                }
            )
        exact_fields = {
            key: value
            for key, value in current.items()
            if isinstance(key, str) and key.startswith("auto_exact_")
        }
        acoustic_fields = bounded_multi_acoustic_evidence(current)
        if proof_fields or exact_fields:
            result = {
                **result,
                "state": {
                    **dict(result_state),
                    **acoustic_fields,
                    **exact_fields,
                    **proof_fields,
                },
            }
    return result
