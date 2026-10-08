"""Old self-shot controls acknowledge before their read-only Hub recovery."""
import ast
import asyncio
from contextvars import ContextVar
from copy import deepcopy
import inspect
from pathlib import Path
import re
from types import SimpleNamespace
import unittest

from services import video_scene3_flow, video_selfshot2, video_selfshot3


SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
def _function_source(name):
    start = re.search(rf"(?m)^(?:async\s+)?def {re.escape(name)}\s*\(", SOURCE)
    assert start is not None, f"missing source function: {name}"
    boundary = re.search(
        r"(?m)^(?:async\s+)?def\s+\w+\s*\(|^class\s+\w+|^[A-Z][A-Z0-9_]*\s*=|^@",
        SOURCE[start.end():],
    )
    end = start.end() + boundary.start() if boundary else len(SOURCE)
    source = SOURCE[start.start():end]
    node = ast.parse(source).body[0]
    return "".join(source.splitlines(keepends=True)[:node.end_lineno])


FUNCTIONS = {name: _function_source(name) for name in (
    "video_public_callback_failure_guard", "video_scene3_keyboard",
    "video_selfshot_product_hub_text", "video_selfshot_product_hub_keyboard",
    "safe_edit_or_send", "handle_video_product_callback",
)}


class Button:
    def __init__(self, text, callback_data):
        self.text, self.callback_data = text, callback_data


class Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class Query:
    def __init__(self, data, fail_answer=False):
        self.data, self.fail_answer = data, fail_answer
        self.from_user = SimpleNamespace(id=701)
        self.message = SimpleNamespace(chat_id=701)
        self.events, self.edits = [], []

    async def answer(self, *args, **kwargs):
        self.events.append("answer")
        if self.fail_answer:
            raise TimeoutError("offline ACK timeout")

    async def edit_message_text(self, text, **kwargs):
        self.events.append("edit")
        self.edits.append((text, kwargs["reply_markup"]))
        return True


def _runtime(session):
    errors, routes = [], []
    ns = {
        "Update": object, "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "InlineKeyboardButton": Button, "InlineKeyboardMarkup": Markup,
        "video_scene3_flow": video_scene3_flow,
        "video_selfshot2": video_selfshot2, "video_selfshot3": video_selfshot3,
        "get_user_language": lambda _uid: "vi",
        "get_video_session": lambda _uid: session,
        "_VIDEO_EDIT_CALLBACK_TRANSACTIONAL": ContextVar("transaction", default=False),
        "_VIDEO_EDIT_CALLBACK_ANSWERED": ContextVar("answered", default=False),
        "inspect": inspect,
        "ApplicationHandlerStop": type("ApplicationHandlerStop", (Exception,), {}),
        "_is_video_public_callback": lambda *_args: True,
        "logger": SimpleNamespace(exception=lambda *_args: errors.append("unexpected handler failure")),
    }
    for name in ("video_public_callback_failure_guard", "video_scene3_keyboard",
                 "video_selfshot_product_hub_text", "video_selfshot_product_hub_keyboard",
                 "safe_edit_or_send", "handle_video_product_callback"):
        code = FUNCTIONS[name]
        if name == "handle_video_product_callback":
            code = "@video_public_callback_failure_guard\n" + code
        exec(compile("from __future__ import annotations\n" + code, "bot.py:" + name, "exec"), ns)
    ns.update(tg_app=SimpleNamespace(add_handler=routes.append),
              CallbackQueryHandler=lambda callback, pattern: (callback, re.compile(pattern)))
    registration = next(line.strip() for line in SOURCE.splitlines()
                        if "tg_app.add_handler(CallbackQueryHandler(handle_video_product_callback," in line)
    exec(registration, ns)
    return routes[0], errors


class StaleSelfshotAcknowledgementTests(unittest.TestCase):
    def _click(self, flow, fail_answer=False):
        session = {"product_id": "video_ai_real", "draft": {"content": "keep", "step": "review"}}
        original = deepcopy(session)
        service = video_selfshot2 if flow == "ss2" else video_selfshot3
        rows = service.screen_model("intro", service.initial_draft())["rows"]
        data = next(callback for row in rows for _label, callback in row
                    if callback == f"vproduct|{flow}|source")
        (handler, pattern), errors = _runtime(session)
        self.assertIsNotNone(pattern.match(data))
        query = Query(data, fail_answer)
        asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace(user_data={})))
        self.assertEqual([], errors)
        self.assertEqual(original, session)
        self.assertEqual(1, len(query.edits))
        text, markup = query.edits[0]
        self.assertIn("Video tự quay", text)
        self.assertIn("menu|main_video", [button.callback_data for row in markup.inline_keyboard for button in row])
        return query

    def test_emitted_old_selfshot_buttons_acknowledge_before_hub_render(self):
        for flow in ("ss2", "ss3"):
            with self.subTest(flow=flow):
                self.assertEqual(["answer", "edit"], self._click(flow).events)

    def test_ack_timeout_does_not_interrupt_read_only_hub_recovery(self):
        for flow in ("ss2", "ss3"):
            with self.subTest(flow=flow):
                self.assertEqual(["answer", "edit"], self._click(flow, fail_answer=True).events)


if __name__ == "__main__":
    unittest.main()
