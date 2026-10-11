"""Expired Split PDF page prompts must not fall through to generic chat."""

import re
import unittest
from pathlib import Path
from types import SimpleNamespace


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def _source_function(name):
    start = re.search(rf"(?m)^(?:async )?def {re.escape(name)}\(", BOT_SOURCE)
    if not start:
        return ""
    following = re.search(r"(?m)^(?:async )?def [A-Za-z_]\w*\(", BOT_SOURCE[start.end():])
    end = start.end() + following.start() if following else len(BOT_SOURCE)
    return BOT_SOURCE[start.start():end]


class _Noop:
    def __call__(self, *_args, **_kwargs):
        return _Noop()

    def __bool__(self):
        return False

    def __await__(self):
        if False:
            yield None
        return False


class _Filter:
    def __and__(self, _other):
        return self

    def __invert__(self):
        return self


class _MessageHandler:
    def __init__(self, _filters, callback):
        self.callback = callback


def _run_immediate(coro):
    try:
        coro.send(None)
    except StopIteration as completed:
        return completed.value
    raise AssertionError("fixture unexpectedly yielded I/O")


class ExpiredDocPageSpecInputTests(unittest.TestCase):
    def test_expired_emitted_message_handler_consumes_text_before_generic_chat(self):
        now = 10_000.0
        user_id = 7041
        stale_key = f"doc_tool:{user_id}"
        unrelated_key = "doc_tool:7042"
        pending = {
            stale_key: {
                "doc_tool_current": "split_pdf",
                "awaiting_page_spec": "1",
                "created_at_ts": now - 601,
                "doc_tool_files": [{"file_id": "fixture-file"}],
            },
            unrelated_key: {"doc_tool_current": "split_pdf", "created_at_ts": now},
        }
        replies, events = [], []

        class Message:
            text = "1-3"

            async def reply_text(self, text, **kwargs):
                replies.append((text, kwargs))

        async def generic_chat(*_args, **_kwargs):
            events.append("generic_chat")
            return "generic"

        namespace = {
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "USER_PENDING": pending,
            "DOC_TOOL_STATE_TTL_SECONDS": 600,
            "time": SimpleNamespace(time=lambda: now),
            "telegram_message_idempotent": lambda function: function,
            "handle_state_reset_slash_command": _Noop(),
            "get_user_language": lambda _uid: "vi",
            "main_docs_keyboard": lambda _lang: "documents-menu",
            "handle_public_chat_text": generic_chat,
            "SUPPORT_PERSONA_NORMAL_CHAT_ENABLED": False,
            "AICHAT_INLINE_ENABLED": False,
            "ensure_user_modes": lambda _uid: {},
            "get_video_downloader_pending": lambda _uid: {},
            "get_video_dubbing_pending": lambda _uid: {},
            "VIDEO_DUBBING_PENDING_TEXT_STEPS": set(),
            "normalize_music_inline_command_text": lambda _text: "",
            "extract_first_http_url": lambda _text: None,
            "is_media_preview_url_text": lambda _text: False,
            "is_probable_media_tags_text": lambda _text: False,
            "extract_supported_video_url": lambda _text: None,
            "re": re,
        }
        for name in ("doc_tool_pending_key", "get_doc_tool_pending", "handle_doc_tool_pending_text"):
            source = _source_function(name)
            self.assertTrue(source, f"missing production source function {name}")
            exec(compile("from __future__ import annotations\n" + source, f"bot.py:{name}", "exec"), namespace)

        message_function = _source_function("handle_message")
        self.assertTrue(message_function, "missing production handle_message")
        async def not_pending(*_args, **_kwargs):
            return False

        for handler_name in set(re.findall(r"(?m)\bawait\s+(handle_[A-Za-z_]\w*)\s*\(", message_function)):
            namespace.setdefault(handler_name, not_pending)
        namespace.setdefault("get_video_editor_pending", lambda _uid: {})
        namespace.setdefault("pending_text_owner_active", lambda _uid: False)
        exec(compile("from __future__ import annotations\n" + message_function, "bot.py:handle_message", "exec"), namespace)

        registration = re.search(
            r"(?m)^\s*tg_app\.add_handler\(MessageHandler\(filters\.TEXT & ~filters\.COMMAND, handle_message\)\)\s*$",
            BOT_SOURCE,
        )
        self.assertIsNotNone(registration, "non-command MessageHandler registration changed")
        handlers = []
        namespace.update(
            tg_app=SimpleNamespace(add_handler=handlers.append),
            MessageHandler=_MessageHandler,
            filters=SimpleNamespace(TEXT=_Filter(), COMMAND=_Filter()),
        )
        exec(compile(registration.group(0).strip(), "bot.py:message handler registration", "exec"), namespace)
        self.assertEqual(len(handlers), 1)

        update = SimpleNamespace(
            message=Message(),
            effective_user=SimpleNamespace(id=user_id),
        )
        context = SimpleNamespace(user_data={})
        _run_immediate(handlers[0].callback(update, context))

        self.assertEqual(events, [], "expired page input reached generic chat")
        self.assertEqual(len(replies), 1)
        self.assertIn("hết hạn", replies[0][0].lower())
        self.assertIn("Tách PDF", replies[0][0])
        self.assertEqual(replies[0][1].get("reply_markup"), "documents-menu")
        self.assertNotIn(stale_key, pending, "only the expired actor's document state should be removed")
        self.assertIn(unrelated_key, pending, "another user's active document state must remain")


if __name__ == "__main__":
    unittest.main()
