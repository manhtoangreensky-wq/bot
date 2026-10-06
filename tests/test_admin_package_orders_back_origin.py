"""Admin package-order Back must return to the package module that opened it."""

import asyncio
import html
import re
import unittest
from pathlib import Path
from types import SimpleNamespace


BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"
BOT_SOURCE = BOT_PATH.read_text(encoding="utf-8")


def _function_source(name):
    start = re.search(rf"(?m)^(?:async )?def {name}\(", BOT_SOURCE)
    if not start:
        raise AssertionError(f"missing production function: {name}")
    following = re.search(r"(?m)^(?:async )?def \w+\(", BOT_SOURCE[start.end():])
    end = start.end() + following.start() if following else len(BOT_SOURCE)
    return BOT_SOURCE[start.start():end]


class _Button:
    def __init__(self, text, callback_data=None, **_kwargs):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class _Query:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(id=9001, username="admin", first_name="Admin")
        self.message = SimpleNamespace(chat_id=9001)
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _buttons(markup):
    return [
        (button.text, button.callback_data)
        for row in markup.inline_keyboard
        for button in row
    ]


class AdminPackageOrdersBackOriginTests(unittest.TestCase):
    def test_package_orders_entry_and_back_keep_opening_module_origin(self):
        self.assertIn('(\"📦 Đơn chờ duyệt\", \"menu|admin_package_orders|admin_packages\")', BOT_SOURCE)
        self.assertIn('callback_data="menu|admin_package_orders|finance"', BOT_SOURCE)

        namespace = {
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
        }
        exec(compile(_function_source("admin_package_orders_keyboard"), str(BOT_PATH), "exec"), namespace)

        child_buttons = _buttons(namespace["admin_package_orders_keyboard"]())
        self.assertIn(("⬅️ Gói / Combo", "menu|admin_packages"), child_buttons)
        self.assertNotIn(("⬅️ Tài chính", "menu|finance"), child_buttons)

        finance_buttons = _buttons(namespace["admin_package_orders_keyboard"]("finance"))
        self.assertIn(("⬅️ Tài chính", "menu|finance"), finance_buttons)
        self.assertNotIn(("⬅️ Gói / Combo", "menu|admin_packages"), finance_buttons)

    def test_registered_menu_handler_preserves_each_opening_origin(self):
        rendered = {}

        async def capture_render(_query, text, **kwargs):
            rendered["text"] = text
            rendered["reply_markup"] = kwargs.get("reply_markup")

        namespace = {
            "__builtins__": __builtins__,
            "html": SimpleNamespace(escape=html.escape),
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "Update": object,
            "VIDEO_TAIL9_TEXT_INPUT_KEY": "video_tail9_input",
            "DOC_TOOL_MENU_ACTIONS": set(),
            "normalize_user_language": lambda value: value or "vi",
            "localized_start_menu_text": lambda _user_id, _lang: "MAIN",
            "localized_main_menu_keyboard": lambda *_args: _Markup([]),
            "get_user_language": lambda _user_id: "vi",
            "is_admin_user": lambda _user_id: True,
            "safe_edit_query_message": capture_render,
            "localized_menu_content": lambda *_args: ("PACKAGE ORDERS", _Markup([])),
        }
        for helper in (
            "clear_broadcast_lite_pending", "clear_translation_menu_pending",
            "clear_translation_session", "clear_media_creator_pending_states",
            "clear_support_ticket_pending", "clear_finance_compliance_pending",
            "clear_internal_archive_pending", "clear_doc_tool_pending",
            "clear_storage_addon_pending", "clear_memory_guided_pending",
            "clear_music_guided_pending", "clear_pending_admin_tool_test",
        ):
            namespace[helper] = lambda *_args, **_kwargs: None
        exec(compile(_function_source("admin_package_orders_keyboard"), str(BOT_PATH), "exec"), namespace)
        exec(compile(_function_source("handle_menu_callback"), str(BOT_PATH), "exec"), namespace)

        for origin, expected in (("admin_packages", "menu|admin_packages"), ("finance", "menu|finance")):
            rendered.clear()
            query = _Query(f"menu|admin_package_orders|{origin}")
            update = SimpleNamespace(callback_query=query)
            asyncio.run(namespace["handle_menu_callback"](update, SimpleNamespace(user_data={})))
            callbacks = [
                button.callback_data
                for row in rendered["reply_markup"].inline_keyboard
                for button in row
            ]
            self.assertIn(expected, callbacks)


if __name__ == "__main__":
    unittest.main()
