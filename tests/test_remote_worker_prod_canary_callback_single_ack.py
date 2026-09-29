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
        return self


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
    def close(self):
        return None


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


def _registered_prod_canary_route(handler):
    matches = [
        line.strip()
        for line in BOT_SOURCE.splitlines()
        if "tg_app.add_handler(CallbackQueryHandler(handle_remote_worker_prod_canary_callback," in line
    ]
    assert len(matches) == 1, f"expected one prod-canary lifecycle registration, got {len(matches)}"
    app = _Application()
    exec(
        matches[0],
        {
            "tg_app": app,
            "CallbackQueryHandler": _CapturedCallbackQueryHandler,
            "handle_remote_worker_prod_canary_callback": handler,
        },
    )
    assert len(app.handlers) == 1
    return app.handlers[0]


def _status_namespace(is_admin_user, effects=None):
    effects = effects if effects is not None else []

    def get_status(conn, *, job_id, admin_user_id):
        effects.append(("get_status", job_id, admin_user_id))
        return {"ok": True, "canary_ref": "RW-PROD-CANARY-17", "status": "queued"}

    api = SimpleNamespace(
        get_remote_worker_admin_canary_status=get_status,
        create_remote_worker_admin_canary_job=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("status fixture must not create a canary job")
        ),
    )
    return _load_functions(
        "_remote_worker_prod_canary_keyboard",
        "cmd_remote_worker_prod_canary_status",
        "handle_remote_worker_prod_canary_callback",
        is_admin_user=is_admin_user,
        db_connect=lambda: _Connection(),
        remote_worker_api=api,
        safe_int=lambda value, default=0: int(value or default),
        get_system_setting=lambda *_args: "17",
        set_system_setting=lambda *args: effects.append(("set_setting", args[0])),
        _parse_remote_worker_canary_job_id=lambda _args: 17,
        _format_remote_worker_prod_canary_status=lambda status: f"status={status.get('status')}",
        logger=SimpleNamespace(warning=lambda *_args: None),
        effects=effects,
    )


def _emitted_status_callback(namespace):
    message = _Message()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        message=message,
    )
    context = SimpleNamespace(args=["17"])
    asyncio.run(namespace["cmd_remote_worker_prod_canary_status"](update, context))
    markup = message.replies[0][1]["reply_markup"]
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    return next(value for value in callbacks if value == "remote_worker_prod_canary_status|RW-PROD-CANARY-17")


def _forbidden(name, effects):
    def call(*_args, **_kwargs):
        effects.append(name)
        raise AssertionError(f"denied callback reached protected operation: {name}")
    return call


class RemoteWorkerProdCanaryCallbackSingleAckTests(unittest.TestCase):
    def test_actual_keyboard_button_matches_registered_prod_canary_route(self):
        namespace = _status_namespace(lambda uid: uid == 123)
        callback = _emitted_status_callback(namespace)
        route = _registered_prod_canary_route(namespace["handle_remote_worker_prod_canary_callback"])

        self.assertIs(route.callback, namespace["handle_remote_worker_prod_canary_callback"])
        self.assertRegex(callback, route.pattern)

    def test_stale_non_admin_status_button_gets_one_alert_before_any_worker_or_db_access(self):
        access = {"admin": True}
        effects = []
        namespace = _status_namespace(lambda _uid: access["admin"], effects)
        callback = _emitted_status_callback(namespace)
        access["admin"] = False

        namespace["db_connect"] = _forbidden("db_connect", effects)
        namespace["remote_worker_api"].get_remote_worker_admin_canary_status = _forbidden("get_status", effects)
        namespace["remote_worker_api"].create_remote_worker_admin_canary_job = _forbidden("create_job", effects)
        namespace["get_system_setting"] = _forbidden("get_system_setting", effects)
        namespace["set_system_setting"] = _forbidden("set_system_setting", effects)
        route = _registered_prod_canary_route(namespace["handle_remote_worker_prod_canary_callback"])
        self.assertRegex(callback, route.pattern)
        effects.clear()

        query = _Query(991122, callback)
        asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

        self.assertEqual(query.answers, [(('⛔ Khu vực này chỉ dành cho Admin.',), {"show_alert": True})])
        self.assertEqual(query.edits, [])
        self.assertEqual(effects, [])

    def test_authorized_status_keeps_one_ack_and_existing_screen_with_fake_seams(self):
        effects = []
        namespace = _status_namespace(lambda uid: uid == 123, effects)
        callback = _emitted_status_callback(namespace)
        route = _registered_prod_canary_route(namespace["handle_remote_worker_prod_canary_callback"])
        namespace["db_connect"] = lambda: _Connection()

        query = _Query(123, callback)
        asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

        self.assertEqual(query.answers, [((), {})])
        self.assertEqual(effects.count(("get_status", 17, 123)), 2)
        self.assertIn("status=queued", query.edits[0][0])
        self.assertIsInstance(query.edits[0][1]["reply_markup"], _Markup)


if __name__ == "__main__":
    unittest.main()
