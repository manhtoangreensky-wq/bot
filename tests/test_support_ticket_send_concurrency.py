from __future__ import annotations

import asyncio
import html
import re
import time
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _source_function(name):
    match = re.search(rf"(?m)^(?:async )?def {re.escape(name)}\b", BOT_SOURCE)
    if not match:
        raise AssertionError(f"Missing source function: {name}")
    following = re.search(r"(?m)^(?:async )?def [A-Za-z_][A-Za-z_0-9]*\s*\(", BOT_SOURCE[match.end():])
    end = match.end() + following.start() if following else len(BOT_SOURCE)
    return BOT_SOURCE[match.start():end]


def _load_source_functions(namespace, *names):
    for name in names:
        exec(compile(_source_function(name), str(ROOT / "bot.py"), "exec"), namespace)


class _Button:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class _Query:
    def __init__(self, data, user_id=501):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = _Message()
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


class _Message:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((str(text), kwargs))


class _FakeBot:
    def __init__(self, fail=False):
        self.fail = fail
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.sent = []

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)
        self.started.set()
        await self.release.wait()
        if self.fail:
            raise RuntimeError("simulated Telegram send failure")


class SupportTicketSendConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.ticket = {
            "id": 74,
            "user_id": 9001,
            "ticket_code": "T-74",
            "category": "general_support",
            "message": "Khách cần hướng dẫn.",
            "status": "open",
            "admin_note": "",
        }
        self.user_pending = {}
        self.edits = []
        self.ticket_messages = []
        self.namespace = {
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "USER_PENDING": self.user_pending,
            "SUPPORT_TICKET_TTL_SECONDS": 900,
            "SUPPORT_CATEGORIES": {"general_support": "Hỗ trợ chung"},
            "html": html,
            "time": time,
            "logger": SimpleNamespace(warning=lambda *args, **kwargs: None),
            "normalize_user_language": lambda language: language,
            "get_user_language": lambda uid: "vi",
            "public_hub_copy": lambda language: {"support_ticket_admin_only": "Chỉ dành cho admin."},
            "is_admin_user": lambda uid: uid == 501,
            "support_suggested_reply": lambda category, variant, message: f"Gợi ý {variant}: {message}",
            "get_support_ticket": lambda ticket_id, user_id=None: self.ticket if int(ticket_id) == 74 else None,
            "update_support_ticket": self._update_ticket,
            "add_support_ticket_message": lambda *args: self.ticket_messages.append(args),
            "safe_edit_or_send": self._safe_edit,
            "support_ticket_admin_text": lambda ticket: "Ticket admin",
            "support_ticket_admin_keyboard": lambda ticket: _Markup([]),
        }
        _load_source_functions(
            self.namespace,
            "support_ticket_pending_key",
            "set_support_ticket_pending",
            "get_support_ticket_pending",
            "clear_support_ticket_pending",
            "handle_ticket_callback",
        )
        self.handler = self.namespace["handle_ticket_callback"]

    def _update_ticket(self, ticket_id, **fields):
        self.ticket.update(fields)
        return self.ticket

    async def _safe_edit(self, query, text, reply_markup=None, **kwargs):
        self.edits.append({"query": query, "text": text, "reply_markup": reply_markup})

    def _run(self, awaitable):
        return asyncio.run(awaitable)

    def _send_callback_data_from_suggestion(self):
        query = _Query("ticket|suggest|74|0")
        context = SimpleNamespace(bot=SimpleNamespace())
        self._run(self.handler(SimpleNamespace(callback_query=query), context))
        markup = self.edits[-1]["reply_markup"]
        callback_data = [
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.callback_data
        ]
        send_callbacks = [data for data in callback_data if data.startswith("ticket|send|")]
        self.assertEqual(send_callbacks, ["ticket|send|74"])
        routes = re.findall(
            r'(?m)^\s*tg_app\.add_handler\(CallbackQueryHandler\(handle_ticket_callback, pattern=r"([^"]+)"\)\)',
            BOT_SOURCE,
        )
        self.assertEqual(routes, [r"^ticket\|"])
        self.assertRegex(send_callbacks[0], routes[0])
        return send_callbacks[0]

    def test_concurrent_send_is_single_and_does_not_clear_replacement_preview(self):
        callback_data = self._send_callback_data_from_suggestion()
        uid = 501
        bot = _FakeBot()
        context = SimpleNamespace(bot=bot)
        first_query = _Query(callback_data)
        second_query = _Query(callback_data)
        first_state = self.namespace["get_support_ticket_pending"](uid)

        async def scenario():
            first = asyncio.create_task(
                self.handler(SimpleNamespace(callback_query=first_query), context)
            )
            await asyncio.wait_for(bot.started.wait(), timeout=1)
            self.namespace["set_support_ticket_pending"](
                uid, "admin_reply_preview", ticket_id=74, reply_text="Bản xem trước mới"
            )
            replacement_state = self.namespace["get_support_ticket_pending"](uid)
            second = asyncio.create_task(
                self.handler(SimpleNamespace(callback_query=second_query), context)
            )
            await asyncio.sleep(0.01)
            bot.release.set()
            await asyncio.gather(first, second)
            return replacement_state

        replacement_state = self._run(scenario())
        self.assertEqual(len(bot.sent), 1)
        self.assertEqual(len(self.ticket_messages), 1)
        self.assertEqual(
            self.namespace["get_support_ticket_pending"](uid), replacement_state
        )
        self.assertEqual(replacement_state["reply_text"], "Bản xem trước mới")
        self.assertTrue(
            any("Đang gửi" in args[0] for args, _kwargs in second_query.answers if args)
        )
        self.assertTrue(
            any(kwargs.get("show_alert") is True for _args, kwargs in second_query.answers)
        )
        self.assertIsNone(self.namespace["USER_PENDING"].get("support_ticket_send_inflight:501:74"))
        self.assertIsNotNone(first_state)

    def test_failed_send_releases_guard_and_keeps_preview_retryable(self):
        callback_data = self._send_callback_data_from_suggestion()
        uid = 501
        original_state = self.namespace["get_support_ticket_pending"](uid)
        bot = _FakeBot(fail=True)
        query = _Query(callback_data)
        context = SimpleNamespace(bot=bot)

        async def scenario():
            task = asyncio.create_task(
                self.handler(SimpleNamespace(callback_query=query), context)
            )
            await asyncio.wait_for(bot.started.wait(), timeout=1)
            bot.release.set()
            await task

        self._run(scenario())
        self.assertEqual(self.namespace["get_support_ticket_pending"](uid), original_state)
        self.assertEqual(original_state["step"], "admin_reply_preview")
        self.assertNotIn("support_ticket_send_inflight:501:74", self.user_pending)
        self.assertEqual(self.ticket_messages, [])
        self.assertTrue(any("không gửi được" in text.lower() for text, _ in query.message.replies))

        retry_bot = _FakeBot()
        retry_bot.release.set()
        retry_query = _Query(callback_data)
        self._run(
            self.handler(
                SimpleNamespace(callback_query=retry_query),
                SimpleNamespace(bot=retry_bot),
            )
        )
        self.assertEqual(len(retry_bot.sent), 1)
        self.assertEqual(len(self.ticket_messages), 1)
        self.assertIsNone(self.namespace["get_support_ticket_pending"](uid))


if __name__ == "__main__":
    unittest.main()
