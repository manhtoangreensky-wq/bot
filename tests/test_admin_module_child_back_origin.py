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
    for name in ("queue_status_keyboard", "freeze_queue_keyboard", "smoke_test_menu_keyboard", "smoke_action_keyboard", "admin_provider_child_keyboard", "admin_menu_callback", "finance_admin_keyboard"):
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


if __name__ == "__main__":
    unittest.main()
