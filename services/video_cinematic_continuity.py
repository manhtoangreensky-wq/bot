"""Cinematic continuity ledger for video storyboard scene chains."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ContinuityLedger:
    main_subject: str
    subject_identity_rules: list[str]
    product_identity_rules: list[str]
    character_identity_rules: list[str]
    outfit_material_color: str
    location_logic: str
    time_of_day: str
    lighting_arc: str
    camera_arc: str
    emotional_arc: str
    object_positions: list[str]
    visual_motifs: list[str]
    color_palette: str
    transition_plan: list[dict[str, str]]
    forbidden_changes: list[str]
    continuity_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _profile_arc(profile_id: str, scene_count: int) -> str:
    if profile_id == "cinematic_trailer":
        return "quiet setup -> incident -> escalation -> impact glimpse -> title/CTA"
    if profile_id == "storytelling":
        return "character need -> pressure -> emotional turn -> resolution"
    if profile_id in {"product_review", "ugc_affiliate"}:
        return "problem -> product reveal -> proof -> benefit -> CTA"
    if profile_id == "lofi_audio_visualizer":
        return "loop intro -> subtle variation -> return to first visual motif"
    if profile_id == "food_asmr":
        return "ingredient beauty -> texture action -> taste/craving"
    return f"clear opening -> connected middle -> clean ending across {max(1, int(scene_count or 1))} scenes"


def _transition_type(profile_id: str, index: int, selected_transition: str) -> str:
    if profile_id == "lofi_audio_visualizer":
        return "loop bridge"
    if profile_id in {"fashion_lookbook", "ugc_affiliate"}:
        return "cut on beat"
    if profile_id == "real_estate_fpv":
        return "motivated camera pan"
    if profile_id in {"product_review", "food_asmr"}:
        return "object close-up to next scene"
    if profile_id == "cinematic_trailer":
        return "match cut" if index % 2 else "light/color bridge"
    return selected_transition or "match cut"


def build_continuity_ledger(
    *,
    profile_id: str,
    story_bible: Any,
    prompt_context: Any,
    scene_count: int,
) -> ContinuityLedger:
    main_subject = str(getattr(story_bible, "main_subject", "") or "video subject")
    selected_transition = str(getattr(prompt_context, "selected_transition_style", "") or "")
    transition_plan = []
    total = max(1, int(scene_count or 1))
    for index in range(1, total + 1):
        transition_plan.append({
            "scene_index": str(index),
            "type": _transition_type(str(profile_id), index, selected_transition),
            "entry_state": f"{main_subject} enters scene {index} with identity locked",
            "exit_state": f"{main_subject} exits scene {index} preserving color, shape, outfit/material",
            "bridge_to_next": "final scene resolves the arc" if index == total else f"carry motion/object/light from scene {index} into scene {index + 1}",
            "match_cut_hint": "match subject/object position or movement direction across the cut",
            "camera_bridge": "keep camera language consistent with previous scene",
            "visual_bridge": "repeat the strongest motif, color or object detail",
            "audio_bridge": "carry music/SFX tail into next scene when postprocess is enabled",
        })
    return ContinuityLedger(
        main_subject=main_subject,
        subject_identity_rules=[
            f"Keep {main_subject} as the same subject across every scene",
            "Do not change face/body/product silhouette/material/color unless user explicitly asked",
        ],
        product_identity_rules=[
            "Keep product shape, label area, color and material stable",
            "No invented extra product variants",
        ],
        character_identity_rules=[
            "Keep clothing, hairstyle and body proportions consistent",
            "No random extra recurring character",
        ],
        outfit_material_color=str(getattr(story_bible, "color_palette", "") or "profile palette"),
        location_logic=str(getattr(story_bible, "setting", "") or "consistent location logic"),
        time_of_day=str(getattr(story_bible, "time_of_day", "") or "consistent time"),
        lighting_arc=str(getattr(story_bible, "lighting", "") or "consistent lighting"),
        camera_arc=str(getattr(story_bible, "camera_style", "") or "consistent camera"),
        emotional_arc=_profile_arc(str(profile_id), total),
        object_positions=[f"{main_subject} remains readable and centered enough for continuity"],
        visual_motifs=[main_subject, str(getattr(prompt_context, "selected_color_tone", "") or "profile color")],
        color_palette=str(getattr(prompt_context, "selected_color_tone", "") or getattr(story_bible, "color_palette", "")),
        transition_plan=transition_plan,
        forbidden_changes=[
            "do not change identity",
            "do not change product shape/color",
            "do not add random text/logos",
            "do not break location/time logic",
        ],
        continuity_warnings=[],
    )


def scene_state(ledger: ContinuityLedger, scene_index: int) -> dict[str, str]:
    total = len(ledger.transition_plan)
    index = max(1, min(total, int(scene_index or 1)))
    return dict(ledger.transition_plan[index - 1])


def apply_continuity_to_scene_cards(scene_cards: list[Any], ledger: ContinuityLedger, prompt_context: Any) -> list[Any]:
    total = len(scene_cards)
    for card in scene_cards:
        state = scene_state(ledger, int(getattr(card, "scene_index", 1)))
        setattr(card, "exact_subject", ledger.main_subject)
        setattr(card, "exact_product_or_object", ledger.main_subject)
        setattr(card, "exact_location", ledger.location_logic)
        setattr(card, "camera_angle", str(getattr(prompt_context, "selected_camera_language", "") or ledger.camera_arc))
        setattr(card, "lighting", ledger.lighting_arc)
        setattr(card, "color_tone", ledger.color_palette)
        setattr(card, "entry_state", state["entry_state"])
        setattr(card, "exit_state", state["exit_state"])
        setattr(card, "transition_from_previous", state["entry_state"] if int(getattr(card, "scene_index", 1)) == 1 else state["camera_bridge"])
        setattr(card, "transition_to_next", state["bridge_to_next"])
        setattr(card, "match_cut_hint", state["match_cut_hint"])
        setattr(card, "sfx_cue", state["audio_bridge"])
        setattr(card, "continuity_lock", "; ".join(ledger.subject_identity_rules + ledger.forbidden_changes))
        if int(getattr(card, "scene_index", 1)) == total:
            setattr(card, "transition_to_next", "final scene resolves the arc cleanly")
    return scene_cards
