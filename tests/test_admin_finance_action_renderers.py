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
    for name in ("finance_child_keyboard", "finance_period_keyboard"):
        exec(compile(source_fixture._function(name), "bot.py:" + name, "exec"), ns)
    for name in ("finance_add_expense_help_text", "finance_export_menu_text", "finance_export_instruction_text"):
        if re.search(r"(?m)^def " + name + r"\(", source_fixture.SOURCE):
            exec(compile(source_fixture._function(name), "bot.py:" + name, "exec"), ns)
    return ns, route, cleared, reads


def _buttons(markup, callback):
    return [
        button
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data == callback
    ]


class AdminFinanceActionRendererTests(unittest.TestCase):
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
