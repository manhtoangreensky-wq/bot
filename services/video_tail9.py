"""Canonical commercial tail contracts for Product Video flows.

This module is intentionally pure. It owns shared tail state and validation,
while product-specific executors remain behind explicit route adapters.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


TAIL_FLOW_VERSION = 18

STATE_FIELDS = (
    "tail_flow_version",
    "video_product_type",
    "execution_product_type",
    "executor_product_type",
    "required_capability",
    "input_type",
    "worker_owner",
    "video_flow_owner",
    "video_session_id",
    "plan_revision",
    "plan_approved",
    "scene_count",
    "ratio",
    "estimated_duration",
    "source_asset_ids",
    "content_source",
    "content_mode",
    "content_revision",
    "scene_content",
    "selected_prompt",
    "prompt_revision",
    "plan_status",
    "review_status",
    "audio_config",
    "audio_status",
    "addon_config",
    "logo_config",
    "logo_status",
    "watermark_config",
    "watermark_status",
    "summary_status",
    "quality_tier_id",
    "package_id",
    "pricing_snapshot",
    "capability_snapshot",
    "invoice_id",
    "final_confirmed",
    "job_id",
    "submit_user_id",
    "public_processing_code",
    "submitted_at",
    "execution_state",
    "engine_route",
    "status_stage",
    "delivery_message_id",
    "receipt_state",
    "charge_state",
    "return_to",
    "brand_pending_target",
    "brand_pending_position",
    "branding_return_to",
    "branding_back_to",
    "summary_return_to",
    "submit_preflight_snapshot",
)

VOLUME_KEYS = ("source_audio", "dubbing", "music", "sfx", "environment")
TOGGLE_KEYS = ("source_audio", "dubbing", "music", "sfx", "subtitles")
OPTIONAL_STATUSES = ("not_configured", "configured", "skipped")
STATUS_STAGES = (
    "content_ready",
    "logo_watermark",
    "summary",
    "review",
    "audio_addons",
    "quality",
    "invoice",
    "confirmed",
    "rendering",
    "validating",
    "delivering",
    "delivered",
    "failed",
)

CANONICAL_QUALITY_TIERS = (200, 300, 400, 500, 600, 700, 800, 1000, 1200, 1500)
LEGACY_LOCKED_QUALITY_TIERS = (200, 300, 400, 500, 600, 800, 1000, 1200, 1500)
MULTI_SCENE_QUALITY_TIERS = CANONICAL_QUALITY_TIERS
UIFLOW3_EXTENDED_QUALITY_TIERS = (
    200,
    300,
    400,
    500,
    600,
    700,
    800,
    1000,
    1200,
    1500,
)


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
        "supported_quality_tiers": UIFLOW3_EXTENDED_QUALITY_TIERS,
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
        "supported_quality_tiers": UIFLOW3_EXTENDED_QUALITY_TIERS,
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
        "supported_quality_tiers": UIFLOW3_EXTENDED_QUALITY_TIERS,
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
        "minimum_scene_count": 5,
        "supports_single_scene": False,
        "supported_quality_tiers": UIFLOW3_EXTENDED_QUALITY_TIERS,
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
        "pricing_mode": "canonical",
        "maximum_scene_count": 20,
        "supported_quality_tiers": UIFLOW3_EXTENDED_QUALITY_TIERS,
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
        "pricing_mode": "canonical",
        "maximum_scene_count": 20,
        "supported_quality_tiers": UIFLOW3_EXTENDED_QUALITY_TIERS,
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
        "scene_duration_seconds": 300,
        "maximum_scene_count": 20,
        "supported_quality_tiers": MULTI_SCENE_QUALITY_TIERS,
        "execution_enabled": True,
        "execution_blocker": "",
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
        "maximum_scene_count": 20,
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
    "long_video": "video_long",
}


VIDEO_AI_REAL_MODE_PRODUCTS = {
    "prompt_video": "video_ai_prompt",
    "image_video": "video_ai_image",
}


UNKNOWN_PRODUCT_ADAPTER = {
    "flow_owner": "",
    "engine_route": "",
    "executor_product_type": "",
    "source_audio_available": False,
    "return_to": "menu|main_video",
    "required_capability": "",
    "input_type": "",
    "output_type": "",
    "worker_owner": "",
    "public_enabled": False,
    "public_planning_enabled": False,
    "execution_enabled": False,
    "execution_blocker": "product_owner_missing",
    "scene_duration_seconds": 8,
    "minimum_scene_count": 1,
    "maximum_scene_count": 1,
    "supports_single_scene": False,
    "supported_quality_tiers": (),
    "pricing_mode": "none",
}


def adapter_for(product_type: str) -> dict[str, Any]:
    key = str(product_type or "").strip()
    adapter_key = PRODUCT_ADAPTER_ALIASES.get(key, key)
    known = adapter_key in PRODUCT_ADAPTERS
    adapter = PRODUCT_ADAPTERS.get(adapter_key) if known else UNKNOWN_PRODUCT_ADAPTER
    result = deepcopy(adapter)
    result["video_product_type"] = key if known else ""
    result["adapter_key"] = adapter_key if known else ""
    result["canonical_product_type"] = result["adapter_key"]
    result.setdefault("public_enabled", True)
    result.setdefault("public_planning_enabled", True)
    result.setdefault("execution_enabled", True)
    result.setdefault("execution_blocker", "")
    result.setdefault("scene_duration_seconds", 8)
    result.setdefault("minimum_scene_count", 1)
    result.setdefault("maximum_scene_count", 20)
    result.setdefault("supports_single_scene", True)
    result.setdefault("supported_quality_tiers", LEGACY_LOCKED_QUALITY_TIERS)
    result.setdefault("pricing_mode", "canonical")
    result.setdefault("required_capability", "text_to_video")
    result.setdefault("input_type", "text_prompt")
    result.setdefault("output_type", "mp4")
    result.setdefault("worker_owner", "product_video")
    return result


def execution_product_for_mode(product_type: str, entry_mode: str = "") -> str:
    """Resolve an internal executor without changing the public product owner."""

    product = str(product_type or "").strip()
    if product == "video_ai_real":
        return VIDEO_AI_REAL_MODE_PRODUCTS.get(
            str(entry_mode or "").strip(),
            product,
        )
    return product


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
    if not contract["product_type"]:
        blockers.append("product_owner_missing")
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
        "self_shot_scene_change": (
            "source_received",
            "subject_analyzed",
            "planning_scene_change",
            "changing_each_scene",
            "checking_continuity",
            "composing",
            "validating_mp4",
            "delivering",
        ),
        "self_shot_cinematic_transform": (
            "source_received",
            "subject_analyzed",
            "planning_cinematic_timeline",
            "transforming_environment",
            "transforming_wardrobe_effects",
            "checking_continuity",
            "composing",
            "validating_mp4",
            "delivering",
        ),
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
    execution_product_type: str = "",
    session_id: str,
    plan_revision: int = 1,
    scene_count: int = 1,
    ratio: str = "9:16",
    estimated_duration: int | None = None,
    source_asset_ids: list[str] | None = None,
    return_to: str = "",
) -> dict[str, Any]:
    public_adapter = adapter_for(product_type)
    execution_product = str(execution_product_type or "").strip() or execution_product_for_mode(
        product_type
    )
    adapter = adapter_for(execution_product)
    if not public_adapter["adapter_key"] or not adapter["adapter_key"]:
        raise ValueError("video_product_owner_required")
    count = max(1, int(scene_count or 1))
    duration = int(estimated_duration or count * int(adapter["scene_duration_seconds"]))
    state = {
        "tail_flow_version": TAIL_FLOW_VERSION,
        "video_product_type": public_adapter["video_product_type"],
        "execution_product_type": adapter["adapter_key"],
        "executor_product_type": adapter["executor_product_type"],
        "required_capability": adapter["required_capability"],
        "input_type": adapter["input_type"],
        "worker_owner": adapter["worker_owner"],
        "video_flow_owner": public_adapter["flow_owner"],
        "video_session_id": str(session_id or "").strip(),
        "plan_revision": max(1, int(plan_revision or 1)),
        "plan_approved": True,
        "scene_count": count,
        "ratio": str(ratio or "9:16"),
        "estimated_duration": max(1, duration),
        "source_asset_ids": [str(item) for item in source_asset_ids or [] if str(item).strip()],
        "content_source": "",
        "content_mode": "",
        "content_revision": 1,
        "scene_content": [],
        "selected_prompt": "",
        "prompt_revision": 0,
        "plan_status": "approved",
        "review_status": "not_ready",
        "audio_config": default_audio_config(
            source_audio_available=bool(adapter["source_audio_available"]),
        ),
        "audio_status": "not_configured",
        "addon_config": {"automatic_text": [], "postprocessing": {}},
        "logo_config": {
            "enabled": False,
            "asset_file_id": "",
            "file_size": 0,
            "position": "",
        },
        "logo_status": "not_configured",
        "watermark_config": {"enabled": False, "text": "", "position": "", "opacity_percent": 45},
        "watermark_status": "not_configured",
        "summary_status": "not_ready",
        "quality_tier_id": "",
        "package_id": "",
        "pricing_snapshot": {},
        "capability_snapshot": {},
        "invoice_id": "",
        "final_confirmed": False,
        "job_id": "",
        "submit_user_id": "",
        "public_processing_code": "",
        "submitted_at": "",
        "execution_state": "",
        "engine_route": adapter["engine_route"],
        "status_stage": "content_ready",
        "delivery_message_id": "",
        "receipt_state": "not_created",
        "charge_state": "not_charged",
        "return_to": str(return_to or adapter["return_to"]),
        "brand_pending_target": "",
        "brand_pending_position": "",
        "branding_return_to": "addon",
        "branding_back_to": "addon",
        "summary_return_to": "addon",
        "submit_preflight_snapshot": {},
        "handled_callback_ids": [],
        "confirm_token": "",
    }
    return normalize_state(state)


def normalize_state(state: dict[str, Any]) -> dict[str, Any]:
    current = deepcopy(dict(state or {}))
    try:
        stored_flow_version = int(current.get("tail_flow_version") or 0)
    except (TypeError, ValueError):
        stored_flow_version = 0
    public_product = str(current.get("video_product_type") or "")
    public_adapter = adapter_for(public_product)
    execution_product = str(current.get("execution_product_type") or "").strip()
    if not execution_product:
        execution_product = execution_product_for_mode(
            public_product,
            str(current.get("content_mode") or ""),
        )
    adapter = adapter_for(execution_product)
    current["tail_flow_version"] = TAIL_FLOW_VERSION
    current["video_product_type"] = public_adapter["video_product_type"]
    current["execution_product_type"] = adapter["adapter_key"]
    current["executor_product_type"] = str(adapter["executor_product_type"])
    current["required_capability"] = str(adapter["required_capability"])
    current["input_type"] = str(adapter["input_type"])
    current["worker_owner"] = str(adapter["worker_owner"])
    current["video_flow_owner"] = str(
        current.get("video_flow_owner") or public_adapter["flow_owner"]
    )
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
    current["content_source"] = str(current.get("content_source") or "").strip()
    current["content_mode"] = str(current.get("content_mode") or "").strip()
    current["content_revision"] = max(1, int(current.get("content_revision") or 1))
    current["scene_content"] = [
        deepcopy(item)
        for item in list(current.get("scene_content") or [])
        if isinstance(item, dict)
    ]
    current["selected_prompt"] = str(current.get("selected_prompt") or "").strip()
    current["prompt_revision"] = max(0, int(current.get("prompt_revision") or 0))
    current["plan_status"] = str(current.get("plan_status") or "approved")
    current["review_status"] = (
        str(current.get("review_status") or "not_ready")
        if str(current.get("review_status") or "not_ready") in {"not_ready", "ready"}
        else "not_ready"
    )
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
    logo = {
        "enabled": False,
        "asset_file_id": "",
        "file_size": 0,
        "position": "",
        **dict(current.get("logo_config") or {}),
    }
    logo["enabled"] = bool(logo.get("enabled"))
    logo["asset_file_id"] = str(logo.get("asset_file_id") or "").strip()
    raw_logo_file_size = logo.get("file_size")
    try:
        logo_file_size = (
            0
            if isinstance(raw_logo_file_size, bool)
            else int(raw_logo_file_size or 0)
        )
    except (TypeError, ValueError, OverflowError):
        logo_file_size = 0
    logo["file_size"] = max(0, min(logo_file_size, (1 << 63) - 1))
    logo["position"] = str(logo.get("position") or "").strip()
    if not logo["asset_file_id"]:
        logo["enabled"] = False
        logo["file_size"] = 0
        logo["position"] = ""
    watermark = {
        "enabled": False,
        "text": "",
        "position": "",
        "opacity_percent": 45,
        **dict(current.get("watermark_config") or {}),
    }
    watermark["enabled"] = bool(watermark.get("enabled"))
    watermark["text"] = str(watermark.get("text") or "").strip()
    watermark["position"] = str(watermark.get("position") or "").strip()
    try:
        watermark_opacity = int(watermark.get("opacity_percent") or 45)
    except (TypeError, ValueError):
        watermark_opacity = 45
    watermark["opacity_percent"] = max(0, min(100, watermark_opacity))
    if not watermark["text"]:
        watermark["enabled"] = False
        watermark["position"] = ""
    current["logo_config"] = logo
    current["watermark_config"] = watermark
    for field in ("audio_status", "logo_status", "watermark_status"):
        status = str(current.get(field) or "not_configured")
        current[field] = status if status in OPTIONAL_STATUSES else "not_configured"
    current["summary_status"] = (
        str(current.get("summary_status") or "not_ready")
        if str(current.get("summary_status") or "not_ready") in {"not_ready", "ready"}
        else "not_ready"
    )
    current["pricing_snapshot"] = dict(current.get("pricing_snapshot") or {})
    current["capability_snapshot"] = dict(current.get("capability_snapshot") or {})
    current["invoice_id"] = str(current.get("invoice_id") or "").strip()
    current["quality_tier_id"] = str(current.get("quality_tier_id") or "").strip()
    current["package_id"] = str(current.get("package_id") or "").strip()
    current["final_confirmed"] = bool(current.get("final_confirmed"))
    current["job_id"] = str(current.get("job_id") or "").strip()
    current["submit_user_id"] = str(current.get("submit_user_id") or "").strip()
    current["public_processing_code"] = str(current.get("public_processing_code") or "").strip()
    current["submitted_at"] = str(current.get("submitted_at") or "").strip()
    current["execution_state"] = str(current.get("execution_state") or "").strip()
    current["engine_route"] = adapter["engine_route"]
    current["status_stage"] = (
        str(current.get("status_stage") or "content_ready")
        if str(current.get("status_stage") or "content_ready") in STATUS_STAGES
        else "content_ready"
    )
    current["brand_pending_target"] = (
        str(current.get("brand_pending_target") or "")
        if str(current.get("brand_pending_target") or "") in {"logo", "watermark"}
        else ""
    )
    current["brand_pending_position"] = str(current.get("brand_pending_position") or "")
    branding_return_to = str(current.get("branding_return_to") or "addon")
    current["branding_return_to"] = (
        branding_return_to
        if branding_return_to in {"addon", "review"}
        else "addon"
    )
    current["branding_back_to"] = (
        str(current.get("branding_back_to") or "addon")
        if str(current.get("branding_back_to") or "addon") in {"addon", "review", "product_review"}
        else "addon"
    )
    current["summary_return_to"] = "addon"
    current["submit_preflight_snapshot"] = dict(current.get("submit_preflight_snapshot") or {})
    if stored_flow_version < TAIL_FLOW_VERSION:
        terminal_or_commercial = current["status_stage"] in {
            "quality", "invoice", "confirmed", "rendering", "validating",
            "delivering", "delivered", "failed",
        }
        if terminal_or_commercial:
            current["review_status"] = "ready"
            if current.get("audio_status") not in {"configured", "skipped"}:
                current["audio_status"] = "skipped"
            if current.get("logo_status") not in {"configured", "skipped"}:
                current["logo_status"] = "skipped"
            if current.get("watermark_status") not in {"configured", "skipped"}:
                current["watermark_status"] = "skipped"
            current["summary_status"] = "ready"
        else:
            current["review_status"] = "not_ready"
            current["summary_status"] = "not_ready"
            current["branding_return_to"] = "addon"
            current["branding_back_to"] = "addon"
            current["summary_return_to"] = "addon"
    current["handled_callback_ids"] = [
        str(item) for item in current.get("handled_callback_ids") or [] if str(item).strip()
    ][-100:]
    for field in STATE_FIELDS:
        current.setdefault(field, "")
    return current


def branding_back_callback(state: dict[str, Any] | None) -> str:
    """Return branding to the shared Add-on hub or its exact product owner."""

    current = normalize_state(dict(state or {}))
    adapter = adapter_for(str(current.get("video_product_type") or ""))
    if str(current.get("branding_back_to") or "") == "review":
        return "video_tail|review|open"
    if str(current.get("branding_back_to") or "") == "product_review":
        return str(adapter.get("return_to") or "video_tail|review|prompts")
    return "video_tail|addon|open"


def apply_content_contract(state: dict[str, Any], contract: dict[str, Any] | None) -> dict[str, Any]:
    """Copy an already-completed product content contract into the shared tail.

    Product flows own content selection.  The commercial tail only persists a
    normalized snapshot so Summary, pricing and invoice never reinterpret an
    already selected source or prompt.
    """

    current = normalize_state(state)
    source = dict(contract or {})
    content_source = str(source.get("content_source") or "").strip()
    content_mode = str(
        source.get("canonical_content_mode") or source.get("content_mode") or ""
    ).strip()
    selected_prompt = str(
        source.get("selected_prompt")
        or source.get("selected_prompt_text")
        or source.get("idea_selected_prompt")
        or ""
    ).strip()
    scene_content = next(
        (
            [deepcopy(item) for item in list(value or []) if isinstance(item, dict)]
            for value in (
                source.get("per_scene_content"),
                source.get("idea_scene_contents"),
                source.get("idea_scene_content"),
                source.get("scene_drafts"),
                source.get("video_prompts"),
                source.get("scene_plan") if isinstance(source.get("scene_plan"), list) else [],
                (source.get("scene_plan") or {}).get("scenes") if isinstance(source.get("scene_plan"), dict) else [],
                (source.get("plan") or {}).get("scenes") if isinstance(source.get("plan"), dict) else [],
                ((source.get("prompt_bundle") or {}).get("prompts") if isinstance(source.get("prompt_bundle"), dict) else []),
            )
            if value
        ),
        [],
    )
    if not selected_prompt and isinstance(source.get("prompt_bundle"), dict):
        selected_prompt = str(
            source.get("prompt_bundle", {}).get("summary_prompt")
            or source.get("prompt_bundle", {}).get("master_prompt")
            or (source.get("prompt_bundle", {}).get("prompts") or [""])[0]
            or ""
        ).strip()
    if content_source:
        current["content_source"] = content_source
    if content_mode:
        current["content_mode"] = content_mode
    if scene_content:
        current["scene_content"] = scene_content
    if selected_prompt:
        current["selected_prompt"] = selected_prompt
    current["content_revision"] = max(
        int(current.get("content_revision") or 1),
        int(source.get("content_revision") or source.get("plan_revision") or 1),
    )
    current["prompt_revision"] = max(
        int(current.get("prompt_revision") or 0),
        int(source.get("selected_prompt_revision") or source.get("prompt_revision") or (1 if selected_prompt else 0)),
    )
    if source.get("plan_status"):
        current["plan_status"] = str(source.get("plan_status") or "approved")
    current["plan_approved"] = bool(source.get("plan_approved", current.get("plan_approved", True)))
    return normalize_state(current)


def apply_planning_audio_contract(
    state: dict[str, Any],
    postproduction_addons: dict[str, Any] | None,
    *,
    planning_complete: bool,
) -> dict[str, Any]:
    """Mirror the single planning-audio owner into the commercial tail.

    Scene planning remains authoritative because dialogue, subtitles and audio
    choices affect scene duration. The commercial tail only carries the same
    values forward to Summary, invoice and the executor contract.
    """

    current = normalize_state(state)
    entries = dict(postproduction_addons or {})
    audio = dict(current.get("audio_config") or {})
    volumes = dict(audio.get("volumes") or {})
    addon_config = deepcopy(dict(current.get("addon_config") or {}))
    before_audio = deepcopy(audio)
    before_addons = deepcopy(addon_config)
    before_status = str(current.get("audio_status") or "not_configured")

    addon_config["postprocessing"] = {
        str(key): deepcopy(dict(entry))
        for key, entry in entries.items()
        if isinstance(entry, dict)
    }

    for key in TOGGLE_KEYS:
        entry = dict(entries.get(key) or {})
        enabled = bool(entry.get("enabled"))
        if key == "source_audio" and not audio.get("source_audio_available"):
            enabled = False
        audio[key] = enabled
        value = dict(entry.get("value") or {}) if isinstance(entry.get("value"), dict) else {}
        selected_volume = value.get("volume_percent", value.get("volume"))
        if key in volumes and selected_volume not in (None, ""):
            volumes[key] = _volume(selected_volume, volumes[key])

    audio["volumes"] = volumes
    current["audio_config"] = audio
    current["addon_config"] = addon_config
    if planning_complete:
        current["audio_status"] = (
            "configured" if any(bool(audio.get(key)) for key in TOGGLE_KEYS) else "skipped"
        )

    if (
        before_audio != audio
        or before_addons != addon_config
        or before_status != current.get("audio_status")
    ):
        current["summary_status"] = "not_ready"
        current["review_status"] = "not_ready"
    return normalize_state(current)


def mark_audio_complete(state: dict[str, Any], *, skipped: bool = False) -> dict[str, Any]:
    current = normalize_state(state)
    audio = dict(current.get("audio_config") or {})
    enabled = any(bool(audio.get(key)) for key in TOGGLE_KEYS)
    current["audio_status"] = "configured" if enabled and not skipped else "skipped"
    current["summary_status"] = "not_ready"
    current["review_status"] = "not_ready"
    current["status_stage"] = "audio_addons"
    return normalize_state(current)


def content_contract_ready(state: dict[str, Any]) -> bool:
    current = normalize_state(state)
    adapter = adapter_for(str(current.get("video_product_type") or ""))
    if not adapter.get("adapter_key"):
        return False
    if str(current.get("video_product_type") or "") in {"multi_scene_film", "video_long"}:
        return bool(current.get("plan_approved"))
    prompt_ready = bool(current.get("selected_prompt")) or any(
        str(
            scene.get("provider_prompt")
            or scene.get("video_prompt")
            or scene.get("prompt")
            or ""
        ).strip()
        for scene in current.get("scene_content") or []
        if isinstance(scene, dict)
    )
    source_ready = bool(current.get("source_asset_ids")) and str(adapter.get("input_type") or "") in {
        "source_video", "scene_images", "storyboard_frames",
    }
    return bool(current.get("plan_approved") and (prompt_ready or source_ready))


def mark_review_complete(state: dict[str, Any]) -> dict[str, Any]:
    current = normalize_state(state)
    current["review_status"] = (
        "ready"
        if content_contract_ready(current) and addon_complete(current)
        else "not_ready"
    )
    current["summary_status"] = current["review_status"]
    current["status_stage"] = "review"
    return normalize_state(current)


def addon_complete(state: dict[str, Any]) -> bool:
    """Return whether all optional Add-on choices have an explicit outcome."""

    current = normalize_state(state)
    return all(
        current.get(field) in {"configured", "skipped"}
        for field in ("audio_status", "logo_status", "watermark_status")
    )


def mark_addon_complete(state: dict[str, Any]) -> dict[str, Any]:
    """Finish Add-on without discarding any configured audio or branding."""

    current = normalize_state(state)
    audio = dict(current.get("audio_config") or {})
    if current.get("audio_status") not in {"configured", "skipped"}:
        current["audio_status"] = (
            "configured" if any(bool(audio.get(key)) for key in TOGGLE_KEYS) else "skipped"
        )

    logo = dict(current.get("logo_config") or {})
    if current.get("logo_status") not in {"configured", "skipped"}:
        current["logo_status"] = (
            "configured"
            if logo.get("enabled") and logo.get("asset_file_id") and logo.get("position")
            else "skipped"
        )

    watermark = dict(current.get("watermark_config") or {})
    if current.get("watermark_status") not in {"configured", "skipped"}:
        current["watermark_status"] = (
            "configured"
            if watermark.get("enabled") and watermark.get("text") and watermark.get("position")
            else "skipped"
        )

    current["review_status"] = "not_ready"
    current["summary_status"] = "not_ready"
    current["status_stage"] = "audio_addons"
    return normalize_state(current)


def prepare_review(state: dict[str, Any]) -> dict[str, Any]:
    """Open Review without silently approving what the customer has not confirmed."""

    current = normalize_state(state)
    current["summary_status"] = (
        "ready" if content_contract_ready(current) and addon_complete(current) else "not_ready"
    )
    current["status_stage"] = "review"
    return normalize_state(current)


def mark_branding_skipped(state: dict[str, Any]) -> dict[str, Any]:
    current = normalize_state(state)
    current["logo_config"] = {
        "enabled": False,
        "asset_file_id": "",
        "file_size": 0,
        "position": "",
    }
    current["watermark_config"] = {"enabled": False, "text": "", "position": "", "opacity_percent": 45}
    current["logo_status"] = "skipped"
    current["watermark_status"] = "skipped"
    current["brand_pending_target"] = ""
    current["brand_pending_position"] = ""
    current["summary_status"] = "not_ready"
    current["review_status"] = "not_ready"
    current["status_stage"] = "logo_watermark"
    return normalize_state(current)


def mark_branding_configured(state: dict[str, Any], target: str) -> dict[str, Any]:
    current = normalize_state(state)
    if target == "logo":
        current["logo_status"] = "configured"
    elif target == "watermark":
        current["watermark_status"] = "configured"
    current["summary_status"] = "not_ready"
    current["review_status"] = "not_ready"
    return normalize_state(current)


def mark_branding_complete(state: dict[str, Any]) -> dict[str, Any]:
    """Finish the optional branding hub without discarding saved assets."""

    current = normalize_state(state)
    logo = dict(current.get("logo_config") or {})
    watermark = dict(current.get("watermark_config") or {})
    logo_ready = bool(
        logo.get("enabled")
        and logo.get("asset_file_id")
        and logo.get("position")
    )
    watermark_ready = bool(
        watermark.get("enabled")
        and watermark.get("text")
        and watermark.get("position")
    )
    current["logo_status"] = "configured" if logo_ready else "skipped"
    current["watermark_status"] = "configured" if watermark_ready else "skipped"
    current["brand_pending_target"] = ""
    current["brand_pending_position"] = ""
    current["summary_status"] = "not_ready"
    current["review_status"] = "not_ready"
    current["status_stage"] = "logo_watermark"
    return normalize_state(current)


def next_required_screen(state: dict[str, Any]) -> str:
    """Return the first missing screen in the canonical shared video tail."""

    current = normalize_state(state)
    product_type = str(current.get("video_product_type") or "")
    if product_type in {"multi_scene_film", "video_long"}:
        return ""
    if not addon_complete(current):
        return "addon"
    if not content_contract_ready(current) or current.get("review_status") != "ready":
        return "review"
    return ""


def prepare_summary(state: dict[str, Any]) -> dict[str, Any]:
    """Compatibility entry for old Summary callbacks; Review remains explicit."""

    return prepare_review(state)


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
    current["summary_status"] = "not_ready"
    current["review_status"] = "not_ready"
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
    current["summary_status"] = "not_ready"
    current["review_status"] = "not_ready"
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
        str(current.get("video_product_type") or ""),
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


def evaluate_submit_preflight(
    state: dict[str, Any],
    *,
    available_xu: Any,
    provider_ready: bool,
    worker_ready: bool,
    is_admin_or_owner: bool = False,
    existing_job_id: Any = "",
    admin_detail: str = "",
) -> dict[str, Any]:
    """Return exactly one submit outcome in the public confirmation order."""

    current = normalize_state(state)
    persisted_job_id = str(existing_job_id or current.get("job_id") or "").strip()
    try:
        invoice_valid, invoice_reason = invoice_allowed(current)
    except (TypeError, ValueError, OverflowError):
        invoice_valid, invoice_reason = False, "invalid_pricing_snapshot"
    pricing = dict(current.get("pricing_snapshot") or {})
    raw_quoted_xu = pricing.get("total_xu") or pricing.get("price_xu") or 0
    try:
        quoted_xu = int(raw_quoted_xu)
    except (TypeError, ValueError, OverflowError):
        quoted_xu = 0
        invoice_valid, invoice_reason = False, "invalid_pricing_snapshot"
    if quoted_xu < 0:
        quoted_xu = 0
        invoice_valid, invoice_reason = False, "invalid_pricing_snapshot"
    required_xu = 0 if is_admin_or_owner else quoted_xu
    try:
        available = max(0, int(available_xu or 0))
    except (TypeError, ValueError):
        available = 0
    missing_xu = max(0, required_xu - available)

    result = {
        "allowed": False,
        "blocker_code": "",
        "public_message": "",
        "admin_detail": str(admin_detail or ""),
        "required_xu": required_xu,
        "quoted_xu": quoted_xu,
        "available_xu": available,
        "missing_xu": missing_xu,
        "provider_ready": bool(provider_ready),
        "worker_ready": bool(worker_ready),
        "invoice_valid": bool(invoice_valid),
        "invoice_reason": str(invoice_reason or ""),
        "existing_job_id": persisted_job_id,
        "is_admin_or_owner": bool(is_admin_or_owner),
    }

    if persisted_job_id:
        result["allowed"] = True
        return result
    if not invoice_valid:
        result.update({
            "blocker_code": "invoice_invalid",
            "public_message": (
                "⚠️ <b>Hóa đơn chưa sẵn sàng để xác nhận.</b>\n\n"
                "Toàn bộ cấu hình vẫn được giữ nguyên. Anh/chị vui lòng quay lại hóa đơn để kiểm tra. "
                "Hệ thống chưa tạo tác vụ và chưa trừ Xu."
            ),
        })
        return result
    if missing_xu:
        result.update({
            "blocker_code": "insufficient_balance",
            "public_message": (
                "💰 <b>Chưa đủ Xu để bắt đầu tạo video</b>\n\n"
                f"• Tổng thanh toán: <b>{required_xu} Xu</b>\n"
                f"• Số dư hiện tại: <b>{available} Xu</b>\n"
                f"• Còn thiếu: <b>{missing_xu} Xu</b>\n\n"
                "Hóa đơn và toàn bộ cấu hình vẫn được giữ nguyên. Hệ thống chưa tạo tác vụ, "
                "chưa bắt đầu xử lý video và chưa trừ Xu."
            ),
        })
        return result
    if not provider_ready:
        result.update({
            "blocker_code": "provider_unavailable",
            "public_message": (
                "⚙️ <b>TOAN AAS chưa thể bắt đầu xử lý video lúc này.</b>\n\n"
                "Hóa đơn và toàn bộ cấu hình vẫn được giữ nguyên. Hệ thống chưa tạo tác vụ và "
                "chưa trừ Xu. Anh/chị vui lòng kiểm tra lại sau."
            ),
        })
        return result
    if not worker_ready:
        result.update({
            "blocker_code": "worker_unavailable",
            "public_message": (
                "⚙️ <b>TOAN AAS chưa thể bắt đầu xử lý video lúc này.</b>\n\n"
                "Hóa đơn và toàn bộ cấu hình vẫn được giữ nguyên. Hệ thống chưa tạo tác vụ và "
                "chưa trừ Xu. Anh/chị vui lòng kiểm tra lại sau."
            ),
        })
        return result

    result["allowed"] = True
    return result


def confirm_once(state: dict[str, Any], confirm_token: str) -> tuple[dict[str, Any], bool]:
    current = normalize_state(state)
    allowed, reason = invoice_allowed(current)
    if not allowed:
        raise ValueError(reason)
    contract = commercial_contract(str(current.get("video_product_type") or ""))
    if not contract.get("execution_enabled"):
        raise ValueError(str(contract.get("execution_blocker") or "execution_disabled"))
    token = str(confirm_token or "").strip()
    if current.get("final_confirmed"):
        return current, False
    current["final_confirmed"] = True
    current["confirm_token"] = token
    current["status_stage"] = "confirmed"
    return current, True


def mark_submitted(
    state: dict[str, Any],
    *,
    user_id: Any,
    job_id: Any,
    public_processing_code: str = "",
    submitted_at: str = "",
    execution_state: str = "queued",
) -> tuple[dict[str, Any], bool]:
    """Persist one accepted submit without allowing a second job identity."""

    current = normalize_state(state)
    accepted_job_id = str(job_id or "").strip()
    if not accepted_job_id:
        raise ValueError("submitted_job_missing")
    existing_job_id = str(current.get("job_id") or "").strip()
    if existing_job_id and existing_job_id != accepted_job_id:
        raise ValueError("submitted_job_conflict")
    created = not bool(existing_job_id and current.get("final_confirmed"))
    current["job_id"] = accepted_job_id
    current["submit_user_id"] = str(user_id or "").strip()
    current["public_processing_code"] = str(
        current.get("public_processing_code")
        or public_processing_code
        or f"#{accepted_job_id}"
    ).strip()
    current["submitted_at"] = str(current.get("submitted_at") or submitted_at or "").strip()
    current["execution_state"] = str(current.get("execution_state") or execution_state or "queued").strip()
    current["final_confirmed"] = True
    current["status_stage"] = "confirmed"
    return normalize_state(current), created


def recover_submission(state: dict[str, Any], persisted: dict[str, Any] | None) -> dict[str, Any]:
    """Recover the canonical invoice/job identity after volatile UI state loss."""

    current = normalize_state(state)
    record = deepcopy(dict(persisted or {}))
    job = dict(record.get("job") or record.get("b14_queue_job") or {})
    invoice = dict(record.get("invoice") or record.get("b14_invoice") or {})
    job_id = str(
        record.get("job_id")
        or record.get("b14_queue_job_id")
        or job.get("id")
        or ""
    ).strip()
    if not job_id:
        return current

    quality_tier_id = str(
        record.get("quality_tier_id")
        or invoice.get("quality_tier_id")
        or invoice.get("quality_xu")
        or current.get("quality_tier_id")
        or ""
    ).strip()
    package_id = str(
        record.get("package_id")
        or invoice.get("package_id")
        or current.get("package_id")
        or (f"product_video_{quality_tier_id}" if quality_tier_id else "")
    ).strip()
    invoice_id = str(
        record.get("invoice_id")
        or invoice.get("invoice_id")
        or current.get("invoice_id")
        or ""
    ).strip()
    if quality_tier_id:
        current["quality_tier_id"] = quality_tier_id
    if package_id:
        current["package_id"] = package_id
    if invoice_id:
        current["invoice_id"] = invoice_id
    if record.get("scene_count") or invoice.get("scene_count"):
        current["scene_count"] = max(
            1,
            int(record.get("scene_count") or invoice.get("scene_count") or current.get("scene_count") or 1),
        )

    pricing = dict(current.get("pricing_snapshot") or {})
    pricing.update(invoice)
    total_xu = record.get("total_xu")
    if total_xu is not None:
        pricing["total_xu"] = int(total_xu or 0)
    if quality_tier_id:
        pricing.setdefault("quality_xu", int(quality_tier_id or 0))
    current["pricing_snapshot"] = pricing

    recovered, _created = mark_submitted(
        current,
        user_id=record.get("user_id") or job.get("user_id") or current.get("submit_user_id"),
        job_id=job_id,
        public_processing_code=str(record.get("public_processing_code") or record.get("public_code") or ""),
        submitted_at=str(record.get("submitted_at") or job.get("created_at") or ""),
        execution_state=str(record.get("execution_state") or record.get("status") or job.get("status") or "queued"),
    )
    return recovered


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
        "content_ready": 0,
        "logo_watermark": 3,
        "summary": 5,
        "review": 7,
        "audio_addons": 9,
        "quality": 10,
        "invoice": 12,
        "confirmed": 20,
        "rendering": 55,
        "validating": 80,
        "delivering": 90,
        "delivered": 100,
        "failed": 0,
    }[stage]
