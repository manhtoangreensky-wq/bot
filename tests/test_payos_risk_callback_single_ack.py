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


def _registered_risk_route(handler):
    matches = [
        line.strip()
        for line in BOT_SOURCE.splitlines()
        if "tg_app.add_handler(CallbackQueryHandler(handle_payos_risk_callback," in line
    ]
    assert len(matches) == 1, f"expected one PayOS risk lifecycle registration, got {len(matches)}"
    app = _Application()
    exec(
        matches[0],
        {
            "tg_app": app,
            "CallbackQueryHandler": _CapturedCallbackQueryHandler,
            "handle_payos_risk_callback": handler,
        },
    )
    assert len(app.handlers) == 1
    return app.handlers[0]


class PayOSRiskCallbackSingleAckTests(unittest.TestCase):
    def test_emitted_report_button_matches_real_registered_risk_route(self):
        namespace = _load_functions("payos_risk_menu_keyboard", "handle_payos_risk_callback")
        markup = namespace["payos_risk_menu_keyboard"]()
        callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
        self.assertIn("payrisk|report", callbacks)

        route = _registered_risk_route(namespace["handle_payos_risk_callback"])
        self.assertIs(route.callback, namespace["handle_payos_risk_callback"])
        self.assertRegex("payrisk|report", route.pattern)

    def test_stale_non_admin_risk_button_gets_only_one_denial_ack_without_actions(self):
        access = {"admin": True}
        action_calls = []

        def forbidden_action(*args, **kwargs):
            action_calls.append((args, kwargs))
            raise AssertionError("denied risk callbacks must not run risk or audit actions")

        async def forbidden_edit(*args, **kwargs):
            action_calls.append((args, kwargs))
            raise AssertionError("denied risk callbacks must not render an admin screen")

        namespace = _load_functions(
            "payos_risk_menu_keyboard",
            "handle_payos_risk_callback",
            is_admin_user=lambda _uid: access["admin"],
            record_audit_event=forbidden_action,
            payos_risk_report_text=forbidden_action,
            payos_risk_report_keyboard=forbidden_action,
            safe_edit_query_message=forbidden_edit,
        )
        callback = next(
            button.callback_data
            for row in namespace["payos_risk_menu_keyboard"]().inline_keyboard
            for button in row
            if button.callback_data == "payrisk|report"
        )
        route = _registered_risk_route(namespace["handle_payos_risk_callback"])
        access["admin"] = False
        self.assertRegex(callback, route.pattern)

        query = _Query(991122, callback)
        asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

        self.assertEqual(
            query.answers,
            [(("Khu vực này chỉ dành cho Admin.",), {"show_alert": True})],
        )
        self.assertEqual(query.edits, [], "denied callbacks must not render or execute a risk action")
        self.assertEqual(action_calls, [], "denied callbacks must not reach report/audit operations")

    def test_authorized_help_button_keeps_one_ack_and_existing_help_screen(self):
        async def safe_edit_query_message(query, text, **kwargs):
            query.edits.append((text, kwargs))

        namespace = _load_functions(
            "payos_risk_menu_keyboard",
            "payos_risk_help_text",
            "handle_payos_risk_callback",
            is_admin_user=lambda uid: uid == 123,
            safe_edit_query_message=safe_edit_query_message,
        )
        callback = next(
            button.callback_data
            for row in namespace["payos_risk_menu_keyboard"]().inline_keyboard
            for button in row
            if button.callback_data == "payrisk|user_help"
        )
        route = _registered_risk_route(namespace["handle_payos_risk_callback"])
        query = _Query(123, callback)

        asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

        self.assertEqual(query.answers, [((), {})])
        self.assertEqual(len(query.edits), 1)
        self.assertIn("Tra rủi ro user/order", query.edits[0][0])
        self.assertEqual(
            query.edits[0][1]["reply_markup"].inline_keyboard[0][0].callback_data,
            "payrisk|review",
        )


if __name__ == "__main__":
    unittest.main()
