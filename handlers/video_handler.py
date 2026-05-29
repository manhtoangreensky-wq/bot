"""
Handler: Tạo & Bán Video
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


async def show_menu(query):
    text = """
🎬 *Tạo & Bán Video*

Chọn hướng bạn muốn khai thác:
"""
    keyboard = [
        [InlineKeyboardButton("🤖 Faceless AI Video", callback_data="video_faceless"),
         InlineKeyboardButton("✂️ Video Editing Service", callback_data="video_editing")],
        [InlineKeyboardButton("📦 Stock Video/Photo", callback_data="video_stock"),
         InlineKeyboardButton("🎓 Khóa học video", callback_data="video_course")],
        [InlineKeyboardButton("🔙 Quay lại", callback_data="back_main")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def handle(query, data):
    handlers = {
        "video_faceless": show_faceless,
        "video_editing": show_editing,
        "video_stock": show_stock,
        "video_course": show_course,
    }
    handler = handlers.get(data)
    if handler:
        await handler(query)


async def show_faceless(query):
    text = """
🤖 *Faceless YouTube Channel với AI*

Tạo kênh YouTube kiếm tiền mà không cần lộ mặt!

*🔧 Quy trình tạo video AI:*
1️⃣ **Ý tưởng** → ChatGPT viết script
2️⃣ **Giọng đọc** → ElevenLabs (giọng tự nhiên)
3️⃣ **Hình ảnh** → Midjourney / Pexels stock
4️⃣ **Video** → CapCut / DaVinci edit
5️⃣ **Thumbnail** → Canva
6️⃣ **Upload & Tối ưu SEO**

*🔥 Niche hot cho Faceless Channel:*
• Top 10 / List videos
• True crime / Horror stories
• History & Documentary
• Finance & Investment tips
• Motivational content
• AI & Technology news

*💰 Thu nhập tiềm năng:*
• 10k views/video × $3-5 RPM = $30-50/video
• 3 videos/tuần × 4 tuần = $360-600/tháng ban đầu
• Scale lên 100k+ views → $1000+/tháng

*🛠️ Tool stack miễn phí/rẻ:*
• ChatGPT Free / Claude
• ElevenLabs (10k chars/tháng miễn phí)
• Pexels, Pixabay (stock free)
• DaVinci Resolve (miễn phí)
• TubeBuddy (SEO YouTube)
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại Video", callback_data="menu_video")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_editing(query):
    text = """
✂️ *Dịch Vụ Video Editing*

Cung cấp dịch vụ chỉnh sửa video cho doanh nghiệp và creator!

*💰 Dịch vụ có thể cung cấp:*
• Short-form (Reels/TikTok/Shorts): 200k-500k/video
• Long-form YouTube: 500k-2M/video
• Corporate video: 2M-10M/video
• Wedding/Event highlight: 3M-15M/video

*🎯 Kiếm khách hàng:*
• Fiverr, Upwork (thị trường quốc tế)
• Facebook Groups doanh nghiệp VN
• LinkedIn outreach
• Portfolio trên Behance/YouTube

*📚 Kỹ năng cần học:*
• DaVinci Resolve (miễn phí, pro)
• Adobe Premiere Pro
• After Effects (motion graphics)
• Color grading

*💡 Tip:*
Tập trung vào 1 niche (ví dụ: chỉ edit video gym, hoặc chỉ edit podcast) để dễ charge giá cao hơn.
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại Video", callback_data="menu_video")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_stock(query):
    text = """
📦 *Bán Stock Video & Photo*

Upload nội dung một lần, thu tiền mãi mãi!

*🌐 Các nền tảng bán stock:*
• **Shutterstock** - Phổ biến nhất, 15-40% hoa hồng
• **Adobe Stock** - 33% hoa hồng
• **Getty Images** - Giá cao nhất, khó được chấp nhận
• **Pond5** - 50% hoa hồng, dễ upload
• **Envato Elements** - Tốt cho template

*📸 Loại nội dung bán chạy:*
• Cảnh thiên nhiên VN (ít ai có)
• Business & workplace
• Food photography
• Drone footage
• Lifestyle người châu Á

*💰 Thu nhập thực tế:*
• 100 files × $1-3/tháng = $100-300/tháng thụ động
• Contributor giỏi: $500-2000/tháng

*💡 Tip:*
Nội dung về Việt Nam (Hội An, Hạ Long, ẩm thực đường phố) rất được tìm kiếm và ít cạnh tranh!
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại Video", callback_data="menu_video")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_course(query):
    text = """
🎓 *Bán Khóa Học Video Online*

Biến kỹ năng của bạn thành thu nhập thụ động!

*🌐 Nền tảng bán khóa học:*
• **Udemy** - Thị trường lớn nhất, cắt 50-75% doanh thu
• **Gumroad** - Giữ 92% doanh thu, phí thấp
• **Teachable** - Chuyên nghiệp, phí $39/tháng
• **YouTube + Patreon** - Community-based
• **Tự host** - WordPress + WooCommerce

*🔥 Chủ đề khóa học bán chạy:*
• Excel / Google Sheets
• Thiết kế Canva
• Chạy quảng cáo Facebook/Google
• Video editing
• Tiếng Anh thực dụng
• Coding Python / No-code

*💡 Quy trình tạo khóa học:*
1. Validate ý tưởng (khảo sát, pre-sell)
2. Outline curriculum chi tiết
3. Quay video (điện thoại + mic tốt là đủ)
4. Edit và upload
5. Marketing qua MXH & email

*💰 Tiềm năng:*
Khóa học $50-200 × 10 học viên/tháng = $500-2000/tháng
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại Video", callback_data="menu_video")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
