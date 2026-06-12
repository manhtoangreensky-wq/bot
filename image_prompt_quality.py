import re


PURPOSE_LABELS = {
    "product_photo": "Ảnh sản phẩm",
    "ad_creative": "Ảnh quảng cáo",
    "logo_branding": "Logo / nhận diện thương hiệu",
    "social_banner": "Banner / social post",
    "cinematic_key_visual": "Key visual cinematic",
    "avatar_character": "Chân dung / nhân vật",
    "tech_ai_visual": "Công nghệ / AI",
    "lifestyle_scene": "Lifestyle",
    "food_restaurant": "Ẩm thực / nhà hàng",
    "real_estate": "Bất động sản / nội thất",
    "fashion_model": "Thời trang / người mẫu",
    "custom": "Yêu cầu tùy chỉnh",
}

PURPOSE_TEMPLATES = {
    "product_photo": (
        "Professional product photography of {request}; clear main subject; centered commercial composition; "
        "clean studio background or suitable lifestyle context; realistic materials and texture; clean shadows; "
        "suitable for ecommerce and social media advertising"
    ),
    "ad_creative": (
        "Advertising key visual for {request}; strong visual hook; clear focal point; modern commercial layout; "
        "brand-friendly color palette; space for a headline or caption overlay; social-media-ready composition"
    ),
    "logo_branding": (
        "Minimal modern brand identity concept for {request}; simple geometric symbol; clean vector-like look; "
        "professional, scalable design; uncluttered background; technology and automation feeling when relevant; "
        "concept-first composition without complex generated lettering"
    ),
    "social_banner": (
        "Modern social media banner for {request}; clear visual hierarchy; clean layout; strong focal subject; "
        "intentional empty space for a text overlay; polished campaign-ready design"
    ),
    "cinematic_key_visual": (
        "Cinematic key visual of {request}; dramatic but controlled lighting; realistic atmosphere; camera depth; "
        "strong composition; film-like color grading; smooth background detail; high-end production look"
    ),
    "avatar_character": (
        "Professional character portrait of {request}; recognizable face and silhouette; natural anatomy; "
        "intentional pose; clean background separation; flattering controlled light; consistent wardrobe details"
    ),
    "tech_ai_visual": (
        "Premium technology and AI visual for {request}; modern automation theme; precise geometric details; "
        "clean interfaces without readable random text; sophisticated light; credible professional atmosphere"
    ),
    "lifestyle_scene": (
        "Natural lifestyle scene featuring {request}; authentic environment; believable human activity; "
        "clear subject hierarchy; candid editorial framing; realistic daylight and materials"
    ),
    "food_restaurant": (
        "Commercial food photography of {request}; appetizing presentation; fresh realistic texture; "
        "clean plating; controlled highlights; suitable restaurant context; menu and social advertising quality"
    ),
    "real_estate": (
        "Premium real-estate and interior photography of {request}; accurate architectural lines; "
        "spacious clean composition; realistic materials; balanced natural and interior light; inviting atmosphere"
    ),
    "fashion_model": (
        "Fashion editorial image of {request}; confident model pose; accurate garment construction and texture; "
        "clean styling; controlled studio or location lighting; polished campaign composition"
    ),
    "custom": (
        "Professional image of {request}; clear primary subject; suitable context; intentional composition; "
        "coherent visual style; clean background separation"
    ),
}

PURPOSE_NEGATIVES = {
    "product_photo": "distorted product, duplicate objects, wrong packaging, broken logo, messy background",
    "ad_creative": "weak focal point, cluttered layout, random text, misleading claims",
    "logo_branding": "misspelled text, random letters, distorted logo, overly complex details",
    "social_banner": "random text, crowded layout, missing safe area, weak visual hierarchy",
    "cinematic_key_visual": "flat lighting, muddy colors, artificial depth, noisy background",
    "avatar_character": "distorted face, asymmetrical eyes, extra fingers, deformed hands, unnatural anatomy",
    "tech_ai_visual": "fake readable UI text, random symbols, cluttered interface, cheap sci-fi look",
    "lifestyle_scene": "stiff pose, unnatural hands, artificial skin, implausible environment",
    "food_restaurant": "unappetizing texture, duplicate food, dirty plate, plastic-looking ingredients",
    "real_estate": "warped walls, bent architecture, impossible windows, distorted furniture",
    "fashion_model": "distorted anatomy, extra fingers, broken garment, inconsistent fabric",
    "custom": "distorted subject, messy background, duplicate objects",
}

RATIO_MODIFIERS = {
    "9:16": "vertical composition, centered subject, suitable for TikTok, Reels and Shorts, safe area for captions",
    "16:9": "wide composition, suitable for YouTube, banners and video thumbnails, balanced horizontal depth",
    "1:1": "square composition, balanced layout, suitable for Instagram and Facebook posts",
    "4:5": "vertical feed composition, suitable for Facebook and Instagram ads, clear mobile focal point",
    "3:4": "portrait or product composition, clean framing, balanced vertical negative space",
    "3:2": "landscape product composition, clean framing, natural horizontal balance",
    "4:3": "classic landscape composition, clean presentation framing, balanced safe margins",
}

TIER_QUALITY_MODIFIERS = {
    "low": "concise art direction, clean basic quality, clear subject, simple controlled lighting",
    "standard": "professional high quality, clean composition, realistic detail, polished commercial lighting",
    "standard_warranty": "professional high quality, clean composition, realistic detail, polished commercial lighting",
    "high": "premium cinematic and commercial grade, high detail, controlled lighting, refined materials and color",
    "high_warranty": "premium cinematic and commercial grade, high detail, controlled lighting, refined materials and color",
}

GENERIC_NEGATIVE = (
    "low quality, blurry, pixelated, distorted subject, duplicate objects, bad anatomy, distorted hands, "
    "overexposed, underexposed, watermark, random text, misspelled text, messy background"
)

TEXT_LOGO_TERMS = (
    "chữ", "text", "logo", "tên thương hiệu", "slogan", "banner có chữ", "toan aas",
    "số điện thoại", "website", "địa chỉ", "phone number", "brand name", "headline",
)

VAGUE_REQUESTS = {
    "tạo ảnh đẹp", "làm ảnh đẹp", "làm ảnh bán hàng", "tạo ảnh bán hàng", "ảnh ai", "logo", "sản phẩm",
    "beautiful image", "sales image", "ai image", "product",
}


def _clean(value: str, limit: int = 1200) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:limit]


def detect_image_purpose(user_request: str, requested_purpose: str = "") -> str:
    purpose = _clean(requested_purpose, 80).lower().replace("-", "_").replace(" ", "_")
    if purpose in PURPOSE_TEMPLATES:
        return purpose
    text = _clean(user_request).lower()
    rules = (
        ("logo_branding", ("logo", "branding", "nhận diện", "thương hiệu")),
        ("social_banner", ("banner", "social post", "poster", "cover", "thumbnail")),
        ("food_restaurant", ("đồ ăn", "món ăn", "nhà hàng", "quán ăn", "food", "restaurant", "coffee", "cà phê")),
        ("real_estate", ("bất động sản", "nội thất", "căn hộ", "biệt thự", "real estate", "interior", "architecture")),
        ("fashion_model", ("thời trang", "người mẫu", "fashion", "lookbook", "outfit")),
        ("avatar_character", ("avatar", "chân dung", "nhân vật", "portrait", "character")),
        ("cinematic_key_visual", ("cinematic", "key visual", "điện ảnh", "product reveal")),
        ("tech_ai_visual", ("công nghệ", "automation", "trí tuệ nhân tạo", " ai ", "technology", "app")),
        ("ad_creative", ("quảng cáo", "bán hàng", "campaign", "creative ad", "affiliate")),
        ("lifestyle_scene", ("lifestyle", "đời thường", "sinh hoạt", "creator")),
        ("product_photo", ("sản phẩm", "product", "chai", "hộp", "mỹ phẩm", "nước hoa", "skincare")),
    )
    padded = f" {text} "
    for code, keywords in rules:
        if any(keyword in padded for keyword in keywords):
            return code
    return "custom"


def image_request_has_text_or_logo(user_request: str) -> bool:
    text = _clean(user_request).lower()
    return any(term in text for term in TEXT_LOGO_TERMS)


def image_request_is_vague(user_request: str) -> bool:
    text = _clean(user_request).lower().strip(" .,!?:;")
    if text in VAGUE_REQUESTS:
        return True
    meaningful = [part for part in re.split(r"\W+", text, flags=re.UNICODE) if len(part) > 1]
    return len(meaningful) < 3


def suggested_ratio_for_purpose(purpose: str) -> str:
    return {
        "product_photo": "1:1",
        "ad_creative": "4:5",
        "logo_branding": "1:1",
        "social_banner": "16:9",
        "cinematic_key_visual": "16:9",
        "avatar_character": "3:4",
        "tech_ai_visual": "16:9",
        "lifestyle_scene": "4:5",
        "food_restaurant": "4:5",
        "real_estate": "16:9",
        "fashion_model": "3:4",
    }.get(purpose, "1:1")


def build_image_prompt(
    user_request: str,
    image_purpose: str = "",
    style: str = "",
    ratio: str = "",
    tier: str = "",
) -> dict:
    request = _clean(user_request) or "a clearly defined subject"
    purpose = detect_image_purpose(request, image_purpose)
    ratio_value = _clean(ratio, 20) or suggested_ratio_for_purpose(purpose)
    if ratio_value not in RATIO_MODIFIERS:
        ratio_value = suggested_ratio_for_purpose(purpose)
    tier_value = _clean(tier, 40).lower().replace("-", "_").replace(" ", "_") or "standard"
    quality = TIER_QUALITY_MODIFIERS.get(tier_value, TIER_QUALITY_MODIFIERS["standard"])
    style_value = _clean(style, 240) or "modern, professional and visually coherent"
    has_text_logo = image_request_has_text_or_logo(request)
    keep_rules = "preserve the requested subject, product identity, proportions, colors and recognizable details"
    text_rules = ""
    caution = ""
    if has_text_logo:
        text_rules = "; leave clean space for text overlay; avoid random text; do not invent letters or misspell brand text"
        caution = (
            "Lưu ý: AI tạo ảnh có thể sai chữ hoặc logo. TOAN AAS sẽ ưu tiên bố cục và ý tưởng; "
            "phần chữ quan trọng nên được kiểm tra hoặc chỉnh lại ở bước hậu kỳ."
        )
    template = PURPOSE_TEMPLATES.get(purpose, PURPOSE_TEMPLATES["custom"])
    prompt = (
        f"{template.format(request=request)}; style: {style_value}; {RATIO_MODIFIERS[ratio_value]}; "
        f"aspect ratio {ratio_value}; {quality}; {keep_rules}{text_rules}; no watermark; no unnecessary text."
    )
    negative_parts = [GENERIC_NEGATIVE, PURPOSE_NEGATIVES.get(purpose, PURPOSE_NEGATIVES["custom"])]
    if has_text_logo:
        negative_parts.append("random letters, misspelled brand name, broken logo, unwanted text")
    negative = ", ".join(dict.fromkeys(part.strip() for part in negative_parts if part.strip()))
    return {
        "purpose": purpose,
        "purpose_label": PURPOSE_LABELS[purpose],
        "prompt": _clean(prompt, 1800),
        "negative_prompt": _clean(negative, 1000),
        "suggested_ratio": ratio_value,
        "tier": tier_value,
        "quality_modifier": quality,
        "text_logo_caution": caution,
        "needs_clarification": image_request_is_vague(request),
        "clarification_options": ["Ảnh sản phẩm rõ chủ thể", "Ảnh quảng cáo bán hàng", "Banner / social post"],
    }


def enhance_image_prompt_for_generation(prompt: str, ratio: str = "", tier: str = "") -> str:
    request = _clean(prompt)
    purpose = detect_image_purpose(request)
    ratio_value = _clean(ratio, 20) if _clean(ratio, 20) in RATIO_MODIFIERS else suggested_ratio_for_purpose(purpose)
    tier_value = _clean(tier, 40).lower().replace("-", "_").replace(" ", "_") or "low"
    quality = TIER_QUALITY_MODIFIERS.get(tier_value, TIER_QUALITY_MODIFIERS["low"])
    text_rules = ""
    if image_request_has_text_or_logo(request):
        text_rules = " Leave clean space for text overlay; avoid random text; no misspelled text; preserve logo concept."
    negative = f"{GENERIC_NEGATIVE}, {PURPOSE_NEGATIVES.get(purpose, PURPOSE_NEGATIVES['custom'])}"
    return _clean(
        f"{request}. {RATIO_MODIFIERS[ratio_value]}. Aspect ratio {ratio_value}. {quality}. "
        f"Preserve the requested subject, product identity, colors and recognizable details.{text_rules} "
        f"Negative prompt: {negative}.",
        1800,
    )
