"""Regression contract for returning to a customer ticket detail screen."""

import asyncio
from types import SimpleNamespace

import bot


class _FakeQuery:
    def __init__(self, data, user_id):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace()

    async def answer(self, *_args, **_kwargs):
        return None


def test_customer_ticket_detail_back_releases_reply_and_attachment(monkeypatch, tmp_path):
    db_path = tmp_path / "ticket_detail_back.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "DB_STARTUP_BACKUP_PATHS", set())
    monkeypatch.setattr(bot, "get_user_language", lambda _user_id: "vi")
    bot.init_db()

    user = SimpleNamespace(id="ticket-back-owner", username="owner", first_name="Owner")
    ticket = bot.create_support_ticket(user, "general_support", "Nội dung ban đầu")

    async def fake_edit(*_args, **_kwargs):
        return SimpleNamespace()

    monkeypatch.setattr(bot, "safe_edit_or_send", fake_edit)

    async def press(data):
        await bot.handle_ticket_callback(
            SimpleNamespace(callback_query=_FakeQuery(data, user.id)),
            SimpleNamespace(),
        )

    class _Message:
        def __init__(self, text=""):
            self.text = text
            self.photo = []
            self.document = None

        async def reply_text(self, *_args, **_kwargs):
            return None

    bot.clear_support_ticket_pending(user.id)
    try:
        asyncio.run(press(f"ticket|reply_user|{ticket['id']}"))
        assert bot.get_support_ticket_pending(user.id)["step"] == "awaiting_ticket_reply"
        asyncio.run(press(f"ticket|pv|{ticket['id']}"))
        assert bot.get_support_ticket_pending(user.id) is None
        assert asyncio.run(bot.handle_support_ticket_pending_text(
            SimpleNamespace(effective_user=user, message=_Message("Tin nhắn bình thường")),
            SimpleNamespace(),
        )) is False

        asyncio.run(press(f"ticket|attach|{ticket['id']}"))
        assert bot.get_support_ticket_pending(user.id)["step"] == "awaiting_attachment"
        asyncio.run(press(f"ticket|pv|{ticket['id']}"))
        assert bot.get_support_ticket_pending(user.id) is None
        assert asyncio.run(bot.handle_support_ticket_attachment(
            SimpleNamespace(
                effective_user=user,
                message=_Message(),
            ),
            SimpleNamespace(),
        )) is False
    finally:
        bot.clear_support_ticket_pending(user.id)
