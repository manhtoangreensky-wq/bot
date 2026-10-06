"""Runtime-help Back must retain the Admin module that emitted the control."""
import asyncio
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace

_spec = importlib.util.spec_from_file_location(
    "billing_menu_fixture", Path(__file__).with_name("test_admin_billing_guide_labels.py"),
)
fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixture)


def _load(admin=True):
    namespace, cleared = fixture._load(admin)
    names = ("menu_parent_action", "menu_nav_keyboard", "system_help_text", "system_help_keyboard")
    exec(compile("from __future__ import annotations\n\n" + "\n\n".join(fixture._function(n) for n in names), "bot.py:runtime-help-context", "exec"), namespace)
    return namespace, cleared


def _dispatch(namespace, callback):
    query = fixture.Query(callback)
    asyncio.run(namespace["handle_menu_callback"](SimpleNamespace(callback_query=query), SimpleNamespace(user_data={})))
    return query


def _callbacks(query):
    return [b.callback_data for row in query.edits[0][1]["reply_markup"].inline_keyboard for b in row]


class RuntimeHelpBackOriginTests(unittest.TestCase):
    def test_module_guide_back_dispatches_to_its_emitting_module(self):
        self.assertIn('CallbackQueryHandler(handle_menu_callback, pattern=r"^menu\\|")', fixture.SOURCE)
        for module in ("security_db", "system_ops"):
            with self.subTest(module=module):
                namespace, _ = _load()
                keyboard = namespace["admin_module_keyboard"](module)
                guide = next(b for row in keyboard.inline_keyboard for b in row if b.callback_data.startswith("menu|system_runtime_help"))
                self.assertLessEqual(len(guide.callback_data.encode("utf-8")), 64)
                opened = _dispatch(namespace, guide.callback_data)
                self.assertEqual(opened.answers, [((), {})])
                self.assertIn("/runtime", opened.edits[0][0])
                back_callback = f"menu|admin_{module}"
                self.assertIn(back_callback, _callbacks(opened))
                self.assertNotIn("menu|system", _callbacks(opened))
                self.assertTrue({"menu|admin", "menu|main"} <= set(_callbacks(opened)))
                back = _dispatch(namespace, back_callback)
                self.assertIn(namespace["ADMIN_CONTROL_MODULES"][module]["title"], back.edits[0][0])

    def test_legacy_guide_keeps_system_back_and_existing_controls(self):
        namespace, _ = _load()
        keyboard = namespace["menu_nav_keyboard"]("system", True)
        guide = next(b for row in keyboard.inline_keyboard for b in row if b.callback_data == "menu|system_runtime_help")
        opened = _dispatch(namespace, guide.callback_data)
        self.assertEqual(opened.answers, [((), {})])
        self.assertIn("/runtime", opened.edits[0][0])
        self.assertEqual(_callbacks(opened), ["menu|admin", "menu|system", "menu|main"])

    def test_public_user_is_denied_before_any_pending_cleanup(self):
        namespace, cleared = _load(admin=False)
        for callback in (
            "menu|system_runtime_help", "menu|system_runtime_help|admin_security_db",
            "menu|system_runtime_help|admin_system_ops",
        ):
            query = _dispatch(namespace, callback)
            self.assertEqual(query.answers, [(("Khu vực này chỉ dành cho Admin.",), {"show_alert": True})])
            self.assertEqual(query.edits, [])
        self.assertEqual(cleared, [])

    def test_invalid_or_expired_origin_is_rejected_before_pending_cleanup(self):
        namespace, cleared = _load()
        for parent in ("", "main", "admin_billing", "admin_security_db|extra"):
            query = _dispatch(namespace, f"menu|system_runtime_help|{parent}")
            self.assertEqual(len(query.answers), 1)
            self.assertTrue(query.answers[0][1].get("show_alert"))
            self.assertEqual(query.edits, [])
        self.assertEqual(cleared, [])


if __name__ == "__main__":
    unittest.main()
