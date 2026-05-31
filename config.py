"""
Cấu hình bot - chỉ đọc từ biến môi trường.

Không đặt token/API key thật trong file này. Hãy cấu hình trên Railway/Render/VPS
hoặc file .env cục bộ và tham khảo .env.example.
"""
import os

# Hệ thống sẽ tự động lấy Token từ biến môi trường
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("BOT_TOKEN", "")

ADMIN_IDS = [
    int(x.strip())
    for x in os.environ.get("ADMIN_IDS", os.environ.get("ADMIN_ID", "")).split(",")
    if x.strip().isdigit()
]

BOT_NAME = "HoTroToanBot"
BOT_USERNAME = os.environ.get("BOT_USERNAME", "hotrotoanbot")

GROUP_LINK = os.environ.get("GROUP_LINK", "")
CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "")

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///toandaas_system.db")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
PORT = int(os.environ.get("PORT", "8000"))
