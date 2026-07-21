"""Continuity prompt and reference-asset adapter layer.

The adapter returns payloads for callers. It does not import or mutate provider
code and it degrades to text prompt continuity when reference images are not
supported.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from services.video_asset_intake import VideoAssetPack, asset_reference_summary
from services.video_storyboard_planner import SceneCard, StoryBible


@dataclass
class VideoReferencePlan:
    story_bible: StoryBible
    scene_cards: list[SceneCard]
    asset_pack: VideoAssetPack
    provider_supports_reference_image: bool = False
    provider_supports_first_frame: bool = False
    provider_supports_last_frame: bool = False
    provider_supports_image_to_video: bool = False
    reference_mode: str = "text_fallback"
    manifest: dict[str, Any] = field(default_factory=dict)


def build_scene_prompt(story_bible: StoryBible, scene_card: SceneCard, *, total_scenes: int) -> str:
    reference_summary = _reference_summary_from_bible(story_bible)
    creative_controls = dict(getattr(story_bible, "creative_controls", {}) or {})
    creative_summary = "; ".join(f"{key}:{value}" for key, value in creative_controls.items() if value) or "profile defaults"
    prompt = f"""[CONTINUITY LOCK]
Keep the same subject/product/character:
{getattr(scene_card, "continuity_lock", "") or story_bible.subject_description}
Do not change:
identity, product shape/color/material, location logic, time of day, random text/logo placement
Asset summary: {reference_summary}

[SCENE ROLE]
Scene {scene_card.scene_index}/{total_scenes}
Role: {scene_card.role}
Purpose: {scene_card.visual_goal}

[VISUAL]
Subject: {getattr(scene_card, "exact_subject", "") or story_bible.main_subject}
Product/object: {getattr(scene_card, "exact_product_or_object", "") or story_bible.product_description}
Location: {getattr(scene_card, "exact_location", "") or story_bible.setting}
Lighting: {getattr(scene_card, "lighting", "") or story_bible.lighting}
Color tone: {getattr(scene_card, "color_tone", "") or story_bible.color_palette}
Mood: {story_bible.brand_tone}

[ACTION]
One clear visible action:
{scene_card.subject_action}

[CAMERA]
Angle: {getattr(scene_card, "camera_angle", "") or story_bible.camera_style}
Framing: {scene_card.composition}
Movement: {scene_card.camera_motion}

[TRANSITION]
Entry state: {getattr(scene_card, "entry_state", "") or scene_card.transition_from_previous}
Exit state: {getattr(scene_card, "exit_state", "") or scene_card.transition_to_next}
Bridge to next: {scene_card.transition_to_next}
Match cut hint: {getattr(scene_card, "match_cut_hint", "")}

[STYLE]
Profile style: {story_bible.visual_style}
Creative controls: {creative_summary}
Pacing: {story_bible.motion_style}

[POSTPROCESS READINESS]
Narration/subtitle line: {scene_card.subtitle_line}
Music cue: {scene_card.music_cue}
SFX cue: {getattr(scene_card, "sfx_cue", "")}
Logo cue: {scene_card.logo_cue}

[NO TEXT RULE]
Do not generate random text/logos/watermarks. Subtitles/logo are added later in postprocess.

[NEGATIVE]
{scene_card.negative_prompt}
"""
    return prompt.strip()


def build_continuity_prompts(story_bible: StoryBible, scene_cards: list[SceneCard]) -> list[SceneCard]:
    total = len(scene_cards)
    updated: list[SceneCard] = []
    for card in scene_cards:
        card.provider_prompt = build_scene_prompt(story_bible, card, total_scenes=total)
        updated.append(card)
    return updated


def _reference_summary_from_bible(story_bible: StoryBible) -> str:
    payload = dict(story_bible.reference_assets_used or {})
    counts = []
    for key, value in payload.items():
        if isinstance(value, list) and value:
            counts.append(f"{key}:{len(value)}")
    return ", ".join(counts) if counts else "no user-supplied assets; use textual continuity rules"


def create_reference_plan(
    *,
    story_bible: StoryBible,
    scene_cards: list[SceneCard],
    asset_pack: VideoAssetPack,
    provider_supports_reference_image: bool = False,
    provider_supports_first_frame: bool = False,
    provider_supports_last_frame: bool = False,
    provider_supports_image_to_video: bool = False,
) -> VideoReferencePlan:
    supports_any = any([
        provider_supports_reference_image,
        provider_supports_first_frame,
        provider_supports_last_frame,
        provider_supports_image_to_video,
    ])
    mode = "provider_reference" if supports_any else "text_fallback"
    plan = VideoReferencePlan(
        story_bible=story_bible,
        scene_cards=scene_cards,
        asset_pack=asset_pack,
        provider_supports_reference_image=provider_supports_reference_image,
        provider_supports_first_frame=provider_supports_first_frame,
        provider_supports_last_frame=provider_supports_last_frame,
        provider_supports_image_to_video=provider_supports_image_to_video,
        reference_mode=mode,
    )
    plan.manifest = reference_adapter_payload(plan)
    return plan


def reference_adapter_payload(plan: VideoReferencePlan) -> dict[str, Any]:
    pack = plan.asset_pack
    payload: dict[str, Any] = {
        "reference_mode": plan.reference_mode,
        "reference_summary": asset_reference_summary(pack),
        "provider_core_touched": False,
        "text_prompt_fallback": plan.reference_mode == "text_fallback",
        "story_bible": {
            "profile_id": plan.story_bible.profile_id,
            "main_subject": plan.story_bible.main_subject,
            "visual_style": plan.story_bible.visual_style,
            "creative_controls": dict(getattr(plan.story_bible, "creative_controls", {}) or {}),
            "continuity_rules": list(plan.story_bible.continuity_rules),
        },
        "scene_prompts": [card.provider_prompt or build_scene_prompt(plan.story_bible, card, total_scenes=len(plan.scene_cards)) for card in plan.scene_cards],
    }
    if plan.provider_supports_reference_image or plan.provider_supports_image_to_video:
        payload["subject_refs"] = [asdict(item) for item in (pack.character_refs or pack.product_refs or pack.subject_refs)[:3]]
        payload["background_refs"] = [asdict(item) for item in pack.background_refs[:5]]
        payload["style_refs"] = [asdict(item) for item in pack.style_refs[:5]]
    else:
        payload["subject_refs"] = []
        payload["background_refs"] = []
        payload["style_refs"] = []
    if plan.provider_supports_first_frame:
        payload["first_frame_by_scene"] = {
            int(item.scene_index or index + 1): asdict(item)
            for index, item in enumerate(pack.storyboard_frames[:10])
        }
    else:
        payload["first_frame_by_scene"] = {}
    if plan.provider_supports_last_frame:
        payload["last_frame_policy"] = "use scene ending frame when renderer exposes it"
    return payload


def scene_prompt_has_one_primary_action(prompt: str) -> bool:
    marker = "[ACTION]"
    if marker not in prompt:
        return False
    section = prompt.split(marker, 1)[1].split("[CAMERA]", 1)[0]
    return ("One clear action only:" in section or "One clear visible action:" in section) and section.strip().count("\n") <= 3
