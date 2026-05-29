"""
HoTroToanBot - Trạm Điều Khiển AI Đa Tác Vụ (Multi-Agent System)
Phiên bản V7 - Nâng cấp Gemini 1.5 Pro & Chế Độ Kín (Private Mode)
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
ADMIN_ID = os.environ.get("ADMIN_ID") # Lấy ID của Admin từ Railway

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    logger.error("❌ THIẾU BIẾN MÔI TRƯỜNG!")

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# ─── CHẶN NGƯỜI LẠ (PRIVATE MODE) ───────────────────────────────────────
async def restrict_access(update: Update) -> bool:
    """Hàm kiểm tra quyền Admin. Trả về True nếu bị chặn, False nếu được phép."""
    user_id = update.effective_user.id
    if not ADMIN_ID:
        # Nếu chưa cấu hình ADMIN_ID trên Railway, bot sẽ báo ID để bồ copy
        await update.message.reply_text(
            f"🔒 <b>HỆ THỐNG ĐANG BỊ KHÓA</b>\n\n"
            f"Bot này được thiết lập chế độ Private. Để cấp quyền cho chính mình, bồ hãy copy dãy số ID dưới đây:\n\n"
            f"<code>{user_id}</code>\n\n"
            f"<i>👉 Lên Railway -> tab Variables -> Thêm biến mới tên là <b>ADMIN_ID</b> và dán dãy số này vào -> Bấm Redeploy.</i>",
            parse_mode="HTML"
        )
        return True
    elif str(user_id) != str(ADMIN_ID):
        # Nếu người lạ chat vào, bot đuổi thẳng cổ
        await update.message.reply_text("⛔ <b>TRUY CẬP TỪ CHỐI:</b> Bạn không phải là Chủ Nhân của hệ thống này.")
        return True
    return False

# ─── BỘ PROMPT ĐIỀU KHIỂN CÁC "TRƯỞNG PHÒNG AI" ─────────────────────────
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

GENERAL_PROMPT = "Bạn là Trợ lý AI hệ thống điều khiển. Hãy hướng dẫn Admin sử dụng các lệnh /code, /mmo, /trend, /voice."

# ─── HÀM GIAO TIẾP VỚI LÕI AI GEMINI PRO ────────────────────────────────
def call_gemini(prompt_system: str, user_text: str) -> str:
    try:
        # Nâng cấp lên gemini-1.5-pro: Chuyên xử lý dữ liệu khủng, code mượt
        response = gemini_client.models.generate_content(
            model="gemini-1.5-pro", 
            config=types.GenerateContentConfig(system_instruction=prompt_system),
            contents=user_text,
        )
        return response.text
    except Exception as e:
        logger.error(f"Gemini Error: {e}")
        # In thẳng lỗi kỹ thuật ra Telegram để dễ dàng bắt bệnh
        return f"❌ <b>Lỗi kết nối Gemini API:</b>\n<code>{str(e)}</code>"

# ─── MODULE 1: CHUYÊN GIA LẬP TRÌNH (/code) ─────────────────────────────
async def cmd_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return # Kiểm tra Admin
    if not context.args:
        await update.message.reply_text("💻 <b>Nhập lệnh:</b> <code>/code [Câu hỏi lập trình]</code>", parse_mode="HTML")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    user_query = " ".join(context.args)
    reply = call_gemini(CODER_PROMPT, user_query)
    await send_long_text(update, f"👨‍💻 <b>CHUYÊN GIA LẬP TRÌNH:</b>\n\n{reply}")

# ─── MODULE 2: CHUYÊN GIA MMO (/mmo) ────────────────────────────────────
async def cmd_mmo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return # Kiểm tra Admin
    if not context.args:
        await update.message.reply_text("💰 <b>Nhập lệnh:</b> <code>/mmo [Câu hỏi kiếm tiền/Kịch bản]</code>", parse_mode="HTML")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    user_query = " ".join(context.args)
    reply = call_gemini(MMO_PROMPT, user_query)
    await send_long_text(update, f"💡 <b>CHIẾN LƯỢC GIA MMO:</b>\n\n{reply}")

# ─── MODULE 3: TÌM KIẾM TREND THỜI GIAN THỰC (/trend) ───────────────────
async def cmd_trend(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return # Kiểm tra Admin
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
    if await restrict_access(update): return # Kiểm tra Admin
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
            await update.message.reply_text(chunk) 

# ─── GIAO DIỆN MENU & LỆNH /START ───────────────────────────────────────
def get_bottom_menu() -> ReplyKeyboardMarkup:
    keyboard = [[KeyboardButton("🛠 BẢNG ĐIỀU KHIỂN HỆ THỐNG")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return # Kiểm tra Admin
    text = (
        "🛸 <b>TRẠM ĐIỀU KHIỂN ĐA TÁC VỤ AI KÍCH HOẠT</b>\n\n"
        "Hệ thống đã phân luồng các chuyên gia. Vui lòng sử dụng các lệnh sau để ra việc:\n\n"
        "👨‍💻 <code>/code [Câu hỏi]</code> : Gọi kỹ sư lập trình (Web/App/Auto)\n"
        "💰 <code>/mmo [Câu hỏi]</code> : Gọi chuyên gia kiếm tiền, kịch bản\n"
        "📈 <code>/trend [Từ khóa]</code> : Cào dữ liệu tìm kiếm thời gian thực\n"
        "🎙️ <code>/voice [Văn bản]</code> : Render file âm thanh MP3\n\n"
        "<i>Bảo mật: Hệ thống đang chạy ở Private Mode (Chỉ Chủ Nhân được quyền điều khiển).</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=get_bottom_menu())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return # Kiểm tra Admin
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