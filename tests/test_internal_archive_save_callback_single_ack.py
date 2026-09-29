import asyncio
import html
import time
import unittest
from pathlib import Path
from types import SimpleNamespace


class _Button:
    def __init__(self, text, callback_data=None, **kwargs):
        self.text = text
        self.callback_data = callback_data
        self.kwargs = kwargs


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


def _runtime():
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")

    def block(start, end):
        first = source.index(start)
        return source[first:source.index(end, first)]

    definitions = "\n".join((
        block("def internal_archive_pending_key(", "def internal_archive_menu_text()"),
        block("async def handle_internal_archive_callback(", "async def handle_internal_archive_pending_upload("),
    ))
    saved = []
    rendered = []
    namespace = {
        "time": time,
        "html": html,
        "USER_PENDING": {},
        "INTERNAL_ARCHIVE_TTL_SECONDS": 900,
        "INTERNAL_DOC_DEPARTMENTS": {"customers": "Hồ sơ khách hàng"},
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "is_admin_user": lambda _uid: True,
        "clear_doc_tool_pending": lambda _uid: None,
        "clear_media_creator_pending_states": lambda _uid: None,
        "internal_archive_quota_error": lambda _uid, _size: None,
        "save_internal_document": lambda uid, state: saved.append((uid, dict(state))) or 701,
    }
    exec(compile("from __future__ import annotations\n" + definitions, "bot.py", "exec"), namespace)

    async def safe_edit(_query, text, **kwargs):
        rendered.append((text, kwargs.get("reply_markup")))

    namespace["safe_edit_query_message"] = safe_edit
    return source, namespace, saved, rendered


class _FakeQuery:
    def __init__(self, user_id, data):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace()
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


class InternalArchiveSaveCallbackSingleAckTests(unittest.TestCase):
    def test_real_archive_route_is_registered(self):
        source, _runtime_scope, _saved, _rendered = _runtime()
        self.assertIn(
            r'tg_app.add_handler(CallbackQueryHandler(handle_internal_archive_callback, pattern=r"^archive\|"))',
            source,
        )

    def test_stale_save_replay_answers_once_without_saving_again(self):
        _source, runtime, saved, rendered = _runtime()
        user_id = 771122
        runtime["set_internal_archive_pending"](
            user_id,
            "preview",
            department="customers",
            document_type="customer_profile",
            file_info={
                "file_id": "fake-telegram-file-id",
                "file_name": "customer.pdf",
                "mime_type": "application/pdf",
                "size_bytes": 64,
            },
        )
        context = SimpleNamespace()
        first = _FakeQuery(user_id, "archive|save")
        asyncio.run(runtime["handle_internal_archive_callback"](
            SimpleNamespace(callback_query=first), context,
        ))

        self.assertEqual(len(saved), 1)
        self.assertEqual(first.answers, [((), {})])
        self.assertIsNone(runtime["get_internal_archive_pending"](user_id))
        self.assertIn("Đã lưu hồ sơ #701", rendered[-1][0])

        stale = _FakeQuery(user_id, "archive|save")
        asyncio.run(runtime["handle_internal_archive_callback"](
            SimpleNamespace(callback_query=stale), context,
        ))

        self.assertEqual(len(saved), 1, "the stale keyboard must not save a second archive row")
        self.assertEqual(
            stale.answers,
            [(('Chưa có hồ sơ chờ lưu.',), {"show_alert": True})],
            "one stale callback must receive exactly one alert acknowledgement",
        )


if __name__ == "__main__":
    unittest.main()
