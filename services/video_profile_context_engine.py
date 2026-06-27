"""Select prompt context blocks from the local video prompt vault."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from services import video_prompt_vault
from services.video_asset_intake import VideoAssetPack, asset_reference_summary, pack_from_dict


@dataclass
class PromptContextBundle:
    profile_id: str
    profile_pack: dict[str, Any]
    selected_script_formula: str
    selected_hook_templates: list[str]
    selected_scene_role_templates: list[dict[str, str]]
    selected_visual_style: str
    selected_camera_language: str
    selected_motion_language: str
    selected_color_tone: str
    selected_transition_style: str
    selected_negative_prompt: str
    selected_voice_music_subtitle_cues: dict[str, Any]
    reason_summary: str
    product_domain: str = "general"
    provider_called: bool = False
    xu_charged: int = 0
    shared_blocks: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _asset_pack(value: Any) -> VideoAssetPack:
    if isinstance(value, VideoAssetPack):
        return value
    if isinstance(value, dict):
        return pack_from_dict(value)
    return VideoAssetPack()


def _tokens(text: str) -> set[str]:
    return {item for item in re.split(r"[^0-9A-Za-zÀ-ỹ]+", text.lower()) if item}


def _domain_score(domain: dict[str, Any], idea_tokens: set[str], asset_summary: str) -> int:
    keywords = _tokens(" ".join(str(item) for item in domain.get("keywords") or []))
    score = len(keywords & idea_tokens) * 3
    asset_lower = asset_summary.lower()
    for hint in ("product", "character", "background", "storyboard", "logo", "music", "voice"):
        if hint in asset_lower and hint in " ".join(keywords):
            score += 1
    return score


def _select_domain(profile_pack: dict[str, Any], user_idea: str, asset_summary: str) -> tuple[str, dict[str, Any], str]:
    domains = dict(profile_pack.get("product_domains") or {})
    if not domains:
        return "general", {}, "profile default"
    idea_tokens = _tokens(user_idea)
    scored = []
    for name, payload in domains.items():
        scored.append((_domain_score(dict(payload or {}), idea_tokens, asset_summary), str(name), dict(payload or {})))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    score, name, payload = scored[0]
    if score <= 0 and "general" in domains:
        return "general", dict(domains.get("general") or {}), "fallback general domain"
    return name, payload, f"matched domain '{name}' score={score}"


def _creative_override(creative_controls: dict[str, Any], key: str, fallback: str) -> str:
    value = _clean_text(creative_controls.get(key) if creative_controls else "")
    if value and value.lower() not in {"default", "mặc định", "theo profile"}:
        return value
    return fallback


def select_prompt_context(
    profile_id: str,
    user_idea: str = "",
    asset_pack: Any = None,
    creative_controls: dict[str, Any] | None = None,
    scene_count: int = 3,
    language: str = "vi",
) -> PromptContextBundle:
    pack = video_prompt_vault.load_profile_pack(profile_id)
    shared = {
        name: video_prompt_vault.load_shared_block(name)
        for name in video_prompt_vault.SHARED_BLOCKS
    }
    assets = _asset_pack(asset_pack)
    asset_summary = asset_reference_summary(assets)
    domain_name, domain, domain_reason = _select_domain(pack, _clean_text(user_idea), asset_summary)

    formulas = list(domain.get("script_formulas") or pack.get("script_formulas") or [])
    hooks = list(domain.get("hook_templates") or []) + list(pack.get("hook_templates") or [])
    role_templates = list(domain.get("scene_role_templates") or pack.get("scene_role_templates") or [])
    visual_style = _creative_override(
        creative_controls or {},
        "visual_style",
        _clean_text(domain.get("visual_style") or (pack.get("visual_style_templates") or [""])[0]),
    )
    camera = _creative_override(
        creative_controls or {},
        "camera_angle",
        _clean_text(domain.get("camera") or (pack.get("camera_templates") or [""])[0]),
    )
    motion = _creative_override(
        creative_controls or {},
        "camera_motion",
        _clean_text(domain.get("motion") or (pack.get("motion_templates") or [""])[0]),
    )
    color = _creative_override(
        creative_controls or {},
        "color_tone",
        _clean_text(domain.get("color") or (pack.get("color_tone_templates") or [""])[0]),
    )
    transition = _clean_text(domain.get("transition") or (pack.get("transition_templates") or [""])[0])
    negative_blocks = list(shared["negative_prompts"].get("blocks") or []) + list(pack.get("negative_prompt_blocks") or [])
    negative_extra = _clean_text((creative_controls or {}).get("negative_prompt_extra"))
    if negative_extra:
        negative_blocks.append(negative_extra)
    pacing_note = "short compact pacing" if int(scene_count or 0) <= 3 else "multi-scene pacing with bridge continuity"
    reason = (
        f"profile={pack.get('profile_id')} primary; {domain_reason}; assets={asset_summary}; "
        f"scene_count={int(scene_count or 0)} -> {pacing_note}; language={language}; provider_called=False; xu_charged=0"
    )
    return PromptContextBundle(
        profile_id=str(pack.get("profile_id") or profile_id),
        profile_pack=pack,
        selected_script_formula=_clean_text(formulas[0] if formulas else pack.get("script_formula") or ""),
        selected_hook_templates=[_clean_text(item) for item in hooks[:5] if _clean_text(item)],
        selected_scene_role_templates=[dict(item or {}) for item in role_templates[:8]],
        selected_visual_style=visual_style,
        selected_camera_language=camera,
        selected_motion_language=motion,
        selected_color_tone=color,
        selected_transition_style=transition,
        selected_negative_prompt=", ".join(dict.fromkeys(_clean_text(item) for item in negative_blocks if _clean_text(item))),
        selected_voice_music_subtitle_cues={
            "voice": list(pack.get("voice_cues") or []),
            "music": list(pack.get("music_cues") or []),
            "subtitle": list(pack.get("subtitle_cues") or []),
            "logo": list(pack.get("logo_cues") or []),
            "postprocess": list(shared["postprocess_cues"].get("blocks") or []),
        },
        reason_summary=reason,
        product_domain=domain_name,
        provider_called=False,
        xu_charged=0,
        shared_blocks=shared,
    )
