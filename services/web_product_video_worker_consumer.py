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
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit

from services.video_provider_base import VideoGenerationRequest

logger = logging.getLogger("web_product_video_worker_consumer")

# Supported product scope for R1
PRIMARY_PRODUCT_KEY = "video_ai_prompt"
SUPPORTED_PRODUCTS: frozenset[str] = frozenset({PRIMARY_PRODUCT_KEY})

# Canonical execution / capability parameters
BOT_CANONICAL_PRODUCT_KEY = "video_ai_prompt"
BOT_EXECUTOR_PRODUCT_TYPE = "video_ai_prompt"
DEFAULT_REQUIRED_CAPABILITY = "text_to_video"
ALLOWED_ASPECT_RATIOS: frozenset[str] = frozenset({"9:16", "16:9", "1:1"})
MIN_DURATION_SECONDS: float = 1.0
MAX_DURATION_SECONDS: float = 60.0
MIN_PROMPT_LENGTH: int = 3
MAX_PROMPT_LENGTH: int = 2000

# Artifact & URL validation constants
SAFE_VIDEO_EXTENSIONS: frozenset[str] = frozenset({".mp4", ".webm", ".mov"})
SAFE_HOSTNAME_PATTERN = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
FORBIDDEN_OUTPUT_URL_SCHEMES = frozenset({"javascript:", "vbscript:", "data:", "file:", "blob:", "about:"})
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


def is_safe_video_output_url(url: Any) -> bool:
    """Validate that candidate Product Video output URL is safe to deliver."""
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
        parsed = urlsplit(trimmed)
    except Exception:
        return False
    if parsed.scheme.lower() != "https":
        return False
    if not parsed.netloc:
        return False
    if parsed.username or parsed.password or "@" in parsed.netloc:
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
    }
    return True, "", sanitized


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

    def claim(self, lease_seconds: int = 300) -> WebClaimResponse:
        """Claim the oldest queued canonical Product Video job from the Web dispatcher."""
        payload = {
            "worker_id": self.worker_id,
            "lease_seconds": max(30, int(lease_seconds)),
        }
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


def validate_claimed_job(job: Mapping[str, Any] | None) -> tuple[bool, str]:
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
    is_valid, reason = validate_claimed_job(job)
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

    if owner_acceptance_auth is not None:
        from services.video_provider_router import (
            OWNER_AUTHORIZED_LIVE_ACCEPTANCE,
            validate_owner_acceptance_authorization,
        )

        derived_route = derive_canonical_tier_route(quality, environ=env)
        derived_ctx: dict[str, Any] = {
            "user_id": str(account_id or job.get("account_id") or "").strip(),
            "job_id": job_id,
            "project_id": str(job.get("project_id") or "").strip(),
            "product_type": BOT_CANONICAL_PRODUCT_KEY,
            "provider": derived_route["provider"],
            "required_capability": derived_route["required_capability"],
            "tier": str(derived_route["tier_id"]),
            "estimated_provider_cost": derived_route["estimated_provider_cost"],
            "estimated_provider_cost_unit": derived_route["estimated_provider_cost_unit"],
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
        product_type=BOT_CANONICAL_PRODUCT_KEY,
        video_flow_type=BOT_EXECUTOR_PRODUCT_TYPE,
        prompt=prompt,
        ratio=aspect_ratio,
        duration_seconds=duration_seconds,
        quality=quality,
        metadata=metadata,
        required_capability=DEFAULT_REQUIRED_CAPABILITY,
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

    is_valid, validation_reason = validate_claimed_job(job)
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
    is_valid, validation_reason = validate_claimed_job(job)
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

            with tempfile.TemporaryDirectory(prefix="web_pv_worker_") as tmp_dir:
                active_out_dir = str(output_dir or tmp_dir)
                gen_result = fn(gen_request, output_dir=active_out_dir, environ=call_env)
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
                logger.error("unsafe_output_url_rejected job_id=%s url=%s", raw_job_id, output_url[:80])
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

            # Artifact metadata validation
            duration = float(gen_result.get("duration") or gen_result.get("duration_seconds") or (job.get("payload") or {}).get("duration") or 5.0)
            file_size = int(gen_result.get("bytes") or (os.path.getsize(output_path) if output_path and os.path.exists(output_path) else 0))
            ratio = str((job.get("payload") or {}).get("aspect_ratio") or "9:16").strip()
            dims = (720, 1280) if ratio == "9:16" else ((1280, 720) if ratio == "16:9" else (1024, 1024))
            raw_meta = {
                "duration_seconds": duration,
                "width": int(gen_result.get("width") or dims[0]),
                "height": int(gen_result.get("height") or dims[1]),
                "file_size_bytes": file_size,
                "format": str(gen_result.get("format") or "mp4").strip().lower(),
                "codec": str(gen_result.get("codec") or "h264").strip().lower(),
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
