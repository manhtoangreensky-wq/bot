"""
╔══════════════════════════════════════════════════════════════╗
║   TOAN DAAS V14.0 - DYNAMIC BILLING & VIP DISCOUNT           ║
║   Pay-as-you-go (MB/Chars) | Deepgram Audio | Auto-Tiers     ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import logging
import asyncio
import edge_tts
import json
import sqlite3
import httpx
import math
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger("TOAN_DAAS")

TELEGRAM_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = str(os.environ.get("ADMIN_ID", "7126457028")) 

REMOVEBG_API_KEY = os.environ.get("REMOVEBG_API_KEY")
FISH_AUDIO_KEY = os.environ.get("FISH_AUDIO_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "28c47440be06a578356c7f636388f3e818a4337b") # Đã gắn key Deepgram của sếp

gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
user_memory = {}       

DB_FILE = "toandaas_system.db"
TRIAL_CREDITS = 200

# ─── 1. DATABASE & TÍNH TOÁN CHI PHÍ ĐỘNG ──────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, username TEXT, credits INTEGER, is_vip INTEGER, join_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, username TEXT, content TEXT, timestamp DATETIME)''')
    # Bảng lưu bill chờ duyệt (trạng thái pending)
    c.execute('''CREATE TABLE IF NOT EXISTS pending_deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        username TEXT,
        file_id TEXT,
        submitted_at DATETIME,
        status TEXT DEFAULT 'pending'
    )''')
    try: c.execute("ALTER TABLE users ADD COLUMN total_spent INTEGER DEFAULT 0")
    except: pass
    conn.commit()
    conn.close()

def get_user(user_id, username="Unknown"):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT credits, total_spent, is_vip FROM users WHERE user_id=?", (str(user_id),))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (user_id, username, credits, is_vip, join_date, total_spent) VALUES (?, ?, ?, ?, ?, ?)", 
                  (str(user_id), username, TRIAL_CREDITS, 0, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 0))
        conn.commit()
        row = (TRIAL_CREDITS, 0, 0)
    conn.close()
    return row[0], row[1], row[2]

def calculate_dynamic_cost(action_type, size_or_length):
    if action_type == 'chat': return 2 + math.ceil(size_or_length / 500) * 1
    elif action_type == 'whisper': return 5 + math.ceil(size_or_length / (1024 * 1024)) * 10 # Tính theo MB
    elif action_type == 'image': return 40 + math.ceil(size_or_length / (1024 * 1024)) * 5 # Tính theo MB
    elif action_type == 'voice': return 10 + math.ceil(size_or_length / 50) * 5
    elif action_type == 'download': return 5
    return 2

def apply_discount(total_spent, raw_cost):
    if total_spent >= 20000: discount = 0.20 # Giảm 20%
    elif total_spent >= 5000: discount = 0.10 # Giảm 10%
    else: discount = 0.0
    return math.ceil(raw_cost * (1 - discount)), discount

def deduct_dynamic_credit(user_id, action_type, size_or_length) -> tuple[bool, int, float]:
    if str(user_id) == ADMIN_ID: return True, 0, 1.0 
    credits, total_spent, is_vip = get_user(user_id)
    if is_vip == 1: return True, 0, 1.0 
    
    raw_cost = calculate_dynamic_cost(action_type, size_or_length)
    final_cost, discount_rate = apply_discount(total_spent, raw_cost)
    
    if credits >= final_cost:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET credits = credits - ?, total_spent = total_spent + ? WHERE user_id=?", (final_cost, final_cost, str(user_id)))
        conn.commit()
        conn.close()
        return True, final_cost, discount_rate
    return False, final_cost, discount_rate

def add_credit(user_id, amount):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET credits = credits + ? WHERE user_id=?", (amount, str(user_id)))
    conn.commit()
    conn.close()

async def alert_admin(context: ContextTypes.DEFAULT_TYPE, service_name: str, error_msg: str):
    try: await context.bot.send_message(chat_id=ADMIN_ID, text=f"🚨 <b>BÁO ĐỘNG TOAN DAAS</b> 🚨\n\n{service_name} lỗi: <code>{error_msg}</code>", parse_mode="HTML")
    except: pass

# ─── 2. LỆNH CỦA KHÁCH HÀNG ──────────────────────────────────────
async def cmd_naptien(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    credits, total_spent, _ = get_user(user_id, update.effective_user.first_name)
    msg = (
        f"💳 <b>NẠP SỐ DƯ — HỆ THỐNG TOAN DAAS</b>\n\n"
        f"👤 ID Telegram của bạn: <code>{user_id}</code>\n"
        f"🪙 Số dư hiện tại: <b>{credits} Xu</b>\n\n"
        f"<b>🛒 BẢNG GIÁ ƯU ĐÃI (1 Xu = 100đ):</b>\n"
        f"• Gói Cà Phê: 50.000đ ➔ <b>500 Xu</b>\n"
        f"• Gói Tiêu Chuẩn: 100.000đ ➔ <b>1.050 Xu</b>\n"
        f"• Gói Doanh Nghiệp: 500.000đ ➔ <b>6.000 Xu</b>\n\n"
        f"<b>🏦 CHUYỂN KHOẢN:</b>\n"
        f"- Ngân hàng: <b>ACB</b>\n"
        f"- STK: <b>8899397968</b> (NGUYEN MANH TOAN)\n"
        f"- Nội dung bắt buộc: <code>DAAS {user_id}</code>\n\n"
        f"<b>📋 QUY TRÌNH 3 BƯỚC:</b>\n"
        f"1️⃣ Chuyển khoản với nội dung <code>DAAS {user_id}</code>\n"
        f"2️⃣ Chụp màn hình bill ngân hàng (có đủ: số tiền, nội dung, thời gian)\n"
        f"3️⃣ Gửi ảnh bill vào đây ngay trong chat này ➔ Bot tự báo Admin duyệt!\n\n"
        f"⚠️ <i>Lưu ý: ID Telegram là mã định danh duy nhất để Admin cấp xu chính xác cho bạn. Vui lòng không chuyển khoản thiếu nội dung.</i>"
    )
    qr_url = f"https://img.vietqr.io/image/ACB-8899397968-compact.png?amount=&addInfo=DAAS+{user_id}&accountName=NGUYEN+MANH+TOAN"
    USER_BILL_STATE[user_id] = True  # Đánh dấu: ảnh kế tiếp từ user này là bill
    await update.message.reply_photo(photo=qr_url, caption=msg, parse_mode="HTML")

async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    credits, total_spent, _ = get_user(user_id, update.effective_user.first_name)
    
    tier_name = "🥉 Tiêu Chuẩn (Nguyên giá)"
    if user_id == ADMIN_ID: tier_name = "👑 ADMIN (Miễn phí 100%)"
    elif total_spent >= 20000: tier_name = "🥇 VÀNG (Giảm 20% dịch vụ)"
    elif total_spent >= 5000: tier_name = "🥈 BẠC (Giảm 10% dịch vụ)"

    msg = f"👤 <b>HỒ SƠ TÀI KHOẢN</b>\n\n• Mã ID: <code>{user_id}</code>\n• Hạng: <b>{tier_name}</b>\n• Hạn mức khả dụng: <b>{credits if user_id != ADMIN_ID else 'Vô Hạn (∞)'} Xu</b>\n• Tổng chi tiêu hệ thống: {total_spent} Xu\n\n👉 Gõ /naptien để mua thêm hạn mức."
    await update.message.reply_text(msg, parse_mode="HTML")

async def cmd_gopy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    content = " ".join(context.args)
    if not content: return await update.message.reply_text("⚠️ Vui lòng nhập nội dung. VD: `/gopy Thêm thanh toán Momo đi bot`", parse_mode="HTML")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO feedback (user_id, username, content, timestamp) VALUES (?, ?, ?, ?)", (str(update.effective_user.id), update.effective_user.first_name, content, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ <b>Cảm ơn bạn!</b> Góp ý / Đề xuất của bạn đã được ghi nhận.", parse_mode="HTML")

# ADMIN COMMANDS
async def cmd_admin_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.effective_user.id) != ADMIN_ID: return
    try:
        add_credit(context.args[0], int(context.args[1]))
        await update.message.reply_text(f"✅ Đã bơm {context.args[1]} Xu cho ID: {context.args[0]}")
    except: await update.message.reply_text("⚠️ Lỗi. Cú pháp: /add <ID> <Số_Xu>")

async def cmd_admin_gopy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.effective_user.id) != ADMIN_ID: return
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT username, content FROM feedback WHERE timestamp >= ?", ((datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"),))
    rows = c.fetchall()
    conn.close()
    if not rows: return await update.message.reply_text("📭 Hòm thư 7 ngày qua trống.")
    summary = AgentGemini.chat(f"Tóm tắt yêu cầu khách hàng cực ngắn ngọn:\n" + "\n".join([f"- {r[0]}: {r[1]}" for r in rows]), "Tóm tắt", ADMIN_ID)
    await update.message.reply_text(f"📊 <b>BÁO CÁO GÓP Ý (7 NGÀY)</b>\n\n{summary}", parse_mode="HTML")

# ─── 3. PHÂN HỆ AI (DEEPGRAM THAY THẾ WHISPER) ──────────────────────────────────
class AgentRouter(BaseModel):
    action: str = Field(description="voice, code, content, image, download, general")
    data: str = Field(description="Từ khóa")

class AgentGemini:
    @staticmethod
    def chat(prompt: str, text: str, uid: int, is_json: bool=False) -> str:
        if not gemini_client: return "❌ Lỗi AI."
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

class AgentDeepgram:
    @staticmethod
    async def transcribe(file_bytes: bytes, context: ContextTypes.DEFAULT_TYPE) -> str:
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    "https://api.deepgram.com/v1/listen?model=nova-2&language=vi&smart_format=true", 
                    headers={"Authorization": f"Token {DEEPGRAM_API_KEY}", "Content-Type": "audio/mpeg"}, 
                    content=file_bytes, timeout=60.0)
                if res.status_code == 200: 
                    return res.json().get('results', {}).get('channels', [{}])[0].get('alternatives', [{}])[0].get('transcript', 'Không nhận diện được lời nói.')
                await alert_admin(context, "Deepgram", f"Code {res.status_code}. Báo lỗi API!")
                return "❌ Cổng bóc băng lỗi."
        except Exception as e: return f"❌ Lỗi: {str(e)}"

# CÁC AGENT KHÁC (GIỮ NGUYÊN LÕI, THAY ĐỔI BILLING Ở HANDLER)
class AgentVoice:
    @staticmethod
    async def render(text: str, user_id: int, context: ContextTypes.DEFAULT_TYPE, chat_id: int, cost: int):
        out = f"v_{user_id}.mp3"
        msg = await context.bot.send_message(chat_id=chat_id, text="⏳ <i>[Nhân Bản Giọng Nói] Đang tổng hợp...</i>", parse_mode="HTML")
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post("https://api.fish.audio/v1/tts", headers={"Authorization": f"Bearer {FISH_AUDIO_KEY}", "Content-Type": "application/json"}, json={"text": text, "reference_id": "7f0955e88846433e9ecb241357608bf8", "format": "mp3"}, timeout=30.0)
            if res.status_code == 200:
                with open(out, 'wb') as f: f.write(res.content)
            else:
                communicate = edge_tts.Communicate(text, "vi-VN-NamMinhNeural")
                await communicate.save(out)
            with open(out, 'rb') as f: await context.bot.send_audio(chat_id=chat_id, audio=f, caption=f"🔊 Hoàn tất! (-{cost} Xu)")
            await msg.delete()
        except: await msg.edit_text("❌ Lỗi Voice.")
        finally:
            if os.path.exists(out): os.remove(out)

class AgentDownloader:
    @staticmethod
    async def download(url: str, context: ContextTypes.DEFAULT_TYPE, chat_id: int, cost: int):
        msg = await context.bot.send_message(chat_id=chat_id, text="⏳ <i>Đang bóc tách video...</i>", parse_mode="HTML")
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post("https://api.cobalt.tools/api/json", headers={"Accept": "application/json", "Content-Type": "application/json"}, json={"url": url}, timeout=30.0)
            if res.status_code == 200 and res.json().get("status") in ["stream", "redirect", "success"]:
                await context.bot.send_video(chat_id=chat_id, video=res.json().get("url"), caption=f"🎬 Đã làm sạch! (-{cost} Xu)")
                await msg.delete()
            else: await msg.edit_text("❌ Link không hỗ trợ.")
        except: await msg.edit_text("❌ Lỗi luồng tải.")

# ─── 4. ĐIỀU PHỐI TIN NHẮN (SỬ DỤNG DYNAMIC BILLING) ────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text, uid = update.message.text.strip(), update.message.effective_user.id
    if text == "🛸 MENU DỊCH VỤ TOAN DAAS": return await cmd_start(update, context)
    
    route = json.loads(AgentGemini.chat("Phân loại: 'voice', 'download', 'general'. URL -> 'download'. Lệnh đọc giọng nói -> 'voice'.", text, uid, is_json=True))
    act, data = route.get("action", "general"), route.get("data", text)
    
    size_calc = len(data) if act != 'download' else 0
    can_afford, cost, discount = deduct_dynamic_credit(uid, act if act != 'general' else 'chat', size_calc)
    
    if not can_afford: return await update.message.reply_text(f"❌ <b>HẾT HẠN MỨC!</b> Yêu cầu {cost} Xu (Đã tính chiết khấu VIP).\nGõ /naptien.", parse_mode="HTML")
        
    if act == "voice": await AgentVoice.render(data, uid, context, update.effective_chat.id, cost)
    elif act == "download": await AgentDownloader.download(data, context, update.effective_chat.id, cost)
    else: 
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        reply = AgentGemini.chat('Bạn là Trợ Lý Ảo TOAN DAAS. Trả lời súc tích.', text, uid)
        discount_text = " (Đã áp dụng VIP)" if discount > 0 else ""
        await update.message.reply_text(f"🤖 {reply}\n\n<i>(-{cost} Xu){discount_text}</i>", parse_mode="HTML")

USER_BILL_STATE: dict[int, bool] = {}  # Theo dõi user vừa gõ /naptien hay chưa

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    username = update.effective_user.first_name

    # ── LUỒNG BILL: user vừa dùng /naptien hoặc caption có từ khoá bill/nạp ──
    caption_lower = (update.message.caption or "").lower()
    is_bill_context = USER_BILL_STATE.get(uid, False) or any(k in caption_lower for k in ["bill", "nạp", "chuyển khoản", "ck", "daas"])

    if is_bill_context:
        USER_BILL_STATE.pop(uid, None)  # Reset trạng thái

        # Lưu bill vào DB trạng thái pending
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO pending_deposits (user_id, username, file_id, submitted_at, status) VALUES (?, ?, ?, ?, ?)",
                  (str(uid), username, update.message.photo[-1].file_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "pending"))
        deposit_id = c.lastrowid
        conn.commit()
        conn.close()

        # Chuyển tiếp ảnh + thông tin đầy đủ cho Admin
        admin_caption = (
            f"💸 <b>BILL NẠP TIỀN MỚI #{deposit_id}</b>\n\n"
            f"👤 Khách: <b>{username}</b>\n"
            f"🆔 ID Telegram: <code>{uid}</code>\n"
            f"🕐 Thời gian gửi: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
            f"👉 Duyệt: <code>/duyet {uid} &lt;Số_Xu&gt;</code>\n"
            f"❌ Từ chối: <code>/tuchoi {uid}</code>"
        )
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=update.message.photo[-1].file_id,
                                     caption=admin_caption, parse_mode="HTML")
        await update.message.reply_text(
            f"✅ <b>Đã gửi bill cho Admin!</b>\n\n"
            f"📋 Mã yêu cầu: <b>#{deposit_id}</b>\n"
            f"🆔 ID Telegram của bạn: <code>{uid}</code>\n\n"
            f"⏳ Vui lòng chờ Admin xác nhận (thường trong vài phút). Bạn sẽ nhận thông báo khi được cấp Xu!",
            parse_mode="HTML"
        )
        return

    # ── LUỒNG TÁCH NỀN: ảnh bình thường ──
    file_size = update.message.photo[-1].file_size
    can_afford, cost, _ = deduct_dynamic_credit(uid, 'image', file_size)
    if not can_afford:
        return await update.message.reply_text(
            f"❌ Cần {cost} Xu để bóc nền file {math.ceil(file_size/(1024*1024))}MB. Gõ /naptien.\n"
            f"<i>Nếu bạn muốn gửi bill nạp tiền, hãy thêm caption 'bill' vào ảnh.</i>",
            parse_mode="HTML"
        )

    msg = await update.message.reply_text("⏳ <i>[Studio] Đang xử lý bóc nền...</i>", parse_mode="HTML")
    img_bytes = bytes(await (await update.message.photo[-1].get_file()).download_as_bytearray())
    async with httpx.AsyncClient() as client:
        res = await client.post("https://api.remove.bg/v1.0/removebg", headers={"X-Api-Key": REMOVEBG_API_KEY},
                                files={"image_file": img_bytes}, data={"size": "auto"}, timeout=30.0)
    if res.status_code == 200:
        await context.bot.send_document(chat_id=update.effective_chat.id, document=res.content,
                                        filename="no_bg.png", caption=f"✂️ Tách nền thành công! (-{cost} Xu)")
        await msg.delete()
    else:
        await msg.edit_text("❌ Lỗi API Đồ họa.")

# ─── LỆNH ADMIN DUYỆT BILL ───────────────────────────────────────────────────
async def cmd_duyet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.effective_user.id) != ADMIN_ID:
        return
    try:
        target_id = context.args[0]
        amount = int(context.args[1])
        add_credit(target_id, amount)

        # Cập nhật trạng thái bill trong DB
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE pending_deposits SET status='approved' WHERE user_id=? AND status='pending'", (str(target_id),))
        conn.commit()
        conn.close()

        credits, _, _ = get_user(target_id)
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                f"🎉 <b>NẠP TIỀN THÀNH CÔNG!</b>\n\n"
                f"Admin đã xác nhận và cộng <b>{amount} Xu</b> vào tài khoản.\n"
                f"🪙 Số dư mới: <b>{credits} Xu</b>\n\n"
                f"Cảm ơn bạn đã tin dùng TOAN DAAS! 🙏"
            ),
            parse_mode="HTML"
        )
        await update.message.reply_text(f"✅ Đã duyệt {amount} Xu cho ID: {target_id}")
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ Cú pháp: /duyet <ID> <Số_Xu>")

async def cmd_tuchoi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.effective_user.id) != ADMIN_ID:
        return
    try:
        target_id = context.args[0]
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE pending_deposits SET status='rejected' WHERE user_id=? AND status='pending'", (str(target_id),))
        conn.commit()
        conn.close()
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                f"❌ <b>BILL BỊ TỪ CHỐI</b>\n\n"
                f"Admin không xác nhận được giao dịch của bạn.\n"
                f"Vui lòng kiểm tra lại nội dung chuyển khoản (<code>DAAS {target_id}</code>) và gửi bill rõ hơn.\n"
                f"Liên hệ Admin nếu cần hỗ trợ."
            ),
            parse_mode="HTML"
        )
        await update.message.reply_text(f"✅ Đã từ chối và thông báo cho ID: {target_id}")
    except IndexError:
        await update.message.reply_text("⚠️ Cú pháp: /tuchoi <ID>")

async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin xem danh sách bill đang chờ duyệt"""
    if str(update.effective_user.id) != ADMIN_ID:
        return
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, user_id, username, submitted_at FROM pending_deposits WHERE status='pending' ORDER BY submitted_at DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()
    if not rows:
        return await update.message.reply_text("📭 Không có bill nào đang chờ duyệt.")
    lines = ["📋 <b>DANH SÁCH BILL CHỜ DUYỆT:</b>\n"]
    for r in rows:
        lines.append(f"• #{r[0]} | 👤 {r[2]} | 🆔 <code>{r[1]}</code> | 🕐 {r[3]}\n  ➔ <code>/duyet {r[1]} &lt;Xu&gt;</code>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Xử lý cả Voice (Ghi âm) và Audio (File âm thanh tải lên) bằng Deepgram
    file_obj = update.message.voice or update.message.audio
    file_size = file_obj.file_size
    
    can_afford, cost, discount = deduct_dynamic_credit(update.effective_user.id, 'whisper', file_size)
    if not can_afford: return await update.message.reply_text(f"❌ Cần {cost} Xu để bóc băng file {math.ceil(file_size/(1024*1024))}MB. Gõ /naptien.")
    
    msg = await update.message.reply_text("⚡ <i>[Deepgram AI] Đang chạy bóc băng...</i>", parse_mode="HTML")
    file_bytes = bytes(await (await file_obj.get_file()).download_as_bytearray())
    
    txt = await AgentDeepgram.transcribe(file_bytes, context)
    await msg.delete()
    if not txt.startswith("❌"):
        discount_text = " (Áp dụng VIP)" if discount > 0 else ""
        await update.message.reply_text(f"🗣️ <i>\"{txt}\"</i>\n\n<i>(-{cost} Xu){discount_text}</i>", parse_mode="HTML")
        if update.message.voice: # Nếu là tin nhắn thoại, đẩy tiếp vào chat AI
            update.message.text = txt
            await handle_message(update, context)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    get_user(update.effective_user.id, update.effective_user.first_name) 
    text = (
        "👑 <b>HỆ SINH THÁI AI — TOAN DAAS V14.0 (DYNAMIC PRICING)</b>\n\n"
        "Chào mừng bạn! Hệ thống sử dụng công nghệ thanh toán thông minh dựa trên dung lượng (MB) và ký tự bạn sử dụng.\n\n"
        "🛠️ <b>CÁCH RA LỆNH CHO HỆ THỐNG:</b>\n"
        "<b>1. Trợ Lý AI Chat:</b> Nhắn tin bình thường (Tính phí theo độ dài chữ).\n"
        "<b>2. Máy Bóc Băng Audio:</b> Gửi tin nhắn thoại 🎤 hoặc tải file `.mp3`, `.m4a` lên (Tính phí theo MB).\n"
        "<b>3. Hút Video Sạch:</b> Gửi link video TikTok/YT/FB.\n"
        "<b>4. Studio Tách Nền:</b> Gửi ảnh để tách nền xuyên thấu (Tính phí theo MB).\n"
        "<b>5. Đọc Voice:</b> Cú pháp 'Đọc voice: (nội dung)' (Tính phí theo độ dài).\n\n"
        "💡 <b>Lệnh hệ thống:</b>\n"
        "• /profile - Xem Hạng VIP và Số dư\n"
        "• /naptien - Nạp thêm hạn mức\n"
        "• /gopy (nội dung) - Báo lỗi/Đề xuất tính năng"
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
    app.add_handler(CommandHandler("duyet", cmd_duyet))       # Admin duyệt bill
    app.add_handler(CommandHandler("tuchoi", cmd_tuchoi))     # Admin từ chối bill
    app.add_handler(CommandHandler("pending", cmd_pending))   # Admin xem bill chờ duyệt
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO | filters.Document.AUDIO, handle_media))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("🚀 LÕI BILLING V14.1 DYNAMIC + BILL FLOW ONLINE...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()