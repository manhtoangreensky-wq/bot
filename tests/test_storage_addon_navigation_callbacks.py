"""Exercise Storage Add-on custom-input Back through its registered callback."""
import asyncio
import re
import time
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
import unittest


SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


class _Button:
    def __init__(self, text, callback_data=None, **kwargs):
        self.text = text
        self.callback_data = callback_data
        self.url = kwargs.get("url")


class _Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class _Query:
    def __init__(self, data, user_id):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = object()
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _source_function(name):
    start = re.search(rf"(?m)^(?:async )?def {re.escape(name)}\(", SOURCE)
    assert start, f"missing source function: {name}"
    following = re.search(r"(?m)^(?:async )?def [A-Za-z_]\w*\(", SOURCE[start.end():])
    end = start.end() + following.start() if following else len(SOURCE)
    return SOURCE[start.start():end]


def _runtime():
    screens = []
    routes = []
    tiers = [{"code": "test-tier", "addon_mb": 50, "amount_vnd": 10000}]

    async def render(query, text, **kwargs):
        screens.append((query, text, kwargs))

    scope = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "public_hub_copy": lambda _lang: defaultdict(
            lambda: "label",
            {
                "storage_addon_custom": "Custom amount",
                "storage_addon_back": "Back to Notes",
                "common_main_menu": "Main menu",
            },
        ),
        "normalize_user_language": lambda lang: lang,
        "storage_addon_tiers": lambda: tiers,
        "storage_addon_label": lambda _spec: "50MB",
        "get_user_language": lambda _uid: "vi",
        "safe_edit_or_send": render,
        "memory_storage_addon_text": lambda _lang: "Storage add-on menu",
        "time": time,
        "QUICK_MEDIA_PENDING_TTL_SECONDS": 600,
        "USER_PENDING": {},
        "start_storage_addon_purchase": lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("navigation must not start a purchase")
        ),
    }
    for name in (
        "memory_storage_addon_keyboard",
        "storage_addon_pending_key",
        "set_storage_addon_pending",
        "get_storage_addon_pending",
        "clear_storage_addon_pending",
        "handle_storage_addon_callback",
    ):
        exec(compile(_source_function(name), f"bot.py:{name}", "exec"), scope)

    registration = re.search(
        r"(?m)^\s*tg_app\.add_handler\(CallbackQueryHandler\(handle_storage_addon_callback,.*$",
        SOURCE,
    )
    assert registration, "storage callback registration is missing"
    scope.update(
        tg_app=SimpleNamespace(add_handler=routes.append),
        CallbackQueryHandler=lambda callback, pattern: (callback, re.compile(pattern)),
    )
    exec(compile(registration.group(0).strip(), "bot.py:storage callback registration", "exec"), scope)
    assert len(routes) == 1
    callback, pattern = routes[0]
    return scope, screens, callback, pattern


def _click(callback, pattern, data, user_id):
    assert pattern.search(data), f"registered storage handler does not accept {data!r}"
    query = _Query(data, user_id)
    asyncio.run(callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert query.answers == [((), {})]
    return query


class StorageAddonNavigationCallbacksTests(unittest.TestCase):
    def test_custom_amount_back_returns_to_storage_menu_and_keeps_memory_parent_route(self):
        user_id = 90817
        scope, screens, callback, pattern = _runtime()
        menu = scope["memory_storage_addon_keyboard"]("vi")
        menu_buttons = [button for row in menu.inline_keyboard for button in row]
        custom = next(button for button in menu_buttons if button.callback_data == "storage|custom")
        parent_back = next(button for button in menu_buttons if button.text.startswith("⬅️"))
        self.assertEqual(parent_back.callback_data, "menu|main_memory")
        menu_route = re.search(
            r"CallbackQueryHandler\(handle_menu_callback,\s*pattern=r(['\"])(.*?)\1",
            SOURCE,
        )
        self.assertIsNotNone(menu_route)
        self.assertRegex(parent_back.callback_data, re.compile(menu_route.group(2)))

        _click(callback, pattern, custom.callback_data, user_id)
        pending = scope["get_storage_addon_pending"](user_id)
        self.assertEqual(pending["pending_action"], "custom")
        custom_markup = screens[-1][2]["reply_markup"]
        custom_buttons = [button for row in custom_markup.inline_keyboard for button in row]
        back = next(button for button in custom_buttons if button.text.startswith("⬅️"))
        home = next(button for button in custom_buttons if button.text.startswith("🏠"))
        self.assertEqual(back.callback_data, "storage|menu")
        self.assertEqual(home.callback_data, "menu|main")

        _click(callback, pattern, back.callback_data, user_id)
        self.assertIsNone(scope["get_storage_addon_pending"](user_id))
        self.assertEqual(screens[-1][1], "Storage add-on menu")
        self.assertEqual(
            [
                button.callback_data
                for row in screens[-1][2]["reply_markup"].inline_keyboard
                for button in row
            ],
            [button.callback_data for button in menu_buttons],
        )


if __name__ == "__main__":
    unittest.main()
