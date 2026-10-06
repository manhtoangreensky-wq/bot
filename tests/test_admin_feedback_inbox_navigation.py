"""Read-only feedback inbox provides actual registered Support/Home exits."""
import asyncio
import html
import importlib.util
import re
import unittest
from pathlib import Path
from types import SimpleNamespace


def _fixture(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


feedback = _fixture("feedback_inbox_fixture", "test_admin_feedback_button_route.py")
menu = _fixture("feedback_menu_fixture", "test_admin_billing_guide_labels.py")
guards = _fixture("feedback_guard_fixture", "test_admin_feedback_callback_admin_guard.py")
ROW = (7, "42", "fixture", "bug", "fixture feedback", "support", "new", "2026-10-07")


class Connection:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []
        self.closed = False

    def execute(self, sql, params=()):
        if not sql.lstrip().upper().startswith("SELECT "):
            raise AssertionError("read-only inbox must not execute a write")
        self.statements.append((sql, params))
        return self

    def fetchall(self):
        return self.rows

    def commit(self):
        raise AssertionError("read-only inbox must not commit")

    def close(self):
        self.closed = True


def _route(namespace, name):
    registrations = []
    namespace["tg_app"] = SimpleNamespace(add_handler=registrations.append)
    namespace["CallbackQueryHandler"] = lambda callback, pattern: SimpleNamespace(callback=callback, pattern=re.compile(pattern))
    line = next(line.strip() for line in feedback.BOT_SOURCE.splitlines() if "tg_app.add_handler(CallbackQueryHandler(" + name + "," in line)
    exec(line, namespace)
    return registrations[0]


def _dispatch(route, callback):
    if not route.pattern.match(callback):
        raise AssertionError("emitted control does not match its registration")
    query = feedback._Query(callback)
    asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace(user_data={})))
    return query


class AdminFeedbackInboxNavigationTests(unittest.TestCase):
    def test_fifteen_long_feedback_rows_fit_telegram_and_keep_final_navigation(self):
        rows = [(i, "42", "fixture", "bug", "X" * 260, "Y" * 120, "new", "2026-10-07") for i in range(1, 16)]
        conn = Connection(rows)
        ns = feedback._load_functions(("cmd_admin_gopy", "handle_admin_gopy_callback"), db_connect=lambda: conn, is_admin_user=lambda _uid: True)
        query = _dispatch(_route(ns, "handle_admin_gopy_callback"), "admin_gopy|inbox")
        messages = query.message.replies
        for text, kwargs in messages:
            plain = html.unescape(re.sub(r"<[^>]+>", "", text))
            self.assertLessEqual(len(plain), 4096, "Full 15-row inbox exceeds Telegram sendMessage limit")
        combined = "\n".join(text for text, _kwargs in messages)
        for i in range(1, 16):
            self.assertIn(f"#{i} |", combined)
        self.assertIsNotNone(messages[-1][1].get("reply_markup"))
        self.assertTrue(all(not kwargs.get("reply_markup") for _text, kwargs in messages[:-1]))
        self.assertEqual(1, len(conn.statements))

    def test_empty_and_populated_inbox_footer_dispatches_support_and_home(self):
        for rows in ([], [ROW]):
            with self.subTest(populated=bool(rows)):
                conn = Connection(rows)
                ns = feedback._load_functions(("cmd_admin_gopy", "handle_admin_gopy_callback", "admin_module_keyboard"), db_connect=lambda: conn, is_admin_user=lambda _uid: True)
                control = next(b for row in ns["admin_module_keyboard"]("support").inline_keyboard for b in row if b.text == "📝 Góp ý admin")
                inbox = _dispatch(_route(ns, "handle_admin_gopy_callback"), control.callback_data)
                self.assertEqual([((), {})], inbox.answers)
                self.assertEqual(1, len(inbox.message.replies))
                self.assertTrue(conn.closed)
                self.assertEqual(1, len(conn.statements))
                markup = inbox.message.replies[0][1].get("reply_markup")
                self.assertIsNotNone(markup, "Inbox result needs a Back/Home navigation keyboard")
                callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
                self.assertEqual(["menu|admin_support", "menu|main"], callbacks)

                nav, _ = menu._load()
                nav["time"] = SimpleNamespace(perf_counter=lambda: 0.0)
                nav["logger"] = SimpleNamespace(info=lambda *_args: None)
                nav["localized_start_menu_text"] = lambda *_args: "MAIN MENU"
                nav["localized_main_menu_keyboard"] = lambda *_args: feedback._Markup([])
                menu_route = _route(nav, "handle_menu_callback")
                support = _dispatch(menu_route, callbacks[0])
                self.assertIn(nav["ADMIN_CONTROL_MODULES"]["support"]["title"], support.edits[0][0])
                home = _dispatch(menu_route, callbacks[1])
                self.assertEqual("MAIN MENU", home.edits[0][0])

    def test_filtered_readonly_command_keeps_filter_and_navigation(self):
        conn = Connection([ROW])
        ns = feedback._load_functions(("cmd_admin_gopy",), db_connect=lambda: conn, is_admin_user=lambda _uid: True)
        message = feedback._Message()
        update = SimpleNamespace(effective_user=SimpleNamespace(id=123), message=message)
        asyncio.run(ns["cmd_admin_gopy"](update, SimpleNamespace(args=["bug"])))
        self.assertEqual(("bug",), conn.statements[0][1])
        self.assertIn("WHERE category=?", conn.statements[0][0])
        self.assertIsNotNone(message.replies[0][1].get("reply_markup"))
        self.assertIn("fixture feedback", message.replies[0][0])

    def test_public_denial_and_existing_feedback_regressions(self):
        guards.test_admin_feedback_callback_is_registered_and_public_is_blocked()
        guards.test_admin_feedback_callback_keeps_admin_inbox_route()
        feedback.test_admin_support_buttons_open_their_labeled_destinations()
        feedback.test_admin_feedback_callback_renders_existing_inbox_without_status_mutations()
        feedback.test_admin_support_guidance_callback_still_renders_the_handbook()


if __name__ == "__main__":
    unittest.main()
