import asyncio
import ast
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


def _admin_modules():
    start = BOT_SOURCE.index("ADMIN_CONTROL_MODULES = {")
    end = BOT_SOURCE.index("\ndef admin_module_command_lines", start)
    assignment = ast.parse(BOT_SOURCE[start:end], filename=str(BOT_PATH)).body[0]
    return ast.literal_eval(assignment.value)


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


def _load_functions(*names, **dependencies):
    namespace = {
        "SimpleNamespace": SimpleNamespace,
        "ADMIN_CONTROL_MODULES": _admin_modules(),
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        **dependencies,
    }
    source = "from __future__ import annotations\n\n" + "\n\n".join(
        _function_source(name) for name in names
    )
    exec(compile(source, str(BOT_PATH), "exec"), namespace)
    return namespace


class AdminHelpCallbackSingleAckTests(unittest.TestCase):
    def test_real_callback_route_is_registered(self):
        self.assertIn(
            r'tg_app.add_handler(CallbackQueryHandler(handle_admin_help_callback, pattern=r"^admin_help\|"))',
            BOT_SOURCE,
        )

    def test_stale_support_button_denied_to_non_admin_with_one_alert(self):
        async def safe_edit(query, text, **kwargs):
            query.edits.append((text, kwargs))

        namespace = _load_functions(
            "admin_module_keyboard",
            "handle_admin_help_callback",
            is_admin_user=lambda _uid: False,
            admin_handbook_section_text=lambda kind: f"handbook:{kind}",
            admin_handbook_section_keyboard=lambda kind, _return_action="": f"keyboard:{kind}",
            safe_edit_query_message=safe_edit,
        )
        markup = namespace["admin_module_keyboard"]("support")
        callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
        self.assertIn("admin_help|support|admin_support", callbacks)

        query = _Query(991122, "admin_help|support|admin_support")
        asyncio.run(namespace["handle_admin_help_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(),
        ))

        self.assertEqual(
            query.answers,
            [(("⛔ Khu vực này chỉ dành cho Admin.",), {"show_alert": True})],
        )
        self.assertEqual(query.edits, [], "denied stale callbacks must not render handbook content")

    def test_admin_gets_one_normal_ack_and_existing_handbook(self):
        async def safe_edit(query, text, **kwargs):
            query.edits.append((text, kwargs))

        namespace = _load_functions(
            "handle_admin_help_callback",
            is_admin_user=lambda uid: uid == 123,
            admin_handbook_section_text=lambda kind: f"handbook:{kind}",
            admin_handbook_section_keyboard=lambda kind, _return_action="": f"keyboard:{kind}",
            safe_edit_query_message=safe_edit,
        )
        query = _Query(123, "admin_help|support")
        asyncio.run(namespace["handle_admin_help_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(),
        ))

        self.assertEqual(query.answers, [((), {})])
        self.assertEqual(query.edits, [("handbook:support", {"reply_markup": "keyboard:support"})])

    def test_module_guide_back_returns_to_the_module_that_emitted_it(self):
        async def safe_edit(query, text, **kwargs):
            query.edits.append((text, kwargs))

        namespace = _load_functions(
            "admin_module_keyboard",
            "admin_handbook_section_keyboard",
            "handle_admin_help_callback",
            is_admin_user=lambda uid: uid == 123,
            admin_handbook_section_text=lambda kind: f"handbook:{kind}",
            safe_edit_query_message=safe_edit,
        )

        for module in namespace["ADMIN_CONTROL_MODULES"]:
            markup = namespace["admin_module_keyboard"](module)
            guides = [
                button
                for row in markup.inline_keyboard
                for button in row
                if button.callback_data.startswith("admin_help|")
            ]
            self.assertTrue(guides, module)
            expected_back = f"menu|admin_{module}"
            for guide in guides:
                self.assertEqual(
                    guide.callback_data.split("|")[2],
                    f"admin_{module}",
                    guide.text,
                )
                query = _Query(123, guide.callback_data)
                asyncio.run(namespace["handle_admin_help_callback"](
                    SimpleNamespace(callback_query=query), SimpleNamespace(),
                ))
                rendered = query.edits[0][1]["reply_markup"]
                back_buttons = [
                    button.callback_data
                    for row in rendered.inline_keyboard
                    for button in row
                ]
                self.assertIn(expected_back, back_buttons)
                self.assertNotIn("menu|admin", back_buttons)


if __name__ == "__main__":
    unittest.main()
