"""
Handler: Affiliate Marketing
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


async def show_menu(query):
    text = """
🔗 *Affiliate Marketing*

Kiếm hoa hồng khi giới thiệu sản phẩm/dịch vụ:
"""
    keyboard = [
        [InlineKeyboardButton("🇻🇳 Affiliate Việt Nam", callback_data="affiliate_vn"),
         InlineKeyboardButton("🌍 Affiliate Quốc Tế", callback_data="affiliate_intl")],
        [InlineKeyboardButton("📱 Affiliate MXH", callback_data="affiliate_social"),
         InlineKeyboardButton("📝 Chiến lược & Tips", callback_data="affiliate_tips")],
        [InlineKeyboardButton("🔙 Quay lại", callback_data="back_main")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def handle(query, data):
    handlers = {
        "affiliate_vn": show_vn,
        "affiliate_intl": show_intl,
        "affiliate_social": show_social,
        "affiliate_tips": show_tips,
    }
    handler = handlers.get(data)
    if handler:
        await handler(query)


async def show_vn(query):
    text = """
🇻🇳 *Affiliate Việt Nam*

*🛒 Sàn TMĐT:*
• **Shopee Affiliate** - shopee.vn/affiliate (2-8% hoa hồng)
• **Lazada Affiliate** - affiliate.lazada.vn (2-9%)
• **Tiki Affiliate** - tiki.vn/affiliate (2-7%)
• **TikTok Shop Affiliate** - 5-20% (đang hot nhất!)

*💳 Tài chính & Crypto:*
• **Finhay, Momo, VNPay** - Giới thiệu mở tài khoản
• **Sàn crypto VN** - Binance, OKX (có ref link)

*🎓 Giáo dục:*
• **Unica** - Khóa học online VN (20-30%)
• **Edumall** - 20-40%
• **Kyna** - 20-30%

*🏦 Ngân hàng & Thẻ:*
• **Tamo, Finhay** - Giới thiệu vay
• **Các ngân hàng** có chương trình ref

*💡 Tip nhanh:*
TikTok Shop Affiliate đang bùng nổ tại VN! Hoa hồng cao, không cần stock hàng, chỉ cần review video.
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại Affiliate", callback_data="menu_affiliate")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_intl(query):
    text = """
🌍 *Affiliate Quốc Tế*

*💻 Phần mềm & SaaS (hoa hồng cao nhất):*
• **Hostinger** - 60% hoa hồng hosting
• **Semrush** - $200/ref
• **Teachable** - 30% recurring
• **ConvertKit** - 30% recurring hàng tháng
• **ClickFunnels** - 40% recurring

*🛒 Sản phẩm vật lý:*
• **Amazon Associates** - 1-10% tùy category
• **eBay Partner Network** - 1-4%
• **Walmart Affiliates** - 1-4%

*📚 Digital Products:*
• **ClickBank** - 50-75% hoa hồng (!!)
• **ShareASale** - Đa dạng merchants
• **CJ Affiliate** - Nhiều big brands
• **Digistore24** - Alternative to ClickBank

*💡 Best niches cho affiliate:*
• Web hosting (hoa hồng cao)
• VPN services
• Online courses
• Finance & Investment tools
• Health & Wellness
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại Affiliate", callback_data="menu_affiliate")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_social(query):
    text = """
📱 *Affiliate Qua Mạng Xã Hội*

*🎵 TikTok Shop Affiliate (HOT nhất 2024):*
• Đăng ký: TikTok Creator Marketplace
• Review sản phẩm trong video ngắn
• Hoa hồng 5-30% mỗi đơn
• Không cần followers tối thiểu để bắt đầu

*📸 Instagram:*
• Link in Bio (dùng Linktree)
• Story swipe-up (cần 10k+ followers)
• Shopping tags
• Reels với caption kèm link

*📘 Facebook:*
• Facebook Group niche (build trust, rồi share)
• Facebook Page + link affiliate
• Facebook Shop (redirect affiliate)

*▶️ YouTube:*
• Description box (link affiliate)
• Pinned comment
• Cards và End screens
• Dedicated review videos

*💡 Nguyên tắc vàng:*
• Luôn disclose "link affiliate" hoặc "#ad"
• Chỉ promote sản phẩm bạn tin tưởng
• Nội dung chất lượng > spam link
• Build trust trước, bán hàng sau
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại Affiliate", callback_data="menu_affiliate")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_tips(query):
    text = """
📝 *Chiến Lược Affiliate Marketing*

*🎯 Framework cơ bản:*
1. Chọn niche có nhu cầu + sản phẩm affiliate tốt
2. Build traffic (blog, YouTube, TikTok, email list)
3. Tạo nội dung review/comparison chất lượng
4. Đặt link affiliate tự nhiên, không spam
5. Theo dõi analytics và tối ưu

*📊 Loại content affiliate hiệu quả:*
• **"Best X for Y"** - "Best laptop for students"
• **"X vs Y Comparison"** - So sánh 2 sản phẩm
• **"How to X"** - Tutorial + recommend tool
• **"X Review"** - Review chi tiết 1 sản phẩm
• **"X Coupon/Deal"** - Người đang mua hàng

*💰 Math đơn giản:*
Sản phẩm $100 × 30% hoa hồng = $30/sale
10 sales/ngày = $300/ngày = $9,000/tháng 🔥

*⚠️ Tránh sai lầm phổ biến:*
• Promote quá nhiều sản phẩm cùng lúc
• Không test sản phẩm trước khi giới thiệu
• Bỏ qua SEO / traffic dài hạn
• Không build email list song song
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại Affiliate", callback_data="menu_affiliate")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
