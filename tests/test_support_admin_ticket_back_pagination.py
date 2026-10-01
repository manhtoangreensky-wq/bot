"""Regression contract for returning to the originating admin ticket page."""

import asyncio
import html
import re
import unittest
from pathlib import Path
from types import SimpleNamespace


class _Button:
    def __init__(self, text, callback_data=None, url=None):
        self.text, self.callback_data, self.url = text, callback_data, url


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class _CallbackQueryHandler:
    def __init__(self, callback, pattern):
        self.callback, self.pattern = callback, re.compile(pattern)


class _FakeApplication:
    def __init__(self):
        self.handlers = []

    def add_handler(self, handler):
        self.handlers.append(handler)


def _actual_function_source(source, name):
    lines = source.splitlines()
    start = next(i for i, line in enumerate(lines) if re.match(rf"^(?:async )?def {re.escape(name)}\(", line))
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"^(?:async )?def \w+\(", lines[i])), len(lines))
    return "\n".join(lines[start:end]) + "\n"


def _load_actual_function(source, name, namespace):
    exec(compile(_actual_function_source(source, name), "bot.py", "exec"), namespace)
    return namespace[name]


class _FakeQuery:
    def __init__(self, data, user_id):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace()
        self.reply_markups = []

    async def answer(self, *_args, **_kwargs):
        return None


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


class AdminTicketBackPaginationTest(unittest.TestCase):
    def test_detail_back_restores_originating_list_offset(self):
        admin_id, ticket_id = 4242, 9006
        ticket = {
            "id": ticket_id,
            "ticket_code": "TKT-9006",
            "category": "general_support",
            "priority": "normal",
            "status": "new",
            "message": "Fixture ticket; no persistent record.",
            "created_at": "2026-09-27",
            "user_id": "fixture-customer",
        }
        page_tickets = [
            {"id": 9001 + i, "ticket_code": f"TKT-{9001 + i}", "category": "general_support", "user_id": "fixture-customer"}
            for i in range(6)
        ]

        async def capture_edit(query, *_args, **kwargs):
            query.reply_markups.append(kwargs.get("reply_markup"))

        listed_offsets = []

        def fake_list_support_tickets(**kwargs):
            listed_offsets.append(kwargs["offset"])
            return page_tickets

        namespace = {
            "html": html,
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "normalize_user_language": lambda lang: lang,
            "get_user_language": lambda _uid: "vi",
            "is_admin_user": lambda _uid: True,
            "public_hub_copy": lambda _lang: {"support_ticket_admin_only": "admin only", "support_ticket_action_unsupported": "unsupported"},
            "support_category_label": lambda category: category,
            "list_support_tickets": fake_list_support_tickets,
            "get_support_ticket": lambda *_args, **_kwargs: ticket,
            "support_ticket_admin_text": lambda _ticket: "ticket detail",
            "safe_edit_or_send": capture_edit,
        }
        source_path = Path(__file__).resolve().parents[1] / "bot.py"
        source = source_path.read_text(encoding="utf-8")
        list_payload = _load_actual_function(source, "support_admin_list_payload", namespace)
        _load_actual_function(source, "support_ticket_admin_keyboard", namespace)
        ticket_callback = _load_actual_function(source, "handle_ticket_callback", namespace)

        lifecycle_source = _actual_function_source(source, "lifespan")
        registration = [line.strip() for line in lifecycle_source.splitlines() if "tg_app.add_handler(CallbackQueryHandler(handle_ticket_callback," in line]
        self.assertEqual(len(registration), 1)
        application = _FakeApplication()
        exec(compile(registration[0], "bot.py", "exec"), {**namespace, "tg_app": application, "CallbackQueryHandler": _CallbackQueryHandler})
        self.assertEqual(len(application.handlers), 1)
        self.assertIs(application.handlers[0].callback, ticket_callback)
        self.assertIsNotNone(application.handlers[0].pattern.match("ticket|av|9006|new|6"))

        async def press(data):
            query = _FakeQuery(data, admin_id)
            await ticket_callback(SimpleNamespace(callback_query=query), SimpleNamespace())
            return query

        for offset, expected in ((0, "ticket|al|new|0"), (6, "ticket|al|new|6")):
            list_text, list_markup = list_payload("new", offset)
            self.assertIn("TKT-9006", list_text)
            open_callback = next(cb for cb in _callbacks(list_markup) if cb.startswith(f"ticket|av|{ticket_id}|"))
            detail_query = asyncio.run(press(open_callback))
            detail_markup = detail_query.reply_markups[-1]
            back_callback = next(cb for cb in _callbacks(detail_markup) if cb.startswith("ticket|al|new|"))
            self.assertEqual(back_callback, expected)
            returned_query = asyncio.run(press(back_callback))
            self.assertEqual(listed_offsets[-1], offset)
            if offset:
                self.assertIn(f"ticket|av|{ticket_id}|new|{offset}", _callbacks(returned_query.reply_markups[-1]))

        legacy_query = asyncio.run(press(f"ticket|av|{ticket_id}|new"))
        legacy_back = next(cb for cb in _callbacks(legacy_query.reply_markups[-1]) if cb.startswith("ticket|al|new|"))
        self.assertEqual(legacy_back, "ticket|al|new|0")


if __name__ == "__main__":
    unittest.main()
