import asyncio
import html
import unittest
from pathlib import Path
from types import SimpleNamespace


def load_support_ticket_callbacks():
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
    keyboard_start = source.index("def support_ticket_admin_keyboard(")
    keyboard_end = source.index("def support_admin_list_payload(", keyboard_start)
    handler_start = source.index("async def handle_ticket_callback(")
    handler_end = source.index("async def handle_admin_help_callback(", handler_start)

    ticket = {
        "id": 73,
        "ticket_code": "T-73",
        "user_id": "customer-73",
        "category": "other",
        "priority": "normal",
        "status": "open",
        "message": "Help needed",
    }
    notices = []
    edits = []
    callbacks = []

    def button(text, callback_data):
        return SimpleNamespace(text=text, callback_data=callback_data)

    def markup(rows):
        return SimpleNamespace(inline_keyboard=rows)

    class Query:
        data = ""
        from_user = SimpleNamespace(id=501)

        async def answer(self, *args, **kwargs):
            return None

    class Message:
        async def reply_text(self, text):
            notices.append(text)

    query = Query()
    query.message = Message()

    class Update:
        callback_query = query

    def get_ticket(ticket_id):
        if int(ticket_id) != ticket["id"]:
            return None
        return dict(ticket)

    def update_ticket(ticket_id, **fields):
        if int(ticket_id) != ticket["id"]:
            return None
        ticket.update(fields)
        return dict(ticket)

    async def safe_edit_or_send(query, text, reply_markup=None, **kwargs):
        edits.append((text, reply_markup))

    namespace = {
        "Update": Update,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "InlineKeyboardButton": button,
        "InlineKeyboardMarkup": markup,
        "get_support_ticket": get_ticket,
        "update_support_ticket": update_ticket,
        "support_ticket_admin_text": lambda current: current["status"],
        "support_ticket_admin_keyboard": None,
        "public_hub_copy": lambda _lang: {"support_ticket_admin_only": "admin only"},
        "normalize_user_language": lambda _lang: "vi",
        "get_user_language": lambda _uid: "vi",
        "is_admin_user": lambda _uid: True,
        "safe_edit_or_send": safe_edit_or_send,
        "html": html,
    }
    exec(source[keyboard_start:keyboard_end], namespace)
    exec(source[handler_start:handler_end], namespace)

    async def click(callback_data):
        callbacks.append(callback_data)
        query.data = callback_data
        await namespace["handle_ticket_callback"](Update(), SimpleNamespace())

    namespace["click"] = click
    namespace["ticket"] = ticket
    namespace["notices"] = notices
    namespace["edits"] = edits
    namespace["source"] = source
    return namespace


class SupportRefundPendingNoticeIdempotencyTests(unittest.TestCase):
    def test_notice_is_once_per_transition_into_refund_pending(self):
        namespace = load_support_ticket_callbacks()
        source = namespace["source"]
        registration = next(
            line
            for line in source.splitlines()
            if "CallbackQueryHandler(handle_ticket_callback," in line
        )
        self.assertIn(r'pattern=r"^ticket\|"', registration)

        ticket = namespace["ticket"]
        keyboard = namespace["support_ticket_admin_keyboard"](ticket)
        emitted = {
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
        }
        pending = "ticket|st|73|refund_pending"
        waiting = "ticket|st|73|waiting_provider"
        self.assertIn(pending, emitted)
        self.assertIn(waiting, emitted)

        async def replay_and_reenter():
            await namespace["click"](pending)
            await namespace["click"](pending)
            self.assertEqual(ticket["status"], "refund_pending")
            self.assertEqual(len(namespace["notices"]), 1)

            await namespace["click"](waiting)
            self.assertEqual(ticket["status"], "waiting_provider")
            self.assertEqual(len(namespace["notices"]), 1)

            await namespace["click"](pending)
            self.assertEqual(ticket["status"], "refund_pending")
            self.assertEqual(len(namespace["notices"]), 2)

        asyncio.run(replay_and_reenter())
        self.assertEqual(len(namespace["edits"]), 4)
        self.assertEqual(
            namespace["notices"],
            [
                "💰 Ticket đã được đánh dấu cần kiểm tra hoàn Xu/refund. Thao tác này chưa cộng hoặc trừ Xu.",
                "💰 Ticket đã được đánh dấu cần kiểm tra hoàn Xu/refund. Thao tác này chưa cộng hoặc trừ Xu.",
            ],
        )


if __name__ == "__main__":
    unittest.main()
