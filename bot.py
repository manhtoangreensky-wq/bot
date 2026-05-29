"""
HoTroToanBot - Trợ lý AI Tối ưu Hóa MMO & Tự động hóa Video
Phiên bản VIP V5 - Đổi tên phân hệ thành KÍCH HOẠT AI TỰ ĐỘNG HÓA
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

# ─── CẤU HÌNH LOGGING ──────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── URL NÚT OPEN ──────────────────────────────────────────────────────
WEB_APP_URL = "https://hoangthai223388-maker.github.io/xx88/redirect.html"

# ─── BẢO MẬT BIẾN MÔI TRƯỜNG LẤY TỪ RAILWAY ─────────────────────────────
TELEGRAM_TOKEN = os.environ.get("BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    logger.error("❌ THIẾU BIẾN MÔI TRƯỜNG! Hãy kiểm tra lại mục Variables trên Railway.")

# ─── KHỞI TẠO AI GEMINI ────────────────────────────────────────────────
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# ─── PROMPT TƯ DUY AI DÀNH CHO MMO & TỰ ĐỘNG HÓA ────────────────────────
SYSTEM_PROMPT = f"""
Bạn là Trợ lý Ảo AI Cấp Cao của hệ thống HoTroToanBot - Chuyên gia về MMO, Freelance, và Tự động hóa quy trình hệ thống bằng AI.
Văn phong chuyên nghiệp, thực tế, tập trung tối ưu hóa lợi nhuận tối đa với chi phí bằng 0 (Zero Cost Automation). 

Khi khách hàng hỏi về cách làm hoặc xin code, bạn phải cung cấp các giải pháp và đoạn code Python thực tế để:
1. Điều khiển các mô hình AI (Sử dụng google-genai bản free hoặc edge-tts miễn phí) để tự sinh nội dung.
2. Sử dụng thư viện MoviePy để tự động chèn sub, ghép âm thanh lồng vào video nền hàng loạt.
3. Sử dụng Playwright/Selenium phối hợp giải pháp giả lập trình duyệt sạch chống quét nuôi tài khoản Facebook Reels/TikTok đăng bài hàng loạt.

Đường link kết nối hệ thống duy nhất:
Link khóa học/Tool AI/Hỗ trợ: <b><a href="https://t.me/hethongtoan">Kết Nối Hệ Thống Toàn</a></b>

Tuyệt đối không dùng dấu sao (*) hoặc gạch dưới (_) của Markdown. Chỉ sử dụng các thẻ HTML được hỗ trợ: <b>, <i>, <a>, <code>.
"""

# ─── NỘI DUNG BÀI VIẾT TƯ VẤN ──────────────────────────────────────────
TEXT_AI_VIDEO = """🤖 <b>HỆ THỐNG KÍCH HOẠT AI TỰ ĐỘNG HÓA (BẢN FREE)</b> 🤖

<i>Tự động hóa 100% quy trình từ kịch bản đến render video nuôi hệ thống tài khoản mạng xã hội lớn mà không tốn chi phí.</i>

━━━━━━━━━━━━━━━━━━━━━━
🧠 <b>I. BỘ NÃO ĐIỀU KHIỂN SCRIPT (MIỄN PHÍ)</b>
• Tận dụng hệ thống <b>Gemini 2.0 Flash API Free Tier</b> kết hợp với Python để tự sinh hàng loạt 100 kịch bản ngắn mỗi ngày theo cấu trúc JSON.

🎙️ <b>II. CÔNG NGHỆ CHUYỂN TEXT-TO-SPEECH KHÔNG GIỚI HẠN</b>
• Thay vì mua ElevenLabs đắt đỏ, hệ thống khuyên dùng <code>edge-tts</code> của Microsoft. Thư viện này chạy trực tiếp bằng Python, hoàn toàn miễn phí và không giới hạn ký tự, giọng đọc AI tự nhiên cực chuẩn.

🎬 <b>III. LẮP RÁP & ĐÓNG GÓI VIDEO TỰ ĐỘNG HÀNG LOẠT</b>
• Viết một đoạn script Python kết hợp thư viện <code>MoviePy</code> để tự đóng gói Video nền (B-roll) + file âm thanh âm đọc + Chèn phụ đề tự động (Subtitles) thành sản phẩm MP4 hoàn chỉnh mà không cần chạm tay vào phần mềm edit.

⚙️ <b>IV. ĐOẠN CODE CODE MẪU BỘ LỌC AUDIO (PYTHON + EDGE-TTS)</b>
<code>import edge_tts\nasync def make_voice(text, output_file):\n    communicate = edge_tts.Communicate(text, "vi-VN-HoaiAnNeural")\n    await communicate.save(output_file)</code>

📲 Liên hệ Hệ Thống Toàn để lấy toàn bộ mã nguồn framework dựng video tự động: <b><a href="https://t.me/hethongtoan">Nhận Framework Automation</a></b>"""

TEXT_FREELANCE = """💼 <b>GIẢI PHÁP FREELANCER & TOÀN DIỆN THƯƠNG HIỆU SỐ</b> 💼

<i>Vận hành hệ thống Freelance tối ưu để chuyển đổi lưu lượng truy cập (Traffic) thành dòng tiền mỗi ngày.</i>

• <b>Khai Thác Bulk Video Faceless:</b> Sản xuất hàng loạt video ngắn cho thị trường ngách (Tài chính, Câu chuyện, Thần thoại, Động lực) chỉ mất 5 phút cài đặt luồng chạy cho hệ thống để phân phối hàng loạt lên các nick vệ tinh Facebook/TikTok.
• <b>Tiếp Thị Liên Kết (Affiliate Matrix):</b> Tự động đăng video hàng loạt phủ kín nền tảng mạng xã hội để tối ưu hóa tỷ lệ chuyển đổi đơn hàng mà không cần tốn tiền chạy quảng cáo.
• <b>Hệ Thống Đăng Bài Tự Động (Auto Upload):</b> Kết hợp Python <code>Playwright</code> với các trình duyệt Antidetect để tự động lên lịch post bài, phân bổ giờ vàng thông minh cho hàng chục kênh TikTok và Facebook cùng lúc."""

# ─── HỆ THỐNG ĐÁP ÁN TỪ KHÓA NHANH ─────────────────────────────────────
KEYWORD_REPLIES = {
    "video": TEXT_AI_VIDEO,
    "ai": TEXT_AI_VIDEO,
    "tiktok": TEXT_AI_VIDEO,
    "facebook": TEXT_AI_VIDEO,
    "reels": TEXT_AI_VIDEO,
    "tự động hóa": TEXT_AI_VIDEO,
    "tu dong hoa": TEXT_AI_VIDEO,
    "kich hoat": TEXT_AI_VIDEO,
    "kích hoạt": TEXT_AI_VIDEO,
    "freelance": TEXT_FREELANCE,
    "kiếm tiền": TEXT_FREELANCE,
    "công cụ": "🛠️ <b>KHO CÔNG CỤ AI MIỄN PHÍ DÀNH CHO HỆ THỐNG MMO:</b>\n\n- Kịch bản: Gemini API (Free tier), Claude.\n- Giọng đọc: Python Edge-TTS (Free 100%).\n- Xử lý Video: MoviePy Core, Pexels API.\n- Trình duyệt nuôi tài khoản: Playwright Automation.\n\nBấm vào nút bên dưới để xem kho công cụ chi tiết.",
    "tool": "🛠️ <b>KHO CÔNG CỤ AI MIỄN PHÍ DÀNH CHO HỆ THỐNG MMO:</b>\n\n- Kịch bản: Gemini API (Free tier), Claude.\n- Giọng đọc: Python Edge-TTS (Free 100%).\n- Xử lý Video: MoviePy Core, Pexels API.\n- Trình duyệt nuôi tài khoản: Playwright Automation.\n\nBấm vào nút bên dưới để xem kho công cụ chi tiết.",
    "admin": "Dạ, để được tư vấn nâng cao về kiến trúc mã nguồn Python Automation hoặc phân tích tài nguyên hệ thống, Quý khách vui lòng kết nối trực tiếp: <b><a href=\"https://t.me/hethongtoan\">HỆ THỐNG TOÀN</a></b>."
}

# ─── KHO FILE ID ẢNH BANNER TRÊN TELEGRAM ──────────────────────────────
IMG_VIDEO      = "AgACAgUAAxkBAAPzahbudVw6wBpMyIwah_9XoBKTGRcAAvgPaxtEaLlUr4O-Ebqn30EBAAMCAAN5AAM7BA"
IMG_FREELANCE  = "AgACAgUAAxkBAAPvahbsSqrvQCcd71o-U12xYzv2hMwAAvYPaxtEaLlUC-iRAAHC9wfoAQADAgADeQADOwQ"

# ─── GIAO DIỆN NÚT BẤM MENU ĐÁY MÀN HÌNH ───────────────────────────────
def get_bottom_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("🚀 KÍCH HOẠT AI TỰ ĐỘNG HÓA")],
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

# ─── HÀM GỬI AN TOÀN - TỰ ĐỘNG FALLBACK NẾU TEXT QUÁ DÀI ─────────────────────
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
        return "Dạ hệ thống phân tích dữ liệu đang bận xử lý dữ liệu, Quý khách vui lòng lựa chọn các phím chức năng tiện ích bên dưới màn hình ạ!"

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
            "🚀 <b>CHÀO MỪNG ĐẾN VỚI HỆ THỐNG HOTROTOANBOT VIP</b>\n\n"
            "🔥 Giải pháp tự động hóa quy trình sản xuất Video ngắn và khai thác MMO bằng hệ thống AI hàng đầu.\n\n"
            "💻 <b>Các phân hệ tính năng lõi:</b>\n"
            "• Quản lý luồng sinh Video ngắn (TikTok/Facebook Reels) tự động hàng loạt.\n"
            "• Phân bổ kiến trúc hệ thống Freelance & Digital Branding tối ưu hóa chi phí.\n"
            "• Đề xuất giải pháp và mã nguồn kết nối API các công cụ AI hoàn toàn miễn phí.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📲 <b>Mã Nguồn Framework Automation:</b> <b><a href=\"https://t.me/hethongtoan\">Kết Nối Hệ Thống Toàn</a></b>\n"
        )
        await update.message.reply_text(text=text, parse_mode="HTML", reply_markup=get_bottom_menu())
        await update.message.reply_text("👇 Bấm <b>Open</b> để mở giao diện quản lý ngay!", parse_mode="HTML", reply_markup=get_open_button())
    except Exception as e:
        logger.error("Lỗi cmd_start: %s", e)

# ─── FILE ID HANDLER LẤY MÃ ẢNH TỰ ĐỘNG ─────────────────────────────────────
async def reply_file_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        file_id = update.message.photo[-1].file_id
        await update.message.reply_text(f"📸 <b>MÃ FILE ID CỦA ẢNH NÀY LÀ:</b>\n\n<code>{file_id}</code>\n\n<i>Hãy copy mã này và dán định cấu hình vào file bot.py</i>", parse_mode="HTML")
    except Exception as e:
        logger.error("Lỗi reply_file_id: %s", e)

# ─── XỬ LÝ TIN NHẮN TEXT & PHÍM BẤM MENU ĐÁY MÀN HÌNH ─────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    user_id = update.effective_user.id

    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        if text == "🚀 KÍCH HOẠT AI TỰ ĐỘNG HÓA":
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
            caption = "Để được hướng dẫn cấu hình chi tiết framework tự động nuôi nhiều tài khoản mạng xã hội bằng Python Playwright, vui lòng liên hệ:"
            inline_kb = InlineKeyboardMarkup([[InlineKeyboardButton("👩🏻‍💻 Trò Chuyện Cùng Hệ Thống Toàn ↗️", url="https://t.me/hethongtoan")]])
            await update.message.reply_text(text=caption, reply_markup=inline_kb)
            return

        # Xử lý Từ khóa & Trí tuệ nhân tạo AI phản hồi sâu
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

# ─── KHỔI CHẠY KHUNG BOT TELEGRAM ───────────────────────────────────────────
def main() -> None:
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Đăng ký các phân hệ Handler cốt lõi
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.PHOTO, reply_file_id))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🤖 HoTroToanBot đang khởi chạy luồng Polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()