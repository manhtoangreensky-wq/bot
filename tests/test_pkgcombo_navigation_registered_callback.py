"""Exercise a customer package Back route through its registered handler."""
import asyncio
import re
from pathlib import Path
from types import SimpleNamespace

import unittest


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


class _Button:
    def __init__(self, text, callback_data=None, **_kwargs):
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


def _source_function(name):
    match = re.search(
        rf"(?ms)^(?:async )?def {re.escape(name)}\(.*?(?=^(?:async )?def |\Z)",
        BOT_SOURCE,
    )
    if not match:
        raise AssertionError(f"missing source function: {name}")
    return match.group(0)


def _runtime():
    scope = {
        "__builtins__": __builtins__,
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "public_pricing_locale": lambda lang: lang,
        "pricing_copy_language": lambda lang: lang,
        "pkgcombo_normalize_group": lambda group: group,
        "pkgcombo_large_order_callback": lambda _origin, group: f"pkgcombo:large_order:group:{group}",
        "public_task_package_entries": lambda group: [(f"{group}_fixture", {"label": group})],
        "package_i18n_button_label": lambda entry, code, _kind, _lang: f"{entry['label']} {code}",
        "pricing_packages_lines": lambda _lang: ["Packages screen"],
        "pricing_task_package_group_lines": lambda group, _lang: [f"{group} packages"],
        "get_user_language": lambda _uid: "vi",
    }
    for name in (
        "pricing_packages_keyboard",
        "pricing_task_package_group_keyboard",
        "handle_pkgcombo_callback",
    ):
        exec(compile("from __future__ import annotations\n" + _source_function(name), f"bot.py:{name}", "exec"), scope)

    cleared = []
    scope["clear_media_creator_pending_states"] = lambda uid: cleared.append(uid)
    async def render(query, lines, markup):
        query.edits.append(("\n".join(lines), markup))
    scope["edit_or_send_pricing_lines"] = render
    scope["pricing_combo_lines"] = lambda _lang: ["Combo packages"]
    scope["pricing_combo_keyboard"] = lambda _lang: _Markup([])

    routes = []
    scope.update(
        tg_app=SimpleNamespace(add_handler=routes.append),
        CallbackQueryHandler=lambda handler, pattern: (handler, re.compile(pattern)),
    )
    registration = next(
        line.strip()
        for line in BOT_SOURCE.splitlines()
        if "tg_app.add_handler(CallbackQueryHandler(handle_pkgcombo_callback," in line
    )
    exec(registration, scope)
    if len(routes) != 1:
        raise AssertionError("expected exactly one registered package-combo callback")
    return scope, routes[0], cleared


def _click(route, user_id, callback_data):
    handler, pattern = route
    if not pattern.search(callback_data):
        raise AssertionError(f"registered route does not accept {callback_data!r}")
    query = _Query(user_id, callback_data)
    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))
    if query.answers != [((), {})]:
        raise AssertionError(f"callback acknowledgement mismatch: {query.answers!r}")
    return query


class PackageComboNavigationTests(unittest.TestCase):
    def test_emitted_image_group_back_returns_to_packages_via_registered_handler(self):
        user_id = 90731
        scope, route, cleared = _runtime()
        package_menu = scope["pricing_packages_keyboard"]("vi")
        menu_buttons = [button for row in package_menu.inline_keyboard for button in row]
        group_entry = next(button for button in menu_buttons if button.callback_data == "pkgcombo:group:image")
        self.assertEqual("🖼 Gói Ảnh", group_entry.text)

        group_screen = _click(route, user_id, group_entry.callback_data)
        self.assertEqual("image packages", group_screen.edits[0][0])
        group_markup = group_screen.edits[0][1]
        back = next(button for row in group_markup.inline_keyboard for button in row if button.text.startswith("⬅"))
        self.assertEqual("pkgcombo:home", back.callback_data)

        returned = _click(route, user_id, back.callback_data)
        self.assertEqual("Packages screen", returned.edits[0][0])
        returned_callbacks = [
            button.callback_data
            for row in returned.edits[0][1].inline_keyboard
            for button in row
        ]
        self.assertEqual(
            [button.callback_data for button in menu_buttons],
            returned_callbacks,
        )
        self.assertIn("pricing|main", returned_callbacks)
        self.assertIn("menu|main", returned_callbacks)
        self.assertEqual([user_id, user_id], cleared)


if __name__ == "__main__":
    unittest.main()
