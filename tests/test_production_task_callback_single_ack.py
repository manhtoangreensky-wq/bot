import asyncio
import html
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
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class _CallbackQueryHandler:
    def __init__(self, callback, pattern):
        self.callback = callback
        self.pattern = pattern


class _Application:
    def __init__(self):
        self.handlers = []

    def add_handler(self, handler):
        self.handlers.append(handler)


def _load_functions(*names, **dependencies):
    namespace = {
        "SimpleNamespace": SimpleNamespace,
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "html": html,
        **dependencies,
    }
    source = "from __future__ import annotations\n\n" + "\n\n".join(
        _function_source(name) for name in names
    )
    exec(compile(source, str(BOT_PATH), "exec"), namespace)
    return namespace


def _registered_task_route(handler):
    matches = [
        line.strip()
        for line in BOT_SOURCE.splitlines()
        if "tg_app.add_handler(CallbackQueryHandler(handle_task_callback," in line
    ]
    assert len(matches) == 1, f"expected one task callback lifecycle route, got {len(matches)}"
    app = _Application()
    exec(
        matches[0],
        {
            "tg_app": app,
            "CallbackQueryHandler": _CallbackQueryHandler,
            "handle_task_callback": handler,
        },
    )
    assert len(app.handlers) == 1
    return app.handlers[0]


def _actual_ready_callback():
    task_summary = (17, 5, 2, "script", "claude", 1, "Scene 1", "working", None, "", "now")
    full_task = (17, 5, 2, "script", "claude", 1, "Scene 1", "Prompt", "working", None, "", "now")
    message = SimpleNamespace()

    async def reply_text(text, **kwargs):
        message.text = text
        message.reply_markup = kwargs["reply_markup"]

    message.reply_text = reply_text
    namespace = _load_functions(
        "cmd_next_task",
        is_admin_user=lambda _uid: True,
        parse_key_value_args=lambda _raw: {},
        next_production_task=lambda _uid, job_id=None: task_summary,
        get_production_task=lambda _uid, _tid: full_task,
        operator_task_execution_runbook=lambda *_args: {
            "required_output": ["script"],
            "fallback_tools": ["claude"],
        },
        update_production_task=lambda *_args, **_kwargs: None,
        html_pre=lambda value, _limit=None: str(value),
    )
    update = SimpleNamespace(effective_user=SimpleNamespace(id=51), message=message)
    asyncio.run(namespace["cmd_next_task"](update, SimpleNamespace(args=[])))
    return next(
        button.callback_data
        for row in message.reply_markup.inline_keyboard
        for button in row
        if button.text == "✅ Ready"
    )


class ProductionTaskCallbackSingleAckTests(unittest.TestCase):
    def test_real_next_task_button_matches_real_registered_task_route(self):
        namespace = _load_functions("handle_task_callback")
        callback = _actual_ready_callback()
        route = _registered_task_route(namespace["handle_task_callback"])

        self.assertEqual(callback, "task|status|ready|17")
        self.assertIs(route.callback, namespace["handle_task_callback"])
        self.assertRegex(callback, route.pattern)

    def test_revoked_admin_gets_only_one_denial_ack_without_task_access(self):
        access = {"admin": True}
        task_calls = []

        def forbidden_task_action(*args, **kwargs):
            task_calls.append((args, kwargs))
            raise AssertionError("denied task callbacks must not read or update a production task")

        namespace = _load_functions(
            "handle_task_callback",
            is_admin_user=lambda _uid: access["admin"],
            get_production_task=forbidden_task_action,
            update_production_task=forbidden_task_action,
            html_pre=lambda value, _limit=None: str(value),
        )
        callback = _actual_ready_callback()
        route = _registered_task_route(namespace["handle_task_callback"])
        access["admin"] = False
        self.assertRegex(callback, route.pattern)

        query = _Query(51, callback)
        asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

        self.assertEqual(
            query.answers,
            [(("Chỉ Admin được dùng.",), {"show_alert": True})],
        )
        self.assertEqual(query.edits, [], "denied callbacks must not render an admin screen")
        self.assertEqual(task_calls, [], "denied callbacks must not access task state")

    def test_authorized_ready_button_keeps_one_ack_and_existing_status_update(self):
        updates = []
        full_task = (17, 5, 2, "script", "claude", 1, "Scene 1", "Prompt", "working", None, "", "now")

        namespace = _load_functions(
            "handle_task_callback",
            is_admin_user=lambda uid: uid == 51,
            get_production_task=lambda _uid, _tid: full_task,
            update_production_task=lambda *args, **kwargs: updates.append((args, kwargs)),
            html_pre=lambda value, _limit=None: str(value),
        )
        callback = _actual_ready_callback()
        route = _registered_task_route(namespace["handle_task_callback"])
        query = _Query(51, callback)

        asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

        self.assertEqual(query.answers, [((), {})])
        self.assertEqual(updates, [((51, 17), {"status": "ready"})])
        self.assertEqual(len(query.edits), 1)
        self.assertIn("Task #17 đã cập nhật status=<b>ready</b>", query.edits[0][0])


if __name__ == "__main__":
    unittest.main()
