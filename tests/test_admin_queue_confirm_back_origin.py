"""Queue-entered command guides preserve navigation without executing commands."""
import asyncio
import html
import importlib.util
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

_spec = importlib.util.spec_from_file_location("queue_guide_fixture", Path(__file__).with_name("test_admin_billing_guide_labels.py"))
fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixture)
CASES = ("unfreeze_tool", "freeze_video", "refund_job")


def _runtime(admin=True):
    ns, cleared = fixture._load(admin)
    ns.update(html=html, re=re)
    ns["localized_start_menu_text"] = lambda *_args: "MAIN MENU"
    ns["localized_main_menu_keyboard"] = lambda *_args: fixture.Markup([])
    exec(fixture._assignment("ADMIN_CONFIRM_ACTIONS"), ns)
    for name in ("admin_confirm_text", "admin_confirm_keyboard", "admin_confirm_ack_text", "admin_confirm_ack_keyboard"):
        exec(compile("from __future__ import annotations\n" + fixture._function(name), "bot.py:" + name, "exec"), ns)
    loop = re.search(r"(?ms)^for _admin_confirm_key in tuple\(ADMIN_CONFIRM_ACTIONS.keys\(\)\):.*?(?=^async def |^def |\Z)", fixture.SOURCE).group(0)
    exec(loop, ns)
    registered = []
    ns["tg_app"] = SimpleNamespace(add_handler=registered.append)
    ns["CallbackQueryHandler"] = lambda callback, pattern: SimpleNamespace(callback=callback, pattern=re.compile(pattern))
    line = next(line.strip() for line in fixture.SOURCE.splitlines() if "tg_app.add_handler(CallbackQueryHandler(handle_menu_callback," in line)
    exec(line, ns)
    return ns, registered[0], cleared


def _dispatch(route, callback):
    if not route.pattern.match(callback):
        raise AssertionError("emitted control is not registered")
    query = fixture.Query(callback)
    asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace(user_data={})))
    return query


def _controls(query):
    return [button for row in query.edits[0][1]["reply_markup"].inline_keyboard for button in row]


class QueueConfirmGuideOriginTests(unittest.TestCase):
    def test_new_controls_traverse_actual_common_guards_before_registered_menu(self):
        ns, route, _ = _runtime()
        ns.update({
            "security_defense_shield": None,
            "dispatch_throttle_allow": lambda _uid: True,
            "ApplicationHandlerStop": RuntimeError,
            "deactivate_video_uiflow3_pending_input": lambda _context: None,
        })
        prefixes = re.search(r"(?ms)^VIDEO_PUBLIC_CALLBACK_PREFIXES = \(\n.*?^\)", fixture.SOURCE).group(0)
        exec(prefixes, ns)
        guard_names = ("dispatch_throttle_callback_guard", "safe_mode_callback_guard", "video_public_callback_dedupe_guard")
        for name in (*guard_names, "_is_video_public_callback"):
            exec(compile("from __future__ import annotations\n" + fixture._function(name), "bot.py:" + name, "exec"), ns)
        for mode in ({}, {"maintenance_mode": True, "tool_freeze": True, "provider_freeze": True}):
            ns["current_system_mode"] = lambda mode=mode: mode
            for key in CASES:
                for prefix in ("admin_confirm_", "admin_confirm_ack_"):
                    query = fixture.Query("menu|" + prefix + key + "|admin_queue")
                    update, context = SimpleNamespace(callback_query=query), SimpleNamespace(user_data={})
                    async def dispatch():
                        for name in guard_names:
                            await ns[name](update, context)
                        await route.callback(update, context)
                    asyncio.run(dispatch())
                    self.assertEqual([((), {})], query.answers)
                    self.assertEqual(1, len(query.edits))

    def test_queue_prompt_cancel_back_and_acknowledgement_preserve_flow(self):
        ns, route, _ = _runtime()
        for key in CASES:
            with self.subTest(key=key):
                emitted = next(b for row in ns["admin_module_keyboard"]("queue").inline_keyboard for b in row if b.callback_data.split("|")[1] == "admin_confirm_" + key)
                prompt = _dispatch(route, emitted.callback_data)
                self.assertIn(ns["ADMIN_CONFIRM_ACTIONS"][key]["command"].split()[0], prompt.edits[0][0])
                back = next(b for b in _controls(prompt) if b.text.startswith("⬅"))
                cancel = next(b for b in _controls(prompt) if b.text.startswith("❌"))
                self.assertEqual("menu|admin_queue", back.callback_data)
                self.assertEqual("menu|admin_queue", cancel.callback_data)
                parent = _dispatch(route, cancel.callback_data)
                self.assertIn(ns["ADMIN_CONTROL_MODULES"]["queue"]["title"], parent.edits[0][0])
                confirm = next(
                    b for b in _controls(prompt)
                    if b.callback_data == "menu|admin_confirm_ack_" + key + "|admin_queue"
                )
                acknowledged = _dispatch(route, confirm.callback_data)
                self.assertEqual(ns["admin_confirm_ack_text"](key), acknowledged.edits[0][0])
                ack_back = next(b for b in _controls(acknowledged) if b.text.startswith("⬅"))
                self.assertEqual("menu|admin_confirm_" + key + "|admin_queue", ack_back.callback_data)
                returned = _dispatch(route, ack_back.callback_data)
                self.assertEqual(prompt.edits[0][0], returned.edits[0][0])
                self.assertIn("menu|admin_queue", [b.callback_data for b in _controls(returned)])
                for page in (prompt, acknowledged, returned):
                    self.assertEqual([((), {})], page.answers)
                    for b in _controls(page):
                        self.assertLessEqual(len(b.callback_data.encode("utf-8")), 64)

    def test_manual_command_guidance_is_not_labelled_as_executed_confirmation(self):
        ns, route, _ = _runtime()
        for key in CASES:
            with self.subTest(key=key):
                prompt = _dispatch(route, "menu|admin_confirm_" + key + "|admin_queue")
                show_command = next(
                    b for b in _controls(prompt)
                    if b.callback_data == "menu|admin_confirm_ack_" + key + "|admin_queue"
                )
                self.assertEqual("📋 Xem lệnh cần chạy", show_command.text)

                acknowledgement = _dispatch(route, show_command.callback_data)
                self.assertNotIn("Đã xác nhận thao tác admin", acknowledgement.edits[0][0])
                self.assertIn("Hướng dẫn", acknowledgement.edits[0][0])
                self.assertIn(ns["ADMIN_CONFIRM_ACTIONS"][key]["command"], html.unescape(acknowledgement.edits[0][0]))
                self.assertIn("gửi lệnh dưới đây bằng tay", acknowledgement.edits[0][0])

    def test_legacy_confirmation_and_ack_keep_their_original_instructions_and_back(self):
        ns, route, _ = _runtime()
        for key in CASES:
            for prefix, text_name in (("admin_confirm_", "admin_confirm_text"), ("admin_confirm_ack_", "admin_confirm_ack_text")):
                page = _dispatch(route, "menu|" + prefix + key)
                self.assertEqual(ns[text_name](key), page.edits[0][0])
                back = next(b for b in _controls(page) if b.text.startswith("⬅"))
                self.assertEqual("menu|" + ns["ADMIN_CONFIRM_ACTIONS"][key]["back"], back.callback_data)

    def test_public_invalid_contexts_stop_before_cleanup_and_render(self):
        for admin in (False, True):
            ns, route, cleared = _runtime(admin)
            for key in CASES:
                for prefix in ("admin_confirm_", "admin_confirm_ack_"):
                    tokens = ("", "admin_queue|extra", "admin_billing") if admin else ("admin_queue",)
                    for token in tokens:
                        query = _dispatch(route, "menu|" + prefix + key + "|" + token)
                        self.assertEqual([], query.edits)
                        self.assertEqual(1, len(query.answers))
                        self.assertTrue(query.answers[0][1].get("show_alert"))
            self.assertEqual([], cleared)


if __name__ == "__main__":
    unittest.main()
