"""
╔══════════════════════════════════════════════════════════════╗
║   TOAN DAAS V13.1 - ENTERPRISE SAAS BILLING ENGINE           ║
║   Tối ưu Lợi nhuận | Báo động API | Hòm Thư AI | Sổ tay HDSD ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import logging
import asyncio
import edge_tts
import json
import sqlite3
import httpx
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger("TOAN_DAAS")

TELEGRAM_TOKEN = os.environ.get("BOT_TOKEN")
# CHÚ Ý: Đảm bảo biến ADMIN_ID trên Railway đã được đặt thành 7126457028
ADMIN_ID = str(os.environ.get("ADMIN_ID", "7126457028")) 

DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY")
REMOVEBG_API_KEY = os.environ.get("REMOVEBG_API_KEY")
FISH_AUDIO_KEY = os.environ.get("FISH_AUDIO_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
user_memory = {}       

DB_FILE = "toandaas_system.db"

# ─── 1. BẢNG GIÁ KINH TẾ (1 Xu = 100 VNĐ) ──────────────────────────────────────
COSTS = {
    'chat': 2,        # 200đ
    'whisper': 5,     # 500đ
    'download': 5,    # 500đ
    'voice': 30,      # 3.000đ
    'image': 50       # 5.000đ
}
TRIAL_CREDITS = 30    # Tặng 30 Xu trải nghiệm

# ─── 2. HỆ THỐNG DATABASE (TÀI KHOẢN & HÒM THƯ) ───────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, username TEXT, credits INTEGER, is_vip INTEGER, join_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, username TEXT, content TEXT, timestamp DATETIME)''')
    conn.commit()
    conn.close()

def get_user(user_id, username="Unknown"):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT credits, is_vip FROM users WHERE user_id=?", (str(user_id),))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (user_id, username, credits, is_vip, join_date) VALUES (?, ?, ?, ?, ?)", 
                  (str(user_id), username, TRIAL_CREDITS, 0, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        row = (TRIAL_CREDITS, 0)
    conn.close()
    return row[0], row[1]

def deduct_credit(user_id, action_type) -> bool:
    if str(user_id) == ADMIN_ID: return True 
    credits, is_vip = get_user(user_id)
    if is_vip == 1: return True 
    cost = COSTS.get(action_type, 2)
    if credits >= cost:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET credits = credits - ? WHERE user_id=?", (cost, str(user_id)))
        conn.commit()
        conn.close()
        return True
    return False

def add_credit(user_id, amount):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET credits = credits + ? WHERE user_id=?", (amount, str(user_id)))
    conn.commit()
    conn.close()

# ─── 3. CƠ CHẾ BÁO ĐỘNG ADMIN ─────────────────────────────────────────────────
async def alert_admin(context: ContextTypes.DEFAULT_TYPE, service_name: str, error_msg: str):
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"🚨 <b>BÁO ĐỘNG ADMIN TOAN DAAS</b> 🚨\n\nDịch vụ <b>{service_name}</b> vừa gặp sự cố!\nChi tiết: <code>{error_msg}</code>\n\n👉 Sếp hãy kiểm tra lại tài khoản Token/Credit của bên thứ 3 nhé!", parse_mode="HTML")
    except: pass

# ─── 4. LỆNH CỦA KHÁCH HÀNG & THANH TOÁN ──────────────────────────────────────
async def cmd_naptien(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    username = update.effective_user.first_name
    credits, _ = get_user(user_id, username)
    msg = (
        f"💳 <b>NẠP SỐ DƯ CREDIT — HỆ THỐNG TOAN DAAS</b>\n\n"
        f"👤 Khách hàng: {username} (ID: <code>{user_id}</code>)\n"
        f"🪙 Số dư hiện tại: <b>{credits} Xu (Credit)</b>\n\n"
        f"<b>🛒 BẢNG GIÁ ƯU ĐÃI (1 Xu = 100đ):</b>\n"
        f"• Gói Cà Phê: 50.000đ ➔ <b>500 Xu</b>\n"
        f"• Gói Tiêu Chuẩn: 100.000đ ➔ <b>1.050 Xu</b>\n"
        f"• Gói Thương Mại: 200.000đ ➔ <b>2.200 Xu</b>\n"
        f"• Gói Doanh Nghiệp: 500.000đ ➔ <b>6.000 Xu</b>\n\n"
        f"<b>🏦 PHƯƠNG THỨC CHUYỂN KHOẢN TỰ ĐỘNG:</b>\n"
        f"- Ngân hàng: <b>ACB (Ngân hàng Á Châu)</b>\n"
        f"- Số tài khoản: <b>8899397968</b>\n"
        f"- Chủ tài khoản: <b>NGUYEN MANH TOAN</b>\n"
        f"- Nội dung bắt buộc: <code>DAAS {user_id}</code>\n\n"
        f"<i>💡 Quét mã QR đi kèm để hệ thống tự điền STK & Nội dung. AI sẽ cấp Xu ngay khi Admin duyệt.</i>"
    )
    qr_url = f"https://img.vietqr.io/image/ACB-8899397968-compact.png?amount=&addInfo=DAAS+{user_id}&accountName=NGUYEN+MANH+TOAN"
    await update.message.reply_photo(photo=qr_url, caption=msg, parse_mode="HTML")

async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    credits, is_vip = get_user(user_id, update.effective_user.first_name)
    if user_id == ADMIN_ID:
        account_status = "👑 TÀI KHOẢN QUẢN TRỊ VIÊN (ADMIN)"
        credits_display = "Vô Hạn (∞)"
    else:
        account_status = "💳 Gói Cước Trả Trước (Credit)"
        credits_display = f"{credits} Xu"

    msg = f"👤 <b>HỒ SƠ TÀI KHOẢN</b>\n\n• Mã ID: <code>{user_id}</code>\n• Trạng thái: {account_status}\n• Hạn mức khả dụng: <b>{credits_display}</b>\n\n👉 Gõ /naptien để mua thêm hạn mức.\n👉 Gõ /gopy kèm nội dung để phản hồi chất lượng."
    await update.message.reply_text(msg, parse_mode="HTML")

async def cmd_gopy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    username = update.effective_user.first_name
    content = " ".join(context.args)
    if not content:
        await update.message.reply_text("⚠️ Vui lòng nhập nội dung. VD: `/gopy Máy hút video bị lỗi rồi bot ơi`", parse_mode="HTML")
        return
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO feedback (user_id, username, content, timestamp) VALUES (?, ?, ?, ?)", (str(user_id), username, content, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ <b>Cảm ơn bạn!</b> Góp ý đã được ghi nhận vào hòm thư hệ thống.", parse_mode="HTML")

# ─── 5. LỆNH DÀNH RIÊNG CHO ADMIN (SẾP TOÀN) ──────────────────────────────────
async def cmd_admin_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.effective_user.id) != ADMIN_ID: return
    try:
        target_id, amount = context.args[0], int(context.args[1])
        add_credit(target_id, amount)
        await update.message.reply_text(f"✅ Đã bơm {amount} Xu cho ID: {target_id}")
        await context.bot.send_message(chat_id=target_id, text=f"🎉 <b>GIAO DỊCH THÀNH CÔNG!</b>\nTài khoản của bạn đã được Admin cộng <b>{amount} Xu</b>.", parse_mode="HTML")
    except: await update.message.reply_text("⚠️ Lỗi. Cú pháp: /add <ID> <Số_Xu>")

async def cmd_admin_gopy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.effective_user.id) != ADMIN_ID: return
    await update.message.reply_text("⏳ <i>Đang gọi AI tổng hợp hòm thư góp ý...</i>", parse_mode="HTML")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    seven_days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("SELECT username, content FROM feedback WHERE timestamp >= ?", (seven_days_ago,))
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        await update.message.reply_text("📭 Hòm thư 7 ngày qua trống rỗng.")
        return
        
    raw_feedbacks = "\n".join([f"- {r[0]}: {r[1]}" for r in rows])
    prompt = f"Bạn là Thư ký Giám đốc. Dưới đây là các góp ý của khách hàng gửi cho hệ thống phần mềm TOAN DAAS. Hãy phân tích, gom nhóm các lỗi/yêu cầu giống nhau và tóm tắt cực kỳ ngắn gọn, chuyên nghiệp đệ trình cho Giám đốc xử lý:\n{raw_feedbacks}"
    summary = AgentGemini.chat(prompt, "Tổng hợp góp ý", ADMIN_ID)
    await send_long_text(update, f"📊 <b>BÁO CÁO GÓP Ý KHÁCH HÀNG (7 NGÀY QUA)</b>\n\n{summary}")

async def cmd_admin_xoa_gopy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.effective_user.id) != ADMIN_ID: return
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    seven_days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("DELETE FROM feedback WHERE timestamp < ?", (seven_days_ago,))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    await update.message.reply_text(f"🧹 <b>Đã dọn dẹp hệ thống!</b>\nXóa thành công {deleted} góp ý cũ hơn 7 ngày.", parse_mode="HTML")

# ─── 6. CÁC PHÂN HỆ AI (CÓ BÁO ĐỘNG ADMIN) ──────────────────────────────────
class AgentRouter(BaseModel):
    action: str = Field(description="voice, code, content, image, download, general")
    data: str = Field(description="Từ khóa nội dung")

class AgentGemini:
    @staticmethod
    def chat(prompt: str, text: str, uid: int, is_json: bool=False) -> str:
        if not gemini_client: return "❌ Kết nối AI gián đoạn."
        if uid not in user_memory: user_memory[uid] = []
        user_memory[uid].append(types.Content(role="user", parts=[types.Part(text=text)]))
        if len(user_memory[uid]) > 10: user_memory[uid] = user_memory[uid][-10:]
        cfg = {"system_instruction": prompt, "response_mime_type": "application/json" if is_json else "text/plain"}
        if is_json: cfg["response_schema"] = AgentRouter
        try:
            res = gemini_client.models.generate_content(model="gemini-2.0-flash", config=types.GenerateContentConfig(**cfg), contents=user_memory[uid] if not is_json else text)
            if not is_json: user_memory[uid].append(types.Content(role="model", parts=[types.Part(text=res.text)]))
            return res.text
        except: return "Lỗi hệ thống Gemini."

class AgentVoice:
    @staticmethod
    async def render(text: str, user_id: int, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        out = f"voice_{user_id}.mp3"
        msg = await context.bot.send_message(chat_id=chat_id, text="⏳ <i>[Nhân Bản Giọng Nói] Đang tổng hợp audio...</i>", parse_mode="HTML")
        try:
            try:
                async with httpx.AsyncClient() as client:
                    res = await client.post("https://api.fish.audio/v1/tts", headers={"Authorization": f"Bearer {FISH_AUDIO_KEY}", "Content-Type": "application/json"}, json={"text": text, "reference_id": "7f0955e88846433e9ecb241357608bf8", "format": "mp3"}, timeout=30.0)
                if res.status_code == 200:
                    with open(out, 'wb') as f: f.write(res.content)
                else: 
                    await alert_admin(context, "Fish Audio", f"Lỗi {res.status_code} - Có thể hết credit!")
                    raise Exception("Fallback Edge")
            except:
                communicate = edge_tts.Communicate(text, "vi-VN-NamMinhNeural")
                await communicate.save(out)
            with open(out, 'rb') as f: 
                await context.bot.send_audio(chat_id=chat_id, audio=f, caption=f"🔊 Thành công! (-{COSTS['voice']} Xu)")
            await msg.delete()
        except: await msg.edit_text("❌ Lỗi Voice.")
        finally:
            if os.path.exists(out): os.remove(out)

class AgentWhisper:
    @staticmethod
    async def transcribe(file_bytes: bytes, context: ContextTypes.DEFAULT_TYPE) -> str:
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post("https://api.openai.com/v1/audio/transcriptions", headers={"Authorization": f"Bearer {OPENAI_API_KEY}"}, files={'file': ('v.ogg', file_bytes, 'audio/ogg')}, data={'model': 'whisper-1', 'language': 'vi'}, timeout=60.0)
                if res.status_code == 200: return res.json().get("text", "")
                await alert_admin(context, "OpenAI Whisper", f"Status: {res.status_code}. Hết token?")
                return "❌ Lỗi Ghi Âm."
        except: return "❌ Cổng âm thanh gián đoạn."

class AgentRemoveBg:
    @staticmethod
    async def remove(img_bytes: bytes, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        msg = await context.bot.send_message(chat_id=chat_id, text="⏳ <i>[Studio Đồ Họa] Đang bóc tách nền...</i>", parse_mode="HTML")
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post("https://api.remove.bg/v1.0/removebg", headers={"X-Api-Key": REMOVEBG_API_KEY}, files={"image_file": img_bytes}, data={"size": "auto"}, timeout=30.0)
            if res.status_code == 200:
                await context.bot.send_document(chat_id=chat_id, document=res.content, filename="no_bg.png", caption=f"✂️ Tách nền thành công! (-{COSTS['image']} Xu)")
                await msg.delete()
            else:
                await alert_admin(context, "Remove.bg", f"Code {res.status_code}. Có thể hết lượt tách nền!")
                await msg.edit_text("❌ Hệ thống đồ họa báo lỗi.")
        except: await msg.edit_text("❌ Lỗi kết nối đồ họa.")

class AgentDownloader:
    @staticmethod
    async def download(url: str, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        msg = await context.bot.send_message(chat_id=chat_id, text="⏳ <i>[Máy Hút Media Sạch] Đang bóc tách video...</i>", parse_mode="HTML")
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post("https://api.cobalt.tools/api/json", headers={"Accept": "application/json", "Content-Type": "application/json"}, json={"url": url}, timeout=30.0)
            if res.status_code == 200:
                if res.json().get("status") in ["stream", "redirect", "success"]:
                    await context.bot.send_video(chat_id=chat_id, video=res.json().get("url"), caption=f"🎬 Đã làm sạch video! (-{COSTS['download']} Xu)")
                    await msg.delete()
                else: await msg.edit_text("❌ Link không được hỗ trợ.")
            else: await msg.edit_text("❌ Máy chủ hút dữ liệu từ chối.")
        except: await msg.edit_text("❌ Lỗi luồng tải video.")

# ─── 7. ĐIỀU PHỐI TIN NHẮN ───────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text, uid = update.message.text.strip(), update.message.effective_user.id
    if text == "🛸 MENU DỊCH VỤ TOAN DAAS": return await cmd_start(update, context)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    routing_instruction = "Phân loại: 'voice', 'code', 'content', 'download', 'general'. Nếu user gửi link URL -> 'download'. Nếu user yêu cầu đọc voice/tạo giọng nói -> 'voice'."
    route = json.loads(AgentGemini.chat(routing_instruction, text, uid, is_json=True))
    act, data = route.get("action", "general"), route.get("data", text)
    
    cost_type = 'voice' if act == 'voice' else 'download' if act == 'download' else 'chat'
    if not deduct_credit(uid, cost_type):
        return await update.message.reply_text(f"❌ <b>HẾT HẠN MỨC!</b> Yêu cầu {COSTS[cost_type]} Xu.\nGõ /naptien để mua thêm.", parse_mode="HTML")
        
    if act == "voice": await AgentVoice.render(data, uid, context, update.effective_chat.id)
    elif act == "download": await AgentDownloader.download(data, context, update.effective_chat.id)
    else: await send_long_text(update, f"🤖 {AgentGemini.chat('Bạn là Trợ Lý Ảo TOAN DAAS. Trả lời súc tích.', text, uid)}\n\n<i>(-{COSTS['chat']} Xu)</i>")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not deduct_credit(update.effective_user.id, 'image'):
        return await update.message.reply_text(f"❌ Cần {COSTS['image']} Xu để dùng Studio Đồ Họa. Gõ /naptien.")
    context.user_data["last_photo_bytes"] = bytes(await (await update.message.photo[-1].get_file()).download_as_bytearray())
    await update.message.reply_text("📥 Đã nhận Ảnh!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✂️ Tách Nền Xuyên Thấu", callback_data="removebg")]]))

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not deduct_credit(update.effective_user.id, 'whisper'):
        return await update.message.reply_text(f"❌ Cần {COSTS['whisper']} Xu để Bóc Băng Giọng Nói. Gõ /naptien.")
    msg = await update.message.reply_text("⚡ <i>[Trợ Lý Bóc Băng AI] Đang xử lý...</i>", parse_mode="HTML")
    txt = await AgentWhisper.transcribe(bytes(await (await (update.message.voice or update.message.audio).get_file()).download_as_bytearray()), context)
    await msg.delete()
    if not txt.startswith("❌"):
        await update.message.reply_text(f"🗣️ <i>\"{txt}\"</i>\n\n<i>(-{COSTS['whisper']} Xu)</i>", parse_mode="HTML")
        update.message.text = txt
        await handle_message(update, context)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer() 
    if update.callback_query.data == "removebg" and context.user_data.get("last_photo_bytes"):
        await AgentRemoveBg.remove(context.user_data.get("last_photo_bytes"), context, update.callback_query.message.chat_id)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    get_user(update.effective_user.id, update.effective_user.first_name) 
    text = (
        "👑 <b>HỆ SINH THÁI AI — TOAN DAAS V13.1</b>\n\n"
        "Chào mừng bạn! Dưới đây là Sổ tay hướng dẫn sử dụng cỗ máy tự động hóa:\n\n"
        f"🎁 <b>Tài khoản mới:</b> Bạn có <b>{TRIAL_CREDITS} Xu</b> trải nghiệm.\n\n"
        "🛠️ <b>CÁCH RA LỆNH CHO HỆ THỐNG:</b>\n"
        f"<b>1. Trợ Lý Ảo TOAN DAAS</b> (-{COSTS['chat']} Xu):\n"
        "👉 <i>Cách dùng:</i> Gõ tin nhắn bình thường (VD: 'Viết kịch bản Tiktok về loa bluetooth').\n\n"
        f"<b>2. Trợ Lý Bóc Băng AI</b> (-{COSTS['whisper']} Xu):\n"
        "👉 <i>Cách dùng:</i> Bấm giữ nút Micro 🎤, gửi 1 đoạn ghi âm, AI sẽ chuyển thành văn bản và tự hiểu lệnh.\n\n"
        f"<b>3. Máy Hút Media Sạch</b> (-{COSTS['download']} Xu):\n"
        "👉 <i>Cách dùng:</i> Copy link video (TikTok/Youtube/FB) và dán thẳng vào khung chat.\n\n"
        f"<b>4. Studio Đồ Họa Tự Động</b> (-{COSTS['image']} Xu):\n"
        "👉 <i>Cách dùng:</i> Bấm nút Gửi Ảnh 🖼️, tải 1 bức ảnh lên để AI tách nền xuyên thấu.\n\n"
        f"<b>5. Nhân Bản Giọng Nói Tiếng Việt</b> (-{COSTS['voice']} Xu):\n"
        "👉 <i>Cách dùng:</i> Nhắn tin với cú pháp 'Đọc voice: [nội dung của bạn]'.\n\n"
        "💡 <b>Lệnh hệ thống:</b>\n"
        "• /profile - Xem ID và Số dư Xu\n"
        "• /naptien - Nạp thêm hạn mức\n"
        "• /gopy <nội dung> - Gửi phản hồi báo lỗi"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🛸 MENU DỊCH VỤ TOAN DAAS")]], resize_keyboard=True))

def main() -> None:
    init_db() 
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("naptien", cmd_naptien))
    app.add_handler(CommandHandler("gopy", cmd_gopy))
    app.add_handler(CommandHandler("add", cmd_admin_add)) 
    app.add_handler(CommandHandler("admin_gopy", cmd_admin_gopy)) 
    app.add_handler(CommandHandler("admin_xoa_gopy", cmd_admin_xoa_gopy)) 
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("🚀 LÕI BILLING V13.1 ONLINE...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()