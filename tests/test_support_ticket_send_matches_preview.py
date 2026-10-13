"""Regression for stale support-ticket reply preview Send buttons."""

from __future__ import annotations

import html
from pathlib import Path
import re
import time
import unittest
import uuid
from types import SimpleNamespace


def _run_inert(coroutine):
    try:
        yielded = coroutine.send(None)
    except StopIteration as completed:
        return completed.value
    coroutine.close()
    raise AssertionError(f"No-I/O handler unexpectedly yielded: {yielded!r}")


class _Button:
    def __init__(self, text: str, callback_data: str):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class _Message:
    def __init__(self, text: str | None = None):
        self.text = text
        self.chat_id = 501
        self.replies = []

    async def reply_text(self, *args, **kwargs):
        self.replies.append((args, kwargs))


class _Query:
    def __init__(self, data: str, user_id: int = 501):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = _Message()
        self.answers = []
        self.events = []

    async def answer(self, *args, **kwargs):
        self.events.append("ack")
        self.answers.append((args, kwargs))


class _Bot:
    def __init__(self):
        self.sent = []
        self.failure = None
        self.events = []

    async def send_message(self, **kwargs):
        self.events.append("send")
        if self.failure is not None:
            raise self.failure
        self.sent.append(kwargs)


class _Logger:
    def warning(self, *_args, **_kwargs):
        pass


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

    names = (
        "support_ticket_pending_key",
        "set_support_ticket_pending",
        "get_support_ticket_pending",
        "clear_support_ticket_pending",
        "handle_support_pending_input",
        "handle_ticket_callback",
    )
    namespace = {
        "USER_PENDING": {},
        "SUPPORT_TICKET_TTL_SECONDS": 15 * 60,
        "time": time,
        "uuid": uuid,
        "html": html,
        "logger": _Logger(),
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
    }
    code = "\n".join(source_function(name) for name in names)
    exec(compile(code, str(bot_path), "exec"), namespace)

    ticket = {"id": 74, "ticket_code": "TA-TEST-74", "user_id": 900, "category": "general_support", "message": "Customer question"}
    bot = _Bot()
    edits = []
    sent_rows = []
    read_dispatch = []
    ticket_reads = []

    def get_language(_uid):
        return "vi"

    def get_ticket(ticket_id, *_args):
        ticket_reads.append(int(ticket_id))
        return dict(ticket) if int(ticket_id) == ticket["id"] else None

    async def read_only_thread(helper, *args, **kwargs):
        read_dispatch.append("language" if helper is get_language else "ticket")
        return helper(*args, **kwargs)

    def update_ticket(ticket_id, **fields):
        if int(ticket_id) != ticket["id"]:
            return None
        ticket.update(fields)
        return dict(ticket)

    async def safe_edit_or_send(_query, text, reply_markup=None, **_kwargs):
        edits.append((text, reply_markup))

    namespace.update({
        "asyncio": SimpleNamespace(to_thread=read_only_thread),
        "get_support_ticket": get_ticket,
        "update_support_ticket": update_ticket,
        "add_support_ticket_message": lambda *args: sent_rows.append(args),
        "support_suggested_reply": lambda _category, variant, _message: f"Suggested reply variant {variant}",
        "support_ticket_admin_text": lambda _ticket: "Admin ticket",
        "support_ticket_admin_keyboard": lambda _ticket, source="new", list_offset=0: _Markup([]),
        "get_user_language": get_language,
        "normalize_user_language": lambda language: language,
        "public_hub_copy": lambda _language: {
            "support_ticket_admin_only": "Admin only",
            "support_ticket_action_unsupported": "Unsupported",
        },
        "is_admin_user": lambda _uid: True,
        "safe_edit_or_send": safe_edit_or_send,
    })
    return source, namespace, ticket, bot, edits, sent_rows, read_dispatch, ticket_reads


class SupportTicketSendMatchesPreviewTests(unittest.TestCase):
    def setUp(self):
        (
            self.source, self.ns, self.ticket, self.bot, self.edits,
            self.sent_rows, self.read_dispatch, self.ticket_reads,
        ) = _load_actual_code()

    def _assert_real_route(self, callback_data: str):
        routes = re.findall(
            r'(?m)^\s*tg_app\.add_handler\(CallbackQueryHandler\(handle_ticket_callback, pattern=r"([^\"]+)"\)\)',
            self.source,
        )
        self.assertEqual(len(routes), 1, "ticket callback handler should be registered exactly once")
        self.assertRegex(callback_data, routes[0])

    def _render_preview(self, kind: str, text: str, variant: int = 0) -> str:
        if kind == "manual":
            self.ns["set_support_ticket_pending"](501, "admin_reply_input", ticket_id=74, source="new")
            message = _Message(text)
            update = SimpleNamespace(effective_user=SimpleNamespace(id=501), message=message)
            _run_inert(self.ns["handle_support_pending_input"](update, SimpleNamespace()))
            markup = message.replies[-1][1]["reply_markup"]
        else:
            query = _Query(f"ticket|suggest|74|{variant}")
            update = SimpleNamespace(callback_query=query)
            _run_inert(self.ns["handle_ticket_callback"](update, SimpleNamespace(bot=self.bot)))
            markup = self.edits[-1][1]

        callback_data = next(
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.text == "📨 Gửi cho khách"
        )
        self._assert_real_route(callback_data)
        self.assertLessEqual(len(callback_data.encode("utf-8")), 64)
        return callback_data

    def _click_send(self, callback_data: str):
        query = _Query(callback_data)
        self.bot.events.clear()
        query.events = self.bot.events
        update = SimpleNamespace(callback_query=query)
        _run_inert(self.ns["handle_ticket_callback"](update, SimpleNamespace(bot=self.bot)))
        return query

    def test_stale_manual_and_suggested_previews_cannot_send_newer_text(self):
        for kind in ("manual", "suggested"):
            with self.subTest(kind=kind):
                self.ns["USER_PENDING"].clear()
                self.bot.sent.clear()
                self.sent_rows.clear()

                old_callback = self._render_preview(kind, f"{kind} old text", variant=0)
                new_callback = self._render_preview(kind, f"{kind} current text", variant=1)

                self.read_dispatch.clear()
                self.ticket_reads.clear()
                stale_query = self._click_send(old_callback)

                self.assertEqual(
                    self.bot.sent,
                    [],
                    f"stale {kind} preview sent newer text through its old Send callback",
                )
                self.assertEqual(
                    stale_query.answers,
                    [(('Bản xem trước đã hết hạn. Vui lòng soạn hoặc tạo gợi ý lại.',), {"show_alert": True})],
                )
                self.assertEqual(self.read_dispatch, ["language"])
                self.assertEqual(self.ticket_reads, [])
                self.assertNotEqual(old_callback, new_callback)
                self.assertEqual(self.ns["get_support_ticket_pending"](501)["reply_text"], f"{kind} current text" if kind == "manual" else "Suggested reply variant 1")

                self.read_dispatch.clear()
                self.ticket_reads.clear()
                current_query = self._click_send(new_callback)
                self.assertEqual(current_query.answers, [(('Đang gửi phản hồi...',), {"show_alert": False})])
                self.assertEqual(self.read_dispatch, ["language", "ticket"])
                self.assertEqual(self.ticket_reads, [74])
                self.assertEqual(self.bot.events, ["ack", "send"])
                self.assertEqual(len(self.bot.sent), 1)
                expected = f"{kind} current text" if kind == "manual" else "Suggested reply variant 1"
                self.assertIn(expected, self.bot.sent[0]["text"])
                self.assertEqual(len(self.sent_rows), 1)

    def test_legacy_tokenless_send_callback_is_rejected(self):
        self._render_preview("manual", "Current reply")

        self.read_dispatch.clear()
        self.ticket_reads.clear()
        query = self._click_send("ticket|send|74")

        self.assertEqual(self.bot.sent, [])
        self.assertEqual(self.read_dispatch, ["language"])
        self.assertEqual(self.ticket_reads, [])
        self.assertEqual(
            query.answers,
            [(('Bản xem trước đã hết hạn. Vui lòng soạn hoặc tạo gợi ý lại.',), {"show_alert": True})],
        )

    def test_delivery_failure_keeps_preview_retryable_after_single_ack(self):
        callback_data = self._render_preview("manual", "Retryable reply")
        self.bot.failure = RuntimeError("simulated send failure")

        self.read_dispatch.clear()
        self.ticket_reads.clear()
        failed_query = self._click_send(callback_data)

        self.assertEqual(failed_query.answers, [(('Đang gửi phản hồi...',), {"show_alert": False})])
        self.assertEqual(self.read_dispatch, ["language", "ticket"])
        self.assertEqual(self.ticket_reads, [74])
        self.assertEqual(self.bot.events, ["ack", "send"])
        self.assertIn("Bản xem trước vẫn còn", failed_query.message.replies[0][0][0])
        self.assertEqual(self.ns["get_support_ticket_pending"](501)["reply_text"], "Retryable reply")
        self.assertEqual(self.bot.sent, [])

        self.bot.failure = None
        self.read_dispatch.clear()
        self.ticket_reads.clear()
        self._click_send(callback_data)

        self.assertEqual(self.read_dispatch, ["language", "ticket"])
        self.assertEqual(self.ticket_reads, [74])
        self.assertEqual(len(self.bot.sent), 1)
        self.assertIn("Retryable reply", self.bot.sent[0]["text"])

    def test_still_valid_preview_with_stale_ticket_does_not_send(self):
        callback_data = self._render_preview("manual", "Ticket disappeared")
        self.ns["get_support_ticket"] = lambda ticket_id: self.ticket_reads.append(int(ticket_id) or None)
        self.read_dispatch.clear()
        self.ticket_reads.clear()

        query = self._click_send(callback_data)

        self.assertEqual(self.read_dispatch, ["language", "ticket"])
        self.assertEqual(self.bot.sent, [])
        self.assertEqual(query.answers, [(('Không có nội dung hợp lệ để gửi.',), {"show_alert": True})])

    def test_public_actor_cannot_send_admin_preview(self):
        callback_data = self._render_preview("manual", "Admin-only reply")
        self.ns["is_admin_user"] = lambda _uid: False
        self.read_dispatch.clear()
        self.ticket_reads.clear()

        query = self._click_send(callback_data)

        self.assertEqual(query.answers, [(('Admin only',), {"show_alert": True})])
        self.assertEqual(self.ticket_reads, [])
        self.assertEqual(self.bot.sent, [])


if __name__ == "__main__":
    unittest.main()
