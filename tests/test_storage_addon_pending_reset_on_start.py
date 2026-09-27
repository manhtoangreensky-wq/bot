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


class _Message:
    def __init__(self, text=""):
        self.text = text
        self.replies = []

    async def reply_text(self, *args, **kwargs):
        self.replies.append((args, kwargs))


class _Query:
    def __init__(self, user_id):
        self.data = "storage|custom"
        self.from_user = SimpleNamespace(id=user_id)
        self.message = _Message()

    async def answer(self, *_args, **_kwargs):
        return None


class StorageAddonPendingResetOnStartTests(unittest.TestCase):
    def _scope(self):
        async def noop_async(*_args, **_kwargs):
            return None

        scope = {
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "USER_PENDING": {},
            "time": time,
            "QUICK_MEDIA_PENDING_TTL_SECONDS": 600,
            "get_user_language": lambda _uid: "vi",
            "user_ui_lang": lambda _uid: "vi",
            "safe_edit_or_send": noop_async,
            "InlineKeyboardMarkup": lambda rows: rows,
            "InlineKeyboardButton": lambda *args, **kwargs: (args, kwargs),
            "clear_media_creator_pending_states": lambda _uid: False,
            "clear_pending_start_notice": None,
            "storage_addon_spec_from_custom": lambda _text: None,
            "memory_storage_addon_keyboard": lambda *_args: "storage-keyboard",
            "start_storage_addon_purchase": lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("test must not create a storage purchase")
            ),
            "log_command_received": lambda *_args: None,
            "user_exists": lambda _uid: False,
            "get_user": lambda *_args: None,
            "record_usage_event": lambda *_args, **_kwargs: None,
            "is_admin_user": lambda _uid: True,
            "has_user_language": lambda _uid: True,
            "localized_start_menu_text": lambda *_args: "main menu",
            "mode_start_notice": lambda _uid: "",
            "localized_main_menu_keyboard": lambda *_args: "main-keyboard",
            "maybe_auto_grant_birthday_gift": noop_async,
            "asyncio": asyncio,
        }
        for name in (
            "storage_addon_pending_key",
            "set_storage_addon_pending",
            "get_storage_addon_pending",
            "clear_storage_addon_pending",
            "handle_storage_addon_callback",
            "handle_storage_addon_pending_text",
            "clear_pending_start_notice",
            "cmd_start",
            "cmd_menu",
        ):
            exec(compile(_source_function(name), f"bot.py:{name}", "exec"), scope)
        return scope

    def test_start_and_menu_release_custom_input_without_consuming_text(self):
        self.assertIn(
            'tg_app.add_handler(CallbackQueryHandler(handle_storage_addon_callback, pattern=r"^storage\\|"))',
            BOT_SOURCE,
        )
        self.assertRegex(BOT_SOURCE, r'tg_app\.add_handler\(CommandHandler\("start",\s*cmd_start\)')
        self.assertRegex(BOT_SOURCE, r'tg_app\.add_handler\(CommandHandler\("menu",\s*cmd_menu\)')
        self.assertIn("if await handle_storage_addon_pending_text(update, context):", BOT_SOURCE)

        for command_name, user_id in (("cmd_start", 842401), ("cmd_menu", 842402)):
            with self.subTest(command=command_name):
                scope = self._scope()
                unrelated_key = f"unrelated:{user_id}"
                unrelated_state = {"pending_action": "preserve"}
                scope["USER_PENDING"][unrelated_key] = unrelated_state.copy()

                query = _Query(user_id)
                asyncio.run(
                    scope["handle_storage_addon_callback"](
                        SimpleNamespace(callback_query=query), SimpleNamespace()
                    )
                )
                self.assertEqual(
                    scope["get_storage_addon_pending"](user_id).get("pending_action"), "custom"
                )

                user = SimpleNamespace(id=user_id, first_name="Tester", username="tester")
                command_update = SimpleNamespace(effective_user=user, message=_Message())
                context = SimpleNamespace(args=[], user_data={})
                asyncio.run(scope[command_name](command_update, context))

                state_after_home = dict(scope["get_storage_addon_pending"](user_id) or {})
                ordinary_message = _Message("ordinary text after Home")
                text_update = SimpleNamespace(
                    message=ordinary_message,
                    effective_user=user,
                    effective_chat=SimpleNamespace(id=user_id),
                )
                consumed = asyncio.run(scope["handle_storage_addon_pending_text"](text_update, context))

                with self.subTest(check="pending-state-release"):
                    self.assertEqual(state_after_home, {}, "Home must release the custom storage input")
                with self.subTest(check="ordinary-text-ownership"):
                    self.assertFalse(consumed, "ordinary text after Home must not enter the storage flow")
                with self.subTest(check="unrelated-pending-preserved"):
                    self.assertEqual(scope["USER_PENDING"].get(unrelated_key), unrelated_state)


if __name__ == "__main__":
    unittest.main()
