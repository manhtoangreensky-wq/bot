"""
Cấu hình bot - Chỉnh sửa thông tin tại đây
"""
import os

# ─── BẮT BUỘC PHẢI ĐIỀN ────────────────────────────────────────
BOT_TOKEN = os.environ.get("8323884388:AAHjlvtCW8fF-x9jT7YgJYn6UQawlomsSo4", "")

# ─── TÙY CHỌN ──────────────────────────────────────────────────
ADMIN_IDS = [123456789]  # Thay bằng ID từ @userinfobot

BOT_NAME = "HoTroToanBot"
BOT_USERNAME = "hotrotoanbot"

GROUP_LINK = "https://t.me/your_group"
CHANNEL_LINK = "https://t.me/your_channel"

DATABASE_URL = "sqlite:///hotrotoanbot.d