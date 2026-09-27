import asyncio
import re
import time
import unittest
from pathlib import Path
from types import SimpleNamespace


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def _source_function(name):
    start = re.search(rf"(?m)^(?:async )?def {re.escape(name)}\(", BOT_SOURCE)
    if not start:
        raise AssertionError(f"missing actual source function: {name}")
    following = re.search(r"(?m)^(?:async )?def [A-Za-z_]\w*\(", BOT_SOURCE[start.end():])
    end = start.end() + following.start() if following else len(BOT_SOURCE)
    return BOT_SOURCE[start.start():end]


class _Button:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class _Message:
    def __init__(self, text=""):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class FreeHubMaintenancePendingResetTest(unittest.TestCase):
    def test_main_maintenance_exit_clears_freehub_input_before_next_text(self):
        events = []
        generator_calls = []
        scope = {
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "USER_PENDING": {},
            "time": time,
            "FREE_HUB_PENDING_TTL_SECONDS": 600,
            "FREE_HUB_ENABLED": True,
            "public_hub_copy": lambda _lang: {"freehub_main": "Free Tools", "main_menu": "Home"},
            "normalize_user_language": lambda _lang: "vi",
            "get_user_language": lambda _uid: "vi",
            "localized_public_back_keyboard": lambda _lang: "maintenance keyboard",
            "free_hub_quota_payload": lambda _uid: {"allowed": True},
            "normalize_free_hub_task_type": lambda task_type: task_type,
            "free_hub_suggestion_items": lambda *_args: ["sample suggestion"],
            "free_hub_suggestions_text": lambda *_args: "suggestions",
            "free_hub_suggestions_keyboard": lambda *_args: "suggestions keyboard",
            "free_hub_input_text": lambda *_args: "enter custom input",
            "free_hub_quota_exhausted_text": lambda _lang: "quota exhausted",
            "free_hub_main_keyboard": lambda _lang: "free hub keyboard",
            "free_hub_generate_task_payload": lambda *_args: generator_calls.append("generator"),
            "safe_edit_or_send": None,
        }

        async def safe_edit_or_send(_query, text, **kwargs):
            events.append((text, kwargs.get("reply_markup")))
            return "rendered"

        scope["safe_edit_or_send"] = safe_edit_or_send
        for name in (
            "free_hub_pending_key",
            "set_free_hub_pending",
            "get_free_hub_pending",
            "clear_free_hub_pending",
            "free_hub_input_keyboard",
            "handle_free_hub_callback",
            "handle_free_hub_pending_text",
        ):
            exec(compile(_source_function(name), f"bot.py:{name}", "exec"), scope)

        self.assertIn(
            'CallbackQueryHandler(handle_free_hub_callback, pattern=r"^freehub\\|")',
            BOT_SOURCE,
        )
        handle_message = _source_function("handle_message")
        self.assertRegex(handle_message, r"if await handle_free_hub_pending_text\(update, context\):")

        async def answer():
            return None

        async def click(uid, data):
            query = SimpleNamespace(
                data=data,
                from_user=SimpleNamespace(id=uid),
                answer=answer,
                message=SimpleNamespace(),
            )
            return await scope["handle_free_hub_callback"](
                SimpleNamespace(callback_query=query), SimpleNamespace()
            )

        uid = 9031801
        # Exercise the real entry and custom-input callback branches.
        asyncio.run(click(uid, "freehub|meta"))
        asyncio.run(click(uid, "freehub|suggest_custom"))
        input_markup = events[-1][1]
        input_callbacks = [
            button.callback_data
            for row in input_markup.inline_keyboard
            for button in row
        ]
        self.assertIn("freehub|main", input_callbacks)
        self.assertEqual("input", scope["get_free_hub_pending"](uid)["step"])

        # Maintenance must preserve its response but release only Free Hub input state.
        scope["FREE_HUB_ENABLED"] = False
        scope["free_hub_quota_payload"] = lambda _uid: {"allowed": False}
        scope["USER_PENDING"]["unrelated:state"] = {"pending_action": "unrelated"}
        asyncio.run(click(uid, "freehub|main"))
        self.assertIn("đang bảo trì", events[-1][0])
        self.assertEqual("maintenance keyboard", events[-1][1])
        self.assertFalse(
            scope["get_free_hub_pending"](uid),
            "Free Hub main during maintenance must clear its pending input state",
        )
        self.assertEqual({"pending_action": "unrelated"}, scope["USER_PENDING"]["unrelated:state"])

        message = _Message("ordinary text after leaving Free Tools")
        consumed = asyncio.run(
            scope["handle_free_hub_pending_text"](
                SimpleNamespace(message=message, effective_user=SimpleNamespace(id=uid)),
                SimpleNamespace(),
            )
        )
        self.assertFalse(consumed, "ordinary text after leaving Free Tools must not be captured")
        self.assertEqual([], generator_calls, "test must not invoke any task generator/provider")


if __name__ == "__main__":
    unittest.main()
