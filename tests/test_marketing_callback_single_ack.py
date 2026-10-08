import ast
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


class MarketingCallbackSingleAckTests(unittest.TestCase):
    def test_real_marketing_callback_route_is_registered(self):
        self.assertIn(
            r'tg_app.add_handler(CallbackQueryHandler(handle_marketing_callback, pattern=r"^marketing\|"))',
            BOT_SOURCE,
        )

    def test_support_marketing_button_denies_non_admin_with_one_alert(self):
        async def safe_edit(query, text, **kwargs):
            query.edits.append((text, kwargs))

        effects = []
        namespace = _load_functions(
            "admin_module_keyboard",
            "handle_marketing_callback",
            is_admin_user=lambda _uid: False,
            safe_edit_or_send=safe_edit,
            get_marketing_pending=lambda _uid: effects.append("get_pending") or {},
            clear_marketing_pending=lambda _uid: effects.append("clear_pending"),
            VIDEO_WAITING_LOCK_ENABLED=False,
        )
        markup = namespace["admin_module_keyboard"]("support")
        callbacks = [
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
        ]
        self.assertIn("marketing|start|admin_support", callbacks)

        query = _Query(991122, "marketing|start")
        asyncio.run(namespace["handle_marketing_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(),
        ))

        self.assertEqual(
            query.answers,
            [(("Tính năng Marketing tự động đang thử nghiệm nội bộ. Hiện chỉ admin sử dụng.",), {"show_alert": True})],
        )
        self.assertEqual(query.edits, [], "unauthorized callbacks must not display marketing content")
        self.assertEqual(effects, [], "denial must stop before accessing or clearing marketing state")

    def test_admin_gets_one_normal_ack_and_existing_marketing_menu(self):
        async def safe_edit(query, text, **kwargs):
            query.edits.append((text, kwargs))

        effects = []

        def video_v6_keyboard(items, lang, main=False, back=None):
            return {"items": items, "lang": lang, "main": main, "back": back}

        namespace = _load_functions(
            "marketing_menu_keyboard",
            "handle_marketing_callback",
            is_admin_user=lambda uid: uid == 123,
            get_marketing_pending=lambda _uid: {},
            clear_marketing_pending=lambda uid: effects.append(("clear_pending", uid)),
            safe_edit_or_send=safe_edit,
            marketing_menu_text=lambda: "existing-marketing-menu",
            video_v6_keyboard=video_v6_keyboard,
            VIDEO_WAITING_LOCK_ENABLED=False,
        )
        query = _Query(123, "marketing|start")
        asyncio.run(namespace["handle_marketing_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(),
        ))

        self.assertEqual(query.answers, [((), {})])
        self.assertEqual(effects, [("clear_pending", 123)])
        self.assertEqual(
            query.edits,
            [(
                "existing-marketing-menu",
                {
                    "parse_mode": "HTML",
                    "reply_markup": {
                        "items": [
                            ("📦 Sản phẩm vật lý", "marketing|kind|physical"),
                            ("💻 Dịch vụ / App", "marketing|kind|service"),
                            ("🎁 Affiliate", "marketing|kind|affiliate"),
                            ("🏢 Địa điểm / BĐS", "marketing|kind|realestate"),
                            ("🍽 F&B", "marketing|kind|food"),
                            ("✍️ Nhập ngành khác", "marketing|kind_custom"),
                        ],
                        "lang": "vi",
                        "main": False,
                        "back": ("⬅️ Quản trị", "menu|admin"),
                    },
                },
            )],
        )


if __name__ == "__main__":
    unittest.main()
