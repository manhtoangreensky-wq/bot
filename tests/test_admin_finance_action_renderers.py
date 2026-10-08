"""Finance-menu help buttons render through the registered menu callback."""
import asyncio
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "admin_finance_route_fixture",
    Path(__file__).with_name("test_admin_module_child_back_origin.py"),
)
fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixture)


def _runtime(admin=True):
    ns, route, cleared, reads = fixture._runtime(admin)
    source_fixture = fixture.fixture
    ns["datetime"] = datetime
    for name in (
        "finance_child_keyboard", "finance_period_keyboard",
        "finance_menu_text",
        "finance_payload_has_data", "finance_money_or_no_data",
        "finance_xu_or_no_data", "finance_brief_report_text",
        "finance_revenue_period_text", "finance_expense_period_text",
    ):
        exec(compile(source_fixture._function(name), "bot.py:" + name, "exec"), ns)
    for name in (
        "finance_add_expense_help_text", "finance_export_menu_text", "finance_export_instruction_text",
        "finance_admin_guide_text",
        "finance_overview_text", "finance_revenue_text", "finance_revenue_month_menu_text",
        "finance_expense_month_menu_text", "finance_command_help_text",
    ):
        if re.search(r"(?m)^def " + name + r"\(", source_fixture.SOURCE):
            exec(compile(source_fixture._function(name), "bot.py:" + name, "exec"), ns)
    ns["finance_period_payload"] = lambda *_args, **_kwargs: {
        "label": "Fixture month", "revenue_success": 1000, "revenue_count": 2,
        "xu_credited": 20, "expenses_after": 300, "expenses_pre_period": 0,
        "provider_cost_estimate": 10, "tax_reserve": 100,
        "profit_operating": 590, "profit_management": 590,
        "expenses_by_category": [("tools", 1, 300)],
    }
    ns["vnd_text"] = lambda amount: f"{int(amount or 0)} VND"
    ns["xu_text"] = lambda amount: f"{int(amount or 0)} Xu"
    ns["TAX_PREP_DISCLAIMER"] = "Fixture-only financial disclaimer."
    return ns, route, cleared, reads


def _buttons(markup, callback):
    return [
        button
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data == callback
    ]


class AdminFinanceActionRendererTests(unittest.TestCase):
    def test_admin_control_center_finance_button_opens_finance_hub(self):
        ns, route, _, _ = _runtime()
        source_fixture = fixture.fixture
        for name in ("admin_control_center_keyboard", "menu_nav_keyboard", "finance_menu_text", "finance_admin_keyboard"):
            exec(compile(source_fixture._function(name), "bot.py:" + name, "exec"), ns)
        ns["TAX_PREP_DISCLAIMER"] = "Fixture-only financial disclaimer."

        root = ns["menu_nav_keyboard"]("admin", True)
        button = next(
            button
            for row in root.inline_keyboard
            for button in row
            if button.text == "💰 Tài chính"
        )
        self.assertEqual("menu|admin_finance", button.callback_data)

        query = fixture._dispatch(route, button.callback_data)
        self.assertEqual([((), {})], query.answers)
        self.assertIn("Admin Tài chính TOAN AAS", query.edits[0][0])
        callbacks = [
            button.callback_data
            for row in query.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertIn("menu|finance_overview", callbacks)
        self.assertIn("menu|admin", callbacks)

    def test_system_ops_dashboard_finance_child_back_returns_to_dashboard(self):
        ns, route, _, _ = _runtime()
        source_fixture = fixture.fixture
        exec(compile(source_fixture._function("admin_overview_keyboard"), "bot.py:admin_overview_keyboard", "exec"), ns)
        ns["admin_overview_text"] = lambda: "INERT DASHBOARD FIXTURE"

        system_ops = ns["admin_module_keyboard"]("system_ops")
        dashboard = next(
            button
            for row in system_ops.inline_keyboard
            for button in row
            if button.callback_data.startswith("menu|admin_overview")
        )
        opened = fixture._dispatch(route, dashboard.callback_data)
        self.assertEqual([((), {})], opened.answers)
        self.assertEqual(["menu|admin_system_ops"], [
            button.callback_data
            for row in opened.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
            if button.text.startswith("⬅")
        ])

        dashboard_controls = [
            button
            for row in opened.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
        ]
        finance_entries = [button for button in dashboard_controls if button.callback_data.startswith("menu|finance_overview|")]
        self.assertEqual(1, len(finance_entries))
        finance_entry = finance_entries[0]
        self.assertEqual("📊 Báo cáo tài chính", finance_entry.text)
        self.assertEqual("menu|finance_overview|admin_overview|admin_system_ops", finance_entry.callback_data)
        self.assertEqual(
            {"menu|finance_overview|admin_overview|admin_system_ops", "menu|admin_system_ops", "menu|main"},
            {button.callback_data for button in dashboard_controls},
        )
        self.assertTrue(all(len(button.callback_data.encode("utf-8")) <= 64 for button in dashboard_controls))

        report = fixture._dispatch(route, finance_entry.callback_data)
        self.assertIn("Tổng quan tài chính", report.edits[0][0])
        back_callbacks = [
            button.callback_data
            for row in report.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
            if button.text.startswith("⬅")
        ]
        self.assertEqual([dashboard.callback_data], back_callbacks)
        self.assertTrue(all(len(button.callback_data.encode("utf-8")) <= 64 for row in report.edits[0][1]["reply_markup"].inline_keyboard for button in row))

        returned = fixture._dispatch(route, back_callbacks[0])
        self.assertEqual(["menu|admin_system_ops"], [
            button.callback_data
            for row in returned.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
            if button.text.startswith("⬅")
        ])

    def test_legacy_dashboard_context_and_finance_hub_back_remain_distinct(self):
        ns, route, _, _ = _runtime()
        source_fixture = fixture.fixture
        exec(compile(source_fixture._function("admin_overview_keyboard"), "bot.py:admin_overview_keyboard", "exec"), ns)
        ns["admin_overview_text"] = lambda: "INERT DASHBOARD FIXTURE"

        legacy_finance = fixture._dispatch(route, "menu|admin_finance")
        self.assertEqual(["menu|admin"], [
            button.callback_data
            for row in legacy_finance.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
            if button.text.startswith("⬅")
        ])

        legacy_dashboard = fixture._dispatch(route, "menu|admin_overview")
        finance_entries = _buttons(legacy_dashboard.edits[0][1]["reply_markup"], "menu|finance_overview|admin_overview")
        self.assertEqual(1, len(finance_entries))
        finance_entry = finance_entries[0]
        legacy_dashboard_report = fixture._dispatch(route, finance_entry.callback_data)
        self.assertIn("Tổng quan tài chính", legacy_dashboard_report.edits[0][0])
        self.assertEqual(["menu|admin_overview"], [
            button.callback_data
            for row in legacy_dashboard_report.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
            if button.text.startswith("⬅")
        ])

    def test_dashboard_finance_overview_rejects_public_and_stale_origins(self):
        for admin, callback in (
            (False, "menu|finance_overview|admin_overview"),
            (True, "menu|finance_overview|unknown"),
            (True, "menu|finance_overview|admin_overview|extra"),
            (True, "menu|finance_overview|admin_system_ops"),
        ):
            with self.subTest(admin=admin, callback=callback):
                ns, route, cleared, _ = _runtime(admin=admin)
                query = fixture._dispatch(route, callback)
                self.assertTrue(query.answers[0][1].get("show_alert"))
                self.assertEqual([], query.edits)
                self.assertEqual([], cleared)

    def test_finance_report_buttons_render_readonly_pages_and_return_to_finance(self):
        ns, route, _, _ = _runtime()
        visible_controls = (ns["admin_module_keyboard"]("finance"), ns["finance_admin_keyboard"]())
        emitted_by_menu = [
            {button.callback_data for row in markup.inline_keyboard for button in row}
            for markup in visible_controls
        ]
        for emitted in emitted_by_menu:
            self.assertTrue({"menu|finance_overview", "menu|finance_revenue", "menu|finance_expense_month"} <= emitted)
        expected = {
            "menu|finance_overview": "Tổng quan tài chính",
            "menu|finance_revenue": "Doanh thu tháng này",
            "menu|finance_revenue_month": "Nhập kỳ doanh thu",
            "menu|finance_revenue_custom_help": "Nhập kỳ doanh thu",
            "menu|finance_expense_month": "Chi phí tháng này",
            "menu|finance_help": "Hướng dẫn Admin Tài chính",
        }
        for callback, heading in expected.items():
            with self.subTest(callback=callback):
                query = fixture._dispatch(route, callback)
                self.assertEqual([((), {})], query.answers)
                self.assertEqual(1, len(query.edits))
                self.assertIn(heading, query.edits[0][0])
                if callback in {"menu|finance_revenue", "menu|finance_expense_month"}:
                    self.assertIn("Fixture month", query.edits[0][0])
                back = [
                    button.callback_data
                    for row in query.edits[0][1]["reply_markup"].inline_keyboard
                    for button in row
                    if button.text.startswith("⬅")
                ]
                self.assertEqual(["menu|finance"], back)

        parent = fixture._dispatch(route, "menu|finance")
        parent_callbacks = {
            button.callback_data
            for row in parent.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
        }
        self.assertTrue({"menu|finance_overview", "menu|finance_revenue", "menu|finance_expense_month"} <= parent_callbacks)

    def test_all_expense_guide_entries_are_labeled_as_guides(self):
        ns, _, _, _ = _runtime()
        markups = (
            ns["admin_module_keyboard"]("finance"),
            ns["finance_admin_keyboard"](),
            ns["finance_period_keyboard"]("expense"),
        )
        for markup in markups:
            with self.subTest(callback="menu|finance_add_expense"):
                buttons = _buttons(markup, "menu|finance_add_expense")
                self.assertEqual(1, len(buttons))
                self.assertEqual("📘 Hướng dẫn thêm chi phí", buttons[0].text)

    def test_export_period_buttons_are_labeled_as_command_guides(self):
        ns, _, _, _ = _runtime()
        for markup in (ns["finance_admin_keyboard"](), ns["admin_module_keyboard"]("finance")):
            buttons = _buttons(markup, "menu|finance_export")
            self.assertEqual(1, len(buttons))
            self.assertEqual("📘 Hướng dẫn xuất báo cáo", buttons[0].text)
        labels = {
            button.callback_data: button.text
            for row in ns["finance_period_keyboard"]("export").inline_keyboard
            for button in row
        }
        self.assertEqual("📘 Hướng dẫn xuất tháng này", labels["menu|finance_export_month"])
        self.assertEqual("📘 Hướng dẫn xuất năm nay", labels["menu|finance_export_year"])

    def test_emitted_expense_and_export_controls_render_registered_pages(self):
        ns, route, _, _ = _runtime()
        controls = ns["admin_module_keyboard"]("finance")
        for callback, expected_text in (
            ("menu|finance_add_expense", "/expense_add"),
            ("menu|finance_export", "Chọn kỳ"),
        ):
            with self.subTest(callback=callback):
                self.assertEqual(1, len(_buttons(controls, callback)))
                query = fixture._dispatch(route, callback)
                self.assertEqual([((), {})], query.answers)
                self.assertEqual(1, len(query.edits))
                self.assertIn(expected_text, query.edits[0][0])
                if callback == "menu|finance_add_expense":
                    self.assertIn("Hướng dẫn thêm chi phí", query.edits[0][0])
                back = [
                    button
                    for row in query.edits[0][1]["reply_markup"].inline_keyboard
                    for button in row
                    if button.text.startswith("⬅")
                ]
                self.assertEqual(["menu|finance"], [button.callback_data for button in back])

        for callback in ("menu|finance_export_month", "menu|finance_export_year"):
            with self.subTest(callback=callback):
                query = fixture._dispatch(route, callback)
                self.assertEqual(1, len(query.edits))
                self.assertIn("📘 <b>Hướng dẫn xuất báo cáo", query.edits[0][0])
                self.assertIn("/finance_export ", query.edits[0][0])
                back = [
                    button
                    for row in query.edits[0][1]["reply_markup"].inline_keyboard
                    for button in row
                    if button.text.startswith("⬅")
                ]
                self.assertEqual(["menu|finance"], [button.callback_data for button in back])

    def test_public_user_is_denied_before_finance_renderer_or_cleanup(self):
        ns, route, cleared, _ = _runtime(admin=False)
        for callback in (
            "menu|finance_overview",
            "menu|finance_revenue",
            "menu|finance_revenue_month",
            "menu|finance_revenue_custom_help",
            "menu|finance_expense_month",
            "menu|finance_help",
            "menu|finance_add_expense",
            "menu|finance_export",
            "menu|finance_export_month",
            "menu|finance_export_year",
        ):
            with self.subTest(callback=callback):
                query = fixture._dispatch(route, callback)
                self.assertEqual([], query.edits)
                self.assertEqual(1, len(query.answers))
                self.assertTrue(query.answers[0][1].get("show_alert"))
        self.assertEqual([], cleared)


if __name__ == "__main__":
    unittest.main()
