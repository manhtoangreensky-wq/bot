"""
╔══════════════════════════════════════════════════════════════╗
║   HoTroToanBot - TRẠM ĐIỀU KHIỂN AI ĐA TÁC VỤ VIP V11.0      ║
║   Enterprise Multi-Agent Orchestration System                ║
║   Tích hợp: Code, Content, Voice, Image, Data, Download      ║
║   MỚI V11: OCR, DeepL Dịch, Fish Audio Clone, Remove.bg      ║
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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ─── 1. CẤU HÌNH HỆ THỐNG CORE & LOGGING ───────────────────────────────────────
logging.basicConfig(format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", level=logging.INFO)
logger = logging.getLogger("HoTroToanBot")

WEB_APP_URL = "https://manhtoangreensky-wq.github.io/web-admin-bot/trangchu.html"
TELEGRAM_TOKEN = os.environ.get("BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")
ADMIN_ID       = os.environ.get("ADMIN_ID")

# ─── BIẾN MÔI TRƯỜNG CÁC CÔNG CỤ MỚI V11 ───────────────────────────────────────
OCR_API_KEY      = os.environ.get("OCR_API_KEY", "helloworld")  # Free key mặc định của OCR.Space
DEEPL_API_KEY    = os.environ.get("DEEPL_API_KEY", "")          # deepl.com/pro-api (Free: 500k ký tự/tháng)
FISH_AUDIO_KEY   = os.environ.get("FISH_AUDIO_KEY", "")         # fish.audio (clone giọng, rẻ hơn ElevenLabs)
REMOVEBG_API_KEY = os.environ.get("REMOVEBG_API_KEY", "")       # remove.bg (50 ảnh/tháng free)
OPENAI_API_KEY   = os.environ.get("OPENAI_API_KEY", "")         # Whisper STT (nhận dạng giọng nói)

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
    
    if len(user_timestamps) >= 7: 
        await update.message.reply_text("⚠️ <b>CẢNH BÁO:</b> Sếp ra lệnh quá nhanh, vui lòng đợi AI xử lý luồng cũ.")
        return True
    
    user_rate_limit[user_id].append(current_time)
    return False

# ─── 3. ĐỊNH CHUẨN ĐẦU RA SẾP TỔNG (ROUTER SCHEMA) ─────────────────────────────
class AgentRouter(BaseModel):
    action: str = Field(description="Phân loại: 'voice', 'voice_clone', 'trend', 'code', 'content', 'image', 'video', 'mmo', 'download', 'ocr', 'translate', 'removebg', 'general'")
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
            fallback_msg = "⚠️ <i>(Chưa nạp CLAUDE_API_KEY. Hệ thống tự động chuyển task cho Gemini xử lý bù đắp...)</i>\n\n"
            return fallback_msg + AgentGemini.chat(CLAUDE_SYSTEM_PROMPT, prompt, user_id)
        if user_id not in claude_memory: claude_memory[user_id] = []
        claude_memory[user_id].append({"role": "user", "content": prompt})
        if len(claude_memory[user_id]) > 10: claude_memory[user_id] = claude_memory[user_id][-10:]
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": CLAUDE_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                    json={"model": "claude-sonnet-4-6", "max_tokens": 4096, "system": CLAUDE_SYSTEM_PROMPT, "messages": claude_memory[user_id]},
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
        status_msg = await context.bot.send_message(chat_id=chat_id, text="⏳ <i>[Phân xưởng Voice] Đang xử lý âm thanh kỹ thuật...</i>", parse_mode="HTML")
        try:
            communicate = edge_tts.Communicate(text, "vi-VN-NamMinhNeural")
            await communicate.save(output_file)
            with open(output_file, 'rb') as audio_file: await context.bot.send_audio(chat_id=chat_id, audio=audio_file, caption="✅ Render Voice hoàn tất!")
            await status_msg.delete()
        except Exception as e: await status_msg.edit_text(f"❌ Lỗi Voice: {e}")
        finally:
            if os.path.exists(output_file): os.remove(output_file)

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
            english_prompt = AgentGemini.chat("Dịch mô tả sau sang tiếng Anh ngắn gọn, thêm các từ khóa: photorealistic, cinematic, 4k, highly detailed.", prompt, chat_id)
            safe_prompt = urllib.parse.quote(english_prompt)
            api_url = f"https://image.pollinations.ai/prompt/{safe_prompt}"
            
            caption = f"🎨 <b>Đã tạo Ảnh thành công!</b>\n<i>Prompt: {prompt}</i>"
            if media_type == "video":
                caption = f"🎬 <b>TEST KHUNG VIDEO THÀNH CÔNG!</b>\n\n💡 <i>Hệ thống trả về bản nháp (Storyboard) dạng ảnh. Khi nạp API Video (Veo/Kling) vào hệ thống, vị trí này sẽ tự động xuất file MP4!</i>"
            
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
    """Phân hệ tải Video/Audio mọi nền tảng không có Logo (Dùng Cobalt Tools API)"""
    @staticmethod
    async def download(url: str, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        status_msg = await context.bot.send_message(chat_id=chat_id, text="⏳ <i>[Máy Hút Dữ Liệu] Đang bóc tách video gốc không logo...</i>", parse_mode="HTML")
        try:
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "HoTroToanBot-Enterprise/1.0"
            }
            payload = {
                "url": url,
                "videoQuality": "1080",
                "isAudioOnly": False
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post("https://api.cobalt.tools/api/json", headers=headers, json=payload, timeout=30.0)
                
            if response.status_code == 200:
                data = response.json()
                if data.get("status") in ["stream", "redirect", "success"]:
                    download_url = data.get("url")
                    await context.bot.send_video(
                        chat_id=chat_id, 
                        video=download_url, 
                        caption=f"✅ <b>TẢI THÀNH CÔNG!</b>\n🔗 <i>Nguồn: {url}</i>\n💡 Video đã được làm sạch logo, sẵn sàng đưa vào xưởng CapCut.",
                        parse_mode="HTML"
                    )
                    await status_msg.delete()
                else:
                    await status_msg.edit_text(f"❌ Không thể trích xuất video: {data.get('text', 'Lỗi không xác định')}")
            else:
                await status_msg.edit_text(f"❌ Máy chủ Cobalt từ chối: {response.status_code}")
                
        except Exception as e:
            await status_msg.edit_text(f"❌ Lỗi Phân xưởng Tải: {e}")


# ─── 4b. PHÂN HỆ MỚI V11: OCR / DỊCH / CLONE GIỌNG / XÓA NỀN ──────────────────

class AgentOCR:
    """Đọc chữ từ ảnh — OCR.Space API (hỗ trợ tiếng Việt, hóa đơn, tài liệu)"""
    @staticmethod
    async def read_image(image_url: str = "", image_bytes: bytes = None) -> str:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                if image_bytes:
                    response = await client.post(
                        "https://api.ocr.space/parse/image",
                        data={"apikey": OCR_API_KEY, "language": "vie", "OCREngine": "2",
                              "detectOrientation": "true", "scale": "true"},
                        files={"file": ("img.jpg", image_bytes, "image/jpeg")},
                    )
                else:
                    response = await client.post(
                        "https://api.ocr.space/parse/image",
                        data={"apikey": OCR_API_KEY, "language": "vie", "OCREngine": "2",
                              "url": image_url},
                    )
            data = response.json()
            if data.get("IsErroredOnProcessing"):
                return f"❌ OCR lỗi: {data.get('ErrorMessage', ['Không xác định'])[0]}"
            results = data.get("ParsedResults", [])
            text = results[0].get("ParsedText", "").strip() if results else ""
            return text if text else "⚠️ Không đọc được chữ trong ảnh."
        except Exception as e:
            return f"❌ Lỗi OCR: {e}"

class AgentTranslate:
    """Dịch văn bản — DeepL Free API (500.000 ký tự/tháng miễn phí)"""
    @staticmethod
    async def translate(text: str, target_lang: str = "VI") -> str:
        if not DEEPL_API_KEY:
            return "⚠️ Chưa cấu hình DEEPL_API_KEY. Thêm vào Railway Variables."
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    "https://api-free.deepl.com/v2/translate",
                    data={"auth_key": DEEPL_API_KEY, "text": text, "target_lang": target_lang},
                )
            result = response.json()
            translated = result["translations"][0]["text"]
            detected = result["translations"][0].get("detected_source_language", "?")
            return f"🌐 <b>Dịch từ [{detected}] → [{target_lang}]:</b>\n\n{translated}"
        except Exception as e:
            return f"❌ Lỗi DeepL: {e}"

class AgentVoiceClone:
    """Clone giọng nói — Fish Audio API (rẻ hơn ElevenLabs 5-10x, tiếng Việt tốt)"""
    @staticmethod
    async def speak(text: str, context: ContextTypes.DEFAULT_TYPE, chat_id: int,
                    reference_id: str = ""):
        if not FISH_AUDIO_KEY:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Chưa cấu hình FISH_AUDIO_KEY. Fish Audio: fish.audio → API Key.\n"
                     "<i>Tạm thời dùng Edge TTS mặc định...</i>",
                parse_mode="HTML"
            )
            await AgentVoice.render(text, chat_id, context, chat_id)
            return

        status_msg = await context.bot.send_message(
            chat_id=chat_id, text="⏳ <i>[Fish Audio] Đang clone giọng...</i>", parse_mode="HTML"
        )
        try:
            payload = {"text": text, "format": "mp3", "mp3_bitrate": 128}
            if reference_id:
                payload["reference_id"] = reference_id  # ID model giọng clone

            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    "https://api.fish.audio/v1/tts",
                    headers={"Authorization": f"Bearer {FISH_AUDIO_KEY}",
                             "Content-Type": "application/json"},
                    json=payload,
                )

            if response.status_code == 200:
                audio_data = response.content
                await context.bot.send_audio(
                    chat_id=chat_id,
                    audio=audio_data,
                    filename="fish_voice.mp3",
                    caption="✅ <b>Fish Audio Clone hoàn tất!</b>",
                    parse_mode="HTML"
                )
                await status_msg.delete()
            else:
                await status_msg.edit_text(f"❌ Fish Audio lỗi {response.status_code}: {response.text[:200]}")
        except Exception as e:
            await status_msg.edit_text(f"❌ Lỗi Fish Audio: {e}")

class AgentRemoveBg:
    """Xóa nền ảnh — Remove.bg API (50 lần/tháng miễn phí)"""
    @staticmethod
    async def remove(image_bytes: bytes, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        if not REMOVEBG_API_KEY:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Chưa cấu hình REMOVEBG_API_KEY. Lấy key tại remove.bg → API.",
                parse_mode="HTML"
            )
            return
        status_msg = await context.bot.send_message(
            chat_id=chat_id, text="⏳ <i>[Remove.bg] Đang xóa nền ảnh...</i>", parse_mode="HTML"
        )
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    "https://api.remove.bg/v1.0/removebg",
                    headers={"X-Api-Key": REMOVEBG_API_KEY},
                    files={"image_file": ("image.jpg", image_bytes, "image/jpeg")},
                    data={"size": "auto"},
                )
            if response.status_code == 200:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=response.content,
                    filename="no_background.png",
                    caption="✅ <b>Xóa nền thành công!</b> File PNG trong suốt sẵn sàng dùng.",
                    parse_mode="HTML"
                )
                await status_msg.delete()
            else:
                await status_msg.edit_text(f"❌ Remove.bg lỗi {response.status_code}: {response.text[:200]}")
        except Exception as e:
            await status_msg.edit_text(f"❌ Lỗi Remove.bg: {e}")

class AgentWhisper:
    """Nhận dạng giọng nói → văn bản — OpenAI Whisper (cực chính xác tiếng Việt)"""
    @staticmethod
    async def transcribe(audio_bytes: bytes) -> str:
        if not OPENAI_API_KEY:
            return "⚠️ Chưa cấu hình OPENAI_API_KEY cho Whisper."
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    data={"model": "whisper-1", "language": "vi"},
                    files={"file": ("audio.ogg", audio_bytes, "audio/ogg")},
                )
            return response.json().get("text", "").strip()
        except Exception as e:
            return f"❌ Lỗi Whisper: {e}"


# ─── XỬ LÝ ẢNH & VOICE GỬI VÀO ──────────────────────────────────────────────────

async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Nhận ảnh → hỏi sếp muốn OCR hay xóa nền"""
    if await restrict_access(update): return
    file = await context.bot.get_file(update.message.photo[-1].file_id)
    image_bytes = bytes(await file.download_as_bytearray())

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 OCR — Đọc chữ trong ảnh", callback_data=f"ocr_photo"),
         InlineKeyboardButton("✂️ Xóa nền ảnh", callback_data=f"removebg_photo")]
    ])
    # Lưu tạm ảnh vào context
    context.user_data["last_photo_bytes"] = image_bytes
    await update.message.reply_text(
        "📸 Đã nhận ảnh! Sếp muốn làm gì với ảnh này?",
        reply_markup=kb
    )

async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Nhận voice note → Whisper chuyển thành text → AI trả lời"""
    if await restrict_access(update): return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    voice = update.message.voice or update.message.audio
    file = await context.bot.get_file(voice.file_id)
    audio_bytes = bytes(await file.download_as_bytearray())

    await update.message.reply_text("🎙️ <i>[Whisper] Đang nhận dạng giọng nói...</i>", parse_mode="HTML")
    transcribed = await AgentWhisper.transcribe(audio_bytes)

    if not transcribed or transcribed.startswith("⚠️") or transcribed.startswith("❌"):
        await update.message.reply_text(
            f"{transcribed}\n\n💡 Thêm OPENAI_API_KEY vào Railway để dùng Whisper STT."
        )
        return

    user_id = update.effective_user.id
    reply = AgentGemini.chat("Bạn là Trợ lý HoTroToanBot. Trả lời ngắn gọn, thực chiến.", transcribed, user_id)
    await send_long_text(update, f"🎙️ <i>Whisper nghe được: \"{transcribed}\"</i>\n\n{reply}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    if text == "🛸 MỞ TRẠM ĐIỀU KHIỂN AI CENTRAL":
        await cmd_start(update, context)
        return
        
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    routing_instruction = (
        "Bạn là Tổng Giám Đốc AI. Phân loại lệnh của chủ nhân vào đúng hành động: "
        "voice, voice_clone, trend, code, content, image, video, download, mmo, ocr, translate, removebg, general. "
        "Nếu user gửi link URL (tiktok, youtube, facebook...) → 'download'. "
        "Nếu user muốn dịch văn bản → 'translate'. "
        "Nếu user muốn clone giọng nói / giọng thật / fish audio → 'voice_clone'. "
        "Nếu user gửi link ảnh và muốn đọc chữ → 'ocr'. "
        "Nếu user muốn xóa nền ảnh từ URL → 'removebg'."
    )
    router_json = AgentGemini.chat(routing_instruction, text, user_id, is_json=True)
    
    try:
        route_plan = json.loads(router_json)
        action, data = route_plan.get("action"), route_plan.get("data", "")
        
        if action == "voice": await AgentVoice.render(data, user_id, context, update.effective_chat.id)
        elif action == "voice_clone":
            await AgentVoiceClone.speak(data, context, update.effective_chat.id)
        elif action == "ocr":
            await update.message.reply_text("⏳ <i>[OCR] Đang đọc chữ trong ảnh...</i>", parse_mode="HTML")
            ocr_result = await AgentOCR.read_image(image_url=data)
            await send_long_text(update, f"📋 <b>KẾT QUẢ OCR:</b>\n\n<code>{ocr_result}</code>")
        elif action == "translate":
            await update.message.reply_text("⏳ <i>[DeepL] Đang dịch...</i>", parse_mode="HTML")
            translated = await AgentTranslate.translate(data)
            await send_long_text(update, translated)
        elif action == "removebg":
            await update.message.reply_text("⏳ <i>[Remove.bg] Đang tải ảnh từ URL...</i>", parse_mode="HTML")
            async with httpx.AsyncClient(timeout=20) as client:
                img_resp = await client.get(data)
            await AgentRemoveBg.remove(img_resp.content, context, update.effective_chat.id)
        elif action == "image": await AgentMedia.generate(data, "image", context, update.effective_chat.id)
        elif action == "video": await AgentMedia.generate(data, "video", context, update.effective_chat.id)
        elif action == "download": await AgentDownloader.download(data, context, update.effective_chat.id)
        elif action == "trend":
            await update.message.reply_text(f"⏳ <i>[Data Agent] Đang cào dữ liệu: '{data}'...</i>", parse_mode="HTML")
            await update.message.reply_text(AgentData.search_trend(data), parse_mode="HTML", disable_web_page_preview=True)
        elif action == "code":
            await update.message.reply_text("⏳ <i>[Phòng Code] Đang biên dịch thuật toán chuyên sâu...</i>", parse_mode="HTML")
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
        await update.message.reply_text("Dạ, luồng dữ liệu trung tâm đang đồng bộ, sếp vui lòng thử lại sau vài giây ạ!")

# ─── 6. LỆNH ĐIỀU KHIỂN HỆ THỐNG ───────────────────────────────────────────────
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await restrict_access(update): return
    status_text = (
        "🎛️ <b>TRẠNG THÁI CÁC PHÂN HỆ AI ENGINE V11.0:</b>\n\n"
        f"🤖 <b>Gemini 2.0 Flash (Router):</b> ✅ Hoạt động\n"
        f"👨‍💻 <b>Claude Sonnet 4.6 (Code Brain):</b> {'✅ Đã nạp Key' if CLAUDE_API_KEY else '⚠️ Chưa Key (Gemini code thay)'}\n"
        f"🎙️ <b>Edge TTS (Voice Nam Minh):</b> ✅ Trực tuyến\n"
        f"🐟 <b>Fish Audio (Clone Giọng):</b> {'✅ Đã nạp Key' if FISH_AUDIO_KEY else '⚠️ Chưa Key'}\n"
        f"📋 <b>OCR.Space (Đọc chữ ảnh):</b> {'✅ Key tùy chỉnh' if OCR_API_KEY != 'helloworld' else '🆓 Free Key mặc định'}\n"
        f"🌐 <b>DeepL (Dịch thuật):</b> {'✅ Đã nạp Key' if DEEPL_API_KEY else '⚠️ Chưa Key'}\n"
        f"✂️ <b>Remove.bg (Xóa nền):</b> {'✅ Đã nạp Key' if REMOVEBG_API_KEY else '⚠️ Chưa Key'}\n"
        f"🎤 <b>Whisper STT (Nghe giọng):</b> {'✅ Đã nạp Key' if OPENAI_API_KEY else '⚠️ Chưa Key'}\n"
        f"📈 <b>DuckDuckGo Trend:</b> ✅ Sẵn sàng\n"
        f"🎨 <b>Pollinations Media:</b> ✅ Sẵn sàng\n"
        f"📥 <b>Cobalt Downloader:</b> ✅ Sẵn sàng\n"
        f"🔒 <b>Khóa Chủ Nhân:</b> 🔐 ĐÃ BẬT TUYỆT ĐỐI\n"
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
        "👑 <b>HỆ THỐNG ENTERPRISE MULTI-AGENT VIP V11.0</b>\n\n"
        "Chào mừng sếp Toàn. Cỗ máy All-in-One đã lên nòng!\n\n"
        "🆕 <b>Tính năng mới V11:</b>\n"
        "🐟 Clone giọng thật (Fish Audio)\n"
        "📋 OCR đọc chữ từ ảnh\n"
        "🌐 Dịch thuật DeepL (500k ký tự/tháng free)\n"
        "✂️ Xóa nền ảnh (Remove.bg)\n"
        "🎤 Nhận giọng nói → text (Whisper)\n\n"
        "💡 <i>Gửi ảnh trực tiếp → Bot hỏi OCR hay xóa nền\n"
        "Gửi voice note → Whisper chép thành text → AI trả lời</i>\n\n"
        "🛠️ Lệnh: <code>/status</code> | <code>/clear</code>"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=get_bottom_menu())
    await update.message.reply_text("🎛️ <b>BẢNG ĐIỀU KHIỂN NHANH:</b>", parse_mode="HTML", reply_markup=get_inline_dashboard())

async def send_long_text(update: Update, text: str):
    for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
        try: await update.message.reply_text(chunk, parse_mode="HTML")
        except: await update.message.reply_text(chunk)

# ─── GIAO DIỆN NÚT BẤM TƯƠNG TÁC ────────────────────────────────────────────────
def get_bottom_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton("🛸 MỞ TRẠM ĐIỀU KHIỂN AI CENTRAL")]], resize_keyboard=True, is_persistent=True)

def get_inline_dashboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👨‍💻 Kỹ sư Code", callback_data="btn_code"),
         InlineKeyboardButton("📝 Viết Kịch Bản", callback_data="btn_content")],
        [InlineKeyboardButton("🎨 Tạo Ảnh AI", callback_data="btn_image"),
         InlineKeyboardButton("🎙️ Voice Edge TTS", callback_data="btn_voice")],
        [InlineKeyboardButton("🐟 Clone Giọng Fish", callback_data="btn_voice_clone"),
         InlineKeyboardButton("📋 OCR Đọc Ảnh", callback_data="btn_ocr")],
        [InlineKeyboardButton("🌐 Dịch DeepL", callback_data="btn_translate"),
         InlineKeyboardButton("✂️ Xóa Nền Ảnh", callback_data="btn_removebg")],
        [InlineKeyboardButton("📥 Tải Video Không Logo", callback_data="btn_download"),
         InlineKeyboardButton("📈 Quét Trend", callback_data="btn_trend")]
    ])

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() 
    
    guidance = {
        "btn_code":         "💻 <b>[Code Brain — Claude]</b>: Chat yêu cầu (VD: <i>'Viết mã Python đọc file CSV...'</i>)",
        "btn_content":      "📝 <b>[Content AI]</b>: Chat yêu cầu (VD: <i>'Viết kịch bản review loa xưởng cho TikTok...'</i>)",
        "btn_image":        "🎨 <b>[Đồ Họa AI]</b>: Chat yêu cầu (VD: <i>'Tạo ảnh góc làm việc ban đêm, ánh neon...'</i>)",
        "btn_voice":        "🎙️ <b>[Voice Edge TTS]</b>: Chat yêu cầu (VD: <i>'Đọc giọng nam: Xin chào anh em...'</i>)",
        "btn_voice_clone":  "🐟 <b>[Fish Audio Clone]</b>: Chat yêu cầu (VD: <i>'Clone giọng đọc đoạn: Hôm nay mình review...'</i>)\n⚙️ Cần thêm <code>FISH_AUDIO_KEY</code> vào Railway.",
        "btn_ocr":          "📋 <b>[OCR Đọc Ảnh]</b>: Gửi link ảnh vào chat (VD: <i>'OCR https://example.com/img.jpg'</i>)\nHoặc gửi ảnh trực tiếp → Bot tự hỏi.",
        "btn_translate":    "🌐 <b>[DeepL Dịch]</b>: Chat yêu cầu (VD: <i>'Dịch sang tiếng Anh: Hệ thống AI tự động hóa...'</i>)\n⚙️ Cần thêm <code>DEEPL_API_KEY</code> vào Railway.",
        "btn_removebg":     "✂️ <b>[Remove.bg Xóa Nền]</b>: Gửi ảnh trực tiếp → Bot tự hỏi, hoặc chat link ảnh.\n⚙️ Cần thêm <code>REMOVEBG_API_KEY</code> vào Railway.",
        "btn_trend":        "📈 <b>[Trend Agent]</b>: Chat yêu cầu (VD: <i>'Tìm trend thiết bị smart home 2026...'</i>)",
        "btn_download":     "📥 <b>[Máy Hút Video]</b>: Dán link TikTok/YouTube/FB/Insta vào chat, Bot tự bóc logo tải về!",
    }
    if query.data in guidance:
        await query.message.reply_text(guidance[query.data], parse_mode="HTML")
        return

    # Callback xử lý ảnh đã lưu tạm
    photo_bytes = context.user_data.get("last_photo_bytes")
    if query.data == "ocr_photo" and photo_bytes:
        await query.message.reply_text("⏳ <i>[OCR] Đang đọc chữ...</i>", parse_mode="HTML")
        result = await AgentOCR.read_image(image_bytes=photo_bytes)
        await query.message.reply_text(f"📋 <b>KẾT QUẢ OCR:</b>\n\n<code>{result}</code>", parse_mode="HTML")
    elif query.data == "removebg_photo" and photo_bytes:
        await AgentRemoveBg.remove(photo_bytes, context, query.message.chat_id)

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

    logger.info("🚀 Enterprise Architecture VIP V11.0 Online — OCR + DeepL + Fish Audio + Remove.bg + Whisper READY")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()