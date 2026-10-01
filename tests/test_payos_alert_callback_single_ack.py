import asyncio
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


def _load_functions(*names, **dependencies):
    namespace = {
        "SimpleNamespace": SimpleNamespace,
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        **dependencies,
    }
    source = "from __future__ import annotations\n\n" + "\n\n".join(
        _function_source(name) for name in names
    )
    exec(compile(source, str(BOT_PATH), "exec"), namespace)
    return namespace


def _registered_alert_route(handler):
    matches = [
        line.strip()
        for line in BOT_SOURCE.splitlines()
        if "tg_app.add_handler(CallbackQueryHandler(handle_payos_alert_callback," in line
    ]
    assert len(matches) == 1, f"expected one PayOS alert lifecycle registration, got {len(matches)}"
    app = _Application()
    exec(
        matches[0],
        {
            "tg_app": app,
            "CallbackQueryHandler": _CapturedCallbackQueryHandler,
            "handle_payos_alert_callback": handler,
        },
    )
    assert len(app.handlers) == 1
    return app.handlers[0]


class PayOSAlertCallbackSingleAckTests(unittest.TestCase):
    def test_emitted_test_button_matches_real_registered_alert_route(self):
        namespace = _load_functions("payos_alert_keyboard", "handle_payos_alert_callback")
        markup = namespace["payos_alert_keyboard"]()
        callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
        self.assertIn("payosalert|test", callbacks)

        route = _registered_alert_route(namespace["handle_payos_alert_callback"])
        self.assertIs(route.callback, namespace["handle_payos_alert_callback"])
        self.assertRegex("payosalert|test", route.pattern)

    def test_stale_non_admin_alert_button_gets_only_one_denial_ack(self):
        access = {"admin": True}
        namespace = _load_functions(
            "payos_alert_keyboard",
            "handle_payos_alert_callback",
            is_admin_user=lambda _uid: access["admin"],
        )
        markup = namespace["payos_alert_keyboard"]()
        callback = next(
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.callback_data == "payosalert|test"
        )
        access["admin"] = False
        route = _registered_alert_route(namespace["handle_payos_alert_callback"])
        self.assertRegex(callback, route.pattern)

        query = _Query(991122, callback)
        asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

        self.assertEqual(
            query.answers,
            [(("Lệnh này chỉ dành cho admin.",), {"show_alert": True})],
        )
        self.assertEqual(query.edits, [], "denied callbacks must not render or execute an action")

    def test_authorized_test_button_keeps_one_ack_and_existing_help(self):
        namespace = _load_functions(
            "payos_alert_keyboard",
            "handle_payos_alert_callback",
            is_admin_user=lambda uid: uid == 123,
        )
        callback = next(
            button.callback_data
            for row in namespace["payos_alert_keyboard"]().inline_keyboard
            for button in row
            if button.callback_data == "payosalert|test"
        )
        route = _registered_alert_route(namespace["handle_payos_alert_callback"])
        query = _Query(123, callback)

        asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

        self.assertEqual(query.answers, [((), {})])
        self.assertEqual(
            query.edits,
            [(
                "🧪 Dùng <code>/payos_debug_create 10000</code> để kiểm tra tạo checkout hoặc "
                "<code>/payos_env_check</code> để kiểm tra cấu hình đã mask. Các lệnh test "
                "không tự cộng Xu.",
                {"parse_mode": "HTML"},
            )],
        )


if __name__ == "__main__":
    unittest.main()
