"""Safe public video-link downloader adapter.

This module is intentionally separate from AI/video/subtitle providers.  It
detects public video links, can fetch metadata/download through yt-dlp when
enabled by the bot config, and owns temp-file cleanup for this tool only.
"""

from __future__ import annotations

import ipaddress
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse


VIDEO_DOWNLOADER_RIGHTS_COPY = "Vui lòng chỉ tải nội dung anh/chị có quyền sử dụng hoặc được phép lưu lại."
DIRECT_VIDEO_EXTENSIONS = (".mp4", ".mov", ".webm")
SUPPORTED_PLATFORM_DOMAINS = {
    "TikTok": ("tiktok.com", "vt.tiktok.com", "vm.tiktok.com"),
    "Facebook": ("facebook.com", "fb.watch", "m.facebook.com", "web.facebook.com"),
    "YouTube": ("youtube.com", "youtu.be", "m.youtube.com", "youtube-nocookie.com"),
    "Instagram": ("instagram.com",),
    "Douyin": ("douyin.com",),
}
RESTRICTED_HINT_PATTERN = re.compile(
    r"(?:^|[/?&#._-])(private|paywall|drm|login_required|signin|required-login|members-only)(?:$|[/?&#._=-])",
    re.IGNORECASE,
)


@dataclass
class VideoDownloaderDetection:
    ok: bool
    url: str
    platform: str = ""
    host: str = ""
    reason: str = ""
    direct_video: bool = False
    public_supported: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VideoDownloaderMetadata:
    ok: bool
    url: str
    platform: str = ""
    title: str = ""
    duration_seconds: int = 0
    size_bytes: int = 0
    thumbnail_url: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _clean_url(value: str) -> str:
    return str(value or "").strip().strip("<>()[]{}\"'").rstrip(".,;!?")


def _host_matches(host: str, domains: tuple[str, ...]) -> bool:
    host = str(host or "").lower().lstrip(".")
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def _is_direct_video_path(path: str) -> bool:
    clean_path = unquote(str(path or "")).lower()
    return any(clean_path.endswith(ext) for ext in DIRECT_VIDEO_EXTENSIONS)


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
    return bool(RESTRICTED_HINT_PATTERN.search(blob))


class VideoDownloaderProvider:
    """Downloader adapter used by the public Video Studio link tool."""

    def __init__(
        self,
        *,
        max_mb: int = 100,
        max_duration_seconds: int = 300,
        temp_cleanup: bool = True,
    ) -> None:
        self.max_mb = max(1, int(max_mb or 100))
        self.max_duration_seconds = max(1, int(max_duration_seconds or 300))
        self.temp_cleanup = bool(temp_cleanup)

    @property
    def max_bytes(self) -> int:
        return int(self.max_mb) * 1024 * 1024

    def detect_link(self, url: str) -> dict:
        clean_url = _clean_url(url)
        try:
            parsed = urlparse(clean_url)
        except Exception:
            parsed = None
        if not parsed or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return VideoDownloaderDetection(False, clean_url, reason="private_or_invalid").to_dict()
        host = (parsed.hostname or "").lower()
        if parsed.username or parsed.password or _is_private_host(host) or _restricted_hint(parsed):
            return VideoDownloaderDetection(False, clean_url, host=host, reason="private_or_invalid").to_dict()
        if _is_direct_video_path(parsed.path):
            return VideoDownloaderDetection(
                True,
                clean_url,
                platform="Direct video",
                host=host,
                direct_video=True,
                public_supported=True,
            ).to_dict()
        for platform, domains in SUPPORTED_PLATFORM_DOMAINS.items():
            if _host_matches(host, domains):
                return VideoDownloaderDetection(
                    True,
                    clean_url,
                    platform=platform,
                    host=host,
                    public_supported=True,
                ).to_dict()
        return VideoDownloaderDetection(False, clean_url, host=host, reason="unsupported_platform").to_dict()

    def _direct_metadata(self, detection: dict) -> VideoDownloaderMetadata:
        size_bytes = 0
        req = urllib.request.Request(str(detection.get("url") or ""), method="HEAD", headers={"User-Agent": "TOAN-AAS-Bot/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                size_bytes = int(response.headers.get("content-length") or 0)
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            size_bytes = 0
        if size_bytes and size_bytes > self.max_bytes:
            return VideoDownloaderMetadata(
                False,
                detection.get("url", ""),
                platform=detection.get("platform", ""),
                size_bytes=size_bytes,
                reason="too_large",
            )
        return VideoDownloaderMetadata(
            True,
            detection.get("url", ""),
            platform=detection.get("platform", ""),
            title=Path(urlparse(str(detection.get("url") or "")).path).name or "direct-video",
            size_bytes=size_bytes,
        )

    def metadata(self, url: str) -> dict:
        detection = self.detect_link(url)
        if not detection.get("ok"):
            return VideoDownloaderMetadata(
                False,
                detection.get("url", _clean_url(url)),
                platform=detection.get("platform", ""),
                reason=detection.get("reason") or "unsupported_platform",
            ).to_dict()
        if detection.get("direct_video"):
            return self._direct_metadata(detection).to_dict()
        try:
            import yt_dlp
        except Exception:
            return VideoDownloaderMetadata(
                False,
                detection["url"],
                platform=detection.get("platform", ""),
                reason="adapter_missing",
            ).to_dict()
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True}) as ydl:
                info = ydl.extract_info(detection["url"], download=False)
        except Exception as exc:
            return VideoDownloaderMetadata(
                False,
                detection["url"],
                platform=detection.get("platform", ""),
                reason=f"metadata_failed:{type(exc).__name__}",
            ).to_dict()
        duration = int(info.get("duration") or 0)
        size_bytes = int(info.get("filesize") or info.get("filesize_approx") or 0)
        if duration and duration > self.max_duration_seconds:
            return VideoDownloaderMetadata(
                False,
                detection["url"],
                platform=detection.get("platform", ""),
                title=str(info.get("title") or ""),
                duration_seconds=duration,
                size_bytes=size_bytes,
                thumbnail_url=str(info.get("thumbnail") or ""),
                reason="duration_too_long",
            ).to_dict()
        if size_bytes and size_bytes > self.max_bytes:
            return VideoDownloaderMetadata(
                False,
                detection["url"],
                platform=detection.get("platform", ""),
                title=str(info.get("title") or ""),
                duration_seconds=duration,
                size_bytes=size_bytes,
                thumbnail_url=str(info.get("thumbnail") or ""),
                reason="too_large",
            ).to_dict()
        return VideoDownloaderMetadata(
            True,
            detection["url"],
            platform=detection.get("platform", ""),
            title=str(info.get("title") or ""),
            duration_seconds=duration,
            size_bytes=size_bytes,
            thumbnail_url=str(info.get("thumbnail") or ""),
        ).to_dict()

    def _download_url_to_temp(self, url: str, suffix: str, output_dir: Path) -> str:
        output_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix="toan_aas_link_", suffix=suffix, dir=str(output_dir))
        os.close(fd)
        total = 0
        req = urllib.request.Request(url, headers={"User-Agent": "TOAN-AAS-Bot/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=120) as response, open(tmp_path, "wb") as handle:
                content_length = int(response.headers.get("content-length") or 0)
                if content_length and content_length > self.max_bytes:
                    raise ValueError("too_large")
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > self.max_bytes:
                        raise ValueError("too_large")
                    handle.write(chunk)
            if total <= 0:
                raise ValueError("empty_download")
            return tmp_path
        except Exception:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise

    def _latest_downloaded_file(self, output_dir: Path) -> str:
        files = [path for path in output_dir.glob("*") if path.is_file()]
        if not files:
            return ""
        return str(max(files, key=lambda item: item.stat().st_mtime))

    def download(self, url: str, kind: str = "video", output_dir: str | os.PathLike | None = None) -> dict:
        kind = str(kind or "video").strip().lower()
        if kind not in {"video", "audio", "cover"}:
            return {"ok": False, "reason": "unsupported_format"}
        detection = self.detect_link(url)
        if not detection.get("ok"):
            return {"ok": False, "reason": detection.get("reason") or "unsupported_platform", "detection": detection}
        output_path = Path(output_dir or tempfile.mkdtemp(prefix="toan_aas_video_downloader_"))
        metadata = self.metadata(detection["url"])
        if not metadata.get("ok") and metadata.get("reason") in {"too_large", "duration_too_long", "private_or_invalid", "unsupported_platform"}:
            return {"ok": False, "reason": metadata.get("reason"), "metadata": metadata, "detection": detection}
        try:
            if kind == "cover":
                thumbnail = str(metadata.get("thumbnail_url") or "")
                if not thumbnail:
                    return {"ok": False, "reason": "cover_unavailable", "metadata": metadata, "detection": detection}
                suffix = Path(urlparse(thumbnail).path).suffix or ".jpg"
                file_path = self._download_url_to_temp(thumbnail, suffix, output_path)
                return {"ok": True, "kind": "cover", "file_path": file_path, "metadata": metadata, "detection": detection}
            if detection.get("direct_video") and kind == "video":
                suffix = Path(urlparse(detection["url"]).path).suffix or ".mp4"
                file_path = self._download_url_to_temp(detection["url"], suffix, output_path)
                return {"ok": True, "kind": "video", "file_path": file_path, "metadata": metadata, "detection": detection}
            try:
                import yt_dlp
            except Exception:
                return {"ok": False, "reason": "adapter_missing", "metadata": metadata, "detection": detection}
            outtmpl = str(output_path / "toan_aas_%(id)s.%(ext)s")
            ydl_opts = {
                "outtmpl": outtmpl,
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "max_filesize": self.max_bytes,
            }
            if kind == "audio":
                ydl_opts.update({
                    "format": "bestaudio/best",
                    "postprocessors": [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }],
                })
            else:
                ydl_opts["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(detection["url"], download=True)
            file_path = self._latest_downloaded_file(output_path)
            if not file_path or not os.path.exists(file_path) or os.path.getsize(file_path) <= 0:
                return {"ok": False, "reason": "empty_download", "metadata": metadata, "detection": detection}
            if os.path.getsize(file_path) > self.max_bytes:
                return {"ok": False, "reason": "too_large", "metadata": metadata, "detection": detection, "file_path": file_path}
            return {"ok": True, "kind": kind, "file_path": file_path, "metadata": metadata, "detection": detection}
        except Exception as exc:
            return {"ok": False, "reason": f"download_failed:{type(exc).__name__}", "metadata": metadata, "detection": detection}

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
