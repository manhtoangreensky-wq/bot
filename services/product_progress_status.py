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


PRODUCT_PROGRESS_SPECS: dict[str, dict[str, Any]] = {
    "music_bg": {
        "title": "🎵 TOAN AAS đang tạo nhạc nền",
        "send_label": "📤 Tạo nhạc khác",
        "send_callback": "music_quick|showroom|ai_music",
        "back_label": "⬅️ Studio nhạc",
        "back_callback": "music_quick|showroom|music_hub",
        "steps": [
            _stage("received_request", "Nhận yêu cầu", "Đã nhận yêu cầu tạo nhạc", 5),
            _stage("preparing_prompt", "Chuẩn bị mô tả nhạc", "Đang chuẩn bị mô tả nhạc", 20),
            _stage("generating_music", "Tạo nhạc nền", "Đang tạo nhạc nền", 60),
            _stage("validating_audio", "Kiểm tra file nhạc", "Đang kiểm tra file nhạc", 85),
            _stage("delivering", "Gửi kết quả", "Đang gửi kết quả", 95),
            _stage("delivered", "Hoàn tất", "Đã gửi kết quả", 100),
        ],
    },
    "music_song": {
        "title": "🎤 TOAN AAS đang tạo bài hát",
        "send_label": "📤 Tạo bài hát khác",
        "send_callback": "music_quick|showroom|ai_music",
        "back_label": "⬅️ Studio nhạc",
        "back_callback": "music_quick|showroom|music_hub",
        "steps": [
            _stage("received_request", "Nhận yêu cầu", "Đã nhận yêu cầu tạo bài hát", 5),
            _stage("preparing_lyrics", "Chuẩn bị lời bài hát", "Đang chuẩn bị lời bài hát", 20),
            _stage("preparing_style", "Chuẩn bị phong cách", "Đang chuẩn bị phong cách", 35),
            _stage("generating_song", "Tạo bài hát", "Đang tạo bài hát", 65),
            _stage("validating_audio", "Kiểm tra file nhạc", "Đang kiểm tra file nhạc", 85),
            _stage("delivering", "Gửi kết quả", "Đang gửi kết quả", 95),
            _stage("delivered", "Hoàn tất", "Đã gửi kết quả", 100),
        ],
    },
    "video_trend": {
        "title": "🎬 TOAN AAS đang xử lý video trend",
        "send_label": "📤 Gửi yêu cầu khác",
        "send_callback": "trendg|start",
        "back_label": "⬅️ Menu video",
        "back_callback": "menu|main_video",
        "steps": [
            _stage("received_request", "Nhận yêu cầu", "Đã nhận yêu cầu", 5),
            _stage("building_script", "Lên ý tưởng video", "Đang lên ý tưởng video", 20),
            _stage("preparing_visuals", "Chuẩn bị cảnh", "Đang chuẩn bị cảnh", 40),
            _stage("rendering_video", "Dựng video", "Đang dựng video", 65),
            _stage("validating_video", "Kiểm tra file", "Đang kiểm tra file", 85),
            _stage("delivering", "Gửi kết quả", "Đang gửi kết quả", 95),
            _stage("delivered", "Hoàn tất", "Đã gửi kết quả", 100),
        ],
    },
    "script_to_video": {
        "title": "🎬 TOAN AAS đang dựng video từ kịch bản",
        "send_label": "📤 Gửi kịch bản khác",
        "send_callback": "vproduct|start_script_to_video",
        "back_label": "⬅️ Menu video",
        "back_callback": "menu|main_video",
        "steps": [
            _stage("received_script", "Nhận kịch bản", "Đã nhận kịch bản", 5),
            _stage("planning_scenes", "Chia cảnh", "Đang chia cảnh", 25),
            _stage("rendering_scenes", "Dựng cảnh", "Đang dựng cảnh", 60),
            _stage("validating_video", "Kiểm tra file", "Đang kiểm tra file", 85),
            _stage("delivering", "Gửi kết quả", "Đang gửi kết quả", 95),
            _stage("delivered", "Hoàn tất", "Đã gửi kết quả", 100),
        ],
    },
    "frame_video": {
        "title": "🎞 TOAN AAS đang ghép ảnh thành video",
        "send_label": "📤 Gửi ảnh khác",
        "send_callback": "framevideo|start",
        "back_label": "⬅️ Menu video",
        "back_callback": "menu|main_video",
        "steps": [
            _stage("received_images", "Nhận ảnh", "Đã nhận ảnh", 5),
            _stage("preparing_layout", "Chuẩn bị bố cục", "Đang chuẩn bị bố cục", 25),
            _stage("rendering_video", "Ghép video", "Đang ghép video", 65),
            _stage("validating_video", "Kiểm tra file", "Đang kiểm tra file", 85),
            _stage("delivering", "Gửi kết quả", "Đang gửi kết quả", 95),
            _stage("delivered", "Hoàn tất", "Đã gửi kết quả", 100),
        ],
    },
    "multiscene_video": {
        "title": "🎬 TOAN AAS đang dựng video nhiều cảnh",
        "send_label": "📤 Gửi yêu cầu khác",
        "send_callback": "vproduct|b14_start",
        "back_label": "⬅️ Menu video",
        "back_callback": "menu|main_video",
        "steps": [
            _stage("received_request", "Nhận yêu cầu", "Đã nhận yêu cầu", 5),
            _stage("planning_scenes", "Lập kế hoạch cảnh", "Đang lập kế hoạch cảnh", 20),
            _stage("rendering_scenes", "Dựng các cảnh", "Đang dựng các cảnh", 55),
            _stage("post_processing", "Hoàn thiện video", "Đang hoàn thiện video", 75),
            _stage("validating_video", "Kiểm tra file", "Đang kiểm tra file", 88),
            _stage("delivering", "Gửi kết quả", "Đang gửi kết quả", 95),
            _stage("delivered", "Hoàn tất", "Đã gửi kết quả", 100),
        ],
    },
    "video_ai_real": {
        "title": "🎥 TOAN AAS đang tạo video AI",
        "send_label": "📤 Gửi yêu cầu khác",
        "send_callback": "vproduct|start",
        "back_label": "⬅️ Menu video",
        "back_callback": "menu|main_video",
        "steps": [
            _stage("received_request", "Nhận yêu cầu", "Đã nhận yêu cầu", 5),
            _stage("preparing_scene", "Chuẩn bị cảnh", "Đang chuẩn bị cảnh", 25),
            _stage("generating_video", "Tạo video", "Đang tạo video", 65),
            _stage("validating_video", "Kiểm tra file", "Đang kiểm tra file", 85),
            _stage("delivering", "Gửi kết quả", "Đang gửi kết quả", 95),
            _stage("delivered", "Hoàn tất", "Đã gửi kết quả", 100),
        ],
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
            _stage("generating_voice", "Tạo giọng lồng tiếng", "Đang tạo giọng lồng tiếng", 65),
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
        "queued": "received_images",
        "processing": "rendering_video",
        "running": "rendering_video",
        "succeeded": "delivered",
        "success": "delivered",
        "completed": "delivered",
    },
    "multiscene_video": {
        "queued": "received_request",
        "queued_for_worker": "received_request",
        "processing": "rendering_scenes",
        "running": "rendering_scenes",
        "completed": "delivered",
        "success": "delivered",
    },
    "subdub": {
        "saved_input": "received_file",
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


def product_progress_public_job_code(job_id: str = "") -> str:
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
    safe_job = product_progress_safe_callback_value(job_id, 28) or "latest"
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
    if percent is not None:
        try:
            return max(0, min(100, int(percent)))
        except Exception:
            pass
    return int(product_progress_stage(product_type, stage).get("percent") or 0)


def product_progress_single_terminal_state(current_state: str = "", next_state: str = "") -> str:
    current = str(current_state or "").strip().lower()
    upcoming = str(next_state or "").strip().lower()
    if current in TERMINAL_STATES:
        return current
    return upcoming if upcoming in TERMINAL_STATES else current


def render_product_progress_panel(
    product_type: str = "",
    job_id: str = "",
    current_stage: str = "",
    percent: int | None = None,
    terminal_state: str = "",
    public_note: str = "",
    lang: str = "vi",
) -> str:
    canonical = normalize_product_type(product_type)
    spec = product_progress_spec(canonical)
    terminal = str(terminal_state or "").strip().lower()
    if terminal == "delivered":
        current_stage = "delivered"
    stage = product_progress_stage(canonical, current_stage)
    progress = product_progress_percent(canonical, stage.get("key"), percent, terminal)
    status_text = product_progress_terminal_label(terminal) or str(stage.get("status") or "")
    if canonical in {"music_bg", "music_song"} and terminal == "delivered":
        status_text = "Đã gửi file nhạc"
    status_text = sanitize_public_copy(status_text, "TOAN AAS đang xử lý.")
    note = sanitize_public_copy(public_note, "") if public_note else ""
    current_key = str(stage.get("key") or "")
    steps = list(spec.get("steps") or [])
    lines: list[str] = []
    if terminal == "delivered":
        lines = [f"✅ {item['label']}" for item in steps if item.get("key") != "delivered"]
    else:
        current_percent = int(stage.get("percent") or progress)
        for item in steps:
            if item.get("key") == "delivered":
                continue
            item_percent = int(item.get("percent") or 0)
            if terminal in {"failed_no_charge", "failed_refunded", "needs_admin_review"} and item.get("key") == current_key:
                marker = "⚠️" if terminal != "needs_admin_review" else "⏳"
            elif item_percent < current_percent:
                marker = "✅"
            elif item.get("key") == current_key:
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
            ("🔄 Cập nhật trạng thái", product_progress_update_callback(product_type, job_id)),
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
    provider_task_id = str(job.get("provider_task_id") or job.get("provider_job_id") or "").strip()
    has_delivery = bool(
        job.get("sent_full_at")
        or job.get("delivered_at")
        or job.get("music_delivered_at")
        or job.get("music_result_delivered_at")
        or job.get("output_file_id")
        or job.get("music_output_file_id")
    )
    terminal = ""
    explicit_terminal = str(job.get("terminal_state") or job.get("music_terminal_state") or "").strip().lower()
    if explicit_terminal in TERMINAL_STATES:
        terminal = explicit_terminal
    elif canonical in {"music_bg", "music_song"} and status in {"completed", "complete", "success", "succeeded"} and output_bytes <= 0 and not has_delivery:
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
    elif status in {"completed", "complete", "success", "succeeded", "delivered"}:
        terminal = "delivered"
    elif any(token in status for token in ("fail", "error", "cancel")):
        terminal = "failed_no_charge"
    stage_key = STAGE_ALIASES.get(canonical, {}).get(status, "")
    if not stage_key:
        if canonical in {"music_bg"}:
            stage_key = "generating_music" if status else "received_request"
        elif canonical in {"music_song"}:
            stage_key = "generating_song" if status else "received_request"
        elif canonical == "subdub":
            stage_key = "generating_voice" if status else "received_file"
        elif canonical == "frame_video":
            stage_key = "rendering_video" if status else "received_images"
        elif canonical == "multiscene_video":
            stage_key = "rendering_scenes" if status else "received_request"
        else:
            stage_key = str(job.get("stage") or job.get("current_stage") or "received_request")
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
        "update_callback": product_progress_update_callback(product_type, job_id),
    }


def product_progress_matrix_lines() -> list[str]:
    lines = ["📊 <b>TOAN AAS progress matrix</b>"]
    for product_type in sorted(PRODUCT_PROGRESS_SPECS):
        spec = PRODUCT_PROGRESS_SPECS[product_type]
        steps = ", ".join(str(item.get("key") or "") for item in spec.get("steps") or [])
        lines.append(f"• <code>{html.escape(product_type)}</code>: {html.escape(steps)}")
    return lines
