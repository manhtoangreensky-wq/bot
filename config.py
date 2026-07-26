"""
Cấu hình bot - chỉ đọc từ biến môi trường.

Không đặt token/API key thật trong file này. Hãy cấu hình trên Railway/Render/VPS
hoặc file .env cục bộ và tham khảo .env.example.
"""
import os

# Hệ thống sẽ tự động lấy Token từ biến môi trường
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("BOT_TOKEN", "")

# NOT the owner gate used by the running bot.
#
# bot.py owns authorisation: it builds ADMIN_IDS / OWNER_IDS from the same
# environment variables and every handler asks is_admin_user(). The list below
# is only read by handlers/admin_handler.py, which nothing in bot.py imports,
# so it is not wired into the live bot. It is kept so the handlers/ package
# still imports, and it reads the same environment variables on purpose: if it
# is ever wired up it must not become a second, divergent definition of owner.
# Anything that needs an owner check belongs in bot.py's is_admin_user().
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
