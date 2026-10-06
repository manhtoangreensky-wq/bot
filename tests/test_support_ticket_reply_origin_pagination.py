"""Regression for the admin Reply prompt Back target on a filtered ticket page."""

import asyncio
import html
import re
import time
import uuid
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


class _Application:
    def __init__(self):
        self.handlers = []

    def add_handler(self, handler):
        self.handlers.append(handler)


class _Query:
    def __init__(self, data, user_id):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.answers = 0
        self.reply_markups = []

    async def answer(self, *_args, **_kwargs):
        self.answers += 1


def _actual_function_source(source, name):
    lines = source.splitlines()
    start = next(i for i, line in enumerate(lines) if re.match(rf"^(?:async )?def {re.escape(name)}\(", line))
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"^(?:async )?def \w+\(", lines[i])), len(lines))
    return "\n".join(lines[start:end]) + "\n"


def _load_actual_function(source, name, namespace):
    exec(compile(_actual_function_source(source, name), f"bot.py:{name}", "exec"), namespace)
    return namespace[name]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def _fixture():
    admin_id, ticket_id = 4242, 9006
    ticket = {
        "id": ticket_id,
        "ticket_code": "TKT-9006",
        "category": "general_support",
        "priority": "high",
        "status": "new",
        "message": "Fixture ticket; no persistent record.",
        "created_at": "2026-10-01",
        "user_id": "fixture-customer",
    }
    page_tickets = [
        {"id": 9001 + i, "ticket_code": f"TKT-{9001 + i}", "category": "general_support", "user_id": "fixture-customer"}
        for i in range(6)
    ]
    edits, list_calls, user_pending = [], [], {}

    async def safe_edit_or_send(query, _text, *, reply_markup=None, **_kwargs):
        query.reply_markups.append(reply_markup)
        return None

    def list_support_tickets(**kwargs):
        list_calls.append(kwargs)
        return page_tickets

    namespace = {
        "html": html,
        "time": time,
        "uuid": uuid,
        "USER_PENDING": user_pending,
        "SUPPORT_TICKET_TTL_SECONDS": 600,
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "normalize_user_language": lambda value: value,
        "get_user_language": lambda _uid: "vi",
        "public_hub_copy": lambda _lang: {
            "support_ticket_admin_only": "admin only",
            "support_ticket_action_unsupported": "unsupported",
        },
        "is_admin_user": lambda uid: uid == admin_id,
        "support_category_label": lambda category: category,
        "list_support_tickets": list_support_tickets,
        "get_support_ticket": lambda value, *_args, **_kwargs: ticket if int(value) == ticket_id else None,
        "support_ticket_admin_text": lambda _ticket: "ticket detail",
        "safe_edit_or_send": safe_edit_or_send,
    }
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
    for name in (
        "support_ticket_pending_key",
        "set_support_ticket_pending",
        "get_support_ticket_pending",
        "clear_support_ticket_pending",
        "support_ticket_admin_keyboard",
        "support_admin_list_payload",
        "handle_support_pending_input",
        "handle_ticket_callback",
    ):
        _load_actual_function(source, name, namespace)

    registrations = [
        line.strip()
        for line in _actual_function_source(source, "lifespan").splitlines()
        if "tg_app.add_handler(CallbackQueryHandler(handle_ticket_callback," in line
    ]
    assert len(registrations) == 1
    application = _Application()
    exec(
        compile(registrations[0], "bot.py:ticket-registration", "exec"),
        {**namespace, "tg_app": application, "CallbackQueryHandler": _CallbackQueryHandler},
    )
    assert len(application.handlers) == 1
    handler = application.handlers[0]
    assert handler.callback is namespace["handle_ticket_callback"]

    async def press(data):
        query = _Query(data, admin_id)
        await handler.callback(SimpleNamespace(callback_query=query), SimpleNamespace())
        return query

    return namespace, handler, press, list_calls, admin_id, ticket_id


class AdminTicketReplyOriginPaginationTest(unittest.TestCase):
    def test_reply_prompt_back_returns_to_the_same_filtered_page(self):
        namespace, handler, press, list_calls, _admin_id, ticket_id = _fixture()
        self.assertIsNotNone(handler.pattern.match("ticket|reply|9006|high|6"))

        _list_text, list_markup = namespace["support_admin_list_payload"]("high", 6)
        detail_callback = next(cb for cb in _callbacks(list_markup) if cb.startswith(f"ticket|av|{ticket_id}|"))
        detail = asyncio.run(press(detail_callback))
        self.assertEqual(detail.answers, 1)
        detail_markup = detail.reply_markups[-1]
        reply_callback = next(cb for cb in _callbacks(detail_markup) if cb.startswith(f"ticket|reply|{ticket_id}"))
        self.assertEqual(reply_callback, "ticket|reply|9006|high|6")

        prompt = asyncio.run(press(reply_callback))
        self.assertEqual(prompt.answers, 1)
        pending = namespace["get_support_ticket_pending"](4242)
        self.assertEqual((pending["source"], pending["list_offset"]), ("high", "6"))
        back_callback = next(cb for cb in _callbacks(prompt.reply_markups[-1]) if cb.startswith("ticket|av|9006|"))
        self.assertEqual(back_callback, "ticket|av|9006|high|6")

        returned_detail = asyncio.run(press(back_callback))
        self.assertIsNone(namespace["get_support_ticket_pending"](4242))
        list_callback = next(cb for cb in _callbacks(returned_detail.reply_markups[-1]) if cb.startswith("ticket|al|"))
        self.assertEqual(list_callback, "ticket|al|high|6")
        asyncio.run(press(list_callback))
        self.assertEqual(list_calls[-1], {"limit": 6, "offset": 6, "high_priority": True})

    def test_reply_preview_back_returns_to_the_same_filtered_page_without_sending(self):
        namespace, handler, press, list_calls, admin_id, ticket_id = _fixture()
        _list_text, list_markup = namespace["support_admin_list_payload"]("high", 6)
        detail_callback = next(cb for cb in _callbacks(list_markup) if cb.startswith(f"ticket|av|{ticket_id}|"))
        detail = asyncio.run(press(detail_callback))
        reply_callback = next(cb for cb in _callbacks(detail.reply_markups[-1]) if cb.startswith(f"ticket|reply|{ticket_id}"))
        prompt = asyncio.run(press(reply_callback))

        replies = []

        async def reply_text(text, **kwargs):
            replies.append((text, kwargs))

        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=admin_id),
            message=SimpleNamespace(text="Fixture reply text", reply_text=reply_text),
        )
        send_attempts = []
        context = SimpleNamespace(bot=SimpleNamespace(send_message=lambda **kwargs: send_attempts.append(kwargs)))
        handled = asyncio.run(namespace["handle_support_pending_input"](update, context))
        self.assertTrue(handled)
        self.assertEqual(len(replies), 1)
        preview_markup = replies[-1][1]["reply_markup"]
        back_callback = next(cb for cb in _callbacks(preview_markup) if cb.startswith(f"ticket|av|{ticket_id}|"))
        self.assertEqual(back_callback, "ticket|av|9006|high|6")

        returned_detail = asyncio.run(press(back_callback))
        self.assertIsNone(namespace["get_support_ticket_pending"](admin_id))
        list_callback = next(cb for cb in _callbacks(returned_detail.reply_markups[-1]) if cb.startswith("ticket|al|"))
        self.assertEqual(list_callback, "ticket|al|high|6")
        asyncio.run(press(list_callback))
        self.assertEqual(list_calls[-1], {"limit": 6, "offset": 6, "high_priority": True})
        self.assertEqual(send_attempts, [])


if __name__ == "__main__":
    unittest.main()
