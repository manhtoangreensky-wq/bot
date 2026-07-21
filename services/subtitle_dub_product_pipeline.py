from __future__ import annotations

import asyncio
from typing import Any, Callable

from services.subdub_tts_language_routing import (
    resolve_subdub_tts_language_route,
    subdub_tts_language_state_fields,
)


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


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


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


def resolve_subdub_dub_audio_policy(state: dict, prepared: dict) -> dict[str, Any]:
    """Select one TTS text source and make original-audio mixing explicit."""
    current = dict(state or {})
    prepared = dict(prepared or {})
    source_segments = list(prepared.get("source_segments") or [])
    output_segments = list(prepared.get("output_segments") or [])
    requested_source = str(
        current.get("dub_text_source")
        or current.get("voice_text_source")
        or current.get("dub_language_mode")
        or ""
    ).strip().lower()
    target_language = str(current.get("target_language") or "").strip().lower()
    source_aliases = {
        "source", "original", "same", "nguyen ban", "nguyên bản",
        "giu nguyen ngon ngu goc", "giữ nguyên ngôn ngữ gốc",
    }
    translated_aliases = {"translated", "translation", "target", "target_language"}
    translated_requested = (
        requested_source in translated_aliases
        or _truthy(current.get("translate_requested"))
        or (bool(target_language) and target_language not in {"auto", *source_aliases})
    )
    source_requested = requested_source in source_aliases or target_language in source_aliases

    if source_requested or not translated_requested:
        dub_text_source = "source"
        tts_segments = source_segments or output_segments
    else:
        dub_text_source = "translated"
        tts_segments = [
            dict(item or {})
            for item in output_segments
            if str((item or {}).get("text") or "").strip()
            and not _truthy((item or {}).get("translate_missing"))
        ]

    keep_original_audio = _truthy(current.get("keep_original_audio"))
    policy_fields = {
        "dub_text_source": dub_text_source,
        "original_audio_policy": "kept_low_volume" if keep_original_audio else "muted",
        "tts_tracks_count": 1 if tts_segments else 0,
        "source_tts_rendered": dub_text_source == "source" and bool(tts_segments),
        "target_tts_rendered": dub_text_source == "translated" and bool(tts_segments),
        "keep_original_audio": keep_original_audio,
    }
    return {**policy_fields, "tts_segments": tts_segments}


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
        "tts_language_preflight": False,
        "tts": False,
        "render": False,
    }
    tts_language_route: dict[str, Any] = {}
    if _mode_needs_dub(mode):
        route_attempts["tts_language_preflight"] = True
        tts_language_route = resolve_subdub_tts_language_route(state)
        language_fields = subdub_tts_language_state_fields(tts_language_route)
        state.update(language_fields)
        if not tts_language_route.get("ok"):
            return {
                "ok": False,
                "status": "UNSUPPORTED_LANGUAGE_FOR_TTS",
                "error_code": "unsupported_language_for_tts",
                "admin_debug_summary": "unsupported_language_for_tts",
                "public_safe_error": "Ngôn ngữ lồng tiếng này chưa được hỗ trợ. Hệ thống chưa xử lý file và chưa trừ Xu.",
                "provider_called": False,
                "tts_provider_called": False,
                "charged": False,
                "created_files": [],
                "state": state,
                "product_type": _product_type_for_mode(mode),
                "route_attempts": route_attempts,
                **language_fields,
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
    if tts_language_route:
        language_fields = subdub_tts_language_state_fields(tts_language_route)
        pipeline_state.update(language_fields)
        prepared["tts_language_route"] = dict(tts_language_route)
    source_bytes = bytes(prepared.get("source_bytes") or b"")
    content_type = str(prepared.get("content_type") or "")
    output_subtitle = str(prepared.get("output_subtitle") or "").strip()
    output_text = str(prepared.get("output_script") or "").strip()
    output_segments = list(prepared.get("output_segments") or []) or list(segments_from_subtitle(output_subtitle) or [])
    if not output_segments and output_text:
        output_segments = list(segments_from_text(output_text, _safe_int(pipeline_state.get("video_duration") or pipeline_state.get("source_duration"), 0)) or [])
    if mode == VIDEO_SUBTITLE_MODE_DUB and not output_segments:
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
    tts_chunks: list[dict] = []
    tts_expected_segments = 0
    tts_generated_segments = 0
    tts_mixed_segments = 0
    tts_dropped_segments = 0
    tts_timeline_duration = 0.0
    audio_padding_seconds = 0.0
    selected_tts_voice_id = ""
    dub_audio_policy: dict[str, Any] = {}
    if _mode_needs_dub(mode):
        dub_audio_policy = resolve_subdub_dub_audio_policy(pipeline_state, prepared)
        tts_segments = list(dub_audio_policy.pop("tts_segments", []) or [])
        pipeline_state.update(dub_audio_policy)
        prepared["dub_audio_policy"] = dict(dub_audio_policy)
        if not tts_segments:
            translated = dub_audio_policy.get("dub_text_source") == "translated"
            return {
                "ok": False,
                "status": "TRANSLATED_TEXT_UNAVAILABLE" if translated else "DIALOGUE_UNAVAILABLE",
                "error_code": "translated_tts_segments_missing" if translated else "source_tts_segments_missing",
                "provider_called": bool(prepared.get("asr_provider") or prepared.get("translation_provider")),
                "charged": False,
                "created_files": [],
                "state": pipeline_state,
                "prepared": prepared,
                "product_type": _product_type_for_mode(mode),
                "route_attempts": route_attempts,
                **dub_audio_policy,
            }
        tts_expected_segments = len(tts_segments)
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
        voice_resolution = dict(pipeline_state.get("_subdub_voice_resolution") or {})
        pipeline_state["resolved_voice_id_masked"] = (
            f"{selected_tts_voice_id[:4]}...{selected_tts_voice_id[-3:]}"
            if len(selected_tts_voice_id) > 9
            else selected_tts_voice_id
        )
        pipeline_state["resolved_voice_name"] = str(
            voice_resolution.get("selected_voice_label")
            or pipeline_state.get("voice_style")
            or pipeline_state.get("voice_kind")
            or "selected_subdub_voice"
        )[:120]
        speed = float(parse_voice_speed(str(pipeline_state.get("voice_speed") or "1.0")))
        route_attempts["tts"] = True
        segment_tts = await _maybe_await(
            synthesize_segments(
                tts_segments,
                voice_style=pipeline_state.get("voice_style") or "",
                voice_id=selected_tts_voice_id,
                base_speed=speed,
                max_speed=min(1.0, max(0.7, speed)),
                tts_language_code=pipeline_state.get("resolved_tts_language_code") or "auto",
                tts_language_boost=pipeline_state.get("tts_language_boost") or "auto",
                edge_voice_id=pipeline_state.get("resolved_edge_voice_id") or "",
            )
        )
        segment_tts = dict(segment_tts or {})
        tts_chunks = list(segment_tts.get("chunks") or [])
        tts_generated_segments = len(tts_chunks)
        tts_dropped_segments = max(0, tts_expected_segments - tts_generated_segments)
        if tts_dropped_segments:
            return {
                "ok": False,
                "status": "TTS_SEGMENT_COVERAGE_FAILED",
                "error_code": "tts_segments_dropped",
                "provider_called": True,
                "charged": False,
                "created_files": [],
                "state": pipeline_state,
                "prepared": prepared,
                "route_attempts": route_attempts,
                "tts_expected_segments": tts_expected_segments,
                "tts_generated_segments": tts_generated_segments,
                "tts_mixed_segments": 0,
                "tts_dropped_segments": tts_dropped_segments,
            }
        tts_provider = str(segment_tts.get("provider") or "")
        timeline_duration = max(
            float(
                pipeline_state.get("input_duration_seconds")
                or pipeline_state.get("input_duration")
                or pipeline_state.get("video_duration")
                or pipeline_state.get("source_duration")
                or 0
            ),
            max((float(item.get("end") or 0) for item in tts_segments), default=0.0),
        )
        tts_timeline_duration = float(timeline_duration or 0.0)
        latest_audio_end = max(
            (
                float(item.get("start") or 0.0)
                + float(item.get("audio_duration") or 0.0)
                for item in tts_chunks
            ),
            default=0.0,
        )
        audio_padding_seconds = max(0.0, tts_timeline_duration - latest_audio_end)
        raw_audio_bytes, _timeline_detail = await _maybe_await(build_timeline_audio(tts_chunks, timeline_duration))
        if not raw_audio_bytes:
            return {
                "ok": False,
                "status": "NO_AUDIO_BYTES",
                "error_code": "dub_audio_empty",
                "provider_called": True,
                "charged": False,
                "created_files": [],
                "route_attempts": route_attempts,
            }
        tts_mixed_segments = tts_generated_segments
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
    if _is_video_source(content_type):
        if audio_bytes and dub_mux_enabled and ffmpeg_ready():
            try:
                route_attempts["render"] = True
                video_output, _render_detail = await _maybe_await(
                    render_video(
                        source_bytes,
                        dubbed_audio=audio_bytes,
                        subtitle_bytes=srt_bytes if wants_subtitle_video else b"",
                        keep_original_audio=bool(dub_audio_policy.get("keep_original_audio")),
                    )
                )
            except Exception as exc:
                video_output = b""
                prepared["mux_error"] = type(exc).__name__
        elif audio_bytes and wants_final_video:
            prepared["mux_error"] = "mux_unavailable"
        elif wants_subtitle_video and video_render_ready(output_type):
            route_attempts["render"] = True
            video_output, _render_detail = await _maybe_await(
                render_video(
                    source_bytes,
                    subtitle_bytes=srt_bytes,
                )
            )
        if wants_final_video and not video_output and (srt_bytes or audio_bytes):
            partial_result = True
            partial_reason = str(prepared.get("mux_error") or "video_render_unavailable")
            prepared["partial_reason"] = partial_reason

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
        "tts_expected_segments": tts_expected_segments,
        "tts_generated_segments": tts_generated_segments,
        "tts_mixed_segments": tts_mixed_segments,
        "tts_dropped_segments": tts_dropped_segments,
        "tts_overlap_resolutions": max(0, sum(1 for item in tts_chunks if float(item.get("audio_duration") or 0.0) > max(0.1, float(item.get("end") or 0.0) - float(item.get("start") or 0.0)))),
        "tts_timeline_duration": tts_timeline_duration,
        "audio_padding_seconds": audio_padding_seconds,
        "raw_audio_bytes": raw_audio_bytes,
        "audio_bytes": audio_bytes,
        "video_output": video_output,
        "normalization_detail": normalization_detail,
        "selected_tts_voice_id": selected_tts_voice_id,
        "requested_target_language": str(pipeline_state.get("requested_target_language") or ""),
        "resolved_tts_language_code": str(pipeline_state.get("resolved_tts_language_code") or ""),
        "resolved_voice_id_masked": str(pipeline_state.get("resolved_voice_id_masked") or ""),
        "resolved_voice_name": str(pipeline_state.get("resolved_voice_name") or ""),
        "voice_source": str(pipeline_state.get("voice_source") or ""),
        "unsupported_reason": str(pipeline_state.get("unsupported_reason") or ""),
        "output_type": output_type,
        "provider_called": bool(prepared.get("asr_provider") or prepared.get("translation_provider") or tts_provider),
        "charged": False,
        "created_files": [],
        "error_code": "",
        "safe_public_message": "",
        "admin_debug_summary": "",
        "route_attempts": route_attempts,
        "shared_core_used": True,
        **dub_audio_policy,
    }


async def run_subdub_pipeline(job_id: str = "", mode: str = "", **kwargs: Any) -> dict[str, Any]:
    result = await process_subtitle_dub_job(mode=mode, **kwargs)
    result["job_id"] = str(job_id or "")
    result["mode"] = str(mode or result.get("mode") or "")
    result["shared_core_used"] = True
    return result
