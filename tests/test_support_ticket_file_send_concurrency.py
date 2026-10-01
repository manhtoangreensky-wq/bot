from __future__ import annotations

import asyncio
import html
import re
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _source_function(name):
    match = re.search(rf"(?m)^(?:async )?def {re.escape(name)}\b", BOT_SOURCE)
    if not match:
        raise AssertionError(f"Missing source function: {name}")
    following = re.search(
        r"(?m)^(?:async )?def [A-Za-z_][A-Za-z_0-9]*\s*\(",
        BOT_SOURCE[match.end():],
    )
    end = match.end() + following.start() if following else len(BOT_SOURCE)
    return BOT_SOURCE[match.start():end]


class _Button:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class _Message:
    def __init__(self):
        self.chat_id = 501
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((str(text), kwargs))


class _Query:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(id=501)
        self.message = _Message()
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


class _FakeBot:
    def __init__(self, fail=False):
        self.fail = fail
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.sent = []

    async def send_document(self, **kwargs):
        self.sent.append(kwargs)
        self.started.set()
        await self.release.wait()
        if self.fail:
            raise RuntimeError("simulated Telegram send failure")

    async def send_photo(self, **kwargs):
        self.sent.append(kwargs)
        self.started.set()
        await self.release.wait()
        if self.fail:
            raise RuntimeError("simulated Telegram send failure")


class SupportTicketFileSendConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.ticket = {
            "id": 74,
            "user_id": 9001,
            "ticket_code": "T-74",
            "category": "other",
            "attachment_file_id": "file-74",
            "attachment_type": "document",
        }
        self.user_pending = {}
        self.get_ticket = lambda ticket_id: (
            self.ticket if int(ticket_id) == self.ticket["id"] else None
        )
        self.namespace = {
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "USER_PENDING": self.user_pending,
            "html": html,
            "logger": SimpleNamespace(warning=lambda *args, **kwargs: None),
            "normalize_user_language": lambda language: language,
            "get_user_language": lambda uid: "vi",
            "public_hub_copy": lambda language: {
                "support_ticket_admin_only": "Chỉ dành cho admin."
            },
            "is_admin_user": lambda uid: uid == 501,
            "get_support_ticket": self.get_ticket,
        }
        for name in ("support_ticket_admin_keyboard", "handle_ticket_callback"):
            exec(
                compile(_source_function(name), str(ROOT / "bot.py"), "exec"),
                self.namespace,
            )
        self.handler = self.namespace["handle_ticket_callback"]

    def _file_callback(self):
        keyboard = self.namespace["support_ticket_admin_keyboard"](self.ticket)
        callbacks = [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if button.text == "📎 Xem file đính kèm"
        ]
        self.assertEqual(callbacks, ["ticket|file|74"])
        routes = re.findall(
            r'(?m)^\s*tg_app\.add_handler\(CallbackQueryHandler\(handle_ticket_callback, pattern=r"([^"]+)"\)\)',
            BOT_SOURCE,
        )
        self.assertEqual(routes, [r"^ticket\|"])
        self.assertRegex(callbacks[0], routes[0])
        return callbacks[0]

    def _run(self, query, bot):
        update = SimpleNamespace(callback_query=query)
        return asyncio.run(self.handler(update, SimpleNamespace(bot=bot)))

    def test_concurrent_file_callback_only_sends_once_and_alerts_duplicate(self):
        callback_data = self._file_callback()
        bot = _FakeBot()
        first_query = _Query(callback_data)
        duplicate = _Query(callback_data)
        unrelated_state = {"pending_action": "support_ticket", "step": "awaiting_message"}
        self.user_pending["support_ticket:501"] = unrelated_state

        async def scenario():
            first = asyncio.create_task(
                self.handler(
                    SimpleNamespace(callback_query=first_query),
                    SimpleNamespace(bot=bot),
                )
            )
            await asyncio.wait_for(bot.started.wait(), timeout=1)
            second = asyncio.create_task(
                self.handler(
                    SimpleNamespace(callback_query=duplicate),
                    SimpleNamespace(bot=bot),
                )
            )
            await asyncio.sleep(0.01)
            bot.release.set()
            await asyncio.gather(first, second)

        asyncio.run(scenario())

        self.assertEqual(len(bot.sent), 1)
        self.assertEqual(
            first_query.answers,
            [(("Đang gửi file đính kèm...",), {"show_alert": False})],
        )
        self.assertEqual(
            duplicate.answers,
            [(("File đính kèm đang được gửi. Vui lòng chờ.",), {"show_alert": True})],
        )
        self.assertNotIn("support_ticket_file_inflight:501:74", self.user_pending)
        self.assertIs(self.user_pending["support_ticket:501"], unrelated_state)

    def test_sequential_file_reopen_still_sends_again(self):
        callback_data = self._file_callback()
        bot = _FakeBot()
        bot.release.set()

        self._run(_Query(callback_data), bot)
        self._run(_Query(callback_data), bot)

        self.assertEqual(len(bot.sent), 2)
        self.assertNotIn("support_ticket_file_inflight:501:74", self.user_pending)

    def test_photo_attachment_keeps_photo_send_path(self):
        callback_data = self._file_callback()
        self.ticket["attachment_type"] = "photo"
        bot = _FakeBot()
        bot.release.set()

        self._run(_Query(callback_data), bot)

        self.assertEqual(len(bot.sent), 1)
        self.assertEqual(bot.sent[0]["photo"], "file-74")
        self.assertNotIn("document", bot.sent[0])

    def test_stale_file_callback_answers_once_without_sending(self):
        callback_data = self._file_callback()
        self.namespace["get_support_ticket"] = lambda _ticket_id: None
        bot = _FakeBot()
        query = _Query(callback_data)

        self._run(query, bot)

        self.assertEqual(bot.sent, [])
        self.assertEqual(
            query.answers,
            [(("Ticket chưa có file đính kèm.",), {"show_alert": True})],
        )

    def test_non_admin_file_callback_keeps_admin_only_guard(self):
        callback_data = self._file_callback()
        self.namespace["is_admin_user"] = lambda _uid: False
        bot = _FakeBot()
        query = _Query(callback_data)

        self._run(query, bot)

        self.assertEqual(bot.sent, [])
        self.assertEqual(
            query.answers,
            [(("Chỉ dành cho admin.",), {"show_alert": True})],
        )

    def test_failed_file_send_releases_guard_and_can_be_retried(self):
        callback_data = self._file_callback()
        failed_bot = _FakeBot(fail=True)
        failed_bot.release.set()
        failed_query = _Query(callback_data)

        self._run(failed_query, failed_bot)

        self.assertNotIn("support_ticket_file_inflight:501:74", self.user_pending)
        self.assertEqual(len(failed_query.message.replies), 1)
        self.assertIn("Không gửi lại được file", failed_query.message.replies[0][0])

        retry_bot = _FakeBot()
        retry_bot.release.set()
        self._run(_Query(callback_data), retry_bot)

        self.assertEqual(len(retry_bot.sent), 1)
        self.assertNotIn("support_ticket_file_inflight:501:74", self.user_pending)


if __name__ == "__main__":
    unittest.main()
