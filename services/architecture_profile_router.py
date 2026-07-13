"""Deterministic Architecture Studio profile router.

This module has no provider, queue, job, outbox, pricing or wallet imports.
It only validates knowledge and creates a draft for an existing destination
wizard.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from services.architecture_prompt_builder import (
    EXTERIOR_PROJECT_TYPES,
    INTERIOR_SPACE_TYPES,
    RENOVATION_SCOPES,
    build_architecture_image_prompt,
    default_preservation,
)
from services.architecture_scene_planner import build_architecture_scene_plan
from services.architecture_video_prompt_builder import build_architecture_video_prompt


REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE_ROOT = REPO_ROOT / "knowledge" / "profiles"
REFERENCE_MANIFEST_PATH = REPO_ROOT / "knowledge" / "references" / "uploaded_video_reference_manifest.json"

ARCHITECTURE_PROFILE_IDS = (
    "architecture_exterior",
    "interior_design",
    "space_renovation",
    "real_estate_property",
    "architecture_walkthrough",
    "floorplan_visualization",
    "commercial_space",
    "landscape_garden",
)

ARCHITECTURE_PROFILE_MENU = (
    ("architecture_exterior", "🏛 Kiến trúc ngoại thất"),
    ("interior_design", "🛋 Thiết kế nội thất"),
    ("space_renovation", "🏠 Cải tạo không gian"),
    ("real_estate_property", "🏢 Bất động sản"),
    ("architecture_walkthrough", "🎬 Walkthrough kiến trúc"),
    ("floorplan_visualization", "🗺 Mặt bằng → phối cảnh"),
    ("commercial_space", "🏪 Cửa hàng / văn phòng"),
    ("landscape_garden", "🌿 Cảnh quan / sân vườn"),
    ("auto", "🧠 Tự động đề xuất"),
)

ARCH_REQUIRED_FIELDS = (
    "profile_id", "title_vi", "aliases", "intent_keywords", "suitable_outputs",
    "project_types", "space_types", "architectural_styles", "materials",
    "color_palettes", "lighting_presets", "camera_presets", "motion_presets",
    "preservation_rules", "clarifying_questions", "image_prompt_sections",
    "video_prompt_sections", "scene_templates", "negative_prompt",
    "safe_defaults", "source_reference_ids",
)

QUESTION_SCHEMAS: dict[str, tuple[tuple[str, str], ...]] = {
    "architecture_exterior": (
        ("project_type", "Anh/chị đang thiết kế loại công trình nào?"),
        ("floor_count", "Công trình có bao nhiêu tầng?"),
        ("facade_width", "Mặt tiền rộng khoảng bao nhiêu, nếu anh/chị đã biết?"),
        ("style", "Anh/chị muốn phong cách kiến trúc nào?"),
        ("palette", "Màu chủ đạo mong muốn là gì?"),
        ("materials", "Anh/chị muốn dùng vật liệu chính nào?"),
        ("lighting", "Anh/chị muốn bối cảnh ban ngày, hoàng hôn hay ban đêm?"),
        ("preserve_requirements", "Có cần giữ nguyên hình dáng hiện tại không?"),
    ),
    "interior_design": (
        ("space_type", "Anh/chị muốn thiết kế loại phòng hoặc không gian nào?"),
        ("dimensions", "Diện tích hoặc kích thước là bao nhiêu, nếu anh/chị đã biết?"),
        ("style", "Anh/chị muốn phong cách nội thất nào?"),
        ("palette", "Màu chủ đạo mong muốn là gì?"),
        ("materials", "Anh/chị muốn dùng vật liệu chính nào?"),
        ("preserved_furniture", "Có đồ vật nào cần giữ lại không?"),
        ("renovation_scope", "Anh/chị muốn thay đổi nhẹ hay thiết kế lại toàn diện?"),
        ("lighting", "Anh/chị muốn ánh sáng tự nhiên hay kiểu studio?"),
    ),
    "space_renovation": (
        ("space_type", "Anh/chị muốn cải tạo không gian nào?"),
        ("renovation_scope", "Phạm vi cải tạo mong muốn là gì?"),
        ("preserve_requirements", "Những phần nào bắt buộc phải giữ nguyên?"),
        ("style", "Phong cách mới mong muốn là gì?"),
        ("materials", "Anh/chị muốn thay đổi vật liệu nào?"),
    ),
    "real_estate_property": (
        ("project_type", "Đây là loại bất động sản nào?"),
        ("listing_goal", "Mục tiêu là đăng bán, cho thuê hay giới thiệu dự án?"),
        ("target_customer", "Đối tượng khách hàng chính là ai?"),
        ("requested_output", "Anh/chị cần ảnh hay video walkthrough?"),
        ("truth_mode", "Anh/chị muốn giữ hiện trạng tuyệt đối hay làm phối cảnh ý tưởng cải tạo?"),
        ("presentation_style", "Phong cách trình bày: trung thực, cao cấp hay lifestyle?"),
    ),
    "architecture_walkthrough": (
        ("start_point", "Video bắt đầu từ vị trí nào?"),
        ("room_order", "Camera cần đi qua các khu vực nào, theo thứ tự?"),
        ("camera_speed", "Anh/chị muốn camera đi chậm hay nhanh?"),
        ("duration", "Thời lượng walkthrough mong muốn là bao nhiêu giây?"),
        ("aspect_ratio", "Tỉ lệ khung hình mong muốn là gì?"),
        ("lighting", "Không gian ở ban ngày hay ban đêm?"),
        ("before_after", "Có cần chuyển cảnh trước/sau cải tạo không?"),
        ("preserve_camera", "Có cần giữ nguyên đường camera gốc không?"),
    ),
    "floorplan_visualization": (
        ("project_type", "Đây là mặt bằng của loại công trình nào?"),
        ("dimensions", "Mặt bằng đã có đơn vị và kích thước xác định chưa?"),
        ("priority_space", "Khu vực nào cần ưu tiên thể hiện?"),
        ("style", "Phong cách mong muốn là gì?"),
        ("requested_output", "Anh/chị cần ảnh top-down, phối cảnh hay walkthrough?"),
        ("layout_change_allowed", "Có được phép thay đổi bố trí không?"),
    ),
    "commercial_space": (
        ("project_type", "Anh/chị đang thiết kế cửa hàng, văn phòng hay loại hình kinh doanh nào?"),
        ("space_type", "Khu vực sử dụng chính là gì?"),
        ("target_customer", "Khách hàng hoặc người sử dụng chính là ai?"),
        ("style", "Phong cách thương hiệu mong muốn là gì?"),
        ("preserve_requirements", "Có cấu trúc hoặc nhận diện nào cần giữ lại không?"),
    ),
    "landscape_garden": (
        ("project_type", "Đây là sân vườn của nhà ở, resort hay công trình nào?"),
        ("space_type", "Khu vực cảnh quan cần thiết kế là gì?"),
        ("style", "Anh/chị muốn phong cách cảnh quan nào?"),
        ("materials", "Anh/chị muốn ưu tiên cây, đá, gỗ hay mặt nước nào?"),
        ("preserve_requirements", "Có cây hoặc cấu trúc nào bắt buộc phải giữ không?"),
    ),
}

PROFILE_SIGNALS: dict[str, tuple[str, ...]] = {
    "architecture_exterior": ("mặt tiền", "ngoại thất", "facade", "exterior", "elevation", "nhà phố", "biệt thự"),
    "interior_design": ("nội thất", "phòng khách", "phòng ngủ", "phòng bếp", "interior", "thiết kế phòng"),
    "space_renovation": ("cải tạo", "thiết kế lại", "biến phòng", "phòng trống", "before after", "renovation"),
    "real_estate_property": ("bất động sản", "đăng bán", "cho thuê", "listing", "property", "rao bán"),
    "architecture_walkthrough": ("walkthrough", "đi xuyên", "đi qua", "camera đi", "property tour", "video kiến trúc"),
    "floorplan_visualization": ("mặt bằng", "floor plan", "floorplan", "blueprint", "top down", "phối cảnh từ bản vẽ"),
    "commercial_space": ("cửa hàng", "showroom", "văn phòng", "quán cà phê", "nhà hàng", "spa", "commercial"),
    "landscape_garden": ("sân vườn", "cảnh quan", "landscape", "garden", "tiểu cảnh", "hồ cá"),
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _normalized(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _clean(value).lower().replace("đ", "d"))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def valid_reference_ids() -> set[str]:
    try:
        payload = json.loads(REFERENCE_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return set()
    return {
        _clean(item.get("reference_id"))
        for item in payload.get("references") or []
        if isinstance(item, dict) and _clean(item.get("reference_id"))
    }


def validate_architecture_profile(payload: Any, *, source: str = "") -> list[str]:
    if not isinstance(payload, dict):
        return [f"{source or 'profile'}:not_an_object"]
    errors: list[str] = []
    for field_name in ARCH_REQUIRED_FIELDS:
        if field_name not in payload:
            errors.append(f"{source}:{field_name}:missing")
        elif field_name != "safe_defaults" and payload.get(field_name) in (None, "", []):
            errors.append(f"{source}:{field_name}:empty")
    profile_id = _clean(payload.get("profile_id"))
    if profile_id not in ARCHITECTURE_PROFILE_IDS:
        errors.append(f"{source}:profile_id:unsupported")
    refs = valid_reference_ids()
    for reference_id in payload.get("source_reference_ids") or []:
        if _clean(reference_id) not in refs:
            errors.append(f"{source}:source_reference_ids:unknown:{reference_id}")
    defaults = payload.get("safe_defaults")
    if not isinstance(defaults, dict):
        errors.append(f"{source}:safe_defaults:must_be_object")
    return errors


def load_architecture_profiles(*, strict: bool = False) -> tuple[dict[str, dict[str, Any]], list[str]]:
    profiles: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    seen_payload_ids: set[str] = set()
    for profile_id in ARCHITECTURE_PROFILE_IDS:
        path = PROFILE_ROOT / f"{profile_id}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{path.name}:json_load_failed:{exc.__class__.__name__}")
            continue
        item_errors = validate_architecture_profile(payload, source=path.name)
        payload_id = _clean(payload.get("profile_id")) if isinstance(payload, dict) else ""
        if payload_id and payload_id != profile_id:
            item_errors.append(f"{path.name}:profile_id:filename_mismatch:{payload_id}")
        if payload_id in seen_payload_ids:
            item_errors.append(f"{path.name}:duplicate_profile_id:{payload_id}")
        if item_errors:
            errors.extend(item_errors)
            continue
        seen_payload_ids.add(payload_id)
        profiles[profile_id] = payload
    if strict and errors:
        raise ValueError(";".join(errors))
    return profiles, errors


def questions_for_profile(profile_id: str) -> tuple[tuple[str, str], ...]:
    return QUESTION_SCHEMAS.get(_clean(profile_id), QUESTION_SCHEMAS["interior_design"])


def next_missing_question(profile_id: str, answers: dict[str, Any]) -> dict[str, str]:
    for field_name, question in questions_for_profile(profile_id):
        value = answers.get(field_name)
        if value is None or value == "" or value == []:
            return {"field": field_name, "question": question}
    return {"field": "", "question": ""}


def _auto_profile(user_text: str) -> tuple[str, float, list[str]]:
    normalized = _normalized(user_text)
    strong_rules = (
        ("floorplan_visualization", ("mat bang", "floor plan", "floorplan", "blueprint")),
        ("architecture_walkthrough", ("walkthrough", "di xuyen", "camera di qua", "property tour", "tour can ho")),
        ("landscape_garden", ("san vuon", "canh quan", "landscape", "garden", "tieu canh")),
        ("commercial_space", ("cua hang", "showroom", "van phong", "quan ca phe", "nha hang", "spa", "salon")),
        ("space_renovation", ("cai tao", "bien phong", "phong trong", "before after")),
        ("real_estate_property", ("bat dong san", "dang ban", "cho thue", "property listing", "rao ban")),
        ("architecture_exterior", ("mat tien", "ngoai that", "facade", "exterior", "mat dung")),
        ("interior_design", ("noi that", "phong khach", "phong ngu", "phong bep", "interior")),
    )
    for profile_id, tokens in strong_rules:
        matches = [token for token in tokens if re.search(rf"(?:^| ){re.escape(token)}(?: |$)", normalized)]
        if matches:
            return profile_id, min(0.98, 0.72 + 0.08 * (len(matches) - 1)), matches
    scored: list[tuple[int, int, str, list[str]]] = []
    for order, profile_id in enumerate(ARCHITECTURE_PROFILE_IDS):
        signals = []
        score = 0
        for signal in PROFILE_SIGNALS[profile_id]:
            token = _normalized(signal)
            if token and re.search(rf"(?:^| ){re.escape(token)}(?: |$)", normalized):
                signals.append(signal)
                score += 3 + min(3, len(token.split()))
        scored.append((score, -order, profile_id, signals))
    scored.sort(reverse=True)
    top = scored[0]
    second = scored[1]
    if top[0] == 0 or top[0] == second[0]:
        return "interior_design", 0.25, []
    return top[2], min(0.98, 0.55 + top[0] / 30.0), top[3]


def _recommended_output(profile_id: str, requested_output: str, user_text: str) -> str:
    requested = _normalized(requested_output)
    normalized = _normalized(user_text)
    if profile_id == "architecture_walkthrough" or any(token in normalized for token in ("video", "walkthrough", "di xuyen", "tour")):
        return "video"
    if any(token in requested for token in ("video", "walkthrough", "tour", "reel")):
        return "video"
    if any(token in requested for token in ("image", "anh", "top down", "phoi canh")):
        return "image"
    return "image"


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        match = re.search(r"\d+", _clean(value))
        return int(match.group()) if match else int(default)


def _text_list(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple, set)) else [value]
    return [_clean(item) for item in values if _clean(item)]


def route_architecture_profile(payload: dict[str, Any]) -> dict[str, Any]:
    profiles, errors = load_architecture_profiles(strict=False)
    explicit = _clean(payload.get("explicit_profile"))
    user_text = _clean(payload.get("user_text"))
    if explicit in profiles:
        profile_id, confidence, signals = explicit, 1.0, [f"explicit:{explicit}"]
    else:
        profile_id, confidence, signals = _auto_profile(user_text)
    profile = profiles.get(profile_id) or profiles.get("interior_design") or {}
    output = _recommended_output(profile_id, _clean(payload.get("requested_output")), user_text)
    answers = {key: value for key, value in payload.items() if value not in (None, "", [])}
    next_question = next_missing_question(profile_id, answers)
    missing_fields = [field for field, _question in questions_for_profile(profile_id) if answers.get(field) in (None, "", [])]
    clarification = ""
    if confidence < 0.5:
        clarification = "Anh/chị muốn làm ngoại thất, nội thất, cải tạo, bất động sản, walkthrough, mặt bằng, không gian kinh doanh hay cảnh quan?"
    elif next_question:
        clarification = next_question["question"]
    preserve = _text_list(payload.get("preserve_requirements"))
    if not preserve:
        preserve = list(profile.get("safe_defaults", {}).get("preserve_requirements") or default_preservation(profile_id, bool(payload.get("reference_assets"))))
    merged = {
        **dict(profile.get("safe_defaults") or {}),
        **payload,
        "profile_id": profile_id,
        "requested_output": output,
        "preserve_requirements": preserve,
    }
    scene_payload = {
        **merged,
        "duration": _safe_int(payload.get("duration"), 40 if profile_id == "architecture_walkthrough" else 24),
        "scene_count": _safe_int(payload.get("scene_count"), 0),
    }
    scene_plan = build_architecture_scene_plan(scene_payload)
    image_package = build_architecture_image_prompt(merged)
    video_package = build_architecture_video_prompt({**merged, "scene_plan": scene_plan})
    if not image_package.get("ok") and not clarification:
        clarification = _clean(image_package.get("clarification_question"))
    real_estate_label = ""
    if profile_id == "real_estate_property":
        truth_mode = _normalized(payload.get("truth_mode"))
        real_estate_label = "Phối cảnh ý tưởng cải tạo" if any(token in truth_mode for token in ("y tuong", "cai tao", "concept")) else "Chỉnh ảnh hiện trạng"
    return {
        "profile_id": profile_id,
        "profile_title": _clean(profile.get("title_vi") or profile_id),
        "confidence": round(confidence, 3),
        "matched_signals": signals,
        "missing_fields": missing_fields,
        "next_question_field": next_question.get("field", ""),
        "clarification_question": clarification,
        "recommended_output": output,
        "preserve_constraints": preserve,
        "professional_image_prompt": _clean(image_package.get("prompt")),
        "professional_video_prompt": _clean(video_package.get("prompt")),
        "negative_prompt": _clean(video_package.get("negative_prompt") if output == "video" else image_package.get("negative_prompt")),
        "scene_plan": list(scene_plan.get("shots") or []),
        "scene_plan_summary": scene_plan,
        "safe_fallback_profile": "interior_design",
        "real_estate_truth_label": real_estate_label,
        "knowledge_valid": not errors and len(profiles) == len(ARCHITECTURE_PROFILE_IDS),
        "validation_errors": errors,
        "provider_called": False,
        "provider_task_created": False,
        "job_created": False,
        "outbox_created": False,
        "xu_charged": 0,
        "preview_price_xu": 0,
    }


def architecture_catalog_summary() -> dict[str, Any]:
    profiles, errors = load_architecture_profiles(strict=False)
    return {
        "ok": not errors and len(profiles) == len(ARCHITECTURE_PROFILE_IDS),
        "profile_count": len(profiles),
        "profile_ids": list(profiles),
        "errors": errors,
        "exterior_project_types": list(EXTERIOR_PROJECT_TYPES),
        "interior_space_types": list(INTERIOR_SPACE_TYPES),
        "renovation_scopes": list(RENOVATION_SCOPES),
    }
