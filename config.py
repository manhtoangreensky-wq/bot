"""
Cấu hình bot - Chỉnh sửa thông tin tại đây
"""
import os

# Hệ thống sẽ tự động lấy Token này để chạy
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8323884388:AAGtcyKZ3bzkK-Bdxc6-61l4gdD9Y6FE23g")

ADMIN_IDS = [123456789]

BOT_NAME = "HoTroToanBot"
BOT_USERNAME = "hotrotoanbot"

GROUP_LINK = "https://t.me/your_group"
CHANNEL_LINK = "https://t.me/your_channel"

DATABASE_URL = "sqlite:///hotrotoanbot.db"
WEBHOOK_URL = ""
PORT = 8443