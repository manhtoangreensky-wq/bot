"""
HoTroToanBot - Trạm Điều Khiển AI Đa Tác Vụ (Multi-Agent System)
Phiên bản V7.3 - Sửa lỗi kết nối Model 404 sang định dạng Model chuẩn 2026
"""

import os
import logging
import asyncio
import edge_tts
from duckduckgo_search import DDGS
from google import genai
from google.genai import types
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ─── CẤU HÌNH HỆ THỐNG LOGGING ──────────────────────────────────────────────────
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── ĐƯỜNG LINK GIAO DIỆN WEB APP CỦA HỆ THỐNG ──────────────────────────────────
WEB_APP_URL = "https://hoangthai223388-maker.github.io/xx88/redirect.html"

# ─── BẢO MẬT BIẾN MÔI TRƯỜNG LẤY TỪ KHÔNG GIAN RAILWAY ─────────────────────────────
TELEGRAM_TOKEN = os.environ.get("BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    logger.error("❌ THIẾU BIẾN MÔI TRƯỜNG! Vui lòng kiểm tra lại cấu hình trên Railway.")

# ─── KHỞI TẠO ĐỘNG CƠ CORE AI GEMINI SDK ─────────────────────────────────────────
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# ─── CƠ CHẾ BẢO MẬT: TẠM TẮT ĐỂ TEST CÔNG KHAI ───────────────────────────────────
async def restrict_access(update: Update) -> bool:
    """Đã tạm tắt chế độ khóa để bồ test luồng lệnh thuận tiện nhất."""
    return False

# ─── HỆ THỐNG PROMPT ĐỊNH HƯỚNG TƯ DUY CHO CÁC PHÒNG BAN AI ─────────────────────────
CODER_PROMPT = """
Bạn là một Senior Software Engineer. 
Nhiệm vụ: Cung cấp giải pháp lập trình Web, App, Automation, và Tester chuyên sâu.
Quy tắc: Luôn cung cấp code sạch (clean code), tối ưu hiệu suất, có comment giải thích rõ ràng. Phân tích lỗi logic chính xác. Trả lời thẳng vào vấn đề kỹ thuật, không dài dòng.
"""

MMO_PROMPT = """
Bạn là một Chuyên gia MMO & Digital Marketing thực chiến.
Nhiệm vụ: Lập kế hoạch kiếm tiền, kịch bản chuyển đổi cao, chiến lược traffic không đồng.
Quy tắc: Tư duy thực tế, ưu tiên tự động hóa (zero-cost). Đưa ra các bước hành động cụ thể để tạo ra dòng tiền.
"""

GENERAL_PROMPT = "Bạn là Trợ lý AI hệ thống điều khiển. Hãy hướng dẫn người dùng sử dụng các lệnh /code, /mmo, /trend, /voice."

# ─── HÀM LIÊN KẾT GIAO TIẾP VỚI LÕI AI GEMINI CORE ──────────────────────────────────
def call_gemini(prompt_system: str, user_text: str) -> str:
    try:
        # Cấu hình chuẩn hóa tên model cho thư viện mới để kích hoạt luồng truyền tải
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash", 
            config=types.GenerateContentConfig(system_instruction=prompt_system),
            contents=user_text,
        )
        return response.text
    except Exception as e:
        logger.error(f"Gemini Error: {e}")
        error_str = str(e).replace("<", "&lt;").replace(">", "&gt;")
        return f"❌ <b>Lỗi kết nối lõi Gemini API:</b>\n<code>{error_str}</code>"

# ─── PHÂN HỆ 1: KỸ SƯ LẬP TRÌNH CHUYÊN SÂU (/code) ───────────────────────────────────
async def cmd_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    if not context.args:
        await update.message.reply_text("💻 <b>Cú pháp lệnh:</b> <code>/code [Câu hỏi lập trình / Sửa Bug]</code>", parse_mode="HTML")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    user_query = " ".join(context.args)
    reply = call_gemini(CODER_PROMPT, user_query)
    await send_long_text(update, f"👨‍💻 <b>CHUYÊN GIA LẬP TRÌNH VÀ TESTER:</b>\n\n{reply}")

# ─── PHÂN HỆ 2: CHIẾN LƯỢC GIA MMO & MARKETING (/mmo) ───────────────────────────────
async def cmd_mmo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    if not context.args:
        await update.message.reply_text("💰 <b>Cú pháp lệnh:</b> <code>/mmo [Câu hỏi MMO / Viết kịch bản]</code>", parse_mode="HTML")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    user_query = " ".join(context.args)
    reply = call_gemini(MMO_PROMPT, user_query)
    await send_long_text(update, f"💡 <b>CHIẾN LƯỢC GIA HỆ THỐNG MMO:</b>\n\n{reply}")

# ─── PHÂN HỆ 3: CÀO TIN TỨC & PHÂN TÍCH XU HƯỚNG MẠNG (/trend) ─────────────────────────
async def cmd_trend(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    if not context.args:
        await update.message.reply_text("📈 <b>Cú pháp lệnh:</b> <code>/trend [Từ khóa quét mạng]</code>", parse_mode="HTML")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    keyword = " ".join(context.args)
    try:
        results = DDGS().text(keyword, max_results=5)
        if not results:
            await update.message.reply_text("❌ Hệ thống mạng không tìm thấy tin tức mới nào liên quan.")
            return
        
        response_text = f"🌍 <b>KẾT QUẢ DỮ LIỆU QUÉT XU HƯỚNG: '{keyword}'</b>\n\n"
        for idx, res in enumerate(results):
            response_text += f"{idx+1}. <b>{res['title']}</b>\n- <i>{res['body']}</i>\n🔗 <a href='{res['href']}'>Link đọc nguồn bài viết</a>\n\n"
        
        await update.message.reply_text(response_text, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        await update.message.reply_text(f"❌ Quá trình cào mạng dữ liệu thất bại: {e}")

# ─── PHÂN HỆ 4: KÍCH HOẠT GENERATE GIỌNG ĐỌC NAM MIỄN PHÍ (/voice) ────────────────────
async def cmd_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    if not context.args:
        await update.message.reply_text("🎙️ <b>Cú pháp lệnh:</b> <code>/voice [Đoạn văn bản cần đọc]</code>", parse_mode="HTML")
        return
    
    text = " ".join(context.args)
    user_id = update.effective_user.id
    output_file = f"voice_{user_id}.mp3"
    status_msg = await update.message.reply_text("⏳ <i>Đang kết nối máy chủ Microsoft render âm thanh...</i>", parse_mode="HTML")
    
    try:
        communicate = edge_tts.Communicate(text, "vi-VN-NamMinhNeural")
        await communicate.save(output_file)
        with open(output_file, 'rb') as audio_file:
            await update.message.reply_audio(audio=audio_file, caption="✅ Hệ thống Render file âm thanh thành công!")
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ Luồng tạo audio thất bại. Lỗi tham số: {e}")
    finally:
        if os.path.exists(output_file): os.remove(output_file)

# ─── THUẬT TOÁN BỔ TRỢ: TỰ ĐỘNG CHIA NHỎ TIN NHẮN TRÁNH TRÀN KHUNG TELEGRAM ─────────
async def send_long_text(update: Update, text: str):
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        try:
            await update.message.reply_text(chunk, parse_mode="HTML")
        except:
            await update.message.reply_text(chunk)

# ─── THIẾT LẬP PHÍM CHỨC NĂNG VÀ LỆNH KHỞI ĐỘNG CƠ /START ─────────────────────────────
def get_bottom_menu() -> ReplyKeyboardMarkup:
    keyboard = [[KeyboardButton("🛠 BẢNG ĐIỀU KHIỂN HỆ THỐNG")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

def get_open_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(text="⚙️ Mở Kho Công Cụ MMO", web_app=WebAppInfo(url=WEB_APP_URL))
    ]])

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    text = (
        "🛸 <b>TRẠM ĐIỀU KHIỂN ĐA TÁC VỤ AI HOÀN CHỈNH</b>\n\n"
        "Chào mừng sếp đã quay trở lại phòng làm việc trung tâm. Hãy sử dụng các phân hệ lệnh sau để giao việc cho các trưởng phòng AI:\n\n"
        "👨‍💻 <code>/code [Nội dung]</code> : Gọi kỹ sư phần mềm (Web/App/Automation/Tester)\n"
        "💰 <code>/mmo [Nội dung]</code> : Gọi chuyên gia tư vấn kiếm tiền & Kịch bản Marketing\n"
        "📈 <code>/trend [Từ khóa]</code> : Cào dữ liệu mạng phân tích xu hướng thời gian thực\n"
        "🎙️ <code>/voice [Văn bản]</code> : Render file giọng đọc AI Nam Minh MP3\n\n"
        "🔓 <i>Trạng thái bảo mật: Chế độ Private đang TẠM TẮT để phục vụ quá trình test luồng tính năng công khai.</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=get_bottom_menu())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    text = update.message.text.strip()
    if text == "🛠 BẢNG ĐIỀU KHIỂN HỆ THỐNG":
        await cmd_start(update, context)
        return
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = call_gemini(GENERAL_PROMPT, text)
    await update.message.reply_text(reply, reply_markup=get_open_button())

# ─── KHỞI CHẠY KHUNG ĐIỀU HÀNH LUỒNG POLLING HỆ THỐNG ────────────────────────────────
def main() -> None:
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("code", cmd_code))
    app.add_handler(CommandHandler("mmo", cmd_mmo))
    app.add_handler(CommandHandler("trend", cmd_trend))
    app.add_handler(CommandHandler("voice", cmd_voice))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🤖 Trạm Điều Khiển Multi-Agent đang chạy...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()