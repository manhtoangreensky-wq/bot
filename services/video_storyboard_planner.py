"""Storyboard planner that turns profiles and assets into a shared story bible."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from services.video_asset_intake import VideoAssetPack, asset_reference_summary, pack_to_dict
from services.video_cinematic_continuity import apply_continuity_to_scene_cards, build_continuity_ledger
from services.video_profile_context_engine import select_prompt_context
from services.video_product_profiles import VideoProductProfile, get_video_profile, profile_template


DEFAULT_NEGATIVE_PROMPT = (
    "random text artifacts, unreadable words, inconsistent identity, changing product shape, "
    "extra characters, logo distortion, watermark, flicker, jump cut, cluttered background"
)

GENERIC_PROMPT_PHRASES = (
    "sản phẩm chính trong ảnh tham chiếu",
    "performs one clear action",
    "user idea",
    "main subject",
    "reference asset",
    "reference image",
    "do something",
    "generic product",
    "scene continues naturally",
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
    creative_controls: dict[str, Any] = field(default_factory=dict)


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
    exact_subject: str = ""
    exact_product_or_object: str = ""
    exact_location: str = ""
    camera_angle: str = ""
    lighting: str = ""
    color_tone: str = ""
    entry_state: str = ""
    exit_state: str = ""
    match_cut_hint: str = ""
    sfx_cue: str = ""
    continuity_lock: str = ""
    provider_prompt: str = ""
    negative_prompt: str = DEFAULT_NEGATIVE_PROMPT
    quality_score: dict[str, int] = field(default_factory=dict)


@dataclass
class StoryboardPlan:
    profile: VideoProductProfile
    story_bible: StoryBible
    scene_cards: list[SceneCard]
    asset_pack: VideoAssetPack
    preview_text: str
    prompt_context: dict[str, Any] = field(default_factory=dict)
    continuity_ledger: dict[str, Any] = field(default_factory=dict)
    provider_called: bool = False
    xu_charged: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.to_public_dict(),
            "story_bible": asdict(self.story_bible),
            "scene_cards": [asdict(card) for card in self.scene_cards],
            "asset_pack": pack_to_dict(self.asset_pack),
            "preview_text": self.preview_text,
            "prompt_context": dict(self.prompt_context or {}),
            "continuity_ledger": dict(self.continuity_ledger or {}),
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


def _strip_leading_intent_words(text: str) -> str:
    cleaned = _clean_text(text)
    cleaned = re.sub(
        r"^(review|quảng cáo|quang cao|bán hàng|ban hang|video|clip|tạo|tao|làm|lam|kể chuyện|ke chuyen|giới thiệu|gioi thieu)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return _clean_text(cleaned)


def _subject_from_idea(idea_text: str, profile: VideoProductProfile) -> str:
    text = _strip_leading_intent_words(idea_text)
    if not text:
        return _clean_text(profile.product_goal, profile.menu_label)[:96]
    text = re.split(r"\s+(?:cho|về|ve|bằng|bang|để|de)\s+", text, maxsplit=1)[-1] if len(text) > 120 else text
    text = re.sub(r"[,.;:!?]+$", "", text).strip()
    return (text[:96].strip() or profile.menu_label)


def _asset_detail_notes(pack: VideoAssetPack) -> list[str]:
    notes: list[str] = []
    for field_name in (
        "product_refs",
        "object_refs",
        "character_refs",
        "subject_refs",
        "background_refs",
        "style_refs",
        "storyboard_frames",
        "logo_refs",
        "voice_audio_refs",
        "music_audio_refs",
    ):
        count = len(getattr(pack, field_name))
        if count:
            label = field_name.replace("_refs", "").replace("_", " ")
            notes.append(f"{label}:{count}")
    return notes


def _main_subject_label(profile: VideoProductProfile, idea_text: str, pack: VideoAssetPack) -> str:
    subject = _subject_from_idea(idea_text, profile)
    if pack.product_refs:
        return f"sản phẩm chính: {subject}"
    if pack.character_refs:
        return f"nhân vật chính: {subject}"
    if pack.subject_refs:
        return f"chủ thể chính: {subject}"
    if pack.object_refs:
        return f"đồ vật chính: {subject}"
    return subject


def _setting_label(profile: VideoProductProfile, idea_text: str, pack: VideoAssetPack) -> str:
    subject = _subject_from_idea(idea_text, profile)
    if pack.background_refs:
        return f"bối cảnh theo ảnh tư liệu đã gửi, giữ logic quanh {subject}"
    if profile.profile_id == "real_estate_fpv":
        return f"không gian địa điểm/tài sản liên quan đến {subject}"
    if profile.profile_id in {"product_review", "ugc_affiliate", "food_asmr", "fashion_lookbook"}:
        return f"bối cảnh quay sạch, làm nổi bật {subject}"
    return f"bối cảnh nhất quán theo câu chuyện về {subject}"


def _specific_action(subject: str, role: str, purpose: str, index: int, total: int) -> str:
    role_clean = _clean_text(role, f"scene_{index}").replace("_", " ")
    purpose_clean = _clean_text(purpose, "thể hiện một ý chính rõ ràng")
    if role_clean.lower() in {"hook", "setup"}:
        return f"Đưa {subject} vào khung hình, tạo hook bằng một hành động trực quan: {purpose_clean.lower()}."
    if role_clean.lower() in {"proof", "product reveal", "product_reveal", "solution"}:
        return f"Cho {subject} thực hiện/demonstrate điểm chính của cảnh: {purpose_clean.lower()}."
    if role_clean.lower() in {"cta", "ending", "lesson"} or index == total:
        return f"Chốt cảnh bằng {subject}, nhấn kết quả hoặc lời kêu gọi hành động: {purpose_clean.lower()}."
    return f"Tiếp nối câu chuyện với {subject}, chỉ giữ một hành động chính: {purpose_clean.lower()}."


def scene_quality_score(card: SceneCard) -> dict[str, int]:
    text = " ".join(
        str(value or "")
        for value in (
            card.visual_goal,
            card.subject_action,
            card.camera_motion,
            card.composition,
            card.background,
            card.provider_prompt,
        )
    ).lower()
    has_forbidden = any(phrase in text for phrase in GENERIC_PROMPT_PHRASES)
    return {
        "subject_specificity": 0 if has_forbidden else min(5, max(1, len(card.subject_action.split()) // 4)),
        "action_specificity": 0 if has_forbidden else (5 if len(card.subject_action.split()) >= 10 else 3),
        "camera_specificity": 4 if len(card.camera_motion.split()) >= 4 else 2,
        "continuity_specificity": 4 if len(card.transition_from_previous.split()) >= 4 and len(card.transition_to_next.split()) >= 4 else 2,
        "addon_readiness": 5 if card.subtitle_line and card.music_cue and card.logo_cue else 2,
    }


def _asset_summary_from_bible(bible: StoryBible) -> str:
    payload = dict(bible.reference_assets_used or {})
    notes = []
    for key, value in payload.items():
        if isinstance(value, list) and value:
            notes.append(f"{key}:{len(value)}")
    return ", ".join(notes) if notes else "không có ảnh tư liệu; bám chặt mô tả chữ của người dùng"


def _normalize_creative_controls(value: dict[str, Any] | None = None) -> dict[str, str]:
    raw = dict(value or {})
    if "color_palette" not in raw and "color_tone" in raw:
        raw["color_palette"] = raw.get("color_tone")
    if "color_tone" not in raw and "color_palette" in raw:
        raw["color_tone"] = raw.get("color_palette")
    if "emotion_tone" not in raw and "mood" in raw:
        raw["emotion_tone"] = raw.get("mood")
    if "mood" not in raw and "emotion_tone" in raw:
        raw["mood"] = raw.get("emotion_tone")
    allowed = (
        "topic_mode",
        "color_palette",
        "color_tone",
        "visual_style",
        "camera_motion",
        "camera_angle",
        "pacing",
        "emotion_tone",
        "mood",
        "negative_prompt_extra",
    )
    return {key: _clean_text(str(raw.get(key) or "")) for key in allowed}


def _creative_value(controls: dict[str, str], key: str, fallback: str) -> str:
    value = _clean_text(controls.get(key) or "")
    if value and value.lower() not in {"default", "mặc định", "theo profile"}:
        return value
    return fallback


def _creative_summary(controls: dict[str, str]) -> str:
    visible = []
    labels = {
        "topic_mode": "topic",
        "color_palette": "color",
        "visual_style": "style",
        "camera_motion": "motion",
        "camera_angle": "angle",
        "pacing": "pacing",
        "emotion_tone": "emotion",
    }
    for key, label in labels.items():
        value = controls.get(key)
        if value:
            visible.append(f"{label}:{value}")
    return "; ".join(visible) if visible else "profile defaults"


def _provider_prompt_for_scene(bible: StoryBible, card: SceneCard, total: int) -> str:
    asset_notes = _asset_summary_from_bible(bible)
    creative_notes = _creative_summary(dict(bible.creative_controls or {}))
    prompt = f"""[CONTINUITY LOCK]
Keep the same subject/product/character:
{card.continuity_lock or bible.subject_description}
Do not change:
identity, product shape/color/material, location logic, time of day, random text/logo placement
Asset summary: {asset_notes}

[SCENE ROLE]
Scene {card.scene_index}/{total}
Role: {card.role}
Purpose: {card.visual_goal}

[VISUAL]
Subject: {card.exact_subject or bible.main_subject}
Product/object: {card.exact_product_or_object or bible.product_description}
Location: {card.exact_location or bible.setting}
Lighting: {card.lighting or bible.lighting}
Color tone: {card.color_tone or bible.color_palette}
Mood: {bible.brand_tone}

[ACTION]
One clear visible action:
{card.subject_action}

[CAMERA]
Angle: {card.camera_angle or bible.camera_style}
Framing: {card.composition}
Movement: {card.camera_motion}

[TRANSITION]
Entry state: {card.entry_state or card.transition_from_previous}
Exit state: {card.exit_state or card.transition_to_next}
Bridge to next: {card.transition_to_next}
Match cut hint: {card.match_cut_hint}

[STYLE]
Profile style: {bible.visual_style}
Creative controls: {creative_notes}
Pacing: {bible.motion_style}

[POSTPROCESS READINESS]
Narration/subtitle line: {card.subtitle_line}
Music cue: {card.music_cue}
SFX cue: {card.sfx_cue}
Logo cue: {card.logo_cue}

[NO TEXT RULE]
Do not generate random text/logos/watermarks. Subtitles/logo are added later in postprocess.

[NEGATIVE]
{card.negative_prompt}
"""
    return prompt.strip()


def repair_weak_scene_card(card: SceneCard, bible: StoryBible, profile: VideoProductProfile, *, total: int) -> SceneCard:
    subject = bible.main_subject
    card.subject_action = _specific_action(subject, card.role, card.visual_goal, card.scene_index, total)
    card.camera_motion = _clean_text(card.camera_motion, profile.camera_style)
    if len(card.camera_motion.split()) < 4:
        card.camera_motion = f"{profile.camera_style}; chuyển động rõ, ổn định, bám {subject}"
    card.composition = _clean_text(card.composition, f"{card.role}; khung hình rõ chủ thể; nền gọn")
    card.background = _clean_text(card.background, bible.setting)
    card.subtitle_line = _clean_text(card.subtitle_line, card.narration_line)
    card.provider_prompt = _provider_prompt_for_scene(bible, card, total)
    for phrase in GENERIC_PROMPT_PHRASES:
        card.provider_prompt = re.sub(re.escape(phrase), subject, card.provider_prompt, flags=re.IGNORECASE)
    card.quality_score = scene_quality_score(card)
    return card


def create_story_bible(
    profile: VideoProductProfile | str,
    asset_pack: VideoAssetPack | None = None,
    *,
    idea_text: str = "",
    target_audience: str = "khán giả short-form",
    brand_tone: str = "rõ ràng, hữu ích, tự nhiên",
    creative_controls: dict[str, Any] | None = None,
) -> StoryBible:
    item = get_video_profile(profile) if isinstance(profile, str) else profile
    pack = asset_pack or VideoAssetPack()
    idea = _clean_text(idea_text, item.product_goal)
    asset_summary = asset_reference_summary(pack)
    main_subject = _main_subject_label(item, idea, pack)
    controls = _normalize_creative_controls(creative_controls)
    visual_style = _creative_value(controls, "visual_style", item.image_style)
    color_palette = _creative_value(
        controls,
        "color_palette",
        _creative_value(controls, "color_tone", "consistent palette based on profile and references"),
    )
    camera_style = _creative_value(controls, "camera_angle", item.camera_style)
    motion_style = _creative_value(controls, "camera_motion", item.motion_style)
    pacing = _creative_value(controls, "pacing", item.pacing_policy)
    mood = _creative_value(controls, "emotion_tone", _creative_value(controls, "mood", brand_tone))
    negative_prompt_extra = controls.get("negative_prompt_extra")
    negative_prompt = DEFAULT_NEGATIVE_PROMPT
    if negative_prompt_extra:
        negative_prompt = f"{negative_prompt}, {negative_prompt_extra}"

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
        f"creative controls: {_creative_summary(controls)}",
    ]
    return StoryBible(
        profile_id=item.profile_id,
        title=_title_from_idea(idea, item),
        core_message=idea,
        target_audience=target_audience,
        brand_tone=mood,
        visual_style=visual_style,
        color_palette=color_palette,
        main_subject=main_subject,
        subject_description=f"{main_subject}; {asset_summary}",
        product_description=f"giữ đúng hình dáng/màu/chất liệu của {main_subject}" if (pack.product_refs or pack.object_refs) else f"chỉ dùng chi tiết sản phẩm có trong ý tưởng: {main_subject}",
        character_description=f"giữ diện mạo, trang phục và silhouette của {main_subject}" if pack.character_refs else "không tự thêm nhân vật lặp lại nếu ý tưởng không cần",
        object_description=f"giữ vật thể liên quan đến {main_subject} ổn định qua các cảnh" if pack.object_refs else "không thêm đồ vật phụ gây nhiễu nếu user không yêu cầu",
        setting=_setting_label(item, idea, pack),
        time_of_day="consistent time of day across connected scenes",
        lighting=f"{visual_style}; {color_palette}",
        camera_style=camera_style,
        motion_style=f"{motion_style}; {pacing}",
        continuity_rules=continuity_rules,
        reference_assets_used=pack_to_dict(pack),
        negative_prompt=negative_prompt,
        voice_policy=item.voice_style,
        music_policy=item.music_style,
        subtitle_policy=item.subtitle_style,
        logo_policy=item.logo_policy,
        fact_policy=fact_policy,
        creative_controls=controls,
    )


def _narration_for_scene(bible: StoryBible, role: str, purpose: str, index: int, total: int) -> str:
    if bible.profile_id == "philosophy_quotes" and index == 2:
        return f"[pause 0.8s] {purpose}"
    if bible.profile_id == "news" and bible.fact_policy and "chua du du lieu" in bible.fact_policy:
        return "Thông tin hiện chưa đủ dữ liệu; đây là bản khung cần xác minh thêm."
    if bible.profile_id == "history" and bible.fact_policy and "dramatized" in bible.fact_policy.lower():
        return "Đây là phần dựng lại theo phong cách lịch sử, không trình bày như sự kiện đã xác minh."
    return f"{bible.main_subject}: {purpose}"


def build_scene_cards(
    story_bible: StoryBible,
    profile: VideoProductProfile | str,
    *,
    scene_count: int = 3,
    asset_pack: VideoAssetPack | None = None,
    duration_seconds: float = 6.0,
) -> list[SceneCard]:
    item = get_video_profile(profile) if isinstance(profile, str) else profile
    requested = max(1, min(20, int(scene_count or 3)))
    count = requested
    template = profile_template(item, 5 if requested >= 5 else (3 if requested >= 3 else 3))
    pack = asset_pack or VideoAssetPack()
    asset_ids = _asset_ids(pack)
    cards: list[SceneCard] = []
    for index in range(1, count + 1):
        template_item = template[(index - 1) % len(template)]
        role = template_item["role"] if index <= len(template) else f"{template_item['role']}_part_{index}"
        purpose = template_item["purpose"]
        if index > len(template):
            purpose = f"{purpose} Mở rộng mạch kể ở cảnh {index} nhưng vẫn bám {story_bible.main_subject}."
        previous_hint = "start cleanly from the established story bible" if index == 1 else f"continue the visual logic from scene {index - 1}"
        next_hint = "prepare the ending cleanly" if index == count else f"set up scene {index + 1} with a natural visual bridge"
        narration = _narration_for_scene(story_bible, role, purpose, index, count)
        subject_action = _specific_action(story_bible.main_subject, role, purpose, index, count)
        card = SceneCard(
            scene_index=index,
            role=role,
            duration_seconds=float(duration_seconds),
            narration_line=narration,
            subtitle_line=narration.replace("[pause 0.8s]", "").strip(),
            visual_goal=purpose,
            subject_action=subject_action,
            camera_motion=f"{story_bible.motion_style}; bám {story_bible.main_subject} trong cảnh {index}",
            composition=f"{template_item['title']}; {story_bible.camera_style}; khung hình rõ {story_bible.main_subject}; nền gọn",
            background=story_bible.setting,
            reference_asset_ids=asset_ids[:6],
            transition_from_previous=previous_hint,
            transition_to_next=next_hint,
            music_cue=item.music_style,
            logo_cue=item.logo_policy if index == count else "no logo unless subtle watermark is required",
            exact_subject=story_bible.main_subject,
            exact_product_or_object=story_bible.product_description,
            exact_location=story_bible.setting,
            camera_angle=story_bible.camera_style,
            lighting=story_bible.lighting,
            color_tone=story_bible.color_palette,
            entry_state=previous_hint,
            exit_state=next_hint,
            match_cut_hint="match subject/object position or movement direction",
            sfx_cue=getattr(item, "sfx_policy", "") or "postprocess SFX only if enabled",
            continuity_lock="; ".join(story_bible.continuity_rules),
            negative_prompt=story_bible.negative_prompt,
        )
        card.provider_prompt = _provider_prompt_for_scene(story_bible, card, count)
        card.quality_score = scene_quality_score(card)
        if min(card.quality_score.values() or [0]) < 3:
            card = repair_weak_scene_card(card, story_bible, item, total=count)
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
    creative_controls: dict[str, Any] | None = None,
) -> StoryboardPlan:
    profile = get_video_profile(profile_id)
    pack = asset_pack or VideoAssetPack()
    prompt_context = select_prompt_context(
        profile_id=profile.profile_id,
        user_idea=idea_text,
        asset_pack=pack,
        creative_controls=creative_controls or {},
        scene_count=scene_count,
        language="vi",
    )
    controls = dict(creative_controls or {})
    controls.setdefault("visual_style", prompt_context.selected_visual_style)
    controls.setdefault("camera_angle", prompt_context.selected_camera_language)
    controls.setdefault("camera_motion", prompt_context.selected_motion_language)
    controls.setdefault("color_tone", prompt_context.selected_color_tone)
    controls.setdefault("negative_prompt_extra", "")
    bible = create_story_bible(
        profile,
        pack,
        idea_text=idea_text,
        target_audience=target_audience,
        creative_controls=controls,
    )
    cards = build_scene_cards(bible, profile, scene_count=scene_count, asset_pack=pack)
    ledger = build_continuity_ledger(
        profile_id=profile.profile_id,
        story_bible=bible,
        prompt_context=prompt_context,
        scene_count=len(cards),
    )
    cards = apply_continuity_to_scene_cards(cards, ledger, prompt_context)
    for card in cards:
        card.negative_prompt = prompt_context.selected_negative_prompt or card.negative_prompt
        card.provider_prompt = _provider_prompt_for_scene(bible, card, len(cards))
        card.quality_score = scene_quality_score(card)
        if min(card.quality_score.values() or [0]) < 3:
            card = repair_weak_scene_card(card, bible, profile, total=len(cards))
    plan = StoryboardPlan(
        profile=profile,
        story_bible=bible,
        scene_cards=cards,
        asset_pack=pack,
        preview_text="",
        prompt_context=prompt_context.to_dict(),
        continuity_ledger=ledger.to_dict(),
    )
    plan.preview_text = storyboard_preview_text(plan)
    return plan


def render_allowed_for_plan(plan: StoryboardPlan, *, storyboard_confirmed: bool, final_confirmed: bool) -> bool:
    return bool(storyboard_confirmed and final_confirmed and not plan.provider_called and plan.xu_charged == 0)
