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
    "brand_pending_target",
    "brand_pending_position",
)

VOLUME_KEYS = ("source_audio", "dubbing", "music", "sfx", "environment")
TOGGLE_KEYS = ("source_audio", "dubbing", "music", "sfx", "subtitles")
STATUS_STAGES = (
    "review",
    "audio_addons",
    "logo_watermark",
    "summary",
    "quality",
    "invoice",
    "confirmed",
    "rendering",
    "validating",
    "delivering",
    "delivered",
    "failed",
)

CANONICAL_QUALITY_TIERS = (200, 300, 400, 500, 600, 800, 1000, 1200, 1500)
MULTI_SCENE_QUALITY_TIERS = tuple(item for item in CANONICAL_QUALITY_TIERS if item != 200)


PRODUCT_ADAPTERS: dict[str, dict[str, Any]] = {
    "video_ai_real": {
        "flow_owner": "scene3",
        "engine_route": "video_ai_canonical",
        "executor_product_type": "video_ai_prompt",
        "source_audio_available": False,
        "return_to": "vprofile|full_review",
        "required_capability": "text_to_video",
        "input_type": "text_prompt",
        "worker_owner": "product_video",
    },
    "video_ai_prompt": {
        "flow_owner": "scene3",
        "engine_route": "video_ai_canonical",
        "executor_product_type": "video_ai_prompt",
        "source_audio_available": False,
        "return_to": "vprofile|full_review",
        "required_capability": "text_to_video",
        "input_type": "text_prompt",
        "worker_owner": "product_video",
    },
    "video_ai_image": {
        "flow_owner": "scene3",
        "engine_route": "video_ai_canonical",
        "executor_product_type": "video_ai_image",
        "source_audio_available": False,
        "return_to": "vprofile|full_review",
        "required_capability": "image_to_video",
        "input_type": "scene_images",
        "worker_owner": "product_video",
    },
    "video_ai_video_reference": {
        "flow_owner": "scene3",
        "engine_route": "video_ai_canonical",
        "executor_product_type": "video_ai_video_reference",
        "source_audio_available": True,
        "return_to": "vprofile|full_review",
        "required_capability": "video_to_video",
        "input_type": "source_video",
        "worker_owner": "product_video",
    },
    "script_image_video": {
        "flow_owner": "scene3",
        "engine_route": "script_to_video",
        "executor_product_type": "script_to_video",
        "source_audio_available": False,
        "return_to": "vprofile|full_review",
        "required_capability": "text_to_video",
        "input_type": "long_script",
        "worker_owner": "product_video",
        "minimum_scene_count": 2,
        "supports_single_scene": False,
        "supported_quality_tiers": MULTI_SCENE_QUALITY_TIERS,
    },
    "storyboard_prompt": {
        "flow_owner": "storyboard",
        "engine_route": "storyboard_to_video",
        "executor_product_type": "storyboard_prompt",
        "source_audio_available": False,
        "return_to": "vprofile|full_review",
        "required_capability": "image_to_video",
        "input_type": "storyboard_frames",
        "worker_owner": "product_video",
        "minimum_scene_count": 2,
        "supports_single_scene": False,
        "supported_quality_tiers": MULTI_SCENE_QUALITY_TIERS,
    },
    "video_trend": {
        "flow_owner": "trend",
        "engine_route": "trend_video",
        "executor_product_type": "video_trend",
        "source_audio_available": False,
        "return_to": "vprofile|full_review",
        "required_capability": "text_to_video",
        "input_type": "trend_prompt",
        "worker_owner": "product_video",
    },
    "frame_video_local": {
        "flow_owner": "frame_video",
        "engine_route": "frame_video_render",
        "executor_product_type": "image_to_video",
        "source_audio_available": False,
        "return_to": "framevideo|review",
        "pricing_mode": "frame_video",
        "required_capability": "local_ffmpeg",
        "input_type": "image_sequence",
        "worker_owner": "frame_video",
    },
    "self_shot_scene_change": {
        "flow_owner": "selfshot2",
        "engine_route": "self_shot_scene_change",
        "executor_product_type": "self_shot_scene_change",
        "source_audio_available": True,
        "return_to": "vproduct|ss2|show|review",
        "required_capability": "video_to_video",
        "input_type": "source_video",
        "worker_owner": "selfshot2",
    },
    "self_shot_cinematic_transform": {
        "flow_owner": "selfshot3",
        "engine_route": "self_shot_cinematic_transform",
        "executor_product_type": "self_shot_cinematic_transform",
        "source_audio_available": True,
        "return_to": "vproduct|ss3|show|review",
        "required_capability": "video_to_video",
        "input_type": "source_video",
        "worker_owner": "selfshot3",
    },
    "video_idea": {
        "flow_owner": "scene3",
        "engine_route": "video_idea_to_product",
        "executor_product_type": "video_idea_to_product",
        "source_audio_available": False,
        "return_to": "vprofile|full_review",
        "required_capability": "text_to_video",
        "input_type": "idea_preset",
        "worker_owner": "product_video",
    },
    "multi_scene_film": {
        "flow_owner": "scene3",
        "engine_route": "multi_scene_film",
        "executor_product_type": "multi_scene_film",
        "source_audio_available": False,
        "return_to": "vprofile|full_review",
        "required_capability": "text_to_video",
        "input_type": "long_form_plan",
        "worker_owner": "product_video",
        "scene_duration_seconds": 600,
        "maximum_scene_count": 12,
        "supported_quality_tiers": MULTI_SCENE_QUALITY_TIERS,
        "execution_enabled": False,
        "execution_blocker": "long_video_under_upgrade",
    },
    "video_long": {
        "flow_owner": "video_long",
        "engine_route": "video_long",
        "executor_product_type": "multi_scene_film",
        "source_audio_available": False,
        "return_to": "vproduct|open|video_long",
        "public_enabled": False,
        "scene_duration_seconds": 600,
        "required_capability": "text_to_video",
        "input_type": "long_form_plan",
        "worker_owner": "product_video",
        "maximum_scene_count": 12,
        "supported_quality_tiers": MULTI_SCENE_QUALITY_TIERS,
        "execution_enabled": False,
        "execution_blocker": "long_video_under_upgrade",
    },
    "video_local_edit": {
        "flow_owner": "video_edit",
        "engine_route": "local_worker_ffmpeg",
        "executor_product_type": "video_local_edit",
        "source_audio_available": True,
        "return_to": "videoedit|review",
        "required_capability": "video_to_video",
        "input_type": "source_video",
        "worker_owner": "video_edit",
    },
}

PRODUCT_ADAPTER_ALIASES = {
    "video_edit": "video_local_edit",
    "video_ai_realistic": "video_ai_real",
    "trend_video": "video_trend",
    "script_to_video": "script_image_video",
    "storyboard_to_video": "storyboard_prompt",
    "frame_video": "frame_video_local",
    "image_to_video": "frame_video_local",
    "long_video": "multi_scene_film",
}


def adapter_for(product_type: str) -> dict[str, Any]:
    key = str(product_type or "video_ai_real").strip()
    adapter_key = PRODUCT_ADAPTER_ALIASES.get(key, key)
    adapter = PRODUCT_ADAPTERS.get(adapter_key) or PRODUCT_ADAPTERS["video_ai_real"]
    result = deepcopy(adapter)
    result["video_product_type"] = key if adapter_key in PRODUCT_ADAPTERS else "video_ai_real"
    result["adapter_key"] = adapter_key if adapter_key in PRODUCT_ADAPTERS else "video_ai_real"
    result["canonical_product_type"] = result["adapter_key"]
    result.setdefault("public_enabled", True)
    result.setdefault("public_planning_enabled", True)
    result.setdefault("execution_enabled", True)
    result.setdefault("execution_blocker", "")
    result.setdefault("scene_duration_seconds", 8)
    result.setdefault("minimum_scene_count", 1)
    result.setdefault("maximum_scene_count", 20)
    result.setdefault("supports_single_scene", True)
    result.setdefault("supported_quality_tiers", CANONICAL_QUALITY_TIERS)
    result.setdefault("pricing_mode", "canonical")
    result.setdefault("required_capability", "text_to_video")
    result.setdefault("input_type", "text_prompt")
    result.setdefault("output_type", "mp4")
    result.setdefault("worker_owner", "product_video")
    return result


def commercial_contract(product_type: str) -> dict[str, Any]:
    """Return the product contract used by catalog, invoice and confirmation.

    The contract contains no provider or worker health. Runtime readiness is a
    final-confirm concern and must never erase compatible public packages.
    """

    adapter = adapter_for(product_type)
    return {
        "product_type": str(adapter["canonical_product_type"]),
        "flow_owner": str(adapter["flow_owner"]),
        "engine_route": str(adapter["engine_route"]),
        "executor_product_type": str(adapter["executor_product_type"]),
        "pricing_mode": str(adapter["pricing_mode"]),
        "required_capability": str(adapter["required_capability"]),
        "input_type": str(adapter["input_type"]),
        "output_type": str(adapter["output_type"]),
        "worker_owner": str(adapter["worker_owner"]),
        "minimum_scene_count": max(1, int(adapter["minimum_scene_count"])),
        "maximum_scene_count": max(1, int(adapter["maximum_scene_count"])),
        "supports_single_scene": bool(adapter["supports_single_scene"]),
        "supported_quality_tiers": tuple(int(item) for item in adapter["supported_quality_tiers"]),
        "supported_package_tiers": tuple(int(item) for item in adapter["supported_quality_tiers"]),
        "scene_duration_seconds": max(1, int(adapter["scene_duration_seconds"])),
        "public_planning_enabled": bool(adapter["public_planning_enabled"]),
        "execution_enabled": bool(adapter["execution_enabled"]),
        "execution_blocker": str(adapter["execution_blocker"]),
    }


def package_compatibility(
    product_type: str,
    *,
    scene_count: int,
    ratio: str,
    quality_tier_id: int = 0,
    asset_ready: bool = True,
    input_valid: bool = True,
) -> dict[str, Any]:
    contract = commercial_contract(product_type)
    count = max(1, int(scene_count or 1))
    tier_id = int(quality_tier_id or 0)
    blockers: list[str] = []
    if not (contract["minimum_scene_count"] <= count <= contract["maximum_scene_count"]):
        blockers.append("scene_count_not_supported")
    if count == 1 and not contract["supports_single_scene"]:
        blockers.append("single_scene_not_supported")
    if tier_id and tier_id not in set(contract["supported_quality_tiers"]):
        blockers.append("quality_tier_not_supported")
    if not input_valid:
        blockers.append("input_not_ready")
    if not asset_ready:
        blockers.append("assets_not_ready")
    if str(ratio or "") not in {"9:16", "16:9", "1:1", "4:5", "keep"}:
        blockers.append("ratio_not_supported")
    return {
        **contract,
        "ok": not blockers,
        "blockers": blockers,
        "reason": blockers[0] if blockers else "",
        "scene_count": count,
        "ratio": str(ratio or "9:16"),
        "quality_tier_id": tier_id,
        "side_effects": {
            "job": 0,
            "outbox": 0,
            "provider_calls": 0,
            "generated_files": 0,
            "wallet_mutations": 0,
            "xu_charged": 0,
        },
    }


def status_contract(product_type: str) -> dict[str, Any]:
    contract = commercial_contract(product_type)
    product_stages = {
        "video_ai_real": ("planning", "preparing_assets", "rendering_scenes", "composing"),
        "video_trend": ("locking_trend", "rendering_scenes", "composing", "validating_mp4"),
        "script_image_video": ("locking_script", "rendering_scenes", "composing", "validating_mp4"),
        "storyboard_prompt": ("locking_storyboard", "preparing_images", "animating_scenes", "composing"),
        "self_shot_scene_change": ("analyzing_source", "changing_scenes", "continuity", "composing"),
        "self_shot_cinematic_transform": ("analyzing_source", "cinematic_transform", "continuity", "composing"),
        "frame_video_local": ("preparing_images", "rendering_transitions", "mixing_audio", "validating_mp4"),
        "multi_scene_film": ("locking_long_plan", "preparing_chapters", "rendering_chapters", "composing"),
    }
    return {
        "product_type": contract["product_type"],
        "engine_route": contract["engine_route"],
        "stages": (
            "received",
            "preparing",
            "rendering",
            "postprocessing",
            "validating_mp4",
            "delivering",
            "delivered",
        ),
        "product_stages": product_stages.get(
            str(contract["product_type"]),
            ("planning", "preparing_assets", "rendering", "postprocessing"),
        ),
        "delivery_requires_message_id": True,
        "receipt_after_delivery": True,
        "charge_after_receipt": True,
    }


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
        "brand_pending_target": "",
        "brand_pending_position": "",
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
    current["brand_pending_target"] = (
        str(current.get("brand_pending_target") or "")
        if str(current.get("brand_pending_target") or "") in {"logo", "watermark"}
        else ""
    )
    current["brand_pending_position"] = str(current.get("brand_pending_position") or "")
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
    compatibility = package_compatibility(
        str(current.get("video_product_type") or "video_ai_real"),
        scene_count=int(current.get("scene_count") or 1),
        ratio=str(current.get("ratio") or "9:16"),
        quality_tier_id=int(quality_tier_id or 0),
    )
    if not compatibility.get("ok"):
        raise ValueError(str(compatibility.get("reason") or "package_not_compatible"))
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
    current["invoice_id"] = str(
        f"pv:{current['video_session_id']}:{current['plan_revision']}:{current['quality_tier_id']}"
    )[:160]
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
    contract = commercial_contract(str(current.get("video_product_type") or "video_ai_real"))
    if not contract.get("execution_enabled"):
        raise ValueError(str(contract.get("execution_blocker") or "execution_disabled"))
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
        "summary": 9,
        "quality": 10,
        "invoice": 12,
        "confirmed": 20,
        "rendering": 55,
        "validating": 80,
        "delivering": 90,
        "delivered": 100,
        "failed": 0,
    }[stage]
