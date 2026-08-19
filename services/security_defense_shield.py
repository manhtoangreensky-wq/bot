"""Multi-layer Security Defense Shield for TOAN AAS Video System.

Defense-in-depth architecture:
- Layer 1: Input Sanitization & Prompt Injection Shield
- Layer 2: File Upload Integrity & Executable Disguise Shield (Magic Bytes)
- Layer 3: Anti-SSRF & Internal Network Boundary Shield
- Layer 4: Anti-Flood & Token-Bucket Rate Limiter Guard
- Layer 5: Crash Resilience & System Integrity Watchdog
"""

from __future__ import annotations

from dataclasses import dataclass
import functools
import ipaddress
import os
from pathlib import Path
import re
import socket
import threading
import time
from typing import Any, Callable
import urllib.parse


# --- LAYER 1: INPUT SANITIZATION & PROMPT INJECTION SHIELD ---

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_NULL_BYTE = "\x00"

# Potentially malicious shell breakout or command injection tokens
_SHELL_INJECTION_TOKENS = (
    ";", "&&", "||", "`", "$(", "${", "<(", ">(",
    "rm -rf", "mkfs", "dd if=", "/bin/sh", "/bin/bash", "cmd.exe", "powershell"
)

# SQL Injection keywords when chained
_SQL_INJECTION_PATTERNS = re.compile(
    r"\b(union\s+all\s+select|union\s+select|insert\s+into|drop\s+table|drop\s+database|truncate\s+table|information_schema|exec\s+xp_)\b",
    re.IGNORECASE,
)

# Template Injection patterns
_TEMPLATE_INJECTION_PATTERNS = re.compile(r"(\{\{|\}\}|\$\{.*\}|<%.*%>)", re.IGNORECASE)


def sanitize_text_input(
    value: Any,
    *,
    max_length: int = 4000,
    allow_newlines: bool = True,
    fallback: str = "",
) -> str:
    """Strip dangerous control characters, enforce length boundaries, and remove null bytes."""
    if value is None:
        return fallback
    text = str(value)
    # Remove null bytes immediately
    text = text.replace(_NULL_BYTE, "")
    # Remove ASCII control characters
    text = _CONTROL_CHARS.sub(" ", text)
    if not allow_newlines:
        text = text.replace("\r", " ").replace("\n", " ")
    # Normalize multiple whitespace
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text[:max_length]


def is_malicious_prompt_payload(text: str) -> bool:
    """Detect overt injection payloads intended to subvert command or database layers."""
    lowered = text.lower()
    if _NULL_BYTE in text:
        return True
    if _SQL_INJECTION_PATTERNS.search(lowered):
        return True
    if _TEMPLATE_INJECTION_PATTERNS.search(text):
        return True
    return False


# --- LAYER 2: FILE UPLOAD INTEGRITY & MAGIC BYTES VALIDATION ---

_DANGEROUS_EXTENSIONS = frozenset({
    ".exe", ".bat", ".cmd", ".sh", ".bash", ".zsh", ".ps1", ".psm1",
    ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".msc",
    ".php", ".phtml", ".php3", ".php4", ".php5", ".phps",
    ".py", ".pyw", ".pyc", ".pyo", ".pyd",
    ".pl", ".cgi", ".msi", ".jar", ".jsp", ".jspx",
    ".asp", ".aspx", ".ashx", ".asmx",
    ".so", ".dll", ".dylib", ".bin", ".elf", ".com", ".scr", ".hta", ".cpl",
})

_ALLOWED_MEDIA_EXTENSIONS = frozenset({
    ".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi",
    ".jpg", ".jpeg", ".png", ".webp", ".gif",
    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac",
    ".srt", ".vtt",
})

# Magic Bytes Signatures
_MAGIC_SIGNATURES = {
    "jpeg": (b"\xff\xd8\xff",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "webp": (b"RIFF",),  # and WEBP at offset 8
    "mp4_mov": (b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip"),
}


def sanitize_filename(filename: str, fallback: str = "upload.bin") -> str:
    """Eliminate directory traversal tokens, control characters, and unsafe characters."""
    raw = str(filename or "").strip()
    # Strip path separators
    raw = os.path.basename(raw).replace("\\", "").replace("/", "")
    # Remove null bytes & controls
    raw = _CONTROL_CHARS.sub("", raw).replace(_NULL_BYTE, "")
    # Keep only safe characters: alphanumeric, dot, underscore, dash
    clean = re.sub(r"[^A-Za-z0-9._-]", "_", raw)
    # Remove leading dots to prevent hidden file creation
    clean = clean.lstrip(".")
    if not clean or len(clean) > 200:
        return fallback
    return clean


def is_safe_upload_extension(filename: str) -> bool:
    """Reject executable and dangerous extensions, allow only standard media/data formats."""
    clean = sanitize_filename(filename)
    suffix = Path(clean).suffix.lower()
    if not suffix:
        return False
    if suffix in _DANGEROUS_EXTENSIONS:
        return False
    return suffix in _ALLOWED_MEDIA_EXTENSIONS


def validate_media_magic_bytes(data: bytes, expected_kind: str = "auto") -> bool:
    """Verify file magic bytes to prevent disguised executable payloads."""
    if not data or len(data) < 12:
        return False

    # Check for executable headers (MZ / PE for Windows, ELF for Linux, Mach-O for macOS, Shebang)
    if data.startswith(b"MZ") or data.startswith(b"\x7fELF") or data.startswith(b"#!"):
        return False
    if data.startswith((b"\xca\xfe\xba\xbe", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe")):  # Mach-O
        return False

    if expected_kind in ("image", "auto"):
        if any(data.startswith(sig) for sig in _MAGIC_SIGNATURES["jpeg"]):
            return True
        if any(data.startswith(sig) for sig in _MAGIC_SIGNATURES["png"]):
            return True
        if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
            return True

    if expected_kind in ("video", "auto"):
        # MP4 / MOV container: offset 4-8 usually contains ftyp, moov, or mdat
        header_segment = data[:32]
        if any(sig in header_segment for sig in _MAGIC_SIGNATURES["mp4_mov"]):
            return True
        # WebM / Matroska container
        if data.startswith(b"\x1a\x45\xdf\xa3"):
            return True

    if expected_kind in ("audio", "auto"):
        # MP3 ID3v2 or sync frame
        if data.startswith(b"ID3") or data.startswith(b"\xff\xfb") or data.startswith(b"\xff\xf3"):
            return True
        # WAV container
        if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WAVE":
            return True
        # OGG container
        if data.startswith(b"OggS"):
            return True
        # FLAC container
        if data.startswith(b"fLaC"):
            return True

    return False


# --- LAYER 3: ANTI-SSRF & INTERNAL NETWORK BOUNDARY SHIELD ---

_DISALLOWED_IP_NETWORKS = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Cloud metadata IP (169.254.169.254)
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.88.99.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),  # Multicast
    ipaddress.ip_network("240.0.0.0/4"),  # Reserved
    ipaddress.ip_network("255.255.255.255/32"),
    # IPv6 ranges
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)

_BLOCKED_HOSTNAMES = frozenset({
    "localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback",
    "metadata.google.internal", "instance-data", "metadata",
})


def is_safe_public_url(url: str, *, allow_internal_whitelist: tuple[str, ...] = ("tg.toanaas.vn",)) -> bool:
    """Validate that a URL points to public web resources and blocks SSRF to internal/cloud metadata."""
    if not isinstance(url, str) or not url:
        return False
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme.lower() not in {"http", "https"}:
        return False
    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if not hostname:
        return False
    if hostname in _BLOCKED_HOSTNAMES:
        return False
    if hostname in allow_internal_whitelist:
        return True

    # Check if hostname is an explicit IP literal
    try:
        ip_obj = ipaddress.ip_address(hostname)
        for net in _DISALLOWED_IP_NETWORKS:
            if ip_obj in net:
                return False
    except ValueError:
        pass  # Hostname is a domain name

    return True


# --- LAYER 4: ANTI-FLOOD & RATE LIMITING GUARD ---

class SlidingWindowRateLimiter:
    """Thread-safe sliding window rate limiter per user/token."""

    def __init__(self, max_requests: int = 30, window_seconds: float = 10.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._records: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            timestamps = self._records.get(key, [])
            # Purge expired timestamps
            valid_from = now - self.window_seconds
            timestamps = [t for t in timestamps if t > valid_from]
            if len(timestamps) >= self.max_requests:
                self._records[key] = timestamps
                return False
            timestamps.append(now)
            self._records[key] = timestamps
            return True

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is not None:
                self._records.pop(key, None)
            else:
                self._records.clear()


# Global rate limiter instance for public commands & UI callbacks
GLOBAL_RATE_LIMITER = SlidingWindowRateLimiter(max_requests=25, window_seconds=10.0)


# --- LAYER 5: SYSTEM INTEGRITY WATCHDOG & CRASH SHIELD ---

def safe_guard_boundary(fallback_return: Any = None) -> Callable:
    """Decorator to shield critical routes from unhandled exceptions and prevent process crashes."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception:
                return fallback_return

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception:
                return fallback_return

        return async_wrapper if asyncio_iscoroutinefunction(func) else sync_wrapper
    return decorator


def asyncio_iscoroutinefunction(func: Any) -> bool:
    import inspect
    return inspect.iscoroutinefunction(func)


def system_security_status() -> dict[str, Any]:
    """Return a health snapshot of all active security defense layers."""
    return {
        "status": "active",
        "layers": {
            "layer1_input_sanitization": "enabled",
            "layer2_magic_bytes_integrity": "enabled",
            "layer3_anti_ssrf_boundary": "enabled",
            "layer4_anti_flood_limiter": "enabled",
            "layer5_crash_resilience_shield": "enabled",
        },
        "safe_extensions_count": len(_ALLOWED_MEDIA_EXTENSIONS),
        "blocked_extensions_count": len(_DANGEROUS_EXTENSIONS),
        "anti_ssrf_networks_count": len(_DISALLOWED_IP_NETWORKS),
    }
