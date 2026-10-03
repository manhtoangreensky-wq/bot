"""Web Product Video Worker Consumer Adapter.

P0.WEBAPP.V3.CUSTOMER.PRODUCT_VIDEO.BOT_WORKER.CONSUMER.ADAPTER.R1
Program: P0.WEBAPP.FULL.PRODUCT.TRUTH.REMEDIATION.V1

This bounded module consumes canonical Web Product Video jobs for video_ai_prompt
from the Web dispatcher (/api/v1/worker/product-video/*) and maps them into the Bot
runtime VideoGenerationRequest contract.

Strict Safety Invariants & Execution Truth:
- Production capability exists via execute_claimed_web_product_video_job() and services.web_product_video_worker_daemon.
- Default production activation remains OFF (fail-closed by default).
- Live execution requires explicit WEB_PRODUCT_VIDEO_WORKER_ENABLED=true in environment.
- No live claims occur while the gate is false (WEB_PRODUCT_VIDEO_WORKER_ENABLED=false).
- Zero direct customer wallet mutations (WALLET_MUTATIONS = 0, PAYMENT_MUTATIONS = 0).
- Canonical Web settlement (Classification A): worker enforces admin_no_charge=True and no_wallet_charge=True.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit

from services.video_provider_base import (
    FORBIDDEN_OUTPUT_URL_SCHEMES,
    SAFE_HOSTNAME_PATTERN,
    SAFE_VIDEO_EXTENSIONS,
    SHOPAIKEY_EXACT_HOST,
    SHOPAIKEY_PATH_PATTERN,
    SHOPAIKEY_TASK_ID_PATTERN,
    VideoGenerationRequest,
    is_safe_shopaikey_content_url,
    is_safe_video_output_url,
    sanitize_output_url_for_logging,
)

logger = logging.getLogger("web_product_video_worker_consumer")

# Supported product scope for R1
PRIMARY_PRODUCT_KEY = "video_ai_prompt"
SUPPORTED_PRODUCTS: frozenset[str] = frozenset({PRIMARY_PRODUCT_KEY})
OWNER_ACCEPTANCE_SUPPORTED_PRODUCTS: frozenset[str] = frozenset({"video_ai_video_reference"})

# Canonical execution / capability parameters
BOT_CANONICAL_PRODUCT_KEY = "video_ai_prompt"
BOT_EXECUTOR_PRODUCT_TYPE = "video_ai_prompt"
DEFAULT_REQUIRED_CAPABILITY = "text_to_video"
ALLOWED_ASPECT_RATIOS: frozenset[str] = frozenset({"9:16", "16:9", "1:1"})
MIN_DURATION_SECONDS: float = 1.0
MAX_DURATION_SECONDS: float = 60.0
MIN_PROMPT_LENGTH: int = 3
MAX_PROMPT_LENGTH: int = 2000
ACCEPTED_VIDEO_FORMATS = frozenset({"mp4", "mov", "webm", "mkv"})
ACCEPTED_VIDEO_CODECS = frozenset({"h264", "hevc", "av1", "vp9", "vp8", "prores"})
MIN_ARTIFACT_BYTES = 4096
DEFAULT_HEARTBEAT_INTERVAL = 15.0
DEFAULT_LEASE_SECONDS = 300

# Concurrency / in-memory deduplication
_ACTIVE_JOB_IDS: set[str] = set()


class WorkerConsumerError(Exception):
    """Base error for worker consumer."""


class WorkerAuthError(WorkerConsumerError):
    """Worker authentication missing or rejected (Fail-Closed)."""


class WorkerClientError(WorkerConsumerError):
    """Worker HTTP client failure (network, status 5xx, timeout)."""


class InvalidJobEnvelopeError(WorkerConsumerError):
    """Claimed job failed envelope validation before runtime."""


class UnsupportedProductError(WorkerConsumerError):
    """Claimed job product is outside supported R1 scope."""


def get_worker_secret(environ: Mapping[str, str] | None = None) -> str:
    """Retrieve worker secret from environment or fail closed."""
    source = os.environ if environ is None else environ
    token = (
        source.get("PRODUCT_VIDEO_WORKER_SECRET")
        or source.get("WORKER_AUTH_TOKEN")
        or source.get("TOANAAS_WORKER_SECRET")
        or ""
    ).strip()
    return token


def get_web_base_url(environ: Mapping[str, str] | None = None) -> str:
    """Retrieve Web base URL from environment without hardcoding production host."""
    source = os.environ if environ is None else environ
    url = (
        source.get("WEB_API_URL")
        or source.get("TOANAAS_WEB_URL")
        or source.get("LOCAL_WEB_API_URL")
        or "http://127.0.0.1:8000"
    ).strip().rstrip("/")
    return url


@dataclass(frozen=True)
class WebClaimResponse:
    ok: bool
    idle: bool
    job: dict[str, Any] | None
    message: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PreparedExecutionOutcome:
    ok: bool
    job_id: str
    request_id: str
    product_key: str
    status: str
    generation_request: VideoGenerationRequest | None
    blocker_reason: str = ""
    provider_submit_called: bool = False
    provider_calls: int = 0
    paid_provider_calls: int = 0
    video_renders: int = 0
    wallet_mutations: int = 0


@dataclass(frozen=True)
class ConsumerExecutionOutcome:
    ok: bool
    job_id: str
    request_id: str
    product_key: str
    status: str
    blocker_reason: str = ""
    output_url: str = ""
    output_metadata: dict[str, Any] = field(default_factory=dict)
    provider_task_id: str = ""
    provider_submit_called: bool = False
    provider_calls: int = 0
    paid_provider_calls: int = 0
    video_renders: int = 0
    wallet_mutations: int = 0


def is_web_product_video_worker_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Production gate check. Defaults strictly to False."""
    source = os.environ if environ is None else environ
    return str(source.get("WEB_PRODUCT_VIDEO_WORKER_ENABLED") or "false").strip().lower() in {"1", "true", "yes", "on"}





def validate_video_artifact_metadata(metadata: Any) -> tuple[bool, str, dict[str, Any]]:
    """Validate that completed video output contains genuine, non-empty artifact metadata."""
    if not isinstance(metadata, dict):
        return False, "METADATA_MUST_BE_DICT", {}

    try:
        duration = float(metadata.get("duration_seconds") or metadata.get("duration") or 0)
    except (TypeError, ValueError):
        return False, "INVALID_DURATION", {}
    if duration <= 0:
        return False, "DURATION_MUST_BE_POSITIVE", {}

    try:
        width = int(metadata.get("width") or 0)
        height = int(metadata.get("height") or 0)
    except (TypeError, ValueError):
        return False, "INVALID_DIMENSIONS", {}
    if width < 64 or height < 64:
        return False, "DIMENSIONS_TOO_SMALL", {}

    try:
        file_size = int(metadata.get("file_size_bytes") or metadata.get("file_size") or 0)
    except (TypeError, ValueError):
        return False, "INVALID_FILE_SIZE", {}
    if file_size < MIN_ARTIFACT_BYTES:
        return False, "FILE_SIZE_TOO_SMALL", {}

    fmt = str(metadata.get("format") or "").strip().lower()
    if fmt not in ACCEPTED_VIDEO_FORMATS:
        return False, "INVALID_FORMAT", {}

    codec = str(metadata.get("codec") or "").strip().lower()
    if codec not in ACCEPTED_VIDEO_CODECS:
        return False, "INVALID_CODEC", {}

    sanitized = {
        "duration_seconds": round(duration, 3),
        "width": width,
        "height": height,
        "file_size_bytes": file_size,
        "format": fmt,
        "codec": codec,
        "fps": float(metadata.get("fps") or 30.0),
        "bitrate_kbps": int(metadata.get("bitrate_kbps") or 0),
        "has_audio": bool(metadata.get("has_audio")),
    }
    return True, "", sanitized


def validate_aspect_ratio_match(actual_width: int, actual_height: int, requested_ratio: str) -> tuple[bool, str]:
    """Validate that actual probed dimensions match the requested aspect ratio contract."""
    if actual_width <= 0 or actual_height <= 0:
        return False, "INVALID_DIMENSIONS_ZERO_OR_NEGATIVE"

    ratio_str = str(requested_ratio or "9:16").strip()
    ratio_map = {
        "9:16": (9, 16),
        "9/16": (9, 16),
        "16:9": (16, 9),
        "16/9": (16, 9),
        "1:1": (1, 1),
        "1/1": (1, 1),
        "4:5": (4, 5),
        "4/5": (4, 5),
        "3:4": (3, 4),
        "3/4": (3, 4),
        "4:3": (4, 3),
        "4/3": (4, 3),
    }
    expected_w, expected_h = ratio_map.get(ratio_str, (9, 16))
    expected_ratio = expected_w / expected_h
    actual_ratio = actual_width / actual_height

    # Orientation mismatch check
    if expected_w < expected_h and actual_width >= actual_height:
        return False, f"ACTUAL_ASPECT_RATIO_MISMATCH: requested {ratio_str} (vertical), got {actual_width}x{actual_height} (horizontal/square)"
    if expected_w > expected_h and actual_width <= actual_height:
        return False, f"ACTUAL_ASPECT_RATIO_MISMATCH: requested {ratio_str} (horizontal), got {actual_width}x{actual_height} (vertical/square)"
    if expected_w == expected_h and abs(actual_width - actual_height) / max(actual_width, actual_height) > 0.05:
        return False, f"ACTUAL_ASPECT_RATIO_MISMATCH: requested {ratio_str} (square), got {actual_width}x{actual_height}"

    # Ratio numeric tolerance check (8% tolerance on aspect ratio)
    if abs(actual_ratio - expected_ratio) / expected_ratio > 0.08:
        return False, f"ACTUAL_ASPECT_RATIO_MISMATCH: requested {ratio_str} ({expected_ratio:.3f}), got {actual_width}x{actual_height} ({actual_ratio:.3f})"

    return True, ""


def validate_duration_contract(actual_duration: float, expected_duration: float, *, tolerance_seconds: float | None = None) -> tuple[bool, str]:
    """Validate that actual probed duration matches the canonical Product Video contract."""
    try:
        actual = float(actual_duration or 0.0)
        expected = float(expected_duration or 0.0)
    except (TypeError, ValueError):
        return False, "INVALID_DURATION_VALUE"

    if actual <= 0.0:
        return False, "DURATION_MUST_BE_POSITIVE"
    if expected <= 0.0:
        return False, "EXPECTED_DURATION_MUST_BE_POSITIVE"

    # Canonical Product Video duration tolerance: max(0.75, expected * 0.20)
    tolerance = float(tolerance_seconds) if tolerance_seconds is not None else max(0.75, expected * 0.20)
    # Narrow boundary grace for media container timestamp quantization
    # (e.g. 6.016s actual for 5.0s expected due to audio/video stream boundary)
    MAX_ADDITIONAL_BOUNDARY_GRACE_SECONDS = 0.025
    effective_tolerance = tolerance + MAX_ADDITIONAL_BOUNDARY_GRACE_SECONDS
    if abs(actual - expected) > effective_tolerance:
        return False, f"DURATION_OUT_OF_TOLERANCE: expected {expected:.1f}s +/- {tolerance:.2f}s, got {actual:.2f}s"

    return True, ""


def probe_artifact_file(path: str) -> dict[str, Any]:
    """Probe actual downloaded MP4 artifact using ffprobe truth."""
    clean_path = str(path or "").strip()
    if not clean_path or not os.path.exists(clean_path):
        return {"ok": False, "reason": "OUTPUT_MISSING", "error": "Artifact file missing on disk"}

    size = os.path.getsize(clean_path)
    if size <= 0:
        return {"ok": False, "reason": "ZERO_BYTE_ARTIFACT", "error": "Artifact file is zero bytes"}

    ffprobe = shutil.which("ffprobe") or os.environ.get("FFPROBE_PATH") or ""
    if not ffprobe:
        try:
            from services.video_final_output import ffprobe_path
            ffprobe = ffprobe_path()
        except Exception:
            pass

    if not ffprobe:
        return {"ok": False, "reason": "PROBE_FAILURE", "error": "ffprobe binary not found"}

    command = [
        ffprobe,
        "-v", "error",
        "-show_entries", "format=format_name,duration,size:stream=codec_type,codec_name,width,height",
        "-of", "json",
        clean_path,
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=45)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "reason": "PROBE_FAILURE", "error": f"ffprobe execution failed: {type(exc).__name__}"}

    if completed.returncode != 0:
        return {"ok": False, "reason": "PROBE_FAILURE", "error": f"ffprobe returned non-zero code {completed.returncode}"}

    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "reason": "PROBE_FAILURE", "error": "ffprobe output invalid JSON"}

    streams = [s for s in payload.get("streams") or [] if isinstance(s, dict)]
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video_stream:
        return {"ok": False, "reason": "MISSING_VIDEO_STREAM", "error": "Artifact contains no video stream"}

    try:
        width = int(video_stream.get("width") or 0)
        height = int(video_stream.get("height") or 0)
    except (TypeError, ValueError):
        width, height = 0, 0

    if width <= 0 or height <= 0:
        return {"ok": False, "reason": "MISSING_VIDEO_STREAM", "error": "Invalid video stream dimensions"}

    try:
        duration = float((payload.get("format") or {}).get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0

    if duration <= 0.0:
        return {"ok": False, "reason": "INVALID_DURATION", "error": "Artifact duration is zero or negative"}

    codec = str(video_stream.get("codec_name") or "h264").strip().lower()
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    format_name = str((payload.get("format") or {}).get("format_name") or "mp4").strip().lower()

    return {
        "ok": True,
        "duration": duration,
        "duration_seconds": duration,
        "width": width,
        "height": height,
        "codec": codec,
        "has_audio": has_audio,
        "file_size_bytes": size,
        "bytes": size,
        "format": "mp4" if "mp4" in format_name else format_name.split(",")[0],
    }


class WebProductVideoDispatcherClient:
    """Bounded HTTP client for the Web Product Video Worker Dispatcher API."""

    def __init__(
        self,
        base_url: str | None = None,
        worker_id: str | None = None,
        worker_secret: str | None = None,
        timeout: int = 30,
        transport: Callable[[urllib.request.Request, int], tuple[int, bytes, dict[str, str]]] | None = None,
    ) -> None:
        self.base_url = (base_url or get_web_base_url()).rstrip("/")
        self.worker_id = str(worker_id or os.environ.get("WORKER_ID") or "vps-toanaas-bot-worker-1").strip()
        self._worker_secret = str(worker_secret if worker_secret is not None else get_worker_secret()).strip()
        self.timeout = max(5, int(timeout))
        self._transport = transport

    def _auth_headers(self) -> dict[str, str]:
        if not self._worker_secret:
            raise WorkerAuthError("MISSING_WORKER_SECRET: Worker secret must be configured; fail closed")
        return {
            "Authorization": f"Bearer {self._worker_secret}",
            "X-Worker-Secret": self._worker_secret,
            "Content-Type": "application/json",
            "User-Agent": f"toanaas-bot-worker/{self.worker_id}",
        }

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = self._auth_headers()
        url = f"{self.base_url}/{path.lstrip('/')}"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None

        if self._transport is not None:
            req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
            status_code, raw_bytes, _ = self._transport(req, self.timeout)
            if status_code in (401, 403):
                raise WorkerAuthError(f"INVALID_WORKER_SECRET: Server returned HTTP {status_code}")
            if status_code >= 400:
                raise WorkerClientError(f"WORKER_CLIENT_FAIL_CLOSED: Server returned HTTP {status_code}")
            try:
                return json.loads(raw_bytes.decode("utf-8", errors="replace") or "{}")
            except Exception as exc:
                raise WorkerClientError("MALFORMED_JSON_RESPONSE") from exc

        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status_code = resp.status
                body = resp.read().decode("utf-8", errors="replace")
                return json.loads(body or "{}")
        except urllib.error.HTTPError as err:
            if err.code in (401, 403):
                raise WorkerAuthError(f"INVALID_WORKER_SECRET: Server returned HTTP {err.code}") from err
            raise WorkerClientError(f"WORKER_CLIENT_FAIL_CLOSED: HTTP {err.code}") from err
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            raise WorkerClientError(f"WORKER_CLIENT_FAIL_CLOSED: Network/transport error {type(exc).__name__}") from exc
        except json.JSONDecodeError as exc:
            raise WorkerClientError("MALFORMED_JSON_RESPONSE") from exc

    def claim(self, lease_seconds: int = 300, target_job_id: str | None = None) -> WebClaimResponse:
        """Claim the oldest queued canonical Product Video job (or specific target job) from the Web dispatcher."""
        payload: dict[str, Any] = {
            "worker_id": self.worker_id,
            "lease_seconds": max(30, int(lease_seconds)),
        }
        if target_job_id:
            payload["target_job_id"] = str(target_job_id).strip()
        res = self._request_json("POST", "/api/v1/worker/product-video/claim", payload)
        if not isinstance(res, dict) or not res.get("ok"):
            error_msg = str(res.get("message") or "Claim failed")
            raise WorkerClientError(f"WORKER_CLAIM_FAILED: {error_msg}")

        data = res.get("data") if isinstance(res.get("data"), dict) else {}
        job = data.get("job") if isinstance(data.get("job"), dict) else None
        idle = bool(data.get("idle") or job is None)

        if job:
            logger.info(
                "claimed_job job_id=%s request_id=%s product=%s worker_id=%s",
                job.get("job_id"),
                job.get("request_id"),
                job.get("product_key"),
                self.worker_id,
            )
        else:
            logger.debug("claim_idle worker_id=%s queue_empty=true", self.worker_id)

        return WebClaimResponse(
            ok=True,
            idle=idle,
            job=job,
            message=str(res.get("message") or ""),
            raw=res,
        )

    def heartbeat(self, job_id: str, lease_seconds: int = 300) -> bool:
        """Send lease heartbeat extension for active job."""
        if not job_id:
            raise ValueError("job_id is required for heartbeat")
        payload = {
            "job_id": str(job_id),
            "worker_id": self.worker_id,
            "lease_seconds": max(30, int(lease_seconds)),
        }
        try:
            res = self._request_json("POST", "/api/v1/worker/product-video/heartbeat", payload)
            return bool(isinstance(res, dict) and res.get("ok"))
        except WorkerClientError as exc:
            if "HTTP 404" in str(exc):
                return False
            raise

    def complete(
        self,
        job_id: str,
        output_url: str,
        output_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Serialize and submit job completion to Web dispatcher.

        INVARIANT: Must never be called with synthetic fake output in production.
        """
        if not job_id or not output_url:
            raise ValueError("job_id and output_url are required to complete job")
        payload = {
            "job_id": str(job_id),
            "worker_id": self.worker_id,
            "output_url": str(output_url),
            "output_metadata": dict(output_metadata or {}),
        }
        return self._request_json("POST", "/api/v1/worker/product-video/complete", payload)

    def fail(
        self,
        job_id: str,
        error_code: str = "WORKER_FAILED",
        error_message: str = "",
        fatal: bool = False,
    ) -> dict[str, Any]:
        """Send factual failure report to Web dispatcher."""
        if not job_id:
            raise ValueError("job_id is required to fail job")
        payload = {
            "job_id": str(job_id),
            "worker_id": self.worker_id,
            "error_code": str(error_code or "WORKER_FAILED")[:64],
            "error_message": str(error_message or "")[:1000],
            "fatal": bool(fatal),
        }
        return self._request_json("POST", "/api/v1/worker/product-video/fail", payload)


def validate_claimed_job(
    job: Mapping[str, Any] | None,
    *,
    owner_acceptance_auth: Mapping[str, Any] | None = None,
) -> tuple[bool, str]:
    """Strictly validate claimed job envelope before runtime mapping."""
    if not isinstance(job, Mapping) or not job:
        return False, "EMPTY_OR_NON_MAPPING_JOB"

    job_id = str(job.get("job_id") or "").strip()
    if len(job_id) < 8:
        return False, "INVALID_OR_MISSING_JOB_ID"

    request_id = str(job.get("request_id") or "").strip()
    if not request_id:
        return False, "MISSING_REQUEST_ID"

    product_key = str(job.get("product_key") or "").strip()
    if not product_key:
        return False, "MISSING_PRODUCT_KEY"

    if product_key not in SUPPORTED_PRODUCTS:
        if product_key in OWNER_ACCEPTANCE_SUPPORTED_PRODUCTS:
            if not owner_acceptance_auth or not isinstance(owner_acceptance_auth, Mapping):
                return False, f"UNSUPPORTED_PRODUCT:{product_key}"
            if not bool(owner_acceptance_auth.get("owner_authorized")):
                return False, "OWNER_ACCEPTANCE_AUTH_UNAUTHORIZED"
            auth_job_id = str(owner_acceptance_auth.get("job_id") or "").strip()
            if not auth_job_id or auth_job_id != job_id:
                return False, f"OWNER_ACCEPTANCE_JOB_ID_MISMATCH:{auth_job_id}!={job_id}"
            auth_product = str(
                owner_acceptance_auth.get("product_type")
                or owner_acceptance_auth.get("product_key")
                or ""
            ).strip()
            if auth_product != product_key:
                return False, f"OWNER_ACCEPTANCE_PRODUCT_MISMATCH:{auth_product}!={product_key}"

            if product_key == "video_ai_video_reference":
                auth_provider = str(owner_acceptance_auth.get("provider") or "").strip().lower()
                if "fal" in auth_provider:
                    return False, "OWNER_ACCEPTANCE_FAL_PROHIBITED_FOR_VIDEO_REFERENCE"
                if auth_provider in ("key4u_video", "key4u"):
                    return False, "KEY4U_SECONDARY_COMMERCIAL_DISABLED"
                if auth_provider not in ("shopaikey_video", "shopaikey"):
                    return False, f"OWNER_ACCEPTANCE_PROVIDER_MISMATCH:{auth_provider}"

                auth_model = str(
                    owner_acceptance_auth.get("model")
                    or owner_acceptance_auth.get("selected_model")
                    or ""
                ).strip()
                if auth_model:
                    if "fal" in auth_model.lower():
                        return False, "OWNER_ACCEPTANCE_FAL_MODEL_PROHIBITED"
                    if auth_model != "veo3.1-fast":
                        return False, f"CROSS_PROVIDER_MODEL_PAIR_REJECTED:{auth_provider}+{auth_model}"

                auth_cap = str(
                    owner_acceptance_auth.get("capability")
                    or owner_acceptance_auth.get("required_capability")
                    or ""
                ).strip()
                if auth_cap:
                    if auth_cap == "video_to_video":
                        return False, "NATIVE_V2V_NOT_PERMITTED:capability_must_be_image_to_video"
                    if auth_cap != "image_to_video":
                        return False, f"OWNER_ACCEPTANCE_CAPABILITY_MISMATCH:{auth_cap}"

                auth_exec_mode = str(owner_acceptance_auth.get("execution_mode") or "").strip()
                if auth_exec_mode and auth_exec_mode != "video_reference_guided_i2v":
                    return False, f"EXECUTION_MODE_MISMATCH:{auth_exec_mode}"

                payload_dict = job.get("payload") if isinstance(job.get("payload"), Mapping) else {}
                job_quality = str(payload_dict.get("quality_tier") or payload_dict.get("tier") or "400").strip().lower()
                auth_tier = str(owner_acceptance_auth.get("tier") or owner_acceptance_auth.get("quality_tier") or "").strip().lower()
                if auth_tier:
                    tier_alias_map = {
                        "400": "400", "veo31_fast_8": "400", "balanced": "400", "veo3.1-fast": "400",
                        "500": "500", "motion_standard_5": "500", "standard": "500",
                        "600": "600", "motion_audio_5": "600",
                    }
                    can_auth = tier_alias_map.get(auth_tier, auth_tier)
                    can_job = tier_alias_map.get(job_quality, job_quality)
                    if can_auth != can_job:
                        return False, f"QUALITY_TIER_MISMATCH:{can_auth}!={can_job}"
            else:
                auth_provider = str(owner_acceptance_auth.get("provider") or "").strip().lower()
                allowed_auth_providers = ("shopaikey_video", "shopaikey", "key4u_video", "fal_video", "fal.ai", "fal-video")
                if auth_provider not in allowed_auth_providers:
                    return False, f"OWNER_ACCEPTANCE_PROVIDER_MISMATCH:{auth_provider}"
                auth_model = str(
                    owner_acceptance_auth.get("model")
                    or owner_acceptance_auth.get("selected_model")
                    or ""
                ).strip()
                allowed_auth_models = ("veo3.1-fast", "fal-ai/wan/v2.2-a14b/video-to-video", "veo3.1-components")
                if auth_model and auth_model not in allowed_auth_models:
                    return False, f"OWNER_ACCEPTANCE_MODEL_MISMATCH:{auth_model}"
                auth_cap = str(
                    owner_acceptance_auth.get("capability")
                    or owner_acceptance_auth.get("required_capability")
                    or ""
                ).strip()
                if auth_cap and auth_cap not in ("image_to_video", "video_to_video"):
                    return False, f"OWNER_ACCEPTANCE_CAPABILITY_MISMATCH:{auth_cap}"
        else:
            return False, f"UNSUPPORTED_PRODUCT:{product_key}"

    account_id = str(job.get("account_id") or "").strip()
    if not account_id:
        return False, "MISSING_ACCOUNT_ID"

    status = str(job.get("status") or "").strip().lower()
    if status != "processing":
        return False, f"INVALID_CLAIMED_STATUS:{status}"

    payload = job.get("payload")
    if not isinstance(payload, Mapping):
        return False, "MALFORMED_PAYLOAD_NOT_OBJECT"

    if product_key == "video_ai_video_reference":
        source_video_path = str(
            payload.get("source_video_path")
            or payload.get("video_path")
            or payload.get("source_video")
            or ""
        ).strip()
        if not source_video_path:
            return False, "MISSING_SOURCE_VIDEO_PATH"

    prompt = str(payload.get("prompt") or "").strip()
    if len(prompt) < MIN_PROMPT_LENGTH:
        return False, "PROMPT_TOO_SHORT"
    if len(prompt) > MAX_PROMPT_LENGTH:
        return False, "PROMPT_TOO_LONG"

    aspect_ratio = str(payload.get("aspect_ratio") or "9:16").strip()
    if aspect_ratio not in ALLOWED_ASPECT_RATIOS:
        return False, f"INVALID_ASPECT_RATIO:{aspect_ratio}"

    try:
        duration = float(payload.get("duration") or 5.0)
    except (ValueError, TypeError):
        return False, "DURATION_NOT_NUMERIC"
    if duration < MIN_DURATION_SECONDS or duration > MAX_DURATION_SECONDS:
        return False, f"DURATION_OUT_OF_BOUNDS:{duration}"

    quality_tier = str(payload.get("quality_tier") or "standard").strip().lower()
    if quality_tier and not re.fullmatch(r"[a-z0-9_\-]+", quality_tier):
        return False, f"INVALID_QUALITY_TIER:{quality_tier}"

    if product_key == "video_ai_video_reference":
        supported_hybrid_tiers = {
            "400", "veo31_fast_8", "balanced",
            "500", "motion_standard_5", "standard",
            "600", "motion_audio_5",
        }
        raw_q = str(payload.get("tier") or payload.get("quality_tier") or "400").strip().lower()
        if raw_q not in supported_hybrid_tiers:
            return False, f"INCOMPATIBLE_HYBRID_QUALITY_TIER:{raw_q}"

    return True, ""


def derive_canonical_tier_route(
    tier: int | str = 200,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Derive canonical Tier runtime identity, provider, model, capability, and cost bounds."""
    try:
        tier_int = int(tier)
    except (ValueError, TypeError):
        tier_int = 200

    from services import video_ai_real_pricing as real_pricing
    from services import video_provider_catalog as catalog

    tier_info = real_pricing.public_quality_by_tier(tier_int)
    route_info = real_pricing.product_video_route_by_tier(tier_int)
    resolved_model = catalog.resolve_product_video_model(tier=tier_int)

    candidates = route_info.get("candidates") or []
    primary = candidates[0] if candidates else {}
    primary_prov = str(primary.get("provider") or "shopaikey").strip()
    if not primary_prov.endswith("_video"):
        primary_prov = f"{primary_prov}_video"

    usd_cost = float(primary.get("usd_per_scene") or 0.400)
    audio_vnd = float(primary.get("audio_addon_cost_vnd") or 0.0)
    audio_usd = audio_vnd / 25000.0 if audio_vnd else 0.00014
    total_cost_usd = round(usd_cost + audio_usd, 5)

    return {
        "tier_id": tier_int,
        "quality_key": str(tier_info.get("quality_key") or "social_fast_5"),
        "seconds": int(tier_info.get("seconds") or 5),
        "unit_xu": int(tier_info.get("unit_xu") or 259),
        "provider": primary_prov,
        "model": str(primary.get("model") or resolved_model.get("model") or "grok-video-3"),
        "required_capability": DEFAULT_REQUIRED_CAPABILITY,
        "estimated_provider_cost": total_cost_usd,
        "estimated_provider_cost_unit": "USD",
        "fallback_allowed": False,
    }


def map_web_job_to_bot_runtime(
    job: Mapping[str, Any],
    *,
    owner_acceptance_auth: Mapping[str, Any] | None = None,
    acceptance_context: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
) -> VideoGenerationRequest:
    """Map canonical Web Product Video job into Bot runtime VideoGenerationRequest."""
    is_valid, reason = validate_claimed_job(job, owner_acceptance_auth=owner_acceptance_auth)
    if not is_valid:
        raise InvalidJobEnvelopeError(f"Job validation failed before runtime mapping: {reason}")

    payload = dict(job.get("payload") or {})
    job_id = str(job["job_id"]).strip()
    request_id = str(job["request_id"]).strip()
    account_id = str(job["account_id"]).strip()

    prompt = str(payload["prompt"]).strip()
    aspect_ratio = str(payload.get("aspect_ratio") or "9:16").strip()
    duration_seconds = float(payload.get("duration") or 5.0)
    quality = str(payload.get("quality_tier") or "standard").strip().lower()

    # Security check: Customer payload must never be allowed to self-authorize
    if "owner_acceptance_auth" in payload or (isinstance(job, Mapping) and "owner_acceptance_auth" in job):
        logger.warning("customer_payload_owner_auth_forgery_ignored job_id=%s", job_id)
    if "public_user_confirmed" in payload or (isinstance(job, Mapping) and "public_user_confirmed" in job):
        logger.warning("customer_payload_public_confirm_forgery_ignored job_id=%s", job_id)

    metadata: dict[str, Any] = {
        "source": "web_dispatcher",
        "web_dispatched": True,
        "web_job_id": job_id,
        "web_request_id": request_id,
        "account_id": account_id,
        "attempts": int(job.get("attempts") or 1),
        "worker_id": str(job.get("worker_id") or ""),
        "quality_tier": quality,
        "admin_no_charge": True,  # Worker consumption must not trigger secondary charging
        "no_wallet_charge": True,
    }

    env = dict(os.environ if environ is None else environ)

    product_key = str(job.get("product_key") or "").strip()
    is_v2v = (product_key == "video_ai_video_reference")

    if is_v2v:
        source_video_path = str(
            payload.get("source_video_path")
            or payload.get("video_path")
            or payload.get("source_video")
            or ""
        ).strip()
        if not source_video_path:
            raise InvalidJobEnvelopeError("SOURCE_VIDEO_PATH_REQUIRED: Missing source_video_path for video_ai_video_reference")

        raw_quality = str(payload.get("tier") or payload.get("quality_tier") or "400").strip().lower()
        from services.video_ai_real_pricing import build_canonical_hybrid_pricing_snapshot
        try:
            pricing_snap = build_canonical_hybrid_pricing_snapshot(tier=raw_quality)
        except ValueError as exc:
            raise InvalidJobEnvelopeError(f"INCOMPATIBLE_HYBRID_QUALITY_TIER: {exc}") from exc

        tier_id = pricing_snap["tier_id"]
        quality_key = pricing_snap["quality_tier"]
        effective_duration = float(pricing_snap["seconds"])
        estimated_cost = float(pricing_snap["usd_cost"])
        pricing_snap_hash = str(pricing_snap["pricing_snapshot_id_or_hash"])

        from services.video_reference_package import (
            create_video_reference_package,
            VideoReferencePackageError,
        )
        try:
            ref_pkg = create_video_reference_package(
                source_video_path=source_video_path,
                user_prompt=prompt,
                duration=effective_duration,
            )
        except VideoReferencePackageError as exc:
            raise InvalidJobEnvelopeError(f"VIDEO_REFERENCE_PACKAGING_FAILED: {exc}") from exc
        except Exception as exc:
            raise InvalidJobEnvelopeError(f"VIDEO_REFERENCE_PACKAGING_ERROR: {exc}") from exc

        image_paths = list(ref_pkg.get("frame_paths") or [])
        if len(image_paths) != 2:
            raise InvalidJobEnvelopeError(f"INVALID_REFERENCE_FRAME_COUNT: expected 2, got {len(image_paths)}")

        metadata["reference_package"] = ref_pkg
        metadata["execution_mode"] = "video_reference_guided_i2v"
        metadata["source_input_kind"] = "video"
        metadata["native_v2v"] = False
        metadata["native_v2v_enabled"] = False
        metadata["source_video_sha256"] = ref_pkg.get("source_video_sha256")
        metadata["frame_1_sha256"] = ref_pkg.get("frame_1_sha256")
        metadata["frame_2_sha256"] = ref_pkg.get("frame_2_sha256")
        metadata["prompt_sha256"] = ref_pkg.get("prompt_sha256")
        metadata["pricing_snapshot"] = pricing_snap
        metadata["pricing_snapshot_id_or_hash"] = pricing_snap_hash
        metadata["duration_seconds"] = effective_duration
        metadata["aspect_ratio"] = aspect_ratio
        metadata["quality_tier"] = quality_key
        metadata["tier"] = str(tier_id)

        req_product_type = "video_ai_video_reference"
        req_video_flow_type = "video_ai_video_reference"
        req_capability = "image_to_video"
        duration_seconds = effective_duration
        derived_route = {
            "tier_id": tier_id,
            "quality_key": quality_key,
            "seconds": int(effective_duration),
            "provider": "shopaikey_video",
            "model": "veo3.1-fast",
            "required_capability": "image_to_video",
            "estimated_provider_cost": estimated_cost,
            "estimated_provider_cost_unit": "USD",
            "pricing_snapshot_id_or_hash": pricing_snap_hash,
            "fallback_allowed": False,
        }
    else:
        source_video_path = ""
        image_paths = []
        req_product_type = BOT_CANONICAL_PRODUCT_KEY
        req_video_flow_type = BOT_EXECUTOR_PRODUCT_TYPE
        req_capability = DEFAULT_REQUIRED_CAPABILITY
        derived_route = derive_canonical_tier_route(quality, environ=env)

    if owner_acceptance_auth is not None:
        from services.video_provider_router import (
            OWNER_AUTHORIZED_LIVE_ACCEPTANCE,
            validate_owner_acceptance_authorization,
        )

        derived_ctx: dict[str, Any] = {
            "user_id": str(account_id or job.get("account_id") or "").strip(),
            "job_id": job_id,
            "project_id": str(job.get("project_id") or "").strip(),
            "product_type": req_product_type,
            "provider": derived_route["provider"],
            "model": derived_route["model"],
            "required_capability": derived_route["required_capability"],
            "tier": str(derived_route["tier_id"]),
            "quality_tier": derived_route["quality_key"],
            "estimated_provider_cost": derived_route["estimated_provider_cost"],
            "estimated_provider_cost_unit": derived_route["estimated_provider_cost_unit"],
            "expected_duration_seconds": derived_route.get("seconds", 5),
            "duration_seconds": derived_route.get("seconds", 5),
            "aspect_ratio": aspect_ratio,
            "execution_mode": "video_reference_guided_i2v" if is_v2v else "",
            "source_video_sha256": metadata.get("source_video_sha256", ""),
            "frame_1_sha256": metadata.get("frame_1_sha256", ""),
            "frame_2_sha256": metadata.get("frame_2_sha256", ""),
            "prompt_sha256": metadata.get("prompt_sha256", ""),
            "pricing_snapshot_id_or_hash": metadata.get("pricing_snapshot_id_or_hash", ""),
            "max_provider_submits": 1,
        }
        if acceptance_context and isinstance(acceptance_context, Mapping):
            derived_ctx.update(dict(acceptance_context))

        # Support user binding against account_id, canonical_user_id, or user_id
        auth_user_id = str(owner_acceptance_auth.get("user_id") or "").strip()
        job_user_ids = {
            str(account_id).strip(),
            str(job.get("account_id") or "").strip(),
            str(job.get("user_id") or "").strip(),
            str(job.get("canonical_user_id") or "").strip(),
        }
        job_user_ids.discard("")
        if auth_user_id and auth_user_id in job_user_ids:
            derived_ctx["user_id"] = auth_user_id

        # Support tier binding against numeric tier or quality key or model
        auth_tier = str(owner_acceptance_auth.get("tier") or "").strip()
        if is_v2v:
            valid_tiers = {
                str(derived_route["tier_id"]).strip().lower(),
                derived_route["quality_key"].strip().lower(),
                derived_route["model"].strip().lower(),
            }
            if derived_route["tier_id"] == 500:
                valid_tiers.add("standard")
            elif derived_route["tier_id"] == 400:
                valid_tiers.add("balanced")
            if auth_tier and auth_tier.lower() in valid_tiers:
                derived_ctx["tier"] = auth_tier
            elif auth_tier:
                derived_ctx["tier"] = auth_tier
        else:
            valid_tiers = {
                str(derived_route["tier_id"]).strip().lower(),
                derived_route["quality_key"].strip().lower(),
                derived_route["model"].strip().lower(),
                quality,
            }
            if auth_tier and auth_tier.lower() in valid_tiers:
                derived_ctx["tier"] = auth_tier

        # Resolve runtime SHA
        try:
            from services.remote_worker_api import resolve_runtime_sha
            current_sha = resolve_runtime_sha(environ=env)
        except Exception:
            current_sha = ""
        if current_sha:
            derived_ctx["runtime_sha"] = current_sha

        auth_valid, auth_blocker, verified_auth = validate_owner_acceptance_authorization(
            dict(owner_acceptance_auth),
            context=derived_ctx,
            environ=env,
        )

        if not auth_valid:
            logger.warning(
                "owner_acceptance_auth_validation_failed job_id=%s reason=%s",
                job_id,
                auth_blocker,
            )
            raise InvalidJobEnvelopeError(f"Owner acceptance authorization invalid: {auth_blocker}")

        # Inject verified authorization into request metadata
        metadata["owner_acceptance_auth"] = dict(owner_acceptance_auth)
        metadata["owner_authorized"] = True
        metadata["acceptance_lane_active"] = True
        metadata["pinned_provider"] = verified_auth.get("pinned_provider") or derived_route["provider"]
        metadata["provider"] = verified_auth.get("pinned_provider") or derived_route["provider"]
        metadata["selected_provider"] = verified_auth.get("pinned_provider") or derived_route["provider"]
        metadata["submit_source"] = OWNER_AUTHORIZED_LIVE_ACCEPTANCE
        metadata["source"] = OWNER_AUTHORIZED_LIVE_ACCEPTANCE
        metadata["tier"] = derived_ctx["tier"]
        metadata["selected_model"] = derived_route["model"]
        metadata["model"] = derived_route["model"]
        metadata["user_id"] = derived_ctx["user_id"]
        metadata["project_id"] = derived_ctx["project_id"]
        metadata["runtime_sha"] = derived_ctx.get("runtime_sha")
        metadata["estimated_provider_cost"] = derived_ctx["estimated_provider_cost"]
        metadata["estimated_provider_cost_unit"] = derived_ctx["estimated_provider_cost_unit"]
        metadata["acceptance_bypass_scope"] = str(
            derived_ctx.get("acceptance_bypass_scope") or "probation_liveness_only"
        )

    return VideoGenerationRequest(
        job_id=job_id,
        product_type=req_product_type,
        video_flow_type=req_video_flow_type,
        prompt=prompt,
        ratio=aspect_ratio,
        duration_seconds=duration_seconds,
        quality=quality,
        metadata=metadata,
        required_capability=req_capability,
        source_video_path=source_video_path,
        image_paths=image_paths,
    )


def prepare_and_gate_execution(
    job: Mapping[str, Any],
    client: WebProductVideoDispatcherClient | None = None,
    *,
    owner_acceptance_auth: Mapping[str, Any] | None = None,
    acceptance_context: Mapping[str, Any] | None = None,
    acceptance_bypass_scope: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> PreparedExecutionOutcome:
    """Execute provider-free preparation boundary and gate before provider submit.

    This function proves the canonical contract without invoking paid external providers.
    """
    raw_job_id = str((job or {}).get("job_id") or "")
    if raw_job_id in _ACTIVE_JOB_IDS:
        logger.warning("duplicate_execution_rejected job_id=%s", raw_job_id)
        return PreparedExecutionOutcome(
            ok=False,
            job_id=raw_job_id,
            request_id=str((job or {}).get("request_id") or ""),
            product_key=str((job or {}).get("product_key") or ""),
            status="DUPLICATE_EXECUTION_BLOCKED",
            generation_request=None,
            blocker_reason="DUPLICATE_ACTIVE_JOB_EXECUTION",
        )

    is_valid, validation_reason = validate_claimed_job(job, owner_acceptance_auth=owner_acceptance_auth)
    if not is_valid:
        if client and raw_job_id:
            try:
                client.fail(
                    job_id=raw_job_id,
                    error_code="VALIDATION_FAILED",
                    error_message=validation_reason,
                    fatal=True,
                )
            except Exception as exc:
                logger.error("pre_provider_fail_reporting_error job_id=%s err=%s", raw_job_id, type(exc).__name__)

        return PreparedExecutionOutcome(
            ok=False,
            job_id=raw_job_id,
            request_id=str((job or {}).get("request_id") or ""),
            product_key=str((job or {}).get("product_key") or ""),
            status="INVALID_JOB_REJECTED",
            generation_request=None,
            blocker_reason=validation_reason,
        )

    _ACTIVE_JOB_IDS.add(raw_job_id)
    try:
        eff_ctx = dict(acceptance_context or {})
        if acceptance_bypass_scope:
            eff_ctx["acceptance_bypass_scope"] = str(acceptance_bypass_scope)
        request = map_web_job_to_bot_runtime(
            job,
            owner_acceptance_auth=owner_acceptance_auth,
            acceptance_context=eff_ctx,
            environ=environ,
        )
        return PreparedExecutionOutcome(
            ok=True,
            job_id=request.job_id,
            request_id=str(request.metadata.get("web_request_id") or ""),
            product_key=request.product_type,
            status="PREPARED_PROVIDER_BLOCKED",
            generation_request=request,
            blocker_reason="",
            provider_submit_called=False,
            provider_calls=0,
            paid_provider_calls=0,
            video_renders=0,
            wallet_mutations=0,
        )
    except InvalidJobEnvelopeError as exc:
        if client and raw_job_id:
            try:
                client.fail(
                    job_id=raw_job_id,
                    error_code="VALIDATION_FAILED",
                    error_message=str(exc),
                    fatal=True,
                )
            except Exception as e:
                logger.error("pre_provider_fail_reporting_error job_id=%s err=%s", raw_job_id, type(e).__name__)
        return PreparedExecutionOutcome(
            ok=False,
            job_id=raw_job_id,
            request_id=str((job or {}).get("request_id") or ""),
            product_key=str((job or {}).get("product_key") or ""),
            status="INVALID_JOB_REJECTED",
            generation_request=None,
            blocker_reason=str(exc),
        )
    finally:
        _ACTIVE_JOB_IDS.discard(raw_job_id)


def execute_claimed_web_product_video_job(
    job: Mapping[str, Any] | None,
    client: WebProductVideoDispatcherClient | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    output_dir: str | Path | None = None,
    heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    executor_fn: Callable[..., dict[str, Any]] | None = None,
    stop_event: threading.Event | None = None,
    owner_acceptance_auth: Mapping[str, Any] | None = None,
    acceptance_context: Mapping[str, Any] | None = None,
    acceptance_bypass_scope: str | None = None,
) -> ConsumerExecutionOutcome:
    """Execute a claimed Web Product Video job through the canonical Bot runtime.

    Invariants:
    1. Validation First: Validates envelope before allocating resources or calling provider.
    2. Fail-Closed Gate: Requires WEB_PRODUCT_VIDEO_WORKER_ENABLED=true in environment.
    3. Fencing & Deduplication: Prevents concurrent execution of the same job_id.
    4. Active Heartbeat: Sends periodic heartbeats during execution; fail-closed on lease loss.
    5. Canonical Runtime: Invokes Bot Product Video runtime (max 1 provider submit).
    6. Safe Output Truth: Validates HTTPS video output URL and non-zero artifact metadata.
    7. No Wallet Mutations: Strictly passes admin_no_charge=True and no_wallet_charge=True.
    8. Factual Reporting: Reports terminal complete or factual failure to Web dispatcher.
    """
    env = os.environ if environ is None else environ
    raw_job_id = str((job or {}).get("job_id") or "").strip()
    request_id = str((job or {}).get("request_id") or "").strip()
    product_key = str((job or {}).get("product_key") or "").strip()

    if not raw_job_id:
        return ConsumerExecutionOutcome(
            ok=False,
            job_id="",
            request_id=request_id,
            product_key=product_key,
            status="INVALID_JOB_REJECTED",
            blocker_reason="MISSING_JOB_ID",
        )

    # In-memory deduplication check
    if raw_job_id in _ACTIVE_JOB_IDS:
        logger.warning("duplicate_execution_rejected job_id=%s", raw_job_id)
        return ConsumerExecutionOutcome(
            ok=False,
            job_id=raw_job_id,
            request_id=request_id,
            product_key=product_key,
            status="DUPLICATE_EXECUTION_BLOCKED",
            blocker_reason="DUPLICATE_ACTIVE_JOB_EXECUTION",
        )

    # Envelope validation
    is_valid, validation_reason = validate_claimed_job(job, owner_acceptance_auth=owner_acceptance_auth)
    if not is_valid:
        if client:
            try:
                client.fail(
                    job_id=raw_job_id,
                    error_code="VALIDATION_FAILED",
                    error_message=validation_reason,
                    fatal=True,
                )
            except Exception as exc:
                logger.error("fail_reporting_error job_id=%s err=%s", raw_job_id, type(exc).__name__)
        return ConsumerExecutionOutcome(
            ok=False,
            job_id=raw_job_id,
            request_id=request_id,
            product_key=product_key,
            status="INVALID_JOB_REJECTED",
            blocker_reason=validation_reason,
        )

    # Fail-closed production activation gate
    if not is_web_product_video_worker_enabled(env):
        logger.warning("worker_execution_disabled_by_config job_id=%s", raw_job_id)
        if client:
            try:
                client.fail(
                    job_id=raw_job_id,
                    error_code="WORKER_DISABLED",
                    error_message="Web Product Video worker execution disabled by configuration",
                    fatal=True,
                )
            except Exception as exc:
                logger.error("fail_reporting_error job_id=%s err=%s", raw_job_id, type(exc).__name__)
        return ConsumerExecutionOutcome(
            ok=False,
            job_id=raw_job_id,
            request_id=request_id,
            product_key=product_key,
            status="WORKER_EXECUTION_DISABLED",
            blocker_reason="WORKER_DISABLED",
        )

    _ACTIVE_JOB_IDS.add(raw_job_id)
    heartbeat_abort = threading.Event()
    lease_lost = False
    hb_thread: threading.Thread | None = None

    try:
        # Map Web job to canonical VideoGenerationRequest
        eff_ctx = dict(acceptance_context or {})
        if acceptance_bypass_scope:
            eff_ctx["acceptance_bypass_scope"] = str(acceptance_bypass_scope)
        try:
            gen_request = map_web_job_to_bot_runtime(
                job,
                owner_acceptance_auth=owner_acceptance_auth,
                acceptance_context=eff_ctx,
                environ=dict(env),
            )
        except InvalidJobEnvelopeError as exc:
            logger.warning("invalid_job_envelope_rejected job_id=%s reason=%s", raw_job_id, exc)
            if client:
                try:
                    client.fail(
                        job_id=raw_job_id,
                        error_code="VALIDATION_FAILED",
                        error_message=str(exc),
                        fatal=True,
                    )
                except Exception as client_exc:
                    logger.error("fail_reporting_error job_id=%s err=%s", raw_job_id, type(client_exc).__name__)
            return ConsumerExecutionOutcome(
                ok=False,
                job_id=raw_job_id,
                request_id=request_id,
                product_key=product_key,
                status="INVALID_JOB_REJECTED",
                blocker_reason=str(exc),
            )

        # Heartbeat loop for lease extension
        if client is not None:
            def _heartbeat_loop():
                nonlocal lease_lost
                interval = max(0.05, float(heartbeat_interval))
                while not heartbeat_abort.wait(timeout=interval):
                    if stop_event and stop_event.is_set():
                        break
                    try:
                        hb_ok = client.heartbeat(raw_job_id, lease_seconds=lease_seconds)
                        if not hb_ok:
                            logger.warning("heartbeat_rejected_lease_lost job_id=%s", raw_job_id)
                            lease_lost = True
                            heartbeat_abort.set()
                            break
                    except Exception as exc:
                        logger.warning("heartbeat_exception job_id=%s err=%s", raw_job_id, type(exc).__name__)

            hb_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
            hb_thread.start()

        # Execute canonical Bot Product Video runtime
        gen_result: dict[str, Any] = {}
        try:
            if executor_fn is not None:
                fn = executor_fn
            else:
                from services.video_provider_router import run_provider_generation
                fn = run_provider_generation

            call_env = dict(env)
            effective_scope = str(
                acceptance_bypass_scope or eff_ctx.get("acceptance_bypass_scope") or ""
            ).strip()
            if (
                owner_acceptance_auth is not None
                and gen_request.metadata.get("owner_authorized")
                and effective_scope in {"probation_liveness_only", "owner_acceptance_liveness"}
            ):
                call_env["PROVIDER_SPEND_FREEZE"] = "0"
                call_env["ACCEPTANCE_BYPASS_SCOPE"] = effective_scope

            _tmp_ctx = tempfile.TemporaryDirectory(prefix="web_pv_worker_")
            tmp_dir = _tmp_ctx.__enter__()
            try:
                active_out_dir = str(output_dir or tmp_dir)
                gen_result = fn(gen_request, output_dir=active_out_dir, environ=call_env)
            except Exception:
                # Cleanup temp dir immediately on provider failure before re-raising
                _tmp_ctx.__exit__(None, None, None)
                raise
        except Exception as exc:
            logger.exception("provider_runtime_exception job_id=%s err=%s", raw_job_id, type(exc).__name__)
            gen_result = {
                "ok": False,
                "blocker": "PROVIDER_EXCEPTION",
                "provider_error": type(exc).__name__,
                "public_message": str(exc)[:200],
                "provider_submit_called": True,
            }
        finally:
            heartbeat_abort.set()
            if hb_thread is not None:
                hb_thread.join(timeout=1.0)

        # Check lease status: if lease lost, fail-closed without completing
        if lease_lost:
            logger.error("lease_lost_fail_closed job_id=%s", raw_job_id)
            return ConsumerExecutionOutcome(
                ok=False,
                job_id=raw_job_id,
                request_id=request_id,
                product_key=product_key,
                status="LEASE_LOST_FAIL_CLOSED",
                blocker_reason="WORKER_LEASE_LOST_DURING_EXECUTION",
                provider_submit_called=bool(gen_result.get("provider_submit_called") if isinstance(gen_result, dict) else False),
                provider_calls=1 if isinstance(gen_result, dict) and gen_result.get("provider_submit_called") else 0,
                paid_provider_calls=1 if isinstance(gen_result, dict) and gen_result.get("provider_submit_called") else 0,
            )

        # Process execution outcome
        if isinstance(gen_result, dict) and gen_result.get("ok"):
            output_url = str(gen_result.get("result_url") or gen_result.get("file_url") or "").strip()
            output_path = str(gen_result.get("output_path") or gen_result.get("local_path") or "").strip()

            if not output_url or not is_safe_video_output_url(output_url):
                sanitized_url = sanitize_output_url_for_logging(output_url)
                logger.error("unsafe_output_url_rejected job_id=%s url=%s", raw_job_id, sanitized_url)
                if client:
                    try:
                        client.fail(
                            job_id=raw_job_id,
                            error_code="UNSAFE_OUTPUT_URL",
                            error_message="Provider produced an unsafe or non-HTTPS output URL",
                            fatal=True,
                        )
                    except Exception as exc:
                        logger.error("fail_reporting_error job_id=%s err=%s", raw_job_id, type(exc).__name__)
                return ConsumerExecutionOutcome(
                    ok=False,
                    job_id=raw_job_id,
                    request_id=request_id,
                    product_key=product_key,
                    status="UNSAFE_OUTPUT_REJECTED",
                    blocker_reason="UNSAFE_OUTPUT_URL",
                    output_url=output_url,
                    provider_submit_called=True,
                    provider_calls=1,
                    paid_provider_calls=1,
                    video_renders=1,
                )

            # Artifact metadata validation using actual ffprobe truth
            requested_ratio = str((job.get("payload") or {}).get("aspect_ratio") or "9:16").strip()
            expected_duration = float((job.get("payload") or {}).get("duration") or 5.0)

            # If local artifact path is present on disk, probe truth directly from the file
            if output_path and os.path.exists(output_path):
                probe = probe_artifact_file(output_path)
                if not probe.get("ok"):
                    err_code = str(probe.get("reason") or "PROBE_FAILURE")
                    err_msg = str(probe.get("error") or err_code)
                    logger.error("artifact_probe_failed job_id=%s reason=%s error=%s", raw_job_id, err_code, err_msg)
                    if client:
                        try:
                            client.fail(
                                job_id=raw_job_id,
                                error_code=err_code,
                                error_message=err_msg,
                                fatal=True,
                            )
                        except Exception as exc:
                            logger.error("fail_reporting_error job_id=%s err=%s", raw_job_id, type(exc).__name__)
                    return ConsumerExecutionOutcome(
                        ok=False,
                        job_id=raw_job_id,
                        request_id=request_id,
                        product_key=product_key,
                        status=err_code,
                        blocker_reason=err_msg,
                        output_url=output_url,
                        provider_submit_called=True,
                        provider_calls=1,
                        paid_provider_calls=1,
                        video_renders=1,
                    )
                duration = float(probe.get("duration") or 0.0)
                width = int(probe.get("width") or 0)
                height = int(probe.get("height") or 0)
                file_size = int(probe.get("file_size_bytes") or os.path.getsize(output_path))
                fmt = str(probe.get("format") or "mp4").strip().lower()
                codec = str(probe.get("codec") or "h264").strip().lower()
                has_audio = bool(probe.get("has_audio"))
            else:
                # No local artifact file on disk (e.g. mock executor in unit tests):
                # Use explicit gen_result attributes if provided, or default dims for ratio
                dims = (720, 1280) if requested_ratio == "9:16" else (1280, 720)
                try:
                    width = int(gen_result.get("width") or dims[0])
                    height = int(gen_result.get("height") or dims[1])
                except (TypeError, ValueError):
                    width, height = dims
                duration = float(gen_result.get("duration") or gen_result.get("duration_seconds") or 0.0)
                file_size = int(gen_result.get("bytes") or gen_result.get("file_size_bytes") or 0)
                fmt = str(gen_result.get("format") or "mp4").strip().lower()
                codec = str(gen_result.get("codec") or "h264").strip().lower()
                has_audio = bool(gen_result.get("has_audio"))

            # Aspect Ratio Contract Validation
            is_ratio_match, ratio_err = validate_aspect_ratio_match(width, height, requested_ratio)
            if not is_ratio_match:
                logger.error("artifact_aspect_ratio_mismatch job_id=%s err=%s", raw_job_id, ratio_err)
                if client:
                    try:
                        client.fail(
                            job_id=raw_job_id,
                            error_code="ARTIFACT_CONTRACT_MISMATCH",
                            error_message=ratio_err,
                            fatal=True,
                        )
                    except Exception as exc:
                        logger.error("fail_reporting_error job_id=%s err=%s", raw_job_id, type(exc).__name__)
                return ConsumerExecutionOutcome(
                    ok=False,
                    job_id=raw_job_id,
                    request_id=request_id,
                    product_key=product_key,
                    status="ARTIFACT_CONTRACT_MISMATCH",
                    blocker_reason=ratio_err,
                    output_url=output_url,
                    provider_submit_called=True,
                    provider_calls=1,
                    paid_provider_calls=1,
                    video_renders=1,
                )

            # Duration Contract Validation
            is_duration_match, duration_err = validate_duration_contract(duration, expected_duration)
            if not is_duration_match:
                logger.error("artifact_duration_mismatch job_id=%s err=%s", raw_job_id, duration_err)
                if client:
                    try:
                        client.fail(
                            job_id=raw_job_id,
                            error_code="ARTIFACT_CONTRACT_MISMATCH",
                            error_message=duration_err,
                            fatal=True,
                        )
                    except Exception as exc:
                        logger.error("fail_reporting_error job_id=%s err=%s", raw_job_id, type(exc).__name__)
                return ConsumerExecutionOutcome(
                    ok=False,
                    job_id=raw_job_id,
                    request_id=request_id,
                    product_key=product_key,
                    status="ARTIFACT_CONTRACT_MISMATCH",
                    blocker_reason=duration_err,
                    output_url=output_url,
                    provider_submit_called=True,
                    provider_calls=1,
                    paid_provider_calls=1,
                    video_renders=1,
                )

            # Basic metadata schema validation
            raw_meta = {
                "duration_seconds": duration,
                "width": width,
                "height": height,
                "file_size_bytes": file_size,
                "format": fmt,
                "codec": codec,
                "has_audio": has_audio,
            }
            is_valid_meta, meta_err, sanitized_meta = validate_video_artifact_metadata(raw_meta)
            if not is_valid_meta:
                logger.error("invalid_artifact_metadata job_id=%s reason=%s", raw_job_id, meta_err)
                if client:
                    try:
                        client.fail(
                            job_id=raw_job_id,
                            error_code="INVALID_ARTIFACT_METADATA",
                            error_message=meta_err,
                            fatal=True,
                        )
                    except Exception as exc:
                        logger.error("fail_reporting_error job_id=%s err=%s", raw_job_id, type(exc).__name__)
                return ConsumerExecutionOutcome(
                    ok=False,
                    job_id=raw_job_id,
                    request_id=request_id,
                    product_key=product_key,
                    status="INVALID_ARTIFACT_METADATA",
                    blocker_reason=meta_err,
                    output_url=output_url,
                    provider_submit_called=True,
                    provider_calls=1,
                    paid_provider_calls=1,
                    video_renders=1,
                )

            # Report completion to Web Dispatcher
            if client:
                try:
                    client.complete(
                        job_id=raw_job_id,
                        output_url=output_url,
                        output_metadata=sanitized_meta,
                    )
                except Exception as exc:
                    logger.error("complete_reporting_error job_id=%s err=%s", raw_job_id, type(exc).__name__)
                    return ConsumerExecutionOutcome(
                        ok=False,
                        job_id=raw_job_id,
                        request_id=request_id,
                        product_key=product_key,
                        status="DISPATCHER_COMPLETE_FAILED",
                        blocker_reason=f"COMPLETE_REPORT_FAILED:{type(exc).__name__}",
                        output_url=output_url,
                        output_metadata=sanitized_meta,
                        provider_submit_called=True,
                        provider_calls=1,
                        paid_provider_calls=1,
                        video_renders=1,
                    )

            provider_task_ids = gen_result.get("provider_task_ids") or []
            task_id_str = str(provider_task_ids[0] if provider_task_ids else (gen_result.get("provider_task_id") or ""))
            logger.info("web_product_video_job_completed job_id=%s task_id=%s", raw_job_id, task_id_str)
            return ConsumerExecutionOutcome(
                ok=True,
                job_id=raw_job_id,
                request_id=request_id,
                product_key=product_key,
                status="COMPLETED",
                output_url=output_url,
                output_metadata=sanitized_meta,
                provider_task_id=task_id_str,
                provider_submit_called=True,
                provider_calls=1,
                paid_provider_calls=1,
                video_renders=1,
                wallet_mutations=0,
            )

        # Provider execution failed
        blocker = str(gen_result.get("blocker") or gen_result.get("provider_error") or "PROVIDER_FAILED")
        err_msg = str(gen_result.get("public_message") or gen_result.get("exception_message_safe") or blocker)
        logger.warning("provider_execution_failed job_id=%s blocker=%s", raw_job_id, blocker)
        if client:
            try:
                client.fail(
                    job_id=raw_job_id,
                    error_code=blocker[:64],
                    error_message=err_msg[:1000],
                    fatal=True,
                )
            except Exception as exc:
                logger.error("fail_reporting_error job_id=%s err=%s", raw_job_id, type(exc).__name__)

        return ConsumerExecutionOutcome(
            ok=False,
            job_id=raw_job_id,
            request_id=request_id,
            product_key=product_key,
            status="PROVIDER_FAILED",
            blocker_reason=blocker,
            provider_submit_called=bool(gen_result.get("provider_submit_called")),
            provider_calls=1 if gen_result.get("provider_submit_called") else 0,
            paid_provider_calls=1 if gen_result.get("provider_submit_called") else 0,
            video_renders=0,
            wallet_mutations=0,
        )
    finally:
        _ACTIVE_JOB_IDS.discard(raw_job_id)
        # Deferred cleanup: temp dir kept alive through probe/validate/complete
        try:
            _tmp_ctx.__exit__(None, None, None)  # type: ignore[name-defined]
        except Exception:
            pass
