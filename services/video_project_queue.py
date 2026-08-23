"""SQLite-backed video project state machine and worker queue.

This module is intentionally provider-free. It stores planning state, creates a
persistent render job after final confirmation, and lets a worker claim jobs
atomically from SQLite.
"""

from __future__ import annotations

import asyncio
import hmac
import inspect
import json
import hashlib
import os
import socket
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urlparse

from services import (
    product_video_public_seam,
    video_final_output,
    video_uiflow3_execution_contract,
)
from services.video_ai_real_pricing import public_quality_catalog
from services.video_provider_catalog import (
    model_metadata_from_resolution,
    normalize_tier,
    resolve_product_video_model,
)


PROJECT_STATUSES = (
    "draft_planning",
    "draft_assets",
    "draft_prompt",
    "draft_addons",
    "draft_quality",
    "draft_scene_count",
    "draft_invoice",
    "queued_for_worker",
    "processing",
    "completed",
    "failed",
    "cancelled",
)
PROJECT_DRAFT_STATUSES = tuple(status for status in PROJECT_STATUSES if status.startswith("draft_"))
SCENE_STATUSES = ("pending", "gen_audio", "gen_image", "gen_video", "postprocess", "done", "failed", "terminal_failed")
JOB_STATUSES = ("queued", "processing", "completed", "failed", "cancelled")
VIDEO_RENDER_JOB_TYPE = "video_render"
VIDEO_JOB_PRECHECK_RUNNING = "precheck_running"
VIDEO_JOB_PRECHECK_BLOCKED = "precheck_blocked"
VIDEO_JOB_READY_TO_SUBMIT = "ready_to_submit"
PRODUCT_VIDEO_DISPATCH_OUTBOX_OWNER = "owner_product_video"
PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID = "product_video_public_confirm_v1"
PRODUCT_VIDEO_PUBLIC_CONFIRM_CALLBACK = "vproduct|b14_confirm"
PRODUCT_VIDEO_CANONICAL_ENGINE_ENTRY = "b13_r18c"
PRODUCT_VIDEO_CANONICAL_WORKER_CAPABILITY = "canonical_multiscene_b13_r18c_v1"
PRODUCT_VIDEO_ADMISSION_TTL_SECONDS_DEFAULT = 60
PRODUCT_VIDEO_FINAL_ADMISSION_CONTEXT_VERSION = "product_video_final_admission_v1"
PRODUCT_VIDEO_PROBATION_ADMISSION_MODE = "public_confirmed_probation"
PRODUCT_VIDEO_PROBATION_FAILURE_COOLDOWN_SECONDS_DEFAULT = 1800
PRODUCT_VIDEO_EXISTING_TASK_RECOVERY_MAX_ATTEMPTS = 3
PRODUCT_VIDEO_EXISTING_TASK_RECOVERY_COOLDOWN_SECONDS = 60
PRODUCT_VIDEO_RECONCILIATION_SOURCES = frozenset(
    {
        "watchdog_scheduler",
        "startup_sweep",
        "worker_claim_recovery",
        "public_status_read_reconcile",
        "manual_admin_reconcile",
    }
)
PRODUCT_VIDEO_WATCHDOG_INTERVAL_SECONDS_DEFAULT = 20
PRODUCT_VIDEO_WATCHDOG_INTERVAL_SECONDS_MIN = 15
PRODUCT_VIDEO_WATCHDOG_INTERVAL_SECONDS_MAX = 30
PRODUCT_VIDEO_DISPATCH_OUTBOX_STATES = (
    "pending",
    "leased",
    "acknowledged",
    "retry_wait",
    "completed",
    "terminal_failed",
)
PRODUCT_VIDEO_PREMATURE_DISPATCH_FAILURE_REASONS = frozenset(
    {
        "dispatch_not_started_dispatch_outbox_job_not_claimable",
        "dispatch_not_started_processing_job_has_no_claimable_scene",
        "dispatch_not_started_video_job_claim_conflict",
        "dispatch_not_started_dispatch_outbox_ack_conflict",
    }
)

_PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE: dict[str, Any] = {
    "watchdog_enabled": True,
    "scheduler_registered": False,
    "scheduler_running": False,
    "watchdog_started_at": "",
    "watchdog_generation_id": "",
    "watchdog_tick_count": 0,
    "last_run_at": "",
    "last_success_at": "",
    "last_error": "",
    "jobs_scanned": 0,
    "jobs_reconciled": 0,
    "watchdog_generation_jobs_scanned": 0,
    "watchdog_generation_jobs_reconciled": 0,
    "watchdog_last_reconciled_job_ids": [],
    "last_reconciliation_source": "",
    "next_run_at": "",
    "interval_seconds": PRODUCT_VIDEO_WATCHDOG_INTERVAL_SECONDS_DEFAULT,
    "watchdog_configured_interval_seconds": PRODUCT_VIDEO_WATCHDOG_INTERVAL_SECONDS_DEFAULT,
    "watchdog_effective_interval_seconds": PRODUCT_VIDEO_WATCHDOG_INTERVAL_SECONDS_DEFAULT,
    "watchdog_interval_clamp_applied": False,
    "watchdog_interval_clamp_reason": "",
    "duplicate_scheduler_prevented": False,
}
_PRODUCT_VIDEO_FINAL_ADMISSION_SIGNING_KEY = os.urandom(32)
_PRODUCT_VIDEO_FINAL_ADMISSION_SIGNED_FIELDS = (
    "admission_context_version",
    "admission_snapshot_id",
    "admission_checked_at",
    "admission_candidate_keys",
    "admission_candidate_count",
    "admission_result",
    "admission_user_id",
    "admission_project_id",
    "admission_quote_fingerprint",
    "admission_callback_handler_id",
    "admission_callback_data",
    "admission_provider_health_gate_pass",
    "public_provider_freeze",
    "hidden_submit_freeze",
    "background_submit_freeze",
    "smoke_freeze",
    "public_live_provider_allowed",
    "freeze_blocker_code",
    "freeze_blocker_source",
    "worker_generation_id",
    "worker_git_sha",
    "runtime_sha",
    "worker_compatible",
    "worker_connected",
    "worker_heartbeat_fresh",
    "worker_lease_valid",
    "worker_sha_match",
    "worker_capability_match",
    "worker_identity_conflict",
    "route_requires_provider",
    "handler_id",
    "admission_mode",
    "probation_candidate_key",
    "probation_reason",
    "probation_lock_clear",
    "submit_source",
    "public_user_confirmed",
)
PRODUCT_VIDEO_TIER_PRICE_MAP = {
    normalize_tier(row["tier_id"]): int(row["unit_xu"])
    for row in public_quality_catalog()
}


def now_text(moment: datetime | None = None) -> str:
    return (moment or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")


def product_video_outbox_utc_datetime(moment: datetime | None = None) -> datetime:
    """Return an aware UTC datetime for the SQLite outbox timestamp contract."""
    current = moment or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.astimezone()
    return current.astimezone(timezone.utc)


def product_video_outbox_time_text(moment: datetime | None = None) -> str:
    return product_video_outbox_utc_datetime(moment).strftime("%Y-%m-%d %H:%M:%S")


def normalize_product_video_reconciliation_source(value: Any, default: str = "manual_admin_reconcile") -> str:
    source = str(value or default or "manual_admin_reconcile").strip()
    return source if source in PRODUCT_VIDEO_RECONCILIATION_SOURCES else "manual_admin_reconcile"


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, separators=(",", ":"))


def inline_processor_trace_payload(*, processor: str = "railway_bot", service_mode: str = "inline_video_job") -> dict[str, Any]:
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = ""
    return {
        "actual_processor": str(processor or "railway_bot")[:80],
        "worker_id": str(processor or "railway_bot")[:120],
        "worker_service_mode": str(service_mode or "inline_video_job")[:80],
        "claimed_by_service_mode": str(service_mode or "inline_video_job")[:80],
        "worker_claim_route": "inline",
        "worker_claim_status": "inline_processing",
        "worker_claim_reason": "",
        "process_hostname": str(hostname or "")[:160],
        "process_pid": int(os.getpid() or 0),
    }


def _json_loads(value: str | None, fallback: Any = None) -> Any:
    if not value:
        return {} if fallback is None else fallback
    try:
        return json.loads(value)
    except Exception:
        return {} if fallback is None else fallback


def _product_video_selected_tier(value: Any) -> str:
    return normalize_tier(value)


def _product_video_route_tier_value(invoice: dict[str, Any], project: dict[str, Any]) -> Any:
    return (
        invoice.get("tier")
        or invoice.get("tier_key")
        or invoice.get("routing_quality_tier")
        or invoice.get("quality_tier")
        or project.get("quality_tier")
        or "basic"
    )


def _product_video_quote_consistency(invoice: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
    invoice = dict(invoice or {})
    project = dict(project or {})
    selected_tier = _product_video_selected_tier(_product_video_route_tier_value(invoice, project))
    scene_count = max(1, _as_int(invoice.get("scene_count") or project.get("scene_count"), 1))
    unit_price = _as_int(
        invoice.get("quality_xu")
        or invoice.get("unit_xu")
        or PRODUCT_VIDEO_TIER_PRICE_MAP.get(selected_tier),
        PRODUCT_VIDEO_TIER_PRICE_MAP.get("basic", 220),
    )
    calculated_total = max(1, unit_price) * scene_count + max(
        0,
        _as_int(invoice.get("addons_xu") or invoice.get("addon_total_xu"), 0),
    )
    user_visible = _as_int(
        invoice.get("user_visible_price_xu")
        or invoice.get("package_xu")
        or invoice.get("package_price_xu")
        or invoice.get("total_xu")
        or invoice.get("total")
        or project.get("total_xu_estimated")
        or calculated_total,
        calculated_total,
    )
    persisted = _as_int(
        invoice.get("persisted_quoted_price_xu")
        or invoice.get("quoted_price_xu")
        or invoice.get("quoted_price")
        or user_visible,
        user_visible,
    )
    customer_charge = _as_int(
        invoice.get("customer_charge_planned_xu")
        or invoice.get("wallet_charge_amount_xu")
        or invoice.get("charge_amount_planned_xu")
        or persisted,
        persisted,
    )
    list_price = _as_int(
        invoice.get("list_price_xu")
        or invoice.get("standard_price_xu")
        or invoice.get("scene_list_total_xu")
        or invoice.get("total_xu")
        or invoice.get("total")
        or project.get("total_xu_estimated")
        or customer_charge,
        customer_charge,
    )
    provider_budget = _as_int(
        invoice.get("provider_budget_xu")
        or invoice.get("provider_cost_cap_xu")
        or invoice.get("total_xu")
        or invoice.get("total")
        or project.get("total_xu_estimated")
        or customer_charge,
        customer_charge,
    )
    consistent = bool(user_visible > 0 and persisted == user_visible and customer_charge == user_visible)
    reason = "" if consistent else "product_video_quote_mismatch_no_charge"
    return {
        "selected_tier": selected_tier,
        "user_visible_price_xu": user_visible,
        "persisted_quoted_price_xu": persisted,
        "customer_charge_planned_xu": customer_charge,
        "wallet_charge_amount_xu": customer_charge,
        "charge_amount_planned_xu": customer_charge,
        "list_price_xu": list_price,
        "standard_price_xu": list_price,
        "promo_discount_xu": max(0, list_price - customer_charge),
        "provider_budget_xu": provider_budget,
        "provider_cost_cap_xu": provider_budget,
        "quote_consistent": consistent,
        "quote_mismatch_reason": reason,
    }


def product_video_admission_quote_fingerprint(project: dict[str, Any], user_id: int | None = None) -> str:
    project = dict(project or {})
    invoice = _json_loads(str(project.get("invoice_json") or ""), {})
    if not isinstance(invoice, dict):
        invoice = {}
    quote = _product_video_quote_consistency(invoice, project)
    payload = {
        "user_id": int(user_id if user_id is not None else project.get("user_id") or 0),
        "project_id": int(project.get("project_id") or 0),
        "project_uuid": str(project.get("project_uuid") or ""),
        "scene_count": max(1, _as_int(project.get("scene_count") or invoice.get("scene_count"), 1)),
        "selected_tier": str(quote.get("selected_tier") or ""),
        "customer_charge_planned_xu": _as_int(quote.get("customer_charge_planned_xu"), 0),
    }
    return hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()


def _product_video_final_admission_signature_payload(admission: dict[str, Any] | None) -> bytes:
    current = dict(admission or {})
    payload = {key: current.get(key) for key in _PRODUCT_VIDEO_FINAL_ADMISSION_SIGNED_FIELDS}
    return _json_dumps(payload).encode("utf-8")


def sign_product_video_final_admission_context(admission: dict[str, Any] | None) -> dict[str, Any]:
    """Seal a short-lived server-created final-confirm context.

    The process-local key prevents public/legacy callers from manufacturing a
    PASS context. The context is consumed immediately by the same bot process.
    """
    sealed = dict(admission or {})
    sealed["admission_context_version"] = PRODUCT_VIDEO_FINAL_ADMISSION_CONTEXT_VERSION
    sealed["admission_context_signature"] = hmac.new(
        _PRODUCT_VIDEO_FINAL_ADMISSION_SIGNING_KEY,
        _product_video_final_admission_signature_payload(sealed),
        hashlib.sha256,
    ).hexdigest()
    return sealed


def verify_product_video_final_admission_context(admission: dict[str, Any] | None) -> bool:
    current = dict(admission or {})
    if current.get("admission_context_version") != PRODUCT_VIDEO_FINAL_ADMISSION_CONTEXT_VERSION:
        return False
    supplied = str(current.get("admission_context_signature") or "").strip()
    if not supplied:
        return False
    expected = hmac.new(
        _PRODUCT_VIDEO_FINAL_ADMISSION_SIGNING_KEY,
        _product_video_final_admission_signature_payload(current),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(supplied, expected)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if isinstance(value, bool):
            return int(value)
        text = str(value).strip().rstrip("%")
        if not text:
            return int(default)
        return int(float(text))
    except Exception:
        return int(default)


def _parse_time_epoch(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        numeric = float(value)
        if numeric > 0:
            return numeric
    except Exception:
        pass
    text = str(value or "").strip()
    if not text:
        return 0.0
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(text.replace("Z", "").split("+", 1)[0], fmt).timestamp()
        except Exception:
            continue
    return 0.0


def _parse_outbox_utc_epoch(value: Any) -> float:
    """Parse outbox timestamps as UTC instead of the host's local timezone."""
    if value in (None, ""):
        return 0.0
    try:
        numeric = float(value)
        if numeric > 0:
            return numeric
    except Exception:
        pass
    text = str(value or "").strip()
    if not text:
        return 0.0
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).timestamp()
    except Exception:
        return 0.0


def _format_epoch(epoch: float) -> str:
    try:
        if float(epoch) > 0:
            return datetime.fromtimestamp(float(epoch)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    return ""


def _human_elapsed(seconds: int | float | str = 0) -> str:
    total = max(0, _as_int(seconds, 0))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} giờ {minutes} phút {secs} giây"
    if minutes:
        return f"{minutes} phút {secs} giây"
    return f"{secs} giây"


def _progress_from_value(value: Any) -> int:
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


R8B_SHOPAIKEY_STATUS_KEYS = (
    "shopaikey_status_endpoint_exact",
    "shopaikey_status_http_code",
    "shopaikey_raw_status",
    "shopaikey_normalized_status",
    "shopaikey_data_progress_raw",
    "shopaikey_progress_source",
    "shopaikey_result_url_from_data",
    "shopaikey_data_result_url_present",
    "shopaikey_fail_reason",
    "provider_progress_raw",
    "provider_progress_raw_number",
    "provider_progress_source",
    "http_200_not_used_as_progress",
    "result_url_primary_path_checked",
    "result_url_found",
    "result_url_source_path",
)


def _non_empty(value: Any) -> bool:
    return value not in (None, "")


def _provider_attempts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for key in ("provider_attempts", "provider_pending_attempts", "provider_fallback_attempts", "fallback_provider_attempts"):
        value = payload.get(key)
        if isinstance(value, list):
            attempts.extend(dict(item) for item in value if isinstance(item, dict))
    return attempts


def _r8b_shopaikey_parser_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the newest ShopAIKey R8B parser fields from payload or attempts."""
    payload = dict(payload or {})
    selected = str(payload.get("selected_provider") or payload.get("selected_provider_before_submit") or payload.get("provider_pending_provider") or "").strip()
    candidates: list[dict[str, Any]] = []
    if any(key in payload for key in R8B_SHOPAIKEY_STATUS_KEYS):
        candidates.append(payload)
    for item in _provider_attempts(payload):
        provider = str(item.get("provider") or "").strip()
        if selected and provider and provider != selected:
            continue
        if any(key in item for key in R8B_SHOPAIKEY_STATUS_KEYS):
            candidates.append(item)
    if not candidates and selected:
        for item in _provider_attempts(payload):
            if any(key in item for key in R8B_SHOPAIKEY_STATUS_KEYS):
                candidates.append(item)
    result: dict[str, Any] = {}
    for item in candidates:
        for key in R8B_SHOPAIKEY_STATUS_KEYS:
            value = item.get(key)
            if _non_empty(value):
                result[key] = value
            elif key not in result and isinstance(value, bool):
                result[key] = value
    return result


def _progress_source(payload: dict[str, Any], parser_fields: dict[str, Any]) -> str:
    for key in ("provider_progress_source", "shopaikey_progress_source"):
        value = parser_fields.get(key)
        if _non_empty(value):
            return str(value)
    for key in ("provider_progress_source", "shopaikey_progress_source"):
        value = payload.get(key)
        if _non_empty(value):
            return str(value)
    return "none"


def _extract_progress_raw(payload: dict[str, Any]) -> Any:
    parser_fields = _r8b_shopaikey_parser_fields(payload)
    for key in ("shopaikey_data_progress_raw", "provider_progress_raw"):
        value = parser_fields.get(key)
        if _non_empty(value):
            return value
    for key in (
        "shopaikey_data_progress_raw",
        "provider_progress_raw",
        "provider_progress_percent",
        "provider_progress_normalized",
        "progress_percent",
        "progress",
        "percent",
        "percentage",
    ):
        value = payload.get(key)
        if value not in (None, ""):
            return value
    for source_key in ("provider_raw", "poll_raw", "raw", "response"):
        value = payload.get(source_key)
        if isinstance(value, dict):
            nested = _extract_progress_raw(value)
            if nested not in (None, ""):
                return nested
    return None


def _provider_result_url_valid(value: Any = "") -> bool:
    raw = str(value or "").strip()
    if not raw or raw[:1] in {"{", "["} or raw.lower() in {"none", "null", "false", "error"}:
        return False
    parsed = urlparse(raw)
    return bool(parsed.scheme in {"http", "https"} and parsed.netloc)


def _provider_result_url_present(payload: dict[str, Any]) -> bool:
    if payload.get("result_url_valid") is False or payload.get("provider_result_url_valid") is False:
        return False
    for key in (
        "provider_result_url_present",
        "result_url_present",
        "provider_final_url_present",
        "final_url_present",
    ):
        if payload.get(key) and not payload.get("result_url_invalid_reason"):
            return True
    for key in (
        "provider_result_url",
        "result_url",
        "download_url",
        "provider_download_url",
        "file_url",
        "video_url",
        "output_url",
        "final_video_url",
    ):
        if _provider_result_url_valid(payload.get(key)):
            return True
    return False


def _provider_final_output_ready(payload: dict[str, Any]) -> bool:
    scene_count = max(
        _as_int(payload.get("scene_count") or payload.get("scenes_total") or payload.get("scene_tasks_total"), 0),
        len(payload.get("scene_tasks") or []) if isinstance(payload.get("scene_tasks"), list) else 0,
    )
    if scene_count > 1:
        coverage_count = _as_int(
            payload.get("scene_coverage_count")
            or payload.get("completed_scene_count")
            or payload.get("scene_tasks_completed")
            or payload.get("scenes_done"),
            0,
        )
        concat_valid = bool(
            payload.get("concat_output_valid")
            or payload.get("stitch_output_valid")
            or str(payload.get("concat_status") or "").strip().lower() == "completed"
        )
        final_flag = bool(
            payload.get("final_mp4_validated")
            or payload.get("final_mp4_valid")
            or payload.get("final_video_validated")
            or payload.get("delivery_succeeded")
            or payload.get("video_delivered")
            or payload.get("final_delivered")
        )
        # A downloaded scene clip is not the final artifact for a multi-scene job.
        return bool(coverage_count >= scene_count and concat_valid and final_flag)
    if any(
        payload.get(key)
        for key in (
            "final_mp4_validated",
            "final_mp4_valid",
            "final_video_validated",
            "delivery_succeeded",
            "video_delivered",
            "final_delivered",
        )
    ):
        return True
    if _as_int(payload.get("output_bytes") or payload.get("bytes") or payload.get("final_video_bytes"), 0) > 0:
        return True
    if str(payload.get("final_video_file_id") or "").strip():
        return True
    return False


def _provider_status_value_is_not_start(*values: Any) -> bool:
    for value in values:
        text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        if text in {
            "not_start",
            "not_started",
            "notstart",
            "provider_not_start",
            "media_generation_status_not_start",
            "media_generation_status_not_started",
        }:
            return True
        if "not_start" in text or "not_started" in text:
            return True
    return False


def _provider_status_value_is_running(*values: Any) -> bool:
    for value in values:
        text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        if text in {
            "running",
            "processing",
            "in_progress",
            "provider_running",
            "provider_in_progress",
            "media_generation_status_pending",
            "media_generation_status_in_progress",
        }:
            return True
    return False


def _actual_provider_payload_status(payload: dict[str, Any]) -> tuple[str, str, bool]:
    source = str(payload.get("provider_status_payload_source") or "").strip()
    status = ""
    if source.startswith("shopaikey.data."):
        status = str(payload.get("shopaikey_data_status") or payload.get("shopaikey_raw_status") or "").strip()
    authoritative = bool(source.startswith("shopaikey.data.") and status)
    return status, source, authoritative


def _provider_status_for_progress(payload: dict[str, Any], alive: bool) -> str:
    actual_status, _actual_source, actual_authoritative = _actual_provider_payload_status(payload)
    if actual_authoritative:
        if _provider_status_value_is_not_start(actual_status):
            return "not_start"
        if _provider_status_value_is_running(actual_status):
            return "in_progress"
        return str(actual_status or "").strip().lower()
    if _provider_status_value_is_not_start(
        payload.get("shopaikey_data_status"),
        payload.get("shopaikey_raw_status"),
        payload.get("raw_provider_status"),
        payload.get("provider_status_raw"),
        payload.get("nonterminal_provider_status"),
    ):
        return "not_start"
    status = str(
        payload.get("normalized_provider_status")
        or payload.get("provider_status")
        or payload.get("provider_status_raw")
        or payload.get("nonterminal_provider_status")
        or ""
    ).strip().lower()
    if alive and not status:
        return "running"
    return status


def _provider_progress_effective(
    normalized_progress: int,
    *,
    raw_progress_number: float | None = None,
    provider_status: str,
    result_url_present: bool,
    final_output_ready: bool,
    alive: bool,
) -> tuple[int, bool, str, bool]:
    if raw_progress_number is not None and (raw_progress_number < 0 or raw_progress_number > 100):
        return 0, False, "invalid_provider_progress_raw", False
    if normalized_progress <= 0:
        return 0, False, "", False
    running = alive or provider_status in {"running", "queued", "pending", "in_progress", "processing", "not_start", "final_rendering"}
    if final_output_ready or (normalized_progress >= 100 and result_url_present and not running):
        return 100, True, "", False
    if running and not result_url_present and normalized_progress >= 100:
        return 0, False, "in_progress_without_result_url", False
    if running and not result_url_present:
        return normalized_progress, True, "", False
    if result_url_present:
        return max(95, min(99, normalized_progress)), True, "", False
    return min(99, normalized_progress), normalized_progress < 100, "missing_final_mp4" if normalized_progress >= 100 else "", normalized_progress >= 100


def _render_subprogress(
    *,
    normalized_progress: int,
    elapsed: int,
    wait_max: int,
    poll_count: int,
    previous_render_progress: int,
    result_url_present: bool,
    final_output_ready: bool,
    alive: bool,
    provider_status: str,
    provider_progress_trusted: bool = False,
) -> tuple[int, str, bool, bool]:
    if final_output_ready:
        return 100, "final_mp4_validated", False, False
    if result_url_present:
        progress = 95
        return max(previous_render_progress, progress), "provider_result_url", False, False
    effective, trusted, _reason, capped = _provider_progress_effective(
        normalized_progress,
        provider_status=provider_status,
        result_url_present=result_url_present,
        final_output_ready=final_output_ready,
        alive=alive,
    )
    if effective > 0 and trusted and provider_progress_trusted:
        elapsed_progress = 0
        if alive and not result_url_present:
            wait_window = max(60, int(wait_max or 0))
            elapsed_seconds = max(0, int(elapsed or 0))
            elapsed_progress = int(min(85, max(0, round((elapsed_seconds / wait_window) * 85))))
        progress = max(effective, elapsed_progress)
        source = "provider_raw_elapsed_max" if elapsed_progress > effective else "provider_raw"
        estimated = bool(elapsed_progress > effective)
    else:
        wait_window = max(60, int(wait_max or 0))
        elapsed_seconds = max(0, int(elapsed or 0))
        if alive:
            # Real elapsed wait is the only public-safe progress before result_url.
            # It starts at 0, never trusts HTTP 200/raw provider numbers, and caps
            # below completion until a downloadable MP4 URL exists.
            progress = int(min(85, max(0, round((elapsed_seconds / wait_window) * 85))))
            source = "elapsed_provider_wait"
            estimated = False
        else:
            del poll_count
            progress = 0
            source = "indeterminate"
            estimated = False
    if alive:
        progress = min(90, progress)
    if source != "indeterminate":
        progress = max(previous_render_progress, progress)
    if alive:
        progress = min(90, progress)
    return max(0, min(100, progress)), source, estimated, capped


def _provider_poll_count(payload: dict[str, Any]) -> int:
    count, _source = _provider_poll_count_with_source(payload)
    return count


def _provider_poll_count_with_source(payload: dict[str, Any]) -> tuple[int, str]:
    raw_count = payload.get("provider_poll_count")
    if raw_count in (None, ""):
        raw_count = payload.get("poll_count")
    count = _as_int(raw_count, 0)
    declared_source = str(payload.get("provider_poll_count_source") or "").strip().lower()
    trusted_sources = {"internal_worker", "worker_poll", "worker", "live_worker", "registry_live", "active_worker"}
    source = declared_source if count > 0 and declared_source in trusted_sources else ("payload" if count > 0 else "none")
    attempts = payload.get("provider_attempts") or payload.get("provider_pending_attempts") or []
    if isinstance(attempts, list):
        poll_attempts = sum(1 for item in attempts if isinstance(item, dict) and (item.get("poll_called") or item.get("phase") == "poll"))
        if poll_attempts > 0 and poll_attempts >= count:
            count = max(count, poll_attempts)
            source = "provider_attempts"
    return max(0, count), source


def provider_task_alive(payload: dict[str, Any] | None = None) -> bool:
    payload = dict(payload or {})
    if payload.get("zero_task_progress_guard") or _as_int(payload.get("valid_provider_task_count"), 1) == 0:
        return False
    terminal = str(payload.get("terminal_state") or payload.get("final_decision") or "").strip().lower()
    task_present = bool(
        payload.get("provider_task_id_saved")
        or payload.get("primary_provider_task_id_present")
        or payload.get("provider_task_ids")
        or payload.get("provider_video_ids")
        or payload.get("provider_pending_task_id")
        or payload.get("provider_pending_video_id")
    )
    actual_status, _actual_source, actual_authoritative = _actual_provider_payload_status(payload)
    actual_running = bool(
        actual_authoritative
        and _provider_status_value_is_running(actual_status)
        and not _provider_status_value_is_not_start(actual_status)
    )
    final_ready = _provider_final_output_ready(payload) or _provider_result_url_present(payload)
    if actual_running and task_present and not final_ready:
        return True
    not_start_under_threshold = bool(
        _provider_status_value_is_not_start(
            payload.get("shopaikey_raw_status"),
            payload.get("shopaikey_data_status"),
            payload.get("raw_provider_status"),
            payload.get("provider_status_raw"),
            payload.get("normalized_provider_status"),
            payload.get("provider_status"),
            payload.get("provider_error"),
            payload.get("blocker"),
        )
        and (payload.get("continue_polling") or payload.get("primary_provider_continue_polling") or payload.get("provider_pending_deferred"))
        and _as_int(payload.get("scene_not_start_elapsed") or payload.get("provider_elapsed_seconds"), 0)
        < max(1, _as_int(payload.get("not_start_threshold_seconds") or payload.get("stall_threshold"), 60))
    )
    stalled_without_fallback = bool(
        payload.get("provider_stalled_not_start")
        and not payload.get("fallback_allowed")
        and not payload.get("fallback_used")
        and str(payload.get("fallback_submit_source") or payload.get("submit_source") or "").strip()
        not in {"public_confirmed_fallback_once", "public_confirmed_scene_fallback_once"}
    )
    if (terminal in {"failed", "failed_no_charge", "failed_refunded", "needs_admin_review"} and not not_start_under_threshold) or stalled_without_fallback:
        return False
    status_text = " ".join(
        str(payload.get(key) or "").strip().lower()
        for key in (
            "normalized_provider_status",
            "provider_status",
            "provider_status_raw",
            "nonterminal_provider_status",
            "provider_error",
            "blocker",
            "provider_poll_blocker",
            "terminal_state",
        )
        if str(payload.get(key) or "").strip()
    )
    return bool(
        payload.get("continue_polling")
        or payload.get("primary_provider_continue_polling")
        or payload.get("provider_pending_deferred")
        or payload.get("primary_provider_task_alive")
        or (task_present and any(marker in status_text for marker in ("running", "queued", "pending", "in_progress", "processing", "final_rendering")))
    )


def reconcile_provider_progress_telemetry(
    job: dict[str, Any] | None,
    payload: dict[str, Any] | None = None,
    *,
    now: datetime | None = None,
    refresh_source: str = "queue",
) -> dict[str, Any]:
    """Return monotonic Product Video progress telemetry without changing provider state."""
    job = dict(job or {})
    payload = dict(payload or {})
    current_dt = now or datetime.now()
    current_epoch = current_dt.timestamp()
    persisted_status = str(job.get("status") or "").strip().lower()
    persisted_progress = max(_as_int(job.get("progress_percent"), 0), _as_int(payload.get("progress_percent"), 0))
    scene_count = max(
        _as_int(payload.get("scene_count") or payload.get("scenes_total") or payload.get("scene_tasks_total"), 0),
        len(payload.get("scene_tasks") or []) if isinstance(payload.get("scene_tasks"), list) else 0,
    )
    multiscene_ledger = (
        product_video_scene_ledger_state({}, job, payload, now=current_dt)
        if scene_count > 1
        else {}
    )
    alive = provider_task_alive(payload)
    terminal_failure_requested = str(payload.get("terminal_state") or payload.get("final_decision") or "").strip().lower() in {
        "failed",
        "failed_no_charge",
        "failed_refunded",
        "needs_admin_review",
    }
    explicit_terminal_failure = bool(
        terminal_failure_requested
        and payload.get("continue_polling") is False
    )
    terminal_failure = terminal_failure_requested
    ledger_terminal_failure = False
    if multiscene_ledger:
        ledger_terminal_failure = multiscene_ledger.get("aggregate_job_status") == "failed_no_charge"
        terminal_failure = bool(explicit_terminal_failure or ledger_terminal_failure)
        alive = bool(multiscene_ledger.get("provider_task_alive") and not terminal_failure)
    processing_truth = bool(
        multiscene_ledger.get("processing_truth_applied")
        or multiscene_ledger.get("active_scene_indexes")
        or multiscene_ledger.get("dispatchable_scene_indexes")
        or multiscene_ledger.get("fallback_candidate_indexes")
    ) if multiscene_ledger else False
    if processing_truth and not terminal_failure:
        if not multiscene_ledger.get("zero_task_progress_guard"):
            alive = True
    wait_max = max(60, _as_int(payload.get("provider_wait_max_seconds"), 20 * 60))
    started_source = "payload"
    started_epoch = _parse_time_epoch(payload.get("provider_started_at_epoch") or payload.get("provider_started_at"))
    if started_epoch <= 0:
        started_source = "provider_wait_started"
        started_epoch = _parse_time_epoch(payload.get("provider_wait_started_epoch") or payload.get("provider_wait_started_at"))
    if started_epoch <= 0:
        started_source = "job_started_at"
        started_epoch = _parse_time_epoch(job.get("started_at"))
    if started_epoch <= 0:
        started_source = "job_updated_at"
        started_epoch = _parse_time_epoch(job.get("updated_at"))
    if started_epoch <= 0:
        started_source = "job_created_at"
        started_epoch = _parse_time_epoch(job.get("created_at"))
    estimated_started = started_source != "payload"
    if started_epoch <= 0:
        started_source = "now"
        started_epoch = current_epoch
        estimated_started = True
    previous_elapsed = _as_int(payload.get("provider_wait_elapsed_seconds") or payload.get("provider_elapsed_seconds"), 0)
    wall_clock_elapsed = int(max(0, current_epoch - started_epoch))
    elapsed = max(previous_elapsed, wall_clock_elapsed)
    elapsed_monotonic_applied = bool(previous_elapsed and wall_clock_elapsed < previous_elapsed)
    raw_progress = _extract_progress_raw(payload)
    normalized_progress = _progress_from_value(raw_progress)
    raw_progress_number = _progress_raw_number(raw_progress)
    parser_fields = _r8b_shopaikey_parser_fields(payload)
    provider_progress_source = _progress_source(payload, parser_fields)
    poll_count, poll_count_source = _provider_poll_count_with_source(payload)
    result_url_present = _provider_result_url_present(payload)
    final_output_ready = _provider_final_output_ready(payload)
    final_delivered = bool(
        payload.get("final_delivered")
        or payload.get("final_mp4_delivered")
        or payload.get("delivery_succeeded")
        or payload.get("video_delivered")
        or payload.get("video_delivered_at")
        or payload.get("video_delivery_message_id")
    )
    if multiscene_ledger:
        # Canonical task output is scene evidence only until every scene is
        # valid and the final concat artifact has passed validation.
        result_url_present = bool(multiscene_ledger.get("final_mp4_valid"))
        final_output_ready = bool(multiscene_ledger.get("final_mp4_valid"))
        final_delivered = bool(multiscene_ledger.get("final_delivered"))
    provider_status = _provider_status_for_progress(payload, alive)
    if multiscene_ledger and alive:
        provider_status = "processing"
    actual_provider_status, actual_provider_source, actual_provider_authoritative = _actual_provider_payload_status(payload)
    actual_provider_running = bool(
        actual_provider_authoritative
        and _provider_status_value_is_running(actual_provider_status)
        and not _provider_status_value_is_not_start(actual_provider_status)
    )
    stale_not_start_blocker_ignored = bool(
        actual_provider_running
        and _provider_status_value_is_not_start(
            payload.get("raw_provider_status"),
            payload.get("provider_status_raw"),
            payload.get("provider_error"),
            payload.get("blocker"),
            payload.get("fallback_block_reason"),
            payload.get("fallback_blocked_reason"),
        )
    )
    provider_not_start = _provider_status_value_is_not_start(
        payload.get("shopaikey_raw_status"),
        payload.get("shopaikey_data_status"),
        payload.get("raw_provider_status"),
        payload.get("provider_status_raw"),
        payload.get("normalized_provider_status"),
        payload.get("provider_status"),
        provider_status,
    )
    if actual_provider_running:
        provider_not_start = False
    scene_not_start_elapsed = max(
        _as_int(payload.get("scene_not_start_elapsed"), 0),
        elapsed if provider_not_start else 0,
    )
    if actual_provider_running:
        scene_not_start_elapsed = 0
    not_start_threshold = max(1, _as_int(payload.get("not_start_threshold_seconds") or payload.get("stall_threshold"), 60))
    provider_stalled_not_start = bool(provider_not_start and scene_not_start_elapsed >= not_start_threshold and not result_url_present and not final_output_ready)
    if (
        alive
        and provider_not_start
        and not provider_stalled_not_start
        and not explicit_terminal_failure
        and not ledger_terminal_failure
    ):
        terminal_failure = False
    actual_provider_status_raw = (
        payload.get("shopaikey_raw_status")
        or payload.get("shopaikey_data_status")
        if str(payload.get("provider_status_payload_source") or "").strip().startswith("shopaikey.data.")
        else None
    )
    if not actual_provider_status_raw:
        actual_provider_status_raw = payload.get("provider_status_raw") or payload.get("nonterminal_provider_status") or payload.get("provider_status") or ""
    if actual_provider_running:
        actual_provider_status_raw = actual_provider_status
    in_progress_stall_threshold = max(
        60,
        _as_int(
            payload.get("in_progress_stall_threshold")
            or payload.get("in_progress_stall_threshold_seconds")
            or os.getenv("VIDEO_PROVIDER_IN_PROGRESS_STALL_SECONDS")
            or os.getenv("PRODUCT_VIDEO_SCENE_RUNNING_WITHOUT_RESULT_GRACE_SECONDS"),
            300,
        ),
    )
    progress_last_changed_source = "elapsed"
    progress_last_changed_at = str(payload.get("provider_progress_last_changed_at") or payload.get("progress_last_changed_at") or "").strip()
    progress_last_changed_elapsed = _as_int(
        payload.get("provider_progress_last_changed_elapsed_seconds")
        or payload.get("progress_last_changed_elapsed_seconds"),
        0,
    )
    if progress_last_changed_elapsed <= 0 and progress_last_changed_at:
        changed_epoch = _parse_time_epoch(progress_last_changed_at)
        if changed_epoch > 0:
            progress_last_changed_elapsed = int(max(0, current_epoch - changed_epoch))
            progress_last_changed_source = "timestamp"
    if progress_last_changed_elapsed <= 0:
        progress_last_changed_elapsed = elapsed if normalized_progress > 0 or actual_provider_running else 0
    provider_progress_stuck = bool(
        actual_provider_running
        and not result_url_present
        and not final_output_ready
        and progress_last_changed_elapsed >= in_progress_stall_threshold
    )
    provider_in_progress_stalled = bool(
        actual_provider_running
        and not result_url_present
        and not final_output_ready
        and elapsed >= in_progress_stall_threshold
        and provider_progress_stuck
    )
    in_progress_stall_decision = ""
    if actual_provider_running and not result_url_present and not final_output_ready:
        if provider_in_progress_stalled:
            in_progress_stall_decision = "fallback_or_fail_after_in_progress_stall"
        elif elapsed >= in_progress_stall_threshold and not provider_progress_stuck:
            in_progress_stall_decision = "progress_changed_recently_continue_polling"
        else:
            in_progress_stall_decision = "under_threshold_continue_polling"
    scene_count_for_public = max(
        _as_int(payload.get("scene_count") or payload.get("scenes_total") or payload.get("scene_tasks_total"), 0),
        len(payload.get("scene_tasks") or []) if isinstance(payload.get("scene_tasks"), list) else 0,
    )
    scene_done_for_public = _as_int(
        payload.get("scene_coverage_count")
        or payload.get("scene_clip_count")
        or payload.get("scene_tasks_completed")
        or payload.get("scenes_done"),
        0,
    )
    raw_progress_fixed_without_scene = bool(
        actual_provider_running
        and scene_count_for_public > 1
        and scene_done_for_public <= 0
        and raw_progress_number not in (None, "")
        and not result_url_present
        and not final_output_ready
        and progress_last_changed_elapsed >= 60
    )
    public_progress_mode = "scene_and_elapsed" if raw_progress_fixed_without_scene else "percent"
    provider_progress_effective, provider_progress_trusted, provider_progress_cap_reason, provider_progress_cap_applied = _provider_progress_effective(
        normalized_progress,
        raw_progress_number=raw_progress_number,
        provider_status=provider_status,
        result_url_present=result_url_present,
        final_output_ready=final_output_ready,
        alive=alive,
    )
    previous_render_progress = max(
        _as_int(payload.get("render_video_progress_percent"), 0),
        _as_int(payload.get("provider_render_progress_percent"), 0),
    )
    render_progress, render_source, render_estimated, render_cap_applied = _render_subprogress(
        normalized_progress=normalized_progress,
        elapsed=elapsed,
        wait_max=wait_max,
        poll_count=poll_count,
        previous_render_progress=previous_render_progress,
        result_url_present=result_url_present,
        final_output_ready=final_output_ready,
        alive=alive,
        provider_status=provider_status,
        provider_progress_trusted=provider_progress_trusted,
    )
    provider_progress_public_suppressed = bool(
        alive
        and not final_output_ready
        and not result_url_present
        and (
            not provider_progress_trusted
            or bool(parser_fields.get("http_200_not_used_as_progress") or payload.get("http_200_not_used_as_progress"))
        )
    )
    if provider_progress_public_suppressed and alive and render_source == "indeterminate":
        render_progress = max(0, min(85, render_progress))
        render_source = "elapsed_provider_wait"
    elapsed_estimate_progress = 0
    public_progress_source = render_source
    public_progress_cap = 85 if alive and not final_output_ready else (95 if not final_delivered else 100)
    if actual_provider_running and alive and not result_url_present and not final_output_ready:
        ratio = min(1.0, max(0.0, float(elapsed) / float(max(1, in_progress_stall_threshold))))
        elapsed_estimate_progress = max(25, min(85, 25 + int(round(ratio * 60))))
        if elapsed_estimate_progress > render_progress:
            render_progress = elapsed_estimate_progress
            public_progress_source = "provider_elapsed_in_progress"
            render_source = "provider_elapsed_in_progress"
    render_progress_public_mode = "elapsed_wait" if provider_progress_public_suppressed and alive else ("zero_waiting" if provider_progress_public_suppressed else "percent")
    render_progress_public_percent = str(render_progress)
    fake_progress_prevention_reason = "untrusted_provider_progress_without_result_url" if provider_progress_public_suppressed else ""
    trusted_render_progress_available = bool(provider_progress_trusted or result_url_present or final_output_ready)
    why_render_bar_stays_zero = (
        "waiting_for_real_elapsed_or_result_url" if provider_progress_public_suppressed and render_progress <= 0 else ""
    )
    status_registry_missing_after_restart = bool(
        payload.get("status_registry_missing_after_restart")
        or payload.get("registry_missing_after_restart")
        or payload.get("recovered_from_db_for_status_debug")
    )
    live_elapsed_sources = {"internal_worker", "worker_poll", "worker", "live_worker", "registry_live", "active_worker"}
    if status_registry_missing_after_restart:
        elapsed_public_mode = "hidden"
    elif poll_count_source in live_elapsed_sources:
        elapsed_public_mode = "live"
    elif estimated_started:
        elapsed_public_mode = "recovered_approx"
    else:
        elapsed_public_mode = "hidden" if provider_progress_public_suppressed else "recovered_approx"
    render_monotonic_applied = bool(render_progress > max(0, _as_int(payload.get("render_video_progress_percent"), 0)) and previous_render_progress)
    overall_progress_from_render = 100 if final_delivered else (95 if final_output_ready else (90 if result_url_present else 20 + int(render_progress * 0.65)))
    if elapsed_estimate_progress and alive and not result_url_present and not final_output_ready:
        overall_progress_from_render = max(overall_progress_from_render, elapsed_estimate_progress)
    if alive and not final_output_ready:
        overall_progress_from_render = min(85, overall_progress_from_render)
    estimated = False
    if alive:
        requested = max(20, min(85, overall_progress_from_render))
        estimated = bool(render_estimated)
        progress_source = "render_subprogress"
    else:
        requested = max(persisted_progress, _as_int(payload.get("provider_progress_percent"), 0))
        progress_source = "persisted"
    final_progress = requested if provider_progress_public_suppressed else max(persisted_progress, requested)
    if alive:
        final_progress = max(20, min(85, final_progress))
    else:
        final_progress = max(0, min(100, final_progress))
    final_status = "failed" if terminal_failure else ("processing" if alive else (persisted_status or "queued"))
    if terminal_failure:
        final_progress = min(85, max(20, final_progress))
    if final_output_ready and not final_delivered and not terminal_failure:
        final_status = "processing"
        final_progress = max(85, min(95, max(final_progress, 95 if result_url_present else 85)))
        progress_source = "final_mp4_waiting_delivery"
    if final_delivered:
        final_status = "completed"
        final_progress = 100
        progress_source = "final_delivered"
    if multiscene_ledger:
        ledger_progress_cap = _as_int(multiscene_ledger.get("public_progress_cap"), 70)
        final_progress = min(
            ledger_progress_cap,
            max(
                final_progress,
                _as_int(multiscene_ledger.get("public_effective_progress"), 0),
            ),
        )
        render_progress = min(
            ledger_progress_cap,
            final_progress,
        )
        render_progress_public_percent = str(render_progress)
        render_source = str(multiscene_ledger.get("render_progress_source") or "scene_ledger_coverage")
        progress_source = "scene_ledger_coverage"
        public_progress_source = (
            "scene_ledger_coverage"
            if _as_int(multiscene_ledger.get("completed_scene_count"), 0) > 0
            else public_progress_source
        )
        public_progress_mode = "scene_and_elapsed" if not final_delivered else "percent"
        public_progress_cap = _as_int(multiscene_ledger.get("public_progress_cap"), 70)
        final_status = "failed" if terminal_failure else ("completed" if final_delivered else "processing")
    telemetry = {
        "provider_task_alive": bool(alive),
        "progress_monotonic_applied": bool(final_progress > requested or final_progress > persisted_progress),
        "previous_progress": persisted_progress,
        "requested_progress": requested,
        "final_progress": final_progress,
        "progress_source": progress_source,
        "provider_progress_raw": raw_progress if raw_progress not in (None, "") else "",
        "provider_progress_source": provider_progress_source,
        "provider_progress_normalized": normalized_progress,
        "provider_progress_trusted": bool(provider_progress_trusted),
        "provider_progress_cap_reason": provider_progress_cap_reason,
        "provider_progress_cap_applied": bool(provider_progress_cap_applied or render_cap_applied),
        "provider_progress_effective": provider_progress_effective,
        "provider_progress_raw_number": raw_progress_number if raw_progress_number is not None else "",
        "provider_progress_estimated": bool(estimated),
        "provider_progress_percent": provider_progress_effective if provider_progress_effective else render_progress,
        "render_video_progress_percent": render_progress,
        "provider_render_progress_percent": render_progress,
        "render_video_progress_percent_public": render_progress_public_percent,
        "provider_progress_public_suppressed": bool(provider_progress_public_suppressed),
        "render_progress_public_mode": render_progress_public_mode,
        "public_zero_bar_due_to_untrusted_provider": bool(provider_progress_public_suppressed and render_progress <= 0),
        "fake_progress_prevented": bool(provider_progress_public_suppressed),
        "fake_progress_prevention_reason": fake_progress_prevention_reason,
        "percent_conservative_due_to_untrusted_provider": bool(provider_progress_public_suppressed),
        "render_progress_source": render_source,
        "elapsed_estimate_progress": elapsed_estimate_progress,
        "public_progress_source": public_progress_source,
        "public_progress_mode": public_progress_mode,
        "public_progress_percent_visible": bool(public_progress_mode != "scene_and_elapsed" or final_delivered),
        "public_progress_cap": public_progress_cap,
        "persisted_progress_updated": bool(final_progress > persisted_progress),
        "in_progress_stall_elapsed": progress_last_changed_elapsed if actual_provider_running else 0,
        "in_progress_stall_threshold": in_progress_stall_threshold,
        "provider_progress_last_changed_at": progress_last_changed_at,
        "provider_progress_last_changed_source": progress_last_changed_source,
        "provider_progress_stuck": bool(provider_progress_stuck),
        "provider_in_progress_stalled": bool(provider_in_progress_stalled),
        "in_progress_stall_decision": in_progress_stall_decision,
        "fallback_due_to_in_progress_stall": bool(provider_in_progress_stalled and payload.get("fallback_allowed")),
        "render_progress_raw_provider": raw_progress if raw_progress not in (None, "") else "",
        "render_progress_estimated": bool(render_estimated),
        "render_progress_cap_applied": bool(render_cap_applied or provider_progress_cap_applied),
        "render_progress_result_url_present": bool(result_url_present),
        "render_progress_monotonic_applied": bool(render_monotonic_applied),
        "overall_progress_from_render": overall_progress_from_render,
        "provider_status_for_progress": provider_status,
        "provider_task_status": provider_status,
        "trusted_render_progress_available": bool(trusted_render_progress_available),
        "why_render_bar_stays_zero": why_render_bar_stays_zero,
        "external_provider_spend_possible": bool(payload.get("provider_submit_called") or payload.get("submit_accepted") or payload.get("provider_task_id_saved") or alive),
        "provider_poll_count": poll_count,
        "provider_poll_count_source": poll_count_source,
        "provider_last_poll_at": payload.get("provider_last_poll_at") or payload.get("last_poll_at") or now_text(current_dt),
        "provider_started_at": payload.get("provider_started_at") or _format_epoch(started_epoch),
        "provider_started_at_epoch": started_epoch,
        "provider_started_at_source": started_source,
        "provider_elapsed_seconds": elapsed,
        "provider_wait_elapsed_seconds": elapsed,
        "scene_not_start_elapsed": scene_not_start_elapsed,
        "not_start_threshold_seconds": not_start_threshold,
        "stall_threshold": not_start_threshold if provider_not_start else _as_int(payload.get("stall_threshold"), 0),
        "provider_stalled_not_start": provider_stalled_not_start,
        "fallback_block_reason": (
            "not_start_under_threshold"
            if provider_not_start and not provider_stalled_not_start
            else (
                "provider_in_progress_stalled"
                if actual_provider_running
                and provider_in_progress_stalled
                and str(payload.get("fallback_block_reason") or payload.get("fallback_blocked_reason") or "") == ""
                else (
                "primary_provider_in_progress"
                if actual_provider_running
                and str(payload.get("fallback_block_reason") or payload.get("fallback_blocked_reason") or "")
                in {"", "not_start_under_threshold", "provider_not_start", "provider_stalled_not_start"}
                else str(payload.get("fallback_block_reason") or payload.get("fallback_blocked_reason") or "")
                )
            )
        ),
        "provider_wait_max_seconds": wait_max,
        "timeout_at": _format_epoch(started_epoch + wait_max) if started_epoch > 0 else "",
        "provider_elapsed_estimated": bool(estimated_started),
        "elapsed_public_mode": elapsed_public_mode,
        "elapsed_public_source": started_source,
        "status_registry_missing_after_restart": bool(status_registry_missing_after_restart),
        "elapsed_wall_clock_seconds": wall_clock_elapsed,
        "previous_elapsed_seconds": previous_elapsed,
        "elapsed_monotonic_applied": bool(elapsed_monotonic_applied),
        "elapsed_display_text": _human_elapsed(elapsed),
        "panel_refresh_interval_seconds": _as_int(payload.get("panel_refresh_interval_seconds"), 25),
        "auto_refresh_interval_seconds": _as_int(
            payload.get("auto_refresh_interval_seconds")
            or payload.get("panel_refresh_interval_seconds")
            or os.getenv("VIDEO_PUBLIC_STATUS_REFRESH_SECONDS"),
            10,
        ),
        "elapsed_live_tick_enabled": True,
        "elapsed_source": "persisted_started_at" if started_source != "now" else "elapsed_field",
        "panel_rendered_at": now_text(current_dt),
        "provider_status_raw": actual_provider_status_raw,
        "provider_status_normalized": provider_status or payload.get("normalized_provider_status") or payload.get("provider_status") or ("running" if alive else ""),
        "actual_provider_payload_status": actual_provider_status,
        "state_authority_source": actual_provider_source,
        "stale_not_start_blocker_ignored": bool(stale_not_start_blocker_ignored),
        "not_start_decision_source": (
            "actual_provider_payload_in_progress"
            if actual_provider_running
            else (
                "actual_provider_payload_not_start"
                if provider_not_start and actual_provider_authoritative
                else ("stale_or_derived_not_start" if provider_not_start else "")
            )
        ),
        "provider_progress_authoritative": bool(actual_provider_running or actual_provider_authoritative),
        "provider_progress_capped_reason": provider_progress_cap_reason or ("capped_before_result_url" if alive and not result_url_present and render_progress >= 85 else ""),
        "no_fake_success_guard": bool(not final_delivered and final_progress < 100),
        "result_url_present": bool(result_url_present),
        "provider_result_url_present": bool(result_url_present),
        "http_200_not_used_as_progress": bool(parser_fields.get("http_200_not_used_as_progress") or payload.get("http_200_not_used_as_progress")),
        "shopaikey_status_endpoint_exact": bool(parser_fields.get("shopaikey_status_endpoint_exact") or payload.get("shopaikey_status_endpoint_exact")),
        "shopaikey_status_http_code": _as_int(parser_fields.get("shopaikey_status_http_code") or payload.get("shopaikey_status_http_code"), 0),
        "shopaikey_raw_status": parser_fields.get("shopaikey_raw_status") or payload.get("shopaikey_raw_status") or "",
        "shopaikey_normalized_status": parser_fields.get("shopaikey_normalized_status") or payload.get("shopaikey_normalized_status") or "",
        "shopaikey_data_progress_raw": parser_fields.get("shopaikey_data_progress_raw") or payload.get("shopaikey_data_progress_raw") or "",
        "shopaikey_progress_source": parser_fields.get("shopaikey_progress_source") or payload.get("shopaikey_progress_source") or "",
        "shopaikey_result_url_from_data": bool(parser_fields.get("shopaikey_result_url_from_data") or payload.get("shopaikey_result_url_from_data")),
        "shopaikey_data_result_url_present": bool(parser_fields.get("shopaikey_data_result_url_present") or payload.get("shopaikey_data_result_url_present")),
        "shopaikey_fail_reason": parser_fields.get("shopaikey_fail_reason") or payload.get("shopaikey_fail_reason") or "",
        "result_url_primary_path_checked": bool(parser_fields.get("result_url_primary_path_checked") or payload.get("result_url_primary_path_checked")),
        "result_url_found": bool(parser_fields.get("result_url_found") or payload.get("result_url_found")),
        "result_url_source_path": parser_fields.get("result_url_source_path") or payload.get("result_url_source_path") or "",
        "next_poll_scheduled": False if terminal_failure else bool(payload.get("next_poll_scheduled") or alive),
        "next_poll_scheduled_at": payload.get("next_poll_scheduled_at") or "",
        "panel_last_updated_at": now_text(current_dt),
        "refresh_source": refresh_source,
        "stage_monotonic_applied": bool(alive),
        "status_source_priority_used": "terminal_failed_no_charge" if terminal_failure else ("provider_task_alive" if alive else "persisted_status"),
        "provider_state_overrode_registry": bool(alive and not terminal_failure),
        "provider_state_overrode_persisted_status": bool(alive and not terminal_failure and persisted_status in {"", "queued", "queued_for_worker", "draft", "failed", "error"}),
        "persisted_status_before_reconcile": persisted_status,
        "persisted_progress_before_reconcile": persisted_progress,
        "final_status_after_reconcile": final_status,
        "terminal_state": "delivered" if final_delivered else ("final_rendering" if alive and not terminal_failure else str(payload.get("terminal_state") or "")),
        "final_user_visible_state": "delivered" if final_delivered else ("final_rendering" if alive and not terminal_failure else ("failed_no_charge" if terminal_failure else final_status)),
        "final_progress_after_reconcile": final_progress,
        "processing_truth_applied": bool(processing_truth),
        "refresh_terminal_suppressed": bool(processing_truth),
        "refresh_state_source": "scene_ledger" if processing_truth else refresh_source,
    }
    if multiscene_ledger:
        telemetry.update(multiscene_ledger)
        telemetry.update(
            {
                "provider_task_alive": bool(alive),
                "final_status_after_reconcile": final_status,
                "final_progress": final_progress,
                "final_progress_after_reconcile": final_progress,
                "public_effective_progress": final_progress,
                "progress_source": "scene_ledger_coverage",
                "public_progress_source": public_progress_source,
                "public_progress_mode": public_progress_mode,
                "public_progress_percent_visible": False if not final_delivered else True,
                "render_video_progress_percent": render_progress,
                "provider_render_progress_percent": render_progress,
                "render_video_progress_percent_public": str(render_progress),
                "render_progress_source": render_source,
                "result_url_present": bool(multiscene_ledger.get("final_mp4_valid")),
                "provider_result_url_present": bool(multiscene_ledger.get("final_mp4_valid")),
                "result_url_found": bool(multiscene_ledger.get("final_mp4_valid")),
                "next_poll_scheduled": bool(alive and not terminal_failure),
                "status_source_priority_used": "scene_ledger_authority",
                "provider_state_overrode_registry": bool(alive),
                "provider_state_overrode_persisted_status": bool(alive and persisted_status in {"", "queued", "queued_for_worker", "draft", "failed", "error"}),
                "final_user_visible_state": "delivered" if final_delivered else ("failed_no_charge" if terminal_failure else "final_rendering"),
                "no_fake_success_guard": bool(not final_delivered),
                "processing_truth_applied": bool(processing_truth),
                "refresh_terminal_suppressed": bool(processing_truth),
                "refresh_state_source": "scene_ledger" if processing_truth else refresh_source,
            }
        )
    if multiscene_ledger.get("zero_task_progress_guard"):
        zero_terminal = bool(multiscene_ledger.get("aggregate_job_status") == "failed_no_charge")
        zero_progress = max(0, min(20, _as_int(multiscene_ledger.get("public_effective_progress"), 10)))
        telemetry.update(
            {
                "provider_task_alive": False,
                "valid_provider_task_count": 0,
                "zero_task_progress_guard": True,
                "progress_suppressed_without_task": True,
                "render_video_progress_percent": 0,
                "provider_render_progress_percent": 0,
                "render_video_progress_percent_public": "0",
                "provider_progress_percent": 0,
                "provider_progress_effective": 0,
                "render_progress_source": "zero_task_waiting_for_dispatch",
                "progress_source": "zero_task_waiting_for_dispatch",
                "public_progress_source": "zero_task_waiting_for_dispatch",
                "public_stage": "failed_no_charge" if zero_terminal else "preparing",
                "final_status_after_reconcile": "failed" if zero_terminal else "processing",
                "final_user_visible_state": "failed_no_charge" if zero_terminal else "preparing",
                "final_progress": zero_progress,
                "final_progress_after_reconcile": zero_progress,
                "public_effective_progress": zero_progress,
                "next_poll_scheduled": bool(multiscene_ledger.get("continue_polling") and not zero_terminal),
                "terminal_state": "failed_no_charge" if zero_terminal else "final_rendering",
                "no_fake_success_guard": True,
                "external_provider_spend_possible": False,
            }
        )
    return telemetry


def _columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _add_column_if_missing(conn: sqlite3.Connection, table_name: str, column_name: str, column_sql: str) -> None:
    if column_name not in _columns(conn, table_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")


def ensure_video_project_queue_schema(conn: sqlite3.Connection) -> None:
    """Create/adapt queue tables without dropping or deleting existing data."""
    caller_transaction_active = bool(conn.in_transaction)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS video_projects (
            project_id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_uuid TEXT UNIQUE,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft_planning',
            profile_id TEXT,
            topic TEXT,
            ratio TEXT DEFAULT '9:16',
            selected_suggestion_json TEXT,
            asset_pack_json TEXT,
            story_bible_json TEXT,
            scene_cards_json TEXT,
            prompt_text TEXT,
            addon_plan_json TEXT,
            creative_control_json TEXT,
            quality_tier INTEGER DEFAULT 200,
            scene_count INTEGER DEFAULT 1,
            addons_disabled_by_package INTEGER DEFAULT 0,
            invoice_json TEXT,
            total_xu_estimated INTEGER DEFAULT 0,
            is_confirmed INTEGER DEFAULT 0,
            job_id INTEGER,
            final_video_file_id TEXT,
            final_video_path TEXT,
            video_delivery_started_at DATETIME,
            video_delivered_at DATETIME,
            video_delivery_message_id TEXT,
            video_success_message_id TEXT,
            video_terminal_state TEXT DEFAULT '',
            video_terminal_locked_at DATETIME,
            video_artifact_hash TEXT DEFAULT '',
            delivery_attempt_count INTEGER DEFAULT 0,
            error_log TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            confirmed_at DATETIME,
            completed_at DATETIME,
            cancelled_at DATETIME
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS video_scenes (
            scene_id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            scene_index INTEGER NOT NULL,
            role TEXT,
            script_text TEXT DEFAULT '',
            subtitle_line TEXT DEFAULT '',
            image_prompt TEXT DEFAULT '',
            video_prompt TEXT DEFAULT '',
            reference_asset_ids_json TEXT,
            image_file_path TEXT DEFAULT '',
            audio_file_path TEXT DEFAULT '',
            video_file_path TEXT DEFAULT '',
            scene_status TEXT DEFAULT 'pending',
            UNIQUE(project_id, scene_index)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS video_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            user_id INTEGER,
            job_type TEXT NOT NULL DEFAULT 'video_render',
            status TEXT NOT NULL DEFAULT 'queued',
            priority INTEGER DEFAULT 100,
            attempts INTEGER DEFAULT 0,
            max_attempts INTEGER DEFAULT 3,
            locked_by TEXT,
            locked_at DATETIME,
            lease_expires_at DATETIME,
            last_error TEXT,
            result_json TEXT,
            progress_percent INTEGER DEFAULT 0,
            progress_message TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            started_at DATETIME,
            completed_at DATETIME
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS video_dispatch_outbox (
            outbox_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL UNIQUE,
            project_id INTEGER NOT NULL,
            scene_indexes_json TEXT NOT NULL DEFAULT '[]',
            owner TEXT NOT NULL DEFAULT 'owner_product_video',
            dispatch_status TEXT NOT NULL DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            available_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            attempt_count INTEGER DEFAULT 0,
            last_attempt_at DATETIME,
            lease_owner TEXT,
            lease_expires_at DATETIME,
            acknowledged_at DATETIME,
            completed_at DATETIME,
            last_error TEXT DEFAULT '',
            terminal_reason TEXT DEFAULT '',
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    for column_name, column_sql in [
        ("project_uuid", "project_uuid TEXT"),
        ("profile_id", "profile_id TEXT"),
        ("topic", "topic TEXT"),
        ("ratio", "ratio TEXT DEFAULT '9:16'"),
        ("selected_suggestion_json", "selected_suggestion_json TEXT"),
        ("asset_pack_json", "asset_pack_json TEXT"),
        ("story_bible_json", "story_bible_json TEXT"),
        ("scene_cards_json", "scene_cards_json TEXT"),
        ("prompt_text", "prompt_text TEXT"),
        ("addon_plan_json", "addon_plan_json TEXT"),
        ("creative_control_json", "creative_control_json TEXT"),
        ("quality_tier", "quality_tier INTEGER DEFAULT 200"),
        ("scene_count", "scene_count INTEGER DEFAULT 1"),
        ("addons_disabled_by_package", "addons_disabled_by_package INTEGER DEFAULT 0"),
        ("invoice_json", "invoice_json TEXT"),
        ("total_xu_estimated", "total_xu_estimated INTEGER DEFAULT 0"),
        ("is_confirmed", "is_confirmed INTEGER DEFAULT 0"),
        ("job_id", "job_id INTEGER"),
        ("final_video_file_id", "final_video_file_id TEXT"),
        ("final_video_path", "final_video_path TEXT"),
        ("video_delivery_started_at", "video_delivery_started_at DATETIME"),
        ("video_delivered_at", "video_delivered_at DATETIME"),
        ("video_delivery_message_id", "video_delivery_message_id TEXT"),
        ("video_success_message_id", "video_success_message_id TEXT"),
        ("video_terminal_state", "video_terminal_state TEXT DEFAULT ''"),
        ("video_terminal_locked_at", "video_terminal_locked_at DATETIME"),
        ("video_artifact_hash", "video_artifact_hash TEXT DEFAULT ''"),
        ("delivery_attempt_count", "delivery_attempt_count INTEGER DEFAULT 0"),
        ("error_log", "error_log TEXT"),
        ("updated_at", "updated_at DATETIME"),
        ("confirmed_at", "confirmed_at DATETIME"),
        ("completed_at", "completed_at DATETIME"),
        ("cancelled_at", "cancelled_at DATETIME"),
    ]:
        _add_column_if_missing(conn, "video_projects", column_name, column_sql)
    for column_name, column_sql in [
        ("role", "role TEXT"),
        ("script_text", "script_text TEXT DEFAULT ''"),
        ("subtitle_line", "subtitle_line TEXT DEFAULT ''"),
        ("image_prompt", "image_prompt TEXT DEFAULT ''"),
        ("video_prompt", "video_prompt TEXT DEFAULT ''"),
        ("reference_asset_ids_json", "reference_asset_ids_json TEXT"),
        ("image_file_path", "image_file_path TEXT DEFAULT ''"),
        ("audio_file_path", "audio_file_path TEXT DEFAULT ''"),
        ("video_file_path", "video_file_path TEXT DEFAULT ''"),
        ("scene_status", "scene_status TEXT DEFAULT 'pending'"),
    ]:
        _add_column_if_missing(conn, "video_scenes", column_name, column_sql)
    for column_name, column_sql in [
        ("project_id", "project_id INTEGER"),
        ("user_id", "user_id INTEGER"),
        ("job_type", "job_type TEXT DEFAULT 'video_render'"),
        ("priority", "priority INTEGER DEFAULT 100"),
        ("attempts", "attempts INTEGER DEFAULT 0"),
        ("max_attempts", "max_attempts INTEGER DEFAULT 3"),
        ("locked_by", "locked_by TEXT"),
        ("locked_at", "locked_at DATETIME"),
        ("lease_expires_at", "lease_expires_at DATETIME"),
        ("last_error", "last_error TEXT"),
        ("result_json", "result_json TEXT"),
        ("progress_percent", "progress_percent INTEGER DEFAULT 0"),
        ("progress_message", "progress_message TEXT DEFAULT ''"),
        ("updated_at", "updated_at DATETIME"),
        ("started_at", "started_at DATETIME"),
        ("completed_at", "completed_at DATETIME"),
    ]:
        _add_column_if_missing(conn, "video_jobs", column_name, column_sql)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video_projects_user_status ON video_projects(user_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video_projects_project_uuid ON video_projects(project_uuid)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video_scenes_project ON video_scenes(project_id, scene_index)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video_jobs_status_priority ON video_jobs(status, priority, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video_jobs_project ON video_jobs(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video_jobs_user ON video_jobs(user_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_video_dispatch_outbox_claim ON video_dispatch_outbox(owner,dispatch_status,available_at,created_at)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video_dispatch_outbox_project ON video_dispatch_outbox(project_id)")
    conn.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_video_jobs_active_render_project
           ON video_jobs(project_id, job_type)
           WHERE project_id IS NOT NULL
             AND job_type='video_render'
             AND status IN ('queued','processing')"""
    )
    if not caller_transaction_active:
        conn.commit()


def _project_from_row(row: sqlite3.Row | tuple | None) -> dict[str, Any]:
    if not row:
        return {}
    keys = [
        "project_id",
        "project_uuid",
        "user_id",
        "status",
        "profile_id",
        "topic",
        "ratio",
        "selected_suggestion_json",
        "asset_pack_json",
        "story_bible_json",
        "scene_cards_json",
        "prompt_text",
        "addon_plan_json",
        "creative_control_json",
        "quality_tier",
        "scene_count",
        "addons_disabled_by_package",
        "invoice_json",
        "total_xu_estimated",
        "is_confirmed",
        "job_id",
        "final_video_file_id",
        "final_video_path",
        "video_delivery_started_at",
        "video_delivered_at",
        "video_delivery_message_id",
        "video_success_message_id",
        "video_terminal_state",
        "video_terminal_locked_at",
        "video_artifact_hash",
        "delivery_attempt_count",
        "error_log",
        "created_at",
        "updated_at",
        "confirmed_at",
        "completed_at",
        "cancelled_at",
    ]
    return {key: row[idx] for idx, key in enumerate(keys) if idx < len(row)}


def _scene_from_row(row: sqlite3.Row | tuple | None) -> dict[str, Any]:
    if not row:
        return {}
    keys = [
        "scene_id",
        "project_id",
        "scene_index",
        "role",
        "script_text",
        "subtitle_line",
        "image_prompt",
        "video_prompt",
        "reference_asset_ids_json",
        "image_file_path",
        "audio_file_path",
        "video_file_path",
        "scene_status",
    ]
    return {key: row[idx] for idx, key in enumerate(keys) if idx < len(row)}


def _job_from_row(row: sqlite3.Row | tuple | None) -> dict[str, Any]:
    if not row:
        return {}
    keys = [
        "id",
        "project_id",
        "user_id",
        "job_type",
        "status",
        "priority",
        "attempts",
        "max_attempts",
        "locked_by",
        "locked_at",
        "lease_expires_at",
        "last_error",
        "result_json",
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
        "progress_percent",
        "progress_message",
    ]
    data = {key: row[idx] for idx, key in enumerate(keys) if idx < len(row)}
    data["job_id"] = data.get("id")
    return data


def _dispatch_outbox_from_row(row: sqlite3.Row | tuple | None) -> dict[str, Any]:
    if not row:
        return {}
    keys = [
        "outbox_id",
        "job_id",
        "project_id",
        "scene_indexes_json",
        "owner",
        "dispatch_status",
        "created_at",
        "available_at",
        "attempt_count",
        "last_attempt_at",
        "lease_owner",
        "lease_expires_at",
        "acknowledged_at",
        "completed_at",
        "last_error",
        "terminal_reason",
        "updated_at",
    ]
    payload = {key: row[index] for index, key in enumerate(keys) if index < len(row)}
    payload["scene_indexes"] = [
        _as_int(item, 0)
        for item in _json_loads(str(payload.get("scene_indexes_json") or "[]"), [])
        if _as_int(item, 0) > 0
    ]
    payload["dispatch_outbox_present"] = True
    payload["dispatch_outbox_status"] = str(payload.get("dispatch_status") or "")
    payload["dispatch_outbox_attempt_count"] = _as_int(payload.get("attempt_count"), 0)
    payload["dispatch_outbox_lease_owner"] = str(payload.get("lease_owner") or "")
    payload["dispatch_outbox_lease_expires_at"] = str(payload.get("lease_expires_at") or "")
    payload["dispatch_outbox_last_error"] = str(payload.get("last_error") or "")
    payload["dispatch_outbox_acknowledged"] = bool(payload.get("acknowledged_at"))
    payload.update(product_video_dispatch_outbox_debug_contract(payload))
    return payload


def product_video_dispatch_outbox_debug_contract(
    outbox: dict[str, Any] | None,
    *,
    diagnostic: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    item = dict(outbox or {})
    truth = dict(diagnostic or {})
    current_dt = product_video_outbox_utc_datetime(now)
    current_epoch = current_dt.replace(tzinfo=timezone.utc).timestamp()
    present = bool(item or truth.get("outbox_exists"))
    status = str(item.get("dispatch_status") or truth.get("outbox_status") or "").strip().lower()
    available_at = str(item.get("available_at") or truth.get("outbox_available_at") or "")
    lease_expires_at = str(item.get("lease_expires_at") or truth.get("outbox_lease_expiry") or "")
    exact_reason = str(truth.get("exact_claim_block_reason") or "").strip()
    if "claimable" in truth:
        claimable = bool(truth.get("claimable"))
    elif not present:
        claimable = False
        exact_reason = exact_reason or "dispatch_outbox_missing"
    elif status in {"completed", "terminal_failed", "cancelled", "acknowledged"}:
        claimable = False
        exact_reason = exact_reason or f"dispatch_outbox_{status}"
    elif status == "leased":
        claimable = _parse_outbox_utc_epoch(lease_expires_at) <= current_epoch
        exact_reason = "" if claimable else "dispatch_outbox_lease_active"
    elif status in {"pending", "retry_wait"}:
        claimable = _parse_outbox_utc_epoch(available_at) <= current_epoch
        exact_reason = "" if claimable else "dispatch_outbox_not_available_yet"
    else:
        claimable = False
        exact_reason = exact_reason or f"dispatch_outbox_status_{status or 'missing'}"
    if status in {"completed", "terminal_failed", "cancelled", "acknowledged"}:
        public_reason = f"dispatch_outbox_{status}"
    elif exact_reason in {"video_job_lease_active", "dispatch_outbox_lease_active"}:
        public_reason = "active_lease"
    else:
        public_reason = exact_reason
    if not claimable and not public_reason:
        public_reason = "dispatch_outbox_not_claimable"
    available_epoch = _parse_outbox_utc_epoch(available_at)
    due = bool(status in {"pending", "retry_wait"} and available_epoch <= current_epoch)
    retry_seconds_remaining = int(max(0, available_epoch - current_epoch)) if available_epoch else 0
    return {
        "dispatch_outbox_present": present,
        "dispatch_outbox_id": _as_int(item.get("outbox_id") or truth.get("outbox_id"), 0),
        "dispatch_outbox_status": status,
        "dispatch_outbox_owner": str(item.get("owner") or truth.get("outbox_owner") or ""),
        "dispatch_outbox_available_at": available_at,
        "dispatch_outbox_available_at_timezone": "UTC",
        "dispatch_outbox_due": due,
        "dispatch_outbox_retry_seconds_remaining": retry_seconds_remaining,
        "dispatch_outbox_attempt_count": _as_int(item.get("attempt_count"), 0),
        "dispatch_claim_attempt_count": _as_int(
            truth.get("dispatch_claim_attempt_count") or item.get("dispatch_claim_attempt_count"),
            0,
        ),
        "dispatch_claim_failure_count": _as_int(
            truth.get("dispatch_claim_failure_count") or item.get("dispatch_claim_failure_count"),
            0,
        ),
        "dispatch_first_due_claim_attempted": bool(
            truth.get("dispatch_first_due_claim_attempted")
            or item.get("dispatch_first_due_claim_attempted")
        ),
        "dispatch_terminal_transition_source": str(
            truth.get("dispatch_terminal_transition_source")
            or item.get("dispatch_terminal_transition_source")
            or ""
        ),
        "dispatch_outbox_retry_count": _as_int(item.get("attempt_count"), 0),
        "dispatch_outbox_retry_reason": str(item.get("last_error") or ""),
        "dispatch_outbox_last_attempt_at": str(item.get("last_attempt_at") or ""),
        "dispatch_outbox_lease_owner": str(item.get("lease_owner") or truth.get("outbox_lease_owner") or ""),
        "dispatch_outbox_lease_expires_at": lease_expires_at,
        "dispatch_outbox_claimable": claimable,
        "dispatch_outbox_claim_block_reason": public_reason,
        "dispatch_outbox_acknowledged_at": str(item.get("acknowledged_at") or ""),
        "dispatch_outbox_last_error": str(item.get("last_error") or ""),
        "dispatch_outbox_terminal_reason": str(item.get("terminal_reason") or ""),
        "dispatch_outbox_exact_claim_block_reason": exact_reason,
    }


def product_video_dispatch_status_authority(
    job: dict[str, Any] | None,
    result: dict[str, Any] | None,
    outbox: dict[str, Any] | None,
) -> dict[str, Any]:
    """Resolve pre-submit Product Video status from durable dispatch truth."""
    job = dict(job or {})
    result = dict(result or {})
    outbox = dict(outbox or {})
    outbox_status = str(outbox.get("dispatch_status") or result.get("dispatch_outbox_status") or "").strip().lower()
    provider_task_alive = bool(
        result.get("provider_task_alive")
        or str(result.get("provider_task_id") or result.get("provider_video_id") or "").strip()
        or any(
            _product_video_scene_task_identity(item)
            for item in (result.get("scene_tasks") or result.get("provider_scene_tasks") or [])
            if isinstance(item, dict)
        )
    )
    delivered = bool(
        result.get("final_delivered")
        or result.get("delivered")
        or result.get("telegram_delivery_succeeded")
        or result.get("video_delivery_message_id")
    )
    job_failed = str(job.get("status") or "").strip().lower() == "failed"
    terminal = bool(
        outbox_status == "terminal_failed"
        or str(result.get("terminal_state") or "").strip().lower() == "failed_no_charge"
        or job_failed
    )
    if delivered:
        canonical = "success"
        public_stage = "delivered"
        source = "final_delivery"
    elif terminal:
        canonical = "failed_no_charge"
        public_stage = "failed_no_charge"
        source = "dispatch_terminal"
    elif provider_task_alive:
        canonical = "processing"
        public_stage = "processing"
        source = "provider_task"
    elif outbox_status in {"leased", "acknowledged"}:
        canonical = "processing"
        public_stage = "processing"
        source = "dispatch_claimed"
    else:
        canonical = "queued"
        public_stage = "preparing"
        source = "dispatch_outbox"
    return {
        "dispatch_status_authority": source,
        "dispatch_canonical_status": canonical,
        "dispatch_public_stage": public_stage,
        "dispatch_status_consistent": not bool(
            canonical == "failed_no_charge"
            and str(result.get("aggregate_status") or "").strip().lower() == "processing_scenes"
        ),
    }


def get_video_project(conn: sqlite3.Connection, project_id: int | None = None, project_uuid: str = "") -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    if project_id:
        row = conn.execute(
            """SELECT project_id,project_uuid,user_id,status,profile_id,topic,ratio,selected_suggestion_json,
                      asset_pack_json,story_bible_json,scene_cards_json,prompt_text,addon_plan_json,creative_control_json,
                      quality_tier,scene_count,addons_disabled_by_package,invoice_json,total_xu_estimated,
                      is_confirmed,job_id,final_video_file_id,final_video_path,
                      video_delivery_started_at,video_delivered_at,video_delivery_message_id,video_success_message_id,
                      video_terminal_state,video_terminal_locked_at,video_artifact_hash,delivery_attempt_count,
                      error_log,created_at,updated_at,
                      confirmed_at,completed_at,cancelled_at
               FROM video_projects WHERE project_id=?""",
            (int(project_id),),
        ).fetchone()
        return _project_from_row(row)
    if project_uuid:
        row = conn.execute(
            """SELECT project_id,project_uuid,user_id,status,profile_id,topic,ratio,selected_suggestion_json,
                      asset_pack_json,story_bible_json,scene_cards_json,prompt_text,addon_plan_json,creative_control_json,
                      quality_tier,scene_count,addons_disabled_by_package,invoice_json,total_xu_estimated,
                      is_confirmed,job_id,final_video_file_id,final_video_path,
                      video_delivery_started_at,video_delivered_at,video_delivery_message_id,video_success_message_id,
                      video_terminal_state,video_terminal_locked_at,video_artifact_hash,delivery_attempt_count,
                      error_log,created_at,updated_at,
                      confirmed_at,completed_at,cancelled_at
               FROM video_projects WHERE project_uuid=?""",
            (str(project_uuid),),
        ).fetchone()
        return _project_from_row(row)
    return {}


def create_video_project(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    profile_id: str = "storytelling",
    topic: str = "",
    ratio: str = "9:16",
    selected_suggestion: dict | None = None,
    asset_pack: dict | None = None,
) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    project_uuid = f"vprj_{uuid.uuid4().hex}"
    now = now_text()
    cursor = conn.execute(
        """INSERT INTO video_projects
           (project_uuid,user_id,status,profile_id,topic,ratio,selected_suggestion_json,asset_pack_json,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            project_uuid,
            int(user_id),
            "draft_planning",
            str(profile_id or "storytelling"),
            str(topic or ""),
            str(ratio or "9:16"),
            _json_dumps(selected_suggestion or {}),
            _json_dumps(asset_pack or {}),
            now,
            now,
        ),
    )
    conn.commit()
    return get_video_project(conn, int(cursor.lastrowid))


PROJECT_UPDATE_FIELDS = {
    "status",
    "profile_id",
    "topic",
    "ratio",
    "selected_suggestion_json",
    "asset_pack_json",
    "story_bible_json",
    "scene_cards_json",
    "prompt_text",
    "addon_plan_json",
    "creative_control_json",
    "quality_tier",
    "scene_count",
    "addons_disabled_by_package",
    "invoice_json",
    "total_xu_estimated",
    "is_confirmed",
    "job_id",
    "final_video_file_id",
    "final_video_path",
    "video_delivery_started_at",
    "video_delivered_at",
    "video_delivery_message_id",
    "video_success_message_id",
    "video_terminal_state",
    "video_terminal_locked_at",
    "video_artifact_hash",
    "delivery_attempt_count",
    "error_log",
    "confirmed_at",
    "completed_at",
    "cancelled_at",
}


def update_video_project(conn: sqlite3.Connection, project_id: int, **fields: Any) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    updates = []
    values: list[Any] = []
    for key, value in fields.items():
        if key not in PROJECT_UPDATE_FIELDS:
            continue
        if key == "status" and value not in PROJECT_STATUSES:
            raise ValueError("invalid_project_status")
        if key.endswith("_json") and not isinstance(value, str):
            value = _json_dumps(value)
        updates.append(f"{key}=?")
        values.append(value)
    updates.append("updated_at=?")
    values.append(now_text())
    values.append(int(project_id))
    conn.execute(f"UPDATE video_projects SET {', '.join(updates)} WHERE project_id=?", values)
    conn.commit()
    return get_video_project(conn, int(project_id))


def advance_video_project_state(conn: sqlite3.Connection, project_id: int, next_status: str, *, strict: bool = True) -> dict[str, Any]:
    project = get_video_project(conn, int(project_id))
    if not project:
        raise ValueError("project_not_found")
    if next_status not in PROJECT_STATUSES:
        raise ValueError("invalid_project_status")
    current = str(project.get("status") or "draft_planning")
    current_index = PROJECT_STATUSES.index(current)
    next_index = PROJECT_STATUSES.index(next_status)
    if strict and next_index != current_index + 1:
        raise ValueError("invalid_project_state_transition")
    if not strict and next_index < current_index and next_status != "cancelled":
        raise ValueError("invalid_project_state_transition")
    return update_video_project(conn, int(project_id), status=next_status)


def handle_video_project_text(conn: sqlite3.Connection, project_id: int, text: str) -> dict[str, Any]:
    project = get_video_project(conn, int(project_id))
    if not project:
        raise ValueError("project_not_found")
    if str(project.get("status") or "") != "draft_prompt":
        return {"ok": False, "changed": False, "project": project}
    updated = update_video_project(conn, int(project_id), prompt_text=str(text or "")[:8000])
    return {"ok": True, "changed": True, "project": updated}


def get_active_video_project(conn: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    row = conn.execute(
        """SELECT project_id,project_uuid,user_id,status,profile_id,topic,ratio,selected_suggestion_json,
                  asset_pack_json,story_bible_json,scene_cards_json,prompt_text,addon_plan_json,creative_control_json,
                  quality_tier,scene_count,addons_disabled_by_package,invoice_json,total_xu_estimated,
                  is_confirmed,job_id,final_video_file_id,final_video_path,
                  video_delivery_started_at,video_delivered_at,video_delivery_message_id,video_success_message_id,
                  video_terminal_state,video_terminal_locked_at,video_artifact_hash,delivery_attempt_count,
                  error_log,created_at,updated_at,
                  confirmed_at,completed_at,cancelled_at
           FROM video_projects
           WHERE user_id=? AND status IN ('draft_planning','draft_assets','draft_prompt','draft_addons','draft_quality','draft_scene_count','draft_invoice','queued_for_worker','processing')
           ORDER BY project_id DESC
           LIMIT 1""",
        (int(user_id),),
    ).fetchone()
    return _project_from_row(row)


def menu_main_keeps_video_draft(conn: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    return {"ok": True, "active_project": get_active_video_project(conn, int(user_id)), "deleted": False}


def save_video_project_storyboard(conn: sqlite3.Connection, project_id: int, storyboard: Any) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    data = storyboard.to_dict() if hasattr(storyboard, "to_dict") else dict(storyboard or {})
    bible = data.get("story_bible") or {}
    cards = list(data.get("scene_cards") or [])
    conn.execute("DELETE FROM video_scenes WHERE project_id=?", (int(project_id),))
    for index, card in enumerate(cards, start=1):
        conn.execute(
            """INSERT OR REPLACE INTO video_scenes
               (project_id,scene_index,role,script_text,subtitle_line,image_prompt,video_prompt,reference_asset_ids_json,scene_status)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                int(project_id),
                int(card.get("scene_index") or index),
                str(card.get("role") or ""),
                str(card.get("narration_line") or card.get("script_text") or ""),
                str(card.get("subtitle_line") or ""),
                str(card.get("image_prompt") or card.get("visual_goal") or ""),
                str(card.get("provider_prompt") or card.get("video_prompt") or ""),
                _json_dumps(card.get("reference_asset_ids") or []),
                "pending",
            ),
        )
    return update_video_project(
        conn,
        int(project_id),
        story_bible_json=bible,
        scene_cards_json=cards,
        scene_count=max(1, len(cards)),
    )


def list_video_project_scenes(conn: sqlite3.Connection, project_id: int) -> list[dict[str, Any]]:
    ensure_video_project_queue_schema(conn)
    rows = conn.execute(
        """SELECT scene_id,project_id,scene_index,role,script_text,subtitle_line,image_prompt,video_prompt,
                  reference_asset_ids_json,image_file_path,audio_file_path,video_file_path,scene_status
           FROM video_scenes WHERE project_id=? ORDER BY scene_index ASC""",
        (int(project_id),),
    ).fetchall()
    return [_scene_from_row(row) for row in rows]


def get_active_video_render_job(conn: sqlite3.Connection, project_id: int) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    row = conn.execute(
        """SELECT id,project_id,user_id,job_type,status,priority,attempts,max_attempts,locked_by,locked_at,
                  lease_expires_at,last_error,result_json,created_at,updated_at,started_at,completed_at,
                  progress_percent,progress_message
           FROM video_jobs
           WHERE project_id=? AND job_type=? AND status IN ('queued','processing')
           ORDER BY id ASC LIMIT 1""",
        (int(project_id), VIDEO_RENDER_JOB_TYPE),
    ).fetchone()
    return _job_from_row(row)


def get_video_render_job(conn: sqlite3.Connection, job_id: int) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    row = conn.execute(
        """SELECT id,project_id,user_id,job_type,status,priority,attempts,max_attempts,locked_by,locked_at,
                  lease_expires_at,last_error,result_json,created_at,updated_at,started_at,completed_at,
                  progress_percent,progress_message
           FROM video_jobs WHERE id=?""",
        (int(job_id),),
    ).fetchone()
    return _job_from_row(row)


def product_video_probation_lock_state(
    conn: sqlite3.Connection,
    *,
    provider_key: str = "",
    current_job_id: int = 0,
    current_project_id: int = 0,
    current_user_id: int = 0,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return the persisted single-probation lock without probing providers."""
    wanted_provider = str(provider_key or "").strip()
    current_dt = now or datetime.now()
    current_epoch = current_dt.timestamp()
    try:
        rows = conn.execute(
            """SELECT id,project_id,user_id,status,result_json,created_at,updated_at,completed_at
                 FROM video_jobs
                WHERE job_type=? AND result_json LIKE ?
                ORDER BY id DESC LIMIT 500""",
            (VIDEO_RENDER_JOB_TYPE, f"%{PRODUCT_VIDEO_PROBATION_ADMISSION_MODE}%"),
        ).fetchall()
    except Exception as exc:
        return {
            "probation_active": False,
            "probation_lock_clear": False,
            "probation_lock_status": "unknown",
            "probation_lock_error": type(exc).__name__,
            "active_probation_job_id": 0,
            "active_probation_provider": "",
            "probation_last_result": "unknown",
            "probation_cooldown_active": False,
        }

    active: dict[str, Any] = {}
    latest_terminal: dict[str, Any] = {}
    for row in rows:
        job_id = int(row["id"] if isinstance(row, sqlite3.Row) else row[0])
        project_id = int(row["project_id"] if isinstance(row, sqlite3.Row) else row[1])
        user_id = int(row["user_id"] if isinstance(row, sqlite3.Row) else row[2])
        status = str(row["status"] if isinstance(row, sqlite3.Row) else row[3])
        raw_payload = row["result_json"] if isinstance(row, sqlite3.Row) else row[4]
        payload = _json_loads(str(raw_payload or ""), {})
        if not isinstance(payload, dict):
            continue
        if str(payload.get("admission_mode") or "") != PRODUCT_VIDEO_PROBATION_ADMISSION_MODE:
            continue
        candidate = str(
            payload.get("probation_candidate_key")
            or payload.get("selected_provider")
            or payload.get("provider")
            or ""
        ).strip()
        if wanted_provider and candidate != wanted_provider:
            continue
        record = {
            "job_id": job_id,
            "project_id": project_id,
            "user_id": user_id,
            "status": status,
            "provider": candidate,
            "probation_result": str(payload.get("probation_result") or "pending"),
            "probation_started_at": str(payload.get("probation_started_at") or ""),
            "probation_terminal_at": str(payload.get("probation_terminal_at") or ""),
            "probation_cooldown_until": str(payload.get("probation_cooldown_until") or ""),
            "probation_lock_expires_at": str(payload.get("probation_lock_expires_at") or ""),
        }
        lock_expiry_epoch = _parse_time_epoch(record["probation_lock_expires_at"])
        lock_expired = bool(lock_expiry_epoch and lock_expiry_epoch <= current_epoch)
        probation_result = str(payload.get("probation_result") or "pending").strip().lower()
        pending_delivery = bool(
            probation_result == "pending"
            and status not in {"failed", "cancelled"}
        )
        if (status in {"queued", "processing"} or pending_delivery) and not lock_expired and not active:
            active = record
        elif (probation_result in {"success", "failed"} or status in {"failed", "cancelled"}) and not latest_terminal:
            latest_terminal = record

    cooldown_until = str(latest_terminal.get("probation_cooldown_until") or "")
    cooldown_epoch = _parse_time_epoch(cooldown_until)
    cooldown_active = bool(cooldown_epoch and cooldown_epoch > current_epoch)
    lock_clear = bool(not active and not cooldown_active)
    active_job_id = int(active.get("job_id") or 0)
    current_job_matches_lock = bool(int(current_job_id or 0) > 0 and active_job_id == int(current_job_id or 0))
    same_project = bool(
        int(current_project_id or 0) > 0
        and int(active.get("project_id") or 0) == int(current_project_id or 0)
    )
    same_user = bool(
        int(current_user_id or 0) > 0
        and int(active.get("user_id") or 0) == int(current_user_id or 0)
    )
    owned_by_other_job = bool(active_job_id > 0 and not current_job_matches_lock)
    clear_for_current_job = bool(lock_clear or current_job_matches_lock)
    return {
        "probation_active": bool(active),
        "probation_lock_clear": lock_clear,
        "probation_lock_clear_for_current_job": clear_for_current_job,
        "probation_lock_status": "clear" if lock_clear else ("active" if active else "cooldown"),
        "active_probation_job_id": active_job_id,
        "probation_lock_owner_job": active_job_id,
        "probation_lock_owner_project": int(active.get("project_id") or 0),
        "probation_lock_owner_user": int(active.get("user_id") or 0),
        "active_probation_provider": str(active.get("provider") or ""),
        "active_probation_started_at": str(active.get("probation_started_at") or ""),
        "probation_lock_expires_at": str(active.get("probation_lock_expires_at") or ""),
        "current_probation_job_id": int(current_job_id or 0),
        "current_job_matches_lock": current_job_matches_lock,
        "current_project_matches_lock": same_project,
        "current_user_matches_lock": same_user,
        "same_job_lock_reentry_allowed": current_job_matches_lock,
        "probation_lock_owned_by_other_job": owned_by_other_job,
        "probation_lock_reject_reason": "probation_lock_owned_by_other_job" if owned_by_other_job else "",
        "probation_last_job_id": int(latest_terminal.get("job_id") or 0),
        "probation_last_provider": str(latest_terminal.get("provider") or ""),
        "probation_last_result": str(latest_terminal.get("probation_result") or "none"),
        "probation_last_terminal_at": str(latest_terminal.get("probation_terminal_at") or ""),
        "probation_cooldown_active": cooldown_active,
        "probation_cooldown_until": cooldown_until,
    }


def get_product_video_dispatch_outbox(
    conn: sqlite3.Connection,
    *,
    job_id: int = 0,
    project_id: int = 0,
) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    where = "job_id=?" if int(job_id or 0) > 0 else "project_id=?"
    value = int(job_id or project_id or 0)
    if value <= 0:
        return {}
    row = conn.execute(
        f"""SELECT outbox_id,job_id,project_id,scene_indexes_json,owner,dispatch_status,
                   created_at,available_at,attempt_count,last_attempt_at,lease_owner,lease_expires_at,
                   acknowledged_at,completed_at,last_error,terminal_reason,updated_at
              FROM video_dispatch_outbox
             WHERE {where}
             ORDER BY outbox_id DESC LIMIT 1""",
        (value,),
    ).fetchone()
    return _dispatch_outbox_from_row(row)


def product_video_dispatch_outbox_diagnostic(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Explain the durable owner-worker claim decision for one Product Video job."""
    ensure_video_project_queue_schema(conn)
    current_dt = product_video_outbox_utc_datetime(now)
    current_epoch = current_dt.replace(tzinfo=timezone.utc).timestamp()
    job = get_video_render_job(conn, int(job_id))
    if not job:
        return {
            "job_id": int(job_id),
            "outbox_exists": False,
            "claimable": False,
            "exact_claim_block_reason": "job_not_found",
            "claim_query_source": "video_dispatch_outbox_join_video_jobs_video_projects",
        }
    project = get_video_project(conn, int(job.get("project_id") or 0))
    if not project:
        return {
            "job_id": int(job_id),
            "project_id": int(job.get("project_id") or 0),
            "outbox_exists": False,
            "claimable": False,
            "exact_claim_block_reason": "project_not_found",
            "claim_query_source": "video_dispatch_outbox_join_video_jobs_video_projects",
        }
    result = _json_loads(str(job.get("result_json") or ""), {})
    if not isinstance(result, dict):
        result = {}
    outbox = get_product_video_dispatch_outbox(conn, job_id=int(job_id))
    route_contract = canonical_product_video_route_contract(project, result)
    job_status = str(job.get("status") or "").strip().lower()
    project_status = str(project.get("status") or "").strip().lower()
    outbox_status = str(outbox.get("dispatch_status") or "").strip().lower()
    available_at = str(outbox.get("available_at") or "")
    lease_expiry = str(outbox.get("lease_expires_at") or "")
    available_epoch = _parse_outbox_utc_epoch(available_at)
    lease_expiry_epoch = _parse_outbox_utc_epoch(lease_expiry)
    job_lease_expiry = _parse_time_epoch(job.get("lease_expires_at"))
    job_active_lease = bool(
        job_status == "processing"
        and str(job.get("locked_by") or "").strip()
        and job_lease_expiry > current_epoch
    )
    reason = ""
    if not _is_product_video_project(project):
        reason = "not_product_video_project"
    elif job_status not in {"queued", "processing"}:
        reason = f"job_status_{job_status or 'missing'}"
    elif _as_int(project.get("is_confirmed"), 0) != 1:
        reason = "project_not_confirmed"
    elif project_status not in {"queued_for_worker", "processing"}:
        reason = f"project_status_{project_status or 'missing'}"
    elif not outbox:
        reason = "dispatch_outbox_missing"
    elif str(outbox.get("owner") or "") != PRODUCT_VIDEO_DISPATCH_OUTBOX_OWNER:
        reason = "dispatch_outbox_owner_mismatch"
    elif job_active_lease:
        reason = "video_job_lease_active"
    elif outbox_status in {"terminal_failed", "completed", "cancelled"}:
        reason = f"dispatch_outbox_{outbox_status}"
    elif outbox_status == "acknowledged":
        reason = "dispatch_outbox_already_acknowledged"
    elif outbox_status == "leased" and lease_expiry_epoch > current_epoch:
        reason = "dispatch_outbox_lease_active"
    elif outbox_status in {"pending", "retry_wait"} and available_epoch > current_epoch:
        reason = "dispatch_outbox_not_available_yet"
    elif outbox_status not in {"pending", "retry_wait", "leased"}:
        reason = f"dispatch_outbox_status_{outbox_status or 'missing'}"
    claimable = not bool(reason)
    watchdog = product_video_zero_task_watchdog_state(job, result, now=current_dt)
    diagnostic = {
        "job_id": int(job_id),
        "project_id": int(project.get("project_id") or 0),
        "job_status": job_status,
        "project_status": project_status,
        "project_confirmed": _as_int(project.get("is_confirmed"), 0) == 1,
        "outbox_exists": bool(outbox),
        "outbox_id": _as_int(outbox.get("outbox_id"), 0),
        "outbox_status": outbox_status,
        "outbox_owner": str(outbox.get("owner") or ""),
        "outbox_available_at": available_at,
        "outbox_lease_owner": str(outbox.get("lease_owner") or ""),
        "outbox_lease_expiry": lease_expiry,
        "job_lease_owner": str(job.get("locked_by") or ""),
        "job_lease_expiry": str(job.get("lease_expires_at") or ""),
        "job_active_lease": job_active_lease,
        "claimable": claimable,
        "exact_claim_block_reason": reason,
        "claim_query_source": "video_dispatch_outbox_join_video_jobs_video_projects",
        "claim_allowed_job_statuses": ["queued", "processing"],
        "claim_allowed_outbox_states": ["pending", "retry_wait", "expired_lease"],
        "claim_owner_filter": PRODUCT_VIDEO_DISPATCH_OUTBOX_OWNER,
        "claim_job_age_filter": "none",
        "claim_zero_task_filter": "watchdog_recovery_before_claim",
        "valid_provider_task_count": _as_int(watchdog.get("valid_provider_task_count"), 0),
        "valid_scene_clip_count": _as_int(watchdog.get("valid_scene_clip_count"), 0),
        "zero_task_watchdog_triggered": bool(watchdog.get("zero_task_watchdog_triggered")),
        "dispatch_claim_attempt_count": _as_int(result.get("dispatch_claim_attempt_count"), 0),
        "dispatch_claim_failure_count": _as_int(result.get("dispatch_claim_failure_count"), 0),
        "dispatch_first_due_claim_attempted": bool(result.get("dispatch_first_due_claim_attempted")),
        "dispatch_terminal_transition_source": str(result.get("dispatch_terminal_transition_source") or ""),
        **route_contract,
    }
    diagnostic.update(product_video_dispatch_status_authority(job, result, outbox))
    diagnostic.update(
        product_video_dispatch_outbox_debug_contract(
            outbox,
            diagnostic=diagnostic,
            now=current_dt,
        )
    )
    return diagnostic


def _insert_product_video_dispatch_outbox_record(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    project_id: int,
    scene_indexes: list[int],
    available_at: str,
    owner: str = PRODUCT_VIDEO_DISPATCH_OUTBOX_OWNER,
) -> int:
    cursor = conn.execute(
        """INSERT INTO video_dispatch_outbox
           (job_id,project_id,scene_indexes_json,owner,dispatch_status,created_at,available_at,attempt_count,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            int(job_id),
            int(project_id),
            _json_dumps([int(item) for item in scene_indexes if int(item) > 0]),
            str(owner or PRODUCT_VIDEO_DISPATCH_OUTBOX_OWNER),
            "pending",
            str(available_at),
            str(available_at),
            0,
            str(available_at),
        ),
    )
    return int(cursor.lastrowid or 0)


def ensure_product_video_dispatch_outbox(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    project_id: int,
    scene_indexes: list[int],
    now: datetime | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    existing = get_product_video_dispatch_outbox(conn, job_id=int(job_id))
    if existing:
        return {**existing, "dispatch_outbox_created": False}
    current = product_video_outbox_time_text(now)
    try:
        _insert_product_video_dispatch_outbox_record(
            conn,
            job_id=int(job_id),
            project_id=int(project_id),
            scene_indexes=scene_indexes,
            available_at=current,
        )
        if commit:
            conn.commit()
    except sqlite3.IntegrityError:
        if commit:
            conn.rollback()
    outbox = get_product_video_dispatch_outbox(conn, job_id=int(job_id))
    return {**outbox, "dispatch_outbox_created": bool(outbox and not existing)}


def claim_product_video_dispatch_outbox(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    lease_seconds: int = 600,
    now: datetime | None = None,
) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    input_dt = now or datetime.now()
    current_dt = product_video_outbox_utc_datetime(input_dt)
    job_current = now_text(input_dt)
    current = product_video_outbox_time_text(input_dt)
    expires = product_video_outbox_time_text(input_dt + timedelta(seconds=max(30, int(lease_seconds or 600))))
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """SELECT o.outbox_id,o.job_id,o.project_id,o.scene_indexes_json,o.owner,o.dispatch_status,
                      o.created_at,o.available_at,o.attempt_count,o.last_attempt_at,o.lease_owner,o.lease_expires_at,
                      o.acknowledged_at,o.completed_at,o.last_error,o.terminal_reason,o.updated_at
                 FROM video_dispatch_outbox o
                 JOIN video_jobs j ON j.id=o.job_id
                 JOIN video_projects p ON p.project_id=o.project_id
                WHERE o.owner=?
                  AND j.status IN ('queued','processing')
                  AND (
                       j.status='queued'
                       OR COALESCE(j.locked_by,'')=''
                       OR j.lease_expires_at IS NULL
                       OR j.lease_expires_at<?
                  )
                  AND COALESCE(p.is_confirmed,0)=1
                  AND p.status IN ('queued_for_worker','processing')
                  AND (
                       (o.dispatch_status IN ('pending','retry_wait') AND COALESCE(o.available_at,'')<=?)
                       OR (o.dispatch_status='leased' AND COALESCE(o.lease_expires_at,'')<?)
                  )
                ORDER BY o.available_at ASC,o.created_at ASC,o.outbox_id ASC
                LIMIT 1""",
            (PRODUCT_VIDEO_DISPATCH_OUTBOX_OWNER, job_current, current, current),
        ).fetchone()
        if not row:
            conn.commit()
            return {}
        outbox = _dispatch_outbox_from_row(row)
        stale_recovered = bool(
            str(outbox.get("dispatch_status") or "") == "leased"
            and _parse_outbox_utc_epoch(outbox.get("lease_expires_at"))
            <= current_dt.replace(tzinfo=timezone.utc).timestamp()
        )
        cursor = conn.execute(
            """UPDATE video_dispatch_outbox
                  SET dispatch_status='leased',attempt_count=COALESCE(attempt_count,0)+1,
                      last_attempt_at=?,lease_owner=?,lease_expires_at=?,updated_at=?
                WHERE outbox_id=?
                  AND (
                       dispatch_status IN ('pending','retry_wait')
                       OR (dispatch_status='leased' AND COALESCE(lease_expires_at,'')<?)
                  )""",
            (current, str(worker_id or "")[:120], expires, current, int(outbox["outbox_id"]), current),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return {}
        conn.commit()
        claimed = get_product_video_dispatch_outbox(conn, job_id=int(outbox["job_id"]))
        return {
            **claimed,
            "worker_scan_seen_outbox": True,
            "worker_claim_attempted": True,
            "worker_claim_result": "dispatch_outbox_leased",
            "worker_claim_block_reason": "",
            "stale_dispatch_lease_recovered": stale_recovered,
        }
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


def acknowledge_product_video_dispatch_outbox(
    conn: sqlite3.Connection,
    *,
    outbox_id: int,
    worker_id: str,
    now: datetime | None = None,
    commit: bool = True,
) -> bool:
    current = product_video_outbox_time_text(now)
    cursor = conn.execute(
        """UPDATE video_dispatch_outbox
              SET dispatch_status='acknowledged',acknowledged_at=COALESCE(acknowledged_at,?),updated_at=?
            WHERE outbox_id=? AND dispatch_status='leased' AND lease_owner=?""",
        (current, current, int(outbox_id), str(worker_id or "")[:120]),
    )
    if commit:
        conn.commit()
    return cursor.rowcount == 1


def retry_product_video_dispatch_outbox(
    conn: sqlite3.Connection,
    *,
    outbox_id: int,
    worker_id: str,
    error: str,
    retry_seconds: int = 15,
    now: datetime | None = None,
) -> bool:
    current_dt = product_video_outbox_utc_datetime(now)
    current = product_video_outbox_time_text(current_dt)
    previous = conn.execute(
        """SELECT o.available_at,o.last_error,o.attempt_count,o.job_id,o.project_id,
                  j.max_attempts,j.result_json,o.dispatch_status,o.lease_owner,o.last_attempt_at
             FROM video_dispatch_outbox o
             JOIN video_jobs j ON j.id=o.job_id
            WHERE o.outbox_id=?""",
        (int(outbox_id),),
    ).fetchone()
    previous_available = str((previous[0] if previous else "") or "")
    previous_error = str((previous[1] if previous else "") or "")
    normalized_error = str(error or "dispatch_claim_failed")[:500]
    attempt_count = _as_int(previous[2] if previous else 0, 0)
    max_attempts = max(1, _as_int(previous[5] if previous else 3, 3))
    previous_result = _json_loads(str((previous[6] if previous else "") or ""), {})
    if not isinstance(previous_result, dict):
        previous_result = {}
    outbox_status = str((previous[7] if previous else "") or "").strip().lower()
    lease_owner = str((previous[8] if previous else "") or "").strip()
    lease_claim_recorded = bool(
        previous
        and outbox_status == "leased"
        and lease_owner == str(worker_id or "")[:120]
        and attempt_count > 0
    )
    recorded_failure_count = max(
        _as_int(previous_result.get("dispatch_claim_failure_count"), 0),
        max(0, attempt_count - 1) if lease_claim_recorded else 0,
    )
    claim_failure_count = recorded_failure_count + (1 if lease_claim_recorded else 0)
    claim_attempt_count = max(
        _as_int(previous_result.get("dispatch_claim_attempt_count"), 0),
        attempt_count if lease_claim_recorded else 0,
    )
    has_provider_task = bool(
        str(previous_result.get("provider_task_id") or previous_result.get("provider_video_id") or "").strip()
        or any(
            _product_video_scene_task_identity(item)
            for item in (previous_result.get("scene_tasks") or previous_result.get("provider_scene_tasks") or [])
            if isinstance(item, dict)
        )
    )
    previous_result.update(
        {
            "dispatch_claim_attempt_count": claim_attempt_count,
            "dispatch_claim_failure_count": claim_failure_count,
            "dispatch_first_due_claim_attempted": bool(claim_attempt_count > 0),
            "dispatch_last_claim_failure_reason": normalized_error if lease_claim_recorded else "",
            "dispatch_last_claim_failure_at": current if lease_claim_recorded else "",
            "dispatch_retry_exhausted": bool(
                lease_claim_recorded and claim_failure_count >= max_attempts
            ),
            "dispatch_outbox_retry_reason": normalized_error,
            "dispatch_outbox_retry_count": claim_failure_count,
        }
    )
    if (
        previous
        and lease_claim_recorded
        and claim_failure_count >= max_attempts
        and not has_provider_task
    ):
        terminal_reason = f"dispatch_not_started_{normalized_error}"
        previous_result.update(
            {
                "terminal_state": "failed_no_charge",
                "final_decision": "failed_no_charge",
                "canonical_status": "failed_no_charge",
                "continue_polling": False,
                "next_poll_scheduled": False,
                "dispatch_outbox_status": "terminal_failed",
                "dispatch_outbox_terminal_reason": terminal_reason,
                "provider_submit_called": False,
                "provider_http_request_sent": False,
                "provider_router_called": False,
                "router_skip_reason": normalized_error,
                "provider_submit_allowed": False,
                "provider_submit_block_reason": terminal_reason,
                "dispatch_terminal_transition_source": "dispatch_claim_retry_exhausted",
                "dispatch_terminal_failure_reason": terminal_reason,
                "charge": 0,
                "charged_xu": 0,
            }
        )
        conn.execute(
            """UPDATE video_jobs
                  SET status='failed',result_json=?,last_error=?,progress_percent=0,
                      progress_message=?,completed_at=COALESCE(completed_at,?),updated_at=?
                WHERE id=?""",
            (_json_dumps(previous_result), terminal_reason, terminal_reason, current, current, int(previous[3])),
        )
        conn.execute(
            """UPDATE video_projects
                  SET status='failed',video_terminal_state='failed_no_charge',error_log=?,updated_at=?
                WHERE project_id=?""",
            (terminal_reason, current, int(previous[4])),
        )
        conn.execute(
            """UPDATE video_dispatch_outbox
                  SET dispatch_status='terminal_failed',terminal_reason=?,last_error=?,
                      lease_owner='',lease_expires_at=NULL,updated_at=?
                WHERE outbox_id=?""",
            (terminal_reason, normalized_error, current, int(outbox_id)),
        )
        conn.execute(
            "UPDATE video_scenes SET scene_status='terminal_failed' WHERE project_id=?",
            (int(previous[4]),),
        )
        conn.commit()
        return True
    repeated_without_new_failure = bool(previous_error and previous_error == normalized_error)
    available = (
        previous_available
        if repeated_without_new_failure and previous_available
        else product_video_outbox_time_text(current_dt + timedelta(seconds=max(1, int(retry_seconds or 15))))
    )
    cursor = conn.execute(
        """UPDATE video_dispatch_outbox
              SET dispatch_status='retry_wait',available_at=?,last_error=?,lease_owner='',lease_expires_at=NULL,updated_at=?
            WHERE outbox_id=? AND dispatch_status='leased' AND lease_owner=?""",
        (
            available,
            normalized_error,
            current,
            int(outbox_id),
            str(worker_id or "")[:120],
        ),
    )
    if cursor.rowcount == 1 and previous and not has_provider_task:
        scene_count = max(
            1,
            _as_int(
                previous_result.get("scene_count")
                or previous_result.get("scenes_total")
                or previous_result.get("scene_tasks_total"),
                1,
            ),
        )
        scene_tasks: list[dict[str, Any]] = []
        for offset, item in enumerate(previous_result.get("scene_tasks") or [], start=1):
            if not isinstance(item, dict):
                continue
            row = dict(item)
            if not _product_video_scene_task_identity(row):
                row.update(
                    {
                        "scene_index": max(1, _as_int(row.get("scene_index"), offset)),
                        "status": "queued_waiting_for_dispatch",
                        "current_scene_status": "queued_waiting_for_dispatch",
                        "continue_polling": True,
                    }
                )
            scene_tasks.append(row)
        previous_result.update(
            {
                "status": "queued",
                "canonical_status": "queued_waiting_for_dispatch",
                "terminal_state": "",
                "final_decision": "continue_polling",
                "terminal": False,
                "continue_polling": True,
                "next_poll_scheduled": True,
                "dispatch_outbox_status": "retry_wait",
                "dispatch_outbox_available_at": available,
                "dispatch_outbox_claimable": False,
                "dispatch_outbox_claim_block_reason": "outbox_not_due",
                "provider_router_called": False,
                "router_skip_reason": f"outbox_not_claimable_{normalized_error}",
                "scene_status_by_scene": {
                    str(index): "queued_waiting_for_dispatch"
                    for index in range(1, scene_count + 1)
                },
                "scene_tasks": scene_tasks,
                "charge": 0,
                "charged_xu": 0,
            }
        )
        conn.execute(
            """UPDATE video_jobs
                  SET status='queued',result_json=?,last_error=?,progress_percent=10,
                      progress_message='queued_waiting_for_dispatch',locked_by='',locked_at=NULL,
                      lease_expires_at=NULL,completed_at=NULL,updated_at=?
                WHERE id=?""",
            (_json_dumps(previous_result), normalized_error, current, int(previous[3])),
        )
        conn.execute(
            """UPDATE video_projects
                  SET status='queued_for_worker',video_terminal_state='',error_log='',updated_at=?
                WHERE project_id=?""",
            (current, int(previous[4])),
        )
        conn.execute(
            "UPDATE video_scenes SET scene_status='pending' WHERE project_id=? AND scene_status!='done'",
            (int(previous[4]),),
        )
    conn.commit()
    return cursor.rowcount == 1


def product_video_premature_dispatch_failure_state(
    job: dict[str, Any] | None,
    project: dict[str, Any] | None,
    result: dict[str, Any] | None,
    outbox: dict[str, Any] | None,
    *,
    worker_compatible: bool = True,
) -> dict[str, Any]:
    """Classify the narrow no-submit terminal failure that may be reopened once."""
    job = dict(job or {})
    project = dict(project or {})
    result = dict(result or {})
    outbox = dict(outbox or {})
    reason = str(
        result.get("dispatch_terminal_failure_reason")
        or result.get("dispatch_outbox_terminal_reason")
        or outbox.get("terminal_reason")
        or job.get("last_error")
        or project.get("error_log")
        or ""
    ).strip()
    submit_source = str(
        result.get("submit_source")
        or result.get("provider_submit_source")
        or result.get("original_submit_source")
        or ""
    ).strip()
    public_confirmed = bool(
        result.get("public_user_confirmed")
        or result.get("user_final_confirmed")
        or result.get("invoice_confirmed")
    )
    scene_tasks = [
        dict(item)
        for item in (result.get("scene_tasks") or result.get("provider_scene_tasks") or [])
        if isinstance(item, dict)
    ]
    provider_task_exists = bool(
        str(result.get("provider_task_id") or result.get("provider_video_id") or "").strip()
        or any(_product_video_scene_task_identity(item) for item in scene_tasks)
    )
    provider_attempted = bool(
        result.get("provider_submit_called")
        or result.get("provider_http_request_sent")
        or _as_int(result.get("provider_http_status"), 0) > 0
        or any(
            bool(item.get("provider_http_request_sent"))
            or _as_int(item.get("provider_http_status") or item.get("submit_http_status"), 0) > 0
            for item in (result.get("provider_attempts") or [])
            if isinstance(item, dict)
        )
    )
    charged = bool(
        _as_int(result.get("charged_xu") or result.get("charge"), 0) > 0
        or result.get("wallet_charge_recorded")
    )
    recoverable_reason = bool(reason in PRODUCT_VIDEO_PREMATURE_DISPATCH_FAILURE_REASONS)
    already_recovered = bool(result.get("premature_dispatch_recovery_used"))
    automatic_retry_forbidden = bool(
        (
            result.get("product_video_durable_public_seam")
            or isinstance(result.get("product_video_route_decision"), dict)
        )
        and result.get("automatic_retry_allowed") is False
    )
    recoverable = bool(
        str(job.get("status") or "").strip().lower() == "failed"
        and str(outbox.get("dispatch_status") or "").strip().lower() == "terminal_failed"
        and submit_source == "public_user_final_confirm"
        and public_confirmed
        and worker_compatible
        and recoverable_reason
        and not provider_attempted
        and not provider_task_exists
        and not charged
        and not already_recovered
        and not automatic_retry_forbidden
    )
    return {
        "premature_dispatch_failure_recoverable": recoverable,
        "premature_dispatch_failure_reason": reason,
        "premature_dispatch_failure_reason_allowed": recoverable_reason,
        "premature_dispatch_recovery_used": already_recovered,
        "premature_dispatch_automatic_retry_forbidden": automatic_retry_forbidden,
        "premature_dispatch_public_confirmed": public_confirmed,
        "premature_dispatch_worker_compatible": bool(worker_compatible),
        "premature_dispatch_provider_attempted": provider_attempted,
        "premature_dispatch_provider_task_exists": provider_task_exists,
        "premature_dispatch_charge_recorded": charged,
        "premature_dispatch_recovery_block_reason": "" if recoverable else (
            "automatic_retry_forbidden"
            if automatic_retry_forbidden
            else "recovery_already_used"
            if already_recovered
            else "genuine_provider_terminal_failure"
            if provider_attempted or provider_task_exists
            else "wallet_charge_already_recorded"
            if charged
            else "worker_incompatible"
            if not worker_compatible
            else "failure_reason_not_recoverable"
            if not recoverable_reason
            else "public_final_confirm_missing"
        ),
    }


def recover_product_video_premature_dispatch_failure(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    now: datetime | None = None,
    worker_compatible: bool = True,
) -> dict[str, Any]:
    """Reopen one historical pre-router failure without creating a provider task."""
    ensure_video_project_queue_schema(conn)
    job = get_video_render_job(conn, int(job_id))
    project = get_video_project(conn, int(job.get("project_id") or 0)) if job else {}
    result = _json_loads(str(job.get("result_json") or ""), {}) if job else {}
    if not isinstance(result, dict):
        result = {}
    outbox = get_product_video_dispatch_outbox(conn, job_id=int(job_id))
    state = product_video_premature_dispatch_failure_state(
        job,
        project,
        result,
        outbox,
        worker_compatible=worker_compatible,
    )
    if not state.get("premature_dispatch_failure_recoverable"):
        return {**state, "premature_dispatch_recovered": False}
    current = product_video_outbox_time_text(now)
    scene_count = max(
        1,
        _as_int(result.get("scene_count") or result.get("scenes_total") or project.get("scene_count"), 1),
    )
    scene_tasks: list[dict[str, Any]] = []
    for offset, item in enumerate(result.get("scene_tasks") or [], start=1):
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row.update(
            {
                "scene_index": max(1, _as_int(row.get("scene_index"), offset)),
                "status": "queued_waiting_for_dispatch",
                "current_scene_status": "queued_waiting_for_dispatch",
                "continue_polling": True,
                "next_poll_at": "",
            }
        )
        scene_tasks.append(row)
    original_reason = str(state.get("premature_dispatch_failure_reason") or "")
    result.update(
        {
            "status": "queued",
            "canonical_status": "queued_waiting_for_dispatch",
            "terminal_state": "",
            "final_decision": "continue_polling",
            "terminal": False,
            "continue_polling": True,
            "next_poll_scheduled": True,
            "dispatch_outbox_status": "retry_wait",
            "dispatch_outbox_available_at": current,
            "dispatch_outbox_due": True,
            "dispatch_outbox_claimable": True,
            "dispatch_outbox_claim_block_reason": "",
            "dispatch_claim_attempt_count_before_recovery": _as_int(
                result.get("dispatch_claim_attempt_count") or outbox.get("attempt_count"),
                0,
            ),
            "dispatch_claim_attempt_count": 0,
            "dispatch_claim_failure_count": 0,
            "dispatch_retry_exhausted": False,
            "dispatch_terminal_transition_source": "",
            "dispatch_terminal_failure_reason": "",
            "premature_dispatch_recovery_used": True,
            "premature_dispatch_recovery_count": 1,
            "premature_dispatch_recovered_at": current,
            "premature_dispatch_recovered_reason": original_reason,
            "premature_dispatch_recovery_source": "zero_task_watchdog_before_claim",
            "provider_submit_allowed": False,
            "provider_submit_block_reason": "outbox_due_awaiting_claim",
            "provider_router_called": False,
            "router_skip_reason": "outbox_due_awaiting_claim",
            "worker_claim_result": "premature_terminal_recovered_for_due_claim",
            "worker_claim_block_reason": "",
            "scene_status_by_scene": {
                str(index): "queued_waiting_for_dispatch"
                for index in range(1, scene_count + 1)
            },
            "scene_tasks": scene_tasks,
            "charge": 0,
            "charged_xu": 0,
            "wallet_charge_recorded": False,
        }
    )
    claimed_recovery = conn.execute(
        """UPDATE video_jobs
              SET status='queued',result_json=?,last_error='',progress_percent=10,
                  progress_message='queued_waiting_for_dispatch',locked_by='',locked_at=NULL,
                  lease_expires_at=NULL,completed_at=NULL,updated_at=?
            WHERE id=? AND status='failed'""",
        (_json_dumps(result), current, int(job_id)),
    )
    if claimed_recovery.rowcount != 1:
        conn.commit()
        return {
            **state,
            "premature_dispatch_recovered": False,
            "premature_dispatch_recovery_block_reason": "recovery_claim_lost",
        }
    conn.execute(
        """UPDATE video_projects
              SET status='queued_for_worker',video_terminal_state='',video_terminal_locked_at=NULL,
                  error_log='',completed_at=NULL,updated_at=?
            WHERE project_id=?""",
        (current, int(project.get("project_id") or 0)),
    )
    conn.execute(
        """UPDATE video_dispatch_outbox
              SET dispatch_status='retry_wait',available_at=?,attempt_count=0,last_attempt_at=NULL,
                  lease_owner='',lease_expires_at=NULL,acknowledged_at=NULL,completed_at=NULL,
                  last_error='premature_dispatch_failure_recovered',terminal_reason='',updated_at=?
            WHERE outbox_id=? AND dispatch_status='terminal_failed'""",
        (current, current, int(outbox.get("outbox_id") or 0)),
    )
    conn.execute(
        "UPDATE video_scenes SET scene_status='pending' WHERE project_id=? AND scene_status!='done'",
        (int(project.get("project_id") or 0),),
    )
    conn.commit()
    recovered_job = get_video_render_job(conn, int(job_id))
    recovered_outbox = get_product_video_dispatch_outbox(conn, job_id=int(job_id))
    return {
        **state,
        "premature_dispatch_recovered": True,
        "job_status_after_recovery": str(recovered_job.get("status") or ""),
        "outbox_status_after_recovery": str(recovered_outbox.get("dispatch_status") or ""),
        "outbox_id": _as_int(recovered_outbox.get("outbox_id"), 0),
    }


def enqueue_video_render_job(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    user_id: int,
    priority: int = 100,
    max_attempts: int = 3,
) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    active = get_active_video_render_job(conn, int(project_id))
    if active:
        return {**active, "duplicate_prevented": True}
    now = now_text()
    try:
        cursor = conn.execute(
            """INSERT INTO video_jobs
               (project_id,user_id,job_type,status,priority,attempts,max_attempts,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (int(project_id), int(user_id), VIDEO_RENDER_JOB_TYPE, "queued", int(priority), 0, int(max_attempts), now, now),
        )
        conn.commit()
        job = get_video_render_job(conn, int(cursor.lastrowid))
        return {**job, "duplicate_prevented": False}
    except sqlite3.IntegrityError:
        conn.rollback()
        active = get_active_video_render_job(conn, int(project_id))
        if active:
            return {**active, "duplicate_prevented": True}
        raise


def begin_video_precheck_job(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    user_id: int,
    chat_id: int,
    request_id: str,
    confirm_attempt_key: str,
) -> dict[str, Any]:
    """Create or resume one durable job without making it worker-claimable."""

    ensure_video_project_queue_schema(conn)
    project = get_video_project(conn, int(project_id))
    if not project:
        raise ValueError("project_not_found")
    if int(project.get("user_id") or 0) != int(user_id):
        raise PermissionError("project_user_mismatch")

    linked_job_id = _as_int(project.get("job_id"), 0)
    if linked_job_id > 0:
        linked_job = get_video_render_job(conn, linked_job_id)
        if (
            linked_job
            and int(linked_job.get("project_id") or 0) == int(project_id)
            and int(linked_job.get("user_id") or 0) == int(user_id)
        ):
            return {**linked_job, "duplicate_prevented": True}

    existing_row = conn.execute(
        """SELECT id,project_id,user_id,job_type,status,priority,attempts,max_attempts,
                  locked_by,locked_at,lease_expires_at,last_error,result_json,created_at,
                  updated_at,started_at,completed_at,progress_percent,progress_message
             FROM video_jobs
            WHERE project_id=? AND user_id=? AND job_type=?
            ORDER BY id ASC LIMIT 1""",
        (int(project_id), int(user_id), VIDEO_RENDER_JOB_TYPE),
    ).fetchone()
    existing_job = _job_from_row(existing_row)
    if existing_job:
        conn.execute(
            "UPDATE video_projects SET job_id=?,updated_at=? WHERE project_id=? AND user_id=?",
            (int(existing_job["id"]), now_text(), int(project_id), int(user_id)),
        )
        return {**existing_job, "duplicate_prevented": True}

    current = now_text()
    result_payload = {
        "request_id": str(request_id),
        "confirm_attempt_key": str(confirm_attempt_key),
        "chat_id": int(chat_id or 0),
        "preflight_result": "RUNNING",
        "admission_result": "NOT_RUN",
        "exact_blocker_code": "",
        "provider_task_id": None,
        "submit_count": 0,
        "poll_count": 0,
        "charge_count": 0,
        "charge_state": "NO_CHARGE",
        "dispatch_outbox_created": False,
    }
    cursor = conn.execute(
        """INSERT INTO video_jobs
           (project_id,user_id,job_type,status,priority,attempts,max_attempts,result_json,
            progress_percent,progress_message,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            int(project_id),
            int(user_id),
            VIDEO_RENDER_JOB_TYPE,
            VIDEO_JOB_PRECHECK_RUNNING,
            100,
            0,
            3,
            _json_dumps(result_payload),
            5,
            VIDEO_JOB_PRECHECK_RUNNING,
            current,
            current,
        ),
    )
    job_id = int(cursor.lastrowid or 0)
    if job_id <= 0:
        raise RuntimeError("job_create_failed")
    conn.execute(
        "UPDATE video_projects SET job_id=?,updated_at=? WHERE project_id=? AND user_id=?",
        (job_id, current, int(project_id), int(user_id)),
    )
    job = get_video_render_job(conn, job_id)
    if not job:
        raise RuntimeError("job_create_readback_failed")
    return {**job, "duplicate_prevented": False}


def record_video_precheck_job_result(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    user_id: int,
    preflight_result: str,
    admission_result: str,
    blocker_code: str = "",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist a zero-submit precheck result on the already-created job."""

    ensure_video_project_queue_schema(conn)
    job = get_video_render_job(conn, int(job_id))
    if not job:
        raise ValueError("job_not_found")
    if int(job.get("user_id") or 0) != int(user_id):
        raise PermissionError("job_user_mismatch")

    allowed_statuses = {
        VIDEO_JOB_PRECHECK_RUNNING,
        VIDEO_JOB_PRECHECK_BLOCKED,
        VIDEO_JOB_READY_TO_SUBMIT,
    }
    if str(job.get("status") or "") not in allowed_statuses:
        raise ValueError("job_not_in_precheck_state")

    preflight = str(preflight_result or "NOT_RUN").strip().upper()
    admission = str(admission_result or "NOT_RUN").strip().upper()
    blocked = preflight == "BLOCKED" or admission == "BLOCKED"
    ready = preflight == "PASS" and admission == "PASS"
    if not blocked and not ready:
        raise ValueError("invalid_precheck_result")
    status = VIDEO_JOB_PRECHECK_BLOCKED if blocked else VIDEO_JOB_READY_TO_SUBMIT
    progress = 5 if blocked else 10

    result_payload = _json_loads(str(job.get("result_json") or ""), {})
    if not isinstance(result_payload, dict):
        result_payload = {}
    result_payload.update(dict(payload or {}))
    result_payload.update(
        {
            "preflight_result": preflight,
            "admission_result": admission,
            "exact_blocker_code": str(blocker_code or ""),
            "provider_task_id": None,
            "submit_count": 0,
            "poll_count": 0,
            "charge_count": 0,
            "charge_state": "NO_CHARGE",
            "dispatch_outbox_created": False,
        }
    )
    cursor = conn.execute(
        """UPDATE video_jobs
              SET status=?,result_json=?,progress_percent=?,progress_message=?,updated_at=?
            WHERE id=? AND user_id=? AND status IN (?,?,?)""",
        (
            status,
            _json_dumps(result_payload),
            progress,
            status,
            now_text(),
            int(job_id),
            int(user_id),
            VIDEO_JOB_PRECHECK_RUNNING,
            VIDEO_JOB_PRECHECK_BLOCKED,
            VIDEO_JOB_READY_TO_SUBMIT,
        ),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("job_precheck_state_changed")
    updated = get_video_render_job(conn, int(job_id))
    if not updated:
        raise RuntimeError("job_precheck_readback_failed")
    return updated


def _product_video_final_admission_state(
    project: dict[str, Any],
    admission: dict[str, Any] | None,
    *,
    user_id: int,
    require_provider_admission: bool,
    require_authoritative_snapshot: bool,
    checked_at: str,
) -> dict[str, Any]:
    project = dict(project or {})
    admission = dict(admission or {})
    asset_pack = _json_loads(str(project.get("asset_pack_json") or ""), {})
    invoice = _json_loads(str(project.get("invoice_json") or ""), {})
    if not isinstance(asset_pack, dict):
        asset_pack = {}
    if not isinstance(invoice, dict):
        invoice = {}
    snapshot = admission.get("provider_eligibility_snapshot")
    if not isinstance(snapshot, dict):
        snapshot = admission if admission.get("provider_eligibility_snapshot_id") else {}
    if not snapshot and not require_authoritative_snapshot:
        persisted = asset_pack.get("provider_eligibility_snapshot") or invoice.get("provider_eligibility_snapshot") or {}
        snapshot = dict(persisted) if isinstance(persisted, dict) else {}
    candidates = [
        str(item or "").strip()
        for item in (
            admission.get("admission_candidate_keys")
            or admission.get("runtime_candidate_keys")
            or admission.get("eligible_provider_keys")
            or snapshot.get("runtime_candidate_keys")
            or snapshot.get("eligible_provider_keys")
            or []
        )
        if str(item or "").strip()
    ]
    if not require_provider_admission and not candidates:
        if os.environ.get("VIDEO_PROVIDER_CHAIN") is not None:
            candidates = resolve_product_video_provider_chain()
        else:
            candidates = _split_product_video_provider_chain(
                asset_pack.get("provider_chain")
                or asset_pack.get("provider_order")
                or invoice.get("provider_chain")
                or invoice.get("provider_order")
                or ""
            ) or resolve_product_video_provider_chain()
    declared_candidate_count = _as_int(admission.get("admission_candidate_count"), len(candidates))
    snapshot_id = str(
        admission.get("admission_snapshot_id")
        or admission.get("provider_eligibility_snapshot_id")
        or snapshot.get("provider_eligibility_snapshot_id")
        or (f"legacy-{project.get('project_id')}" if not require_provider_admission else "")
    )
    admission_checked_at = str(admission.get("admission_checked_at") or snapshot.get("admission_checked_at") or checked_at)
    ttl_seconds = max(
        5,
        min(
            300,
            _as_int(
                admission.get("admission_ttl_seconds")
                or os.getenv("PRODUCT_VIDEO_ADMISSION_TTL_SECONDS"),
                PRODUCT_VIDEO_ADMISSION_TTL_SECONDS_DEFAULT,
            ),
        ),
    )
    checked_epoch = _parse_time_epoch(admission_checked_at)
    current_epoch = _parse_time_epoch(checked_at)
    snapshot_age_seconds = max(0, int(current_epoch - checked_epoch)) if checked_epoch and current_epoch else -1
    snapshot_fresh = bool(
        checked_epoch
        and current_epoch
        and checked_epoch <= current_epoch + 5
        and snapshot_age_seconds <= ttl_seconds
    )
    quote_fingerprint = product_video_admission_quote_fingerprint(project, int(user_id))
    snapshot_user_id = _as_int(admission.get("admission_user_id") or snapshot.get("admission_user_id"), 0)
    snapshot_project_id = _as_int(admission.get("admission_project_id") or snapshot.get("admission_project_id"), 0)
    snapshot_quote_fingerprint = str(
        admission.get("admission_quote_fingerprint")
        or snapshot.get("admission_quote_fingerprint")
        or ""
    )
    handler_id = str(admission.get("admission_callback_handler_id") or snapshot.get("admission_callback_handler_id") or "")
    callback_data = str(admission.get("admission_callback_data") or snapshot.get("admission_callback_data") or "")
    context_signature_valid = verify_product_video_final_admission_context(admission)
    provider_health_gate_pass = bool(admission.get("admission_provider_health_gate_pass"))
    worker_version_compatible = bool(
        admission.get("worker_compatible")
        if "worker_compatible" in admission
        else admission.get("admission_worker_version_compatible")
    )
    worker_connected = bool(admission.get("worker_connected"))
    worker_heartbeat_fresh = bool(admission.get("worker_heartbeat_fresh"))
    worker_lease_valid = bool(admission.get("worker_lease_valid"))
    worker_sha_match = bool(admission.get("worker_sha_match"))
    worker_capability_match = bool(admission.get("worker_capability_match"))
    worker_identity_conflict = bool(admission.get("worker_identity_conflict"))
    worker_generation_id = str(admission.get("worker_generation_id") or "")
    worker_git_sha = str(admission.get("worker_git_sha") or admission.get("admission_worker_sha") or "")
    runtime_sha = str(admission.get("runtime_sha") or admission.get("admission_worker_runtime_sha") or "")
    route_contract = canonical_product_video_route_contract(project, admission)
    persisted_admission_route = admission.get("admission_route_requires_provider")
    canonical_route_requires_provider = bool(route_contract.get("route_requires_provider"))
    route_requires_provider = bool(canonical_route_requires_provider)
    if require_authoritative_snapshot and persisted_admission_route is False:
        route_requires_provider = False
        route_contract["route_requirement_override"] = "signed_admission_route_false_rejected"
    elif route_requires_provider and persisted_admission_route is False:
        route_contract["route_requirement_override"] = "legacy_persisted_false_ignored"
    duplicate_handler_detected = bool(admission.get("duplicate_confirm_handler_detected"))
    admission_mode = str(admission.get("admission_mode") or "healthy").strip().lower()
    probation_mode = admission_mode == PRODUCT_VIDEO_PROBATION_ADMISSION_MODE
    probation_candidate_key = str(admission.get("probation_candidate_key") or "").strip()
    probation_reason = str(admission.get("probation_reason") or "").strip()
    probation_lock_clear = bool(admission.get("probation_lock_clear"))
    submit_source = str(
        admission.get("submit_source")
        or asset_pack.get("submit_source")
        or asset_pack.get("provider_submit_source")
        or invoice.get("submit_source")
        or invoice.get("provider_submit_source")
        or ""
    ).strip().lower()
    public_user_confirmed = bool(
        admission.get("public_user_confirmed")
        if "public_user_confirmed" in admission
        else (
            asset_pack.get("public_user_confirmed")
            or asset_pack.get("b14_public_user_confirmed")
            or invoice.get("public_user_confirmed")
            or invoice.get("b14_public_user_confirmed")
        )
    )
    probation_contract_ok = bool(
        not probation_mode
        or (
            admission_mode == PRODUCT_VIDEO_PROBATION_ADMISSION_MODE
            and len(candidates) == 1
            and candidates[0] == probation_candidate_key
            and submit_source == "public_user_final_confirm"
            and public_user_confirmed
            and probation_lock_clear
        )
    )
    admission_mode_valid = admission_mode in {"healthy", PRODUCT_VIDEO_PROBATION_ADMISSION_MODE}
    consumed_ids = {
        str(asset_pack.get("admission_snapshot_consumed_id") or ""),
        str(invoice.get("admission_snapshot_consumed_id") or ""),
    }
    replayed = bool(
        admission.get("admission_snapshot_consumed")
        or snapshot.get("admission_snapshot_consumed")
        or (snapshot_id and snapshot_id in consumed_ids)
    )
    result_value = str(admission.get("admission_result") or ("PASS" if admission.get("ok") else "BLOCKED")).upper()
    has_cloud = bool(
        candidates
        and any(
            token in str(c).lower()
            for c in candidates
            for token in ("shopaikey", "key4u", "kling", "veo", "cloud", "generic", "http")
        )
    )
    execution_mode = str(admission.get("execution_mode") or ("cloud" if has_cloud else "local")).strip().lower()
    local_worker_required = bool(execution_mode == "local" or not has_cloud)
    authoritative_ok = bool(
        context_signature_valid
        and snapshot_id
        and candidates
        and declared_candidate_count > 0
        and declared_candidate_count == len(candidates)
        and result_value in {"PASS", "ALLOWED"}
        and provider_health_gate_pass
        and snapshot_fresh
        and snapshot_user_id == int(user_id)
        and snapshot_project_id == _as_int(project.get("project_id"), 0)
        and snapshot_quote_fingerprint == quote_fingerprint
        and handler_id == PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID
        and callback_data == PRODUCT_VIDEO_PUBLIC_CONFIRM_CALLBACK
        and (not local_worker_required or worker_version_compatible)
        and (not local_worker_required or worker_connected)
        and (not local_worker_required or worker_heartbeat_fresh)
        and (not local_worker_required or worker_lease_valid)
        and (not local_worker_required or worker_sha_match)
        and (not local_worker_required or worker_capability_match)
        and (not local_worker_required or not worker_identity_conflict)
        and (not local_worker_required or bool(worker_generation_id and worker_git_sha and runtime_sha))
        and route_requires_provider
        and not duplicate_handler_detected
        and not replayed
        and admission_mode_valid
        and probation_contract_ok
    )
    admission_ok = bool(candidates) and (
        not require_provider_admission
        or (
            authoritative_ok
            if require_authoritative_snapshot
            else bool(admission.get("ok", True)) and result_value in {"PASS", "ALLOWED"}
        )
    )
    if admission_ok:
        block_reason = ""
    elif require_authoritative_snapshot and not context_signature_valid:
        block_reason = "admission_context_missing_or_invalid"
    elif not candidates or declared_candidate_count <= 0:
        block_reason = "no_eligible_product_video_provider"
    elif require_authoritative_snapshot and not provider_health_gate_pass:
        block_reason = str(admission.get("admission_block_reason") or "provider_health_gate_blocked")
    elif require_authoritative_snapshot and not admission_mode_valid:
        block_reason = "product_video_admission_mode_invalid"
    elif require_authoritative_snapshot and probation_mode and submit_source != "public_user_final_confirm":
        block_reason = "probation_requires_public_final_confirm"
    elif require_authoritative_snapshot and probation_mode and not public_user_confirmed:
        block_reason = "probation_public_user_confirm_missing"
    elif require_authoritative_snapshot and probation_mode and len(candidates) != 1:
        block_reason = "probation_requires_exactly_one_candidate"
    elif require_authoritative_snapshot and probation_mode and candidates[0] != probation_candidate_key:
        block_reason = "probation_candidate_mismatch"
    elif require_authoritative_snapshot and probation_mode and not probation_lock_clear:
        block_reason = "probation_lock_not_clear"
    elif require_authoritative_snapshot and duplicate_handler_detected:
        block_reason = "duplicate_product_video_confirm_handler"
    elif require_authoritative_snapshot and worker_identity_conflict:
        block_reason = "worker_generation_conflict"
    elif require_authoritative_snapshot and not worker_connected:
        block_reason = str(admission.get("worker_admission_block_reason") or "worker_disconnected")
    elif require_authoritative_snapshot and not worker_heartbeat_fresh:
        block_reason = str(admission.get("worker_admission_block_reason") or "worker_heartbeat_stale")
    elif require_authoritative_snapshot and not worker_lease_valid:
        block_reason = str(admission.get("worker_admission_block_reason") or "worker_lease_expired")
    elif require_authoritative_snapshot and not worker_sha_match:
        block_reason = str(admission.get("worker_admission_block_reason") or "worker_sha_mismatch")
    elif require_authoritative_snapshot and not worker_capability_match:
        block_reason = str(admission.get("worker_admission_block_reason") or "worker_capability_mismatch")
    elif require_authoritative_snapshot and not worker_version_compatible:
        block_reason = str(admission.get("worker_admission_block_reason") or "worker_version_incompatible")
    elif require_authoritative_snapshot and not route_requires_provider:
        block_reason = "product_video_route_contract_mismatch"
    elif require_authoritative_snapshot and replayed:
        block_reason = "admission_snapshot_replayed"
    elif require_authoritative_snapshot and not snapshot_fresh:
        block_reason = "admission_snapshot_stale"
    elif require_authoritative_snapshot and snapshot_user_id != int(user_id):
        block_reason = "admission_snapshot_user_mismatch"
    elif require_authoritative_snapshot and snapshot_project_id != _as_int(project.get("project_id"), 0):
        block_reason = "admission_snapshot_project_mismatch"
    elif require_authoritative_snapshot and snapshot_quote_fingerprint != quote_fingerprint:
        block_reason = "admission_snapshot_quote_mismatch"
    elif require_authoritative_snapshot and handler_id != PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID:
        block_reason = "admission_callback_handler_mismatch"
    else:
        block_reason = str(
            admission.get("admission_block_reason")
            or admission.get("blocker")
            or "product_video_admission_blocked"
        )
    return {
        "admission_enforced": bool(require_provider_admission),
        "admission_authoritative_snapshot_required": bool(require_authoritative_snapshot),
        "admission_snapshot_id": snapshot_id,
        "admission_checked_at": admission_checked_at,
        "admission_ttl_seconds": ttl_seconds,
        "admission_snapshot_age_seconds": snapshot_age_seconds,
        "admission_snapshot_fresh": snapshot_fresh,
        "admission_candidate_keys": candidates,
        "admission_candidate_count": len(candidates),
        "admission_result": (
            "PASS" if admission_ok else "BLOCKED"
        ) if require_authoritative_snapshot else ("allowed" if admission_ok else "blocked"),
        "admission_passed": admission_ok,
        "admission_context_verified": context_signature_valid,
        "admission_provider_health_gate_pass": provider_health_gate_pass,
        "admission_block_reason": block_reason,
        "admission_user_id": snapshot_user_id,
        "admission_project_id": snapshot_project_id,
        "admission_quote_fingerprint": snapshot_quote_fingerprint,
        "admission_callback_handler_id": handler_id,
        "admission_callback_data": callback_data,
        **route_contract,
        "execution_mode": execution_mode,
        "local_worker_required": local_worker_required,
        "cloud_provider_ready": bool(provider_health_gate_pass and candidates),
        "admission_worker_runtime_sha": str(admission.get("admission_worker_runtime_sha") or ""),
        "admission_worker_sha": str(admission.get("admission_worker_sha") or ""),
        "admission_worker_version_compatible": worker_version_compatible,
        "admission_route_requires_provider": route_requires_provider,
        "worker_generation_id": worker_generation_id,
        "worker_git_sha": worker_git_sha,
        "runtime_sha": runtime_sha,
        "worker_compatible": worker_version_compatible,
        "worker_connected": worker_connected,
        "worker_heartbeat_fresh": worker_heartbeat_fresh,
        "worker_lease_valid": worker_lease_valid,
        "worker_sha_match": worker_sha_match,
        "worker_capability_match": worker_capability_match,
        "worker_identity_conflict": worker_identity_conflict,
        "route_requires_provider": route_requires_provider,
        "handler_id": handler_id,
        "persisted_admission_route_requires_provider": persisted_admission_route,
        "worker_admission_block_reason": str(admission.get("worker_admission_block_reason") or ""),
        "duplicate_confirm_handler_detected": duplicate_handler_detected,
        "admission_mode": admission_mode,
        "probation_candidate_key": probation_candidate_key,
        "probation_reason": probation_reason,
        "probation_lock_clear": probation_lock_clear,
        "submit_source": submit_source,
        "public_user_confirmed": public_user_confirmed,
        "probation_contract_ok": probation_contract_ok,
        "provider_eligibility_snapshot": snapshot,
        "provider_eligibility_snapshot_id": snapshot_id,
        "preconfirm_candidate_keys": candidates,
        "runtime_candidate_keys": candidates,
        "final_eligible_provider_count": len(candidates),
        "candidate_set_consistent": True,
    }


def product_video_assert_final_admission(
    project: dict[str, Any],
    admission: dict[str, Any] | None,
    *,
    user_id: int,
    checked_at: str,
    assertion_phase: str,
) -> dict[str, Any]:
    """Evaluate the mandatory public final-confirm gate without any DB write."""
    state = _product_video_final_admission_state(
        project,
        admission,
        user_id=int(user_id),
        require_provider_admission=True,
        require_authoritative_snapshot=True,
        checked_at=checked_at,
    )
    return {
        **state,
        "admission_assertion_phase": str(assertion_phase or "pre_transaction"),
        "admission_pre_insert_hard_stop": not bool(state.get("admission_passed")),
    }


def _confirm_product_video_invoice_atomic(
    conn: sqlite3.Connection,
    *,
    project: dict[str, Any],
    user_id: int,
    admission: dict[str, Any] | None,
    require_provider_admission: bool,
    require_authoritative_snapshot: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    current_dt = now or datetime.now()
    current = now_text(current_dt)
    if require_authoritative_snapshot:
        admission_state = product_video_assert_final_admission(
            project,
            admission,
            user_id=int(user_id),
            checked_at=current,
            assertion_phase="pre_transaction",
        )
    else:
        admission_state = _product_video_final_admission_state(
            project,
            admission,
            user_id=int(user_id),
            require_provider_admission=require_provider_admission,
            require_authoritative_snapshot=False,
            checked_at=current,
        )
    if not admission_state.get("admission_passed"):
        if not require_provider_admission:
            legacy_blocker = "provider_chain_missing_no_charge"
            legacy_payload = {
                **admission_state,
                "source": "product_video",
                "product_video": True,
                "provider_chain_resolved": False,
                "public_confirm_kickoff_attempted": True,
                "public_confirm_kickoff_success": False,
                "worker_dispatch_attempted": True,
                "worker_dispatch_success": False,
                "worker_dispatch_blocker": legacy_blocker,
                "provider_error": legacy_blocker,
                "terminal_state": legacy_blocker,
                "final_decision": "failed_no_charge",
                "provider_submit_called": False,
                "provider_task_id_saved": False,
                "continue_polling": False,
                "charge": 0,
                "charged_xu": 0,
            }
            try:
                conn.execute("BEGIN IMMEDIATE")
                cursor = conn.execute(
                    """INSERT INTO video_jobs
                       (project_id,user_id,job_type,status,priority,attempts,max_attempts,last_error,result_json,
                        progress_percent,progress_message,created_at,updated_at,completed_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        int(project["project_id"]),
                        int(user_id),
                        VIDEO_RENDER_JOB_TYPE,
                        "failed",
                        100,
                        0,
                        3,
                        legacy_blocker,
                        _json_dumps(legacy_payload),
                        0,
                        legacy_blocker,
                        current,
                        current,
                        current,
                    ),
                )
                job_id = int(cursor.lastrowid or 0)
                conn.execute(
                    """UPDATE video_projects
                          SET status='failed',is_confirmed=1,confirmed_at=?,job_id=?,
                              video_terminal_state=?,error_log=?,updated_at=?
                        WHERE project_id=?""",
                    (current, job_id, legacy_blocker, legacy_blocker, current, int(project["project_id"])),
                )
                conn.commit()
                return {
                    "ok": True,
                    "project": get_video_project(conn, int(project["project_id"])),
                    "job": get_video_render_job(conn, job_id),
                    "duplicate_prevented": False,
                    "job_created": True,
                    "scene_records_created": False,
                    "dispatch_outbox_created": False,
                }
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
        return {
            "ok": False,
            "reason": str(admission_state.get("admission_block_reason") or "product_video_admission_blocked"),
            "public_message": "TOAN AAS chưa thể bắt đầu tạo video lúc này.\nHệ thống chưa trừ Xu.\nAnh/chị vui lòng thử lại sau.",
            "admission": admission_state,
            "job_created": False,
            "scene_records_created": False,
            "dispatch_outbox_created": False,
            "charge": 0,
            "charged_xu": 0,
        }
    try:
        conn.execute("BEGIN IMMEDIATE")
        locked = conn.execute(
            """SELECT status,user_id,job_id,asset_pack_json,invoice_json,
                      story_bible_json,scene_cards_json,scene_count,profile_id
                 FROM video_projects WHERE project_id=?""",
            (int(project["project_id"]),),
        ).fetchone()
        if not locked:
            conn.rollback()
            return {"ok": False, "reason": "project_not_found"}
        if int(locked[1] or 0) != int(user_id):
            conn.rollback()
            return {"ok": False, "reason": "project_user_mismatch"}
        if str(locked[0] or "") not in {"draft_invoice", "queued_for_worker"}:
            conn.rollback()
            return {"ok": False, "reason": "project_not_at_invoice"}
        locked_project = {
            **project,
            "status": str(locked[0] or ""),
            "user_id": int(locked[1] or 0),
            "job_id": int(locked[2] or 0),
            "asset_pack_json": str(locked[3] or ""),
            "invoice_json": str(locked[4] or ""),
            "story_bible_json": str(locked[5] or ""),
            "scene_cards_json": str(locked[6] or ""),
            "scene_count": int(locked[7] or 0),
            "profile_id": str(locked[8] or ""),
        }
        if require_authoritative_snapshot:
            boundary_state = product_video_assert_final_admission(
                locked_project,
                admission,
                user_id=int(user_id),
                checked_at=now_text(),
                assertion_phase="inside_transaction_before_first_insert",
            )
            if not boundary_state.get("admission_passed"):
                conn.rollback()
                return {
                    "ok": False,
                    "reason": str(boundary_state.get("admission_block_reason") or "product_video_admission_blocked"),
                    "public_message": "TOAN AAS chưa thể bắt đầu tạo video lúc này.\nHệ thống chưa trừ Xu.\nAnh/chị vui lòng thử lại sau.",
                    "admission": boundary_state,
                    "job_created": False,
                    "scene_records_created": False,
                    "dispatch_outbox_created": False,
                    "charge": 0,
                    "charged_xu": 0,
                }
            admission_state = boundary_state
            locked_asset_pack = _json_loads(str(locked[3] or ""), {})
            locked_invoice = _json_loads(str(locked[4] or ""), {})
            consumed_ids = {
                str((locked_asset_pack or {}).get("admission_snapshot_consumed_id") or ""),
                str((locked_invoice or {}).get("admission_snapshot_consumed_id") or ""),
            }
            if str(admission_state.get("admission_snapshot_id") or "") in consumed_ids:
                conn.rollback()
                return {
                    "ok": False,
                    "reason": "admission_snapshot_replayed",
                    "public_message": "Yêu cầu xác nhận này đã được xử lý. TOAN AAS chưa trừ thêm Xu.",
                    "job_created": False,
                    "scene_records_created": False,
                    "dispatch_outbox_created": False,
                    "charge": 0,
                    "charged_xu": 0,
                }
            seam_state = product_video_public_seam.evaluate_product_video_public_seam(
                locked_project,
                environ=os.environ,
            )
            if seam_state.get("enabled") and not seam_state.get("ready"):
                conn.rollback()
                return {
                    "ok": False,
                    "reason": str(
                        seam_state.get("blocker")
                        or "product_video_public_seam_blocked"
                    ),
                    "public_message": "TOAN AAS chưa thể bắt đầu tạo video lúc này.\nHệ thống chưa trừ Xu.\nAnh/chị vui lòng thử lại sau.",
                    "job_created": False,
                    "scene_records_created": False,
                    "dispatch_outbox_created": False,
                    "charge": 0,
                    "charged_xu": 0,
                }
            decision = seam_state.get("route_decision")
            if seam_state.get("enabled") and isinstance(decision, dict):
                admission_state.update(
                    product_video_public_seam.product_video_route_decision_payload(
                        decision
                    )
                )
        if str(admission_state.get("admission_mode") or "") == PRODUCT_VIDEO_PROBATION_ADMISSION_MODE:
            existing_job_id = int(locked[2] or 0)
            probation_lock = product_video_probation_lock_state(
                conn,
                current_job_id=existing_job_id,
                current_project_id=int(project["project_id"]),
                current_user_id=int(user_id),
                now=current_dt,
            )
            if not probation_lock.get("probation_lock_clear_for_current_job"):
                conn.rollback()
                return {
                    "ok": False,
                    "reason": str(
                        probation_lock.get("probation_lock_reject_reason")
                        or "product_video_probation_lock_active"
                    ),
                    "public_message": "TOAN AAS chưa thể bắt đầu tạo video lúc này.\nHệ thống chưa trừ Xu.\nAnh/chị có thể kiểm tra lại sau.",
                    "admission": {**admission_state, **probation_lock},
                    "job_created": False,
                    "scene_records_created": False,
                    "dispatch_outbox_created": False,
                    "charge": 0,
                    "charged_xu": 0,
                }
            admission_state.update(probation_lock)
            if probation_lock.get("same_job_lock_reentry_allowed"):
                admission_state.update(
                    {
                        "probation_job_id": existing_job_id,
                        "probation_candidate_key": str(
                            probation_lock.get("active_probation_provider")
                            or admission_state.get("probation_candidate_key")
                            or ""
                        ),
                        "probation_result": "pending",
                    }
                )
            else:
                admission_state.update(
                    {
                        "probation_started_at": current,
                        "probation_job_id": 0,
                        "probation_result": "pending",
                        "probation_terminal_at": "",
                        "probation_cooldown_active": False,
                        "probation_cooldown_until": "",
                    }
                )
        active_row = conn.execute(
            """SELECT id,project_id,user_id,job_type,status,priority,attempts,max_attempts,locked_by,locked_at,
                      lease_expires_at,last_error,result_json,created_at,updated_at,started_at,completed_at,
                      progress_percent,progress_message
                 FROM video_jobs
                WHERE project_id=? AND job_type=? AND status IN ('queued','processing')
                ORDER BY id ASC LIMIT 1""",
            (int(project["project_id"]), VIDEO_RENDER_JOB_TYPE),
        ).fetchone()
        if active_row:
            active = _job_from_row(active_row)
            active_payload = _json_loads(str(active.get("result_json") or ""), {})
            if not isinstance(active_payload, dict):
                active_payload = {}
            incoming_route_hash = str(
                admission_state.get("product_video_route_decision_sha256") or ""
            )
            if incoming_route_hash:
                active_route_hash = str(
                    active_payload.get("product_video_route_decision_sha256") or ""
                )
                if not active_route_hash or active_route_hash != incoming_route_hash:
                    conn.rollback()
                    return {
                        "ok": False,
                        "reason": (
                            "product_video_route_decision_conflict"
                            if active_route_hash
                            else "product_video_route_decision_missing_on_active_job"
                        ),
                        "public_message": "Yêu cầu tạo video đang được xử lý theo lựa chọn đã xác nhận. Hệ thống chưa trừ thêm Xu.",
                        "job_created": False,
                        "scene_records_created": False,
                        "dispatch_outbox_created": False,
                        "charge": 0,
                        "charged_xu": 0,
                    }
            existing_probation_started_at = str(active_payload.get("probation_started_at") or "")
            existing_probation_provider = str(active_payload.get("probation_candidate_key") or "")
            active_payload.update(admission_state)
            if str(active_payload.get("admission_mode") or "") == PRODUCT_VIDEO_PROBATION_ADMISSION_MODE:
                active_payload["probation_job_id"] = int(active["id"])
                active_payload["same_job_lock_reentry_allowed"] = True
                active_payload["current_job_matches_lock"] = True
                if existing_probation_started_at:
                    active_payload["probation_started_at"] = existing_probation_started_at
                if existing_probation_provider:
                    active_payload["probation_candidate_key"] = existing_probation_provider
            has_task = any(
                _product_video_scene_task_identity(item)
                for item in (active_payload.get("scene_tasks") or [])
                if isinstance(item, dict)
            )
            has_clip = any(
                bool(item.get("winning_task_id") or item.get("clip_valid") or item.get("result_url"))
                for item in (active_payload.get("scene_tasks") or [])
                if isinstance(item, dict)
            )
            existing_outbox = conn.execute(
                "SELECT outbox_id FROM video_dispatch_outbox WHERE job_id=? LIMIT 1",
                (int(active["id"]),),
            ).fetchone()
            if not existing_outbox and not has_task and not has_clip:
                active_scene_count = max(1, _product_video_scene_count(project, active_payload))
                _insert_product_video_dispatch_outbox_record(
                    conn,
                    job_id=int(active["id"]),
                    project_id=int(project["project_id"]),
                    scene_indexes=list(range(1, active_scene_count + 1)),
                    available_at=product_video_outbox_time_text(current_dt),
                )
                active_payload.update(
                    {
                        "dispatch_outbox_present": True,
                        "dispatch_outbox_status": "pending",
                        "dispatch_outbox_attempt_count": 0,
                    }
                )
            conn.execute(
                "UPDATE video_jobs SET result_json=?,updated_at=? WHERE id=?",
                (_json_dumps(active_payload), current, int(active["id"])),
            )
            conn.commit()
            active = get_video_render_job(conn, int(active["id"]))
            return {
                "ok": True,
                "project": get_video_project(conn, int(project["project_id"])),
                "job": active,
                "duplicate_prevented": True,
            }
        asset_pack = _json_loads(str(locked[3] or ""), {})
        invoice = _json_loads(str(locked[4] or ""), {})
        if not isinstance(asset_pack, dict):
            asset_pack = {}
        if not isinstance(invoice, dict):
            invoice = {}
        asset_pack.update(admission_state)
        invoice.update(admission_state)
        route_max_attempts = (
            1
            if admission_state.get("product_video_durable_public_seam")
            and admission_state.get("automatic_retry_allowed") is False
            else 3
        )
        linked_job_id = _as_int(locked[2], 0)
        linked_job = get_video_render_job(conn, linked_job_id) if linked_job_id > 0 else {}
        linked_status = str(linked_job.get("status") or "")
        preflight_payload = _json_loads(str(linked_job.get("result_json") or ""), {})
        if not isinstance(preflight_payload, dict):
            preflight_payload = {}
        job_promoted = bool(
            linked_job
            and _as_int(linked_job.get("project_id"), 0) == int(project["project_id"])
            and _as_int(linked_job.get("user_id"), 0) == int(user_id)
            and str(linked_job.get("job_type") or "") == VIDEO_RENDER_JOB_TYPE
            and linked_status == VIDEO_JOB_READY_TO_SUBMIT
        )
        if linked_status in {
            VIDEO_JOB_PRECHECK_RUNNING,
            VIDEO_JOB_PRECHECK_BLOCKED,
            VIDEO_JOB_READY_TO_SUBMIT,
        } and not job_promoted:
            conn.rollback()
            return {
                "ok": False,
                "reason": "product_video_preflight_job_not_ready",
                "public_message": "TOAN AAS chưa thể bắt đầu tạo video lúc này. Hệ thống chưa trừ Xu.",
                "job_created": False,
                "job_promoted": False,
                "dispatch_outbox_created": False,
                "charge": 0,
                "charged_xu": 0,
            }
        if job_promoted and any((
            str(preflight_payload.get("preflight_result") or "").upper() != "PASS",
            str(preflight_payload.get("admission_result") or "").upper() != "PASS",
            bool(preflight_payload.get("provider_task_id")),
            _as_int(preflight_payload.get("submit_count"), 0) != 0,
            _as_int(preflight_payload.get("poll_count"), 0) != 0,
            _as_int(preflight_payload.get("charge_count"), 0) != 0,
            not str(preflight_payload.get("request_id") or "").strip(),
        )):
            conn.rollback()
            return {
                "ok": False,
                "reason": "product_video_preflight_job_identity_invalid",
                "public_message": "TOAN AAS chưa thể bắt đầu tạo video lúc này. Hệ thống chưa trừ Xu.",
                "job_created": False,
                "job_promoted": False,
                "dispatch_outbox_created": False,
                "charge": 0,
                "charged_xu": 0,
            }
        if job_promoted:
            job_id = linked_job_id
        else:
            cursor = conn.execute(
                """INSERT INTO video_jobs
                   (project_id,user_id,job_type,status,priority,attempts,max_attempts,result_json,
                    progress_percent,progress_message,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    int(project["project_id"]),
                    int(user_id),
                    VIDEO_RENDER_JOB_TYPE,
                    "queued",
                    100,
                    0,
                    route_max_attempts,
                    _json_dumps(admission_state),
                    10,
                    "dispatch_outbox_pending",
                    current,
                    current,
                ),
            )
            job_id = int(cursor.lastrowid or 0)
        if str(admission_state.get("admission_mode") or "") == PRODUCT_VIDEO_PROBATION_ADMISSION_MODE:
            admission_state.update(
                {
                    "probation_job_id": job_id,
                    "probation_lock_owner_job": job_id,
                    "current_probation_job_id": job_id,
                    "current_job_matches_lock": True,
                    "same_job_lock_reentry_allowed": True,
                    "probation_lock_clear_for_current_job": True,
                    "probation_lock_owned_by_other_job": False,
                    "probation_lock_reject_reason": "",
                }
            )
            asset_pack.update(admission_state)
            invoice.update(admission_state)
        failure_stage = str((admission or {}).get("_test_failure_stage") or "") if os.getenv("PYTEST_CURRENT_TEST") else ""
        if failure_stage == "after_job_insert":
            raise RuntimeError("injected_after_job_insert")
        project_for_payload = {
            **project,
            "asset_pack_json": _json_dumps(asset_pack),
            "invoice_json": _json_dumps(invoice),
            "is_confirmed": 1,
            "confirmed_at": current,
            "job_id": job_id,
        }
        job_seed = {
            "id": job_id,
            "job_id": job_id,
            "project_id": int(project["project_id"]),
            "user_id": int(user_id),
            "status": "queued",
            "created_at": current,
            "updated_at": current,
        }
        kickoff = build_product_video_confirm_kickoff_payload(
            job_seed,
            project_for_payload,
            provider_chain=list(admission_state["admission_candidate_keys"]),
            now=current_dt,
        )
        if not kickoff.get("provider_chain_resolved"):
            conn.rollback()
            return {
                "ok": False,
                "reason": str(kickoff.get("worker_dispatch_blocker") or "no_eligible_product_video_provider"),
                "public_message": "Hệ thống tạo video nhiều cảnh đang tạm bận. TOAN AAS chưa trừ Xu. Anh/chị vui lòng thử lại sau.",
                "admission": admission_state,
                "job_created": False,
                "dispatch_outbox_created": False,
                "charge": 0,
                "charged_xu": 0,
            }
        scene_count = max(1, _as_int(kickoff.get("scene_count"), 1))
        scene_indexes = list(range(1, scene_count + 1))
        for scene_index in scene_indexes:
            conn.execute(
                """INSERT OR IGNORE INTO video_scenes
                   (project_id,scene_index,role,scene_status)
                   VALUES (?,?,?,?)""",
                (int(project["project_id"]), int(scene_index), "product_video_scene", "pending"),
            )
        if failure_stage == "after_scene_insert":
            raise RuntimeError("injected_after_scene_insert")
        outbox_id = _insert_product_video_dispatch_outbox_record(
            conn,
            job_id=job_id,
            project_id=int(project["project_id"]),
            scene_indexes=scene_indexes,
            available_at=product_video_outbox_time_text(current_dt),
        )
        if failure_stage == "after_outbox_insert":
            raise RuntimeError("injected_after_outbox_insert")
        payload = {
            **preflight_payload,
            **kickoff,
            **admission_state,
            "dispatch_outbox_present": True,
            "dispatch_outbox_id": outbox_id,
            "dispatch_outbox_status": "pending",
            "dispatch_outbox_attempt_count": 0,
            "dispatch_outbox_lease_owner": "",
            "dispatch_outbox_lease_expires_at": "",
            "dispatch_outbox_last_error": "",
            "dispatch_outbox_acknowledged": False,
            "scene_records_created": True,
            "scene_record_indexes": scene_indexes,
            "worker_scan_seen_job": False,
            "worker_scan_seen_outbox": False,
            "worker_claim_attempted": False,
            "worker_claim_result": "",
            "worker_claim_block_reason": "",
            "worker_last_scan_at": "",
            "worker_next_scan_at": "",
            "terminal_state": "",
            "final_decision": "continue_polling",
            "charge": 0,
            "charged_xu": 0,
            "admission_handler_id": str(admission_state.get("admission_callback_handler_id") or ""),
            "worker_claim_id": "",
            "canonical_engine_entry": PRODUCT_VIDEO_CANONICAL_ENGINE_ENTRY,
            "canonical_manifest_id": f"product-video-{job_id}-manifest",
            "scene_dispatch_count": len(scene_indexes),
            "finalizer_reached": False,
            "job_promoted_from_preflight": job_promoted,
            "preflight_job_status_before_promotion": (
                VIDEO_JOB_READY_TO_SUBMIT if job_promoted else ""
            ),
            "provider_task_id": None,
            "submit_count": 0,
            "poll_count": 0,
            "charge_count": 0,
        }
        promoted = conn.execute(
            """UPDATE video_jobs
                  SET status='queued',max_attempts=?,result_json=?,last_error='',progress_percent=10,
                      progress_message='dispatch_outbox_pending',locked_by='',locked_at=NULL,
                      lease_expires_at=NULL,completed_at=NULL,updated_at=?
                WHERE id=? AND status IN (?, 'queued')""",
            (
                route_max_attempts,
                _json_dumps(payload),
                current,
                job_id,
                VIDEO_JOB_READY_TO_SUBMIT,
            ),
        )
        if promoted.rowcount != 1:
            raise RuntimeError("product_video_same_job_promotion_conflict")
        if failure_stage == "before_snapshot_consume":
            raise RuntimeError("injected_before_snapshot_consume")
        if require_authoritative_snapshot:
            consumed = {
                "admission_snapshot_consumed": True,
                "admission_snapshot_consumed_id": str(admission_state.get("admission_snapshot_id") or ""),
                "admission_snapshot_consumed_at": current,
                "admission_snapshot_consumed_job_id": job_id,
            }
            asset_pack.update(consumed)
            invoice.update(consumed)
        conn.execute(
            """UPDATE video_projects
                  SET status='queued_for_worker',is_confirmed=1,confirmed_at=?,job_id=?,
                      asset_pack_json=?,invoice_json=?,video_terminal_state='',updated_at=?
                WHERE project_id=?""",
            (
                current,
                job_id,
                _json_dumps(asset_pack),
                _json_dumps(invoice),
                current,
                int(project["project_id"]),
            ),
        )
        if failure_stage == "during_commit":
            raise RuntimeError("injected_during_commit")
        conn.commit()
        return {
            "ok": True,
            "project": get_video_project(conn, int(project["project_id"])),
            "job": get_video_render_job(conn, job_id),
            "outbox": get_product_video_dispatch_outbox(conn, job_id=job_id),
            "duplicate_prevented": False,
            "job_created": not job_promoted,
            "job_promoted": job_promoted,
            "dispatch_outbox_created": True,
            "scene_records_created": True,
        }
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        return {
            "ok": False,
            "reason": "dispatch_outbox_transaction_failed",
            "public_message": "Hệ thống chưa thể bắt đầu tạo video lúc này. TOAN AAS chưa trừ Xu. Anh/chị vui lòng thử lại sau.",
            "error_class": type(exc).__name__,
            "job_created": False,
            "dispatch_outbox_created": False,
            "charge": 0,
            "charged_xu": 0,
        }


def confirm_video_project_invoice(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    user_id: int,
    balance_xu: int | None = None,
    deduct_func: Callable[[int, int], Any] | None = None,
    provider_admission: dict[str, Any] | None = None,
    require_provider_admission: bool = False,
    require_authoritative_admission: bool = False,
) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    project = get_video_project(conn, int(project_id))
    if not project:
        return {"ok": False, "reason": "project_not_found"}
    if int(project.get("user_id") or 0) != int(user_id):
        return {"ok": False, "reason": "project_user_mismatch"}
    if str(project.get("status") or "") not in {"draft_invoice", "queued_for_worker"}:
        return {"ok": False, "reason": "project_not_at_invoice"}
    active = get_active_video_render_job(conn, int(project_id))
    if active and not _is_product_video_project(project):
        kickoff = kickoff_product_video_job_after_confirm(conn, job_id=int(active.get("id") or 0))
        if not kickoff.get("skipped"):
            active = kickoff.get("job") or active
            project = kickoff.get("project") or project
        return {"ok": True, "project": project, "job": active, "duplicate_prevented": True}
    invoice = _json_loads(str(project.get("invoice_json") or ""), {})
    if not isinstance(invoice, dict):
        invoice = {}
    if _is_product_video_project(project):
        quote_state = _product_video_quote_consistency(invoice, project)
        if not quote_state.get("quote_consistent"):
            return {"ok": False, "reason": quote_state.get("quote_mismatch_reason") or "product_video_quote_mismatch_no_charge", "quote": quote_state}
        total_xu = int(quote_state.get("customer_charge_planned_xu") or 0)
    else:
        total_xu = int(project.get("total_xu_estimated") or 0)
    if total_xu <= 0:
        total_xu = int(invoice.get("total_xu") or invoice.get("total") or 0)
    if balance_xu is not None and int(balance_xu) < total_xu:
        return {"ok": False, "reason": "insufficient_balance", "required_xu": total_xu}
    if _is_product_video_project(project):
        return _confirm_product_video_invoice_atomic(
            conn,
            project=project,
            user_id=int(user_id),
            admission=provider_admission,
            require_provider_admission=bool(require_provider_admission),
            require_authoritative_snapshot=bool(require_authoritative_admission),
        )
    if deduct_func is not None:
        charge = deduct_func(int(user_id), total_xu)
        if isinstance(charge, dict) and not charge.get("ok", True):
            return {"ok": False, "reason": "deduct_failed", "charge": charge}
        if charge is False:
            return {"ok": False, "reason": "deduct_failed", "charge": charge}
    confirmed_at = now_text()
    update_video_project(
        conn,
        int(project_id),
        status="queued_for_worker",
        video_terminal_state="final_rendering",
        is_confirmed=1,
        confirmed_at=confirmed_at,
    )
    job = enqueue_video_render_job(conn, project_id=int(project_id), user_id=int(user_id))
    update_video_project(conn, int(project_id), job_id=int(job.get("id") or 0))
    kickoff = kickoff_product_video_job_after_confirm(conn, job_id=int(job.get("id") or 0))
    if not kickoff.get("skipped"):
        job = kickoff.get("job") or job
        project = kickoff.get("project") or get_video_project(conn, int(project_id))
    else:
        project = get_video_project(conn, int(project_id))
    return {"ok": True, "project": project, "job": job, "duplicate_prevented": bool(job.get("duplicate_prevented"))}


def _persisted_product_video_route_identity_matches(payload: dict[str, Any]) -> bool:
    """Validate the frozen route without depending on current runtime flags."""

    raw_decision = payload.get("product_video_route_decision")
    if not payload.get("product_video_durable_public_seam") or not isinstance(raw_decision, dict):
        return False
    decision = dict(raw_decision)
    persisted_hash = str(decision.pop("route_decision_sha256", "")).strip().lower()
    if len(persisted_hash) != 64 or any(
        character not in "0123456789abcdef" for character in persisted_hash
    ):
        return False
    calculated_hash = hashlib.sha256(
        json.dumps(
            decision,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    if calculated_hash != persisted_hash or str(
        payload.get("product_video_route_decision_sha256") or ""
    ).strip().lower() != persisted_hash:
        return False
    frozen = {**decision, "route_decision_sha256": persisted_hash}
    flattened = product_video_public_seam.product_video_route_decision_payload(frozen)
    for key in (
        "product_video_route_decision_version",
        "product_video_route_selection_sha256",
        "product_video_engine_mode",
        "scene_count",
        "route_id",
        "product_video_engine_adapter",
        "worker_job_type",
        "worker_owner",
        "required_worker_capability",
        "automatic_retry_allowed",
        "automatic_resubmit_allowed",
        "automatic_fallback_allowed",
    ):
        if payload.get(key) != flattened.get(key):
            return False
    return bool(
        decision.get("canonical_engine_entry") == PRODUCT_VIDEO_CANONICAL_ENGINE_ENTRY
        and decision.get("automatic_retry_allowed") is False
        and decision.get("automatic_resubmit_allowed") is False
        and decision.get("automatic_fallback_allowed") is False
    )


def _confirmed_uiflow3_job_for_exact_admission_replay(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    user_id: int,
    admission: dict[str, Any] | None,
) -> dict[str, Any]:
    """Resolve an exact UIFLOW3 confirmation replay without creating work."""

    project = get_video_project(conn, int(project_id))
    if not project or _as_int(project.get("user_id"), 0) != int(user_id):
        return {}
    asset_pack = _json_loads(str(project.get("asset_pack_json") or ""), {})
    invoice = _json_loads(str(project.get("invoice_json") or ""), {})
    if not isinstance(asset_pack, dict) or not isinstance(invoice, dict):
        return {}
    if str(asset_pack.get("uiflow3_bridge_version") or "") != video_uiflow3_execution_contract.BRIDGE_VERSION:
        return {}

    admission = dict(admission or {})
    snapshot_id = str(admission.get("admission_snapshot_id") or "").strip()
    consumed_ids = {
        str(asset_pack.get("admission_snapshot_consumed_id") or "").strip(),
        str(invoice.get("admission_snapshot_consumed_id") or "").strip(),
    }
    consumed_job_ids = {
        _as_int(asset_pack.get("admission_snapshot_consumed_job_id"), 0),
        _as_int(invoice.get("admission_snapshot_consumed_job_id"), 0),
    }
    if not snapshot_id or consumed_ids != {snapshot_id} or len(consumed_job_ids) != 1:
        return {}
    consumed_job_id = next(iter(consumed_job_ids))
    if consumed_job_id <= 0 or _as_int(project.get("job_id"), 0) != consumed_job_id:
        return {}
    if any(
        (
            _as_int(admission.get("admission_user_id"), 0) != int(user_id),
            _as_int(admission.get("admission_project_id"), 0) != int(project_id),
            str(admission.get("admission_quote_fingerprint") or "")
            != product_video_admission_quote_fingerprint(project, int(user_id)),
            str(admission.get("admission_callback_handler_id") or "")
            != PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID,
            str(admission.get("admission_callback_data") or "")
            != PRODUCT_VIDEO_PUBLIC_CONFIRM_CALLBACK,
        )
    ):
        return {}

    job = get_video_render_job(conn, consumed_job_id)
    if (
        not job
        or _as_int(job.get("project_id"), 0) != int(project_id)
        or _as_int(job.get("user_id"), 0) != int(user_id)
        or str(job.get("job_type") or "") != VIDEO_RENDER_JOB_TYPE
    ):
        return {}
    payload = _json_loads(str(job.get("result_json") or ""), {})
    if not isinstance(payload, dict):
        return {}
    if any(
        (
            str(payload.get("admission_snapshot_id") or "") != snapshot_id,
            _as_int(payload.get("admission_user_id"), 0) != int(user_id),
            _as_int(payload.get("admission_project_id"), 0) != int(project_id),
            str(payload.get("admission_quote_fingerprint") or "")
            != str(admission.get("admission_quote_fingerprint") or ""),
        )
    ):
        return {}
    execution = video_uiflow3_execution_contract.validate_execution_contract(
        project,
        payload,
        require_payload_identity=True,
    )
    if not execution.get("applies") or not execution.get("ok"):
        return {}
    if not _persisted_product_video_route_identity_matches(payload):
        return {}
    if str(payload.get("product_video_route_selection_sha256") or "") != str(
        payload.get("uiflow3_route_selection_sha256") or ""
    ):
        return {}
    return {
        "ok": True,
        "project": project,
        "job": job,
        "outbox": get_product_video_dispatch_outbox(conn, job_id=consumed_job_id),
        "duplicate_prevented": True,
        "confirmation_replay_resolved": True,
        "job_created": False,
        "dispatch_outbox_created": False,
        "scene_records_created": False,
        "charge": 0,
        "charged_xu": 0,
    }


def confirm_public_product_video_invoice(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    user_id: int,
    balance_xu: int | None = None,
    provider_admission: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The only queue entry point authorized for a public final-confirm callback."""
    if not verify_product_video_final_admission_context(provider_admission):
        return {
            "ok": False,
            "reason": "admission_context_missing_or_invalid",
            "public_message": "TOAN AAS chưa thể bắt đầu tạo video lúc này.\nHệ thống chưa trừ Xu.\nAnh/chị vui lòng thử lại sau.",
            "job_created": False,
            "scene_records_created": False,
            "dispatch_outbox_created": False,
            "charge": 0,
            "charged_xu": 0,
        }
    replay = _confirmed_uiflow3_job_for_exact_admission_replay(
        conn,
        project_id=int(project_id),
        user_id=int(user_id),
        admission=provider_admission,
    )
    if replay:
        return replay
    return confirm_video_project_invoice(
        conn,
        project_id=int(project_id),
        user_id=int(user_id),
        balance_xu=balance_xu,
        deduct_func=None,
        provider_admission=provider_admission,
        require_provider_admission=True,
        require_authoritative_admission=True,
    )


def requeue_stale_video_jobs(conn: sqlite3.Connection, *, now: datetime | None = None) -> int:
    ensure_video_project_queue_schema(conn)
    current = now_text(now)
    cursor = conn.execute(
        """UPDATE video_jobs
           SET status='queued', locked_by='', locked_at=NULL, lease_expires_at=NULL, updated_at=?, last_error='lease_expired_requeued'
           WHERE job_type=? AND status='processing'
             AND lease_expires_at IS NOT NULL
             AND lease_expires_at < ?
             AND COALESCE(attempts,0) < COALESCE(max_attempts,3)""",
        (current, VIDEO_RENDER_JOB_TYPE, current),
    )
    conn.commit()
    return int(cursor.rowcount or 0)


def claim_next_video_job(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    lease_seconds: int = 600,
    now: datetime | None = None,
) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    requeue_stale_video_jobs(conn, now=now)
    current_dt = now or datetime.now()
    current = now_text(current_dt)
    lease_expires = now_text(current_dt + timedelta(seconds=max(30, int(lease_seconds or 600))))
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """SELECT j.id,j.project_id,j.user_id,j.job_type,j.status,j.priority,j.attempts,j.max_attempts,j.locked_by,j.locked_at,
                      j.lease_expires_at,j.last_error,j.result_json,j.created_at,j.updated_at,j.started_at,j.completed_at,
                      j.progress_percent,j.progress_message
               FROM video_jobs j
               JOIN video_projects p ON p.project_id=j.project_id
               WHERE j.job_type=? AND j.status='queued'
                 AND COALESCE(p.is_confirmed,0)=1
                 AND p.status IN ('queued_for_worker','processing')
               ORDER BY j.priority ASC, j.created_at ASC, j.id ASC
               LIMIT 1""",
            (VIDEO_RENDER_JOB_TYPE,),
        ).fetchone()
        if not row:
            conn.commit()
            return {}
        job = _job_from_row(row)
        cursor = conn.execute(
            """UPDATE video_jobs
               SET status='processing', attempts=COALESCE(attempts,0)+1, locked_by=?, locked_at=?,
                   lease_expires_at=?, started_at=COALESCE(started_at, ?), updated_at=?
               WHERE id=? AND status='queued'""",
            (str(worker_id or "local_worker")[:120], current, lease_expires, current, current, int(job["id"])),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return {}
        conn.execute("UPDATE video_projects SET status='processing', updated_at=? WHERE project_id=?", (current, int(job["project_id"])))
        conn.commit()
        return get_video_render_job(conn, int(job["id"]))
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


def video_worker_poll_queued_job(conn: sqlite3.Connection, worker_id: str = "local_worker") -> dict[str, Any]:
    return claim_next_video_job(conn, worker_id=worker_id)


def heartbeat_video_job(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    worker_id: str,
    progress_percent: int = 0,
    message: str = "",
    lease_seconds: int = 600,
    now: datetime | None = None,
) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    current_dt = now or datetime.now()
    current = now_text(current_dt)
    lease_expires = now_text(current_dt + timedelta(seconds=max(30, int(lease_seconds or 600))))
    progress = max(0, min(100, int(progress_percent or 0)))
    cursor = conn.execute(
        """UPDATE video_jobs
           SET lease_expires_at=?, progress_percent=?, progress_message=?, updated_at=?
           WHERE id=? AND status='processing' AND locked_by=?""",
        (
            lease_expires,
            progress,
            str(message or "")[:500],
            current,
            int(job_id),
            str(worker_id or "")[:120],
        ),
    )
    conn.commit()
    if cursor.rowcount != 1:
        return {"ok": False, "reason": "job_not_owned_or_not_processing", "job": get_video_render_job(conn, int(job_id))}
    return {"ok": True, "job": get_video_render_job(conn, int(job_id))}


PRODUCT_VIDEO_SCENE_SECONDS = 8
PRODUCT_VIDEO_MAX_UIFLOW3_SCENE_SECONDS = 15
PRODUCT_VIDEO_DURATION_TOLERANCE_SECONDS = 0.7
PRODUCT_VIDEO_DEFAULT_PROVIDER_CHAIN = "shopaikey_video,key4u_video,toanaas_video,veo,kling,generic_http"
PRODUCT_VIDEO_ORCHESTRATION_MODE_RAW_DELIVERY = "single_task_legacy"
PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE = "per_scene_8s"
PRODUCT_VIDEO_RENDER_PIPELINE_HISTORICAL_CONCAT = "historical_multi_clip_concat"
VIDEO_SCENE_DISPATCH_GRACE_SECONDS_DEFAULT = 30
PRODUCT_VIDEO_PER_SCENE_ORCHESTRATION_ALIASES = {
    "per_scene_8s",
    "per_scene",
    "scene",
    "scene_orchestrator",
    "multi_clip_concat",
    "historical_multi_clip_concat",
}


def _split_product_video_provider_chain(value: Any) -> list[str]:
    aliases = {
        "shopaikey": "shopaikey_video",
        "shopai": "shopaikey_video",
        "key4u": "key4u_video",
        "k4u": "key4u_video",
        "toanaas": "toanaas_video",
        "generic": "generic_http",
    }
    if isinstance(value, (list, tuple)):
        raw_items = [str(item or "") for item in value]
    else:
        raw_items = str(value or "").replace(">", ",").replace("|", ",").split(",")
    result: list[str] = []
    for item in raw_items:
        token = aliases.get(item.strip().lower(), item.strip().lower())
        if token and token not in result:
            result.append(token)
    return result


def normalize_product_video_provider_chain(value: Any) -> list[str]:
    """Normalize a configured provider chain for service-layer callers."""

    return _split_product_video_provider_chain(value)


def resolve_product_video_provider_chain(environ: dict[str, str] | None = None) -> list[str]:
    env = os.environ if environ is None else environ
    raw = env.get("VIDEO_PROVIDER_CHAIN") if hasattr(env, "get") else None
    return _split_product_video_provider_chain(raw if raw is not None else PRODUCT_VIDEO_DEFAULT_PROVIDER_CHAIN)


def _product_video_truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_product_video_project(project: dict[str, Any]) -> bool:
    asset_pack = _json_loads(str(project.get("asset_pack_json") or ""), {})
    invoice = _json_loads(str(project.get("invoice_json") or ""), {})
    if not isinstance(asset_pack, dict):
        asset_pack = {}
    if not isinstance(invoice, dict):
        invoice = {}
    source = str(asset_pack.get("source") or invoice.get("source") or "").strip()
    render_mode = str(asset_pack.get("render_mode") or invoice.get("render_mode") or "").strip().lower().replace("-", "_")
    return bool(
        source == "product_video"
        and (
            render_mode == "real"
            or _product_video_truthy(asset_pack.get("provider_call") or invoice.get("provider_call"))
            or _product_video_truthy(asset_pack.get("public_user") or invoice.get("public_user"))
        )
    )


def product_video_engine_contract(product_type: Any) -> dict[str, Any]:
    """Resolve one product's immutable commercial-to-engine adapter contract."""

    from services import video_tail9

    requested = str(product_type or "video_ai_real").strip() or "video_ai_real"
    commercial = video_tail9.commercial_contract(requested)
    executor_product_type = str(commercial.get("executor_product_type") or requested)
    route = video_final_output.route_for_product_type(executor_product_type)
    required_capability = str(
        route.get("provider_capability")
        or commercial.get("required_capability")
        or "text_to_video"
    )
    if str(commercial.get("pricing_mode") or "") == "frame_video" or executor_product_type == "video_local_edit":
        required_capability = str(commercial.get("required_capability") or required_capability)
    return {
        "public_product_type": requested,
        "product_type": str(route.get("product_type") or executor_product_type),
        "executor_product_type": executor_product_type,
        "engine_route": str(commercial.get("engine_route") or route.get("engine_adapter") or ""),
        "engine_adapter": str(route.get("engine_adapter") or commercial.get("engine_route") or ""),
        "required_capability": required_capability,
        "package_capability": str(commercial.get("required_capability") or required_capability),
        "input_type": str(commercial.get("input_type") or ""),
        "worker_owner": str(commercial.get("worker_owner") or "product_video"),
        "execution_enabled": bool(commercial.get("execution_enabled", True)),
        "execution_blocker": str(commercial.get("execution_blocker") or ""),
    }


def _product_video_requested_product_type(
    project: dict[str, Any],
    asset_pack: dict[str, Any],
    invoice: dict[str, Any],
) -> str:
    for value in (
        asset_pack.get("public_product_type"),
        asset_pack.get("video_product_type"),
        asset_pack.get("product_type"),
        invoice.get("public_product_type"),
        invoice.get("video_product_type"),
        invoice.get("product_type"),
        project.get("profile_id"),
    ):
        token = str(value or "").strip()
        if token:
            return token
    return "video_ai_real"


def canonical_product_video_route_contract(
    project: dict[str, Any] | None,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve the immutable Product Video route contract from durable inputs."""
    project = dict(project or {})
    result = dict(result or {})
    asset_pack = _json_loads(str(project.get("asset_pack_json") or ""), {})
    invoice = _json_loads(str(project.get("invoice_json") or ""), {})
    if not isinstance(asset_pack, dict):
        asset_pack = {}
    if not isinstance(invoice, dict):
        invoice = {}
    from services import video_provider_router

    product_type = str(
        result.get("product_type")
        or asset_pack.get("product_type")
        or invoice.get("product_type")
        or project.get("profile_id")
        or ""
    )
    engine_adapter = str(
        result.get("engine_adapter")
        or asset_pack.get("engine_adapter")
        or invoice.get("engine_adapter")
        or ""
    )
    orchestration_mode = str(
        result.get("orchestration_mode")
        or result.get("provider_orchestration_mode")
        or asset_pack.get("orchestration_mode")
        or asset_pack.get("provider_orchestration_mode")
        or invoice.get("orchestration_mode")
        or invoice.get("provider_orchestration_mode")
        or ""
    )
    explicit_local_renderer = bool(
        result.get("explicit_local_renderer")
        or asset_pack.get("explicit_local_renderer")
        or invoice.get("explicit_local_renderer")
    )
    contract = video_provider_router.product_video_route_contract(
        product_type,
        engine_adapter,
        orchestration_mode,
        explicit_local_renderer=explicit_local_renderer,
    )
    persisted_value = result.get("route_requires_provider")
    persisted_false_ignored = bool(contract.get("route_requires_provider") and persisted_value is False)
    return {
        **contract,
        "route_contract_product_type": product_type,
        "route_contract_engine_adapter": engine_adapter,
        "route_contract_orchestration_mode": orchestration_mode,
        "persisted_route_requires_provider_before_reconcile": persisted_value,
        "route_requirement_override": (
            "legacy_persisted_false_ignored"
            if persisted_false_ignored
            else str(result.get("route_requirement_override") or "")
        ),
        "route_requirement_product_contract": bool(contract.get("route_requires_provider")),
    }


def _product_video_scene_count(project: dict[str, Any], payload: dict[str, Any] | None = None) -> int:
    payload = dict(payload or {})
    invoice = _json_loads(str(project.get("invoice_json") or ""), {})
    if not isinstance(invoice, dict):
        invoice = {}
    return max(1, min(20, _as_int(project.get("scene_count") or payload.get("scene_count") or invoice.get("scene_count"), 1)))


def product_video_initial_scene_tasks(
    job_id: int | str,
    scene_count: int,
    scene_duration_seconds: int = PRODUCT_VIDEO_SCENE_SECONDS,
    scene_cards: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    safe_job_id = str(job_id or "").strip() or "job"
    safe_count = max(1, min(20, int(scene_count or 1)))
    safe_duration = max(
        1,
        min(
            PRODUCT_VIDEO_MAX_UIFLOW3_SCENE_SECONDS,
            int(scene_duration_seconds or PRODUCT_VIDEO_SCENE_SECONDS),
        ),
    )
    cards_by_index: dict[int, dict[str, Any]] = {}
    for fallback_index, raw_card in enumerate(scene_cards or [], start=1):
        if not isinstance(raw_card, dict):
            continue
        card = dict(raw_card)
        index = max(1, min(safe_count, _as_int(card.get("scene_index"), fallback_index)))
        cards_by_index[index] = card
    return [
        {
            "scene_index": index,
            "scene_id": index,
            "clip_index": index,
            "required": True,
            "request_job_id": f"{safe_job_id}-{index}",
            "scene_duration_seconds": safe_duration,
            "clip_duration_seconds": safe_duration,
            "provider": "",
            "provider_task_id": "",
            "provider_video_id": "",
            "primary_task_id": "",
            "fallback_task_ids": [],
            "active_task_id": "",
            "winning_task_id": "",
            "status": "queued_waiting_for_dispatch",
            "clip_status": "queued_waiting_for_dispatch",
            "dispatch_state": "queued_waiting_for_dispatch",
            "download_url_present": False,
            "result_url_valid": False,
            "raw_clip_duration": 0,
            "fallback_count": 0,
            "submitted_at": "",
            "submitted_at_epoch": 0,
            "started_at": "",
            "started_at_epoch": 0,
            "progress": 0,
            "progress_last_changed_at": "",
            "result_url": "",
            "clip_path": "",
            "clip_bytes": 0,
            "clip_valid": False,
            "scene_validation_verified": False,
            "completed_at": "",
            "failure_reason": "",
            "provider_wait_elapsed_seconds": 0,
            "provider_started_at_epoch": "",
            "scene_role": str(cards_by_index.get(index, {}).get("role") or ""),
            "scene_prompt": str(
                cards_by_index.get(index, {}).get("provider_prompt")
                or cards_by_index.get(index, {}).get("video_prompt")
                or ""
            ),
            "provider_prompt": str(
                cards_by_index.get(index, {}).get("provider_prompt")
                or cards_by_index.get(index, {}).get("video_prompt")
                or ""
            ),
            "image_prompt": str(cards_by_index.get(index, {}).get("image_prompt") or ""),
            "scene_prompt_source": "video_project_scene" if cards_by_index.get(index) else "",
        }
        for index in range(1, safe_count + 1)
    ]


def _product_video_orchestration_mode_from_sources(*sources: dict[str, Any] | None) -> str:
    product_video_seen = False
    requested_scene_count = 0
    for source in sources:
        if not isinstance(source, dict):
            continue
        if str(source.get("source") or "").strip() == "product_video" or _product_video_truthy(source.get("product_video")):
            product_video_seen = True
        requested_scene_count = max(requested_scene_count, _as_int(source.get("scene_count") or source.get("scenes_total"), 0))
        value = str(source.get("orchestration_mode") or source.get("provider_orchestration_mode") or "").strip().lower()
        if value in PRODUCT_VIDEO_PER_SCENE_ORCHESTRATION_ALIASES:
            return PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE
        if value in {"single_task", "legacy", "legacy_single_task", "single_task_legacy", "raw_render_delivery"}:
            return PRODUCT_VIDEO_ORCHESTRATION_MODE_RAW_DELIVERY
    if product_video_seen and requested_scene_count > 1:
        return PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE
    return PRODUCT_VIDEO_ORCHESTRATION_MODE_RAW_DELIVERY


def build_product_video_confirm_kickoff_payload(
    job: dict[str, Any],
    project: dict[str, Any],
    *,
    provider_chain: list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current_dt = now or datetime.now()
    scene_count = _product_video_scene_count(project)
    invoice = _json_loads(str(project.get("invoice_json") or ""), {})
    if not isinstance(invoice, dict):
        invoice = {}
    quote_state = _product_video_quote_consistency(invoice, project)
    asset_pack = _json_loads(str(project.get("asset_pack_json") or ""), {})
    if not isinstance(asset_pack, dict):
        asset_pack = {}
    scene_duration_limit = (
        PRODUCT_VIDEO_MAX_UIFLOW3_SCENE_SECONDS
        if str(asset_pack.get("uiflow3_handoff_sha256") or "").strip()
        else PRODUCT_VIDEO_SCENE_SECONDS
    )
    scene_duration = max(
        1,
        min(
            scene_duration_limit,
            _as_int(
                invoice.get("scene_duration_seconds")
                or invoice.get("scene_seconds")
                or asset_pack.get("scene_duration_seconds")
                or asset_pack.get("scene_seconds"),
                PRODUCT_VIDEO_SCENE_SECONDS,
            ),
        ),
    )
    requested_product_type = _product_video_requested_product_type(project, asset_pack, invoice)
    engine_contract = product_video_engine_contract(requested_product_type)
    execution_product_type = str(engine_contract.get("product_type") or requested_product_type)
    required_capability = str(engine_contract.get("required_capability") or "text_to_video")
    eligibility_snapshot = (
        asset_pack.get("provider_eligibility_snapshot")
        or invoice.get("provider_eligibility_snapshot")
        or {}
    )
    if not isinstance(eligibility_snapshot, dict):
        eligibility_snapshot = {}
    orchestration_mode = _product_video_orchestration_mode_from_sources(dict(job or {}), asset_pack, invoice, dict(project or {}))
    per_scene_orchestration = orchestration_mode == PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE
    render_pipeline_mode = (
        PRODUCT_VIDEO_RENDER_PIPELINE_HISTORICAL_CONCAT
        if per_scene_orchestration
        else PRODUCT_VIDEO_ORCHESTRATION_MODE_RAW_DELIVERY
    )
    project_scene_cards = _json_loads(str(project.get("scene_cards_json") or ""), [])
    if not isinstance(project_scene_cards, list):
        project_scene_cards = []
    scene_tasks = (
        product_video_initial_scene_tasks(
            job.get("id") or job.get("job_id") or "job",
            scene_count,
            scene_duration,
            scene_cards=[dict(item) for item in project_scene_cards if isinstance(item, dict)],
        )
        if per_scene_orchestration
        else []
    )
    if provider_chain is not None:
        chain = list(provider_chain)
    elif eligibility_snapshot.get("eligible_provider_keys") or asset_pack.get("preconfirm_candidate_keys") or invoice.get("preconfirm_candidate_keys"):
        chain = _split_product_video_provider_chain(
            eligibility_snapshot.get("eligible_provider_keys")
            or asset_pack.get("preconfirm_candidate_keys")
            or invoice.get("preconfirm_candidate_keys")
        )
    elif os.environ.get("VIDEO_PROVIDER_CHAIN") is not None:
        chain = resolve_product_video_provider_chain()
    else:
        source_chain = (
            asset_pack.get("provider_chain")
            or asset_pack.get("provider_order")
            or invoice.get("provider_chain")
            or invoice.get("provider_order")
            or ""
        )
        chain = _split_product_video_provider_chain(source_chain) or resolve_product_video_provider_chain()
    model_resolution = resolve_product_video_model(
        tier=_product_video_route_tier_value(invoice, project),
        provider_chain=chain,
        scene_count=scene_count,
        required_capability=required_capability,
        requires_concat=per_scene_orchestration,
    )
    model_metadata = model_metadata_from_resolution(model_resolution)
    if scene_tasks:
        for task in scene_tasks:
            task.update(
                {
                    "selected_provider": model_metadata.get("selected_provider") or "",
                    "selected_model": model_metadata.get("selected_model") or "",
                    "selected_family": model_metadata.get("selected_family") or "",
                    "selected_model_source": model_metadata.get("selected_model_source") or "",
                    "selected_payload_adapter": model_metadata.get("selected_payload_adapter") or "",
                    "selected_request_defaults": dict(model_metadata.get("selected_request_defaults") or {}),
                    "model_used": model_metadata.get("selected_model") or "",
                    "model_used_in_payload": model_metadata.get("selected_model") or "",
                    "provider_model_map": dict(model_metadata.get("provider_model_map") or {}),
                    "provider_request_defaults": {
                        str(key): dict(value)
                        for key, value in (model_metadata.get("provider_request_defaults") or {}).items()
                        if isinstance(value, dict)
                    },
                    "contract_validation_status": model_metadata.get("contract_validation_status") or "",
                    "supports_concat": bool(model_metadata.get("supports_concat")),
                }
            )
    next_poll_at = now_text(current_dt + timedelta(seconds=25))
    preconfirm_candidate_keys = [
        str(item or "").strip()
        for item in (
            eligibility_snapshot.get("eligible_provider_keys")
            or asset_pack.get("preconfirm_candidate_keys")
            or chain
        )
        if str(item or "").strip()
    ]
    provider_chain_resolved = bool(chain and preconfirm_candidate_keys and model_resolution.get("ok"))
    dispatch_blocker = ""
    if not chain:
        dispatch_blocker = "provider_chain_missing_no_charge"
    elif not model_resolution.get("ok"):
        dispatch_blocker = str(model_resolution.get("blocker") or "provider_contract_missing_no_charge")
    elif not quote_state.get("quote_consistent"):
        provider_chain_resolved = False
        dispatch_blocker = "product_video_quote_mismatch_no_charge"
    provider_health_at_submit = (
        asset_pack.get("provider_health_at_submit")
        or invoice.get("provider_health_at_submit")
        or asset_pack.get("provider_health_summary")
        or invoice.get("provider_health_summary")
        or {}
    )
    multi_scene_health_gate = (
        asset_pack.get("multi_scene_health_gate")
        or invoice.get("multi_scene_health_gate")
        or {}
    )
    # Keep the immutable UIFLOW3 handoff identity at the worker payload
    # boundary as well as inside the durable project asset pack.  Recovery,
    # worker admission, and artifact validation must be able to verify the
    # exact approved plan without reconstructing it from UI state.
    uiflow3_identity = {
        key: asset_pack.get(key) or invoice.get(key)
        for key in (
            "uiflow3_bridge_version",
            "uiflow3_draft_id",
            "uiflow3_owner_user_id",
            "uiflow3_owner_chat_id",
            "uiflow3_snapshot_config_hash",
            "uiflow3_handoff_sha256",
            "uiflow3_quote_sha256",
            "uiflow3_route_selection_sha256",
        )
        if asset_pack.get(key) not in (None, "") or invoice.get(key) not in (None, "")
    }
    return {
        "source": "product_video",
        "product_video": True,
        "public_product_type": requested_product_type,
        "video_product_type": requested_product_type,
        "product_type": execution_product_type,
        "executor_product_type": str(engine_contract.get("executor_product_type") or execution_product_type),
        "engine_route": str(engine_contract.get("engine_route") or ""),
        "engine_adapter": str(engine_contract.get("engine_adapter") or ""),
        "required_capability": required_capability,
        "input_type": str(engine_contract.get("input_type") or ""),
        "worker_owner": str(engine_contract.get("worker_owner") or "product_video"),
        "render_mode": "real",
        "provider_call": True,
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "original_submit_source": "public_user_final_confirm",
        "public_confirm_submit_source": "public_user_final_confirm",
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "charge_policy": "after_valid_mp4_delivery",
        "charge": 0,
        "charged_xu": 0,
        "no_charge_before_final_mp4": True,
        **quote_state,
        "orchestration_mode": orchestration_mode,
        "provider_orchestration_mode": orchestration_mode,
        "render_pipeline_mode": render_pipeline_mode,
        "raw_render_delivery_baseline": not per_scene_orchestration,
        "r18a_raw_render_delivery_default": not per_scene_orchestration,
        "scene_count": scene_count,
        "scenes_total": scene_count,
        "clip_count": scene_count if per_scene_orchestration else 0,
        "target_duration_seconds": scene_count * scene_duration,
        "clip_duration_seconds": scene_duration if per_scene_orchestration else 0,
        "scene_duration_seconds": scene_duration,
        "scene_seconds": scene_duration,
        "expected_duration_seconds": scene_count * scene_duration,
        "duration_seconds": scene_count * scene_duration,
        "scene_tasks": scene_tasks,
        "provider_scene_tasks": scene_tasks,
        "scene_tasks_total": scene_count if per_scene_orchestration else 0,
        "scene_tasks_created_count": scene_count if per_scene_orchestration else 0,
        "scene_tasks_submitted": 0,
        "scene_tasks_submitted_count": 0,
        "scene_tasks_completed": 0,
        "clips_created_count": scene_count if per_scene_orchestration else 0,
        "clips_submitted_count": 0,
        "clips_done_count": 0,
        "clips_failed_count": 0,
        "scenes_done": 0,
        "scenes_pending": scene_count if per_scene_orchestration else 0,
        "scenes_running": 0,
        "current_scene": 1 if per_scene_orchestration and scene_count else 0,
        "current_scene_index": 1 if per_scene_orchestration and scene_count else 0,
        "current_clip_index": 1 if per_scene_orchestration and scene_count else 0,
        "current_scene_status": "queued_waiting_for_dispatch" if per_scene_orchestration else "",
        "final_concat_required": bool(per_scene_orchestration and scene_count > 1),
        "concat_status": "waiting_for_clips" if per_scene_orchestration and scene_count > 1 else "",
        "concat_ready": False,
        "configured_provider_chain": chain,
        "effective_provider_chain": chain,
        "provider_chain": chain,
        "provider_order": chain,
        "provider_chain_resolved": provider_chain_resolved,
        "provider_eligibility_snapshot": eligibility_snapshot,
        "provider_eligibility_snapshot_id": str(eligibility_snapshot.get("provider_eligibility_snapshot_id") or asset_pack.get("provider_eligibility_snapshot_id") or ""),
        "preconfirm_candidate_keys": preconfirm_candidate_keys,
        "runtime_candidate_keys": preconfirm_candidate_keys,
        "candidate_set_consistent": True,
        "candidate_rejection_reason_by_provider": dict(eligibility_snapshot.get("candidate_rejection_reason_by_provider") or {}),
        "final_eligible_provider_count": len(preconfirm_candidate_keys),
        "provider_health_at_submit": provider_health_at_submit,
        "provider_route_ready_chain": list(asset_pack.get("provider_route_ready_chain") or invoice.get("provider_route_ready_chain") or []),
        "provider_live_healthy_chain": list(asset_pack.get("provider_live_healthy_chain") or invoice.get("provider_live_healthy_chain") or []),
        "multi_scene_health_gate": dict(multi_scene_health_gate) if isinstance(multi_scene_health_gate, dict) else {},
        "primary_selected_due_to_health": str(asset_pack.get("primary_selected_due_to_health") or invoice.get("primary_selected_due_to_health") or ""),
        "provider_degraded_reason": str(asset_pack.get("provider_degraded_reason") or invoice.get("provider_degraded_reason") or ""),
        "effective_primary_for_low_basic": str(asset_pack.get("effective_primary_for_low_basic") or invoice.get("effective_primary_for_low_basic") or (chain[0] if chain else "")),
        **model_metadata,
        "public_confirm_kickoff_attempted": True,
        "public_confirm_kickoff_success": provider_chain_resolved,
        "worker_dispatch_attempted": True,
        "worker_dispatch_success": provider_chain_resolved,
        "worker_dispatch_blocker": dispatch_blocker,
        "dispatch_status": "queued_for_worker" if provider_chain_resolved else dispatch_blocker,
        "actual_processor": "remote_worker" if provider_chain_resolved else "",
        "worker_service_mode": "owner_product_video" if provider_chain_resolved else "",
        "claimed_by_service_mode": "owner_product_video" if provider_chain_resolved else "",
        "worker_claim_status": "dispatch_queued" if provider_chain_resolved else "dispatch_blocked",
        "worker_claim_reason": dispatch_blocker,
        "next_poll_scheduled": provider_chain_resolved,
        "next_poll_scheduled_at": next_poll_at if provider_chain_resolved else "",
        "next_poll_at": next_poll_at if provider_chain_resolved else "",
        "next_refresh_expected_at": next_poll_at if provider_chain_resolved else "",
        "autonomous_db_poller_enabled": provider_chain_resolved,
        "autonomous_poll_enabled": provider_chain_resolved,
        "db_poll_candidate": provider_chain_resolved,
        "registry_required_for_poll": False,
        "registry_missing_is_blocker": False,
        "status_source_priority_used": "confirm_kickoff_db",
        "provider_router_called": False,
        "provider_submit_called": False,
        "provider_attempted": False,
        "provider_task_id_saved": False,
        "no_new_paid_submit": True,
        **uiflow3_identity,
    }


def _product_video_scene_task_identity(item: dict[str, Any] | None) -> str:
    item = dict(item or {})
    return str(
        item.get("winning_task_id")
        or item.get("active_task_id")
        or item.get("provider_task_id")
        or item.get("task_id")
        or item.get("provider_video_id")
        or item.get("video_id")
        or ""
    ).strip()


def product_video_zero_task_watchdog_state(
    job: dict[str, Any] | None,
    result: dict[str, Any] | None,
    *,
    now: datetime | None = None,
    dispatch_grace_seconds: int | None = None,
) -> dict[str, Any]:
    """Classify confirmed Product Video jobs that have not created any task."""
    job = dict(job or {})
    result = dict(result or {})
    current_dt = now or datetime.now()
    scene_count = max(
        1,
        min(
            20,
            _as_int(
                result.get("scene_count")
                or result.get("scenes_total")
                or result.get("scene_tasks_total")
                or job.get("scene_count"),
                1,
            ),
        ),
    )
    scene_rows: list[dict[str, Any]] = []
    for key in ("scene_tasks", "provider_scene_tasks", "product_video_scene_tasks", "scene_ledger"):
        value = result.get(key)
        if isinstance(value, list):
            scene_rows.extend(dict(item) for item in value if isinstance(item, dict))
        elif isinstance(value, dict):
            for index, item in value.items():
                row = dict(item or {}) if isinstance(item, dict) else {}
                row.setdefault("scene_index", index)
                scene_rows.append(row)
    task_ids = {
        _product_video_scene_task_identity(item)
        for item in scene_rows
        if _product_video_scene_task_identity(item)
    }
    for key in ("provider_task_ids", "provider_video_ids"):
        values = result.get(key)
        if isinstance(values, (list, tuple)):
            task_ids.update(str(item or "").strip() for item in values if str(item or "").strip())
    for key in ("provider_pending_task_id", "provider_pending_video_id", "canonical_task_selected"):
        value = str(result.get(key) or "").strip()
        if value:
            task_ids.add(value)
    valid_provider_task_count = len(task_ids)
    valid_scene_clip_indexes = {
        _product_video_scene_task_index(item)
        for item in scene_rows
        if _product_video_scene_task_index(item) > 0
        and _product_video_scene_task_is_valid_clip(item)
        and bool(
            item.get("clip_valid")
            or item.get("validation_passed")
            or item.get("output_validated")
            or _as_int(item.get("clip_bytes") or item.get("artifact_size") or item.get("output_bytes"), 0) > 0
        )
    }
    valid_scene_clip_count = len(valid_scene_clip_indexes)
    grace_seconds = max(
        1,
        _as_int(
            dispatch_grace_seconds
            if dispatch_grace_seconds is not None
            else result.get("dispatch_grace_seconds")
            or os.getenv("VIDEO_SCENE_DISPATCH_GRACE_SECONDS"),
            VIDEO_SCENE_DISPATCH_GRACE_SECONDS_DEFAULT,
        ),
    )
    started_epoch = _parse_time_epoch(
        result.get("public_confirmed_at")
        or result.get("confirmed_at")
        or job.get("created_at")
        or job.get("updated_at")
    )
    elapsed_from_clock = int(max(0, current_dt.timestamp() - started_epoch)) if started_epoch > 0 else 0
    grace_elapsed = max(
        elapsed_from_clock,
        _as_int(
            result.get("dispatch_grace_elapsed")
            or result.get("provider_elapsed_seconds")
            or result.get("provider_wait_elapsed_seconds"),
            0,
        ),
    )
    runtime_candidates_explicit = bool(
        "runtime_candidate_keys" in result
        or "provider_candidates_count" in result
        or result.get("provider_router_called")
    )
    if "runtime_candidate_keys" in result:
        runtime_candidates = [str(item or "").strip() for item in (result.get("runtime_candidate_keys") or []) if str(item or "").strip()]
    elif runtime_candidates_explicit and _as_int(result.get("provider_candidates_count"), 0) <= 0:
        runtime_candidates = []
    else:
        snapshot = result.get("provider_eligibility_snapshot") if isinstance(result.get("provider_eligibility_snapshot"), dict) else {}
        runtime_candidates = [
            str(item or "").strip()
            for item in (
                snapshot.get("eligible_provider_keys")
                or result.get("preconfirm_candidate_keys")
                or result.get("effective_provider_chain")
                or []
            )
            if str(item or "").strip()
        ]
    preconfirm_candidates = [
        str(item or "").strip()
        for item in (
            result.get("preconfirm_candidate_keys")
            or (result.get("provider_eligibility_snapshot") or {}).get("eligible_provider_keys")
            or []
        )
        if str(item or "").strip()
    ]
    zero_tasks = valid_provider_task_count == 0 and valid_scene_clip_count == 0
    terminal_scene_states = {"failed", "error", "exhausted", "terminal_failed", "failed_no_charge"}
    explicit_terminal_scene_failure = bool(scene_rows) and all(
        str(item.get("dispatch_state") or item.get("status") or item.get("clip_status") or "").strip().lower()
        in terminal_scene_states
        or bool(item.get("exhausted"))
        for item in scene_rows
    )
    existing_terminal_no_charge = bool(
        str(result.get("terminal_state") or result.get("aggregate_status") or result.get("final_decision") or "").strip().lower()
        == "failed_no_charge"
        and explicit_terminal_scene_failure
    )
    watchdog_triggered = bool(zero_tasks and grace_elapsed >= grace_seconds)
    no_eligible_provider = bool(watchdog_triggered and runtime_candidates_explicit and not runtime_candidates)
    terminal_reason = (
        str(result.get("aggregate_reason") or result.get("provider_error") or "required_scene_exhausted_no_charge")
        if existing_terminal_no_charge
        else ("no_eligible_provider_before_scene_dispatch" if no_eligible_provider else "")
    )
    failed_no_charge = bool(existing_terminal_no_charge or no_eligible_provider)
    if failed_no_charge:
        scene_state = "terminal_failed"
    elif watchdog_triggered and runtime_candidates:
        scene_state = "queued_waiting_for_dispatch"
    elif zero_tasks:
        scene_state = "queued_waiting_for_dispatch"
    else:
        scene_state = "task_submitted"
    attempts = [
        dict(item)
        for item in (result.get("provider_attempts") or result.get("provider_pending_attempts") or [])
        if isinstance(item, dict)
    ]
    actual_submit_attempts = [
        item
        for item in attempts
        if bool(item.get("provider_http_request_sent"))
        or _as_int(item.get("provider_http_status") or item.get("submit_http_status"), 0) > 0
    ]
    return {
        "zero_task_watchdog_triggered": watchdog_triggered,
        "dispatch_grace_seconds": grace_seconds,
        "dispatch_grace_elapsed": grace_elapsed,
        "valid_provider_task_count": valid_provider_task_count,
        "valid_scene_clip_count": valid_scene_clip_count,
        "zero_task_progress_guard": zero_tasks,
        "progress_suppressed_without_task": zero_tasks,
        "public_stage": "preparing" if zero_tasks and not failed_no_charge else ("failed_no_charge" if failed_no_charge else "rendering"),
        "undispatched_scene_indexes": list(range(1, scene_count + 1)) if zero_tasks else [],
        "dispatch_recovery_attempted": bool(watchdog_triggered and runtime_candidates),
        "dispatch_recovery_result": "eligible_for_scene_claim" if watchdog_triggered and runtime_candidates else (terminal_reason or "waiting_for_dispatch_grace"),
        "zero_task_terminal_reason": terminal_reason,
        "runtime_candidates_evaluated": runtime_candidates_explicit,
        "preconfirm_candidate_keys": preconfirm_candidates,
        "runtime_candidate_keys": runtime_candidates,
        "candidate_set_consistent": runtime_candidates == preconfirm_candidates if runtime_candidates_explicit else True,
        "final_eligible_provider_count": len(runtime_candidates),
        "scene_dispatch_state_by_index": {str(index): scene_state for index in range(1, scene_count + 1)},
        "candidate_evaluated_count": _as_int(result.get("candidate_evaluated_count"), len(runtime_candidates)),
        "candidate_preflight_rejected_count": _as_int(result.get("candidate_preflight_rejected_count"), 0),
        "submit_invoked_count": len([item for item in attempts if item.get("submit_called")]),
        "submit_accepted_count": len([item for item in attempts if item.get("submit_accepted")]),
        "task_created_count": valid_provider_task_count,
        "provider_http_request_sent": bool(actual_submit_attempts),
        "provider_http_status": max(
            [_as_int(item.get("provider_http_status") or item.get("submit_http_status"), 0) for item in actual_submit_attempts]
            or [0]
        ),
        "fallback_count_effective": len(actual_submit_attempts[1:]),
        "failed_no_charge": failed_no_charge,
        "continue_polling": bool(zero_tasks and not failed_no_charge),
        "charge": 0,
        "charged_xu": 0,
    }


def product_video_processing_scene_claim_state(
    job: dict[str, Any] | None,
    result: dict[str, Any] | None,
    *,
    now: datetime | None = None,
    worker_id: str = "",
    lease_seconds: int = 600,
) -> dict[str, Any]:
    job = dict(job or {})
    result = dict(result or {})
    current_dt = now or datetime.now()
    watchdog = product_video_zero_task_watchdog_state(job, result, now=current_dt)
    scene_count = max(
        1,
        _as_int(
            result.get("scene_count")
            or result.get("scenes_total")
            or result.get("scene_tasks_total")
            or job.get("scene_count"),
            1,
        ),
    )
    leases = result.get("scene_dispatch_lease_by_index") if isinstance(result.get("scene_dispatch_lease_by_index"), dict) else {}
    tasks = result.get("scene_tasks") if isinstance(result.get("scene_tasks"), list) else []
    task_by_index = {_as_int(item.get("scene_index"), 0): dict(item) for item in tasks if isinstance(item, dict)}
    runtime_candidates_explicit = bool(
        "runtime_candidate_keys" in result
        and (
            result.get("runtime_candidates_evaluated")
            or result.get("admission_enforced")
            or result.get("admission_rechecked_before_dispatch")
        )
    )
    eligible_candidates = [
        str(item or "").strip()
        for item in (
            result.get("runtime_candidate_keys")
            if runtime_candidates_explicit
            else (result.get("runtime_candidate_keys") or result.get("preconfirm_candidate_keys") or [])
        )
        if str(item or "").strip()
    ]
    claimable_by_index: dict[str, bool] = {}
    block_reason_by_index: dict[str, str] = {}
    stale_recovered = False
    now_epoch = current_dt.timestamp()
    for index in range(1, scene_count + 1):
        item = task_by_index.get(index, {})
        lease = dict(leases.get(str(index)) or {}) if isinstance(leases.get(str(index)), dict) else {}
        lease_expiry = _parse_time_epoch(lease.get("lease_expires_at"))
        lease_active = bool(lease.get("lease_owner") and lease_expiry > now_epoch)
        if lease.get("lease_owner") and lease_expiry and lease_expiry <= now_epoch:
            stale_recovered = True
        if _product_video_scene_task_identity(item):
            claimable = False
            reason = "scene_task_already_exists"
        elif item.get("winning_task_id") or item.get("clip_valid"):
            claimable = False
            reason = "scene_winning_clip_exists"
        elif watchdog.get("failed_no_charge"):
            claimable = False
            reason = str(watchdog.get("zero_task_terminal_reason") or "scene_terminal")
        elif not eligible_candidates:
            claimable = False
            reason = "no_eligible_provider_for_scene_dispatch"
        elif lease_active:
            claimable = False
            reason = "scene_dispatch_lease_active"
        else:
            claimable = True
            reason = ""
        claimable_by_index[str(index)] = claimable
        block_reason_by_index[str(index)] = reason
    return {
        **watchdog,
        "processing_job_scene_claimable": any(claimable_by_index.values()),
        "scene_claimable_by_index": claimable_by_index,
        "scene_dispatch_lease_by_index": leases,
        "stale_dispatch_lease_recovered": stale_recovered,
        "claim_block_reason_by_scene": block_reason_by_index,
        "lease_seconds": max(30, int(lease_seconds or 600)),
    }


def acquire_product_video_scene_dispatch_leases(
    job: dict[str, Any],
    result: dict[str, Any],
    *,
    worker_id: str,
    now: datetime | None = None,
    lease_seconds: int = 600,
) -> dict[str, Any]:
    current_dt = now or datetime.now()
    state = product_video_processing_scene_claim_state(
        job,
        result,
        now=current_dt,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
    )
    updated = dict(result or {})
    leases = dict(state.get("scene_dispatch_lease_by_index") or {})
    runtime_candidates_explicit = bool(
        "runtime_candidate_keys" in updated
        and (
            updated.get("runtime_candidates_evaluated")
            or updated.get("admission_enforced")
            or updated.get("admission_rechecked_before_dispatch")
        )
    )
    candidates = list(
        updated.get("runtime_candidate_keys")
        if runtime_candidates_explicit
        else (state.get("runtime_candidate_keys") or state.get("preconfirm_candidate_keys") or [])
    )
    provider_key = str(candidates[0] if candidates else "")
    expires_at = now_text(current_dt + timedelta(seconds=max(30, int(lease_seconds or 600))))
    job_id = _as_int(job.get("id") or job.get("job_id"), 0)
    for index_text, claimable in (state.get("scene_claimable_by_index") or {}).items():
        if not claimable:
            continue
        index = _as_int(index_text, 0)
        leases[str(index)] = {
            "job_id": job_id,
            "scene_index": index,
            "provider_key": provider_key,
            "lease_owner": str(worker_id or "")[:120],
            "lease_acquired_at": now_text(current_dt),
            "lease_expires_at": expires_at,
            "idempotency_key": f"product-video:{job_id}:scene:{index}:provider:{provider_key or 'unassigned'}",
        }
    updated.update(state)
    updated["scene_dispatch_lease_by_index"] = leases
    updated["processing_job_scene_claimable"] = bool(state.get("processing_job_scene_claimable"))
    return updated


def product_video_failed_no_charge_terminal_payload(
    result: dict[str, Any] | None,
    *,
    scene_count: int,
    reason: str,
    reconciliation_source: str,
    reconciliation_run_id: str,
    reconciled_at: str,
) -> dict[str, Any]:
    """Canonical zero-task terminal truth shared by watchdog/status/claim recovery."""
    current = dict(result or {})
    source = normalize_product_video_reconciliation_source(reconciliation_source)
    count = max(1, _as_int(scene_count, 1))
    scene_status = {str(index): "terminal_failed" for index in range(1, count + 1)}
    tasks: list[dict[str, Any]] = []
    for offset, item in enumerate(current.get("scene_tasks") or [], start=1):
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row["scene_index"] = max(1, _as_int(row.get("scene_index"), offset))
        row["status"] = "terminal_failed"
        row["current_scene_status"] = "terminal_failed"
        row["continue_polling"] = False
        row["next_poll_at"] = ""
        tasks.append(row)
    return {
        **current,
        "status": "failed",
        "canonical_status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "final_decision": "failed_no_charge",
        "terminal": True,
        "continue_polling": False,
        "next_poll_scheduled": False,
        "next_poll_scheduled_at": "",
        "next_poll_at": "",
        "next_scene_poll_at": "",
        "next_refresh_expected_at": "",
        "auto_refresh_next_tick_at": "",
        "fallback_allowed": False,
        "fallback_provider_candidate": "",
        "fallback_candidate": "",
        "next_provider_or_model_candidate": "",
        "dispatch_status": "terminal_failed",
        "dispatch_outbox_status": "terminal_failed",
        "dispatch_outbox_claimable": False,
        "scene_status": "terminal_failed",
        "current_scene_status": "terminal_failed",
        "scene_status_by_scene": scene_status,
        "scene_tasks": tasks,
        "provider_task_alive": False,
        "provider_submit_called": False,
        "provider_http_request_sent": False,
        "provider_http_status": 0,
        "fallback_count_effective": 0,
        "concat_attempted": False,
        "delivery_attempted": False,
        "charge": 0,
        "charged_xu": 0,
        "wallet_charge_recorded": False,
        "reconciliation_source": source,
        "reconciliation_run_id": str(reconciliation_run_id or ""),
        "reconciliation_at": str(reconciled_at or now_text()),
        "reconciliation_reason": str(reason or "no_eligible_provider_before_scene_dispatch"),
    }


def sweep_product_video_zero_task_watchdog(
    conn: sqlite3.Connection,
    *,
    now: datetime | None = None,
    eligibility_evaluator: Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None,
    job_id: int = 0,
    limit: int = 50,
    reconciliation_source: str = "watchdog_scheduler",
    reconciliation_run_id: str = "",
) -> dict[str, Any]:
    """Reconcile zero-task Product Video jobs from durable DB state only."""
    ensure_video_project_queue_schema(conn)
    current_dt = now or datetime.now()
    current = now_text(current_dt)
    outbox_current = product_video_outbox_time_text(current_dt)
    source = normalize_product_video_reconciliation_source(reconciliation_source, "watchdog_scheduler")
    run_id = str(reconciliation_run_id or f"pv-reconcile-{uuid.uuid4().hex}")
    params: list[Any] = [VIDEO_RENDER_JOB_TYPE]
    wanted = int(job_id or 0)
    extra = ""
    if wanted > 0:
        extra = " AND j.id=?"
        params.append(wanted)
    params.append(max(1, int(limit or 50)))
    rows = conn.execute(
        f"""SELECT j.id,j.project_id
              FROM video_jobs j
              JOIN video_projects p ON p.project_id=j.project_id
             WHERE j.job_type=? AND j.status IN ('queued','processing','failed')
               AND COALESCE(p.is_confirmed,0)=1
               AND p.status IN ('queued_for_worker','processing','failed'){extra}
             ORDER BY j.created_at ASC,j.id ASC
             LIMIT ?""",
        params,
    ).fetchall()
    report = {
        "reconciliation_source": source,
        "reconciliation_run_id": run_id,
        "reconciliation_at": current,
        "scanned": 0,
        "checked": 0,
        "triggered": 0,
        "recovered": 0,
        "terminal_failed": 0,
        "kept_by_active_lease": 0,
        "details": [],
    }
    for row in rows:
        job = get_video_render_job(conn, int(row[0]))
        project = get_video_project(conn, int(row[1]))
        if not job or not project or not _is_product_video_project(project):
            continue
        report["scanned"] += 1
        result = _json_loads(str(job.get("result_json") or ""), {})
        if not isinstance(result, dict):
            result = {}
        if str(job.get("status") or "").strip().lower() == "failed":
            recovery = recover_product_video_premature_dispatch_failure(
                conn,
                job_id=int(job["id"]),
                now=current_dt,
                worker_compatible=bool(
                    result.get("worker_compatible")
                    or result.get("admission_worker_version_compatible")
                    or result.get("worker_connected")
                ),
            )
            if not recovery.get("premature_dispatch_recovered"):
                continue
            report["recovered"] += 1
            job = get_video_render_job(conn, int(row[0]))
            project = get_video_project(conn, int(row[1]))
            result = _json_loads(str(job.get("result_json") or ""), {})
            if not isinstance(result, dict):
                result = {}
        result.update(canonical_product_video_route_contract(project, result))
        preliminary = product_video_zero_task_watchdog_state(job, result, now=current_dt)
        if not preliminary.get("zero_task_progress_guard"):
            continue
        report["checked"] += 1
        worker_scan = {
            "worker_scan_seen_job": True,
            "worker_scan_seen_outbox": bool(get_product_video_dispatch_outbox(conn, job_id=int(job["id"]))),
            "worker_claim_attempted": False,
            "worker_claim_result": "watchdog_scan",
            "worker_claim_block_reason": "",
            "worker_last_scan_at": current,
            "worker_next_scan_at": now_text(current_dt + timedelta(seconds=5)),
        }
        if not preliminary.get("zero_task_watchdog_triggered"):
            result.update(
                {
                    **preliminary,
                    **worker_scan,
                    "zero_task_watchdog_checked_at": current,
                    "zero_task_elapsed_seconds": _as_int(preliminary.get("dispatch_grace_elapsed"), 0),
                    "zero_task_candidate_count": _as_int(preliminary.get("final_eligible_provider_count"), 0),
                    "zero_task_recovery_action": "wait_dispatch_grace",
                    "reconciliation_source": source,
                    "reconciliation_run_id": run_id,
                    "reconciliation_at": current,
                    "reconciliation_reason": "wait_dispatch_grace",
                }
            )
            conn.execute(
                "UPDATE video_jobs SET result_json=?,progress_percent=?,progress_message='queued_waiting_for_dispatch',updated_at=? WHERE id=?",
                (_json_dumps(result), min(20, max(10, _as_int(job.get("progress_percent"), 10))), current, int(job["id"])),
            )
            conn.commit()
            continue
        report["triggered"] += 1
        eligibility: dict[str, Any] = {}
        if callable(eligibility_evaluator):
            try:
                eligibility = dict(eligibility_evaluator(job, result, project) or {})
            except Exception as exc:
                eligibility = {
                    "eligible_provider_keys": [],
                    "runtime_candidate_keys": [],
                    "final_eligible_provider_count": 0,
                    "admission_block_reason": f"eligibility_recheck_failed:{type(exc).__name__}",
                }
        if eligibility:
            candidates = [
                str(item or "").strip()
                for item in (
                    eligibility.get("runtime_candidate_keys")
                    or eligibility.get("eligible_provider_keys")
                    or eligibility.get("admission_candidate_keys")
                    or []
                )
                if str(item or "").strip()
            ]
            result.update(
                {
                    "provider_eligibility_snapshot": eligibility.get("provider_eligibility_snapshot") or eligibility,
                    "provider_eligibility_snapshot_id": str(
                        eligibility.get("provider_eligibility_snapshot_id")
                        or result.get("provider_eligibility_snapshot_id")
                        or ""
                    ),
                    "runtime_candidate_keys": candidates,
                    "final_eligible_provider_count": len(candidates),
                    "candidate_rejection_reason_by_provider": dict(
                        eligibility.get("candidate_rejection_reason_by_provider") or {}
                    ),
                    "candidate_resolver_source": str(eligibility.get("candidate_resolver_source") or ""),
                    "candidate_resolver_public_user_confirmed": bool(
                        eligibility.get("candidate_resolver_public_user_confirmed")
                    ),
                    "provider_submit_allowed": bool(eligibility.get("provider_submit_allowed")),
                    "provider_submit_block_reason": str(
                        eligibility.get("provider_submit_block_reason")
                        or eligibility.get("provider_submit_block_reason_at_candidate_resolver")
                        or ("" if candidates else eligibility.get("blocker") or "no_eligible_provider_before_scene_dispatch")
                    ),
                    "router_skip_reason": str(
                        eligibility.get("router_skip_reason")
                        or ("" if candidates else eligibility.get("blocker") or "no_eligible_provider_before_scene_dispatch")
                    ),
                    "candidates_before_filter": list(eligibility.get("candidates_before_filter") or []),
                    "candidates_after_route_filter": list(eligibility.get("candidates_after_route_filter") or []),
                    "candidates_after_freeze_filter": list(eligibility.get("candidates_after_freeze_filter") or []),
                    "candidates_after_health_filter": list(eligibility.get("candidates_after_health_filter") or []),
                    "candidates_after_hard_block_filter": list(eligibility.get("candidates_after_hard_block_filter") or []),
                    "probation_candidate": str(
                        eligibility.get("probation_candidate_selected")
                        or eligibility.get("probation_candidate")
                        or ""
                    ),
                    "probation_eligible": bool(eligibility.get("probation_eligible")),
                    "probation_reject_reason": str(eligibility.get("probation_reject_reason") or ""),
                }
            )
        watchdog = product_video_zero_task_watchdog_state(job, result, now=current_dt)
        candidates = list(watchdog.get("runtime_candidate_keys") or [])
        outbox = get_product_video_dispatch_outbox(conn, job_id=int(job["id"]))
        outbox_lease_active = bool(
            outbox.get("dispatch_status") == "leased"
            and _parse_time_epoch(outbox.get("lease_expires_at")) > current_dt.timestamp()
        )
        scene_claim = product_video_processing_scene_claim_state(job, result, now=current_dt)
        scene_leases = dict(scene_claim.get("scene_dispatch_lease_by_index") or {})
        scene_lease_active = any(
            str(item.get("lease_owner") or "")
            and _parse_time_epoch(item.get("lease_expires_at")) > current_dt.timestamp()
            for item in scene_leases.values()
            if isinstance(item, dict)
        )
        active_lease = bool(outbox_lease_active or scene_lease_active)
        recovery_action = ""
        terminal_reason = ""
        claim_attempt_count = max(
            _as_int(result.get("dispatch_claim_attempt_count"), 0),
            _as_int(outbox.get("attempt_count"), 0),
        )
        max_claim_attempts = max(1, _as_int(job.get("max_attempts"), 3))
        claim_retries_exhausted = bool(
            result.get("dispatch_retry_exhausted")
            or (
                claim_attempt_count >= max_claim_attempts
                and bool(outbox.get("last_attempt_at"))
            )
        )
        explicit_admission_block = bool(
            eligibility and eligibility.get("ok") is False
        )
        if (
            not candidates
            and not active_lease
            and not claim_retries_exhausted
            and not explicit_admission_block
        ):
            if not outbox:
                outbox = ensure_product_video_dispatch_outbox(
                    conn,
                    job_id=int(job["id"]),
                    project_id=int(project["project_id"]),
                    scene_indexes=list(range(1, max(1, _as_int(result.get("scene_count"), 1)) + 1)),
                    now=current_dt,
                )
            wait_reason = str(
                eligibility.get("provider_submit_block_reason")
                or eligibility.get("provider_submit_block_reason_at_candidate_resolver")
                or eligibility.get("blocker")
                or "no_eligible_provider_before_scene_dispatch"
            )
            result.update(
                {
                    **watchdog,
                    **worker_scan,
                    "status": "queued",
                    "canonical_status": "queued_waiting_for_dispatch",
                    "terminal_state": "",
                    "final_decision": "retry_dispatch",
                    "terminal": False,
                    "continue_polling": True,
                    "next_poll_scheduled": True,
                    "zero_task_watchdog_checked_at": current,
                    "zero_task_recovery_action": "await_due_claim_retry",
                    "zero_task_terminal_reason": "",
                    "provider_submit_allowed": False,
                    "provider_submit_block_reason": wait_reason,
                    "provider_router_called": False,
                    "router_skip_reason": f"outbox_not_claimable_{wait_reason}",
                    "dispatch_claim_attempt_count": claim_attempt_count,
                    "dispatch_claim_failure_count": max(
                        _as_int(result.get("dispatch_claim_failure_count"), 0),
                        claim_attempt_count,
                    ),
                    "dispatch_retry_exhausted": False,
                    "dispatch_terminal_transition_source": "",
                    "dispatch_outbox_present": bool(outbox),
                    "dispatch_outbox_status": str(outbox.get("dispatch_status") or "pending"),
                    "charge": 0,
                    "charged_xu": 0,
                }
            )
            conn.execute(
                """UPDATE video_jobs
                      SET status='queued',result_json=?,progress_percent=10,
                          progress_message='queued_waiting_for_dispatch',locked_by='',locked_at=NULL,
                          lease_expires_at=NULL,completed_at=NULL,updated_at=?
                    WHERE id=?""",
                (_json_dumps(result), current, int(job["id"])),
            )
            conn.execute(
                "UPDATE video_projects SET status='queued_for_worker',video_terminal_state='',updated_at=? WHERE project_id=?",
                (current, int(project["project_id"])),
            )
            conn.commit()
            report["details"].append(
                {
                    "job_id": int(job["id"]),
                    "project_id": int(project["project_id"]),
                    "action": "await_due_claim_retry",
                    "reason": wait_reason,
                    "claim_attempt_count": claim_attempt_count,
                    "max_claim_attempts": max_claim_attempts,
                }
            )
            continue
        if not candidates and not active_lease:
            if not outbox:
                outbox = ensure_product_video_dispatch_outbox(
                    conn,
                    job_id=int(job["id"]),
                    project_id=int(project["project_id"]),
                    scene_indexes=list(range(1, max(1, _as_int(result.get("scene_count"), 1)) + 1)),
                    now=current_dt,
                )
            terminal_reason = str(
                eligibility.get("provider_submit_block_reason")
                or eligibility.get("provider_submit_block_reason_at_candidate_resolver")
                or eligibility.get("reconciliation_reason")
                or eligibility.get("worker_admission_block_reason")
                or "no_eligible_provider_before_scene_dispatch"
            )
            recovery_action = "failed_no_charge"
            result = product_video_failed_no_charge_terminal_payload(
                {
                    **result,
                    **watchdog,
                    **worker_scan,
                    "zero_task_watchdog_checked_at": current,
                    "zero_task_watchdog_triggered": True,
                    "zero_task_elapsed_seconds": _as_int(watchdog.get("dispatch_grace_elapsed"), 0),
                    "zero_task_candidate_count": 0,
                    "zero_task_recovery_action": recovery_action,
                    "zero_task_terminal_reason": terminal_reason,
                    "provider_submit_allowed": False,
                    "provider_submit_block_reason": terminal_reason,
                    "router_called": False,
                    "router_skip_reason": terminal_reason,
                    "original_admission_snapshot": result.get("provider_eligibility_snapshot") or {},
                    "handler_id_that_created_job": str(result.get("admission_callback_handler_id") or ""),
                    "worker_sha_at_creation": str(result.get("admission_worker_sha") or ""),
                    "runtime_sha_at_creation": str(result.get("admission_worker_runtime_sha") or ""),
                    "no_provider_call_verified": not bool(watchdog.get("provider_http_request_sent")),
                    "no_charge_verified": _as_int(result.get("charged_xu") or result.get("charge"), 0) == 0,
                    "worker_claim_result": "blocked_no_eligible_provider",
                    "worker_claim_block_reason": terminal_reason,
                    "dispatch_claim_attempt_count": claim_attempt_count,
                    "dispatch_claim_failure_count": max(
                        _as_int(result.get("dispatch_claim_failure_count"), 0),
                        claim_attempt_count,
                    ),
                    "dispatch_retry_exhausted": True,
                    "dispatch_terminal_transition_source": "dispatch_claim_retry_exhausted",
                    "dispatch_outbox_present": bool(outbox),
                    "dispatch_outbox_status": "terminal_failed" if outbox else "",
                },
                scene_count=max(1, _as_int(result.get("scene_count"), 1)),
                reason=terminal_reason,
                reconciliation_source=source,
                reconciliation_run_id=run_id,
                reconciled_at=current,
            )
            conn.execute(
                """UPDATE video_jobs
                      SET status='failed',result_json=?,progress_percent=?,progress_message=?,last_error=?,
                          completed_at=COALESCE(completed_at,?),updated_at=?
                    WHERE id=?""",
                (_json_dumps(result), 10, terminal_reason, terminal_reason, current, current, int(job["id"])),
            )
            conn.execute(
                """UPDATE video_projects
                      SET status='failed',video_terminal_state='failed_no_charge',error_log=?,updated_at=?
                    WHERE project_id=?""",
                (terminal_reason, current, int(project["project_id"])),
            )
            if outbox:
                conn.execute(
                    """UPDATE video_dispatch_outbox
                          SET dispatch_status='terminal_failed',terminal_reason=?,last_error=?,
                              lease_owner='',lease_expires_at=NULL,updated_at=?
                        WHERE outbox_id=?""",
                    (terminal_reason, terminal_reason, current, int(outbox["outbox_id"])),
                )
            conn.execute(
                "UPDATE video_scenes SET scene_status='terminal_failed' WHERE project_id=?",
                (int(project["project_id"]),),
            )
            conn.commit()
            report["terminal_failed"] += 1
        elif active_lease:
            recovery_action = "active_dispatch_lease"
            result.update(
                {
                    **watchdog,
                    **worker_scan,
                    "zero_task_watchdog_checked_at": current,
                    "zero_task_watchdog_triggered": True,
                    "zero_task_elapsed_seconds": _as_int(watchdog.get("dispatch_grace_elapsed"), 0),
                    "zero_task_candidate_count": len(candidates),
                    "zero_task_recovery_action": recovery_action,
                    "zero_task_terminal_reason": "",
                    "reconciliation_source": source,
                    "reconciliation_run_id": run_id,
                    "reconciliation_at": current,
                    "reconciliation_reason": recovery_action,
                    "continue_polling": True,
                    "public_stage": "preparing",
                    "worker_claim_result": "active_dispatch_lease",
                    "worker_claim_block_reason": "dispatch_lease_active",
                }
            )
            conn.execute(
                "UPDATE video_jobs SET result_json=?,progress_percent=?,progress_message='dispatch_lease_active',updated_at=? WHERE id=?",
                (_json_dumps(result), min(20, max(10, _as_int(job.get("progress_percent"), 10))), current, int(job["id"])),
            )
            conn.commit()
            report["kept_by_active_lease"] += 1
        else:
            if not outbox:
                outbox = ensure_product_video_dispatch_outbox(
                    conn,
                    job_id=int(job["id"]),
                    project_id=int(project["project_id"]),
                    scene_indexes=list(range(1, max(1, _as_int(result.get("scene_count"), 1)) + 1)),
                    now=current_dt,
                )
                recovery_action = "dispatch_outbox_recreated"
            elif str(outbox.get("dispatch_status") or "") in {"acknowledged", "leased"}:
                conn.execute(
                    """UPDATE video_dispatch_outbox
                          SET dispatch_status='retry_wait',available_at=?,lease_owner='',lease_expires_at=NULL,
                              last_error='zero_task_dispatch_recovery',updated_at=?
                        WHERE outbox_id=?""",
                    (outbox_current, current, int(outbox["outbox_id"])),
                )
                conn.commit()
                outbox = get_product_video_dispatch_outbox(conn, job_id=int(job["id"]))
                recovery_action = "dispatch_outbox_retry_recovered"
            else:
                recovery_action = "dispatch_outbox_pending"
            result.update(
                {
                    **watchdog,
                    **worker_scan,
                    "zero_task_watchdog_checked_at": current,
                    "zero_task_watchdog_triggered": True,
                    "zero_task_elapsed_seconds": _as_int(watchdog.get("dispatch_grace_elapsed"), 0),
                    "zero_task_candidate_count": len(candidates),
                    "zero_task_recovery_action": recovery_action,
                    "zero_task_terminal_reason": "",
                    "reconciliation_source": source,
                    "reconciliation_run_id": run_id,
                    "reconciliation_at": current,
                    "reconciliation_reason": recovery_action,
                    "continue_polling": True,
                    "public_stage": "preparing",
                    "dispatch_outbox_present": bool(outbox),
                    "dispatch_outbox_status": str(outbox.get("dispatch_status") or "pending"),
                    "dispatch_outbox_attempt_count": _as_int(outbox.get("attempt_count"), 0),
                    "dispatch_outbox_lease_owner": str(outbox.get("lease_owner") or ""),
                    "dispatch_outbox_lease_expires_at": str(outbox.get("lease_expires_at") or ""),
                    "dispatch_outbox_last_error": str(outbox.get("last_error") or ""),
                    "dispatch_outbox_acknowledged": bool(outbox.get("acknowledged_at")),
                    "worker_claim_result": recovery_action,
                }
            )
            conn.execute(
                "UPDATE video_jobs SET result_json=?,progress_percent=?,progress_message='queued_waiting_for_dispatch',updated_at=? WHERE id=?",
                (_json_dumps(result), min(20, max(10, _as_int(job.get("progress_percent"), 10))), current, int(job["id"])),
            )
            conn.commit()
            report["recovered"] += 1
        outbox_diagnostic = product_video_dispatch_outbox_diagnostic(
            conn,
            job_id=int(job["id"]),
            now=current_dt,
        )
        latest_job = get_video_render_job(conn, int(job["id"]))
        latest_result = _json_loads(str((latest_job or {}).get("result_json") or ""), {})
        if isinstance(latest_result, dict):
            latest_result.update(
                {
                    key: value
                    for key, value in outbox_diagnostic.items()
                    if key.startswith("dispatch_outbox_")
                }
            )
            conn.execute(
                "UPDATE video_jobs SET result_json=?,updated_at=? WHERE id=?",
                (_json_dumps(latest_result), current, int(job["id"])),
            )
            conn.commit()
        report["details"].append(
            {
                "job_id": int(job["id"]),
                "zero_task_recovery_action": recovery_action,
                "zero_task_terminal_reason": terminal_reason,
                "candidate_count": len(candidates),
                "reconciliation_source": source,
                "reconciliation_run_id": run_id,
                "dispatch_outbox": outbox_diagnostic,
            }
        )
    return report


def mark_product_video_watchdog_scheduler(
    *,
    registered: bool | None = None,
    running: bool | None = None,
    interval_seconds: int | None = None,
    configured_interval_seconds: Any = None,
    generation_id: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    current_dt = now or datetime.now()
    interval_config = product_video_watchdog_interval_config(
        configured_interval_seconds
        if configured_interval_seconds is not None
        else interval_seconds
    )
    if registered is not None:
        _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE["scheduler_registered"] = bool(registered)
    start_accepted = True
    current_generation = str(_PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE.get("watchdog_generation_id") or "")
    requested_generation = str(generation_id or current_generation or uuid.uuid4().hex)
    if running is True and _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE.get("scheduler_running"):
        start_accepted = False
        _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE["duplicate_scheduler_prevented"] = True
    elif running is not None:
        if running is False and generation_id and current_generation and generation_id != current_generation:
            start_accepted = False
        else:
            _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE["scheduler_running"] = bool(running)
            if running:
                _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE["watchdog_started_at"] = now_text(current_dt)
                _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE["watchdog_generation_id"] = requested_generation
                _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE["duplicate_scheduler_prevented"] = False
                _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE["watchdog_generation_jobs_scanned"] = 0
                _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE["watchdog_generation_jobs_reconciled"] = 0
                _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE["watchdog_last_reconciled_job_ids"] = []
    _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE.update(
        {
            "watchdog_enabled": True,
            "interval_seconds": interval_config["effective_interval_seconds"],
            "watchdog_configured_interval_seconds": interval_config["configured_interval_seconds"],
            "watchdog_effective_interval_seconds": interval_config["effective_interval_seconds"],
            "watchdog_interval_clamp_applied": interval_config["clamp_applied"],
            "watchdog_interval_clamp_reason": interval_config["clamp_reason"],
        }
    )
    interval = int(
        _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE.get("interval_seconds")
        or PRODUCT_VIDEO_WATCHDOG_INTERVAL_SECONDS_DEFAULT
    )
    if _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE.get("scheduler_running"):
        _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE["next_run_at"] = now_text(
            current_dt + timedelta(seconds=interval)
        )
    elif running is False:
        _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE["next_run_at"] = ""
    return {**product_video_watchdog_scheduler_status(), "scheduler_start_accepted": start_accepted}


def product_video_watchdog_scheduler_status() -> dict[str, Any]:
    status = dict(_PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE)
    status.update(
        {
            "watchdog_scheduler_registered": bool(status.get("scheduler_registered")),
            "watchdog_scheduler_running": bool(status.get("scheduler_running")),
            "watchdog_last_run_at": str(status.get("last_run_at") or ""),
            "watchdog_last_success_at": str(status.get("last_success_at") or ""),
            "watchdog_last_error": str(status.get("last_error") or ""),
            "watchdog_jobs_scanned": _as_int(status.get("jobs_scanned"), 0),
            "watchdog_jobs_reconciled": _as_int(status.get("jobs_reconciled"), 0),
            "watchdog_next_run_at": str(status.get("next_run_at") or ""),
            "watchdog_interval_seconds": _as_int(status.get("interval_seconds"), PRODUCT_VIDEO_WATCHDOG_INTERVAL_SECONDS_DEFAULT),
        }
    )
    return status


def product_video_watchdog_interval_config(configured: Any = None) -> dict[str, Any]:
    raw = configured
    if raw in (None, ""):
        parsed = PRODUCT_VIDEO_WATCHDOG_INTERVAL_SECONDS_DEFAULT
        configured_text = str(PRODUCT_VIDEO_WATCHDOG_INTERVAL_SECONDS_DEFAULT)
    else:
        configured_text = str(raw)
        try:
            parsed = int(str(raw).strip())
        except Exception:
            parsed = PRODUCT_VIDEO_WATCHDOG_INTERVAL_SECONDS_DEFAULT
    effective = max(
        PRODUCT_VIDEO_WATCHDOG_INTERVAL_SECONDS_MIN,
        min(PRODUCT_VIDEO_WATCHDOG_INTERVAL_SECONDS_MAX, parsed),
    )
    clamp_applied = effective != parsed
    if parsed < PRODUCT_VIDEO_WATCHDOG_INTERVAL_SECONDS_MIN:
        clamp_reason = "below_minimum_15_seconds"
    elif parsed > PRODUCT_VIDEO_WATCHDOG_INTERVAL_SECONDS_MAX:
        clamp_reason = "above_maximum_30_seconds"
    elif raw not in (None, "") and str(raw).strip() and not str(raw).strip().lstrip("+-").isdigit():
        clamp_reason = "invalid_interval_default_20_seconds"
    else:
        clamp_reason = ""
    return {
        "configured_interval": configured_text,
        "configured_interval_seconds": parsed,
        "effective_interval_seconds": effective,
        "clamp_applied": clamp_applied or bool(clamp_reason),
        "clamp_reason": clamp_reason,
    }


async def run_product_video_watchdog_scheduler_loop(
    tick: Callable[[], Any],
    *,
    sleep: Callable[[float], Any] = asyncio.sleep,
    configured_interval_seconds: Any = None,
    generation_id: str = "",
    max_ticks: int = 0,
    now_provider: Callable[[], datetime] = datetime.now,
) -> dict[str, Any]:
    """Production scheduler loop with injectable clock/sleep for deterministic tests."""
    generation = str(generation_id or uuid.uuid4().hex)
    started = mark_product_video_watchdog_scheduler(
        registered=True,
        running=True,
        configured_interval_seconds=configured_interval_seconds,
        generation_id=generation,
        now=now_provider(),
    )
    if not started.get("scheduler_start_accepted"):
        return {**started, "duplicate_scheduler_prevented": True, "ticks_executed": 0}
    effective_interval = _as_int(
        started.get("watchdog_effective_interval_seconds"),
        PRODUCT_VIDEO_WATCHDOG_INTERVAL_SECONDS_DEFAULT,
    )
    ticks_executed = 0
    running_snapshot: dict[str, Any] = {}
    try:
        while True:
            tick_now = now_provider()
            tick_result: dict[str, Any] = {}
            tick_error = ""
            try:
                value = tick()
                if inspect.isawaitable(value):
                    value = await value
                tick_result = dict(value or {}) if isinstance(value, dict) else {}
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                tick_error = f"{type(exc).__name__}:{str(exc)[:160]}"
            ticks_executed += 1
            _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE["watchdog_tick_count"] = _as_int(
                _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE.get("watchdog_tick_count"), 0
            ) + 1
            _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE["last_run_at"] = now_text(tick_now)
            _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE["next_run_at"] = now_text(
                tick_now + timedelta(seconds=effective_interval)
            )
            if tick_error:
                _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE["last_error"] = tick_error
                _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE["watchdog_tick_error_count"] = _as_int(
                    _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE.get("watchdog_tick_error_count"), 0
                ) + 1
            else:
                _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE.update(
                    {
                        "last_success_at": str(tick_result.get("last_success_at") or now_text(tick_now)),
                        "last_error": "",
                        "jobs_scanned": _as_int(tick_result.get("scanned") or tick_result.get("jobs_scanned"), 0),
                        "jobs_reconciled": _as_int(
                            tick_result.get("jobs_reconciled")
                            or _as_int(tick_result.get("recovered"), 0) + _as_int(tick_result.get("terminal_failed"), 0),
                            0,
                        ),
                    }
                )
            running_snapshot = product_video_watchdog_scheduler_status()
            if max_ticks > 0 and ticks_executed >= max_ticks:
                return {
                    **running_snapshot,
                    "scheduler_running_at_return": True,
                    "ticks_executed": ticks_executed,
                }
            wait_result = sleep(float(effective_interval))
            if inspect.isawaitable(wait_result):
                await wait_result
    finally:
        mark_product_video_watchdog_scheduler(
            registered=True,
            running=False,
            configured_interval_seconds=effective_interval,
            generation_id=generation,
            now=now_provider(),
        )


def run_product_video_watchdog_scheduler_tick(
    conn: sqlite3.Connection,
    *,
    eligibility_evaluator: Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], dict[str, Any]] | None,
    now: datetime | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Run the exact durable watchdog tick used by the bot scheduler."""
    current_dt = now or datetime.now()
    interval = int(
        _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE.get("interval_seconds")
        or PRODUCT_VIDEO_WATCHDOG_INTERVAL_SECONDS_DEFAULT
    )
    _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE.update(
        {
            "scheduler_registered": True,
            "scheduler_running": True,
            "last_run_at": now_text(current_dt),
            "last_error": "",
            "next_run_at": now_text(current_dt + timedelta(seconds=interval)),
        }
    )
    try:
        run_id = f"watchdog-{_PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE.get('watchdog_generation_id') or 'generation'}-{uuid.uuid4().hex}"
        report = sweep_product_video_zero_task_watchdog(
            conn,
            now=current_dt,
            eligibility_evaluator=eligibility_evaluator,
            limit=limit,
            reconciliation_source="watchdog_scheduler",
            reconciliation_run_id=run_id,
        )
    except Exception as exc:
        _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE.update(
            {
                "last_error": f"{type(exc).__name__}:{str(exc)[:160]}",
                "jobs_scanned": 0,
                "jobs_reconciled": 0,
            }
        )
        raise
    jobs_reconciled = int(report.get("recovered") or 0) + int(report.get("terminal_failed") or 0)
    reconciled_ids = [
        _as_int(item.get("job_id"), 0)
        for item in (report.get("details") or [])
        if isinstance(item, dict)
        and str(item.get("zero_task_recovery_action") or "") not in {"", "wait_dispatch_grace", "active_dispatch_lease"}
        and _as_int(item.get("job_id"), 0) > 0
    ]
    _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE.update(
        {
            "last_success_at": now_text(current_dt),
            "jobs_scanned": int(report.get("scanned") or 0),
            "jobs_reconciled": jobs_reconciled,
            "watchdog_generation_jobs_scanned": _as_int(
                _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE.get("watchdog_generation_jobs_scanned"), 0
            ) + int(report.get("scanned") or 0),
            "watchdog_generation_jobs_reconciled": _as_int(
                _PRODUCT_VIDEO_WATCHDOG_SCHEDULER_STATE.get("watchdog_generation_jobs_reconciled"), 0
            ) + jobs_reconciled,
            "watchdog_last_reconciled_job_ids": reconciled_ids,
            "last_reconciliation_source": "watchdog_scheduler",
            "last_error": "",
        }
    )
    return {
        **report,
        **product_video_watchdog_scheduler_status(),
    }


def kickoff_product_video_job_after_confirm(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    provider_chain: list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    job = get_video_render_job(conn, int(job_id))
    if not job:
        return {"ok": False, "reason": "job_not_found"}
    project = get_video_project(conn, int(job.get("project_id") or 0))
    if not project or not _is_product_video_project(project):
        return {"ok": True, "skipped": True, "reason": "not_product_video", "job": job, "project": project}
    existing = _json_loads(str(job.get("result_json") or ""), {})
    if not isinstance(existing, dict):
        existing = {}
    payload = dict(existing)
    kickoff = build_product_video_confirm_kickoff_payload(job, project, provider_chain=provider_chain, now=now)
    payload.update(kickoff)
    current = now_text(now)
    if not kickoff.get("provider_chain_resolved"):
        blocker = str(kickoff.get("worker_dispatch_blocker") or kickoff.get("dispatch_status") or "provider_chain_missing_no_charge")
        payload.update(
            {
                "ok": False,
                "blocker": blocker,
                "provider_error": blocker,
                "terminal_state": blocker,
                "no_charge": True,
            }
        )
        conn.execute(
            """UPDATE video_jobs
               SET status='failed', last_error=?, result_json=?, progress_percent=?, progress_message=?, updated_at=?, completed_at=COALESCE(completed_at, ?)
               WHERE id=?""",
            (
                blocker,
                _json_dumps(payload),
                0,
                blocker,
                current,
                current,
                int(job_id),
            ),
        )
        conn.execute(
            """UPDATE video_projects
               SET status='failed', video_terminal_state=?,
                   error_log=?, updated_at=?
               WHERE project_id=?""",
            (blocker, blocker, current, int(project["project_id"])),
        )
    else:
        conn.execute(
            """UPDATE video_jobs
               SET result_json=?, progress_percent=?, progress_message=?, updated_at=?
               WHERE id=? AND status IN ('queued','processing')""",
            (_json_dumps(payload), 10, "queued_for_worker_dispatch", current, int(job_id)),
        )
        conn.execute(
            """UPDATE video_projects
               SET status='processing', video_terminal_state='final_rendering', updated_at=?
               WHERE project_id=?""",
            (current, int(project["project_id"])),
        )
    conn.commit()
    return {
        "ok": bool(kickoff.get("provider_chain_resolved")),
        "reason": "" if kickoff.get("provider_chain_resolved") else "provider_chain_missing_no_charge",
        "job": get_video_render_job(conn, int(job_id)),
        "project": get_video_project(conn, int(project["project_id"])),
        "payload": payload,
    }


def product_video_expected_duration_seconds(project: dict | None = None, payload: dict | None = None) -> int:
    project = dict(project or {})
    payload = dict(payload or {})
    invoice = _json_loads(str(project.get("invoice_json") or payload.get("invoice_json") or ""), {})
    if not isinstance(invoice, dict):
        invoice = {}
    asset_pack = _json_loads(str(project.get("asset_pack_json") or payload.get("asset_pack_json") or ""), {})
    if not isinstance(asset_pack, dict):
        asset_pack = {}
    scene_duration_limit = (
        PRODUCT_VIDEO_MAX_UIFLOW3_SCENE_SECONDS
        if str(
            payload.get("uiflow3_handoff_sha256")
            or asset_pack.get("uiflow3_handoff_sha256")
            or invoice.get("uiflow3_handoff_sha256")
            or ""
        ).strip()
        else PRODUCT_VIDEO_SCENE_SECONDS
    )
    scene_count = _as_int(project.get("scene_count") or payload.get("scene_count") or invoice.get("scene_count"), 1)
    orchestration_mode = str(
        payload.get("orchestration_mode")
        or payload.get("provider_orchestration_mode")
        or invoice.get("orchestration_mode")
        or ""
    ).strip().lower()
    if orchestration_mode in {"per_scene_8s", "scene_orchestrator", "per_scene"}:
        scene_seconds = _as_int(
            payload.get("scene_duration_seconds")
            or payload.get("scene_seconds")
            or invoice.get("scene_duration_seconds")
            or invoice.get("scene_seconds"),
            PRODUCT_VIDEO_SCENE_SECONDS,
        )
        return max(1, min(20, scene_count)) * max(1, min(scene_duration_limit, scene_seconds))
    direct = _as_int(
        payload.get("expected_duration_seconds")
        or payload.get("duration_seconds")
        or invoice.get("duration_seconds"),
        0,
    )
    if direct > 0:
        return direct
    scene_seconds = _as_int(payload.get("scene_seconds") or invoice.get("scene_seconds"), PRODUCT_VIDEO_SCENE_SECONDS)
    return max(1, min(20, scene_count)) * max(1, scene_seconds)


def product_video_duration_contract(project: dict | None, payload: dict | None, validation: dict | None) -> dict[str, Any]:
    validation = dict(validation or {})
    expected = product_video_expected_duration_seconds(project, payload)
    duration = float(validation.get("duration") or validation.get("duration_seconds") or 0)
    if not validation.get("ok"):
        return {
            "ok": False,
            "expected_duration_seconds": expected,
            "actual_duration_seconds": duration,
            "duration_tolerance_seconds": PRODUCT_VIDEO_DURATION_TOLERANCE_SECONDS,
            "reason": str(validation.get("reason") or "final_output_invalid"),
        }
    ok = duration + PRODUCT_VIDEO_DURATION_TOLERANCE_SECONDS >= float(expected)
    return {
        "ok": bool(ok),
        "expected_duration_seconds": expected,
        "actual_duration_seconds": duration,
        "duration_tolerance_seconds": PRODUCT_VIDEO_DURATION_TOLERANCE_SECONDS,
        "reason": "" if ok else "final_duration_short_scene_coverage_missing",
    }


def _product_video_index_map(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return {}


def _product_video_scene_task_index(item: dict[str, Any]) -> int:
    return _as_int(item.get("scene_index") or item.get("scene_id") or item.get("clip_index") or item.get("index"), 0)


def _product_video_scene_task_is_valid_clip(item: dict[str, Any]) -> bool:
    status = str(item.get("status") or item.get("clip_status") or item.get("provider_status") or "").strip().lower()
    return bool(
        item.get("clip_valid")
        or item.get("validation_passed")
        or item.get("output_validated")
        or _as_int(item.get("clip_bytes") or item.get("artifact_size") or item.get("output_bytes"), 0) > 0
        or status in {"clip_downloaded", "downloaded", "validated", "clip_validated", "scene_clip_validated"}
    )


def product_video_durable_task_scene_owners(result: dict | None = None) -> dict[str, Any]:
    """Resolve persisted provider-task ownership without guessing from a canonical scene."""
    payload = dict(result or {})
    scene_count = max(
        1,
        min(
            20,
            _as_int(
                payload.get("scene_count")
                or payload.get("scenes_total")
                or payload.get("scene_tasks_total"),
                1,
            ),
        ),
    )
    required = list(range(1, scene_count + 1))
    allowed = set(required)
    task_to_scene_index: dict[str, int] = {}
    conflicts: dict[str, list[int]] = {}
    sources_by_task: dict[str, list[str]] = {}

    def register(task_id: Any, scene_index: Any, source: str) -> None:
        task_key = str(task_id or "").strip()
        index = _as_int(scene_index, 0)
        if not task_key or task_key == "-" or index not in allowed:
            return
        source_list = sources_by_task.setdefault(task_key, [])
        if source not in source_list:
            source_list.append(source)
        existing = task_to_scene_index.get(task_key)
        if existing is None and task_key not in conflicts:
            task_to_scene_index[task_key] = index
            return
        if existing == index:
            return
        indexes = set(conflicts.get(task_key) or [])
        if existing:
            indexes.add(existing)
        indexes.add(index)
        conflicts[task_key] = sorted(indexes)
        task_to_scene_index.pop(task_key, None)

    for field_name in ("task_scene_index_map", "task_to_scene_index"):
        mapping = _product_video_index_map(payload.get(field_name))
        for task_id, scene_index in mapping.items():
            register(task_id, scene_index, field_name)

    for field_name in (
        "scene_task_map",
        "scene_active_task_by_index",
        "scene_winner_task_by_index",
    ):
        mapping = _product_video_index_map(payload.get(field_name))
        for scene_index, raw in mapping.items():
            values: list[Any]
            if isinstance(raw, dict):
                values = [
                    raw.get(key)
                    for key in (
                        "provider_task_id",
                        "task_id",
                        "active_task_id",
                        "winning_task_id",
                        "scene_winner_task",
                        "canonical_task_selected",
                    )
                ]
            elif isinstance(raw, (list, tuple, set)):
                values = list(raw)
            else:
                values = [raw]
            for task_id in values:
                register(task_id, scene_index, field_name)

    for field_name in (
        "scene_ledger",
        "scene_tasks",
        "provider_scene_tasks",
        "product_video_scene_tasks",
    ):
        raw_rows = payload.get(field_name) or []
        if isinstance(raw_rows, str):
            raw_rows = _json_loads(raw_rows, [])
        if isinstance(raw_rows, dict):
            rows = []
            for scene_index, raw in raw_rows.items():
                item = dict(raw or {}) if isinstance(raw, dict) else {}
                item.setdefault("scene_index", scene_index)
                rows.append(item)
        elif isinstance(raw_rows, (list, tuple)):
            rows = [dict(item or {}) for item in raw_rows if isinstance(item, dict)]
        else:
            rows = []
        for row in rows:
            scene_index = _product_video_scene_task_index(row)
            task_ids = [
                row.get(key)
                for key in (
                    "provider_task_id",
                    "task_id",
                    "provider_video_id",
                    "video_id",
                    "active_task_id",
                    "winning_task_id",
                    "scene_winner_task",
                    "canonical_task_selected",
                )
            ]
            for key in ("fallback_task_ids", "provider_task_ids", "provider_video_ids"):
                values = row.get(key)
                if isinstance(values, (list, tuple, set)):
                    task_ids.extend(values)
            for task_id in task_ids:
                register(task_id, scene_index, field_name)

    mapped_scene_indexes = sorted(set(task_to_scene_index.values()))
    coverage_complete = mapped_scene_indexes == required
    return {
        "task_to_scene_index": dict(task_to_scene_index),
        "task_scene_index_map": dict(task_to_scene_index),
        "task_scene_mapping_conflicts": dict(conflicts),
        "task_scene_mapping_sources": dict(sources_by_task),
        "task_scene_mapping_verified": bool(task_to_scene_index and not conflicts),
        "required_scene_indexes": required,
        "mapped_scene_indexes": mapped_scene_indexes,
        "scene_task_coverage_complete": coverage_complete,
    }


def product_video_recovery_cancellation_state(
    project: dict | None = None,
    outbox: dict | None = None,
) -> dict[str, Any]:
    project = dict(project or {})
    outbox = dict(outbox or {})
    project_status = str(project.get("status") or "").strip().lower()
    outbox_status = str(outbox.get("dispatch_status") or "").strip().lower()
    project_cancelled = project_status in {"cancelled", "canceled"}
    outbox_cancelled = outbox_status in {"cancelled", "canceled"}
    blocker = (
        "project_cancelled"
        if project_cancelled
        else "dispatch_outbox_cancelled"
        if outbox_cancelled
        else ""
    )
    return {
        "cancelled": bool(blocker),
        "blocker": blocker,
        "project_status": project_status,
        "outbox_status": outbox_status,
        "project_cancelled": project_cancelled,
        "outbox_cancelled": outbox_cancelled,
    }


def product_video_existing_task_recovery_state(
    job: dict | None = None,
    project: dict | None = None,
    result: dict | None = None,
    outbox: dict | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Decide whether a failed job may resume by polling already-created tasks only."""
    job = dict(job or {})
    project = dict(project or {})
    result = dict(result or {})
    outbox = dict(outbox or {})
    invoice = _json_loads(project.get("invoice_json"), {})
    if not isinstance(invoice, dict):
        invoice = {}
    durable_scene_count = _as_int(
        project.get("scene_count")
        or invoice.get("scene_count")
        or result.get("scene_count")
        or result.get("scenes_total")
        or result.get("scene_tasks_total"),
        0,
    )
    ownership_payload = dict(result)
    if durable_scene_count > 0:
        ownership_payload["scene_count"] = durable_scene_count
    ownership = product_video_durable_task_scene_owners(ownership_payload)
    required = list(ownership.get("required_scene_indexes") or [])
    mapped = list(ownership.get("mapped_scene_indexes") or [])
    outbox_present = _as_int(outbox.get("outbox_id"), 0) > 0
    cancellation = product_video_recovery_cancellation_state(project, outbox)
    outbox_status = str(cancellation.get("outbox_status") or "")
    job_status = str(job.get("status") or "").strip().lower()
    project_status = str(cancellation.get("project_status") or "")
    project_cancelled = bool(cancellation.get("project_cancelled"))
    outbox_cancelled = bool(cancellation.get("outbox_cancelled"))
    product_video = bool(
        result.get("product_video")
        or str(result.get("source") or "").strip().lower() == "product_video"
    )
    confirmed = bool(
        _as_int(project.get("is_confirmed"), 0) == 1
        and result.get("public_user_confirmed")
        and result.get("invoice_confirmed")
    )
    charged_xu = max(
        0,
        _as_int(
            result.get("charged_xu")
            or result.get("charge")
            or result.get("wallet_charge")
            or result.get("charged_amount_xu"),
            0,
        ),
    )
    charge_recorded = bool(
        charged_xu > 0
        or result.get("wallet_charge_recorded")
        or result.get("charge_committed")
    )
    delivered = bool(
        project.get("video_delivered_at")
        or project.get("video_delivery_message_id")
        or project.get("final_video_file_id")
        or result.get("video_delivered_at")
        or result.get("delivery_done")
        or result.get("final_delivered")
    )
    terminal_outbox = outbox_status in {
        "acknowledged",
        "completed",
        "terminal_failed",
    }
    mapping_verified = bool(
        ownership.get("task_scene_mapping_verified")
        and ownership.get("scene_task_coverage_complete")
        and required
        and mapped == required
    )
    already_recovered = bool(result.get("recovery_existing_tasks_only"))
    recovery_count = max(
        _as_int(result.get("existing_task_recovery_count"), 0),
        1 if already_recovered else 0,
    )
    recovery_max_attempts = PRODUCT_VIDEO_EXISTING_TASK_RECOVERY_MAX_ATTEMPTS
    recovery_attempts_remaining = max(0, recovery_max_attempts - recovery_count)
    recovery_attempts_exhausted = recovery_count >= recovery_max_attempts
    recovered_at_epoch = _parse_time_epoch(
        result.get("existing_task_recovery_recovered_at")
    )
    current_dt = now or datetime.now()
    current_epoch = current_dt.timestamp()
    retry_after_epoch = (
        recovered_at_epoch + PRODUCT_VIDEO_EXISTING_TASK_RECOVERY_COOLDOWN_SECONDS
        if recovered_at_epoch > 0
        else 0.0
    )
    recovery_cooldown_active = bool(
        already_recovered
        and retry_after_epoch > 0
        and current_epoch < retry_after_epoch
    )
    recoverable = bool(
        job_status == "failed"
        and product_video
        and confirmed
        and not project_cancelled
        and not outbox_cancelled
        and outbox_present
        and terminal_outbox
        and mapping_verified
        and not charge_recorded
        and not delivered
        and not recovery_attempts_exhausted
        and not recovery_cooldown_active
    )
    if recoverable:
        blocker = ""
    elif job_status != "failed":
        blocker = "job_not_failed"
    elif not product_video:
        blocker = "not_product_video"
    elif not confirmed:
        blocker = "public_confirmation_missing"
    elif project_cancelled:
        blocker = "project_cancelled"
    elif outbox_cancelled:
        blocker = "dispatch_outbox_cancelled"
    elif not outbox_present:
        blocker = "dispatch_outbox_missing"
    elif not terminal_outbox:
        blocker = "dispatch_outbox_not_terminal"
    elif not mapping_verified:
        blocker = "existing_task_scene_coverage_incomplete"
    elif charge_recorded:
        blocker = "wallet_charge_already_recorded"
    elif delivered:
        blocker = "video_already_delivered"
    elif recovery_attempts_exhausted:
        blocker = "existing_task_recovery_attempts_exhausted"
    elif recovery_cooldown_active:
        blocker = "existing_task_recovery_cooldown_active"
    else:
        blocker = "existing_task_recovery_not_eligible"
    return {
        **ownership,
        "existing_task_recovery_recoverable": recoverable,
        "existing_task_recovery_block_reason": blocker,
        "existing_task_recovery_already_used": already_recovered,
        "existing_task_recovery_count": recovery_count,
        "existing_task_recovery_max_attempts": recovery_max_attempts,
        "existing_task_recovery_attempts_remaining": recovery_attempts_remaining,
        "existing_task_recovery_attempts_exhausted": recovery_attempts_exhausted,
        "existing_task_recovery_cooldown_seconds": PRODUCT_VIDEO_EXISTING_TASK_RECOVERY_COOLDOWN_SECONDS,
        "existing_task_recovery_cooldown_active": recovery_cooldown_active,
        "existing_task_recovery_retry_after": _format_epoch(retry_after_epoch),
        "existing_task_recovery_job_status": job_status,
        "existing_task_recovery_project_status": project_status,
        "existing_task_recovery_outbox_status": outbox_status,
        "existing_task_recovery_outbox_present": outbox_present,
        "existing_task_recovery_product_video": product_video,
        "existing_task_recovery_public_confirmed": confirmed,
        "existing_task_recovery_outbox_terminal": terminal_outbox,
        "existing_task_recovery_project_cancelled": project_cancelled,
        "existing_task_recovery_outbox_cancelled": outbox_cancelled,
        "existing_task_recovery_delivered": delivered,
        "provider_submit_allowed": False,
        "automatic_retry_allowed": False,
        "automatic_resubmit_allowed": False,
        "automatic_fallback_allowed": False,
        "charged_xu": charged_xu,
        "wallet_charge_recorded": charge_recorded,
    }


def recover_product_video_existing_tasks(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    """CAS-requeue a failed Product Video job for read-only polling of its old tasks."""
    ensure_video_project_queue_schema(conn)
    recovery_moment = now or datetime.now()

    def snapshot() -> tuple[dict, dict, dict, dict, dict]:
        current_job = get_video_render_job(conn, int(job_id))
        current_project = (
            get_video_project(conn, _as_int(current_job.get("project_id"), 0))
            if current_job
            else {}
        )
        current_result = (
            _json_loads(str(current_job.get("result_json") or ""), {})
            if current_job
            else {}
        )
        if not isinstance(current_result, dict):
            current_result = {}
        current_outbox = get_product_video_dispatch_outbox(
            conn,
            job_id=int(job_id),
        )
        current_state = product_video_existing_task_recovery_state(
            current_job,
            current_project,
            current_result,
            current_outbox,
            now=recovery_moment,
        )
        return (
            current_job,
            current_project,
            current_result,
            current_outbox,
            current_state,
        )

    job, project, result, outbox, state = snapshot()
    if not state.get("existing_task_recovery_recoverable"):
        return {**state, "existing_task_recovery_recovered": False}

    try:
        conn.execute("BEGIN IMMEDIATE")
        job, project, result, outbox, state = snapshot()
        if not state.get("existing_task_recovery_recoverable"):
            conn.rollback()
            return {**state, "existing_task_recovery_recovered": False}

        current = now_text(recovery_moment)
        invoice = _json_loads(str(project.get("invoice_json") or ""), {})
        if not isinstance(invoice, dict):
            invoice = {}
        durable_scene_count = max(
            [
                _as_int(project.get("scene_count"), 0),
                _as_int(invoice.get("scene_count"), 0),
                _as_int(result.get("scene_count"), 0),
                *[
                    _as_int(index, 0)
                    for index in (state.get("required_scene_indexes") or [])
                ],
            ]
        )
        original_submit_source = str(
            result.get("original_submit_source")
            or result.get("submit_source")
            or result.get("provider_submit_source")
            or "public_user_final_confirm"
        ).strip()
        prior_recovery_count = max(
            _as_int(result.get("existing_task_recovery_count"), 0),
            1 if result.get("recovery_existing_tasks_only") else 0,
        )
        result.update(
            {
                "status": "queued",
                "canonical_status": "queued_existing_task_recovery",
                "terminal": False,
                "terminal_state": "",
                "final_decision": "continue_polling",
                "continue_polling": True,
                "scene_count": durable_scene_count,
                "recovery_existing_tasks_only": True,
                "existing_task_recovery_recovered": True,
                "existing_task_recovery_recovered_at": current,
                "existing_task_recovery_count": prior_recovery_count + 1,
                "existing_task_recovery_max_attempts": PRODUCT_VIDEO_EXISTING_TASK_RECOVERY_MAX_ATTEMPTS,
                "existing_task_recovery_cooldown_seconds": PRODUCT_VIDEO_EXISTING_TASK_RECOVERY_COOLDOWN_SECONDS,
                "existing_task_recovery_retry_after": now_text(
                    recovery_moment
                    + timedelta(
                        seconds=PRODUCT_VIDEO_EXISTING_TASK_RECOVERY_COOLDOWN_SECONDS
                    )
                ),
                "existing_task_recovery_outbox_status": str(
                    outbox.get("dispatch_status") or ""
                ),
                "submit_source": "worker_poll_existing_task",
                "provider_submit_source": "worker_poll_existing_task",
                "original_submit_source": original_submit_source,
                "provider_submit_allowed": False,
                "provider_submit_block_reason": "existing_task_recovery_read_only",
                "automatic_retry_allowed": False,
                "automatic_resubmit_allowed": False,
                "automatic_fallback_allowed": False,
                "no_charge": True,
                "charge": 0,
                "charged_xu": 0,
                "wallet_charge_recorded": False,
            }
        )
        progress = max(20, min(60, _as_int(job.get("progress_percent"), 20)))
        cursor = conn.execute(
            """UPDATE video_jobs
                  SET status='queued',result_json=?,last_error='',progress_percent=?,
                      progress_message='queued_existing_task_recovery',locked_by='',locked_at=NULL,
                      lease_expires_at=NULL,completed_at=NULL,updated_at=?
                WHERE id=? AND status='failed'""",
            (_json_dumps(result), progress, current, int(job_id)),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return {
                **state,
                "existing_task_recovery_recovered": False,
                "existing_task_recovery_block_reason": "recovery_claim_lost",
            }
        project_cursor = conn.execute(
            """UPDATE video_projects
                  SET status='queued_for_worker',scene_count=?,video_terminal_state='',
                      video_terminal_locked_at=NULL,error_log='',completed_at=NULL,updated_at=?
                WHERE project_id=? AND status=?
                  AND LOWER(status) NOT IN ('cancelled','canceled')""",
            (
                durable_scene_count,
                current,
                _as_int(project.get("project_id"), 0),
                str(project.get("status") or ""),
            ),
        )
        if project_cursor.rowcount != 1:
            conn.rollback()
            return {
                **state,
                "existing_task_recovery_recovered": False,
                "existing_task_recovery_block_reason": "recovery_project_cas_lost",
            }
        conn.commit()
        return {
            **state,
            "existing_task_recovery_recovered": True,
            "job_status_after_recovery": "queued",
            "project_status_after_recovery": "queued_for_worker",
            "outbox_status_after_recovery": str(outbox.get("dispatch_status") or ""),
        }
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


def product_video_scene_ledger_state(
    project: dict | None = None,
    job: dict | None = None,
    result: dict | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the durable per-scene truth used by worker, status and delivery gates.

    Every task is accepted only with an explicit scene index. A successful task
    may complete its own scene, but it cannot complete a multi-scene job.
    """
    project = dict(project or {})
    job = dict(job or {})
    result = dict(result or {})
    invoice = _json_loads(project.get("invoice_json") or result.get("invoice_json") or result.get("invoice"), {})
    if not isinstance(invoice, dict):
        invoice = {}
    scene_count = max(
        1,
        min(
            20,
            _as_int(
                project.get("scene_count")
                or job.get("scene_count")
                or result.get("scene_count")
                or result.get("scenes_total")
                or result.get("scene_tasks_total")
                or invoice.get("scene_count"),
                1,
            ),
        ),
    )
    expected = list(range(1, scene_count + 1))
    now_dt = now or datetime.now()
    zero_task_watchdog = product_video_zero_task_watchdog_state(job, result, now=now_dt)
    explicit_scene_plan = any(
        bool(container.get(key))
        for container in (project, job, result)
        for key in ("scene_ledger", "scene_tasks", "provider_scene_tasks", "product_video_scene_tasks")
        if isinstance(container, dict)
    )

    records: dict[int, dict[str, Any]] = {
        index: {
            "scene_index": index,
            "required": True,
            "provider_key": "",
            "primary_task_id": "",
            "fallback_task_ids": [],
            "active_task_id": "",
            "winning_task_id": "",
            "status": "pending_submit",
            "dispatch_state": "submit_in_progress",
            "dispatch_attempted": False,
            "dispatch_block_reason": "",
            "dispatch_idempotency_key": "",
            "dispatch_recovered": False,
            "dispatchable": bool(explicit_scene_plan),
            "exhausted": False,
            "submitted_at": "",
            "submitted_at_epoch": 0,
            "started_at": "",
            "started_at_epoch": 0,
            "progress": 0,
            "progress_last_changed_at": "",
            "result_url": "",
            "result_url_present": False,
            "result_task_id": "",
            "result_url_source": "",
            "task_scene_mapping_verified": False,
            "phantom_result_prevented": False,
            "authoritative_status_source": "estimated_internal_state",
            "historical_status_ignored": False,
            "success_result_overrode_stale_not_start": False,
            "provider_status_conflict": False,
            "provider_status_conflict_resolution": "",
            "result_processing_action": "",
            "clip_path": "",
            "clip_bytes": 0,
            "clip_valid": False,
            "scene_validation_verified": False,
            "completed_at": "",
            "failure_reason": "",
            "fallback_count": 0,
            "fallback_allowed": False,
            "fallback_provider_order": [],
            "provider_elapsed_seconds": 0,
            "scene_not_start_elapsed": 0,
            "next_poll_at": "",
            "task_candidates": [],
            "task_id_present": False,
            "task_pollable": False,
            "effective_submit_outcome": "",
            "transport_http": 0,
            "transport_anomaly": False,
            "duplicate_submit_prevented": False,
        }
        for index in expected
    }
    unknown_scene_task_ignored = False
    phantom_result_prevented = False
    sources_used: list[str] = []
    task_to_scene_index: dict[str, int] = {}
    task_scene_mapping_conflicts: dict[str, list[int]] = {}

    def _items(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, str):
            value = _json_loads(value, [])
        if isinstance(value, dict):
            rows: list[dict[str, Any]] = []
            for key, raw in value.items():
                item = dict(raw or {}) if isinstance(raw, dict) else {"status": raw}
                item.setdefault("scene_index", key)
                rows.append(item)
            return rows
        if isinstance(value, (list, tuple)):
            return [dict(item or {}) for item in value if isinstance(item, dict)]
        return []

    def _text_value(item: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = item.get(key)
            if value not in (None, "", [], {}):
                return str(value).strip()
        return ""

    def _status_class(value: Any) -> str:
        raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        if raw in {"clip_downloaded", "downloaded", "validated", "clip_validated", "scene_clip_validated", "success", "succeeded", "completed", "done"}:
            return "succeeded"
        if raw in {"failed", "failure", "error", "failed_no_charge", "cancelled", "canceled", "provider_failed", "terminal_failed"}:
            return "failed"
        if "not_start" in raw or raw in {
            "queued",
            "pending",
            "waiting",
            "result_pending_validation",
            "result_pending_download",
            "download_validation_pending",
            "pending_submit",
            "submit_in_progress",
            "queued_waiting_for_slot",
            "scheduled_after_scene_1_progress",
            "queued_waiting_for_dispatch",
            "dispatch_lease_acquired",
            "submit_in_progress",
        }:
            return "not_start" if "not_start" in raw else "pending"
        if raw in {"submit_blocked_with_reason", "exhausted", "dispatch_exhausted"}:
            return "failed"
        if raw in {"running", "provider_running", "processing", "in_progress", "provider_in_progress", "rendering", "final_rendering"}:
            return "running"
        return raw or "pending"

    def _status_authority_rank(value: Any) -> int:
        raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        if raw in {"scene_clip_validated", "clip_downloaded", "downloaded", "validated", "succeeded"}:
            return 6
        if raw in {"result_pending_validation", "result_pending_download", "download_validation_pending"}:
            return 5
        if raw in {"failed", "failed_no_charge", "error"}:
            return 4
        status_class = _status_class(raw)
        if status_class == "running":
            return 3
        if status_class == "not_start":
            return 2
        return 1

    def _register_task_owner(task_id: str, scene_index: int) -> None:
        task_key = str(task_id or "").strip()
        if not task_key or scene_index not in records:
            return
        existing = task_to_scene_index.get(task_key)
        if existing is None and task_key not in task_scene_mapping_conflicts:
            task_to_scene_index[task_key] = scene_index
            return
        if existing == scene_index:
            return
        indexes = set(task_scene_mapping_conflicts.get(task_key) or [])
        if existing:
            indexes.add(existing)
        indexes.add(scene_index)
        task_scene_mapping_conflicts[task_key] = sorted(indexes)
        task_to_scene_index.pop(task_key, None)

    def _task_owner_verified(task_id: str, scene_index: int) -> bool:
        task_key = str(task_id or "").strip()
        return bool(
            task_key
            and task_key not in task_scene_mapping_conflicts
            and task_to_scene_index.get(task_key) == scene_index
        )

    def _first_status_value(item: dict[str, Any], keys: tuple[str, ...]) -> tuple[str, str]:
        for key in keys:
            value = str(item.get(key) or "").strip()
            if value:
                return value, key
        return "", ""

    def _candidate_ids(item: dict[str, Any]) -> list[str]:
        values: list[str] = []
        for key in (
            "provider_task_id",
            "task_id",
            "provider_video_id",
            "video_id",
            "active_task_id",
            "canonical_task_selected",
            "winning_task_id",
            "scene_winner_task",
        ):
            value = str(item.get(key) or "").strip()
            if value and value not in values:
                values.append(value)
        for key in ("fallback_task_ids", "provider_task_ids", "provider_video_ids"):
            raw = item.get(key)
            if not isinstance(raw, (list, tuple, set)):
                continue
            for value in raw:
                text = str(value or "").strip()
                if text and text not in values:
                    values.append(text)
        return values

    def _merge_item(item: dict[str, Any], source_name: str) -> None:
        nonlocal unknown_scene_task_ignored, phantom_result_prevented
        debug = dict(item.get("debug") or {}) if isinstance(item.get("debug"), dict) else {}
        merged = {**debug, **item}
        index = _product_video_scene_task_index(merged)
        task_ids = _candidate_ids(merged)
        if index not in records:
            if task_ids:
                unknown_scene_task_ignored = True
            return
        if source_name not in sources_used:
            sources_used.append(source_name)
        record = records[index]
        for task_id in task_ids:
            _register_task_owner(task_id, index)
        provider = _text_value(merged, "provider_key", "provider", "selected_provider", "provider_pending_provider")
        current_status_raw, current_status_source = _first_status_value(
            merged,
            (
                "actual_provider_payload_status",
                "provider_status_payload_data_status",
                "shopaikey_data_status",
                "shopaikey_raw_status",
                "poll_raw_status",
            ),
        )
        historical_status_raw, historical_status_source = _first_status_value(
            merged,
            (
                "raw_provider_status_before_source_fix",
                "raw_provider_status",
                "provider_status_raw",
                "normalized_provider_status",
                "provider_status",
                "status",
                "clip_status",
                "blocker",
            ),
        )
        status_raw = current_status_raw or historical_status_raw
        dispatch_state = _text_value(
            merged,
            "dispatch_state",
            "scene_dispatch_state",
            "worker_dispatch_state",
        )
        dispatch_block_reason = _text_value(
            merged,
            "dispatch_block_reason",
            "scene_dispatch_block_reason",
            "provider_submit_block_reason",
        )
        dispatch_idempotency_key = _text_value(
            merged,
            "dispatch_idempotency_key",
            "scene_dispatch_idempotency_key",
            "provider_submit_idempotency_key",
        )
        result_url = _text_value(merged, "result_url", "provider_result_url", "download_url", "file_url", "video_url", "output_url")
        clip_path = _text_value(merged, "clip_path", "output_path", "local_path", "raw_provider_video_path")
        clip_bytes = _as_int(
            merged.get("clip_bytes")
            or merged.get("artifact_size")
            or merged.get("artifact_bytes")
            or merged.get("downloaded_file_size")
            or merged.get("output_bytes"),
            0,
        )
        if clip_path and clip_bytes <= 0:
            try:
                clip_bytes = os.path.getsize(clip_path) if os.path.isfile(clip_path) else 0
            except OSError:
                clip_bytes = 0
        result_present_raw = bool(
            result_url
            or merged.get("result_url_valid")
            or merged.get("download_url_present")
            or merged.get("provider_result_url_present")
        )
        explicit_result_task_id = _text_value(
            merged,
            "result_task_id",
            "winning_task_id",
            "scene_winner_task",
            "active_task_id",
            "provider_task_id",
            "task_id",
            "provider_video_id",
            "video_id",
            "canonical_task_selected",
        )
        if not explicit_result_task_id and len(task_ids) == 1:
            explicit_result_task_id = task_ids[0]
        result_mapping_verified = bool(
            result_present_raw
            and explicit_result_task_id
            and _task_owner_verified(explicit_result_task_id, index)
        )
        result_present = bool(result_present_raw and result_mapping_verified)
        if result_present_raw and not result_mapping_verified:
            phantom_result_prevented = True
            record["phantom_result_prevented"] = True
            result_url = ""
        normalized_status_raw = status_raw.strip().lower().replace("-", "_").replace(" ", "_")
        clip_valid = bool(
            merged.get("clip_valid")
            or merged.get("validation_passed")
            or merged.get("output_validated")
            or merged.get("mp4_validator_result") == "valid_mp4"
            or clip_bytes > 0
            or (normalized_status_raw in {"clip_downloaded", "downloaded", "validated", "scene_clip_validated"} and result_present)
        )
        durable_clip_without_task_identity = bool(
            (
                merged.get("clip_valid")
                and normalized_status_raw
                in {"clip_downloaded", "downloaded", "validated", "clip_validated", "scene_clip_validated"}
            )
            or merged.get("validation_passed")
            or merged.get("output_validated")
            or merged.get("mp4_validator_result") == "valid_mp4"
            or clip_bytes > 0
        )
        if not result_mapping_verified and not task_ids and not durable_clip_without_task_identity:
            clip_valid = False
        submitted_at = _text_value(merged, "submitted_at", "scene_submitted_at", "provider_started_at", "provider_wait_started_at")
        started_at = _text_value(merged, "started_at", "scene_started_at", "provider_started_at", "provider_wait_started_at")
        completed_at = _text_value(merged, "completed_at", "result_received_at", "winner_selected_at")
        progress = _as_int(
            merged.get("progress")
            or merged.get("provider_progress_normalized")
            or merged.get("provider_progress_percent")
            or merged.get("provider_progress_raw"),
            0,
        )
        current_status_class = _status_class(current_status_raw)
        historical_status_class = _status_class(historical_status_raw)
        success_with_result = bool(current_status_class == "succeeded" and result_present)
        provider_status_conflict = bool(success_with_result and historical_status_class == "not_start")
        if clip_valid:
            candidate_status = "succeeded"
            authoritative_status_source = "validated_scene_clip"
        elif success_with_result:
            candidate_status = "result_pending_validation"
            authoritative_status_source = f"current_result_bearing_success:{current_status_source or 'provider_response'}"
        elif current_status_raw:
            candidate_status = current_status_class
            authoritative_status_source = f"current_provider_status:{current_status_source}"
        else:
            candidate_status = historical_status_class
            authoritative_status_source = f"historical_provider_status:{historical_status_source or 'status'}"
        for offset, task_id in enumerate(task_ids):
            candidate_owns_result = bool(result_present and task_id == explicit_result_task_id)
            candidate = {
                "task_id": task_id,
                "provider": provider,
                "status": candidate_status,
                "result_url": result_url if candidate_owns_result else "",
                "result_url_present": candidate_owns_result,
                "result_url_source": source_name if candidate_owns_result else "",
                "clip_path": clip_path,
                "clip_bytes": clip_bytes,
                "clip_valid": clip_valid,
                "submitted_at": submitted_at,
                "completed_at": completed_at,
                "progress": max(0, min(100, progress)),
                "source": source_name,
            }
            existing = next((entry for entry in record["task_candidates"] if entry.get("task_id") == task_id), None)
            if existing:
                for key, value in candidate.items():
                    if key == "status" and _status_authority_rank(value) < _status_authority_rank(existing.get("status")):
                        continue
                    if value not in (None, "", False, 0, [], {}):
                        existing[key] = value
            else:
                record["task_candidates"].append(candidate)
            if not record["primary_task_id"] and offset == 0:
                record["primary_task_id"] = task_id
            elif task_id != record["primary_task_id"] and task_id not in record["fallback_task_ids"]:
                record["fallback_task_ids"].append(task_id)
        persisted_winner = _text_value(merged, "winning_task_id", "scene_winner_task")
        if persisted_winner:
            record["winning_task_id"] = persisted_winner
        active_task = _text_value(merged, "active_task_id", "provider_task_id", "task_id", "provider_video_id", "video_id", "canonical_task_selected")
        if active_task:
            record["active_task_id"] = active_task
        if provider:
            record["provider_key"] = provider
        status_applied = False
        if status_raw and _status_authority_rank(candidate_status) >= _status_authority_rank(record.get("status")):
            record["status"] = candidate_status
            status_applied = True
        if task_ids:
            record["dispatch_state"] = "task_submitted"
            record["dispatchable"] = False
            record["task_id_present"] = True
            record["task_pollable"] = bool(
                merged.get("task_pollable") is not False
                and (merged.get("task_pollable") or merged.get("provider_poll_called") or task_ids)
            )
            record["effective_submit_outcome"] = "accepted" if record["task_pollable"] else str(
                merged.get("effective_submit_outcome") or "accepted"
            )
            record["transport_http"] = max(
                record["transport_http"],
                _as_int(merged.get("transport_http") or merged.get("submit_http_status") or merged.get("provider_submit_http_status"), 0),
            )
            record["transport_anomaly"] = bool(
                record["transport_anomaly"]
                or merged.get("transport_anomaly")
                or record["transport_http"] >= 400
            )
            record["duplicate_submit_prevented"] = bool(
                record["duplicate_submit_prevented"]
                or (record["task_pollable"] and record["transport_anomaly"])
                or merged.get("duplicate_submit_prevented")
            )
        elif dispatch_state:
            record["dispatch_state"] = dispatch_state
        record["dispatch_attempted"] = bool(
            record["dispatch_attempted"]
            or merged.get("dispatch_attempted")
            or merged.get("scene_dispatch_attempted")
            or merged.get("provider_submit_called")
        )
        if dispatch_block_reason:
            record["dispatch_block_reason"] = dispatch_block_reason
        if dispatch_idempotency_key:
            record["dispatch_idempotency_key"] = dispatch_idempotency_key
        record["dispatch_recovered"] = bool(
            record["dispatch_recovered"]
            or merged.get("dispatch_recovered")
            or merged.get("missing_scene_dispatch_recovered")
        )
        if merged.get("dispatchable") is not None:
            record["dispatchable"] = bool(merged.get("dispatchable"))
        if merged.get("exhausted") is not None:
            record["exhausted"] = bool(merged.get("exhausted"))
        if submitted_at:
            record["submitted_at"] = submitted_at
        record["submitted_at_epoch"] = max(
            record["submitted_at_epoch"],
            _as_int(merged.get("submitted_at_epoch") or merged.get("scene_submitted_at_epoch") or merged.get("provider_started_at_epoch"), 0),
        )
        if started_at:
            record["started_at"] = started_at
        record["started_at_epoch"] = max(
            record["started_at_epoch"],
            _as_int(merged.get("started_at_epoch") or merged.get("scene_started_at_epoch") or merged.get("provider_started_at_epoch"), 0),
        )
        record["progress"] = max(record["progress"], max(0, min(100, progress)))
        changed_at = _text_value(merged, "progress_last_changed_at", "provider_progress_last_changed_at")
        if changed_at:
            record["progress_last_changed_at"] = changed_at
        if result_url:
            record["result_url"] = result_url
        record["result_url_present"] = bool(record["result_url_present"] or result_present)
        if result_present:
            record["result_task_id"] = explicit_result_task_id
            record["result_url_source"] = source_name
            record["task_scene_mapping_verified"] = True
            if not clip_valid:
                record["result_processing_action"] = "download_and_validate"
        if status_applied or clip_valid or provider_status_conflict:
            record["authoritative_status_source"] = authoritative_status_source
        record["historical_status_ignored"] = bool(record["historical_status_ignored"] or provider_status_conflict)
        record["success_result_overrode_stale_not_start"] = bool(
            record["success_result_overrode_stale_not_start"] or provider_status_conflict
        )
        record["provider_status_conflict"] = bool(record["provider_status_conflict"] or provider_status_conflict)
        if provider_status_conflict:
            record["provider_status_conflict_resolution"] = "result_bearing_success_pending_validation"
        if clip_path:
            record["clip_path"] = clip_path
        record["clip_bytes"] = max(record["clip_bytes"], clip_bytes)
        record["clip_valid"] = bool(record["clip_valid"] or clip_valid)
        record["scene_validation_verified"] = bool(
            record["scene_validation_verified"]
            or (
                clip_valid
                and (
                    clip_bytes > 0
                    or bool(merged.get("validation_passed") or merged.get("output_validated"))
                )
            )
        )
        if completed_at:
            record["completed_at"] = completed_at
        record["failure_reason"] = _text_value(merged, "failure_reason", "provider_error", "blocker") or record["failure_reason"]
        actual_outbound_submit = bool(
            merged.get("provider_http_request_sent")
            or _as_int(merged.get("provider_http_status") or merged.get("submit_http_status") or merged.get("provider_submit_http_status"), 0) > 0
            or task_ids
        )
        if actual_outbound_submit:
            record["fallback_count"] = max(
                record["fallback_count"],
                _as_int(merged.get("fallback_count") or merged.get("provider_fallback_count"), 0),
            )
        record["fallback_allowed"] = bool(record["fallback_allowed"] or merged.get("fallback_allowed"))
        fallback_order = merged.get("fallback_provider_order")
        if isinstance(fallback_order, (list, tuple)) and fallback_order:
            record["fallback_provider_order"] = [str(item) for item in fallback_order if str(item or "").strip()]
        record["provider_elapsed_seconds"] = max(
            record["provider_elapsed_seconds"],
            _as_int(merged.get("provider_elapsed_seconds") or merged.get("provider_wait_elapsed_seconds"), 0),
        )
        record["scene_not_start_elapsed"] = max(record["scene_not_start_elapsed"], _as_int(merged.get("scene_not_start_elapsed"), 0))
        next_poll_at = _text_value(merged, "next_scene_poll_at", "next_poll_scheduled_at", "next_poll_at")
        if next_poll_at:
            record["next_poll_at"] = next_poll_at

    durable_ownership = product_video_durable_task_scene_owners(result)
    durable_status_by_index = _product_video_index_map(
        result.get("scene_status_by_index") or result.get("scene_status_by_scene")
    )
    durable_winner_by_index = _product_video_index_map(
        result.get("scene_winner_task_by_index")
    )
    for task_id, scene_index in (
        durable_ownership.get("task_to_scene_index") or {}
    ).items():
        index = _as_int(scene_index, 0)
        task_key = str(task_id or "").strip()
        if not task_key or index not in records:
            continue
        winner_task_id = str(durable_winner_by_index.get(str(index)) or "").strip()
        _merge_item(
            {
                "scene_index": index,
                "provider_task_id": task_key,
                "winning_task_id": task_key if winner_task_id == task_key else "",
                "provider": result.get("provider_pending_provider")
                or result.get("selected_provider"),
                "status": durable_status_by_index.get(str(index)) or "pending",
                "submitted_at": result.get("provider_started_at")
                or result.get("provider_wait_started_at"),
                "submitted_at_epoch": result.get("provider_started_at_epoch")
                or result.get("provider_wait_started_epoch"),
            },
            "result.durable_task_scene_ownership",
        )

    for container_name, container in (("project", project), ("job", job), ("result", result)):
        for key in ("scene_ledger", "scene_tasks", "provider_scene_tasks", "product_video_scene_tasks"):
            for item in _items(container.get(key)):
                _merge_item(item, f"{container_name}.{key}")
    for key in ("provider_events", "provider_attempts", "provider_pending_attempts", "provider_fallback_attempts"):
        for item in _items(result.get(key)):
            _merge_item(item, f"result.{key}")
    for item in _items(result.get("canonical_candidate_summaries")):
        _merge_item(item, "result.canonical_candidate_summaries")

    canonical_index = _as_int(result.get("canonical_scene_index"), 0)
    if canonical_index in records:
        canonical_task_id = str(result.get("canonical_task_id") or result.get("canonical_task_selected") or "").strip()
        canonical_item = {
            "scene_index": canonical_index,
            "provider": result.get("canonical_provider") or result.get("selected_provider"),
            "provider_task_id": canonical_task_id,
            "result_task_id": canonical_task_id,
            "status": result.get("canonical_status") or result.get("provider_status"),
            "actual_provider_payload_status": result.get("actual_provider_payload_status") or result.get("shopaikey_data_status"),
            "raw_provider_status_before_source_fix": result.get("raw_provider_status_before_source_fix") or result.get("provider_status_raw"),
            "result_url": result.get("canonical_result_url") or result.get("result_url"),
            "result_url_valid": result.get("canonical_result_url_present") or result.get("result_url_valid"),
            "clip_valid": result.get("scene_clip_validated"),
            "artifact_size": result.get("artifact_size") or result.get("output_bytes") or result.get("bytes"),
            "provider_progress_raw": result.get("provider_progress_raw"),
        }
        _merge_item(canonical_item, "result.canonical_summary")
    elif scene_count > 1 and (
        result.get("provider_task_ids")
        or result.get("provider_video_ids")
        or result.get("result_url_present")
        or result.get("provider_result_url_present")
        or result.get("final_video_path")
    ):
        unknown_scene_task_ignored = True

    validations = _product_video_index_map(result.get("scene_clip_validation_by_index"))
    result_urls = _product_video_index_map(result.get("scene_result_urls_by_index"))
    statuses = _product_video_index_map(result.get("scene_status_by_index") or result.get("scene_status_by_scene"))
    for index in expected:
        record = records[index]
        validation = validations.get(str(index))
        if isinstance(validation, dict):
            validation_bytes = _as_int(validation.get("bytes") or validation.get("size"), 0)
            validation_ok = bool(validation.get("ok") or validation.get("valid"))
            record["clip_valid"] = bool(record["clip_valid"] or validation_ok)
            record["clip_bytes"] = max(record["clip_bytes"], validation_bytes)
            path = str(validation.get("path") or validation.get("clip_path") or "").strip()
            if path:
                record["clip_path"] = path
            record["scene_validation_verified"] = bool(
                record["scene_validation_verified"]
                or (validation_ok and (validation_bytes > 0 or bool(path)))
            )
        result_value = result_urls.get(str(index))
        if str(result_value or "").strip().lower() in {"yes", "true", "1", "valid"}:
            # This summary contains no task identity. It may confirm an
            # already assigned result, but it cannot create scene ownership.
            if not record["result_url_present"]:
                record["phantom_result_prevented"] = True
                phantom_result_prevented = True
        if statuses.get(str(index)) not in (None, "") and not record["clip_valid"]:
            record["status"] = _status_class(statuses.get(str(index)))
        valid_candidates = [entry for entry in record["task_candidates"] if entry.get("clip_valid")]
        persisted_winner = record["winning_task_id"]
        winner = next((entry for entry in valid_candidates if entry.get("task_id") == persisted_winner), None)
        if winner is None and valid_candidates:
            winner = min(
                valid_candidates,
                key=lambda entry: (
                    _parse_time_epoch(entry.get("completed_at")) or float("inf"),
                    str(entry.get("task_id") or ""),
                ),
            )
        if winner:
            record["winning_task_id"] = str(winner.get("task_id") or record["winning_task_id"])
            record["active_task_id"] = record["winning_task_id"]
            record["provider_key"] = str(winner.get("provider") or record["provider_key"])
            record["result_url"] = str(winner.get("result_url") or record["result_url"])
            record["result_url_present"] = bool(winner.get("result_url_present") or record["result_url_present"])
            record["clip_path"] = str(winner.get("clip_path") or record["clip_path"])
            record["clip_bytes"] = max(record["clip_bytes"], _as_int(winner.get("clip_bytes"), 0))
            record["clip_valid"] = True
            record["completed_at"] = str(winner.get("completed_at") or record["completed_at"])
            record["status"] = "scene_clip_validated"
            record["progress"] = 100
        elif record["clip_valid"]:
            record["status"] = "scene_clip_validated"
            record["progress"] = 100
        else:
            active = next(
                (
                    entry
                    for entry in reversed(record["task_candidates"])
                    if entry.get("status") in {"running", "not_start", "pending", "result_pending_validation"}
                ),
                None,
            )
            if active:
                record["active_task_id"] = str(active.get("task_id") or record["active_task_id"])
                record["provider_key"] = str(active.get("provider") or record["provider_key"])
                if active.get("status") == "result_pending_validation":
                    record["status"] = "result_pending_validation"
                    record["result_processing_action"] = "download_and_validate"
                else:
                    record["status"] = "provider_not_start" if active.get("status") in {"not_start", "pending"} else "provider_running"
            elif record["status"] == "failed":
                record["status"] = "failed"
            elif record["active_task_id"]:
                record["status"] = "provider_running"

        owned_task_ids = {
            str(record.get("primary_task_id") or "").strip(),
            str(record.get("active_task_id") or "").strip(),
            str(record.get("winning_task_id") or "").strip(),
            *[str(item or "").strip() for item in record.get("fallback_task_ids") or []],
        }
        owned_task_ids.discard("")
        if record["result_task_id"] and not _task_owner_verified(record["result_task_id"], index):
            record["result_url"] = ""
            record["result_url_present"] = False
            record["result_task_id"] = ""
            record["result_url_source"] = ""
            record["task_scene_mapping_verified"] = False
            durable_clip_without_task = bool(
                record["clip_valid"]
                and _status_class(record.get("status")) == "succeeded"
            )
            if not record["scene_validation_verified"] and not durable_clip_without_task:
                record["clip_valid"] = False
            record["result_processing_action"] = ""
            record["phantom_result_prevented"] = True
            phantom_result_prevented = True
        if not owned_task_ids:
            if record["result_url_present"] or record["result_url"]:
                record["phantom_result_prevented"] = True
                phantom_result_prevented = True
            record["result_url"] = ""
            record["result_url_present"] = False
            record["result_task_id"] = ""
            record["result_url_source"] = ""
            record["task_scene_mapping_verified"] = False
            durable_clip_without_task = bool(
                record["clip_valid"]
                and _status_class(record.get("status")) == "succeeded"
            )
            if not record["scene_validation_verified"] and not durable_clip_without_task:
                record["clip_valid"] = False
            record["result_processing_action"] = ""

    if scene_count == 1 and (
        result.get("final_mp4_valid")
        or result.get("final_mp4_validated")
        or result.get("final_video_validated")
        or result.get("final_video_path")
        or result.get("result_url_present")
        or result.get("provider_result_url_present")
    ):
        records[1]["clip_valid"] = True
        records[1]["status"] = "scene_clip_validated"
        records[1]["progress"] = 100
        records[1]["clip_path"] = str(result.get("final_video_path") or result.get("final_mp4_path") or records[1]["clip_path"] or "")

    if zero_task_watchdog.get("zero_task_progress_guard"):
        watchdog_states = dict(zero_task_watchdog.get("scene_dispatch_state_by_index") or {})
        for index in expected:
            record = records[index]
            if record["active_task_id"] or record["task_candidates"] or record["clip_valid"]:
                continue
            watchdog_state = str(watchdog_states.get(str(index)) or "queued_waiting_for_dispatch")
            record["dispatch_state"] = watchdog_state
            if watchdog_state == "terminal_failed":
                record["status"] = "terminal_failed"
                record["failure_reason"] = str(zero_task_watchdog.get("zero_task_terminal_reason") or "no_eligible_provider_before_scene_dispatch")
                record["dispatch_block_reason"] = record["failure_reason"]
                record["dispatchable"] = False
                record["exhausted"] = True
                record["fallback_count"] = int(zero_task_watchdog.get("fallback_count_effective") or 0)
            else:
                record["status"] = "queued_waiting_for_dispatch"
                record["dispatchable"] = True
                record["exhausted"] = False

    # A scene that lacks a task is still actionable. Keep that truth durable
    # across worker restarts instead of letting a generic pending state turn
    # the whole confirmed job into a terminal failure.
    for index in expected:
        record = records[index]
        status_class = _status_class(record.get("status"))
        if record["clip_valid"]:
            record["dispatch_state"] = "task_submitted"
            record["dispatchable"] = False
            record["exhausted"] = False
        elif (
            record["active_task_id"]
            or record["task_candidates"]
        ) and status_class not in {"failed", "succeeded"} and not (
            (
                str(record.get("status") or "").strip().lower()
                in {"provider_stalled_not_start", "provider_scene_stalled"}
                or str(record.get("failure_reason") or "").strip().lower()
                in {"provider_stalled_not_start", "provider_scene_stalled"}
            )
            and not record["fallback_allowed"]
            and not record["fallback_provider_order"]
        ):
            record["dispatch_state"] = "task_submitted"
            record["dispatchable"] = False
            record["exhausted"] = False
        elif (
            str(record.get("status") or "").strip().lower()
            in {"provider_stalled_not_start", "provider_scene_stalled"}
            or str(record.get("failure_reason") or "").strip().lower()
            in {"provider_stalled_not_start", "provider_scene_stalled"}
        ) and (
            not record["fallback_allowed"]
            and not record["fallback_provider_order"]
        ):
            record["dispatch_state"] = "exhausted"
            record["dispatchable"] = False
            record["exhausted"] = True
        elif status_class == "failed":
            record["dispatch_state"] = record["dispatch_state"] or "submit_blocked_with_reason"
            record["dispatchable"] = False
            record["exhausted"] = True
        else:
            record["dispatch_state"] = record["dispatch_state"] or "submit_in_progress"
            record["dispatchable"] = True
            record["exhausted"] = False

    completed_indexes = [index for index in expected if records[index]["clip_valid"]]
    unresolved_indexes = [index for index in expected if index not in completed_indexes]
    active_indexes = [
        index
        for index in unresolved_indexes
        if (
            _status_class(records[index].get("status")) in {"running", "not_start", "pending"}
            and not records[index]["exhausted"]
            and (
                bool(records[index]["active_task_id"])
                or any(entry.get("status") in {"running", "not_start", "pending"} for entry in records[index]["task_candidates"])
            )
        )
    ]
    dispatchable_indexes = [
        index
        for index in unresolved_indexes
        if bool(records[index]["dispatchable"])
        and not records[index]["active_task_id"]
        and not records[index]["clip_valid"]
    ]
    fallback_candidate_indexes = [
        index
        for index in unresolved_indexes
        if bool(records[index]["fallback_allowed"] or records[index]["fallback_provider_order"])
        and not records[index]["clip_valid"]
    ]
    unprocessed_result_indexes = [
        index
        for index in unresolved_indexes
        if records[index]["result_url_present"] and not records[index]["clip_valid"]
    ]
    exhausted_indexes = [
        index
        for index in unresolved_indexes
        if bool(records[index]["exhausted"])
        and index not in active_indexes
        and index not in dispatchable_indexes
        and index not in fallback_candidate_indexes
    ]
    failed_indexes = list(exhausted_indexes)
    coverage_count = len(completed_indexes)
    coverage_complete = coverage_count >= scene_count
    raw_concat_attempted = bool(result.get("concat_attempted") or result.get("stitch_attempted"))
    final_delivered_raw = bool(
        result.get("final_delivered")
        or result.get("final_mp4_delivered")
        or result.get("delivery_succeeded")
        or result.get("video_delivered")
        or project.get("video_delivered_at")
        or project.get("video_delivery_message_id")
    )
    concat_attempted = bool(raw_concat_attempted and coverage_complete)
    concat_output_valid = bool(
        coverage_complete
        and (
            result.get("concat_output_valid")
            or result.get("stitch_output_valid")
            or str(result.get("concat_status") or "").strip().lower() == "completed"
            or final_delivered_raw
        )
    )
    explicit_final_valid = bool(
        result.get("final_mp4_valid")
        or result.get("final_mp4_validated")
        or result.get("final_video_validated")
        or result.get("output_validated")
        or final_delivered_raw
    )
    final_assembly_valid = bool(
        (scene_count == 1 and coverage_complete and explicit_final_valid)
        or (
            scene_count > 1
            and coverage_complete
            and concat_output_valid
            and explicit_final_valid
            and (concat_attempted or final_delivered_raw)
        )
    )
    final_delivered = bool(final_assembly_valid and final_delivered_raw)
    terminal_requested = str(result.get("terminal_state") or result.get("final_decision") or "").strip().lower() == "failed_no_charge"
    processing_truth = bool(
        active_indexes
        or dispatchable_indexes
        or fallback_candidate_indexes
        or unprocessed_result_indexes
    )
    explicit_terminal_without_scene_plan = bool(
        terminal_requested
        and not explicit_scene_plan
        and result.get("continue_polling") is False
    )
    if explicit_terminal_without_scene_plan:
        processing_truth = False
    terminal_no_charge = bool(
        unresolved_indexes
        and not processing_truth
        and (
            len(exhausted_indexes) == len(unresolved_indexes)
            or (terminal_requested and not explicit_scene_plan)
        )
    )
    if final_delivered:
        aggregate_status = "completed"
        aggregate_reason = "final_video_delivered"
    elif terminal_no_charge:
        aggregate_status = "failed_no_charge"
        aggregate_reason = str(zero_task_watchdog.get("zero_task_terminal_reason") or "required_scene_exhausted_no_charge")
    elif final_assembly_valid:
        aggregate_status = "ready_for_delivery"
        aggregate_reason = "final_concat_validated"
    elif concat_attempted:
        aggregate_status = "concatenating"
        aggregate_reason = "full_scene_coverage_concat_running"
    elif coverage_complete:
        aggregate_status = "ready_for_concat"
        aggregate_reason = "all_required_scene_clips_valid"
    elif coverage_count > 0:
        aggregate_status = "processing_partial_scene_success"
        aggregate_reason = "waiting_for_remaining_scenes"
    else:
        aggregate_status = "processing_scenes"
        aggregate_reason = "waiting_for_scene_clips"

    if zero_task_watchdog.get("zero_task_progress_guard"):
        progress_cap = 20
    elif final_delivered:
        progress_cap = 100
    elif final_assembly_valid:
        progress_cap = 95
    elif coverage_complete:
        progress_cap = 85
    elif coverage_count > 0:
        progress_cap = 70
    else:
        progress_cap = 60
    raw_progress = max(
        _as_int(job.get("progress_percent"), 0),
        _as_int(result.get("final_progress_after_reconcile") or result.get("progress_percent"), 0),
    )
    progress_floor = (
        10
        if zero_task_watchdog.get("zero_task_progress_guard")
        else (100 if final_delivered else (90 if final_assembly_valid else (80 if coverage_complete else (55 if coverage_count else 20))))
    )
    effective_progress = min(
        progress_cap,
        max(progress_floor, 0 if zero_task_watchdog.get("zero_task_progress_guard") else raw_progress),
    )
    progress_cap_correction = bool(raw_progress > progress_cap)
    scene_task_map = {
        str(index): [entry.get("task_id") for entry in records[index]["task_candidates"] if entry.get("task_id")]
        for index in expected
    }
    scene_dispatch_attempt_by_index = {str(index): bool(records[index]["dispatch_attempted"]) for index in expected}
    scene_dispatch_block_reason_by_index = {str(index): str(records[index]["dispatch_block_reason"] or "") for index in expected}
    scene_dispatch_idempotency_keys = {str(index): str(records[index]["dispatch_idempotency_key"] or "") for index in expected}
    scene_dispatch_state_by_index = {str(index): str(records[index]["dispatch_state"] or "submit_in_progress") for index in expected}
    scene_status_by_index = {str(index): str(records[index]["status"] or "pending_submit") for index in expected}
    scene_active_task_by_index = {str(index): str(records[index]["active_task_id"] or "") for index in expected}
    scene_winner_task_by_index = {str(index): str(records[index]["winning_task_id"] or "") for index in expected}
    scene_provider_progress_by_index = {str(index): _as_int(records[index]["progress"], 0) for index in expected}
    scene_result_available_by_index = {str(index): bool(records[index]["result_url_present"]) for index in expected}
    scene_clip_valid_by_index = {str(index): bool(records[index]["clip_valid"]) for index in expected}
    result_task_id_by_scene = {str(index): str(records[index]["result_task_id"] or "") for index in expected}
    result_url_source_by_scene = {str(index): str(records[index]["result_url_source"] or "") for index in expected}
    authoritative_status_source_by_scene = {
        str(index): str(records[index]["authoritative_status_source"] or "") for index in expected
    }
    result_processing_action_by_scene = {
        str(index): str(records[index]["result_processing_action"] or "") for index in expected
    }
    effective_submit_outcome_by_scene = {
        str(index): str(records[index]["effective_submit_outcome"] or "") for index in expected
    }
    submitted_scene_count = sum(1 for index in expected if records[index]["task_candidates"] or records[index]["active_task_id"])
    current_scene_index = unresolved_indexes[0] if unresolved_indexes else (expected[-1] if expected else 0)
    next_poll_candidates = [str(records[index]["next_poll_at"] or "") for index in unresolved_indexes if records[index]["next_poll_at"]]
    next_scene_poll_at = min(next_poll_candidates) if next_poll_candidates else str(result.get("next_poll_scheduled_at") or "")
    panel_source = ",".join(sources_used) or "initial_scene_plan"
    concat_waiting = bool(scene_count > 1 and not coverage_complete)
    return {
        "scene_ledger": [records[index] for index in expected],
        "scene_ledger_source": panel_source,
        "panel_scene_ledger_source": panel_source,
        "scene_task_map": scene_task_map,
        "required_scene_indexes": expected,
        "dispatched_scene_indexes": [index for index in expected if records[index]["active_task_id"] or records[index]["task_candidates"]],
        "undispatched_scene_indexes": [index for index in expected if index in dispatchable_indexes],
        "dispatchable_scene_indexes": dispatchable_indexes,
        "active_scene_indexes": active_indexes,
        "fallback_candidate_indexes": fallback_candidate_indexes,
        "unprocessed_result_indexes": unprocessed_result_indexes,
        "exhausted_scene_indexes": exhausted_indexes,
        "scene_dispatch_state_by_index": scene_dispatch_state_by_index,
        "scene_dispatch_attempt_by_index": scene_dispatch_attempt_by_index,
        "scene_dispatch_block_reason_by_index": scene_dispatch_block_reason_by_index,
        "scene_dispatch_idempotency_key": scene_dispatch_idempotency_keys,
        "missing_scene_dispatch_recovered": bool(any(records[index]["dispatch_recovered"] for index in expected)),
        "processing_truth_applied": bool(processing_truth and not final_delivered),
        "stale_persisted_failure_cleared": bool(processing_truth and str(job.get("status") or "").strip().lower() in {"failed", "error"}),
        "terminal_suppressed_due_to_active_scene": bool(active_indexes and terminal_requested),
        "terminal_suppressed_due_to_dispatchable_scene": bool(dispatchable_indexes and terminal_requested),
        "terminal_blocked_by_active_task": bool(active_indexes),
        "terminal_blocked_by_pending_scene": bool(dispatchable_indexes),
        "terminal_blocked_by_unprocessed_result": bool(unprocessed_result_indexes),
        "terminal_eligibility": bool(terminal_no_charge),
        "final_terminal_eligibility": bool(terminal_no_charge),
        "state_repair_event": (
            "processing_truth_overrode_stale_persisted_failure"
            if processing_truth and str(job.get("status") or "").strip().lower() in {"failed", "error"}
            else ""
        ),
        "task_scene_index_map": dict(task_to_scene_index),
        "task_to_scene_index": dict(task_to_scene_index),
        "task_scene_mapping_conflicts": dict(task_scene_mapping_conflicts),
        "task_scene_mapping_verified": bool(not task_scene_mapping_conflicts),
        "result_task_id_by_scene": result_task_id_by_scene,
        "result_url_source_by_scene": result_url_source_by_scene,
        "authoritative_status_source_by_scene": authoritative_status_source_by_scene,
        "result_processing_action_by_scene": result_processing_action_by_scene,
        "effective_submit_outcome_by_scene": effective_submit_outcome_by_scene,
        "duplicate_submit_prevented": any(
            bool(records[index]["duplicate_submit_prevented"]) for index in expected
        ),
        "historical_status_ignored": any(bool(records[index]["historical_status_ignored"]) for index in expected),
        "success_result_overrode_stale_not_start": any(
            bool(records[index]["success_result_overrode_stale_not_start"]) for index in expected
        ),
        "provider_status_conflict": any(bool(records[index]["provider_status_conflict"]) for index in expected),
        "provider_status_conflict_resolution": next(
            (
                str(records[index]["provider_status_conflict_resolution"])
                for index in expected
                if records[index]["provider_status_conflict_resolution"]
            ),
            "",
        ),
        "phantom_result_prevented": bool(
            phantom_result_prevented
            or any(bool(records[index]["phantom_result_prevented"]) for index in expected)
        ),
        "scene_status_by_index": scene_status_by_index,
        "scene_status_by_scene": scene_status_by_index,
        "scene_active_task_by_index": scene_active_task_by_index,
        "scene_winner_task_by_index": scene_winner_task_by_index,
        "scene_provider_progress_by_index": scene_provider_progress_by_index,
        "scene_result_available_by_index": scene_result_available_by_index,
        "scene_clip_valid_by_index": scene_clip_valid_by_index,
        "scene_result_urls_by_index": {key: "yes" if value else "no" for key, value in scene_result_available_by_index.items()},
        "scene_clip_validation_by_index": {
            str(index): {
                "ok": bool(records[index]["clip_valid"]),
                "path_present": bool(records[index]["clip_path"]),
                "bytes": _as_int(records[index]["clip_bytes"], 0),
            }
            for index in expected
        },
        "unresolved_scene_indexes": unresolved_indexes,
        "missing_scene_indexes": unresolved_indexes,
        "next_scene_poll_at": next_scene_poll_at,
        "required_scene_count": scene_count,
        "completed_scene_count": coverage_count,
        "unresolved_scene_count": len(unresolved_indexes),
        "failed_scene_count": len(failed_indexes),
        "scene_tasks_total": scene_count,
        "scene_tasks_created_count": scene_count,
        "scene_tasks_submitted": submitted_scene_count,
        "scene_tasks_submitted_count": submitted_scene_count,
        "scene_tasks_completed": coverage_count,
        "scene_success_count": coverage_count,
        "scenes_total": scene_count,
        "scenes_done": coverage_count,
        "scenes_pending": sum(1 for index in unresolved_indexes if records[index]["status"] == "pending_submit"),
        "scenes_running": sum(1 for index in unresolved_indexes if records[index]["status"] in {"provider_running", "provider_not_start"}),
        "current_scene_index": current_scene_index,
        "current_scene": current_scene_index,
        "current_scene_status": str(records[current_scene_index]["status"] if current_scene_index in records else ""),
        "scene_coverage_expected": scene_count,
        "scene_coverage_count": coverage_count,
        "scene_clip_coverage_complete": bool(coverage_complete),
        "scene_coverage_valid": bool(final_assembly_valid),
        "scene_coverage_valid_bool": bool(final_assembly_valid),
        "aggregate_job_status": aggregate_status,
        "aggregate_status_reason": aggregate_reason,
        "provider_status": "succeeded" if final_assembly_valid else ("failed_no_charge" if terminal_no_charge else "processing"),
        "normalized_provider_status": "succeeded" if final_assembly_valid else ("failed_no_charge" if terminal_no_charge else "processing"),
        "continue_polling": (
            bool(zero_task_watchdog.get("continue_polling"))
            if zero_task_watchdog.get("zero_task_progress_guard")
            else bool(unresolved_indexes and not terminal_no_charge)
        ),
        "provider_task_alive": bool(active_indexes and not terminal_no_charge),
        "terminal_state": "completed" if final_delivered else ("failed_no_charge" if terminal_no_charge else "final_rendering"),
        "final_decision": "delivered" if final_delivered else ("failed_no_charge" if terminal_no_charge else "continue_polling"),
        "concat_ready": bool(coverage_complete and scene_count > 1),
        "concat_attempted": bool(concat_attempted),
        "concat_attempted_raw": bool(raw_concat_attempted),
        "concat_attempt_count_raw": _as_int(result.get("concat_attempt_count"), 0),
        "concat_attempt_count": _as_int(result.get("concat_attempt_count"), 0) if concat_attempted else 0,
        "concat_waiting_for_scene_coverage": concat_waiting,
        "concat_output_valid": bool(concat_output_valid),
        "concat_status": "completed" if concat_output_valid else ("ready_to_concat" if coverage_complete else "waiting_for_required_scenes"),
        "concat_duration_seconds": (
            result.get("concat_duration_seconds") or result.get("final_duration_seconds") or 0
        ) if concat_attempted else 0,
        "final_duration_coverage_reason": "" if final_assembly_valid else ("waiting_for_required_scenes" if unresolved_indexes else "waiting_for_final_concat"),
        "final_mp4_valid": bool(final_assembly_valid),
        "final_mp4_validated": bool(final_assembly_valid),
        "job_final_result_url_present": bool(final_assembly_valid),
        "result_url_present": bool(final_assembly_valid),
        "provider_result_url_present": bool(final_assembly_valid),
        "result_url_found": bool(final_assembly_valid),
        "result_url_valid": bool(final_assembly_valid),
        "result_url": str(result.get("result_url") or result.get("provider_result_url") or "") if final_assembly_valid else "",
        "provider_result_url": str(result.get("provider_result_url") or result.get("result_url") or "") if final_assembly_valid else "",
        "final_delivered": bool(final_delivered),
        "delivery_succeeded": bool(final_delivered),
        "delivery_blocked_by_scene_coverage": bool(scene_count > 1 and not final_assembly_valid),
        "invalid_delivery_attempt_prevented": bool(scene_count > 1 and not final_assembly_valid),
        "artifact_valid_for_charge_after_coverage": bool(final_assembly_valid),
        "public_progress_cap": progress_cap,
        "public_effective_progress": effective_progress,
        "final_progress_after_reconcile": effective_progress,
        "progress_cap_correction": progress_cap_correction,
        "progress_cap_correction_from": raw_progress if progress_cap_correction else 0,
        "progress_cap_correction_to": progress_cap if progress_cap_correction else 0,
        "render_progress_source": (
            "final_concat_validated"
            if final_assembly_valid
            else ("partial_scene_coverage" if coverage_count else "waiting_for_remaining_scenes")
        ),
        "source_of_truth": (
            "final_concat_validated"
            if final_assembly_valid
            else ("partial_scene_coverage" if coverage_count else "waiting_for_remaining_scenes")
        ),
        "final_artifact_source": "final_concat_validated" if final_assembly_valid else ("scene_clip_validated" if coverage_count else ""),
        "public_progress_source": "scene_ledger_coverage",
        "zero_task_watchdog_triggered": bool(zero_task_watchdog.get("zero_task_watchdog_triggered")),
        "dispatch_grace_seconds": _as_int(zero_task_watchdog.get("dispatch_grace_seconds"), VIDEO_SCENE_DISPATCH_GRACE_SECONDS_DEFAULT),
        "dispatch_grace_elapsed": _as_int(zero_task_watchdog.get("dispatch_grace_elapsed"), 0),
        "valid_provider_task_count": _as_int(zero_task_watchdog.get("valid_provider_task_count"), 0),
        "zero_task_progress_guard": bool(zero_task_watchdog.get("zero_task_progress_guard")),
        "progress_suppressed_without_task": bool(zero_task_watchdog.get("progress_suppressed_without_task")),
        "public_stage": str(zero_task_watchdog.get("public_stage") or ""),
        "dispatch_recovery_attempted": bool(zero_task_watchdog.get("dispatch_recovery_attempted")),
        "dispatch_recovery_result": str(zero_task_watchdog.get("dispatch_recovery_result") or ""),
        "zero_task_terminal_reason": str(zero_task_watchdog.get("zero_task_terminal_reason") or ""),
        "runtime_candidate_keys": list(zero_task_watchdog.get("runtime_candidate_keys") or []),
        "preconfirm_candidate_keys": list(zero_task_watchdog.get("preconfirm_candidate_keys") or []),
        "candidate_set_consistent": bool(zero_task_watchdog.get("candidate_set_consistent", True)),
        "final_eligible_provider_count": _as_int(zero_task_watchdog.get("final_eligible_provider_count"), 0),
        "fallback_count_effective": _as_int(zero_task_watchdog.get("fallback_count_effective"), 0),
        "provider_http_request_sent": bool(zero_task_watchdog.get("provider_http_request_sent")),
        "provider_http_status": _as_int(zero_task_watchdog.get("provider_http_status"), 0),
        "canonical_scope": "job_summary" if scene_count > 1 else "scene",
        "canonical_scene_index": _as_int(result.get("canonical_scene_index"), 0),
        "canonical_does_not_imply_job_success": bool(scene_count > 1),
        "unresolved_scenes_preserved": bool(unresolved_indexes),
        "unknown_scene_task_ignored_for_coverage": bool(unknown_scene_task_ignored),
        "panel_completed_scene_count": coverage_count,
        "panel_unresolved_scene_count": len(unresolved_indexes),
        "scene_ledger_rendered_at": now_text(now_dt),
    }


def product_video_scene_coverage_state(
    project: dict | None = None,
    job: dict | None = None,
    result: dict | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Authoritative Product Video scene coverage gate.

    Multi-scene Product Video must have one valid clip for every scene index and
    a valid concat output before delivery/charge can proceed. This function is
    intentionally provider-free and works from persisted job/project metadata so
    status/debug can recover after registry memory is lost.
    """
    project = dict(project or {})
    job = dict(job or {})
    result = dict(result or {})
    ledger = product_video_scene_ledger_state(project, job, result, now=now)
    missing = list(ledger.get("unresolved_scene_indexes") or [])
    now_dt = now or datetime.now()
    created_epoch = _parse_time_epoch(
        result.get("provider_started_at")
        or job.get("started_at")
        or job.get("updated_at")
        or job.get("created_at")
    )
    elapsed = max(
        _as_int(result.get("scene_coverage_elapsed_seconds") or result.get("provider_wait_elapsed_seconds") or result.get("provider_elapsed_seconds"), 0),
        int(max(0, now_dt.timestamp() - created_epoch)) if created_epoch > 0 else 0,
    )
    timeout_seconds = max(60, _as_int(result.get("missing_scene_timeout_seconds") or result.get("scene_coverage_timeout_seconds") or result.get("provider_wait_max_seconds"), 20 * 60))
    timeout = bool(missing and elapsed >= timeout_seconds)
    scene_count = _as_int(ledger.get("required_scene_count"), 1)
    if not missing:
        action = "concat" if scene_count > 1 and not ledger.get("concat_output_valid") else "complete"
    elif timeout:
        action = "timeout"
    else:
        action = "poll"
    return {
        **ledger,
        "scene_plan_recovered": bool(str(ledger.get("scene_ledger_source") or "").startswith("initial_")),
        "scene_plan_source": str(ledger.get("scene_ledger_source") or "initial_scene_plan"),
        "expected_scene_indexes": list(range(1, scene_count + 1)),
        "missing_scene_action": action,
        "missing_scene_timeout_seconds": timeout_seconds,
        "missing_scene_elapsed_seconds": elapsed,
        "missing_scene_coverage_timeout": bool(timeout),
    }


def _product_video_charge_first_int(source: dict[str, Any], keys: tuple[str, ...], default: int = 0) -> int:
    for key in keys:
        value = source.get(key)
        if value not in (None, ""):
            return _as_int(value, default)
    return int(default or 0)


def product_video_delivery_charge_decision(
    project: dict | None = None,
    job: dict | None = None,
    result: dict | None = None,
) -> dict[str, Any]:
    """Pure Product Video charge gate for post-delivery billing.

    This never touches wallet state. Runtime callers must execute the returned
    amount only after this says ok=True, then persist the returned idempotency
    key with the wallet result.
    """
    project = dict(project or {})
    job = dict(job or {})
    result = dict(result or {})
    invoice = _json_loads(project.get("invoice_json") or result.get("invoice_json") or result.get("invoice"), {})
    merged = {**project, **job, **invoice, **result}
    job_id = _as_int(job.get("id") or job.get("job_id") or result.get("job_id"), 0)
    recovery_existing_tasks_only = bool(
        result.get("recovery_existing_tasks_only")
        or job.get("recovery_existing_tasks_only")
        or project.get("recovery_existing_tasks_only")
    )
    no_charge_contract = bool(recovery_existing_tasks_only or merged.get("no_charge"))
    if no_charge_contract:
        return {
            "ok": False,
            "already_charged": False,
            "amount_xu": 0,
            "wallet_charge_amount_xu": 0,
            "recovery_existing_tasks_only": recovery_existing_tasks_only,
            "charge_skip_reason": (
                "existing_task_recovery_no_charge"
                if recovery_existing_tasks_only
                else "no_charge_contract"
            ),
        }
    delivered = bool(
        project.get("video_delivered_at")
        or project.get("video_delivery_message_id")
        or result.get("final_delivered")
        or result.get("final_mp4_delivered")
        or result.get("delivery_succeeded")
        or result.get("video_delivered")
    )
    already_charged = _product_video_charge_first_int(
        merged,
        ("charged_amount_xu", "total_xu_charged", "charged_xu"),
        0,
    )
    if already_charged > 0 or (result.get("wallet_charge_recorded") and result.get("charge_tx_id")):
        return {
            "ok": True,
            "already_charged": True,
            "amount_xu": already_charged,
            "charge_skip_reason": "already_charged",
            "charge_idempotency_key": str(result.get("charge_idempotency_key") or ""),
        }
    if not delivered:
        return {"ok": False, "amount_xu": 0, "charge_skip_reason": "delivery_required_before_charge"}
    final_path = str(
        result.get("final_video_path")
        or result.get("final_mp4_path")
        or result.get("output_path")
        or project.get("final_video_path")
        or ""
    ).strip()
    local_ok = False
    if final_path:
        try:
            local_ok = os.path.isfile(final_path) and os.path.getsize(final_path) > 0
        except OSError:
            local_ok = False
    valid = bool(
        result.get("final_mp4_valid")
        or result.get("final_mp4_validated")
        or result.get("output_validated")
        or result.get("validation_passed")
        or result.get("mp4_validator_result") == "valid_mp4"
        or local_ok
    )
    if not valid:
        return {"ok": False, "amount_xu": 0, "charge_skip_reason": "valid_mp4_required_before_charge"}
    coverage = product_video_scene_coverage_state(project, job, result)
    if not coverage.get("artifact_valid_for_charge_after_coverage"):
        return {
            "ok": False,
            "amount_xu": 0,
            "charge_skip_reason": "scene_coverage_required_before_charge",
            **coverage,
        }
    user_visible = _product_video_charge_first_int(
        merged,
        ("user_visible_price_xu", "package_xu", "package_price_xu", "package_base_xu"),
        0,
    )
    quoted = _product_video_charge_first_int(
        merged,
        ("persisted_quoted_price_xu", "quoted_price_xu", "quoted_price"),
        user_visible,
    )
    planned = _product_video_charge_first_int(
        merged,
        ("customer_charge_planned_xu", "wallet_charge_amount_xu"),
        quoted,
    )
    fallback_amount = _product_video_charge_first_int(
        merged,
        ("total_xu_estimated", "total_xu", "total"),
        0,
    )
    amount = _as_int(planned or quoted or user_visible or fallback_amount, 0)
    quote_values = [value for value in (user_visible, quoted, planned) if _as_int(value, 0) > 0]
    quote_consistent = bool(not quote_values or len({_as_int(value, 0) for value in quote_values}) == 1)
    if not quote_consistent:
        return {
            "ok": False,
            "amount_xu": 0,
            "user_visible_price_xu": user_visible or amount,
            "persisted_quoted_price_xu": quoted or amount,
            "customer_charge_planned_xu": planned or amount,
            "wallet_charge_amount_xu": amount,
            "quote_consistent": False,
            "charge_skip_reason": "product_video_quote_mismatch_no_charge",
        }
    if amount <= 0:
        return {"ok": False, "amount_xu": 0, "charge_skip_reason": "charge_amount_missing"}
    return {
        "ok": True,
        "already_charged": False,
        "amount_xu": amount,
        "user_visible_price_xu": user_visible or amount,
        "persisted_quoted_price_xu": quoted or amount,
        "customer_charge_planned_xu": planned or amount,
        "wallet_charge_amount_xu": amount,
        "quote_consistent": True,
        "charge_idempotency_key": f"product_video_final_delivery:{job_id}:{amount}",
        "charge_skip_reason": "",
    }


def complete_video_job(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    final_video_path: str = "",
    final_video_file_id: str = "",
    result: dict | None = None,
) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    job = get_video_render_job(conn, int(job_id))
    if not job:
        return {"ok": False, "reason": "job_not_found"}
    current = now_text()

    def begin_completion_mutation() -> tuple[dict | None, dict, dict]:
        """Lock and recheck cancellation immediately before a terminal mutation."""
        conn.execute("BEGIN IMMEDIATE")
        locked_job = get_video_render_job(conn, int(job_id))
        if not locked_job:
            conn.rollback()
            return {"ok": False, "reason": "job_not_found"}, {}, {}
        locked_project = get_video_project(
            conn,
            _as_int(locked_job.get("project_id"), 0),
        )
        if not locked_project:
            conn.rollback()
            return {
                "ok": False,
                "reason": "project_not_found",
                "job": locked_job,
            }, {}, {}
        locked_outbox = get_product_video_dispatch_outbox(
            conn,
            job_id=int(job_id),
        )
        cancellation = product_video_recovery_cancellation_state(
            locked_project,
            locked_outbox,
        )
        locked_job_status = str(locked_job.get("status") or "").strip().lower()
        if locked_job_status in {"cancelled", "canceled"} or cancellation.get("cancelled"):
            blocker = (
                "job_cancelled"
                if locked_job_status in {"cancelled", "canceled"}
                else str(cancellation.get("blocker") or "product_video_cancelled")
            )
            conn.rollback()
            return {
                "ok": False,
                "reason": blocker,
                "cancelled": True,
                "job": get_video_render_job(conn, int(job_id)),
                "project": get_video_project(
                    conn,
                    _as_int(locked_job.get("project_id"), 0),
                ),
            }, {}, {}
        return None, locked_job, locked_project

    persisted_payload = _json_loads(str(job.get("result_json") or ""), {})
    if not isinstance(persisted_payload, dict):
        persisted_payload = {}
    has_route_marker = bool(
        persisted_payload.get("product_video_durable_public_seam")
        or isinstance(
            persisted_payload.get("product_video_route_decision"),
            dict,
        )
    )
    route_validation = (
        product_video_public_seam.validate_persisted_product_video_route_decision(
            persisted_payload,
            environ=os.environ,
        )
        if has_route_marker
        else {"ready": True, "decision": None}
    )
    if has_route_marker and not route_validation.get("ready"):
        return {
            "ok": False,
            "reason": str(
                route_validation.get("blocker")
                or "product_video_route_decision_invalid"
            ),
            "job": job,
        }
    incoming_payload = dict(result or {})
    payload = {**persisted_payload, **incoming_payload}
    recovery_existing_tasks_only = bool(
        persisted_payload.get("recovery_existing_tasks_only")
        or incoming_payload.get("recovery_existing_tasks_only")
    )
    if recovery_existing_tasks_only:
        payload.update(
            {
                "recovery_existing_tasks_only": True,
                "provider_submit_allowed": False,
                "provider_submit_block_reason": "existing_task_recovery_read_only",
                "automatic_retry_allowed": False,
                "automatic_resubmit_allowed": False,
                "automatic_fallback_allowed": False,
                "no_charge": True,
                "charge": 0,
                "charged_xu": 0,
                "wallet_charge_recorded": False,
                "final_delivery_charge_allowed": False,
            }
        )
    route_decision = route_validation.get("decision")
    if isinstance(route_decision, dict):
        payload.update(
            product_video_public_seam.product_video_route_decision_payload(
                route_decision
            )
        )
    if final_video_path:
        payload["final_video_path"] = final_video_path
    if final_video_file_id:
        payload["final_video_file_id"] = final_video_file_id
    project = get_video_project(conn, int(job["project_id"]))
    asset_pack = _json_loads(str(project.get("asset_pack_json") or ""), {})
    product_job = _is_product_video_project(project)
    allow_admin_test = bool(asset_pack.get("admin_video_delivery") or asset_pack.get("test_pattern"))
    claim_only_diagnostic = bool(
        asset_pack.get("claim_only_diagnostic")
        or asset_pack.get("diagnostic_claim_only")
        or payload.get("claim_only_diagnostic")
        or payload.get("diagnostic_claim_only")
    )
    safe_claim_only_diagnostic = bool(
        claim_only_diagnostic
        and asset_pack.get("source") == "product_video"
        and not asset_pack.get("provider_call")
        and not payload.get("provider_call")
        and not asset_pack.get("public_user")
        and not payload.get("public_user")
        and not asset_pack.get("test_pattern")
        and not payload.get("test_pattern")
        and not asset_pack.get("admin_video_delivery")
        and not payload.get("admin_video_delivery")
        and (asset_pack.get("no_charge") or asset_pack.get("admin_no_charge") or payload.get("no_charge"))
    )
    terminal_state = "needs_admin_review" if safe_claim_only_diagnostic else "final_delivered"
    if product_job and not safe_claim_only_diagnostic:
        coverage = product_video_scene_coverage_state(project, job, payload)
        payload.update(coverage)
        if coverage.get("delivery_blocked_by_scene_coverage"):
            payload.update(
                {
                    "ok": False,
                    "final_delivered": False,
                    "final_mp4_delivered": False,
                    "delivery_succeeded": False,
                    "artifact_valid_for_charge": False,
                    "charge_skip_reason": "scene_coverage_required_before_charge",
                    "public_progress_source": "waiting_missing_scene_coverage",
                    "final_progress_after_reconcile": min(84, max(20, _as_int(job.get("progress_percent"), 65))),
                }
            )
            if coverage.get("missing_scene_coverage_timeout"):
                payload.update(
                    {
                        "terminal_state": "failed_no_charge",
                        "final_decision": "failed_no_charge",
                        "provider_error": "missing_scene_coverage_timeout",
                        "blocker": "missing_scene_coverage_timeout",
                        "continue_polling": False,
                        "no_charge": True,
                    }
                )
                blocked, _locked_job, _locked_project = begin_completion_mutation()
                if blocked is not None:
                    return blocked
                conn.execute("UPDATE video_jobs SET result_json=? WHERE id=?", (_json_dumps(payload), int(job_id)))
                return fail_video_job(conn, job_id=int(job_id), error="missing_scene_coverage_timeout", retry=False)
            payload.update(
                {
                    "terminal_state": "final_rendering",
                    "final_decision": "continue_polling",
                    "continue_polling": True,
                    "provider_error": "missing_scene_coverage_waiting",
                    "blocker": "missing_scene_coverage_waiting",
                    "no_charge": True,
                }
            )
            current = now_text()
            blocked, locked_job, _locked_project = begin_completion_mutation()
            if blocked is not None:
                return blocked
            conn.execute(
                """UPDATE video_jobs
                   SET status='processing', result_json=?, progress_percent=?,
                       progress_message='waiting_missing_scene_coverage', updated_at=?
                   WHERE id=?""",
                (
                    _json_dumps(payload),
                    int(payload.get("final_progress_after_reconcile") or 65),
                    current,
                    int(job_id),
                ),
            )
            conn.execute(
                """UPDATE video_projects
                   SET status='processing', video_terminal_state='final_rendering',
                       error_log='missing_scene_coverage_waiting', updated_at=?
                   WHERE project_id=?""",
                (current, int(locked_job["project_id"])),
            )
            conn.commit()
            return {"ok": False, "reason": "missing_scene_coverage_waiting", "job": get_video_render_job(conn, int(job_id)), "project": get_video_project(conn, int(locked_job["project_id"]))}
        validation = video_final_output.validate_final_video_output(
            path=str(final_video_path or payload.get("final_video_path") or ""),
            result=payload,
            require_audio=bool((_json_loads(str(project.get("addon_plan_json") or ""), {}) or {}).get("voice_enabled")),
            allow_admin_test=allow_admin_test,
        )
        payload["final_output_validation"] = validation
        if not validation.get("ok"):
            payload["terminal_state"] = "failed_no_charge"
            blocked, _locked_job, _locked_project = begin_completion_mutation()
            if blocked is not None:
                return blocked
            conn.execute("UPDATE video_jobs SET result_json=? WHERE id=?", (_json_dumps(payload), int(job_id)))
            return fail_video_job(conn, job_id=int(job_id), error=str(validation.get("reason") or "final_output_invalid"), retry=False)
        uiflow3_contract = video_uiflow3_execution_contract.validate_execution_contract(
            project,
            payload,
            artifact_validation=validation,
            require_payload_identity=True,
            require_artifact=True,
        )
        if uiflow3_contract.get("applies"):
            payload["uiflow3_execution_contract"] = uiflow3_contract
        if not uiflow3_contract.get("ok"):
            blocker = str(
                uiflow3_contract.get("blocker")
                or "uiflow3_execution_contract_invalid"
            )
            payload.update(
                {
                    "terminal_state": "failed_no_charge",
                    "final_decision": "failed_no_charge",
                    "blocker": blocker,
                    "provider_error": blocker,
                    "continue_polling": False,
                    "no_charge": True,
                    "charge": 0,
                    "charged_xu": 0,
                }
            )
            blocked, _locked_job, _locked_project = begin_completion_mutation()
            if blocked is not None:
                return blocked
            conn.execute(
                "UPDATE video_jobs SET result_json=? WHERE id=?",
                (_json_dumps(payload), int(job_id)),
            )
            failed = fail_video_job(
                conn,
                job_id=int(job_id),
                error=blocker,
                retry=False,
            )
            return {**failed, "ok": False, "reason": blocker}
        duration_contract = product_video_duration_contract(project, payload, validation)
        payload["final_duration_contract"] = duration_contract
        payload["expected_duration_seconds"] = duration_contract["expected_duration_seconds"]
        payload["final_duration_seconds"] = duration_contract["actual_duration_seconds"]
        if not duration_contract.get("ok"):
            payload["terminal_state"] = "failed_no_charge"
            payload["finalizer_error"] = duration_contract["reason"]
            blocked, _locked_job, _locked_project = begin_completion_mutation()
            if blocked is not None:
                return blocked
            conn.execute("UPDATE video_jobs SET result_json=? WHERE id=?", (_json_dumps(payload), int(job_id)))
            return fail_video_job(conn, job_id=int(job_id), error=str(duration_contract.get("reason") or "final_duration_invalid"), retry=False)
        payload.update(
            {
                "output_bytes": int(validation.get("bytes") or 0),
                "output_duration": float(validation.get("duration") or 0),
                "has_video": bool(validation.get("has_video")),
                "has_audio": bool(validation.get("has_audio")),
                "status": "completed",
                "canonical_status": "completed",
                "terminal": True,
                "terminal_state": "final_delivered",
                "final_decision": "final_delivered",
                "continue_polling": False,
                "blocker": "",
                "provider_error": "",
                "visual_classification": payload.get("visual_classification") or "final_ai_video",
                "final_classification": payload.get("final_classification") or "final_ai_video",
            }
        )
    elif safe_claim_only_diagnostic:
        payload["terminal_state"] = terminal_state
    try:
        blocked, locked_job, locked_project = begin_completion_mutation()
        if blocked is not None:
            return blocked
        job_cursor = conn.execute(
            """UPDATE video_jobs
               SET status='completed', result_json=?, progress_percent=?,
                   progress_message=?, completed_at=?, updated_at=?, lease_expires_at=NULL
               WHERE id=?
                 AND LOWER(COALESCE(status,'')) NOT IN ('cancelled','canceled')
                 AND NOT EXISTS (
                     SELECT 1 FROM video_projects p
                      WHERE p.project_id=video_jobs.project_id
                        AND LOWER(COALESCE(p.status,'')) IN ('cancelled','canceled')
                 )
                 AND NOT EXISTS (
                     SELECT 1 FROM video_dispatch_outbox o
                      WHERE o.job_id=video_jobs.id
                        AND LOWER(COALESCE(o.dispatch_status,'')) IN ('cancelled','canceled')
                 )""",
            (
                _json_dumps(payload),
                95 if product_job and not safe_claim_only_diagnostic else 100,
                "final_mp4_ready_waiting_delivery" if product_job and not safe_claim_only_diagnostic else "completed",
                current,
                current,
                int(job_id),
            ),
        )
        project_cursor = conn.execute(
            """UPDATE video_projects
               SET status='completed', final_video_path=?, final_video_file_id=?,
                   video_terminal_state=?, video_terminal_locked_at=?,
                   video_artifact_hash=?, completed_at=?, updated_at=?
               WHERE project_id=?
                 AND LOWER(COALESCE(status,'')) NOT IN ('cancelled','canceled')
                 AND NOT EXISTS (
                     SELECT 1 FROM video_dispatch_outbox o
                      WHERE o.job_id=?
                        AND LOWER(COALESCE(o.dispatch_status,'')) IN ('cancelled','canceled')
                 )""",
            (
                str(final_video_path or ""),
                str(final_video_file_id or ""),
                terminal_state,
                current,
                str(payload.get("video_artifact_hash") or payload.get("artifact_hash") or ""),
                current,
                current,
                int(locked_job["project_id"]),
                int(job_id),
            ),
        )
        if job_cursor.rowcount != 1 or project_cursor.rowcount != 1:
            conn.rollback()
            fresh_job = get_video_render_job(conn, int(job_id))
            fresh_project = get_video_project(
                conn,
                _as_int((fresh_job or {}).get("project_id"), 0),
            )
            fresh_outbox = get_product_video_dispatch_outbox(
                conn,
                job_id=int(job_id),
            )
            fresh_cancellation = product_video_recovery_cancellation_state(
                fresh_project,
                fresh_outbox,
            )
            return {
                "ok": False,
                "reason": str(
                    fresh_cancellation.get("blocker")
                    or "completion_state_cas_lost"
                ),
                "cancelled": bool(fresh_cancellation.get("cancelled")),
                "job": fresh_job,
                "project": fresh_project,
            }
        conn.commit()
        return {
            "ok": True,
            "job": get_video_render_job(conn, int(job_id)),
            "project": get_video_project(conn, int(locked_job["project_id"])),
        }
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


def note_video_delivery_result(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    sent: bool,
    delivery_message_id: str = "",
    success_message_id: str = "",
    reason: str = "",
) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    job = get_video_render_job(conn, int(job_id))
    if not job:
        return {"ok": False, "reason": "job_not_found"}
    project = get_video_project(conn, int(job.get("project_id") or 0))
    if not project:
        return {"ok": False, "reason": "project_not_found", "job": job}
    payload = _json_loads(job.get("result_json"), {})
    if not isinstance(payload, dict):
        payload = {}
    has_route_marker = bool(
        payload.get("product_video_durable_public_seam")
        or isinstance(payload.get("product_video_route_decision"), dict)
    )
    route_validation = (
        product_video_public_seam.validate_persisted_product_video_route_decision(
            payload,
            environ=os.environ,
        )
        if has_route_marker
        else {"ready": True}
    )
    if has_route_marker and not route_validation.get("ready"):
        return {
            "ok": False,
            "sent": False,
            "reason": str(
                route_validation.get("blocker")
                or "product_video_route_decision_invalid"
            ),
            "job": job,
            "project": project,
        }
    uiflow3_contract = video_uiflow3_execution_contract.validate_execution_contract(
        project,
        payload,
        artifact_validation=(
            payload.get("final_output_validation")
            if isinstance(payload.get("final_output_validation"), dict)
            else None
        ),
        require_payload_identity=True,
        require_artifact=True,
    )
    if not uiflow3_contract.get("ok"):
        return {
            "ok": False,
            "sent": False,
            "reason": str(
                uiflow3_contract.get("blocker")
                or "uiflow3_execution_contract_invalid"
            ),
            "job": job,
            "project": project,
        }
    already_delivered = bool(project.get("video_delivered_at") or project.get("video_delivery_message_id"))
    if already_delivered and sent:
        return {"ok": True, "duplicate_prevented": True, "job": job, "project": project}
    current = now_text()
    attempts = int(project.get("delivery_attempt_count") or 0) + 1
    if sent:
        delivery_message_id_value = str(delivery_message_id or success_message_id or "").strip()
        if str(payload.get("admission_mode") or "") == PRODUCT_VIDEO_PROBATION_ADMISSION_MODE:
            scene_tasks = [
                dict(item)
                for item in (payload.get("scene_tasks") or payload.get("provider_scene_tasks") or [])
                if isinstance(item, dict)
            ]
            coverage_expected = max(1, _as_int(payload.get("scene_coverage_expected") or payload.get("scenes_total"), 1))
            coverage_count = max(0, _as_int(payload.get("scene_coverage_count") or payload.get("scenes_done"), 0))
            coverage_complete = bool(
                payload.get("scene_clip_coverage_complete")
                or coverage_count >= coverage_expected
            )
            result_url_present = bool(
                payload.get("result_url")
                or payload.get("provider_result_url")
                or payload.get("download_url")
                or any(item.get("result_url") or item.get("download_url") for item in scene_tasks)
            )
            promotion_eligible = bool(
                coverage_complete
                and (payload.get("final_mp4_valid") or payload.get("final_mp4_validated") or payload.get("artifact_valid_for_charge"))
                and _as_int(payload.get("output_bytes") or payload.get("artifact_size"), 0) > 0
                and result_url_present
                and delivery_message_id_value
            )
            if promotion_eligible:
                payload.update(
                    {
                        "probation_result": "success",
                        "probation_terminal_at": current,
                        "probation_cooldown_active": False,
                        "probation_cooldown_until": "",
                        "last_valid_mp4_at": current,
                        "provider_health_promotion_eligible": True,
                        "probation_result_validation_blocker": "",
                    }
                )
            else:
                payload.update(
                    {
                        "probation_result": "pending",
                        "provider_health_promotion_eligible": False,
                        "probation_result_validation_blocker": "valid_result_scene_coverage_final_mp4_delivery_message_required",
                    }
                )
        payload.update(
            {
                "final_delivery_attempted": True,
                "telegram_delivery_status": "sent",
                "final_delivered": True,
                "final_mp4_delivered": True,
                "delivery_succeeded": True,
                "video_delivered": True,
                "final_delivered_at": current,
                "delivery_message_id": delivery_message_id_value,
                "telegram_delivery_message_id": delivery_message_id_value,
                "download_button_visible": True,
                "public_progress_source": "final_delivered",
                "final_progress_after_reconcile": 100,
                "charge_after_delivery_attempted": bool(payload.get("charge_after_delivery_attempted")),
                "charge_skip_reason": str(payload.get("charge_skip_reason") or ""),
            }
        )
        conn.execute(
            """UPDATE video_projects
               SET video_delivery_started_at=COALESCE(video_delivery_started_at, ?),
                   video_delivered_at=?,
                   video_delivery_message_id=?,
                   video_success_message_id=?,
                   video_terminal_state='final_delivered',
                   video_terminal_locked_at=COALESCE(video_terminal_locked_at, ?),
                   delivery_attempt_count=?,
                   updated_at=?
               WHERE project_id=?""",
            (
                current,
                current,
                str(delivery_message_id or project.get("video_delivery_message_id") or ""),
                str(success_message_id or delivery_message_id or project.get("video_success_message_id") or ""),
                current,
                attempts,
                current,
                int(project["project_id"]),
            ),
        )
        conn.execute(
            """UPDATE video_jobs
               SET status='completed', result_json=?, progress_percent=100,
                   progress_message='delivered', completed_at=COALESCE(completed_at, ?), updated_at=?
               WHERE id=?""",
            (_json_dumps(payload), current, current, int(job_id)),
        )
    else:
        clean_reason = str(reason or "telegram_delivery_failed").replace("\n", " ")[:500]
        coverage = product_video_scene_coverage_state(project, job, payload)
        coverage_reason = clean_reason in {
            "scene_coverage_required_before_delivery",
            "missing_scene_coverage_waiting",
            "missing_scene_coverage_timeout",
            "final_duration_short_scene_coverage_missing",
        } or bool(payload.get("delivery_blocked_by_scene_coverage") or coverage.get("delivery_blocked_by_scene_coverage"))
        if coverage_reason:
            payload.update(
                {
                    **coverage,
                    "final_delivery_attempted": False,
                    "telegram_delivery_status": "delivery_blocked_by_scene_coverage",
                    "final_delivered": False,
                    "final_mp4_delivered": False,
                    "delivery_succeeded": False,
                    "video_delivered": False,
                    "charge_after_delivery_attempted": bool(payload.get("charge_after_delivery_attempted")),
                    "charge_skip_reason": "scene_coverage_required_before_charge",
                    "public_progress_source": "waiting_missing_scene_coverage",
                    "final_progress_after_reconcile": min(84, max(20, _as_int(job.get("progress_percent"), 65))),
                    "no_charge": True,
                }
            )
            if coverage.get("missing_scene_coverage_timeout") or clean_reason == "missing_scene_coverage_timeout":
                payload.update(
                    {
                        "terminal_state": "failed_no_charge",
                        "final_decision": "failed_no_charge",
                        "continue_polling": False,
                        "provider_error": "missing_scene_coverage_timeout",
                        "blocker": "missing_scene_coverage_timeout",
                    }
                )
                conn.execute(
                    """UPDATE video_projects
                       SET video_terminal_state='failed_no_charge', error_log='missing_scene_coverage_timeout',
                           delivery_attempt_count=?, updated_at=?
                       WHERE project_id=?""",
                    (attempts, current, int(project["project_id"])),
                )
                conn.execute(
                    """UPDATE video_jobs
                       SET status='failed', result_json=?, progress_percent=?,
                           progress_message='missing_scene_coverage_timeout', completed_at=COALESCE(completed_at, ?), updated_at=?
                       WHERE id=?""",
                    (_json_dumps(payload), int(payload.get("final_progress_after_reconcile") or 84), current, current, int(job_id)),
                )
            else:
                payload.update(
                    {
                        "terminal_state": "final_rendering",
                        "final_decision": "continue_polling",
                        "continue_polling": True,
                        "provider_error": "missing_scene_coverage_waiting",
                        "blocker": "missing_scene_coverage_waiting",
                    }
                )
                conn.execute(
                    """UPDATE video_projects
                       SET status='processing', video_terminal_state='final_rendering',
                           error_log='missing_scene_coverage_waiting', delivery_attempt_count=?, updated_at=?
                       WHERE project_id=?""",
                    (attempts, current, int(project["project_id"])),
                )
                conn.execute(
                    """UPDATE video_jobs
                       SET status='processing', result_json=?, progress_percent=?,
                           progress_message='waiting_missing_scene_coverage', updated_at=?
                       WHERE id=?""",
                    (_json_dumps(payload), int(payload.get("final_progress_after_reconcile") or 65), current, int(job_id)),
                )
            conn.commit()
            return {"ok": True, "sent": False, "delivery_blocked_by_scene_coverage": True, "job": get_video_render_job(conn, int(job_id)), "project": get_video_project(conn, int(project["project_id"]))}
        payload.update(
            {
                "final_delivery_attempted": True,
                "telegram_delivery_status": clean_reason,
                "final_delivered": False,
                "final_mp4_delivered": False,
                "delivery_succeeded": False,
                "video_delivered": False,
                "charge_after_delivery_attempted": bool(payload.get("charge_after_delivery_attempted")),
                "charge_skip_reason": "delivery_failed_no_charge",
                "public_progress_source": "delivery_failed_waiting_retry",
                "final_progress_after_reconcile": max(85, min(95, _as_int(job.get("progress_percent"), 95))),
            }
        )
        conn.execute(
            """UPDATE video_projects
               SET video_delivery_started_at=COALESCE(video_delivery_started_at, ?),
                   video_terminal_state='telegram_delivery_failed',
                   error_log=?,
                   delivery_attempt_count=?,
                   updated_at=?
               WHERE project_id=?""",
            (
                current,
                clean_reason,
                attempts,
                current,
                int(project["project_id"]),
            ),
        )
        conn.execute(
            """UPDATE video_jobs
               SET result_json=?, progress_percent=?,
                   progress_message=?, updated_at=?
               WHERE id=?""",
            (
                _json_dumps(payload),
                int(payload.get("final_progress_after_reconcile") or 95),
                clean_reason,
                current,
                int(job_id),
            ),
        )
    conn.commit()
    return {"ok": True, "sent": bool(sent), "job": get_video_render_job(conn, int(job_id)), "project": get_video_project(conn, int(project["project_id"]))}


def fail_video_job(conn: sqlite3.Connection, *, job_id: int, error: str, retry: bool = True) -> dict[str, Any]:
    ensure_video_project_queue_schema(conn)
    job = get_video_render_job(conn, int(job_id))
    if not job:
        return {"ok": False, "reason": "job_not_found"}
    project = get_video_project(conn, int(job.get("project_id") or 0))
    if project and (project.get("video_delivered_at") or project.get("video_delivery_message_id")):
        return {"ok": False, "reason": "late_fail_suppressed_after_delivery", "job": job, "project": project}
    attempts = int(job.get("attempts") or 0)
    max_attempts = int(job.get("max_attempts") or 3)
    current = now_text()
    payload = _json_loads(job.get("result_json"), {})
    if not isinstance(payload, dict):
        payload = {}
    if (
        payload.get("product_video_durable_public_seam")
        or isinstance(payload.get("product_video_route_decision"), dict)
    ):
        retry = False
    probation_mode = str(payload.get("admission_mode") or "") == PRODUCT_VIDEO_PROBATION_ADMISSION_MODE
    if probation_mode:
        retry = False
        cooldown_seconds = max(
            60,
            _as_int(
                os.getenv("PRODUCT_VIDEO_PROBATION_FAILURE_COOLDOWN_SECONDS"),
                PRODUCT_VIDEO_PROBATION_FAILURE_COOLDOWN_SECONDS_DEFAULT,
            ),
        )
        payload.update(
            {
                "probation_result": "failed",
                "probation_terminal_at": current,
                "probation_cooldown_started_at": current,
                "probation_cooldown_seconds": cooldown_seconds,
                "probation_cooldown_active": True,
                "probation_cooldown_until": now_text(datetime.now() + timedelta(seconds=cooldown_seconds)),
                "provider_health_promotion_eligible": False,
                "terminal_state": "failed_no_charge",
                "final_decision": "failed_no_charge",
                "continue_polling": False,
                "no_charge": True,
                "charge": 0,
                "charged_xu": 0,
            }
        )
    if retry and attempts < max_attempts:
        conn.execute(
            """UPDATE video_jobs
               SET status='queued', locked_by='', locked_at=NULL, lease_expires_at=NULL,
                   last_error=?, result_json=?, updated_at=?
               WHERE id=?""",
            (str(error or "")[:1000], _json_dumps(payload), current, int(job_id)),
        )
        conn.execute("UPDATE video_projects SET status='queued_for_worker', video_terminal_state='final_rendering', error_log=?, updated_at=? WHERE project_id=?", (str(error or "")[:2000], current, int(job["project_id"])))
        final_status = "queued"
    else:
        conn.execute(
            """UPDATE video_jobs
               SET status='failed', lease_expires_at=NULL,
                   last_error=?, result_json=?, completed_at=?, updated_at=?
               WHERE id=?""",
            (str(error or "")[:1000], _json_dumps(payload), current, current, int(job_id)),
        )
        conn.execute("UPDATE video_projects SET status='failed', video_terminal_state='failed_no_charge', video_terminal_locked_at=?, error_log=?, updated_at=? WHERE project_id=?", (current, str(error or "")[:2000], current, int(job["project_id"])))
        final_status = "failed"
    conn.commit()
    return {"ok": True, "status": final_status, "job": get_video_render_job(conn, int(job_id)), "project": get_video_project(conn, int(job["project_id"]))}


def defer_video_job_for_provider_polling(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    reason: str = "provider_in_progress",
    diagnostics: dict | None = None,
) -> dict[str, Any]:
    """Keep a real provider video job non-terminal while the provider is still rendering."""
    ensure_video_project_queue_schema(conn)
    job = get_video_render_job(conn, int(job_id))
    if not job:
        return {"ok": False, "reason": "job_not_found"}
    project = get_video_project(conn, int(job.get("project_id") or 0))
    if project and (project.get("video_delivered_at") or project.get("video_delivery_message_id")):
        return {"ok": False, "reason": "late_defer_suppressed_after_delivery", "job": job, "project": project}
    payload = _json_loads(job.get("result_json"), {})
    if not isinstance(payload, dict):
        payload = {}
    if isinstance(diagnostics, dict):
        payload.update(diagnostics)
    clean_reason = str(reason or payload.get("provider_error") or payload.get("blocker") or "provider_in_progress")[:1000]
    payload.update(
        {
            "ok": False,
            "continue_polling": True,
            "provider_pending_deferred": True,
            "provider_error": payload.get("provider_error") or clean_reason,
            "blocker": payload.get("blocker") or clean_reason,
            "no_charge": True,
        }
    )
    current = now_text()
    telemetry = reconcile_provider_progress_telemetry(job, payload, refresh_source="defer_provider_polling")
    interval_seconds = max(5, _as_int(payload.get("panel_refresh_interval_seconds"), 25))
    next_poll_at = now_text(datetime.now() + timedelta(seconds=interval_seconds))
    payload.update(telemetry)
    payload.update(
        {
            "autonomous_db_poller_enabled": True,
            "autonomous_poll_enabled": True,
            "db_poll_candidate": True,
            "registry_required_for_poll": False,
            "registry_missing_is_blocker": False,
            "next_poll_at": next_poll_at,
            "next_poll_scheduled": True,
            "next_poll_scheduled_at": next_poll_at,
            "next_refresh_expected_at": next_poll_at,
            "terminal_before_reconcile": str(payload.get("terminal_state") or job.get("status") or ""),
            "terminal_after_reconcile": "final_rendering",
            "terminal_override_reason": "provider_running_overrides_failed_no_charge",
            "no_new_paid_submit": True,
            "paid_fallback_not_used": True,
        }
    )
    progress = int(telemetry.get("final_progress_after_reconcile") or telemetry.get("final_progress") or 20)
    conn.execute(
        """UPDATE video_jobs
           SET status='queued', locked_by='', locked_at=NULL, lease_expires_at=NULL,
               last_error=?, result_json=?, progress_percent=?, progress_message=?, updated_at=?
           WHERE id=?""",
        (clean_reason, _json_dumps(payload), progress, "provider_in_progress", current, int(job_id)),
    )
    conn.execute(
        """UPDATE video_projects
           SET status='processing', video_terminal_state='final_rendering',
               error_log=?, updated_at=?
           WHERE project_id=?""",
        (clean_reason[:2000], current, int(job["project_id"])),
    )
    conn.commit()
    return {
        "ok": True,
        "status": "queued",
        "deferred": True,
        "continue_polling": True,
        "job": get_video_render_job(conn, int(job_id)),
        "project": get_video_project(conn, int(job["project_id"])),
    }


def process_claimed_video_job(
    conn: sqlite3.Connection,
    job: dict[str, Any],
    runner: Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any]],
) -> dict[str, Any]:
    project = get_video_project(conn, int(job.get("project_id") or 0))
    scenes = list_video_project_scenes(conn, int(job.get("project_id") or 0))
    try:
        result = runner(project, scenes)
        if not result or not result.get("ok"):
            raise RuntimeError(str((result or {}).get("error") or "video_render_failed"))
        result = {**inline_processor_trace_payload(), **dict(result or {})}
        return complete_video_job(
            conn,
            job_id=int(job.get("id") or job.get("job_id")),
            final_video_path=str(result.get("final_video_path") or ""),
            final_video_file_id=str(result.get("final_video_file_id") or ""),
            result=result,
        )
    except Exception as exc:
        return fail_video_job(conn, job_id=int(job.get("id") or job.get("job_id")), error=f"{type(exc).__name__}:{exc}")


def hydrate_video_job_payload(conn: sqlite3.Connection, job: dict[str, Any]) -> dict[str, Any]:
    if not job:
        return {}
    project_id = int(job.get("project_id") or 0)
    persisted_payload = _json_loads(str(job.get("result_json") or ""), {})
    if not isinstance(persisted_payload, dict):
        persisted_payload = {}
    route_payload = {
        key: persisted_payload[key]
        for key in product_video_public_seam.WORKER_ROUTE_PAYLOAD_KEYS
        if key in persisted_payload
    }
    return {
        **job,
        **route_payload,
        "project": get_video_project(conn, project_id),
        "scenes": list_video_project_scenes(conn, project_id),
    }
