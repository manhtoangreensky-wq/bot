"""Shared public progress panel for long-running TOAN AAS products.

This module is deliberately UI-only: it renders safe customer copy and
button plans from already-known job status. It must not call providers,
create jobs, render files, or touch billing.
"""

from __future__ import annotations

import hashlib
import html
import re
from typing import Any


TERMINAL_STATES = {"delivered", "failed_no_charge", "failed_refunded", "needs_admin_review"}
VIDEO_PROGRESS_TYPES = {"video_trend", "script_to_video", "frame_video", "multiscene_video", "video_ai_real"}
PROGRESS_REFRESH_LABEL = "🔄 Cập nhật trạng thái"

PUBLIC_TECHNICAL_WORDS = (
    "provider",
    "api",
    "ffmpeg",
    "worker",
    "debug",
    "payload",
    "adapter",
    "blackbox",
    "local_worker",
    "runtimeerror",
    "traceback",
    "component",
    "test",
    "canary",
    "admin test",
)

TECHNICAL_WORD_RE = re.compile("|".join(re.escape(word) for word in PUBLIC_TECHNICAL_WORDS), re.IGNORECASE)


def _stage(key: str, label: str, status: str, percent: int) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "percent": max(0, min(100, int(percent or 0))),
    }


def _video_steps() -> list[dict[str, Any]]:
    return [
        _stage("received_request", "Nhận yêu cầu", "Đã nhận yêu cầu", 5),
        _stage("preparing_content", "Chuẩn bị nội dung", "Đang chuẩn bị nội dung", 20),
        _stage("preparing_assets", "Chuẩn bị tài nguyên", "Đang chuẩn bị tài nguyên", 35),
        _stage("generating_video", "Tạo video", "Đang tạo video", 60),
        _stage("post_processing", "Ghép hậu kỳ", "Đang ghép hậu kỳ", 75),
        _stage("validating_output", "Kiểm tra file", "Đang kiểm tra file", 85),
        _stage("delivering", "Gửi kết quả", "Đang gửi kết quả", 95),
        _stage("delivered", "Hoàn tất", "Đã gửi kết quả", 100),
    ]


def _music_song_steps() -> list[dict[str, Any]]:
    return [
        _stage("received_request", "Nhận yêu cầu", "Đã nhận yêu cầu tạo nhạc", 5),
        _stage("preparing_lyrics", "Chuẩn bị lời bài hát", "Đang chuẩn bị lời bài hát", 20),
        _stage("preparing_style", "Chuẩn bị phong cách", "Đang chuẩn bị phong cách", 35),
        _stage("generating_song", "Tạo bài hát", "Đang tạo bài hát", 65),
        _stage("validating_audio", "Kiểm tra file nhạc", "Đang kiểm tra file nhạc", 85),
        _stage("delivering", "Gửi kết quả", "Đang gửi kết quả", 95),
        _stage("delivered", "Hoàn tất", "Đã gửi kết quả", 100),
    ]


PRODUCT_PROGRESS_SPECS: dict[str, dict[str, Any]] = {
    "music_bg": {
        "title": "🎵 TOAN AAS đang tạo nhạc nền",
        "send_label": "📥 Tạo nhạc khác",
        "send_callback": "music_quick|showroom|ai_music",
        "back_label": "⬅️ Studio nhạc",
        "back_callback": "music_quick|showroom|music_hub",
        "steps": [
            _stage("received_request", "Nhận yêu cầu", "Đã nhận yêu cầu tạo nhạc", 5),
            _stage("preparing_prompt", "Chuẩn bị nội dung nhạc", "Đang chuẩn bị nội dung nhạc", 20),
            _stage("preparing_style", "Chuẩn bị phong cách", "Đang chuẩn bị phong cách", 35),
            _stage("generating_music", "Tạo nhạc nền", "Đang tạo nhạc nền", 65),
            _stage("validating_audio", "Kiểm tra file nhạc", "Đang kiểm tra file nhạc", 85),
            _stage("delivering", "Gửi kết quả", "Đang gửi kết quả", 95),
            _stage("delivered", "Hoàn tất", "Đã gửi kết quả", 100),
        ],
    },
    "music_song": {
        "title": "🎙 TOAN AAS đang tạo bài hát",
        "send_label": "📥 Tạo bài hát khác",
        "send_callback": "music_quick|showroom|ai_music",
        "back_label": "⬅️ Studio nhạc",
        "back_callback": "music_quick|showroom|music_hub",
        "steps": _music_song_steps(),
    },
    "video_trend": {
        "title": "🎬 TOAN AAS đang xử lý video trend",
        "send_label": "📤 Gửi yêu cầu khác",
        "send_callback": "trendg|start",
        "back_label": "⬅️ Menu video",
        "back_callback": "menu|main_video",
        "steps": _video_steps(),
    },
    "script_to_video": {
        "title": "🎬 TOAN AAS đang dựng video từ kịch bản",
        "send_label": "📤 Gửi kịch bản khác",
        "send_callback": "vproduct|start_script_to_video",
        "back_label": "⬅️ Menu video",
        "back_callback": "menu|main_video",
        "steps": _video_steps(),
    },
    "frame_video": {
        "title": "🎞 TOAN AAS đang ghép ảnh thành video",
        "send_label": "📤 Gửi ảnh khác",
        "send_callback": "framevideo|start",
        "back_label": "⬅️ Menu video",
        "back_callback": "menu|main_video",
        "steps": _video_steps(),
    },
    "multiscene_video": {
        "title": "🎬 TOAN AAS đang dựng video nhiều cảnh",
        "send_label": "📤 Gửi yêu cầu khác",
        "send_callback": "vproduct|b14_start",
        "back_label": "⬅️ Menu video",
        "back_callback": "menu|main_video",
        "steps": _video_steps(),
    },
    "video_ai_real": {
        "title": "🎥 TOAN AAS đang tạo video AI",
        "send_label": "📤 Gửi yêu cầu khác",
        "send_callback": "vproduct|start",
        "back_label": "⬅️ Menu video",
        "back_callback": "menu|main_video",
        "steps": _video_steps(),
    },
    "addon_voice": {
        "title": "🎙 TOAN AAS đang tạo giọng đọc cho video",
        "send_label": "📤 Gửi nội dung khác",
        "send_callback": "vfinal|voice",
        "back_label": "⬅️ Video",
        "back_callback": "menu|main_video",
        "steps": [
            _stage("received_request", "Nhận nội dung", "Đã nhận nội dung", 5),
            _stage("preparing_voice", "Chuẩn bị giọng đọc", "Đang chuẩn bị giọng đọc", 30),
            _stage("rendering_voice", "Tạo audio", "Đang tạo audio", 70),
            _stage("validating_audio", "Kiểm tra file audio", "Đang kiểm tra file audio", 88),
            _stage("delivering", "Gửi kết quả", "Đang gửi kết quả", 95),
            _stage("delivered", "Hoàn tất", "Đã gửi kết quả", 100),
        ],
    },
    "addon_music": {
        "title": "🎵 TOAN AAS đang tạo nhạc cho video",
        "send_label": "📤 Gửi yêu cầu khác",
        "send_callback": "vfinal|music",
        "back_label": "⬅️ Video",
        "back_callback": "menu|main_video",
        "steps": [
            _stage("received_request", "Nhận yêu cầu", "Đã nhận yêu cầu", 5),
            _stage("preparing_music", "Chuẩn bị nhạc", "Đang chuẩn bị nhạc", 30),
            _stage("rendering_music", "Tạo nhạc", "Đang tạo nhạc", 70),
            _stage("validating_audio", "Kiểm tra file nhạc", "Đang kiểm tra file nhạc", 88),
            _stage("delivering", "Gửi kết quả", "Đang gửi kết quả", 95),
            _stage("delivered", "Hoàn tất", "Đã gửi kết quả", 100),
        ],
    },
    "addon_subtitle": {
        "title": "💬 TOAN AAS đang tạo phụ đề cho video",
        "send_label": "📤 Gửi video khác",
        "send_callback": "videodub|source_upload",
        "back_label": "⬅️ Video",
        "back_callback": "menu|main_video",
        "steps": [
            _stage("received_file", "Nhận video", "Đã nhận video", 5),
            _stage("extracting_audio", "Tách âm thanh", "Đang tách âm thanh", 20),
            _stage("transcribing", "Nhận diện lời thoại", "Đang nhận diện lời thoại", 40),
            _stage("creating_subtitles", "Tạo phụ đề", "Đang tạo phụ đề", 70),
            _stage("validating_video", "Kiểm tra file", "Đang kiểm tra file", 88),
            _stage("delivering", "Gửi kết quả", "Đang gửi kết quả", 95),
            _stage("delivered", "Hoàn tất", "Đã gửi kết quả", 100),
        ],
    },
    "subdub": {
        "title": "🎬 TOAN AAS đang xử lý video",
        "send_label": "📤 Gửi video khác",
        "send_callback": "videodub|source_upload",
        "back_label": "⬅️ Phụ đề + Lồng tiếng",
        "back_callback": "videodub|type|subtitle_plus_dub",
        "steps": [
            _stage("received_file", "Nhận video", "Đã nhận video", 5),
            _stage("extracting_audio", "Tách âm thanh", "Đang tách âm thanh", 20),
            _stage("transcribing", "Nhận diện lời thoại", "Đang nhận diện lời thoại", 35),
            _stage("translating", "Dịch nội dung", "Đang dịch nội dung", 50),
            _stage("generating_voice", "Tạo phụ đề / Tạo giọng lồng tiếng", "Đang tạo phụ đề / tạo giọng lồng tiếng", 65),
            _stage("muxing_video", "Ghép video", "Đang ghép video", 80),
            _stage("validating_output", "Kiểm tra file", "Đang kiểm tra file", 90),
            _stage("delivering", "Gửi kết quả", "Đang gửi kết quả", 95),
            _stage("delivered", "Hoàn tất", "Đã gửi kết quả", 100),
        ],
    },
}


PRODUCT_PROGRESS_ALIASES = {
    "music": "music_bg",
    "music_suno": "music_bg",
    "background_music": "music_bg",
    "music_background": "music_bg",
    "instrumental": "music_bg",
    "song": "music_song",
    "lyrics_song": "music_song",
    "video_b14": "multiscene_video",
    "b14": "multiscene_video",
    "image_to_video": "frame_video",
    "frame": "frame_video",
    "trend_video": "video_trend",
    "real_video": "video_ai_real",
    "video_real": "video_ai_real",
    "video_dub": "subdub",
    "subtitle_dub": "subdub",
    "addon_logo": "addon_logo",
}

STAGE_ALIASES = {
    "music_bg": {
        "submitted": "received_request",
        "queued": "received_request",
        "processing": "generating_music",
        "running": "generating_music",
        "downloading": "validating_audio",
        "completed": "delivered",
        "success": "delivered",
    },
    "music_song": {
        "submitted": "received_request",
        "queued": "received_request",
        "processing": "generating_song",
        "running": "generating_song",
        "downloading": "validating_audio",
        "completed": "delivered",
        "success": "delivered",
    },
    "frame_video": {
        "queued": "received_request",
        "received_images": "received_request",
        "preparing_layout": "preparing_content",
        "rendering_video": "generating_video",
        "validating_video": "validating_output",
        "processing": "generating_video",
        "running": "generating_video",
        "succeeded": "delivered",
        "success": "delivered",
        "completed": "delivered",
    },
    "multiscene_video": {
        "queued": "received_request",
        "queued_for_worker": "received_request",
        "building_script": "preparing_content",
        "planning_scenes": "preparing_content",
        "preparing_visuals": "preparing_assets",
        "rendering_video": "generating_video",
        "rendering_scenes": "generating_video",
        "validating_video": "validating_output",
        "processing": "generating_video",
        "running": "generating_video",
        "post_processing": "post_processing",
        "completed": "delivered",
        "success": "delivered",
    },
    "video_trend": {
        "queued": "received_request",
        "queued_for_worker": "received_request",
        "building_script": "preparing_content",
        "planning_scenes": "preparing_content",
        "preparing_visuals": "preparing_assets",
        "rendering_video": "generating_video",
        "rendering_scenes": "generating_video",
        "validating_video": "validating_output",
        "processing": "generating_video",
        "running": "generating_video",
        "post_processing": "post_processing",
        "completed": "delivered",
        "success": "delivered",
    },
    "script_to_video": {
        "queued": "received_request",
        "queued_for_worker": "received_request",
        "received_script": "received_request",
        "planning_scenes": "preparing_content",
        "preparing_visuals": "preparing_assets",
        "rendering_scenes": "generating_video",
        "rendering_video": "generating_video",
        "validating_video": "validating_output",
        "processing": "generating_video",
        "running": "generating_video",
        "post_processing": "post_processing",
        "completed": "delivered",
        "success": "delivered",
    },
    "video_ai_real": {
        "queued": "received_request",
        "queued_for_worker": "received_request",
        "preparing_scene": "preparing_content",
        "preparing_visuals": "preparing_assets",
        "rendering_video": "generating_video",
        "rendering_scenes": "generating_video",
        "validating_video": "validating_output",
        "processing": "generating_video",
        "running": "generating_video",
        "post_processing": "post_processing",
        "completed": "delivered",
        "success": "delivered",
    },
    "subdub": {
        "received": "received_file",
        "received_video": "received_file",
        "saved_input": "received_file",
        "extracting": "extracting_audio",
        "translate": "translating",
        "generating_subtitle": "generating_voice",
        "creating_subtitle": "generating_voice",
        "tts": "generating_voice",
        "muxing": "muxing_video",
        "rendering": "muxing_video",
        "validating": "validating_output",
        "checking_file": "validating_output",
        "output": "validating_output",
        "processing": "generating_voice",
        "running": "generating_voice",
        "completed": "delivered",
        "success": "delivered",
    },
}


def normalize_product_type(product_type: str = "") -> str:
    token = re.sub(r"[^A-Za-z0-9_:-]+", "", str(product_type or "").strip().lower())
    token = token.replace("-", "_").replace(":", "_")
    canonical = PRODUCT_PROGRESS_ALIASES.get(token, token)
    return canonical if canonical in PRODUCT_PROGRESS_SPECS else "multiscene_video"


def product_progress_spec(product_type: str = "") -> dict[str, Any]:
    return PRODUCT_PROGRESS_SPECS[normalize_product_type(product_type)]


def product_progress_stage(product_type: str = "", stage: str = "") -> dict[str, Any]:
    canonical = normalize_product_type(product_type)
    spec = product_progress_spec(canonical)
    token = str(stage or "").strip().lower().replace("-", "_")
    token = STAGE_ALIASES.get(canonical, {}).get(token, token)
    steps = list(spec.get("steps") or [])
    for item in steps:
        if item.get("key") == token:
            return dict(item)
    if steps:
        return dict(steps[0])
    return _stage("received_request", "Nhận yêu cầu", "Đã nhận yêu cầu", 5)


def canonical_music_job_id(job_id: str = "") -> str:
    raw = str(job_id or "").strip().upper()
    if raw.startswith("#"):
        raw = raw[1:].strip()
    raw = re.sub(r"[^A-Z0-9-]+", "", raw)
    if raw.startswith("MUS-"):
        raw = "MUS" + raw[4:]
    if not raw.startswith("MUS") or raw.startswith("MUSIC"):
        return ""
    payload = re.sub(r"[^A-Z0-9]+", "", raw[3:])
    if not payload:
        return ""
    return "MUS" + payload


def product_progress_public_job_code(job_id: str = "") -> str:
    music_id = canonical_music_job_id(job_id)
    if music_id:
        return "#" + music_id
    raw = re.sub(r"[^A-Za-z0-9]+", "", str(job_id or "")).upper()
    if not raw:
        raw = hashlib.sha256(b"TOAN_AAS").hexdigest()[:8].upper()
    return "#" + raw[:10]


def product_progress_safe_callback_value(value: str = "", limit: int = 28) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "", str(value or ""))[: max(1, int(limit or 28))]


def product_progress_safe_callback_data(value: str = "", limit: int = 54) -> str:
    return re.sub(r"[^A-Za-z0-9_.:|:-]+", "", str(value or ""))[: max(1, int(limit or 54))]


def product_progress_update_callback(product_type: str = "", job_id: str = "") -> str:
    safe_type = product_progress_safe_callback_value(normalize_product_type(product_type), 20)
    safe_job = canonical_music_job_id(job_id) or product_progress_safe_callback_value(job_id, 28) or "latest"
    callback = f"progress|status|{safe_type}|{safe_job}"
    return callback[:64]


def public_copy_has_technical_words(text: str = "") -> bool:
    return bool(TECHNICAL_WORD_RE.search(str(text or "")))


def sanitize_public_copy(text: str = "", fallback: str = "") -> str:
    value = re.sub(r"\s+", " ", str(text or "").strip())
    if not value:
        value = str(fallback or "").strip()
    if not value or public_copy_has_technical_words(value):
        return str(fallback or "TOAN AAS đang xử lý. Anh/chị vui lòng kiểm tra lại sau.").strip()
    return value


def product_progress_terminal_label(terminal_state: str = "") -> str:
    state = str(terminal_state or "").strip().lower()
    if state == "delivered":
        return "Đã gửi kết quả"
    if state == "failed_refunded":
        return "Chưa xử lý được lúc này, TOAN AAS đã hoàn Xu nếu có phát sinh"
    if state == "needs_admin_review":
        return "Đang cần kiểm tra thêm, TOAN AAS chưa trừ Xu mới"
    if state == "failed_no_charge":
        return "Chưa xử lý được lúc này, TOAN AAS chưa trừ Xu"
    return ""


def product_progress_percent(product_type: str = "", stage: str = "", percent: int | None = None, terminal_state: str = "") -> int:
    state = str(terminal_state or "").strip().lower()
    if state == "delivered":
        return 100
    stage_percent = int(product_progress_stage(product_type, stage).get("percent") or 0)
    if percent is not None:
        try:
            requested = max(0, min(100, int(percent)))
            if state in {"failed_no_charge", "failed_refunded", "needs_admin_review"}:
                return min(requested, max(stage_percent, 5))
            return min(requested, stage_percent)
        except Exception:
            pass
    return stage_percent


def product_progress_single_terminal_state(current_state: str = "", next_state: str = "") -> str:
    current = str(current_state or "").strip().lower()
    upcoming = str(next_state or "").strip().lower()
    if current in TERMINAL_STATES:
        return current
    return upcoming if upcoming in TERMINAL_STATES else current


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "ok", "done", "ready", "completed", "success", "sent"}


def _as_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(round(float(value)))
    except Exception:
        return int(fallback or 0)


def _first_text(job: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = job.get(key)
        if value not in (None, ""):
            text = str(value).strip()
            if text:
                return text
    return ""


def _positive_int(job: dict[str, Any], *keys: str) -> int:
    for key in keys:
        try:
            value = int(round(float(job.get(key) or 0)))
        except Exception:
            value = 0
        if value > 0:
            return value
    return 0


def music_progress_lifecycle(product_type: str = "", job: dict[str, Any] | None = None) -> dict[str, Any]:
    job = dict(job or {})
    canonical = normalize_product_type(product_type)
    status = str(job.get("status") or job.get("music_status") or "").strip().lower()
    output_bytes = _positive_int(job, "output_bytes", "music_result_size_bytes", "music_output_size_bytes")
    if output_bytes <= 0:
        output_bytes = _positive_int(job, "selected_artifact_bytes", "delivered_artifact_bytes", "final_audio_bytes")
    duration = _positive_int(
        job,
        "artifact_duration",
        "artifact_duration_seconds",
        "music_artifact_duration",
        "selected_artifact_duration",
        "delivered_duration_seconds",
        "delivered_track_duration_seconds",
        "music_result_duration_seconds",
        "music_output_duration_seconds",
        "duration_seconds",
        "audio_duration_seconds",
    )
    provider_task_id = _first_text(job, "provider_task_id", "provider_job_id", "music_task_id")
    has_delivery = bool(
        job.get("sent_full_at")
        or job.get("delivered_at")
        or job.get("music_delivered_at")
        or job.get("music_result_delivered_at")
        or job.get("music_delivery_message_id")
        or job.get("delivery_message_id")
        or job.get("output_file_id")
        or job.get("music_output_file_id")
        or job.get("delivery_succeeded")
        or job.get("telegram_delivery_confirmed")
        or job.get("delivery_confirmed")
    )
    style_prepared = bool(
        _as_bool(job.get("style_prepared"))
        or _as_bool(job.get("music_style_prepared"))
        or _as_bool(job.get("prompt_prepared"))
        or _as_bool(job.get("music_prompt_prepared"))
        or _first_text(
            job,
            "provider_style_prompt",
            "style_prompt",
            "selected_style_prompt",
            "music_selected_style_prompt",
            "safe_prompt",
            "prompt_summary",
            "description",
            "genre",
            "mood",
        )
    )
    lyrics_prepared = bool(
        _as_bool(job.get("lyrics_prepared"))
        or _as_bool(job.get("music_lyrics_prepared"))
        or _first_text(
            job,
            "provider_lyrics",
            "lyrics",
            "song_lyrics",
            "lyrics_text",
            "music_selected_lyrics_prompt",
        )
    )
    provider_submit_called = bool(
        _as_bool(job.get("provider_submit_called"))
        or str(job.get("confirm_submit_phase") or "").strip().lower() in {"provider_submit_called", "provider_job_id_saved"}
        or provider_task_id
    )
    artifact_metadata_ready = bool(
        _first_text(
            job,
            "output_url",
            "music_output_url",
            "result_url",
            "download_url",
            "file_url",
            "audio_url",
            "music_result_url",
            "music_artifact_url",
            "selected_artifact_url",
            "output_path",
            "music_result_path",
            "local_path",
            "storage_ref",
            "vault_id",
            "music_vault_id",
            "music_artifact_id",
            "selected_artifact_id",
            "selected_artifact_hash",
            "music_artifact_hash",
        )
        or str(job.get("artifact_state") or job.get("music_artifact_state") or "").strip().lower() in {"metadata_ready", "materializing", "ready"}
    )
    provider_completed = bool(
        _as_bool(job.get("provider_completed"))
        or _as_bool(job.get("music_provider_completed"))
        or status in {"completed", "complete", "success", "succeeded", "done", "finished", "downloading", "delivered"}
        or output_bytes > 0
    )
    audio_validation_flag = bool(
        _as_bool(job.get("artifact_validated"))
        or _as_bool(job.get("audio_validated"))
        or _as_bool(job.get("music_audio_validated"))
    )
    audio_validation_explicit = any(key in job for key in ("artifact_validated", "audio_validated", "music_audio_validated"))
    audio_validated = bool(
        has_delivery
        or (output_bytes > 0 and duration > 0 and audio_validation_flag)
    )
    artifact_ready = bool(audio_validated and output_bytes > 0 and duration > 0)
    completed_steps: list[str] = []
    if job:
        completed_steps.append("received_request")
    if canonical == "music_song":
        if lyrics_prepared:
            completed_steps.append("preparing_lyrics")
        if style_prepared:
            completed_steps.append("preparing_style")
    else:
        if style_prepared:
            completed_steps.append("preparing_prompt")
    if provider_completed:
        completed_steps.append("generating_song" if canonical == "music_song" else "generating_music")
    if audio_validated:
        completed_steps.append("validating_audio")
    if has_delivery:
        completed_steps.append("delivering")
    return {
        "lyrics_prepared": lyrics_prepared,
        "style_prepared": style_prepared,
        "provider_submit_called": provider_submit_called,
        "provider_task_id": provider_task_id,
        "provider_completed": provider_completed,
        "artifact_metadata_ready": artifact_metadata_ready,
        "artifact_state": str(job.get("artifact_state") or job.get("music_artifact_state") or ("ready" if artifact_ready else "metadata_ready" if artifact_metadata_ready else "missing")),
        "artifact_ready": artifact_ready,
        "audio_validated": audio_validated,
        "delivery_confirmed": has_delivery,
        "output_bytes": output_bytes,
        "duration_seconds": duration,
        "completed_steps": completed_steps,
        "delivery_succeeded": has_delivery,
        "progress_step_source": "music_real_lifecycle",
    }


def job_has_final_artifact(job: dict[str, Any] | None = None) -> bool:
    current = dict(job or {})
    for key in (
        "final_video_file_id",
        "final_video_path",
        "output_file_id",
        "video_output_file_id",
        "music_output_file_id",
        "output_path",
        "final_mp4",
        "final_mp4_path",
        "dubbed_audio_path",
        "generated_audio_path",
        "storage_ref",
    ):
        if str(current.get(key) or "").strip():
            return True
    for key in ("final_mp4_exists", "dubbed_audio_exists", "output_validated"):
        if _as_bool(current.get(key)):
            return True
    for key in ("output_bytes", "uploaded_file_bytes", "music_result_size_bytes", "bytes"):
        try:
            if int(current.get(key) or 0) > 0:
                return True
        except Exception:
            continue
    return False


def render_product_progress_panel(
    product_type: str = "",
    job_id: str = "",
    current_stage: str = "",
    percent: int | None = None,
    terminal_state: str = "",
    public_note: str = "",
    lang: str = "vi",
    completed_steps: list[str] | tuple[str, ...] | set[str] | None = None,
    status_override: str = "",
) -> str:
    canonical = normalize_product_type(product_type)
    spec = product_progress_spec(canonical)
    terminal = str(terminal_state or "").strip().lower()
    if terminal == "delivered":
        current_stage = "delivered"
    elif str(current_stage or "").strip().lower().replace("-", "_") == "delivered":
        current_stage = "validating_output" if canonical in VIDEO_PROGRESS_TYPES or canonical == "subdub" else "validating_audio"
    stage = product_progress_stage(canonical, current_stage)
    progress = product_progress_percent(canonical, stage.get("key"), percent, terminal)
    status_text = product_progress_terminal_label(terminal) or sanitize_public_copy(status_override, "") or str(stage.get("status") or "")
    if canonical in {"music_bg", "music_song"} and terminal == "delivered":
        status_text = "Đã gửi file nhạc"
    status_text = sanitize_public_copy(status_text, "TOAN AAS đang xử lý.")
    note = sanitize_public_copy(public_note, "") if public_note else ""
    current_key = str(stage.get("key") or "")
    steps = list(spec.get("steps") or [])
    step_keys = [str(item.get("key") or "") for item in steps]
    current_index = step_keys.index(current_key) if current_key in step_keys else 0
    lines: list[str] = []
    if terminal == "delivered":
        lines = [f"✅ {item['label']}" for item in steps if item.get("key") != "delivered"]
    elif canonical in {"music_bg", "music_song"} and completed_steps is not None:
        completed = {str(item or "") for item in completed_steps}
        for item in steps:
            key = str(item.get("key") or "")
            if key == "delivered":
                continue
            if terminal in {"failed_no_charge", "failed_refunded", "needs_admin_review"} and key == current_key:
                marker = "⚠️" if terminal != "needs_admin_review" else "⏳"
            elif key in completed:
                marker = "✅"
            elif key == current_key:
                marker = "⏳"
            else:
                marker = "⬜"
            lines.append(f"{marker} {item['label']}")
    else:
        for index, item in enumerate(steps):
            item_key = str(item.get("key") or "")
            if item_key == "delivered":
                continue
            if terminal in {"failed_no_charge", "failed_refunded", "needs_admin_review"} and item_key == current_key:
                marker = "⚠️" if terminal != "needs_admin_review" else "⏳"
            elif index < current_index:
                marker = "✅"
            elif item_key == current_key:
                marker = "⏳"
            else:
                marker = "⬜"
            lines.append(f"{marker} {item['label']}")
    body = [
        f"{html.escape(str(spec.get('title') or 'TOAN AAS đang xử lý'))}",
        "",
        f"Trạng thái: {html.escape(status_text)}",
        f"Tiến độ: {progress}%",
        f"Mã xử lý: <code>{html.escape(product_progress_public_job_code(job_id))}</code>",
        "",
        "Các bước:",
        *lines,
    ]
    if note:
        body.extend(["", html.escape(note)])
    if canonical in {"music_bg", "music_song"}:
        body.extend(["", "Anh/chị không cần bấm nhiều lần."])
    else:
        body.extend(["", "Vui lòng không bấm lại nhiều lần."])
    return "\n".join(body)


def product_progress_button_rows(
    product_type: str = "",
    job_id: str = "",
    *,
    lang: str = "vi",
    send_callback: str = "",
    back_callback: str = "",
) -> list[list[tuple[str, str]]]:
    spec = product_progress_spec(product_type)
    return [
        [
            (PROGRESS_REFRESH_LABEL, product_progress_update_callback(product_type, job_id)),
            (str(spec.get("send_label") or "📤 Gửi file khác"), product_progress_safe_callback_data(send_callback or spec.get("send_callback") or "menu|main", 54)),
        ],
        [
            (str(spec.get("back_label") or "⬅️ Quay lại"), product_progress_safe_callback_data(back_callback or spec.get("back_callback") or "menu|main", 54)),
            ("🏠 Menu chính", "menu|main"),
        ],
    ]


def addon_config_saved_text(lang: str = "vi") -> str:
    return "✅ Đã lưu cấu hình."


def product_progress_stage_from_job(product_type: str = "", job: dict[str, Any] | None = None) -> dict[str, Any]:
    job = dict(job or {})
    canonical = normalize_product_type(product_type)
    status = str(job.get("status") or job.get("music_status") or "").strip().lower()
    progress = job.get("progress_percent")
    output_bytes = int(job.get("output_bytes") or job.get("music_result_size_bytes") or 0)
    has_final_artifact = job_has_final_artifact(job)
    provider_task_id = str(job.get("provider_task_id") or job.get("provider_job_id") or "").strip()
    has_delivery = bool(
        job.get("sent_full_at")
        or job.get("delivered_at")
        or job.get("music_delivered_at")
        or job.get("music_result_delivered_at")
        or job.get("output_file_id")
        or job.get("music_output_file_id")
    )
    music_artifact_waiting = bool(
        canonical in {"music_bg", "music_song"}
        and not bool(job.get("terminal_after_wait_exhausted"))
        and (
            job.get("artifact_waiting")
            or job.get("music_artifact_waiting")
            or str(job.get("final_audio_download_status") or "").strip().upper() == "PENDING"
            or str(job.get("artifact_materialization_status") or "").strip().lower() in {"waiting_for_provider_audio", "waiting"}
            or str(job.get("materialization_status") or "").strip().lower() in {"waiting_for_provider_audio", "waiting"}
            or str(job.get("lifecycle_status") or "").strip().lower() == "artifact_waiting"
            or any(
                str(job.get(key) or "").strip().lower() == "artifact_not_ready"
                for key in (
                    "primary_blocker",
                    "artifact_blocker",
                    "auto_delivery_blocker",
                    "artifact_download_error_category",
                    "download_error_category",
                    "last_download_error_category",
                    "error_category",
                )
            )
        )
    )
    terminal = ""
    explicit_terminal = str(job.get("terminal_state") or job.get("music_terminal_state") or "").strip().lower()
    if explicit_terminal in TERMINAL_STATES and not music_artifact_waiting:
        terminal = explicit_terminal
    elif canonical in {"music_bg", "music_song"} and status in {"completed", "complete", "success", "succeeded"} and output_bytes <= 0 and not has_delivery and not music_artifact_waiting:
        terminal = "failed_no_charge"
        status = "failed"
        progress = max(85, int(progress or 85))
    elif canonical in {"music_bg", "music_song"} and status in {"completed", "complete", "success", "succeeded"} and output_bytes > 0 and not has_delivery:
        status = "downloading"
        progress = min(85, int(progress or 85))
    elif canonical in {"music_bg", "music_song"} and not provider_task_id and output_bytes <= 0 and (
        bool(job.get("provider"))
        or bool(re.match(r"^MUS(?!IC)", str(job.get("internal_job_id") or job.get("job_id") or "").upper()))
        or str(job.get("error_category") or "") == "provider_job_missing"
    ) and status in {"submitted", "queued", "processing", "running", "generating", "downloading"}:
        terminal = "failed_no_charge"
        status = "failed"
        progress = max(85, int(progress or 85))
    elif canonical in VIDEO_PROGRESS_TYPES and status in {"completed", "complete", "success", "succeeded", "delivered"} and not has_final_artifact:
        terminal = "failed_no_charge"
        status = "failed"
        progress = min(85, int(progress or 85))
    elif canonical in VIDEO_PROGRESS_TYPES and str(job.get("visual_classification") or job.get("final_classification") or "").strip().lower() in {"partial_simple_video", "failed_no_real_visual"}:
        terminal = "failed_no_charge"
        status = "failed"
        progress = min(85, int(progress or 85))
    elif status in {"completed", "complete", "success", "succeeded", "delivered"}:
        terminal = "delivered"
    elif any(token in status for token in ("fail", "error", "cancel")):
        terminal = "failed_no_charge"
    if canonical in {"music_bg", "music_song"}:
        lifecycle = music_progress_lifecycle(canonical, job)
        completed_steps = list(lifecycle.get("completed_steps") or [])
        status_text = ""
        if terminal == "delivered":
            stage_key = "delivered"
            progress = 100
            completed_steps = [
                str(item.get("key") or "")
                for item in product_progress_spec(canonical).get("steps") or []
                if item.get("key") != "delivered"
            ]
        elif terminal:
            stage_key = str(job.get("stage") or job.get("current_stage") or "")
            if not stage_key:
                if not lifecycle.get("provider_task_id"):
                    stage_key = "received_request"
                elif lifecycle.get("provider_completed"):
                    stage_key = "validating_audio"
                else:
                    stage_key = "generating_song" if canonical == "music_song" else "generating_music"
            if progress is None:
                progress = int(product_progress_stage(canonical, stage_key).get("percent") or 5)
            if lifecycle.get("provider_completed") and not lifecycle.get("audio_validated"):
                status_text = "Chưa tải được file nhạc. Hệ thống chưa trừ Xu."
                progress = max(85, int(progress or 85))
        elif music_artifact_waiting:
            stage_key = "validating_audio"
            progress = max(80, min(90, int(progress if progress is not None else 85)))
            status_text = "Đang kiểm tra file nhạc"
        elif lifecycle.get("audio_validated"):
            stage_key = "delivering"
            progress = max(90, min(95, int(progress if progress is not None else 95)))
        elif lifecycle.get("artifact_ready"):
            stage_key = "validating_audio"
            progress = max(85, min(90, int(progress if progress is not None else 85)))
        elif lifecycle.get("provider_completed"):
            stage_key = "validating_audio"
            progress = max(80, min(90, int(progress if progress is not None else 85)))
            status_text = "Đang tải file nhạc"
        elif lifecycle.get("provider_task_id") or lifecycle.get("provider_submit_called"):
            stage_key = "generating_song" if canonical == "music_song" else "generating_music"
            if progress is None:
                progress = int(product_progress_stage(canonical, stage_key).get("percent") or 60)
        elif status in {"submitted", "queued", "processing", "running", "generating"}:
            stage_key = "generating_song" if canonical == "music_song" else "generating_music"
            if progress is None:
                progress = int(product_progress_stage(canonical, stage_key).get("percent") or 60)
        elif canonical == "music_song" and lifecycle.get("style_prepared"):
            stage_key = "preparing_style"
            progress = int(product_progress_stage(canonical, stage_key).get("percent") or 35)
        elif canonical == "music_song" and lifecycle.get("lyrics_prepared"):
            stage_key = "preparing_lyrics"
            progress = int(product_progress_stage(canonical, stage_key).get("percent") or 20)
        elif canonical == "music_bg" and lifecycle.get("style_prepared"):
            stage_key = "preparing_prompt"
            progress = int(product_progress_stage(canonical, stage_key).get("percent") or 20)
        else:
            stage_key = "received_request"
            progress = int(product_progress_stage(canonical, stage_key).get("percent") or 5)
        stage = product_progress_stage(canonical, stage_key)
        return {
            "product_type": canonical,
            "current_stage": str(stage.get("key") or stage_key),
            "percent": product_progress_percent(canonical, str(stage.get("key") or stage_key), progress if progress is not None else None, terminal),
            "terminal_state": terminal,
            "completed_steps": completed_steps,
            "music_lifecycle": lifecycle,
            "status_text": status_text,
        }
    if canonical == "subdub":
        stage_key = str(
            job.get("lifecycle_state")
            or job.get("progress_stage")
            or job.get("stage")
            or job.get("current_stage")
            or status
            or "received_file"
        ).strip().lower().replace("-", "_")
        stage_key = STAGE_ALIASES.get(canonical, {}).get(stage_key, stage_key)
        if terminal == "delivered":
            stage_key = "delivered"
            progress = 100
            completed_steps = [
                str(item.get("key") or "")
                for item in product_progress_spec(canonical).get("steps") or []
                if item.get("key") != "delivered"
            ]
            status_text = "Đã gửi kết quả"
        elif terminal in {"failed_no_charge", "failed_refunded", "needs_admin_review"}:
            if stage_key in {"delivered", "success", "completed", "failed", "failed_no_charge", "failed_refunded", "needs_admin_review"}:
                stage_key = "validating_output"
            progress = max(5, min(95, _as_int(progress, int(product_progress_stage(canonical, stage_key).get("percent") or 90))))
            completed_steps = list(job.get("completed_steps") or [])
            status_text = "Chưa xử lý được lúc này, TOAN AAS chưa trừ Xu."
        else:
            stage = product_progress_stage(canonical, stage_key)
            stage_key = str(stage.get("key") or stage_key)
            progress = max(5, min(95, _as_int(progress, int(stage.get("percent") or 5))))
            completed_steps = list(job.get("completed_steps") or [])
            status_text = "TOAN AAS đang xử lý, anh/chị kiểm tra lại sau." if status in {"running", "processing", "queued", "submitted"} else ""
        stage = product_progress_stage(canonical, stage_key)
        return {
            "product_type": canonical,
            "current_stage": str(stage.get("key") or stage_key),
            "percent": product_progress_percent(canonical, str(stage.get("key") or stage_key), progress if progress is not None else None, terminal),
            "terminal_state": terminal,
            "completed_steps": completed_steps,
            "status_text": status_text,
        }
    stage_key = STAGE_ALIASES.get(canonical, {}).get(status, "")
    if not stage_key:
        if canonical in {"music_bg"}:
            stage_key = "generating_music" if status else "received_request"
        elif canonical in {"music_song"}:
            stage_key = "generating_song" if status else "received_request"
        elif canonical == "subdub":
            stage_key = "generating_voice" if status else "received_file"
        elif canonical in VIDEO_PROGRESS_TYPES:
            stage_key = "generating_video" if status else "received_request"
        else:
            stage_key = str(job.get("stage") or job.get("current_stage") or "received_request")
    if terminal in {"failed_no_charge", "failed_refunded", "needs_admin_review"} and canonical in {"music_bg", "music_song"}:
        stage_key = "validating_audio"
    stage = product_progress_stage(canonical, str(job.get("stage") or job.get("current_stage") or stage_key))
    return {
        "product_type": canonical,
        "current_stage": str(stage.get("key") or stage_key),
        "percent": product_progress_percent(canonical, str(stage.get("key") or stage_key), progress if progress is not None else None, terminal),
        "terminal_state": terminal,
    }


def product_progress_debug_payload(product_type: str = "", job_id: str = "", job: dict[str, Any] | None = None) -> dict[str, Any]:
    state = product_progress_stage_from_job(product_type, job)
    return {
        "product_type": normalize_product_type(product_type),
        "job_code": product_progress_public_job_code(job_id),
        "current_stage": state.get("current_stage"),
        "percent": state.get("percent"),
        "terminal_state": state.get("terminal_state") or "",
        "completed_steps": list(state.get("completed_steps") or []),
        "update_callback": product_progress_update_callback(product_type, job_id),
    }


def product_progress_matrix_lines() -> list[str]:
    lines = ["📊 <b>TOAN AAS progress matrix</b>"]
    for product_type in sorted(PRODUCT_PROGRESS_SPECS):
        spec = PRODUCT_PROGRESS_SPECS[product_type]
        steps = ", ".join(str(item.get("key") or "") for item in spec.get("steps") or [])
        lines.append(f"• <code>{html.escape(product_type)}</code>: {html.escape(steps)}")
    return lines


def _labels_from_rows(rows: list[list[tuple[str, str]]]) -> list[str]:
    return [str(label or "") for row in rows for label, _callback in row]


def progress_panel_contract_audit_payload() -> dict[str, Any]:
    labels = []
    for product_type in PRODUCT_PROGRESS_SPECS:
        labels.extend(_labels_from_rows(product_progress_button_rows(product_type, "audit")))
    forbidden = ("Kiểm tra trạng thái", "Kiểm tra/gửi kết quả", "Kiểm tra/gửi")
    checks = [
        {"name": "refresh_label_locked", "ok": all(PROGRESS_REFRESH_LABEL in _labels_from_rows(product_progress_button_rows(product_type, "audit")) for product_type in PRODUCT_PROGRESS_SPECS)},
        {"name": "no_kiem_tra_trang_thai_label", "ok": not any("Kiểm tra trạng thái" in label for label in labels)},
        {"name": "no_check_send_result_label", "ok": not any(any(term in label for term in forbidden[1:]) for label in labels)},
        {"name": "video_no_95_without_final_artifact", "ok": product_progress_stage_from_job("multiscene_video", {"status": "processing", "progress_percent": 95}).get("percent", 100) < 95},
        {"name": "draft_not_final_delivered", "ok": product_progress_stage_from_job("multiscene_video", {"status": "completed", "visual_classification": "partial_simple_video"}).get("terminal_state") != "delivered"},
    ]
    return {"ok": all(item["ok"] for item in checks), "checks": checks, "labels": labels}


def product_progress_stage_audit_payload() -> dict[str, Any]:
    video_labels = [item["label"] for item in product_progress_spec("multiscene_video").get("steps", []) if item.get("key") != "delivered"]
    music_labels = [item["label"] for item in product_progress_spec("music_song").get("steps", []) if item.get("key") != "delivered"]
    subdub_labels = [item["label"] for item in product_progress_spec("subdub").get("steps", []) if item.get("key") != "delivered"]
    checks = [
        {"name": "video_stage_contract", "ok": video_labels == ["Nhận yêu cầu", "Chuẩn bị nội dung", "Chuẩn bị tài nguyên", "Tạo video", "Ghép hậu kỳ", "Kiểm tra file", "Gửi kết quả"]},
        {"name": "music_stage_contract", "ok": music_labels == ["Nhận yêu cầu", "Chuẩn bị lời bài hát", "Chuẩn bị phong cách", "Tạo bài hát", "Kiểm tra file nhạc", "Gửi kết quả"]},
        {"name": "subdub_stage_contract", "ok": subdub_labels == ["Nhận video", "Tách âm thanh", "Nhận diện lời thoại", "Dịch nội dung", "Tạo phụ đề / Tạo giọng lồng tiếng", "Ghép video", "Kiểm tra file", "Gửi kết quả"]},
    ]
    return {"ok": all(item["ok"] for item in checks), "checks": checks}


def video_progress_panel_audit_payload() -> dict[str, Any]:
    processing = render_product_progress_panel("multiscene_video", "VID1", "generating_video", percent=95)
    draft = render_product_progress_panel("multiscene_video", "VID2", "generating_video", terminal_state="failed_no_charge", public_note="Đã có bản nháp, chưa có video hoàn chỉnh. Bản này chưa trừ Xu.")
    checks = [
        {"name": "video_steps_not_green_before_real_state", "ok": "✅ Kiểm tra file" not in processing and "✅ Gửi kết quả" not in processing},
        {"name": "video_no_95_without_final_or_checking_artifact", "ok": "Tiến độ: 95%" not in processing},
        {"name": "video_draft_not_rendered_as_final", "ok": "Đã gửi kết quả" not in draft and "chưa có video hoàn chỉnh" in draft},
    ]
    return {"ok": all(item["ok"] for item in checks), "checks": checks, "sample": processing}


def music_progress_panel_audit_payload() -> dict[str, Any]:
    submitted = render_product_progress_panel("music_song", "MUS1", "preparing_style", percent=95)
    failed = product_progress_stage_from_job("music_song", {"status": "submitted", "progress_percent": 95, "provider": "suno", "output_bytes": 0})
    checks = [
        {"name": "music_steps_not_green_before_real_state", "ok": "✅ Tạo bài hát" not in submitted and "✅ Kiểm tra file nhạc" not in submitted and "✅ Gửi kết quả" not in submitted},
        {"name": "music_no_95_before_delivery", "ok": "Tiến độ: 95%" not in submitted},
        {"name": "music_missing_provider_job_fails_no_charge", "ok": failed.get("terminal_state") == "failed_no_charge"},
    ]
    return {"ok": all(item["ok"] for item in checks), "checks": checks, "sample": submitted}
