import re
import unittest
from pathlib import Path
from types import SimpleNamespace


BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"
BOT_SOURCE = BOT_PATH.read_text(encoding="utf-8")


def _function_source(name):
    start = re.search(rf"(?m)^(?:async\s+)?def {re.escape(name)}\s*\(", BOT_SOURCE)
    assert start is not None, f"missing source function: {name}"
    boundary = re.search(
        r"(?m)^(?:async\s+)?def\s+\w+\s*\(|^class\s+\w+|^[A-Z][A-Z0-9_]*\s*=",
        BOT_SOURCE[start.end():],
    )
    end = start.end() + boundary.start() if boundary else len(BOT_SOURCE)
    return BOT_SOURCE[start.start():end].rstrip()


class _Button:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class _Query:
    def __init__(self, user_id, data):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


class _CapturedCallbackQueryHandler:
    def __init__(self, callback, pattern):
        self.callback = callback
        self.pattern = re.compile(pattern)


class _Application:
    def __init__(self):
        self.handlers = []

    def add_handler(self, handler):
        self.handlers.append(handler)


def _run_immediate(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as stopped:
        return stopped.value
    finally:
        coroutine.close()
    raise AssertionError("callback unexpectedly yielded to I/O or a scheduler")


def _registered_status_route(namespace):
    registrations = [
        line.strip()
        for line in BOT_SOURCE.splitlines()
        if "tg_app.add_handler(CallbackQueryHandler(handle_public_video_status_callback," in line
    ]
    assert len(registrations) == 1, (
        f"expected one public video status registration, got {len(registrations)}"
    )
    app = _Application()
    exec(
        registrations[0],
        {
            "tg_app": app,
            "CallbackQueryHandler": _CapturedCallbackQueryHandler,
            "handle_public_video_status_callback": namespace[
                "handle_public_video_status_callback"
            ],
        },
    )
    assert len(app.handlers) == 1
    return app.handlers[0]


class PublicVideoStatusSingleAckTests(unittest.TestCase):
    def test_emitted_status_route_returns_one_alert_for_missing_task_id(self):
        forbidden_calls = []

        def forbidden_status_lookup(*args, **kwargs):
            forbidden_calls.append((args, kwargs))
            raise AssertionError("invalid status callbacks must stop before job/provider lookup")

        namespace = {
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "ui_text": lambda _lang, key: key,
            "user_ui_lang": lambda _uid: "vi",
            "shopaikey_job_by_task_id": forbidden_status_lookup,
            "shopaikey_video_job_status": forbidden_status_lookup,
        }
        exec(
            "from __future__ import annotations\n\n"
            + "\n\n".join(
                _function_source(name)
                for name in (
                    "video_public_callback_failure_guard",
                    "shopaikey_video_job_check_keyboard",
                    "handle_public_video_status_callback",
                )
            ),
            namespace,
        )
        namespace["handle_public_video_status_callback"] = namespace[
            "video_public_callback_failure_guard"
        ](namespace["handle_public_video_status_callback"])

        markup = namespace["shopaikey_video_job_check_keyboard"](
            "task-123", "vi", public_user=True
        )
        emitted = markup.inline_keyboard[0][0].callback_data
        self.assertEqual(emitted, "video|status|task-123")

        # Simulate an expired/malformed instance of the actual emitted route.
        stale_callback = emitted.rsplit("|", 1)[0] + "|"
        route = _registered_status_route(namespace)
        self.assertIsNotNone(route.pattern.match(stale_callback))

        query = _Query(456, stale_callback)
        update = SimpleNamespace(callback_query=query)
        _run_immediate(route.callback(update, SimpleNamespace()))

        self.assertEqual(
            query.answers,
            [(("Không tìm thấy trạng thái xử lý.",), {"show_alert": True})],
        )
        self.assertEqual(forbidden_calls, [])


if __name__ == "__main__":
    unittest.main()
