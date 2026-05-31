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
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
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
AFFILIATE_POSTBACK_TOKEN = _env("AFFILIATE_POSTBACK_TOKEN")

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
    c.execute("""CREATE TABLE IF NOT EXISTS tool_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id TEXT,
        stage TEXT,
        tool_name TEXT,
        event_type TEXT,
        severity TEXT,
        job_id INTEGER DEFAULT 0,
        task_id INTEGER DEFAULT 0,
        fallback_tool TEXT,
        message TEXT,
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
        "tool_events": [
            ("stage", "TEXT"),
            ("tool_name", "TEXT"),
            ("event_type", "TEXT"),
            ("severity", "TEXT"),
            ("job_id", "INTEGER DEFAULT 0"),
            ("task_id", "INTEGER DEFAULT 0"),
            ("fallback_tool", "TEXT"),
            ("message", "TEXT"),
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

def find_matching_campaign(owner_id, niche="", platform=""):
    rows = list_campaigns(owner_id, limit=50)
    active_rows = [row for row in rows if (row[5] or "active") == "active"]
    if not active_rows:
        return None, 0
    query = f"{niche or ''} {platform or ''}".lower()
    best = None
    best_score = -1
    for row in active_rows:
        cid, name, campaign_niche, platforms, affiliate_url, status = row
        text = f"{name or ''} {campaign_niche or ''} {platforms or ''}".lower()
        score = 0
        for token in tokenize_text(query)[:30]:
            if token and token in text:
                score += 8
        if platform and platform.lower() in (platforms or "").lower():
            score += 25
        if niche and (niche or "").lower() in text:
            score += 25
        if affiliate_url:
            score += 3
        if score > best_score:
            best = row
            best_score = score
    return best, max(best_score, 0)

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

DEFAULT_AFFILIATE_LINKS = [
    {
        "network": "GoEco",
        "product_name": "VPBank",
        "niche": "tai chinh ngan hang",
        "url": "https://goecom.asia/Z31Vp7Ad",
        "target_audience": "nguoi can tai khoan ngan hang, the, uu dai tai chinh ca nhan",
        "product_score": 78,
    },
    {
        "network": "GoEco",
        "product_name": "Shopee",
        "niche": "san thuong mai dien tu",
        "url": "https://goeco.mobi/GJPRlrH3",
        "target_audience": "nguoi mua online, san deal, do cong nghe va do gia dung",
        "product_score": 82,
    },
    {
        "network": "GoEco",
        "product_name": "Lazada",
        "niche": "san thuong mai dien tu",
        "url": "https://goeco.mobi/Ao8zhi5N",
        "target_audience": "nguoi mua online, san voucher, do cong nghe va tieu dung",
        "product_score": 82,
    },
    {
        "network": "GoEco",
        "product_name": "Traveloka",
        "niche": "du lich booking",
        "url": "https://goeco.mobi/UbHEhUul",
        "target_audience": "nguoi dat ve may bay, khach san, du lich tu tuc",
        "product_score": 74,
    },
    {
        "network": "TrackFin",
        "product_name": "TikTok",
        "niche": "social commerce tiktok affiliate",
        "url": "https://trackfin.asia/J5X2hWfu",
        "target_audience": "creator, nguoi ban hang, nguoi mua san pham tren tiktok",
        "product_score": 84,
    },
    {
        "network": "Attracking",
        "product_name": "MSB Bank",
        "niche": "tai chinh ngan hang",
        "url": "https://attracking.asia/TfNc2dfN",
        "target_audience": "nguoi can tai khoan ngan hang, the, uu dai tai chinh ca nhan",
        "product_score": 74,
    },
    {
        "network": "TrackEC",
        "product_name": "Mam Nam Ngu",
        "niche": "hang tieu dung gia dinh",
        "url": "https://trackec.asia/x6H5baXh",
        "target_audience": "noi tro, gia dinh, nguoi mua hang tieu dung",
        "product_score": 68,
    },
    {
        "network": "Attracking",
        "product_name": "BIDV",
        "niche": "tai chinh ngan hang",
        "url": "https://attracking.asia/jaUg5JFT",
        "target_audience": "nguoi can tai khoan ngan hang, the, uu dai tai chinh ca nhan",
        "product_score": 76,
    },
    {
        "network": "Attracking",
        "product_name": "MBBank",
        "niche": "tai chinh ngan hang",
        "url": "https://attracking.asia/eVBScXBZ",
        "target_audience": "nguoi can tai khoan ngan hang, the, app ngan hang so",
        "product_score": 78,
    },
    {
        "network": "TrackEC",
        "product_name": "VPBank Ho Kinh Doanh",
        "niche": "tai chinh doanh nghiep nho",
        "url": "https://trackec.asia/xMdFNmSa",
        "target_audience": "chu shop, ho kinh doanh, nguoi ban hang online",
        "product_score": 77,
    },
    {
        "network": "TrackMobi",
        "product_name": "Hong Leong Bank",
        "niche": "tai chinh ngan hang",
        "url": "https://trackmobi.asia/ss183PMu",
        "target_audience": "nguoi can tai khoan ngan hang va uu dai tai chinh",
        "product_score": 72,
    },
    {
        "network": "ShortenAsia",
        "product_name": "Zalo Ads",
        "niche": "quang cao marketing",
        "url": "https://shorten.asia/SBPDCn5x",
        "target_audience": "chu shop, doanh nghiep nho, nguoi chay quang cao",
        "product_score": 78,
    },
    {
        "network": "ShortenAsia",
        "product_name": "ShopDunk Web",
        "niche": "dien thoai cong nghe",
        "url": "https://shorten.asia/TFbjeqe8",
        "target_audience": "nguoi mua iphone, ipad, phu kien apple",
        "product_score": 80,
    },
    {
        "network": "TrackFin",
        "product_name": "Giay Shondo",
        "niche": "thoi trang giay dep",
        "url": "https://trackfin.asia/W7d7w4EX",
        "target_audience": "nguoi mua giay dep, thoi trang hang ngay",
        "product_score": 70,
    },
    {
        "network": "TrackEC",
        "product_name": "Savani",
        "niche": "thoi trang",
        "url": "https://trackec.asia/Udse3MbB",
        "target_audience": "nguoi mua quan ao cong so, thoi trang gia dinh",
        "product_score": 70,
    },
    {
        "network": "Attracking",
        "product_name": "Lazada Referral",
        "niche": "san thuong mai dien tu referral",
        "url": "https://attracking.asia/YUVK7hBs",
        "target_audience": "nguoi mua online, san voucher, nguoi moi dung lazada",
        "product_score": 80,
    },
    {
        "network": "ShortenAsia",
        "product_name": "AEON eShop",
        "niche": "san thuong mai dien tu hang tieu dung",
        "url": "https://shorten.asia/1JdwRvYt",
        "target_audience": "gia dinh, nguoi mua hang sieu thi online",
        "product_score": 72,
    },
    {
        "network": "GoEcom",
        "product_name": "Hoang Ha Mobile",
        "niche": "dien thoai cong nghe",
        "url": "https://goecom.asia/wnMFwYsF",
        "target_audience": "nguoi mua dien thoai, laptop, phu kien cong nghe",
        "product_score": 82,
    },
    {
        "network": "TrackFin",
        "product_name": "TikTok For Business",
        "niche": "quang cao marketing tiktok",
        "url": "https://trackfin.asia/c413qgqe",
        "target_audience": "chu shop, creator, doanh nghiep can chay quang cao tiktok",
        "product_score": 83,
    },
    {
        "network": "TrackFin",
        "product_name": "Chickita Voucher",
        "niche": "voucher hang tieu dung",
        "url": "https://trackfin.asia/N9sa43Xv",
        "target_audience": "nguoi san voucher, me va be, gia dinh",
        "product_score": 66,
    },
    {
        "network": "TrackEcom",
        "product_name": "Samsung Student",
        "niche": "dien thoai cong nghe sinh vien",
        "url": "https://trackecom.asia/YbBhQ2pq",
        "target_audience": "sinh vien, nguoi mua dien thoai laptop samsung",
        "product_score": 82,
    },
    {
        "network": "ShortenAsia",
        "product_name": "CellphoneS",
        "niche": "dien thoai cong nghe",
        "url": "https://shorten.asia/1hyutcwN",
        "target_audience": "nguoi mua dien thoai, laptop, phu kien cong nghe",
        "product_score": 82,
    },
    {
        "network": "ShortenAsia",
        "product_name": "Dien Thoai Vui",
        "niche": "sua chua dien thoai cong nghe",
        "url": "https://shorten.asia/pPvvzj6X",
        "target_audience": "nguoi can sua dien thoai, thay pin, phu kien",
        "product_score": 76,
    },
    {
        "network": "TrackEcom",
        "product_name": "JOCKEY",
        "niche": "thoi trang do lot",
        "url": "https://trackecom.asia/VYp9XMEB",
        "target_audience": "nguoi mua do lot, do mac nha, lifestyle",
        "product_score": 70,
    },
    {
        "network": "TrackMobi",
        "product_name": "VERA",
        "niche": "thoi trang do lot",
        "url": "https://trackmobi.asia/fQRZdVyj",
        "target_audience": "phu nu, nguoi mua do lot va do mac nha",
        "product_score": 70,
    },
    {
        "network": "TrackFin",
        "product_name": "Vascara",
        "niche": "thoi trang giay tui",
        "url": "https://trackfin.asia/8uvHbKPp",
        "target_audience": "phu nu mua giay, tui xach, phu kien thoi trang",
        "product_score": 72,
    },
    {
        "network": "Attracking",
        "product_name": "Adidas Viet Nam Online",
        "niche": "thoi trang the thao",
        "url": "https://attracking.asia/GsQmmkz7",
        "target_audience": "nguoi tap luyen, mua giay va do the thao",
        "product_score": 78,
    },
    {
        "network": "TrackFin",
        "product_name": "SUPERSPORTS",
        "niche": "thoi trang the thao",
        "url": "https://trackfin.asia/9ueaXQH5",
        "target_audience": "nguoi tap luyen, mua do the thao va lifestyle",
        "product_score": 76,
    },
    {
        "network": "TrackMobi",
        "product_name": "Lazada Viet Nam VIP",
        "niche": "san thuong mai dien tu vip",
        "url": "https://trackmobi.asia/pdfM4UWt",
        "target_audience": "nguoi mua online, san voucher, khach hang lazada vip",
        "product_score": 82,
    },
    {
        "network": "ShortenAsia",
        "product_name": "Nguyen Kim",
        "niche": "dien may cong nghe gia dung",
        "url": "https://shorten.asia/xaE7DBsX",
        "target_audience": "gia dinh, nguoi mua dien may, do gia dung, thiet bi cong nghe",
        "commission_note": "brand=Nguyen Kim | family=dien may gia dung cong nghe | os=all",
        "product_score": 82,
    },
    {
        "network": "TrackEcom",
        "product_name": "JUNO",
        "niche": "thoi trang giay tui phu nu",
        "url": "https://trackecom.asia/uq3Z3zhF",
        "target_audience": "phu nu, dan van phong, nguoi mua giay tui thoi trang",
        "commission_note": "brand=JUNO | family=thoi trang giay tui | os=all",
        "product_score": 74,
    },
    {
        "network": "Attracking",
        "product_name": "BEN Computer",
        "niche": "may tinh laptop gaming cong nghe",
        "url": "https://attracking.asia/gzGJAWXZ",
        "target_audience": "sinh vien, dan van phong, game thu, nguoi mua laptop pc",
        "commission_note": "brand=BEN Computer | family=cong nghe laptop pc | os=all",
        "product_score": 82,
    },
    {
        "network": "Attracking",
        "product_name": "ELMICH",
        "niche": "do gia dung nha bep",
        "url": "https://attracking.asia/VU3B73xB",
        "target_audience": "gia dinh, noi tro, nguoi mua do bep va do gia dung",
        "commission_note": "brand=ELMICH | family=do gia dung nha bep | os=all",
        "product_score": 72,
    },
    {
        "network": "ShortenAsia",
        "product_name": "PNJ",
        "niche": "trang suc qua tang thoi trang",
        "url": "https://shorten.asia/JxpW7rgv",
        "target_audience": "nguoi mua trang suc, qua tang, cuoi hoi, phu kien cao cap",
        "commission_note": "brand=PNJ | family=trang suc qua tang | os=all",
        "product_score": 76,
    },
    {
        "network": "GoEcom",
        "product_name": "Lug",
        "niche": "vali balo du lich",
        "url": "https://goecom.asia/8F5QMNzs",
        "target_audience": "nguoi di du lich, dan van phong, sinh vien can vali balo",
        "commission_note": "brand=Lug | family=du lich vali balo | os=all",
        "product_score": 72,
    },
    {
        "network": "TrackEC",
        "product_name": "ACFC",
        "niche": "thoi trang lifestyle",
        "url": "https://trackec.asia/UQn56Ycp",
        "target_audience": "nguoi mua thoi trang, lifestyle, hang chinh hang",
        "commission_note": "brand=ACFC | family=thoi trang lifestyle | os=all",
        "product_score": 74,
    },
    {
        "network": "TrackFin",
        "product_name": "Con Cung",
        "niche": "me va be tieu dung gia dinh",
        "url": "https://trackfin.asia/cyrwNfdM",
        "target_audience": "me bim, gia dinh co tre nho, nguoi mua do me va be",
        "commission_note": "brand=Con Cung | family=me va be hang tieu dung | os=all",
        "product_score": 76,
    },
    {
        "network": "TrackFin",
        "product_name": "SAMSUNG",
        "niche": "dien thoai cong nghe dien may",
        "url": "https://trackfin.asia/vVv8KEHu",
        "target_audience": "nguoi mua smartphone, tablet, tv, do cong nghe samsung",
        "commission_note": "brand=Samsung | family=cong nghe dien thoai dien may | os=all",
        "product_score": 84,
    },
    {
        "network": "GoEcom",
        "product_name": "MediaMart",
        "niche": "dien may cong nghe gia dung",
        "url": "https://goecom.asia/4GGZ8meW",
        "target_audience": "gia dinh, nguoi mua dien may, tv, tu lanh, may giat",
        "commission_note": "brand=MediaMart | family=dien may gia dung cong nghe | os=all",
        "product_score": 80,
    },
    {
        "network": "TrackFin",
        "product_name": "Biti's",
        "niche": "thoi trang giay dep",
        "url": "https://trackfin.asia/7wamMsFq",
        "target_audience": "nguoi mua giay dep, hoc sinh sinh vien, gia dinh",
        "commission_note": "brand=Bitis | family=thoi trang giay dep | os=all",
        "product_score": 76,
    },
    {
        "network": "TrackFin",
        "product_name": "HDBank The Tin Dung",
        "niche": "tai chinh ngan hang the tin dung",
        "url": "https://trackfin.asia/SHXY6qMT",
        "target_audience": "nguoi can the tin dung, uu dai chi tieu, tai chinh ca nhan",
        "commission_note": "brand=HDBank | family=tai chinh the tin dung | os=all",
        "product_score": 76,
    },
    {
        "network": "GoEcom",
        "product_name": "AppMax Vay Nhanh Max Card",
        "niche": "tai chinh vay nhanh the",
        "url": "https://goecom.asia/QYPZrGrU",
        "target_audience": "nguoi can vay, the, giai phap tai chinh ca nhan",
        "commission_note": "brand=AppMax | family=tai chinh vay the | os=all",
        "product_score": 72,
    },
    {
        "network": "Attracking",
        "product_name": "VIB AppMax The Thanh Toan",
        "niche": "tai chinh ngan hang the thanh toan",
        "url": "https://attracking.asia/AJSh3W9U",
        "target_audience": "nguoi can the thanh toan, app ngan hang, tai chinh ca nhan",
        "commission_note": "brand=VIB AppMax | family=tai chinh ngan hang the | os=all",
        "product_score": 76,
    },
    {
        "network": "GoEcom",
        "product_name": "Cathay United Bank Android",
        "niche": "tai chinh ngan hang app android",
        "url": "https://goecom.asia/5pKeXgNU",
        "target_audience": "nguoi dung android can ngan hang, the, tai chinh ca nhan",
        "commission_note": "brand=Cathay United Bank | family=tai chinh ngan hang app | os=android | pair=ios",
        "product_score": 76,
    },
    {
        "network": "GoEcom",
        "product_name": "Cathay United Bank iOS",
        "niche": "tai chinh ngan hang app ios iphone",
        "url": "https://goecom.asia/WWHZMPKm",
        "target_audience": "nguoi dung iphone ios can ngan hang, the, tai chinh ca nhan",
        "commission_note": "brand=Cathay United Bank | family=tai chinh ngan hang app | os=ios | pair=android",
        "product_score": 76,
    },
    {
        "network": "ShortenAsia",
        "product_name": "Bao Hiem Hung Vuong",
        "niche": "bao hiem tai chinh",
        "url": "https://shorten.asia/gSrcTngW",
        "target_audience": "nguoi can bao hiem, gia dinh, chu xe, tai chinh an toan",
        "commission_note": "brand=Bao Hiem Hung Vuong | family=bao hiem tai chinh | os=all",
        "product_score": 70,
    },
    {
        "network": "Attracking",
        "product_name": "Liobank The Va Vay",
        "niche": "tai chinh ngan hang the vay",
        "url": "https://attracking.asia/jRG236hs",
        "target_audience": "nguoi can the, vay, app ngan hang so",
        "commission_note": "brand=Liobank | family=tai chinh ngan hang the vay | os=all",
        "product_score": 74,
    },
    {
        "network": "TrackEC",
        "product_name": "VPBank The Direct",
        "niche": "tai chinh ngan hang the",
        "url": "https://trackec.asia/s6sWSVKG",
        "target_audience": "nguoi can the ngan hang, uu dai thanh toan, tai chinh ca nhan",
        "commission_note": "brand=VPBank | family=tai chinh ngan hang the | os=all",
        "product_score": 78,
    },
    {
        "network": "TrackEC",
        "product_name": "Lotte Finance",
        "niche": "tai chinh vay tieu dung",
        "url": "https://trackec.asia/TGGjCWA2",
        "target_audience": "nguoi can vay tieu dung, tai chinh ca nhan",
        "commission_note": "brand=Lotte Finance | family=tai chinh vay tieu dung | os=all",
        "product_score": 72,
    },
    {
        "network": "Attracking",
        "product_name": "VPBank 3T The Tin Dung",
        "niche": "tai chinh ngan hang the tin dung",
        "url": "https://attracking.asia/CGxE1aYN",
        "target_audience": "nguoi can the tin dung, uu dai chi tieu, khach hang vpbank",
        "commission_note": "brand=VPBank | family=tai chinh the tin dung | os=all",
        "product_score": 78,
    },
    {
        "network": "Attracking",
        "product_name": "VPBank SENID Mo The",
        "niche": "tai chinh ngan hang the",
        "url": "https://attracking.asia/pjdNn2EA",
        "target_audience": "nguoi can mo the vpbank, tai chinh ca nhan",
        "commission_note": "brand=VPBank | family=tai chinh ngan hang the | os=all",
        "product_score": 77,
    },
    {
        "network": "ShortenAsia",
        "product_name": "HomeCredit Cash Loan",
        "niche": "tai chinh vay tieu dung",
        "url": "https://shorten.asia/P6SstnNY",
        "target_audience": "nguoi can vay tien mat, tai chinh ca nhan",
        "commission_note": "brand=HomeCredit | family=tai chinh vay tieu dung | os=all",
        "product_score": 72,
    },
    {
        "network": "TrackFin",
        "product_name": "VIB The Tin Dung",
        "niche": "tai chinh ngan hang the tin dung",
        "url": "https://trackfin.asia/UPbWDCPC",
        "target_audience": "nguoi can the tin dung, uu dai hoan tien, chi tieu ca nhan",
        "commission_note": "brand=VIB | family=tai chinh ngan hang the tin dung | os=all",
        "product_score": 78,
    },
    {
        "network": "TrackEcom",
        "product_name": "Tima",
        "niche": "tai chinh vay",
        "url": "https://trackecom.asia/KuBZKykJ",
        "target_audience": "nguoi can vay, tu van tai chinh ca nhan",
        "commission_note": "brand=Tima | family=tai chinh vay | os=all",
        "product_score": 70,
    },
    {
        "network": "Attracking",
        "product_name": "Bao Minh",
        "niche": "bao hiem tai chinh",
        "url": "https://attracking.asia/cnuDXMgD",
        "target_audience": "nguoi can bao hiem, gia dinh, chu xe, tai chinh an toan",
        "commission_note": "brand=Bao Minh | family=bao hiem tai chinh | os=all",
        "product_score": 70,
    },
    {
        "network": "TrackFin",
        "product_name": "EVOCARD The Tin Dung",
        "niche": "tai chinh the tin dung",
        "url": "https://trackfin.asia/wmqm9WMB",
        "target_audience": "nguoi can the tin dung, uu dai chi tieu, tai chinh ca nhan",
        "commission_note": "brand=EVOCARD | family=tai chinh the tin dung | os=all",
        "product_score": 72,
    },
    {
        "network": "TrackMobi",
        "product_name": "Ve May Bay",
        "niche": "du lich ve may bay",
        "url": "https://trackmobi.asia/f5vK6kWh",
        "target_audience": "nguoi dat ve may bay, du lich tu tuc, cong tac",
        "commission_note": "brand=Ve May Bay | family=du lich ve may bay | os=all",
        "product_score": 74,
    },
    {
        "network": "Attracking",
        "product_name": "Xanh SM Tuyen Tai Xe Xe May",
        "niche": "viec lam giao thong cong nghe",
        "url": "https://attracking.asia/mhGF3BVF",
        "target_audience": "nguoi tim viec tai xe, shipper, xe may cong nghe",
        "commission_note": "brand=Xanh SM | family=viec lam tai xe giao thong | os=all",
        "product_score": 74,
    },
    {
        "network": "TrackFin",
        "product_name": "BestPrice",
        "niche": "du lich khach san ve may bay tour",
        "url": "https://trackfin.asia/V9G8j3Gs",
        "target_audience": "nguoi dat phong, ve may bay, tour du lich, gia dinh di choi",
        "commission_note": "brand=BestPrice | family=du lich booking tour ve may bay khach san | os=all",
        "product_score": 78,
    },
    {
        "network": "Attracking",
        "product_name": "Vietnam Airlines",
        "niche": "du lich hang khong ve may bay",
        "url": "https://attracking.asia/xaqY9Mcq",
        "target_audience": "nguoi dat ve may bay, cong tac, du lich gia dinh",
        "commission_note": "brand=Vietnam Airlines | family=du lich hang khong ve may bay | os=all",
        "product_score": 80,
    },
    {
        "network": "Attracking",
        "product_name": "VinWonders Website",
        "niche": "du lich giai tri ve tham quan",
        "url": "https://attracking.asia/6PBPz15b",
        "target_audience": "gia dinh, khach du lich, nguoi mua ve vui choi giai tri",
        "commission_note": "brand=VinWonders | family=du lich giai tri ve tham quan | os=all",
        "product_score": 76,
    },
    {
        "network": "ShortenAsia",
        "product_name": "Ve Gia Re",
        "niche": "du lich ve may bay gia re",
        "url": "https://shorten.asia/7E5yK36E",
        "target_audience": "nguoi san ve re, du lich tu tuc, sinh vien, gia dinh",
        "commission_note": "brand=Ve Gia Re | family=du lich ve may bay | os=all",
        "product_score": 74,
    },
    {
        "network": "TrackFin",
        "product_name": "GOTADI Ve May Bay",
        "niche": "du lich ve may bay booking",
        "url": "https://trackfin.asia/C2wmhSqG",
        "target_audience": "nguoi dat ve may bay, du lich, cong tac",
        "commission_note": "brand=GOTADI | family=du lich ve may bay booking | os=all",
        "product_score": 76,
    },
    {
        "network": "TrackMobi",
        "product_name": "ATADI Dat Ve May Bay",
        "niche": "du lich ve may bay booking",
        "url": "https://trackmobi.asia/nbv6ZXPa",
        "target_audience": "nguoi dat ve may bay online, du lich, cong tac",
        "commission_note": "brand=ATADI | family=du lich ve may bay booking | os=all",
        "product_score": 76,
    },
    {
        "network": "TrackFin",
        "product_name": "Klook SIM Ve Tham Quan Tour",
        "niche": "du lich tour sim ve tham quan",
        "url": "https://trackfin.asia/pagx7bx2",
        "target_audience": "nguoi di du lich tu tuc, mua sim, ve tham quan, tour, van chuyen",
        "commission_note": "brand=Klook | family=du lich tour sim ve tham quan van chuyen | os=all",
        "product_score": 80,
    },
]

DEFAULT_AFFILIATE_ALLOWED_CLAIMS = (
    "Gioi thieu uu dai, so sanh tinh nang, neu trai nghiem va huong dan mua hang minh bach."
)
DEFAULT_AFFILIATE_BLOCKED_CLAIMS = (
    "Khong cam ket duyet ho so, khong cam ket loi nhuan/thu nhap, khong mao danh thuong hieu, khong spam, khong noi sai chinh sach."
)

def get_affiliate_by_url(owner_id, url):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "SELECT id, network, product_name, url FROM affiliate_links WHERE owner_id=? AND url=? LIMIT 1",
        (str(owner_id), url)
    )
    row = c.fetchone()
    conn.close()
    return row

def seed_default_affiliate_links(owner_id):
    created = []
    skipped = []
    for item in DEFAULT_AFFILIATE_LINKS:
        url = item["url"].strip()
        existing = get_affiliate_by_url(owner_id, url)
        if existing:
            skipped.append(existing)
            continue
        affiliate_id = create_affiliate_link(
            owner_id,
            item["network"],
            item["product_name"],
            item["niche"],
            url,
            item.get("commission_note") or "Affiliate link moi dang ky tu admin.",
            0,
            0,
            item.get("target_audience", ""),
            DEFAULT_AFFILIATE_ALLOWED_CLAIMS,
            DEFAULT_AFFILIATE_BLOCKED_CLAIMS,
            item.get("product_score", 0),
        )
        created.append((affiliate_id, item["network"], item["product_name"], url))
    return created, skipped

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

def public_tracking_base_url():
    return (PUBLIC_BASE_URL or "").rstrip("/")

def affiliate_tracking_url(affiliate_id, job_id=0, source=""):
    base_url = public_tracking_base_url()
    if not base_url or not affiliate_id:
        return ""
    query = {}
    if job_id:
        query["job"] = int(job_id)
    if source:
        query["src"] = str(source)[:80]
    suffix = f"?{urlencode(query)}" if query else ""
    return f"{base_url}/r/{int(affiliate_id)}{suffix}"

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

def affiliate_search_blob(affiliate):
    (
        aid, network, product_name, aff_niche, url, commission_note, status,
        price_vnd, commission_rate, target_audience, allowed_claims, blocked_claims, product_score
    ) = affiliate
    return " ".join([
        str(network or ""),
        str(product_name or ""),
        str(aff_niche or ""),
        str(commission_note or ""),
        str(target_audience or ""),
    ]).lower()

def extract_affiliate_brand_hint(text):
    text = text or ""
    match = re.search(r"brand\s*=\s*([^|,;\n]+)", text, flags=re.I)
    if match:
        return match.group(1).strip()
    return ""

def affiliate_family_tokens(affiliate):
    blob = affiliate_search_blob(affiliate)
    groups = {
        "finance": ["tai", "chinh", "ngan", "hang", "the", "vay", "credit", "bank", "loan", "bao", "hiem"],
        "travel": ["du", "lich", "tour", "ve", "may", "bay", "khach", "san", "booking", "sim", "tham", "quan"],
        "tech": ["cong", "nghe", "dien", "thoai", "laptop", "pc", "may", "tinh", "samsung", "iphone", "apple"],
        "ecommerce": ["san", "thuong", "mai", "voucher", "deal", "mua", "online", "eshop"],
        "fashion": ["thoi", "trang", "giay", "tui", "dep", "juno", "adidas", "vascara", "jockey", "vera"],
        "home": ["gia", "dung", "dien", "may", "nha", "bep", "noi", "tro", "elmich"],
        "mom_baby": ["me", "be", "con", "cung", "tre", "nho"],
    }
    found = set()
    for family, tokens in groups.items():
        if any(token in blob for token in tokens):
            found.add(family)
    return found

def score_related_affiliate(base_affiliate, candidate, brand_query="", niche_query=""):
    if not candidate or (candidate[6] or "active") != "active":
        return 0, []
    if base_affiliate and candidate[0] == base_affiliate[0]:
        return 0, []

    base_blob = affiliate_search_blob(base_affiliate) if base_affiliate else ""
    cand_blob = affiliate_search_blob(candidate)
    query_blob = f"{brand_query or ''} {niche_query or ''}".lower()
    score = 0
    reasons = []

    brand_hint = extract_affiliate_brand_hint(base_blob) or brand_query
    if brand_hint and brand_hint.lower() in cand_blob:
        score += 60
        reasons.append(f"cùng brand {brand_hint}")

    base_tokens = set(tokenize_text(base_blob + " " + query_blob)[:80])
    cand_tokens = set(tokenize_text(cand_blob)[:80])
    overlap = sorted((base_tokens & cand_tokens) - {"affiliate", "link", "brand", "family", "all"})
    if overlap:
        score += min(40, len(overlap) * 5)
        reasons.append("trùng từ khóa: " + ", ".join(overlap[:5]))

    families = affiliate_family_tokens(base_affiliate) if base_affiliate else set()
    query_family = affiliate_family_tokens((0, "", niche_query, niche_query, "", query_blob, "active", 0, 0, "", "", "", 0)) if niche_query else set()
    family_overlap = (families | query_family) & affiliate_family_tokens(candidate)
    if family_overlap:
        score += 22
        reasons.append("cùng nhóm: " + ", ".join(sorted(family_overlap)))

    if "android" in (base_blob + query_blob) and "ios" in cand_blob:
        score += 35
        reasons.append("bổ sung link iOS")
    if ("ios" in base_blob or "iphone" in base_blob or "iphone" in query_blob) and "android" in cand_blob:
        score += 35
        reasons.append("bổ sung link Android")

    return score, reasons

def list_related_affiliate_links(owner_id, affiliate_id=0, brand="", niche="", limit=12):
    base = get_affiliate_link(affiliate_id, owner_id) if affiliate_id else None
    rows = list_affiliate_links(owner_id, limit=300)
    ranked = []
    for row in rows:
        score, reasons = score_related_affiliate(base, row, brand, niche)
        if score > 0:
            ranked.append((score, reasons, row))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[:limit]

def format_related_affiliate_links(related, max_items=8):
    lines = []
    for score, reasons, row in related[:max_items]:
        aid, network, product_name, aff_niche, url, *_ = row
        reason_text = "; ".join(reasons[:2]) if reasons else f"score={score}"
        lines.append(f"#{aid} | {network or '-'} | {product_name or '-'} | {url or '-'} | {reason_text}")
    return "\n".join(lines)

def fallback_affiliate_video_ideas(affiliate, platform="tiktok", limit=5):
    (
        aid, network, product_name, niche, url, commission_note, status,
        price_vnd, commission_rate, target_audience, allowed_claims, blocked_claims, product_score
    ) = affiliate
    product = product_name or "sản phẩm affiliate"
    audience = target_audience or "người mua online"
    platform = platform or "tiktok"
    templates = [
        (
            f"3 lỗi thường gặp khi chọn {product}",
            f"mở bằng vấn đề thật của {audience}, demo cách tránh lỗi, CTA xem link nếu phù hợp",
            "problem -> quick checklist -> soft CTA",
        ),
        (
            f"So sánh nhanh {product} cho người mới",
            "đặt 2-3 tiêu chí chọn mua, không phóng đại kết quả, chốt bằng tiêu chí tự kiểm tra",
            "comparison -> buying criteria -> disclosure",
        ),
        (
            f"Checklist trước khi dùng {product}",
            "dùng dạng checklist lưu lại được, ưu tiên minh bạch điều kiện/chi phí/chính sách",
            "checklist -> common traps -> CTA",
        ),
        (
            f"Một tình huống đời thường cần {product}",
            "kể tình huống ngắn, đưa sản phẩm như một lựa chọn, không ép mua",
            "story -> use case -> link placement",
        ),
        (
            f"Review thật lòng: {product} hợp với ai?",
            "nêu ai nên dùng, ai không nên dùng, minh bạch đây là affiliate",
            "fit/not-fit -> pros/limits -> affiliate disclosure",
        ),
    ]
    ideas = []
    for idx, (hook, angle, structure) in enumerate(templates[:limit], 1):
        ideas.append(
            f"{idx}. Hook: {hook}\n"
            f"   Góc làm: {angle}\n"
            f"   Format: {structure}\n"
            f"   Nền tảng: {platform}\n"
            f"   CTA: Xem link {product} trong bio/mô tả nếu phù hợp nhu cầu."
        )
    return "\n\n".join(ideas)

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

def operator_status_data(owner_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM social_channels WHERE owner_id=? AND status='active'", (str(owner_id),))
    active_channels = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM affiliate_links WHERE owner_id=? AND status='active'", (str(owner_id),))
    active_affiliates = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM campaigns WHERE owner_id=? AND status='active'", (str(owner_id),))
    active_campaigns = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM production_jobs WHERE owner_id=? AND status IN ('queued','working','waiting','blocked','ready')", (str(owner_id),))
    open_jobs = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM production_tasks WHERE owner_id=? AND status IN ('queued','waiting','working','blocked')", (str(owner_id),))
    open_tasks = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM publish_queue WHERE owner_id=? AND status IN ('queued','scheduled','publishing','blocked')", (str(owner_id),))
    open_publish = c.fetchone()[0]
    c.execute(
        """SELECT id, platform, channel_name, account_label, status, publish_mode, token_env, page_id
        FROM social_channels WHERE owner_id=? AND status='active' ORDER BY id DESC LIMIT 20""",
        (str(owner_id),)
    )
    channel_rows = c.fetchall()
    c.execute(
        """SELECT pj.id, pj.stage, pj.status, pj.platform, pj.topic, sc.channel_name, al.product_name, pj.updated_at
        FROM production_jobs pj
        LEFT JOIN social_channels sc ON sc.id=pj.channel_id
        LEFT JOIN affiliate_links al ON al.id=pj.affiliate_id
        WHERE pj.owner_id=? AND pj.status='blocked'
        ORDER BY pj.updated_at DESC LIMIT 8""",
        (str(owner_id),)
    )
    blocked_jobs = c.fetchall()
    conn.close()
    channel_readiness = []
    for row in channel_rows:
        readiness, reason = channel_publish_readiness(row)
        channel_readiness.append((row, readiness, reason))
    checks = [
        ("channels", active_channels > 0, f"{active_channels} kênh active", "/channel_add platform=tiktok name=..."),
        ("affiliates", active_affiliates > 0, f"{active_affiliates} affiliate active", "/affiliate_seed hoặc /affiliate_add"),
        ("campaigns", active_campaigns > 0, f"{active_campaigns} campaign active", "/campaign_new name=... niche=..."),
        ("operator_api", bool(OPERATOR_API_TOKEN), "OPERATOR_API_TOKEN đã bật" if OPERATOR_API_TOKEN else "OPERATOR_API_TOKEN chưa set", "/operator_api"),
        ("publish_ready", any(r in {"manual_ready", "api_ready"} for _, r, _ in channel_readiness), "Có kênh sẵn sàng đăng" if channel_readiness else "Chưa có kênh", "/publish_readiness"),
    ]
    ready_to_scale = all(ok for key, ok, _, _ in checks[:3])
    return {
        "counts": {
            "active_channels": active_channels,
            "active_affiliates": active_affiliates,
            "active_campaigns": active_campaigns,
            "open_jobs": open_jobs,
            "open_tasks": open_tasks,
            "open_publish": open_publish,
        },
        "checks": checks,
        "ready_to_scale": ready_to_scale,
        "channel_readiness": channel_readiness,
        "blocked_jobs": blocked_jobs,
    }

def publisher_status_data(owner_id):
    channel_rows = list_social_publish_readiness(owner_id)
    channels = []
    counts = {
        "manual_ready": 0,
        "api_ready": 0,
        "manual_required": 0,
        "missing_token_env": 0,
        "missing_secret": 0,
        "missing_page_id": 0,
        "blocked": 0,
    }
    for row in channel_rows:
        cid, platform, channel_name, account_label, status, publish_mode, token_env, page_id = row
        readiness, reason = channel_publish_readiness(row)
        counts[readiness] = counts.get(readiness, 0) + 1
        channels.append({
            "id": cid,
            "platform": platform,
            "channel_name": channel_name,
            "account_label": account_label,
            "status": status,
            "publish_mode": publish_mode or "manual",
            "token_env": token_env,
            "page_id": page_id,
            "readiness": readiness,
            "reason": reason,
            "can_manual_publish": readiness in {"manual_ready", "api_ready", "manual_required"},
            "can_api_publish": readiness == "api_ready",
        })

    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT pq.status, COALESCE(pq.platform,''), COALESCE(pq.mode,''), COUNT(*)
        FROM publish_queue pq
        WHERE pq.owner_id=?
        GROUP BY pq.status, pq.platform, pq.mode
        ORDER BY pq.status, pq.platform, pq.mode""",
        (str(owner_id),)
    )
    queue_counts = [
        {"status": status, "platform": platform, "mode": mode, "count": count}
        for status, platform, mode, count in c.fetchall()
    ]
    c.execute(
        """SELECT pq.id, pq.job_id, pq.platform, pq.mode, pq.status, pq.scheduled_at,
                  sc.channel_name, sc.account_label, pj.topic, pj.asset_url
        FROM publish_queue pq
        LEFT JOIN social_channels sc ON sc.id=pq.channel_id
        LEFT JOIN production_jobs pj ON pj.id=pq.job_id
        WHERE pq.owner_id=? AND pq.status IN ('queued','scheduled','publishing','blocked')
        ORDER BY
            CASE pq.status WHEN 'queued' THEN 0 WHEN 'scheduled' THEN 1 WHEN 'publishing' THEN 2 WHEN 'blocked' THEN 3 ELSE 4 END,
            pq.id ASC
        LIMIT 20""",
        (str(owner_id),)
    )
    open_queue = [
        {
            "queue_id": qid,
            "job_id": job_id,
            "platform": platform,
            "mode": mode,
            "status": status,
            "scheduled_at": scheduled_at,
            "channel_name": channel_name,
            "account_label": account_label,
            "topic": topic,
            "has_asset": bool(asset_url),
            "handoff_url": f"/api/operator/publish/{qid}/handoff",
            "complete_url": f"/api/operator/publish/{qid}/complete",
        }
        for qid, job_id, platform, mode, status, scheduled_at, channel_name, account_label, topic, asset_url in c.fetchall()
    ]
    conn.close()

    blockers = []
    if not channel_rows:
        blockers.append({"key": "no_channels", "detail": "Chưa có kênh đăng.", "next": "/channel_add platform=tiktok name=... mode=manual"})
    for channel in channels:
        if channel["readiness"] in {"missing_token_env", "missing_secret", "missing_page_id", "blocked"}:
            blockers.append({
                "key": f"channel_{channel['id']}",
                "detail": f"{channel['platform']} / {channel['channel_name']}: {channel['reason']}",
                "next": f"/channel_publish_set id={channel['id']} mode=manual hoặc mode=api token_env=...",
            })
    can_publish_any = any(ch["can_manual_publish"] for ch in channels)
    can_api_publish = any(ch["can_api_publish"] for ch in channels)
    queued_count = sum(row["count"] for row in queue_counts if row["status"] in {"queued", "scheduled"})
    return {
        "ready": can_publish_any,
        "api_ready": can_api_publish,
        "counts": counts,
        "queue_counts": queue_counts,
        "open_queue": open_queue,
        "channels": channels,
        "blockers": blockers,
        "next": {
            "telegram_queue": "/publish_queue",
            "telegram_handoff": "/publisher_handoff queue=<QUEUE_ID>",
            "api_next": "/api/operator/publish/next",
            "api_handoff": "/api/operator/publish/<QUEUE_ID>/handoff",
            "api_complete": "/api/operator/publish/<QUEUE_ID>/complete",
        },
        "rule": "Manual-ready được phép đăng thủ công. API-ready mới cho publisher worker tự đăng qua API chính thức; OnlyFans giữ manual trừ khi có công cụ được phép theo ToS.",
        "queued_count": queued_count,
    }

def operator_audit_data(owner_id):
    status = operator_status_data(owner_id)
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM affiliate_links WHERE owner_id=? AND status='active'", (str(owner_id),))
    active_affiliates = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM social_channels WHERE owner_id=? AND status='active'", (str(owner_id),))
    active_channels = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM campaigns WHERE owner_id=? AND status='active'", (str(owner_id),))
    active_campaigns = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM production_jobs WHERE owner_id=?", (str(owner_id),))
    total_jobs = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM production_tasks WHERE owner_id=?", (str(owner_id),))
    total_tasks = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM publish_queue WHERE owner_id=?", (str(owner_id),))
    total_publish_queue = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM performance_events WHERE owner_id=?", (str(owner_id),))
    total_performance = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM trend_candidates WHERE owner_id=?", (str(owner_id),))
    total_trends = c.fetchone()[0]
    conn.close()

    channel_rows = list_social_publish_readiness(owner_id)
    manual_ready = 0
    api_ready = 0
    channel_issues = []
    for row in channel_rows:
        readiness, reason = channel_publish_readiness(row)
        if readiness == "manual_ready":
            manual_ready += 1
        elif readiness == "api_ready":
            api_ready += 1
        elif readiness != "manual_required":
            channel_issues.append({"channel_id": row[0], "platform": row[1], "readiness": readiness, "reason": reason})

    api_ok = bool(OPERATOR_API_TOKEN and PUBLIC_BASE_URL)
    ai_ok = bool(gemini_client or openai_client)
    payos_ok = bool(PAYOS_CLIENT_ID and PAYOS_API_KEY and PAYOS_CHECKSUM_KEY)
    content_ok = active_affiliates > 0 and active_channels > 0 and active_campaigns > 0
    production_ok = total_jobs > 0 or total_tasks > 0
    publish_ok = manual_ready > 0 or api_ready > 0
    tracking_ok = total_performance > 0

    checks = [
        ("telegram_brain", True, "Telegram bot có /brain, /operator_director, /operator_execute.", "/brain đầu não nên làm gì tiếp theo"),
        ("operator_api", api_ok, "OPERATOR_API_TOKEN và PUBLIC_BASE_URL đã sẵn sàng." if api_ok else "Thiếu OPERATOR_API_TOKEN hoặc PUBLIC_BASE_URL cho n8n/Claude.", "/operator_api"),
        ("ai_provider", ai_ok, "Có Gemini/OpenAI để tạo brief/prompt." if ai_ok else "Thiếu GEMINI_API_KEY hoặc OPENAI_API_KEY; bot dùng fallback template.", "Set GEMINI_API_KEY hoặc OPENAI_API_KEY trên Railway"),
        ("payos", payos_ok, "PayOS env đủ 3 khóa." if payos_ok else "Thiếu PAYOS_CLIENT_ID/PAYOS_API_KEY/PAYOS_CHECKSUM_KEY.", "Kiểm tra biến PayOS trên Railway"),
        ("affiliate_catalog", active_affiliates > 0, f"{active_affiliates} affiliate active.", "/affiliate_seed"),
        ("channels", active_channels > 0, f"{active_channels} kênh active.", "/channel_add platform=tiktok name=... mode=manual"),
        ("campaigns", active_campaigns > 0, f"{active_campaigns} campaign active.", "/campaign_new name=... niche=... platforms=tiktok"),
        ("publish_readiness", publish_ok, f"manual_ready={manual_ready}, api_ready={api_ready}.", "/publish_readiness"),
        ("production_pipeline", production_ok, f"jobs={total_jobs}, tasks={total_tasks}.", "/operator_execute"),
        ("performance_tracking", tracking_ok, f"performance_events={total_performance}.", "/performance_add job=<ID> type=view value=..."),
    ]
    ready_count = sum(1 for _, ok, _, _ in checks if ok)
    score = int(ready_count / len(checks) * 100)
    blockers = [{"key": key, "detail": detail, "next": next_cmd} for key, ok, detail, next_cmd in checks if not ok]
    if score >= 85 and api_ok and content_ok and publish_ok:
        level = "READY_FOR_OPERATOR"
    elif score >= 60 and content_ok:
        level = "PARTIAL_READY"
    else:
        level = "SETUP_REQUIRED"
    return {
        "level": level,
        "score": score,
        "checks": checks,
        "blockers": blockers,
        "channel_issues": channel_issues,
        "counts": {
            **status["counts"],
            "total_jobs": total_jobs,
            "total_tasks": total_tasks,
            "total_publish_queue": total_publish_queue,
            "total_performance": total_performance,
            "total_trends": total_trends,
            "manual_ready_channels": manual_ready,
            "api_ready_channels": api_ready,
        },
        "next_command": blockers[0]["next"] if blockers else "/operator_director",
    }

def operator_worker_spec_data():
    base_url = (PUBLIC_BASE_URL or "https://<RAILWAY_DOMAIN>").rstrip("/")
    return {
        "name": "TOAN DAAS AI Operator Worker Spec",
        "version": "1.0",
        "base_url": base_url,
        "auth": {
            "type": "bearer",
            "header": "Authorization: Bearer <OPERATOR_API_TOKEN>",
            "note": "Không nhúng token vào prompt công khai, repo, caption hoặc log gửi cho khách.",
        },
        "mission": (
            "Điều phối sản xuất video affiliate hợp pháp: chọn affiliate, tìm trend, tạo job, giao task cho AI/tool, "
            "chuẩn bị publish pack, đăng có kiểm soát và ghi performance."
        ),
        "toolchain_url": f"{base_url}/api/operator/toolchain",
        "roles": [
            {
                "role": "director",
                "owner": "Claude/n8n hoặc admin Telegram",
                "input": "GET /api/operator/audit, GET /api/operator/director",
                "allowed_actions": [
                    "POST /api/operator/director/run để scale/build hoặc queue publish manual an toàn",
                    "POST /api/operator/affiliate-scale khi đã chọn affiliate rõ ràng",
                    "Không tự đăng ra mạng xã hội nếu chưa qua publish pack/review gate",
                ],
            },
            {
                "role": "creative_strategist",
                "owner": "Claude/Gemini",
                "input": "production job, affiliate profile, trend, related links",
                "allowed_actions": [
                    "Tạo hook, script, caption, CTA, hashtag, checklist compliance",
                    "Không cam kết doanh thu/lợi nhuận/phê duyệt tài chính",
                    "Không mạo danh thương hiệu/người thật",
                ],
            },
            {
                "role": "tool_worker",
                "owner": "Kling/Runway/Fish/Edge/CapCut/FFmpeg/n8n",
                "input": "GET /api/operator/tasks/next",
                "submit": "POST /api/operator/tasks/<TASK_ID>/complete",
                "allowed_actions": [
                    "Tạo voice, visual, edit, subtitle, final_video theo task",
                    "Trả output_url hoặc note lỗi rõ ràng",
                    "Không tự thay đổi affiliate link hoặc claim chính sách",
                ],
            },
            {
                "role": "publisher",
                "owner": "Admin/manual publisher hoặc API chính thức",
                "input": "GET /api/operator/publish/next và GET /api/operator/jobs/<JOB_ID>/publish-pack",
                "submit": "POST /api/operator/publish/<QUEUE_ID>/complete",
                "allowed_actions": [
                    "Đăng theo publish_pack, gắn disclosure, link chính và link liên quan phù hợp",
                    "Nếu nền tảng/API chặn thì trả status=blocked và note",
                    "OnlyFans giữ manual/official tool, chỉ dùng nhân vật tự tạo hoặc consent 18+",
                ],
            },
            {
                "role": "growth_analyst",
                "owner": "Claude/n8n/admin",
                "input": "GET /api/operator/affiliate-report, GET /api/operator/affiliate-decisions",
                "submit": "POST /api/operator/performance",
                "allowed_actions": [
                    "Ghi view/click/order/lead/revenue/cost",
                    "Đề xuất SCALE/FIX/TEST/PAUSE dựa trên dữ liệu",
                    "Không scale khi chưa có dữ liệu hoặc khi compliance bị chặn",
                ],
            },
        ],
        "standard_loop": [
            {"step": 1, "name": "audit", "method": "GET", "url": "/api/operator/audit"},
            {"step": 2, "name": "director", "method": "GET", "url": "/api/operator/director?days=30&platform=tiktok"},
            {"step": 3, "name": "safe_execute", "method": "POST", "url": "/api/operator/director/run"},
            {"step": 4, "name": "claim_task", "method": "GET", "url": "/api/operator/tasks/next"},
            {"step": 5, "name": "submit_task", "method": "POST", "url": "/api/operator/tasks/<TASK_ID>/complete"},
            {"step": 6, "name": "check_ready", "method": "GET", "url": "/api/operator/jobs/<JOB_ID>/ready"},
            {"step": 7, "name": "publish_pack", "method": "GET", "url": "/api/operator/jobs/<JOB_ID>/publish-pack"},
            {"step": 8, "name": "claim_publish", "method": "GET", "url": "/api/operator/publish/next"},
            {"step": 9, "name": "submit_publish", "method": "POST", "url": "/api/operator/publish/<QUEUE_ID>/complete"},
            {"step": 10, "name": "performance", "method": "POST", "url": "/api/operator/performance"},
        ],
        "payloads": {
            "director_run": {
                "days": 30,
                "platform": "tiktok",
                "limit": 10,
                "execute": True,
                "build": True,
                "duration": 45,
                "notify_admin": True,
            },
            "task_complete": {
                "status": "ready",
                "output_url": "https://.../asset.mp4",
                "note": "tool output or error detail",
            },
            "publish_complete": {
                "status": "published",
                "publish_url": "https://...",
                "views": 0,
                "clicks": 0,
                "note": "manual/api publisher",
            },
            "performance": {
                "job_id": 1,
                "event_type": "view|click|order|lead|revenue|cost",
                "value": 1,
                "amount": 0,
                "source": "tiktok|facebook|onlyfans|manual",
                "note": "tracking detail",
            },
        },
        "safety_rules": [
            "Không dùng ảnh/voice người thật nếu không có consent rõ ràng.",
            "Mọi nhân vật người mẫu/OnlyFans phải tự tạo hoặc có consent và đủ 18 tuổi.",
            "Không hứa thu nhập, lợi nhuận, phê duyệt vay/thẻ, hoặc kết quả tài chính.",
            "Không spam link; gắn disclosure affiliate rõ ràng.",
            "Không tự publish nếu readiness/review bị blocked.",
            "Không ghi secret/token/API key vào database, caption, note công khai hoặc repo.",
        ],
    }

def _tool_env_ready(env_keys):
    if not env_keys:
        return True
    return all(bool(_env(key)) for key in env_keys)

def _tool_node(name, kind, env_keys=None, cost="unknown", mode="api", note=""):
    env_keys = env_keys or []
    return {
        "name": name,
        "kind": kind,
        "cost": cost,
        "mode": mode,
        "env_keys": env_keys,
        "configured": _tool_env_ready(env_keys),
        "note": note,
    }

def operator_toolchain_data():
    chains = [
        {
            "stage": "brain_and_script",
            "purpose": "Hiểu lệnh Telegram, tạo brief, script, hook, caption và prompt cho tool khác.",
            "primary": _tool_node("Claude Opus / Claude Sonnet external", "llm", ["ANTHROPIC_API_KEY"], "paid", "external_api_or_manual", "Có thể chạy ngoài n8n/Claude app; bot không cần giữ key nếu bạn điều khiển thủ công."),
            "fallbacks": [
                _tool_node("Gemini", "llm", ["GEMINI_API_KEY"], "paid_or_free_quota", "api", "Đang được bot dùng cho brief/prompt khi có key."),
                _tool_node("OpenAI", "llm", ["OPENAI_API_KEY"], "paid", "api", "Fallback khi Gemini lỗi hoặc cần model khác."),
                _tool_node("Template nội bộ", "template", [], "free", "local", "Không gọi API, chất lượng thấp hơn nhưng không tốn phí."),
            ],
        },
        {
            "stage": "trend_research",
            "purpose": "Tìm trend, news/RSS, ghép trend với affiliate và đề xuất góc video.",
            "primary": _tool_node("Gemini/OpenAI trend analyst", "llm", ["GEMINI_API_KEY"], "paid_or_free_quota", "api", "Dùng AI để phân tích trend và sản phẩm phù hợp."),
            "fallbacks": [
                _tool_node("RSS/news public parser", "public_data", [], "free", "local", "Nguồn công khai trong /trend_search."),
                _tool_node("Manual trend input", "manual", [], "free", "telegram", "Admin nhập trend trực tiếp qua bot."),
            ],
        },
        {
            "stage": "voice",
            "purpose": "Tạo giọng đọc cho video.",
            "primary": _tool_node("Fish Audio HD", "tts", ["FISH_AUDIO_KEY"], "paid", "api", "Giọng chất lượng cao; nếu lỗi/quota/hết tiền thì fallback Edge và báo admin."),
            "fallbacks": [
                _tool_node("Edge TTS", "tts", [], "free", "local", "Fallback miễn phí/ít phí, bot có sẵn."),
            ],
        },
        {
            "stage": "transcription",
            "purpose": "Bóc băng audio/video thành text.",
            "primary": _tool_node("Deepgram", "speech_to_text", ["DEEPGRAM_API_KEY"], "paid", "api", "Bóc băng nhanh, cần theo dõi quota."),
            "fallbacks": [
                _tool_node("Manual transcript", "manual", [], "free", "telegram", "Nếu Deepgram lỗi, yêu cầu admin/worker nhập transcript hoặc dùng tool ngoài."),
            ],
        },
        {
            "stage": "background_removal",
            "purpose": "Tách nền ảnh sản phẩm/người mẫu AI.",
            "primary": _tool_node("RemoveBG HD", "image", ["REMOVEBG_API_KEY"], "paid", "api", "Chất lượng cao; nếu lỗi/quota/hết tiền thì fallback Cutout và hoàn chênh lệch."),
            "fallbacks": [
                _tool_node("Cutout.pro", "image", ["CUTOUT_API_KEY"], "paid_or_free_quota", "api", "Gói tiết kiệm/fallback."),
            ],
        },
        {
            "stage": "video_generation",
            "purpose": "Tạo cảnh video AI từ manifest/prompt.",
            "primary": _tool_node("Kling", "video", ["KLING_API_KEY"], "paid", "external_api_or_manual", "Ưu tiên khi có tài khoản/API/tool chính thức."),
            "fallbacks": [
                _tool_node("Runway", "video", ["RUNWAY_API_KEY"], "paid", "external_api_or_manual", "Fallback/so sánh chất lượng."),
                _tool_node("Pika/Luma/manual tool", "video", [], "manual", "manual", "Dùng khi chưa có API hoặc cần kiểm soát bằng tay."),
            ],
        },
        {
            "stage": "editing",
            "purpose": "Ghép cảnh, voice, subtitle, CTA overlay và export final video.",
            "primary": _tool_node("CapCut", "editor", ["CAPCUT_API_KEY"], "paid_or_manual", "external_api_or_manual", "Ưu tiên workflow dựng video nhanh nếu có API/tool hợp lệ."),
            "fallbacks": [
                _tool_node("FFmpeg", "editor", [], "free", "local_or_worker", "Fallback tự động cho ghép file cơ bản."),
                _tool_node("Manual editor", "manual", [], "manual", "manual", "Dùng khi video cần review/chỉnh tay."),
            ],
        },
        {
            "stage": "publishing",
            "purpose": "Đăng TikTok/Facebook/OnlyFans/Reels và gắn link affiliate đúng chỗ.",
            "primary": _tool_node("Official platform API", "publisher", ["TIKTOK_ACCESS_TOKEN", "FACEBOOK_PAGE_TOKEN"], "paid_or_platform", "api", "Chỉ dùng API chính thức khi tài khoản được phép."),
            "fallbacks": [
                _tool_node("Manual publish gate", "publisher", [], "manual", "telegram", "Mặc định an toàn: admin tự đăng hoặc duyệt trước khi worker đăng."),
            ],
        },
        {
            "stage": "performance_tracking",
            "purpose": "Ghi view/click/lead/order/revenue/cost để AI quyết định scale/fix/pause.",
            "primary": _tool_node("Operator performance API", "analytics", ["OPERATOR_API_TOKEN"], "free", "api", "n8n/worker gửi số liệu vào /api/operator/performance."),
            "fallbacks": [
                _tool_node("Manual performance_add", "analytics", [], "free", "telegram", "Admin nhập số liệu bằng /performance_add."),
            ],
        },
        {
            "stage": "payment",
            "purpose": "Thu tiền từ khách hoặc thanh toán thủ công khi PayOS lỗi.",
            "primary": _tool_node("PayOS dynamic QR", "payment", ["PAYOS_CLIENT_ID", "PAYOS_API_KEY", "PAYOS_CHECKSUM_KEY"], "transaction_fee", "api", "Tạo QR động và webhook tự cộng xu khi chữ ký/số tiền đúng."),
            "fallbacks": [
                _tool_node("Manual bank QR", "payment", [], "manual", "telegram", "Khách gửi bill, admin duyệt và cộng xu khi PayOS lỗi."),
            ],
        },
    ]
    ready = 0
    blocked = []
    for chain in chains:
        options = [chain["primary"], *chain["fallbacks"]]
        active = next((item for item in options if item["configured"] or item["mode"] in {"manual", "telegram", "local", "local_or_worker"}), None)
        chain["active_choice"] = active["name"] if active else ""
        chain["primary_ready"] = chain["primary"]["configured"]
        chain["fallback_ready"] = any(item["configured"] or item["mode"] in {"manual", "telegram", "local", "local_or_worker"} for item in chain["fallbacks"])
        chain["ready"] = bool(active)
        if chain["ready"]:
            ready += 1
        else:
            blocked.append({"stage": chain["stage"], "missing": chain["primary"]["env_keys"]})
    return {
        "policy": "paid_best_tool_first_then_low_cost_or_free_fallback",
        "failure_protocol": [
            "Nếu tool chính lỗi/quota/hết tiền: ghi rõ lỗi, báo admin, dùng fallback được phép.",
            "Nếu dịch vụ khách đã bị trừ phí cao cấp nhưng fallback rẻ hơn: hoàn chênh lệch bằng credit log.",
            "Nếu cả primary và fallback đều không có output: đánh dấu task blocked/failed, không tự giả lập kết quả.",
            "Không xóa tool cũ khi nâng cấp; chỉ thay đổi khi tool sai hoặc vi phạm chính sách.",
        ],
        "event_api": {
            "report_url": "/api/operator/tool-events",
            "list_url": "/api/operator/tool-events",
            "telegram": "/operator_tool_events",
            "payload": {
                "stage": "voice",
                "tool_name": "Fish Audio HD",
                "event_type": "quota",
                "severity": "warning",
                "job_id": 0,
                "task_id": 0,
                "fallback_tool": "Edge TTS",
                "message": "quota hết, đã fallback",
                "notify_admin": True,
            },
        },
        "counts": {"ready": ready, "total": len(chains), "blocked": len(blocked)},
        "blocked": blocked,
        "chains": chains,
    }

def record_tool_event(owner_id, stage, tool_name, event_type, severity="warning", job_id=0, task_id=0, fallback_tool="", message=""):
    event_type = (event_type or "error").strip().lower()
    severity = (severity or "warning").strip().lower()
    allowed_events = {"error", "quota", "out_of_credit", "fallback", "blocked", "recovered", "info"}
    allowed_severity = {"info", "warning", "critical"}
    if event_type not in allowed_events:
        event_type = "error"
    if severity not in allowed_severity:
        severity = "warning"
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """INSERT INTO tool_events
           (owner_id, stage, tool_name, event_type, severity, job_id, task_id, fallback_tool, message, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            str(owner_id), stage or "", tool_name or "", event_type, severity,
            int(job_id or 0), int(task_id or 0), fallback_tool or "", message or "", now_text()
        )
    )
    event_id = c.lastrowid
    conn.commit()
    conn.close()
    return event_id

def list_tool_events(owner_id, limit=20, stage="", severity=""):
    limit = max(1, min(int(limit or 20), 50))
    params = [str(owner_id)]
    where = ["owner_id=?"]
    if stage:
        where.append("LOWER(stage)=?")
        params.append(stage.lower())
    if severity:
        where.append("LOWER(severity)=?")
        params.append(severity.lower())
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        f"""SELECT id, stage, tool_name, event_type, severity, job_id, task_id, fallback_tool, message, created_at
            FROM tool_events
            WHERE {' AND '.join(where)}
            ORDER BY id DESC
            LIMIT ?""",
        [*params, limit]
    )
    rows = c.fetchall()
    conn.close()
    return rows

def serialize_tool_event(row):
    if not row:
        return {}
    event_id, stage, tool_name, event_type, severity, job_id, task_id, fallback_tool, message, created_at = row
    return {
        "id": event_id,
        "stage": stage,
        "tool_name": tool_name,
        "event_type": event_type,
        "severity": severity,
        "job_id": job_id,
        "task_id": task_id,
        "fallback_tool": fallback_tool,
        "message": message,
        "created_at": created_at,
    }

def operator_n8n_template_data():
    base_url = (PUBLIC_BASE_URL or "https://<RAILWAY_DOMAIN>").rstrip("/")
    bearer = "Bearer <OPERATOR_API_TOKEN>"
    return {
        "name": "TOAN DAAS n8n Safe Operator Loop",
        "version": "1.0",
        "base_url": base_url,
        "purpose": (
            "Template workflow cho n8n/automation chạy công ty một người: audit hệ thống, hỏi director, "
            "chạy action an toàn, giao task cho AI/tool, chuẩn bị publish pack, đăng qua review gate và ghi performance."
        ),
        "required_env": {
            "OPERATOR_BASE_URL": base_url,
            "OPERATOR_API_TOKEN": "<set in n8n credentials/env, không paste vào node note hoặc repo>",
        },
        "default_schedule": {
            "cron": "*/30 * * * *",
            "note": "Chạy 30 phút/lần khi mới vận hành; chỉ giảm xuống 5-15 phút khi API/tool đã ổn định.",
        },
        "http_defaults": {
            "headers": {
                "Authorization": bearer,
                "Content-Type": "application/json",
            },
            "timeout_seconds": 60,
            "retry": {"max_attempts": 2, "backoff_seconds": 20},
        },
        "workflow": [
            {
                "node": "Cron Trigger",
                "type": "schedule",
                "action": "Start safe loop",
                "config": {"cron": "*/30 * * * *"},
            },
            {
                "node": "Audit",
                "type": "http_request",
                "method": "GET",
                "url": f"{base_url}/api/operator/audit",
                "continue_if": "ok=true",
            },
            {
                "node": "Read Worker Spec",
                "type": "http_request",
                "method": "GET",
                "url": f"{base_url}/api/operator/worker-spec",
                "note": "Cho Claude/tool worker biết vai trò, payload và safety rules.",
            },
            {
                "node": "Read Toolchain",
                "type": "http_request",
                "method": "GET",
                "url": f"{base_url}/api/operator/toolchain",
                "note": "Cho worker biết tool chính/fallback, env còn thiếu và failure protocol.",
            },
            {
                "node": "Director Run",
                "type": "http_request",
                "method": "POST",
                "url": f"{base_url}/api/operator/director/run",
                "body": {
                    "days": 30,
                    "platform": "tiktok",
                    "limit": 10,
                    "execute": True,
                    "build": True,
                    "duration": 45,
                    "notify_admin": True,
                },
                "note": "Chỉ chạy action an toàn: scale/build/queue manual; không auto publish ngoài MXH.",
            },
            {
                "node": "Claim Production Task",
                "type": "http_request",
                "method": "GET",
                "url": f"{base_url}/api/operator/tasks/next",
                "when": "director result has no blocker or a task is pending",
            },
            {
                "node": "AI/Tool Worker",
                "type": "external_tool",
                "tools": ["Claude/Gemini", "Kling/Runway", "Fish Audio/Edge TTS", "CapCut/FFmpeg"],
                "rule": "Dùng công cụ trả phí/chất lượng cao trước; nếu lỗi/quota hết thì POST /api/operator/tool-events, fallback công cụ rẻ/miễn phí và báo admin.",
                "output": {"status": "ready|blocked|failed", "output_url": "https://...", "note": "tool log"},
            },
            {
                "node": "Report Tool Event",
                "type": "http_request",
                "method": "POST",
                "url": f"{base_url}/api/operator/tool-events",
                "body": {
                    "stage": "voice",
                    "tool_name": "Fish Audio HD",
                    "event_type": "quota",
                    "severity": "warning",
                    "fallback_tool": "Edge TTS",
                    "message": "quota hết, đã fallback",
                    "notify_admin": True,
                },
                "note": "Gọi node này khi tool chính lỗi/quota/hết tiền hoặc worker phải fallback.",
            },
            {
                "node": "Complete Task",
                "type": "http_request",
                "method": "POST",
                "url": f"{base_url}/api/operator/tasks/<TASK_ID>/complete",
                "body": {"status": "ready", "output_url": "https://.../asset.mp4", "note": "tool output"},
            },
            {
                "node": "Job Readiness",
                "type": "http_request",
                "method": "GET",
                "url": f"{base_url}/api/operator/jobs/<JOB_ID>/ready",
                "continue_if": "ready=true or manual_ready=true",
            },
            {
                "node": "Publish Pack",
                "type": "http_request",
                "method": "GET",
                "url": f"{base_url}/api/operator/jobs/<JOB_ID>/publish-pack",
                "note": "Lấy caption, disclosure, link chính, link liên quan/comment ghim và checklist.",
            },
            {
                "node": "Approve Publish",
                "type": "http_request",
                "method": "POST",
                "url": f"{base_url}/api/operator/jobs/<JOB_ID>/approve",
                "body": {"queue": True, "mode": "manual", "note": "reviewed_by_admin_or_worker", "notify_admin": True},
                "note": "Chỉ gọi sau khi admin/worker đã kiểm duyệt final video, caption, affiliate claim và quyền nội dung.",
            },
            {
                "node": "Claim Publish Queue",
                "type": "http_request",
                "method": "GET",
                "url": f"{base_url}/api/operator/publish/next?platform=tiktok&mode=manual",
            },
            {
                "node": "Publisher",
                "type": "manual_or_official_api",
                "rule": "Đăng thủ công/API chính thức sau review. OnlyFans giữ manual/official tool và consent 18+.",
                "output": {"status": "published|blocked", "publish_url": "https://...", "views": 0, "clicks": 0},
            },
            {
                "node": "Complete Publish",
                "type": "http_request",
                "method": "POST",
                "url": f"{base_url}/api/operator/publish/<QUEUE_ID>/complete",
                "body": {"status": "published", "publish_url": "https://...", "views": 0, "clicks": 0, "note": "manual/api publisher"},
            },
            {
                "node": "Performance Tracker",
                "type": "http_request",
                "method": "POST",
                "url": f"{base_url}/api/operator/performance",
                "body": {"job_id": 1, "event_type": "view|click|order|lead|revenue|cost", "value": 1, "amount": 0, "source": "tiktok"},
            },
        ],
        "branching_rules": [
            "Nếu audit.level=SETUP_REQUIRED: dừng workflow và báo admin bằng next_command.",
            "Nếu director_run.executed=false: báo admin kèm next_action, không cố chạy node tool.",
            "Nếu task không có output_url: complete task status=blocked/failed để không kẹt pipeline.",
            "Nếu publish readiness không đạt: queue manual hoặc blocked, không tự đăng.",
            "Nếu affiliate_decisions có SCALE/PUBLISH: ưu tiên link đó và chèn các related_links phù hợp trong caption/comment/status.",
        ],
        "tracking_events": [
            "view: lượt xem video/bài viết",
            "click: lượt bấm link affiliate",
            "lead: form/app install/đăng ký",
            "order: đơn hàng hoặc conversion",
            "revenue: hoa hồng/doanh thu",
            "cost: chi phí ads/tool",
        ],
        "sample_curl": {
            "audit": f"curl -H \"Authorization: {bearer}\" {base_url}/api/operator/audit",
            "director_run": (
                f"curl -X POST -H \"Authorization: {bearer}\" -H \"Content-Type: application/json\" "
                f"-d '{{\"days\":30,\"platform\":\"tiktok\",\"limit\":10,\"execute\":true,\"build\":true,\"duration\":45}}' "
                f"{base_url}/api/operator/director/run"
            ),
        },
        "guardrails": [
            "Không paste OPERATOR_API_TOKEN vào workflow note, prompt public, caption hoặc Git.",
            "Không tự động dùng content có bản quyền từ trang brand nếu điều khoản không cho phép; chỉ tham khảo và viết lại.",
            "Luôn có disclosure affiliate khi quảng cáo/link kiếm hoa hồng.",
            "Không hứa duyệt vay/thẻ, thu nhập, chữa bệnh, hoặc kết quả tài chính chắc chắn.",
            "Không dùng ảnh/giọng người thật nếu không có consent rõ ràng; nội dung người lớn phải đủ 18+ và tuân thủ nền tảng.",
        ],
    }

def operator_n8n_workflow_json_data():
    base_url_expr = "={{$env.OPERATOR_BASE_URL || 'https://<RAILWAY_DOMAIN>'}}"
    auth_header = "Bearer {{$env.OPERATOR_API_TOKEN}}"
    headers = {
        "parameters": [
            {"name": "Authorization", "value": auth_header},
            {"name": "Content-Type", "value": "application/json"},
        ]
    }
    return {
        "name": "TOAN DAAS Safe Operator Loop",
        "active": False,
        "nodes": [
            {
                "id": "manual-trigger",
                "name": "Manual Test",
                "type": "n8n-nodes-base.manualTrigger",
                "typeVersion": 1,
                "position": [-1180, -180],
                "parameters": {},
            },
            {
                "id": "schedule-trigger",
                "name": "Every 30 Minutes",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1.2,
                "position": [-1180, 80],
                "parameters": {
                    "rule": {
                        "interval": [
                            {
                                "field": "minutes",
                                "minutesInterval": 30,
                            }
                        ]
                    }
                },
            },
            {
                "id": "audit",
                "name": "Audit Operator",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [-900, -40],
                "parameters": {
                    "method": "GET",
                    "url": f"{base_url_expr}/api/operator/audit",
                    "sendHeaders": True,
                    "headerParameters": headers,
                    "options": {"timeout": 60000},
                },
            },
            {
                "id": "audit-ready",
                "name": "Audit Ready?",
                "type": "n8n-nodes-base.if",
                "typeVersion": 2,
                "position": [-640, -40],
                "parameters": {
                    "conditions": {
                        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                        "conditions": [
                            {
                                "id": "audit-not-setup",
                                "leftValue": "={{$json.level}}",
                                "rightValue": "SETUP_REQUIRED",
                                "operator": {"type": "string", "operation": "notEquals"},
                            }
                        ],
                        "combinator": "and",
                    }
                },
            },
            {
                "id": "read-toolchain",
                "name": "Read Toolchain",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [-500, -300],
                "parameters": {
                    "method": "GET",
                    "url": f"{base_url_expr}/api/operator/toolchain",
                    "sendHeaders": True,
                    "headerParameters": headers,
                    "options": {"timeout": 60000},
                },
            },
            {
                "id": "director-run",
                "name": "Director Run Safe Action",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [-360, -120],
                "parameters": {
                    "method": "POST",
                    "url": f"{base_url_expr}/api/operator/director/run",
                    "sendHeaders": True,
                    "headerParameters": headers,
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": (
                        "={\"days\":30,\"platform\":\"tiktok\",\"limit\":10,"
                        "\"execute\":true,\"build\":true,\"duration\":45,\"notify_admin\":true}"
                    ),
                    "options": {"timeout": 120000},
                },
            },
            {
                "id": "claim-task",
                "name": "Claim Next Task",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [-80, -120],
                "parameters": {
                    "method": "GET",
                    "url": f"{base_url_expr}/api/operator/tasks/next",
                    "sendHeaders": True,
                    "headerParameters": headers,
                    "options": {"timeout": 60000},
                },
            },
            {
                "id": "tool-worker-note",
                "name": "Tool Worker Placeholder",
                "type": "n8n-nodes-base.stickyNote",
                "typeVersion": 1,
                "position": [180, -300],
                "parameters": {
                    "content": (
                        "Gắn node Claude/Gemini/Kling/Runway/Fish/Edge/CapCut tại đây.\n"
                        "Luật vận hành: dùng tool trả phí/chất lượng cao trước; hết quota/lỗi thì fallback tool rẻ/miễn phí và báo admin.\n"
                        "Output cần có: status, output_url, note. Không tự đổi affiliate link, không tự publish nếu chưa qua review."
                    ),
                    "height": 260,
                    "width": 360,
                },
            },
            {
                "id": "report-tool-event",
                "name": "Report Tool Event Sample",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [180, 120],
                "parameters": {
                    "method": "POST",
                    "url": f"{base_url_expr}/api/operator/tool-events",
                    "sendHeaders": True,
                    "headerParameters": headers,
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": (
                        "={\"stage\":\"voice\",\"tool_name\":\"Fish Audio HD\","
                        "\"event_type\":\"quota\",\"severity\":\"warning\","
                        "\"fallback_tool\":\"Edge TTS\",\"message\":\"sample fallback event\","
                        "\"notify_admin\":true}"
                    ),
                    "options": {"timeout": 60000},
                },
            },
            {
                "id": "complete-task",
                "name": "Complete Task",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [240, -120],
                "parameters": {
                    "method": "POST",
                    "url": f"{base_url_expr}/api/operator/tasks/{{{{$json.task.id}}}}/complete",
                    "sendHeaders": True,
                    "headerParameters": headers,
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": (
                        "={\"status\":\"blocked\",\"output_url\":\"\","
                        "\"note\":\"Replace this node body with real tool output from Claude/Kling/CapCut/etc.\"}"
                    ),
                    "options": {"timeout": 60000},
                },
            },
            {
                "id": "claim-publish",
                "name": "Claim Publish Queue",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [540, -120],
                "parameters": {
                    "method": "GET",
                    "url": f"{base_url_expr}/api/operator/publish/next?platform=tiktok&mode=manual",
                    "sendHeaders": True,
                    "headerParameters": headers,
                    "options": {"timeout": 60000},
                },
            },
            {
                "id": "approve-publish",
                "name": "Approve Publish Gate",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [520, 80],
                "parameters": {
                    "method": "POST",
                    "url": f"{base_url_expr}/api/operator/jobs/{{{{$json.job_id}}}}/approve",
                    "sendHeaders": True,
                    "headerParameters": headers,
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": (
                        "={\"queue\":true,\"mode\":\"manual\","
                        "\"note\":\"approved by n8n/manual gate\",\"notify_admin\":true}"
                    ),
                    "options": {"timeout": 60000},
                },
            },
            {
                "id": "publish-pack",
                "name": "Get Publish Pack",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [820, -120],
                "parameters": {
                    "method": "GET",
                    "url": f"{base_url_expr}/api/operator/jobs/{{{{$json.item.job_id}}}}/publish-pack",
                    "sendHeaders": True,
                    "headerParameters": headers,
                    "options": {"timeout": 60000},
                },
            },
            {
                "id": "publisher-note",
                "name": "Manual/Official Publisher Gate",
                "type": "n8n-nodes-base.stickyNote",
                "typeVersion": 1,
                "position": [1080, -300],
                "parameters": {
                    "content": (
                        "Đăng bằng tay hoặc API chính thức sau khi kiểm duyệt.\n"
                        "TikTok/Facebook: gắn disclosure affiliate.\n"
                        "OnlyFans: chỉ dùng nhân vật tự tạo hoặc người thật có consent, đủ 18+, không auto bằng tool trái điều khoản."
                    ),
                    "height": 220,
                    "width": 340,
                },
            },
            {
                "id": "complete-publish",
                "name": "Complete Publish",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1120, -120],
                "parameters": {
                    "method": "POST",
                    "url": f"{base_url_expr}/api/operator/publish/{{{{$json.item.queue_id}}}}/complete",
                    "sendHeaders": True,
                    "headerParameters": headers,
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": (
                        "={\"status\":\"blocked\",\"publish_url\":\"\","
                        "\"views\":0,\"clicks\":0,\"note\":\"Fill after manual/official publish.\"}"
                    ),
                    "options": {"timeout": 60000},
                },
            },
            {
                "id": "performance-note",
                "name": "Performance Tracking Reminder",
                "type": "n8n-nodes-base.stickyNote",
                "typeVersion": 1,
                "position": [1380, -300],
                "parameters": {
                    "content": (
                        "Sau khi có số liệu, gọi /api/operator/performance cho view/click/lead/order/revenue/cost.\n"
                        "Dữ liệu này nuôi /affiliate_decisions để chọn SCALE, FIX, TEST hoặc PAUSE."
                    ),
                    "height": 180,
                    "width": 340,
                },
            },
            {
                "id": "record-performance",
                "name": "Record Performance Sample",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1440, -120],
                "parameters": {
                    "method": "POST",
                    "url": f"{base_url_expr}/api/operator/performance",
                    "sendHeaders": True,
                    "headerParameters": headers,
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": (
                        "={\"job_id\":{{$json.job_id || 0}},\"event_type\":\"view\","
                        "\"value\":0,\"amount\":0,\"source\":\"n8n\",\"note\":\"sample, replace with real metrics\"}"
                    ),
                    "options": {"timeout": 60000},
                },
            },
            {
                "id": "blocked-note",
                "name": "Setup Required",
                "type": "n8n-nodes-base.set",
                "typeVersion": 3.4,
                "position": [-360, 120],
                "parameters": {
                    "assignments": {
                        "assignments": [
                            {
                                "id": "setup-required-message",
                                "name": "message",
                                "type": "string",
                                "value": "Audit đang báo SETUP_REQUIRED. Xem next_command trong output và xử lý trên Telegram trước khi bật workflow.",
                            }
                        ]
                    },
                    "includeOtherFields": True,
                },
            },
        ],
        "connections": {
            "Manual Test": {"main": [[{"node": "Audit Operator", "type": "main", "index": 0}]]},
            "Every 30 Minutes": {"main": [[{"node": "Audit Operator", "type": "main", "index": 0}]]},
            "Audit Operator": {"main": [[{"node": "Audit Ready?", "type": "main", "index": 0}]]},
            "Audit Ready?": {
                "main": [
                    [{"node": "Read Toolchain", "type": "main", "index": 0}],
                    [{"node": "Setup Required", "type": "main", "index": 0}],
                ]
            },
            "Read Toolchain": {"main": [[{"node": "Director Run Safe Action", "type": "main", "index": 0}]]},
            "Director Run Safe Action": {"main": [[{"node": "Claim Next Task", "type": "main", "index": 0}]]},
            "Claim Next Task": {"main": [[{"node": "Complete Task", "type": "main", "index": 0}]]},
            "Complete Task": {"main": [[{"node": "Claim Publish Queue", "type": "main", "index": 0}]]},
            "Claim Publish Queue": {"main": [[{"node": "Get Publish Pack", "type": "main", "index": 0}]]},
            "Get Publish Pack": {"main": [[{"node": "Complete Publish", "type": "main", "index": 0}]]},
            "Complete Publish": {"main": [[{"node": "Record Performance Sample", "type": "main", "index": 0}]]},
        },
        "settings": {
            "executionOrder": "v1",
            "saveManualExecutions": True,
        },
        "staticData": None,
        "pinData": {},
        "meta": {
            "templateCredsSetupCompleted": False,
            "description": "Set OPERATOR_BASE_URL and OPERATOR_API_TOKEN in n8n environment before activation.",
        },
        "tags": ["toan-daas", "ai-operator", "affiliate", "safe-loop"],
    }

def operator_today_data(owner_id):
    status = operator_status_data(owner_id)
    since, affiliate_rows, job_rows = affiliate_performance_report_data(owner_id, days=30, limit=8)
    next_task = next_production_task(owner_id)
    publish_rows = list_publish_queue(owner_id, limit=5)
    actions = []
    for key, ok, detail, next_cmd in status["checks"]:
        if not ok:
            actions.append({
                "priority": "setup",
                "title": f"Hoàn thiện {key}",
                "detail": detail,
                "command": next_cmd,
            })
    if status["blocked_jobs"]:
        jid, stage, job_status, platform, topic, channel_name, product_name, updated_at = status["blocked_jobs"][0]
        actions.append({
            "priority": "fix",
            "title": f"Gỡ nghẽn job #{jid}",
            "detail": f"{platform or '-'} | {topic or '-'}",
            "command": f"/job_ready job={jid}",
        })
    if next_task:
        tid, job_id, manifest_id, task_type, tool, scene_no, title, task_status, output_url, note, updated_at = next_task
        actions.append({
            "priority": "produce",
            "title": f"Làm task #{tid} cho job #{job_id}",
            "detail": f"{task_type or '-'} / {tool or '-'} | {title or '-'}",
            "command": f"/task_handoff id={tid}",
        })
    open_publish = [row for row in publish_rows if (row[5] or "") in {"queued", "scheduled", "publishing", "blocked"}]
    if open_publish:
        qid, job_id, platform, channel_name, mode, queue_status, scheduled_at, publish_url, topic, updated_at = open_publish[0]
        actions.append({
            "priority": "publish",
            "title": f"Xử lý publish queue #{qid}",
            "detail": f"job #{job_id} | {platform or '-'} | {topic or '-'}",
            "command": "/publish_queue",
        })
    best_affiliate = None
    if affiliate_rows:
        ranked = []
        for row in affiliate_rows:
            (
                aid, network, product, niche, url, product_score, jobs, publishes, views,
                clicks, conversions, revenue, cost, events
            ) = row
            score, ctr, cvr, roi = growth_score(views, clicks, conversions, revenue, cost)
            ranked.append((score, row, ctr, cvr, roi))
        ranked.sort(key=lambda item: item[0], reverse=True)
        best_affiliate = ranked[0]
        score, row, ctr, cvr, roi = best_affiliate
        aid, network, product, niche, url, product_score, jobs, publishes, views, clicks, conversions, revenue, cost, events = row
        actions.append({
            "priority": "scale",
            "title": f"Scale affiliate #{aid}: {product or network or 'affiliate'}",
            "detail": f"score={score} views={views or 0} clicks={clicks or 0} revenue={int(revenue or 0):,}đ",
            "command": f"/affiliate_scale aff={aid} platform=tiktok channel=all limit=3 build=1 duration=45",
        })
    if not actions:
        actions.append({
            "priority": "start",
            "title": "Bắt đầu vòng scale mới",
            "detail": "Hệ thống không có việc nghẽn rõ ràng.",
            "command": "/affiliate_report days=30",
        })
    return {
        "status": status,
        "affiliate_since": since,
        "best_affiliate": best_affiliate,
        "next_task": next_task,
        "publish_rows": publish_rows,
        "actions": actions[:8],
    }

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
        or (stage or "").lower() in {"review", "publish", "approved", "done"}
        and (status or "").lower() in {"ready", "approved", "queued", "published"}
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
        ("queue_or_published", bool(queue_open or publish_url or (status or "").lower() == "published"), "Đã vào hàng đợi hoặc đã đăng.", f"/publish_pack job={job_id} rồi /approve_publish job={job_id} queue=1 mode=manual"),
    ]
    if blocked_tasks:
        checks.append(("blocked_tasks", False, f"Có {len(blocked_tasks)} task bị blocked.", f"/tasks job={job_id}"))

    missing = [row for row in checks if not row[1]]
    core_missing = [row for row in missing if row[0] != "queue_or_published"]
    if not core_missing and not queue_open and not publish_url and (status or "").lower() != "published":
        level = "READY_TO_QUEUE"
        next_action = f"/publish_pack job={job_id} rồi /approve_publish job={job_id} queue=1 mode=manual"
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

def approve_publish_job(owner_id, job_id, note="", queue=True, mode="manual", scheduled_at=""):
    readiness = production_readiness_data(owner_id, job_id)
    if not readiness:
        return False, "job_not_found", {}
    blocking = [row for row in readiness["missing"] if row[0] != "queue_or_published"]
    if blocking:
        return False, "not_ready", {
            "missing": [
                {"key": key, "detail": detail, "next": next_cmd}
                for key, _ok, detail, next_cmd in blocking
            ],
            "next_action": blocking[0][3],
        }
    update_production_job(
        job_id,
        owner_id,
        stage="approved",
        status="approved",
        note=note or "approved_publish_gate",
    )
    queue_id = 0
    queued = False
    if queue:
        ok, result = create_publish_queue_item(owner_id, job_id, mode=mode or "manual", scheduled_at=scheduled_at or "", note=note or "approved_publish_gate")
        queued = bool(ok)
        queue_id = result if ok else 0
        if not ok:
            return False, str(result), {"approved": True, "queued": False}
    return True, "approved", {"approved": True, "queued": queued, "queue_id": queue_id}

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

def add_performance_event(owner_id, job_id, event_type, value=0, amount=0, note="", variant_id=0, affiliate_id_override=0):
    job = get_production_job(job_id, owner_id)
    if not job:
        return False, None
    if variant_id:
        variant = get_creative_variant(owner_id, variant_id)
        if not variant or int(variant[1]) != int(job_id):
            return False, None
    _, _, _, channel_id, affiliate_id, platform, *_ = job
    if affiliate_id_override:
        affiliate_id = int(affiliate_id_override)
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

def record_affiliate_postback(owner_id, job_id=0, affiliate_id=0, event_type="order", value=1, amount=0, source="affiliate_postback", order_id="", note=""):
    event_type = (event_type or "order").lower()
    if event_type not in {"order", "revenue", "lead"}:
        event_type = "order"
    affiliate_id = int(affiliate_id or 0)
    job_id = int(job_id or 0)
    if not job_id and affiliate_id:
        conn = db_connect()
        c = conn.cursor()
        c.execute(
            """SELECT id FROM production_jobs
               WHERE owner_id=? AND affiliate_id=?
               ORDER BY updated_at DESC, id DESC LIMIT 1""",
            (str(owner_id), affiliate_id)
        )
        row = c.fetchone()
        conn.close()
        job_id = int(row[0]) if row else 0
    if not job_id:
        return False, "missing_job_id", {}
    note_parts = [source or "affiliate_postback"]
    if affiliate_id:
        note_parts.append(f"affiliate:{affiliate_id}")
    if order_id:
        note_parts.append(f"order:{order_id}")
    if note:
        note_parts.append(note)
    ok, job = add_performance_event(
        owner_id,
        job_id,
        event_type,
        int(value or 1),
        int(amount or 0),
        " | ".join(note_parts),
        0,
        affiliate_id_override=affiliate_id,
    )
    if not ok:
        return False, "job_not_found", {}
    if amount:
        update_production_job(job_id, owner_id, status="published", note=f"affiliate_postback:{event_type} amount={amount}")
    return True, "recorded", {"job_id": job_id, "affiliate_id": affiliate_id, "event_type": event_type, "amount": int(amount or 0)}

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

def affiliate_performance_report_data(owner_id, days=30, limit=15):
    since = (datetime.now() - timedelta(days=max(1, int(days)))).strftime("%Y-%m-%d %H:%M:%S")
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT al.id, al.network, al.product_name, al.niche, al.url, al.product_score,
                  COUNT(DISTINCT pj.id) AS jobs,
                  SUM(CASE WHEN pe.event_type='publish' THEN pe.value ELSE 0 END) AS publishes,
                  SUM(CASE WHEN pe.event_type='view' THEN pe.value ELSE 0 END) AS views,
                  SUM(CASE WHEN pe.event_type='click' THEN pe.value ELSE 0 END) AS clicks,
                  SUM(CASE WHEN pe.event_type IN ('order','lead','revenue') THEN pe.value ELSE 0 END) AS conversions,
                  SUM(CASE WHEN pe.event_type IN ('order','lead','revenue') THEN pe.amount ELSE 0 END) AS revenue,
                  SUM(CASE WHEN pe.event_type='cost' THEN pe.amount ELSE 0 END) AS cost,
                  COUNT(pe.id) AS events
        FROM affiliate_links al
        LEFT JOIN production_jobs pj ON pj.affiliate_id=al.id AND pj.owner_id=al.owner_id
        LEFT JOIN performance_events pe ON pe.affiliate_id=al.id AND pe.owner_id=al.owner_id AND pe.created_at>=?
        WHERE al.owner_id=? AND COALESCE(al.status,'active')='active'
        GROUP BY al.id, al.network, al.product_name, al.niche, al.url, al.product_score
        ORDER BY revenue DESC, clicks DESC, views DESC, jobs DESC, al.product_score DESC
        LIMIT ?""",
        (since, str(owner_id), limit)
    )
    affiliate_rows = c.fetchall()
    c.execute(
        """SELECT al.id, al.network, al.product_name, pj.id, pj.platform, pj.topic, pj.status, pj.publish_url,
                  SUM(CASE WHEN pe.event_type='view' THEN pe.value ELSE 0 END) AS views,
                  SUM(CASE WHEN pe.event_type='click' THEN pe.value ELSE 0 END) AS clicks,
                  SUM(CASE WHEN pe.event_type IN ('order','lead','revenue') THEN pe.amount ELSE 0 END) AS revenue,
                  MAX(COALESCE(pe.created_at, pj.updated_at, pj.created_at)) AS last_seen
        FROM production_jobs pj
        LEFT JOIN affiliate_links al ON al.id=pj.affiliate_id
        LEFT JOIN performance_events pe ON pe.job_id=pj.id AND pe.owner_id=pj.owner_id AND pe.created_at>=?
        WHERE pj.owner_id=? AND COALESCE(pj.affiliate_id,0)>0
        GROUP BY al.id, al.network, al.product_name, pj.id, pj.platform, pj.topic, pj.status, pj.publish_url
        ORDER BY revenue DESC, clicks DESC, views DESC, last_seen DESC
        LIMIT ?""",
        (since, str(owner_id), limit)
    )
    job_rows = c.fetchall()
    conn.close()
    return since, affiliate_rows, job_rows

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

def performance_source_from_note(note):
    note = str(note or "").strip()
    if not note:
        return "unknown"
    match = re.search(r"(?:^|\|\s*)src:([^|]+)", note, re.IGNORECASE)
    if match:
        return match.group(1).strip()[:80] or "unknown"
    first = note.split("|", 1)[0].strip()
    if ":" in first:
        key, value = first.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key in {"api", "affiliate_postback", "redirect_affiliate", "tiktok_affiliate", "manual", "n8n"}:
            return key if key != "api" or not value else value[:80]
    return first[:80] or "unknown"

def tracking_report_data(owner_id, days=30, limit=15):
    since = (datetime.now() - timedelta(days=max(1, int(days or 30)))).strftime("%Y-%m-%d %H:%M:%S")
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        """SELECT pe.affiliate_id, al.network, al.product_name, al.url,
                  pe.job_id, pj.topic, pe.platform, pe.event_type,
                  COALESCE(pe.value,0), COALESCE(pe.amount,0), COALESCE(pe.note,''), pe.created_at
        FROM performance_events pe
        LEFT JOIN affiliate_links al ON al.id=pe.affiliate_id
        LEFT JOIN production_jobs pj ON pj.id=pe.job_id
        WHERE pe.owner_id=? AND pe.created_at>=?
        ORDER BY pe.id DESC""",
        (str(owner_id), since)
    )
    rows = c.fetchall()
    conn.close()

    by_affiliate = {}
    by_source = {}
    by_job = {}

    def blank():
        return {"views": 0, "clicks": 0, "conversions": 0, "revenue": 0, "cost": 0, "events": 0}

    for aid, network, product, url, job_id, topic, platform, event_type, value, amount, note, created_at in rows:
        value = int(value or 0)
        amount = int(amount or 0)
        event_type = (event_type or "").lower()
        source = performance_source_from_note(note)
        aff_key = int(aid or 0)
        if aff_key not in by_affiliate:
            by_affiliate[aff_key] = {
                **blank(),
                "affiliate_id": aff_key,
                "network": network or "",
                "product": product or "",
                "url": url or "",
                "sources": set(),
            }
        source_key = (aff_key, source)
        if source_key not in by_source:
            by_source[source_key] = {
                **blank(),
                "affiliate_id": aff_key,
                "network": network or "",
                "product": product or "",
                "source": source,
            }
        job_key = int(job_id or 0)
        if job_key not in by_job:
            by_job[job_key] = {
                **blank(),
                "job_id": job_key,
                "affiliate_id": aff_key,
                "product": product or "",
                "topic": topic or "",
                "platform": platform or "",
            }
        for bucket in (by_affiliate[aff_key], by_source[source_key], by_job[job_key]):
            bucket["events"] += 1
            if event_type == "view":
                bucket["views"] += value
            elif event_type == "click":
                bucket["clicks"] += value
            elif event_type in {"order", "lead", "revenue"}:
                bucket["conversions"] += value
                bucket["revenue"] += amount
            elif event_type == "cost":
                bucket["cost"] += amount
        by_affiliate[aff_key]["sources"].add(source)

    def finalize(items):
        output = []
        for item in items:
            views = item["views"]
            clicks = item["clicks"]
            conversions = item["conversions"]
            revenue = item["revenue"]
            cost = item["cost"]
            score, ctr, cvr, roi = growth_score(views, clicks, conversions, revenue, cost)
            row = {**item, "score": score, "ctr": round(ctr, 2), "cvr": round(cvr, 2), "roi": round(roi, 1)}
            if isinstance(row.get("sources"), set):
                row["sources"] = sorted(row["sources"])
            output.append(row)
        output.sort(key=lambda x: (x["revenue"], x["conversions"], x["clicks"], x["views"], x["score"]), reverse=True)
        return output[:limit]

    return {
        "since": since,
        "days": days,
        "affiliates": finalize(by_affiliate.values()),
        "sources": finalize(by_source.values()),
        "jobs": finalize(by_job.values()),
    }

def scale_plan_action(item, min_clicks=20, min_views=200):
    views = int(item.get("views") or 0)
    clicks = int(item.get("clicks") or 0)
    conversions = int(item.get("conversions") or 0)
    revenue = int(item.get("revenue") or 0)
    cost = int(item.get("cost") or 0)
    score = int(item.get("score") or 0)
    if cost > 0 and revenue < cost and (views >= min_views or clicks >= min_clicks):
        return "PAUSE_CHECK", "Có chi phí nhưng doanh thu chưa bù chi phí; tạm dừng scale và kiểm tra offer/targeting."
    if revenue > 0 or conversions > 0 or score >= 45:
        return "SCALE", "Đã có tín hiệu doanh thu/chuyển đổi hoặc score đủ mạnh để tạo thêm biến thể."
    if views >= min_views and clicks == 0:
        return "FIX_CTA", "Có view nhưng chưa có click; cần sửa hook, caption, CTA hoặc vị trí link."
    if clicks >= min_clicks and conversions == 0:
        return "FIX_OFFER", "Có click nhưng chưa có đơn/lead; cần đổi offer, landing, sản phẩm liên quan hoặc góc nội dung."
    return "TEST_MORE", "Dữ liệu còn mỏng; tiếp tục test thêm creative/source trước khi scale."

def scale_plan_command(item, action, platform="tiktok"):
    aid = int(item.get("affiliate_id") or 0)
    job_id = int(item.get("job_id") or 0)
    platform = (item.get("platform") or platform or "tiktok").lower()
    if action == "SCALE" and aid:
        return f"/affiliate_scale aff={aid} platform={platform} channel=all limit=3 build=1 duration=45"
    if action == "FIX_CTA" and job_id:
        return f"/creative_test job={job_id} n=5"
    if action == "FIX_OFFER" and aid:
        return f"/affiliate_related aff={aid} limit=12"
    if action == "PAUSE_CHECK" and aid:
        return f"/tracking_report days=30 limit=20 và kiểm tra cost/revenue aff={aid}"
    if aid:
        return f"/affiliate_ideas aff={aid} platform={platform} n=5 topic=remix"
    return "/tracking_report days=30"

def scale_plan_data(owner_id, days=30, limit=10, platform="tiktok"):
    report = tracking_report_data(owner_id, days=days, limit=max(limit, 20))
    candidates = []
    for scope, rows in (("source", report["sources"]), ("job", report["jobs"]), ("affiliate", report["affiliates"])):
        for item in rows:
            if not item.get("affiliate_id") and not item.get("job_id"):
                continue
            action, reason = scale_plan_action(item)
            command = scale_plan_command(item, action, platform=platform)
            candidates.append({
                "scope": scope,
                "action": action,
                "reason": reason,
                "command": command,
                "affiliate_id": int(item.get("affiliate_id") or 0),
                "job_id": int(item.get("job_id") or 0),
                "source": item.get("source", ""),
                "product": item.get("product", ""),
                "topic": item.get("topic", ""),
                "platform": item.get("platform", platform),
                "score": int(item.get("score") or 0),
                "views": int(item.get("views") or 0),
                "clicks": int(item.get("clicks") or 0),
                "conversions": int(item.get("conversions") or 0),
                "revenue": int(item.get("revenue") or 0),
                "cost": int(item.get("cost") or 0),
                "ctr": item.get("ctr", 0),
                "cvr": item.get("cvr", 0),
                "roi": item.get("roi", 0),
            })
    action_rank = {"SCALE": 5, "FIX_OFFER": 4, "FIX_CTA": 3, "TEST_MORE": 2, "PAUSE_CHECK": 1}
    candidates.sort(
        key=lambda x: (
            action_rank.get(x["action"], 0),
            x["revenue"],
            x["conversions"],
            x["clicks"],
            x["score"],
        ),
        reverse=True,
    )
    return {
        "since": report["since"],
        "days": days,
        "platform": platform,
        "plans": candidates[:limit],
        "summary": {
            "scale": sum(1 for item in candidates if item["action"] == "SCALE"),
            "fix": sum(1 for item in candidates if item["action"] in {"FIX_CTA", "FIX_OFFER"}),
            "test": sum(1 for item in candidates if item["action"] == "TEST_MORE"),
            "pause": sum(1 for item in candidates if item["action"] == "PAUSE_CHECK"),
        },
    }

def affiliate_decision_label(score, views, clicks, conversions, revenue, cost, jobs, publishes, min_views=200):
    views = int(views or 0)
    clicks = int(clicks or 0)
    conversions = int(conversions or 0)
    revenue = int(revenue or 0)
    cost = int(cost or 0)
    jobs = int(jobs or 0)
    publishes = int(publishes or 0)
    if jobs == 0:
        return "TEST", "Chưa có job, cần tạo batch test nhỏ trước khi đánh giá."
    if publishes == 0:
        return "PUBLISH", "Đã có job nhưng chưa ghi nhận bài đăng, cần đưa vào publish queue hoặc đăng thủ công."
    if cost > 0 and revenue < cost and views >= min_views:
        return "PAUSE_CHECK", "Có chi phí nhưng doanh thu chưa bù chi phí, cần dừng scale và kiểm tra offer/targeting."
    if revenue > 0 or conversions > 0 or score >= 35:
        return "SCALE", "Đã có tín hiệu chuyển đổi/doanh thu hoặc điểm tăng trưởng đủ tốt."
    if views >= min_views and clicks == 0:
        return "FIX_CTA", "Có view nhưng chưa có click, cần sửa hook/caption/CTA/link placement."
    if clicks >= 20 and conversions == 0:
        return "FIX_OFFER", "Có click nhưng chưa có lead/order, cần đổi angle, sản phẩm kèm hoặc landing/offer."
    return "TEST_MORE", "Dữ liệu còn mỏng, tiếp tục test thêm creative và kênh."

def affiliate_decision_command(action, aid, niche, platform="tiktok", limit=3):
    safe_niche = niche or "affiliate"
    if action == "SCALE":
        return f"/affiliate_scale aff={aid} platform={platform} channel=all limit={limit} build=1 duration=45"
    if action == "PUBLISH":
        return "/publish_queue hoặc /mark_published job=<JOB_ID> url=https://... views=0 clicks=0"
    if action == "FIX_CTA":
        return f"/affiliate_ideas aff={aid} platform={platform} n=5 topic=sửa CTA cho {safe_niche}"
    if action == "FIX_OFFER":
        return f"/affiliate_related aff={aid} limit=12"
    if action == "PAUSE_CHECK":
        return f"/affiliate_report days=30 limit=20 và kiểm tra cost/revenue cho aff={aid}"
    return f"/affiliate_scale aff={aid} platform={platform} channel=all limit=2 build=1 duration=45"

def affiliate_decision_data(owner_id, days=30, limit=20, min_views=200, platform="tiktok"):
    since, affiliate_rows, job_rows = affiliate_performance_report_data(owner_id, days=days, limit=max(limit, 30))
    decisions = []
    for (
        aid, network, product, niche, url, product_score, jobs, publishes, views,
        clicks, conversions, revenue, cost, events
    ) in affiliate_rows[:limit]:
        score, ctr, cvr, roi = growth_score(views, clicks, conversions, revenue, cost)
        action, reason = affiliate_decision_label(score, views, clicks, conversions, revenue, cost, jobs, publishes, min_views)
        related = list_related_affiliate_links(owner_id, affiliate_id=aid, niche=niche or product, limit=6)
        related_links = [
            {
                "id": row[0],
                "network": row[1],
                "product": row[2],
                "niche": row[3],
                "url": row[4],
                "match_score": int(rel_score or 0),
                "reasons": reasons[:3],
            }
            for rel_score, reasons, row in related
        ]
        decisions.append({
            "id": aid,
            "network": network,
            "product": product,
            "niche": niche,
            "url": url,
            "action": action,
            "reason": reason,
            "score": score,
            "base_score": int(product_score or 0),
            "jobs": int(jobs or 0),
            "publishes": int(publishes or 0),
            "views": int(views or 0),
            "clicks": int(clicks or 0),
            "conversions": int(conversions or 0),
            "revenue": int(revenue or 0),
            "cost": int(cost or 0),
            "events": int(events or 0),
            "ctr": round(ctr, 2),
            "cvr": round(cvr, 2),
            "roi": round(roi, 1),
            "command": affiliate_decision_command(action, aid, niche or product, platform=platform),
            "related_links": related_links,
        })
    decisions.sort(key=lambda item: (
        {"SCALE": 5, "PUBLISH": 4, "FIX_CTA": 3, "FIX_OFFER": 3, "TEST_MORE": 2, "TEST": 1, "PAUSE_CHECK": 0}.get(item["action"], 0),
        item["score"],
        item["revenue"],
        item["clicks"],
    ), reverse=True)
    return since, decisions, job_rows

def operator_director_data(owner_id, days=30, platform="tiktok", limit=10):
    status = operator_status_data(owner_id)
    since, decisions, _ = affiliate_decision_data(owner_id, days=days, limit=limit, platform=platform)
    advanced, ready_publish, next_tasks, blocked = operator_loop_data(owner_id, limit=limit, auto_queue=False)
    actions = []

    for key, ok, detail, next_cmd in status["checks"]:
        if not ok:
            actions.append({
                "rank": len(actions) + 1,
                "action": "SETUP",
                "priority": "high",
                "title": f"Hoàn thiện {key}",
                "detail": detail,
                "telegram_command": next_cmd,
                "api": None,
            })

    if blocked:
        jid, level, next_action, topic, action_platform, channel_name = blocked[0]
        actions.append({
            "rank": len(actions) + 1,
            "action": "FIX_BLOCKED_JOB",
            "priority": "high",
            "title": f"Gỡ nghẽn job #{jid}",
            "detail": f"{action_platform or '-'} | {channel_name or '-'} | {topic or '-'} | {level or '-'}",
            "telegram_command": next_action or f"/job_ready job={jid}",
            "api": {"method": "GET", "url": f"/api/operator/jobs/{jid}/ready"},
        })

    if next_tasks:
        tid, job_id, task_type, tool, scene_no, title, task_status, topic, action_platform, channel_name = next_tasks[0]
        url = f"/api/operator/tasks/next?job_id={job_id}"
        if tool:
            url += f"&tool={tool}"
        actions.append({
            "rank": len(actions) + 1,
            "action": "WORK_TASK",
            "priority": "high",
            "title": f"Worker làm task #{tid}",
            "detail": f"job #{job_id} | {task_type or '-'} / {tool or '-'} | scene={scene_no or '-'} | {title or topic or '-'}",
            "telegram_command": f"/task_handoff id={tid}",
            "api": {"method": "GET", "url": url, "submit_after": f"/api/operator/tasks/{tid}/complete"},
        })

    if ready_publish:
        jid, topic, action_platform, channel_name = ready_publish[0]
        actions.append({
            "rank": len(actions) + 1,
            "action": "PUBLISH_READY",
            "priority": "medium",
            "title": f"Đăng job #{jid}",
            "detail": f"{action_platform or '-'} | {channel_name or '-'} | {topic or '-'}",
            "telegram_command": f"/publish_pack job={jid}",
            "api": {"method": "GET", "url": f"/api/operator/publish/next?platform={action_platform or ''}"},
        })

    for decision in decisions:
        decision_action = decision.get("action")
        if decision_action == "SCALE":
            actions.append({
                "rank": len(actions) + 1,
                "action": "SCALE_AFFILIATE",
                "priority": "medium",
                "title": f"Scale affiliate #{decision['id']}: {decision.get('product') or '-'}",
                "detail": f"score={decision['score']} views={decision['views']} clicks={decision['clicks']} revenue={decision['revenue']:,}đ",
                "telegram_command": decision["command"],
                "api": {
                    "method": "POST",
                    "url": "/api/operator/affiliate-scale",
                    "payload": {
                        "affiliate_id": int(decision["id"]),
                        "platform": platform,
                        "channel": "all",
                        "limit": 3,
                        "build": True,
                        "duration": 45,
                        "notify_admin": True,
                    },
                },
                "related_links": decision.get("related_links", [])[:5],
            })
            break

    if not any(item["action"] == "SCALE_AFFILIATE" for item in actions):
        fix_decision = next((item for item in decisions if item.get("action") in {"PUBLISH", "FIX_CTA", "FIX_OFFER", "TEST", "TEST_MORE"}), None)
        if fix_decision:
            actions.append({
                "rank": len(actions) + 1,
                "action": f"AFFILIATE_{fix_decision['action']}",
                "priority": "medium",
                "title": f"{fix_decision['action']} affiliate #{fix_decision['id']}: {fix_decision.get('product') or '-'}",
                "detail": fix_decision.get("reason") or "",
                "telegram_command": fix_decision["command"],
                "api": {"method": "GET", "url": f"/api/operator/affiliate-decisions?days={days}&platform={platform}&limit={limit}"},
                "related_links": fix_decision.get("related_links", [])[:5],
            })

    if not actions:
        actions.append({
            "rank": 1,
            "action": "START_TEST",
            "priority": "medium",
            "title": "Bắt đầu batch test affiliate",
            "detail": "Không có task/publish/job nghẽn rõ ràng. Hãy chọn affiliate có base score tốt để test.",
            "telegram_command": f"/affiliate_decisions days={days} platform={platform} limit={limit}",
            "api": {"method": "GET", "url": f"/api/operator/affiliate-decisions?days={days}&platform={platform}&limit={limit}"},
        })

    return {
        "status": status,
        "since": since,
        "platform": platform,
        "decisions": decisions[:limit],
        "actions": actions[:limit],
        "next_action": actions[0] if actions else None,
        "rule": "Director ưu tiên setup/blocker/task/publish trước, sau đó mới scale affiliate có tín hiệu tốt.",
    }

async def execute_operator_director_action(owner_id, action, build=True, duration=45):
    if not action:
        return {"executed": False, "message": "Không có action để chạy."}
    action_type = action.get("action") or ""
    if action_type == "SCALE_AFFILIATE":
        payload = ((action.get("api") or {}).get("payload") or {}).copy()
        affiliate_id = int(payload.get("affiliate_id") or 0)
        if not affiliate_id:
            return {"executed": False, "message": "SCALE_AFFILIATE thiếu affiliate_id."}
        affiliate = get_affiliate_link(affiliate_id, owner_id)
        if not affiliate:
            return {"executed": False, "message": "Không tìm thấy affiliate."}
        aid, network, product, affiliate_niche, url, note, status, price_vnd, commission_rate, audience, allowed_claims, blocked_claims, product_score = affiliate
        scale_niche = payload.get("niche") or affiliate_niche or product or "affiliate"
        platform = (payload.get("platform") or "tiktok").lower()
        channel = payload.get("channel") or "all"
        limit = max(1, min(int(payload.get("limit") or 3), 12))
        campaign_id = int(payload.get("campaign_id") or 0)
        if not campaign_id:
            matched_campaign, _ = find_matching_campaign(owner_id, scale_niche, platform)
            if matched_campaign:
                campaign_id = matched_campaign[0]
        created_jobs, error = await create_operator_auto_jobs(owner_id, scale_niche, platform, channel, campaign_id, affiliate_id, limit)
        if error:
            return {"executed": False, "message": error, "action": action_type}
        built = []
        failed = []
        if build:
            for item in created_jobs:
                ok, bundle = build_operator_job_bundle(owner_id, item["job_id"], count=5, duration=duration)
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
                    failed.append({"job_id": item["job_id"], "error": bundle.get("error", "build lỗi")})
        return {
            "executed": True,
            "action": action_type,
            "affiliate_id": affiliate_id,
            "scale_niche": scale_niche,
            "campaign_id": campaign_id,
            "created_jobs": created_jobs,
            "built_jobs": built,
            "failed_builds": failed,
            "next": {"tasks_url": "/api/operator/tasks/next", "publish_url": "/api/operator/publish/next"},
        }
    if action_type == "PUBLISH_READY":
        match = re.search(r"job[ =#]*(\d+)", action.get("telegram_command", "") + " " + action.get("title", ""))
        job_id = int(match.group(1)) if match else 0
        if not job_id:
            return {"executed": False, "message": "PUBLISH_READY thiếu job_id."}
        job = get_production_job(job_id, owner_id)
        if job and (job[8] or "").lower() != "approved":
            return {
                "executed": False,
                "action": action_type,
                "job_id": job_id,
                "message": "Job đã đủ điều kiện nhưng chưa có duyệt cuối. Admin cần /approve_publish trước khi queue đăng.",
                "telegram_command": f"/approve_publish job={job_id} queue=1 mode=manual",
                "api": {"method": "POST", "url": f"/api/operator/jobs/{job_id}/approve"},
            }
        ok, queue_id = create_publish_queue_item(owner_id, job_id, mode="manual", scheduled_at="", note="director_execute_queue")
        return {
            "executed": bool(ok),
            "action": action_type,
            "job_id": job_id,
            "queue_id": queue_id if ok else 0,
            "message": "Đã đưa vào publish queue manual." if ok else str(queue_id),
            "next": {"publish_pack_url": f"/api/operator/jobs/{job_id}/publish-pack", "publish_next_url": "/api/operator/publish/next"},
        }
    if action_type == "WORK_TASK":
        return {
            "executed": False,
            "action": action_type,
            "message": "Task cần worker AI/tool xử lý qua GET /api/operator/tasks/next; director không tự giả lập output.",
            "next": action.get("api") or {"method": "GET", "url": "/api/operator/tasks/next"},
        }
    return {
        "executed": False,
        "action": action_type,
        "message": "Action này cần admin cấu hình/xác nhận thủ công.",
        "telegram_command": action.get("telegram_command", ""),
        "api": action.get("api"),
    }

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
        if level == "READY_TO_QUEUE" and auto_queue and (status or "").lower() == "approved":
            ok, queue_id = create_publish_queue_item(owner_id, jid, mode="manual", scheduled_at="", note="operator_loop_auto_queue")
            if ok:
                advanced.append((jid, "queued_publish", queue_id, topic, platform, channel_name))
                continue
        if level == "READY_TO_QUEUE" and auto_queue:
            blocked.append((jid, "NEEDS_APPROVAL", f"/approve_publish job={jid} queue=1 mode=manual", topic, platform, channel_name))
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
                  sc.publish_mode, sc.token_env, sc.page_id,
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
        scheduled_at, publish_url, note, updated_at, publish_mode, token_env, page_id, topic, asset_url, brief_text,
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
    job = get_production_job(job_id, ADMIN_ID)
    static_pack = build_static_publish_pack(job, ADMIN_ID) if job else {}
    return {
        "id": qid,
        "job_id": job_id,
        "channel_id": channel_id,
        "platform": platform,
        "channel_name": channel_name,
        "account_label": account_label,
        "mode": mode,
        "channel_publish_mode": publish_mode,
        "token_env": token_env,
        "page_id": page_id,
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
            "caption": caption or static_pack.get("caption", ""),
            "cta": cta or static_pack.get("cta", ""),
            "hashtags": hashtags or static_pack.get("hashtags", ""),
            "affiliate_placement": affiliate_url,
            "pinned_comment": static_pack.get("pinned_comment", ""),
            "related_links": static_pack.get("related_links", []),
            "disclosure": static_pack.get("disclosure", ""),
            "checklist": static_pack.get("checklist", []),
            "performance_plan": static_pack.get("performance_plan", {}),
        },
        "rule": "Publish only approved/queued jobs. Keep affiliate disclosure and platform rules.",
    }

def build_publisher_handoff(queue_payload):
    if not queue_payload:
        return {}
    platform = (queue_payload.get("platform") or "").lower()
    mode = (queue_payload.get("mode") or queue_payload.get("channel_publish_mode") or "manual").lower()
    pack = queue_payload.get("publish_pack") or {}
    final_video = queue_payload.get("final_video") or {}
    media_url = final_video.get("url") or queue_payload.get("asset_url") or ""
    caption_parts = [
        pack.get("caption", ""),
        pack.get("cta", ""),
        pack.get("hashtags", ""),
    ]
    caption = "\n\n".join([part for part in caption_parts if part]).strip()
    pinned_comment = pack.get("pinned_comment") or ""
    related_links = pack.get("related_links") or []
    if platform in {"tiktok", "tiktokshop"}:
        api_plan = [
            "Dùng TikTok Content Posting API chính thức nếu channel api_ready.",
            "Upload video 9:16, caption ngắn, hashtag rõ ràng.",
            "Nếu TikTok không cho link ngoài trong caption, đưa tracking URL vào bio/comment ghim/manual note.",
        ]
        required_env = [queue_payload.get("token_env") or "TIKTOK_ACCESS_TOKEN"]
    elif platform in {"facebook", "fb", "reels", "instagram"}:
        api_plan = [
            "Dùng Meta Graph API chính thức cho Page/Reels nếu channel api_ready.",
            "Đăng video/reel với caption, disclosure affiliate và CTA.",
            "Link affiliate chính/related nên đưa vào caption hoặc comment đầu tùy chính sách page.",
        ]
        required_env = [queue_payload.get("token_env") or "META_PAGE_ACCESS_TOKEN", "page_id=" + str(queue_payload.get("page_id") or "<PAGE_ID>")]
    elif platform in {"onlyfan", "onlyfans"}:
        api_plan = [
            "OnlyFans không có public API ổn định cho auto-post đại trà; ưu tiên manual hoặc automation có consent/ToS rõ ràng.",
            "Không đăng nội dung người thật/AI influencer nếu thiếu consent, tuổi 18+ và quyền thương mại.",
            "Dùng pack này làm checklist đăng thủ công, sau đó trả publish_url qua complete endpoint.",
        ]
        required_env = []
    else:
        api_plan = [
            "Dùng kênh manual/API chính thức của nền tảng.",
            "Giữ disclosure affiliate, không spam link và không mạo danh.",
        ]
        required_env = [queue_payload.get("token_env")] if queue_payload.get("token_env") else []
    return {
        "queue_id": queue_payload.get("id"),
        "job_id": queue_payload.get("job_id"),
        "platform": platform or "social",
        "mode": mode,
        "can_auto_publish": mode == "api" and bool(queue_payload.get("token_env")),
        "required_env": [item for item in required_env if item],
        "media": {
            "final_video_url": media_url,
            "telegram_file_id": final_video.get("file_id", ""),
            "required": "final_video_url hoặc telegram_file_id",
        },
        "copy": {
            "caption": caption,
            "pinned_comment": pinned_comment,
            "related_links": related_links,
            "disclosure": pack.get("disclosure", ""),
        },
        "api_plan": api_plan,
        "manual_steps": [
            "Tải final video từ media.",
            "Đăng lên đúng account/channel.",
            "Dán caption, disclosure, CTA và link liên quan phù hợp.",
            "Kiểm tra bài hiển thị công khai.",
            f"Gọi POST /api/operator/publish/{queue_payload.get('id')}/complete với publish_url thật.",
        ],
        "complete_payload": {
            "status": "published",
            "publish_url": "https://...",
            "views": 0,
            "clicks": 0,
            "note": f"published_by_{platform or 'worker'}",
        },
        "performance_next": (pack.get("performance_plan") or {}),
        "rule": "Không publish nếu thiếu final video, thiếu consent/quyền nội dung, hoặc review gate/publish queue chưa duyệt.",
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
    related_affiliates = list_related_affiliate_links(owner_id, affiliate_id=affiliate_id, niche=niche, limit=8) if affiliate_id else []
    related_note = format_related_affiliate_links(related_affiliates, max_items=6)
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
                + (f" | related_affiliates={related_note}" if related_note else "")
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
                    build_production_prompt(slot)
                    + f"\n\nNguồn trend: {item['url']}\nTóm tắt trend: {item.get('summary','')}"
                    + (f"\n\nLink affiliate liên quan để chèn caption/comment/status:\n{related_note}" if related_note else ""),
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

async def execute_scale_plan_actions(owner_id, days=30, platform="tiktok", limit=5, per_affiliate_limit=3, build=True, duration=45, notify_admin=False):
    plan = scale_plan_data(owner_id, days=days, limit=max(limit * 3, 10), platform=platform)
    executed = []
    skipped = []
    seen_affiliates = set()
    for item in plan["plans"]:
        if len(executed) >= limit:
            break
        aid = int(item.get("affiliate_id") or 0)
        if item.get("action") != "SCALE":
            skipped.append({**item, "skip_reason": "not_scale_action"})
            continue
        if not aid:
            skipped.append({**item, "skip_reason": "missing_affiliate_id"})
            continue
        if aid in seen_affiliates:
            skipped.append({**item, "skip_reason": "duplicate_affiliate_in_batch"})
            continue
        affiliate = get_affiliate_link(aid, owner_id)
        if not affiliate:
            skipped.append({**item, "skip_reason": "affiliate_not_found"})
            continue
        (
            _aid, network, product, affiliate_niche, url, note, status,
            price_vnd, commission_rate, audience, allowed_claims, blocked_claims, product_score
        ) = affiliate
        if (status or "active").lower() != "active":
            skipped.append({**item, "skip_reason": "affiliate_inactive"})
            continue
        scale_niche = affiliate_niche or product or item.get("topic") or "affiliate"
        matched_campaign, campaign_score = find_matching_campaign(owner_id, scale_niche, platform)
        campaign_id = matched_campaign[0] if matched_campaign else 0
        created_jobs, error = await create_operator_auto_jobs(
            owner_id,
            scale_niche,
            platform,
            "all",
            campaign_id,
            aid,
            per_affiliate_limit,
        )
        if error:
            skipped.append({**item, "skip_reason": error})
            continue
        built = []
        failed = []
        if build:
            for created in created_jobs:
                ok, bundle = build_operator_job_bundle(owner_id, created["job_id"], count=5, duration=duration)
                if ok:
                    built.append({
                        "job_id": created["job_id"],
                        "manifest_id": bundle.get("manifest_id"),
                        "task_count": len(bundle.get("task_ids") or []),
                        "variant_id": bundle.get("best_variant_id"),
                        "readiness": (bundle.get("readiness") or {}).get("level", "UNKNOWN"),
                    })
                else:
                    failed.append({"job_id": created["job_id"], "error": bundle.get("error", "build lỗi") if isinstance(bundle, dict) else "build lỗi"})
        seen_affiliates.add(aid)
        executed.append({
            **item,
            "affiliate": {"id": aid, "network": network, "product": product, "niche": affiliate_niche},
            "campaign": {
                "id": campaign_id,
                "name": matched_campaign[1] if matched_campaign else "",
                "match_score": campaign_score,
            },
            "created_jobs": created_jobs,
            "built_jobs": built,
            "failed_builds": failed,
        })
    if notify_admin and tg_app and ADMIN_ID:
        try:
            await tg_app.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    "🎯 <b>SCALE PLAN EXECUTED</b>\n\n"
                    f"• Executed: <b>{len(executed)}</b>\n"
                    f"• Skipped: <b>{len(skipped)}</b>\n"
                    f"• Platform: <code>{html.escape(platform)}</code>\n"
                    f"• Next: <code>/tasks</code> hoặc <code>/operator_loop</code>"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Scale plan execute notify error: {e}")
    return {"plan": plan, "executed": executed, "skipped": skipped}

async def make_video_pipeline(owner_id, topic, platform="tiktok", channel="all", affiliate_id=0, campaign_id=0, limit=3, build=True, duration=45, variants=5):
    topic = (topic or "").strip()
    if not topic:
        return False, "missing_topic", {}
    platform = (platform or "tiktok").lower()
    channel = (channel or "all").lower()

    selected_affiliate = get_affiliate_link(affiliate_id, owner_id) if affiliate_id else None
    affiliate_score = 0
    affiliate_hits = 0
    if affiliate_id and not selected_affiliate:
        return False, "affiliate_not_found", {}
    if not selected_affiliate:
        matches = list_affiliate_matches(owner_id, niche=topic, trend_text=topic, platform=platform, limit=5)
        if matches:
            affiliate_score, affiliate_hits, _blocked, selected_affiliate = matches[0]
            affiliate_id = selected_affiliate[0]

    selected_campaign = get_campaign(campaign_id, owner_id) if campaign_id else None
    campaign_score = 0
    if campaign_id and not selected_campaign:
        return False, "campaign_not_found", {}
    if not selected_campaign:
        selected_campaign, campaign_score = find_matching_campaign(owner_id, topic, platform)
        campaign_id = selected_campaign[0] if selected_campaign else 0

    created_jobs, error = await create_operator_auto_jobs(
        owner_id,
        topic,
        platform,
        channel,
        campaign_id,
        affiliate_id,
        limit,
    )
    if error:
        return False, error, {
            "affiliate_id": affiliate_id,
            "campaign_id": campaign_id,
            "topic": topic,
            "platform": platform,
            "channel": channel,
        }

    built = []
    failed = []
    publish_packs = []
    if build:
        for item in created_jobs:
            ok, bundle = build_operator_job_bundle(owner_id, item["job_id"], count=variants, duration=duration)
            if ok:
                readiness = bundle.get("readiness") or {}
                built_item = {
                    **item,
                    "manifest_id": bundle.get("manifest_id"),
                    "task_count": len(bundle.get("task_ids") or []),
                    "variant_id": bundle.get("best_variant_id"),
                    "readiness": readiness.get("level", "UNKNOWN") if isinstance(readiness, dict) else "UNKNOWN",
                }
                built.append(built_item)
                job = get_production_job(item["job_id"], owner_id)
                if job:
                    pack = build_static_publish_pack(job, owner_id)
                    publish_packs.append({
                        "job_id": item["job_id"],
                        "caption": pack.get("caption", ""),
                        "tracking_url": (pack.get("primary_affiliate") or {}).get("tracking_url", ""),
                        "related_links": pack.get("related_affiliates", [])[:6],
                        "disclosure": pack.get("disclosure", ""),
                    })
            else:
                failed.append({"job_id": item["job_id"], "error": bundle.get("error", "build lỗi") if isinstance(bundle, dict) else "build lỗi"})

    affiliate_payload = None
    if selected_affiliate:
        aid, network, product, niche, url, note, status, *_rest = selected_affiliate
        affiliate_payload = {
            "id": aid,
            "network": network,
            "product": product,
            "niche": niche,
            "url": url,
            "match_score": affiliate_score,
            "match_hits": affiliate_hits,
        }

    campaign_payload = None
    if selected_campaign:
        if len(selected_campaign) >= 8:
            campaign_name = selected_campaign[2]
            campaign_niche = selected_campaign[3]
            campaign_platforms = selected_campaign[4]
        else:
            campaign_name = selected_campaign[1]
            campaign_niche = selected_campaign[2]
            campaign_platforms = selected_campaign[3]
        campaign_payload = {
            "id": selected_campaign[0],
            "name": campaign_name,
            "niche": campaign_niche,
            "platforms": campaign_platforms,
            "match_score": campaign_score,
        }

    return True, "ok", {
        "topic": topic,
        "platform": platform,
        "channel": channel,
        "affiliate": affiliate_payload,
        "campaign": campaign_payload,
        "created_jobs": created_jobs,
        "built_jobs": built,
        "failed_builds": failed,
        "publish_packs": publish_packs,
    }

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
    related = list_related_affiliate_links(ADMIN_ID, affiliate_id=affiliate_id, niche=topic or product_name or "", limit=8) if affiliate_id else []
    related_note = format_related_affiliate_links(related, max_items=6)
    platform_key = (platform or "").lower()
    if platform_key in {"onlyfans", "of"}:
        platform_rule = (
            "OnlyFans: chỉ dùng người thật có consent rõ ràng hoặc nhân vật AI tự tạo; tất cả nhân vật phải đủ 18 tuổi; "
            "không mạo danh người thật/creator khác; không dùng ảnh người khác để gợi dục hoặc lừa đảo."
        )
    elif platform_key in {"tiktok", "tik tok"}:
        platform_rule = (
            "TikTok: hook nhanh, caption gọn, affiliate disclosure rõ, tránh claim tài chính quá mức, tránh spam link trong mô tả; "
            "nếu cần nhiều link thì đưa link chính ở bio/mô tả và link liên quan ở comment ghim/status."
        )
    elif platform_key in {"facebook", "fb", "reels"}:
        platform_rule = (
            "Facebook/Reels: caption có ngữ cảnh, disclosure affiliate, link chính trong post/comment ghim, không bait tương tác giả tạo."
        )
    else:
        platform_rule = "Nền tảng bất kỳ: minh bạch affiliate, không spam, không mạo danh, không cam kết kết quả tài chính."
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
        f"Link liên quan để chèn caption/comment/status:\n{related_note or '-'}\n"
        f"Asset URL: {asset_url or 'chưa có'}\n"
        f"Publish URL hiện tại: {publish_url or 'chưa có'}\n"
        f"Ghi chú: {note or '-'}\n\n"
        f"Luật nền tảng:\n{platform_rule}\n\n"
        f"Brief/job context:\n{brief or 'Chưa có brief'}\n\n"
        "Trả về tiếng Việt theo format:\n"
        "1. Caption chính theo nền tảng.\n"
        "2. Caption ngắn A/B.\n"
        "3. Hashtag.\n"
        "4. CTA và vị trí gắn link affiliate chính.\n"
        "5. Link liên quan nên đưa vào comment ghim/status/mô tả, chỉ chọn link thật sự liên quan.\n"
        "6. Checklist trước khi đăng.\n"
        "7. Kế hoạch đo hiệu quả sau đăng: publish_url, view, click, order/lead, revenue, cost bằng /mark_published và /performance_add."
    )

def build_static_publish_pack(job, owner_id=ADMIN_ID):
    (
        jid, calendar_id, campaign_id, channel_id, affiliate_id, platform, topic, stage, status,
        note, brief, asset_url, publish_url, channel_name, account_label, network, product_name, affiliate_url
    ) = job
    related = list_related_affiliate_links(owner_id, affiliate_id=affiliate_id, niche=topic or product_name or "", limit=8) if affiliate_id else []
    related_links = [
        {
            "id": row[0],
            "network": row[1],
            "product": row[2],
            "niche": row[3],
            "url": row[4],
            "tracking_url": affiliate_tracking_url(row[0], jid, f"{platform or 'social'}_related"),
            "match_score": int(score or 0),
            "reasons": reasons[:3],
        }
        for score, reasons, row in related
    ]
    primary_tracking_url = affiliate_tracking_url(affiliate_id, jid, f"{platform or 'social'}_primary") if affiliate_id else ""
    primary_display_url = primary_tracking_url or affiliate_url
    disclosure = "Có thể nhận hoa hồng affiliate nếu người xem mua/đăng ký qua link."
    caption = (
        f"{topic or product_name or 'Gợi ý sản phẩm/dịch vụ'}\n\n"
        f"Link chính: {primary_display_url or 'chưa có'}\n"
        f"{disclosure}"
    )
    pinned_comment_parts = []
    if primary_display_url:
        pinned_comment_parts.append(f"Link chính: {primary_display_url}")
    for item in related_links[:5]:
        pinned_comment_parts.append(f"{item['product']}: {item.get('tracking_url') or item['url']}")
    checklist = [
        "Đã kiểm tra quyền hình ảnh/voice/nhạc.",
        "Đã ghi disclosure affiliate rõ ràng.",
        "Không hứa thu nhập/lãi suất/kết quả phê duyệt.",
        "Không mạo danh thương hiệu/người thật.",
        "Nếu nội dung người mẫu/OnlyFans: nhân vật tự tạo hoặc có consent, đủ 18 tuổi.",
        "Sau đăng ghi /mark_published và /performance_add.",
    ]
    return {
        "job_id": jid,
        "platform": platform,
        "channel_name": channel_name,
        "account_label": account_label,
        "topic": topic,
        "primary_affiliate": {
            "id": affiliate_id,
            "network": network,
            "product": product_name,
            "url": affiliate_url,
            "tracking_url": primary_tracking_url,
        },
        "related_links": related_links,
        "caption": caption,
        "pinned_comment": "\n".join(pinned_comment_parts),
        "hashtags": "#review #affiliate #muasamthongminh #AI",
        "cta": "Xem link chính và các lựa chọn liên quan trong mô tả/comment ghim.",
        "disclosure": disclosure,
        "checklist": checklist,
        "performance_plan": {
            "after_publish": f"/mark_published job={jid} url=https://... views=0 clicks=0 note=...",
            "views": f"/performance_add job={jid} type=view value=<VIEWS>",
            "clicks": f"/performance_add job={jid} type=click value=<CLICKS>",
            "orders": f"/performance_add job={jid} type=order value=<ORDERS> amount=<REVENUE>",
            "revenue": f"/performance_add job={jid} type=revenue value=1 amount=<REVENUE>",
            "cost": f"/performance_add job={jid} type=cost value=1 amount=<COST>",
        },
    }

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

class OperatorApprovePublishRequest(BaseModel):
    queue: bool = True
    mode: str = Field(default="manual", max_length=20)
    scheduled_at: str = Field(default="", max_length=80)
    note: str = Field(default="", max_length=1200)
    notify_admin: bool = True

class OperatorPerformanceRequest(BaseModel):
    job_id: int = Field(gt=0)
    event_type: str = Field(default="click", max_length=40)
    value: int = Field(default=1, ge=0)
    amount: int = Field(default=0, ge=0)
    variant_id: int = Field(default=0, ge=0)
    note: str = Field(default="", max_length=1200)
    source: str = Field(default="api", max_length=120)

class AffiliatePostbackRequest(BaseModel):
    job_id: int = Field(default=0, ge=0)
    affiliate_id: int = Field(default=0, ge=0)
    event_type: str = Field(default="order", max_length=40)
    value: int = Field(default=1, ge=0)
    amount: int = Field(default=0, ge=0)
    order_id: str = Field(default="", max_length=160)
    source: str = Field(default="affiliate_postback", max_length=120)
    note: str = Field(default="", max_length=1200)
    token: str = Field(default="", max_length=240)

class OperatorToolEventRequest(BaseModel):
    stage: str = Field(default="", max_length=80)
    tool_name: str = Field(default="", max_length=120)
    event_type: str = Field(default="error", max_length=40)
    severity: str = Field(default="warning", max_length=40)
    job_id: int = Field(default=0, ge=0)
    task_id: int = Field(default=0, ge=0)
    fallback_tool: str = Field(default="", max_length=120)
    message: str = Field(default="", max_length=1500)
    notify_admin: bool = True

class OperatorLoopRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=30)
    auto_queue: bool = True
    notify_admin: bool = True

class OperatorAffiliateScaleRequest(BaseModel):
    affiliate_id: int = Field(gt=0)
    niche: str = Field(default="", max_length=240)
    platform: str = Field(default="tiktok", max_length=40)
    channel: str = Field(default="all", max_length=40)
    campaign_id: int = Field(default=0, ge=0)
    limit: int = Field(default=3, ge=1, le=12)
    build: bool = False
    duration: int = Field(default=45, ge=15, le=120)
    variants: int = Field(default=5, ge=3, le=8)
    notify_admin: bool = True

class OperatorMakeVideoRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=300)
    platform: str = Field(default="tiktok", max_length=40)
    channel: str = Field(default="all", max_length=40)
    affiliate_id: int = Field(default=0, ge=0)
    campaign_id: int = Field(default=0, ge=0)
    limit: int = Field(default=3, ge=1, le=8)
    build: bool = True
    duration: int = Field(default=45, ge=15, le=120)
    variants: int = Field(default=5, ge=3, le=8)
    notify_admin: bool = True

class OperatorDirectorRunRequest(BaseModel):
    days: int = Field(default=30, ge=1, le=180)
    platform: str = Field(default="tiktok", max_length=40)
    limit: int = Field(default=10, ge=3, le=20)
    execute: bool = True
    build: bool = True
    duration: int = Field(default=45, ge=15, le=120)
    notify_admin: bool = True

class OperatorScalePlanRunRequest(BaseModel):
    days: int = Field(default=30, ge=1, le=180)
    platform: str = Field(default="tiktok", max_length=40)
    limit: int = Field(default=3, ge=1, le=10)
    per_affiliate_limit: int = Field(default=3, ge=1, le=8)
    build: bool = True
    duration: int = Field(default=45, ge=15, le=120)
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
            "• /operator_menu — Menu nút theo thư mục: Trend, Affiliate, Sản xuất, Đăng bài, Doanh thu, API",
            "• /brain &lt;lệnh&gt; — Ra lệnh tự nhiên cho AI Operator",
            "• /autopilot — Tìm trend, tạo job và build production bundle",
            "• /affiliate_scale — Chọn affiliate rồi tự tạo batch video theo trend",
            "• /dashboard — Dashboard quản trị hệ thống",
            "• /checkpayos &lt;mã_đơn&gt; — Kiểm tra lại đơn PayOS",
            "• /tools và /mmo — Kho công cụ/quy trình nội bộ Admin",
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

def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
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
    build_requested = any(word in lower for word in ["build", "dựng", "dung", "xây", "xay", "tạo bundle", "tao bundle", "build luôn", "build luon"])
    days = int_from_text(lower, ["days", "ngày", "ngay"], 30) or 30

    if any(word in lower for word in ["execute", "thực thi", "thuc thi", "chạy bước tiếp", "chay buoc tiep", "tự xử lý", "tu xu ly", "đầu não chạy", "dau nao chay"]):
        return {
            "intent": "operator_execute",
            "platform": platform,
            "limit": max(3, min(limit, 20)),
            "duration": duration,
            "build": 1 if build_requested or "build" in lower else 1,
            "days": max(1, min(days, 180)),
            "confidence": 82,
        }
    if any(word in lower for word in ["director", "đầu não", "dau nao", "việc tiếp theo", "viec tiep theo", "next action", "nên làm gì", "nen lam gi"]):
        return {
            "intent": "operator_director",
            "platform": platform,
            "limit": max(3, min(limit, 20)),
            "days": max(1, min(days, 180)),
            "confidence": 80,
        }

    if any(word in lower for word in ["ready", "sẵn sàng", "san sang", "đủ điều kiện", "du dieu kien"]):
        return {"intent": "job_ready", "job": job_id, "confidence": 70}
    if affiliate_id and any(word in lower for word in ["scale", "nhân rộng", "nhan rong", "đẩy link", "day link", "affiliate", "link này", "link nay"]):
        niche = re.sub(r"\b(scale|nhân rộng|nhan rong|đẩy link|day link|affiliate|aff|link này|link nay|tạo|tao|làm|lam|video|trend|cho|trên|tren|kênh|kenh|campaign|camp|limit|job|build|luôn|luon)\b", " ", lower)
        niche = re.sub(r"\b(tiktok|facebook|fb|youtube|shorts|onlyfan|onlyfans|reels)\b", " ", niche)
        niche = re.sub(r"\s+", " ", niche).strip(" :=#")
        return {
            "intent": "affiliate_scale",
            "niche": niche,
            "platform": platform,
            "channel": channel_id or "all",
            "affiliate": affiliate_id,
            "campaign": campaign_id,
            "limit": max(1, min(limit, 12)),
            "duration": duration,
            "build": 1 if build_requested else 0,
            "confidence": 78,
        }
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
    if "video" in lower and any(word in lower for word in ["tạo", "tao", "làm", "lam", "kiếm tiền", "kiem tien", "affiliate", "bán hàng", "ban hang"]):
        niche = re.sub(r"\b(tạo|tao|làm|lam|video|trend|viral|mới nhất|moi nhat|cho|trên|tren|kênh|kenh|gắn|gan|link|affiliate|aff|campaign|camp|limit|job)\b", " ", lower)
        niche = re.sub(r"\b(tiktok|facebook|fb|youtube|shorts|onlyfan|onlyfans|reels)\b", " ", niche)
        niche = re.sub(r"\s+", " ", niche).strip(" :=#") or "công nghệ AI"
        return {
            "intent": "make_video",
            "niche": niche,
            "topic": niche,
            "platform": platform,
            "channel": channel_id or "all",
            "affiliate": affiliate_id,
            "campaign": campaign_id,
            "limit": max(1, min(limit, 8)),
            "duration": duration,
            "build": 1,
            "confidence": 72,
        }
    if any(word in lower for word in ["trend", "viral", "mới nhất", "moi nhat"]):
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
        "Chỉ chọn một intent trong: operator_director, operator_execute, make_video, affiliate_scale, autopilot, operator_auto, operator, operator_build, job_ready, operator_daily, trend_search, publish_queue, performance, help.\n\n"
        "Quy tắc:\n"
        "- operator_director: khi admin hỏi đầu não nên làm gì, việc tiếp theo, next action.\n"
        "- operator_execute: khi admin yêu cầu đầu não tự chạy/thực thi bước tiếp theo an toàn.\n"
        "- affiliate_scale: khi admin muốn scale/đẩy một link affiliate cụ thể thành nhiều video theo trend; cần affiliate/aff ID.\n"
        "- make_video: khi admin ra lệnh tạo video kiếm tiền/affiliate theo chủ đề nhưng không muốn nhớ nhiều lệnh; có thể tự chọn affiliate phù hợp nếu thiếu aff ID.\n"
        "- operator_auto: khi admin muốn tìm trend/tạo nhiều video theo niche/platform.\n"
        "- autopilot: khi admin muốn tìm trend, tạo job và build luôn creative/manifest/task trong một lệnh.\n"
        "- operator: khi admin nêu một topic cụ thể và có channel để tạo một job.\n"
        "- operator_build: khi admin muốn dựng tiếp một job đã có thành creative/manifest/task.\n"
        "- job_ready: khi admin muốn kiểm tra đủ điều kiện đăng.\n"
        "- operator_daily: khi admin muốn báo cáo/tổng quan.\n"
        "- Không tự động chọn nội dung vi phạm, mạo danh người thật, deepfake không consent, claim affiliate quá mức.\n\n"
        "Schema:\n"
        '{"intent":"affiliate_scale","niche":"công nghệ AI","platform":"tiktok","channel":"all","affiliate":0,"campaign":0,"job":0,"limit":3,"duration":45,"build":1,"days":30,"topic":"","confidence":0,"safety_note":""}'
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
    if intent == "operator_director":
        return (
            f"/operator_director days={max(1, min(int(plan.get('days') or 30), 180))} "
            f"platform={plan.get('platform') or 'tiktok'} limit={max(3, min(int(plan.get('limit') or 10), 20))}"
        )
    if intent == "operator_execute":
        return (
            f"/operator_execute days={max(1, min(int(plan.get('days') or 30), 180))} "
            f"platform={plan.get('platform') or 'tiktok'} build={int(plan.get('build') or 1)} "
            f"duration={int(plan.get('duration') or 45)}"
        )
    if intent == "affiliate_scale":
        return (
            f"/affiliate_scale aff={int(plan.get('affiliate') or 0)} "
            f"platform={plan.get('platform') or 'tiktok'} channel={plan.get('channel') or 'all'} "
            f"limit={max(1, min(int(plan.get('limit') or 5), 12))} "
            f"campaign={int(plan.get('campaign') or 0)} build={int(plan.get('build') or 0)} "
            f"duration={int(plan.get('duration') or 45)}"
        )
    if intent == "make_video":
        return (
            f"/make_video topic={plan.get('topic') or plan.get('niche') or 'công nghệ AI'} "
            f"platform={plan.get('platform') or 'tiktok'} channel={plan.get('channel') or 'all'} "
            f"aff={int(plan.get('affiliate') or 0)} campaign={int(plan.get('campaign') or 0)} "
            f"limit={max(1, min(int(plan.get('limit') or 3), 8))} build={int(plan.get('build') or 1)} "
            f"duration={int(plan.get('duration') or 45)}"
        )
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
        if intent == "operator_director":
            context.args = [
                f"days={max(1, min(int(plan.get('days') or 30), 180))}",
                f"platform={plan.get('platform') or 'tiktok'}",
                f"limit={max(3, min(int(plan.get('limit') or 10), 20))}",
            ]
            return await cmd_operator_director(update, context)
        if intent == "operator_execute":
            context.args = [
                f"days={max(1, min(int(plan.get('days') or 30), 180))}",
                f"platform={plan.get('platform') or 'tiktok'}",
                f"build={int(plan.get('build') or 1)}",
                f"duration={int(plan.get('duration') or 45)}",
                f"limit={max(3, min(int(plan.get('limit') or 10), 20))}",
            ]
            return await cmd_operator_execute(update, context)
        if intent == "affiliate_scale":
            if not int(plan.get("affiliate") or 0):
                return await update.message.reply_text(
                    "⚠️ Lệnh scale affiliate cần <code>aff=&lt;ID&gt;</code>. Xem ID bằng /affiliates.",
                    parse_mode="HTML"
                )
            context.args = [
                f"aff={int(plan.get('affiliate') or 0)}",
                f"platform={plan.get('platform') or 'tiktok'}",
                f"channel={plan.get('channel') or 'all'}",
                f"limit={max(1, min(int(plan.get('limit') or 5), 12))}",
                f"campaign={int(plan.get('campaign') or 0)}",
                f"build={int(plan.get('build') or 0)}",
                f"duration={int(plan.get('duration') or 45)}",
            ]
            if plan.get("niche"):
                context.args.append(f"niche={plan.get('niche')}")
            return await cmd_affiliate_scale(update, context)
        if intent == "make_video":
            context.args = [
                f"topic={plan.get('topic') or plan.get('niche') or 'công nghệ AI'}",
                f"platform={plan.get('platform') or 'tiktok'}",
                f"channel={plan.get('channel') or 'all'}",
                f"aff={int(plan.get('affiliate') or 0)}",
                f"campaign={int(plan.get('campaign') or 0)}",
                f"limit={max(1, min(int(plan.get('limit') or 3), 8))}",
                f"build={int(plan.get('build') or 1)}",
                f"duration={int(plan.get('duration') or 45)}",
            ]
            return await cmd_make_video(update, context)
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

async def cmd_publisher_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = publisher_status_data(update.effective_user.id)
    lines = [
        "📡 <b>PUBLISHER STATUS</b>",
        f"• Ready manual/API: <b>{'có' if data['ready'] else 'chưa'}</b>",
        f"• API-ready: <b>{'có' if data['api_ready'] else 'chưa'}</b>",
        f"• Queue chờ đăng: <b>{data['queued_count']}</b>",
        "",
        "<b>Kênh đăng:</b>",
    ]
    if data["channels"]:
        for ch in data["channels"][:12]:
            lines.append(
                f"• #{ch['id']} | <code>{html.escape(ch['platform'] or '-')}</code> | "
                f"{html.escape(ch['channel_name'] or '-')} / {html.escape(ch['account_label'] or 'main')}\n"
                f"  mode=<code>{html.escape(ch['publish_mode'] or '-')}</code> "
                f"readiness=<b>{html.escape(ch['readiness'])}</b> | {html.escape(ch['reason'])}"
            )
    else:
        lines.append("• Chưa có kênh. Tạo bằng /channel_add.")
    if data["open_queue"]:
        lines.append("\n<b>Queue đang mở:</b>")
        for item in data["open_queue"][:8]:
            lines.append(
                f"• queue #{item['queue_id']} | job #{item['job_id']} | "
                f"<code>{html.escape(item['platform'] or '-')}</code>/{html.escape(item['mode'] or '-')}"
                f" | {html.escape(item['status'] or '-')}\n"
                f"  {html.escape(item['topic'] or '-')}\n"
                f"  next: <code>/publisher_handoff queue={item['queue_id']}</code>"
            )
    if data["blockers"]:
        lines.append("\n<b>Blocker cần xử lý:</b>")
        for blocker in data["blockers"][:8]:
            lines.append(f"• {html.escape(blocker['detail'])}\n  <code>{html.escape(blocker['next'])}</code>")
    lines.append("\nAPI: <code>GET /api/operator/publisher/status</code>")
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

async def cmd_affiliate_seed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    created, skipped = seed_default_affiliate_links(update.effective_user.id)
    lines = [
        "🔗 <b>IMPORT AFFILIATE CATALOG</b>",
        f"• Tạo mới: <b>{len(created)}</b>",
        f"• Bỏ qua do trùng URL: <b>{len(skipped)}</b>",
        f"• Tổng catalog chuẩn: <b>{len(DEFAULT_AFFILIATE_LINKS)}</b>\n",
    ]
    if created:
        lines.append("<b>Link vừa tạo:</b>")
        for affiliate_id, network, product, url in created[:20]:
            lines.append(f"• #{affiliate_id} | <code>{html.escape(network)}</code> | {html.escape(product)}")
        if len(created) > 20:
            lines.append(f"• ... và {len(created) - 20} link khác.")
    if skipped:
        lines.append("\n<b>Đã có sẵn, không tạo trùng:</b>")
        for affiliate_id, network, product, url in skipped[:10]:
            lines.append(f"• #{affiliate_id} | <code>{html.escape(network or '-')}</code> | {html.escape(product or '-')}")
        if len(skipped) > 10:
            lines.append(f"• ... và {len(skipped) - 10} link khác.")
    lines.append("\nDùng <code>/affiliates</code> để xem ID, hoặc <code>/affiliate_match niche=...</code> để chọn link theo trend.")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

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

async def cmd_affiliate_ideas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        affiliate_id = int(data.get("id") or data.get("aff") or context.args[0])
    except (IndexError, TypeError, ValueError):
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/affiliate_ideas aff=&lt;AFF_ID&gt; platform=tiktok n=5 topic=...</code>",
            parse_mode="HTML"
        )
    affiliate = get_affiliate_link(affiliate_id, update.effective_user.id)
    if not affiliate:
        return await update.message.reply_text("❌ Không tìm thấy affiliate hoặc không có quyền.")
    platform = data.get("platform") or data.get("nen") or "tiktok"
    topic = data.get("topic") or data.get("trend") or data.get("chude") or ""
    try:
        limit = max(1, min(int(data.get("n") or data.get("limit") or 5), 8))
    except ValueError:
        limit = 5
    (
        aid, network, product, niche, url, note, status,
        price_vnd, commission_rate, audience, allowed_claims, blocked_claims, product_score
    ) = affiliate
    related = list_related_affiliate_links(update.effective_user.id, affiliate_id=aid, niche=niche or topic, limit=8)
    related_text = format_related_affiliate_links(related, max_items=6)
    prompt = (
        "Tạo danh sách ý tưởng video ngắn affiliate hợp pháp, có thể đưa vào pipeline sản xuất.\n"
        f"Nền tảng: {platform}\n"
        f"Sản phẩm: {product}\n"
        f"Network: {network}\n"
        f"Niche: {niche}\n"
        f"Khách mục tiêu: {audience or '-'}\n"
        f"Claim được phép: {allowed_claims or DEFAULT_AFFILIATE_ALLOWED_CLAIMS}\n"
        f"Claim cấm: {blocked_claims or DEFAULT_AFFILIATE_BLOCKED_CLAIMS}\n"
        f"Topic/trend gợi ý: {topic or '-'}\n\n"
        f"Link affiliate liên quan có thể chèn caption/comment/status:\n{related_text or '-'}\n\n"
        f"Hãy trả về {limit} ý tưởng. Mỗi ý tưởng gồm: hook 3 giây đầu, angle, script outline 30-45s, "
        "visual direction, CTA minh bạch affiliate, rủi ro cần kiểm duyệt. Không cam kết kết quả tài chính, "
        "không mạo danh thương hiệu/người thật, không spam."
    )
    next_command = (
        f"/operator_auto niche={html.escape(niche or product or 'affiliate')} "
        f"platform={html.escape(platform)} channel=all aff={aid} campaign=&lt;ID&gt; limit=5"
    )
    if gemini_client or openai_client:
        msg = await update.message.reply_text("⏳ Đang tạo ý tưởng video từ affiliate catalog...")
        ideas = AgentGemini.chat(
            "Bạn là creative strategist cho video short affiliate hợp pháp.",
            prompt,
            update.effective_user.id,
            is_json=False
        )
        await msg.edit_text(
            f"💡 <b>AFFILIATE VIDEO IDEAS #{aid}</b>\n"
            f"• <code>{html.escape(network or '-')}</code> / <b>{html.escape(product or '-')}</b>\n"
            f"• Platform: <code>{html.escape(platform)}</code>\n"
            f"• Link: <code>{html.escape(url or '-')}</code>\n\n"
            + (f"<b>Link liên quan nên chèn kèm:</b>\n<pre>{html_pre(related_text)}</pre>\n\n" if related_text else "")
            + f"<pre>{html_pre(ideas)}</pre>\n\n"
            + f"Tạo batch từ trend: <code>{next_command}</code>",
            parse_mode="HTML"
        )
        return
    ideas = fallback_affiliate_video_ideas(affiliate, platform, limit)
    await update.message.reply_text(
        f"💡 <b>AFFILIATE VIDEO IDEAS #{aid}</b>\n"
        f"• <code>{html.escape(network or '-')}</code> / <b>{html.escape(product or '-')}</b>\n"
        f"• Platform: <code>{html.escape(platform)}</code>\n"
        f"• Link: <code>{html.escape(url or '-')}</code>\n\n"
        + (f"<b>Link liên quan nên chèn kèm:</b>\n<pre>{html_pre(related_text)}</pre>\n\n" if related_text else "")
        + f"<pre>{html.escape(ideas)}</pre>\n\n"
        + f"⚠️ Chưa cấu hình AI provider nên bot dùng template fallback.\n"
        + f"Tạo batch từ trend: <code>{next_command}</code>",
        parse_mode="HTML"
    )

async def cmd_affiliate_related(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        affiliate_id = int(data.get("id") or data.get("aff") or (context.args[0] if context.args and context.args[0].isdigit() else 0))
    except (TypeError, ValueError):
        affiliate_id = 0
    brand = data.get("brand") or data.get("thuonghieu") or data.get("product") or data.get("sanpham") or ""
    niche = data.get("niche") or data.get("ngach") or data.get("topic") or data.get("chude") or ""
    try:
        limit = max(3, min(int(data.get("limit") or 12), 30))
    except ValueError:
        limit = 12
    if not affiliate_id and not brand and not niche:
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/affiliate_related aff=&lt;AFF_ID&gt;</code> hoặc "
            "<code>/affiliate_related brand=Samsung niche=điện thoại limit=12</code>",
            parse_mode="HTML"
        )
    base = get_affiliate_link(affiliate_id, update.effective_user.id) if affiliate_id else None
    if affiliate_id and not base:
        return await update.message.reply_text("❌ Không tìm thấy affiliate hoặc không có quyền.")
    related = list_related_affiliate_links(
        update.effective_user.id,
        affiliate_id=affiliate_id,
        brand=brand,
        niche=niche or (base[3] if base else ""),
        limit=limit,
    )
    title = f"🔎 <b>LINK AFFILIATE LIÊN QUAN</b>"
    if base:
        title += f"\n• Gốc: #{base[0]} | <b>{html.escape(base[2] or '-')}</b> | {html.escape(base[3] or '-')}"
    if brand or niche:
        title += f"\n• Query: brand=<code>{html.escape(brand or '-')}</code> | niche=<code>{html.escape(niche or '-')}</code>"
    lines = [
        title,
        "",
        "Dùng danh sách này để chèn link chính + link liên quan vào caption, comment ghim, status hoặc mô tả video.",
    ]
    if not related:
        lines.append("\n📭 Chưa tìm thấy link liên quan. Thêm link bằng /affiliate_add hoặc chạy /affiliate_seed.")
    else:
        lines.append("\n<b>Gợi ý chèn kèm:</b>")
        for score, reasons, row in related:
            aid, network, product, aff_niche, url, note, status, price_vnd, commission_rate, audience, *_ = row
            lines.append(
                f"• #{aid} | match=<b>{score}</b> | <code>{html.escape(network or '-')}</code> / "
                f"<b>{html.escape(product or '-')}</b>\n"
                f"  {html.escape(aff_niche or '-')}\n"
                f"  <code>{html.escape(url or '-')}</code>\n"
                f"  lý do: {html.escape('; '.join(reasons[:3]) if reasons else '-')}"
            )
    lines.append(
        "\nLệnh tiếp:\n"
        "<code>/affiliate_ideas aff=&lt;AFF_ID&gt; platform=tiktok n=5 topic=...</code>\n"
        "<code>/affiliate_scale aff=&lt;AFF_ID&gt; platform=tiktok channel=all limit=3 build=1</code>"
    )
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
    related_affiliates = list_related_affiliate_links(update.effective_user.id, affiliate_id=affiliate_id, niche=niche, limit=8) if affiliate_id else []
    related_note = format_related_affiliate_links(related_affiliates, max_items=6)
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
                + (f" | related_affiliates={related_note}" if related_note else "")
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
                    build_production_prompt(slot)
                    + f"\n\nNguồn trend: {item['url']}\nTóm tắt trend: {item.get('summary','')}"
                    + (f"\n\nLink affiliate liên quan để chèn caption/comment/status:\n{related_note}" if related_note else ""),
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
    ]
    if related_note:
        lines.extend([
            "<b>Link liên quan nên chèn kèm caption/comment/status:</b>",
            f"<pre>{html_pre(related_note)}</pre>",
            "",
        ])
    lines.append("<b>Job mới:</b>")
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

async def cmd_make_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    raw = " ".join(context.args).strip()
    data = parse_key_value_args(raw)
    topic = data.get("topic") or data.get("chude") or data.get("niche") or data.get("ngach") or (raw if "=" not in raw else "")
    if not topic:
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/make_video topic=đồ công nghệ văn phòng platform=tiktok channel=all limit=3 build=1</code>\n"
            "Có thể thêm <code>aff=&lt;ID&gt;</code> hoặc để bot tự chọn affiliate phù hợp.",
            parse_mode="HTML"
        )
    platform = (data.get("platform") or data.get("nen") or "tiktok").lower()
    channel = (data.get("channel") or data.get("kenh") or "all").lower()
    try:
        affiliate_id = int(data.get("affiliate_id") or data.get("aff") or 0)
    except ValueError:
        affiliate_id = 0
    try:
        campaign_id = int(data.get("campaign") or data.get("camp") or 0)
    except ValueError:
        campaign_id = 0
    try:
        limit = max(1, min(int(data.get("limit") or data.get("max") or 3), 8))
    except ValueError:
        limit = 3
    build = (data.get("build") or data.get("autobuild") or "1").lower() not in {"0", "false", "no", "off", "khong"}
    try:
        duration = max(15, min(int(data.get("duration") or data.get("sec") or 45), 120))
    except ValueError:
        duration = 45
    try:
        variants = max(3, min(int(data.get("variants") or data.get("n") or 5), 8))
    except ValueError:
        variants = 5

    msg = await update.message.reply_text("🎬 Đang tạo pipeline video kiếm tiền: chọn affiliate, tìm trend, tạo job và build task...")
    try:
        ok, reason, result = await make_video_pipeline(
            update.effective_user.id,
            topic,
            platform=platform,
            channel=channel,
            affiliate_id=affiliate_id,
            campaign_id=campaign_id,
            limit=limit,
            build=build,
            duration=duration,
            variants=variants,
        )
    except Exception as e:
        await alert_admin(context, "Make Video", f"{str(e)} | topic={topic} platform={platform}")
        return await msg.edit_text("❌ Make Video lỗi khi tìm trend/tạo job. Đã báo admin.")
    if not ok:
        return await msg.edit_text(f"❌ {html.escape(str(reason))}", parse_mode="HTML")

    affiliate = result.get("affiliate") or {}
    campaign = result.get("campaign") or {}
    created_jobs = result.get("created_jobs") or []
    built_jobs = result.get("built_jobs") or []
    packs = result.get("publish_packs") or []
    lines = [
        "🎬 <b>MAKE VIDEO PIPELINE</b>",
        f"• Chủ đề: <b>{html.escape(topic)}</b>",
        f"• Platform/channel: <code>{html.escape(platform)}</code> / <code>{html.escape(channel)}</code>",
        f"• Affiliate chọn: <code>#{affiliate.get('id') or '-'}</code> {html.escape(affiliate.get('product') or 'chưa có')}"
        + (f" | score={affiliate.get('match_score')}" if affiliate.get("id") else ""),
        f"• Campaign: <code>#{campaign.get('id') or '-'}</code> {html.escape(campaign.get('name') or '')}",
        f"• Job tạo: <b>{len(created_jobs)}</b> | Built: <b>{len(built_jobs)}</b>",
        "",
        "<b>Job sản xuất:</b>",
    ]
    for item in created_jobs[:8]:
        built_item = next((row for row in built_jobs if row["job_id"] == item["job_id"]), None)
        build_note = ""
        if built_item:
            build_note = f" | manifest #{built_item['manifest_id']} | tasks={built_item['task_count']} | {built_item['readiness']}"
        lines.append(
            f"• job #{item['job_id']} | trend #{item['trend_id']} | score=<b>{item['score']}</b>{html.escape(build_note)}\n"
            f"  {html.escape(item['title'])}\n"
            f"  next: <code>/tasks job={item['job_id']}</code> | <code>/job_ready job={item['job_id']}</code>"
        )
    if packs:
        first_pack = packs[0]
        lines.extend([
            "",
            "<b>Publish pack đầu tiên:</b>",
            f"• Tracking URL: <code>{html.escape(first_pack.get('tracking_url') or 'cần PUBLIC_BASE_URL')}</code>",
            f"• Disclosure: {html.escape(first_pack.get('disclosure') or '-')}",
        ])
    if result.get("failed_builds"):
        lines.append("\n<b>Build lỗi:</b>")
        for item in result["failed_builds"][:5]:
            lines.append(f"• job #{item.get('job_id')}: {html.escape(item.get('error') or '-')}")
    lines.append("\nChốt đăng: <code>/review_gate job=&lt;JOB_ID&gt;</code> → <code>/approve_publish job=&lt;JOB_ID&gt; queue=1</code>")
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

async def cmd_operator_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = operator_status_data(update.effective_user.id)
    counts = data["counts"]
    lines = [
        "🧭 <b>OPERATOR SYSTEM STATUS</b>",
        f"• Ready to scale: <b>{'YES' if data['ready_to_scale'] else 'NO'}</b>",
        f"• Channels: <b>{counts['active_channels']}</b> | Affiliates: <b>{counts['active_affiliates']}</b> | Campaigns: <b>{counts['active_campaigns']}</b>",
        f"• Open jobs: <b>{counts['open_jobs']}</b> | Tasks: <b>{counts['open_tasks']}</b> | Publish queue: <b>{counts['open_publish']}</b>",
        "",
        "<b>Checklist:</b>",
    ]
    for key, ok, detail, next_cmd in data["checks"]:
        lines.append(f"• {'✅' if ok else '⚠️'} <code>{html.escape(key)}</code> — {html.escape(detail)} | next: <code>{html.escape(next_cmd)}</code>")
    lines.append("\n<b>Channel readiness:</b>")
    if data["channel_readiness"]:
        for row, readiness, reason in data["channel_readiness"][:10]:
            cid, platform, channel_name, account_label, status, publish_mode, token_env, page_id = row
            lines.append(
                f"• #{cid} | <code>{html.escape(platform or '-')}</code> | {html.escape(channel_name or '-')} / {html.escape(account_label or 'main')}\n"
                f"  mode={html.escape(publish_mode or 'manual')} | <b>{html.escape(readiness)}</b> — {html.escape(reason)}"
            )
    else:
        lines.append("• Chưa có channel active.")
    lines.append("\n<b>Blocked jobs:</b>")
    if data["blocked_jobs"]:
        for jid, stage, status, platform, topic, channel_name, product_name, updated_at in data["blocked_jobs"]:
            lines.append(
                f"• job #{jid} | <code>{html.escape(platform or '-')}</code> | {html.escape(stage or '-')}/{html.escape(status or '-')}\n"
                f"  {html.escape(topic or '-')}\n"
                f"  next: <code>/job_ready job={jid}</code>"
            )
    else:
        lines.append("• Không có job blocked.")
    lines.append("\nLệnh nhanh: <code>/operator_menu</code> | <code>/affiliate_scale aff=&lt;ID&gt; build=1</code> | <code>/operator_loop</code>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_operator_audit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = operator_audit_data(update.effective_user.id)
    lines = [
        "🧪 <b>OPERATOR AUDIT — END TO END</b>",
        f"• Level: <b>{html.escape(data['level'])}</b>",
        f"• Score: <b>{data['score']}/100</b>",
        "",
        "<b>Checklist:</b>",
    ]
    for key, ok, detail, next_cmd in data["checks"]:
        icon = "✅" if ok else "⚠️"
        lines.append(f"{icon} <code>{html.escape(key)}</code> — {html.escape(detail)}")
        if not ok:
            lines.append(f"  next: <code>{html.escape(next_cmd)}</code>")
    if data["channel_issues"]:
        lines.append("\n<b>Channel cần kiểm tra:</b>")
        for item in data["channel_issues"][:8]:
            lines.append(
                f"• #{item['channel_id']} | <code>{html.escape(item['platform'] or '-')}</code> | "
                f"{html.escape(item['readiness'])}: {html.escape(item['reason'])}"
            )
    counts = data["counts"]
    lines.extend([
        "",
        "<b>Số liệu:</b>",
        f"• Affiliates={counts['active_affiliates']} | Channels={counts['active_channels']} | Campaigns={counts['active_campaigns']}",
        f"• Jobs={counts['total_jobs']} | Tasks={counts['total_tasks']} | Queue={counts['total_publish_queue']} | Trends={counts['total_trends']}",
        f"• Performance events={counts['total_performance']} | manual_ready={counts['manual_ready_channels']} | api_ready={counts['api_ready_channels']}",
        "",
        f"Next: <code>{html.escape(data['next_command'])}</code>",
    ])
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_operator_playbook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    text = (
        "📘 <b>OPERATOR PLAYBOOK — KIẾM TIỀN BẰNG VIDEO + AFFILIATE</b>\n\n"
        "<b>0. Kiểm tra hệ thống</b>\n"
        "• <code>/operator_status</code>\n"
        "• <code>/operator_director</code> để lấy đúng một next action cho admin/Claude/n8n.\n"
        "• Nếu thiếu kênh: <code>/channel_add platform=tiktok name=... slots=2/day mode=manual</code>\n"
        "• Nếu thiếu link: <code>/affiliate_seed</code> hoặc <code>/affiliate_add ...</code>\n\n"
        "<b>1. Chọn link cần scale</b>\n"
        "• <code>/affiliate_report days=30</code> để xem link nào có view/click/doanh thu.\n"
        "• <code>/affiliates</code> để lấy ID link.\n\n"
        "<b>2. Tạo video theo trend từ affiliate</b>\n"
        "• Cách nhanh: <code>/brain scale affiliate &lt;ID&gt; lên TikTok build luôn 3 video</code>\n"
        "• Cách rõ tham số: <code>/affiliate_scale aff=&lt;ID&gt; platform=tiktok channel=all limit=3 build=1 duration=45</code>\n\n"
        "<b>3. Giao việc cho AI/tool ngoài</b>\n"
        "• Lấy task: <code>/next_task</code>\n"
        "• Xuất prompt: <code>/task_handoff id=&lt;TASK_ID&gt;</code> hoặc <code>/manifest_handoff job=&lt;JOB_ID&gt; tool=kling</code>\n"
        "• Worker API: <code>GET /api/operator/tasks/next</code> rồi trả output qua <code>POST /api/operator/tasks/&lt;ID&gt;/complete</code>\n\n"
        "<b>4. Kiểm duyệt trước đăng</b>\n"
        "• <code>/job_ready job=&lt;JOB_ID&gt;</code>\n"
        "• <code>/review_gate job=&lt;JOB_ID&gt;</code>\n"
        "• Không đăng nếu thiếu quyền hình ảnh/voice/nhạc, claim affiliate quá mức, mạo danh hoặc nội dung nhạy cảm sai chính sách.\n\n"
        "<b>5. Đăng bài và gắn link</b>\n"
        "• <code>/publish_pack job=&lt;JOB_ID&gt;</code>\n"
        "• <code>/queue_publish job=&lt;JOB_ID&gt; mode=manual</code>\n"
        "• Sau khi đăng: <code>/mark_published job=&lt;JOB_ID&gt; url=https://...</code>\n\n"
        "<b>6. Đo tiền và tối ưu</b>\n"
        "• <code>/performance_add job=&lt;JOB_ID&gt; type=click value=1</code>\n"
        "• <code>/performance_add job=&lt;JOB_ID&gt; type=revenue value=1 amount=150000</code>\n"
        "• <code>/affiliate_report days=30</code> và <code>/growth days=30</code> để quyết định scale tiếp.\n\n"
        "<b>7. Tự động hóa bằng API</b>\n"
        "• <code>/operator_api</code> để lấy endpoint/payload.\n"
        "• Luồng API chuẩn: director → affiliate-scale → tasks/next → publish/next → performance.\n"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def cmd_operator_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = operator_today_data(update.effective_user.id)
    counts = data["status"]["counts"]
    lines = [
        "📌 <b>OPERATOR TODAY</b>",
        f"• Ready to scale: <b>{'YES' if data['status']['ready_to_scale'] else 'NO'}</b>",
        f"• Channels/Affiliates/Campaigns: <b>{counts['active_channels']}</b>/<b>{counts['active_affiliates']}</b>/<b>{counts['active_campaigns']}</b>",
        f"• Open jobs/tasks/publish: <b>{counts['open_jobs']}</b>/<b>{counts['open_tasks']}</b>/<b>{counts['open_publish']}</b>",
        "",
        "<b>Việc ưu tiên hôm nay:</b>",
    ]
    for idx, action in enumerate(data["actions"], 1):
        lines.append(
            f"{idx}. <b>{html.escape(action['title'])}</b> "
            f"(<code>{html.escape(action['priority'])}</code>)\n"
            f"   {html.escape(action['detail'])}\n"
            f"   <code>{html.escape(action['command'])}</code>"
        )
    if data["best_affiliate"]:
        score, row, ctr, cvr, roi = data["best_affiliate"]
        aid, network, product, niche, url, product_score, jobs, publishes, views, clicks, conversions, revenue, cost, events = row
        lines.append(
            "\n<b>Affiliate nổi bật:</b>\n"
            f"• #{aid} | <code>{html.escape(network or '-')}</code> | {html.escape(product or '-')}\n"
            f"• score={score} | CTR={ctr:.2f}% | CVR={cvr:.2f}% | ROI={roi:.1f}% | revenue={int(revenue or 0):,}đ"
        )
    lines.append("\nMở checklist đầy đủ: <code>/operator_playbook</code>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

def operator_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🧠 Điều hành", callback_data="opmenu|cat_control"),
            InlineKeyboardButton("🔥 Trend", callback_data="opmenu|cat_trend")
        ],
        [
            InlineKeyboardButton("🔗 Affiliate", callback_data="opmenu|cat_affiliate"),
            InlineKeyboardButton("📅 Kênh & lịch", callback_data="opmenu|cat_schedule")
        ],
        [
            InlineKeyboardButton("🎬 Sản xuất", callback_data="opmenu|cat_production"),
            InlineKeyboardButton("📮 Đăng bài", callback_data="opmenu|cat_publish")
        ],
        [
            InlineKeyboardButton("💰 Doanh thu", callback_data="opmenu|cat_money"),
            InlineKeyboardButton("🔌 API/Auto", callback_data="opmenu|cat_api")
        ],
        [
            InlineKeyboardButton("🛠 Nội bộ", callback_data="opmenu|cat_internal"),
            InlineKeyboardButton("📊 Dashboard", callback_data="opmenu|dashboard")
        ],
    ])

def operator_category_keyboard(category):
    categories = {
        "cat_control": [
            ("🧠 Brain command", "brain"), ("🎬 Make video", "makevideo"),
            ("🚀 Autopilot batch", "autopilot"),
            ("🤖 Auto batch", "auto"), ("🔁 Operator loop", "loop"),
            ("🎛 Director", "director"), ("▶️ Execute", "execute"),
            ("🧪 Audit", "audit"), ("📌 Today plan", "today"),
            ("📘 Playbook", "playbook"),
            ("🧭 System status", "status"), ("📊 Daily digest", "daily"),
            ("🧭 Dashboard", "dashboard"),
        ],
        "cat_trend": [
            ("🔥 Tìm trend", "trend"), ("🏆 Trend ranking", "rank"),
            ("🤖 Auto từ trend", "auto"), ("📈 Growth optimizer", "growth"),
        ],
        "cat_affiliate": [
            ("🔗 Import catalog", "affseed"), ("🛒 Danh sách link", "affiliates"),
            ("💡 Ý tưởng video", "affideas"), ("🎯 Match trend", "affmatch"),
            ("🚀 Scale thành video", "affscale"), ("💰 Báo cáo affiliate", "affreport"),
            ("🧠 Quyết định scale", "affdecisions"), ("🔎 Link liên quan", "affrelated"),
            ("✏️ Cập nhật hồ sơ", "affprofile"),
        ],
        "cat_schedule": [
            ("📡 Kênh", "channels"), ("➕ Thêm kênh", "channeladd"),
            ("📅 Calendar", "calendar"), ("🗓 Lên lịch", "calendarplan"),
            ("🧪 Auto-post ready", "readiness"),
        ],
        "cat_production": [
            ("🎬 Make video", "makevideo"), ("⚡ Build bundle", "build"),
            ("🎛 Pipeline", "pipeline"),
            ("🎬 Manifest", "manifest"), ("🤝 Manifest handoff", "manifesthandoff"),
            ("✅ Tasks", "tasks"), ("➡️ Next task", "nexttask"),
            ("🗂 Assets", "assets"), ("📋 Job report", "report"),
            ("🚦 Job ready", "jobready"), ("🛡 Review gate", "review"),
            ("🧪 Creative test", "creative"), ("🏁 Creative report", "creativereport"),
        ],
        "cat_publish": [
            ("📦 Publish pack", "publish"), ("📮 Publish queue", "publishqueue"),
            ("🤖 Publisher handoff", "publisherhandoff"), ("✅ Approve publish", "approvepublish"),
            ("📡 Publisher status", "publisherstatus"), ("🧪 Publish readiness", "readiness"),
            ("✅ Mark published", "markpublished"),
        ],
        "cat_money": [
            ("💰 Performance", "performance"), ("📈 Growth optimizer", "growth"),
            ("🔗 Báo cáo affiliate", "affreport"), ("📊 Tracking funnel", "trackingreport"),
            ("🎯 Scale plan", "scaleplan"), ("🚀 Execute scale", "scaleexecute"),
            ("📊 Daily digest", "daily"),
            ("🏦 Dashboard quản trị", "admin_dashboard"),
            ("💳 Check PayOS", "checkpayos"),
        ],
        "cat_api": [
            ("🔌 Operator API", "api"), ("🔁 Operator loop", "loop"),
            ("📜 Worker spec", "workerspec"), ("🧰 Toolchain", "toolchain"),
            ("🧯 Tool events", "toolevents"), ("🧪 Auto-post ready", "readiness"),
            ("🧩 n8n template", "n8ntemplate"), ("📥 n8n import", "n8nworkflow"),
            ("📮 Publish API queue", "publishqueue"),
        ],
        "cat_internal": [
            ("🛠 Tools", "tools"), ("💼 MMO workflow", "mmo"),
            ("📘 Playbook", "playbook"), ("🤝 Handoff AI", "handoff"),
            ("📊 Campaign stats", "campaignstats"),
        ],
    }
    rows = []
    items = categories.get(category, [])
    for i in range(0, len(items), 2):
        rows.append([InlineKeyboardButton(text, callback_data=f"opmenu|{action}") for text, action in items[i:i + 2]])
    rows.append([InlineKeyboardButton("⬅️ Quay lại thư mục", callback_data="opmenu|root")])
    return InlineKeyboardMarkup(rows)

def operator_category_title(category):
    titles = {
        "cat_control": "🧠 ĐIỀU HÀNH",
        "cat_trend": "🔥 TREND",
        "cat_affiliate": "🔗 AFFILIATE",
        "cat_schedule": "📅 KÊNH & LỊCH",
        "cat_production": "🎬 SẢN XUẤT",
        "cat_publish": "📮 ĐĂNG BÀI",
        "cat_money": "💰 DOANH THU",
        "cat_api": "🔌 API/AUTO",
        "cat_internal": "🛠 NỘI BỘ",
    }
    return titles.get(category, "AI OPERATOR")

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
        "Chọn một thư mục bên dưới để mở các lệnh liên quan."
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=operator_menu_keyboard())

async def cmd_operator_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    base_url = (PUBLIC_BASE_URL or "").rstrip("/") or "https://<RAILWAY_DOMAIN>"
    token_status = "đã bật" if OPERATOR_API_TOKEN else "chưa bật"
    lines = [
        "🔌 <b>OPERATOR API BRIDGE</b>",
        "",
        f"• Base URL: <code>{html.escape(base_url)}</code>",
        f"• OPERATOR_API_TOKEN: <b>{token_status}</b>",
        "• Header bắt buộc: <code>Authorization: Bearer &lt;OPERATOR_API_TOKEN&gt;</code>",
        "",
        "<b>Endpoint cho n8n/worker:</b>",
        f"• Director next action: <code>GET {html.escape(base_url)}/api/operator/director</code>",
        f"• Director execute an toàn: <code>POST {html.escape(base_url)}/api/operator/director/run</code>",
        f"• Audit end-to-end: <code>GET {html.escape(base_url)}/api/operator/audit</code>",
        f"• Worker spec: <code>GET {html.escape(base_url)}/api/operator/worker-spec</code>",
        f"• Toolchain paid/fallback: <code>GET {html.escape(base_url)}/api/operator/toolchain</code>",
        f"• Báo lỗi/quota tool: <code>POST {html.escape(base_url)}/api/operator/tool-events</code>",
        f"• n8n template: <code>GET {html.escape(base_url)}/api/operator/n8n-template</code>",
        f"• n8n import JSON: <code>GET {html.escape(base_url)}/api/operator/n8n-workflow.json</code>",
        f"• Trạng thái hệ thống: <code>GET {html.escape(base_url)}/api/operator/status</code>",
        f"• Trạng thái publisher: <code>GET {html.escape(base_url)}/api/operator/publisher/status</code>",
        f"• Việc ưu tiên hôm nay: <code>GET {html.escape(base_url)}/api/operator/today</code>",
        f"• Loop cron: <code>POST {html.escape(base_url)}/api/operator/loop</code>",
        f"• Make video pipeline: <code>POST {html.escape(base_url)}/api/operator/make-video</code>",
        f"• Danh sách kênh: <code>GET {html.escape(base_url)}/api/operator/channels</code>",
        f"• Danh sách campaign: <code>GET {html.escape(base_url)}/api/operator/campaigns</code>",
        f"• Danh sách affiliate: <code>GET {html.escape(base_url)}/api/operator/affiliates</code>",
        f"• Báo cáo affiliate: <code>GET {html.escape(base_url)}/api/operator/affiliate-report</code>",
        f"• Tracking funnel: <code>GET {html.escape(base_url)}/api/operator/tracking-report</code>",
        f"• Scale plan: <code>GET {html.escape(base_url)}/api/operator/scale-plan</code>",
        f"• Execute scale plan: <code>POST {html.escape(base_url)}/api/operator/scale-plan/run</code>",
        f"• Quyết định scale affiliate: <code>GET {html.escape(base_url)}/api/operator/affiliate-decisions</code>",
        f"• Scale affiliate: <code>POST {html.escape(base_url)}/api/operator/affiliate-scale</code>",
        f"• Lấy task: <code>GET {html.escape(base_url)}/api/operator/tasks/next</code>",
        f"• Trả task: <code>POST {html.escape(base_url)}/api/operator/tasks/&lt;TASK_ID&gt;/complete</code>",
        f"• Lấy publish pack: <code>GET {html.escape(base_url)}/api/operator/jobs/&lt;JOB_ID&gt;/publish-pack</code>",
        f"• Duyệt publish: <code>POST {html.escape(base_url)}/api/operator/jobs/&lt;JOB_ID&gt;/approve</code>",
        f"• Lấy hàng đợi đăng: <code>GET {html.escape(base_url)}/api/operator/publish/next</code>",
        f"• Publisher handoff: <code>GET {html.escape(base_url)}/api/operator/publish/&lt;QUEUE_ID&gt;/handoff</code>",
        f"• Trả URL đã đăng: <code>POST {html.escape(base_url)}/api/operator/publish/&lt;QUEUE_ID&gt;/complete</code>",
        f"• Ghi view/click/doanh thu: <code>POST {html.escape(base_url)}/api/operator/performance</code>",
        "",
        "<b>Payload loop mẫu:</b>",
        '<pre>{"limit":10,"auto_queue":true,"notify_admin":true}</pre>',
        "<b>Payload director-run mẫu:</b>",
        '<pre>{"days":30,"platform":"tiktok","limit":10,"execute":true,"build":true,"duration":45,"notify_admin":true}</pre>',
        "<b>Payload make-video mẫu:</b>",
        '<pre>{"topic":"đồ công nghệ văn phòng","platform":"tiktok","channel":"all","limit":3,"build":true,"duration":45,"notify_admin":true}</pre>',
        "<b>Payload affiliate-scale mẫu:</b>",
        '<pre>{"affiliate_id":3,"platform":"tiktok","channel":"all","limit":3,"build":true,"duration":45,"notify_admin":true}</pre>',
        "<b>Payload task complete mẫu:</b>",
        '<pre>{"status":"ready","output_url":"https://.../final.mp4","note":"kling/capcut output"}</pre>',
        "<b>Payload performance mẫu:</b>",
        '<pre>{"job_id":12,"event_type":"revenue","value":1,"amount":150000,"source":"tiktok_affiliate","note":"order"}</pre>',
    ]
    if not OPERATOR_API_TOKEN:
        lines.append("\n⚠️ Chưa set <code>OPERATOR_API_TOKEN</code> trên server nên API bridge đang đóng.")
    if not PUBLIC_BASE_URL:
        lines.append("⚠️ Chưa set <code>PUBLIC_BASE_URL</code>, hãy dùng domain Railway thật trong n8n.")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_operator_worker_spec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    spec = operator_worker_spec_data()
    compact = {
        "base_url": spec["base_url"],
        "auth": spec["auth"],
        "standard_loop": spec["standard_loop"],
        "payloads": spec["payloads"],
        "safety_rules": spec["safety_rules"],
    }
    text = (
        "📜 <b>OPERATOR WORKER SPEC</b>\n\n"
        "Dùng spec này làm system/runbook cho Claude, n8n hoặc tool worker.\n\n"
        f"• API: <code>{html.escape(spec['base_url'])}/api/operator/worker-spec</code>\n"
        "• Luồng chuẩn: audit → director → director/run → tasks/next → task complete → ready → publish-pack → publish → performance\n\n"
        f"<pre>{html_pre(json.dumps(compact, ensure_ascii=False, indent=2), 3000)}</pre>"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def cmd_operator_toolchain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = operator_toolchain_data()
    lines = [
        "🧰 <b>OPERATOR TOOLCHAIN</b>",
        "",
        f"• Policy: <code>{html.escape(data['policy'])}</code>",
        f"• Ready: <b>{data['counts']['ready']}/{data['counts']['total']}</b> | Blocked: <b>{data['counts']['blocked']}</b>",
        "",
    ]
    for chain in data["chains"]:
        primary = chain["primary"]
        status = "✅" if chain["ready"] else "⚠️"
        p_status = "OK" if primary["configured"] else "thiếu env"
        fallback_names = ", ".join(item["name"] for item in chain["fallbacks"][:3])
        lines.append(
            f"{status} <b>{html.escape(chain['stage'])}</b>\n"
            f"  Primary: <code>{html.escape(primary['name'])}</code> ({html.escape(p_status)})\n"
            f"  Active: <code>{html.escape(chain['active_choice'] or '-')}</code>\n"
            f"  Fallback: {html.escape(fallback_names or '-')}"
        )
    lines.append("\nFailure protocol:")
    for rule in data["failure_protocol"][:4]:
        lines.append(f"• {html.escape(rule)}")
    lines.append("\nAPI: <code>GET /api/operator/toolchain</code>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_operator_tool_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    if data.get("tool") or data.get("stage") or data.get("type") or data.get("message"):
        event_id = record_tool_event(
            update.effective_user.id,
            data.get("stage", ""),
            data.get("tool") or data.get("tool_name", ""),
            data.get("type") or data.get("event") or data.get("event_type") or "error",
            data.get("severity", "warning"),
            safe_int(data.get("job") or data.get("job_id"), 0),
            safe_int(data.get("task") or data.get("task_id"), 0),
            data.get("fallback", "") or data.get("fallback_tool", ""),
            data.get("message", "") or data.get("note", ""),
        )
        return await update.message.reply_text(
            f"✅ Đã ghi tool event <code>#{event_id}</code>.\nXem lại: <code>/operator_tool_events limit=10</code>",
            parse_mode="HTML"
        )
    try:
        limit = int(data.get("limit") or context.args[0])
    except (IndexError, TypeError, ValueError):
        limit = 12
    rows = list_tool_events(
        update.effective_user.id,
        limit=limit,
        stage=(data.get("stage") or "").lower(),
        severity=(data.get("severity") or "").lower(),
    )
    lines = [
        "🧯 <b>TOOL EVENTS / QUOTA LOG</b>",
        "",
        "Ghi mới: <code>/operator_tool_events stage=voice tool=Fish type=quota fallback=Edge message=het_quota</code>",
        "API: <code>POST /api/operator/tool-events</code>",
        "",
    ]
    if not rows:
        lines.append("Chưa có sự cố tool nào.")
    for row in rows:
        event_id, stage, tool_name, event_type, severity, job_id, task_id, fallback_tool, message, created_at = row
        icon = "🚨" if severity == "critical" else ("⚠️" if severity == "warning" else "ℹ️")
        lines.append(
            f"{icon} <code>#{event_id}</code> | {html.escape(created_at or '-')}\n"
            f"• <b>{html.escape(stage or '-')}</b> / <code>{html.escape(tool_name or '-')}</code> | "
            f"type=<code>{html.escape(event_type or '-')}</code> | severity=<code>{html.escape(severity or '-')}</code>\n"
            f"• job=<code>{job_id or '-'}</code> task=<code>{task_id or '-'}</code> fallback=<code>{html.escape(fallback_tool or '-')}</code>\n"
            f"• {html.escape(message or '-')}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_operator_n8n_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = operator_n8n_template_data()
    compact = {
        "base_url": data["base_url"],
        "required_env": data["required_env"],
        "default_schedule": data["default_schedule"],
        "workflow": data["workflow"],
        "branching_rules": data["branching_rules"],
        "tracking_events": data["tracking_events"],
        "guardrails": data["guardrails"],
    }
    text = (
        "🧩 <b>N8N SAFE OPERATOR TEMPLATE</b>\n\n"
        "Dùng template này để dựng workflow n8n: Cron → Audit → Worker Spec → Director Run → Task Worker → Publish Pack → Publish Queue → Performance.\n\n"
        f"• API: <code>{html.escape(data['base_url'])}/api/operator/n8n-template</code>\n"
        "• Lịch mặc định: 30 phút/lần khi mới chạy.\n"
        "• Quy tắc: không tự đăng nếu chưa qua review/readiness; không lộ token; có disclosure affiliate.\n\n"
        f"<pre>{html_pre(json.dumps(compact, ensure_ascii=False, indent=2), 3000)}</pre>"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def cmd_operator_n8n_workflow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = operator_n8n_workflow_json_data()
    base_url = (PUBLIC_BASE_URL or "https://<RAILWAY_DOMAIN>").rstrip("/")
    text = (
        "🧩 <b>N8N IMPORT WORKFLOW JSON</b>\n\n"
        "Dùng endpoint này trong trình duyệt/Postman để lấy JSON rồi import vào n8n.\n\n"
        f"• URL: <code>{html.escape(base_url)}/api/operator/n8n-workflow.json</code>\n"
        "• Trước khi bật workflow, set env trong n8n: <code>OPERATOR_BASE_URL</code> và <code>OPERATOR_API_TOKEN</code>.\n"
        "• Workflow mặc định inactive và có gate thủ công ở bước publish.\n\n"
        f"<pre>{html_pre(json.dumps({'name': data['name'], 'active': data['active'], 'nodes': len(data['nodes']), 'tags': data['tags']}, ensure_ascii=False, indent=2), 1200)}</pre>"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def handle_operator_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if str(query.from_user.id) != ADMIN_ID:
        return await query.answer("Chỉ Admin được dùng.", show_alert=True)
    action = query.data.split("|", 1)[1]
    if action == "root":
        return await query.edit_message_text(
            "🧠 <b>AI OPERATOR MENU</b>\n\nChọn một thư mục để mở các lệnh liên quan.",
            parse_mode="HTML",
            reply_markup=operator_menu_keyboard()
        )
    if action.startswith("cat_"):
        return await query.edit_message_text(
            f"{operator_category_title(action)}\n\nChọn mục cần thao tác:",
            parse_mode="HTML",
            reply_markup=operator_category_keyboard(action)
        )
    snippets = {
        "dashboard": "/operator_dashboard",
        "status": "/operator_status",
        "audit": "/operator_audit",
        "today": "/operator_today",
        "playbook": "/operator_playbook",
        "admin_dashboard": "/dashboard",
        "api": "/operator_api",
        "workerspec": "/operator_worker_spec\nGET /api/operator/worker-spec",
        "toolchain": "/operator_toolchain\nGET /api/operator/toolchain",
        "toolevents": "/operator_tool_events\n/operator_tool_events stage=voice tool=Fish type=quota fallback=Edge message=het_quota\nPOST /api/operator/tool-events",
        "n8ntemplate": "/operator_n8n_template\nGET /api/operator/n8n-template",
        "n8nworkflow": "/operator_n8n_workflow\nGET /api/operator/n8n-workflow.json",
        "director": "/operator_director days=30 platform=tiktok limit=10",
        "execute": "/operator_execute days=30 platform=tiktok build=1 duration=45",
        "brain": "/brain tạo 5 video trend công nghệ AI cho tiktok aff=<AFF_ID> campaign=<ID>",
        "makevideo": "/make_video topic=công nghệ AI platform=tiktok channel=all limit=3 build=1\nPOST /api/operator/make-video",
        "autopilot": "/autopilot niche=công nghệ AI platform=tiktok channel=all aff=<AFF_ID> campaign=<ID> limit=3 duration=45",
        "build": "/operator_build job=<JOB_ID> n=5 duration=45",
        "channels": "/channels",
        "channeladd": "/channel_add platform=tiktok name=TechVN account=tk1 focus=AI tools audience=creator slots=2/day mode=manual",
        "trend": "/trend_search niche=công nghệ AI platform=tiktok channel=<ID> aff=<ID> campaign=<ID>",
        "auto": "/operator_auto niche=công nghệ AI platform=tiktok channel=all aff=<ID> campaign=<ID> limit=5",
        "rank": "/trend_rank\n/trend_rank 20",
        "affseed": "/affiliate_seed\n/affiliates",
        "affiliates": "/affiliates",
        "affreport": "/affiliate_report days=30\n/affiliate_report days=90 limit=20",
        "affdecisions": "/affiliate_decisions days=30 platform=tiktok limit=12\n/affiliate_decisions days=7 min_views=200",
        "affscale": "/affiliate_scale aff=<AFF_ID> platform=tiktok channel=all limit=5 campaign=<ID>\n/affiliate_scale aff=<AFF_ID> platform=tiktok channel=all limit=3 build=1 duration=45",
        "affideas": "/affiliate_ideas aff=<AFF_ID> platform=tiktok n=5 topic=trend đang nóng",
        "affmatch": "/affiliate_match niche=công nghệ AI platform=tiktok trend=AI agent creator",
        "affrelated": "/affiliate_related aff=<AFF_ID>\n/affiliate_related brand=Samsung niche=điện thoại limit=12",
        "affprofile": "/affiliate_profile id=<AFF_ID> price=199000 rate=8 audience=creator allowed=... blocked=... score=70",
        "pipeline": "/pipeline\n/pipeline <JOB_ID>",
        "calendar": "/calendar\n/calendar_plan days=7 channel=all campaign=<ID> aff=<ID> niche=công nghệ",
        "calendarplan": "/calendar_plan days=7 channel=all campaign=<ID> aff=<ID> niche=công nghệ",
        "publish": "/publish_pack job=<JOB_ID>\n/queue_publish job=<JOB_ID> mode=manual\n/mark_published job=<JOB_ID> url=https://... views=0 clicks=0 note=...",
        "approvepublish": "/approve_publish job=<JOB_ID> queue=1 mode=manual note=duyet_ok\nPOST /api/operator/jobs/<JOB_ID>/approve",
        "markpublished": "/mark_published job=<JOB_ID> url=https://... views=0 clicks=0 note=...",
        "readiness": "/publish_readiness\n/channel_publish_set id=<CHANNEL_ID> mode=api token_env=TIKTOK_ACCESS_TOKEN",
        "publishqueue": "/publish_queue\n/publisher_handoff queue=<QUEUE_ID>\n/publish_queue_set id=<QUEUE_ID> status=published url=https://...",
        "publisherhandoff": "/publisher_handoff queue=<QUEUE_ID>\nGET /api/operator/publish/<QUEUE_ID>/handoff",
        "publisherstatus": "/publisher_status\nGET /api/operator/publisher/status",
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
        "trackingreport": "/tracking_report days=30 limit=10\nGET /api/operator/tracking-report?days=30",
        "scaleplan": "/scale_plan days=30 platform=tiktok limit=10\nGET /api/operator/scale-plan?days=30",
        "scaleexecute": "/scale_execute days=30 platform=tiktok limit=3 per=3 build=1\nPOST /api/operator/scale-plan/run",
        "growth": "/growth\n/growth days=30",
        "loop": "/operator_loop\n/operator_loop limit=10 queue=1",
        "daily": "/operator_daily\n/operator_daily days=7",
        "tools": "/tools",
        "mmo": "/mmo",
        "campaignstats": "/campaign_stats",
        "checkpayos": "/checkpayos <ORDER_CODE>",
    }
    await query.edit_message_text(
        f"🧠 <b>AI OPERATOR MENU</b>\n\n"
        f"Lệnh nhanh:\n<pre>{html.escape(snippets.get(action, '/operator_dashboard'))}</pre>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Quay lại thư mục", callback_data="opmenu|root")]])
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
            "• <code>/brain đầu não nên làm gì tiếp theo</code>\n"
            "• <code>/brain đầu não chạy bước tiếp theo an toàn</code>\n"
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

async def cmd_approve_publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        job_id = int(data.get("job") or data.get("id") or context.args[0])
    except (IndexError, TypeError, ValueError):
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/approve_publish job=1 queue=1 mode=manual note=...</code>",
            parse_mode="HTML"
        )
    queue = str(data.get("queue") or data.get("enqueue") or "1").lower() not in {"0", "false", "no", "khong"}
    mode = (data.get("mode") or "manual").lower()
    if mode not in {"manual", "api"}:
        return await update.message.reply_text("⚠️ mode hợp lệ: <code>manual</code> hoặc <code>api</code>", parse_mode="HTML")
    note = data.get("note") or "admin_approved_publish"
    scheduled_at = data.get("schedule") or data.get("time") or ""
    ok, reason, info = approve_publish_job(update.effective_user.id, job_id, note=note, queue=queue, mode=mode, scheduled_at=scheduled_at)
    if not ok:
        if reason == "not_ready":
            missing = info.get("missing") or []
            lines = [f"⚠️ <b>Job #{job_id} chưa đủ điều kiện duyệt đăng</b>\n"]
            for item in missing[:8]:
                lines.append(f"• <code>{html.escape(item['key'])}</code>: {html.escape(item['detail'])}\n  Next: <code>{html.escape(item['next'])}</code>")
            return await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        return await update.message.reply_text(f"❌ Không duyệt được: <code>{html.escape(reason)}</code>", parse_mode="HTML")
    await update.message.reply_text(
        f"✅ <b>Đã duyệt publish job #{job_id}</b>\n"
        f"• Queue: <b>{'có' if info.get('queued') else 'không'}</b>\n"
        f"• Queue ID: <code>{info.get('queue_id') or '-'}</code>\n"
        f"• Mode: <code>{html.escape(mode)}</code>\n\n"
        f"Xem hàng đợi: <code>/publish_queue</code>",
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
    lines.append(
        "\nLệnh tiếp:\n"
        "<code>/publisher_handoff queue=&lt;QUEUE_ID&gt;</code>\n"
        "<code>/publish_queue_set id=&lt;QUEUE_ID&gt; status=published url=https://...</code>"
    )
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_publisher_handoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        queue_id = int(data.get("id") or data.get("queue") or context.args[0])
    except (IndexError, TypeError, ValueError):
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/publisher_handoff queue=&lt;QUEUE_ID&gt;</code>\n"
            "Lấy queue ID bằng <code>/publish_queue</code>.",
            parse_mode="HTML"
        )
    item = get_publish_queue_item(update.effective_user.id, queue_id)
    if not item:
        return await update.message.reply_text("❌ Không tìm thấy publish queue item.")
    payload = serialize_publish_queue_item(item)
    handoff = build_publisher_handoff(payload)
    copy = handoff.get("copy") or {}
    media = handoff.get("media") or {}
    lines = [
        f"📮 <b>PUBLISHER HANDOFF — QUEUE #{queue_id}</b>",
        f"• Job: <code>#{handoff.get('job_id') or '-'}</code>",
        f"• Platform/mode: <code>{html.escape(handoff.get('platform') or '-')}</code> / <code>{html.escape(handoff.get('mode') or '-')}</code>",
        f"• Auto publish: <b>{'có thể' if handoff.get('can_auto_publish') else 'manual/API chưa đủ token'}</b>",
        f"• Env cần có: <code>{html.escape(', '.join(handoff.get('required_env') or []) or '-')}</code>",
        f"• Final video: <code>{html.escape(media.get('final_video_url') or media.get('telegram_file_id') or 'thiếu')}</code>",
        "",
        "<b>Caption:</b>",
        f"<pre>{html_pre(copy.get('caption') or '-', 900)}</pre>",
        "<b>Comment ghim/link kèm:</b>",
        f"<pre>{html_pre(copy.get('pinned_comment') or '-', 900)}</pre>",
        "<b>Plan đăng:</b>",
    ]
    for step in handoff.get("api_plan") or []:
        lines.append(f"• {html.escape(step)}")
    lines.append(
        "\nSau khi đăng xong gọi:\n"
        f"<code>/publish_queue_set id={queue_id} status=published url=https://...</code>"
    )
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

async def cmd_tracking_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        days = max(1, min(int(data.get("days") or data.get("ngay") or (context.args[0] if context.args else 30)), 180))
    except (TypeError, ValueError):
        days = 30
    try:
        limit = max(3, min(int(data.get("limit") or 10), 30))
    except ValueError:
        limit = 10
    report = tracking_report_data(update.effective_user.id, days=days, limit=limit)
    lines = [
        f"📊 <b>AFFILIATE TRACKING FUNNEL — {days} ngày</b>",
        f"• Từ: <code>{html.escape(report['since'])}</code>",
        "",
        "<b>1. Link/affiliate tạo tiền:</b>",
    ]
    if report["affiliates"]:
        for item in report["affiliates"]:
            if not item["affiliate_id"]:
                continue
            lines.append(
                f"• aff #{item['affiliate_id']} | <b>{html.escape(item['product'] or '-')}</b> | score=<b>{item['score']}</b>\n"
                f"  views={item['views']} click={item['clicks']} conv={item['conversions']} rev={item['revenue']:,}đ cost={item['cost']:,}đ\n"
                f"  CTR={item['ctr']:.2f}% CVR={item['cvr']:.2f}% ROI={item['roi']:.1f}% | src={html.escape(', '.join(item.get('sources') or []) or '-')}"
            )
    else:
        lines.append("• Chưa có dữ liệu. Dùng tracking URL /r/<AFF_ID>?job=<JOB_ID>&src=tiktok_primary hoặc postback.")
    lines.append("\n<b>2. Source/caption/comment hiệu quả:</b>")
    if report["sources"]:
        for item in report["sources"][:limit]:
            lines.append(
                f"• <code>{html.escape(item['source'])}</code> | aff #{item['affiliate_id'] or '-'} {html.escape(item['product'] or '-')}\n"
                f"  click={item['clicks']} conv={item['conversions']} rev={item['revenue']:,}đ | CTR={item['ctr']:.2f}% CVR={item['cvr']:.2f}% ROI={item['roi']:.1f}%"
            )
    else:
        lines.append("• Chưa có source.")
    lines.append("\n<b>3. Job nên scale/remix:</b>")
    if report["jobs"]:
        for item in report["jobs"][:limit]:
            if not item["job_id"]:
                continue
            lines.append(
                f"• job #{item['job_id']} | <code>{html.escape(item['platform'] or '-')}</code> | score=<b>{item['score']}</b>\n"
                f"  click={item['clicks']} conv={item['conversions']} rev={item['revenue']:,}đ | {html.escape(item['topic'] or '-')}\n"
                f"  next: <code>/affiliate_scale aff={item['affiliate_id']} platform={item['platform'] or 'tiktok'} channel=all limit=3 build=1</code>"
            )
    else:
        lines.append("• Chưa có job performance.")
    lines.append("\nAPI: <code>GET /api/operator/tracking-report?days=30</code>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_scale_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        days = max(1, min(int(data.get("days") or data.get("ngay") or (context.args[0] if context.args else 30)), 180))
    except (TypeError, ValueError):
        days = 30
    try:
        limit = max(3, min(int(data.get("limit") or 10), 30))
    except ValueError:
        limit = 10
    platform = (data.get("platform") or "tiktok").lower()
    plan = scale_plan_data(update.effective_user.id, days=days, limit=limit, platform=platform)
    lines = [
        f"🎯 <b>AFFILIATE SCALE PLAN — {days} ngày</b>",
        f"• Từ: <code>{html.escape(plan['since'])}</code> | Platform mặc định: <code>{html.escape(platform)}</code>",
        f"• SCALE={plan['summary']['scale']} | FIX={plan['summary']['fix']} | TEST={plan['summary']['test']} | PAUSE={plan['summary']['pause']}",
        "",
    ]
    if not plan["plans"]:
        lines.append("📭 Chưa đủ dữ liệu. Hãy dùng tracking URL/postback hoặc ghi /performance_add trước.")
    for item in plan["plans"]:
        icon = {
            "SCALE": "🚀",
            "FIX_OFFER": "🛒",
            "FIX_CTA": "✍️",
            "TEST_MORE": "🧪",
            "PAUSE_CHECK": "⏸️",
        }.get(item["action"], "•")
        title = item["source"] or item["topic"] or item["product"] or f"aff #{item['affiliate_id']}"
        lines.append(
            f"{icon} <b>{html.escape(item['action'])}</b> | {html.escape(item['scope'])}: {html.escape(str(title)[:90])}\n"
            f"• aff=<code>{item['affiliate_id'] or '-'}</code> job=<code>{item['job_id'] or '-'}</code> score=<b>{item['score']}</b>\n"
            f"• view={item['views']} click={item['clicks']} conv={item['conversions']} rev={item['revenue']:,}đ cost={item['cost']:,}đ\n"
            f"• Lý do: {html.escape(item['reason'])}\n"
            f"• Next: <code>{html.escape(item['command'])}</code>"
        )
    lines.append("\nAPI: <code>GET /api/operator/scale-plan?days=30</code>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_scale_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        days = max(1, min(int(data.get("days") or data.get("ngay") or 30), 180))
    except ValueError:
        days = 30
    platform = (data.get("platform") or "tiktok").lower()
    try:
        limit = max(1, min(int(data.get("limit") or 3), 10))
    except ValueError:
        limit = 3
    try:
        per_affiliate_limit = max(1, min(int(data.get("per") or data.get("per_affiliate") or 3), 8))
    except ValueError:
        per_affiliate_limit = 3
    build = str(data.get("build") or "1").lower() not in {"0", "false", "no", "khong"}
    try:
        duration = max(15, min(int(data.get("duration") or 45), 120))
    except ValueError:
        duration = 45
    msg = await update.message.reply_text("🎯 Đang chạy scale plan an toàn từ funnel...")
    result = await execute_scale_plan_actions(
        update.effective_user.id,
        days=days,
        platform=platform,
        limit=limit,
        per_affiliate_limit=per_affiliate_limit,
        build=build,
        duration=duration,
        notify_admin=False,
    )
    lines = [
        "🎯 <b>SCALE PLAN EXECUTE</b>",
        f"• Executed: <b>{len(result['executed'])}</b>",
        f"• Skipped: <b>{len(result['skipped'])}</b>",
        f"• Platform: <code>{html.escape(platform)}</code>",
        "",
    ]
    if result["executed"]:
        lines.append("<b>Đã tạo job:</b>")
        for item in result["executed"][:8]:
            jobs = item.get("created_jobs") or []
            built = item.get("built_jobs") or []
            next_line = f"  next: <code>/tasks job={jobs[0]['job_id']}</code>" if jobs else "  next: <code>/tasks</code>"
            lines.append(
                f"🚀 aff #{item['affiliate_id']} | {html.escape(item.get('product') or item.get('affiliate', {}).get('product') or '-')}\n"
                f"  jobs={len(jobs)} built={len(built)} | reason={html.escape(item.get('reason') or '-')}\n"
                f"{next_line}"
            )
    if result["skipped"]:
        lines.append("\n<b>Bỏ qua/chờ xử lý:</b>")
        for item in result["skipped"][:8]:
            lines.append(
                f"• {html.escape(item.get('action') or '-')} | aff #{item.get('affiliate_id') or '-'} | "
                f"{html.escape(item.get('skip_reason') or item.get('reason') or '-')}"
            )
    lines.append("\nTiếp theo: <code>/operator_loop</code> hoặc <code>/tasks</code>")
    await msg.edit_text("\n".join(lines), parse_mode="HTML")

async def cmd_affiliate_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        days = max(1, min(int(data.get("days") or data.get("ngay") or (context.args[0] if context.args else 30)), 180))
    except (TypeError, ValueError):
        days = 30
    try:
        limit = max(3, min(int(data.get("limit") or 15), 30))
    except ValueError:
        limit = 15
    since, affiliate_rows, job_rows = affiliate_performance_report_data(update.effective_user.id, days=days, limit=limit)
    lines = [
        f"🔗 <b>AFFILIATE MONEY REPORT — {days} ngày</b>",
        f"• Từ: <code>{html.escape(since)}</code>",
        "",
        "<b>Link nên ưu tiên:</b>",
    ]
    if affiliate_rows:
        for (
            aid, network, product, niche, url, product_score, jobs, publishes, views,
            clicks, conversions, revenue, cost, events
        ) in affiliate_rows:
            score, ctr, cvr, roi = growth_score(views, clicks, conversions, revenue, cost)
            lines.append(
                f"• #{aid} | <code>{html.escape(network or '-')}</code> | <b>{html.escape(product or '-')}</b> | score=<b>{score}</b>\n"
                f"  niche={html.escape(niche or '-')} | jobs={jobs or 0} | post={publishes or 0} | events={events or 0}\n"
                f"  views={views or 0} click={clicks or 0} conv={conversions or 0} rev={int(revenue or 0):,}đ cost={int(cost or 0):,}đ\n"
                f"  CTR={ctr:.2f}% | CVR={cvr:.2f}% | ROI={roi:.1f}% | base={product_score or 0}\n"
                f"  <code>{html.escape((url or '-')[:80])}</code>"
            )
    else:
        lines.append("• Chưa có affiliate active. Dùng /affiliate_seed hoặc /affiliate_add.")
    lines.append("\n<b>Job affiliate gần đây/có hiệu quả:</b>")
    if job_rows:
        for (
            aid, network, product, job_id, platform, topic, status, publish_url,
            views, clicks, revenue, last_seen
        ) in job_rows[:10]:
            lines.append(
                f"• job #{job_id} | aff #{aid} {html.escape(product or '-') } | <code>{html.escape(platform or '-')}</code> | {html.escape(status or '-')}\n"
                f"  views={views or 0} click={clicks or 0} rev={int(revenue or 0):,}đ | {html.escape(last_seen or '-')}\n"
                f"  {html.escape(topic or '-')}\n"
                f"  url={html.escape(publish_url or '-')}"
            )
    else:
        lines.append("• Chưa có job nào gắn affiliate.")
    lines.append(
        "\nLệnh scale nhanh:\n"
        "<code>/affiliate_ideas aff=&lt;ID&gt; platform=tiktok n=5 topic=...</code>\n"
        "<code>/operator_auto niche=... platform=tiktok channel=all aff=&lt;ID&gt; campaign=&lt;ID&gt; limit=5</code>\n"
        "<code>/performance_add job=&lt;JOB_ID&gt; type=click|order|revenue value=1 amount=...</code>"
    )
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_affiliate_decisions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        days = max(1, min(int(data.get("days") or data.get("ngay") or (context.args[0] if context.args else 30)), 180))
    except (TypeError, ValueError):
        days = 30
    try:
        limit = max(3, min(int(data.get("limit") or 12), 30))
    except ValueError:
        limit = 12
    try:
        min_views = max(50, min(int(data.get("min_views") or data.get("views") or 200), 10000))
    except ValueError:
        min_views = 200
    platform = (data.get("platform") or data.get("nen") or "tiktok").lower()
    since, decisions, job_rows = affiliate_decision_data(
        update.effective_user.id,
        days=days,
        limit=limit,
        min_views=min_views,
        platform=platform,
    )
    lines = [
        f"🧠 <b>AFFILIATE SCALE DECISIONS — {days} ngày</b>",
        f"• Từ: <code>{html.escape(since)}</code>",
        f"• Rule: SCALE khi có revenue/conversion/score tốt; FIX khi có view/click nhưng chưa ra đơn; TEST khi thiếu dữ liệu.",
        "",
    ]
    if not decisions:
        lines.append("📭 Chưa có affiliate active. Chạy <code>/affiliate_seed</code> hoặc thêm bằng <code>/affiliate_add</code>.")
    else:
        for item in decisions[:limit]:
            related = item.get("related_links") or []
            related_hint = ""
            if related:
                related_hint = "\n  Link kèm: " + " | ".join(
                    f"#{row['id']} {row['product']}" for row in related[:3]
                )
            lines.append(
                f"• <b>{html.escape(item['action'])}</b> | aff #{item['id']} | "
                f"<code>{html.escape(item['network'] or '-')}</code> / <b>{html.escape(item['product'] or '-')}</b> | score=<b>{item['score']}</b>\n"
                f"  views={item['views']} click={item['clicks']} conv={item['conversions']} "
                f"rev={item['revenue']:,}đ cost={item['cost']:,}đ | CTR={item['ctr']:.2f}% CVR={item['cvr']:.2f}% ROI={item['roi']:.1f}%\n"
                f"  lý do: {html.escape(item['reason'])}{html.escape(related_hint)}\n"
                f"  next: <code>{html.escape(item['command'])}</code>"
            )
    lines.append(
        "\nGhi dữ liệu để quyết định chuẩn hơn:\n"
        "<code>/performance_add job=&lt;JOB_ID&gt; type=view value=1000</code>\n"
        "<code>/performance_add job=&lt;JOB_ID&gt; type=click value=20</code>\n"
        "<code>/performance_add job=&lt;JOB_ID&gt; type=revenue value=1 amount=150000</code>"
    )
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_operator_director(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        days = max(1, min(int(data.get("days") or data.get("ngay") or (context.args[0] if context.args else 30)), 180))
    except (TypeError, ValueError):
        days = 30
    try:
        limit = max(3, min(int(data.get("limit") or 10), 20))
    except ValueError:
        limit = 10
    platform = (data.get("platform") or data.get("nen") or "tiktok").lower()
    data_out = operator_director_data(update.effective_user.id, days=days, platform=platform, limit=limit)
    next_action = data_out.get("next_action") or {}
    counts = data_out["status"]["counts"]
    lines = [
        f"🧠 <b>AI OPERATOR DIRECTOR — {days} ngày</b>",
        f"• Platform: <code>{html.escape(platform)}</code>",
        f"• Ready scale: <b>{'có' if data_out['status']['ready_to_scale'] else 'chưa'}</b>",
        f"• Channels={counts['active_channels']} | Affiliates={counts['active_affiliates']} | Campaigns={counts['active_campaigns']} | Jobs mở={counts['open_jobs']} | Tasks mở={counts['open_tasks']}",
        "",
        "<b>Việc nên làm ngay:</b>",
    ]
    if next_action:
        api = next_action.get("api") or {}
        lines.append(
            f"• <b>{html.escape(next_action.get('action') or '-')}</b> | {html.escape(next_action.get('title') or '-')}\n"
            f"  {html.escape(next_action.get('detail') or '-')}\n"
            f"  Telegram: <code>{html.escape(next_action.get('telegram_command') or '-')}</code>"
        )
        if api:
            payload = api.get("payload")
            api_line = f"{api.get('method', 'GET')} {api.get('url', '-')}"
            lines.append(f"  API: <code>{html.escape(api_line)}</code>")
            if payload:
                lines.append(f"  Payload: <pre>{html_pre(json.dumps(payload, ensure_ascii=False), 700)}</pre>")
    else:
        lines.append("• Chưa có hành động rõ ràng.")

    lines.append("\n<b>Hàng đợi director:</b>")
    for item in data_out.get("actions", [])[1:limit]:
        lines.append(
            f"• {html.escape(item.get('action') or '-')} | {html.escape(item.get('title') or '-')}\n"
            f"  <code>{html.escape(item.get('telegram_command') or '-')}</code>"
        )
    lines.append(
        "\nAPI cho Claude/n8n: "
        "<code>GET /api/operator/director?days=30&amp;platform=tiktok</code>"
    )
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")

async def cmd_operator_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        days = max(1, min(int(data.get("days") or data.get("ngay") or 30), 180))
    except ValueError:
        days = 30
    try:
        limit = max(3, min(int(data.get("limit") or 10), 20))
    except ValueError:
        limit = 10
    try:
        duration = max(15, min(int(data.get("duration") or data.get("sec") or 45), 120))
    except ValueError:
        duration = 45
    platform = (data.get("platform") or data.get("nen") or "tiktok").lower()
    build = (data.get("build") or "1").lower() not in {"0", "false", "no", "off"}
    director = operator_director_data(update.effective_user.id, days=days, platform=platform, limit=limit)
    action = director.get("next_action")
    msg = await update.message.reply_text("🎛 Director Execute đang chạy action an toàn tiếp theo...")
    try:
        result = await execute_operator_director_action(update.effective_user.id, action, build=build, duration=duration)
    except Exception as e:
        await alert_admin(context, "Operator Execute", str(e))
        return await msg.edit_text("❌ Director Execute lỗi. Đã báo admin.")
    lines = [
        "🎛 <b>DIRECTOR EXECUTE</b>",
        f"• Action: <b>{html.escape((action or {}).get('action') or '-')}</b>",
        f"• Executed: <b>{'có' if result.get('executed') else 'chưa'}</b>",
    ]
    if result.get("message"):
        lines.append(f"• Ghi chú: {html.escape(str(result.get('message')))}")
    if result.get("created_jobs") is not None:
        lines.append(f"• Jobs tạo: <b>{len(result.get('created_jobs') or [])}</b>")
    if result.get("built_jobs") is not None:
        lines.append(f"• Jobs build: <b>{len(result.get('built_jobs') or [])}</b>")
    if result.get("queue_id"):
        lines.append(f"• Queue publish: <code>#{result.get('queue_id')}</code>")
    if result.get("next"):
        lines.append(f"\n<b>Next:</b>\n<pre>{html_pre(json.dumps(result.get('next'), ensure_ascii=False), 900)}</pre>")
    lines.append("\nXem tiếp: <code>/operator_director</code> | <code>/operator_loop</code> | <code>/publish_queue</code>")
    await msg.edit_text("\n".join(lines), parse_mode="HTML")

async def cmd_affiliate_scale(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    data = parse_key_value_args(" ".join(context.args))
    try:
        affiliate_id = int(data.get("id") or data.get("aff") or context.args[0])
    except (IndexError, TypeError, ValueError):
        return await update.message.reply_text(
            "⚠️ Cú pháp: <code>/affiliate_scale aff=&lt;AFF_ID&gt; platform=tiktok channel=all limit=5 campaign=&lt;ID&gt;</code>",
            parse_mode="HTML"
        )
    affiliate = get_affiliate_link(affiliate_id, update.effective_user.id)
    if not affiliate:
        return await update.message.reply_text("❌ Không tìm thấy affiliate hoặc không có quyền.")
    (
        aid, network, product, niche, url, note, status,
        price_vnd, commission_rate, audience, allowed_claims, blocked_claims, product_score
    ) = affiliate
    related = list_related_affiliate_links(update.effective_user.id, affiliate_id=aid, niche=niche or product, limit=8)
    related_text = format_related_affiliate_links(related, max_items=6)
    platform_filter = (data.get("platform") or data.get("nen") or "tiktok").lower()
    channel_filter = (data.get("channel") or data.get("kenh") or "all").lower()
    scale_niche = data.get("niche") or data.get("ngach") or niche or product or "affiliate"
    try:
        limit = max(1, min(int(data.get("limit") or data.get("max") or 5), 12))
    except ValueError:
        limit = 5
    auto_build = (data.get("build") or data.get("autobuild") or "0").lower() in {"1", "true", "yes", "on"}
    try:
        duration = max(15, min(int(data.get("duration") or data.get("sec") or 45), 120))
    except ValueError:
        duration = 45
    try:
        variant_count = max(3, min(int(data.get("variants") or data.get("n") or 5), 8))
    except ValueError:
        variant_count = 5
    try:
        campaign_id = int(data.get("campaign") or data.get("camp") or 0)
    except ValueError:
        campaign_id = 0
    if campaign_id and not get_campaign(campaign_id, update.effective_user.id):
        return await update.message.reply_text("❌ Không tìm thấy campaign hoặc không có quyền.")
    matched_campaign = None
    campaign_match_score = 0
    if not campaign_id:
        matched_campaign, campaign_match_score = find_matching_campaign(update.effective_user.id, scale_niche, platform_filter)
        if matched_campaign:
            campaign_id = matched_campaign[0]
    msg = await update.message.reply_text(
        f"🚀 Đang scale affiliate #{aid}: {html.escape(product or '-')}\n"
        "Bot sẽ tìm trend phù hợp và tạo production job..."
    )
    try:
        created_jobs, error = await create_operator_auto_jobs(
            update.effective_user.id,
            scale_niche,
            platform_filter,
            channel_filter,
            campaign_id,
            affiliate_id,
            limit,
        )
    except Exception as e:
        await alert_admin(context, "Affiliate Scale", f"{str(e)} | aff={affiliate_id} niche={scale_niche}")
        return await msg.edit_text("❌ Affiliate Scale lỗi khi tìm trend/tạo job. Đã báo admin.")
    if error:
        return await msg.edit_text(f"❌ {html.escape(error)}", parse_mode="HTML")
    if not created_jobs:
        return await msg.edit_text("📭 Chưa tạo được job nào. Kiểm tra lại channel active hoặc niche.")
    built = []
    failed = []
    if auto_build:
        for item in created_jobs:
            ok, bundle = build_operator_job_bundle(update.effective_user.id, item["job_id"], count=variant_count, duration=duration)
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
                failed.append((item["job_id"], bundle.get("error", "build lỗi")))
    lines = [
        f"✅ <b>ĐÃ SCALE AFFILIATE #{aid}</b>",
        f"• Sản phẩm: <b>{html.escape(product or '-')}</b>",
        f"• Network: <code>{html.escape(network or '-')}</code>",
        f"• Niche: <b>{html.escape(scale_niche)}</b>",
        f"• Platform: <code>{html.escape(platform_filter or 'auto')}</code>",
        f"• Channel: <code>{html.escape(channel_filter)}</code>",
        f"• Campaign: <code>{campaign_id or 'chưa gắn'}</code>"
        + (f" | auto match score={campaign_match_score}" if matched_campaign else ""),
        f"• Job tạo mới: <b>{len(created_jobs)}</b>",
        f"• Auto build: <b>{'bật' if auto_build else 'tắt'}</b>",
        "",
    ]
    if related_text:
        lines.extend([
            "<b>Link liên quan nên chèn kèm caption/comment/status:</b>",
            f"<pre>{html_pre(related_text)}</pre>",
            "",
        ])
    lines.append("<b>Job mới:</b>")
    for item in created_jobs[:10]:
        build_note = ""
        built_item = next((row for row in built if row["job_id"] == item["job_id"]), None)
        if built_item:
            build_note = f" | manifest #{built_item['manifest_id']} | tasks={built_item['task_count']} | {built_item['readiness']}"
        lines.append(
            f"• job #{item['job_id']} | trend #{item['trend_id']} | score=<b>{item['score']}</b> | "
            f"<code>{html.escape(item['platform'] or '-')}</code> | {html.escape(item['channel_name'] or '-')}{html.escape(build_note)}\n"
            f"  {html.escape(item['title'])}\n"
            f"  lý do: {html.escape(item.get('reason') or '-')}"
        )
    if failed:
        lines.append("\n<b>Build lỗi:</b>")
        for job_id, reason in failed[:8]:
            lines.append(f"• job #{job_id}: {html.escape(reason)}")
    lines.append(
        "\nBước tiếp:\n"
        "<code>/operator_build job=&lt;JOB_ID&gt; n=5 duration=45</code>\n"
        "<code>/affiliate_scale aff=%s platform=%s channel=%s limit=%s campaign=%s build=1 duration=%s</code>"
        % (
            aid,
            html.escape(platform_filter or "tiktok"),
            html.escape(channel_filter),
            limit,
            campaign_id or "&lt;ID&gt;",
            duration,
        )
    )
    await msg.edit_text("\n".join(lines), parse_mode="HTML")

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
    static_pack = build_static_publish_pack(job, update.effective_user.id)
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
        f"<b>Link chính:</b> <code>{html.escape((static_pack.get('primary_affiliate') or {}).get('url') or '-')}</code>\n"
        f"<b>Comment ghim/link kèm:</b>\n<pre>{html_pre(static_pack.get('pinned_comment') or '-', 900)}</pre>\n"
        f"<b>Ghi performance sau đăng:</b>\n"
        f"<code>{html.escape((static_pack.get('performance_plan') or {}).get('after_publish') or '')}</code>\n\n"
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
    tg_app.add_handler(CommandHandler("publisher_status", cmd_publisher_status))
    tg_app.add_handler(CommandHandler("affiliate_add", cmd_affiliate_add))
    tg_app.add_handler(CommandHandler("affiliate_seed", cmd_affiliate_seed))
    tg_app.add_handler(CommandHandler("affiliates",  cmd_affiliates))
    tg_app.add_handler(CommandHandler("affiliate_profile", cmd_affiliate_profile))
    tg_app.add_handler(CommandHandler("affiliate_match", cmd_affiliate_match))
    tg_app.add_handler(CommandHandler("affiliate_ideas", cmd_affiliate_ideas))
    tg_app.add_handler(CommandHandler("affiliate_related", cmd_affiliate_related))
    tg_app.add_handler(CommandHandler("calendar_plan", cmd_calendar_plan))
    tg_app.add_handler(CommandHandler("calendar",    cmd_calendar))
    tg_app.add_handler(CommandHandler("operator",    cmd_operator))
    tg_app.add_handler(CommandHandler("operator_build", cmd_operator_build))
    tg_app.add_handler(CommandHandler("operator_auto", cmd_operator_auto))
    tg_app.add_handler(CommandHandler("operator_next", cmd_operator_next))
    tg_app.add_handler(CommandHandler("operator_dashboard", cmd_operator_dashboard))
    tg_app.add_handler(CommandHandler("operator_daily", cmd_operator_daily))
    tg_app.add_handler(CommandHandler("operator_status", cmd_operator_status))
    tg_app.add_handler(CommandHandler("operator_audit", cmd_operator_audit))
    tg_app.add_handler(CommandHandler("operator_playbook", cmd_operator_playbook))
    tg_app.add_handler(CommandHandler("operator_director", cmd_operator_director))
    tg_app.add_handler(CommandHandler("operator_execute", cmd_operator_execute))
    tg_app.add_handler(CommandHandler("operator_today", cmd_operator_today))
    tg_app.add_handler(CommandHandler("operator_menu", cmd_operator_menu))
    tg_app.add_handler(CommandHandler("operator_api", cmd_operator_api))
    tg_app.add_handler(CommandHandler("operator_worker_spec", cmd_operator_worker_spec))
    tg_app.add_handler(CommandHandler("operator_toolchain", cmd_operator_toolchain))
    tg_app.add_handler(CommandHandler("operator_tool_events", cmd_operator_tool_events))
    tg_app.add_handler(CommandHandler("operator_n8n_template", cmd_operator_n8n_template))
    tg_app.add_handler(CommandHandler("operator_n8n_workflow", cmd_operator_n8n_workflow))
    tg_app.add_handler(CommandHandler("operator_loop", cmd_operator_loop))
    tg_app.add_handler(CommandHandler("brain", cmd_brain))
    tg_app.add_handler(CommandHandler("autopilot", cmd_autopilot))
    tg_app.add_handler(CommandHandler("make_video", cmd_make_video))
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
    tg_app.add_handler(CommandHandler("approve_publish", cmd_approve_publish))
    tg_app.add_handler(CommandHandler("publish_queue", cmd_publish_queue))
    tg_app.add_handler(CommandHandler("publisher_handoff", cmd_publisher_handoff))
    tg_app.add_handler(CommandHandler("publish_queue_set", cmd_publish_queue_set))
    tg_app.add_handler(CommandHandler("asset_add", cmd_asset_add))
    tg_app.add_handler(CommandHandler("assets", cmd_assets))
    tg_app.add_handler(CommandHandler("job_report", cmd_job_report))
    tg_app.add_handler(CommandHandler("job_ready", cmd_job_ready))
    tg_app.add_handler(CommandHandler("mark_published", cmd_mark_published))
    tg_app.add_handler(CommandHandler("performance_add", cmd_performance_add))
    tg_app.add_handler(CommandHandler("performance", cmd_performance))
    tg_app.add_handler(CommandHandler("tracking_report", cmd_tracking_report))
    tg_app.add_handler(CommandHandler("scale_plan", cmd_scale_plan))
    tg_app.add_handler(CommandHandler("scale_execute", cmd_scale_execute))
    tg_app.add_handler(CommandHandler("affiliate_report", cmd_affiliate_report))
    tg_app.add_handler(CommandHandler("affiliate_decisions", cmd_affiliate_decisions))
    tg_app.add_handler(CommandHandler("affiliate_scale", cmd_affiliate_scale))
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

@fastapi_app.get("/LOGO.png")
@fastapi_app.get("/logo.png")
async def logo_image():
    logo_path = os.path.join(os.path.dirname(__file__), "LOGO.png")
    if not os.path.exists(logo_path):
        raise HTTPException(status_code=404, detail="Logo not found")
    return FileResponse(logo_path, media_type="image/png")

@fastapi_app.get("/r/{affiliate_id}")
async def affiliate_redirect(affiliate_id: int, request: Request, job: int = 0, src: str = ""):
    affiliate = get_affiliate_link(affiliate_id, ADMIN_ID)
    if not affiliate:
        raise HTTPException(status_code=404, detail="Affiliate link not found")
    aid, network, product_name, niche, url, commission_note, status, *_ = affiliate
    if (status or "active").lower() != "active" or not url:
        raise HTTPException(status_code=404, detail="Affiliate link is inactive")
    if not re.match(r"^https?://", url, re.IGNORECASE):
        raise HTTPException(status_code=400, detail="Affiliate URL must start with http:// or https://")
    note_parts = [f"redirect_affiliate:{aid}", f"network:{network or '-'}", f"product:{product_name or '-'}"]
    if src:
        note_parts.append(f"src:{src[:80]}")
    referer = request.headers.get("referer") or ""
    if referer:
        note_parts.append(f"ref:{referer[:160]}")
    if job:
        add_performance_event(ADMIN_ID, job, "click", 1, 0, " | ".join(note_parts), affiliate_id_override=aid)
    return RedirectResponse(url=url, status_code=302)

@fastapi_app.post("/api/affiliate/postback")
async def affiliate_postback(payload: AffiliatePostbackRequest, request: Request):
    token = payload.token or request.headers.get("x-affiliate-postback-token", "")
    if AFFILIATE_POSTBACK_TOKEN and not hmac.compare_digest(str(token), AFFILIATE_POSTBACK_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid affiliate postback token")
    ok, reason, info = record_affiliate_postback(
        ADMIN_ID,
        job_id=payload.job_id,
        affiliate_id=payload.affiliate_id,
        event_type=payload.event_type,
        value=payload.value,
        amount=payload.amount,
        source=payload.source,
        order_id=payload.order_id,
        note=payload.note,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=reason)
    if tg_app and ADMIN_ID and payload.amount > 0:
        try:
            await tg_app.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"💰 <b>AFFILIATE POSTBACK</b>\n\n"
                    f"• Job: <code>#{info.get('job_id')}</code> | Affiliate: <code>{info.get('affiliate_id') or '-'}</code>\n"
                    f"• Type: <code>{html.escape(info.get('event_type') or '-')}</code> | Value: <b>{payload.value}</b>\n"
                    f"• Amount: <b>{payload.amount:,}đ</b>\n"
                    f"• Order: <code>{html.escape(payload.order_id or '-')}</code>\n"
                    f"• Source: <code>{html.escape(payload.source or 'affiliate_postback')}</code>"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Affiliate postback notify error: {e}")
    return {"ok": True, **info}

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

@fastapi_app.get("/api/operator/status")
async def api_operator_status(request: Request):
    verify_operator_api_token(request)
    data = operator_status_data(ADMIN_ID)
    channel_readiness = []
    for row, readiness, reason in data["channel_readiness"]:
        cid, platform, channel_name, account_label, status, publish_mode, token_env, page_id = row
        channel_readiness.append({
            "id": cid,
            "platform": platform,
            "channel_name": channel_name,
            "account_label": account_label,
            "status": status,
            "publish_mode": publish_mode,
            "token_env": token_env,
            "page_id": page_id,
            "readiness": readiness,
            "reason": reason,
        })
    return {
        "ok": True,
        "ready_to_scale": data["ready_to_scale"],
        "counts": data["counts"],
        "checks": [
            {"key": key, "ok": ok, "detail": detail, "next": next_cmd}
            for key, ok, detail, next_cmd in data["checks"]
        ],
        "channel_readiness": channel_readiness,
        "blocked_jobs": [
            {
                "job_id": jid,
                "stage": stage,
                "status": status,
                "platform": platform,
                "topic": topic,
                "channel_name": channel_name,
                "affiliate_product": product_name,
                "updated_at": updated_at,
                "ready_url": f"/api/operator/jobs/{jid}/ready",
            }
            for jid, stage, status, platform, topic, channel_name, product_name, updated_at in data["blocked_jobs"]
        ],
        "next": {
            "telegram": "/operator_status",
            "audit": "/api/operator/audit",
            "worker_spec": "/api/operator/worker-spec",
            "toolchain": "/api/operator/toolchain",
            "tool_events": "/api/operator/tool-events",
            "n8n_template": "/api/operator/n8n-template",
            "n8n_workflow": "/api/operator/n8n-workflow.json",
            "director": "/api/operator/director",
            "make_video": "/api/operator/make-video",
            "affiliate_report": "/api/operator/affiliate-report",
            "tracking_report": "/api/operator/tracking-report",
            "scale_plan": "/api/operator/scale-plan",
            "scale_plan_run": "/api/operator/scale-plan/run",
            "affiliate_decisions": "/api/operator/affiliate-decisions",
            "affiliate_scale": "/api/operator/affiliate-scale",
            "approve_publish": "/api/operator/jobs/<JOB_ID>/approve",
            "loop": "/api/operator/loop",
        },
    }

@fastapi_app.get("/api/operator/publisher/status")
async def api_operator_publisher_status(request: Request):
    verify_operator_api_token(request)
    data = publisher_status_data(ADMIN_ID)
    return {"ok": True, **data}

@fastapi_app.get("/api/operator/audit")
async def api_operator_audit(request: Request):
    verify_operator_api_token(request)
    data = operator_audit_data(ADMIN_ID)
    return {
        "ok": True,
        "level": data["level"],
        "score": data["score"],
        "checks": [
            {"key": key, "ok": ok, "detail": detail, "next": next_cmd}
            for key, ok, detail, next_cmd in data["checks"]
        ],
        "blockers": data["blockers"],
        "channel_issues": data["channel_issues"],
        "counts": data["counts"],
        "next_command": data["next_command"],
        "rule": "Score >=85 with API/content/publish readiness means ready for director-run automation. Missing checks must be configured before claiming full automation.",
    }

@fastapi_app.get("/api/operator/worker-spec")
async def api_operator_worker_spec(request: Request):
    verify_operator_api_token(request)
    return {"ok": True, "spec": operator_worker_spec_data()}

@fastapi_app.get("/api/operator/toolchain")
async def api_operator_toolchain(request: Request):
    verify_operator_api_token(request)
    return {"ok": True, "toolchain": operator_toolchain_data()}

@fastapi_app.get("/api/operator/tool-events")
async def api_operator_tool_events(request: Request, limit: int = 20, stage: str = "", severity: str = ""):
    verify_operator_api_token(request)
    rows = list_tool_events(ADMIN_ID, limit=limit, stage=(stage or "").lower(), severity=(severity or "").lower())
    return {"ok": True, "events": [serialize_tool_event(row) for row in rows]}

@fastapi_app.post("/api/operator/tool-events")
async def api_operator_tool_event(payload: OperatorToolEventRequest, request: Request):
    verify_operator_api_token(request)
    event_id = record_tool_event(
        ADMIN_ID,
        payload.stage,
        payload.tool_name,
        payload.event_type,
        payload.severity,
        payload.job_id,
        payload.task_id,
        payload.fallback_tool,
        payload.message,
    )
    if tg_app and ADMIN_ID and payload.notify_admin and payload.severity.lower() in {"warning", "critical"}:
        try:
            await tg_app.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    "🧯 <b>TOOL EVENT / FALLBACK ALERT</b>\n\n"
                    f"• Event: <code>#{event_id}</code> | Severity: <b>{html.escape(payload.severity)}</b>\n"
                    f"• Stage: <code>{html.escape(payload.stage or '-')}</code>\n"
                    f"• Tool: <code>{html.escape(payload.tool_name or '-')}</code>\n"
                    f"• Type: <code>{html.escape(payload.event_type or '-')}</code>\n"
                    f"• Fallback: <code>{html.escape(payload.fallback_tool or '-')}</code>\n"
                    f"• Job/task: <code>{payload.job_id or '-'}</code>/<code>{payload.task_id or '-'}</code>\n"
                    f"• Message: {html.escape(payload.message or '-')}"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Tool event notify error: {e}")
    return {
        "ok": True,
        "event_id": event_id,
        "next": {
            "toolchain": "/api/operator/toolchain",
            "events": "/api/operator/tool-events",
            "telegram": "/operator_tool_events",
        },
    }

@fastapi_app.get("/api/operator/n8n-template")
async def api_operator_n8n_template(request: Request):
    verify_operator_api_token(request)
    return {"ok": True, "template": operator_n8n_template_data()}

@fastapi_app.get("/api/operator/n8n-workflow.json")
async def api_operator_n8n_workflow(request: Request):
    verify_operator_api_token(request)
    return operator_n8n_workflow_json_data()

@fastapi_app.get("/api/operator/director")
async def api_operator_director(request: Request, days: int = 30, platform: str = "tiktok", limit: int = 10):
    verify_operator_api_token(request)
    days = max(1, min(int(days or 30), 180))
    limit = max(3, min(int(limit or 10), 20))
    platform = (platform or "tiktok").lower()
    data = operator_director_data(ADMIN_ID, days=days, platform=platform, limit=limit)
    return {
        "ok": True,
        "days": days,
        "platform": platform,
        "ready_to_scale": data["status"]["ready_to_scale"],
        "counts": data["status"]["counts"],
        "next_action": data["next_action"],
        "actions": data["actions"],
        "rule": data["rule"],
        "next": {
            "director_url": "/api/operator/director",
            "scale_url": "/api/operator/affiliate-scale",
            "tasks_url": "/api/operator/tasks/next",
            "publish_url": "/api/operator/publish/next",
            "performance_url": "/api/operator/performance",
        },
    }

@fastapi_app.post("/api/operator/director/run")
async def api_operator_director_run(payload: OperatorDirectorRunRequest, request: Request):
    verify_operator_api_token(request)
    data = operator_director_data(ADMIN_ID, days=payload.days, platform=payload.platform.lower(), limit=payload.limit)
    action = data.get("next_action")
    result = {"executed": False, "message": "execute=false", "action": (action or {}).get("action")}
    if payload.execute:
        result = await execute_operator_director_action(
            ADMIN_ID,
            action,
            build=payload.build,
            duration=payload.duration,
        )
    if payload.notify_admin and tg_app and ADMIN_ID:
        try:
            await tg_app.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    "🎛 <b>OPERATOR DIRECTOR RUN</b>\n\n"
                    f"• Action: <b>{html.escape((action or {}).get('action') or '-')}</b>\n"
                    f"• Executed: <b>{'có' if result.get('executed') else 'chưa'}</b>\n"
                    f"• Note: {html.escape(str(result.get('message') or '-'))}\n"
                    f"• Xem: <code>/operator_director</code>"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Operator director run notify error: {e}")
    return {
        "ok": True,
        "director": {
            "next_action": action,
            "ready_to_scale": data["status"]["ready_to_scale"],
            "counts": data["status"]["counts"],
        },
        "result": result,
        "next": {
            "director_url": "/api/operator/director",
            "tasks_url": "/api/operator/tasks/next",
            "publish_url": "/api/operator/publish/next",
            "performance_url": "/api/operator/performance",
        },
    }

@fastapi_app.get("/api/operator/today")
async def api_operator_today(request: Request):
    verify_operator_api_token(request)
    data = operator_today_data(ADMIN_ID)
    best = None
    if data["best_affiliate"]:
        score, row, ctr, cvr, roi = data["best_affiliate"]
        aid, network, product, niche, url, product_score, jobs, publishes, views, clicks, conversions, revenue, cost, events = row
        best = {
            "id": aid,
            "network": network,
            "product": product,
            "niche": niche,
            "url": url,
            "score": score,
            "views": int(views or 0),
            "clicks": int(clicks or 0),
            "conversions": int(conversions or 0),
            "revenue": int(revenue or 0),
            "cost": int(cost or 0),
            "ctr": round(ctr, 2),
            "cvr": round(cvr, 2),
            "roi": round(roi, 1),
        }
    return {
        "ok": True,
        "ready_to_scale": data["status"]["ready_to_scale"],
        "counts": data["status"]["counts"],
        "actions": data["actions"],
        "best_affiliate": best,
        "next": {
            "director_url": "/api/operator/director",
            "status_url": "/api/operator/status",
            "affiliate_report_url": "/api/operator/affiliate-report",
            "affiliate_decisions_url": "/api/operator/affiliate-decisions",
            "affiliate_scale_url": "/api/operator/affiliate-scale",
            "tasks_url": "/api/operator/tasks/next",
            "telegram": "/operator_today",
        },
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

@fastapi_app.post("/api/operator/jobs/{job_id}/approve")
async def api_operator_approve_publish(job_id: int, payload: OperatorApprovePublishRequest, request: Request):
    verify_operator_api_token(request)
    mode = (payload.mode or "manual").lower()
    if mode not in {"manual", "api"}:
        raise HTTPException(status_code=400, detail="mode must be manual or api")
    ok, reason, info = approve_publish_job(
        ADMIN_ID,
        job_id,
        note=payload.note or "api_approved_publish",
        queue=payload.queue,
        mode=mode,
        scheduled_at=payload.scheduled_at,
    )
    if not ok:
        status_code = 404 if reason == "job_not_found" else 400
        raise HTTPException(status_code=status_code, detail={"reason": reason, **info})
    if tg_app and ADMIN_ID and payload.notify_admin:
        try:
            await tg_app.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"✅ <b>OPERATOR APPROVED PUBLISH</b>\n\n"
                    f"• Job: <code>#{job_id}</code>\n"
                    f"• Queue: <b>{'có' if info.get('queued') else 'không'}</b> | ID: <code>{info.get('queue_id') or '-'}</code>\n"
                    f"• Mode: <code>{html.escape(mode)}</code>\n"
                    f"• Note: {html.escape(payload.note or '-')}"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Approve publish notify error: {e}")
    return {"ok": True, "job_id": job_id, **info}

@fastapi_app.get("/api/operator/jobs/{job_id}/publish-pack")
async def api_operator_job_publish_pack(job_id: int, request: Request):
    verify_operator_api_token(request)
    job = get_production_job(job_id, ADMIN_ID)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    readiness = production_readiness_data(ADMIN_ID, job_id)
    return {
        "ok": True,
        "job_id": job_id,
        "readiness": {
            "level": (readiness or {}).get("level", "UNKNOWN"),
            "next_action": (readiness or {}).get("next_action", ""),
        },
        "publish_pack": build_static_publish_pack(job, ADMIN_ID),
        "rule": "Use this pack for manual/API publishing. Do not publish if review/compliance is blocked.",
        "next": {
            "queue_url": "/api/operator/publish/next",
            "complete_url": "/api/operator/publish/<QUEUE_ID>/complete",
            "performance_url": "/api/operator/performance",
        },
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

@fastapi_app.post("/api/operator/make-video")
async def api_operator_make_video(payload: OperatorMakeVideoRequest, request: Request):
    verify_operator_api_token(request)
    ok, reason, result = await make_video_pipeline(
        ADMIN_ID,
        payload.topic,
        platform=payload.platform,
        channel=payload.channel,
        affiliate_id=payload.affiliate_id,
        campaign_id=payload.campaign_id,
        limit=payload.limit,
        build=payload.build,
        duration=payload.duration,
        variants=payload.variants,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=reason)
    if payload.notify_admin and tg_app and ADMIN_ID:
        try:
            affiliate = result.get("affiliate") or {}
            await tg_app.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    "🎬 <b>OPERATOR API MAKE VIDEO</b>\n\n"
                    f"• Topic: <b>{html.escape(payload.topic)}</b>\n"
                    f"• Platform/channel: <code>{html.escape(payload.platform)}</code> / <code>{html.escape(payload.channel)}</code>\n"
                    f"• Affiliate: <code>#{affiliate.get('id') or '-'}</code> {html.escape(affiliate.get('product') or '')}\n"
                    f"• Jobs: <b>{len(result.get('created_jobs') or [])}</b> | Built: <b>{len(result.get('built_jobs') or [])}</b>\n"
                    "• Next: <code>/tasks</code> → <code>/review_gate</code> → <code>/approve_publish</code>"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Operator make-video notify error: {e}")
    return {
        "ok": True,
        **result,
        "next": {
            "tasks_url": "/api/operator/tasks/next",
            "ready_url": "/api/operator/jobs/<JOB_ID>/ready",
            "publish_pack_url": "/api/operator/jobs/<JOB_ID>/publish-pack",
            "approve_url": "/api/operator/jobs/<JOB_ID>/approve",
            "publish_queue_url": "/api/operator/publish/next",
        },
        "rule": "Creates monetizable video production jobs and task bundles only. Real publishing still requires review/approval gate.",
    }

@fastapi_app.post("/api/operator/affiliate-scale")
async def api_operator_affiliate_scale(payload: OperatorAffiliateScaleRequest, request: Request):
    verify_operator_api_token(request)
    affiliate = get_affiliate_link(payload.affiliate_id, ADMIN_ID)
    if not affiliate:
        raise HTTPException(status_code=404, detail="Affiliate not found")
    if payload.campaign_id and not get_campaign(payload.campaign_id, ADMIN_ID):
        raise HTTPException(status_code=404, detail="Campaign not found")
    (
        aid, network, product, affiliate_niche, url, note, status,
        price_vnd, commission_rate, audience, allowed_claims, blocked_claims, product_score
    ) = affiliate
    scale_niche = payload.niche or affiliate_niche or product or "affiliate"
    campaign_id = payload.campaign_id
    matched_campaign = None
    campaign_match_score = 0
    if not campaign_id:
        matched_campaign, campaign_match_score = find_matching_campaign(ADMIN_ID, scale_niche, payload.platform or "tiktok")
        if matched_campaign:
            campaign_id = matched_campaign[0]
    created_jobs, error = await create_operator_auto_jobs(
        ADMIN_ID,
        scale_niche,
        (payload.platform or "tiktok").lower(),
        payload.channel or "all",
        campaign_id,
        payload.affiliate_id,
        payload.limit,
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    built = []
    failed = []
    if payload.build:
        for item in created_jobs:
            ok, bundle = build_operator_job_bundle(ADMIN_ID, item["job_id"], count=payload.variants, duration=payload.duration)
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
                failed.append({"job_id": item["job_id"], "error": bundle.get("error", "build lỗi")})
    if payload.notify_admin and tg_app and ADMIN_ID:
        try:
            await tg_app.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"🚀 <b>OPERATOR API AFFILIATE SCALE</b>\n\n"
                    f"• Affiliate: <code>#{aid}</code> {html.escape(product or '-')}\n"
                    f"• Niche: <b>{html.escape(scale_niche)}</b>\n"
                    f"• Campaign: <code>{campaign_id or 'chưa gắn'}</code>"
                    + (f" | auto score={campaign_match_score}" if matched_campaign else "")
                    + "\n"
                    f"• Platform/channel: <code>{html.escape(payload.platform or 'tiktok')}</code> / <code>{html.escape(payload.channel or 'all')}</code>\n"
                    f"• Jobs: <b>{len(created_jobs)}</b> | Built: <b>{len(built)}</b> | Failed: <b>{len(failed)}</b>\n"
                    f"• Xem: <code>/affiliate_report days=30</code> hoặc <code>/operator_dashboard</code>"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Operator affiliate scale notify error: {e}")
    return {
        "ok": True,
        "affiliate": {
            "id": aid,
            "network": network,
            "product": product,
            "niche": affiliate_niche,
            "url": url,
        },
        "scale_niche": scale_niche,
        "campaign": {
            "id": campaign_id,
            "auto_matched": bool(matched_campaign and not payload.campaign_id),
            "match_score": campaign_match_score,
            "name": matched_campaign[1] if matched_campaign else "",
            "niche": matched_campaign[2] if matched_campaign else "",
            "platforms": matched_campaign[3] if matched_campaign else "",
        },
        "created_jobs": created_jobs,
        "built_jobs": built,
        "failed_builds": failed,
        "next": {
            "tasks_url": "/api/operator/tasks/next",
            "loop_url": "/api/operator/loop",
            "publish_url": "/api/operator/publish/next",
            "telegram_report": "/affiliate_report days=30",
        },
    }

@fastapi_app.get("/api/operator/affiliates")
async def api_operator_affiliates(request: Request, limit: int = 50):
    verify_operator_api_token(request)
    limit = max(1, min(int(limit or 50), 100))
    rows = list_affiliate_links(ADMIN_ID, limit=limit)
    return {
        "ok": True,
        "affiliates": [
            {
                "id": aid,
                "network": network,
                "product": product,
                "niche": niche,
                "url": url,
                "commission_note": note,
                "status": status,
                "price_vnd": int(price_vnd or 0),
                "commission_rate": float(commission_rate or 0),
                "target_audience": audience,
                "allowed_claims": allowed_claims,
                "blocked_claims": blocked_claims,
                "product_score": int(product_score or 0),
                "scale_url": "/api/operator/affiliate-scale",
            }
            for (
                aid, network, product, niche, url, note, status,
                price_vnd, commission_rate, audience, allowed_claims, blocked_claims, product_score
            ) in rows
        ],
        "rule": "Pick an active affiliate id, then call POST /api/operator/affiliate-scale. Keep affiliate claims compliant.",
    }

@fastapi_app.get("/api/operator/channels")
async def api_operator_channels(request: Request, limit: int = 50):
    verify_operator_api_token(request)
    limit = max(1, min(int(limit or 50), 100))
    rows = list_social_channels(ADMIN_ID, limit=limit)
    readiness_rows = {row[0]: row for row in list_social_publish_readiness(ADMIN_ID)}
    channels = []
    for cid, platform, name, account, focus, audience, slots, status in rows:
        readiness_row = readiness_rows.get(cid)
        readiness = "unknown"
        reason = "Chưa có dữ liệu readiness."
        publish_mode = "manual"
        token_env = ""
        page_id = ""
        if readiness_row:
            _, _, _, _, _, publish_mode, token_env, page_id = readiness_row
            readiness, reason = channel_publish_readiness(readiness_row)
        channels.append({
            "id": cid,
            "platform": platform,
            "channel_name": name,
            "account_label": account,
            "topic_focus": focus,
            "audience": audience,
            "posting_slots": slots,
            "status": status,
            "publish_mode": publish_mode or "manual",
            "token_env": token_env,
            "page_id": page_id,
            "readiness": readiness,
            "reason": reason,
            "can_manual_publish": readiness in {"manual_ready", "api_ready", "manual_required"},
            "can_api_publish": readiness == "api_ready",
        })
    return {
        "ok": True,
        "channels": channels,
        "rule": "Use active channels for affiliate-scale. Use api_ready only for automated publisher workers; manual_ready still requires admin/manual posting.",
        "next": {
            "scale_url": "/api/operator/affiliate-scale",
            "publish_next_url": "/api/operator/publish/next",
            "status_url": "/api/operator/status",
        },
    }

@fastapi_app.get("/api/operator/campaigns")
async def api_operator_campaigns(request: Request, limit: int = 30):
    verify_operator_api_token(request)
    limit = max(1, min(int(limit or 30), 100))
    rows = list_campaigns(ADMIN_ID, limit=limit)
    campaigns = []
    for cid, name, niche, platforms, affiliate_url, status in rows:
        detail = get_campaign(cid, ADMIN_ID)
        pay_url = detail[6] if detail else ""
        campaigns.append({
            "id": cid,
            "name": name,
            "niche": niche,
            "platforms": platforms,
            "affiliate_url": affiliate_url,
            "pay_url": pay_url,
            "status": status,
            "use_in_affiliate_scale": f"campaign_id={cid}",
        })
    return {
        "ok": True,
        "campaigns": campaigns,
        "rule": "Pick an active campaign whose niche/platform matches the affiliate and channel. Pass campaign_id to POST /api/operator/affiliate-scale.",
        "next": {
            "channels_url": "/api/operator/channels",
            "affiliates_url": "/api/operator/affiliates",
            "scale_url": "/api/operator/affiliate-scale",
        },
    }

@fastapi_app.get("/api/operator/affiliate-report")
async def api_operator_affiliate_report(request: Request, days: int = 30, limit: int = 15):
    verify_operator_api_token(request)
    days = max(1, min(int(days or 30), 180))
    limit = max(3, min(int(limit or 15), 30))
    since, affiliate_rows, job_rows = affiliate_performance_report_data(ADMIN_ID, days=days, limit=limit)
    affiliates = []
    for (
        aid, network, product, niche, url, product_score, jobs, publishes, views,
        clicks, conversions, revenue, cost, events
    ) in affiliate_rows:
        score, ctr, cvr, roi = growth_score(views, clicks, conversions, revenue, cost)
        affiliates.append({
            "id": aid,
            "network": network,
            "product": product,
            "niche": niche,
            "url": url,
            "score": score,
            "base_score": int(product_score or 0),
            "jobs": int(jobs or 0),
            "publishes": int(publishes or 0),
            "views": int(views or 0),
            "clicks": int(clicks or 0),
            "conversions": int(conversions or 0),
            "revenue": int(revenue or 0),
            "cost": int(cost or 0),
            "events": int(events or 0),
            "ctr": round(ctr, 2),
            "cvr": round(cvr, 2),
            "roi": round(roi, 1),
        })
    jobs = [
        {
            "affiliate_id": aid,
            "network": network,
            "product": product,
            "job_id": job_id,
            "platform": platform,
            "topic": topic,
            "status": status,
            "publish_url": publish_url,
            "views": int(views or 0),
            "clicks": int(clicks or 0),
            "revenue": int(revenue or 0),
            "last_seen": last_seen,
        }
        for (
            aid, network, product, job_id, platform, topic, status, publish_url,
            views, clicks, revenue, last_seen
        ) in job_rows
    ]
    return {
        "ok": True,
        "days": days,
        "since": since,
        "affiliates": affiliates,
        "jobs": jobs,
        "next": {
            "list_url": "/api/operator/affiliates",
            "scale_url": "/api/operator/affiliate-scale",
            "performance_url": "/api/operator/performance",
        },
    }

@fastapi_app.get("/api/operator/tracking-report")
async def api_operator_tracking_report(request: Request, days: int = 30, limit: int = 15):
    verify_operator_api_token(request)
    days = max(1, min(int(days or 30), 180))
    limit = max(3, min(int(limit or 15), 50))
    report = tracking_report_data(ADMIN_ID, days=days, limit=limit)
    return {
        "ok": True,
        "days": days,
        "since": report["since"],
        "affiliates": report["affiliates"],
        "sources": report["sources"],
        "jobs": report["jobs"],
        "rule": "Scale sources/jobs with revenue or high conversion rate; fix CTA when views/clicks exist without conversions; pause when cost exceeds revenue.",
    }

@fastapi_app.get("/api/operator/scale-plan")
async def api_operator_scale_plan(request: Request, days: int = 30, limit: int = 10, platform: str = "tiktok"):
    verify_operator_api_token(request)
    days = max(1, min(int(days or 30), 180))
    limit = max(3, min(int(limit or 10), 50))
    platform = (platform or "tiktok").lower()
    plan = scale_plan_data(ADMIN_ID, days=days, limit=limit, platform=platform)
    return {
        "ok": True,
        "days": days,
        "since": plan["since"],
        "platform": platform,
        "summary": plan["summary"],
        "plans": plan["plans"],
        "rule": "Run SCALE commands for winners, fix CTA/offer before spending more, pause items where cost exceeds revenue.",
        "next": {
            "tracking_report_url": "/api/operator/tracking-report",
            "affiliate_scale_url": "/api/operator/affiliate-scale",
            "performance_url": "/api/operator/performance",
        },
    }

@fastapi_app.post("/api/operator/scale-plan/run")
async def api_operator_scale_plan_run(payload: OperatorScalePlanRunRequest, request: Request):
    verify_operator_api_token(request)
    platform = (payload.platform or "tiktok").lower()
    result = await execute_scale_plan_actions(
        ADMIN_ID,
        days=payload.days,
        platform=platform,
        limit=payload.limit,
        per_affiliate_limit=payload.per_affiliate_limit,
        build=payload.build,
        duration=payload.duration,
        notify_admin=payload.notify_admin,
    )
    return {
        "ok": True,
        "days": payload.days,
        "platform": platform,
        "executed": result["executed"],
        "skipped": result["skipped"],
        "summary": {
            "executed": len(result["executed"]),
            "skipped": len(result["skipped"]),
            "scale_candidates": result["plan"]["summary"]["scale"],
        },
        "next": {
            "tasks_url": "/api/operator/tasks/next",
            "loop_url": "/api/operator/loop",
            "publish_queue_url": "/api/operator/publish/next",
        },
    }

@fastapi_app.get("/api/operator/affiliate-decisions")
async def api_operator_affiliate_decisions(
    request: Request,
    days: int = 30,
    limit: int = 12,
    min_views: int = 200,
    platform: str = "tiktok",
):
    verify_operator_api_token(request)
    days = max(1, min(int(days or 30), 180))
    limit = max(3, min(int(limit or 12), 30))
    min_views = max(50, min(int(min_views or 200), 10000))
    platform = (platform or "tiktok").lower()
    since, decisions, job_rows = affiliate_decision_data(
        ADMIN_ID,
        days=days,
        limit=limit,
        min_views=min_views,
        platform=platform,
    )
    return {
        "ok": True,
        "days": days,
        "since": since,
        "platform": platform,
        "min_views": min_views,
        "decisions": decisions,
        "rule": "Use SCALE to create more videos, FIX_CTA/FIX_OFFER before spending more, PUBLISH when jobs exist but no publish event, TEST/TEST_MORE for low data.",
        "next": {
            "scale_url": "/api/operator/affiliate-scale",
            "performance_url": "/api/operator/performance",
            "affiliate_report_url": "/api/operator/affiliate-report",
        },
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
    queue_payload = serialize_publish_queue_item(item)
    return {
        "ok": True,
        "queue": queue_payload,
        "publisher_handoff": build_publisher_handoff(queue_payload),
        "submit_url": f"/api/operator/publish/{queue_id}/complete",
        "rule": "Return publish_url after posting. If blocked by platform/compliance, submit status=blocked and note.",
    }

@fastapi_app.get("/api/operator/publish/{queue_id}/handoff")
async def api_operator_publish_handoff(queue_id: int, request: Request):
    verify_operator_api_token(request)
    item = get_publish_queue_item(ADMIN_ID, queue_id)
    if not item:
        raise HTTPException(status_code=404, detail="Publish queue item not found")
    queue_payload = serialize_publish_queue_item(item)
    return {
        "ok": True,
        "queue": queue_payload,
        "publisher_handoff": build_publisher_handoff(queue_payload),
        "submit_url": f"/api/operator/publish/{queue_id}/complete",
        "rule": "Use official platform API or manual publishing. Never bypass platform rules, consent, or review gate.",
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
