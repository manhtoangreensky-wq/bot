"""Module entry -> read-only child -> Back must retain the emitting Admin module."""
import asyncio
import html
import importlib.util
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

_spec = importlib.util.spec_from_file_location("admin_child_fixture", Path(__file__).with_name("test_admin_billing_guide_labels.py"))
fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixture)

CASES = (
    ("queue", "freeze_queue_status", "freeze_queue"),
    ("queue", "freeze_queue_help", "admin"),
    ("security_db", "smoke_sales_ready", "smoke_test"),
    ("system_ops", "admin_overview", "admin"),
    ("provider_worker", "admin_provider_status", "admin_provider"),
    ("provider_worker", "smoke_test", "admin"),
    ("provider_worker", "admin_provider_routes", "admin_provider"),
)


def _runtime(admin=True):
    ns, cleared = fixture._load(admin)
    ns.update(html=html, re=re)
    ns["localized_start_menu_text"] = lambda *_args: "MAIN MENU"
    ns["localized_main_menu_keyboard"] = lambda *_args: fixture.Markup([])
    for name in ("queue_status_keyboard", "freeze_queue_keyboard", "smoke_test_menu_keyboard", "smoke_action_keyboard", "admin_provider_child_keyboard", "admin_menu_callback", "finance_admin_keyboard", "admin_overview_keyboard"):
        exec(compile("from __future__ import annotations\n" + fixture._function(name), "bot.py:" + name, "exec"), ns)
    reads = []
    for name in ("freeze_queue_status_text", "freeze_queue_help_text", "smoke_test_menu_text", "admin_provider_status_text_v2", "admin_provider_routes_text", "admin_overview_text"):
        ns[name] = lambda name=name: reads.append(name) or "INERT DATA: " + name
    ns["smoke_action_text"] = lambda key: "INERT GUIDE: " + key
    registrations = []
    ns["tg_app"] = SimpleNamespace(add_handler=registrations.append)
    ns["CallbackQueryHandler"] = lambda callback, pattern: SimpleNamespace(callback=callback, pattern=re.compile(pattern))
    registration = next(line.strip() for line in fixture.SOURCE.splitlines() if "tg_app.add_handler(CallbackQueryHandler(handle_menu_callback," in line)
    exec(registration, ns)
    return ns, registrations[0], cleared, reads


def _dispatch(route, callback):
    if not route.pattern.match(callback):
        raise AssertionError("emitted callback is not registered: " + callback)
    query = fixture.Query(callback)
    asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace(user_data={})))
    return query


def _controls(query):
    return [button for row in query.edits[0][1]["reply_markup"].inline_keyboard for button in row]


class AdminModuleChildBackTests(unittest.TestCase):
    def test_admin_control_center_entries_reach_their_registered_module_roots(self):
        ns, route, _, _ = _runtime()
        source_fixture = fixture
        for name in (
            "admin_control_center_keyboard", "menu_nav_keyboard", "finance_menu_text",
            "broadcast_lite_admin_menu_text", "broadcast_lite_admin_menu_keyboard",
        ):
            exec(compile("from __future__ import annotations\n" + source_fixture._function(name), "bot.py:" + name, "exec"), ns)
        ns["TAX_PREP_DISCLAIMER"] = "Fixture-only disclaimer."

        root = ns["menu_nav_keyboard"]("admin", True)
        root_callbacks = {button.callback_data for row in root.inline_keyboard for button in row}
        expected = {
            "menu|admin_users", "menu|admin_billing", "menu|admin_packages", "menu|admin_queue",
            "menu|admin_security_db", "menu|admin_system_ops", "menu|admin_provider_worker",
            "menu|admin_finance", "admin_growth|main", "menu|admin_support",
            "menu|admin_broadcast_lite", "menu|main",
        }
        self.assertEqual(expected, root_callbacks)

        destinations = {
            "menu|admin_users": "👤 User / Xu",
            "menu|admin_billing": "💳 Bill / PayOS",
            "menu|admin_packages": "🎁 Gói / Combo",
            "menu|admin_queue": "🧊 Queue / Freeze / Refund",
            "menu|admin_security_db": "🛡 Bảo mật / DB",
            "menu|admin_system_ops": "🖥 Hệ thống",
            "menu|admin_provider_worker": "🤖 Provider / Worker",
            "menu|admin_finance": "Admin Tài chính TOAN AAS",
            "menu|admin_support": "🎧 CSKH / Góp ý",
            "menu|admin_broadcast_lite": "Thông báo khách hàng",
        }
        for callback, heading in destinations.items():
            with self.subTest(callback=callback):
                opened = _dispatch(route, callback)
                self.assertEqual([((), {})], opened.answers)
                self.assertIn(heading, opened.edits[0][0])
                self.assertEqual(["menu|admin"], [
                    button.callback_data
                    for row in opened.edits[0][1]["reply_markup"].inline_keyboard
                    for button in row
                    if button.text.startswith("⬅")
                ])

        self.assertIn(
            'tg_app.add_handler(CallbackQueryHandler(handle_admin_growth_callback, pattern=r"^admin_growth\\|"))',
            source_fixture.SOURCE,
        )
        for name in ("admin_growth_marketing_keyboard", "handle_admin_growth_callback"):
            exec(compile("from __future__ import annotations\n" + source_fixture._function(name), "bot.py:" + name, "exec"), ns)
        ns["affiliate_campaign_cockpit_data"] = lambda *_args, **_kwargs: {
            "summary": {"affiliate_views": 1, "affiliate_clicks": 2, "affiliate_conversions": 3,
                        "affiliate_revenue": 4, "affiliate_profit_estimate": 5}
        }

        async def capture_growth_edit(query, text, **kwargs):
            query.edits.append((text, kwargs))

        ns["safe_edit_or_send"] = capture_growth_edit
        growth_query = fixture.Query("admin_growth|main")
        asyncio.run(ns["handle_admin_growth_callback"](
            SimpleNamespace(callback_query=growth_query), SimpleNamespace(),
        ))
        self.assertEqual([((), {})], growth_query.answers)
        self.assertIn("MARKETING & AUTO-AFFILIATE COCKPIT", growth_query.edits[0][0])
        growth_back = next(
            button.callback_data
            for row in growth_query.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
            if button.text.startswith("⬅")
        )
        self.assertEqual("menu|admin", growth_back)
        ns["menu_text_admin"] = lambda: "INERT ADMIN ROOT"
        returned = _dispatch(route, growth_back)
        self.assertEqual("INERT ADMIN ROOT", returned.edits[0][0])
        self.assertEqual(root_callbacks, {button.callback_data for row in returned.edits[0][1]["reply_markup"].inline_keyboard for button in row})

    def test_admin_growth_root_denies_public_user_before_report_read(self):
        ns, _, _, _ = _runtime(admin=False)
        source_fixture = fixture
        exec(compile("from __future__ import annotations\n" + source_fixture._function("admin_growth_marketing_keyboard"), "bot.py:admin_growth_marketing_keyboard", "exec"), ns)
        exec(compile("from __future__ import annotations\n" + source_fixture._function("handle_admin_growth_callback"), "bot.py:handle_admin_growth_callback", "exec"), ns)
        ns["affiliate_campaign_cockpit_data"] = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("public report read"))

        async def capture_growth_edit(query, text, **kwargs):
            query.edits.append((text, kwargs))

        ns["safe_edit_or_send"] = capture_growth_edit
        query = fixture.Query("admin_growth|main")
        asyncio.run(ns["handle_admin_growth_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(),
        ))
        self.assertEqual([((), {})], query.answers)
        self.assertIn("Chỉ dành cho Quản trị viên", query.edits[0][0])
        self.assertEqual(["menu|main"], [
            button.callback_data
            for row in query.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
        ])

    def test_smoke_guide_round_trip_retains_provider_worker_parent(self):
        ns, route, _, _ = _runtime()
        exec(fixture._assignment("SMOKE_TEST_ACTIONS"), ns)
        for name in ("smoke_action_text", "smoke_action_keyboard"):
            exec(compile(fixture._function(name), "bot.py:" + name, "exec"), ns)
        entry = next(button for row in ns["admin_module_keyboard"]("provider_worker").inline_keyboard
                     for button in row if button.callback_data.startswith("menu|smoke_test"))
        smoke = _dispatch(route, entry.callback_data)
        guides = [button for button in _controls(smoke)
                  if button.callback_data.startswith("menu|smoke_") and "smoke_test" not in button.callback_data]
        self.assertEqual(8, len(guides))
        for button in guides:
            with self.subTest(callback=button.callback_data):
                guide = _dispatch(route, button.callback_data)
                self.assertIn("chỉ hướng dẫn thao tác", guide.edits[0][0])
                self.assertIn("Hướng dẫn", button.text)
                back = next(button for button in _controls(guide) if button.text.startswith("⬅"))
                returned = _dispatch(route, back.callback_data)
                self.assertIn("menu|admin_provider_worker", [button.callback_data for button in _controls(returned)])
                self.assertEqual([((), {})], guide.answers)
                self.assertEqual([((), {})], returned.answers)
                self.assertTrue(all(len(item.callback_data.encode("utf-8")) <= 64 for item in _controls(guide)))

    def test_smoke_guide_invalid_public_contexts_stop_before_cleanup_or_reads(self):
        actions = ("smoke_shopaikey", "smoke_tts", "smoke_image", "smoke_video",
                   "smoke_ffmpeg", "smoke_comfy", "smoke_providers", "smoke_sales_ready")
        for admin in (False, True):
            ns, route, cleared, reads = _runtime(admin)
            origins = ("", "main", "admin_queue", "admin_provider_worker|extra") if admin else ("admin_provider_worker",)
            for action in actions:
                for origin in origins:
                    query = _dispatch(route, f"menu|{action}|{origin}")
                    self.assertEqual(1, len(query.answers))
                    self.assertTrue(query.answers[0][1].get("show_alert"))
                    self.assertEqual([], query.edits)
            self.assertEqual([], cleared)
            self.assertEqual([], reads)

    def test_legacy_smoke_guides_keep_original_admin_parent(self):
        ns, route, _, _ = _runtime()
        exec(fixture._assignment("SMOKE_TEST_ACTIONS"), ns)
        for name in ("smoke_action_text", "smoke_action_keyboard"):
            exec(compile(fixture._function(name), "bot.py:" + name, "exec"), ns)
        for key in ns["SMOKE_TEST_ACTIONS"]:
            guide = _dispatch(route, "menu|smoke_" + key)
            self.assertIn("menu|smoke_test", [button.callback_data for button in _controls(guide)])
            returned = _dispatch(route, "menu|smoke_test")
            self.assertIn("menu|admin", [button.callback_data for button in _controls(returned)])

    def test_provider_worker_route_info_control_matches_its_registered_destination(self):
        ns, route, _, reads = _runtime()
        button = next(
            button
            for row in ns["admin_module_keyboard"]("provider_worker").inline_keyboard
            for button in row
            if button.callback_data.startswith("menu|admin_provider_routes|")
        )

        self.assertEqual("🧾 Route/Group Info", button.text)
        opened = _dispatch(route, button.callback_data)
        self.assertEqual(["admin_provider_routes_text"], reads)
        self.assertIn("INERT DATA: admin_provider_routes_text", opened.edits[0][0])

    def test_provider_worker_smoke_test_shortcut_is_labeled_as_guide(self):
        ns, route, _, _ = _runtime()
        parent = _dispatch(route, "menu|admin_provider_worker")
        button = next(
            button
            for button in _controls(parent)
            if button.callback_data.startswith("menu|smoke_test|")
        )

        self.assertEqual("📘 Hướng dẫn Smoke Test", button.text)
        exec(compile(fixture._function("smoke_test_menu_text"), "bot.py:smoke_test_menu_text", "exec"), ns)
        opened = _dispatch(route, button.callback_data)
        self.assertIn("<b>Lệnh nhanh</b>", opened.edits[0][0])
        guide_buttons = [b for b in _controls(opened) if b.callback_data.startswith("menu|smoke_")]
        self.assertTrue(guide_buttons)
        self.assertTrue(all(b.text.startswith("📘 Hướng dẫn") for b in guide_buttons))

    def test_sales_ready_entries_are_labeled_as_guides(self):
        ns, route, _, _ = _runtime()
        ns["menu_parent_action"] = lambda _section: "admin"
        exec(compile(fixture._function("menu_nav_keyboard"), "bot.py:menu_nav_keyboard", "exec"), ns)

        system_keyboard = ns["menu_nav_keyboard"]("system", True)
        sources = (
            ("Security/DB", _controls(_dispatch(route, "menu|admin_security_db"))),
            ("System", [b for row in system_keyboard.inline_keyboard for b in row]),
        )
        for source, controls in sources:
            with self.subTest(source=source):
                button = next(b for b in controls if b.callback_data.startswith("menu|smoke_sales_ready"))
                self.assertEqual("📘 Hướng dẫn Sales Ready", button.text)

    def test_legacy_system_sales_ready_back_returns_to_system(self):
        ns, route, _, _ = _runtime()
        ns["menu_parent_action"] = lambda _section: "admin"
        exec(compile(fixture._function("menu_nav_keyboard"), "bot.py:menu_nav_keyboard", "exec"), ns)
        exec(fixture._assignment("SMOKE_TEST_ACTIONS"), ns)
        for name in ("smoke_action_text", "smoke_action_keyboard"):
            exec(compile(fixture._function(name), "bot.py:" + name, "exec"), ns)
        ns["menu_text_system"] = lambda: "INERT LEGACY SYSTEM MENU"

        system = ns["menu_nav_keyboard"]("system", True)
        entry = next(b for row in system.inline_keyboard for b in row if b.callback_data.startswith("menu|smoke_sales_ready"))
        guide = _dispatch(route, entry.callback_data)
        self.assertIn("Trang này chỉ hướng dẫn thao tác.", guide.edits[0][0])
        back = next(b for b in _controls(guide) if b.text.startswith("⬅"))
        self.assertEqual(("⬅️ Hệ thống", "menu|system"), (back.text, back.callback_data))

        returned = _dispatch(route, back.callback_data)
        self.assertIn("INERT LEGACY SYSTEM MENU", returned.edits[0][0])

        public_ns, public_route, cleared, reads = _runtime(admin=False)
        query = _dispatch(public_route, "menu|smoke_sales_ready|system")
        self.assertEqual([], query.edits)
        self.assertEqual(1, len(query.answers))
        self.assertTrue(query.answers[0][1].get("show_alert"))
        self.assertEqual([], cleared)
        self.assertEqual([], reads)

    def test_legacy_system_operator_entry_and_back_keep_system_parent(self):
        ns, route, _, _ = _runtime()
        ns["menu_parent_action"] = lambda _section: "admin"
        ns["menu_text_system"] = lambda: "INERT LEGACY SYSTEM MENU"
        exec(compile(fixture._function("menu_nav_keyboard"), "bot.py:menu_nav_keyboard", "exec"), ns)
        exec(compile(fixture._function("menu_text_operator"), "bot.py:menu_text_operator", "exec"), ns)

        system = ns["menu_nav_keyboard"]("system", True)
        entry = next(b for row in system.inline_keyboard for b in row if b.text == "🧠 Operator")
        self.assertEqual("menu|operator|system", entry.callback_data)
        operator = _dispatch(route, entry.callback_data)
        self.assertIn("Operator System", operator.edits[0][0])
        operator_controls = _controls(operator)
        back = next(b for b in operator_controls if b.text.startswith("⬅"))
        self.assertEqual(("⬅️ Hệ thống", "menu|system"), (back.text, back.callback_data))
        self.assertEqual(1, sum(b.callback_data == "menu|system" for b in operator_controls))
        self.assertIn("INERT LEGACY SYSTEM MENU", _dispatch(route, back.callback_data).edits[0][0])

        _, public_route, cleared, reads = _runtime(admin=False)
        denied = _dispatch(public_route, "menu|operator|system")
        self.assertEqual([], denied.edits)
        self.assertEqual(1, len(denied.answers))
        self.assertTrue(denied.answers[0][1].get("show_alert"))
        self.assertEqual([], cleared)
        self.assertEqual([], reads)

    def test_legacy_system_read_only_shortcuts_are_labeled_as_guides(self):
        ns, route, _, _ = _runtime()
        ns["menu_parent_action"] = lambda _section: "admin"
        ns["menu_text_system"] = lambda: "INERT LEGACY SYSTEM MENU"
        for name in ("menu_nav_keyboard", "system_help_text", "system_help_keyboard"):
            exec(compile(fixture._function(name), "bot.py:" + name, "exec"), ns)

        system = ns["menu_nav_keyboard"]("system", True)
        expected = {
            "menu|system_data_status_help": ("📘 Hướng dẫn Data Status", "/data_status"),
            "menu|system_backup_help": ("📘 Hướng dẫn Backup DB", "/backup_db"),
            "menu|system_health_help": ("📘 Hướng dẫn Health", "GET /health"),
        }
        for callback, (label, instruction) in expected.items():
            with self.subTest(callback=callback):
                entry = next(button for row in system.inline_keyboard for button in row
                             if button.callback_data == callback)
                self.assertEqual(label, entry.text)

                guide = _dispatch(route, entry.callback_data)
                self.assertEqual([((), {})], guide.answers)
                self.assertIn(instruction, guide.edits[0][0])
                backs = [button for button in _controls(guide) if button.text.startswith("⬅")]
                self.assertEqual(["menu|system"], [button.callback_data for button in backs])
                returned = _dispatch(route, backs[0].callback_data)
                self.assertIn("INERT LEGACY SYSTEM MENU", returned.edits[0][0])

    def test_system_provider_status_refresh_details_and_back_keep_system_parent(self):
        ns, route, _, reads = _runtime()
        ns["menu_parent_action"] = lambda _section: "admin"
        ns["menu_text_system"] = lambda: "INERT LEGACY SYSTEM MENU"
        exec(compile(fixture._function("menu_nav_keyboard"), "bot.py:menu_nav_keyboard", "exec"), ns)

        system = ns["menu_nav_keyboard"]("system", True)
        entry = next(button for row in system.inline_keyboard for button in row
                     if button.text == "📊 Providers")
        self.assertEqual("menu|admin_provider_status|system", entry.callback_data)

        status = _dispatch(route, entry.callback_data)
        self.assertIn("INERT DATA: admin_provider_status_text_v2", status.edits[0][0])
        status_controls = _controls(status)
        status_callbacks = {button.callback_data: button.text for button in status_controls}
        self.assertEqual("🔄 Làm mới", status_callbacks["menu|admin_provider_status|system"])
        self.assertEqual("📋 Chi tiết", status_callbacks["menu|admin_provider_routes|system"])
        self.assertEqual("⬅️ Hệ thống", status_callbacks["menu|system"])

        details = _dispatch(route, "menu|admin_provider_routes|system")
        self.assertIn("INERT DATA: admin_provider_routes_text", details.edits[0][0])
        detail_controls = _controls(details)
        self.assertEqual(
            ["🔄 Làm mới", "📋 Chi tiết"],
            [button.text for button in detail_controls
             if button.callback_data == "menu|admin_provider_routes|system"],
        )
        detail_back = next(button for button in detail_controls if button.text.startswith("⬅"))
        self.assertEqual(("⬅️ Provider Status", "menu|admin_provider_status|system"),
                         (detail_back.text, detail_back.callback_data))

        returned = _dispatch(route, detail_back.callback_data)
        self.assertIn("INERT DATA: admin_provider_status_text_v2", returned.edits[0][0])
        system_return = _dispatch(route, "menu|system")
        self.assertIn("INERT LEGACY SYSTEM MENU", system_return.edits[0][0])
        self.assertEqual(3, len(reads))

        for callback, admin in (
            ("menu|admin_provider_status|unknown", True),
            ("menu|admin_provider_routes|system|extra", True),
            ("menu|admin_provider_status|system", False),
            ("menu|admin_provider_routes|system", False),
        ):
            with self.subTest(callback=callback, admin=admin):
                _, denied_route, cleared, denied_reads = _runtime(admin=admin)
                denied = _dispatch(denied_route, callback)
                self.assertEqual([], denied.edits)
                self.assertTrue(denied.answers[0][1].get("show_alert"))
                self.assertEqual([], cleared)
                self.assertEqual([], denied_reads)

    def test_operator_system_back_returns_to_operator_and_preserves_legacy_system_parent(self):
        ns, route, _, _ = _runtime()
        ns["menu_parent_action"] = lambda section: {"operator": "admin", "system": "admin"}.get(section, "main")
        ns["menu_text_system"] = lambda: "INERT LEGACY SYSTEM MENU"
        for name in ("menu_text_operator", "menu_nav_keyboard", "system_help_text", "system_help_keyboard"):
            exec(compile(fixture._function(name), "bot.py:" + name, "exec"), ns)

        operator = ns["menu_nav_keyboard"]("operator", True)
        system_entry = next(button for row in operator.inline_keyboard for button in row
                            if button.text == "⚙️ Hệ thống")
        self.assertEqual("menu|system|operator", system_entry.callback_data)
        self.assertLessEqual(len(system_entry.callback_data.encode("utf-8")), 64)

        system = _dispatch(route, system_entry.callback_data)
        self.assertIn("INERT LEGACY SYSTEM MENU", system.edits[0][0])
        back = next(button for button in _controls(system) if button.text.startswith("⬅"))
        self.assertEqual(("⬅️ Operator", "menu|operator"), (back.text, back.callback_data))
        returned = _dispatch(route, back.callback_data)
        self.assertIn("Operator System", returned.edits[0][0])

        child_actions = {
            "admin_provider_status", "smoke_sales_ready", "system_runtime_help",
            "system_data_status_help", "system_backup_help", "system_health_help",
        }
        for entry in _controls(system):
            if entry.callback_data.split("|")[1] not in child_actions:
                continue
            with self.subTest(child=entry.callback_data):
                self.assertLessEqual(len(entry.callback_data.encode("utf-8")), 64)
                child = _dispatch(route, entry.callback_data)
                if entry.callback_data.split("|")[1] == "admin_provider_status":
                    details = next(button for button in _controls(child) if button.text == "📋 Chi tiết")
                    detail_screen = _dispatch(route, details.callback_data)
                    detail_back = next(button for button in _controls(detail_screen) if button.text.startswith("⬅"))
                    self.assertEqual("menu|admin_provider_status|system|operator", detail_back.callback_data)
                    child = _dispatch(route, detail_back.callback_data)
                child_back = next(button for button in _controls(child) if button.text.startswith("⬅"))
                self.assertEqual("menu|system|operator", child_back.callback_data)
                restored_system = _dispatch(route, child_back.callback_data)
                restored_back = next(button for button in _controls(restored_system) if button.text.startswith("⬅"))
                self.assertEqual("menu|operator", restored_back.callback_data)
                self.assertEqual([((), {})], child.answers)

        legacy = _dispatch(route, "menu|system")
        legacy_back = next(button for button in _controls(legacy) if button.text.startswith("⬅"))
        self.assertEqual(("⬅️ Quay lại", "menu|admin"), (legacy_back.text, legacy_back.callback_data))

        for callback, admin in (("menu|system|main", True), ("menu|system|operator|extra", True),
                                ("menu|system|operator", False),
                                ("menu|system_data_status_help|system|invalid", True),
                                ("menu|admin_provider_status|system|operator|extra", True),
                                ("menu|admin_provider_status|system|operator", False),
                                ("menu|system_runtime_help|system|operator", False)):
            with self.subTest(callback=callback, admin=admin):
                _, denied_route, cleared, reads = _runtime(admin=admin)
                denied = _dispatch(denied_route, callback)
                self.assertEqual([], denied.edits)
                self.assertTrue(denied.answers[0][1].get("show_alert"))
                self.assertEqual([], cleared)
                self.assertEqual([], reads)

    def test_package_module_commands_are_labeled_as_guides_and_return_to_packages(self):
        expected = {
            "menu|admin_packages_catalog": ("📘 Hướng dẫn xem catalog gói", "/package_catalog"),
            "menu|admin_packages_grant_combo": ("📘 Hướng dẫn cấp combo", "/grant_combo"),
            "menu|admin_packages_grant_monthly": ("📘 Hướng dẫn cấp gói tháng", "/grant_monthly"),
            "menu|admin_packages_user": ("📘 Hướng dẫn xem gói của user", "/user_packages"),
        }
        ns, route, _, _ = _runtime()
        for name in ("admin_packages_text", "admin_packages_help_text"):
            exec(compile(fixture._function(name), f"bot.py:{name}", "exec"), ns)
        parent = _dispatch(route, "menu|admin_packages")
        self.assertIn(ns["ADMIN_CONTROL_MODULES"]["packages"]["title"], parent.edits[0][0])

        for callback, (expected_label, command) in expected.items():
            with self.subTest(callback=callback):
                button = next(
                    button
                    for button in _controls(parent)
                    if button.callback_data == callback
                )
                self.assertEqual(expected_label, button.text)
                opened = _dispatch(route, button.callback_data)
                self.assertIn(command, opened.edits[0][0])
                backs = [b for b in _controls(opened) if b.text.startswith("⬅")]
                self.assertEqual(["menu|admin_packages"], [b.callback_data for b in backs])
                returned = _dispatch(route, backs[0].callback_data)
                self.assertIn(ns["ADMIN_CONTROL_MODULES"]["packages"]["title"], returned.edits[0][0])
                self.assertIn(callback, [b.callback_data for b in _controls(returned)])

    def test_all_seven_emitted_controls_and_back_dispatch_to_their_module(self):
        ns, route, _, _ = _runtime()
        for module, action, _legacy_parent in CASES:
            with self.subTest(module=module, action=action):
                button = next(button for row in ns["admin_module_keyboard"](module).inline_keyboard for button in row if button.callback_data.split("|")[1] == action)
                opened = _dispatch(route, button.callback_data)
                expected = "menu|admin_" + module
                back = [button for button in _controls(opened) if button.text.startswith("⬅")]
                self.assertEqual([expected], [button.callback_data for button in back])
                self.assertEqual([((), {})], opened.answers)
                parent = _dispatch(route, back[0].callback_data)
                self.assertIn(ns["ADMIN_CONTROL_MODULES"][module]["title"], parent.edits[0][0])
                for control in _controls(opened):
                    self.assertLessEqual(len(control.callback_data.encode("utf-8")), 64)
                for refresh in [control for control in _controls(opened) if control.callback_data.split("|")[1] == action]:
                    refreshed = _dispatch(route, refresh.callback_data)
                    self.assertEqual([expected], [b.callback_data for b in _controls(refreshed) if b.text.startswith("⬅")])

    def test_legacy_child_controls_keep_their_original_parent_and_other_controls(self):
        ns, route, _, _ = _runtime()
        for module, action, legacy_parent in CASES:
            with self.subTest(action=action):
                legacy = _dispatch(route, "menu|" + action)
                self.assertEqual(["menu|" + legacy_parent], [b.callback_data for b in _controls(legacy) if b.text.startswith("⬅")])
                module_entry = _dispatch(route, "menu|" + action + "|admin_" + module)
                def business_callbacks(query):
                    return [b.callback_data for b in _controls(query) if not b.text.startswith("⬅") and b.callback_data.split("|")[1] != action]
                expected = business_callbacks(legacy)
                if action == "smoke_test":
                    guide_callbacks = {
                        "menu|smoke_shopaikey", "menu|smoke_tts", "menu|smoke_image", "menu|smoke_video",
                        "menu|smoke_ffmpeg", "menu|smoke_comfy", "menu|smoke_providers", "menu|smoke_sales_ready",
                    }
                    expected = [callback + "|admin_provider_worker" if callback in guide_callbacks else callback
                                for callback in expected]
                elif action == "admin_overview":
                    expected = [callback + "|admin_system_ops"
                                if callback == "menu|finance_overview|admin_overview" else callback
                                for callback in expected]
                self.assertEqual(expected, business_callbacks(module_entry))

    def test_public_or_invalid_origins_stop_before_cleanup_reads_or_render(self):
        for admin in (True, False):
            ns, route, cleared, reads = _runtime(admin)
            for module, action, _legacy_parent in CASES:
                tokens = ("", "main", "admin_" + module + "|extra") if admin else ("admin_" + module,)
                for token in tokens:
                    query = _dispatch(route, "menu|" + action + "|" + token)
                    self.assertEqual([], query.edits)
                    self.assertEqual(1, len(query.answers))
                    self.assertTrue(query.answers[0][1].get("show_alert"))
            self.assertEqual([], cleared)
            self.assertEqual([], reads)


class AdminGrowthNavigationTests(unittest.TestCase):
    @staticmethod
    def _growth_runtime(admin=True):
        ns, menu_route, cleared, reads = _runtime(admin)
        growth_reads = []
        ns.update(html=html, short_url_display=lambda value: str(value), channel_publish_readiness=lambda _row: ("READY", "inert"))
        ns["menu_text_admin"] = lambda: "INERT ADMIN ROOT"
        ns["time"] = SimpleNamespace(perf_counter=lambda: 0.0)
        read = lambda name, value: lambda *_args, **_kwargs: growth_reads.append(name) or value
        ns["list_affiliate_links"] = read("affiliate_links", [])
        ns["list_calendar_slots"] = read("calendar_slots", [])
        ns["list_campaigns"] = read("campaigns", [])
        ns["list_social_publish_readiness"] = read("channels", [])
        ns["list_publish_queue"] = read("publish_queue", [])
        ns["affiliate_campaign_cockpit_data"] = read("cockpit", {
            "summary": {"affiliate_views": 1, "affiliate_clicks": 2, "affiliate_conversions": 3,
                        "affiliate_revenue": 4, "affiliate_profit_estimate": 5, "affiliate_cost": 0},
            "winners": [],
        })
        for name in ("admin_growth_marketing_keyboard", "handle_admin_growth_callback"):
            exec(compile("from __future__ import annotations\n" + fixture._function(name), "bot.py:" + name, "exec"), ns)
        for name in ("admin_control_center_keyboard", "menu_nav_keyboard"):
            exec(compile("from __future__ import annotations\n" + fixture._function(name), "bot.py:" + name, "exec"), ns)

        async def capture_edit(query, text, **kwargs):
            query.edits.append((text, kwargs))

        ns["safe_edit_or_send"] = capture_edit
        registrations = []
        ns["tg_app"] = SimpleNamespace(add_handler=registrations.append)
        ns["CallbackQueryHandler"] = lambda callback, pattern: SimpleNamespace(callback=callback, pattern=re.compile(pattern))
        registration = next(
            line.strip()
            for line in fixture.SOURCE.splitlines()
            if "tg_app.add_handler(CallbackQueryHandler(handle_admin_growth_callback," in line
        )
        exec(registration, ns)
        return ns, menu_route, registrations[0], cleared, growth_reads

    @staticmethod
    def _dispatch_growth(route, callback):
        if not route.pattern.match(callback):
            raise AssertionError("callback is not handled by the registered Marketing route: " + callback)
        query = fixture.Query(callback)
        asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
        return query

    def test_marketing_read_only_pages_are_reachable_and_return_to_their_emitting_page(self):
        ns, menu_route, growth_route, _, _ = self._growth_runtime()
        root = self._dispatch_growth(growth_route, "admin_growth|main")
        self.assertIn("MARKETING & AUTO-AFFILIATE COCKPIT", root.edits[0][0])
        headings = {
            "affiliates": "KHO LINK AFFILIATE",
            "ideas": "AI TẠO NỘI DUNG",
            "calendar": "LỊCH ĐĂNG BÀI",
            "cockpit": "BÁO CÁO DOANH THU",
            "channels": "TRẠNG THÁI KẾT NỐI KÊNH",
            "packages": "PUBLISH PACKAGES",
        }
        for action, heading in headings.items():
            with self.subTest(action=action):
                entry = next(button for button in _controls(root) if button.callback_data == "admin_growth|" + action)
                opened = self._dispatch_growth(growth_route, entry.callback_data)
                self.assertIn(heading, opened.edits[0][0])
                back = next(button for button in _controls(opened) if button.text.startswith("⬅"))
                self.assertEqual("admin_growth|main", back.callback_data)
                returned = self._dispatch_growth(growth_route, back.callback_data)
                self.assertIn("MARKETING & AUTO-AFFILIATE COCKPIT", returned.edits[0][0])
                self.assertIn(entry.callback_data, [button.callback_data for button in _controls(returned)])
                for button in _controls(opened):
                    self.assertLessEqual(len(button.callback_data.encode("utf-8")), 64)
                    if button.text.startswith("🏠"):
                        self.assertTrue(menu_route.pattern.match(button.callback_data))

        admin_back = next(button for button in _controls(root) if button.text.startswith("⬅"))
        self.assertEqual("menu|admin", admin_back.callback_data)
        admin = _dispatch(menu_route, admin_back.callback_data)
        self.assertIn("INERT ADMIN ROOT", admin.edits[0][0])

    def test_nested_marketing_back_preserves_route_history_and_campaign_calendar_parent(self):
        _, _, route, _, _ = self._growth_runtime()

        channels = self._dispatch_growth(route, "admin_growth|channels")
        packages_button = next(button for button in _controls(channels) if button.callback_data.startswith("admin_growth|packages|"))
        packages = self._dispatch_growth(route, packages_button.callback_data)
        ideas_button = next(button for button in _controls(packages) if button.callback_data.startswith("admin_growth|ideas|"))
        ideas = self._dispatch_growth(route, ideas_button.callback_data)
        ideas_back = next(button for button in _controls(ideas) if button.text.startswith("⬅"))
        self.assertEqual("admin_growth|packages|channels", ideas_back.callback_data)
        returned_packages = self._dispatch_growth(route, ideas_back.callback_data)
        self.assertIn("PUBLISH PACKAGES", returned_packages.edits[0][0])
        packages_back = next(button for button in _controls(returned_packages) if button.text.startswith("⬅"))
        self.assertEqual("admin_growth|channels", packages_back.callback_data)
        self.assertIn("TRẠNG THÁI KẾT NỐI KÊNH", self._dispatch_growth(route, packages_back.callback_data).edits[0][0])

        calendar = self._dispatch_growth(route, "admin_growth|calendar")
        campaigns_button = next(button for button in _controls(calendar) if button.callback_data.startswith("admin_growth|campaigns|"))
        campaigns = self._dispatch_growth(route, campaigns_button.callback_data)
        self.assertIn("DANH SÁCH CHIẾN DỊCH", campaigns.edits[0][0])
        back_to_calendar = next(button for button in _controls(campaigns) if button.text.startswith("⬅"))
        self.assertEqual("admin_growth|calendar", back_to_calendar.callback_data)
        self.assertIn("LỊCH ĐĂNG BÀI", self._dispatch_growth(route, back_to_calendar.callback_data).edits[0][0])
        for page in (channels, packages, ideas, returned_packages, calendar, campaigns):
            self.assertTrue(all(len(button.callback_data.encode("utf-8")) <= 64 for button in _controls(page)))

    def test_growth_actions_that_only_show_commands_are_explicitly_labeled_as_guides(self):
        _, _, route, _, _ = self._growth_runtime()
        root = self._dispatch_growth(route, "admin_growth|main")
        ideas = next(button for button in _controls(root) if button.callback_data == "admin_growth|ideas")
        self.assertIn("Hướng dẫn", ideas.text)

        affiliates = self._dispatch_growth(route, "admin_growth|affiliates")
        for action in ("aff_add", "aff_import"):
            with self.subTest(action=action):
                entry = next(button for button in _controls(affiliates) if button.callback_data.startswith("admin_growth|" + action + "|"))
                self.assertIn("Hướng dẫn", entry.text)
                guide = self._dispatch_growth(route, entry.callback_data)
                self.assertIn("lệnh", guide.edits[0][0])
                back = next(button for button in _controls(guide) if button.text.startswith("⬅"))
                self.assertEqual("admin_growth|affiliates", back.callback_data)
                self.assertIn("KHO LINK AFFILIATE", self._dispatch_growth(route, back.callback_data).edits[0][0])
                legacy = self._dispatch_growth(route, "admin_growth|" + action)
                self.assertEqual("admin_growth|affiliates", next(button for button in _controls(legacy) if button.text.startswith("⬅")).callback_data)

        calendar = self._dispatch_growth(route, "admin_growth|calendar")
        campaigns = next(button for button in _controls(calendar) if button.callback_data.startswith("admin_growth|campaigns|"))
        self.assertIn("Danh sách", campaigns.text)

        packages = self._dispatch_growth(route, "admin_growth|packages")
        ideas = next(button for button in _controls(packages) if button.callback_data.startswith("admin_growth|ideas|"))
        self.assertIn("Hướng dẫn", ideas.text)

    def test_growth_route_rejects_malformed_return_trail_before_report_reads(self):
        _, _, route, _, growth_reads = self._growth_runtime()
        for callback in ("admin_growth|ideas|unknown", "admin_growth|main|extra", "admin_growth|ideas|packages|unknown", "admin_growth|main|packages"):
            with self.subTest(callback=callback):
                query = self._dispatch_growth(route, callback)
                self.assertEqual([], query.edits)
                self.assertTrue(query.answers[0][1].get("show_alert"))
        self.assertEqual([], growth_reads)

    def test_public_growth_callback_is_denied_before_reading_admin_data(self):
        _, _, route, _, growth_reads = self._growth_runtime(admin=False)
        query = self._dispatch_growth(route, "admin_growth|cockpit")
        self.assertIn("Chỉ dành cho Quản trị viên", query.edits[0][0])
        self.assertEqual([], growth_reads)


if __name__ == "__main__":
    unittest.main()
