"""
Content Strategy Engine for TOAN AAS Marketing Automation.
Generates multi-day content plans, content pillars, platform adaptations, and realistic schedules.
"""
from typing import Dict, Any, List, Optional
import datetime

CONTENT_GOALS = [
    ("AWARENESS", "Nhận diện thương hiệu & Thu hút traffic mới"),
    ("ENGAGEMENT", "Tăng tương tác, bình luận & chia sẻ"),
    ("LEADS", "Thu thập khách hàng tiềm năng & Đăng ký dùng thử"),
    ("SALES", "Chuyển đổi bán hàng & Đơn hàng trực tiếp"),
    ("AFFILIATE_CONVERSION", "Tiếp thị liên kết & Hoa hồng đối tác"),
    ("COMMUNITY", "Xây dựng cộng đồng & Giữ chân khách hàng trung thành"),
]

def create_content_plan(
    owner_id: str,
    brand: Dict[str, Any],
    niche: str,
    goal: str = "AWARENESS",
    duration_days: int = 7,
    platforms: Optional[List[str]] = None,
    include_affiliate: bool = True,
    language: str = "vi",
) -> Dict[str, Any]:
    """Generate a structured multi-day content calendar plan."""
    platforms = platforms or ["telegram", "facebook", "instagram", "youtube", "tiktok"]
    duration_days = min(30, max(1, duration_days))
    
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
            "schedule_source": "HEURISTIC",
            "suggested_slots": ["11:30", "20:00"],
            "pillar": pillar["name"],
            "topic": f"Chiến lược {niche} ngày {day+1}: {pillar['name']}",
            "master_hook": f"Bí quyết tối ưu {niche} cho kết quả đột phá ngày {day+1}!",
            "master_caption": (
                f"Bạn đang tìm kiếm giải pháp hiệu quả cho {niche}?\n\n"
                f"• Bước 1: Xác định đúng đối tượng và nhu cầu cốt lõi.\n"
                f"• Bước 2: Tự động hóa quy trình với TOAN AAS để tiết kiệm 80% thời gian.\n"
                f"• Bước 3: Đo lường và tối ưu dựa trên dữ liệu thực tế.\n\n"
                f"Bình luận hoặc bấm link bên dưới để nhận tài liệu hướng dẫn chi tiết!"
            ),
            "cta": brand.get("primary_cta", "Trải nghiệm ngay trên Telegram @toanaasbot"),
            "hashtags": brand.get("preferred_hashtags", ["#TOANAAS", "#AIAutomation", f"#{niche}"]),
            "target_platforms": platforms,
            "affiliate_enabled": include_affiliate and (pillar["name"] == "Kêu gọi hành động & Ưu đãi"),
        }
        items.append(item)
        
    return {
        "plan_id": f"PLAN-{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{owner_id[:6]}",
        "owner_id": owner_id,
        "brand_name": brand.get("brand_name", "TOAN AAS"),
        "niche": niche,
        "goal": goal,
        "duration_days": duration_days,
        "total_posts": len(items),
        "pillars": pillars,
        "items": items,
        "created_at": datetime.datetime.utcnow().isoformat() + "Z",
    }
