"""Admin ticket actions must keep their ticket-list origin."""

import asyncio
import html
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
import uuid
from support_v1b import suggested_reply as _support_suggested_reply


class _Button:
    def __init__(self, text, callback_data=None):
        self.text, self.callback_data = text, callback_data


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
        self.message = _Message("")
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


class AdminTicketOriginPaginationTest(unittest.TestCase):
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
        }
        self.pending = {}
        self.edits = []
        self.sent = []

        async def safe_edit_or_send(query, text, **kwargs):
            markup = kwargs.get("reply_markup")
            query.reply_markups.append(markup)
            self.edits.append((text, markup))

        def set_pending(user_id, step, **fields):
            self.pending[user_id] = {"step": step, **fields}

        def update_ticket(ticket_id, **fields):
            self.assertEqual(ticket_id, self.ticket["id"])
            self.ticket.update(fields)
            return dict(self.ticket)

        async def fake_send_message(**kwargs):
            self.sent.append(kwargs)

        self.namespace = {
            "html": html,
            "uuid": uuid,
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
            "support_ticket_admin_text": lambda _ticket: "Ticket detail",
            "support_suggested_reply": _support_suggested_reply,
            "now_text": lambda: "fixture-time",
            "get_support_ticket": lambda ticket_id: (
                dict(self.ticket) if ticket_id == self.ticket["id"] else None
            ),
            "update_support_ticket": update_ticket,
            "add_support_ticket_message": lambda *_args: None,
            "clear_support_ticket_pending": lambda user_id: self.pending.pop(user_id, None),
            "get_support_ticket_pending": lambda user_id: self.pending.get(user_id),
            "set_support_ticket_pending": set_pending,
            "USER_PENDING": {},
            "safe_edit_or_send": safe_edit_or_send,
        }
        self.context = SimpleNamespace(bot=SimpleNamespace(send_message=fake_send_message))
        source_path = Path(__file__).resolve().parents[1] / "bot.py"
        self.source = source_path.read_text(encoding="utf-8")
        for name in (
            "support_ticket_admin_keyboard",
            "handle_ticket_callback",
            "handle_support_pending_input",
        ):
            code = _function_source(self.source, name)
            exec(compile(code, f"bot.py:{name}", "exec"), self.namespace)

        lifecycle = _function_source(self.source, "lifespan")
        registration = [
            line.strip() for line in lifecycle.splitlines()
            if "tg_app.add_handler(CallbackQueryHandler(handle_ticket_callback," in line
        ]
        self.assertEqual(len(registration), 1)
        application = _Application()
        exec(registration[0], {
            **self.namespace,
            "tg_app": application,
            "CallbackQueryHandler": _CallbackQueryHandler,
        })
        self.assertEqual(len(application.handlers), 1)
        self.callback = application.handlers[0].callback
        self.pattern = application.handlers[0].pattern

    async def _press(self, data):
        self.assertRegex(data, self.pattern)
        query = _Query(data, self.admin_id)
        await self.callback(SimpleNamespace(callback_query=query), self.context)
        return query

    async def _open_ticket_from_high_page_six(self):
        detail = await self._press("ticket|av|9006|high|6")
        ask_callback = next(
            button.callback_data
            for row in detail.reply_markups[-1].inline_keyboard
            for button in row
            if button.text == "👤 Hỏi thêm khách"
        )
        return ask_callback

    def test_emitted_ask_button_keeps_origin_filter_and_page(self):
        ask_callback = asyncio.run(self._open_ticket_from_high_page_six())

        self.assertEqual(ask_callback, "ticket|ask|9006|high|6")

    def test_ask_prompt_back_returns_to_same_ticket_detail_and_clears_pending(self):
        ask_callback = asyncio.run(self._open_ticket_from_high_page_six())
        prompt = asyncio.run(self._press("ticket|ask|9006|high|6"))

        self.assertEqual(
            self.pending[self.admin_id],
            {"step": "admin_reply_input", "ticket_id": 9006, "source": "high", "list_offset": 6},
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
        self.assertEqual(self.sent, [])

    def test_ask_preview_back_keeps_origin_and_does_not_send_customer_message(self):
        ask_callback = asyncio.run(self._open_ticket_from_high_page_six())
        asyncio.run(self._press("ticket|ask|9006|high|6"))
        message = _Message("Vui lòng bổ sung thông tin fixture")
        handled = asyncio.run(self.namespace["handle_support_pending_input"](
            SimpleNamespace(
                effective_user=SimpleNamespace(id=self.admin_id), message=message
            ),
            self.context,
        ))

        self.assertTrue(handled)
        preview_markup = message.reply_markups[-1]
        preview_back = next(
            callback for callback in _callbacks(preview_markup)
            if callback.startswith("ticket|av|")
        )
        self.assertEqual(preview_back, "ticket|av|9006|high|6")

        detail = asyncio.run(self._press(preview_back))
        self.assertNotIn(self.admin_id, self.pending)
        list_back = next(
            callback for callback in _callbacks(detail.reply_markups[-1])
            if callback.startswith("ticket|al|")
        )
        self.assertEqual(list_back, "ticket|al|high|6")
        self.assertEqual(self.sent, [])

    def test_assign_from_filtered_page_keeps_origin_and_offset(self):
        async def exercise():
            detail = await self._press("ticket|av|9006|high|6")
            assign_callback = next(
                button.callback_data
                for row in detail.reply_markups[-1].inline_keyboard
                for button in row
                if button.text == "🙋 Nhận xử lý"
            )
            self.assertEqual(assign_callback, "ticket|assign|9006|high|6")

            assigned_detail = await self._press(assign_callback)
            list_back = next(
                callback for callback in _callbacks(assigned_detail.reply_markups[-1])
                if callback.startswith("ticket|al|")
            )
            self.assertEqual(list_back, "ticket|al|high|6")
            self.assertEqual(self.ticket["assigned_admin_id"], self.admin_id)

        asyncio.run(exercise())

    def test_lead_actions_keep_origin_through_first_and_repeat_clicks(self):
        async def exercise():
            self.ticket["category"] = "lead_consulting"
            for button_label, marker in (
                ("📞 Cần liên hệ", "Cần liên hệ"),
                ("⭐ Lead tiềm năng", "Lead tiềm năng"),
            ):
                self.ticket.update(status="new", assigned_admin_id=None, admin_note="")
                detail = await self._press("ticket|av|9006|high|6")
                lead_callback = next(
                    button.callback_data
                    for row in detail.reply_markups[-1].inline_keyboard
                    for button in row
                    if button.text == button_label
                )

                first_detail = await self._press(lead_callback)
                first_list = next(
                    callback for callback in _callbacks(first_detail.reply_markups[-1])
                    if callback.startswith("ticket|al|")
                )
                self.assertEqual(first_list, "ticket|al|high|6")

                repeated_detail = await self._press(lead_callback)
                repeated_list = next(
                    callback for callback in _callbacks(repeated_detail.reply_markups[-1])
                    if callback.startswith("ticket|al|")
                )
                self.assertEqual(repeated_list, "ticket|al|high|6")
                self.assertEqual(self.ticket["admin_note"].count(marker), 1)

            legacy_detail = await self._press("ticket|lead|9006|contact")
            legacy_list = next(
                callback for callback in _callbacks(legacy_detail.reply_markups[-1])
                if callback.startswith("ticket|al|")
            )
            self.assertEqual(legacy_list, "ticket|al|new|0")

        asyncio.run(exercise())

    def test_status_updates_from_filtered_page_keep_origin_and_offset(self):
        async def exercise():
            detail = await self._press("ticket|av|9006|high|6")
            expected_callbacks = {
                "✅ Đã xử lý": "ticket|st|9006|resolved|high|6",
                "💰 Đánh dấu refund": "ticket|st|9006|refund_pending|high|6",
                "⏳ Chờ provider": "ticket|st|9006|waiting_provider|high|6",
            }
            actual_callbacks = {
                button.text: button.callback_data
                for row in detail.reply_markups[-1].inline_keyboard
                for button in row
                if button.text in expected_callbacks
            }
            self.assertEqual(actual_callbacks, expected_callbacks)

            updated_detail = await self._press(expected_callbacks["⏳ Chờ provider"])
            self.assertEqual(self.ticket["status"], "waiting_provider")
            list_back = next(
                callback for callback in _callbacks(updated_detail.reply_markups[-1])
                if callback.startswith("ticket|al|")
            )
            self.assertEqual(list_back, "ticket|al|high|6")

        asyncio.run(exercise())

    def test_suggested_reply_keeps_origin_through_preview_back_and_send(self):
        async def exercise():
            detail = await self._press("ticket|av|9006|high|6")
            suggest_callback = next(
                button.callback_data
                for row in detail.reply_markups[-1].inline_keyboard
                for button in row
                if button.text == "🤖 Gợi ý trả lời"
            )
            self.assertEqual(suggest_callback, "ticket|suggest|9006|0|high|6")

            preview = await self._press(suggest_callback)
            state = self.pending[self.admin_id]
            self.assertEqual(state["source"], "high")
            self.assertEqual(state["list_offset"], 6)
            preview_callbacks = {
                button.text: button.callback_data
                for row in preview.reply_markups[-1].inline_keyboard
                for button in row
            }
            self.assertEqual(preview_callbacks["⬅️ Ticket"], "ticket|av|9006|high|6")
            self.assertEqual(preview_callbacks["✍️ Sửa lại"], "ticket|reply|9006|high|6")
            self.assertEqual(preview_callbacks["🔄 Gợi ý khác"], "ticket|suggest|9006|1|high|6")

            back_detail = await self._press(preview_callbacks["⬅️ Ticket"])
            back_list = next(
                callback for callback in _callbacks(back_detail.reply_markups[-1])
                if callback.startswith("ticket|al|")
            )
            self.assertEqual(back_list, "ticket|al|high|6")

            detail = await self._press("ticket|av|9006|high|6")
            suggest_callback = next(
                button.callback_data
                for row in detail.reply_markups[-1].inline_keyboard
                for button in row
                if button.text == "🤖 Gợi ý trả lời"
            )
            preview = await self._press(suggest_callback)
            send_callback = next(
                button.callback_data
                for row in preview.reply_markups[-1].inline_keyboard
                for button in row
                if button.text == "📨 Gửi cho khách"
            )
            sent_detail = await self._press(send_callback)
            self.assertEqual(len(self.sent), 1)
            self.assertEqual(self.sent[0]["chat_id"], "fixture-customer")
            send_list = next(
                callback for callback in _callbacks(sent_detail.reply_markups[-1])
                if callback.startswith("ticket|al|")
            )
            self.assertEqual(send_list, "ticket|al|high|6")

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
