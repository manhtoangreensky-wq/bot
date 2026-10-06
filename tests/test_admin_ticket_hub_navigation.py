"""Ticket hub and read-only panel controls navigate to their actual parent."""
import asyncio
import importlib.util
import inspect
import unittest
from pathlib import Path
from types import SimpleNamespace

_spec = importlib.util.spec_from_file_location("ticket_hub_fixture", Path(__file__).with_name("test_admin_feedback_inbox_navigation.py"))
fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixture)
feedback, menu = fixture.feedback, fixture.menu


def _runtime(admin=True):
    cleared, reads = [], []
    async def render(query, text, **kwargs):
        query.edits.append((text, kwargs))
    namespace = feedback._load_functions(
        ("admin_module_keyboard", "support_admin_menu_text", "support_admin_menu_keyboard", "handle_ticket_callback"),
        normalize_user_language=lambda value: value,
        get_user_language=lambda _uid: "vi",
        public_hub_copy=lambda _lang: {"support_ticket_admin_only": "Admin only", "support_ticket_action_unsupported": "Unsupported"},
        is_admin_user=lambda _uid: admin,
        clear_support_ticket_pending=lambda _uid: cleared.append(True),
        support_ticket_stats_text=lambda: reads.append("stats") or "INERT STATS",
        support_reply_templates_text=lambda: reads.append("templates") or "INERT TEMPLATES",
        safe_edit_or_send=render,
    )
    return namespace, fixture._route(namespace, "handle_ticket_callback"), cleared, reads


def _button(query, prefix):
    return next(b for row in query.edits[0][1]["reply_markup"].inline_keyboard for b in row if b.text.startswith(prefix))


class AdminTicketHubNavigationTests(unittest.TestCase):
    def test_ticket_business_controls_and_legacy_pending_cleanup_remain_available(self):
        ns, route, cleared, reads = _runtime()
        expected = ["ticket|al|new|0", "ticket|al|high|0", "ticket|al|refund|0", "ticket|asearch|user", "ticket|asearch|all", "menu|main"]
        for page, origin in (("admin", "admin"), ("stats", "admin"), ("stats", "templates"), ("templates", "admin"), ("templates", "stats")):
            builder = ns["support_admin_menu_keyboard"]
            markup = builder(page, origin) if "page" in inspect.signature(builder).parameters else builder()
            controls = [b for row in markup.inline_keyboard for b in row]
            business = [b.callback_data for b in controls if not b.text.startswith(("⬅", "📊", "📚"))]
            self.assertEqual(expected, business)
        for callback in ("ticket|stats", "ticket|templates", "ticket|stats|admin", "ticket|templates|stats"):
            cleared.clear()
            reads.clear()
            query = fixture._dispatch(route, callback)
            self.assertEqual([True], cleared)
            self.assertEqual(1, len(reads))
            self.assertEqual(1, len(query.edits))

    def test_module_entry_and_read_only_panel_back_dispatch_to_actual_parent(self):
        ns, route, _, _ = _runtime()
        emitted = next(b for row in ns["admin_module_keyboard"]("support").inline_keyboard for b in row if b.text == "🎧 Ticket admin")
        hub = fixture._dispatch(route, emitted.callback_data)
        self.assertEqual("menu|admin_support", _button(hub, "⬅").callback_data)
        nav, _ = menu._load()
        support = fixture._dispatch(fixture._route(nav, "handle_menu_callback"), _button(hub, "⬅").callback_data)
        self.assertIn(nav["ADMIN_CONTROL_MODULES"]["support"]["title"], support.edits[0][0])
        for label in ("📊 Thống kê", "📚 Mẫu trả lời"):
            panel = fixture._dispatch(route, _button(hub, label).callback_data)
            self.assertEqual("ticket|admin", _button(panel, "⬅").callback_data)
            returned = fixture._dispatch(route, _button(panel, "⬅").callback_data)
            self.assertEqual(hub.edits[0][0], returned.edits[0][0])
            self.assertEqual("menu|admin_support", _button(returned, "⬅").callback_data)
            self.assertEqual([((), {})], panel.answers)

    def test_sibling_panel_and_self_press_keep_immediate_origin(self):
        ns, route, _, _ = _runtime()
        hub = fixture._dispatch(route, "ticket|admin")
        for first_label, sibling_label in (("📊 Thống kê", "📚 Mẫu trả lời"), ("📚 Mẫu trả lời", "📊 Thống kê")):
            first = fixture._dispatch(route, _button(hub, first_label).callback_data)
            sibling = fixture._dispatch(route, _button(first, sibling_label).callback_data)
            expected = "ticket|stats" if first_label.startswith("📊") else "ticket|templates"
            self.assertEqual(expected, _button(sibling, "⬅").callback_data)
            repeated = fixture._dispatch(route, _button(sibling, sibling_label).callback_data)
            self.assertEqual(expected, _button(repeated, "⬅").callback_data)
            parent = fixture._dispatch(route, expected)
            self.assertEqual(first.edits[0][0], parent.edits[0][0])
            for page in (first, sibling, repeated):
                for row in page.edits[0][1]["reply_markup"].inline_keyboard:
                    for button in row:
                        self.assertLessEqual(len(button.callback_data.encode("utf-8")), 64)

    def test_public_or_bad_origins_stop_before_pending_cleanup_or_report_reads(self):
        for admin in (False, True):
            ns, route, cleared, reads = _runtime(admin)
            callbacks = ("ticket|stats|stats", "ticket|templates|templates", "ticket|stats|main", "ticket|templates|admin|extra") if admin else ("ticket|admin", "ticket|stats|admin", "ticket|templates|stats")
            for callback in callbacks:
                query = fixture._dispatch(route, callback)
                self.assertEqual([], query.edits)
                self.assertEqual(1, len(query.answers))
                self.assertTrue(query.answers[0][1].get("show_alert"))
            self.assertEqual([], cleared)
            self.assertEqual([], reads)


if __name__ == "__main__":
    unittest.main()
