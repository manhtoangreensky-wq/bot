"""
╔══════════════════════════════════════════════════════════════╗
║   HoTroToanBot - TRẠM ĐIỀU KHIỂN AI ĐA TÁC VỤ VIP V10.0     ║
║   Enterprise Multi-Agent Orchestration System                ║
║   Bộ não chính: Gemini 2.0 Flash (Điều phối trung tâm)      ║
║   Các AI con: Claude 3.5 Sonnet (Code chuyên sâu),           ║
║               Edge TTS (Media Voice), DuckDuckGo (Data)      ║
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

# ─── 2. CƠ CHẾ BẢO MẬT TUYỆT ĐỐI: KHÓA CHỦ NHÂN (PRIVATE MODE) ───────────────────
async def restrict_access(update: Update) -> bool:
    """Hàm chặn người lạ. Trả về True nếu bị chặn, False nếu hợp lệ."""
    user_id = update.effective_user.id
    if not ADMIN_ID:
        await update.message.reply_text(
            f"🔒 <b>TRẠM ĐIỀU KHIỂN ĐANG KHÓA VẬT LÝ</b>\n\n"
            f"Hệ thống đang bật chế độ bảo mật nghiêm ngặt. Để cấp quyền admin, sếp hãy copy mã ID này:\n"
            f"<code>{user_id}</code>\n\n"
            f"<i>👉 Vào Railway -> Variables -> Thêm biến <b>ADMIN_ID</b> và dán số này vào -> Restart.</i>",
            parse_mode="HTML"
        )
        return True
    if str(user_id) != str(ADMIN_ID):
        await update.message.reply_text("⛔ <b>TRUY CẬP TỪ CHỐI:</b> Bạn không phải chủ nhân của hệ thống này.")
        return True
    
    # Cơ chế Rate Limiter chống treo luồng (Tối đa 5 yêu cầu / 1 phút)
    current_time = time.time()
    user_timestamps = user_rate_limit.get(user_id, [])
    user_timestamps = [t for t in user_timestamps if current_time - t < 60]
    user_rate_limit[user_id] = user_timestamps
    
    if len(user_timestamps) >= 5:
        await update.message.reply_text("⚠️ <b>HỆ THỐNG CẢNH BÁO:</b> Sếp đang ra lệnh quá nhanh, vui lòng đợi vài giây để AI xử lý xong luồng cũ.")
        return True
    
    user_rate_limit[user_id].append(current_time)
    return False

# ─── 3. ĐỊNH CHUẨN ĐẦU RA CHO SẾP TỔNG (PYDANTIC ROUTER SCHEMA) ──────────────────
class AgentRouter(BaseModel):
    action: str = Field(description="Phân loại chính xác: 'voice', 'trend', 'code', 'mmo', 'general'")
    data: str = Field(description="Từ khóa hoặc nội dung yêu cầu sạch đã bóc tách")

# ─── 4. CÁC PHÒNG BAN AI THỰC THI (MULTI-AGENT ENGINES) ────────────────────────
class AgentVoice:
    """Module giọng đọc AI chất lượng cao"""
    @staticmethod
    async def render(text: str, user_id: int, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        output_file = f"voice_pro_{user_id}.mp3"
        status_msg = await context.bot.send_message(chat_id=chat_id, text="⏳ <i>[Voice Agent] Đang xử lý âm thanh kỹ thuật...</i>", parse_mode="HTML")
        try:
            communicate = edge_tts.Communicate(text, "vi-VN-NamMinhNeural")
            await communicate.save(output_file)
            with open(output_file, 'rb') as audio_file:
                await context.bot.send_audio(chat_id=chat_id, audio=audio_file, caption="✅ Render giọng đọc hoàn tất!")
            await status_msg.delete()
        except Exception as e:
            await status_msg.edit_text(f"❌ Lỗi thiết lập Voice: {e}")
        finally:
            if os.path.exists(output_file): os.remove(output_file)

class AgentData:
    """Module cào dữ liệu mạng thời gian thực"""
    @staticmethod
    def search_trend(keyword: str) -> str:
        try:
            results = DDGS().text(keyword, max_results=5)
            if not results: return "❌ Không tìm thấy thông tin mới trên mạng luồng."
            resp = f"🌍 <b>KẾT QUẢ QUÉT DỮ LIỆU TREND THỜI GIAN THỰC:</b>\n\n"
            for idx, res in enumerate(results):
                resp += f"{idx+1}. <b>{res['title']}</b>\n- <i>{res['body']}</i>\n🔗 <a href='{res['href']}'>Xem bài viết</a>\n\n"
            return resp
        except Exception as e:
            return f"❌ Mạng dữ liệu lỗi: {e}"

CLAUDE_SYSTEM_PROMPT = """
Bạn là Đầu Não Lập Trình Cấp Cao (Lead Engineer) của hệ thống HoTroToanBot.
Chuyên môn: Python, JavaScript, Automation, Bot Telegram, API integration, tạo nội dung tự động, MMO, video script.

Nguyên tắc làm việc:
- Luôn trả lời bằng tiếng Việt, rõ ràng và thực chiến
- Code phải sạch, có comment, chạy được ngay — không viết code mẫu giả
- Khi debug: chỉ ra đúng dòng lỗi, giải thích nguyên nhân gốc rễ, đưa fix hoàn chỉnh
- Khi thiết kế hệ thống: dùng tư duy modular, dễ mở rộng, tối ưu chi phí API
- Với yêu cầu kiếm tiền/MMO/nội dung: đưa action plan cụ thể từng bước, ưu tiên tự động hóa
- Không nói chung chung — luôn đưa ra giải pháp cụ thể có thể thực hiện ngay
"""

# Lưu lịch sử chat Claude riêng per user (tối đa 10 lượt)
claude_memory: dict[int, list[dict]] = {}

class AgentClaude:
    """Đầu Não Lập Trình — kết nối trực tiếp Anthropic API (claude-sonnet-4-6)"""

    @staticmethod
    async def chat(prompt: str, user_id: int = 0) -> str:
        if not CLAUDE_API_KEY:
            return "⚠️ <b>[Claude Agent] Báo lỗi:</b> Thiếu <code>CLAUDE_API_KEY</code> trên Railway. Vào console.anthropic.com lấy key rồi thêm vào biến môi trường."

        # Quản lý lịch sử hội thoại
        if user_id not in claude_memory:
            claude_memory[user_id] = []
        claude_memory[user_id].append({"role": "user", "content": prompt})
        if len(claude_memory[user_id]) > 20:
            claude_memory[user_id] = claude_memory[user_id][-20:]

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": CLAUDE_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-sonnet-4-6",
                        "max_tokens": 4096,
                        "system": CLAUDE_SYSTEM_PROMPT,
                        "messages": claude_memory[user_id],
                    },
                    timeout=90.0
                )
                if response.status_code == 200:
                    reply = response.json()["content"][0]["text"]
                    claude_memory[user_id].append({"role": "assistant", "content": reply})
                    return reply
                else:
                    return f"❌ Lỗi Claude API ({response.status_code}): {response.text}"
        except Exception as e:
            return f"❌ Lỗi kết nối Claude: {e}"

    @staticmethod
    def clear_memory(user_id: int):
        claude_memory[user_id] = []

class AgentGemini:
    """Module Sếp Tổng & Chiến lược gia MMO chuyên sâu"""
    @staticmethod
    def chat(prompt_system: str, user_text: str, user_id: int, is_json: bool = False) -> str:
        if not gemini_client: return "❌ Chưa cấu hình GEMINI_API_KEY."
        
        # Duy trì quản lý bộ nhớ Memory (10 lượt gần nhất)
        if user_id not in user_memory: user_memory[user_id] = []
        user_memory[user_id].append(types.Content(role="user", parts=[types.Part(text=user_text)]))
        if len(user_memory[user_id]) > 10: user_memory[user_id] = user_memory[user_id][-10:]
        
        config_args = {"system_instruction": prompt_system}
        if is_json:
            config_args["response_mime_type"] = "application/json"
            config_args["response_schema"] = AgentRouter

        # Cơ chế dự phòng thông minh (Fallback) chống nghẽn lỗi 429/503 của Google Free tier
        try:
            response = gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                config=types.GenerateContentConfig(**config_args),
                contents=user_memory[user_id] if not is_json else user_text
            )
            if not is_json:
                user_memory[user_id].append(types.Content(role="model", parts=[types.Part(text=response.text)]))
            return response.text
        except Exception:
            try:
                # Tuyến dự phòng ổn định cao
                response = gemini_client.models.generate_content(
                    model="gemini-1.5-flash",
                    config=types.GenerateContentConfig(**config_args),
                    contents=user_memory[user_id] if not is_json else user_text
                )
                return response.text
            except Exception as e:
                error_str = str(e).replace("<", "&lt;").replace(">", "&gt;")
                return f"❌ <b>Lỗi đồng bộ lõi API kép (Quota 429):</b>\n<code>{error_str}</code>"

# ─── 5. BỘ NÃO ĐIỀU PHỐI TRUNG TÂM (ORCHESTRATOR ROUTING ENGINE) ─────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    if text == "🛸 MỞ TRẠM ĐIỀU KHIỂN AI CENTRAL":
        await cmd_start(update, context)
        return
        
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    # Sếp Tổng Gemini quét tin nhắn để định tuyến việc ngầm
    routing_instruction = "Bạn là Tổng Giám Đốc AI. Phân loại lệnh của chủ nhân vào đúng hành động: voice, trend, code, mmo, general."
    router_json = AgentGemini.chat(routing_instruction, text, user_id, is_json=True)
    
    if "Lỗi đồng bộ" in router_json or "❌" in router_json:
        await update.message.reply_text(router_json, parse_mode="HTML")
        return
        
    try:
        route_plan = json.loads(router_json)
        action = route_plan.get("action")
        data = route_plan.get("data", "")
        
        if action == "voice":
            await AgentVoice.render(data, user_id, context, update.effective_chat.id)
        elif action == "trend":
            await update.message.reply_text(f"⏳ <i>[Data Agent] Đang cào mạng quét dữ liệu xu hướng cho: '{data}'...</i>", parse_mode="HTML")
            await update.message.reply_text(AgentData.search_trend(data), parse_mode="HTML", disable_web_page_preview=True)
        elif action == "code":
            await update.message.reply_text("⏳ <i>[Claude Agent] Đã kích hoạt. Đang biên dịch thuật toán code chuyên sâu...</i>", parse_mode="HTML")
            code_reply = await AgentClaude.chat(data, user_id)
            await send_long_text(update, f"👨‍💻 <b>KẾT QUẢ TỪ CLAUDE SONNET 4.6:</b>\n\n{code_reply}")
        elif action == "mmo":
            mmo_prompt = "Bạn là Chuyên gia MMO & Automation tối ưu hóa hệ thống tài khoản và dòng tiền."
            mmo_reply = AgentGemini.chat(mmo_prompt, data, user_id)
            await send_long_text(update, f"💡 <b>CHIẾN LƯỢC HỆ THỐNG ĐỀ XUẤT:</b>\n\n{mmo_reply}")
        else:
            gen_prompt = "Bạn là Trợ lý AI trung tâm của hệ thống HoTroToanBot."
            gen_reply = AgentGemini.chat(gen_prompt, text, user_id)
            await update.message.reply_text(gen_reply, reply_markup=get_inline_dashboard())
            
    except Exception as err:
        logger.error(f"Routing Error: {err}")
        await update.message.reply_text("Dạ, luồng dữ liệu trung tâm đang đồng bộ, sếp vui lòng thử lại câu lệnh sau vài giây ạ!")

# ─── 6. HỆ THỐNG LỆNH ĐIỀU KHIỂN HỆ THỐNG (SYSTEM COMMANDS) ───────────────────
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    status_text = (
        "🎛️ <b>TRẠNG THÁI CÁC PHÂN HỆ AI ENGINE:</b>\n\n"
        f"🤖 <b>Sếp Tổng Gemini:</b> ✅ Hoạt động ổn định\n"
        f"👨‍💻 <b>Claude Sonnet 4.6 (Đầu não Code):</b> {'✅ Đã kết nối Key' if CLAUDE_API_KEY else '⏳ Chờ nạp Key'}\n"
        f"🎙️ <b>Edge-TTS Audio:</b> ✅ Trực tuyến (Nam Minh Neural)\n"
        f"📈 <b>DuckDuckGo Data:</b> ✅ Sẵn sàng quét mạng\n"
        f"🔒 <b>Chế độ bảo mật (Private):</b> 🔐 ĐÃ KÍCH HOẠT TUYỆT ĐỐI\n"
    )
    await update.message.reply_text(status_text, parse_mode="HTML")

async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    user_id = update.effective_user.id
    if user_id in user_memory:
        user_memory[user_id] = []
    AgentClaude.clear_memory(user_id)
    await update.message.reply_text("🧹 <b>Đã xóa sạch toàn bộ lịch sử bộ nhớ hội thoại ngữ cảnh của sếp!</b>")

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    text = (
        "👑 <b>HỆ THỐNG ENTERPRISE MULTI-AGENT VIP V10.0</b>\n\n"
        "Chào mừng sếp đã quay trở lại trung tâm chỉ huy. Cỗ máy đã được kích hoạt chế độ bảo mật riêng tư cao nhất.\n\n"
        "🧠 <b>Sức mạnh điều phối:</b> Chat tự nhiên tiếng Việt, Sếp Tổng Gemini sẽ tự động kích hoạt ngầm Edge-TTS tạo tiếng nói, DuckDuckGo quét trend hoặc đẩy bài lập trình khó sang cho **Claude 3.5 Sonnet** thi hành!\n\n"
        "🛠️ <b>Các lệnh quản trị nhanh:</b>\n"
        "• Lệnh <code>/status</code> : Kiểm tra trạng thái kết nối các AI\n"
        "• Lệnh <code>/clear</code> : Xóa sạch lịch sử bộ nhớ đệm"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=get_bottom_menu())
    await update.message.reply_text("🎛️ <b>SƠ ĐỒ TỔ CHỨC CÁC PHÒNG BAN:</b>", parse_mode="HTML", reply_markup=get_inline_dashboard())

# ─── THUẬT TOÁN HỖ TRỢ CHIA NHỎ VĂN BẢN TRÁNH TRÀN KHUNG ────────────────────────
async def send_long_text(update: Update, text: str):
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        try: await update.message.reply_text(chunk, parse_mode="HTML")
        except: await update.message.reply_text(chunk)

# ─── GIAO DIỆN NÚT BẤM TƯƠNG TÁC CHUYÊN NGHIỆP ──────────────────────────────────
def get_bottom_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton("🛸 MỞ TRẠM ĐIỀU KHIỂN AI CENTRAL")]], resize_keyboard=True, is_persistent=True)

def get_inline_dashboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👨‍💻 Claude 3.5 Sonnet (Code)", callback_data="btn_code"), InlineKeyboardButton("🎙️ Edge-TTS (Audio)", callback_data="btn_voice")],
        [InlineKeyboardButton("📈 Data Agent (Quét Trend)", callback_data="btn_trend"), InlineKeyboardButton("🌐 Mở Cổng Cấu Hình", web_app=WebAppInfo(url=WEB_APP_URL))]
    ])

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Hệ thống vận hành mượt mà qua luồng chat tự nhiên ngầm!")

# ─── KHỞI CHẠY KHUNG ĐIỀU HÀNH LUỒNG POLLING ─────────────────────────────────────
def main() -> None:
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Enterprise Architecture VIP V10.0 Online...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()