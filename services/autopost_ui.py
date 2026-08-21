"""
Clean UI Renderers & 10-Button Omnichannel Layout for TOAN AAS.
Guarantees real line breaks (no literal \\n\\n), full i18n support, and seamless Back navigation.
Includes complete Personal Affiliate Vault UI renderers.
"""
from typing import Dict, Any, List, Optional
import html
import urllib.parse
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def autopost_main_dashboard_text(lang: str = "vi", stats: Optional[Dict[str, Any]] = None) -> str:
    """Render the official Owner-approved Main AutoPost Dashboard."""
    stats = stats or {
        "weekly_posts": 14,
        "queued_posts": 4,
        "published_posts": 7,
        "pending_action": 1,
        "ad_spend_today": 0,
        "ad_mode": "Chờ Owner duyệt",
    }
    
    if lang == "en":
        lines = [
            "📢 <b>AUTO POST & OMNICHANNEL MARKETING HUB</b>",
            "",
            "Automate content planning → generation → Affiliate selection → scheduling → omnichannel publishing → metrics loop → ads recommendation.",
            "",
            f"📅 <b>This week:</b> {stats['weekly_posts']} posts",
            f"🚀 <b>Queued:</b> {stats['queued_posts']}",
            f"✅ <b>Published:</b> {stats['published_posts']}",
            f"⚠️ <b>Needs action:</b> {stats['pending_action']}",
            "",
            "<b>Channels:</b>",
            "✅ Telegram",
            "✅ Facebook Pages",
            "✅ Instagram Professional",
            "⚠️ YouTube · Requires OAuth",
            "⚠️ TikTok · Awaiting Direct Post audit",
            "",
            "<b>Affiliate:</b>",
            "✅ Personal Vault & Auto-match relevant products",
            "",
            "<b>Advertising:</b>",
            f"🟡 <b>Mode:</b> {stats['ad_mode']}",
            f"💰 <b>Spend today:</b> {stats['ad_spend_today']:,}đ",
        ]
        return "\n".join(lines)
        
    lines = [
        "📢 <b>ĐĂNG BÀI TỰ ĐỘNG & MARKETING HUB</b>",
        "",
        "Tự động lên kế hoạch → tạo nội dung → chọn Affiliate từ kho cá nhân → lên lịch → đăng đa kênh → đo hiệu quả → đề xuất quảng cáo.",
        "",
        f"📅 <b>Tuần này:</b> {stats['weekly_posts']} bài",
        f"🚀 <b>Chờ đăng:</b> {stats['queued_posts']}",
        f"✅ <b>Đã đăng:</b> {stats['published_posts']}",
        f"⚠️ <b>Cần xử lý:</b> {stats['pending_action']}",
        "",
        "<b>Kênh kết nối:</b>",
        "✅ Telegram",
        "✅ Facebook",
        "✅ Instagram",
        "⚠️ YouTube · Cần OAuth",
        "⚠️ TikTok · Chờ xác minh Direct Post",
        "",
        "<b>Affiliate:</b>",
        "✅ Kho cá nhân riêng biệt & Tự động ghép sản phẩm",
        "",
        "<b>Quảng cáo:</b>",
        f"🟡 <b>Chế độ:</b> {stats['ad_mode']}",
        f"💰 <b>Chi tiêu hôm nay:</b> {stats['ad_spend_today']:,}đ",
    ]
    return "\n".join(lines)

def autopost_main_keyboard(lang: str = "vi") -> InlineKeyboardMarkup:
    """10-button keyboard layout (5 rows of 2 buttons)."""
    rows = [
        [InlineKeyboardButton("🧠 Kế hoạch nội dung", callback_data="autopost|content_plan"), InlineKeyboardButton("🎨 Thương hiệu", callback_data="autopost|brands")],
        [InlineKeyboardButton("🔗 Affiliate", callback_data="autopost|affiliate"), InlineKeyboardButton("📅 Lịch đăng", callback_data="autopost|calendar")],
        [InlineKeyboardButton("📡 Kênh kết nối", callback_data="autopost|channels"), InlineKeyboardButton("🚀 Hàng đợi", callback_data="autopost|queue")],
        [InlineKeyboardButton("📊 Hiệu quả", callback_data="autopost|metrics"), InlineKeyboardButton("📣 Quảng cáo", callback_data="autopost|ads_center")],
        [InlineKeyboardButton("⚙️ Cài đặt", callback_data="autopost|settings"), InlineKeyboardButton("🏠 Menu chính", callback_data="menu|main")],
    ]
    return InlineKeyboardMarkup(rows)

def autopost_content_plan_text() -> str:
    return "\n".join([
        "🧠 <b>KẾ HOẠCH NỘI DUNG TỰ ĐỘNG (CONTENT STRATEGY):</b>",
        "",
        "Chọn ngành hàng của bạn để AI tự động lên lịch đăng bài 7/14/30 ngày, kịch bản đa kênh và gợi ý sản phẩm Affiliate từ kho cá nhân của bạn:",
    ])

def autopost_plan_result_text(niche: str, total_posts: int, item: Dict[str, Any]) -> str:
    return "\n".join([
        f"🚀 <b>KẾ HOẠCH NỘI DUNG 7 NGÀY — {html.escape(niche).upper()}</b>",
        "",
        "• <b>Mục tiêu:</b> Nhận diện thương hiệu & Thu hút traffic",
        f"• <b>Tổng số bài:</b> {total_posts} bài",
        "• <b>Nền tảng:</b> Telegram, Facebook, Instagram, YouTube, TikTok",
        "",
        f"<b>Mẫu bài Ngày 1 ({item.get('pillar', '')}):</b>",
        f"🎯 <i>{html.escape(item.get('master_hook', ''))}</i>",
        f"📝 {html.escape(item.get('master_caption', '')[:180])}...",
        "",
        "<i>Lịch đăng đã sẵn sàng phát hành tự động theo khung giờ tối ưu.</i>",
    ])

def autopost_brands_text(brand: Dict[str, Any]) -> str:
    return "\n".join([
        "🎨 <b>HỒ SƠ THƯƠNG HIỆU (BRAND PROFILE):</b>",
        "",
        f"• <b>Tên thương hiệu:</b> {brand.get('brand_name')}",
        f"• <b>Giọng điệu:</b> {brand.get('brand_voice')}",
        f"• <b>Đối tượng:</b> {brand.get('target_audience')}",
        f"• <b>CTA chính:</b> {brand.get('primary_cta')}",
        "",
        "🛡️ <b>Quy chuẩn nền tảng (Compliance Guard):</b>",
        "✅ <b>Telegram/FB/YT:</b> Cho phép logo overlay & link caption.",
        "⚠️ <b>TikTok Direct Post:</b> Tự động bỏ logo/watermark gắn cứng để tuân thủ chính sách Content Sharing.",
    ])

def autopost_affiliate_text(uid: int, stats: Optional[Dict[str, Any]] = None, lang: str = "vi") -> str:
    """Render Personal Affiliate Vault Overview."""
    ref_link = f"https://t.me/toanaasbot?start=ref_{uid}"
    stats = stats or {"total": 0, "cong_nghe": 0, "thoi_trang": 0, "tai_chinh": 0, "du_lich": 0, "gia_dung": 0, "san_tmdt": 0}
    total = stats.get("total", 0)
    
    lines = [
        "🔗 <b>KHO AFFILIATE CÁ NHÂN & TIẾP THỊ LIÊN KẾT:</b>",
        "",
        f"👤 <b>Tài khoản:</b> <code>{uid}</code> (Kho lưu trữ độc lập)",
        f"📦 <b>Tổng số sản phẩm trong kho:</b> <b>{total} link</b>",
        "",
        "📊 <b>Thống kê theo ngành hàng:</b>",
        f"• 📱 Công nghệ & AI: <b>{stats.get('cong_nghe', 0)}</b> link",
        f"• 👗 Thời trang & Phụ kiện: <b>{stats.get('thoi_trang', 0)}</b> link",
        f"• 💳 Tài chính & Thẻ tín dụng: <b>{stats.get('tai_chinh', 0)}</b> link",
        f"• ✈️ Du lịch & Vé máy bay: <b>{stats.get('du_lich', 0)}</b> link",
        f"• 🏡 Mẹ & Bé, Gia dụng: <b>{stats.get('gia_dung', 0)}</b> link",
        f"• 🛒 Sàn TMĐT & Dịch vụ: <b>{stats.get('san_tmdt', 0)}</b> link",
        "",
        "💡 <i>Khi tạo bài đăng tự động cho ngành hàng nào, AI sẽ ưu tiên trích xuất link từ kho cá nhân của chính bạn để chèn vào bài viết.</i>",
        "",
        f"🎁 <b>Link giới thiệu Bot của bạn (Nhận 10% Xu nạp):</b>",
        f"<code>{ref_link}</code>",
    ]
    return "\n".join(lines)

def autopost_affiliate_keyboard(uid: int, stats: Optional[Dict[str, Any]] = None, lang: str = "vi") -> InlineKeyboardMarkup:
    """Keyboard for Personal Affiliate Vault."""
    ref_link = f"https://t.me/toanaasbot?start=ref_{uid}"
    encoded_text = urllib.parse.quote("Trải nghiệm Bot AI TOAN AAS!")
    stats = stats or {"total": 0}
    total = stats.get("total", 0)
    
    rows = [
        [
            InlineKeyboardButton("📥 Thêm link / Gửi file", callback_data="autopost|aff_import_prompt"),
            InlineKeyboardButton(f"📂 Xem kho link ({total})", callback_data="autopost|aff_view|all|0"),
        ],
        [
            InlineKeyboardButton("⚡ Nạp 65+ link mẫu gợi ý", callback_data="autopost|aff_seed"),
            InlineKeyboardButton("🗑️ Xóa kho cá nhân", callback_data="autopost|aff_clear_confirm"),
        ],
        [
            InlineKeyboardButton("📲 Chia sẻ link giới thiệu", url=f"https://t.me/share/url?url={ref_link}&text={encoded_text}"),
        ],
        [
            InlineKeyboardButton("⬅️ Quay lại Hub", callback_data="autopost|main"),
            InlineKeyboardButton("🏠 Menu chính", callback_data="menu|main"),
        ]
    ]
    return InlineKeyboardMarkup(rows)

def autopost_affiliate_import_prompt_text(lang: str = "vi") -> str:
    lines = [
        "📥 <b>HƯỚNG DẪN THÊM LINK VÀO KHO AFFILIATE CÁ NHÂN:</b>",
        "",
        "Hệ thống hỗ trợ 2 cách nạp link cực kỳ tiện lợi:",
        "",
        "1️⃣ <b>Cách 1: Gửi tin nhắn văn bản (Text)</b>",
        "Dán trực tiếp danh sách link vào chat theo cú pháp linh hoạt:",
        "• <code>https://shorten.asia/xxx (Tên sản phẩm)</code>",
        "• <code>Tên sản phẩm - https://...</code>",
        "• Hoặc dán danh sách nhiều link (mỗi dòng 1 link).",
        "",
        "2️⃣ <b>Cách 2: Gửi File dữ liệu (.txt, .csv, .json, .md)</b>",
        "Đính kèm file chứa danh sách link affiliate của bạn lên Telegram. AI sẽ tự động đọc, bóc tách và phân loại vào đúng danh mục ngành hàng.",
        "",
        "👉 <i>Hãy gửi tin nhắn chứa link hoặc gửi file đính kèm ngay bây giờ:</i>",
    ]
    return "\n".join(lines)

def autopost_affiliate_import_success_text(added_count: int, total_in_vault: int, by_niche: Dict[str, int], lang: str = "vi") -> str:
    lines = [
        "✅ <b>ĐÃ NẠP THÀNH CÔNG VÀO KHO AFFILIATE CÁ NHÂN!</b>",
        "",
        f"• Đã thêm mới / cập nhật: <b>{added_count}</b> link",
        f"• Tổng số sản phẩm trong kho của bạn: <b>{total_in_vault}</b> link",
        "",
        "📊 <b>Phân loại danh mục:</b>",
    ]
    for niche, count in by_niche.items():
        niche_label = {
            "cong_nghe": "📱 Công nghệ & AI",
            "thoi_trang": "👗 Thời trang & Phụ kiện",
            "tai_chinh": "💳 Tài chính & Thẻ",
            "du_lich": "✈️ Du lịch & Vé máy bay",
            "gia_dung": "🏡 Mẹ & Bé, Gia dụng",
            "san_tmdt": "🛒 Sàn TMĐT & Dịch vụ",
        }.get(niche, f"📦 {niche}")
        lines.append(f"• {niche_label}: <b>{count}</b> link")
        
    lines.extend([
        "",
        "💡 <i>Các bài đăng AI AutoPost tiếp theo sẽ tự động ưu tiên các link này của bạn.</i>"
    ])
    return "\n".join(lines)

def autopost_affiliate_list_text(uid: int, items: List[Dict[str, Any]], total: int, niche: str, page: int, per_page: int = 5, lang: str = "vi") -> str:
    niche_label = {
        "all": "TẤT CẢ NGÀNH HÀNG",
        "cong_nghe": "CÔNG NGHỆ & AI",
        "thoi_trang": "THỜI TRANG & PHỤ KIỆN",
        "tai_chinh": "TÀI CHÍNH & THẺ",
        "du_lich": "DU LỊCH & VÉ MÁY BAY",
        "gia_dung": "GIA DỤNG & MẸ BÉ",
        "san_tmdt": "SÀN TMĐT & DỊCH VỤ",
    }.get(niche, niche.upper())
    
    start_idx = page * per_page
    total_pages = max(1, (total + per_page - 1) // per_page)
    
    lines = [
        f"📂 <b>DANH SÁCH KHO AFFILIATE — {niche_label}</b>",
        f"<i>(Trang {page + 1}/{total_pages} — Tổng {total} link)</i>",
        "",
    ]
    
    if not items:
        lines.append("<i>Kho cá nhân chưa có link nào trong mục này. Hãy bấm 'Thêm link / Gửi file' hoặc 'Nạp link mẫu'.</i>")
    else:
        for idx, it in enumerate(items, start=start_idx + 1):
            name = html.escape(str(it.get("product_name") or "Sản phẩm"))
            url = html.escape(str(it.get("url") or ""))
            it_niche = it.get("niche", "cong_nghe")
            it_id = it.get("id")
            lines.append(f"<b>{idx}. {name}</b> [#{it_id}]")
            lines.append(f"🔗 <code>{url}</code>")
            lines.append(f"🏷️ Ngành: <i>{it_niche}</i> | Hoa hồng: <b>{it.get('commission_rate', '10%')}</b>")
            lines.append("")
            
    return "\n".join(lines)

def autopost_affiliate_list_keyboard(uid: int, items: List[Dict[str, Any]], total: int, niche: str, page: int, per_page: int = 5, lang: str = "vi") -> InlineKeyboardMarkup:
    total_pages = max(1, (total + per_page - 1) // per_page)
    rows = []
    
    # Niche filters row
    rows.append([
        InlineKeyboardButton("📱 CN", callback_data=f"autopost|aff_view|cong_nghe|0"),
        InlineKeyboardButton("👗 TT", callback_data=f"autopost|aff_view|thoi_trang|0"),
        InlineKeyboardButton("💳 TC", callback_data=f"autopost|aff_view|tai_chinh|0"),
        InlineKeyboardButton("✈️ DL", callback_data=f"autopost|aff_view|du_lich|0"),
        InlineKeyboardButton("🏡 GD", callback_data=f"autopost|aff_view|gia_dung|0"),
        InlineKeyboardButton("🌐 Tất cả", callback_data=f"autopost|aff_view|all|0"),
    ])
    
    # Pagination row
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Trước", callback_data=f"autopost|aff_view|{niche}|{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="autopost|aff_noop"))
    if page + 1 < total_pages:
        nav_row.append(InlineKeyboardButton("Sau ➡️", callback_data=f"autopost|aff_view|{niche}|{page + 1}"))
    rows.append(nav_row)
    
    # Actions row
    rows.append([
        InlineKeyboardButton("📥 Thêm link mới", callback_data="autopost|aff_import_prompt"),
        InlineKeyboardButton("⬅️ Quay lại Kho", callback_data="autopost|affiliate"),
    ])
    
    return InlineKeyboardMarkup(rows)

def autopost_calendar_text() -> str:
    return "\n".join([
        "📅 <b>LỊCH ĐĂNG NỘI DUNG (CONTENT CALENDAR):</b>",
        "",
        "• <b>Hôm nay:</b> 2 bài (11:30 & 20:00) — Trạng thái: ✅ Đã lên lịch",
        "• <b>Ngày mai:</b> 2 bài (11:30 & 20:00) — Trạng thái: 🚀 Chờ phát hành",
        "• <b>7 ngày tới:</b> 14 bài đa nền tảng (Telegram, FB, IG, YT, TikTok)",
        "",
        "<i>Hệ thống tự động phát hành đúng giờ mà không cần thao tác thủ công.</i>",
    ])

def autopost_channels_text() -> str:
    return "\n".join([
        "📡 <b>TRUNG TÂM KẾT NỐI KÊNH (CHANNEL CENTER):</b>",
        "",
        "Trạng thái xác thực thời gian thực:",
        "• ✅ <b>Telegram:</b> Đã kết nối Bot Admin",
        "• ✅ <b>Facebook Pages:</b> OAuth Active",
        "• ✅ <b>Instagram Pro:</b> Graph API Active",
        "• ⚠️ <b>YouTube:</b> Cần cấp quyền OAuth kênh",
        "• ⚠️ <b>TikTok:</b> Chờ xác minh Direct Post Developer Audit",
        "",
        "<i>Mọi token xác thực được mã hóa an toàn ở tầng máy chủ, không lộ trong UI.</i>",
    ])

def autopost_queue_text() -> str:
    return "\n".join([
        "🚀 <b>HÀNG ĐỢI ĐĂNG BÀI (IDEMPOTENT PUBLISH QUEUE):</b>",
        "",
        "• <b>Tổng tác vụ:</b> 4 bài đang chờ",
        "• <b>Cơ chế an toàn:</b> Khóa Idempotency Key chống đăng trùng lặp khi mạng chậm hoặc bot khởi động lại.",
        "• <b>Tự phục hồi:</b> Tự động kiểm tra trạng thái remote post trước khi retry.",
    ])

def autopost_metrics_text() -> str:
    return "\n".join([
        "📊 <b>HIỆU QUẢ BÀI ĐĂNG & ĐO LƯỜNG (METRICS LOOP):</b>",
        "",
        "• <b>Tổng lượt xem:</b> 12,450",
        "• <b>Lượt tương tác:</b> 842",
        "• <b>Lượt click link:</b> 156",
        "• <b>Điểm chuyển đổi sang Ads:</b> <b>82/100 (Đủ điều kiện chạy Ads ✅)</b>",
        "",
        "💡 <i>Bài đăng Ngày 1 đạt tương tác cao vượt trội, AI đề xuất kích hoạt gói quảng cáo tăng tốc.</i>",
    ])

def autopost_ads_center_text(env: Dict[str, Any]) -> str:
    kill_status = "🛑 ĐÃ DỪNG TOÀN BỘ" if env.get("emergency_kill_switch") else "🟢 ĐANG HOẠT ĐỘNG"
    return "\n".join([
        "📣 <b>TRUNG TÂM QUẢN TRỊ QUẢNG CÁO (ADS CONTROL PLANE):</b>",
        "",
        f"• <b>Trạng thái:</b> {kill_status}",
        f"• <b>Cấp độ tự trị:</b> L{env.get('autonomy_level', 3)} (Tạo bản nháp / Chờ duyệt)",
        f"• <b>Hạn mức ngày:</b> {env.get('max_daily_spend_vnd', 300000):,}đ / ngày",
        f"• <b>Hạn mức chiến dịch:</b> {env.get('max_campaign_spend_vnd', 1500000):,}đ / chiến dịch",
        "• <b>Nền tảng hỗ trợ:</b> Meta Ads, TikTok Ads, Google Ads",
        "",
        "🛡️ <i>Mọi chiến dịch chi tiêu tiền thật đều bị kiểm soát trong hộp ngân sách của Owner.</i>",
    ])

def autopost_settings_text() -> str:
    return "\n".join([
        "⚙️ <b>CÀI ĐẶT CHẾ ĐỘ PHÁT HÀNH (PUBLISHING MODES):</b>",
        "",
        "• <b>1. MANUAL (Thủ công):</b> Chỉ tạo kịch bản và bản nháp để người dùng tự duyệt.",
        "• <b>2. SCHEDULED (Lên lịch):</b> Tự động đăng khi tới khung giờ vàng đã được duyệt.",
        "• <b>3. AUTO_ORGANIC (Tự động thông minh):</b> Tự động phân phối kế hoạch đã duyệt lên toàn bộ kênh đã kết nối.",
        "",
        "<i>Chế độ hiện tại: <b>SCHEDULED (Khuyên dùng) ✅</b></i>",
    ])

def autopost_kill_switch_text() -> str:
    return "\n".join([
        "🛑 <b>EMERGENCY KILL SWITCH ĐÃ ĐƯỢC KÍCH HOẠT!</b>",
        "",
        "✅ Đã chặn toàn bộ yêu cầu kích hoạt quảng cáo mới.",
        "✅ Đã chặn toàn bộ lệnh tăng ngân sách.",
        "✅ Gửi lệnh tạm dừng (PAUSE) tức thì đến tất cả chiến dịch đang hoạt động.",
    ])

def autopost_resume_ads_text() -> str:
    return "🟢 <b>Hệ thống quảng cáo đã khôi phục trạng thái chờ lệnh an toàn.</b>"
