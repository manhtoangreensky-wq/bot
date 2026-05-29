"""
╔══════════════════════════════════════════════════════════════╗
║   HoTroToanBot - TRẠM ĐIỀU KHIỂN AI ĐA TÁC VỤ VIP V10.1     ║
║   Enterprise Multi-Agent Orchestration System                ║
║   Bộ não chính: Gemini (Điều phối + Dự phòng mọi luồng)      ║
║   Các AI con: Claude 3.5 Sonnet (Code), Edge TTS, DuckDuckGo ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import logging
import asyncio
import edge_tts
import json
import time
import httpx
from pydantic import BaseModel, Field
from duckduckgo_search import DDGS
from google import genai
from google.genai import types
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ─── 1. CẤU HÌNH HỆ THỐNG CORE & LOGGING ───────────────────────────────────────
logging.basicConfig(format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", level=logging.INFO)
logger = logging.getLogger("HoTroToanBot")

WEB_APP_URL = "https://hoangthai223388-maker.github.io/xx88/redirect.html"
TELEGRAM_TOKEN = os.environ.get("BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")
ADMIN_ID = os.environ.get("ADMIN_ID")

# Khởi tạo Client Gemini bảo vệ cấu trúc
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# Bộ nhớ lưu trữ dữ liệu ngầm cho hệ thống
user_memory = {}       # Lưu lịch sử 10 lượt chat gần nhất
user_rate_limit = {}   # Kiểm soát tần suất tránh spam
claude_memory = {}     # Lịch sử riêng cho luồng code

# ─── 2. CƠ CHẾ BẢO MẬT TUYỆT ĐỐI: KHÓA CHỦ NHÂN (PRIVATE MODE) ───────────────────
async def restrict_access(update: Update) -> bool:
    user_id = update.effective_user.id
    if not ADMIN_ID:
        await update.message.reply_text(
            f"🔒 <b>TRẠM ĐIỀU KHIỂN ĐANG KHÓA VẬT LÝ</b>\n\n"
            f"Sếp hãy copy mã ID này: <code>{user_id}</code>\n"
            f"<i>👉 Vào Railway -> Variables -> Thêm biến <b>ADMIN_ID</b> và dán số này vào -> Restart.</i>",
            parse_mode="HTML"
        )
        return True
    if str(user_id) != str(ADMIN_ID):
        await update.message.reply_text("⛔ <b>TRUY CẬP TỪ CHỐI:</b> Bạn không phải chủ nhân của hệ thống này.")
        return True
    
    # Rate Limiter chống spam (5 lệnh / phút)
    current_time = time.time()
    user_timestamps = user_rate_limit.get(user_id, [])
    user_timestamps = [t for t in user_timestamps if current_time - t < 60]
    user_rate_limit[user_id] = user_timestamps
    
    if len(user_timestamps) >= 5:
        await update.message.reply_text("⚠️ <b>CẢNH BÁO:</b> Sếp ra lệnh quá nhanh, vui lòng đợi AI xử lý luồng cũ.")
        return True
    
    user_rate_limit[user_id].append(current_time)
    return False

# ─── 3. ĐỊNH CHUẨN ĐẦU RA SẾP TỔNG (PYDANTIC ROUTER SCHEMA) ──────────────────
class AgentRouter(BaseModel):
    action: str = Field(description="Phân loại: 'voice', 'trend', 'code', 'mmo', 'general'")
    data: str = Field(description="Từ khóa hoặc nội dung yêu cầu sạch đã bóc tách")

# ─── 4. CÁC PHÒNG BAN AI THỰC THI (MULTI-AGENT ENGINES) ────────────────────────

class AgentGemini:
    """Module Sếp Tổng & Chiến lược gia & Dự phòng cho mọi hệ thống"""
    @staticmethod
    def chat(prompt_system: str, user_text: str, user_id: int, is_json: bool = False) -> str:
        if not gemini_client: return "❌ Chưa cấu hình GEMINI_API_KEY."
        
        if user_id not in user_memory: user_memory[user_id] = []
        user_memory[user_id].append(types.Content(role="user", parts=[types.Part(text=user_text)]))
        if len(user_memory[user_id]) > 10: user_memory[user_id] = user_memory[user_id][-10:]
        
        config_args = {"system_instruction": prompt_system}
        if is_json:
            config_args["response_mime_type"] = "application/json"
            config_args["response_schema"] = AgentRouter

        try:
            response = gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                config=types.GenerateContentConfig(**config_args),
                contents=user_memory[user_id] if not is_json else user_text
            )
            if not is_json: user_memory[user_id].append(types.Content(role="model", parts=[types.Part(text=response.text)]))
            return response.text
        except Exception:
            try:
                response = gemini_client.models.generate_content(
                    model="gemini-1.5-flash",
                    config=types.GenerateContentConfig(**config_args),
                    contents=user_memory[user_id] if not is_json else user_text
                )
                return response.text
            except Exception as e:
                return f"❌ <b>Lỗi đồng bộ lõi API kép (Quota 429):</b>\n<code>{str(e)[:100]}...</code>"

CLAUDE_SYSTEM_PROMPT = """Bạn là Đầu Não Lập Trình Cấp Cao. 
Luôn trả lời tiếng Việt, code sạch có comment, chạy được ngay. Không nói chung chung."""

class AgentClaude:
    """Đầu Não Lập Trình (Tự động chuyển cho Gemini nếu chưa có Key Claude)"""
    @staticmethod
    async def chat(prompt: str, user_id: int) -> str:
        # Nếu chưa nạp Key Claude -> Nhờ Gemini Code thay luôn!
        if not CLAUDE_API_KEY:
            fallback_msg = "⚠️ <i>(Chưa nạp CLAUDE_API_KEY. Hệ thống tự động chuyển task cho Gemini xử lý bù đắp...)</i>\n\n"
            gemini_code = AgentGemini.chat(CLAUDE_SYSTEM_PROMPT, prompt, user_id)
            return fallback_msg + gemini_code

        if user_id not in claude_memory: claude_memory[user_id] = []
        claude_memory[user_id].append({"role": "user", "content": prompt})
        if len(claude_memory[user_id]) > 10: claude_memory[user_id] = claude_memory[user_id][-10:]

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": CLAUDE_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                    json={"model": "claude-3-5-sonnet-latest", "max_tokens": 4096, "system": CLAUDE_SYSTEM_PROMPT, "messages": claude_memory[user_id]},
                    timeout=90.0
                )
                if response.status_code == 200:
                    reply = response.json()["content"][0]["text"]
                    claude_memory[user_id].append({"role": "assistant", "content": reply})
                    return reply
                else: return f"❌ Lỗi Claude API ({response.status_code}): {response.text}"
        except Exception as e:
            return f"❌ Lỗi kết nối Claude: {e}"

class AgentVoice:
    """Module giọng đọc AI chất lượng cao"""
    @staticmethod
    async def render(text: str, user_id: int, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        output_file = f"voice_pro_{user_id}.mp3"
        status_msg = await context.bot.send_message(chat_id=chat_id, text="⏳ <i>[Voice Agent] Đang xử lý âm thanh kỹ thuật...</i>", parse_mode="HTML")
        try:
            communicate = edge_tts.Communicate(text, "vi-VN-NamMinhNeural")
            await communicate.save(output_file)
            with open(output_file, 'rb') as audio_file: await context.bot.send_audio(chat_id=chat_id, audio=audio_file, caption="✅ Render hoàn tất!")
            await status_msg.delete()
        except Exception as e: await status_msg.edit_text(f"❌ Lỗi Voice: {e}")
        finally:
            if os.path.exists(output_file): os.remove(output_file)

class AgentData:
    """Module cào dữ liệu mạng thời gian thực"""
    @staticmethod
    def search_trend(keyword: str) -> str:
        try:
            results = DDGS().text(keyword, max_results=5)
            if not results: return "❌ Không tìm thấy thông tin mới."
            resp = f"🌍 <b>KẾT QUẢ QUÉT TREND: '{keyword}'</b>\n\n"
            for idx, res in enumerate(results): resp += f"{idx+1}. <b>{res['title']}</b>\n- <i>{res['body']}</i>\n🔗 <a href='{res['href']}'>Xem</a>\n\n"
            return resp
        except Exception as e: return f"❌ Lỗi quét mạng: {e}"

# ─── 5. BỘ NÃO ĐIỀU PHỐI TRUNG TÂM (ORCHESTRATOR ROUTING ENGINE) ─────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    if text == "🛸 MỞ TRẠM ĐIỀU KHIỂN AI CENTRAL":
        await cmd_start(update, context)
        return
        
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    routing_instruction = "Bạn là Tổng Giám Đốc AI. Phân loại lệnh của chủ nhân vào đúng hành động: voice, trend, code, mmo, general."
    router_json = AgentGemini.chat(routing_instruction, text, user_id, is_json=True)
    
    if "Lỗi đồng bộ" in router_json or "❌" in router_json:
        await update.message.reply_text(router_json, parse_mode="HTML")
        return
        
    try:
        route_plan = json.loads(router_json)
        action, data = route_plan.get("action"), route_plan.get("data", "")
        
        if action == "voice": await AgentVoice.render(data, user_id, context, update.effective_chat.id)
        elif action == "trend":
            await update.message.reply_text(f"⏳ <i>[Data Agent] Đang cào dữ liệu: '{data}'...</i>", parse_mode="HTML")
            await update.message.reply_text(AgentData.search_trend(data), parse_mode="HTML", disable_web_page_preview=True)
        elif action == "code":
            await update.message.reply_text("⏳ <i>[Phòng Code] Đang biên dịch thuật toán chuyên sâu...</i>", parse_mode="HTML")
            code_reply = await AgentClaude.chat(data, user_id)
            await send_long_text(update, f"👨‍💻 <b>KẾT QUẢ PHÂN TÍCH LẬP TRÌNH:</b>\n\n{code_reply}")
        elif action == "mmo":
            mmo_prompt = "Bạn là Chuyên gia MMO & Automation. Đưa ra action plan cụ thể."
            await send_long_text(update, f"💡 <b>CHIẾN LƯỢC HỆ THỐNG ĐỀ XUẤT:</b>\n\n{AgentGemini.chat(mmo_prompt, data, user_id)}")
        else:
            await update.message.reply_text(AgentGemini.chat("Bạn là Trợ lý trung tâm HoTroToanBot.", text, user_id), reply_markup=get_inline_dashboard())
            
    except Exception as err:
        logger.error(f"Routing Error: {err}")
        await update.message.reply_text("Dạ, luồng dữ liệu trung tâm đang đồng bộ, sếp vui lòng thử lại sau vài giây ạ!")

# ─── 6. LỆNH ĐIỀU KHIỂN HỆ THỐNG ───────────────────────────────────────────────
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    status_text = (
        "🎛️ <b>TRẠNG THÁI CÁC PHÂN HỆ AI ENGINE:</b>\n\n"
        f"🤖 <b>Sếp Tổng Gemini:</b> ✅ Hoạt động (Có lưu Memory)\n"
        f"👨‍💻 <b>Claude Sonnet:</b> {'✅ Đã nạp Key' if CLAUDE_API_KEY else '⚠️ Chưa Key (Gemini đang code thay)'}\n"
        f"🎙️ <b>Edge-TTS Audio:</b> ✅ Trực tuyến (Nam Minh)\n"
        f"📈 <b>DuckDuckGo Data:</b> ✅ Sẵn sàng\n"
        f"🔒 <b>Khóa Chủ Nhân:</b> 🔐 ĐÃ BẬT TUYỆT ĐỐI\n"
    )
    await update.message.reply_text(status_text, parse_mode="HTML")

async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    uid = update.effective_user.id
    if uid in user_memory: user_memory[uid] = []
    if uid in claude_memory: claude_memory[uid] = []
    await update.message.reply_text("🧹 <b>Đã xóa sạch bộ nhớ ngữ cảnh của tất cả các AI!</b>")

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    text = (
        "👑 <b>HỆ THỐNG ENTERPRISE MULTI-AGENT VIP V10.1</b>\n\n"
        "Chào mừng sếp. Khóa bảo mật vật lý đã nhận diện thành công!\n"
        "🧠 <b>Sức mạnh điều phối:</b> Chat tiếng Việt tự nhiên, hệ thống tự kích hoạt module tương ứng (Quét trend, tạo giọng đọc, code tự động...)\n\n"
        "🛠️ Lệnh phụ trợ: <code>/status</code> (Xem trạng thái) | <code>/clear</code> (Xóa bộ nhớ)"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=get_bottom_menu())
    await update.message.reply_text("🎛️ <b>BẢNG ĐIỀU KHIỂN NHANH:</b>", parse_mode="HTML", reply_markup=get_inline_dashboard())

async def send_long_text(update: Update, text: str):
    for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
        try: await update.message.reply_text(chunk, parse_mode="HTML")
        except: await update.message.reply_text(chunk)

# ─── GIAO DIỆN NÚT BẤM TƯƠNG TÁC CHUYÊN NGHIỆP ──────────────────────────────────
def get_bottom_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton("🛸 MỞ TRẠM ĐIỀU KHIỂN AI CENTRAL")]], resize_keyboard=True, is_persistent=True)

def get_inline_dashboard() -> InlineKeyboardMarkup:
    # Đã gỡ bỏ hoàn toàn link WebApp cũ, chuyển thành callback_data có chức năng
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👨‍💻 Kỹ sư Code", callback_data="btn_code"), InlineKeyboardButton("🎙️ Tạo Audio", callback_data="btn_voice")],
        [InlineKeyboardButton("📈 Quét Trend", callback_data="btn_trend"), InlineKeyboardButton("🌐 Mở Cấu Hình", callback_data="btn_config")]
    ])

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() # Tắt vòng loading khi bấm nút
    
    # Bắt sự kiện khi sếp bấm vào từng nút và trả về câu hướng dẫn
    if query.data == "btn_code":
        await query.message.reply_text("💻 <b>[Phân Hệ Lập Trình]</b>: Sếp hãy chat trực tiếp yêu cầu (VD: <i>'Viết mã Python...'</i>) hoặc dùng lệnh <code>/code [Câu hỏi]</code>", parse_mode="HTML")
    elif query.data == "btn_voice":
        await query.message.reply_text("🎙️ <b>[Phân Hệ Giọng Nói]</b>: Sếp hãy chat yêu cầu (VD: <i>'Tạo file nói...'</i>) hoặc dùng lệnh <code>/voice [Văn bản]</code>", parse_mode="HTML")
    elif query.data == "btn_trend":
        await query.message.reply_text("📈 <b>[Phân Hệ Quét Trend]</b>: Sếp hãy chat yêu cầu (VD: <i>'Tìm trend...'</i>) hoặc dùng lệnh <code>/trend [Từ khóa]</code>", parse_mode="HTML")
    elif query.data == "btn_config":
        await query.message.reply_text("🚧 <b>Hệ thống Website quản trị đang được xây dựng. Chức năng sẽ sớm ra mắt!</b>", parse_mode="HTML")

# ─── KHỞI CHẠY KHUNG ĐIỀU HÀNH LUỒNG POLLING ─────────────────────────────────────
def main() -> None:
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("clear", cmd_clear))
    
    # Bắt sự kiện bấm nút Inline
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # Bắt sự kiện chat thường
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Enterprise Architecture VIP V10.2 Online...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()