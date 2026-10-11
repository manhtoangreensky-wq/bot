"""Expired customer Support input must not fall through to unrelated chat."""

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


class ExpiredSupportInputDispatchTests(unittest.TestCase):
    def test_expired_ticket_text_is_consumed_before_public_chat(self):
        now = 10_000.0
        user_id = 7051
        stale_key = f"support_ticket:{user_id}"
        unrelated_key = "support_ticket:7052"
        pending = {
            stale_key: {
                "pending_action": "support_ticket",
                "step": "awaiting_message",
                "created_at_ts": now - 901,
                "category": "general_support",
                "back_to": "support|start|profile",
            },
            unrelated_key: {
                "pending_action": "support_ticket",
                "step": "awaiting_message",
                "created_at_ts": now,
            },
        }
        replies, events = [], []

        class Message:
            text = "My ticket details arrived after the form timed out."

            async def reply_text(self, text, **kwargs):
                replies.append((text, kwargs))

        async def public_chat(*_args, **_kwargs):
            events.append("public_chat")

        namespace = {
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "USER_PENDING": pending,
            "SUPPORT_TICKET_TTL_SECONDS": 900,
            "time": SimpleNamespace(time=lambda: now),
            "normalize_user_language": lambda lang: lang or "vi",
            "get_user_language": lambda _uid: "vi",
            "public_hub_copy": lambda _lang: {"support_back": "Quay lại", "main_menu": "Menu chính"},
            "ui_text": lambda _lang, _key: "⏰ Yêu cầu đã hết hạn. Bot chưa trừ Xu.",
            "InlineKeyboardButton": lambda text, callback_data=None: SimpleNamespace(text=text, callback_data=callback_data),
            "InlineKeyboardMarkup": lambda rows: SimpleNamespace(inline_keyboard=rows),
            "SUPPORT_PERSONA_NORMAL_CHAT_ENABLED": False,
            "AICHAT_INLINE_ENABLED": False,
            "handle_state_reset_slash_command": _Noop(),
            "get_video_downloader_pending": lambda _uid: {},
            "get_video_dubbing_pending": lambda _uid: {},
            "VIDEO_DUBBING_PENDING_TEXT_STEPS": set(),
            "ensure_user_modes": lambda _uid: {},
            "normalize_music_inline_command_text": lambda _text: "",
            "extract_first_http_url": lambda _text: None,
            "is_media_preview_url_text": lambda _text: False,
            "is_probable_media_tags_text": lambda _text: False,
            "extract_supported_video_url": lambda _text: None,
            "handle_public_chat_text": public_chat,
            "re": re,
        }
        for name in (
            "support_ticket_pending_key",
            "get_support_ticket_pending",
            "support_flow_back_keyboard",
            "handle_support_pending_input",
        ):
            source = _source_function(name)
            self.assertTrue(source, f"missing production source function {name}")
            exec(compile("from __future__ import annotations\n" + source, f"bot.py:{name}", "exec"), namespace)

        message_function = _source_function("handle_message")
        self.assertTrue(message_function, "missing production handle_message")

        async def not_pending(*_args, **_kwargs):
            return False

        for name in set(re.findall(r"(?m)\bawait\s+(handle_[A-Za-z_]\w*)\s*\(", message_function)):
            namespace.setdefault(name, not_pending)
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

        update = SimpleNamespace(message=Message(), effective_user=SimpleNamespace(id=user_id))
        _run_immediate(handlers[0].callback(update, SimpleNamespace(user_data={})))

        self.assertEqual(events, [], "expired Support text reached public chat")
        self.assertEqual(len(replies), 1)
        self.assertIn("hết hạn", replies[0][0].lower())
        self.assertEqual(
            {button.callback_data for row in replies[0][1]["reply_markup"].inline_keyboard for button in row},
            {"support|start|profile", "menu|main"},
        )
        self.assertNotIn(stale_key, pending, "only the expired actor's Support state should be removed")
        self.assertIn(unrelated_key, pending, "another user's active Support state must remain")


if __name__ == "__main__":
    unittest.main()
