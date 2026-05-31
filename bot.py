"""
╔══════════════════════════════════════════════════════════════════╗
║   TOAN DAAS V15.0 - PRODUCTION READY                            ║
║   FastAPI + Telegram Bot (Shared Event Loop via Lifespan)        ║
║   Dynamic Billing | Deepgram | Auto-Tiers | HMAC Webhook Ready  ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import logging
import asyncio
import edge_tts
import json
import sqlite3
import httpx
import math
import hmac
import hashlib
import uvicorn
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from google import genai
from google.genai import types
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

# ─── LOGGING ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("TOAN_DAAS")

# ─── BIẾN MÔI TRƯỜNG ─────────────────────────────────────────────────────────
# .strip() loại bỏ \n, \r, space thừa do copy-paste vào Railway
def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()

TELEGRAM_TOKEN   = _env("TELEGRAM_TOKEN") or _env("BOT_TOKEN")
ADMIN_ID         = _env("ADMIN_ID", "7126457028")
REMOVEBG_API_KEY = _env("REMOVEBG_API_KEY")
FISH_AUDIO_KEY   = _env("FISH_AUDIO_KEY")
GEMINI_API_KEY   = _env("GEMINI_API_KEY")
DEEPGRAM_API_KEY = _env("DEEPGRAM_API_KEY")
PAYOS_CHECKSUM_KEY = _env("PAYOS_CHECKSUM_KEY")
PORT             = int(_env("PORT", "8000"))

# ─── GEMINI CLIENT ────────────────────────────────────────────────────────────
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
user_memory: dict = {}

# ─── DATABASE ─────────────────────────────────────────────────────────────────
DB_FILE       = "toandaas_system.db"
TRIAL_CREDITS = 200

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        username TEXT,
        credits INTEGER DEFAULT 0,
        is_vip INTEGER DEFAULT 0,
        join_date TEXT,
        total_spent INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT, username TEXT, content TEXT, timestamp DATETIME
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS pending_deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT, username TEXT, file_id TEXT,
        submitted_at DATETIME, status TEXT DEFAULT 'pending'
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT, action TEXT, cost INTEGER,
        discount_rate REAL, created_at DATETIME
    )""")
    # Migration an toàn: thêm cột nếu thiếu
    for col, defval in [("total_spent","0"), ("is_vip","0")]:
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} INTEGER DEFAULT {defval}")
        except Exception:
            pass
    conn.commit()
    conn.close()

def get_user(user_id, username="Unknown"):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT credits, total_spent, is_vip FROM users WHERE user_id=?", (str(user_id),))
    row = c.fetchone()
    if not row:
        c.execute(
            "INSERT INTO users (user_id, username, credits, is_vip, join_date, total_spent) VALUES (?,?,?,?,?,?)",
            (str(user_id), username, TRIAL_CREDITS, 0, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 0)
        )
        conn.commit()
        row = (TRIAL_CREDITS, 0, 0)
    conn.close()
    return row[0], row[1], row[2]  # credits, total_spent, is_vip

def add_credit(user_id, amount):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET credits = credits + ? WHERE user_id=?", (amount, str(user_id)))
    conn.commit()
    conn.close()

def calculate_dynamic_cost(action_type, size_or_length):
    if action_type == "chat":
        return 2 + math.ceil(size_or_length / 500) * 1
    elif action_type == "whisper":
        return 5 + math.ceil(size_or_length / (1024 * 1024)) * 10
    elif action_type == "image":
        return 40 + math.ceil(size_or_length / (1024 * 1024)) * 5
    elif action_type == "voice":
        return 10 + math.ceil(size_or_length / 50) * 5
    elif action_type == "download":
        return 5
    return 2

def apply_discount(total_spent, raw_cost):
    if total_spent >= 20000:
        discount = 0.20
    elif total_spent >= 5000:
        discount = 0.10
    else:
        discount = 0.0
    return math.ceil(raw_cost * (1 - discount)), discount

def deduct_dynamic_credit(user_id, action_type, size_or_length) -> tuple:
    if str(user_id) == ADMIN_ID:
        return True, 0, 1.0
    credits, total_spent, is_vip = get_user(user_id)
    if is_vip == 1:
        return True, 0, 1.0
    raw_cost  = calculate_dynamic_cost(action_type, size_or_length)
    final_cost, discount_rate = apply_discount(total_spent, raw_cost)
    if credits >= final_cost:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            "UPDATE users SET credits = credits - ?, total_spent = total_spent + ? WHERE user_id=?",
            (final_cost, final_cost, str(user_id))
        )
        c.execute(
            "INSERT INTO transactions (user_id, action, cost, discount_rate, created_at) VALUES (?,?,?,?,?)",
            (str(user_id), action_type, final_cost, discount_rate, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        conn.close()
        return True, final_cost, discount_rate
    return False, final_cost, discount_rate

# ─── ADMIN ALERT ─────────────────────────────────────────────────────────────
async def alert_admin(context: ContextTypes.DEFAULT_TYPE, service_name: str, error_msg: str):
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🚨 <b>BÁO ĐỘNG TOAN DAAS</b>\n\n{service_name} lỗi:\n<code>{error_msg}</code>",
            parse_mode="HTML"
        )
    except Exception:
        pass

# ─── AI AGENTS ───────────────────────────────────────────────────────────────
class AgentRouter(BaseModel):
    action: str = Field(description="voice, code, content, image, download, general")
    data:   str = Field(description="Từ khóa hoặc URL")

class AgentGemini:
    @staticmethod
    def chat(prompt: str, text: str, uid, is_json: bool = False) -> str:
        if not gemini_client:
            return "❌ Chưa cấu hình GEMINI_API_KEY."
        if uid not in user_memory:
            user_memory[uid] = []
        user_memory[uid].append(types.Content(role="user", parts=[types.Part(text=text)]))
        if len(user_memory[uid]) > 10:
            user_memory[uid] = user_memory[uid][-10:]
        cfg = {
            "system_instruction": prompt,
            "response_mime_type": "application/json" if is_json else "text/plain"
        }
        if is_json:
            cfg["response_schema"] = AgentRouter
        try:
            res = gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                config=types.GenerateContentConfig(**cfg),
                contents=user_memory[uid] if not is_json else text
            )
            if not is_json:
                user_memory[uid].append(
                    types.Content(role="model", parts=[types.Part(text=res.text)])
                )
            return res.text
        except Exception as e:
            logger.error(f"Gemini error: {e}")
            return "Lỗi hệ thống Gemini."

class AgentDeepgram:
    @staticmethod
    async def transcribe(file_bytes: bytes, context: ContextTypes.DEFAULT_TYPE) -> str:
        if not DEEPGRAM_API_KEY:
            return "❌ Chưa cấu hình DEEPGRAM_API_KEY."
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    "https://api.deepgram.com/v1/listen?model=nova-2&language=vi&smart_format=true",
                    headers={
                        "Authorization": f"Token {DEEPGRAM_API_KEY}",
                        "Content-Type": "audio/mpeg"
                    },
                    content=file_bytes,
                    timeout=60.0
                )
            if res.status_code == 200:
                return (
                    res.json()
                    .get("results", {})
                    .get("channels", [{}])[0]
                    .get("alternatives", [{}])[0]
                    .get("transcript", "Không nhận diện được lời nói.")
                )
            await alert_admin(context, "Deepgram", f"HTTP {res.status_code}")
            return "❌ Cổng bóc băng lỗi."
        except Exception as e:
            return f"❌ Lỗi: {str(e)}"

class AgentVoice:
    @staticmethod
    async def render(text: str, user_id, context: ContextTypes.DEFAULT_TYPE, chat_id: int, cost: int) -> bool:
        """Trả về True = Fish Audio (tính phí), False = Edge TTS (hoàn xu)."""
        out = f"v_{user_id}.mp3"
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text="⏳ <i>[Giọng Nói] Đang tổng hợp...</i>",
            parse_mode="HTML"
        )
        used_fish = False
        try:
            if FISH_AUDIO_KEY:
                async with httpx.AsyncClient() as client:
                    res = await client.post(
                        "https://api.fish.audio/v1/tts",
                        headers={
                            "Authorization": f"Bearer {FISH_AUDIO_KEY}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "text": text,
                            "reference_id": "7f0955e88846433e9ecb241357608bf8",
                            "format": "mp3"
                        },
                        timeout=30.0
                    )
                if res.status_code == 200:
                    with open(out, "wb") as f:
                        f.write(res.content)
                    used_fish = True
            if not used_fish:
                communicate = edge_tts.Communicate(text, "vi-VN-NamMinhNeural")
                await communicate.save(out)
            with open(out, "rb") as f:
                if used_fish:
                    caption = f"🎙️ Fish Audio — Giọng nhân bản! (-{cost} Xu)"
                else:
                    caption = "🔊 Edge TTS — Giọng chuẩn! (Miễn phí 0 Xu)"
                await context.bot.send_audio(chat_id=chat_id, audio=f, caption=caption)
            await msg.delete()
        except Exception as e:
            logger.error(f"Voice error: {e}")
            await msg.edit_text("❌ Lỗi Voice.")
        finally:
            if os.path.exists(out):
                os.remove(out)
        return used_fish

class AgentDownloader:
    @staticmethod
    async def download(url: str, context: ContextTypes.DEFAULT_TYPE, chat_id: int, cost: int):
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text="⏳ <i>Đang bóc tách video...</i>",
            parse_mode="HTML"
        )
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    "https://api.cobalt.tools/api/json",
                    headers={"Accept": "application/json", "Content-Type": "application/json"},
                    json={"url": url},
                    timeout=30.0
                )
            data = res.json()
            if res.status_code == 200 and data.get("status") in ["stream", "redirect", "success"]:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=data.get("url"),
                    caption=f"🎬 Đã làm sạch! (-{cost} Xu)"
                )
                await msg.delete()
            else:
                await msg.edit_text("❌ Link không hỗ trợ hoặc dịch vụ tải đang bảo trì.")
        except Exception as e:
            logger.error(f"Downloader error: {e}")
            await msg.edit_text("❌ Lỗi luồng tải.")

# ─── STATE: THEO DÕI USER VỪA GỬI /naptien ──────────────────────────────────
USER_BILL_STATE: dict = {}

# ─── HANDLERS ────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    get_user(update.effective_user.id, update.effective_user.first_name)
    text = (
        "👑 <b>HỆ SINH THÁI AI — TOAN DAAS V15.0</b>\n\n"
        "Chào mừng! Hệ thống tính phí thông minh theo dung lượng thực tế.\n\n"
        "🛠️ <b>CÁCH SỬ DỤNG:</b>\n"
        "<b>1. Chat AI:</b> Nhắn tin bình thường (tính theo độ dài chữ).\n"
        "<b>2. Bóc băng Audio:</b> Gửi tin nhắn thoại 🎤 hoặc file .mp3/.m4a (tính theo MB).\n"
        "<b>3. Tải Video Sạch:</b> Gửi link TikTok / YouTube / Facebook.\n"
        "<b>4. Tách Nền Ảnh:</b> Gửi ảnh bất kỳ (tính theo MB).\n"
        "<b>5. Đọc Voice:</b> Nhập 'Đọc voice: (nội dung)' (tính theo ký tự).\n\n"
        "💡 <b>Lệnh hệ thống:</b>\n"
        "• /profile — Xem Hạng VIP & Số dư\n"
        "• /naptien — Nạp thêm hạn mức\n"
        "• /gopy &lt;nội dung&gt; — Góp ý / báo lỗi"
    )
    await update.message.reply_text(
        text, parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("🛸 MENU DỊCH VỤ TOAN DAAS")]],
            resize_keyboard=True
        )
    )

async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    credits, total_spent, is_vip = get_user(user_id, update.effective_user.first_name)
    if user_id == ADMIN_ID:
        tier = "👑 ADMIN (Miễn phí 100%)"
    elif is_vip == 1:
        tier = "💎 VIP (Miễn phí 100%)"
    elif total_spent >= 20000:
        tier = "🥇 VÀNG (Giảm 20%)"
    elif total_spent >= 5000:
        tier = "🥈 BẠC (Giảm 10%)"
    else:
        tier = "🥉 Tiêu Chuẩn"
    credit_display = "Vô Hạn (∞)" if user_id == ADMIN_ID or is_vip else f"{credits} Xu"
    msg = (
        f"👤 <b>HỒ SƠ TÀI KHOẢN</b>\n\n"
        f"• ID: <code>{user_id}</code>\n"
        f"• Hạng: <b>{tier}</b>\n"
        f"• Số dư: <b>{credit_display}</b>\n"
        f"• Tổng chi tiêu: {total_spent} Xu\n\n"
        f"👉 /naptien để mua thêm hạn mức."
    )
    await update.message.reply_text(msg, parse_mode="HTML")

async def cmd_naptien(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    credits, _, _ = get_user(uid, update.effective_user.first_name)
    msg = (
        f"💳 <b>NẠP SỐ DƯ — TOAN DAAS</b>\n\n"
        f"👤 ID Telegram: <code>{uid}</code>\n"
        f"🪙 Số dư: <b>{credits} Xu</b>\n\n"
        f"<b>🛒 BẢNG GIÁ (1 Xu = 100đ):</b>\n"
        f"• Gói Cà Phê: 50.000đ ➔ <b>500 Xu</b>\n"
        f"• Gói Tiêu Chuẩn: 100.000đ ➔ <b>1.050 Xu</b>\n"
        f"• Gói Doanh Nghiệp: 500.000đ ➔ <b>6.000 Xu</b>\n\n"
        f"<b>🏦 CHUYỂN KHOẢN:</b>\n"
        f"- Ngân hàng: <b>ACB</b>\n"
        f"- STK: <b>8899397968</b> (NGUYEN MANH TOAN)\n"
        f"- Nội dung BẮT BUỘC: <code>DAAS {uid}</code>\n\n"
        f"<b>📋 QUY TRÌNH 3 BƯỚC:</b>\n"
        f"1️⃣ Chuyển khoản với nội dung <code>DAAS {uid}</code>\n"
        f"2️⃣ Chụp màn hình bill ngân hàng\n"
        f"3️⃣ Gửi ảnh bill vào đây → Bot tự báo Admin duyệt!\n\n"
        f"⚠️ <i>Không ghi sai nội dung — Admin sẽ không thể xác nhận.</i>"
    )
    qr_url = (
        f"https://img.vietqr.io/image/ACB-8899397968-compact.png"
        f"?amount=&addInfo=DAAS+{uid}&accountName=NGUYEN+MANH+TOAN"
    )
    USER_BILL_STATE[uid] = True
    await update.message.reply_photo(photo=qr_url, caption=msg, parse_mode="HTML")

async def cmd_gopy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = " ".join(context.args)
    if not content:
        return await update.message.reply_text(
            "⚠️ VD: <code>/gopy Thêm thanh toán Momo đi bot</code>", parse_mode="HTML"
        )
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO feedback (user_id, username, content, timestamp) VALUES (?,?,?,?)",
        (str(update.effective_user.id), update.effective_user.first_name,
         content, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ <b>Cảm ơn!</b> Góp ý đã được ghi nhận.", parse_mode="HTML")

# ─── ADMIN COMMANDS ───────────────────────────────────────────────────────────
async def cmd_admin_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    try:
        target_id, amount = context.args[0], int(context.args[1])
        add_credit(target_id, amount)
        credits, _, _ = get_user(target_id)
        await update.message.reply_text(f"✅ Đã bơm {amount} Xu cho ID {target_id}. Số dư mới: {credits} Xu")
    except Exception:
        await update.message.reply_text("⚠️ Cú pháp: /add <ID> <Số_Xu>")

async def cmd_admin_gopy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT username, content FROM feedback WHERE timestamp >= ?",
        ((datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"),)
    )
    rows = c.fetchall()
    conn.close()
    if not rows:
        return await update.message.reply_text("📭 Hòm thư 7 ngày qua trống.")
    summary = AgentGemini.chat(
        "Tóm tắt yêu cầu khách hàng cực ngắn gọn:",
        "\n".join([f"- {r[0]}: {r[1]}" for r in rows]),
        ADMIN_ID
    )
    await update.message.reply_text(
        f"📊 <b>BÁO CÁO GÓP Ý (7 NGÀY)</b>\n\n{summary}", parse_mode="HTML"
    )

async def cmd_duyet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    try:
        target_id, amount = context.args[0], int(context.args[1])
        add_credit(target_id, amount)
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            "UPDATE pending_deposits SET status='approved' WHERE user_id=? AND status='pending'",
            (str(target_id),)
        )
        conn.commit()
        conn.close()
        credits, _, _ = get_user(target_id)
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                f"🎉 <b>NẠP TIỀN THÀNH CÔNG!</b>\n\n"
                f"Admin đã xác nhận +<b>{amount} Xu</b>.\n"
                f"🪙 Số dư mới: <b>{credits} Xu</b>\n\n"
                f"Cảm ơn bạn đã tin dùng TOAN DAAS! 🙏"
            ),
            parse_mode="HTML"
        )
        await update.message.reply_text(f"✅ Đã duyệt {amount} Xu cho ID: {target_id}")
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ Cú pháp: /duyet <ID> <Số_Xu>")

async def cmd_tuchoi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    try:
        target_id = context.args[0]
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            "UPDATE pending_deposits SET status='rejected' WHERE user_id=? AND status='pending'",
            (str(target_id),)
        )
        conn.commit()
        conn.close()
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                f"❌ <b>BILL BỊ TỪ CHỐI</b>\n\n"
                f"Admin không xác nhận được giao dịch.\n"
                f"Kiểm tra lại nội dung: <code>DAAS {target_id}</code>\n"
                f"Gửi bill rõ hơn hoặc liên hệ Admin."
            ),
            parse_mode="HTML"
        )
        await update.message.reply_text(f"✅ Đã từ chối và thông báo ID: {target_id}")
    except IndexError:
        await update.message.reply_text("⚠️ Cú pháp: /tuchoi <ID>")

async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "SELECT id, user_id, username, submitted_at FROM pending_deposits "
        "WHERE status='pending' ORDER BY submitted_at DESC LIMIT 10"
    )
    rows = c.fetchall()
    conn.close()
    if not rows:
        return await update.message.reply_text("📭 Không có bill nào đang chờ.")
    lines = ["📋 <b>BILL CHỜ DUYỆT:</b>\n"]
    for r in rows:
        lines.append(
            f"• #{r[0]} | {r[2]} | <code>{r[1]}</code> | {r[3]}\n"
            f"  ➔ <code>/duyet {r[1]} &lt;Xu&gt;</code>"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: thống kê nhanh hệ thống"""
    if str(update.effective_user.id) != ADMIN_ID:
        return
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM transactions WHERE created_at >= ?",
              ((datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),))
    tx_today = c.fetchone()[0]
    c.execute("SELECT SUM(cost) FROM transactions WHERE created_at >= ?",
              ((datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),))
    revenue_today = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM pending_deposits WHERE status='pending'")
    pending = c.fetchone()[0]
    conn.close()
    await update.message.reply_text(
        f"📊 <b>THỐNG KÊ HỆ THỐNG</b>\n\n"
        f"👥 Tổng user: <b>{total_users}</b>\n"
        f"⚡ Giao dịch hôm nay: <b>{tx_today}</b>\n"
        f"💰 Xu tiêu hôm nay: <b>{revenue_today}</b>\n"
        f"📋 Bill chờ duyệt: <b>{pending}</b>",
        parse_mode="HTML"
    )

async def cmd_setvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: bật/tắt VIP cho user"""
    if str(update.effective_user.id) != ADMIN_ID:
        return
    try:
        target_id = context.args[0]
        flag = int(context.args[1])  # 1 = VIP, 0 = thường
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET is_vip=? WHERE user_id=?", (flag, str(target_id)))
        conn.commit()
        conn.close()
        label = "VIP ✅" if flag == 1 else "Tiêu Chuẩn"
        await update.message.reply_text(f"✅ ID {target_id} → Hạng: {label}")
        await context.bot.send_message(
            chat_id=target_id,
            text=f"🎖️ Tài khoản của bạn đã được nâng lên hạng <b>{'VIP 💎' if flag else 'Tiêu Chuẩn'}</b>.",
            parse_mode="HTML"
        )
    except Exception:
        await update.message.reply_text("⚠️ Cú pháp: /setvip <ID> <1|0>")

# ─── MESSAGE HANDLERS ─────────────────────────────────────────────────────────
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    username = update.effective_user.first_name
    caption_lower = (update.message.caption or "").lower()
    is_bill = USER_BILL_STATE.get(uid, False) or any(
        k in caption_lower for k in ["bill", "nạp", "chuyển khoản", "ck", "daas"]
    )

    if is_bill:
        USER_BILL_STATE.pop(uid, None)
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            "INSERT INTO pending_deposits (user_id, username, file_id, submitted_at, status) VALUES (?,?,?,?,?)",
            (str(uid), username, update.message.photo[-1].file_id,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "pending")
        )
        deposit_id = c.lastrowid
        conn.commit()
        conn.close()
        admin_caption = (
            f"💸 <b>BILL MỚI #{deposit_id}</b>\n\n"
            f"👤 Khách: <b>{username}</b>\n"
            f"🆔 ID: <code>{uid}</code>\n"
            f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
            f"👉 Duyệt: <code>/duyet {uid} &lt;Số_Xu&gt;</code>\n"
            f"❌ Từ chối: <code>/tuchoi {uid}</code>"
        )
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=update.message.photo[-1].file_id,
            caption=admin_caption,
            parse_mode="HTML"
        )
        await update.message.reply_text(
            f"✅ <b>Đã gửi bill cho Admin!</b>\n\n"
            f"📋 Mã: <b>#{deposit_id}</b>\n"
            f"🆔 ID của bạn: <code>{uid}</code>\n\n"
            f"⏳ Vui lòng chờ Admin xác nhận.",
            parse_mode="HTML"
        )
        return

    # ── Tách nền ──
    if not REMOVEBG_API_KEY:
        return await update.message.reply_text("❌ Dịch vụ tách nền chưa được cấu hình.")
    file_size = update.message.photo[-1].file_size
    can_afford, cost, _ = deduct_dynamic_credit(uid, "image", file_size)
    if not can_afford:
        return await update.message.reply_text(
            f"❌ Cần {cost} Xu để xử lý ảnh {math.ceil(file_size/(1024*1024))}MB.\n"
            f"<i>Nếu muốn gửi bill, thêm caption 'bill' vào ảnh.</i>",
            parse_mode="HTML"
        )
    msg = await update.message.reply_text("⏳ <i>[Studio] Đang xử lý tách nền...</i>", parse_mode="HTML")
    img_bytes = bytes(await (await update.message.photo[-1].get_file()).download_as_bytearray())
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://api.remove.bg/v1.0/removebg",
            headers={"X-Api-Key": REMOVEBG_API_KEY},
            files={"image_file": img_bytes},
            data={"size": "auto"},
            timeout=30.0
        )
    if res.status_code == 200:
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=res.content,
            filename="no_bg.png",
            caption=f"✂️ Tách nền thành công! (-{cost} Xu)"
        )
        await msg.delete()
    else:
        await msg.edit_text("❌ Lỗi API tách nền.")

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_obj = update.message.voice or update.message.audio
    if not file_obj:
        return
    file_size = file_obj.file_size
    can_afford, cost, discount = deduct_dynamic_credit(update.effective_user.id, "whisper", file_size)
    if not can_afford:
        return await update.message.reply_text(
            f"❌ Cần {cost} Xu để bóc băng file {math.ceil(file_size/(1024*1024))}MB. Gõ /naptien."
        )
    msg = await update.message.reply_text("⚡ <i>[Deepgram] Đang chạy bóc băng...</i>", parse_mode="HTML")
    file_bytes = bytes(await (await file_obj.get_file()).download_as_bytearray())
    txt = await AgentDeepgram.transcribe(file_bytes, context)
    await msg.delete()
    if not txt.startswith("❌"):
        discount_text = " (VIP)" if discount > 0 else ""
        await update.message.reply_text(
            f"🗣️ <i>\"{txt}\"</i>\n\n<i>(-{cost} Xu){discount_text}</i>",
            parse_mode="HTML"
        )
        if update.message.voice:
            update.message.text = txt
            await handle_message(update, context)
    else:
        await update.message.reply_text(txt)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    uid  = update.effective_user.id

    if text == "🛸 MENU DỊCH VỤ TOAN DAAS":
        return await cmd_start(update, context)

    if not gemini_client:
        return await update.message.reply_text("❌ Hệ thống AI chưa sẵn sàng (thiếu GEMINI_API_KEY).")

    try:
        route_raw = AgentGemini.chat(
            "Phân loại: 'voice' (đọc văn bản), 'download' (URL video), 'general' (còn lại). Trả về JSON.",
            text, uid, is_json=True
        )
        route = json.loads(route_raw)
    except Exception:
        route = {"action": "general", "data": text}

    act  = route.get("action", "general")
    data = route.get("data", text)
    size_calc = len(data) if act != "download" else 0
    action_key = act if act in ("voice", "download") else "chat"

    can_afford, cost, discount = deduct_dynamic_credit(uid, action_key, size_calc)
    if not can_afford:
        return await update.message.reply_text(
            f"❌ <b>HẾT HẠN MỨC!</b> Yêu cầu {cost} Xu.\nGõ /naptien để nạp thêm.",
            parse_mode="HTML"
        )

    if act == "voice":
        used_fish = await AgentVoice.render(data, uid, context, update.effective_chat.id, cost)
        # Nếu fallback Edge TTS (miễn phí) → hoàn xu đã trừ
        if not used_fish and cost > 0 and str(uid) != ADMIN_ID:
            add_credit(uid, cost)
    elif act == "download":
        await AgentDownloader.download(data, context, update.effective_chat.id, cost)
    else:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        reply = AgentGemini.chat(
            "Bạn là Trợ Lý Ảo TOAN DAAS. Trả lời súc tích, thân thiện.",
            text, uid
        )
        discount_text = " (Đã áp dụng VIP)" if discount > 0 else ""
        await update.message.reply_text(
            f"🤖 {reply}\n\n<i>(-{cost} Xu){discount_text}</i>",
            parse_mode="HTML"
        )

# ─── FASTAPI + LIFESPAN (GIẢI QUYẾT EVENT LOOP CONFLICT) ─────────────────────
tg_app: Application = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Khởi động Telegram bot cùng vòng lặp sự kiện của FastAPI"""
    global tg_app
    init_db()
    if not TELEGRAM_TOKEN:
        logger.error("❌ TELEGRAM_TOKEN chưa được set!")
        yield
        return

    tg_app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Đăng ký handlers
    tg_app.add_handler(CommandHandler("start",       cmd_start))
    tg_app.add_handler(CommandHandler("profile",     cmd_profile))
    tg_app.add_handler(CommandHandler("naptien",     cmd_naptien))
    tg_app.add_handler(CommandHandler("gopy",        cmd_gopy))
    tg_app.add_handler(CommandHandler("add",         cmd_admin_add))
    tg_app.add_handler(CommandHandler("admin_gopy",  cmd_admin_gopy))
    tg_app.add_handler(CommandHandler("duyet",       cmd_duyet))
    tg_app.add_handler(CommandHandler("tuchoi",      cmd_tuchoi))
    tg_app.add_handler(CommandHandler("pending",     cmd_pending))
    tg_app.add_handler(CommandHandler("stats",       cmd_stats))
    tg_app.add_handler(CommandHandler("setvip",      cmd_setvip))
    tg_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    tg_app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_media))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await tg_app.initialize()
    await tg_app.start()
    # Chạy polling trong background task (không block event loop)
    asyncio.create_task(tg_app.updater.start_polling(allowed_updates=Update.ALL_TYPES))
    logger.info("🚀 TOAN DAAS V15.0 ONLINE — Bot + API đang chạy.")
    yield
    # Graceful shutdown
    await tg_app.updater.stop()
    await tg_app.stop()
    await tg_app.shutdown()
    logger.info("🛑 Bot đã dừng an toàn.")

fastapi_app = FastAPI(title="TOAN DAAS V15.0", lifespan=lifespan)

# ─── HEALTH CHECK (Railway dùng để kiểm tra container còn sống) ───────────────
@fastapi_app.get("/")
async def health():
    return {"status": "ok", "service": "TOAN DAAS V15.0"}

# ─── WEBHOOK PAYOS (TUỲ CHỌN — BẬT KHI CÓ PAYOS_CHECKSUM_KEY) ───────────────
def verify_payos_signature(data: dict, received_sig: str) -> bool:
    """Xác thực chữ ký HMAC-SHA256 từ payOS"""
    if not PAYOS_CHECKSUM_KEY:
        return False
    sorted_keys = sorted(data.keys())
    raw_str = "&".join(f"{k}={data[k]}" for k in sorted_keys)
    computed = hmac.new(
        PAYOS_CHECKSUM_KEY.encode("utf-8"),
        raw_str.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed, received_sig)

@fastapi_app.post("/webhook/payos")
async def webhook_payos(request: Request):
    body = await request.json()
    sig  = body.get("signature", "")
    data = body.get("data", {})

    if PAYOS_CHECKSUM_KEY and not verify_payos_signature(data, sig):
        raise HTTPException(status_code=400, detail="Invalid signature")

    if body.get("success") and data.get("description", ""):
        desc = data["description"].upper()
        # Tìm pattern "DAAS <user_id>" trong nội dung chuyển khoản
        parts = desc.split()
        for i, p in enumerate(parts):
            if p == "DAAS" and i + 1 < len(parts):
                target_id = parts[i + 1]
                amount_vnd = int(data.get("amount", 0))
                xu = math.floor(amount_vnd / 100)  # 100đ = 1 Xu
                if xu > 0:
                    add_credit(target_id, xu)
                    logger.info(f"✅ Auto nạp {xu} Xu cho {target_id} (payOS)")
                    if tg_app:
                        try:
                            await tg_app.bot.send_message(
                                chat_id=target_id,
                                text=(
                                    f"🎉 <b>NẠP TỰ ĐỘNG THÀNH CÔNG!</b>\n\n"
                                    f"payOS xác nhận +<b>{xu} Xu</b>.\n"
                                    f"💰 Số tiền: {amount_vnd:,}đ\n\n"
                                    f"Cảm ơn bạn đã tin dùng TOAN DAAS! 🙏"
                                ),
                                parse_mode="HTML"
                            )
                        except Exception as e:
                            logger.error(f"Notify user error: {e}")
                break
    return JSONResponse({"code": "00", "desc": "success"})

# ─── ENTRY POINT ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "bot:fastapi_app",
        host="0.0.0.0",
        port=PORT,
        log_level="info"
    )
