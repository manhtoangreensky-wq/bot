"""Prompt extraction without synthetic OCR, ASR, transcript, or prompt content."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from services.media_classifier import category_for_text, normalize_text, tags_for_text


PROMPT_MARKERS = {
    "storyboard": ("storyboard", "scene 1", "scene 2", "canh 1", "shot list"),
    "workflow": ("workflow", "step 1", "buoc 1", "pipeline", "automation"),
    "music": ("music prompt", "bpm", "instrumental", "compose a song", "nhac"),
    "voice": ("voice prompt", "tts", "voice over", "narration", "giong doc"),
    "image": ("image prompt", "midjourney", "stable diffusion", "create an image", "tao anh"),
    "video": (
        "video prompt",
        "create a video",
        "tao video",
        "camera movement",
        "seedance",
        "veo",
        "kling",
        "gommo",
    ),
}

MODEL_HINTS = {
    "Gommo": ("gommo",),
    "Seedance": ("seedance",),
    "VEO": ("veo",),
    "Kling": ("kling",),
    "Midjourney": ("midjourney",),
    "MiniMax": ("minimax",),
}


@dataclass(frozen=True)
class PromptCandidate:
    prompt_type: str
    prompt_text: str
    source_original_text: str
    cleaned_prompt_text: str
    negative_prompt: str
    language: str
    model_hint: str
    ratio_hint: str
    duration_hint: str
    style_tags: list[str]
    scene_count: int
    category: str
    use_case: str
    source_confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def clean_prompt_text(value: str) -> str:
    text = str(value or "").replace("\x00", " ").strip()
    text = re.sub(r"```(?:json|text|prompt)?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^(prompt|câu lệnh|cau lenh)\s*:\s*", "", text, flags=re.IGNORECASE)
    return text.strip()[:12000]


def classify_prompt_type(value: str) -> str:
    text = normalize_text(value)
    for prompt_type in ("storyboard", "workflow", "music", "voice", "image", "video"):
        if any(normalize_text(marker) in text for marker in PROMPT_MARKERS[prompt_type]):
            return prompt_type
    return "caption"


def _model_hint(value: str) -> str:
    text = normalize_text(value)
    for model, markers in MODEL_HINTS.items():
        if any(normalize_text(marker) in text for marker in markers):
            return model
    return "generic"


def _language(value: str) -> str:
    text = str(value or "")
    vietnamese_markers = ("ă", "â", "đ", "ê", "ô", "ơ", "ư")
    return "vi" if any(marker in text.lower() for marker in vietnamese_markers) else "en"


def _ratio_hint(value: str) -> str:
    match = re.search(r"\b(9:16|16:9|1:1|4:5|3:2|2:3)\b", value)
    return match.group(1) if match else ""


def _duration_hint(value: str) -> str:
    match = re.search(r"\b(\d{1,4})\s*(?:s|sec|seconds|giây|giay)\b", value, re.IGNORECASE)
    return f"{match.group(1)}s" if match else ""


def _negative_prompt(value: str) -> str:
    match = re.search(
        r"(?:negative prompt|avoid|không có|khong co)\s*:\s*(.+?)(?:\n|$)",
        value,
        re.IGNORECASE,
    )
    return clean_prompt_text(match.group(1)) if match else ""


def _scene_count(value: str) -> int:
    scenes = re.findall(r"(?:scene|cảnh|canh)\s*(\d{1,2})", value, re.IGNORECASE)
    return max((int(item) for item in scenes), default=0)


def looks_like_prompt(value: str) -> bool:
    clean = clean_prompt_text(value)
    if len(clean) < 18:
        return False
    prompt_type = classify_prompt_type(clean)
    if prompt_type != "caption":
        return True
    imperative = re.search(
        r"\b(create|generate|design|write|compose|make|tạo|tao|viết|viet|hãy|hay)\b",
        clean,
        re.IGNORECASE,
    )
    return bool(imperative and len(clean.split()) >= 6)


def extract_prompt(value: str, *, source_kind: str = "manual_text") -> PromptCandidate | None:
    original = str(value or "").strip()
    clean = clean_prompt_text(original)
    if not looks_like_prompt(clean):
        return None
    prompt_type = classify_prompt_type(clean)
    tags = tags_for_text(clean)
    confidence = 0.95 if source_kind in {"manual_text", "caption_file"} else 0.75
    return PromptCandidate(
        prompt_type=prompt_type,
        prompt_text=clean,
        source_original_text=original[:20000],
        cleaned_prompt_text=clean,
        negative_prompt=_negative_prompt(original),
        language=_language(original),
        model_hint=_model_hint(original),
        ratio_hint=_ratio_hint(original),
        duration_hint=_duration_hint(original),
        style_tags=tags,
        scene_count=_scene_count(original),
        category=category_for_text(clean),
        use_case=next((tag for tag in tags if tag in {"product_ads", "affiliate", "course", "tutorial"}), ""),
        source_confidence=confidence,
    )


def extract_prompts(values: Iterable[str], *, source_kind: str = "manual_text") -> list[dict[str, Any]]:
    prompts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        candidate = extract_prompt(value, source_kind=source_kind)
        if not candidate:
            continue
        normalized = normalize_text(candidate.cleaned_prompt_text)
        if normalized in seen:
            continue
        seen.add(normalized)
        prompts.append(candidate.to_dict())
    return prompts
