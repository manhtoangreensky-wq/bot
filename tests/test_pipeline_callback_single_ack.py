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


class _Message:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


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


class _CapturedCallbackQueryHandler:
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
        "re": re,
        **dependencies,
    }
    source = "from __future__ import annotations\n\n" + "\n\n".join(
        _function_source(name) for name in names
    )
    exec(compile(source, str(BOT_PATH), "exec"), namespace)
    return namespace


def _registered_pipeline_route(handler):
    matches = [
        line.strip()
        for line in BOT_SOURCE.splitlines()
        if "tg_app.add_handler(CallbackQueryHandler(handle_pipeline_callback," in line
    ]
    assert len(matches) == 1, f"expected one pipeline lifecycle registration, got {len(matches)}"
    app = _Application()
    exec(
        matches[0],
        {
            "tg_app": app,
            "CallbackQueryHandler": _CapturedCallbackQueryHandler,
            "handle_pipeline_callback": handler,
        },
    )
    assert len(app.handlers) == 1
    return app.handlers[0]


def _readiness_data(_user_id, job_id):
    assert job_id == 17
    job = (
        17, 1, 0, 2, 0, "tiktok", "fixture topic", "script", "working", "note", "brief",
        "", "", "fixture channel", "main", "", "fixture product", "https://example.invalid",
    )
    return {
        "job": job,
        "level": "BLOCKED",
        "checks": [],
        "variants": [],
        "selected_variant": None,
        "manifests": [],
        "tasks": [],
        "blocked_tasks": [],
        "assets": [],
        "final_asset": None,
        "publish_gate": {},
        "queue_items": [],
        "next_action": "/review_gate job=17",
    }


def _emitted_pipeline_callback(namespace):
    message = _Message()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        message=message,
    )
    context = SimpleNamespace(args=["17"])
    asyncio.run(namespace["cmd_job_ready"](update, context))
    markup = message.replies[0][1]["reply_markup"]
    callbacks = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    ]
    return next(value for value in callbacks if value == "pipe|stage|review|17")


def _forbidden(name, effects):
    def call(*_args, **_kwargs):
        effects.append(name)
        raise AssertionError(f"denied callback reached production-job operation: {name}")
    return call


class PipelineCallbackSingleAckTests(unittest.TestCase):
    def test_actual_job_ready_button_matches_registered_pipeline_route(self):
        namespace = _load_functions(
            "cmd_job_ready",
            "handle_pipeline_callback",
            is_admin_user=lambda uid: uid == 123,
            parse_key_value_args=lambda _raw: {"job": "17"},
            production_readiness_data=_readiness_data,
        )
        callback = _emitted_pipeline_callback(namespace)
        route = _registered_pipeline_route(namespace["handle_pipeline_callback"])

        self.assertIs(route.callback, namespace["handle_pipeline_callback"])
        self.assertRegex(callback, route.pattern)

    def test_stale_non_admin_pipeline_button_gets_one_alert_without_job_operation(self):
        access = {"admin": True}
        effects = []
        namespace = _load_functions(
            "cmd_job_ready",
            "handle_pipeline_callback",
            is_admin_user=lambda _uid: access["admin"],
            parse_key_value_args=lambda _raw: {"job": "17"},
            production_readiness_data=_readiness_data,
        )
        callback = _emitted_pipeline_callback(namespace)
        access["admin"] = False
        namespace["update_production_job"] = _forbidden("update_production_job", effects)
        namespace["get_production_job"] = _forbidden("get_production_job", effects)
        route = _registered_pipeline_route(namespace["handle_pipeline_callback"])
        self.assertRegex(callback, route.pattern)

        query = _Query(991122, callback)
        asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

        self.assertEqual(
            query.answers,
            [(('Chỉ Admin được dùng.',), {"show_alert": True})],
        )
        self.assertEqual(query.edits, [])
        self.assertEqual(effects, [])

    def test_authorized_pipeline_button_keeps_single_ack_and_existing_screen_with_fake_job(self):
        updates = []

        def update_job(*args, **kwargs):
            updates.append((args, kwargs))

        job = (17, 1, 0, 2, 0, "tiktok", "fixture topic", "review", "working")
        namespace = _load_functions(
            "cmd_job_ready",
            "handle_pipeline_callback",
            is_admin_user=lambda uid: uid == 123,
            parse_key_value_args=lambda _raw: {"job": "17"},
            production_readiness_data=_readiness_data,
            update_production_job=update_job,
            get_production_job=lambda job_id, user_id: job if (job_id, user_id) == (17, 123) else None,
        )
        callback = _emitted_pipeline_callback(namespace)
        route = _registered_pipeline_route(namespace["handle_pipeline_callback"])
        query = _Query(123, callback)
        asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

        self.assertEqual(query.answers, [((), {})])
        self.assertEqual(updates, [((17, 123), {"stage": "review", "status": "working"})])
        self.assertIn("Pipeline #17", query.edits[0][0])
        self.assertIn("Stage: <b>review</b>", query.edits[0][0])


if __name__ == "__main__":
    unittest.main()
