"""Safe in-process draft/status support for Architecture Studio."""

from __future__ import annotations

import copy
import os
import re
import time
from pathlib import Path, PurePath
from typing import Any


ARCHITECTURE_REFERENCE_MAX_BYTES = max(1, int(os.getenv("ARCHITECTURE_REFERENCE_MAX_BYTES", str(25 * 1024 * 1024))))
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov"}
FLOORPLAN_EXTENSIONS = IMAGE_EXTENSIONS | {".pdf"}
IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp"}
VIDEO_MIMES = {"video/mp4", "video/quicktime"}
PDF_MIMES = {"application/pdf"}

_DRAFTS: dict[int, dict[str, Any]] = {}
_LAST_ROUTE: dict[str, Any] = {}
_LAST_VALIDATION_ERROR = ""


def _clean(value: Any, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:limit]


def safe_copy(value: Any) -> Any:
    return copy.deepcopy(value)


def validate_reference_asset(asset: dict[str, Any], *, asset_type: str = "") -> dict[str, Any]:
    global _LAST_VALIDATION_ERROR
    file_name = _clean(asset.get("file_name") or "reference", 180)
    mime_type = _clean(asset.get("mime_type"), 120).lower()
    file_size = int(asset.get("file_size") or 0)
    file_id = _clean(asset.get("file_id"), 300)
    kind = _clean(asset_type or asset.get("asset_type") or "reference_image", 80)
    raw_path = _clean(asset.get("path"), 500)
    suffix = Path(file_name).suffix.lower()
    if not suffix and mime_type == "image/jpeg":
        suffix = ".jpg"
    if PurePath(file_name).name != file_name or ".." in PurePath(file_name).parts:
        reason = "path_traversal_blocked"
    elif raw_path and (".." in Path(raw_path).parts or Path(raw_path).is_absolute()):
        reason = "external_or_traversal_path_blocked"
    elif file_size <= 0 or file_size > ARCHITECTURE_REFERENCE_MAX_BYTES:
        reason = "file_size_invalid"
    elif not file_id and not raw_path:
        reason = "file_reference_missing"
    elif kind == "walkthrough_reference" and (suffix not in VIDEO_EXTENSIONS or mime_type not in VIDEO_MIMES):
        reason = "walkthrough_video_type_invalid"
    elif kind == "floorplan" and (suffix not in FLOORPLAN_EXTENSIONS or mime_type not in IMAGE_MIMES | PDF_MIMES):
        reason = "floorplan_type_invalid"
    elif kind != "walkthrough_reference" and kind != "floorplan" and (suffix not in IMAGE_EXTENSIONS or mime_type not in IMAGE_MIMES):
        reason = "reference_image_type_invalid"
    else:
        reason = ""
    if reason:
        _LAST_VALIDATION_ERROR = reason
        return {"ok": False, "reason": reason, "provider_called": False}
    _LAST_VALIDATION_ERROR = ""
    return {
        "ok": True,
        "reason": "",
        "asset": {
            "asset_type": kind,
            "file_id": file_id,
            "file_name": PurePath(file_name).name,
            "mime_type": mime_type,
            "file_size": file_size,
            "duration": max(0, int(asset.get("duration") or 0)),
            "stored_scope": "telegram_session_reference",
        },
        "provider_called": False,
        "hidden_analysis_called": False,
    }


def save_draft(user_id: int, draft: dict[str, Any]) -> dict[str, Any]:
    uid = int(user_id)
    saved = safe_copy(draft)
    saved.pop("provider_task_id", None)
    saved.pop("provider_secret", None)
    saved["user_id"] = uid
    saved["saved_at"] = time.time()
    saved["provider_task_created"] = False
    saved["charge_created"] = False
    _DRAFTS[uid] = saved
    return safe_copy(saved)


def load_draft(user_id: int) -> dict[str, Any]:
    item = _DRAFTS.get(int(user_id)) or {}
    if int(item.get("user_id") or 0) != int(user_id):
        return {}
    return safe_copy(item)


def delete_draft(user_id: int) -> bool:
    return _DRAFTS.pop(int(user_id), None) is not None


def active_draft_count() -> int:
    return len(_DRAFTS)


def record_route(user_id: int, route: dict[str, Any]) -> None:
    global _LAST_ROUTE
    _LAST_ROUTE = {
        "user_id": int(user_id),
        "profile_id": _clean(route.get("profile_id"), 80),
        "confidence": float(route.get("confidence") or 0.0),
        "matched_signals": list(route.get("matched_signals") or [])[:20],
        "missing_fields": list(route.get("missing_fields") or [])[:20],
        "preserve_constraints": list(route.get("preserve_constraints") or [])[:30],
        "prompt_present": bool(route.get("professional_image_prompt") or route.get("professional_video_prompt")),
        "negative_prompt_present": bool(route.get("negative_prompt")),
        "scene_count": len(route.get("scene_plan") or []),
        "requested_output": _clean(route.get("recommended_output"), 40),
        "destination_handoff_status": _clean(route.get("destination_handoff_status") or "draft_only", 80),
        "updated_at": time.time(),
    }


def record_handoff(user_id: int, status: str) -> None:
    if int(_LAST_ROUTE.get("user_id") or 0) != int(user_id):
        return
    _LAST_ROUTE["destination_handoff_status"] = _clean(status, 80) or "draft_only"
    _LAST_ROUTE["updated_at"] = time.time()


def status_payload(*, profile_count: int, profile_json_loaded: bool, router_ready: bool = True) -> dict[str, Any]:
    return {
        "profile_studio_enabled": True,
        "architecture_profile_count": int(profile_count),
        "profile_json_loaded": bool(profile_json_loaded),
        "router_ready": bool(router_ready),
        "image_handoff_ready": True,
        "video_handoff_ready": True,
        "reference_upload_enabled": True,
        "active_drafts_count": active_draft_count(),
        "last_route_profile": _clean(_LAST_ROUTE.get("profile_id"), 80) or "-",
        "last_route_confidence": float(_LAST_ROUTE.get("confidence") or 0.0),
        "last_validation_error": _clean(_LAST_VALIDATION_ERROR, 120) or "-",
        "provider_calls_from_profile_studio": False,
        "jobs_created_from_profile_studio": False,
        "outbox_created_from_profile_studio": False,
        "xu_charged_from_profile_studio": 0,
        "paths_exposed": False,
    }


def debug_payload(user_id: int | None = None) -> dict[str, Any]:
    route = safe_copy(_LAST_ROUTE)
    if user_id is not None and int(route.get("user_id") or 0) != int(user_id):
        draft = load_draft(int(user_id))
        generated = dict(draft.get("draft") or {})
        route = {
            "user_id": int(user_id),
            "profile_id": _clean(generated.get("profile_id") or draft.get("profile_id"), 80) or "-",
            "confidence": float(generated.get("confidence") or draft.get("confidence") or 0.0),
            "matched_signals": list(generated.get("matched_signals") or draft.get("matched_signals") or [])[:20],
            "missing_fields": list(generated.get("missing_fields") or draft.get("missing_fields") or [])[:20],
            "preserve_constraints": list(generated.get("preserve_constraints") or draft.get("preserve_constraints") or [])[:30],
            "prompt_present": bool(generated.get("professional_image_prompt") or generated.get("professional_video_prompt")),
            "negative_prompt_present": bool(generated.get("negative_prompt")),
            "scene_count": len(generated.get("scene_plan") or []),
            "requested_output": _clean(generated.get("recommended_output") or draft.get("requested_output"), 40),
            "destination_handoff_status": _clean(draft.get("destination_handoff_status") or "draft_only", 80),
        }
    route.pop("updated_at", None)
    route["provider_task_created_by_profile_studio"] = False
    route["charge_created_by_profile_studio"] = False
    route["raw_media_exposed"] = False
    route["private_path_exposed"] = False
    return route
