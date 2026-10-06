"""Admin note flow must keep the ticket list page it came from."""

import asyncio
import html
import re
import unittest
from pathlib import Path
from types import SimpleNamespace


class _Button:
    def __init__(self, text, callback_data=None):
        self.text, self.callback_data = text, callback_data


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class _Query:
    def __init__(self, data, user_id):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace()
        self.answers = []
        self.reply_markups = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


class _Message:
    def __init__(self, text):
        self.text = text
        self.reply_markups = []

    async def reply_text(self, *_args, **kwargs):
        self.reply_markups.append(kwargs.get("reply_markup"))


def _function_source(source, name):
    lines = source.splitlines()
    start = next(
        index for index, line in enumerate(lines)
        if re.match(rf"^(?:async )?def {re.escape(name)}\(", line)
    )
    end = next(
        (index for index in range(start + 1, len(lines))
         if re.match(r"^(?:async )?def \w+\(", lines[index])),
        len(lines),
    )
    return "\n".join(lines[start:end]) + "\n"


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


class AdminTicketNoteOriginPaginationTest(unittest.TestCase):
    def setUp(self):
        self.admin_id = 4242
        self.ticket = {
            "id": 9006,
            "ticket_code": "TKT-9006",
            "category": "general_support",
            "priority": "normal",
            "status": "new",
            "message": "Fixture ticket; no persistent record.",
            "created_at": "2026-09-27",
            "user_id": "fixture-customer",
            "admin_note": "",
        }
        self.pending = {}
        self.list_calls = []
        self.edits = []
        self.page_tickets = [
            {
                "id": 9001 + index,
                "ticket_code": f"TKT-{9001 + index}",
                "category": "general_support",
                "user_id": "fixture-customer",
            }
            for index in range(6)
        ]
        self.page_tickets[-1] = self.ticket

        async def safe_edit_or_send(query, text, **kwargs):
            markup = kwargs.get("reply_markup")
            query.reply_markups.append(markup)
            self.edits.append((text, markup))

        def list_support_tickets(**kwargs):
            self.list_calls.append(kwargs)
            return self.page_tickets

        def set_pending(user_id, step, **fields):
            self.pending[user_id] = {"step": step, **fields}

        def update_ticket(ticket_id, **fields):
            self.assertEqual(ticket_id, self.ticket["id"])
            self.ticket.update(fields)
            return dict(self.ticket)

        self.namespace = {
            "html": html,
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "normalize_user_language": lambda lang: lang,
            "get_user_language": lambda _uid: "vi",
            "is_admin_user": lambda _uid: True,
            "public_hub_copy": lambda _lang: {
                "support_ticket_admin_only": "Admin only",
                "support_ticket_action_unsupported": "Unsupported",
            },
            "support_category_label": lambda category: category,
            "support_ticket_admin_text": lambda _ticket: "Ticket detail",
            "list_support_tickets": list_support_tickets,
            "get_support_ticket": lambda ticket_id: (
                dict(self.ticket) if ticket_id == self.ticket["id"] else None
            ),
            "update_support_ticket": update_ticket,
            "clear_support_ticket_pending": lambda user_id: self.pending.pop(user_id, None),
            "get_support_ticket_pending": lambda user_id: self.pending.get(user_id),
            "set_support_ticket_pending": set_pending,
            "safe_edit_or_send": safe_edit_or_send,
            "now_text": lambda: "fixture-time",
        }
        source_path = Path(__file__).resolve().parents[1] / "bot.py"
        self.source = source_path.read_text(encoding="utf-8")
        for name in (
            "support_ticket_admin_keyboard",
            "support_admin_list_payload",
            "handle_ticket_callback",
            "handle_support_pending_input",
        ):
            code = _function_source(self.source, name)
            exec(compile(code, f"bot.py:{name}", "exec"), self.namespace)

    async def _press(self, data):
        query = _Query(data, self.admin_id)
        await self.namespace["handle_ticket_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace()
        )
        return query

    async def _open_high_priority_page_six(self):
        await self._press("ticket|al|high|6")
        list_markup = self.edits[-1][1]
        self.assertEqual(self.list_calls[-1]["offset"], 6)
        detail_callback = next(
            callback for callback in _callbacks(list_markup)
            if callback == "ticket|av|9006|high|6"
        )
        await self._press(detail_callback)
        return self.edits[-1][1]

    def test_emitted_note_button_preserves_originating_list_filter_and_page(self):
        detail_markup = asyncio.run(self._open_high_priority_page_six())

        note_callback = next(
            callback for callback in _callbacks(detail_markup)
            if callback.startswith("ticket|note|")
        )

        self.assertEqual(note_callback, "ticket|note|9006|high|6")

    def test_note_back_returns_to_originating_page_and_clears_pending_input(self):
        asyncio.run(self._open_high_priority_page_six())
        prompt = asyncio.run(self._press("ticket|note|9006|high|6"))

        self.assertEqual(
            self.pending[self.admin_id],
            {"step": "admin_note_input", "ticket_id": 9006, "source": "high", "list_offset": 6},
        )
        prompt_back = _callbacks(prompt.reply_markups[-1])[0]
        self.assertEqual(prompt_back, "ticket|av|9006|high|6")

        detail = asyncio.run(self._press(prompt_back))
        self.assertNotIn(self.admin_id, self.pending)
        list_back = next(
            callback for callback in _callbacks(detail.reply_markups[-1])
            if callback.startswith("ticket|al|")
        )
        self.assertEqual(list_back, "ticket|al|high|6")

    def test_saving_note_returns_to_detail_with_originating_page_context(self):
        asyncio.run(self._open_high_priority_page_six())
        asyncio.run(self._press("ticket|note|9006|high|6"))
        message = _Message("Ghi chú fixture")
        handled = asyncio.run(self.namespace["handle_support_pending_input"](
            SimpleNamespace(
                effective_user=SimpleNamespace(id=self.admin_id), message=message
            ),
            SimpleNamespace(),
        ))

        self.assertTrue(handled)
        self.assertIn("Ghi chú fixture", self.ticket["admin_note"])
        self.assertNotIn(self.admin_id, self.pending)
        detail_markup = message.reply_markups[-1]
        list_back = next(
            callback for callback in _callbacks(detail_markup)
            if callback.startswith("ticket|al|")
        )
        self.assertEqual(list_back, "ticket|al|high|6")


if __name__ == "__main__":
    unittest.main()
