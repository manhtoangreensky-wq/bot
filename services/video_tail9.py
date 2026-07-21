"""Canonical commercial tail contracts for Product Video flows.

This module is intentionally pure. It owns shared tail state and validation,
while product-specific executors remain behind explicit route adapters.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


STATE_FIELDS = (
    "video_product_type",
    "video_flow_owner",
    "video_session_id",
    "plan_revision",
    "plan_approved",
    "scene_count",
    "ratio",
    "estimated_duration",
    "source_asset_ids",
    "audio_config",
    "addon_config",
    "logo_config",
    "watermark_config",
    "quality_tier_id",
    "package_id",
    "pricing_snapshot",
    "capability_snapshot",
    "invoice_id",
    "final_confirmed",
    "job_id",
    "engine_route",
    "status_stage",
    "delivery_message_id",
    "receipt_state",
    "charge_state",
    "return_to",
)

VOLUME_KEYS = ("source_audio", "dubbing", "music", "sfx", "environment")
TOGGLE_KEYS = ("source_audio", "dubbing", "music", "sfx", "subtitles")
STATUS_STAGES = (
    "review",
    "audio_addons",
    "logo_watermark",
    "quality",
    "invoice",
    "confirmed",
    "rendering",
    "validating",
    "delivering",
    "delivered",
    "failed",
)


PRODUCT_ADAPTERS: dict[str, dict[str, Any]] = {
    "video_ai_real": {
        "flow_owner": "scene3",
        "engine_route": "video_ai_canonical",
        "executor_product_type": "video_ai_prompt",
        "source_audio_available": False,
        "return_to": "vprofile|full_review",
    },
    "video_ai_prompt": {
        "flow_owner": "scene3",
        "engine_route": "video_ai_canonical",
        "executor_product_type": "video_ai_prompt",
        "source_audio_available": False,
        "return_to": "vprofile|full_review",
    },
    "video_ai_image": {
        "flow_owner": "scene3",
        "engine_route": "video_ai_canonical",
        "executor_product_type": "video_ai_image",
        "source_audio_available": False,
        "return_to": "vprofile|full_review",
    },
    "video_ai_video_reference": {
        "flow_owner": "scene3",
        "engine_route": "video_ai_canonical",
        "executor_product_type": "video_ai_video_reference",
        "source_audio_available": True,
        "return_to": "vprofile|full_review",
    },
    "script_image_video": {
        "flow_owner": "scene3",
        "engine_route": "script_to_video",
        "executor_product_type": "script_to_video",
        "source_audio_available": False,
        "return_to": "vprofile|full_review",
    },
    "storyboard_prompt": {
        "flow_owner": "storyboard",
        "engine_route": "storyboard_to_video",
        "executor_product_type": "storyboard_prompt",
        "source_audio_available": False,
        "return_to": "vprofile|full_review",
    },
    "video_trend": {
        "flow_owner": "trend",
        "engine_route": "trend_video",
        "executor_product_type": "video_trend",
        "source_audio_available": False,
        "return_to": "vprofile|full_review",
    },
    "frame_video_local": {
        "flow_owner": "frame_video",
        "engine_route": "frame_video_render",
        "executor_product_type": "image_to_video",
        "source_audio_available": False,
        "return_to": "framevideo|review",
    },
    "self_shot_scene_change": {
        "flow_owner": "selfshot2",
        "engine_route": "self_shot_scene_change",
        "executor_product_type": "self_shot_scene_change",
        "source_audio_available": True,
        "return_to": "vproduct|ss2|show|review",
    },
    "self_shot_cinematic_transform": {
        "flow_owner": "selfshot3",
        "engine_route": "self_shot_cinematic_transform",
        "executor_product_type": "self_shot_cinematic_transform",
        "source_audio_available": True,
        "return_to": "vproduct|ss3|show|review",
    },
    "video_idea": {
        "flow_owner": "scene3",
        "engine_route": "video_idea_to_product",
        "executor_product_type": "video_idea_to_product",
        "source_audio_available": False,
        "return_to": "vprofile|full_review",
    },
    "multi_scene_film": {
        "flow_owner": "scene3",
        "engine_route": "multi_scene_film",
        "executor_product_type": "multi_scene_film",
        "source_audio_available": False,
        "return_to": "vprofile|full_review",
    },
    "video_long": {
        "flow_owner": "video_long",
        "engine_route": "video_long",
        "executor_product_type": "multi_scene_film",
        "source_audio_available": False,
        "return_to": "vproduct|open|video_long",
        "public_enabled": False,
        "scene_duration_seconds": 600,
    },
    "video_local_edit": {
        "flow_owner": "video_edit",
        "engine_route": "local_worker_ffmpeg",
        "executor_product_type": "video_local_edit",
        "source_audio_available": True,
        "return_to": "videoedit|review",
    },
}

PRODUCT_ADAPTER_ALIASES = {
    "video_edit": "video_local_edit",
}


def adapter_for(product_type: str) -> dict[str, Any]:
    key = str(product_type or "video_ai_real").strip()
    adapter_key = PRODUCT_ADAPTER_ALIASES.get(key, key)
    adapter = PRODUCT_ADAPTERS.get(adapter_key) or PRODUCT_ADAPTERS["video_ai_real"]
    result = deepcopy(adapter)
    result["video_product_type"] = key if adapter_key in PRODUCT_ADAPTERS else "video_ai_real"
    result.setdefault("public_enabled", True)
    result.setdefault("scene_duration_seconds", 8)
    return result


def _volume(value: Any, default: int = 100) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(0, min(200, number))


def default_audio_config(*, source_audio_available: bool) -> dict[str, Any]:
    return {
        "source_audio_available": bool(source_audio_available),
        "source_audio": bool(source_audio_available),
        "dubbing": False,
        "music": False,
        "sfx": False,
        "subtitles": False,
        "volumes": {
            "source_audio": 100,
            "dubbing": 100,
            "music": 20,
            "sfx": 35,
            "environment": 100,
        },
        "ducking": True,
        "clipping_guard": True,
    }


def new_state(
    *,
    product_type: str,
    session_id: str,
    plan_revision: int = 1,
    scene_count: int = 1,
    ratio: str = "9:16",
    estimated_duration: int | None = None,
    source_asset_ids: list[str] | None = None,
    return_to: str = "",
) -> dict[str, Any]:
    adapter = adapter_for(product_type)
    count = max(1, int(scene_count or 1))
    duration = int(estimated_duration or count * int(adapter["scene_duration_seconds"]))
    state = {
        "video_product_type": adapter["video_product_type"],
        "video_flow_owner": adapter["flow_owner"],
        "video_session_id": str(session_id or "").strip(),
        "plan_revision": max(1, int(plan_revision or 1)),
        "plan_approved": True,
        "scene_count": count,
        "ratio": str(ratio or "9:16"),
        "estimated_duration": max(1, duration),
        "source_asset_ids": [str(item) for item in source_asset_ids or [] if str(item).strip()],
        "audio_config": default_audio_config(
            source_audio_available=bool(adapter["source_audio_available"]),
        ),
        "addon_config": {"automatic_text": [], "postprocessing": {}},
        "logo_config": {"enabled": False, "asset_file_id": "", "position": "bottom_right"},
        "watermark_config": {"enabled": False, "text": "", "position": "bottom_right", "opacity_percent": 45},
        "quality_tier_id": "",
        "package_id": "",
        "pricing_snapshot": {},
        "capability_snapshot": {},
        "invoice_id": "",
        "final_confirmed": False,
        "job_id": "",
        "engine_route": adapter["engine_route"],
        "status_stage": "review",
        "delivery_message_id": "",
        "receipt_state": "not_created",
        "charge_state": "not_charged",
        "return_to": str(return_to or adapter["return_to"]),
        "handled_callback_ids": [],
        "confirm_token": "",
    }
    return normalize_state(state)


def normalize_state(state: dict[str, Any]) -> dict[str, Any]:
    current = deepcopy(dict(state or {}))
    adapter = adapter_for(str(current.get("video_product_type") or "video_ai_real"))
    current["video_product_type"] = adapter["video_product_type"]
    current["video_flow_owner"] = str(current.get("video_flow_owner") or adapter["flow_owner"])
    current["video_session_id"] = str(current.get("video_session_id") or "").strip()
    current["plan_revision"] = max(1, int(current.get("plan_revision") or 1))
    current["scene_count"] = max(1, int(current.get("scene_count") or 1))
    current["ratio"] = str(current.get("ratio") or "9:16")
    current["estimated_duration"] = max(
        1,
        int(current.get("estimated_duration") or current["scene_count"] * int(adapter["scene_duration_seconds"])),
    )
    current["source_asset_ids"] = [
        str(item) for item in current.get("source_asset_ids") or [] if str(item).strip()
    ]
    audio = default_audio_config(source_audio_available=bool(adapter["source_audio_available"]))
    audio.update(dict(current.get("audio_config") or {}))
    audio["source_audio_available"] = bool(
        adapter["source_audio_available"]
        and audio.get("source_audio_available", adapter["source_audio_available"])
    )
    if not audio["source_audio_available"]:
        audio["source_audio"] = False
    volumes = dict(default_audio_config(source_audio_available=False)["volumes"])
    volumes.update(dict(audio.get("volumes") or {}))
    audio["volumes"] = {key: _volume(volumes.get(key)) for key in VOLUME_KEYS}
    audio["clipping_guard"] = True
    audio["ducking"] = bool(audio.get("ducking", True))
    current["audio_config"] = audio
    current["addon_config"] = dict(current.get("addon_config") or {})
    current["logo_config"] = dict(current.get("logo_config") or {})
    current["watermark_config"] = dict(current.get("watermark_config") or {})
    current["pricing_snapshot"] = dict(current.get("pricing_snapshot") or {})
    current["capability_snapshot"] = dict(current.get("capability_snapshot") or {})
    current["engine_route"] = adapter["engine_route"]
    current["status_stage"] = (
        str(current.get("status_stage") or "review")
        if str(current.get("status_stage") or "review") in STATUS_STAGES
        else "review"
    )
    current["handled_callback_ids"] = [
        str(item) for item in current.get("handled_callback_ids") or [] if str(item).strip()
    ][-100:]
    for field in STATE_FIELDS:
        current.setdefault(field, "")
    return current


def scope_key(state: dict[str, Any]) -> tuple[str, str, int]:
    current = normalize_state(state)
    return (
        str(current["video_product_type"]),
        str(current["video_session_id"]),
        int(current["plan_revision"]),
    )


def scope_matches(state: dict[str, Any], *, product_type: str, session_id: str, plan_revision: int) -> bool:
    return scope_key(state) == (
        str(product_type or ""),
        str(session_id or ""),
        max(1, int(plan_revision or 1)),
    )


def claim_callback(state: dict[str, Any], callback_query_id: str) -> tuple[dict[str, Any], bool]:
    current = normalize_state(state)
    token = str(callback_query_id or "").strip()
    if not token:
        return current, True
    handled = list(current.get("handled_callback_ids") or [])
    if token in handled:
        return current, False
    handled.append(token)
    current["handled_callback_ids"] = handled[-100:]
    return current, True


def toggle_audio(state: dict[str, Any], key: str) -> dict[str, Any]:
    current = normalize_state(state)
    name = str(key or "").strip()
    if name not in TOGGLE_KEYS:
        raise ValueError("unsupported_audio_toggle")
    audio = dict(current["audio_config"])
    if name == "source_audio" and not audio.get("source_audio_available"):
        raise ValueError("source_audio_unavailable")
    audio[name] = not bool(audio.get(name))
    current["audio_config"] = audio
    current["status_stage"] = "audio_addons"
    return normalize_state(current)


def set_volume(state: dict[str, Any], key: str, value: Any) -> dict[str, Any]:
    current = normalize_state(state)
    name = str(key or "").strip()
    if name not in VOLUME_KEYS:
        raise ValueError("unsupported_volume")
    if name == "source_audio" and not current["audio_config"].get("source_audio_available"):
        raise ValueError("source_audio_unavailable")
    audio = dict(current["audio_config"])
    volumes = dict(audio.get("volumes") or {})
    volumes[name] = _volume(value)
    audio["volumes"] = volumes
    current["audio_config"] = audio
    current["status_stage"] = "audio_addons"
    return normalize_state(current)


def set_capability(state: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    current = normalize_state(state)
    snapshot = deepcopy(dict(report or {}))
    snapshot["ok"] = bool(snapshot.get("ok"))
    snapshot.setdefault("engine_route", current["engine_route"])
    current["capability_snapshot"] = snapshot
    return current


def select_package(
    state: dict[str, Any],
    *,
    quality_tier_id: str,
    package_id: str,
    pricing_snapshot: dict[str, Any],
    capability_snapshot: dict[str, Any],
) -> dict[str, Any]:
    current = normalize_state(state)
    capability = dict(capability_snapshot or {})
    if not capability.get("ok"):
        raise ValueError(str(capability.get("reason") or "engine_route_unavailable"))
    pricing = deepcopy(dict(pricing_snapshot or {}))
    if int(pricing.get("total_xu") or pricing.get("price_xu") or 0) < 0:
        raise ValueError("invalid_pricing_snapshot")
    current["quality_tier_id"] = str(quality_tier_id or "")
    current["package_id"] = str(package_id or "")
    current["pricing_snapshot"] = pricing
    current["capability_snapshot"] = capability
    current["status_stage"] = "invoice"
    return current


def invoice_allowed(state: dict[str, Any]) -> tuple[bool, str]:
    current = normalize_state(state)
    if not current.get("plan_approved"):
        return False, "plan_not_approved"
    if not current.get("package_id") or not current.get("quality_tier_id"):
        return False, "package_not_selected"
    if not current.get("capability_snapshot", {}).get("ok"):
        return False, str(current.get("capability_snapshot", {}).get("reason") or "engine_route_unavailable")
    if not current.get("pricing_snapshot"):
        return False, "pricing_snapshot_missing"
    return True, "ok"


def confirm_once(state: dict[str, Any], confirm_token: str) -> tuple[dict[str, Any], bool]:
    current = normalize_state(state)
    allowed, reason = invoice_allowed(current)
    if not allowed:
        raise ValueError(reason)
    token = str(confirm_token or "").strip()
    if current.get("final_confirmed"):
        return current, False
    current["final_confirmed"] = True
    current["confirm_token"] = token
    current["status_stage"] = "confirmed"
    return current, True


def update_delivery_truth(
    state: dict[str, Any],
    *,
    final_mp4_valid: bool,
    delivery_message_id: str = "",
    receipt_created: bool = False,
    charged: bool = False,
) -> dict[str, Any]:
    current = normalize_state(state)
    message_id = str(delivery_message_id or "").strip()
    delivered = bool(final_mp4_valid and message_id)
    if charged and not (delivered and receipt_created):
        raise ValueError("charge_before_delivery_receipt")
    if receipt_created and not delivered:
        raise ValueError("receipt_before_delivery")
    current["delivery_message_id"] = message_id if delivered else ""
    current["receipt_state"] = "created" if receipt_created else "not_created"
    current["charge_state"] = "charged" if charged else "not_charged"
    current["status_stage"] = "delivered" if delivered else ("delivering" if final_mp4_valid else "validating")
    return current


def public_progress(state: dict[str, Any]) -> int:
    stage = normalize_state(state)["status_stage"]
    return {
        "review": 0,
        "audio_addons": 5,
        "logo_watermark": 8,
        "quality": 10,
        "invoice": 12,
        "confirmed": 20,
        "rendering": 55,
        "validating": 80,
        "delivering": 90,
        "delivered": 100,
        "failed": 0,
    }[stage]
