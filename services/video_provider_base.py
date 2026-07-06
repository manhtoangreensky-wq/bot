"""Provider-neutral video generation contracts.

This module is UI-free and safe to import at startup. It does not read secrets
except through caller-provided adapter configuration and it never performs
network work unless an adapter method is called explicitly.
"""

from __future__ import annotations

import hashlib
import os
import shutil
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


def materialize_video_url(
    url: str,
    *,
    job_id: str,
    output_dir: str = "",
    timeout_seconds: int = 180,
    filename_prefix: str = "provider_video",
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
            parsed_source.scheme in {"http", "https"} and parsed_source.hostname
        ) or os.path.isfile(source),
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
    }
    out_dir = Path(output_dir or os.environ.get("VIDEO_PROVIDER_OUTPUT_DIR") or os.environ.get("VIDEO_PROVIDER_WORK_DIR") or "video_outputs")
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_job = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(job_id or "job"))[:80]
    target = out_dir / f"{filename_prefix}_{safe_job}.mp4"
    content_type = ""

    class _CountingRedirectHandler(urllib.request.HTTPRedirectHandler):
        def __init__(self):
            super().__init__()
            self.redirect_count = 0

        def redirect_request(self, req, fp, code, msg, headers, newurl):
            self.redirect_count += 1
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    try:
        if os.path.isfile(source):
            shutil.copyfile(source, target)
            content_type = "video/mp4"
            diagnostics["download_http_status"] = 200
            diagnostics["download_final_url_host"] = "local_file"
        else:
            request = urllib.request.Request(source, headers={"User-Agent": "TOAN-AAS-video-provider/1.0"})
            redirect_handler = _CountingRedirectHandler()
            opener = urllib.request.build_opener(redirect_handler)
            with opener.open(request, timeout=max(1, int(timeout_seconds or 180))) as response:
                content_type = str(response.headers.get("Content-Type") or "")
                final_url = str(response.geturl() or "")
                final_parts = urllib.parse.urlsplit(final_url)
                try:
                    content_length = int(response.headers.get("Content-Length") or 0)
                except Exception:
                    content_length = 0
                diagnostics.update(
                    {
                        "download_http_status": int(getattr(response, "status", 0) or response.getcode() or 0),
                        "download_final_url_host": str(final_parts.hostname or "")[:160],
                        "download_redirect_count": int(redirect_handler.redirect_count),
                        "download_content_length": content_length,
                    }
                )
                with target.open("wb") as handle:
                    shutil.copyfileobj(response, handle)
    except Exception as exc:
        diagnostics.update(
            {
                "download_error_class": type(exc).__name__,
                "download_error_message_masked": type(exc).__name__,
                "mp4_validator_result": "not_run_download_failed",
            }
        )
        return VideoArtifactResult(
            ok=False,
            local_path=str(target),
            error_code="provider_download_failed",
            error_message=type(exc).__name__,
            diagnostics=diagnostics,
        )
    diagnostics["download_content_type"] = content_type[:160]
    size = int(target.stat().st_size) if target.exists() else 0
    diagnostics["download_bytes"] = size
    try:
        diagnostics["first_bytes_hex_safe"] = target.read_bytes()[:16].hex()
    except Exception:
        diagnostics["first_bytes_hex_safe"] = ""
    minimum_bytes = max(1, int(os.environ.get("VIDEO_PROVIDER_MIN_VIDEO_BYTES") or 1024))
    rejected = _reject_non_video_payload(target, content_type)
    if rejected:
        diagnostics["mp4_validator_result"] = rejected
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
        return VideoArtifactResult(
            ok=False,
            local_path=str(target),
            bytes=size,
            error_code="output_zero_bytes" if size <= 0 else "output_below_minimum_bytes",
            content_type=content_type,
            diagnostics=diagnostics,
        )
    probe = video_final_output.probe_video(str(target))
    if not probe.get("ok"):
        diagnostics["mp4_validator_result"] = str(probe.get("reason") or "output_unreadable")
        return VideoArtifactResult(
            ok=False,
            local_path=str(target),
            bytes=size,
            error_code=str(probe.get("reason") or "output_unreadable"),
            content_type=content_type,
            diagnostics=diagnostics,
        )
    diagnostics["mp4_validator_result"] = "valid_mp4"
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
