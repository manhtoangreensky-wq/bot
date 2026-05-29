"""
HoTroToanBot - Trợ lý AI Tối ưu Hóa MMO & Tự động hóa Video
Phiên bản VIP - Tích hợp AI Gemini + Menu Đáy + Nút Open
"""

import os
import logging
from google import genai
from google.genai import types
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# ─── CẤU HÌNH LOGGING ──────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── CẤU HÌNH LIÊN KẾT HỆ THỐNG ─────────────────────────────────────────
LINK_BEACON = "https://beacons.ai/toantong199"
WEB_APP_URL = "https://hoangthai223388-maker.github.io/xx88/redirect.html" # Đổi thành link web tool của bồ sau

# ─── BẢO MẬT BIẾN MÔI TRƯỜNG LẤY TỪ RAILWAY ─────────────────────────────
TELEGRAM_TOKEN = os.environ.get("BOT_TOKEN") # Đã sửa cho khớp với biến trên Railway của bồ
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    logger.error("❌ THIẾU BIẾN MÔI TRƯỜNG! Hãy kiểm tra lại mục Variables trên Railway.")

# ─── KHỞI TẠO AI GEMINI ────────────────────────────────────────────────
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# ─── PROMPT TƯ DUY AI DÀNH CHO MMO & TỰ ĐỘNG HÓA ────────────────────────
SYSTEM_PROMPT = f"""
Bạn là Trợ lý Ảo AI Cấp Cao của hệ thống HoTroToanBot - Chuyên gia về MMO (Kiếm tiền online), Freelance, và Tự động hóa quy trình bằng AI.
Văn phong chuyên nghiệp, thực tế, tối ưu hóa lợi nhuận và tư duy hệ thống. 
Khách hàng là những người muốn dùng AI (Gemini, Claude) để điều khiển các AI khác làm video, code, tạo sản phẩm đăng lên TikTok/Facebook Reels.
Mục tiêu là cung cấp các giải pháp miễn phí (Free tier) trước khi họ đầu tư mua VIP.

Các link hệ thống:
1. Link khóa học/Tool AI: <b><a href="https://t.me/toantong199">Truy Cập Kho Tool AI Tự Động</a></b>
2. Link quản lý thương hiệu số: <b><a href="{LINK_BEACON}">Hệ Sinh Thái Kỹ Thuật Số</a></b>

Tuyệt đối không dùng dấu sao (*) hoặc gạch dưới (_) của Markdown. Chỉ sử dụng các thẻ HTML được hỗ trợ: <b>, <i>, <a>, <code>.
"""

# ─── NỘI DUNG BÀI VIẾT TƯ VẤN ──────────────────────────────────────────
TEXT_AI_VIDEO = """🤖 <b>HỆ THỐNG AI TỰ ĐỘNG LÀM VIDEO FB/TIKTOK (BẢN FREE)</b> 🤖

<i>Tự động hóa 100% quy trình từ kịch bản đến render video để nuôi hàng loạt tài khoản mạng xã hội.</i>

━━━━━━━━━━━━━━━━━━━━━━
🧠 <b>I. TẠO KỊCH BẢN & LOGIC (Não bộ)</b>
• Dùng <b>Claude 3.5 Sonnet (Free)</b> hoặc <b>Gemini 1.5 (Free)</b>: Viết script TikTok 15-30s, chia cột rõ ràng: Hình ảnh - Lời đọc - Text trên màn hình.

🎙️ <b>II. TẠO GIỌNG ĐỌC (Voiceover)</b>
• <b>ElevenLabs (Free tier)</b>: 10,000 ký tự/tháng, giọng cực chuẩn.
• <b>CapCut Text-to-Speech (Free)</b>: Có thể tự động hóa thao tác bằng Python (PyAutoGUI).

🎨 <b>III. TẠO HÌNH ẢNH & VIDEO AI</b>
• <b>Leonardo.AI / SeaArt (Free daily credits)</b>: Tạo ảnh minh họa sắc nét.
• <b>Luma Dream Machine / Kling AI (Free daily)</b>: Biến ảnh tĩnh thành video chuyển động (B-roll).

🎬 <b>IV. LẮP RÁP & RENDER HÀNG LOẠT</b>
• Viết một đoạn script Python dùng thư viện <code>MoviePy</code> để tự động ghép Audio + Video + Text lại với nhau thành hàng trăm video một ngày mà không cần mở app sửa tay.

📲 Liên hệ Admin để nhận code mẫu Python ghép video tự động: <b><a href="https://t.me/toantong199">Nhận Code Automation</a></b>"""

TEXT_FREELANCE = """💼 <b>GIẢI PHÁP FREELANCER & KIẾM TIỀN TỐI ƯU</b> 💼

<i>Dùng hệ thống AI tự động để tạo ra sản phẩm bán lấy tiền.</i>

• <b>Bán Video Hàng Loạt:</b> Nhận làm video faceless cho các kênh YouTube, TikTok của người khác. Bạn dùng hệ thống AI phía trên để làm mất 5 phút/video nhưng charge giá 5-10$/video.
• <b>Xây Kênh Nhận Booking/Affiliate:</b> Đẩy mạnh thương hiệu cá nhân hoặc xây kênh chủ đề (Tâm lý, Tài chính, Kể chuyện). Khi kênh có view trên TikTok/FB Reels, gắn link Shopee Affiliate hoặc nhận booking.
• <b>Quản lý Social Media:</b> Nhận quản lý page Facebook/TikTok cho doanh nghiệp. Dùng AI lên lịch bài viết và tạo nội dung cả tháng trong 1 ngày."""

# ─── HỆ THỐNG ĐÁP ÁN TỪ KHÓA NHANH ─────────────────────────────────────
KEYWORD_REPLIES = {
    "video": TEXT_AI_VIDEO,
    "ai": TEXT_AI_VIDEO,
    "tiktok": TEXT_AI_VIDEO,
    "facebook": TEXT_AI_VIDEO,
    "reels": TEXT_AI_VIDEO,
    "freelance": TEXT_FREELANCE,
    "kiếm tiền": TEXT_FREELANCE,
    "công cụ": "🛠️ <b>KHO CÔNG CỤ AI MIỄN PHÍ DÀNH CHO MMO:</b>\n\n- Kịch bản: ChatGPT, Claude, Gemini.\n- Hình ảnh: Leonardo.AI, Bing Image Creator.\n- Video: Luma AI, Kling AI, CapCut.\n- Code Automation: Cursor AI, GitHub Copilot (Trial).\n\nBấm vào nút bên dưới để mở kho công cụ chi tiết.",
    "tool": "🛠️ <b>KHO CÔNG CỤ AI MIỄN PHÍ DÀNH CHO MMO:</b>\n\n- Kịch bản: ChatGPT, Claude, Gemini.\n- Hình ảnh: Leonardo.AI, Bing Image Creator.\n- Video: Luma AI, Kling AI, CapCut.\n- Code Automation: Cursor AI, GitHub Copilot (Trial).\n\nBấm vào nút bên dưới để mở kho công cụ chi tiết.",
    "admin": "Dạ, để được tư vấn thiết lập hệ thống tự động hóa làm video hoặc hướng dẫn chạy script Python, Quý khách vui lòng liên hệ trực tiếp: <b><a href=\"https://t.me/toantong199\">ADMIN HỆ THỐNG</a></b>."
}

# ─── KHO FILE ID ẢNH BANNER TRÊN TELEGRAM ──────────────────────────────
# Tạm thời dùng ảnh cũ, bồ hãy gửi ảnh mới cho bot, lấy File ID từ bot trả về và thay vào đây nhé!
IMG_START      = "AgACAgUAAxkBAAP1ahbu9wl2UOIkh5HyVFiFPbgQwIkAAvkPaxtEaLlUNwymVRbVQTsBAAMCAAN5AAM7BA"
IMG_VIDEO      = "AgACAgUAAxkBAAPzahbudVw6wBpMyIwah_9XoBKTGRcAAvgPaxtEaLlUr4O-Ebqn30EBAAMCAAN5AAM7BA"
IMG_FREELANCE  = "AgACAgUAAxkBAAPvahbsSqrvQCcd71o-U12xYzv2hMwAAvYPaxtEaLlUC-iRAAHC9wfoAQADAgADeQADOwQ"

# ─── GIAO DIỆN NÚT BẤM MENU ĐÁY MÀN HÌNH ───────────────────────────────
def get_bottom_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("🚀 HỆ THỐNG LÀM VIDEO AI")],
        [KeyboardButton("🛠 CÔNG CỤ FREE"), KeyboardButton("💼 FREELANCER MMO")],
        [KeyboardButton("📲 QUẢN LÝ TIKTOK/FB"), KeyboardButton("👩🏻‍💻 LIÊN HỆ ADMIN")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

# ─── NÚT "OPEN" MỞ FULL MÀN HÌNH ───────────────────────────────────────
def get_open_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            text="⚙️ Mở Kho Công Cụ MMO",
            web_app=WebAppInfo(url=WEB_APP_URL)
        )
    ]])

# ─── HÀM GỬI AN TOÀN - TỰ ĐỘNG FALLBACK ────────────────────────────────
async def send_photo_with_long_text(update: Update, photo: str, text: str, reply_markup=None, parse_mode: str = "HTML") -> None:
    CAPTION_LIMIT = 1024
    try:
        if len(text) <= CAPTION_LIMIT:
            await update.message.reply_photo(photo=photo, caption=text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await update.message.reply_photo(photo=photo)
            chunks = [text[i:i + 4096] for i in range(0, len(text), 4096)]
            for idx, chunk in enumerate(chunks):
                kb = reply_markup if idx == len(chunks) - 1 else None
                try:
                    await update.message.reply_text(chunk, reply_markup=kb, parse_mode=parse_mode)
                except Exception:
                    await update.message.reply_text(chunk, reply_markup=kb)
    except Exception as e:
        logger.error("Lỗi send_photo_with_long_text: %s", e)

# ─── XỬ LÝ AI GEMINI ──────────────────────────────────────────────────
conversation_history: dict[int, list] = {}
MAX_HISTORY = 16

def ask_ai(user_id: int, message: str) -> str:
    if user_id not in conversation_history:
        conversation_history[user_id] = []
    conversation_history[user_id].append(types.Content(role="user", parts=[types.Part(text=message)]))
    if len(conversation_history[user_id]) > MAX_HISTORY:
        conversation_history[user_id] = conversation_history[user_id][-MAX_HISTORY:]
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
            contents=conversation_history[user_id],
        )
        reply = response.text
        conversation_history[user_id].append(types.Content(role="model", parts=[types.Part(text=reply)]))
        return reply
    except Exception as e:
        logger.error("Lỗi AI: %s", e)
        return "Dạ hệ thống AI đang quá tải, Quý khách vui lòng lựa chọn các phím chức năng tiện ích bên dưới màn hình ạ!"

def match_keyword(text: str) -> str | None:
    lower = text.lower().strip()
    for kw in sorted(KEYWORD_REPLIES.keys(), key=len, reverse=True):
        if kw in lower:
            return KEYWORD_REPLIES[kw]
    return None

# ─── LỆNH /START ──────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        text = (
            "🚀 <b>CHÀO MỪNG ĐẾN VỚI HỆ THỐNG HOTROTOANBOT</b>\n\n"
            "🔥 Giải pháp tự động hóa Video & Kiếm tiền MMO bằng AI hàng đầu.\n\n"
            "💻 <b>Các tính năng chính:</b>\n"
            "• Tự động tạo video TikTok/Facebook Reels hàng loạt.\n"
            "• Quản lý quy trình Freelance & Digital Branding tối ưu.\n"
            "• Đề xuất tool AI miễn phí giúp giảm chi phí xuống mức 0.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🌐 <b>Hệ Sinh Thái:</b> <b><a href=\"{LINK_BEACON}\">Mở Hệ Thống Cổng Tổng</a></b>\n"
            "📲 <b>Kỹ Thuật/Code Script:</b> <b><a href=\"https://t.me/toantong199\">Kết Nối Trực Tiếp Admin</a></b>\n"
        )
        await update.message.reply_photo(photo=IMG_START, caption=text, parse_mode="HTML", reply_markup=get_bottom_menu())
        await update.message.reply_text("👇 Bấm <b>Open</b> để mở giao diện quản lý ngay!", parse_mode="HTML", reply_markup=get_open_button())
    except Exception as e:
        logger.error("Lỗi cmd_start: %s", e)

# ─── FILE ID HANDLER LẤY ẢNH ──────────────────────────────────────────
async def reply_file_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        file_id = update.message.photo[-1].file_id
        await update.message.reply_text(f"📸 <b>MÃ FILE ID CỦA ẢNH NÀY LÀ:</b>\n\n<code>{file_id}</code>\n\n<i>Hãy copy mã này và dán vào file bot.py</i>", parse_mode="HTML")
    except Exception as e:
        logger.error("Lỗi reply_file_id: %s", e)

# ─── XỬ LÝ TIN NHẮN TEXT & PHÍM BẤM MENU ĐÁY ───────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    user_id = update.effective_user.id

    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        if text == "🚀 HỆ THỐNG LÀM VIDEO AI":
            await send_photo_with_long_text(update, photo=IMG_VIDEO, text=TEXT_AI_VIDEO, parse_mode="HTML")
            return
        elif text == "💼 FREELANCER MMO":
            await send_photo_with_long_text(update, photo=IMG_FREELANCE, text=TEXT_FREELANCE, parse_mode="HTML")
            return
        elif text == "🛠 CÔNG CỤ FREE":
            reply_text = KEYWORD_REPLIES["công cụ"]
            await update.message.reply_text(reply_text, parse_mode="HTML", reply_markup=get_open_button())
            return
        elif text == "📲 QUẢN LÝ TIKTOK/FB" or text == "👩🏻‍💻 LIÊN HỆ ADMIN":
            caption = "Để được hướng dẫn set up luồng tự động hóa nuôi nhiều tài khoản TikTok/Facebook bằng Python, vui lòng liên hệ:"
            inline_kb = InlineKeyboardMarkup([[InlineKeyboardButton("👩🏻‍💻 Trò Chuyện Cùng Chuyên Gia AI ↗️", url="https://t.me/toantong199")]])
            await update.message.reply_photo(photo=IMG_START, caption=caption, reply_markup=inline_kb)
            return

        # Xử lý Từ khóa & AI phản hồi
        reply = match_keyword(text)
        if reply is None:
            reply = ask_ai(user_id, text)

        chunks = [reply[i:i + 4096] for i in range(0, len(reply), 4096)]
        for idx, chunk in enumerate(chunks):
            kb = get_open_button() if idx == len(chunks) - 1 else None
            try:
                await update.message.reply_text(chunk, reply_markup=kb, parse_mode="HTML")
            except Exception:
                await update.message.reply_text(chunk, reply_markup=kb)

    except Exception as main_err:
        logger.error("Lỗi tại handle_message: %s", main_err)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

# ─── KHỞI CHẠY BOT TELEGRAM ───────────────────────────────────────────
def main() -> None:
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.PHOTO, reply_file_id))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()