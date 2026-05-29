"""
Handler: Admin Commands
"""
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_IDS
import logging

logger = logging.getLogger(__name__)

# Lưu user IDs đơn giản (sau này có thể dùng database)
user_db = set()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gửi broadcast đến tất cả users - chỉ admin"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Bạn không có quyền dùng lệnh này!")
        return

    if not context.args:
        await update.message.reply_text(
            "📢 Cách dùng: /broadcast <nội dung tin nhắn>\n"
            "Ví dụ: /broadcast Chào mừng tính năng mới! 🎉"
        )
        return

    message = " ".join(context.args)
    success = 0
    failed = 0

    broadcast_text = f"📢 *Thông báo từ Bot:*\n\n{message}"

    for user_id in user_db:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=broadcast_text,
                parse_mode="Markdown"
            )
            success += 1
        except Exception as e:
            logger.error(f"Failed to send to {user_id}: {e}")
            failed += 1

    await update.message.reply_text(
        f"✅ Broadcast hoàn tất!\n"
        f"• Thành công: {success}\n"
        f"• Thất bại: {failed}\n"
        f"• Tổng users: {len(user_db)}"
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xem thống kê bot - chỉ admin"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Bạn không có quyền dùng lệnh này!")
        return

    stats_text = f"""
📊 *Thống kê HoTroToanBot*

👥 Tổng users: {len(user_db)}
🤖 Bot: @hotrotoanbot
📅 Trạng thái: Đang hoạt động ✅

_Tip: Kết nối database để lưu stats chi tiết hơn_
"""
    await update.message.reply_text(stats_text, parse_mode="Markdown")


def track_user(user_id: int):
    """Ghi nhận user mới"""
    user_db.add(user_id)
