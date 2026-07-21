"""Scene-first, provider-free semantic story planner."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from services.video_scene_continuity import (
    build_continuity_contract,
    inherit_previous_completion,
    validate_continuity,
)
from services.video_scene_transition_planner import apply_transitions, plan_transitions, profile_family


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = REPO_ROOT / "knowledge" / "video" / "scene_templates" / "profile_semantic_arcs.json"
SCENE_SECONDS = 8
MIN_SCENES = 1
MAX_SCENES = 20

SCENE_REQUIRED_FIELDS = (
    "scene_index",
    "scene_role",
    "main_idea",
    "subject",
    "environment",
    "start_state",
    "primary_action",
    "development",
    "completion_state",
    "camera",
    "lighting",
    "visual_style",
    "dialogue_or_voiceover",
    "audio_intent",
    "preserve_constraints",
    "transition_in",
    "transition_out",
    "provider_prompt",
    "negative_prompt",
)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _load_templates() -> dict[str, list[dict[str, str]]]:
    try:
        payload = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        payload = {}
    profiles = payload.get("profiles") if isinstance(payload, dict) else {}
    return {
        str(key): [dict(item) for item in value if isinstance(item, dict)]
        for key, value in dict(profiles or {}).items()
    }


def canonical_scene_count(value: Any) -> int:
    return max(MIN_SCENES, min(MAX_SCENES, int(value or 1)))


def _template_positions(template_count: int, scene_count: int) -> list[int]:
    if scene_count <= 1:
        return [0]
    if template_count <= 1:
        return [0] * scene_count
    return [round(index * (template_count - 1) / (scene_count - 1)) for index in range(scene_count)]


def _phase(index: int, total: int) -> str:
    if total == 1:
        return "complete"
    progress = index / max(1, total - 1)
    if progress == 0:
        return "opening"
    if progress < 0.35:
        return "context"
    if progress < 0.72:
        return "development"
    if progress < 1:
        return "payoff"
    return "conclusion"


def _scene_idea(template: dict[str, str], subject: str, context: str, index: int, total: int) -> str:
    idea = _clean(template.get("idea") or f"Phát triển nội dung {subject}")
    phase = _phase(index - 1, total)
    if total > 5 and index not in {1, total}:
        idea = f"{idea}: nhịp {index}/{total} tập trung vào {context or subject} ({phase})"
    return idea


def _dialogue(addons: dict[str, Any], subject: str, role: str, index: int, total: int, max_words: int) -> str:
    if not (addons.get("voiceover") or addons.get("dialogue") or addons.get("captions")):
        return ""
    if index == total and addons.get("cta"):
        text = f"Khép lại {subject} và mời người xem thực hiện bước tiếp theo."
    else:
        text = f"Nhịp {index}: {role.replace('_', ' ')} cho {subject}."
    return " ".join(text.split()[:max_words])


def build_semantic_scene_plan(
    *,
    subject: str,
    scene_count: int,
    profile_id: str,
    context: str = "",
    requirements: dict[str, Any] | None = None,
    assets: dict[str, Any] | None = None,
    addon_plan: dict[str, Any] | None = None,
    semantic_beats: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create exactly N complete scene beats; never creates a provider job."""

    count = canonical_scene_count(scene_count)
    subject_clean = _clean(subject) or "chủ thể video"
    context_clean = _clean(context)
    requirements = dict(requirements or {})
    assets = dict(assets or {})
    addon_plan = dict(addon_plan or {})
    semantic_beats = [dict(item) for item in semantic_beats or [] if isinstance(item, dict)]
    content_addons = dict(addon_plan.get("content_affecting") or {})
    constraints = dict(addon_plan.get("composition_constraints") or {})
    family = profile_family(profile_id)
    templates = _load_templates()
    family_templates = templates.get(family) or templates.get("product") or []
    if not family_templates:
        raise ValueError("semantic_scene_templates_missing")
    positions = _template_positions(len(family_templates), count)
    continuity = build_continuity_contract(
        subject=subject_clean,
        profile_id=profile_id,
        requirements=requirements,
        assets=assets,
        content_addons=content_addons,
    )
    max_words = int(constraints.get("voiceover_max_words_per_scene") or 17)
    scenes: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for index, position in enumerate(positions, start=1):
        template = family_templates[position]
        beat = semantic_beats[index - 1] if index <= len(semantic_beats) else {}
        role_base = _clean(beat.get("role") or template.get("role") or "development")
        role = role_base if count <= len(family_templates) else f"{role_base}_{index:02d}"
        main_idea = _clean(beat.get("main_idea")) or _scene_idea(template, subject_clean, context_clean, index, count)
        if count == 1:
            final_template = family_templates[-1]
            role = "complete_story"
            main_idea = _clean(beat.get("main_idea")) or f"Trình bày trọn vẹn {subject_clean}: thiết lập rõ, hoàn tất hành động chính và khép lại bằng kết quả"
        start_state = (
            _clean(previous.get("completion_state"))
            if previous
            else f"{subject_clean} ở trạng thái mở đầu rõ ràng trong {context_clean or 'bối cảnh đã chọn'}"
        )
        action = _clean(beat.get("action") or template.get("action") or f"Hoàn tất một hành động rõ ràng cho {main_idea}")
        completion = _clean(beat.get("completion") or template.get("completion") or f"Ý cảnh {index} đã hoàn tất")
        if count == 1:
            action = f"Thiết lập {subject_clean}, thực hiện trọn hành động chính và đi tới kết quả trong cùng một nhịp hoàn chỉnh"
            completion = _clean(final_template.get("completion") or f"Câu chuyện về {subject_clean} đã kết thúc trọn vẹn")
        if count > 5 and index not in {1, count}:
            completion = f"{completion}; nhịp {index}/{count} kết thúc ở trạng thái ổn định"
        preserve = list(dict.fromkeys(
            [str(item) for item in continuity.get("must_remain_constant") or []]
            + [str(item) for item in requirements.get("preserve_constraints") or []]
        ))
        scene = {
            "scene_index": index,
            "scene_role": role,
            "main_idea": main_idea,
            "subject": subject_clean,
            "environment": context_clean or (_clean("; ".join(continuity.get("environment") or [])) or "bối cảnh phù hợp profile"),
            "start_state": start_state,
            "primary_action": action,
            "development": _clean(beat.get("development")) or f"Phát triển duy nhất ý cảnh {index}, để hành động diễn ra đủ đầu, giữa và cuối trong {SCENE_SECONDS} giây.",
            "completion_state": completion,
            "camera": str(requirements.get("camera") or continuity.get("camera_language") or "camera có động cơ và dừng tự nhiên"),
            "lighting": str(requirements.get("lighting") or continuity.get("lighting_state") or "ánh sáng nhất quán"),
            "creative_palette_lighting": str(
                requirements.get("creative_palette_lighting")
                or "; ".join(continuity.get("creative_palette_lighting") or [])
                or requirements.get("lighting")
                or continuity.get("lighting_state")
                or "ánh sáng nhất quán"
            ),
            "identity_color_locks": str(
                requirements.get("identity_color_locks")
                or "; ".join(continuity.get("identity_color_locks") or [])
            ),
            "color_conflict_policy": str(
                requirements.get("color_conflict_policy")
                or continuity.get("color_conflict_policy")
                or "identity_color_locks_override_creative_palette"
            ),
            "visual_style": str(requirements.get("visual_style") or f"phong cách {family} nhất quán"),
            "dialogue_or_voiceover": _dialogue(content_addons, subject_clean, role_base, index, count, max_words),
            "audio_intent": str(content_addons.get("music_mood") or continuity.get("audio_style") or "theo mạch nội dung"),
            "preserve_constraints": preserve,
            "transition_in": "",
            "transition_out": "",
            "provider_prompt": (
                f"Cảnh {index}: {main_idea}. Bắt đầu: {start_state}. Hành động hoàn chỉnh: {action}. "
                f"Kết thúc: {completion}. Không cắt giữa hành động, lời nói hoặc chuyển động camera."
            ),
            "negative_prompt": "no filler, no duplicate beat, no unfinished action, no identity drift, no mid-camera cut",
            "duration_seconds": SCENE_SECONDS,
            "motion_direction": str(continuity.get("motion_direction") or "trái sang phải"),
            "semantic_complete": True,
            "action_completed": True,
            "dialogue_completed": True,
            "camera_motion_completed": True,
        }
        scene = inherit_previous_completion(scene, previous)
        scenes.append(scene)
        previous = scene
    transitions = plan_transitions(
        scenes,
        profile_id=profile_id,
        preferred_style=str(content_addons.get("transition_style") or ""),
    )
    apply_transitions(scenes, transitions)
    continuity_result = validate_continuity(scenes, continuity)
    result = {
        "subject": subject_clean,
        "scene_count": count,
        "seconds_per_scene": SCENE_SECONDS,
        "duration_seconds": count * SCENE_SECONDS,
        "planner_max_scenes": MAX_SCENES,
        "planner_theoretical_max_seconds": MAX_SCENES * SCENE_SECONDS,
        "live_capability_requires_validation": True,
        "profile_id": str(profile_id or "general"),
        "profile_family": family,
        "context": context_clean,
        "requirements": requirements,
        "assets": assets,
        "addon_plan": addon_plan,
        "continuity_contract": continuity,
        "continuity_validation": continuity_result,
        "transitions": transitions,
        "semantic_beats_source": "curated_idea_catalog" if semantic_beats else "profile_template",
        "scenes": scenes,
        "provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "xu_charged": 0,
    }
    result["quality_gate"] = semantic_quality_gate(result)
    return result


def semantic_quality_gate(plan: dict[str, Any]) -> dict[str, Any]:
    scenes = [dict(item) for item in plan.get("scenes") or [] if isinstance(item, dict)]
    expected = canonical_scene_count(plan.get("scene_count"))
    errors: list[str] = []
    if len(scenes) != expected:
        errors.append(f"scene_count_mismatch:{len(scenes)}:{expected}")
    normalized_ideas: set[str] = set()
    for index, scene in enumerate(scenes, start=1):
        for field in SCENE_REQUIRED_FIELDS:
            value = scene.get(field)
            if field == "dialogue_or_voiceover":
                continue
            if value in (None, "", []):
                errors.append(f"scene_{index}:missing_{field}")
        idea = re.sub(r"[^a-z0-9à-ỹ]+", " ", str(scene.get("main_idea") or "").lower()).strip()
        if idea in normalized_ideas:
            errors.append(f"scene_{index}:duplicate_main_idea")
        normalized_ideas.add(idea)
        if not all(bool(scene.get(flag)) for flag in ("semantic_complete", "action_completed", "dialogue_completed", "camera_motion_completed")):
            errors.append(f"scene_{index}:truncated_beat")
        words = len(str(scene.get("dialogue_or_voiceover") or "").split())
        if words > max(1, int(scene.get("duration_seconds") or SCENE_SECONDS) * 2.2):
            errors.append(f"scene_{index}:dialogue_too_long")
    if scenes and not any(token in str(scenes[-1].get("scene_role") or "") for token in ("complete", "result", "cta", "hero", "resolution", "recap", "conclusion", "state")):
        errors.append("final_scene_missing_complete_conclusion")
    continuity = dict(plan.get("continuity_validation") or {})
    if not continuity.get("ok", True):
        errors.extend(str(item) for item in continuity.get("warnings") or [])
    return {
        "ok": not errors,
        "errors": list(dict.fromkeys(errors)),
        "exact_scene_count": len(scenes) == expected,
        "unique_semantic_beats": len(normalized_ideas) == len(scenes),
        "final_conclusion_complete": "final_scene_missing_complete_conclusion" not in errors,
        "provider_called": False,
        "job_created": False,
        "xu_charged": 0,
    }


def replace_scene_idea(plan: dict[str, Any], scene_index: int, new_idea: str) -> dict[str, Any]:
    updated = deepcopy(plan)
    index = max(1, min(len(updated.get("scenes") or []), int(scene_index or 1)))
    scene = updated["scenes"][index - 1]
    scene["main_idea"] = _clean(new_idea)
    scene["primary_action"] = f"Hoàn tất hành động thể hiện rõ: {_clean(new_idea)}"
    scene["completion_state"] = f"Ý mới của cảnh {index} đã được truyền tải trọn vẹn"
    scene["provider_prompt"] = (
        f"Cảnh {index}: {_clean(new_idea)}. Hoàn tất toàn bộ hành động trước khi chuyển cảnh; "
        "giữ continuity và không cắt giữa lời nói hoặc chuyển động camera."
    )
    updated["quality_gate"] = semantic_quality_gate(updated)
    return updated


def reorder_scenes(plan: dict[str, Any], order: list[int]) -> dict[str, Any]:
    updated = deepcopy(plan)
    scenes = list(updated.get("scenes") or [])
    expected = list(range(1, len(scenes) + 1))
    normalized = [int(item) for item in order]
    if sorted(normalized) != expected:
        raise ValueError("invalid_scene_order")
    reordered = [deepcopy(scenes[item - 1]) for item in normalized]
    previous: dict[str, Any] | None = None
    for index, scene in enumerate(reordered, start=1):
        scene["scene_index"] = index
        scene["inherited_from_previous"] = str((previous or {}).get("completion_state") or "")
        if previous:
            scene["start_state"] = scene["inherited_from_previous"]
        previous = scene
    transitions = plan_transitions(reordered, profile_id=str(updated.get("profile_id") or "general"))
    apply_transitions(reordered, transitions)
    updated["scenes"] = reordered
    updated["transitions"] = transitions
    updated["quality_gate"] = semantic_quality_gate(updated)
    return updated


def rebuild_for_scene_count(plan: dict[str, Any], scene_count: int) -> dict[str, Any]:
    return build_semantic_scene_plan(
        subject=str(plan.get("subject") or ""),
        scene_count=scene_count,
        profile_id=str(plan.get("profile_id") or "general"),
        context=str(plan.get("context") or ""),
        requirements=dict(plan.get("requirements") or {}),
        assets=dict(plan.get("assets") or {}),
        addon_plan=dict(plan.get("addon_plan") or {}),
    )
