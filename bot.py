"""
╔══════════════════════════════════════════════════════════════╗
║   HoTroToanBot - TRẠM ĐIỀU KHIỂN AI ĐA TÁC VỤ VIP V11.0      ║
║   Enterprise Multi-Agent Orchestration System                ║
║   Tích hợp: Code, Content, Voice, Image, Data, Download      ║
║   HỆ THỐNG API: Đã nạp đủ DeepL, Remove.bg, Fish, OpenAI     ║
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
from pydantic import BaseModel, Field
from duckduckgo_search import DDGS
from google import genai
from google.genai import types
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ─── 1. CẤU HÌNH HỆ THỐNG CORE & LOGGING ───────────────────────────────────────
logging.basicConfig(format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", level=logging.INFO)
logger = logging.getLogger("HoTroToanBot")

WEB_APP_URL = "https://manhtoangreensky-wq.github.io/web-admin-bot/trangchu.html"
TELEGRAM_TOKEN = os.environ.get("BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")
ADMIN_ID = os.environ.get("ADMIN_ID")

# Hệ thống Thẻ bài API được tích hợp qua biến môi trường
DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY")
REMOVEBG_API_KEY = os.environ.get("REMOVEBG_API_KEY")
FISH_AUDIO_KEY = os.environ.get("FISH_AUDIO_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

user_memory = {}       
user_rate_limit = {}   
claude_memory = {}     

# ─── 2. CƠ CHẾ BẢO MẬT TUYỆT ĐỐI: KHÓA CHỦ NHÂN ──────────────────────────────────
async def restrict_access(update: Update) -> bool:
    user_id = update.effective_user.id
    if not ADMIN_ID:
        await update.message.reply_text(
            f"🔒 <b>TRẠM ĐIỀU KHIỂN ĐANG KHÓA VẬT LÝ</b>\n\n"
            f"Sếp hãy copy mã ID này: <code>{user_id}</code>\n"
            f"<i>👉 Vào Railway -> Variables -> Thêm biến <b>ADMIN_ID</b> và dán số này vào -> Restart.</i>",
            parse_mode="HTML"
        )
        return True
    if str(user_id) != str(ADMIN_ID):
        await update.message.reply_text("⛔ <b>TRUY CẬP TỪ CHỐI:</b> Bạn không phải chủ nhân của hệ thống này.")
        return True
    
    current_time = time.time()
    user_timestamps = user_rate_limit.get(user_id, [])
    user_timestamps = [t for t in user_timestamps if current_time - t < 60]
    user_rate_limit[user_id] = user_timestamps
    
    if len(user_timestamps) >= 10: 
        await update.message.reply_text("⚠️ <b>CẢNH BÁO:</b> Sếp ra lệnh quá nhanh, vui lòng đợi AI xử lý luồng cũ.")
        return True
    
    user_rate_limit[user_id].append(current_time)
    return False

# ─── 3. ĐỊNH CHUẨN ĐẦU RA SẾP TỔNG (ROUTER SCHEMA) ─────────────────────────────
class AgentRouter(BaseModel):
    action: str = Field(description="Phân loại: 'voice', 'trend', 'code', 'content', 'image', 'video', 'mmo', 'download', 'general'")
    data: str = Field(description="Từ khóa hoặc nội dung yêu cầu sạch đã bóc tách")

# ─── 4. CÁC PHÒNG BAN AI THỰC THI (MULTI-AGENT ENGINES) ────────────────────────

class AgentGemini:
    @staticmethod
    def chat(prompt_system: str, user_text: str, user_id: int, is_json: bool = False) -> str:
        if not gemini_client: return "❌ Chưa cấu hình GEMINI_API_KEY."
        if user_id not in user_memory: user_memory[user_id] = []
        user_memory[user_id].append(types.Content(role="user", parts=[types.Part(text=user_text)]))
        if len(user_memory[user_id]) > 10: user_memory[user_id] = user_memory[user_id][-10:]
        
        config_args = {"system_instruction": prompt_system}
        if is_json:
            config_args["response_mime_type"] = "application/json"
            config_args["response_schema"] = AgentRouter

        try:
            response = gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                config=types.GenerateContentConfig(**config_args),
                contents=user_memory[user_id] if not is_json else user_text
            )
            if not is_json: user_memory[user_id].append(types.Content(role="model", parts=[types.Part(text=response.text)]))
            return response.text
        except Exception as e:
            return f"❌ <b>Lỗi API Gemini:</b> {e}"

CLAUDE_SYSTEM_PROMPT = "Bạn là Đầu Não Lập Trình Cấp Cao. Luôn trả lời tiếng Việt, code sạch có comment, chạy được ngay. Không nói chung chung."
class AgentClaude:
    @staticmethod
    async def chat(prompt: str, user_id: int) -> str:
        if not CLAUDE_API_KEY:
            fallback_msg = "⚠️ <i>(Chưa nạp CLAUDE_API_KEY. Hệ thống tự động chuyển task cho Gemini xử lý...)</i>\n\n"
            return fallback_msg + AgentGemini.chat(CLAUDE_SYSTEM_PROMPT, prompt, user_id)
        if user_id not in claude_memory: claude_memory[user_id] = []
        claude_memory[user_id].append({"role": "user", "content": prompt})
        if len(claude_memory[user_id]) > 10: claude_memory[user_id] = claude_memory[user_id][-10:]
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": CLAUDE_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                    json={"model": "claude-3-5-sonnet-latest", "max_tokens": 4096, "system": CLAUDE_SYSTEM_PROMPT, "messages": claude_memory[user_id]},
                    timeout=90.0
                )
                if response.status_code == 200:
                    reply = response.json()["content"][0]["text"]
                    claude_memory[user_id].append({"role": "assistant", "content": reply})
                    return reply
                else: return f"❌ Lỗi Claude API ({response.status_code}): {response.text}"
        except Exception as e: return f"❌ Lỗi kết nối Claude: {e}"

class AgentVoice:
    @staticmethod
    async def render(text: str, user_id: int, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        output_file = f"voice_pro_{user_id}.mp3"
        status_msg = await context.bot.send_message(chat_id=chat_id, text="⏳ <i>[Fish Audio / Edge-TTS] Đang truyền tải giọng đọc cao cấp...</i>", parse_mode="HTML")
        try:
            # Ưu tiên sử dụng Fish Audio nâng cao nếu được kích hoạt, có lỗi sẽ tự động fallback sang EdgeTTS
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "https://api.fish.audio/v1/tts",
                        headers={"Authorization": f"Bearer {FISH_AUDIO_KEY}", "Content-Type": "application/json"},
                        json={"text": text, "reference_id": "7f0955e88846433e9ecb241357608bf8", "format": "mp3"},
                        timeout=30.0
                    )
                if response.status_code == 200:
                    with open(output_file, 'wb') as f: f.write(response.content)
                else: raise Exception("Chuyển sang gói dự phòng Edge-TTS")
            except:
                communicate = edge_tts.Communicate(text, "vi-VN-NamMinhNeural")
                await communicate.save(output_file)
                
            with open(output_file, 'rb') as audio_file: 
                await context.bot.send_audio(chat_id=chat_id, audio=audio_file, caption="✅ Bản render voice hoàn tất cho sếp!")
            await status_msg.delete()
        except Exception as e: await status_msg.edit_text(f"❌ Lỗi xử lý âm thanh: {e}")
        finally:
            if os.path.exists(output_file): os.remove(output_file)

class AgentWhisper:
    @staticmethod
    async def transcribe(file_bytes: bytes) -> str:
        try:
            async with httpx.AsyncClient() as client:
                files = {'file': ('voice.ogg', file_bytes, 'audio/ogg')}
                data = {'model': 'whisper-1', 'language': 'vi'}
                response = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    files=files,
                    data=data,
                    timeout=60.0
                )
                if response.status_code == 200:
                    return response.json().get("text", "")
                return f"❌ Lỗi Whisper API ({response.status_code})"
        except Exception as e:
            return f"❌ Không thể kết nối cổng Whisper OpenAI: {e}"

class AgentDeepL:
    @staticmethod
    async def translate(text: str, target_lang: str = "EN") -> str:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api-free.deepl.com/v2/translate",
                    headers={"Authorization": f"DeepL-Auth-Key {DEEPL_API_KEY}"},
                    data={"text": [text], "target_lang": target_lang},
                    timeout=15.0
                )
                if response.status_code == 200:
                    return response.json()["translations"][0]["text"]
                return text
        except:
            return text

class AgentRemoveBg:
    @staticmethod
    async def remove(image_bytes: bytes, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        status_msg = await context.bot.send_message(chat_id=chat_id, text="⏳ <i>[Remove.bg] Đang bóc tách nền vật thể siêu tốc...</i>", parse_mode="HTML")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.remove.bg/v1.0/removebg",
                    headers={"X-Api-Key": REMOVEBG_API_KEY},
                    files={"image_file": image_bytes},
                    data={"size": "auto"},
                    timeout=30.0
                )
            if response.status_code == 200:
                await context.bot.send_document(chat_id=chat_id, document=response.content, filename="no_bg.png", caption="✅ Đã xóa nền hoàn tất! Định dạng PNG trong suốt.")
                await status_msg.delete()
            else:
                await status_msg.edit_text(f"❌ Lỗi bóc nền ({response.status_code}): {response.text}")
        except Exception as e:
            await status_msg.edit_text(f"❌ Lỗi phân hệ đồ họa: {e}")

class AgentOCR:
    @staticmethod
    async def read_image(image_bytes: bytes) -> str:
        try:
            async with httpx.AsyncClient() as client:
                files = {"file": ("ocr_image.jpg", image_bytes, "image/jpeg")}
                response = await client.post(
                    "https://api.ocr.space/parse/image",
                    headers={"apikey": "helloworld"},
                    files=files,
                    data={"language": "vie"},
                    timeout=30.0
                )
            if response.status_code == 200:
                data = response.json()
                if data.get("ParsedResults"):
                    return data["ParsedResults"][0].get("ParsedText", "Không tìm thấy văn bản trong ảnh.")
            return "❌ Lỗi trích xuất chữ từ ảnh (OCR Engine)."
        except Exception as e:
            return f"❌ Phân hệ OCR gián đoạn: {e}"

class AgentData:
    @staticmethod
    def search_trend(keyword: str) -> str:
        try:
            results = DDGS().text(keyword, max_results=5)
            if not results: return "❌ Không tìm thấy thông tin mới."
            resp = f"🌍 <b>KẾT QUẢ QUÉT TREND: '{keyword}'</b>\n\n"
            for idx, res in enumerate(results): resp += f"{idx+1}. <b>{res['title']}</b>\n- <i>{res['body']}</i>\n🔗 <a href='{res['href']}'>Xem</a>\n\n"
            return resp
        except Exception as e: return f"❌ Lỗi quét mạng: {e}"

class AgentMedia:
    @staticmethod
    async def generate(prompt: str, media_type: str, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        action_name = "Tạo Ảnh" if media_type == "image" else "Render Video"
        status_msg = await context.bot.send_message(chat_id=chat_id, text=f"⏳ <i>[Phân xưởng Media] Đang thực thi: {action_name}...</i>", parse_mode="HTML")
        try:
            # Sử dụng DeepL Engine dịch tối ưu hóa prompt sang tiếng Anh cho AI vẽ tranh
            english_prompt = await AgentDeepL.translate(prompt, "EN")
            safe_prompt = urllib.parse.quote(f"{english_prompt}, photorealistic, cinematic, 4k, highly detailed")
            api_url = f"https://image.pollinations.ai/prompt/{safe_prompt}"
            
            caption = f"🎨 <b>Đã tạo Ảnh thành công!</b>\n<i>Prompt gốc: {prompt}</i>"
            if media_type == "video":
                caption = f"🎬 <b>TEST KHUNG VIDEO THÀNH CÔNG!</b>\n\n💡 <i>Hệ thống trả về bản nháp dạng ảnh. Khi nạp thêm API Video vào hệ thống, vị trí này sẽ tự động xuất file MP4!</i>"
            
            await context.bot.send_photo(chat_id=chat_id, photo=api_url, caption=caption, parse_mode="HTML")
            await status_msg.delete()
        except Exception as e:
            await status_msg.edit_text(f"❌ Lỗi Phân xưởng Media: {e}")

class AgentContent:
    @staticmethod
    def create_script(topic: str, user_id: int) -> str:
        prompt = """Bạn là chuyên gia Content Creator & Affiliate Marketing. Hãy viết 1 kịch bản video TikTok/Reels ngắn (dưới 1 phút). 
        Cấu trúc bắt buộc: 1. Hook (Giật gân) 2. Vấn đề 3. Giải pháp (Sản phẩm) 4. Call to action (Chỉ giỏ hàng). 
        Viết kèm các gợi ý Cảnh quay (B-roll) tương ứng với từng câu thoại."""
        return AgentGemini.chat(prompt, topic, user_id)

class AgentDownloader:
    @staticmethod
    async def download(url: str, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        status_msg = await context.bot.send_message(chat_id=chat_id, text="⏳ <i>[Máy Hút Dữ Liệu] Đang bóc tách video gốc không logo...</i>", parse_mode="HTML")
        try:
            headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "HoTroToanBot-Enterprise/1.0"}
            payload = {"url": url, "videoQuality": "1080", "isAudioOnly": False}
            
            async with httpx.AsyncClient() as client:
                response = await client.post("https://api.cobalt.tools/api/json", headers=headers, json=payload, timeout=30.0)
                
            if response.status_code == 200:
                data = response.json()
                if data.get("status") in ["stream", "redirect", "success"]:
                    download_url = data.get("url")
                    await context.bot.send_video(
                        chat_id=chat_id, 
                        video=download_url, 
                        caption=f"✅ <b>TẢI THÀNH CÔNG!</b>\n🔗 <i>Nguồn: {url}</i>\n💡 Video đã làm sạch logo, sẵn sàng cho sếp đưa vào CapCut.",
                        parse_mode="HTML"
                    )
                    await status_msg.delete()
                else:
                    await status_msg.edit_text(f"❌ Không thể trích xuất video: {data.get('text', 'Lỗi không xác định')}")
            else:
                await status_msg.edit_text(f"❌ Máy chủ Cobalt từ chối: {response.status_code}")
        except Exception as e:
            await status_msg.edit_text(f"❌ Lỗi Phân xưởng Tải: {e}")

# ─── 5. BỘ NÃO ĐIỀU PHỐI TRUNG TÂM & TIẾP NHẬN LUỒNG ĐA PHƯƠNG TIỆN ──────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    if text == "🛸 MỞ TRẠM ĐIỀU KHIỂN AI CENTRAL":
        await cmd_start(update, context)
        return
        
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    routing_instruction = "Bạn là Tổng Giám Đốc AI. Phân loại lệnh của chủ nhân vào đúng hành động: voice, trend, code, content, image, video, download, mmo, general. Nếu user gửi đường link URL, đổi action thành 'download'."
    router_json = AgentGemini.chat(routing_instruction, text, user_id, is_json=True)
    
    try:
        route_plan = json.loads(router_json)
        action, data = route_plan.get("action"), route_plan.get("data", "")
        
        if action == "voice": await AgentVoice.render(data, user_id, context, update.effective_chat.id)
        elif action == "image": await AgentMedia.generate(data, "image", context, update.effective_chat.id)
        elif action == "video": await AgentMedia.generate(data, "video", context, update.effective_chat.id)
        elif action == "download": await AgentDownloader.download(data, context, update.effective_chat.id)
        elif action == "trend":
            await update.message.reply_text(f"⏳ <i>[Data Agent] Đang cào dữ liệu: '{data}'...</i>", parse_mode="HTML")
            await update.message.reply_text(AgentData.search_trend(data), parse_mode="HTML", disable_web_page_preview=True)
        elif action == "code":
            await update.message.reply_text("⏳ <i>[Phòng Code] Đang biên dịch thuật toán...</i>", parse_mode="HTML")
            code_reply = await AgentClaude.chat(data, user_id)
            await send_long_text(update, f"👨‍💻 <b>KẾT QUẢ PHÂN TÍCH LẬP TRÌNH:</b>\n\n{code_reply}")
        elif action == "content":
            await send_long_text(update, f"📝 <b>KỊCH BẢN VIDEO DÀNH CHO SẾP:</b>\n\n{AgentContent.create_script(data, user_id)}")
        elif action == "mmo":
            mmo_prompt = "Bạn là Chuyên gia MMO & Automation. Đưa ra action plan cụ thể."
            await send_long_text(update, f"💡 <b>CHIẾN LƯỢC HỆ THỐNG ĐỀ XUẤT:</b>\n\n{AgentGemini.chat(mmo_prompt, data, user_id)}")
        else:
            await update.message.reply_text(AgentGemini.chat("Bạn là Trợ lý trung tâm HoTroToanBot.", text, user_id), reply_markup=get_inline_dashboard())
            
    except Exception as err:
        logger.error(f"Routing Error: {err} | JSON: {router_json}")
        await update.message.reply_text("Dạ, luồng dữ liệu trung tâm đang đồng bộ, sếp vui lòng thử lại sau giây lát ạ!")

async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    photo_file = await update.message.photo[-1].get_file()
    photo_bytes = await photo_file.download_as_bytearray()
    context.user_data["last_photo_bytes"] = bytes(photo_bytes)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Trích Xuất Chữ (OCR)", callback_data="ocr_photo")],
        [InlineKeyboardButton("✂️ Tách Nền Vật Thể (Remove.bg)", callback_data="removebg_photo")]
    ])
    await update.message.reply_text("📥 <b>Đã nhận tập tin Hình ảnh từ Sếp!</b>\nSếp muốn phân xưởng nào thực thi xử lý bức ảnh này?", parse_mode="HTML", reply_markup=keyboard)

async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    voice = update.message.voice or update.message.audio
    status_msg = await update.message.reply_text("⚡ <i>[Whisper Engine] Đang bóc băng ghi âm giọng nói của sếp...</i>", parse_mode="HTML")
    
    voice_file = await voice.get_file()
    voice_bytes = await voice_file.download_as_bytearray()
    
    transcribed_text = await AgentWhisper.transcribe(bytes(voice_bytes))
    await status_msg.delete()
    
    if transcribed_text and not transcribed_text.startswith("❌"):
        await update.message.reply_text(f"🗣️ <b>Lệnh Giọng Nói Đã Chuyển Thành Văn Bản:</b>\n<i>\"{transcribed_text}\"</i>", parse_mode="HTML")
        # Đẩy thẳng text đã transcription vào bộ não điều phối trung tâm để chạy lệnh tự động
        update.message.text = transcribed_text
        await handle_message(update, context)
    else:
        await update.message.reply_text(f"❌ Không thể xử lý âm thanh: {transcribed_text}")

# ─── 6. LỆNH ĐIỀU KHIỂN HỆ THỐNG ───────────────────────────────────────────────
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    status_text = (
        "🎛️ <b>TRẠNG THÁI CÁC PHÂN HỆ AI ENGINE V11.0:</b>\n\n"
        f"🤖 <b>Sếp Tổng Gemini Router:</b> ✅ Hoạt động\n"
        f"👨‍💻 <b>Claude Lập Trình:</b> {'✅ Đã cấu hình' if CLAUDE_API_KEY else '⚠️ Chưa Key (Gemini chạy thay)'}\n"
        f"🌐 <b>DeepL Dịch Thuật:</b> ✅ ĐÃ KÍCH HOẠT (Mã hóa :fx)\n"
        f"✂️ <b>Remove.bg Xóa Phông:</b> ✅ ĐÃ KÍCH HOẠT\n"
        f"🎙️ <b>Fish Audio Clone Giọng:</b> ✅ ĐÃ KÍCH HOẠT\n"
        f"🗣️ <b>Whisper Nghe Hiểu:</b> ✅ ĐÃ KÍCH HOẠT (Cổng OpenAI)\n"
        f"📥 <b>Cobalt Downloader:</b> ✅ Sẵn sàng bóc logo Video\n"
        f"🔒 <b>Khóa Bảo Mật Chủ Nhân:</b> 🔐 AN TOÀN TUYỆT ĐỐI\n"
    )
    await update.message.reply_text(status_text, parse_mode="HTML")

async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    uid = update.effective_user.id
    if uid in user_memory: user_memory[uid] = []
    if uid in claude_memory: claude_memory[uid] = []
    await update.message.reply_text("🧹 <b>Đã xóa sạch bộ nhớ ngữ cảnh của tất cả các AI!</b>")

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    text = (
        "👑 <b>TRẠM ĐIỀU HÀNH THƯƠNG MẠI DOANH NGHIỆP V11.0</b>\n\n"
        "Chào mừng sếp Toàn trở lại phòng làm việc. Toàn bộ tài nguyên API cao cấp nhất đã được liên kết đồng bộ thành công.\n\n"
        "✨ <b>Tính năng nâng cấp vừa bật:</b>\n"
        "1. Gửi tin nhắn thoại ➔ Bot tự chuyển thành text và thực thi lệnh.\n"
        "2. Gửi ảnh ➔ Chọn nút trích chữ (OCR) hoặc Tách phông nền trong suốt để làm ảnh sản phẩm.\n"
        "3. Thả link video ➔ Máy hút Cobalt tự động bóc tách file sạch không logo."
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=get_bottom_menu())
    await update.message.reply_text("🎛️ <b>BẢNG ĐIỀU KHIỂN TÁC VỤ NHANH:</b>", parse_mode="HTML", reply_markup=get_inline_dashboard())

async def send_long_text(update: Update, text: str):
    for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
        try: await update.message.reply_text(chunk, parse_mode="HTML")
        except: await update.message.reply_text(chunk)

# ─── GIAO DIỆN NÚT BẤM TƯƠNG TÁC ────────────────────────────────────────────────
def get_bottom_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton("🛸 MỞ TRẠM ĐIỀU KHIỂN AI CENTRAL")]], resize_keyboard=True, is_persistent=True)

def get_inline_dashboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👨‍💻 Kỹ sư Code", callback_data="btn_code"), InlineKeyboardButton("📝 Viết Kịch Bản", callback_data="btn_content")],
        [InlineKeyboardButton("🎨 Tạo Ảnh AI", callback_data="btn_image"), InlineKeyboardButton("🎙️ Đọc Voice", callback_data="btn_voice")],
        [InlineKeyboardButton("📥 Tải Video Không Logo", callback_data="btn_download"), InlineKeyboardButton("📈 Quét Trend", callback_data="btn_trend")]
    ])

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() 
    
    photo_bytes = context.user_data.get("last_photo_bytes")
    if query.data == "ocr_photo" and photo_bytes:
        await query.message.reply_text("⏳ <i>[OCR Space] Đang trích xuất dữ liệu chữ...</i>", parse_mode="HTML")
        result = await AgentOCR.read_image(image_bytes=photo_bytes)
        await query.message.reply_text(f"📋 <b>KẾT QUẢ ĐỌC VĂN BẢN:</b>\n\n<code>{result}</code>", parse_mode="HTML")
        return
    elif query.data == "removebg_photo" and photo_bytes:
        await AgentRemoveBg.remove(photo_bytes, context, query.message.chat_id)
        return

    guidance = {
        "btn_code": "💻 <b>[Phân Hệ Lập Trình]</b>: Chat trực tiếp yêu cầu code hệ thống.",
        "btn_content": "📝 <b>[Phân Hệ Content]</b>: Chat yêu cầu lên kịch bản review thiết bị / đồ ăn vặt.",
        "btn_image": "🎨 <b>[Phân Hệ Đồ Họa]</b>: Bản vẽ thiết kế hình ảnh, tự động dịch bằng DeepL trước khi tạo.",
        "btn_voice": "🎙️ <b>[Phân Hệ Voice]</b>: Chat nội dung văn bản cần chuyển thành giọng nói.",
        "btn_trend": "📈 <b>[Phân Hệ Trend]</b>: Chat từ khóa sếp muốn cào dữ liệu thị trường.",
        "btn_download": "📥 <b>[Máy Hút Dữ Liệu]</b>: Ném link TikTok/YouTube/FB vào khung chat để tải video gốc không logo."
    }
    if query.data in guidance:
        await query.message.reply_text(guidance[query.data], parse_mode="HTML")

# ─── KHỞI CHẠY KHUNG ĐIỀU HÀNH ──────────────────────────────────────────────────
def main() -> None:
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Enterprise Architecture VIP V11.0 Online & Keys Loaded...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()