"""Provider-neutral chunk orchestration for long SubDub media."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
import re
import tempfile
import time
from typing import Any, Awaitable, Callable, Iterable


ChunkExtractor = Callable[[bytes, str, float, float], Awaitable[tuple[bytes, str, str]] | tuple[bytes, str, str]]
ChunkTranscriber = Callable[[bytes, str], Awaitable[dict[str, Any]] | dict[str, Any]]
PartSplitter = Callable[[dict[str, Any]], Awaitable[bytes] | bytes]
PartProcessor = Callable[[bytes, dict[str, Any]], Awaitable[dict[str, Any]] | dict[str, Any]]


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


_NO_SPEECH_STATUSES = frozenset(
    {
        "empty_transcript",
        "deepgram_empty_transcript",
        "long_media_chunk_asr_empty",
        "asr_empty",
        "no_speech",
        "no_speech_detected",
        "speech_not_detected",
        "transcript_empty",
    }
)


def is_no_speech_result(result: dict[str, Any], transcript: str = "") -> bool:
    """Classify only explicit silence/empty-speech outcomes as skippable."""
    current = dict(result or {})
    status = str(current.get("status") or "").strip().lower().replace("-", "_").replace(" ", "_")
    return bool(
        current.get("no_speech")
        or current.get("speech_detected") is False
        or status in _NO_SPEECH_STATUSES
        or (
            current.get("ok") is True
            and not transcript
            and status in {"", "ok", "pass", "success"}
            and not current.get("error")
        )
    )


def build_long_project_plan(
    duration_seconds: float,
    *,
    part_seconds: int = 300,
    max_parts: int = 12,
    max_duration_seconds: int = 3600,
) -> dict[str, Any]:
    """Plan bounded MP4 parts without changing the per-part pipeline limit."""
    duration = max(0, int(round(_float(duration_seconds))))
    part_size = max(30, int(part_seconds or 300))
    part_limit = max(1, int(max_parts or 1))
    duration_limit = max(part_size, int(max_duration_seconds or part_size))
    ranges = []
    for start in range(0, duration, part_size):
        end = min(duration, start + part_size)
        ranges.append(
            {
                "index": len(ranges) + 1,
                "start": start,
                "end": end,
                "duration": end - start,
            }
        )
    split_required = duration > part_size
    supported = bool(
        duration > 0
        and duration <= duration_limit
        and len(ranges) <= part_limit
    )
    blocker = ""
    if duration > duration_limit:
        blocker = "project_duration_limit_exceeded"
    elif len(ranges) > part_limit:
        blocker = "project_part_limit_exceeded"
    return {
        "project_split_required": split_required,
        "project_supported": supported,
        "project_part_seconds": part_size,
        "project_part_count": len(ranges),
        "project_part_ranges": ranges,
        "project_max_parts": part_limit,
        "project_max_duration_seconds": duration_limit,
        "project_blocker": blocker,
    }


async def extract_audio_chunk(
    source_bytes: bytes,
    *,
    ffmpeg_path: str,
    run_command: Callable[..., Any],
    start_seconds: float,
    duration_seconds: float,
) -> tuple[bytes, str, str]:
    """Extract one ASR audio range using an injected FFmpeg runner."""
    if not ffmpeg_path:
        raise RuntimeError("audio_chunk_extract_unavailable")
    start = max(0.0, _float(start_seconds))
    duration = max(0.1, _float(duration_seconds))
    with tempfile.TemporaryDirectory(prefix="toanaas_subdub_chunk_") as tmpdir:
        source_path = os.path.join(tmpdir, "source_media")
        audio_path = os.path.join(tmpdir, "speech_chunk.mp3")
        with open(source_path, "wb") as handle:
            handle.write(source_bytes)
        command = [
            ffmpeg_path,
            "-y",
            "-ss",
            f"{start:.3f}",
            "-i",
            source_path,
            "-t",
            f"{duration:.3f}",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "96k",
            audio_path,
        ]
        ok, detail = await _maybe_await(run_command(command, timeout=120))
        if not ok or not os.path.exists(audio_path) or os.path.getsize(audio_path) <= 0:
            raise RuntimeError(f"audio_chunk_extract_failed:{str(detail or 'unknown')[:120]}")
        with open(audio_path, "rb") as handle:
            return handle.read(), "audio/mpeg", f"ffmpeg_audio_chunk:{start:.3f}-{start + duration:.3f}"


async def extract_video_part(
    source_bytes: bytes,
    *,
    ffmpeg_path: str,
    run_command: Callable[..., Any],
    probe_video: Callable[[bytes], Any],
    start_seconds: float,
    duration_seconds: float,
    min_output_bytes: int = 2048,
) -> bytes:
    """Create one self-contained MP4 part, preferring stream copy then re-encode."""
    if not ffmpeg_path:
        raise RuntimeError("video_part_split_unavailable")
    start = max(0.0, _float(start_seconds))
    duration = max(1.0, _float(duration_seconds))
    timeout_seconds = max(180, min(1200, int(duration * 4)))
    minimum = max(512, int(min_output_bytes or 2048))
    with tempfile.TemporaryDirectory(prefix="toanaas_subdub_video_part_") as tmpdir:
        source_path = os.path.join(tmpdir, "source.mp4")
        copy_path = os.path.join(tmpdir, "part_copy.mp4")
        render_path = os.path.join(tmpdir, "part_render.mp4")
        with open(source_path, "wb") as handle:
            handle.write(source_bytes)

        copy_command = [
            ffmpeg_path,
            "-y",
            "-ss",
            f"{start:.3f}",
            "-i",
            source_path,
            "-t",
            f"{duration:.3f}",
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c",
            "copy",
            "-avoid_negative_ts",
            "make_zero",
            "-movflags",
            "+faststart",
            copy_path,
        ]
        copy_ok, _copy_detail = await _maybe_await(run_command(copy_command, timeout=timeout_seconds))
        if copy_ok and os.path.exists(copy_path) and os.path.getsize(copy_path) >= minimum:
            with open(copy_path, "rb") as handle:
                copy_bytes = handle.read()
            probe = dict(await _maybe_await(probe_video(copy_bytes)) or {})
            actual_duration = _float(probe.get("duration"))
            if probe.get("ok") and actual_duration >= max(1.0, duration - 8.0) and actual_duration <= duration + 8.0:
                return copy_bytes

        render_command = [
            ffmpeg_path,
            "-y",
            "-ss",
            f"{start:.3f}",
            "-i",
            source_path,
            "-t",
            f"{duration:.3f}",
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-avoid_negative_ts",
            "make_zero",
            "-movflags",
            "+faststart",
            render_path,
        ]
        render_ok, render_detail = await _maybe_await(run_command(render_command, timeout=timeout_seconds))
        if not render_ok or not os.path.exists(render_path) or os.path.getsize(render_path) < minimum:
            raise RuntimeError(f"video_part_split_failed:{str(render_detail or 'unknown')[:120]}")
        with open(render_path, "rb") as handle:
            part_bytes = handle.read()
        validation = dict(await _maybe_await(probe_video(part_bytes)) or {})
        if not validation.get("ok"):
            raise RuntimeError("video_part_validation_failed")
        return part_bytes


def build_project_child_state(state: dict[str, Any], part: dict[str, Any], part_bytes: bytes) -> dict[str, Any]:
    """Isolate one project part from parent job/workspace/subtitle caches."""
    current = dict(state or {})
    part_index = int(part.get("index") or 1)
    part_duration = max(1, int(part.get("duration") or (_float(part.get("end")) - _float(part.get("start")))))
    source_token = str(
        current.get("source_file_unique_id")
        or current.get("video_file_unique_id")
        or current.get("source_file_id")
        or current.get("video_file_id")
        or "subdub-project"
    )
    for key in (
        "_pipeline_job_id",
        "_pipeline_job_key",
        "_pipeline_workspace",
        "_pipeline_saved_source_path",
        "status_panel_message_id",
        "subtitle_ref",
        "source_subtitle_ref",
        "translated_subtitle_ref",
        "source_subtitle",
        "translated_subtitle",
    ):
        current.pop(key, None)
    part_token = f"{source_token}:part:{part_index}"
    current.update(
        {
            "_subdub_long_project_child": True,
            "_pipeline_source_bytes_override": bytes(part_bytes),
            "_pipeline_source_content_type_override": "video/mp4",
            "source_mime_type": "video/mp4",
            "source_media_type": "video",
            "media_kind": "video",
            "source_file_unique_id": part_token,
            "video_file_unique_id": part_token,
            "source_file_id": part_token,
            "video_file_id": part_token,
            "source_file_name": f"subdub_part_{part_index:02d}.mp4",
            "source_file_size": len(part_bytes),
            "video_file_size": len(part_bytes),
            "video_duration": part_duration,
            "source_duration": part_duration,
            "input_duration": part_duration,
            "input_duration_seconds": part_duration,
            "active_flow": f"{str(current.get('active_flow') or 'subdub')}:part:{part_index}",
            "long_project_part_index": part_index,
            "long_project_part_start": int(part.get("start") or 0),
            "long_project_part_end": int(part.get("end") or part_duration),
            "long_project_part_duration": part_duration,
        }
    )
    return current


def offset_chunk_segments(
    segments: Iterable[dict[str, Any]],
    *,
    chunk_start: float,
    chunk_end: float,
    fallback_text: str = "",
) -> list[dict[str, Any]]:
    """Map chunk-local cue times onto the absolute media timeline."""
    start_offset = max(0.0, _float(chunk_start))
    absolute_end = max(start_offset, _float(chunk_end, start_offset))
    chunk_duration = max(0.0, absolute_end - start_offset)
    normalized: list[dict[str, Any]] = []
    source_segments = list(segments or [])
    if not source_segments and str(fallback_text or "").strip() and chunk_duration > 0:
        source_segments = [{"start": 0.0, "end": chunk_duration, "text": str(fallback_text).strip()}]

    for source in source_segments:
        text = str((source or {}).get("text") or (source or {}).get("transcript") or "").strip()
        if not text:
            continue
        local_start = min(chunk_duration, max(0.0, _float((source or {}).get("start"))))
        local_end = min(chunk_duration, max(local_start, _float((source or {}).get("end"), local_start)))
        if local_end <= local_start:
            local_end = min(chunk_duration, local_start + 0.5)
        if local_end <= local_start:
            continue
        normalized.append(
            {
                **dict(source or {}),
                "start": round(start_offset + local_start, 3),
                "end": round(min(absolute_end, start_offset + local_end), 3),
                "text": text,
            }
        )
    return normalized


def slice_segments_for_project_part(
    segments: Iterable[dict[str, Any]],
    *,
    part_start: float,
    part_end: float,
) -> list[dict[str, Any]]:
    """Clip absolute subtitle cues to one project part and reset that part to zero."""
    start = max(0.0, _float(part_start))
    end = max(start, _float(part_end, start))
    sliced: list[dict[str, Any]] = []
    for source in segments or []:
        cue_start = max(0.0, _float((source or {}).get("start")))
        cue_end = max(cue_start, _float((source or {}).get("end"), cue_start))
        if cue_end <= start or cue_start >= end:
            continue
        local_start = max(start, cue_start) - start
        local_end = min(end, cue_end) - start
        text = str((source or {}).get("text") or "").strip()
        if not text or local_end <= local_start:
            continue
        sliced.append(
            {
                **dict(source or {}),
                "index": len(sliced) + 1,
                "start": round(local_start, 3),
                "end": round(local_end, 3),
                "text": text,
            }
        )
    return sliced


async def transcribe_long_media_chunks(
    source_bytes: bytes,
    content_type: str,
    chunk_ranges: Iterable[dict[str, Any]],
    *,
    extract_chunk: ChunkExtractor,
    transcribe_chunk: ChunkTranscriber,
    input_duration_seconds: float = 0.0,
    source_hash: str = "",
    checkpoint_path: str = "",
) -> dict[str, Any]:
    """Transcribe deterministic audio chunks with durable, no-resubmit recovery."""
    ranges = [dict(item or {}) for item in (chunk_ranges or [])]
    if not source_bytes or not ranges:
        return {
            "ok": False,
            "status": "long_media_chunk_plan_missing",
            "detail": "source_or_chunk_ranges_missing",
            "segments": [],
            "text": "",
            "chunk_count": 0,
            "chunk_strategy": "asr_audio_chunks",
        }

    source_fingerprint = str(source_hash or hashlib.sha256(bytes(source_bytes)).hexdigest())
    checkpoint: dict[str, Any] = {
        "schema_version": "subdub.asr_chunks.v1",
        "source_hash": source_fingerprint,
        "chunks": {},
    }
    if checkpoint_path and os.path.isfile(checkpoint_path):
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if (
                isinstance(loaded, dict)
                and str(loaded.get("source_hash") or "") == source_fingerprint
                and isinstance(loaded.get("chunks"), dict)
            ):
                checkpoint = loaded
        except (OSError, ValueError, TypeError):
            checkpoint = {
                "schema_version": "subdub.asr_chunks.v1",
                "source_hash": source_fingerprint,
                "chunks": {},
            }

    def _persist_checkpoint() -> None:
        if not checkpoint_path:
            return
        directory = os.path.dirname(os.path.abspath(checkpoint_path))
        os.makedirs(directory, exist_ok=True)
        temporary = f"{checkpoint_path}.tmp"
        with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(checkpoint, handle, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        os.replace(temporary, checkpoint_path)

    def _chunk_bounds(item: dict[str, Any], position: int) -> dict[str, Any]:
        chunk_index = int(item.get("index") or item.get("chunk_index") or position)
        extract_start_ms = int(
            item.get("extract_start_ms")
            if item.get("extract_start_ms") is not None
            else round(_float(item.get("start")) * 1000)
        )
        extract_end_ms = int(
            item.get("extract_end_ms")
            if item.get("extract_end_ms") is not None
            else round(_float(item.get("end"), extract_start_ms / 1000.0) * 1000)
        )
        ownership_start_ms = int(item.get("ownership_start_ms", extract_start_ms))
        ownership_end_ms = int(item.get("ownership_end_ms", extract_end_ms))
        chunk_id = str(item.get("chunk_id") or "").strip()
        if not chunk_id:
            token = f"{source_fingerprint}:{chunk_index}:{ownership_start_ms}:{ownership_end_ms}"
            chunk_id = hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]
        return {
            "index": chunk_index,
            "chunk_id": chunk_id,
            "extract_start_ms": max(0, extract_start_ms),
            "extract_end_ms": max(extract_start_ms, extract_end_ms),
            "ownership_start_ms": max(0, ownership_start_ms),
            "ownership_end_ms": max(ownership_start_ms, ownership_end_ms),
        }

    candidate_segments: list[dict[str, Any]] = []
    providers: list[str] = []
    detected_languages: list[str] = []
    extraction_details: list[str] = []
    skipped_chunk_indices: list[int] = []
    skipped_chunk_details: list[str] = []
    provider_submit_count = 0
    checkpoint_reused_count = 0

    for position, item in enumerate(ranges, start=1):
        bounds = _chunk_bounds(item, position)
        chunk_index = int(bounds["index"])
        chunk_id = str(bounds["chunk_id"])
        chunk_start = float(bounds["extract_start_ms"]) / 1000.0
        chunk_end = float(bounds["extract_end_ms"]) / 1000.0
        chunk_duration = chunk_end - chunk_start
        if chunk_duration <= 0:
            return {
                "ok": False,
                "status": "long_media_chunk_range_invalid",
                "detail": f"chunk={chunk_index}",
                "segments": [],
                "text": "",
                "failed_chunk_index": chunk_index,
                "chunk_count": len(ranges),
                "chunk_strategy": "asr_audio_chunks",
            }
        stored = dict((checkpoint.get("chunks") or {}).get(chunk_id) or {})
        stored_status = str(stored.get("status") or "").upper()
        if stored_status == "ACCEPTANCE_UNKNOWN":
            return {
                "ok": False,
                "status": "ACCEPTANCE_UNKNOWN",
                "detail": f"chunk={chunk_index}; acceptance_unknown_no_resubmit",
                "segments": [],
                "text": "",
                "failed_chunk_index": chunk_index,
                "chunk_count": len(ranges),
                "chunk_strategy": "checkpointed_audio_chunks",
                "provider_submit_count": provider_submit_count,
                "checkpoint_reused_count": checkpoint_reused_count,
                "global_timing_preserved": True,
            }
        if stored_status in {"COMPLETED", "NO_SPEECH"}:
            checkpoint_reused_count += 1
            if stored_status == "NO_SPEECH":
                skipped_chunk_indices.append(chunk_index)
                skipped_chunk_details.append(f"chunk={chunk_index}; status=checkpoint_no_speech")
                continue
            stored_segments = [dict(segment or {}) for segment in list(stored.get("segments") or [])]
            for segment in stored_segments:
                segment.update({
                    "_chunk_id": chunk_id,
                    "_chunk_index": chunk_index,
                    "_ownership_start_ms": int(bounds["ownership_start_ms"]),
                    "_ownership_end_ms": int(bounds["ownership_end_ms"]),
                })
            candidate_segments.extend(stored_segments)
            providers.append(str(stored.get("provider") or ""))
            detected_languages.append(str(stored.get("language") or ""))
            extraction_details.append("checkpoint_reused")
            continue
        try:
            audio_bytes, audio_content_type, extraction_detail = await _maybe_await(
                extract_chunk(source_bytes, content_type, chunk_start, chunk_duration)
            )
        except Exception as exc:
            return {
                "ok": False,
                "status": "long_media_chunk_extract_failed",
                "detail": f"chunk={chunk_index}; error={type(exc).__name__}",
                "segments": [],
                "text": "",
                "failed_chunk_index": chunk_index,
                "chunk_count": len(ranges),
                "chunk_strategy": "asr_audio_chunks",
            }
        if not audio_bytes:
            return {
                "ok": False,
                "status": "long_media_chunk_extract_empty",
                "detail": f"chunk={chunk_index}",
                "segments": [],
                "text": "",
                "failed_chunk_index": chunk_index,
                "chunk_count": len(ranges),
                "chunk_strategy": "asr_audio_chunks",
            }
        extraction_details.append(str(extraction_detail or ""))

        try:
            provider_submit_count += 1
            result = dict(await _maybe_await(transcribe_chunk(bytes(audio_bytes), str(audio_content_type or "audio/mpeg"))) or {})
        except asyncio.TimeoutError:
            checkpoint.setdefault("chunks", {})[chunk_id] = {
                **bounds,
                "source_hash": source_fingerprint,
                "status": "ACCEPTANCE_UNKNOWN",
                "artifact_hash": hashlib.sha256(bytes(audio_bytes)).hexdigest(),
                "updated_at": time.time(),
            }
            _persist_checkpoint()
            return {
                "ok": False,
                "status": "ACCEPTANCE_UNKNOWN",
                "detail": f"chunk={chunk_index}; provider_acceptance_unknown",
                "segments": [],
                "text": "",
                "failed_chunk_index": chunk_index,
                "chunk_count": len(ranges),
                "chunk_strategy": "checkpointed_audio_chunks",
                "provider_submit_count": provider_submit_count,
                "checkpoint_reused_count": checkpoint_reused_count,
                "global_timing_preserved": True,
            }
        except Exception as exc:
            return {
                "ok": False,
                "status": "long_media_chunk_asr_failed",
                "detail": f"chunk={chunk_index}; error={type(exc).__name__}",
                "segments": [],
                "text": "",
                "failed_chunk_index": chunk_index,
                "chunk_count": len(ranges),
                "chunk_strategy": "asr_audio_chunks",
            }
        result_status = str(result.get("status") or "long_media_chunk_asr_empty").strip()
        normalized_result_status = result_status.upper()
        if (
            normalized_result_status == "ACCEPTANCE_UNKNOWN"
            or "TIMEOUT" in normalized_result_status
        ):
            checkpoint.setdefault("chunks", {})[chunk_id] = {
                **bounds,
                "source_hash": source_fingerprint,
                "status": "ACCEPTANCE_UNKNOWN",
                "provider_status": result_status,
                "artifact_hash": hashlib.sha256(bytes(audio_bytes)).hexdigest(),
                "updated_at": time.time(),
            }
            _persist_checkpoint()
            return {
                "ok": False,
                "status": "ACCEPTANCE_UNKNOWN",
                "detail": f"chunk={chunk_index}; provider_acceptance_unknown",
                "segments": [],
                "text": "",
                "failed_chunk_index": chunk_index,
                "chunk_count": len(ranges),
                "chunk_strategy": "checkpointed_audio_chunks",
                "provider_submit_count": provider_submit_count,
                "checkpoint_reused_count": checkpoint_reused_count,
                "global_timing_preserved": True,
            }
        transcript = str(result.get("text") or result.get("transcript") or "").strip()
        if not result.get("ok") or not transcript:
            if is_no_speech_result(result, transcript):
                skipped_chunk_indices.append(chunk_index)
                skipped_chunk_details.append(
                    f"chunk={chunk_index}; status={result_status[:80]}"
                )
                checkpoint.setdefault("chunks", {})[chunk_id] = {
                    **bounds,
                    "source_hash": source_fingerprint,
                    "status": "NO_SPEECH",
                    "artifact_hash": hashlib.sha256(bytes(audio_bytes)).hexdigest(),
                    "updated_at": time.time(),
                }
                _persist_checkpoint()
                continue
            return {
                "ok": False,
                "status": result_status,
                "detail": f"chunk={chunk_index}; {str(result.get('detail') or '')[:160]}",
                "segments": [],
                "text": "",
                "failed_chunk_index": chunk_index,
                "chunk_count": len(ranges),
                "chunk_strategy": "asr_audio_chunks",
                "skipped_chunk_count": len(skipped_chunk_indices),
                "skipped_chunk_indices": skipped_chunk_indices,
            }

        absolute_segments = offset_chunk_segments(
            result.get("segments") or [],
            chunk_start=chunk_start,
            chunk_end=chunk_end,
            fallback_text=transcript,
        )
        if not absolute_segments:
            return {
                "ok": False,
                "status": "long_media_chunk_segments_empty",
                "detail": f"chunk={chunk_index}",
                "segments": [],
                "text": "",
                "failed_chunk_index": chunk_index,
                "chunk_count": len(ranges),
                "chunk_strategy": "asr_audio_chunks",
                "skipped_chunk_count": len(skipped_chunk_indices),
                "skipped_chunk_indices": skipped_chunk_indices,
            }
        stored_segments = []
        for segment in absolute_segments:
            public_segment = {
                key: value
                for key, value in dict(segment or {}).items()
                if key in {"index", "start", "end", "text", "confidence", "speaker", "language"}
            }
            stored_segments.append(public_segment)
            candidate_segments.append({
                **public_segment,
                "_chunk_id": chunk_id,
                "_chunk_index": chunk_index,
                "_ownership_start_ms": int(bounds["ownership_start_ms"]),
                "_ownership_end_ms": int(bounds["ownership_end_ms"]),
            })
        providers.append(str(result.get("provider") or ""))
        detected_languages.append(str(result.get("language") or result.get("detected_language") or ""))
        checkpoint.setdefault("chunks", {})[chunk_id] = {
            **bounds,
            "source_hash": source_fingerprint,
            "status": "COMPLETED",
            "artifact_hash": hashlib.sha256(bytes(audio_bytes)).hexdigest(),
            "transcript": transcript,
            "segments": stored_segments,
            "provider": str(result.get("provider") or ""),
            "language": str(result.get("language") or result.get("detected_language") or ""),
            "updated_at": time.time(),
        }
        _persist_checkpoint()

    def _normalized_text(value: Any) -> str:
        return re.sub(r"[^\w]+", " ", str(value or "").casefold()).strip()

    candidate_segments.sort(key=lambda segment: (_float(segment.get("start")), _float(segment.get("end"))))
    all_segments: list[dict[str, Any]] = []
    overlap_duplicate_count = 0
    for candidate in candidate_segments:
        start = _float(candidate.get("start"))
        end = max(start, _float(candidate.get("end"), start))
        start_ms = int(round(start * 1000))
        end_ms = int(round(end * 1000))
        owner_start = int(candidate.get("_ownership_start_ms") or 0)
        owner_end = int(candidate.get("_ownership_end_ms") or 0)
        ownership_overlap_ms = max(
            0,
            min(end_ms, owner_end) - max(start_ms, owner_start),
        )
        owned = ownership_overlap_ms > 0
        if not owned:
            overlap_duplicate_count += 1
            continue
        text_key = _normalized_text(candidate.get("text"))
        duplicate = False
        for existing in reversed(all_segments[-4:]):
            existing_key = _normalized_text(existing.get("text"))
            overlaps = min(end, _float(existing.get("end"))) > max(start, _float(existing.get("start")))
            if text_key and text_key == existing_key and overlaps:
                duplicate = True
                break
        if duplicate:
            overlap_duplicate_count += 1
            continue
        all_segments.append({
            key: value
            for key, value in candidate.items()
            if not str(key).startswith("_")
        })

    if not all_segments:
        return {
            "ok": False,
            "status": "long_media_no_speech",
            "detail": f"chunks={len(ranges)}; skipped={','.join(str(item) for item in skipped_chunk_indices)}",
            "segments": [],
            "text": "",
            "provider": "",
            "language": "",
            "duration_seconds": round(max(_float(input_duration_seconds), 0.0), 3),
            "chunk_count": len(ranges),
            "chunk_strategy": "asr_audio_chunks",
            "global_timing_preserved": True,
            "skipped_chunk_count": len(skipped_chunk_indices),
            "skipped_chunk_indices": skipped_chunk_indices,
            "skipped_chunk_details": skipped_chunk_details,
            "speech_chunk_count": 0,
            "provider_submit_count": provider_submit_count,
            "checkpoint_reused_count": checkpoint_reused_count,
            "overlap_duplicate_count": overlap_duplicate_count,
        }

    all_segments.sort(key=lambda item: (_float(item.get("start")), _float(item.get("end"))))
    for index, item in enumerate(all_segments, start=1):
        item["index"] = index
    duration = max(
        _float(input_duration_seconds),
        max((_float(item.get("end")) for item in all_segments), default=0.0),
    )
    return {
        "ok": bool(all_segments),
        "status": "PASS" if all_segments else "long_media_segments_empty",
        "text": " ".join(str(item.get("text") or "") for item in all_segments).strip(),
        "segments": all_segments,
        "provider": next((item for item in providers if item), ""),
        "language": next((item for item in detected_languages if item and item != "auto"), ""),
        "duration_seconds": round(duration, 3),
        "chunk_count": len(ranges),
        "chunk_strategy": "checkpointed_audio_chunks",
        "global_timing_preserved": True,
        "detail": (
            f"chunks={len(ranges)}; speech_chunks={len(ranges) - len(skipped_chunk_indices)}; "
            f"skipped={','.join(str(item) for item in skipped_chunk_indices)}; "
            f"extraction={','.join(item for item in extraction_details if item)}"
        ),
        "skipped_chunk_count": len(skipped_chunk_indices),
        "skipped_chunk_indices": skipped_chunk_indices,
        "skipped_chunk_details": skipped_chunk_details,
        "speech_chunk_count": len(ranges) - len(skipped_chunk_indices),
        "provider_submit_count": provider_submit_count,
        "checkpoint_reused_count": checkpoint_reused_count,
        "overlap_duplicate_count": overlap_duplicate_count,
        "checkpoint_path": str(checkpoint_path or ""),
    }


async def process_long_project_parts(
    project_plan: dict[str, Any],
    *,
    split_part: PartSplitter,
    process_part: PartProcessor,
) -> dict[str, Any]:
    """Run already-confirmed SubDub parts in order and stop at the first real failure."""
    plan = dict(project_plan or {})
    ranges = [dict(item or {}) for item in (plan.get("project_part_ranges") or [])]
    if not plan.get("project_supported") or not ranges:
        return {
            "ok": False,
            "status": "LONG_PROJECT_UNSUPPORTED",
            "project_blocker": str(plan.get("project_blocker") or "project_plan_invalid"),
            "project_part_count": len(ranges),
            "project_parts_delivered": 0,
            "part_results": [],
        }

    results: list[dict[str, Any]] = []
    delivered = 0
    for item in ranges:
        part_index = int(item.get("index") or len(results) + 1)
        try:
            part_bytes = bytes(await _maybe_await(split_part(item)) or b"")
        except Exception as exc:
            return {
                "ok": False,
                "status": "LONG_PROJECT_SPLIT_FAILED",
                "project_blocker": f"part={part_index}; error={type(exc).__name__}",
                "project_part_count": len(ranges),
                "project_parts_delivered": delivered,
                "failed_part_index": part_index,
                "part_results": results,
            }
        if not part_bytes:
            return {
                "ok": False,
                "status": "LONG_PROJECT_SPLIT_EMPTY",
                "project_blocker": f"part={part_index}",
                "project_part_count": len(ranges),
                "project_parts_delivered": delivered,
                "failed_part_index": part_index,
                "part_results": results,
            }
        try:
            result = dict(await _maybe_await(process_part(part_bytes, item)) or {})
        except Exception as exc:
            result = {
                "ok": False,
                "status": "LONG_PROJECT_PART_EXCEPTION",
                "detail": type(exc).__name__,
            }
        results.append(result)
        part_delivered = bool(
            result.get("ok")
            and (
                result.get("already_delivered")
                or str(result.get("terminal_state") or "").lower() == "delivered"
                or result.get("final_mp4_delivered")
                or result.get("video_delivered")
                or result.get("video_delivery_message_id")
            )
        )
        if not part_delivered:
            return {
                "ok": False,
                "status": str(result.get("status") or "LONG_PROJECT_PART_FAILED"),
                "project_blocker": str(result.get("detail") or result.get("partial_reason") or "part_not_delivered"),
                "project_part_count": len(ranges),
                "project_parts_delivered": delivered,
                "failed_part_index": part_index,
                "part_results": results,
            }
        delivered += 1

    return {
        "ok": delivered == len(ranges),
        "status": "OK" if delivered == len(ranges) else "LONG_PROJECT_INCOMPLETE",
        "project_blocker": "",
        "project_part_count": len(ranges),
        "project_parts_delivered": delivered,
        "part_results": results,
    }
