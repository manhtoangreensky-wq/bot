"""
Content Strategy Engine for TOAN AAS Marketing Automation.
Generates multi-day content plans, single post drafts from Content Inputs,
consumes Brand Profile & Affiliate Matcher, and persists into durable database.
"""
from typing import Dict, Any, List, Optional
import datetime
from services.autopost_db import save_content_plan_with_items, save_content_input

CONTENT_GOALS = [
    ("AWARENESS", "Nhận diện thương hiệu & Thu hút traffic mới"),
    ("ENGAGEMENT", "Tăng tương tác, bình luận & chia sẻ"),
    ("LEADS", "Thu thập khách hàng tiềm năng & Đăng ký dùng thử"),
    ("SALES", "Chuyển đổi bán hàng & Đơn hàng trực tiếp"),
    ("AFFILIATE_CONVERSION", "Tiếp thị liên kết & Hoa hồng đối tác"),
    ("COMMUNITY", "Xây dựng cộng đồng & Giữ chân khách hàng trung thành"),
]

def generate_single_post_draft(
    owner_user_id: int,
    topic_or_text: str,
    brand: Dict[str, Any],
    platform: str = "telegram",
    affiliate: Optional[Dict[str, Any]] = None,
    content_input_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Generate a high-converting post draft from raw user input, brand, and affiliate link."""
    brand_name = brand.get("brand_name") or "TOAN AAS"
    voice = brand.get("brand_voice") or "Chuyên nghiệp & Hiện đại"
    cta = brand.get("primary_cta") or f"Trải nghiệm ngay cùng {brand_name}"
    hashtags = brand.get("default_hashtags") or "#TOANAAS #AIAutomation"
    if isinstance(hashtags, list):
        hashtags = " ".join(hashtags)
        
    hook = f"🚀 Khám phá giải pháp mới cùng {brand_name}: {topic_or_text[:60]}"
    
    caption_lines = [
        f"🎯 <b>{hook}</b>",
        "",
        f"💡 <i>{topic_or_text}</i>",
        "",
        f"✨ <b>Lợi ích nổi bật:</b>",
        f"• Tối ưu hiệu quả và tiết kiệm thời gian đáng kể.",
        f"• Đơn giản, thực chiến, áp dụng ngay hôm nay.",
        "",
        f"👉 <b>Hành động ngay:</b> {cta}",
    ]
    
    if affiliate and affiliate.get("url"):
        aff_name = affiliate.get("product_name") or "Sản phẩm đề xuất"
        aff_url = affiliate.get("url")
        caption_lines.extend([
            "",
            f"🛒 <b>Sản phẩm liên kết:</b> <a href=\"{aff_url}\">{aff_name}</a>",
            "<i>(Liên kết tiếp thị đối tác chính thức)</i>"
        ])
        
    caption_lines.extend([
        "",
        f"{hashtags}"
    ])
    
    full_caption = "\n".join(caption_lines)
    
    return {
        "owner_user_id": owner_user_id,
        "content_input_id": content_input_id,
        "platform": platform,
        "topic": topic_or_text,
        "hook": hook,
        "caption": full_caption,
        "cta": cta,
        "hashtags": hashtags,
        "affiliate_id": affiliate.get("id") if affiliate else None,
        "status": "DRAFT",
    }

def create_content_plan(
    owner_id: str,
    brand: Dict[str, Any],
    niche: str,
    goal: str = "AWARENESS",
    duration_days: int = 7,
    platforms: Optional[List[str]] = None,
    include_affiliate: bool = True,
    language: str = "vi",
    persist_db: bool = True,
) -> Dict[str, Any]:
    """Generate a structured multi-day content calendar plan and optionally persist to SQLite."""
    platforms = platforms or ["telegram", "facebook", "instagram", "youtube", "tiktok"]
    duration_days = min(30, max(1, duration_days))
    uid_int = int(owner_id) if str(owner_id).isdigit() else 0
    brand_name = brand.get("brand_name") or "TOAN AAS"
    
    pillars = [
        {"name": "Giáo dục & Giá trị", "ratio": 0.4, "description": "Hướng dẫn, mẹo hay, giải quyết vấn đề khách hàng"},
        {"name": "Chứng thực & Trải nghiệm", "ratio": 0.3, "description": "Case study, kết quả thực tế, feedback khách hàng"},
        {"name": "Kêu gọi hành động & Ưu đãi", "ratio": 0.3, "description": "Giới thiệu giải pháp, link affiliate, ưu đãi đặc biệt"},
    ]
    
    items = []
    base_date = datetime.datetime.utcnow().date()
    
    for day in range(duration_days):
        cur_date = base_date + datetime.timedelta(days=day)
        pillar = pillars[day % len(pillars)]
        
        item = {
            "day_index": day + 1,
            "post_date": cur_date.strftime("%Y-%m-%d"),
            "time_slot": "11:30" if day % 2 == 0 else "20:00",
            "schedule_source": "HEURISTIC",
            "suggested_slots": ["11:30", "20:00"],
            "pillar": pillar["name"],
            "topic": f"Chiến lược {niche} ngày {day+1}: {pillar['name']}",
            "master_hook": f"Bí quyết tối ưu {niche} cùng {brand_name} ngày {day+1}!",
            "master_caption": (
                f"Bạn đang tìm kiếm giải pháp hiệu quả cho {niche}?\n\n"
                f"• Bước 1: Xác định đúng đối tượng và nhu cầu cốt lõi.\n"
                f"• Bước 2: Tự động hóa quy trình với {brand_name} để tiết kiệm 80% thời gian.\n"
                f"• Bước 3: Đo lường và tối ưu dựa trên dữ liệu thực tế.\n\n"
                f"Bình luận hoặc bấm link bên dưới để nhận tài liệu hướng dẫn chi tiết!"
            ),
            "cta": brand.get("primary_cta", f"Trải nghiệm ngay cùng {brand_name}"),
            "hashtags": brand.get("preferred_hashtags", [f"#{brand_name.replace(' ', '')}", "#AIAutomation", f"#{niche}"]),
            "platform": platforms[day % len(platforms)],
            "target_platforms": platforms,
            "affiliate_enabled": include_affiliate and (pillar["name"] == "Kêu gọi hành động & Ưu đãi"),
        }
        items.append(item)
        
    plan_dict = {
        "plan_id": f"PLAN-{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{owner_id[:6]}",
        "owner_id": owner_id,
        "brand_name": brand_name,
        "niche": niche,
        "goal": goal,
        "duration_days": duration_days,
        "total_posts": len(items),
        "pillars": pillars,
        "items": items,
        "created_at": datetime.datetime.utcnow().isoformat() + "Z",
    }
    
    if persist_db and uid_int > 0:
        db_plan_id = save_content_plan_with_items(uid_int, brand_name, goal, duration_days, items)
        plan_dict["db_plan_id"] = db_plan_id
        
    return plan_dict
