"""Dispatch emitted Billing guide controls without production I/O."""
import asyncio
import html
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
EXPECTED = {
    "menu|admin_billing_pending": ("📘 Hướng dẫn xem bill", "/pending"),
    "menu|admin_billing_duyet": ("📘 Hướng dẫn duyệt bill", "/duyet"),
    "menu|admin_billing_tuchoi": ("📘 Hướng dẫn từ chối bill", "/tuchoi"),
    "menu|admin_billing_payos": ("🧪 Kế hoạch test PayOS", "/payos_test_plan"),
}


def _function(name):
    match = re.search(rf"(?ms)^(?:async )?def {name}\(.*?(?=^(?:async )?def |^class |^[A-Z][A-Z0-9_]*\s*=|\Z)", SOURCE)
    assert match, name
    return match.group(0).rstrip()


def _assignment(name):
    match = re.search(rf"(?ms)^{name} = \{{\n.*?^\}}", SOURCE)
    assert match, name
    return match.group(0)


class Button:
    def __init__(self, text, callback_data=None):
        self.text, self.callback_data = text, callback_data


class Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class Query:
    def __init__(self, callback):
        self.data = callback
        self.from_user = SimpleNamespace(id=123, username="fixture", first_name="Fixture")
        self.answers, self.edits = [], []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _load(admin=True):
    cleared = []

    async def edit(query, text, **kwargs):
        query.edits.append((text, kwargs))

    def forbidden(*args, **kwargs):
        raise AssertionError("Billing guide must not access DB, wallet or provider")

    namespace = {
        "InlineKeyboardButton": Button, "InlineKeyboardMarkup": Markup,
        "is_admin_user": lambda _uid: admin,
        "get_user_language": lambda _uid: "vi",
        "normalize_user_language": lambda lang: lang,
        "safe_html": lambda value: html.escape(str(value)),
        "safe_edit_query_message": edit,
        "VIDEO_TAIL9_TEXT_INPUT_KEY": "fixture_tail_input",
        "DOC_TOOL_MENU_ACTIONS": set(),
        "db_connect": forbidden, "charge_user": forbidden,
        "cmd_duyet": forbidden, "cmd_tuchoi": forbidden,
    }
    for name in (
        "clear_broadcast_lite_pending", "clear_translation_menu_pending",
        "clear_translation_session", "clear_media_creator_pending_states",
        "clear_support_ticket_pending", "clear_finance_compliance_pending",
        "clear_internal_archive_pending", "clear_doc_tool_pending",
        "clear_storage_addon_pending", "clear_memory_guided_pending",
        "clear_music_guided_pending", "clear_pending_admin_tool_test",
    ):
        namespace[name] = lambda *args, **kwargs: cleared.append(True)
    names = (
        "admin_billing_text", "admin_billing_keyboard", "admin_billing_help_text",
        "admin_module_keyboard", "admin_child_keyboard",
        "admin_module_quick_labels", "admin_module_bullet_lines",
        "admin_module_command_lines", "admin_module_page_text",
        "localized_menu_content", "handle_menu_callback",
    )
    blocks = [_assignment("ADMIN_CONTROL_MODULES"), _assignment("ADMIN_MENU_PAGE_HANDLERS")]
    blocks.extend(_function(name) for name in names)
    exec(compile("from __future__ import annotations\n\n" + "\n\n".join(blocks), "bot.py:billing-guides", "exec"), namespace)
    return namespace, cleared


def _controls(namespace):
    for markup in (namespace["admin_billing_keyboard"](), namespace["admin_module_keyboard"]("billing")):
        for row in markup.inline_keyboard:
            for button in row:
                if button.callback_data in EXPECTED:
                    yield button


class BillingGuideRouteTests(unittest.TestCase):
    def test_both_keyboards_label_every_command_page_as_a_guide(self):
        namespace, _ = _load()
        controls = list(_controls(namespace))
        self.assertEqual(len(controls), 8)
        for button in controls:
            self.assertEqual(button.text, EXPECTED[button.callback_data][0])

    def test_emitted_controls_dispatch_to_registered_read_only_guide_and_billing_back(self):
        self.assertIn('CallbackQueryHandler(handle_menu_callback, pattern=r"^menu\\|")', SOURCE)
        namespace, _ = _load()
        for button in _controls(namespace):
            query = Query(button.callback_data)
            asyncio.run(namespace["handle_menu_callback"](SimpleNamespace(callback_query=query), SimpleNamespace(user_data={})))
            self.assertEqual(query.answers, [((), {})])
            self.assertEqual(len(query.edits), 1)
            self.assertIn(EXPECTED[button.callback_data][1], query.edits[0][0])
            callbacks = [b.callback_data for row in query.edits[0][1]["reply_markup"].inline_keyboard for b in row]
            self.assertIn("menu|admin_billing", callbacks)
            back = Query("menu|admin_billing")
            asyncio.run(namespace["handle_menu_callback"](SimpleNamespace(callback_query=back), SimpleNamespace(user_data={})))
            self.assertEqual(back.answers, [((), {})])
            self.assertIn(namespace["ADMIN_CONTROL_MODULES"]["billing"]["title"], back.edits[0][0])
            parent_callbacks = {b.callback_data for row in back.edits[0][1]["reply_markup"].inline_keyboard for b in row}
            self.assertTrue(set(EXPECTED) <= parent_callbacks)

    def test_public_user_cannot_open_any_billing_guide_or_clear_pending_state(self):
        namespace, cleared = _load(admin=False)
        for callback in EXPECTED:
            query = Query(callback)
            asyncio.run(namespace["handle_menu_callback"](SimpleNamespace(callback_query=query), SimpleNamespace(user_data={})))
            self.assertEqual(query.answers, [(("Khu vực này chỉ dành cho Admin.",), {"show_alert": True})])
            self.assertEqual(query.edits, [])
        self.assertEqual(cleared, [])


if __name__ == "__main__":
    unittest.main()
