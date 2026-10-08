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
        "pkgcombo_large_order_callback": lambda *_args, **_kwargs: "pkgcombo:large_order:fixture",
        "public_task_package_entries": lambda group: [
            ("image_mini_monthly" if group == "image" else f"{group}_fixture", {"label": group, "group": group})
        ],
        "package_i18n_button_label": lambda entry, code, _kind, _lang: f"{entry['label']} {code}",
        "package_catalog_entry": lambda code, package_type: (
            {"group": "image", "manual": True}
            if package_type == "monthly" and code == "image_mini_monthly"
            else {"group": "combo", "manual": True, "label": "Fixture combo"}
            if package_type == "combo" and code == "combo_ad_video_588k"
            else None
        ),
        "package_purchase_detail_lines": lambda *_args: ["Package detail fixture"],
        "package_entry_auto_checkout_enabled": lambda _entry: False,
        "PACKAGE_TASK_GROUP_ORDER": (
            "image",
            "video",
            "music",
            "voice",
            "subtitle_dub",
            "prompt_workflow",
            "mixed",
        ),
        "pricing_packages_lines": lambda _lang: ["Packages screen"],
        "pricing_task_package_group_lines": lambda group, _lang: [f"{group} packages"],
        "public_video_combo_pricing_payload": lambda: [
            {"code": "combo_ad_video_588k", "label": "Fixture combo", "group": "combo"}
        ],
        "get_user_language": lambda _uid: "vi",
        "user_package_summary_text": lambda user_id, lang: f"My packages fixture {user_id} ({lang})",
    }
    for name in (
        "pkgcombo_group_callback",
        "package_group_for_code",
        "package_detail_back_callback",
        "pricing_packages_keyboard",
        "pricing_pkgcombo_notes_lines",
        "pricing_pkgcombo_notes_keyboard",
        "pricing_task_package_group_keyboard",
        "pricing_combo_keyboard",
        "my_packages_keyboard",
        "package_purchase_manual_keyboard",
        "render_pkgcombo_detail",
        "handle_pkgcombo_callback",
    ):
        exec(compile("from __future__ import annotations\n" + _source_function(name), f"bot.py:{name}", "exec"), scope)

    cleared = []
    scope["clear_media_creator_pending_states"] = lambda uid: cleared.append(uid)
    async def render(query, lines, markup):
        query.edits.append(("\n".join(lines), markup))
    scope["edit_or_send_pricing_lines"] = render
    scope["pricing_combo_lines"] = lambda _lang: ["Combo packages"]

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

    def test_emitted_package_detail_back_returns_to_origin_group_via_registered_handler(self):
        user_id = 90732
        scope, route, cleared = _runtime()
        package_menu = scope["pricing_packages_keyboard"]("vi")
        group_entry = next(
            button
            for row in package_menu.inline_keyboard
            for button in row
            if button.callback_data == "pkgcombo:group:image"
        )

        group_screen = _click(route, user_id, group_entry.callback_data)
        detail_entry = next(
            button
            for row in group_screen.edits[0][1].inline_keyboard
            for button in row
            if button.callback_data.startswith("pkgcombo:detail:")
        )
        self.assertEqual("pkgcombo:detail:image_mini_monthly", detail_entry.callback_data)

        detail_screen = _click(route, user_id, detail_entry.callback_data)
        self.assertEqual("Package detail fixture", detail_screen.edits[0][0])
        detail_buttons = [button for row in detail_screen.edits[0][1].inline_keyboard for button in row]
        back = next(button for button in detail_buttons if button.text.startswith("🔙"))
        self.assertEqual("pkgcombo:group:image", back.callback_data)

        returned = _click(route, user_id, back.callback_data)
        self.assertEqual("image packages", returned.edits[0][0])
        returned_callbacks = [
            button.callback_data
            for row in returned.edits[0][1].inline_keyboard
            for button in row
        ]
        self.assertEqual(
            [button.callback_data for row in group_screen.edits[0][1].inline_keyboard for button in row],
            returned_callbacks,
        )
        self.assertEqual([user_id, user_id, user_id], cleared)
        self.assertFalse(
            any(
                callback.startswith(("pkgbuy|", "pkgcombo:pay", "pkgcombo:combo_pay"))
                for callback in returned_callbacks
            )
        )

    def test_emitted_combo_detail_back_returns_to_combo_group_via_registered_handler(self):
        user_id = 90733
        scope, route, cleared = _runtime()
        package_menu = scope["pricing_packages_keyboard"]("vi")
        combo_entry = next(
            button
            for row in package_menu.inline_keyboard
            for button in row
            if button.callback_data == "pkgcombo:group:combo"
        )

        combo_group = _click(route, user_id, combo_entry.callback_data)
        self.assertEqual("Combo packages", combo_group.edits[0][0])
        detail_entry = next(
            button
            for row in combo_group.edits[0][1].inline_keyboard
            for button in row
            if button.callback_data.startswith("pkgcombo:combo_detail:")
        )
        self.assertEqual("pkgcombo:combo_detail:combo_ad_video_588k", detail_entry.callback_data)

        detail_screen = _click(route, user_id, detail_entry.callback_data)
        self.assertEqual("Package detail fixture", detail_screen.edits[0][0])
        detail_buttons = [button for row in detail_screen.edits[0][1].inline_keyboard for button in row]
        back = next(button for button in detail_buttons if button.text.startswith("🔙"))
        self.assertEqual("pkgcombo:group:combo", back.callback_data)

        returned = _click(route, user_id, back.callback_data)
        self.assertEqual("Combo packages", returned.edits[0][0])
        returned_callbacks = [
            button.callback_data
            for row in returned.edits[0][1].inline_keyboard
            for button in row
        ]
        self.assertEqual(
            [button.callback_data for row in combo_group.edits[0][1].inline_keyboard for button in row],
            returned_callbacks,
        )
        self.assertEqual([user_id, user_id, user_id], cleared)

    def test_emitted_package_notes_back_returns_to_same_package_home(self):
        user_id = 90734
        scope, route, cleared = _runtime()
        package_menu = scope["pricing_packages_keyboard"]("vi")
        package_callbacks = [
            button.callback_data
            for row in package_menu.inline_keyboard
            for button in row
        ]
        notes_entry = next(
            button
            for row in package_menu.inline_keyboard
            for button in row
            if button.callback_data == "pkgcombo:notes"
        )

        notes_screen = _click(route, user_id, notes_entry.callback_data)
        self.assertIn("ℹ️ <b>Lưu ý Gói / Combo</b>", notes_screen.edits[0][0])
        back = next(
            button
            for row in notes_screen.edits[0][1].inline_keyboard
            for button in row
            if button.text.startswith("⬅️")
        )
        self.assertEqual("pkgcombo:home", back.callback_data)

        returned = _click(route, user_id, back.callback_data)
        self.assertEqual("Packages screen", returned.edits[0][0])
        self.assertEqual(
            package_callbacks,
            [
                button.callback_data
                for row in returned.edits[0][1].inline_keyboard
                for button in row
            ],
        )
        self.assertEqual([user_id, user_id], cleared)

    def test_emitted_my_packages_back_returns_to_same_package_home(self):
        user_id = 90735
        scope, route, cleared = _runtime()
        package_menu = scope["pricing_packages_keyboard"]("vi")
        package_callbacks = [
            button.callback_data
            for row in package_menu.inline_keyboard
            for button in row
        ]
        my_packages_entry = next(
            button
            for row in package_menu.inline_keyboard
            for button in row
            if button.callback_data == "pkgcombo:my"
        )

        my_packages = _click(route, user_id, my_packages_entry.callback_data)
        self.assertEqual(f"My packages fixture {user_id} (vi)", my_packages.edits[0][0])
        back = next(
            button
            for row in my_packages.edits[0][1].inline_keyboard
            for button in row
            if button.text.startswith("⬅️")
        )
        self.assertEqual("pkgcombo:home", back.callback_data)

        returned = _click(route, user_id, back.callback_data)
        self.assertEqual("Packages screen", returned.edits[0][0])
        self.assertEqual(
            package_callbacks,
            [
                button.callback_data
                for row in returned.edits[0][1].inline_keyboard
                for button in row
            ],
        )
        self.assertEqual([user_id, user_id], cleared)


if __name__ == "__main__":
    unittest.main()
