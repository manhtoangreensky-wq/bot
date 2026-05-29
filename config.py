"""
Cấu hình bot - Chỉnh sửa thông tin tại đây
"""

# ─── BẮT BUỘC PHẢI ĐIỀN ────────────────────────────────────────
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Token từ @BotFather

# ─── TÙY CHỌN ──────────────────────────────────────────────────
# ID của admin (lấy từ @userinfobot)
ADMIN_IDS = [123456789]  # Thay bằng Telegram ID của bạn

# Tên bot hiển thị
BOT_NAME = "HoTroToanBot"
BOT_USERNAME = "hotrotoanbot"

# Link group/channel của bạn (nếu có)
GROUP_LINK = "https://t.me/your_group"
CHANNEL_LINK = "https://t.me/your_channel"

# Database (SQLite mặc định, có thể đổi sang PostgreSQL)
DATABASE_URL = "sqlite:///hotrotoanbot.db"

# Webhook (để trống nếu dùng polling)
WEBHOOK_URL = ""
PORT = 8443
