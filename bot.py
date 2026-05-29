"""
HoTroToanBot - Trạm Điều Khiển AI Đa Tác Vụ (Multi-Agent System)
Phiên bản V8.1 - TÍCH HỢP CƠ CHẾ DỰ PHÒNG CHỐNG NGHẼN QUOTA 429 (FALLBACK ENGINE)
Tự động đổi mô hình nếu một trong hai model của Google bị khóa giới hạn.
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
   -> data: Từ khóa cốt lõi cần mang đi tìm kiếm.

3. Nếu chủ nhân muốn hỏi về lập trình, viết code, sửa lỗi phần mềm, tester, xây dựng app web:
   -> action: "code"
   -> data: Toàn bộ câu hỏi lập trình của chủ nhân.

4. Nếu chủ nhân hỏi về chiến lược kinh doanh, lên plan kiếm tiền MMO, kịch bản video, marketing, affiliate:
   -> action: "mmo"
   -> data: Nội dung câu hỏi MMO của chủ nhân.

5. Nếu chỉ là lời chào hỏi bình thường hoặc không thuộc các nhóm trên:
   -> action: "general"
   -> data: Câu trả lời ngắn gọn, lịch sự, hướng dẫn chủ nhân sử dụng hệ thống.
"""

GENERAL_PROMPT = "Bạn là Trợ lý AI hệ thống điều khiển. Hãy hướng dẫn người dùng sử dụng các lệnh /code, /mmo, /trend, /voice."

# ─── HÀM LIÊN KẾT GIAO TIẾP VỚI LÕI AI GEMINI (CƠ CHẾ DỰ PHÒNG CHỐNG NGHẼN VIP) ──────
def call_gemini(prompt_system: str, user_text: str, is_json: bool = False) -> str:
    config_args = {"system_instruction": prompt_system}
    if is_json:
        config_args["response_mime_type"] = "application/json"
        
    # Tuyến phòng thủ số 1: Sử dụng mô hình đời mới nhất 2.0
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.0-flash", 
            config=types.GenerateContentConfig(**config_args),
            contents=user_text,
        )
        return response.text
    except Exception as e_2_0:
        logger.warning(f"Model 2.0-flash kẹt hoặc nghẽn quota: {e_2_0}. Tự động chuyển sang tuyến dự phòng...")
        
        # Tuyến phòng thủ số 2 (Fallback): Tự kích hoạt model 1.5-flash cực kỳ ổn định
        try:
            response = gemini_client.models.generate_content(
                model="gemini-1.5-flash", 
                config=types.GenerateContentConfig(**config_args),
                contents=user_text,
            )
            return response.text
        except Exception as e_1_5:
            logger.error(f"Tuyến dự phòng 1.5-flash cũng thất bại: {e_1_5}")
            error_str = str(e_1_5).replace("<", "&lt;").replace(">", "&gt;")
            return f"❌ <b>Cả hai máy chủ AI dự phòng đều đang quá tải hoặc hết hạn mức (Quota 429).</b>\n\nSếp vui lòng đợi khoảng 20 giây rồi thử lại ạ!"

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

# ─── PHÂN HỆ KHỞI CHẠY CÁC CÂU LỆNH ĐỘC LẬP ──────────────────────────────────────────
async def cmd_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    query = " ".join(context.args) if context.args else "Hãy hướng dẫn tôi cách viết code tối ưu bằng Python."
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = call_gemini(CODER_PROMPT, query)
    await send_long_text(update, f"👨‍💻 <b>CHUYÊN GIA LẬP TRÌNH VÀ TESTER:</b>\n\n{reply}")

async def cmd_mmo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    query = " ".join(context.args) if context.args else "Đề xuất cho tôi mô hình MMO zero-cost ổn định nhất."
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = call_gemini(MMO_PROMPT, query)
    await send_long_text(update, f"💡 <b>CHIẾN LƯỢC GIA HỆ THỐNG MMO:</b>\n\n{reply}")

async def cmd_trend(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    if not context.args:
        await update.message.reply_text("📈 <b>Cú pháp:</b> <code>/trend [Từ khóa]</code>", parse_mode="HTML")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    keyword = " ".join(context.args)
    reply = execute_trend_search(keyword)
    await update.message.reply_text(reply, parse_mode="HTML", disable_web_page_preview=True)

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

# ─── THIẾT LẬP GIAO DIỆN PHÍM BẤM HỆ THỐNG ──────────────────────────────────────────
def get_bottom_menu() -> ReplyKeyboardMarkup:
    keyboard = [[KeyboardButton("🛸 MỞ TRẠM ĐIỀU KHIỂN AI CENTRAL")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

def get_inline_dashboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("👨‍💻 Kỹ Sư Lập Trình", callback_data="btn_code"),
            InlineKeyboardButton("💰 Chiến Lược MMO", callback_data="btn_mmo")
        ],
        [
            InlineKeyboardButton("📈 Quét Xu Hướng Mạng", callback_data="btn_trend"),
            InlineKeyboardButton("🎙️ Tạo Giọng Đọc AI", callback_data="btn_voice")
        ],
        [InlineKeyboardButton("⚙️ Mở Kho Công Cụ MMO (Full Screen)", web_app=WebAppInfo(url=WEB_APP_URL))]
    ]
    return InlineKeyboardMarkup(keyboard)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    text = (
        "🛸 <b>TRẠM ĐIỀU KHIỂN HỆ THỐNG AI ĐA TÁC VỤ VIP V8.1</b>\n\n"
        "Chào mừng sếp đã quay trở lại phòng làm việc trung tâm. Hệ thống bảo vệ kép (Fallback Engine) chống kẹt mạch API đã kích hoạt.\n\n"
        "🧠 <b>Cơ chế điều phối tự động:</b> Sếp có thể nhắn tin thường trực tiếp (Ví dụ: <i>'Tạo file nói xin chào hệ thống'</i> hoặc <i>'Tìm kiếm xu hướng làm video ngắn'</i>). Bot sẽ tự động phân giải cấu trúc chạy lập tức!\n\n"
        "👇 Bấm trực tiếp vào các phân hệ dưới đây để nhận hướng dẫn:"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=get_bottom_menu())
    await update.message.reply_text("🎛️ <b>BẢNG ĐIỀU KHIỂN PHÒNG BAN:</b>", parse_mode="HTML", reply_markup=get_inline_dashboard())

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    if query.data == "btn_code":
        await query.message.reply_text("💻 <b>[Phân Hệ Lập Trình]</b>: Nhập theo cú pháp: <code>/code [Câu hỏi lập trình]</code>", parse_mode="HTML")
    elif query.data == "btn_mmo":
        await query.message.reply_text("💰 <b>[Phân Hệ Chiến Lược MMO]</b>: Nhập theo cú pháp: <code>/mmo [Câu hỏi mmo / Kịch bản]</code>", parse_mode="HTML")
    elif query.data == "btn_trend":
        await query.message.reply_text("📈 <b>[Phân Hệ Quét Trend]</b>: Nhập theo cú pháp: <code>/trend [Từ khóa]</code>", parse_mode="HTML")
    elif query.data == "btn_voice":
        await query.message.reply_text("🎙️ <b>[Phân Hệ Giọng Nói]</b>: Nhập theo cú pháp: <code>/voice [Văn bản]</code>", parse_mode="HTML")

# ─── BỘ NÀO ĐIỀU PHỐI MULTI-AGENT PHÒNG THỦ KÉP ─────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    text = update.message.text.strip()
    
    if text == "🛸 MỞ TRẠM ĐIỀU KHIỂN AI CENTRAL":
        await cmd_start(update, context)
        return
        
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    # Phân giải ý định qua hàm call_gemini có bảo vệ chống lỗi 429
    intent_json_str = call_gemini(ORCHESTRATOR_PROMPT, text, is_json=True)
    
    # Nếu nghẽn mạch hoàn toàn cả 2 model, trả về thẳng thông báo lỗi thân thiện cho sếp
    if "Máy chủ AI dự phòng đều đang quá tải" in intent_json_str or "❌" in intent_json_str:
        await update.message.reply_text(intent_json_str, parse_mode="HTML")
        return
        
    try:
        intent_data = json.loads(intent_json_str)
        action = intent_data.get("action")
        extracted_data = intent_data.get("data", "")
        
        if action == "voice":
            await execute_voice_render(extracted_data, update.effective_user.id, context, update.effective_chat.id)
            return
        elif action == "trend":
            await update.message.reply_text(f"⏳ <i>Sếp tổng ra lệnh: Đang cào mạng quét dữ liệu cho từ khóa '{extracted_data}'...</i>", parse_mode="HTML")
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
            await update.message.reply_text(extracted_data, reply_markup=get_inline_dashboard())
            
    except Exception as err:
        logger.error(f"Routing Error: {err}")
        reply = call_gemini(GENERAL_PROMPT, text)
        await update.message.reply_text(reply)

def main() -> None:
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("code", cmd_code))
    app.add_handler(CommandHandler("mmo", cmd_mmo))
    app.add_handler(CommandHandler("trend", cmd_trend))
    app.add_handler(CommandHandler("voice", cmd_voice))
    
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🤖 Trạm Điều Khiển Multi-Agent V8.1 đang chạy...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()