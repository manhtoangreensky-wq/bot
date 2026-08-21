"""
Brand Profile Engine for TOAN AAS Marketing Automation.
Manages brand voice, multi-brand ownership, and platform-specific branding policies.
"""
from typing import Dict, Any, List, Optional

PLATFORM_BRAND_POLICIES = {
    "telegram": {
        "text_branding_allowed": True,
        "logo_overlay_allowed": True,
        "watermark_allowed": True,
        "link_in_caption_allowed": True,
        "disclosure_required": False,
        "native_partnership_field_available": False,
    },
    "facebook": {
        "text_branding_allowed": True,
        "logo_overlay_allowed": True,
        "watermark_allowed": True,
        "link_in_caption_allowed": True,
        "disclosure_required": True,
        "native_partnership_field_available": True,
    },
    "instagram": {
        "text_branding_allowed": True,
        "logo_overlay_allowed": True,
        "watermark_allowed": True,
        "link_in_caption_allowed": False,
        "disclosure_required": True,
        "native_partnership_field_available": True,
    },
    "youtube": {
        "text_branding_allowed": True,
        "logo_overlay_allowed": True,
        "watermark_allowed": True,
        "link_in_caption_allowed": True,
        "disclosure_required": True,
        "native_partnership_field_available": True,
    },
    "tiktok": {
        "text_branding_allowed": True,
        "logo_overlay_allowed": False,
        "watermark_allowed": False,
        "link_in_caption_allowed": False,
        "disclosure_required": True,
        "native_partnership_field_available": True,
    },
}

DEFAULT_BRAND_PROFILE = {
    "brand_id": "default",
    "brand_name": "TOAN AAS",
    "brand_voice": "Chuyên nghiệp, hiện đại, uy tín, hữu ích và truyền cảm hứng",
    "short_description": "Hệ sinh thái công nghệ & tự động hóa AI toàn diện",
    "target_audience": "Chủ shop online, nhà sáng tạo nội dung, doanh nghiệp vừa và nhỏ (SMEs)",
    "primary_cta": "Trải nghiệm ngay trên Telegram @toanaasbot",
    "approved_domains": ["tg.toanaas.vn", "toanaas.vn", "t.me/toanaasbot"],
    "brand_colors": ["#1E88E5", "#0D47A1", "#00E676"],
    "preferred_hashtags": ["#TOANAAS", "#AIAutomation", "#MarketingAI", "#ContentCreator"],
    "required_disclosures": "Bài viết có thể chứa liên kết tiếp thị đối tác chính thức.",
    "allowed_claims": [
        "Tiết kiệm đến 80% thời gian sáng tạo nội dung",
        "Tự động hóa kịch bản, hình ảnh, video đa kênh",
        "Hỗ trợ 17 ngôn ngữ quốc tế",
    ],
    "blocked_claims": [
        "Cam kết kiếm tiền 100% không cần làm gì",
        "Đảm bảo viral triệu view ngay lập tức",
        "Thu nhập thụ động cam kết không rủi ro",
    ],
    "content_tone": "Truyền cảm hứng & Hướng dẫn thực chiến",
    "language": "vi",
}

def get_platform_brand_policy(platform: str) -> Dict[str, bool]:
    """Return platform-specific branding constraints."""
    return PLATFORM_BRAND_POLICIES.get(platform.lower(), {
        "text_branding_allowed": True,
        "logo_overlay_allowed": True,
        "watermark_allowed": True,
        "link_in_caption_allowed": True,
        "disclosure_required": True,
        "native_partnership_field_available": False,
    })

def validate_brand_compliance_for_platform(brand: Dict[str, Any], platform: str, media_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Verify that the media and text payload comply with platform rules."""
    policy = get_platform_brand_policy(platform)
    violations = []
    
    if platform.lower() == "tiktok":
        if media_payload.get("has_burnt_watermark") and not policy["watermark_allowed"]:
            violations.append("TikTok policy prohibits burnt-in external watermarks on Direct Post.")
        if media_payload.get("has_logo_overlay") and not policy["logo_overlay_allowed"]:
            violations.append("TikTok Direct Post policy restricts burnt-in promotional logo overlays.")

    return {
        "compliant": len(violations) == 0,
        "violations": violations,
        "applied_policy": policy,
    }
