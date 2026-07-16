"""Provider-free state contract for the public SCENE3 video planner.

This module owns planning metadata only.  It must never create a job, write an
outbox row, call an image/video provider, or mutate a wallet.
"""

from __future__ import annotations

import unicodedata
from copy import deepcopy
from typing import Any

from services import (
    video_addon_planner,
    video_profile_catalog,
    video_scene_prompt_builder,
    video_semantic_scene_planner,
)


SCENE_SECONDS = 8
MIN_SCENES = 1
MAX_SCENES = 20

CANONICAL_STEPS = (
    "subject",
    "scene_count",
    "aspect_ratio",
    "technical_profile",
    "character",
    "image_source",
    "image_assets",
    "creative_controls",
    "requirements",
    "audio_plan",
    "scene_plan",
    "image_prompts",
    "video_prompts",
    "full_review",
    "quality",
    "final_report",
    "final_confirmation",
)

BACK_STEP = {
    "subject": "menu",
    "scene_count": "subject",
    "aspect_ratio": "scene_count",
    "technical_profile": "aspect_ratio",
    "character": "technical_profile",
    "image_source": "character",
    "image_assets": "image_source",
    "image_quote": "image_assets",
    "creative_controls": "image_source",
    "requirements": "creative_controls",
    "audio_plan": "requirements",
    "scene_plan": "audio_plan",
    "image_prompts": "scene_plan",
    "video_prompts": "scene_plan",
    "full_review": "video_prompts",
    "transitions": "full_review",
    "automatic_text": "full_review",
    "post_addons": "full_review",
    "quality": "full_review",
    "final_report": "quality",
    "final_confirmation": "final_report",
    # Canonical child screens. They never depend on incidental history order.
    "requirement_detail": "requirements",
    "creative_detail": "creative_controls",
    "creative_suggestions": "creative_controls",
    "materials": "image_source",
    "materials_manage": "image_assets",
    "image_strategy": "image_source",
    "content_addons": "requirements",
    "content_detail": "audio_plan",
    "content_suggestions": "audio_plan",
    "content_position": "audio_plan",
    "scene_detail": "scene_plan",
    "transition_picker": "transitions",
    "post_detail": "post_addons",
    "post_position": "post_detail",
    "post_volume": "post_detail",
    "automatic_text_detail": "automatic_text",
    "automatic_text_review": "automatic_text",
    "automatic_text_position": "automatic_text_review",
    "automatic_text_scope": "automatic_text_review",
    "automatic_text_timing": "automatic_text_review",
    "automatic_text_target": "automatic_text_review",
    "automatic_text_duration": "automatic_text_review",
    "automatic_text_animation": "automatic_text_review",
    "automatic_text_style": "automatic_text_review",
    "quality_guide": "quality",
    "logo_position": "post_detail",
    "await_count_custom": "scene_count",
    "await_profile_custom": "technical_profile",
    "await_character_description": "character",
    "await_material_upload": "image_assets",
    "await_material_caption": "materials_manage",
    "await_requirement": "requirement_detail",
    "await_creative": "creative_detail",
    "await_scene_edit": "scene_plan",
    "await_image_prompt": "image_prompts",
    "await_image_negative": "image_prompts",
    "await_video_prompt": "video_prompts",
    "await_video_negative": "video_prompts",
    "await_automatic_text": "automatic_text",
    "await_automatic_text_coordinates": "automatic_text_review",
    "await_automatic_text_timestamp": "automatic_text_review",
    "await_post_config": "post_detail",
    "await_post_text": "post_detail",
    "await_post_asset_upload": "post_detail",
    "await_post_volume": "post_volume",
}


def canonical_back_step(state: dict[str, Any] | None) -> str:
    """Return the public parent for a SCENE3 screen without history guessing."""

    current = dict(state or {})
    step = str(current.get("step") or "menu")
    if step == "profile_links":
        return "technical_profile"
    if step == "profile_suggestions":
        return "technical_profile"
    if step == "character" and str(current.get("primary_profile") or ""):
        return "profile_links"
    if step == "creative_controls" and str(current.get("image_source_mode") or "") in {"uploaded", "create"}:
        return "image_assets"
    if step == "video_prompts" and image_prompts_required(current):
        return "image_prompts"
    if step == "audio_plan" and str(current.get("audio_plan_return_step") or "") == "full_review":
        return "full_review"
    if step == "transitions":
        return "full_review"
    if step in {"automatic_text", "automatic_text_review"} and str(current.get("automatic_text_return_step") or "") == "full_review":
        return "full_review"
    if step == "post_addons":
        return "full_review"
    if step == "post_detail" and str(current.get("post_return_step") or "") in {"audio_plan", "full_review"}:
        return str(current.get("post_return_step"))
    if step == "automatic_text_scope" and not str(current.get("active_automatic_text_id") or ""):
        return "automatic_text"
    if step == "await_material_upload":
        return str(current.get("input_return_step") or "image_assets")
    if step in {"await_post_config", "await_post_text", "await_post_asset_upload"}:
        return str(current.get("input_return_step") or "post_detail")
    if step in {"await_image_prompt", "await_image_negative"}:
        return "image_prompts"
    if step in {"await_video_prompt", "await_video_negative"}:
        return "video_prompts"
    return str(BACK_STEP.get(step) or "menu")

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

# Content types remain internal planning metadata.  The public flow exposes the
# 14 concrete profiles only, then derives this taxonomy for prompt templates.
PROFILE_CONTENT_TYPE = {
    "architecture_exterior": "real_estate_fpv",
    "architecture_interior": "real_estate_fpv",
    "space_renovation": "real_estate_fpv",
    "real_estate_property": "real_estate_fpv",
    "architecture_walkthrough": "real_estate_fpv",
    "cinematic_vfx": "cinematic_trailer",
    "animation_2d_3d": "storytelling",
    "character": "storytelling",
    "fashion_lookbook": "fashion_lookbook",
    "product_3d_showcase": "product_review",
    "app_game_demo": "product_review",
    "website_saas_demo": "educational",
    "tutorial_explainer": "educational",
    "ugc_social_creator": "ugc_affiliate",
}

REQUIREMENT_CATEGORIES = (
    ("identity", "🧍 Nhân vật/nhận diện"),
    ("product", "📦 Sản phẩm"),
    ("brand_logo", "🏷 Phong cách thương hiệu"),
    ("colors", "🔒 Màu nhận diện"),
    ("materials", "🧱 Vật liệu"),
    ("environment", "🏞 Bối cảnh/kiến trúc"),
    ("wardrobe", "👗 Trang phục"),
    ("references", "🖼 Ảnh tham chiếu"),
)

# Public requirements describe what must remain consistent in generated
# scenes. Reference images are collected once in the following Materials step,
# so exposing them here would create the duplicate flow users reported.
PUBLIC_REQUIREMENT_CATEGORIES = tuple(
    item for item in REQUIREMENT_CATEGORIES if item[0] != "references"
)

REQUIREMENT_UPLOAD_TYPES = {
    "identity": "character_person",
    "product": "product_object",
    "brand_logo": "visual_style_reference",
    "colors": "visual_style_reference",
    "materials": "product_object",
    "environment": "background",
    "wardrobe": "character_person",
}

REQUIREMENT_SUGGESTION_TEMPLATES: dict[str, tuple[str, ...]] = {
    "identity": (
        "Giữ nguyên khuôn mặt, vóc dáng và đặc điểm nhận diện của {subject} trong mọi cảnh.",
        "Giữ cùng một nhân vật chính, độ tuổi, kiểu tóc và tỉ lệ cơ thể từ đầu đến cuối.",
        "Bám đúng ảnh nhân vật đã gửi; không tự đổi gương mặt, màu da hoặc đặc điểm riêng.",
        "Nếu đổi góc máy hoặc ánh sáng, nhận diện của nhân vật vẫn phải nhất quán.",
        "Không thêm nhân vật thay thế; mọi cảnh tiếp tục đúng chủ thể đã chọn.",
    ),
    "product": (
        "Giữ đúng hình dáng, màu, nhãn, chi tiết và tỉ lệ của sản phẩm trong {subject}.",
        "Không tự đổi bao bì, chất liệu, nút bấm hoặc đặc điểm nhận biết của sản phẩm.",
        "Sản phẩm luôn là chủ thể chính, đủ rõ để nhận ra ở cả cận cảnh và toàn cảnh.",
        "Bám đúng ảnh sản phẩm đã gửi; không tạo chữ hoặc logo giả trên bề mặt.",
        "Giữ kích thước sản phẩm hợp lý so với tay người, đồ vật và không gian xung quanh.",
    ),
    "brand_logo": (
        "Giữ đúng màu chủ đạo, tinh thần và dấu hiệu nhận diện của thương hiệu trong mọi cảnh.",
        "Không tự sáng tác tên, biểu tượng hoặc khẩu hiệu thương hiệu chưa được cung cấp.",
        "Bao bì, bảng hiệu và chi tiết nhận diện phải cùng một hệ thiết kế xuyên suốt.",
        "Dùng đúng ngôn ngữ hình ảnh của thương hiệu: {profile}; không pha phong cách trái ngược.",
        "Logo hình ảnh chỉ được nhận ở bước Hậu kỳ; phần này chỉ giữ nhận diện trong nội dung cảnh.",
    ),
    "colors": (
        "Giữ bảng màu chủ đạo nhất quán từ cảnh đầu tới cảnh cuối.",
        "Màu da, màu sản phẩm và màu thương hiệu phải chân thật, không đổi bất thường.",
        "Các cảnh khác bối cảnh vẫn dùng chung tông màu và mức tương phản đã chọn.",
        "Ánh sáng có thể thay đổi theo câu chuyện nhưng không làm sai màu nhận diện.",
        "Ưu tiên tối đa ba màu chính để video liền mạch và dễ nhìn.",
    ),
    "materials": (
        "Giữ đúng chất liệu, bề mặt, độ bóng và cấu tạo đã mô tả.",
        "Gỗ, đá, kim loại, vải hoặc kính phải có kết cấu nhất quán giữa các cảnh.",
        "Không biến đổi vật liệu khi camera đổi góc hoặc khi ánh sáng thay đổi.",
        "Bám sát ảnh chi tiết đã gửi, đặc biệt ở cận cảnh sản phẩm hoặc kiến trúc.",
        "Không thêm hoa văn, vết nứt hoặc chi tiết bề mặt ngoài yêu cầu.",
    ),
    "environment": (
        "Giữ logic kiến trúc, vị trí đồ vật và hướng không gian giữa các cảnh.",
        "Cảnh sau tiếp nối đúng cửa, lối đi, nội thất và hướng di chuyển của cảnh trước.",
        "Không tự đổi thời tiết, thời điểm hoặc vị trí nếu câu chuyện chưa chuyển bối cảnh.",
        "Bám đúng ảnh bối cảnh đã gửi; giữ tỉ lệ và cấu trúc không gian hợp lý.",
        "Mọi thay đổi bối cảnh phải có điểm chuyển rõ và phục vụ đúng mạch nội dung.",
    ),
    "wardrobe": (
        "Giữ nguyên trang phục, phụ kiện và kiểu tóc trừ khi kịch bản yêu cầu thay đổi.",
        "Màu, chất liệu và họa tiết trang phục không được đổi giữa hai cảnh liên tiếp.",
        "Trang phục phải phù hợp nhân vật, bối cảnh và hành động trong {subject}.",
        "Bám đúng ảnh trang phục đã gửi; không thêm chữ hoặc biểu tượng ngoài yêu cầu.",
        "Nếu có thay trang phục, phải kết thúc một nhịp nội dung rồi mới chuyển sang diện mạo mới.",
    ),
    "references": (
        "Bám sát ảnh tham chiếu đã gửi; không dùng tài sản của người dùng khác.",
        "Chỉ dùng ảnh tham chiếu thuộc đúng phiên hiện tại.",
        "Giữ các chi tiết chính đã đánh dấu trong ảnh tham chiếu.",
        "Không suy diễn logo, chữ hoặc vật thể không có trong ảnh.",
        "Dùng ảnh làm chuẩn nhận diện, không sao chép nội dung riêng của người khác.",
    ),
}

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

# The public Materials screen is a single reference-image intake. AI image
# planning belongs to Image Strategy/Prompts; logo, voice and music belong to
# their concrete post-production add-ons.
PUBLIC_MATERIAL_TYPES = tuple(
    item for item in MATERIAL_TYPES
    if item[0] in {
        "character_person", "product_object", "background",
        "visual_style_reference", "storyboard_frames",
    }
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

AUTOMATIC_TEXT_FIXED_POSITIONS = (
    ("top_left", "↖️ Trên trái"),
    ("top_center", "⬆️ Trên giữa"),
    ("top_right", "↗️ Trên phải"),
    ("middle_left", "⬅️ Giữa trái"),
    ("center", "⏺ Giữa"),
    ("middle_right", "➡️ Giữa phải"),
    ("bottom_left", "↙️ Dưới trái"),
    ("bottom_center", "⬇️ Dưới giữa"),
    ("bottom_right", "↘️ Dưới phải"),
)

CHARACTER_MODES = (
    ("male", "👨 Nhân vật nam"),
    ("female", "👩 Nhân vật nữ"),
    ("auto", "🤖 Tự xác định từ mô tả"),
    ("none", "🧑 Không có nhân vật chính"),
    ("uploaded", "📎 Gửi ảnh nhân vật"),
    ("custom", "✍️ Tự nhập mô tả"),
)

IMAGE_SOURCE_MODES = (
    ("uploaded", "📎 Gửi ảnh có sẵn"),
    ("create", "✨ Tạo ảnh mới"),
    ("description", "📝 Chỉ dùng mô tả"),
    ("none", "🎞️ Không cần ảnh"),
)

CREATIVE_CONTROLS = (
    ("context", "🧭 Chủ đề/ngữ cảnh"),
    ("colors", "🎨 Bảng màu & ánh sáng"),
    ("visual_style", "🖼 Phong cách hình ảnh"),
    ("motion", "🏃 Chuyển động"),
    ("camera", "🎥 Góc máy"),
    ("pacing", "⏱ Nhịp dựng"),
    ("emotion", "💭 Cảm xúc"),
    ("negative", "🚫 Điều cần tránh"),
)

FIELD_SUGGESTION_PAGE_SIZE = 5
FIELD_SUGGESTION_VARIANTS = (
    "",
    " Ưu tiên tính nhất quán từ cảnh đầu đến cảnh cuối.",
    " Điều chỉnh bố cục phù hợp tỉ lệ {aspect_ratio} và vùng an toàn.",
    " Phân bổ rõ cho {scene_count} cảnh, mỗi cảnh hoàn tất một ý hoặc hành động.",
)

CREATIVE_QUICK_PRESETS = (
    ("Chân thật tự nhiên", {"visual_style": "chân thật tự nhiên", "motion": "chuyển động nhẹ", "camera": "camera theo chủ thể", "pacing": "nhịp vừa"}),
    ("Điện ảnh cảm xúc", {"visual_style": "điện ảnh cảm xúc", "motion": "chuyển động có chủ đích", "camera": "lia và tiến máy mượt", "pacing": "nhịp cảm xúc"}),
    ("Quảng cáo rõ sản phẩm", {"visual_style": "quảng cáo sạch, rõ sản phẩm", "motion": "chuyển động làm nổi lợi ích", "camera": "cận chi tiết rồi mở rộng", "pacing": "hook nhanh, kết rõ"}),
    ("Sang trọng tối giản", {"visual_style": "sang trọng tối giản", "motion": "chuyển động chậm có kiểm soát", "camera": "mở lộ sản phẩm", "pacing": "chậm và tinh tế"}),
)

CREATIVE_SUGGESTIONS: dict[str, tuple[str, ...]] = {
    "context": (
        "Mở bằng vấn đề người xem đang gặp, phát triển bằng hành động và kết bằng kết quả rõ ràng",
        "Mở bằng khoảnh khắc đời thật, theo chủ thể qua từng nhịp rồi khép lại tự nhiên",
        "Mở bằng kết quả nổi bật, quay lại nguyên nhân và trở về thành quả ở cảnh cuối",
        "Mở bằng câu hỏi ngắn, mỗi cảnh trả lời trọn một ý và kết bằng lời mời hành động",
        "Mở bằng tương phản trước và sau, giữ mạch thay đổi liên tục giữa các cảnh",
    ),
    "colors": (
        "Tự nhiên sáng, màu trung tính, da người và sản phẩm chân thật",
        "Xanh ngọc và trắng sạch, tương phản gọn, cảm giác hiện đại",
        "Vàng ấm và nâu gỗ, ánh sáng gần gũi, cảm giác đáng tin",
        "Đen và vàng điện ảnh, nền sâu, điểm sáng sang trọng",
        "Pastel dịu, bão hòa thấp, ánh sáng mềm và tinh tế",
    ),
    "visual_style": (
        "Chân thật tự nhiên, chi tiết rõ, phù hợp nội dung đời thường",
        "Điện ảnh cảm xúc, chiều sâu tốt, ánh sáng có chủ đích",
        "Quảng cáo sạch, chủ thể nổi bật, lợi ích sản phẩm dễ nhìn",
        "Sang trọng tối giản, ít chi tiết thừa, bố cục cao cấp",
        "Năng động mạng xã hội, mở đầu bắt mắt nhưng vẫn giữ nội dung rõ",
    ),
    "motion": (
        "Chuyển động nhẹ và ổn định, chủ thể luôn rõ",
        "Theo chủ thể mượt, hoàn tất hành động trước khi chuyển cảnh",
        "Tiến gần chi tiết rồi mở rộng để thấy toàn cảnh",
        "Chuyển động theo nhịp nội dung, không cắt giữa hành động",
        "Ít chuyển động, ưu tiên vẻ sang trọng và khả năng quan sát",
    ),
    "camera": (
        "Góc ngang tầm mắt, tự nhiên và dễ gần",
        "Cận chi tiết rồi chuyển sang trung cảnh để thấy ngữ cảnh",
        "Toàn cảnh mở đầu, trung cảnh phát triển, cận cảnh kết thúc",
        "Theo sau chủ thể với khoảng cách ổn định",
        "Góc thấp nhẹ để tạo cảm giác nổi bật nhưng không méo hình",
    ),
    "pacing": (
        "Nhịp vừa, mỗi cảnh đủ mở đầu, phát triển và kết thúc",
        "Mở nhanh để giữ chú ý, phần giữa rõ ràng, cảnh cuối chậm lại",
        "Chậm và cảm xúc, ưu tiên quan sát chi tiết",
        "Theo nhịp lời dẫn, không cắt giữa câu hoặc giữa hành động",
        "Dồn nhịp có kiểm soát, kết mỗi cảnh bằng một điểm chuyển tự nhiên",
    ),
    "emotion": (
        "Gần gũi và đáng tin",
        "Tò mò rồi thỏa mãn khi thấy kết quả",
        "Sang trọng, bình tĩnh và tinh tế",
        "Tươi vui, tích cực và giàu năng lượng",
        "Cảm xúc chân thành, kết thúc ấm áp",
    ),
    "negative": (
        "Không đổi khuôn mặt, trang phục, sản phẩm hoặc màu thương hiệu",
        "Không méo tay, méo chữ, sai logo hoặc thêm vật thể ngoài yêu cầu",
        "Không rung giật, nhấp nháy, đổi ánh sáng vô lý hoặc cắt giữa chuyển động",
        "Không che chủ thể bằng chữ, phụ đề, logo hoặc dấu bản quyền",
        "Không nhồi nhiều ý trong một cảnh và không chuyển bối cảnh đột ngột",
    ),
}

PROFILE_CREATIVE_GUIDANCE: dict[str, dict[str, str]] = {
    "architecture_exterior": {"focus": "giữ đúng tỉ lệ công trình và cảnh quan", "camera": "đường thẳng đứng chuẩn, góc rộng không méo", "visual": "vật liệu và ánh sáng ngoại thất chân thật", "motion": "camera tiến hoặc lia chậm quanh công trình", "avoid": "không cong tường, đổi cửa hoặc sai tầng"},
    "architecture_interior": {"focus": "giữ đúng bố cục phòng và vị trí nội thất", "camera": "camera ngang tầm mắt, đường dọc thẳng", "visual": "ánh sáng phòng tự nhiên và vật liệu rõ", "motion": "đi máy chậm theo lối di chuyển thật", "avoid": "không đổi đồ đạc hoặc làm sai diện tích"},
    "space_renovation": {"focus": "làm rõ hiện trạng, thay đổi và thành quả", "camera": "giữ cùng góc trước và sau", "visual": "vật liệu mới rõ nhưng không làm sai kết cấu", "motion": "chuyển đổi có điểm đầu và kết quả rõ", "avoid": "không biến đổi bố cục ngoài phạm vi cải tạo"},
    "real_estate_property": {"focus": "dẫn người xem theo hành trình xem nhà", "camera": "góc rộng vừa đủ, không kéo méo không gian", "visual": "ánh sáng chân thật, làm rõ tiện ích", "motion": "đi máy ổn định qua từng khu vực", "avoid": "không thêm phòng, nội thất hoặc tầm nhìn không có"},
    "architecture_walkthrough": {"focus": "giữ một tuyến tham quan liên tục", "camera": "hướng camera khớp lối đi giữa các cảnh", "visual": "không gian nhất quán theo từng phòng", "motion": "chuyển động tiến liên tục, dừng đúng điểm nổi bật", "avoid": "không nhảy vị trí hoặc quay ngược hướng vô lý"},
    "cinematic_vfx": {"focus": "mỗi hiệu ứng phục vụ một nhịp câu chuyện", "camera": "camera có chủ đích và điểm dừng rõ", "visual": "điện ảnh nhưng chủ thể vẫn dễ nhận ra", "motion": "hiệu ứng hoàn tất trước điểm cắt", "avoid": "không lạm dụng lóe sáng, rung hoặc biến dạng"},
    "animation_2d_3d": {"focus": "giữ thiết kế nhân vật và thế giới hoạt hình", "camera": "góc máy rõ hình khối và hành động", "visual": "nét, vật liệu và tỉ lệ nhất quán", "motion": "chuyển động có nhịp và hoàn tất tư thế", "avoid": "không đổi model, màu hoặc phong cách giữa cảnh"},
    "character": {"focus": "giữ nhân vật, cảm xúc và mục tiêu xuyên suốt", "camera": "ưu tiên gương mặt và ngôn ngữ cơ thể", "visual": "nhận diện, trang phục và ánh sáng nhất quán", "motion": "hành động trọn vẹn trước khi chuyển cảnh", "avoid": "không đổi mặt, tay, trang phục hoặc tuổi"},
    "fashion_lookbook": {"focus": "làm rõ trang phục, phom dáng và thần thái", "camera": "toàn thân, trung cảnh rồi cận chi tiết", "visual": "màu vải và chất liệu trung thực", "motion": "bước đi hoặc tạo dáng hoàn tất tự nhiên", "avoid": "không đổi trang phục, cơ thể hoặc họa tiết"},
    "product_3d_showcase": {"focus": "mỗi cảnh làm rõ một lợi ích hoặc chi tiết sản phẩm", "camera": "cận chi tiết rồi mở ra toàn sản phẩm", "visual": "bề mặt sạch, màu và nhãn chính xác", "motion": "xoay hoặc mở lộ sản phẩm có kiểm soát", "avoid": "không méo sản phẩm, sai chữ hoặc thêm bộ phận"},
    "app_game_demo": {"focus": "mỗi cảnh trình bày một thao tác và kết quả", "camera": "khung giao diện dễ đọc, nhấn đúng vùng tương tác", "visual": "giao diện nhất quán và chữ rõ", "motion": "thao tác hoàn tất rồi mới sang bước kế", "avoid": "không tạo màn hình hoặc tính năng không tồn tại"},
    "website_saas_demo": {"focus": "đi theo vấn đề, thao tác và kết quả trên sản phẩm", "camera": "zoom vừa đủ vào vùng giao diện cần xem", "visual": "giao diện sạch, đúng màu thương hiệu", "motion": "con trỏ và chuyển trang có nhịp rõ", "avoid": "không sửa nội dung, số liệu hoặc chức năng thật"},
    "tutorial_explainer": {"focus": "mỗi cảnh giải thích trọn một bước", "camera": "ưu tiên vật thể hoặc thao tác đang được hướng dẫn", "visual": "đơn giản, dễ đọc và có thứ tự", "motion": "hoàn tất thao tác trước khi chuyển bước", "avoid": "không bỏ bước, cắt giữa câu hoặc nhồi nhiều ý"},
    "ugc_social_creator": {"focus": "giữ cảm giác đời thật nhưng thông điệp rõ", "camera": "góc điện thoại tự nhiên, chủ thể luôn nhìn rõ", "visual": "ánh sáng chân thật, ít dàn dựng", "motion": "hành động gần gũi, kết thúc tự nhiên", "avoid": "không diễn quá mức, thay mặt hoặc làm sai sản phẩm"},
}

CONTENT_ADDONS = (
    ("voiceover", "Legacy voice request"),
    ("captions", "Legacy caption request"),
    ("cta", "Legacy CTA request"),
    ("scene_text", "Legacy scene text request"),
    ("logo_safe_zone", "🏷 Chừa vùng logo"),
    ("watermark_safe_zone", "🔖 Chừa vùng dấu bản quyền"),
    ("preserve_source_audio", "🔊 Giữ âm thanh gốc"),
    ("music_mood", "Legacy music intent"),
    ("transition_style", "🔗 Kiểu chuyển cảnh"),
    ("target_duration", "⏳ Thời lượng mục tiêu"),
)

# Logo/watermark are configured with the real asset/text in Post-production;
# transitions have their own per-boundary step; duration is already fixed by
# the scene count. Keeping them out of this public list removes three duplicate
# configuration paths while preserving old session fields internally.
# Kept only to read old sessions. Public SCENE3 uses AUDIO_PLANNING_ADDONS and
# the canonical post-production entries below, so no setting has two owners.
PUBLIC_CONTENT_ADDONS: tuple[tuple[str, str], ...] = ()

AUDIO_PLANNING_ADDONS = (
    ("dubbing", "🎙️ Lồng tiếng"),
    ("subtitles", "💬 Phụ đề"),
    ("source_audio", "🔊 Âm thanh gốc"),
    ("music", "🎵 Nhạc nền"),
    ("sfx", "💥 Hiệu ứng âm thanh"),
)

CONTENT_ADDON_SUGGESTIONS: dict[str, tuple[str, ...]] = {
    "voiceover": (
        "Lời dẫn ngắn, mỗi cảnh một câu trọn ý và vừa trong khoảng 8 giây",
        "Lời kể tự nhiên, mở vấn đề rồi dẫn người xem tới kết quả",
        "Giọng giới thiệu rõ lợi ích, cảnh cuối có lời mời hành động",
        "Lời dẫn cảm xúc, có khoảng nghỉ tự nhiên giữa các cảnh",
        "Chỉ dùng lời ở các cảnh cần thiết, ưu tiên hình ảnh tự kể chuyện",
    ),
    "captions": (
        "Phụ đề tối đa 2 dòng, ngắn gọn và chừa vùng an toàn phía dưới",
        "Chỉ hiện từ khóa chính, không che mặt hoặc sản phẩm",
        "Mỗi cảnh một câu ngắn, đồng bộ với lời dẫn",
        "Phụ đề dễ đọc trên điện thoại, tương phản rõ với nền",
        "Không dùng phụ đề ở cảnh chỉ cần âm thanh và hình ảnh",
    ),
    "cta": (
        "Đặt lời kêu gọi hành động ở cảnh cuối sau khi đã cho thấy kết quả",
        "Mời người xem nhắn tin để nhận tư vấn",
        "Mời người xem xem thêm thông tin hoặc sản phẩm",
        "Mời người xem lưu video và theo dõi phần tiếp theo",
        "Kết nhẹ bằng tên thương hiệu, không dùng lời thúc ép",
    ),
    "scene_text": (
        "Mỗi cảnh một tiêu đề ngắn từ 3 đến 7 từ",
        "Chỉ hiện số bước hoặc tên khu vực ở đầu cảnh",
        "Dùng chữ để nhấn một lợi ích chính, không lặp lời dẫn",
        "Cảnh mở đầu có tiêu đề, cảnh cuối có kết luận",
        "Không thêm chữ nếu hình ảnh đã truyền đạt đủ ý",
    ),
    "preserve_source_audio": (
        "Giữ âm thanh gốc rõ, chỉ hạ nhẹ khi có lời dẫn",
        "Ưu tiên tiếng môi trường tự nhiên của từng cảnh",
        "Giữ tiếng nói gốc, giảm tạp âm ở phần không cần thiết",
        "Giữ âm thanh gốc ở cảnh hành động, tắt ở cảnh chuyển",
        "Chỉ dùng âm thanh gốc khi chất lượng đủ rõ",
    ),
    "music_mood": (
        "Nhạc nhẹ, hiện đại, tăng dần theo mạch nội dung",
        "Nhạc sang trọng tối giản, không lấn lời nói",
        "Nhạc tích cực, nhịp vừa, phù hợp video bán hàng",
        "Nhạc cảm xúc, mở nhẹ và kết ấm",
        "Không dùng nhạc; ưu tiên lời nói và âm thanh gốc",
    ),
    "transition_style": (
        "Chuyển tự nhiên theo trạng thái kết của cảnh trước",
        "Nối theo cùng hướng chuyển động của chủ thể",
        "Chuyển mềm bằng bố cục hoặc màu sắc tương đồng",
        "Cắt gọn sau khi hành động và camera đã hoàn tất",
        "Dùng chuyển cảnh tối giản, không thêm hiệu ứng gây rối",
    ),
    "target_duration": (
        "Giữ đủ khoảng 8 giây cho mỗi cảnh",
        "Ưu tiên kết thúc trọn ý, không kéo dài cảnh chỉ để đủ thời lượng",
        "Lời dẫn phải kết thúc trước điểm chuyển cảnh",
        "Cảnh hành động được dùng đủ thời gian để hoàn tất chuyển động",
        "Cảnh tĩnh có thể ngắn hơn nếu ý đã hoàn chỉnh",
    ),
}

POST_ADDONS = (
    ("logo_image", "🏷 Logo hình ảnh"),
    ("watermark_text", "🔖 Dấu bản quyền chữ"),
    ("watermark_image", "🖼 Dấu bản quyền hình"),
    ("subtitles", "💬 Phụ đề"),
    ("dubbing", "🎙 Lồng tiếng"),
    ("music", "🎵 Nhạc nền"),
    ("sfx", "🔊 Hiệu ứng âm thanh"),
    ("source_audio", "🔊 Âm thanh gốc"),
    ("automatic_text", "📝 Chữ trên video"),
    # Legacy read-only fields. normalize_state migrates them into the owners
    # above and the public keyboard never exposes these entries.
    ("voice", "Giọng đọc cũ"),
    ("text_overlay", "Chữ hiển thị cũ"),
    ("audio_balance", "🎚 Cân bằng âm thanh"),
    ("mp4_export", "📦 Xuất MP4"),
)

# Keep the legacy data contract intact while presenting a smaller public menu.
# A picture watermark duplicates the logo flow, and MP4 is the mandatory final
# output rather than an optional add-on.
PUBLIC_POST_ADDONS = tuple(
    item for item in POST_ADDONS
    if item[0] in {"logo_image", "watermark_text"}
)

PUBLIC_CONFIGURABLE_POST_ADDONS = tuple(
    item for item in POST_ADDONS
    if item[0] in {
        "logo_image",
        "watermark_text",
        "subtitles",
        "dubbing",
        "music",
        "sfx",
        "source_audio",
    }
)

AUDIO_POST_ADDONS = frozenset({"dubbing", "music", "sfx", "source_audio"})
AUDIO_VOLUME_LEVELS = (0, 25, 50, 75, 100, 125, 150, 175, 200)
VOICE_CHOICES: dict[str, dict[str, Any]] = {
    "default_female": {
        "voice_type": "female",
        "voice_source": "approved_default",
        "custom_voice_required": False,
    },
    "default_male": {
        "voice_type": "male",
        "voice_source": "approved_default",
        "custom_voice_required": False,
    },
    "custom_voice": {
        "voice_type": "custom_voice",
        "voice_source": "user_or_saved_asset",
        "custom_voice_required": True,
    },
    "follow_character": {
        "voice_type": "follow_character",
        "voice_source": "grounded_character",
        "custom_voice_required": False,
    },
}
MUSIC_SOURCE_CHOICES: dict[str, dict[str, Any]] = {
    "choose_existing": {
        "source": "approved_library_or_user_asset",
        "paid_generation": False,
        "generation_planned_only": False,
    },
    "create_new": {
        "source": "planned_generation",
        "paid_generation": True,
        "generation_planned_only": True,
    },
}
MUSIC_VOCAL_MODES = frozenset({"instrumental", "with_lyrics"})

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
        "voice_type": "not_selected",
        "voice_choice": "",
        "dialogue_text": "",
        "timing": "fit_scene",
        "source_audio_policy": "duck",
        "volume_percent": 100,
        "peak_guard": True,
        "applied_to_mp4": False,
    },
    "music": {
        "source": "not_selected",
        "vocal_mode": "instrumental",
        "music_request": "",
        "volume_percent": 20,
        "trim_mode": "fit_video",
        "fade_in": True,
        "fade_out": True,
        "ducking": True,
        "peak_guard": True,
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
        "peak_guard": True,
        "user_note": "",
        "applied_to_mp4": False,
    },
    "source_audio": {
        "source": "original_video_audio",
        "volume_percent": 100,
        "duck_under_dubbing": True,
        "peak_guard": True,
        "applied_to_mp4": False,
    },
    "automatic_text": {
        "owner": "automatic_text_items",
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
    ("description", "📝 Chỉ dùng mô tả"),
    ("uploaded", "📎 Dùng ảnh đã gửi"),
    ("create", "✨ Lập kế hoạch tạo ảnh mới"),
    ("none", "🎞️ Không cần ảnh"),
)

AUTOMATIC_TEXT_TYPES = (
    ("scene_title", "🏷️ Tiêu đề cảnh"),
    ("character_intro", "👤 Giới thiệu nhân vật"),
    ("product_label", "📦 Nhãn sản phẩm"),
    ("highlight", "💡 Điểm nổi bật"),
    ("cta", "📣 Kêu gọi hành động"),
    ("annotation", "💬 Chú thích ngắn"),
    ("tracked_label", "📍 Chữ theo người/vật"),
    ("data_info", "🔢 Số liệu/thông tin"),
    ("footer_source", "🧾 Chân trang/nguồn"),
    ("custom", "📝 Chữ tự nhập"),
)

AUTOMATIC_TEXT_POSITIONS = (
    ("auto_safe", "✨ Tự chọn vị trí an toàn"),
    *AUTOMATIC_TEXT_FIXED_POSITIONS,
    ("custom_coordinates", "✍️ Tự nhập tọa độ"),
)

AUTOMATIC_TEXT_TIMINGS = (
    ("scene_start", "Đầu cảnh"),
    ("scene_end", "Cuối cảnh"),
    ("character_appears", "Khi nhân vật xuất hiện"),
    ("product_appears", "Khi sản phẩm xuất hiện"),
    ("after_dialogue", "Sau một câu thoại"),
    ("timestamp", "Theo thời điểm"),
    ("whole_scene", "Theo toàn cảnh"),
)

AUTOMATIC_TEXT_ANIMATIONS = (
    ("none", "Không chuyển động"),
    ("fade", "Mờ dần"),
    ("slide_soft", "Trượt nhẹ"),
    ("zoom_soft", "Phóng nhẹ"),
    ("pop_soft", "Bật lên nhẹ"),
    ("typewriter", "Gõ chữ"),
)

AUTOMATIC_TEXT_TARGETS = (
    ("person", "Theo người"),
    ("face", "Theo khuôn mặt"),
    ("product", "Theo sản phẩm"),
    ("object", "Theo vật thể"),
    ("fixed", "Vùng cố định an toàn"),
)

AUTOMATIC_TEXT_DURATIONS = (
    (2, "2 giây"),
    (3, "3 giây"),
    (4, "4 giây"),
    (5, "5 giây"),
    (SCENE_SECONDS, "Hết cảnh"),
)

AUTOMATIC_TEXT_STYLES = (
    "Tối giản", "Điện ảnh", "Công nghệ", "Bán hàng",
    "UGC", "Giáo dục", "Trẻ em", "Cao cấp", "Thẻ giới thiệu nhân vật",
)

# This flow has no object detector/tracker in the planning runtime. The public
# UI must therefore describe a fixed safe position instead of offering a fake
# tracking control.
AUTOMATIC_TEXT_TRACKING_AVAILABLE = False

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


def _safe_nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


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
        "custom_technical_profile": "",
        "technical_profile_history": [],
        "suggested_technical_profile": "",
        "technical_profile_suggestion_offset": 0,
        "show_all_technical_profiles": False,
        "primary_profile": "",
        "linked_profiles": [],
        "profile_page": 1,
        "profile_suggestion_keys": [],
        "profile_bundle_version": video_profile_catalog.SCHEMA_VERSION,
        "context": "",
        "profile_context": "",
        "suggestions": [],
        "suggestion_version": 0,
        "suggestion_history": [],
        "selected_suggestion": {},
        "character_config": {
            "mode": "",
            "gender": "",
            "gender_grounded": False,
            "description": "",
            "history": [],
        },
        "image_source_mode": "",
        "image_source_history": [],
        "image_generation_confirmed": False,
        "image_generation_quote": {},
        "preservation_requirements": _entry_map(REQUIREMENT_CATEGORIES),
        "requirements": {},
        "reference_assets": {},
        "assets": {},
        "creative_controls": _entry_map(CREATIVE_CONTROLS),
        "field_suggestion_offsets": {},
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
        "automatic_text_items": [],
        "automatic_text_history": [],
        "automatic_text_tracking_available": AUTOMATIC_TEXT_TRACKING_AVAILABLE,
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
        "music_provider_calls": 0,
        "voice_provider_calls": 0,
        "files_generated": 0,
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
    profile_state = dict(base)
    if "profile_bundle_version" not in raw:
        profile_state["profile_bundle_version"] = 0
    base.update(video_profile_catalog.migrate_session_profile_state(profile_state))
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
        "character_config", "image_generation_quote",
    ):
        base[field] = dict(base.get(field) or {})
    base["field_suggestion_offsets"] = {
        str(key): _safe_nonnegative_int(value)
        for key, value in dict(base.get("field_suggestion_offsets") or {}).items()
        if str(key or "")
    }
    base["transition_plan"] = [dict(item) for item in base.get("transition_plan") or [] if isinstance(item, dict)]
    base["idea_scene_beats"] = [dict(item) for item in base.get("idea_scene_beats") or [] if isinstance(item, dict)][:MAX_SCENES]
    base["suggestions"] = [dict(item) for item in base.get("suggestions") or [] if isinstance(item, dict)][:5]
    base["suggestion_history"] = [list(items) for items in base.get("suggestion_history") or [] if isinstance(items, list)][-5:]
    base["content_type_history"] = [str(item) for item in base.get("content_type_history") or [] if content_type(str(item))][-10:]
    valid_profiles = (
        {key for key, _label in TECHNICAL_PROFILES}
        | set(video_profile_catalog.PROFILE_BY_KEY)
        | {"custom"}
    )
    base["technical_profile_history"] = [
        str(item)
        for item in base.get("technical_profile_history") or []
        if (
            not item
            or str(item) in valid_profiles
            or video_profile_catalog.PROFILE_KEY_RE.fullmatch(str(item))
        )
    ][-10:]
    base["linked_profiles"] = [
        str(item)
        for item in base.get("linked_profiles") or []
        if str(item) and str(item) != str(base.get("primary_profile") or "")
    ][:video_profile_catalog.MAX_LINKED_PROFILES]
    base["post_addon_suggestion"] = [str(item) for item in base.get("post_addon_suggestion") or [] if str(item) in dict(POST_ADDONS)]
    base["automatic_text_items"] = [
        dict(item) for item in base.get("automatic_text_items") or [] if isinstance(item, dict)
    ][:40]
    base["automatic_text_history"] = [
        list(items) for items in base.get("automatic_text_history") or [] if isinstance(items, list)
    ][-10:]
    base["image_source_history"] = [
        str(item) for item in base.get("image_source_history") or []
        if str(item) in dict(IMAGE_SOURCE_MODES)
    ][-10:]
    if str(base.get("image_source_mode") or "") not in dict(IMAGE_SOURCE_MODES):
        base["image_source_mode"] = ""
    character = dict(base.get("character_config") or {})
    character.setdefault("mode", "")
    character.setdefault("gender", "")
    character.setdefault("gender_grounded", False)
    character.setdefault("description", "")
    character["history"] = [dict(item) for item in character.get("history") or [] if isinstance(item, dict)][-10:]
    base["character_config"] = character
    # Migrate old public owners once. The legacy fields stay readable but are
    # never rendered as a second configuration path.
    post_entries = dict(base.get("postproduction_addons") or {})
    legacy_voice = dict(post_entries.get("voice") or {})
    dubbing = dict(post_entries.get("dubbing") or {})
    if legacy_voice.get("enabled") and not dubbing.get("enabled"):
        legacy_value = dict(legacy_voice.get("value") or {}) if isinstance(legacy_voice.get("value"), dict) else {}
        dubbing_value = dict(dubbing.get("value") or {}) if isinstance(dubbing.get("value"), dict) else post_addon_default("dubbing")
        dubbing_value.update({
            "voice_choice": str(legacy_value.get("voice_choice") or ""),
            "voice_type": str(legacy_value.get("voice_type") or "not_selected"),
            "voice_source": str(legacy_value.get("voice_source") or "not_selected"),
            "dialogue_text": str(legacy_value.get("script_note") or ""),
            "volume_percent": int(legacy_value.get("volume_percent") or 100),
        })
        dubbing.update({"enabled": True, "value": dubbing_value})
        post_entries["dubbing"] = dubbing
    base["postproduction_addons"] = post_entries
    base["scene_count"] = max(0, min(MAX_SCENES, int(base.get("scene_count") or 0)))
    base["provider_called"] = False
    base["image_provider_called"] = False
    base["music_provider_calls"] = 0
    base["voice_provider_calls"] = 0
    base["files_generated"] = 0
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


def content_type_for_profile(profile_id: str, state: dict[str, Any] | None = None) -> str:
    """Derive internal story taxonomy from the selected public profile."""

    canonical = video_profile_catalog.canonical_profile_key(profile_id)
    if canonical:
        return video_profile_catalog.content_type_for_profile(canonical)
    mapped = str(PROFILE_CONTENT_TYPE.get(str(profile_id or "")) or "")
    if mapped:
        return mapped
    return suggested_content_type(dict(state or {}))


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
    suggestions: list[str] = []
    post_entries = dict(state.get("postproduction_addons") or {})
    assets = [dict(item) for item in (state.get("reference_assets") or {}).get("items") or [] if isinstance(item, dict)]
    if any(str(item.get("type") or "") == "logo" for item in assets):
        suggestions.append("logo_image")
    if (post_entries.get("subtitles") or {}).get("enabled"):
        suggestions.append("subtitles")
    if (post_entries.get("dubbing") or {}).get("enabled"):
        suggestions.append("dubbing")
    if any(str(item.get("type") or "") == "music" for item in assets):
        suggestions.extend(["music", "audio_balance"])
    result: list[str] = []
    for key in suggestions:
        if key not in result:
            result.append(key)
    return result


def technical_profile_label(profile_id: str, custom_profile: str = "") -> str:
    if not str(profile_id or ""):
        return "Không dùng mẫu chuyên ngành"
    if str(profile_id or "") == "custom":
        return str(custom_profile or "Profile tự nhập")[:180]
    canonical = video_profile_catalog.canonical_profile_key(profile_id)
    if canonical:
        return video_profile_catalog.profile_label(canonical, custom_profile)
    return next((label for key, label in TECHNICAL_PROFILES if key == profile_id), "Mẫu chuyên ngành chưa xác định")


def select_primary_profile(
    state: dict[str, Any],
    profile_id: str,
    *,
    custom_profile: str = "",
) -> dict[str, Any]:
    """Select one canonical primary profile and keep related profiles off."""

    updated = normalize_state(state)
    selected = video_profile_catalog.select_primary_profile(
        updated,
        profile_id,
        custom_profile=custom_profile,
    )
    selected["profile_context"] = video_profile_catalog.profile_bundle_context(
        str(selected.get("primary_profile") or ""),
        selected.get("linked_profiles") or [],
    )
    return normalize_state(selected)


def toggle_linked_profile(state: dict[str, Any], profile_id: str) -> tuple[dict[str, Any], bool]:
    """Toggle one optional linked profile without changing the primary."""

    updated, changed = video_profile_catalog.toggle_linked_profile(
        normalize_state(state),
        profile_id,
    )
    updated["profile_context"] = video_profile_catalog.profile_bundle_context(
        str(updated.get("primary_profile") or ""),
        updated.get("linked_profiles") or [],
    )
    return normalize_state(updated), changed


def post_addon_default(key: str) -> dict[str, Any]:
    return deepcopy(POST_ADDON_DEFAULTS.get(str(key or ""), {}))


def set_character_mode(state: dict[str, Any], mode: str, *, description: str = "") -> dict[str, Any]:
    """Store a grounded character choice without guessing ambiguous gender."""

    mode = str(mode or "")
    if mode not in dict(CHARACTER_MODES):
        return normalize_state(state)
    updated = normalize_state(state)
    current = dict(updated.get("character_config") or {})
    previous = {
        "mode": str(current.get("mode") or ""),
        "gender": str(current.get("gender") or ""),
        "gender_grounded": bool(current.get("gender_grounded")),
        "description": str(current.get("description") or ""),
    }
    history = [dict(item) for item in current.get("history") or [] if isinstance(item, dict)]
    if any(previous.values()):
        history.append(previous)
    gender = mode if mode in {"male", "female"} else ""
    grounded = mode in {"male", "female"}
    if mode == "auto":
        normalized = unicodedata.normalize("NFKD", str(updated.get("subject") or "").lower())
        normalized = "".join(char for char in normalized if not unicodedata.combining(char))
        male_markers = ("nguoi dan ong", "nam chinh", "chang trai", "be trai")
        female_markers = ("nguoi phu nu", "nu chinh", "co gai", "be gai")
        male = any(marker in normalized for marker in male_markers)
        female = any(marker in normalized for marker in female_markers)
        if male != female:
            gender = "male" if male else "female"
            grounded = True
    current.update({
        "mode": mode,
        "gender": gender,
        "gender_grounded": grounded,
        "description": str(description or current.get("description") or "")[:1600],
        "needs_gender_confirmation": bool(mode == "auto" and not grounded),
        "history": history[-10:],
    })
    updated["character_config"] = current
    if mode == "none":
        updated = set_entry(updated, "preservation_requirements", "identity", "Không có nhân vật chính", enabled=True)
    elif grounded:
        label = "nhân vật nam" if gender == "male" else "nhân vật nữ"
        updated = set_entry(updated, "preservation_requirements", "identity", f"Giữ nhất quán {label} đã chọn", enabled=True)
    elif description:
        updated = set_entry(updated, "preservation_requirements", "identity", description, enabled=True)
    return updated


def restore_character_mode(state: dict[str, Any]) -> dict[str, Any]:
    updated = normalize_state(state)
    current = dict(updated.get("character_config") or {})
    history = [dict(item) for item in current.get("history") or [] if isinstance(item, dict)]
    if history:
        previous = history.pop()
        previous["history"] = history
        updated["character_config"] = previous
    return updated


def character_voice_choice(state: dict[str, Any]) -> str:
    character = dict(normalize_state(state).get("character_config") or {})
    if not character.get("gender_grounded"):
        return ""
    return {"male": "default_male", "female": "default_female"}.get(str(character.get("gender") or ""), "")


def set_image_source_mode(state: dict[str, Any], mode: str) -> dict[str, Any]:
    mode = str(mode or "")
    if mode not in dict(IMAGE_SOURCE_MODES):
        return normalize_state(state)
    updated = normalize_state(state)
    previous = str(updated.get("image_source_mode") or "")
    history = list(updated.get("image_source_history") or [])
    if previous and previous != mode:
        history.append(previous)
    updated["image_source_mode"] = mode
    updated["image_source_history"] = history[-10:]
    if mode != "create":
        updated["image_generation_confirmed"] = False
        updated["image_generation_quote"] = {}
    return updated


def prepare_image_generation_quote(state: dict[str, Any], unit_price_xu: int) -> dict[str, Any]:
    """Persist a planning-only image quote without creating a paid task."""

    updated = normalize_state(state)
    if str(updated.get("image_source_mode") or "") != "create":
        return updated
    try:
        unit_price = max(0, int(unit_price_xu))
    except (TypeError, ValueError):
        unit_price = 0
    image_count = max(MIN_SCENES, min(MAX_SCENES, int(updated.get("scene_count") or 1)))
    updated["image_generation_quote"] = {
        "image_count": image_count,
        "unit_price_xu": unit_price,
        "total_price_xu": unit_price * image_count,
        "quote_consistent": True,
        "provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }
    updated["image_generation_confirmed"] = False
    return updated


def confirm_image_generation_quote(state: dict[str, Any]) -> dict[str, Any]:
    """Confirm the quote only; actual image generation remains a later action."""

    updated = normalize_state(state)
    quote = dict(updated.get("image_generation_quote") or {})
    expected = max(MIN_SCENES, min(MAX_SCENES, int(updated.get("scene_count") or 1)))
    if (
        str(updated.get("image_source_mode") or "") == "create"
        and int(quote.get("image_count") or 0) == expected
        and bool(quote.get("quote_consistent"))
    ):
        updated["image_generation_confirmed"] = True
    return updated


def image_prompts_required(state: dict[str, Any]) -> bool:
    return str(normalize_state(state).get("image_source_mode") or "") in {"uploaded", "create"}


def automatic_text_safe_position(
    state: dict[str, Any],
    *,
    occupied: list[str] | None = None,
    preferred: tuple[str, ...] | None = None,
    exclude_item_id: str = "",
) -> str:
    """Choose a deterministic fixed slot without claiming visual tracking."""

    updated = normalize_state(state)
    reserved = {str(item) for item in (occupied or []) if str(item)}
    post = dict(updated.get("postproduction_addons") or {})
    for key in ("logo_image", "watermark_text", "subtitles"):
        entry = dict(post.get(key) or {})
        value = dict(entry.get("value") or {}) if isinstance(entry.get("value"), dict) else {}
        if entry.get("enabled") and str(value.get("position") or ""):
            reserved.add(str(value.get("position")))
    reserved.update(
        str(item.get("position") or "")
        for item in updated.get("automatic_text_items") or []
        if (
            isinstance(item, dict)
            and item.get("enabled", True)
            and str(item.get("id") or "") != str(exclude_item_id or "")
        )
    )
    order = preferred or (
        "top_center", "top_left", "top_right", "middle_left", "middle_right",
        "bottom_left", "bottom_right", "center", "bottom_center",
    )
    for position in order:
        if position not in reserved:
            return position
    return ""


def upsert_automatic_text_item(
    state: dict[str, Any],
    *,
    item_type: str,
    text: str,
    scene_scope: str = "all",
    position: str = "auto_safe",
    timing: str = "whole_scene",
    animation: str = "fade",
    style: str = "Tối giản",
) -> dict[str, Any]:
    """Create or edit one planning-only text item; never fabricate its copy."""

    item_type = str(item_type or "")
    content = str(text or "").strip()
    if item_type not in dict(AUTOMATIC_TEXT_TYPES) or not content:
        return normalize_state(state)
    if timing not in dict(AUTOMATIC_TEXT_TIMINGS):
        timing = "whole_scene"
    if animation not in dict(AUTOMATIC_TEXT_ANIMATIONS):
        animation = "fade"
    if style not in AUTOMATIC_TEXT_STYLES:
        style = "Tối giản"
    updated = normalize_state(state)
    items = [dict(item) for item in updated.get("automatic_text_items") or [] if isinstance(item, dict)]
    history = [list(rows) for rows in updated.get("automatic_text_history") or [] if isinstance(rows, list)]
    history.append(deepcopy(items))
    character_card = item_type in {"character_intro", "tracked_label"}
    if character_card and str(scene_scope or "all") == "all":
        scene_scope = str(max(1, int(updated.get("active_scene_index") or 1)))
    existing_index = next(
        (
            index for index, item in enumerate(items)
            if str(item.get("type") or "") == item_type
            and str(item.get("scene_scope") or "all") == str(scene_scope or "all")
        ),
        -1,
    )
    existing_item_id = str(items[existing_index].get("id") or "") if existing_index >= 0 else ""
    requested_tracking = position == "tracked" or character_card
    if position == "auto_safe" or requested_tracking:
        preferred = (
            "middle_left", "middle_right", "bottom_left", "bottom_right",
            "top_left", "top_right", "top_center", "center", "bottom_center",
        ) if character_card else None
        fixed = automatic_text_safe_position(
            updated,
            preferred=preferred,
            exclude_item_id=existing_item_id,
        )
        if not fixed:
            return updated
        position = fixed
    if position not in dict(AUTOMATIC_TEXT_FIXED_POSITIONS) and position != "custom_coordinates":
        return updated
    item_id = existing_item_id or f"text_{len(items) + 1}"
    if character_card:
        requested_timing = "character_appears"
        actual_timing = "character_appears" if AUTOMATIC_TEXT_TRACKING_AVAILABLE else "scene_start"
        timing_fallback_reason = "" if AUTOMATIC_TEXT_TRACKING_AVAILABLE else "runtime_detection_unavailable"
        duration_seconds = 3
        end_seconds: int | str = 3
        if animation == "fade":
            animation = "slide_soft"
        if style == "Tối giản":
            style = "Thẻ giới thiệu nhân vật"
    else:
        requested_timing = timing
        actual_timing = timing
        timing_fallback_reason = ""
        duration_seconds = SCENE_SECONDS
        end_seconds = "scene_end"
    item = {
        "id": item_id,
        "type": item_type,
        "text": content[:800],
        "scene_scope": str(scene_scope or "all")[:80],
        "position": position,
        "position_mode": "fixed_safe",
        "tracking_requested": requested_tracking,
        "tracking_active": bool(requested_tracking and AUTOMATIC_TEXT_TRACKING_AVAILABLE),
        "tracking_fallback_reason": (
            "runtime_tracking_unavailable"
            if requested_tracking and not AUTOMATIC_TEXT_TRACKING_AVAILABLE
            else ""
        ),
        "target_kind": "person" if character_card else "fixed",
        "timing_requested": requested_timing,
        "timing": actual_timing,
        "timing_fallback_reason": timing_fallback_reason,
        "start_seconds": 0,
        "end_seconds": end_seconds,
        "duration_seconds": duration_seconds,
        "disappear_on_scene_change": True,
        "animation": animation,
        "style": style,
        "design": (
            {
                "family": "Inter",
                "weight": "semibold",
                "text_color": "#FFFFFF",
                "accent_color": "#22C55E",
                "background": "dark_translucent_lower_third",
                "shadow": "soft",
                "max_lines": 2,
                "line_height": 1.15,
                "safe_margin_ratio": 0.04,
                "title_size_ratio": 0.045,
                "detail_size_ratio": 0.032,
            }
            if character_card
            else {}
        ),
        "layout_guard": (
            {
                "always_avoid": ("subtitles", "logo", "watermark", "existing_text", "frame_edges"),
                "avoid_when_detectable": ("face", "person", "product"),
                "fallback": "fixed_safe_position",
            }
            if character_card
            else {}
        ),
        "enabled": True,
        "applied_to_mp4": False,
    }
    if existing_index >= 0:
        items[existing_index] = item
    else:
        items.append(item)
    updated["automatic_text_items"] = items[:40]
    updated["automatic_text_history"] = history[-10:]
    return _sync_automatic_text_owner(updated)


def _sync_automatic_text_owner(state: dict[str, Any]) -> dict[str, Any]:
    """Keep the one post-production owner aligned with automatic_text_items."""

    updated = normalize_state(state)
    items = [dict(item) for item in updated.get("automatic_text_items") or [] if isinstance(item, dict)]
    entry = dict((updated.get("postproduction_addons") or {}).get("automatic_text") or {})
    entry["enabled"] = bool(items)
    entry["value"] = {"owner": "automatic_text_items", "item_count": len(items), "applied_to_mp4": False}
    post = dict(updated.get("postproduction_addons") or {})
    post["automatic_text"] = entry
    updated["postproduction_addons"] = post
    return updated


def update_automatic_text_item(state: dict[str, Any], item_id: str, **changes: Any) -> dict[str, Any]:
    updated = normalize_state(state)
    items = [dict(item) for item in updated.get("automatic_text_items") or [] if isinstance(item, dict)]
    target = str(item_id or "")
    if not target:
        return updated
    index = next((index for index, item in enumerate(items) if str(item.get("id") or "") == target), -1)
    if index < 0:
        return updated
    history = [list(rows) for rows in updated.get("automatic_text_history") or [] if isinstance(rows, list)]
    history.append(deepcopy(items))
    allowed = {
        "text", "scene_scope", "position", "position_mode", "coordinates",
        "timing", "start_seconds", "end_seconds", "duration_seconds",
        "animation", "style", "tracking_requested", "tracking_active",
        "tracking_fallback_reason", "target_kind", "timing_requested",
        "timing_fallback_reason", "disappear_on_scene_change",
    }
    items[index].update({key: value for key, value in changes.items() if key in allowed})
    updated["automatic_text_items"] = items
    updated["automatic_text_history"] = history[-10:]
    return _sync_automatic_text_owner(updated)


def delete_automatic_text_item(state: dict[str, Any], item_id: str) -> dict[str, Any]:
    updated = normalize_state(state)
    items = [dict(item) for item in updated.get("automatic_text_items") or [] if isinstance(item, dict)]
    filtered = [item for item in items if str(item.get("id") or "") != str(item_id or "")]
    if len(filtered) != len(items):
        history = [list(rows) for rows in updated.get("automatic_text_history") or [] if isinstance(rows, list)]
        history.append(deepcopy(items))
        updated["automatic_text_history"] = history[-10:]
        updated["automatic_text_items"] = filtered
    return _sync_automatic_text_owner(updated)


def restore_automatic_text_items(state: dict[str, Any]) -> dict[str, Any]:
    updated = normalize_state(state)
    history = [list(rows) for rows in updated.get("automatic_text_history") or [] if isinstance(rows, list)]
    if history:
        updated["automatic_text_items"] = [dict(item) for item in history.pop() if isinstance(item, dict)]
        updated["automatic_text_history"] = history
    return _sync_automatic_text_owner(updated)


def creative_suggestions(state: dict[str, Any], key: str) -> list[str]:
    """Return five local suggestions anchored to the selected public profile."""

    updated = normalize_state(state)
    key = str(key or "")
    profile_id = str(updated.get("technical_profile") or "")
    guidance = PROFILE_CREATIVE_GUIDANCE.get(profile_id, {})
    guidance_field = {
        "camera": "camera",
        "motion": "motion",
        "visual_style": "visual",
        "colors": "visual",
        "negative": "avoid",
    }.get(key, "focus")
    profile_note = str(
        guidance.get(guidance_field)
        or guidance.get("focus")
        or "bám đúng chủ đề và profile đã chọn"
    )
    subject = str(updated.get("subject") or "chủ đề đã chọn").strip()
    return [
        f"{str(item).rstrip('.')}; {profile_note}; bám đúng chủ đề {subject}."
        for item in CREATIVE_SUGGESTIONS.get(key, ())
    ][:5]


def content_addon_suggestions(state: dict[str, Any], key: str) -> list[str]:
    """Return five option-specific suggestions anchored to the selected plan."""

    updated = normalize_state(state)
    profile_id = str(updated.get("technical_profile") or "")
    guidance = PROFILE_CREATIVE_GUIDANCE.get(profile_id, {})
    profile_focus = str(
        guidance.get("focus")
        or "giữ đúng mục tiêu của profile đã chọn"
    ).rstrip(".")
    subject = str(updated.get("subject") or "chủ đề đã chọn").strip()
    return [
        f"{str(item).rstrip('.')}; áp dụng cho {subject}, {profile_focus}."
        for item in CONTENT_ADDON_SUGGESTIONS.get(str(key or ""), ())
    ][:5]


def transition_suggestions(state: dict[str, Any], scene_index: int) -> list[str]:
    """Pick five relevant transition keys for one exact scene boundary."""

    updated = normalize_state(state)
    count = max(1, int(updated.get("scene_count") or 1))
    index = max(1, min(max(1, count - 1), int(scene_index or 1)))
    profile_id = str(updated.get("technical_profile") or "")
    scenes = [
        dict(item)
        for item in (updated.get("plan") or {}).get("scenes") or []
        if isinstance(item, dict)
    ]
    current = scenes[index - 1] if index <= len(scenes) else {}
    next_scene = scenes[index] if index < len(scenes) else {}
    searchable = " ".join(
        str(value or "").lower()
        for value in (
            current.get("main_idea"), current.get("primary_action"), current.get("dialogue_or_voiceover"),
            next_scene.get("main_idea"), next_scene.get("primary_action"), next_scene.get("dialogue_or_voiceover"),
        )
    )
    if profile_id in {
        "architecture_exterior", "architecture_interior", "space_renovation",
        "real_estate_property", "architecture_walkthrough",
    }:
        ordered = ["camera pan continuation", "doorway transition", "match cut", "dissolve", "reveal"]
    elif profile_id in {"cinematic_vfx", "animation_2d_3d", "fashion_lookbook"}:
        ordered = ["motion match", "cut on action", "match cut", "object wipe", "dissolve"]
    elif profile_id in {"app_game_demo", "website_saas_demo", "tutorial_explainer"}:
        ordered = ["match cut", "cut on action", "camera pan continuation", "dissolve", "sound bridge"]
    else:
        ordered = ["cut on action", "motion match", "match cut", "dissolve", "sound bridge"]
    if any(token in searchable for token in ("nói", "lời", "thoại", "giọng")):
        ordered = ["dialogue bridge", "sound bridge", *ordered]
    if any(token in searchable for token in ("trước", "sau", "thay đổi", "cải tạo")):
        ordered = ["before/after morph", *ordered]
    result: list[str] = []
    for transition in ordered:
        if transition in TRANSITIONS and transition not in result:
            result.append(transition)
    return result[:5]


def configure_content_safe_zone(
    state: dict[str, Any],
    key: str,
    *,
    position: str,
    enabled: bool = True,
) -> dict[str, Any]:
    """Persist a planning-only logo/copyright safe zone with an exact position."""

    key = str(key or "")
    position = str(position or "")
    if key not in {"logo_safe_zone", "watermark_safe_zone"}:
        return normalize_state(state)
    if enabled and position not in dict(LOGO_POSITIONS):
        return normalize_state(state)
    value = {
        "position": position if enabled else "",
        "planning_only": True,
        "applied_to_mp4": False,
    }
    return set_entry(state, "content_affecting_addons", key, value, enabled=enabled)


def configure_post_position(state: dict[str, Any], key: str, position: str) -> dict[str, Any]:
    """Set an overlay position in the plan without claiming it was rendered."""

    key = str(key or "")
    position = str(position or "")
    if key not in {"logo_image", "watermark_text", "watermark_image", "subtitles", "text_overlay"}:
        return normalize_state(state)
    if position not in dict(LOGO_POSITIONS):
        return normalize_state(state)
    updated = normalize_state(state)
    current = dict((updated.get("postproduction_addons") or {}).get(key) or {})
    config = dict(current.get("value") or {}) if isinstance(current.get("value"), dict) else post_addon_default(key)
    config.update({"position": position, "applied_to_mp4": False})
    return set_entry(updated, "postproduction_addons", key, config, enabled=True)


def configure_post_asset(
    state: dict[str, Any],
    key: str,
    *,
    file_id: str,
    file_unique_id: str = "",
    mime_type: str = "",
) -> dict[str, Any]:
    """Store a Telegram image reference for logo/image watermark planning only."""

    key = str(key or "")
    if key not in {"logo_image", "watermark_image"} or not str(file_id or "").strip():
        return normalize_state(state)
    updated = normalize_state(state)
    current = dict((updated.get("postproduction_addons") or {}).get(key) or {})
    config = post_addon_default(key)
    if isinstance(current.get("value"), dict):
        config.update(dict(current.get("value") or {}))
    config.update({
        "source": "user_asset",
        "asset_file_id": str(file_id),
        "asset_file_unique_id": str(file_unique_id or ""),
        "asset_mime_type": str(mime_type or "image/jpeg"),
        "applied_to_mp4": False,
    })
    safe_zone_key = "logo_safe_zone" if key == "logo_image" else "watermark_safe_zone"
    safe_zone = dict((updated.get("content_affecting_addons") or {}).get(safe_zone_key) or {})
    safe_value = dict(safe_zone.get("value") or {}) if isinstance(safe_zone.get("value"), dict) else {}
    safe_position = str(safe_value.get("position") or "")
    if safe_zone.get("enabled") and safe_position in dict(LOGO_POSITIONS):
        config["position"] = safe_position
    return set_entry(updated, "postproduction_addons", key, config, enabled=True)


def configure_watermark_text(state: dict[str, Any], text: str) -> dict[str, Any]:
    """Store copyright text distinctly from image-logo input."""

    value = str(text or "").strip()
    if not value:
        return normalize_state(state)
    updated = normalize_state(state)
    current = dict((updated.get("postproduction_addons") or {}).get("watermark_text") or {})
    config = post_addon_default("watermark_text")
    if isinstance(current.get("value"), dict):
        config.update(dict(current.get("value") or {}))
    config.update({"text": value[:300], "applied_to_mp4": False})
    safe_zone = dict((updated.get("content_affecting_addons") or {}).get("watermark_safe_zone") or {})
    safe_value = dict(safe_zone.get("value") or {}) if isinstance(safe_zone.get("value"), dict) else {}
    safe_position = str(safe_value.get("position") or "")
    if safe_zone.get("enabled") and safe_position in dict(LOGO_POSITIONS):
        config["position"] = safe_position
    return set_entry(updated, "postproduction_addons", "watermark_text", config, enabled=True)


def configure_audio_volume(state: dict[str, Any], key: str, volume_percent: int) -> dict[str, Any]:
    """Set one planning-only audio level without executing any audio engine."""

    key = str(key or "")
    if key not in AUDIO_POST_ADDONS:
        return normalize_state(state)
    try:
        volume = int(volume_percent)
    except (TypeError, ValueError):
        return normalize_state(state)
    if volume < 0 or volume > 200:
        return normalize_state(state)
    updated = normalize_state(state)
    current = dict((updated.get("postproduction_addons") or {}).get(key) or {})
    config = post_addon_default(key)
    if isinstance(current.get("value"), dict):
        config.update(dict(current.get("value") or {}))
    config.update({
        "volume_percent": volume,
        "peak_guard": True,
        "clipping_guard": "limit_peak_before_mix",
        "ducking": bool(key in {"music", "sfx", "source_audio"}),
        "fade_in_seconds": 0.25 if key in {"music", "sfx"} else 0,
        "fade_out_seconds": 0.25 if key in {"music", "sfx"} else 0,
        "applied_to_mp4": False,
    })
    return set_entry(updated, "postproduction_addons", key, config, enabled=volume > 0)


def personal_voice_asset(state: dict[str, Any], user_id: int) -> dict[str, Any]:
    """Return the latest valid voice reference owned by the current Telegram user."""

    owner_id = int(user_id or 0)
    if owner_id <= 0:
        return {}
    items = [
        dict(item)
        for item in (normalize_state(state).get("reference_assets") or {}).get("items") or []
        if isinstance(item, dict)
    ]
    for item in reversed(items):
        if str(item.get("type") or "") != "voice_audio":
            continue
        if str(item.get("media_kind") or "") != "audio":
            continue
        if int(item.get("owner_user_id") or 0) != owner_id:
            continue
        if not str(item.get("file_id") or "").strip():
            continue
        return item
    return {}


def configure_voice_choice(state: dict[str, Any], choice: str, *, user_id: int = 0) -> dict[str, Any]:
    """Choose one canonical dubbing voice without guessing character gender."""

    choice = str(choice or "")
    patch = VOICE_CHOICES.get(choice)
    if not patch:
        return normalize_state(state)
    updated = normalize_state(state)
    if choice == "follow_character":
        grounded_choice = character_voice_choice(updated)
        if not grounded_choice:
            character = dict(updated.get("character_config") or {})
            character["needs_gender_confirmation"] = True
            updated["character_config"] = character
            return updated
        choice = grounded_choice
        patch = VOICE_CHOICES[choice]
    current = dict((updated.get("postproduction_addons") or {}).get("dubbing") or {})
    config = post_addon_default("dubbing")
    if isinstance(current.get("value"), dict):
        config.update(dict(current.get("value") or {}))
    for field in (
        "asset_file_id", "asset_file_unique_id", "asset_mime_type",
        "asset_owner_user_id", "asset_source_message_id", "custom_voice_asset_present",
    ):
        config.pop(field, None)
    if choice == "custom_voice":
        asset = personal_voice_asset(updated, user_id)
        if not asset:
            return updated
        config.update({
            "asset_file_id": str(asset.get("file_id") or ""),
            "asset_file_unique_id": str(asset.get("file_unique_id") or ""),
            "asset_mime_type": str(asset.get("mime_type") or "audio/ogg"),
            "asset_owner_user_id": int(asset.get("owner_user_id") or 0),
            "asset_source_message_id": int(asset.get("source_message_id") or 0),
            "custom_voice_asset_present": True,
        })
    config.update(deepcopy(patch))
    config.update({"voice_choice": choice, "applied_to_mp4": False})
    return set_entry(updated, "postproduction_addons", "dubbing", config, enabled=True)


def configure_music_source(state: dict[str, Any], source_choice: str) -> dict[str, Any]:
    """Plan existing or newly generated music without making a provider call."""

    source_choice = str(source_choice or "")
    patch = MUSIC_SOURCE_CHOICES.get(source_choice)
    if not patch:
        return normalize_state(state)
    updated = normalize_state(state)
    current = dict((updated.get("postproduction_addons") or {}).get("music") or {})
    config = post_addon_default("music")
    if isinstance(current.get("value"), dict):
        config.update(dict(current.get("value") or {}))
    config.update(deepcopy(patch))
    config.update({"music_source_choice": source_choice, "applied_to_mp4": False})
    return set_entry(updated, "postproduction_addons", "music", config, enabled=True)


def configure_music_vocal_mode(state: dict[str, Any], vocal_mode: str) -> dict[str, Any]:
    """Plan instrumental or lyric music while preserving the selected source."""

    vocal_mode = str(vocal_mode or "")
    if vocal_mode not in MUSIC_VOCAL_MODES:
        return normalize_state(state)
    updated = normalize_state(state)
    current = dict((updated.get("postproduction_addons") or {}).get("music") or {})
    config = post_addon_default("music")
    if isinstance(current.get("value"), dict):
        config.update(dict(current.get("value") or {}))
    config.update({"vocal_mode": vocal_mode, "applied_to_mp4": False})
    source_selected = str(config.get("source") or "not_selected") != "not_selected"
    return set_entry(
        updated,
        "postproduction_addons",
        "music",
        config,
        enabled=bool(current.get("enabled") or source_selected),
    )


def configure_post_note(state: dict[str, Any], key: str, text: str) -> dict[str, Any]:
    """Store editable audio/post copy without claiming an output was generated."""

    key = str(key or "")
    value = str(text or "").strip()
    if key not in dict(POST_ADDONS) or not value:
        return normalize_state(state)
    updated = normalize_state(state)
    current = dict((updated.get("postproduction_addons") or {}).get(key) or {})
    config = post_addon_default(key)
    if isinstance(current.get("value"), dict):
        config.update(dict(current.get("value") or {}))
    field = {"voice": "script_note", "dubbing": "dialogue_text", "music": "music_request"}.get(key, "user_note")
    config.update({field: value[:1600]})
    if "applied_to_mp4" in config:
        config["applied_to_mp4"] = False
    enabled = bool(current.get("enabled")) if key in {"voice", "dubbing", "music"} else True
    return set_entry(updated, "postproduction_addons", key, config, enabled=enabled)


def normalize_material_type(value: str) -> str:
    material_type = str(value or "").strip()
    return MATERIAL_TYPE_ALIASES.get(material_type, material_type)


def logo_position_label(value: str) -> str:
    return dict(LOGO_POSITIONS).get(str(value or ""), "Chưa chọn vị trí")


def automatic_text_position_label(value: str) -> str:
    return dict(AUTOMATIC_TEXT_FIXED_POSITIONS).get(
        str(value or ""),
        "Tọa độ tự nhập" if str(value or "") == "custom_coordinates" else "Chưa chọn vị trí",
    )


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


def validate_adaptive_rows(rows: list[list[tuple[str, str]]]) -> list[list[tuple[str, str]]]:
    """Validate compact public rows without forcing every screen into two columns."""

    normalized: list[list[tuple[str, str]]] = []
    callbacks: set[str] = set()
    for row in rows:
        if not 1 <= len(row) <= 5:
            raise ValueError("video_scene3_keyboard_requires_one_to_five_buttons_per_row")
        clean_row: list[tuple[str, str]] = []
        for label, callback in row:
            clean_label = str(label or "").strip()
            clean_callback = str(callback or "").strip()
            if (
                not clean_label
                or not clean_callback
                or len(clean_callback.encode("utf-8")) > 64
                or clean_callback in callbacks
            ):
                raise ValueError("video_scene3_keyboard_duplicate_or_empty_button")
            callbacks.add(clean_callback)
            clean_row.append((clean_label, clean_callback))
        normalized.append(clean_row)
    return normalized


def validate_two_column_rows(rows: list[list[tuple[str, str]]]) -> list[list[tuple[str, str]]]:
    """Legacy validator retained for non-SCENE3 callers and old contract tests."""

    normalized = validate_adaptive_rows(rows)
    if any(len(row) != 2 for row in normalized):
        raise ValueError("video_scene3_keyboard_requires_exactly_two_buttons_per_row")
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


def requirement_suggestions(state: dict[str, Any], key: str) -> list[str]:
    """Return five category-specific preservation choices for the current plan."""

    updated = normalize_state(state)
    subject = str(updated.get("subject") or "chủ thể đã chọn").strip()
    profile = technical_profile_label(str(updated.get("technical_profile") or ""))
    templates = REQUIREMENT_SUGGESTION_TEMPLATES.get(str(key or ""), ())
    return [
        str(template).format(subject=subject, profile=profile)
        for template in templates[:5]
    ]


def requirement_suggestion(key: str, state: dict[str, Any]) -> str:
    suggestions = requirement_suggestions(state, key)
    return suggestions[0] if suggestions else "Giữ nguyên chi tiết quan trọng giữa mọi cảnh."


def _expanded_field_suggestions(
    state: dict[str, Any],
    values: list[str],
) -> list[str]:
    """Expand five approved choices into four non-repeating context pages."""

    updated = normalize_state(state)
    aspect_ratio = str(updated.get("aspect_ratio") or "9:16")
    scene_count = max(MIN_SCENES, int(updated.get("scene_count") or 1))
    expanded: list[str] = []
    for variant in FIELD_SUGGESTION_VARIANTS:
        suffix = variant.format(
            aspect_ratio=aspect_ratio,
            scene_count=scene_count,
        )
        for value in values[:FIELD_SUGGESTION_PAGE_SIZE]:
            expanded.append(f"{str(value).rstrip('.')}.{suffix}".strip())
    return list(dict.fromkeys(expanded))[:20]


def unified_field_suggestion_catalog(
    state: dict[str, Any],
    group: str,
    key: str,
) -> list[str]:
    """Return the complete 20-choice catalog for one canonical field."""

    clean_group = str(group or "")
    clean_key = str(key or "")
    if clean_group == "creative_controls" and clean_key in dict(CREATIVE_CONTROLS):
        return _expanded_field_suggestions(state, creative_suggestions(state, clean_key))
    if (
        clean_group == "preservation_requirements"
        and clean_key in dict(PUBLIC_REQUIREMENT_CATEGORIES)
    ):
        return _expanded_field_suggestions(state, requirement_suggestions(state, clean_key))
    return []


def _field_suggestion_offset_key(group: str, key: str) -> str:
    return f"{str(group or '')}:{str(key or '')}"


def unified_field_suggestion_page(state: dict[str, Any], group: str, key: str) -> int:
    updated = normalize_state(state)
    offset = int(
        (updated.get("field_suggestion_offsets") or {}).get(
            _field_suggestion_offset_key(group, key),
            0,
        )
        or 0
    )
    return (offset // FIELD_SUGGESTION_PAGE_SIZE) + 1


def unified_field_suggestions(state: dict[str, Any], group: str, key: str) -> list[str]:
    """Resolve the five choices for one canonical editor field."""

    updated = normalize_state(state)
    catalog = unified_field_suggestion_catalog(updated, group, key)
    if not catalog:
        return []
    offset_key = _field_suggestion_offset_key(group, key)
    offset = int((updated.get("field_suggestion_offsets") or {}).get(offset_key, 0) or 0)
    offset %= len(catalog)
    return catalog[offset:offset + FIELD_SUGGESTION_PAGE_SIZE]


def rotate_unified_field_suggestions(
    state: dict[str, Any],
    group: str,
    key: str,
) -> dict[str, Any]:
    """Advance five choices; the first page repeats only after all 20."""

    updated = normalize_state(state)
    catalog = unified_field_suggestion_catalog(updated, group, key)
    if not catalog:
        return updated
    offsets = dict(updated.get("field_suggestion_offsets") or {})
    offset_key = _field_suggestion_offset_key(group, key)
    current = int(offsets.get(offset_key, 0) or 0)
    offsets[offset_key] = (current + FIELD_SUGGESTION_PAGE_SIZE) % len(catalog)
    updated["field_suggestion_offsets"] = offsets
    return updated


def select_unified_field_suggestion(
    state: dict[str, Any],
    group: str,
    key: str,
    selection: int,
) -> dict[str, Any]:
    """Persist one numbered choice without changing any sibling field."""

    updated = normalize_state(state)
    suggestions = unified_field_suggestions(updated, group, key)
    index = int(selection or 0)
    if index < 1 or index > len(suggestions):
        return updated
    updated = set_entry(
        updated,
        str(group or ""),
        str(key or ""),
        suggestions[index - 1],
        enabled=True,
    )
    if str(group or "") == "preservation_requirements":
        updated["requirements"] = public_requirements(updated)
    return updated


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
    primary_profile = str(state.get("primary_profile") or state.get("technical_profile") or "")
    profile = technical_profile_label(
        primary_profile,
        str(state.get("custom_technical_profile") or ""),
    )
    bundle_context = video_profile_catalog.profile_bundle_context(
        primary_profile,
        state.get("linked_profiles") or [],
    )
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
            "context": (
                f"{profile}; {bundle_context} "
                "Giữ mạch hình ảnh và trạng thái cuối cảnh trước sang cảnh sau."
            ),
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


def toggle_audio_planning_addon(state: dict[str, Any], key: str) -> dict[str, Any]:
    """Toggle the single canonical post-production entry used by planning."""

    clean_key = str(key or "")
    updated = normalize_state(state)
    if clean_key not in dict(AUDIO_PLANNING_ADDONS):
        return updated
    current = dict((updated.get("postproduction_addons") or {}).get(clean_key) or {})
    if current.get("enabled"):
        return remove_entry(updated, "postproduction_addons", clean_key)
    value = current.get("value")
    if not isinstance(value, dict) or not value:
        value = post_addon_default(clean_key)
    return set_entry(
        updated,
        "postproduction_addons",
        clean_key,
        value,
        enabled=True,
    )


def finalize_audio_planning(state: dict[str, Any], *, skip: bool = False) -> dict[str, Any]:
    """Build the local scene plan after applying or clearing audio choices."""

    updated = normalize_state(state)
    if skip:
        for key, _label in AUDIO_PLANNING_ADDONS:
            updated = remove_entry(updated, "postproduction_addons", key)
    return build_planning_package(updated)


def public_requirements(state: dict[str, Any]) -> dict[str, Any]:
    rows = dict(normalize_state(state).get("preservation_requirements") or {})
    values = [str(item.get("value") or "").strip() for item in rows.values() if item.get("enabled") and str(item.get("value") or "").strip()]
    return {"brief": "; ".join(values), "preserve_constraints": values}


def planner_content_addons(state: dict[str, Any]) -> dict[str, Any]:
    updated = normalize_state(state)
    post = dict(updated.get("postproduction_addons") or {})
    aspect = str(updated.get("aspect_ratio") or "9:16")

    def _enabled(key: str) -> bool:
        return bool((post.get(key) or {}).get("enabled"))

    def _position(key: str, default: str) -> str:
        item = dict(post.get(key) or {})
        value = dict(item.get("value") or {}) if isinstance(item.get("value"), dict) else {}
        position = str(value.get("position") or "")
        return position if position in dict(LOGO_POSITIONS) else default

    text_items = [dict(item) for item in updated.get("automatic_text_items") or [] if isinstance(item, dict)]
    has_cta = any(item.get("enabled", True) and str(item.get("type") or "") == "cta" for item in text_items)
    music_value = dict((post.get("music") or {}).get("value") or {}) if isinstance((post.get("music") or {}).get("value"), dict) else {}

    result: dict[str, Any] = {
        "voiceover": _enabled("dubbing"),
        "dialogue": _enabled("dubbing"),
        "captions": _enabled("subtitles"),
        "subtitle_required": _enabled("subtitles"),
        "cta": has_cta,
        "logo_safe_zone": _position("logo_image", "top_right") if _enabled("logo_image") else "none",
        "watermark_safe_zone": _position("watermark_text", "bottom_right") if _enabled("watermark_text") else "none",
        "preserve_source_audio": _enabled("source_audio"),
        "aspect_ratio": aspect,
        "music_mood": str(music_value.get("music_request") or "") if _enabled("music") else "",
        "transition_style": "",
    }
    return result


def planner_post_addons(state: dict[str, Any]) -> dict[str, bool]:
    entries = dict(normalize_state(state).get("postproduction_addons") or {})
    return {
        "logo_burn_in": bool(entries["logo_image"].get("enabled")),
        "watermark_burn_in": bool(entries["watermark_text"].get("enabled") or entries["watermark_image"].get("enabled")),
        "subtitle_rendering": bool(entries["subtitles"].get("enabled")),
        "dubbing_mix": bool(entries["dubbing"].get("enabled")),
        "music_mix": bool(entries["music"].get("enabled")),
        "final_audio_mix": bool(
            entries["dubbing"].get("enabled")
            or entries["music"].get("enabled")
            or entries["sfx"].get("enabled")
            or entries["source_audio"].get("enabled")
        ),
        # Product Video always requires a validated MP4 final; this is not an
        # optional public add-on and therefore does not need a checkbox.
        "output_packaging": True,
    }


def _profile_for_planner(state: dict[str, Any]) -> str:
    primary_profile = str(state.get("primary_profile") or "")
    if primary_profile and primary_profile != "custom":
        return video_profile_catalog.technical_profile_for_profile(primary_profile)
    if str(state.get("technical_profile") or "") == "custom":
        return str(state.get("custom_technical_profile") or state.get("content_type") or "storytelling")
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
    creative_palette_lighting = str(
        creative["colors"].get("value")
        if creative["colors"].get("enabled")
        else ""
    )
    identity_colors = dict(
        (updated.get("preservation_requirements") or {}).get("colors") or {}
    )
    identity_color_locks = str(
        identity_colors.get("value")
        if identity_colors.get("enabled")
        else ""
    )
    requirements.update({
        "camera": str(creative["camera"].get("value") or ""),
        "lighting": creative_palette_lighting,
        "visual_style": str(creative["visual_style"].get("value") or ""),
        "creative_palette_lighting": creative_palette_lighting,
        "identity_color_locks": identity_color_locks,
        "color_palette": identity_color_locks or creative_palette_lighting,
        "color_conflict_policy": "identity_color_locks_override_creative_palette",
    })
    primary_profile = str(updated.get("primary_profile") or updated.get("technical_profile") or "")
    linked_profiles = list(updated.get("linked_profiles") or [])
    semantic_beats = [
        dict(item)
        for item in updated.get("idea_scene_beats") or []
        if isinstance(item, dict)
    ]
    if not semantic_beats and primary_profile:
        semantic_beats = video_profile_catalog.semantic_beats_for_bundle(
            primary_profile,
            linked_profiles,
            count,
        )
    bundle_context = video_profile_catalog.profile_bundle_context(
        primary_profile,
        linked_profiles,
    )
    planning_context = " ".join(
        item
        for item in (
            str(updated.get("context") or ""),
            str(updated.get("profile_context") or ""),
            bundle_context,
        )
        if item
    )
    plan = video_semantic_scene_planner.build_semantic_scene_plan(
        subject=str(updated.get("subject") or ""),
        scene_count=count,
        profile_id=_profile_for_planner(updated),
        context=planning_context,
        requirements=requirements,
        assets=dict(updated.get("reference_assets") or updated.get("assets") or {}),
        addon_plan=addon_plan,
        semantic_beats=semantic_beats,
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
        "colors": str(scene.get("creative_palette_lighting") or scene.get("lighting") or ""),
        "identity_color_locks": str(scene.get("identity_color_locks") or ""),
        "color_conflict_policy": str(scene.get("color_conflict_policy") or ""),
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
        f"Camera: {scene.get('camera')}. Bảng màu và ánh sáng: {scene.get('creative_palette_lighting') or scene.get('lighting')}. "
        f"Màu nhận diện phải giữ nguyên: {scene.get('identity_color_locks') or 'theo tư liệu đã chọn'}. "
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
        "colors": str(scene.get("creative_palette_lighting") or scene.get("lighting") or ""),
        "identity_color_locks": str(scene.get("identity_color_locks") or ""),
        "color_conflict_policy": str(scene.get("color_conflict_policy") or ""),
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
    image_mode = str(updated.get("image_source_mode") or "description")
    needs_image_prompts = image_prompts_required(updated)
    for scene in scenes:
        index = int(scene.get("scene_index") or 0)
        key = str(index)
        strategies[key] = {"strategy": image_mode, "approved": image_mode in {"description", "none"}}
        if needs_image_prompts:
            image_versions[key] = {"active_version": 1, "approved": False, "versions": [{"version": 1, **_image_prompt(scene, {**updated, "plan": package})}]}
        video_versions[key] = {"active_version": 1, "approved": False, "versions": [{"version": 1, **_video_prompt(scene, prompt_rows.get(index, {}), updated)}]}
    post_entries = dict(updated.get("postproduction_addons") or {})
    voice_timing = {
        str(index): {
            "start_seconds": (index - 1) * SCENE_SECONDS,
            "end_seconds": index * SCENE_SECONDS,
            "approved": False,
        }
        for index in range(1, len(scenes) + 1)
    } if (post_entries.get("dubbing") or {}).get("enabled") else {}
    cta_placement = {
        str(len(scenes)): {"placement": "cuối cảnh", "approved": False}
    } if scenes and any(
        str(item.get("type") or "") == "cta" and item.get("enabled", True)
        for item in updated.get("automatic_text_items") or []
        if isinstance(item, dict)
    ) else {}
    updated.update({
        "scene_plan": package,
        "plan": package,
        "continuity_contract": dict(package.get("continuity_contract") or {}),
        "image_strategy_per_scene": strategies,
        "image_prompt_versions": image_versions,
        "video_prompt_versions": video_versions,
        "transition_plan": [
            {
                **dict(item),
                "transition_id": str(
                    item.get("transition_id")
                    or f"scene_{int(item.get('from_scene') or 0)}_to_{int(item.get('to_scene') or 0)}"
                ),
            }
            for item in package.get("transitions") or []
            if isinstance(item, dict)
        ],
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
            item["transition_id"] = str(
                item.get("transition_id")
                or f"scene_{index}_to_{index + 1}"
            )
            item["transition_type"] = transition
            item["instruction"] = f"{public['label']}: {public['description']}"
            found = True
    if not found and index < len(scenes):
        transitions.append({
            "transition_id": f"scene_{index}_to_{index + 1}",
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
        "image_prompts_expected": expected if image_prompts_required(updated) else 0,
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


def preconfirm_audio_side_effects(state: dict[str, Any]) -> dict[str, int]:
    """Expose explicit no-engine/no-file counters for the planning-only audio UI."""

    state = normalize_state(state)
    return {
        "music_provider_calls": int(state.get("music_provider_calls") or 0),
        "voice_provider_calls": int(state.get("voice_provider_calls") or 0),
        "files_generated": int(state.get("files_generated") or 0),
    }
