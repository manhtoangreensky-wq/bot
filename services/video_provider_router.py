"""Video provider chain and routing for real product video rendering."""

from __future__ import annotations

import dataclasses
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any
from urllib.parse import urlparse

from providers.video_generic_http_provider import GenericHttpVideoProvider
from providers.video_kling_provider import KlingVideoProvider
from providers.video_veo_provider import VeoVideoProvider
from services.video_provider_base import (
    DisabledVideoProvider,
    VideoArtifactResult,
    VideoGenerationRequest,
    VideoPollResult,
    VideoProviderAdapter,
    VideoSubmitResult,
    mask_provider_task_id,
    normalize_provider_status,
    split_provider_chain,
)


DEFAULT_VIDEO_PROVIDER_CHAIN = "shopaikey_video,key4u_video,toanaas_video,veo,kling,generic_http"
VIDEO_STUB_PROVIDER_NAME = "stub_video"
PUBLIC_NO_VIDEO_PROVIDER_COPY = (
    "Hiện hệ thống dựng video AI chưa sẵn sàng. Bot chưa trừ Xu."
)
PUBLIC_PRODUCT_VIDEO_SUBMIT_BLOCKED_COPY = (
    "TOAN AAS đang tạm khóa tạo video AI để kiểm tra chất lượng. Hệ thống chưa trừ Xu."
)
VIDEO_CREDIT_BLOCKED_STATUSES = {
    "low",
    "low_credit",
    "exhausted",
    "quota_exhausted",
    "quota_empty",
    "frozen",
    "disabled",
    "blocked",
    "bad_health",
    "health_bad",
    "unhealthy",
}
PROVIDER_NONTERMINAL_STATUSES = {"not_start", "queued", "running", "processing", "in_progress", "pending"}
PROVIDER_PENDING_BLOCKERS = {"provider_in_progress", "provider_pending", "provider_status_unknown"}
DEFAULT_PRODUCT_VIDEO_PROVIDER_MAX_WAIT_SECONDS = 20 * 60
PRODUCT_VIDEO_CONTROLLED_FALLBACK_BLOCKERS = {
    "provider_failed_result_url_invalid",
    "provider_result_url_missing",
    "provider_download_failed",
    "provider_timeout",
    "duration_short",
    "final_duration_short_scene_coverage_missing",
    "provider_poll_failed",
}
PUBLIC_PRODUCT_VIDEO_TERMINAL_FAILURE_COPY = (
    "TOAN AAS chưa nhận được video hoàn chỉnh từ hệ thống dựng video. "
    "Bot chưa trừ Xu. Anh/chị có thể gửi video khác hoặc thử lại sau."
)


def _result_url_validation(result_url: str) -> dict[str, Any]:
    raw_url = str(result_url or "").strip()
    if not raw_url:
        return {
            "result_url_present_raw": False,
            "result_url_valid": False,
            "result_url_invalid_reason": "empty",
            "result_url_host": "",
            "result_url_scheme": "",
            "result_url_ext": "",
        }
    if raw_url[:1] in {"{", "["} or raw_url.lower() in {"none", "null", "false", "error"}:
        return {
            "result_url_present_raw": True,
            "result_url_valid": False,
            "result_url_invalid_reason": "provider_error_object",
            "result_url_host": "",
            "result_url_scheme": "",
            "result_url_ext": "",
        }
    parsed = urlparse(raw_url)
    extension = os.path.splitext(parsed.path or "")[1].lower()
    scheme = str(parsed.scheme or "").lower()
    host = str(parsed.netloc or "").strip()
    if scheme not in {"http", "https"} or not host:
        return {
            "result_url_present_raw": True,
            "result_url_valid": False,
            "result_url_invalid_reason": "missing_scheme_or_host",
            "result_url_host": str(parsed.hostname or ""),
            "result_url_scheme": scheme,
            "result_url_ext": extension,
        }
    return {
        "result_url_present_raw": True,
        "result_url_valid": True,
        "result_url_invalid_reason": "",
        "result_url_host": str(parsed.hostname or host),
        "result_url_scheme": scheme,
        "result_url_ext": extension,
    }


def _failed_result_url_diagnostic(result_url: str) -> dict[str, Any]:
    raw_url = str(result_url or "").strip()
    url_check = _result_url_validation(raw_url)
    return {
        "result_url_present": bool(url_check.get("result_url_valid")),
        "provider_result_url_present": bool(url_check.get("result_url_valid")),
        **url_check,
        "download_http_status": 0,
        "download_content_type": "",
        "download_bytes": 0,
        "download_error_class": "provider_terminal_failure",
        "download_error_message_masked": "Provider reported terminal failure; result URL was not trusted or downloaded.",
        "mp4_validator_result": "not_run_provider_terminal_failure",
        "result_url_trusted": False,
    }


def _env_flag(env: dict[str, str], name: str, default: str = "0") -> bool:
    return str(env.get(name, default) or default).strip().lower() in {"1", "true", "yes", "on"}


def _env_flag_detail(
    env: dict[str, str] | None,
    name: str,
    default: str = "0",
    *,
    fallback_to_process_env: bool = False,
) -> dict[str, Any]:
    env_data = dict(env or {})
    if name in env_data:
        raw = str(env_data.get(name, "") or "").strip()
        source = "environ"
    elif fallback_to_process_env and name in os.environ:
        raw = str(os.environ.get(name, "") or "").strip()
        source = "process_env"
    else:
        raw = str(default)
        source = "default"
    normalized = raw.strip().lower()
    truthy = {"1", "true", "yes", "on"}
    falsy = {"0", "false", "no", "off", ""}
    if normalized in truthy:
        resolved = True
    elif normalized in falsy:
        resolved = False
    else:
        resolved = False
        source = f"invalid_{source}"
    return {
        "raw": raw,
        "resolved": bool(resolved),
        "source": source,
    }


def _env_int(env: dict[str, str], name: str, default: int) -> int:
    try:
        return int(str(env.get(name, str(default)) or str(default)).strip())
    except Exception:
        return int(default)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if isinstance(value, bool):
            return int(value)
        text = str(value or "").strip().rstrip("%")
        if not text:
            return int(default)
        return int(float(text))
    except Exception:
        return int(default)


def _first_nonempty_value(*values: Any) -> str:
    for value in values:
        if isinstance(value, (list, tuple)):
            for item in value:
                text = str(item or "").strip()
                if text:
                    return text
            continue
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _metadata_existing_provider_task(metadata: dict[str, Any]) -> tuple[str, str, str]:
    metadata = dict(metadata or {})
    provider = _first_nonempty_value(
        metadata.get("provider_pending_provider"),
        metadata.get("selected_provider"),
        metadata.get("selected_provider_before_submit"),
        metadata.get("provider"),
    )
    task_id = _first_nonempty_value(
        metadata.get("provider_pending_task_id"),
        metadata.get("provider_task_id"),
        metadata.get("provider_job_id"),
        metadata.get("provider_task_ids"),
    )
    video_id = _first_nonempty_value(
        metadata.get("provider_pending_video_id"),
        metadata.get("provider_video_id"),
        metadata.get("provider_video_ids"),
    )
    return provider, task_id, video_id


def product_video_submit_enabled(env: dict[str, str] | None = None) -> bool:
    return bool(product_video_submit_switch_detail(env).get("resolved"))


def product_video_submit_switch_detail(env: dict[str, str] | None = None) -> dict[str, Any]:
    detail = _env_flag_detail(
        env,
        "PRODUCT_VIDEO_PROVIDER_SUBMIT_ENABLED",
        "1",
        fallback_to_process_env=True,
    )
    if detail.get("resolved"):
        return detail
    for public_flag in (
        "SHOPAIKEY_PUBLIC_VIDEO_ENABLED",
        "KEY4U_PUBLIC_VIDEO_ENABLED",
        "KEY4U_PUBLIC_ENABLED",
        "VIDEO_AI_PUBLIC_ENABLED",
        "PUBLIC_VIDEO_GENERATION_ENABLED",
    ):
        flag_detail = _env_flag_detail(env, public_flag, "", fallback_to_process_env=True)
        if flag_detail.get("resolved"):
            return {
                **detail,
                "resolved": True,
                "source": f"{public_flag.lower()}_override",
                "override_flag": public_flag,
                "override_raw": flag_detail.get("raw", ""),
                "previous_source": detail.get("source", ""),
                "previous_raw": detail.get("raw", ""),
            }
    return detail


PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_FINAL_CONFIRM = "public_user_final_confirm"
PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_FALLBACK_ONCE = "public_confirmed_fallback_once"
PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_SCENE_FALLBACK_ONCE = "public_confirmed_scene_fallback_once"
PRODUCT_VIDEO_SUBMIT_SOURCE_WORKER_POLL_EXISTING_TASK = "worker_poll_existing_task"
PRODUCT_VIDEO_HIDDEN_SUBMIT_SOURCES = {
    "codex_test",
    "smoke",
    "debug",
    "recover",
    "status",
    "background_retry",
    "fallback",
}


def normalize_product_video_submit_source(value: Any = "") -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    aliases = {
        "public_confirm": PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_FINAL_CONFIRM,
        "final_confirm": PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_FINAL_CONFIRM,
        "user_final_confirm": PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_FINAL_CONFIRM,
        "b14_confirm": PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_FINAL_CONFIRM,
        "public_confirmed_fallback_once": PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_FALLBACK_ONCE,
        "public_fallback_once": PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_FALLBACK_ONCE,
        "public_confirmed_scene_fallback_once": PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_SCENE_FALLBACK_ONCE,
        "public_scene_fallback_once": PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_SCENE_FALLBACK_ONCE,
        "poll_existing_task": PRODUCT_VIDEO_SUBMIT_SOURCE_WORKER_POLL_EXISTING_TASK,
        "worker_poll": PRODUCT_VIDEO_SUBMIT_SOURCE_WORKER_POLL_EXISTING_TASK,
        "worker_poll_existing": PRODUCT_VIDEO_SUBMIT_SOURCE_WORKER_POLL_EXISTING_TASK,
        "admin_smoke": "smoke",
        "slash_smoke": "smoke",
        "manual_debug": "debug",
        "video_render_debug": "debug",
        "video_provider_job_debug": "debug",
        "admin_recover": "recover",
        "provider_recover": "recover",
        "manual_status": "status",
        "auto_status": "status",
        "manual_refresh": "status",
    }
    return aliases.get(normalized, normalized)


def product_video_provider_submit_source_policy(
    metadata: dict[str, Any] | None = None,
    *,
    public_submit_enabled: bool = False,
    poll_existing_task: bool = False,
) -> dict[str, Any]:
    metadata = dict(metadata or {})
    source = normalize_product_video_submit_source(
        metadata.get("submit_source")
        or metadata.get("provider_submit_source")
        or metadata.get("source_context")
        or metadata.get("entry_source")
        or ""
    )
    if not source and (
        metadata.get("public_user_confirmed")
        or metadata.get("interactive_product")
        or metadata.get("product_video")
        or metadata.get("public_user")
    ):
        # Legacy Product Video jobs created before R10B did not persist a source.
        # They still represent a visible final-confirm route, not a hidden smoke.
        source = PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_FINAL_CONFIRM
    public_user_confirmed = bool(
        metadata.get("public_user_confirmed")
        or metadata.get("b14_public_user_confirmed")
        or metadata.get("user_final_confirmed")
        or source in {
            PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_FINAL_CONFIRM,
            PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_FALLBACK_ONCE,
            PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_SCENE_FALLBACK_ONCE,
        }
    )
    if poll_existing_task or source == PRODUCT_VIDEO_SUBMIT_SOURCE_WORKER_POLL_EXISTING_TASK:
        return {
            "submit_source": PRODUCT_VIDEO_SUBMIT_SOURCE_WORKER_POLL_EXISTING_TASK,
            "public_user_confirmed": public_user_confirmed,
            "provider_submit_allowed": False,
            "provider_submit_block_reason": "worker_poll_existing_task_read_only",
            "poll_existing_task_allowed": True,
        }
    if source in PRODUCT_VIDEO_HIDDEN_SUBMIT_SOURCES:
        return {
            "submit_source": source,
            "public_user_confirmed": public_user_confirmed,
            "provider_submit_allowed": False,
            "provider_submit_block_reason": "hidden_submit_source_blocked",
            "poll_existing_task_allowed": False,
        }
    if source not in {
        PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_FINAL_CONFIRM,
        PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_FALLBACK_ONCE,
        PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_SCENE_FALLBACK_ONCE,
    }:
        return {
            "submit_source": source or "missing",
            "public_user_confirmed": public_user_confirmed,
            "provider_submit_allowed": False,
            "provider_submit_block_reason": "submit_source_not_public_final_confirm",
            "poll_existing_task_allowed": False,
        }
    if not public_user_confirmed:
        return {
            "submit_source": source,
            "public_user_confirmed": False,
            "provider_submit_allowed": False,
            "provider_submit_block_reason": "public_user_confirm_missing",
            "poll_existing_task_allowed": False,
        }
    if not public_submit_enabled:
        return {
            "submit_source": source,
            "public_user_confirmed": True,
            "provider_submit_allowed": False,
            "provider_submit_block_reason": "public_provider_submit_disabled",
            "poll_existing_task_allowed": False,
        }
    return {
        "submit_source": source,
        "public_user_confirmed": True,
        "provider_submit_allowed": True,
        "provider_submit_block_reason": "",
        "poll_existing_task_allowed": False,
    }


def paid_retry_requires_confirmation(env: dict[str, str] | None = None) -> bool:
    env = dict(env or os.environ)
    return _env_flag(env, "PRODUCT_VIDEO_PAID_RETRY_REQUIRES_CONFIRMATION", "1")


def product_video_retry_confirmed(metadata: dict[str, Any] | None = None) -> bool:
    metadata = dict(metadata or {})
    return bool(
        metadata.get("explicit_paid_retry_confirmed")
        or metadata.get("product_video_paid_retry_confirmed")
        or metadata.get("paid_provider_retry_confirmed")
        or metadata.get("paid_fallback_confirmed")
    )


def _truthy_metadata(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "on", "confirmed", "delivered", "charged"}


def _int_metadata(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(str(value).strip()))
    except Exception:
        return default


def product_video_public_confirm_context(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return persisted Product Video confirmation context for paid fallback decisions."""
    metadata = dict(metadata or {})
    current_source = normalize_product_video_submit_source(
        metadata.get("submit_source")
        or metadata.get("provider_submit_source")
        or metadata.get("source_context")
        or metadata.get("entry_source")
        or ""
    )
    original_source = normalize_product_video_submit_source(
        metadata.get("original_submit_source")
        or metadata.get("public_confirm_submit_source")
        or metadata.get("initial_submit_source")
        or metadata.get("provider_original_submit_source")
        or metadata.get("job_original_submit_source")
        or metadata.get("invoice_submit_source")
        or metadata.get("project_submit_source")
        or ""
    )
    if not original_source and current_source not in PRODUCT_VIDEO_HIDDEN_SUBMIT_SOURCES | {PRODUCT_VIDEO_SUBMIT_SOURCE_WORKER_POLL_EXISTING_TASK}:
        original_source = current_source
    if not original_source and (
        _truthy_metadata(metadata.get("public_user_confirmed"))
        or _truthy_metadata(metadata.get("b14_public_user_confirmed"))
        or _truthy_metadata(metadata.get("user_final_confirmed"))
        or _truthy_metadata(metadata.get("invoice_confirmed"))
        or _truthy_metadata(metadata.get("final_invoice_confirmed"))
        or _truthy_metadata(metadata.get("project_is_confirmed"))
        or _truthy_metadata(metadata.get("is_confirmed"))
        or _truthy_metadata(metadata.get("confirmed"))
        or _truthy_metadata(metadata.get("public_user"))
    ):
        original_source = PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_FINAL_CONFIRM

    public_user_confirmed = bool(
        _truthy_metadata(metadata.get("public_user_confirmed"))
        or _truthy_metadata(metadata.get("b14_public_user_confirmed"))
        or _truthy_metadata(metadata.get("user_final_confirmed"))
        or original_source
        in {
            PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_FINAL_CONFIRM,
            PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_FALLBACK_ONCE,
        }
    )
    invoice_confirmed = bool(
        _truthy_metadata(metadata.get("invoice_confirmed"))
        or _truthy_metadata(metadata.get("final_invoice_confirmed"))
        or _truthy_metadata(metadata.get("project_is_confirmed"))
        or _truthy_metadata(metadata.get("is_confirmed"))
        or _truthy_metadata(metadata.get("confirmed"))
        or _truthy_metadata(metadata.get("b14_invoice_confirmed"))
        or (
            public_user_confirmed
            and original_source
            in {
                PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_FINAL_CONFIRM,
                PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_FALLBACK_ONCE,
            }
        )
    )
    delivered = bool(
        _truthy_metadata(metadata.get("delivered"))
        or _truthy_metadata(metadata.get("video_delivered"))
        or _truthy_metadata(metadata.get("delivery_succeeded"))
        or _truthy_metadata(metadata.get("telegram_delivery_succeeded"))
        or _truthy_metadata(metadata.get("final_delivered"))
        or bool(metadata.get("final_video_file_id") or metadata.get("video_delivery_message_id"))
    )
    charged_xu = max(
        _int_metadata(metadata.get("charged_xu"), 0),
        _int_metadata(metadata.get("charged_amount_xu"), 0),
        _int_metadata(metadata.get("wallet_charged_xu"), 0),
        _int_metadata(metadata.get("total_xu_charged"), 0),
        _int_metadata(metadata.get("charge"), 0),
    )
    charged = bool(charged_xu > 0 or _truthy_metadata(metadata.get("wallet_charge_recorded")))
    provider_submit_accepted_before = bool(
        _truthy_metadata(metadata.get("provider_submit_accepted_before"))
        or _truthy_metadata(metadata.get("submit_accepted"))
        or _truthy_metadata(metadata.get("provider_task_id_saved"))
        or bool(
            metadata.get("provider_pending_task_id")
            or metadata.get("provider_pending_video_id")
            or metadata.get("provider_task_id")
            or metadata.get("provider_video_id")
            or metadata.get("canonical_provider_task_id")
            or metadata.get("canonical_task_id")
            or metadata.get("provider_task_ids")
            or metadata.get("provider_video_ids")
        )
    )
    fallback_count = _int_metadata(metadata.get("fallback_count") or metadata.get("provider_fallback_count"), 0)
    current_hidden = current_source in PRODUCT_VIDEO_HIDDEN_SUBMIT_SOURCES
    original_public = original_source in {
        PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_FINAL_CONFIRM,
        PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_FALLBACK_ONCE,
    }
    fallback_eligibility_source = original_source or current_source or "missing"
    return {
        "current_source": current_source or "missing",
        "original_submit_source": original_source or "",
        "public_user_confirmed": public_user_confirmed,
        "invoice_confirmed": invoice_confirmed,
        "provider_submit_accepted_before": provider_submit_accepted_before,
        "delivered": delivered,
        "charged": charged,
        "charged_xu": charged_xu,
        "fallback_count": fallback_count,
        "current_source_hidden": current_hidden,
        "original_source_public": original_public,
        "fallback_eligibility_source": fallback_eligibility_source,
    }


def product_video_controlled_fallback_policy(
    blocker: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = dict(metadata or {})
    context = product_video_public_confirm_context(metadata)
    clean_blocker = str(blocker or "").strip()
    allowed = True
    reason = ""
    if context["current_source_hidden"]:
        allowed = False
        reason = "hidden_or_read_only_source"
    elif not context["original_source_public"]:
        allowed = False
        reason = "source_not_public_confirmed_fallback"
    elif not context["public_user_confirmed"]:
        allowed = False
        reason = "public_confirm_missing"
    elif not context["invoice_confirmed"]:
        allowed = False
        reason = "invoice_confirm_missing"
    elif not context["provider_submit_accepted_before"]:
        allowed = False
        reason = "provider_submit_not_accepted_before"
    elif context["delivered"]:
        allowed = False
        reason = "already_delivered"
    elif context["charged"]:
        allowed = False
        reason = "already_charged"
    elif context["fallback_count"] >= 1:
        allowed = False
        reason = "fallback_limit_reached"
    elif clean_blocker not in PRODUCT_VIDEO_CONTROLLED_FALLBACK_BLOCKERS:
        allowed = False
        reason = "blocker_not_fallbackable"
    return {
        **context,
        "fallback_allowed": bool(allowed),
        "fallback_block_reason": reason,
        "fallback_blocked_reason": reason,
        "fallback_reason": clean_blocker if allowed else "",
        "fallback_submit_source": PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_FALLBACK_ONCE if allowed else "",
    }


def product_video_controlled_fallback_allowed(
    blocker: str,
    metadata: dict[str, Any] | None = None,
) -> bool:
    return bool(product_video_controlled_fallback_policy(blocker, metadata).get("fallback_allowed"))


def _product_video_paid_fallback_blocked(
    blocker: str,
    env: dict[str, str] | None,
    metadata: dict[str, Any] | None,
) -> bool:
    if not paid_retry_requires_confirmation(env) or product_video_retry_confirmed(metadata):
        return False
    # Missing submit config is a local setup check, not a provider credit spend.
    # Let the chain inspect the next provider so admin diagnostics can report
    # the exact all-config-missing state without triggering a paid retry path.
    if str(blocker or "").strip() == "provider_config_missing_at_submit":
        return False
    if product_video_controlled_fallback_allowed(blocker, metadata):
        return False
    return True


def provider_failure_cooldown_state(
    metadata: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    metadata = dict(metadata or {})
    env = dict(env or os.environ)
    enabled = _env_flag(env, "PRODUCT_VIDEO_PROVIDER_FAILURE_COOLDOWN_ENABLED", "1")
    threshold = max(1, _env_int(env, "PRODUCT_VIDEO_PROVIDER_FAILURE_COOLDOWN_THRESHOLD", 3))
    window_minutes = max(1, _env_int(env, "PRODUCT_VIDEO_PROVIDER_FAILURE_COOLDOWN_WINDOW_MINUTES", 60))
    recent_failures = max(
        _as_int(metadata.get("recent_provider_failures"), 0),
        _as_int(metadata.get("recent_product_video_provider_failures"), 0),
        _as_int(env.get("PRODUCT_VIDEO_PROVIDER_RECENT_FAILURES"), 0),
    )
    active = bool(enabled and recent_failures >= threshold)
    return {
        "provider_health_cooldown_enabled": bool(enabled),
        "provider_health_cooldown_active": active,
        "recent_provider_failures": recent_failures,
        "provider_failure_cooldown_threshold": threshold,
        "provider_failure_cooldown_window_minutes": window_minutes,
    }


def _progress_value(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        raw = float(str(value).strip().rstrip("%"))
    except Exception:
        return 0
    if 0 < raw <= 1:
        raw *= 100
    return max(0, min(100, int(raw)))


def _progress_raw_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        raw = float(str(value).strip().rstrip("%"))
    except Exception:
        return None
    if 0 < raw <= 1:
        raw *= 100
    return raw


def _progress_from_raw(raw: Any) -> Any:
    if raw in (None, ""):
        return None
    if isinstance(raw, dict):
        for key in (
            "provider_progress_raw",
            "shopaikey_data_progress_raw",
            "data_progress_raw",
            "provider_progress_percent",
            "progress_percent",
            "progress",
            "percent",
            "percentage",
        ):
            value = raw.get(key)
            if value not in (None, ""):
                return value
        for key in ("data", "result", "output", "response", "raw", "provider_raw", "poll_raw"):
            nested = _progress_from_raw(raw.get(key))
            if nested not in (None, ""):
                return nested
    if isinstance(raw, (list, tuple)):
        for value in raw:
            nested = _progress_from_raw(value)
            if nested not in (None, ""):
                return nested
    return raw if isinstance(raw, (int, float, str)) and str(raw).strip().rstrip("%").replace(".", "", 1).isdigit() else None


def _poll_result_url_present(poll_result: VideoPollResult) -> bool:
    for value in (
        getattr(poll_result, "result_url", ""),
        getattr(poll_result, "download_url", ""),
        getattr(poll_result, "file_url", ""),
    ):
        if str(value or "").strip():
            return True
    raw = getattr(poll_result, "raw", {}) or {}
    if isinstance(raw, dict):
        for key in ("result_url", "download_url", "file_url", "video_url", "output_url", "final_video_url"):
            if str(raw.get(key) or "").strip():
                return True
    return False


def _provider_status_for_progress(poll_result: VideoPollResult) -> str:
    status = str(
        getattr(poll_result, "normalized_status", "")
        or getattr(poll_result, "status", "")
        or ""
    ).strip().lower()
    return status or "running"


def _effective_provider_progress(
    normalized_progress: int,
    *,
    raw_progress_number: float | None = None,
    status: str,
    result_url_present: bool,
) -> tuple[int, bool, str, bool]:
    if raw_progress_number is not None and (raw_progress_number < 0 or raw_progress_number > 100):
        return 0, False, "invalid_provider_progress_raw", False
    if normalized_progress <= 0:
        return 0, False, "", False
    running = status in {"running", "queued", "pending", "in_progress", "processing", "not_start", "final_rendering"}
    if normalized_progress >= 100 and result_url_present and not running:
        return 100, True, "", False
    if running and not result_url_present and normalized_progress >= 100:
        return 0, False, "in_progress_without_result_url", False
    if running and not result_url_present:
        return normalized_progress, True, "", False
    if result_url_present:
        return max(95, min(99, normalized_progress)), True, "", False
    return min(99, normalized_progress), normalized_progress < 100, "missing_final_mp4" if normalized_progress >= 100 else "", normalized_progress >= 100


def _epoch_text(epoch: float) -> str:
    try:
        if float(epoch) > 0:
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(epoch)))
    except Exception:
        pass
    return ""


def _metadata_epoch(metadata: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = metadata.get(key)
        if value in (None, ""):
            continue
        try:
            epoch = float(value)
            if epoch > 0:
                return epoch
        except Exception:
            pass
    return 0.0


def _provider_pending_telemetry(
    request: VideoGenerationRequest,
    poll_result: VideoPollResult,
    *,
    attempt_traces: list[dict[str, Any]],
    wait_max: int,
) -> dict[str, Any]:
    metadata = dict(request.metadata or {})
    now_epoch = time.time()
    started_epoch = _metadata_epoch(
        metadata,
        "provider_started_at_epoch",
        "provider_wait_started_epoch",
    )
    if started_epoch <= 0:
        started_epoch = now_epoch
        started_source = "current_accept_time"
        elapsed_estimated = False
    else:
        started_source = "metadata"
        elapsed_estimated = False
    poll_raw = dict(getattr(poll_result, "raw", {}) or {})
    raw_progress = _progress_from_raw(poll_raw)
    if raw_progress in (None, ""):
        raw_progress = poll_result.progress_percent
    normalized_progress = _progress_value(raw_progress)
    raw_progress_number = _progress_raw_number(raw_progress)
    elapsed = max(0, int(now_epoch - started_epoch))
    result_url_present = _poll_result_url_present(poll_result)
    provider_status = _provider_status_for_progress(poll_result)
    effective_progress, trusted, cap_reason, cap_applied = _effective_provider_progress(
        normalized_progress,
        raw_progress_number=raw_progress_number,
        status=provider_status,
        result_url_present=result_url_present,
    )
    previous_render_progress = max(
        _as_int(metadata.get("render_video_progress_percent"), 0),
        _as_int(metadata.get("provider_render_progress_percent"), 0),
    )
    poll_count = sum(1 for item in attempt_traces if isinstance(item, dict) and (item.get("poll_called") or item.get("phase") == "poll"))
    poll_count = max(0, poll_count)
    poll_count_source = "provider_attempts" if poll_count > 0 else "none"
    provider_progress_public_suppressed = bool(
        not result_url_present
        and (
            not trusted
            or bool(poll_raw.get("http_200_not_used_as_progress"))
        )
    )
    if result_url_present:
        render_progress = max(previous_render_progress, 95)
        render_source = "provider_result_url"
        estimated = False
    elif effective_progress > 0 and trusted:
        render_progress = max(previous_render_progress, effective_progress)
        render_source = "provider_raw"
        estimated = False
    else:
        render_progress = 0
        render_source = "indeterminate"
        estimated = False
    provider_progress = effective_progress or render_progress
    poll_interval = _env_int(dict(os.environ), "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS", 25)
    return {
        "provider_started_at": metadata.get("provider_started_at") or _epoch_text(started_epoch),
        "provider_started_at_epoch": started_epoch,
        "provider_started_at_source": started_source,
        "provider_elapsed_estimated": elapsed_estimated,
        "provider_progress_raw": raw_progress if raw_progress not in (None, "") else "",
        "provider_progress_source": str(poll_raw.get("provider_progress_source") or poll_raw.get("shopaikey_progress_source") or ("poll_result" if raw_progress not in (None, "") else "none")),
        "provider_progress_normalized": normalized_progress,
        "provider_progress_raw_number": raw_progress_number if raw_progress_number is not None else "",
        "provider_progress_trusted": trusted,
        "provider_progress_cap_reason": cap_reason,
        "provider_progress_cap_applied": cap_applied,
        "provider_progress_effective": effective_progress,
        "provider_progress_estimated": estimated,
        "provider_progress_percent": provider_progress,
        "render_video_progress_percent": max(0, min(100, render_progress)),
        "provider_render_progress_percent": max(0, min(100, render_progress)),
        "render_video_progress_percent_public": "0" if provider_progress_public_suppressed else str(max(0, min(100, render_progress))),
        "provider_progress_public_suppressed": provider_progress_public_suppressed,
        "render_progress_public_mode": "zero_waiting" if provider_progress_public_suppressed else "percent",
        "public_zero_bar_due_to_untrusted_provider": provider_progress_public_suppressed,
        "fake_progress_prevented": provider_progress_public_suppressed,
        "fake_progress_prevention_reason": "untrusted_provider_progress_without_result_url" if provider_progress_public_suppressed else "",
        "percent_conservative_due_to_untrusted_provider": provider_progress_public_suppressed,
        "render_progress_source": render_source,
        "render_progress_raw_provider": raw_progress if raw_progress not in (None, "") else "",
        "render_progress_estimated": estimated,
        "render_progress_cap_applied": cap_applied,
        "render_progress_result_url_present": result_url_present,
        "render_progress_monotonic_applied": bool(previous_render_progress and render_progress >= previous_render_progress),
        "overall_progress_from_render": 95 if result_url_present else (20 if provider_progress_public_suppressed else min(85, 20 + int(max(0, min(100, render_progress)) * 0.65))),
        "provider_status_for_progress": provider_status,
        "provider_poll_count": poll_count,
        "provider_poll_count_source": poll_count_source,
        "provider_last_poll_at": _epoch_text(now_epoch),
        "provider_elapsed_seconds": elapsed,
        "provider_wait_elapsed_seconds": elapsed,
        "provider_wait_max_seconds": wait_max,
        "elapsed_wall_clock_seconds": elapsed,
        "previous_elapsed_seconds": _as_int(metadata.get("provider_wait_elapsed_seconds") or metadata.get("provider_elapsed_seconds"), 0),
        "elapsed_monotonic_applied": False,
        "panel_refresh_interval_seconds": poll_interval,
        "result_url_present": result_url_present,
        "provider_result_url_present": result_url_present,
        "next_poll_scheduled_at": _epoch_text(now_epoch + max(1, poll_interval)),
        "http_200_not_used_as_progress": bool(poll_raw.get("http_200_not_used_as_progress")),
        "shopaikey_status_endpoint_exact": bool(poll_raw.get("shopaikey_status_endpoint_exact")),
        "shopaikey_status_http_code": _debug_http_status(poll_raw, "shopaikey_status_http_code"),
        "shopaikey_raw_status": poll_raw.get("shopaikey_raw_status") or poll_raw.get("provider_status_raw") or "",
        "shopaikey_normalized_status": poll_raw.get("shopaikey_normalized_status") or _provider_status_for_progress(poll_result),
        "shopaikey_data_progress_raw": poll_raw.get("shopaikey_data_progress_raw") if poll_raw.get("shopaikey_data_progress_raw") not in (None, "") else "",
        "shopaikey_progress_source": poll_raw.get("shopaikey_progress_source") or poll_raw.get("provider_progress_source") or "none",
        "shopaikey_result_url_from_data": bool(poll_raw.get("shopaikey_result_url_from_data")),
        "shopaikey_data_result_url_present": bool(poll_raw.get("shopaikey_result_url_from_data") and result_url_present),
        "result_url_source_path": poll_raw.get("result_url_source_path") or poll_raw.get("result_field_path") or "",
    }


def _join_url(base: str, endpoint: str) -> str:
    base = str(base or "").strip().rstrip("/")
    endpoint = str(endpoint or "").strip()
    if endpoint.startswith(("http://", "https://")):
        return endpoint
    clean_endpoint = endpoint.lstrip("/")
    base_last = base.rsplit("/", 1)[-1].strip().lower()
    if base_last and clean_endpoint.lower().startswith(base_last + "/"):
        clean_endpoint = clean_endpoint[len(base_last) + 1 :]
    return base + "/" + clean_endpoint if base and clean_endpoint else base or clean_endpoint


def _with_derived(env: dict[str, str], updates: dict[str, str]) -> dict[str, str]:
    result = dict(env)
    for key, value in updates.items():
        if value and not result.get(key):
            result[key] = value
    return result


def _bearer(value: str) -> str:
    token = str(value or "").strip()
    if not token:
        return ""
    return token if token.lower().startswith(("bearer ", "apikey ", "key ")) else f"Bearer {token}"


def _first_env(env: dict[str, str], *names: str) -> str:
    for name in names:
        value = str(env.get(name) or "").strip()
        if value:
            return value
    return ""


def _first_env_name_value(env: dict[str, str], *names: str) -> tuple[str, str]:
    for name in names:
        value = str(env.get(name) or "").strip()
        if value:
            return name, value
    return "", ""


def _normalize_credit_status(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not raw or raw in {"none", "null", "n_a", "na", "unknown"}:
        return "unknown"
    aliases = {
        "ok": "ok",
        "ready": "ok",
        "healthy": "ok",
        "has_credit": "ok",
        "sufficient": "ok",
        "available": "ok",
        "normal": "ok",
        "good": "ok",
        "lowcredit": "low_credit",
        "low_balance": "low_credit",
        "out_of_credit": "exhausted",
        "outofcredit": "exhausted",
        "no_credit": "exhausted",
        "no_balance": "exhausted",
        "empty": "exhausted",
        "quota_empty": "quota_exhausted",
        "quota_exceeded": "quota_exhausted",
        "rate_limited": "bad_health",
        "error": "bad_health",
        "failed": "bad_health",
    }
    return aliases.get(raw, raw)


def _provider_credit_prefixes(provider: str) -> list[str]:
    normalized = str(provider or "").strip().lower()
    if normalized == "shopaikey_video":
        return ["SHOPAIKEY_VIDEO", "SHOPAIKEY"]
    if normalized == "key4u_video":
        return ["KEY4U_VIDEO", "KEY4U"]
    if normalized == "toanaas_video":
        return ["VIDEO_TOANAAS", "TOANAAS_VIDEO", "TOANAAS"]
    if normalized == "veo":
        return ["VIDEO_VEO", "VEO"]
    if normalized == "kling":
        return ["VIDEO_KLING", "KLING"]
    if normalized == "generic_http":
        return ["VIDEO_GENERIC_HTTP", "GENERIC_HTTP"]
    return [normalized.upper()]


def provider_credit_status(provider: str, env: dict[str, str] | None = None) -> str:
    data = dict(env or os.environ)
    prefixes = _provider_credit_prefixes(provider)
    flag_suffixes = [
        ("FROZEN", "frozen"),
        ("EXHAUSTED", "exhausted"),
        ("QUOTA_EXHAUSTED", "quota_exhausted"),
        ("LOW_CREDIT", "low_credit"),
        ("LOW_BALANCE", "low_credit"),
        ("HEALTH_BAD", "bad_health"),
        ("DISABLED", "disabled"),
    ]
    for prefix in prefixes:
        for suffix, status in flag_suffixes:
            if _env_flag(data, f"{prefix}_{suffix}", "0"):
                return status
    for suffix in ("CREDIT_STATUS", "BALANCE_STATUS", "HEALTH_STATUS", "STATUS"):
        for prefix in prefixes:
            value = str(data.get(f"{prefix}_{suffix}") or "").strip()
            if value:
                return _normalize_credit_status(value)
    return "unknown"


def provider_credit_allows_selection(status: str) -> bool:
    normalized = _normalize_credit_status(status)
    return normalized not in VIDEO_CREDIT_BLOCKED_STATUSES


def _endpoint_alias(env: dict[str, str], direct_name: str, base_name: str, endpoint_name: str, *legacy_names: str) -> str:
    direct = _first_env(env, direct_name, *legacy_names)
    if direct:
        return direct
    base = str(env.get(base_name) or "").strip()
    endpoint = str(env.get(endpoint_name) or "").strip()
    if base and endpoint:
        return _join_url(base, endpoint)
    return ""


VIDEO_PROVIDER_ENV_NAMESPACES: dict[str, dict[str, Any]] = {
    "shopaikey_video": {
        "canonical_prefix": "SHOPAIKEY_VIDEO",
        "alias_prefixes": ["VIDEO_SHOPAIKEY"],
        "enabled": ["SHOPAIKEY_VIDEO_ENABLED", "VIDEO_SHOPAIKEY_ENABLED"],
        "submit_url": ["SHOPAIKEY_VIDEO_SUBMIT_URL", "VIDEO_SHOPAIKEY_SUBMIT_URL", "SHOPAIKEY_VIDEO_URL"],
        "poll_url": ["SHOPAIKEY_VIDEO_POLL_URL", "VIDEO_SHOPAIKEY_POLL_URL", "SHOPAIKEY_VIDEO_STATUS_ENDPOINT"],
        "auth_header_name": ["SHOPAIKEY_VIDEO_AUTH_HEADER_NAME", "VIDEO_SHOPAIKEY_AUTH_HEADER_NAME"],
        "auth_header_value": ["SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE", "VIDEO_SHOPAIKEY_AUTH_HEADER_VALUE"],
        "model": ["SHOPAIKEY_VIDEO_MODEL", "VIDEO_SHOPAIKEY_MODEL", "SHOPAIKEY_VIDEO_MODEL_PRIMARY"],
        "capabilities": ["SHOPAIKEY_VIDEO_CAPABILITIES", "VIDEO_SHOPAIKEY_CAPABILITIES"],
    },
    "key4u_video": {
        "canonical_prefix": "KEY4U_VIDEO",
        "alias_prefixes": ["VIDEO_KEY4U"],
        "enabled": ["KEY4U_VIDEO_ENABLED", "VIDEO_KEY4U_ENABLED"],
        "submit_url": ["KEY4U_VIDEO_SUBMIT_URL", "VIDEO_KEY4U_SUBMIT_URL"],
        "poll_url": ["KEY4U_VIDEO_POLL_URL", "VIDEO_KEY4U_POLL_URL"],
        "auth_header_name": ["KEY4U_VIDEO_AUTH_HEADER_NAME", "VIDEO_KEY4U_AUTH_HEADER_NAME"],
        "auth_header_value": ["KEY4U_VIDEO_AUTH_HEADER_VALUE", "VIDEO_KEY4U_AUTH_HEADER_VALUE"],
        "model": ["KEY4U_VIDEO_MODEL", "VIDEO_KEY4U_MODEL"],
        "capabilities": ["KEY4U_VIDEO_CAPABILITIES", "VIDEO_KEY4U_CAPABILITIES"],
    },
}


def video_provider_namespace_config(provider: str, env: dict[str, str] | None = None) -> dict[str, Any]:
    data = dict(env or os.environ)
    spec = VIDEO_PROVIDER_ENV_NAMESPACES.get(str(provider or "").strip().lower(), {})
    canonical_prefix = str(spec.get("canonical_prefix") or "").strip()
    alias_prefixes = [str(item) for item in (spec.get("alias_prefixes") or []) if str(item).strip()]
    namespaces_checked = [canonical_prefix, *alias_prefixes]
    result: dict[str, Any] = {
        "provider": provider,
        "canonical_prefix": canonical_prefix,
        "alias_prefixes": alias_prefixes,
        "namespaces_checked": [item for item in namespaces_checked if item],
        "source": "",
        "source_prefix": "",
        "namespace_mismatch": False,
    }
    for field in ("enabled", "submit_url", "poll_url", "auth_header_name", "auth_header_value", "model", "capabilities"):
        env_name, value = _first_env_name_value(data, *(spec.get(field) or []))
        result[field] = value
        result[f"{field}_env"] = env_name
        if value and not result["source"]:
            result["source"] = f"worker_env:{env_name.rsplit('_', 1)[0] if '_' in env_name else env_name}"
            for prefix in namespaces_checked:
                if env_name.startswith(prefix):
                    result["source_prefix"] = prefix
                    break
    result["source"] = result["source"] or f"worker_env:{canonical_prefix}" if canonical_prefix else "worker_env"
    result["namespace_mismatch"] = bool(
        result.get("submit_url")
        and result.get("auth_header_value")
        and result.get("submit_url_env")
        and result.get("auth_header_value_env")
        and str(result["submit_url_env"]).split("_", 2)[:2] != str(result["auth_header_value_env"]).split("_", 2)[:2]
    )
    return result


def _provider_namespace_metadata(provider: str, cfg: dict[str, Any]) -> dict[str, str]:
    namespaces_checked = ",".join(str(item) for item in (cfg.get("namespaces_checked") or []) if str(item))
    alias_prefixes = ",".join(str(item) for item in (cfg.get("alias_prefixes") or []) if str(item))
    return {
        "_VIDEO_PROVIDER_NAMESPACES_CHECKED": namespaces_checked,
        "_VIDEO_PROVIDER_ENV_PREFIX": str(cfg.get("canonical_prefix") or ""),
        "_VIDEO_PROVIDER_ALIAS_PREFIXES_CHECKED": alias_prefixes,
        "_VIDEO_PROVIDER_CONFIG_SOURCE": str(cfg.get("source") or f"worker_env:{provider}"),
        "_VIDEO_PROVIDER_NAMESPACE_MISMATCH": "1" if cfg.get("namespace_mismatch") else "0",
    }


def _runtime_env_name(env: dict[str, str]) -> str:
    return str(
        env.get("APP_ENV")
        or env.get("ENVIRONMENT")
        or env.get("RAILWAY_ENVIRONMENT")
        or env.get("TOAN_AAS_ENV")
        or env.get("PYTHON_ENV")
        or ""
    ).strip().lower()


def _stub_env_allowed(env: dict[str, str]) -> bool:
    runtime = _runtime_env_name(env)
    if runtime in {"development", "dev", "test", "testing", "admin", "local"}:
        return True
    return bool(env.get("PYTEST_CURRENT_TEST")) and runtime not in {"production", "prod"}


class StubVideoProvider:
    provider_name = VIDEO_STUB_PROVIDER_NAME

    def __init__(self, environ: dict[str, str] | None = None):
        self.env = environ or os.environ

    def _enabled(self) -> bool:
        return _env_flag(dict(self.env), "VIDEO_STUB_PROVIDER_ENABLED", "0")

    def _configured(self) -> bool:
        return bool(self._enabled() and _stub_env_allowed(dict(self.env)))

    def capabilities(self) -> dict[str, Any]:
        enabled = self._enabled()
        allowed = _stub_env_allowed(dict(self.env))
        missing: list[str] = []
        if not enabled:
            missing.append("VIDEO_STUB_PROVIDER_ENABLED")
        if enabled and not allowed:
            missing.append("non_production_env")
        return {
            "provider": self.provider_name,
            "enabled": enabled,
            "configured": bool(enabled and allowed),
            "missing": missing,
            "capabilities": ["text_to_video", "image_to_video", "video_to_video", "multi_scene_video", "scene_video"],
            "endpoint_configured": False,
            "submit_url_present": False,
            "poll_url_present": False,
            "endpoint_present": False,
            "auth_configured": False,
            "auth_present": False,
            "model_configured": False,
            "model_present": False,
            "stub_test_only": True,
            "production_disabled": enabled and not allowed,
        }

    def submit_video_job(self, request: VideoGenerationRequest):
        from services.video_provider_base import VideoSubmitResult

        if not self._configured():
            return VideoSubmitResult(ok=False, provider_name=self.provider_name, error_code="stub_provider_disabled")
        task_seed = f"{request.job_id}:{request.prompt}:{time.time()}"
        task_id = "stub-" + hashlib.sha1(task_seed.encode("utf-8", errors="ignore")).hexdigest()[:12]
        return VideoSubmitResult(ok=True, provider_name=self.provider_name, provider_task_id=task_id, provider_status="succeeded")

    def poll_video_job(self, provider_task_id: str):
        return VideoPollResult(ok=True, status="succeeded", provider_name=self.provider_name, provider_task_id=provider_task_id)

    def materialize_result(self, poll_result: VideoPollResult, output_name: str) -> VideoArtifactResult:
        output_dir = os.path.abspath(os.getenv("VIDEO_STUB_PROVIDER_OUTPUT_DIR") or tempfile.gettempdir())
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{output_name or poll_result.provider_task_id or 'stub_video'}.mp4")
        ffmpeg = shutil.which("ffmpeg") or str(os.getenv("FFMPEG_PATH") or "").strip()
        if not ffmpeg:
            return VideoArtifactResult(ok=False, provider_name=self.provider_name, local_path=output_path, error_code="ffmpeg_missing")
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x568:d=1",
            "-vf",
            "format=yuv420p",
            "-movflags",
            "+faststart",
            output_path,
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        except Exception:
            return VideoArtifactResult(ok=False, provider_name=self.provider_name, local_path=output_path, error_code="stub_render_failed")
        size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        return VideoArtifactResult(
            ok=bool(size > 0),
            provider_name=self.provider_name,
            local_path=output_path,
            bytes=size,
            duration=1.0,
            has_video_stream=True,
            has_audio_stream=False,
            error_code="" if size > 0 else "stub_output_empty",
        )


def _generic_adapter_for(name: str, env: dict[str, str]) -> VideoProviderAdapter:
    if name == "toanaas_video":
        derived = _with_derived(
            env,
            {
                "VIDEO_TOANAAS_AUTH_HEADER_NAME": env.get("VIDEO_TOANAAS_AUTH_HEADER_NAME") or "Authorization",
                "VIDEO_TOANAAS_AUTH_HEADER_VALUE": env.get("VIDEO_TOANAAS_AUTH_HEADER_VALUE") or _bearer(env.get("VIDEO_TOANAAS_API_KEY") or ""),
            },
        )
        return GenericHttpVideoProvider(
            provider_name="toanaas_video",
            enabled_env="VIDEO_TOANAAS_ENABLED",
            submit_url_env="VIDEO_TOANAAS_SUBMIT_URL",
            poll_url_env="VIDEO_TOANAAS_POLL_URL",
            auth_header_name_env="VIDEO_TOANAAS_AUTH_HEADER_NAME",
            auth_header_value_env="VIDEO_TOANAAS_AUTH_HEADER_VALUE",
            result_field_env="VIDEO_TOANAAS_RESULT_FIELD",
            model_env="VIDEO_TOANAAS_MODEL",
            capabilities_env="VIDEO_TOANAAS_CAPABILITIES",
            environ=derived,
        )
    if name == "shopaikey_video":
        namespace_cfg = video_provider_namespace_config("shopaikey_video", env)
        submit_url = _endpoint_alias(
            env,
            "SHOPAIKEY_VIDEO_SUBMIT_URL",
            "SHOPAIKEY_BASE_URL",
            "SHOPAIKEY_VIDEO_ENDPOINT",
            "VIDEO_SHOPAIKEY_SUBMIT_URL",
            "SHOPAIKEY_VIDEO_URL",
        )
        submit_url = submit_url or str(namespace_cfg.get("submit_url") or "")
        poll_url = _endpoint_alias(
            env,
            "SHOPAIKEY_VIDEO_POLL_URL",
            "SHOPAIKEY_BASE_URL",
            "SHOPAIKEY_VIDEO_POLL_ENDPOINT",
            "VIDEO_SHOPAIKEY_POLL_URL",
            "SHOPAIKEY_VIDEO_STATUS_ENDPOINT",
        )
        poll_url = poll_url or str(namespace_cfg.get("poll_url") or "")
        if not poll_url and submit_url:
            poll_url = submit_url.rstrip("/")
        generic_ready = bool(
            submit_url
            and poll_url
            and (namespace_cfg.get("auth_header_value") or env.get("SHOPAIKEY_API_KEY"))
            and (namespace_cfg.get("model") or env.get("SHOPAIKEY_VIDEO_MODEL_PRIMARY") or env.get("SHOPAIKEY_VIDEO_MODEL"))
        )
        derived = _with_derived(
            env,
            {
                **_provider_namespace_metadata("shopaikey_video", namespace_cfg),
                "SHOPAIKEY_VIDEO_ENABLED": str(env.get("SHOPAIKEY_VIDEO_ENABLED") or namespace_cfg.get("enabled") or ("1" if generic_ready else "")),
                "SHOPAIKEY_VIDEO_SUBMIT_URL": submit_url,
                "SHOPAIKEY_VIDEO_POLL_URL": poll_url,
                "SHOPAIKEY_VIDEO_AUTH_HEADER_NAME": env.get("SHOPAIKEY_VIDEO_AUTH_HEADER_NAME") or namespace_cfg.get("auth_header_name") or "Authorization",
                "SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE": env.get("SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE") or namespace_cfg.get("auth_header_value") or _bearer(env.get("SHOPAIKEY_API_KEY") or ""),
                "SHOPAIKEY_VIDEO_MODEL": env.get("SHOPAIKEY_VIDEO_MODEL") or namespace_cfg.get("model") or "",
                "SHOPAIKEY_VIDEO_CAPABILITIES": env.get("SHOPAIKEY_VIDEO_CAPABILITIES") or namespace_cfg.get("capabilities") or "",
            },
        )
        return GenericHttpVideoProvider(
            provider_name="shopaikey_video",
            enabled_env="SHOPAIKEY_VIDEO_ENABLED",
            submit_url_env="SHOPAIKEY_VIDEO_SUBMIT_URL",
            poll_url_env="SHOPAIKEY_VIDEO_POLL_URL",
            auth_header_name_env="SHOPAIKEY_VIDEO_AUTH_HEADER_NAME",
            auth_header_value_env="SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE",
            result_field_env="SHOPAIKEY_VIDEO_RESULT_FIELD",
            model_env="SHOPAIKEY_VIDEO_MODEL",
            capabilities_env="SHOPAIKEY_VIDEO_CAPABILITIES",
            environ=derived,
        )
    if name == "key4u_video":
        namespace_cfg = video_provider_namespace_config("key4u_video", env)
        submit_url = _endpoint_alias(env, "KEY4U_VIDEO_SUBMIT_URL", "KEY4U_BASE_URL", "KEY4U_VIDEO_ENDPOINT", "VIDEO_KEY4U_SUBMIT_URL")
        submit_url = submit_url or str(namespace_cfg.get("submit_url") or "")
        poll_url = _endpoint_alias(env, "KEY4U_VIDEO_POLL_URL", "KEY4U_BASE_URL", "KEY4U_VIDEO_POLL_ENDPOINT", "VIDEO_KEY4U_POLL_URL")
        poll_url = poll_url or str(namespace_cfg.get("poll_url") or "")
        derived = _with_derived(
            env,
            {
                **_provider_namespace_metadata("key4u_video", namespace_cfg),
                "KEY4U_VIDEO_ENABLED": str(env.get("KEY4U_VIDEO_ENABLED") or namespace_cfg.get("enabled") or ""),
                "KEY4U_VIDEO_SUBMIT_URL": submit_url,
                "KEY4U_VIDEO_POLL_URL": poll_url,
                "KEY4U_VIDEO_AUTH_HEADER_NAME": env.get("KEY4U_VIDEO_AUTH_HEADER_NAME") or namespace_cfg.get("auth_header_name") or "Authorization",
                "KEY4U_VIDEO_AUTH_HEADER_VALUE": env.get("KEY4U_VIDEO_AUTH_HEADER_VALUE") or namespace_cfg.get("auth_header_value") or _bearer(env.get("KEY4U_API_KEY") or env.get("KEY4U_TOKEN") or ""),
                "KEY4U_VIDEO_MODEL": env.get("KEY4U_VIDEO_MODEL") or namespace_cfg.get("model") or "",
                "KEY4U_VIDEO_CAPABILITIES": env.get("KEY4U_VIDEO_CAPABILITIES") or namespace_cfg.get("capabilities") or "",
            },
        )
        return GenericHttpVideoProvider(
            provider_name="key4u_video",
            enabled_env="KEY4U_VIDEO_ENABLED",
            submit_url_env="KEY4U_VIDEO_SUBMIT_URL",
            poll_url_env="KEY4U_VIDEO_POLL_URL",
            auth_header_name_env="KEY4U_VIDEO_AUTH_HEADER_NAME",
            auth_header_value_env="KEY4U_VIDEO_AUTH_HEADER_VALUE",
            result_field_env="KEY4U_VIDEO_RESULT_FIELD",
            model_env="KEY4U_VIDEO_MODEL",
            capabilities_env="KEY4U_VIDEO_CAPABILITIES",
            environ=derived,
        )
    if name == "veo":
        return VeoVideoProvider(environ=env)
    if name == "kling":
        return KlingVideoProvider(environ=env)
    if name == "generic_http":
        return GenericHttpVideoProvider(environ=env)
    if name == VIDEO_STUB_PROVIDER_NAME:
        return StubVideoProvider(environ=env)
    return DisabledVideoProvider(name, missing=["unknown_provider"])


def configured_provider_chain(environ: dict[str, str] | None = None) -> list[str]:
    env = environ or os.environ
    return split_provider_chain(env.get("VIDEO_PROVIDER_CHAIN") or DEFAULT_VIDEO_PROVIDER_CHAIN)


def load_video_provider_adapters(environ: dict[str, str] | None = None) -> list[VideoProviderAdapter]:
    env = dict(environ or os.environ)
    adapters: list[VideoProviderAdapter] = []
    for name in configured_provider_chain(env):
        adapters.append(_generic_adapter_for(name, env))
    return adapters


def normalize_capability_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_values = value.replace("|", ",").replace(";", ",").split(",")
    else:
        try:
            raw_values = list(value)
        except TypeError:
            raw_values = [value]
    result: list[str] = []
    aliases = {
        "text_to_video_or_scene_engine": "text_to_video_or_scene_video",
        "text_to_video_or_scene": "text_to_video_or_scene_video",
        "scene_engine": "scene_video",
        "multiscene_video": "multi_scene_video",
        "multi_scene": "multi_scene_video",
    }
    for item in raw_values:
        token = str(item or "").strip().lower().replace("-", "_")
        token = aliases.get(token, token)
        if token and token not in result:
            result.append(token)
    return result


def capability_options(required_capability: str) -> list[str]:
    cap = (normalize_capability_values([required_capability]) or ["text_to_video"])[0]
    mapping = {
        "text_to_video_or_scene_video": ["multi_scene_video", "scene_video", "text_to_video"],
        "text_to_video_or_scene_engine": ["multi_scene_video", "scene_video", "text_to_video"],
        "multi_scene_video": ["multi_scene_video", "scene_video", "text_to_video"],
        "scene_video": ["scene_video", "multi_scene_video", "text_to_video"],
        "delegates_to_selected_product": ["multi_scene_video", "scene_video", "text_to_video", "image_to_video", "video_to_video"],
    }
    return mapping.get(cap, [cap] if cap else ["text_to_video"])


def provider_supports(adapter: VideoProviderAdapter, required_capability: str) -> bool:
    caps = adapter.capabilities()
    if not caps.get("configured"):
        return False
    supported = set(normalize_capability_values(caps.get("capabilities") or []))
    return any(cap in supported for cap in capability_options(required_capability))


def preferred_provider_capability(adapter: VideoProviderAdapter, required_capability: str) -> str:
    caps = adapter.capabilities()
    supported = set(normalize_capability_values(caps.get("capabilities") or []))
    for cap in capability_options(required_capability):
        if cap in supported:
            return cap
    return (capability_options(required_capability) or ["text_to_video"])[0]


def provider_status_payload(environ: dict[str, str] | None = None) -> dict[str, Any]:
    env = dict(environ or os.environ)
    adapters = load_video_provider_adapters(env)
    if VIDEO_STUB_PROVIDER_NAME not in [adapter.provider_name for adapter in adapters]:
        adapters.append(StubVideoProvider(environ=env))
    providers = []
    for adapter in adapters:
        caps = dict(adapter.capabilities())
        missing = list(caps.get("missing") or [])
        invalid_fields = list(caps.get("invalid_fields") or [])
        invalid_env = list(caps.get("invalid_env") or [])
        config_blocker = str(caps.get("config_blocker") or caps.get("blocker") or "")
        provider_name = str(caps.get("provider") or adapter.provider_name or "").strip()
        credit_status = provider_credit_status(provider_name, env)
        credit_ok = provider_credit_allows_selection(credit_status)
        configured = bool(caps.get("configured"))
        selection_blocker = ""
        if configured and not credit_ok:
            selection_blocker = f"credit_{credit_status}"
        elif not configured:
            selection_blocker = config_blocker or "not_configured"
        providers.append(
            {
                "provider": provider_name,
                "enabled": bool(caps.get("enabled")),
                "configured": configured,
                "missing": missing,
                "invalid_fields": invalid_fields,
                "invalid_env": invalid_env,
                "blocker": config_blocker,
                "config_blocker": config_blocker,
                "capabilities": normalize_capability_values(caps.get("capabilities") or []),
                "endpoint_configured": bool(caps.get("endpoint_configured")),
                "endpoint_present": bool(caps.get("endpoint_present") or caps.get("endpoint_configured")),
                "submit_url_present": bool(caps.get("submit_url_present") or caps.get("endpoint_configured")),
                "poll_url_present": bool(caps.get("poll_url_present") or caps.get("endpoint_configured")),
                "submit_url_configured": bool(caps.get("submit_url_configured")),
                "poll_url_configured": bool(caps.get("poll_url_configured")),
                "model_configured": bool(caps.get("model_configured")),
                "model_present": bool(caps.get("model_present") or caps.get("model_configured")),
                "auth_configured": bool(caps.get("auth_configured")),
                "auth_present": bool(caps.get("auth_present") or caps.get("auth_configured")),
                "provider_config_namespaces_checked": list(caps.get("provider_config_namespaces_checked") or []),
                "selected_provider_env_prefix": str(caps.get("selected_provider_env_prefix") or ""),
                "selected_provider_alias_prefixes_checked": list(caps.get("selected_provider_alias_prefixes_checked") or []),
                "selected_provider_config_source": str(caps.get("selected_provider_config_source") or caps.get("provider_config_source") or ""),
                "provider_config_source": str(caps.get("provider_config_source") or ""),
                "provider_submit_url_host": str(caps.get("provider_submit_url_host") or ""),
                "provider_submit_url_path": str(caps.get("provider_submit_url_path") or ""),
                "provider_env_namespace_mismatch": bool(caps.get("provider_env_namespace_mismatch")),
                "provider_model_present": bool(caps.get("provider_model_present") or caps.get("model_present")),
                "provider_payload_model": str(caps.get("provider_payload_model") or ""),
                "stub_test_only": bool(caps.get("stub_test_only")),
                "production_disabled": bool(caps.get("production_disabled")),
                "credit_status": credit_status,
                "credit_ok": bool(credit_ok),
                "fallback_only": bool(provider_name == "key4u_video" or not credit_ok),
                "selection_blocker": selection_blocker,
            }
        )
    ready = [item["provider"] for item in providers if item["configured"] and item.get("credit_ok")]
    enabled = [item["provider"] for item in providers if item["enabled"]]
    configured = [item["provider"] for item in providers if item["configured"]]
    near_ready = [
        item["provider"]
        for item in providers
        if not item["configured"] and (item["endpoint_present"] or item["auth_present"] or item["enabled"])
    ]
    missing_env = {item["provider"]: item["missing"] for item in providers if item["missing"]}
    invalid_env = {item["provider"]: item["invalid_env"] for item in providers if item.get("invalid_env")}
    invalid_config = [item["provider"] for item in providers if item.get("config_blocker")]
    selected_provider = ready[0] if ready else ""
    fallback_order = [item["provider"] for item in providers if item["configured"] and item["provider"] != selected_provider]
    usable_fallback_order = [
        item["provider"]
        for item in providers
        if item["configured"] and item.get("credit_ok") and item["provider"] != selected_provider
    ]
    skipped_providers = [
        {"provider": item["provider"], "reason": item.get("selection_blocker") or f"credit_{item.get('credit_status')}"}
        for item in providers
        if (item["configured"] and not item.get("credit_ok")) or (not item["configured"] and item.get("selection_blocker") != "not_configured")
    ]
    if ready:
        reason = "provider_ready_and_has_credit"
    elif not enabled:
        reason = "chưa bật provider nào"
    elif invalid_config:
        reason = "provider_config_placeholder_or_invalid_url"
    elif not configured:
        reason = "provider chưa đủ endpoint/auth"
    elif skipped_providers:
        reason = "provider_credit_unavailable"
    else:
        reason = "provider thiếu capability"
    return {
        "ok": bool(ready),
        "ready": bool(ready),
        "reason": reason,
        "summary_reason": reason,
        "provider_chain": configured_provider_chain(env),
        "effective_provider_chain": configured_provider_chain(env),
        "ready_provider_order": ready,
        "first_ready_provider": selected_provider,
        "selected_provider": selected_provider,
        "selection_reason": reason,
        "fallback_order": fallback_order,
        "usable_fallback_order": usable_fallback_order,
        "skipped_providers": skipped_providers,
        "enabled_count": len(enabled),
        "configured_count": len(configured),
        "enabled_providers": enabled,
        "configured_providers": configured,
        "near_ready_providers": near_ready,
        "missing_env": missing_env,
        "invalid_env": invalid_env,
        "invalid_config_providers": invalid_config,
        "providers": providers,
        "public_no_provider_copy": PUBLIC_NO_VIDEO_PROVIDER_COPY,
    }


def provider_candidate_adapters(
    required_capability: str,
    environ: dict[str, str] | None = None,
    status: dict[str, Any] | None = None,
) -> list[VideoProviderAdapter]:
    env = dict(environ or os.environ)
    payload = dict(status or provider_status_payload(env))
    status_by_provider = {str(item.get("provider") or ""): item for item in (payload.get("providers") or []) if isinstance(item, dict)}
    candidates: list[VideoProviderAdapter] = []
    for adapter in load_video_provider_adapters(env):
        item = status_by_provider.get(adapter.provider_name, {})
        if item and not item.get("credit_ok", True):
            continue
        if provider_supports(adapter, required_capability):
            candidates.append(adapter)
    return candidates


def select_video_provider(required_capability: str, environ: dict[str, str] | None = None) -> tuple[VideoProviderAdapter | None, dict[str, Any]]:
    status = provider_status_payload(environ)
    for adapter in provider_candidate_adapters(required_capability, environ, status):
        return adapter, status
    return None, status


def video_provider_env_audit_payload(environ: dict[str, str] | None = None) -> dict[str, Any]:
    env = dict(environ or os.environ)
    status = provider_status_payload(env)
    provider_items = {str(item.get("provider") or ""): item for item in (status.get("providers") or []) if isinstance(item, dict)}
    rows: list[dict[str, Any]] = []
    ok = True
    for provider in ("shopaikey_video", "key4u_video"):
        adapter = _generic_adapter_for(provider, env)
        caps = dict(adapter.capabilities())
        item = dict(provider_items.get(provider) or {})
        submit_path = str(caps.get("provider_submit_url_path") or "")
        ready = bool(item.get("configured"))
        submit_non_empty = bool(caps.get("submit_url_configured") and caps.get("auth_configured") and (caps.get("model_present") or caps.get("provider_payload_model")))
        row = {
            "provider": provider,
            "status_configured": ready,
            "submit_config_non_empty": submit_non_empty,
            "status_submit_registry_aligned": bool((not ready) or submit_non_empty),
            "namespaces_checked": list(caps.get("provider_config_namespaces_checked") or []),
            "canonical_prefix": str(caps.get("selected_provider_env_prefix") or ""),
            "alias_prefixes_checked": list(caps.get("selected_provider_alias_prefixes_checked") or []),
            "config_source": str(caps.get("selected_provider_config_source") or caps.get("provider_config_source") or ""),
            "submit_url_configured": bool(caps.get("submit_url_configured")),
            "submit_url_host": str(caps.get("provider_submit_url_host") or ""),
            "submit_url_path": submit_path,
            "auth_header_name_present": bool(caps.get("provider_auth_header_name")),
            "auth_header_value_present": bool(caps.get("provider_auth_value_present")),
            "model_present": bool(caps.get("model_present") or caps.get("provider_payload_model")),
            "no_v1_v1": "/v1/v1" not in submit_path.lower(),
            "provider_env_namespace_mismatch": bool(caps.get("provider_env_namespace_mismatch")),
        }
        if not row["status_submit_registry_aligned"] or not row["no_v1_v1"]:
            ok = False
        rows.append(row)
    selected = str(status.get("first_ready_provider") or status.get("selected_provider") or "")
    selected_row = next((row for row in rows if row["provider"] == selected), {})
    selected_submit_ready = bool(selected_row.get("submit_config_non_empty")) if selected else False
    return {
        "ok": bool(ok and ((not selected) or selected_submit_ready)),
        "status_ready": bool(status.get("ready") or status.get("ok")),
        "selected_provider": selected,
        "selected_provider_submit_config_non_empty": selected_submit_ready,
        "status_ready_implies_submit_config_non_empty": bool((not (status.get("ready") or status.get("ok"))) or selected_submit_ready),
        "provider_chain": list(status.get("effective_provider_chain") or status.get("provider_chain") or []),
        "rows": rows,
        "worker_local_hydration_attempted": True,
        "worker_local_hydration_success": selected_submit_ready,
        "fallback_provider_attempted_if_selected_empty": bool(selected and not selected_submit_ready and any(row.get("submit_config_non_empty") for row in rows if row.get("provider") != selected)),
    }


def _safe_exception_message(value: Any, limit: int = 220) -> str:
    text = str(value or "").replace("\n", " ").replace("\r", " ")
    for marker in ("Bearer ", "token=", "key=", "secret=", "authorization="):
        idx = text.lower().find(marker.lower())
        if idx >= 0:
            text = text[: idx + len(marker)] + "***"
            break
    return text[:limit]


def _debug_http_status(raw: dict[str, Any] | None = None, key: str = "http_status") -> int:
    raw = dict(raw or {})
    for candidate in (key, "http_status", "status_code", "submit_http_status", "poll_http_status"):
        try:
            value = int(raw.get(candidate) or 0)
        except Exception:
            value = 0
        if value:
            return value
    return 0


def provider_exception_result(exc: BaseException, *, provider: str = "", stage: str = "submit_request", status: dict[str, Any] | None = None) -> dict[str, Any]:
    blocker = str(getattr(exc, "blocker", "") or "")
    if not blocker:
        if isinstance(exc, ValueError):
            blocker = "provider_unhandled_exception"
        elif isinstance(exc, (KeyError, TypeError)):
            blocker = "provider_submit_response_invalid_shape"
        elif isinstance(exc, TimeoutError):
            blocker = "provider_submit_http_error"
        else:
            blocker = "provider_unhandled_exception"
    debug = dict(getattr(exc, "debug", {}) or {})
    return {
        "ok": False,
        **debug,
        "provider_router_called": True,
        "provider_attempted": stage != "payload_build",
        "provider_submit_called": stage == "submit_request",
        "provider": provider,
        "selected_provider": provider,
        "provider_error": blocker,
        "blocker": blocker,
        "provider_status": "failed",
        "smoke_stage": str(getattr(exc, "stage", "") or debug.get("smoke_stage") or stage),
        "exception_class": type(exc).__name__,
        "exception_message_safe": _safe_exception_message(exc),
        "provider_submit_exception_class": type(exc).__name__ if stage == "submit_request" else "",
        "provider_submit_exception_message_safe": _safe_exception_message(exc) if stage == "submit_request" else "",
        "provider_readiness": status or {},
    }


def _merge_contract_debug(target: dict[str, Any], raw: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = dict(raw or {})
    for key in (
        "smoke_stage",
        "exception_class",
        "exception_message_safe",
        "submit_url_configured",
        "poll_url_configured",
        "auth_configured",
        "payload_has_prompt",
        "payload_has_duration",
        "payload_has_ratio",
        "payload_keys",
        "prompt_chars",
        "duration",
        "ratio",
        "quality",
        "scenes_count",
        "submit_response_shape",
        "provider_task_id_present",
        "provider_task_id_masked",
        "poll_response_shape",
        "provider_status_raw",
        "result_field_path",
        "task_id_field_path",
        "video_id_field_path",
        "provider_submit_url_configured",
        "provider_submit_url_host",
        "provider_auth_header_name",
        "provider_auth_value_present",
        "provider_auth_scheme_prefix",
        "provider_payload_keys",
        "provider_payload_model",
        "provider_response_http_status",
        "provider_response_body_shape",
        "provider_submit_exception_class",
        "provider_submit_exception_message_safe",
        "provider_config_source",
        "provider_config_namespaces_checked",
        "selected_provider_env_prefix",
        "selected_provider_alias_prefixes_checked",
        "selected_provider_config_source",
        "provider_env_namespace_mismatch",
        "provider_submit_url_path",
        "selected_provider_before_submit",
        "submit_provider_key",
        "auth_present",
        "auth_scheme",
        "provider_model_present",
        "claim_payload_provider_key",
        "claim_payload_has_provider_config",
        "worker_local_hydration_attempted",
        "worker_local_hydration_success",
        "submit_url_present",
        "auth_header_name_present",
        "auth_header_value_present",
        "model_present",
        "provider_chain_fallback_attempted",
        "fallback_provider_attempts",
        "configured_provider_chain",
        "initial_selected_provider",
        "selected_provider_after_fallback",
        "provider_selection_reason",
        "provider_fallback_attempted",
        "provider_fallback_attempts",
        "provider_fallback_reason",
        "skipped_provider_reasons",
        "fallback_only_respected",
        "submit_accepted",
        "poll_allowed",
        "poll_skipped_reason",
        "provider_submit_http_5xx",
        "provider_submit_retriable",
        "provider_error_message_safe",
        "provider_progress_raw",
        "provider_progress_raw_number",
        "provider_progress_source",
        "http_200_not_used_as_progress",
        "result_url_primary_path_checked",
        "result_url_found",
        "result_url_source_path",
        "shopaikey_status_endpoint_exact",
        "shopaikey_status_http_code",
        "shopaikey_raw_status",
        "shopaikey_normalized_status",
        "shopaikey_data_progress_raw",
        "shopaikey_progress_source",
        "shopaikey_result_url_from_data",
        "shopaikey_data_result_url_present",
        "shopaikey_fail_reason",
    ):
        if key in raw and key not in target:
            target[key] = raw.get(key)
    if raw.get("exception_class") and not target.get("provider_submit_exception_class"):
        target["provider_submit_exception_class"] = raw.get("exception_class")
    if raw.get("exception_message_safe") and not target.get("provider_submit_exception_message_safe"):
        target["provider_submit_exception_message_safe"] = raw.get("exception_message_safe")
    if "provider_submit_blocker" in raw:
        target["provider_submit_stage"] = raw.get("smoke_stage") or "submit_response_parse"
        target["provider_submit_blocker"] = raw.get("provider_submit_blocker")
    if "provider_poll_blocker" in raw:
        target["provider_poll_blocker"] = raw.get("provider_poll_blocker")
    if "provider_result_blocker" in raw:
        target["provider_result_blocker"] = raw.get("provider_result_blocker")
    if "submit_http_status" in raw or "http_status" in raw or "status_code" in raw:
        target["provider_submit_http_status"] = _debug_http_status(raw, "submit_http_status")
    if "poll_http_status" in raw:
        target["provider_poll_http_status"] = _debug_http_status(raw, "poll_http_status")
    if raw.get("result_url_present") is not None:
        target["provider_result_url_present"] = bool(raw.get("result_url_present"))
    return target


def _config_validation_blocker_from_status(status: dict[str, Any], required_capability: str) -> dict[str, Any]:
    for item in status.get("providers") or []:
        if not isinstance(item, dict):
            continue
        if not item.get("config_blocker") and not item.get("blocker"):
            continue
        supported = set(normalize_capability_values(item.get("capabilities") or []))
        if not any(cap in supported for cap in capability_options(required_capability)):
            continue
        invalid_fields = [str(field) for field in (item.get("invalid_fields") or [])]
        if "submit_url" in invalid_fields:
            blocker = "provider_config_invalid_submit_url"
        elif "poll_url" in invalid_fields:
            blocker = "provider_config_invalid_poll_url"
        elif "auth" in invalid_fields:
            blocker = "provider_config_invalid_auth"
        else:
            blocker = str(item.get("config_blocker") or item.get("blocker") or "provider_config_placeholder_or_invalid_url")
        return {
            "provider": str(item.get("provider") or ""),
            "blocker": blocker,
            "invalid_fields": invalid_fields,
            "invalid_env": [str(env_name) for env_name in (item.get("invalid_env") or [])],
        }
    return {}


def _missing_submit_config_blocker_from_status(status: dict[str, Any], required_capability: str) -> dict[str, Any]:
    providers: list[str] = []
    missing_env: dict[str, list[str]] = {}
    for item in status.get("providers") or []:
        if not isinstance(item, dict):
            continue
        if not item.get("enabled"):
            continue
        if item.get("configured"):
            continue
        supported = set(normalize_capability_values(item.get("capabilities") or []))
        if not any(cap in supported for cap in capability_options(required_capability)):
            continue
        provider = str(item.get("provider") or "")
        if not provider:
            continue
        providers.append(provider)
        missing_env[provider] = [str(env_name) for env_name in (item.get("missing") or [])]
    if not providers:
        return {}
    return {
        "provider": providers[0],
        "providers": providers,
        "blocker": "all_video_providers_submit_config_missing",
        "missing_env": missing_env,
    }


def run_provider_generation(
    request: VideoGenerationRequest,
    *,
    output_dir: str,
    environ: dict[str, str] | None = None,
    sleep_func=time.sleep,
) -> dict[str, Any]:
    env = dict(environ or os.environ)
    status = provider_status_payload(env)
    required_capability_original = str(request.required_capability or "").strip()
    normalized_capability_candidates = capability_options(required_capability_original)
    candidate_adapters = provider_candidate_adapters(request.required_capability, env, status)
    adapter = candidate_adapters[0] if candidate_adapters else None
    provider_candidates = [item.provider_name for item in candidate_adapters]
    initial_primary_provider = adapter.provider_name if adapter else ""
    initial_fallback_provider = next((name for name in provider_candidates if name and name != initial_primary_provider), "")
    configured_chain = list(status.get("configured_providers") or status.get("effective_provider_chain") or status.get("provider_chain") or [])
    skipped_provider_reasons = [
        {
            "provider": str(item.get("provider") or ""),
            "reason": str(item.get("reason") or item.get("selection_blocker") or "-"),
        }
        for item in (status.get("skipped_providers") or [])
        if isinstance(item, dict)
    ]
    configured_status_items = {
        str(item.get("provider") or ""): item
        for item in (status.get("providers") or [])
        if isinstance(item, dict)
    }
    fallback_only_respected = not any(
        str(item.get("provider") or "") == "key4u_video"
        and bool(item.get("fallback_only"))
        and adapter
        and adapter.provider_name == "key4u_video"
        and bool(configured_status_items.get("shopaikey_video", {}).get("configured"))
        and bool(configured_status_items.get("shopaikey_video", {}).get("credit_ok"))
        for item in configured_status_items.values()
    )
    allow_pending_result = bool(
        (request.metadata or {}).get("product_video")
        or (request.metadata or {}).get("allow_provider_pending")
        or (request.metadata or {}).get("interactive_product")
    )
    metadata = dict(request.metadata or {})
    is_product_video = bool(metadata.get("product_video") or metadata.get("interactive_product") or allow_pending_result)
    try:
        current_fallback_count = int(metadata.get("fallback_count") or metadata.get("provider_fallback_count") or 0)
    except Exception:
        current_fallback_count = 0
    if is_product_video and candidate_adapters:
        max_provider_attempts = 1 if current_fallback_count >= 1 else 2
        candidate_adapters = candidate_adapters[:max_provider_attempts]
        adapter = candidate_adapters[0] if candidate_adapters else None
        provider_candidates = [item.provider_name for item in candidate_adapters]
        initial_primary_provider = adapter.provider_name if adapter else ""
        initial_fallback_provider = next((name for name in provider_candidates if name and name != initial_primary_provider), "")
    existing_provider, existing_task_id, existing_video_id = _metadata_existing_provider_task(metadata)
    pending_provider = str(metadata.get("provider_pending_provider") or existing_provider or "").strip()
    pending_task_id = str(metadata.get("provider_pending_task_id") or existing_task_id or "").strip()
    pending_video_id = str(metadata.get("provider_pending_video_id") or existing_video_id or "").strip()
    pending_request_job_id = str(metadata.get("provider_pending_request_job_id") or "").strip()
    pending_attempts = [dict(item) for item in (metadata.get("provider_pending_attempts") or []) if isinstance(item, dict)]
    submit_switch = product_video_submit_switch_detail(env)
    submit_enabled = bool(submit_switch.get("resolved"))
    submit_source_policy = product_video_provider_submit_source_policy(
        metadata,
        public_submit_enabled=submit_enabled,
        poll_existing_task=bool(pending_task_id or pending_video_id),
    )
    fallback_context = product_video_public_confirm_context(metadata)
    cooldown_state = provider_failure_cooldown_state(metadata, env)
    submit_idempotency_key = hashlib.sha256(
        f"{request.job_id}|{request.product_type}|{request.video_flow_type}|{request.required_capability}".encode("utf-8")
    ).hexdigest()[:24]
    base_debug = {
        "provider_router_called": True,
        "provider_request_job_id": str(request.job_id or ""),
        "provider_submit_idempotency_key": submit_idempotency_key,
        "product_video_provider_submit_enabled": bool(submit_enabled),
        "product_video_provider_submit_enabled_raw": str(submit_switch.get("raw") or ""),
        "product_video_provider_submit_enabled_resolved": bool(submit_enabled),
        "product_video_provider_submit_enabled_source": str(submit_switch.get("source") or "default"),
        "submit_source": str(submit_source_policy.get("submit_source") or "-"),
        "current_source": str(fallback_context.get("current_source") or submit_source_policy.get("submit_source") or "-"),
        "original_submit_source": str(fallback_context.get("original_submit_source") or ""),
        "fallback_eligibility_source": str(fallback_context.get("fallback_eligibility_source") or ""),
        "public_user_confirmed": bool(submit_source_policy.get("public_user_confirmed")),
        "invoice_confirmed": bool(fallback_context.get("invoice_confirmed")),
        "provider_submit_accepted_before": bool(fallback_context.get("provider_submit_accepted_before")),
        "provider_submit_allowed": bool(submit_source_policy.get("provider_submit_allowed")),
        "provider_submit_block_reason": str(submit_source_policy.get("provider_submit_block_reason") or ""),
        "poll_existing_task_allowed": bool(submit_source_policy.get("poll_existing_task_allowed")),
        "charge_policy": str(metadata.get("charge_policy") or ("after_valid_mp4_delivery" if is_product_video else "")),
        "kill_switch_checked_before_submit": True,
        "provider_submit_blocked_by_kill_switch": False,
        "external_provider_spend_prevented": False,
        "provider_submit_already_exists": bool(pending_task_id or pending_video_id),
        "no_new_submit": bool(pending_task_id or pending_video_id),
        "poll_existing_task": bool(pending_task_id or pending_video_id),
        "duplicate_paid_submit_prevented": False,
        "duplicate_paid_submit_prevented_count": 0,
        "submit_attempt_count": 0,
        "provider_task_id_saved_before_retry": bool(pending_task_id or pending_video_id),
        "active_provider_task": bool(pending_task_id or pending_video_id),
        "last_provider_submit_timestamp": metadata.get("last_provider_submit_timestamp") or "",
        "paid_submit_allowed": bool(submit_enabled),
        "paid_submit_blocked_reason": "",
        "paid_retry_requires_confirmation": paid_retry_requires_confirmation(env),
        "paid_retry_confirmed": product_video_retry_confirmed(metadata),
        "admin_external_spend_warning": (
            "Creating a Product Video job may spend external provider credits even if no MP4 is produced."
        ),
        **cooldown_state,
        "required_capability_original": required_capability_original,
        "normalized_capability_candidates": list(normalized_capability_candidates),
        "provider_candidates_count": len([item for item in provider_candidates if item]),
        "selected_provider": adapter.provider_name if adapter else "",
        "initial_selected_provider": adapter.provider_name if adapter else "",
        "selected_capability": preferred_provider_capability(adapter, request.required_capability) if adapter else "",
        "provider_selection_blocker": "" if adapter else "provider_capability_missing",
        "provider_selection_reason": str(status.get("selection_reason") or status.get("reason") or ("provider_ready_and_has_credit" if adapter else "provider_capability_missing")),
        "configured_provider_chain": configured_chain,
        "provider_chain": list(status.get("provider_chain") or []),
        "effective_provider_chain": list(status.get("effective_provider_chain") or status.get("provider_chain") or []),
        "fallback_order": list(status.get("fallback_order") or []),
        "usable_fallback_order": list(status.get("usable_fallback_order") or []),
        "fallback_used": False,
        "fallback_reason": "",
        "primary_provider": initial_primary_provider,
        "fallback_provider": initial_fallback_provider,
        "fallback_attempted": False,
        "fallback_count": current_fallback_count,
        "fallback_submit_source": "",
        "fallback_eligible": False,
        "final_decision": "pending_provider_result" if adapter else "provider_unavailable",
        "skipped_providers": list(status.get("skipped_providers") or []),
        "skipped_provider_reasons": skipped_provider_reasons,
        "fallback_only_respected": bool(fallback_only_respected),
        "provider_fallback_attempted": False,
        "provider_fallback_attempts": [],
        "provider_fallback_reason": "",
        "selected_provider_after_fallback": "",
        "provider_submit_called": False,
        "provider_submit_http_status": 0,
        "provider_task_id_saved": False,
        "provider_poll_called": False,
        "provider_result_url_present": False,
    }
    if is_product_video and not submit_source_policy.get("provider_submit_allowed") and not (pending_task_id or pending_video_id):
        policy_reason = str(submit_source_policy.get("provider_submit_block_reason") or "provider_submit_source_blocked")
        legacy_kill_switch_block = policy_reason == "public_provider_submit_disabled"
        return {
            "ok": False,
            **base_debug,
            "provider_attempted": False,
            "provider_submit_called": False,
            "provider_submit_blocked_by_kill_switch": bool(legacy_kill_switch_block),
            "external_provider_spend_prevented": True,
            "paid_submit_allowed": False,
            "paid_submit_blocked_reason": "provider_submit_kill_switch" if legacy_kill_switch_block else policy_reason,
            "provider_error": "provider_submit_kill_switch" if legacy_kill_switch_block else policy_reason,
            "blocker": "provider_submit_kill_switch" if legacy_kill_switch_block else policy_reason,
            "provider_status": "blocked_no_charge",
            "terminal_state": "blocked_no_charge",
            "status": "failed_no_charge",
            "charge": 0,
            "charged_xu": 0,
            "no_charge": True,
            "public_message": PUBLIC_PRODUCT_VIDEO_SUBMIT_BLOCKED_COPY,
            "provider_readiness": status,
        }
    if is_product_video and cooldown_state.get("provider_health_cooldown_active") and not (pending_task_id or pending_video_id):
        return {
            "ok": False,
            **base_debug,
            "provider_attempted": False,
            "provider_submit_called": False,
            "external_provider_spend_prevented": True,
            "paid_submit_allowed": False,
            "paid_submit_blocked_reason": "provider_health_cooldown_active",
            "provider_error": "provider_health_cooldown_active",
            "blocker": "provider_health_cooldown_active",
            "provider_status": "blocked_no_charge",
            "terminal_state": "blocked_no_charge",
            "status": "failed_no_charge",
            "charge": 0,
            "charged_xu": 0,
            "no_charge": True,
            "public_message": PUBLIC_PRODUCT_VIDEO_SUBMIT_BLOCKED_COPY,
            "provider_readiness": status,
        }
    if adapter is None:
        config_blocker = _config_validation_blocker_from_status(status, request.required_capability)
        if config_blocker:
            selected = str(config_blocker.get("provider") or "")
            return {
                "ok": False,
                **base_debug,
                "selected_provider": selected,
                "provider": selected,
                "provider_selection_blocker": str(config_blocker.get("blocker") or "provider_config_placeholder_or_invalid_url"),
                "provider_attempted": False,
                "provider_error": str(config_blocker.get("blocker") or "provider_config_placeholder_or_invalid_url"),
                "blocker": str(config_blocker.get("blocker") or "provider_config_placeholder_or_invalid_url"),
                "provider_status": "config_invalid",
                "smoke_stage": "config_validation",
                "exception_class": "",
                "exception_message_safe": "",
                "submit_url_configured": False,
                "poll_url_configured": False,
                "auth_configured": False,
                "payload_has_prompt": False,
                "payload_has_duration": False,
                "payload_has_ratio": False,
                "invalid_fields": list(config_blocker.get("invalid_fields") or []),
                "invalid_env": list(config_blocker.get("invalid_env") or []),
                "no_charge": True,
                "public_message": PUBLIC_NO_VIDEO_PROVIDER_COPY,
                "provider_readiness": status,
            }
        missing_config = _missing_submit_config_blocker_from_status(status, request.required_capability)
        if missing_config:
            selected = str(missing_config.get("provider") or "")
            return {
                "ok": False,
                **base_debug,
                "selected_provider": selected,
                "provider": selected,
                "provider_selection_blocker": "all_video_providers_submit_config_missing",
                "provider_attempted": False,
                "provider_error": "all_video_providers_submit_config_missing",
                "blocker": "all_video_providers_submit_config_missing",
                "provider_status": "config_missing",
                "smoke_stage": "config_validation",
                "submit_url_configured": False,
                "poll_url_configured": False,
                "auth_configured": False,
                "payload_has_prompt": False,
                "payload_has_duration": False,
                "payload_has_ratio": False,
                "provider_submit_called": False,
                "provider_task_id_saved": False,
                "submit_accepted": False,
                "provider_poll_called": False,
                "poll_allowed": False,
                "poll_skipped_reason": "submit_config_missing",
                "missing_env": dict(missing_config.get("missing_env") or {}),
                "no_charge": True,
                "public_message": PUBLIC_NO_VIDEO_PROVIDER_COPY,
                "provider_readiness": status,
            }
        return {
            "ok": False,
            **base_debug,
            "provider_attempted": False,
            "provider_error": "provider_capability_missing",
            "blocker": "provider_capability_missing",
            "provider_status": "not_attempted",
            "provider_readiness": status,
        }

    def _submit_http_status(raw: dict[str, Any] | None) -> int:
        try:
            return int((raw or {}).get("submit_http_status") or (raw or {}).get("provider_response_http_status") or (raw or {}).get("http_status") or (raw or {}).get("status_code") or 0)
        except Exception:
            return 0

    def _is_submit_5xx(raw: dict[str, Any] | None, blocker: str = "", status_code: int = 0) -> bool:
        raw = dict(raw or {})
        try:
            status_int = int(status_code or raw.get("submit_http_status") or raw.get("provider_response_http_status") or raw.get("http_status") or raw.get("status_code") or 0)
        except Exception:
            status_int = 0
        return bool(raw.get("provider_submit_http_5xx") or blocker in {"provider_temporarily_unavailable", "provider_submit_http_5xx"} or 500 <= status_int <= 599)

    def _final_submit_blocker() -> str:
        if not attempt_failures:
            return "provider_submit_failed"
        reasons = [str(item.get("reason") or "") for item in attempt_failures]
        if len(attempt_failures) > 1 and all(reason == "provider_config_missing_at_submit" for reason in reasons):
            return "all_video_providers_submit_config_missing"
        if all(
            str(item.get("reason") or "") in {
                "provider_capacity_unavailable",
                "provider_submit_failed",
                "provider_submit_http_error",
                "provider_submit_http_5xx",
                "provider_temporarily_unavailable",
                "provider_submit_url_missing",
            }
            for item in attempt_failures
        ):
            if any(str(item.get("reason") or "") == "provider_capacity_unavailable" for item in attempt_failures):
                return "all_video_providers_submit_unavailable"
            return "all_video_providers_submit_failed"
        return reasons[-1] or "provider_submit_failed"

    attempt_failures: list[dict[str, Any]] = []
    attempt_traces: list[dict[str, Any]] = list(pending_attempts[:12])
    first_fallback_reason = ""

    def _new_attempt_trace(provider_name: str, capability: str) -> dict[str, Any]:
        return {
            "provider": provider_name,
            "phase": "selected",
            "capability": capability,
            "submit_called": False,
            "submit_http_status": 0,
            "submit_response_shape": {},
            "submit_accepted": False,
            "task_id_present": False,
            "task_id_source": "",
            "poll_called": False,
            "poll_http_status": 0,
            "poll_raw_status": "",
            "normalized_status": "",
            "continue_polling": False,
            "result_url_present": False,
            "download_called": False,
            "download_http_status": 0,
            "download_content_type": "",
            "downloaded_file_size": 0,
            "validation_passed": False,
            "blocker": "",
            "safe_error": "",
        }

    def _copy_attempt_traces() -> list[dict[str, Any]]:
        return [dict(item) for item in attempt_traces if isinstance(item, dict)]

    for attempt_index, current_adapter in enumerate(candidate_adapters):
        fallback_used = attempt_index > 0
        fallback_reason = first_fallback_reason if fallback_used else ""
        selected_capability = preferred_provider_capability(current_adapter, request.required_capability)
        provider_metadata = dict(request.metadata or {})
        if fallback_used:
            provider_metadata.update(
                {
                    "submit_source": PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_FALLBACK_ONCE,
                    "provider_submit_source": PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_FALLBACK_ONCE,
                    "original_submit_source": str(fallback_context.get("original_submit_source") or ""),
                    "public_confirm_submit_source": str(fallback_context.get("original_submit_source") or ""),
                    "public_user_confirmed": bool(fallback_context.get("public_user_confirmed")),
                    "invoice_confirmed": bool(fallback_context.get("invoice_confirmed")),
                    "provider_submit_accepted_before": True,
                    "fallback_count": current_fallback_count + 1,
                }
            )
        provider_request = dataclasses.replace(request, required_capability=selected_capability, metadata=provider_metadata)
        current_caps = dict(current_adapter.capabilities() or {})
        current_trace = _new_attempt_trace(current_adapter.provider_name, selected_capability)
        attempt_traces.append(current_trace)
        poll_existing_task = bool(
            (pending_task_id or pending_video_id)
            and (not pending_provider or pending_provider == current_adapter.provider_name)
            and (not pending_request_job_id or pending_request_job_id == str(request.job_id or ""))
            and attempt_index == 0
        )
        submit_called_flag = not poll_existing_task

        def _safe_cap_bool(*keys: str) -> bool:
            return any(bool(current_caps.get(key)) for key in keys)

        def _safe_cap_text(*keys: str) -> str:
            for key in keys:
                value = str(current_caps.get(key) or "").strip()
                if value:
                    return value
            return ""

        def _attempt_base() -> dict[str, Any]:
            metadata = dict(provider_request.metadata or request.metadata or {})
            submit_configured = _safe_cap_bool("submit_url_configured", "provider_submit_url_configured")
            auth_value_present = _safe_cap_bool("provider_auth_value_present", "auth_present", "auth_configured")
            model_present = _safe_cap_bool("provider_model_present", "model_present", "model_configured") or bool(_safe_cap_text("provider_payload_model"))
            attempt_submit_source = (
                PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_FALLBACK_ONCE
                if fallback_used
                else str(submit_source_policy.get("submit_source") or "-")
            )
            return {
                **base_debug,
                "selected_provider": current_adapter.provider_name,
                "selected_provider_before_submit": current_adapter.provider_name,
                "submit_provider_key": current_adapter.provider_name,
                "claim_payload_provider_key": str(metadata.get("claim_payload_provider_key") or metadata.get("selected_provider") or ""),
                "claim_payload_has_provider_config": bool(metadata.get("provider_config") or metadata.get("claim_payload_has_provider_config")),
                "worker_local_hydration_attempted": True,
                "worker_local_hydration_success": bool(submit_configured and auth_value_present and model_present),
                "selected_capability": selected_capability,
                "provider": current_adapter.provider_name,
                "provider_selection_blocker": "",
                "provider_config_source": _safe_cap_text("provider_config_source") or f"env:{current_adapter.provider_name}",
                "provider_config_namespaces_checked": list(current_caps.get("provider_config_namespaces_checked") or []),
                "selected_provider_env_prefix": _safe_cap_text("selected_provider_env_prefix"),
                "selected_provider_alias_prefixes_checked": list(current_caps.get("selected_provider_alias_prefixes_checked") or []),
                "selected_provider_config_source": _safe_cap_text("selected_provider_config_source", "provider_config_source") or f"env:{current_adapter.provider_name}",
                "provider_env_namespace_mismatch": bool(current_caps.get("provider_env_namespace_mismatch")),
                "submit_url_configured": submit_configured,
                "submit_url_present": _safe_cap_bool("submit_url_present", "submit_url_configured", "provider_submit_url_configured"),
                "provider_submit_url_configured": _safe_cap_bool("provider_submit_url_configured", "submit_url_configured"),
                "provider_submit_url_host": _safe_cap_text("provider_submit_url_host"),
                "provider_submit_url_path": _safe_cap_text("provider_submit_url_path"),
                "auth_present": auth_value_present,
                "auth_scheme": _safe_cap_text("auth_scheme", "provider_auth_scheme_prefix"),
                "provider_auth_header_name": _safe_cap_text("provider_auth_header_name"),
                "auth_header_name_present": bool(_safe_cap_text("provider_auth_header_name")),
                "auth_header_value_present": auth_value_present,
                "provider_auth_value_present": auth_value_present,
                "provider_auth_scheme_prefix": _safe_cap_text("provider_auth_scheme_prefix", "auth_scheme"),
                "provider_model_present": model_present,
                "model_present": model_present,
                "provider_payload_model": _safe_cap_text("provider_payload_model"),
                "provider_chain_fallback_attempted": bool(fallback_used),
                "fallback_provider_attempts": list(attempt_failures),
                "provider_fallback_attempted": bool(attempt_failures or fallback_used),
                "provider_fallback_attempts": list(attempt_failures),
                "provider_fallback_reason": fallback_reason or first_fallback_reason,
                "selected_provider_after_fallback": current_adapter.provider_name if fallback_used else "",
                "fallback_used": fallback_used,
                "fallback_reason": fallback_reason,
                "primary_provider": initial_primary_provider,
                "fallback_provider": current_adapter.provider_name if fallback_used else initial_fallback_provider,
                "fallback_attempted": bool(fallback_used),
                "fallback_count": current_fallback_count + (1 if fallback_used else 0),
                "fallback_submit_source": PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_FALLBACK_ONCE if fallback_used else "",
                "fallback_eligible": bool(fallback_used or (attempt_index + 1 < len(candidate_adapters))),
                "final_decision": "fallback_provider_once" if fallback_used else "waiting_primary_provider",
                "provider_attempted": True,
                "provider_submit_already_exists": bool(poll_existing_task),
                "no_new_submit": bool(poll_existing_task),
                "poll_existing_task": bool(poll_existing_task),
                "poll_existing_task_allowed": bool(poll_existing_task or submit_source_policy.get("poll_existing_task_allowed")),
                "duplicate_paid_submit_prevented": bool(poll_existing_task),
                "duplicate_paid_submit_prevented_count": 1 if poll_existing_task else 0,
                "provider_task_id_saved_before_retry": bool(pending_task_id or pending_video_id),
                "active_provider_task": bool(poll_existing_task),
                "submit_attempt_count": 0 if poll_existing_task else 1,
                "last_provider_submit_timestamp": (
                    metadata.get("last_provider_submit_timestamp")
                    or ("" if poll_existing_task else str(int(time.time())))
                ),
                "submit_source": attempt_submit_source,
                "current_source": attempt_submit_source if fallback_used else str(fallback_context.get("current_source") or submit_source_policy.get("submit_source") or "-"),
                "original_submit_source": str(fallback_context.get("original_submit_source") or ""),
                "fallback_eligibility_source": str(fallback_context.get("fallback_eligibility_source") or ""),
                "public_user_confirmed": bool(fallback_context.get("public_user_confirmed") or submit_source_policy.get("public_user_confirmed")),
                "invoice_confirmed": bool(fallback_context.get("invoice_confirmed")),
                "provider_submit_accepted_before": bool(fallback_context.get("provider_submit_accepted_before")),
                "provider_submit_allowed": bool(True if fallback_used else submit_source_policy.get("provider_submit_allowed") and not poll_existing_task),
                "provider_submit_block_reason": (
                    ""
                    if fallback_used
                    else (
                    "worker_poll_existing_task_read_only"
                    if poll_existing_task
                    else str(submit_source_policy.get("provider_submit_block_reason") or "")
                    )
                ),
                "charge_policy": str(metadata.get("charge_policy") or ("after_valid_mp4_delivery" if is_product_video else "")),
                "paid_submit_allowed": bool(submit_enabled if fallback_used else submit_enabled and submit_source_policy.get("provider_submit_allowed") and not poll_existing_task),
                "external_provider_spend_prevented": bool(poll_existing_task and not fallback_used),
                "provider_attempts": _copy_attempt_traces(),
            }

        def _record_failure(reason: str, raw: dict[str, Any] | None = None, *, submit_failure: bool = False) -> None:
            nonlocal first_fallback_reason
            clean_reason = str(reason or "provider_failed").strip() or "provider_failed"
            raw = dict(raw or {})
            submit_status = _submit_http_status(raw)
            if current_trace is not None:
                current_trace["blocker"] = clean_reason
                if submit_failure:
                    current_trace["phase"] = "submit"
                elif raw.get("provider_poll_blocker"):
                    current_trace["phase"] = "poll"
                elif raw.get("provider_result_blocker") and current_trace.get("phase") not in {"download", "validate", "final"}:
                    current_trace["phase"] = "result"
                current_trace["safe_error"] = str(raw.get("provider_error_message_safe") or raw.get("exception_message_safe") or "")[:220]
            attempt = {
                "provider": current_adapter.provider_name,
                "reason": clean_reason,
                "submit_failure": bool(submit_failure),
                "submit_http_status": submit_status,
                "retriable": bool(raw.get("provider_submit_retriable") or _is_submit_5xx(raw, clean_reason, submit_status)),
                "submit_5xx": bool(_is_submit_5xx(raw, clean_reason, submit_status)),
            }
            if raw.get("provider_submit_blocker"):
                attempt["submit_blocker"] = str(raw.get("provider_submit_blocker") or "")
            if raw.get("provider_error_message_safe"):
                attempt["provider_error_message_safe"] = str(raw.get("provider_error_message_safe") or "")[:220]
            attempt_failures.append(attempt)
            if not first_fallback_reason:
                first_fallback_reason = clean_reason

        def _mark_trace(phase: str = "", raw: dict[str, Any] | None = None, **updates: Any) -> None:
            if phase:
                current_trace["phase"] = phase
            raw = dict(raw or {})
            if raw:
                if raw.get("submit_response_shape") or raw.get("provider_response_body_shape"):
                    current_trace["submit_response_shape"] = raw.get("submit_response_shape") or raw.get("provider_response_body_shape")
                if raw.get("poll_response_shape"):
                    current_trace["poll_response_shape"] = raw.get("poll_response_shape")
                submit_status = _submit_http_status(raw)
                if submit_status:
                    current_trace["submit_http_status"] = submit_status
                poll_status = _debug_http_status(raw, "poll_http_status")
                if poll_status:
                    current_trace["poll_http_status"] = poll_status
                if raw.get("provider_status_raw") is not None:
                    current_trace["poll_raw_status"] = str(raw.get("provider_status_raw") or "")
                if raw.get("shopaikey_raw_status") is not None:
                    current_trace["poll_raw_status"] = str(raw.get("shopaikey_raw_status") or "")
                if raw.get("provider_status") or raw.get("normalized_provider_status"):
                    current_trace["normalized_status"] = str(raw.get("normalized_provider_status") or raw.get("provider_status") or "")
                if raw.get("shopaikey_normalized_status"):
                    current_trace["normalized_status"] = str(raw.get("shopaikey_normalized_status") or "")
                if raw.get("result_url_present") is not None:
                    current_trace["result_url_present"] = bool(raw.get("result_url_present"))
                for key in (
                    "shopaikey_status_endpoint_exact",
                    "shopaikey_status_http_code",
                    "shopaikey_raw_status",
                    "shopaikey_normalized_status",
                    "shopaikey_data_progress_raw",
                    "shopaikey_progress_source",
                    "shopaikey_result_url_from_data",
                    "shopaikey_data_result_url_present",
                    "provider_progress_raw",
                    "provider_progress_raw_number",
                    "provider_progress_source",
                    "http_200_not_used_as_progress",
                    "result_url_source_path",
                    "result_url_primary_path_checked",
                    "result_url_found",
                    "shopaikey_fail_reason",
                ):
                    if key in raw:
                        current_trace[key] = raw.get(key)
                if raw.get("task_id_field_path") or raw.get("video_id_field_path"):
                    current_trace["task_id_source"] = str(raw.get("task_id_field_path") or raw.get("video_id_field_path") or "")
                if raw.get("provider_task_id_present") is not None:
                    current_trace["task_id_present"] = bool(raw.get("provider_task_id_present"))
                if raw.get("provider_submit_blocker") or raw.get("provider_poll_blocker") or raw.get("provider_result_blocker") or raw.get("blocker"):
                    current_trace["blocker"] = str(raw.get("provider_submit_blocker") or raw.get("provider_poll_blocker") or raw.get("provider_result_blocker") or raw.get("blocker") or "")
                if raw.get("provider_error_message_safe") or raw.get("exception_message_safe"):
                    current_trace["safe_error"] = str(raw.get("provider_error_message_safe") or raw.get("exception_message_safe") or "")[:220]
                if raw.get("download_content_type") is not None:
                    current_trace["download_content_type"] = str(raw.get("download_content_type") or "")
                if raw.get("downloaded_file_size") is not None:
                    try:
                        current_trace["downloaded_file_size"] = int(raw.get("downloaded_file_size") or 0)
                    except Exception:
                        current_trace["downloaded_file_size"] = 0
            for key, value in updates.items():
                current_trace[key] = value

        def _paid_fallback_requires_confirmation_payload(reason: str, raw: dict[str, Any] | None = None) -> dict[str, Any]:
            raw = dict(raw or {})
            blocker = str(reason or "paid_fallback_requires_confirmation").strip() or "paid_fallback_requires_confirmation"
            submit_status = _submit_http_status(raw)
            return {
                "ok": False,
                **_attempt_base(),
                "provider_submit_called": submit_called_flag,
                "provider_submit_http_status": submit_status,
                "provider_submit_http_5xx": _is_submit_5xx(raw, blocker, submit_status),
                "provider_submit_retriable": bool(raw.get("provider_submit_retriable") or _is_submit_5xx(raw, blocker, submit_status)),
                "provider_task_id_saved": False,
                "submit_accepted": False,
                "provider_poll_called": False,
                "provider_fallback_attempted": False,
                "provider_fallback_attempts": list(attempt_failures),
                "fallback_provider_attempts": list(attempt_failures),
                "provider_fallback_reason": "paid_fallback_requires_confirmation",
                "fallback_used": False,
                "fallback_reason": "",
                "fallback_allowed": False,
                "fallback_blocked_reason": "paid_fallback_requires_confirmation",
                "provider_error": blocker,
                "blocker": "paid_fallback_requires_confirmation",
                "provider_status": "failed_no_charge",
                "terminal_state": "failed_no_charge",
                "status": "failed_no_charge",
                "paid_submit_allowed": False,
                "paid_submit_blocked_reason": "paid_fallback_requires_confirmation",
                "paid_retry_requires_confirmation": True,
                "paid_retry_confirmed": False,
                "external_provider_spend_prevented": True,
                "charge": 0,
                "charged_xu": 0,
                "no_charge": True,
                "public_message": PUBLIC_PRODUCT_VIDEO_SUBMIT_BLOCKED_COPY,
                "provider_attempts": _copy_attempt_traces(),
                "provider_readiness": status,
            }

        def _provider_pending_payload(
            submit: VideoSubmitResult,
            poll_result: VideoPollResult,
            *,
            poll_blocker: str = "",
        ) -> dict[str, Any]:
            provider_task_key = str(submit.provider_task_id or submit.provider_video_id or poll_result.provider_task_id or poll_result.provider_video_id or "").strip()
            provider_task_ids = [provider_task_key] if provider_task_key else []
            provider_video_ids = [submit.provider_video_id or poll_result.provider_video_id] if (submit.provider_video_id or poll_result.provider_video_id) else []
            raw_status = str(
                poll_result.raw_status
                or (getattr(poll_result, "raw", {}) or {}).get("provider_status_raw")
                or poll_result.status
                or ""
            ).strip()
            normalized_status = normalize_provider_status(poll_result.status or raw_status, has_result_url=False)
            if normalized_status not in {"queued", "running"}:
                normalized_status = "running"
            result_url_present = bool(poll_result.result_url or poll_result.file_url)
            fallback_blocked_reason = "primary_provider_in_progress" if attempt_index == 0 else "selected_provider_in_progress"
            wait_max = max(60, _env_int(env, "PRODUCT_VIDEO_PROVIDER_MAX_WAIT_SECONDS", DEFAULT_PRODUCT_VIDEO_PROVIDER_MAX_WAIT_SECONDS))
            telemetry = _provider_pending_telemetry(
                request,
                poll_result,
                attempt_traces=_copy_attempt_traces(),
                wait_max=wait_max,
            )
            payload = {
                "ok": False,
                **_attempt_base(),
                **telemetry,
                "fallback_used": attempt_index > 0,
                "fallback_reason": first_fallback_reason if attempt_index > 0 else "",
                "provider_fallback_attempted": bool(attempt_index > 0),
                "provider_fallback_attempts": list(attempt_failures),
                "provider_fallback_reason": first_fallback_reason if attempt_index > 0 else "",
                "fallback_provider_attempts": list(attempt_failures),
                "selected_provider_after_fallback": current_adapter.provider_name if attempt_index > 0 else "",
                "provider_submit_called": submit_called_flag,
                "provider_submit_http_status": submit_http_status,
                "provider_task_id_saved": bool(provider_task_ids),
                "submit_accepted": True,
                "provider_poll_called": True,
                "poll_allowed": True,
                "poll_skipped_reason": "",
                "provider_result_url_present": result_url_present,
                "provider_pending_result_url_present": result_url_present,
                "provider_error": "provider_in_progress",
                "blocker": "provider_in_progress",
                "provider_poll_blocker": poll_blocker or "provider_in_progress",
                "continue_polling": True,
                "normalized_provider_status": normalized_status,
                "provider_status": normalized_status,
                "provider_status_raw": raw_status,
                "nonterminal_provider_status": raw_status or normalized_status,
                "provider_task_ids": provider_task_ids,
                "provider_video_ids": provider_video_ids,
                "provider_task_id_masked": mask_provider_task_id(provider_task_key),
                "provider_pending_provider": current_adapter.provider_name,
                "provider_pending_task_id": provider_task_key if provider_task_key == str(submit.provider_task_id or "").strip() else str(submit.provider_task_id or "").strip(),
                "provider_pending_video_id": str(submit.provider_video_id or poll_result.provider_video_id or "").strip(),
                "provider_pending_request_job_id": str(request.job_id or ""),
                "provider_request_job_id": str(request.job_id or ""),
                "request_job_id": str(request.job_id or ""),
                "provider_pending_attempts": _copy_attempt_traces(),
                "provider_pending_deferred": True,
                "fallback_allowed": False,
                "fallback_blocked_reason": fallback_blocked_reason,
                "primary_provider_continue_polling": True,
                "primary_provider_task_id_present": bool(provider_task_ids),
                "primary_provider_task_alive": attempt_index == 0,
                "key4u_submit_suppressed": attempt_index == 0,
                "next_poll_scheduled": True,
                "terminal_state": "final_rendering",
                "progress_message": "provider_in_progress",
                "provider_readiness": status,
                "no_charge": True,
            }
            _mark_trace(
                "poll",
                continue_polling=True,
                blocker="provider_in_progress",
                normalized_status=normalized_status,
                fallback_allowed=False,
                fallback_blocked_reason=fallback_blocked_reason,
                nonterminal_provider_status=raw_status or normalized_status,
                result_url_present=result_url_present,
            )
            payload["provider_attempts"] = _copy_attempt_traces()
            return _merge_contract_debug(_merge_contract_debug(payload, submit.raw), getattr(poll_result, "raw", {}))

        if poll_existing_task:
            _mark_trace(
                "poll",
                submit_called=False,
                submit_accepted=True,
                task_id_present=True,
                task_id_source="persisted_result_json.provider_task_ids.0" if pending_task_id else "persisted_result_json.provider_video_ids.0",
                normalized_status="running",
            )
            submit = VideoSubmitResult(
                ok=True,
                provider_name=current_adapter.provider_name,
                provider_task_id=pending_task_id,
                provider_video_id=pending_video_id,
                provider_status="running",
                raw={
                    "provider_task_id_present": True,
                    "task_id_field_path": "persisted_result_json.provider_task_ids.0" if pending_task_id else "",
                    "video_id_field_path": "persisted_result_json.provider_video_ids.0" if pending_video_id else "",
                    "submit_response_shape": {"type": "persisted_provider_task"},
                },
            )
        else:
            try:
                _mark_trace("submit", submit_called=True)
                submit = current_adapter.submit_video_job(provider_request)
            except Exception as exc:
                exc_payload = {
                    **_attempt_base(),
                    **provider_exception_result(exc, provider=current_adapter.provider_name, stage="submit_request", status=status),
                    "fallback_used": attempt_index > 0,
                    "fallback_reason": first_fallback_reason if attempt_index > 0 else "",
                }
                blocker = str(exc_payload.get("blocker") or "provider_unhandled_exception")
                if attempt_index + 1 < len(candidate_adapters):
                    _record_failure(blocker, exc_payload, submit_failure=True)
                    if is_product_video and _product_video_paid_fallback_blocked(blocker, env, metadata):
                        return _paid_fallback_requires_confirmation_payload(blocker, exc_payload)
                    continue
                _record_failure(blocker, exc_payload, submit_failure=True)
                if allow_pending_result:
                    exc_payload["no_charge"] = True
                exc_payload["provider_attempts"] = _copy_attempt_traces()
                exc_payload["provider_fallback_attempts"] = list(attempt_failures)
                exc_payload["fallback_provider_attempts"] = list(attempt_failures)
                exc_payload["provider_fallback_attempted"] = bool(len(attempt_failures) > 1)
                exc_payload["provider_fallback_reason"] = first_fallback_reason
                return exc_payload
        submit_http_status = _submit_http_status(submit.raw)
        _mark_trace(
            "poll" if poll_existing_task else "submit",
            raw=submit.raw,
            submit_called=submit_called_flag,
            submit_http_status=submit_http_status,
            submit_accepted=bool(submit.ok),
            task_id_present=bool(submit.provider_task_id or submit.provider_video_id),
            task_id_source=str((submit.raw or {}).get("task_id_field_path") or (submit.raw or {}).get("video_id_field_path") or ""),
            normalized_status=normalize_provider_status(submit.provider_status, has_result_url=bool(submit.result_url or submit.file_url)),
            result_url_present=bool(submit.result_url or submit.file_url),
        )
        if not submit.ok:
            blocker = submit.error_code or "provider_submit_failed"
            if attempt_index + 1 < len(candidate_adapters):
                _record_failure(blocker, submit.raw, submit_failure=True)
                if is_product_video and _product_video_paid_fallback_blocked(blocker, env, metadata):
                    return _paid_fallback_requires_confirmation_payload(blocker, submit.raw)
                continue
            _record_failure(blocker, submit.raw, submit_failure=True)
            final_blocker = _final_submit_blocker()
            provider_task_ids = [submit.provider_task_id or submit.provider_video_id] if (submit.provider_task_id or submit.provider_video_id) else []
            payload = {
                "ok": False,
                **_attempt_base(),
                "fallback_used": attempt_index > 0,
                "fallback_reason": first_fallback_reason if attempt_index > 0 else "",
                "provider_fallback_attempted": bool(len(attempt_failures) > 1 or attempt_index > 0),
                "provider_fallback_attempts": list(attempt_failures),
                "provider_fallback_reason": first_fallback_reason,
                "fallback_provider_attempts": list(attempt_failures),
                "selected_provider_after_fallback": current_adapter.provider_name if attempt_index > 0 else "",
                "provider_submit_called": submit_called_flag,
                "provider_submit_http_status": submit_http_status,
                "provider_submit_http_5xx": _is_submit_5xx(submit.raw, blocker, submit_http_status),
                "provider_submit_retriable": bool((submit.raw or {}).get("provider_submit_retriable") or _is_submit_5xx(submit.raw, blocker, submit_http_status)),
                "provider_task_id_saved": bool(provider_task_ids),
                "submit_accepted": False,
                "poll_allowed": False,
                "poll_skipped_reason": "provider_task_id_missing" if blocker == "provider_task_id_missing" else "submit_not_accepted",
                "provider_error": final_blocker,
                "blocker": final_blocker,
                "provider_status": submit.provider_status or "failed",
                "provider_task_ids": provider_task_ids,
                "provider_readiness": status,
                "no_charge": bool(allow_pending_result or (request.metadata or {}).get("product_video")),
            }
            return _merge_contract_debug(payload, submit.raw)
        result_url = submit.result_url or submit.file_url
        poll_result = VideoPollResult(
            ok=True,
            status=normalize_provider_status(submit.provider_status, has_result_url=bool(result_url)),
            provider_name=current_adapter.provider_name,
            provider_task_id=submit.provider_task_id,
            provider_video_id=submit.provider_video_id,
            result_url=result_url,
            file_url=result_url,
            raw_status=submit.provider_status,
        )
        if not result_url:
            provider_task_key = str(submit.provider_task_id or submit.provider_video_id or "").strip()
            if not provider_task_key:
                blocker = "provider_task_id_missing"
                if attempt_index + 1 < len(candidate_adapters):
                    _record_failure(blocker, submit.raw, submit_failure=True)
                    if is_product_video and _product_video_paid_fallback_blocked(blocker, env, metadata):
                        return _paid_fallback_requires_confirmation_payload(blocker, submit.raw)
                    continue
                _record_failure(blocker, submit.raw, submit_failure=True)
                payload = {
                    "ok": False,
                    **_attempt_base(),
                    "fallback_used": attempt_index > 0,
                    "fallback_reason": first_fallback_reason if attempt_index > 0 else "",
                    "provider_fallback_attempted": bool(len(attempt_failures) > 1 or attempt_index > 0),
                    "provider_fallback_attempts": list(attempt_failures),
                    "provider_fallback_reason": first_fallback_reason,
                    "fallback_provider_attempts": list(attempt_failures),
                    "selected_provider_after_fallback": current_adapter.provider_name if attempt_index > 0 else "",
                    "provider_submit_called": submit_called_flag,
                    "provider_submit_http_status": submit_http_status,
                    "provider_task_id_saved": False,
                    "submit_accepted": False,
                    "provider_poll_called": False,
                    "poll_allowed": False,
                    "poll_skipped_reason": "provider_task_id_missing",
                    "provider_error": blocker,
                    "blocker": blocker,
                    "provider_status": submit.provider_status or "failed",
                    "provider_task_ids": [],
                    "provider_readiness": status,
                    "no_charge": bool(allow_pending_result or (request.metadata or {}).get("product_video")),
                }
                return _merge_contract_debug(payload, submit.raw)
            max_attempts = max(1, _env_int(env, "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS", 90))
            interval = max(0, _env_int(env, "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS", 10))
            for attempt in range(1, max_attempts + 1):
                if attempt > 1 and interval:
                    sleep_func(interval)
                try:
                    _mark_trace("poll", poll_called=True)
                    poll_result = current_adapter.poll_video_job(submit.provider_task_id or submit.provider_video_id)
                except Exception as exc:
                    exc_payload = {
                        **_attempt_base(),
                        **provider_exception_result(exc, provider=current_adapter.provider_name, stage="poll_request", status=status),
                        "fallback_used": attempt_index > 0,
                        "fallback_reason": first_fallback_reason if attempt_index > 0 else "",
                    "provider_submit_called": submit_called_flag,
                        "provider_submit_http_status": submit_http_status,
                        "provider_task_id_saved": bool(submit.provider_task_id),
                        "submit_accepted": True,
                        "provider_poll_called": True,
                        "poll_allowed": True,
                        "poll_skipped_reason": "",
                        "provider_task_ids": [submit.provider_task_id] if submit.provider_task_id else [],
                    }
                    blocker = str(exc_payload.get("blocker") or "provider_unhandled_exception")
                    safe_exc_text = str(
                        exc_payload.get("provider_error_message_safe")
                        or exc_payload.get("exception_message_safe")
                        or exc_payload.get("safe_error")
                        or ""
                    ).lower()
                    if (
                        allow_pending_result
                        and (submit.provider_task_id or submit.provider_video_id)
                        and (blocker in PROVIDER_PENDING_BLOCKERS or "in_progress" in safe_exc_text or "pending" in safe_exc_text)
                    ):
                        pending_poll = VideoPollResult(
                            ok=True,
                            status="running",
                            provider_name=current_adapter.provider_name,
                            provider_task_id=submit.provider_task_id,
                            provider_video_id=submit.provider_video_id,
                            raw_status="in_progress",
                            raw=exc_payload,
                        )
                        return _provider_pending_payload(submit, pending_poll, poll_blocker=blocker)
                    if attempt_index + 1 < len(candidate_adapters):
                        _record_failure(blocker, exc_payload, submit_failure=False)
                        if is_product_video and _product_video_paid_fallback_blocked(blocker, env, metadata):
                            return _paid_fallback_requires_confirmation_payload(blocker, exc_payload)
                        break
                    _record_failure(blocker, exc_payload, submit_failure=False)
                    exc_payload["provider_attempts"] = _copy_attempt_traces()
                    return _merge_contract_debug(exc_payload, submit.raw)
                poll_result.status = normalize_provider_status(poll_result.status, has_result_url=bool(poll_result.result_url or poll_result.file_url))
                _mark_trace(
                    "poll",
                    raw=getattr(poll_result, "raw", {}),
                    poll_called=True,
                    poll_http_status=_debug_http_status(getattr(poll_result, "raw", {}), "poll_http_status"),
                    poll_raw_status=str(poll_result.raw_status or ""),
                    normalized_status=poll_result.status,
                    result_url_present=bool(poll_result.result_url or poll_result.file_url),
                )
                if (
                    allow_pending_result
                    and (submit.provider_task_id or submit.provider_video_id)
                    and poll_result.status in PROVIDER_NONTERMINAL_STATUSES
                ):
                    return _provider_pending_payload(
                        submit,
                        poll_result,
                        poll_blocker="provider_status_unknown" if poll_result.error_code == "provider_status_unknown" else "provider_in_progress",
                    )
                if poll_result.status == "succeeded" and (poll_result.result_url or poll_result.file_url):
                    break
                if (
                    allow_pending_result
                    and (submit.provider_task_id or submit.provider_video_id)
                    and poll_result.error_code == "provider_status_unknown"
                ):
                    provider_task_ids = [submit.provider_task_id or submit.provider_video_id]
                    wait_max = max(60, _env_int(env, "PRODUCT_VIDEO_PROVIDER_MAX_WAIT_SECONDS", DEFAULT_PRODUCT_VIDEO_PROVIDER_MAX_WAIT_SECONDS))
                    telemetry = _provider_pending_telemetry(
                        request,
                        poll_result,
                        attempt_traces=_copy_attempt_traces(),
                        wait_max=wait_max,
                    )
                    payload = {
                        "ok": False,
                        **_attempt_base(),
                        **telemetry,
                        "fallback_used": attempt_index > 0,
                        "fallback_reason": first_fallback_reason if attempt_index > 0 else "",
                        "provider_fallback_attempted": bool(attempt_index > 0),
                        "provider_fallback_reason": first_fallback_reason if attempt_index > 0 else "",
                        "provider_submit_called": submit_called_flag,
                        "provider_submit_http_status": submit_http_status,
                        "provider_task_id_saved": bool(provider_task_ids),
                        "submit_accepted": True,
                        "provider_poll_called": True,
                        "poll_allowed": True,
                        "poll_skipped_reason": "",
                        "provider_result_url_present": False,
                        "provider_error": "provider_in_progress",
                        "blocker": "provider_in_progress",
                        "provider_poll_blocker": "provider_status_unknown",
                        "continue_polling": True,
                        "normalized_provider_status": "running",
                        "provider_status": "running",
                        "provider_task_ids": provider_task_ids,
                        "provider_video_ids": [submit.provider_video_id] if submit.provider_video_id else [],
                        "provider_readiness": status,
                        "no_charge": True,
                    }
                    _mark_trace("poll", continue_polling=True, blocker="provider_in_progress", normalized_status="running")
                    payload["provider_attempts"] = _copy_attempt_traces()
                    return _merge_contract_debug(_merge_contract_debug(payload, submit.raw), getattr(poll_result, "raw", {}))
                if poll_result.status in {"failed", "cancelled"}:
                    terminal_result_url = str(poll_result.result_url or poll_result.file_url or "").strip()
                    result_diagnostic = _failed_result_url_diagnostic(terminal_result_url)
                    blocker = (
                        "provider_failed_result_url_invalid"
                        if terminal_result_url
                        else poll_result.error_code or f"provider_poll_{poll_result.status}"
                    )
                    if attempt_index + 1 < len(candidate_adapters):
                        _record_failure(blocker, getattr(poll_result, "raw", {}), submit_failure=False)
                        if is_product_video and _product_video_paid_fallback_blocked(blocker, env, metadata):
                            return _paid_fallback_requires_confirmation_payload(blocker, getattr(poll_result, "raw", {}))
                        break
                    _record_failure(blocker, getattr(poll_result, "raw", {}), submit_failure=False)
                    payload = {
                        "ok": False,
                        **_attempt_base(),
                        **result_diagnostic,
                        "fallback_used": attempt_index > 0,
                        "fallback_reason": first_fallback_reason if attempt_index > 0 else "",
                        "provider_fallback_attempted": bool(attempt_index > 0),
                        "provider_fallback_reason": first_fallback_reason if attempt_index > 0 else "",
                        "provider_submit_called": submit_called_flag,
                        "provider_submit_http_status": submit_http_status,
                        "provider_task_id_saved": bool(submit.provider_task_id),
                        "submit_accepted": True,
                        "provider_poll_called": True,
                        "poll_allowed": True,
                        "poll_skipped_reason": "",
                        "provider_error": blocker,
                        "blocker": blocker,
                        "provider_result_blocker": blocker,
                        "provider_status": poll_result.status,
                        "continue_polling": False,
                        "fallback_allowed": False,
                        "fallback_blocked_reason": "provider_terminal_failure_no_paid_fallback" if is_product_video else "",
                        "provider_task_ids": [submit.provider_task_id] if submit.provider_task_id else [],
                        "provider_readiness": status,
                        "no_charge": bool(allow_pending_result or (request.metadata or {}).get("product_video")),
                        "charge": 0,
                        "public_message": PUBLIC_PRODUCT_VIDEO_TERMINAL_FAILURE_COPY if is_product_video else "",
                    }
                    _mark_trace(
                        "poll",
                        blocker=blocker,
                        normalized_status=poll_result.status,
                        continue_polling=False,
                        result_url_present=bool(terminal_result_url),
                    )
                    payload["provider_attempts"] = _copy_attempt_traces()
                    return _merge_contract_debug(_merge_contract_debug(payload, submit.raw), getattr(poll_result, "raw", {}))
            else:
                if allow_pending_result and (submit.provider_task_id or submit.provider_video_id) and poll_result.status in PROVIDER_NONTERMINAL_STATUSES:
                    provider_task_ids = [submit.provider_task_id or submit.provider_video_id]
                    wait_max = max(60, _env_int(env, "PRODUCT_VIDEO_PROVIDER_MAX_WAIT_SECONDS", DEFAULT_PRODUCT_VIDEO_PROVIDER_MAX_WAIT_SECONDS))
                    telemetry = _provider_pending_telemetry(
                        request,
                        poll_result,
                        attempt_traces=_copy_attempt_traces(),
                        wait_max=wait_max,
                    )
                    payload = {
                        "ok": False,
                        **_attempt_base(),
                        **telemetry,
                        "fallback_used": attempt_index > 0,
                        "fallback_reason": first_fallback_reason if attempt_index > 0 else "",
                        "provider_submit_called": submit_called_flag,
                        "provider_submit_http_status": submit_http_status,
                        "provider_task_id_saved": bool(provider_task_ids),
                        "submit_accepted": True,
                        "provider_poll_called": True,
                        "poll_allowed": True,
                        "poll_skipped_reason": "",
                        "provider_result_url_present": False,
                        "provider_error": "provider_in_progress",
                        "blocker": "provider_in_progress",
                        "continue_polling": True,
                        "normalized_provider_status": poll_result.status,
                        "provider_status": poll_result.status,
                        "provider_task_ids": provider_task_ids,
                        "provider_video_ids": [submit.provider_video_id] if submit.provider_video_id else [],
                        "provider_pending_provider": current_adapter.provider_name,
                        "provider_pending_task_id": str(submit.provider_task_id or "").strip(),
                        "provider_pending_video_id": str(submit.provider_video_id or "").strip(),
                        "provider_pending_request_job_id": str(request.job_id or ""),
                        "provider_request_job_id": str(request.job_id or ""),
                        "request_job_id": str(request.job_id or ""),
                        "provider_pending_deferred": True,
                        "fallback_allowed": False,
                        "fallback_blocked_reason": "primary_provider_in_progress" if attempt_index == 0 else "selected_provider_in_progress",
                        "primary_provider_continue_polling": True,
                        "primary_provider_task_alive": attempt_index == 0,
                        "primary_provider_task_id_present": True,
                        "key4u_submit_suppressed": attempt_index == 0,
                        "next_poll_scheduled": True,
                        "provider_readiness": status,
                        "no_charge": True,
                    }
                    _mark_trace("poll", continue_polling=True, blocker="provider_in_progress", normalized_status=poll_result.status)
                    payload["provider_attempts"] = _copy_attempt_traces()
                    return _merge_contract_debug(_merge_contract_debug(payload, submit.raw), getattr(poll_result, "raw", {}))
                blocker = "provider_timeout"
                if attempt_index + 1 < len(candidate_adapters):
                    _record_failure(blocker)
                    if is_product_video and _product_video_paid_fallback_blocked(blocker, env, metadata):
                        return _paid_fallback_requires_confirmation_payload(blocker)
                    continue
                _record_failure(blocker)
                payload = {
                    "ok": False,
                    **_attempt_base(),
                    "fallback_used": attempt_index > 0,
                    "fallback_reason": first_fallback_reason if attempt_index > 0 else "",
                        "provider_submit_called": submit_called_flag,
                    "provider_submit_http_status": submit_http_status,
                    "provider_task_id_saved": bool(submit.provider_task_id),
                    "submit_accepted": True,
                    "provider_poll_called": True,
                    "poll_allowed": True,
                    "poll_skipped_reason": "",
                    "provider_error": blocker,
                    "blocker": blocker,
                    "provider_status": "timeout",
                    "provider_task_ids": [submit.provider_task_id] if submit.provider_task_id else [],
                    "provider_readiness": status,
                }
                if is_product_video:
                    payload.update({
                        "status": "failed_no_charge",
                        "terminal_state": "failed_no_charge",
                        "public_message": PUBLIC_PRODUCT_VIDEO_TERMINAL_FAILURE_COPY,
                        "no_charge": True,
                        "charge": 0,
                        "charged_xu": 0,
                    })
                _mark_trace("poll", blocker=blocker, normalized_status="timeout")
                payload["provider_attempts"] = _copy_attempt_traces()
                return _merge_contract_debug(_merge_contract_debug(payload, submit.raw), getattr(poll_result, "raw", {}))
            if attempt_failures and attempt_failures[-1].get("provider") == current_adapter.provider_name:
                continue
        if (
            allow_pending_result
            and (submit.provider_task_id or submit.provider_video_id)
            and poll_result.status in PROVIDER_NONTERMINAL_STATUSES
        ):
            return _provider_pending_payload(submit, poll_result, poll_blocker="provider_in_progress")
        if not (poll_result.result_url or poll_result.file_url):
            blocker = "provider_result_url_missing"
            if attempt_index + 1 < len(candidate_adapters):
                _record_failure(blocker)
                if is_product_video and _product_video_paid_fallback_blocked(blocker, env, metadata):
                    return _paid_fallback_requires_confirmation_payload(blocker)
                continue
            _record_failure(blocker)
            payload = {
                "ok": False,
                **_attempt_base(),
                "fallback_used": attempt_index > 0,
                "fallback_reason": first_fallback_reason if attempt_index > 0 else "",
                "provider_submit_called": submit_called_flag,
                "provider_submit_http_status": submit_http_status,
                "provider_task_id_saved": bool(submit.provider_task_id),
                "submit_accepted": True,
                "provider_poll_called": bool(not result_url),
                "poll_allowed": bool(not result_url),
                "poll_skipped_reason": "" if not result_url else "result_url_from_submit",
                "provider_result_url_present": False,
                "provider_error": blocker,
                "blocker": blocker,
                "provider_status": poll_result.status,
                "provider_task_ids": [submit.provider_task_id] if submit.provider_task_id else [],
                "provider_readiness": status,
            }
            if is_product_video:
                payload.update({
                    "status": "failed_no_charge",
                    "terminal_state": "failed_no_charge",
                    "public_message": PUBLIC_PRODUCT_VIDEO_TERMINAL_FAILURE_COPY,
                    "no_charge": True,
                    "charge": 0,
                    "charged_xu": 0,
                })
            _mark_trace("result", blocker=blocker, result_url_present=False, normalized_status=poll_result.status)
            payload["provider_attempts"] = _copy_attempt_traces()
            return _merge_contract_debug(_merge_contract_debug(payload, submit.raw), getattr(poll_result, "raw", {}))
        result_url_value = str(poll_result.result_url or poll_result.file_url or "").strip()
        result_diagnostic = _failed_result_url_diagnostic(result_url_value)
        if not result_diagnostic.get("result_url_valid"):
            blocker = "provider_failed_result_url_invalid"
            if attempt_index + 1 < len(candidate_adapters):
                _record_failure(blocker, {**(getattr(poll_result, "raw", {}) or {}), **result_diagnostic}, submit_failure=False)
                if is_product_video and _product_video_paid_fallback_blocked(blocker, env, metadata):
                    return _paid_fallback_requires_confirmation_payload(blocker, {**(getattr(poll_result, "raw", {}) or {}), **result_diagnostic})
                continue
            _record_failure(blocker, {**(getattr(poll_result, "raw", {}) or {}), **result_diagnostic}, submit_failure=False)
            payload = {
                "ok": False,
                **_attempt_base(),
                **result_diagnostic,
                "fallback_used": attempt_index > 0,
                "fallback_reason": first_fallback_reason if attempt_index > 0 else "",
                "provider_submit_called": submit_called_flag,
                "provider_submit_http_status": submit_http_status,
                "provider_task_id_saved": bool(submit.provider_task_id),
                "submit_accepted": True,
                "provider_poll_called": bool(not result_url),
                "poll_allowed": bool(not result_url),
                "poll_skipped_reason": "" if not result_url else "result_url_from_submit",
                "provider_error": blocker,
                "blocker": blocker,
                "provider_result_blocker": blocker,
                "provider_status": poll_result.status,
                "provider_task_ids": [submit.provider_task_id] if submit.provider_task_id else [],
                "provider_readiness": status,
            }
            if is_product_video:
                payload.update({
                    "status": "failed_no_charge",
                    "terminal_state": "failed_no_charge",
                    "public_message": PUBLIC_PRODUCT_VIDEO_TERMINAL_FAILURE_COPY,
                    "no_charge": True,
                    "charge": 0,
                    "charged_xu": 0,
                })
            _mark_trace("result", blocker=blocker, result_url_present=False, normalized_status=poll_result.status)
            payload["provider_attempts"] = _copy_attempt_traces()
            return _merge_contract_debug(_merge_contract_debug(payload, submit.raw), getattr(poll_result, "raw", {}))
        try:
            _mark_trace("download", download_called=True, result_url_present=True)
            artifact: VideoArtifactResult = current_adapter.materialize_result(poll_result, str(request.job_id or submit.provider_task_id))
        except Exception as exc:
            exc_payload = {
                **_attempt_base(),
                **provider_exception_result(exc, provider=current_adapter.provider_name, stage="download", status=status),
                "fallback_used": attempt_index > 0,
                "fallback_reason": first_fallback_reason if attempt_index > 0 else "",
                "provider_submit_called": submit_called_flag,
                "provider_submit_http_status": submit_http_status,
                "provider_task_id_saved": bool(submit.provider_task_id),
                "submit_accepted": True,
                "provider_poll_called": bool(not result_url),
                "poll_allowed": bool(not result_url),
                "poll_skipped_reason": "" if not result_url else "result_url_from_submit",
                "provider_result_url_present": bool(poll_result.result_url or poll_result.file_url),
                "provider_task_ids": [submit.provider_task_id] if submit.provider_task_id else [],
            }
            if is_product_video:
                exc_payload.update({
                    "status": "failed_no_charge",
                    "terminal_state": "failed_no_charge",
                    "public_message": PUBLIC_PRODUCT_VIDEO_TERMINAL_FAILURE_COPY,
                    "no_charge": True,
                    "charge": 0,
                    "charged_xu": 0,
                })
            blocker = str(exc_payload.get("blocker") or "provider_unhandled_exception")
            if attempt_index + 1 < len(candidate_adapters):
                _record_failure(blocker)
                if is_product_video and _product_video_paid_fallback_blocked(blocker, env, metadata):
                    return _paid_fallback_requires_confirmation_payload(blocker)
                continue
            _record_failure(blocker)
            _mark_trace("download", blocker=blocker, validation_passed=False, safe_error=str(exc_payload.get("exception_message_safe") or "")[:220])
            exc_payload["provider_attempts"] = _copy_attempt_traces()
            return _merge_contract_debug(_merge_contract_debug(exc_payload, submit.raw), getattr(poll_result, "raw", {}))
        if not artifact.ok:
            blocker = artifact.error_code or "provider_download_failed"
            _mark_trace(
                "validate",
                download_called=True,
                download_content_type=str(artifact.content_type or ""),
                downloaded_file_size=int(artifact.bytes or 0),
                validation_passed=False,
                blocker=blocker,
                safe_error=str(artifact.error_message or blocker)[:220],
            )
            if attempt_index + 1 < len(candidate_adapters):
                _record_failure(
                    blocker,
                    {
                        **(getattr(poll_result, "raw", {}) or {}),
                        "provider_result_blocker": blocker,
                        "result_url_present": True,
                        "download_content_type": artifact.content_type,
                        "downloaded_file_size": artifact.bytes,
                        "provider_error_message_safe": artifact.error_message or blocker,
                    },
                )
                if is_product_video and _product_video_paid_fallback_blocked(blocker, env, metadata):
                    return _paid_fallback_requires_confirmation_payload(
                        blocker,
                        {
                            **(getattr(poll_result, "raw", {}) or {}),
                            "provider_result_blocker": blocker,
                            "result_url_present": True,
                            "download_content_type": artifact.content_type,
                            "downloaded_file_size": artifact.bytes,
                            "provider_error_message_safe": artifact.error_message or blocker,
                        },
                    )
                continue
            _record_failure(
                blocker,
                {
                    **(getattr(poll_result, "raw", {}) or {}),
                    "provider_result_blocker": blocker,
                    "result_url_present": True,
                    "download_content_type": artifact.content_type,
                    "downloaded_file_size": artifact.bytes,
                    "provider_error_message_safe": artifact.error_message or blocker,
                },
            )
            payload = {
                "ok": False,
                **_attempt_base(),
                "fallback_used": attempt_index > 0,
                "fallback_reason": first_fallback_reason if attempt_index > 0 else "",
                "provider_submit_called": submit_called_flag,
                "provider_submit_http_status": submit_http_status,
                "provider_task_id_saved": bool(submit.provider_task_id),
                "submit_accepted": True,
                "provider_poll_called": bool(not result_url),
                "poll_allowed": bool(not result_url),
                "poll_skipped_reason": "" if not result_url else "result_url_from_submit",
                "provider_result_url_present": True,
                "provider_error": blocker,
                "blocker": blocker,
                "provider_status": poll_result.status,
                "provider_task_ids": [submit.provider_task_id] if submit.provider_task_id else [],
                "provider_video_ids": [submit.provider_video_id] if submit.provider_video_id else [],
                "provider_task_id_masked": mask_provider_task_id(submit.provider_task_id),
                "result_url_present": True,
                "download_status": artifact.error_code or "failed",
                "provider_readiness": status,
            }
            if is_product_video:
                payload.update({
                    "status": "failed_no_charge",
                    "terminal_state": "failed_no_charge",
                    "public_message": PUBLIC_PRODUCT_VIDEO_TERMINAL_FAILURE_COPY,
                    "no_charge": True,
                    "charge": 0,
                    "charged_xu": 0,
                })
            payload["provider_result_blocker"] = payload["blocker"]
            return _merge_contract_debug(_merge_contract_debug(payload, submit.raw), getattr(poll_result, "raw", {}))
        _mark_trace(
            "final",
            download_called=True,
            download_content_type=str(artifact.content_type or ""),
            downloaded_file_size=int(artifact.bytes or 0),
            validation_passed=True,
            result_url_present=True,
            normalized_status="downloaded",
        )
        payload = {
            "ok": True,
            **_attempt_base(),
            "provider_submit_called": submit_called_flag,
            "provider_submit_http_status": submit_http_status,
            "provider_task_id_saved": bool(submit.provider_task_id),
            "submit_accepted": True,
            "provider_poll_called": bool(not result_url),
            "poll_allowed": bool(not result_url),
            "poll_skipped_reason": "" if not result_url else "result_url_from_submit",
            "provider_result_url_present": True,
            "provider_task_ids": [submit.provider_task_id] if submit.provider_task_id else [],
            "provider_video_ids": [submit.provider_video_id] if submit.provider_video_id else [],
            "provider_task_id_masked": mask_provider_task_id(submit.provider_task_id),
            "provider_status": "downloaded",
            "result_url_present": True,
            "download_status": "downloaded",
            "output_path": artifact.local_path,
            "local_path": artifact.local_path,
            "bytes": artifact.bytes,
            "duration": artifact.duration,
            "has_video_stream": artifact.has_video_stream,
            "has_audio_stream": artifact.has_audio_stream,
            "artifact_hash": artifact.artifact_hash,
            "provider_readiness": status,
        }
        return _merge_contract_debug(_merge_contract_debug(payload, submit.raw), getattr(poll_result, "raw", {}))
    return {
        "ok": False,
        **base_debug,
        "provider_attempted": False,
        "provider_error": "provider_capability_missing",
        "blocker": "provider_capability_missing",
        "provider_status": "not_attempted",
        "provider_readiness": status,
    }
