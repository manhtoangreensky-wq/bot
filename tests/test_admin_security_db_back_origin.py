"""Security/DB child screens must return to their Admin Security/DB module."""

import re
import unittest
from pathlib import Path


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


def _buttons(markup):
    return [
        (button.text, button.callback_data)
        for row in markup.inline_keyboard
        for button in row
    ]


class AdminSecurityDbBackOriginTests(unittest.TestCase):
    def test_security_db_module_children_keep_module_back_destination(self):
        self.assertIn('("🗄 DB trạng thái", "menu|admin_db_status")', BOT_SOURCE)
        self.assertIn('("🛡 Nhật ký bảo mật", "menu|admin_security_log")', BOT_SOURCE)

        namespace = {
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
        }
        for name in ("admin_db_status_keyboard", "security_log_keyboard"):
            exec(compile(_function_source(name), str(BOT_PATH), "exec"), namespace)

        for name in ("admin_db_status_keyboard", "security_log_keyboard"):
            with self.subTest(name=name):
                buttons = _buttons(namespace[name]())
                self.assertIn(("⬅️ Bảo mật / DB", "menu|admin_security_db"), buttons)
                self.assertNotIn(("⬅️ Admin menu", "menu|admin"), buttons)


if __name__ == "__main__":
    unittest.main()
