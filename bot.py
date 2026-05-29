"""
HoTroToanBot - Trạm Điều Khiển AI Đa Tác Vụ (Multi-Agent System)
Phiên bản V8.0 - TÍCH HỢP BỘ NÃO ĐIỀU PHỐI TỰ ĐỘNG (ROUTING INTENT ENGINE)
Gemini tự đọc hiểu chat thường và tự kích hoạt các module Voice / Quét Trend ngầm.
"""

import os
import logging
import asyncio
import edge_tts
import json
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

# BỘ NÃO PHÂN LOẠI Ý ĐỊNH: Đọc tin nhắn thường và quyết định xem cần gọi module con nào
ORCHESTRATOR_PROMPT = """
Bạn là Bộ Não Điều Phối Trung Tâm của hệ thống HoTroToanBot.
Nhiệm vụ của bạn là đọc tin nhắn thường của chủ nhân, phân tích ý định (Intent Tracking) và phân loại nó vào một trong các hành động kỹ thuật.

Bạn chỉ được phép trả về kết quả dưới định dạng JSON duy nhất, không kèm theo lời giải thích nào khác. Cấu trúc JSON bắt buộc:
{
  "action": "gọi_tên_hành_động",
  "data": "nội_dung_đã_được_trích_xuất_hoặc_lọc_sạch"
}

Các hành động bạn cần phân loại:
1. Nếu chủ nhân muốn tạo giọng nói, chuyển văn bản thành tiếng nói, bảo bot nói/đọc một đoạn văn nào đó:
   -> action: "voice"
   -> data: Trích xuất toàn bộ đoạn văn bản thuần túy cần đọc (Bỏ các từ thừa như "hãy nói", "đọc giùm", "tạo file nói").

2. Nếu chủ nhân muốn tìm kiếm tin tức, quét xu hướng thị trường, tìm trend mới trên mạng xã hội:
   -> action: "trend"
   -> data: Từ khóa cốt lõi cần mang đi tìm kiếm (Ví dụ: "cách kiếm tiền tiktok 2026").

3. Nếu chủ nhân muốn hỏi về lập trình, viết code, sửa lỗi phần mềm, tester, xây dựng app web:
   -> action: "code"
   -> data: Toàn bộ câu hỏi lập trình của chủ nhân.

4. Nếu chủ nhân hỏi về chiến lược kinh doanh, lên plan kiếm tiền MMO, kịch bản video, marketing, affiliate:
   -> action: "mmo"
   -> data: Nội dung câu hỏi MMO của chủ nhân.

5. Nếu chỉ là lời chào hỏi bình thường (ví dụ: hello, hi, bạn là ai) hoặc không thuộc các nhóm trên:
   -> action: "general"
   -> data: Câu trả lời ngắn gọn, lịch sự, hướng dẫn chủ nhân sử dụng hệ thống.
"""

# ─── HÀM LIÊN KẾT GIAO TIẾP VỚI LÕI AI GEMINI CORE ──────────────────────────────────
def call_gemini(prompt_system: str, user_text: str, is_json: bool = False) -> str:
    try:
        config_args = {"system_instruction": prompt_system}
        if is_json:
            config_args["response_mime_type"] = "application/json"
            
        response = gemini_client.models.generate_content(
            model="gemini-2.0-flash", 
            config=types.GenerateContentConfig(**config_args),
            contents=user_text,
        )
        return response.text
    except Exception as e:
        logger.error(f"Gemini Error: {e}")
        error_str = str(e).replace("<", "&lt;").replace(">", "&gt;")
        return f"❌ <b>Lỗi kết nối lõi Gemini API:</b>\n<code>{error_str}</code>"

# ─── HÀM THI HÀNH LỆNH QUÉT TREND NGẦM ──────────────────────────────────────────
def execute_trend_search(keyword: str) -> str:
    try:
        results = DDGS().text(keyword, max_results=5)
        if not results:
            return "❌ Hệ thống điều khiển đã quét mạng nhưng không tìm thấy dữ liệu mới nào liên quan."
        response_text = f"🌍 <b>KẾT QUẢ DỮ LIỆU QUÉT XU HƯỚNG: '{keyword}'</b>\n\n"
        for idx, res in enumerate(results):
            response_text += f"{idx+1}. <b>{res['title']}</b>\n- <i>{res['body']}</i>\n🔗 <a href='{res['href']}'>Link nguồn</a>\n\n"
        return response_text
    except Exception as e:
        return f"❌ Quá trình cào mạng dữ liệu tự động thất bại: {e}"

# ─── HÀM THI HÀNH LỆNH RENDER VOICE NGẦM ────────────────────────────────────────
async def execute_voice_render(text: str, user_id: int, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    output_file = f"voice_auto_{user_id}.mp3"
    status_msg = await context.bot.send_message(chat_id=chat_id, text="⏳ <i>Sếp tổng ra lệnh ngầm: Đang tự động render file âm thanh...</i>", parse_mode="HTML")
    try:
        communicate = edge_tts.Communicate(text, "vi-VN-NamMinhNeural")
        await communicate.save(output_file)
        with open(output_file, 'rb') as audio_file:
            await context.bot.send_audio(chat_id=chat_id, audio=audio_file, caption="✅ Tự động kích hoạt module Voice thành công!")
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ Luồng tự động tạo audio thất bại: {e}")
    finally:
        if os.path.exists(output_file): os.remove(output_file)

# ─── PHÂN HỆ 1: KỸ SƯ LẬP TRÌNH CHUYÊN SÂU (/code) ───────────────────────────────────
async def cmd_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    query = " ".join(context.args) if context.args else "Hãy hướng dẫn tôi cách viết code tối ưu bằng Python."
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = call_gemini(CODER_PROMPT, query)
    await send_long_text(update, f"👨‍💻 <b>CHUYÊN GIA LẬP TRÌNH VÀ TESTER:</b>\n\n{reply}")

# ─── PHÂN HỆ 2: CHIẾN LƯỢC GIA MMO & MARKETING (/mmo) ───────────────────────────────
async def cmd_mmo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    query = " ".join(context.args) if context.args else "Đề xuất cho tôi mô hình MMO zero-cost ổn định nhất."
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = call_gemini(MMO_PROMPT, query)
    await send_long_text(update, f"💡 <b>CHIẾN LƯỢC GIA HỆ THỐNG MMO:</b>\n\n{reply}")

# ─── PHÂN HỆ 3: CÀO TIN TỨC & PHÂN TÍCH XU HƯỚNG MẠNG (/trend) ─────────────────────────
async def cmd_trend(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    if not context.args:
        await update.message.reply_text("txt <b>Cú pháp:</b> <code>/trend [Từ khóa]</code>", parse_mode="HTML")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    keyword = " ".join(context.args)
    reply = execute_trend_search(keyword)
    await update.message.reply_text(reply, parse_mode="HTML", disable_web_page_preview=True)

# ─── PHÂN HỆ 4: GENERATE GIỌNG ĐỌC NAM MIỄN PHÍ (/voice) ────────────────────
async def cmd_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    if not context.args:
        await update.message.reply_text("🎙️ <b>Cú pháp:</b> <code>/voice [Văn bản]</code>", parse_mode="HTML")
        return
    text = " ".join(context.args)
    await execute_voice_render(text, update.effective_user.id, context, update.effective_chat.id)

# ─── THUẬT TOÁN BỔ TRỢ: TỰ ĐỘNG CHIA NHỎ TIN NHẮN TRÁNH TRÀN KHUNG TELEGRAM ─────────
async def send_long_text(update: Update, text: str):
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        try:
            await update.message.reply_text(chunk, parse_mode="HTML")
        except:
            await update.message.reply_text(chunk)

# ─── THIẾT LẬP PHÍM CHỨC NĂNG INLINE VIP & LỆNH /START ─────────────────────────────────
def get_bottom_menu() -> ReplyKeyboardMarkup:
    keyboard = [[KeyboardButton("🛸 MỞ TRẠM ĐIỀU KHIỂN AI CENTRAL")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

def get_inline_dashboard() -> InlineKeyboardMarkup:
    # Thiết kế bảng nút bấm Inline hiện đại như phần mềm quản trị chuyên nghiệp
    keyboard = [
        [
            InlineKeyboardButton("👨‍💻 Kỹ Sư Lập Trình", callback_data="btn_code"),
            InlineKeyboardButton("💰 Chiến Lược MMO", callback_data="btn_mmo")
        ],
        [
            InlineKeyboardButton("📈 Quét Xu Hướng Mạng", callback_data="btn_trend"),
            InlineKeyboardButton("🎙️ Tạo Giọng Đọc AI", callback_data="btn_voice")
        ],
        [
            InlineKeyboardButton("⚙️ Mở Kho Công Cụ MMO (Full Screen)", web_app=WebAppInfo(url=WEB_APP_URL))
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    text = (
        "🛸 <b>TRẠM ĐIỀU KHIỂN HỆ THỐNG AI ĐA TÁC VỤ VIP V8.0</b>\n\n"
        "Chào mừng sếp đã quay trở lại phòng làm việc trung tâm. Hệ thống điều phối ngầm đã được kích hoạt thành công.\n\n"
        "🧠 <b>Cơ chế Sếp Tổng hoạt động:</b> Sếp không cần gõ câu lệnh phức tạp nữa. Cứ chat trực tiếp tiếng Việt bình thường (Ví dụ: <i>'Tạo file nói xin chào hệ thống'</i> hoặc <i>'Kiểm tra lỗi đoạn code này...'</i>), bộ não Gemini sẽ tự phân tích và điều khiển các module con chạy ngầm lập tức!\n\n"
        "👇 Hoặc sếp có thể bấm trực tiếp vào bảng phân hệ chức năng dưới đây:"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=get_bottom_menu())
    await update.message.reply_text("🎛️ <b>BẢNG ĐIỀU KHIỂN PHÒNG BAN:</b>", parse_mode="HTML", reply_markup=get_inline_dashboard())

# ─── XỬ LÝ SỰ KIỆN KHI ẤN NÚT BẤM INLINE ──────────────────────────────────────────
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    if query.data == "btn_code":
        await query.message.reply_text("💻 <b>[Phân Hệ Lập Trình]</b>: Sếp hãy nhập theo cú pháp: <code>/code [Câu hỏi hoặc đoạn code cần sửa]</code>", parse_mode="HTML")
    elif query.data == "btn_mmo":
        await query.message.reply_text("💰 <b>[Phân Hệ Chiến Lược MMO]</b>: Sếp hãy nhập theo cú pháp: <code>/mmo [Ý tưởng kiếm tiền hoặc yêu cầu kịch bản]</code>", parse_mode="HTML")
    elif query.data == "btn_trend":
        await query.message.reply_text("📈 <b>[Phân Hệ Quét Trend]</b>: Sếp hãy nhập theo cú pháp: <code>/trend [Từ khóa cần quét mạng]</code>", parse_mode="HTML")
    elif query.data == "btn_voice":
        await query.message.reply_text("🎙️ <b>[Phân Hệ Render Giọng Nói]</b>: Sếp hãy nhập theo cú pháp: <code>/voice [Đoạn văn bản cần bot đọc thành tiếng]</code>", parse_mode="HTML")

# ─── BỘ NÃO ĐIỀU PHỐI (CHAT THƯỜNG TỰ ĐIỀU KHIỂN TẤT CẢ AI KHÁC) ───────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    text = update.message.text.strip()
    
    if text == "🛸 MỞ TRẠM ĐIỀU KHIỂN AI CENTRAL":
        await cmd_start(update, context)
        return
        
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    # Bước 1: Đẩy tin nhắn thường qua Gemini để phân tích ý định (Intent Routing) dưới dạng JSON
    intent_json_str = call_gemini(ORCHESTRATOR_PROMPT, text, is_json=True)
    
    try:
        intent_data = json.loads(intent_json_str)
        action = intent_data.get("action")
        extracted_data = intent_data.get("data", "")
        
        # Bước 2: Dựa vào hành động được Sếp Tổng phân loại, kích hoạt ngầm module tương ứng
        if action == "voice":
            await execute_voice_render(extracted_data, update.effective_user.id, context, update.effective_chat.id)
            return
            
        elif action == "trend":
            await update.message.reply_text(f"⏳ <i>Sếp tổng ra lệnh ngầm: Đang tự cào mạng quét dữ liệu cho từ khóa '{extracted_data}'...</i>", parse_mode="HTML")
            reply = execute_trend_search(extracted_data)
            await update.message.reply_text(reply, parse_mode="HTML", disable_web_page_preview=True)
            return
            
        elif action == "code":
            reply = call_gemini(CODER_PROMPT, extracted_data)
            await send_long_text(update, f"👨‍💻 <b>HỆ THỐNG TỰ ĐỘNG KÍCH HOẠT PHÒNG CODE:</b>\n\n{reply}")
            return
            
        elif action == "mmo":
            reply = call_gemini(MMO_PROMPT, extracted_data)
            await send_long_text(update, f"💡 <b>HỆ THỐNG TỰ ĐỘNG KÍCH HOẠT CHIẾN LƯỢC MMO:</b>\n\n{reply}")
            return
            
        else:
            # Lời chào hoặc trò chuyện chung
            await update.message.reply_text(extracted_data, reply_markup=get_inline_dashboard())
            
    except Exception as err:
        logger.error(f"Routing Error: {err}")
        # Nếu lỗi JSON, quay về chế độ chat thông thường bảo vệ luồng chạy
        reply = call_gemini("Bạn là trợ lý AI thân thiện.", text)
        await update.message.reply_text(reply)

# ─── KHỔI CHẠY KHUNG ĐIỀU HÀNH LUỒNG POLLING HỆ THỐNG ────────────────────────────────
def main() -> None:
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("code", cmd_code))
    app.add_handler(CommandHandler("mmo", cmd_mmo))
    app.add_handler(CommandHandler("trend", cmd_trend))
    app.add_handler(CommandHandler("voice", cmd_voice))
    
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🤖 Trạm Điều Khiển Multi-Agent V8.0 đang chạy...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()