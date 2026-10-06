"""Regression for stale admin ticket-note callbacks."""

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


def _load_ticket_note_code():
    bot_path = Path(__file__).resolve().parents[1] / "bot.py"
    source = bot_path.read_text(encoding="utf-8")
    def source_function(name):
        match = re.search(rf"(?m)^(?:async )?def {re.escape(name)}\b", source)
        if match is None:
            raise AssertionError(f"Actual top-level function is missing: {name}")
        following = re.search(
            r"(?m)^(?:async )?def [A-Za-z_][A-Za-z_0-9]*\s*\(",
            source[match.end():],
        )
        end = match.end() + following.start() if following else len(source)
        return source[match.start():end]

    keyboard = source_function("support_ticket_admin_keyboard")
    handler = source_function("handle_ticket_callback")

    namespace = {
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
    }
    exec(compile(keyboard + "\n" + handler, str(bot_path), "exec"), namespace)
    return source, namespace


class SupportTicketNoteStaleGuardTests(unittest.TestCase):
    def setUp(self):
        self.source, self.namespace = _load_ticket_note_code()
        self.pending = []
        self.edits = []

        async def safe_edit(_query, text, reply_markup=None, **_kwargs):
            self.edits.append((text, reply_markup))

        self.namespace.update(
            get_support_ticket=lambda _ticket_id: None,
            set_support_ticket_pending=lambda *args, **kwargs: self.pending.append((args, kwargs)),
            safe_edit_or_send=safe_edit,
            get_user_language=lambda _uid: "vi",
            normalize_user_language=lambda language: language,
            public_hub_copy=lambda _language: {},
            is_admin_user=lambda _uid: True,
        )

    def _note_callback(self, ticket_id: int) -> str:
        keyboard = self.namespace["support_ticket_admin_keyboard"]({"id": ticket_id})
        callback_data = next(
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if button.text == "📌 Ghi chú admin"
        )
        self.assertEqual(callback_data, f"ticket|note|{ticket_id}|new|0")
        routes = re.findall(
            r'(?m)^\s*tg_app\.add_handler\(CallbackQueryHandler\(handle_ticket_callback, pattern=r"([^"]+)"\)\)',
            self.source,
        )
        self.assertEqual(len(routes), 1, "ticket handler should be registered exactly once")
        self.assertRegex(callback_data, routes[0])
        return callback_data

    def _run_note_callback(self, query: _Query):
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace()
        asyncio.run(self.namespace["handle_ticket_callback"](update, context))

    def test_stale_keyboard_does_not_create_pending_state_or_prompt(self):
        query = _Query(self._note_callback(74))

        self._run_note_callback(query)

        self.assertEqual(self.pending, [])
        self.assertEqual(self.edits, [])
        self.assertEqual(query.answers[-1], (("Không tìm thấy ticket.",), {"show_alert": True}))

    def test_existing_ticket_keeps_current_note_prompt_and_pending_state(self):
        ticket = {"id": 74, "ticket_code": "TA-TEST-74"}
        self.namespace["get_support_ticket"] = lambda ticket_id: ticket if ticket_id == 74 else None
        query = _Query(self._note_callback(74))

        self._run_note_callback(query)

        self.assertEqual(
            self.pending,
            [((501, "admin_note_input"), {"ticket_id": 74, "source": "new", "list_offset": 0})],
        )
        self.assertEqual(len(self.edits), 1)
        self.assertIn("📌 Nhập ghi chú nội bộ", self.edits[0][0])


if __name__ == "__main__":
    unittest.main()
