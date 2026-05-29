"""
╔══════════════════════════════════════════════════════════════╗
║   HoTroToanBot - TRẠM ĐIỀU KHIỂN AI ĐA TÁC VỤ V9.0          ║
║   Multi-Agent Orchestration System                            ║
║   Bộ não chính: Gemini 2.0 Flash (Orchestrator)              ║
║   Các AI con: Gemini (Code/MMO), Claude (Phân tích sâu),     ║
║               Edge TTS (Voice), DuckDuckGo (Trend)            ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import logging
import asyncio
import json
import tempfile
import time
from collections import defaultdict
from typing import Optional

import edge_tts
from duckduckgo_search import DDGS
from google import genai
from google.genai import types
import httpx  # Dùng để gọi Claude API (Anthropic)

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

# ─────────────────────────────────────────────────────────────
# ▌ LOGGING
# ─────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("HoTroToanBot")

# ─────────────────────────────────────────────────────────────
# ▌ BIẾN MÔI TRƯỜNG (Railway / VPS)
# ─────────────────────────────────────────────────────────────
TELEGRAM_TOKEN  = os.environ.get("BOT_TOKEN")
GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY")
CLAUDE_API_KEY  = os.environ.get("CLAUDE_API_KEY")   # Anthropic API Key (tùy chọn)
OWNER_ID        = int(os.environ.get("OWNER_ID", "0"))  # Telegram user_id của chủ
WEB_APP_URL     = os.environ.get("WEB_APP_URL", "https://hoangthai223388-maker.github.io/xx88/redirect.html")

# Model mặc định
GEMINI_MODEL    = "gemini-2.0-flash"
CLAUDE_MODEL    = "claude-sonnet-4-6"   # hoặc claude-haiku-4-5 (rẻ hơn)

# ─────────────────────────────────────────────────────────────
# ▌ KIỂM TRA CONFIG
# ─────────────────────────────────────────────────────────────
if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    logger.error("❌ THIẾU BOT_TOKEN hoặc GEMINI_API_KEY!")

if not CLAUDE_API_KEY:
    logger.warning("⚠️  CLAUDE_API_KEY chưa có — Module Claude Analyst sẽ bị tắt.")

# ─────────────────────────────────────────────────────────────
# ▌ KHỞI TẠO AI CLIENTS
# ─────────────────────────────────────────────────────────────
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# ─────────────────────────────────────────────────────────────
# ▌ RATE LIMITER (5 request/phút mỗi user)
# ─────────────────────────────────────────────────────────────
_rate_store: dict[int, list[float]] = defaultdict(list)
RATE_LIMIT_CALLS   = 5
RATE_LIMIT_SECONDS = 60

def is_rate_limited(user_id: int) -> bool:
    now = time.time()
    _rate_store[user_id] = [t for t in _rate_store[user_id] if now - t < RATE_LIMIT_SECONDS]
    if len(_rate_store[user_id]) >= RATE_LIMIT_CALLS:
        return True
    _rate_store[user_id].append(now)
    return False

# ─────────────────────────────────────────────────────────────
# ▌ BẢO MẬT — whitelist chủ nhân
# ─────────────────────────────────────────────────────────────
async def restrict_access(update: Update) -> bool:
    """Trả về True nếu BỊ chặn, False nếu được phép."""
    user_id = update.effective_user.id

    # Nếu OWNER_ID = 0 → chế độ public (test), bỏ qua whitelist
    if OWNER_ID == 0:
        return False

    if user_id != OWNER_ID:
        await update.effective_message.reply_text(
            "🔒 Xin lỗi, trạm điều khiển này là riêng tư. Liên hệ chủ nhân để được cấp quyền."
        )
        return True
    return False

# ─────────────────────────────────────────────────────────────
# ▌ SYSTEM PROMPTS
# ─────────────────────────────────────────────────────────────
ORCHESTRATOR_PROMPT = """
Bạn là Bộ Não Điều Phối Trung Tâm (Central Orchestrator) của hệ thống HoTroToanBot V9.0.
Nhiệm vụ: Đọc tin nhắn tiếng Việt của chủ nhân, phân tích ý định và phân loại thành action JSON.

CHỈ trả về JSON thuần túy, không có markdown, không có lời giải thích. Định dạng:
{"action": "tên_action", "data": "nội_dung_trích_xuất", "lang": "vi"}

Danh sách action hợp lệ:
- "voice"     : Chủ nhân muốn chuyển văn bản → giọng nói. data = đoạn văn cần đọc (bỏ cụm "hãy nói", "đọc giùm").
- "trend"     : Tìm tin tức, xu hướng, quét mạng xã hội. data = từ khóa cốt lõi.
- "code"      : Câu hỏi lập trình, debug, viết script, build app. data = câu hỏi đầy đủ.
- "mmo"       : Chiến lược MMO, marketing, kiếm tiền online, kịch bản video, affiliate. data = yêu cầu đầy đủ.
- "analyze"   : Phân tích sâu, so sánh ý kiến, đánh giá tài liệu, đặt câu hỏi phức tạp cần tư duy cao. data = câu hỏi đầy đủ.
- "image_gen" : Chủ nhân muốn tạo/mô tả ảnh AI, prompt ảnh. data = mô tả hình ảnh bằng tiếng Anh.
- "remind"    : Nhắc việc, ghi chú, todo. data = nội dung cần ghi nhớ.
- "general"   : Lời chào, câu hỏi đơn giản không thuộc nhóm trên. data = câu trả lời ngắn gọn thân thiện.

Ưu tiên "analyze" khi câu hỏi mang tính chiến lược, phân tích, so sánh nhiều chiều.
"""

CODER_PROMPT = """
Bạn là Senior Software Engineer chuyên Python, JavaScript, Automation, DevOps.
Quy tắc:
- Code sạch, có comment, tối ưu hiệu suất
- Giải thích ngắn gọn, đúng trọng tâm
- Ưu tiên dùng thư viện có sẵn, tránh over-engineering
- Nếu là bug: phân tích nguyên nhân gốc rễ trước khi fix
"""

MMO_PROMPT = """
Bạn là Chuyên gia MMO & Digital Marketing thực chiến (affiliate, dropship, TikTok, YouTube, SEO).
Quy tắc:
- Tư duy thực tế, zero-cost hoặc low-cost
- Đưa ra action plan từng bước rõ ràng
- Ưu tiên tự động hóa và scale
- Kịch bản video phải có hook 3 giây đầu
"""

ANALYST_PROMPT = """
Bạn là Chuyên gia Phân Tích Chiến Lược cấp cao (McKinsey-level).
Nhiệm vụ: Phân tích sâu, đa chiều, đưa ra insight không hiển nhiên.
Quy tắc:
- Dùng framework: SWOT, First Principles, Second-order thinking khi phù hợp
- Luôn đặt câu hỏi "Tại sao?" ít nhất 3 lần
- Kết luận phải actionable (có thể thực hiện ngay)
- Trả lời bằng tiếng Việt rõ ràng, súc tích
"""

GENERAL_PROMPT = """
Bạn là trợ lý AI thân thiện của HoTroToanBot V9.0.
Trả lời ngắn gọn, lịch sự, dùng tiếng Việt.
Nếu câu hỏi phức tạp hơn khả năng của bạn, hướng dẫn chủ nhân dùng lệnh /code, /mmo, /analyze, /trend, /voice.
"""

# ─────────────────────────────────────────────────────────────
# ▌ MEMORY — lưu lịch sử hội thoại per user (tối đa 10 lượt)
# ─────────────────────────────────────────────────────────────
MAX_HISTORY = 10
_chat_history: dict[int, list[dict]] = defaultdict(list)

def get_history(user_id: int) -> list[dict]:
    return _chat_history[user_id]

def add_to_history(user_id: int, role: str, content: str):
    history = _chat_history[user_id]
    history.append({"role": role, "content": content})
    if len(history) > MAX_HISTORY * 2:
        _chat_history[user_id] = history[-(MAX_HISTORY * 2):]

def clear_history(user_id: int):
    _chat_history[user_id] = []

# ─────────────────────────────────────────────────────────────
# ▌ AI ENGINE 1: GEMINI (Orchestrator, Code, MMO, General)
# ─────────────────────────────────────────────────────────────
async def call_gemini(
    system_prompt: str,
    user_text: str,
    is_json: bool = False,
    history: Optional[list] = None
) -> str:
    """Gọi Gemini async — không block event loop."""
    def _sync_call():
        try:
            config_args = {"system_instruction": system_prompt}
            if is_json:
                config_args["response_mime_type"] = "application/json"

            # Xây dựng contents có history
            contents = []
            if history:
                for h in history:
                    contents.append(
                        types.Content(
                            role=h["role"],
                            parts=[types.Part(text=h["content"])]
                        )
                    )
            contents.append(
                types.Content(role="user", parts=[types.Part(text=user_text)])
            )

            response = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                config=types.GenerateContentConfig(**config_args),
                contents=contents,
            )
            return response.text or "❌ Gemini trả về rỗng."
        except Exception as e:
            logger.error(f"[Gemini Error] {e}")
            err = str(e).replace("<", "&lt;").replace(">", "&gt;")
            return f"❌ <b>Lỗi Gemini:</b>\n<code>{err}</code>"

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_call)

# ─────────────────────────────────────────────────────────────
# ▌ AI ENGINE 2: CLAUDE (Anthropic) — Phân tích sâu
# ─────────────────────────────────────────────────────────────
async def call_claude(
    system_prompt: str,
    user_text: str,
    history: Optional[list] = None
) -> str:
    """Gọi Claude API (Anthropic) async."""
    if not CLAUDE_API_KEY:
        return "⚠️ Module Claude Analyst chưa được kích hoạt. Vui lòng thêm CLAUDE_API_KEY vào biến môi trường."

    messages = []
    if history:
        for h in history:
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_text})

    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": 2048,
        "system": system_prompt,
        "messages": messages
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": CLAUDE_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json=payload
            )
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]
    except httpx.HTTPStatusError as e:
        logger.error(f"[Claude HTTP Error] {e.response.status_code}: {e.response.text}")
        return f"❌ <b>Lỗi Claude API (HTTP {e.response.status_code}):</b>\n<code>{e.response.text[:300]}</code>"
    except Exception as e:
        logger.error(f"[Claude Error] {e}")
        return f"❌ <b>Lỗi kết nối Claude:</b>\n<code>{str(e)[:300]}</code>"

# ─────────────────────────────────────────────────────────────
# ▌ AI ENGINE 3: TREND / WEB SEARCH (DuckDuckGo)
# ─────────────────────────────────────────────────────────────
async def execute_trend_search(keyword: str) -> str:
    def _sync_search():
        try:
            results = DDGS().text(keyword, max_results=6)
            if not results:
                return f"❌ Không tìm thấy dữ liệu nào cho: <b>{keyword}</b>"
            text = f"🌍 <b>XU HƯỚNG: '{keyword}'</b>\n{'─'*30}\n\n"
            for i, r in enumerate(results, 1):
                title = r.get('title', 'N/A')
                body  = r.get('body', '')[:150]
                href  = r.get('href', '#')
                text += f"{i}. <b>{title}</b>\n<i>{body}...</i>\n🔗 <a href='{href}'>Xem chi tiết</a>\n\n"
            return text
        except Exception as e:
            return f"❌ Lỗi quét web: {e}"

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_search)

# ─────────────────────────────────────────────────────────────
# ▌ AI ENGINE 4: VOICE (Edge TTS)
# ─────────────────────────────────────────────────────────────
VOICE_OPTIONS = {
    "nam": "vi-VN-NamMinhNeural",
    "nu":  "vi-VN-HoaiMyNeural",
}

async def execute_voice_render(
    text: str,
    user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    voice_gender: str = "nam"
) -> None:
    voice = VOICE_OPTIONS.get(voice_gender, VOICE_OPTIONS["nam"])
    status = await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏳ <i>Đang render giọng {voice_gender.upper()} ({voice})...</i>",
        parse_mode="HTML"
    )
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp = f.name
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(tmp)
        with open(tmp, "rb") as audio:
            await context.bot.send_audio(
                chat_id=chat_id,
                audio=audio,
                caption=f"✅ Voice render ({voice_gender}) | {len(text)} ký tự",
                title="HoTroToanBot Voice"
            )
        await status.delete()
    except Exception as e:
        await status.edit_text(f"❌ Lỗi render voice: {e}")
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)

# ─────────────────────────────────────────────────────────────
# ▌ UTILITY: Chia nhỏ tin nhắn dài
# ─────────────────────────────────────────────────────────────
async def send_long_text(update: Update, text: str, parse_mode: str = "HTML"):
    MAX = 4000
    chunks = [text[i:i+MAX] for i in range(0, len(text), MAX)]
    for chunk in chunks:
        try:
            await update.message.reply_text(chunk, parse_mode=parse_mode)
        except Exception:
            await update.message.reply_text(chunk)

# ─────────────────────────────────────────────────────────────
# ▌ KEYBOARDS
# ─────────────────────────────────────────────────────────────
def get_bottom_menu() -> ReplyKeyboardMarkup:
    keyboard = [[KeyboardButton("🛸 MỞ TRẠM ĐIỀU KHIỂN AI CENTRAL")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

def get_inline_dashboard() -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton("👨‍💻 Kỹ Sư Lập Trình", callback_data="btn_code"),
            InlineKeyboardButton("💰 Chiến Lược MMO",   callback_data="btn_mmo"),
        ],
        [
            InlineKeyboardButton("🧠 Phân Tích Sâu (Claude)", callback_data="btn_analyze"),
            InlineKeyboardButton("📈 Quét Xu Hướng",          callback_data="btn_trend"),
        ],
        [
            InlineKeyboardButton("🎙️ Giọng Nam", callback_data="btn_voice_nam"),
            InlineKeyboardButton("🎙️ Giọng Nữ", callback_data="btn_voice_nu"),
        ],
        [
            InlineKeyboardButton("🗑️ Xóa lịch sử chat",             callback_data="btn_clear"),
            InlineKeyboardButton("⚙️ Kho Công Cụ MMO", web_app=WebAppInfo(url=WEB_APP_URL)),
        ],
    ]
    return InlineKeyboardMarkup(kb)

# ─────────────────────────────────────────────────────────────
# ▌ COMMAND HANDLERS
# ─────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    claude_status = "✅ Đã kết nối" if CLAUDE_API_KEY else "⚠️ Chưa cấu hình"
    text = (
        "🛸 <b>TRẠM ĐIỀU KHIỂN AI ĐA TÁC VỤ V9.0</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🤖 <b>Mạng lưới AI đang hoạt động:</b>\n"
        f"  • Gemini 2.0 Flash — Điều phối, Code, MMO ✅\n"
        f"  • Claude Sonnet — Phân tích sâu {claude_status}\n"
        f"  • Edge TTS — Tổng hợp giọng nói ✅\n"
        f"  • DuckDuckGo Search — Quét xu hướng ✅\n\n"
        "🧠 <b>Cách dùng đơn giản nhất:</b>\n"
        "Chỉ cần <i>chat bình thường tiếng Việt</i> — AI điều phối tự xác định và gọi đúng module!\n\n"
        "<b>Ví dụ:</b>\n"
        "• <code>Hãy đọc: Xin chào hệ thống</code> → Tự render voice\n"
        "• <code>Viết bot Python gửi email tự động</code> → Kỹ sư Code\n"
        "• <code>Phân tích thị trường TikTok Shop 2026</code> → Claude Analyst\n"
        "• <code>Quét trend AI tháng này</code> → Quét web\n\n"
        "👇 Hoặc bấm nút để chọn phân hệ:"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=get_bottom_menu())
    await update.message.reply_text("🎛️ <b>BẢNG ĐIỀU KHIỂN:</b>", parse_mode="HTML", reply_markup=get_inline_dashboard())

async def cmd_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    query = " ".join(context.args) if context.args else "Hướng dẫn tôi viết code Python tối ưu."
    user_id = update.effective_user.id
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    history = get_history(user_id)
    reply = await call_gemini(CODER_PROMPT, query, history=history)
    add_to_history(user_id, "user", query)
    add_to_history(user_id, "model", reply)
    await send_long_text(update, f"👨‍💻 <b>KỸ SƯ LẬP TRÌNH:</b>\n\n{reply}")

async def cmd_mmo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    query = " ".join(context.args) if context.args else "Đề xuất mô hình MMO zero-cost ổn định nhất 2026."
    user_id = update.effective_user.id
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    history = get_history(user_id)
    reply = await call_gemini(MMO_PROMPT, query, history=history)
    add_to_history(user_id, "user", query)
    add_to_history(user_id, "model", reply)
    await send_long_text(update, f"💰 <b>CHIẾN LƯỢC MMO:</b>\n\n{reply}")

async def cmd_trend(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    if not context.args:
        await update.message.reply_text("📈 <b>Cú pháp:</b> <code>/trend [từ khóa]</code>", parse_mode="HTML")
        return
    keyword = " ".join(context.args)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = await execute_trend_search(keyword)
    await update.message.reply_text(reply, parse_mode="HTML", disable_web_page_preview=True)

async def cmd_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    args = context.args
    if not args:
        await update.message.reply_text(
            "🎙️ <b>Cú pháp:</b>\n"
            "<code>/voice [văn bản]</code> — giọng Nam\n"
            "<code>/voice nu [văn bản]</code> — giọng Nữ",
            parse_mode="HTML"
        )
        return
    gender = "nu" if args[0].lower() == "nu" else "nam"
    text = " ".join(args[1:] if args[0].lower() == "nu" else args)
    await execute_voice_render(text, update.effective_user.id, context, update.effective_chat.id, gender)

async def cmd_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    query = " ".join(context.args) if context.args else "Phân tích xu hướng AI trong kinh doanh 2026."
    user_id = update.effective_user.id
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    status = await update.message.reply_text("🧠 <i>Claude đang phân tích sâu...</i>", parse_mode="HTML")
    history = get_history(user_id)
    reply = await call_claude(ANALYST_PROMPT, query, history=history)
    add_to_history(user_id, "user", query)
    add_to_history(user_id, "model", reply)
    await status.delete()
    await send_long_text(update, f"🧠 <b>CLAUDE ANALYST:</b>\n\n{reply}")

async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    clear_history(update.effective_user.id)
    await update.message.reply_text("🗑️ Đã xóa toàn bộ lịch sử hội thoại. Bắt đầu cuộc trò chuyện mới!")

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    user_id = update.effective_user.id
    hist_len = len(get_history(user_id)) // 2
    rate_remaining = RATE_LIMIT_CALLS - len([
        t for t in _rate_store[user_id]
        if time.time() - t < RATE_LIMIT_SECONDS
    ])
    text = (
        "📊 <b>TRẠNG THÁI HỆ THỐNG</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🧠 Gemini 2.0 Flash: ✅\n"
        f"🤖 Claude Sonnet: {'✅' if CLAUDE_API_KEY else '❌ Thiếu key'}\n"
        f"🎙️ Edge TTS: ✅\n"
        f"🌍 DuckDuckGo Search: ✅\n\n"
        f"💬 Lịch sử chat hiện tại: {hist_len} lượt\n"
        f"⚡ Request còn lại (phút này): {rate_remaining}/{RATE_LIMIT_CALLS}\n"
    )
    await update.message.reply_text(text, parse_mode="HTML")

# ─────────────────────────────────────────────────────────────
# ▌ CALLBACK QUERY HANDLER (Nút bấm inline)
# ─────────────────────────────────────────────────────────────
CALLBACK_GUIDES = {
    "btn_code":      "👨‍💻 <b>Kỹ Sư Lập Trình</b>\n<code>/code [câu hỏi hoặc đoạn code cần sửa]</code>",
    "btn_mmo":       "💰 <b>Chiến Lược MMO</b>\n<code>/mmo [ý tưởng kiếm tiền hoặc yêu cầu kịch bản]</code>",
    "btn_analyze":   "🧠 <b>Claude Analyst (Phân tích sâu)</b>\n<code>/analyze [câu hỏi chiến lược]</code>",
    "btn_trend":     "📈 <b>Quét Xu Hướng</b>\n<code>/trend [từ khóa]</code>",
    "btn_voice_nam": "🎙️ <b>Giọng Đọc Nam</b>\n<code>/voice [văn bản cần đọc]</code>",
    "btn_voice_nu":  "🎙️ <b>Giọng Đọc Nữ</b>\n<code>/voice nu [văn bản cần đọc]</code>",
    "btn_clear":     None,  # xử lý riêng
}

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "btn_clear":
        clear_history(query.from_user.id)
        await query.message.reply_text("🗑️ Đã xóa lịch sử hội thoại!")
        return

    guide = CALLBACK_GUIDES.get(data)
    if guide:
        await query.message.reply_text(guide, parse_mode="HTML")

# ─────────────────────────────────────────────────────────────
# ▌ BỘ NÃO ĐIỀU PHỐI CHÍNH — xử lý mọi tin nhắn thường
# ─────────────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return

    user_id = update.effective_user.id
    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    # Nút reply keyboard
    if text == "🛸 MỞ TRẠM ĐIỀU KHIỂN AI CENTRAL":
        await cmd_start(update, context)
        return

    # Rate limiting
    if is_rate_limited(user_id):
        await update.message.reply_text(
            f"⏱️ Bạn đang gửi quá nhanh! Tối đa {RATE_LIMIT_CALLS} request/{RATE_LIMIT_SECONDS}s. Thử lại sau nhé."
        )
        return

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # ── Bước 1: Phân loại intent ──
    intent_str = await call_gemini(ORCHESTRATOR_PROMPT, text, is_json=True)

    try:
        intent = json.loads(intent_str)
        action = intent.get("action", "general")
        data   = intent.get("data", text)
    except Exception:
        # JSON lỗi → fallback general
        action, data = "general", text

    logger.info(f"[Routing] user={user_id} action={action} data_preview={data[:60]}")

    # ── Bước 2: Dispatch đến AI tương ứng ──
    history = get_history(user_id)

    if action == "voice":
        await execute_voice_render(data, user_id, context, chat_id)
        return

    elif action == "trend":
        status = await update.message.reply_text(
            f"⏳ <i>Đang quét mạng: <b>{data}</b>...</i>", parse_mode="HTML"
        )
        reply = await execute_trend_search(data)
        await status.delete()
        await update.message.reply_text(reply, parse_mode="HTML", disable_web_page_preview=True)

    elif action == "code":
        reply = await call_gemini(CODER_PROMPT, data, history=history)
        add_to_history(user_id, "user", data)
        add_to_history(user_id, "model", reply)
        await send_long_text(update, f"👨‍💻 <b>KỸ SƯ CODE:</b>\n\n{reply}")

    elif action == "mmo":
        reply = await call_gemini(MMO_PROMPT, data, history=history)
        add_to_history(user_id, "user", data)
        add_to_history(user_id, "model", reply)
        await send_long_text(update, f"💰 <b>CHIẾN LƯỢC MMO:</b>\n\n{reply}")

    elif action == "analyze":
        status = await update.message.reply_text("🧠 <i>Claude đang phân tích...</i>", parse_mode="HTML")
        reply = await call_claude(ANALYST_PROMPT, data, history=history)
        add_to_history(user_id, "user", data)
        add_to_history(user_id, "model", reply)
        await status.delete()
        await send_long_text(update, f"🧠 <b>CLAUDE ANALYST:</b>\n\n{reply}")

    elif action == "image_gen":
        # Placeholder — tích hợp Imagen hoặc DALL-E sau
        await update.message.reply_text(
            f"🖼️ <b>Image Gen (Sắp ra mắt)</b>\n\n"
            f"Prompt: <i>{data}</i>\n\n"
            f"Module tạo ảnh AI đang được tích hợp. Hiện tại bạn có thể dùng <b>Midjourney</b> hoặc <b>Ideogram</b> với prompt trên.",
            parse_mode="HTML"
        )

    elif action == "remind":
        # Lưu vào user_data của bot
        if "reminders" not in context.user_data:
            context.user_data["reminders"] = []
        context.user_data["reminders"].append(data)
        await update.message.reply_text(
            f"📌 <b>Đã ghi nhớ:</b>\n<i>{data}</i>\n\n"
            f"Tổng số ghi chú: {len(context.user_data['reminders'])} mục\n"
            f"(Dùng /notes để xem tất cả)",
            parse_mode="HTML"
        )

    else:
        # General chat — Gemini với history
        reply = await call_gemini(GENERAL_PROMPT, data, history=history)
        add_to_history(user_id, "user", data)
        add_to_history(user_id, "model", reply)
        await update.message.reply_text(reply, reply_markup=get_inline_dashboard())

async def cmd_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    notes = context.user_data.get("reminders", [])
    if not notes:
        await update.message.reply_text("📝 Chưa có ghi chú nào. Chat <i>'Nhắc tôi...'</i> để thêm!", parse_mode="HTML")
        return
    text = "📋 <b>DANH SÁCH GHI CHÚ:</b>\n\n"
    for i, n in enumerate(notes, 1):
        text += f"{i}. {n}\n"
    await update.message.reply_text(text, parse_mode="HTML")

# ─────────────────────────────────────────────────────────────
# ▌ MAIN
# ─────────────────────────────────────────────────────────────
def main() -> None:
    if not TELEGRAM_TOKEN:
        logger.critical("❌ Thiếu BOT_TOKEN. Dừng lại.")
        return

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("code",    cmd_code))
    app.add_handler(CommandHandler("mmo",     cmd_mmo))
    app.add_handler(CommandHandler("trend",   cmd_trend))
    app.add_handler(CommandHandler("voice",   cmd_voice))
    app.add_handler(CommandHandler("analyze", cmd_analyze))
    app.add_handler(CommandHandler("clear",   cmd_clear))
    app.add_handler(CommandHandler("status",  cmd_status))
    app.add_handler(CommandHandler("notes",   cmd_notes))

    # Inline buttons
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Tin nhắn thường
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🚀 HoTroToanBot V9.0 Multi-Agent đã khởi động!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
