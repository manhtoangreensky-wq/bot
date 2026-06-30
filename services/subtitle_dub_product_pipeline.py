from __future__ import annotations

import asyncio
from typing import Any, Callable


VIDEO_SUBTITLE_MODE_CREATE = "subtitle_create"
VIDEO_SUBTITLE_MODE_TRANSLATE = "subtitle_translate"
VIDEO_SUBTITLE_MODE_DUB = "dub"
VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB = "subtitle_plus_dub"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value or default))
    except Exception:
        return int(default)


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
    try:
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
        }
    prepared = dict(prepared or {})
    pipeline_state = dict(prepared.get("state") or state)
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
            }
    subtitle_items = subtitle_output_items(srt_text, output_type, mode) if srt_bytes else []

    tts_provider = ""
    audio_bytes = b""
    raw_audio_bytes = b""
    normalization_detail = "not_requested"
    tts_chunks: list[dict] = []
    selected_tts_voice_id = ""
    if _mode_needs_dub(mode):
        selected_tts_voice_id = str(resolve_voice_id(user_id, pipeline_state) or "")
        speed = float(parse_voice_speed(str(pipeline_state.get("voice_speed") or "1.0")))
        segment_tts = await _maybe_await(
            synthesize_segments(
                output_segments,
                voice_style=pipeline_state.get("voice_style") or "",
                voice_id=selected_tts_voice_id,
                base_speed=speed,
                max_speed=max(1.35, speed),
            )
        )
        segment_tts = dict(segment_tts or {})
        tts_chunks = list(segment_tts.get("chunks") or [])
        tts_provider = str(segment_tts.get("provider") or "")
        timeline_duration = max(
            _safe_int(pipeline_state.get("video_duration") or pipeline_state.get("source_duration"), 0),
            int(max((float(item.get("end") or 0) for item in output_segments), default=0)),
        )
        raw_audio_bytes, _timeline_detail = await _maybe_await(build_timeline_audio(tts_chunks, timeline_duration))
        if not raw_audio_bytes:
            return {
                "ok": False,
                "status": "NO_AUDIO_BYTES",
                "error_code": "dub_audio_empty",
                "provider_called": True,
                "charged": False,
                "created_files": [],
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
            }

    wants_subtitle_video = output_type in {"burn", "both", "video_subtitle"}
    wants_final_video = _video_output_requested(mode, output_type, content_type)
    video_output = b""
    partial_result = False
    partial_reason = ""
    if _is_video_source(content_type):
        if audio_bytes and dub_mux_enabled and ffmpeg_ready():
            try:
                video_output, _render_detail = await _maybe_await(
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
        "raw_audio_bytes": raw_audio_bytes,
        "audio_bytes": audio_bytes,
        "video_output": video_output,
        "normalization_detail": normalization_detail,
        "selected_tts_voice_id": selected_tts_voice_id,
        "output_type": output_type,
        "provider_called": bool(prepared.get("asr_provider") or prepared.get("translation_provider") or tts_provider),
        "charged": False,
        "created_files": [],
        "error_code": "",
        "safe_public_message": "",
        "admin_debug_summary": "",
    }
