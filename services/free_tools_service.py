"""Canonical Free Tools Service for TOAN AAS Ecosystem (R38).

Reuses Bot's canonical open_public_tools and public_video_link_downloader.
Ensures parity, truthful error behavior, zero wallet mutation, and SSRF/safe delivery guards.
"""

from __future__ import annotations

import html
import ipaddress
import logging
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

    s = str(seed or "").strip()
    if not s:
        s = "toanaas_user"

    s_lower = s.lower()
    if any(s_lower.startswith(sch) for sch in DANGEROUS_SCHEMES) or "<script" in s_lower or "javascript:" in s_lower:
        return False, {
            "ok": False,
            "error_code": "AVATAR_UNSAFE_URL_BLOCKED",
            "message": "Mô tả hoặc seed avatar chứa ký tự không an toàn.",
        }, 400

    style_set_map = {
        "realistic": 1,
        "robot": 1,
        "illustration": 2,
        "monster": 2,
        "creator": 4,
        "cat": 4,
        "business": 5,
        "human": 5,
    }
    set_id = style_set_map.get(str(style or "").lower(), int(avatar_set or 1))
    set_id = max(1, min(5, set_id))

    try:
        avatar_url = opt.generate_avatar_ai_url(s, set_id)
    except Exception as exc:
        logger.warning("Avatar generation error: %s", exc)
        return False, {
            "ok": False,
            "error_code": "AVATAR_SOURCE_ERROR",
            "message": "Lỗi sinh URL ảnh đại diện AI.",
        }, 503

    return True, {
        "ok": True,
        "avatar_url": avatar_url,
        "seed": s,
        "avatar_set": set_id,
        "style": style,
    }, 200


# ─── 4. VIDEO DOWNLOADER ──────────────────────────────────────────────────────

def _get_downloader() -> PublicVideoLinkDownloader:
    # Use existing singleton/factory from bot if present
    return PublicVideoLinkDownloader()

def handle_downloader_inspect(url: str, requested_asset: str = "video") -> tuple[bool, dict[str, Any], int]:
    clean_url = str(url or "").strip()
    if not clean_url:
        return False, {
            "ok": False,
            "error_code": "DOWNLOADER_INVALID_URL",
            "message": "Liên kết không được để trống.",
        }, 400

    try:
        parsed = urlparse(clean_url)
    except Exception:
        parsed = None

    if not parsed or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False, {
            "ok": False,
            "error_code": "DOWNLOADER_UNSUPPORTED_OR_PRIVATE_URL_BLOCKED",
            "reason": "private_or_invalid",
            "message": "Liên kết không hợp lệ hoặc thiếu giao thức http/https.",
        }, 400

    host = (parsed.hostname or "").lower()
    if parsed.username or parsed.password or _is_private_host(host):
        return False, {
            "ok": False,
            "error_code": "DOWNLOADER_UNSUPPORTED_OR_PRIVATE_URL_BLOCKED",
            "reason": "private_or_invalid",
            "message": "Liên kết nội bộ, IP riêng tư hoặc loopback đã bị chặn.",
        }, 400

    downloader = _get_downloader()
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
    public_enabled = bool(globals().get("VIDEO_DOWNLOADER_PUBLIC_ENABLED", True))
    if not public_enabled:
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

    try:
        parsed = urlparse(clean_url)
    except Exception:
        parsed = None

    if not parsed or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False, {
            "ok": False,
            "error_code": "DOWNLOADER_UNSUPPORTED_OR_PRIVATE_URL_BLOCKED",
            "reason": "private_or_invalid",
            "message": "Liên kết không hợp lệ.",
        }, 400

    host = (parsed.hostname or "").lower()
    if parsed.username or parsed.password or _is_private_host(host):
        return False, {
            "ok": False,
            "error_code": "DOWNLOADER_UNSUPPORTED_OR_PRIVATE_URL_BLOCKED",
            "reason": "private_or_invalid",
            "message": "Liên kết nội bộ, IP riêng tư hoặc loopback đã bị chặn.",
        }, 400

    downloader = _get_downloader()
    detection = downloader.detect_link(clean_url)
    if not detection.get("ok"):
        return False, {
            "ok": False,
            "error_code": "DOWNLOADER_UNSUPPORTED_OR_PRIVATE_URL_BLOCKED",
            "reason": detection.get("reason", "unsupported_platform"),
            "message": "Nền tảng chưa được hỗ trợ.",
        }, 400

    public_enabled = bool(globals().get("VIDEO_DOWNLOADER_PUBLIC_ENABLED", True))
    if not public_enabled:
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

    # Ensure Safe Delivery:
    # Do NOT leak server-private filesystem paths
    return True, {
        "ok": True,
        "job_id": result.get("job_id", ""),
        "platform": result.get("platform") or detection.get("platform", ""),
        "kind": kind,
        "title": result.get("title", ""),
        "duration": result.get("duration", 0),
        "bytes": result.get("bytes", 0),
        "status": "ready",
        "charged_xu": 0,
        "rights_notice": VIDEO_DOWNLOADER_RIGHTS_COPY,
    }, 200
