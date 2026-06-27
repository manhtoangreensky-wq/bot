"""Storyboard planner that turns profiles and assets into a shared story bible."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from services.video_asset_intake import VideoAssetPack, asset_reference_summary, pack_to_dict
from services.video_product_profiles import VideoProductProfile, get_video_profile, profile_template


DEFAULT_NEGATIVE_PROMPT = (
    "random text artifacts, unreadable words, inconsistent identity, changing product shape, "
    "extra characters, logo distortion, watermark, flicker, jump cut, cluttered background"
)


@dataclass
class StoryBible:
    profile_id: str
    title: str
    core_message: str
    target_audience: str
    brand_tone: str
    visual_style: str
    color_palette: str
    main_subject: str
    subject_description: str
    product_description: str
    character_description: str
    object_description: str
    setting: str
    time_of_day: str
    lighting: str
    camera_style: str
    motion_style: str
    continuity_rules: list[str]
    reference_assets_used: dict[str, Any]
    negative_prompt: str
    voice_policy: str
    music_policy: str
    subtitle_policy: str
    logo_policy: str
    fact_policy: str = ""


@dataclass
class SceneCard:
    scene_index: int
    role: str
    duration_seconds: float
    narration_line: str
    subtitle_line: str
    visual_goal: str
    subject_action: str
    camera_motion: str
    composition: str
    background: str
    reference_asset_ids: list[str]
    transition_from_previous: str
    transition_to_next: str
    music_cue: str
    logo_cue: str
    provider_prompt: str = ""
    negative_prompt: str = DEFAULT_NEGATIVE_PROMPT


@dataclass
class StoryboardPlan:
    profile: VideoProductProfile
    story_bible: StoryBible
    scene_cards: list[SceneCard]
    asset_pack: VideoAssetPack
    preview_text: str
    provider_called: bool = False
    xu_charged: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.to_public_dict(),
            "story_bible": asdict(self.story_bible),
            "scene_cards": [asdict(card) for card in self.scene_cards],
            "asset_pack": pack_to_dict(self.asset_pack),
            "preview_text": self.preview_text,
            "provider_called": self.provider_called,
            "xu_charged": self.xu_charged,
        }


def _clean_text(value: str, fallback: str = "") -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text or fallback


def _title_from_idea(idea_text: str, profile: VideoProductProfile) -> str:
    text = _clean_text(idea_text)
    if not text:
        return profile.menu_label
    text = re.sub(r"[.!?].*$", "", text).strip()
    return text[:72] or profile.menu_label


def _asset_ids(pack: VideoAssetPack) -> list[str]:
    ids: list[str] = []
    for field_name in (
        "subject_refs",
        "product_refs",
        "object_refs",
        "character_refs",
        "background_refs",
        "style_refs",
        "storyboard_frames",
        "logo_refs",
    ):
        ids.extend(slot.slot_id for slot in getattr(pack, field_name))
    return ids


def create_story_bible(
    profile: VideoProductProfile | str,
    asset_pack: VideoAssetPack | None = None,
    *,
    idea_text: str = "",
    target_audience: str = "khán giả short-form",
    brand_tone: str = "rõ ràng, hữu ích, tự nhiên",
) -> StoryBible:
    item = get_video_profile(profile) if isinstance(profile, str) else profile
    pack = asset_pack or VideoAssetPack()
    idea = _clean_text(idea_text, item.product_goal)
    asset_summary = asset_reference_summary(pack)
    main_subject = "chủ thể chính từ ý tưởng hoặc ảnh tham chiếu"
    if pack.product_refs:
        main_subject = "sản phẩm chính trong ảnh tham chiếu"
    elif pack.character_refs:
        main_subject = "nhân vật chính trong ảnh tham chiếu"
    elif pack.subject_refs:
        main_subject = "chủ thể chính trong ảnh tham chiếu"

    fact_policy = item.fact_policy
    if item.profile_id in {"news", "history"} and not idea_text.strip():
        fact_policy = (fact_policy + " Input lacks facts; mark as chua du du lieu.").strip()

    continuity_rules = [
        "keep same main subject/product/character identity",
        "keep clothing/material/shape/color consistent",
        "keep location logic consistent",
        "use transition hints between scenes",
        "avoid inventing new characters/products unless user asked",
        "one main action per scene",
        "no random text artifacts in image/video",
        "no unnecessary style shift",
    ]
    return StoryBible(
        profile_id=item.profile_id,
        title=_title_from_idea(idea, item),
        core_message=idea,
        target_audience=target_audience,
        brand_tone=brand_tone,
        visual_style=item.image_style,
        color_palette="consistent palette based on profile and references",
        main_subject=main_subject,
        subject_description=f"{main_subject}; {asset_summary}",
        product_description="use product/object reference consistently" if (pack.product_refs or pack.object_refs) else "derive product details only from user input",
        character_description="keep character face, outfit, and silhouette consistent" if pack.character_refs else "do not invent a new recurring character unless the story requires it",
        object_description="keep object material, color, and shape consistent" if pack.object_refs else "no extra product/object unless requested",
        setting="location logic follows user idea and background references" if pack.background_refs else "simple consistent location logic",
        time_of_day="consistent time of day across connected scenes",
        lighting=item.image_style,
        camera_style=item.camera_style,
        motion_style=item.motion_style,
        continuity_rules=continuity_rules,
        reference_assets_used=pack_to_dict(pack),
        negative_prompt=DEFAULT_NEGATIVE_PROMPT,
        voice_policy=item.voice_style,
        music_policy=item.music_style,
        subtitle_policy=item.subtitle_style,
        logo_policy=item.logo_policy,
        fact_policy=fact_policy,
    )


def _narration_for_scene(bible: StoryBible, role: str, purpose: str, index: int, total: int) -> str:
    if bible.profile_id == "philosophy_quotes" and index == 2:
        return f"[pause 0.8s] {purpose}"
    if bible.profile_id == "news" and bible.fact_policy and "chua du du lieu" in bible.fact_policy:
        return "Thông tin hiện chưa đủ dữ liệu; đây là bản khung cần xác minh thêm."
    if bible.profile_id == "history" and bible.fact_policy and "dramatized" in bible.fact_policy.lower():
        return "Đây là phần dựng lại theo phong cách lịch sử, không trình bày như sự kiện đã xác minh."
    return f"{purpose} ({index}/{total})"


def build_scene_cards(
    story_bible: StoryBible,
    profile: VideoProductProfile | str,
    *,
    scene_count: int = 3,
    asset_pack: VideoAssetPack | None = None,
    duration_seconds: float = 6.0,
) -> list[SceneCard]:
    item = get_video_profile(profile) if isinstance(profile, str) else profile
    count = 5 if int(scene_count or 3) >= 5 else 3
    template = profile_template(item, count)
    pack = asset_pack or VideoAssetPack()
    asset_ids = _asset_ids(pack)
    cards: list[SceneCard] = []
    for index, template_item in enumerate(template, start=1):
        role = template_item["role"]
        purpose = template_item["purpose"]
        previous_hint = "start cleanly from the established story bible" if index == 1 else f"continue the visual logic from scene {index - 1}"
        next_hint = "prepare the ending cleanly" if index == count else f"set up scene {index + 1} with a natural visual bridge"
        narration = _narration_for_scene(story_bible, role, purpose, index, count)
        card = SceneCard(
            scene_index=index,
            role=role,
            duration_seconds=float(duration_seconds),
            narration_line=narration,
            subtitle_line=narration.replace("[pause 0.8s]", "").strip(),
            visual_goal=purpose,
            subject_action=f"{story_bible.main_subject} performs one clear action for {role}",
            camera_motion=item.camera_style,
            composition=f"{template_item['title']}; stable framing; no clutter",
            background=story_bible.setting,
            reference_asset_ids=asset_ids[:6],
            transition_from_previous=previous_hint,
            transition_to_next=next_hint,
            music_cue=item.music_style,
            logo_cue=item.logo_policy if index == count else "no logo unless subtle watermark is required",
            negative_prompt=story_bible.negative_prompt,
        )
        cards.append(card)
    return cards


def storyboard_preview_text(plan: StoryboardPlan) -> str:
    bible = plan.story_bible
    lines = [
        "Storyboard preview",
        f"Profile: {plan.profile.menu_label}",
        f"Title: {bible.title}",
        f"Main subject: {bible.main_subject}",
        f"Style: {bible.visual_style}",
        f"Scene count: {len(plan.scene_cards)}",
        "Scenes:",
    ]
    for card in plan.scene_cards:
        lines.append(f"{card.scene_index}. {card.role}: {card.visual_goal}")
    lines.extend([
        f"Voice: {bible.voice_policy}",
        f"Music: {bible.music_policy}",
        f"Subtitle: {bible.subtitle_policy}",
        f"Logo: {bible.logo_policy}",
        f"Reference assets: {asset_reference_summary(plan.asset_pack)}",
        "No render/provider call before storyboard confirm.",
    ])
    return "\n".join(lines)


def create_storyboard_plan(
    *,
    profile_id: str,
    idea_text: str,
    asset_pack: VideoAssetPack | None = None,
    scene_count: int = 3,
    target_audience: str = "khán giả short-form",
) -> StoryboardPlan:
    profile = get_video_profile(profile_id)
    pack = asset_pack or VideoAssetPack()
    bible = create_story_bible(profile, pack, idea_text=idea_text, target_audience=target_audience)
    cards = build_scene_cards(bible, profile, scene_count=scene_count, asset_pack=pack)
    plan = StoryboardPlan(profile=profile, story_bible=bible, scene_cards=cards, asset_pack=pack, preview_text="")
    plan.preview_text = storyboard_preview_text(plan)
    return plan


def render_allowed_for_plan(plan: StoryboardPlan, *, storyboard_confirmed: bool, final_confirmed: bool) -> bool:
    return bool(storyboard_confirmed and final_confirmed and not plan.provider_called and plan.xu_charged == 0)
