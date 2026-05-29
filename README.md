# 🤖 HoTroToanBot

Bot Telegram hỗ trợ kiếm tiền online toàn diện.

## 📦 Cài đặt

```bash
# 1. Clone hoặc tải project về
cd hotrotoanbot

# 2. Tạo virtual environment (khuyên dùng)
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# 3. Cài thư viện
pip install -r requirements.txt

# 4. Cấu hình bot
# Mở file config.py và điền:
# - BOT_TOKEN: lấy từ @BotFather trên Telegram
# - ADMIN_IDS: Telegram ID của bạn (lấy từ @userinfobot)
```

## ⚙️ Cấu hình

Mở `config.py` và chỉnh sửa:

```python
BOT_TOKEN = "1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ"  # Token từ @BotFather
ADMIN_IDS = [123456789]  # ID Telegram của bạn
```

## 🚀 Chạy bot

```bash
python bot.py
```

## 📁 Cấu trúc project

```
hotrotoanbot/
├── bot.py                  # File chính - khởi chạy bot
├── config.py               # Cấu hình (token, admin IDs...)
├── requirements.txt        # Thư viện cần thiết
├── handlers/
│   ├── __init__.py
│   ├── mxh_handler.py      # Kiếm tiền mạng xã hội
│   ├── video_handler.py    # Tạo & bán video
│   ├── freelance_handler.py # Freelance online
│   ├── affiliate_handler.py # Affiliate marketing
│   ├── tools_handler.py    # Công cụ hỗ trợ
│   └── admin_handler.py    # Lệnh admin
└── README.md
```

## 📱 Commands có sẵn

| Lệnh | Mô tả |
|------|-------|
| /start | Menu chính |
| /help | Hướng dẫn sử dụng |
| /menu | Quay về menu chính |
| /tip | Tip kiếm tiền ngẫu nhiên |
| /idea | Gợi ý ý tưởng kiếm tiền |
| /checklist | Checklist bắt đầu |
| /resource | Tài nguyên & công cụ |
| /broadcast | [Admin] Gửi thông báo |
| /stats | [Admin] Xem thống kê |

## 🔧 Phát triển thêm (TODO)

- [ ] Kết nối database (SQLite/PostgreSQL) lưu users
- [ ] Hệ thống premium/subscription
- [ ] Tích hợp AI (ChatGPT) để trả lời câu hỏi tự do
- [ ] Thêm mini-course trong bot
- [ ] Hệ thống referral (giới thiệu bạn bè)
- [ ] Push notification cho content mới
- [ ] Webhook deployment (Railway, Heroku, VPS)
- [ ] Tích hợp payment (Momo, VNPAY)
- [ ] Dashboard web cho admin

## 🚀 Deploy lên server

### Railway (miễn phí)
```bash
# Cài Railway CLI
npm install -g @railway/cli
railway login
railway init
railway up
```

### VPS (DigitalOcean, Vultr, etc.)
```bash
# Dùng PM2 để chạy nền
npm install -g pm2
pm2 start bot.py --interpreter python3
pm2 save
pm2 startup
```

## 📞 Liên hệ

Bot: @hotrotoanbot
```
