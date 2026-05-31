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
import html
import uvicorn
import time
import random
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote, urlencode
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
OPERATOR_API_TOKEN  = _env("OPERATOR_API_TOKEN")

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

# ─── MANUAL BANK FALLBACK ────────────────────────────────────────────────────
MANUAL_BANK_NAME      = _env("MANUAL_BANK_NAME", "ACB")
MANUAL_BANK_CODE      = _env("MANUAL_BANK_CODE", "ACB")
MANUAL_BANK_ACCOUNT   = _env("MANUAL_BANK_ACCOUNT", "8899397968")
MANUAL_BANK_OWNER     = _env("MANUAL_BANK_OWNER", "NGUYEN MANH TOAN")

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
        submitted_at DATETIME, status TEXT DEFAULT 'pending',
        order_code TEXT,
        amount INTEGER DEFAULT 0,
        xu INTEGER DEFAULT 0
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
        checkout_url TEXT,
        payment_link_id TEXT
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
    c.execute("""CREATE TABLE IF NOT EXISTS campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id TEXT,
        name TEXT,
        niche TEXT,
        platforms TEXT,
        affiliate_url TEXT,
        pay_url TEXT,
        status TEXT DEFAULT 'active',
        created_at DATETIME
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS video_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER,
        owner_id TEXT,
        topic TEXT,
        platforms TEXT,
        affiliate_url TEXT,
        status TEXT DEFAULT 'draft',
        brief_json TEXT,
        created_at DATETIME,
        approved_at DATETIME,
        published_at DATETIME
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS social_channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id TEXT,
        platform TEXT,
        channel_name TEXT,
        account_label TEXT,
        topic_focus TEXT,
        audience TEXT,
        posting_slots TEXT,
        status TEXT DEFAULT 'active',
        notes TEXT,
        created_at DATETIME
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS affiliate_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id TEXT,
        network TEXT,
        product_name TEXT,
        niche TEXT,
        url TEXT,
        commission_note TEXT,
        price_vnd INTEGER DEFAULT 0,
        commission_rate REAL DEFAULT 0,
        target_audience TEXT,
        allowed_claims TEXT,
        blocked_claims TEXT,
        product_score INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active',
        created_at DATETIME
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS content_calendar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id TEXT,
        channel_id INTEGER,
        campaign_id INTEGER,
        affiliate_id INTEGER,
        post_date TEXT,
        platform TEXT,
        topic TEXT,
        status TEXT DEFAULT 'planned',
        notes TEXT,
        created_at DATETIME
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS production_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id TEXT,
        calendar_id INTEGER,
        campaign_id INTEGER,
        channel_id INTEGER,
        affiliate_id INTEGER,
        platform TEXT,
        topic TEXT,
        stage TEXT DEFAULT 'brief',
        status TEXT DEFAULT 'queued',
        operator_note TEXT,
        brief_text TEXT,
        asset_url TEXT,
        publish_url TEXT,
        created_at DATETIME,
        updated_at DATETIME
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS production_assets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id TEXT,
        job_id INTEGER,
        asset_type TEXT,
        url TEXT,
        file_id TEXT,
        note TEXT,
        created_at DATETIME
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS creative_variants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id TEXT,
        job_id INTEGER,
        variant_label TEXT,
        hook TEXT,
        script_angle TEXT,
        caption TEXT,
        cta TEXT,
        hashtags TEXT,
        creative_score INTEGER DEFAULT 0,
        status TEXT DEFAULT 'draft',
        note TEXT,
        created_at DATETIME,
        selected_at DATETIME
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS production_manifests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id TEXT,
        job_id INTEGER,
        variant_id INTEGER DEFAULT 0,
        manifest_json TEXT,
        status TEXT DEFAULT 'draft',
        created_at DATETIME,
        updated_at DATETIME
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS production_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id TEXT,
        job_id INTEGER,
        manifest_id INTEGER DEFAULT 0,
        task_type TEXT,
        tool TEXT,
        scene_no INTEGER DEFAULT 0,
        title TEXT,
        prompt TEXT,
        status TEXT DEFAULT 'queued',
        output_url TEXT,
        note TEXT,
        created_at DATETIME,
        updated_at DATETIME
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS performance_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id TEXT,
        job_id INTEGER,
        variant_id INTEGER DEFAULT 0,
        channel_id INTEGER,
        affiliate_id INTEGER,
        platform TEXT,
        event_type TEXT,
        value INTEGER DEFAULT 0,
        amount INTEGER DEFAULT 0,
        note TEXT,
        created_at DATETIME
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS trend_candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id TEXT,
        niche TEXT,
        platform TEXT,
        title TEXT,
        source_url TEXT,
        source_name TEXT,
        summary TEXT,
        channel_id INTEGER DEFAULT 0,
        campaign_id INTEGER DEFAULT 0,
        affiliate_id INTEGER DEFAULT 0,
        trend_score INTEGER DEFAULT 0,
        affiliate_fit_score INTEGER DEFAULT 0,
        competition_score INTEGER DEFAULT 0,
        score_reason TEXT,
        status TEXT DEFAULT 'new',
        created_at DATETIME
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS publish_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id TEXT,
        job_id INTEGER,
        channel_id INTEGER,
        platform TEXT,
        mode TEXT DEFAULT 'manual',
        status TEXT DEFAULT 'queued',
        scheduled_at TEXT,
        publish_url TEXT,
        note TEXT,
        created_at DATETIME,
        updated_at DATETIME
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
        ("payment_link_id", "TEXT"),
    ]:
        try:
            c.execute(f"ALTER TABLE payos_orders ADD COLUMN {col} {col_type}")
        except Exception:
            pass
    for col, col_type in [
        ("order_code", "TEXT"),
        ("amount", "INTEGER DEFAULT 0"),
        ("xu", "INTEGER DEFAULT 0"),
    ]:
        try:
            c.execute(f"ALTER TABLE pending_deposits ADD COLUMN {col} {col_type}")
        except Exception:
            pass
    for table, columns in {
        "campaigns": [
            ("pay_url", "TEXT"),
            ("status", "TEXT DEFAULT 'active'"),
        ],
        "video_jobs": [
            ("approved_at", "DATETIME"),
            ("published_at", "DATETIME"),
        ],
        "social_channels": [
            ("notes", "TEXT"),
            ("status", "TEXT DEFAULT 'active'"),
            ("publish_mode", "TEXT DEFAULT 'manual'"),
            ("token_env", "TEXT"),
            ("page_id", "TEXT"),
        ],
        "affiliate_links": [
            ("commission_note", "TEXT"),
            ("price_vnd", "INTEGER DEFAULT 0"),
            ("commission_rate", "REAL DEFAULT 0"),
            ("target_audience", "TEXT"),
            ("allowed_claims", "TEXT"),
            ("blocked_claims", "TEXT"),
            ("product_score", "INTEGER DEFAULT 0"),
            ("status", "TEXT DEFAULT 'active'"),
        ],
        "content_calendar": [
            ("notes", "TEXT"),
            ("status", "TEXT DEFAULT 'planned'"),
        ],
        "production_jobs": [
            ("operator_note", "TEXT"),
            ("brief_text", "TEXT"),
            ("asset_url", "TEXT"),
            ("publish_url", "TEXT"),
            ("updated_at", "DATETIME"),
        ],
        "production_assets": [
            ("file_id", "TEXT"),
            ("note", "TEXT"),
        ],
        "creative_variants": [
            ("variant_label", "TEXT"),
            ("hook", "TEXT"),
            ("script_angle", "TEXT"),
            ("caption", "TEXT"),
            ("cta", "TEXT"),
            ("hashtags", "TEXT"),
            ("creative_score", "INTEGER DEFAULT 0"),
            ("status", "TEXT DEFAULT 'draft'"),
            ("note", "TEXT"),
            ("selected_at", "DATETIME"),
        ],
        "production_manifests": [
            ("variant_id", "INTEGER DEFAULT 0"),
            ("manifest_json", "TEXT"),
            ("status", "TEXT DEFAULT 'draft'"),
            ("updated_at", "DATETIME"),
        ],
        "production_tasks": [
            ("manifest_id", "INTEGER DEFAULT 0"),
            ("task_type", "TEXT"),
            ("tool", "TEXT"),
            ("scene_no", "INTEGER DEFAULT 0"),
            ("title", "TEXT"),
            ("prompt", "TEXT"),
            ("status", "TEXT DEFAULT 'queued'"),
            ("output_url", "TEXT"),
            ("note", "TEXT"),
            ("updated_at", "DATETIME"),
        ],
        "performance_events": [
            ("variant_id", "INTEGER DEFAULT 0"),
            ("value", "INTEGER DEFAULT 0"),
            ("amount", "INTEGER DEFAULT 0"),
            ("note", "TEXT"),
        ],
        "trend_candidates": [
            ("channel_id", "INTEGER DEFAULT 0"),
            ("campaign_id", "INTEGER DEFAULT 0"),
            ("affiliate_id", "INTEGER DEFAULT 0"),
            ("trend_score", "INTEGER DEFAULT 0"),
            ("affiliate_fit_score", "INTEGER DEFAULT 0"),
            ("competition_score", "INTEGER DEFAULT 0"),
            ("score_reason", "TEXT"),
            ("status", "TEXT DEFAULT 'new'"),
        ],
        "publish_queue": [
            ("mode", "TEXT DEFAULT 'manual'"),
            ("status", "TEXT DEFAULT 'queued'"),
            ("scheduled_at", "TEXT"),
            ("publish_url", "TEXT"),
            ("note", "TEXT"),
            ("updated_at", "DATETIME"),
        ],
    }.items():
        for col, col_type in columns:
            try:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
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

def update_order_checkout_info(order_code, checkout_url, payment_link_id=""):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "UPDATE payos_orders SET checkout_url=?, payment_link_id=? WHERE order_code=?",
        (checkout_url, str(payment_link_id), str(order_code))
    )
    conn.commit()
    conn.close()

def get_order_payment_link_id(order_code):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT payment_link_id FROM payos_orders WHERE order_code=?", (str(order_code),))
    row = c.fetchone()
    conn.close()
    return row[0] if row and row[0] else ""

def generate_order_code() -> int:
    # payOS hoạt động ổn định hơn với orderCode trong phạm vi số nguyên 32-bit.
    base = int(time.time())
    for _ in range(20):
        code = base + random.randint(0, 999)
        if not get_order(code):
            return code
    return base

def make_payos_return_url(context: ContextTypes.DEFAULT_TYPE) -> str:
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL.rstrip("/") + "/landing"
    bot_name = context.bot.username or BOT_USERNAME
    return f"https://t.me/{bot_name}" if bot_name else "https://t.me"

def make_payos_description(pkg_key: str) -> str:
    # payOS giới hạn 9 ký tự mô tả với một số kênh ngân hàng chưa liên kết.
    return f"DAAS{pkg_key.upper()}"[:9]

def sign_payos_payment_request(data: dict, variant: str = "payos_sorted") -> tuple[str, str]:
    if variant == "faq_field_order":
        raw_str = (
            f"amount={data['amount']}"
            f"&orderCode={data['orderCode']}"
            f"&description={data['description']}"
            f"&returnUrl={data['returnUrl']}"
            f"&cancelUrl={data['cancelUrl']}"
        )
    elif variant == "payload_order":
        raw_str = (
            f"orderCode={data['orderCode']}"
            f"&amount={data['amount']}"
            f"&description={data['description']}"
            f"&cancelUrl={data['cancelUrl']}"
            f"&returnUrl={data['returnUrl']}"
        )
    else:
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

def manual_payment_text(uid: int, amount: int, xu: int, order_code: int, reason: str = "") -> str:
    reason_line = f"⚠️ {reason}\n\n" if reason else ""
    return (
        f"{reason_line}"
        f"🏦 <b>NẠP XU THỦ CÔNG</b>\n\n"
        f"📋 Gói: <b>{amount:,}đ → +{xu} Xu</b>\n"
        f"👤 ID Telegram: <code>{uid}</code>\n"
        f"🆔 Mã đơn: <code>{order_code}</code>\n\n"
        f"<b>Thông tin chuyển khoản:</b>\n"
        f"• Ngân hàng: <b>{MANUAL_BANK_NAME}</b>\n"
        f"• Số tài khoản: <code>{MANUAL_BANK_ACCOUNT}</code>\n"
        f"• Chủ tài khoản: <b>{MANUAL_BANK_OWNER}</b>\n"
        f"• Số tiền: <b>{amount:,}đ</b>\n"
        f"• Nội dung: <code>DAAS {uid} {order_code}</code>\n\n"
        f"📸 Sau khi chuyển khoản, gửi ảnh bill ngay tại đây. Admin sẽ kiểm tra và cộng <b>{xu} Xu</b>."
    )

def manual_qr_url(uid: int, amount: int, order_code: int) -> str:
    params = {
        "amount": int(amount),
        "addInfo": f"DAAS {uid} {order_code}",
        "accountName": MANUAL_BANK_OWNER,
    }
    bank_code = quote(MANUAL_BANK_CODE, safe="")
    account = quote(MANUAL_BANK_ACCOUNT, safe="")
    return f"https://img.vietqr.io/image/{bank_code}-{account}-compact2.png?{urlencode(params)}"

async def send_manual_payment(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    uid: int,
    amount: int,
    xu: int,
    order_code: int,
    reason: str = "",
):
    text = manual_payment_text(uid, amount, xu, order_code, reason)
    try:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=manual_qr_url(uid, amount, order_code),
            caption=text,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Manual QR send error: {e}")
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

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

def create_campaign(owner_id, name, niche, platforms, affiliate_url="", pay_url="") -> int:
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "INSERT INTO campaigns (owner_id, name, niche, platforms, affiliate_url, pay_url, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (str(owner_id), name, niche, platforms, affiliate_url, pay_url, "active", now_text())
    )
    campaign_id = c.lastrowid
    conn.commit()
    conn.close()
    return campaign_id

def list_campaigns(owner_id, limit=8):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "SELECT id, name, niche, platforms, affiliate_url, status FROM campaigns WHERE owner_id=? ORDER BY id DESC LIMIT ?",
        (str(owner_id), limit)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def get_campaign(campaign_id, owner_id=None):
    conn = db_connect()
    c = conn.cursor()
    if owner_id is None:
        c.execute("SELECT id, owner_id, name, niche, platforms, affiliate_url, pay_url, status FROM campaigns WHERE id=?", (campaign_id,))
    else:
        c.execute(
            "SELECT id, owner_id, name, niche, platforms, affiliate_url, pay_url, status FROM campaigns WHERE id=? AND owner_id=?",
            (campaign_id, str(owner_id))
        )
    row = c.fetchone()
    conn.close()
    return row

def create_video_job(campaign_id, owner_id, topic, platforms, affiliate_url, brief_json) -> int:
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "INSERT INTO video_jobs (campaign_id, owner_id, topic, platforms, affiliate_url, status, brief_json, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (campaign_id, str(owner_id), topic, platforms, affiliate_url, "draft", brief_json, now_text())
    )
    job_id = c.lastrowid
    conn.commit()
    conn.close()
    return job_id

def get_video_job(job_id, owner_id=None):
    conn = db_connect()
    c = conn.cursor()
    if owner_id is None:
        c.execute("SELECT id, campaign_id, owner_id, topic, platforms, affiliate_url, status, brief_json FROM video_jobs WHERE id=?", (job_id,))
    else:
        c.execute(
            "SELECT id, campaign_id, owner_id, topic, platforms, affiliate_url, status, brief_json FROM video_jobs WHERE id=? AND owner_id=?",
            (job_id, str(owner_id))
        )
    row = c.fetchone()
    conn.close()
    return row

def update_video_job_status(job_id, status, timestamp_col=None):
    conn = db_connect()
    c = conn.cursor()
    if timestamp_col in ("approved_at", "published_at"):
        c.execute(f"UPDATE video_jobs SET status=?, {timestamp_col}=? WHERE id=?", (status, now_text(), job_id))
    else:
        c.execute("UPDATE video_jobs SET status=? WHERE id=?", (status, job_id))
    conn.commit()
    conn.close()

def campaign_stats(owner_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM campaigns WHERE owner_id=?", (str(owner_id),))
    total_campaigns = c.fetchone()[0]
    c.execute("SELECT status, COUNT(*) FROM video_jobs WHERE owner_id=? GROUP BY status", (str(owner_id),))
    job_counts = dict(c.fetchall())
    c.execute("SELECT id, topic, platforms, status, created_at FROM video_jobs WHERE owner_id=? ORDER BY id DESC LIMIT 8", (str(owner_id),))
    recent_jobs = c.fetchall()
    conn.close()
    return total_campaigns, job_counts, recent_jobs

def create_social_channel(owner_id, platform, channel_name, account_label="", topic_focus="", audience="", posting_slots="", notes="", publish_mode="manual", token_env="", page_id="") -> int:
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """INSERT INTO social_channels
        (owner_id, platform, channel_name, account_label, topic_focus, audience, posting_slots, status, notes, publish_mode, token_env, page_id, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (str(owner_id), platform, channel_name, account_label, topic_focus, audience, posting_slots, "active", notes, publish_mode, token_env, page_id, now_text())
    )
    channel_id = c.lastrowid
    conn.commit()
    conn.close()
    return channel_id

def list_social_channels(owner_id, limit=30):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT id, platform, channel_name, account_label, topic_focus, audience, posting_slots, status
        FROM social_channels WHERE owner_id=? ORDER BY id DESC LIMIT ?""",
        (str(owner_id), limit)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def get_social_channel(channel_id, owner_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT id, platform, channel_name, account_label, topic_focus, audience, posting_slots, status
        FROM social_channels WHERE id=? AND owner_id=?""",
        (channel_id, str(owner_id))
    )
    row = c.fetchone()
    conn.close()
    return row

def set_social_publish_config(owner_id, channel_id, publish_mode=None, token_env=None, page_id=None):
    updates = []
    params = []
    if publish_mode:
        updates.append("publish_mode=?")
        params.append(publish_mode)
    if token_env is not None:
        updates.append("token_env=?")
        params.append(token_env)
    if page_id is not None:
        updates.append("page_id=?")
        params.append(page_id)
    if not updates:
        return False
    params.extend([channel_id, str(owner_id)])
    conn = db_connect()
    c = conn.cursor()
    c.execute(f"UPDATE social_channels SET {', '.join(updates)} WHERE id=? AND owner_id=?", params)
    changed = c.rowcount
    conn.commit()
    conn.close()
    return changed > 0

def list_social_publish_readiness(owner_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT id, platform, channel_name, account_label, status, publish_mode, token_env, page_id
        FROM social_channels WHERE owner_id=? ORDER BY id DESC""",
        (str(owner_id),)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def channel_publish_readiness(row):
    cid, platform, channel_name, account_label, status, publish_mode, token_env, page_id = row
    publish_mode = publish_mode or "manual"
    if publish_mode == "manual":
        return "manual_ready", "Đăng thủ công, không cần token."
    if publish_mode != "api":
        return "blocked", f"publish_mode không hợp lệ: {publish_mode}"
    if not token_env:
        return "missing_token_env", "Chưa khai báo tên biến môi trường token."
    if not _env(token_env):
        return "missing_secret", f"Biến môi trường {token_env} chưa có giá trị trên server."
    platform_l = (platform or "").lower()
    if platform_l in {"facebook", "fb", "meta"} and not page_id:
        return "missing_page_id", "Facebook/Meta API cần page_id hoặc account id."
    if platform_l in {"onlyfans"}:
        return "manual_required", "OnlyFans không có API public ổn định; giữ manual hoặc tool chính thức được phép."
    return "api_ready", "Đã có cấu hình API cơ bản. Vẫn cần OAuth/quyền đăng chính thức của nền tảng."

def create_affiliate_link(owner_id, network, product_name, niche="", url="", commission_note="", price_vnd=0, commission_rate=0, target_audience="", allowed_claims="", blocked_claims="", product_score=0) -> int:
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """INSERT INTO affiliate_links
        (owner_id, network, product_name, niche, url, commission_note, price_vnd, commission_rate,
         target_audience, allowed_claims, blocked_claims, product_score, status, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            str(owner_id), network, product_name, niche, url, commission_note,
            int(price_vnd or 0), float(commission_rate or 0), target_audience,
            allowed_claims, blocked_claims, int(product_score or 0), "active", now_text()
        )
    )
    affiliate_id = c.lastrowid
    conn.commit()
    conn.close()
    return affiliate_id

def list_affiliate_links(owner_id, limit=30):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT id, network, product_name, niche, url, commission_note, status,
                  price_vnd, commission_rate, target_audience, allowed_claims, blocked_claims, product_score
        FROM affiliate_links WHERE owner_id=? ORDER BY id DESC LIMIT ?""",
        (str(owner_id), limit)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def get_affiliate_link(affiliate_id, owner_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT id, network, product_name, niche, url, commission_note, status,
                  price_vnd, commission_rate, target_audience, allowed_claims, blocked_claims, product_score
        FROM affiliate_links WHERE id=? AND owner_id=?""",
        (affiliate_id, str(owner_id))
    )
    row = c.fetchone()
    conn.close()
    return row

def update_affiliate_profile(owner_id, affiliate_id, **fields):
    allowed = {
        "network", "product_name", "niche", "url", "commission_note", "price_vnd",
        "commission_rate", "target_audience", "allowed_claims", "blocked_claims",
        "product_score", "status"
    }
    updates = []
    params = []
    for key, value in fields.items():
        if key not in allowed or value is None:
            continue
        updates.append(f"{key}=?")
        params.append(value)
    if not updates:
        return False
    params.extend([affiliate_id, str(owner_id)])
    conn = db_connect()
    c = conn.cursor()
    c.execute(f"UPDATE affiliate_links SET {', '.join(updates)} WHERE id=? AND owner_id=?", params)
    changed = c.rowcount
    conn.commit()
    conn.close()
    return changed > 0

def affiliate_match_score(affiliate, niche="", trend_text="", platform=""):
    (
        aid, network, product_name, aff_niche, url, commission_note, status,
        price_vnd, commission_rate, target_audience, allowed_claims, blocked_claims, product_score
    ) = affiliate
    text = f"{niche} {trend_text} {platform}".lower()
    tokens = (
        tokenize_text(product_name) + tokenize_text(aff_niche) + tokenize_text(network) +
        tokenize_text(target_audience) + tokenize_text(allowed_claims)
    )
    hits = sum(1 for token in tokens[:30] if token in text)
    score = int(product_score or 0) + hits * 8
    if commission_rate:
        score += min(20, int(float(commission_rate) * 2))
    if commission_note:
        score += 5
    if url:
        score += 5
    blocked_hits = sum(1 for token in tokenize_text(blocked_claims)[:20] if token in text)
    score -= blocked_hits * 12
    return clamp_score(score), hits, blocked_hits

def list_affiliate_matches(owner_id, niche="", trend_text="", platform="", limit=10):
    rows = list_affiliate_links(owner_id, limit=100)
    active_rows = [row for row in rows if (row[6] or "active") == "active"]
    ranked = []
    for row in active_rows:
        score, hits, blocked_hits = affiliate_match_score(row, niche, trend_text, platform)
        ranked.append((score, hits, blocked_hits, row))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[:limit]

def create_calendar_slot(owner_id, channel_id, campaign_id, affiliate_id, post_date, platform, topic, notes="") -> int:
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """INSERT INTO content_calendar
        (owner_id, channel_id, campaign_id, affiliate_id, post_date, platform, topic, status, notes, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (str(owner_id), channel_id, campaign_id, affiliate_id, post_date, platform, topic, "planned", notes, now_text())
    )
    slot_id = c.lastrowid
    conn.commit()
    conn.close()
    return slot_id

def list_calendar_slots(owner_id, limit=30):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT cc.id, cc.post_date, cc.platform, sc.channel_name, cc.topic, cc.status, cc.campaign_id, cc.affiliate_id
        FROM content_calendar cc
        LEFT JOIN social_channels sc ON sc.id = cc.channel_id
        WHERE cc.owner_id=?
        ORDER BY cc.post_date ASC, cc.id DESC
        LIMIT ?""",
        (str(owner_id), limit)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def get_calendar_slot(slot_id, owner_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT cc.id, cc.owner_id, cc.channel_id, cc.campaign_id, cc.affiliate_id, cc.post_date,
                  cc.platform, cc.topic, cc.status, cc.notes,
                  sc.channel_name, sc.account_label, sc.topic_focus, sc.audience,
                  al.network, al.product_name, al.url, al.commission_note
        FROM content_calendar cc
        LEFT JOIN social_channels sc ON sc.id = cc.channel_id
        LEFT JOIN affiliate_links al ON al.id = cc.affiliate_id
        WHERE cc.id=? AND cc.owner_id=?""",
        (slot_id, str(owner_id))
    )
    row = c.fetchone()
    conn.close()
    return row

def create_production_job(owner_id, calendar_id, campaign_id, channel_id, affiliate_id, platform, topic, brief_text="", note="") -> int:
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """INSERT INTO production_jobs
        (owner_id, calendar_id, campaign_id, channel_id, affiliate_id, platform, topic,
         stage, status, operator_note, brief_text, asset_url, publish_url, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            str(owner_id), calendar_id, campaign_id, channel_id, affiliate_id, platform, topic,
            "brief", "queued", note, brief_text, "", "", now_text(), now_text()
        )
    )
    job_id = c.lastrowid
    if calendar_id:
        c.execute("UPDATE content_calendar SET status=? WHERE id=? AND owner_id=?", ("in_production", calendar_id, str(owner_id)))
    conn.commit()
    conn.close()
    return job_id

def list_production_jobs(owner_id, limit=20):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT pj.id, pj.stage, pj.status, pj.platform, pj.topic, sc.channel_name, al.product_name, pj.updated_at
        FROM production_jobs pj
        LEFT JOIN social_channels sc ON sc.id = pj.channel_id
        LEFT JOIN affiliate_links al ON al.id = pj.affiliate_id
        WHERE pj.owner_id=?
        ORDER BY pj.id DESC
        LIMIT ?""",
        (str(owner_id), limit)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def operator_dashboard_data(owner_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM social_channels WHERE owner_id=? AND status='active'", (str(owner_id),))
    active_channels = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM affiliate_links WHERE owner_id=? AND status='active'", (str(owner_id),))
    active_affiliates = c.fetchone()[0]
    c.execute(
        """SELECT status, COUNT(*) FROM content_calendar
        WHERE owner_id=? GROUP BY status""",
        (str(owner_id),)
    )
    calendar_counts = dict(c.fetchall())
    c.execute(
        """SELECT stage, status, COUNT(*) FROM production_jobs
        WHERE owner_id=? GROUP BY stage, status ORDER BY stage, status""",
        (str(owner_id),)
    )
    pipeline_counts = c.fetchall()
    c.execute(
        """SELECT pj.id, pj.stage, pj.status, pj.platform, pj.topic, sc.channel_name, al.product_name, pj.updated_at
        FROM production_jobs pj
        LEFT JOIN social_channels sc ON sc.id = pj.channel_id
        LEFT JOIN affiliate_links al ON al.id = pj.affiliate_id
        WHERE pj.owner_id=? AND pj.status IN ('queued','working','waiting','blocked','ready')
        ORDER BY
            CASE pj.status
                WHEN 'blocked' THEN 0
                WHEN 'waiting' THEN 1
                WHEN 'working' THEN 2
                WHEN 'queued' THEN 3
                ELSE 4
            END,
            pj.updated_at ASC
        LIMIT 10""",
        (str(owner_id),)
    )
    active_jobs = c.fetchall()
    c.execute(
        """SELECT cc.id, cc.post_date, cc.platform, sc.channel_name, cc.topic, cc.status, cc.campaign_id, cc.affiliate_id
        FROM content_calendar cc
        LEFT JOIN social_channels sc ON sc.id = cc.channel_id
        WHERE cc.owner_id=? AND cc.status IN ('planned','in_production')
        ORDER BY cc.post_date ASC, cc.id DESC
        LIMIT 10""",
        (str(owner_id),)
    )
    upcoming_slots = c.fetchall()
    conn.close()
    return active_channels, active_affiliates, calendar_counts, pipeline_counts, active_jobs, upcoming_slots

def operator_daily_data(owner_id, days=1):
    since = (datetime.now() - timedelta(days=max(1, int(days)))).strftime("%Y-%m-%d %H:%M:%S")
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT status, COUNT(*) FROM production_jobs
        WHERE owner_id=? AND created_at>=?
        GROUP BY status ORDER BY status""",
        (str(owner_id), since)
    )
    job_status_counts = c.fetchall()
    c.execute(
        """SELECT stage, COUNT(*) FROM production_jobs
        WHERE owner_id=? AND updated_at>=?
        GROUP BY stage ORDER BY stage""",
        (str(owner_id), since)
    )
    job_stage_counts = c.fetchall()
    c.execute(
        """SELECT status, COUNT(*) FROM publish_queue
        WHERE owner_id=? AND updated_at>=?
        GROUP BY status ORDER BY status""",
        (str(owner_id), since)
    )
    queue_status_counts = c.fetchall()
    c.execute(
        """SELECT event_type, COALESCE(SUM(value),0), COALESCE(SUM(amount),0), COUNT(*)
        FROM performance_events
        WHERE owner_id=? AND created_at>=?
        GROUP BY event_type ORDER BY event_type""",
        (str(owner_id), since)
    )
    performance_counts = c.fetchall()
    c.execute(
        """SELECT pj.id, pj.stage, pj.status, pj.platform, pj.topic, sc.channel_name, al.product_name, pj.updated_at
        FROM production_jobs pj
        LEFT JOIN social_channels sc ON sc.id = pj.channel_id
        LEFT JOIN affiliate_links al ON al.id = pj.affiliate_id
        WHERE pj.owner_id=? AND pj.updated_at>=?
        ORDER BY pj.updated_at DESC, pj.id DESC
        LIMIT 8""",
        (str(owner_id), since)
    )
    recent_jobs = c.fetchall()
    c.execute(
        """SELECT pq.id, pq.job_id, pq.platform, sc.channel_name, pq.mode, pq.status, pq.scheduled_at, pj.topic
        FROM publish_queue pq
        LEFT JOIN social_channels sc ON sc.id = pq.channel_id
        LEFT JOIN production_jobs pj ON pj.id = pq.job_id
        WHERE pq.owner_id=? AND pq.status IN ('queued','scheduled','publishing','blocked')
        ORDER BY pq.updated_at DESC, pq.id DESC
        LIMIT 8""",
        (str(owner_id),)
    )
    open_queue = c.fetchall()
    conn.close()
    return since, job_status_counts, job_stage_counts, queue_status_counts, performance_counts, recent_jobs, open_queue

def get_production_job(job_id, owner_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT pj.id, pj.calendar_id, pj.campaign_id, pj.channel_id, pj.affiliate_id, pj.platform, pj.topic,
                  pj.stage, pj.status, pj.operator_note, pj.brief_text, pj.asset_url, pj.publish_url,
                  sc.channel_name, sc.account_label, al.network, al.product_name, al.url
        FROM production_jobs pj
        LEFT JOIN social_channels sc ON sc.id = pj.channel_id
        LEFT JOIN affiliate_links al ON al.id = pj.affiliate_id
        WHERE pj.id=? AND pj.owner_id=?""",
        (job_id, str(owner_id))
    )
    row = c.fetchone()
    conn.close()
    return row

def update_production_job(job_id, owner_id, stage=None, status=None, note=None, asset_url=None, publish_url=None):
    updates = []
    params = []
    if stage:
        updates.append("stage=?")
        params.append(stage)
    if status:
        updates.append("status=?")
        params.append(status)
    if note is not None:
        updates.append("operator_note=?")
        params.append(note)
    if asset_url is not None:
        updates.append("asset_url=?")
        params.append(asset_url)
    if publish_url is not None:
        updates.append("publish_url=?")
        params.append(publish_url)
    updates.append("updated_at=?")
    params.append(now_text())
    params.extend([job_id, str(owner_id)])
    conn = db_connect()
    c = conn.cursor()
    c.execute(f"UPDATE production_jobs SET {', '.join(updates)} WHERE id=? AND owner_id=?", params)
    changed = c.rowcount
    conn.commit()
    conn.close()
    return changed > 0

def add_production_asset(owner_id, job_id, asset_type, url="", file_id="", note=""):
    job = get_production_job(job_id, owner_id)
    if not job:
        return False, None
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """INSERT INTO production_assets
        (owner_id, job_id, asset_type, url, file_id, note, created_at)
        VALUES (?,?,?,?,?,?,?)""",
        (str(owner_id), job_id, asset_type, url, file_id, note, now_text())
    )
    asset_id = c.lastrowid
    conn.commit()
    conn.close()
    if url:
        update_production_job(job_id, owner_id, asset_url=url)
    return True, asset_id

def list_production_assets(owner_id, job_id, limit=20):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT id, asset_type, url, file_id, note, created_at
        FROM production_assets
        WHERE owner_id=? AND job_id=?
        ORDER BY id DESC LIMIT ?""",
        (str(owner_id), job_id, limit)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def job_report_data(owner_id, job_id):
    job = get_production_job(job_id, owner_id)
    if not job:
        return None
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT id, asset_type, url, file_id, note, created_at
        FROM production_assets
        WHERE owner_id=? AND job_id=?
        ORDER BY id DESC LIMIT 8""",
        (str(owner_id), job_id)
    )
    assets = c.fetchall()
    c.execute(
        """SELECT id, mode, status, scheduled_at, publish_url, note, updated_at
        FROM publish_queue
        WHERE owner_id=? AND job_id=?
        ORDER BY id DESC LIMIT 5""",
        (str(owner_id), job_id)
    )
    queue_items = c.fetchall()
    c.execute(
        """SELECT event_type, COALESCE(SUM(value),0), COALESCE(SUM(amount),0), COUNT(*)
        FROM performance_events
        WHERE owner_id=? AND job_id=?
        GROUP BY event_type ORDER BY event_type""",
        (str(owner_id), job_id)
    )
    performance = c.fetchall()
    conn.close()
    return job, assets, queue_items, performance

def list_publish_queue_for_job(owner_id, job_id, limit=5):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT id, mode, status, scheduled_at, publish_url, note, updated_at
        FROM publish_queue
        WHERE owner_id=? AND job_id=?
        ORDER BY id DESC LIMIT ?""",
        (str(owner_id), job_id, limit)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def production_readiness_data(owner_id, job_id):
    job = get_production_job(job_id, owner_id)
    if not job:
        return None
    (
        jid, calendar_id, campaign_id, channel_id, affiliate_id, platform, topic, stage, status,
        note, brief, asset_url, publish_url, channel_name, account_label, network, product_name, affiliate_url
    ) = job
    assets = list_production_assets(owner_id, job_id, limit=80)
    variants = list_creative_variants(owner_id, job_id, limit=80)
    manifests = list_production_manifests(owner_id, job_id, limit=5)
    tasks = list_production_tasks(owner_id, job_id=job_id, limit=120)
    queue_items = list_publish_queue_for_job(owner_id, job_id, limit=5)

    selected_variant = next((row for row in variants if (row[8] or "").lower() == "selected"), None)
    final_asset = next(
        (
            row for row in assets
            if (row[1] or "").lower() == "final_video" and (row[2] or row[3] or asset_url)
        ),
        None
    )
    raw_assets = [row for row in assets if (row[1] or "").lower() in {"raw_video", "scene_video", "source"}]
    voice_asset = next((row for row in assets if (row[1] or "").lower() in {"voice", "audio"} and (row[2] or row[3])), None)
    queue_open = next((row for row in queue_items if (row[2] or "").lower() in {"queued", "scheduled", "publishing", "published"}), None)
    blocked_tasks = [row for row in tasks if (row[7] or "").lower() == "blocked"]
    active_tasks = [row for row in tasks if (row[7] or "").lower() not in {"cancelled"}]

    def tasks_by_type(task_type):
        return [row for row in active_tasks if (row[3] or "").lower() == task_type]

    def tasks_done(task_rows):
        return bool(task_rows) and all((row[7] or "").lower() in {"ready", "done"} for row in task_rows)

    visual_tasks = tasks_by_type("visual_scene")
    voice_tasks = tasks_by_type("voice")
    edit_tasks = tasks_by_type("edit")
    review_tasks = tasks_by_type("review")

    review_ok = (
        tasks_done(review_tasks)
        or (stage or "").lower() in {"review", "publish", "done"}
        and (status or "").lower() in {"ready", "queued", "published"}
    )
    final_ok = bool(final_asset or publish_url)
    checks = [
        ("brief", bool(brief), "Có brief sản xuất.", f"/video_job {job_id} hoặc /operator_next id={job_id} stage=script"),
        ("channel", bool(channel_id), "Có kênh/account để đăng.", "/channel_add platform=tiktok name=... account=..."),
        ("affiliate", bool(affiliate_url), "Có link affiliate gắn sản phẩm.", "/affiliate_add network=... product=... url=..."),
        ("creative_selected", bool(selected_variant), "Đã chọn creative variant thắng.", f"/creative_test job={job_id} n=5 rồi /creative_select id=<VARIANT_ID>"),
        ("manifest", bool(manifests), "Có production manifest.", f"/manifest job={job_id} duration=45"),
        ("tasks", bool(active_tasks), "Đã tách task sản xuất.", f"/task_plan job={job_id}"),
        ("visuals", tasks_done(visual_tasks) or bool(raw_assets) or final_ok, "Visual scene đã có output hoặc final video.", f"/next_task job={job_id}"),
        ("voice", tasks_done(voice_tasks) or bool(voice_asset) or final_ok, "Voice/audio đã có output hoặc final video.", f"/next_task job={job_id}"),
        ("edit_final", final_ok or tasks_done(edit_tasks), "Có final video hoặc edit task đã ready.", f"/next_task job={job_id}"),
        ("review", review_ok, "Đã qua review gate.", f"/review_gate job={job_id}"),
        ("queue_or_published", bool(queue_open or publish_url or (status or "").lower() == "published"), "Đã vào hàng đợi hoặc đã đăng.", f"/publish_pack job={job_id} rồi /queue_publish job={job_id} mode=manual"),
    ]
    if blocked_tasks:
        checks.append(("blocked_tasks", False, f"Có {len(blocked_tasks)} task bị blocked.", f"/tasks job={job_id}"))

    missing = [row for row in checks if not row[1]]
    core_missing = [row for row in missing if row[0] != "queue_or_published"]
    if not core_missing and not queue_open and not publish_url and (status or "").lower() != "published":
        level = "READY_TO_QUEUE"
        next_action = f"/publish_pack job={job_id} rồi /queue_publish job={job_id} mode=manual"
    elif not missing:
        level = "READY_TO_PUBLISH"
        next_action = f"/publish_queue hoặc /mark_published job={job_id} url=https://..."
    else:
        level = "BLOCKED"
        next_action = missing[0][3]

    return {
        "job": job,
        "assets": assets,
        "variants": variants,
        "manifests": manifests,
        "tasks": tasks,
        "queue_items": queue_items,
        "checks": checks,
        "missing": missing,
        "level": level,
        "next_action": next_action,
        "selected_variant": selected_variant,
        "final_asset": final_asset,
        "blocked_tasks": blocked_tasks,
    }

def create_creative_variant(owner_id, job_id, variant_label, hook="", script_angle="", caption="", cta="", hashtags="", creative_score=0, note=""):
    job = get_production_job(job_id, owner_id)
    if not job:
        return False, None
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """INSERT INTO creative_variants
        (owner_id, job_id, variant_label, hook, script_angle, caption, cta, hashtags, creative_score, status, note, created_at, selected_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            str(owner_id), job_id, variant_label, hook, script_angle, caption, cta, hashtags,
            int(creative_score or 0), "draft", note, now_text(), None
        )
    )
    variant_id = c.lastrowid
    conn.commit()
    conn.close()
    return True, variant_id

def list_creative_variants(owner_id, job_id, limit=20):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT id, variant_label, hook, script_angle, caption, cta, hashtags, creative_score, status, note, created_at, selected_at
        FROM creative_variants
        WHERE owner_id=? AND job_id=?
        ORDER BY creative_score DESC, id ASC
        LIMIT ?""",
        (str(owner_id), job_id, limit)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def get_creative_variant(owner_id, variant_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT id, job_id, variant_label, hook, script_angle, caption, cta, hashtags, creative_score, status, note
        FROM creative_variants WHERE owner_id=? AND id=?""",
        (str(owner_id), variant_id)
    )
    row = c.fetchone()
    conn.close()
    return row

def select_creative_variant(owner_id, variant_id):
    variant = get_creative_variant(owner_id, variant_id)
    if not variant:
        return False, None
    _, job_id, variant_label, hook, script_angle, caption, cta, hashtags, creative_score, status, note = variant
    conn = db_connect()
    c = conn.cursor()
    c.execute("UPDATE creative_variants SET status='draft', selected_at=NULL WHERE owner_id=? AND job_id=?", (str(owner_id), job_id))
    c.execute("UPDATE creative_variants SET status='selected', selected_at=? WHERE owner_id=? AND id=?", (now_text(), str(owner_id), variant_id))
    conn.commit()
    conn.close()
    job_note = f"creative_variant:{variant_id} {variant_label or ''} | hook={truncate_text(hook, 180)} | cta={truncate_text(cta, 120)}"
    update_production_job(job_id, owner_id, stage="script", status="working", note=job_note)
    return True, variant

def creative_report_data(owner_id, job_id):
    variants = list_creative_variants(owner_id, job_id, limit=50)
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT variant_id, event_type, COALESCE(SUM(value),0), COALESCE(SUM(amount),0), COUNT(*)
        FROM performance_events
        WHERE owner_id=? AND job_id=? AND COALESCE(variant_id,0)>0
        GROUP BY variant_id, event_type
        ORDER BY variant_id, event_type""",
        (str(owner_id), job_id)
    )
    events = c.fetchall()
    conn.close()
    return variants, events

def selected_creative_variant(owner_id, job_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT id, job_id, variant_label, hook, script_angle, caption, cta, hashtags, creative_score, status, note
        FROM creative_variants
        WHERE owner_id=? AND job_id=? AND status='selected'
        ORDER BY selected_at DESC, id DESC LIMIT 1""",
        (str(owner_id), job_id)
    )
    row = c.fetchone()
    conn.close()
    return row

def save_production_manifest(owner_id, job_id, variant_id, manifest_json, status="draft"):
    job = get_production_job(job_id, owner_id)
    if not job:
        return False, None
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """INSERT INTO production_manifests
        (owner_id, job_id, variant_id, manifest_json, status, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?)""",
        (str(owner_id), job_id, int(variant_id or 0), manifest_json, status, now_text(), now_text())
    )
    manifest_id = c.lastrowid
    conn.commit()
    conn.close()
    update_production_job(job_id, owner_id, stage="visuals", status="working", note=f"production_manifest:{manifest_id}")
    return True, manifest_id

def list_production_manifests(owner_id, job_id, limit=5):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT id, variant_id, status, manifest_json, created_at, updated_at
        FROM production_manifests
        WHERE owner_id=? AND job_id=?
        ORDER BY id DESC LIMIT ?""",
        (str(owner_id), job_id, limit)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def get_production_manifest(owner_id, manifest_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT id, job_id, variant_id, status, manifest_json, created_at, updated_at
        FROM production_manifests WHERE owner_id=? AND id=?""",
        (str(owner_id), manifest_id)
    )
    row = c.fetchone()
    conn.close()
    return row

def latest_production_manifest(owner_id, job_id):
    rows = list_production_manifests(owner_id, job_id, limit=1)
    if not rows:
        return None
    mid, variant_id, status, manifest_json, created_at, updated_at = rows[0]
    return (mid, job_id, variant_id, status, manifest_json, created_at, updated_at)

def build_manifest_prompt(job, variant=None, duration=45):
    (
        jid, calendar_id, campaign_id, channel_id, affiliate_id, platform, topic, stage, status,
        note, brief, asset_url, publish_url, channel_name, account_label, network, product_name, affiliate_url
    ) = job
    variant_text = "Chưa chọn creative variant."
    if variant:
        _, _, label, hook, angle, caption, cta, hashtags, score, v_status, v_note = variant
        variant_text = (
            f"Variant #{variant[0]} / {label or '-'} / score={score or 0}\n"
            f"Hook: {hook or '-'}\n"
            f"Angle: {angle or '-'}\n"
            f"Caption: {caption or '-'}\n"
            f"CTA: {cta or '-'}\n"
            f"Hashtags: {hashtags or '-'}"
        )
    return (
        "Bạn là AI production director cho video ngắn affiliate. Hãy tạo PRODUCTION MANIFEST dạng JSON thuần, "
        "để Claude/Gemini/Runway/Kling/Fish/CapCut/FFmpeg có thể thực thi từng bước. "
        "Không spam, không mạo danh, không cam kết thu nhập phi thực tế. Với AI influencer/OnlyFans/người mẫu, "
        "chỉ dùng nhân vật tự tạo hoặc người thật có consent rõ ràng, đủ 18 tuổi.\n\n"
        f"Job ID: #{jid}\n"
        f"Nền tảng: {platform or '-'} | Tỷ lệ: 9:16 | Độ dài mục tiêu: {duration}s\n"
        f"Kênh/account: {channel_name or channel_id or '-'} / {account_label or 'main'}\n"
        f"Topic: {topic or '-'}\n"
        f"Affiliate: {network or '-'} - {product_name or '-'} - {affiliate_url or '-'}\n"
        f"Asset hiện có: {asset_url or 'chưa có'}\n"
        f"Operator note: {note or '-'}\n\n"
        f"Creative variant:\n{variant_text}\n\n"
        f"Brief:\n{brief or 'Chưa có brief'}\n\n"
        "JSON schema bắt buộc:\n"
        "{\n"
        '  "title": "...",\n'
        '  "duration_sec": 45,\n'
        '  "format": "9:16",\n'
        '  "selected_variant_id": 0,\n'
        '  "voice": {"provider_primary":"Fish Audio HD","provider_fallback":"Edge TTS","style":"...","script":"..."},\n'
        '  "scenes": [\n'
        '    {"scene":1,"start":0,"end":5,"goal":"hook","visual_prompt":"...","video_tool":"kling|runway","on_screen_text":"...","voice_line":"...","asset_needed":"..."}\n'
        "  ],\n"
        '  "edit_instructions": {"tool":"capcut|ffmpeg","music":"...","subtitle":"...","transitions":"...","cta_overlay":"..."},\n'
        '  "publish": {"caption":"...","hashtags":"...","affiliate_placement":"...","cta":"..."},\n'
        '  "compliance_checklist": ["..."],\n'
        '  "handoff_order": ["claude","kling","fish","capcut","review_gate"]\n'
        "}"
    )

def fallback_production_manifest(job, variant=None, duration=45):
    (
        jid, calendar_id, campaign_id, channel_id, affiliate_id, platform, topic, stage, status,
        note, brief, asset_url, publish_url, channel_name, account_label, network, product_name, affiliate_url
    ) = job
    hook = topic or "video affiliate"
    caption = f"{topic or 'Nội dung mới'} - xem link gợi ý trong bio/mô tả."
    cta = "Xem link affiliate trong bio/mô tả nếu phù hợp nhu cầu."
    hashtags = "#AI #review #affiliate"
    selected_variant_id = 0
    if variant:
        selected_variant_id = variant[0]
        hook = variant[3] or hook
        caption = variant[5] or caption
        cta = variant[6] or cta
        hashtags = variant[7] or hashtags
    scenes = []
    scene_ranges = [(1, 0, 4, "hook"), (2, 4, 12, "problem"), (3, 12, 25, "demo"), (4, 25, 38, "benefit"), (5, 38, duration, "cta")]
    for scene, start, end, goal in scene_ranges:
        scenes.append({
            "scene": scene,
            "start": start,
            "end": end,
            "goal": goal,
            "visual_prompt": f"Vertical 9:16 short video scene about {topic or product_name or 'AI affiliate product'}, clean realistic tech creator style, no impersonation, no copyrighted likeness.",
            "video_tool": "kling",
            "on_screen_text": hook if scene == 1 else (product_name or topic or "TOAN DAAS"),
            "voice_line": hook if scene == 1 else f"Giải thích ngắn về {topic or product_name or 'sản phẩm'} theo góc {goal}.",
            "asset_needed": f"scene_{scene}_video.mp4",
        })
    return {
        "title": topic or "Affiliate short video",
        "duration_sec": duration,
        "format": "9:16",
        "selected_variant_id": selected_variant_id,
        "voice": {
            "provider_primary": "Fish Audio HD",
            "provider_fallback": "Edge TTS",
            "style": "giọng Việt rõ, nhanh vừa, đáng tin",
            "script": " ".join(scene["voice_line"] for scene in scenes),
        },
        "scenes": scenes,
        "edit_instructions": {
            "tool": "capcut|ffmpeg",
            "music": "nhạc nền hợp lệ, âm lượng thấp",
            "subtitle": "burn subtitle tiếng Việt, chữ rõ trên mobile",
            "transitions": "cut nhanh, không rối",
            "cta_overlay": cta,
        },
        "publish": {
            "caption": caption,
            "hashtags": hashtags,
            "affiliate_placement": affiliate_url or "bio/mô tả",
            "cta": cta,
        },
        "compliance_checklist": [
            "Không mạo danh người thật/brand.",
            "Không cam kết thu nhập/kết quả phi thực tế.",
            "Affiliate CTA minh bạch.",
            "Asset hình/voice/nhạc có quyền dùng.",
        ],
        "handoff_order": ["claude", "kling", "fish", "capcut", "review_gate"],
    }

def parse_manifest_json(raw_text, job, variant=None, duration=45):
    try:
        parsed = json.loads(raw_text)
        if isinstance(parsed, dict) and parsed.get("scenes"):
            return parsed
    except Exception:
        pass
    manifest = fallback_production_manifest(job, variant, duration)
    if raw_text:
        manifest["ai_raw_unparsed"] = truncate_text(raw_text, 1200)
    return manifest

def create_manifest_for_job(owner_id, job, variant=None, duration=45):
    job_id = job[0]
    if gemini_client or openai_client:
        raw = AgentGemini.chat(
            "Bạn là AI production director tạo production manifest JSON cho video affiliate.",
            build_manifest_prompt(job, variant, duration),
            owner_id,
            is_json=False
        )
        manifest = parse_manifest_json(raw, job, variant, duration)
    else:
        manifest = fallback_production_manifest(job, variant, duration)
    manifest["job_id"] = job_id
    manifest["generated_at"] = now_text()
    manifest["tool_policy"] = "premium_first_then_fallback"
    manifest_json = json.dumps(manifest, ensure_ascii=False, indent=2)
    ok, manifest_id = save_production_manifest(
        owner_id,
        job_id,
        variant[0] if variant else 0,
        manifest_json,
        "draft"
    )
    return ok, manifest_id, manifest

def build_manifest_handoff_prompt(job, manifest_row, target_tool):
    (
        jid, calendar_id, campaign_id, channel_id, affiliate_id, platform, topic, stage, status,
        note, brief, asset_url, publish_url, channel_name, account_label, network, product_name, affiliate_url
    ) = job
    manifest_id, _, variant_id, manifest_status, manifest_json, created_at, updated_at = manifest_row
    try:
        manifest = json.loads(manifest_json or "{}")
    except Exception:
        manifest = {}
    target_tool = (target_tool or "claude").lower()
    scenes = manifest.get("scenes") or []
    voice = manifest.get("voice") or {}
    edit = manifest.get("edit_instructions") or {}
    publish = manifest.get("publish") or {}
    compliance = manifest.get("compliance_checklist") or []
    title = manifest.get("title") or topic or f"job #{jid}"
    common = (
        f"VAI TRÒ: Bạn là {target_tool.upper()} trong AI Operator TOAN DAAS.\n"
        f"Manifest: #{manifest_id} | Job: #{jid} | Variant: {variant_id or '-'} | Platform: {platform or '-'} | Format: {manifest.get('format','9:16')}\n"
        f"Title: {title}\n"
        f"Affiliate: {network or '-'} / {product_name or '-'} / {affiliate_url or '-'}\n\n"
        "QUY TẮC:\n"
        "- Ưu tiên công cụ tốt/có phí trước, nếu lỗi/quota/hết tiền thì ghi fallback và báo admin.\n"
        "- Không spam, không mạo danh, không dùng likeness/người thật nếu chưa có consent rõ ràng, đủ 18 tuổi.\n"
        "- Không cam kết thu nhập/kết quả phi thực tế; affiliate CTA phải minh bạch.\n"
        "- Output phải có file/link/asset cần lưu vào /asset_add hoặc trạng thái cần cập nhật bằng /pipeline_set.\n\n"
    )
    if target_tool in {"kling", "runway", "pika", "luma", "visuals"}:
        scene_lines = []
        for scene in scenes:
            scene_lines.append(
                f"SCENE {scene.get('scene')} ({scene.get('start')}-{scene.get('end')}s, {scene.get('goal')}):\n"
                f"Visual prompt: {scene.get('visual_prompt')}\n"
                f"On-screen text: {scene.get('on_screen_text')}\n"
                f"Voice line: {scene.get('voice_line')}\n"
                f"Asset cần xuất: {scene.get('asset_needed')}"
            )
        return (
            common +
            "NHIỆM VỤ VISUAL VIDEO:\n"
            "Tạo từng scene video 9:16 theo prompt. Giữ style nhất quán, không dùng logo/nhân vật bản quyền khi chưa có quyền.\n\n"
            + "\n\n".join(scene_lines) +
            "\n\nOUTPUT:\n"
            "1. Link/file từng scene.\n"
            "2. Scene nào lỗi và fallback đề xuất.\n"
            f"3. Lệnh cập nhật: /asset_add job={jid} type=raw_video url=<LINK> note=manifest:{manifest_id} scene=<N>"
        )
    if target_tool in {"fish", "edge", "tts", "voice"}:
        return (
            common +
            "NHIỆM VỤ VOICE:\n"
            f"Provider chính: {voice.get('provider_primary','Fish Audio HD')} | fallback: {voice.get('provider_fallback','Edge TTS')}\n"
            f"Style: {voice.get('style','giọng Việt rõ, đáng tin')}\n\n"
            f"SCRIPT:\n{voice.get('script') or ' '.join(str(s.get('voice_line','')) for s in scenes)}\n\n"
            "OUTPUT:\n"
            "1. File/link audio.\n"
            "2. Duration thực tế.\n"
            "3. Nếu Fish lỗi/quota, dùng Edge và báo admin.\n"
            f"4. Lệnh cập nhật: /asset_add job={jid} type=voice url=<LINK> note=manifest:{manifest_id}"
        )
    if target_tool in {"capcut", "ffmpeg", "edit"}:
        return (
            common +
            "NHIỆM VỤ EDIT:\n"
            f"Tool: {edit.get('tool','capcut|ffmpeg')}\n"
            f"Music: {edit.get('music','nhạc hợp lệ, âm lượng thấp')}\n"
            f"Subtitle: {edit.get('subtitle','burn subtitle tiếng Việt')}\n"
            f"Transitions: {edit.get('transitions','cut nhanh, sạch')}\n"
            f"CTA overlay: {edit.get('cta_overlay') or publish.get('cta') or '-'}\n\n"
            "INPUT CẦN DÙNG:\n"
            "- raw_video scenes từ /assets\n"
            "- voice audio từ /assets\n"
            "- caption/CTA từ manifest\n\n"
            "OUTPUT:\n"
            "1. final_video mp4 9:16.\n"
            "2. subtitle file nếu có.\n"
            "3. thumbnail nếu có.\n"
            f"4. Lệnh cập nhật: /asset_add job={jid} type=final_video url=<LINK> note=manifest:{manifest_id}"
        )
    if target_tool in {"publish", "caption", "social"}:
        return (
            common +
            "NHIỆM VỤ PUBLISH PACK:\n"
            f"Caption: {publish.get('caption','-')}\n"
            f"Hashtags: {publish.get('hashtags','-')}\n"
            f"Affiliate placement: {publish.get('affiliate_placement','-')}\n"
            f"CTA: {publish.get('cta','-')}\n\n"
            "OUTPUT:\n"
            "1. Caption cuối cùng theo nền tảng.\n"
            "2. Checklist trước khi đăng.\n"
            f"3. Queue đăng: /queue_publish job={jid} mode=manual note=manifest:{manifest_id}"
        )
    if target_tool in {"review", "review_gate", "compliance"}:
        return (
            common +
            "NHIỆM VỤ REVIEW GATE:\n"
            "Checklist manifest:\n" + "\n".join(f"- {item}" for item in compliance) + "\n\n"
            "Kiểm tra thêm: quyền hình ảnh/voice/nhạc, affiliate claim, nội dung người mẫu/OnlyFans nếu có, CTA, link, publish URL.\n"
            "OUTPUT: APPROVE/FIX/BLOCK, lý do, sửa gì trước khi đăng."
        )
    return (
        common +
        "NHIỆM VỤ ORCHESTRATION:\n"
        "Đọc manifest dưới đây và chia việc cho tool phù hợp theo handoff_order.\n\n"
        f"<MANIFEST_JSON>\n{manifest_json}\n</MANIFEST_JSON>\n\n"
        "OUTPUT: danh sách việc theo thứ tự, lệnh Telegram cần chạy tiếp, và điểm rủi ro cần xử lý."
    )

def create_production_task(owner_id, job_id, manifest_id, task_type, tool, scene_no=0, title="", prompt="", status="queued", output_url="", note=""):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """INSERT INTO production_tasks
        (owner_id, job_id, manifest_id, task_type, tool, scene_no, title, prompt, status, output_url, note, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            str(owner_id), job_id, int(manifest_id or 0), task_type, tool, int(scene_no or 0),
            title, prompt, status, output_url, note, now_text(), now_text()
        )
    )
    task_id = c.lastrowid
    conn.commit()
    conn.close()
    return task_id

def create_tasks_from_manifest(owner_id, manifest_row):
    manifest_id, job_id, variant_id, manifest_status, manifest_json, created_at, updated_at = manifest_row
    try:
        manifest = json.loads(manifest_json or "{}")
    except Exception:
        manifest = {}
    scenes = manifest.get("scenes") or []
    voice = manifest.get("voice") or {}
    edit = manifest.get("edit_instructions") or {}
    publish = manifest.get("publish") or {}
    created = []
    for scene in scenes:
        scene_no = int(scene.get("scene") or 0)
        tool = str(scene.get("video_tool") or "kling").split("|")[0].strip() or "kling"
        prompt = (
            f"Scene {scene_no} ({scene.get('start','?')}-{scene.get('end','?')}s, {scene.get('goal','-')})\n"
            f"Visual prompt: {scene.get('visual_prompt','')}\n"
            f"On-screen text: {scene.get('on_screen_text','')}\n"
            f"Voice line: {scene.get('voice_line','')}\n"
            f"Asset needed: {scene.get('asset_needed','')}"
        )
        created.append(create_production_task(
            owner_id, job_id, manifest_id, "visual_scene", tool, scene_no,
            f"Scene {scene_no}: {scene.get('goal','visual')}", prompt, "queued", "", f"asset_needed={scene.get('asset_needed','')}"
        ))
    voice_script = voice.get("script") or " ".join(str(scene.get("voice_line", "")) for scene in scenes)
    if voice_script:
        created.append(create_production_task(
            owner_id, job_id, manifest_id, "voice", "fish", 0,
            "Voice over", f"Style: {voice.get('style','giọng Việt rõ')}\nScript:\n{voice_script}", "queued", "",
            f"fallback={voice.get('provider_fallback','Edge TTS')}"
        ))
    created.append(create_production_task(
        owner_id, job_id, manifest_id, "edit", "capcut", 0,
        "Edit final video",
        "Dựng 9:16 từ raw scene + voice.\n"
        f"Music: {edit.get('music','nhạc hợp lệ')}\nSubtitle: {edit.get('subtitle','burn subtitle')}\n"
        f"Transitions: {edit.get('transitions','cut nhanh')}\nCTA overlay: {edit.get('cta_overlay') or publish.get('cta','')}",
        "queued", "", "fallback=ffmpeg"
    ))
    created.append(create_production_task(
        owner_id, job_id, manifest_id, "review", "review_gate", 0,
        "Compliance review", "\n".join(str(item) for item in (manifest.get("compliance_checklist") or [])), "queued", "", ""
    ))
    created.append(create_production_task(
        owner_id, job_id, manifest_id, "publish", "manual", 0,
        "Publish/queue",
        f"Caption: {publish.get('caption','')}\nHashtags: {publish.get('hashtags','')}\nCTA: {publish.get('cta','')}\nAffiliate: {publish.get('affiliate_placement','')}",
        "queued", "", "mode=manual_or_api"
    ))
    update_production_job(job_id, owner_id, stage="visuals", status="working", note=f"task_plan manifest:{manifest_id} tasks={len(created)}")
    return created

def build_operator_job_bundle(owner_id, job_id, count=5, duration=45):
    job = get_production_job(job_id, owner_id)
    if not job:
        return False, {"error": "Không tìm thấy production job."}
    created_variants = create_creative_variants_for_job(owner_id, job, count)
    if not created_variants:
        return False, {"error": "Không tạo được creative variants."}
    best_variant_id, best_variant = sorted(
        created_variants,
        key=lambda item: int(item[1].get("creative_score") or 0),
        reverse=True
    )[0]
    ok, selected_variant = select_creative_variant(owner_id, best_variant_id)
    if not ok:
        return False, {"error": "Không chọn được creative variant tốt nhất."}
    ok, manifest_id, manifest = create_manifest_for_job(owner_id, job, selected_variant, duration)
    if not ok:
        return False, {"error": "Không tạo được production manifest."}
    manifest_row = get_production_manifest(owner_id, manifest_id)
    task_ids = create_tasks_from_manifest(owner_id, manifest_row)
    readiness = production_readiness_data(owner_id, job_id)
    return True, {
        "job": job,
        "created_variants": created_variants,
        "best_variant_id": best_variant_id,
        "best_variant": best_variant,
        "selected_variant": selected_variant,
        "manifest_id": manifest_id,
        "manifest": manifest,
        "task_ids": task_ids,
        "readiness": readiness,
    }

def list_production_tasks(owner_id, job_id=None, manifest_id=None, limit=30):
    where = ["owner_id=?"]
    params = [str(owner_id)]
    if job_id:
        where.append("job_id=?")
        params.append(int(job_id))
    if manifest_id:
        where.append("manifest_id=?")
        params.append(int(manifest_id))
    params.append(limit)
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        f"""SELECT id, job_id, manifest_id, task_type, tool, scene_no, title, status, output_url, note, updated_at
        FROM production_tasks
        WHERE {' AND '.join(where)}
        ORDER BY
            CASE status
                WHEN 'blocked' THEN 0
                WHEN 'working' THEN 1
                WHEN 'queued' THEN 2
                WHEN 'ready' THEN 3
                ELSE 4
            END,
            id ASC
        LIMIT ?""",
        params
    )
    rows = c.fetchall()
    conn.close()
    return rows

def get_production_task(owner_id, task_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT id, job_id, manifest_id, task_type, tool, scene_no, title, prompt, status, output_url, note, updated_at
        FROM production_tasks WHERE owner_id=? AND id=?""",
        (str(owner_id), task_id)
    )
    row = c.fetchone()
    conn.close()
    return row

def next_production_task(owner_id, job_id=None):
    rows = list_production_tasks(owner_id, job_id=job_id, limit=100)
    if not rows:
        return None
    type_priority = {
        "visual_scene": 0,
        "voice": 1,
        "edit": 2,
        "review": 3,
        "publish": 4,
    }
    status_priority = {
        "blocked": 0,
        "working": 1,
        "queued": 2,
        "waiting": 3,
        "ready": 4,
        "done": 5,
        "cancelled": 6,
    }
    actionable = [row for row in rows if (row[7] or "queued") not in {"ready", "done", "cancelled"}]
    if not actionable:
        return None
    actionable.sort(key=lambda row: (status_priority.get(row[7] or "queued", 9), type_priority.get(row[3] or "", 9), row[5] or 0, row[0]))
    return actionable[0]

def next_worker_task(owner_id, job_id=None, tool=""):
    rows = list_production_tasks(owner_id, job_id=job_id, limit=200)
    allowed_status = {"queued", "waiting"}
    tool = (tool or "").strip().lower()
    candidates = []
    for row in rows:
        row_tool = (row[4] or "").lower()
        row_status = (row[7] or "queued").lower()
        if row_status not in allowed_status:
            continue
        if tool and tool not in {row_tool, (row[3] or "").lower()}:
            continue
        candidates.append(row)
    if not candidates:
        return None
    type_priority = {"visual_scene": 0, "voice": 1, "edit": 2, "review": 3, "publish": 4}
    candidates.sort(key=lambda row: (type_priority.get(row[3] or "", 9), row[5] or 0, row[0]))
    return get_production_task(owner_id, candidates[0][0])

def update_production_task(owner_id, task_id, status=None, output_url=None, note=None):
    updates = []
    params = []
    if status:
        updates.append("status=?")
        params.append(status)
    if output_url is not None:
        updates.append("output_url=?")
        params.append(output_url)
    if note is not None:
        updates.append("note=?")
        params.append(note)
    if not updates:
        return False, None
    updates.append("updated_at=?")
    params.append(now_text())
    params.extend([str(owner_id), task_id])
    conn = db_connect()
    c = conn.cursor()
    c.execute(f"UPDATE production_tasks SET {', '.join(updates)} WHERE owner_id=? AND id=?", params)
    changed = c.rowcount
    c.execute("SELECT job_id, task_type FROM production_tasks WHERE owner_id=? AND id=?", (str(owner_id), task_id))
    row = c.fetchone()
    conn.commit()
    conn.close()
    if changed and output_url and row:
        asset_type = {
            "visual_scene": "raw_video",
            "voice": "voice",
            "edit": "final_video",
            "publish": "source",
        }.get(row[1], "source")
        add_production_asset(owner_id, row[0], asset_type, output_url, "", f"task:{task_id} {note or ''}")
    return changed > 0, row

def serialize_operator_task(row):
    if not row:
        return None
    task_id, job_id, manifest_id, task_type, tool, scene_no, title, prompt, status, output_url, note, updated_at = row
    job = get_production_job(job_id, ADMIN_ID)
    job_payload = None
    if job:
        (
            jid, calendar_id, campaign_id, channel_id, affiliate_id, platform, topic, stage, job_status,
            operator_note, brief, asset_url, publish_url, channel_name, account_label, network, product_name, affiliate_url
        ) = job
        job_payload = {
            "id": jid,
            "platform": platform,
            "topic": topic,
            "stage": stage,
            "status": job_status,
            "channel_name": channel_name,
            "account_label": account_label,
            "affiliate_network": network,
            "affiliate_product": product_name,
            "affiliate_url": affiliate_url,
            "asset_url": asset_url,
            "publish_url": publish_url,
        }
    return {
        "id": task_id,
        "job_id": job_id,
        "manifest_id": manifest_id,
        "task_type": task_type,
        "tool": tool,
        "scene_no": scene_no,
        "title": title,
        "prompt": prompt,
        "status": status,
        "output_url": output_url,
        "note": note,
        "updated_at": updated_at,
        "job": job_payload,
    }

def add_performance_event(owner_id, job_id, event_type, value=0, amount=0, note="", variant_id=0):
    job = get_production_job(job_id, owner_id)
    if not job:
        return False, None
    if variant_id:
        variant = get_creative_variant(owner_id, variant_id)
        if not variant or int(variant[1]) != int(job_id):
            return False, None
    _, _, _, channel_id, affiliate_id, platform, *_ = job
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """INSERT INTO performance_events
        (owner_id, job_id, variant_id, channel_id, affiliate_id, platform, event_type, value, amount, note, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (str(owner_id), job_id, int(variant_id or 0), channel_id, affiliate_id, platform, event_type, int(value), int(amount), note, now_text())
    )
    conn.commit()
    conn.close()
    return True, job

def performance_report_data(owner_id, limit=10):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT event_type, COALESCE(SUM(value),0), COALESCE(SUM(amount),0), COUNT(*)
        FROM performance_events WHERE owner_id=? GROUP BY event_type ORDER BY event_type""",
        (str(owner_id),)
    )
    event_totals = c.fetchall()
    c.execute(
        """SELECT pe.platform, sc.channel_name, COALESCE(SUM(pe.value),0), COALESCE(SUM(pe.amount),0), COUNT(*)
        FROM performance_events pe
        LEFT JOIN social_channels sc ON sc.id = pe.channel_id
        WHERE pe.owner_id=?
        GROUP BY pe.platform, sc.channel_name
        ORDER BY COALESCE(SUM(pe.amount),0) DESC, COALESCE(SUM(pe.value),0) DESC
        LIMIT ?""",
        (str(owner_id), limit)
    )
    channel_totals = c.fetchall()
    c.execute(
        """SELECT pe.job_id, pe.event_type, pe.value, pe.amount, pe.platform, pj.topic, pe.note, pe.created_at
        FROM performance_events pe
        LEFT JOIN production_jobs pj ON pj.id = pe.job_id
        WHERE pe.owner_id=?
        ORDER BY pe.id DESC
        LIMIT ?""",
        (str(owner_id), limit)
    )
    recent_events = c.fetchall()
    conn.close()
    return event_totals, channel_totals, recent_events

def growth_optimizer_data(owner_id, days=14, limit=8):
    since = (datetime.now() - timedelta(days=max(1, int(days)))).strftime("%Y-%m-%d %H:%M:%S")
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT pe.job_id, pj.topic, pe.platform, sc.channel_name, al.product_name,
                  SUM(CASE WHEN pe.event_type='view' THEN pe.value ELSE 0 END) AS views,
                  SUM(CASE WHEN pe.event_type='click' THEN pe.value ELSE 0 END) AS clicks,
                  SUM(CASE WHEN pe.event_type IN ('order','lead','revenue') THEN pe.value ELSE 0 END) AS conversions,
                  SUM(CASE WHEN pe.event_type IN ('order','lead','revenue') THEN pe.amount ELSE 0 END) AS revenue,
                  SUM(CASE WHEN pe.event_type='cost' THEN pe.amount ELSE 0 END) AS cost,
                  COUNT(*) AS events
        FROM performance_events pe
        LEFT JOIN production_jobs pj ON pj.id = pe.job_id
        LEFT JOIN social_channels sc ON sc.id = pe.channel_id
        LEFT JOIN affiliate_links al ON al.id = pe.affiliate_id
        WHERE pe.owner_id=? AND pe.created_at>=?
        GROUP BY pe.job_id, pj.topic, pe.platform, sc.channel_name, al.product_name
        ORDER BY revenue DESC, clicks DESC, views DESC
        LIMIT ?""",
        (str(owner_id), since, limit)
    )
    job_rows = c.fetchall()
    c.execute(
        """SELECT pe.platform, sc.channel_name,
                  SUM(CASE WHEN pe.event_type='view' THEN pe.value ELSE 0 END) AS views,
                  SUM(CASE WHEN pe.event_type='click' THEN pe.value ELSE 0 END) AS clicks,
                  SUM(CASE WHEN pe.event_type IN ('order','lead','revenue') THEN pe.value ELSE 0 END) AS conversions,
                  SUM(CASE WHEN pe.event_type IN ('order','lead','revenue') THEN pe.amount ELSE 0 END) AS revenue,
                  COUNT(*) AS events
        FROM performance_events pe
        LEFT JOIN social_channels sc ON sc.id = pe.channel_id
        WHERE pe.owner_id=? AND pe.created_at>=?
        GROUP BY pe.platform, sc.channel_name
        ORDER BY revenue DESC, clicks DESC, views DESC
        LIMIT ?""",
        (str(owner_id), since, limit)
    )
    channel_rows = c.fetchall()
    c.execute(
        """SELECT pe.variant_id, cv.variant_label, cv.hook,
                  SUM(CASE WHEN pe.event_type='view' THEN pe.value ELSE 0 END) AS views,
                  SUM(CASE WHEN pe.event_type='click' THEN pe.value ELSE 0 END) AS clicks,
                  SUM(CASE WHEN pe.event_type IN ('order','lead','revenue') THEN pe.value ELSE 0 END) AS conversions,
                  SUM(CASE WHEN pe.event_type IN ('order','lead','revenue') THEN pe.amount ELSE 0 END) AS revenue
        FROM performance_events pe
        LEFT JOIN creative_variants cv ON cv.id = pe.variant_id
        WHERE pe.owner_id=? AND pe.created_at>=? AND COALESCE(pe.variant_id,0)>0
        GROUP BY pe.variant_id, cv.variant_label, cv.hook
        ORDER BY revenue DESC, clicks DESC, views DESC
        LIMIT ?""",
        (str(owner_id), since, limit)
    )
    variant_rows = c.fetchall()
    conn.close()
    return since, job_rows, channel_rows, variant_rows

def growth_score(views=0, clicks=0, conversions=0, revenue=0, cost=0):
    views = int(views or 0)
    clicks = int(clicks or 0)
    conversions = int(conversions or 0)
    revenue = int(revenue or 0)
    cost = int(cost or 0)
    ctr = (clicks / views * 100) if views else 0
    cvr = (conversions / clicks * 100) if clicks else 0
    roi = ((revenue - cost) / cost * 100) if cost else (100 if revenue > 0 else 0)
    score = min(100, int((ctr * 3) + (cvr * 5) + min(revenue / 10000, 40) + max(min(roi / 10, 20), 0)))
    return score, ctr, cvr, roi

def operator_loop_data(owner_id, limit=10, auto_queue=True):
    jobs = list_production_jobs(owner_id, limit=limit)
    advanced = []
    blocked = []
    next_tasks = []
    ready_publish = []
    for jid, stage, status, platform, topic, channel_name, product_name, updated_at in jobs:
        if status in {"published", "done", "cancelled"}:
            continue
        readiness = production_readiness_data(owner_id, jid)
        level = readiness["level"] if readiness else "UNKNOWN"
        next_action = readiness["next_action"] if readiness else ""
        if level == "READY_TO_QUEUE" and auto_queue:
            ok, queue_id = create_publish_queue_item(owner_id, jid, mode="manual", scheduled_at="", note="operator_loop_auto_queue")
            if ok:
                advanced.append((jid, "queued_publish", queue_id, topic, platform, channel_name))
                continue
        if level == "READY_TO_PUBLISH":
            ready_publish.append((jid, topic, platform, channel_name))
            continue
        task = next_production_task(owner_id, job_id=jid)
        if task:
            tid, job_id, manifest_id, task_type, tool, scene_no, title, t_status, output_url, note, task_updated = task
            next_tasks.append((tid, job_id, task_type, tool, scene_no, title, t_status, topic, platform, channel_name))
        else:
            blocked.append((jid, level, next_action, topic, platform, channel_name))
    return advanced, ready_publish, next_tasks, blocked

def serialize_operator_loop_result(advanced, ready_publish, next_tasks, blocked):
    return {
        "advanced": [
            {
                "job_id": jid,
                "action": action,
                "queue_id": queue_id,
                "topic": topic,
                "platform": platform,
                "channel_name": channel_name,
            }
            for jid, action, queue_id, topic, platform, channel_name in advanced
        ],
        "ready_publish": [
            {
                "job_id": jid,
                "topic": topic,
                "platform": platform,
                "channel_name": channel_name,
            }
            for jid, topic, platform, channel_name in ready_publish
        ],
        "next_tasks": [
            {
                "task_id": tid,
                "job_id": job_id,
                "task_type": task_type,
                "tool": tool,
                "scene_no": scene_no,
                "title": title,
                "status": status,
                "topic": topic,
                "platform": platform,
                "channel_name": channel_name,
            }
            for tid, job_id, task_type, tool, scene_no, title, status, topic, platform, channel_name in next_tasks
        ],
        "blocked": [
            {
                "job_id": jid,
                "level": level,
                "next_action": next_action,
                "topic": topic,
                "platform": platform,
                "channel_name": channel_name,
            }
            for jid, level, next_action, topic, platform, channel_name in blocked
        ],
    }

def create_publish_queue_item(owner_id, job_id, mode="manual", scheduled_at="", note=""):
    job = get_production_job(job_id, owner_id)
    if not job:
        return False, None
    _, _, _, channel_id, _, platform, *_ = job
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """INSERT INTO publish_queue
        (owner_id, job_id, channel_id, platform, mode, status, scheduled_at, publish_url, note, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (str(owner_id), job_id, channel_id, platform, mode, "queued", scheduled_at, "", note, now_text(), now_text())
    )
    queue_id = c.lastrowid
    conn.commit()
    conn.close()
    update_production_job(job_id, owner_id, stage="publish", status="queued", note=f"publish_queue:{queue_id} mode={mode} {note}")
    return True, queue_id

def list_publish_queue(owner_id, limit=15):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT pq.id, pq.job_id, pq.platform, sc.channel_name, pq.mode, pq.status, pq.scheduled_at, pq.publish_url, pj.topic, pq.updated_at
        FROM publish_queue pq
        LEFT JOIN social_channels sc ON sc.id = pq.channel_id
        LEFT JOIN production_jobs pj ON pj.id = pq.job_id
        WHERE pq.owner_id=?
        ORDER BY
            CASE pq.status
                WHEN 'blocked' THEN 0
                WHEN 'queued' THEN 1
                WHEN 'scheduled' THEN 2
                WHEN 'publishing' THEN 3
                ELSE 4
            END,
            pq.id DESC
        LIMIT ?""",
        (str(owner_id), limit)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def get_publish_queue_item(owner_id, queue_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT pq.id, pq.job_id, pq.channel_id, pq.platform, sc.channel_name, sc.account_label,
                  pq.mode, pq.status, pq.scheduled_at, pq.publish_url, pq.note, pq.updated_at,
                  pj.topic, pj.asset_url, pj.brief_text, pj.stage, pj.status,
                  al.network, al.product_name, al.url
        FROM publish_queue pq
        LEFT JOIN social_channels sc ON sc.id = pq.channel_id
        LEFT JOIN production_jobs pj ON pj.id = pq.job_id
        LEFT JOIN affiliate_links al ON al.id = pj.affiliate_id
        WHERE pq.owner_id=? AND pq.id=?""",
        (str(owner_id), queue_id)
    )
    row = c.fetchone()
    conn.close()
    return row

def next_publish_queue_item(owner_id, platform="", mode=""):
    where = ["pq.owner_id=?", "pq.status IN ('queued','scheduled')"]
    params = [str(owner_id)]
    if platform:
        where.append("LOWER(pq.platform)=?")
        params.append(platform.lower())
    if mode:
        where.append("LOWER(pq.mode)=?")
        params.append(mode.lower())
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        f"""SELECT pq.id
        FROM publish_queue pq
        WHERE {' AND '.join(where)}
        ORDER BY
            CASE pq.status WHEN 'queued' THEN 0 WHEN 'scheduled' THEN 1 ELSE 2 END,
            pq.scheduled_at ASC,
            pq.id ASC
        LIMIT 1""",
        params
    )
    row = c.fetchone()
    conn.close()
    return get_publish_queue_item(owner_id, row[0]) if row else None

def serialize_publish_queue_item(row):
    if not row:
        return None
    (
        qid, job_id, channel_id, platform, channel_name, account_label, mode, status,
        scheduled_at, publish_url, note, updated_at, topic, asset_url, brief_text,
        stage, job_status, network, product_name, affiliate_url
    ) = row
    assets = list_production_assets(ADMIN_ID, job_id, limit=20)
    final_asset = next(
        (
            {"id": aid, "type": asset_type, "url": url, "file_id": file_id, "note": asset_note, "created_at": created_at}
            for aid, asset_type, url, file_id, asset_note, created_at in assets
            if (asset_type or "").lower() == "final_video" and (url or file_id)
        ),
        None
    )
    variants = list_creative_variants(ADMIN_ID, job_id, limit=20)
    selected_variant = next((row for row in variants if (row[8] or "").lower() == "selected"), None)
    caption = selected_variant[5] if selected_variant else ""
    cta = selected_variant[6] if selected_variant else ""
    hashtags = selected_variant[7] if selected_variant else ""
    return {
        "id": qid,
        "job_id": job_id,
        "channel_id": channel_id,
        "platform": platform,
        "channel_name": channel_name,
        "account_label": account_label,
        "mode": mode,
        "status": status,
        "scheduled_at": scheduled_at,
        "publish_url": publish_url,
        "note": note,
        "updated_at": updated_at,
        "topic": topic,
        "asset_url": asset_url,
        "final_video": final_asset,
        "brief": brief_text,
        "stage": stage,
        "job_status": job_status,
        "affiliate": {
            "network": network,
            "product_name": product_name,
            "url": affiliate_url,
        },
        "publish_pack": {
            "caption": caption,
            "cta": cta,
            "hashtags": hashtags,
            "affiliate_placement": affiliate_url,
        },
        "rule": "Publish only approved/queued jobs. Keep affiliate disclosure and platform rules.",
    }

def update_publish_queue_item(owner_id, queue_id, status=None, publish_url=None, note=None):
    updates = []
    params = []
    if status:
        updates.append("status=?")
        params.append(status)
    if publish_url is not None:
        updates.append("publish_url=?")
        params.append(publish_url)
    if note is not None:
        updates.append("note=?")
        params.append(note)
    updates.append("updated_at=?")
    params.append(now_text())
    params.extend([queue_id, str(owner_id)])
    conn = db_connect()
    c = conn.cursor()
    c.execute(f"UPDATE publish_queue SET {', '.join(updates)} WHERE id=? AND owner_id=?", params)
    changed = c.rowcount
    c.execute("SELECT job_id FROM publish_queue WHERE id=? AND owner_id=?", (queue_id, str(owner_id)))
    row = c.fetchone()
    conn.commit()
    conn.close()
    return changed > 0, row[0] if row else None

def clamp_score(value, low=0, high=100):
    return max(low, min(high, int(value)))

def tokenize_text(text):
    return [part.strip().lower() for part in (text or "").replace("|", " ").replace("/", " ").replace(",", " ").split() if len(part.strip()) >= 3]

def score_trend_candidate(niche, platform, title, summary="", channel=None, affiliate=None):
    text = f"{title} {summary}".lower()
    niche_tokens = tokenize_text(niche)
    platform_l = (platform or "").lower()
    reasons = []

    trend_score = 45
    if any(token in text for token in niche_tokens[:8]):
        trend_score += 15
        reasons.append("khớp niche")
    if platform_l and platform_l in text:
        trend_score += 8
        reasons.append("có tín hiệu nền tảng")
    fresh_words = ["mới", "ra mắt", "2026", "trend", "viral", "tăng", "bùng nổ", "latest", "new"]
    fresh_hits = sum(1 for word in fresh_words if word in text)
    trend_score += min(18, fresh_hits * 6)
    if fresh_hits:
        reasons.append("có tín hiệu mới/viral")
    if channel:
        _, _, _, _, topic_focus, audience, *_ = channel
        focus_tokens = tokenize_text(topic_focus) + tokenize_text(audience)
        focus_hits = sum(1 for token in focus_tokens[:12] if token in text)
        trend_score += min(14, focus_hits * 4)
        if focus_hits:
            reasons.append("khớp kênh")

    affiliate_fit = 0
    if affiliate:
        (
            _, network, product_name, aff_niche, _, commission_note, _, _price_vnd,
            commission_rate, target_audience, allowed_claims, blocked_claims, product_score
        ) = affiliate
        aff_tokens = (
            tokenize_text(product_name) + tokenize_text(aff_niche) + tokenize_text(network) +
            tokenize_text(target_audience) + tokenize_text(allowed_claims)
        )
        aff_hits = sum(1 for token in aff_tokens[:16] if token in text)
        blocked_hits = sum(1 for token in tokenize_text(blocked_claims)[:12] if token in text)
        affiliate_fit = clamp_score(
            20 + int(product_score or 0) // 3 + aff_hits * 12 +
            (10 if aff_niche and aff_niche.lower() in text else 0) +
            (5 if commission_rate else 0) - blocked_hits * 15
        )
        if aff_hits:
            reasons.append("khớp affiliate")
        if blocked_hits:
            reasons.append("có claim cần tránh")
        if commission_note:
            affiliate_fit = clamp_score(affiliate_fit + 5)
    elif any(word in text for word in ["review", "mua", "shop", "giá", "deal", "sản phẩm", "product"]):
        affiliate_fit = 45
        reasons.append("có góc bán hàng")

    broad_words = ["ai", "tiktok", "facebook", "youtube", "iphone", "chatgpt", "gemini", "trend"]
    broad_hits = sum(1 for word in broad_words if word in text)
    competition = clamp_score(35 + broad_hits * 10 - len(niche_tokens) * 2)
    if competition >= 70:
        reasons.append("cạnh tranh cao")
    elif competition <= 45:
        reasons.append("ngách hẹp")

    opportunity = clamp_score(int((trend_score * 0.55) + (affiliate_fit * 0.35) + ((100 - competition) * 0.10)))
    if not reasons:
        reasons.append("trend mới từ RSS")
    return {
        "trend_score": opportunity,
        "affiliate_fit_score": affiliate_fit,
        "competition_score": competition,
        "score_reason": "; ".join(reasons[:5]),
    }

def save_trend_candidate(owner_id, niche, platform, title, source_url, source_name="", summary="", channel_id=0, campaign_id=0, affiliate_id=0, trend_score=0, affiliate_fit_score=0, competition_score=0, score_reason=""):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """INSERT INTO trend_candidates
        (owner_id, niche, platform, title, source_url, source_name, summary, channel_id, campaign_id, affiliate_id,
         trend_score, affiliate_fit_score, competition_score, score_reason, status, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            str(owner_id), niche, platform, title, source_url, source_name, summary,
            int(channel_id or 0), int(campaign_id or 0), int(affiliate_id or 0),
            int(trend_score or 0), int(affiliate_fit_score or 0), int(competition_score or 0), score_reason,
            "new", now_text()
        )
    )
    trend_id = c.lastrowid
    conn.commit()
    conn.close()
    return trend_id

def get_trend_candidate(trend_id, owner_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT id, niche, platform, title, source_url, source_name, summary, channel_id, campaign_id, affiliate_id,
                  status, trend_score, affiliate_fit_score, competition_score, score_reason
        FROM trend_candidates WHERE id=? AND owner_id=?""",
        (trend_id, str(owner_id))
    )
    row = c.fetchone()
    conn.close()
    return row

def list_trend_candidates(owner_id, limit=10):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT id, niche, platform, title, source_name, status, trend_score, affiliate_fit_score, competition_score, score_reason, created_at
        FROM trend_candidates
        WHERE owner_id=?
        ORDER BY trend_score DESC, id DESC
        LIMIT ?""",
        (str(owner_id), limit)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def update_trend_status(trend_id, owner_id, status):
    conn = db_connect()
    c = conn.cursor()
    c.execute("UPDATE trend_candidates SET status=? WHERE id=? AND owner_id=?", (status, trend_id, str(owner_id)))
    conn.commit()
    conn.close()

async def fetch_google_news_trends(niche, platform="", limit=5):
    query_parts = [niche, "trend", "mới nhất"]
    if platform:
        query_parts.append(platform)
    query = quote(" ".join(query_parts))
    url = f"https://news.google.com/rss/search?q={query}&hl=vi&gl=VN&ceid=VN:vi"
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        res = await client.get(url, headers={"User-Agent": "TOAN-DAAS-Bot/1.0"})
    if res.status_code != 200:
        raise RuntimeError(f"Google News RSS HTTP {res.status_code}")
    root = ET.fromstring(res.content)
    items = []
    for item in root.findall(".//item")[:limit]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        source_node = item.find("source")
        source_name = source_node.text.strip() if source_node is not None and source_node.text else "Google News"
        summary = (item.findtext("description") or "").strip()
        if title and link:
            items.append({"title": title, "url": link, "source": source_name, "summary": summary})
    return items

async def create_operator_auto_jobs(owner_id, niche, platform_filter="", channel_filter="all", campaign_id=0, affiliate_id=0, limit=5):
    if campaign_id and not get_campaign(campaign_id, owner_id):
        return [], "Không tìm thấy campaign."
    if affiliate_id and not get_affiliate_link(affiliate_id, owner_id):
        return [], "Không tìm thấy affiliate."
    if channel_filter == "all":
        channels = list_social_channels(owner_id, limit=80)
        if platform_filter:
            channels = [ch for ch in channels if (ch[1] or "").lower() == platform_filter]
    else:
        try:
            one = get_social_channel(int(channel_filter), owner_id)
        except ValueError:
            one = None
        channels = [one] if one else []
    channels = [ch for ch in channels if ch and ch[7] == "active"]
    if not channels:
        return [], "Chưa có channel active phù hợp. Tạo bằng /channel_add."

    search_platform = platform_filter or (channels[0][1] if channels else "tiktok")
    trends = await fetch_google_news_trends(niche, search_platform, limit=limit)
    if not trends:
        return [], "Không tìm thấy trend để tạo job."

    affiliate = get_affiliate_link(affiliate_id, owner_id) if affiliate_id else None
    primary_channel = channels[0] if channels else None
    scored_trends = []
    for item in trends:
        scores = score_trend_candidate(niche, search_platform, item["title"], item.get("summary", ""), primary_channel, affiliate)
        scored_trends.append((scores["trend_score"], item, scores))
    scored_trends.sort(key=lambda row: row[0], reverse=True)

    created = []
    for _, item, base_scores in scored_trends:
        for channel in channels:
            if len(created) >= limit:
                break
            cid, channel_platform, channel_name, account_label, focus, audience, slots, status = channel
            scores = score_trend_candidate(niche, channel_platform or search_platform, item["title"], item.get("summary", ""), channel, affiliate) or base_scores
            trend_id = save_trend_candidate(
                owner_id,
                niche,
                channel_platform or search_platform,
                item["title"],
                item["url"],
                item.get("source", ""),
                item.get("summary", ""),
                cid,
                campaign_id,
                affiliate_id,
                scores["trend_score"],
                scores["affiliate_fit_score"],
                scores["competition_score"],
                scores["score_reason"]
            )
            topic = f"{item['title']} | {niche} | affiliate product placement"
            note = (
                f"operator_auto trend #{trend_id} | score={scores['trend_score']} "
                f"aff_fit={scores['affiliate_fit_score']} competition={scores['competition_score']} | "
                f"source={item.get('source','')} | {item['url']}"
            )
            slot_id = create_calendar_slot(
                owner_id,
                cid,
                campaign_id,
                affiliate_id,
                datetime.now().date().isoformat(),
                channel_platform or search_platform,
                topic,
                note
            )
            slot = get_calendar_slot(slot_id, owner_id)
            if gemini_client or openai_client:
                brief = AgentGemini.chat(
                    "Bạn là AI Operator trưởng, tạo brief video affiliate từ trend cho pipeline batch.",
                    build_production_prompt(slot) + f"\n\nNguồn trend: {item['url']}\nTóm tắt trend: {item.get('summary','')}",
                    owner_id,
                    is_json=False
                )
            else:
                brief = f"Trend: {item['title']}\nNguồn: {item['url']}\nTạo video affiliate theo trend này và kiểm duyệt trước khi đăng."
            job_id = create_production_job(
                owner_id,
                slot_id,
                campaign_id,
                cid,
                affiliate_id,
                channel_platform or search_platform,
                topic,
                brief,
                note
            )
            update_trend_status(trend_id, owner_id, f"job:{job_id}")
            created.append({
                "job_id": job_id,
                "slot_id": slot_id,
                "trend_id": trend_id,
                "platform": channel_platform or search_platform,
                "channel_name": channel_name,
                "title": item["title"],
                "score": scores["trend_score"],
                "reason": scores["score_reason"],
            })
    return created, ""

def build_production_prompt(slot):
    (
        slot_id, _, channel_id, campaign_id, affiliate_id, post_date, platform, topic, _, notes,
        channel_name, account_label, topic_focus, audience, network, product_name, affiliate_url, commission_note
    ) = slot
    return (
        "Bạn là AI Operator điều phối sản xuất video affiliate cho TOAN DAAS. "
        "Lập brief sản xuất có thể giao cho Claude/Gemini/Runway/Kling/CapCut/FFmpeg, không spam, không mạo danh, "
        "không hướng dẫn né kiểm duyệt. Nội dung người mẫu/OnlyFans chỉ dùng nhân vật tự tạo hoặc người thật có đồng ý rõ ràng, đủ 18 tuổi.\n\n"
        f"Calendar slot: #{slot_id}\n"
        f"Ngày đăng dự kiến: {post_date}\n"
        f"Nền tảng: {platform}\n"
        f"Kênh: {channel_name or channel_id} / account={account_label or 'main'}\n"
        f"Audience: {audience or 'general'}\n"
        f"Focus: {topic_focus or 'công nghệ'}\n"
        f"Topic: {topic}\n"
        f"Campaign ID: {campaign_id or 'chưa gắn'}\n"
        f"Affiliate: {network or 'chưa gắn'} - {product_name or ''} - {affiliate_url or ''}\n"
        f"Hoa hồng/ghi chú: {commission_note or notes or 'chưa có'}\n\n"
        "Trả về tiếng Việt dạng checklist gồm: mục tiêu video, hook 3 giây, kịch bản 45-60s, cảnh quay/visual prompt, "
        "voice style, caption, hashtag, CTA, vị trí gắn link affiliate, asset cần tạo, bước kiểm duyệt trước đăng, và next action cho admin."
    )

def build_operator_stage_prompt(job, target_stage):
    (
        jid, calendar_id, campaign_id, channel_id, affiliate_id, platform, topic, stage, status,
        note, brief, asset_url, publish_url, channel_name, account_label, network, product_name, affiliate_url
    ) = job
    tool_map = {
        "script": "Gemini/OpenAI/Claude Opus để chốt kịch bản, hook, CTA và caption.",
        "voice": "Fish Audio HD trước; nếu lỗi/quota/hết tiền thì Edge TTS fallback, báo admin và hoàn chênh lệch cho khách nếu đây là dịch vụ tính phí.",
        "visuals": "Kling/Runway/Canva/CapCut assets theo prompt; chỉ dùng hình/nhân vật có quyền, AI model tự tạo hoặc người thật có consent 18+.",
        "edit": "CapCut/DaVinci/FFmpeg để dựng 9:16, subtitle, nhạc nền hợp lệ và CTA rõ.",
        "review": "Kiểm tra compliance, quyền hình ảnh/âm thanh, claim affiliate, nội dung không spam/không mạo danh.",
        "publish": "Chuẩn bị caption, hashtag, affiliate placement và checklist đăng thủ công/API chính thức cho nền tảng.",
    }
    return (
        "Bạn là AI Operator trưởng của TOAN DAAS. Hãy tạo lệnh điều phối stage tiếp theo cho production job. "
        "Giữ nguyên triết lý công cụ: dùng công cụ tốt/có phí trước, khi hết quota/hết tiền/lỗi thì fallback sang công cụ ít phí/miễn phí, "
        "đồng thời báo admin cần bổ sung quota/số dư/key. Không spam, không mạo danh, không hướng dẫn né kiểm duyệt.\n\n"
        f"Job ID: #{jid}\n"
        f"Calendar: {calendar_id or '-'} | Campaign: {campaign_id or '-'}\n"
        f"Nền tảng: {platform or '-'}\n"
        f"Kênh: {channel_name or channel_id or '-'} / account={account_label or 'main'}\n"
        f"Topic: {topic or '-'}\n"
        f"Stage hiện tại: {stage or '-'} | Status: {status or '-'}\n"
        f"Stage cần làm: {target_stage}\n"
        f"Affiliate: {network or '-'} - {product_name or '-'} - {affiliate_url or '-'}\n"
        f"Asset hiện có: {asset_url or 'chưa có'}\n"
        f"Publish URL: {publish_url or 'chưa có'}\n"
        f"Ghi chú admin: {note or '-'}\n\n"
        f"Tool routing stage này: {tool_map.get(target_stage, 'Tự chọn công cụ phù hợp, ưu tiên bản tốt/có phí trước.')}\n\n"
        f"Brief gốc:\n{brief or 'Chưa có brief'}\n\n"
        "Trả về tiếng Việt dạng checklist ngắn gọn gồm: mục tiêu stage, input cần dùng, tool chính, tool fallback, lệnh/prompt đưa vào tool, "
        "tiêu chí đạt, lỗi cần báo admin, output cần lưu vào pipeline."
    )

def build_publish_pack_prompt(job):
    (
        jid, calendar_id, campaign_id, channel_id, affiliate_id, platform, topic, stage, status,
        note, brief, asset_url, publish_url, channel_name, account_label, network, product_name, affiliate_url
    ) = job
    return (
        "Bạn là AI Operator trưởng chuẩn bị gói đăng bài kiếm tiền cho TOAN DAAS. "
        "Tạo nội dung đăng hợp pháp, không spam, không mạo danh, không cam kết thu nhập phi thực tế, "
        "không hướng dẫn né kiểm duyệt. Nếu nền tảng là OnlyFans hoặc có người mẫu/AI influencer thì chỉ dùng nhân vật tự tạo "
        "hoặc người thật có consent rõ ràng và đủ 18 tuổi.\n\n"
        f"Job ID: #{jid}\n"
        f"Nền tảng: {platform or '-'}\n"
        f"Kênh: {channel_name or channel_id or '-'} / account={account_label or 'main'}\n"
        f"Topic: {topic or '-'}\n"
        f"Affiliate: {network or '-'} - {product_name or '-'}\n"
        f"Affiliate URL: {affiliate_url or 'chưa có'}\n"
        f"Asset URL: {asset_url or 'chưa có'}\n"
        f"Publish URL hiện tại: {publish_url or 'chưa có'}\n"
        f"Ghi chú: {note or '-'}\n\n"
        f"Brief/job context:\n{brief or 'Chưa có brief'}\n\n"
        "Trả về tiếng Việt theo format:\n"
        "1. Caption chính theo nền tảng.\n"
        "2. Caption ngắn A/B.\n"
        "3. Hashtag.\n"
        "4. CTA và vị trí gắn link affiliate.\n"
        "5. Checklist trước khi đăng.\n"
        "6. Sau khi đăng cần ghi lại: publish_url, view, click, order, revenue bằng /pipeline_set và /performance_add."
    )

def build_creative_test_prompt(job, count=5):
    (
        jid, calendar_id, campaign_id, channel_id, affiliate_id, platform, topic, stage, status,
        note, brief, asset_url, publish_url, channel_name, account_label, network, product_name, affiliate_url
    ) = job
    return (
        "Bạn là creative strategist cho video affiliate ngắn. Tạo nhiều biến thể hook/caption/CTA để A/B test, "
        "không spam, không cam kết thu nhập phi thực tế, không mạo danh, không dùng nội dung nhạy cảm trái phép. "
        "Nếu có AI influencer/OnlyFans thì chỉ dùng nhân vật tự tạo hoặc người thật có consent rõ ràng, đủ 18 tuổi.\n\n"
        f"Số biến thể cần tạo: {count}\n"
        f"Job ID: #{jid}\n"
        f"Nền tảng: {platform or '-'}\n"
        f"Kênh: {channel_name or channel_id or '-'} / account={account_label or 'main'}\n"
        f"Topic: {topic or '-'}\n"
        f"Affiliate: {network or '-'} - {product_name or '-'}\n"
        f"Affiliate URL: {affiliate_url or 'chưa có'}\n"
        f"Brief:\n{brief or 'Chưa có brief'}\n\n"
        "Trả về JSON thuần là một mảng. Mỗi phần tử có key: "
        "variant_label, hook, script_angle, caption, cta, hashtags, creative_score, note. "
        "creative_score là 0-100 dựa trên khả năng giữ chân 3 giây đầu, độ khớp affiliate và độ an toàn nền tảng."
    )

def fallback_creative_variants(job, count=5):
    (
        jid, calendar_id, campaign_id, channel_id, affiliate_id, platform, topic, stage, status,
        note, brief, asset_url, publish_url, channel_name, account_label, network, product_name, affiliate_url
    ) = job
    base_topic = topic or "sản phẩm affiliate"
    product = product_name or "sản phẩm đề xuất"
    templates = [
        ("A", f"Bạn đang bỏ lỡ mẹo này về {base_topic}", "pain-point -> demo nhanh -> giải pháp", f"Một mẹo nhỏ giúp xử lý {base_topic}. Xem kỹ phần cuối để lấy link.", f"Xem link {product} trong mô tả/bio.", "#AI #congnghe #review #affiliate"),
        ("B", f"Trước khi mua {product}, xem 3 điểm này", "checklist review -> ưu/nhược -> ai nên mua", f"3 điểm cần biết trước khi chọn {product}.", "Lưu lại và mở link khi cần so sánh.", "#review #muasamthongminh #deal"),
        ("C", f"Tôi thử biến {base_topic} thành quy trình 60 giây", "case study -> kết quả -> công cụ", f"Quy trình 60 giây để áp dụng {base_topic} vào công việc thật.", "Muốn làm theo thì bắt đầu từ link trong bio.", "#workflow #creator #AItools"),
        ("D", f"Sai lầm phổ biến khi dùng {base_topic}", "mistake -> correction -> product placement", f"Nhiều người dùng sai bước này khi bắt đầu với {base_topic}.", "Kiểm tra checklist và link gợi ý trước khi mua.", "#meohay #tiktokshop #congnghe"),
        ("E", f"Setup tối giản cho người mới bắt đầu {base_topic}", "starter kit -> budget -> next step", f"Setup tối giản, dễ làm, không cần quá nhiều công cụ.", "Chọn món phù hợp trong link affiliate, không cần mua quá tay.", "#setup #creatorlife #shopee"),
    ]
    variants = []
    for label, hook, angle, caption, cta, hashtags in templates[:max(1, min(count, len(templates)))]:
        variants.append({
            "variant_label": label,
            "hook": hook,
            "script_angle": angle,
            "caption": caption,
            "cta": cta,
            "hashtags": hashtags,
            "creative_score": 70 - len(variants) * 3,
            "note": "fallback_template",
        })
    return variants

def parse_creative_variants(raw_text, job, count=5):
    try:
        parsed = json.loads(raw_text)
        if isinstance(parsed, dict):
            parsed = parsed.get("variants") or parsed.get("items") or []
        if isinstance(parsed, list):
            clean = []
            for idx, item in enumerate(parsed[:count], start=1):
                if not isinstance(item, dict):
                    continue
                clean.append({
                    "variant_label": str(item.get("variant_label") or item.get("label") or chr(64 + idx)),
                    "hook": str(item.get("hook") or ""),
                    "script_angle": str(item.get("script_angle") or item.get("angle") or ""),
                    "caption": str(item.get("caption") or ""),
                    "cta": str(item.get("cta") or ""),
                    "hashtags": str(item.get("hashtags") or ""),
                    "creative_score": clamp_score(item.get("creative_score") or item.get("score") or 0),
                    "note": str(item.get("note") or "ai_generated"),
                })
            if clean:
                return clean
    except Exception:
        pass
    variants = fallback_creative_variants(job, count=count)
    if raw_text:
        variants[0]["note"] = "ai_raw_unparsed"
        variants[0]["script_angle"] = truncate_text(raw_text, 800)
    return variants

def create_creative_variants_for_job(owner_id, job, count=5):
    job_id = job[0]
    if gemini_client or openai_client:
        raw = AgentGemini.chat(
            "Bạn là creative strategist tạo biến thể A/B test video affiliate.",
            build_creative_test_prompt(job, count),
            owner_id,
            is_json=False
        )
        variants = parse_creative_variants(raw, job, count)
    else:
        variants = fallback_creative_variants(job, count)
    created = []
    for item in variants[:count]:
        ok, variant_id = create_creative_variant(
            owner_id,
            job_id,
            item["variant_label"],
            item["hook"],
            item["script_angle"],
            item["caption"],
            item["cta"],
            item["hashtags"],
            item["creative_score"],
            item["note"],
        )
        if ok:
            created.append((variant_id, item))
    return created

def build_handoff_prompt(job, target_tool, target_stage):
    (
        jid, calendar_id, campaign_id, channel_id, affiliate_id, platform, topic, stage, status,
        note, brief, asset_url, publish_url, channel_name, account_label, network, product_name, affiliate_url
    ) = job
    tool_hint = {
        "claude": "Claude Opus: kiểm tra logic, viết script/caption/prompt chi tiết, bóc tách task cho các AI khác.",
        "gemini": "Gemini: nghiên cứu nhanh, viết kịch bản, tối ưu caption/hashtag theo nền tảng.",
        "runway": "Runway: tạo footage/video asset theo visual prompt, ưu tiên cảnh hợp pháp và không mạo danh.",
        "kling": "Kling: tạo video từ prompt, giữ style nhất quán và không dùng người thật khi chưa có consent.",
        "capcut": "CapCut: dựng video 9:16, subtitle, nhạc, CTA, logo/watermark nếu cần.",
        "ffmpeg": "FFmpeg: xử lý kỹ thuật như ghép audio/video, resize 9:16, burn subtitle, xuất mp4.",
        "fish": "Fish Audio HD: tạo voice cao cấp; nếu quota/số dư/key lỗi thì fallback Edge TTS và báo admin.",
        "edge": "Edge TTS: fallback voice miễn phí/ít phí.",
    }
    return (
        f"VAI TRÒ: Bạn là {target_tool.upper()} trong hệ thống AI Operator TOAN DAAS.\n"
        "NHIỆM VỤ: Hoàn thành đúng stage được giao, tạo output có thể dùng trực tiếp cho sản xuất video affiliate.\n\n"
        "QUY TẮC BẮT BUỘC:\n"
        "- Ưu tiên công cụ tốt/có phí trước; nếu hết quota/hết tiền/lỗi thì ghi rõ fallback ít phí/miễn phí và báo admin.\n"
        "- Không spam, không mạo danh, không hướng dẫn né kiểm duyệt.\n"
        "- Với OnlyFans/AI influencer/người mẫu: chỉ dùng nhân vật tự tạo hoặc người thật có consent rõ ràng, đủ 18 tuổi.\n"
        "- Không cam kết thu nhập phi thực tế; affiliate CTA phải minh bạch.\n\n"
        f"TOOL/STAGE: {target_tool} / {target_stage}\n"
        f"Gợi ý tool: {tool_hint.get(target_tool, 'Dùng công cụ phù hợp, xuất kết quả rõ ràng để đưa về pipeline.')}\n\n"
        f"JOB ID: #{jid}\n"
        f"Calendar: {calendar_id or '-'} | Campaign: {campaign_id or '-'}\n"
        f"Nền tảng đăng: {platform or '-'}\n"
        f"Kênh/account: {channel_name or channel_id or '-'} / {account_label or 'main'}\n"
        f"Topic: {topic or '-'}\n"
        f"Stage hiện tại: {stage or '-'} | Status: {status or '-'}\n"
        f"Affiliate: {network or '-'} - {product_name or '-'}\n"
        f"Affiliate URL: {affiliate_url or 'chưa có'}\n"
        f"Asset URL: {asset_url or 'chưa có'}\n"
        f"Publish URL: {publish_url or 'chưa có'}\n"
        f"Ghi chú operator: {note or '-'}\n\n"
        f"BRIEF GỐC:\n{brief or 'Chưa có brief'}\n\n"
        "OUTPUT CẦN TRẢ VỀ:\n"
        "1. Kết quả chính cho stage này.\n"
        "2. File/link/asset cần lưu lại nếu có.\n"
        "3. Prompt tiếp theo cho tool sau.\n"
        "4. Checklist chất lượng và compliance.\n"
        "5. Dòng cập nhật đề xuất cho Telegram: /pipeline_set id=... stage=... status=... asset=... publish=... note=..."
    )

def build_review_gate_prompt(job):
    (
        jid, calendar_id, campaign_id, channel_id, affiliate_id, platform, topic, stage, status,
        note, brief, asset_url, publish_url, channel_name, account_label, network, product_name, affiliate_url
    ) = job
    return (
        "Bạn là AI compliance reviewer cho TOAN DAAS. Hãy kiểm duyệt production job trước khi đăng. "
        "Không cần trích dẫn luật; hãy kiểm tra thực dụng theo rủi ro nền tảng và rủi ro kinh doanh.\n\n"
        f"Job ID: #{jid}\n"
        f"Platform: {platform or '-'}\n"
        f"Channel/account: {channel_name or channel_id or '-'} / {account_label or 'main'}\n"
        f"Topic: {topic or '-'}\n"
        f"Stage/status: {stage or '-'} / {status or '-'}\n"
        f"Affiliate: {network or '-'} - {product_name or '-'} - {affiliate_url or '-'}\n"
        f"Asset URL: {asset_url or 'chưa có'}\n"
        f"Publish URL: {publish_url or 'chưa có'}\n"
        f"Operator note: {note or '-'}\n\n"
        f"Brief/publish context:\n{brief or 'Chưa có brief'}\n\n"
        "Trả về tiếng Việt theo format:\n"
        "DECISION: APPROVE hoặc FIX hoặc BLOCK\n"
        "RISK_LEVEL: LOW/MEDIUM/HIGH\n"
        "CHECKLIST:\n"
        "- Quyền hình ảnh/nhân vật/consent 18+ nếu có người mẫu hoặc OnlyFans\n"
        "- Quyền âm thanh/voice/music\n"
        "- Affiliate claim có minh bạch, không cam kết thu nhập phi thực tế\n"
        "- Không spam, không mạo danh, không né kiểm duyệt\n"
        "- Caption/CTA không gây hiểu nhầm\n"
        "- Có link affiliate và tracking cần thiết\n"
        "FIX_REQUIRED: các điểm phải sửa trước khi đăng\n"
        "APPROVAL_NOTE: câu ngắn để lưu vào pipeline"
    )

def slots_per_day(posting_slots: str) -> int:
    digits = "".join(ch for ch in (posting_slots or "") if ch.isdigit())
    if not digits:
        return 2
    return max(1, min(int(digits), 5))

def content_topic_for_slot(niche, channel_focus, platform, day_index, slot_index):
    focus = channel_focus or niche or "công nghệ"
    templates = [
        "Review nhanh {focus}: vấn đề thật và cách TOAN DAAS xử lý",
        "Top công cụ {focus} đáng dùng trong ngày",
        "Case study kiếm tiền với {focus} và link affiliate phù hợp",
        "So sánh sản phẩm {focus}: nên mua loại nào",
        "Checklist tạo nội dung {focus} để bán hàng bền vững",
        "Lỗi thường gặp khi làm {focus} và cách sửa",
    ]
    template = templates[(day_index + slot_index) % len(templates)]
    return f"{template.format(focus=focus)} ({platform})"

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

class OperatorTaskCompleteRequest(BaseModel):
    status: str = Field(default="ready", max_length=30)
    output_url: str = Field(default="", max_length=2000)
    note: str = Field(default="", max_length=1200)

class OperatorPublishCompleteRequest(BaseModel):
    status: str = Field(default="published", max_length=30)
    publish_url: str = Field(default="", max_length=2000)
    note: str = Field(default="", max_length=1200)
    views: int = Field(default=0, ge=0)
    clicks: int = Field(default=0, ge=0)

class OperatorPerformanceRequest(BaseModel):
    job_id: int = Field(gt=0)
    event_type: str = Field(default="click", max_length=40)
    value: int = Field(default=1, ge=0)
    amount: int = Field(default=0, ge=0)
    variant_id: int = Field(default=0, ge=0)
    note: str = Field(default="", max_length=1200)
    source: str = Field(default="api", max_length=120)

class OperatorLoopRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=30)
    auto_queue: bool = True
    notify_admin: bool = True

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
                    return True
                else:
                    logger.warning(f"Fish Audio lỗi {res.status_code} — fallback Edge TTS")

            communicate = edge_tts.Communicate(text, "vi-VN-NamMinhNeural")
            await communicate.save(out)
            if os.path.exists(out) and os.path.getsize(out) > 0:
                with open(out, "rb") as f:
                    await context.bot.send_audio(
                        chat_id=chat_id, audio=f,
                        caption=f"🔊 Gói Tiết Kiệm — Tổng hợp giọng nói thành công! (-{VOICE_FREE_COST} Xu)"
                    )
                await msg.delete()
                return False
            await msg.edit_text("❌ Cả hai gói đều gặp lỗi.")

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
        buttons = []
        if not trial:
            buttons.append([
                InlineKeyboardButton(
                    f"🎙️ Gói Cao Cấp — -{cost} Xu",
                    callback_data=f"prov|voice|paid|{uid}"
                )
            ])
        buttons.append([
            InlineKeyboardButton(
                f"🔊 Gói Tiết Kiệm — -{VOICE_FREE_COST} Xu",
                callback_data=f"prov|voice|free|{uid}"
            )
        ])
    else:
        buttons = []
        if not trial:
            buttons.append([
                InlineKeyboardButton(
                    f"🖼️ Gói Cao Cấp — -{cost} Xu",
                    callback_data=f"prov|image|paid|{uid}"
                )
            ])
        buttons.append([
            InlineKeyboardButton(
                f"✂️ Gói Tiết Kiệm — -{IMAGE_FREE_COST} Xu",
                callback_data=f"prov|image|free|{uid}"
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
            premium_refunded = False
            fallback_charged = False
            try:
                if FISH_AUDIO_KEY:
                    try:
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
                            await alert_admin(
                                context,
                                "Fish Audio HD",
                                f"HTTP {res.status_code}. Đã fallback Edge TTS cho user={uid}. Kiểm tra quota/số dư/API key."
                            )
                    except Exception as e:
                        logger.error(f"Fish Audio exception: {e} — fallback Edge TTS")
                        await alert_admin(
                            context,
                            "Fish Audio HD",
                            f"Exception: {str(e)}. Đã fallback Edge TTS cho user={uid}. Kiểm tra quota/số dư/API key."
                        )
                else:
                    await alert_admin(
                        context,
                        "Fish Audio HD",
                        f"Chưa cấu hình FISH_AUDIO_KEY. Đã fallback Edge TTS cho user={uid}."
                    )
                if not ok:
                    if cost > 0 and str(uid) != ADMIN_ID:
                        add_credit(uid, cost, "refund", "", "Hoàn phí voice cao cấp do fallback")
                        premium_refunded = True
                    if not spend_fixed_credit(uid, VOICE_FREE_COST, "spend_voice_free_fallback", "Fallback sang Edge TTS"):
                        await query.edit_message_text(f"❌ Không đủ xu cho gói fallback. Cần ít nhất {VOICE_FREE_COST} Xu.")
                        return
                    fallback_charged = True
                    try:
                        communicate = edge_tts.Communicate(data, "vi-VN-NamMinhNeural")
                        await communicate.save(out)
                        with open(out, "rb") as f:
                            await context.bot.send_audio(
                                chat_id=chat_id, audio=f,
                                caption=f"🔊 Gói Tiết Kiệm — Hoàn thành! (-{VOICE_FREE_COST} Xu)"
                            )
                        await query.delete_message()
                    except Exception as e:
                        logger.error(f"Edge TTS fallback error: {e}")
                        if str(uid) != ADMIN_ID and fallback_charged:
                            add_credit(uid, VOICE_FREE_COST, "refund", "", "Hoàn gói voice fallback do lỗi")
                        await query.edit_message_text("❌ Cả Fish Audio và Edge TTS đều lỗi. Xu đã hoàn lại.")
            except Exception as e:
                logger.error(f"Voice paid error: {e}")
                if cost > 0 and str(uid) != ADMIN_ID and not premium_refunded:
                    add_credit(uid, cost, "refund", "", "Hoàn phí voice cao cấp do lỗi")
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
                        await alert_admin(
                            context,
                            "RemoveBG HD",
                            f"HTTP {res.status_code}. Đã fallback Cutout.pro cho user={uid}. Kiểm tra quota/số dư/API key."
                        )
                except Exception as e:
                    logger.error(f"RemoveBG error: {e}")
                    await alert_admin(
                        context,
                        "RemoveBG HD",
                        f"Exception: {str(e)}. Đã fallback Cutout.pro cho user={uid}. Kiểm tra quota/số dư/API key."
                    )
            else:
                await alert_admin(
                    context,
                    "RemoveBG HD",
                    f"Chưa cấu hình REMOVEBG_API_KEY. Đã fallback Cutout.pro cho user={uid}."
                )
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
    order_code = generate_order_code()
    create_order(order_code, uid, amount, xu)
    USER_BILL_STATE[uid] = {
        "order_code": order_code,
        "amount": amount,
        "xu": xu,
        "pkg_key": pkg_key,
    }

    if not PAYOS_CLIENT_ID or not PAYOS_API_KEY or not PAYOS_CHECKSUM_KEY:
        update_order_status(order_code, PAYOS_STATUS_CANCELLED)
        await query.edit_message_text("⚠️ Cổng QR tự động đang bảo trì. Bot đã gửi mã QR nạp thủ công bên dưới.")
        await send_manual_payment(
            context,
            update.effective_chat.id,
            uid,
            amount,
            xu,
            order_code,
            "Cổng QR tự động đang bảo trì, vui lòng nạp thủ công theo mã QR dưới đây."
        )
        return

    return_url = make_payos_return_url(context)
    payos_body = {
        "orderCode": order_code,
        "amount": amount,
        "description": make_payos_description(pkg_key),
        "cancelUrl": return_url,
        "returnUrl": return_url
    }

    headers = {
        "x-client-id": PAYOS_CLIENT_ID,
        "x-api-key": PAYOS_API_KEY,
        "Content-Type": "application/json"
    }

    try:
        res = None
        res_data = {}
        raw_str = ""
        used_variant = ""
        signature_variants = ("payos_sorted", "faq_field_order", "payload_order")
        async with httpx.AsyncClient() as client:
            for variant in signature_variants:
                signature, raw_str = sign_payos_payment_request(payos_body, variant)
                request_body = {**payos_body, "signature": signature}
                res = await client.post(
                    "https://api-merchant.payos.vn/v2/payment-requests",
                    headers=headers,
                    json=request_body,
                    timeout=30.0
                )
                res_data = res.json()
                used_variant = variant
                if res.status_code == 200 and res_data.get("code") == "00":
                    break
                desc_try = str(res_data.get("desc", "")).lower()
                if "signature" not in desc_try and "kiểm tra" not in desc_try:
                    break
        if res.status_code == 200 and res_data.get("code") == "00":
            checkout_data = res_data["data"]
            checkout_url = checkout_data["checkoutUrl"]
            update_order_checkout_info(order_code, checkout_url, checkout_data.get("paymentLinkId", ""))
            qr_text = (
                f"⚡ <b>ĐÃ KHỞI TẠO HÓA ĐƠN QR ĐỘNG SUCCESS</b>\n\n"
                f"📋 Gói lựa chọn: <b>{pkg['text']}</b>\n"
                f"💰 Số tiền cần chuyển: <b>{amount:,}đ</b>\n"
                f"🪙 Hạn mức nhận được: <b>+{xu} Xu</b>\n"
                f"🆔 Mã đơn định danh: <code>{order_code}</code>\n\n"
                f"⏳ Hóa đơn hết hạn sau <b>{ORDER_TTL_MINUTES} phút</b>.\n\n"
                f"👉 Nhấn vào nút liên kết dưới đây để nhận diện mã QR thanh toán động. Hệ thống sẽ tự động điền sẵn số tiền và nội dung hóa đơn chính xác!"
            )
            logger.info(f"PayOS create success | order={order_code} | signature_variant={used_variant}")
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 QUÉT MÃ QR THANH TOÁN", url=checkout_url)]])
            await query.edit_message_text(qr_text, parse_mode="HTML", reply_markup=kb)
        else:
            update_order_status(order_code, PAYOS_STATUS_CANCELLED)
            logger.error(f"PayOS error response: {res_data} | variant={used_variant} | signed={raw_str}")
            desc = res_data.get("desc", "Lỗi không rõ")
            await alert_admin(
                context,
                "PayOS tạo hóa đơn",
                f"{desc} | order={order_code} | amount={amount} | variant={used_variant} | signed={raw_str} | nếu cả 3 variant đều lỗi, kiểm tra PAYOS_CHECKSUM_KEY có cùng kênh với Client ID/API Key không"
            )
            await query.edit_message_text("⚠️ Cổng QR tự động đang bận. Bot đã gửi mã QR nạp thủ công bên dưới.")
            await send_manual_payment(
                context,
                update.effective_chat.id,
                uid,
                amount,
                xu,
                order_code,
                "Cổng QR tự động đang bận, vui lòng nạp thủ công theo mã QR dưới đây."
            )
    except Exception as e:
        update_order_status(order_code, PAYOS_STATUS_CANCELLED)
        logger.error(f"PayOS Exception: {e}")
        await alert_admin(context, "PayOS API", f"Exception order={order_code}: {str(e)}")
        await query.edit_message_text("⚠️ Cổng QR tự động đang bận. Bot đã gửi mã QR nạp thủ công bên dưới.")
        await send_manual_payment(
            context,
            update.effective_chat.id,
            uid,
            amount,
            xu,
            order_code,
            "Cổng QR tự động đang bận, vui lòng nạp thủ công theo mã QR dưới đây."
        )

# ─── HANDLERS ────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    get_user(update.effective_user.id, update.effective_user.first_name)
    is_admin = str(update.effective_user.id) == ADMIN_ID
    if context.args and context.args[0].startswith("ref_"):
        referrer = context.args[0].replace("ref_", "", 1)
        if register_referral(update.effective_user.id, referrer):
            await update.message.reply_text(
                f"🎁 Đã ghi nhận mã giới thiệu. Người giới thiệu sẽ nhận {REFERRAL_BONUS_XU} Xu khi bạn nạp lần đầu."
            )
    command_lines = [
        "• /profile — Xem Hạng VIP & Số dư",
        "• /naptien — Nạp thêm hạn mức",
        "• /thucong — Nạp thủ công khi QR tự động lỗi",
        "• /gopy &lt;nội dung&gt; — Góp ý / báo lỗi",
    ]
    if is_admin:
        command_lines.extend([
            "• /tools — Kho 30 công cụ AI/MMO (Admin)",
            "• /mmo — Quy trình kiếm tiền bằng AI (Admin)",
            "• /brain — Ra lệnh tự nhiên cho AI Operator",
            "• /autopilot — Tìm trend, tạo job và build production bundle",
            "• /operator_menu — Menu vận hành AI Operator",
            "• /campaign_new — Tạo chiến dịch affiliate/video",
            "• /campaigns — Danh sách chiến dịch",
            "• /video_plan — AI lập kế hoạch video",
            "• /video_job &lt;id&gt; — Xem job video",
            "• /campaign_stats — Thống kê AI Operator",
            "• /channel_add — Thêm kênh/tài khoản nội bộ",
            "• /channels — Danh sách kênh nội bộ",
            "• /affiliate_add — Lưu link affiliate",
            "• /affiliates — Danh sách affiliate",
            "• /affiliate_profile — Cập nhật hồ sơ/claim affiliate",
            "• /affiliate_match — Chọn affiliate phù hợp trend",
            "• /calendar_plan — Lên lịch nội dung",
            "• /calendar — Xem lịch nội dung",
            "• /operator — Ra lệnh tạo video một bước",
            "• /operator_build — Tạo creative + manifest + task một lần",
            "• /operator_auto — Tự tạo batch job từ trend",
            "• /operator_next — Điều phối stage tiếp theo",
            "• /operator_dashboard — Tổng quan vận hành",
            "• /operator_loop — Quét job, tự queue job ready và báo task tiếp theo",
            "• /publish_readiness — Kiểm tra sẵn sàng auto-post",
            "• /channel_publish_set — Cấu hình mode/token kênh",
            "• /trend_search — Tìm trend mới để làm video",
            "• /trend_rank — Xếp hạng trend theo điểm affiliate",
            "• /handoff — Prompt giao việc cho AI/tool khác",
            "• /publish_pack — Gói caption/link để đăng",
            "• /review_gate — Kiểm duyệt trước khi đăng",
            "• /creative_test — Tạo biến thể hook/caption/CTA",
            "• /creative_variants — Xem biến thể creative",
            "• /creative_select — Chọn biến thể để sản xuất",
            "• /creative_report — Báo cáo biến thể thắng",
            "• /manifest — Tạo production manifest cho AI/tool",
            "• /manifests — Xem manifest của job",
            "• /manifest_handoff — Giao manifest cho từng AI/tool",
            "• /task_plan — Tách manifest thành task",
            "• /tasks — Xem production task",
            "• /next_task — Lấy task ưu tiên tiếp theo",
            "• /task_handoff — Giao từng task cho AI/tool",
            "• /task_set — Cập nhật output task",
            "• /queue_publish — Đưa job vào hàng đợi đăng",
            "• /publish_queue — Xem hàng đợi đăng",
            "• /asset_add — Lưu asset vào job",
            "• /assets — Xem asset của job",
            "• /job_report — Báo cáo đầy đủ một job",
            "• /job_ready — Kiểm tra job đủ điều kiện đăng chưa",
            "• /mark_published — Ghi nhận đã đăng bài",
            "• /performance_add — Ghi hiệu quả bài đăng",
            "• /performance — Báo cáo hiệu quả kiếm tiền",
            "• /growth — Tối ưu nội dung/kênh/affiliate theo performance",
            "• /produce — Tạo job sản xuất từ lịch",
            "• /pipeline — Theo dõi pipeline video",
            "• /pipeline_set — Cập nhật stage/trạng thái",
            "• /dashboard — Dashboard quản trị",
            "• /checkpayos &lt;mã_đơn&gt; — Kiểm tra lại đơn PayOS",
        ])
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
        + "\n".join(command_lines)
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

async def cmd_thanhtoan_thucong(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    amount = 0
    xu = 0
    if context.args:
        pkg_key = context.args[0].lower()
        if pkg_key in PAYMENT_PACKAGES:
            pkg = PAYMENT_PACKAGES[pkg_key]
            amount, xu = pkg["amount"], pkg["xu"]
    order_code = generate_order_code()
    if amount and xu:
        create_order(order_code, uid, amount, xu)
        USER_BILL_STATE[uid] = {"order_code": order_code, "amount": amount, "xu": xu, "pkg_key": context.args[0].lower()}
        return await send_manual_payment(context, update.effective_chat.id, uid, amount, xu, order_code)
    else:
        USER_BILL_STATE[uid] = True
        text = (
            "🏦 <b>NẠP XU THỦ CÔNG</b>\n\n"
            f"👤 ID Telegram: <code>{uid}</code>\n\n"
            f"• Ngân hàng: <b>{MANUAL_BANK_NAME}</b>\n"
            f"• Số tài khoản: <code>{MANUAL_BANK_ACCOUNT}</code>\n"
            f"• Chủ tài khoản: <b>{MANUAL_BANK_OWNER}</b>\n"
            f"• Nội dung: <code>DAAS {uid}</code>\n\n"
            "📸 Sau khi chuyển khoản, gửi ảnh bill tại đây.\n"
            "Gợi ý: <code>/thucong 10k</code>, <code>/thucong 100k</code> để bot tự điền số tiền và số Xu."
        )
    await update.message.reply_text(text, parse_mode="HTML")

async def cmd_tools(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return await update.message.reply_text(
            "🔒 Lệnh này chỉ dành cho Admin.", parse_mode="HTML"
        )
    text = (
        "🧰 <b>KHO 30 CÔNG CỤ CHUẨN</b>\n\n"
        "<b>Viết & nghiên cứu:</b> ChatGPT, Perplexity, DeepL, Notion\n"
        "<b>Ảnh & thiết kế:</b> Ideogram, Photopea, Remove.bg, Upscale.media, ResizePixel, Canva, Figma\n"
        "<b>Video:</b> CapCut, Kling AI, Cobalt Tools, DaVinci Resolve\n"
        "<b>Audio:</b> ElevenLabs, Whisper, Suno, Moises\n"
        "<b>Tài liệu:</b> PDF24, OCR Space, Convertio, Google Drive, Google Forms\n"
        "<b>Ý tưởng & quản lý:</b> Excalidraw, XMind, Cursor, GitHub\n"
        "<b>Marketing/Web:</b> Ahrefs Free Tools, Framer\n\n"
        "⚙️ <b>Stack đang chạy trong bot:</b>\n"
        "• Chat: Gemini → fallback OpenAI\n"
        "• Voice: Fish Audio HD → fallback Edge TTS + hoàn chênh lệch\n"
        "• Tách nền: RemoveBG HD → fallback Cutout.pro + hoàn chênh lệch\n"
        "• Bóc băng: Deepgram\n"
        "• Download: Cobalt\n\n"
        "💡 Nguyên tắc: ưu tiên công cụ tốt nhất trước; nếu lỗi/quota thì chuyển công cụ dự phòng và ghi refund."
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def cmd_mmo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return await update.message.reply_text(
            "🔒 Lệnh này chỉ dành cho Admin.", parse_mode="HTML"
        )
    text = (
        "💰 <b>WORKFLOW AI KIẾM TIỀN HỢP PHÁP</b>\n\n"
        "<b>1. Faceless video:</b> ChatGPT/Claude viết kịch bản → ElevenLabs/Edge TTS đọc → Kling/CapCut dựng → đăng TikTok/Reels/YouTube Shorts.\n"
        "<b>2. TikTok Affiliate:</b> chọn niche dễ mua → tạo 3-5 video/ngày → gắn sản phẩm → đo video thắng và remix.\n"
        "<b>3. Dịch vụ video AI:</b> nhận brief doanh nghiệp nhỏ → báo giá 500k-2M/video → giao kịch bản, voice, phụ đề, bản dựng.\n"
        "<b>4. Ảnh người mẫu AI:</b> chỉ dùng nhân vật tự tạo hoặc người thật có đồng ý rõ ràng, đủ 18 tuổi; không giả mạo người khác.\n\n"
        "✅ Bắt đầu nhỏ: 1 niche, 1 format, 30 video đầu tiên. Dùng /tools để lấy bộ công cụ."
    )
    await update.message.reply_text(text, parse_mode="HTML")

def parse_key_value_args(raw: str) -> dict:
    data = {}
    current_key = None
    for token in raw.split():
        if "=" in token:
            key, value = token.split("=", 1)
            current_key = key.strip().lower()
            data[current_key] = value.strip()
        elif current_key:
            data[current_key] += " " + token.strip()
    return data

def int_from_text(text, keys, default=0):
    for key in keys:
        match = re.search(rf"(?:{re.escape(key)}|{re.escape(key)}=)\s*#?(\d+)", text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return default

def first_number_near(text, words, default=0):
    for word in words:
        match = re.search(rf"(\d+)\s+(?:\S+\s+){{0,2}}{re.escape(word)}", text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        match = re.search(rf"{re.escape(word)}\s*(?:=|#)?\s*(\d+)", text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return default

def compact_arg_value(value):
    value = str(value or "").strip()
    if not value:
        return ""
    if any(ch.isspace() for ch in value):
        return value
    return value

def operator_brain_fallback(raw_text):
    text = raw_text.strip()
    lower = text.lower()
    platform = "tiktok"
    for candidate in ["tiktok", "facebook", "fb", "reels", "youtube", "shorts", "onlyfan", "onlyfans"]:
        if candidate in lower:
            platform = "facebook" if candidate in {"fb", "reels"} else ("youtube" if candidate == "shorts" else candidate)
            break
    channel_id = int_from_text(lower, ["channel", "kenh", "kênh"], 0)
    affiliate_id = int_from_text(lower, ["aff", "affiliate"], 0)
    campaign_id = int_from_text(lower, ["campaign", "camp", "chiến dịch", "chien dich"], 0)
    job_id = int_from_text(lower, ["job", "video job"], 0)
    limit = first_number_near(lower, ["video", "job", "trend"], 0) or int_from_text(lower, ["limit", "max"], 0) or 5
    duration = int_from_text(lower, ["duration", "dai", "dài"], 45) or 45

    if any(word in lower for word in ["ready", "sẵn sàng", "san sang", "đủ điều kiện", "du dieu kien"]):
        return {"intent": "job_ready", "job": job_id, "confidence": 70}
    if any(word in lower for word in ["build", "dựng", "san xuat", "sản xuất", "manifest", "task"]):
        return {"intent": "operator_build", "job": job_id, "duration": duration, "limit": limit, "confidence": 70}
    if any(word in lower for word in ["daily", "báo cáo ngày", "bao cao ngay", "tổng quan", "tong quan", "dashboard"]):
        return {"intent": "operator_daily", "days": int_from_text(lower, ["days", "ngày", "ngay"], 1) or 1, "confidence": 65}
    if any(word in lower for word in ["autopilot", "tự chạy", "tu chay", "tự động hết", "tu dong het", "build luôn", "build luon"]):
        niche = re.sub(r"\b(autopilot|tự chạy|tu chay|tự động hết|tu dong het|build luôn|build luon|tạo|tao|làm|lam|video|trend|cho|trên|tren|gắn|gan|link|affiliate|aff|campaign|camp|limit|job)\b", " ", lower)
        niche = re.sub(r"\b(tiktok|facebook|fb|youtube|shorts|onlyfan|onlyfans|reels)\b", " ", niche)
        niche = re.sub(r"\s+", " ", niche).strip(" :=#") or "công nghệ AI"
        return {
            "intent": "autopilot",
            "niche": niche,
            "platform": platform,
            "channel": channel_id or "all",
            "affiliate": affiliate_id,
            "campaign": campaign_id,
            "limit": max(1, min(limit, 8)),
            "duration": duration,
            "confidence": 75,
        }
    if any(word in lower for word in ["trend", "viral", "mới nhất", "moi nhat"]) or "tạo" in lower and "video" in lower and channel_id == 0:
        niche = re.sub(r"\b(tạo|tao|làm|lam|video|trend|viral|mới nhất|moi nhat|cho|trên|tren|kênh|kenh|gắn|gan|link|affiliate|aff|campaign|camp|limit|job)\b", " ", lower)
        niche = re.sub(r"\b(tiktok|facebook|fb|youtube|shorts|onlyfan|onlyfans|reels)\b", " ", niche)
        niche = re.sub(r"\s+", " ", niche).strip(" :=#") or "công nghệ AI"
        return {
            "intent": "operator_auto",
            "niche": niche,
            "platform": platform,
            "channel": channel_id or "all",
            "affiliate": affiliate_id,
            "campaign": campaign_id,
            "limit": max(1, min(limit, 15)),
            "confidence": 60,
        }
    return {
        "intent": "operator",
        "topic": text,
        "platform": platform,
        "channel": channel_id,
        "affiliate": affiliate_id,
        "campaign": campaign_id,
        "confidence": 45,
    }

def parse_operator_brain(raw_text, owner_id):
    fallback = operator_brain_fallback(raw_text)
    if not (gemini_client or openai_client):
        return fallback
    prompt = (
        "Bạn là bộ định tuyến lệnh cho Telegram bot TOAN DAAS AI Operator. "
        "Chuyển câu lệnh tự nhiên của admin thành JSON thuần, không markdown. "
        "Chỉ chọn một intent trong: autopilot, operator_auto, operator, operator_build, job_ready, operator_daily, trend_search, publish_queue, performance, help.\n\n"
        "Quy tắc:\n"
        "- operator_auto: khi admin muốn tìm trend/tạo nhiều video theo niche/platform.\n"
        "- autopilot: khi admin muốn tìm trend, tạo job và build luôn creative/manifest/task trong một lệnh.\n"
        "- operator: khi admin nêu một topic cụ thể và có channel để tạo một job.\n"
        "- operator_build: khi admin muốn dựng tiếp một job đã có thành creative/manifest/task.\n"
        "- job_ready: khi admin muốn kiểm tra đủ điều kiện đăng.\n"
        "- operator_daily: khi admin muốn báo cáo/tổng quan.\n"
        "- Không tự động chọn nội dung vi phạm, mạo danh người thật, deepfake không consent, claim affiliate quá mức.\n\n"
        "Schema:\n"
        '{"intent":"autopilot","niche":"công nghệ AI","platform":"tiktok","channel":"all","affiliate":0,"campaign":0,"job":0,"limit":3,"duration":45,"days":1,"topic":"","confidence":0,"safety_note":""}'
    )
    try:
        raw = AgentGemini.chat(prompt, raw_text, owner_id, is_json=True)
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and parsed.get("intent"):
            merged = {**fallback, **{k: v for k, v in parsed.items() if v not in (None, "")}}
            return merged
    except Exception as e:
        logger.warning(f"Operator brain parse fallback: {e}")
    return fallback

def brain_command_preview(plan):
    intent = (plan.get("intent") or "help").lower()
    if intent == "operator_auto":
        return (
            f"/operator_auto niche={plan.get('niche') or 'công nghệ AI'} "
            f"platform={plan.get('platform') or 'tiktok'} channel={plan.get('channel') or 'all'} "
            f"aff={int(plan.get('affiliate') or 0)} campaign={int(plan.get('campaign') or 0)} "
            f"limit={max(1, min(int(plan.get('limit') or 5), 15))}"
        )
    if intent == "autopilot":
        return (
            f"/autopilot niche={plan.get('niche') or 'công nghệ AI'} "
            f"platform={plan.get('platform') or 'tiktok'} channel={plan.get('channel') or 'all'} "
            f"aff={int(plan.get('affiliate') or 0)} campaign={int(plan.get('campaign') or 0)} "
            f"limit={max(1, min(int(plan.get('limit') or 3), 8))} duration={int(plan.get('duration') or 45)}"
        )
    if intent == "operator":
        return (
            f"/operator topic={plan.get('topic') or plan.get('niche') or 'video affiliate'} "
            f"channel={int(plan.get('channel') or 0)} aff={int(plan.get('affiliate') or 0)} "
            f"campaign={int(plan.get('campaign') or 0)}"
        )
    if intent == "operator_build":
        return f"/operator_build job={int(plan.get('job') or 0)} n={max(2, min(int(plan.get('limit') or 5), 8))} duration={int(plan.get('duration') or 45)}"
    if intent == "job_ready":
        return f"/job_ready job={int(plan.get('job') or 0)}"
    if intent == "operator_daily":
        return f"/operator_daily days={max(1, min(int(plan.get('days') or 1), 30))}"
    if intent == "trend_search":
        return (
            f"/trend_search niche={plan.get('niche') or 'công nghệ AI'} "
            f"platform={plan.get('platform') or 'tiktok'} channel={int(plan.get('channel') or 0)} "
            f"aff={int(plan.get('affiliate') or 0)} campaign={int(plan.get('campaign') or 0)}"
        )
    if intent == "publish_queue":
        return "/publish_queue"
    if intent == "performance":
        return "/performance"
    return "/operator_menu"

async def run_brain_plan(update, context, plan):
    intent = (plan.get("intent") or "help").lower()
    old_args = list(getattr(context, "args", []) or [])
    try:
        if intent == "operator_auto":
            context.args = [
                f"niche={plan.get('niche') or 'công nghệ AI'}",
                f"platform={plan.get('platform') or 'tiktok'}",
                f"channel={plan.get('channel') or 'all'}",
                f"aff={int(plan.get('affiliate') or 0)}",
                f"campaign={int(plan.get('campaign') or 0)}",
                f"limit={max(1, min(int(plan.get('limit') or 5), 15))}",
            ]
            return await cmd_operator_auto(update, context)
        if intent == "autopilot":
            context.args = [
                f"niche={plan.get('niche') or 'công nghệ AI'}",
                f"platform={plan.get('platform') or 'tiktok'}",
                f"channel={plan.get('channel') or 'all'}",
                f"aff={int(plan.get('affiliate') or 0)}",
                f"campaign={int(plan.get('campaign') or 0)}",
                f"limit={max(1, min(int(plan.get('limit') or 3), 8))}",
                f"duration={int(plan.get('duration') or 45)}",
            ]
            return await cmd_autopilot(update, context)
        if intent == "operator":
            if not int(plan.get("channel") or 0):
                return await update.message.reply_text(
                    "⚠️ Lệnh tạo một video cần <code>channel=&lt;ID&gt;</code>. Xem ID bằng /channels hoặc dùng /brain tạo video trend ... để chạy batch channel=all.",
                    parse_mode="HTML"
                )
            context.args = [
                f"topic={plan.get('topic') or plan.get('niche') or 'video affiliate'}",
                f"channel={int(plan.get('channel') or 0)}",
                f"aff={int(plan.get('affiliate') or 0)}",
                f"campaign={int(plan.get('campaign') or 0)}",
            ]
            return await cmd_operator(update, context)
        if intent == "operator_build":
            if not int(plan.get("job") or 0):
                return await update.message.reply_text("⚠️ Cần job ID. Ví dụ: <code>/brain build job 12</code>", parse_mode="HTML")
            context.args = [
                f"job={int(plan.get('job') or 0)}",
                f"n={max(2, min(int(plan.get('limit') or 5), 8))}",
                f"duration={int(plan.get('duration') or 45)}",
            ]
            return await cmd_operator_build(update, context)
        if intent == "job_ready":
            if not int(plan.get("job") or 0):
                return await update.message.reply_text("⚠️ Cần job ID. Ví dụ: <code>/brain kiểm tra job 12 đã ready chưa</code>", parse_mode="HTML")
            context.args = [f"job={int(plan.get('job') or 0)}"]
            return await cmd_job_ready(update, context)
        if intent == "operator_daily":
            context.args = [f"days={max(1, min(int(plan.get('days') or 1), 30))}"]
            return await cmd_operator_daily(update, context)
        if intent == "trend_search":
            context.args = [
                f"niche={plan.get('niche') or 'công nghệ AI'}",
                f"platform={plan.get('platform') or 'tiktok'}",
                f"channel={int(plan.get('channel') or 0)}",
                f"aff={int(plan.get('affiliate') or 0)}",
                f"campaign={int(plan.get('campaign') or 0)}",
            ]
            return await cmd_trend_search(update, context)
        if intent == "publish_queue":
            context.args = []
            return await cmd_publish_queue(update, context)
        if intent == "performance":
            context.args = []
            return await cmd_performance(update, context)
        context.args = []
        return await cmd_operator_menu(update, context)
    finally:
        context.args = old_args

def truncate_text(text: str, limit: int = 3500) -> str:
    return text if len(text) <= limit else text[: limit - 20] + "\n...[đã rút gọn]"

def html_pre(text: str, limit: int = 3500) -> str:
    return html.escape(truncate_text(text, limit))

def build_video_brief_prompt(campaign, topic, platforms, affiliate_url):
    _, _, name, niche, campaign_platforms, campaign_affiliate, pay_url, _ = campaign
    target_platforms = platforms or campaign_platforms
    target_affiliate = affiliate_url or campaign_affiliate or pay_url
    return (
        "Bạn là AI Operator trưởng cho hệ thống TOAN DAAS. "
        "Tạo kế hoạch video kiếm tiền hợp pháp, không spam, không giả mạo người thật, "
        "không hướng dẫn né kiểm duyệt nền tảng. Nếu có người mẫu/AI influencer thì chỉ dùng nhân vật tự tạo hoặc có consent 18+.\n\n"
        f"Chiến dịch: {name}\n"
        f"Niche: {niche}\n"
        f"Nền tảng: {target_platforms}\n"
        f"Chủ đề video: {topic}\n"
        f"Link affiliate/thu tiền: {target_affiliate or 'chưa có'}\n\n"
        "Trả về bằng tiếng Việt, dạng JSON có các khóa: hook, script_45s, shot_list, voice_style, visual_prompts, "
        "caption_by_platform, hashtags, cta, affiliate_placement, compliance_check, next_actions. "
        "Mỗi caption phải có vị trí gắn link/CTA rõ ràng."
    )

async def cmd_campaign_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    raw = " ".join(context.args)
    data = parse_key_value_args(raw)
    name = data.get("name") or data.get("ten")
    niche = data.get("niche") or data.get("ngach")
    platforms = data.get("platforms") or data.get("nen") or "tiktok,facebook,youtube"
    affiliate_url = data.get("affiliate") or data.get("link") or ""
    pay_url = data.get("pay") or data.get("payos") or ""
    if not name or not niche:
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/campaign_new name=AI Tools niche=affiliate platforms=tiktok,fb affiliate=https://...</code>",
            parse_mode="HTML"
        )
    campaign_id = create_campaign(update.effective_user.id, name, niche, platforms, affiliate_url, pay_url)
    await update.message.reply_text(
        f"✅ <b>Đã tạo campaign #{campaign_id}</b>\n"
        f"• Tên: <b>{name}</b>\n"
        f"• Niche: <b>{niche}</b>\n"
        f"• Nền tảng: <code>{platforms}</code>\n"
        f"• Affiliate: <code>{affiliate_url or 'chưa có'}</code>\n\n"
        f"Tạo video: <code>/video_plan campaign={campaign_id} topic=...</code>",
        parse_mode="HTML"
    )

async def cmd_campaigns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    rows = list_campaigns(update.effective_user.id)
    if not rows:
        return await update.message.reply_text("📭 Chưa có campaign. Tạo bằng /campaign_new.")
    lines = ["📌 <b>CAMPAIGN ĐANG CÓ</b>\n"]
    for cid, name, niche, platforms, affiliate_url, status in rows:
        lines.append(f"• #{cid} | <b>{name}</b> | {niche} | <code>{platforms}</code> | {status}")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_video_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    if not gemini_client and not openai_client:
        return await update.message.reply_text("❌ Chưa cấu hình AI Provider.")
    raw = " ".join(context.args)
    data = parse_key_value_args(raw)
    try:
        campaign_id = int(data.get("campaign") or data.get("camp") or data.get("id"))
    except (TypeError, ValueError):
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/video_plan campaign=1 topic=5 công cụ AI giúp kiếm tiền platforms=tiktok,fb</code>",
            parse_mode="HTML"
        )
    topic = data.get("topic") or data.get("chude")
    if not topic:
        return await update.message.reply_text("⚠️ Thiếu <code>topic=...</code>", parse_mode="HTML")
    campaign = get_campaign(campaign_id, update.effective_user.id)
    if not campaign:
        return await update.message.reply_text("❌ Không tìm thấy campaign hoặc không có quyền.")
    platforms = data.get("platforms") or data.get("nen") or ""
    affiliate_url = data.get("affiliate") or data.get("link") or ""
    channel_id = data.get("channel") or data.get("kenh")
    if channel_id:
        try:
            channel = get_social_channel(int(channel_id), update.effective_user.id)
        except ValueError:
            channel = None
        if not channel:
            return await update.message.reply_text("❌ Không tìm thấy channel hoặc không có quyền.")
        platforms = platforms or channel[1]
    affiliate_id = data.get("affiliate_id") or data.get("aff")
    if affiliate_id:
        try:
            affiliate = get_affiliate_link(int(affiliate_id), update.effective_user.id)
        except ValueError:
            affiliate = None
        if not affiliate:
            return await update.message.reply_text("❌ Không tìm thấy affiliate hoặc không có quyền.")
        affiliate_url = affiliate_url or affiliate[4]
    prompt = build_video_brief_prompt(campaign, topic, platforms, affiliate_url)
    msg = await update.message.reply_text("⏳ AI Operator đang lập kế hoạch video...")
    brief = AgentGemini.chat(
        "Bạn là AI Operator chuyên lập kế hoạch video affiliate hợp pháp, có kiểm duyệt trước khi đăng.",
        prompt,
        update.effective_user.id,
        is_json=False
    )
    job_id = create_video_job(campaign_id, update.effective_user.id, topic, platforms or campaign[4], affiliate_url or campaign[5] or campaign[6], brief)
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Duyệt job", callback_data=f"job|approve|{job_id}"),
            InlineKeyboardButton("❌ Hủy", callback_data=f"job|cancel|{job_id}")
        ],
        [InlineKeyboardButton("📊 Stats", callback_data="job|stats|0")]
    ])
    await msg.edit_text(
        f"🎬 <b>VIDEO JOB #{job_id}</b>\n"
        f"Campaign: <b>#{campaign_id}</b>\n"
        f"Topic: <b>{topic}</b>\n\n"
        f"<pre>{html_pre(brief)}</pre>\n\n"
        "Trạng thái: <b>DRAFT - chờ duyệt</b>",
        parse_mode="HTML",
        reply_markup=kb
    )

async def cmd_video_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    try:
        job_id = int(context.args[0])
    except (IndexError, ValueError):
        return await update.message.reply_text("⚠️ Cú pháp: /video_job <ID>")
    job = get_video_job(job_id, update.effective_user.id)
    if not job:
        return await update.message.reply_text("❌ Không tìm thấy job.")
    _, campaign_id, _, topic, platforms, affiliate_url, status, brief = job
    await update.message.reply_text(
        f"🎬 <b>VIDEO JOB #{job_id}</b>\n"
        f"Campaign: <b>#{campaign_id}</b>\n"
        f"Topic: <b>{topic}</b>\n"
        f"Nền tảng: <code>{platforms}</code>\n"
        f"Affiliate: <code>{affiliate_url or 'chưa có'}</code>\n"
        f"Status: <b>{status}</b>\n\n"
        f"<pre>{html_pre(brief)}</pre>",
        parse_mode="HTML"
    )

async def cmd_campaign_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    total_campaigns, job_counts, recent_jobs = campaign_stats(update.effective_user.id)
    lines = [
        "📊 <b>AI OPERATOR STATS</b>",
        f"Campaign: <b>{total_campaigns}</b>",
        "Video jobs: " + ", ".join(f"{k}={v}" for k, v in job_counts.items()) if job_counts else "Video jobs: 0",
        "",
        "<b>Job gần nhất:</b>",
    ]
    for jid, topic, platforms, status, created_at in recent_jobs:
        lines.append(f"• #{jid} | {status} | <code>{platforms}</code> | {topic}")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_channel_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    platform = data.get("platform") or data.get("nen")
    name = data.get("name") or data.get("kenh")
    account = data.get("account") or data.get("tk") or ""
    focus = data.get("focus") or data.get("niche") or data.get("ngach") or ""
    audience = data.get("audience") or data.get("khach") or ""
    slots = data.get("slots") or data.get("lich") or "2/day"
    notes = data.get("notes") or data.get("note") or ""
    publish_mode = (data.get("mode") or data.get("publish_mode") or "manual").lower()
    token_env = data.get("token_env") or data.get("token") or ""
    page_id = data.get("page_id") or data.get("page") or ""
    if not platform or not name:
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/channel_add platform=tiktok name=TechVN account=tk1 focus=AI tools audience=creator slots=2/day mode=manual</code>",
            parse_mode="HTML"
        )
    if publish_mode not in {"manual", "api"}:
        return await update.message.reply_text("⚠️ mode hợp lệ: <code>manual</code> hoặc <code>api</code>", parse_mode="HTML")
    channel_id = create_social_channel(update.effective_user.id, platform, name, account, focus, audience, slots, notes, publish_mode, token_env, page_id)
    await update.message.reply_text(
        f"✅ <b>Đã thêm channel #{channel_id}</b>\n"
        f"• Nền tảng: <code>{html.escape(platform)}</code>\n"
        f"• Kênh: <b>{html.escape(name)}</b>\n"
        f"• Tài khoản: <code>{html.escape(account or 'chưa ghi')}</code>\n"
        f"• Chủ đề: {html.escape(focus or 'chưa ghi')}\n"
        f"• Lịch: <code>{html.escape(slots)}</code>\n"
        f"• Publish mode: <code>{html.escape(publish_mode)}</code>",
        parse_mode="HTML"
    )

async def cmd_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    rows = list_social_channels(update.effective_user.id)
    if not rows:
        return await update.message.reply_text("📭 Chưa có channel. Tạo bằng /channel_add.")
    lines = ["📡 <b>KÊNH NỘI BỘ</b>\n"]
    for cid, platform, name, account, focus, audience, slots, status in rows:
        lines.append(
            f"• #{cid} | <code>{html.escape(platform)}</code> | <b>{html.escape(name)}</b> | "
            f"{html.escape(account or '-') } | {html.escape(focus or '-') } | {html.escape(slots or '-') } | {status}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_channel_publish_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        channel_id = int(data.get("id") or data.get("channel") or data.get("kenh") or context.args[0])
    except (IndexError, TypeError, ValueError):
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/channel_publish_set id=1 mode=api token_env=TIKTOK_ACCESS_TOKEN page_id=...</code>",
            parse_mode="HTML"
        )
    mode = (data.get("mode") or data.get("publish_mode") or "").lower()
    if mode and mode not in {"manual", "api"}:
        return await update.message.reply_text("⚠️ mode hợp lệ: <code>manual</code> hoặc <code>api</code>", parse_mode="HTML")
    token_env = data.get("token_env") or data.get("token")
    page_id = data.get("page_id") or data.get("page")
    if not (mode or token_env is not None or page_id is not None):
        return await update.message.reply_text("⚠️ Cần ít nhất một trường: mode, token_env hoặc page_id.", parse_mode="HTML")
    changed = set_social_publish_config(update.effective_user.id, channel_id, mode or None, token_env, page_id)
    if not changed:
        return await update.message.reply_text("❌ Không tìm thấy channel hoặc không có quyền.")
    await update.message.reply_text(
        f"✅ Đã cập nhật publish config cho channel #{channel_id}\n"
        f"• mode=<code>{html.escape(mode or 'giữ nguyên')}</code>\n"
        f"• token_env=<code>{html.escape(token_env or 'giữ nguyên')}</code>\n"
        f"• page_id=<code>{html.escape(page_id or 'giữ nguyên')}</code>",
        parse_mode="HTML"
    )

async def cmd_publish_readiness(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    rows = list_social_publish_readiness(update.effective_user.id)
    if not rows:
        return await update.message.reply_text("📭 Chưa có channel. Tạo bằng /channel_add.")
    lines = ["🧪 <b>AUTO-POST READINESS</b>\n"]
    for row in rows:
        cid, platform, channel_name, account_label, status, publish_mode, token_env, page_id = row
        readiness, reason = channel_publish_readiness(row)
        icon = "✅" if readiness in {"manual_ready", "api_ready"} else "⚠️"
        lines.append(
            f"{icon} #{cid} | <code>{html.escape(platform or '-')}</code> | "
            f"{html.escape(channel_name or '-')} / {html.escape(account_label or 'main')}\n"
            f"  mode=<code>{html.escape(publish_mode or 'manual')}</code> "
            f"token_env=<code>{html.escape(token_env or '-')}</code> page=<code>{html.escape(page_id or '-')}</code>\n"
            f"  readiness=<b>{html.escape(readiness)}</b> — {html.escape(reason)}"
        )
    lines.append(
        "\nCấu hình: <code>/channel_publish_set id=&lt;ID&gt; mode=api token_env=TIKTOK_ACCESS_TOKEN page_id=...</code>"
    )
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_affiliate_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    network = data.get("network") or data.get("san") or data.get("shop")
    product = data.get("product") or data.get("sp") or data.get("name")
    niche = data.get("niche") or data.get("ngach") or ""
    url = data.get("url") or data.get("link") or ""
    note = data.get("note") or data.get("commission") or data.get("hh") or ""
    try:
        price_vnd = int(data.get("price") or data.get("gia") or 0)
    except ValueError:
        price_vnd = 0
    try:
        commission_rate = float(data.get("rate") or data.get("commission_rate") or data.get("tile") or 0)
    except ValueError:
        commission_rate = 0
    audience = data.get("audience") or data.get("khach") or ""
    allowed_claims = data.get("allowed") or data.get("claim_ok") or ""
    blocked_claims = data.get("blocked") or data.get("claim_cam") or ""
    base_score = clamp_score(40 + (15 if url else 0) + (10 if commission_rate else 0) + (10 if allowed_claims else 0) - (5 if blocked_claims else 0))
    if not network or not product:
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/affiliate_add network=shopee product=mic thu am niche=cong nghe url=https://... price=199000 rate=8 audience=creator allowed=thu am ro blocked=cam ket doanh thu</code>",
            parse_mode="HTML"
        )
    affiliate_id = create_affiliate_link(
        update.effective_user.id, network, product, niche, url, note,
        price_vnd, commission_rate, audience, allowed_claims, blocked_claims, base_score
    )
    await update.message.reply_text(
        f"✅ <b>Đã lưu affiliate #{affiliate_id}</b>\n"
        f"• Sàn: <code>{html.escape(network)}</code>\n"
        f"• Sản phẩm: <b>{html.escape(product)}</b>\n"
        f"• Niche: {html.escape(niche or 'chưa ghi')}\n"
        f"• Giá: <b>{price_vnd:,}đ</b> | Hoa hồng: <b>{commission_rate:g}%</b>\n"
        f"• Score nền: <b>{base_score}</b>\n"
        f"• Link: <code>{html.escape(url or 'chưa có')}</code>",
        parse_mode="HTML"
    )

async def cmd_affiliates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    rows = list_affiliate_links(update.effective_user.id)
    if not rows:
        return await update.message.reply_text("📭 Chưa có affiliate. Tạo bằng /affiliate_add.")
    lines = ["🛒 <b>LINK AFFILIATE NỘI BỘ</b>\n"]
    for aid, network, product, niche, url, note, status, price_vnd, commission_rate, audience, allowed_claims, blocked_claims, product_score in rows:
        url_display = url if len(url or "") <= 70 else url[:67] + "..."
        lines.append(
            f"• #{aid} | <code>{html.escape(network)}</code> | <b>{html.escape(product)}</b> | "
            f"{html.escape(niche or '-') } | score={product_score or 0} | {status}\n"
            f"  giá={int(price_vnd or 0):,}đ | rate={float(commission_rate or 0):g}% | khách={html.escape(audience or '-')}\n"
            f"  note={html.escape(note or '-')}\n"
            f"  <code>{html.escape(url_display or 'chưa có link')}</code>"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_affiliate_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        affiliate_id = int(data.get("id") or data.get("aff") or context.args[0])
    except (IndexError, TypeError, ValueError):
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/affiliate_profile id=1 price=199000 rate=8 audience=creator allowed=... blocked=... score=70 status=active</code>",
            parse_mode="HTML"
        )
    if not get_affiliate_link(affiliate_id, update.effective_user.id):
        return await update.message.reply_text("❌ Không tìm thấy affiliate.")
    fields = {}
    mapping = {
        "network": "network", "product": "product_name", "name": "product_name",
        "niche": "niche", "url": "url", "link": "url", "note": "commission_note",
        "audience": "target_audience", "allowed": "allowed_claims", "blocked": "blocked_claims",
        "status": "status",
    }
    for src, dest in mapping.items():
        if src in data:
            fields[dest] = data[src]
    int_fields = {"price": "price_vnd", "gia": "price_vnd", "score": "product_score"}
    for src, dest in int_fields.items():
        if src in data:
            try:
                fields[dest] = int(data[src])
            except ValueError:
                pass
    if "rate" in data or "commission_rate" in data:
        try:
            fields["commission_rate"] = float(data.get("rate") or data.get("commission_rate") or 0)
        except ValueError:
            pass
    if not fields:
        return await update.message.reply_text("⚠️ Chưa có trường nào để cập nhật.")
    changed = update_affiliate_profile(update.effective_user.id, affiliate_id, **fields)
    if not changed:
        return await update.message.reply_text("❌ Không cập nhật được affiliate.")
    affiliate = get_affiliate_link(affiliate_id, update.effective_user.id)
    (
        aid, network, product, niche, url, note, status,
        price_vnd, commission_rate, audience, allowed_claims, blocked_claims, product_score
    ) = affiliate
    await update.message.reply_text(
        f"✅ <b>Đã cập nhật affiliate #{aid}</b>\n"
        f"• {html.escape(network or '-')} / <b>{html.escape(product or '-')}</b>\n"
        f"• Niche: {html.escape(niche or '-')}\n"
        f"• Giá: <b>{int(price_vnd or 0):,}đ</b> | Rate: <b>{float(commission_rate or 0):g}%</b> | Score: <b>{product_score or 0}</b>\n"
        f"• Khách mục tiêu: {html.escape(audience or '-')}\n"
        f"• Claim OK: {html.escape(allowed_claims or '-')}\n"
        f"• Claim cấm: {html.escape(blocked_claims or '-')}",
        parse_mode="HTML"
    )

async def cmd_affiliate_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    niche = data.get("niche") or data.get("ngach") or data.get("topic") or "công nghệ AI"
    trend_text = data.get("trend") or data.get("text") or data.get("chude") or ""
    platform = data.get("platform") or data.get("nen") or "tiktok"
    try:
        limit = max(1, min(int(data.get("limit") or 10), 20))
    except ValueError:
        limit = 10
    ranked = list_affiliate_matches(update.effective_user.id, niche, trend_text, platform, limit)
    if not ranked:
        return await update.message.reply_text("📭 Chưa có affiliate active để match.")
    lines = [
        "🎯 <b>AFFILIATE MATCH</b>",
        f"• Niche: <b>{html.escape(niche)}</b>",
        f"• Platform: <code>{html.escape(platform)}</code>",
        f"• Trend/topic: {html.escape(trend_text or '-')}\n",
    ]
    for score, hits, blocked_hits, row in ranked:
        (
            aid, network, product, aff_niche, url, note, status,
            price_vnd, commission_rate, audience, allowed_claims, blocked_claims, product_score
        ) = row
        lines.append(
            f"• #{aid} | match=<b>{score}</b> | hits={hits} | blocked={blocked_hits} | base={product_score or 0}\n"
            f"  <code>{html.escape(network or '-')}</code> / <b>{html.escape(product or '-')}</b> | {html.escape(aff_niche or '-')}\n"
            f"  giá={int(price_vnd or 0):,}đ | rate={float(commission_rate or 0):g}% | khách={html.escape(audience or '-')}\n"
            f"  claim OK={html.escape(allowed_claims or '-')}\n"
            f"  claim cấm={html.escape(blocked_claims or '-')}"
        )
    lines.append("\nDùng ID phù hợp trong /trend_search, /operator hoặc /operator_auto bằng <code>aff=&lt;ID&gt;</code>.")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_calendar_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        days = max(1, min(int(data.get("days") or data.get("ngay") or 7), 30))
    except ValueError:
        days = 7
    channel_filter = (data.get("channel") or data.get("kenh") or "all").lower()
    try:
        campaign_id = int(data.get("campaign") or data.get("camp") or 0)
    except ValueError:
        campaign_id = 0
    try:
        affiliate_id = int(data.get("affiliate_id") or data.get("aff") or 0)
    except ValueError:
        affiliate_id = 0
    niche = data.get("niche") or data.get("ngach") or "công nghệ"

    if campaign_id and not get_campaign(campaign_id, update.effective_user.id):
        return await update.message.reply_text("❌ Không tìm thấy campaign.")
    if affiliate_id and not get_affiliate_link(affiliate_id, update.effective_user.id):
        return await update.message.reply_text("❌ Không tìm thấy affiliate.")
    if channel_filter == "all":
        channels = list_social_channels(update.effective_user.id, limit=50)
    else:
        try:
            one = get_social_channel(int(channel_filter), update.effective_user.id)
        except ValueError:
            one = None
        channels = [one] if one else []
    if not channels:
        return await update.message.reply_text("📭 Chưa có channel phù hợp. Tạo bằng /channel_add.")

    created = []
    base_date = datetime.now().date()
    for day_index in range(days):
        for channel in channels:
            cid, platform, name, account, focus, audience, slots, status = channel
            if status != "active":
                continue
            for slot_index in range(slots_per_day(slots)):
                if len(created) >= 80:
                    break
                post_date = (base_date + timedelta(days=day_index)).isoformat()
                topic = content_topic_for_slot(niche, focus, platform, day_index, slot_index)
                note = f"{name} | {account or 'main'} | audience={audience or 'general'}"
                slot_id = create_calendar_slot(
                    update.effective_user.id, cid, campaign_id, affiliate_id, post_date, platform, topic, note
                )
                created.append((slot_id, post_date, platform, name, topic))
    preview = created[:10]
    lines = [
        f"✅ <b>Đã tạo {len(created)} lịch nội dung</b>",
        f"• Số ngày: <b>{days}</b>",
        f"• Channel: <code>{html.escape(channel_filter)}</code>",
        f"• Campaign: <code>{campaign_id or 'chưa gắn'}</code>",
        f"• Affiliate: <code>{affiliate_id or 'chưa gắn'}</code>",
        "",
        "<b>10 lịch đầu:</b>",
    ]
    for slot_id, post_date, platform, name, topic in preview:
        lines.append(f"• #{slot_id} | {post_date} | <code>{html.escape(platform)}</code> | {html.escape(name)} | {html.escape(topic)}")
    lines.append("\nXem tiếp: /calendar")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    rows = list_calendar_slots(update.effective_user.id)
    if not rows:
        return await update.message.reply_text("📭 Chưa có lịch. Tạo bằng /calendar_plan.")
    lines = ["🗓️ <b>LỊCH NỘI DUNG NỘI BỘ</b>\n"]
    for slot_id, post_date, platform, channel_name, topic, status, campaign_id, affiliate_id in rows:
        lines.append(
            f"• #{slot_id} | {post_date} | <code>{html.escape(platform or '-')}</code> | "
            f"{html.escape(channel_name or '-') } | {status}\n"
            f"  {html.escape(topic or '-')}\n"
            f"  camp=<code>{campaign_id or '-'}</code> aff=<code>{affiliate_id or '-'}</code>"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_operator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    topic = data.get("topic") or data.get("chude")
    if not topic:
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/operator topic=review 5 món đồ công nghệ channel=1 aff=1 campaign=1 date=2026-06-01</code>\n"
            "Dùng <code>/channels</code> và <code>/affiliates</code> để lấy ID.",
            parse_mode="HTML"
        )
    try:
        channel_id = int(data.get("channel") or data.get("kenh") or 0)
    except ValueError:
        channel_id = 0
    try:
        affiliate_id = int(data.get("affiliate_id") or data.get("aff") or 0)
    except ValueError:
        affiliate_id = 0
    try:
        campaign_id = int(data.get("campaign") or data.get("camp") or 0)
    except ValueError:
        campaign_id = 0

    if not channel_id:
        return await update.message.reply_text("⚠️ Thiếu <code>channel=&lt;ID&gt;</code>. Xem ID bằng /channels.", parse_mode="HTML")
    channel = get_social_channel(channel_id, update.effective_user.id)
    if not channel:
        return await update.message.reply_text("❌ Không tìm thấy channel hoặc không có quyền.")
    if affiliate_id and not get_affiliate_link(affiliate_id, update.effective_user.id):
        return await update.message.reply_text("❌ Không tìm thấy affiliate hoặc không có quyền.")
    if campaign_id and not get_campaign(campaign_id, update.effective_user.id):
        return await update.message.reply_text("❌ Không tìm thấy campaign hoặc không có quyền.")

    post_date = data.get("date") or data.get("ngay") or datetime.now().date().isoformat()
    note = data.get("note") or "operator_direct"
    _, platform, channel_name, account_label, focus, audience, slots, status = channel
    slot_note = f"{channel_name} | {account_label or 'main'} | audience={audience or 'general'} | {note}"
    slot_id = create_calendar_slot(
        update.effective_user.id,
        channel_id,
        campaign_id,
        affiliate_id,
        post_date,
        platform,
        topic,
        slot_note
    )
    slot = get_calendar_slot(slot_id, update.effective_user.id)
    if gemini_client or openai_client:
        brief = AgentGemini.chat(
            "Bạn là AI Operator trưởng, biến lệnh Telegram của admin thành brief sản xuất video affiliate hợp pháp.",
            build_production_prompt(slot),
            update.effective_user.id,
            is_json=False
        )
    else:
        brief = "Chưa cấu hình AI Provider. Job đã được tạo, admin bổ sung brief thủ công."
    job_id = create_production_job(
        update.effective_user.id,
        slot_id,
        campaign_id,
        channel_id,
        affiliate_id,
        platform or "",
        topic or "",
        brief,
        note
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎙 Voice", callback_data=f"pipe|stage|voice|{job_id}"),
            InlineKeyboardButton("🎞 Edit", callback_data=f"pipe|stage|edit|{job_id}"),
            InlineKeyboardButton("✅ Review", callback_data=f"pipe|stage|review|{job_id}")
        ],
        [
            InlineKeyboardButton("🚀 Published", callback_data=f"pipe|status|published|{job_id}"),
            InlineKeyboardButton("⛔ Blocked", callback_data=f"pipe|status|blocked|{job_id}")
        ]
    ])
    await update.message.reply_text(
        f"🧠 <b>AI OPERATOR ĐÃ NHẬN LỆNH</b>\n\n"
        f"• Calendar slot: <code>#{slot_id}</code>\n"
        f"• Production job: <code>#{job_id}</code>\n"
        f"• Kênh: <b>{html.escape(channel_name or '-')}</b> / <code>{html.escape(account_label or 'main')}</code>\n"
        f"• Nền tảng: <code>{html.escape(platform or '-')}</code>\n"
        f"• Topic: {html.escape(topic)}\n"
        f"• Ngày: <code>{html.escape(post_date)}</code>\n\n"
        f"<pre>{html_pre(brief)}</pre>",
        parse_mode="HTML",
        reply_markup=kb
    )

async def cmd_operator_auto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    niche = data.get("niche") or data.get("ngach") or data.get("topic") or data.get("chude") or "công nghệ AI"
    platform_filter = (data.get("platform") or data.get("nen") or "").lower()
    channel_filter = (data.get("channel") or data.get("kenh") or "all").lower()
    try:
        limit = max(1, min(int(data.get("limit") or data.get("max") or 5), 15))
    except ValueError:
        limit = 5
    try:
        campaign_id = int(data.get("campaign") or data.get("camp") or 0)
    except ValueError:
        campaign_id = 0
    try:
        affiliate_id = int(data.get("affiliate_id") or data.get("aff") or 0)
    except ValueError:
        affiliate_id = 0
    if campaign_id and not get_campaign(campaign_id, update.effective_user.id):
        return await update.message.reply_text("❌ Không tìm thấy campaign.")
    if affiliate_id and not get_affiliate_link(affiliate_id, update.effective_user.id):
        return await update.message.reply_text("❌ Không tìm thấy affiliate.")
    if channel_filter == "all":
        channels = list_social_channels(update.effective_user.id, limit=80)
        if platform_filter:
            channels = [ch for ch in channels if (ch[1] or "").lower() == platform_filter]
    else:
        try:
            one = get_social_channel(int(channel_filter), update.effective_user.id)
        except ValueError:
            one = None
        channels = [one] if one else []
    channels = [ch for ch in channels if ch and ch[7] == "active"]
    if not channels:
        return await update.message.reply_text("📭 Chưa có channel active phù hợp. Tạo bằng /channel_add.")

    msg = await update.message.reply_text("🤖 Operator Auto đang tìm trend và tạo job...")
    search_platform = platform_filter or (channels[0][1] if channels else "tiktok")
    try:
        trends = await fetch_google_news_trends(niche, search_platform, limit=limit)
    except Exception as e:
        await alert_admin(context, "Operator Auto Trend", f"{str(e)} | niche={niche} platform={search_platform}")
        return await msg.edit_text("❌ Operator Auto lỗi khi tìm trend. Đã báo admin.")
    if not trends:
        return await msg.edit_text("📭 Không tìm thấy trend để tạo job.")

    affiliate = get_affiliate_link(affiliate_id, update.effective_user.id) if affiliate_id else None
    primary_channel = channels[0] if channels else None
    scored_trends = []
    for item in trends:
        scores = score_trend_candidate(niche, search_platform, item["title"], item.get("summary", ""), primary_channel, affiliate)
        scored_trends.append((scores["trend_score"], item, scores))
    scored_trends.sort(key=lambda row: row[0], reverse=True)

    created = []
    for _, item, base_scores in scored_trends:
        for channel in channels:
            if len(created) >= limit:
                break
            cid, channel_platform, channel_name, account_label, focus, audience, slots, status = channel
            scores = score_trend_candidate(niche, channel_platform or search_platform, item["title"], item.get("summary", ""), channel, affiliate) or base_scores
            trend_id = save_trend_candidate(
                update.effective_user.id,
                niche,
                channel_platform or search_platform,
                item["title"],
                item["url"],
                item.get("source", ""),
                item.get("summary", ""),
                cid,
                campaign_id,
                affiliate_id,
                scores["trend_score"],
                scores["affiliate_fit_score"],
                scores["competition_score"],
                scores["score_reason"]
            )
            topic = f"{item['title']} | {niche} | affiliate product placement"
            note = (
                f"operator_auto trend #{trend_id} | score={scores['trend_score']} "
                f"aff_fit={scores['affiliate_fit_score']} competition={scores['competition_score']} | "
                f"source={item.get('source','')} | {item['url']}"
            )
            slot_id = create_calendar_slot(
                update.effective_user.id,
                cid,
                campaign_id,
                affiliate_id,
                datetime.now().date().isoformat(),
                channel_platform or search_platform,
                topic,
                note
            )
            slot = get_calendar_slot(slot_id, update.effective_user.id)
            if gemini_client or openai_client:
                brief = AgentGemini.chat(
                    "Bạn là AI Operator trưởng, tạo brief video affiliate từ trend cho pipeline batch.",
                    build_production_prompt(slot) + f"\n\nNguồn trend: {item['url']}\nTóm tắt trend: {item.get('summary','')}",
                    update.effective_user.id,
                    is_json=False
                )
            else:
                brief = f"Trend: {item['title']}\nNguồn: {item['url']}\nTạo video affiliate theo trend này và kiểm duyệt trước khi đăng."
            job_id = create_production_job(
                update.effective_user.id,
                slot_id,
                campaign_id,
                cid,
                affiliate_id,
                channel_platform or search_platform,
                topic,
                brief,
                note
            )
            update_trend_status(trend_id, update.effective_user.id, f"job:{job_id}")
            created.append((job_id, slot_id, trend_id, channel_platform or search_platform, channel_name, item["title"], scores["trend_score"], scores["score_reason"]))
    lines = [
        f"✅ <b>Operator Auto đã tạo {len(created)} production job</b>",
        f"• Niche: <b>{html.escape(niche)}</b>",
        f"• Campaign: <code>{campaign_id or 'chưa gắn'}</code>",
        f"• Affiliate: <code>{affiliate_id or 'chưa gắn'}</code>",
        "",
        "<b>Job mới:</b>",
    ]
    for job_id, slot_id, trend_id, platform, channel_name, title, score, reason in created[:12]:
        lines.append(
            f"• job #{job_id} | slot #{slot_id} | trend #{trend_id} | score=<b>{score}</b> | "
            f"<code>{html.escape(platform or '-')}</code> | {html.escape(channel_name or '-')}\n"
            f"  {html.escape(title)}\n"
            f"  lý do: {html.escape(reason or '-')}"
        )
    lines.append("\nBước tiếp: /operator_dashboard hoặc /operator_next id=<JOB_ID> stage=script")
    await msg.edit_text("\n".join(lines), parse_mode="HTML")

async def cmd_autopilot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    niche = data.get("niche") or data.get("ngach") or data.get("topic") or data.get("chude") or "công nghệ AI"
    platform_filter = (data.get("platform") or data.get("nen") or "").lower()
    channel_filter = (data.get("channel") or data.get("kenh") or "all").lower()
    try:
        limit = max(1, min(int(data.get("limit") or data.get("max") or 3), 8))
    except ValueError:
        limit = 3
    try:
        duration = max(15, min(int(data.get("duration") or data.get("sec") or 45), 120))
    except ValueError:
        duration = 45
    try:
        campaign_id = int(data.get("campaign") or data.get("camp") or 0)
    except ValueError:
        campaign_id = 0
    try:
        affiliate_id = int(data.get("affiliate_id") or data.get("aff") or 0)
    except ValueError:
        affiliate_id = 0

    msg = await update.message.reply_text("🧠 Autopilot đang tìm trend, tạo job và build production bundle...")
    try:
        created_jobs, error = await create_operator_auto_jobs(
            update.effective_user.id,
            niche,
            platform_filter,
            channel_filter,
            campaign_id,
            affiliate_id,
            limit,
        )
    except Exception as e:
        await alert_admin(context, "Autopilot", f"{str(e)} | niche={niche} platform={platform_filter or '-'}")
        return await msg.edit_text("❌ Autopilot lỗi khi tìm trend/tạo job. Đã báo admin.")
    if error:
        return await msg.edit_text(f"❌ {error}")
    if not created_jobs:
        return await msg.edit_text("📭 Autopilot chưa tạo được job nào.")

    built = []
    failed = []
    for item in created_jobs:
        job_id = item["job_id"]
        ok, bundle = build_operator_job_bundle(update.effective_user.id, job_id, count=5, duration=duration)
        if ok:
            readiness = bundle.get("readiness") or {}
            built.append({
                **item,
                "manifest_id": bundle["manifest_id"],
                "task_count": len(bundle["task_ids"]),
                "variant_id": bundle["best_variant_id"],
                "readiness": readiness.get("level", "UNKNOWN") if isinstance(readiness, dict) else "UNKNOWN",
            })
        else:
            failed.append((job_id, bundle.get("error", "build lỗi")))

    lines = [
        "✅ <b>AUTOPILOT BATCH COMPLETE</b>",
        f"• Niche: <b>{html.escape(niche)}</b>",
        f"• Platform filter: <code>{html.escape(platform_filter or 'auto')}</code>",
        f"• Jobs tạo: <b>{len(created_jobs)}</b>",
        f"• Jobs build xong: <b>{len(built)}</b>",
        f"• Jobs lỗi build: <b>{len(failed)}</b>",
        "",
        "<b>Job đã build:</b>",
    ]
    for item in built[:10]:
        lines.append(
            f"• job #{item['job_id']} | trend #{item['trend_id']} | score=<b>{item['score']}</b> | "
            f"<code>{html.escape(item['platform'] or '-')}</code> | {html.escape(item['channel_name'] or '-')}\n"
            f"  variant=#{item['variant_id']} | manifest=#{item['manifest_id']} | tasks={item['task_count']} | ready={html.escape(item['readiness'])}\n"
            f"  {html.escape(item['title'])}"
        )
    if failed:
        lines.append("\n<b>Build lỗi:</b>")
        for job_id, reason in failed[:5]:
            lines.append(f"• job #{job_id}: {html.escape(reason)}")
    lines.append(
        "\nBước tiếp: <code>/tasks job=&lt;JOB_ID&gt;</code>, "
        "<code>/next_task job=&lt;JOB_ID&gt;</code>, hoặc <code>/job_ready job=&lt;JOB_ID&gt;</code>."
    )
    await msg.edit_text("\n".join(lines), parse_mode="HTML")

async def cmd_produce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    if not context.args:
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/produce slot=&lt;calendar_id&gt;</code>\n"
            "Ví dụ: <code>/produce slot=12</code>",
            parse_mode="HTML"
        )
    data = parse_key_value_args(" ".join(context.args))
    try:
        slot_id = int(data.get("slot") or data.get("calendar") or data.get("id") or context.args[0])
    except (TypeError, ValueError):
        return await update.message.reply_text("⚠️ Thiếu <code>slot=&lt;calendar_id&gt;</code>", parse_mode="HTML")
    slot = get_calendar_slot(slot_id, update.effective_user.id)
    if not slot:
        return await update.message.reply_text("❌ Không tìm thấy lịch nội dung hoặc không có quyền.")
    brief = ""
    if gemini_client or openai_client:
        prompt = build_production_prompt(slot)
        brief = AgentGemini.chat(
            "Bạn là AI Operator trưởng, lập lệnh sản xuất video affiliate hợp pháp và có bước kiểm duyệt.",
            prompt,
            update.effective_user.id,
            is_json=False
        )
    else:
        brief = "Chưa cấu hình AI Provider. Job đã được tạo, admin bổ sung brief thủ công ở ghi chú."
    (
        _, _, channel_id, campaign_id, affiliate_id, _, platform, topic, _, notes,
        channel_name, account_label, _, _, network, product_name, affiliate_url, _
    ) = slot
    job_id = create_production_job(
        update.effective_user.id,
        slot_id,
        campaign_id or 0,
        channel_id or 0,
        affiliate_id or 0,
        platform or "",
        topic or "",
        brief,
        notes or ""
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎙 Voice", callback_data=f"pipe|stage|voice|{job_id}"),
            InlineKeyboardButton("🎞 Edit", callback_data=f"pipe|stage|edit|{job_id}"),
            InlineKeyboardButton("✅ Review", callback_data=f"pipe|stage|review|{job_id}")
        ],
        [
            InlineKeyboardButton("🚀 Published", callback_data=f"pipe|status|published|{job_id}"),
            InlineKeyboardButton("⛔ Blocked", callback_data=f"pipe|status|blocked|{job_id}")
        ]
    ])
    await update.message.reply_text(
        f"🎬 <b>PRODUCTION JOB #{job_id}</b>\n"
        f"• Slot: <code>#{slot_id}</code>\n"
        f"• Kênh: <b>{html.escape(channel_name or '-')}</b> / <code>{html.escape(account_label or 'main')}</code>\n"
        f"• Nền tảng: <code>{html.escape(platform or '-')}</code>\n"
        f"• Affiliate: <code>{html.escape((network or '-') + ' / ' + (product_name or '-'))}</code>\n"
        f"• Link: <code>{html.escape(affiliate_url or 'chưa có')}</code>\n"
        f"• Stage: <b>brief</b> | Status: <b>queued</b>\n\n"
        f"<pre>{html_pre(brief)}</pre>",
        parse_mode="HTML",
        reply_markup=kb
    )

async def cmd_pipeline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    if context.args:
        try:
            job_id = int(context.args[0])
        except ValueError:
            job_id = 0
        if job_id:
            job = get_production_job(job_id, update.effective_user.id)
            if not job:
                return await update.message.reply_text("❌ Không tìm thấy production job.")
            (
                jid, calendar_id, campaign_id, channel_id, affiliate_id, platform, topic, stage, status,
                note, brief, asset_url, publish_url, channel_name, account_label, network, product_name, affiliate_url
            ) = job
            return await update.message.reply_text(
                f"🎬 <b>PRODUCTION JOB #{jid}</b>\n"
                f"• Calendar: <code>{calendar_id or '-'}</code> | Campaign: <code>{campaign_id or '-'}</code>\n"
                f"• Channel: <b>{html.escape(channel_name or '-')}</b> / <code>{html.escape(account_label or 'main')}</code>\n"
                f"• Platform: <code>{html.escape(platform or '-')}</code>\n"
                f"• Topic: {html.escape(topic or '-')}\n"
                f"• Stage: <b>{html.escape(stage or '-')}</b> | Status: <b>{html.escape(status or '-')}</b>\n"
                f"• Affiliate: <code>{html.escape(network or '-')} / {html.escape(product_name or '-')}</code>\n"
                f"• Link affiliate: <code>{html.escape(affiliate_url or 'chưa có')}</code>\n"
                f"• Asset: <code>{html.escape(asset_url or 'chưa có')}</code>\n"
                f"• Publish: <code>{html.escape(publish_url or 'chưa có')}</code>\n"
                f"• Note: {html.escape(note or '-')}\n\n"
                f"<pre>{html_pre(brief or 'Chưa có brief')}</pre>",
                parse_mode="HTML"
            )
    rows = list_production_jobs(update.effective_user.id)
    if not rows:
        return await update.message.reply_text("📭 Chưa có production job. Tạo bằng /produce slot=<id>.")
    lines = ["🎛️ <b>PIPELINE VIDEO</b>\n"]
    for jid, stage, status, platform, topic, channel_name, product_name, updated_at in rows:
        lines.append(
            f"• #{jid} | <b>{html.escape(stage or '-')}</b>/{html.escape(status or '-')} | "
            f"<code>{html.escape(platform or '-')}</code> | {html.escape(channel_name or '-')}\n"
            f"  {html.escape(topic or '-')}\n"
            f"  aff={html.escape(product_name or '-')} | {updated_at or '-'}"
        )
    lines.append("\nXem chi tiết: <code>/pipeline &lt;id&gt;</code>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_pipeline_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        job_id = int(data.get("id") or data.get("job") or context.args[0])
    except (IndexError, TypeError, ValueError):
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/pipeline_set id=1 stage=edit status=working asset=https://... publish=https://... note=...</code>",
            parse_mode="HTML"
        )
    stage = data.get("stage")
    status = data.get("status")
    note = data.get("note")
    asset_url = data.get("asset")
    publish_url = data.get("publish")
    allowed_stages = {"brief", "script", "voice", "visuals", "edit", "review", "publish", "done"}
    allowed_status = {"queued", "working", "waiting", "blocked", "ready", "published", "done", "cancelled"}
    if stage and stage not in allowed_stages:
        return await update.message.reply_text(f"⚠️ stage hợp lệ: <code>{', '.join(sorted(allowed_stages))}</code>", parse_mode="HTML")
    if status and status not in allowed_status:
        return await update.message.reply_text(f"⚠️ status hợp lệ: <code>{', '.join(sorted(allowed_status))}</code>", parse_mode="HTML")
    changed = update_production_job(job_id, update.effective_user.id, stage, status, note, asset_url, publish_url)
    if not changed:
        return await update.message.reply_text("❌ Không tìm thấy production job.")
    await update.message.reply_text(
        f"✅ Đã cập nhật pipeline #{job_id}\n"
        f"• stage=<code>{html.escape(stage or 'giữ nguyên')}</code>\n"
        f"• status=<code>{html.escape(status or 'giữ nguyên')}</code>",
        parse_mode="HTML"
    )

async def cmd_operator_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        job_id = int(data.get("id") or data.get("job") or context.args[0])
    except (IndexError, TypeError, ValueError):
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/operator_next id=1 stage=script</code>\n"
            "Stage: <code>script, voice, visuals, edit, review, publish</code>",
            parse_mode="HTML"
        )
    target_stage = (data.get("stage") or data.get("next") or "").lower()
    allowed = ["script", "voice", "visuals", "edit", "review", "publish"]
    job = get_production_job(job_id, update.effective_user.id)
    if not job:
        return await update.message.reply_text("❌ Không tìm thấy production job.")
    current_stage = job[7] or "brief"
    if not target_stage:
        try:
            target_stage = allowed[min(allowed.index(current_stage) + 1, len(allowed) - 1)]
        except ValueError:
            target_stage = "script"
    if target_stage not in allowed:
        return await update.message.reply_text(f"⚠️ stage hợp lệ: <code>{', '.join(allowed)}</code>", parse_mode="HTML")
    if gemini_client or openai_client:
        instruction = AgentGemini.chat(
            "Bạn là AI Operator trưởng điều phối từng stage sản xuất video affiliate.",
            build_operator_stage_prompt(job, target_stage),
            update.effective_user.id,
            is_json=False
        )
    else:
        instruction = (
            "Chưa cấu hình AI Provider. Cập nhật thủ công theo stage: "
            f"{target_stage}. Ưu tiên tool cao cấp trước, lỗi/quota thì fallback và báo admin."
        )
    note = f"operator_next:{target_stage} | {truncate_text(instruction, 800)}"
    update_production_job(job_id, update.effective_user.id, stage=target_stage, status="working", note=note)
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎙 Voice", callback_data=f"pipe|stage|voice|{job_id}"),
            InlineKeyboardButton("🎞 Edit", callback_data=f"pipe|stage|edit|{job_id}"),
            InlineKeyboardButton("✅ Review", callback_data=f"pipe|stage|review|{job_id}")
        ],
        [
            InlineKeyboardButton("🚀 Published", callback_data=f"pipe|status|published|{job_id}"),
            InlineKeyboardButton("⛔ Blocked", callback_data=f"pipe|status|blocked|{job_id}")
        ]
    ])
    await update.message.reply_text(
        f"🧠 <b>OPERATOR NEXT — JOB #{job_id}</b>\n"
        f"Stage: <b>{html.escape(target_stage)}</b> | Status: <b>working</b>\n\n"
        f"<pre>{html_pre(instruction)}</pre>",
        parse_mode="HTML",
        reply_markup=kb
    )

async def cmd_operator_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    active_channels, active_affiliates, calendar_counts, pipeline_counts, active_jobs, upcoming_slots = operator_dashboard_data(update.effective_user.id)
    lines = [
        "🧠 <b>AI OPERATOR DASHBOARD</b>",
        f"• Kênh active: <b>{active_channels}</b>",
        f"• Affiliate active: <b>{active_affiliates}</b>",
        "• Calendar: " + (", ".join(f"{k}={v}" for k, v in calendar_counts.items()) or "0"),
        "• Pipeline: " + (", ".join(f"{stage}/{status}={count}" for stage, status, count in pipeline_counts) or "0"),
        "",
        "<b>Job cần xử lý:</b>",
    ]
    if active_jobs:
        for jid, stage, status, platform, topic, channel_name, product_name, updated_at in active_jobs:
            lines.append(
                f"• #{jid} | <b>{html.escape(stage or '-')}</b>/{html.escape(status or '-')} | "
                f"<code>{html.escape(platform or '-')}</code> | {html.escape(channel_name or '-')}\n"
                f"  {html.escape(topic or '-')}\n"
                f"  aff={html.escape(product_name or '-')} | {updated_at or '-'}"
            )
    else:
        lines.append("• Không có job đang chờ.")
    lines.append("\n<b>Lịch sắp tới:</b>")
    if upcoming_slots:
        for slot_id, post_date, platform, channel_name, topic, status, campaign_id, affiliate_id in upcoming_slots:
            lines.append(
                f"• slot #{slot_id} | {post_date} | <code>{html.escape(platform or '-')}</code> | "
                f"{html.escape(channel_name or '-')} | {status}\n"
                f"  {html.escape(topic or '-')}"
            )
    else:
        lines.append("• Chưa có lịch. Dùng /calendar_plan hoặc /operator.")
    lines.append(
        "\nLệnh nhanh: <code>/operator topic=... channel=... aff=...</code> | "
        "<code>/operator_next id=... stage=script</code>"
    )
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_operator_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        days = int(data.get("days") or data.get("ngay") or (context.args[0] if context.args else 1))
    except (TypeError, ValueError):
        days = 1
    days = max(1, min(days, 30))
    (
        since, job_status_counts, job_stage_counts, queue_status_counts,
        performance_counts, recent_jobs, open_queue
    ) = operator_daily_data(update.effective_user.id, days)
    lines = [
        f"📊 <b>AI OPERATOR DAILY — {days} ngày</b>",
        f"• Từ: <code>{html.escape(since)}</code>",
        "",
        "<b>Job mới theo status:</b>",
        "• " + (", ".join(f"{html.escape(status or '-')}={count}" for status, count in job_status_counts) or "0"),
        "<b>Job cập nhật theo stage:</b>",
        "• " + (", ".join(f"{html.escape(stage or '-')}={count}" for stage, count in job_stage_counts) or "0"),
        "<b>Publish queue:</b>",
        "• " + (", ".join(f"{html.escape(status or '-')}={count}" for status, count in queue_status_counts) or "0"),
        "",
        "<b>Performance:</b>",
    ]
    if performance_counts:
        for event_type, value_sum, amount_sum, count in performance_counts:
            lines.append(f"• {html.escape(event_type or '-')}: value=<b>{value_sum}</b> | amount=<b>{amount_sum:,}đ</b> | events={count}")
    else:
        lines.append("• Chưa có dữ liệu mới.")
    lines.append("\n<b>Job vừa cập nhật:</b>")
    if recent_jobs:
        for jid, stage, status, platform, topic, channel_name, product_name, updated_at in recent_jobs:
            lines.append(
                f"• #{jid} | {html.escape(stage or '-')}/{html.escape(status or '-')} | "
                f"<code>{html.escape(platform or '-')}</code> | {html.escape(channel_name or '-')}\n"
                f"  {html.escape(topic or '-')}\n"
                f"  aff={html.escape(product_name or '-')} | {updated_at or '-'}"
            )
    else:
        lines.append("• Không có job cập nhật.")
    lines.append("\n<b>Queue cần xử lý:</b>")
    if open_queue:
        for qid, job_id, platform, channel_name, mode, status, scheduled_at, topic in open_queue:
            lines.append(
                f"• queue #{qid} | job #{job_id} | {html.escape(mode or '-')}/{html.escape(status or '-')} | "
                f"<code>{html.escape(platform or '-')}</code> | {html.escape(channel_name or '-')}\n"
                f"  schedule={html.escape(scheduled_at or '-')} | {html.escape(topic or '-')}"
            )
    else:
        lines.append("• Không có queue mở.")
    lines.append("\nLệnh nhanh: /operator_dashboard | /publish_queue | /performance | /operator_auto")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

def operator_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧠 Brain command", callback_data="opmenu|brain")],
        [InlineKeyboardButton("🚀 Autopilot batch", callback_data="opmenu|autopilot")],
        [InlineKeyboardButton("⚡ Operator build", callback_data="opmenu|build")],
        [
            InlineKeyboardButton("🧭 Dashboard", callback_data="opmenu|dashboard"),
            InlineKeyboardButton("🔥 Tìm trend", callback_data="opmenu|trend")
        ],
        [InlineKeyboardButton("🏆 Trend ranking", callback_data="opmenu|rank")],
        [
            InlineKeyboardButton("🤖 Auto batch", callback_data="opmenu|auto"),
            InlineKeyboardButton("🧪 Auto-post ready", callback_data="opmenu|readiness")
        ],
        [
            InlineKeyboardButton("🎯 Affiliate match", callback_data="opmenu|affmatch"),
            InlineKeyboardButton("🛒 Affiliate profile", callback_data="opmenu|affprofile")
        ],
        [
            InlineKeyboardButton("🎛 Pipeline", callback_data="opmenu|pipeline"),
            InlineKeyboardButton("📅 Calendar", callback_data="opmenu|calendar")
        ],
        [
            InlineKeyboardButton("📦 Publish pack", callback_data="opmenu|publish"),
            InlineKeyboardButton("🛡 Review gate", callback_data="opmenu|review")
        ],
        [
            InlineKeyboardButton("🧪 Creative test", callback_data="opmenu|creative"),
            InlineKeyboardButton("🏁 Creative report", callback_data="opmenu|creativereport")
        ],
        [
            InlineKeyboardButton("🗂 Assets", callback_data="opmenu|assets"),
            InlineKeyboardButton("📋 Job report", callback_data="opmenu|report")
        ],
        [InlineKeyboardButton("🚦 Job ready check", callback_data="opmenu|jobready")],
        [
            InlineKeyboardButton("🎬 Production manifest", callback_data="opmenu|manifest"),
            InlineKeyboardButton("🤝 Manifest handoff", callback_data="opmenu|manifesthandoff")
        ],
        [InlineKeyboardButton("✅ Production tasks", callback_data="opmenu|tasks")],
        [InlineKeyboardButton("➡️ Next task", callback_data="opmenu|nexttask")],
        [InlineKeyboardButton("📮 Publish queue", callback_data="opmenu|publishqueue")],
        [
            InlineKeyboardButton("🤝 Handoff AI", callback_data="opmenu|handoff"),
            InlineKeyboardButton("💰 Performance", callback_data="opmenu|performance")
        ],
        [InlineKeyboardButton("📈 Growth optimizer", callback_data="opmenu|growth")],
        [InlineKeyboardButton("🔁 Operator loop", callback_data="opmenu|loop")],
        [InlineKeyboardButton("📊 Daily digest", callback_data="opmenu|daily")],
    ])

async def cmd_operator_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    text = (
        "🧠 <b>AI OPERATOR MENU</b>\n\n"
        "Quy trình chuẩn:\n"
        "1. Tìm trend hoặc tạo lệnh trực tiếp.\n"
        "2. Tạo production job và handoff cho AI/tool.\n"
        "3. Review gate trước khi đăng.\n"
        "4. Publish pack, đăng thủ công/API chính thức.\n"
        "5. Mark published và ghi performance.\n\n"
        "Chọn nút bên dưới để lấy lệnh nhanh."
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=operator_menu_keyboard())

async def handle_operator_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if str(query.from_user.id) != ADMIN_ID:
        return await query.answer("Chỉ Admin được dùng.", show_alert=True)
    action = query.data.split("|", 1)[1]
    snippets = {
        "dashboard": "/operator_dashboard",
        "brain": "/brain tạo 5 video trend công nghệ AI cho tiktok aff=<AFF_ID> campaign=<ID>",
        "autopilot": "/autopilot niche=công nghệ AI platform=tiktok channel=all aff=<AFF_ID> campaign=<ID> limit=3 duration=45",
        "build": "/operator_build job=<JOB_ID> n=5 duration=45",
        "trend": "/trend_search niche=công nghệ AI platform=tiktok channel=<ID> aff=<ID> campaign=<ID>",
        "auto": "/operator_auto niche=công nghệ AI platform=tiktok channel=all aff=<ID> campaign=<ID> limit=5",
        "rank": "/trend_rank\n/trend_rank 20",
        "affmatch": "/affiliate_match niche=công nghệ AI platform=tiktok trend=AI agent creator",
        "affprofile": "/affiliate_profile id=<AFF_ID> price=199000 rate=8 audience=creator allowed=... blocked=... score=70",
        "pipeline": "/pipeline\n/pipeline <JOB_ID>",
        "calendar": "/calendar\n/calendar_plan days=7 channel=all campaign=<ID> aff=<ID> niche=công nghệ",
        "publish": "/publish_pack job=<JOB_ID>\n/queue_publish job=<JOB_ID> mode=manual\n/mark_published job=<JOB_ID> url=https://... views=0 clicks=0 note=...",
        "readiness": "/publish_readiness\n/channel_publish_set id=<CHANNEL_ID> mode=api token_env=TIKTOK_ACCESS_TOKEN",
        "publishqueue": "/publish_queue\n/publish_queue_set id=<QUEUE_ID> status=published url=https://...",
        "creative": "/creative_test job=<JOB_ID> n=5\n/creative_variants <JOB_ID>\n/creative_select id=<VARIANT_ID>",
        "creativereport": "/creative_report job=<JOB_ID>\n/performance_add job=<JOB_ID> variant=<VARIANT_ID> type=click value=1",
        "manifest": "/manifest job=<JOB_ID> duration=45\n/manifests <JOB_ID>",
        "manifesthandoff": "/manifest_handoff job=<JOB_ID> tool=kling\n/manifest_handoff manifest=<MANIFEST_ID> tool=capcut",
        "tasks": "/task_plan job=<JOB_ID>\n/tasks job=<JOB_ID>\n/task_set id=<TASK_ID> status=ready url=https://...",
        "nexttask": "/next_task\n/next_task job=<JOB_ID>",
        "assets": "/asset_add job=<JOB_ID> type=final_video url=https://... note=...\n/assets <JOB_ID>",
        "report": "/job_report <JOB_ID>",
        "jobready": "/job_ready job=<JOB_ID>",
        "review": "/review_gate job=<JOB_ID>",
        "handoff": "/handoff job=<JOB_ID> tool=claude stage=script",
        "performance": "/performance\n/performance_add job=<JOB_ID> type=revenue value=1 amount=... note=...",
        "growth": "/growth\n/growth days=30",
        "loop": "/operator_loop\n/operator_loop limit=10 queue=1",
        "daily": "/operator_daily\n/operator_daily days=7",
    }
    await query.edit_message_text(
        f"🧠 <b>AI OPERATOR MENU</b>\n\n"
        f"Lệnh nhanh:\n<pre>{html.escape(snippets.get(action, '/operator_dashboard'))}</pre>",
        parse_mode="HTML",
        reply_markup=operator_menu_keyboard()
    )

async def cmd_brain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    raw_text = " ".join(context.args).strip()
    if not raw_text:
        return await update.message.reply_text(
            "🧠 <b>AI BRAIN</b>\n\n"
            "Gõ lệnh tự nhiên để bot tự định tuyến vào AI Operator.\n\n"
            "Ví dụ:\n"
            "• <code>/brain autopilot 3 video trend công nghệ AI cho tiktok aff 2 campaign 1</code>\n"
            "• <code>/brain tạo 5 video trend công nghệ AI cho tiktok aff 2 campaign 1</code>\n"
            "• <code>/brain build job 12 duration 45</code>\n"
            "• <code>/brain kiểm tra job 12 đã đủ đăng chưa</code>\n"
            "• <code>/brain báo cáo vận hành 7 ngày</code>",
            parse_mode="HTML"
        )
    plan = parse_operator_brain(raw_text, update.effective_user.id)
    command_preview = brain_command_preview(plan)
    safety_note = plan.get("safety_note") or "Giữ review gate trước khi đăng; không mạo danh/deepfake/claim affiliate quá mức."
    await update.message.reply_text(
        "🧠 <b>AI BRAIN ĐÃ HIỂU LỆNH</b>\n\n"
        f"• Intent: <code>{html.escape(str(plan.get('intent') or 'help'))}</code>\n"
        f"• Confidence: <b>{int(plan.get('confidence') or 0)}</b>\n"
        f"• Lệnh nội bộ:\n<code>{html.escape(command_preview)}</code>\n"
        f"• Safety: {html.escape(str(safety_note))}\n\n"
        "Đang thực thi nếu đủ tham số...",
        parse_mode="HTML"
    )
    await run_brain_plan(update, context, plan)

async def cmd_operator_build(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        job_id = int(data.get("job") or data.get("id") or context.args[0])
    except (IndexError, TypeError, ValueError):
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/operator_build job=1 n=5 duration=45</code>",
            parse_mode="HTML"
        )
    try:
        count = max(2, min(int(data.get("n") or data.get("count") or 5), 8))
    except ValueError:
        count = 5
    try:
        duration = max(15, min(int(data.get("duration") or data.get("sec") or 45), 120))
    except ValueError:
        duration = 45
    job = get_production_job(job_id, update.effective_user.id)
    if not job:
        return await update.message.reply_text("❌ Không tìm thấy production job.")

    msg = await update.message.reply_text("🧠 Operator Build đang tạo creative, manifest và task plan...")
    ok, bundle = build_operator_job_bundle(update.effective_user.id, job_id, count, duration)
    if not ok:
        return await msg.edit_text(f"❌ {bundle.get('error', 'Operator Build lỗi.')}")
    created_variants = bundle["created_variants"]
    best_variant_id = bundle["best_variant_id"]
    best_variant = bundle["best_variant"]
    manifest_id = bundle["manifest_id"]
    manifest = bundle["manifest"]
    task_ids = bundle["task_ids"]
    scenes = manifest.get("scenes") or []
    lines = [
        "✅ <b>OPERATOR BUILD COMPLETE</b>",
        f"• Job: <code>#{job_id}</code>",
        f"• Creative variants: <b>{len(created_variants)}</b>",
        f"• Selected variant: <code>#{best_variant_id}</code> | score=<b>{best_variant.get('creative_score', 0)}</b>",
        f"• Manifest: <code>#{manifest_id}</code>",
        f"• Scenes: <b>{len(scenes)}</b>",
        f"• Production tasks: <b>{len(task_ids)}</b>",
        "",
        "<b>Task preview:</b>",
    ]
    rows = list_production_tasks(update.effective_user.id, job_id=job_id, manifest_id=manifest_id, limit=12)
    for tid, _job_id, mid, task_type, tool, scene_no, title, status, output_url, note, updated_at in rows:
        lines.append(
            f"• task #{tid} | {html.escape(task_type or '-')} | tool=<code>{html.escape(tool or '-')}</code> | "
            f"scene={scene_no or '-'} | {html.escape(status or '-')}\n"
            f"  {html.escape(title or '-')}"
        )
    lines.append(
        "\nBước tiếp: <code>/task_handoff id=&lt;TASK_ID&gt;</code> để giao từng việc, "
        "hoặc <code>/manifest_handoff manifest=%s tool=kling</code> để giao theo tool." % manifest_id
    )
    await msg.edit_text("\n".join(lines), parse_mode="HTML")

async def cmd_creative_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        job_id = int(data.get("job") or data.get("id") or context.args[0])
    except (IndexError, TypeError, ValueError):
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/creative_test job=1 n=5</code>",
            parse_mode="HTML"
        )
    try:
        count = max(2, min(int(data.get("n") or data.get("count") or 5), 8))
    except ValueError:
        count = 5
    job = get_production_job(job_id, update.effective_user.id)
    if not job:
        return await update.message.reply_text("❌ Không tìm thấy production job.")
    created = create_creative_variants_for_job(update.effective_user.id, job, count)
    if not created:
        return await update.message.reply_text("❌ Không tạo được creative variant.")
    update_production_job(job_id, update.effective_user.id, stage="script", status="working", note=f"creative_test created={len(created)}")
    lines = [f"🧪 <b>CREATIVE TEST — JOB #{job_id}</b>", f"Đã tạo <b>{len(created)}</b> biến thể hook/caption/CTA.\n"]
    buttons = []
    for variant_id, item in created:
        lines.append(
            f"• variant #{variant_id} | <b>{html.escape(item['variant_label'])}</b> | score=<b>{item['creative_score']}</b>\n"
            f"  Hook: {html.escape(item['hook'])}\n"
            f"  CTA: {html.escape(item['cta'])}"
        )
        buttons.append([InlineKeyboardButton(f"✅ Chọn variant #{variant_id}", callback_data=f"creative|select|{variant_id}")])
    lines.append("\nSau khi đăng/test: <code>/performance_add job=%s variant=&lt;ID&gt; type=click value=...</code>" % job_id)
    await update.message.reply_text("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))

async def cmd_creative_variants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    try:
        job_id = int(context.args[0])
    except (IndexError, ValueError):
        return await update.message.reply_text("⚠️ Cú pháp: <code>/creative_variants &lt;JOB_ID&gt;</code>", parse_mode="HTML")
    rows = list_creative_variants(update.effective_user.id, job_id)
    if not rows:
        return await update.message.reply_text(f"📭 Job #{job_id} chưa có creative variant. Dùng /creative_test job={job_id}.")
    lines = [f"🧪 <b>CREATIVE VARIANTS — JOB #{job_id}</b>\n"]
    buttons = []
    for vid, label, hook, angle, caption, cta, hashtags, score, status, note, created_at, selected_at in rows:
        lines.append(
            f"• #{vid} | <b>{html.escape(label or '-')}</b> | score=<b>{score or 0}</b> | {html.escape(status or '-')}\n"
            f"  Hook: {html.escape(hook or '-')}\n"
            f"  Angle: {html.escape(angle or '-')}\n"
            f"  Caption: {html.escape(caption or '-')}\n"
            f"  CTA: {html.escape(cta or '-')}\n"
            f"  Hashtags: <code>{html.escape(hashtags or '-')}</code>"
        )
        buttons.append([InlineKeyboardButton(f"✅ Chọn variant #{vid}", callback_data=f"creative|select|{vid}")])
    await update.message.reply_text("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))

async def cmd_creative_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        variant_id = int(data.get("id") or data.get("variant") or context.args[0])
    except (IndexError, TypeError, ValueError):
        return await update.message.reply_text("⚠️ Cú pháp: <code>/creative_select id=&lt;VARIANT_ID&gt;</code>", parse_mode="HTML")
    ok, variant = select_creative_variant(update.effective_user.id, variant_id)
    if not ok:
        return await update.message.reply_text("❌ Không tìm thấy creative variant.")
    _, job_id, label, hook, angle, caption, cta, hashtags, score, status, note = variant
    await update.message.reply_text(
        f"✅ <b>Đã chọn creative variant #{variant_id} cho job #{job_id}</b>\n"
        f"• Label: <b>{html.escape(label or '-')}</b> | Score: <b>{score or 0}</b>\n"
        f"• Hook: {html.escape(hook or '-')}\n"
        f"• Caption: {html.escape(caption or '-')}\n"
        f"• CTA: {html.escape(cta or '-')}\n\n"
        f"Bước tiếp: <code>/handoff job={job_id} tool=claude stage=script</code> hoặc <code>/publish_pack job={job_id}</code>",
        parse_mode="HTML"
    )

async def cmd_creative_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        job_id = int(data.get("job") or data.get("id") or context.args[0])
    except (IndexError, TypeError, ValueError):
        return await update.message.reply_text("⚠️ Cú pháp: <code>/creative_report job=&lt;JOB_ID&gt;</code>", parse_mode="HTML")
    if not get_production_job(job_id, update.effective_user.id):
        return await update.message.reply_text("❌ Không tìm thấy production job.")
    variants, events = creative_report_data(update.effective_user.id, job_id)
    if not variants:
        return await update.message.reply_text(f"📭 Job #{job_id} chưa có creative variant.")
    by_variant = {}
    for variant_id, event_type, value_sum, amount_sum, count in events:
        bucket = by_variant.setdefault(variant_id, {"value": 0, "amount": 0, "events": 0, "types": []})
        bucket["value"] += int(value_sum or 0)
        bucket["amount"] += int(amount_sum or 0)
        bucket["events"] += int(count or 0)
        bucket["types"].append(f"{event_type}:v{value_sum}/đ{amount_sum:,}")
    ranked = []
    for row in variants:
        vid, label, hook, angle, caption, cta, hashtags, score, status, note, created_at, selected_at = row
        perf = by_variant.get(vid, {"value": 0, "amount": 0, "events": 0, "types": []})
        rank_score = int(perf["amount"] or 0) + int(perf["value"] or 0) * 10 + int(score or 0)
        ranked.append((rank_score, row, perf))
    ranked.sort(key=lambda item: item[0], reverse=True)
    lines = [f"🏁 <b>CREATIVE REPORT — JOB #{job_id}</b>", "Biến thể thắng dựa trên revenue/order/click/view đã ghi.\n"]
    for rank_score, row, perf in ranked:
        vid, label, hook, angle, caption, cta, hashtags, score, status, note, created_at, selected_at = row
        lines.append(
            f"• #{vid} | <b>{html.escape(label or '-')}</b> | rank=<b>{rank_score}</b> | creative=<b>{score or 0}</b> | {html.escape(status or '-')}\n"
            f"  perf: value={perf['value']} amount={perf['amount']:,}đ events={perf['events']}\n"
            f"  {html.escape(', '.join(perf['types']) or 'chưa có performance')}\n"
            f"  Hook: {html.escape(hook or '-')}"
        )
    lines.append("\nGhi dữ liệu: <code>/performance_add job=%s variant=&lt;ID&gt; type=click value=...</code>" % job_id)
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def handle_creative_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if str(query.from_user.id) != ADMIN_ID:
        return await query.answer("Chỉ Admin được dùng.", show_alert=True)
    parts = query.data.split("|")
    if len(parts) != 3 or parts[1] != "select":
        return
    try:
        variant_id = int(parts[2])
    except ValueError:
        return
    ok, variant = select_creative_variant(query.from_user.id, variant_id)
    if not ok:
        return await query.edit_message_text("❌ Không tìm thấy creative variant.")
    _, job_id, label, hook, angle, caption, cta, hashtags, score, status, note = variant
    await query.edit_message_text(
        f"✅ Đã chọn creative variant #{variant_id} cho job #{job_id}\n"
        f"Hook: {html.escape(hook or '-')}\n"
        f"CTA: {html.escape(cta or '-')}\n\n"
        f"Tiếp theo: /handoff job={job_id} tool=claude stage=script",
        parse_mode="HTML"
    )

async def handle_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if str(query.from_user.id) != ADMIN_ID:
        return await query.answer("Chỉ Admin được dùng.", show_alert=True)
    parts = query.data.split("|")
    if len(parts) != 4:
        return
    _, action, value, task_id_raw = parts
    try:
        task_id = int(task_id_raw)
    except ValueError:
        return
    task = get_production_task(query.from_user.id, task_id)
    if not task:
        return await query.edit_message_text("❌ Không tìm thấy production task.")
    if action == "status":
        if value not in {"queued", "working", "waiting", "ready", "blocked", "done", "cancelled"}:
            return
        update_production_task(query.from_user.id, task_id, status=value)
        return await query.edit_message_text(
            f"✅ Task #{task_id} đã cập nhật status=<b>{html.escape(value)}</b>\n"
            f"Xem tiếp: /next_task job={task[1]}",
            parse_mode="HTML"
        )
    if action == "handoff":
        tid, job_id, manifest_id, task_type, tool, scene_no, title, prompt, status, output_url, note, updated_at = task
        update_production_task(query.from_user.id, task_id, status="working", note=note or "handoff_started")
        return await query.edit_message_text(
            f"🤝 <b>TASK HANDOFF #{tid}</b>\n"
            f"Tool: <b>{html.escape(tool or '-')}</b> | Type: <code>{html.escape(task_type or '-')}</code>\n\n"
            f"<pre>{html_pre(prompt or '-')}</pre>\n\n"
            f"Khi có output: <code>/task_set id={tid} status=ready url=https://...</code>",
            parse_mode="HTML"
        )

async def cmd_performance_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        job_id = int(data.get("id") or data.get("job") or context.args[0])
    except (IndexError, TypeError, ValueError):
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/performance_add job=1 variant=2 type=view value=1000 amount=0 note=tiktok ngay 1</code>\n"
            "Type: <code>view, click, order, revenue, lead</code>",
            parse_mode="HTML"
        )
    event_type = (data.get("type") or data.get("event") or "view").lower()
    allowed = {"view", "click", "order", "revenue", "lead"}
    if event_type not in allowed:
        return await update.message.reply_text(f"⚠️ type hợp lệ: <code>{', '.join(sorted(allowed))}</code>", parse_mode="HTML")
    try:
        value = int(data.get("value") or data.get("count") or 0)
    except ValueError:
        value = 0
    try:
        amount = int(data.get("amount") or data.get("money") or data.get("vnd") or 0)
    except ValueError:
        amount = 0
    try:
        variant_id = int(data.get("variant") or data.get("variant_id") or 0)
    except ValueError:
        variant_id = 0
    note = data.get("note") or ""
    ok, job = add_performance_event(update.effective_user.id, job_id, event_type, value, amount, note, variant_id)
    if not ok:
        return await update.message.reply_text("❌ Không tìm thấy production job hoặc creative variant.")
    if event_type in {"revenue", "order", "lead"} and amount > 0:
        update_production_job(job_id, update.effective_user.id, status="published")
    await update.message.reply_text(
        f"✅ <b>Đã ghi hiệu quả job #{job_id}</b>\n"
        f"• Type: <code>{html.escape(event_type)}</code>\n"
        f"• Variant: <code>{variant_id or 'không gắn'}</code>\n"
        f"• Value: <b>{value}</b>\n"
        f"• Amount: <b>{amount:,}đ</b>\n"
        f"• Note: {html.escape(note or '-')}",
        parse_mode="HTML"
    )

async def cmd_mark_published(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        job_id = int(data.get("id") or data.get("job") or context.args[0])
    except (IndexError, TypeError, ValueError):
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/mark_published job=1 url=https://... views=0 clicks=0 note=...</code>",
            parse_mode="HTML"
        )
    publish_url = data.get("url") or data.get("publish") or ""
    note = data.get("note") or "manual_publish"
    try:
        views = int(data.get("views") or data.get("view") or 0)
    except ValueError:
        views = 0
    try:
        clicks = int(data.get("clicks") or data.get("click") or 0)
    except ValueError:
        clicks = 0
    if not get_production_job(job_id, update.effective_user.id):
        return await update.message.reply_text("❌ Không tìm thấy production job.")
    update_production_job(
        job_id,
        update.effective_user.id,
        stage="done",
        status="published",
        note=note,
        publish_url=publish_url
    )
    add_performance_event(update.effective_user.id, job_id, "publish", 1, 0, note)
    if views > 0:
        add_performance_event(update.effective_user.id, job_id, "view", views, 0, "initial_views")
    if clicks > 0:
        add_performance_event(update.effective_user.id, job_id, "click", clicks, 0, "initial_clicks")
    await update.message.reply_text(
        f"✅ <b>Đã ghi nhận job #{job_id} đã đăng</b>\n"
        f"• Publish URL: <code>{html.escape(publish_url or 'chưa nhập')}</code>\n"
        f"• Views ban đầu: <b>{views}</b>\n"
        f"• Clicks ban đầu: <b>{clicks}</b>\n"
        f"• Note: {html.escape(note)}\n\n"
        f"Cập nhật doanh thu sau: <code>/performance_add job={job_id} type=revenue value=1 amount=...</code>",
        parse_mode="HTML"
    )

async def cmd_queue_publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        job_id = int(data.get("id") or data.get("job") or context.args[0])
    except (IndexError, TypeError, ValueError):
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/queue_publish job=1 mode=manual schedule=2026-06-01 note=...</code>",
            parse_mode="HTML"
        )
    mode = (data.get("mode") or "manual").lower()
    if mode not in {"manual", "api"}:
        return await update.message.reply_text("⚠️ mode hợp lệ: <code>manual</code> hoặc <code>api</code>", parse_mode="HTML")
    scheduled_at = data.get("schedule") or data.get("time") or ""
    note = data.get("note") or ""
    ok, queue_id = create_publish_queue_item(update.effective_user.id, job_id, mode, scheduled_at, note)
    if not ok:
        return await update.message.reply_text("❌ Không tìm thấy production job.")
    await update.message.reply_text(
        f"✅ <b>Đã đưa job #{job_id} vào hàng đợi đăng</b>\n"
        f"• Queue ID: <code>{queue_id}</code>\n"
        f"• Mode: <code>{mode}</code>\n"
        f"• Schedule: <code>{html.escape(scheduled_at or 'chưa hẹn')}</code>\n\n"
        f"Khi đăng xong: <code>/mark_published job={job_id} url=https://...</code>",
        parse_mode="HTML"
    )

async def cmd_asset_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        job_id = int(data.get("job") or data.get("id") or context.args[0])
    except (IndexError, TypeError, ValueError):
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/asset_add job=1 type=final_video url=https://... note=...</code>\n"
            "Type gợi ý: script, voice, raw_video, subtitle, thumbnail, final_video, source.",
            parse_mode="HTML"
        )
    asset_type = (data.get("type") or data.get("asset_type") or "source").lower()
    url = data.get("url") or data.get("link") or ""
    file_id = data.get("file_id") or ""
    note = data.get("note") or ""
    if not url and not file_id:
        return await update.message.reply_text("⚠️ Cần <code>url=...</code> hoặc <code>file_id=...</code>", parse_mode="HTML")
    ok, asset_id = add_production_asset(update.effective_user.id, job_id, asset_type, url, file_id, note)
    if not ok:
        return await update.message.reply_text("❌ Không tìm thấy production job.")
    await update.message.reply_text(
        f"✅ <b>Đã lưu asset #{asset_id} cho job #{job_id}</b>\n"
        f"• Type: <code>{html.escape(asset_type)}</code>\n"
        f"• URL: <code>{html.escape(url or '-')}</code>\n"
        f"• File ID: <code>{html.escape(file_id or '-')}</code>\n"
        f"• Note: {html.escape(note or '-')}",
        parse_mode="HTML"
    )

async def cmd_assets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    try:
        job_id = int(context.args[0])
    except (IndexError, ValueError):
        return await update.message.reply_text("⚠️ Cú pháp: <code>/assets &lt;JOB_ID&gt;</code>", parse_mode="HTML")
    if not get_production_job(job_id, update.effective_user.id):
        return await update.message.reply_text("❌ Không tìm thấy production job.")
    rows = list_production_assets(update.effective_user.id, job_id)
    if not rows:
        return await update.message.reply_text(f"📭 Job #{job_id} chưa có asset. Thêm bằng /asset_add.")
    lines = [f"🗂️ <b>ASSETS — JOB #{job_id}</b>\n"]
    for aid, asset_type, url, file_id, note, created_at in rows:
        lines.append(
            f"• #{aid} | <code>{html.escape(asset_type or '-')}</code> | {created_at}\n"
            f"  url=<code>{html.escape(url or '-')}</code>\n"
            f"  file_id=<code>{html.escape(file_id or '-')}</code>\n"
            f"  note={html.escape(note or '-')}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_manifest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        job_id = int(data.get("job") or data.get("id") or context.args[0])
    except (IndexError, TypeError, ValueError):
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/manifest job=1 duration=45 variant=&lt;ID&gt;</code>",
            parse_mode="HTML"
        )
    try:
        duration = max(15, min(int(data.get("duration") or data.get("sec") or 45), 120))
    except ValueError:
        duration = 45
    job = get_production_job(job_id, update.effective_user.id)
    if not job:
        return await update.message.reply_text("❌ Không tìm thấy production job.")
    try:
        variant_id = int(data.get("variant") or data.get("variant_id") or 0)
    except ValueError:
        variant_id = 0
    variant = get_creative_variant(update.effective_user.id, variant_id) if variant_id else selected_creative_variant(update.effective_user.id, job_id)
    if variant and int(variant[1]) != int(job_id):
        return await update.message.reply_text("❌ Creative variant không thuộc job này.")
    ok, manifest_id, manifest = create_manifest_for_job(update.effective_user.id, job, variant, duration)
    if not ok:
        return await update.message.reply_text("❌ Không lưu được manifest.")
    scenes = manifest.get("scenes") or []
    title = manifest.get("title") or job[6] or "-"
    lines = [
        f"🎬 <b>PRODUCTION MANIFEST #{manifest_id}</b>",
        f"• Job: <code>#{job_id}</code>",
        f"• Variant: <code>{variant[0] if variant else 'chưa chọn'}</code>",
        f"• Title: {html.escape(str(title))}",
        f"• Duration: <b>{manifest.get('duration_sec', duration)}s</b> | Format: <b>{html.escape(str(manifest.get('format', '9:16')))}</b>",
        f"• Scenes: <b>{len(scenes)}</b>",
        "",
        "<b>Scene preview:</b>",
    ]
    for scene in scenes[:5]:
        lines.append(
            f"• {scene.get('scene','?')} | {scene.get('start','?')}-{scene.get('end','?')}s | {html.escape(str(scene.get('goal','-')))}\n"
            f"  {html.escape(str(scene.get('on_screen_text') or scene.get('voice_line') or '-'))}"
        )
    lines.append("\nXem JSON đầy đủ: <code>/manifests %s</code>" % job_id)
    lines.append("Handoff tiếp: <code>/handoff job=%s tool=kling stage=visuals</code> hoặc <code>/handoff job=%s tool=capcut stage=edit</code>" % (job_id, job_id))
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_manifests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    try:
        job_id = int(context.args[0])
    except (IndexError, ValueError):
        return await update.message.reply_text("⚠️ Cú pháp: <code>/manifests &lt;JOB_ID&gt;</code>", parse_mode="HTML")
    rows = list_production_manifests(update.effective_user.id, job_id)
    if not rows:
        return await update.message.reply_text(f"📭 Job #{job_id} chưa có manifest. Dùng /manifest job={job_id}.")
    lines = [f"🎬 <b>MANIFESTS — JOB #{job_id}</b>\n"]
    for mid, variant_id, status, manifest_json, created_at, updated_at in rows:
        try:
            manifest = json.loads(manifest_json or "{}")
        except Exception:
            manifest = {}
        scenes = manifest.get("scenes") or []
        voice = manifest.get("voice") or {}
        publish = manifest.get("publish") or {}
        lines.append(
            f"• manifest #{mid} | variant={variant_id or '-'} | {html.escape(status or '-')}\n"
            f"  title={html.escape(str(manifest.get('title') or '-'))}\n"
            f"  scenes={len(scenes)} | voice={html.escape(str(voice.get('provider_primary') or '-'))}\n"
            f"  cta={html.escape(str(publish.get('cta') or '-'))}\n"
            f"  updated={updated_at or created_at or '-'}"
        )
        if scenes:
            first = scenes[0]
            lines.append(f"  first_scene={html.escape(str(first.get('visual_prompt') or first.get('voice_line') or '-'))[:400]}")
    lines.append("\nTạo lại manifest: <code>/manifest job=%s duration=45</code>" % job_id)
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_manifest_handoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    target_tool = (data.get("tool") or data.get("ai") or "kling").lower()
    manifest_row = None
    job = None
    try:
        manifest_id = int(data.get("manifest") or data.get("mid") or 0)
    except ValueError:
        manifest_id = 0
    if manifest_id:
        manifest_row = get_production_manifest(update.effective_user.id, manifest_id)
        if not manifest_row:
            return await update.message.reply_text("❌ Không tìm thấy manifest.")
        job = get_production_job(manifest_row[1], update.effective_user.id)
    else:
        try:
            job_id = int(data.get("job") or data.get("id") or context.args[0])
        except (IndexError, TypeError, ValueError):
            return await update.message.reply_text(
                "⚠️ Cú pháp: <code>/manifest_handoff job=1 tool=kling</code> hoặc <code>/manifest_handoff manifest=2 tool=capcut</code>",
                parse_mode="HTML"
            )
        job = get_production_job(job_id, update.effective_user.id)
        if not job:
            return await update.message.reply_text("❌ Không tìm thấy production job.")
        manifest_row = latest_production_manifest(update.effective_user.id, job_id)
        if not manifest_row:
            return await update.message.reply_text(
                f"📭 Job #{job_id} chưa có manifest. Tạo trước bằng <code>/manifest job={job_id}</code>.",
                parse_mode="HTML"
            )
    if not job:
        return await update.message.reply_text("❌ Không tìm thấy production job của manifest.")
    prompt = build_manifest_handoff_prompt(job, manifest_row, target_tool)
    update_production_job(
        job[0],
        update.effective_user.id,
        stage="visuals" if target_tool in {"kling", "runway", "visuals"} else ("edit" if target_tool in {"capcut", "ffmpeg", "edit"} else job[7]),
        status="waiting",
        note=f"manifest_handoff:{manifest_row[0]}/{target_tool} | {truncate_text(prompt, 500)}"
    )
    await update.message.reply_text(
        f"🤝 <b>MANIFEST HANDOFF — #{manifest_row[0]}</b>\n"
        f"Job: <code>#{job[0]}</code> | Tool: <b>{html.escape(target_tool)}</b>\n\n"
        f"<pre>{html_pre(prompt)}</pre>",
        parse_mode="HTML"
    )

async def cmd_task_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    manifest_row = None
    try:
        manifest_id = int(data.get("manifest") or data.get("mid") or 0)
    except ValueError:
        manifest_id = 0
    if manifest_id:
        manifest_row = get_production_manifest(update.effective_user.id, manifest_id)
        if not manifest_row:
            return await update.message.reply_text("❌ Không tìm thấy manifest.")
    else:
        try:
            job_id = int(data.get("job") or data.get("id") or context.args[0])
        except (IndexError, TypeError, ValueError):
            return await update.message.reply_text(
                "⚠️ Cú pháp: <code>/task_plan job=1</code> hoặc <code>/task_plan manifest=2</code>",
                parse_mode="HTML"
            )
        manifest_row = latest_production_manifest(update.effective_user.id, job_id)
        if not manifest_row:
            return await update.message.reply_text(
                f"📭 Job #{job_id} chưa có manifest. Tạo trước bằng <code>/manifest job={job_id}</code>.",
                parse_mode="HTML"
            )
    created = create_tasks_from_manifest(update.effective_user.id, manifest_row)
    job_id = manifest_row[1]
    rows = list_production_tasks(update.effective_user.id, job_id=job_id, manifest_id=manifest_row[0], limit=50)
    lines = [
        f"✅ <b>ĐÃ TẠO TASK PLAN</b>",
        f"• Manifest: <code>#{manifest_row[0]}</code>",
        f"• Job: <code>#{job_id}</code>",
        f"• Task mới: <b>{len(created)}</b>\n",
    ]
    for tid, _job_id, mid, task_type, tool, scene_no, title, status, output_url, note, updated_at in rows[:20]:
        lines.append(
            f"• task #{tid} | {html.escape(task_type or '-')} | tool=<code>{html.escape(tool or '-')}</code> | "
            f"scene={scene_no or '-'} | {html.escape(status or '-')}\n"
            f"  {html.escape(title or '-')}"
        )
    lines.append("\nGiao việc: <code>/task_handoff id=&lt;TASK_ID&gt;</code> | Cập nhật: <code>/task_set id=&lt;TASK_ID&gt; status=ready url=https://...</code>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        job_id = int(data.get("job") or data.get("id") or (context.args[0] if context.args else 0))
    except ValueError:
        job_id = 0
    try:
        manifest_id = int(data.get("manifest") or data.get("mid") or 0)
    except ValueError:
        manifest_id = 0
    rows = list_production_tasks(update.effective_user.id, job_id=job_id or None, manifest_id=manifest_id or None)
    if not rows:
        return await update.message.reply_text("📭 Chưa có production task. Dùng /task_plan job=<ID>.")
    lines = ["✅ <b>PRODUCTION TASKS</b>\n"]
    for tid, row_job_id, mid, task_type, tool, scene_no, title, status, output_url, note, updated_at in rows:
        lines.append(
            f"• #{tid} | job #{row_job_id} | manifest #{mid or '-'} | <code>{html.escape(task_type or '-')}</code> | "
            f"{html.escape(status or '-')}\n"
            f"  tool={html.escape(tool or '-')} | scene={scene_no or '-'} | {html.escape(title or '-')}\n"
            f"  output={html.escape(output_url or '-')}"
        )
    lines.append("\nChi tiết/giao việc: <code>/task_handoff id=&lt;TASK_ID&gt;</code>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_next_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        job_id = int(data.get("job") or data.get("id") or (context.args[0] if context.args else 0))
    except ValueError:
        job_id = 0
    task = next_production_task(update.effective_user.id, job_id=job_id or None)
    if not task:
        if job_id:
            return await update.message.reply_text(f"✅ Job #{job_id} không còn task cần xử lý hoặc chưa có task.")
        return await update.message.reply_text("✅ Không có production task nào cần xử lý.")
    tid, row_job_id, mid, task_type, tool, scene_no, title, status, output_url, note, updated_at = task
    full_task = get_production_task(update.effective_user.id, tid)
    prompt = full_task[7] if full_task else ""
    update_production_task(update.effective_user.id, tid, status="working", note=note or "next_task_selected")
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Ready", callback_data=f"task|status|ready|{tid}"),
            InlineKeyboardButton("⛔ Blocked", callback_data=f"task|status|blocked|{tid}")
        ],
        [InlineKeyboardButton("📋 Handoff", callback_data=f"task|handoff|x|{tid}")]
    ])
    await update.message.reply_text(
        f"➡️ <b>NEXT TASK #{tid}</b>\n"
        f"Job: <code>#{row_job_id}</code> | Manifest: <code>#{mid or '-'}</code>\n"
        f"Type: <code>{html.escape(task_type or '-')}</code> | Tool: <b>{html.escape(tool or '-')}</b> | Scene: <b>{scene_no or '-'}</b>\n"
        f"Status: <b>working</b>\n"
        f"Title: {html.escape(title or '-')}\n\n"
        f"<pre>{html_pre(prompt or '-')}</pre>\n\n"
        f"Khi có output: <code>/task_set id={tid} status=ready url=https://...</code>",
        parse_mode="HTML",
        reply_markup=kb
    )

async def cmd_task_handoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        task_id = int(data.get("id") or data.get("task") or context.args[0])
    except (IndexError, TypeError, ValueError):
        return await update.message.reply_text("⚠️ Cú pháp: <code>/task_handoff id=&lt;TASK_ID&gt;</code>", parse_mode="HTML")
    task = get_production_task(update.effective_user.id, task_id)
    if not task:
        return await update.message.reply_text("❌ Không tìm thấy production task.")
    tid, job_id, manifest_id, task_type, tool, scene_no, title, prompt, status, output_url, note, updated_at = task
    update_production_task(update.effective_user.id, task_id, status="working", note=note or "handoff_started")
    await update.message.reply_text(
        f"🤝 <b>TASK HANDOFF #{tid}</b>\n"
        f"Job: <code>#{job_id}</code> | Manifest: <code>#{manifest_id or '-'}</code>\n"
        f"Type: <code>{html.escape(task_type or '-')}</code> | Tool: <b>{html.escape(tool or '-')}</b> | Scene: <b>{scene_no or '-'}</b>\n"
        f"Title: {html.escape(title or '-')}\n\n"
        f"<pre>{html_pre(prompt or '-')}</pre>\n\n"
        f"Khi có output: <code>/task_set id={tid} status=ready url=https://...</code>",
        parse_mode="HTML"
    )

async def cmd_task_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        task_id = int(data.get("id") or data.get("task") or context.args[0])
    except (IndexError, TypeError, ValueError):
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/task_set id=1 status=ready url=https://... note=...</code>",
            parse_mode="HTML"
        )
    status = (data.get("status") or data.get("state") or "").lower()
    allowed = {"queued", "working", "waiting", "ready", "blocked", "done", "cancelled"}
    if status and status not in allowed:
        return await update.message.reply_text(f"⚠️ status hợp lệ: <code>{', '.join(sorted(allowed))}</code>", parse_mode="HTML")
    output_url = data.get("url") or data.get("output")
    note = data.get("note")
    changed, row = update_production_task(update.effective_user.id, task_id, status or None, output_url, note)
    if not changed:
        return await update.message.reply_text("❌ Không tìm thấy task hoặc không có gì để cập nhật.")
    job_id, task_type = row
    if status in {"ready", "done"}:
        update_production_job(job_id, update.effective_user.id, status="working", note=f"task:{task_id} {task_type} {status}")
    await update.message.reply_text(
        f"✅ <b>Đã cập nhật task #{task_id}</b>\n"
        f"• Job: <code>#{job_id}</code>\n"
        f"• Type: <code>{html.escape(task_type or '-')}</code>\n"
        f"• Status: <b>{html.escape(status or 'giữ nguyên')}</b>\n"
        f"• Output: <code>{html.escape(output_url or 'giữ nguyên')}</code>",
        parse_mode="HTML"
    )

async def cmd_job_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    try:
        job_id = int(context.args[0])
    except (IndexError, ValueError):
        return await update.message.reply_text("⚠️ Cú pháp: <code>/job_report &lt;JOB_ID&gt;</code>", parse_mode="HTML")
    data = job_report_data(update.effective_user.id, job_id)
    if not data:
        return await update.message.reply_text("❌ Không tìm thấy production job.")
    job, assets, queue_items, performance = data
    (
        jid, calendar_id, campaign_id, channel_id, affiliate_id, platform, topic, stage, status,
        note, brief, asset_url, publish_url, channel_name, account_label, network, product_name, affiliate_url
    ) = job
    required = {
        "brief": bool(brief),
        "final_asset": any((asset_type or "") in {"final_video", "raw_video"} for _, asset_type, *_ in assets) or bool(asset_url),
        "publish_pack_or_review": stage in {"review", "publish", "done"} or status in {"ready", "published"},
        "affiliate": bool(affiliate_url),
        "queued_or_published": bool(queue_items) or status == "published",
    }
    readiness = "READY" if all(required.values()) else "MISSING"
    lines = [
        f"📋 <b>JOB REPORT #{jid}</b>",
        f"• Readiness: <b>{readiness}</b>",
        f"• Stage/status: <b>{html.escape(stage or '-')}</b>/<b>{html.escape(status or '-')}</b>",
        f"• Platform: <code>{html.escape(platform or '-')}</code>",
        f"• Channel: {html.escape(channel_name or '-')} / <code>{html.escape(account_label or 'main')}</code>",
        f"• Topic: {html.escape(topic or '-')}",
        f"• Affiliate: <code>{html.escape(network or '-')} / {html.escape(product_name or '-')}</code>",
        f"• Affiliate URL: <code>{html.escape(affiliate_url or 'chưa có')}</code>",
        f"• Asset URL: <code>{html.escape(asset_url or 'chưa có')}</code>",
        f"• Publish URL: <code>{html.escape(publish_url or 'chưa có')}</code>",
        "",
        "<b>Checklist:</b>",
    ]
    for key, ok in required.items():
        lines.append(f"• {'✅' if ok else '⚠️'} {key}")
    lines.append("\n<b>Assets gần nhất:</b>")
    if assets:
        for aid, asset_type, url, file_id, asset_note, created_at in assets[:5]:
            lines.append(f"• #{aid} | <code>{html.escape(asset_type or '-')}</code> | {created_at}\n  {html.escape(url or file_id or '-')}")
    else:
        lines.append("• Chưa có asset.")
    lines.append("\n<b>Publish queue:</b>")
    if queue_items:
        for qid, mode, q_status, scheduled_at, q_url, q_note, updated_at in queue_items:
            lines.append(f"• queue #{qid} | {mode}/{q_status} | schedule={html.escape(scheduled_at or '-')}\n  url={html.escape(q_url or '-')}")
    else:
        lines.append("• Chưa vào hàng đợi đăng.")
    lines.append("\n<b>Performance:</b>")
    if performance:
        for event_type, value_sum, amount_sum, count in performance:
            lines.append(f"• {event_type}: value={value_sum} amount={amount_sum:,}đ events={count}")
    else:
        lines.append("• Chưa có dữ liệu.")
    variants = list_creative_variants(update.effective_user.id, job_id, limit=5)
    lines.append("\n<b>Creative variants:</b>")
    if variants:
        for vid, label, hook, angle, caption, cta, hashtags, score, v_status, v_note, created_at, selected_at in variants[:5]:
            lines.append(
                f"• #{vid} | {html.escape(label or '-')} | score={score or 0} | {html.escape(v_status or '-')}\n"
                f"  Hook: {html.escape(hook or '-')}"
            )
    else:
        lines.append("• Chưa có. Dùng /creative_test job=%s." % job_id)
    manifests = list_production_manifests(update.effective_user.id, job_id, limit=3)
    lines.append("\n<b>Production manifests:</b>")
    if manifests:
        for mid, variant_id, m_status, manifest_json, created_at, updated_at in manifests:
            try:
                manifest = json.loads(manifest_json or "{}")
            except Exception:
                manifest = {}
            lines.append(
                f"• manifest #{mid} | variant={variant_id or '-'} | {html.escape(m_status or '-')}\n"
                f"  scenes={len(manifest.get('scenes') or [])} | title={html.escape(str(manifest.get('title') or '-'))}"
            )
    else:
        lines.append("• Chưa có. Dùng /manifest job=%s." % job_id)
    tasks = list_production_tasks(update.effective_user.id, job_id=job_id, limit=8)
    lines.append("\n<b>Production tasks:</b>")
    if tasks:
        for tid, row_job_id, mid, task_type, tool, scene_no, title, t_status, output_url, task_note, updated_at in tasks[:8]:
            lines.append(
                f"• task #{tid} | {html.escape(task_type or '-')} | {html.escape(t_status or '-')}\n"
                f"  tool={html.escape(tool or '-')} | scene={scene_no or '-'} | output={html.escape(output_url or '-')}"
            )
    else:
        lines.append("• Chưa có. Dùng /task_plan job=%s." % job_id)
    lines.append("\nLệnh tiếp theo: /creative_test, /manifest, /task_plan, /review_gate, /publish_pack, /queue_publish hoặc /performance_add tùy checklist.")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_job_ready(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        job_id = int(data.get("job") or data.get("id") or context.args[0])
    except (IndexError, TypeError, ValueError):
        return await update.message.reply_text("⚠️ Cú pháp: <code>/job_ready job=&lt;JOB_ID&gt;</code>", parse_mode="HTML")
    data = production_readiness_data(update.effective_user.id, job_id)
    if not data:
        return await update.message.reply_text("❌ Không tìm thấy production job.")
    job = data["job"]
    (
        jid, calendar_id, campaign_id, channel_id, affiliate_id, platform, topic, stage, status,
        note, brief, asset_url, publish_url, channel_name, account_label, network, product_name, affiliate_url
    ) = job
    level_label = {
        "READY_TO_PUBLISH": "✅ READY TO PUBLISH",
        "READY_TO_QUEUE": "🟡 READY TO QUEUE",
        "BLOCKED": "⛔ CHƯA ĐỦ ĐIỀU KIỆN",
    }.get(data["level"], data["level"])
    lines = [
        f"🚦 <b>JOB READY CHECK #{jid}</b>",
        f"• Kết luận: <b>{level_label}</b>",
        f"• Stage/status: <b>{html.escape(stage or '-')}</b>/<b>{html.escape(status or '-')}</b>",
        f"• Platform: <code>{html.escape(platform or '-')}</code> | Channel: {html.escape(channel_name or '-')}",
        f"• Topic: {html.escape(topic or '-')}",
        f"• Affiliate: {html.escape(product_name or affiliate_url or 'chưa có')}",
        "",
        "<b>Checklist trước khi đăng:</b>",
    ]
    for key, ok, detail, next_cmd in data["checks"]:
        mark = "✅" if ok else "⚠️"
        lines.append(f"• {mark} <code>{html.escape(key)}</code> — {html.escape(detail)}")

    lines.append("\n<b>Tóm tắt production:</b>")
    lines.append(f"• Creative variants: <b>{len(data['variants'])}</b> | selected: <b>{'có' if data['selected_variant'] else 'chưa'}</b>")
    lines.append(f"• Manifest: <b>{len(data['manifests'])}</b> | Tasks: <b>{len(data['tasks'])}</b> | Blocked: <b>{len(data['blocked_tasks'])}</b>")
    lines.append(f"• Assets: <b>{len(data['assets'])}</b> | final video: <b>{'có' if data['final_asset'] or publish_url else 'chưa'}</b>")
    lines.append(f"• Publish queue: <b>{len(data['queue_items'])}</b> | publish URL: <code>{html.escape(publish_url or 'chưa có')}</code>")
    lines.append(f"\n<b>Lệnh nên chạy tiếp:</b>\n<code>{html.escape(data['next_action'])}</code>")

    kb_rows = []
    if data["level"] == "READY_TO_QUEUE":
        kb_rows.append([InlineKeyboardButton("📦 Publish pack", callback_data=f"pipe|stage|publish|{job_id}")])
    if data["level"] == "READY_TO_PUBLISH":
        kb_rows.append([InlineKeyboardButton("✅ Mark ready", callback_data=f"pipe|status|ready|{job_id}")])
    kb_rows.append([InlineKeyboardButton("🛡 Review gate", callback_data=f"pipe|stage|review|{job_id}")])
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb_rows)
    )

async def cmd_publish_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    rows = list_publish_queue(update.effective_user.id)
    if not rows:
        return await update.message.reply_text("📭 Hàng đợi đăng trống. Dùng /queue_publish job=<ID>.")
    lines = ["📮 <b>PUBLISH QUEUE</b>\n"]
    for qid, job_id, platform, channel_name, mode, status, scheduled_at, publish_url, topic, updated_at in rows:
        lines.append(
            f"• queue #{qid} | job #{job_id} | <code>{html.escape(platform or '-')}</code> | "
            f"{html.escape(channel_name or '-')} | {mode}/{status}\n"
            f"  {html.escape(topic or '-')}\n"
            f"  schedule={html.escape(scheduled_at or '-')} | url={html.escape(publish_url or '-')}"
        )
    lines.append("\nCập nhật: <code>/publish_queue_set id=&lt;QUEUE_ID&gt; status=published url=https://...</code>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_publish_queue_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        queue_id = int(data.get("id") or data.get("queue") or context.args[0])
    except (IndexError, TypeError, ValueError):
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/publish_queue_set id=1 status=published url=https://... note=...</code>",
            parse_mode="HTML"
        )
    status = (data.get("status") or "").lower()
    allowed = {"queued", "scheduled", "publishing", "published", "blocked", "cancelled"}
    if status and status not in allowed:
        return await update.message.reply_text(f"⚠️ status hợp lệ: <code>{', '.join(sorted(allowed))}</code>", parse_mode="HTML")
    publish_url = data.get("url") or data.get("publish")
    note = data.get("note")
    changed, job_id = update_publish_queue_item(update.effective_user.id, queue_id, status, publish_url, note)
    if not changed:
        return await update.message.reply_text("❌ Không tìm thấy queue item.")
    if job_id and status == "published":
        update_production_job(job_id, update.effective_user.id, stage="done", status="published", note=note or "publish_queue_set", publish_url=publish_url or "")
        add_performance_event(update.effective_user.id, job_id, "publish", 1, 0, note or f"queue:{queue_id}")
    elif job_id and status == "blocked":
        update_production_job(job_id, update.effective_user.id, status="blocked", note=note or f"queue:{queue_id} blocked")
    await update.message.reply_text(
        f"✅ Đã cập nhật publish queue #{queue_id}\n"
        f"• status=<code>{html.escape(status or 'giữ nguyên')}</code>\n"
        f"• url=<code>{html.escape(publish_url or 'giữ nguyên')}</code>",
        parse_mode="HTML"
    )

async def cmd_performance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    event_totals, channel_totals, recent_events = performance_report_data(update.effective_user.id)
    lines = ["💰 <b>OPERATOR PERFORMANCE</b>", ""]
    lines.append("<b>Tổng theo loại:</b>")
    if event_totals:
        for event_type, value_sum, amount_sum, count in event_totals:
            lines.append(f"• {event_type}: value=<b>{value_sum}</b> | amount=<b>{amount_sum:,}đ</b> | events={count}")
    else:
        lines.append("• Chưa có dữ liệu. Ghi bằng /performance_add.")
    lines.append("\n<b>Kênh/sàn hiệu quả:</b>")
    if channel_totals:
        for platform, channel_name, value_sum, amount_sum, count in channel_totals:
            lines.append(
                f"• <code>{html.escape(platform or '-')}</code> | {html.escape(channel_name or '-')}: "
                f"value=<b>{value_sum}</b> | amount=<b>{amount_sum:,}đ</b> | events={count}"
            )
    else:
        lines.append("• Chưa có dữ liệu.")
    lines.append("\n<b>Sự kiện gần nhất:</b>")
    if recent_events:
        for job_id, event_type, value, amount, platform, topic, note, created_at in recent_events:
            lines.append(
                f"• {created_at} | job #{job_id} | <code>{html.escape(event_type)}</code> | "
                f"{html.escape(platform or '-')} | value={value} | amount={amount:,}đ\n"
                f"  {html.escape(topic or '-')}\n"
                f"  note={html.escape(note or '-')}"
            )
    else:
        lines.append("• Chưa có sự kiện.")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_growth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        days = max(1, min(int(data.get("days") or data.get("ngay") or (context.args[0] if context.args else 14)), 90))
    except (TypeError, ValueError):
        days = 14
    since, job_rows, channel_rows, variant_rows = growth_optimizer_data(update.effective_user.id, days=days, limit=8)
    lines = [
        f"📈 <b>GROWTH OPTIMIZER — {days} ngày</b>",
        f"• Từ: <code>{html.escape(since)}</code>",
        "",
        "<b>Job/nội dung thắng:</b>",
    ]
    best_job = None
    if job_rows:
        ranked_jobs = []
        for row in job_rows:
            job_id, topic, platform, channel_name, product_name, views, clicks, conversions, revenue, cost, events = row
            score, ctr, cvr, roi = growth_score(views, clicks, conversions, revenue, cost)
            ranked_jobs.append((score, row, ctr, cvr, roi))
        ranked_jobs.sort(key=lambda item: item[0], reverse=True)
        best_job = ranked_jobs[0][1]
        for score, row, ctr, cvr, roi in ranked_jobs[:6]:
            job_id, topic, platform, channel_name, product_name, views, clicks, conversions, revenue, cost, events = row
            lines.append(
                f"• job #{job_id} | score=<b>{score}</b> | <code>{html.escape(platform or '-')}</code> | {html.escape(channel_name or '-')}\n"
                f"  views={views or 0} click={clicks or 0} conv={conversions or 0} rev={int(revenue or 0):,}đ cost={int(cost or 0):,}đ\n"
                f"  CTR={ctr:.2f}% | CVR={cvr:.2f}% | ROI={roi:.1f}%\n"
                f"  {html.escape(topic or '-')}"
            )
    else:
        lines.append("• Chưa có dữ liệu. Đẩy dữ liệu qua /performance_add hoặc /api/operator/performance.")

    lines.append("\n<b>Kênh/sàn nên ưu tiên:</b>")
    if channel_rows:
        for platform, channel_name, views, clicks, conversions, revenue, events in channel_rows[:5]:
            score, ctr, cvr, roi = growth_score(views, clicks, conversions, revenue, 0)
            lines.append(
                f"• <code>{html.escape(platform or '-')}</code> | {html.escape(channel_name or '-')}: "
                f"score=<b>{score}</b> | views={views or 0} click={clicks or 0} conv={conversions or 0} rev={int(revenue or 0):,}đ"
            )
    else:
        lines.append("• Chưa có dữ liệu kênh.")

    lines.append("\n<b>Creative/variant nên remix:</b>")
    if variant_rows:
        for variant_id, label, hook, views, clicks, conversions, revenue in variant_rows[:5]:
            score, ctr, cvr, roi = growth_score(views, clicks, conversions, revenue, 0)
            lines.append(
                f"• variant #{variant_id} | score=<b>{score}</b> | {html.escape(label or '-')}\n"
                f"  CTR={ctr:.2f}% | revenue={int(revenue or 0):,}đ | Hook: {html.escape(hook or '-')}"
            )
    else:
        lines.append("• Chưa có variant có dữ liệu.")

    next_commands = []
    if best_job:
        job_id, topic, platform, channel_name, product_name, *_ = best_job
        next_commands.append(f"/operator_build job={job_id} n=5 duration=45")
        next_commands.append(f"/autopilot niche={topic or product_name or 'công nghệ AI'} platform={platform or 'tiktok'} channel=all limit=3 duration=45")
    else:
        next_commands.append("/autopilot niche=công nghệ AI platform=tiktok channel=all limit=3 duration=45")
    lines.append("\n<b>Lệnh đề xuất:</b>")
    for cmd in next_commands[:3]:
        lines.append(f"• <code>{html.escape(cmd)}</code>")

    if (gemini_client or openai_client) and job_rows:
        compact = "\n".join(
            f"job {row[0]} | {row[2]} | {row[3]} | views={row[5]} clicks={row[6]} conv={row[7]} rev={row[8]} | {row[1]}"
            for row in job_rows[:8]
        )
        advice = AgentGemini.chat(
            "Bạn là growth strategist cho hệ thống AI affiliate video. Dựa trên dữ liệu, đề xuất 3 hành động ngắn, thực dụng, không hứa doanh thu phi thực tế.",
            compact,
            update.effective_user.id,
            is_json=False
        )
        lines.append(f"\n<b>AI nhận định:</b>\n<pre>{html_pre(advice, 1200)}</pre>")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_operator_loop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        limit = max(1, min(int(data.get("limit") or data.get("max") or 10), 30))
    except ValueError:
        limit = 10
    auto_queue = (data.get("queue") or data.get("auto_queue") or "1").lower() not in {"0", "false", "no", "off"}
    advanced, ready_publish, next_tasks, blocked = operator_loop_data(update.effective_user.id, limit=limit, auto_queue=auto_queue)
    lines = [
        "🔁 <b>OPERATOR LOOP</b>",
        f"• Quét tối đa: <b>{limit}</b> job",
        f"• Auto queue publish: <b>{'bật' if auto_queue else 'tắt'}</b>",
        "",
    ]
    lines.append("<b>Đã tự đẩy bước:</b>")
    if advanced:
        for jid, action, queue_id, topic, platform, channel_name in advanced[:10]:
            lines.append(
                f"• job #{jid} → queue #{queue_id} | <code>{html.escape(platform or '-')}</code> | {html.escape(channel_name or '-')}\n"
                f"  {html.escape(topic or '-')}"
            )
    else:
        lines.append("• Chưa có job nào đủ điều kiện tự đưa vào publish queue.")

    lines.append("\n<b>Queue sẵn sàng cho publisher worker:</b>")
    if ready_publish:
        for jid, topic, platform, channel_name in ready_publish[:8]:
            lines.append(f"• job #{jid} | <code>{html.escape(platform or '-')}</code> | {html.escape(channel_name or '-')} | {html.escape(topic or '-')}")
    else:
        lines.append("• Chưa có queue ready/publishing mở.")

    lines.append("\n<b>Task tiếp theo cho AI/tool worker:</b>")
    if next_tasks:
        for tid, job_id, task_type, tool, scene_no, title, status, topic, platform, channel_name in next_tasks[:10]:
            lines.append(
                f"• task #{tid} | job #{job_id} | <code>{html.escape(task_type or '-')}</code>/{html.escape(tool or '-')}"
                f" | scene={scene_no or '-'} | {html.escape(status or '-')}\n"
                f"  {html.escape(title or topic or '-')}"
            )
        lines.append("\nWorker API: <code>GET /api/operator/tasks/next</code>")
    else:
        lines.append("• Không có task queued/waiting.")

    lines.append("\n<b>Cần admin xử lý:</b>")
    if blocked:
        for jid, level, next_action, topic, platform, channel_name in blocked[:8]:
            lines.append(
                f"• job #{jid} | {html.escape(level or '-') } | <code>{html.escape(platform or '-')}</code> | {html.escape(channel_name or '-')}\n"
                f"  next: <code>{html.escape(next_action or '/job_ready job=' + str(jid))}</code>"
            )
    else:
        lines.append("• Không có job nghẽn rõ ràng.")
    lines.append("\nLệnh liên quan: <code>/operator_dashboard</code> | <code>/publish_queue</code> | <code>/growth</code>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_publish_pack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        job_id = int(data.get("id") or data.get("job") or context.args[0])
    except (IndexError, TypeError, ValueError):
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/publish_pack job=1</code>\n"
            "Sau khi đăng: <code>/pipeline_set id=1 stage=publish status=published publish=https://...</code>",
            parse_mode="HTML"
        )
    job = get_production_job(job_id, update.effective_user.id)
    if not job:
        return await update.message.reply_text("❌ Không tìm thấy production job.")
    if gemini_client or openai_client:
        pack = AgentGemini.chat(
            "Bạn là AI Operator trưởng chuẩn bị publish pack cho video affiliate.",
            build_publish_pack_prompt(job),
            update.effective_user.id,
            is_json=False
        )
    else:
        pack = (
            "Chưa cấu hình AI Provider. Publish pack tối thiểu:\n"
            "- Dùng brief hiện có trong /pipeline <id>.\n"
            "- Gắn link affiliate rõ ràng.\n"
            "- Kiểm tra quyền hình ảnh/âm thanh và chính sách nền tảng.\n"
            "- Sau khi đăng, cập nhật publish URL và performance."
        )
    update_production_job(job_id, update.effective_user.id, stage="publish", status="ready", note=f"publish_pack | {truncate_text(pack, 800)}")
    await update.message.reply_text(
        f"📦 <b>PUBLISH PACK — JOB #{job_id}</b>\n"
        f"Stage: <b>publish</b> | Status: <b>ready</b>\n\n"
        f"<pre>{html_pre(pack)}</pre>",
        parse_mode="HTML"
    )

async def cmd_handoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        job_id = int(data.get("id") or data.get("job") or context.args[0])
    except (IndexError, TypeError, ValueError):
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/handoff job=1 tool=claude stage=script</code>\n"
            "Tool gợi ý: <code>claude, gemini, runway, kling, capcut, ffmpeg, fish, edge</code>",
            parse_mode="HTML"
        )
    job = get_production_job(job_id, update.effective_user.id)
    if not job:
        return await update.message.reply_text("❌ Không tìm thấy production job.")
    target_tool = (data.get("tool") or data.get("ai") or "claude").lower()
    target_stage = (data.get("stage") or data.get("step") or job[7] or "script").lower()
    handoff = build_handoff_prompt(job, target_tool, target_stage)
    update_production_job(
        job_id,
        update.effective_user.id,
        stage=target_stage,
        status="waiting",
        note=f"handoff:{target_tool}/{target_stage} | {truncate_text(handoff, 500)}"
    )
    await update.message.reply_text(
        f"🤝 <b>HANDOFF PROMPT — JOB #{job_id}</b>\n"
        f"Tool: <b>{html.escape(target_tool)}</b> | Stage: <b>{html.escape(target_stage)}</b>\n\n"
        f"<pre>{html_pre(handoff)}</pre>",
        parse_mode="HTML"
    )

async def cmd_review_gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        job_id = int(data.get("id") or data.get("job") or context.args[0])
    except (IndexError, TypeError, ValueError):
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/review_gate job=1</code>\n"
            "Nếu đạt, dùng nút <b>Approve Publish</b> để chuyển job sang ready.",
            parse_mode="HTML"
        )
    job = get_production_job(job_id, update.effective_user.id)
    if not job:
        return await update.message.reply_text("❌ Không tìm thấy production job.")
    if gemini_client or openai_client:
        review = AgentGemini.chat(
            "Bạn là AI compliance reviewer cho video affiliate/social publishing.",
            build_review_gate_prompt(job),
            update.effective_user.id,
            is_json=False
        )
    else:
        review = (
            "Chưa cấu hình AI Provider. Review thủ công:\n"
            "- Kiểm tra quyền hình ảnh/âm thanh/consent.\n"
            "- Kiểm tra affiliate claim và CTA.\n"
            "- Kiểm tra nội dung không spam/không mạo danh.\n"
            "- Nếu đạt, approve publish."
        )
    update_production_job(job_id, update.effective_user.id, stage="review", status="waiting", note=f"review_gate | {truncate_text(review, 700)}")
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve Publish", callback_data=f"pipe|status|ready|{job_id}"),
            InlineKeyboardButton("⛔ Blocked", callback_data=f"pipe|status|blocked|{job_id}")
        ],
        [InlineKeyboardButton("📦 Publish pack", callback_data=f"pipe|stage|publish|{job_id}")]
    ])
    await update.message.reply_text(
        f"🛡️ <b>REVIEW GATE — JOB #{job_id}</b>\n"
        f"Stage: <b>review</b> | Status: <b>waiting</b>\n\n"
        f"<pre>{html_pre(review)}</pre>",
        parse_mode="HTML",
        reply_markup=kb
    )

async def cmd_trend_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    niche = data.get("niche") or data.get("ngach") or data.get("topic") or data.get("chude") or "công nghệ AI"
    platform = data.get("platform") or data.get("nen") or "tiktok"
    try:
        channel_id = int(data.get("channel") or data.get("kenh") or 0)
    except ValueError:
        channel_id = 0
    try:
        affiliate_id = int(data.get("affiliate_id") or data.get("aff") or 0)
    except ValueError:
        affiliate_id = 0
    try:
        campaign_id = int(data.get("campaign") or data.get("camp") or 0)
    except ValueError:
        campaign_id = 0
    if channel_id and not get_social_channel(channel_id, update.effective_user.id):
        return await update.message.reply_text("❌ Không tìm thấy channel.")
    if affiliate_id and not get_affiliate_link(affiliate_id, update.effective_user.id):
        return await update.message.reply_text("❌ Không tìm thấy affiliate.")
    if campaign_id and not get_campaign(campaign_id, update.effective_user.id):
        return await update.message.reply_text("❌ Không tìm thấy campaign.")

    msg = await update.message.reply_text("🔎 Đang tìm trend mới nhất...")
    try:
        items = await fetch_google_news_trends(niche, platform, limit=5)
    except Exception as e:
        await alert_admin(context, "Trend Search", f"{str(e)} | niche={niche} platform={platform}")
        return await msg.edit_text("❌ Tìm trend lỗi. Đã báo admin kiểm tra mạng/RSS.")
    if not items:
        return await msg.edit_text("📭 Chưa tìm thấy trend phù hợp. Thử niche khác.")

    channel = get_social_channel(channel_id, update.effective_user.id) if channel_id else None
    affiliate = get_affiliate_link(affiliate_id, update.effective_user.id) if affiliate_id else None
    scored_items = []
    for item in items:
        scores = score_trend_candidate(niche, platform, item["title"], item.get("summary", ""), channel, affiliate)
        scored_items.append((scores["trend_score"], item, scores))
    scored_items.sort(key=lambda row: row[0], reverse=True)

    lines = [
        "🔥 <b>TREND MỚI GỢI Ý LÀM VIDEO</b>",
        f"• Niche: <b>{html.escape(niche)}</b>",
        f"• Nền tảng mục tiêu: <code>{html.escape(platform)}</code>",
        "",
    ]
    buttons = []
    for _, item, scores in scored_items:
        trend_id = save_trend_candidate(
            update.effective_user.id,
            niche,
            platform,
            item["title"],
            item["url"],
            item.get("source", ""),
            item.get("summary", ""),
            channel_id,
            campaign_id,
            affiliate_id,
            scores["trend_score"],
            scores["affiliate_fit_score"],
            scores["competition_score"],
            scores["score_reason"]
        )
        lines.append(
            f"• #{trend_id} | score=<b>{scores['trend_score']}</b> | aff=<b>{scores['affiliate_fit_score']}</b> | "
            f"comp=<b>{scores['competition_score']}</b>\n"
            f"  <b>{html.escape(item['title'])}</b>\n"
            f"  Nguồn: {html.escape(item.get('source') or '-')} | Lý do: {html.escape(scores['score_reason'])}"
        )
        buttons.append([InlineKeyboardButton(f"🎬 Tạo video trend #{trend_id} ({scores['trend_score']})", callback_data=f"trend|video|{trend_id}")])
    lines.append("\nChọn nút bên dưới để đưa trend vào pipeline affiliate.")
    await msg.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))

async def cmd_trend_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    try:
        limit = max(1, min(int(context.args[0]), 20)) if context.args else 10
    except ValueError:
        limit = 10
    rows = list_trend_candidates(update.effective_user.id, limit)
    if not rows:
        return await update.message.reply_text("📭 Chưa có trend đã lưu. Dùng /trend_search trước.")
    lines = ["🏆 <b>TREND RANKING</b>", "Điểm càng cao càng nên ưu tiên sản xuất video affiliate.\n"]
    for tid, niche, platform, title, source_name, status, trend_score, affiliate_fit, competition, reason, created_at in rows:
        lines.append(
            f"• #{tid} | score=<b>{trend_score or 0}</b> | aff=<b>{affiliate_fit or 0}</b> | "
            f"comp=<b>{competition or 0}</b> | {html.escape(status or '-')}\n"
            f"  <code>{html.escape(platform or '-')}</code> | {html.escape(niche or '-')}\n"
            f"  {html.escape(title or '-')}\n"
            f"  nguồn={html.escape(source_name or '-')} | lý do={html.escape(reason or '-')}\n"
            f"  {created_at or '-'}"
        )
    lines.append("\nTạo video: bấm nút trong /trend_search hoặc tìm lại kèm channel/aff.")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def handle_trend_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if str(query.from_user.id) != ADMIN_ID:
        return await query.answer("Chỉ Admin được dùng.", show_alert=True)
    parts = query.data.split("|")
    if len(parts) != 3 or parts[1] != "video":
        return
    try:
        trend_id = int(parts[2])
    except ValueError:
        return
    trend = get_trend_candidate(trend_id, query.from_user.id)
    if not trend:
        return await query.edit_message_text("❌ Không tìm thấy trend.")
    (
        _, niche, platform, title, source_url, source_name, summary, channel_id, campaign_id,
        affiliate_id, status, trend_score, affiliate_fit, competition, score_reason
    ) = trend
    if not channel_id:
        return await query.edit_message_text(
            "⚠️ Trend này chưa gắn channel. Tìm lại bằng:\n"
            f"<code>/trend_search niche={html.escape(niche)} platform={html.escape(platform)} channel=&lt;ID&gt; aff=&lt;ID&gt;</code>",
            parse_mode="HTML"
        )
    channel = get_social_channel(channel_id, query.from_user.id)
    if not channel:
        return await query.edit_message_text("❌ Channel của trend không còn tồn tại.")
    _, channel_platform, channel_name, account_label, focus, audience, slots, channel_status = channel
    topic = f"{title} | góc nhìn {niche} | chèn sản phẩm affiliate phù hợp"
    note = (
        f"trend #{trend_id} | score={trend_score or 0} aff_fit={affiliate_fit or 0} "
        f"competition={competition or 0} | source={source_name} | {source_url}"
    )
    slot_id = create_calendar_slot(
        query.from_user.id,
        channel_id,
        campaign_id,
        affiliate_id,
        datetime.now().date().isoformat(),
        channel_platform or platform,
        topic,
        note
    )
    slot = get_calendar_slot(slot_id, query.from_user.id)
    if gemini_client or openai_client:
        brief = AgentGemini.chat(
            "Bạn là AI Operator trưởng, biến trend mới thành brief video affiliate có kiểm duyệt.",
            build_production_prompt(slot) + f"\n\nNguồn trend: {source_url}\nTóm tắt trend: {summary}",
            query.from_user.id,
            is_json=False
        )
    else:
        brief = f"Trend: {title}\nNguồn: {source_url}\nTạo video affiliate theo trend này và kiểm duyệt trước khi đăng."
    job_id = create_production_job(
        query.from_user.id,
        slot_id,
        campaign_id,
        channel_id,
        affiliate_id,
        channel_platform or platform,
        topic,
        brief,
        note
    )
    update_trend_status(trend_id, query.from_user.id, f"job:{job_id}")
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🧠 Next script", callback_data=f"pipe|stage|script|{job_id}"),
            InlineKeyboardButton("📦 Publish pack", callback_data=f"pipe|stage|publish|{job_id}")
        ],
        [InlineKeyboardButton("⛔ Blocked", callback_data=f"pipe|status|blocked|{job_id}")]
    ])
    await query.edit_message_text(
        f"✅ <b>Đã tạo video job từ trend #{trend_id}</b>\n"
        f"• Production job: <code>#{job_id}</code>\n"
        f"• Slot: <code>#{slot_id}</code>\n"
        f"• Kênh: <b>{html.escape(channel_name or '-')}</b> / <code>{html.escape(account_label or 'main')}</code>\n"
        f"• Score: <b>{trend_score or 0}</b> | Aff fit: <b>{affiliate_fit or 0}</b> | Competition: <b>{competition or 0}</b>\n"
        f"• Lý do: {html.escape(score_reason or '-')}\n"
        f"• Trend: {html.escape(title)}\n\n"
        f"<pre>{html_pre(brief)}</pre>",
        parse_mode="HTML",
        reply_markup=kb
    )

async def handle_pipeline_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if str(query.from_user.id) != ADMIN_ID:
        return await query.answer("Chỉ Admin được dùng.", show_alert=True)
    parts = query.data.split("|")
    if len(parts) != 4:
        return
    _, field, value, job_id_raw = parts
    try:
        job_id = int(job_id_raw)
    except ValueError:
        return
    if field == "stage":
        update_production_job(job_id, query.from_user.id, stage=value, status="working")
    elif field == "status":
        stage = "done" if value in ("published", "done") else None
        update_production_job(job_id, query.from_user.id, stage=stage, status=value)
    else:
        return
    job = get_production_job(job_id, query.from_user.id)
    if not job:
        return await query.edit_message_text("❌ Không tìm thấy production job.")
    await query.edit_message_text(
        f"✅ Pipeline #{job_id} đã cập nhật\n"
        f"Stage: <b>{html.escape(job[7] or '-')}</b>\n"
        f"Status: <b>{html.escape(job[8] or '-')}</b>\n\n"
        "Xem chi tiết: /pipeline " + str(job_id),
        parse_mode="HTML"
    )

async def handle_video_job_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if str(query.from_user.id) != ADMIN_ID:
        return await query.answer("Chỉ Admin được dùng.", show_alert=True)
    parts = query.data.split("|")
    if len(parts) != 3:
        return
    _, action, job_id_raw = parts
    if action == "stats":
        total_campaigns, job_counts, recent_jobs = campaign_stats(query.from_user.id)
        lines = [f"📊 Campaign: {total_campaigns}", "Jobs: " + (", ".join(f"{k}={v}" for k, v in job_counts.items()) or "0")]
        return await query.edit_message_text("\n".join(lines))
    try:
        job_id = int(job_id_raw)
    except ValueError:
        return
    job = get_video_job(job_id, query.from_user.id)
    if not job:
        return await query.edit_message_text("❌ Không tìm thấy job.")
    if action == "approve":
        update_video_job_status(job_id, "approved", "approved_at")
        return await query.edit_message_text(
            f"✅ <b>Đã duyệt VIDEO JOB #{job_id}</b>\n\n"
            "Bước tiếp theo v1: dùng brief này để tạo asset/video. V2 sẽ nối API Kling/Runway/CapCut/FFmpeg và auto-post qua API chính thức.",
            parse_mode="HTML"
        )
    if action == "cancel":
        update_video_job_status(job_id, "cancelled")
        return await query.edit_message_text(f"❌ Đã hủy VIDEO JOB #{job_id}")

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
            "SELECT order_code FROM pending_deposits WHERE user_id=? AND status='pending' ORDER BY submitted_at DESC LIMIT 1",
            (str(target_id),)
        )
        pending_order = c.fetchone()
        c.execute(
            "UPDATE pending_deposits SET status='approved' WHERE user_id=? AND status='pending'",
            (str(target_id),)
        )
        if pending_order and pending_order[0]:
            c.execute(
                "UPDATE payos_orders SET status=?, paid_at=? WHERE order_code=?",
                (PAYOS_STATUS_PAID, now_text(), str(pending_order[0]))
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

async def cmd_checkpayos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    try:
        order_code = context.args[0]
    except IndexError:
        return await update.message.reply_text("⚠️ Cú pháp: /checkpayos <Mã_đơn>")

    payment_link_id = get_order_payment_link_id(order_code)
    if not payment_link_id:
        return await update.message.reply_text(
            "⚠️ Đơn này chưa có paymentLinkId PayOS. Nếu khách đã chuyển khoản thủ công, dùng /duyet <ID> <Xu>."
        )
    if not PAYOS_CLIENT_ID or not PAYOS_API_KEY:
        return await update.message.reply_text("❌ Thiếu PAYOS_CLIENT_ID hoặc PAYOS_API_KEY.")

    headers = {"x-client-id": PAYOS_CLIENT_ID, "x-api-key": PAYOS_API_KEY}
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(
                f"https://api-merchant.payos.vn/v2/payment-requests/{payment_link_id}",
                headers=headers,
                timeout=30.0
            )
        data = res.json()
        payment_data = data.get("data", {})
        status = payment_data.get("status", "")
        amount_vnd = int(payment_data.get("amount", 0) or 0)
        if res.status_code == 200 and data.get("code") == "00" and status == PAYOS_STATUS_PAID:
            processed, desc, info = process_payos_paid_order(str(order_code), amount_vnd)
            if processed:
                target_id = info["target_id"]
                credits_now, _, _ = get_user(target_id)
                await context.bot.send_message(
                    chat_id=target_id,
                    text=(
                        f"🎉 <b>NẠP TỰ ĐỘNG THÀNH CÔNG!</b>\n\n"
                        f"PayOS đã xác nhận đơn <code>{order_code}</code>.\n"
                        f"🪙 Đã cộng: <b>+{info['xu']} Xu</b>\n"
                        f"💼 Số dư hiện tại: <b>{credits_now} Xu</b>"
                    ),
                    parse_mode="HTML"
                )
            return await update.message.reply_text(f"✅ Check PayOS: {desc} | status={status}")
        await update.message.reply_text(f"ℹ️ PayOS trả về status=<b>{status or 'UNKNOWN'}</b> cho đơn <code>{order_code}</code>.", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Check PayOS error: {e}")
        await update.message.reply_text(f"❌ Không kiểm tra được PayOS: {str(e)}")

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
        "SELECT id, user_id, username, submitted_at, order_code, amount, xu FROM pending_deposits "
        "WHERE status='pending' ORDER BY submitted_at DESC LIMIT 10"
    )
    rows = c.fetchall()
    conn.close()
    if not rows:
        return await update.message.reply_text("📭 Không có bill nào đang chờ.")
    lines = ["📋 <b>BILL CHỜ DUYỆT (THỦ CÔNG):</b>\n"]
    for r in rows:
        expected = f" | {r[5]:,}đ → {r[6]} Xu | đơn {r[4]}" if r[5] and r[6] else ""
        lines.append(
            f"• #{r[0]} | {r[2]} | <code>{r[1]}</code>{expected} | {r[3]}\n"
            f"  ➔ <code>/duyet {r[1]} {r[6] or '&lt;Xu&gt;'}</code>"
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
    bill_state = USER_BILL_STATE.get(uid)
    is_bill = bill_state or any(
        k in caption_lower for k in ["bill", "nạp", "chuyển khoản", "ck", "daas"]
    )

    if is_bill:
        USER_BILL_STATE.pop(uid, None)
        if isinstance(bill_state, dict):
            order_code = bill_state.get("order_code", "")
            amount = int(bill_state.get("amount", 0) or 0)
            xu = int(bill_state.get("xu", 0) or 0)
        else:
            order_code, amount, xu = "", 0, 0
        conn = db_connect()
        c = conn.cursor()
        c.execute(
            "INSERT INTO pending_deposits (user_id, username, file_id, submitted_at, status, order_code, amount, xu) VALUES (?,?,?,?,?,?,?,?)",
            (str(uid), username, update.message.photo[-1].file_id,
             now_text(), "pending", str(order_code), amount, xu)
        )
        deposit_id = c.lastrowid
        conn.commit()
        conn.close()
        expected_line = (
            f"💰 Gói khách chọn: <b>{amount:,}đ → {xu} Xu</b>\n"
            f"🆔 Mã đơn: <code>{order_code}</code>\n"
            if amount and xu and order_code else ""
        )
        admin_caption = (
            f"💸 <b>BILL MỚI TẢI LÊN THỦ CÔNG #{deposit_id}</b>\n\n"
            f"👤 Khách: <b>{username}</b>\n"
            f"🆔 ID: <code>{uid}</code>\n"
            f"{expected_line}"
            f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
            f"👉 Duyệt: <code>/duyet {uid} {xu or '&lt;Số_Xu&gt;'}</code>\n"
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
            f"⏳ Vui lòng chờ Admin kiểm tra sao kê và cộng Xu.",
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
            f"🖼️ <b>Gói Cao Cấp</b> — RemoveBG HD, trừ <b>{final_cost} Xu</b>\n"
            f"✂️ <b>Gói Tiết Kiệm</b> — Cutout.pro, trừ <b>{IMAGE_FREE_COST} Xu</b>\n\n"
            f"<i>Nếu gói cao cấp lỗi/quota, hệ thống tự chuyển Cutout.pro và hoàn phần chênh lệch.</i>"
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
                f"🎙️ <b>Gói Cao Cấp</b> — Fish Audio HD, trừ <b>{fish_cost} Xu</b>\n"
                f"🔊 <b>Gói Tiết Kiệm</b> — Edge TTS, trừ <b>{VOICE_FREE_COST} Xu</b>\n\n"
                f"<i>Nếu gói cao cấp lỗi/quota, hệ thống tự chuyển Edge TTS và hoàn phần chênh lệch.</i>"
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
    tg_app.add_handler(CommandHandler("thucong",     cmd_thanhtoan_thucong))
    tg_app.add_handler(CommandHandler("tools",       cmd_tools))
    tg_app.add_handler(CommandHandler("mmo",         cmd_mmo))
    tg_app.add_handler(CommandHandler("campaign_new", cmd_campaign_new))
    tg_app.add_handler(CommandHandler("campaigns",   cmd_campaigns))
    tg_app.add_handler(CommandHandler("video_plan",  cmd_video_plan))
    tg_app.add_handler(CommandHandler("video_job",   cmd_video_job))
    tg_app.add_handler(CommandHandler("campaign_stats", cmd_campaign_stats))
    tg_app.add_handler(CommandHandler("channel_add", cmd_channel_add))
    tg_app.add_handler(CommandHandler("channels",    cmd_channels))
    tg_app.add_handler(CommandHandler("channel_publish_set", cmd_channel_publish_set))
    tg_app.add_handler(CommandHandler("publish_readiness", cmd_publish_readiness))
    tg_app.add_handler(CommandHandler("affiliate_add", cmd_affiliate_add))
    tg_app.add_handler(CommandHandler("affiliates",  cmd_affiliates))
    tg_app.add_handler(CommandHandler("affiliate_profile", cmd_affiliate_profile))
    tg_app.add_handler(CommandHandler("affiliate_match", cmd_affiliate_match))
    tg_app.add_handler(CommandHandler("calendar_plan", cmd_calendar_plan))
    tg_app.add_handler(CommandHandler("calendar",    cmd_calendar))
    tg_app.add_handler(CommandHandler("operator",    cmd_operator))
    tg_app.add_handler(CommandHandler("operator_build", cmd_operator_build))
    tg_app.add_handler(CommandHandler("operator_auto", cmd_operator_auto))
    tg_app.add_handler(CommandHandler("operator_next", cmd_operator_next))
    tg_app.add_handler(CommandHandler("operator_dashboard", cmd_operator_dashboard))
    tg_app.add_handler(CommandHandler("operator_daily", cmd_operator_daily))
    tg_app.add_handler(CommandHandler("operator_menu", cmd_operator_menu))
    tg_app.add_handler(CommandHandler("operator_loop", cmd_operator_loop))
    tg_app.add_handler(CommandHandler("brain", cmd_brain))
    tg_app.add_handler(CommandHandler("autopilot", cmd_autopilot))
    tg_app.add_handler(CommandHandler("trend_search", cmd_trend_search))
    tg_app.add_handler(CommandHandler("trend_rank", cmd_trend_rank))
    tg_app.add_handler(CommandHandler("handoff", cmd_handoff))
    tg_app.add_handler(CommandHandler("publish_pack", cmd_publish_pack))
    tg_app.add_handler(CommandHandler("review_gate", cmd_review_gate))
    tg_app.add_handler(CommandHandler("creative_test", cmd_creative_test))
    tg_app.add_handler(CommandHandler("creative_variants", cmd_creative_variants))
    tg_app.add_handler(CommandHandler("creative_select", cmd_creative_select))
    tg_app.add_handler(CommandHandler("creative_report", cmd_creative_report))
    tg_app.add_handler(CommandHandler("manifest", cmd_manifest))
    tg_app.add_handler(CommandHandler("manifests", cmd_manifests))
    tg_app.add_handler(CommandHandler("manifest_handoff", cmd_manifest_handoff))
    tg_app.add_handler(CommandHandler("task_plan", cmd_task_plan))
    tg_app.add_handler(CommandHandler("tasks", cmd_tasks))
    tg_app.add_handler(CommandHandler("next_task", cmd_next_task))
    tg_app.add_handler(CommandHandler("task_handoff", cmd_task_handoff))
    tg_app.add_handler(CommandHandler("task_set", cmd_task_set))
    tg_app.add_handler(CommandHandler("queue_publish", cmd_queue_publish))
    tg_app.add_handler(CommandHandler("publish_queue", cmd_publish_queue))
    tg_app.add_handler(CommandHandler("publish_queue_set", cmd_publish_queue_set))
    tg_app.add_handler(CommandHandler("asset_add", cmd_asset_add))
    tg_app.add_handler(CommandHandler("assets", cmd_assets))
    tg_app.add_handler(CommandHandler("job_report", cmd_job_report))
    tg_app.add_handler(CommandHandler("job_ready", cmd_job_ready))
    tg_app.add_handler(CommandHandler("mark_published", cmd_mark_published))
    tg_app.add_handler(CommandHandler("performance_add", cmd_performance_add))
    tg_app.add_handler(CommandHandler("performance", cmd_performance))
    tg_app.add_handler(CommandHandler("growth", cmd_growth))
    tg_app.add_handler(CommandHandler("produce",     cmd_produce))
    tg_app.add_handler(CommandHandler("pipeline",    cmd_pipeline))
    tg_app.add_handler(CommandHandler("pipeline_set", cmd_pipeline_set))
    tg_app.add_handler(CommandHandler("ref",         cmd_ref))
    tg_app.add_handler(CommandHandler("gopy",        cmd_gopy))
    tg_app.add_handler(CommandHandler("add",         cmd_admin_add))
    tg_app.add_handler(CommandHandler("admin_gopy",  cmd_admin_gopy))
    tg_app.add_handler(CommandHandler("duyet",       cmd_duyet))
    tg_app.add_handler(CommandHandler("checkpayos",  cmd_checkpayos))
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
    tg_app.add_handler(CallbackQueryHandler(handle_video_job_callback, pattern=r"^job\|"))
    tg_app.add_handler(CallbackQueryHandler(handle_pipeline_callback, pattern=r"^pipe\|"))
    tg_app.add_handler(CallbackQueryHandler(handle_trend_callback, pattern=r"^trend\|"))
    tg_app.add_handler(CallbackQueryHandler(handle_creative_callback, pattern=r"^creative\|"))
    tg_app.add_handler(CallbackQueryHandler(handle_task_callback, pattern=r"^task\|"))
    tg_app.add_handler(CallbackQueryHandler(handle_operator_menu_callback, pattern=r"^opmenu\|"))

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

# ─── OPERATOR API BRIDGE ─────────────────────────────────────────────────────
def verify_operator_api_token(request: Request):
    if not OPERATOR_API_TOKEN:
        raise HTTPException(status_code=503, detail="OPERATOR_API_TOKEN is not configured")
    auth = request.headers.get("authorization", "")
    bearer = auth.replace("Bearer ", "", 1).strip() if auth.lower().startswith("bearer ") else ""
    token = request.headers.get("x-operator-token") or bearer
    if not token or not hmac.compare_digest(str(token), OPERATOR_API_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid operator token")

@fastapi_app.get("/api/operator/tasks/next")
async def api_operator_next_task(request: Request, job_id: int = 0, tool: str = ""):
    verify_operator_api_token(request)
    task = next_worker_task(ADMIN_ID, job_id=job_id or None, tool=tool)
    if not task:
        return {"ok": True, "task": None, "message": "no queued task"}
    update_production_task(ADMIN_ID, task[0], status="working", note=f"api_worker_claim tool={tool or task[4] or '-'}")
    task = get_production_task(ADMIN_ID, task[0])
    return {
        "ok": True,
        "task": serialize_operator_task(task),
        "submit_url": f"/api/operator/tasks/{task[0]}/complete",
        "rule": "Submit output_url when the external AI/tool finishes. Do not publish without review gate.",
    }

@fastapi_app.post("/api/operator/tasks/{task_id}/complete")
async def api_operator_complete_task(task_id: int, payload: OperatorTaskCompleteRequest, request: Request):
    verify_operator_api_token(request)
    status = (payload.status or "ready").lower()
    allowed = {"queued", "working", "waiting", "ready", "blocked", "done", "cancelled"}
    if status not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {', '.join(sorted(allowed))}")
    task = get_production_task(ADMIN_ID, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    changed, row = update_production_task(ADMIN_ID, task_id, status=status, output_url=payload.output_url, note=payload.note)
    if not changed:
        raise HTTPException(status_code=400, detail="Task not updated")
    job_id, task_type = row
    if status in {"ready", "done"}:
        update_production_job(job_id, ADMIN_ID, status="working", note=f"api_task_complete:{task_id} {task_type} {status}")
    if status == "blocked":
        update_production_job(job_id, ADMIN_ID, status="blocked", note=f"api_task_blocked:{task_id} {payload.note}")
    updated_task = get_production_task(ADMIN_ID, task_id)
    readiness = production_readiness_data(ADMIN_ID, job_id)

    if tg_app and ADMIN_ID:
        try:
            await tg_app.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"🤖 <b>OPERATOR API TASK UPDATE</b>\n\n"
                    f"• Task: <code>#{task_id}</code> | Job: <code>#{job_id}</code>\n"
                    f"• Type: <code>{html.escape(task_type or '-')}</code> | Status: <b>{html.escape(status)}</b>\n"
                    f"• Output: <code>{html.escape(payload.output_url or 'không có')}</code>\n"
                    f"• Ready: <b>{html.escape((readiness or {}).get('level', 'UNKNOWN'))}</b>"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Operator API notify error: {e}")

    return {
        "ok": True,
        "task": serialize_operator_task(updated_task),
        "job_id": job_id,
        "readiness": {
            "level": (readiness or {}).get("level", "UNKNOWN"),
            "next_action": (readiness or {}).get("next_action", ""),
        },
    }

@fastapi_app.get("/api/operator/jobs/{job_id}/ready")
async def api_operator_job_ready(job_id: int, request: Request):
    verify_operator_api_token(request)
    readiness = production_readiness_data(ADMIN_ID, job_id)
    if not readiness:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "ok": True,
        "job_id": job_id,
        "level": readiness["level"],
        "next_action": readiness["next_action"],
        "checks": [
            {"key": key, "ok": ok, "detail": detail, "next": next_cmd}
            for key, ok, detail, next_cmd in readiness["checks"]
        ],
    }

@fastapi_app.post("/api/operator/loop")
async def api_operator_loop(payload: OperatorLoopRequest, request: Request):
    verify_operator_api_token(request)
    advanced, ready_publish, next_tasks, blocked = operator_loop_data(
        ADMIN_ID,
        limit=payload.limit,
        auto_queue=payload.auto_queue,
    )
    result = serialize_operator_loop_result(advanced, ready_publish, next_tasks, blocked)
    if payload.notify_admin and tg_app and ADMIN_ID:
        try:
            await tg_app.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    "🔁 <b>OPERATOR LOOP API</b>\n\n"
                    f"• Advanced: <b>{len(advanced)}</b>\n"
                    f"• Ready publish: <b>{len(ready_publish)}</b>\n"
                    f"• Next tasks: <b>{len(next_tasks)}</b>\n"
                    f"• Blocked/needs admin: <b>{len(blocked)}</b>\n\n"
                    "Xem chi tiết: <code>/operator_loop</code> hoặc <code>/operator_dashboard</code>"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Operator loop API notify error: {e}")
    return {
        "ok": True,
        "limit": payload.limit,
        "auto_queue": payload.auto_queue,
        **result,
    }

@fastapi_app.get("/api/operator/publish/next")
async def api_operator_publish_next(request: Request, platform: str = "", mode: str = ""):
    verify_operator_api_token(request)
    item = next_publish_queue_item(ADMIN_ID, platform=platform, mode=mode)
    if not item:
        return {"ok": True, "queue": None, "message": "no queued publish item"}
    queue_id = item[0]
    update_publish_queue_item(ADMIN_ID, queue_id, status="publishing", note=f"api_publisher_claim platform={platform or item[3] or '-'}")
    item = get_publish_queue_item(ADMIN_ID, queue_id)
    return {
        "ok": True,
        "queue": serialize_publish_queue_item(item),
        "submit_url": f"/api/operator/publish/{queue_id}/complete",
        "rule": "Return publish_url after posting. If blocked by platform/compliance, submit status=blocked and note.",
    }

@fastapi_app.post("/api/operator/publish/{queue_id}/complete")
async def api_operator_publish_complete(queue_id: int, payload: OperatorPublishCompleteRequest, request: Request):
    verify_operator_api_token(request)
    status = (payload.status or "published").lower()
    allowed = {"published", "blocked", "scheduled", "cancelled", "queued"}
    if status not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {', '.join(sorted(allowed))}")
    item = get_publish_queue_item(ADMIN_ID, queue_id)
    if not item:
        raise HTTPException(status_code=404, detail="Publish queue item not found")
    changed, job_id = update_publish_queue_item(ADMIN_ID, queue_id, status=status, publish_url=payload.publish_url, note=payload.note)
    if not changed:
        raise HTTPException(status_code=400, detail="Publish queue not updated")
    if status == "published":
        update_production_job(job_id, ADMIN_ID, stage="done", status="published", note=payload.note or "api_publish_complete", publish_url=payload.publish_url)
        add_performance_event(ADMIN_ID, job_id, "publish", 1, 0, payload.note or f"queue:{queue_id}")
        if payload.views > 0:
            add_performance_event(ADMIN_ID, job_id, "view", payload.views, 0, "api_initial_views")
        if payload.clicks > 0:
            add_performance_event(ADMIN_ID, job_id, "click", payload.clicks, 0, "api_initial_clicks")
    elif status == "blocked":
        update_production_job(job_id, ADMIN_ID, status="blocked", note=payload.note or f"publish_queue:{queue_id} blocked")
    elif status == "scheduled":
        update_production_job(job_id, ADMIN_ID, stage="publish", status="queued", note=payload.note or f"publish_queue:{queue_id} scheduled")

    updated = get_publish_queue_item(ADMIN_ID, queue_id)
    if tg_app and ADMIN_ID:
        try:
            await tg_app.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"📡 <b>OPERATOR API PUBLISH UPDATE</b>\n\n"
                    f"• Queue: <code>#{queue_id}</code> | Job: <code>#{job_id}</code>\n"
                    f"• Status: <b>{html.escape(status)}</b>\n"
                    f"• URL: <code>{html.escape(payload.publish_url or 'không có')}</code>\n"
                    f"• Views/clicks: <b>{payload.views}</b>/<b>{payload.clicks}</b>\n"
                    f"• Note: {html.escape(payload.note or '-')}"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Operator publish notify error: {e}")
    return {
        "ok": True,
        "queue": serialize_publish_queue_item(updated),
        "job_id": job_id,
    }

@fastapi_app.post("/api/operator/performance")
async def api_operator_performance(payload: OperatorPerformanceRequest, request: Request):
    verify_operator_api_token(request)
    event_type = (payload.event_type or "click").lower()
    allowed = {"view", "click", "order", "revenue", "lead", "publish", "cost"}
    if event_type not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid event_type. Allowed: {', '.join(sorted(allowed))}")
    note = f"{payload.source}: {payload.note}".strip(": ")
    ok, job = add_performance_event(
        ADMIN_ID,
        payload.job_id,
        event_type,
        payload.value,
        payload.amount,
        note,
        payload.variant_id,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Job or variant not found")
    if event_type in {"revenue", "order", "lead"} and payload.amount > 0:
        update_production_job(payload.job_id, ADMIN_ID, status="published", note=f"api_performance:{event_type} amount={payload.amount}")

    if tg_app and ADMIN_ID and (event_type in {"order", "revenue", "lead"} or payload.amount > 0):
        try:
            await tg_app.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"💰 <b>OPERATOR PERFORMANCE API</b>\n\n"
                    f"• Job: <code>#{payload.job_id}</code> | Variant: <code>{payload.variant_id or '-'}</code>\n"
                    f"• Type: <code>{html.escape(event_type)}</code> | Value: <b>{payload.value}</b>\n"
                    f"• Amount: <b>{payload.amount:,}đ</b>\n"
                    f"• Source: <code>{html.escape(payload.source or 'api')}</code>\n"
                    f"• Note: {html.escape(payload.note or '-')}"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Operator performance notify error: {e}")
    return {
        "ok": True,
        "job_id": payload.job_id,
        "event_type": event_type,
        "value": payload.value,
        "amount": payload.amount,
        "variant_id": payload.variant_id,
    }

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
