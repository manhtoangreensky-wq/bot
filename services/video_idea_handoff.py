"""Canonical parent-flow handoff for the public Video idea catalog."""

from __future__ import annotations

from copy import deepcopy
from uuid import uuid4


SUPPORTED_PRODUCTS = frozenset({
    "video_idea",
    "video_trend",
    "video_ai_real",
    "script_image_video",
    "video_reference",
    "motion_prompt",
    "storyboard_prompt",
    "self_shot_scene_change",
    "self_shot_cinematic_transform",
    "multi_scene_film",
})

NEXT_STEPS = {
    "video_idea": "video_prompts",
    "video_trend": "scene_plan",
    "video_ai_real": "scene_plan",
    "script_image_video": "scene_plan",
    "video_reference": "scene_plan",
    "motion_prompt": "scene_plan",
    "storyboard_prompt": "storyboard_scene_review",
    "self_shot_scene_change": "selfshot2_scene_plan",
    "self_shot_cinematic_transform": "selfshot3_timeline",
    "multi_scene_film": "long_chapter_plan",
}


PARENT_STATE_KEYS = frozenset({
    "storyboard2",
    "source_video",
    "source_analysis",
    "source_segment",
    "subject_manifest",
    "preserve_constraints",
    "relationship_locks",
    "layer_rules",
    "direction_contract",
    "selected_direction",
    "selected_group_id",
    "selected_preset",
    "transformation_stage_count",
    "transformation_type",
    "transformation_content",
    "transformation_stages",
    "wardrobe",
    "world",
    "selected_effects",
    "audio_plan",
})


def _bounded_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def build_parent_handoff(
    state: dict,
    *,
    product_id: str,
    return_callback: str,
) -> dict:
    """Capture every value required to return to the exact parent flow."""

    source = deepcopy(dict(state or {}))
    product = str(product_id or "video_idea").strip()
    if product not in SUPPORTED_PRODUCTS:
        product = "video_idea"
    assets = deepcopy(dict(source.get("reference_assets") or source.get("assets") or {}))
    source_items = [
        deepcopy(item)
        for item in assets.get("items") or []
        if isinstance(item, dict)
    ][:20]
    return {
        "owner": "video_idea_parent_handoff",
        "session_id": str(source.get("flow_session_id") or source.get("session_id") or uuid4()),
        "revision": _bounded_int(source.get("flow_revision") or source.get("revision"), 1, 1, 1_000_000),
        "source_flow": str(source.get("flow_kind") or source.get("flow") or product),
        "idea_source_flow": str(
            source.get("idea_source_flow")
            or source.get("flow_kind")
            or source.get("flow")
            or product
        ),
        "origin_product": product,
        "return_step": NEXT_STEPS[product],
        "idea_return_step": str(source.get("idea_return_step") or NEXT_STEPS[product]),
        "return_callback": str(return_callback or "videoidea|start").strip(),
        "idea_preset_id": _bounded_int(source.get("idea_preset_id"), 0, 0, 2_147_483_647),
        "idea_content": str(source.get("idea_content") or source.get("subject") or ""),
        "idea_prompt": str(
            source.get("idea_prompt")
            or source.get("customer_brief")
            or source.get("manual_script_raw")
            or ""
        ),
        "scene_count": _bounded_int(source.get("scene_count"), 1, 1, 20),
        "aspect_ratio": str(source.get("aspect_ratio") or "9:16"),
        "trend_source": deepcopy(dict(source.get("trend_source") or {})),
        "storyboard_session_id": str(source.get("storyboard_session_id") or ""),
        "source_video_id": str(
            assets.get("source_media_ref")
            or source.get("source_video_id")
            or source.get("source_media_ref")
            or ""
        ),
        "source_media_refs": [
            str(item).strip()
            for item in assets.get("source_media_refs") or source.get("source_media_refs") or []
            if str(item or "").strip()
        ][:20],
        "source_asset_items": source_items,
        "parent_state": {
            key: deepcopy(source[key])
            for key in PARENT_STATE_KEYS
            if key in source
        },
    }


def normalize_parent_handoff(value: dict | None) -> dict:
    source = deepcopy(dict(value or {}))
    product = str(source.get("origin_product") or "").strip()
    if source.get("owner") != "video_idea_parent_handoff" or product not in SUPPORTED_PRODUCTS:
        return {}
    source["origin_product"] = product
    source["return_step"] = NEXT_STEPS[product]
    source["idea_source_flow"] = str(source.get("idea_source_flow") or source.get("source_flow") or product)
    source["idea_return_step"] = str(source.get("idea_return_step") or NEXT_STEPS[product])
    source["idea_preset_id"] = _bounded_int(source.get("idea_preset_id"), 0, 0, 2_147_483_647)
    source["idea_content"] = str(source.get("idea_content") or "")
    source["idea_prompt"] = str(source.get("idea_prompt") or "")
    source["scene_count"] = _bounded_int(source.get("scene_count"), 1, 1, 20)
    source["aspect_ratio"] = str(source.get("aspect_ratio") or "9:16")
    source["revision"] = _bounded_int(source.get("revision"), 1, 1, 1_000_000)
    source["trend_source"] = deepcopy(dict(source.get("trend_source") or {}))
    source["source_media_refs"] = [
        str(item).strip()
        for item in source.get("source_media_refs") or []
        if str(item or "").strip()
    ][:20]
    source["source_asset_items"] = [
        deepcopy(item)
        for item in source.get("source_asset_items") or []
        if isinstance(item, dict)
    ][:20]
    source["parent_state"] = {
        key: deepcopy(value)
        for key, value in dict(source.get("parent_state") or {}).items()
        if key in PARENT_STATE_KEYS
    }
    return source


def apply_parent_handoff(scene_state: dict, handoff: dict) -> dict:
    """Restore the parent contract after a preset has been approved."""

    restored = normalize_parent_handoff(handoff)
    if not restored:
        raise ValueError("invalid_video_idea_parent_handoff")
    updated = deepcopy(dict(scene_state or {}))
    product = restored["origin_product"]
    updated.update({
        "source_product_id": product,
        "idea_origin_product": product,
        "scene_count": restored["scene_count"],
        "aspect_ratio": restored["aspect_ratio"],
        "recommended_aspect_ratio": restored["aspect_ratio"],
        "trend_source": deepcopy(restored["trend_source"]),
        "storyboard_session_id": restored.get("storyboard_session_id", ""),
        "idea_parent_owner": restored["owner"],
        "idea_parent_session_id": restored["session_id"],
        "idea_parent_revision": restored["revision"],
        "idea_parent_return_callback": restored["return_callback"],
        "idea_parent_state": deepcopy(restored.get("parent_state") or {}),
        "idea_source_flow": str(updated.get("idea_source_flow") or restored["idea_source_flow"]),
        "idea_return_step": str(updated.get("idea_return_step") or restored["idea_return_step"]),
        "idea_preset_id": _bounded_int(
            updated.get("idea_preset_id") or restored.get("idea_preset_id"),
            0,
            0,
            2_147_483_647,
        ),
        "idea_content": str(updated.get("idea_content") or restored.get("idea_content") or ""),
        "idea_prompt": str(updated.get("idea_prompt") or restored.get("idea_prompt") or ""),
        "step": restored["return_step"],
    })
    assets = deepcopy(dict(updated.get("reference_assets") or updated.get("assets") or {}))
    if restored["source_asset_items"]:
        assets["items"] = deepcopy(restored["source_asset_items"])
    if restored["source_media_refs"]:
        assets["source_media_refs"] = list(restored["source_media_refs"])
    if restored.get("source_video_id"):
        assets["source_media_ref"] = restored["source_video_id"]
    if assets:
        updated["assets"] = deepcopy(assets)
        updated["reference_assets"] = deepcopy(assets)
    return updated
