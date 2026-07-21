"""Deterministic, provider-free routing for the Video Studio Profile menu."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
PROFILE_ROOT = KNOWLEDGE_ROOT / "profiles"
VIDEO_ROOT = KNOWLEDGE_ROOT / "video"
REFERENCE_MANIFEST_PATH = KNOWLEDGE_ROOT / "references" / "uploaded_video_reference_manifest.json"
CATALOG_PATH = KNOWLEDGE_ROOT / "catalog.json"

PROFILE_REQUIRED_FIELDS = (
    "profile_id",
    "title_vi",
    "aliases",
    "intent_keywords",
    "suitable_outputs",
    "subjects",
    "environments",
    "visual_styles",
    "materials",
    "lighting",
    "camera",
    "motion",
    "scene_templates",
    "negative_prompt",
    "clarifying_questions",
    "image_prompt_template",
    "video_prompt_template",
    "editing_recommendations",
    "source_reference_ids",
)

VIDEO_STORE_FILES = (
    "manual_editing.json",
    "ai_edit_vfx.json",
    "animation_motion_3d.json",
    "product_3d_visualization.json",
    "creator_ai_tools.json",
    "creator_productivity.json",
)

SAFE_FALLBACK_PROFILE_ID = "creator_tutorial_ugc"
ARCHITECTURE_STUDIO_ONLY_PROFILE_IDS = {
    "architecture_exterior", "interior_design", "space_renovation",
    "architecture_walkthrough", "floorplan_visualization",
    "commercial_space", "landscape_garden",
}

# Menu selection IDs are intentionally separate from canonical profile IDs.
# Several public choices share one production profile but keep their variant.
STUDIO_PROFILE_OPTIONS: tuple[dict[str, str], ...] = (
    {"selection_id": "architecture_exterior", "profile_id": "architecture_interior", "label_vi": "🏛 Kiến trúc ngoại thất", "variant": "ngoại thất"},
    {"selection_id": "architecture_interior", "profile_id": "architecture_interior", "label_vi": "🛋 Nội thất", "variant": "nội thất"},
    {"selection_id": "space_renovation", "profile_id": "architecture_interior", "label_vi": "🏠 Cải tạo không gian", "variant": "cải tạo không gian"},
    {"selection_id": "real_estate_property", "profile_id": "real_estate_property", "label_vi": "🏢 Bất động sản", "variant": "bất động sản"},
    {"selection_id": "architecture_walkthrough", "profile_id": "architecture_interior", "label_vi": "🎬 Walkthrough kiến trúc", "variant": "walkthrough kiến trúc"},
    {"selection_id": "cinematic_vfx", "profile_id": "cinematic_vfx", "label_vi": "✨ VFX điện ảnh", "variant": "VFX điện ảnh"},
    {"selection_id": "animation_2d_3d", "profile_id": "animation_character", "label_vi": "🧸 Hoạt hình 2D/3D", "variant": "hoạt hình 2D/3D"},
    {"selection_id": "character", "profile_id": "animation_character", "label_vi": "🧍 Nhân vật", "variant": "nhân vật"},
    {"selection_id": "fashion_lookbook", "profile_id": "fashion_virtual_model", "label_vi": "👗 Thời trang/lookbook", "variant": "thời trang/lookbook"},
    {"selection_id": "product_3d_showcase", "profile_id": "product_3d_showcase", "label_vi": "📦 Sản phẩm/3D showcase", "variant": "sản phẩm/3D showcase"},
    {"selection_id": "app_game_demo", "profile_id": "app_game_saas_demo", "label_vi": "🎮 App/game demo", "variant": "app/game demo"},
    {"selection_id": "website_saas_demo", "profile_id": "app_game_saas_demo", "label_vi": "💻 Website/SaaS demo", "variant": "website/SaaS demo"},
    {"selection_id": "tutorial_explainer", "profile_id": "creator_tutorial_ugc", "label_vi": "🎓 Tutorial/giải thích", "variant": "tutorial/giải thích"},
    {"selection_id": "ugc_social_creator", "profile_id": "creator_tutorial_ugc", "label_vi": "📱 UGC/social creator", "variant": "UGC/social creator"},
)


class KnowledgeValidationError(ValueError):
    pass


@dataclass
class ProfileRouteResult:
    selected_profile_id: str
    confidence: float
    matched_signals: list[str]
    missing_fields: list[str]
    clarification_question: str
    professional_prompt: str
    negative_prompt: str
    scene_plan: list[dict[str, Any]]
    editing_profile: dict[str, Any]
    safe_fallback_profile: str
    selected_variant: str = ""
    requested_output: str = "video"
    language: str = "vi"
    knowledge_valid: bool = True
    validation_errors: list[str] = field(default_factory=list)
    provider_called: bool = False
    job_created: bool = False
    outbox_created: bool = False
    xu_charged: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _normalized_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _clean_text(value).lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _profile_selection(value: str) -> dict[str, str]:
    key = _normalized_text(value).replace(" ", "_")
    for option in STUDIO_PROFILE_OPTIONS:
        if key in {
            _normalized_text(option["selection_id"]).replace(" ", "_"),
            _normalized_text(option["profile_id"]).replace(" ", "_"),
            _normalized_text(option["label_vi"]).replace(" ", "_"),
        }:
            return dict(option)
    return {}


def validate_profile_payload(payload: Any, *, source: str = "") -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return [f"{source or 'profile'}:not_an_object"]
    for field_name in PROFILE_REQUIRED_FIELDS:
        if field_name not in payload:
            errors.append(f"{source}:{field_name}:missing")
            continue
        value = payload.get(field_name)
        if field_name in {
            "aliases", "intent_keywords", "suitable_outputs", "subjects", "environments",
            "visual_styles", "materials", "lighting", "camera", "motion", "scene_templates",
            "negative_prompt", "clarifying_questions", "editing_recommendations", "source_reference_ids",
        } and not isinstance(value, list):
            errors.append(f"{source}:{field_name}:must_be_list")
        elif field_name not in {"scene_templates"} and value in (None, "", []):
            errors.append(f"{source}:{field_name}:empty")
    profile_id = _clean_text(payload.get("profile_id"))
    if profile_id and not re.fullmatch(r"[a-z0-9_]+", profile_id):
        errors.append(f"{source}:profile_id:invalid")
    for index, scene in enumerate(payload.get("scene_templates") or [], start=1):
        if not isinstance(scene, dict) or not all(_clean_text(scene.get(key)) for key in ("role", "title", "prompt")):
            errors.append(f"{source}:scene_templates:{index}:invalid")
    return errors


def load_profiles(*, strict: bool = False) -> tuple[dict[str, dict[str, Any]], list[str]]:
    profiles: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for path in sorted(PROFILE_ROOT.glob("*.json")):
        try:
            payload = _read_json(path)
        except Exception as exc:
            errors.append(f"{path.name}:json_load_failed:{exc.__class__.__name__}")
            continue
        item_errors = validate_profile_payload(payload, source=path.name)
        if item_errors:
            errors.extend(item_errors)
            continue
        profile_id = str(payload["profile_id"])
        if profile_id in profiles:
            errors.append(f"{path.name}:duplicate_profile_id:{profile_id}")
            continue
        profiles[profile_id] = payload
    if strict and errors:
        raise KnowledgeValidationError(";".join(errors))
    return profiles, errors


def validate_knowledge_catalog() -> dict[str, Any]:
    errors: list[str] = []
    profiles, profile_errors = load_profiles(strict=False)
    errors.extend(profile_errors)
    try:
        catalog = _read_json(CATALOG_PATH)
        if str(catalog.get("canonical_root") or "") != "knowledge":
            errors.append("catalog:canonical_root_invalid")
    except Exception as exc:
        catalog = {}
        errors.append(f"catalog:json_load_failed:{exc.__class__.__name__}")
    video_store_ids: set[str] = set()
    for file_name in VIDEO_STORE_FILES:
        path = VIDEO_ROOT / file_name
        try:
            payload = _read_json(path)
            store_id = _clean_text(payload.get("store_id"))
            if not store_id:
                errors.append(f"{file_name}:store_id_missing")
            video_store_ids.add(store_id)
        except Exception as exc:
            errors.append(f"{file_name}:json_load_failed:{exc.__class__.__name__}")
    try:
        manifest = _read_json(REFERENCE_MANIFEST_PATH)
        references = list(manifest.get("references") or [])
    except Exception as exc:
        manifest = {}
        references = []
        errors.append(f"manifest:json_load_failed:{exc.__class__.__name__}")
    reference_ids = [_clean_text(item.get("reference_id")) for item in references if isinstance(item, dict)]
    if len(reference_ids) != 18 or len(set(reference_ids)) != 18:
        errors.append(f"manifest:expected_18_unique_references:got_{len(reference_ids)}")
    for item in references:
        if not isinstance(item, dict) or not list(item.get("stores") or []):
            errors.append("manifest:reference_without_store")
            continue
        for store in item.get("stores") or []:
            store = str(store)
            if store.startswith("profile:") and store.split(":", 1)[1] not in profiles:
                errors.append(f"manifest:unknown_{store}")
            elif not store.startswith("profile:") and store not in video_store_ids:
                errors.append(f"manifest:unknown_store:{store}")
    return {
        "ok": not errors,
        "errors": errors,
        "profile_count": len(profiles),
        "video_store_count": len(video_store_ids),
        "reference_count": len(reference_ids),
        "catalog": catalog,
    }


KNOWLEDGE_VALIDATION = validate_knowledge_catalog()


def _fallback_profile(profiles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if SAFE_FALLBACK_PROFILE_ID in profiles:
        return profiles[SAFE_FALLBACK_PROFILE_ID]
    if profiles:
        return profiles[sorted(profiles)[0]]
    return {
        "profile_id": SAFE_FALLBACK_PROFILE_ID,
        "title_vi": "Studio Profile AI",
        "aliases": [],
        "intent_keywords": [],
        "suitable_outputs": ["image", "video", "edit"],
        "scene_templates": [{"role": "plan", "title": "Kế hoạch", "prompt": "Giữ đúng yêu cầu khách hàng."}],
        "negative_prompt": ["invented facts", "invented branding"],
        "clarifying_questions": ["Anh/chị muốn tạo nội dung về chủ thể nào và kết quả mong muốn là gì?"],
        "image_prompt_template": "Create an original image plan for: {user_request}.",
        "video_prompt_template": "Create an original video plan for: {user_request}.",
        "editing_recommendations": ["preserve customer constraints"],
    }


def _score_profile(profile: dict[str, Any], normalized: str, requested_output: str, uploaded_asset_type: str) -> tuple[int, list[str]]:
    if str(profile.get("profile_id") or "") in ARCHITECTURE_STUDIO_ONLY_PROFILE_IDS:
        return -1, []
    score = 0
    signals: list[str] = []
    for alias in profile.get("aliases") or []:
        token = _normalized_text(alias)
        if token and re.search(rf"(?:^| )({re.escape(token)})(?: |$)", normalized):
            weight = 10 + min(4, len(token.split()))
            score += weight
            signals.append(f"alias:{alias}")
    for keyword in profile.get("intent_keywords") or []:
        token = _normalized_text(keyword)
        if token and re.search(rf"(?:^| )({re.escape(token)})(?: |$)", normalized):
            score += 3
            signals.append(f"intent:{keyword}")
    if requested_output and requested_output in set(profile.get("suitable_outputs") or []):
        score += 1
        signals.append(f"output:{requested_output}")
    asset = _normalized_text(uploaded_asset_type)
    if asset:
        if "3d" in asset and profile.get("profile_id") == "product_3d_showcase":
            score += 6
            signals.append("asset:3d")
        elif "screen" in asset and profile.get("profile_id") == "app_game_saas_demo":
            score += 6
            signals.append("asset:screen")
        elif "footage" in asset and profile.get("profile_id") == "cinematic_vfx":
            score += 3
            signals.append("asset:footage")
    return score, signals


def _render_template(template: str, values: dict[str, Any]) -> str:
    rendered = str(template or "")
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return _clean_text(rendered)


def _build_scene_plan(profile: dict[str, Any], scene_count: int, duration: int) -> list[dict[str, Any]]:
    templates = [dict(item) for item in profile.get("scene_templates") or [] if isinstance(item, dict)]
    if not templates:
        templates = [{"role": "plan", "title": "Kế hoạch", "prompt": "Giữ đúng yêu cầu khách hàng."}]
    count = max(1, min(20, int(scene_count or 1)))
    total_duration = max(1, int(duration or count * 8))
    base = total_duration // count
    remainder = total_duration % count
    plan: list[dict[str, Any]] = []
    for index in range(count):
        template = templates[index] if index < len(templates) else templates[-1]
        plan.append(
            {
                "scene_index": index + 1,
                "role": _clean_text(template.get("role") or "continuation"),
                "title": _clean_text(template.get("title") or f"Cảnh {index + 1}"),
                "prompt": _clean_text(template.get("prompt") or "Giữ continuity với cảnh trước."),
                "duration_seconds": base + (1 if index < remainder else 0),
                "continuity": "Giữ nguyên chủ thể, màu, vật liệu và các ràng buộc khách đã nêu.",
            }
        )
    return plan


def route_profile(
    user_text: str,
    *,
    selected_profile: str = "",
    requested_output: str = "video",
    uploaded_asset_type: str = "",
    language: str = "vi",
    aspect_ratio: str = "9:16",
    duration: int = 0,
    scene_count: int = 3,
) -> ProfileRouteResult:
    profiles, load_errors = load_profiles(strict=False)
    validation = validate_knowledge_catalog()
    errors = list(dict.fromkeys(load_errors + list(validation.get("errors") or [])))
    fallback = _fallback_profile(profiles)
    explicit = _profile_selection(selected_profile)
    normalized = _normalized_text(user_text)
    matched_signals: list[str] = []
    selected_variant = str(explicit.get("variant") or "")
    ambiguous = False

    if explicit and explicit.get("profile_id") in profiles:
        selected = profiles[str(explicit["profile_id"])]
        confidence = 1.0
        matched_signals = [f"explicit:{explicit['selection_id']}"]
    else:
        scored: list[tuple[int, str, list[str]]] = []
        for profile_id, profile in profiles.items():
            score, signals = _score_profile(profile, normalized, requested_output, uploaded_asset_type)
            scored.append((score, profile_id, signals))
        scored.sort(key=lambda item: (-item[0], item[1]))
        top_score, top_id, top_signals = scored[0] if scored else (0, str(fallback.get("profile_id") or SAFE_FALLBACK_PROFILE_ID), [])
        second_score = scored[1][0] if len(scored) > 1 else 0
        ambiguous = bool(top_score < 6 or (top_score == second_score and top_score > 0))
        selected = profiles.get(top_id) or fallback
        confidence = 0.25 if ambiguous else min(0.98, 0.55 + (top_score / 40.0))
        matched_signals = top_signals

    scene_count_value = max(1, min(20, int(scene_count or 3)))
    duration_value = max(1, int(duration or scene_count_value * 8))
    output = requested_output if requested_output in {"image", "video", "edit"} else "video"
    missing_fields: list[str] = []
    if not _clean_text(user_text):
        missing_fields.append("user_text")
    if not _clean_text(uploaded_asset_type):
        missing_fields.append("uploaded_asset_type")
    if not _clean_text(aspect_ratio):
        missing_fields.append("aspect_ratio")
    question = ""
    questions = [_clean_text(item) for item in selected.get("clarifying_questions") or [] if _clean_text(item)]
    if ambiguous or not _clean_text(user_text):
        question = questions[0] if questions else "Anh/chị muốn tạo nội dung về chủ thể nào và kết quả mong muốn là gì?"

    values = {
        "user_request": _clean_text(user_text) or "chưa có mô tả; cần hỏi lại khách hàng",
        "scene_count": scene_count_value,
        "aspect_ratio": _clean_text(aspect_ratio) or "chưa chọn",
        "duration_seconds": duration_value,
    }
    template = selected.get("image_prompt_template") if output == "image" else selected.get("video_prompt_template")
    professional_prompt = _render_template(str(template or ""), values)
    professional_prompt = _clean_text(
        f"{professional_prompt} Customer constraints (preserve verbatim): {_clean_text(user_text) or 'not supplied'}. "
        "Do not invent addresses, dimensions, prices, branded products, people, colors, materials or features."
    )
    scene_plan = _build_scene_plan(selected, scene_count_value, duration_value)
    negative_prompt = ", ".join(dict.fromkeys(_clean_text(item) for item in selected.get("negative_prompt") or [] if _clean_text(item)))
    editing_profile = {
        "profile_id": str(selected.get("profile_id") or fallback.get("profile_id") or SAFE_FALLBACK_PROFILE_ID),
        "recommendations": list(selected.get("editing_recommendations") or []),
        "camera": list(selected.get("camera") or []),
        "motion": list(selected.get("motion") or []),
        "lighting": list(selected.get("lighting") or []),
        "aspect_ratio": _clean_text(aspect_ratio) or "9:16",
        "duration_seconds": duration_value,
        "scene_count": scene_count_value,
    }
    return ProfileRouteResult(
        selected_profile_id=str(selected.get("profile_id") or SAFE_FALLBACK_PROFILE_ID),
        confidence=round(confidence, 3),
        matched_signals=matched_signals,
        missing_fields=missing_fields,
        clarification_question=question,
        professional_prompt=professional_prompt,
        negative_prompt=negative_prompt,
        scene_plan=scene_plan,
        editing_profile=editing_profile,
        safe_fallback_profile=str(fallback.get("profile_id") or SAFE_FALLBACK_PROFILE_ID),
        selected_variant=selected_variant,
        requested_output=output,
        language=_clean_text(language) or "vi",
        knowledge_valid=bool(validation.get("ok")),
        validation_errors=errors,
        provider_called=False,
        job_created=False,
        outbox_created=False,
        xu_charged=0,
    )


def profile_for_selection(selection_id: str) -> dict[str, Any]:
    profiles, _ = load_profiles(strict=False)
    selection = _profile_selection(selection_id)
    profile = profiles.get(str(selection.get("profile_id") or "")) or _fallback_profile(profiles)
    return {**profile, "selection_id": str(selection.get("selection_id") or ""), "variant": str(selection.get("variant") or "")}
