"""Canonical Free Tools Service for TOAN AAS Ecosystem (R38).

Reuses Bot's canonical open_public_tools and public_video_link_downloader.
Ensures parity, truthful error behavior, zero wallet mutation, and SSRF/safe delivery guards.
"""

from __future__ import annotations

import html
import ipaddress
import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from services import open_public_tools as opt
from providers.video_downloader_provider import (
    VIDEO_DOWNLOADER_RIGHTS_COPY,
    _is_private_host,
)
from services.public_video_link_downloader import (
    LinkDownloadRequest,
    PublicVideoLinkDownloader,
)

logger = logging.getLogger(__name__)

DANGEROUS_SCHEMES = ("javascript:", "data:", "file:", "vbscript:", "blob:")


def is_downloader_public_enabled() -> bool:
    """Canonical Bot authority for video downloader public readiness."""
    try:
        import bot
        if hasattr(bot, "VIDEO_DOWNLOADER_PUBLIC_ENABLED"):
            return bool(bot.VIDEO_DOWNLOADER_PUBLIC_ENABLED)
    except Exception:
        pass
    val = os.getenv("VIDEO_DOWNLOADER_PUBLIC_ENABLED")
    if val is not None:
        return val.strip().lower() in {"1", "true", "yes", "on"}
    linkdl_val = os.getenv("LINKDL_PUBLIC_ENABLED", "true")
    return linkdl_val.strip().lower() in {"1", "true", "yes", "on"}


# ─── 1. EXCHANGE RATE ─────────────────────────────────────────────────────────

def handle_exchange_rate(raw_input: str, target_lang: str = "vi") -> tuple[bool, dict[str, Any], int]:
    text = str(raw_input or "").strip()
    if not text:
        return False, {
            "ok": False,
            "error_code": "RATE_INVALID_INPUT",
            "message": "Số tiền hoặc công thức quy đổi không được để trống.",
        }, 400

    lang = target_lang if target_lang in {"vi", "en", "zh"} else "vi"
    try:
        conv = opt.convert_custom_currency(text, target_lang=lang)
    except Exception as exc:
        logger.warning("Exchange rate conversion error: %s", exc)
        return False, {
            "ok": False,
            "error_code": "RATE_SOURCE_UNAVAILABLE",
            "message": "Nguồn tỷ giá hiện không khả dụng. Vui lòng thử lại sau.",
        }, 503

    if not isinstance(conv, dict) or not conv.get("currency_in"):
        return False, {
            "ok": False,
            "error_code": "RATE_INVALID_INPUT",
            "message": "Không nhận diện được mệnh giá tiền tệ hợp lệ.",
        }, 400

    conv["ok"] = True
    return True, conv, 200


# ─── 2. WEATHER ───────────────────────────────────────────────────────────────

def handle_weather(location: str, unit: str = "celsius") -> tuple[bool, dict[str, Any], int]:
    loc = str(location or "").strip()
    if not loc:
        return False, {
            "ok": False,
            "error_code": "WEATHER_INVALID_LOCATION",
            "message": "Địa điểm tra cứu thời tiết không được để trống.",
        }, 400

    if len(loc) > 120:
        return False, {
            "ok": False,
            "error_code": "WEATHER_INVALID_LOCATION",
            "message": "Tên địa điểm không được vượt quá 120 ký tự.",
        }, 400

    u = str(unit or "celsius").lower().strip()
    if u not in {"celsius", "fahrenheit"}:
        u = "celsius"

    try:
        report = opt.fetch_weather_report(loc)
    except Exception as exc:
        logger.warning("Weather fetch error: %s", exc)
        return False, {
            "ok": False,
            "error_code": "WEATHER_SOURCE_ERROR",
            "message": "Lỗi kết nối nguồn dữ liệu thời tiết. Vui lòng thử lại sau.",
        }, 503

    if not report or not report.get("ok"):
        return False, {
            "ok": False,
            "error_code": "WEATHER_EMPTY_RESULT",
            "message": "Không tìm thấy dữ liệu thời tiết cho địa điểm đã nhập.",
        }, 404

    temp = float(report.get("temperature", 28.0))
    if u == "fahrenheit":
        temp = round(temp * 9.0 / 5.0 + 32.0, 1)

    result = {
        "ok": True,
        "city": report.get("city", loc),
        "country": report.get("country", ""),
        "temperature": temp,
        "windspeed": report.get("windspeed", 10.0),
        "weathercode": report.get("weathercode", 0),
        "description": report.get("description", "Thời tiết ổn định"),
        "unit": u,
        "source": report.get("source", "Open-Meteo Live API"),
    }
    return True, result, 200


# ─── 3. AI AVATAR ─────────────────────────────────────────────────────────────

def handle_avatar(
    seed: str,
    avatar_set: int = 1,
    confirmed_rights: bool = False,
    style: str = "realistic",
) -> tuple[bool, dict[str, Any], int]:
    if not confirmed_rights:
        return False, {
            "ok": False,
            "error_code": "AVATAR_RIGHTS_REQUIRED",
            "message": "Bạn cần xác nhận có quyền sử dụng hình ảnh và mô tả này.",
        }, 400

    clean_seed = str(seed or "").strip()
    if not clean_seed:
        clean_seed = "toanaas_user"

    # Enforce safe URL and anti-XSS constraints
    s_lower = clean_seed.lower()
    if any(s_lower.startswith(sch) for sch in DANGEROUS_SCHEMES) or "<script" in s_lower or "javascript:" in s_lower:
        return False, {
            "ok": False,
            "error_code": "AVATAR_UNSAFE_URL_BLOCKED",
            "message": "Mô tả hoặc seed avatar chứa ký tự hoặc giao thức không an toàn.",
        }, 400

    set_id = max(1, min(5, int(avatar_set or 1)))
    avatar_url = opt.generate_avatar_ai_url(clean_seed, avatar_set=set_id)

    return True, {
        "ok": True,
        "avatar_url": avatar_url,
        "seed": clean_seed,
        "avatar_set": set_id,
        "style": style or "realistic",
        "rights_notice": "Người dùng đã xác nhận quyền sở hữu/sử dụng ảnh.",
    }, 200


# ─── 4. VIDEO DOWNLOADER ──────────────────────────────────────────────────────

def _validate_downloader_url(url: str) -> tuple[bool, str, dict[str, Any]]:
    clean = str(url or "").strip()
    if not clean:
        return False, "Liên kết không được để trống.", {"error_code": "DOWNLOADER_INVALID_URL"}

    if len(clean) > 2000:
        return False, "Liên kết vượt quá độ dài tối đa 2000 ký tự.", {"error_code": "DOWNLOADER_INVALID_URL"}

    try:
        parsed = urlparse(clean)
    except Exception:
        return False, "Định dạng URL không hợp lệ.", {"error_code": "DOWNLOADER_INVALID_URL"}

    if parsed.scheme not in {"http", "https"}:
        return False, "Chỉ hỗ trợ giao thức HTTP/HTTPS.", {"error_code": "DOWNLOADER_UNSUPPORTED_OR_PRIVATE_URL_BLOCKED"}

    host = (parsed.hostname or "").lower().strip()
    if not host or _is_private_host(host):
        return False, "Địa chỉ mạng nội bộ hoặc máy chủ cục bộ bị chặn vì lý do an toàn.", {
            "error_code": "DOWNLOADER_UNSUPPORTED_OR_PRIVATE_URL_BLOCKED",
            "blocked_host": host,
        }

    return True, clean, {"host": host}


def handle_downloader_inspect(url: str, requested_asset: str = "video") -> tuple[bool, dict[str, Any], int]:
    valid, clean_url, info = _validate_downloader_url(url)
    if not valid:
        return False, {
            "ok": False,
            "error_code": info.get("error_code", "DOWNLOADER_INVALID_URL"),
            "message": clean_url,
        }, 400

    downloader = PublicVideoLinkDownloader()
    detection = downloader.detect_link(clean_url)
    if not detection.get("ok"):
        reason = detection.get("reason") or "unsupported_platform"
        return False, {
            "ok": False,
            "error_code": "DOWNLOADER_UNSUPPORTED_OR_PRIVATE_URL_BLOCKED",
            "reason": reason,
            "message": f"Nền tảng hoặc liên kết chưa được hỗ trợ: {reason}",
        }, 400

    # Public enabled guard
    if not is_downloader_public_enabled():
        return False, {
            "ok": False,
            "error_code": "DOWNLOADER_PROVIDER_DISABLED_FAIL_CLOSED",
            "reason": "disabled",
            "message": "Công cụ tải video hiện đang bảo trì hoặc chưa bật công khai.",
        }, 503

    meta = downloader.metadata(LinkDownloadRequest(url=clean_url, requested_asset=requested_asset))
    if not meta.ok:
        meta_reason = meta.blocker or "metadata_failed"
        return False, {
            "ok": False,
            "error_code": "DOWNLOADER_METADATA_FAILED",
            "reason": meta_reason,
            "message": meta.public_message or f"Không thể lấy thông tin video: {meta_reason}",
        }, 400

    return True, {
        "ok": True,
        "url": clean_url,
        "platform": detection.get("platform", ""),
        "title": meta.title,
        "duration_seconds": meta.duration,
        "size_bytes": meta.bytes,
        "thumbnail_url": meta.thumbnail_url,
        "rights_notice": VIDEO_DOWNLOADER_RIGHTS_COPY,
    }, 200


def handle_downloader_download(
    url: str,
    requested_asset: str = "video",
    confirmed_rights: bool = False,
    user_id: int | str = 0,
    chat_id: int | str = 0,
) -> tuple[bool, dict[str, Any], int]:
    if not confirmed_rights:
        return False, {
            "ok": False,
            "error_code": "DOWNLOADER_RIGHTS_REQUIRED",
            "message": VIDEO_DOWNLOADER_RIGHTS_COPY,
        }, 400

    clean_url = str(url or "").strip()
    if not clean_url:
        return False, {
            "ok": False,
            "error_code": "DOWNLOADER_INVALID_URL",
            "message": "Liên kết không được để trống.",
        }, 400

    valid, clean_url, info = _validate_downloader_url(clean_url)
    if not valid:
        return False, {
            "ok": False,
            "error_code": info.get("error_code", "DOWNLOADER_INVALID_URL"),
            "message": clean_url,
        }, 400

    downloader = PublicVideoLinkDownloader()
    detection = downloader.detect_link(clean_url)
    if not detection.get("ok"):
        return False, {
            "ok": False,
            "error_code": "DOWNLOADER_UNSUPPORTED_OR_PRIVATE_URL_BLOCKED",
            "reason": detection.get("reason", "unsupported_platform"),
            "message": "Nền tảng chưa được hỗ trợ.",
        }, 400

    if not is_downloader_public_enabled():
        return False, {
            "ok": False,
            "error_code": "DOWNLOADER_PROVIDER_DISABLED_FAIL_CLOSED",
            "reason": "disabled",
            "message": "Công cụ tải video hiện đang bảo trì hoặc chưa bật công khai.",
        }, 503

    kind = str(requested_asset or "video").lower()
    if kind not in {"video", "audio", "cover"}:
        kind = "video"

    req = LinkDownloadRequest(
        url=clean_url,
        user_id=user_id,
        chat_id=chat_id,
        requested_asset=kind,
        platform=detection.get("platform", ""),
    )

    try:
        result = downloader.download(req)
    except Exception as exc:
        logger.warning("Downloader execution error: %s", exc)
        return False, {
            "ok": False,
            "error_code": "DOWNLOADER_EXECUTION_FAILED",
            "message": "Lỗi khi xử lý tải video.",
        }, 502

    if not result.get("ok"):
        blocker = result.get("blocker") or "download_failed"
        return False, {
            "ok": False,
            "error_code": "DOWNLOADER_EXECUTION_FAILED",
            "reason": blocker,
            "message": result.get("public_message") or "Tải video không thành công. TOAN AAS không trừ Xu.",
        }, 400

    job_id = str(result.get("job_id", "")).strip()

    # Ensure Safe Delivery:
    # Do NOT leak server-private filesystem paths
    return True, {
        "ok": True,
        "job_id": job_id,
        "platform": result.get("platform") or detection.get("platform", ""),
        "kind": kind,
        "title": result.get("title", ""),
        "duration": result.get("duration", 0),
        "bytes": result.get("bytes", 0),
        "status": "ready",
        "charged_xu": 0,
        "rights_notice": VIDEO_DOWNLOADER_RIGHTS_COPY,
        "delivery_ready": True,
        "delivery_url": f"/api/v1/tools/downloader/delivery/{job_id}?kind={kind}",
    }, 200


def handle_downloader_delivery(
    job_id: str,
    actor_id: str,
    kind: str = "video",
    mode: str = "stream",
) -> tuple[bool, Any, int]:
    """Retrieve verified downloaded artifact without leaking private filesystem paths."""
    clean_id = str(job_id or "").strip()
    if not clean_id:
        return False, {
            "ok": False,
            "error_code": "DOWNLOADER_JOB_NOT_FOUND",
            "message": "Mã tải không được để trống.",
        }, 404

    downloader = PublicVideoLinkDownloader()
    job = downloader.get_job(clean_id)
    if not job:
        return False, {
            "ok": False,
            "error_code": "DOWNLOADER_JOB_NOT_FOUND",
            "message": "Không tìm thấy yêu cầu tải.",
        }, 404

    # Owner check: if job has user_id and actor_id is present, they must match
    job_user = str(job.get("user_id") or "").strip()
    clean_actor = str(actor_id or "").strip()
    if job_user and clean_actor and job_user != clean_actor:
        return False, {
            "ok": False,
            "error_code": "DOWNLOADER_FOREIGN_OWNER_BLOCKED",
            "message": "Bạn không có quyền truy cập tệp tải này.",
        }, 403

    asset_kind = str(kind or job.get("requested_asset") or "video").lower().strip()
    if asset_kind == "thumbnail":
        asset_kind = "cover"
    if asset_kind not in {"video", "audio", "cover"}:
        asset_kind = "video"

    asset_key = "cover_path" if asset_kind == "cover" else f"{asset_kind}_path"
    cached_path = str(job.get(asset_key) or "").strip()
    file_path = Path(cached_path) if cached_path else None

    if not file_path or not file_path.is_file() or file_path.stat().st_size == 0:
        # Attempt lookup in job directory
        job_dir = downloader._job_dir(clean_id)
        if job_dir.is_dir():
            file_path = downloader._latest_file(job_dir, asset=asset_kind)

    if not file_path or not file_path.is_file() or file_path.stat().st_size == 0:
        return False, {
            "ok": False,
            "error_code": "DOWNLOADER_STALE_ARTIFACT_TRUTH",
            "message": "Tệp tải không còn tồn tại trên hệ thống lưu trữ.",
        }, 404

    suffix = file_path.suffix.lower()
    content_type_map = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".wav": "audio/wav",
        ".ogg": "audio/ogg",
        ".opus": "audio/opus",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    content_type = content_type_map.get(suffix, "application/octet-stream")

    if str(mode or "").strip().lower() == "meta":
        return True, {
            "ok": True,
            "job_id": clean_id,
            "kind": asset_kind,
            "content_type": content_type,
            "bytes": file_path.stat().st_size,
            "delivery_ready": True,
            "status": "ready",
        }, 200

    safe_filename = f"toanaas_{clean_id}_{asset_kind}{suffix}"
    return True, (file_path, content_type, safe_filename), 200
