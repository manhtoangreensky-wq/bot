"""Exercise the real menu callback and overview leaf without production I/O."""

import asyncio
import html
from pathlib import Path
import re
import unittest
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def source_between(start_marker, end_marker):
    start = SOURCE.index(start_marker)
    end = SOURCE.index(end_marker, start)
    return SOURCE[start:end]


def source_assignment(name):
    match = re.search(
        rf"^{re.escape(name)} = \{{\n.*?^\}}",
        SOURCE,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise AssertionError(f"source assignment not found: {name}")
    return match.group(0)


class FakeQuery:
    def __init__(self):
        self.data = "menu|admin_overview"
        self.from_user = SimpleNamespace(id=42, username="probe", first_name="Admin")

    async def answer(self, *_args, **_kwargs):
        return None


class AdminOverviewActualCallbackTest(unittest.TestCase):
    def test_registered_admin_overview_callback_renders_report(self):
        registration = 'tg_app.add_handler(CallbackQueryHandler(handle_menu_callback, pattern=r"^menu\\|"))'
        self.assertIn(registration, SOURCE)

        menu_content_source = source_between(
            "def localized_menu_content(",
            "\ndef menu_content(",
        )
        overview_source = source_between(
            "def admin_overview_text() -> str:",
            "\nADMIN_MENU_PAGE_HANDLERS = {",
        )
        mapping_source = source_assignment("ADMIN_MENU_PAGE_HANDLERS")
        callback_source = source_between(
            "async def handle_menu_callback(",
            "\nasync def handle_free_hub_callback(",
        )

        sample_payload = {
            "users": {"total": 12, "new": 2, "active": 6},
            "money": {
                "total_amount": 30000,
                "total_count": 3,
                "xu_sold": 300,
                "pending_deposits": 1,
            },
            "tools": {"requested": 8, "success": 7, "fail": 1},
        }
        rendered = {}

        async def capture_edit(_query, text, **kwargs):
            rendered["text"] = text
            rendered.update(kwargs)

        namespace = {
            "html": html,
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "InlineKeyboardButton": lambda text, callback_data=None: SimpleNamespace(text=text, callback_data=callback_data),
            "InlineKeyboardMarkup": lambda rows: SimpleNamespace(inline_keyboard=rows),
            "VIDEO_TAIL9_TEXT_INPUT_KEY": "probe-only",
            "DOC_TOOL_MENU_ACTIONS": set(),
            "is_admin_user": lambda _uid: True,
            "get_user_language": lambda _uid: "vi",
            "normalize_user_language": lambda lang: lang or "vi",
            "report_period_bounds": lambda _period: ("2026-09-27 00:00", "2026-09-28 00:00", "today"),
            "admin_report_payload": lambda *_args: sample_payload,
            "vnd_text": lambda amount: f"{int(amount):,} VND",
            "xu_text": lambda amount: f"{int(amount):,} Xu",
            "safe_edit_query_message": capture_edit,
        }
        for helper_name in (
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
            "clear_pending_admin_tool_test",
        ):
            namespace[helper_name] = lambda *_args, **_kwargs: None

        exec(compile(menu_content_source, "bot.py:localized_menu_content", "exec"), namespace)
        exec(compile(overview_source, "bot.py:admin_overview_text", "exec"), namespace)
        exec(compile(mapping_source, "bot.py:ADMIN_MENU_PAGE_HANDLERS", "exec"), namespace)
        exec(compile(callback_source, "bot.py:handle_menu_callback", "exec"), namespace)

        update = SimpleNamespace(callback_query=FakeQuery())
        asyncio.run(namespace["handle_menu_callback"](update, SimpleNamespace(user_data={})))

        self.assertIn("Báo cáo tổng TOAN AAS", rendered["text"])
        self.assertIn("Tổng: <b>12</b>", rendered["text"])
        self.assertIn("Doanh thu hôm nay: <b>30,000 VND</b>", rendered["text"])
        dashboard_callbacks = [
            button.callback_data
            for row in rendered["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertIn("menu|finance_overview|admin_overview", dashboard_callbacks)
        self.assertIn("menu|admin", dashboard_callbacks)
        self.assertIn("menu|main", dashboard_callbacks)


if __name__ == "__main__":
    unittest.main()
