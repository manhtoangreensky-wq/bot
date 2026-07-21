"""Professional prompt package builder for semantic video scenes."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from services.video_prompt_pattern_library import select_approved_pattern
from services.video_semantic_scene_planner import semantic_quality_gate


def _join(values: Any) -> str:
    if isinstance(values, (list, tuple, set)):
        return "; ".join(str(item) for item in values if str(item or "").strip())
    return str(values or "").strip()


def build_scene_provider_prompt(
    scene: dict[str, Any],
    *,
    continuity_contract: dict[str, Any],
    aspect_ratio: str,
) -> str:
    return " | ".join([
        f"Scene {int(scene.get('scene_index') or 1)} objective: {scene.get('main_idea')}",
        f"Subject: {scene.get('subject')}",
        f"Environment: {scene.get('environment')}",
        f"Start state: {scene.get('start_state')}",
        f"Complete action: {scene.get('primary_action')}",
        f"Development: {scene.get('development')}",
        f"Completed end state: {scene.get('completion_state')}",
        f"Camera: {scene.get('camera')}",
        f"Creative palette and lighting: {scene.get('creative_palette_lighting') or scene.get('lighting')}",
        f"Identity color locks: {scene.get('identity_color_locks') or 'none supplied'}",
        f"Color conflict policy: {scene.get('color_conflict_policy') or 'identity locks override creative palette'}",
        f"Visual style: {scene.get('visual_style')}",
        f"Dialogue/voiceover: {scene.get('dialogue_or_voiceover') or 'none'}",
        f"Continuity: {_join(continuity_contract.get('must_remain_constant'))}",
        f"Motion direction: {continuity_contract.get('motion_direction')}",
        f"Transition out: {scene.get('transition_out')} after the action and camera movement finish",
        f"Duration: {int(scene.get('duration_seconds') or 8)} seconds",
        f"Aspect ratio: {aspect_ratio}",
        f"Preserve: {_join(scene.get('preserve_constraints'))}",
        "One semantic beat only; complete every spoken sentence, action and camera move before the cut",
    ])


def build_prompt_package(plan: dict[str, Any]) -> dict[str, Any]:
    quality = semantic_quality_gate(plan)
    if not quality.get("ok"):
        raise ValueError("semantic_quality_gate_failed:" + ",".join(quality.get("errors") or []))
    updated = deepcopy(plan)
    addon_plan = dict(updated.get("addon_plan") or {})
    content = dict(addon_plan.get("content_affecting") or {})
    aspect = str(content.get("aspect_ratio") or "9:16")
    continuity = dict(updated.get("continuity_contract") or {})
    pattern = select_approved_pattern(str(updated.get("profile_id") or "general"), int(updated.get("scene_count") or 1))
    negative_common = (
        "no identity drift, no wardrobe or product change, no invented logo or text, "
        "no geometry drift, no duplicated action, no unfinished sentence, no mid-action cut, "
        "no unfinished camera movement, no filler beat"
    )
    prompt_rows = []
    for scene in updated.get("scenes") or []:
        scene["provider_prompt"] = build_scene_provider_prompt(
            scene,
            continuity_contract=continuity,
            aspect_ratio=aspect,
        )
        scene["negative_prompt"] = negative_common
        prompt_rows.append({
            "scene_index": int(scene.get("scene_index") or 0),
            "provider_prompt": scene["provider_prompt"],
            "negative_prompt": scene["negative_prompt"],
            "transition_instruction": next((
                str(item.get("instruction") or "")
                for item in updated.get("transitions") or []
                if int(item.get("from_scene") or 0) == int(scene.get("scene_index") or 0)
            ), "Final scene resolves completely; no outgoing cut."),
        })
    global_prompt = (
        f"Create a coherent {int(updated.get('scene_count') or 1)}-scene video about {updated.get('subject')}. "
        f"Use the {updated.get('profile_id')} profile and {updated.get('context') or 'the selected context'}. "
        "Each scene is one complete semantic beat and inherits the previous scene's completed state."
    )
    continuity_prompt = (
        f"Continuity contract: identity={_join(continuity.get('identity'))}; "
        f"products={_join(continuity.get('products'))}; logos={_join(continuity.get('logos'))}; "
        f"environment={_join(continuity.get('environment'))}; geometry={_join(continuity.get('architecture_geometry'))}; "
        f"creative_palette_lighting={_join(continuity.get('creative_palette_lighting'))}; "
        f"identity_color_locks={_join(continuity.get('identity_color_locks'))}; "
        f"color_policy={continuity.get('color_conflict_policy')}; "
        f"resolved_palette={_join(continuity.get('color_palette'))}; lighting={continuity.get('lighting_state')}; "
        f"time={continuity.get('time_of_day')}; direction={continuity.get('motion_direction')}; "
        f"camera={continuity.get('camera_language')}."
    )
    transitions = []
    for item in updated.get("transitions") or []:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row["transition_id"] = str(
            row.get("transition_id")
            or f"scene_{int(row.get('from_scene') or 0)}_to_{int(row.get('to_scene') or 0)}"
        )
        transitions.append(row)
    updated["transitions"] = transitions
    post = dict(addon_plan.get("post_production") or {})
    return {
        **updated,
        "global_project_prompt": global_prompt,
        "continuity_prompt": continuity_prompt,
        "scene_prompts": prompt_rows,
        "concat_post_production_plan": {
            "order": [int(item.get("scene_index") or 0) for item in updated.get("scenes") or []],
            "validate_every_scene_before_concat": True,
            "concat_only_when_all_scenes_valid": True,
            "execute_after_concat": [key for key, enabled in post.items() if enabled],
            "final_mp4_validation_required": True,
            "delivery_before_charge_required": True,
        },
        "approved_pattern_id": str(pattern.get("pattern_id") or "deterministic_fallback"),
        "approved_pattern_version": str(pattern.get("version") or "1.0.0"),
        "pattern_admin_approved": bool(pattern.get("admin_approved")),
        "provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "xu_charged": 0,
    }


def regenerate_scene_prompt(package: dict[str, Any], scene_index: int) -> dict[str, Any]:
    updated = deepcopy(package)
    index = max(1, min(len(updated.get("scenes") or []), int(scene_index or 1)))
    scene = updated["scenes"][index - 1]
    scene["provider_prompt"] = build_scene_provider_prompt(
        scene,
        continuity_contract=dict(updated.get("continuity_contract") or {}),
        aspect_ratio=str(((updated.get("addon_plan") or {}).get("content_affecting") or {}).get("aspect_ratio") or "9:16"),
    )
    for item in updated.get("scene_prompts") or []:
        if int(item.get("scene_index") or 0) == index:
            item["provider_prompt"] = scene["provider_prompt"]
    return updated
