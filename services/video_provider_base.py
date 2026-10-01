"""Provider-neutral video generation contracts.

This module is UI-free and safe to import at startup. It does not read secrets
except through caller-provided adapter configuration and it never performs
network work unless an adapter method is called explicitly.
"""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import os
import re
import shutil
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from services import video_final_output


VIDEO_PROVIDER_CAPABILITIES = {
    "text_to_video",
    "image_to_video",
    "video_to_video",
    "multi_scene_video",
    "scene_video",
}

BLOCKER_AMBIGUOUS_SUBMIT = "provider_submit_outcome_ambiguous_no_charge"
SUBMIT_OUTCOME_ACCEPTED = "accepted"
SUBMIT_OUTCOME_AMBIGUOUS = "provider_submit_outcome_ambiguous_no_charge"
SUBMIT_OUTCOME_PRE_SEND_FAILURE = "submit_failed_pre_send"


@dataclass(slots=True)
class VideoGenerationRequest:
    job_id: str
    product_type: str
    video_flow_type: str = ""
    prompt: str = ""
    negative_prompt: str = ""
    scenes: list[dict[str, Any]] = field(default_factory=list)
    storyboard: list[dict[str, Any]] = field(default_factory=list)
    image_paths: list[str] = field(default_factory=list)
    source_video_path: str = ""
    ratio: str = "9:16"
    duration_seconds: float = 6.0
    quality: str = ""
    style: str = ""
    seed: int | None = None
    add_ons: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    required_capability: str = "text_to_video"


@dataclass(slots=True)
class VideoSubmitResult:
    ok: bool
    provider_name: str = ""
    provider_task_id: str = ""
    provider_video_id: str = ""
    submitted_at: str = ""
    provider_status: str = ""
    result_url: str = ""
    file_url: str = ""
    error_code: str = ""
    error_message: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VideoPollResult:
    ok: bool
    status: str = "queued"
    provider_name: str = ""
    provider_task_id: str = ""
    provider_video_id: str = ""
    progress_percent: int | None = None
    result_url: str = ""
    file_url: str = ""
    preview_url: str = ""
    error_code: str = ""
    error_message: str = ""
    raw_status: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VideoArtifactResult:
    ok: bool
    local_path: str = ""
    bytes: int = 0
    duration: float = 0.0
    has_video_stream: bool = False
    has_audio_stream: bool = False
    artifact_hash: str = ""
    error_code: str = ""
    error_message: str = ""
    content_type: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CancelResult:
    ok: bool
    provider_name: str = ""
    error_code: str = ""
    error_message: str = ""


class VideoProviderAdapter(Protocol):
    provider_name: str

    def capabilities(self) -> dict[str, Any]:
        ...

    def submit_video_job(self, request: VideoGenerationRequest) -> VideoSubmitResult:
        ...

    def poll_video_job(self, provider_task_id: str) -> VideoPollResult:
        ...

    def materialize_result(self, result: VideoPollResult, job_id: str) -> VideoArtifactResult:
        ...

    def cancel_video_job(self, provider_task_id: str) -> CancelResult:
        ...


def normalize_provider_status(value: Any, *, has_result_url: bool = False) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"success", "succeeded", "completed", "complete", "done", "finished", "media_generation_status_succeeded", "media_generation_status_success"}:
        return "succeeded"
    if raw in {"fail", "failed", "failure", "error"}:
        return "failed"
    if raw in {"cancelled", "canceled"}:
        return "cancelled"
    if raw in {
        "running",
        "processing",
        "in_progress",
        "generating",
        "started",
        "media_generation_status_running",
        "media_generation_status_processing",
        "media_generation_status_in_progress",
    }:
        return "running"
    if raw in {
        "not_start",
        "not_started",
        "notstart",
        "media_generation_status_not_start",
        "media_generation_status_not_started",
    }:
        return "not_start"
    if raw in {"queued", "pending", "submitted", "created", "waiting", "media_generation_status_pending", "media_generation_status_queued"}:
        return "queued"
    if has_result_url and raw not in {"failed", "fail", "error", "cancelled", "canceled"}:
        return "succeeded"
    return raw or "queued"


def mask_provider_task_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= 8:
        return "***" + text[-2:]
    return text[:4] + "***" + text[-4:]


def truthy_env(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def split_provider_chain(value: Any) -> list[str]:
    raw = str(value or "").replace(">", ",").replace("|", ",")
    result: list[str] = []
    aliases = {
        "shopaikey": "shopaikey_video",
        "shopai": "shopaikey_video",
        "key4u": "key4u_video",
        "k4u": "key4u_video",
        "toanaas": "toanaas_video",
        "gommo": "generic_http",
        "79ai": "generic_http",
    }
    for item in raw.split(","):
        token = item.strip().lower()
        if not token:
            continue
        token = aliases.get(token, token)
        if token not in result:
            result.append(token)
    return result


def url_from_poll_result(result: VideoPollResult) -> str:
    return str(result.result_url or result.file_url or "").strip()


def _reject_non_video_payload(path: Path, content_type: str = "") -> str:
    ctype = str(content_type or "").strip().lower()
    if ctype and not any(marker in ctype for marker in ("video/", "application/octet-stream", "binary/octet-stream")):
        return "provider_download_not_video"
    try:
        head = path.read_bytes()[:512].lstrip().lower()
    except Exception:
        return "output_unreadable"
    if not head:
        return "output_zero_bytes"
    if head.startswith(b"<html") or head.startswith(b"<!doctype html"):
        return "provider_download_html_error"
    if head.startswith(b"{") or head.startswith(b"["):
        return "provider_download_json_error"
    return ""


class IncompleteDownloadError(Exception):
    """Raised when downloaded byte count does not match Content-Length header."""
    pass


TRANSIENT_HTTP_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
NON_RETRYABLE_HTTP_STATUS_CODES = {400, 401, 403, 404}


SHOPAIKEY_EXACT_HOST: str = "api.shopaikey.com"
SHOPAIKEY_TASK_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]{1,128}$")
SHOPAIKEY_PATH_PATTERN = re.compile(r"^/v1/videos/([a-zA-Z0-9_\-]+)/content$")
SHOPAIKEY_CONTENT_ENDPOINT_REDIRECT_MAX: int = 1

SAFE_VIDEO_EXTENSIONS: frozenset[str] = frozenset({".mp4", ".webm", ".mov"})
SAFE_HOSTNAME_PATTERN = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
FORBIDDEN_OUTPUT_URL_SCHEMES = frozenset({"javascript:", "vbscript:", "data:", "file:", "blob:", "about:"})


class DisallowedRedirectError(urllib.error.HTTPError):
    """Raised when a redirect target violates safety policy before connection."""

    def __init__(self, url: str, reason: str):
        sanitized = sanitize_output_url_for_logging(url)
        super().__init__(sanitized, 400, f"Disallowed redirect destination ({reason})", hdrs=None, fp=None)
        self.redirect_reason = reason
        self.sanitized_url = sanitized


class UnsafeOutputURLError(ValueError):
    """Raised when candidate video output URL violates SSRF or security whitelist policy."""


def is_safe_shopaikey_content_url(url: Any) -> bool:
    """Validate that candidate URL matches the exact ShopAIKey signed content endpoint policy.

    Required Policy:
    - https scheme only (HTTP_ALLOWED=NO)
    - exact host == "api.shopaikey.com" (HOST_WILDCARD_ALLOWED=NO, SUBDOMAIN_MATCH_ALLOWED=NO, HOST_SUFFIX_MATCH_ALLOWED=NO)
    - port 443 or default None (NON_443_PORT_ALLOWED=NO)
    - no userinfo / no '@' in netloc (USERINFO_ALLOWED=NO)
    - no fragment (FRAGMENT_ALLOWED=NO)
    - exact path shape: /v1/videos/<safe-task-id>/content
    - signed query: both 'exp' and 'sig' parameters must be present and non-empty
    - no directory traversal (.. or %2e) or backslashes
    """
    if not isinstance(url, str):
        return False
    trimmed = url.strip()
    if not trimmed or len(trimmed) > 2048 or trimmed != url:
        return False
    if any(ord(c) < 32 or ord(c) == 127 for c in trimmed):
        return False
    if "\\" in trimmed:
        return False
    lowered = trimmed.lower()
    if ".." in lowered or "%2e" in lowered:
        return False
    if any(lowered.startswith(s) or s in lowered for s in FORBIDDEN_OUTPUT_URL_SCHEMES):
        return False

    try:
        parsed = urllib.parse.urlsplit(trimmed)
    except Exception:
        return False

    if parsed.scheme.lower() != "https":
        return False
    if not parsed.netloc:
        return False
    if parsed.username or parsed.password or "@" in parsed.netloc:
        return False
    if parsed.fragment:
        return False

    hostname = (parsed.hostname or "").lower()
    if hostname != SHOPAIKEY_EXACT_HOST:
        return False

    try:
        port = parsed.port
    except ValueError:
        return False
    if port not in (None, 443):
        return False

    match = SHOPAIKEY_PATH_PATTERN.match(parsed.path)
    if not match:
        return False
    task_id = match.group(1)
    if not SHOPAIKEY_TASK_ID_PATTERN.match(task_id):
        return False

    query_params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    exp_vals = query_params.get("exp")
    sig_vals = query_params.get("sig")
    if not exp_vals or not exp_vals[0].strip():
        return False
    if not sig_vals or not sig_vals[0].strip():
        return False

    return True


def is_safe_video_output_url(url: Any) -> bool:
    """Validate that candidate Product Video output URL is safe to deliver.

    Accepts:
    1. Exact ShopAIKey signed content endpoint
    2. Legacy safe HTTPS video URL (.mp4, .webm, .mov)
    """
    if not isinstance(url, str):
        return False

    if is_safe_shopaikey_content_url(url):
        return True

    trimmed = url.strip()
    if not trimmed or len(trimmed) > 2048 or trimmed != url:
        return False
    if any(ord(c) < 32 or ord(c) == 127 for c in trimmed):
        return False
    if "\\" in trimmed:
        return False
    lowered = trimmed.lower()
    if ".." in lowered or "%2e" in lowered:
        return False
    if any(lowered.startswith(s) or s in lowered for s in FORBIDDEN_OUTPUT_URL_SCHEMES):
        return False

    try:
        parsed = urllib.parse.urlsplit(trimmed)
    except Exception:
        return False

    if parsed.scheme.lower() != "https":
        return False
    if not parsed.netloc:
        return False
    if parsed.username or parsed.password or "@" in parsed.netloc:
        return False
    if parsed.fragment:
        return False

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False

    if hostname == "localhost" or hostname.endswith(".localhost"):
        return False

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        ip = None

    if ip is not None:
        if not ip.is_global:
            return False
    else:
        if not SAFE_HOSTNAME_PATTERN.fullmatch(hostname):
            return False

    try:
        port = parsed.port
    except ValueError:
        return False
    if port not in (None, 443):
        return False

    path = parsed.path.lower()
    if not any(path.endswith(ext) for ext in SAFE_VIDEO_EXTENSIONS):
        return False

    return True


def sanitize_output_url_for_logging(url: Any) -> str:
    """Format URL for safe logging: scheme/host/path/query_present only.

    Never logs signed query values, tokens, sig, or exp.
    """
    if not isinstance(url, str) or not url.strip():
        return "<empty>"
    try:
        p = urllib.parse.urlsplit(url.strip())
        scheme = p.scheme.lower() if p.scheme else "none"
        host = (p.hostname or "").lower() or "none"
        path = p.path or ""
        q_present = bool(p.query)
        return f"{scheme}://{host}{path}?query_present={q_present}"
    except Exception:
        return "<unparseable>"


class _HardenedVideoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Hardened redirect handler enforcing exact destination safety before connection."""

    def __init__(self, initial_source: str):
        super().__init__()
        self.initial_source = initial_source
        self.is_shopaikey = is_safe_shopaikey_content_url(initial_source)
        self.max_redirects = SHOPAIKEY_CONTENT_ENDPOINT_REDIRECT_MAX if self.is_shopaikey else 2
        self.redirect_count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.redirect_count += 1
        if self.redirect_count > self.max_redirects:
            raise DisallowedRedirectError(newurl, f"redirect_limit_exceeded_max_{self.max_redirects}")

        # Validate destination BEFORE contacting
        if self.is_shopaikey:
            if not is_safe_shopaikey_content_url(newurl):
                raise DisallowedRedirectError(newurl, "shopaikey_redirect_destination_disallowed")
        else:
            if not is_safe_video_output_url(newurl):
                raise DisallowedRedirectError(newurl, "redirect_destination_disallowed")

        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _is_transient_download_error(exc: BaseException) -> bool:
    """Determine if a download failure is transient and eligible for bounded retry."""
    if isinstance(exc, (DisallowedRedirectError, UnsafeOutputURLError)):
        return False
    if isinstance(exc, (TimeoutError, socket.timeout, ConnectionResetError, http.client.RemoteDisconnected, http.client.IncompleteRead, IncompleteDownloadError)):
        return True
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in TRANSIENT_HTTP_STATUS_CODES
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, (TimeoutError, socket.timeout, ConnectionResetError, ConnectionRefusedError, socket.gaierror, http.client.RemoteDisconnected, http.client.IncompleteRead)):
            return True
        reason_str = str(reason or "").lower()
        if any(term in reason_str for term in ("timed out", "timeout", "connection reset", "connection refused", "temporary", "nameresolution", "getaddrinfo failed")):
            return True
    return False


def materialize_video_url(
    url: str,
    *,
    job_id: str,
    output_dir: str = "",
    timeout_seconds: int = 180,
    filename_prefix: str = "provider_video",
    sleep_func: Any = None,
) -> VideoArtifactResult:
    source = str(url or "").strip()
    if not source:
        return VideoArtifactResult(
            ok=False,
            error_code="provider_result_url_missing",
            diagnostics={"result_url_present": False, "mp4_validator_result": "not_run_missing_url"},
        )
    parsed_source = urllib.parse.urlsplit(source)
    source_path = str(parsed_source.path or "")
    source_ext = Path(source_path).suffix.lower()
    diagnostics: dict[str, Any] = {
        "result_url_present": True,
        "result_url_host": str(parsed_source.hostname or "")[:160],
        "result_url_scheme": str(parsed_source.scheme or "")[:20],
        "result_url_ext": source_ext[:20],
        "result_url_query_present": bool(parsed_source.query),
        "trusted_video_url": bool(
            is_safe_video_output_url(source) or os.path.isfile(source)
        ),
        "download_http_status": 0,
        "download_final_url_host": "",
        "download_redirect_count": 0,
        "download_content_type": "",
        "download_content_length": 0,
        "download_bytes": 0,
        "download_error_class": "",
        "download_error_message_masked": "",
        "mp4_validator_result": "not_run",
        "first_bytes_hex_safe": "",
        "download_attempts": 0,
        "download_retries": 0,
        "part_file_used": True,
        "content_length_verified": False,
        "transient_retry_attempted": False,
    }
    out_dir = Path(output_dir or os.environ.get("VIDEO_PROVIDER_OUTPUT_DIR") or os.environ.get("VIDEO_PROVIDER_WORK_DIR") or "video_outputs")
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_job = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(job_id or "job"))[:80]
    target = out_dir / f"{filename_prefix}_{safe_job}.mp4"
    content_type = ""

    if os.path.isfile(source):
        part_file = out_dir / f"{filename_prefix}_{safe_job}.attempt_1.part"
        diagnostics["download_attempts"] = 1
        diagnostics["download_retries"] = 0
        diagnostics["download_http_status"] = 200
        diagnostics["download_final_url_host"] = "local_file"
        content_type = "video/mp4"
        try:
            if Path(source).resolve() != target.resolve():
                shutil.copyfile(source, part_file)
                candidate_file = part_file
                cleanup_on_fail = True
            else:
                candidate_file = target
                cleanup_on_fail = False
        except Exception as exc:
            diagnostics.update({
                "download_error_class": type(exc).__name__,
                "download_error_message_masked": type(exc).__name__,
                "mp4_validator_result": "not_run_download_failed",
            })
            if part_file.exists():
                try:
                    part_file.unlink()
                except OSError:
                    pass
            return VideoArtifactResult(
                ok=False,
                local_path=str(target),
                error_code="provider_download_failed",
                error_message=type(exc).__name__,
                diagnostics=diagnostics,
            )
    else:
        if not is_safe_video_output_url(source):
            diagnostics.update({
                "trusted_video_url": False,
                "download_error_class": "UnsafeOutputURLError",
                "download_error_message_masked": "provider_result_url_unsafe",
                "mp4_validator_result": "not_run_unsafe_url",
            })
            return VideoArtifactResult(
                ok=False,
                local_path=str(target),
                error_code="provider_result_url_unsafe",
                error_message="provider_result_url_unsafe",
                diagnostics=diagnostics,
            )

        max_attempts = 2
        last_exc: BaseException | None = None
        transfer_success = False
        candidate_file: Path | None = None
        cleanup_on_fail = True

        for attempt in range(1, max_attempts + 1):
            diagnostics["download_attempts"] = attempt
            part_file = out_dir / f"{filename_prefix}_{safe_job}.attempt_{attempt}.part"
            candidate_file = part_file
            if part_file.exists():
                try:
                    part_file.unlink()
                except OSError:
                    pass

            redirect_handler: _HardenedVideoRedirectHandler | None = None
            try:
                request = urllib.request.Request(source, headers={"User-Agent": "TOAN-AAS-video-provider/1.0"})
                redirect_handler = _HardenedVideoRedirectHandler(source)
                opener = urllib.request.build_opener(redirect_handler)
                with opener.open(request, timeout=max(1, int(timeout_seconds or 180))) as response:
                    content_type = str(response.headers.get("Content-Type") or "")
                    final_url = str(response.geturl() or "")
                    final_parts = urllib.parse.urlsplit(final_url)
                    try:
                        content_length = int(response.headers.get("Content-Length") or 0)
                    except Exception:
                        content_length = 0
                    status_code = int(getattr(response, "status", 0) or response.getcode() or 0)
                    diagnostics.update({
                        "download_http_status": status_code,
                        "download_final_url_host": str(final_parts.hostname or "")[:160],
                        "download_redirect_count": int(redirect_handler.redirect_count),
                        "download_content_length": content_length,
                    })
                    with part_file.open("wb") as handle:
                        shutil.copyfileobj(response, handle)

                transferred = int(part_file.stat().st_size) if part_file.exists() else 0
                diagnostics["download_bytes"] = transferred

                if content_length > 0 and transferred != content_length:
                    raise IncompleteDownloadError(
                        f"Content-Length mismatch: transferred {transferred} != {content_length} Content-Length"
                    )
                if content_length > 0:
                    diagnostics["content_length_verified"] = True

                transfer_success = True
                break

            except Exception as exc:
                last_exc = exc
                diagnostics.update({
                    "download_error_class": type(exc).__name__,
                    "download_error_message_masked": type(exc).__name__,
                    "mp4_validator_result": "not_run_download_failed",
                    "download_redirect_count": int(getattr(redirect_handler, "redirect_count", 0)),
                })
                if isinstance(exc, urllib.error.HTTPError):
                    diagnostics["download_http_status"] = exc.code

                if part_file.exists():
                    try:
                        part_file.unlink()
                    except OSError:
                        pass

                if attempt < max_attempts and _is_transient_download_error(exc):
                    diagnostics["transient_retry_attempted"] = True
                    diagnostics["download_retries"] = diagnostics.get("download_retries", 0) + 1
                    backoff = float(os.environ.get("VIDEO_PROVIDER_DOWNLOAD_RETRY_BACKOFF_SECONDS") or 1.0)
                    sleeper = sleep_func or time.sleep
                    sleeper(backoff)
                    continue
                else:
                    break

        if not transfer_success:
            if candidate_file and candidate_file.exists():
                try:
                    candidate_file.unlink()
                except OSError:
                    pass
            return VideoArtifactResult(
                ok=False,
                local_path=str(target),
                error_code="provider_download_failed",
                error_message=type(last_exc).__name__ if last_exc else "download_failed",
                diagnostics=diagnostics,
            )

    diagnostics["download_content_type"] = content_type[:160]
    size = int(candidate_file.stat().st_size) if candidate_file and candidate_file.exists() else 0
    diagnostics["download_bytes"] = size
    try:
        diagnostics["first_bytes_hex_safe"] = candidate_file.read_bytes()[:16].hex() if candidate_file else ""
    except Exception:
        diagnostics["first_bytes_hex_safe"] = ""

    minimum_bytes = max(1, int(os.environ.get("VIDEO_PROVIDER_MIN_VIDEO_BYTES") or 1024))
    rejected = _reject_non_video_payload(candidate_file, content_type)
    if rejected:
        diagnostics["mp4_validator_result"] = rejected
        if cleanup_on_fail and candidate_file and candidate_file.exists():
            try:
                candidate_file.unlink()
            except OSError:
                pass
        return VideoArtifactResult(
            ok=False,
            local_path=str(target),
            bytes=size,
            error_code=rejected,
            content_type=content_type,
            diagnostics=diagnostics,
        )

    if size < minimum_bytes:
        diagnostics["mp4_validator_result"] = "output_below_minimum_bytes"
        if cleanup_on_fail and candidate_file and candidate_file.exists():
            try:
                candidate_file.unlink()
            except OSError:
                pass
        return VideoArtifactResult(
            ok=False,
            local_path=str(target),
            bytes=size,
            error_code="output_zero_bytes" if size <= 0 else "output_below_minimum_bytes",
            content_type=content_type,
            diagnostics=diagnostics,
        )

    probe = video_final_output.probe_video(str(candidate_file))
    if not probe.get("ok"):
        diagnostics["mp4_validator_result"] = str(probe.get("reason") or "output_unreadable")
        if cleanup_on_fail and candidate_file and candidate_file.exists():
            try:
                candidate_file.unlink()
            except OSError:
                pass
        return VideoArtifactResult(
            ok=False,
            local_path=str(target),
            bytes=size,
            error_code=str(probe.get("reason") or "output_unreadable"),
            content_type=content_type,
            diagnostics=diagnostics,
        )

    diagnostics["mp4_validator_result"] = "valid_mp4"

    if candidate_file != target:
        try:
            os.replace(candidate_file, target)
        except Exception as exc:
            diagnostics.update({
                "download_error_class": type(exc).__name__,
                "download_error_message_masked": type(exc).__name__,
                "mp4_validator_result": "artifact_finalize_failed",
            })
            if candidate_file.exists():
                try:
                    candidate_file.unlink()
                except OSError:
                    pass
            return VideoArtifactResult(
                ok=False,
                local_path=str(target),
                bytes=0,
                error_code="artifact_finalize_failed",
                error_message=type(exc).__name__,
                content_type=content_type,
                diagnostics=diagnostics,
            )

    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return VideoArtifactResult(
        ok=True,
        local_path=str(target),
        bytes=int(target.stat().st_size),
        duration=float(probe.get("duration") or 0.0),
        has_video_stream=bool(probe.get("has_video")),
        has_audio_stream=bool(probe.get("has_audio")),
        artifact_hash=digest.hexdigest(),
        content_type=content_type,
        diagnostics=diagnostics,
    )


class DisabledVideoProvider:
    provider_name = "disabled"

    def __init__(self, provider_name: str, *, missing: list[str] | None = None, capabilities: list[str] | None = None):
        self.provider_name = provider_name
        self._missing = list(missing or ["config"])
        self._capabilities = list(capabilities or [])

    def capabilities(self) -> dict[str, Any]:
        return {"provider": self.provider_name, "enabled": False, "configured": False, "missing": self._missing, "capabilities": self._capabilities}

    def submit_video_job(self, request: VideoGenerationRequest) -> VideoSubmitResult:
        del request
        return VideoSubmitResult(ok=False, provider_name=self.provider_name, error_code="provider_not_configured")

    def poll_video_job(self, provider_task_id: str) -> VideoPollResult:
        return VideoPollResult(ok=False, provider_name=self.provider_name, provider_task_id=provider_task_id, status="failed", error_code="provider_not_configured")

    def materialize_result(self, result: VideoPollResult, job_id: str) -> VideoArtifactResult:
        del result, job_id
        return VideoArtifactResult(ok=False, error_code="provider_not_configured")

    def cancel_video_job(self, provider_task_id: str) -> CancelResult:
        del provider_task_id
        return CancelResult(ok=False, provider_name=self.provider_name, error_code="provider_not_configured")
