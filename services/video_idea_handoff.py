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
    "storyboard_prompt": "storyboard_entity_middle",
    "self_shot_scene_change": "selfshot2_scene_plan",
    "self_shot_cinematic_transform": "selfshot3_timeline",
    "multi_scene_film": "long_chapter_plan",
}


CONTINUATION_REGISTRY = {
    "video_ai_real": {
        "public_product_type": "video_ai_realistic",
        "continuation": "full_review",
        "flow_owner": "scene3",
        "engine_route": "video_ai_canonical",
    },
    "video_trend": {
        "public_product_type": "trend_video",
        "continuation": "full_review",
        "flow_owner": "trend",
        "engine_route": "trend_video",
    },
    "script_image_video": {
        "public_product_type": "script_to_video",
        "continuation": "full_review",
        "flow_owner": "scene3",
        "engine_route": "script_to_video",
    },
    "storyboard_prompt": {
        "public_product_type": "storyboard_to_video",
        "continuation": "entity_middle",
        "flow_owner": "storyboard",
        "engine_route": "storyboard_to_video",
    },
    "self_shot_scene_change": {
        "public_product_type": "self_shot_scene_change",
        "continuation": "scene_plan",
        "flow_owner": "selfshot2",
        "engine_route": "self_shot_scene_change",
    },
    "self_shot_cinematic_transform": {
        "public_product_type": "self_shot_cinematic_transform",
        "continuation": "timeline",
        "flow_owner": "selfshot3",
        "engine_route": "self_shot_cinematic_transform",
    },
    "multi_scene_film": {
        "public_product_type": "long_video",
        "continuation": "full_review",
        "flow_owner": "scene3",
        "engine_route": "multi_scene_film",
    },
    # Compatibility-only products still use the same Scene3 continuation.
    "video_reference": {
        "public_product_type": "video_reference",
        "continuation": "full_review",
        "flow_owner": "scene3",
        "engine_route": "video_ai_canonical",
    },
    "motion_prompt": {
        "public_product_type": "motion_prompt",
        "continuation": "full_review",
        "flow_owner": "scene3",
        "engine_route": "video_ai_canonical",
    },
    "video_idea": {
        "public_product_type": "video_idea",
        "continuation": "video_idea_standalone",
        "flow_owner": "video_idea",
        "engine_route": "video_idea_to_product",
    },
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
    "trend_id",
    "idea_preset_content",
    "idea_scene_content",
    "idea_prompt_candidates",
    "idea_selected_prompt",
    "selected_profile",
    "primary_profile",
    "primary_profile_key",
    "script_session_id",
    "long_script_revision",
    "manual_script_raw",
    "script_text",
    "long_script_mode",
    "selfshot_mode",
    "long_video_mode",
    "identity_lock",
    "relationship_lock",
    "motion_analysis",
    "environment",
    "effects",
    "timeline",
    "compiled_prompt",
    "scene_plan",
    "video_prompts",
})


def _bounded_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def continuation_contract(product_id: str) -> dict:
    product = str(product_id or "").strip()
    contract = CONTINUATION_REGISTRY.get(product)
    if not contract:
        raise ValueError("unsupported_video_idea_parent_product")
    return {"product_id": product, **deepcopy(contract)}


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
        raise ValueError("unsupported_video_idea_parent_product")
    continuation = continuation_contract(product)
    assets = deepcopy(dict(source.get("reference_assets") or source.get("assets") or {}))
    source_items = [
        deepcopy(item)
        for item in assets.get("items") or []
        if isinstance(item, dict)
    ][:20]
    session_id = str(source.get("flow_session_id") or source.get("session_id") or uuid4())
    revision = _bounded_int(source.get("flow_revision") or source.get("revision"), 1, 1, 1_000_000)
    source_flow = str(source.get("flow_kind") or source.get("flow") or product)
    return_step = str(source.get("idea_return_step") or NEXT_STEPS[product])
    ratio = str(source.get("ratio") or source.get("aspect_ratio") or "9:16")
    trend_source = deepcopy(dict(source.get("trend_source") or {}))
    return {
        "owner": "video_idea_parent_handoff",
        "session_id": session_id,
        "revision": revision,
        "source_flow": source_flow,
        "idea_source_flow": str(
            source.get("idea_source_flow")
            or source.get("flow_kind")
            or source.get("flow")
            or product
        ),
        "origin_product": product,
        "idea_parent_product": product,
        "idea_parent_flow": source_flow,
        "idea_parent_session_id": session_id,
        "idea_parent_revision": revision,
        "idea_parent_return_step": return_step,
        "idea_parent_continuation": continuation["continuation"],
        "idea_parent_flow_owner": continuation["flow_owner"],
        "idea_parent_engine_route": continuation["engine_route"],
        "idea_parent_public_product_type": continuation["public_product_type"],
        "return_step": NEXT_STEPS[product],
        "idea_return_step": return_step,
        "return_callback": str(return_callback or "videoidea|start").strip(),
        "content_source": "idea_catalog",
        "selected_profile": str(
            source.get("selected_profile")
            or source.get("primary_profile")
            or source.get("primary_profile_key")
            or ""
        ),
        "idea_preset_id": _bounded_int(source.get("idea_preset_id"), 0, 0, 2_147_483_647),
        "idea_id": str(
            source.get("idea_id")
            or (source.get("idea_preset_content") or {}).get("preset_key")
            or source.get("idea_preset_id")
            or ""
        ),
        "idea_title": str(
            source.get("idea_title")
            or (source.get("idea_preset_content") or {}).get("title")
            or source.get("subject")
            or ""
        ),
        "idea_preset_content": deepcopy(dict(source.get("idea_preset_content") or {})),
        "idea_content": str(source.get("idea_content") or source.get("subject") or ""),
        "idea_prompt": str(
            source.get("idea_prompt")
            or source.get("customer_brief")
            or source.get("manual_script_raw")
            or ""
        ),
        "idea_scene_content": deepcopy(list(source.get("idea_scene_content") or [])),
        "idea_scene_contents": deepcopy(list(
            source.get("idea_scene_contents")
            or source.get("idea_scene_content")
            or []
        )),
        "idea_prompt_candidates": deepcopy(list(source.get("idea_prompt_candidates") or [])),
        "idea_selected_prompt": str(source.get("idea_selected_prompt") or ""),
        "selected_prompt_id": str(source.get("selected_prompt_id") or ""),
        "selected_prompt_text": str(
            source.get("selected_prompt_text")
            or source.get("idea_selected_prompt")
            or ""
        ),
        "selected_prompt_revision": _bounded_int(
            source.get("selected_prompt_revision"), 0, 0, 1_000_000
        ),
        "prompt_style": str(source.get("prompt_style") or ""),
        "scene_count": _bounded_int(source.get("scene_count"), 1, 1, 20),
        "aspect_ratio": ratio,
        "ratio": ratio,
        "trend_source": trend_source,
        "trend_id": str(source.get("trend_id") or trend_source.get("trend_id") or trend_source.get("id") or ""),
        "trend_title": str(source.get("trend_title") or trend_source.get("title") or ""),
        "trend_context": str(source.get("trend_context") or trend_source.get("summary") or ""),
        "script_session_id": str(source.get("script_session_id") or ""),
        "long_script_revision": _bounded_int(source.get("long_script_revision"), 1, 1, 1_000_000),
        "storyboard_session_id": str(source.get("storyboard_session_id") or ""),
        "selfshot_mode": str(source.get("selfshot_mode") or ""),
        "long_video_mode": str(source.get("long_video_mode") or ""),
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
    continuation = continuation_contract(product)
    source["origin_product"] = product
    source["idea_parent_product"] = product
    source["return_step"] = NEXT_STEPS[product]
    source["idea_source_flow"] = str(source.get("idea_source_flow") or source.get("source_flow") or product)
    source["idea_parent_flow"] = str(source.get("idea_parent_flow") or source["idea_source_flow"])
    source["idea_return_step"] = str(source.get("idea_return_step") or NEXT_STEPS[product])
    source["idea_parent_return_step"] = source["idea_return_step"]
    source["idea_parent_continuation"] = continuation["continuation"]
    source["idea_parent_flow_owner"] = continuation["flow_owner"]
    source["idea_parent_engine_route"] = continuation["engine_route"]
    source["idea_parent_public_product_type"] = continuation["public_product_type"]
    source["content_source"] = "idea_catalog"
    source["selected_profile"] = str(source.get("selected_profile") or "")
    source["idea_preset_id"] = _bounded_int(source.get("idea_preset_id"), 0, 0, 2_147_483_647)
    source["idea_id"] = str(source.get("idea_id") or source.get("idea_preset_id") or "")
    source["idea_preset_content"] = deepcopy(dict(source.get("idea_preset_content") or {}))
    source["idea_content"] = str(source.get("idea_content") or "")
    source["idea_title"] = str(
        source.get("idea_title")
        or source["idea_preset_content"].get("title")
        or source.get("idea_content")
        or ""
    )
    source["idea_prompt"] = str(source.get("idea_prompt") or "")
    source["scene_count"] = _bounded_int(source.get("scene_count"), 1, 1, 20)
    source["aspect_ratio"] = str(source.get("aspect_ratio") or "9:16")
    source["ratio"] = str(source.get("ratio") or source["aspect_ratio"])
    source["revision"] = _bounded_int(source.get("revision"), 1, 1, 1_000_000)
    source["idea_parent_session_id"] = str(source.get("idea_parent_session_id") or source.get("session_id") or "")
    source["idea_parent_revision"] = _bounded_int(source.get("idea_parent_revision") or source["revision"], 1, 1, 1_000_000)
    source["trend_source"] = deepcopy(dict(source.get("trend_source") or {}))
    source["trend_id"] = str(source.get("trend_id") or source["trend_source"].get("trend_id") or source["trend_source"].get("id") or "")
    source["trend_title"] = str(source.get("trend_title") or source["trend_source"].get("title") or "")
    source["trend_context"] = str(source.get("trend_context") or source["trend_source"].get("summary") or "")
    source["script_session_id"] = str(source.get("script_session_id") or "")
    source["long_script_revision"] = _bounded_int(source.get("long_script_revision"), 1, 1, 1_000_000)
    source["storyboard_session_id"] = str(source.get("storyboard_session_id") or "")
    source["selfshot_mode"] = str(source.get("selfshot_mode") or "")
    source["long_video_mode"] = str(source.get("long_video_mode") or "")
    source["idea_scene_content"] = deepcopy(list(source.get("idea_scene_content") or []))
    source["idea_scene_contents"] = deepcopy(list(
        source.get("idea_scene_contents")
        or source.get("idea_scene_content")
        or []
    ))
    source["idea_prompt_candidates"] = deepcopy(list(source.get("idea_prompt_candidates") or []))
    source["idea_selected_prompt"] = str(source.get("idea_selected_prompt") or "")
    source["selected_prompt_id"] = str(source.get("selected_prompt_id") or "")
    source["selected_prompt_text"] = str(
        source.get("selected_prompt_text")
        or source.get("idea_selected_prompt")
        or ""
    )
    source["selected_prompt_revision"] = _bounded_int(
        source.get("selected_prompt_revision"), 0, 0, 1_000_000
    )
    source["prompt_style"] = str(source.get("prompt_style") or "")
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


def parent_session_matches(state: dict, handoff: dict) -> bool:
    restored = normalize_parent_handoff(handoff)
    if not restored:
        return False
    source = dict(state or {})
    return (
        str(source.get("idea_parent_product") or "") == restored["origin_product"]
        and str(source.get("idea_parent_session_id") or "") == restored["idea_parent_session_id"]
        and _bounded_int(source.get("idea_parent_revision"), 0, 0, 1_000_000)
        == restored["idea_parent_revision"]
        and str(source.get("idea_parent_continuation") or "")
        == restored["idea_parent_continuation"]
    )


def apply_parent_handoff(scene_state: dict, handoff: dict) -> dict:
    """Restore the parent contract after a preset has been approved."""

    restored = normalize_parent_handoff(handoff)
    if not restored:
        raise ValueError("invalid_video_idea_parent_handoff")
    updated = deepcopy(dict(scene_state or {}))
    product = restored["origin_product"]
    updated.update({
        "source_product_id": product,
        "product_type": restored["idea_parent_public_product_type"],
        "flow_owner": restored["idea_parent_flow_owner"],
        "video_flow_owner": restored["idea_parent_flow_owner"],
        "engine_route": restored["idea_parent_engine_route"],
        "idea_origin_product": product,
        "idea_parent_product": product,
        "idea_parent_flow": restored["idea_parent_flow"],
        "scene_count": restored["scene_count"],
        "aspect_ratio": restored["aspect_ratio"],
        "ratio": restored["ratio"],
        "recommended_aspect_ratio": restored["aspect_ratio"],
        "trend_source": deepcopy(restored["trend_source"]),
        "storyboard_session_id": restored.get("storyboard_session_id", ""),
        "idea_parent_owner": restored["owner"],
        "idea_parent_session_id": restored["session_id"],
        "idea_parent_revision": restored["revision"],
        "idea_parent_return_step": restored["idea_parent_return_step"],
        "idea_parent_continuation": restored["idea_parent_continuation"],
        "idea_parent_flow_owner": restored["idea_parent_flow_owner"],
        "idea_parent_engine_route": restored["idea_parent_engine_route"],
        "idea_parent_public_product_type": restored["idea_parent_public_product_type"],
        "idea_parent_return_callback": restored["return_callback"],
        "idea_parent_state": deepcopy(restored.get("parent_state") or {}),
        "idea_source_flow": str(updated.get("idea_source_flow") or restored["idea_source_flow"]),
        "idea_return_step": str(updated.get("idea_return_step") or restored["idea_return_step"]),
        "content_source": "idea_catalog",
        "selected_profile": str(updated.get("selected_profile") or restored.get("selected_profile") or ""),
        "idea_preset_id": _bounded_int(
            updated.get("idea_preset_id") or restored.get("idea_preset_id"),
            0,
            0,
            2_147_483_647,
        ),
        "idea_id": str(updated.get("idea_id") or restored.get("idea_id") or ""),
        "idea_title": str(updated.get("idea_title") or restored.get("idea_title") or ""),
        "idea_preset_content": deepcopy(
            updated.get("idea_preset_content")
            or restored.get("idea_preset_content")
            or {}
        ),
        "idea_content": str(updated.get("idea_content") or restored.get("idea_content") or ""),
        "idea_prompt": str(updated.get("idea_prompt") or restored.get("idea_prompt") or ""),
        "idea_scene_content": deepcopy(updated.get("idea_scene_content") or restored.get("idea_scene_content") or []),
        "idea_scene_contents": deepcopy(
            updated.get("idea_scene_contents")
            or updated.get("idea_scene_content")
            or restored.get("idea_scene_contents")
            or restored.get("idea_scene_content")
            or []
        ),
        "idea_prompt_candidates": deepcopy(updated.get("idea_prompt_candidates") or restored.get("idea_prompt_candidates") or []),
        "idea_selected_prompt": str(updated.get("idea_selected_prompt") or restored.get("idea_selected_prompt") or ""),
        "selected_prompt_id": str(updated.get("selected_prompt_id") or restored.get("selected_prompt_id") or ""),
        "selected_prompt_text": str(
            updated.get("selected_prompt_text")
            or updated.get("idea_selected_prompt")
            or restored.get("selected_prompt_text")
            or restored.get("idea_selected_prompt")
            or ""
        ),
        "selected_prompt_revision": _bounded_int(
            updated.get("selected_prompt_revision") or restored.get("selected_prompt_revision"),
            0,
            0,
            1_000_000,
        ),
        "prompt_style": str(updated.get("prompt_style") or restored.get("prompt_style") or ""),
        "trend_id": str(updated.get("trend_id") or restored.get("trend_id") or ""),
        "trend_title": str(updated.get("trend_title") or restored.get("trend_title") or ""),
        "trend_context": str(updated.get("trend_context") or restored.get("trend_context") or ""),
        "script_session_id": str(updated.get("script_session_id") or restored.get("script_session_id") or ""),
        "long_script_revision": _bounded_int(
            updated.get("long_script_revision") or restored.get("long_script_revision"),
            1,
            1,
            1_000_000,
        ),
        "selfshot_mode": str(updated.get("selfshot_mode") or restored.get("selfshot_mode") or ""),
        "long_video_mode": str(updated.get("long_video_mode") or restored.get("long_video_mode") or ""),
        "source_video_id": str(updated.get("source_video_id") or restored.get("source_video_id") or ""),
        "step": restored["return_step"],
    })
    if product == "multi_scene_film":
        updated["duration_per_scene"] = 600
        updated["scene_duration_seconds"] = 600
    for key, value in dict(restored.get("parent_state") or {}).items():
        if key not in updated or updated.get(key) in (None, "", [], {}):
            updated[key] = deepcopy(value)
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
