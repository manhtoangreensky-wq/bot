"""
HoTroToanBot - Trạm Điều Khiển AI Đa Tác Vụ (Multi-Agent System)
Phiên bản V6 - Tích hợp Chuyên gia Code, Chuyên gia MMO, Cào Trend và Media
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

# ─── CẤU HÌNH HỆ THỐNG ──────────────────────────────────────────────────
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

WEB_APP_URL = "https://hoangthai223388-maker.github.io/xx88/redirect.html"
TELEGRAM_TOKEN = os.environ.get("BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    logger.error("❌ THIẾU BIẾN MÔI TRƯỜNG!")

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# ─── BỘ PROMPT ĐIỀU KHIỂN CÁC "TRƯỞNG PHÒNG AI" ─────────────────────────

# 1. Trưởng phòng Lập trình (Dev/Tester)
CODER_PROMPT = """
Bạn là một Senior Software Engineer 10 năm kinh nghiệm. 
Nhiệm vụ: Cung cấp giải pháp lập trình Web, App, Automation, và Tester chuyên sâu.
Quy tắc: Luôn cung cấp code sạch (clean code), tối ưu hiệu suất, có comment giải thích rõ ràng. Phân tích lỗi logic chính xác. Trả lời thẳng vào vấn đề kỹ thuật, không dài dòng.
"""

# 2. Trưởng phòng MMO (Chiến lược gia)
MMO_PROMPT = """
Bạn là một Chuyên gia MMO & Digital Marketing thực chiến.
Nhiệm vụ: Lập kế hoạch kiếm tiền, kịch bản chuyển đổi cao, chiến lược traffic không đồng.
Quy tắc: Tư duy thực tế, ưu tiên tự động hóa (zero-cost). Đưa ra các bước hành động cụ thể (Actionable steps) để tạo ra dòng tiền.
"""

# 3. Lễ tân (Trả lời chung chung khi không dùng lệnh)
GENERAL_PROMPT = "Bạn là Trợ lý AI hệ thống điều khiển. Hãy hướng dẫn người dùng sử dụng các lệnh /code, /mmo, /trend, /voice."

# ─── HÀM GIAO TIẾP VỚI LÕI AI GEMINI ────────────────────────────────────
def call_gemini(prompt_system: str, user_text: str) -> str:
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            config=types.GenerateContentConfig(system_instruction=prompt_system),
            contents=user_text,
        )
        return response.text
    except Exception as e:
        logger.error(f"Gemini Error: {e}")
        return "❌ Hệ thống AI đang quá tải hoặc lỗi kết nối API."

# ─── MODULE 1: CHUYÊN GIA LẬP TRÌNH (/code) ─────────────────────────────
async def cmd_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("💻 <b>Nhập lệnh:</b> <code>/code [Câu hỏi lập trình]</code>", parse_mode="HTML")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    user_query = " ".join(context.args)
    reply = call_gemini(CODER_PROMPT, user_query)
    await send_long_text(update, f"👨‍💻 <b>CHUYÊN GIA LẬP TRÌNH:</b>\n\n{reply}")

# ─── MODULE 2: CHUYÊN GIA MMO (/mmo) ────────────────────────────────────
async def cmd_mmo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("💰 <b>Nhập lệnh:</b> <code>/mmo [Câu hỏi kiếm tiền/Kịch bản]</code>", parse_mode="HTML")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    user_query = " ".join(context.args)
    reply = call_gemini(MMO_PROMPT, user_query)
    await send_long_text(update, f"💡 <b>CHIẾN LƯỢC GIA MMO:</b>\n\n{reply}")

# ─── MODULE 3: TÌM KIẾM TREND THỜI GIAN THỰC (/trend) ───────────────────
async def cmd_trend(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("📈 <b>Nhập lệnh:</b> <code>/trend [Từ khóa cần tìm]</code>", parse_mode="HTML")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    keyword = " ".join(context.args)
    try:
        results = DDGS().text(keyword, max_results=5)
        if not results:
            await update.message.reply_text("❌ Không tìm thấy thông tin mới nào.")
            return
        
        response_text = f"🌍 <b>KẾT QUẢ QUÉT TREND: '{keyword}'</b>\n\n"
        for idx, res in enumerate(results):
            response_text += f"{idx+1}. <b>{res['title']}</b>\n- <i>{res['body']}</i>\n🔗 <a href='{res['href']}'>Link</a>\n\n"
        
        await update.message.reply_text(response_text, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi cào dữ liệu: {e}")

# ─── MODULE 4: TẠO GIỌNG ĐỌC (/voice) ───────────────────────────────────
async def cmd_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("🎙️ <b>Nhập lệnh:</b> <code>/voice [Nội dung cần đọc]</code>", parse_mode="HTML")
        return
    
    text = " ".join(context.args)
    user_id = update.effective_user.id
    output_file = f"voice_{user_id}.mp3"
    status_msg = await update.message.reply_text("⏳ <i>Đang render âm thanh...</i>", parse_mode="HTML")
    
    try:
        communicate = edge_tts.Communicate(text, "vi-VN-NamMinhNeural")
        await communicate.save(output_file)
        with open(output_file, 'rb') as audio_file:
            await update.message.reply_audio(audio=audio_file, caption="✅ Render thành công!")
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ Lỗi Voice: {e}")
    finally:
        if os.path.exists(output_file): os.remove(output_file)

# ─── HÀM HỖ TRỢ CHIA NHỎ TIN NHẮN DÀI ───────────────────────────────────
async def send_long_text(update: Update, text: str):
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        try:
            await update.message.reply_text(chunk, parse_mode="HTML")
        except:
            await update.message.reply_text(chunk) # Fallback nếu HTML lỗi syntax

# ─── GIAO DIỆN MENU & LỆNH /START ───────────────────────────────────────
def get_bottom_menu() -> ReplyKeyboardMarkup:
    keyboard = [[KeyboardButton("🛠 BẢNG ĐIỀU KHIỂN HỆ THỐNG")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "🛸 <b>TRẠM ĐIỀU KHIỂN ĐA TÁC VỤ AI KÍCH HOẠT</b>\n\n"
        "Hệ thống đã phân luồng các chuyên gia. Vui lòng sử dụng các lệnh sau để ra việc:\n\n"
        "👨‍💻 <code>/code [Câu hỏi]</code> : Gọi kỹ sư lập trình (Web/App/Auto)\n"
        "💰 <code>/mmo [Câu hỏi]</code> : Gọi chuyên gia kiếm tiền, kịch bản\n"
        "📈 <code>/trend [Từ khóa]</code> : Cào dữ liệu tìm kiếm thời gian thực\n"
        "🎙️ <code>/voice [Văn bản]</code> : Render file âm thanh MP3\n\n"
        "<i>Ví dụ: /trend xu hướng tiktok tháng này</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=get_bottom_menu())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    if text == "🛠 BẢNG ĐIỀU KHIỂN HỆ THỐNG":
        await cmd_start(update, context)
        return
    # Trò chuyện bình thường
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = call_gemini(GENERAL_PROMPT, text)
    await update.message.reply_text(reply)

# ─── KHỞI CHẠY BOT ──────────────────────────────────────────────────────
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