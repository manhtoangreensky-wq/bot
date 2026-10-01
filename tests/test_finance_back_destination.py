import asyncio
import html
import re
import unittest
from pathlib import Path
from types import SimpleNamespace


BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"
BOT_SOURCE = BOT_PATH.read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    starts = [
        index
        for index in (
            BOT_SOURCE.find(f"\ndef {name}("),
            BOT_SOURCE.find(f"\nasync def {name}("),
        )
        if index >= 0
    ]
    if not starts:
        raise AssertionError(f"Function not found in bot.py: {name}")
    start = min(starts) + 1
    ends = [
        index
        for index in (
            BOT_SOURCE.find("\ndef ", start + 1),
            BOT_SOURCE.find("\nasync def ", start + 1),
        )
        if index >= 0
    ]
    end = min(ends) + 1 if ends else len(BOT_SOURCE)
    return BOT_SOURCE[start:end]


class _Button:
    def __init__(self, text, callback_data=None, **_kwargs):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class _Query:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(id=9001, username="admin", first_name="Admin")
        self.message = SimpleNamespace(chat_id=9001)
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _run_finance_back_callback():
    rendered = {}

    async def capture_render(_query, text, **kwargs):
        rendered["text"] = text
        rendered["reply_markup"] = kwargs.get("reply_markup")

    namespace = {
        "__builtins__": __builtins__,
        "html": SimpleNamespace(escape=html.escape),
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "Update": object,
        "TAX_PREP_DISCLAIMER": "Test-only disclaimer",
        "VIDEO_TAIL9_TEXT_INPUT_KEY": "video_tail9_input",
        "DOC_TOOL_MENU_ACTIONS": set(),
        "ADMIN_MENU_PAGE_HANDLERS": {},
        "normalize_user_language": lambda value: value or "vi",
        "localized_start_menu_text": lambda _user_id, _lang: "MAIN MENU TEST MARKER",
        "localized_main_menu_keyboard": lambda *_args: _Markup([]),
        "get_user_language": lambda _user_id: "vi",
        "is_admin_user": lambda _user_id: True,
        "safe_edit_query_message": capture_render,
    }

    for helper in (
        "clear_broadcast_lite_pending",
        "clear_translation_menu_pending",
        "clear_translation_session",
        "clear_media_creator_pending_states",
        "clear_support_ticket_pending",
        "clear_finance_compliance_pending",
        "clear_internal_archive_pending",
        "clear_doc_tool_pending",
        "clear_storage_addon_pending",
        "clear_memory_guided_pending",
        "clear_music_guided_pending",
    ):
        namespace[helper] = lambda *_args, **_kwargs: None

    for helper in (
        "finance_menu_text",
        "finance_admin_keyboard",
        "finance_child_keyboard",
        "localized_menu_content",
        "handle_menu_callback",
    ):
        exec(compile(_function_source(helper), str(BOT_PATH), "exec"), namespace)

    source_keyboard = namespace["finance_child_keyboard"]()
    back_callback = next(
        (button.callback_data for row in source_keyboard.inline_keyboard for button in row if button.text == "⬅️ Tài chính"),
        None,
    )
    query = _Query(back_callback or "")
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(user_data={})
    asyncio.run(namespace["handle_menu_callback"](update, context))
    return back_callback, rendered, query


class FinanceBackDestinationTests(unittest.TestCase):
    def test_registered_admin_finance_back_renders_finance_hub(self):
        registration = re.search(
            r'tg_app\.add_handler\(CallbackQueryHandler\(handle_menu_callback,\s*pattern=r"(?P<pattern>[^"]+)"\)\)',
            BOT_SOURCE,
        )
        self.assertIsNotNone(registration, "menu callback route is not registered")
        self.assertRegex("menu|finance", registration.group("pattern"))

        back_callback, rendered, _query = _run_finance_back_callback()

        self.assertEqual("menu|finance", back_callback)
        self.assertIn("Admin Tài chính TOAN AAS", rendered["text"])
        callbacks = [
            button.callback_data
            for row in rendered["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertIn("menu|finance_overview", callbacks)
        self.assertIn("menu|main", callbacks)


if __name__ == "__main__":
    unittest.main()
