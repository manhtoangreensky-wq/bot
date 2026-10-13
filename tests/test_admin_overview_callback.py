"""Exercise the real menu callback and overview leaf without production I/O."""

import html
from pathlib import Path
import re
import unittest
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def run_immediate(coro):
    try:
        coro.send(None)
    except StopIteration as completed:
        return completed.value
    raise AssertionError("fixture unexpectedly yielded I/O")


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
    def __init__(self, data="menu|admin_overview", user_id=42):
        self.data = data
        self.answers = []
        self.from_user = SimpleNamespace(id=user_id, username="probe", first_name="Admin")

    async def answer(self, *_args, **_kwargs):
        self.answers.append((_args, _kwargs))
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
            "_local_video_planning_clear_pending",
        ):
            namespace[helper_name] = lambda *_args, **_kwargs: None

        exec(compile(menu_content_source, "bot.py:localized_menu_content", "exec"), namespace)
        exec(compile(overview_source, "bot.py:admin_overview_text", "exec"), namespace)
        exec(compile(mapping_source, "bot.py:ADMIN_MENU_PAGE_HANDLERS", "exec"), namespace)
        exec(compile(callback_source, "bot.py:handle_menu_callback", "exec"), namespace)

        update = SimpleNamespace(callback_query=FakeQuery())
        run_immediate(namespace["handle_menu_callback"](update, SimpleNamespace(user_data={})))

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


def finance_tax_menu_callback_fixture():
    rendered = {}
    report_calls = []

    async def capture_edit(_query, text, **kwargs):
        rendered["text"] = text
        rendered.update(kwargs)

    namespace = {
        "html": html,
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "InlineKeyboardButton": lambda text, callback_data=None: SimpleNamespace(
            text=text, callback_data=callback_data
        ),
        "InlineKeyboardMarkup": lambda rows: SimpleNamespace(inline_keyboard=rows),
        "VIDEO_TAIL9_TEXT_INPUT_KEY": "probe-only",
        "DOC_TOOL_MENU_ACTIONS": set(),
        "is_admin_user": lambda user_id: user_id == 42,
        "get_user_language": lambda _uid: "vi",
        "normalize_user_language": lambda lang: lang or "vi",
        "finance_tax_dashboard_text": lambda *args: (
            report_calls.append(args) or "TAX MODULE"
        ),
        "finance_tax_dashboard_text_for_bounds": lambda *_args: "TAX QUARTER",
        "finance_tax_settings_text": lambda: "TAX SETTINGS",
        "finance_policy_status_text": lambda: "B2C/B2B POLICY",
        "finance_tax_scenario_report_text": lambda: "TAX SCENARIO",
        "provider_cost_tax_status_text": lambda: "PROVIDER COST / FCT",
        "finance_menu_audit_text": lambda: "FINANCE AUDIT",
        "finance_vat_rate_help_text": lambda: "VAT RATE HELP",
        "finance_cit_rate_help_text": lambda: "CIT RATE HELP",
        "finance_menu_text": lambda: "FINANCE ROOT",
        "finance_admin_keyboard": lambda: SimpleNamespace(inline_keyboard=[]),
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
        "_local_video_planning_clear_pending",
    ):
        namespace[helper_name] = lambda *_args, **_kwargs: None

    for start, end, name in (
        ("def finance_child_keyboard()", "\ndef finance_tax_keyboard()", "finance_child_keyboard"),
        ("def finance_tax_keyboard()", "\ndef finance_tax_child_keyboard()", "finance_tax_keyboard"),
        ("def finance_tax_child_keyboard()", "\ndef finance_tax_report_keyboard()", "finance_tax_child_keyboard"),
        ("def finance_tax_report_keyboard()", "\ndef finance_adjustments_keyboard()", "finance_tax_report_keyboard"),
    ):
        exec(compile(source_between(start, end), f"bot.py:{name}", "exec"), namespace)
    exec(
        compile(
            source_between("def localized_menu_content(", "\ndef menu_content("),
            "bot.py:localized_menu_content",
            "exec",
        ),
        namespace,
    )
    exec(
        compile(source_assignment("ADMIN_MENU_PAGE_HANDLERS"), "bot.py:ADMIN_MENU_PAGE_HANDLERS", "exec"),
        namespace,
    )
    exec(
        compile(
            source_between("async def handle_menu_callback(", "\nasync def handle_free_hub_callback("),
            "bot.py:handle_menu_callback",
            "exec",
        ),
        namespace,
    )

    def dispatch(callback_data, user_id=42):
        query = FakeQuery(callback_data, user_id)
        update = SimpleNamespace(callback_query=query)
        run_immediate(namespace["handle_menu_callback"](update, SimpleNamespace(user_data={})))
        return query

    return namespace, rendered, report_calls, dispatch


class FinanceTaxReportBackOriginTest(unittest.TestCase):
    def test_emitted_tax_report_back_restores_tax_module_through_registered_handler(self):
        registration = 'tg_app.add_handler(CallbackQueryHandler(handle_menu_callback, pattern=r"^menu\\|"))'
        self.assertIn(registration, SOURCE)
        namespace, rendered, report_calls, dispatch = finance_tax_menu_callback_fixture()

        parent_query = dispatch("menu|finance_tax_vat")
        tax_parent_callbacks = [
            button.callback_data
            for row in rendered["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertIn("menu|finance_tax_report", tax_parent_callbacks)

        report_query = dispatch("menu|finance_tax_report")
        back_button = next(
            button
            for row in rendered["reply_markup"].inline_keyboard
            for button in row
            if button.text.startswith("⬅")
        )
        back_query = dispatch(back_button.callback_data)

        self.assertEqual(back_button.callback_data, "menu|finance_tax_vat")
        self.assertEqual(rendered["text"], "TAX MODULE")
        self.assertEqual(len(parent_query.answers), 1)
        self.assertEqual(len(report_query.answers), 1)
        self.assertEqual(len(back_query.answers), 1)
        self.assertEqual(report_calls[-1], ())

        before_public = len(report_calls)
        public_query = dispatch("menu|finance_tax_report", user_id=7)
        self.assertEqual(len(public_query.answers), 1)
        self.assertTrue(public_query.answers[0][1].get("show_alert"))
        self.assertEqual(len(report_calls), before_public)


class FinanceAuditMenuBackOriginTest(unittest.TestCase):
    def test_audit_menu_from_tax_module_back_restores_immediate_parent(self):
        registration = 'tg_app.add_handler(CallbackQueryHandler(handle_menu_callback, pattern=r"^menu\\|"))'
        self.assertIn(registration, SOURCE)
        _namespace, rendered, _report_calls, dispatch = finance_tax_menu_callback_fixture()

        parent_query = dispatch("menu|finance_tax_vat")
        audit_button = next(
            button
            for row in rendered["reply_markup"].inline_keyboard
            for button in row
            if button.text == "🧭 Audit menu"
        )
        audit_query = dispatch(audit_button.callback_data)
        back_button = next(
            button
            for row in rendered["reply_markup"].inline_keyboard
            for button in row
            if button.text.startswith("⬅")
        )
        back_query = dispatch(back_button.callback_data)

        self.assertEqual(audit_button.callback_data, "menu|finance_menu_audit")
        self.assertEqual(back_button.callback_data, "menu|finance_tax_vat")
        self.assertEqual(rendered["text"], "TAX MODULE")
        self.assertEqual(len(parent_query.answers), 1)
        self.assertEqual(len(audit_query.answers), 1)
        self.assertEqual(len(back_query.answers), 1)


class FinanceTaxReadOnlyChildBackMatrixTest(unittest.TestCase):
    def test_every_emitted_read_only_child_back_restores_tax_module(self):
        registration = 'tg_app.add_handler(CallbackQueryHandler(handle_menu_callback, pattern=r"^menu\\|"))'
        self.assertIn(registration, SOURCE)
        _namespace, rendered, _report_calls, dispatch = finance_tax_menu_callback_fixture()

        parent_query = dispatch("menu|finance_tax_vat")
        emitted = {
            button.callback_data
            for row in rendered["reply_markup"].inline_keyboard
            for button in row
        }
        child_screens = {
            "menu|finance_tax_settings": "TAX SETTINGS",
            "menu|finance_vat_rate_help": "VAT RATE HELP",
            "menu|finance_policy_status": "B2C/B2B POLICY",
            "menu|finance_tax_scenario": "TAX SCENARIO",
            "menu|finance_provider_cost_tax": "PROVIDER COST / FCT",
            "menu|finance_menu_audit": "FINANCE AUDIT",
            "menu|finance_cit_rate_help": "CIT RATE HELP",
        }
        self.assertTrue(set(child_screens).issubset(emitted))

        for callback_data, expected_text in child_screens.items():
            with self.subTest(callback_data=callback_data):
                child_query = dispatch(callback_data)
                self.assertEqual(rendered["text"], expected_text)
                back_button = next(
                    button
                    for row in rendered["reply_markup"].inline_keyboard
                    for button in row
                    if button.text.startswith("⬅")
                )
                self.assertEqual(back_button.callback_data, "menu|finance_tax_vat")

                back_query = dispatch(back_button.callback_data)
                self.assertEqual(rendered["text"], "TAX MODULE")
                self.assertEqual(len(child_query.answers), 1)
                self.assertEqual(len(back_query.answers), 1)

        self.assertEqual(len(parent_query.answers), 1)


class FinanceCitReportBackOriginTest(unittest.TestCase):
    def test_emitted_cit_report_back_restores_tax_module(self):
        registration = 'tg_app.add_handler(CallbackQueryHandler(handle_menu_callback, pattern=r"^menu\\|"))'
        self.assertIn(registration, SOURCE)
        namespace, rendered, report_calls, dispatch = finance_tax_menu_callback_fixture()
        namespace["finance_tax_dashboard_text"] = lambda *args: (
            report_calls.append(args) or ("TAX REPORT" if args else "TAX MODULE")
        )

        parent_query = dispatch("menu|finance_tax_vat")
        cit_button = next(
            button
            for row in rendered["reply_markup"].inline_keyboard
            for button in row
            if button.callback_data == "menu|finance_cit_report"
        )
        report_query = dispatch(cit_button.callback_data)
        back_button = next(
            button
            for row in rendered["reply_markup"].inline_keyboard
            for button in row
            if button.text.startswith("⬅")
        )
        back_query = dispatch(back_button.callback_data)

        self.assertEqual(rendered["text"], "TAX MODULE")
        self.assertEqual(cit_button.callback_data, "menu|finance_cit_report")
        self.assertEqual(report_calls, [(), ("", "month"), ()])
        self.assertEqual(back_button.callback_data, "menu|finance_tax_vat")
        self.assertEqual(len(parent_query.answers), 1)
        self.assertEqual(len(report_query.answers), 1)
        self.assertEqual(len(back_query.answers), 1)


if __name__ == "__main__":
    unittest.main()
