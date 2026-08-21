# 📚 DANH MỤC BIẾN MÔI TRƯỜNG & TÍCH HỢP API TOAN AAS
*(TOAN AAS Master API Keys & Environment Configuration Catalog)*

Tệp này cung cấp bảng tra cứu toàn diện về tất cả các API, Gateway và biến môi trường đang được sử dụng trong hệ sinh thái **TOAN AAS** (Telegram Bot, FastAPI Web App, Background Workers và Ubuntu VPS).

---

## 🗂️ Vị Trí Lưu Trữ Khóa Cấu Hình (Key Storage Locations)

1. **Lưu trữ Cục bộ (Local Disk):**
   - [`deploy/env/toanaas_all_keys.env`](toanaas_all_keys.env) - Tệp `.env` cấu hình hoàn chỉnh chứa tất cả các khóa bí mật.
   - [`deploy/env/toanaas-worker.env.example`](toanaas-worker.env.example) - Tệp mẫu cho Worker.
2. **Lưu trữ Trên Máy Chủ (Production Ubuntu VPS):**
   - `/etc/toanaas/bot.env` - Tệp môi trường chính cho Telegram Bot & Workers (Quyền riêng tư `chmod 600`).
   - `/etc/toanaas/web.env` - Tệp môi trường cho FastAPI Web App (`toanaas-web.service`).

---

## 1. 🤖 AI Language Models (LLMs & Chat & Prompts)

| Tên Biến Môi Trường | Nhà Cung Cấp / Nền Tảng | Vai Trò & Chức Năng | Trạng Thái Trên VPS | Nơi Đăng Ký / Lấy Khóa |
| :--- | :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Google Gemini AI | Tạo prompt, brief kịch bản, trợ lý AI | *Cần điền key Google AI Studio* | [Google AI Studio](https://aistudio.google.com/apikey) |
| `OPENAI_API_KEY` | OpenAI (GPT-4o, Whisper, DALL-E) | LLM Chatbot, phân tích ảnh, Voice TTS, DALL-E | ✅ **Đã Cấu Hình** | [OpenAI Platform](https://platform.openai.com/api-keys) |
| `OPENROUTER_API_KEY` | OpenRouter.ai | Cổng đa mô hình (Claude 3.5, Llama, DeepSeek) | ✅ **Đã Cấu Hình** | [OpenRouter](https://openrouter.ai/keys) |
| `SHOPAIKEY_API_KEY` | ShopAIKey Gateway | Cổng tổng hợp mô hình AI, GPT, Veo | ✅ **Đã Cấu Hình** | [ShopAIKey Dashboard](https://api.shopaikey.com) |
| `WOKU_API_KEY` | WokuShop Gateway | Proxy mở rộng dự phòng mô hình AI | ✅ **Đã Cấu Hình** | Woku Platform |
| `YOUMIND_API_KEY` | YouMind Gateway | Proxy tạo nội dung bổ trợ | ✅ **Đã Cấu Hình** | YouMind Console |

---

## 2. 🎬 AI Video Generation Engines (Veo 3.1, Kling, MiniMax, Runway)

| Tên Biến Môi Trường | Nền Tảng | Vai Trò & Chức Năng | Trạng Thái Trên VPS |
| :--- | :--- | :--- | :--- |
| `RUNWAY_API_KEY` | Runway ML (Gen-2/3/4) | Sinh video chuyển động điện ảnh cao cấp | ✅ **Đã Cấu Hình** |
| `KLING_ACCESS_KEY` & `KLING_SECRET_KEY` | Kling AI Official | Tạo video chuyển động vật lý, lip-sync | ✅ **Đã Cấu Hình** |
| `MINIMAX_API_KEY` & `MINIMAX_GROUP_ID` | MiniMax Hailuo AI | Tạo video phong cách chân thực & voice AI | ✅ **Đã Cấu Hình** |
| `KEY4U_VIDEO_AUTH_HEADER_VALUE` | Key4U Gateway | Cổng kết nối Google Veo 3.1, Hailuo-02/2.3, Kling | ✅ **Đã Cấu Hình** |
| `SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE` | ShopAIKey Video | Tạo video sản phẩm, multi-scene video rendering | ✅ **Đã Cấu Hình** |

---

## 3. 🎨 AI Image, Graphics & Design (Stability, Remove.bg, Replicate)

| Tên Biến Môi Trường | Nền Tảng | Vai Trò & Chức Năng | Trạng Thái Trên VPS |
| :--- | :--- | :--- | :--- |
| `STABILITY_API_KEY` | Stability AI (SDXL / Ultra) | Tạo ảnh nghệ thuật độ phân giải cao | ✅ **Đã Cấu Hình** |
| `REMOVEBG_API_KEY` | Remove.bg | Tách nền ảnh sản phẩm & nhân vật tự động | ✅ **Đã Cấu Hình** |
| `REPLICATE_API_TOKEN` | Replicate Cloud | Chạy mô hình mã nguồn mở Flux, SD, Upscale | ✅ **Đã Cấu Hình** |
| `PIXABAY_API_KEY` | Pixabay API | Tìm kiếm ảnh stock và video nền miễn phí | ✅ **Đã Cấu Hình** |

---

## 4. 🎙️ Audio, Voice, TTS & Music

| Tên Biến Môi Trường | Nền Tảng | Vai Trò & Chức Năng | Trạng Thái Trên VPS |
| :--- | :--- | :--- | :--- |
| `TTS_PROVIDER` | `key4u_minimax` | Lồng tiếng AI, chuyển văn bản thành giọng đọc | ✅ **Đã Cấu Hình** |
| `MUSICFUL_API_KEY` | Musicful / Suno AI | Sinh nhạc nền, giai điệu AI cho video sản phẩm | ✅ **Đã Cấu Hình** |
| `TRANSLATE_PROVIDER` | DeepL / Open Translation | Dịch thuật tự động phụ đề và hội thoại | ✅ **Đã Cấu Hình** |

---

## 5. 💳 Thanh Toán & Nạp Xu (PayOS Payment Gateway)

| Tên Biến Môi Trường | Nền Tảng | Vai Trò & Chức Năng | Trạng Thái Trên VPS |
| :--- | :--- | :--- | :--- |
| `PAYOS_CLIENT_ID` | PayOS Vietnam | Mã định danh tài khoản tích hợp thanh toán | ✅ **Đã Cấu Hình** |
| `PAYOS_API_KEY` | PayOS Vietnam | Khóa API tạo link nạp Xu QR VietQR tự động | ✅ **Đã Cấu Hình** |
| `PAYOS_CHECKSUM_KEY` | PayOS Vietnam | Khóa chữ ký HMAC xác thực Webhook thanh toán | ✅ **Đã Cấu Hình** |

---

## 6. 📱 Telegram Platform & Bot Server

| Tên Biến Môi Trường | Vai Trò | Trạng Thái Trên VPS |
| :--- | :--- | :--- |
| `TELEGRAM_TOKEN` | Bot Token từ @BotFather | ✅ **Đã Cấu Hình** |
| `TELEGRAM_API_PROXY_SECRET` | Secret xác thực bảo mật giữa Nginx và Local Bot API | ✅ **Đã Cấu Hình** |
| `TELEGRAM_API_BASE_URL` | Địa chỉ proxy tải lên/xuống file media dung lượng lớn (tới 2GB) | `https://tg.toanaas.vn` |
| `OWNER_ID` / `ADMIN_ID` | Telegram User ID của quản trị viên tối cao (`7126457028`) | ✅ **Đã Cấu Hình** |

---

## 7. 🌐 Open APIs & Public Utilities (Không Yêu Cầu Key / Hoàn Toàn Miễn Phí)

Các tiện ích mở rộng trong **Bộ Công Cụ Miễn Phí** sử dụng các Public API mở chuẩn công nghiệp:
- **Tỷ giá ngoại tệ & Xu:** `ExchangeRate-API` / `Frankfurter Open Currency API`
- **Dự báo thời tiết:** `Open-Meteo API` (Dữ liệu thời tiết toàn cầu theo thời gian thực)
- **Tạo mã QR:** `QR Server API` (Sinh ảnh mã QR tức thì)
- **Sinh Avatar AI:** `DiceBear Open Avatar Engine` (Bottts, Avataaars, Croodles, Personas)
- **Dịch thuật:** `MyMemory Open Translation API` (Hỗ trợ hơn 100+ ngôn ngữ)
