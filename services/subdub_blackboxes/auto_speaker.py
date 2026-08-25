"""Bounded Auto speaker preflight and per-cue voice adapter for SubDub."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import math
import os
import shutil
import subprocess
import threading
import time
import unicodedata
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from services import subdub_speaker_cast as speaker_cast
from services import subtitle_dub_product_pipeline


AUTO_SPEAKER_PREFLIGHT_READY = "AUTO_SPEAKER_PREFLIGHT_READY"
AUTO_SPEAKER_PCM_AUDIO_FILTER = (
    "highpass=f=70,lowpass=f=320,afftdn=nr=6:nf=-50"
)

_SUBTITLE_SCRIPT_CHARSET = {
    "japanese": "3042",
    "chinese": "4e2d",
    "korean": "ac00",
    "thai": "0e01",
    "arabic": "0627",
    "devanagari": "0915",
    "cyrillic": "0416",
}


def is_auto_speaker_state(state: Mapping[str, object] | None) -> bool:
    """Return true only for the repository-wide exact Auto state pair."""

    current = state or {}
    return (
        current.get("voice_kind") == "auto_speaker_gender"
        and current.get("voice_selection_mode") == "auto_speaker"
    )


def _font_path_supports_script(path: str, script: str) -> bool:
    font_path = os.path.abspath(os.path.expandvars(os.path.expanduser(str(path or ""))))
    if not font_path or not os.path.isfile(font_path):
        return False
    charset = str(_SUBTITLE_SCRIPT_CHARSET.get(str(script or "").strip().lower()) or "")
    if not charset:
        return True
    fc_list = shutil.which("fc-list")
    if not fc_list:
        return False
    try:
        proc = subprocess.run(
            [fc_list, "-f", "%{file}\\n", f":charset={charset}"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return False
    supported = {
        os.path.normcase(os.path.realpath(item.strip()))
        for item in str(proc.stdout or "").splitlines()
        if item.strip()
    }
    return proc.returncode == 0 and os.path.normcase(os.path.realpath(font_path)) in supported


def guard_subtitle_font(style: Mapping[str, object] | None, *, script: str) -> dict:
    current = dict(style or {})
    normalized_script = str(script or "latin").strip().lower()
    if normalized_script == "latin" or _font_path_supports_script(
        str(current.get("subtitle_font_path") or ""),
        normalized_script,
    ):
        return current
    current.update(
        {
            "subtitle_font_resolution_ok": False,
            "subtitle_font_blocker": f"subtitle_font_missing:{normalized_script}",
            "subtitle_font_script": normalized_script,
            "subtitle_font_fallback_reason": "resolved_font_missing_required_script",
        }
    )
    return current


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _gate_continues(gate_result: Any) -> bool:
    if gate_result is None or gate_result is True:
        return True
    if not isinstance(gate_result, Mapping):
        return False
    if gate_result.get("continue") is True:
        return True
    return bool(
        gate_result.get("ok") is True
        and str(gate_result.get("status") or "").strip().upper()
        in {"CONTINUE", "AUTO_PREFLIGHT_CONTINUE"}
    )


def _manual_required_result(
    state: Mapping[str, object],
    error: Exception,
) -> dict[str, Any]:
    return {
        "ok": False,
        "status": speaker_cast.AUTO_CAST_MANUAL_REQUIRED,
        "reason": str(error),
        "lane_mode": str(state.get("mode") or state.get("lane_mode") or ""),
        "public_copy_key": "voice_auto_manual_required",
    }


def _prepared_state(prepared: dict) -> Mapping[str, object]:
    nested = prepared.get("state")
    if nested is None:
        return {}
    if not isinstance(nested, Mapping):
        raise speaker_cast.AutoCastUnavailable()
    return nested


def _nested_receipt_value(prepared: dict, field: str) -> str:
    nested = _prepared_state(prepared)
    top_level = str(prepared.get(field) or "").strip()
    nested_value = str(nested.get(field) or "").strip()
    if top_level and nested_value and top_level != nested_value:
        raise speaker_cast.AutoCastUnavailable()
    return nested_value or top_level


def _explicit_prepared_sha256(prepared: dict, fields: tuple[str, ...]) -> str:
    hashes: list[str] = []
    for field in fields:
        raw = prepared.get(field)
        if raw in (None, ""):
            continue
        normalized = str(raw).strip().lower()
        if (
            len(normalized) != 64
            or any(character not in "0123456789abcdef" for character in normalized)
        ):
            raise speaker_cast.AutoCastUnavailable()
        if normalized not in hashes:
            hashes.append(normalized)
    if len(hashes) > 1:
        raise speaker_cast.AutoCastUnavailable()
    return hashes[0] if hashes else ""


def _prepared_media_sha256(prepared: dict) -> str:
    explicit = _explicit_prepared_sha256(
        prepared,
        ("media_sha256", "source_media_sha256", "source_sha256"),
    )
    source_bytes = prepared.get("source_bytes")
    derived = ""
    if source_bytes is not None:
        if not isinstance(source_bytes, (bytes, bytearray)) or not source_bytes:
            raise speaker_cast.AutoCastUnavailable()
        derived = hashlib.sha256(bytes(source_bytes)).hexdigest()
    if explicit and derived and explicit != derived:
        raise speaker_cast.AutoCastUnavailable()
    if explicit or derived:
        return explicit or derived
    raise speaker_cast.AutoCastUnavailable()


def _source_subtitle_sha256(source_subtitle: str) -> str:
    normalized = unicodedata.normalize("NFC", str(source_subtitle or ""))
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8", errors="strict")).hexdigest()


def _prepared_subtitle_sha256(prepared: dict) -> str:
    explicit = _explicit_prepared_sha256(
        prepared,
        ("subtitle_sha256", "selected_subtitle_sha256"),
    )
    source_subtitle = prepared.get("source_subtitle")
    derived = ""
    if source_subtitle is not None:
        if not isinstance(source_subtitle, str) or not source_subtitle.strip():
            raise speaker_cast.AutoCastUnavailable()
        derived = _source_subtitle_sha256(source_subtitle)
    if explicit and derived and explicit != derived:
        raise speaker_cast.AutoCastUnavailable()
    if explicit or derived:
        return explicit or derived
    raise speaker_cast.AutoCastUnavailable()


def _validated_classifier_inputs(prepared: object) -> tuple[list[str], dict[str, list[tuple[float, float]]]]:
    if not isinstance(prepared, dict):
        raise speaker_cast.AutoCastUnavailable()
    source_segments = prepared.get("source_segments")
    if not isinstance(source_segments, list) or not source_segments:
        raise speaker_cast.AutoCastUnavailable()

    workspace = _nested_receipt_value(prepared, "_pipeline_workspace")
    if not workspace:
        workspace = _nested_receipt_value(prepared, "workspace")
    sidecar_path = _nested_receipt_value(prepared, "speaker_sidecar_path")
    sidecar_sha256 = _nested_receipt_value(prepared, "speaker_sidecar_sha256")
    media_sha256 = _prepared_media_sha256(prepared)
    subtitle_sha256 = _prepared_subtitle_sha256(prepared)
    sidecar = speaker_cast.load_sidecar(
        sidecar_path,
        expected_sha256=sidecar_sha256,
        workspace=workspace,
    )
    joined = speaker_cast.require_matching_sidecar(
        sidecar,
        source_segments,
        media_sha256=media_sha256,
        subtitle_sha256=subtitle_sha256,
    )
    labels = speaker_cast.ordered_auto_speaker_labels(joined)
    if not labels:
        raise speaker_cast.AutoCastUnavailable()

    ranges_by_speaker: dict[str, list[tuple[float, float]]] = {
        speaker_id: [] for speaker_id in labels
    }
    for cue in joined:
        speaker_id = str(cue.get("speaker_id") or "")
        try:
            start_ms = int(cue.get("start_ms"))
            end_ms = int(cue.get("end_ms"))
        except (TypeError, ValueError, OverflowError) as exc:
            raise speaker_cast.AutoCastUnavailable() from exc
        if speaker_id not in ranges_by_speaker or start_ms < 0 or end_ms <= start_ms:
            raise speaker_cast.AutoCastUnavailable()
        ranges_by_speaker[speaker_id].append((start_ms / 1000.0, end_ms / 1000.0))
    return labels, ranges_by_speaker


def _validated_pcm_path(prepared: dict, extracted: object) -> Path:
    if isinstance(extracted, Mapping):
        raw_path = extracted.get("pcm_path") or extracted.get("path")
    else:
        raw_path = extracted
    workspace = _nested_receipt_value(prepared, "_pipeline_workspace")
    if not workspace:
        workspace = _nested_receipt_value(prepared, "workspace")
    target = speaker_cast._workspace_file(workspace, str(raw_path or ""))
    if not target.is_file():
        raise speaker_cast.AutoCastUnavailable()
    return target


async def _drain_worker(worker: asyncio.Task) -> None:
    while not worker.done():
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            continue
        except Exception:
            break
    if worker.done():
        try:
            worker.result()
        except (asyncio.CancelledError, Exception):
            pass


async def _classify_off_event_loop(
    pcm_path: Path,
    ranges_by_speaker: dict[str, list[tuple[float, float]]],
    classify_speakers: Callable[..., dict[str, dict]] | None = None,
) -> dict[str, dict]:
    classifier = classify_speakers or speaker_cast.classify_speaker_registers
    if not callable(classifier):
        raise speaker_cast.AutoCastUnavailable()
    classifier_started = time.monotonic()
    classifier_deadline = (
        classifier_started + speaker_cast.CLASSIFIER_WALL_TIMEOUT_SECONDS
    )
    stop_event = threading.Event()
    classifier_kwargs = {
        "deadline_monotonic": classifier_deadline,
        "stop_requested": stop_event.is_set,
    }
    if classify_speakers is None:
        classifier_kwargs["allow_single_pitch_frame"] = True
    worker = asyncio.create_task(
        asyncio.to_thread(
            classifier,
            str(pcm_path),
            ranges_by_speaker,
            **classifier_kwargs,
        )
    )
    remaining_seconds = max(0.0, classifier_deadline - time.monotonic())
    try:
        return await asyncio.wait_for(
            asyncio.shield(worker),
            remaining_seconds,
        )
    except (asyncio.TimeoutError, TimeoutError) as exc:
        stop_event.set()
        await _drain_worker(worker)
        raise speaker_cast.AutoCastManualRequired() from exc
    except asyncio.CancelledError:
        stop_event.set()
        await _drain_worker(worker)
        raise
    finally:
        if not worker.done():
            stop_event.set()
            await _drain_worker(worker)


def _cleanup_pcm_path(pcm_path: Path | None) -> bool:
    if pcm_path is None:
        return True
    try:
        pcm_path.unlink(missing_ok=True)
    except OSError:
        return False
    return True


def _exact_cue_identity(item: object) -> tuple[str, float, float]:
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


def _annotate_prepared_assignments(
    prepared: object,
    casts: Mapping[str, object],
) -> tuple[dict[str, Any], dict[tuple[str, float, float], tuple[str, str]]]:
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

    assignments: dict[tuple[str, float, float], tuple[str, str]] = {}
    annotated_source: list[dict[str, Any]] = []
    for raw_segment in raw_source:
        identity = _exact_cue_identity(raw_segment)
        if identity in assignments:
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
        assignments[identity] = (str(voice_register), voice_id)
        annotated_source.append(
            {
                **segment,
                "voice_register": voice_register,
                "tts_voice_id": voice_id,
            }
        )

    annotated_output: list[dict[str, Any]] = []
    output_identities: set[tuple[str, float, float]] = set()
    for raw_segment in raw_output:
        identity = _exact_cue_identity(raw_segment)
        if identity in output_identities:
            raise speaker_cast.AutoCastUnavailable()
        output_identities.add(identity)
        assignment = assignments.get(identity)
        if assignment is None:
            raise speaker_cast.AutoCastUnavailable()
        voice_register, voice_id = assignment
        annotated_output.append(
            {
                **dict(raw_segment),
                "voice_register": voice_register,
                "tts_voice_id": voice_id,
            }
        )
    if output_identities != set(assignments):
        raise speaker_cast.AutoCastUnavailable()

    annotated = dict(prepared)
    annotated["source_segments"] = annotated_source
    annotated["output_segments"] = annotated_output
    return annotated, assignments


def _validated_policy_segments(
    pipeline_state: object,
    prepared: dict[str, Any],
    assignments: Mapping[tuple[str, float, float], tuple[str, str]],
) -> list[dict[str, Any]]:
    if not isinstance(pipeline_state, dict):
        raise speaker_cast.AutoCastUnavailable()
    policy = subtitle_dub_product_pipeline.resolve_subdub_dub_audio_policy(
        pipeline_state,
        prepared,
    )
    raw_segments = policy.get("tts_segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise speaker_cast.AutoCastManualRequired()

    return _validated_assigned_segments(raw_segments, assignments)


def _validated_assigned_segments(
    raw_segments: object,
    assignments: Mapping[tuple[str, float, float], tuple[str, str]],
) -> list[dict[str, Any]]:
    if not isinstance(raw_segments, list) or not raw_segments:
        raise speaker_cast.AutoCastManualRequired()

    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, float, float]] = set()
    for raw_segment in raw_segments:
        identity = _exact_cue_identity(raw_segment)
        if identity in seen:
            raise speaker_cast.AutoCastUnavailable()
        seen.add(identity)
        expected = assignments.get(identity)
        if expected is None:
            raise speaker_cast.AutoCastUnavailable()
        expected_register, expected_voice_id = expected
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


def _selected_voice_signature(
    segments: list[dict[str, Any]],
) -> tuple[tuple[str, float, float, str], ...]:
    signature: list[tuple[str, float, float, str]] = []
    seen: set[tuple[str, float, float]] = set()
    for segment in segments:
        identity = _exact_cue_identity(segment)
        if identity in seen:
            raise speaker_cast.AutoCastUnavailable()
        seen.add(identity)
        voice_id = segment.get("tts_voice_id")
        if type(voice_id) is not str or not voice_id:
            raise speaker_cast.AutoCastManualRequired()
        signature.append((*identity, voice_id))
    if not signature:
        raise speaker_cast.AutoCastManualRequired()
    return tuple(signature)


def _validated_scalar_result(
    result: object,
    cue: Mapping[str, object],
) -> tuple[list[dict[str, Any]], str]:
    if not isinstance(result, Mapping):
        raise speaker_cast.AutoCastUnavailable()
    raw_chunks = result.get("chunks")
    if not isinstance(raw_chunks, list) or not raw_chunks:
        raise speaker_cast.AutoCastUnavailable()
    cue_identity = _exact_cue_identity(cue)
    chunks: list[dict[str, Any]] = []
    previous_start = cue_identity[1]
    for raw_chunk in raw_chunks:
        if not isinstance(raw_chunk, Mapping):
            raise speaker_cast.AutoCastUnavailable()
        chunk = dict(raw_chunk)
        chunk_start = chunk.get("start")
        chunk_end = chunk.get("end")
        if (
            isinstance(chunk_start, bool)
            or isinstance(chunk_end, bool)
            or not isinstance(chunk_start, (int, float))
            or not isinstance(chunk_end, (int, float))
        ):
            raise speaker_cast.AutoCastUnavailable()
        normalized_start = float(chunk_start)
        normalized_end = float(chunk_end)
        if (
            not math.isfinite(normalized_start)
            or not math.isfinite(normalized_end)
            or normalized_start < cue_identity[1]
            or normalized_end > cue_identity[2]
            or normalized_end <= normalized_start
            or normalized_start < previous_start
        ):
            raise speaker_cast.AutoCastUnavailable()
        audio_bytes = chunk.get("audio_bytes")
        if not isinstance(audio_bytes, (bytes, bytearray)) or not audio_bytes:
            raise speaker_cast.AutoCastUnavailable()
        chunks.append(chunk)
        previous_start = normalized_start
    provider = result.get("provider")
    if provider in (None, ""):
        provider_label = ""
    elif type(provider) is str and provider == provider.strip() and len(provider) <= 160:
        provider_label = provider
    else:
        raise speaker_cast.AutoCastUnavailable()
    return chunks, provider_label


def _aggregate_provider_labels(labels: list[str]) -> str:
    distinct = list(dict.fromkeys(label for label in labels if label))
    if not distinct:
        return ""
    if len(distinct) == 1:
        return distinct[0]
    return "mixed"


async def run_auto_speaker_preflight(
    state: Mapping[str, object],
    *,
    prepare_subtitles: Callable[..., Any],
    post_prepare_gate: Callable[[dict, Mapping[str, object]], Any],
    extract_pcm: Callable[..., Any],
    classify_speakers: Callable[..., dict[str, dict]] | None = None,
) -> dict[str, Any]:
    """Prepare, gate, stream-classify, clean up, and stop before Task 5 work."""

    current = state if isinstance(state, Mapping) else {}
    pcm_path: Path | None = None
    try:
        if not is_auto_speaker_state(current):
            raise speaker_cast.AutoCastUnavailable()
        prepared = await _maybe_await(
            prepare_subtitles(current, require_auto_cast=True)
        )
        gate_result = await _maybe_await(post_prepare_gate(prepared, current))
        if not _gate_continues(gate_result):
            return gate_result

        labels, ranges_by_speaker = _validated_classifier_inputs(prepared)
        extracted = await _maybe_await(
            extract_pcm(
                prepared,
                current,
                channels=1,
                sample_rate=speaker_cast.PCM_SAMPLE_RATE,
                sample_format="s16le",
            )
        )
        pcm_path = _validated_pcm_path(prepared, extracted)
        classifications = await _classify_off_event_loop(
            pcm_path,
            ranges_by_speaker,
            classify_speakers,
        )
        result = {
            "ok": True,
            "status": AUTO_SPEAKER_PREFLIGHT_READY,
            "prepared": prepared,
            "speaker_labels": labels,
            "classifications": classifications,
        }
    except asyncio.CancelledError:
        _cleanup_pcm_path(pcm_path)
        raise
    except (speaker_cast.AutoCastUnavailable, speaker_cast.AutoCastManualRequired) as exc:
        _cleanup_pcm_path(pcm_path)
        return _manual_required_result(current, exc)
    except Exception:
        _cleanup_pcm_path(pcm_path)
        raise

    if not _cleanup_pcm_path(pcm_path):
        return _manual_required_result(current, speaker_cast.AutoCastManualRequired())
    return result


async def run_auto_speaker_blackbox(
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
    required_pool_capacity: int = 1,
    classify_speakers: Callable[..., dict[str, dict]] | None = None,
    **payload: Any,
) -> dict[str, Any]:
    """Run the Auto-only wrappers, then delegate once to the protected lane."""

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
        if not callable(synthesize_segments):
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

        preflight = await run_auto_speaker_preflight(
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
            and preflight.get("status") == AUTO_SPEAKER_PREFLIGHT_READY
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
        source_speaker_order = speaker_cast.ordered_auto_speaker_labels(source_segments)
        if source_speaker_order != speaker_labels:
            raise speaker_cast.AutoCastUnavailable()
        assignment_seed = _nested_receipt_value(
            prepared,
            "speaker_sidecar_sha256",
        )
        casts = speaker_cast.assign_stable_voices(
            classifications,
            speaker_order=speaker_labels,
            validated_pools=validated_pools,
            assignment_seed=assignment_seed,
        )
        annotated_prepared, assignments = _annotate_prepared_assignments(
            prepared,
            casts,
        )
    except asyncio.CancelledError:
        raise
    except (speaker_cast.AutoCastUnavailable, speaker_cast.AutoCastManualRequired) as exc:
        return _manual_required_result(current, exc)

    expected_selected_signature: tuple[tuple[str, float, float, str], ...] | None = None

    async def already_prepared(_state: dict) -> dict[str, Any]:
        return annotated_prepared

    def auto_resolve_voice_id(_user_id: int | str, pipeline_state: dict) -> str:
        nonlocal expected_selected_signature
        try:
            selected = _validated_policy_segments(
                pipeline_state,
                annotated_prepared,
                assignments,
            )
            expected_selected_signature = _selected_voice_signature(selected)
            return expected_selected_signature[0][3]
        except (speaker_cast.AutoCastUnavailable, speaker_cast.AutoCastManualRequired) as exc:
            record_owned_failure(exc)
            raise

    async def auto_synthesize_segments(
        segments: list[dict],
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            if expected_selected_signature is None:
                raise speaker_cast.AutoCastUnavailable()
            selected = _validated_assigned_segments(segments, assignments)
            actual_signature = _selected_voice_signature(selected)
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
                scalar_result = await _maybe_await(
                    synthesize_segments(
                        [cue],
                        *args,
                        **scalar_kwargs,
                    )
                )
                scalar_chunks, provider_label = _validated_scalar_result(
                    scalar_result,
                    cue,
                )
                chunks.extend(scalar_chunks)
                provider_labels.append(provider_label)
                scalar_result_count += 1
            if scalar_result_count != len(selected):
                raise speaker_cast.AutoCastUnavailable()
            return {
                "chunks": chunks,
                "provider": _aggregate_provider_labels(provider_labels),
            }
        except (speaker_cast.AutoCastUnavailable, speaker_cast.AutoCastManualRequired) as exc:
            record_owned_failure(exc)
            raise

    lane_payload = dict(payload)
    lane_payload.update(
        {
            "prepare_subtitles": already_prepared,
            "resolve_voice_id": auto_resolve_voice_id,
            "synthesize_segments": auto_synthesize_segments,
        }
    )
    try:
        result = await _maybe_await(
            run_lane_blackbox(
                lane_mode=lane_mode,
                runner=runner,
                **lane_payload,
            )
        )
    except asyncio.CancelledError:
        raise
    except (speaker_cast.AutoCastUnavailable, speaker_cast.AutoCastManualRequired) as exc:
        return _manual_required_result(current, failure_slot[0] if failure_slot else exc)
    except Exception:
        if failure_slot:
            return _manual_required_result(current, failure_slot[0])
        raise
    if failure_slot:
        return _manual_required_result(current, failure_slot[0])
    if not isinstance(result, dict):
        return _manual_required_result(current, speaker_cast.AutoCastUnavailable())
    return result
