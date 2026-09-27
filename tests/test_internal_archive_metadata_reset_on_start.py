import asyncio
import re
import textwrap
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


def _archive_dispatch_function_source():
    block = re.search(
        r"(?m)^    if await handle_internal_archive_pending_text\(update, context\):\n        return\s*$",
        BOT_SOURCE,
    )
    if not block:
        raise AssertionError("missing actual Internal Archive dispatch branch")
    return "async def dispatch_internal_archive_pending_text(update, context):\n" + textwrap.indent(
        textwrap.dedent(block.group(0)), "    "
    )


class _Message:
    def __init__(self, text=""):
        self.text = text
        self.replies = []

    async def reply_text(self, *args, **kwargs):
        self.replies.append((args, kwargs))


class _Query:
    def __init__(self, user_id):
        self.data = "archive|edit"
        self.from_user = SimpleNamespace(id=user_id)
        self.message = _Message()

    async def answer(self, *_args, **_kwargs):
        return None


class InternalArchiveMetadataResetOnStartTests(unittest.TestCase):
    def _scope(self):
        async def noop_async(*_args, **_kwargs):
            return None

        scope = {
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "USER_PENDING": {},
            "time": time,
            "INTERNAL_ARCHIVE_TTL_SECONDS": 900,
            "is_admin_user": lambda _uid: True,
            "get_user_language": lambda _uid: "vi",
            "user_ui_lang": lambda _uid: "vi",
            "safe_edit_query_message": noop_async,
            "InlineKeyboardMarkup": lambda rows: rows,
            "InlineKeyboardButton": lambda *args, **kwargs: (args, kwargs),
            "clear_doc_tool_pending": lambda _uid: False,
            "clear_media_creator_pending_states": lambda _uid: False,
            "internal_archive_preview_text": lambda _state: "archive-preview",
            "internal_archive_preview_keyboard": lambda: "archive-preview-keyboard",
            "RETENTION_LABELS": {"1_year", "3_years", "5_years", "10_years", "permanent", "manual_review"},
            "log_command_received": lambda *_args: None,
            "user_exists": lambda _uid: False,
            "get_user": lambda *_args: None,
            "record_usage_event": lambda *_args, **_kwargs: None,
            "has_user_language": lambda _uid: True,
            "localized_start_menu_text": lambda *_args: "main menu",
            "mode_start_notice": lambda _uid: "",
            "localized_main_menu_keyboard": lambda *_args: "main-keyboard",
            "maybe_auto_grant_birthday_gift": noop_async,
            "asyncio": asyncio,
        }
        for name in (
            "internal_archive_pending_key",
            "set_internal_archive_pending",
            "get_internal_archive_pending",
            "clear_internal_archive_pending",
            "handle_internal_archive_callback",
            "handle_internal_archive_pending_text",
            "clear_pending_start_notice",
            "cmd_start",
            "cmd_menu",
        ):
            exec(compile(_source_function(name), f"bot.py:{name}", "exec"), scope)
        exec(compile(_archive_dispatch_function_source(), "bot.py:handle_message:archive-dispatch", "exec"), scope)
        return scope

    def test_start_and_menu_release_unsaved_metadata_without_consuming_text(self):
        self.assertIn(
            'tg_app.add_handler(CallbackQueryHandler(handle_internal_archive_callback, pattern=r"^archive\\|"))',
            BOT_SOURCE,
        )
        self.assertRegex(BOT_SOURCE, r'tg_app\.add_handler\(CommandHandler\("start",\s*cmd_start\)')
        self.assertRegex(BOT_SOURCE, r'tg_app\.add_handler\(CommandHandler\("menu",\s*cmd_menu\)')
        self.assertIn("if await handle_internal_archive_pending_text(update, context):", BOT_SOURCE)

        for command_name, user_id in (("cmd_start", 842501), ("cmd_menu", 842502)):
            with self.subTest(command=command_name):
                scope = self._scope()
                unrelated_key = f"unrelated:{user_id}"
                unrelated_state = {"pending_action": "preserve"}
                scope["USER_PENDING"][unrelated_key] = unrelated_state.copy()
                scope["set_internal_archive_pending"](
                    user_id,
                    "preview",
                    department="finance",
                    document_type="contract",
                    file_info={"file_id": "inert-probe-file", "file_name": "test.pdf", "size_bytes": 1},
                    title="Draft only",
                )

                query = _Query(user_id)
                asyncio.run(
                    scope["handle_internal_archive_callback"](
                        SimpleNamespace(callback_query=query), SimpleNamespace()
                    )
                )
                self.assertEqual(
                    scope["get_internal_archive_pending"](user_id).get("step"), "awaiting_metadata"
                )

                user = SimpleNamespace(id=user_id, first_name="Tester", username="tester")
                command_update = SimpleNamespace(effective_user=user, message=_Message())
                context = SimpleNamespace(args=[], user_data={})
                asyncio.run(scope[command_name](command_update, context))

                state_after_home = dict(scope["get_internal_archive_pending"](user_id) or {})
                ordinary_message = _Message("ordinary text after Home")
                text_update = SimpleNamespace(effective_user=user, effective_message=ordinary_message)
                asyncio.run(scope["dispatch_internal_archive_pending_text"](text_update, context))
                consumed = bool(ordinary_message.replies)

                with self.subTest(check="pending-state-release"):
                    self.assertEqual(state_after_home, {}, "Home must release the unsaved metadata prompt")
                with self.subTest(check="ordinary-text-ownership"):
                    self.assertFalse(consumed, "ordinary text after Home must not become archive metadata")
                with self.subTest(check="unrelated-pending-preserved"):
                    self.assertEqual(scope["USER_PENDING"].get(unrelated_key), unrelated_state)


if __name__ == "__main__":
    unittest.main()
