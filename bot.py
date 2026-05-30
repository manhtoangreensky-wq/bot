"""
╔══════════════════════════════════════════════════════════════╗
║   TOAN DAAS V12.0 - ENTERPRISE SAAS BILLING ENGINE           ║
║   Hệ thống Kinh doanh AI Tự động hóa - Tích hợp Credit       ║
║   Giao diện thương mại bọc ngoài công nghệ lõi (White-Label) ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import logging
import asyncio
import edge_tts
import json
import time
import httpx
import urllib.parse
import sqlite3
from datetime import datetime
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ─── 1. CẤU HÌNH HỆ THỐNG BIẾN MÔI TRƯỜNG ─────────────────────────────────────
logging.basicConfig(format="%(asctime)s | %(name)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger("TOAN_DAAS")

TELEGRAM_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = str(os.environ.get("ADMIN_ID", "NHAP_ID_TELEGRAM_CUA_SEP")) # ID của sếp để toàn quyền điều phối

DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY")
REMOVEBG_API_KEY = os.environ.get("REMOVEBG_API_KEY")
FISH_AUDIO_KEY = os.environ.get("FISH_AUDIO_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
user_memory = {}       

# ─── 2. HỆ THỐNG CƠ SỞ DỮ LIỆU & TỰ ĐỘNG TRỪ XU (BILLING ENGINE) ──────────────
DB_FILE = "toandaas_billing.db"

# Bảng giá tiêu hao Xu hệ thống (Credit Cost)
COSTS = {
    'chat': 10,       # Trợ Lý Ảo TOAN DAAS
    'whisper': 50,    # Ghi Âm Siêu Tốc
    'download': 100,  # Máy Hút Media Sạch
    'image': 100,     # Studio Đồ Họa Tự Động (Tách nền)
    'voice': 200      # Nhân Bản Giọng Nói Tiếng Việt
}

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id TEXT PRIMARY KEY, username TEXT, credits INTEGER, is_vip INTEGER, join_date TEXT)''')
    conn.commit()
    conn.close()

def get_user(user_id, username="Unknown"):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT credits, is_vip FROM users WHERE user_id=?", (str(user_id),))
    row = c.fetchone()
    if not row:
        # THAY ĐỔI: Tặng gói mồi 200 Xu trải nghiệm cho tài khoản mới đăng ký lần đầu
        initial_credits = 200
        c.execute("INSERT INTO users (user_id, username, credits, is_vip, join_date) VALUES (?, ?, ?, ?, ?)", 
                  (str(user_id), username, initial_credits, 0, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        row = (initial_credits, 0)
    conn.close()
    return row[0], row[1]

def deduct_credit(user_id, action_type) -> bool:
    if str(user_id) == ADMIN_ID: return True # Chủ nhân hệ thống được miễn phí toàn bộ
    credits, is_vip = get_user(user_id)
    if is_vip == 1: return True # Tài khoản kích hoạt gói VIP vô hạn
    
    cost = COSTS.get(action_type, 10)
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

# ─── 3. TIỆN ÍCH THANH TOÁN TỰ ĐỘNG & QUẢN TRỊ ADMIN ─────────────────────────
async def cmd_naptien(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    username = update.effective_user.first_name
    credits, is_vip = get_user(user_id, username)
    
    msg = (
        f"💳 <b>NẠP SỐ DƯ CREDIT — HỆ THỐNG TOAN DAAS</b>\n\n"
        f"👤 Khách hàng: {username} (ID: <code>{user_id}</code>)\n"
        f"🪙 Số dư hiện tại: <b>{credits} Xu (Credit)</b>\n\n"
        f"<b>🛒 BẢNG GIÁ CÁC GÓI NẠP XU:</b>\n"
        f"• Gói Tiêu Chuẩn: 50.000đ ➔ <b>5.000 Xu</b>\n"
        f"• Gói Tiết Kiệm: 100.000đ ➔ <b>12.000 Xu</b>\n"
        f"• Gói Thương Mại: 200.000đ ➔ <b>25.000 Xu</b>\n"
        f"• Gói Doanh Nghiệp: 500.000đ ➔ <b>70.000 Xu</b>\n\n"
        f"<b>🏦 PHƯƠNG THỨC CHUYỂN KHOẢN TỰ ĐỘNG:</b>\n"
        f"- Ngân hàng: <b>ACB (Ngân hàng Á Châu)</b>\n"
        f"- Số tài khoản: <b>8899397968</b>\n"
        f"- Chủ tài khoản: <b>NGUYEN MANH TOAN</b>\n"
        f"- Nội dung chuyển khoản bắt buộc: <code>DAAS {user_id}</code>\n\n"
        f"<i>💡 Hướng dẫn: Sếp có thể quét mã QR đi kèm để tự động điền STK và nội dung. Sau khi chuyển khoản, hệ thống sẽ được phê duyệt cộng Xu ngay lập tức.</i>"
    )
    # Tự động cấu hình VietQR trỏ thẳng về tài khoản ACB của sếp kèm nội dung điền sẵn ID khách
    qr_url = f"https://img.vietqr.io/image/ACB-8899397968-compact.png?amount=&addInfo=DAAS+{user_id}&accountName=NGUYEN+MANH+TOAN"
    await update.message.reply_photo(photo=qr_url, caption=msg, parse_mode="HTML")

async def cmd_admin_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.effective_user.id) != ADMIN_ID: return
    try:
        target_id = context.args[0]
        amount = int(context.args[1])
        add_credit(target_id, amount)
        await update.message.reply_text(f"✅ Đã cộng {amount} Xu thành công cho khách hàng có ID: {target_id}")
        
        # Gửi thông báo tự động (Ting Ting) cho khách hàng biết
        await context.bot.send_message(
            chat_id=target_id, 
            text=f"🎉 <b>HỆ THỐNG ĐÃ CẬP NHẬT SỐ DƯ!</b>\nTài khoản của bạn đã được nạp thêm <b>{amount} Xu</b> từ Admin. Hãy tiếp tục trải nghiệm các dịch vụ tự động hóa từ TOAN DAAS!", 
            parse_mode="HTML"
        )
    except:
        await update.message.reply_text("⚠️ Cú pháp phê duyệt lỗi. Sếp gõ: /add <ID_Khách_Hàng> <Số_Xu_Cần_Cộng>")

async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    credits, is_vip = get_user(user_id, update.effective_user.first_name)
    account_status = "👑 THÀNH VIÊN VIP (Không giới hạn)" if is_vip else "💳 Gói Cước Trả Trước (Credit)"
    msg = (
        f"👤 <b>QUẢN LÝ TÀI KHOẢN KHÁCH HÀNG</b>\n\n"
        f"• Mã ID của bạn: <code>{user_id}</code>\n"
        f"• Trạng thái hệ thống: {account_status}\n"
        f"• Hạn mức khả dụng: <b>{credits} Xu (Credit)</b>\n\n"
        f"👉 Gõ lệnh /naptien để mua thêm hạn mức Xu bất cứ lúc nào."
    )
    await update.message.reply_text(msg, parse_mode="HTML")

# ─── 4. BỘ ĐIỀU PHỐI ĐẦU RA AI ────────────────────────────────────────────────
class AgentRouter(BaseModel):
    action: str = Field(description="Phân loại: 'voice', 'trend', 'code', 'content', 'image', 'video', 'download', 'general'")
    data: str = Field(description="Nội dung bóc tách yêu cầu sạch")

# ─── 5. CÁC PHÒNG BAN AI THỰC THI (WHITE-LABEL ENGINES) ────────────────────────
class AgentGemini:
    @staticmethod
    def chat(prompt_system: str, user_text: str, user_id: int, is_json: bool = False) -> str:
        if not gemini_client: return "❌ Kết nối máy chủ AI gián đoạn."
        if user_id not in user_memory: user_memory[user_id] = []
        user_memory[user_id].append(types.Content(role="user", parts=[types.Part(text=user_text)]))
        if len(user_memory[user_id]) > 10: user_memory[user_id] = user_memory[user_id][-10:]
        config_args = {"system_instruction": prompt_system}
        if is_json:
            config_args["response_mime_type"] = "application/json"
            config_args["response_schema"] = AgentRouter
        try:
            response = gemini_client.models.generate_content(model="gemini-2.0-flash", config=types.GenerateContentConfig(**config_args), contents=user_memory[user_id] if not is_json else user_text)
            if not is_json: user_memory[user_id].append(types.Content(role="model", parts=[types.Part(text=response.text)]))
            return response.text
        except Exception as e: return f"❌ Lỗi xử lý dữ liệu: {e}"

class AgentVoice:
    @staticmethod
    async def render(text: str, user_id: int, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        output_file = f"voice_pro_{user_id}.mp3"
        status_msg = await context.bot.send_message(chat_id=chat_id, text="⏳ <i>[Nhân Bản Giọng Nói Tiếng Việt] Đang tổng hợp âm thanh chất lượng cao...</i>", parse_mode="HTML")
        try:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post("https://api.fish.audio/v1/tts", headers={"Authorization": f"Bearer {FISH_AUDIO_KEY}", "Content-Type": "application/json"}, json={"text": text, "reference_id": "7f0955e88846433e9ecb241357608bf8", "format": "mp3"}, timeout=30.0)
                if response.status_code == 200:
                    with open(output_file, 'wb') as f: f.write(response.content)
                else: raise Exception("Cơ chế dự phòng")
            except:
                communicate = edge_tts.Communicate(text, "vi-VN-NamMinhNeural")
                await communicate.save(output_file)
                
            with open(output_file, 'rb') as audio_file: 
                await context.bot.send_audio(chat_id=chat_id, audio=audio_file, caption=f"🔊 Bản render âm thanh hoàn tất! (-{COSTS['voice']} Xu)")
            await status_msg.delete()
        except Exception as e: await status_msg.edit_text(f"❌ Phân hệ âm thanh báo lỗi: {e}")
        finally:
            if os.path.exists(output_file): os.remove(output_file)

class AgentWhisper:
    @staticmethod
    async def transcribe(file_bytes: bytes) -> str:
        try:
            async with httpx.AsyncClient() as client:
                files = {'file': ('voice.ogg', file_bytes, 'audio/ogg')}
                data = {'model': 'whisper-1', 'language': 'vi'}
                response = await client.post("https://api.openai.com/v1/audio/transcriptions", headers={"Authorization": f"Bearer {OPENAI_API_KEY}"}, files=files, data=data, timeout=60.0)
                if response.status_code == 200: return response.json().get("text", "")
                return "❌ Phân hệ Ghi Âm lỗi kết nối."
        except: return "❌ Cổng truyền dữ liệu âm thanh gián đoạn."

class AgentRemoveBg:
    @staticmethod
    async def remove(image_bytes: bytes, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        status_msg = await context.bot.send_message(chat_id=chat_id, text="⏳ <i>[Studio Đồ Họa Tự Động] Đang bóc tách phông nền sản phẩm...</i>", parse_mode="HTML")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post("https://api.remove.bg/v1.0/removebg", headers={"X-Api-Key": REMOVEBG_API_KEY}, files={"image_file": image_bytes}, data={"size": "auto"}, timeout=30.0)
            if response.status_code == 200:
                await context.bot.send_document(chat_id=chat_id, document=response.content, filename="no_bg.png", caption=f"✂️ Đã tách nền xuyên thấu hoàn tất! (-{COSTS['image']} Xu)")
                await status_msg.delete()
            else: await status_msg.edit_text("❌ Xóa nền không thành công từ máy chủ.")
        except Exception as e: await status_msg.edit_text(f"❌ Lỗi đồ họa: {e}")

class AgentDownloader:
    @staticmethod
    async def download(url: str, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        status_msg = await context.bot.send_message(chat_id=chat_id, text="⏳ <i>[Máy Hút Media Sạch] Đang bóc tách video gốc không dính logo...</i>", parse_mode="HTML")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post("https://api.cobalt.tools/api/json", headers={"Accept": "application/json", "Content-Type": "application/json"}, json={"url": url, "videoQuality": "1080"}, timeout=30.0)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") in ["stream", "redirect", "success"]:
                    await context.bot.send_video(chat_id=chat_id, video=data.get("url"), caption=f"🎬 Đã làm sạch video gốc, sẵn sàng biên tập! (-{COSTS['download']} Xu)", parse_mode="HTML")
                    await status_msg.delete()
                else: await status_msg.edit_text("❌ Đường link này không được hệ thống hỗ trợ.")
            else: await status_msg.edit_text("❌ Máy chủ hút dữ liệu từ chối phản hồi.")
        except: await status_msg.edit_text("❌ Lỗi kết nối luồng tải video.")

# ─── 6. BỘ NÃO TRUNG TÂM KIỂM SOÁT LUỒNG DỮ LIỆU & TRỪ XU TỰ ĐỘNG ──────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    if text == "🛸 MENU DỊCH VỤ TOAN DAAS":
        await cmd_start(update, context)
        return
        
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    # Định tuyến thông minh bằng trợ lý AI trung tâm
    routing_instruction = "Phân loại hành động: 'voice', 'trend', 'code', 'content', 'image', 'video', 'download', 'general'. Nếu user gửi link URL -> đổi thành 'download'."
    router_json = AgentGemini.chat(routing_instruction, text, user_id, is_json=True)
    
    try:
        route_plan = json.loads(router_json)
        action = route_plan.get("action", "general")
        data = route_plan.get("data", text)
        
        # HỆ THỐNG TRỪ XU TỰ ĐỘNG (BILLING ENGINE)
        cost_type = 'chat'
        if action == 'voice': cost_type = 'voice'
        elif action == 'download': cost_type = 'download'
        
        if not deduct_credit(user_id, cost_type):
            await update.message.reply_text(f"❌ <b>HẠN MỨC XU KHÔNG ĐỦ!</b>\nTính năng này yêu cầu <b>{COSTS[cost_type]} Xu</b>.\nVui lòng gõ /naptien để mua thêm hạn mức sử dụng.", parse_mode="HTML")
            return
            
        # Kích hoạt các đầu mục thực thi công việc
        if action == "voice": 
            await AgentVoice.render(data, user_id, context, update.effective_chat.id)
        elif action == "download": 
            await AgentDownloader.download(data, context, update.effective_chat.id)
        else:
            bot_reply = AgentGemini.chat("Bạn là Trợ Lý Ảo TOAN DAAS. Trả lời bằng tiếng Việt chuyên nghiệp, súc tích và có giá trị chuyên môn cao.", text, user_id)
            await send_long_text(update, f"🤖 <b>Trợ Lý Ảo TOAN DAAS phản hồi:</b>\n\n{bot_reply}\n\n<i>(-{COSTS['chat']} Xu)</i>")
            
    except Exception as err:
        logger.error(f"Routing Error: {err}")

async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not deduct_credit(user_id, 'image'):
        await update.message.reply_text(f"❌ <b>HẠN MỨC XU KHÔNG ĐỦ!</b>\nSử dụng Studio Đồ Họa Tự Động yêu cầu <b>{COSTS['image']} Xu</b>/lần. Vui lòng gõ lệnh /naptien.")
        return
        
    photo_file = await update.message.photo[-1].get_file()
    photo_bytes = await photo_file.download_as_bytearray()
    context.user_data["last_photo_bytes"] = bytes(photo_bytes)
    
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✂️ Tách Nền Xuyên Thấu", callback_data="removebg_photo")]])
    await update.message.reply_text("📥 <b>Hệ thống đã nhận tập tin Hình ảnh sản phẩm!</b>\nBấm nút bên dưới để phân xưởng đồ họa bắt đầu bóc tách nền.", parse_mode="HTML", reply_markup=keyboard)

async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not deduct_credit(user_id, 'whisper'):
        await update.message.reply_text(f"❌ <b>HẠN MỨC XU KHÔNG ĐỦ!</b>\nSử dụng Máy Ghi Âm Siêu Tốc yêu cầu <b>{COSTS['whisper']} Xu</b>/lần. Vui lòng gõ lệnh /naptien.")
        return
        
    voice = update.message.voice or update.message.audio
    status_msg = await update.message.reply_text("⚡ <i>[Ghi Âm Siêu Tốc] Đang bóc băng ghi âm giọng nói...</i>", parse_mode="HTML")
    voice_file = await voice.get_file()
    voice_bytes = await voice_file.download_as_bytearray()
    
    transcribed_text = await AgentWhisper.transcribe(bytes(voice_bytes))
    await status_msg.delete()
    
    if transcribed_text and not transcribed_text.startswith("❌"):
        await update.message.reply_text(f"🗣️ <b>Văn bản hóa giọng đọc hoàn tất:</b>\n<i>\"{transcribed_text}\"</i>\n\n<i>(-{COSTS['whisper']} Xu)</i>", parse_mode="HTML")
        # Đẩy thẳng văn bản đã bóc băng vào bộ định tuyến trung tâm để tự động ra lệnh chat tiếp tục
        update.message.text = transcribed_text
        await handle_message(update, context)

# ─── 7. LỆNH ĐIỀU HÀNH START ──────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    username = update.effective_user.first_name
    get_user(user_id, username) 
    
    text = (
        "👑 <b>CHÀO MỪNG ĐẾN VỚI HỆ SINH THÁI AI — TOAN DAAS V12.0</b>\n\n"
        "Hệ thống Multi-Agent tự động hóa toàn diện các tác vụ kinh doanh chuyên nghiệp. Toàn bộ tính năng vận hành thông qua hạn mức <b>Xu (Credit)</b>.\n\n"
        "🎁 <b>Quà tặng tân thủ:</b> Bạn đã được cộng sẵn <b>200 Xu Trải Nghiệm Miễn Phí</b> vào tài khoản.\n\n"
        "✨ <b>Các phân hệ dịch vụ cao cấp có thể sử dụng:</b>\n"
        "1. <b>Trợ Lý Ảo TOAN DAAS:</b> Chat trực tiếp để yêu cầu viết kịch bản viral, viết code hệ thống, lập chiến lược MMO.\n"
        "2. <b>Ghi Âm Siêu Tốc:</b> Gửi tin nhắn thoại để tự động bóc băng thành văn bản và ra lệnh cho Bot.\n"
        "3. <b>Máy Hút Media Sạch:</b> Thả link video (TikTok/FB/YouTube) để tự động tải file gốc sạch 100% logo.\n"
        "4. <b>Studio Đồ Họa Tự Động:</b> Gửi ảnh sản phẩm để bóc tách nền trong suốt làm tư liệu marketing.\n"
        "5. <b>Nhân Bản Giọng Nói Tiếng Việt:</b> Chuyển đổi văn bản thành giọng đọc voice-off cao cấp.\n\n"
        "👉 Kiểm tra ví Xu: /profile · Nạp thêm xu tự động: /naptien"
    )
    markup = ReplyKeyboardMarkup([[KeyboardButton("🛸 MENU DỊCH VỤ TOAN DAAS")]], resize_keyboard=True)
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=markup)

async def send_long_text(update: Update, text: str):
    for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
        try: await update.message.reply_text(chunk, parse_mode="HTML")
        except: await update.message.reply_text(chunk)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() 
    if query.data == "removebg_photo" and context.user_data.get("last_photo_bytes"):
        await AgentRemoveBg.remove(context.user_data.get("last_photo_bytes"), context, query.message.chat_id)

def main() -> None:
    init_db() # Khởi tạo hoặc kết nối cơ sở dữ liệu SQLite tính tiền tự động
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("naptien", cmd_naptien))
    app.add_handler(CommandHandler("add", cmd_admin_add)) # Lệnh dành riêng cho sếp Toàn để duyệt tiền
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 LÕI BILLING SAAS TOAN DAAS V12.0 ĐÃ TRỰC TUYẾN...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()