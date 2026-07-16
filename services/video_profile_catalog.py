"""Canonical, provider-free Video Profile catalog and relation graph.

The catalog is planning metadata only. It never creates jobs, outbox rows,
media files, provider requests, or wallet mutations.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = 2
MAX_LINKED_PROFILES = 2
PAGE_GROUPS = (
    ("sales_social", "Bán hàng & mạng xã hội"),
    ("story_knowledge_emotion", "Kể chuyện, kiến thức & cảm xúc"),
    ("industry_visual", "Ngành & hình ảnh chuyên biệt"),
)
RELATION_TYPES = {
    "recommended_with",
    "subtype_of",
    "alternative_to",
    "visual_style_for",
    "domain_overlay_for",
}
PROFILE_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_]{1,63}$")


def _profile(
    profile_key: str,
    icon: str,
    public_name: str,
    short_name: str,
    page_group: str,
    description: str,
    pattern: tuple[str, ...],
    *,
    narrative: tuple[str, ...] = (),
    industry: tuple[str, ...] = (),
    visual: tuple[str, ...] = (),
    platform: tuple[str, ...] = (),
    goal: tuple[str, ...] = (),
    aliases: tuple[str, ...] = (),
    sort_order: int,
) -> dict[str, Any]:
    return {
        "profile_key": profile_key,
        "icon": icon,
        "public_name": public_name,
        "short_name": short_name,
        "page_group": page_group,
        "description": description,
        "narrative_tags": list(narrative),
        "industry_tags": list(industry),
        "visual_tags": list(visual),
        "platform_tags": list(platform),
        "goal_tags": list(goal),
        "default_scene_pattern": list(pattern),
        "clarification_questions": [
            f"Anh/chị muốn {public_name.lower()} tập trung vào chủ thể hoặc kết quả nào?",
            "Người xem cần nhớ điều gì sau cảnh cuối?",
        ],
        "aliases": list(dict.fromkeys((profile_key, public_name, short_name, *aliases))),
        "sort_order": sort_order,
        "is_active": 1,
    }


PROFILE_SEEDS = (
    _profile(
        "sales_ads", "🛍", "Bán hàng / quảng cáo", "Bán hàng / quảng cáo",
        "sales_social", "Giới thiệu giá trị, bằng chứng và lời mời hành động rõ ràng.",
        ("Hook vấn đề", "Lợi ích chính", "Bằng chứng", "Lời kêu gọi hành động"),
        narrative=("sales", "problem_solution"), industry=("commerce",),
        visual=("product", "proof"), platform=("short_video", "social"),
        goal=("conversion", "awareness"), aliases=("quảng cáo", "bán hàng"), sort_order=1,
    ),
    _profile(
        "product_review_demo", "🛒", "Review / demo sản phẩm", "Review / demo",
        "sales_social", "Trải nghiệm hoặc minh họa sản phẩm một cách cụ thể, có ưu nhược điểm.",
        ("Nhu cầu", "Cận cảnh hoặc dùng thử", "Ưu và nhược điểm", "Kết luận"),
        narrative=("review", "demonstration"), industry=("commerce",),
        visual=("macro", "product_demo"), platform=("social", "youtube"),
        goal=("consideration", "trust"), aliases=("review sản phẩm", "demo sản phẩm"), sort_order=2,
    ),
    _profile(
        "affiliate_ugc", "📱", "Affiliate / UGC", "Affiliate / UGC",
        "sales_social", "Góc nhìn người dùng đời thường, chân thật và có lời mời mềm.",
        ("POV đời thường", "Trải nghiệm thật", "Lợi ích", "Lời mời mềm"),
        narrative=("ugc", "personal_experience"), industry=("commerce", "lifestyle"),
        visual=("handheld", "natural"), platform=("tiktok", "reels"),
        goal=("affiliate", "trust"), aliases=("ugc", "affiliate", "tiếp thị liên kết"), sort_order=3,
    ),
    _profile(
        "testimonial_case_study", "✅", "Testimonial / case study", "Testimonial / case study",
        "sales_social", "Trình bày vấn đề, giải pháp và kết quả đã được xác minh.",
        ("Trước đây", "Vấn đề", "Giải pháp", "Kết quả đã xác minh"),
        narrative=("case_study", "testimonial"), industry=("business",),
        visual=("before_after", "evidence"), platform=("social", "linkedin"),
        goal=("proof", "trust"), aliases=("case study", "khách hàng chứng thực"), sort_order=4,
    ),
    _profile(
        "brand_corporate", "🏢", "Thương hiệu / doanh nghiệp", "Thương hiệu / doanh nghiệp",
        "sales_social", "Kể câu chuyện thương hiệu qua con người, quy trình và giá trị.",
        ("Sứ mệnh", "Con người hoặc quy trình", "Giá trị", "Lời mời"),
        narrative=("brand_story", "corporate"), industry=("business",),
        visual=("corporate", "process"), platform=("linkedin", "youtube"),
        goal=("brand_awareness", "recruitment"), aliases=("doanh nghiệp", "thương hiệu"), sort_order=5,
    ),
    _profile(
        "social_creator_trend", "🔥", "Social creator / bắt trend", "Social creator / trend",
        "sales_social", "Nội dung ngắn có hook nhanh, nhịp dọc và điểm nhớ rõ.",
        ("Hook nhanh", "Diễn biến ngắn", "Điểm nhấn", "Kết gọn"),
        narrative=("trend", "creator"), industry=("social_media",),
        visual=("vertical", "fast_paced"), platform=("tiktok", "reels", "shorts"),
        goal=("reach", "engagement"), aliases=("bắt trend", "video trend", "social creator"), sort_order=6,
    ),
    _profile(
        "meme_parody_comedy", "🎭", "Meme / parody / hài", "Meme / parody / hài",
        "sales_social", "Tình huống quen thuộc, cú bẻ hợp lý và câu chốt ngắn.",
        ("Tình huống quen thuộc", "Lệch kỳ vọng", "Cú bẻ", "Câu chốt"),
        narrative=("comedy", "parody"), industry=("entertainment",),
        visual=("reaction", "comic_timing"), platform=("tiktok", "reels"),
        goal=("engagement", "share"), aliases=("meme", "parody", "hài"), sort_order=7,
    ),
    _profile(
        "event_highlight", "🎉", "Sự kiện / highlight", "Sự kiện / highlight",
        "sales_social", "Tóm lược không khí, khoảnh khắc nổi bật và cao trào sự kiện.",
        ("Không khí", "Khoảnh khắc nổi bật", "Cao trào", "Tóm lược"),
        narrative=("highlight", "recap"), industry=("event",),
        visual=("dynamic", "crowd"), platform=("social", "youtube"),
        goal=("recap", "awareness"), aliases=("highlight", "sự kiện"), sort_order=8,
    ),
    _profile(
        "news_data_analysis", "📊", "Tin tức / phân tích dữ liệu", "Tin tức / dữ liệu",
        "sales_social", "Diễn giải thông tin có nguồn, mốc thời gian và giới hạn rõ.",
        ("Tiêu đề", "Dữ liệu hoặc nguồn", "Diễn giải", "Kết luận có giới hạn"),
        narrative=("news", "analysis"), industry=("media", "data"),
        visual=("infographic", "charts"), platform=("youtube", "social", "linkedin"),
        goal=("inform", "explain"), aliases=("tin tức", "phân tích dữ liệu", "data"), sort_order=9,
    ),
    _profile(
        "podcast_interview_talking_head", "🎙", "Podcast / phỏng vấn / talking-head", "Podcast / phỏng vấn",
        "sales_social", "Tập trung vào quan điểm, ví dụ và điều người xem có thể ghi nhớ.",
        ("Câu hỏi", "Quan điểm", "Ví dụ", "Điều rút ra"),
        narrative=("interview", "talking_head"), industry=("media",),
        visual=("speaker", "clean_frame"), platform=("youtube", "podcast", "social"),
        goal=("authority", "education"), aliases=("podcast", "phỏng vấn", "talking head"), sort_order=10,
    ),
    _profile(
        "storytelling_life", "📖", "Kể chuyện / đời sống", "Kể chuyện / đời sống",
        "story_knowledge_emotion", "Một mạch truyện có nhân vật, lựa chọn, thay đổi và kết thúc trọn vẹn.",
        ("Nhân vật", "Vấn đề", "Lựa chọn", "Thay đổi", "Kết"),
        narrative=("storytelling", "life"), industry=("general",),
        visual=("cinematic", "character"), platform=("social", "youtube"),
        goal=("retention", "emotion"), aliases=("kể chuyện", "đời sống"), sort_order=11,
    ),
    _profile(
        "short_film_trailer", "🎞", "Phim ngắn / trailer", "Phim ngắn / trailer",
        "story_knowledge_emotion", "Tạo bí ẩn, xung đột, cao trào và dư âm điện ảnh.",
        ("Mở bí ẩn", "Tăng xung đột", "Cao trào", "Dư âm"),
        narrative=("short_film", "trailer"), industry=("entertainment",),
        visual=("cinematic", "dramatic"), platform=("youtube", "social"),
        goal=("emotion", "tease"), aliases=("phim ngắn", "trailer", "điện ảnh"), sort_order=12,
    ),
    _profile(
        "tutorial_howto", "🧭", "Hướng dẫn / how-to", "Hướng dẫn / how-to",
        "story_knowledge_emotion", "Hướng dẫn từng bước, có chuẩn bị và kiểm tra kết quả.",
        ("Mục tiêu", "Chuẩn bị", "Các bước", "Kiểm tra kết quả"),
        narrative=("tutorial", "steps"), industry=("education",),
        visual=("demonstration", "clear"), platform=("youtube", "social"),
        goal=("teach", "completion"), aliases=("hướng dẫn", "how to", "tutorial"), sort_order=13,
    ),
    _profile(
        "knowledge_explainer", "💡", "Kiến thức / explainer", "Kiến thức / explainer",
        "story_knowledge_emotion", "Giải thích một khái niệm hoặc cơ chế bằng ví dụ dễ hiểu.",
        ("Câu hỏi", "Khái niệm", "Ví dụ", "Tóm tắt"),
        narrative=("explainer", "education"), industry=("education",),
        visual=("infographic", "animation"), platform=("youtube", "social"),
        goal=("understanding", "education"), aliases=("kiến thức", "giải thích", "explainer"), sort_order=14,
    ),
    _profile(
        "history_culture_mythology", "🏺", "Lịch sử / văn hóa / thần thoại", "Lịch sử / văn hóa",
        "story_knowledge_emotion", "Kể bối cảnh, sự kiện và ý nghĩa, phân biệt dữ kiện với giai thoại.",
        ("Bối cảnh", "Sự kiện hoặc nhân vật", "Diễn biến", "Ý nghĩa"),
        narrative=("history", "documentary"), industry=("culture",),
        visual=("period", "cinematic"), platform=("youtube", "social"),
        goal=("education", "heritage"), aliases=("lịch sử", "văn hóa", "thần thoại"), sort_order=15,
    ),
    _profile(
        "philosophy_morality", "🧘", "Triết lý / đạo lý", "Triết lý / đạo lý",
        "story_knowledge_emotion", "Đi từ nghịch cảnh tới lựa chọn, hệ quả và bài học.",
        ("Nghịch cảnh", "Lựa chọn", "Hệ quả", "Bài học"),
        narrative=("philosophy", "morality"), industry=("general",),
        visual=("reflective", "minimal"), platform=("social", "youtube"),
        goal=("reflection", "emotion"), aliases=("triết lý", "đạo lý", "quotes"), sort_order=16,
    ),
    _profile(
        "motivation_self_help", "🌱", "Động lực / phát triển bản thân", "Động lực / phát triển",
        "story_knowledge_emotion", "Chuyển nỗi đau thành một góc nhìn và hành động nhỏ thực tế.",
        ("Nỗi đau", "Góc nhìn", "Hành động nhỏ", "Lời nhắc"),
        narrative=("motivation", "self_help"), industry=("general",),
        visual=("inspirational", "human"), platform=("social", "podcast"),
        goal=("motivate", "save"), aliases=("động lực", "phát triển bản thân", "self help"), sort_order=17,
    ),
    _profile(
        "kids_education", "🧒", "Giáo dục trẻ em", "Giáo dục trẻ em",
        "story_knowledge_emotion", "Dùng nhân vật thân thiện và lặp có chủ đích để trẻ ghi nhớ.",
        ("Nhân vật thân thiện", "Bài học", "Lặp có chủ đích", "Kết"),
        narrative=("kids", "education"), industry=("education",),
        visual=("colorful", "animation"), platform=("youtube",),
        goal=("teach", "safe_content"), aliases=("trẻ em", "giáo dục trẻ em"), sort_order=18,
    ),
    _profile(
        "documentary_series", "🎥", "Tài liệu / documentary / series", "Tài liệu / documentary",
        "story_knowledge_emotion", "Phát triển luận đề bằng bằng chứng, phỏng vấn và diễn giải.",
        ("Luận đề", "Bằng chứng hoặc phỏng vấn", "Diễn giải", "Kết luận"),
        narrative=("documentary", "series"), industry=("media",),
        visual=("observational", "evidence"), platform=("youtube", "series"),
        goal=("inform", "authority"), aliases=("tài liệu", "documentary", "series"), sort_order=19,
    ),
    _profile(
        "asmr_relax_lofi_visualizer", "🌧", "ASMR / thư giãn / lofi / visualizer", "ASMR / lofi / visualizer",
        "story_knowledge_emotion", "Không gian ổn định, nhịp chậm và vòng lặp hình ảnh hoặc âm thanh mượt.",
        ("Không gian ổn định", "Nhịp chậm", "Âm thanh hoặc hình ảnh chính", "Vòng lặp mượt"),
        narrative=("ambient", "loop"), industry=("wellness", "music"),
        visual=("lofi", "slow", "visualizer"), platform=("youtube", "social"),
        goal=("relax", "focus"), aliases=("asmr", "lofi", "visualizer", "chill"), sort_order=20,
    ),
    _profile(
        "architecture_interior_renovation", "🏛", "Kiến trúc / nội thất / cải tạo", "Kiến trúc / nội thất",
        "industry_visual", "Trình bày hiện trạng, ý tưởng, vật liệu, ánh sáng và trạng thái hoàn thiện.",
        ("Hiện trạng", "Ý tưởng", "Vật liệu và ánh sáng", "Hoàn thiện"),
        narrative=("transformation", "walkthrough"), industry=("architecture", "interior"),
        visual=("geometry", "materials", "lighting"), platform=("social", "youtube"),
        goal=("showcase", "design"), aliases=("kiến trúc ngoại thất", "nội thất", "cải tạo không gian"), sort_order=21,
    ),
    _profile(
        "real_estate_place_walkthrough", "🏠", "Bất động sản / địa điểm / walkthrough", "BĐS / địa điểm",
        "industry_visual", "Dẫn người xem qua vị trí, luồng di chuyển, từng khu vực và điểm mạnh.",
        ("Mặt tiền hoặc vị trí", "Luồng di chuyển", "Các khu vực", "Điểm mạnh"),
        narrative=("walkthrough", "tour"), industry=("real_estate", "place"),
        visual=("spatial", "fpv"), platform=("social", "youtube"),
        goal=("showcase", "lead"), aliases=("bất động sản", "địa điểm", "walkthrough", "tham quan kiến trúc"), sort_order=22,
    ),
    _profile(
        "fashion_beauty_lookbook", "👗", "Thời trang / làm đẹp / lookbook", "Thời trang / lookbook",
        "industry_visual", "Tôn nhân vật hoặc sản phẩm bằng chi tiết, chuyển dáng và hero shot.",
        ("Nhân vật hoặc sản phẩm", "Chi tiết", "Chuyển dáng", "Hero shot"),
        narrative=("lookbook", "showcase"), industry=("fashion", "beauty"),
        visual=("editorial", "model"), platform=("social", "reels"),
        goal=("showcase", "brand"), aliases=("thời trang", "làm đẹp", "lookbook", "trình diễn"), sort_order=23,
    ),
    _profile(
        "food_cooking_asmr", "🍜", "Ẩm thực / nấu ăn / food ASMR", "Ẩm thực / nấu ăn",
        "industry_visual", "Theo nguyên liệu, thao tác, kết cấu, âm thanh và thành phẩm.",
        ("Nguyên liệu", "Thao tác", "Kết cấu và âm thanh", "Thành phẩm"),
        narrative=("process", "sensory"), industry=("food",),
        visual=("macro", "texture"), platform=("social", "youtube"),
        goal=("appetite", "teach"), aliases=("ẩm thực", "nấu ăn", "food asmr"), sort_order=24,
    ),
    _profile(
        "travel_local_experience", "🧭", "Du lịch / trải nghiệm địa phương", "Du lịch / trải nghiệm",
        "industry_visual", "Dẫn từ lúc đến nơi qua trải nghiệm, điểm nổi bật và lưu ý thực tế.",
        ("Đến nơi", "Trải nghiệm", "Điểm nổi bật", "Lưu ý và kết"),
        narrative=("journey", "review"), industry=("travel", "hospitality"),
        visual=("pov", "location"), platform=("social", "youtube"),
        goal=("inspire", "inform"), aliases=("du lịch", "trải nghiệm địa phương", "nightlife", "staycation"), sort_order=25,
    ),
    _profile(
        "sports_esports", "🏆", "Thể thao / eSports", "Thể thao / eSports",
        "industry_visual", "Phân tích bối cảnh trận, khoảnh khắc, chiến thuật và kết luận có điều kiện.",
        ("Bối cảnh trận", "Khoảnh khắc hoặc chiến thuật", "Phân tích", "Kết luận"),
        narrative=("analysis", "highlight"), industry=("sports", "esports"),
        visual=("action", "data"), platform=("social", "youtube"),
        goal=("inform", "engage"), aliases=("thể thao", "esports", "game meta"), sort_order=26,
    ),
    _profile(
        "app_website_saas", "💻", "Ứng dụng / website / SaaS", "App / website / SaaS",
        "industry_visual", "Giải thích vấn đề, giao diện, thao tác và lợi ích bằng luồng dùng thật.",
        ("Vấn đề", "Giao diện", "Thao tác", "Kết quả hoặc lợi ích"),
        narrative=("demo", "explainer"), industry=("software", "saas"),
        visual=("screen", "ui"), platform=("youtube", "linkedin", "social"),
        goal=("demo", "conversion"), aliases=("ứng dụng", "website", "saas", "phần mềm"), sort_order=27,
    ),
    _profile(
        "game_trailer", "🎮", "Trò chơi / game trailer", "Trò chơi / game trailer",
        "industry_visual", "Giới thiệu thế giới, cơ chế, nhân vật hoặc đối đầu rồi kết bằng lời mời.",
        ("Thế giới", "Cơ chế", "Nhân vật hoặc đối đầu", "Lời mời"),
        narrative=("trailer", "gameplay"), industry=("gaming",),
        visual=("game", "cinematic"), platform=("youtube", "social"),
        goal=("tease", "conversion"), aliases=("trò chơi", "game", "game trailer"), sort_order=28,
    ),
    _profile(
        "engineering_industry_automation", "🏭", "Kỹ thuật / công nghiệp / tự động hóa", "Kỹ thuật / công nghiệp",
        "industry_visual", "Trình bày bài toán, thiết bị, quy trình vận hành và kết quả đo được.",
        ("Bài toán", "Quy trình hoặc thiết bị", "Vận hành", "Kết quả"),
        narrative=("process", "case_study"), industry=("engineering", "industry", "automation"),
        visual=("technical", "machine"), platform=("youtube", "linkedin"),
        goal=("explain", "b2b"), aliases=("kỹ thuật", "công nghiệp", "tự động hóa", "elv"), sort_order=29,
    ),
    _profile(
        "product_3d_showcase", "📦", "Trưng bày sản phẩm / 3D", "Sản phẩm / 3D",
        "industry_visual", "Tạo hero shot, chi tiết vật liệu, công năng và khung kết thương hiệu.",
        ("Hero shot", "Chi tiết và vật liệu", "Công năng", "Khung kết thương hiệu"),
        narrative=("showcase", "demo"), industry=("product",),
        visual=("3d", "macro", "studio"), platform=("social", "web"),
        goal=("showcase", "conversion"), aliases=("trưng bày sản phẩm", "3d showcase", "sản phẩm 3d"), sort_order=30,
    ),
    _profile(
        "character_animation_vfx", "🧸", "Nhân vật / hoạt hình / VFX", "Nhân vật / hoạt hình / VFX",
        "industry_visual", "Khóa nhận diện nhân vật, hành động, hiệu ứng và continuity qua các cảnh.",
        ("Khóa nhận diện", "Hành động", "Hiệu ứng", "Continuity"),
        narrative=("character", "animation"), industry=("animation", "vfx"),
        visual=("2d", "3d", "vfx"), platform=("social", "youtube"),
        goal=("story", "spectacle"), aliases=("nhân vật", "hoạt hình", "vfx", "hiệu ứng điện ảnh"), sort_order=31,
    ),
    _profile(
        "music_video_performance", "🎵", "Music video / biểu diễn", "Music video / biểu diễn",
        "industry_visual", "Đồng bộ nhịp nhạc với hình ảnh chủ đạo, cao trào và khung kết biểu tượng.",
        ("Nhịp nhạc", "Hình ảnh chủ đạo", "Cao trào", "Khung kết biểu tượng"),
        narrative=("performance", "rhythm"), industry=("music", "event"),
        visual=("performance", "rhythmic"), platform=("youtube", "social"),
        goal=("entertain", "brand"), aliases=("music video", "biểu diễn", "nhạc hình"), sort_order=32,
    ),
)


PROFILE_BY_KEY = {str(item["profile_key"]): dict(item) for item in PROFILE_SEEDS}
PAGE_GROUP_BY_KEY = {key: label for key, label in PAGE_GROUPS}


PROFILE_LINK_TARGETS = {
    "sales_ads": ("product_review_demo", "affiliate_ugc", "product_3d_showcase", "app_website_saas"),
    "product_review_demo": (
        "sales_ads",
        "affiliate_ugc",
        "testimonial_case_study",
        "product_3d_showcase",
        "app_website_saas",
    ),
    "affiliate_ugc": ("product_review_demo", "social_creator_trend", "fashion_beauty_lookbook", "food_cooking_asmr", "travel_local_experience"),
    "testimonial_case_study": ("sales_ads", "brand_corporate", "app_website_saas", "engineering_industry_automation"),
    "brand_corporate": ("testimonial_case_study", "documentary_series", "event_highlight", "engineering_industry_automation"),
    "social_creator_trend": ("affiliate_ugc", "meme_parody_comedy", "event_highlight", "character_animation_vfx"),
    "meme_parody_comedy": ("social_creator_trend", "character_animation_vfx", "short_film_trailer"),
    "event_highlight": ("brand_corporate", "sports_esports", "music_video_performance"),
    "news_data_analysis": ("knowledge_explainer", "documentary_series", "engineering_industry_automation", "sports_esports"),
    "podcast_interview_talking_head": ("motivation_self_help", "philosophy_morality", "knowledge_explainer", "testimonial_case_study"),
    "storytelling_life": ("short_film_trailer", "philosophy_morality", "motivation_self_help", "character_animation_vfx"),
    "short_film_trailer": ("storytelling_life", "character_animation_vfx", "history_culture_mythology", "game_trailer"),
    "tutorial_howto": ("knowledge_explainer", "app_website_saas", "engineering_industry_automation", "food_cooking_asmr"),
    "knowledge_explainer": ("tutorial_howto", "news_data_analysis", "app_website_saas", "character_animation_vfx"),
    "history_culture_mythology": ("documentary_series", "short_film_trailer", "storytelling_life", "character_animation_vfx"),
    "philosophy_morality": ("storytelling_life", "motivation_self_help", "podcast_interview_talking_head"),
    "motivation_self_help": ("podcast_interview_talking_head", "philosophy_morality", "social_creator_trend"),
    "kids_education": ("knowledge_explainer", "storytelling_life", "character_animation_vfx"),
    "documentary_series": ("news_data_analysis", "history_culture_mythology", "brand_corporate", "podcast_interview_talking_head"),
    "asmr_relax_lofi_visualizer": ("food_cooking_asmr", "music_video_performance", "travel_local_experience"),
    "architecture_interior_renovation": ("real_estate_place_walkthrough", "product_3d_showcase", "engineering_industry_automation"),
    "real_estate_place_walkthrough": ("architecture_interior_renovation", "travel_local_experience", "sales_ads"),
    "fashion_beauty_lookbook": ("sales_ads", "affiliate_ugc", "character_animation_vfx", "product_3d_showcase"),
    "food_cooking_asmr": ("tutorial_howto", "affiliate_ugc", "asmr_relax_lofi_visualizer", "sales_ads"),
    "travel_local_experience": ("affiliate_ugc", "real_estate_place_walkthrough", "event_highlight", "documentary_series"),
    "sports_esports": ("event_highlight", "news_data_analysis", "game_trailer", "social_creator_trend"),
    "app_website_saas": ("tutorial_howto", "product_review_demo", "sales_ads", "testimonial_case_study"),
    "game_trailer": ("short_film_trailer", "sports_esports", "character_animation_vfx"),
    "engineering_industry_automation": ("tutorial_howto", "news_data_analysis", "brand_corporate", "app_website_saas"),
    "product_3d_showcase": ("sales_ads", "product_review_demo", "fashion_beauty_lookbook", "architecture_interior_renovation"),
    "character_animation_vfx": ("storytelling_life", "short_film_trailer", "kids_education", "meme_parody_comedy"),
    "music_video_performance": ("event_highlight", "asmr_relax_lofi_visualizer", "fashion_beauty_lookbook", "character_animation_vfx"),
}


LEGACY_CONTENT_PROFILE_MAP = {
    "storytelling": ("storytelling_life", ("short_film_trailer", "philosophy_morality")),
    "product_review": ("product_review_demo", ("sales_ads", "affiliate_ugc")),
    "news": ("news_data_analysis", ("knowledge_explainer", "documentary_series")),
    "philosophy_quotes": ("philosophy_morality", ("podcast_interview_talking_head", "motivation_self_help")),
    "educational": ("knowledge_explainer", ("tutorial_howto", "kids_education")),
    "history": ("history_culture_mythology", ("short_film_trailer", "documentary_series")),
    "ugc_affiliate": ("affiliate_ugc", ("sales_ads", "social_creator_trend")),
    "real_estate_fpv": ("real_estate_place_walkthrough", ("architecture_interior_renovation", "travel_local_experience")),
    "fashion_lookbook": ("fashion_beauty_lookbook", ("sales_ads", "product_3d_showcase")),
    "food_asmr": ("food_cooking_asmr", ("tutorial_howto", "asmr_relax_lofi_visualizer")),
    "lofi_audio_visualizer": ("asmr_relax_lofi_visualizer", ("music_video_performance",)),
    "cinematic_trailer": ("short_film_trailer", ("storytelling_life", "character_animation_vfx")),
}

LEGACY_TECHNICAL_PROFILE_MAP = {
    "architecture_exterior": ("architecture_interior_renovation", ()),
    "architecture_interior": ("architecture_interior_renovation", ()),
    "space_renovation": ("architecture_interior_renovation", ()),
    "real_estate_property": ("real_estate_place_walkthrough", ()),
    "architecture_walkthrough": ("real_estate_place_walkthrough", ()),
    "cinematic_vfx": ("character_animation_vfx", ("short_film_trailer",)),
    "animation_2d_3d": ("character_animation_vfx", ()),
    "character": ("character_animation_vfx", ("storytelling_life",)),
    "fashion_lookbook": ("fashion_beauty_lookbook", ()),
    "product_3d_showcase": ("product_3d_showcase", ()),
    "app_game_demo": ("app_website_saas", ("game_trailer",)),
    "website_saas_demo": ("app_website_saas", ()),
    "tutorial_explainer": ("tutorial_howto", ("knowledge_explainer",)),
    "ugc_social_creator": ("affiliate_ugc", ("social_creator_trend",)),
}

IDEA_GROUP_PROFILE_MAP = {
    "sales": ("sales_ads",),
    "ugc": ("affiliate_ugc", "social_creator_trend"),
    "education": ("tutorial_howto", "knowledge_explainer"),
    "story": ("storytelling_life", "short_film_trailer"),
    "space": ("architecture_interior_renovation", "real_estate_place_walkthrough"),
    "lifestyle": ("fashion_beauty_lookbook", "food_cooking_asmr"),
    "digital": ("app_website_saas", "game_trailer"),
    "visual": ("event_highlight", "music_video_performance"),
    "history": ("history_culture_mythology",),
    "sports": ("sports_esports",),
    "travel": ("travel_local_experience",),
    "industry": ("engineering_industry_automation",),
    "data_news": ("news_data_analysis",),
    "self_help": ("motivation_self_help",),
    "meme": ("social_creator_trend", "meme_parody_comedy"),
    "asmr": ("asmr_relax_lofi_visualizer",),
}


CANONICAL_CONTENT_TYPE = {
    "sales_ads": "product_review",
    "product_review_demo": "product_review",
    "affiliate_ugc": "ugc_affiliate",
    "testimonial_case_study": "product_review",
    "brand_corporate": "storytelling",
    "social_creator_trend": "ugc_affiliate",
    "meme_parody_comedy": "storytelling",
    "event_highlight": "cinematic_trailer",
    "news_data_analysis": "news",
    "podcast_interview_talking_head": "philosophy_quotes",
    "storytelling_life": "storytelling",
    "short_film_trailer": "cinematic_trailer",
    "tutorial_howto": "educational",
    "knowledge_explainer": "educational",
    "history_culture_mythology": "history",
    "philosophy_morality": "philosophy_quotes",
    "motivation_self_help": "philosophy_quotes",
    "kids_education": "educational",
    "documentary_series": "news",
    "asmr_relax_lofi_visualizer": "lofi_audio_visualizer",
    "architecture_interior_renovation": "real_estate_fpv",
    "real_estate_place_walkthrough": "real_estate_fpv",
    "fashion_beauty_lookbook": "fashion_lookbook",
    "food_cooking_asmr": "food_asmr",
    "travel_local_experience": "real_estate_fpv",
    "sports_esports": "news",
    "app_website_saas": "educational",
    "game_trailer": "cinematic_trailer",
    "engineering_industry_automation": "educational",
    "product_3d_showcase": "product_review",
    "character_animation_vfx": "storytelling",
    "music_video_performance": "lofi_audio_visualizer",
}

CANONICAL_TECHNICAL_PROFILE = {
    "sales_ads": "product_3d_showcase",
    "product_review_demo": "product_3d_showcase",
    "affiliate_ugc": "ugc_social_creator",
    "testimonial_case_study": "ugc_social_creator",
    "brand_corporate": "cinematic_vfx",
    "social_creator_trend": "ugc_social_creator",
    "meme_parody_comedy": "animation_2d_3d",
    "event_highlight": "cinematic_vfx",
    "news_data_analysis": "tutorial_explainer",
    "podcast_interview_talking_head": "character",
    "storytelling_life": "character",
    "short_film_trailer": "cinematic_vfx",
    "tutorial_howto": "tutorial_explainer",
    "knowledge_explainer": "tutorial_explainer",
    "history_culture_mythology": "cinematic_vfx",
    "philosophy_morality": "character",
    "motivation_self_help": "character",
    "kids_education": "animation_2d_3d",
    "documentary_series": "cinematic_vfx",
    "asmr_relax_lofi_visualizer": "animation_2d_3d",
    "architecture_interior_renovation": "architecture_interior",
    "real_estate_place_walkthrough": "real_estate_property",
    "fashion_beauty_lookbook": "fashion_lookbook",
    "food_cooking_asmr": "product_3d_showcase",
    "travel_local_experience": "architecture_walkthrough",
    "sports_esports": "app_game_demo",
    "app_website_saas": "website_saas_demo",
    "game_trailer": "app_game_demo",
    "engineering_industry_automation": "tutorial_explainer",
    "product_3d_showcase": "product_3d_showcase",
    "character_animation_vfx": "animation_2d_3d",
    "music_video_performance": "cinematic_vfx",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _json_text(value: Any) -> str:
    return json.dumps(value if value is not None else [], ensure_ascii=False, sort_keys=True)


def _json_value(value: Any, fallback: Any) -> Any:
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _normalized(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def profile_seeds() -> list[dict[str, Any]]:
    return [dict(item) for item in PROFILE_SEEDS]


def link_seeds() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source, targets in PROFILE_LINK_TARGETS.items():
        for offset, target in enumerate(targets):
            relation_type = "recommended_with"
            if source == "product_review_demo" and target == "sales_ads":
                relation_type = "subtype_of"
            elif source == "short_film_trailer" and target == "storytelling_life":
                relation_type = "alternative_to"
            elif source == "character_animation_vfx" and target == "short_film_trailer":
                relation_type = "visual_style_for"
            elif source == "product_review_demo" and target == "product_3d_showcase":
                relation_type = "visual_style_for"
            elif source == "product_review_demo" and target == "app_website_saas":
                relation_type = "domain_overlay_for"
            rows.append({
                "source_profile_key": source,
                "target_profile_key": target,
                "relation_type": relation_type,
                "weight": max(1, 100 - offset * 10),
                "reason": _link_reason(source, target),
                "is_active": 1,
            })
    return rows


def _link_reason(source_key: str, target_key: str) -> str:
    source = PROFILE_BY_KEY.get(source_key, {})
    target = PROFILE_BY_KEY.get(target_key, {})
    source_name = str(source.get("short_name") or source_key)
    target_name = str(target.get("short_name") or target_key)
    return f"{target_name} bổ sung góc kể, ngành hoặc hình ảnh phù hợp cho {source_name}."


def ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS video_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_key TEXT NOT NULL UNIQUE,
            icon TEXT NOT NULL DEFAULT '🎯',
            public_name TEXT NOT NULL,
            short_name TEXT NOT NULL,
            page_group TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            narrative_tags TEXT NOT NULL DEFAULT '[]',
            industry_tags TEXT NOT NULL DEFAULT '[]',
            visual_tags TEXT NOT NULL DEFAULT '[]',
            platform_tags TEXT NOT NULL DEFAULT '[]',
            goal_tags TEXT NOT NULL DEFAULT '[]',
            default_scene_pattern TEXT NOT NULL DEFAULT '[]',
            clarification_questions TEXT NOT NULL DEFAULT '[]',
            aliases TEXT NOT NULL DEFAULT '[]',
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by TEXT NOT NULL DEFAULT 'system'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS video_profile_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_profile_key TEXT NOT NULL,
            target_profile_key TEXT NOT NULL,
            relation_type TEXT NOT NULL DEFAULT 'recommended_with',
            weight INTEGER NOT NULL DEFAULT 0,
            reason TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1,
            version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by TEXT NOT NULL DEFAULT 'system',
            UNIQUE(source_profile_key, target_profile_key, relation_type)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_video_profiles_active_page_sort "
        "ON video_profiles(is_active, page_group, sort_order, id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_video_profile_links_source_active_weight "
        "ON video_profile_links(source_profile_key, is_active, weight DESC, id)"
    )


def seed_catalog(conn, *, actor_id: str = "system_seed") -> dict[str, int]:
    ensure_schema(conn)
    now = _now()
    profile_count = 0
    link_count = 0
    for item in profile_seeds():
        before = conn.total_changes
        conn.execute(
            """
            INSERT OR IGNORE INTO video_profiles
                (profile_key, icon, public_name, short_name, page_group, description,
                 narrative_tags, industry_tags, visual_tags, platform_tags, goal_tags,
                 default_scene_pattern, clarification_questions, aliases, sort_order,
                 is_active, version, created_at, updated_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (
                item["profile_key"], item["icon"], item["public_name"], item["short_name"],
                item["page_group"], item["description"], _json_text(item["narrative_tags"]),
                _json_text(item["industry_tags"]), _json_text(item["visual_tags"]),
                _json_text(item["platform_tags"]), _json_text(item["goal_tags"]),
                _json_text(item["default_scene_pattern"]),
                _json_text(item["clarification_questions"]), _json_text(item["aliases"]),
                int(item["sort_order"]), int(bool(item["is_active"])), now, now, actor_id,
            ),
        )
        profile_count += int(conn.total_changes > before)
    for item in link_seeds():
        before = conn.total_changes
        conn.execute(
            """
            INSERT OR IGNORE INTO video_profile_links
                (source_profile_key, target_profile_key, relation_type, weight, reason,
                 is_active, version, created_at, updated_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (
                item["source_profile_key"], item["target_profile_key"],
                item["relation_type"], int(item["weight"]), item["reason"],
                int(bool(item["is_active"])), now, now, actor_id,
            ),
        )
        link_count += int(conn.total_changes > before)
    return {"profiles_inserted": profile_count, "links_inserted": link_count}


def _decode_profile(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for field in (
        "narrative_tags", "industry_tags", "visual_tags", "platform_tags",
        "goal_tags", "default_scene_pattern", "clarification_questions", "aliases",
    ):
        result[field] = list(_json_value(result.get(field), []))
    result["is_active"] = bool(result.get("is_active"))
    return result


def list_profiles(conn, *, page_group: str = "", active_only: bool = True) -> list[dict[str, Any]]:
    ensure_schema(conn)
    clauses: list[str] = []
    values: list[Any] = []
    if active_only:
        clauses.append("is_active=1")
    if page_group:
        clauses.append("page_group=?")
        values.append(str(page_group))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    cursor = conn.execute(
        f"SELECT * FROM video_profiles {where} ORDER BY sort_order, id",
        tuple(values),
    )
    names = [str(item[0]) for item in cursor.description or ()]
    return [_decode_profile(dict(zip(names, row))) for row in cursor.fetchall()]


def profile_by_key(conn, profile_key: str, *, active_only: bool = False) -> dict[str, Any]:
    ensure_schema(conn)
    query = "SELECT * FROM video_profiles WHERE profile_key=?"
    values: list[Any] = [str(profile_key or "")]
    if active_only:
        query += " AND is_active=1"
    row = conn.execute(query, tuple(values)).fetchone()
    if not row:
        return {}
    names = [str(item[1]) for item in conn.execute("PRAGMA table_info(video_profiles)").fetchall()]
    return _decode_profile(dict(zip(names, row)))


def links_for_profile(conn, profile_key: str, *, active_only: bool = True, limit: int = 5) -> list[dict[str, Any]]:
    ensure_schema(conn)
    query = (
        "SELECT l.*, p.icon, p.public_name, p.short_name, p.page_group "
        "FROM video_profile_links l "
        "JOIN video_profiles p ON p.profile_key=l.target_profile_key "
        "WHERE l.source_profile_key=?"
    )
    values: list[Any] = [str(profile_key or "")]
    if active_only:
        query += " AND l.is_active=1 AND p.is_active=1"
    query += " ORDER BY l.weight DESC, p.sort_order, l.id LIMIT ?"
    values.append(max(1, int(limit or 5)))
    cursor = conn.execute(query, tuple(values))
    names = [str(item[0]) for item in cursor.description or ()]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def upsert_profile(conn, payload: Mapping[str, Any], *, actor_id: str = "admin") -> dict[str, Any]:
    ensure_schema(conn)
    profile_key = str(payload.get("profile_key") or "").strip()
    if not PROFILE_KEY_RE.fullmatch(profile_key):
        raise ValueError("invalid_video_profile_key")
    page_group = str(payload.get("page_group") or "")
    if page_group not in PAGE_GROUP_BY_KEY:
        raise ValueError("invalid_video_profile_page_group")
    now = _now()
    item = {
        "profile_key": profile_key,
        "icon": str(payload.get("icon") or "🎯")[:8],
        "public_name": str(payload.get("public_name") or "").strip(),
        "short_name": str(payload.get("short_name") or payload.get("public_name") or "").strip(),
        "page_group": page_group,
        "description": str(payload.get("description") or "").strip(),
        "narrative_tags": list(payload.get("narrative_tags") or []),
        "industry_tags": list(payload.get("industry_tags") or []),
        "visual_tags": list(payload.get("visual_tags") or []),
        "platform_tags": list(payload.get("platform_tags") or []),
        "goal_tags": list(payload.get("goal_tags") or []),
        "default_scene_pattern": list(payload.get("default_scene_pattern") or []),
        "clarification_questions": list(payload.get("clarification_questions") or []),
        "aliases": list(payload.get("aliases") or []),
        "sort_order": int(payload.get("sort_order") or 999),
        "is_active": int(bool(payload.get("is_active", True))),
    }
    if not item["public_name"] or not item["short_name"] or not item["default_scene_pattern"]:
        raise ValueError("incomplete_video_profile")
    conn.execute(
        """
        INSERT INTO video_profiles
            (profile_key, icon, public_name, short_name, page_group, description,
             narrative_tags, industry_tags, visual_tags, platform_tags, goal_tags,
             default_scene_pattern, clarification_questions, aliases, sort_order,
             is_active, version, created_at, updated_at, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
        ON CONFLICT(profile_key) DO UPDATE SET
            icon=excluded.icon,
            public_name=excluded.public_name,
            short_name=excluded.short_name,
            page_group=excluded.page_group,
            description=excluded.description,
            narrative_tags=excluded.narrative_tags,
            industry_tags=excluded.industry_tags,
            visual_tags=excluded.visual_tags,
            platform_tags=excluded.platform_tags,
            goal_tags=excluded.goal_tags,
            default_scene_pattern=excluded.default_scene_pattern,
            clarification_questions=excluded.clarification_questions,
            aliases=excluded.aliases,
            sort_order=excluded.sort_order,
            is_active=excluded.is_active,
            version=video_profiles.version+1,
            updated_at=excluded.updated_at,
            created_by=excluded.created_by
        """,
        (
            item["profile_key"], item["icon"], item["public_name"], item["short_name"],
            item["page_group"], item["description"], _json_text(item["narrative_tags"]),
            _json_text(item["industry_tags"]), _json_text(item["visual_tags"]),
            _json_text(item["platform_tags"]), _json_text(item["goal_tags"]),
            _json_text(item["default_scene_pattern"]),
            _json_text(item["clarification_questions"]), _json_text(item["aliases"]),
            item["sort_order"], item["is_active"], now, now, actor_id,
        ),
    )
    return profile_by_key(conn, profile_key)


def upsert_link(conn, payload: Mapping[str, Any], *, actor_id: str = "admin") -> dict[str, Any]:
    ensure_schema(conn)
    source = str(payload.get("source_profile_key") or "")
    target = str(payload.get("target_profile_key") or "")
    relation_type = str(payload.get("relation_type") or "recommended_with")
    if source == target or not profile_by_key(conn, source) or not profile_by_key(conn, target):
        raise ValueError("invalid_video_profile_link")
    if relation_type not in RELATION_TYPES:
        raise ValueError("invalid_video_profile_relation_type")
    now = _now()
    conn.execute(
        """
        INSERT INTO video_profile_links
            (source_profile_key, target_profile_key, relation_type, weight, reason,
             is_active, version, created_at, updated_at, created_by)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
        ON CONFLICT(source_profile_key, target_profile_key, relation_type) DO UPDATE SET
            weight=excluded.weight,
            reason=excluded.reason,
            is_active=excluded.is_active,
            version=video_profile_links.version+1,
            updated_at=excluded.updated_at,
            created_by=excluded.created_by
        """,
        (
            source, target, relation_type, int(payload.get("weight") or 0),
            str(payload.get("reason") or ""), int(bool(payload.get("is_active", True))),
            now, now, actor_id,
        ),
    )
    cursor = conn.execute(
        "SELECT * FROM video_profile_links WHERE source_profile_key=? AND target_profile_key=? AND relation_type=?",
        (source, target, relation_type),
    )
    row = cursor.fetchone()
    names = [str(item[0]) for item in cursor.description or ()]
    return dict(zip(names, row)) if row else {}


def canonical_profile_key(value: Any) -> str:
    raw = str(value or "").strip()
    if raw in PROFILE_BY_KEY:
        return raw
    normalized = _normalized(raw)
    if not normalized:
        return ""
    for item in PROFILE_SEEDS:
        aliases = list(item.get("aliases") or [])
        if any(_normalized(alias) == normalized for alias in aliases):
            return str(item["profile_key"])
    legacy = LEGACY_TECHNICAL_PROFILE_MAP.get(raw) or LEGACY_CONTENT_PROFILE_MAP.get(raw)
    return str((legacy or ("", ()))[0])


def canonical_bundle_from_legacy(content_type: str = "", technical_profile: str = "") -> dict[str, Any]:
    technical = LEGACY_TECHNICAL_PROFILE_MAP.get(str(technical_profile or ""))
    content = LEGACY_CONTENT_PROFILE_MAP.get(str(content_type or ""))
    primary = str((technical or content or ("", ()))[0])
    linked: list[str] = []
    for source in (technical, content):
        for item in (source or ("", ()))[1]:
            if item and item != primary and item not in linked:
                linked.append(item)
    return {"primary_profile": primary, "linked_profiles": linked[:MAX_LINKED_PROFILES]}


def migrate_session_profile_state(state: Mapping[str, Any] | None) -> dict[str, Any]:
    current = dict(state or {})
    try:
        bundle_version = int(current.get("profile_bundle_version") or 0)
    except (TypeError, ValueError):
        bundle_version = 0
    legacy_session = bundle_version < SCHEMA_VERSION
    primary_raw = str(current.get("primary_profile") or "")
    had_explicit_primary = bool(primary_raw)
    primary = canonical_profile_key(primary_raw)
    if primary_raw == "custom":
        primary = "custom"
    elif not primary and PROFILE_KEY_RE.fullmatch(primary_raw):
        # Admin-created profiles are stored in SQLite and may not be part of
        # the built-in seed list. Preserve their stable key during session
        # normalization; the public route validates active status from DB.
        primary = primary_raw
    legacy_bundle = canonical_bundle_from_legacy(
        str(current.get("content_type") or ""),
        str(current.get("technical_profile") or ""),
    )
    if not primary and legacy_session:
        primary = str(legacy_bundle.get("primary_profile") or "")
    linked: list[str] = []
    legacy_linked = (
        []
        if had_explicit_primary or not legacy_session
        else list(legacy_bundle.get("linked_profiles") or [])
    )
    for item in list(current.get("linked_profiles") or []) + legacy_linked:
        raw_key = str(item or "").strip()
        key = canonical_profile_key(raw_key)
        if not key and PROFILE_KEY_RE.fullmatch(raw_key):
            key = raw_key
        if key and key != primary and key not in linked:
            linked.append(key)
    page = max(1, min(len(PAGE_GROUPS), int(current.get("profile_page") or 1)))
    return {
        "primary_profile": primary,
        "linked_profiles": linked[:MAX_LINKED_PROFILES],
        "profile_page": page,
        "profile_suggestion_keys": [
            key for key in (
                canonical_profile_key(item)
                for item in current.get("profile_suggestion_keys") or []
            )
            if key and key != primary
        ][:5],
        "profile_bundle_version": SCHEMA_VERSION,
    }


def profile_label(profile_key: str, custom_profile: str = "") -> str:
    if str(profile_key or "") == "custom":
        return str(custom_profile or "Profile tự nhập")[:180]
    item = PROFILE_BY_KEY.get(canonical_profile_key(profile_key), {})
    return str(item.get("public_name") or "Video Profile chưa xác định")


def select_primary_profile(
    state: Mapping[str, Any] | None,
    profile_key: str,
    *,
    custom_profile: str = "",
) -> dict[str, Any]:
    """Select one primary profile without auto-enabling related profiles."""

    current = dict(state or {})
    raw_key = str(profile_key or "").strip()
    key = canonical_profile_key(raw_key)
    if raw_key == "custom":
        key = "custom"
    elif not key and PROFILE_KEY_RE.fullmatch(raw_key):
        key = raw_key
    if not key:
        raise ValueError("invalid_video_profile")
    current.update({
        "primary_profile": key,
        "linked_profiles": [],
        "profile_page": profile_page(key) if key in PROFILE_BY_KEY else max(1, int(current.get("profile_page") or 1)),
        "profile_suggestion_keys": [],
        "profile_bundle_version": SCHEMA_VERSION,
    })
    if key == "custom":
        current["custom_technical_profile"] = str(custom_profile or "")[:300]
        current["technical_profile"] = "custom"
        current["content_type"] = str(current.get("content_type") or "storytelling")
    else:
        current["technical_profile"] = technical_profile_for_profile(key)
        current["content_type"] = content_type_for_profile(key)
    return current


def toggle_linked_profile(
    state: Mapping[str, Any] | None,
    profile_key: str,
    *,
    max_linked: int = MAX_LINKED_PROFILES,
) -> tuple[dict[str, Any], bool]:
    """Toggle one linked profile and report whether the requested state changed."""

    current = dict(state or {})
    primary = str(current.get("primary_profile") or "")
    raw_key = str(profile_key or "").strip()
    key = canonical_profile_key(raw_key)
    if not key and PROFILE_KEY_RE.fullmatch(raw_key):
        key = raw_key
    if not key or key == primary:
        return current, False
    linked: list[str] = []
    for item in current.get("linked_profiles") or []:
        item_key = str(item or "").strip()
        if item_key and item_key != primary and item_key not in linked:
            linked.append(item_key)
    if key in linked:
        linked.remove(key)
        current["linked_profiles"] = linked
        return current, True
    if len(linked) >= max(0, int(max_linked)):
        return current, False
    linked.append(key)
    current["linked_profiles"] = linked
    return current, True


def content_type_for_profile(profile_key: str, fallback: str = "storytelling") -> str:
    return str(CANONICAL_CONTENT_TYPE.get(canonical_profile_key(profile_key)) or fallback)


def technical_profile_for_profile(profile_key: str, fallback: str = "tutorial_explainer") -> str:
    return str(CANONICAL_TECHNICAL_PROFILE.get(canonical_profile_key(profile_key)) or fallback)


def profile_page(profile_key: str) -> int:
    item = PROFILE_BY_KEY.get(canonical_profile_key(profile_key), {})
    page_group = str(item.get("page_group") or PAGE_GROUPS[0][0])
    return next((index for index, (key, _label) in enumerate(PAGE_GROUPS, 1) if key == page_group), 1)


def linked_candidates(profile_key: str, *, limit: int = 5) -> list[dict[str, Any]]:
    source = canonical_profile_key(profile_key)
    rows: list[dict[str, Any]] = []
    for offset, target in enumerate(PROFILE_LINK_TARGETS.get(source, ())[:max(1, int(limit or 5))]):
        item = dict(PROFILE_BY_KEY.get(target) or {})
        if not item:
            continue
        rows.append({
            **item,
            "source_profile_key": source,
            "target_profile_key": target,
            "relation_type": "recommended_with",
            "weight": max(1, 100 - offset * 10),
            "reason": _link_reason(source, target),
        })
    return rows


def suggest_primary_profiles(subject: str, scene_count: int, *, limit: int = 5) -> list[dict[str, Any]]:
    tokens = set(_normalized(subject).split())
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for item in PROFILE_SEEDS:
        searchable = " ".join(
            [
                str(item.get("public_name") or ""),
                str(item.get("description") or ""),
                *[str(value) for value in item.get("aliases") or []],
                *[str(value) for value in item.get("industry_tags") or []],
                *[str(value) for value in item.get("goal_tags") or []],
            ]
        )
        profile_tokens = set(_normalized(searchable).split())
        score = len(tokens & profile_tokens) * 4
        pattern_length = len(item.get("default_scene_pattern") or [])
        score += 1 if int(scene_count or 0) >= pattern_length else 0
        scored.append((score, -int(item["sort_order"]), dict(item)))
    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    if not scored or scored[0][0] <= 0:
        fallback_keys = ("storytelling_life", "sales_ads", "knowledge_explainer", "affiliate_ugc", "short_film_trailer")
        return [dict(PROFILE_BY_KEY[key]) for key in fallback_keys[:max(1, int(limit or 5))]]
    return [item for _score, _order, item in scored[:max(1, int(limit or 5))]]


def profile_bundle_context(primary_profile: str, linked_profiles: Iterable[str] = ()) -> str:
    primary = PROFILE_BY_KEY.get(canonical_profile_key(primary_profile), {})
    linked = [
        PROFILE_BY_KEY.get(canonical_profile_key(item), {})
        for item in linked_profiles
        if canonical_profile_key(item) and canonical_profile_key(item) != canonical_profile_key(primary_profile)
    ][:MAX_LINKED_PROFILES]
    primary_name = str(primary.get("public_name") or primary_profile or "Video Profile")
    pattern = " → ".join(str(item) for item in primary.get("default_scene_pattern") or [])
    linked_names = ", ".join(str(item.get("public_name") or "") for item in linked if item)
    result = f"Profile chính: {primary_name}. Khung kể chuyện: {pattern}."
    if linked_names:
        result += f" Profile liên kết chỉ bổ sung ngành/hình ảnh/nền tảng: {linked_names}."
    return result


def semantic_beats_for_bundle(primary_profile: str, linked_profiles: Iterable[str], scene_count: int) -> list[dict[str, Any]]:
    primary = PROFILE_BY_KEY.get(canonical_profile_key(primary_profile), PROFILE_BY_KEY["storytelling_life"])
    pattern = [str(item) for item in primary.get("default_scene_pattern") or []]
    count = max(1, min(20, int(scene_count or 1)))
    if not pattern:
        pattern = ["Mở đầu", "Phát triển", "Kết quả"]
    positions = (
        [0]
        if count == 1
        else [round(index * (len(pattern) - 1) / (count - 1)) for index in range(count)]
    )
    linked_names = [
        profile_label(item)
        for item in list(linked_profiles or [])[:MAX_LINKED_PROFILES]
        if canonical_profile_key(item)
    ]
    linked_note = f"; bổ sung góc nhìn {', '.join(linked_names)}" if linked_names else ""
    totals = {position: positions.count(position) for position in set(positions)}
    occurrences: dict[int, int] = {}
    beats: list[dict[str, Any]] = []
    for index, position in enumerate(positions, 1):
        title = pattern[position]
        occurrences[position] = occurrences.get(position, 0) + 1
        occurrence = occurrences[position]
        total = totals[position]
        if total == 1:
            beat_title = title
        elif occurrence == 1:
            beat_title = f"Mở nhịp {title.lower()}"
        elif occurrence == total:
            beat_title = f"Hoàn tất {title.lower()}"
        else:
            beat_title = f"Phát triển {title.lower()} - lớp {occurrence - 1}/{max(1, total - 2)}"
        beats.append({
            "role": "opening" if index == 1 else ("conclusion" if index == count else "development"),
            "main_idea": f"{beat_title} cho {primary['public_name']}{linked_note}",
            "action": f"Hoàn tất hành động riêng của phần {beat_title.lower()} trong cảnh {index}",
            "development": f"Phát triển trọn vẹn {beat_title.lower()}, không lặp ý hoặc cắt giữa hành động.",
            "completion": f"Phần {beat_title.lower()} đã kết thúc tự nhiên và sẵn sàng nối sang cảnh tiếp theo.",
        })
    return beats


def mapping_status() -> dict[str, Any]:
    return {
        "profiles": len(PROFILE_SEEDS),
        "pages": len(PAGE_GROUPS),
        "legacy_content_types": len(LEGACY_CONTENT_PROFILE_MAP),
        "legacy_technical_profiles": len(LEGACY_TECHNICAL_PROFILE_MAP),
        "idea_groups": len(IDEA_GROUP_PROFILE_MAP),
        "duplicate_public_names": len(PROFILE_SEEDS) - len({item["public_name"] for item in PROFILE_SEEDS}),
        "dead_link_targets": sorted({
            target
            for targets in PROFILE_LINK_TARGETS.values()
            for target in targets
            if target not in PROFILE_BY_KEY
        }),
        "provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "files_generated": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }
