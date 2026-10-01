"""Regression for repeat clicks on Admin Ticket lead markers."""

from __future__ import annotations

import asyncio
import html
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


class _Message:
    def __init__(self):
        self.replies = []

    async def reply_text(self, *args, **kwargs):
        self.replies.append((args, kwargs))


class _Query:
    def __init__(self, data: str, user_id: int = 501):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = _Message()
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _load_actual_code():
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

    names = ("support_ticket_admin_keyboard", "handle_ticket_callback")
    namespace = {
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "html": html,
    }
    code = "\n".join(source_function(name) for name in names)
    exec(compile(code, str(bot_path), "exec"), namespace)

    ticket = {
        "id": 74,
        "ticket_code": "TA-TEST-74",
        "user_id": 900,
        "category": "lead_consulting",
        "status": "new",
        "assigned_admin_id": None,
        "admin_note": "",
    }
    updates = []
    edits = []
    clock = {"value": 0}

    def update_ticket(ticket_id, **fields):
        if int(ticket_id) != ticket["id"]:
            return None
        updates.append(dict(fields))
        ticket.update(fields)
        return dict(ticket)

    async def safe_edit_or_send(_query, text, reply_markup=None, **_kwargs):
        edits.append((text, reply_markup))

    def now_text():
        clock["value"] += 1
        return f"test-time-{clock['value']}"

    namespace.update({
        "get_support_ticket": lambda ticket_id, *_args: dict(ticket) if int(ticket_id) == ticket["id"] else None,
        "update_support_ticket": update_ticket,
        "support_ticket_admin_text": lambda _ticket: "Admin lead ticket",
        "get_user_language": lambda _uid: "vi",
        "normalize_user_language": lambda language: language,
        "public_hub_copy": lambda _language: {
            "support_ticket_admin_only": "Admin only",
            "support_ticket_action_unsupported": "Unsupported",
        },
        "is_admin_user": lambda uid: uid in {501, 502},
        "safe_edit_or_send": safe_edit_or_send,
        "now_text": now_text,
    })
    return source, namespace, ticket, updates, edits


class SupportTicketLeadActionRepeatTests(unittest.TestCase):
    def setUp(self):
        self.source, self.ns, self.ticket, self.updates, self.edits = _load_actual_code()

    def _lead_callback(self, button_label: str) -> str:
        markup = self.ns["support_ticket_admin_keyboard"](self.ticket)
        callback_data = next(
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.text == button_label
        )
        routes = re.findall(
            r'(?m)^\s*tg_app\.add_handler\(CallbackQueryHandler\(handle_ticket_callback, pattern=r"([^\"]+)"\)\)',
            self.source,
        )
        self.assertEqual(len(routes), 1, "ticket callback handler should be registered exactly once")
        self.assertRegex(callback_data, routes[0])
        return callback_data

    def _click(self, callback_data: str, admin_id: int = 501):
        query = _Query(callback_data, admin_id)
        asyncio.run(self.ns["handle_ticket_callback"](
            SimpleNamespace(callback_query=query),
            SimpleNamespace(),
        ))
        return query

    def test_repeating_same_lead_marker_by_same_admin_is_idempotent(self):
        cases = (("📞 Cần liên hệ", "Cần liên hệ"), ("⭐ Lead tiềm năng", "Lead tiềm năng"))
        for button_label, marker in cases:
            with self.subTest(marker=marker):
                self.ticket.update(status="new", assigned_admin_id=None, admin_note="")
                self.updates.clear()
                callback_data = self._lead_callback(button_label)

                self._click(callback_data)
                self._click(callback_data)

                self.assertEqual(self.ticket["admin_note"].count(marker), 1)
                self.assertEqual(len(self.updates), 1)
                self.assertEqual(self.ticket["status"], "reviewing")
                self.assertEqual(self.ticket["assigned_admin_id"], 501)

    def test_new_marker_or_admin_keeps_event_and_assignment_semantics(self):
        contact = self._lead_callback("📞 Cần liên hệ")
        potential = self._lead_callback("⭐ Lead tiềm năng")

        self._click(contact, 501)
        self._click(contact, 501)
        self._click(potential, 501)
        self._click(potential, 502)

        self.assertEqual(self.ticket["admin_note"].count("Cần liên hệ"), 1)
        self.assertEqual(self.ticket["admin_note"].count("Lead tiềm năng"), 2)
        self.assertEqual(len(self.updates), 3)
        self.assertEqual(self.ticket["status"], "reviewing")
        self.assertEqual(self.ticket["assigned_admin_id"], 502)

    def test_same_marker_restores_changed_status_and_assignee_without_duplicate_note(self):
        callback_data = self._lead_callback("📞 Cần liên hệ")

        self._click(callback_data, 501)
        self.ticket.update(status="waiting_provider", assigned_admin_id=777)
        self._click(callback_data, 501)

        self.assertEqual(self.ticket["admin_note"].count("Cần liên hệ"), 1)
        self.assertEqual(len(self.updates), 2)
        self.assertEqual(self.ticket["status"], "reviewing")
        self.assertEqual(self.ticket["assigned_admin_id"], 501)


if __name__ == "__main__":
    unittest.main()
