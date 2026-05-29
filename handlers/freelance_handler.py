"""
Handler: Freelance Online
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


async def show_menu(query):
    text = """
💼 *Freelance Online*

Bán kỹ năng của bạn cho khách hàng toàn cầu:
"""
    keyboard = [
        [InlineKeyboardButton("🌍 Fiverr & Upwork", callback_data="freelance_platforms"),
         InlineKeyboardButton("✍️ Viết lách & Content", callback_data="freelance_writing")],
        [InlineKeyboardButton("🎨 Design & Creative", callback_data="freelance_design"),
         InlineKeyboardButton("💻 Lập trình & Tech", callback_data="freelance_tech")],
        [InlineKeyboardButton("📊 Marketing & SEO", callback_data="freelance_marketing"),
         InlineKeyboardButton("🌐 Dịch thuật", callback_data="freelance_translate")],
        [InlineKeyboardButton("🔙 Quay lại", callback_data="back_main")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def handle(query, data):
    handlers = {
        "freelance_platforms": show_platforms,
        "freelance_writing": show_writing,
        "freelance_design": show_design,
        "freelance_tech": show_tech,
        "freelance_marketing": show_marketing,
        "freelance_translate": show_translate,
    }
    handler = handlers.get(data)
    if handler:
        await handler(query)


async def show_platforms(query):
    text = """
🌍 *Nền Tảng Freelance Tốt Nhất*

*🏆 Top platforms quốc tế:*

**Fiverr** - fiverr.com
• Khách hàng tìm đến bạn
• Bắt đầu từ $5/gig
• Phí: 20% hoa hồng
• Phù hợp: designer, copywriter, video editor

**Upwork** - upwork.com
• Bạn đấu thầu dự án
• Hourly hoặc fixed-price
• Phí: 20% (giảm dần theo doanh thu)
• Phù hợp: developer, consultant, writer

**Freelancer.com**
• Tương tự Upwork
• Nhiều dự án nhỏ lẻ

**Toptal** - toptal.com
• Chỉ top 3% freelancer
• Rate rất cao ($50-200+/giờ)
• Cần pass screening nghiêm ngặt

*🇻🇳 Platforms Việt Nam:*
• TopDev (lập trình)
• ViecLamTot.com
• Vietnamworks Freelance
• Facebook Groups freelance VN

*💡 Tip bắt đầu:*
Tạo 3 gig chuyên biệt trên Fiverr, tối ưu title với từ khóa, thêm video giới thiệu tăng conversion 200%!
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại Freelance", callback_data="menu_freelance")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_writing(query):
    text = """
✍️ *Freelance Viết Lách & Content*

*💰 Dịch vụ có thể cung cấp:*
• Copywriting (landing page, quảng cáo)
• Content marketing (blog, article)
• Ghostwriting (viết sách, ebook)
• Social media content
• Script viết video/podcast
• Email marketing sequences

*💵 Mức giá tham khảo:*
• Blog post 500 từ: $15-50 (tiếng Anh)
• Landing page: $100-500
• Email sequence (5 emails): $150-300
• Script YouTube 10 phút: $50-100

*🛠️ Tools hỗ trợ:*
• ChatGPT / Claude (ideation, draft)
• Grammarly (kiểm tra grammar)
• Hemingway App (readability)
• Notion (organize projects)

*📈 Cách tìm khách:*
• Fiverr: gig "SEO Blog Writing"
• LinkedIn: outreach marketing agencies
• Cold email blog owners nhỏ
• Reddit: r/HireAWriter
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại Freelance", callback_data="menu_freelance")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_design(query):
    text = """
🎨 *Freelance Design & Creative*

*💰 Dịch vụ phổ biến:*
• Logo design: $50-500
• Brand identity: $200-2000
• Social media kit: $100-300
• UI/UX design: $500-5000
• Illustration: $30-200/piece
• Motion graphics: $100-500/clip

*🛠️ Tools cần biết:*
• **Canva** - Nhanh, dễ, khách VN thích
• **Figma** - UI/UX standard
• **Adobe Illustrator** - Vector professional
• **Photoshop** - Photo manipulation
• **After Effects** - Animation

*📈 Tìm khách:*
• Behance portfolio (rất quan trọng)
• Dribbble (cộng đồng designer)
• Fiverr logo design category
• 99designs contests (luyện tập)

*💡 Tips:*
Chuyên môn hóa = charge cao hơn. "Logo designer" vs "Logo designer cho nhà hàng" → cái sau dễ tìm khách và charge 2-3x hơn!
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại Freelance", callback_data="menu_freelance")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_tech(query):
    text = """
💻 *Freelance Lập Trình & Tech*

*💰 Dịch vụ có nhu cầu cao:*
• Web development (WordPress, React): $500-5000
• Shopify store setup: $200-1000
• Bot Telegram/Discord: $100-500
• Automation (Zapier, Make): $100-300
• Mobile app: $1000-10000+
• API integration: $200-800

*🔥 Kỹ năng hot 2024:*
• No-code (Bubble, Webflow, FlutterFlow)
• AI integration (OpenAI API)
• Shopify development
• WordPress + WooCommerce
• Python automation
• React/Next.js

*📈 Tìm khách:*
• Upwork (tốt nhất cho dev)
• Toptal (high-end)
• LinkedIn (B2B)
• GitHub profile (portfolio tự nhiên)
• Local businesses (website đơn giản)

*💡 Tip:*
No-code skills đang boom! Học Bubble hoặc Webflow trong 1-2 tháng, charge $50-100/giờ ngay cả khi mới bắt đầu.
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại Freelance", callback_data="menu_freelance")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_marketing(query):
    text = """
📊 *Freelance Marketing & SEO*

*💰 Dịch vụ phổ biến:*
• Chạy Facebook Ads: $300-1000/tháng (retainer)
• Google Ads management: $300-1000/tháng
• SEO On-page: $200-500/project
• SEO Monthly: $300-800/tháng
• Email marketing setup: $200-500
• Social media management: $300-700/tháng

*🛠️ Tools cần biết:*
• Meta Ads Manager
• Google Ads + Google Analytics
• SEMrush / Ahrefs (SEO)
• Mailchimp / ActiveCampaign
• Hootsuite / Buffer (scheduling)

*📈 Cách tìm khách:*
• Tiếp cận SME địa phương trực tiếp
• Facebook Groups kinh doanh
• LinkedIn outreach
• Referral từ khách cũ

*💡 Tip:*
Bắt đầu với case study: làm miễn phí/giảm giá cho 1-2 khách, chụp kết quả, dùng làm portfolio để pitch khách trả tiền!
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại Freelance", callback_data="menu_freelance")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_translate(query):
    text = """
🌐 *Freelance Dịch Thuật*

*💰 Cặp ngôn ngữ có nhu cầu cao:*
• Anh - Việt: $0.03-0.08/từ
• Việt - Anh: $0.04-0.10/từ
• Nhật - Việt: $0.05-0.12/từ
• Hàn - Việt: $0.04-0.10/từ

*📋 Loại dịch thuật phổ biến:*
• Dịch tài liệu kinh doanh
• Dịch phụ đề video
• Dịch website/app
• Dịch sách/ebook
• Phiên dịch (online/offline)

*🌐 Tìm việc:*
• ProZ.com (chuyên dịch thuật)
• Gengo.com (volume lớn)
• Upwork (đa dạng)
• Fiverr
• Công ty dịch thuật VN (outsource)

*💡 Chuyên môn hóa:*
Dịch pháp lý, y tế, hoặc kỹ thuật → charge 2-3x so với dịch thông thường!
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại Freelance", callback_data="menu_freelance")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
