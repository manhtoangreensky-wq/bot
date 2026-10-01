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


class _CapturedCallbackQueryHandler:
    def __init__(self, callback, pattern):
        self.callback = callback
        self.pattern = pattern


class _Application:
    def __init__(self):
        self.handlers = []

    def add_handler(self, handler):
        self.handlers.append(handler)


class _Connection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


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


def _registered_canary_route(handler):
    matches = [
        line.strip()
        for line in BOT_SOURCE.splitlines()
        if "tg_app.add_handler(CallbackQueryHandler(handle_remote_worker_canary_callback," in line
    ]
    assert len(matches) == 1, f"expected one canary lifecycle registration, got {len(matches)}"
    app = _Application()
    exec(
        matches[0],
        {
            "tg_app": app,
            "CallbackQueryHandler": _CapturedCallbackQueryHandler,
            "handle_remote_worker_canary_callback": handler,
        },
    )
    assert len(app.handlers) == 1
    return app.handlers[0]


def _visible_callbacks(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    ]


def _admin_denial_namespace(side_effects):
    def forbidden(name):
        def call(*_args, **_kwargs):
            side_effects.append(name)
            raise AssertionError(f"denied callback reached protected operation: {name}")
        return call

    return _load_functions(
        "_remote_worker_canary_keyboard",
        "_parse_remote_worker_canary_job_id",
        "_format_remote_worker_canary_status",
        "handle_remote_worker_canary_callback",
        is_admin_user=lambda _uid: False,
        worker_auth=SimpleNamespace(worker_api_runtime_flags=forbidden("worker_flags")),
        LOCAL_WORKER_TOKEN="test-only-token",
        remote_worker_api=SimpleNamespace(
            create_remote_worker_canary_job=forbidden("create_canary"),
            get_remote_worker_canary_status=forbidden("get_status"),
        ),
        db_connect=forbidden("db_connect"),
        get_system_setting=forbidden("get_setting"),
        set_system_setting=forbidden("set_setting"),
        safe_int=lambda value, default=0: int(value or default),
    )


class RemoteWorkerCanaryCallbackSingleAckTests(unittest.TestCase):
    def test_visible_canary_buttons_match_the_registered_handler(self):
        namespace = _load_functions("_remote_worker_canary_keyboard", "handle_remote_worker_canary_callback")
        callbacks = _visible_callbacks(namespace["_remote_worker_canary_keyboard"]("RW-CANARY-17"))
        route = _registered_canary_route(namespace["handle_remote_worker_canary_callback"])

        self.assertIs(route.callback, namespace["handle_remote_worker_canary_callback"])
        self.assertIn("remote_worker_canary_create", callbacks)
        self.assertIn("remote_worker_canary_status|RW-CANARY-17", callbacks)
        self.assertTrue(all(re.match(route.pattern, callback) for callback in callbacks[:2]))

    def test_stale_non_admin_create_button_gets_one_alert_and_no_worker_side_effect(self):
        effects = []
        namespace = _admin_denial_namespace(effects)
        callbacks = _visible_callbacks(namespace["_remote_worker_canary_keyboard"]())
        callback = next(value for value in callbacks if value == "remote_worker_canary_create")
        route = _registered_canary_route(namespace["handle_remote_worker_canary_callback"])
        self.assertRegex(callback, route.pattern)

        query = _Query(991122, callback)
        asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

        self.assertEqual(
            query.answers,
            [(("⛔ Khu vực này chỉ dành cho Admin.",), {"show_alert": True})],
        )
        self.assertEqual(query.edits, [])
        self.assertEqual(effects, [])

    def test_authorized_status_still_gets_one_normal_ack_and_existing_status_screen(self):
        connection = _Connection()
        status_calls = []

        def get_status(conn, *, job_id, admin_user_id):
            status_calls.append((conn, job_id, admin_user_id))
            return {"ok": False, "reason": "canary_not_found"}

        namespace = _load_functions(
            "_remote_worker_canary_keyboard",
            "_parse_remote_worker_canary_job_id",
            "_format_remote_worker_canary_status",
            "handle_remote_worker_canary_callback",
            is_admin_user=lambda uid: uid == 123,
            remote_worker_api=SimpleNamespace(get_remote_worker_canary_status=get_status),
            db_connect=lambda: connection,
            get_system_setting=lambda *_args: self.fail("explicit canary ref must not read fallback settings"),
            set_system_setting=lambda *_args: self.fail("not-found status must not write settings"),
            safe_int=lambda value, default=0: int(value or default),
        )
        callback = next(
            value
            for value in _visible_callbacks(namespace["_remote_worker_canary_keyboard"]("RW-CANARY-17"))
            if value == "remote_worker_canary_status|RW-CANARY-17"
        )
        route = _registered_canary_route(namespace["handle_remote_worker_canary_callback"])
        query = _Query(123, callback)
        asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

        self.assertEqual(query.answers, [((), {})])
        self.assertEqual(status_calls, [(connection, 17, 123)])
        self.assertTrue(connection.closed)
        self.assertIn("Chưa tìm thấy job canary an toàn.", query.edits[0][0])
        self.assertIn("remote_worker_canary_create", _visible_callbacks(query.edits[0][1]["reply_markup"]))


if __name__ == "__main__":
    unittest.main()
