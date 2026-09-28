"""Focused regression for stale admin ticket "ask customer" callbacks."""

from __future__ import annotations

import asyncio
from pathlib import Path
import re
import unittest
from types import SimpleNamespace


class _Button:
    def __init__(self, text: str, callback_data: str):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class _Query:
    def __init__(self, data: str, user_id: int = 501):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace()
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _load_ticket_ask_code():
    bot_path = Path(__file__).resolve().parents[1] / "bot.py"
    source = bot_path.read_text(encoding="utf-8")
    keyboard_marker = 'def support_ticket_admin_keyboard(ticket: dict, source: str = "new") -> InlineKeyboardMarkup:'
    handler_marker = (
        "async def handle_ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):\n"
        "    query = update.callback_query"
    )
    keyboard_start = source.index(keyboard_marker)
    keyboard_end = source.index("\ndef support_admin_list_payload(", keyboard_start)
    handler_start = source.index(handler_marker)
    ask_start = source.index('    if action == "ask" and len(parts) >= 3:', handler_start)
    ask_end = source.index('    if action == "suggest" and len(parts) >= 4:', ask_start + 1)
    keyboard = source[keyboard_start:keyboard_end]
    ask_branch = source[ask_start:ask_end]

    namespace = {
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
    }
    exec(compile(keyboard + "\nasync def ask_callback_branch():\n" + ask_branch, str(bot_path), "exec"), namespace)
    return source, namespace


class SupportTicketAskStaleGuardTests(unittest.TestCase):
    def setUp(self):
        self.source, self.namespace = _load_ticket_ask_code()
        self.pending = []
        self.edits = []

        async def safe_edit(_query, text, reply_markup=None, **_kwargs):
            self.edits.append((text, reply_markup))

        self.namespace.update(
            get_support_ticket=lambda _ticket_id: None,
            set_support_ticket_pending=lambda *args, **kwargs: self.pending.append((args, kwargs)),
            safe_edit_or_send=safe_edit,
        )

    def _ask_callback(self, ticket_id: int) -> str:
        keyboard = self.namespace["support_ticket_admin_keyboard"]({"id": ticket_id})
        callback_data = next(
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if button.text == "👤 Hỏi thêm khách"
        )
        self.assertRegex(callback_data, rf"^ticket\|ask\|{ticket_id}$")
        route = re.search(
            r'CallbackQueryHandler\(handle_ticket_callback, pattern=r"([^"]+)"\)',
            self.source,
        )
        self.assertIsNotNone(route)
        if route is None:
            self.fail("ticket callback handler is not registered")
        self.assertRegex(callback_data, route.group(1))
        return callback_data

    def _run_ask_callback(self, query: _Query):
        self.namespace.update(action="ask", query=query, uid=query.from_user.id, parts=query.data.split("|"))

        async def run():
            await query.answer()
            await self.namespace["ask_callback_branch"]()

        asyncio.run(run())

    def test_stale_keyboard_does_not_create_pending_state_or_prompt(self):
        query = _Query(self._ask_callback(73))

        self._run_ask_callback(query)

        self.assertEqual(self.pending, [])
        self.assertEqual(self.edits, [])
        self.assertEqual(query.answers[-1], (("Không tìm thấy ticket.",), {"show_alert": True}))

    def test_existing_ticket_keeps_current_ask_prompt_and_pending_state(self):
        ticket = {"id": 73, "ticket_code": "TA-TEST-73"}
        self.namespace["get_support_ticket"] = lambda ticket_id: ticket if ticket_id == 73 else None
        query = _Query(self._ask_callback(73))

        self._run_ask_callback(query)

        self.assertEqual(
            self.pending,
            [((501, "admin_reply_input"), {"ticket_id": 73, "source": "new"})],
        )
        self.assertEqual(len(self.edits), 1)
        self.assertIn("👤 Nhập câu hỏi", self.edits[0][0])


if __name__ == "__main__":
    unittest.main()
