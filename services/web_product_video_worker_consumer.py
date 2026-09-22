"""Web Product Video Worker Consumer Adapter.

P0.WEBAPP.V3.CUSTOMER.PRODUCT_VIDEO.BOT_WORKER.CONSUMER.ADAPTER.R1
Program: P0.WEBAPP.FULL.PRODUCT.TRUTH.REMEDIATION.V1

This bounded module consumes canonical Web Product Video jobs for video_ai_prompt
from the Web dispatcher (/api/v1/worker/product-video/*) and maps them into the Bot
runtime VideoGenerationRequest contract.

Strict Safety Invariants:
- PROVIDER_SUBMIT_CALLED = False
- PROVIDER_CALLS = 0
- PAID_PROVIDER_CALLS = 0
- VIDEO_RENDERS = 0
- WALLET_MUTATIONS = 0
- PAYMENT_MUTATIONS = 0
- PRODUCTION_WORKER_ACTIVATION = False (Contract-only / provider-blocked by default)
- LIVE_WEB_CLAIMS = 0 (No background live polling daemon)
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping, Sequence

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


def map_web_job_to_bot_runtime(job: Mapping[str, Any]) -> VideoGenerationRequest:
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

    metadata = {
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
        request = map_web_job_to_bot_runtime(job)
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
    finally:
        _ACTIVE_JOB_IDS.discard(raw_job_id)
