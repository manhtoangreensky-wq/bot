"""Shared public progress panel for long-running TOAN AAS products.

This module is deliberately UI-only: it renders safe customer copy and
button plans from already-known job status. It must not call providers,
create jobs, render files, or touch billing.
"""

from __future__ import annotations

import hashlib
import html
import re
import time
from datetime import datetime
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
        _stage("preparing_lyrics", "Chuẩn bị lời bài hát", "Đang chuẩn bị lời bài hát", 15),
        _stage("preparing_style", "Chuẩn bị phong cách", "Đang chuẩn bị phong cách", 25),
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
            _stage("preparing_prompt", "Chuẩn bị nội dung nhạc", "Đang chuẩn bị nội dung nhạc", 15),
            _stage("preparing_style", "Chuẩn bị phong cách", "Đang chuẩn bị phong cách", 25),
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
        "input_save": "received_file",
        "input_save_failed": "received_file",
        "received_file_failed": "received_file",
        "telegram_download_failed": "received_file",
        "large_telegram_download_unsupported": "received_file",
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
    canonical = normalize_product_type(product_type)
    stage_percent = int(product_progress_stage(product_type, stage).get("percent") or 0)
    if percent is not None:
        try:
            requested = max(0, min(100, int(percent)))
            if canonical in {"music_bg", "music_song"}:
                stage_key = str(stage or "").strip().lower().replace("-", "_")
                music_caps = {
                    "received_request": 5,
                    "preparing_lyrics": 25,
                    "preparing_prompt": 25,
                    "preparing_style": 35,
                    "generating_song": 75,
                    "generating_music": 75,
                    "validating_audio": 95,
                    "delivering": 99,
                }
                cap = int(music_caps.get(stage_key, max(stage_percent, 5)))
                if state in {"failed_no_charge", "failed_refunded", "needs_admin_review"}:
                    cap = max(cap, 95 if stage_key in {"validating_audio", "delivering"} else cap)
                return min(requested, cap)
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


def _music_raw_audio_url_present(job: dict[str, Any]) -> bool:
    if _first_text(
        job,
        "music_output_url",
        "output_url",
        "result_url",
        "download_url",
        "file_url",
        "audio_url",
        "stream_url",
        "stream_audio_url",
        "source_audio_url",
        "selected_artifact_url",
        "music_result_url",
        "music_artifact_url",
        "final_audio_url",
    ):
        return True
    for key in ("provider_result_candidates", "key4u_suno_fetch_candidate_paths", "provider_result_candidate_paths"):
        value = job.get(key)
        if isinstance(value, (list, tuple, set)) and len(value) > 0:
            return True
    return _positive_int(job, "provider_result_candidate_count", "provider_result_candidate_total_count") > 0


def _music_artifact_materialization_started(job: dict[str, Any]) -> bool:
    if bool(
        job.get("artifact_materialization_attempted")
        or job.get("artifact_materialization_started_at")
        or job.get("materialization_attempted")
        or job.get("artifact_download_attempted")
        or job.get("direct_audio_url_get_attempted")
        or job.get("provider_download_endpoint_attempted")
        or job.get("provider_proxy_attempted")
        or job.get("key4u_suno_fetch_attempted")
    ):
        return True
    if _positive_int(job, "download_attempt_count", "artifact_wait_attempt_count", "artifact_materialization_attempt_count") > 0:
        return True
    return bool(
        _first_text(
            job,
            "download_strategy_used",
            "artifact_materialization_status",
            "materialization_status",
            "final_audio_download_status",
        )
    )


def _music_previous_progress(job: dict[str, Any]) -> int:
    candidates = []
    for key in (
        "final_progress_after_reconcile",
        "final_progress",
        "progress_percent",
        "persisted_job_progress",
        "last_progress_percent",
        "last_meaningful_progress",
        "max_progress_percent",
        "registry_progress",
        "panel_progress_percent",
    ):
        try:
            value = int(round(float(job.get(key) or 0)))
        except Exception:
            value = 0
        if value > 0:
            candidates.append(value)
    return max(candidates or [0])


def _music_artifact_wait_attempts(job: dict[str, Any]) -> tuple[int, int]:
    attempt = _positive_int(job, "artifact_wait_attempt_count", "download_attempt_count", "artifact_materialization_attempt_count")
    max_attempts = _positive_int(job, "artifact_wait_max_attempts", "music_artifact_wait_max_attempts", "max_artifact_wait_attempts")
    return attempt, max_attempts


def _music_terminal_fail_allowed(job: dict[str, Any], lifecycle: dict[str, Any], terminal: str = "") -> bool:
    state = str(terminal or "").strip().lower()
    if state not in {"failed_no_charge", "failed_refunded", "needs_admin_review"}:
        return True
    blocker = str(
        job.get("primary_blocker")
        or job.get("artifact_blocker")
        or job.get("auto_delivery_blocker")
        or job.get("artifact_download_error_category")
        or job.get("download_error_category")
        or job.get("last_download_error_category")
        or job.get("error_category")
        or ""
    ).strip().lower()
    status = str(job.get("status") or job.get("music_status") or "").strip().lower()
    provider_status = str(job.get("provider_status") or job.get("last_provider_status") or "").strip().lower()
    wait_attempts, wait_max = _music_artifact_wait_attempts(job)
    wait_exhausted = bool(
        job.get("terminal_after_wait_exhausted")
        or job.get("artifact_wait_terminal_exhausted")
        or (wait_max > 0 and wait_attempts >= wait_max)
    )
    provider_failed = any(token in f"{status} {provider_status}" for token in ("fail", "error", "cancel", "rejected"))
    all_candidates_invalid = blocker in {
        "all_candidates_terminal_invalid",
        "all_candidates_invalid",
        "artifact_materialization_failed",
        "artifact_download_failed",
        "result_url_forbidden_access_denied",
        "audio_validation_failed",
        "scheduler_start_failed",
        "job_persist_failed",
        "provider_submit_failed",
    }
    provider_missing = bool(
        not lifecycle.get("provider_task_id")
        and (
            blocker == "provider_job_missing"
            or job.get("provider")
            or job.get("provider_name_internal")
            or (status in {"completed", "complete", "success", "succeeded"} and _positive_int(job, "output_bytes", "music_result_size_bytes", "music_output_size_bytes") <= 0)
        )
    )
    return bool(wait_exhausted or provider_failed or all_candidates_invalid or provider_missing)


def _music_reconcile_progress(
    canonical: str,
    job: dict[str, Any],
    lifecycle: dict[str, Any],
    stage_key: str,
    requested_progress: int,
    terminal: str,
    *,
    music_artifact_waiting: bool = False,
) -> dict[str, Any]:
    stage_key = str(stage_key or "received_request").strip().lower().replace("-", "_")
    previous_progress = _music_previous_progress(job)
    requested_progress = max(0, min(100, int(requested_progress or 0)))
    provider_completed = bool(lifecycle.get("provider_completed"))
    create_song_started = bool(lifecycle.get("create_song_started"))
    provider_status = str(job.get("status") or job.get("music_status") or "").strip().lower()
    raw_audio_url_present = _music_raw_audio_url_present(job)
    artifact_materialization_started = _music_artifact_materialization_started(job)
    artifact_waiting = bool(music_artifact_waiting or job.get("artifact_waiting") or job.get("music_artifact_waiting"))
    completed = {str(item or "").strip().lower() for item in (job.get("completed_steps") or lifecycle.get("completed_steps") or [])}
    generation_checkpoint_done = bool(completed & {"generating_song", "generating_music", "validating_audio", "delivering"})
    artifact_check_stage_allowed = bool(provider_completed or raw_audio_url_present or artifact_materialization_started or artifact_waiting or generation_checkpoint_done)
    terminal_fail_allowed = _music_terminal_fail_allowed(job, lifecycle, terminal)
    if artifact_waiting and not bool(job.get("terminal_after_wait_exhausted") or job.get("artifact_wait_terminal_exhausted")):
        terminal_fail_allowed = False
    progress_source = "stage_default"
    if previous_progress >= 95 and not lifecycle.get("audio_validated") and str(terminal or "").strip().lower() != "delivered":
        previous_progress = 0
    if previous_progress > 0:
        progress_source = "persisted_job_progress"
    if artifact_waiting:
        floor, cap = 80, 90
        progress_source = "artifact_waiting"
    elif lifecycle.get("audio_validated"):
        floor, cap = 95, 95
        progress_source = "audio_validated"
    elif stage_key == "delivering":
        floor, cap = 95, 99
        progress_source = "delivery_started"
    elif stage_key == "validating_audio" and artifact_check_stage_allowed:
        floor, cap = 80, 90
        progress_source = "artifact_check"
    elif provider_status == "submitting" and not lifecycle.get("provider_task_id"):
        floor, cap = 5, 25
        progress_source = "provider_submitting"
    elif create_song_started:
        if provider_status in {"generating"}:
            floor, cap = 65, 75
            progress_source = "provider_generating"
        elif provider_status in {"processing", "running", "in_progress"}:
            floor, cap = 50, 75
            progress_source = "provider_generating"
        else:
            floor, cap = 35, 75
            progress_source = "provider_accepted"
    elif stage_key in {"preparing_style"}:
        floor, cap = 25, 25
        progress_source = "style_prepared"
    elif stage_key in {"preparing_lyrics", "preparing_prompt"}:
        floor, cap = 15, 15
        progress_source = "lyrics_or_prompt_prepared"
    else:
        floor, cap = 5, 5
    final_progress = max(requested_progress, floor)
    if previous_progress > 0:
        final_progress = max(final_progress, previous_progress)
    final_progress = min(final_progress, cap)
    if str(terminal or "").strip().lower() == "delivered":
        final_progress = 100
        progress_source = "delivered"
    rollback_prevented = bool(previous_progress > requested_progress and final_progress >= min(previous_progress, cap))
    public_percent_reason = (
        "provider_processing"
        if create_song_started and provider_status in {"processing", "running", "in_progress"}
        else progress_source
    )
    return {
        "progress_monotonic_applied": True,
        "previous_progress": previous_progress,
        "requested_progress": requested_progress,
        "final_progress": final_progress,
        "final_progress_after_reconcile": final_progress,
        "progress_source": progress_source,
        "public_percent_reason": public_percent_reason,
        "progress_rollback_prevented": rollback_prevented,
        "create_song_started": create_song_started,
        "provider_completed": provider_completed,
        "raw_audio_url_present": raw_audio_url_present,
        "artifact_materialization_started": artifact_materialization_started,
        "artifact_waiting": artifact_waiting,
        "generation_checkpoint_done": generation_checkpoint_done,
        "artifact_check_stage_allowed": artifact_check_stage_allowed,
        "artifact_wait_attempt_count": _music_artifact_wait_attempts(job)[0],
        "artifact_wait_max_attempts": _music_artifact_wait_attempts(job)[1],
        "next_artifact_retry_at": str(job.get("next_artifact_retry_at") or ""),
        "artifact_wait_terminal_exhausted": bool(job.get("terminal_after_wait_exhausted") or job.get("artifact_wait_terminal_exhausted")),
        "terminal_fail_allowed": terminal_fail_allowed,
    }


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
    style_input_present = bool(
        _first_text(
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
    lyrics_input_present = bool(
        _first_text(
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
    stage_hint = str(job.get("current_stage") or job.get("stage") or job.get("progress_stage") or job.get("lifecycle_status") or "").strip().lower().replace("-", "_")
    provider_missing_failure_candidate = bool(
        not provider_task_id
        and output_bytes <= 0
        and status in {"submitted", "queued", "processing", "running", "generating", "downloading"}
        and (
            job.get("provider")
            or str(job.get("error_category") or "") == "provider_job_missing"
            or bool(re.match(r"^MUS(?!IC)", str(job.get("internal_job_id") or job.get("job_id") or "").upper()))
        )
    )
    create_song_started = bool(
        not provider_missing_failure_candidate
        and (
            _as_bool(job.get("create_song_started"))
            or provider_task_id
            or provider_completed
            or status in {"submitted", "queued", "processing", "running", "generating", "downloading", "delivered"}
        )
    )
    lyrics_prepared = bool(
        _as_bool(job.get("lyrics_prepared"))
        or _as_bool(job.get("music_lyrics_prepared"))
        or stage_hint in {"preparing_style", "generating_song", "generating_music", "validating_audio", "delivering", "delivered", "provider_submitted", "provider_completed"}
        or create_song_started
    )
    style_prepared = bool(
        _as_bool(job.get("style_prepared"))
        or _as_bool(job.get("music_style_prepared"))
        or _as_bool(job.get("prompt_prepared"))
        or _as_bool(job.get("music_prompt_prepared"))
        or stage_hint in {"generating_song", "generating_music", "validating_audio", "delivering", "delivered", "provider_submitted", "provider_completed"}
        or create_song_started
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
        "lyrics_input_present": lyrics_input_present,
        "style_input_present": style_input_present,
        "provider_submit_called": provider_submit_called,
        "provider_task_id": provider_task_id,
        "create_song_started": create_song_started,
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


def _video_human_elapsed(seconds: Any) -> str:
    total = max(0, _as_int(seconds, 0))
    minutes, secs = divmod(total, 60)
    if minutes:
        return f"{minutes} phút {secs:02d} giây"
    return f"{secs} giây"


def _video_epoch_from_value(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        numeric = float(value)
        if numeric > 0:
            return numeric
    except Exception:
        pass
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.timestamp()
        return parsed.timestamp()
    except Exception:
        return 0.0


def _video_scene_status_label(status: Any, clip_ready: bool = False) -> str:
    raw = str(status or "").strip().lower().replace("-", "_")
    if clip_ready or raw in {"done", "complete", "completed", "success", "clip_ready", "downloaded", "validated", "scene_clip_validated", "clip_downloaded"}:
        return "Đã xong"
    if raw in {"queued_waiting_for_slot", "scheduled_after_scene_1_progress"}:
        return "Đang chờ lượt"
    if raw in {
        "queued_waiting_for_dispatch",
        "dispatch_lease_acquired",
        "submit_in_progress",
        "pending_submit",
        "provider_not_start",
        "not_start",
        "queued",
        "waiting",
        "pending",
    }:
        return "Đang chờ bắt đầu"
    if raw in {"provider_running", "running", "in_progress", "processing", "final_rendering", "rendering"}:
        return "Đang tạo"
    if raw in {"provider_stalled_not_start", "stalled", "fallback_pending", "retrying"}:
        return "Đang chuyển hướng xử lý"
    if raw in {"submit_blocked_with_reason"}:
        return "Chưa thể bắt đầu"
    if raw in {"failed", "failed_no_charge", "error", "provider_failed", "exhausted"}:
        return "Chưa tạo được"
    return "Đang xử lý"


def _video_scene_started_epoch(item: dict[str, Any], current: dict[str, Any]) -> tuple[float, str]:
    for source, data in (("scene", item), ("job", current)):
        for key in (
            "started_at",
            "scene_started_at",
            "scene_submitted_at",
            "submitted_at",
            "provider_started_at",
            "provider_wait_started_at",
            "first_seen_at",
            "created_at",
        ):
            epoch = _video_epoch_from_value(data.get(key))
            if epoch > 0:
                return epoch, f"persisted_{key}"
        for key in (
            "started_at_epoch",
            "scene_started_at_epoch",
            "scene_submitted_at_epoch",
            "submitted_at_epoch",
            "provider_started_at_epoch",
            "provider_wait_started_at_epoch",
            "first_seen_at_epoch",
        ):
            epoch = _video_epoch_from_value(data.get(key))
            if epoch > 0:
                return epoch, f"persisted_{key}"
    return 0.0, "elapsed_field"


def video_per_scene_progress_board(job: dict[str, Any] | None = None) -> dict[str, Any]:
    current = dict(job or {})
    now_epoch = _video_epoch_from_value(current.get("_panel_now_epoch") or current.get("panel_rendered_at_epoch")) or time.time()
    scene_count = max(
        0,
        _as_int(
            current.get("scene_count")
            or current.get("scenes_total")
            or current.get("scene_tasks_total")
            or current.get("total_scenes"),
            0,
        ),
    )
    tasks_raw = current.get("scene_ledger") or current.get("scene_tasks") or current.get("provider_scene_tasks") or []
    tasks: list[dict[str, Any]] = []
    if isinstance(tasks_raw, dict):
        for key, value in sorted(tasks_raw.items(), key=lambda item: _as_int(item[0], 0)):
            item = dict(value or {}) if isinstance(value, dict) else {"status": value}
            item.setdefault("scene_index", key)
            tasks.append(item)
    elif isinstance(tasks_raw, (list, tuple)):
        tasks = [dict(item or {}) for item in tasks_raw if isinstance(item, dict)]
    status_by_scene = current.get("scene_status_by_scene") or {}
    if scene_count <= 0 and tasks:
        scene_count = max(_as_int(item.get("scene_index") or item.get("index"), idx + 1) for idx, item in enumerate(tasks))
    if scene_count <= 1 and not tasks:
        return {
            "visible": False,
            "scene_count": scene_count,
            "lines": [],
            "concat_waiting_for_scene_coverage": False,
        }
    by_index: dict[int, dict[str, Any]] = {}
    for offset, item in enumerate(tasks, start=1):
        idx = _as_int(item.get("scene_index") or item.get("index") or item.get("scene"), offset)
        by_index[max(1, idx)] = item
    for key, value in (status_by_scene.items() if isinstance(status_by_scene, dict) else []):
        idx = _as_int(key, 0)
        if idx <= 0:
            continue
        item = by_index.setdefault(idx, {"scene_index": idx})
        if not item.get("status"):
            item["status"] = value
    coverage_count = _as_int(
        current.get("completed_scene_count")
        or current.get("panel_completed_scene_count")
        or current.get("scene_coverage_count")
        or current.get("scene_clip_count")
        or current.get("scenes_done"),
        0,
    )
    lines: list[str] = []
    statuses: list[dict[str, Any]] = []
    elapsed_by_scene: dict[str, int] = {}
    elapsed_sources: dict[str, str] = {}
    raw_progress_values: list[int] = []
    for idx in range(1, max(scene_count, len(by_index)) + 1):
        item = by_index.get(idx, {"scene_index": idx})
        clip_ready = bool(
            _as_bool(item.get("clip_valid") or item.get("clip_ready") or item.get("downloaded"))
            or _as_int(item.get("clip_bytes") or item.get("artifact_size"), 0) > 0
            or str(item.get("status") or "").strip().lower() in {"scene_clip_validated", "clip_downloaded", "validated"}
        )
        status = item.get("status") or item.get("current_scene_status") or current.get("current_scene_status")
        label = _video_scene_status_label(status, clip_ready)
        raw_progress = _as_int(
            item.get("provider_progress")
            or item.get("provider_progress_raw")
            or item.get("raw_provider_progress")
            or item.get("progress"),
            0,
        )
        raw_progress_values.append(max(0, min(100, raw_progress)))
        started_epoch, elapsed_source = _video_scene_started_epoch(item, current)
        elapsed = int(max(0, now_epoch - started_epoch)) if started_epoch > 0 else _as_int(
            item.get("provider_elapsed_seconds")
            or item.get("elapsed_seconds")
            or item.get("scene_not_start_elapsed")
            or current.get("provider_elapsed_seconds"),
            0,
        )
        elapsed_by_scene[str(idx)] = elapsed
        elapsed_sources[str(idx)] = elapsed_source
        if clip_ready:
            lines.append(f"• Cảnh {idx}/{max(scene_count, idx)}: {html.escape(label)}")
        elif elapsed > 0:
            lines.append(f"• Cảnh {idx}/{max(scene_count, idx)}: {html.escape(label)} — đã chờ {_video_human_elapsed(elapsed)}")
        else:
            lines.append(f"• Cảnh {idx}/{max(scene_count, idx)}: {html.escape(label)}")
        statuses.append(
            {
                "scene_index": idx,
                "status": label,
                "elapsed_seconds": elapsed,
                "provider_progress": raw_progress,
                "clip_ready": clip_ready,
                "elapsed_source": elapsed_source,
            }
        )
    concat_attempted = _as_bool(current.get("concat_attempted") or current.get("stitch_attempted"))
    concat_waiting = bool(scene_count > 1 and coverage_count < scene_count)
    final_delivered = _as_bool(current.get("final_delivered") or current.get("delivery_succeeded"))
    final_artifact = job_has_final_artifact(current)
    if scene_count > 1:
        final_artifact = bool(
            coverage_count >= scene_count
            and current.get("concat_output_valid")
            and current.get("final_mp4_valid")
        )
    lines.append(f"• Hoàn tất: {coverage_count}/{max(scene_count, 1)} cảnh")
    if scene_count > 1:
        if final_delivered:
            lines.append("• Ghép video: Đã xong")
        elif concat_waiting and coverage_count > 0:
            lines.append("• Ghép video: Chờ cảnh còn lại")
        elif concat_waiting:
            lines.append("• Ghép video: Chưa bắt đầu")
        elif concat_attempted or coverage_count >= scene_count:
            lines.append("• Ghép video: Đang thực hiện")
        else:
            lines.append("• Ghép video: Chưa bắt đầu")
    if final_delivered:
        lines.append("• Video đã hoàn tất")
        lines.append("• Đã gửi kết quả")
    elif final_artifact:
        lines.append("• Gửi kết quả: Đang kiểm tra")
    else:
        lines.append("• Gửi kết quả: Chưa bắt đầu")
    refresh_seconds = max(5, min(30, _as_int(current.get("auto_refresh_interval_seconds") or current.get("panel_refresh_interval_seconds"), 10)))
    if not final_delivered:
        lines.append(f"• Hệ thống sẽ tự kiểm tra lại sau {refresh_seconds} giây")
        fallback_candidate = str(
            current.get("fallback_provider_candidate")
            or current.get("next_provider_or_model_candidate")
            or current.get("fallback_provider")
            or ""
        ).strip()
        fallback_available = bool(current.get("fallback_allowed") and fallback_candidate)
        threshold = _as_int(current.get("in_progress_stall_threshold") or current.get("not_start_threshold_seconds"), 0)
        stall_elapsed = _as_int(current.get("in_progress_stall_elapsed") or current.get("provider_elapsed_seconds"), 0)
        if fallback_available and threshold > 0 and stall_elapsed < threshold:
            lines.append(f"• Nếu chưa có kết quả sau {_video_human_elapsed(threshold - stall_elapsed)}, hệ thống sẽ tự chuyển hướng xử lý.")
        elif fallback_available and threshold > 0:
            lines.append("• Hệ thống đang tiếp tục kiểm tra và sẽ tự xử lý nếu chờ quá lâu.")
    unique_raw = {value for value in raw_progress_values if value > 0}
    progress_source = str(current.get("public_progress_source") or current.get("render_progress_source") or "").strip().lower()
    untrusted_progress = bool(
        current.get("provider_progress_public_suppressed")
        or progress_source in {"provider_elapsed_in_progress", "elapsed_provider_wait", "scene_and_elapsed"}
        or (len(unique_raw) == 1 and coverage_count == 0 and not final_artifact)
    )
    public_progress_mode = "scene_and_elapsed" if scene_count > 1 and untrusted_progress and not final_delivered else "percent"
    return {
        "visible": bool(lines),
        "scene_count": scene_count,
        "lines": lines,
        "scene_statuses": statuses,
        "elapsed_live_tick_enabled": True,
        "elapsed_source": "persisted_started_at" if any(source.startswith("persisted_") for source in elapsed_sources.values()) else "elapsed_field",
        "elapsed_seconds_by_scene": elapsed_by_scene,
        "panel_rendered_at_epoch": now_epoch,
        "concat_waiting_for_scene_coverage": concat_waiting,
        "concat_attempted": bool(concat_attempted and not concat_waiting),
        "scene_coverage_count": coverage_count,
        "panel_scene_ledger_source": str(current.get("panel_scene_ledger_source") or current.get("scene_ledger_source") or "scene_tasks"),
        "panel_completed_scene_count": coverage_count,
        "panel_unresolved_scene_count": max(0, scene_count - coverage_count),
        "public_progress_mode": public_progress_mode,
        "public_progress_percent_visible": bool(public_progress_mode != "scene_and_elapsed" or final_delivered),
        "public_technical_terms_hidden": True,
    }


def video_per_scene_progress_board_text(job: dict[str, Any] | None = None) -> str:
    board = video_per_scene_progress_board(job)
    if not board.get("visible"):
        return ""
    return "\n".join(["<b>Theo từng cảnh:</b>", *[str(line) for line in board.get("lines") or []]])


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
    if canonical in {"music_bg", "music_song"} and completed_steps is not None and terminal != "delivered":
        completed = {str(item or "").strip().lower() for item in completed_steps}
        generation_done = bool(completed & {"generating_song", "generating_music", "validating_audio", "delivering"})
        stage_input = str(current_stage or "").strip().lower().replace("-", "_")
        if generation_done and stage_input in {"", "received_request", "preparing_lyrics", "preparing_style", "preparing_prompt"}:
            current_stage = "validating_audio"
            try:
                percent = max(85, int(percent or 0))
            except Exception:
                percent = 85
            if not status_override:
                status_override = "Chưa tải được file nhạc. Hệ thống chưa trừ Xu."
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
        or job.get("video_delivered_at")
        or job.get("video_delivery_message_id")
        or job.get("final_video_file_id")
        or job.get("final_delivered")
        or job.get("final_mp4_delivered")
        or job.get("delivery_succeeded")
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
    zero_task_preparing = bool(
        canonical in VIDEO_PROGRESS_TYPES
        and not has_final_artifact
        and (
            job.get("zero_task_progress_guard")
            or (
                _as_int(job.get("scene_count") or job.get("scenes_total"), 0) > 0
                and _as_int(
                    job.get("valid_provider_task_count")
                    or job.get("task_created_count")
                    or job.get("scene_tasks_submitted_count"),
                    0,
                ) == 0
                and str(job.get("current_scene_status") or "").strip().lower()
                in {"queued_waiting_for_dispatch", "pending", "waiting"}
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
    elif canonical in VIDEO_PROGRESS_TYPES and status in {"completed", "complete", "success", "succeeded", "delivered"} and has_final_artifact and not has_delivery:
        status = "processing"
        progress = max(85, min(95, int(progress or 95)))
    elif canonical in VIDEO_PROGRESS_TYPES and str(job.get("visual_classification") or job.get("final_classification") or "").strip().lower() in {"partial_simple_video", "failed_no_real_visual"}:
        terminal = "failed_no_charge"
        status = "failed"
        progress = min(85, int(progress or 85))
    elif canonical in VIDEO_PROGRESS_TYPES and status in {"completed", "complete", "success", "succeeded", "delivered"} and has_delivery:
        terminal = "delivered"
    elif status in {"completed", "complete", "success", "succeeded", "delivered"}:
        terminal = "delivered"
    elif any(token in status for token in ("fail", "error", "cancel")):
        if canonical in {"music_bg", "music_song"} and music_artifact_waiting:
            status = "processing"
        else:
            terminal = "failed_no_charge"
    if canonical in {"music_bg", "music_song"}:
        lifecycle = music_progress_lifecycle(canonical, job)
        completed_steps = list(lifecycle.get("completed_steps") or [])
        job_completed_steps = [str(item or "").strip() for item in (job.get("completed_steps") or []) if str(item or "").strip()]
        if job_completed_steps:
            merged_completed: list[str] = []
            for item in product_progress_spec(canonical).get("steps") or []:
                key = str(item.get("key") or "")
                if key and (key in completed_steps or key in job_completed_steps) and key not in merged_completed:
                    merged_completed.append(key)
            completed_steps = merged_completed or completed_steps
        completed_set = {str(item or "").strip().lower() for item in completed_steps}
        generation_checkpoint_done = bool(completed_set & {"generating_song", "generating_music", "validating_audio", "delivering"})
        status_text = ""
        terminal_fail_allowed = _music_terminal_fail_allowed(job, lifecycle, terminal)
        if terminal in {"failed_no_charge", "failed_refunded", "needs_admin_review"} and not terminal_fail_allowed:
            terminal = ""
            status = "processing"
            music_artifact_waiting = bool(
                music_artifact_waiting
                or lifecycle.get("provider_task_id")
                or lifecycle.get("provider_completed")
                or _music_raw_audio_url_present(job)
                or _music_artifact_materialization_started(job)
            )
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
            if (lifecycle.get("provider_completed") or generation_checkpoint_done) and not lifecycle.get("audio_validated"):
                stage_key = "validating_audio"
            if not stage_key:
                if not lifecycle.get("provider_task_id"):
                    stage_key = "received_request"
                elif lifecycle.get("provider_completed"):
                    stage_key = "validating_audio"
                else:
                    stage_key = "generating_song" if canonical == "music_song" else "generating_music"
            if progress is None:
                progress = int(product_progress_stage(canonical, stage_key).get("percent") or 5)
            if (lifecycle.get("provider_completed") or generation_checkpoint_done) and not lifecycle.get("audio_validated"):
                status_text = "Chưa tải được file nhạc. Hệ thống chưa trừ Xu."
                progress = max(85, int(progress or 85))
        elif music_artifact_waiting:
            stage_key = "validating_audio"
            progress = max(80, min(90, int(progress if progress is not None else 85)))
            status_text = "TOAN AAS đang chuẩn bị file nhạc. Anh/chị vui lòng kiểm tra lại sau."
        elif lifecycle.get("audio_validated"):
            stage_key = "delivering"
            progress = max(90, min(95, int(progress if progress is not None else 95)))
        elif lifecycle.get("artifact_ready"):
            stage_key = "validating_audio"
            progress = max(85, min(90, int(progress if progress is not None else 85)))
        elif lifecycle.get("provider_completed"):
            stage_key = "validating_audio"
            progress = max(80, min(90, int(progress if progress is not None else 85)))
            status_text = "Đang tải file nhạc. TOAN AAS đang chuẩn bị file nhạc. Anh/chị vui lòng kiểm tra lại sau."
        elif generation_checkpoint_done and not lifecycle.get("audio_validated"):
            stage_key = "validating_audio"
            progress = max(80, min(90, int(progress if progress is not None else 85)))
            status_text = "Đang kiểm tra file nhạc. Khi file nhạc sẵn sàng, hệ thống sẽ tự gửi kết quả."
        elif lifecycle.get("create_song_started"):
            stage_key = "generating_song" if canonical == "music_song" else "generating_music"
            if progress is None or int(progress or 0) <= 0:
                if status == "generating":
                    progress = 65
                elif status in {"processing", "running", "in_progress"}:
                    progress = 50
                else:
                    progress = 35
            else:
                floor_progress = 50 if status in {"processing", "running", "in_progress"} else 35
                progress = max(floor_progress, min(75, int(progress or floor_progress)))
            status_text = "TOAN AAS đang tạo bài hát. Khi file nhạc sẵn sàng, hệ thống sẽ tự gửi kết quả." if canonical == "music_song" else "TOAN AAS đang tạo nhạc. Khi file nhạc sẵn sàng, hệ thống sẽ tự gửi kết quả."
        elif lifecycle.get("provider_submit_called"):
            stage_key = "preparing_style" if canonical == "music_song" else "preparing_prompt"
            progress = max(5, min(25, int(progress if progress is not None else (25 if canonical == "music_song" else 15))))
            status_text = "TOAN AAS đang gửi yêu cầu tạo bài hát." if canonical == "music_song" else "TOAN AAS đang gửi yêu cầu tạo nhạc."
        elif status in {"submitted", "queued", "processing", "running", "generating"}:
            stage_key = "generating_song" if canonical == "music_song" else "generating_music"
            if progress is None or int(progress or 0) <= 0:
                if status == "generating":
                    progress = 65
                elif status in {"processing", "running"}:
                    progress = 50
                else:
                    progress = 35
            else:
                floor_progress = 50 if status in {"processing", "running"} else 35
                progress = max(floor_progress, min(75, int(progress or floor_progress)))
            status_text = "TOAN AAS đang tạo bài hát. Khi file nhạc sẵn sàng, hệ thống sẽ tự gửi kết quả." if canonical == "music_song" else "TOAN AAS đang tạo nhạc. Khi file nhạc sẵn sàng, hệ thống sẽ tự gửi kết quả."
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
        requested_progress = product_progress_percent(canonical, str(stage.get("key") or stage_key), progress if progress is not None else None, terminal)
        progress_debug = _music_reconcile_progress(
            canonical,
            job,
            lifecycle,
            str(stage.get("key") or stage_key),
            requested_progress,
            terminal,
            music_artifact_waiting=music_artifact_waiting,
        )
        final_progress = int(progress_debug.get("final_progress_after_reconcile") or requested_progress)
        return {
            "product_type": canonical,
            "current_stage": str(stage.get("key") or stage_key),
            "percent": final_progress,
            "terminal_state": terminal,
            "completed_steps": completed_steps,
            "music_lifecycle": lifecycle,
            "status_text": status_text,
            **progress_debug,
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
            input_save_failed = bool(
                stage_key in {"input_save", "input_save_failed", "received_file_failed", "telegram_download_failed", "large_telegram_download_unsupported"}
                or str(job.get("last_error_stage") or "").strip().lower() == "input_save"
                or str(job.get("input_save_blocker") or job.get("pipeline_blocker") or "").strip().lower()
                in {"telegram_download_failed", "large_telegram_download_unsupported", "file_not_saved", "local_input_missing", "input_file_size_0"}
                or str(job.get("status") or "").strip().upper() == "INPUT_SAVE_FAILED"
            )
            if input_save_failed:
                stage_key = "input_save_failed"
                progress = 5
                completed_steps = []
                status_text = "Chưa tải được video. Hệ thống chưa trừ Xu."
            elif stage_key in {"delivered", "success", "completed", "failed", "failed_no_charge", "failed_refunded", "needs_admin_review"}:
                stage_key = "validating_output"
                progress = max(5, min(95, _as_int(progress, int(product_progress_stage(canonical, stage_key).get("percent") or 90))))
                completed_steps = list(job.get("completed_steps") or [])
                status_text = "Chưa xử lý được lúc này, TOAN AAS chưa trừ Xu."
            else:
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
        public_stage_key = str(stage.get("key") or stage_key)
        debug_stage_key = stage_key if stage_key == "input_save_failed" else public_stage_key
        return {
            "product_type": canonical,
            "current_stage": str(debug_stage_key),
            "percent": product_progress_percent(canonical, public_stage_key, progress if progress is not None else None, terminal),
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
            if has_final_artifact and not has_delivery:
                stage_key = "validating_output"
            elif zero_task_preparing:
                stage_key = "preparing_content"
                progress = min(20, max(5, _as_int(progress, 10)))
            else:
                stage_key = "generating_video" if status else "received_request"
        else:
            stage_key = str(job.get("stage") or job.get("current_stage") or "received_request")
    if canonical in VIDEO_PROGRESS_TYPES and has_final_artifact and not has_delivery and not terminal:
        stage_key = "validating_output"
        progress = max(85, min(95, _as_int(progress, 95)))
    if terminal in {"failed_no_charge", "failed_refunded", "needs_admin_review"} and canonical in {"music_bg", "music_song"}:
        stage_key = "validating_audio"
    requested_stage = "preparing_content" if zero_task_preparing and not terminal else str(
        job.get("stage") or job.get("current_stage") or stage_key
    )
    stage = product_progress_stage(canonical, requested_stage)
    return {
        "product_type": canonical,
        "current_stage": str(stage.get("key") or stage_key),
        "percent": product_progress_percent(canonical, str(stage.get("key") or stage_key), progress if progress is not None else None, terminal),
        "terminal_state": terminal,
    }


def product_progress_debug_payload(product_type: str = "", job_id: str = "", job: dict[str, Any] | None = None) -> dict[str, Any]:
    state = product_progress_stage_from_job(product_type, job)
    payload = {
        "product_type": normalize_product_type(product_type),
        "job_code": product_progress_public_job_code(job_id),
        "current_stage": state.get("current_stage"),
        "percent": state.get("percent"),
        "terminal_state": state.get("terminal_state") or "",
        "completed_steps": list(state.get("completed_steps") or []),
        "update_callback": product_progress_update_callback(product_type, job_id),
    }
    if normalize_product_type(product_type) in {"music_bg", "music_song"}:
        for key in (
            "progress_monotonic_applied",
            "previous_progress",
            "requested_progress",
            "final_progress",
            "final_progress_after_reconcile",
            "progress_source",
            "progress_rollback_prevented",
            "provider_completed",
            "raw_audio_url_present",
            "artifact_materialization_started",
            "artifact_waiting",
            "artifact_check_stage_allowed",
            "artifact_wait_attempt_count",
            "artifact_wait_max_attempts",
            "next_artifact_retry_at",
            "artifact_wait_terminal_exhausted",
            "terminal_fail_allowed",
        ):
            payload[key] = state.get(key)
    if normalize_product_type(product_type) in VIDEO_PROGRESS_TYPES:
        for key in (
            "orchestration_mode",
            "scene_count",
            "scene_tasks_created_count",
            "scene_tasks_submitted_count",
            "scene_tasks_completed",
            "scene_tasks_total",
            "scenes_total",
            "scenes_done",
            "scenes_pending",
            "scenes_running",
            "current_scene",
            "current_scene_index",
            "current_scene_status",
            "scene_not_start_elapsed",
            "scene_submitted_at",
            "scene_first_not_start_seen_at",
            "provider_elapsed_seconds",
            "elapsed_estimate_progress",
            "public_progress_source",
            "public_progress_mode",
            "public_progress_percent_visible",
            "public_progress_cap",
            "persisted_progress_updated",
            "elapsed_live_tick_enabled",
            "elapsed_source",
            "panel_rendered_at",
            "elapsed_seconds_by_scene",
            "no_fake_success_guard",
            "in_progress_stall_elapsed",
            "in_progress_stall_threshold",
            "provider_progress_last_changed_at",
            "provider_progress_stuck",
            "in_progress_stall_decision",
            "fallback_due_to_in_progress_stall",
            "stall_threshold",
            "not_start_threshold_seconds",
            "not_start_threshold_source",
            "provider_status_payload_source",
            "shopaikey_data_status",
            "raw_provider_status_before_source_fix",
            "raw_provider_status",
            "normalized_provider_status",
            "canonical_status_before_not_start_override",
            "not_start_override_applied",
            "provider_stalled_not_start",
            "scene_status_by_scene",
            "fallback_eligible_by_scene",
            "fallback_reason_by_scene",
            "selected_model_by_scene",
            "canonical_scene_index",
            "canonical_task_selected",
            "canonical_task_candidates_by_scene",
            "canonical_task_reject_reasons",
            "next_provider_or_model_candidate",
            "fallback_scene_index",
            "fallback_allowed",
            "fallback_block_reason",
            "final_user_visible_state",
            "final_status_after_reconcile",
            "public_confirm_kickoff_attempted",
            "public_confirm_kickoff_success",
            "worker_dispatch_attempted",
            "worker_dispatch_success",
            "worker_dispatch_blocker",
            "dispatch_status",
            "provider_chain_resolved",
            "configured_provider_chain",
            "next_poll_scheduled",
            "admission_snapshot_id",
            "admission_checked_at",
            "admission_candidate_keys",
            "admission_candidate_count",
            "admission_result",
            "admission_block_reason",
            "dispatch_outbox_present",
            "dispatch_outbox_status",
            "dispatch_outbox_attempt_count",
            "dispatch_outbox_lease_owner",
            "dispatch_outbox_lease_expires_at",
            "dispatch_outbox_last_error",
            "dispatch_outbox_acknowledged",
            "worker_scan_seen_job",
            "worker_scan_seen_outbox",
            "worker_claim_attempted",
            "worker_claim_result",
            "worker_claim_block_reason",
            "worker_last_scan_at",
            "worker_next_scan_at",
            "zero_task_watchdog_checked_at",
            "zero_task_watchdog_triggered",
            "zero_task_elapsed_seconds",
            "zero_task_candidate_count",
            "zero_task_recovery_action",
            "zero_task_terminal_reason",
            "route_requires_provider",
            "route_requirement_source",
            "route_requirement_product_contract",
            "route_requirement_override",
            "route_block_reason",
        ):
            payload[key] = job.get(key)
        try:
            from services import video_provider_router

            route_contract = video_provider_router.product_video_route_contract(
                str(job.get("product_type") or job.get("profile_id") or ""),
                str(job.get("engine_adapter") or ""),
                str(job.get("orchestration_mode") or job.get("provider_orchestration_mode") or ""),
                explicit_local_renderer=bool(job.get("explicit_local_renderer")),
            )
            persisted_route = job.get("route_requires_provider")
            if route_contract.get("route_requires_provider") or str(job.get("source") or "") == "product_video":
                payload.update(route_contract)
                payload["route_requirement_product_contract"] = bool(route_contract.get("route_requires_provider"))
                payload["persisted_route_requires_provider_before_reconcile"] = persisted_route
                if route_contract.get("route_requires_provider") and persisted_route is False:
                    payload["route_requirement_override"] = "legacy_persisted_false_ignored"
        except Exception:
            pass
    return payload


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
