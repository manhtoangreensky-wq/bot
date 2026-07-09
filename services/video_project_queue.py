"""SQLite-backed video project state machine and worker queue.

This module is intentionally provider-free. It stores planning state, creates a
persistent render job after final confirmation, and lets a worker claim jobs
atomically from SQLite.
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable
from urllib.parse import urlparse

from services import video_final_output
from services.video_provider_catalog import (
    model_metadata_from_resolution,
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
SCENE_STATUSES = ("pending", "gen_audio", "gen_image", "gen_video", "postprocess", "done", "failed")
JOB_STATUSES = ("queued", "processing", "completed", "failed", "cancelled")
VIDEO_RENDER_JOB_TYPE = "video_render"
PRODUCT_VIDEO_TIER_PRICE_MAP = {
    "low": 200,
    "trial": 200,
    "basic": 300,
    "common": 400,
    "good": 400,
    "standard": 500,
    "advanced": 600,
    "premium": 800,
    "pro": 1000,
    "studio": 1200,
    "high": 1200,
    "max": 1500,
}


def now_text(moment: datetime | None = None) -> str:
    return (moment or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")


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
    raw = str(value or "").strip().lower()
    if raw in {"200", "trial", "low"}:
        return "low"
    if raw in {"300", "basic"}:
        return "basic"
    if raw in {"400", "good", "common"}:
        return "common"
    if raw in {"500", "standard"}:
        return "standard"
    if raw in {"600", "advanced"}:
        return "advanced"
    if raw in {"800", "premium"}:
        return "premium"
    if raw in {"1000", "pro"}:
        return "pro"
    if raw in {"1200", "studio", "high"}:
        return "studio"
    if raw in {"1500", "max"}:
        return "max"
    return raw or "basic"


def _product_video_quote_consistency(invoice: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
    invoice = dict(invoice or {})
    project = dict(project or {})
    selected_tier = _product_video_selected_tier(
        invoice.get("tier")
        or invoice.get("tier_key")
        or invoice.get("package_xu")
        or invoice.get("quality_tier")
        or project.get("quality_tier")
        or project.get("total_xu_estimated")
        or "basic"
    )
    user_visible = _as_int(
        invoice.get("user_visible_price_xu")
        or invoice.get("package_xu")
        or invoice.get("package_price_xu")
        or invoice.get("quality_tier")
        or PRODUCT_VIDEO_TIER_PRICE_MAP.get(selected_tier)
        or 300,
        300,
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
    alive = provider_task_alive(payload)
    terminal_failure = str(payload.get("terminal_state") or payload.get("final_decision") or "").strip().lower() in {
        "failed",
        "failed_no_charge",
        "failed_refunded",
        "needs_admin_review",
    }
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
    provider_status = _provider_status_for_progress(payload, alive)
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
    if alive and provider_not_start and not provider_stalled_not_start:
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
    return {
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
                "primary_provider_in_progress"
                if actual_provider_running
                and str(payload.get("fallback_block_reason") or payload.get("fallback_blocked_reason") or "")
                in {"", "not_start_under_threshold", "provider_not_start", "provider_stalled_not_start"}
                else str(payload.get("fallback_block_reason") or payload.get("fallback_blocked_reason") or "")
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
        "elapsed_estimate_progress": render_progress if render_source in {"elapsed_provider_wait", "provider_raw_elapsed_max"} else 0,
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
        "provider_state_overrode_persisted_status": bool(alive and not terminal_failure and persisted_status in {"", "queued", "queued_for_worker", "draft"}),
        "persisted_status_before_reconcile": persisted_status,
        "persisted_progress_before_reconcile": persisted_progress,
        "final_status_after_reconcile": final_status,
        "terminal_state": "delivered" if final_delivered else ("final_rendering" if alive and not terminal_failure else str(payload.get("terminal_state") or "")),
        "final_user_visible_state": "delivered" if final_delivered else ("final_rendering" if alive and not terminal_failure else ("failed_no_charge" if terminal_failure else final_status)),
        "final_progress_after_reconcile": final_progress,
    }


def _columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _add_column_if_missing(conn: sqlite3.Connection, table_name: str, column_name: str, column_sql: str) -> None:
    if column_name not in _columns(conn, table_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")


def ensure_video_project_queue_schema(conn: sqlite3.Connection) -> None:
    """Create/adapt queue tables without dropping or deleting existing data."""
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
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_video_jobs_active_render_project
           ON video_jobs(project_id, job_type)
           WHERE project_id IS NOT NULL
             AND job_type='video_render'
             AND status IN ('queued','processing')"""
    )
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


def confirm_video_project_invoice(
    conn: sqlite3.Connection,
    *,
    project_id: int,
    user_id: int,
    balance_xu: int | None = None,
    deduct_func: Callable[[int, int], Any] | None = None,
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
    if active:
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
PRODUCT_VIDEO_DURATION_TOLERANCE_SECONDS = 0.7
PRODUCT_VIDEO_DEFAULT_PROVIDER_CHAIN = "shopaikey_video,key4u_video,toanaas_video,veo,kling,generic_http"
PRODUCT_VIDEO_ORCHESTRATION_MODE_RAW_DELIVERY = "single_task_legacy"
PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE = "per_scene_8s"
PRODUCT_VIDEO_RENDER_PIPELINE_HISTORICAL_CONCAT = "historical_multi_clip_concat"
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
) -> list[dict[str, Any]]:
    safe_job_id = str(job_id or "").strip() or "job"
    safe_count = max(1, min(20, int(scene_count or 1)))
    safe_duration = max(1, min(PRODUCT_VIDEO_SCENE_SECONDS, int(scene_duration_seconds or PRODUCT_VIDEO_SCENE_SECONDS)))
    return [
        {
            "scene_index": index,
            "scene_id": index,
            "clip_index": index,
            "request_job_id": f"{safe_job_id}-{index}",
            "scene_duration_seconds": safe_duration,
            "clip_duration_seconds": safe_duration,
            "provider": "",
            "provider_task_id": "",
            "provider_video_id": "",
            "status": "pending_submit",
            "clip_status": "pending_submit",
            "download_url_present": False,
            "result_url_valid": False,
            "raw_clip_duration": 0,
            "fallback_count": 0,
            "provider_wait_elapsed_seconds": 0,
            "provider_started_at_epoch": "",
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
    scene_duration = PRODUCT_VIDEO_SCENE_SECONDS
    invoice = _json_loads(str(project.get("invoice_json") or ""), {})
    if not isinstance(invoice, dict):
        invoice = {}
    quote_state = _product_video_quote_consistency(invoice, project)
    asset_pack = _json_loads(str(project.get("asset_pack_json") or ""), {})
    if not isinstance(asset_pack, dict):
        asset_pack = {}
    orchestration_mode = _product_video_orchestration_mode_from_sources(dict(job or {}), asset_pack, invoice, dict(project or {}))
    per_scene_orchestration = orchestration_mode == PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE
    render_pipeline_mode = (
        PRODUCT_VIDEO_RENDER_PIPELINE_HISTORICAL_CONCAT
        if per_scene_orchestration
        else PRODUCT_VIDEO_ORCHESTRATION_MODE_RAW_DELIVERY
    )
    scene_tasks = (
        product_video_initial_scene_tasks(job.get("id") or job.get("job_id") or "job", scene_count, scene_duration)
        if per_scene_orchestration
        else []
    )
    if provider_chain is not None:
        chain = list(provider_chain)
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
        tier=invoice.get("tier")
        or invoice.get("tier_key")
        or invoice.get("package_xu")
        or invoice.get("quality_tier")
        or project.get("quality_tier")
        or project.get("total_xu_estimated")
        or "basic",
        provider_chain=chain,
        scene_count=scene_count,
        required_capability="text_to_video_or_scene_video",
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
                    "model_used": model_metadata.get("selected_model") or "",
                    "model_used_in_payload": model_metadata.get("selected_model") or "",
                    "provider_model_map": dict(model_metadata.get("provider_model_map") or {}),
                    "contract_validation_status": model_metadata.get("contract_validation_status") or "",
                    "supports_concat": bool(model_metadata.get("supports_concat")),
                }
            )
    next_poll_at = now_text(current_dt + timedelta(seconds=25))
    provider_chain_resolved = bool(chain and model_resolution.get("ok"))
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
    return {
        "source": "product_video",
        "product_video": True,
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
        "current_scene_status": "pending_submit" if per_scene_orchestration else "",
        "final_concat_required": bool(per_scene_orchestration and scene_count > 1),
        "concat_status": "waiting_for_clips" if per_scene_orchestration and scene_count > 1 else "",
        "concat_ready": False,
        "configured_provider_chain": chain,
        "effective_provider_chain": chain,
        "provider_chain": chain,
        "provider_order": chain,
        "provider_chain_resolved": provider_chain_resolved,
        "provider_health_at_submit": provider_health_at_submit,
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
        return max(1, min(20, scene_count)) * max(1, min(PRODUCT_VIDEO_SCENE_SECONDS, scene_seconds))
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
    payload = dict(result or {})
    if final_video_path:
        payload["final_video_path"] = final_video_path
    if final_video_file_id:
        payload["final_video_file_id"] = final_video_file_id
    project = get_video_project(conn, int(job["project_id"]))
    asset_pack = _json_loads(str(project.get("asset_pack_json") or ""), {})
    product_job = str(asset_pack.get("source") or "") == "product_video" and bool(asset_pack.get("real_renderer_required"))
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
        validation = video_final_output.validate_final_video_output(
            path=str(final_video_path or payload.get("final_video_path") or ""),
            result=payload,
            require_audio=bool((_json_loads(str(project.get("addon_plan_json") or ""), {}) or {}).get("voice_enabled")),
            allow_admin_test=allow_admin_test,
        )
        payload["final_output_validation"] = validation
        if not validation.get("ok"):
            payload["terminal_state"] = "failed_no_charge"
            conn.execute("UPDATE video_jobs SET result_json=? WHERE id=?", (_json_dumps(payload), int(job_id)))
            conn.commit()
            return fail_video_job(conn, job_id=int(job_id), error=str(validation.get("reason") or "final_output_invalid"), retry=False)
        duration_contract = product_video_duration_contract(project, payload, validation)
        payload["final_duration_contract"] = duration_contract
        payload["expected_duration_seconds"] = duration_contract["expected_duration_seconds"]
        payload["final_duration_seconds"] = duration_contract["actual_duration_seconds"]
        if not duration_contract.get("ok"):
            payload["terminal_state"] = "failed_no_charge"
            payload["finalizer_error"] = duration_contract["reason"]
            conn.execute("UPDATE video_jobs SET result_json=? WHERE id=?", (_json_dumps(payload), int(job_id)))
            conn.commit()
            return fail_video_job(conn, job_id=int(job_id), error=str(duration_contract.get("reason") or "final_duration_invalid"), retry=False)
        payload.update(
            {
                "output_bytes": int(validation.get("bytes") or 0),
                "output_duration": float(validation.get("duration") or 0),
                "has_video": bool(validation.get("has_video")),
                "has_audio": bool(validation.get("has_audio")),
                "terminal_state": "final_delivered",
                "visual_classification": payload.get("visual_classification") or "final_ai_video",
                "final_classification": payload.get("final_classification") or "final_ai_video",
            }
        )
    elif safe_claim_only_diagnostic:
        payload["terminal_state"] = terminal_state
    conn.execute(
        """UPDATE video_jobs
           SET status='completed', result_json=?, progress_percent=?,
               progress_message=?, completed_at=?, updated_at=?, lease_expires_at=NULL
           WHERE id=?""",
        (
            _json_dumps(payload),
            95 if product_job and not safe_claim_only_diagnostic else 100,
            "final_mp4_ready_waiting_delivery" if product_job and not safe_claim_only_diagnostic else "completed",
            current,
            current,
            int(job_id),
        ),
    )
    conn.execute(
        """UPDATE video_projects
           SET status='completed', final_video_path=?, final_video_file_id=?,
               video_terminal_state=?, video_terminal_locked_at=?,
               video_artifact_hash=?, completed_at=?, updated_at=?
           WHERE project_id=?""",
        (
            str(final_video_path or ""),
            str(final_video_file_id or ""),
            terminal_state,
            current,
            str(payload.get("video_artifact_hash") or payload.get("artifact_hash") or ""),
            current,
            current,
            int(job["project_id"]),
        ),
    )
    conn.commit()
    return {"ok": True, "job": get_video_render_job(conn, int(job_id)), "project": get_video_project(conn, int(job["project_id"]))}


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
    already_delivered = bool(project.get("video_delivered_at") or project.get("video_delivery_message_id"))
    if already_delivered and sent:
        return {"ok": True, "duplicate_prevented": True, "job": job, "project": project}
    current = now_text()
    attempts = int(project.get("delivery_attempt_count") or 0) + 1
    if sent:
        payload.update(
            {
                "final_delivery_attempted": True,
                "telegram_delivery_status": "sent",
                "final_delivered": True,
                "final_mp4_delivered": True,
                "delivery_succeeded": True,
                "video_delivered": True,
                "final_delivered_at": current,
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
    if retry and attempts < max_attempts:
        conn.execute(
            """UPDATE video_jobs
               SET status='queued', locked_by='', locked_at=NULL, lease_expires_at=NULL,
                   last_error=?, updated_at=?
               WHERE id=?""",
            (str(error or "")[:1000], current, int(job_id)),
        )
        conn.execute("UPDATE video_projects SET status='queued_for_worker', video_terminal_state='final_rendering', error_log=?, updated_at=? WHERE project_id=?", (str(error or "")[:2000], current, int(job["project_id"])))
        final_status = "queued"
    else:
        conn.execute(
            """UPDATE video_jobs
               SET status='failed', lease_expires_at=NULL,
                   last_error=?, completed_at=?, updated_at=?
               WHERE id=?""",
            (str(error or "")[:1000], current, current, int(job_id)),
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
    return {
        **job,
        "project": get_video_project(conn, project_id),
        "scenes": list_video_project_scenes(conn, project_id),
    }
