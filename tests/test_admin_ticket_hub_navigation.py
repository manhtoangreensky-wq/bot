"""Ticket hub and read-only panel controls navigate to their actual parent."""
import importlib.util
import inspect
import unittest
from pathlib import Path
from types import SimpleNamespace

_spec = importlib.util.spec_from_file_location("ticket_hub_fixture", Path(__file__).with_name("test_admin_feedback_inbox_navigation.py"))
fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixture)
feedback, menu = fixture.feedback, fixture.menu


def _dispatch_no_io(route, callback):
    if not route.pattern.match(callback):
        raise AssertionError("emitted control does not match its registration")
    query = feedback._Query(callback)
    coroutine = route.callback(SimpleNamespace(callback_query=query), SimpleNamespace(user_data={}))
    try:
        coroutine.send(None)
    except StopIteration:
        return query
    coroutine.close()
    raise AssertionError("callback fixture yielded; unexpected async I/O")


fixture._dispatch = _dispatch_no_io


def _runtime(admin=True):
    cleared, reads = [], []
    async def to_thread(function, *args, **kwargs):
        return function(*args, **kwargs)

    async def render(query, text, **kwargs):
        query.edits.append((text, kwargs))
    namespace = feedback._load_functions(
        ("admin_module_keyboard", "support_admin_menu_text", "support_admin_menu_keyboard", "handle_ticket_callback"),
        asyncio=SimpleNamespace(to_thread=to_thread),
        normalize_user_language=lambda value: value,
        get_user_language=lambda _uid: "vi",
        public_hub_copy=lambda _lang: {"support_ticket_admin_only": "Admin only", "support_ticket_action_unsupported": "Unsupported"},
        is_admin_user=lambda _uid: admin,
        clear_support_ticket_pending=lambda _uid: cleared.append(True),
        support_ticket_stats_text=lambda: reads.append("stats") or "INERT STATS",
        support_reply_templates_text=lambda: reads.append("templates") or "INERT TEMPLATES",
        support_admin_list_payload=lambda kind, offset: reads.append(("list", kind, offset)) or ("INERT LIST", None),
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

    def test_emitted_admin_ticket_entry_skips_unused_language_lookup(self):
        ns, route, cleared, _ = _runtime()
        language_reads = []
        ns["get_user_language"] = lambda uid: language_reads.append(uid) or "vi"
        emitted = next(
            button
            for row in ns["admin_module_keyboard"]("support").inline_keyboard
            for button in row
            if button.text == "🎧 Ticket admin"
        )

        query = fixture._dispatch(route, emitted.callback_data)

        self.assertEqual("ticket|admin", emitted.callback_data)
        self.assertEqual([], language_reads)
        self.assertEqual([((), {})], query.answers)
        self.assertEqual([True], cleared)
        self.assertEqual(1, len(query.edits))
        self.assertEqual(ns["support_admin_menu_text"](), query.edits[0][0])
        self.assertEqual("menu|admin_support", _button(query, "⬅").callback_data)

    def test_emitted_admin_ticket_list_skips_unused_language_lookup(self):
        ns, route, cleared, reads = _runtime()
        language_reads = []
        ns["get_user_language"] = lambda uid: language_reads.append(uid) or "vi"
        module_entry = next(
            button
            for row in ns["admin_module_keyboard"]("support").inline_keyboard
            for button in row
            if button.text == "🎧 Ticket admin"
        )
        hub = fixture._dispatch(route, module_entry.callback_data)
        emitted = _button(hub, "🆕 Ticket mới")
        self.assertEqual("ticket|al|new|0", emitted.callback_data)
        language_reads.clear()
        reads.clear()
        cleared.clear()

        query = fixture._dispatch(route, emitted.callback_data)

        self.assertEqual([], language_reads)
        self.assertEqual([((), {})], query.answers)
        self.assertEqual([True], cleared)
        self.assertEqual([("list", "new", 0)], reads)
        self.assertEqual("INERT LIST", query.edits[0][0])

    def test_emitted_admin_ticket_static_panels_skip_unused_language_lookup(self):
        cases = (
            ("📊 Thống kê", "ticket|stats|admin", "INERT STATS", ["stats"], None, True),
            ("📚 Mẫu trả lời", "ticket|templates|admin", "INERT TEMPLATES", ["templates"], None, True),
            ("👤 Theo user", "ticket|asearch|user", "Nhập user ID", [], "user", False),
            ("🔍 Tìm ticket", "ticket|asearch|all", "Nhập mã ticket", [], "all", False),
        )
        for label, expected_callback, expected_text, expected_reads, search_source, expect_clear in cases:
            with self.subTest(label=label):
                ns, route, cleared, reads = _runtime()
                language_reads = []
                pending = []
                ns["get_user_language"] = lambda uid: language_reads.append(uid) or "vi"
                ns["set_support_ticket_pending"] = lambda uid, step, **fields: pending.append(
                    (uid, step, fields)
                )
                module_entry = next(
                    button
                    for row in ns["admin_module_keyboard"]("support").inline_keyboard
                    for button in row
                    if button.text == "🎧 Ticket admin"
                )
                hub = fixture._dispatch(route, module_entry.callback_data)
                emitted = _button(hub, label)
                self.assertEqual(expected_callback, emitted.callback_data)
                language_reads.clear()
                pending.clear()
                cleared.clear()
                reads.clear()

                query = fixture._dispatch(route, emitted.callback_data)

                self.assertEqual([], language_reads)
                self.assertEqual([((), {})], query.answers)
                self.assertEqual([True] if expect_clear else [], cleared)
                self.assertEqual(expected_reads, reads)
                self.assertIn(expected_text, query.edits[0][0])
                self.assertEqual("ticket|admin", _button(query, "⬅").callback_data)
                self.assertEqual("menu|main", _button(query, "🏠").callback_data)
                if search_source:
                    self.assertEqual([(123, "admin_search", {"source": search_source})], pending)
                else:
                    self.assertEqual([], pending)

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

    def test_malformed_admin_list_offset_fails_closed_before_cleanup_or_list_read(self):
        _, route, cleared, reads = _runtime()
        invalid_callbacks = (
            "ticket|al|new|not-a-number",
            "ticket|al|new",
            "ticket|al|new|",
            "ticket|al|unknown|0",
            "ticket|al|high|-6",
            "ticket|al|refund|٦",
        )
        for callback in invalid_callbacks:
            with self.subTest(callback=callback):
                query = fixture._dispatch(route, callback)
                self.assertEqual(
                    [(('Nút danh sách ticket đã hết phiên. Vui lòng mở lại từ CSKH/Ticket.',), {"show_alert": True})],
                    query.answers,
                )
                self.assertEqual([], query.edits)
        self.assertEqual([], cleared)
        self.assertEqual([], reads)

    def test_valid_admin_list_page_preserves_filter_and_offset(self):
        _, route, cleared, reads = _runtime()
        query = fixture._dispatch(route, "ticket|al|high|6")

        self.assertEqual(1, len(query.answers))
        self.assertFalse(query.answers[0][1].get("show_alert", False))
        self.assertEqual([True], cleared)
        self.assertEqual([("list", "high", 6)], reads)
        self.assertEqual("INERT LIST", query.edits[0][0])

    def test_emitted_stats_control_offloads_read_after_ack_and_keeps_hub_back(self):
        namespace, route, cleared, reads = _runtime()
        active_queries, offloads = [], []

        def stats_text():
            reads.append(("stats_read_ack", len(active_queries[-1].answers)))
            return "INERT STATS"

        async def to_thread(function, *args, **kwargs):
            offloads.append((function.__name__, len(active_queries[-1].answers)))
            return function(*args, **kwargs)

        namespace["support_ticket_stats_text"] = stats_text
        namespace["asyncio"] = SimpleNamespace(to_thread=to_thread)
        emitted = next(
            button for row in namespace["support_admin_menu_keyboard"]("admin").inline_keyboard
            for button in row if button.text == "📊 Thống kê"
        )
        self.assertEqual("ticket|stats|admin", emitted.callback_data)
        self.assertIsNotNone(route.pattern.match(emitted.callback_data))

        query = feedback._Query(emitted.callback_data)
        active_queries.append(query)
        coroutine = route.callback(SimpleNamespace(callback_query=query), SimpleNamespace(user_data={}))
        try:
            coroutine.send(None)
        except StopIteration:
            pass
        else:
            coroutine.close()
            self.fail("stats fixture unexpectedly yielded I/O")

        self.assertEqual([((), {})], query.answers)
        self.assertEqual([("stats_text", 1)], offloads)
        self.assertEqual([("stats_read_ack", 1)], reads)
        self.assertEqual([True], cleared)
        self.assertEqual("ticket|admin", _button(query, "⬅").callback_data)
        self.assertEqual("menu|main", _button(query, "🏠").callback_data)


if __name__ == "__main__":
    unittest.main()
