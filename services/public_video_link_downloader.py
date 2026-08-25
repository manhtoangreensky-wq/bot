"""Public video-link downloader service for the Video Studio utility.

The service is intentionally narrow: it resolves public links, asks yt-dlp
only when needed, stores per-link artifacts, and never uses cookies or private
session data.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


VIDEO_LINK_DOWNLOADER_RIGHTS_COPY = "Vui lòng chỉ tải nội dung anh/chị có quyền sử dụng hoặc được phép lưu lại."
DIRECT_MEDIA_EXTENSIONS = (".mp4", ".mov", ".webm", ".mp3", ".m4a", ".aac", ".wav")
DIRECT_VIDEO_EXTENSIONS = (".mp4", ".mov", ".webm")
TIKTOK_SHORT_HOSTS = {"vt.tiktok.com", "vm.tiktok.com"}
SUPPORTED_PLATFORM_DOMAINS = {
    "tiktok": ("tiktok.com", "vt.tiktok.com", "vm.tiktok.com"),
    "facebook": ("facebook.com", "fb.watch", "m.facebook.com", "web.facebook.com"),
    "youtube": ("youtube.com", "youtu.be", "m.youtube.com", "youtube-nocookie.com"),
    "instagram": ("instagram.com",),
    "douyin": ("douyin.com",),
}
PLATFORM_LABELS = {
    "tiktok": "TikTok",
    "facebook": "Facebook",
    "youtube": "YouTube",
    "instagram": "Instagram",
    "douyin": "Douyin",
    "direct": "Direct video",
}
PRIVATE_OR_RESTRICTED_PATTERN = re.compile(
    r"(?:^|[/?&#._-])(private|paywall|drm|login_required|signin|required-login|members-only|login)(?:$|[/?&#._=-])",
    re.IGNORECASE,
)
TRACKING_QUERY_KEYS = {
    "_r",
    "checksum",
    "is_copy_url",
    "is_from_webapp",
    "lang",
    "preview_pb",
    "refer",
    "referer_url",
    "sec_user_id",
    "sender_device",
    "share_app_id",
    "share_iid",
    "share_item_id",
    "share_link_id",
    "share_token",
    "source",
    "timestamp",
    "tt_from",
    "u_code",
}
_LINK_DOWNLOAD_JOBS: dict[str, dict[str, Any]] = {}


@dataclass
class LinkDownloadRequest:
    url: str
    user_id: int | str = 0
    chat_id: int | str = 0
    requested_asset: str = "video"
    max_duration_seconds: int = 300
    max_input_mb: int = 100
    max_output_mb: int = 100
    platform: str = ""
    job_id: str = ""
    output_dir: str = ""


@dataclass
class LinkDownloadResult:
    ok: bool
    platform: str = ""
    title: str = ""
    duration: int = 0
    thumbnail_url: str = ""
    thumbnail_path: str = ""
    video_path: str = ""
    audio_path: str = ""
    cover_path: str = ""
    bytes: int = 0
    format: str = ""
    blocker: str = ""
    public_message: str = ""
    debug: dict[str, Any] = field(default_factory=dict)
    job_id: str = ""
    input_url: str = ""
    final_url: str = ""
    requested_asset: str = ""
    delivery_message_id: int = 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        asset = self.requested_asset or self.format
        if asset == "audio":
            data["file_path"] = self.audio_path
        elif asset in {"cover", "thumbnail"}:
            data["file_path"] = self.cover_path or self.thumbnail_path
        else:
            data["file_path"] = self.video_path
        data["duration_seconds"] = self.duration
        data["size_bytes"] = self.bytes
        data["reason"] = self.blocker
        data["kind"] = self.requested_asset
        return data


def _clean_url(value: str) -> str:
    return str(value or "").strip().strip("<>()[]{}\"'").rstrip(".,;!?")


def _host_matches(host: str, domains: tuple[str, ...]) -> bool:
    host = str(host or "").lower().lstrip(".")
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def _safe_host(url: str) -> str:
    try:
        return (urlparse(str(url or "")).hostname or "").lower()
    except Exception:
        return ""


def _is_private_host(host: str) -> bool:
    host = str(host or "").strip().lower().rstrip(".")
    if not host:
        return True
    if host in {"localhost", "0.0.0.0"} or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return bool(ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)
    except ValueError:
        return False


def _restricted_hint(parsed) -> bool:
    blob = f"{parsed.path or ''}?{parsed.query or ''}".lower()
    return bool(PRIVATE_OR_RESTRICTED_PATTERN.search(blob))


def _direct_media_path(path: str) -> bool:
    clean = str(path or "").lower()
    return any(clean.endswith(ext) for ext in DIRECT_MEDIA_EXTENSIONS)


def _direct_video_path(path: str) -> bool:
    clean = str(path or "").lower()
    return any(clean.endswith(ext) for ext in DIRECT_VIDEO_EXTENSIONS)


def _detect_platform_key(url: str) -> tuple[str, str, bool]:
    parsed = urlparse(_clean_url(url))
    host = (parsed.hostname or "").lower()
    if _direct_media_path(parsed.path or ""):
        return "direct", host, True
    for key, domains in SUPPORTED_PLATFORM_DOMAINS.items():
        if _host_matches(host, domains):
            return key, host, False
    return "", host, False


def _strip_tracking_query(url: str) -> str:
    parsed = urlparse(str(url or ""))
    kept = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith("utm_") or lowered in TRACKING_QUERY_KEYS:
            continue
        kept.append((key, value))
    return urlunparse(parsed._replace(query=urlencode(kept), fragment=""))


def _extract_tiktok_video_id(url: str) -> str:
    parsed = urlparse(str(url or ""))
    match = re.search(r"/video/(\d+)", parsed.path or "")
    if match:
        return match.group(1)
    match = re.search(r"/t/([^/?#]+)", parsed.path or "")
    return match.group(1) if match else ""


def _blocker_public_message(blocker: str) -> str:
    key = str(blocker or "").split(":", 1)[0]
    messages = {
        "unsupported_url": "TOAN AAS chưa hỗ trợ tải link này. Hệ thống chưa trừ Xu.",
        "unsupported_platform": "TOAN AAS chưa hỗ trợ tải link này. Hệ thống chưa trừ Xu.",
        "private_or_login_required": "TOAN AAS không tải được nội dung riêng tư hoặc cần đăng nhập. Hệ thống chưa trừ Xu.",
        "private_or_invalid": "TOAN AAS không tải được nội dung riêng tư hoặc cần đăng nhập. Hệ thống chưa trừ Xu.",
        "url_resolve_failed": "TOAN AAS chưa tải được link này lúc này. Hệ thống chưa trừ Xu.",
        "downloader_unavailable": "Bộ tải link đang tạm thời chưa sẵn sàng. Hệ thống chưa trừ Xu.",
        "adapter_missing": "Bộ tải link đang tạm thời chưa sẵn sàng. Hệ thống chưa trừ Xu.",
        "file_too_large": "File vượt giới hạn dung lượng hiện tại. Hệ thống chưa trừ Xu.",
        "too_large": "File vượt giới hạn dung lượng hiện tại. Hệ thống chưa trừ Xu.",
        "duration_too_long": "Video vượt giới hạn thời lượng hiện tại. Hệ thống chưa trừ Xu.",
        "cover_unavailable": "Link này chưa có ảnh bìa có thể tải. Hệ thống chưa trừ Xu.",
        "empty_download": "TOAN AAS chưa tải được file hợp lệ từ link này. Hệ thống chưa trừ Xu.",
        "metadata_failed": "TOAN AAS chưa lấy được thông tin link này lúc này. Hệ thống chưa trừ Xu.",
        "download_failed": "TOAN AAS chưa tải được link này lúc này. Hệ thống chưa trừ Xu.",
    }
    return messages.get(key, "TOAN AAS chưa tải được link này lúc này. Hệ thống chưa trừ Xu.")


def _looks_private_error(exc: Exception | str) -> bool:
    text = str(exc or "").lower()
    return any(token in text for token in ("private", "login", "sign in", "members-only", "not available", "permission"))


def _lazy_import_yt_dlp():
    try:
        import yt_dlp  # type: ignore
    except Exception:
        return None
    return yt_dlp


class _TrackingRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self) -> None:
        super().__init__()
        self.redirect_count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.redirect_count += 1
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class PublicVideoLinkDownloader:
    def __init__(
        self,
        *,
        data_dir: str | os.PathLike | None = None,
        max_input_mb: int = 100,
        max_output_mb: int = 100,
        max_duration_seconds: int = 300,
        timeout_seconds: int = 30,
    ) -> None:
        self.data_dir = Path(data_dir or os.getenv("LINKDL_DATA_DIR") or "data/link_downloads")
        self.max_input_mb = max(1, int(max_input_mb or 100))
        self.max_output_mb = max(1, int(max_output_mb or self.max_input_mb))
        self.max_duration_seconds = max(1, int(max_duration_seconds or 300))
        self.timeout_seconds = max(5, int(timeout_seconds or 30))

    @property
    def max_input_bytes(self) -> int:
        return self.max_input_mb * 1024 * 1024

    @property
    def max_output_bytes(self) -> int:
        return self.max_output_mb * 1024 * 1024

    def _job_dir(self, job_id: str) -> Path:
        return self.data_dir / str(job_id or "").strip()

    def _new_job_id(self) -> str:
        return "LDL" + time.strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:8].upper()

    def _save_job(self, job: dict[str, Any]) -> dict[str, Any]:
        job_id = str(job.get("job_id") or self._new_job_id())
        now = int(time.time())
        current = dict(_LINK_DOWNLOAD_JOBS.get(job_id) or {})
        current.update(job)
        current["job_id"] = job_id
        current.setdefault("created_at", now)
        current["updated_at"] = now
        _LINK_DOWNLOAD_JOBS[job_id] = current
        try:
            job_dir = self._job_dir(job_id)
            job_dir.mkdir(parents=True, exist_ok=True)
            (job_dir / "job.json").write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
        return dict(current)

    def get_job(self, job_id: str) -> dict[str, Any]:
        job_id = str(job_id or "").strip()
        if not job_id:
            return {}
        if job_id in _LINK_DOWNLOAD_JOBS:
            return dict(_LINK_DOWNLOAD_JOBS[job_id])
        path = self._job_dir(job_id) / "job.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                _LINK_DOWNLOAD_JOBS[job_id] = payload
                return dict(payload)
        except (OSError, json.JSONDecodeError):
            return {}
        return {}

    def detect_link(self, url: str) -> dict[str, Any]:
        clean = _clean_url(url)
        try:
            parsed = urlparse(clean)
        except Exception:
            parsed = None
        if not parsed or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return {"ok": False, "url": clean, "platform": "", "host": "", "reason": "private_or_invalid", "public_supported": False}
        host = (parsed.hostname or "").lower()
        if parsed.username or parsed.password or _is_private_host(host) or _restricted_hint(parsed):
            return {"ok": False, "url": clean, "platform": "", "host": host, "reason": "private_or_invalid", "public_supported": False}
        platform_key, detected_host, direct = _detect_platform_key(clean)
        if not platform_key:
            return {"ok": False, "url": clean, "platform": "", "host": detected_host, "reason": "unsupported_platform", "public_supported": False}
        return {
            "ok": True,
            "url": clean,
            "platform": PLATFORM_LABELS.get(platform_key, platform_key.title()),
            "platform_key": platform_key,
            "host": detected_host,
            "reason": "",
            "direct_video": bool(direct and _direct_video_path(parsed.path or "")),
            "direct_media": bool(direct),
            "public_supported": True,
        }

    def _follow_redirects(self, url: str) -> tuple[str, int, int]:
        handler = _TrackingRedirectHandler()
        opener = urllib.request.build_opener(handler)
        request = urllib.request.Request(url, method="GET", headers={"User-Agent": "Mozilla/5.0 TOAN-AAS-LinkDL/1.0"})
        with opener.open(request, timeout=self.timeout_seconds) as response:
            final_url = response.geturl() or url
            status = int(getattr(response, "status", 0) or getattr(response, "code", 0) or 0)
            return final_url, handler.redirect_count, status

    def resolve_url(self, url: str) -> dict[str, Any]:
        detection = self.detect_link(url)
        clean = detection.get("url") or _clean_url(url)
        if not detection.get("ok"):
            return {
                "ok": False,
                "input_url": clean,
                "final_url": "",
                "platform": detection.get("platform") or "",
                "platform_key": detection.get("platform_key") or "",
                "host": detection.get("host") or "",
                "resolver_status": "blocked",
                "redirect_count": 0,
                "http_status": 0,
                "blocker": detection.get("reason") or "unsupported_url",
                "reason": detection.get("reason") or "unsupported_url",
            }
        final_url = clean
        redirect_count = 0
        http_status = 0
        resolver_status = "not_required"
        if detection.get("host") in TIKTOK_SHORT_HOSTS:
            resolver_status = "resolve_failed"
            try:
                final_url, redirect_count, http_status = self._follow_redirects(clean)
                resolver_status = "resolved"
            except Exception:
                return {
                    "ok": False,
                    "input_url": clean,
                    "final_url": "",
                    "platform": "TikTok",
                    "platform_key": "tiktok",
                    "host": detection.get("host") or "",
                    "resolver_status": "resolve_failed",
                    "redirect_count": redirect_count,
                    "http_status": http_status,
                    "blocker": "url_resolve_failed",
                    "reason": "url_resolve_failed",
                }
        final_url = _strip_tracking_query(final_url)
        final_detection = self.detect_link(final_url)
        if not final_detection.get("ok"):
            return {
                "ok": False,
                "input_url": clean,
                "final_url": final_url,
                "platform": detection.get("platform") or "",
                "platform_key": detection.get("platform_key") or "",
                "host": _safe_host(final_url),
                "resolver_status": "unsupported_final",
                "redirect_count": redirect_count,
                "http_status": http_status,
                "blocker": "unsupported_url",
                "reason": "unsupported_url",
            }
        platform_key = final_detection.get("platform_key") or detection.get("platform_key") or ""
        return {
            "ok": True,
            "input_url": clean,
            "final_url": final_url,
            "platform": final_detection.get("platform") or detection.get("platform") or "",
            "platform_key": platform_key,
            "host": final_detection.get("host") or _safe_host(final_url),
            "resolver_status": resolver_status,
            "redirect_count": redirect_count,
            "http_status": http_status,
            "video_id": _extract_tiktok_video_id(final_url) if platform_key == "tiktok" else "",
            "direct_video": bool(final_detection.get("direct_video")),
            "direct_media": bool(final_detection.get("direct_media")),
            "reason": "",
        }

    def _tikwm_metadata(self, url: str) -> dict | None:
        try:
            api_url = "https://www.tikwm.com/api/?url=" + urllib.parse.quote(url)
            req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as res:
                data = json.loads(res.read())
                if data.get("code") == 0 and data.get("data"):
                    info = data["data"]
                    return {
                        "ok": True,
                        "title": str(info.get("title") or ""),
                        "author": str(info.get("author", {}).get("nickname") or ""),
                        "duration_seconds": int(info.get("duration") or 0),
                        "size_bytes": int(info.get("size") or 0),
                        "thumbnail_url": str(info.get("cover") or ""),
                        "format": "mp4",
                        "id": str(info.get("id") or ""),
                    }
        except Exception:
            pass
        return None

    def _tikwm_download(self, url: str, asset: str, output_dir: Path, limit_bytes: int) -> tuple[Path | None, str]:
        try:
            api_url = "https://www.tikwm.com/api/?url=" + urllib.parse.quote(url)
            req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as res:
                data = json.loads(res.read())
                if data.get("code") == 0 and data.get("data"):
                    info = data["data"]
                    dl_url = info.get("play")
                    suffix = ".mp4"
                    if asset == "audio":
                        dl_url = info.get("music")
                        suffix = ".mp3"
                    if dl_url:
                        target = output_dir / f"{asset}{suffix}"
                        self._download_url_to_file(dl_url, target, limit_bytes)
                        return target, ""
        except Exception:
            pass
        return None, "tikwm_failed"

    def _direct_metadata(self, resolved: dict[str, Any], request: LinkDownloadRequest) -> dict[str, Any]:
        size_bytes = 0
        url = str(resolved.get("final_url") or resolved.get("input_url") or request.url)
        try:
            head = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0 TOAN-AAS-LinkDL/1.0"})
            with urllib.request.urlopen(head, timeout=self.timeout_seconds) as response:
                size_bytes = int(response.headers.get("content-length") or 0)
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            size_bytes = 0
        return {
            "ok": True,
            "title": Path(urlparse(url).path).name or "direct-media",
            "duration_seconds": 0,
            "size_bytes": size_bytes,
            "thumbnail_url": "",
            "format": Path(urlparse(url).path).suffix.lstrip(".") or "media",
        }

    def _metadata_from_ytdlp(self, url: str) -> tuple[dict[str, Any] | None, str]:
        yt_dlp = _lazy_import_yt_dlp()
        if yt_dlp is None:
            return None, "downloader_unavailable"
        try:
            opts = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "skip_download": True,
                "cachedir": False,
                "socket_timeout": self.timeout_seconds,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as exc:
            return None, "private_or_login_required" if _looks_private_error(exc) else "metadata_failed"
        if not isinstance(info, dict):
            return None, "metadata_failed"
        size_bytes = int(info.get("filesize") or info.get("filesize_approx") or 0)
        if not size_bytes:
            for item in info.get("requested_formats") or []:
                if isinstance(item, dict):
                    size_bytes += int(item.get("filesize") or item.get("filesize_approx") or 0)
        thumbnail = str(info.get("thumbnail") or "")
        if not thumbnail:
            thumbs = [item for item in info.get("thumbnails") or [] if isinstance(item, dict) and item.get("url")]
            if thumbs:
                thumbnail = str(thumbs[-1].get("url") or "")
        return {
            "ok": True,
            "title": str(info.get("title") or ""),
            "author": str(info.get("uploader") or info.get("channel") or ""),
            "duration_seconds": int(info.get("duration") or 0),
            "size_bytes": size_bytes,
            "thumbnail_url": thumbnail,
            "format": str(info.get("ext") or ""),
            "id": str(info.get("id") or ""),
        }, ""

    def metadata(self, url_or_request: str | LinkDownloadRequest) -> dict[str, Any]:
        request = url_or_request if isinstance(url_or_request, LinkDownloadRequest) else LinkDownloadRequest(url=str(url_or_request or ""))
        request.max_duration_seconds = request.max_duration_seconds or self.max_duration_seconds
        request.max_input_mb = request.max_input_mb or self.max_input_mb
        resolved = self.resolve_url(request.url)
        if not resolved.get("ok"):
            blocker = str(resolved.get("blocker") or "unsupported_url")
            return {
                "ok": False,
                "url": request.url,
                "final_url": resolved.get("final_url") or "",
                "platform": resolved.get("platform") or "",
                "reason": blocker,
                "blocker": blocker,
                "public_message": _blocker_public_message(blocker),
                "resolver": resolved,
            }
        if resolved.get("direct_media"):
            metadata = self._direct_metadata(resolved, request)
        else:
            final_url_str = str(resolved.get("final_url") or request.url)
            if resolved.get("platform") == "TikTok" or "tiktok" in final_url_str.lower():
                tk_meta = self._tikwm_metadata(final_url_str)
                if tk_meta:
                    metadata = tk_meta
                    blocker = ""
                else:
                    metadata, blocker = self._metadata_from_ytdlp(final_url_str)
            else:
                metadata, blocker = self._metadata_from_ytdlp(final_url_str)
            if metadata is None:
                return {
                    "ok": False,
                    "url": request.url,
                    "final_url": resolved.get("final_url") or "",
                    "platform": resolved.get("platform") or "",
                    "reason": blocker,
                    "blocker": blocker,
                    "public_message": _blocker_public_message(blocker),
                    "resolver": resolved,
                }
        duration = int(metadata.get("duration_seconds") or 0)
        size_bytes = int(metadata.get("size_bytes") or 0)
        if duration and duration > int(request.max_duration_seconds or self.max_duration_seconds):
            return {**metadata, "ok": False, "platform": resolved.get("platform") or "", "reason": "duration_too_long", "blocker": "duration_too_long", "public_message": _blocker_public_message("duration_too_long"), "resolver": resolved}
        if size_bytes and size_bytes > int(request.max_input_mb or self.max_input_mb) * 1024 * 1024:
            return {**metadata, "ok": False, "platform": resolved.get("platform") or "", "reason": "file_too_large", "blocker": "file_too_large", "public_message": _blocker_public_message("file_too_large"), "resolver": resolved}
        return {
            **metadata,
            "ok": True,
            "url": request.url,
            "final_url": resolved.get("final_url") or "",
            "platform": resolved.get("platform") or "",
            "reason": "",
            "blocker": "",
            "public_message": "",
            "resolver": resolved,
            "thumbnail_url": metadata.get("thumbnail_url") or "",
        }

    def prepare(self, request: LinkDownloadRequest) -> LinkDownloadResult:
        job_id = request.job_id or self._new_job_id()
        metadata = self.metadata(request)
        resolved = dict(metadata.get("resolver") or {})
        job = {
            "job_id": job_id,
            "input_url": request.url,
            "final_url": metadata.get("final_url") or resolved.get("final_url") or "",
            "platform": metadata.get("platform") or resolved.get("platform") or request.platform or "",
            "resolver_status": resolved.get("resolver_status") or "",
            "redirect_count": int(resolved.get("redirect_count") or 0),
            "http_status": int(resolved.get("http_status") or 0),
            "metadata_status": "ok" if metadata.get("ok") else "failed",
            "requested_asset": request.requested_asset,
            "title": metadata.get("title") or "",
            "duration": int(metadata.get("duration_seconds") or 0),
            "thumbnail_url": metadata.get("thumbnail_url") or "",
            "blocker": metadata.get("blocker") or metadata.get("reason") or "",
            "output_bytes": int(metadata.get("size_bytes") or 0),
            "user_id": str(request.user_id or ""),
            "chat_id": str(request.chat_id or ""),
        }
        self._save_job(job)
        blocker = str(job.get("blocker") or "")
        return LinkDownloadResult(
            ok=bool(metadata.get("ok")),
            platform=str(job.get("platform") or ""),
            title=str(job.get("title") or ""),
            duration=int(job.get("duration") or 0),
            thumbnail_url=str(job.get("thumbnail_url") or ""),
            bytes=int(job.get("output_bytes") or 0),
            format=str(metadata.get("format") or ""),
            blocker=blocker,
            public_message=_blocker_public_message(blocker) if blocker else "",
            debug={"resolver": resolved, "metadata": metadata},
            job_id=job_id,
            input_url=request.url,
            final_url=str(job.get("final_url") or ""),
            requested_asset=request.requested_asset,
        )

    def _valid_cached_path(self, path: str) -> bool:
        try:
            return bool(path and Path(path).is_file() and Path(path).stat().st_size > 0)
        except OSError:
            return False

    def _download_url_to_file(self, url: str, output_path: Path, limit_bytes: int) -> int:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 TOAN-AAS-LinkDL/1.0"})
        total = 0
        try:
            with urllib.request.urlopen(request, timeout=120) as response, output_path.open("wb") as handle:
                content_length = int(response.headers.get("content-length") or 0)
                if content_length and content_length > limit_bytes:
                    raise ValueError("file_too_large")
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > limit_bytes:
                        raise ValueError("file_too_large")
                    handle.write(chunk)
        except Exception:
            try:
                output_path.unlink()
            except OSError:
                pass
            raise
        if total <= 0:
            raise ValueError("empty_download")
        return total

    def _latest_file(self, directory: Path, asset: str = "video") -> Path | None:
        files = [item for item in directory.glob("*") if item.is_file() and item.name != "job.json"]
        if not files:
            return None
        if asset == "audio":
            audio_files = [p for p in files if p.suffix.lower() in {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac"}]
            if audio_files:
                return max(audio_files, key=lambda item: item.stat().st_mtime)
        elif asset == "video":
            video_files = [p for p in files if p.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm", ".m4v"}]
            if video_files:
                return max(video_files, key=lambda item: item.stat().st_mtime)
        elif asset in {"cover", "thumbnail"}:
            img_files = [p for p in files if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]
            if img_files:
                return max(img_files, key=lambda item: item.stat().st_mtime)
        return max(files, key=lambda item: item.stat().st_mtime)

    def _download_with_ytdlp(self, url: str, asset: str, output_dir: Path, limit_bytes: int | None = None) -> tuple[Path | None, str]:
        yt_dlp = _lazy_import_yt_dlp()
        if yt_dlp is None:
            return None, "downloader_unavailable"
        limit_bytes = int(limit_bytes or self.max_output_bytes)
        outtmpl = str(output_dir / "toan_aas_%(id)s.%(ext)s")
        opts: dict[str, Any] = {
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "cachedir": False,
            "socket_timeout": self.timeout_seconds,
            "max_filesize": limit_bytes,
        }
        ffmpeg_path = shutil.which("ffmpeg") or os.environ.get("FFMPEG_PATH")
        if ffmpeg_path:
            opts["ffmpeg_location"] = ffmpeg_path

        if asset == "audio":
            opts["format"] = "bestaudio/best[acodec!=none]/best"
            if ffmpeg_path:
                opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }]
        else:
            if ffmpeg_path:
                opts["merge_output_format"] = "mp4"
                opts["format"] = "bestvideo+bestaudio/best[acodec!=none]/best[ext=mp4]/best"
            else:
                opts["format"] = "best[acodec!=none]/best[ext=mp4]/best"
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.extract_info(url, download=True)
        except Exception as exc:
            return None, "private_or_login_required" if _looks_private_error(exc) else "download_failed"
        return self._latest_file(output_dir, asset=asset), ""

    def download(
        self,
        request_or_url: LinkDownloadRequest | str,
        kind: str | None = None,
        output_dir: str | os.PathLike | None = None,
    ) -> dict[str, Any]:
        if isinstance(request_or_url, LinkDownloadRequest):
            request = request_or_url
        else:
            request = LinkDownloadRequest(url=str(request_or_url or ""), requested_asset=str(kind or "video"), output_dir=str(output_dir or ""))
        asset = str(request.requested_asset or kind or "video").strip().lower()
        if asset == "thumbnail":
            asset = "cover"
        if asset not in {"video", "audio", "cover"}:
            return LinkDownloadResult(False, blocker="unsupported_format", public_message=_blocker_public_message("unsupported_url"), requested_asset=asset).to_dict()
        request.requested_asset = asset
        request.max_duration_seconds = request.max_duration_seconds or self.max_duration_seconds
        request.max_input_mb = request.max_input_mb or self.max_input_mb
        request.max_output_mb = request.max_output_mb or self.max_output_mb
        output_limit_bytes = max(1, int(request.max_output_mb or self.max_output_mb)) * 1024 * 1024
        prepared = self.prepare(request)
        job_id = prepared.job_id
        job = self.get_job(job_id)
        asset_key = "cover_path" if asset == "cover" else f"{asset}_path"
        cached = str(job.get(asset_key) or "")
        if self._valid_cached_path(cached):
            size = Path(cached).stat().st_size
            result = LinkDownloadResult(
                True,
                platform=prepared.platform,
                title=prepared.title,
                duration=prepared.duration,
                thumbnail_url=prepared.thumbnail_url,
                video_path=cached if asset == "video" else str(job.get("video_path") or ""),
                audio_path=cached if asset == "audio" else str(job.get("audio_path") or ""),
                cover_path=cached if asset == "cover" else str(job.get("cover_path") or ""),
                bytes=size,
                format=Path(cached).suffix.lstrip("."),
                debug={"cache_reused": True},
                job_id=job_id,
                input_url=prepared.input_url,
                final_url=prepared.final_url,
                requested_asset=asset,
            )
            return result.to_dict()
        if not prepared.ok:
            return prepared.to_dict()
        job_dir = Path(request.output_dir) if request.output_dir else self._job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        final_url = prepared.final_url or request.url
        metadata = dict(prepared.debug.get("metadata") or {})
        try:
            if asset == "cover":
                thumbnail = str(prepared.thumbnail_url or metadata.get("thumbnail_url") or "")
                if not thumbnail:
                    blocker = "cover_unavailable"
                    result = LinkDownloadResult(False, platform=prepared.platform, blocker=blocker, public_message=_blocker_public_message(blocker), job_id=job_id, input_url=request.url, final_url=final_url, requested_asset=asset)
                    self._save_job({**job, "blocker": blocker, "requested_asset": asset})
                    return result.to_dict()
                suffix = Path(urlparse(thumbnail).path).suffix or ".jpg"
                target = job_dir / f"cover{suffix}"
                bytes_written = self._download_url_to_file(thumbnail, target, output_limit_bytes)
                file_path = target
            elif metadata.get("resolver", {}).get("direct_media"):
                suffix = Path(urlparse(final_url).path).suffix or ".mp4"
                target = job_dir / f"{asset}{suffix}"
                bytes_written = self._download_url_to_file(final_url, target, output_limit_bytes)
                file_path = target
            else:
                final_url_str = str(final_url)
                if prepared.platform == "TikTok" or "tiktok" in final_url_str.lower():
                    file_path, blocker = self._tikwm_download(final_url_str, asset, job_dir, output_limit_bytes)
                    if not file_path:
                        file_path, blocker = self._download_with_ytdlp(final_url_str, asset, job_dir, output_limit_bytes)
                else:
                    file_path, blocker = self._download_with_ytdlp(final_url_str, asset, job_dir, output_limit_bytes)
                if blocker:
                    result = LinkDownloadResult(False, platform=prepared.platform, blocker=blocker, public_message=_blocker_public_message(blocker), job_id=job_id, input_url=request.url, final_url=final_url, requested_asset=asset)
                    self._save_job({**job, "blocker": blocker, "requested_asset": asset})
                    return result.to_dict()
                if not file_path or not file_path.is_file():
                    raise ValueError("empty_download")
                bytes_written = file_path.stat().st_size
            if bytes_written <= 0:
                raise ValueError("empty_download")
            if bytes_written > output_limit_bytes:
                raise ValueError("file_too_large")
        except ValueError as exc:
            blocker = str(exc) if str(exc) in {"file_too_large", "empty_download"} else "download_failed"
            result = LinkDownloadResult(False, platform=prepared.platform, blocker=blocker, public_message=_blocker_public_message(blocker), job_id=job_id, input_url=request.url, final_url=final_url, requested_asset=asset)
            self._save_job({**job, "blocker": blocker, "requested_asset": asset})
            return result.to_dict()
        except Exception as exc:
            blocker = "private_or_login_required" if _looks_private_error(exc) else "download_failed"
            result = LinkDownloadResult(False, platform=prepared.platform, blocker=blocker, public_message=_blocker_public_message(blocker), job_id=job_id, input_url=request.url, final_url=final_url, requested_asset=asset)
            self._save_job({**job, "blocker": blocker, "requested_asset": asset})
            return result.to_dict()
        file_path_str = str(file_path)
        job_update = {
            **job,
            "job_id": job_id,
            "input_url": prepared.input_url,
            "final_url": final_url,
            "platform": prepared.platform,
            "requested_asset": asset,
            "status": "downloaded",
            "blocker": "",
            "output_bytes": int(bytes_written),
            asset_key: file_path_str,
        }
        self._save_job(job_update)
        result = LinkDownloadResult(
            True,
            platform=prepared.platform,
            title=prepared.title,
            duration=prepared.duration,
            thumbnail_url=prepared.thumbnail_url,
            video_path=file_path_str if asset == "video" else str(job_update.get("video_path") or ""),
            audio_path=file_path_str if asset == "audio" else str(job_update.get("audio_path") or ""),
            cover_path=file_path_str if asset == "cover" else str(job_update.get("cover_path") or ""),
            bytes=int(bytes_written),
            format=Path(file_path_str).suffix.lstrip("."),
            debug={"cache_reused": False},
            job_id=job_id,
            input_url=prepared.input_url,
            final_url=final_url,
            requested_asset=asset,
        )
        return result.to_dict()

    def mark_delivered(self, job_id: str, *, message_id: int = 0, method: str = "", asset: str = "") -> dict[str, Any]:
        job = self.get_job(job_id)
        if not job:
            return {}
        delivered = dict(job.get("delivered_assets") or {})
        if asset:
            delivered[str(asset)] = {"message_id": int(message_id or 0), "method": method, "ts": int(time.time())}
        job.update({
            "delivery_message_id": int(message_id or 0),
            "telegram_send_method": method,
            "delivered_assets": delivered,
            "status": "delivered",
        })
        return self._save_job(job)

    def audit(self) -> dict[str, Any]:
        return {
            "downloader_available": True,
            "yt_dlp_available": _lazy_import_yt_dlp() is not None,
            "supported_platforms": ["TikTok", "Facebook", "YouTube", "Instagram", "Douyin", "Direct video"],
            "tiktok_shortlink_supported": True,
            "direct_mp4_supported": True,
            "max_mb": self.max_output_mb,
            "max_duration": self.max_duration_seconds,
            "telegram_fallback_enabled": True,
            "no_cookie_required": True,
            "no_private_bypass": True,
        }

    def status(self, job_id: str) -> dict[str, Any]:
        job = self.get_job(job_id)
        if not job:
            return {"ok": False, "job_id": str(job_id or ""), "blocker": "job_not_found"}
        return {
            "ok": True,
            "job_id": job.get("job_id") or "",
            "platform": job.get("platform") or "",
            "input_url_host": _safe_host(str(job.get("input_url") or "")),
            "final_url_host": _safe_host(str(job.get("final_url") or "")),
            "resolver_status": job.get("resolver_status") or "",
            "metadata_status": job.get("metadata_status") or "",
            "requested_asset": job.get("requested_asset") or "",
            "local_video_path_exists": self._valid_cached_path(str(job.get("video_path") or "")),
            "local_audio_path_exists": self._valid_cached_path(str(job.get("audio_path") or "")),
            "cover_path_exists": self._valid_cached_path(str(job.get("cover_path") or "")),
            "output_bytes": int(job.get("output_bytes") or 0),
            "duration": int(job.get("duration") or 0),
            "blocker": job.get("blocker") or "",
            "delivery_message_id": int(job.get("delivery_message_id") or 0),
        }

    @staticmethod
    def cleanup_temp_files(paths, *, enabled: bool = True) -> int:
        if not enabled:
            return 0
        removed = 0
        for item in paths or []:
            path = Path(str(item or ""))
            try:
                if path.is_file():
                    path.unlink()
                    removed += 1
                parent = path.parent
                if parent.exists() and parent.is_dir() and parent.name.startswith("toan_aas_video_downloader_"):
                    shutil.rmtree(parent, ignore_errors=True)
            except OSError:
                continue
        return removed


def public_message_for_blocker(blocker: str) -> str:
    return _blocker_public_message(blocker)
