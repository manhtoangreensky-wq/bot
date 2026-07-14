"""Provider-free state contract for the public SCENE3 video planner.

This module owns planning metadata only.  It must never create a job, write an
outbox row, call an image/video provider, or mutate a wallet.
"""

from __future__ import annotations

import unicodedata
from copy import deepcopy
from typing import Any

from services import video_addon_planner, video_scene_prompt_builder, video_semantic_scene_planner


SCENE_SECONDS = 8
MIN_SCENES = 1
MAX_SCENES = 20

CANONICAL_STEPS = (
    "subject",
    "scene_count",
    "content_type",
    "technical_profile",
    "suggestion",
    "requirements",
    "materials",
    "creative_controls",
    "content_addons",
    "scene_plan",
    "image_strategy",
    "image_prompts",
    "video_prompts",
    "full_review",
    "post_addons",
    "aspect_ratio",
    "quality",
    "final_report",
    "final_confirmation",
)

BACK_STEP = {
    "subject": "menu",
    "scene_count": "subject",
    "content_type": "scene_count",
    "technical_profile": "content_type",
    "suggestion": "technical_profile",
    "requirements": "suggestion",
    "materials": "requirements",
    "creative_controls": "materials",
    "content_addons": "creative_controls",
    "scene_plan": "content_addons",
    "image_strategy": "scene_plan",
    "image_prompts": "image_strategy",
    "video_prompts": "image_prompts",
    "full_review": "video_prompts",
    "post_addons": "full_review",
    "aspect_ratio": "post_addons",
    "quality": "aspect_ratio",
    "final_report": "quality",
    "final_confirmation": "final_report",
}

CONTENT_TYPES = (
    {"id": "storytelling", "label": "📖 Kể chuyện", "arc": "mở vấn đề, phát triển hành động, khép lại trọn ý"},
    {"id": "product_review", "label": "🛒 Review sản phẩm", "arc": "nhu cầu, trải nghiệm, bằng chứng, kết luận"},
    {"id": "news", "label": "📰 Tin tức", "arc": "sự kiện, bối cảnh, diễn biến, điều cần nhớ"},
    {"id": "philosophy_quotes", "label": "🧘 Triết lý / đạo lý", "arc": "tình huống, chiêm nghiệm, bài học"},
    {"id": "educational", "label": "🎓 Kiến thức", "arc": "câu hỏi, giải thích, ví dụ, ghi nhớ"},
    {"id": "history", "label": "🏛 Lịch sử", "arc": "bối cảnh, mốc chính, chuyển biến, ý nghĩa"},
    {"id": "ugc_affiliate", "label": "🛍 Tiếp thị / trải nghiệm đời thường", "arc": "vấn đề thật, dùng thử, lợi ích, lời mời"},
    {"id": "real_estate_fpv", "label": "🏠 Bất động sản / địa điểm", "arc": "tiếp cận, khám phá, điểm nổi bật, tổng quan"},
    {"id": "fashion_lookbook", "label": "👗 Thời trang / trình diễn", "arc": "diện mạo, chuyển động, chi tiết, thần thái"},
    {"id": "food_asmr", "label": "🍜 Ẩm thực / âm thanh cận cảnh", "arc": "nguyên liệu, chế biến, thành phẩm, thưởng thức"},
    {"id": "lofi_audio_visualizer", "label": "🎧 Thư giãn / nhạc hình", "arc": "không gian, nhịp cảm xúc, biến chuyển, dư âm"},
    {"id": "cinematic_trailer", "label": "🎞 Phim ngắn / trailer", "arc": "thiết lập, xung đột, cao trào, kết hoặc gợi mở"},
)

TECHNICAL_PROFILES = (
    ("architecture_exterior", "🏛 Kiến trúc ngoại thất"),
    ("architecture_interior", "🛋 Nội thất"),
    ("space_renovation", "🏠 Cải tạo không gian"),
    ("real_estate_property", "🏢 Bất động sản"),
    ("architecture_walkthrough", "🎬 Video tham quan kiến trúc"),
    ("cinematic_vfx", "✨ Hiệu ứng điện ảnh"),
    ("animation_2d_3d", "🧸 Hoạt hình 2D/3D"),
    ("character", "🧍 Nhân vật"),
    ("fashion_lookbook", "👗 Thời trang/trình diễn"),
    ("product_3d_showcase", "📦 Trưng bày sản phẩm/3D"),
    ("app_game_demo", "🎮 Giới thiệu ứng dụng/trò chơi"),
    ("website_saas_demo", "💻 Giới thiệu website/phần mềm"),
    ("tutorial_explainer", "🎓 Hướng dẫn/giải thích"),
    ("ugc_social_creator", "📱 Nội dung người dùng/mạng xã hội"),
)

TECHNICAL_PROFILE_RELEVANCE = {
    "storytelling": ("character", "cinematic_vfx", "animation_2d_3d", "ugc_social_creator"),
    "product_review": ("product_3d_showcase", "ugc_social_creator", "cinematic_vfx", "app_game_demo"),
    "news": ("tutorial_explainer", "ugc_social_creator", "cinematic_vfx", "app_game_demo"),
    "philosophy_quotes": ("character", "cinematic_vfx", "animation_2d_3d", "tutorial_explainer"),
    "educational": ("tutorial_explainer", "app_game_demo", "website_saas_demo", "animation_2d_3d"),
    "history": ("cinematic_vfx", "animation_2d_3d", "architecture_exterior", "character"),
    "ugc_affiliate": ("ugc_social_creator", "product_3d_showcase", "fashion_lookbook", "tutorial_explainer"),
    "real_estate_fpv": (
        "real_estate_property", "architecture_walkthrough", "architecture_interior",
        "architecture_exterior", "space_renovation", "cinematic_vfx",
    ),
    "fashion_lookbook": ("fashion_lookbook", "character", "cinematic_vfx", "animation_2d_3d"),
    "food_asmr": ("product_3d_showcase", "ugc_social_creator", "cinematic_vfx", "tutorial_explainer"),
    "lofi_audio_visualizer": ("animation_2d_3d", "cinematic_vfx", "character", "architecture_interior"),
    "cinematic_trailer": ("cinematic_vfx", "character", "animation_2d_3d", "product_3d_showcase"),
}

REQUIREMENT_CATEGORIES = (
    ("identity", "🧍 Nhân vật/nhận diện"),
    ("product", "📦 Sản phẩm"),
    ("brand_logo", "🏷 Thương hiệu/logo"),
    ("colors", "🎨 Màu sắc chủ đạo"),
    ("materials", "🧱 Vật liệu"),
    ("environment", "🏞 Bối cảnh/kiến trúc"),
    ("wardrobe", "👗 Trang phục"),
    ("references", "🖼 Ảnh tham chiếu"),
)

MATERIAL_TYPES = (
    ("ai_image_plan", "✨ Tạo ảnh AI trước"),
    ("layout_ideas", "💡 Gợi ý bố cục ảnh"),
    ("storyboard_prompt", "🎞 Câu lệnh ảnh từ bảng phân cảnh"),
    ("character_person", "🧍 Gửi ảnh nhân vật/người"),
    ("product_object", "📦 Gửi ảnh sản phẩm/đồ vật"),
    ("background", "🏞 Gửi ảnh bối cảnh"),
    ("visual_style_reference", "🎨 Gửi ảnh phong cách"),
    ("storyboard_frames", "🖼 Gửi ảnh bảng phân cảnh"),
    ("logo", "🏷 Gửi logo"),
    ("voice_audio", "🎙 Gửi lời đọc/âm thanh"),
    ("music", "🎵 Gửi nhạc nền"),
)

MATERIAL_TYPE_ALIASES = {
    "character_product": "product_object",
}

LOGO_POSITIONS = (
    ("top_left", "↖️ Trên trái"),
    ("top_center", "⬆️ Trên giữa"),
    ("top_right", "↗️ Trên phải"),
    ("bottom_left", "↙️ Dưới trái"),
    ("bottom_center", "⬇️ Dưới giữa"),
    ("bottom_right", "↘️ Dưới phải"),
)

CREATIVE_CONTROLS = (
    ("context", "🧭 Chủ đề/ngữ cảnh"),
    ("colors", "🎨 Màu sắc"),
    ("visual_style", "🖼 Phong cách hình ảnh"),
    ("motion", "🏃 Chuyển động"),
    ("camera", "🎥 Góc máy"),
    ("pacing", "⏱ Nhịp dựng"),
    ("emotion", "💭 Cảm xúc"),
    ("negative", "🚫 Điều cần tránh"),
)

CREATIVE_QUICK_PRESETS = (
    ("Chân thật tự nhiên", {"visual_style": "chân thật tự nhiên", "motion": "chuyển động nhẹ", "camera": "camera theo chủ thể", "pacing": "nhịp vừa"}),
    ("Điện ảnh cảm xúc", {"visual_style": "điện ảnh cảm xúc", "motion": "chuyển động có chủ đích", "camera": "lia và tiến máy mượt", "pacing": "nhịp cảm xúc"}),
    ("Quảng cáo rõ sản phẩm", {"visual_style": "quảng cáo sạch, rõ sản phẩm", "motion": "chuyển động làm nổi lợi ích", "camera": "cận chi tiết rồi mở rộng", "pacing": "hook nhanh, kết rõ"}),
    ("Sang trọng tối giản", {"visual_style": "sang trọng tối giản", "motion": "chuyển động chậm có kiểm soát", "camera": "mở lộ sản phẩm", "pacing": "chậm và tinh tế"}),
)

CONTENT_ADDONS = (
    ("voiceover", "🎙 Lời dẫn/lời thoại"),
    ("captions", "💬 Phụ đề/chữ hiển thị"),
    ("cta", "📣 Lời kêu gọi hành động"),
    ("scene_text", "🔤 Chữ riêng theo cảnh"),
    ("logo_safe_zone", "🏷 Chừa vùng logo"),
    ("watermark_safe_zone", "🔖 Chừa vùng dấu bản quyền"),
    ("preserve_source_audio", "🔊 Giữ âm thanh gốc"),
    ("music_mood", "🎵 Nhịp/cảm xúc nhạc"),
    ("transition_style", "🔗 Kiểu chuyển cảnh"),
    ("target_duration", "⏳ Thời lượng mục tiêu"),
)

POST_ADDONS = (
    ("logo_image", "🏷 Logo hình ảnh"),
    ("watermark_text", "🔖 Dấu bản quyền chữ"),
    ("watermark_image", "🖼 Dấu bản quyền hình"),
    ("subtitles", "💬 Phụ đề"),
    ("voice", "🗣 Giọng đọc"),
    ("dubbing", "🎙 Lồng tiếng"),
    ("music", "🎵 Nhạc nền"),
    ("text_overlay", "🔤 Chữ hiển thị"),
    ("sfx", "🔊 Hiệu ứng âm thanh"),
    ("audio_balance", "🎚 Cân bằng âm thanh"),
    ("mp4_export", "📦 Xuất MP4"),
)

POST_ADDON_DEFAULTS: dict[str, dict[str, Any]] = {
    "logo_image": {
        "source": "user_asset",
        "position": "top_right",
        "width_ratio": 0.12,
        "max_width_ratio": 0.18,
        "opacity_percent": 90,
        "margin_x_ratio": 0.04,
        "margin_y_ratio": 0.035,
        "preserve_aspect_ratio": True,
        "safe_zone": True,
        "applied_to_mp4": False,
    },
    "watermark_text": {
        "text": "",
        "font": "mặc định dễ đọc",
        "size": "nhỏ",
        "opacity_percent": 45,
        "position": "bottom_right",
        "repeat": False,
        "start_seconds": 0,
        "end_seconds": "hết video",
        "applied_to_mp4": False,
    },
    "watermark_image": {
        "source": "user_asset",
        "size": "nhỏ",
        "opacity_percent": 45,
        "position": "bottom_right",
        "start_seconds": 0,
        "end_seconds": "hết video",
        "applied_to_mp4": False,
    },
    "subtitles": {
        "source": "voice_or_dialogue",
        "translation": False,
        "style": "dễ đọc",
        "position": "bottom_center",
        "outline": True,
        "max_lines": 2,
        "safe_area": True,
        "applied_to_mp4": False,
    },
    "voice": {
        "voice_type": "not_selected",
        "voice_source": "not_selected",
        "script_note": "",
        "preview_requested": False,
        "volume_percent": 100,
        "applied_to_mp4": False,
    },
    "dubbing": {
        "language": "vi",
        "voice_source": "not_selected",
        "timing": "fit_scene",
        "source_audio_policy": "duck",
        "volume_percent": 100,
        "applied_to_mp4": False,
    },
    "music": {
        "source": "not_selected",
        "volume_percent": 20,
        "trim_mode": "fit_video",
        "fade_in": True,
        "fade_out": True,
        "ducking": True,
        "paid_generation": False,
        "applied_to_mp4": False,
    },
    "text_overlay": {
        "text": "",
        "position": "top_center",
        "safe_area": True,
        "applied_to_mp4": False,
    },
    "sfx": {
        "source": "library_only",
        "volume_percent": 35,
        "applied_to_mp4": False,
    },
    "audio_balance": {
        "normalize": True,
        "voice_priority": True,
        "applied_to_mp4": False,
    },
    "mp4_export": {
        "container": "MP4",
        "validation_required": True,
        "delivery_required_before_charge": True,
        "completed": False,
    },
}

POST_ADDON_PRESETS: dict[str, tuple[tuple[str, dict[str, Any]], ...]] = {
    "logo_image": (
        ("Nhỏ ở góc trên phải", {"position": "top_right", "width_ratio": 0.12, "opacity_percent": 90}),
        ("Nhỏ ở góc trên trái", {"position": "top_left", "width_ratio": 0.12, "opacity_percent": 90}),
        ("Nhỏ ở góc dưới phải", {"position": "bottom_right", "width_ratio": 0.12, "opacity_percent": 90}),
    ),
    "watermark_text": (
        ("Một lần ở góc dưới phải", {"position": "bottom_right", "repeat": False, "opacity_percent": 45}),
        ("Lặp nhẹ trong video", {"position": "bottom_right", "repeat": True, "opacity_percent": 35}),
    ),
    "watermark_image": (
        ("Hình nhỏ ở góc dưới phải", {"position": "bottom_right", "size": "nhỏ", "opacity_percent": 45}),
        ("Hình nhỏ ở góc trên trái", {"position": "top_left", "size": "nhỏ", "opacity_percent": 45}),
    ),
    "subtitles": (
        ("Dễ đọc ở phía dưới", {"style": "dễ đọc", "position": "bottom_center", "outline": True, "max_lines": 2}),
        ("Gọn ở phía trên", {"style": "gọn", "position": "top_center", "outline": True, "max_lines": 2}),
    ),
    "voice": (
        ("Giọng nữ mặc định", {"voice_type": "female", "voice_source": "approved_default", "volume_percent": 100}),
        ("Giọng nam mặc định", {"voice_type": "male", "voice_source": "approved_default", "volume_percent": 100}),
        ("Dùng tệp giọng đã gửi", {"voice_type": "user_voice", "voice_source": "user_asset", "volume_percent": 100}),
        ("Dùng giọng đã lưu", {"voice_type": "saved_voice", "voice_source": "saved_asset", "volume_percent": 100}),
    ),
    "dubbing": (
        ("Tiếng Việt, ưu tiên lời nói", {"language": "vi", "timing": "fit_scene", "source_audio_policy": "duck"}),
        ("Tiếng Anh, ưu tiên lời nói", {"language": "en", "timing": "fit_scene", "source_audio_policy": "duck"}),
        ("Tiếng Nhật, ưu tiên lời nói", {"language": "ja", "timing": "fit_scene", "source_audio_policy": "duck"}),
        ("Tiếng Hàn, ưu tiên lời nói", {"language": "ko", "timing": "fit_scene", "source_audio_policy": "duck"}),
        ("Tiếng Trung, ưu tiên lời nói", {"language": "zh", "timing": "fit_scene", "source_audio_policy": "duck"}),
        ("Ngôn ngữ khác", {"language": "other", "timing": "fit_scene", "source_audio_policy": "duck"}),
    ),
    "music": (
        ("Nhạc mặc định theo nội dung", {"source": "approved_library", "volume_percent": 20, "ducking": True}),
        ("Kho nhạc đã duyệt", {"source": "approved_library", "volume_percent": 20, "ducking": True, "trim_mode": "fit_video"}),
        ("Tệp nhạc người dùng đã gửi", {"source": "user_asset", "volume_percent": 20, "ducking": True, "trim_mode": "fit_video"}),
    ),
    "text_overlay": (
        ("Chữ gọn phía trên", {"position": "top_center", "safe_area": True}),
        ("Chữ gọn phía dưới", {"position": "bottom_center", "safe_area": True}),
    ),
    "sfx": (
        ("Hiệu ứng nhẹ từ kho có sẵn", {"source": "library_only", "volume_percent": 35}),
        ("Hiệu ứng rõ hơn từ kho có sẵn", {"source": "library_only", "volume_percent": 50}),
    ),
    "audio_balance": (
        ("Ưu tiên lời nói", {"normalize": True, "voice_priority": True}),
        ("Cân bằng lời và nhạc", {"normalize": True, "voice_priority": False}),
    ),
    "mp4_export": (
        ("MP4 có kiểm tra trước khi gửi", {"container": "MP4", "validation_required": True, "delivery_required_before_charge": True}),
    ),
}

IMAGE_STRATEGIES = (
    ("direct_description", "📝 Tạo trực tiếp từ mô tả"),
    ("uploaded_image", "📎 Dùng ảnh đã tải"),
    ("ai_image", "✨ Lập kế hoạch tạo ảnh AI"),
    ("previous_last_frame", "🔗 Dùng khung cuối cảnh trước"),
)

TRANSITIONS = {
    "cut on action": ("Cắt theo hành động", "Chuyển sau khi hành động đã hoàn tất tự nhiên."),
    "match cut": ("Cắt tương đồng", "Nối hai khung có hình dáng hoặc bố cục tương đồng."),
    "motion match": ("Nối cùng hướng chuyển động", "Giữ cùng hướng di chuyển để cảnh sau tiếp nhận mượt."),
    "camera pan continuation": ("Tiếp nối lia máy", "Cảnh sau tiếp tục hướng lia của cảnh trước."),
    "object wipe": ("Vật thể lướt che khung", "Dùng vật thể đi qua khung để che điểm cắt."),
    "doorway transition": ("Chuyển qua cửa", "Đi qua cửa hoặc lối mở để bước sang không gian mới."),
    "reveal": ("Mở lộ cảnh", "Camera hoặc chủ thể mở dần cảnh tiếp theo."),
    "dissolve": ("Hòa cảnh", "Hai cảnh hòa nhẹ khi cảm xúc hoặc thời gian chuyển tiếp."),
    "fade": ("Mờ dần", "Khép một nhịp rồi mở nhịp mới bằng mờ dần."),
    "whip pan": ("Lia nhanh", "Lia máy nhanh có kiểm soát để nối hai cảnh năng động."),
    "before/after morph": ("Biến đổi trước–sau", "Biến đổi cùng bố cục để thể hiện thay đổi rõ ràng."),
    "sound bridge": ("Nối bằng âm thanh", "Âm thanh cảnh sau xuất hiện trước hình để nối mạch."),
    "dialogue bridge": ("Nối bằng lời thoại", "Lời nói tiếp tục qua điểm cắt mà không bị cụt câu."),
    "mở trực tiếp": ("Mở trực tiếp", "Bắt đầu cảnh đầu tiên rõ ràng, không cần chuyển cảnh."),
    "kết thúc trọn vẹn": ("Kết thúc trọn vẹn", "Khép video sau khi hành động và camera đã hoàn tất."),
}

PUBLIC_PLANNING_REPLACEMENTS = {
    "character_setup": "giới thiệu nhân vật và trạng thái ban đầu",
    "resolution": "hoàn tất câu chuyện và kết luận",
    "opening": "mở đầu",
    "context": "bối cảnh",
    "development": "phát triển",
    "payoff": "thành quả",
    "conclusion": "kết luận",
    "cut on action": "cắt theo hành động",
    "match cut": "cắt tương đồng",
    "motion match": "nối cùng hướng chuyển động",
    "camera pan continuation": "tiếp nối lia máy",
    "object wipe": "vật thể lướt che khung",
    "doorway transition": "chuyển qua cửa",
    "before/after morph": "biến đổi trước-sau",
    "sound bridge": "nối bằng âm thanh",
    "dialogue bridge": "nối bằng lời thoại",
}

_SUGGESTION_PATTERNS = (
    ("Mở bằng điều người xem đang quan tâm", "đặt vấn đề rõ, phát triển bằng hành động, kết bằng kết quả", "dễ hiểu ngay từ những giây đầu"),
    ("Mở bằng tương phản trước và sau", "cho thấy trạng thái ban đầu, quá trình thay đổi và thành quả", "làm nổi bật giá trị bằng bằng chứng hình ảnh"),
    ("Mở bằng một khoảnh khắc đời thật", "theo chủ thể qua từng nhịp hoàn chỉnh rồi khép lại tự nhiên", "tạo cảm giác gần gũi và liền mạch"),
    ("Mở bằng câu hỏi ngắn", "trả lời lần lượt qua các cảnh, mỗi cảnh giải quyết một ý", "phù hợp nội dung cần giải thích rõ"),
    ("Mở bằng hình ảnh kết quả đáng nhớ", "quay lại nguyên nhân, diễn biến rồi trở về kết quả và lời kết", "tạo tò mò nhưng vẫn trọn vẹn câu chuyện"),
)


def _entry_map(items: tuple[tuple[str, str], ...]) -> dict[str, dict[str, Any]]:
    return {key: {"enabled": False, "value": "", "history": []} for key, _label in items}


def default_state(*, product_type: str = "", subject: str = "", aspect_ratio: str = "9:16") -> dict[str, Any]:
    return {
        "step": "scene_count" if subject else "await_subject",
        "history": ["await_subject"] if subject else ["menu"],
        "product_type": str(product_type or ""),
        "subject": str(subject or ""),
        "scene_count": 0,
        "content_type": "",
        "content_type_history": [],
        "suggested_content_type": "",
        "technical_profile": "",
        "technical_profile_history": [],
        "suggested_technical_profile": "",
        "technical_profile_suggestion_offset": 0,
        "show_all_technical_profiles": False,
        "context": "",
        "profile_context": "",
        "suggestions": [],
        "suggestion_version": 0,
        "suggestion_history": [],
        "selected_suggestion": {},
        "preservation_requirements": _entry_map(REQUIREMENT_CATEGORIES),
        "requirements": {},
        "reference_assets": {},
        "assets": {},
        "creative_controls": _entry_map(CREATIVE_CONTROLS),
        "content_affecting_addons": _entry_map(CONTENT_ADDONS),
        "content_addons": {"cta": False, "aspect_ratio": aspect_ratio, "transition_style": ""},
        "scene_plan": {},
        "plan": {},
        "continuity_contract": {},
        "image_strategy_per_scene": {},
        "image_prompt_versions": {},
        "video_prompt_versions": {},
        "transition_plan": [],
        "voice_timing_by_scene": {},
        "cta_placement_by_scene": {},
        "postproduction_addons": _entry_map(POST_ADDONS),
        "post_addon_suggestion": [],
        "post_addons": {},
        "aspect_ratio": aspect_ratio if aspect_ratio in {"9:16", "16:9", "1:1", "4:5"} else "9:16",
        "quality_tier": 0,
        "quality_xu": 0,
        "estimate": {},
        "duration_estimate": {},
        "price_estimate": {},
        "final_report": {},
        "final_confirmed": False,
        "provider_called": False,
        "image_provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "xu_charged": 0,
        "wallet_mutations": 0,
    }


def normalize_state(value: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(value or {})
    base = default_state(
        product_type=str(raw.get("product_type") or raw.get("source_product_id") or ""),
        subject=str(raw.get("subject") or ""),
        aspect_ratio=str(raw.get("aspect_ratio") or (raw.get("content_addons") or {}).get("aspect_ratio") or "9:16"),
    )
    base.update(raw)
    base["history"] = [str(item) for item in base.get("history") or [] if str(item or "").strip()][-40:]
    for field, items in (
        ("preservation_requirements", REQUIREMENT_CATEGORIES),
        ("creative_controls", CREATIVE_CONTROLS),
        ("content_affecting_addons", CONTENT_ADDONS),
        ("postproduction_addons", POST_ADDONS),
    ):
        normalized = _entry_map(items)
        for key, item in dict(base.get(field) or {}).items():
            if key in normalized:
                if isinstance(item, dict):
                    normalized[key].update(item)
                else:
                    normalized[key].update({"enabled": bool(item), "value": item})
        base[field] = normalized
    for field in (
        "requirements", "reference_assets", "assets", "content_addons", "scene_plan", "plan",
        "continuity_contract", "image_strategy_per_scene", "image_prompt_versions", "video_prompt_versions",
        "voice_timing_by_scene", "cta_placement_by_scene", "post_addons", "estimate",
        "duration_estimate", "price_estimate", "final_report", "selected_suggestion",
    ):
        base[field] = dict(base.get(field) or {})
    base["transition_plan"] = [dict(item) for item in base.get("transition_plan") or [] if isinstance(item, dict)]
    base["suggestions"] = [dict(item) for item in base.get("suggestions") or [] if isinstance(item, dict)][:5]
    base["suggestion_history"] = [list(items) for items in base.get("suggestion_history") or [] if isinstance(items, list)][-5:]
    base["content_type_history"] = [str(item) for item in base.get("content_type_history") or [] if content_type(str(item))][-10:]
    valid_profiles = {key for key, _label in TECHNICAL_PROFILES}
    base["technical_profile_history"] = [str(item) for item in base.get("technical_profile_history") or [] if not item or str(item) in valid_profiles][-10:]
    base["post_addon_suggestion"] = [str(item) for item in base.get("post_addon_suggestion") or [] if str(item) in dict(POST_ADDONS)]
    base["scene_count"] = max(0, min(MAX_SCENES, int(base.get("scene_count") or 0)))
    base["provider_called"] = False
    base["image_provider_called"] = False
    base["job_created"] = False
    base["outbox_created"] = False
    base["xu_charged"] = 0
    base["wallet_mutations"] = 0
    return base


def invalidate_scene_outputs(state: dict[str, Any], scene_count: int) -> dict[str, Any]:
    updated = normalize_state(state)
    updated["scene_count"] = max(MIN_SCENES, min(MAX_SCENES, int(scene_count or 1)))
    for field, empty in (
        ("scene_plan", {}), ("plan", {}), ("continuity_contract", {}),
        ("image_strategy_per_scene", {}), ("image_prompt_versions", {}),
        ("video_prompt_versions", {}), ("transition_plan", []),
        ("voice_timing_by_scene", {}), ("cta_placement_by_scene", {}),
        ("estimate", {}), ("duration_estimate", {}), ("price_estimate", {}),
        ("final_report", {}),
    ):
        updated[field] = deepcopy(empty)
    updated["quality_tier"] = 0
    updated["quality_xu"] = 0
    updated["final_confirmed"] = False
    return updated


def content_type(content_type_id: str) -> dict[str, str]:
    return next((dict(item) for item in CONTENT_TYPES if item["id"] == str(content_type_id or "")), {})


def suggested_content_type(state: dict[str, Any]) -> str:
    """Choose a deterministic approved content type without external inference."""

    state = normalize_state(state)
    product_type = str(state.get("product_type") or state.get("source_product_id") or "")
    product_defaults = {
        "video_trend": "news",
        "script_image_video": "storytelling",
        "self_shot_scene_change": "ugc_affiliate",
        "multi_scene_film": "cinematic_trailer",
        "storyboard_prompt": "storytelling",
        "video_idea": "storytelling",
    }
    if product_type in product_defaults:
        return product_defaults[product_type]
    subject = unicodedata.normalize("NFKD", str(state.get("subject") or "").lower())
    subject = "".join(char for char in subject if not unicodedata.combining(char))
    keyword_types = (
        (("can ho", "bat dong san", "kien truc", "noi that", "dia diem"), "real_estate_fpv"),
        (("san pham", "review", "danh gia"), "product_review"),
        (("lich su", "di san"), "history"),
        (("kien thuc", "huong dan", "giai thich"), "educational"),
        (("thoi trang", "lookbook"), "fashion_lookbook"),
        (("am thuc", "mon an", "nau an"), "food_asmr"),
        (("trailer", "phim ngan", "dien anh"), "cinematic_trailer"),
    )
    for keywords, content_id in keyword_types:
        if any(keyword in subject for keyword in keywords):
            return content_id
    return "storytelling"


def post_addon_suggestions(state: dict[str, Any]) -> list[str]:
    """Return optional post-production suggestions without enabling anything."""

    state = normalize_state(state)
    suggestions: list[str] = ["mp4_export"]
    content_addons = dict(state.get("content_affecting_addons") or {})
    assets = [dict(item) for item in (state.get("reference_assets") or {}).get("items") or [] if isinstance(item, dict)]
    if any(str(item.get("type") or "") == "logo" for item in assets):
        suggestions.append("logo_image")
    if (content_addons.get("captions") or {}).get("enabled"):
        suggestions.append("subtitles")
    if (content_addons.get("voiceover") or {}).get("enabled"):
        suggestions.extend(["voice", "audio_balance"])
    if any(str(item.get("type") or "") == "music" for item in assets):
        suggestions.extend(["music", "audio_balance"])
    result: list[str] = []
    for key in suggestions:
        if key not in result:
            result.append(key)
    return result


def technical_profile_label(profile_id: str) -> str:
    if not str(profile_id or ""):
        return "Không dùng mẫu chuyên ngành"
    return next((label for key, label in TECHNICAL_PROFILES if key == profile_id), "Mẫu chuyên ngành chưa xác định")


def post_addon_default(key: str) -> dict[str, Any]:
    return deepcopy(POST_ADDON_DEFAULTS.get(str(key or ""), {}))


def normalize_material_type(value: str) -> str:
    material_type = str(value or "").strip()
    return MATERIAL_TYPE_ALIASES.get(material_type, material_type)


def logo_position_label(value: str) -> str:
    return dict(LOGO_POSITIONS).get(str(value or ""), "Chưa chọn vị trí")


def configure_logo_reference(
    state: dict[str, Any],
    *,
    position: str = "",
    enabled: bool = True,
) -> dict[str, Any]:
    """Store a planning-only logo layout without claiming an MP4 overlay."""

    updated = normalize_state(state)
    assets = dict(updated.get("reference_assets") or {})
    current = dict(assets.get("logo_config") or {})
    if position and position not in dict(LOGO_POSITIONS):
        return updated
    current.update({
        "logo_enabled": bool(enabled),
        "logo_position": position if enabled else "",
        "logo_width_ratio": 0.12,
        "logo_max_width_ratio": 0.18,
        "logo_margin_x_ratio": 0.04,
        "logo_margin_y_ratio": 0.035,
        "logo_preserve_aspect_ratio": True,
        "applied_to_mp4": False,
    })
    assets["logo_config"] = current
    updated["reference_assets"] = assets
    updated["assets"] = deepcopy(assets)
    return updated


def post_addon_preset_label(key: str, config: dict[str, Any] | None) -> str:
    config = dict(config or {})
    label = str(config.get("preset_name") or "").strip()
    return label or "Cấu hình mặc định"


def cycle_post_addon_preset(state: dict[str, Any], key: str) -> dict[str, Any]:
    """Cycle approved deterministic presets without executing an add-on."""

    updated = normalize_state(state)
    key = str(key or "")
    presets = POST_ADDON_PRESETS.get(key, ())
    if not presets:
        return updated
    current = dict((updated.get("postproduction_addons") or {}).get(key) or {})
    current_value = dict(current.get("value") or {}) if isinstance(current.get("value"), dict) else {}
    current_index = current_value.get("preset_index")
    next_index = (int(current_index) + 1) % len(presets) if current_index is not None else 0
    preset_name, patch = presets[next_index]
    config = post_addon_default(key)
    config.update(deepcopy(patch))
    config.update({
        "preset_index": next_index,
        "preset_name": preset_name,
    })
    if "applied_to_mp4" in config:
        config["applied_to_mp4"] = False
    if "completed" in config:
        config["completed"] = False
    return set_entry(updated, "postproduction_addons", key, config, enabled=True)


def cycle_creative_quick_preset(state: dict[str, Any]) -> dict[str, Any]:
    """Apply the next approved style bundle without external generation."""

    updated = normalize_state(state)
    raw_index = updated.get("creative_quick_index")
    current_index = int(raw_index) if raw_index is not None else -1
    next_index = (current_index + 1) % len(CREATIVE_QUICK_PRESETS)
    preset_name, values = CREATIVE_QUICK_PRESETS[next_index]
    for key, value in values.items():
        updated = set_entry(updated, "creative_controls", key, value, enabled=True)
    updated["creative_quick_index"] = next_index
    updated["creative_quick_name"] = preset_name
    return updated


def validate_two_column_rows(rows: list[list[tuple[str, str]]]) -> list[list[tuple[str, str]]]:
    """Validate the public two-column keyboard contract without Telegram imports."""

    normalized: list[list[tuple[str, str]]] = []
    callbacks: set[str] = set()
    for row in rows:
        if len(row) != 2:
            raise ValueError("video_scene3_keyboard_requires_exactly_two_buttons_per_row")
        clean_row: list[tuple[str, str]] = []
        for label, callback in row:
            clean_label = str(label or "").strip()
            clean_callback = str(callback or "").strip()
            if not clean_label or not clean_callback or clean_callback in callbacks:
                raise ValueError("video_scene3_keyboard_duplicate_or_empty_button")
            callbacks.add(clean_callback)
            clean_row.append((clean_label, clean_callback))
        normalized.append(clean_row)
    return normalized


def technical_profiles_for_content(content_type_id: str, *, show_all: bool = False) -> tuple[tuple[str, str], ...]:
    if show_all:
        return TECHNICAL_PROFILES
    labels = dict(TECHNICAL_PROFILES)
    relevant = TECHNICAL_PROFILE_RELEVANCE.get(str(content_type_id or ""), ())
    return tuple((profile_id, labels[profile_id]) for profile_id in relevant if profile_id in labels) or TECHNICAL_PROFILES


def suggested_technical_profile(content_type_id: str, offset: int = 0) -> str:
    options = technical_profiles_for_content(content_type_id)
    if not options:
        return ""
    return str(options[max(0, int(offset or 0)) % len(options)][0])


def requirement_suggestion(key: str, state: dict[str, Any]) -> str:
    subject = str((state or {}).get("subject") or "chủ thể")
    values = {
        "identity": f"Giữ nguyên khuôn mặt, vóc dáng và đặc điểm nhận diện của {subject} giữa mọi cảnh.",
        "product": f"Giữ nguyên hình dáng, màu, nhãn và tỉ lệ sản phẩm trong {subject}.",
        "brand_logo": "Không tự tạo hoặc sửa logo; chỉ dùng đúng logo người dùng đã gửi.",
        "colors": "Giữ bảng màu chủ đạo nhất quán từ cảnh đầu tới cảnh cuối.",
        "materials": "Giữ đúng chất liệu, bề mặt, độ bóng và cấu tạo đã mô tả.",
        "environment": "Giữ logic kiến trúc, vị trí đồ vật và hướng không gian giữa các cảnh.",
        "wardrobe": "Giữ nguyên trang phục, phụ kiện và kiểu tóc trừ khi kịch bản yêu cầu thay đổi.",
        "references": "Bám sát ảnh tham chiếu đã gửi; không dùng tài sản của người dùng khác.",
    }
    return values.get(str(key or ""), "Giữ nguyên chi tiết quan trọng giữa mọi cảnh.")


def creative_defaults(state: dict[str, Any]) -> dict[str, str]:
    profile = technical_profile_label(str((state or {}).get("technical_profile") or ""))
    content = content_type_label(str((state or {}).get("content_type") or ""))
    return {
        "context": f"Bối cảnh phù hợp {content.lower()}, tập trung đúng chủ đề đã nhập.",
        "colors": "Màu tự nhiên, đồng nhất và đủ tương phản cho chủ thể chính.",
        "visual_style": f"Phong cách hình ảnh theo {profile.lower()}, chân thật và nhất quán.",
        "motion": "Mỗi cảnh có một chuyển động chính hoàn tất trong 8 giây.",
        "camera": "Camera có điểm bắt đầu, chuyển động và điểm dừng rõ; không cắt giữa chuyển động.",
        "pacing": "Nhịp rõ ràng, đủ thời gian hiểu ý cảnh, nối mượt sang cảnh sau.",
        "emotion": "Cảm xúc tăng dần theo mạch nội dung và khép lại tự nhiên.",
        "negative": "Không đổi nhận diện, không méo sản phẩm, không chữ giả, không hành động dang dở.",
    }


def content_type_label(content_type_id: str) -> str:
    return str(content_type(content_type_id).get("label") or "Chưa chọn")


def suggestions_for(state: dict[str, Any], *, revision: int | None = None) -> list[dict[str, Any]]:
    state = normalize_state(state)
    info = content_type(str(state.get("content_type") or "storytelling")) or content_type("storytelling")
    subject = str(state.get("subject") or "chủ đề video").strip()
    profile = technical_profile_label(str(state.get("technical_profile") or ""))
    count = max(1, int(state.get("scene_count") or 1))
    rev = int(state.get("suggestion_version") or 0) + 1 if revision is None else max(1, int(revision))
    rows: list[dict[str, Any]] = []
    offset = (rev - 1) % len(_SUGGESTION_PATTERNS)
    for index in range(5):
        hook, flow, reason = _SUGGESTION_PATTERNS[(index + offset) % len(_SUGGESTION_PATTERNS)]
        rows.append({
            "index": index + 1,
            "title": f"Hướng {index + 1}: {hook}",
            "hook": f"{hook} về {subject}.",
            "concept": f"Kể theo loại {info['label'].split(' ', 1)[-1].lower()}, {info['arc']}.",
            "flow": f"Phân bổ thành đúng {count} cảnh: {flow}; mỗi cảnh hoàn tất một ý hoặc hành động.",
            "context": f"{profile}; giữ mạch hình ảnh và trạng thái cuối cảnh trước sang cảnh sau.",
            "reason": reason,
            "revision": rev,
        })
    return rows


def select_suggestion(state: dict[str, Any], index: int) -> dict[str, Any]:
    updated = normalize_state(state)
    suggestions = list(updated.get("suggestions") or [])
    if not suggestions:
        suggestions = suggestions_for(updated)
        updated["suggestions"] = suggestions
        updated["suggestion_version"] = int(suggestions[0].get("revision") or 1)
    selected = dict(suggestions[max(0, min(len(suggestions) - 1, int(index) - 1))])
    updated["selected_suggestion"] = selected
    updated["context"] = str(selected.get("concept") or selected.get("flow") or "")
    updated["profile_context"] = updated["context"]
    return updated


def refresh_suggestions(state: dict[str, Any]) -> dict[str, Any]:
    updated = normalize_state(state)
    current = list(updated.get("suggestions") or [])
    if current:
        history = list(updated.get("suggestion_history") or [])
        history.append(current)
        updated["suggestion_history"] = history[-5:]
    revision = int(updated.get("suggestion_version") or 0) + 1
    updated["suggestions"] = suggestions_for(updated, revision=revision)
    updated["suggestion_version"] = revision
    updated["selected_suggestion"] = {}
    return updated


def restore_suggestions(state: dict[str, Any]) -> dict[str, Any]:
    updated = normalize_state(state)
    history = list(updated.get("suggestion_history") or [])
    if history:
        updated["suggestions"] = [dict(item) for item in history.pop() if isinstance(item, dict)][:5]
        updated["suggestion_history"] = history
        updated["suggestion_version"] = max(1, int(updated.get("suggestion_version") or 1) - 1)
        updated["selected_suggestion"] = {}
    return updated


def set_entry(state: dict[str, Any], group: str, key: str, value: Any, *, enabled: bool = True) -> dict[str, Any]:
    updated = normalize_state(state)
    entries = dict(updated.get(group) or {})
    if key not in entries:
        return updated
    item = dict(entries[key])
    old = {"enabled": bool(item.get("enabled")), "value": item.get("value", "")}
    if old["enabled"] or str(old["value"] or ""):
        history = list(item.get("history") or [])
        history.append(old)
        item["history"] = history[-10:]
    item["enabled"] = bool(enabled)
    item["value"] = value
    entries[key] = item
    updated[group] = entries
    return updated


def toggle_entry(state: dict[str, Any], group: str, key: str, *, default_value: str = "đã chọn") -> dict[str, Any]:
    updated = normalize_state(state)
    item = dict((updated.get(group) or {}).get(key) or {})
    return set_entry(updated, group, key, item.get("value") or default_value, enabled=not bool(item.get("enabled")))


def remove_entry(state: dict[str, Any], group: str, key: str) -> dict[str, Any]:
    return set_entry(state, group, key, "", enabled=False)


def restore_entry(state: dict[str, Any], group: str, key: str) -> dict[str, Any]:
    updated = normalize_state(state)
    entries = dict(updated.get(group) or {})
    item = dict(entries.get(key) or {})
    history = list(item.get("history") or [])
    if history:
        previous = dict(history.pop())
        item.update(previous)
        item["history"] = history
        entries[key] = item
        updated[group] = entries
    return updated


def public_requirements(state: dict[str, Any]) -> dict[str, Any]:
    rows = dict(normalize_state(state).get("preservation_requirements") or {})
    values = [str(item.get("value") or "").strip() for item in rows.values() if item.get("enabled") and str(item.get("value") or "").strip()]
    return {"brief": "; ".join(values), "preserve_constraints": values}


def planner_content_addons(state: dict[str, Any]) -> dict[str, Any]:
    updated = normalize_state(state)
    entries = dict(updated.get("content_affecting_addons") or {})
    aspect = str(updated.get("aspect_ratio") or "9:16")
    result: dict[str, Any] = {
        "voiceover": bool(entries["voiceover"].get("enabled")),
        "dialogue": bool(entries["voiceover"].get("enabled")),
        "captions": bool(entries["captions"].get("enabled")),
        "subtitle_required": bool(entries["captions"].get("enabled")),
        "cta": bool(entries["cta"].get("enabled")),
        "logo_safe_zone": "top_right" if entries["logo_safe_zone"].get("enabled") else "none",
        "watermark_safe_zone": "bottom_right" if entries["watermark_safe_zone"].get("enabled") else "none",
        "preserve_source_audio": bool(entries["preserve_source_audio"].get("enabled")),
        "aspect_ratio": aspect,
        "music_mood": str(entries["music_mood"].get("value") or "theo mạch cảm xúc của nội dung"),
        "transition_style": str(entries["transition_style"].get("value") or ""),
    }
    return result


def planner_post_addons(state: dict[str, Any]) -> dict[str, bool]:
    entries = dict(normalize_state(state).get("postproduction_addons") or {})
    return {
        "logo_burn_in": bool(entries["logo_image"].get("enabled")),
        "watermark_burn_in": bool(entries["watermark_text"].get("enabled") or entries["watermark_image"].get("enabled")),
        "subtitle_rendering": bool(entries["subtitles"].get("enabled")),
        "dubbing_mix": bool(entries["voice"].get("enabled") or entries["dubbing"].get("enabled")),
        "music_mix": bool(entries["music"].get("enabled")),
        "final_audio_mix": bool(entries["audio_balance"].get("enabled")),
        "output_packaging": bool(entries["mp4_export"].get("enabled")),
    }


def _profile_for_planner(state: dict[str, Any]) -> str:
    return str(state.get("technical_profile") or state.get("content_type") or "storytelling")


def build_planning_package(state: dict[str, Any]) -> dict[str, Any]:
    """Build exact-N scene and prompt metadata without any provider call."""

    updated = normalize_state(state)
    count = max(MIN_SCENES, min(MAX_SCENES, int(updated.get("scene_count") or 1)))
    addon_plan = video_addon_planner.normalize_addon_plan(
        planner_content_addons(updated),
        planner_post_addons(updated),
        scene_count=count,
        seconds_per_scene=SCENE_SECONDS,
    )
    creative = dict(updated.get("creative_controls") or {})
    requirements = public_requirements(updated)
    requirements.update({
        "camera": str(creative["camera"].get("value") or ""),
        "lighting": str(creative["emotion"].get("value") or ""),
        "visual_style": str(creative["visual_style"].get("value") or ""),
    })
    plan = video_semantic_scene_planner.build_semantic_scene_plan(
        subject=str(updated.get("subject") or ""),
        scene_count=count,
        profile_id=_profile_for_planner(updated),
        context=str(updated.get("context") or updated.get("profile_context") or ""),
        requirements=requirements,
        assets=dict(updated.get("reference_assets") or updated.get("assets") or {}),
        addon_plan=addon_plan,
    )
    package = video_scene_prompt_builder.build_prompt_package(plan)
    return initialize_scene_artifacts(updated, package)


def transition_public(value: str) -> dict[str, str]:
    label, description = TRANSITIONS.get(str(value or ""), ("Chuyển cảnh tự nhiên", "Nối hai cảnh sau khi ý và chuyển động đã hoàn tất."))
    return {"label": label, "description": description}


def public_planning_text(value: Any) -> str:
    """Translate planner-only tokens before they reach a public Video screen."""

    text = str(value or "")
    for internal, public in sorted(PUBLIC_PLANNING_REPLACEMENTS.items(), key=lambda item: len(item[0]), reverse=True):
        text = text.replace(internal, public)
        text = text.replace(internal.upper(), public)
        text = text.replace(internal.title(), public)
    return text.replace("_", " ")


def _image_prompt(scene: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    aspect = str(state.get("aspect_ratio") or "9:16")
    constraints = "; ".join(str(item) for item in scene.get("preserve_constraints") or [])
    return {
        "prompt": (
            f"Khung hình cho cảnh {int(scene.get('scene_index') or 1)}: {scene.get('main_idea')}. "
            f"Chủ thể {scene.get('subject')}; bối cảnh {scene.get('environment')}; "
            f"bắt đầu {scene.get('start_state')}; ánh sáng {scene.get('lighting')}; "
            f"phong cách {scene.get('visual_style')}."
        ),
        "negative_prompt": "không sai nhận diện, không méo hình, không chữ giả, không thừa chi tiết, không đổi sản phẩm",
        "references": [],
        "identity_constraints": constraints,
        "composition": "chủ thể rõ; chừa vùng an toàn theo tùy chọn đã chọn",
        "camera": str(scene.get("camera") or ""),
        "lighting": str(scene.get("lighting") or ""),
        "colors": str(scene.get("visual_style") or ""),
        "aspect_ratio": aspect,
        "safe_zone": dict(((state.get("plan") or {}).get("addon_plan") or {}).get("composition_constraints") or {}),
    }


def _video_prompt(scene: dict[str, Any], prompt_row: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    internal_prompt = str(prompt_row.get("provider_prompt") or scene.get("provider_prompt") or "")
    internal_negative = str(prompt_row.get("negative_prompt") or scene.get("negative_prompt") or "")
    public_prompt = (
        f"Cảnh {int(scene.get('scene_index') or 1)}. Mục tiêu: {scene.get('main_idea')}. "
        f"Chủ thể: {scene.get('subject')}. Bối cảnh: {scene.get('environment')}. "
        f"Trạng thái đầu: {scene.get('start_state')}. Hành động hoàn chỉnh: {scene.get('primary_action')}. "
        f"Diễn biến: {scene.get('development')}. Trạng thái kết: {scene.get('completion_state')}. "
        f"Camera: {scene.get('camera')}. Ánh sáng: {scene.get('lighting')}. "
        f"Phong cách: {scene.get('visual_style')}. Hoàn tất hành động, câu nói và chuyển động camera trước khi chuyển cảnh."
    )
    return {
        "goal": str(scene.get("main_idea") or ""),
        "main_idea": str(scene.get("main_idea") or ""),
        "start_state": str(scene.get("start_state") or ""),
        "action": str(scene.get("primary_action") or ""),
        "development": str(scene.get("development") or ""),
        "end_state": str(scene.get("completion_state") or ""),
        "subject": str(scene.get("subject") or ""),
        "environment": str(scene.get("environment") or ""),
        "camera": str(scene.get("camera") or ""),
        "lighting": str(scene.get("lighting") or ""),
        "colors": str(scene.get("visual_style") or ""),
        "voice_or_dialogue": str(scene.get("dialogue_or_voiceover") or ""),
        "audio_intent": str(scene.get("audio_intent") or ""),
        "preserve": list(scene.get("preserve_constraints") or []),
        "transition_in": transition_public(str(scene.get("transition_in") or "")),
        "transition_out": transition_public(str(scene.get("transition_out") or "")),
        "duration_seconds": int(scene.get("duration_seconds") or SCENE_SECONDS),
        "aspect_ratio": str(state.get("aspect_ratio") or "9:16"),
        "prompt": public_prompt,
        "negative_prompt": "không đổi nhận diện, không đổi trang phục hoặc sản phẩm, không tạo logo/chữ giả, không cắt giữa hành động",
        "provider_prompt": internal_prompt,
        "provider_negative_prompt": internal_negative,
    }


def initialize_scene_artifacts(state: dict[str, Any], package: dict[str, Any]) -> dict[str, Any]:
    updated = normalize_state(state)
    scenes = [dict(item) for item in package.get("scenes") or []]
    prompt_rows = {int(item.get("scene_index") or 0): dict(item) for item in package.get("scene_prompts") or []}
    strategies: dict[str, Any] = {}
    image_versions: dict[str, Any] = {}
    video_versions: dict[str, Any] = {}
    for scene in scenes:
        index = int(scene.get("scene_index") or 0)
        key = str(index)
        strategies[key] = {"strategy": "direct_description", "approved": False}
        image_versions[key] = {"active_version": 1, "approved": False, "versions": [{"version": 1, **_image_prompt(scene, {**updated, "plan": package})}]}
        video_versions[key] = {"active_version": 1, "approved": False, "versions": [{"version": 1, **_video_prompt(scene, prompt_rows.get(index, {}), updated)}]}
    content_entries = dict(updated.get("content_affecting_addons") or {})
    voice_timing = {
        str(index): {
            "start_seconds": (index - 1) * SCENE_SECONDS,
            "end_seconds": index * SCENE_SECONDS,
            "approved": False,
        }
        for index in range(1, len(scenes) + 1)
    } if (content_entries.get("voiceover") or {}).get("enabled") else {}
    cta_placement = {
        str(len(scenes)): {"placement": "cuối cảnh", "approved": False}
    } if scenes and (content_entries.get("cta") or {}).get("enabled") else {}
    updated.update({
        "scene_plan": package,
        "plan": package,
        "continuity_contract": dict(package.get("continuity_contract") or {}),
        "image_strategy_per_scene": strategies,
        "image_prompt_versions": image_versions,
        "video_prompt_versions": video_versions,
        "transition_plan": [dict(item) for item in package.get("transitions") or []],
        "voice_timing_by_scene": voice_timing,
        "cta_placement_by_scene": cta_placement,
        "active_scene_index": 1,
        "quality_tier": 0,
        "quality_xu": 0,
        "estimate": {},
        "duration_estimate": {
            "scene_count": len(scenes),
            "seconds_per_scene": SCENE_SECONDS,
            "total_seconds": len(scenes) * SCENE_SECONDS,
        },
        "price_estimate": {},
        "final_report": {},
    })
    return updated


def replace_package(
    state: dict[str, Any],
    package: dict[str, Any],
    *,
    changed_scene_indices: set[int] | None = None,
) -> dict[str, Any]:
    """Replace a plan while retaining untouched per-scene prompt histories."""

    original = normalize_state(state)
    rebuilt = initialize_scene_artifacts(original, package)
    changed = {int(item) for item in (changed_scene_indices or set())}
    if not changed:
        return rebuilt
    for field in ("image_strategy_per_scene", "image_prompt_versions", "video_prompt_versions"):
        previous = dict(original.get(field) or {})
        current = dict(rebuilt.get(field) or {})
        for key, value in previous.items():
            try:
                index = int(key)
            except (TypeError, ValueError):
                continue
            if index not in changed and key in current:
                current[key] = deepcopy(value)
        rebuilt[field] = current
    return rebuilt


def set_scene_transition(
    state: dict[str, Any],
    *,
    scene_index: int,
    transition: str,
    remember: bool = True,
) -> dict[str, Any]:
    """Set one outgoing transition and refresh only affected prompt contracts."""

    updated = normalize_state(state)
    transition = str(transition or "")
    if transition not in TRANSITIONS:
        return updated
    plan = deepcopy(updated.get("plan") or {})
    scenes = [dict(item) for item in plan.get("scenes") or [] if isinstance(item, dict)]
    index = max(1, int(scene_index or 1))
    if index > len(scenes):
        return updated
    previous = str(scenes[index - 1].get("transition_out") or "")
    if remember and previous != transition:
        history = [dict(item) for item in updated.get("transition_history") or [] if isinstance(item, dict)]
        history.append({"scene_index": index, "transition": previous})
        updated["transition_history"] = history[-20:]
    scenes[index - 1]["transition_out"] = transition
    if index < len(scenes):
        scenes[index]["transition_in"] = transition
    plan["scenes"] = scenes
    transitions = [dict(item) for item in plan.get("transitions") or [] if isinstance(item, dict)]
    found = False
    public = transition_public(transition)
    for item in transitions:
        if int(item.get("from_scene") or 0) == index:
            item["transition_type"] = transition
            item["instruction"] = f"{public['label']}: {public['description']}"
            found = True
    if not found and index < len(scenes):
        transitions.append({
            "from_scene": index,
            "to_scene": index + 1,
            "transition_type": transition,
            "instruction": f"{public['label']}: {public['description']}",
        })
    plan["transitions"] = transitions
    package = video_scene_prompt_builder.build_prompt_package(plan)
    changed = {index, index + 1} if index < len(scenes) else {index}
    rebuilt = replace_package(updated, package, changed_scene_indices=changed)
    rebuilt["transition_history"] = list(updated.get("transition_history") or [])
    rebuilt["active_scene_index"] = index
    return rebuilt


def restore_scene_transition(state: dict[str, Any], *, scene_index: int) -> dict[str, Any]:
    updated = normalize_state(state)
    history = [dict(item) for item in updated.get("transition_history") or [] if isinstance(item, dict)]
    index = max(1, int(scene_index or 1))
    selected_position = next(
        (position for position in range(len(history) - 1, -1, -1) if int(history[position].get("scene_index") or 0) == index),
        -1,
    )
    if selected_position < 0:
        return updated
    previous = history.pop(selected_position)
    value = str(previous.get("transition") or ("kết thúc trọn vẹn" if index >= int(updated.get("scene_count") or 1) else "cut on action"))
    rebuilt = set_scene_transition(updated, scene_index=index, transition=value, remember=False)
    rebuilt["transition_history"] = history
    return rebuilt


def active_prompt(entry: dict[str, Any] | None) -> dict[str, Any]:
    entry = dict(entry or {})
    versions = [dict(item) for item in entry.get("versions") or [] if isinstance(item, dict)]
    active = int(entry.get("active_version") or (versions[-1].get("version") if versions else 0))
    return next((item for item in versions if int(item.get("version") or 0) == active), versions[-1] if versions else {})


def update_prompt(
    state: dict[str, Any],
    *,
    kind: str,
    scene_index: int,
    field: str,
    value: str,
) -> dict[str, Any]:
    updated = normalize_state(state)
    collection_name = "image_prompt_versions" if kind == "image" else "video_prompt_versions"
    collection = dict(updated.get(collection_name) or {})
    key = str(max(1, int(scene_index or 1)))
    entry = dict(collection.get(key) or {"active_version": 0, "approved": False, "versions": []})
    current = active_prompt(entry)
    version = max([int(item.get("version") or 0) for item in entry.get("versions") or []] + [0]) + 1
    new_value = {**current, field: str(value or "").strip(), "version": version}
    entry["versions"] = [dict(item) for item in entry.get("versions") or []] + [new_value]
    entry["active_version"] = version
    entry["approved"] = False
    collection[key] = entry
    updated[collection_name] = collection
    return updated


def regenerate_prompt(state: dict[str, Any], *, kind: str, scene_index: int) -> dict[str, Any]:
    updated = normalize_state(state)
    collection = updated["image_prompt_versions" if kind == "image" else "video_prompt_versions"]
    current = active_prompt(collection.get(str(scene_index)))
    field = "prompt"
    revision = len((collection.get(str(scene_index)) or {}).get("versions") or []) + 1
    text = str(current.get(field) or "")
    return update_prompt(updated, kind=kind, scene_index=scene_index, field=field, value=f"{text} Bản gợi ý {revision}: giữ trọn ý cảnh và nối mạch tự nhiên.")


def restore_prompt(state: dict[str, Any], *, kind: str, scene_index: int) -> dict[str, Any]:
    updated = normalize_state(state)
    name = "image_prompt_versions" if kind == "image" else "video_prompt_versions"
    collection = dict(updated.get(name) or {})
    key = str(scene_index)
    entry = dict(collection.get(key) or {})
    versions = [dict(item) for item in entry.get("versions") or []]
    active = int(entry.get("active_version") or 0)
    previous = [int(item.get("version") or 0) for item in versions if int(item.get("version") or 0) < active]
    if previous:
        entry["active_version"] = max(previous)
        entry["approved"] = False
        collection[key] = entry
        updated[name] = collection
    return updated


def approve_prompt(state: dict[str, Any], *, kind: str, scene_index: int) -> dict[str, Any]:
    updated = normalize_state(state)
    name = "image_prompt_versions" if kind == "image" else "video_prompt_versions"
    collection = dict(updated.get(name) or {})
    key = str(scene_index)
    entry = dict(collection.get(key) or {})
    entry["approved"] = True
    collection[key] = entry
    updated[name] = collection
    return updated


def all_prompts_approved(state: dict[str, Any], kind: str) -> bool:
    updated = normalize_state(state)
    name = "image_prompt_versions" if kind == "image" else "video_prompt_versions"
    count = max(1, int(updated.get("scene_count") or 1))
    return all(bool((updated.get(name) or {}).get(str(index), {}).get("approved")) for index in range(1, count + 1))


def scene_contract_counts(state: dict[str, Any]) -> dict[str, int]:
    updated = normalize_state(state)
    expected = max(1, int(updated.get("scene_count") or 1))
    return {
        "expected": expected,
        "scenes": len((updated.get("plan") or {}).get("scenes") or []),
        "image_strategies": len(updated.get("image_strategy_per_scene") or {}),
        "image_prompts": len(updated.get("image_prompt_versions") or {}),
        "video_prompts": len(updated.get("video_prompt_versions") or {}),
    }


def preconfirm_side_effects(state: dict[str, Any]) -> dict[str, int | bool]:
    state = normalize_state(state)
    return {
        "provider_called": bool(state.get("provider_called")),
        "image_provider_called": bool(state.get("image_provider_called")),
        "job_created": bool(state.get("job_created")),
        "outbox_created": bool(state.get("outbox_created")),
        "xu_charged": int(state.get("xu_charged") or 0),
        "wallet_mutations": int(state.get("wallet_mutations") or 0),
    }
