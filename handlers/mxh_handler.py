"""
Handler: Kiếm tiền Mạng Xã Hội (Facebook, TikTok, Instagram, YouTube)
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


async def show_menu(query):
    text = """
📱 *Kiếm Tiền Mạng Xã Hội*

Chọn nền tảng bạn muốn khai thác:
"""
    keyboard = [
        [InlineKeyboardButton("🎵 TikTok", callback_data="mxh_tiktok"),
         InlineKeyboardButton("📘 Facebook", callback_data="mxh_facebook")],
        [InlineKeyboardButton("📸 Instagram", callback_data="mxh_instagram"),
         InlineKeyboardButton("▶️ YouTube", callback_data="mxh_youtube")],
        [InlineKeyboardButton("💼 LinkedIn", callback_data="mxh_linkedin"),
         InlineKeyboardButton("🐦 X/Twitter", callback_data="mxh_twitter")],
        [InlineKeyboardButton("🔙 Quay lại", callback_data="back_main")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def handle(query, data):
    handlers = {
        "mxh_tiktok": show_tiktok,
        "mxh_facebook": show_facebook,
        "mxh_instagram": show_instagram,
        "mxh_youtube": show_youtube,
        "mxh_linkedin": show_linkedin,
        "mxh_twitter": show_twitter,
    }
    handler = handlers.get(data)
    if handler:
        await handler(query)


async def show_tiktok(query):
    text = """
🎵 *Kiếm Tiền TikTok*

*💰 Nguồn thu chính:*
• **TikTok Shop** - Bán hàng trực tiếp qua video/livestream
• **Affiliate TikTok** - Hoa hồng 5-30% mỗi đơn hàng
• **TikTok Creator Fund** - Trả tiền theo lượt xem (cần 10k followers)
• **Quảng cáo thương hiệu** - Cần 100k+ followers
• **Livestream Gift** - Nhận quà từ người xem

*📈 Chiến lược tăng trưởng:*
• Đăng 1-3 video/ngày trong 30 ngày đầu
• Dùng trending sounds và hashtags
• Hook mạnh trong 3 giây đầu
• Tương tác với comment sớm sau khi đăng

*🎯 Niche dễ viral tại VN:*
• Ẩm thực & nấu ăn
• Review sản phẩm
• Thủ thuật/mẹo vặt
• Hài hước & giải trí

*🛠️ Tools cần thiết:*
• CapCut (edit video)
• TikTok Analytics (theo dõi hiệu quả)
• Canva (tạo thumbnail)
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại MXH", callback_data="menu_mxh")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_facebook(query):
    text = """
📘 *Kiếm Tiền Facebook*

*💰 Nguồn thu chính:*
• **Facebook Reels Bonus** - Chương trình thưởng creator
• **In-stream Ads** - Quảng cáo giữa video (cần 10k followers + 600k phút xem)
• **Facebook Shop** - Bán hàng trực tiếp
• **Stars** - Nhận sao từ fans khi livestream
• **Subscription** - Fans trả phí để xem nội dung độc quyền

*📈 Chiến lược:*
• Tạo Page riêng (không dùng profile cá nhân)
• Post đều đặn 1-2 lần/ngày
• Reels đang được FB ưu tiên reach
• Join và tương tác trong các Group lớn

*💡 Mẹo tăng reach:*
• Video native (upload trực tiếp, không share từ YT)
• Captions kích thích tương tác ("Tag người...")
• Đăng vào khung 8-9h tối
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại MXH", callback_data="menu_mxh")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_instagram(query):
    text = """
📸 *Kiếm Tiền Instagram*

*💰 Nguồn thu chính:*
• **Sponsored Posts** - Thương hiệu trả để đăng bài quảng cáo
• **Affiliate Links** - Link sản phẩm trong bio/stories
• **Instagram Shop** - Bán sản phẩm trực tiếp
• **Reels Bonus** - Thưởng cho creator Reels (tùy khu vực)
• **Digital Products** - Bán preset, template qua DM

*📈 Chiến lược:*
• Chọn niche rõ ràng (photography, lifestyle, food...)
• Reels > Stories > Feed về mặt reach
• Consistency > Quantity
• Dùng 5-10 hashtags liên quan (không spam 30 hashtags)

*💰 Mức giá sponsorship tham khảo:*
• 1k-10k followers: 200k-1M VNĐ/post
• 10k-100k followers: 1M-10M VNĐ/post
• 100k+ followers: thương lượng
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại MXH", callback_data="menu_mxh")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_youtube(query):
    text = """
▶️ *Kiếm Tiền YouTube*

*💰 Nguồn thu chính:*
• **AdSense** - Quảng cáo trên video (cần 1000 sub + 4000h xem)
• **YouTube Shorts Fund** - Thưởng cho Shorts viral
• **Sponsorship** - Thương hiệu tài trợ video
• **Membership** - Fan trả phí hàng tháng
• **Super Chat/Thanks** - Donate khi livestream

*📈 Chiến lược Faceless Channel:*
• Dùng AI tạo script (ChatGPT)
• Text-to-speech (ElevenLabs)
• Stock footage (Pexels, Pixabay)
• Edit bằng DaVinci Resolve (miễn phí)
• Niche: top 10 lists, horror stories, finance

*💡 Tips quan trọng:*
• Thumbnail quyết định 70% click rate
• Title chứa từ khóa người tìm kiếm
• Upload đều đặn (tối thiểu 1 video/tuần)
• Playlist giúp tăng watch time
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại MXH", callback_data="menu_mxh")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_linkedin(query):
    text = """
💼 *Kiếm Tiền LinkedIn*

*💰 Cách kiếm tiền:*
• **B2B Freelance** - Tìm khách hàng doanh nghiệp
• **Consulting** - Tư vấn chuyên môn
• **Course/Coaching** - Bán khóa học nghề nghiệp
• **Affiliate B2B** - Giới thiệu phần mềm, dịch vụ

*📈 Chiến lược:*
• Tối ưu profile 100% (ảnh, headline, about)
• Post 3-5 lần/tuần nội dung chuyên môn
• Kết nối và tương tác trong ngành
• LinkedIn Newsletter để build audience

*💡 Tips:*
• Posts dạng câu chuyện cá nhân viral nhất
• Kết thúc post bằng câu hỏi để tăng comment
• Giờ đăng tốt: 8-9h sáng, 12h trưa, 5-6h chiều
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại MXH", callback_data="menu_mxh")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_twitter(query):
    text = """
🐦 *Kiếm Tiền X (Twitter)*

*💰 Nguồn thu chính:*
• **X Premium Revenue Share** - Chia sẻ doanh thu quảng cáo (cần 5M impressions/tháng)
• **Affiliate Marketing** - Tweet kèm link affiliate
• **Ghostwriting** - Viết tweet cho người khác ($500-5000/tháng)
• **Newsletter** - Substack, Beehiiv tích hợp
• **Digital Products** - Bán qua Gumroad

*📈 Chiến lược:*
• Thread dạng "How I..." rất viral
• Quote tweet + thêm góc nhìn riêng
• Tương tác với big accounts trong niche
• Post 3-5 tweets/ngày

*💡 Tips:*
• Niche tài chính, crypto, tech dễ monetize nhất
• Build email list từ Twitter
• Dùng Typefully để lên lịch tweet
"""
    keyboard = [[InlineKeyboardButton("🔙 Quay lại MXH", callback_data="menu_mxh")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
