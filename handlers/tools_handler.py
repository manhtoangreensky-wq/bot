"""
Handler: Công cụ hỗ trợ
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


async def show_menu(query):
    text = """
🛠️ *Công Cụ Hỗ Trợ Kiếm Tiền*

Tổng hợp tools hữu ích miễn phí:
"""
    keyboard = [
        [InlineKeyboardButton("🤖 AI Tools", callback_data="tools_ai"),
         InlineKeyboardButton("🎨 Design Tools", callback_data="tools_design")],
        [InlineKeyboardButton("📊 Analytics & SEO", callback_data="tools_seo"),
         InlineKeyboardButton("💳 Nhận Thanh Toán", callback_data="tools_payment")],
        [InlineKeyboardButton("⚙️ Automation", callback_data="tools_automation"),
         InlineKeyboardButton("📅 Productivity", callback_data="tools_productivity")],
        [InlineKeyboardButton("🔙 Quay lại", callback_data="back_main")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def handle(query, data):
    handlers = {
        "tools_ai": show_ai,
        "tools_design": show_design,
        "tools_seo": show_seo,
        "tools_payment": show_payment,
        "tools_automation": show_automation,
        "tools_productivity": show_productivity,
    }
    handler = handlers.get(data)
    if handler:
        await handler(query)


async def show_ai(query):
    text = """
🤖 *AI Tools Miễn Phí / Rẻ*

*✍️ Viết & Content:*
• ChatGPT (Free tier) - chat.openai.com
• Claude (Free tier) - claude.ai
• Gemini - gemini.google.com
• Perplexity - perplexity.ai (research)

*🎨 Tạo Ảnh:*
• Midjourney - $10/tháng (tốt nhất)
• DALL-E 3 (trong ChatGPT Plus)
• Adobe Firefly - firefly.adobe.com
• Canva AI - trong Canva miễn phí

*🎵 Giọng đọc & Âm thanh:*
• ElevenLabs - 10k chars/tháng free
• Murf.ai - giọng đọc chuyên nghiệp
• Suno.ai - tạo nhạc AI miễn phí

*🎬 Video AI:*
• Runway ML - tạo/edit video AI
• Pika Labs - text-to-video
• HeyGen - avatar video AI
• CapCut AI - edit tự động

*📊 Productivity AI:*
• Notion AI - $10/tháng
• Gamma.app - tạo presentation
• Otter.ai - transcribe meetings
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại Tools", callback_data="menu_tools")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_design(query):
    text = """
🎨 *Design Tools*

*🖼️ Thiết kế tổng quát:*
• **Canva** - canva.com (miễn phí, rất mạnh)
• **Adobe Express** - Miễn phí cơ bản
• **Figma** - UI/UX, free cho cá nhân

*📱 Edit ảnh:*
• **Photopea** - Photoshop online miễn phí
• **Remove.bg** - Xóa nền ảnh
• **Squoosh** - Compress ảnh
• **Tinypng** - Nén ảnh website

*🎬 Edit Video:*
• **CapCut** - Mobile & Desktop, miễn phí
• **DaVinci Resolve** - Pro, hoàn toàn miễn phí
• **Clipchamp** - Windows built-in
• **iMovie** - Mac/iOS miễn phí

*🎨 Tài nguyên miễn phí:*
• **Pexels** - Stock ảnh/video HD
• **Unsplash** - Stock ảnh đẹp
• **Pixabay** - Ảnh, vector, video
• **FlatIcon** - Icons miễn phí
• **Google Fonts** - Font đẹp
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại Tools", callback_data="menu_tools")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_seo(query):
    text = """
📊 *Analytics & SEO Tools*

*📈 Analytics:*
• **Google Analytics 4** - Miễn phí, bắt buộc
• **Google Search Console** - SEO monitoring
• **Meta Business Suite** - FB/IG analytics
• **TikTok Analytics** - Trong app

*🔍 SEO Research:*
• **Google Keyword Planner** - Miễn phí
• **Ubersuggest** - 3 search/ngày free
• **AnswerThePublic** - Tìm câu hỏi người dùng
• **Google Trends** - Xu hướng tìm kiếm

*🎥 YouTube SEO:*
• **TubeBuddy** - Free tier đủ dùng
• **VidIQ** - Competitor analysis
• **YouTube Studio** - Analytics built-in

*🔗 Backlink & Technical:*
• **Screaming Frog** - 500 URLs free
• **Ahrefs Webmaster** - Miễn phí cơ bản
• **GTmetrix** - Page speed test
• **Google PageSpeed** - Tốc độ trang

*📊 Social Media:*
• **Metricool** - Free plan đủ dùng
• **Later** - Lên lịch đăng bài
• **Buffer** - 3 kênh miễn phí
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại Tools", callback_data="menu_tools")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_payment(query):
    text = """
💳 *Nhận Thanh Toán Quốc Tế*

*🌍 Nhận tiền từ nước ngoài:*

**PayPal**
• Phổ biến nhất, khách quen dùng
• Phí: ~4.4% + $0.3/giao dịch
• Rút về VN: qua ngân hàng liên kết

**Payoneer**
• Tốt nhất cho freelancer
• Phí thấp hơn PayPal
• Thẻ Mastercard để mua sắm
• Liên kết Fiverr, Upwork, Amazon

**Wise (TransferWise)**
• Tỷ giá thực, phí thấp nhất
• Tài khoản đa tiền tệ
• Rút về VN dễ dàng

**Stripe** (nếu có website)
• Chấp nhận thẻ tín dụng
• Cần tài khoản business nước ngoài

*🇻🇳 Thanh toán trong nước:*
• Momo, ZaloPay, ViettelPay
• QR banking (tất cả ngân hàng)
• Chuyển khoản thông thường

*💡 Tip:*
Mở Payoneer ngay cả khi chưa cần - có sẵn tài khoản USD/EUR khi nhận tiền từ Fiverr, Upwork, Amazon.
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại Tools", callback_data="menu_tools")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_automation(query):
    text = """
⚙️ *Automation Tools - Làm Ít, Kiếm Nhiều*

*🔄 Workflow Automation (No-code):*
• **Zapier** - Kết nối 6000+ apps, 100 tasks/tháng free
• **Make (Integromat)** - Mạnh hơn Zapier, 1000 ops/tháng free
• **n8n** - Open source, tự host miễn phí

*📱 Social Media Automation:*
• **Buffer** - Lên lịch đăng 3 kênh free
• **Later** - Tốt cho Instagram
• **Metricool** - All-in-one, free plan
• **Publer** - Lên lịch + analytics

*📧 Email Automation:*
• **Mailchimp** - 1000 contacts free
• **Brevo (Sendinblue)** - 300 emails/ngày free
• **ConvertKit** - 1000 subscribers free

*🤖 Chatbot:*
• **ManyChat** - Facebook/IG chatbot
• **Tidio** - Website chatbot
• Telegram Bot (như bot này!) 😄

*💡 Ví dụ automation đơn giản:*
New follower trên Twitter → Auto DM chào + link → Họ click → Vào email list → Nhận chuỗi email → Mua hàng 🎯
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại Tools", callback_data="menu_tools")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_productivity(query):
    text = """
📅 *Productivity Tools*

*📝 Note-taking & Organization:*
• **Notion** - All-in-one workspace (free)
• **Obsidian** - Personal knowledge base
• **Google Docs/Sheets** - Collaboration
• **Trello** - Kanban boards free

*🗓️ Scheduling:*
• **Calendly** - Book meetings tự động (free)
• **Google Calendar** - Lên lịch cơ bản

*⏱️ Time Tracking:*
• **Toggl** - Free, rất dễ dùng
• **Clockify** - Unlimited free

*📁 File Storage & Sharing:*
• **Google Drive** - 15GB free
• **Dropbox** - 2GB free
• **WeTransfer** - Gửi file lớn free

*💬 Communication:*
• **Discord** - Community building
• **Slack** - Team communication
• **Loom** - Record screen + video

*🔐 Password & Security:*
• **Bitwarden** - Password manager free
• **Google Authenticator** - 2FA

*💡 Combo tối thượng miễn phí:*
Notion + Google Drive + Calendly + Toggl = workflow hoàn chỉnh không tốn đồng nào!
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại Tools", callback_data="menu_tools")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
