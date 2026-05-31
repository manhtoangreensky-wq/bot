"""
╔══════════════════════════════════════════════════════════════════╗
║   TOAN DAAS V15.2 - DYNAMIC QR READY                             ║
║   FastAPI + Telegram Bot (Shared Event Loop via Lifespan)        ║
║   Dynamic Billing | Deepgram | Auto-Tiers | PayOS Dynamic QR     ║
║   Cutout Fallback | OpenAI Fallback | Full Env Vars              ║
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
import time
import random
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from google import genai
from google.genai import types
from openai import OpenAI
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
def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()

TELEGRAM_TOKEN      = _env("TELEGRAM_TOKEN") or _env("BOT_TOKEN")
ADMIN_ID            = _env("ADMIN_ID", "7126457028")

# AI Providers
GEMINI_API_KEY      = _env("GEMINI_API_KEY")
OPENAI_API_KEY      = _env("OPENAI_API_KEY")

# Audio
DEEPGRAM_API_KEY    = _env("DEEPGRAM_API_KEY")
DEEPL_API_KEY       = _env("DEEPL_API_KEY")
FISH_AUDIO_KEY      = _env("FISH_AUDIO_KEY")

# Image
REMOVEBG_API_KEY    = _env("REMOVEBG_API_KEY")
CUTOUT_API_KEY      = _env("CUTOUT_API_KEY")

# Payment
PAYOS_CLIENT_ID     = _env("PAYOS_CLIENT_ID")
PAYOS_API_KEY       = _env("PAYOS_API_KEY")
PAYOS_CHECKSUM_KEY  = _env("PAYOS_CHECKSUM_KEY")

# Misc
RAPIDAPI_KEY        = _env("RAPIDAPI_KEY")
RAPIDAPI_HOST       = _env("RAPIDAPI_HOST")
PORT                = int(_env("PORT", "8000"))
BOT_USERNAME        = _env("BOT_USERNAME", "Httdhtoan")
PUBLIC_BASE_URL     = _env("PUBLIC_BASE_URL")
LEAD_WEBHOOK_SECRET = _env("LEAD_WEBHOOK_SECRET")

# ─── AI CLIENTS ───────────────────────────────────────────────────────────────
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
user_memory: dict = {}

# ─── DANH SÁCH GÓI CƯỚC NẠP ────────────────────────────────────────────────────
PAYMENT_PACKAGES = {
    "10k":  {"amount":  10000, "xu":  100,  "text": "Gói Dùng Thử: 10.000đ ➔ 100 Xu"},
    "20k":  {"amount":  20000, "xu":  200,  "text": "Gói Nhỏ: 20.000đ ➔ 200 Xu"},
    "50k":  {"amount":  50000, "xu":  500,  "text": "Gói Trung: 50.000đ ➔ 500 Xu"},
    "100k": {"amount": 100000, "xu": 1050,  "text": "Gói Tiêu Chuẩn: 100.000đ ➔ 1.050 Xu (Tặng 50 Xu)"},
    "200k": {"amount": 200000, "xu": 2150,  "text": "Gói Nâng Cao: 200.000đ ➔ 2.150 Xu (Tặng 150 Xu)"},
    "500k": {"amount": 500000, "xu": 5500,  "text": "Gói Doanh Nghiệp: 500.000đ ➔ 5.500 Xu (Tặng 500 Xu)"}
}

# ─── DATABASE ─────────────────────────────────────────────────────────────────
DB_FILE           = "toandaas_system.db"
TRIAL_CREDITS     = 150
ORDER_TTL_MINUTES  = 30
REFERRAL_BONUS_XU  = 20

PAYOS_STATUS_PENDING   = "PENDING"
PAYOS_STATUS_PAID      = "PAID"
PAYOS_STATUS_EXPIRED   = "EXPIRED"
PAYOS_STATUS_CANCELLED = "CANCELLED"

# ─── FREE CHAT CONFIG ─────────────────────────────────────────────────────────
FREE_CHAT_DAILY   = 20   # lượt chat/ngày cho tài khoản chưa nạp tiền

# ─── PLACEHOLDER: AI KEYS CAO CẤP (bỏ comment khi sẵn sàng) ──────────────────
# Bước 1: Thêm biến môi trường tương ứng trên server/render/railway
# Bước 2: Bỏ comment dòng cần dùng bên dưới
# OPENAI_PRO_KEY  = _env("OPENAI_PRO_KEY")   # GPT-4o Pro  — https://platform.openai.com
# GEMINI_PRO_KEY  = _env("GEMINI_PRO_KEY")   # Gemini 1.5 Pro/Ultra
# CLAUDE_KEY      = _env("CLAUDE_API_KEY")   # Claude Sonnet/Opus — https://console.anthropic.com
# GROQ_KEY        = _env("GROQ_KEY")         # Groq Llama-3 — siêu nhanh, có free tier
# COHERE_KEY      = _env("COHERE_KEY")       # Cohere Command R+

def db_connect():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    return conn

def init_db():
    conn = db_connect()
    conn.execute("PRAGMA journal_mode=WAL")
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
    c.execute("""CREATE TABLE IF NOT EXISTS payos_processed (
        order_code TEXT PRIMARY KEY,
        processed_at DATETIME
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS payos_orders (
        order_code TEXT PRIMARY KEY,
        user_id TEXT,
        amount INTEGER,
        xu INTEGER,
        status TEXT DEFAULT 'PENDING',
        created_at DATETIME,
        expires_at DATETIME,
        paid_at DATETIME,
        checkout_url TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS credit_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        delta INTEGER,
        balance_after INTEGER,
        event_type TEXT,
        ref_id TEXT,
        note TEXT,
        created_at DATETIME
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        phone TEXT,
        services TEXT,
        note TEXT,
        source TEXT,
        created_at DATETIME
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS referrals (
        referred_user_id TEXT PRIMARY KEY,
        referrer_user_id TEXT,
        bonus_paid INTEGER DEFAULT 0,
        created_at DATETIME
    )""")
    for col, defval in [("total_spent","0"), ("is_vip","0"), ("has_deposited","0"),
                        ("free_chat_count","0"), ("free_chat_date","''")]:
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} {'INTEGER' if 'count' in col or 'spent' in col or 'vip' in col or 'deposited' in col else 'TEXT'} DEFAULT {defval}")
        except Exception:
            pass
    for col, col_type in [
        ("expires_at", "DATETIME"),
        ("paid_at", "DATETIME"),
        ("checkout_url", "TEXT"),
    ]:
        try:
            c.execute(f"ALTER TABLE payos_orders ADD COLUMN {col} {col_type}")
        except Exception:
            pass
    conn.commit()
    conn.close()

def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def record_credit_event(conn, user_id, delta, event_type, ref_id="", note=""):
    c = conn.cursor()
    c.execute("SELECT credits FROM users WHERE user_id=?", (str(user_id),))
    row = c.fetchone()
    balance_after = row[0] if row else 0
    c.execute(
        "INSERT INTO credit_events (user_id, delta, balance_after, event_type, ref_id, note, created_at) VALUES (?,?,?,?,?,?,?)",
        (str(user_id), int(delta), balance_after, event_type, str(ref_id), note, now_text())
    )

def get_user(user_id, username="Unknown"):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT credits, total_spent, is_vip FROM users WHERE user_id=?", (str(user_id),))
    row = c.fetchone()
    if not row:
        c.execute(
            "INSERT INTO users (user_id, username, credits, is_vip, join_date, total_spent) VALUES (?,?,?,?,?,?)",
            (str(user_id), username, TRIAL_CREDITS, 0, now_text(), 0)
        )
        record_credit_event(conn, user_id, TRIAL_CREDITS, "trial_grant", "", "Tặng xu dùng thử")
        conn.commit()
        row = (TRIAL_CREDITS, 0, 0)
    conn.close()
    return row[0], row[1], row[2]

def add_credit(user_id, amount, event_type="manual_add", ref_id="", note=""):
    get_user(user_id)
    conn = db_connect()
    c = conn.cursor()
    c.execute("UPDATE users SET credits = credits + ? WHERE user_id=?", (amount, str(user_id)))
    record_credit_event(conn, user_id, amount, event_type, ref_id, note)
    conn.commit()
    conn.close()

def spend_fixed_credit(user_id, amount, event_type, note="") -> bool:
    if str(user_id) == ADMIN_ID:
        return True
    get_user(user_id)
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT credits FROM users WHERE user_id=?", (str(user_id),))
    row = c.fetchone()
    if not row or row[0] < amount:
        conn.close()
        return False
    c.execute("UPDATE users SET credits = credits - ?, total_spent = total_spent + ? WHERE user_id=?", (amount, amount, str(user_id)))
    record_credit_event(conn, user_id, -amount, event_type, "", note)
    conn.commit()
    conn.close()
    return True

def is_payos_order_processed(order_code: str) -> bool:
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT 1 FROM payos_processed WHERE order_code=?", (str(order_code),))
    exists = c.fetchone() is not None
    conn.close()
    return exists

def mark_payos_order_processed(order_code: str):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO payos_processed (order_code, processed_at) VALUES (?,?)",
        (str(order_code), now_text())
    )
    conn.commit()
    conn.close()

def create_order(order_code, user_id, amount, xu):
    conn = db_connect()
    c = conn.cursor()
    created_at = datetime.now()
    expires_at = created_at + timedelta(minutes=ORDER_TTL_MINUTES)
    c.execute(
        "INSERT INTO payos_orders (order_code, user_id, amount, xu, status, created_at, expires_at) VALUES (?,?,?,?,?,?,?)",
        (str(order_code), str(user_id), amount, xu, PAYOS_STATUS_PENDING,
         created_at.strftime("%Y-%m-%d %H:%M:%S"), expires_at.strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()

def get_order(order_code):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT user_id, amount, xu, status, expires_at FROM payos_orders WHERE order_code=?", (str(order_code),))
    row = c.fetchone()
    conn.close()
    return row

def update_order_status(order_code, status):
    conn = db_connect()
    c = conn.cursor()
    c.execute("UPDATE payos_orders SET status=? WHERE order_code=?", (status, str(order_code)))
    conn.commit()
    conn.close()

def update_order_checkout_url(order_code, checkout_url):
    conn = db_connect()
    c = conn.cursor()
    c.execute("UPDATE payos_orders SET checkout_url=? WHERE order_code=?", (checkout_url, str(order_code)))
    conn.commit()
    conn.close()

def make_payos_return_url(context: ContextTypes.DEFAULT_TYPE) -> str:
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL.rstrip("/") + "/landing"
    bot_name = context.bot.username or BOT_USERNAME
    return f"https://t.me/{bot_name}" if bot_name else "https://t.me"

def make_payos_description(pkg_key: str) -> str:
    # payOS giới hạn 9 ký tự mô tả với một số kênh ngân hàng chưa liên kết.
    return f"DAAS{pkg_key.upper()}"[:9]

def sign_payos_payment_request(data: dict) -> tuple[str, str]:
    raw_str = (
        f"amount={data['amount']}"
        f"&cancelUrl={data['cancelUrl']}"
        f"&description={data['description']}"
        f"&orderCode={data['orderCode']}"
        f"&returnUrl={data['returnUrl']}"
    )
    signature = hmac.new(
        PAYOS_CHECKSUM_KEY.encode("utf-8"),
        raw_str.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return signature, raw_str

def expire_old_payos_orders():
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "UPDATE payos_orders SET status=? WHERE status=? AND expires_at IS NOT NULL AND expires_at < ?",
        (PAYOS_STATUS_EXPIRED, PAYOS_STATUS_PENDING, now_text())
    )
    conn.commit()
    conn.close()

def register_referral(referred_user_id, referrer_user_id) -> bool:
    if str(referred_user_id) == str(referrer_user_id):
        return False
    get_user(referrer_user_id)
    get_user(referred_user_id)
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO referrals (referred_user_id, referrer_user_id, bonus_paid, created_at) VALUES (?,?,0,?)",
        (str(referred_user_id), str(referrer_user_id), now_text())
    )
    inserted = c.rowcount > 0
    conn.commit()
    conn.close()
    return inserted

def award_referral_bonus_if_needed(conn, referred_user_id) -> int:
    c = conn.cursor()
    c.execute(
        "SELECT referrer_user_id FROM referrals WHERE referred_user_id=? AND bonus_paid=0",
        (str(referred_user_id),)
    )
    row = c.fetchone()
    if not row:
        return 0
    referrer_id = row[0]
    c.execute("UPDATE users SET credits = credits + ? WHERE user_id=?", (REFERRAL_BONUS_XU, str(referrer_id)))
    c.execute("UPDATE referrals SET bonus_paid=1 WHERE referred_user_id=?", (str(referred_user_id),))
    record_credit_event(conn, referrer_id, REFERRAL_BONUS_XU, "referral_bonus", referred_user_id, "Thưởng giới thiệu khách nạp lần đầu")
    return REFERRAL_BONUS_XU

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
        conn = db_connect()
        c = conn.cursor()
        c.execute(
            "UPDATE users SET credits = credits - ?, total_spent = total_spent + ? WHERE user_id=?",
            (final_cost, final_cost, str(user_id))
        )
        c.execute(
            "INSERT INTO transactions (user_id, action, cost, discount_rate, created_at) VALUES (?,?,?,?,?)",
            (str(user_id), action_type, final_cost, discount_rate, now_text())
        )
        record_credit_event(conn, user_id, -final_cost, f"spend_{action_type}", "", f"Trừ xu cho {action_type}")
        conn.commit()
        conn.close()
        return True, final_cost, discount_rate
    return False, final_cost, discount_rate

def process_payos_paid_order(order_code: str, amount_vnd: int) -> tuple[bool, str, dict]:
    """
    Cộng xu cho đơn PayOS trong một transaction để tránh cộng trùng.
    Trả về (processed, desc, info).
    """
    if not order_code:
        return False, "missing_order_code", {}

    conn = db_connect()
    c = conn.cursor()
    try:
        c.execute("BEGIN IMMEDIATE")
        c.execute(
            "SELECT user_id, amount, xu, status, expires_at FROM payos_orders WHERE order_code=?",
            (str(order_code),)
        )
        order = c.fetchone()
        if not order:
            conn.rollback()
            return False, "order_not_found", {}

        target_id, expected_amount, xu, status, expires_at = order
        info = {
            "target_id": target_id,
            "expected_amount": expected_amount,
            "xu": xu,
            "status": status,
        }

        if status == PAYOS_STATUS_PAID:
            conn.rollback()
            return False, "already_paid", info
        if status in (PAYOS_STATUS_EXPIRED, PAYOS_STATUS_CANCELLED):
            conn.rollback()
            return False, status.lower(), info
        if expires_at and expires_at < now_text():
            c.execute("UPDATE payos_orders SET status=? WHERE order_code=?", (PAYOS_STATUS_EXPIRED, str(order_code)))
            conn.commit()
            return False, "expired", info
        if int(expected_amount) != int(amount_vnd):
            conn.rollback()
            return False, "amount_mismatch", info

        c.execute("SELECT 1 FROM payos_processed WHERE order_code=?", (str(order_code),))
        if c.fetchone():
            conn.rollback()
            return False, "duplicate", info

        c.execute("SELECT user_id FROM users WHERE user_id=?", (str(target_id),))
        if not c.fetchone():
            c.execute(
                "INSERT INTO users (user_id, username, credits, is_vip, join_date, total_spent, has_deposited) VALUES (?,?,?,?,?,?,?)",
                (str(target_id), "PayOS user", 0, 0, now_text(), 0, 1)
            )

        c.execute(
            "UPDATE users SET credits = credits + ?, has_deposited=1 WHERE user_id=?",
            (int(xu), str(target_id))
        )
        c.execute(
            "UPDATE payos_orders SET status=?, paid_at=? WHERE order_code=?",
            (PAYOS_STATUS_PAID, now_text(), str(order_code))
        )
        c.execute(
            "INSERT INTO payos_processed (order_code, processed_at) VALUES (?,?)",
            (str(order_code), now_text())
        )
        record_credit_event(conn, target_id, int(xu), "payos_deposit", order_code, f"Nạp PayOS {amount_vnd}đ")
        referral_bonus = award_referral_bonus_if_needed(conn, target_id)
        info["referral_bonus"] = referral_bonus
        conn.commit()
        return True, "success", info
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

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

class LeadRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=6, max_length=30)
    services: list[str] = Field(default_factory=list)
    note: str = Field(default="", max_length=1000)
    source: str = Field(default="landing", max_length=80)

class AgentGemini:
    @staticmethod
    def chat(prompt: str, text: str, uid, is_json: bool = False) -> str:
        if not gemini_client and not openai_client:
            return "❌ Chưa cấu hình AI Provider."

        if gemini_client:
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
                logger.error(f"Gemini error: {e} — Thử fallback OpenAI...")

        if openai_client:
            try:
                messages = [{"role": "system", "content": prompt}]
                if uid in user_memory:
                    for m in user_memory[uid][-6:]:
                        role = "user" if m.role == "user" else "assistant"
                        messages.append({"role": role, "content": m.parts[0].text})
                messages.append({"role": "user", "content": text})

                res = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    response_format={"type": "json_object"} if is_json else {"type": "text"},
                    max_tokens=1000
                )
                return res.choices[0].message.content
            except Exception as e:
                logger.error(f"OpenAI error: {e}")
                return "❌ Lỗi cả Gemini lẫn OpenAI."

        return "❌ Không có AI Provider nào hoạt động."

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
        out = f"v_{user_id}.mp3"
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text="⏳ <i>[Giọng Nói] Đang tổng hợp...</i>",
            parse_mode="HTML"
        )
        used_fish = False
        try:
            edge_ok = False
            try:
                communicate = edge_tts.Communicate(text, "vi-VN-NamMinhNeural")
                await communicate.save(out)
                if os.path.exists(out) and os.path.getsize(out) > 0:
                    edge_ok = True
            except Exception as e:
                logger.warning(f"Edge TTS lỗi: {e} — thử Fish Audio...")

            if edge_ok:
                with open(out, "rb") as f:
                    await context.bot.send_audio(
                        chat_id=chat_id, audio=f,
                        caption=f"🔊 Gói Tiết Kiệm — Tổng hợp giọng nói thành công! (-{VOICE_FREE_COST} Xu)"
                    )
                await msg.delete()
                return False

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
                    with open(out, "rb") as f:
                        await context.bot.send_audio(
                            chat_id=chat_id, audio=f,
                            caption=f"🎙️ Gói Cao Cấp — Tổng hợp thành công! (-{cost} Xu)"
                        )
                    await msg.delete()
                else:
                    logger.error(f"Fish Audio lỗi {res.status_code}")
                    await msg.edit_text("❌ Cả hai gói đều gặp lỗi.")
            else:
                await msg.edit_text("❌ Edge TTS lỗi và chưa cấu hình FISH_AUDIO_KEY.")

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

# ─── STATE ───────────────────────────────────────────────────────────────────
USER_BILL_STATE: dict = {}
USER_PENDING: dict = {}

VOICE_FREE_COST  = 5
IMAGE_FREE_COST  = 5

def is_trial_account(user_id) -> bool:
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT has_deposited FROM users WHERE user_id=?", (str(user_id),))
    row = c.fetchone()
    conn.close()
    if not row:
        return True
    return row[0] != 1

def get_free_chat_status(user_id) -> tuple:
    """Trả về (đã dùng hôm nay, còn lại). Reset tự động sang ngày mới."""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT free_chat_count, free_chat_date FROM users WHERE user_id=?", (str(user_id),))
    row = c.fetchone()
    conn.close()
    if not row or row[1] != today:
        return 0, FREE_CHAT_DAILY
    used = row[0]
    return used, max(0, FREE_CHAT_DAILY - used)

def consume_free_chat(user_id) -> bool:
    """Tiêu 1 lượt free chat. Trả về True nếu thành công, False nếu hết."""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT free_chat_count, free_chat_date FROM users WHERE user_id=?", (str(user_id),))
    row = c.fetchone()
    if not row:
        conn.close()
        return False
    count, date = row
    if date != today:
        count = 0  # reset ngày mới
    if count >= FREE_CHAT_DAILY:
        conn.close()
        return False
    c.execute(
        "UPDATE users SET free_chat_count=?, free_chat_date=? WHERE user_id=?",
        (count + 1, today, str(user_id))
    )
    conn.commit()
    conn.close()
    return True

def provider_keyboard(service: str, uid: int, cost: int) -> InlineKeyboardMarkup:
    trial = is_trial_account(uid)
    if service == "voice":
        buttons = [
            [
                InlineKeyboardButton(
                    f"🔊 Gói Tiết Kiệm — -{VOICE_FREE_COST} Xu",
                    callback_data=f"prov|voice|free|{uid}"
                )
            ],
        ]
        if not trial:
            buttons.append([
                InlineKeyboardButton(
                    f"🎙️ Gói Cao Cấp — -{cost} Xu",
                    callback_data=f"prov|voice|paid|{uid}"
                )
            ])
    else:
        buttons = [
            [
                InlineKeyboardButton(
                    f"✂️ Gói Tiết Kiệm — -{IMAGE_FREE_COST} Xu",
                    callback_data=f"prov|image|free|{uid}"
                )
            ],
        ]
        if not trial:
            buttons.append([
                InlineKeyboardButton(
                    f"🖼️ Gói Cao Cấp — -{cost} Xu",
                    callback_data=f"prov|image|paid|{uid}"
                )
            ])
    buttons.append([InlineKeyboardButton("❌ Huỷ", callback_data=f"prov|cancel|cancel|{uid}")])
    return InlineKeyboardMarkup(buttons)


async def handle_provider_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("|")
    if len(parts) != 4:
        return
    _, service, mode, uid_str = parts
    uid = int(uid_str)

    if query.from_user.id != uid:
        await query.answer("⚠️ Không phải yêu cầu của bạn!", show_alert=True)
        return

    pending = USER_PENDING.pop(uid, None)
    if not pending:
        await query.edit_message_text("⏰ Yêu cầu đã hết hạn hoặc đã xử lý.")
        return

    if mode == "cancel":
        if pending.get("cost", 0) > 0:
            add_credit(uid, pending["cost"], "refund", "", "Hoàn xu do khách hủy yêu cầu")
        await query.edit_message_text("❌ Đã huỷ. Xu được hoàn lại.")
        return

    chat_id  = pending["chat_id"]
    cost     = pending["cost"]
    svc_type = pending["type"]

    if svc_type == "voice":
        data = pending["data"]
        if mode == "free":
            if cost > 0 and str(uid) != ADMIN_ID:
                add_credit(uid, cost, "refund", "", "Hoàn phí voice cao cấp trước khi chọn gói tiết kiệm")
            if not spend_fixed_credit(uid, VOICE_FREE_COST, "spend_voice_free", "Gói voice tiết kiệm"):
                await query.edit_message_text(f"❌ Không đủ xu. Cần ít nhất {VOICE_FREE_COST} Xu.")
                return
            await query.edit_message_text("⏳ <i>Đang tổng hợp giọng nói (Gói Tiết Kiệm)...</i>", parse_mode="HTML")
            out = f"v_{uid}.mp3"
            try:
                communicate = edge_tts.Communicate(data, "vi-VN-NamMinhNeural")
                await communicate.save(out)
                with open(out, "rb") as f:
                    await context.bot.send_audio(
                        chat_id=chat_id, audio=f,
                        caption=f"🔊 Gói Tiết Kiệm — Tổng hợp giọng nói thành công! (-{VOICE_FREE_COST} Xu)"
                    )
                await query.delete_message()
            except Exception as e:
                logger.error(f"Edge TTS error: {e}")
                if str(uid) != ADMIN_ID:
                    add_credit(uid, VOICE_FREE_COST, "refund", "", "Hoàn gói voice tiết kiệm do lỗi")
                await query.edit_message_text("❌ Gói Tiết Kiệm gặp lỗi.")
            finally:
                if os.path.exists(out):
                    os.remove(out)
        else:
            await query.edit_message_text("⏳ <i>Đang tổng hợp giọng nói (Gói Cao Cấp)...</i>", parse_mode="HTML")
            out = f"v_{uid}.mp3"
            ok = False
            try:
                if FISH_AUDIO_KEY:
                    async with httpx.AsyncClient() as client:
                        res = await client.post(
                            "https://api.fish.audio/v1/tts",
                            headers={"Authorization": f"Bearer {FISH_AUDIO_KEY}", "Content-Type": "application/json"},
                            json={"text": data, "reference_id": "7f0955e88846433e9ecb241357608bf8", "format": "mp3"},
                            timeout=30.0
                        )
                    if res.status_code == 200:
                        with open(out, "wb") as f:
                            f.write(res.content)
                        ok = True
                        with open(out, "rb") as f:
                            await context.bot.send_audio(
                                chat_id=chat_id, audio=f,
                                caption=f"🎙️ Gói Cao Cấp — Tổng hợp thành công! (-{cost} Xu)"
                            )
                        await query.delete_message()
                    else:
                        logger.warning(f"Fish Audio {res.status_code} — fallback Edge TTS")
                if not ok:
                    if cost > 0 and str(uid) != ADMIN_ID:
                        add_credit(uid, cost, "refund", "", "Hoàn phí voice cao cấp do fallback")
                    if not spend_fixed_credit(uid, VOICE_FREE_COST, "spend_voice_free_fallback", "Fallback sang Edge TTS"):
                        await query.edit_message_text(f"❌ Không đủ xu cho gói fallback. Cần ít nhất {VOICE_FREE_COST} Xu.")
                        return
                    communicate = edge_tts.Communicate(data, "vi-VN-NamMinhNeural")
                    await communicate.save(out)
                    with open(out, "rb") as f:
                        await context.bot.send_audio(
                            chat_id=chat_id, audio=f,
                            caption=f"🔊 Gói Tiết Kiệm — Hoàn thành! (-{VOICE_FREE_COST} Xu)"
                        )
                    await query.delete_message()
            except Exception as e:
                logger.error(f"Voice paid error: {e}")
                await query.edit_message_text("❌ Lỗi tổng hợp giọng.")
            finally:
                if os.path.exists(out):
                    os.remove(out)

    elif svc_type == "image":
        img_bytes = pending["file_bytes"]
        if mode == "free":
            if cost > 0 and str(uid) != ADMIN_ID:
                add_credit(uid, cost, "refund", "", "Hoàn phí ảnh cao cấp trước khi chọn gói tiết kiệm")
            if not spend_fixed_credit(uid, IMAGE_FREE_COST, "spend_image_free", "Gói tách nền tiết kiệm"):
                await query.edit_message_text(f"❌ Không đủ xu. Cần ít nhất {IMAGE_FREE_COST} Xu.")
                return
            await query.edit_message_text("⏳ <i>Đang tách nền (Gói Tiết Kiệm)...</i>", parse_mode="HTML")
            ok = False
            if CUTOUT_API_KEY:
                try:
                    async with httpx.AsyncClient() as client:
                        res = await client.post(
                            "https://www.cutout.pro/api/v1/matting2?mattingType=2&crop=true",
                            headers={"APIKEY": CUTOUT_API_KEY},
                            files={"file": img_bytes},
                            timeout=30.0
                        )
                    if res.status_code == 200:
                        await context.bot.send_document(
                            chat_id=chat_id, document=res.content,
                            filename="no_bg.png",
                            caption=f"✂️ Gói Tiết Kiệm — Tách nền thành công! (-{IMAGE_FREE_COST} Xu)"
                        )
                        await query.delete_message()
                        ok = True
                    else:
                        logger.warning(f"Cutout {res.status_code}")
                except Exception as e:
                    logger.error(f"Cutout error: {e}")
            if not ok:
                if str(uid) != ADMIN_ID:
                    add_credit(uid, IMAGE_FREE_COST, "refund", "", "Hoàn gói tách nền tiết kiệm do lỗi")
                await query.edit_message_text("❌ Cutout.pro lỗi hoặc chưa cấu hình CUTOUT_API_KEY.")
        else:
            await query.edit_message_text("⏳ <i>Đang tách nền (Gói Cao Cấp)...</i>", parse_mode="HTML")
            ok = False
            if REMOVEBG_API_KEY:
                try:
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
                            chat_id=chat_id, document=res.content,
                            filename="no_bg.png",
                            caption=f"✂️ Gói Cao Cấp — Tách nền HD thành công! (-{cost} Xu)"
                        )
                        await query.delete_message()
                        ok = True
                    else:
                        logger.warning(f"RemoveBG {res.status_code} → fallback Cutout")
                except Exception as e:
                    logger.error(f"RemoveBG error: {e}")
            if not ok:
                if cost > 0 and str(uid) != ADMIN_ID:
                    add_credit(uid, cost, "refund", "", "Hoàn phí ảnh cao cấp do fallback")
                if not spend_fixed_credit(uid, IMAGE_FREE_COST, "spend_image_free_fallback", "Fallback sang Cutout"):
                    await query.edit_message_text(f"❌ Không đủ xu cho gói fallback. Cần ít nhất {IMAGE_FREE_COST} Xu.")
                    return
                cutout_ok = False
                if CUTOUT_API_KEY:
                    try:
                        async with httpx.AsyncClient() as client:
                            res = await client.post(
                                "https://www.cutout.pro/api/v1/matting2?mattingType=2&crop=true",
                                headers={"APIKEY": CUTOUT_API_KEY},
                                files={"file": img_bytes},
                                timeout=30.0
                            )
                        if res.status_code == 200:
                            await context.bot.send_document(
                                chat_id=chat_id, document=res.content,
                                filename="no_bg.png",
                                caption=f"✂️ Gói Tiết Kiệm — Hoàn thành! (-{IMAGE_FREE_COST} Xu)"
                            )
                            await query.delete_message()
                            cutout_ok = True
                    except Exception as e:
                        logger.error(f"Cutout fallback error: {e}")
                if not cutout_ok:
                    if str(uid) != ADMIN_ID:
                        add_credit(uid, IMAGE_FREE_COST, "refund", "", "Hoàn gói tách nền fallback do lỗi")
                    await query.edit_message_text("❌ Cả 2 dịch vụ đều lỗi. Xu đã hoàn lại.")


async def handle_package_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý sinh hóa đơn và link QR Động từ PayOS khi khách click chọn gói"""
    expire_old_payos_orders()
    query = update.callback_query
    await query.answer()
    parts = query.data.split("|")
    if len(parts) != 3:
        return
    _, pkg_key, uid_str = parts
    uid = int(uid_str)

    if query.from_user.id != uid:
        await query.answer("⚠️ Không phải yêu cầu của bạn!", show_alert=True)
        return

    if pkg_key not in PAYMENT_PACKAGES:
        await query.edit_message_text("❌ Gói nạp không hợp lệ.")
        return

    pkg = PAYMENT_PACKAGES[pkg_key]
    amount = pkg["amount"]
    xu = pkg["xu"]
    get_user(uid, query.from_user.first_name or "PayOS user")

    if not PAYOS_CLIENT_ID or not PAYOS_API_KEY or not PAYOS_CHECKSUM_KEY:
        await query.edit_message_text("❌ Hệ thống chưa cấu hình đầy đủ API Key PayOS.")
        return

    # Sinh mã đơn hàng dạng số nguyên (timestamp + random) hợp lệ với PayOS
    order_code = int(time.time() * 10) + random.randint(0, 9)
    create_order(order_code, uid, amount, xu)

    return_url = make_payos_return_url(context)
    payos_body = {
        "orderCode": order_code,
        "amount": amount,
        "description": make_payos_description(pkg_key),
        "cancelUrl": return_url,
        "returnUrl": return_url
    }

    signature, raw_str = sign_payos_payment_request(payos_body)
    payos_body["signature"] = signature

    headers = {
        "x-client-id": PAYOS_CLIENT_ID,
        "x-api-key": PAYOS_API_KEY,
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(
                "https://api-merchant.payos.vn/v2/payment-requests",
                headers=headers,
                json=payos_body,
                timeout=30.0
            )
        res_data = res.json()
        if res.status_code == 200 and res_data.get("code") == "00":
            checkout_url = res_data["data"]["checkoutUrl"]
            update_order_checkout_url(order_code, checkout_url)
            qr_text = (
                f"⚡ <b>ĐÃ KHỞI TẠO HÓA ĐƠN QR ĐỘNG SUCCESS</b>\n\n"
                f"📋 Gói lựa chọn: <b>{pkg['text']}</b>\n"
                f"💰 Số tiền cần chuyển: <b>{amount:,}đ</b>\n"
                f"🪙 Hạn mức nhận được: <b>+{xu} Xu</b>\n"
                f"🆔 Mã đơn định danh: <code>{order_code}</code>\n\n"
                f"⏳ Hóa đơn hết hạn sau <b>{ORDER_TTL_MINUTES} phút</b>.\n\n"
                f"👉 Nhấn vào nút liên kết dưới đây để nhận diện mã QR thanh toán động. Hệ thống sẽ tự động điền sẵn số tiền và nội dung hóa đơn chính xác!"
            )
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 QUÉT MÃ QR THANH TOÁN", url=checkout_url)]])
            await query.edit_message_text(qr_text, parse_mode="HTML", reply_markup=kb)
        else:
            update_order_status(order_code, PAYOS_STATUS_CANCELLED)
            logger.error(f"PayOS error response: {res_data} | signed={raw_str}")
            desc = res_data.get("desc", "Lỗi không rõ")
            hint = "\n\n⚠️ Nếu vẫn báo signature không hợp lệ, kiểm tra lại biến PAYOS_CHECKSUM_KEY trên server."
            await query.edit_message_text(f"❌ PayOS từ chối tạo hóa đơn: {desc}{hint}")
    except Exception as e:
        update_order_status(order_code, PAYOS_STATUS_CANCELLED)
        logger.error(f"PayOS Exception: {e}")
        await query.edit_message_text(f"❌ Thất bại khi kết nối API cổng PayOS: {str(e)}")

# ─── HANDLERS ────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    get_user(update.effective_user.id, update.effective_user.first_name)
    if context.args and context.args[0].startswith("ref_"):
        referrer = context.args[0].replace("ref_", "", 1)
        if register_referral(update.effective_user.id, referrer):
            await update.message.reply_text(
                f"🎁 Đã ghi nhận mã giới thiệu. Người giới thiệu sẽ nhận {REFERRAL_BONUS_XU} Xu khi bạn nạp lần đầu."
            )
    text = (
        "👑 <b>HỆ SINH THÁI AI — TOAN DAAS V15.2</b>\n\n"
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
        "• /tools — Kho 30 công cụ AI/MMO\n"
        "• /mmo — Quy trình kiếm tiền bằng AI\n"
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
        f"💳 <b>NẠP SỐ DƯ TỰ ĐỘNG (QR ĐỘNG) — TOAN DAAS</b>\n\n"
        f"👤 ID Telegram: <code>{uid}</code>\n"
        f"🪙 Số dư hiện tại: <b>{credits} Xu</b>\n\n"
        f"<b>🛒 BẢNG GIÁ (1 Xu = 100đ):</b>\n"
        f"• Gói Dùng Thử: 10.000đ ➔ <b>100 Xu</b>\n"
        f"• Gói Nhỏ: 20.000đ ➔ <b>200 Xu</b>\n"
        f"• Gói Trung: 50.000đ ➔ <b>500 Xu</b>\n"
        f"• Gói Tiêu Chuẩn: 100.000đ ➔ <b>1.050 Xu</b> 🎁 Tặng 50 Xu\n"
        f"• Gói Nâng Cao: 200.000đ ➔ <b>2.150 Xu</b> 🎁 Tặng 150 Xu\n"
        f"• Gói Doanh Nghiệp: 500.000đ ➔ <b>5.500 Xu</b> 🎁 Tặng 500 Xu\n\n"
        f"⚡ Hệ thống tự động khởi tạo link mã QR PayOS thời gian thực. Không lo điền sai nội dung chuyển khoản.\n\n"
        f"👇 <b>Vui lòng click chọn gói cước mong muốn dưới đây:</b>"
    )
    buttons = [
        [InlineKeyboardButton("🧪 Gói Dùng Thử (10k)", callback_data=f"pkg|10k|{uid}")],
        [InlineKeyboardButton("📦 Gói Nhỏ (20k)", callback_data=f"pkg|20k|{uid}")],
        [InlineKeyboardButton("⚡ Gói Trung (50k)", callback_data=f"pkg|50k|{uid}")],
        [InlineKeyboardButton("⭐ Gói Tiêu Chuẩn (100k)", callback_data=f"pkg|100k|{uid}")],
        [InlineKeyboardButton("🚀 Gói Nâng Cao (200k)", callback_data=f"pkg|200k|{uid}")],
        [InlineKeyboardButton("🏢 Gói Doanh Nghiệp (500k)", callback_data=f"pkg|500k|{uid}")]
    ]
    USER_BILL_STATE[uid] = True
    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))

async def cmd_tools(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🧰 <b>KHO 30 CÔNG CỤ CHUẨN</b>\n\n"
        "<b>Viết & nghiên cứu:</b> ChatGPT, Perplexity, DeepL, Notion\n"
        "<b>Ảnh & thiết kế:</b> Ideogram, Photopea, Remove.bg, Upscale.media, ResizePixel, Canva, Figma\n"
        "<b>Video:</b> CapCut, Kling AI, Cobalt Tools, DaVinci Resolve\n"
        "<b>Audio:</b> ElevenLabs, Whisper, Suno, Moises\n"
        "<b>Tài liệu:</b> PDF24, OCR Space, Convertio, Google Drive, Google Forms\n"
        "<b>Ý tưởng & quản lý:</b> Excalidraw, XMind, Cursor, GitHub\n"
        "<b>Marketing/Web:</b> Ahrefs Free Tools, Framer\n\n"
        "💡 Gửi yêu cầu cụ thể, bot sẽ gợi ý quy trình dùng công cụ phù hợp."
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def cmd_mmo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "💰 <b>WORKFLOW AI KIẾM TIỀN HỢP PHÁP</b>\n\n"
        "<b>1. Faceless video:</b> ChatGPT/Claude viết kịch bản → ElevenLabs/Edge TTS đọc → Kling/CapCut dựng → đăng TikTok/Reels/YouTube Shorts.\n"
        "<b>2. TikTok Affiliate:</b> chọn niche dễ mua → tạo 3-5 video/ngày → gắn sản phẩm → đo video thắng và remix.\n"
        "<b>3. Dịch vụ video AI:</b> nhận brief doanh nghiệp nhỏ → báo giá 500k-2M/video → giao kịch bản, voice, phụ đề, bản dựng.\n"
        "<b>4. Ảnh người mẫu AI:</b> chỉ dùng nhân vật tự tạo hoặc người thật có đồng ý rõ ràng, đủ 18 tuổi; không giả mạo người khác.\n\n"
        "✅ Bắt đầu nhỏ: 1 niche, 1 format, 30 video đầu tiên. Dùng /tools để lấy bộ công cụ."
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def cmd_ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bot_name = context.bot.username or BOT_USERNAME
    link = f"https://t.me/{bot_name}?start=ref_{uid}"
    await update.message.reply_text(
        f"🔗 <b>LINK GIỚI THIỆU CỦA BẠN</b>\n\n"
        f"<code>{link}</code>\n\n"
        f"🎁 Thưởng <b>{REFERRAL_BONUS_XU} Xu</b> khi người được giới thiệu nạp lần đầu.",
        parse_mode="HTML"
    )

async def cmd_gopy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = " ".join(context.args)
    if not content:
        return await update.message.reply_text(
            "⚠️ VD: <code>/gopy Thêm thanh toán Momo đi bot</code>", parse_mode="HTML"
        )
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "INSERT INTO feedback (user_id, username, content, timestamp) VALUES (?,?,?,?)",
        (str(update.effective_user.id), update.effective_user.first_name,
         content, now_text())
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
        add_credit(target_id, amount, "admin_add", "", "Admin cộng xu thủ công")
        conn = db_connect()
        c = conn.cursor()
        c.execute("UPDATE users SET has_deposited=1 WHERE user_id=?", (str(target_id),))
        conn.commit()
        conn.close()
        credits, _, _ = get_user(target_id)
        await update.message.reply_text(f"✅ Đã bơm {amount} Xu cho ID {target_id}. Số dư mới: {credits} Xu")
    except Exception:
        await update.message.reply_text("⚠️ Cú pháp: /add <ID> <Số_Xu>")

async def cmd_admin_gopy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    conn = db_connect()
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
        add_credit(target_id, amount, "manual_deposit", "", "Admin duyệt bill thủ công")
        conn = db_connect()
        c = conn.cursor()
        c.execute(
            "UPDATE pending_deposits SET status='approved' WHERE user_id=? AND status='pending'",
            (str(target_id),)
        )
        c.execute("UPDATE users SET has_deposited=1 WHERE user_id=?", (str(target_id),))
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
        conn = db_connect()
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
                f"Kiểm tra lại nội dung chuyển khoản hoặc liên hệ Admin."
            ),
            parse_mode="HTML"
        )
        await update.message.reply_text(f"✅ Đã từ chối và thông báo ID: {target_id}")
    except IndexError:
        await update.message.reply_text("⚠️ Cú pháp: /tuchoi <ID>")

async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "SELECT id, user_id, username, submitted_at FROM pending_deposits "
        "WHERE status='pending' ORDER BY submitted_at DESC LIMIT 10"
    )
    rows = c.fetchall()
    conn.close()
    if not rows:
        return await update.message.reply_text("📭 Không có bill nào đang chờ.")
    lines = ["📋 <b>BILL CHỜ DUYỆT (THỦ CÔNG):</b>\n"]
    for r in rows:
        lines.append(
            f"• #{r[0]} | {r[2]} | <code>{r[1]}</code> | {r[3]}\n"
            f"  ➔ <code>/duyet {r[1]} &lt;Xu&gt;</code>"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    conn = db_connect()
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
    c.execute("SELECT COUNT(*) FROM payos_processed")
    payos_auto = c.fetchone()[0]
    conn.close()
    await update.message.reply_text(
        f"📊 <b>THỐNG KÊ HỆ THỐNG</b>\n\n"
        f"👥 Tổng user: <b>{total_users}</b>\n"
        f"⚡ Giao dịch hôm nay: <b>{tx_today}</b>\n"
        f"💰 Xu tiêu hôm nay: <b>{revenue_today}</b>\n"
        f"📋 Bill chờ duyệt (thủ công): <b>{pending}</b>\n"
        f"🤖 Nạp tự động PayOS QR Động: <b>{payos_auto}</b>",
        parse_mode="HTML"
    )

async def cmd_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT user_id, username, credits, total_spent, is_vip FROM users ORDER BY CAST(credits AS INTEGER) DESC LIMIT 8")
    top_users = c.fetchall()
    c.execute("SELECT order_code, user_id, amount, xu, status, created_at FROM payos_orders ORDER BY created_at DESC LIMIT 8")
    recent_orders = c.fetchall()
    c.execute("SELECT user_id, delta, balance_after, event_type, created_at FROM credit_events ORDER BY id DESC LIMIT 8")
    recent_credit = c.fetchall()
    c.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM payos_orders WHERE status=?", (PAYOS_STATUS_PAID,))
    paid_count, paid_amount = c.fetchone()
    conn.close()

    lines = [
        "🧭 <b>ADMIN DASHBOARD</b>",
        f"💳 PayOS đã thanh toán: <b>{paid_count}</b> đơn / <b>{paid_amount:,}đ</b>",
        "",
        "<b>Top user theo số dư:</b>",
    ]
    for user_id, username, credits, total_spent, is_vip in top_users:
        vip = " VIP" if is_vip else ""
        lines.append(f"• {username or 'Unknown'} <code>{user_id}</code>: {credits} Xu, chi {total_spent}{vip}")

    lines.append("\n<b>Đơn PayOS gần nhất:</b>")
    for order_code, user_id, amount, xu, status, created_at in recent_orders:
        lines.append(f"• <code>{order_code}</code> | {user_id} | {amount:,}đ → {xu} Xu | {status}")

    lines.append("\n<b>Biến động xu gần nhất:</b>")
    for user_id, delta, balance_after, event_type, created_at in recent_credit:
        lines.append(f"• {created_at} | {user_id} | {delta:+} Xu | còn {balance_after} | {event_type}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_setvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    try:
        target_id = context.args[0]
        flag = int(context.args[1])
        conn = db_connect()
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
        conn = db_connect()
        c = conn.cursor()
        c.execute(
            "INSERT INTO pending_deposits (user_id, username, file_id, submitted_at, status) VALUES (?,?,?,?,?)",
            (str(uid), username, update.message.photo[-1].file_id,
             now_text(), "pending")
        )
        deposit_id = c.lastrowid
        conn.commit()
        conn.close()
        admin_caption = (
            f"💸 <b>BILL MỚI TẢI LÊN THỦ CÔNG #{deposit_id}</b>\n\n"
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
            f"📋 Mã đơn: <b>#{deposit_id}</b>\n"
            f"🆔 ID của bạn: <code>{uid}</code>\n\n"
            f"⏳ Vui lòng chờ Admin kiểm tra chéo sao kê thủ công.",
            parse_mode="HTML"
        )
        return

    if not REMOVEBG_API_KEY and not CUTOUT_API_KEY:
        return await update.message.reply_text("❌ Dịch vụ tách nền chưa được cấu hình.")
    file_size = update.message.photo[-1].file_size
    raw_cost = calculate_dynamic_cost("image", file_size)
    credits, total_spent, is_vip = get_user(uid)
    final_cost, _ = apply_discount(total_spent, raw_cost)
    if credits < final_cost and str(uid) != ADMIN_ID and is_vip != 1:
        return await update.message.reply_text(
            f"❌ Cần {final_cost} Xu để dùng Gói Cao Cấp.\n"
            f"Chọn Gói Tiết Kiệm (-5 Xu) hoặc /naptien để nạp thêm.",
            parse_mode="HTML"
        )
    img_bytes = bytes(await (await update.message.photo[-1].get_file()).download_as_bytearray())
    USER_PENDING[uid] = {
        "type": "image",
        "file_bytes": img_bytes,
        "cost": final_cost,
        "chat_id": update.effective_chat.id,
    }
    kb = provider_keyboard("image", uid, final_cost)
    if is_trial_account(uid):
        img_desc = (
            f"🖼️ <b>Chọn gói tách nền:</b>\n\n"
            f"✂️ <b>Gói Tiết Kiệm</b> — Tách nền nhanh, trừ <b>{IMAGE_FREE_COST} Xu</b>\n\n"
            f"<i>💡 Nạp tiền để mở khoá Gói Cao Cấp — chất lượng HD!</i>"
        )
    else:
        img_desc = (
            f"🖼️ <b>Chọn gói tách nền:</b>\n\n"
            f"✂️ <b>Gói Tiết Kiệm</b> — Tách nền nhanh, trừ <b>{IMAGE_FREE_COST} Xu</b>\n"
            f"🖼️ <b>Gói Cao Cấp</b> — Chất lượng HD, trừ <b>{final_cost} Xu</b>\n\n"
            f"<i>If premium engine fails, system auto switch to save engine & refund.</i>"
        )
    await update.message.reply_text(img_desc, parse_mode="HTML", reply_markup=kb)

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

    if not gemini_client and not openai_client:
        return await update.message.reply_text("❌ Hệ thống AI chưa sẵn sàng (thiếu GEMINI_API_KEY và OPENAI_API_KEY).")

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

    # ── LOGIC CHAT MIỄN PHÍ / TRẢ PHÍ ───────────────────────────────────────
    is_admin = str(uid) == ADMIN_ID
    credits, total_spent, is_vip = get_user(uid)
    trial = is_trial_account(uid)

    if action_key == "chat" and not is_admin and not is_vip:
        used_today, remaining = get_free_chat_status(uid)

        if trial:
            # Tài khoản chưa nạp: dùng lượt miễn phí, hết thì khoá đến hôm sau
            if remaining <= 0:
                reset_time = (datetime.now().replace(hour=0, minute=0, second=0) + timedelta(days=1)).strftime("%H:%M ngày %d/%m")
                return await update.message.reply_text(
                    f"🚫 <b>Hết {FREE_CHAT_DAILY} lượt chat miễn phí hôm nay!</b>\n\n"
                    f"⏰ Lượt mới reset lúc <b>00:00 ngày mai</b>\n"
                    f"💡 Hoặc nạp tiền để chat <b>không giới hạn</b> ngay bây giờ:\n"
                    f"👉 /naptien",
                    parse_mode="HTML"
                )
            # Còn lượt — dùng miễn phí, không trừ Xu
            consume_free_chat(uid)
            cost, discount = 0, 0.0
            warn = f"\n\n<i>🆓 Lượt miễn phí: còn {remaining - 1}/{FREE_CHAT_DAILY} hôm nay</i>" if remaining <= 5 else ""
        else:
            # Đã nạp tiền: trừ Xu bình thường, không giới hạn lượt
            can_afford, cost, discount = deduct_dynamic_credit(uid, action_key, size_calc)
            if not can_afford:
                return await update.message.reply_text(
                    f"❌ <b>HẾT XU!</b> Yêu cầu {cost} Xu.\n"
                    f"💳 Gõ /naptien để nạp thêm.",
                    parse_mode="HTML"
                )
            warn = ""
    elif action_key == "chat" and (is_admin or is_vip):
        cost, discount, warn = 0, 0.0, ""
    else:
        # voice / download — xử lý bình thường
        can_afford, cost, discount = deduct_dynamic_credit(uid, action_key, size_calc)
        if not can_afford:
            return await update.message.reply_text(
                f"❌ <b>HẾT HẠN MỨC!</b> Yêu cầu {cost} Xu.\nGõ /naptien để nạp thêm.",
                parse_mode="HTML"
            )
        warn = ""

    if act == "voice":
        raw_cost_v = calculate_dynamic_cost("voice", size_calc)
        _, ts_v, _ = get_user(uid)
        fish_cost, _ = apply_discount(ts_v, raw_cost_v)
        if cost > 0 and str(uid) != ADMIN_ID:
            add_credit(uid, cost)
        USER_PENDING[uid] = {
            "type": "voice",
            "data": data,
            "cost": fish_cost,
            "chat_id": update.effective_chat.id,
            "file_bytes": None,
        }
        kb = provider_keyboard("voice", uid, fish_cost)
        if is_trial_account(uid):
            voice_desc = (
                f"🎙️ <b>Chọn gói đọc giọng nói:</b>\n\n"
                f"🔊 <b>Gói Tiết Kiệm</b> — Giọng chuẩn, trừ <b>{VOICE_FREE_COST} Xu</b>\n\n"
                f"<i>💡 Nạp tiền để mở khoá Gói Cao Cấp — giọng nhân bản siêu thực!</i>"
            )
        else:
            voice_desc = (
                f"🎙️ <b>Chọn gói đọc giọng nói:</b>\n\n"
                f"🔊 <b>Gói Tiết Kiệm</b> — Giọng chuẩn, trừ <b>{VOICE_FREE_COST} Xu</b>\n"
                f"🎙️ <b>Gói Cao Cấp</b> — Giọng nhân bản siêu thực, trừ <b>{fish_cost} Xu</b>\n\n"
                f"<i>If premium voice system crash, system auto fallback to save engine & refund.</i>"
            )
        await update.message.reply_text(voice_desc, parse_mode="HTML", reply_markup=kb)
    elif act == "download":
        await AgentDownloader.download(data, context, update.effective_chat.id, cost)
    else:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        reply = AgentGemini.chat(
            "Bạn là Trợ Lý Ảo TOAN DAAS. Trả lời súc tích, thân thiện.",
            text, uid
        )
        if cost > 0:
            discount_text = " (Đã áp dụng VIP)" if discount > 0 else ""
            cost_line = f"\n\n<i>(-{cost} Xu){discount_text}</i>"
        else:
            cost_line = ""
        await update.message.reply_text(
            f"🤖 {reply}{cost_line}{warn}",
            parse_mode="HTML"
        )

# ─── FASTAPI + LIFESPAN ───────────────────────────────────────────────────────
tg_app: Application = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global tg_app
    init_db()
    if not TELEGRAM_TOKEN:
        logger.error("❌ TELEGRAM_TOKEN chưa được set!")
        yield
        return

    tg_app = Application.builder().token(TELEGRAM_TOKEN).build()

    tg_app.add_handler(CommandHandler("start",       cmd_start))
    tg_app.add_handler(CommandHandler("profile",     cmd_profile))
    tg_app.add_handler(CommandHandler("naptien",     cmd_naptien))
    tg_app.add_handler(CommandHandler("tools",       cmd_tools))
    tg_app.add_handler(CommandHandler("mmo",         cmd_mmo))
    tg_app.add_handler(CommandHandler("ref",         cmd_ref))
    tg_app.add_handler(CommandHandler("gopy",        cmd_gopy))
    tg_app.add_handler(CommandHandler("add",         cmd_admin_add))
    tg_app.add_handler(CommandHandler("admin_gopy",  cmd_admin_gopy))
    tg_app.add_handler(CommandHandler("duyet",       cmd_duyet))
    tg_app.add_handler(CommandHandler("tuchoi",      cmd_tuchoi))
    tg_app.add_handler(CommandHandler("pending",     cmd_pending))
    tg_app.add_handler(CommandHandler("stats",       cmd_stats))
    tg_app.add_handler(CommandHandler("dashboard",   cmd_dashboard))
    tg_app.add_handler(CommandHandler("setvip",      cmd_setvip))
    tg_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    tg_app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_media))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    tg_app.add_handler(CallbackQueryHandler(handle_provider_choice, pattern=r"^prov\|"))
    tg_app.add_handler(CallbackQueryHandler(handle_package_choice, pattern=r"^pkg\|"))

    await tg_app.initialize()
    await tg_app.start()
    asyncio.create_task(tg_app.updater.start_polling(allowed_updates=Update.ALL_TYPES))
    logger.info("🚀 TOAN DAAS ONLINE — Bot + Cổng QR Động PayOS Sẵn Sàng.")
    yield
    await tg_app.updater.stop()
    await tg_app.stop()
    await tg_app.shutdown()
    logger.info("🛑 Bot đã dừng an toàn.")

fastapi_app = FastAPI(title="TOAN DAAS V15.2", lifespan=lifespan)

# ─── HEALTH CHECK ─────────────────────────────────────────────────────────────
@fastapi_app.get("/")
async def health():
    return {"status": "ok", "service": "TOAN DAAS V15.2 — Dynamic Billing Verified"}

@fastapi_app.get("/landing")
async def landing_page():
    index_path = os.path.join(os.path.dirname(__file__), "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="Landing page not found")
    return FileResponse(index_path)

@fastapi_app.post("/lead")
async def create_lead(payload: LeadRequest, request: Request):
    if LEAD_WEBHOOK_SECRET and request.headers.get("x-lead-secret") != LEAD_WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid lead secret")

    services_text = ", ".join(payload.services) if payload.services else "Chưa chọn"
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "INSERT INTO leads (name, phone, services, note, source, created_at) VALUES (?,?,?,?,?,?)",
        (payload.name.strip(), payload.phone.strip(), services_text, payload.note.strip(), payload.source.strip(), now_text())
    )
    lead_id = c.lastrowid
    conn.commit()
    conn.close()

    if tg_app and ADMIN_ID:
        try:
            await tg_app.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"📩 <b>LEAD LANDING PAGE #{lead_id}</b>\n\n"
                    f"👤 {payload.name}\n"
                    f"☎️ <code>{payload.phone}</code>\n"
                    f"🧩 {services_text}\n"
                    f"📝 {payload.note or 'Không có ghi chú'}"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Lead notify error: {e}")

    return {"ok": True, "lead_id": lead_id}

# ─── WEBHOOK PAYOS (DYNAMIC UPDATED) ─────────────────────────────────────────
def verify_payos_signature(data: dict, received_sig: str) -> bool:
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
    """
    PayOS gọi Webhook tự động sau khi giao dịch QR động thành công.
    Tự đối chiếu orderCode nội bộ để cộng Xu mà khách không cần điền nội dung.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    sig  = body.get("signature", "")
    data = body.get("data", {})

    if PAYOS_CHECKSUM_KEY and not verify_payos_signature(data, sig):
        logger.warning("PayOS webhook: chữ ký xác thực không hợp lệ!")
        raise HTTPException(status_code=400, detail="Invalid signature")

    if not (body.get("success") or data.get("status") == "PAID"):
        return JSONResponse({"code": "00", "desc": "ignored"})

    order_code = str(data.get("orderCode", data.get("order_code", "")))
    try:
        amount_vnd = int(data.get("amount", 0))
    except (TypeError, ValueError):
        logger.warning(f"PayOS webhook: amount không hợp lệ | order={order_code} | data={data}")
        return JSONResponse({"code": "00", "desc": "invalid_amount"})

    processed, desc, info = process_payos_paid_order(order_code, amount_vnd)
    if not processed:
        logger.warning(f"PayOS webhook ignored: {desc} | order={order_code} | amount={amount_vnd} | info={info}")
        return JSONResponse({"code": "00", "desc": desc})

    target_id = info["target_id"]
    xu = info["xu"]
    referral_bonus = info.get("referral_bonus", 0)
    credits_now, _, _ = get_user(target_id)
    logger.info(f"✅ PayOS dynamic QR nạp thành công {xu} Xu cho {target_id} | Đơn: {order_code}")

    if tg_app:
        try:
            await tg_app.bot.send_message(
                chat_id=target_id,
                text=(
                    f"🎉 <b>NẠP TỰ ĐỘNG THÀNH CÔNG!</b>\n\n"
                    f"✅ PayOS xác nhận cổng QR Động trực tuyến!\n"
                    f"💰 Số tiền giao dịch: <b>{amount_vnd:,}đ</b>\n"
                    f"🪙 Hạn mức cộng: <b>+{xu} Xu</b>\n"
                    f"💼 Số dư tài khoản hiện tại: <b>{credits_now} Xu</b>\n\n"
                    f"Cảm ơn bạn đã tin dùng dịch vụ TOAN DAAS! 🙏"
                ),
                parse_mode="HTML"
            )
            await tg_app.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"💸 <b>AUTO NẠP PAYOS (QR ĐỘNG SUCCESS)</b>\n\n"
                    f"🆔 Khách hàng: <code>{target_id}</code>\n"
                    f"💰 {amount_vnd:,}đ → +{xu} Xu\n"
                    f"📋 Order Code: <code>{order_code}</code>\n"
                    f"🎁 Referral bonus: <b>{referral_bonus} Xu</b>"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Notify error: {e}")

    return JSONResponse({"code": "00", "desc": "success"})

# ─── ENTRY POINT ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "bot:fastapi_app",
        host="0.0.0.0",
        port=PORT,
        log_level="info"
    )
