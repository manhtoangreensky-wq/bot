"""
╔══════════════════════════════════════════════════════════════════╗
║   TOAN DAAS V15.1 - PRODUCTION READY                            ║
║   FastAPI + Telegram Bot (Shared Event Loop via Lifespan)        ║
║   Dynamic Billing | Deepgram | Auto-Tiers | PayOS Auto Xu       ║
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
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
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

# ─── AI CLIENTS ───────────────────────────────────────────────────────────────
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
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
    c.execute("""CREATE TABLE IF NOT EXISTS payos_processed (
        order_code TEXT PRIMARY KEY,
        processed_at DATETIME
    )""")
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
    return row[0], row[1], row[2]

def add_credit(user_id, amount):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET credits = credits + ? WHERE user_id=?", (amount, str(user_id)))
    conn.commit()
    conn.close()

def is_payos_order_processed(order_code: str) -> bool:
    """Kiểm tra order đã xử lý chưa (chống duplicate)"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT 1 FROM payos_processed WHERE order_code=?", (str(order_code),))
    exists = c.fetchone() is not None
    conn.close()
    return exists

def mark_payos_order_processed(order_code: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO payos_processed (order_code, processed_at) VALUES (?,?)",
        (str(order_code), datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
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
        if not gemini_client and not openai_client:
            return "❌ Chưa cấu hình AI Provider."

        # --- Thử Gemini trước ---
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

        # --- Fallback OpenAI ---
        if openai_client:
            try:
                messages = [{"role": "system", "content": prompt}]
                if uid in user_memory:
                    for m in user_memory[uid][-6:]:
                        role = "user" if m.role == "user" else "assistant"
                        messages.append({"role": role, "content": m.parts[0].text})
                else:
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
        """
        Thứ tự ưu tiên FREE → TRẢ PHÍ:
        1. Edge TTS (hoàn toàn miễn phí) — thử trước, hoàn xu nếu thành công
        2. Fish Audio (có phí quota) — chỉ dùng khi Edge TTS lỗi, giữ xu
        Trả về True = đã dùng Fish Audio (tính phí), False = Edge TTS (hoàn xu)
        """
        out = f"v_{user_id}.mp3"
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text="⏳ <i>[Giọng Nói] Đang tổng hợp...</i>",
            parse_mode="HTML"
        )
        used_fish = False
        try:
            # Bước 1: Thử Edge TTS FREE trước
            edge_ok = False
            try:
                communicate = edge_tts.Communicate(text, "vi-VN-NamMinhNeural")
                await communicate.save(out)
                if os.path.exists(out) and os.path.getsize(out) > 0:
                    edge_ok = True
            except Exception as e:
                logger.warning(f"Edge TTS lỗi: {e} — thử Fish Audio...")

            if edge_ok:
                # Edge TTS thành công → miễn phí, hoàn xu
                with open(out, "rb") as f:
                    await context.bot.send_audio(
                        chat_id=chat_id, audio=f,
                        caption=f"🔊 Gói Tiết Kiệm — Tổng hợp giọng nói thành công! (-{VOICE_FREE_COST} Xu)"
                    )
                await msg.delete()
                return False  # hoàn xu ở caller

            # Bước 2: Edge TTS lỗi → fallback Fish Audio (tính phí)
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
# Lưu pending action khi khách đang chọn provider
# key=user_id, value={type, data, cost, file_bytes, chat_id, msg_id}
USER_PENDING: dict = {}

VOICE_FREE_COST  = 5   # xu cho gói tiết kiệm giọng nói
IMAGE_FREE_COST  = 5   # xu cho gói tiết kiệm tách nền

def provider_keyboard(service: str, uid: int, cost: int) -> InlineKeyboardMarkup:
    """
    Tạo inline keyboard cho khách chọn provider.
    service: 'voice' | 'image'
    """
    if service == "voice":
        buttons = [
            [
                InlineKeyboardButton(
                    f"🔊 Gói Tiết Kiệm — -{VOICE_FREE_COST} Xu",
                    callback_data=f"prov|voice|free|{uid}"
                )
            ],
            [
                InlineKeyboardButton(
                    f"🎙️ Gói Cao Cấp — -{cost} Xu",
                    callback_data=f"prov|voice|paid|{uid}"
                )
            ],
        ]
    else:  # image
        buttons = [
            [
                InlineKeyboardButton(
                    f"✂️ Gói Tiết Kiệm — -{IMAGE_FREE_COST} Xu",
                    callback_data=f"prov|image|free|{uid}"
                )
            ],
            [
                InlineKeyboardButton(
                    f"🖼️ Gói Cao Cấp — -{cost} Xu",
                    callback_data=f"prov|image|paid|{uid}"
                )
            ],
        ]
    buttons.append([InlineKeyboardButton("❌ Huỷ", callback_data=f"prov|cancel|cancel|{uid}")])
    return InlineKeyboardMarkup(buttons)


async def handle_provider_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi khách bấm chọn provider từ inline keyboard."""
    query = update.callback_query
    await query.answer()
    parts = query.data.split("|")
    if len(parts) != 4:
        return
    _, service, mode, uid_str = parts
    uid = int(uid_str)

    # Bảo vệ: chỉ chính user đó mới được bấm
    if query.from_user.id != uid:
        await query.answer("⚠️ Không phải yêu cầu của bạn!", show_alert=True)
        return

    pending = USER_PENDING.pop(uid, None)
    if not pending:
        await query.edit_message_text("⏰ Yêu cầu đã hết hạn hoặc đã xử lý.")
        return

    if mode == "cancel":
        # Hoàn xu nếu đã trừ
        if pending.get("cost", 0) > 0:
            add_credit(uid, pending["cost"])
        await query.edit_message_text("❌ Đã huỷ. Xu được hoàn lại.")
        return

    chat_id  = pending["chat_id"]
    cost     = pending["cost"]
    svc_type = pending["type"]

    # ── VOICE ──
    if svc_type == "voice":
        data = pending["data"]
        if mode == "free":
            # Gói tiết kiệm — hoàn xu đã tạm trừ, sau đó trừ 5 xu
            if cost > 0 and str(uid) != ADMIN_ID:
                add_credit(uid, cost)  # hoàn lại khoản tạm trừ
            # Trừ 5 xu cho gói tiết kiệm
            can_afford_free = True
            if str(uid) != ADMIN_ID:
                credits_now, _, _ = get_user(uid)
                if credits_now >= VOICE_FREE_COST:
                    conn = __import__('sqlite3').connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("UPDATE users SET credits = credits - ? WHERE user_id=?", (VOICE_FREE_COST, str(uid)))
                    conn.commit()
                    conn.close()
                else:
                    can_afford_free = False
            if not can_afford_free:
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
                await query.edit_message_text("❌ Gói Tiết Kiệm gặp lỗi.")
            finally:
                if os.path.exists(out):
                    os.remove(out)
        else:
            # Fish Audio — giữ xu, nếu lỗi hoàn xu + fallback
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
                    # Fallback gói tiết kiệm — hoàn xu cao cấp, trừ 5 xu tiết kiệm
                    if cost > 0 and str(uid) != ADMIN_ID:
                        add_credit(uid, cost)  # hoàn xu gói cao cấp
                    if str(uid) != ADMIN_ID:
                        conn = __import__('sqlite3').connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("UPDATE users SET credits = credits - ? WHERE user_id=?", (VOICE_FREE_COST, str(uid)))
                        conn.commit()
                        conn.close()
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

    # ── IMAGE ──
    elif svc_type == "image":
        img_bytes = pending["file_bytes"]
        if mode == "free":
            # Gói tiết kiệm — hoàn xu tạm trừ, sau đó trừ 5 xu
            if cost > 0 and str(uid) != ADMIN_ID:
                add_credit(uid, cost)  # hoàn lại khoản tạm trừ
            # Trừ 5 xu cho gói tiết kiệm
            can_afford_free = True
            if str(uid) != ADMIN_ID:
                credits_now, _, _ = get_user(uid)
                if credits_now >= IMAGE_FREE_COST:
                    conn = __import__('sqlite3').connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("UPDATE users SET credits = credits - ? WHERE user_id=?", (IMAGE_FREE_COST, str(uid)))
                    conn.commit()
                    conn.close()
                else:
                    can_afford_free = False
            if not can_afford_free:
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
                await query.edit_message_text("❌ Cutout.pro lỗi hoặc chưa cấu hình CUTOUT_API_KEY.")
        else:
            # RemoveBG — giữ xu, nếu lỗi tự chuyển Cutout
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
                # Fallback gói tiết kiệm — hoàn xu cao cấp, trừ 5 xu tiết kiệm
                if cost > 0 and str(uid) != ADMIN_ID:
                    add_credit(uid, cost)  # hoàn xu gói cao cấp
                if str(uid) != ADMIN_ID:
                    conn = __import__('sqlite3').connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("UPDATE users SET credits = credits - ? WHERE user_id=?", (IMAGE_FREE_COST, str(uid)))
                    conn.commit()
                    conn.close()
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
                    await query.edit_message_text("❌ Cả 2 dịch vụ đều lỗi. Xu đã hoàn lại.")


# ─── HANDLERS ────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    get_user(update.effective_user.id, update.effective_user.first_name)
    text = (
        "👑 <b>HỆ SINH THÁI AI — TOAN DAAS V15.1</b>\n\n"
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
        f"<b>⚡ NẠP TỰ ĐỘNG:</b>\n"
        f"Hệ thống tự xác nhận qua PayOS trong vài giây!\n\n"
        f"<b>📋 QUY TRÌNH:</b>\n"
        f"1️⃣ Chuyển khoản với nội dung <code>DAAS {uid}</code>\n"
        f"2️⃣ Xu tự động vào tài khoản trong 5-10 giây ⚡\n"
        f"3️⃣ Bot sẽ gửi thông báo xác nhận\n\n"
        f"⚠️ <i>Không ghi sai nội dung — hệ thống sẽ không nhận diện được.</i>"
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
    c.execute("SELECT COUNT(*) FROM payos_processed")
    payos_auto = c.fetchone()[0]
    conn.close()
    await update.message.reply_text(
        f"📊 <b>THỐNG KÊ HỆ THỐNG</b>\n\n"
        f"👥 Tổng user: <b>{total_users}</b>\n"
        f"⚡ Giao dịch hôm nay: <b>{tx_today}</b>\n"
        f"💰 Xu tiêu hôm nay: <b>{revenue_today}</b>\n"
        f"📋 Bill chờ duyệt (thủ công): <b>{pending}</b>\n"
        f"🤖 Nạp tự động PayOS: <b>{payos_auto}</b>",
        parse_mode="HTML"
    )

async def cmd_setvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return
    try:
        target_id = context.args[0]
        flag = int(context.args[1])
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

    # -- Tach nen: cho khach chon provider --
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
    await update.message.reply_text(
        f"🖼️ <b>Chọn gói tách nền:</b>\n\n"
        f"✂️ <b>Gói Tiết Kiệm</b> — Tách nền nhanh, trừ <b>{IMAGE_FREE_COST} Xu</b>\n"
        f"🖼️ <b>Gói Cao Cấp</b> — Chất lượng HD, trừ <b>{final_cost} Xu</b>\n\n"
        f"<i>Nếu gói cao cấp gặp sự cố → tự chuyển gói tiết kiệm và hoàn phần dư.</i>",
        parse_mode="HTML", reply_markup=kb
    )

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

    can_afford, cost, discount = deduct_dynamic_credit(uid, action_key, size_calc)
    if not can_afford:
        return await update.message.reply_text(
            f"❌ <b>HẾT HẠN MỨC!</b> Yêu cầu {cost} Xu.\nGõ /naptien để nạp thêm.",
            parse_mode="HTML"
        )

    if act == "voice":
        # Hoi khach chon provider truoc khi xu ly
        # Tinh cost cho Fish Audio (co phi); neu chon Edge TTS mien phi thi khong tru xu
        raw_cost_v = calculate_dynamic_cost("voice", size_calc)
        _, ts_v, _ = get_user(uid)
        fish_cost, _ = apply_discount(ts_v, raw_cost_v)
        # Hoan xu da tru (vi deduct_dynamic_credit da tru cho 'voice')
        if cost > 0 and str(uid) != ADMIN_ID:
            add_credit(uid, cost)  # hoan tam, se tru lai neu chon paid
        USER_PENDING[uid] = {
            "type": "voice",
            "data": data,
            "cost": fish_cost,
            "chat_id": update.effective_chat.id,
            "file_bytes": None,
        }
        kb = provider_keyboard("voice", uid, fish_cost)
        await update.message.reply_text(
            f"🎙️ <b>Chọn gói đọc giọng nói:</b>\n\n"
            f"🔊 <b>Gói Tiết Kiệm</b> — Giọng chuẩn, trừ <b>{VOICE_FREE_COST} Xu</b>\n"
            f"🎙️ <b>Gói Cao Cấp</b> — Giọng nhân bản siêu thực, trừ <b>{fish_cost} Xu</b>\n\n"
            f"<i>Nếu gói cao cấp gặp sự cố → tự chuyển gói tiết kiệm và hoàn phần dư.</i>",
            parse_mode="HTML", reply_markup=kb
        )
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
    tg_app.add_handler(CallbackQueryHandler(handle_provider_choice, pattern=r"^prov\|"))

    await tg_app.initialize()
    await tg_app.start()
    asyncio.create_task(tg_app.updater.start_polling(allowed_updates=Update.ALL_TYPES))
    logger.info("🚀 TOAN DAAS V15.1 ONLINE — Bot + API đang chạy.")
    yield
    await tg_app.updater.stop()
    await tg_app.stop()
    await tg_app.shutdown()
    logger.info("🛑 Bot đã dừng an toàn.")

fastapi_app = FastAPI(title="TOAN DAAS V15.1", lifespan=lifespan)

# ─── HEALTH CHECK ─────────────────────────────────────────────────────────────
@fastapi_app.get("/")
async def health():
    return {"status": "ok", "service": "TOAN DAAS V15.1"}

# ─── WEBHOOK PAYOS ────────────────────────────────────────────────────────────
def verify_payos_signature(data: dict, received_sig: str) -> bool:
    """Xác thực chữ ký HMAC-SHA256 từ payOS"""
    if not PAYOS_CHECKSUM_KEY:
        return False
    # PayOS yêu cầu sort key theo alphabet, ghép thành key=value&key=value
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
    PayOS gọi endpoint này sau mỗi giao dịch thành công.
    Khách chuyển khoản nội dung: DAAS <user_id>
    Bot tự cộng Xu và thông báo cho khách.
    """
    try:
        body = await request.json()
        logger.info(f"PayOS webhook received: {body}")
    except Exception:
        logger.warning("PayOS webhook: body không phải JSON hợp lệ")
        return JSONResponse({"code": "00", "desc": "ok"})

    sig  = body.get("signature", "")
    data = body.get("data", {})

    # Xác thực chữ ký — chỉ bật khi đã cấu hình PAYOS_CHECKSUM_KEY
    if PAYOS_CHECKSUM_KEY:
        if not sig:
            logger.warning("PayOS webhook: không có signature, bỏ qua xác thực.")
        elif not verify_payos_signature(data, sig):
            logger.warning("PayOS webhook: chữ ký không hợp lệ!")
            return JSONResponse({"code": "01", "desc": "invalid_signature"}, status_code=200)

    # Chỉ xử lý khi giao dịch thành công
    if not (body.get("success") or data.get("status") == "PAID"):
        return JSONResponse({"code": "00", "desc": "ignored"})

    order_code = str(data.get("orderCode", data.get("order_code", "")))
    desc = data.get("description", data.get("addInfo", "")).upper()
    amount_vnd = int(data.get("amount", 0))

    # Chống xử lý trùng
    if order_code and is_payos_order_processed(order_code):
        logger.info(f"PayOS: order {order_code} đã xử lý, bỏ qua.")
        return JSONResponse({"code": "00", "desc": "duplicate"})

    # Tìm pattern "DAAS <user_id>" trong nội dung chuyển khoản
    target_id = None
    parts = desc.split()
    for i, p in enumerate(parts):
        if p == "DAAS" and i + 1 < len(parts) and parts[i + 1].isdigit():
            target_id = parts[i + 1]
            break

    if not target_id:
        logger.warning(f"PayOS webhook: không tìm thấy DAAS <user_id> trong nội dung: {desc}")
        return JSONResponse({"code": "00", "desc": "no_target"})

    # Tính xu — bảng quy đổi có thưởng
    if amount_vnd >= 500000:
        xu = 6000
    elif amount_vnd >= 100000:
        xu = 1050
    elif amount_vnd >= 50000:
        xu = 500
    else:
        xu = math.floor(amount_vnd / 100)  # fallback: 100đ = 1 Xu

    if xu <= 0:
        return JSONResponse({"code": "00", "desc": "amount_too_low"})

    add_credit(target_id, xu)
    if order_code:
        mark_payos_order_processed(order_code)

    credits_now, _, _ = get_user(target_id)
    logger.info(f"✅ PayOS auto nạp {xu} Xu cho {target_id} | {amount_vnd:,}đ | order: {order_code}")

    # Thông báo cho khách qua Telegram
    if tg_app:
        try:
            await tg_app.bot.send_message(
                chat_id=target_id,
                text=(
                    f"🎉 <b>NẠP TỰ ĐỘNG THÀNH CÔNG!</b>\n\n"
                    f"✅ PayOS xác nhận thanh toán!\n"
                    f"💰 Số tiền: <b>{amount_vnd:,}đ</b>\n"
                    f"🪙 Cộng: <b>+{xu} Xu</b>\n"
                    f"💼 Số dư hiện tại: <b>{credits_now} Xu</b>\n\n"
                    f"Cảm ơn bạn đã tin dùng TOAN DAAS! 🙏"
                ),
                parse_mode="HTML"
            )
            # Thông báo admin
            await tg_app.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"💸 <b>AUTO NẠP PAYOS</b>\n\n"
                    f"🆔 User: <code>{target_id}</code>\n"
                    f"💰 {amount_vnd:,}đ → +{xu} Xu\n"
                    f"📋 Order: {order_code}"
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