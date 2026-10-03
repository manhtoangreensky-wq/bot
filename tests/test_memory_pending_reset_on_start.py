import asyncio
import html
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

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class _Query:
    def __init__(self, user_id):
        self.data = "memory|search"
        self.from_user = SimpleNamespace(id=user_id)

    async def answer(self, *_args, **_kwargs):
        return None


class MemoryPendingResetOnStartTests(unittest.TestCase):
    def _scope(self):
        async def noop_async(*_args, **_kwargs):
            return None

        async def allow_memory_access(_update):
            return True

        async def safe_edit_or_send(*_args, **_kwargs):
            return None

        scope = {
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "USER_PENDING": {},
            "QUICK_MEDIA_PENDING_TTL_SECONDS": 3600,
            "time": time,
            "html": html,
            "_short_pending_text": lambda value, limit: str(value)[:limit],
            "get_user_language": lambda _uid: "vi",
            "memory_can_use_full": lambda _uid: True,
            "safe_edit_or_send": safe_edit_or_send,
            "memory_search_prompt_text": lambda _lang: "Search memory",
            "memory_main_keyboard": lambda _lang: "memory-keyboard",
            "clear_media_creator_pending_states": lambda _uid: False,
            "clear_doc_tool_pending": lambda _uid: None,
            "user_ui_lang": lambda _uid: "vi",
            "ui_text": lambda *_args: "Pending input canceled",
            "log_command_received": lambda *_args: None,
            "user_exists": lambda _uid: True,
            "get_user": lambda *_args: None,
            "record_usage_event": lambda *_args, **_kwargs: None,
            "has_user_language": lambda _uid: True,
            "is_admin_user": lambda _uid: True,
            "localized_start_menu_text": lambda *_args: "main menu",
            "mode_start_notice": lambda _uid: "",
            "localized_main_menu_keyboard": lambda *_args: "main-keyboard",
            "maybe_auto_grant_birthday_gift": noop_async,
            "memory_require_access": allow_memory_access,
            "memory_list_notes": lambda *_args, **_kwargs: [],
            "normalize_user_language": lambda _lang: "vi",
            "memory_notes_list_text": lambda *_args: "empty results",
            "memory_notes_list_keyboard": lambda *_args: "empty-results-keyboard",
        }
        for helper in (
            "clear_pending_admin_tool_test", "clear_support_ticket_pending",
            "clear_internal_archive_pending", "clear_storage_addon_pending",
            "clear_translation_menu_pending", "clear_translation_session",
            "clear_broadcast_lite_pending",
        ):
            scope.setdefault(helper, lambda *_args, **_kwargs: None)
        for name in (
            "memory_guided_pending_key",
            "set_memory_guided_pending",
            "get_memory_guided_pending",
            "clear_memory_guided_pending",
            "clear_pending_start_notice",
            "handle_memory_callback",
            "handle_memory_pending_text",
            "cmd_start",
            "cmd_menu",
        ):
            exec(compile(_source_function(name), f"bot.py:{name}", "exec"), scope)
        return scope

    def test_start_and_menu_release_memory_search_without_clearing_other_state(self):
        self.assertRegex(BOT_SOURCE, r'tg_app\.add_handler\(CommandHandler\("start",\s*cmd_start\)')
        self.assertRegex(BOT_SOURCE, r'tg_app\.add_handler\(CommandHandler\("menu",\s*cmd_menu\)')
        self.assertIn('CallbackQueryHandler(handle_memory_callback, pattern=r"^memory\\|")', BOT_SOURCE)
        self.assertIn("if await handle_memory_pending_text(update, context):", BOT_SOURCE)

        for command_name, user_id in (("cmd_start", 841301), ("cmd_menu", 841302)):
            with self.subTest(command=command_name):
                scope = self._scope()
                unrelated_key = f"unrelated:{user_id}"
                unrelated_state = {"pending_action": "preserve"}
                scope["USER_PENDING"][unrelated_key] = unrelated_state.copy()

                query = _Query(user_id)
                asyncio.run(
                    scope["handle_memory_callback"](
                        SimpleNamespace(callback_query=query), SimpleNamespace(user_data={})
                    )
                )
                self.assertEqual(scope["get_memory_guided_pending"](user_id)["pending_action"], "search")

                user = SimpleNamespace(id=user_id, first_name="Tester", username="tester")
                command_update = SimpleNamespace(effective_user=user, message=_Message())
                context = SimpleNamespace(args=[], user_data={})
                asyncio.run(scope[command_name](command_update, context))

                pending_after_home = scope["get_memory_guided_pending"](user_id)
                ordinary_message = _Message("ordinary message after Home")
                text_update = SimpleNamespace(
                    message=ordinary_message,
                    effective_user=user,
                    effective_chat=SimpleNamespace(id=user_id),
                )
                consumed = asyncio.run(scope["handle_memory_pending_text"](text_update, context))

                self.assertIsNone(pending_after_home, "Home must release Memory's input ownership")
                self.assertFalse(consumed, "ordinary text after Home must not be treated as a Memory search")
                self.assertEqual(scope["USER_PENDING"].get(unrelated_key), unrelated_state)


if __name__ == "__main__":
    unittest.main()
