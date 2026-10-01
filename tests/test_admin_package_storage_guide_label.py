import asyncio
import re
import unittest
from pathlib import Path
from types import SimpleNamespace


BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"
BOT_SOURCE = BOT_PATH.read_text(encoding="utf-8")


def _source_block(name, *, assignment=False):
    if assignment:
        pattern = rf"(?ms)^{re.escape(name)}\s*=.*?(?=^\w+\s*=|^async def |^def |^class |\Z)"
    else:
        pattern = rf"(?ms)^(?:async )?def {re.escape(name)}\(.*?(?=^async def |^def |^class |^[A-Z][A-Z0-9_]*\s*=|\Z)"
    match = re.search(pattern, BOT_SOURCE)
    assert match is not None, f"missing source block: {name}"
    return match.group(0).rstrip()


class _Button:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class _Query:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(id=123)
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _load(*names, **dependencies):
    namespace = {
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "SimpleNamespace": SimpleNamespace,
        **dependencies,
    }
    blocks = []
    for name in names:
        blocks.append(_source_block(name, assignment=name == "ADMIN_CONTROL_MODULES"))
    exec(
        compile(
            "from __future__ import annotations\n\n" + "\n\n".join(blocks),
            str(BOT_PATH),
            "exec",
        ),
        namespace,
    )
    return namespace


def _registered_admin_help_pattern():
    lines = [
        line.strip()
        for line in BOT_SOURCE.splitlines()
        if "CallbackQueryHandler(handle_admin_help_callback," in line
    ]
    assert len(lines) == 1, f"expected one admin-help route, got {len(lines)}"
    assert "pattern=r\"^admin_help\\|\"" in lines[0]
    return re.compile(r"^admin_help\|")


class AdminPackageStorageGuideLabelTests(unittest.TestCase):
    def test_package_storage_emitter_uses_guide_label_and_registered_route(self):
        namespace = _load("ADMIN_CONTROL_MODULES", "admin_module_keyboard")
        markup = namespace["admin_module_keyboard"]("packages")
        buttons = {
            button.text: button.callback_data
            for row in markup.inline_keyboard
            for button in row
        }

        self.assertEqual(buttons.get("📘 Cách cấp lưu trữ"), "admin_help|packages")
        self.assertNotIn("💾 Cấp lưu trữ", buttons)
        self.assertRegex("admin_help|packages", _registered_admin_help_pattern())

    def test_registered_admin_help_handler_renders_package_handbook(self):
        edited = []

        async def safe_edit_query_message(query, text, **kwargs):
            edited.append((text, kwargs))

        namespace = _load(
            "admin_handbook_section_text",
            "admin_handbook_section_keyboard",
            "handle_admin_help_callback",
            is_admin_user=lambda user_id: user_id == 123,
            safe_edit_query_message=safe_edit_query_message,
        )
        query = _Query("admin_help|packages")
        asyncio.run(
            namespace["handle_admin_help_callback"](
                SimpleNamespace(callback_query=query), SimpleNamespace()
            )
        )

        self.assertEqual(query.answers, [((), {})])
        self.assertEqual(len(edited), 1)
        self.assertIn("📘 Gói / Combo", edited[0][0])
        self.assertIn("/package_catalog", edited[0][0])
        callbacks = {
            button.callback_data
            for row in edited[0][1]["reply_markup"].inline_keyboard
            for button in row
        }
        self.assertTrue({"menu|admin_handbook", "menu|admin", "menu|main"} <= callbacks)


if __name__ == "__main__":
    unittest.main()
