import asyncio
import html
import unittest
from pathlib import Path
from types import SimpleNamespace


class _Button:
    def __init__(self, text, callback_data):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class SupportLeadCallbackIdempotencyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source_path = Path(__file__).resolve().parents[1] / "bot.py"
        cls.source = source_path.read_text(encoding="utf-8")

    def setUp(self):
        self.ticket = {
            "id": 72,
            "category": "lead_consulting",
            "ticket_code": "LEAD-000072",
            "user_id": "lead-72",
            "admin_note": "Existing note",
            "status": "open",
        }
        self.updates = []
        self.answers = []
        self.rendered_markups = []
        self.clock = iter(["12:00:01", "12:00:02", "12:00:03", "12:00:04"])

        keyboard_start = self.source.index("def support_ticket_admin_keyboard")
        keyboard_end = self.source.index("def support_admin_list_payload", keyboard_start)
        keyboard_namespace = {
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
        }
        exec(self.source[keyboard_start:keyboard_end], keyboard_namespace)
        self.keyboard = keyboard_namespace["support_ticket_admin_keyboard"]

        handler_start = self.source.index("async def handle_ticket_callback")
        handler_end = self.source.index("async def handle_admin_help_callback", handler_start)
        handler_namespace = {
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "html": html,
            "normalize_user_language": lambda _uid: "vi",
            "get_user_language": lambda _uid: "vi",
            "public_hub_copy": lambda _lang: {"support_ticket_admin_only": "admin only"},
            "is_admin_user": lambda uid: int(uid) == 42,
            "get_support_ticket": self._get_ticket,
            "now_text": lambda: next(self.clock),
            "update_support_ticket": self._update_ticket,
            "safe_edit_or_send": self._safe_edit_or_send,
            "support_ticket_admin_text": lambda _ticket: "ticket detail",
            "support_ticket_admin_keyboard": self.keyboard,
        }
        exec(self.source[handler_start:handler_end], handler_namespace)
        self.handler = handler_namespace["handle_ticket_callback"]

    def _get_ticket(self, ticket_id):
        return self.ticket if int(ticket_id) == self.ticket["id"] else None

    def _update_ticket(self, ticket_id, **fields):
        self.updates.append((ticket_id, fields.copy()))
        self.ticket.update(fields)
        return self.ticket

    async def _safe_edit_or_send(self, _query, _text, reply_markup=None, **_kwargs):
        self.rendered_markups.append(reply_markup)

    async def _click(self, action):
        class _Message:
            async def reply_text(self, *_args, **_kwargs):
                return None

        class _Query:
            data = f"ticket|lead|72|{action}"
            from_user = SimpleNamespace(id=42)
            message = _Message()

            async def answer(inner_self, *args, **kwargs):
                self.answers.append((args, kwargs))

        update = SimpleNamespace(callback_query=_Query())
        await self.handler(update, SimpleNamespace(bot=object()))

    def test_visible_lead_actions_are_registered_and_repeat_is_idempotent(self):
        self.assertIn(
            'CallbackQueryHandler(handle_ticket_callback, pattern=r"^ticket\\|")',
            self.source,
        )
        keyboard = self.keyboard(self.ticket)
        callbacks = [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data.startswith("ticket|lead|")
        ]
        self.assertEqual(
            callbacks,
            ["ticket|lead|72|contact", "ticket|lead|72|potential"],
        )

        async def replay():
            await self._click("contact")
            await self._click("contact")

        asyncio.run(replay())

        self.assertEqual(self.ticket["admin_note"].count("Cần liên hệ"), 1)
        self.assertIn("Existing note", self.ticket["admin_note"])
        self.assertEqual(self.ticket["status"], "reviewing")
        self.assertEqual(self.ticket["assigned_admin_id"], 42)

    def test_distinct_lead_action_is_recorded_once_and_preserves_prior_action(self):
        async def replay():
            await self._click("contact")
            await self._click("potential")
            await self._click("potential")

        asyncio.run(replay())

        self.assertEqual(self.ticket["admin_note"].count("Cần liên hệ"), 1)
        self.assertEqual(self.ticket["admin_note"].count("Lead tiềm năng"), 1)
        self.assertIn("Existing note", self.ticket["admin_note"])
        self.assertEqual(self.ticket["status"], "reviewing")
        self.assertEqual(self.ticket["assigned_admin_id"], 42)


if __name__ == "__main__":
    unittest.main()
