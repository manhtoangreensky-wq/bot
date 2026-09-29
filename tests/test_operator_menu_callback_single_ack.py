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


class OperatorMenuCallbackSingleAckTests(unittest.TestCase):
    def test_real_operator_menu_callback_route_is_registered(self):
        self.assertIn(
            r'tg_app.add_handler(CallbackQueryHandler(handle_operator_menu_callback, pattern=r"^opmenu\|"))',
            BOT_SOURCE,
        )

    def test_stale_operator_button_denies_non_admin_with_one_alert(self):
        namespace = _load_functions(
            "operator_menu_keyboard",
            "handle_operator_menu_callback",
            is_admin_user=lambda _uid: False,
        )
        markup = namespace["operator_menu_keyboard"]()
        callbacks = [
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
        ]
        self.assertIn("opmenu|cat_control", callbacks)

        query = _Query(991122, "opmenu|cat_control")
        asyncio.run(namespace["handle_operator_menu_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(),
        ))

        self.assertEqual(query.answers, [(("Chỉ Admin được dùng.",), {"show_alert": True})])
        self.assertEqual(query.edits, [], "denied stale callbacks must not open an operator command")

    def test_admin_category_keeps_one_normal_ack_and_existing_destination(self):
        namespace = _load_functions(
            "operator_menu_keyboard",
            "handle_operator_menu_callback",
            is_admin_user=lambda uid: uid == 123,
            operator_category_title=lambda action: f"title:{action}",
            operator_category_keyboard=lambda action: f"keyboard:{action}",
        )
        markup = namespace["operator_menu_keyboard"]()
        callback = next(
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.callback_data == "opmenu|cat_control"
        )
        query = _Query(123, callback)
        asyncio.run(namespace["handle_operator_menu_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(),
        ))

        self.assertEqual(query.answers, [((), {})])
        self.assertEqual(
            query.edits,
            [(
                "title:cat_control\n\nChọn mục cần thao tác:",
                {"parse_mode": "HTML", "reply_markup": "keyboard:cat_control"},
            )],
        )


if __name__ == "__main__":
    unittest.main()
