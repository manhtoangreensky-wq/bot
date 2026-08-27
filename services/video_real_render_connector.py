"""Real provider connector for product video worker jobs.

This module bridges the B14/remote-worker job contract to existing video
providers. It never generates testsrc/color bars and never marks a job complete
without a downloaded MP4 for every rendered scene.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx

from services.multiscene_video_pipeline import (
    SceneSpec,
    create_multiscene_workspace,
    ensure_video_output,
    finalize_multiscene_scene_clips,
    load_multiscene_manifest,
    multiscene_manifest_scene_tasks,
    normalize_scene_duration,
    process_multiscene_video_pipeline,
    safe_run_ffmpeg,
    sync_multiscene_manifest,
)
from services import video_final_output
from services import video_ai_edit_provider
from services import product_video_addon_materialization
from services import video_project_queue as video_project_queue_service
from services.video_provider_base import VideoGenerationRequest
from services.video_provider_router import (
    PUBLIC_NO_VIDEO_PROVIDER_COPY,
    PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_FALLBACK_ONCE,
    PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_SCENE_FALLBACK_ONCE,
    PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_FINAL_CONFIRM,
    PRODUCT_VIDEO_SUBMIT_SOURCE_WORKER_POLL_EXISTING_TASK,
    capability_options,
    normalize_capability_values,
    product_video_route_contract,
    provider_status_payload,
    run_provider_generation,
)
from services.video_provider_catalog import model_metadata_from_resolution, resolve_product_video_model


REAL_VIDEO_RENDER_UNAVAILABLE = "real_video_renderer_unavailable"
FINAL_AI_VIDEO = "final_ai_video"
PARTIAL_SIMPLE_VIDEO = "partial_simple_video"
FAILED_NO_REAL_VISUAL = "failed_no_real_visual"
LOCAL_PLACEHOLDER_RENDERER = "local_scene_composer"
LOCAL_IMAGE_SEQUENCE_RENDERER = video_final_output.LOCAL_IMAGE_SEQUENCE_RENDERER
LOCAL_SCENE_CARD_RENDERER = video_final_output.LOCAL_SCENE_CARD_RENDERER
PROVIDER_SCENE_RENDERER = "provider_scene_video"
VISUAL_SOURCE_PROVIDER_MP4 = "provider_mp4"
VISUAL_SOURCE_LOCAL_PLACEHOLDER = "local_placeholder"
VISUAL_SOURCE_LOCAL_IMAGE_SEQUENCE = video_final_output.VISUAL_SOURCE_LOCAL_IMAGE_SEQUENCE
VISUAL_SOURCE_LOCAL_SCENE_CARD = video_final_output.VISUAL_SOURCE_LOCAL_SCENE_CARD
LOCAL_IMAGE_SEQUENCE_PRODUCT_TYPES = {"image_to_video", "storyboard_prompt", "script_to_video"}
LOCAL_SCENE_CARD_PRODUCT_TYPES = {"script_to_video", "storyboard_prompt", "multi_scene_film"}
PRODUCT_VIDEO_SCENE_IMAGE_INPUT_TYPES = {
    "storyboard_prompt",
    "storyboard_to_video",
    "video_ai_image",
    "image_to_video",
}
PROVIDER_BRIDGE_RENDERER = "video_provider_bridge"
PRODUCT_VIDEO_SCENE_SECONDS = 8
PRODUCT_VIDEO_MAX_UIFLOW3_SCENE_SECONDS = 15
PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE_8S = "per_scene_8s"
PRODUCT_VIDEO_ORCHESTRATION_MODE_LEGACY_SINGLE_TASK = "single_task_legacy"
PRODUCT_VIDEO_RENDER_PIPELINE_HISTORICAL_CONCAT = "historical_multi_clip_concat"
PRODUCT_VIDEO_DURATION_TOLERANCE_SECONDS = 0.7
PRODUCT_VIDEO_LOGO_DEFAULT_WIDTH_RATIO = 0.12
PRODUCT_VIDEO_LOGO_MAX_WIDTH_RATIO = 0.18
PRODUCT_VIDEO_LOGO_MARGIN_X_RATIO = 0.04
PRODUCT_VIDEO_LOGO_MARGIN_Y_RATIO = 0.035
PROVIDER_VIDEO_SOURCE = "provider"
PROVIDER_REQUIRED_PRODUCT_TYPES = {
    "video_ai_prompt",
    "prompt_vault_to_video",
    "self_shot_scene_change",
    "self_shot_cinematic_transform",
}
PROVIDER_REQUIRED_CAPABILITIES = {
    "text_to_video",
    "image_to_video",
    "video_to_video",
    "multi_scene_video",
    "scene_video",
    "text_to_video_or_scene_video",
    "delegates_to_selected_product",
}
PROVIDER_CLEAN_FAIL_FALLBACKS = {
    "clean_fail_provider_capability_missing",
    "delegate_or_clean_fail",
}

RAW_PROMPT_FRAME_MARKERS = (
    "chủ thể chính:",
    "chu the chinh:",
    "visual:",
    "prompt:",
    "provider:",
    "debug:",
    "pov trải nghiệm thật: add one subtle visual",
    "pov trai nghiem that: add one subtle visual",
)


LAST_RENDER_DIAGNOSTICS: dict[str, Any] = {}
PROVIDER_PENDING_BLOCKERS = {"provider_in_progress", "provider_pending", "provider_status_unknown"}
PROVIDER_PENDING_STATUS_MARKERS = {
    "not_start",
    "queued",
    "running",
    "processing",
    "in_progress",
    "pending",
    "media_generation_status_pending",
    "media_generation_status_in_progress",
    "media_generation_status_processing",
    "media_generation_status_running",
}
DEFAULT_PRODUCT_VIDEO_PROVIDER_MAX_WAIT_SECONDS = 20 * 60
DEFAULT_PRODUCT_VIDEO_FIRST_SCENE_NOT_START_GRACE_SECONDS = 60
DEFAULT_PRODUCT_VIDEO_SCENE_RUNNING_WITHOUT_RESULT_GRACE_SECONDS = 300
DEFAULT_PRODUCT_VIDEO_TOTAL_SCENE_TIMEOUT_SECONDS = 600
PRODUCT_VIDEO_PROVIDER_STALLED_NOT_START = "provider_stalled_not_start"


class RealVideoRenderError(RuntimeError):
    """Safe worker-facing render error with admin-only diagnostics."""

    def __init__(self, message: str = "", diagnostics: dict[str, Any] | None = None):
        super().__init__(message or REAL_VIDEO_RENDER_UNAVAILABLE)
        self.diagnostics = dict(diagnostics or {})


def _record_render_diagnostics(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global LAST_RENDER_DIAGNOSTICS
    LAST_RENDER_DIAGNOSTICS = dict(payload or {})
    return LAST_RENDER_DIAGNOSTICS


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, "", {}):
        return []
    return [value]


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _text_indicates_not_start(*values: Any) -> bool:
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


def _text_indicates_running(*values: Any) -> bool:
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


def _actual_status_payload_value(payload: dict[str, Any] | None = None) -> tuple[str, str, str]:
    data = dict(payload or {})
    source = str(data.get("provider_status_payload_source") or "").strip()
    shopaikey_data_status = _first_nonempty(
        data.get("shopaikey_data_status"),
        data.get("provider_status_payload_data_status"),
        data.get("actual_provider_payload_status"),
    )
    historical = _first_nonempty(
        data.get("raw_provider_status_before_source_fix"),
        data.get("raw_provider_status"),
        data.get("provider_status_raw"),
    )
    if shopaikey_data_status:
        return shopaikey_data_status, source or "shopaikey.data.status", historical
    shopaikey_raw = _first_nonempty(data.get("shopaikey_raw_status"))
    if source.startswith("shopaikey.data.") and shopaikey_raw:
        return shopaikey_raw, source, historical
    return _first_nonempty(data.get("raw_provider_status"), data.get("provider_status_raw"), data.get("nonterminal_provider_status"), data.get("provider_status"), data.get("status")), source, _first_nonempty(data.get("raw_provider_status_before_source_fix"))


def _actual_provider_payload_is_running(payload: dict[str, Any] | None = None) -> tuple[bool, str, str]:
    status, source, _raw_before = _actual_status_payload_value(payload)
    authoritative = bool(str(source or "").strip().startswith("shopaikey.data.") and status)
    running = bool(authoritative and _text_indicates_running(status) and not _text_indicates_not_start(status))
    return running, str(status or ""), str(source or "")


def _provider_attempts_indicate_not_start(data: dict[str, Any] | None = None) -> bool:
    data = dict(data or {})
    for key in ("provider_attempts", "provider_pending_attempts", "provider_events"):
        for item in _as_list(data.get(key)):
            if not isinstance(item, dict):
                continue
            debug = item.get("debug") if isinstance(item.get("debug"), dict) else {}
            merged = {**item, **debug}
            if _text_indicates_not_start(
                merged.get("shopaikey_data_status"),
                merged.get("shopaikey_raw_status"),
                merged.get("raw_provider_status"),
                merged.get("provider_status_raw"),
                merged.get("provider_status"),
                merged.get("normalized_provider_status"),
                merged.get("blocker"),
                merged.get("provider_error"),
            ):
                return True
    return False


def _provider_result_or_artifact_present(data: dict[str, Any] | None = None) -> bool:
    data = dict(data or {})
    if any(
        bool(data.get(key))
        for key in (
            "provider_result_url_present",
            "result_url_present",
            "download_url_present",
            "result_url_found",
            "final_mp4_valid",
            "final_mp4_validated",
            "final_video_validated",
            "delivery_succeeded",
            "delivered",
            "final_delivered",
        )
    ):
        return True
    for key in (
        "artifact_size",
        "artifact_bytes",
        "output_bytes",
        "final_video_bytes",
        "raw_provider_video_bytes",
        "downloaded_bytes",
    ):
        if _safe_int(data.get(key), 0) > 0:
            return True
    return False


def _not_start_elapsed_seconds(data: dict[str, Any] | None = None, job: dict | None = None) -> int:
    data = dict(data or {})
    job = dict(job or {})
    values = [
        _safe_int(data.get("scene_not_start_elapsed"), 0),
        _safe_int(data.get("provider_elapsed_seconds"), 0),
        _safe_int(data.get("provider_wait_elapsed_seconds"), 0),
        _safe_int(data.get("elapsed_wall_clock_seconds"), 0),
        _safe_int(data.get("previous_elapsed_seconds"), 0),
        _safe_int(job.get("scene_not_start_elapsed"), 0),
        _safe_int(job.get("provider_elapsed_seconds"), 0),
        _safe_int(job.get("provider_wait_elapsed_seconds"), 0),
        _safe_int(job.get("elapsed_wall_clock_seconds"), 0),
        _safe_int(job.get("previous_elapsed_seconds"), 0),
    ]
    return max(values or [0])


def _enforce_shopaikey_not_start_final_invariant(data: dict[str, Any] | None = None, *, job: dict | None = None) -> dict[str, Any]:
    current = dict(data or {})
    job = dict(job or {})
    source = _first_nonempty(current.get("provider_status_payload_source"), job.get("provider_status_payload_source"))
    shopaikey_status = _first_nonempty(
        current.get("shopaikey_data_status"),
        current.get("shopaikey_raw_status"),
        job.get("shopaikey_data_status"),
        job.get("shopaikey_raw_status"),
    )
    provider = _first_nonempty(
        current.get("selected_provider"),
        current.get("provider"),
        current.get("provider_pending_provider"),
        current.get("selected_provider_before_submit"),
        job.get("selected_provider"),
        job.get("provider"),
        job.get("provider_pending_provider"),
    )
    actual_running, actual_status, actual_source = _actual_provider_payload_is_running({**job, **current})
    attempt_not_start = _provider_attempts_indicate_not_start(current)
    stale_not_start_present = bool(
        attempt_not_start
        or current.get("provider_stalled_not_start")
        or _text_indicates_not_start(
            current.get("raw_provider_status"),
            current.get("provider_status_raw"),
            current.get("provider_error"),
            current.get("blocker"),
        )
    )
    if actual_running:
        current.update(
            {
                "actual_provider_payload_status": actual_status,
                "state_authority_source": actual_source,
                "provider_progress_authoritative": True,
                "stale_not_start_blocker_ignored": bool(stale_not_start_present),
                "not_start_decision_source": "ignored_actual_provider_in_progress",
                "raw_provider_status": actual_status,
                "provider_status_raw": actual_status,
                "provider_status": "running",
                "normalized_provider_status": "running",
                "provider_task_status": "running",
                "provider_status_for_progress": "running",
                "current_scene_status": "provider_running",
                "not_start_override_applied": False,
                "provider_stalled_not_start": False,
                "scene_not_start_elapsed": 0,
                "provider_error": "provider_in_progress",
                "blocker": "provider_in_progress",
                "fallback_allowed": False,
                "fallback_block_reason": "primary_provider_in_progress",
                "fallback_blocked_reason": "primary_provider_in_progress",
                "fallback_eligibility_reason": "primary_provider_in_progress",
                "key4u_submit_suppressed": True,
                "key4u_submit_suppressed_reason": "primary_provider_in_progress",
                "terminal_state": "final_rendering",
                "final_decision": "continue_polling",
                "continue_polling": True,
            }
        )
        return current
    source_not_start = bool(source.startswith("shopaikey.data.") and _text_indicates_not_start(shopaikey_status))
    if not (source_not_start or attempt_not_start):
        return current
    if provider and provider != "shopaikey_video" and source_not_start is False:
        return current
    if _provider_result_or_artifact_present(current):
        return current

    elapsed = _not_start_elapsed_seconds(current, job)
    threshold, threshold_source = _product_video_not_start_threshold()
    stalled = bool(elapsed >= threshold)
    existing_fallback_allowed = bool(current.get("fallback_allowed"))
    fallback_order = current.get("fallback_provider_order")
    if not isinstance(fallback_order, list):
        fallback_order = []
    if not fallback_order:
        fallback_order = [item for item in _provider_order(job) if item and item != (provider or "shopaikey_video")]
    fallback_candidate = _first_nonempty(
        current.get("fallback_provider"),
        current.get("fallback_provider_candidate"),
        current.get("next_provider_or_model_candidate"),
        *(fallback_order[:1]),
    )
    fallback_allowed = bool(existing_fallback_allowed or (stalled and fallback_candidate))
    fallback_block_reason = str(current.get("fallback_block_reason") or current.get("fallback_blocked_reason") or "")
    if not stalled:
        fallback_block_reason = "not_start_under_threshold"
    elif fallback_allowed:
        fallback_block_reason = ""
    elif fallback_block_reason in {"", "scene_not_stalled", "primary_provider_in_progress", "selected_provider_in_progress", "provider_in_progress", "not_start_under_threshold"}:
        fallback_block_reason = "no_fallback_provider"

    raw_before = _first_nonempty(
        current.get("raw_provider_status_before_source_fix"),
        current.get("raw_provider_status"),
        current.get("provider_status_raw"),
        "IN_PROGRESS" if source_not_start else "",
    )
    current.update(
        {
            "provider_status_payload_source": source or "shopaikey.data.status",
            "shopaikey_data_status": shopaikey_status or "NOT_START",
            "shopaikey_raw_status": _first_nonempty(current.get("shopaikey_raw_status"), shopaikey_status, "NOT_START"),
            "raw_provider_status_before_source_fix": raw_before,
            "raw_provider_status": "NOT_START",
            "provider_status_raw": "NOT_START",
            "provider_status": "not_start",
            "normalized_provider_status": "not_start",
            "provider_task_status": "not_start",
            "provider_status_for_progress": "not_start",
            "current_scene_status": PRODUCT_VIDEO_PROVIDER_STALLED_NOT_START if stalled and not fallback_allowed else "provider_not_start",
            "canonical_status_before_not_start_override": str(current.get("canonical_status_before_not_start_override") or "running"),
            "not_start_override_applied": True,
            "provider_error": "provider_not_start",
            "blocker": "provider_not_start",
            "scene_not_start_elapsed": elapsed,
            "provider_elapsed_seconds": max(_safe_int(current.get("provider_elapsed_seconds"), 0), elapsed),
            "provider_wait_elapsed_seconds": max(_safe_int(current.get("provider_wait_elapsed_seconds"), 0), elapsed),
            "not_start_threshold_seconds": threshold,
            "not_start_threshold_source": threshold_source,
            "stall_threshold": threshold,
            "provider_stalled_not_start": bool(stalled),
            "fallback_allowed": fallback_allowed,
            "fallback_block_reason": fallback_block_reason,
            "fallback_blocked_reason": fallback_block_reason,
            "fallback_eligibility_reason": "eligible" if fallback_allowed else fallback_block_reason,
            "key4u_submit_suppressed": not fallback_allowed,
            "key4u_submit_suppressed_reason": "" if fallback_allowed else fallback_block_reason,
        }
    )
    if stalled and not fallback_allowed:
        return _enforce_product_video_terminal_consistency(current, reason=PRODUCT_VIDEO_PROVIDER_STALLED_NOT_START)
    return current


def _pending_attempt_from_payload(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = dict(payload or {})
    candidates: list[dict[str, Any]] = []

    def _add(item: Any) -> None:
        if isinstance(item, dict) and item:
            candidates.append(dict(item))

    _add(data)
    for item in _as_list(data.get("provider_attempts")):
        _add(item)
    for item in _as_list(data.get("provider_pending_attempts")):
        _add(item)
    for item in _as_list(data.get("provider_events")):
        if isinstance(item, dict):
            _add(item)
            _add(item.get("debug"))

    for item in candidates:
        provider = _first_nonempty(
            item.get("provider"),
            item.get("selected_provider"),
            item.get("provider_pending_provider"),
            item.get("selected_provider_before_submit"),
        )
        task_id = _first_nonempty(
            item.get("provider_pending_task_id"),
            item.get("provider_task_id"),
            item.get("task_id"),
            *(_as_list(item.get("provider_task_ids"))[:1]),
        )
        video_id = _first_nonempty(
            item.get("provider_pending_video_id"),
            item.get("provider_video_id"),
            item.get("video_id"),
            *(_as_list(item.get("provider_video_ids"))[:1]),
        )
        accepted_task = bool(
            item.get("submit_accepted")
            or item.get("provider_task_id_saved")
            or item.get("task_id_present")
            or task_id
            or video_id
        )
        actual_status, actual_status_source, raw_status_before_fix = _actual_status_payload_value(item)
        status_text = " ".join(
            str(value or "").strip().lower()
            for value in (
                actual_status,
                item.get("shopaikey_raw_status"),
                item.get("shopaikey_data_status"),
                item.get("normalized_provider_status"),
                item.get("provider_status"),
                item.get("status"),
                item.get("provider_status_raw"),
                item.get("poll_raw_status"),
                item.get("nonterminal_provider_status"),
            )
            if str(value or "").strip()
        )
        blocker_text = " ".join(
            str(value or "").strip().lower()
            for value in (
                item.get("blocker"),
                item.get("provider_error"),
                item.get("provider_poll_blocker"),
                item.get("safe_error"),
                item.get("provider_error_message_safe"),
                item.get("exception_message_safe"),
            )
            if str(value or "").strip()
        )
        raw_not_start = _text_indicates_not_start(status_text)
        has_pending_status = any(marker in status_text for marker in PROVIDER_PENDING_STATUS_MARKERS)
        has_pending_blocker = any(marker in blocker_text for marker in PROVIDER_PENDING_BLOCKERS) or "in_progress" in blocker_text
        result_url_present = bool(item.get("provider_result_url_present") or item.get("result_url_present") or item.get("download_url_present"))
        download_called = bool(item.get("download_called") or item.get("download_status") == "downloaded")
        if accepted_task and not result_url_present and not download_called and (item.get("continue_polling") or has_pending_status or has_pending_blocker or raw_not_start):
            return {
                "provider": provider or "shopaikey_video",
                "task_id": task_id,
                "video_id": video_id,
                "status": "not_start" if raw_not_start else (status_text or "running"),
                "raw_status": actual_status,
                "status_source": actual_status_source,
                "raw_status_before_source_fix": raw_status_before_fix,
                "request_job_id": _first_nonempty(
                    item.get("provider_pending_request_job_id"),
                    item.get("provider_request_job_id"),
                    item.get("request_job_id"),
                ),
            }
    return {}


def _product_video_terminal_failure_should_dominate(data: dict[str, Any] | None = None) -> bool:
    data = dict(data or {})
    actual_running, _actual_status, _actual_source = _actual_provider_payload_is_running(data)
    if actual_running:
        return False
    terminal = str(data.get("terminal_state") or "").strip().lower()
    final_decision = str(data.get("final_decision") or "").strip().lower()
    status_text = " ".join(
        str(data.get(key) or "").strip().lower()
        for key in (
            "provider_error",
            "blocker",
            "provider_status",
            "normalized_provider_status",
            "provider_result_blocker",
        )
        if str(data.get(key) or "").strip()
    )
    stalled_without_fallback = bool(
        data.get("provider_stalled_not_start")
        and not data.get("fallback_allowed")
        and str(data.get("fallback_block_reason") or data.get("fallback_blocked_reason") or "").strip()
        not in {"", "scene_not_stalled"}
    )
    return bool(
        terminal in {"failed", "failed_no_charge", "failed_refunded", "needs_admin_review"}
        or final_decision == "failed_no_charge"
        or stalled_without_fallback
        or PRODUCT_VIDEO_PROVIDER_STALLED_NOT_START in status_text
        and not data.get("fallback_allowed")
    )


def _enforce_product_video_terminal_consistency(data: dict[str, Any] | None = None, *, reason: str = "") -> dict[str, Any]:
    current = dict(data or {})
    failure_reason = str(
        reason
        or current.get("provider_error")
        or current.get("blocker")
        or current.get("fallback_block_reason")
        or current.get("fallback_blocked_reason")
        or "failed_no_charge"
    ).strip()
    if not failure_reason or failure_reason in {"provider_in_progress", "provider_pending"}:
        failure_reason = "failed_no_charge"
    current.update(
        {
            "ok": False,
            "status": "failed",
            "continue_polling": False,
            "primary_provider_continue_polling": False,
            "primary_provider_task_alive": False,
            "provider_pending_deferred": False,
            "next_poll_scheduled": False,
            "terminal_state": "failed_no_charge",
            "final_decision": "failed_no_charge",
            "provider_status": "failed",
            "normalized_provider_status": "failed",
            "provider_task_status": "failed",
            "final_status_after_reconcile": "failed",
            "source_of_truth": str(current.get("source_of_truth") or "terminal_failed_no_charge"),
            "status_source_priority_used": "terminal_failed_no_charge",
            "provider_state_source": str(current.get("provider_state_source") or "terminal_failed_no_charge"),
            "no_charge": True,
        }
    )
    current["provider_error"] = failure_reason
    current["blocker"] = failure_reason
    if str(current.get("charge_gate_blocker") or "").strip() in {"", "provider_in_progress_no_charge"}:
        current["charge_gate_blocker"] = failure_reason
    return current


def _apply_pending_provider_dominance(data: dict[str, Any], *, job: dict | None = None) -> dict[str, Any]:
    terminal_probe = {**dict(job or {}), **dict(data or {})}
    if _product_video_terminal_failure_should_dominate(terminal_probe):
        return _enforce_product_video_terminal_consistency({**dict(data or {}), **dict(job or {})})
    pending = _pending_attempt_from_payload(data)
    if not pending:
        return _enforce_shopaikey_not_start_final_invariant(data, job=job)
    provider = str(pending.get("provider") or data.get("selected_provider") or "shopaikey_video")
    task_id = str(pending.get("task_id") or "")
    video_id = str(pending.get("video_id") or "")
    wait_max = max(60, _env_int("PRODUCT_VIDEO_PROVIDER_MAX_WAIT_SECONDS", DEFAULT_PRODUCT_VIDEO_PROVIDER_MAX_WAIT_SECONDS))
    started_at = str(data.get("provider_started_at") or (job or {}).get("provider_started_at") or "").strip()
    started_epoch = data.get("provider_started_at_epoch") or (job or {}).get("provider_started_at_epoch") or ""
    actual_running, actual_status, actual_source = _actual_provider_payload_is_running(data)
    pending_raw_not_start = _text_indicates_not_start(
        pending.get("raw_status"),
        pending.get("status"),
        data.get("shopaikey_raw_status"),
        data.get("shopaikey_data_status"),
        data.get("provider_status_raw"),
        data.get("raw_provider_status"),
        data.get("nonterminal_provider_status"),
        data.get("normalized_provider_status"),
        data.get("provider_status"),
    )
    if actual_running:
        pending_raw_not_start = False
    raw_provider_status_before_fix = _first_nonempty(pending.get("raw_status_before_source_fix"), data.get("raw_provider_status_before_source_fix"))
    actual_raw_provider_status = (
        _first_nonempty(pending.get("raw_status"), data.get("shopaikey_raw_status"), data.get("shopaikey_data_status"), pending.get("status"))
        if pending_raw_not_start
        else _first_nonempty(actual_status if actual_running else "", data.get("raw_provider_status"), data.get("provider_status_raw"), pending.get("raw_status"), pending.get("status"))
    )
    status_payload_source = _first_nonempty(actual_source if actual_running else "", pending.get("status_source"), data.get("provider_status_payload_source"))
    provider_status_value = "not_start" if pending_raw_not_start else "running"
    provider_error_value = "provider_not_start" if pending_raw_not_start else "provider_in_progress"
    default_fallback_blocked = "not_start_under_threshold" if pending_raw_not_start else ("primary_provider_in_progress" if not data.get("fallback_used") else "")
    existing_fallback_blocked = str(data.get("fallback_blocked_reason") or data.get("fallback_block_reason") or "")
    if pending_raw_not_start and existing_fallback_blocked in {
        "",
        "primary_provider_in_progress",
        "selected_provider_in_progress",
        "provider_in_progress",
    }:
        existing_fallback_blocked = default_fallback_blocked
    if actual_running and existing_fallback_blocked in {
        "",
        "not_start_under_threshold",
        "scene_not_stalled",
        "provider_not_start",
        PRODUCT_VIDEO_PROVIDER_STALLED_NOT_START,
    }:
        existing_fallback_blocked = "primary_provider_in_progress"
    not_start_elapsed = max(
        _safe_int(data.get("scene_not_start_elapsed"), 0),
        _safe_int(data.get("provider_elapsed_seconds"), 0),
        _safe_int(data.get("provider_wait_elapsed_seconds"), 0),
        _safe_int(data.get("elapsed_wall_clock_seconds"), 0),
        _safe_int(data.get("previous_elapsed_seconds"), 0),
        _safe_int((job or {}).get("provider_elapsed_seconds"), 0),
        _safe_int((job or {}).get("provider_wait_elapsed_seconds"), 0),
    )
    data.update(
        {
            "ok": False,
            "continue_polling": True,
            "provider_pending_deferred": True,
            "provider_error": provider_error_value,
            "blocker": provider_error_value,
            "provider_status": provider_status_value,
            "normalized_provider_status": provider_status_value,
            "raw_provider_status": actual_raw_provider_status,
            "provider_status_raw": actual_raw_provider_status,
            "provider_status_payload_source": status_payload_source,
            "raw_provider_status_before_source_fix": raw_provider_status_before_fix,
            "canonical_status_before_not_start_override": str(data.get("canonical_status_before_not_start_override") or ("running" if pending_raw_not_start else provider_status_value)),
            "not_start_override_applied": bool(False if actual_running else (pending_raw_not_start or data.get("not_start_override_applied"))),
            "actual_provider_payload_status": actual_status if actual_running else str(data.get("actual_provider_payload_status") or ""),
            "state_authority_source": actual_source if actual_running else str(data.get("state_authority_source") or status_payload_source or ""),
            "provider_progress_authoritative": bool(actual_running or data.get("provider_progress_authoritative")),
            "stale_not_start_blocker_ignored": bool(
                actual_running
                and _text_indicates_not_start(
                    pending.get("raw_status"),
                    pending.get("status"),
                    data.get("raw_provider_status"),
                    data.get("provider_status_raw"),
                    data.get("provider_error"),
                    data.get("blocker"),
                )
            ),
            "not_start_decision_source": "ignored_actual_provider_in_progress" if actual_running else str(data.get("not_start_decision_source") or ("actual_provider_payload" if pending_raw_not_start else "")),
            "nonterminal_provider_status": str(pending.get("status") or "running"),
            "selected_provider": provider,
            "initial_selected_provider": str(data.get("initial_selected_provider") or provider),
            "selected_provider_before_submit": provider,
            "selected_provider_after_fallback": "",
            "provider_attempted": True,
            "provider_router_called": True,
            "provider_submit_called": True,
            "submit_accepted": True,
            "provider_task_id_saved": bool(task_id or video_id or data.get("provider_task_id_saved")),
            "provider_poll_called": True,
            "poll_allowed": True,
            "provider_result_url_present": False,
            "result_url_present": False,
            "fallback_used": False,
            "fallback_reason": "",
            "provider_fallback_attempted": False,
            "provider_fallback_reason": "",
            "fallback_allowed": bool(data.get("fallback_allowed") if data.get("fallback_allowed") is not None else False),
            "fallback_blocked_reason": existing_fallback_blocked or default_fallback_blocked,
            "fallback_block_reason": existing_fallback_blocked or default_fallback_blocked,
            "primary_provider_continue_polling": not bool(data.get("fallback_used")),
            "primary_provider_task_alive": not bool(data.get("fallback_used")),
            "primary_provider_task_id_present": bool(task_id or video_id or data.get("provider_task_ids") or data.get("provider_video_ids")),
            "key4u_submit_suppressed": True,
            "key4u_submit_suppressed_reason": (
                "primary_provider_in_progress"
                if actual_running
                else (
                    default_fallback_blocked
                    if pending_raw_not_start
                    and str(data.get("key4u_submit_suppressed_reason") or "")
                    in {"", "primary_provider_in_progress", "selected_provider_in_progress", "provider_in_progress"}
                    else str(data.get("key4u_submit_suppressed_reason") or default_fallback_blocked)
                )
            ),
            "next_poll_scheduled": True,
            "provider_started_at": started_at,
            "provider_started_at_epoch": started_epoch,
            "provider_started_at_source": str(data.get("provider_started_at_source") or ("payload" if started_at or started_epoch else "")),
            "provider_wait_elapsed_seconds": int(data.get("provider_wait_elapsed_seconds") or 0),
            "provider_elapsed_seconds": int(data.get("provider_elapsed_seconds") or data.get("provider_wait_elapsed_seconds") or 0),
            "provider_wait_max_seconds": int(data.get("provider_wait_max_seconds") or wait_max),
            "provider_progress_raw": data.get("provider_progress_raw", ""),
            "provider_progress_normalized": int(data.get("provider_progress_normalized") or 0),
            "provider_progress_raw_number": data.get("provider_progress_raw_number", ""),
            "provider_progress_trusted": bool(data.get("provider_progress_trusted")),
            "provider_progress_cap_reason": str(data.get("provider_progress_cap_reason") or ""),
            "provider_progress_cap_applied": bool(data.get("provider_progress_cap_applied")),
            "provider_progress_effective": int(data.get("provider_progress_effective") or 0),
            "provider_progress_estimated": bool(data.get("provider_progress_estimated")),
            "provider_progress_percent": int(data.get("provider_progress_percent") or 20),
            "render_video_progress_percent": int(data.get("render_video_progress_percent") or data.get("provider_render_progress_percent") or 0),
            "provider_render_progress_percent": int(data.get("provider_render_progress_percent") or data.get("render_video_progress_percent") or 0),
            "render_video_progress_percent_public": data.get("render_video_progress_percent_public", ""),
            "provider_progress_public_suppressed": bool(data.get("provider_progress_public_suppressed")),
            "render_progress_public_mode": str(data.get("render_progress_public_mode") or ""),
            "fake_progress_prevented": bool(data.get("fake_progress_prevented")),
            "fake_progress_prevention_reason": str(data.get("fake_progress_prevention_reason") or ""),
            "percent_conservative_due_to_untrusted_provider": bool(data.get("percent_conservative_due_to_untrusted_provider")),
            "render_progress_source": str(data.get("render_progress_source") or ""),
            "render_progress_raw_provider": data.get("render_progress_raw_provider", data.get("provider_progress_raw", "")),
            "render_progress_estimated": bool(data.get("render_progress_estimated")),
            "render_progress_cap_applied": bool(data.get("render_progress_cap_applied")),
            "render_progress_result_url_present": bool(data.get("render_progress_result_url_present")),
            "render_progress_monotonic_applied": bool(data.get("render_progress_monotonic_applied")),
            "overall_progress_from_render": int(data.get("overall_progress_from_render") or 20),
            "provider_status_for_progress": provider_status_value,
            "elapsed_wall_clock_seconds": int(data.get("elapsed_wall_clock_seconds") or data.get("provider_elapsed_seconds") or 0),
            "previous_elapsed_seconds": int(data.get("previous_elapsed_seconds") or 0),
            "elapsed_monotonic_applied": bool(data.get("elapsed_monotonic_applied")),
            "scene_not_start_elapsed": not_start_elapsed if pending_raw_not_start else _safe_int(data.get("scene_not_start_elapsed"), 0),
            "current_scene_status": "provider_not_start" if pending_raw_not_start else str(data.get("current_scene_status") or "provider_running"),
            "panel_refresh_interval_seconds": int(data.get("panel_refresh_interval_seconds") or 25),
            "provider_poll_count": int(data.get("provider_poll_count") or 0),
            "provider_poll_count_source": str(data.get("provider_poll_count_source") or ""),
            "provider_last_poll_at": str(data.get("provider_last_poll_at") or ""),
            "terminal_state": "final_rendering",
            "progress_message": provider_error_value,
            "public_message": "TOAN AAS đang dựng video. Anh/chị vui lòng kiểm tra lại sau.",
            "no_charge": True,
        }
    )
    if data.get("fallback_used") or str(data.get("submit_source") or data.get("provider_submit_source") or "") in {
        PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_FALLBACK_ONCE,
        PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_SCENE_FALLBACK_ONCE,
    }:
        data["fallback_submit_source"] = PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_SCENE_FALLBACK_ONCE
        data["fallback_used"] = True
        data["provider_fallback_attempted"] = True
        data["provider_fallback_reason"] = str(data.get("provider_fallback_reason") or data.get("fallback_reason") or PRODUCT_VIDEO_PROVIDER_STALLED_NOT_START)
        data["fallback_reason"] = str(data.get("fallback_reason") or PRODUCT_VIDEO_PROVIDER_STALLED_NOT_START)
        data["fallback_blocked_reason"] = ""
        data["primary_provider_continue_polling"] = False
        data["primary_provider_task_alive"] = False
    if task_id:
        data["provider_pending_task_id"] = task_id
        ids = [str(item) for item in _as_list(data.get("provider_task_ids")) if str(item or "").strip()]
        data["provider_task_ids"] = ids or [task_id]
    if video_id:
        data["provider_pending_video_id"] = video_id
        ids = [str(item) for item in _as_list(data.get("provider_video_ids")) if str(item or "").strip()]
        data["provider_video_ids"] = ids or [video_id]
    request_job_id = str(pending.get("request_job_id") or "")
    if request_job_id:
        data["provider_pending_request_job_id"] = request_job_id
        data["provider_request_job_id"] = request_job_id
        data["request_job_id"] = request_job_id
    data["provider_pending_provider"] = provider
    return _enforce_shopaikey_not_start_final_invariant(data, job=job)


def _env_flag(name: str, default: str = "0") -> bool:
    return str(os.environ.get(name, default) or default).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.environ.get(name, str(default)) or str(default)).strip())
    except Exception:
        return int(default)


def _product_video_not_start_threshold() -> tuple[int, str]:
    for name in ("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", "PRODUCT_VIDEO_NOT_START_GRACE_SECONDS"):
        raw = os.environ.get(name)
        if raw not in (None, ""):
            try:
                return max(1, int(str(raw).strip())), f"env:{name}"
            except Exception:
                continue
    return DEFAULT_PRODUCT_VIDEO_FIRST_SCENE_NOT_START_GRACE_SECONDS, "default:product_video_not_start_grace"


def _json_loads(value: Any, fallback: Any = None) -> Any:
    if value in (None, ""):
        return {} if fallback is None else fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return {} if fallback is None else fallback


def _safe_text(value: Any, limit: int = 4000) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text[:limit]


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def is_local_placeholder_renderer(renderer: Any) -> bool:
    value = str(renderer or "").strip().lower()
    return any(marker in value for marker in ("local_scene_composer", "local_placeholder", "text_slide", "color_slide", "placeholder"))


def classify_visual_result(result: dict | None = None) -> str:
    payload = dict(result or {})
    explicit = str(payload.get("visual_classification") or payload.get("final_classification") or "").strip()
    if explicit in {FINAL_AI_VIDEO, PARTIAL_SIMPLE_VIDEO, FAILED_NO_REAL_VISUAL}:
        return explicit
    if not payload.get("ok"):
        return FAILED_NO_REAL_VISUAL
    renderer = str(payload.get("renderer") or payload.get("connector_renderer") or "").strip().lower()
    if is_local_placeholder_renderer(renderer) or payload.get("placeholder_detected") or payload.get("placeholder_visual"):
        return PARTIAL_SIMPLE_VIDEO
    if payload.get("raw_prompt_burned_into_frame"):
        return FAILED_NO_REAL_VISUAL
    if renderer in {LOCAL_IMAGE_SEQUENCE_RENDERER, LOCAL_SCENE_CARD_RENDERER} or payload.get("visual_source") in {VISUAL_SOURCE_LOCAL_IMAGE_SEQUENCE, VISUAL_SOURCE_LOCAL_SCENE_CARD}:
        return FINAL_AI_VIDEO
    if renderer in {"real_provider", PROVIDER_SCENE_RENDERER, "provider_video"} or payload.get("provider_attempted"):
        return FINAL_AI_VIDEO
    return FAILED_NO_REAL_VISUAL


def _contains_raw_prompt_marker(text: Any) -> bool:
    value = _safe_text(text, 3000).lower()
    if not value:
        return False
    return any(marker in value for marker in RAW_PROMPT_FRAME_MARKERS)


def _provider_order(job: dict | None = None) -> list[str]:
    job = dict(job or {})
    asset_pack = _json_loads(job.get("asset_pack"), {})
    if not asset_pack and isinstance(job.get("project"), dict):
        asset_pack = _json_loads((job.get("project") or {}).get("asset_pack_json"), {})
    raw = (
        job.get("provider_order")
        or asset_pack.get("provider_order")
        or os.environ.get("VIDEO_PROVIDER_CHAIN")
        or os.environ.get("VIDEO_PROVIDER_ORDER")
        or "shopaikey_video,key4u_video,toanaas_video,veo,kling,generic_http"
    )
    if isinstance(raw, (list, tuple)):
        values = raw
    else:
        values = re.split(r"[,|>\s]+", str(raw or ""))
    result = []
    for item in values:
        provider = str(item or "").strip().lower()
        if provider in {"shopai", "shopaikey", "shopaikey_video"}:
            provider = "shopaikey_video"
        elif provider in {"key4u", "k4u", "key4u_video"}:
            provider = "key4u_video"
        elif provider in {"toanaas", "toanaas_video"}:
            provider = "toanaas_video"
        elif provider in {"veo", "video_veo"}:
            provider = "veo"
        elif provider in {"kling", "video_kling"}:
            provider = "kling"
        elif provider in {"generic", "generic_http", "gommo", "79ai", "gommo79ai", "gommo_79ai", "go-mmo"}:
            provider = "generic_http"
        else:
            continue
        if provider not in result:
            result.append(provider)
    return result or ["shopaikey_video", "key4u_video", "toanaas_video", "veo", "kling", "generic_http"]


def _durable_product_video_route_forbids(job: dict | None, policy_key: str) -> bool:
    payload = dict(job or {})
    decision = payload.get("product_video_route_decision")
    marker = bool(
        payload.get("product_video_durable_public_seam")
        or isinstance(decision, dict)
    )
    if not marker:
        return False
    return bool(
        payload.get(policy_key) is False
        or (isinstance(decision, dict) and decision.get(policy_key) is False)
    )


def real_video_provider_readiness(job: dict | None = None, environ: dict[str, str] | None = None) -> dict:
    del job
    status = provider_status_payload(environ)
    providers = list(status.get("providers") or [])
    ordered_ready = list(status.get("ready_provider_order") or [])
    return {
        "ok": bool(ordered_ready),
        "provider_order": list(status.get("provider_chain") or []),
        "configured_providers": ordered_ready,
        "ready_provider_order": ordered_ready,
        "first_ready_provider": status.get("first_ready_provider") or (ordered_ready[0] if ordered_ready else ""),
        "enabled_count": int(status.get("enabled_count") or 0),
        "configured_count": int(status.get("configured_count") or 0),
        "enabled_providers": list(status.get("enabled_providers") or []),
        "missing_env": dict(status.get("missing_env") or {}),
        "providers": providers,
    }


def _provider_candidates_for_capability(readiness: dict | None = None, required_capability: str = "") -> list[str]:
    payload = dict(readiness or {})
    allowed = set(capability_options(required_capability))
    candidates: list[str] = []
    for item in payload.get("providers") or []:
        if not isinstance(item, dict):
            continue
        if not item.get("configured"):
            continue
        supported = set(normalize_capability_values(item.get("capabilities") or []))
        if allowed and not (supported & allowed):
            continue
        provider_name = str(item.get("provider") or "").strip()
        if provider_name and provider_name not in candidates:
            candidates.append(provider_name)
    if candidates:
        return candidates
    ready = [str(item or "").strip() for item in (payload.get("ready_provider_order") or []) if str(item or "").strip()]
    return ready


def _route_requires_provider(
    product_type: str,
    required_capability: str,
    fallback_capability: str,
    *,
    provider_ready: bool = False,
    engine_adapter: str = "",
    orchestration_mode: str = "",
    explicit_local_renderer: bool = False,
) -> bool:
    route_contract = product_video_route_contract(
        product_type,
        engine_adapter,
        orchestration_mode,
        explicit_local_renderer=explicit_local_renderer,
    )
    if route_contract.get("route_requires_provider") or route_contract.get("local_renderer_selected"):
        return bool(route_contract.get("route_requires_provider"))
    product = video_final_output.normalize_video_product_type(product_type)
    capability = str(required_capability or "").strip()
    fallback = str(fallback_capability or "").strip()
    adapter = str(engine_adapter or "").strip().lower().replace("-", "_")
    orchestration = str(orchestration_mode or "").strip().lower().replace("-", "_")
    if (
        not explicit_local_renderer
        and adapter in {"text_to_video", "text_to_video_or_scene_engine", "text_to_video_or_scene_video"}
        and orchestration in {"per_scene_8s", "scene_orchestrator", "per_scene"}
    ):
        return True
    if product in PROVIDER_REQUIRED_PRODUCT_TYPES:
        return True
    if capability not in PROVIDER_REQUIRED_CAPABILITIES:
        return False
    if fallback in PROVIDER_CLEAN_FAIL_FALLBACKS:
        return True
    if provider_ready and product in {
        "video_ai_image",
        "video_ai_video_reference",
        "self_shot_scene_change",
        "self_shot_cinematic_transform",
    }:
        return True
    return False


def _addon_plan(job: dict | None = None) -> dict:
    job = dict(job or {})
    candidates = [
        job.get("addon_plan"),
        job.get("addon_plan_json"),
        (job.get("project") or {}).get("addon_plan_json") if isinstance(job.get("project"), dict) else "",
    ]
    for candidate in candidates:
        value = _json_loads(candidate, {})
        if isinstance(value, dict) and value:
            return value
    return {}


def product_video_materialize_addons(
    job: dict | None,
    *,
    workspace: str,
    scene_count: int,
    scene_duration: float,
) -> dict:
    """Resolve the strict worker Add-on contract before provider readiness."""

    logo_material = product_video_logo_material(job)
    return product_video_addon_materialization.materialize_product_video_addons(
        job,
        workspace=workspace,
        scene_count=scene_count,
        scene_duration=scene_duration,
        logo_fallback_path=str(logo_material.get("logo_path") or ""),
        ffmpeg_path=_ffmpeg_binary(),
    )


def original_prompt_from_job(job: dict | None = None) -> str:
    job = dict(job or {})
    asset_pack = _json_loads(job.get("asset_pack"), {})
    if not asset_pack and isinstance(job.get("project"), dict):
        asset_pack = _json_loads((job.get("project") or {}).get("asset_pack_json"), {})
    candidates = [
        job.get("original_user_prompt"),
        job.get("cleaned_user_prompt"),
        asset_pack.get("original_user_prompt") if isinstance(asset_pack, dict) else "",
        asset_pack.get("cleaned_user_prompt") if isinstance(asset_pack, dict) else "",
        job.get("prompt_text"),
        (job.get("project") or {}).get("prompt_text") if isinstance(job.get("project"), dict) else "",
        job.get("topic"),
        (job.get("project") or {}).get("topic") if isinstance(job.get("project"), dict) else "",
    ]
    for candidate in candidates:
        text = _safe_text(candidate, 4000)
        if text and "No render/provider call before" not in text:
            return text
    return "short product video"


def _scene_cards(job: dict | None = None) -> list[dict]:
    job = dict(job or {})
    cards = job.get("scene_cards")
    if not cards and isinstance(job.get("project"), dict):
        cards = _json_loads((job.get("project") or {}).get("scene_cards_json"), [])
    if isinstance(cards, list):
        return [dict(item or {}) for item in cards if isinstance(item, dict)]
    return []


def _has_user_facing_subtitle_text(job: dict | None = None) -> bool:
    addon = _addon_plan(job)
    if _safe_text(addon.get("narration_text") or addon.get("script_text") or addon.get("subtitle_text"), 1000):
        return True
    for card in _scene_cards(job):
        if _safe_text(card.get("narration_line") or card.get("script_text") or card.get("subtitle_line"), 1000):
            return True
    return False


def _subtitle_raw_prompt_burn_detected(job: dict | None, result: dict | None) -> bool:
    subtitle_path = str((result or {}).get("subtitle_path") or "").strip()
    if not subtitle_path or not os.path.isfile(subtitle_path):
        return False
    try:
        with open(subtitle_path, "r", encoding="utf-8", errors="ignore") as handle:
            content = handle.read(6000)
    except OSError:
        return False
    if _contains_raw_prompt_marker(content):
        return True
    return False


def _scene_count(job: dict | None = None) -> int:
    job = dict(job or {})
    value = job.get("scene_count")
    if not value and isinstance(job.get("project"), dict):
        value = (job.get("project") or {}).get("scene_count")
    return max(1, min(20, _safe_int(value, 3)))


def _job_base_id(job: dict | None = None) -> str:
    job = dict(job or {})
    return str(job.get("id") or job.get("job_id") or "video_job").strip() or "video_job"


def product_video_scene_request_id(job: dict | None = None, scene_index: int = 1) -> str:
    return f"{_job_base_id(job)}-{max(1, _safe_int(scene_index, 1))}"


def _task_id_masked(value: Any, visible: int = 4) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= visible * 2:
        return "*" * len(text)
    return f"{text[:visible]}...{text[-visible:]}"


def _product_video_pending_request_is_scene(job: dict | None = None) -> bool:
    request_job_id = str((job or {}).get("provider_pending_request_job_id") or "").strip()
    if not request_job_id:
        return False
    return bool(re.search(r"-\d+$", request_job_id))


def product_video_orchestration_mode(job: dict | None = None) -> str:
    """Return the Product Video provider orchestration mode.

    Public jobs default to the R14B raw delivery path. The R16 per-scene
    orchestrator remains available for explicitly marked jobs and live jobs
    that already carry scene-task state.
    """
    job = dict(job or {})
    invoice = _invoice_payload(job)
    asset_pack = _asset_pack_payload(job)
    project = job.get("project") if isinstance(job.get("project"), dict) else {}
    explicit = str(
        job.get("orchestration_mode")
        or job.get("provider_orchestration_mode")
        or asset_pack.get("orchestration_mode")
        or invoice.get("orchestration_mode")
        or (project or {}).get("orchestration_mode")
        or ""
    ).strip().lower()
    aliases = {
        "per_scene": PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE_8S,
        "scene": PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE_8S,
        "scene_orchestrator": PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE_8S,
        "per_scene_8s": PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE_8S,
        "multi_clip_concat": PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE_8S,
        "historical_multi_clip_concat": PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE_8S,
        "single_task": PRODUCT_VIDEO_ORCHESTRATION_MODE_LEGACY_SINGLE_TASK,
        "legacy": PRODUCT_VIDEO_ORCHESTRATION_MODE_LEGACY_SINGLE_TASK,
        "legacy_single_task": PRODUCT_VIDEO_ORCHESTRATION_MODE_LEGACY_SINGLE_TASK,
        "single_task_legacy": PRODUCT_VIDEO_ORCHESTRATION_MODE_LEGACY_SINGLE_TASK,
    }
    if explicit in aliases:
        return aliases[explicit]
    for key in ("scene_tasks", "provider_scene_tasks", "product_video_scene_tasks"):
        value = job.get(key)
        if isinstance(value, str):
            value = _json_loads(value, [])
        if isinstance(value, list) and any(isinstance(item, dict) for item in value):
            return PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE_8S
    task_present = bool(
        job.get("provider_pending_task_id")
        or job.get("provider_pending_video_id")
        or job.get("provider_task_ids")
        or job.get("provider_video_ids")
    )
    if task_present and not _product_video_pending_request_is_scene(job):
        return PRODUCT_VIDEO_ORCHESTRATION_MODE_LEGACY_SINGLE_TASK
    if _product_video_pending_request_is_scene(job):
        return PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE_8S
    if (
        str(job.get("source") or "").strip() == "product_video"
        or bool(job.get("product_video"))
    ) and _scene_count(job) > 1:
        return PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE_8S
    return PRODUCT_VIDEO_ORCHESTRATION_MODE_LEGACY_SINGLE_TASK


def product_video_scene_duration_seconds(job: dict | None = None) -> int:
    job = dict(job or {})
    invoice = _invoice_payload(job)
    asset_pack = _asset_pack_payload(job)
    product_type = str(
        job.get("product_type")
        or job.get("job_type")
        or invoice.get("product_type")
        or invoice.get("job_type")
        or ""
    ).strip()
    if product_type == "self_shot_cinematic_transform":
        segment = dict(asset_pack.get("source_segment") or {})
        segment_seconds = _safe_int((segment.get("duration_ms") or 0) / 1000, 0)
        direct_seconds = _safe_int(
            asset_pack.get("duration_seconds")
            or job.get("expected_duration_seconds")
            or job.get("duration_seconds")
            or invoice.get("duration_seconds"),
            0,
        )
        return max(1, segment_seconds or direct_seconds or PRODUCT_VIDEO_SCENE_SECONDS)
    scene_seconds = _safe_int(
        job.get("scene_duration_seconds")
        or job.get("scene_seconds")
        or invoice.get("scene_duration_seconds")
        or invoice.get("scene_seconds"),
        PRODUCT_VIDEO_SCENE_SECONDS,
    )
    scene_duration_limit = (
        PRODUCT_VIDEO_MAX_UIFLOW3_SCENE_SECONDS
        if str(
            job.get("uiflow3_handoff_sha256")
            or asset_pack.get("uiflow3_handoff_sha256")
            or invoice.get("uiflow3_handoff_sha256")
            or ""
        ).strip()
        else PRODUCT_VIDEO_SCENE_SECONDS
    )
    return max(1, min(scene_duration_limit, scene_seconds))


def _existing_scene_tasks(job: dict | None = None) -> list[dict[str, Any]]:
    job = dict(job or {})
    result: list[dict[str, Any]] = []
    for key in ("scene_tasks", "provider_scene_tasks", "product_video_scene_tasks"):
        value = job.get(key)
        if isinstance(value, str):
            value = _json_loads(value, [])
        if isinstance(value, list):
            result.extend(dict(item or {}) for item in value if isinstance(item, dict))
    return result


def _scene_task_has_dispatch_attempt(item: dict | None = None) -> bool:
    task = dict(item or {})
    return bool(
        _scene_task_has_provider_id(task)
        or task.get("scene_dispatch_attempted")
        or task.get("dispatch_attempted")
        or task.get("provider_submit_called")
        or task.get("provider_http_request_sent")
        or _safe_int(
            task.get("submit_http_status")
            or task.get("provider_submit_http_status")
            or task.get("provider_http_status"),
            0,
        )
        > 0
    )


def _scene_task_index(item: dict | None = None, default: int = 1) -> int:
    item = dict(item or {})
    return max(1, _safe_int(item.get("scene_index") or item.get("scene_id") or item.get("index"), default))


def product_video_scene_task_for_index(job: dict | None = None, scene_index: int = 1) -> dict[str, Any]:
    wanted = max(1, _safe_int(scene_index, 1))
    for item in _existing_scene_tasks(job):
        if _scene_task_index(item) == wanted and (
            str(
                item.get("active_task_id")
                or item.get("provider_task_id")
                or item.get("task_id")
                or item.get("provider_video_id")
                or item.get("video_id")
                or item.get("winning_task_id")
                or item.get("scene_winner_task")
                or item.get("canonical_task_selected")
                or ""
            ).strip()
        ):
            return dict(item)
    return {}


def _scene_task_status(item: dict | None = None) -> str:
    item = dict(item or {})
    actual_status, _, _ = _actual_status_payload_value(item)
    raw = str(
        actual_status
        or item.get("status")
        or item.get("normalized_provider_status")
        or item.get("provider_status")
        or item.get("provider_status_raw")
        or item.get("nonterminal_provider_status")
        or item.get("blocker")
        or ""
    ).strip()
    return _normalize_scene_task_status(raw, item)


def _scene_task_has_raw_not_start(item: dict | None = None) -> bool:
    item = dict(item or {})
    actual_running, _actual_status, _actual_source = _actual_provider_payload_is_running(item)
    if actual_running:
        return False
    for key in (
        "shopaikey_raw_status",
        "shopaikey_data_status",
        "raw_provider_status",
        "provider_status_raw",
        "nonterminal_provider_status",
        "normalized_provider_status",
        "provider_status",
        "status",
        "blocker",
    ):
        value = item.get(key)
        if value in (None, ""):
            continue
        text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        if text in {"not_start", "not_started", "provider_not_start", "media_generation_status_not_start"}:
            return True
        if _normalize_scene_task_status(text, item) == "provider_not_start":
            return True
    return False


def _normalize_scene_task_status(status: Any = "", item: dict | None = None) -> str:
    text = str(status or "").strip().lower().replace("-", "_")
    item = dict(item or {})
    has_task = bool(
        str(
            item.get("provider_task_id")
            or item.get("task_id")
            or item.get("provider_video_id")
            or item.get("video_id")
            or item.get("active_task_id")
            or item.get("winning_task_id")
            or item.get("scene_winner_task")
            or item.get("canonical_task_selected")
            or item.get("provider_task_id_masked")
            or item.get("task_id_masked")
            or item.get("provider_video_id_masked")
            or ""
        ).strip()
    )
    has_result = bool(
        has_task
        and (item.get("result_url_valid") or item.get("download_url_present") or item.get("provider_result_url_present"))
    )
    has_valid_clip = bool(
        item.get("clip_valid")
        or item.get("validation_passed")
        or item.get("output_validated")
        or _safe_int(item.get("clip_bytes") or item.get("artifact_size") or item.get("output_bytes"), 0) > 0
        or text in {"downloaded", "validated", "clip_downloaded", "scene_clip_validated"}
    )
    if has_valid_clip:
        return "clip_downloaded"
    if has_result and text in {"success", "completed", "succeeded", "done", "result_pending_validation"}:
        return "result_pending_validation"
    if text in {"not_start", "not_started", "provider_not_start", "media_generation_status_not_start"}:
        return "provider_not_start"
    if text in {"provider_stalled_not_start", PRODUCT_VIDEO_PROVIDER_STALLED_NOT_START}:
        return PRODUCT_VIDEO_PROVIDER_STALLED_NOT_START
    if text in {
        "running",
        "processing",
        "in_progress",
        "pending",
        "queued",
        "provider_running",
        "provider_in_progress",
        "provider_pending",
        "media_generation_status_pending",
        "media_generation_status_in_progress",
    }:
        return "provider_running" if has_task else "pending_submit"
    if text in {"failed", "error", "failure", "provider_failed", "provider_submit_failed"}:
        return "failed"
    return "provider_running" if has_task else "pending_submit"


def _scene_task_has_provider_id(item: dict | None = None) -> bool:
    item = dict(item or {})
    return bool(
        str(
            item.get("provider_task_id")
            or item.get("task_id")
            or item.get("provider_video_id")
            or item.get("video_id")
            or item.get("active_task_id")
            or item.get("winning_task_id")
            or item.get("scene_winner_task")
            or item.get("canonical_task_selected")
            or item.get("provider_task_id_masked")
            or item.get("task_id_masked")
            or item.get("provider_video_id_masked")
            or ""
        ).strip()
    )


def _scene_task_progress_number(item: dict | None = None) -> float:
    item = dict(item or {})
    for key in (
        "provider_progress_normalized",
        "provider_progress_percent",
        "provider_progress_raw",
        "shopaikey_data_progress_raw",
        "data_progress_raw",
        "progress",
    ):
        value = item.get(key)
        if value in (None, ""):
            continue
        try:
            text = str(value).strip().rstrip("%")
            return float(text)
        except Exception:
            continue
    return 0.0


def _scene_task_elapsed_seconds(item: dict | None = None, job: dict | None = None) -> int:
    item = dict(item or {})
    job = dict(job or {})
    values: list[int] = []
    for key in (
        "scene_not_start_elapsed",
        "provider_wait_elapsed_seconds",
        "provider_elapsed_seconds",
        "elapsed_wall_clock_seconds",
        "previous_elapsed_seconds",
    ):
        value = _safe_int(item.get(key), 0)
        if value > 0:
            values.append(value)
    for key in (
        "scene_not_start_elapsed",
        "provider_wait_elapsed_seconds",
        "provider_elapsed_seconds",
        "elapsed_wall_clock_seconds",
        "previous_elapsed_seconds",
    ):
        value = _safe_int(job.get(key), 0)
        if value > 0:
            values.append(value)
    now = time.time()
    for key in (
        "scene_submitted_at_epoch",
        "scene_first_not_start_seen_at_epoch",
        "provider_started_at_epoch",
        "provider_wait_started_epoch",
        "started_at_epoch",
        "last_provider_submit_timestamp",
    ):
        try:
            epoch = float(item.get(key) or 0)
            if epoch > 0:
                values.append(max(0, int(now - epoch)))
        except Exception:
            pass
    for key in ("scene_submitted_at_epoch", "scene_first_not_start_seen_at_epoch", "provider_started_at_epoch", "provider_wait_started_epoch", "started_at_epoch"):
        try:
            epoch = float(job.get(key) or 0)
            if epoch > 0:
                values.append(max(0, int(now - epoch)))
        except Exception:
            pass
    for source in (item, job):
        for key in (
            "scene_submitted_at",
            "submitted_at",
            "scene_first_not_start_seen_at",
            "provider_started_at",
            "provider_wait_started_at",
            "started_at",
        ):
            text = str(source.get(key) or "").strip().replace("T", " ")[:19]
            if not text:
                continue
            try:
                epoch = time.mktime(time.strptime(text, "%Y-%m-%d %H:%M:%S"))
            except (OSError, OverflowError, ValueError):
                continue
            if 0 < epoch <= now:
                values.append(max(0, int(now - epoch)))
    return max(values) if values else 0


def _product_video_in_progress_stall_threshold() -> int:
    return max(
        60,
        _env_int(
            "VIDEO_PROVIDER_IN_PROGRESS_STALL_SECONDS",
            _env_int(
                "PRODUCT_VIDEO_SCENE_RUNNING_WITHOUT_RESULT_GRACE_SECONDS",
                DEFAULT_PRODUCT_VIDEO_SCENE_RUNNING_WITHOUT_RESULT_GRACE_SECONDS,
            ),
        ),
    )


def product_video_scene_fallback_idempotency_key(job_id: Any, scene_index: int, fallback_provider: str) -> str:
    return hashlib.sha256(
        f"{str(job_id or '').strip()}|{max(1, _safe_int(scene_index, 1))}|{str(fallback_provider or '').strip()}|product_video_scene_fallback_once".encode("utf-8")
    ).hexdigest()[:24]


def product_video_scene_dispatch_idempotency_key(job_id: Any, scene_index: int, provider_key: str) -> str:
    return hashlib.sha256(
        f"{str(job_id or '').strip()}|{max(1, _safe_int(scene_index, 1))}|{str(provider_key or '').strip()}|product_video_scene_dispatch".encode("utf-8")
    ).hexdigest()[:24]


def product_video_scene_dispatch_mode(job: dict | None = None) -> str:
    job = dict(job or {})
    raw = str(
        job.get("scene_dispatch_mode")
        or job.get("provider_scene_dispatch_mode")
        or os.getenv("PRODUCT_VIDEO_SCENE_DISPATCH_MODE", "parallel")
        or "parallel"
    ).strip().lower().replace("-", "_")
    return "sequential" if raw in {"sequential", "serial", "one_at_a_time"} else "parallel"


def _scene_task_progress_last_changed_elapsed(item: dict | None, job: dict | None, elapsed: int) -> tuple[int, str, str]:
    item = dict(item or {})
    job = dict(job or {})
    for source, current in (("scene", item), ("job", job)):
        for key in ("provider_progress_last_changed_elapsed_seconds", "progress_last_changed_elapsed_seconds"):
            value = _safe_int(current.get(key), 0)
            if value > 0:
                return value, source, str(current.get("provider_progress_last_changed_at") or current.get("progress_last_changed_at") or "")
        for key in ("provider_progress_last_changed_at_epoch", "progress_last_changed_at_epoch"):
            try:
                epoch = float(current.get(key) or 0)
                if epoch > 0:
                    return max(0, int(time.time() - epoch)), source, str(current.get(key) or "")
            except Exception:
                pass
    return max(0, elapsed), "elapsed", ""


def product_video_scene_stall_policy(job: dict | None, scene_task: dict | None, scene_index: int = 1) -> dict[str, Any]:
    job = dict(job or {})
    scene_task = dict(scene_task or {})
    actual_running, actual_status, actual_source = _actual_provider_payload_is_running(scene_task)
    status = _normalize_scene_task_status(_scene_task_status(scene_task), scene_task)
    progress = _scene_task_progress_number(scene_task)
    elapsed = _scene_task_elapsed_seconds(scene_task, job)
    not_start_threshold, not_start_threshold_source = _product_video_not_start_threshold()
    running_threshold = max(not_start_threshold, _product_video_in_progress_stall_threshold())
    total_threshold = max(
        running_threshold,
        _env_int("PRODUCT_VIDEO_TOTAL_SCENE_TIMEOUT_SECONDS", DEFAULT_PRODUCT_VIDEO_TOTAL_SCENE_TIMEOUT_SECONDS),
    )
    result_url_valid = bool(
        scene_task.get("result_url_valid")
        or scene_task.get("download_url_present")
        or scene_task.get("provider_result_url_present")
        or scene_task.get("clip_valid")
        or scene_task.get("artifact_valid")
        or _safe_int(scene_task.get("artifact_size") or scene_task.get("artifact_bytes") or scene_task.get("output_bytes"), 0) > 0
    )
    actual_success_with_result = bool(
        result_url_valid
        and str(actual_status or "").strip().upper() in {"SUCCESS", "SUCCEEDED", "COMPLETED", "DONE"}
    )
    is_not_start = bool(
        False
        if actual_running or actual_success_with_result
        else (status == "provider_not_start" or _scene_task_has_raw_not_start(scene_task))
    )
    current_scene_status = (
        "result_pending_validation"
        if actual_success_with_result and not scene_task.get("clip_valid")
        else (
            PRODUCT_VIDEO_PROVIDER_STALLED_NOT_START
            if is_not_start and elapsed >= not_start_threshold and progress <= 0 and not result_url_valid
            else ("provider_not_start" if is_not_start else status)
        )
    )
    not_start_stalled = bool(is_not_start and progress <= 0 and not result_url_valid and elapsed >= not_start_threshold)
    running_active = bool(actual_running or actual_success_with_result or status in {"provider_running", "result_pending_validation"})
    progress_changed_elapsed, progress_changed_source, progress_changed_at = _scene_task_progress_last_changed_elapsed(scene_task, job, elapsed)
    provider_progress_stuck = bool(running_active and not result_url_valid and progress_changed_elapsed >= running_threshold)
    running_stalled = bool(running_active and not result_url_valid and elapsed >= running_threshold and provider_progress_stuck)
    timed_out = bool(_scene_task_has_provider_id(scene_task) and not result_url_valid and elapsed >= total_threshold)
    stalled = bool(not_start_stalled or running_stalled or timed_out)
    fallback_count = _safe_int(scene_task.get("fallback_count") or scene_task.get("provider_fallback_count"), 0)
    source = str(
        job.get("original_submit_source")
        or job.get("public_confirm_submit_source")
        or job.get("submit_source")
        or job.get("provider_submit_source")
        or ""
    ).strip()
    public_confirmed = bool(
        job.get("public_user_confirmed")
        or job.get("invoice_confirmed")
        or job.get("user_final_confirmed")
        or source == PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_FINAL_CONFIRM
    )
    invoice_confirmed = bool(
        job.get("invoice_confirmed")
        or job.get("final_invoice_confirmed")
        or job.get("project_is_confirmed")
        or public_confirmed
    )
    delivered = bool(job.get("delivered") or job.get("final_delivered") or job.get("video_delivered_at") or job.get("delivery_state") == "delivered")
    charged = bool(_safe_int(job.get("charged_xu") or job.get("total_xu_charged") or job.get("charged_amount_xu"), 0) > 0)
    provider_order = _provider_order(job)
    current_provider = str(
        scene_task.get("provider")
        or job.get("provider_pending_provider")
        or job.get("selected_provider")
        or job.get("selected_provider_before_submit")
        or ""
    ).strip()
    health_at_submit = job.get("provider_health_at_submit") if isinstance(job.get("provider_health_at_submit"), dict) else {}
    fallback_chain = []
    for item in provider_order:
        if not item or item == current_provider:
            continue
        health_state = health_at_submit.get(item) if isinstance(health_at_submit.get(item), dict) else {}
        if health_state and (
            health_state.get("provider_degraded_for_product_video_public")
            or health_state.get("degraded_for_product_video_public")
            or ("live_healthy" in health_state and not health_state.get("live_healthy"))
        ):
            continue
        fallback_chain.append(item)
    automatic_fallback_forbidden = bool(
        _durable_product_video_route_forbids(
            job,
            "automatic_fallback_allowed",
        )
        or (
            str(job.get("source") or "").strip() == "product_video"
            and job.get("automatic_fallback_allowed") is False
        )
    )
    quote_values = [
        _safe_int(job.get("user_visible_price_xu"), 0),
        _safe_int(job.get("persisted_quoted_price_xu"), 0),
        _safe_int(job.get("customer_charge_planned_xu"), 0),
        _safe_int(job.get("provider_budget_xu") or job.get("provider_cost_cap_xu"), 0),
    ]
    exact_quote_preserved = bool(
        quote_values[0] > 0
        and len(set(quote_values)) == 1
        and job.get("quote_consistent") is not False
    )
    runtime_fallback_candidate_recovered = False
    if (
        automatic_fallback_forbidden
        and not fallback_chain
        and exact_quote_preserved
        and public_confirmed
        and invoice_confirmed
        and _scene_task_has_provider_id(scene_task)
        and fallback_count <= 0
        and not delivered
        and not charged
    ):
        runtime_candidates = _provider_candidates_for_capability(
            real_video_provider_readiness(job),
            product_video_required_capability(job),
        )
        if "key4u_video" in runtime_candidates and current_provider != "key4u_video":
            fallback_chain.append("key4u_video")
            runtime_fallback_candidate_recovered = True
    controlled_fallback_allowed = bool(
        automatic_fallback_forbidden
        and exact_quote_preserved
        and public_confirmed
        and invoice_confirmed
        and _scene_task_has_provider_id(scene_task)
        and fallback_count <= 0
        and fallback_chain
        and fallback_chain[0] == "key4u_video"
        and not delivered
        and not charged
    )
    fallback_allowed = bool(
        stalled
        and public_confirmed
        and invoice_confirmed
        and fallback_count <= 0
        and fallback_chain
        and not delivered
        and not charged
        and (not automatic_fallback_forbidden or controlled_fallback_allowed)
    )
    if result_url_valid:
        fallback_block_reason = "scene_already_has_valid_clip"
    elif automatic_fallback_forbidden and not controlled_fallback_allowed:
        fallback_block_reason = "automatic_fallback_forbidden"
    elif not stalled:
        if is_not_start:
            fallback_block_reason = "not_start_under_threshold"
        elif running_active and elapsed >= running_threshold and not provider_progress_stuck:
            fallback_block_reason = "provider_progress_changed_recently"
        else:
            fallback_block_reason = "primary_provider_in_progress" if running_active and elapsed >= not_start_threshold else "scene_not_stalled"
    elif not public_confirmed:
        fallback_block_reason = "not_public_user_final_confirm"
    elif not invoice_confirmed:
        fallback_block_reason = "invoice_not_confirmed"
    elif delivered:
        fallback_block_reason = "already_delivered"
    elif charged:
        fallback_block_reason = "already_charged"
    elif fallback_count > 0:
        fallback_block_reason = "scene_fallback_already_used"
    elif not fallback_chain:
        fallback_block_reason = "no_fallback_provider"
    else:
        fallback_block_reason = ""
    fallbackable_blocker = bool(stalled)
    fallback_eligibility_reason = "eligible" if fallback_allowed else fallback_block_reason
    threshold = not_start_threshold if is_not_start else (running_threshold if running_stalled else total_threshold)
    fallback_provider = str((fallback_chain or [""])[0] or "")
    fallback_idempotency_key = product_video_scene_fallback_idempotency_key(
        job.get("job_id") or job.get("id") or job.get("project_id") or "",
        scene_index,
        fallback_provider,
    ) if fallback_provider else ""
    return {
        "scene_index": max(1, _safe_int(scene_index, 1)),
        "current_scene_status": current_scene_status,
        "provider_not_start": bool(is_not_start),
        "scene_not_start_elapsed": elapsed,
        "provider_elapsed_seconds": elapsed,
        "provider_wait_elapsed_seconds": elapsed,
        "stall_threshold": threshold,
        "not_start_threshold_seconds": not_start_threshold,
        "not_start_threshold_source": not_start_threshold_source,
        "provider_stalled_not_start": bool(not_start_stalled),
        "provider_scene_stalled": stalled,
        "scene_running_without_result_stalled": bool(running_stalled),
        "in_progress_stall_elapsed": progress_changed_elapsed if running_active else 0,
        "in_progress_stall_threshold": running_threshold,
        "provider_progress_last_changed_at": progress_changed_at,
        "provider_progress_last_changed_source": progress_changed_source,
        "provider_progress_stuck": bool(provider_progress_stuck),
        "provider_in_progress_stalled": bool(running_stalled),
        "in_progress_stall_decision": (
            "fallback_allowed"
            if running_stalled and fallback_allowed
            else (
                "failed_no_charge_no_fallback"
                if running_stalled and not fallback_allowed
                else (
                    "progress_changed_recently_continue_polling"
                    if running_active and elapsed >= running_threshold and not provider_progress_stuck
                    else ("under_threshold_continue_polling" if running_active else "")
                )
            )
        ),
        "fallback_due_to_in_progress_stall": bool(running_stalled and fallback_allowed),
        "scene_total_timeout": bool(timed_out),
        "fallback_scene_index": max(1, _safe_int(scene_index, 1)) if stalled else 0,
        "fallback_allowed": fallback_allowed,
        "automatic_fallback_forbidden": automatic_fallback_forbidden,
        "controlled_fallback_allowed": controlled_fallback_allowed,
        "runtime_fallback_candidate_recovered": runtime_fallback_candidate_recovered,
        "fallback_authorization_source": (
            "persisted_exact_quote_final_confirm"
            if controlled_fallback_allowed
            else ""
        ),
        "exact_quote_preserved": exact_quote_preserved,
        "fallback_block_reason": fallback_block_reason,
        "fallbackable_blocker": fallbackable_blocker,
        "fallback_eligibility_reason": fallback_eligibility_reason,
        "fallback_provider_order": fallback_chain,
        "fallback_provider_candidate": fallback_provider,
        "fallback_evaluated": True,
        "fallback_evaluation_source": "product_video_scene_stall_policy",
        "fallback_idempotency_key": fallback_idempotency_key,
        "fallback_count": fallback_count,
        "source_of_truth": (
            "scene_not_start_stalled"
            if not_start_stalled
            else ("scene_provider_stalled" if stalled else ("actual_provider_in_progress" if actual_running else ("scene_provider_task" if _scene_task_has_provider_id(scene_task) else "scene_pending_submit")))
        ),
        "actual_provider_payload_status": actual_status,
        "state_authority_source": actual_source,
        "authoritative_status_source": "result_bearing_success" if actual_success_with_result else (actual_source or "scene_state"),
        "historical_status_ignored": bool(
            (actual_running or actual_success_with_result)
            and _text_indicates_not_start(
                scene_task.get("raw_provider_status_before_source_fix"),
                scene_task.get("raw_provider_status"),
                scene_task.get("provider_status_raw"),
                scene_task.get("blocker"),
                scene_task.get("provider_error"),
            )
        ),
        "success_result_overrode_stale_not_start": bool(
            actual_success_with_result
            and _text_indicates_not_start(
                scene_task.get("raw_provider_status_before_source_fix"),
                scene_task.get("raw_provider_status"),
                scene_task.get("provider_status_raw"),
            )
        ),
        "provider_status_conflict": bool(
            actual_success_with_result
            and _text_indicates_not_start(
                scene_task.get("raw_provider_status_before_source_fix"),
                scene_task.get("raw_provider_status"),
                scene_task.get("provider_status_raw"),
            )
        ),
        "provider_status_conflict_resolution": "result_bearing_success_pending_validation" if actual_success_with_result else "",
        "result_processing_action": "download_and_validate" if actual_success_with_result and not scene_task.get("clip_valid") else "",
        "stale_not_start_blocker_ignored": bool(
            (actual_running or actual_success_with_result)
            and _text_indicates_not_start(
                scene_task.get("raw_provider_status_before_source_fix"),
                scene_task.get("raw_provider_status"),
                scene_task.get("provider_status_raw"),
                scene_task.get("blocker"),
                scene_task.get("provider_error"),
            )
        ),
        "not_start_decision_source": (
            "ignored_result_bearing_success"
            if actual_success_with_result
            else ("ignored_actual_provider_in_progress" if actual_running else ("actual_or_raw_not_start" if is_not_start else ""))
        ),
        "provider_progress_authoritative": bool(actual_running or actual_success_with_result),
    }


def product_video_scene_task_counts(scene_tasks: list[dict[str, Any]] | None = None) -> dict[str, int]:
    tasks = [dict(item or {}) for item in (scene_tasks or []) if isinstance(item, dict)]
    total = len(tasks)
    done = sum(1 for item in tasks if _normalize_scene_task_status(item.get("status"), item) == "clip_downloaded")
    submitted = sum(1 for item in tasks if _scene_task_has_provider_id(item))
    running = sum(1 for item in tasks if _normalize_scene_task_status(item.get("status"), item) in {"provider_running", "provider_not_start", "result_pending_validation", PRODUCT_VIDEO_PROVIDER_STALLED_NOT_START})
    pending = sum(1 for item in tasks if _normalize_scene_task_status(item.get("status"), item) == "pending_submit")
    return {
        "scene_tasks_created_count": total,
        "scene_tasks_submitted_count": submitted,
        "scene_tasks_submitted": submitted,
        "scene_tasks_completed": done,
        "scenes_total": total,
        "scenes_done": done,
        "scenes_pending": pending,
        "scenes_running": running,
    }


def _scene_winner_task_id(candidate: dict[str, Any]) -> str:
    task_ids = candidate.get("provider_task_ids") if isinstance(candidate.get("provider_task_ids"), list) else []
    video_ids = candidate.get("provider_video_ids") if isinstance(candidate.get("provider_video_ids"), list) else []
    return str(
        candidate.get("task_id")
        or candidate.get("provider_task_id")
        or (task_ids[0] if task_ids else "")
        or candidate.get("video_id")
        or candidate.get("provider_video_id")
        or (video_ids[0] if video_ids else "")
        or ""
    ).strip()


def _scene_winner_candidate_valid(candidate: dict[str, Any]) -> bool:
    artifact_size = _safe_int(
        candidate.get("artifact_size")
        or candidate.get("artifact_bytes")
        or candidate.get("output_bytes")
        or candidate.get("bytes"),
        0,
    )
    output_path = str(candidate.get("output_path") or candidate.get("local_path") or "").strip()
    path_valid = bool(output_path and os.path.isfile(output_path) and os.path.getsize(output_path) > 0)
    return bool(
        candidate.get("clip_valid")
        or candidate.get("artifact_valid")
        or candidate.get("validation_passed")
        or path_valid
        or (
            artifact_size > 0
            and (
                candidate.get("result_url_valid")
                or candidate.get("provider_result_url_present")
                or candidate.get("download_url_present")
                or candidate.get("result_url_present")
            )
        )
    )


def _scene_winner_completed_epoch(candidate: dict[str, Any], fallback_order: int) -> float:
    for key in (
        "winner_selected_at_epoch",
        "completed_at_epoch",
        "result_received_at_epoch",
        "downloaded_at_epoch",
        "updated_at_epoch",
    ):
        try:
            value = float(candidate.get(key) or 0)
        except Exception:
            value = 0.0
        if value > 0:
            return value
    return float(10_000_000_000 + fallback_order)


def product_video_select_scene_winner(
    candidates: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    *,
    persisted_winner_task: str = "",
    now_epoch: float | None = None,
) -> dict[str, Any]:
    rows = [dict(item or {}) for item in (candidates or []) if isinstance(item, dict)]
    valid: list[tuple[int, dict[str, Any]]] = [
        (index, item)
        for index, item in enumerate(rows)
        if _scene_winner_task_id(item) and _scene_winner_candidate_valid(item)
    ]
    persisted = str(persisted_winner_task or "").strip()
    winner: dict[str, Any] = {}
    winner_source = ""
    if persisted:
        winner = next((item for _index, item in valid if _scene_winner_task_id(item) == persisted), {})
        if winner:
            winner_source = "persisted_winner"
    if not winner and valid:
        _index, winner = min(
            valid,
            key=lambda pair: (_scene_winner_completed_epoch(pair[1], pair[0]), pair[0]),
        )
        winner_source = "first_valid_clip"
    winner_task = _scene_winner_task_id(winner) if winner else ""
    late = [
        _scene_winner_task_id(item)
        for _index, item in valid
        if _scene_winner_task_id(item) and _scene_winner_task_id(item) != winner_task
    ]
    selected_epoch = _scene_winner_completed_epoch(winner, 0) if winner else 0.0
    if selected_epoch >= 10_000_000_000:
        selected_epoch = float(now_epoch or time.time()) if winner else 0.0
    return {
        "scene_winner_task": winner_task,
        "scene_winner_task_masked": _task_id_masked(winner_task),
        "scene_winner_provider": str(winner.get("provider") or winner.get("selected_provider") or ""),
        "winner_selected_at_epoch": selected_epoch,
        "winner_selected_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(selected_epoch)) if selected_epoch else "",
        "winner_source": winner_source,
        "winner_valid": bool(winner),
        "late_result_ignored": late,
        "late_result_ignored_masked": [_task_id_masked(item) for item in late],
        "duplicate_scene_result_prevented": bool(late),
    }


def product_video_scene_tasks_debug(
    job: dict | None = None,
    *,
    provider_events: list[dict[str, Any]] | None = None,
    debug_results: list[dict[str, Any]] | None = None,
    scene_count: int | None = None,
) -> list[dict[str, Any]]:
    total = max(1, min(20, _safe_int(scene_count, _scene_count(job))))
    by_scene: dict[int, dict[str, Any]] = {}
    canonical_task_candidates_by_scene: dict[str, list[dict[str, Any]]] = {str(idx): [] for idx in range(1, total + 1)}
    canonical_task_reject_reasons: dict[str, list[dict[str, Any]]] = {str(idx): [] for idx in range(1, total + 1)}

    def _record_canonical_candidate(source: dict[str, Any], debug: dict[str, Any] | None = None) -> None:
        debug = dict(debug or {})
        if not isinstance(source, dict):
            return
        idx = _scene_task_index(source, 1)
        if idx not in by_scene:
            return
        task_id = str(
            source.get("provider_task_id")
            or source.get("task_id")
            or debug.get("provider_task_id")
            or ""
        ).strip()
        video_id = str(
            source.get("provider_video_id")
            or source.get("video_id")
            or debug.get("provider_video_id")
            or ""
        ).strip()
        if not task_id and not video_id:
            return
        actual_status, actual_status_source, raw_status_before_fix = _actual_status_payload_value({**source, **debug})
        candidate = {
            "scene_index": idx,
            "task_id": task_id,
            "task_id_masked": _task_id_masked(task_id),
            "video_id_masked": _task_id_masked(video_id),
            "provider": str(source.get("provider") or debug.get("selected_provider") or debug.get("provider") or ""),
            "provider_status_raw": actual_status
            or str(debug.get("provider_status_raw") or source.get("provider_status_raw") or source.get("status") or ""),
            "provider_status_payload_source": actual_status_source,
            "raw_provider_status_before_source_fix": raw_status_before_fix,
            "result_url_valid": bool(
                (task_id or video_id)
                and (
                source.get("result_url_valid")
                or source.get("download_url_present")
                or debug.get("provider_result_url_present")
                or debug.get("result_url_present")
                )
            ),
            "result_url": str((
                source.get("result_url")
                or source.get("download_url")
                or debug.get("result_url")
                or debug.get("provider_result_url")
                or ""
            ) if (task_id or video_id) else ""),
            "clip_valid": bool(source.get("clip_valid") or debug.get("clip_valid") or debug.get("validation_passed")),
            "artifact_size": _safe_int(
                source.get("artifact_size")
                or source.get("artifact_bytes")
                or debug.get("artifact_size")
                or debug.get("bytes")
                or debug.get("downloaded_file_size"),
                0,
            ),
            "output_path": str(source.get("output_path") or debug.get("output_path") or debug.get("local_path") or ""),
            "completed_at_epoch": source.get("completed_at_epoch") or debug.get("completed_at_epoch") or debug.get("result_received_at_epoch") or 0,
        }
        canonical_task_candidates_by_scene[str(idx)].append(candidate)
        for other_idx in range(1, total + 1):
            if other_idx == idx:
                continue
            canonical_task_reject_reasons[str(other_idx)].append(
                {
                    "candidate_scene_index": idx,
                    "task_id_masked": candidate["task_id_masked"],
                    "video_id_masked": candidate["video_id_masked"],
                    "reason": "different_scene",
                }
            )

    for idx in range(1, total + 1):
        by_scene[idx] = {
            "scene_index": idx,
            "required": True,
            "canonical_scene_index": idx,
            "canonical_task_selected": "",
            "canonical_task_candidates_by_scene": {},
            "canonical_task_reject_reasons": {},
            "scene_winner_task": "",
            "scene_winner_task_masked": "",
            "scene_winner_provider": "",
            "winner_selected_at": "",
            "winner_selected_at_epoch": 0,
            "late_result_ignored": [],
            "late_result_ignored_masked": [],
            "duplicate_scene_result_prevented": False,
            "scene_duration_seconds": product_video_scene_duration_seconds(job),
            "request_job_id": product_video_scene_request_id(job, idx),
            "provider": "",
            "provider_key": "",
            "provider_task_id": "",
            "task_id": "",
            "provider_video_id": "",
            "video_id": "",
            "primary_task_id": "",
            "fallback_task_ids": [],
            "active_task_id": "",
            "winning_task_id": "",
            "provider_task_id_masked": "",
            "task_id_masked": "",
            "provider_video_id_masked": "",
            "status": "pending_submit",
            "result_url_valid": False,
            "result_url": "",
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
            "raw_clip_duration": 0,
            "fallback_count": 0,
            "provider_progress_raw": "",
            "provider_progress_normalized": 0,
            "progress": 0,
            "progress_last_changed_at": "",
            "selected_model": "",
            "selected_provider": "",
            "selected_family": "",
            "selected_payload_adapter": "",
            "provider_wait_elapsed_seconds": 0,
            "provider_elapsed_seconds": 0,
            "scene_not_start_elapsed": 0,
            "scene_submitted_at": "",
            "submitted_at": "",
            "started_at": "",
            "scene_first_not_start_seen_at": "",
            "completed_at": "",
            "failure_reason": "",
            "stall_threshold": DEFAULT_PRODUCT_VIDEO_FIRST_SCENE_NOT_START_GRACE_SECONDS,
            "not_start_threshold_seconds": DEFAULT_PRODUCT_VIDEO_FIRST_SCENE_NOT_START_GRACE_SECONDS,
            "not_start_threshold_source": "default:product_video_not_start_grace",
            "provider_stalled_not_start": False,
            "fallback_allowed": False,
            "fallback_block_reason": "scene_not_stalled",
            "fallbackable_blocker": False,
            "fallback_eligibility_reason": "scene_not_stalled",
            "fallback_provider_order": [],
            "fallback_scene_index": 0,
            "source_of_truth": "scene_pending_submit",
        }
    for item in _existing_scene_tasks(job):
        idx = _scene_task_index(item)
        if idx not in by_scene:
            continue
        _record_canonical_candidate(item)
        task_id = str(item.get("provider_task_id") or item.get("task_id") or "").strip()
        video_id = str(item.get("provider_video_id") or item.get("video_id") or "").strip()
        actual_status, actual_status_source, raw_status_before_fix = _actual_status_payload_value(item)
        merged = {
                "canonical_scene_index": idx,
                "canonical_task_selected": task_id or video_id,
                "provider": str(item.get("provider") or by_scene[idx].get("provider") or ""),
                "provider_key": str(item.get("provider_key") or item.get("provider") or by_scene[idx].get("provider_key") or ""),
                "provider_task_id": task_id,
                "task_id": task_id,
                "provider_video_id": video_id,
                "video_id": video_id,
                "primary_task_id": str(item.get("primary_task_id") or task_id or video_id or by_scene[idx].get("primary_task_id") or ""),
                "fallback_task_ids": list(item.get("fallback_task_ids") or by_scene[idx].get("fallback_task_ids") or []),
                "active_task_id": str(item.get("active_task_id") or task_id or video_id or by_scene[idx].get("active_task_id") or ""),
                "winning_task_id": str(item.get("winning_task_id") or item.get("scene_winner_task") or by_scene[idx].get("winning_task_id") or ""),
                "provider_task_id_masked": _task_id_masked(task_id),
                "task_id_masked": _task_id_masked(task_id),
                "provider_video_id_masked": _task_id_masked(video_id),
                "result_url_valid": bool(
                    (task_id or video_id)
                    and (item.get("result_url_valid") or item.get("download_url_present") or item.get("provider_result_url_present"))
                ),
                "result_url": str(
                    (item.get("result_url") or item.get("provider_result_url") or item.get("download_url") or by_scene[idx].get("result_url") or "")
                    if (task_id or video_id)
                    else ""
                ),
                "result_task_id": str(task_id or video_id or ""),
                "result_url_source": "persisted_scene_task" if (task_id or video_id) and (item.get("result_url") or item.get("provider_result_url") or item.get("download_url")) else "",
                "task_scene_mapping_verified": bool(task_id or video_id),
                "phantom_result_prevented": bool(
                    not (task_id or video_id)
                    and (item.get("result_url") or item.get("provider_result_url") or item.get("download_url") or item.get("result_url_valid"))
                ),
                "clip_path": str(item.get("clip_path") or item.get("output_path") or item.get("local_path") or by_scene[idx].get("clip_path") or ""),
                "clip_bytes": _safe_int(item.get("clip_bytes") or item.get("artifact_size") or item.get("artifact_bytes") or item.get("output_bytes"), _safe_int(by_scene[idx].get("clip_bytes"), 0)),
                "clip_valid": bool(item.get("clip_valid") or item.get("validation_passed") or by_scene[idx].get("clip_valid")),
                "raw_clip_duration": item.get("raw_clip_duration") or item.get("duration") or item.get("output_duration") or 0,
                "fallback_count": _safe_int(item.get("fallback_count"), 0),
                "provider_progress_raw": item.get("provider_progress_raw") or item.get("shopaikey_data_progress_raw") or item.get("data_progress_raw") or item.get("progress") or "",
                "provider_progress_normalized": _safe_int(item.get("provider_progress_normalized") or item.get("provider_progress_percent") or item.get("progress"), 0),
                "progress": _safe_int(item.get("progress") or item.get("provider_progress_normalized") or item.get("provider_progress_percent"), 0),
                "selected_model": str(item.get("selected_model") or item.get("model") or ""),
                "selected_provider": str(item.get("selected_provider") or item.get("provider") or ""),
                "selected_family": str(item.get("selected_family") or ""),
                "selected_payload_adapter": str(item.get("selected_payload_adapter") or ""),
                "provider_wait_elapsed_seconds": _safe_int(item.get("provider_wait_elapsed_seconds") or item.get("provider_elapsed_seconds") or item.get("elapsed_wall_clock_seconds"), 0),
                "provider_elapsed_seconds": _safe_int(item.get("provider_elapsed_seconds") or item.get("provider_wait_elapsed_seconds") or item.get("elapsed_wall_clock_seconds"), 0),
                "provider_status_raw": actual_status or str(item.get("provider_status_raw") or item.get("nonterminal_provider_status") or item.get("provider_status") or ""),
                "raw_provider_status_before_source_fix": raw_status_before_fix,
                "provider_status_payload_source": actual_status_source,
                "scene_submitted_at": str(item.get("scene_submitted_at") or item.get("submitted_at") or item.get("provider_started_at") or item.get("provider_wait_started_at") or ""),
                "submitted_at": str(item.get("submitted_at") or item.get("scene_submitted_at") or item.get("provider_started_at") or ""),
                "started_at": str(item.get("started_at") or item.get("provider_started_at") or item.get("provider_wait_started_at") or ""),
                "scene_first_not_start_seen_at": str(item.get("scene_first_not_start_seen_at") or item.get("first_not_start_seen_at") or item.get("provider_started_at") or item.get("provider_wait_started_at") or ""),
                "completed_at": str(item.get("completed_at") or item.get("result_received_at") or item.get("winner_selected_at") or ""),
                "failure_reason": str(item.get("failure_reason") or item.get("provider_error") or item.get("blocker") or ""),
                "scene_winner_task": str(item.get("scene_winner_task") or ""),
                "scene_winner_provider": str(item.get("scene_winner_provider") or ""),
                "winner_selected_at": str(item.get("winner_selected_at") or ""),
                "winner_selected_at_epoch": item.get("winner_selected_at_epoch") or 0,
                "provider_progress_last_changed_at": str(item.get("provider_progress_last_changed_at") or item.get("progress_last_changed_at") or ""),
                "provider_progress_last_changed_elapsed_seconds": _safe_int(item.get("provider_progress_last_changed_elapsed_seconds") or item.get("progress_last_changed_elapsed_seconds"), 0),
                "submit_accepted": bool(item.get("submit_accepted") or task_id or video_id),
                "submit_http_status": _safe_int(item.get("submit_http_status") or item.get("provider_submit_http_status"), 0),
                "transport_http": _safe_int(item.get("transport_http") or item.get("submit_http_status") or item.get("provider_submit_http_status"), 0),
                "task_id_present": bool(item.get("task_id_present") or task_id or video_id),
                "task_pollable": bool(item.get("task_pollable") or task_id or video_id),
                "effective_submit_outcome": str(item.get("effective_submit_outcome") or ""),
                "transport_anomaly": bool(item.get("transport_anomaly")),
                "transport_anomaly_ignored_due_to_valid_task": bool(item.get("transport_anomaly_ignored_due_to_valid_task")),
                "dispatch_state": str(item.get("dispatch_state") or item.get("scene_dispatch_state") or ("task_submitted" if task_id or video_id else "submit_in_progress")),
                "dispatch_attempted": bool(item.get("dispatch_attempted") or item.get("scene_dispatch_attempted") or item.get("provider_submit_called")),
                "dispatch_block_reason": str(item.get("dispatch_block_reason") or item.get("scene_dispatch_block_reason") or ""),
                "dispatch_idempotency_key": str(item.get("dispatch_idempotency_key") or item.get("scene_dispatch_idempotency_key") or item.get("provider_submit_idempotency_key") or ""),
                "dispatch_recovered": bool(item.get("dispatch_recovered") or item.get("missing_scene_dispatch_recovered")),
        }
        merged["status"] = _normalize_scene_task_status(actual_status or item.get("status") or merged.get("provider_status_raw"), {**item, **merged})
        historical_not_start = _text_indicates_not_start(raw_status_before_fix, item.get("provider_status_raw"))
        current_success = str(actual_status or "").strip().upper() in {"SUCCESS", "SUCCEEDED", "COMPLETED", "DONE"}
        result_pending = bool(merged["result_url_valid"] and not merged["clip_valid"])
        merged["authoritative_status_source"] = (
            "validated_scene_clip"
            if merged["clip_valid"]
            else ("current_result_bearing_success" if current_success and result_pending else (actual_status_source or "persisted_scene_status"))
        )
        merged["historical_status_ignored"] = bool(current_success and result_pending and historical_not_start)
        merged["success_result_overrode_stale_not_start"] = bool(current_success and result_pending and historical_not_start)
        merged["provider_status_conflict"] = bool(current_success and result_pending and historical_not_start)
        merged["provider_status_conflict_resolution"] = "result_bearing_success_pending_validation" if merged["provider_status_conflict"] else ""
        merged["result_processing_action"] = "download_and_validate" if result_pending else ""
        by_scene[idx].update(merged)
    for source in (provider_events or []) + (debug_results or []):
        if not isinstance(source, dict):
            continue
        idx = _scene_task_index(source, 1)
        if idx not in by_scene:
            continue
        debug = source.get("debug") if isinstance(source.get("debug"), dict) else source
        _record_canonical_candidate(source, debug)
        task_id = str(source.get("task_id") or source.get("provider_task_id") or debug.get("provider_task_id") or "").strip()
        video_id = str(source.get("video_id") or source.get("provider_video_id") or debug.get("provider_video_id") or "").strip()
        actual_status, actual_status_source, raw_status_before_fix = _actual_status_payload_value({**source, **debug})
        status = str(
            actual_status
            or source.get("status")
            or debug.get("normalized_provider_status")
            or debug.get("nonterminal_provider_status")
            or debug.get("provider_status_raw")
            or debug.get("provider_status")
            or debug.get("blocker")
            or ""
        ).strip()
        merged = {
                "canonical_scene_index": idx,
                "canonical_task_selected": task_id or video_id or str(by_scene[idx].get("canonical_task_selected") or ""),
                "provider": str(source.get("provider") or debug.get("selected_provider") or debug.get("provider") or by_scene[idx].get("provider") or ""),
                "provider_key": str(source.get("provider_key") or source.get("provider") or debug.get("selected_provider") or debug.get("provider") or by_scene[idx].get("provider_key") or ""),
                "provider_task_id": task_id or str(by_scene[idx].get("provider_task_id") or ""),
                "task_id": task_id or str(by_scene[idx].get("task_id") or ""),
                "provider_video_id": video_id or str(by_scene[idx].get("provider_video_id") or ""),
                "video_id": video_id or str(by_scene[idx].get("video_id") or ""),
                "primary_task_id": str(by_scene[idx].get("primary_task_id") or task_id or video_id or ""),
                "fallback_task_ids": list(by_scene[idx].get("fallback_task_ids") or []),
                "active_task_id": task_id or video_id or str(by_scene[idx].get("active_task_id") or ""),
                "winning_task_id": str(debug.get("winning_task_id") or debug.get("scene_winner_task") or source.get("winning_task_id") or source.get("scene_winner_task") or by_scene[idx].get("winning_task_id") or ""),
                "provider_task_id_masked": _task_id_masked(task_id),
                "task_id_masked": _task_id_masked(task_id),
                "provider_video_id_masked": _task_id_masked(video_id),
                "result_url_valid": bool(
                    (task_id or video_id)
                    and (
                    source.get("download_url_present")
                    or debug.get("provider_result_url_present")
                    or debug.get("result_url_present")
                    or by_scene[idx].get("result_url_valid")
                    )
                ),
                "result_url": str(
                    (debug.get("result_url") or debug.get("provider_result_url") or source.get("result_url") or source.get("download_url") or by_scene[idx].get("result_url") or "")
                    if (task_id or video_id)
                    else ""
                ),
                "result_task_id": str(task_id or video_id or ""),
                "result_url_source": "scene_provider_event" if (task_id or video_id) and (debug.get("result_url") or debug.get("provider_result_url") or source.get("result_url") or source.get("download_url")) else "",
                "task_scene_mapping_verified": bool(task_id or video_id),
                "phantom_result_prevented": bool(
                    not (task_id or video_id)
                    and (debug.get("result_url") or debug.get("provider_result_url") or source.get("result_url") or source.get("download_url") or debug.get("result_url_present"))
                ),
                "clip_path": str(debug.get("clip_path") or debug.get("output_path") or debug.get("local_path") or source.get("clip_path") or source.get("output_path") or by_scene[idx].get("clip_path") or ""),
                "clip_bytes": _safe_int(debug.get("clip_bytes") or debug.get("artifact_size") or debug.get("artifact_bytes") or debug.get("output_bytes") or debug.get("downloaded_file_size") or source.get("clip_bytes"), _safe_int(by_scene[idx].get("clip_bytes"), 0)),
                "clip_valid": bool(debug.get("clip_valid") or debug.get("validation_passed") or source.get("clip_valid") or by_scene[idx].get("clip_valid")),
                "raw_clip_duration": source.get("duration") or debug.get("output_duration") or by_scene[idx].get("raw_clip_duration") or 0,
                "fallback_count": _safe_int(debug.get("fallback_count") or source.get("fallback_count"), _safe_int(by_scene[idx].get("fallback_count"), 0)),
                "provider_progress_raw": debug.get("provider_progress_raw") or debug.get("shopaikey_data_progress_raw") or source.get("provider_progress_raw") or by_scene[idx].get("provider_progress_raw") or "",
                "provider_progress_normalized": _safe_int(debug.get("provider_progress_normalized") or debug.get("provider_progress_percent") or source.get("provider_progress_normalized"), _safe_int(by_scene[idx].get("provider_progress_normalized"), 0)),
                "progress": _safe_int(debug.get("progress") or debug.get("provider_progress_normalized") or debug.get("provider_progress_percent") or source.get("progress"), _safe_int(by_scene[idx].get("progress"), 0)),
                "selected_model": str(debug.get("selected_model") or debug.get("model_used_in_payload") or debug.get("provider_payload_model") or source.get("selected_model") or source.get("model") or by_scene[idx].get("selected_model") or ""),
                "selected_provider": str(debug.get("selected_provider") or source.get("selected_provider") or by_scene[idx].get("selected_provider") or ""),
                "selected_family": str(debug.get("selected_family") or source.get("selected_family") or by_scene[idx].get("selected_family") or ""),
                "selected_payload_adapter": str(debug.get("selected_payload_adapter") or source.get("selected_payload_adapter") or by_scene[idx].get("selected_payload_adapter") or ""),
                "provider_wait_elapsed_seconds": _safe_int(debug.get("provider_wait_elapsed_seconds") or debug.get("provider_elapsed_seconds") or debug.get("elapsed_wall_clock_seconds") or source.get("provider_wait_elapsed_seconds"), _safe_int(by_scene[idx].get("provider_wait_elapsed_seconds"), 0)),
                "provider_elapsed_seconds": _safe_int(debug.get("provider_elapsed_seconds") or debug.get("provider_wait_elapsed_seconds") or debug.get("elapsed_wall_clock_seconds") or source.get("provider_elapsed_seconds"), _safe_int(by_scene[idx].get("provider_elapsed_seconds") or by_scene[idx].get("provider_wait_elapsed_seconds"), 0)),
                "provider_status_raw": actual_status or str(debug.get("provider_status_raw") or debug.get("nonterminal_provider_status") or source.get("provider_status_raw") or status or ""),
                "raw_provider_status_before_source_fix": raw_status_before_fix,
                "provider_status_payload_source": actual_status_source,
                "provider_stalled_not_start": bool(debug.get("provider_stalled_not_start") or source.get("provider_stalled_not_start")),
                "fallback_allowed": bool(debug.get("fallback_allowed") or source.get("fallback_allowed") or False),
                "fallback_block_reason": str(debug.get("fallback_block_reason") or debug.get("fallback_blocked_reason") or source.get("fallback_block_reason") or by_scene[idx].get("fallback_block_reason") or ""),
                "fallback_scene_index": _safe_int(debug.get("fallback_scene_index") or source.get("fallback_scene_index"), _safe_int(by_scene[idx].get("fallback_scene_index"), 0)),
                "fallbackable_blocker": bool(debug.get("fallbackable_blocker") or source.get("fallbackable_blocker") or by_scene[idx].get("fallbackable_blocker")),
                "fallback_eligibility_reason": str(debug.get("fallback_eligibility_reason") or source.get("fallback_eligibility_reason") or by_scene[idx].get("fallback_eligibility_reason") or ""),
                "fallback_provider_order": debug.get("fallback_provider_order") or source.get("fallback_provider_order") or by_scene[idx].get("fallback_provider_order") or [],
                "source_of_truth": str(debug.get("source_of_truth") or source.get("source_of_truth") or by_scene[idx].get("source_of_truth") or ""),
                "scene_submitted_at": str(debug.get("scene_submitted_at") or source.get("scene_submitted_at") or by_scene[idx].get("scene_submitted_at") or ""),
                "submitted_at": str(debug.get("submitted_at") or debug.get("scene_submitted_at") or source.get("submitted_at") or source.get("scene_submitted_at") or by_scene[idx].get("submitted_at") or ""),
                "started_at": str(debug.get("started_at") or debug.get("provider_started_at") or source.get("started_at") or source.get("provider_started_at") or by_scene[idx].get("started_at") or ""),
                "scene_first_not_start_seen_at": str(debug.get("scene_first_not_start_seen_at") or source.get("scene_first_not_start_seen_at") or by_scene[idx].get("scene_first_not_start_seen_at") or ""),
                "completed_at": str(debug.get("completed_at") or debug.get("result_received_at") or source.get("completed_at") or source.get("result_received_at") or by_scene[idx].get("completed_at") or ""),
                "failure_reason": str(debug.get("failure_reason") or debug.get("provider_error") or debug.get("blocker") or source.get("failure_reason") or source.get("provider_error") or source.get("blocker") or by_scene[idx].get("failure_reason") or ""),
                "scene_winner_task": str(debug.get("scene_winner_task") or source.get("scene_winner_task") or by_scene[idx].get("scene_winner_task") or ""),
                "scene_winner_provider": str(debug.get("scene_winner_provider") or source.get("scene_winner_provider") or by_scene[idx].get("scene_winner_provider") or ""),
                "winner_selected_at": str(debug.get("winner_selected_at") or source.get("winner_selected_at") or by_scene[idx].get("winner_selected_at") or ""),
                "winner_selected_at_epoch": debug.get("winner_selected_at_epoch") or source.get("winner_selected_at_epoch") or by_scene[idx].get("winner_selected_at_epoch") or 0,
                "provider_progress_last_changed_at": str(debug.get("provider_progress_last_changed_at") or source.get("provider_progress_last_changed_at") or by_scene[idx].get("provider_progress_last_changed_at") or ""),
                "provider_progress_last_changed_elapsed_seconds": _safe_int(debug.get("provider_progress_last_changed_elapsed_seconds") or source.get("provider_progress_last_changed_elapsed_seconds"), _safe_int(by_scene[idx].get("provider_progress_last_changed_elapsed_seconds"), 0)),
                "submit_accepted": bool(debug.get("submit_accepted") or source.get("submit_accepted") or task_id or video_id),
                "submit_http_status": _safe_int(debug.get("submit_http_status") or debug.get("provider_submit_http_status") or source.get("submit_http_status"), _safe_int(by_scene[idx].get("submit_http_status"), 0)),
                "transport_http": _safe_int(debug.get("transport_http") or source.get("transport_http") or debug.get("submit_http_status") or debug.get("provider_submit_http_status"), _safe_int(by_scene[idx].get("transport_http"), 0)),
                "task_id_present": bool(debug.get("task_id_present") or source.get("task_id_present") or task_id or video_id),
                "task_pollable": bool(debug.get("task_pollable") or source.get("task_pollable") or task_id or video_id),
                "effective_submit_outcome": str(debug.get("effective_submit_outcome") or source.get("effective_submit_outcome") or by_scene[idx].get("effective_submit_outcome") or ""),
                "transport_anomaly": bool(debug.get("transport_anomaly") or source.get("transport_anomaly") or by_scene[idx].get("transport_anomaly")),
                "transport_anomaly_ignored_due_to_valid_task": bool(debug.get("transport_anomaly_ignored_due_to_valid_task") or source.get("transport_anomaly_ignored_due_to_valid_task") or by_scene[idx].get("transport_anomaly_ignored_due_to_valid_task")),
                "dispatch_state": str(debug.get("dispatch_state") or debug.get("scene_dispatch_state") or source.get("dispatch_state") or by_scene[idx].get("dispatch_state") or ("task_submitted" if task_id or video_id else "submit_in_progress")),
                "dispatch_attempted": bool(debug.get("dispatch_attempted") or debug.get("scene_dispatch_attempted") or source.get("dispatch_attempted") or source.get("provider_submit_called") or by_scene[idx].get("dispatch_attempted")),
                "dispatch_block_reason": str(debug.get("dispatch_block_reason") or debug.get("scene_dispatch_block_reason") or source.get("dispatch_block_reason") or by_scene[idx].get("dispatch_block_reason") or ""),
                "dispatch_idempotency_key": str(debug.get("dispatch_idempotency_key") or debug.get("scene_dispatch_idempotency_key") or source.get("dispatch_idempotency_key") or by_scene[idx].get("dispatch_idempotency_key") or ""),
                "dispatch_recovered": bool(debug.get("dispatch_recovered") or debug.get("missing_scene_dispatch_recovered") or source.get("dispatch_recovered") or by_scene[idx].get("dispatch_recovered")),
        }
        merged["status"] = _normalize_scene_task_status(actual_status or status or by_scene[idx].get("status"), {**source, **debug, **merged})
        historical_not_start = _text_indicates_not_start(raw_status_before_fix, debug.get("provider_status_raw"), source.get("provider_status_raw"))
        current_success = str(actual_status or "").strip().upper() in {"SUCCESS", "SUCCEEDED", "COMPLETED", "DONE"}
        result_pending = bool(merged["result_url_valid"] and not merged["clip_valid"])
        merged["authoritative_status_source"] = (
            "validated_scene_clip"
            if merged["clip_valid"]
            else ("current_result_bearing_success" if current_success and result_pending else (actual_status_source or "scene_provider_event"))
        )
        merged["historical_status_ignored"] = bool(current_success and result_pending and historical_not_start)
        merged["success_result_overrode_stale_not_start"] = bool(current_success and result_pending and historical_not_start)
        merged["provider_status_conflict"] = bool(current_success and result_pending and historical_not_start)
        merged["provider_status_conflict_resolution"] = "result_bearing_success_pending_validation" if merged["provider_status_conflict"] else ""
        merged["result_processing_action"] = "download_and_validate" if result_pending else ""
        by_scene[idx].update(merged)
    for idx in sorted(by_scene):
        policy = product_video_scene_stall_policy(job, by_scene[idx], idx)
        current_block_reason = str(by_scene[idx].get("fallback_block_reason") or "")
        current_eligibility_reason = str(by_scene[idx].get("fallback_eligibility_reason") or "")
        current_source_of_truth = str(by_scene[idx].get("source_of_truth") or "")
        policy_block_reason = str(policy["fallback_block_reason"] or "")
        policy_eligibility_reason = str(policy["fallback_eligibility_reason"] or "")
        policy_source_of_truth = str(policy["source_of_truth"] or "")
        if current_block_reason in {"", "scene_not_stalled", "primary_provider_in_progress", "selected_provider_in_progress", "not_start_under_threshold"} or policy["provider_not_start"] or policy["fallback_allowed"] or policy["provider_scene_stalled"]:
            current_block_reason = policy_block_reason
        if current_eligibility_reason in {"", "scene_not_stalled", "primary_provider_in_progress", "selected_provider_in_progress", "not_start_under_threshold"} or policy["provider_not_start"] or policy["fallback_allowed"] or policy["provider_scene_stalled"]:
            current_eligibility_reason = policy_eligibility_reason
        if current_source_of_truth in {"", "scene_pending_submit"} or policy["provider_not_start"] or policy["provider_scene_stalled"]:
            current_source_of_truth = policy_source_of_truth
        fallback_allowed = bool(policy["fallback_allowed"] if policy["provider_scene_stalled"] else (by_scene[idx].get("fallback_allowed") or policy["fallback_allowed"]))
        own_candidates = canonical_task_candidates_by_scene.get(str(idx)) or []
        canonical_selected = str(by_scene[idx].get("canonical_task_selected") or "")
        if not canonical_selected and own_candidates:
            canonical_selected = str(own_candidates[-1].get("task_id") or own_candidates[-1].get("video_id_masked") or "")
        policy_actual_authoritative = str(policy.get("not_start_decision_source") or "") in {
            "ignored_actual_provider_in_progress",
            "ignored_result_bearing_success",
        }
        winner = product_video_select_scene_winner(
            own_candidates,
            persisted_winner_task=str(by_scene[idx].get("scene_winner_task") or ""),
        )
        candidate_task_ids = [
            str(item.get("task_id") or "").strip()
            for item in own_candidates
            if str(item.get("task_id") or "").strip()
        ]
        primary_task_id = str(by_scene[idx].get("primary_task_id") or (candidate_task_ids[0] if candidate_task_ids else ""))
        fallback_task_ids = [task_id for task_id in candidate_task_ids if task_id != primary_task_id]
        if winner.get("winner_valid"):
            canonical_selected = str(winner.get("scene_winner_task") or canonical_selected)
        by_scene[idx].update(
            {
                "canonical_scene_index": idx,
                "canonical_task_selected": canonical_selected,
                "canonical_task_candidates_by_scene": canonical_task_candidates_by_scene,
                "canonical_task_reject_reasons": canonical_task_reject_reasons,
                "primary_task_id": primary_task_id,
                "fallback_task_ids": fallback_task_ids,
                "active_task_id": str(winner.get("scene_winner_task") or by_scene[idx].get("active_task_id") or canonical_selected or ""),
                "winning_task_id": str(winner.get("scene_winner_task") or by_scene[idx].get("winning_task_id") or ""),
                "status": policy["current_scene_status"] if (policy.get("provider_not_start") or policy_actual_authoritative) else by_scene[idx].get("status"),
                "scene_not_start_elapsed": policy["scene_not_start_elapsed"],
                "provider_elapsed_seconds": max(_safe_int(by_scene[idx].get("provider_elapsed_seconds"), 0), _safe_int(policy.get("provider_elapsed_seconds"), 0)),
                "provider_wait_elapsed_seconds": max(_safe_int(by_scene[idx].get("provider_wait_elapsed_seconds"), 0), _safe_int(policy.get("provider_wait_elapsed_seconds"), 0)),
                "stall_threshold": policy["stall_threshold"],
                "not_start_threshold_seconds": policy["not_start_threshold_seconds"],
                "not_start_threshold_source": policy["not_start_threshold_source"],
                "provider_stalled_not_start": False if policy_actual_authoritative else bool(by_scene[idx].get("provider_stalled_not_start") or policy["provider_stalled_not_start"]),
                "provider_scene_stalled": bool(policy.get("provider_scene_stalled")),
                "provider_in_progress_stalled": bool(policy.get("provider_in_progress_stalled")),
                "scene_running_without_result_stalled": bool(policy.get("scene_running_without_result_stalled")),
                "in_progress_stall_elapsed": _safe_int(policy.get("in_progress_stall_elapsed"), 0),
                "in_progress_stall_threshold": _safe_int(policy.get("in_progress_stall_threshold"), 0),
                "provider_progress_last_changed_at": str(policy.get("provider_progress_last_changed_at") or by_scene[idx].get("provider_progress_last_changed_at") or ""),
                "provider_progress_last_changed_source": str(policy.get("provider_progress_last_changed_source") or ""),
                "provider_progress_stuck": bool(policy.get("provider_progress_stuck")),
                "fallback_allowed": fallback_allowed,
                "fallback_block_reason": current_block_reason,
                "fallbackable_blocker": bool(by_scene[idx].get("fallbackable_blocker") or policy["fallbackable_blocker"]),
                "fallback_eligibility_reason": current_eligibility_reason,
                "fallback_provider_order": policy["fallback_provider_order"],
                "fallback_provider_candidate": str((policy["fallback_provider_order"] or [""])[0]),
                "fallback_evaluated": bool(policy.get("fallback_evaluated")),
                "fallback_evaluation_source": str(policy.get("fallback_evaluation_source") or ""),
                "fallback_idempotency_key": str(policy.get("fallback_idempotency_key") or ""),
                "fallback_scene_index": _safe_int(by_scene[idx].get("fallback_scene_index"), policy["fallback_scene_index"]),
                "source_of_truth": current_source_of_truth,
                "actual_provider_payload_status": policy.get("actual_provider_payload_status") or by_scene[idx].get("actual_provider_payload_status") or "",
                "state_authority_source": policy.get("state_authority_source") or by_scene[idx].get("state_authority_source") or "",
                "authoritative_status_source": policy.get("authoritative_status_source") or by_scene[idx].get("authoritative_status_source") or "",
                "historical_status_ignored": bool(policy.get("historical_status_ignored") or by_scene[idx].get("historical_status_ignored")),
                "success_result_overrode_stale_not_start": bool(policy.get("success_result_overrode_stale_not_start") or by_scene[idx].get("success_result_overrode_stale_not_start")),
                "provider_status_conflict": bool(policy.get("provider_status_conflict") or by_scene[idx].get("provider_status_conflict")),
                "provider_status_conflict_resolution": policy.get("provider_status_conflict_resolution") or by_scene[idx].get("provider_status_conflict_resolution") or "",
                "result_processing_action": policy.get("result_processing_action") or by_scene[idx].get("result_processing_action") or "",
                "stale_not_start_blocker_ignored": bool(policy.get("stale_not_start_blocker_ignored") or by_scene[idx].get("stale_not_start_blocker_ignored")),
                "not_start_decision_source": policy.get("not_start_decision_source") or by_scene[idx].get("not_start_decision_source") or "",
                "provider_progress_authoritative": bool(policy.get("provider_progress_authoritative") or by_scene[idx].get("provider_progress_authoritative")),
                **winner,
            }
        )
        if winner.get("winner_valid"):
            winning_candidate = next(
                (item for item in own_candidates if str(item.get("task_id") or "") == str(winner.get("scene_winner_task") or "")),
                {},
            )
            by_scene[idx]["clip_valid"] = True
            by_scene[idx]["clip_bytes"] = max(
                _safe_int(by_scene[idx].get("clip_bytes"), 0),
                _safe_int(winning_candidate.get("artifact_size"), 0),
            )
            by_scene[idx]["clip_path"] = str(winning_candidate.get("output_path") or by_scene[idx].get("clip_path") or "")
            by_scene[idx]["status"] = "scene_clip_validated"
            by_scene[idx]["progress"] = 100
        if by_scene[idx]["provider_stalled_not_start"]:
            by_scene[idx]["status"] = PRODUCT_VIDEO_PROVIDER_STALLED_NOT_START
        owned_task = str(
            by_scene[idx].get("winning_task_id")
            or by_scene[idx].get("active_task_id")
            or by_scene[idx].get("primary_task_id")
            or by_scene[idx].get("provider_task_id")
            or by_scene[idx].get("task_id")
            or by_scene[idx].get("provider_video_id")
            or by_scene[idx].get("video_id")
            or ""
        ).strip()
        if owned_task:
            by_scene[idx]["task_scene_mapping_verified"] = True
            if by_scene[idx].get("result_url_valid"):
                by_scene[idx]["result_task_id"] = str(by_scene[idx].get("result_task_id") or owned_task)
        else:
            had_phantom_result = bool(by_scene[idx].get("result_url_valid") or by_scene[idx].get("result_url"))
            validated_local_clip = bool(
                by_scene[idx].get("clip_valid")
                and (
                    _safe_int(by_scene[idx].get("clip_bytes"), 0) > 0
                    or bool(str(by_scene[idx].get("clip_path") or "").strip())
                )
            )
            by_scene[idx]["result_url_valid"] = False
            by_scene[idx]["result_url"] = ""
            by_scene[idx]["result_task_id"] = ""
            by_scene[idx]["result_url_source"] = ""
            by_scene[idx]["task_scene_mapping_verified"] = False
            by_scene[idx]["clip_valid"] = validated_local_clip
            by_scene[idx]["result_processing_action"] = ""
            by_scene[idx]["phantom_result_prevented"] = bool(
                by_scene[idx].get("phantom_result_prevented") or had_phantom_result
            )
    return [by_scene[idx] for idx in sorted(by_scene)]


def product_video_scene_execution_audit(
    job: dict | None = None,
    scene_tasks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    job = dict(job or {})
    tasks = [dict(item or {}) for item in (scene_tasks or product_video_scene_tasks_debug(job)) if isinstance(item, dict)]
    scene_rows: list[dict[str, Any]] = []
    stalled_count = 0
    missing_task_count = 0
    missing_task_after_attempt_count = 0
    dispatch_pending_count = 0
    fallback_allowed_count = 0
    fallback_evaluated_count = 0
    result_count = 0
    for item in tasks:
        scene_index = _scene_task_index(item)
        task_id = str(
            item.get("provider_task_id")
            or item.get("task_id")
            or item.get("canonical_task_selected")
            or item.get("provider_video_id")
            or item.get("video_id")
            or ""
        ).strip()
        actual_status, _actual_source, _raw_before = _actual_status_payload_value(item)
        actual_status = str(actual_status or item.get("provider_status_raw") or item.get("status") or "").strip().upper()
        policy = product_video_scene_stall_policy(job, item, scene_index)
        result_available = bool(
            item.get("result_url_valid")
            or item.get("provider_result_url_present")
            or item.get("download_url_present")
            or item.get("clip_valid")
            or _safe_int(item.get("artifact_size") or item.get("artifact_bytes") or item.get("output_bytes"), 0) > 0
        )
        stalled = bool(policy.get("provider_scene_stalled"))
        fallback_allowed = bool(policy.get("fallback_allowed"))
        fallback_evaluated = bool(policy.get("fallback_evaluated"))
        dispatch_attempted = bool(
            item.get("dispatch_attempted")
            or item.get("scene_dispatch_attempted")
            or item.get("provider_submit_called")
            or _safe_int(item.get("submit_invoked_count"), 0) > 0
            or _safe_int(item.get("submit_attempt_count"), 0) > 0
        )
        dispatch_state = str(
            item.get("dispatch_state")
            or item.get("scene_dispatch_state")
            or item.get("status")
            or ""
        ).strip().lower()
        dispatch_pending = bool(
            not task_id
            and not dispatch_attempted
            and dispatch_state
            in {
                "queued",
                "pending",
                "queued_waiting_for_dispatch",
                "queued_waiting_for_slot",
                "submit_in_progress",
            }
        )
        stalled_count += int(stalled)
        missing_task_count += int(not bool(task_id))
        missing_task_after_attempt_count += int(not bool(task_id) and not dispatch_pending)
        dispatch_pending_count += int(dispatch_pending)
        fallback_allowed_count += int(fallback_allowed)
        fallback_evaluated_count += int(fallback_evaluated)
        result_count += int(result_available)
        scene_rows.append(
            {
                "scene_index": scene_index,
                "task_id_masked": _task_id_masked(task_id),
                "submit_accepted": bool(item.get("submit_accepted") or task_id),
                "submit_http_status": _safe_int(item.get("submit_http_status") or item.get("provider_submit_http_status"), 0),
                "actual_status": actual_status,
                "progress": _safe_int(item.get("provider_progress_normalized") or item.get("provider_progress_raw"), 0),
                "progress_last_changed_at": str(item.get("provider_progress_last_changed_at") or policy.get("provider_progress_last_changed_at") or ""),
                "progress_last_changed_elapsed_seconds": _safe_int(
                    item.get("provider_progress_last_changed_elapsed_seconds") or policy.get("in_progress_stall_elapsed"),
                    0,
                ),
                "elapsed_seconds": max(
                    _safe_int(item.get("provider_elapsed_seconds"), 0),
                    _safe_int(policy.get("provider_elapsed_seconds"), 0),
                ),
                "result_available": result_available,
                "fallback_evaluated": fallback_evaluated,
                "fallback_allowed": fallback_allowed,
                "fallback_blocked_reason": str(policy.get("fallback_block_reason") or ""),
                "fallback_provider_candidate": str(policy.get("fallback_provider_candidate") or ""),
                "fallback_idempotency_key": str(policy.get("fallback_idempotency_key") or ""),
                "provider_in_progress_stalled": bool(policy.get("provider_in_progress_stalled")),
                "provider_stalled_not_start": bool(policy.get("provider_stalled_not_start")),
                "scene_winner_task": str(item.get("scene_winner_task_masked") or _task_id_masked(str(item.get("scene_winner_task") or ""))),
                "scene_winner_provider": str(item.get("scene_winner_provider") or ""),
                "winner_selected_at": str(item.get("winner_selected_at") or ""),
                "late_result_ignored": list(item.get("late_result_ignored_masked") or []),
                "duplicate_scene_result_prevented": bool(item.get("duplicate_scene_result_prevented")),
            }
        )
    scene_count = max(_scene_count(job), len(tasks))
    unresolved_count = max(0, scene_count - result_count)
    all_unresolved_stalled = bool(unresolved_count > 0 and stalled_count >= unresolved_count)
    if missing_task_after_attempt_count > 0 and fallback_allowed_count == 0:
        terminal_reason = "scene_submit_missing_no_charge"
    elif all_unresolved_stalled and fallback_allowed_count == 0:
        terminal_reason = "all_scene_providers_exhausted_no_charge"
    elif fallback_allowed_count > 0:
        terminal_reason = "fallback_available_for_stalled_scenes"
    else:
        terminal_reason = ""
    root_cause = ""
    if any(item.get("provider_in_progress_stalled") for item in scene_rows):
        root_cause = "provider_in_progress_stall"
    elif any(item.get("provider_stalled_not_start") for item in scene_rows):
        root_cause = "provider_not_start_stall"
    elif missing_task_after_attempt_count:
        root_cause = "scene_submit_missing"
    elif dispatch_pending_count:
        root_cause = "scene_dispatch_pending"
    continue_polling = bool(not terminal_reason or terminal_reason == "fallback_available_for_stalled_scenes")
    return {
        "job_id": _safe_int(job.get("job_id") or job.get("id"), 0),
        "scene_count": scene_count,
        "scenes": scene_rows,
        "root_cause": root_cause,
        "fallback_evaluated_count": fallback_evaluated_count,
        "fallback_allowed_count": fallback_allowed_count,
        "missing_task_count": missing_task_count,
        "missing_task_after_attempt_count": missing_task_after_attempt_count,
        "dispatch_pending_count": dispatch_pending_count,
        "result_available_count": result_count,
        "terminal_reason": terminal_reason,
        "continue_polling": continue_polling,
        "wallet_charge": _safe_int(job.get("charged_xu") or job.get("wallet_charge_amount_xu") or job.get("charge"), 0),
    }


def _invoice_payload(job: dict | None = None) -> dict:
    job = dict(job or {})
    candidates = [
        job.get("invoice_json"),
        job.get("invoice"),
        (job.get("project") or {}).get("invoice_json") if isinstance(job.get("project"), dict) else "",
    ]
    for candidate in candidates:
        parsed = _json_loads(candidate, {})
        if isinstance(parsed, dict) and parsed:
            return parsed
    return {}


def product_video_expected_duration_seconds(job: dict | None = None) -> int:
    job = dict(job or {})
    invoice = _invoice_payload(job)
    scene_count = _safe_int(job.get("scene_count") or invoice.get("scene_count"), _scene_count(job))
    if product_video_orchestration_mode(job) == PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE_8S:
        return max(1, min(20, scene_count)) * product_video_scene_duration_seconds(job)
    direct = _safe_int(
        job.get("expected_duration_seconds")
        or job.get("duration_seconds")
        or invoice.get("duration_seconds"),
        0,
    )
    if direct > 0:
        return direct
    scene_seconds = _safe_int(job.get("scene_seconds") or invoice.get("scene_seconds"), PRODUCT_VIDEO_SCENE_SECONDS)
    return max(1, min(20, scene_count)) * max(1, scene_seconds)


def product_video_duration_contract(job: dict | None, duration_seconds: float | int | None) -> dict[str, Any]:
    expected = product_video_expected_duration_seconds(job)
    actual = float(duration_seconds or 0)
    ok = actual + PRODUCT_VIDEO_DURATION_TOLERANCE_SECONDS >= float(expected)
    return {
        "ok": bool(ok),
        "expected_duration_seconds": expected,
        "actual_duration_seconds": actual,
        "duration_tolerance_seconds": PRODUCT_VIDEO_DURATION_TOLERANCE_SECONDS,
        "reason": "" if ok else "final_duration_short_scene_coverage_missing",
    }


def finalize_recovered_product_video_artifact(
    job: dict | None,
    project: dict | None,
    artifact_path: str,
    *,
    workspace: str = "",
) -> dict[str, Any]:
    """Validate and normalize a recovered one-scene provider MP4 before delivery."""
    job_context = dict(job or {})
    project_context = dict(project or {})
    if project_context:
        job_context["project"] = project_context
        job_context.setdefault("scene_count", project_context.get("scene_count"))
        job_context.setdefault("invoice_json", project_context.get("invoice_json"))
    scene_count = _scene_count(job_context)
    expected = product_video_expected_duration_seconds(job_context)
    raw_path = str(artifact_path or "").strip()
    raw_probe = video_final_output.probe_video(raw_path)
    base = {
        "ok": False,
        "delivery_allowed": False,
        "raw_provider_video_path": raw_path,
        "raw_duration_seconds": float(raw_probe.get("duration") or 0),
        "raw_output_bytes": int(raw_probe.get("bytes") or 0),
        "expected_duration_seconds": int(expected),
        "scene_count": int(scene_count),
        "recovery_duration_normalized": False,
    }
    if scene_count != 1:
        return {**base, "reason": "multiscene_recovery_requires_scene_orchestrator"}
    if not raw_probe.get("ok"):
        return {**base, "reason": str(raw_probe.get("reason") or "recovered_artifact_invalid")}

    raw_contract = product_video_duration_contract(job_context, raw_probe.get("duration"))
    if raw_contract.get("ok"):
        return {
            **base,
            "ok": True,
            "delivery_allowed": True,
            "reason": "",
            "final_video_path": raw_path,
            "output_bytes": int(raw_probe.get("bytes") or 0),
            "final_duration_seconds": float(raw_probe.get("duration") or 0),
            "has_video": bool(raw_probe.get("has_video")),
            "has_audio": bool(raw_probe.get("has_audio")),
            "final_duration_contract": raw_contract,
        }
    if raw_probe.get("has_audio"):
        return {**base, "reason": "recovered_audio_duration_normalization_requires_worker"}

    output_dir = os.path.abspath(workspace or os.path.dirname(raw_path) or ".")
    os.makedirs(output_dir, exist_ok=True)
    stem = Path(raw_path).stem or "recovered_provider"
    finalized_path = os.path.join(output_dir, f"{stem}.finalized.mp4")
    try:
        normalize_scene_duration(raw_path, finalized_path, float(expected))
    except Exception as exc:
        return {
            **base,
            "reason": str(exc)[:160] or "recovered_duration_normalization_failed",
            "normalization_exception": type(exc).__name__,
        }

    final_probe = video_final_output.probe_video(finalized_path)
    final_contract = product_video_duration_contract(job_context, final_probe.get("duration"))
    if not final_probe.get("ok") or not final_contract.get("ok"):
        return {
            **base,
            "reason": str(final_probe.get("reason") or final_contract.get("reason") or "recovered_final_artifact_invalid"),
            "final_video_path": finalized_path,
            "final_duration_seconds": float(final_probe.get("duration") or 0),
            "final_duration_contract": final_contract,
        }
    return {
        **base,
        "ok": True,
        "delivery_allowed": True,
        "reason": "",
        "final_video_path": finalized_path,
        "output_bytes": int(final_probe.get("bytes") or 0),
        "final_duration_seconds": float(final_probe.get("duration") or 0),
        "has_video": bool(final_probe.get("has_video")),
        "has_audio": bool(final_probe.get("has_audio")),
        "recovery_duration_normalized": True,
        "final_duration_contract": final_contract,
    }


def _asset_pack_payload(job: dict | None = None) -> dict:
    job = dict(job or {})
    candidates = [
        job.get("asset_pack"),
        job.get("asset_pack_json"),
        (job.get("project") or {}).get("asset_pack_json") if isinstance(job.get("project"), dict) else "",
    ]
    for candidate in candidates:
        parsed = _json_loads(candidate, {})
        if isinstance(parsed, dict) and parsed:
            return parsed
    return {}


def product_video_logo_material(job: dict | None = None) -> dict:
    asset_pack = _asset_pack_payload(job)
    material = asset_pack.get("logo_material") if isinstance(asset_pack, dict) else {}
    if not isinstance(material, dict):
        return {}
    enabled = bool(material.get("logo_enabled"))
    if not enabled:
        return {}
    position = str(material.get("logo_position") or "top_right").strip().lower()
    if position not in {
        "top_left", "top_center", "top_right",
        "center_left", "center", "center_right",
        "bottom_left", "bottom_center", "bottom_right",
    }:
        position = "top_right"
    return {
        "logo_enabled": True,
        "logo_file_id": str(material.get("logo_file_id") or ""),
        "logo_path": str(material.get("logo_path") or material.get("path") or ""),
        "logo_position": position,
        "logo_width_ratio": float(material.get("logo_width_ratio") or PRODUCT_VIDEO_LOGO_DEFAULT_WIDTH_RATIO),
        "logo_max_width_ratio": float(material.get("logo_max_width_ratio") or PRODUCT_VIDEO_LOGO_MAX_WIDTH_RATIO),
        "logo_margin_x_ratio": float(material.get("logo_margin_x_ratio") or PRODUCT_VIDEO_LOGO_MARGIN_X_RATIO),
        "logo_margin_y_ratio": float(material.get("logo_margin_y_ratio") or PRODUCT_VIDEO_LOGO_MARGIN_Y_RATIO),
        "logo_preserve_aspect_ratio": bool(material.get("logo_preserve_aspect_ratio", True)),
    }


def _product_type(job: dict | None = None) -> str:
    job = dict(job or {})
    project = dict(job.get("project") or {})
    if not project and job.get("asset_pack"):
        project = {"asset_pack_json": job.get("asset_pack")}
    product_type = video_final_output.product_type_from_project(project, job)
    return video_final_output.normalize_video_product_type(product_type)


def product_video_required_capability(job: dict | None = None) -> str:
    """Resolve provider capability from the immutable product engine contract."""

    product_type = _product_type(job)
    contract = video_project_queue_service.product_video_engine_contract(product_type)
    capability = str(contract.get("required_capability") or "").strip()
    if capability:
        return capability
    route = video_final_output.route_for_product_type(product_type)
    return str(route.get("provider_capability") or "text_to_video").strip()


def _local_image_sequence_paths(job: dict | None = None) -> list[str]:
    return video_final_output.extract_local_image_paths(job or {})


def storyboard_scene_image_paths(job: dict | None = None, scene_index: int = 1) -> list[str]:
    """Return only the approved image inputs belonging to one storyboard scene."""

    target_index = max(1, _safe_int(scene_index, 1))
    cards = _scene_cards(job)
    for fallback_index, card in enumerate(cards, start=1):
        card_index = max(1, _safe_int(card.get("scene_index") or card.get("scene_id"), fallback_index))
        if card_index != target_index:
            continue
        paths = video_final_output.extract_local_image_paths(card, limit=2)
        if paths:
            return paths
    all_paths = _local_image_sequence_paths(job)
    if target_index <= len(all_paths):
        return [all_paths[target_index - 1]]
    return []


def product_video_scene_image_paths(job: dict | None = None, scene_index: int = 1) -> list[str]:
    product_type = _product_type(job)
    if product_type in PRODUCT_VIDEO_SCENE_IMAGE_INPUT_TYPES:
        return storyboard_scene_image_paths(job, scene_index)
    return _local_image_sequence_paths(job)


def _local_image_sequence_allowed(job: dict | None = None, paths: list[str] | None = None) -> bool:
    if not paths:
        return False
    product_type = _product_type(job)
    if product_type in LOCAL_IMAGE_SEQUENCE_PRODUCT_TYPES:
        return True
    route = video_final_output.route_for_product_type(product_type)
    return str(route.get("engine_family") or "") in {"image_sequence", "storyboard"} and product_type not in {"video_ai_image"}


def _local_scene_card_allowed(job: dict | None = None) -> bool:
    """Allow local final MP4 only for products whose canonical output is scenes."""
    product_type = _product_type(job)
    if product_type in LOCAL_SCENE_CARD_PRODUCT_TYPES:
        return True
    if product_type == "video_trend":
        return bool(_scene_cards(job))
    return False


def _local_addon_audio_path(job: dict | None = None) -> str:
    addon = _addon_plan(job)
    candidates = [
        addon.get("music_path"),
        addon.get("music_audio_path"),
        addon.get("bgm_audio_path"),
        addon.get("voice_path"),
        addon.get("voice_audio_path"),
        addon.get("audio_path"),
    ]
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text and os.path.isfile(text) and os.path.getsize(text) > 0:
            return text
    return ""


def _aspect_ratio(job: dict | None = None) -> str:
    job = dict(job or {})
    value = job.get("aspect_ratio") or job.get("ratio")
    if not value and isinstance(job.get("project"), dict):
        value = (job.get("project") or {}).get("ratio")
    text = str(value or "9:16").strip()
    return text if re.match(r"^\d{1,2}:\d{1,2}$", text) else "9:16"


def _soft_prompt(base_prompt: str, scene_index: int, scene_count: int, aspect_ratio: str, style: str = "") -> str:
    base = _safe_text(base_prompt, 900)
    stage = {
        1: "opening establishing shot with the clearest subject and mood",
        2: "detail/action shot showing benefit, texture, motion, and context",
        3: "closing hero shot with satisfying payoff and polished composition",
    }.get(scene_index, "continuation shot with a new angle and clear visual progression")
    style_text = _safe_text(style, 220)
    return (
        f"Vertical {aspect_ratio} cinematic video scene {scene_index}/{scene_count}. "
        f"User intent: {base}. "
        f"Scene direction: {stage}. "
        f"{style_text + '. ' if style_text else ''}"
        "Natural camera movement, realistic lighting, coherent continuity with previous scenes, "
        "professional commercial quality, no fake logo, no extra text, no watermark, no subtitles."
    )[:1200]


def real_video_scene_plan(job: dict | None = None) -> dict:
    job = dict(job or {})
    count = _scene_count(job)
    aspect_ratio = _aspect_ratio(job)
    orchestration_mode = product_video_orchestration_mode(job)
    if orchestration_mode == PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE_8S:
        default_duration = float(product_video_scene_duration_seconds(job))
    else:
        total_duration = _safe_int(job.get("expected_duration_seconds") or job.get("duration_seconds"), 0)
        if total_duration <= 0:
            total_duration = product_video_expected_duration_seconds(job)
        default_duration = max(1.0, min(8.0, float(total_duration) / max(1, count)))
    original = original_prompt_from_job(job)
    style = _safe_text(job.get("profile_id") or "", 120)
    cards = _scene_cards(job)
    scenes = []
    for index in range(1, count + 1):
        card = cards[index - 1] if index - 1 < len(cards) else {}
        prompt = _safe_text(
            card.get("provider_prompt")
            or card.get("video_prompt")
            or card.get("visual_goal")
            or card.get("image_prompt"),
            1200,
        )
        if not prompt:
            prompt = _soft_prompt(original, index, count, aspect_ratio, style)
        elif original and original.lower() not in prompt.lower():
            prompt = f"{prompt} User intent to preserve: {original}"[:1200]
        scenes.append(
            {
                "scene_id": index,
                "title": _safe_text(card.get("title") or card.get("role") or f"Scene {index}", 120),
                "visual_prompt": _safe_text(card.get("visual_goal") or card.get("image_prompt") or prompt, 1200),
                "video_prompt": prompt,
                "narration_text": _safe_text(card.get("narration_line") or card.get("script_text") or card.get("subtitle_line") or "", 1000) or None,
                "target_duration_sec": default_duration,
                "aspect_ratio": aspect_ratio,
                "transition": None if index == count else "cut",
                "provider_params": {
                    "real_provider": True,
                    "original_user_prompt": original,
                    "orchestration_mode": orchestration_mode,
                    "scene_duration_seconds": default_duration,
                    "scene_index": index,
                    "scene_count": count,
                },
            }
        )
    return {
        "orchestration_mode": orchestration_mode,
        "scene_duration_seconds": default_duration,
        "expected_duration_seconds": product_video_expected_duration_seconds(job),
        "scene_count": count,
        "scenes": scenes,
    }


def real_video_llm_func_from_job(job: dict | None = None):
    plan = real_video_scene_plan(job)

    def _llm_func(*_args, **_kwargs):
        return plan

    return _llm_func


def _join_url(base: str, path: str) -> str:
    base = str(base or "").strip().rstrip("/")
    path = str(path or "").strip()
    if path.startswith(("http://", "https://")):
        return path
    return base + "/" + path.lstrip("/")


def _video_payload_data(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _extract_task_id(payload: dict) -> str:
    data = _video_payload_data(payload)
    for value in (data.get("task_id"), data.get("taskId"), data.get("id"), payload.get("task_id"), payload.get("id")):
        text = str(value or "").strip()
        if text:
            return text[:180]
    return ""


def _extract_output_url(payload: dict) -> str:
    data = _video_payload_data(payload)
    candidates = [
        data.get("result_url"),
        data.get("video_url"),
        data.get("output_url"),
        data.get("url"),
        payload.get("result_url"),
        payload.get("video_url"),
        payload.get("output_url"),
        payload.get("url"),
    ]
    nested = data.get("result") if isinstance(data.get("result"), dict) else {}
    candidates.extend([nested.get("result_url"), nested.get("video_url"), nested.get("url")])
    for value in candidates:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _normalized_status(payload: dict) -> str:
    data = _video_payload_data(payload)
    raw = str(data.get("status") or payload.get("status") or payload.get("code") or "").strip().upper()
    if raw in {"SUCCESS", "SUCCEEDED", "COMPLETED", "DONE", "FINISHED"}:
        return "SUCCESS"
    if raw in {"FAIL", "FAILED", "FAILURE", "ERROR", "CANCELLED", "CANCELED"}:
        return "FAILED"
    if raw in {"QUEUED", "PENDING", "SUBMITTED", "PROCESSING", "IN_PROGRESS", "RUNNING", "STARTED", "GENERATING"}:
        return "IN_PROGRESS"
    return raw or "UNKNOWN"


async def _submit_shopaikey(prompt: str, aspect_ratio: str) -> dict:
    api_key = str(os.environ.get("SHOPAIKEY_API_KEY") or "").strip()
    url = str(os.environ.get("SHOPAIKEY_VIDEO_URL") or "").strip()
    if not url:
        base = str(os.environ.get("SHOPAIKEY_BASE_URL") or "").strip()
        endpoint = str(os.environ.get("SHOPAIKEY_VIDEO_ENDPOINT") or "/video/generations").strip()
        url = _join_url(base, endpoint) if base else ""
    model = str(os.environ.get("SHOPAIKEY_VIDEO_MODEL") or os.environ.get("SHOPAIKEY_VIDEO_MODEL_PRIMARY") or "veo3.1-fast").strip()
    if not api_key or not url or not model:
        return {"ok": False, "provider": "shopaikey", "error": "shopaikey_video_config_missing"}
    payload = {
        "model": model,
        "prompt": _safe_text(prompt, 1200),
        "metadata": {"aspect_ratio": aspect_ratio, "enhance_prompt": False, "enable_upsample": False},
    }
    async with httpx.AsyncClient(timeout=float(_env_int("REAL_VIDEO_SUBMIT_TIMEOUT_SECONDS", 60))) as client:
        response = await client.post(url, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json=payload)
    try:
        data = response.json()
    except Exception:
        data = {}
    task_id = _extract_task_id(data)
    if response.status_code < 400 and task_id:
        return {"ok": True, "provider": "shopaikey", "task_id": task_id, "model": model}
    return {"ok": False, "provider": "shopaikey", "error": f"shopaikey_submit_failed:{response.status_code}"}


async def _poll_shopaikey(task_id: str) -> dict:
    api_key = str(os.environ.get("SHOPAIKEY_API_KEY") or "").strip()
    submit_url = str(os.environ.get("SHOPAIKEY_VIDEO_URL") or "").strip()
    status_endpoint = str(os.environ.get("SHOPAIKEY_VIDEO_STATUS_ENDPOINT") or "").strip()
    if status_endpoint:
        if "{task_id}" in status_endpoint:
            url = status_endpoint.replace("{task_id}", task_id)
        elif "{id}" in status_endpoint:
            url = status_endpoint.replace("{id}", task_id)
        else:
            url = status_endpoint.rstrip("/") + "/" + task_id
    else:
        url = submit_url.rstrip("/") + "/" + task_id
    if not api_key or not url:
        return {"ok": False, "provider": "shopaikey", "error": "shopaikey_status_config_missing"}
    async with httpx.AsyncClient(timeout=float(_env_int("REAL_VIDEO_POLL_TIMEOUT_SECONDS", 45))) as client:
        response = await client.get(url, headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"})
    try:
        data = response.json()
    except Exception:
        data = {}
    output_url = _extract_output_url(data)
    status = _normalized_status(data)
    return {"ok": bool(response.status_code < 400), "provider": "shopaikey", "status": status, "output_url": output_url, "http_status": response.status_code}


async def _submit_key4u(prompt: str, aspect_ratio: str) -> dict:
    try:
        from providers.key4u_provider import Key4UProvider
    except Exception as exc:
        return {"ok": False, "provider": "key4u", "error": f"key4u_import_failed:{type(exc).__name__}"}
    provider = Key4UProvider()
    if not provider.is_configured():
        return {"ok": False, "provider": "key4u", "error": "key4u_video_config_missing"}
    result = await provider.video_generation(
        prompt=prompt,
        model=str(os.environ.get("KEY4U_VIDEO_MODEL") or os.environ.get("KEY4U_DEFAULT_VIDEO_MODEL") or ""),
        timeout_seconds=float(_env_int("REAL_VIDEO_SUBMIT_TIMEOUT_SECONDS", 60)),
        aspect_ratio=aspect_ratio,
    )
    task_id = str(result.get("task_id") or "").strip()
    if result.get("ok") and task_id:
        return {"ok": True, "provider": "key4u", "task_id": task_id, "model": result.get("model") or ""}
    return {"ok": False, "provider": "key4u", "error": str(result.get("error_class") or result.get("status") or "key4u_submit_failed")}


async def _poll_key4u(task_id: str) -> dict:
    from providers.key4u_provider import Key4UProvider

    result = await Key4UProvider().poll_video_task(task_id, timeout_seconds=float(_env_int("REAL_VIDEO_POLL_TIMEOUT_SECONDS", 45)))
    output_url = str(result.get("output_url") or result.get("result_url") or "").strip()
    status = str(result.get("status") or "").upper()
    if output_url:
        status = "SUCCESS"
    elif status not in {"SUCCESS", "FAILED", "FAIL", "ERROR"}:
        status = "IN_PROGRESS"
    return {"ok": bool(result.get("ok") or output_url), "provider": "key4u", "status": status, "output_url": output_url, "http_status": result.get("http_status") or 0}


async def _submit_gommo(prompt: str, aspect_ratio: str, duration_seconds: float = 6.0) -> dict:
    try:
        from providers.gommo_79ai_provider import Gommo79AIProvider
    except Exception as exc:
        return {"ok": False, "provider": "gommo_79ai", "error": f"gommo_import_failed:{type(exc).__name__}"}
    provider = Gommo79AIProvider()
    if not provider.is_ready():
        return {"ok": False, "provider": "gommo_79ai", "error": "gommo_video_config_missing"}
    plan = await asyncio.to_thread(
        provider.pick_video_model,
        package="basic",
        scenes=1,
        duration=max(1, int(round(float(duration_seconds or 6.0)))),
        aspect_ratio=aspect_ratio,
        references={},
    )
    if not plan.get("ok"):
        return {"ok": False, "provider": "gommo_79ai", "error": str(plan.get("error") or "gommo_model_unavailable")}
    result = await asyncio.to_thread(
        provider.create_video,
        prompt=_safe_text(prompt, 1800),
        model=str(plan.get("model") or ""),
        ratio=str(plan.get("ratio") or aspect_ratio),
        resolution=str(plan.get("resolution") or "720p"),
        duration=int(plan.get("duration") or 6),
        mode=str(plan.get("mode") or "business_fast"),
        count_tasks=1,
        references={},
    )
    if result.get("ok") and (result.get("video_id") or result.get("task_id")):
        video_id = str(result.get("video_id") or result.get("task_id") or "").strip()
        task_id = str(result.get("task_id") or video_id).strip()
        return {
            "ok": True,
            "provider": "gommo_79ai",
            "video_id": video_id,
            "task_id": task_id,
            "status": str(result.get("status") or "IN_PROGRESS"),
            "download_url": str(result.get("download_url") or ""),
            "model": str(result.get("model") or plan.get("model") or ""),
            "mode": str(result.get("mode") or plan.get("mode") or ""),
            "ratio": str(result.get("ratio") or plan.get("ratio") or aspect_ratio),
            "resolution": str(result.get("resolution") or plan.get("resolution") or ""),
            "duration": int(result.get("duration") or plan.get("duration") or 6),
            "credit_fee": int(result.get("credit_fee") or 0),
        }
    return {"ok": False, "provider": "gommo_79ai", "error": str(result.get("error") or "gommo_create_video_failed")}


async def _poll_gommo(video_id: str) -> dict:
    try:
        from providers.gommo_79ai_provider import Gommo79AIProvider
    except Exception as exc:
        return {"ok": False, "provider": "gommo_79ai", "status": "FAILED", "error": f"gommo_import_failed:{type(exc).__name__}"}
    provider = Gommo79AIProvider()
    if not provider.is_ready():
        return {"ok": False, "provider": "gommo_79ai", "status": "FAILED", "error": "gommo_video_config_missing"}
    result = await asyncio.to_thread(
        provider.poll_video_until_ready,
        str(video_id or ""),
        max_attempts=max(1, _env_int("GOMMO_POLL_MAX_ATTEMPTS", _env_int("REAL_VIDEO_POLL_MAX_ATTEMPTS", 24))),
        interval_seconds=max(0, _env_int("GOMMO_POLL_INTERVAL_SECONDS", _env_int("REAL_VIDEO_POLL_INTERVAL_SECONDS", 25))),
        success_url_extra_attempts=max(0, _env_int("GOMMO_SUCCESS_URL_EXTRA_POLLS", 4)),
    )
    status = str(result.get("status") or "").upper()
    if result.get("download_url"):
        status = "SUCCESS"
    elif result.get("timeout"):
        status = "IN_PROGRESS"
    return {
        "ok": bool(result.get("ok", True)),
        "provider": "gommo_79ai",
        "status": status or "UNKNOWN",
        "output_url": str(result.get("download_url") or ""),
        "video_id": str(result.get("video_id") or video_id),
        "task_id": str(result.get("task_id") or video_id),
        "model": str(result.get("model") or ""),
        "mode": str(result.get("mode") or ""),
        "duration": int(result.get("duration") or 0),
        "credit_fee": int(result.get("credit_fee") or 0),
        "error": str(result.get("error") or ("poll_timeout" if result.get("timeout") else "")),
    }


async def _submit_provider(provider: str, prompt: str, aspect_ratio: str) -> dict:
    if provider == "shopaikey":
        return await _submit_shopaikey(prompt, aspect_ratio)
    if provider == "key4u":
        return await _submit_key4u(prompt, aspect_ratio)
    if provider == "gommo_79ai":
        return await _submit_gommo(prompt, aspect_ratio)
    return {"ok": False, "provider": provider, "error": "provider_unsupported"}


async def _poll_provider(provider: str, task_id: str, submit: dict | None = None) -> dict:
    if provider == "shopaikey":
        return await _poll_shopaikey(task_id)
    if provider == "key4u":
        return await _poll_key4u(task_id)
    if provider == "gommo_79ai":
        submit = dict(submit or {})
        return await _poll_gommo(str(submit.get("video_id") or task_id))
    return {"ok": False, "provider": provider, "status": "FAILED", "error": "provider_unsupported"}


def _download_output(source: str, destination: str) -> str:
    source = str(source or "").strip()
    target = os.path.abspath(destination)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if os.path.isfile(source):
        shutil.copyfile(source, target)
    elif source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=_env_int("REAL_VIDEO_DOWNLOAD_TIMEOUT_SECONDS", 180)) as response:
            with open(target, "wb") as handle:
                shutil.copyfileobj(response, handle)
    else:
        raise RealVideoRenderError("provider_output_url_missing")
    if not os.path.isfile(target) or os.path.getsize(target) <= 0:
        raise RealVideoRenderError("provider_output_empty")
    return target


def _selfshot3_prompt_payload(asset_pack: dict[str, Any], fallback_prompt: str, job: dict[str, Any]) -> tuple[str, str]:
    """Build the one-take prompt without falling back to text-only generation."""

    bundle = asset_pack.get("prompt_bundle") if isinstance(asset_pack.get("prompt_bundle"), dict) else {}
    stage_rows = bundle.get("stage_prompts") if isinstance(bundle, dict) else []
    stage_text = []
    for row in stage_rows if isinstance(stage_rows, list) else []:
        if isinstance(row, dict) and str(row.get("prompt") or "").strip():
            stage_text.append(str(row["prompt"]).strip())
    preset = asset_pack.get("transformation_preset") if isinstance(asset_pack.get("transformation_preset"), dict) else {}
    content = str(
        asset_pack.get("transformation_content")
        or preset.get("description")
        or (job or {}).get("topic")
        or fallback_prompt
        or "Biến đổi điện ảnh liên tục trong một cú máy"
    ).strip()
    sections = [content]
    if stage_text:
        sections.append("Timeline stages:\n" + "\n\n".join(stage_text))
    sections.append(
        "Preserve the source person's/object's identity, body proportions, original motion, "
        "camera continuity, contact points and audio timing. Apply only the approved wardrobe, "
        "world and subtle effects transformations. No cuts, no replacement subject, no identity drift."
    )
    prompt = "\n\n".join(part for part in sections if part)
    negative = str(
        bundle.get("negative_prompt")
        or "no face replacement, no identity drift, no duplicate subject, no abrupt cut, no temporal flicker"
    ).strip()
    return prompt[:12_000], negative[:8_000]


def _selfshot3_provider_configs(provider_order: list[str], duration_seconds: int) -> list[Any]:
    """Return only configured, contract-valid V2V providers in persisted order."""

    configured = video_ai_edit_provider.configured_provider_chain(os.environ)
    valid = []
    for config in configured:
        check = video_ai_edit_provider.validate_provider_config(config)
        contract = dict(check.get("contract") or {})
        max_seconds = _safe_int(contract.get("max_single_task_seconds"), 0)
        if not check.get("ok") or (max_seconds and duration_seconds > max_seconds):
            continue
        valid.append(config)
    aliases = {
        "key4u": "key4u_video",
        "shopaikey": "shopaikey_video",
        "generic_http": "generic_http",
    }
    ordered_names = [aliases.get(str(name).strip().lower(), str(name).strip().lower()) for name in provider_order if str(name).strip()]
    ordered = []
    for name in ordered_names:
        ordered.extend(item for item in valid if item.provider_name == name and item not in ordered)
    ordered.extend(item for item in valid if item not in ordered)
    return ordered


def _render_selfshot3_video_to_video(
    *,
    job: dict[str, Any],
    asset_pack: dict[str, Any],
    raw_path: str,
    provider_order: list[str],
    fallback_prompt: str,
    aspect_ratio: str,
) -> dict[str, Any]:
    """Render SELFSHOT3 through a real multipart video-to-video contract."""

    source_path = str((job or {}).get("source_video_local_path") or (job or {}).get("source_video_path") or "").strip()
    if not source_path or not os.path.isfile(source_path):
        raise RealVideoRenderError(
            "selfshot3_source_video_not_materialized",
            diagnostics={"ok": False, "selfshot3": True, "provider_attempted": False, "no_charge": True, "blocker": "selfshot3_source_video_not_materialized"},
        )
    source_path = os.path.abspath(source_path)
    if Path(source_path).suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm"}:
        raise RealVideoRenderError(
            "selfshot3_source_video_invalid",
            diagnostics={"ok": False, "selfshot3": True, "provider_attempted": False, "no_charge": True, "blocker": "selfshot3_source_video_invalid"},
        )
    confirmed = bool(
        asset_pack.get("public_user_confirmed")
        or asset_pack.get("b14_public_user_confirmed")
        or asset_pack.get("invoice_confirmed")
        or (job or {}).get("public_user_confirmed")
        or (job or {}).get("invoice_confirmed")
    )
    submit_source = str(asset_pack.get("submit_source") or (job or {}).get("submit_source") or "").strip()
    if not confirmed or submit_source not in {"public_user_final_confirm", video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE}:
        raise RealVideoRenderError(
            "selfshot3_public_confirm_required",
            diagnostics={"ok": False, "selfshot3": True, "provider_attempted": False, "no_charge": True, "blocker": "selfshot3_public_confirm_required"},
        )
    segment = dict(asset_pack.get("source_segment") or {})
    duration_seconds = _safe_int((segment.get("duration_ms") or 0) / 1000, 0)
    if duration_seconds <= 0:
        duration_seconds = _safe_int(asset_pack.get("duration_seconds") or (job or {}).get("duration_seconds"), 1)
    duration_seconds = max(1, duration_seconds)
    configs = _selfshot3_provider_configs(provider_order, duration_seconds)
    if not configs:
        raise RealVideoRenderError(
            "selfshot3_video_to_video_provider_unavailable",
            diagnostics={"ok": False, "selfshot3": True, "provider_attempted": False, "no_charge": True, "blocker": "selfshot3_video_to_video_provider_unavailable"},
        )
    prompt, negative = _selfshot3_prompt_payload(asset_pack, fallback_prompt, job)
    job_id = str((job or {}).get("job_id") or (job or {}).get("id") or "selfshot3")
    selected = configs[0]
    fallback = configs[1] if len(configs) > 1 else None
    attempts = []
    for index, config in enumerate((selected, fallback)):
        if config is None:
            break
        try:
            submitted = video_ai_edit_provider.submit_video_edit(
                config,
                source_video_path=source_path,
                prompt=prompt,
                negative_prompt=negative,
                aspect_ratio=aspect_ratio,
                duration_seconds=duration_seconds,
                job_id=job_id,
                submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
                public_user_confirmed=True,
            )
            task_id = str(submitted.get("provider_task_id") or "")
            result = dict(submitted)
            if not submitted.get("result_url_present"):
                result = video_ai_edit_provider.wait_for_result(config, task_id)
            result_url = str(result.get("result_url") or "").strip()
            if not result_url:
                raise video_ai_edit_provider.AiEditProviderError("provider_result_url_missing")
            downloaded = video_ai_edit_provider.download_result(result_url, raw_path)
            attempts.append({"provider": config.provider_name, "model": config.model, "task_id_present": bool(task_id), "fallback": bool(index)})
            return {
                "ok": True,
                "selfshot3": True,
                "provider_attempted": True,
                "provider": config.provider_name,
                "model": config.model,
                "provider_task_ids": [task_id] if task_id else [],
                "provider_video_ids": [],
                "result_url_present": True,
                "output_path": str(downloaded.get("path") or raw_path),
                "duration": duration_seconds,
                "scene_duration_seconds": duration_seconds,
                "clip_duration_seconds": duration_seconds,
                "expected_duration_seconds": duration_seconds,
                "engine_route": "direct_video_to_video",
                "selected_capability": "video_to_video",
                "source_uploaded_multipart": True,
                "fallback_used": bool(index),
                "fallback_count": int(index),
                "attempts": attempts,
                "no_charge": False,
            }
        except video_ai_edit_provider.AiEditProviderError as exc:
            attempts.append({"provider": config.provider_name, "model": config.model, "error": exc.reason, "fallback": bool(index)})
            if index == 0:
                decision = video_ai_edit_provider.controlled_fallback_decision(
                    public_confirm_provenance=True,
                    primary_status="timeout" if exc.reason == "provider_poll_timeout" else "failed",
                    primary_task_alive=False,
                    fallback_count=0,
                    candidate=fallback,
                )
                if not decision.get("allowed"):
                    raise RealVideoRenderError(exc.reason, diagnostics={"ok": False, "selfshot3": True, "provider_attempted": True, "attempts": attempts, "no_charge": True, "blocker": exc.reason}) from exc
                continue
            raise RealVideoRenderError(exc.reason, diagnostics={"ok": False, "selfshot3": True, "provider_attempted": True, "attempts": attempts, "no_charge": True, "blocker": exc.reason}) from exc
    raise RealVideoRenderError("selfshot3_video_to_video_failed", diagnostics={"ok": False, "selfshot3": True, "provider_attempted": bool(attempts), "attempts": attempts, "no_charge": True, "blocker": "selfshot3_video_to_video_failed"})


def _selfshot2_scene_source_segment(asset_pack: dict[str, Any], scene_index: int) -> dict[str, Any]:
    rows = asset_pack.get("scene_source_segments")
    if not isinstance(rows, list):
        rows = []
    selected = next(
        (
            dict(item)
            for item in rows
            if isinstance(item, dict) and _safe_int(item.get("scene_index"), 0) == scene_index
        ),
        {},
    )
    start_seconds = float(selected.get("start_seconds") or 0)
    end_seconds = float(selected.get("end_seconds") or 0)
    if start_seconds < 0 or end_seconds <= start_seconds:
        raise RealVideoRenderError(
            "selfshot2_scene_source_segment_invalid",
            diagnostics={
                "ok": False,
                "selfshot2": True,
                "scene_index": scene_index,
                "provider_attempted": False,
                "no_charge": True,
                "blocker": "selfshot2_scene_source_segment_invalid",
            },
        )
    return {
        "scene_index": scene_index,
        "start_seconds": start_seconds,
        "end_seconds": end_seconds,
        "duration_seconds": end_seconds - start_seconds,
    }


def _selfshot2_prompt_payload(
    asset_pack: dict[str, Any],
    *,
    scene_index: int,
    fallback_prompt: str,
) -> tuple[str, str]:
    rows = asset_pack.get("video_prompts")
    if not isinstance(rows, list):
        rows = []
    selected = next(
        (
            dict(item)
            for item in rows
            if isinstance(item, dict) and _safe_int(item.get("scene_index"), 0) == scene_index
        ),
        {},
    )
    prompt = str(selected.get("prompt") or fallback_prompt or "").strip()
    if not prompt:
        raise RealVideoRenderError(
            "selfshot2_scene_prompt_missing",
            diagnostics={
                "ok": False,
                "selfshot2": True,
                "scene_index": scene_index,
                "provider_attempted": False,
                "no_charge": True,
                "blocker": "selfshot2_scene_prompt_missing",
            },
        )
    negative = str(
        selected.get("negative_prompt")
        or "no identity drift, no body or product shape drift, no lost held object, "
        "no broken person-object contact, no unrelated subject, no slideshow"
    ).strip()
    return prompt[:12_000], negative[:8_000]


def _materialize_selfshot2_source_segment(
    source_path: str,
    raw_path: str,
    *,
    scene_index: int,
    start_seconds: float,
    duration_seconds: float,
) -> str:
    ffmpeg = _ffmpeg_binary()
    if not ffmpeg:
        raise RealVideoRenderError(
            "selfshot2_source_segment_ffmpeg_missing",
            diagnostics={
                "ok": False,
                "selfshot2": True,
                "scene_index": scene_index,
                "provider_attempted": False,
                "no_charge": True,
                "blocker": "selfshot2_source_segment_ffmpeg_missing",
            },
        )
    root = Path(os.path.dirname(os.path.abspath(raw_path))).resolve()
    target = (root / f"selfshot2-source-scene-{scene_index:02d}.mp4").resolve()
    if root not in target.parents:
        raise RealVideoRenderError("selfshot2_source_segment_path_unsafe")
    command = [
        ffmpeg,
        "-y",
        "-ss",
        f"{max(0.0, start_seconds):.3f}",
        "-i",
        os.path.abspath(source_path),
        "-t",
        f"{max(0.1, duration_seconds):.3f}",
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(target),
    ]
    result = safe_run_ffmpeg(command, timeout=max(90, int(duration_seconds * 30)))
    if result.returncode != 0 or not target.is_file() or target.stat().st_size <= 0:
        try:
            target.unlink(missing_ok=True)
        except Exception:
            pass
        raise RealVideoRenderError(
            "selfshot2_source_segment_materialization_failed",
            diagnostics={
                "ok": False,
                "selfshot2": True,
                "scene_index": scene_index,
                "provider_attempted": False,
                "no_charge": True,
                "blocker": "selfshot2_source_segment_materialization_failed",
                "ffmpeg_error": str(result.stderr or result.stdout or "")[-600:],
            },
        )
    return str(target)


def _render_selfshot2_video_to_video(
    *,
    job: dict[str, Any],
    asset_pack: dict[str, Any],
    raw_path: str,
    provider_order: list[str],
    fallback_prompt: str,
    aspect_ratio: str,
    scene_index: int,
) -> dict[str, Any]:
    """Render one source-bound SELFSHOT2 scene through a true V2V contract."""

    source_path = str((job or {}).get("source_video_local_path") or (job or {}).get("source_video_path") or "").strip()
    if not source_path or not os.path.isfile(source_path):
        raise RealVideoRenderError(
            "selfshot2_source_video_not_materialized",
            diagnostics={"ok": False, "selfshot2": True, "scene_index": scene_index, "provider_attempted": False, "no_charge": True, "blocker": "selfshot2_source_video_not_materialized"},
        )
    if Path(source_path).suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm"}:
        raise RealVideoRenderError(
            "selfshot2_source_video_invalid",
            diagnostics={"ok": False, "selfshot2": True, "scene_index": scene_index, "provider_attempted": False, "no_charge": True, "blocker": "selfshot2_source_video_invalid"},
        )
    confirmed = bool(
        asset_pack.get("public_user_confirmed")
        or asset_pack.get("b14_public_user_confirmed")
        or asset_pack.get("invoice_confirmed")
        or (job or {}).get("public_user_confirmed")
        or (job or {}).get("invoice_confirmed")
    )
    submit_source = str(asset_pack.get("submit_source") or (job or {}).get("submit_source") or "").strip()
    if not confirmed or submit_source not in {"public_user_final_confirm", video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE}:
        raise RealVideoRenderError(
            "selfshot2_public_confirm_required",
            diagnostics={"ok": False, "selfshot2": True, "scene_index": scene_index, "provider_attempted": False, "no_charge": True, "blocker": "selfshot2_public_confirm_required"},
        )
    segment = _selfshot2_scene_source_segment(asset_pack, scene_index)
    target_duration = max(1, _safe_int(asset_pack.get("scene_duration_seconds"), PRODUCT_VIDEO_SCENE_SECONDS))
    configs = _selfshot3_provider_configs(provider_order, target_duration)
    if not configs:
        raise RealVideoRenderError(
            "selfshot2_video_to_video_provider_unavailable",
            diagnostics={"ok": False, "selfshot2": True, "scene_index": scene_index, "provider_attempted": False, "no_charge": True, "blocker": "selfshot2_video_to_video_provider_unavailable"},
        )
    prompt, negative = _selfshot2_prompt_payload(
        asset_pack,
        scene_index=scene_index,
        fallback_prompt=fallback_prompt,
    )
    scene_source_path = _materialize_selfshot2_source_segment(
        source_path,
        raw_path,
        scene_index=scene_index,
        start_seconds=float(segment["start_seconds"]),
        duration_seconds=float(segment["duration_seconds"]),
    )
    job_id = str((job or {}).get("job_id") or (job or {}).get("id") or "selfshot2")
    selected = configs[0]
    fallback = configs[1] if len(configs) > 1 else None
    attempts = []
    for index, config in enumerate((selected, fallback)):
        if config is None:
            break
        try:
            submitted = video_ai_edit_provider.submit_video_edit(
                config,
                source_video_path=scene_source_path,
                prompt=prompt,
                negative_prompt=negative,
                aspect_ratio=aspect_ratio,
                duration_seconds=target_duration,
                job_id=f"{job_id}:scene:{scene_index}",
                submit_source=video_ai_edit_provider.PUBLIC_FINAL_CONFIRM_SOURCE,
                public_user_confirmed=True,
            )
            task_id = str(submitted.get("provider_task_id") or "")
            provider_result = dict(submitted)
            if not submitted.get("result_url_present"):
                provider_result = video_ai_edit_provider.wait_for_result(config, task_id)
            result_url = str(provider_result.get("result_url") or "").strip()
            if not result_url:
                raise video_ai_edit_provider.AiEditProviderError("provider_result_url_missing")
            downloaded = video_ai_edit_provider.download_result(result_url, raw_path)
            continuity_evidence = _selfshot2_continuity_evidence_from_payload(provider_result)
            attempts.append({"provider": config.provider_name, "model": config.model, "task_id_present": bool(task_id), "fallback": bool(index)})
            return {
                "ok": True,
                "selfshot2": True,
                "scene_index": scene_index,
                "provider_attempted": True,
                "provider": config.provider_name,
                "model": config.model,
                "provider_task_ids": [task_id] if task_id else [],
                "provider_video_ids": [],
                "result_url_present": True,
                "output_path": str(downloaded.get("path") or raw_path),
                "duration": target_duration,
                "scene_duration_seconds": target_duration,
                "clip_duration_seconds": target_duration,
                "expected_duration_seconds": target_duration,
                "engine_route": "direct_video_to_video",
                "selected_capability": "video_to_video",
                "source_uploaded_multipart": True,
                "source_bound": True,
                "source_segment_start": segment["start_seconds"],
                "source_segment_end": segment["end_seconds"],
                "text_only_fallback_allowed": False,
                "continuity_validation_required": True,
                "continuity_evidence": continuity_evidence,
                "continuity_evidence_present": bool(continuity_evidence),
                "fallback_used": bool(index),
                "fallback_count": int(index),
                "attempts": attempts,
                "no_charge": False,
            }
        except video_ai_edit_provider.AiEditProviderError as exc:
            attempts.append({"provider": config.provider_name, "model": config.model, "error": exc.reason, "fallback": bool(index)})
            if index == 0:
                decision = video_ai_edit_provider.controlled_fallback_decision(
                    public_confirm_provenance=True,
                    primary_status="timeout" if exc.reason == "provider_poll_timeout" else "failed",
                    primary_task_alive=False,
                    fallback_count=0,
                    candidate=fallback,
                )
                if not decision.get("allowed"):
                    raise RealVideoRenderError(exc.reason, diagnostics={"ok": False, "selfshot2": True, "scene_index": scene_index, "provider_attempted": True, "attempts": attempts, "no_charge": True, "blocker": exc.reason}) from exc
                continue
            raise RealVideoRenderError(exc.reason, diagnostics={"ok": False, "selfshot2": True, "scene_index": scene_index, "provider_attempted": True, "attempts": attempts, "no_charge": True, "blocker": exc.reason}) from exc
    raise RealVideoRenderError(
        "selfshot2_video_to_video_failed",
        diagnostics={"ok": False, "selfshot2": True, "scene_index": scene_index, "provider_attempted": bool(attempts), "attempts": attempts, "no_charge": True, "blocker": "selfshot2_video_to_video_failed"},
    )


_SELFSHOT2_CONTINUITY_ALIASES = {
    "person_identity": (
        "person_identity",
        "person_identity_preserved",
        "face_identity_preserved",
        "subject_identity_preserved",
        "person_continuity",
        "face_continuity",
    ),
    "object_identity": (
        "object_identity",
        "object_identity_preserved",
        "product_identity_preserved",
        "object_continuity",
        "product_continuity",
    ),
    "person_object_relationship": (
        "person_object_relationship",
        "person_object_relationship_preserved",
        "relationship_continuity",
        "interaction_relationship_preserved",
    ),
}


def _selfshot2_explicit_pass(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"true", "pass", "passed", "ok", "preserved", "valid"}
    return False


def _selfshot2_continuity_evidence_from_payload(payload: dict[str, Any] | None) -> dict[str, bool]:
    """Extract only explicit continuity evidence; transport success is never evidence."""

    row = dict(payload or {})
    candidates: list[dict[str, Any]] = [row]
    for key in ("continuity_metrics", "continuity_evidence", "continuity_validation", "subject_continuity"):
        value = row.get(key)
        if isinstance(value, dict):
            candidates.append(dict(value))
            metrics = value.get("metrics")
            if isinstance(metrics, dict):
                candidates.append(dict(metrics))
    evidence: dict[str, bool] = {}
    for canonical, aliases in _SELFSHOT2_CONTINUITY_ALIASES.items():
        for candidate in candidates:
            matched = next((candidate.get(alias) for alias in aliases if alias in candidate), None)
            if matched is not None:
                evidence[canonical] = _selfshot2_explicit_pass(matched)
                break
    return evidence


def selfshot2_continuity_validation(
    job: dict[str, Any] | None,
    result: dict[str, Any] | None,
    *,
    scene_tasks: list[dict[str, Any]] | None = None,
    debug_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Require final MP4, full scene coverage, and explicit per-scene continuity proof."""

    job_payload = dict(job or {})
    output = dict(result or {})
    asset_pack = _asset_pack_payload(job_payload)
    subject_manifest = dict(asset_pack.get("subject_manifest") or {})
    person_required = bool(subject_manifest.get("person_subject_ids"))
    object_required = bool(subject_manifest.get("object_subject_ids"))
    relationship_required = person_required and object_required
    scene_count = max(1, _scene_count(job_payload))
    expected_indexes = set(range(1, scene_count + 1))

    final_path = str(output.get("final_video_path") or output.get("master_video_path") or "")
    final_mp4_valid = bool(
        final_path
        and os.path.isfile(final_path)
        and os.path.getsize(final_path) > 0
        and int(output.get("output_bytes") or 0) > 0
        and output.get("has_video") is True
        and str(output.get("validation_status") or "").startswith("candidate_mp4_valid")
    )

    task_rows = [dict(item) for item in (scene_tasks or []) if isinstance(item, dict)]
    completed_indexes: set[int] = set()
    for item in task_rows:
        index = _safe_int(item.get("scene_index") or item.get("scene_id"), 0)
        status = str(item.get("status") or item.get("provider_status") or "").strip().lower()
        # Provider success/task/result URL proves transport only. Coverage is
        # complete after a scene clip was downloaded or explicitly validated.
        clip_validated = bool(
            status in {"downloaded", "validated", "clip_downloaded", "scene_clip_validated"}
            or item.get("clip_valid") is True
            or item.get("validation_passed") is True
        )
        if index and clip_validated:
            completed_indexes.add(index)
    scene_coverage_complete = bool(
        expected_indexes.issubset(completed_indexes)
        and (scene_count == 1 or output.get("concat_ready") is True)
    )

    evidence_by_scene: dict[int, dict[str, bool]] = {}
    evidence_rows = [
        *[dict(item) for item in (debug_results or []) if isinstance(item, dict)],
        *task_rows,
    ]
    for row in evidence_rows:
        nested = dict(row.get("debug") or {}) if isinstance(row.get("debug"), dict) else {}
        index = _safe_int(
            row.get("scene_index") or row.get("scene_id") or nested.get("scene_index") or nested.get("scene_id"),
            0,
        )
        if index not in expected_indexes:
            continue
        evidence = _selfshot2_continuity_evidence_from_payload({**row, **nested})
        if not evidence:
            continue
        current = evidence_by_scene.setdefault(index, {})
        for key, value in evidence.items():
            current[key] = bool(current.get(key)) or value

    person_ok = not person_required or all(evidence_by_scene.get(index, {}).get("person_identity") is True for index in expected_indexes)
    object_ok = not object_required or all(evidence_by_scene.get(index, {}).get("object_identity") is True for index in expected_indexes)
    relationship_ok = not relationship_required or all(
        evidence_by_scene.get(index, {}).get("person_object_relationship") is True for index in expected_indexes
    )
    required_metrics = ["final_mp4_valid", "scene_coverage_complete"]
    if person_required:
        required_metrics.append("person_identity")
    if object_required:
        required_metrics.append("object_identity")
    if relationship_required:
        required_metrics.append("person_object_relationship")
    metrics = {
        "final_mp4_valid": final_mp4_valid,
        "scene_coverage_complete": scene_coverage_complete,
        "person_identity": person_ok,
        "object_identity": object_ok,
        "person_object_relationship": relationship_ok,
    }
    blocker = ""
    if not final_mp4_valid:
        blocker = "selfshot2_valid_final_mp4_required"
    elif not scene_coverage_complete:
        blocker = "selfshot2_scene_coverage_incomplete"
    elif not person_ok:
        blocker = "selfshot2_person_continuity_evidence_missing"
    elif not object_ok:
        blocker = "selfshot2_object_continuity_evidence_missing"
    elif not relationship_ok:
        blocker = "selfshot2_relationship_continuity_evidence_missing"
    evidence_scene_indexes = sorted(
        index
        for index in expected_indexes
        if (
            (not person_required or evidence_by_scene.get(index, {}).get("person_identity") is True)
            and (not object_required or evidence_by_scene.get(index, {}).get("object_identity") is True)
            and (not relationship_required or evidence_by_scene.get(index, {}).get("person_object_relationship") is True)
        )
    )
    return {
        "ok": not blocker,
        "blocker": blocker,
        "required": required_metrics,
        "metrics": metrics,
        "expected_scene_indexes": sorted(expected_indexes),
        "completed_scene_indexes": sorted(completed_indexes),
        "continuity_evidence_scene_indexes": evidence_scene_indexes,
        "continuity_missing_scene_indexes": sorted(expected_indexes - set(evidence_scene_indexes)),
        "continuity_evidence_by_scene": {str(key): value for key, value in sorted(evidence_by_scene.items())},
    }


async def _render_scene_async(scene, raw_path: str, provider_order: list[str]) -> dict:
    prompt = _safe_text(getattr(scene, "video_prompt", "") or getattr(scene, "visual_prompt", ""), 1200)
    aspect_ratio = str(getattr(scene, "aspect_ratio", "") or "9:16")
    job = getattr(scene, "_toan_aas_job", {}) if hasattr(scene, "_toan_aas_job") else {}
    product_type = _product_type(job)
    required_capability = product_video_required_capability(job)
    scene_index = _safe_int(getattr(scene, "scene_id", 0), 0) or 1
    orchestration_mode = product_video_orchestration_mode(job)
    scene_duration_seconds = product_video_scene_duration_seconds(job)
    request_job_id = product_video_scene_request_id(job, scene_index)
    pending_scene_task = product_video_scene_task_for_index(job, scene_index)
    pending_request_job_id = str(
        pending_scene_task.get("request_job_id")
        or pending_scene_task.get("provider_pending_request_job_id")
        or (job or {}).get("provider_pending_request_job_id")
        or ""
    ).strip()
    pending_task_id = str(
        pending_scene_task.get("active_task_id")
        or pending_scene_task.get("provider_task_id")
        or pending_scene_task.get("task_id")
        or pending_scene_task.get("winning_task_id")
        or pending_scene_task.get("scene_winner_task")
        or pending_scene_task.get("canonical_task_selected")
        or ((job or {}).get("provider_pending_task_id") if not pending_scene_task else "")
        or ""
    ).strip()
    pending_video_id = str(
        pending_scene_task.get("provider_video_id")
        or pending_scene_task.get("video_id")
        or ((job or {}).get("provider_pending_video_id") if not pending_scene_task else "")
        or ""
    ).strip()
    pending_matches_request = bool(
        pending_task_id or pending_video_id
    ) and (not pending_request_job_id or pending_request_job_id == request_job_id)
    recovery_existing_tasks_only = bool(
        (job or {}).get("recovery_existing_tasks_only")
    )
    provider_aliases = {
        "shopai": "shopaikey_video",
        "shopaikey": "shopaikey_video",
        "k4u": "key4u_video",
        "key4u": "key4u_video",
        "toanaas": "toanaas_video",
        "generic": "generic_http",
    }
    pending_provider_key = provider_aliases.get(
        str(
            pending_scene_task.get("provider")
            or pending_scene_task.get("provider_name")
            or pending_scene_task.get("provider_key")
            or ""
        ).strip().lower(),
        str(
            pending_scene_task.get("provider")
            or pending_scene_task.get("provider_name")
            or pending_scene_task.get("provider_key")
            or ""
        ).strip().lower(),
    )
    recovery_provider_order = {
        provider_aliases.get(str(item or "").strip().lower(), str(item or "").strip().lower())
        for item in provider_order
        if str(item or "").strip()
    }
    recovery_provider_mismatch = bool(
        recovery_existing_tasks_only
        and pending_matches_request
        and (
            not pending_provider_key
            or (
                recovery_provider_order
                and pending_provider_key not in recovery_provider_order
            )
        )
    )
    if recovery_provider_mismatch:
        raise RealVideoRenderError(
            "scene_provider_mismatch",
            diagnostics={
                "ok": False,
                "scene_index": scene_index,
                "scene_id": scene_index,
                "request_job_id": request_job_id,
                "provider_error": "scene_provider_mismatch",
                "blocker": "scene_provider_mismatch",
                "provider_binding_present": bool(pending_provider_key),
                "provider_order_match": False,
                "provider_submit_called": False,
                "provider_submit_allowed": False,
                "automatic_retry_allowed": False,
                "automatic_resubmit_allowed": False,
                "automatic_fallback_allowed": False,
                "recovery_existing_tasks_only": True,
                "no_charge": True,
            },
        )
    pending_policy = product_video_scene_stall_policy(job, pending_scene_task, scene_index) if pending_matches_request else {}
    scene_fallback_order = list(pending_policy.get("fallback_provider_order") or [])
    scene_fallback_allowed = bool(pending_policy.get("fallback_allowed"))
    automatic_fallback_forbidden = _durable_product_video_route_forbids(
        job,
        "automatic_fallback_allowed",
    )
    controlled_fallback_allowed = bool(
        pending_policy.get("controlled_fallback_allowed")
    )
    if automatic_fallback_forbidden and not controlled_fallback_allowed:
        scene_fallback_order = []
        scene_fallback_allowed = False
    if recovery_existing_tasks_only and not controlled_fallback_allowed:
        automatic_fallback_forbidden = True
        scene_fallback_order = []
        scene_fallback_allowed = False
    scene_stalled_not_start = bool(pending_policy.get("provider_stalled_not_start"))
    scene_provider_stalled = bool(pending_policy.get("provider_scene_stalled"))
    fallback_execution_tick_called = bool(pending_matches_request and scene_provider_stalled)
    fallback_provider_candidate = str((scene_fallback_order or [""])[0] or "")
    fallback_idempotency_key = product_video_scene_fallback_idempotency_key(
        (job or {}).get("job_id") or (job or {}).get("id") or request_job_id,
        scene_index,
        fallback_provider_candidate,
    ) if fallback_provider_candidate else ""
    if pending_matches_request and scene_provider_stalled and scene_fallback_allowed:
        pending_matches_request = False
        pending_task_id = ""
        pending_video_id = ""
        pending_request_job_id = ""
    asset_pack = _json_loads((job or {}).get("asset_pack"), {})
    invoice = _json_loads((job or {}).get("invoice"), {})
    if not asset_pack and isinstance((job or {}).get("project"), dict):
        asset_pack = _json_loads(((job or {}).get("project") or {}).get("asset_pack_json"), {})
    if not invoice and isinstance((job or {}).get("project"), dict):
        invoice = _json_loads(((job or {}).get("project") or {}).get("invoice_json"), {})

    def _meta_value(*keys: str) -> Any:
        for source in (job or {}, asset_pack, invoice):
            if not isinstance(source, dict):
                continue
            for key in keys:
                value = source.get(key)
                if value not in (None, "", [], {}):
                    return value
        return ""

    original_submit_source = str(
        _meta_value("original_submit_source", "public_confirm_submit_source", "initial_submit_source")
        or ""
    ).strip()
    if not original_submit_source:
        for source in (asset_pack, invoice, job or {}):
            if not isinstance(source, dict):
                continue
            candidate = str(source.get("submit_source") or source.get("provider_submit_source") or "").strip()
            if candidate and candidate != PRODUCT_VIDEO_SUBMIT_SOURCE_WORKER_POLL_EXISTING_TASK:
                original_submit_source = candidate
                break
    confirmed_public_input = bool(
        _meta_value(
            "public_user_confirmed",
            "b14_public_user_confirmed",
            "user_final_confirmed",
            "invoice_confirmed",
            "final_invoice_confirmed",
            "project_is_confirmed",
            "is_confirmed",
            "confirmed",
            "public_user",
        )
    )
    submit_source = str(_meta_value("submit_source", "provider_submit_source") or "").strip()
    if pending_matches_request:
        submit_source = PRODUCT_VIDEO_SUBMIT_SOURCE_WORKER_POLL_EXISTING_TASK
    elif scene_fallback_allowed:
        submit_source = PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_SCENE_FALLBACK_ONCE
    elif not submit_source and confirmed_public_input:
        submit_source = PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_FINAL_CONFIRM
    if not original_submit_source and confirmed_public_input:
        original_submit_source = PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_FINAL_CONFIRM
    public_user_confirmed = bool(
        _meta_value("public_user_confirmed", "b14_public_user_confirmed", "user_final_confirmed")
        or original_submit_source == PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_FINAL_CONFIRM
        or submit_source == PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_FINAL_CONFIRM
    )
    invoice_confirmed = bool(
        _meta_value("invoice_confirmed", "final_invoice_confirmed", "project_is_confirmed", "is_confirmed", "confirmed")
        or public_user_confirmed
    )
    charge_policy = str(_meta_value("charge_policy") or "after_valid_mp4_delivery").strip()
    current_job_id = _safe_int(
        _meta_value("current_probation_job_id", "current_job_id")
        or (job or {}).get("job_id")
        or (job or {}).get("id"),
        0,
    )
    probation_lock_owner_job = _safe_int(
        _meta_value("probation_lock_owner_job", "active_probation_job_id", "probation_job_id"),
        0,
    )
    current_job_matches_lock = bool(
        _meta_value("current_job_matches_lock", "same_job_lock_reentry_allowed")
        or (
            current_job_id > 0
            and probation_lock_owner_job > 0
            and current_job_id == probation_lock_owner_job
        )
    )
    probation_lock_clear_for_current_job = bool(
        _meta_value(
            "probation_lock_clear_for_current_job",
            "probation_lock_clear_at_candidate_resolver",
            "probation_lock_clear",
        )
        or current_job_matches_lock
    )
    admission_context = {
        "admission_enforced": bool(_meta_value("admission_enforced")),
        "admission_mode": str(_meta_value("admission_mode") or ""),
        "worker_compatible": bool(
            _meta_value(
                "worker_compatible",
                "admission_worker_version_compatible",
                "worker_connected",
            )
        ),
        "probation_lock_clear": bool(_meta_value("probation_lock_clear")),
        "probation_lock_clear_for_current_job": probation_lock_clear_for_current_job,
        "probation_lock_owner_job": probation_lock_owner_job,
        "current_job_id": current_job_id,
        "current_probation_job_id": current_job_id,
        "current_job_matches_lock": current_job_matches_lock,
        "same_job_lock_reentry_allowed": bool(
            _meta_value("same_job_lock_reentry_allowed") or current_job_matches_lock
        ),
        "probation_lock_owned_by_other_job": bool(
            _meta_value("probation_lock_owned_by_other_job")
        ),
    }
    model_context: dict[str, Any] = {}
    for source in (pending_scene_task, job or {}, asset_pack, invoice):
        if not isinstance(source, dict):
            continue
        for key in (
            "model_routing_ok",
            "product_video_tier",
            "selected_provider",
            "selected_model",
            "selected_family",
            "selected_model_source",
            "selected_quality",
            "selected_capabilities",
            "selected_clip_seconds",
            "selected_payload_adapter",
            "selected_request_defaults",
            "provider_model_map",
            "provider_request_defaults",
            "provider_catalog_model_found",
            "supports_concat",
            "contract_validation_status",
            "rejected_models",
            "required_capability_original",
            "normalized_capability_candidates",
            "model_routing_blocker",
        ):
            if key not in model_context and source.get(key) not in (None, "", [], {}):
                model_context[key] = source.get(key)
    if not model_context.get("selected_model"):
        model_resolution = resolve_product_video_model(
            tier=_meta_value("tier", "tier_key", "package_xu", "quality_tier") or "basic",
            provider_chain=provider_order,
            scene_count=_scene_count(job),
            required_capability=required_capability,
            requires_concat=orchestration_mode == PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE_8S,
        )
        model_context.update(model_metadata_from_resolution(model_resolution))
    if (
        recovery_existing_tasks_only
        and not pending_matches_request
        and not scene_fallback_allowed
    ):
        raise RealVideoRenderError(
            "scene_provider_task_id_missing",
            diagnostics={
                "ok": False,
                "scene_index": scene_index,
                "scene_id": scene_index,
                "request_job_id": request_job_id,
                "provider_error": "scene_provider_task_id_missing",
                "blocker": "scene_provider_task_id_missing",
                "provider_submit_called": False,
                "provider_submit_allowed": False,
                "automatic_retry_allowed": False,
                "automatic_resubmit_allowed": False,
                "automatic_fallback_allowed": False,
                "recovery_existing_tasks_only": True,
                "no_charge": True,
            },
        )
    if (
        pending_matches_request
        and scene_provider_stalled
        and not scene_fallback_allowed
        and not recovery_existing_tasks_only
    ):
        raise RealVideoRenderError(
            PRODUCT_VIDEO_PROVIDER_STALLED_NOT_START,
            diagnostics={
                "ok": False,
                "scene_index": scene_index,
                "scene_id": scene_index,
                "request_job_id": request_job_id,
                "provider": str(pending_scene_task.get("provider") or ""),
                "selected_provider": str(pending_scene_task.get("provider") or ""),
                "provider_task_ids": [pending_task_id] if pending_task_id else [],
                "provider_video_ids": [pending_video_id] if pending_video_id else [],
                "provider_error": PRODUCT_VIDEO_PROVIDER_STALLED_NOT_START,
                "blocker": PRODUCT_VIDEO_PROVIDER_STALLED_NOT_START,
                "provider_status": PRODUCT_VIDEO_PROVIDER_STALLED_NOT_START,
                "normalized_provider_status": PRODUCT_VIDEO_PROVIDER_STALLED_NOT_START,
                "provider_status_raw": str(pending_scene_task.get("provider_status_raw") or "NOT_START"),
                "continue_polling": False,
                "provider_stalled_not_start": scene_stalled_not_start,
                "scene_not_start_elapsed": pending_policy.get("scene_not_start_elapsed") or 0,
                "stall_threshold": pending_policy.get("stall_threshold") or DEFAULT_PRODUCT_VIDEO_FIRST_SCENE_NOT_START_GRACE_SECONDS,
                "fallback_scene_index": scene_index,
                "fallback_allowed": False,
                "fallback_execution_tick_called": fallback_execution_tick_called,
                "fallback_submit_attempted": False,
                "fallback_idempotency_key": fallback_idempotency_key,
                "fallback_block_reason": pending_policy.get("fallback_block_reason") or "no_fallback_provider",
                "no_charge": True,
            },
        )
    dispatch_provider_key = str(
        pending_scene_task.get("provider")
        or model_context.get("selected_provider")
        or (provider_order[0] if provider_order else "")
        or ""
    ).strip()
    scene_dispatch_idempotency_key = product_video_scene_dispatch_idempotency_key(
        (job or {}).get("job_id") or (job or {}).get("id") or request_job_id,
        scene_index,
        dispatch_provider_key,
    )
    missing_scene_dispatch_recovered = bool(
        not pending_matches_request
        and any(
            _scene_task_index(item) == scene_index
            and _scene_task_has_dispatch_attempt(item)
            for item in _existing_scene_tasks(job)
        )
    )
    if (
        missing_scene_dispatch_recovered
        and not scene_fallback_allowed
        and _durable_product_video_route_forbids(
            job,
            "automatic_resubmit_allowed",
        )
    ):
        raise RealVideoRenderError(
            "product_video_automatic_resubmit_forbidden",
            diagnostics={
                "ok": False,
                "scene_index": scene_index,
                "scene_id": scene_index,
                "request_job_id": request_job_id,
                "provider_error": "product_video_automatic_resubmit_forbidden",
                "blocker": "product_video_automatic_resubmit_forbidden",
                "provider_submit_called": False,
                "automatic_resubmit_allowed": False,
                "no_charge": True,
            },
        )
    request = VideoGenerationRequest(
        job_id=request_job_id,
        product_type=product_type or "video_ai_prompt",
        video_flow_type=str((job or {}).get("video_flow") or product_type or ""),
        prompt=prompt,
        negative_prompt=str((job or {}).get("negative_prompt") or ""),
        scenes=[dict(getattr(scene, "__dict__", {}) or {})],
        storyboard=(
            [
                card
                for fallback_index, card in enumerate(_scene_cards(job), start=1)
                if max(1, _safe_int(card.get("scene_index") or card.get("scene_id"), fallback_index)) == scene_index
            ]
            if product_type in PRODUCT_VIDEO_SCENE_IMAGE_INPUT_TYPES
            else _scene_cards(job)
        ),
        image_paths=product_video_scene_image_paths(job, scene_index),
        source_video_path=str((job or {}).get("source_video_path") or ""),
        ratio=aspect_ratio,
        duration_seconds=float(scene_duration_seconds if orchestration_mode == PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE_8S else (getattr(scene, "target_duration_sec", 6.0) or 6.0)),
        quality=str((job or {}).get("quality") or ""),
        style=str((job or {}).get("style") or ""),
        add_ons=_addon_plan(job),
        metadata={
            "scene_id": scene_index,
            "scene_index": scene_index,
            "scene_count": _scene_count(job),
            "scene_duration_seconds": scene_duration_seconds,
            "clip_index": scene_index,
            "clip_count": _scene_count(job),
            "clip_duration_seconds": scene_duration_seconds,
            "orchestration_mode": orchestration_mode,
            "provider_orchestration_mode": orchestration_mode,
            "render_pipeline_mode": PRODUCT_VIDEO_RENDER_PIPELINE_HISTORICAL_CONCAT
            if orchestration_mode == PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE_8S
            else PRODUCT_VIDEO_ORCHESTRATION_MODE_LEGACY_SINGLE_TASK,
            "expected_duration_seconds": product_video_expected_duration_seconds(job),
            "provider_scene_request_id": request_job_id,
            "scene_dispatch_state": "task_submitted" if pending_matches_request else "submit_in_progress",
            "scene_dispatch_attempted": bool(not pending_matches_request),
            "scene_dispatch_block_reason": "",
            "scene_dispatch_idempotency_key": scene_dispatch_idempotency_key,
            "missing_scene_dispatch_recovered": missing_scene_dispatch_recovered,
            "dispatch_recovered": missing_scene_dispatch_recovered,
            "raw_output_path": raw_path,
            "product_video": bool(str((job or {}).get("source") or "") == "product_video" or (job or {}).get("product_video")),
            "render_mode": str((job or {}).get("render_mode") or ""),
            "submit_source": submit_source,
            "provider_submit_source": submit_source,
            "original_submit_source": original_submit_source or submit_source,
            "public_confirm_submit_source": original_submit_source or submit_source,
            "public_user_confirmed": public_user_confirmed,
            "invoice_confirmed": invoice_confirmed,
            "project_is_confirmed": invoice_confirmed,
            "provider_submit_accepted_before": bool(pending_matches_request),
            "product_video_durable_public_seam": bool(
                (job or {}).get("product_video_durable_public_seam")
            ),
            "automatic_retry_allowed": (job or {}).get(
                "automatic_retry_allowed"
            ),
            "automatic_resubmit_allowed": (job or {}).get(
                "automatic_resubmit_allowed"
            ),
            "automatic_fallback_allowed": (job or {}).get(
                "automatic_fallback_allowed"
            ),
            "recovery_existing_tasks_only": recovery_existing_tasks_only,
            "provider_submit_allowed": False
            if recovery_existing_tasks_only and not scene_fallback_allowed
            else (job or {}).get("provider_submit_allowed"),
            "paid_fallback_confirmed": bool(scene_fallback_allowed or invoice_confirmed),
            "fallback_count": 1 if scene_fallback_allowed else _safe_int(pending_scene_task.get("fallback_count"), 0),
            "provider_fallback_count": 1 if scene_fallback_allowed else _safe_int(pending_scene_task.get("provider_fallback_count") or pending_scene_task.get("fallback_count"), 0),
            "fallback_scene_index": scene_index if scene_fallback_allowed else 0,
            "provider_stalled_not_start": scene_stalled_not_start,
            "scene_not_start_elapsed": pending_policy.get("scene_not_start_elapsed") or 0,
            "stall_threshold": pending_policy.get("stall_threshold") or DEFAULT_PRODUCT_VIDEO_FIRST_SCENE_NOT_START_GRACE_SECONDS,
            "not_start_threshold_seconds": pending_policy.get("not_start_threshold_seconds") or pending_policy.get("stall_threshold") or DEFAULT_PRODUCT_VIDEO_FIRST_SCENE_NOT_START_GRACE_SECONDS,
            "not_start_threshold_source": str(pending_policy.get("not_start_threshold_source") or ""),
            "fallback_execution_tick_called": fallback_execution_tick_called,
            "fallback_submit_attempted": bool(scene_fallback_allowed),
            "fallback_idempotency_key": fallback_idempotency_key,
            "provider_eligibility_snapshot": _meta_value("provider_eligibility_snapshot") or {},
            "provider_eligibility_snapshot_id": _meta_value("provider_eligibility_snapshot_id") or "",
            "configured_provider_chain": _meta_value("configured_provider_chain") or [],
            "preconfirm_candidate_keys": _meta_value("preconfirm_candidate_keys") or [],
            "runtime_candidate_keys": _meta_value("runtime_candidate_keys") or [],
            "candidate_set_consistent": _meta_value("candidate_set_consistent") is not False,
            "candidate_rejection_reason_by_provider": _meta_value("candidate_rejection_reason_by_provider") or {},
            "final_eligible_provider_count": _meta_value("final_eligible_provider_count") or 0,
            "provider_health_at_submit": _meta_value("provider_health_at_submit", "provider_health_summary") or {},
            "primary_selected_due_to_health": _meta_value("primary_selected_due_to_health") or "",
            "provider_degraded_reason": _meta_value("provider_degraded_reason", "degraded_reason") or "",
            "charge_policy": charge_policy,
            "user_visible_price_xu": _meta_value("user_visible_price_xu", "package_xu", "package_price_xu"),
            "persisted_quoted_price_xu": _meta_value("persisted_quoted_price_xu", "quoted_price_xu", "quoted_price"),
            "customer_charge_planned_xu": _meta_value("customer_charge_planned_xu", "wallet_charge_amount_xu", "charge_amount_planned_xu"),
            "provider_budget_xu": _meta_value("provider_budget_xu", "provider_cost_cap_xu"),
            "quote_consistent": _meta_value("quote_consistent") or True,
            "allow_provider_pending": True,
            "claim_payload_provider_key": str((job or {}).get("selected_provider") or (job or {}).get("submit_provider_key") or ""),
            "claim_payload_has_provider_config": bool((job or {}).get("provider_config") or (job or {}).get("provider_submit_url") or (job or {}).get("provider_auth_header_value")),
            "provider_pending_provider": str(pending_scene_task.get("provider") or (job or {}).get("provider_pending_provider") or "") if pending_matches_request else "",
            "provider_pending_task_id": pending_task_id if pending_matches_request else "",
            "provider_pending_video_id": pending_video_id if pending_matches_request else "",
            "provider_pending_request_job_id": pending_request_job_id if pending_matches_request else "",
            "provider_pending_attempts": ((job or {}).get("provider_pending_attempts") or []) if pending_matches_request else [],
            "provider_started_at": str((job or {}).get("provider_started_at") or "") if pending_matches_request else "",
            "provider_started_at_epoch": (job or {}).get("provider_started_at_epoch") if pending_matches_request else "",
            "provider_wait_started_at": str((job or {}).get("provider_started_at") or (job or {}).get("provider_wait_started_at") or "") if pending_matches_request else "",
            "provider_wait_started_epoch": (job or {}).get("provider_started_at_epoch") or (job or {}).get("provider_wait_started_epoch") if pending_matches_request else "",
            **admission_context,
            **model_context,
        },
        required_capability=required_capability,
    )
    output_dir = os.path.dirname(os.path.abspath(raw_path))
    provider_env = dict(os.environ)
    if provider_order:
        provider_env["VIDEO_PROVIDER_CHAIN"] = ",".join(provider_order)
    if automatic_fallback_forbidden and dispatch_provider_key:
        provider_env["VIDEO_PROVIDER_CHAIN"] = dispatch_provider_key
    if scene_fallback_allowed and scene_fallback_order:
        provider_env["VIDEO_PROVIDER_CHAIN"] = ",".join(scene_fallback_order)
    provider_model_map = model_context.get("provider_model_map") if isinstance(model_context.get("provider_model_map"), dict) else {}
    if provider_model_map.get("shopaikey_video"):
        provider_env["SHOPAIKEY_VIDEO_MODEL"] = str(provider_model_map.get("shopaikey_video") or "")
    if provider_model_map.get("key4u_video"):
        provider_env["KEY4U_VIDEO_MODEL"] = str(provider_model_map.get("key4u_video") or "")
    if recovery_existing_tasks_only:
        result = run_provider_generation(
            request,
            output_dir=output_dir,
            environ=provider_env,
        )
    elif product_type == "self_shot_scene_change":
        result = _render_selfshot2_video_to_video(
            job=dict(job or {}),
            asset_pack=dict(asset_pack or {}),
            raw_path=raw_path,
            provider_order=provider_order,
            fallback_prompt=prompt,
            aspect_ratio=aspect_ratio,
            scene_index=scene_index,
        )
    elif product_type == "self_shot_cinematic_transform":
        result = _render_selfshot3_video_to_video(
            job=dict(job or {}),
            asset_pack=dict(asset_pack or {}),
            raw_path=raw_path,
            provider_order=provider_order,
            fallback_prompt=prompt,
            aspect_ratio=aspect_ratio,
        )
    else:
        result = run_provider_generation(request, output_dir=output_dir, environ=provider_env)
    result.setdefault("scene_index", scene_index)
    result.setdefault("scene_id", scene_index)
    result.setdefault("scene_duration_seconds", scene_duration_seconds)
    result.setdefault("provider_scene_request_id", request_job_id)
    result.setdefault("request_job_id", request_job_id)
    result.setdefault("dispatch_idempotency_key", scene_dispatch_idempotency_key)
    result.setdefault("scene_dispatch_idempotency_key", scene_dispatch_idempotency_key)
    result.setdefault("dispatch_attempted", bool(not pending_matches_request))
    result.setdefault("scene_dispatch_attempted", bool(not pending_matches_request))
    result.setdefault("dispatch_recovered", missing_scene_dispatch_recovered)
    result.setdefault("missing_scene_dispatch_recovered", missing_scene_dispatch_recovered)
    result.setdefault("dispatch_state", "task_submitted" if (pending_matches_request or result.get("provider_task_id_saved") or result.get("task_id_present")) else "submit_in_progress")
    result.setdefault("scene_dispatch_state", result.get("dispatch_state"))
    result.setdefault("dispatch_block_reason", "")
    result.setdefault("scene_dispatch_block_reason", result.get("dispatch_block_reason"))
    result.setdefault("provider_stalled_not_start", scene_stalled_not_start)
    result.setdefault("scene_not_start_elapsed", pending_policy.get("scene_not_start_elapsed") or 0)
    result.setdefault("stall_threshold", pending_policy.get("stall_threshold") or DEFAULT_PRODUCT_VIDEO_FIRST_SCENE_NOT_START_GRACE_SECONDS)
    result.setdefault("not_start_threshold_seconds", pending_policy.get("not_start_threshold_seconds") or pending_policy.get("stall_threshold") or DEFAULT_PRODUCT_VIDEO_FIRST_SCENE_NOT_START_GRACE_SECONDS)
    result.setdefault("not_start_threshold_source", pending_policy.get("not_start_threshold_source") or "")
    result.setdefault("fallback_execution_tick_called", fallback_execution_tick_called)
    result.setdefault("fallback_submit_attempted", bool(scene_fallback_allowed))
    result.setdefault("fallback_idempotency_key", fallback_idempotency_key)
    result.setdefault("fallback_scene_index", scene_index if scene_fallback_allowed else 0)
    result.setdefault("fallback_allowed", scene_fallback_allowed)
    result.setdefault("fallback_block_reason", pending_policy.get("fallback_block_reason") or "")
    if scene_fallback_allowed:
        result.setdefault("fallback_used", True)
        result.setdefault("provider_fallback_attempted", True)
        result.setdefault("provider_fallback_reason", PRODUCT_VIDEO_PROVIDER_STALLED_NOT_START)
        result.setdefault("fallback_reason", PRODUCT_VIDEO_PROVIDER_STALLED_NOT_START)
        result.setdefault("submit_source", PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_SCENE_FALLBACK_ONCE)
        result.setdefault("provider_submit_source", PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_SCENE_FALLBACK_ONCE)
        result.setdefault("fallback_submit_source", PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_SCENE_FALLBACK_ONCE)
        result.setdefault("selected_provider_before_submit", str(pending_scene_task.get("provider") or ""))
        result.setdefault("fallback_count", 1)
        result.setdefault("provider_fallback_count", 1)
        result["key4u_submit_suppressed"] = False
        result["key4u_submit_suppressed_reason"] = ""
    if not result.get("ok"):
        raise RealVideoRenderError(str(result.get("blocker") or result.get("provider_error") or REAL_VIDEO_RENDER_UNAVAILABLE), diagnostics=result)
    output_path = str(result.get("output_path") or result.get("local_path") or "")
    if not output_path:
        raise RealVideoRenderError("provider_result_missing", diagnostics=result)
    if os.path.abspath(output_path) != os.path.abspath(raw_path):
        shutil.copyfile(output_path, raw_path)
        output_path = raw_path
    scene_result = dict(result)
    scene_result.update(
        {
            "ok": True,
            "provider": str(result.get("provider") or ""),
            "task_id": str((result.get("provider_task_ids") or [""])[0] or ""),
            "video_id": str((result.get("provider_video_ids") or [""])[0] or ""),
            "status": "SUCCESS",
            "output_path": ensure_video_output(output_path),
            "model": str(result.get("model") or ""),
            "mode": str(result.get("mode") or ""),
            "duration": result.get("duration") or result.get("output_duration") or 0,
            "download_url_present": bool(result.get("result_url_present")),
            "artifact_hash": str(result.get("artifact_hash") or ""),
        }
    )
    return scene_result


def build_real_scene_renderer(
    job: dict | None = None,
    events: list[dict[str, Any]] | None = None,
    debug_results: list[dict[str, Any]] | None = None,
):
    provider_order = _provider_order(job)

    def _render(scene, raw_path: str):
        try:
            setattr(scene, "_toan_aas_job", dict(job or {}))
        except Exception:
            pass
        try:
            result = asyncio.run(_render_scene_async(scene, raw_path, provider_order))
        except RealVideoRenderError as exc:
            diagnostics = dict(getattr(exc, "diagnostics", {}) or {})
            if isinstance(debug_results, list) and diagnostics:
                debug_results.append(diagnostics)
            if isinstance(events, list):
                scene_index = _safe_int(getattr(scene, "scene_id", 0), 0)
                events.append(
                    {
                        "scene_id": scene_index,
                        "scene_index": scene_index,
                        "request_job_id": product_video_scene_request_id(job, scene_index),
                        "scene_duration_seconds": product_video_scene_duration_seconds(job),
                        "provider": str(diagnostics.get("selected_provider") or diagnostics.get("provider") or ""),
                        "task_id": str((diagnostics.get("provider_task_ids") or [""])[0] or "")[:180],
                        "video_id": str((diagnostics.get("provider_video_ids") or [""])[0] or "")[:180],
                        "status": str(diagnostics.get("provider_status") or diagnostics.get("blocker") or "failed"),
                        "model": str(diagnostics.get("provider_payload_model") or "")[:120],
                        "mode": str(diagnostics.get("selected_capability") or "")[:80],
                        "duration": diagnostics.get("output_duration") or 0,
                        "download_url_present": bool(diagnostics.get("provider_result_url_present") or diagnostics.get("result_url_present")),
                        "debug": diagnostics,
                    }
                )
            raise
        if isinstance(debug_results, list) and isinstance(result, dict):
            debug_results.append(dict(result))
        if isinstance(events, list) and isinstance(result, dict):
            scene_index = _safe_int(getattr(scene, "scene_id", 0), 0)
            events.append(
                {
                    "scene_id": scene_index,
                    "scene_index": scene_index,
                    "request_job_id": product_video_scene_request_id(job, scene_index),
                    "scene_duration_seconds": product_video_scene_duration_seconds(job),
                    "provider": str(result.get("provider") or ""),
                    "task_id": str(result.get("task_id") or "")[:180],
                    "video_id": str(result.get("video_id") or "")[:180],
                    "status": "downloaded" if result.get("ok") else str(result.get("status") or "failed"),
                    "model": str(result.get("model") or "")[:120],
                    "mode": str(result.get("mode") or "")[:80],
                    "duration": result.get("duration") or 0,
                    "download_url_present": bool(result.get("download_url_present")),
                    "debug": dict(result),
                }
            )
        return result

    return _render


def _provider_event_from_payload(job: dict | None, scene_index: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(payload or {})
    task_ids = payload.get("provider_task_ids") if isinstance(payload.get("provider_task_ids"), list) else []
    video_ids = payload.get("provider_video_ids") if isinstance(payload.get("provider_video_ids"), list) else []
    task_id = str(payload.get("task_id") or (task_ids[0] if task_ids else "") or payload.get("provider_pending_task_id") or "").strip()
    video_id = str(payload.get("video_id") or (video_ids[0] if video_ids else "") or payload.get("provider_pending_video_id") or "").strip()
    return {
        "scene_id": scene_index,
        "scene_index": scene_index,
        "request_job_id": product_video_scene_request_id(job, scene_index),
        "scene_duration_seconds": product_video_scene_duration_seconds(job),
        "provider": str(payload.get("provider") or payload.get("selected_provider") or payload.get("provider_pending_provider") or ""),
        "task_id": task_id[:180],
        "video_id": video_id[:180],
        "status": _normalize_scene_task_status(payload.get("status") or payload.get("normalized_provider_status") or payload.get("provider_status") or payload.get("blocker"), payload),
        "model": str(payload.get("provider_payload_model") or payload.get("model") or "")[:120],
        "mode": str(payload.get("selected_capability") or payload.get("mode") or "")[:80],
        "duration": payload.get("output_duration") or payload.get("duration") or 0,
        "download_url_present": bool(
            (task_id or video_id)
            and (payload.get("provider_result_url_present") or payload.get("result_url_present"))
        ),
        "result_url": str(
            (payload.get("result_url") or payload.get("provider_result_url") or payload.get("download_url") or "")
            if (task_id or video_id)
            else ""
        ),
        "result_task_id": str(task_id or video_id or ""),
        "result_url_source": "scene_provider_payload" if (task_id or video_id) and (payload.get("result_url") or payload.get("provider_result_url") or payload.get("download_url")) else "",
        "task_scene_mapping_verified": bool(task_id or video_id),
        "phantom_result_prevented": bool(
            not (task_id or video_id)
            and (payload.get("result_url") or payload.get("provider_result_url") or payload.get("download_url") or payload.get("result_url_present"))
        ),
        "clip_path": str(payload.get("clip_path") or payload.get("output_path") or payload.get("local_path") or ""),
        "clip_bytes": _safe_int(payload.get("clip_bytes") or payload.get("artifact_size") or payload.get("artifact_bytes") or payload.get("output_bytes") or payload.get("downloaded_file_size"), 0),
        "clip_valid": bool(payload.get("clip_valid") or payload.get("validation_passed") or payload.get("output_validated") or _scene_output_from_payload(payload)),
        "provider_progress_raw": payload.get("provider_progress_raw") or payload.get("shopaikey_data_progress_raw") or "",
        "provider_progress_normalized": payload.get("provider_progress_normalized") or payload.get("provider_progress_percent") or 0,
        "provider_progress_last_changed_at": str(payload.get("provider_progress_last_changed_at") or payload.get("progress_last_changed_at") or ""),
        "provider_progress_last_changed_elapsed_seconds": _safe_int(payload.get("provider_progress_last_changed_elapsed_seconds") or payload.get("progress_last_changed_elapsed_seconds") or payload.get("in_progress_stall_elapsed"), 0),
        "provider_wait_elapsed_seconds": payload.get("provider_wait_elapsed_seconds") or payload.get("provider_elapsed_seconds") or 0,
        "provider_status_raw": payload.get("provider_status_raw") or payload.get("nonterminal_provider_status") or "",
        "provider_stalled_not_start": bool(payload.get("provider_stalled_not_start")),
        "provider_in_progress_stalled": bool(payload.get("provider_in_progress_stalled")),
        "provider_scene_stalled": bool(payload.get("provider_scene_stalled") or payload.get("provider_in_progress_stalled") or payload.get("provider_stalled_not_start")),
        "submit_accepted": bool(payload.get("submit_accepted") or task_id or video_id),
        "submit_http_status": _safe_int(payload.get("submit_http_status") or payload.get("provider_submit_http_status"), 0),
        "transport_http": _safe_int(payload.get("transport_http") or payload.get("submit_http_status") or payload.get("provider_submit_http_status"), 0),
        "task_id_present": bool(payload.get("task_id_present") or task_id or video_id),
        "task_pollable": bool(payload.get("task_pollable") or task_id or video_id),
        "effective_submit_outcome": str(payload.get("effective_submit_outcome") or ""),
        "transport_anomaly": bool(payload.get("transport_anomaly")),
        "transport_anomaly_ignored_due_to_valid_task": bool(payload.get("transport_anomaly_ignored_due_to_valid_task")),
        "dispatch_state": str(payload.get("dispatch_state") or payload.get("scene_dispatch_state") or ("task_submitted" if task_id or video_id else "submit_in_progress")),
        "dispatch_attempted": bool(payload.get("dispatch_attempted") or payload.get("scene_dispatch_attempted") or payload.get("provider_submit_called")),
        "dispatch_block_reason": str(payload.get("dispatch_block_reason") or payload.get("scene_dispatch_block_reason") or ""),
        "dispatch_idempotency_key": str(payload.get("dispatch_idempotency_key") or payload.get("scene_dispatch_idempotency_key") or payload.get("provider_submit_idempotency_key") or ""),
        "dispatch_recovered": bool(payload.get("dispatch_recovered") or payload.get("missing_scene_dispatch_recovered")),
        "fallback_count": _safe_int(payload.get("fallback_count") or payload.get("provider_fallback_count"), 0),
        "fallback_allowed": bool(payload.get("fallback_allowed")),
        "fallback_block_reason": str(payload.get("fallback_block_reason") or payload.get("fallback_blocked_reason") or ""),
        "fallbackable_blocker": bool(payload.get("fallbackable_blocker")),
        "fallback_eligibility_reason": str(payload.get("fallback_eligibility_reason") or ""),
        "fallback_scene_index": _safe_int(payload.get("fallback_scene_index"), 0),
        "fallback_submit_source": str(payload.get("fallback_submit_source") or payload.get("submit_source") or payload.get("provider_submit_source") or ""),
        "fallback_evaluated": bool(payload.get("fallback_evaluated") or payload.get("fallback_execution_tick_called")),
        "fallback_idempotency_key": str(payload.get("fallback_idempotency_key") or ""),
        "scene_winner_task": str(payload.get("scene_winner_task") or ""),
        "scene_winner_provider": str(payload.get("scene_winner_provider") or ""),
        "winner_selected_at": str(payload.get("winner_selected_at") or ""),
        "source_of_truth": str(payload.get("source_of_truth") or ""),
        "debug": payload,
    }


def _scene_output_from_payload(payload: dict[str, Any] | None = None) -> str:
    payload = dict(payload or {})
    for key in ("output_path", "local_path", "final_video_path", "raw_provider_video_path"):
        text = str(payload.get(key) or "").strip()
        if text and os.path.isfile(text) and os.path.getsize(text) > 0:
            return text
    return ""


def _canonical_product_video_workspace(job: dict | None = None) -> str:
    job = dict(job or {})
    job_id = str(job.get("job_id") or job.get("id") or job.get("project_id") or "product-video")
    identity_parts = (
        job_id,
        str(job.get("project_id") or ((job.get("project") or {}).get("project_id") if isinstance(job.get("project"), dict) else "") or ""),
        str(job.get("user_id") or ((job.get("project") or {}).get("user_id") if isinstance(job.get("project"), dict) else "") or ""),
        str(job.get("created_at") or job.get("confirmed_at") or ""),
        str(_scene_count(job)),
        str(job.get("scene_dispatch_mode") or "parallel"),
    )
    fingerprint = hashlib.sha256("|".join(identity_parts).encode("utf-8", errors="ignore")).hexdigest()[:12]
    return create_multiscene_workspace(f"product-video-{job_id}-{fingerprint}")


def _merge_manifest_scene_tasks(job: dict, recovered: list[dict[str, Any]]) -> dict:
    """Merge filesystem recovery behind current DB truth, one record per scene."""
    records: dict[int, dict[str, Any]] = {}
    for item in list(recovered or []) + _existing_scene_tasks(job):
        if not isinstance(item, dict):
            continue
        index = _scene_task_index(item, 0)
        if index <= 0:
            continue
        current = records.setdefault(index, {"scene_index": index, "scene_id": index})
        for key, value in item.items():
            if value not in (None, "", [], {}):
                current[key] = value
    merged = [records[index] for index in sorted(records)]
    return {
        **dict(job or {}),
        "scene_tasks": merged,
        "provider_scene_tasks": merged,
        "canonical_manifest_recovered": bool(recovered),
        "canonical_manifest_recovered_scene_indexes": [
            _scene_task_index(item, 0) for item in recovered if _scene_task_index(item, 0) > 0
        ],
    }


def _scene_specs_from_plan(plan: dict[str, Any]) -> list[SceneSpec]:
    specs: list[SceneSpec] = []
    for index, payload in enumerate(list(plan.get("scenes") or []), start=1):
        item = dict(payload or {})
        specs.append(
            SceneSpec(
                scene_id=_safe_int(item.get("scene_id"), index),
                title=str(item.get("title") or f"Scene {index}"),
                visual_prompt=str(item.get("visual_prompt") or item.get("video_prompt") or ""),
                video_prompt=str(item.get("video_prompt") or item.get("visual_prompt") or ""),
                narration_text=item.get("narration_text"),
                target_duration_sec=float(item.get("target_duration_sec") or PRODUCT_VIDEO_SCENE_SECONDS),
                aspect_ratio=str(item.get("aspect_ratio") or "9:16"),
                transition=item.get("transition"),
                seed_image_path=item.get("seed_image_path"),
                provider_params=dict(item.get("provider_params") or {}),
            )
        )
    return specs


def _product_video_addon_render_kwargs(
    addon_plan: dict,
    addon_materials: dict | None,
    *,
    bgm_audio_path: str | None = None,
) -> dict[str, Any]:
    materials = dict(addon_materials or {})
    if not materials.get("strict"):
        return {
            "bgm_audio_path": bgm_audio_path,
            "enable_voice": False,
            "enable_subtitle": bool(
                addon_plan.get("subtitle_enabled", True)
                and _has_user_facing_subtitle_text({"addon_plan": addon_plan})
            ),
            "enable_logo": _logo_enabled(addon_plan),
            "logo_text": str(addon_plan.get("logo_text") or ""),
            "logo_position": str(addon_plan.get("logo_position") or "bottom_right"),
        }
    return {
        "voice_audio_path": materials.get("voice_audio_path") or None,
        "voice_volume_percent": int(materials.get("voice_volume_percent") or 100),
        "enable_voice": bool(materials.get("voice_audio_path")),
        "bgm_audio_path": materials.get("bgm_audio_path") or None,
        "music_volume_percent": int(materials.get("music_volume_percent") or 20),
        "sfx_audio_paths": list(materials.get("sfx_audio_paths") or []),
        "sfx_assets": list(materials.get("sfx_assets") or []),
        "sfx_volume_percent": int(materials.get("sfx_volume_percent") or 35),
        "subtitle_path": materials.get("subtitle_path") or None,
        "enable_subtitle": bool(materials.get("subtitle_path")),
        "logo_path": materials.get("logo_path") or None,
        "enable_logo": bool(materials.get("logo_path")),
        "logo_position": str(materials.get("logo_position") or "top_left"),
        "watermark_text": str(materials.get("watermark_text") or ""),
        "watermark_position": str(materials.get("watermark_position") or "bottom_right"),
        "watermark_opacity_percent": int(materials.get("watermark_opacity_percent") or 45),
        "text_overlays": list(materials.get("text_overlays") or []),
        "transition_plan": list(materials.get("transition_plan") or []),
        "requested_addons": list(materials.get("requested_addons") or []),
    }


def _run_per_scene_provider_orchestrator(
    job: dict,
    workspace: str,
    *,
    provider_order: list[str],
    bgm_audio_path: str | None = None,
    addon_materials: dict | None = None,
    provider_events: list[dict[str, Any]],
    debug_results: list[dict[str, Any]],
) -> dict[str, Any]:
    plan = real_video_scene_plan(job)
    workspace = _canonical_product_video_workspace(job)
    scene_specs = _scene_specs_from_plan(plan)
    manifest = load_multiscene_manifest(
        workspace,
        job_id=str(job.get("job_id") or job.get("id") or ""),
        user_id=str(job.get("user_id") or ""),
    )
    recovered_scene_tasks = multiscene_manifest_scene_tasks(manifest)
    job = _merge_manifest_scene_tasks(job, recovered_scene_tasks)
    manifest_path = sync_multiscene_manifest(
        manifest,
        scene_specs=[dict(item or {}) for item in list(plan.get("scenes") or [])],
        scene_tasks=_existing_scene_tasks(job),
        status="dispatching_or_polling_scenes",
    )
    scene_outputs: dict[int, str] = {}
    hard_failures: list[dict[str, Any]] = []
    pending_seen = False
    dispatch_mode = product_video_scene_dispatch_mode(job)
    active_scene_slot = False
    os.makedirs(workspace, exist_ok=True)
    for scene_payload in plan.get("scenes") or []:
        if not isinstance(scene_payload, dict):
            continue
        scene_index = _safe_int(scene_payload.get("scene_id"), len(scene_outputs) + 1)
        scene = SimpleNamespace(**scene_payload)
        setattr(scene, "_toan_aas_job", dict(job or {}))
        raw_path = os.path.join(workspace, f"provider_scene_{scene_index:03d}.mp4")
        persisted_scene = product_video_scene_task_for_index(job, scene_index)
        persisted_clip = _scene_output_from_payload(persisted_scene)
        if persisted_clip and bool(persisted_scene.get("clip_valid") or persisted_scene.get("validation_passed")):
            scene_outputs[scene_index] = persisted_clip
            retained = {**persisted_scene, "scene_index": scene_index, "status": "scene_clip_validated", "clip_valid": True}
            debug_results.append(retained)
            provider_events.append(_provider_event_from_payload(job, scene_index, retained))
            continue
        if persisted_scene:
            active_scene_slot = _normalize_scene_task_status(
                persisted_scene.get("status") or persisted_scene.get("provider_status"),
                persisted_scene,
            ) in {"provider_running", "provider_not_start", PRODUCT_VIDEO_PROVIDER_STALLED_NOT_START}
        elif dispatch_mode == "sequential" and active_scene_slot:
            provider_key = str((provider_order or [""])[0] or "")
            queued = {
                "ok": False,
                "scene_index": scene_index,
                "scene_id": scene_index,
                "request_job_id": product_video_scene_request_id(job, scene_index),
                "status": "queued_waiting_for_slot",
                "provider_status": "queued_waiting_for_slot",
                "normalized_provider_status": "queued_waiting_for_slot",
                "continue_polling": True,
                "dispatch_state": "submit_in_progress",
                "dispatch_attempted": False,
                "dispatch_block_reason": "scheduled_after_scene_1_progress",
                "dispatch_idempotency_key": product_video_scene_dispatch_idempotency_key(
                    job.get("job_id") or job.get("id") or "",
                    scene_index,
                    provider_key,
                ),
                "provider_submit_called": False,
                "no_charge": True,
                "source_of_truth": "scene_dispatch_queue",
            }
            debug_results.append(queued)
            provider_events.append(_provider_event_from_payload(job, scene_index, queued))
            pending_seen = True
            continue
        try:
            result = asyncio.run(_render_scene_async(scene, raw_path, provider_order))
        except RealVideoRenderError as exc:
            diagnostics = dict(getattr(exc, "diagnostics", {}) or {})
            diagnostics.setdefault("scene_index", scene_index)
            diagnostics.setdefault("scene_id", scene_index)
            diagnostics.setdefault("request_job_id", product_video_scene_request_id(job, scene_index))
            debug_results.append(diagnostics)
            provider_events.append(_provider_event_from_payload(job, scene_index, diagnostics))
            if diagnostics.get("continue_polling") or str(diagnostics.get("provider_error") or diagnostics.get("blocker") or "") in PROVIDER_PENDING_BLOCKERS:
                pending_seen = True
                if diagnostics.get("provider_task_id_saved") or diagnostics.get("task_id_present") or diagnostics.get("provider_pending_task_id"):
                    active_scene_slot = True
                continue
            hard_failures.append(diagnostics)
            continue
        debug_results.append(dict(result))
        provider_events.append(_provider_event_from_payload(job, scene_index, result))
        if result.get("provider_task_id_saved") or result.get("task_id_present") or result.get("provider_pending_task_id"):
            active_scene_slot = True
        output_path = _scene_output_from_payload(result)
        if output_path:
            scene_outputs[scene_index] = output_path

    manifest_path = sync_multiscene_manifest(
        manifest,
        scene_tasks=[
            dict(item or {})
            for item in list(provider_events or []) + list(debug_results or [])
            if isinstance(item, dict)
        ],
        scene_clip_paths=scene_outputs,
        status="ready_to_finalize" if len(scene_outputs) >= _scene_count(job) else "waiting_for_scene_clips",
    )
    scene_tasks = product_video_scene_tasks_debug(
        job,
        provider_events=provider_events,
        debug_results=debug_results,
        scene_count=_scene_count(job),
    )
    manifest_path = sync_multiscene_manifest(
        manifest,
        scene_tasks=scene_tasks,
        scene_clip_paths=scene_outputs,
        status="ready_to_finalize" if len(scene_outputs) >= _scene_count(job) else "waiting_for_scene_clips",
    )
    scene_execution_audit = product_video_scene_execution_audit(job, scene_tasks)
    counts = product_video_scene_task_counts(scene_tasks)
    scenes_stalled_count = sum(1 for item in scene_tasks if bool(item.get("provider_stalled_not_start") or item.get("provider_scene_stalled")))
    fallback_count_by_scene = {
        str(_safe_int(item.get("scene_index"), 0)): _safe_int(item.get("fallback_count") or item.get("provider_fallback_count"), 0)
        for item in scene_tasks
        if _safe_int(item.get("scene_index"), 0)
    }
    scene_status_by_scene = {
        str(_safe_int(item.get("scene_index"), 0)): str(item.get("status") or "")
        for item in scene_tasks
        if _safe_int(item.get("scene_index"), 0)
    }
    fallback_eligible_by_scene = {
        str(_safe_int(item.get("scene_index"), 0)): bool(item.get("fallback_allowed"))
        for item in scene_tasks
        if _safe_int(item.get("scene_index"), 0)
    }
    fallback_reason_by_scene = {
        str(_safe_int(item.get("scene_index"), 0)): str(item.get("fallback_block_reason") or item.get("fallback_eligibility_reason") or "")
        for item in scene_tasks
        if _safe_int(item.get("scene_index"), 0)
    }
    selected_model_by_scene = {
        str(_safe_int(item.get("scene_index"), 0)): str(item.get("selected_model") or item.get("model") or "")
        for item in scene_tasks
        if _safe_int(item.get("scene_index"), 0)
    }
    scene_result_urls_by_index = {
        str(_safe_int(item.get("scene_index"), 0)): (
            "yes"
            if bool(
                _scene_task_has_provider_id(item)
                and (item.get("result_url_valid") or item.get("download_url_present") or item.get("provider_result_url_present"))
            )
            else "no"
        )
        for item in scene_tasks
        if _safe_int(item.get("scene_index"), 0)
    }
    scene_winner_by_scene = {
        str(_safe_int(item.get("scene_index"), 0)): {
            "task": str(item.get("scene_winner_task_masked") or ""),
            "provider": str(item.get("scene_winner_provider") or ""),
            "selected_at": str(item.get("winner_selected_at") or ""),
        }
        for item in scene_tasks
        if _safe_int(item.get("scene_index"), 0) and item.get("scene_winner_task")
    }
    scene_clip_validation_by_index: dict[str, dict[str, Any]] = {}
    for index, path in scene_outputs.items():
        clip_path = str(path or "")
        try:
            clip_size = os.path.getsize(clip_path) if clip_path and os.path.isfile(clip_path) else 0
        except OSError:
            clip_size = 0
        scene_clip_validation_by_index[str(index)] = {
            "ok": bool(clip_size > 0),
            "path_present": bool(clip_path),
            "bytes": int(clip_size or 0),
        }
    for index in range(1, _scene_count(job) + 1):
        scene_clip_validation_by_index.setdefault(
            str(index),
            {"ok": False, "path_present": False, "bytes": 0},
        )
    expected_scene_indexes = list(range(1, _scene_count(job) + 1))
    missing_scene_indexes = [index for index in expected_scene_indexes if index not in scene_outputs]
    scene_coverage_valid_bool = bool(len(scene_outputs) >= _scene_count(job))
    task_scene_index_map = {
        str((item.get("provider_task_id") or item.get("task_id") or item.get("provider_video_id") or item.get("video_id") or item.get("canonical_task_selected") or "")): _safe_int(item.get("scene_index"), 0)
        for item in scene_tasks
        if _safe_int(item.get("scene_index"), 0)
        and str((item.get("provider_task_id") or item.get("task_id") or item.get("provider_video_id") or item.get("video_id") or item.get("canonical_task_selected") or ""))
    }
    unknown_scene_task_ignored = any(
        bool((item.get("provider_task_id_masked") or item.get("provider_video_id_masked") or item.get("canonical_task_selected")))
        and not _safe_int(item.get("scene_index"), 0)
        for item in scene_tasks
    )
    active_scene = next(
        (
            item
            for item in scene_tasks
            if _normalize_scene_task_status(item.get("status"), item) != "clip_downloaded"
        ),
        scene_tasks[-1] if scene_tasks else {},
    )
    base = {
        "ok": False,
        "status": "processing" if pending_seen and not hard_failures else "failed",
        "orchestration_mode": PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE_8S,
        "provider_orchestration_mode": PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE_8S,
        "render_pipeline_mode": PRODUCT_VIDEO_RENDER_PIPELINE_HISTORICAL_CONCAT,
        "canonical_multiscene_engine": "b13_r18c",
        "canonical_multiscene_workspace": workspace,
        "canonical_multiscene_manifest_path": manifest_path,
        "manifest_path": manifest_path,
        "manifest_recovered": bool(recovered_scene_tasks),
        "manifest_recovered_scene_indexes": list(job.get("canonical_manifest_recovered_scene_indexes") or []),
        "target_duration_seconds": product_video_expected_duration_seconds(job),
        "clip_duration_seconds": product_video_scene_duration_seconds(job),
        "clip_count": _scene_count(job),
        "scene_duration_seconds": product_video_scene_duration_seconds(job),
        "expected_duration_seconds": product_video_expected_duration_seconds(job),
        "scene_count": _scene_count(job),
        "scene_tasks": scene_tasks,
        "scene_execution_audit": scene_execution_audit,
        "scene_forensic_root_cause": str(scene_execution_audit.get("root_cause") or ""),
        "scene_forensic_terminal_reason": str(scene_execution_audit.get("terminal_reason") or ""),
        "fallback_evaluated_count": _safe_int(scene_execution_audit.get("fallback_evaluated_count"), 0),
        "fallback_allowed_count": _safe_int(scene_execution_audit.get("fallback_allowed_count"), 0),
        "wallet_charge": _safe_int(scene_execution_audit.get("wallet_charge"), 0),
        "scene_tasks_total": len(scene_tasks),
        "scene_tasks_created_count": counts["scene_tasks_created_count"],
        "scene_tasks_submitted": counts["scene_tasks_submitted"],
        "scene_tasks_submitted_count": counts["scene_tasks_submitted_count"],
        "scene_tasks_completed": counts["scene_tasks_completed"],
        "clips_created_count": counts["scene_tasks_created_count"],
        "clips_submitted_count": counts["scene_tasks_submitted_count"],
        "clips_done_count": counts["scene_tasks_completed"],
        "clips_failed_count": sum(1 for item in scene_tasks if str(item.get("status") or "").strip().lower() in {"failed", "error"}),
        "scenes_total": counts["scenes_total"],
        "scenes_done": counts["scenes_done"],
        "scenes_pending": counts["scenes_pending"],
        "scenes_running": counts["scenes_running"],
        "scenes_stalled": scenes_stalled_count,
        "scenes_stalled_count": scenes_stalled_count,
        "scene_success_count": counts["scene_tasks_completed"],
        "fallback_count_by_scene": fallback_count_by_scene,
        "scene_status_by_scene": scene_status_by_scene,
        "fallback_eligible_by_scene": fallback_eligible_by_scene,
        "fallback_reason_by_scene": fallback_reason_by_scene,
        "selected_model_by_scene": selected_model_by_scene,
        "scene_coverage_expected": _scene_count(job),
        "scene_coverage_valid": len(scene_outputs),
        "scene_coverage_valid_bool": bool(scene_coverage_valid_bool),
        "scene_coverage_count": len(scene_outputs),
        "expected_scene_indexes": expected_scene_indexes,
        "missing_scene_indexes": missing_scene_indexes,
        "scene_plan_recovered": False,
        "scene_plan_source": "runtime_scene_plan",
        "task_scene_index_map": task_scene_index_map,
        "task_to_scene_index": task_scene_index_map,
        "task_scene_mapping_verified": bool(
            all(
                not item.get("result_url_valid") or item.get("task_scene_mapping_verified")
                for item in scene_tasks
            )
        ),
        "unknown_scene_task_ignored_for_coverage": bool(unknown_scene_task_ignored),
        "scene_result_urls_by_index": scene_result_urls_by_index,
        "result_task_id_by_scene": {
            str(_safe_int(item.get("scene_index"), 0)): str(item.get("result_task_id") or "")
            for item in scene_tasks
            if _safe_int(item.get("scene_index"), 0)
        },
        "result_url_source_by_scene": {
            str(_safe_int(item.get("scene_index"), 0)): str(item.get("result_url_source") or "")
            for item in scene_tasks
            if _safe_int(item.get("scene_index"), 0)
        },
        "authoritative_status_source_by_scene": {
            str(_safe_int(item.get("scene_index"), 0)): str(item.get("authoritative_status_source") or "")
            for item in scene_tasks
            if _safe_int(item.get("scene_index"), 0)
        },
        "phantom_result_prevented": any(bool(item.get("phantom_result_prevented")) for item in scene_tasks),
        "historical_status_ignored": any(bool(item.get("historical_status_ignored")) for item in scene_tasks),
        "success_result_overrode_stale_not_start": any(bool(item.get("success_result_overrode_stale_not_start")) for item in scene_tasks),
        "provider_status_conflict": any(bool(item.get("provider_status_conflict")) for item in scene_tasks),
        "provider_status_conflict_resolution": next(
            (
                str(item.get("provider_status_conflict_resolution") or "")
                for item in scene_tasks
                if item.get("provider_status_conflict_resolution")
            ),
            "",
        ),
        "scene_winner_by_scene": scene_winner_by_scene,
        "scene_winner_task_masked": str(active_scene.get("scene_winner_task_masked") or ""),
        "scene_winner_provider": str(active_scene.get("scene_winner_provider") or ""),
        "winner_selected_at": str(active_scene.get("winner_selected_at") or ""),
        "late_result_ignored_masked": list(active_scene.get("late_result_ignored_masked") or []),
        "duplicate_scene_result_prevented": any(bool(item.get("duplicate_scene_result_prevented")) for item in scene_tasks),
        "scene_clip_validation_by_index": scene_clip_validation_by_index,
        "canonical_scene_index": _safe_int(active_scene.get("canonical_scene_index") or active_scene.get("scene_index"), 0),
        "canonical_task_selected": str(active_scene.get("canonical_task_selected") or ""),
        "canonical_task_candidates_by_scene": active_scene.get("canonical_task_candidates_by_scene") or {},
        "canonical_task_reject_reasons": active_scene.get("canonical_task_reject_reasons") or {},
        "next_provider_or_model_candidate": next(
            (
                str((item.get("fallback_provider_order") or [""])[0])
                for item in scene_tasks
                if isinstance(item.get("fallback_provider_order"), list) and item.get("fallback_provider_order")
            ),
            "",
        ),
        "fallback_provider_candidate": next(
            (
                str(item.get("fallback_provider_candidate") or "")
                for item in scene_tasks
                if str(item.get("fallback_provider_candidate") or "")
            ),
            "",
        ),
        "current_scene_index": _safe_int(active_scene.get("scene_index"), counts["scenes_done"] + 1) if scene_tasks else 0,
        "current_scene": _safe_int(active_scene.get("scene_index"), counts["scenes_done"] + 1) if scene_tasks else 0,
        "current_clip_index": _safe_int(active_scene.get("scene_index"), counts["scenes_done"] + 1) if scene_tasks else 0,
        "current_scene_status": str(active_scene.get("status") or ""),
        "scene_not_start_elapsed": _safe_int(active_scene.get("scene_not_start_elapsed"), 0),
        "stall_threshold": _safe_int(active_scene.get("stall_threshold"), DEFAULT_PRODUCT_VIDEO_FIRST_SCENE_NOT_START_GRACE_SECONDS),
        "provider_stalled_not_start": any(bool(item.get("provider_stalled_not_start")) for item in scene_tasks),
        "fallback_scene_index": next((_safe_int(item.get("fallback_scene_index"), 0) for item in scene_tasks if _safe_int(item.get("fallback_scene_index"), 0)), 0),
        "fallback_allowed": any(bool(item.get("fallback_allowed")) for item in scene_tasks),
        "fallback_block_reason": next((str(item.get("fallback_block_reason") or "") for item in scene_tasks if str(item.get("fallback_block_reason") or "")), ""),
        "fallbackable_blocker": any(bool(item.get("fallbackable_blocker")) for item in scene_tasks),
        "fallback_eligibility_reason": next((str(item.get("fallback_eligibility_reason") or "") for item in scene_tasks if str(item.get("fallback_eligibility_reason") or "")), ""),
        "fallback_provider": next(
            (
                str((item.get("fallback_provider_order") or [""])[0])
                for item in scene_tasks
                if item.get("fallback_allowed") and isinstance(item.get("fallback_provider_order"), list) and item.get("fallback_provider_order")
            ),
            "",
        ),
        "fallback_submit_source": PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_SCENE_FALLBACK_ONCE if any(bool(item.get("fallback_allowed")) for item in scene_tasks) else "",
        "source_of_truth": str(active_scene.get("source_of_truth") or ("scene_stalled_not_start" if scenes_stalled_count else "scene_orchestrator")),
        "provider_events": provider_events,
        "provider_task_ids": [item.get("task_id") for item in provider_events if item.get("task_id")],
        "provider_video_ids": [item.get("video_id") for item in provider_events if item.get("video_id")],
        "provider_models": [item.get("model") for item in provider_events if item.get("model")],
        "provider_modes": [item.get("mode") for item in provider_events if item.get("mode")],
        "downloaded_clip_paths": [scene_outputs[index] for index in sorted(scene_outputs)],
        "local_clip_path_count": len(scene_outputs),
        "final_concat_required": bool(_scene_count(job) > 1),
        "concat_attempted": False,
        "concat_output_valid": False,
        "concat_status": "ready_to_concat" if len(scene_outputs) >= _scene_count(job) else "waiting_for_clips",
        "concat_ready": bool(len(scene_outputs) >= _scene_count(job)),
        "delivery_blocked_by_scene_coverage": bool(_scene_count(job) > 1 and not scene_coverage_valid_bool),
        "invalid_delivery_attempt_prevented": bool(_scene_count(job) > 1 and not scene_coverage_valid_bool),
        "artifact_valid_for_charge_after_coverage": bool(_scene_count(job) == 1 and len(scene_outputs) >= 1),
        "missing_scene_action": "poll" if missing_scene_indexes else "concat",
        "provider_router_called": True,
        "provider_submit_called": any(bool(item.get("provider_submit_called")) for item in debug_results if isinstance(item, dict)),
        "provider_poll_called": any(bool(item.get("provider_poll_called")) for item in debug_results if isinstance(item, dict)),
        "provider_task_id_saved": any(bool(item.get("provider_task_id_saved")) for item in debug_results if isinstance(item, dict)),
        "provider_attempted": True,
        "route_requires_provider": True,
        "placeholder_forbidden": True,
        "visual_source": "provider_pending" if len(scene_outputs) < _scene_count(job) else VISUAL_SOURCE_PROVIDER_MP4,
        "base_video_source": PROVIDER_VIDEO_SOURCE,
        "no_charge": True,
    }
    scene_ledger = video_project_queue_service.product_video_scene_ledger_state({}, job, base)
    base.update(scene_ledger)
    base["scene_coverage_valid"] = _safe_int(base.get("completed_scene_count"), 0)
    if hard_failures and base.get("processing_truth_applied"):
        # A failed dispatch for one scene cannot terminal the confirmed job
        # while another scene already has a live task or an actionable slot.
        base["terminal_suppressed_due_to_active_scene"] = bool(base.get("active_scene_indexes"))
        base["terminal_suppressed_due_to_dispatchable_scene"] = bool(base.get("dispatchable_scene_indexes"))
        base["state_repair_event"] = "scene_failure_deferred_while_processing_truth"
        base["deferred_scene_failures"] = [dict(item) for item in hard_failures]
        hard_failures = []
    if hard_failures:
        failure = dict(hard_failures[0])
        base.update(failure)
        base["ok"] = False
        base["continue_polling"] = False
        base["terminal_state"] = "failed_no_charge"
        base["final_decision"] = "failed_no_charge"
        base["status"] = "failed"
        base["source_of_truth"] = str(failure.get("source_of_truth") or base.get("source_of_truth") or "scene_failure")
        base["status_source_priority_used"] = "terminal_failed_no_charge"
        base["provider_state_source"] = "scene_failure"
        specific_terminal_reason = str(scene_execution_audit.get("terminal_reason") or "")
        base["provider_error"] = str(
            specific_terminal_reason
            or failure.get("provider_error")
            or failure.get("blocker")
            or PRODUCT_VIDEO_PROVIDER_STALLED_NOT_START
        )
        base["blocker"] = base["provider_error"]
        return _enforce_product_video_terminal_consistency(base, reason=base["provider_error"])
    if len(scene_outputs) < _scene_count(job):
        active_status = str(active_scene.get("status") or "")
        active_raw_status = str(active_scene.get("provider_status_raw") or active_status or "")
        active_is_not_start = _text_indicates_not_start(active_status, active_raw_status)
        normalized_pending_status = "not_start" if active_is_not_start else (active_status or "running")
        pending_error = "provider_not_start" if active_is_not_start else "provider_in_progress"
        base["continue_polling"] = True
        base["provider_error"] = pending_error
        base["blocker"] = pending_error
        base["provider_status"] = normalized_pending_status
        base["normalized_provider_status"] = normalized_pending_status
        base["raw_provider_status"] = active_raw_status
        base["provider_status_raw"] = active_raw_status
        base["canonical_status_before_not_start_override"] = str(base.get("canonical_status_before_not_start_override") or ("running" if active_is_not_start else normalized_pending_status))
        base["not_start_override_applied"] = bool(active_is_not_start)
        base["actual_provider_payload_status"] = str(active_scene.get("actual_provider_payload_status") or "")
        base["state_authority_source"] = str(active_scene.get("state_authority_source") or active_scene.get("provider_status_payload_source") or "")
        base["stale_not_start_blocker_ignored"] = bool(active_scene.get("stale_not_start_blocker_ignored"))
        base["not_start_decision_source"] = str(active_scene.get("not_start_decision_source") or ("actual_provider_payload_not_start" if active_is_not_start else ""))
        base["provider_progress_authoritative"] = bool(active_scene.get("provider_progress_authoritative"))
        base["provider_elapsed_seconds"] = max(_safe_int(base.get("provider_elapsed_seconds"), 0), _safe_int(active_scene.get("provider_elapsed_seconds"), 0), _safe_int(active_scene.get("scene_not_start_elapsed"), 0))
        base["provider_wait_elapsed_seconds"] = max(_safe_int(base.get("provider_wait_elapsed_seconds"), 0), _safe_int(active_scene.get("provider_wait_elapsed_seconds"), 0), _safe_int(base.get("provider_elapsed_seconds"), 0))
        base["terminal_state"] = "final_rendering"
        base["final_decision"] = "continue_polling"
        base["key4u_submit_suppressed"] = not bool(base.get("fallback_allowed"))
        base["key4u_submit_suppressed_reason"] = str(base.get("fallback_block_reason") or ("not_start_under_threshold" if active_is_not_start else "primary_provider_in_progress"))
        partial_ledger = video_project_queue_service.product_video_scene_ledger_state({}, job, base)
        base.update(partial_ledger)
        base["scene_coverage_valid"] = _safe_int(base.get("completed_scene_count"), 0)
        base["source_of_truth"] = "partial_scene_coverage" if base.get("completed_scene_count") else str(active_scene.get("source_of_truth") or "waiting_for_remaining_scenes")
        base["visual_source"] = "scene_clip_validated" if base.get("completed_scene_count") else "provider_pending"
        base["concat_attempted"] = False
        base["concat_status"] = "waiting_for_clips"
        base["concat_duration_seconds"] = 0
        base["final_duration_coverage_reason"] = "waiting_for_required_scenes"
        base["final_mp4_valid"] = False
        base["final_mp4_validated"] = False
        base["final_delivered"] = False
        return base

    addon = _addon_plan(job)
    render_addon_kwargs = _product_video_addon_render_kwargs(
        addon,
        addon_materials,
        bgm_audio_path=bgm_audio_path,
    )
    scene_audio_probes = [
        dict(video_final_output.probe_video(path) or {})
        for _, path in sorted(scene_outputs.items())
    ]
    preserve_scene_audio = bool(scene_audio_probes) and all(
        probe.get("ok") and probe.get("has_audio")
        for probe in scene_audio_probes
    )
    final_result = finalize_multiscene_scene_clips(
        user_id=str(job.get("user_id") or ""),
        job_id=str(job.get("job_id") or job.get("id") or ""),
        workspace_dir=workspace,
        scenes=scene_specs,
        scene_clip_paths=scene_outputs,
        manifest=manifest,
        **render_addon_kwargs,
        preserve_scene_audio=preserve_scene_audio,
        output_width=_canvas_size(_aspect_ratio(job))[0],
        output_height=_canvas_size(_aspect_ratio(job))[1],
    )
    final_result.update(base)
    final_result["finalizer_invoked"] = True
    final_result["finalizer_error"] = "" if final_result.get("final_video_path") else str(final_result.get("error") or "canonical_multiscene_finalizer_failed")
    final_result["canonical_multiscene_engine"] = "b13_r18c"
    final_result["canonical_multiscene_manifest_path"] = str(final_result.get("manifest_path") or manifest_path)
    final_result["ok"] = bool(final_result.get("final_video_path"))
    final_result["status"] = "completed" if final_result["ok"] else "error"
    final_result["continue_polling"] = False
    final_result["provider_error"] = ""
    final_result["blocker"] = ""
    final_result["visual_source"] = VISUAL_SOURCE_PROVIDER_MP4
    final_result["base_video_source"] = PROVIDER_VIDEO_SOURCE
    final_result["no_charge"] = bool(job.get("no_charge"))
    final_result["final_decision"] = "final_mp4_ready"
    final_result["source_of_truth"] = "final_mp4_validated"
    final_result["concat_status"] = "completed"
    final_result["concat_attempted"] = not bool(final_result.get("final_reused_from_manifest"))
    final_result["concat_attempt_count"] = max(
        1,
        _safe_int(job.get("concat_attempt_count"), 0)
        + (0 if final_result.get("final_reused_from_manifest") else 1),
    )
    final_result["concat_idempotency_key"] = f"product_video_concat:{job.get('job_id') or job.get('id') or 'job'}:{_scene_count(job)}"
    final_result["concat_output_valid"] = bool(final_result.get("final_video_path"))
    final_result["concat_duration_seconds"] = final_result.get("duration_sec") or final_result.get("duration_seconds") or 0
    final_result["final_mp4_valid"] = bool(final_result.get("final_video_path"))
    final_result["final_duration_seconds"] = final_result.get("duration_sec") or final_result.get("duration_seconds") or 0
    final_result["scene_coverage_count"] = len(scene_outputs)
    final_result["scene_coverage_valid"] = len(scene_outputs)
    final_result["scene_coverage_valid_bool"] = bool(len(scene_outputs) >= _scene_count(job) and final_result["concat_output_valid"])
    final_result["missing_scene_indexes"] = []
    final_result["delivery_blocked_by_scene_coverage"] = False
    final_result["invalid_delivery_attempt_prevented"] = False
    final_result["artifact_valid_for_charge_after_coverage"] = bool(final_result["scene_coverage_valid_bool"])
    final_result["missing_scene_action"] = "complete"
    final_result.update(video_project_queue_service.product_video_scene_ledger_state({}, job, final_result))
    final_result["scene_coverage_valid"] = _safe_int(final_result.get("completed_scene_count"), 0)
    return final_result


def _logo_enabled(addon_plan: dict) -> bool:
    return bool(addon_plan.get("logo_enabled") and _safe_text(addon_plan.get("logo_text"), 120))


def product_video_logo_overlay_xy(position: str, margin_x_ratio: float = PRODUCT_VIDEO_LOGO_MARGIN_X_RATIO, margin_y_ratio: float = PRODUCT_VIDEO_LOGO_MARGIN_Y_RATIO) -> tuple[str, str]:
    position = str(position or "top_right").strip().lower()
    mx = max(0.0, min(0.2, float(margin_x_ratio or PRODUCT_VIDEO_LOGO_MARGIN_X_RATIO)))
    my = max(0.0, min(0.2, float(margin_y_ratio or PRODUCT_VIDEO_LOGO_MARGIN_Y_RATIO)))
    x_map = {
        "top_left": f"main_w*{mx}",
        "center_left": f"main_w*{mx}",
        "bottom_left": f"main_w*{mx}",
        "top_center": "(main_w-overlay_w)/2",
        "center": "(main_w-overlay_w)/2",
        "bottom_center": "(main_w-overlay_w)/2",
        "top_right": f"main_w-overlay_w-main_w*{mx}",
        "center_right": f"main_w-overlay_w-main_w*{mx}",
        "bottom_right": f"main_w-overlay_w-main_w*{mx}",
    }
    y_map = {
        "top_left": f"main_h*{my}",
        "top_center": f"main_h*{my}",
        "top_right": f"main_h*{my}",
        "center_left": "(main_h-overlay_h)/2",
        "center": "(main_h-overlay_h)/2",
        "center_right": "(main_h-overlay_h)/2",
        "bottom_left": f"main_h-overlay_h-main_h*{my}",
        "bottom_center": f"main_h-overlay_h-main_h*{my}",
        "bottom_right": f"main_h-overlay_h-main_h*{my}",
    }
    return x_map.get(position, x_map["top_right"]), y_map.get(position, y_map["top_right"])


def build_product_video_logo_overlay_command(source_video: str, logo_path: str, output_video: str, material: dict | None = None) -> list[str]:
    material = dict(material or {})
    width_ratio = max(0.01, min(PRODUCT_VIDEO_LOGO_MAX_WIDTH_RATIO, float(material.get("logo_width_ratio") or PRODUCT_VIDEO_LOGO_DEFAULT_WIDTH_RATIO)))
    max_width_ratio = max(width_ratio, min(0.5, float(material.get("logo_max_width_ratio") or PRODUCT_VIDEO_LOGO_MAX_WIDTH_RATIO)))
    x_expr, y_expr = product_video_logo_overlay_xy(
        str(material.get("logo_position") or "top_right"),
        float(material.get("logo_margin_x_ratio") or PRODUCT_VIDEO_LOGO_MARGIN_X_RATIO),
        float(material.get("logo_margin_y_ratio") or PRODUCT_VIDEO_LOGO_MARGIN_Y_RATIO),
    )
    # scale2ref keeps the original logo aspect ratio. The min() guard keeps old
    # configs from making a large logo even if a wider value is present.
    filter_complex = (
        f"[1:v][0:v]scale2ref=w='min(main_w*{max_width_ratio},main_w*{width_ratio})':h=-1[logo][base];"
        f"[base][logo]overlay={x_expr}:{y_expr}:format=auto[v]"
    )
    return [
        _ffmpeg_binary(),
        "-y",
        "-i",
        str(source_video),
        "-i",
        str(logo_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(output_video),
    ]


def apply_product_video_logo_overlay(source_video: str, logo_path: str, output_video: str, material: dict | None = None) -> dict[str, Any]:
    if not _ffmpeg_binary():
        return {"ok": False, "reason": "ffmpeg_missing"}
    if not logo_path or not os.path.isfile(str(logo_path)):
        return {"ok": False, "reason": "logo_file_not_available_to_worker"}
    cmd = build_product_video_logo_overlay_command(source_video, logo_path, output_video, material)
    result = safe_run_ffmpeg(cmd, timeout=300)
    if result.returncode != 0:
        return {"ok": False, "reason": "logo_overlay_ffmpeg_failed", "stderr": (result.stderr or "")[-600:]}
    try:
        ensured = ensure_video_output(output_video)
    except RuntimeError as exc:
        return {"ok": False, "reason": f"logo_overlay_invalid_output:{exc}"}
    return {"ok": True, "path": ensured, "command": cmd}


def _addon_degrade_notes(addon_plan: dict, *, bgm_audio_path: str | None = None, job: dict | None = None) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    if addon_plan.get("voice_enabled"):
        notes.append(
            {
                "addon": "voice",
                "requested": True,
                "applied": False,
                "reason": "voice_addon_not_available_in_video_composer",
            }
        )
    if addon_plan.get("music_enabled"):
        source = str(addon_plan.get("music_source") or "none").strip().lower()
        notes.append(
            {
                "addon": "music",
                "requested": True,
                "applied": bool(bgm_audio_path),
                "source": source,
                "reason": "" if bgm_audio_path else "music_default_missing_or_unavailable",
            }
        )
    if addon_plan.get("subtitle_enabled"):
        subtitle_source_ready = _has_user_facing_subtitle_text(job)
        notes.append(
            {
                "addon": "subtitle",
                "requested": True,
                "applied": bool(subtitle_source_ready),
                "source": str(addon_plan.get("subtitle_source") or ""),
                "reason": "" if subtitle_source_ready else "subtitle_source_missing",
            }
        )
    if addon_plan.get("logo_enabled"):
        notes.append({"addon": "logo", "requested": True, "applied": _logo_enabled(addon_plan), "source": str(addon_plan.get("logo_source") or "text")})
    return notes


def _local_composer_enabled(job: dict | None = None) -> bool:
    del job
    return _env_flag("REAL_VIDEO_LOCAL_COMPOSER_FALLBACK_ENABLED", "1")


def _ffmpeg_binary() -> str:
    configured = str(os.getenv("FFMPEG_PATH") or os.getenv("LOCAL_FFMPEG_PATH") or "").strip()
    if configured and (os.path.isfile(configured) or shutil.which(configured)):
        return configured
    return shutil.which("ffmpeg") or ""


def _canvas_size(aspect_ratio: str) -> tuple[int, int]:
    value = str(aspect_ratio or "9:16").strip()
    if value == "16:9":
        return 960, 540
    if value == "1:1":
        return 720, 720
    if value == "4:5":
        return 720, 900
    return 540, 960


def _ffmpeg_text(value: Any, limit: int = 320) -> str:
    text = _safe_text(value, limit)
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def _scene_color(scene_id: int) -> str:
    palette = ("0b1f3a", "163b2f", "40213a", "1f3344", "3b2f16", "24351f")
    return palette[(max(1, int(scene_id or 1)) - 1) % len(palette)]


def _render_local_composer_scene(scene, raw_path: str) -> dict:
    ffmpeg = _ffmpeg_binary()
    if not ffmpeg:
        raise RealVideoRenderError("ffmpeg_missing")
    scene_id = _safe_int(getattr(scene, "scene_id", 1), 1)
    duration = max(1.0, min(8.0, float(getattr(scene, "target_duration_sec", 6.0) or 6.0)))
    width, height = _canvas_size(str(getattr(scene, "aspect_ratio", "") or "9:16"))
    target = os.path.abspath(raw_path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    color = _scene_color(scene_id)
    fade_out = max(0.1, duration - 0.3)
    primary_filter = (
        f"scale={width}:{height},"
        "format=yuv420p,"
        f"drawbox=x=36:y=36:w=iw-72:h=ih-72:color=white@0.08:t=4,"
        f"fade=t=in:st=0:d=0.25,fade=t=out:st={fade_out:.3f}:d=0.25"
    )
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x{color}:s={width}x{height}:r=30:d={duration:.3f}",
        "-vf",
        primary_filter,
        "-t",
        f"{duration:.3f}",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        target,
    ]
    result = safe_run_ffmpeg(cmd, timeout=max(60, int(duration * 30)))
    if result.returncode != 0:
        fallback = [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x{color}:s={width}x{height}:r=30:d={duration:.3f}",
            "-vf",
            "format=yuv420p",
            "-t",
            f"{duration:.3f}",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            target,
        ]
        result = safe_run_ffmpeg(fallback, timeout=max(60, int(duration * 30)))
    if result.returncode != 0:
        raise RealVideoRenderError("local_composer_ffmpeg_failed")
    return {"ok": True, "provider": "local_scene_composer", "output_path": ensure_video_output(target)}


def _render_local_scene_card_scene(scene, raw_path: str) -> dict:
    ffmpeg = _ffmpeg_binary()
    if not ffmpeg:
        raise RealVideoRenderError("ffmpeg_missing")
    scene_id = _safe_int(getattr(scene, "scene_id", 1), 1)
    duration = max(1.0, min(8.0, float(getattr(scene, "target_duration_sec", 6.0) or 6.0)))
    width, height = _canvas_size(str(getattr(scene, "aspect_ratio", "") or "9:16"))
    target = os.path.abspath(raw_path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    palette = (
        ("10233f", "32d3c8", "f5c542"),
        ("183428", "9af06a", "60a5fa"),
        ("321b36", "f472b6", "facc15"),
        ("1f2a44", "38bdf8", "f97316"),
        ("2b2615", "f59e0b", "22c55e"),
        ("1f2f25", "a3e635", "e879f9"),
    )
    base, accent, glow = palette[(max(1, scene_id) - 1) % len(palette)]
    fade_out = max(0.1, duration - 0.3)
    filter_graph = (
        "format=yuv420p,"
        f"drawbox=x=0:y=0:w=iw:h=ih:color=0x{base}@1.0:t=fill,"
        f"drawbox=x=iw*0.08:y=ih*0.10:w=iw*0.42:h=ih*0.26:color=0x{accent}@0.28:t=fill,"
        f"drawbox=x=iw*0.18:y=ih*0.46:w=iw*0.62:h=ih*0.12:color=white@0.10:t=fill,"
        f"drawbox=x=iw*0.52:y=ih*0.64:w=iw*0.34:h=ih*0.20:color=0x{glow}@0.22:t=fill,"
        "drawbox=x=24:y=24:w=iw-48:h=ih-48:color=white@0.08:t=3,"
        f"fade=t=in:st=0:d=0.25,fade=t=out:st={fade_out:.3f}:d=0.25"
    )
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x{base}:s={width}x{height}:r=30:d={duration:.3f}",
        "-vf",
        filter_graph,
        "-t",
        f"{duration:.3f}",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        target,
    ]
    result = safe_run_ffmpeg(cmd, timeout=max(60, int(duration * 30)))
    if result.returncode != 0:
        fallback = [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x{base}:s={width}x{height}:r=30:d={duration:.3f}",
            "-vf",
            "format=yuv420p,drawbox=x=24:y=24:w=iw-48:h=ih-48:color=white@0.08:t=3",
            "-t",
            f"{duration:.3f}",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            target,
        ]
        result = safe_run_ffmpeg(fallback, timeout=max(60, int(duration * 30)))
    if result.returncode != 0:
        raise RealVideoRenderError("local_scene_card_ffmpeg_failed")
    return {"ok": True, "provider": "local_scene_card", "output_path": ensure_video_output(target)}


def build_local_scene_composer(job: dict | None = None):
    del job

    def _render(scene, raw_path: str):
        return _render_local_composer_scene(scene, raw_path)

    return _render


def build_local_scene_card_renderer(job: dict | None = None):
    del job

    def _render(scene, raw_path: str):
        return _render_local_scene_card_scene(scene, raw_path)

    return _render


def _default_bgm_path(addon_plan: dict, workspace: str, duration_seconds: float) -> str | None:
    if not addon_plan.get("music_enabled"):
        return None
    source = str(addon_plan.get("music_source") or "none").strip().lower()
    if source in {"none", "off", "disabled", ""}:
        return None
    explicit = str(addon_plan.get("music_path") or addon_plan.get("music_audio_path") or addon_plan.get("bgm_audio_path") or "").strip()
    if explicit and os.path.isfile(explicit) and os.path.getsize(explicit) > 0:
        return explicit
    if source not in {"default", "saved", "vault", "system"}:
        return None
    ffmpeg = _ffmpeg_binary()
    if not ffmpeg:
        return None
    os.makedirs(workspace, exist_ok=True)
    duration = max(1.0, min(180.0, float(duration_seconds or 6.0)))
    volume = max(0.0, min(1.0, _safe_int(addon_plan.get("music_volume_percent"), 30) / 100.0))
    output = os.path.join(workspace, "default_bgm.m4a")
    result = safe_run_ffmpeg(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=220:sample_rate=44100:duration={duration:.3f}",
            "-filter:a",
            f"volume={max(0.01, volume * 0.12):.3f}",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            output,
        ],
        timeout=max(60, int(duration * 2)),
    )
    if result.returncode != 0:
        return None
    try:
        return ensure_video_output(output)
    except RuntimeError:
        return None


def _run_multiscene_render(
    job: dict,
    workspace: str,
    *,
    render_video_func,
    bgm_audio_path: str | None = None,
    addon_materials: dict | None = None,
) -> dict:
    addon = _addon_plan(job)
    render_addon_kwargs = _product_video_addon_render_kwargs(
        addon,
        addon_materials,
        bgm_audio_path=bgm_audio_path,
    )
    if product_video_orchestration_mode(job) == PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE_8S:
        per_scene_duration = float(product_video_scene_duration_seconds(job))
    else:
        per_scene_duration = max(1.0, min(8.0, product_video_expected_duration_seconds(job) / max(1, _scene_count(job))))
    output_width, output_height = _canvas_size(_aspect_ratio(job))
    return process_multiscene_video_pipeline(
        user_id=str(job.get("user_id") or ""),
        job_id=str(job.get("job_id") or job.get("id") or int(time.time())),
        user_prompt=original_prompt_from_job(job),
        workspace_dir=workspace,
        render_video_func=render_video_func,
        llm_func=real_video_llm_func_from_job(job),
        max_scenes=_scene_count(job),
        default_scene_duration=per_scene_duration,
        aspect_ratio=_aspect_ratio(job),
        **render_addon_kwargs,
        output_width=output_width,
        output_height=output_height,
    )


def render_real_video_job(job: dict, work_dir: str) -> dict:
    addon = _addon_plan(job)
    workspace = os.path.abspath(work_dir)
    total_duration = max(1.0, float(product_video_expected_duration_seconds(job)))
    is_product_video = bool(str(job.get("source") or "") == "product_video" or job.get("product_video"))
    addon_materials = product_video_materialize_addons(
        job,
        workspace=workspace,
        scene_count=_scene_count(job),
        scene_duration=product_video_scene_duration_seconds(job),
    )
    if addon_materials.get("strict") and not addon_materials.get("ok"):
        blocker = str(addon_materials.get("blocker") or "addon_materialization_failed")
        raise RealVideoRenderError(
            blocker,
            diagnostics={
                "ok": False,
                "status": "failed_no_charge",
                "terminal_state": "failed_no_charge",
                "final_decision": "failed_no_charge",
                "provider_attempted": False,
                "provider_submit_called": False,
                "provider_poll_called": False,
                "provider_submit_allowed": False,
                "no_charge": True,
                "addon_materialization": {
                    "contract_version": product_video_addon_materialization.CONTRACT_VERSION,
                    "requested_addons": list(addon_materials.get("requested_addons") or []),
                    "materialized_addons": list(addon_materials.get("materialized_addons") or []),
                    "blocker": blocker,
                    "silent_drop_allowed": False,
                },
                "blocker": blocker,
                "provider_error": blocker,
            },
        )
    job["_product_video_addon_materials"] = dict(addon_materials)
    strict_addons = bool(addon_materials.get("strict"))
    bgm_audio_path = (
        str(addon_materials.get("bgm_audio_path") or "").strip()
        if strict_addons
        else _default_bgm_path(addon, workspace, total_duration)
    ) or None
    degrade_notes = [] if strict_addons else _addon_degrade_notes(
        addon,
        bgm_audio_path=bgm_audio_path,
        job=job,
    )
    readiness = real_video_provider_readiness(job)
    product_type = _product_type(job)
    product_route = video_final_output.route_for_product_type(product_type)
    required_capability = product_video_required_capability(job)
    fallback_capability = str(product_route.get("fallback_capability") or "")
    render_mode = str(job.get("render_mode") or "").strip().lower().replace("-", "_")
    test_pattern = bool(job.get("test_pattern") or job.get("admin_video_delivery"))
    provider_call_requested = bool(job.get("provider_call") or job.get("real_renderer_required") or product_type == "video_ai_prompt")
    result: dict[str, Any] = {}
    provider_attempted = False
    provider_events: list[dict[str, Any]] = []
    provider_runtime_debug: list[dict[str, Any]] = []
    provider_error = ""
    fallback_used = False
    fallback_reason = ""
    provider_candidates = _provider_candidates_for_capability(readiness, required_capability)
    engine_adapter = str(job.get("engine_adapter") or product_route.get("engine_adapter") or "").strip().lower()
    orchestration_contract = str(
        job.get("orchestration_mode")
        or job.get("provider_orchestration_mode")
        or product_video_orchestration_mode(job)
        or ""
    ).strip().lower()
    explicit_local_renderer = bool(
        job.get("explicit_local_renderer")
        or job.get("local_renderer_selected")
        or job.get("validated_local_renderer_route")
    )
    product_contract_requires_provider = bool(
        engine_adapter in {"text_to_video", "text_to_video_or_scene_engine", "text_to_video_or_scene_video"}
        and orchestration_contract in {"per_scene_8s", "scene_orchestrator", "per_scene"}
        and not explicit_local_renderer
    )
    route_contract = product_video_route_contract(
        product_type,
        engine_adapter,
        orchestration_contract,
        explicit_local_renderer=explicit_local_renderer,
    )
    force_product_provider_route = bool(
        is_product_video
        and render_mode == "real"
        and not test_pattern
        and provider_call_requested
        and required_capability in PROVIDER_REQUIRED_CAPABILITIES
    )
    route_requires_provider = bool(
        is_product_video
        and (
            force_product_provider_route
            or route_contract.get("route_requires_provider")
            or _route_requires_provider(
                product_type,
                required_capability,
                fallback_capability,
                provider_ready=bool(provider_candidates),
                engine_adapter=engine_adapter,
                orchestration_mode=orchestration_contract,
                explicit_local_renderer=explicit_local_renderer,
            )
        )
    )
    provider_route_selected = bool(provider_candidates) if route_requires_provider else bool(readiness.get("ok"))
    local_fallback_allowed = not route_requires_provider
    local_image_sequence_used = False
    local_scene_card_used = False

    def _latest_provider_runtime_debug() -> dict[str, Any]:
        for item in reversed(provider_runtime_debug):
            if isinstance(item, dict) and item:
                return dict(item)
        for item in reversed(provider_events):
            if isinstance(item, dict) and isinstance(item.get("debug"), dict) and item.get("debug"):
                return dict(item.get("debug") or {})
        return {}

    def _merge_provider_runtime_debug(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = dict(payload or {})
        provider_debug = _latest_provider_runtime_debug()
        if not provider_debug:
            return data
        merged = dict(provider_debug)
        for key, value in data.items():
            if key in {
                "ok",
                "status",
                "error",
                "final_video_path",
                "master_video_path",
                "subtitle_path",
                "manifest_path",
                "scene_count",
                "duration_sec",
                "created_files",
                "failed_scenes",
                "stitch_attempted",
                "downloaded_clip_paths",
            }:
                merged[key] = value
            elif value not in (None, "", [], {}):
                merged[key] = value
            elif key not in merged:
                merged[key] = value
        return merged

    def _base_diagnostics(payload: dict[str, Any] | None = None, *, error: str = "") -> dict[str, Any]:
        data = _merge_provider_runtime_debug(payload)
        if error:
            data.setdefault("error", error)
        data["provider_attempted"] = bool(provider_attempted)
        data["provider_route_selected"] = bool(provider_route_selected)
        data["fallback_used"] = bool(fallback_used or data.get("fallback_used"))
        data["fallback_reason"] = str(data.get("fallback_reason") or fallback_reason or "")
        data["provider_events"] = data.get("provider_events") or provider_events
        orchestration_mode = product_video_orchestration_mode(job)
        scene_tasks = product_video_scene_tasks_debug(
            job,
            provider_events=data.get("provider_events") or provider_events,
            debug_results=provider_runtime_debug,
            scene_count=_scene_count(job),
        )
        completed_scenes = sum(1 for item in scene_tasks if str(item.get("status") or "").lower() in {"downloaded", "success", "completed"} or item.get("result_url_valid"))
        active_scene = next(
            (
                item
                for item in scene_tasks
                if str(item.get("status") or "").lower() not in {"downloaded", "success", "completed"}
            ),
            scene_tasks[-1] if scene_tasks else {},
        )
        data["orchestration_mode"] = orchestration_mode
        data["provider_orchestration_mode"] = orchestration_mode
        data["scene_duration_seconds"] = product_video_scene_duration_seconds(job)
        data["expected_duration_seconds"] = product_video_expected_duration_seconds(job)
        data["scene_count"] = _scene_count(job)
        data["scene_tasks"] = scene_tasks
        data["scene_tasks_total"] = len(scene_tasks)
        counts = product_video_scene_task_counts(scene_tasks)
        data.update(counts)
        data["scenes_stalled"] = sum(1 for item in scene_tasks if bool(item.get("provider_stalled_not_start") or item.get("provider_scene_stalled")))
        data["scenes_stalled_count"] = data["scenes_stalled"]
        data["scene_success_count"] = counts["scene_tasks_completed"]
        data["fallback_count_by_scene"] = {
            str(_safe_int(item.get("scene_index"), 0)): _safe_int(item.get("fallback_count") or item.get("provider_fallback_count"), 0)
            for item in scene_tasks
            if _safe_int(item.get("scene_index"), 0)
        }
        data["scene_status_by_scene"] = {
            str(_safe_int(item.get("scene_index"), 0)): str(item.get("status") or "")
            for item in scene_tasks
            if _safe_int(item.get("scene_index"), 0)
        }
        data["fallback_eligible_by_scene"] = {
            str(_safe_int(item.get("scene_index"), 0)): bool(item.get("fallback_allowed"))
            for item in scene_tasks
            if _safe_int(item.get("scene_index"), 0)
        }
        data["fallback_reason_by_scene"] = {
            str(_safe_int(item.get("scene_index"), 0)): str(item.get("fallback_block_reason") or item.get("fallback_eligibility_reason") or "")
            for item in scene_tasks
            if _safe_int(item.get("scene_index"), 0)
        }
        data["selected_model_by_scene"] = {
            str(_safe_int(item.get("scene_index"), 0)): str(item.get("selected_model") or item.get("model") or "")
            for item in scene_tasks
            if _safe_int(item.get("scene_index"), 0)
        }
        data["scene_tasks_completed"] = completed_scenes
        data["scene_tasks_submitted"] = sum(1 for item in scene_tasks if item.get("provider_task_id_masked") or item.get("provider_video_id_masked"))
        data["scene_tasks_submitted_count"] = data["scene_tasks_submitted"]
        data["current_scene_index"] = _safe_int(active_scene.get("scene_index"), completed_scenes + 1) if scene_tasks else 0
        data["current_scene"] = data["current_scene_index"]
        data["current_scene_status"] = str(active_scene.get("status") or "")
        data["scene_not_start_elapsed"] = _safe_int(active_scene.get("scene_not_start_elapsed"), 0)
        data["stall_threshold"] = _safe_int(active_scene.get("stall_threshold"), DEFAULT_PRODUCT_VIDEO_FIRST_SCENE_NOT_START_GRACE_SECONDS)
        data["provider_stalled_not_start"] = any(bool(item.get("provider_stalled_not_start")) for item in scene_tasks)
        data["fallback_scene_index"] = next((_safe_int(item.get("fallback_scene_index"), 0) for item in scene_tasks if _safe_int(item.get("fallback_scene_index"), 0)), 0)
        data["fallback_allowed"] = any(bool(item.get("fallback_allowed")) for item in scene_tasks)
        data["fallback_block_reason"] = next((str(item.get("fallback_block_reason") or "") for item in scene_tasks if str(item.get("fallback_block_reason") or "")), "")
        data["fallbackable_blocker"] = any(bool(item.get("fallbackable_blocker")) for item in scene_tasks)
        data["fallback_eligibility_reason"] = next((str(item.get("fallback_eligibility_reason") or "") for item in scene_tasks if str(item.get("fallback_eligibility_reason") or "")), "")
        data["fallback_provider"] = next(
            (
                str((item.get("fallback_provider_order") or [""])[0])
                for item in scene_tasks
                if item.get("fallback_allowed") and isinstance(item.get("fallback_provider_order"), list) and item.get("fallback_provider_order")
            ),
            "",
        )
        data["next_provider_or_model_candidate"] = str(
            data.get("fallback_provider")
            or next(
                (
                    str((item.get("fallback_provider_order") or [""])[0])
                    for item in scene_tasks
                    if isinstance(item.get("fallback_provider_order"), list) and item.get("fallback_provider_order")
                ),
                "",
            )
        )
        data["fallback_provider_candidate"] = str(
            data.get("fallback_provider_candidate")
            or data.get("next_provider_or_model_candidate")
            or ""
        )
        data["fallback_submit_source"] = str(data.get("fallback_submit_source") or (PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_CONFIRMED_SCENE_FALLBACK_ONCE if data.get("fallback_allowed") else ""))
        data["source_of_truth"] = str(data.get("source_of_truth") or active_scene.get("source_of_truth") or ("scene_stalled_not_start" if data["scenes_stalled"] else "scene_orchestrator"))
        data["final_concat_required"] = bool(orchestration_mode == PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE_8S and _scene_count(job) > 1)
        data["concat_ready"] = bool(completed_scenes >= len(scene_tasks) and scene_tasks)
        data["provider_task_ids"] = data.get("provider_task_ids") or [item.get("task_id") for item in provider_events if item.get("task_id")]
        data["provider_video_ids"] = data.get("provider_video_ids") or [item.get("video_id") for item in provider_events if item.get("video_id")]
        data["provider_models"] = data.get("provider_models") or [item.get("model") for item in provider_events if item.get("model")]
        data["provider_modes"] = data.get("provider_modes") or [item.get("mode") for item in provider_events if item.get("mode")]
        data["chunk_count"] = data.get("chunk_count") or _scene_count(job)
        data["downloaded_clip_paths"] = data.get("downloaded_clip_paths") or list(data.get("created_files") or [])[:80]
        data["stitch_attempted"] = bool(data.get("master_video_path") or data.get("final_video_path") or data.get("stitch_attempted"))
        data["provider_status"] = str(
            data.get("provider_status")
            or ("downloaded" if provider_events else ("attempted" if provider_attempted else "not_attempted"))
        )
        effective_provider_error = str(data.get("provider_error") or provider_error or "")
        if provider_attempted and not data["provider_task_ids"] and not effective_provider_error:
            effective_provider_error = str(data.get("error") or data.get("visual_classification") or "provider_attempt_no_artifact")
        data["provider_error"] = effective_provider_error
        data["provider_order"] = _provider_order(job)
        data["required_capability"] = required_capability
        data["required_capability_original"] = str(data.get("required_capability_original") or required_capability)
        data["normalized_capability_candidates"] = list(
            data.get("normalized_capability_candidates") or capability_options(required_capability)
        )
        data["fallback_capability"] = fallback_capability
        data["route_requires_provider"] = bool(route_requires_provider)
        data["route_requirement_source"] = (
            str(route_contract.get("route_requirement_source") or "")
            if route_contract.get("route_requires_provider") or route_contract.get("local_renderer_selected")
            else ("product_type_or_capability_contract" if route_requires_provider else "local_renderer_contract")
        )
        data["allowed_execution_modes"] = list(route_contract.get("allowed_execution_modes") or [])
        data["local_renderer_selected"] = bool(route_contract.get("local_renderer_selected"))
        data["provider_required_reason"] = str(route_contract.get("provider_required_reason") or "")
        data["route_requirement_product_contract"] = bool(product_contract_requires_provider)
        data["route_requirement_override"] = "explicit_valid_local_renderer" if explicit_local_renderer else ""
        data["route_block_reason"] = "" if provider_candidates else (
            "no_eligible_product_video_provider" if route_requires_provider else ""
        )
        data["local_fallback_allowed"] = bool(local_fallback_allowed)
        data["provider_router_called"] = bool(route_requires_provider or provider_attempted or data.get("provider_router_called"))
        data["provider_candidates_count"] = int(data.get("provider_candidates_count") or len(provider_candidates))
        data["selected_provider"] = str(
            data.get("selected_provider")
            or data.get("provider")
            or (provider_events[0].get("provider") if provider_events else "")
            or (provider_candidates[0] if provider_candidates else "")
        )
        data["provider_selection_blocker"] = str(
            data.get("provider_selection_blocker")
            or ("" if provider_candidates else ("provider_capability_missing" if route_requires_provider else ""))
        )
        data["provider_submit_called"] = bool(data.get("provider_submit_called") or provider_attempted)
        data["provider_submit_http_status"] = data.get("provider_submit_http_status") or data.get("provider_http_status") or 0
        data["provider_task_id_saved"] = bool(data.get("provider_task_id_saved") or data["provider_task_ids"])
        data["provider_poll_called"] = bool(data.get("provider_poll_called")) if "provider_poll_called" in data else bool(provider_attempted)
        data["provider_result_url_present"] = bool(
            data.get("provider_result_url_present")
            or data.get("result_url_present")
            or any((item or {}).get("download_url_present") for item in provider_events if isinstance(item, dict))
        )
        if not data.get("connector_renderer") and (route_requires_provider or provider_attempted):
            data["connector_renderer"] = PROVIDER_BRIDGE_RENDERER
        if not data.get("renderer") and (route_requires_provider or provider_attempted):
            data["renderer"] = PROVIDER_SCENE_RENDERER
        data["continue_polling"] = bool(data.get("continue_polling"))
        data["normalized_provider_status"] = str(data.get("normalized_provider_status") or data.get("provider_status") or "")
        data["base_video_source"] = str(
            data.get("base_video_source")
            or (
                PROVIDER_VIDEO_SOURCE
                if data.get("visual_source") == VISUAL_SOURCE_PROVIDER_MP4 or data.get("provider_task_ids")
                else ("placeholder" if data.get("visual_source") == VISUAL_SOURCE_LOCAL_PLACEHOLDER else ("local" if data.get("visual_source") else ""))
            )
        )
        data["visual_source"] = str(data.get("visual_source") or ("provider_pending" if provider_attempted else ""))
        data["placeholder_detected"] = bool(data.get("placeholder_detected") or False)
        data["placeholder_visual"] = bool(data.get("placeholder_visual") or False)
        data["placeholder_forbidden"] = bool(route_requires_provider)
        data["fallback_policy"] = fallback_capability
        data["provider_readiness"] = {
            "ok": bool(readiness.get("ok")),
            "ready_provider_order": readiness.get("ready_provider_order") or [],
            "first_ready_provider": readiness.get("first_ready_provider") or "",
            "enabled_count": readiness.get("enabled_count") or 0,
            "configured_count": readiness.get("configured_count") or 0,
            "enabled_providers": readiness.get("enabled_providers") or [],
            "configured_providers": readiness.get("configured_providers") or [],
            "missing_env": readiness.get("missing_env") or {},
        }
        data["enabled_providers"] = readiness.get("enabled_providers") or []
        data["configured_providers"] = readiness.get("configured_providers") or []
        data["missing_env"] = readiness.get("missing_env") or {}
        data["original_user_prompt"] = original_prompt_from_job(job)
        data["addon_degrade_notes"] = degrade_notes
        data["partial_addons"] = any(item.get("requested") and not item.get("applied") for item in degrade_notes)
        data["voice_requested"] = bool(addon.get("voice_enabled"))
        data["music_requested"] = bool(addon.get("music_enabled"))
        data["subtitle_requested"] = bool(addon.get("subtitle_enabled"))
        data["subtitle_user_facing_source"] = bool(_has_user_facing_subtitle_text(job))
        data["logo_requested"] = bool(addon.get("logo_enabled"))
        if bgm_audio_path:
            data["bgm_audio_path"] = bgm_audio_path
        data = _apply_pending_provider_dominance(data, job=job)
        data = _enforce_shopaikey_not_start_final_invariant(data, job=job)
        if _product_video_terminal_failure_should_dominate(data):
            data = _enforce_product_video_terminal_consistency(data)
        return _record_render_diagnostics(data)

    def _raise_render_error(reason: str, payload: dict[str, Any] | None = None) -> None:
        data = _base_diagnostics(payload, error=reason or REAL_VIDEO_RENDER_UNAVAILABLE)
        if is_product_video:
            data["no_charge"] = True
        if reason == FAILED_NO_REAL_VISUAL:
            data["visual_classification"] = FAILED_NO_REAL_VISUAL
            data["final_classification"] = FAILED_NO_REAL_VISUAL
        if reason == "provider_capability_missing":
            data["blocker"] = "provider_capability_missing"
            data["provider_error"] = "provider_capability_missing"
            data["provider_status"] = "not_attempted"
            data["provider_attempted"] = False
            data["public_message"] = PUBLIC_NO_VIDEO_PROVIDER_COPY
        raise RealVideoRenderError(reason or REAL_VIDEO_RENDER_UNAVAILABLE, diagnostics=data)

    local_image_paths = _local_image_sequence_paths(job) if is_product_video else []
    if is_product_video and _local_image_sequence_allowed(job, local_image_paths) and local_fallback_allowed:
        local_image_sequence_used = True
        local_workspace = os.path.join(workspace, "local_image_sequence")
        local_output = os.path.join(local_workspace, "final_output.mp4")
        result = video_final_output.render_local_image_sequence_video(
            local_image_paths,
            local_output,
            aspect_ratio=_aspect_ratio(job),
            duration_per_image=max(1.0, min(8.0, total_duration / max(1, len(local_image_paths)))),
            audio_path=_local_addon_audio_path(job) or bgm_audio_path or "",
            ffmpeg=_ffmpeg_binary(),
        )
        if not result.get("ok"):
            _raise_render_error(str(result.get("error") or "local_image_sequence_failed"), result)
        result["renderer"] = LOCAL_IMAGE_SEQUENCE_RENDERER
        result["provider_attempted"] = False
        result["provider_route_selected"] = False
        result["provider_events"] = []
        result["provider_task_ids"] = []
        result["provider_video_ids"] = []
        result["provider_models"] = []
        result["provider_modes"] = []
        result["provider_status"] = "not_needed"
        result["provider_error"] = ""
        result["fallback_used"] = False
        result["fallback_reason"] = ""
        result["visual_source"] = VISUAL_SOURCE_LOCAL_IMAGE_SEQUENCE
        result["base_video_source"] = "local"
        result["connector_renderer"] = LOCAL_IMAGE_SEQUENCE_RENDERER
        result["placeholder_detected"] = False
        result["placeholder_visual"] = False
        result["raw_prompt_burned_into_frame"] = False
        result["visual_classification"] = FINAL_AI_VIDEO
        result["final_classification"] = FINAL_AI_VIDEO
        result["no_charge"] = bool(job.get("no_charge"))
    elif is_product_video and not readiness.get("ok") and fallback_capability in {
        "clean_fail_provider_capability_missing",
        "delegate_or_clean_fail",
    }:
        provider_error = "provider_capability_missing"
        _raise_render_error(
            "provider_capability_missing",
            {
                "ok": False,
                "blocker": "provider_capability_missing",
                "provider_error": "provider_capability_missing",
                "provider_status": "not_attempted",
                "provider_attempted": False,
                "provider_readiness": readiness,
                "public_message": PUBLIC_NO_VIDEO_PROVIDER_COPY,
                "progress_percent": 40,
                "no_charge": True,
            },
        )
    elif readiness.get("ok") or not is_product_video:
        provider_attempted = True
        try:
            if is_product_video and product_video_orchestration_mode(job) == PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE_8S:
                result = _run_per_scene_provider_orchestrator(
                    job,
                    workspace,
                    provider_order=_provider_order(job),
                    bgm_audio_path=bgm_audio_path,
                    addon_materials=addon_materials,
                    provider_events=provider_events,
                    debug_results=provider_runtime_debug,
                )
            else:
                try:
                    real_scene_renderer = build_real_scene_renderer(job, provider_events, provider_runtime_debug)
                except TypeError:
                    real_scene_renderer = build_real_scene_renderer(job, provider_events)
                result = _run_multiscene_render(
                    job,
                    workspace,
                    render_video_func=real_scene_renderer,
                    bgm_audio_path=bgm_audio_path,
                    addon_materials=addon_materials,
                )
        except RealVideoRenderError as exc:
            provider_error = str(exc) or REAL_VIDEO_RENDER_UNAVAILABLE
            result = dict(getattr(exc, "diagnostics", {}) or {})
            result["ok"] = False
            result["error"] = provider_error
        except Exception as exc:
            provider_error = f"provider_render_failed:{type(exc).__name__}"
            result = {"ok": False, "error": provider_error}
        if not result.get("ok"):
            provider_error = str(result.get("error") or provider_error or REAL_VIDEO_RENDER_UNAVAILABLE)
    if (
        is_product_video
        and isinstance(result, dict)
        and not result.get("ok")
        and bool(result.get("continue_polling"))
        and str(result.get("terminal_state") or "") in {"", "final_rendering"}
    ):
        result["status"] = "processing"
        result["terminal_state"] = "final_rendering"
        result["final_decision"] = "continue_polling"
        result["no_charge"] = True
        result.setdefault("provider_error", provider_error or result.get("blocker") or "provider_in_progress")
        result.setdefault("blocker", result.get("provider_error") or "provider_in_progress")
        return _record_render_diagnostics(result)
    if is_product_video and not readiness.get("ok"):
        provider_error = str(readiness.get("reason") or "provider_capability_missing")
    if is_product_video and route_requires_provider and (not result or not result.get("ok")):
        blocker = str((result or {}).get("blocker") or (result or {}).get("provider_error") or provider_error or REAL_VIDEO_RENDER_UNAVAILABLE)
        if blocker == REAL_VIDEO_RENDER_UNAVAILABLE and not provider_candidates:
            blocker = "provider_capability_missing"
        _raise_render_error(blocker, result or {"ok": False, "provider_error": blocker, "provider_status": "failed" if provider_attempted else "not_attempted"})
    if is_product_video and not local_image_sequence_used and (not result or not result.get("ok")) and local_fallback_allowed and _local_scene_card_allowed(job):
        local_scene_card_used = True
        local_workspace = os.path.join(workspace, "local_scene_card")
        fallback_used = True
        fallback_reason = provider_error or "provider_unavailable"
        try:
            result = _run_multiscene_render(
                job,
                local_workspace,
                render_video_func=build_local_scene_card_renderer(job),
                bgm_audio_path=bgm_audio_path,
                addon_materials=addon_materials,
            )
        except RealVideoRenderError as exc:
            _raise_render_error(str(exc) or REAL_VIDEO_RENDER_UNAVAILABLE, dict(getattr(exc, "diagnostics", {}) or {}))
        result["renderer"] = LOCAL_SCENE_CARD_RENDERER
        result["provider_attempted"] = bool(provider_attempted)
        result["provider_route_selected"] = bool(provider_route_selected)
        result["provider_events"] = provider_events
        result["provider_task_ids"] = [item.get("task_id") for item in provider_events if item.get("task_id")]
        result["provider_video_ids"] = [item.get("video_id") for item in provider_events if item.get("video_id")]
        result["provider_models"] = [item.get("model") for item in provider_events if item.get("model")]
        result["provider_modes"] = [item.get("mode") for item in provider_events if item.get("mode")]
        result["provider_status"] = "downloaded" if provider_events else ("attempted" if provider_attempted else "not_needed")
        result["provider_error"] = provider_error
        result["fallback_used"] = True
        result["fallback_reason"] = fallback_reason
        result["visual_source"] = VISUAL_SOURCE_LOCAL_SCENE_CARD
        result["base_video_source"] = "local"
        result["connector_renderer"] = LOCAL_SCENE_CARD_RENDERER
        result["placeholder_detected"] = False
        result["placeholder_visual"] = False
        result["raw_prompt_burned_into_frame"] = _subtitle_raw_prompt_burn_detected(job, result)
        result["visual_classification"] = FINAL_AI_VIDEO if result.get("ok") and not result["raw_prompt_burned_into_frame"] else FAILED_NO_REAL_VISUAL
        result["final_classification"] = result["visual_classification"]
        result["no_charge"] = bool(job.get("no_charge"))
    if is_product_video and not local_image_sequence_used and (not result or not result.get("ok")) and local_fallback_allowed and _local_composer_enabled(job):
        local_workspace = os.path.join(workspace, "local_composer")
        fallback_used = True
        fallback_reason = provider_error or "provider_unavailable"
        try:
            result = _run_multiscene_render(
                job,
                local_workspace,
                render_video_func=build_local_scene_composer(job),
                bgm_audio_path=bgm_audio_path,
                addon_materials=addon_materials,
            )
        except RealVideoRenderError as exc:
            _raise_render_error(str(exc) or REAL_VIDEO_RENDER_UNAVAILABLE, dict(getattr(exc, "diagnostics", {}) or {}))
        result["renderer"] = LOCAL_PLACEHOLDER_RENDERER
        result["provider_attempted"] = bool(provider_attempted)
        result["provider_route_selected"] = bool(provider_route_selected)
        result["provider_events"] = provider_events
        result["provider_task_ids"] = [item.get("task_id") for item in provider_events if item.get("task_id")]
        result["provider_video_ids"] = [item.get("video_id") for item in provider_events if item.get("video_id")]
        result["provider_models"] = [item.get("model") for item in provider_events if item.get("model")]
        result["provider_modes"] = [item.get("mode") for item in provider_events if item.get("mode")]
        result["provider_status"] = "downloaded" if provider_events else ("attempted" if provider_attempted else "not_attempted")
        result["provider_error"] = provider_error
        result["fallback_used"] = True
        result["fallback_reason"] = fallback_reason
        result["visual_source"] = VISUAL_SOURCE_LOCAL_PLACEHOLDER
        result["base_video_source"] = "placeholder"
        result["connector_renderer"] = LOCAL_PLACEHOLDER_RENDERER
        result["placeholder_detected"] = True
        result["placeholder_visual"] = True
        result["raw_prompt_burned_into_frame"] = _subtitle_raw_prompt_burn_detected(job, result)
        result["visual_classification"] = PARTIAL_SIMPLE_VIDEO if result.get("ok") and not result["raw_prompt_burned_into_frame"] else FAILED_NO_REAL_VISUAL
        result["final_classification"] = result["visual_classification"]
        result["no_charge"] = True
    elif result and not local_image_sequence_used and not local_scene_card_used:
        result = _merge_provider_runtime_debug(result)
        result["renderer"] = PROVIDER_SCENE_RENDERER
        result["connector_renderer"] = PROVIDER_BRIDGE_RENDERER
        result["provider_attempted"] = bool(provider_attempted)
        result["provider_route_selected"] = bool(provider_route_selected)
        result["fallback_used"] = False
        result["fallback_reason"] = ""
        result["provider_events"] = provider_events
        result["provider_task_ids"] = [item.get("task_id") for item in provider_events if item.get("task_id")]
        result["provider_video_ids"] = [item.get("video_id") for item in provider_events if item.get("video_id")]
        result["provider_models"] = [item.get("model") for item in provider_events if item.get("model")]
        result["provider_modes"] = [item.get("mode") for item in provider_events if item.get("mode")]
        result["provider_status"] = "downloaded" if provider_events else ("attempted" if provider_attempted else "not_attempted")
        result["provider_error"] = provider_error
        result["visual_source"] = VISUAL_SOURCE_PROVIDER_MP4
        result["base_video_source"] = PROVIDER_VIDEO_SOURCE
        result["placeholder_detected"] = False
        result["placeholder_visual"] = False
        result["raw_prompt_burned_into_frame"] = _subtitle_raw_prompt_burn_detected(job, result)
        result["visual_classification"] = FINAL_AI_VIDEO if result.get("ok") and not result["raw_prompt_burned_into_frame"] else FAILED_NO_REAL_VISUAL
        result["final_classification"] = result["visual_classification"]
    result = _merge_provider_runtime_debug(result)
    final_path = str(result.get("final_video_path") or "")
    if not result.get("ok") or not final_path or not os.path.exists(final_path) or os.path.getsize(final_path) <= 0:
        _raise_render_error(str(result.get("error") or provider_error or REAL_VIDEO_RENDER_UNAVAILABLE), result)
    if is_product_video and result.get("visual_classification") == FAILED_NO_REAL_VISUAL:
        _raise_render_error(FAILED_NO_REAL_VISUAL, result)
    probe = video_final_output.probe_video(final_path)
    if probe.get("ok"):
        result["output_bytes"] = int(probe.get("bytes") or 0)
        result["output_duration"] = float(probe.get("duration") or 0)
        result["has_video"] = bool(probe.get("has_video"))
        result["has_audio"] = bool(probe.get("has_audio"))
        result["validation_status"] = "candidate_mp4_valid"
    else:
        result["validation_status"] = str(probe.get("reason") or "candidate_mp4_probe_failed")
    if is_product_video:
        duration_contract = product_video_duration_contract(job, result.get("output_duration"))
        result["raw_provider_video_path"] = final_path
        result["raw_duration_seconds"] = float(result.get("output_duration") or 0)
        result["expected_duration_seconds"] = duration_contract["expected_duration_seconds"]
        result["final_duration_contract"] = duration_contract
        result["finalizer_invoked"] = True
        if not duration_contract.get("ok"):
            result["terminal_state"] = "failed_no_charge"
            result["finalizer_error"] = duration_contract["reason"]
            result["no_charge"] = True
            _raise_render_error(str(duration_contract.get("reason") or "final_duration_invalid"), result)
        result["final_duration_seconds"] = float(result.get("output_duration") or 0)
        logo_material = product_video_logo_material(job)
        if logo_material.get("logo_enabled") and not strict_addons:
            result["logo_overlay_requested"] = True
            logo_path = str(logo_material.get("logo_path") or "")
            overlay_path = os.path.join(workspace, "final_with_logo.mp4")
            overlay = apply_product_video_logo_overlay(final_path, logo_path, overlay_path, logo_material)
            result["logo_overlay_result"] = overlay
            if not overlay.get("ok"):
                result["terminal_state"] = "failed_no_charge"
                result["logo_overlay_applied"] = False
                result["logo_overlay_error"] = str(overlay.get("reason") or "logo_overlay_failed")
                result["no_charge"] = True
                _raise_render_error(str(overlay.get("reason") or "logo_overlay_failed"), result)
            final_path = str(overlay.get("path") or overlay_path)
            result["final_video_path"] = final_path
            result["master_video_path"] = final_path
            result["logo_overlay_applied"] = True
            result["logo_overlay_position"] = str(logo_material.get("logo_position") or "")
            probe = video_final_output.probe_video(final_path)
            if probe.get("ok"):
                result["output_bytes"] = int(probe.get("bytes") or 0)
                result["output_duration"] = float(probe.get("duration") or 0)
                result["final_duration_seconds"] = float(probe.get("duration") or 0)
                result["has_video"] = bool(probe.get("has_video"))
                result["has_audio"] = bool(probe.get("has_audio"))
                result["validation_status"] = "candidate_mp4_valid_with_logo"
    if addon.get("music_enabled") and not result.get("has_audio"):
        for note in degrade_notes:
            if note.get("addon") == "music":
                note["applied"] = False
                note["reason"] = "music_mux_missing_audio_stream"
                break
    result["provider_order"] = _provider_order(job)
    result["provider_readiness"] = {"ok": bool(readiness.get("ok")), "ready_provider_order": readiness.get("ready_provider_order") or []}
    result["required_capability"] = required_capability
    result["required_capability_original"] = str(result.get("required_capability_original") or required_capability)
    result["normalized_capability_candidates"] = list(
        result.get("normalized_capability_candidates") or capability_options(required_capability)
    )
    result["fallback_capability"] = fallback_capability
    result["route_requires_provider"] = bool(route_requires_provider)
    result["route_requirement_source"] = (
        str(route_contract.get("route_requirement_source") or "")
        if route_contract.get("route_requires_provider") or route_contract.get("local_renderer_selected")
        else ("product_type_or_capability_contract" if route_requires_provider else "local_renderer_contract")
    )
    result["allowed_execution_modes"] = list(route_contract.get("allowed_execution_modes") or [])
    result["local_renderer_selected"] = bool(route_contract.get("local_renderer_selected"))
    result["provider_required_reason"] = str(route_contract.get("provider_required_reason") or "")
    result["route_requirement_product_contract"] = bool(product_contract_requires_provider)
    result["route_requirement_override"] = "explicit_valid_local_renderer" if explicit_local_renderer else ""
    result["route_block_reason"] = "" if provider_candidates else (
        "no_eligible_product_video_provider" if route_requires_provider else ""
    )
    result["local_fallback_allowed"] = bool(local_fallback_allowed)
    result["provider_router_called"] = bool(route_requires_provider or provider_attempted or result.get("provider_router_called"))
    result["provider_candidates_count"] = int(result.get("provider_candidates_count") or len(provider_candidates))
    result["selected_provider"] = str(
        result.get("selected_provider")
        or result.get("provider")
        or (provider_events[0].get("provider") if provider_events else "")
        or (provider_candidates[0] if provider_candidates else "")
    )
    result["provider_selection_blocker"] = str(
        result.get("provider_selection_blocker")
        or ("" if provider_candidates else ("provider_capability_missing" if route_requires_provider else ""))
    )
    result["provider_submit_called"] = bool(result.get("provider_submit_called") or provider_attempted)
    result["provider_submit_http_status"] = result.get("provider_submit_http_status") or result.get("provider_http_status") or 0
    result["provider_task_id_saved"] = bool(result.get("provider_task_id_saved") or result.get("provider_task_ids"))
    result["provider_poll_called"] = bool(result.get("provider_poll_called")) if "provider_poll_called" in result else bool(provider_attempted)
    result["provider_result_url_present"] = bool(
        result.get("provider_result_url_present")
        or result.get("result_url_present")
        or any((item or {}).get("download_url_present") for item in provider_events if isinstance(item, dict))
    )
    result["continue_polling"] = bool(result.get("continue_polling"))
    result["normalized_provider_status"] = str(result.get("normalized_provider_status") or result.get("provider_status") or "")
    result["base_video_source"] = str(
        result.get("base_video_source")
        or (
            PROVIDER_VIDEO_SOURCE
            if result.get("visual_source") == VISUAL_SOURCE_PROVIDER_MP4 or result.get("provider_task_ids")
            else ("placeholder" if result.get("visual_source") == VISUAL_SOURCE_LOCAL_PLACEHOLDER else "local")
        )
    )
    result["placeholder_forbidden"] = bool(route_requires_provider)
    result["fallback_policy"] = fallback_capability
    result["original_user_prompt"] = original_prompt_from_job(job)
    result["addon_degrade_notes"] = [] if strict_addons else degrade_notes
    result["partial_addons"] = (
        False
        if strict_addons
        else any(item.get("requested") and not item.get("applied") for item in degrade_notes)
    )
    requested_addon_names = set(str(item or "") for item in addon_materials.get("requested_addons") or [])
    result["voice_requested"] = bool(addon.get("voice_enabled") or "dubbing" in requested_addon_names)
    result["music_requested"] = bool(addon.get("music_enabled") or "music" in requested_addon_names)
    result["subtitle_requested"] = bool(addon.get("subtitle_enabled") or "subtitle" in requested_addon_names)
    result["subtitle_user_facing_source"] = bool(_has_user_facing_subtitle_text(job))
    result["logo_requested"] = bool(addon.get("logo_enabled") or "logo" in requested_addon_names)
    if strict_addons:
        result["addon_materialization"] = {
            "contract_version": product_video_addon_materialization.CONTRACT_VERSION,
            "requested_addons": list(addon_materials.get("requested_addons") or []),
            "materialized_addons": list(addon_materials.get("materialized_addons") or []),
            "silent_drop_allowed": False,
        }
        result["addon_application"] = dict(result.get("addon_application") or {
            "requested": list(addon_materials.get("requested_addons") or []),
            "applied": list(addon_materials.get("materialized_addons") or []),
            "missing": [],
        })
    if bgm_audio_path:
        result["bgm_audio_path"] = bgm_audio_path
    orchestration_mode = product_video_orchestration_mode(job)
    scene_tasks = product_video_scene_tasks_debug(
        job,
        provider_events=provider_events,
        debug_results=provider_runtime_debug,
        scene_count=_scene_count(job),
    )
    completed_scenes = sum(1 for item in scene_tasks if str(item.get("status") or "").lower() in {"downloaded", "success", "completed"} or item.get("result_url_valid"))
    active_scene = next(
        (
            item
            for item in scene_tasks
            if str(item.get("status") or "").lower() not in {"downloaded", "success", "completed"}
        ),
        scene_tasks[-1] if scene_tasks else {},
    )
    result["orchestration_mode"] = orchestration_mode
    result["provider_orchestration_mode"] = orchestration_mode
    result["scene_duration_seconds"] = product_video_scene_duration_seconds(job)
    result["expected_duration_seconds"] = product_video_expected_duration_seconds(job)
    result["scene_count"] = _scene_count(job)
    result["scene_tasks"] = scene_tasks
    result["scene_tasks_total"] = len(scene_tasks)
    counts = product_video_scene_task_counts(scene_tasks)
    result.update(counts)
    result["scene_tasks_completed"] = completed_scenes
    result["scene_tasks_submitted"] = sum(1 for item in scene_tasks if item.get("provider_task_id_masked") or item.get("provider_video_id_masked"))
    result["scene_tasks_submitted_count"] = result["scene_tasks_submitted"]
    result["current_scene_index"] = _safe_int(active_scene.get("scene_index"), completed_scenes + 1) if scene_tasks else 0
    result["current_scene"] = result["current_scene_index"]
    result["current_scene_status"] = str(active_scene.get("status") or "")
    result["scene_not_start_elapsed"] = _safe_int(active_scene.get("scene_not_start_elapsed"), 0)
    result["stall_threshold"] = _safe_int(active_scene.get("stall_threshold"), DEFAULT_PRODUCT_VIDEO_FIRST_SCENE_NOT_START_GRACE_SECONDS)
    result["provider_stalled_not_start"] = any(bool(item.get("provider_stalled_not_start")) for item in scene_tasks)
    result["fallback_scene_index"] = next((_safe_int(item.get("fallback_scene_index"), 0) for item in scene_tasks if _safe_int(item.get("fallback_scene_index"), 0)), 0)
    result["fallback_allowed"] = any(bool(item.get("fallback_allowed")) for item in scene_tasks)
    result["fallback_block_reason"] = next((str(item.get("fallback_block_reason") or "") for item in scene_tasks if str(item.get("fallback_block_reason") or "")), "")
    result["final_concat_required"] = bool(orchestration_mode == PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE_8S and _scene_count(job) > 1)
    result["concat_ready"] = bool(completed_scenes >= len(scene_tasks) and scene_tasks)
    result["chunk_count"] = result.get("chunk_count") or _scene_count(job)
    result["downloaded_clip_paths"] = result.get("downloaded_clip_paths") or list(result.get("created_files") or [])[:80]
    result["stitch_attempted"] = bool(result.get("master_video_path") or result.get("final_video_path") or result.get("stitch_attempted"))
    if product_type == "self_shot_scene_change":
        continuity = selfshot2_continuity_validation(
            job,
            result,
            scene_tasks=scene_tasks,
            debug_results=provider_runtime_debug,
        )
        result["selfshot2_continuity_validation"] = continuity
        result["continuity_validation_passed"] = continuity.get("ok") is True
        result["continuity_blocker"] = str(continuity.get("blocker") or "")
        result["continuity_metrics"] = dict(continuity.get("metrics") or {})
        result["continuity_evidence_scene_indexes"] = list(continuity.get("continuity_evidence_scene_indexes") or [])
        result["continuity_missing_scene_indexes"] = list(continuity.get("continuity_missing_scene_indexes") or [])
        if continuity.get("ok") is not True:
            result["delivery_blocked"] = True
            result["terminal_state"] = "failed_no_charge"
            result["no_charge"] = True
            _raise_render_error(str(continuity.get("blocker") or "selfshot2_continuity_validation_failed"), result)
    result["visual_classification"] = classify_visual_result(result)
    result["final_classification"] = result["visual_classification"]
    if result["visual_classification"] != FINAL_AI_VIDEO:
        result["no_charge"] = True
    result = _apply_pending_provider_dominance(result, job=job)
    _record_render_diagnostics(result)
    return result
