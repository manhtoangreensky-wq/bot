from __future__ import annotations

import asyncio
from typing import Any, Callable

from services import subdub_canonical_cues


VIDEO_SUBTITLE_MODE_CREATE = "subtitle_create"
VIDEO_SUBTITLE_MODE_TRANSLATE = "subtitle_translate"
VIDEO_SUBTITLE_MODE_DUB = "dub"
VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB = "subtitle_plus_dub"
SUBDUB_SHARED_CORE_MODES = {
    VIDEO_SUBTITLE_MODE_CREATE,
    VIDEO_SUBTITLE_MODE_TRANSLATE,
    VIDEO_SUBTITLE_MODE_DUB,
    VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value or default))
    except Exception:
        return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value not in (None, "") else default)
    except Exception:
        return float(default)


def _srt_timestamp(milliseconds: int) -> str:
    value = max(0, int(milliseconds or 0))
    hours, remainder = divmod(value, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _canonical_srt(cues: list[dict], *, source_text_only: bool = False) -> str:
    blocks: list[str] = []
    for position, cue in enumerate(cues or [], start=1):
        start_ms = int(cue.get("source_start_ms") or cue.get("start_ms") or 0)
        end_ms = int(cue.get("source_end_ms") or cue.get("end_ms") or 0)
        text = str(
            cue.get("source_text")
            if source_text_only
            else cue.get("translated_text") or cue.get("source_text") or ""
        ).strip()
        if end_ms <= start_ms or not text:
            continue
        blocks.append(
            f"{position}\n{_srt_timestamp(start_ms)} --> {_srt_timestamp(end_ms)}\n{text}"
        )
    return "\n\n".join(blocks).strip()


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value) or hasattr(value, "__await__"):
        return await value
    return value


def _mode_needs_dub(mode: str) -> bool:
    return mode in {VIDEO_SUBTITLE_MODE_DUB, VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}


def _mode_needs_subtitle(mode: str) -> bool:
    return mode in {
        VIDEO_SUBTITLE_MODE_CREATE,
        VIDEO_SUBTITLE_MODE_TRANSLATE,
        VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    }


def subdub_mode_uses_shared_core(mode: str) -> bool:
    return str(mode or "").strip() in SUBDUB_SHARED_CORE_MODES


def _product_type_for_mode(mode: str) -> str:
    if mode == VIDEO_SUBTITLE_MODE_DUB:
        return "dub_only"
    if mode == VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB:
        return "subtitle_dub"
    return "subtitle_only"


def _default_output_type(mode: str, state: dict, content_type: str) -> str:
    output_type = str(state.get("output_type") or "").strip().lower()
    if output_type:
        return output_type
    is_video_source = str(content_type or "").lower().startswith("video/")
    if mode in {VIDEO_SUBTITLE_MODE_CREATE, VIDEO_SUBTITLE_MODE_TRANSLATE}:
        return "burn" if is_video_source else "srt"
    if mode == VIDEO_SUBTITLE_MODE_DUB:
        return "video" if is_video_source else "audio"
    if mode == VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB:
        return "video_subtitle" if is_video_source else "audio"
    return "srt"


def _is_video_source(content_type: str) -> bool:
    return str(content_type or "").lower().startswith("video/")


def _video_output_requested(mode: str, output_type: str, content_type: str) -> bool:
    if not _is_video_source(content_type):
        return False
    output = str(output_type or "").strip().lower()
    if output in {"burn", "both", "video", "video_subtitle"}:
        return True
    return mode in {
        VIDEO_SUBTITLE_MODE_CREATE,
        VIDEO_SUBTITLE_MODE_TRANSLATE,
        VIDEO_SUBTITLE_MODE_DUB,
        VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    }


async def process_subtitle_dub_job(
    *,
    mode: str,
    state: dict,
    user_id: int | str,
    prepare_subtitles: Callable[[dict], Any],
    srt_from_text: Callable[[str, int], str],
    segments_from_text: Callable[[str, int], list[dict]],
    segments_from_subtitle: Callable[[str], list[dict]],
    subtitle_output_items: Callable[[str, str, str], list[dict]],
    resolve_voice_id: Callable[[int | str, dict], str],
    parse_voice_speed: Callable[[str], float],
    synthesize_segments: Callable[..., Any],
    build_timeline_audio: Callable[..., Any],
    normalize_audio: Callable[[bytes], Any],
    render_video: Callable[..., Any],
    video_render_ready: Callable[[str], bool],
    ffmpeg_ready: Callable[[], bool],
    dub_mux_enabled: bool,
    is_admin: bool = False,
) -> dict[str, Any]:
    del is_admin
    mode = str(mode or "").strip()
    state = dict(state or {})
    route_attempts = {
        "shared_core": subdub_mode_uses_shared_core(mode),
        "subtitle_prepare": False,
        "tts": False,
        "render": False,
    }
    try:
        route_attempts["subtitle_prepare"] = True
        prepared = await _maybe_await(prepare_subtitles(state))
    except Exception as exc:
        return {
            "ok": False,
            "status": "DIALOGUE_UNAVAILABLE" if mode == VIDEO_SUBTITLE_MODE_DUB else "SUBTITLE_PREPARE_FAILED",
            "error_code": type(exc).__name__,
            "admin_debug_summary": str(exc)[:160],
            "provider_called": False,
            "charged": False,
            "created_files": [],
            "route_attempts": route_attempts,
        }
    prepared = dict(prepared or {})
    pipeline_state = dict(prepared.get("state") or state)
    source_bytes = bytes(prepared.get("source_bytes") or b"")
    content_type = str(prepared.get("content_type") or "")
    output_subtitle = str(prepared.get("output_subtitle") or "").strip()
    output_text = str(prepared.get("output_script") or "").strip()
    canonical_mode = subdub_mode_uses_shared_core(mode)
    source_segments = list(prepared.get("canonical_source_cues") or prepared.get("source_segments") or [])
    output_segments = list(prepared.get("canonical_cues") or prepared.get("output_segments") or [])
    if not source_segments:
        source_segments = list(segments_from_subtitle(str(prepared.get("source_subtitle") or "")) or [])
    if not output_segments:
        output_segments = list(segments_from_subtitle(output_subtitle) or [])
    if not output_segments and output_text and not canonical_mode:
        output_segments = list(segments_from_text(output_text, _safe_int(pipeline_state.get("video_duration") or pipeline_state.get("source_duration"), 0)) or [])
    if canonical_mode:
        source_segments = subdub_canonical_cues.canonicalize_segments(
            source_segments or output_segments,
            extraction_source=str(prepared.get("cue_source") or prepared.get("extraction_source") or "canonical_product_contract"),
            source_language=str(prepared.get("detected_language") or pipeline_state.get("source_language") or "auto"),
        )
        if not source_segments:
            output_segments = []
        elif mode == VIDEO_SUBTITLE_MODE_CREATE:
            output_segments = list(source_segments)
        else:
            output_segments = subdub_canonical_cues.apply_translations(
                source_segments,
                output_segments or source_segments,
                target_language=str(prepared.get("target_language") or pipeline_state.get("target_language") or ""),
            )
        if output_segments and not subdub_canonical_cues.same_timeline(source_segments, output_segments):
            return {
                "ok": False,
                "status": "CANONICAL_TIMELINE_MISMATCH",
                "error_code": "canonical_timeline_mismatch",
                "provider_called": bool(prepared.get("asr_provider") or prepared.get("translation_provider")),
                "charged": False,
                "created_files": [],
                "route_attempts": route_attempts,
            }
        output_subtitle = _canonical_srt(
            output_segments,
            source_text_only=mode == VIDEO_SUBTITLE_MODE_CREATE,
        )
        output_text = "\n".join(
            str(
                cue.get("source_text")
                if mode == VIDEO_SUBTITLE_MODE_CREATE
                else cue.get("translated_text") or cue.get("source_text") or ""
            ).strip()
            for cue in output_segments
            if str(cue.get("source_text") or cue.get("translated_text") or "").strip()
        ).strip()
    if not output_segments:
        return {
            "ok": False,
            "status": "DIALOGUE_UNAVAILABLE",
            "error_code": "subtitle_segments_missing",
            "provider_called": bool(prepared.get("asr_provider") or prepared.get("translation_provider")),
            "charged": False,
            "created_files": [],
            "route_attempts": route_attempts,
        }

    srt_text = ""
    srt_bytes = b""
    output_type = _default_output_type(mode, pipeline_state, content_type)
    if _mode_needs_subtitle(mode):
        if canonical_mode:
            srt_text = _canonical_srt(
                output_segments,
                source_text_only=mode == VIDEO_SUBTITLE_MODE_CREATE,
            )
        else:
            srt_text = output_subtitle if "-->" in output_subtitle else srt_from_text(
                output_text,
                _safe_int(pipeline_state.get("video_duration") or pipeline_state.get("source_duration"), 0),
            )
        srt_bytes = str(srt_text or "").encode("utf-8")
        if not srt_text.strip() or "-->" not in srt_text:
            return {
                "ok": False,
                "status": "SUBTITLE_EMPTY",
                "error_code": "subtitle_empty",
                "provider_called": bool(prepared.get("asr_provider") or prepared.get("translation_provider")),
                "charged": False,
                "created_files": [],
                "state": pipeline_state,
                "prepared": prepared,
                "product_type": _product_type_for_mode(mode),
                "route_attempts": route_attempts,
            }
    subtitle_items = subtitle_output_items(srt_text, output_type, mode) if srt_bytes else []

    tts_provider = ""
    audio_bytes = b""
    raw_audio_bytes = b""
    normalization_detail = "not_requested"
    timeline_detail = "not_requested"
    tts_chunks: list[dict] = []
    selected_tts_voice_id = ""
    if _mode_needs_dub(mode):
        selected_tts_voice_id = str(resolve_voice_id(user_id, pipeline_state) or "")
        if not selected_tts_voice_id:
            return {
                "ok": False,
                "status": "VOICE_NOT_READY",
                "error_code": "voice_not_ready",
                "provider_called": bool(prepared.get("asr_provider") or prepared.get("translation_provider")),
                "charged": False,
                "created_files": [],
                "state": pipeline_state,
                "prepared": prepared,
                "product_type": _product_type_for_mode(mode),
                "voice_resolution": dict(pipeline_state.get("_subdub_voice_resolution") or {}),
                "route_attempts": route_attempts,
            }
        speed = float(parse_voice_speed(str(pipeline_state.get("voice_speed") or "1.0")))
        route_attempts["tts"] = True
        segment_tts = await _maybe_await(
            synthesize_segments(
                output_segments,
                voice_style=pipeline_state.get("voice_style") or "",
                voice_id=selected_tts_voice_id,
                base_speed=speed,
            )
        )
        segment_tts = dict(segment_tts or {})
        tts_chunks = list(segment_tts.get("chunks") or [])
        tts_provider = str(segment_tts.get("provider") or "")
        timeline_duration = max(
            _safe_float(pipeline_state.get("video_duration") or pipeline_state.get("source_duration"), 0.0),
            max((float(item.get("end") or 0) for item in output_segments), default=0.0),
        )
        raw_audio_bytes, timeline_detail = await _maybe_await(build_timeline_audio(tts_chunks, timeline_duration))
        if not raw_audio_bytes:
            return {
                "ok": False,
                "status": "NO_AUDIO_BYTES",
                "error_code": str(timeline_detail or "dub_audio_empty"),
                "provider_called": True,
                "charged": False,
                "created_files": [],
                "route_attempts": route_attempts,
            }
        audio_bytes, normalization_detail = await _maybe_await(normalize_audio(raw_audio_bytes))
        if not audio_bytes:
            return {
                "ok": False,
                "status": "NO_NORMALIZED_AUDIO_BYTES",
                "error_code": "dub_audio_normalize_empty",
                "provider_called": True,
                "charged": False,
                "created_files": [],
                "route_attempts": route_attempts,
            }

    wants_subtitle_video = output_type in {"burn", "both", "video_subtitle"}
    wants_final_video = _video_output_requested(mode, output_type, content_type)
    video_output = b""
    partial_result = False
    partial_reason = ""
    render_detail = ""
    if _is_video_source(content_type):
        if audio_bytes and dub_mux_enabled and ffmpeg_ready():
            try:
                route_attempts["render"] = True
                video_output, render_detail = await _maybe_await(
                    render_video(
                        source_bytes,
                        dubbed_audio=audio_bytes,
                        subtitle_bytes=srt_bytes if wants_subtitle_video else b"",
                        keep_original_audio=False,
                    )
                )
            except Exception as exc:
                video_output = b""
                prepared["mux_error"] = type(exc).__name__
        elif audio_bytes and wants_final_video:
            prepared["mux_error"] = "mux_unavailable"
        elif wants_subtitle_video and video_render_ready(output_type):
            route_attempts["render"] = True
            video_output, render_detail = await _maybe_await(
                render_video(
                    source_bytes,
                    subtitle_bytes=srt_bytes,
                )
            )
        if wants_final_video and not video_output and (srt_bytes or audio_bytes):
            partial_result = True
            partial_reason = str(prepared.get("mux_error") or "video_render_unavailable")
            prepared["partial_reason"] = partial_reason

    if wants_final_video and not video_output:
        return {
            "ok": False,
            "status": "FINAL_VIDEO_NOT_READY",
            "error_code": partial_reason or str(prepared.get("mux_error") or "final_video_not_ready"),
            "provider_called": bool(prepared.get("asr_provider") or prepared.get("translation_provider") or tts_provider),
            "charged": False,
            "created_files": [],
            "state": pipeline_state,
            "prepared": prepared,
            "product_type": _product_type_for_mode(mode),
            "route_attempts": route_attempts,
        }

    if not (srt_bytes or audio_bytes or video_output):
        return {
            "ok": False,
            "status": "NO_OUTPUT_BYTES",
            "error_code": "output_empty",
            "provider_called": bool(prepared.get("asr_provider") or prepared.get("translation_provider") or tts_provider),
            "charged": False,
            "created_files": [],
            "state": pipeline_state,
            "prepared": prepared,
            "route_attempts": route_attempts,
        }

    duration_evidence = subdub_canonical_cues.parse_render_duration_evidence(render_detail)
    return {
        "ok": True,
        "status": "PARTIAL_VIDEO_NOT_READY" if partial_result else "OK",
        "product_type": _product_type_for_mode(mode),
        "result_type": "mp4" if video_output else ("partial_audio_subtitle" if audio_bytes and partial_result else ("audio_subtitle" if audio_bytes else "subtitle")),
        "partial_result": bool(partial_result),
        "partial_reason": partial_reason,
        "video_output_requested": bool(wants_final_video),
        "state": pipeline_state,
        "prepared": prepared,
        "source_bytes": source_bytes,
        "content_type": content_type,
        "asr_provider": str(prepared.get("asr_provider") or ("cached_subtitle" if prepared.get("source_subtitle") else "")),
        "translation_provider": str(prepared.get("translation_provider") or ""),
        "tts_provider": tts_provider,
        "output_subtitle": output_subtitle,
        "output_text": output_text,
        "output_segments": output_segments,
        "srt_text": srt_text,
        "srt_bytes": srt_bytes,
        "subtitle_items": subtitle_items,
        "tts_chunks": tts_chunks,
        "raw_audio_bytes": raw_audio_bytes,
        "audio_bytes": audio_bytes,
        "video_output": video_output,
        "normalization_detail": normalization_detail,
        "timeline_detail": timeline_detail,
        "render_detail": str(render_detail or ""),
        "selected_tts_voice_id": selected_tts_voice_id,
        "output_type": output_type,
        "provider_called": bool(prepared.get("asr_provider") or prepared.get("translation_provider") or tts_provider),
        "charged": False,
        "created_files": [],
        "error_code": "",
        "safe_public_message": "",
        "admin_debug_summary": "",
        "route_attempts": route_attempts,
        "shared_core_used": True,
        "canonical_cue_mode": bool(canonical_mode),
        "canonical_cue_count": len(output_segments),
        "canonical_timeline_signature": subdub_canonical_cues.timeline_signature(output_segments) if canonical_mode else [],
        "tts_overlap_count": 0 if _mode_needs_dub(mode) and "overlap_count=0" in timeline_detail else None,
        "cue_source": str(prepared.get("cue_source") or prepared.get("extraction_source") or ""),
        "source_language": str(prepared.get("detected_language") or pipeline_state.get("source_language") or "auto"),
        "detected_script": str(prepared.get("detected_script") or "unknown"),
        "ocr_accepted": bool(prepared.get("ocr_quality_accepted")),
        "ocr_rejected": bool(prepared.get("ocr_rejected_reason")),
        "ocr_rejection_reason": str(prepared.get("ocr_rejected_reason") or ""),
        "asr_fallback_used": bool(prepared.get("asr_fallback_used")),
        **duration_evidence,
    }


async def run_subdub_pipeline(job_id: str = "", mode: str = "", **kwargs: Any) -> dict[str, Any]:
    result = await process_subtitle_dub_job(mode=mode, **kwargs)
    result["job_id"] = str(job_id or "")
    result["mode"] = str(mode or result.get("mode") or "")
    result["shared_core_used"] = True
    return result
