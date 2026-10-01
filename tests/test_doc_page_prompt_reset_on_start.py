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
        self.data = "docflow|ask_pages"
        self.from_user = SimpleNamespace(id=user_id)

    async def answer(self, *_args, **_kwargs):
        return None


class DocPagePromptResetOnStartTests(unittest.TestCase):
    def _scope(self):
        async def noop_async(*_args, **_kwargs):
            return None

        scope = {
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "USER_PENDING": {},
            "time": time,
            "DOC_TOOL_STATE_TTL_SECONDS": 600,
            "DOC_TOOL_MAX_FILES": 20,
            "DOC_TOOL_CONFIG": {"split_pdf": {"expected": "pdf", "max_files": 5, "min_files": 1}},
            "now_text": lambda: "2026-09-27 00:00:00",
            "_short_pending_text": lambda value, limit: str(value)[:limit],
            "get_user_language": lambda _uid: "vi",
            "safe_edit_or_send": noop_async,
            "doc_tool_after_file_keyboard": lambda *_args: "document-keyboard",
            "doc_tool_confirm_text": lambda *_args: "document-confirm",
            "doc_tool_confirm_keyboard": lambda *_args: "confirm-keyboard",
            "clear_media_creator_pending_states": lambda _uid: False,
            "clear_memory_guided_pending": lambda _uid: None,
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
        }
        for name in (
            "doc_tool_pending_key",
            "get_doc_tool_pending",
            "set_doc_tool_pending",
            "clear_doc_tool_pending",
            "handle_doc_tool_callback",
            "handle_doc_tool_pending_text",
            "clear_pending_start_notice",
            "cmd_start",
            "cmd_menu",
        ):
            exec(compile(_source_function(name), f"bot.py:{name}", "exec"), scope)
        return scope

    def test_start_and_menu_release_page_range_without_clearing_other_state(self):
        self.assertRegex(BOT_SOURCE, r'tg_app\.add_handler\(CommandHandler\("start",\s*cmd_start\)')
        self.assertRegex(BOT_SOURCE, r'tg_app\.add_handler\(CommandHandler\("menu",\s*cmd_menu\)')
        self.assertIn('CallbackQueryHandler(handle_doc_tool_callback, pattern=r"^docflow\\|")', BOT_SOURCE)
        self.assertIn("if await handle_doc_tool_pending_text(update, context):", BOT_SOURCE)

        for command_name, user_id in (("cmd_start", 842301), ("cmd_menu", 842302)):
            with self.subTest(command=command_name):
                scope = self._scope()
                unrelated_key = f"unrelated:{user_id}"
                unrelated_state = {"pending_action": "preserve"}
                scope["USER_PENDING"][unrelated_key] = unrelated_state.copy()
                scope["set_doc_tool_pending"](
                    user_id,
                    "split_pdf",
                    doc_tool_files=[{"file_id": "inert-test-file", "file_name": "test.pdf"}],
                    doc_tool_options={},
                )

                query = _Query(user_id)
                asyncio.run(
                    scope["handle_doc_tool_callback"](
                        SimpleNamespace(callback_query=query), SimpleNamespace()
                    )
                )
                self.assertEqual(scope["get_doc_tool_pending"](user_id).get("awaiting_page_spec"), "1")

                user = SimpleNamespace(id=user_id, first_name="Tester", username="tester")
                command_update = SimpleNamespace(effective_user=user, message=_Message())
                context = SimpleNamespace(args=[], user_data={})
                asyncio.run(scope[command_name](command_update, context))

                state_after_home = dict(scope["get_doc_tool_pending"](user_id) or {})
                ordinary_message = _Message("ordinary text after Home")
                text_update = SimpleNamespace(
                    message=ordinary_message,
                    effective_user=user,
                    effective_chat=SimpleNamespace(id=user_id),
                )
                consumed = asyncio.run(scope["handle_doc_tool_pending_text"](text_update, context))

                self.assertEqual(state_after_home, {}, "Home must release the document page-range session")
                self.assertFalse(consumed, "ordinary text after Home must not become a page range")
                self.assertEqual(scope["USER_PENDING"].get(unrelated_key), unrelated_state)


if __name__ == "__main__":
    unittest.main()
