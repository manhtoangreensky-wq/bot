from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any


FREE_TOOL_TYPES = {
    "free_chat",
    "meta_ai_prompt",
    "content_idea",
    "caption_hashtag",
    "hook_script",
    "image_prompt",
    "video_prompt",
    "document_pdf",
    "notes_storage",
    "prompt_library",
    "byok_api",
    "upload_for_postprocess",
}

ALLOWED_FREE_PROVIDER_TASKS = {
    "free_chat",
    "content_idea",
    "caption_hashtag",
    "hook_script",
    "image_prompt",
    "video_prompt",
    "meta_ai_prompt",
    "summarize_light",
    "rewrite_light",
    "support_classification_safe",
}

BLOCKED_FREE_TASK_MARKERS = {
    "payment": (
        "chuyển khoản",
        "bill thanh toán",
        "chưa thấy xu",
        "hoàn tiền",
        "refund",
        "payment",
        "payos",
        "nạp tiền",
        "nap tien",
        "txid",
    ),
    "secret": (
        "api key",
        "apikey",
        "access token",
        "secret key",
        "bearer ",
        "mật khẩu",
        "password",
        "otp",
    ),
    "official_advice": (
        "khai thuế",
        "nộp thuế",
        "tư vấn pháp lý",
        "lời khuyên đầu tư",
        "tax filing",
        "legal advice",
        "investment advice",
    ),
    "admin_security": (
        "admin debug",
        "webhook signature",
        "security token",
        "database password",
        "railway secret",
    ),
}

DEFAULT_PROMPT_LIBRARY_PATH = (
    Path(__file__).resolve().parent / "data" / "prompt_library" / "free_hub_prompts.json"
)


def _clean_text(value: Any, limit: int = 1200) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:limit]


def load_prompt_library(path: str | Path | None = None) -> dict[str, Any]:
    source = Path(path) if path else DEFAULT_PROMPT_LIBRARY_PATH
    with source.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("prompt library root must be an object")
    payload["_source"] = str(source)
    payload["_expanded_items"] = expand_prompt_library(payload)
    return payload


def expand_prompt_library(payload: dict[str, Any]) -> list[dict[str, Any]]:
    industries = payload.get("industries") or []
    categories = payload.get("categories") or []
    expanded: list[dict[str, Any]] = []
    for category in categories:
        category_id = _clean_text(category.get("id"), 80)
        category_title = _clean_text(category.get("title"), 120)
        templates = category.get("templates") or []
        for industry in industries:
            industry_id = _clean_text(industry.get("id"), 80)
            variables = {
                "industry": _clean_text(industry.get("title"), 100),
                "product": _clean_text(industry.get("product"), 180),
                "audience": _clean_text(industry.get("audience"), 180),
                "benefit": _clean_text(industry.get("benefit"), 180),
            }
            for index, template in enumerate(templates, 1):
                body = str(template.get("prompt_template") or "").format(**variables)
                expanded.append(
                    {
                        "id": f"{category_id}_{industry_id}_{index}",
                        "category_id": category_id,
                        "category_title": category_title,
                        "industry_id": industry_id,
                        "industry": variables["industry"],
                        "title": _clean_text(
                            str(template.get("title") or category_title).format(**variables),
                            160,
                        ),
                        "prompt": _clean_text(body, 2200),
                        "goal": list(template.get("goal") or []),
                        "platform": list(template.get("platform") or []),
                    }
                )
    return expanded


def prompt_library_items(
    library: dict[str, Any],
    category_id: str = "",
    industry_id: str = "",
) -> list[dict[str, Any]]:
    items = list(library.get("_expanded_items") or expand_prompt_library(library))
    if category_id:
        items = [item for item in items if item.get("category_id") == category_id]
    if industry_id:
        items = [item for item in items if item.get("industry_id") == industry_id]
    return items


def prompt_library_counts(library: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in prompt_library_items(library):
        category_id = str(item.get("category_id") or "other")
        counts[category_id] = counts.get(category_id, 0) + 1
    return counts


def prompt_library_suggestions(
    library: dict[str, Any],
    category_id: str,
    count: int = 3,
    exclude_ids: list[str] | None = None,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    excluded = set(exclude_ids or [])
    candidates = [
        item
        for item in prompt_library_items(library, category_id=category_id)
        if item.get("id") not in excluded
    ]
    if len(candidates) < count:
        candidates = prompt_library_items(library, category_id=category_id)
    rng = random.Random(seed)
    rng.shuffle(candidates)
    return candidates[: max(1, int(count or 3))]


def prompt_library_item(library: dict[str, Any], prompt_id: str) -> dict[str, Any]:
    for item in prompt_library_items(library):
        if item.get("id") == prompt_id:
            return dict(item)
    return {}


def sensitive_free_task_reason(user_input: str, task_type: str = "") -> str:
    task = _clean_text(task_type, 80).lower()
    if task and task not in ALLOWED_FREE_PROVIDER_TASKS:
        return "task_not_allowed"
    normalized = _clean_text(user_input, 4000).lower()
    for reason, markers in BLOCKED_FREE_TASK_MARKERS.items():
        if any(marker in normalized for marker in markers):
            return reason
    return ""


def infer_product_context(user_input: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    text = _clean_text(user_input, 900)
    lower = text.lower()
    supplied = dict(context or {})
    mappings = [
        (("nước hoa", "nuoc hoa", "fragrance"), "beauty_fragrance", "Làm đẹp / nước hoa", "nam và nữ 18-35 quan tâm phong cách cá nhân", "sang trọng / cinematic"),
        (("spa", "thẩm mỹ", "tham my"), "spa_beauty", "Spa / thẩm mỹ", "khách địa phương muốn cải thiện ngoại hình", "chân thật / before-after"),
        (("cafe", "cà phê", "quan an", "đồ ăn"), "food_cafe", "Đồ ăn / quán cafe", "người trẻ thích trải nghiệm địa điểm mới", "ấm áp / appetizing"),
        (("bất động sản", "nội thất", "can ho"), "real_estate", "Bất động sản / nội thất", "người đang tìm không gian sống hoặc đầu tư", "premium / architectural"),
        (("khóa học", "khoa hoc", "giáo dục"), "education", "Giáo dục / kỹ năng", "người mới muốn học nhanh và áp dụng thực tế", "rõ ràng / truyền cảm hứng"),
        (("phần mềm", "saas", "app ai", "công cụ ai"), "software_saas", "Phần mềm / SaaS", "creator, shop nhỏ và người làm nội dung", "công nghệ / hiện đại"),
        (("thời trang", "quần áo", "túi", "giày"), "fashion", "Thời trang", "người mua online quan tâm phong cách và độ phù hợp", "editorial / lifestyle"),
        (("affiliate", "tiếp thị liên kết"), "affiliate", "Affiliate", "người mới tìm công cụ và cách làm thực tế", "UGC / review chân thật"),
        (("fitness", "gym", "thể thao"), "fitness", "Fitness", "người muốn cải thiện sức khỏe và vóc dáng", "năng lượng / động lực"),
        (("mẹ và bé", "thú cưng", "pet"), "family_pet", "Gia đình / thú cưng", "gia đình trẻ và người nuôi thú cưng", "ấm áp / đáng yêu"),
    ]
    industry_id = "shop_online"
    industry = "Shop online / dịch vụ"
    audience = "khách hàng 18-35 trên TikTok, Facebook và Instagram"
    style = "chân thật / hiện đại"
    for markers, mapped_id, mapped_name, mapped_audience, mapped_style in mappings:
        if any(marker in lower for marker in markers):
            industry_id = mapped_id
            industry = mapped_name
            audience = mapped_audience
            style = mapped_style
            break
    product = supplied.get("product_name") or text or "sản phẩm/dịch vụ của bạn"
    goal = supplied.get("goal") or "bán hàng"
    platform = supplied.get("platform") or "TikTok/Reels"
    ratio = supplied.get("aspect_ratio") or "9:16"
    duration = int(supplied.get("duration_seconds") or 12)
    tone = supplied.get("tone") or "thuyết phục nhưng tự nhiên"
    return {
        "industry_id": industry_id,
        "industry": industry,
        "product_name": _clean_text(product, 220),
        "product_description": _clean_text(supplied.get("product_description") or text, 500),
        "target_audience": _clean_text(supplied.get("target_audience") or audience, 240),
        "goal": _clean_text(goal, 100),
        "platform": _clean_text(platform, 100),
        "aspect_ratio": _clean_text(ratio, 30),
        "duration_seconds": max(5, min(60, duration)),
        "style": _clean_text(supplied.get("style") or style, 120),
        "tone": _clean_text(tone, 120),
        "call_to_action": _clean_text(
            supplied.get("call_to_action") or "Khám phá thêm và chọn phiên bản phù hợp với bạn",
            180,
        ),
        "available_assets": list(supplied.get("available_assets") or []),
        "user_skill_level": _clean_text(supplied.get("user_skill_level") or "beginner", 40),
        "language": _clean_text(supplied.get("language") or "vi", 10),
    }


def generate_contextual_prompt(
    user_input: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = infer_product_context(user_input, context)
    product = data["product_name"]
    audience = data["target_audience"]
    style = data["style"]
    ratio = data["aspect_ratio"]
    duration = data["duration_seconds"]
    platform = data["platform"]
    goal = data["goal"]
    cta = data["call_to_action"]
    prompt = (
        f"Tạo video quảng cáo {ratio}, dài khoảng {duration} giây cho {product}. "
        f"Mục tiêu: {goal}; nền tảng: {platform}; khán giả: {audience}. "
        f"Cảnh 1 mở bằng close-up chủ thể trong bối cảnh đời thực sạch, có hành động rõ ràng ngay 2 giây đầu. "
        f"Cảnh 2 dùng medium shot để cho thấy lợi ích qua thao tác hoặc tình huống sử dụng tự nhiên. "
        f"Cảnh 3 chuyển sang hero shot sản phẩm/kết quả, camera slow push-in rồi orbit nhẹ 10-15 độ. "
        f"Ánh sáng mềm có key light định hướng, viền sáng tinh tế, màu sắc {style}; vật liệu và chuyển động phải chân thật. "
        f"Không chèn chữ sai chính tả, không logo giả, không watermark, không thêm ngón tay/vật thể méo, "
        f"không chuyển động giật hoặc thay đổi hình dạng chủ thể. Kết thúc bằng khung hình sạch để ghép CTA."
    )
    variants = [
        prompt.replace("close-up chủ thể", "POV tình huống đời thường").replace("slow push-in", "handheld nhẹ ổn định"),
        prompt.replace("Cảnh 1 mở bằng", "Mở theo cấu trúc before/after bằng").replace("orbit nhẹ 10-15 độ", "match cut mượt"),
        prompt.replace("hero shot", "UGC reaction shot rồi product reveal").replace("Ánh sáng mềm", "Ánh sáng cinematic tương phản vừa"),
    ]
    caption = (
        f"{product}: một cách trực quan để biến nhu cầu hằng ngày thành trải nghiệm gọn hơn. "
        f"Phù hợp với {audience}. {cta}."
    )
    hashtag_tokens = [
        "#TOANAAS",
        "#ContentAI",
        "#VideoMarketing",
        "#" + re.sub(r"[^A-Za-z0-9À-ỹ]", "", data["industry"].title().replace(" ", ""))[:30],
        "#TikTokVietnam" if "tiktok" in platform.lower() else "#SocialMedia",
    ]
    return {
        "title": f"Prompt {data['industry']} - {product[:70]}",
        "prompt": prompt,
        "variants": variants,
        "caption": caption,
        "hashtags": hashtag_tokens,
        "cta": cta,
        "shot_list": [
            "0-2s: close-up/POV hook, hành động chính xuất hiện ngay",
            "2-7s: medium shot minh họa cách dùng hoặc lợi ích",
            f"7-{duration}s: hero shot/kết quả, camera push-in và khung CTA sạch",
        ],
        "negative_prompt": (
            "low quality, blurry subject, deformed hands, duplicate objects, unstable identity, "
            "warped product, flicker, jitter, unreadable text, fake logo, watermark, abrupt camera motion"
        ),
        "music_sfx": "Nhạc hiện đại nhịp vừa; SFX whoosh nhẹ ở chuyển cảnh và soft impact ở product reveal.",
        "copy_instruction": "Copy prompt này sang Meta AI/Facebook/Instagram. TOAN AAS chưa gọi API Meta và chưa tạo video.",
        "context": data,
    }


def content_idea_pack(user_input: str) -> dict[str, Any]:
    data = infer_product_context(user_input)
    product = data["product_name"]
    return {
        "title": f"Ý tưởng content cho {product}",
        "ideas": [
            f"Before/after: vấn đề trước khi biết {product} và kết quả sau khi áp dụng.",
            f"POV đời thường: một tình huống quen thuộc khiến {product} trở thành giải pháp tự nhiên.",
            f"3 mẹo nhanh: chia sẻ giá trị trước, đưa {product} vào mẹo cuối như công cụ hỗ trợ.",
        ],
        "caption": f"Bạn đang gặp tình huống nào trong 3 trường hợp này? {data['call_to_action']}.",
        "hashtags": ["#TOANAAS", "#ContentIdeas", "#Marketing", "#Creator"],
    }


def caption_hashtag_pack(user_input: str) -> dict[str, Any]:
    data = infer_product_context(user_input)
    product = data["product_name"]
    return {
        "caption": (
            f"Không cần làm mọi thứ phức tạp. {product} tập trung vào điều quan trọng: "
            f"giúp {data['target_audience']} có trải nghiệm rõ ràng, dễ bắt đầu và dễ duy trì. "
            f"{data['call_to_action']}."
        ),
        "hashtags": ["#TOANAAS", "#NoiDungBanHang", "#SocialContent", "#TikTokMarketing", "#ReelsVietnam"],
        "cta": data["call_to_action"],
    }


def hook_script_pack(user_input: str) -> dict[str, Any]:
    data = infer_product_context(user_input)
    product = data["product_name"]
    return {
        "hooks": [
            f"Nếu bạn đang dùng {product} theo cách này, có thể bạn đang bỏ lỡ phần hữu ích nhất.",
            f"Đây là lý do {data['target_audience']} đang chú ý đến {product}.",
            f"Chỉ trong 15 giây, đây là cách {product} giải quyết một vấn đề quen thuộc.",
        ],
        "script_15s": (
            f"0-3s: Nêu vấn đề quen thuộc. 3-9s: Cho thấy {product} trong hành động thực tế. "
            f"9-13s: Chốt lợi ích chính. 13-15s: {data['call_to_action']}."
        ),
        "script_30s": (
            f"0-4s hook; 4-10s bối cảnh/vấn đề; 10-20s demo {product}; "
            f"20-26s kết quả hoặc proof; 26-30s CTA nhẹ."
        ),
        "cta": data["call_to_action"],
    }


def free_provider_candidates(
    order: list[str],
    enabled: dict[str, bool],
    byok_provider: str = "",
) -> list[str]:
    candidates: list[str] = []
    byok = _clean_text(byok_provider, 40).lower()
    if byok and enabled.get(f"byok_{byok}", False):
        candidates.append(f"byok:{byok}")
    for provider in order:
        name = _clean_text(provider, 40).lower()
        if name and enabled.get(name, False) and name not in candidates:
            candidates.append(name)
    return candidates


def quota_limit_for_user(
    is_admin: bool,
    is_premium: bool,
    is_registered: bool,
    limits: dict[str, int],
) -> int:
    if is_admin:
        return max(0, int(limits.get("admin", 1000)))
    if is_premium:
        return max(0, int(limits.get("premium", 300)))
    if is_registered:
        return max(0, int(limits.get("registered", 100)))
    return max(0, int(limits.get("free", 30)))


def should_show_soft_promo(
    success_count: int,
    after_requests: int = 5,
    last_shown_ts: float = 0.0,
    now_ts: float = 0.0,
    cooldown_hours: int = 24,
) -> bool:
    count = max(0, int(success_count or 0))
    threshold = max(1, int(after_requests or 5))
    if count == 0 or count % threshold:
        return False
    if not last_shown_ts:
        return True
    return float(now_ts or 0.0) - float(last_shown_ts) >= max(1, int(cooldown_hours or 24)) * 3600
