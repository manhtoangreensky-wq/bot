"""Regression contract for returning to an admin ticket detail screen."""

import asyncio
from types import SimpleNamespace

import bot


class _FakeQuery:
    def __init__(self, data, user_id):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace()
        self.answers = []

    async def answer(self, *_args, **_kwargs):
        self.answers.append((_args, _kwargs))


def test_admin_ticket_detail_back_releases_reply_note_and_suggestion(monkeypatch, tmp_path):
    db_path = tmp_path / "admin_ticket_detail_back.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    monkeypatch.setattr(bot, "DB_STARTUP_BACKUP_PATHS", set())
    monkeypatch.setattr(bot, "get_user_language", lambda _user_id: "vi")
    monkeypatch.setattr(bot, "is_admin_user", lambda _user_id: True)
    bot.init_db()

    customer = SimpleNamespace(id="ticket-back-customer", username="customer", first_name="Customer")
    ticket = bot.create_support_ticket(customer, "general_support", "Nội dung ban đầu")
    admin_id = "ticket-back-admin"

    async def fake_edit(*_args, **_kwargs):
        return SimpleNamespace()

    monkeypatch.setattr(bot, "safe_edit_or_send", fake_edit)

    async def press(data):
        query = _FakeQuery(data, admin_id)
        await bot.handle_ticket_callback(
            SimpleNamespace(callback_query=query),
            SimpleNamespace(),
        )
        return query

    class _Message:
        def __init__(self, text):
            self.text = text

        async def reply_text(self, *_args, **_kwargs):
            return None

    bot.clear_support_ticket_pending(admin_id)
    try:
        asyncio.run(press(f"ticket|reply|{ticket['id']}"))
        assert bot.get_support_ticket_pending(admin_id)["step"] == "admin_reply_input"
        asyncio.run(press(f"ticket|av|{ticket['id']}|new"))
        assert bot.get_support_ticket_pending(admin_id) is None
        assert asyncio.run(bot.handle_support_pending_input(
            SimpleNamespace(effective_user=SimpleNamespace(id=admin_id), message=_Message("Tin nhắn bình thường")),
            SimpleNamespace(),
        )) is False

        asyncio.run(press(f"ticket|note|{ticket['id']}"))
        assert bot.get_support_ticket_pending(admin_id)["step"] == "admin_note_input"
        asyncio.run(press(f"ticket|av|{ticket['id']}|new"))
        assert bot.get_support_ticket_pending(admin_id) is None
        assert asyncio.run(bot.handle_support_pending_input(
            SimpleNamespace(effective_user=SimpleNamespace(id=admin_id), message=_Message("Ghi chú ngoài ticket")),
            SimpleNamespace(),
        )) is False

        asyncio.run(press(f"ticket|suggest|{ticket['id']}|0"))
        assert bot.get_support_ticket_pending(admin_id)["step"] == "admin_reply_preview"
        asyncio.run(press(f"ticket|av|{ticket['id']}|new"))
        assert bot.get_support_ticket_pending(admin_id) is None
        stale_send = asyncio.run(press(f"ticket|send|{ticket['id']}"))
        assert stale_send.answers[-1][1].get("show_alert") is True
    finally:
        bot.clear_support_ticket_pending(admin_id)
