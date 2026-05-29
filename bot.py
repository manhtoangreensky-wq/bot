"""
HoTroToanBot - Bot hỗ trợ kiếm tiền online
Telegram Bot chính
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from config import BOT_TOKEN, ADMIN_IDS
from handlers import (
    mxh_handler,
    video_handler,
    freelance_handler,
    affiliate_handler,
    tools_handler,
    admin_handler,
)

# Cấu hình logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ─── MENU CHÍNH ────────────────────────────────────────────────
MAIN_MENU_TEXT = """
🤖 *Chào mừng đến với HoTroToanBot!*

Bot hỗ trợ kiếm tiền online toàn diện 💰

Chọn lĩnh vực bạn muốn khám phá:
"""

def main_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("📱 Kiếm tiền MXH", callback_data="menu_mxh"),
            InlineKeyboardButton("🎬 Tạo & Bán Video", callback_data="menu_video"),
        ],
        [
            InlineKeyboardButton("💼 Freelance Online", callback_data="menu_freelance"),
            InlineKeyboardButton("🔗 Affiliate Marketing", callback_data="menu_affiliate"),
        ],
        [
            InlineKeyboardButton("🌐 Kiếm Tiền Web/App", callback_data="menu_web"),
            InlineKeyboardButton("🛠️ Công cụ hỗ trợ", callback_data="menu_tools"),
        ],
        [
            InlineKeyboardButton("📚 Tài nguyên học tập", callback_data="menu_learn"),
            InlineKeyboardButton("💬 Cộng đồng & Hỏi đáp", callback_data="menu_community"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


# ─── COMMAND HANDLERS ──────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /start - Hiện menu chính"""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.first_name}) started the bot")
    await update.message.reply_text(
        MAIN_MENU_TEXT,
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /help"""
    help_text = """
📖 *Hướng dẫn sử dụng HoTroToanBot*

*Lệnh cơ bản:*
/start - Mở menu chính
/help - Xem hướng dẫn
/menu - Quay về menu chính
/tip - Tip kiếm tiền ngẫu nhiên
/tools - Danh sách công cụ miễn phí

*Lệnh nâng cao:*
/idea - Gợi ý ý tưởng kiếm tiền
/checklist - Checklist bắt đầu kiếm tiền online
/resource - Tài nguyên & link hữu ích

Gõ bất kỳ câu hỏi nào, bot sẽ cố gắng hỗ trợ! 💪
"""
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /menu - Quay lại menu chính"""
    await update.message.reply_text(
        MAIN_MENU_TEXT,
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown"
    )


async def tip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /tip - Gửi tip kiếm tiền ngẫu nhiên"""
    import random
    tips = [
        "💡 Bắt đầu với 1 kênh duy nhất, làm thật tốt trước khi mở rộng.",
        "💡 Nội dung giải quyết vấn đề cụ thể luôn hiệu quả hơn nội dung chung chung.",
        "💡 Tái sử dụng nội dung: 1 video dài → shorts, reels, bài blog, tweet.",
        "💡 Email marketing vẫn là kênh ROI cao nhất năm 2024.",
        "💡 Affiliate sản phẩm số (khóa học, phần mềm) hoa hồng cao hơn hàng vật lý.",
        "💡 Fiverr và Upwork: niche càng hẹp, càng dễ cạnh tranh và charge cao.",
        "💡 Shorts/Reels 15-30 giây đang được thuật toán ưu tiên phân phối.",
        "💡 Dùng ChatGPT để tạo ý tưởng content, nhưng luôn thêm góc nhìn cá nhân.",
        "💡 Bán templates, preset, Notion dashboard — làm 1 lần, bán mãi mãi.",
        "💡 Community building (group, channel) giúp bán hàng dễ hơn 10 lần quảng cáo.",
    ]
    await update.message.reply_text(random.choice(tips))


async def idea_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /idea - Gợi ý ý tưởng kiếm tiền"""
    ideas_text = """
💰 *Ý tưởng kiếm tiền online nổi bật 2024:*

*🔥 Đang trending:*
• Faceless YouTube channel (dùng AI tạo video)
• Bán Prompt AI (ChatGPT, Midjourney)
• Digital Products trên Gumroad/Etsy
• UGC Creator cho các thương hiệu

*📱 Mạng xã hội:*
• TikTok Shop + Affiliate
• Instagram Reels monetization
• Facebook Reels bonus program
• Pinterest affiliate marketing

*💻 Kỹ năng số:*
• Thiết kế Canva template bán trên Etsy
• Lập trình no-code (Bubble, Webflow)
• Video editing cho doanh nghiệp nhỏ
• Dịch thuật + biên dịch nội dung

*📊 Đầu tư thụ động:*
• Staking crypto (nghiên cứu kỹ trước)
• Print-on-demand (Redbubble, Merch)
• Stock photos/videos (Shutterstock)
"""
    await update.message.reply_text(ideas_text, parse_mode="Markdown")


async def checklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /checklist"""
    checklist_text = """
✅ *Checklist bắt đầu kiếm tiền online:*

*Bước 1 - Chuẩn bị:*
☐ Xác định kỹ năng/sở thích của bạn
☐ Chọn 1 hướng kiếm tiền để tập trung
☐ Tạo tài khoản PayPal / Payoneer / Wise

*Bước 2 - Xây dựng nền tảng:*
☐ Tạo profile chuyên nghiệp (LinkedIn, Fiverr)
☐ Tạo tài khoản mạng xã hội riêng cho công việc
☐ Cài đặt các công cụ cần thiết (Canva, CapCut...)

*Bước 3 - Bắt đầu tạo thu nhập:*
☐ Publish nội dung/dịch vụ đầu tiên
☐ Quảng bá trong community phù hợp
☐ Thu thập feedback và cải thiện

*Bước 4 - Scale up:*
☐ Tối ưu những gì đang hoạt động
☐ Tự động hóa quy trình lặp lại
☐ Mở rộng sang kênh/nguồn thu nhập mới

Gõ /tip để nhận mẹo kiếm tiền! 💪
"""
    await update.message.reply_text(checklist_text, parse_mode="Markdown")


async def resource_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /resource - Tài nguyên hữu ích"""
    resource_text = """
🔗 *Tài nguyên & Công cụ Miễn Phí:*

*🎨 Thiết kế & Video:*
• [Canva](https://canva.com) - Thiết kế miễn phí
• [CapCut](https://capcut.com) - Edit video
• [DaVinci Resolve](https://blackmagicdesign.com) - Edit pro miễn phí
• [Pexels](https://pexels.com) - Stock ảnh/video free

*🤖 AI Tools:*
• [ChatGPT](https://chat.openai.com) - Viết content
• [Gamma.app](https://gamma.app) - Tạo presentation AI
• [ElevenLabs](https://elevenlabs.io) - Giọng đọc AI
• [Suno.ai](https://suno.ai) - Tạo nhạc AI

*💰 Kiếm tiền:*
• [Fiverr](https://fiverr.com) - Bán dịch vụ
• [Gumroad](https://gumroad.com) - Bán sản phẩm số
• [Ko-fi](https://ko-fi.com) - Nhận donate
• [Admitad](https://admitad.com) - Affiliate VN

*📊 Phân tích & SEO:*
• [Google Trends](https://trends.google.com)
• [Ubersuggest](https://neilpatel.com/ubersuggest/)
• [TubeBuddy](https://tubebuddy.com) - YouTube tools
"""
    await update.message.reply_text(resource_text, parse_mode="Markdown", disable_web_page_preview=True)


# ─── CALLBACK HANDLER ──────────────────────────────────────────
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý tất cả inline button callbacks"""
    query = update.callback_query
    await query.answer()
    data = query.data

    # Routing đến các handler chuyên biệt
    if data.startswith("mxh_"):
        await mxh_handler.handle(query, data)
    elif data.startswith("video_"):
        await video_handler.handle(query, data)
    elif data.startswith("freelance_"):
        await freelance_handler.handle(query, data)
    elif data.startswith("affiliate_"):
        await affiliate_handler.handle(query, data)
    elif data.startswith("tools_"):
        await tools_handler.handle(query, data)
    elif data == "menu_mxh":
        await mxh_handler.show_menu(query)
    elif data == "menu_video":
        await video_handler.show_menu(query)
    elif data == "menu_freelance":
        await freelance_handler.show_menu(query)
    elif data == "menu_affiliate":
        await affiliate_handler.show_menu(query)
    elif data == "menu_web":
        await show_web_menu(query)
    elif data == "menu_tools":
        await tools_handler.show_menu(query)
    elif data == "menu_learn":
        await show_learn_menu(query)
    elif data == "menu_community":
        await show_community_menu(query)
    elif data == "back_main":
        await query.edit_message_text(
            MAIN_MENU_TEXT,
            reply_markup=main_menu_keyboard(),
            parse_mode="Markdown"
        )


async def show_web_menu(query):
    text = """
🌐 *Kiếm Tiền Web & App*

Các phương thức kiếm tiền qua website và ứng dụng:
"""
    keyboard = [
        [InlineKeyboardButton("📰 Google AdSense", callback_data="web_adsense"),
         InlineKeyboardButton("🛒 Dropshipping", callback_data="web_dropship")],
        [InlineKeyboardButton("📧 Email Marketing", callback_data="web_email"),
         InlineKeyboardButton("🎮 App kiếm tiền", callback_data="web_apps")],
        [InlineKeyboardButton("🔙 Quay lại", callback_data="back_main")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_learn_menu(query):
    text = """
📚 *Tài nguyên học tập*

Học để kiếm tiền hiệu quả hơn:
"""
    keyboard = [
        [InlineKeyboardButton("🎥 Khóa học miễn phí", callback_data="learn_free"),
         InlineKeyboardButton("📖 Sách hay nên đọc", callback_data="learn_books")],
        [InlineKeyboardButton("🎙️ Podcast kiếm tiền", callback_data="learn_podcast"),
         InlineKeyboardButton("📺 YouTube channels", callback_data="learn_youtube")],
        [InlineKeyboardButton("🔙 Quay lại", callback_data="back_main")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_community_menu(query):
    text = """
💬 *Cộng đồng & Hỏi đáp*

Kết nối với cộng đồng kiếm tiền online:
"""
    keyboard = [
        [InlineKeyboardButton("❓ Hỏi đáp nhanh", callback_data="community_qa"),
         InlineKeyboardButton("🤝 Tìm partner", callback_data="community_partner")],
        [InlineKeyboardButton("📣 Chia sẻ kết quả", callback_data="community_share"),
         InlineKeyboardButton("🏆 Thách thức 30 ngày", callback_data="community_challenge")],
        [InlineKeyboardButton("🔙 Quay lại", callback_data="back_main")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


# ─── MESSAGE HANDLER ───────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý tin nhắn thông thường"""
    text = update.message.text.lower()
    user = update.effective_user

    # Keywords cơ bản
    if any(word in text for word in ["kiếm tiền", "kiem tien", "money", "thu nhập"]):
        await update.message.reply_text(
            "💰 Bạn muốn kiếm tiền online? Dùng /start để xem tất cả các hướng!",
        )
    elif any(word in text for word in ["video", "youtube", "tiktok"]):
        await update.message.reply_text(
            "🎬 Quan tâm đến video content? Gõ /start và chọn 'Tạo & Bán Video'!",
        )
    elif any(word in text for word in ["affiliate", "tiếp thị liên kết"]):
        await update.message.reply_text(
            "🔗 Affiliate Marketing rất tiềm năng! Gõ /start và chọn 'Affiliate Marketing'!",
        )
    elif "xin chào" in text or "hello" in text or "hi" in text:
        await update.message.reply_text(
            f"Chào {user.first_name}! 👋 Gõ /start để khám phá cách kiếm tiền online nhé!"
        )
    else:
        await update.message.reply_text(
            "🤔 Mình chưa hiểu ý bạn. Gõ /help để xem hướng dẫn hoặc /start để vào menu chính!"
        )


# ─── ERROR HANDLER ─────────────────────────────────────────────
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception while handling an update: {context.error}")


# ─── MAIN ──────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("tip", tip_command))
    app.add_handler(CommandHandler("idea", idea_command))
    app.add_handler(CommandHandler("checklist", checklist_command))
    app.add_handler(CommandHandler("resource", resource_command))

    # Admin commands
    app.add_handler(CommandHandler("broadcast", admin_handler.broadcast))
    app.add_handler(CommandHandler("stats", admin_handler.stats))

    # Callbacks
    app.add_handler(CallbackQueryHandler(button_callback))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Error handler
    app.add_error_handler(error_handler)

    logger.info("🤖 HoTroToanBot đang chạy...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
# sửa lỗi chạy bot
