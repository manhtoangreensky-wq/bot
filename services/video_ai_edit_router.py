"""Provider-free intent and profile routing for AI Video Editing."""

from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from typing import Any

from services import profile_router


DEFAULT_PRESERVE_CONTROLS = {
    "preserve_identity": True,
    "preserve_subject": True,
    "preserve_outfit": True,
    "preserve_product_logo": True,
    "preserve_composition": True,
    "preserve_architecture": True,
    "preserve_original_motion": True,
    "preserve_source_audio": True,
    "replace_background": False,
    "allow_full_scene_transformation": False,
}

INTENSITY_LEVELS = ("light", "medium", "strong", "creative")
INTENSITY_LABELS = {
    "light": "Nhẹ",
    "medium": "Vừa",
    "strong": "Mạnh",
    "creative": "Biến đổi sáng tạo",
}


def _profile(
    profile_id: str,
    title_vi: str,
    keywords: tuple[str, ...],
    suitable_footage: tuple[str, ...],
    visual_objective: str,
    effect_stack: tuple[str, ...],
    lighting: str,
    color: str,
    camera_motion: str,
    transitions: str,
    preserve_rules: tuple[str, ...],
    local_fallback: tuple[str, ...],
    *,
    capability: str = "video_to_video",
    canonical_profile: str = "cinematic_vfx",
    generative: bool = True,
) -> dict[str, Any]:
    return {
        "profile_id": profile_id,
        "title_vi": title_vi,
        "keywords": list(keywords),
        "suitable_footage": list(suitable_footage),
        "visual_objective": visual_objective,
        "effect_stack": list(effect_stack),
        "lighting_treatment": lighting,
        "color_treatment": color,
        "camera_motion_treatment": camera_motion,
        "transition_behavior": transitions,
        "preserve_rules": list(preserve_rules),
        "negative_prompt": [
            "identity drift", "face deformation", "extra fingers or limbs",
            "warped product", "corrupted logo", "architectural geometry changes",
            "camera jitter", "duplicated objects", "flicker", "inconsistent lighting",
            "text artifacts", "low resolution", "overexposure", "frame interpolation errors",
        ],
        "provider_capability_required": capability,
        "local_fallback_options": list(local_fallback),
        "clarification_questions": [
            "Chủ thể nào phải được giữ nguyên tuyệt đối?",
            "Anh/chị muốn thay đổi nhẹ hay biến đổi sáng tạo rõ rệt?",
        ],
        "canonical_profile_id": canonical_profile,
        "generative_required": bool(generative),
    }


AI_EDIT_PROFILES: tuple[dict[str, Any], ...] = (
    _profile("cinematic_professional", "🎬 Điện ảnh chuyên nghiệp", ("cinematic", "điện ảnh", "phim"), ("person", "landscape", "room", "vehicle"), "Hình ảnh điện ảnh tự nhiên, có chiều sâu và nhịp dựng chuyên nghiệp.", ("cinematic_grade", "soft_depth", "subtle_motion"), "Ánh sáng điện ảnh cân bằng, giữ da và vùng sáng.", "Tương phản có kiểm soát, màu phim tự nhiên.", "Ổn định chuyển động, chuyển động máy tinh tế.", "Chuyển cảnh mềm, không phô trương.", ("identity", "subject", "source_motion"), ("light_cinematic", "stabilize", "denoise")),
    _profile("fantasy_energy", "✨ Fantasy / năng lượng / phép thuật", ("fantasy", "năng lượng", "phép thuật", "magic", "vfx"), ("person", "character", "landscape"), "Hiệu ứng năng lượng có kiểm soát quanh hành động, không làm biến dạng chủ thể.", ("energy_trails", "particles", "volumetric_light"), "Ánh sáng viền và thể tích theo nguồn hiệu ứng.", "Màu giàu tương phản nhưng không cháy sáng.", "Theo chuyển động gốc, không rung giật.", "Hiệu ứng nối tiếp theo hành động.", ("identity", "body", "outfit"), ("glow", "light_leak", "color_grade")),
    _profile("cyberpunk_neon", "🌃 Cyberpunk / neon", ("cyberpunk", "neon", "tương lai", "đô thị"), ("person", "vehicle", "city", "product"), "Không khí neon tương lai với phản xạ và chiều sâu có kiểm soát.", ("neon_rim", "city_reflection", "digital_accents"), "Viền neon tách chủ thể khỏi nền.", "Teal-magenta cân bằng, giữ tông da.", "Chuyển động mượt, parallax nhẹ.", "Glitch ngắn tại điểm chuyển.", ("identity", "product", "logo"), ("cool_grade", "glow", "glitch")),
    _profile("animation_cartoon", "🧸 Hoạt hình / anime / cartoon", ("anime", "cartoon", "hoạt hình", "animation"), ("person", "character", "pet", "object"), "Chuyển phong cách minh họa nhất quán theo toàn clip.", ("stylized_lines", "toon_shading", "controlled_motion"), "Ánh sáng đơn giản, nhất quán theo phong cách.", "Bảng màu rõ, không nhấp nháy.", "Giữ timing và cử động gốc.", "Chuyển cảnh theo nét/vệt chuyển động.", ("identity", "silhouette", "motion"), ("saturation", "edge_emphasis"), canonical_profile="animation_character"),
    _profile("action_impact", "💥 Action / speed ramp / impact", ("action", "tốc độ", "speed ramp", "impact", "thể thao"), ("person", "vehicle", "sport", "game"), "Nhịp nhanh, lực tác động rõ và vẫn đọc được hành động.", ("speed_ramp", "impact_flash", "motion_blur"), "Tăng tương phản tại điểm hành động.", "Màu mạnh, giữ chi tiết vùng tối.", "Speed ramp và zoom có chủ đích.", "Cut theo nhịp hành động.", ("identity", "action_path", "source_audio"), ("speed_ramp", "contrast", "motion_blur")),
    _profile("product_commercial", "📦 Quảng cáo sản phẩm", ("sản phẩm", "product", "quảng cáo", "commercial", "logo"), ("product", "food", "vehicle", "object"), "Trình bày sản phẩm cao cấp, nhãn và hình dáng chính xác.", ("premium_light", "product_focus", "clean_reflection"), "Ánh sáng studio sạch, không đổi màu sản phẩm.", "Màu thương mại chính xác.", "Orbit/push-in nhẹ, không làm méo sản phẩm.", "Chuyển cảnh sạch theo chi tiết sản phẩm.", ("product_shape", "label", "logo", "brand_colors"), ("sharpen", "denoise", "premium_grade"), canonical_profile="product_3d_showcase"),
    _profile("fashion_lookbook", "👗 Thời trang / lookbook", ("fashion", "thời trang", "lookbook", "outfit"), ("person", "fashion", "runway"), "Lookbook thời trang hiện đại, giữ khuôn mặt và trang phục.", ("fabric_detail", "beauty_light", "editorial_motion"), "Ánh sáng beauty mềm, giữ chất liệu vải.", "Màu editorial, tông da thật.", "Chuyển động máy thanh lịch, nhịp vừa.", "Match cut theo dáng/chuyển động.", ("identity", "outfit", "fabric", "body_proportion"), ("soft_clean", "stabilize", "editorial_grade"), canonical_profile="fashion_virtual_model"),
    _profile("architecture_interior", "🏛 Kiến trúc / nội thất", ("kiến trúc", "nội thất", "architecture", "interior", "room"), ("room", "building", "architecture"), "Nâng cấp thẩm mỹ không gian nhưng giữ tuyệt đối hình học kiến trúc.", ("material_response", "window_balance", "walkthrough_stabilize"), "Ánh sáng tự nhiên cân bằng, không tạo cửa giả.", "Màu vật liệu trung thực.", "Giữ nguyên camera path và phối cảnh.", "Chuyển cảnh không làm đổi cấu trúc phòng.", ("wall_openings", "windows", "room_dimensions", "camera_path"), ("stabilize", "warm_grade", "exposure_balance"), canonical_profile="architecture_interior"),
    _profile("real_estate_cinematic", "🏢 Bất động sản cinematic", ("bất động sản", "real estate", "property", "căn hộ"), ("room", "building", "property"), "Walkthrough bất động sản sáng rõ, sang trọng và trung thực.", ("real_estate_grade", "smooth_walkthrough", "detail_recovery"), "Cân bằng trong/ngoài cửa sổ.", "Màu sạch, vật liệu thật.", "Ổn định walkthrough, không đổi layout.", "Dissolve nhẹ giữa không gian.", ("geometry", "layout", "fixtures", "camera_path"), ("stabilize", "exposure_balance", "sharpen"), canonical_profile="real_estate_property"),
    _profile("scifi_futuristic", "🌌 Sci-fi / futuristic", ("sci-fi", "futuristic", "tương lai", "space"), ("person", "vehicle", "product", "city"), "Không khí khoa học viễn tưởng rõ nét, hiệu ứng bám đúng cảnh.", ("hologram", "futuristic_ui", "atmosphere"), "Ánh sáng môi trường tương lai có logic.", "Tông lạnh hiện đại, giữ chi tiết chủ thể.", "Camera trôi mượt, hiệu ứng bám chuyển động.", "Chuyển cảnh hologram có kiểm soát.", ("identity", "product", "scene_continuity"), ("cool_grade", "glow", "light_leak")),
    _profile("artistic_surreal", "🎨 Artistic / surreal", ("artistic", "surreal", "nghệ thuật", "trừu tượng"), ("person", "landscape", "object"), "Biến đổi nghệ thuật có chủ đích nhưng giữ chủ thể đọc được.", ("surreal_texture", "dream_motion", "color_expression"), "Ánh sáng biểu cảm nhất quán.", "Màu nghệ thuật có kiểm soát.", "Chuyển động mơ màng, không rung.", "Morph nhẹ giữa các lớp hình.", ("identity", "main_subject", "motion"), ("color_grade", "glow", "vignette")),
    _profile("ugc_social", "📱 UGC / social nổi bật", ("ugc", "social", "tiktok", "reels", "shorts"), ("talking_head", "person", "product"), "Video mạng xã hội rõ chủ thể, nhịp nhanh và dễ xem.", ("dynamic_crop", "punch_zoom", "text_emphasis"), "Da sáng tự nhiên, nền rõ vừa đủ.", "Màu nổi nhưng không lệch da/sản phẩm.", "Crop động và zoom nhẹ theo điểm nhấn.", "Cut nhanh theo câu/nhịp.", ("identity", "product", "source_audio"), ("dynamic_crop", "high_contrast", "sharpen"), canonical_profile="creator_tutorial_ugc", generative=False),
    _profile("talking_head_pro", "🎓 Talking-head chuyên nghiệp", ("talking head", "giải thích", "tutorial", "phỏng vấn"), ("talking_head", "person"), "Hình ảnh người nói sạch, ổn định và chuyên nghiệp.", ("skin_tone_clean", "background_balance", "subtle_push"), "Ánh sáng mặt mềm, không thay khuôn mặt.", "Tông da chính xác, tương phản vừa.", "Ổn định và push-in rất nhẹ.", "Cut kín, không gây giật.", ("identity", "face", "lip_motion", "source_audio"), ("denoise", "soft_clean", "stabilize"), canonical_profile="creator_tutorial_ugc", generative=False),
    _profile("app_saas_demo", "🖥 App / website / SaaS demo", ("app", "website", "saas", "screen", "demo"), ("screen_recording", "device", "interface"), "Demo giao diện rõ ràng, dễ theo dõi và không làm sai nội dung màn hình.", ("focus_zoom", "pointer_emphasis", "clean_frame"), "Nền trung tính, màn hình dễ đọc.", "Màu giao diện giữ nguyên.", "Pan/zoom theo vùng thao tác.", "Chuyển cảnh theo bước thao tác.", ("ui_text", "layout", "brand", "timing"), ("crop", "zoom_pan", "sharpen"), canonical_profile="app_game_saas_demo", generative=False),
    _profile("game_trailer", "🎮 Game / trailer", ("game", "trailer", "gaming", "gameplay"), ("gameplay", "screen_recording", "character"), "Trailer game có nhịp, giữ hình ảnh gameplay và UI quan trọng.", ("impact_cut", "cinematic_grade", "controlled_glitch"), "Nhấn sáng tại cao trào.", "Màu đậm, giữ chi tiết gameplay.", "Speed ramp/crop theo hành động.", "Cut theo nhịp, không che UI.", ("gameplay", "ui", "character", "logo"), ("contrast", "speed_ramp", "glitch"), canonical_profile="app_game_saas_demo"),
    _profile("visualizer_lofi", "🎧 Visualizer / chill / lofi", ("visualizer", "lofi", "chill", "ambient"), ("landscape", "artwork", "object"), "Chuyển động chậm, lặp mượt và không tự thêm nhạc bản quyền.", ("slow_zoom", "ambient_particles", "soft_loop"), "Ánh sáng dịu, nhịp thở nhẹ.", "Màu êm, tương phản thấp vừa.", "Pan/zoom chậm, không rung.", "Dissolve dài, lặp kín.", ("main_subject", "source_audio"), ("slow_zoom", "soft_grade", "vignette"), generative=False),
    _profile("clean_enhance", "🧼 Làm sạch và nâng cấp hình ảnh", ("làm sạch", "nâng nét", "denoise", "clean", "enhance"), ("person", "product", "room", "landscape", "screen_recording"), "Làm video rõ và sạch hơn mà không thay nội dung.", ("denoise", "sharpen", "exposure_balance", "audio_normalize"), "Cân bằng sáng, không tạo ánh sáng giả.", "Giữ màu nguồn, sửa lệch nhẹ.", "Ổn định nếu cần, giữ chuyển động gốc.", "Giữ nguyên cut gốc.", ("all_source_content", "identity", "geometry", "audio"), ("denoise", "sharpen", "audio_normalize"), capability="local_ffmpeg", canonical_profile="creator_tutorial_ugc", generative=False),
    _profile("auto_recommend", "🧠 Tự động đề xuất", ("tự động", "đề xuất", "auto", "không biết"), ("person", "product", "room", "landscape", "screen_recording"), "Chọn hướng an toàn nhất dựa trên mô tả và metadata nguồn.", ("safe_recommendation",), "Theo profile được chọn.", "Theo profile được chọn.", "Theo profile được chọn.", "Theo profile được chọn.", ("identity", "subject", "product", "geometry"), ("denoise", "color_grade", "stabilize"), capability="local_or_video_to_video", canonical_profile="creator_tutorial_ugc", generative=False),
)

PROFILE_BY_ID = {item["profile_id"]: item for item in AI_EDIT_PROFILES}

PROFILE_PRIORITY_BY_FOOTAGE = {
    "talking_head": ("talking_head_pro", "ugc_social", "cinematic_professional", "cyberpunk_neon", "fantasy_energy"),
    "person": ("talking_head_pro", "ugc_social", "cinematic_professional", "fashion_lookbook", "fantasy_energy"),
    "product": ("product_commercial", "cinematic_professional", "cyberpunk_neon", "clean_enhance", "scifi_futuristic"),
    "fashion": ("fashion_lookbook", "cinematic_professional", "ugc_social", "cyberpunk_neon", "artistic_surreal"),
    "room": ("architecture_interior", "real_estate_cinematic", "cinematic_professional", "clean_enhance", "artistic_surreal"),
    "architecture": ("architecture_interior", "real_estate_cinematic", "cinematic_professional", "clean_enhance", "scifi_futuristic"),
    "screen_recording": ("app_saas_demo", "ugc_social", "game_trailer", "clean_enhance", "cinematic_professional"),
    "animation": ("animation_cartoon", "game_trailer", "fantasy_energy", "artistic_surreal", "cinematic_professional"),
}


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def profile_option(profile_id: str) -> dict[str, Any]:
    return deepcopy(PROFILE_BY_ID.get(str(profile_id or ""), {}))


def public_profile_options() -> list[dict[str, str]]:
    return [{"profile_id": item["profile_id"], "title_vi": item["title_vi"]} for item in AI_EDIT_PROFILES]


def _footage_type(user_request: str, uploaded_asset_type: str, metadata: dict[str, Any]) -> str:
    text = normalize_text(" ".join((user_request, uploaded_asset_type, str(metadata.get("content_hint") or ""))))
    rules = (
        ("architecture", ("kien truc", "ngoai that", "building")),
        ("room", ("noi that", "room", "phong", "can ho", "real estate", "bat dong san")),
        ("product", ("san pham", "product", "logo", "quang cao", "food", "xe")),
        ("fashion", ("thoi trang", "fashion", "lookbook", "outfit")),
        ("screen_recording", ("screen", "website", "saas", "app", "gameplay", "giao dien")),
        ("talking_head", ("talking", "noi truoc camera", "phong van", "tutorial", "nguoi noi")),
        ("animation", ("anime", "cartoon", "hoat hinh")),
        ("vehicle", ("vehicle", "oto", "xe may", "car")),
        ("landscape", ("landscape", "phong canh", "travel", "du lich")),
    )
    for result, tokens in rules:
        if any(token in text for token in tokens):
            return result
    if metadata.get("orientation") == "portrait" or int(metadata.get("height") or 0) > int(metadata.get("width") or 0):
        return "person"
    return str(uploaded_asset_type or "ordinary_video").strip() or "ordinary_video"


def _score(profile: dict[str, Any], text: str, footage_type: str) -> tuple[int, list[str]]:
    score = 0
    signals: list[str] = []
    for token in profile.get("keywords") or []:
        normalized = normalize_text(token)
        if normalized and normalized in text:
            score += 8
            signals.append(f"intent:{token}")
    for token in profile.get("suitable_footage") or []:
        if normalize_text(token) == normalize_text(footage_type):
            score += 6
            signals.append(f"footage:{token}")
    if profile["profile_id"] == "clean_enhance":
        score += 1
    return score, signals


def suggestion_for_profile(profile: dict[str, Any], intensity: str = "medium") -> dict[str, Any]:
    preserved = list(profile.get("preserve_rules") or [])
    return {
        "profile_id": profile["profile_id"],
        "title": profile["title_vi"],
        "result": profile["visual_objective"],
        "estimated_intensity": INTENSITY_LABELS.get(intensity, INTENSITY_LABELS["medium"]),
        "preserve_summary": ", ".join(preserved[:4]),
        "requires_generative": bool(profile.get("generative_required")),
        "local_fallback_available": bool(profile.get("local_fallback_options")),
        "local_fallback_options": list(profile.get("local_fallback_options") or []),
    }


def suggestions_for_footage(footage_type: str, user_request: str = "", limit: int = 5) -> list[dict[str, Any]]:
    text = normalize_text(user_request)
    scored = []
    for profile in AI_EDIT_PROFILES:
        if profile["profile_id"] == "auto_recommend":
            continue
        score, _signals = _score(profile, text, footage_type)
        scored.append((score, profile["profile_id"], profile))
    priority = {
        profile_id: index
        for index, profile_id in enumerate(PROFILE_PRIORITY_BY_FOOTAGE.get(footage_type, PROFILE_PRIORITY_BY_FOOTAGE["person"]))
    }
    scored.sort(key=lambda item: (-item[0], priority.get(item[1], 100), item[1]))
    selected = [suggestion_for_profile(item[2]) for item in scored[: max(3, min(5, int(limit or 5)))]]
    return selected


def effect_stack_for(profile: dict[str, Any], intensity: str) -> list[str]:
    stack = list(profile.get("effect_stack") or [])
    if intensity == "light":
        return stack[: max(1, min(2, len(stack)))]
    if intensity == "strong":
        return stack + ["strong_but_controlled"]
    if intensity == "creative":
        return stack + ["creative_scene_transformation"]
    return stack


def local_preprocess_plan(profile: dict[str, Any], intensity: str, aspect_ratio: str, preserve_audio: bool) -> dict[str, Any]:
    fallbacks = set(profile.get("local_fallback_options") or [])
    color_map = {
        "light_cinematic": "light_cinematic",
        "premium_grade": "light_cinematic",
        "editorial_grade": "warm",
        "warm_grade": "warm",
        "cool_grade": "cool",
        "soft_clean": "keep",
        "high_contrast": "high_contrast",
    }
    color = next((color_map[item] for item in fallbacks if item in color_map), "bright_clear" if "sharpen" in fallbacks else "keep")
    plan = {
        "crop_or_fit": {"aspect_ratio": aspect_ratio or "keep", "mode": "fit"},
        "color_preset": color,
        "sharpen": "sharpen" in fallbacks or profile.get("profile_id") == "clean_enhance",
        "denoise": "denoise" in fallbacks,
        "stabilize": "stabilize" in fallbacks,
        "audio_normalize": bool(preserve_audio and "audio_normalize" in fallbacks),
        "intensity": intensity,
    }
    return plan


def route_ai_edit_intent(
    user_request: str,
    *,
    selected_profile: str = "",
    source_metadata: dict[str, Any] | None = None,
    uploaded_asset_type: str = "",
    preserve_controls: dict[str, Any] | None = None,
    intensity: str = "medium",
    target_aspect_ratio: str = "",
    target_duration_seconds: int = 0,
) -> dict[str, Any]:
    metadata = dict(source_metadata or {})
    intensity_value = intensity if intensity in INTENSITY_LEVELS else "medium"
    preserve = dict(DEFAULT_PRESERVE_CONTROLS)
    preserve.update({key: bool(value) for key, value in dict(preserve_controls or {}).items() if key in preserve})
    footage_type = _footage_type(user_request, uploaded_asset_type, metadata)
    text = normalize_text(user_request)
    explicit = profile_option(selected_profile)
    matched_signals: list[str] = []
    if explicit:
        chosen = explicit
        confidence = 1.0
        matched_signals = [f"explicit:{selected_profile}"]
    else:
        scored = []
        for profile in AI_EDIT_PROFILES:
            score, signals = _score(profile, text, footage_type)
            scored.append((score, profile["profile_id"], signals, profile))
        priority = {
            profile_id: index
            for index, profile_id in enumerate(PROFILE_PRIORITY_BY_FOOTAGE.get(footage_type, ()))
        }
        scored.sort(key=lambda item: (-item[0], priority.get(item[1], 100), item[1]))
        top = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else -1
        recognized_footage = footage_type in PROFILE_PRIORITY_BY_FOOTAGE
        ambiguous = top[0] < 6 or (top[0] == second_score and not recognized_footage)
        chosen = profile_option("auto_recommend") if ambiguous else deepcopy(top[3])
        confidence = 0.35 if ambiguous else min(0.98, 0.58 + top[0] / 40.0)
        matched_signals = list(top[2])
    missing_fields: list[str] = []
    if not str(user_request or "").strip():
        missing_fields.append("user_request")
    if chosen.get("profile_id") == "auto_recommend" or confidence < 0.5:
        missing_fields.append("selected_profile")
    clarification = ""
    if missing_fields:
        clarification = "Anh/chị muốn giữ nguyên chủ thể nào và muốn video nổi bật theo phong cách nào?"
    duration = int(target_duration_seconds or round(float(metadata.get("duration") or 0)) or 0)
    aspect = str(target_aspect_ratio or "").strip()
    if not aspect:
        width, height = int(metadata.get("width") or 0), int(metadata.get("height") or 0)
        aspect = "9:16" if height > width else "16:9" if width > height else "1:1"
    canonical = profile_router.route_profile(
        user_request,
        selected_profile=str(chosen.get("canonical_profile_id") or ""),
        requested_output="edit",
        uploaded_asset_type=footage_type,
        aspect_ratio=aspect,
        duration=max(1, duration or 8),
        scene_count=1,
    )
    constraints = [key for key, enabled in preserve.items() if enabled and key.startswith("preserve_")]
    if preserve.get("replace_background"):
        constraints.append("replace_background_explicit")
    return {
        "profile_id": chosen["profile_id"],
        "profile_title": chosen["title_vi"],
        "confidence": round(confidence, 3),
        "matched_signals": matched_signals,
        "missing_fields": list(dict.fromkeys(missing_fields)),
        "clarification_question": clarification,
        "suggestions": suggestions_for_footage(footage_type, user_request),
        "selected_effect_stack": effect_stack_for(chosen, intensity_value),
        "professional_prompt": canonical.professional_prompt,
        "negative_prompt": ", ".join(chosen.get("negative_prompt") or []),
        "preserve_constraints": constraints,
        "preserve_controls": preserve,
        "target_duration_seconds": max(0, duration),
        "target_aspect_ratio": aspect,
        "provider_capability_required": chosen.get("provider_capability_required") or "video_to_video",
        "execution_lane": "generative" if chosen.get("generative_required") else "local",
        "local_preprocess_plan": local_preprocess_plan(chosen, intensity_value, aspect, preserve.get("preserve_source_audio", True)),
        "safe_fallback": "local_enhancement" if chosen.get("local_fallback_options") else "ask_user",
        "footage_type": footage_type,
        "intensity": intensity_value,
        "profile": chosen,
        "knowledge_profile_id": canonical.selected_profile_id,
        "provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "xu_charged": 0,
    }


__all__ = [
    "AI_EDIT_PROFILES", "DEFAULT_PRESERVE_CONTROLS", "INTENSITY_LABELS",
    "profile_option", "public_profile_options", "route_ai_edit_intent",
    "suggestions_for_footage", "local_preprocess_plan",
]
