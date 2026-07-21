"""Deterministic professional prompt builder for AI Video Editing."""

from __future__ import annotations

import hashlib
import re
from typing import Any


NEGATIVE_PROMPT_ITEMS = (
    "identity drift",
    "face deformation",
    "extra fingers or limbs",
    "warped product geometry",
    "logo corruption",
    "architectural geometry changes",
    "camera jitter",
    "duplicated objects",
    "frame flicker",
    "inconsistent lighting",
    "text artifacts",
    "low resolution",
    "overexposure",
    "frame interpolation errors",
)

INTENSITY_DIRECTIONS = {
    "light": "Use restrained changes that remain close to the source footage.",
    "medium": "Apply a clearly visible but controlled professional transformation.",
    "strong": "Apply a strong treatment while preserving every selected constraint.",
    "creative": "Apply an expressive transformation only where the preservation rules allow it.",
}

PRESERVE_COPY = {
    "preserve_identity": "preserve the exact face and identity",
    "preserve_subject": "preserve the main person or subject",
    "preserve_outfit": "preserve the exact outfit, fabric and body proportions",
    "preserve_product_logo": "preserve product shape, labels, logos and brand colors exactly",
    "preserve_composition": "preserve the source composition and important object positions",
    "preserve_architecture": "preserve wall openings, windows, room dimensions and architectural geometry exactly",
    "preserve_original_motion": "preserve the original action timing and camera path",
    "preserve_source_audio": "preserve the source audio without adding copyrighted music",
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _source_description(metadata: dict[str, Any], footage_type: str) -> str:
    width = int(metadata.get("width") or 0)
    height = int(metadata.get("height") or 0)
    duration = float(metadata.get("duration") or 0)
    fps = float(metadata.get("fps") or 0)
    audio = "with source audio" if metadata.get("has_audio") else "without source audio"
    facts = [f"uploaded {footage_type or 'ordinary video'}"]
    if width > 0 and height > 0:
        facts.append(f"{width}x{height}")
    if duration > 0:
        facts.append(f"{duration:.1f} seconds")
    if fps > 0:
        facts.append(f"{fps:.2f} fps")
    facts.append(audio)
    return ", ".join(facts)


def build_professional_prompt(
    route: dict[str, Any],
    *,
    user_request: str,
    source_metadata: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build all fourteen sections without calling an LLM or provider."""
    metadata = dict(source_metadata or {})
    controls = dict(route.get("preserve_controls") or {})
    options = dict(settings or {})
    profile = dict(route.get("profile") or {})
    intensity = str(options.get("intensity") or route.get("intensity") or "medium")
    effect_stack = list(route.get("selected_effect_stack") or profile.get("effect_stack") or [])
    preserve = [copy for key, copy in PRESERVE_COPY.items() if controls.get(key)]
    if controls.get("replace_background"):
        background = "Replace the background only as explicitly requested, while preserving clean subject edges and contact shadows."
    else:
        background = "Keep the original environment and background unless a selected effect only changes lighting or color."
    aspect = _clean(options.get("target_aspect_ratio") or route.get("target_aspect_ratio") or "keep source")
    aspect_method = _clean(options.get("aspect_method") or "crop theo khung")
    effect_timing = _clean(options.get("effect_timing") or "toàn video")
    duration = int(options.get("target_duration_seconds") or route.get("target_duration_seconds") or 0)
    text_pref = _clean(options.get("text_preference") or "do not add unrequested text, captions or logos")
    camera_pref = _clean(options.get("camera_motion_preference") or profile.get("camera_motion_treatment") or "preserve source motion")
    audio_policy = (
        "Preserve and normalize the source audio. Do not add copyrighted music."
        if controls.get("preserve_source_audio", True)
        else "Do not invent or add copyrighted music; keep audio changes limited to the explicit user request."
    )
    sections = {
        "source_description": _source_description(metadata, str(route.get("footage_type") or "ordinary_video")),
        "transformation_objective": _clean(user_request) or _clean(profile.get("visual_objective")),
        "selected_profile": _clean(route.get("profile_title") or profile.get("title_vi") or "professional video edit"),
        "subject_preservation": "; ".join(preserve) or "preserve the main subject and all factual source details",
        "environment_background": background,
        "lighting": _clean(profile.get("lighting_treatment") or "balanced realistic lighting"),
        "color_grade": _clean(profile.get("color_treatment") or "natural controlled color grade"),
        "effects": (", ".join(effect_stack) or "subtle professional enhancement") + f"; timing: {effect_timing}",
        "camera_motion": camera_pref,
        "timing_pacing": f"Preserve coherent timing. {INTENSITY_DIRECTIONS.get(intensity, INTENSITY_DIRECTIONS['medium'])}",
        "aspect_resolution": f"Target aspect ratio {aspect}; method: {aspect_method}; keep a valid resolution no larger than the configured output limit.",
        "output_realism_style": _clean(profile.get("visual_objective") or "polished, coherent and artifact-free output"),
        "audio_policy": audio_policy,
        "text_logo_caption_policy": text_pref,
    }
    if duration > 0:
        sections["timing_pacing"] += f" Target duration: {duration} seconds."
    ordered = (
        ("Source", sections["source_description"]),
        ("Objective", sections["transformation_objective"]),
        ("Profile", sections["selected_profile"]),
        ("Preservation", sections["subject_preservation"]),
        ("Environment", sections["environment_background"]),
        ("Lighting", sections["lighting"]),
        ("Color", sections["color_grade"]),
        ("Effects", sections["effects"]),
        ("Camera and motion", sections["camera_motion"]),
        ("Timing and pacing", sections["timing_pacing"]),
        ("Aspect and resolution", sections["aspect_resolution"]),
        ("Realism and style", sections["output_realism_style"]),
        ("Audio", sections["audio_policy"]),
        ("Text/logo/caption", sections["text_logo_caption_policy"]),
    )
    prompt = "\n".join(f"{label}: {value}" for label, value in ordered if _clean(value))
    negative_items = list(NEGATIVE_PROMPT_ITEMS)
    negative_items.extend(profile.get("negative_prompt") or [])
    negative_prompt = ", ".join(dict.fromkeys(_clean(item) for item in negative_items if _clean(item)))
    digest = hashlib.sha256((prompt + "\nNEGATIVE:" + negative_prompt).encode("utf-8")).hexdigest()
    return {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "prompt_hash": digest,
        "sections": sections,
        "intensity": intensity,
        "preserve_constraints": list(route.get("preserve_constraints") or []),
        "provider_called": False,
    }


def prompt_preview(payload: dict[str, Any], maximum: int = 2200) -> str:
    prompt = _clean(str(payload.get("prompt") or "").replace("\n", " | "))
    negative = _clean(payload.get("negative_prompt"))
    text = f"{prompt}\n\nTránh: {negative}"
    return text[: max(200, int(maximum or 2200))]


__all__ = ["NEGATIVE_PROMPT_ITEMS", "build_professional_prompt", "prompt_preview"]
