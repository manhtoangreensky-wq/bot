"""
HoTroToanBot - Khung Cấu Trúc AI Automation & MMO VIP
Bản thô sạch 100% - Đã xóa toàn bộ nội dung Boss Toàn cũ và loại bỏ hoàn toàn Beacon
"""

import os
import logging
import asyncio
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

# ─── CẤU HÌNH LOGGING HỆ THỐNG ──────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── URL NÚT OPEN (MỞ WEB APP TOÀN MÀN HÌNH) ────────────────────────────────────
# Bồ có thể thay link Web App của bồ vào đây sau
WEB_APP_URL = "https://hoangthai223388-maker.github.io/xx88/redirect.html"

# ─── BẢO MẬT BIẾN MÔI TRƯỜNG LẤY TỪ RAILWAY ─────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    logger.error("❌ THIẾU BIẾN MÔI TRƯỜNG! Hãy kiểm tra lại mục Variables trên Railway.")

# ─── KHỞI TẠO AI GEMINI ──────────────────────────────────────────────────
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# ─── PROMPT VIP TƯ DUY AI (ĐÃ LÀM SẠCH NỘI DUNG) ────────────────────────────────
SYSTEM_PROMPT = """
Bạn là Trợ lý Ảo AI Cấp Cao thuộc hệ thống HoTroToanBot.
Nhiệm vụ của bạn là hỗ trợ tư vấn về MMO (Kiếm tiền online), Freelancer và Tự động hóa quy trình (Automation) bằng Python.
Văn phong chuyên nghiệp, tập trung vào giải pháp tối ưu hệ thống, lập trình tự động bằng code.

Khi người dùng yêu cầu kịch bản hoặc mã nguồn, hãy cung cấp các đoạn code Python thực tế sử dụng các thư viện miễn phí như:
- edge-tts (Tạo giọng đọc AI miễn phí)
- MoviePy (Tự động dựng và ghép video hàng loạt)
- Playwright / Selenium (Tự động hóa trình duyệt nuôi và đăng bài mạng xã hội)

Đường link hỗ trợ kỹ thuật duy nhất:
<b><a href="https://t.me/hethongtoan">Kết Nối Hệ Thống Toàn</a></b>

Tuyệt đối không dùng dấu sao (*) hoặc gạch dưới (_) của Markdown. Chỉ sử dụng các thẻ HTML được hỗ trợ: <b>, <i>, <a>, <code>.
"""

# ─── NỘI DUNG THÔ CHO CÁC PHÍM CHỨC NĂNG (BỒ TỰ THAY LINK SAU) ───────────────────
TEXT_KICH_HOAT_AI = """🤖 <b>HỆ THỐNG KÍCH HOẠT AI TỰ ĐỘNG HÓA</b> 🤖

<i>Nơi cấu hình và vận hành các kịch bản tự động hóa sản xuất nội dung số.</i>

━━━━━━━━━━━━━━━━━━━━━━
🧠 <b>1. Lên Kịch Bản Tự Động:</b> Sử dụng Gemini API bản Free kết hợp Python để sinh nội dung hàng loạt.
🎙️ <b>2. Tạo Giọng Đọc Không Giới Hạn:</b> Tích hợp thư viện <code>edge-tts</code> của Microsoft chạy trực tiếp bằng code, hoàn toàn miễn phí.
🎬 <b>3. Render Video Hàng Loạt:</b> Sử dụng thư viện <code>MoviePy</code> để tự động ghép video nền, lồng âm thanh và chèn phụ đề tự động.

📲 Liên hệ Admin để nhận bộ khung mã nguồn: <b><a href="https://t.me/hethongtoan">Nhận Framework Kỹ Thuật</a></b>"""

TEXT_FREELANCER_MMO = """💼 <b>GIẢI PHÁP FREELANCER MMO</b> 💼

<i>Chiến lược tối ưu hóa hệ thống tài khoản mạng xã hội để tạo nguồn thu nhập thụ động.</i>

━━━━━━━━━━━━━━━━━━━━━━
• <b>Hệ Thống Video Ngắn:</b> Sản xuất hàng loạt video ngắn cho thị trường ngách để phủ sóng lưu lượng truy cập sạch trên các nền tảng.
• <b>Tự Động Hóa Vận Hành (Auto Upload):</b> Viết mã Python kết hợp trình duyệt Antidetect để tự động lên lịch và đăng bài trên hàng loạt nick vệ tinh.
• <b>Tiếp Thị Liên Kết:</b> Điều hướng traffic về các link sản phẩm để tối ưu hóa tỷ lệ chuyển đổi.

📲 Nhận tư vấn thiết lập kiến trúc luồng chạy: <b><a href="https://t.me/hethongtoan">Kết Nối Với Kỹ Thuật</a></b>"""

# ─── HỆ THỐNG ĐÁP ÁN TỪ KHÓA NHANH (MẪU) ────────────────────────────────────────
KEYWORD_REPLIES = {
    "kich hoat": TEXT_KICH_HOAT_AI,
    "kích hoạt": TEXT_KICH_HOAT_AI,
    "automation": TEXT_KICH_HOAT_AI,
    "freelance": TEXT_FREELANCER_MMO,
    "kiếm tiền": TEXT_FREELANCER_MMO,
    "công cụ": "🛠️ <b>DANH SÁCH CÔNG CỤ AUTOMATION CORE:</b>\n\n- Kịch bản: Gemini API\n- Giọng đọc: Edge-TTS Python\n- Dựng Video: MoviePy Core\n- Nuôi nick: Playwright Automation",
    "tool": "🛠️ <b>DANH SÁCH CÔNG CỤ AUTOMATION CORE:</b>\n\n- Kịch bản: Gemini API\n- Giọng đọc: Edge-TTS Python\n- Dựng Video: MoviePy Core\n- Nuôi nick: Playwright Automation"
}

# ─── GIAO DIỆN NÚT BẤM MENU ĐÁY MÀN HÌNH ───────────────────────────────────────
def get_bottom_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("🚀 KÍCH HOẠT AI TỰ ĐỘNG HÓA")],
        [KeyboardButton("🛠 CÔNG CỤ FREE"), KeyboardButton("💼 FREELANCER MMO")],
        [KeyboardButton("📲 QUẢN LÝ TIKTOK/FB"), KeyboardButton("👩🏻‍💻 LIÊN HỆ ADMIN")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

# ─── NÚT "OPEN" HIỆN Ở CHAT LIST (WEB APP) ──────────────────────────────────────
def get_open_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            text="⚙️ Mở Kho Công Cụ MMO",
            web_app=WebAppInfo(url=WEB_APP_URL)
        )
    ]])

# ─── XỬ LÝ AI GEMINI PHẢN HỒI LƯU LỊCH SỬ ───────────────────────────────────────
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
        return "Dạ hệ thống AI đang bận xử lý, Quý khách vui lòng thử lại hoặc sử dụng menu phím bấm bên dưới!"

def match_keyword(text: str) -> str | None:
    lower = text.lower().strip()
    for kw in sorted(KEYWORD_REPLIES.keys(), key=len, reverse=True):
        if kw in lower:
            return KEYWORD_REPLIES[kw]
    return None

# ─── LỆNH /START (TIN NHẮN CHỮ VIP SẠCH 100%) ────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        text = (
            "🚀 <b>CHÀO MỪNG ĐẾN VỚI HỆ THỐNG HOTROTOANBOT VIP</b>\n\n"
            "🔥 Giải pháp tự động hóa quy trình sản xuất nội dung số và tối ưu hóa Freelancer MMO hàng đầu.\n\n"
            "💻 <b>Các phân hệ quản trị lõi:</b>\n"
            "• Quản lý luồng kích hoạt AI tự động hóa sản xuất kịch bản và giọng đọc.\n"
            "• Định cấu hình hệ thống dựng video tự động hàng loạt bằng Python.\n"
            "• Đề xuất giải pháp và cung cấp mã nguồn kết nối các công cụ miễn phí.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📲 <b>Hỗ Trợ & Nhận Mã Nguồn Kỹ Thuật:</b> <b><a href=\"https://t.me/hethongtoan\">Kết Nối Hệ Thống Toàn</a></b>"
        )
        await update.message.reply_text(text=text, parse_mode="HTML", reply_markup=get_bottom_menu())
        await update.message.reply_text("👇 Bấm <b>Open</b> để mở giao diện quản lý ngay!", parse_mode="HTML", reply_markup=get_open_button())
    except Exception as e:
        logger.error("Lỗi cmd_start: %s", e)

# ─── XỬ LÝ TIN NHẮN VĂN BẢN & PHÍM BẤM MENU ĐÁY MÀN HÌNH ─────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    user_id = update.effective_user.id

    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        if text == "🚀 KÍCH HOẠT AI TỰ ĐỘNG HÓA":
            await update.message.reply_text(text=TEXT_KICH_HOAT_AI, parse_mode="HTML")
            return
        elif text == "💼 FREELANCER MMO":
            await update.message.reply_text(text=TEXT_FREELANCER_MMO, parse_mode="HTML")
            return
        elif text == "🛠 CÔNG CỤ FREE":
            reply_text = KEYWORD_REPLIES["công cụ"]
            await update.message.reply_text(text=reply_text, parse_mode="HTML", reply_markup=get_open_button())
            return
        elif text == "📲 QUẢN LÝ TIKTOK/FB" or text == "👩🏻‍💻 LIÊN HỆ ADMIN":
            caption = "Để được hướng dẫn chi tiết framework tự động đăng bài nuôi nhiều tài khoản mạng xã hội bằng Python Playwright, vui lòng liên hệ:"
            inline_kb = InlineKeyboardMarkup([[InlineKeyboardButton("👩🏻‍💻 Kết Nối Hệ Thống Toàn ↗️", url="https://t.me/hethongtoan")]])
            await update.message.reply_text(text=caption, reply_markup=inline_kb)
            return

        # Xử lý Từ khóa & Trí tuệ nhân tạo AI phản hồi
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

# ─── KHỞI CHẠY KHUNG BOT TELEGRAM ───────────────────────────────────────────
def main() -> None:
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Đăng ký các phân hệ Handler cốt lõi
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🤖 HoTroToanBot đang khởi chạy luồng Polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()