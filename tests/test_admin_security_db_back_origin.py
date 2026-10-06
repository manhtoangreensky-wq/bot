"""Security/DB child screens preserve the immediate UI origin."""

import asyncio
import importlib.util
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

_fixture_spec = importlib.util.spec_from_file_location(
    "security_db_menu_fixture", Path(__file__).with_name("test_admin_billing_guide_labels.py")
)
fixture = importlib.util.module_from_spec(_fixture_spec)
_fixture_spec.loader.exec_module(fixture)

BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"
BOT_SOURCE = BOT_PATH.read_text(encoding="utf-8")


def _function_source(name):
    start = re.search(rf"(?m)^(?:async )?def {name}\(", BOT_SOURCE)
    if not start:
        raise AssertionError(f"missing production function: {name}")
    following = re.search(r"(?m)^(?:async )?def \w+\(", BOT_SOURCE[start.end():])
    end = start.end() + following.start() if following else len(BOT_SOURCE)
    return BOT_SOURCE[start.start():end]


class _Button:
    def __init__(self, text, callback_data=None, **_kwargs):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class _Query:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(id=9001, username="admin", first_name="Admin")
        self.message = SimpleNamespace(chat_id=9001)
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _buttons(markup):
    return [
        (button.text, button.callback_data)
        for row in markup.inline_keyboard
        for button in row
    ]


def _runtime(admin=True):
    namespace, cleared = fixture._load(admin)
    backup_calls, read_calls = [], []
    for name in ("admin_db_status_keyboard", "security_log_keyboard"):
        exec(compile("from __future__ import annotations\n" + _function_source(name), str(BOT_PATH), "exec"), namespace)
    namespace.update({
        "record_security_event": lambda *_args, **_kwargs: None,
        "record_audit_event": lambda *_args, **_kwargs: None,
        "db_status_admin_text": lambda: read_calls.append("db") or "DB STATUS",
        "security_log_text": lambda: read_calls.append("log") or "SECURITY LOG",
        "create_db_backup_now": lambda *_args: backup_calls.append(True) or {"ok": True},
        "backup_db_result_text": lambda _result: "BACKUP RESULT",
        "DB_FILE": "fixture.db",
        "os": SimpleNamespace(path=SimpleNamespace(basename=lambda value: value)),
    })
    registrations = []
    namespace["tg_app"] = SimpleNamespace(add_handler=registrations.append)
    namespace["CallbackQueryHandler"] = lambda callback, pattern: SimpleNamespace(callback=callback, pattern=re.compile(pattern))
    line = next(line.strip() for line in BOT_SOURCE.splitlines() if "tg_app.add_handler(CallbackQueryHandler(handle_menu_callback," in line)
    exec(line, namespace)
    return namespace, registrations[0], cleared, backup_calls, read_calls


def _dispatch(route, callback):
    if not route.pattern.match(callback):
        raise AssertionError(f"emitted callback has no registered handler: {callback}")
    query = _Query(callback)
    asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace(user_data={})))
    return query


def _control(query, label):
    return next(callback for text, callback in _buttons(query.edits[0][1]["reply_markup"]) if text == label)


class AdminSecurityDbBackOriginTests(unittest.TestCase):
    def test_emitted_module_controls_and_sibling_back_dispatch_to_actual_parent(self):
        namespace, route, _, backups, _ = _runtime()
        controls = _buttons(namespace["admin_module_keyboard"]("security_db"))
        for label, sibling_label, parent_text in (
            ("🗄 DB trạng thái", "🛡 Nhật ký bảo mật", "DB STATUS"),
            ("🛡 Nhật ký bảo mật", "🗄 DB trạng thái", "SECURITY LOG"),
        ):
            opened = _dispatch(route, next(cb for text, cb in controls if text == label))
            root = _dispatch(route, _control(opened, "⬅️ Bảo mật / DB"))
            self.assertIn(namespace["ADMIN_CONTROL_MODULES"]["security_db"]["title"], root.edits[0][0])
            child = _dispatch(route, _control(opened, sibling_label))
            back_label = "⬅️ DB trạng thái" if parent_text == "DB STATUS" else "⬅️ Nhật ký bảo mật"
            returned = _dispatch(route, _control(child, back_label))
            self.assertEqual(parent_text, returned.edits[0][0])
            refreshed = _dispatch(route, _control(child, "🔄 Làm mới"))
            self.assertEqual(_control(child, back_label), _control(refreshed, back_label))
        self.assertEqual([], backups)

    def test_backup_result_returns_to_the_emitting_screen_without_real_backup(self):
        namespace, route, _, backups, _ = _runtime()
        keyboards = (
            (namespace["admin_module_keyboard"]("security_db"), "⬅️ Bảo mật / DB", "menu|admin_security_db"),
            (namespace["admin_db_status_keyboard"](), "⬅️ DB trạng thái", "menu|admin_db_status"),
            (namespace["security_log_keyboard"](), "⬅️ Nhật ký bảo mật", "menu|admin_security_log"),
        )
        for keyboard, back_label, expected in keyboards:
            callback = next(cb for text, cb in _buttons(keyboard) if text == "💾 Sao lưu DB")
            result = _dispatch(route, callback)
            self.assertEqual("BACKUP RESULT", result.edits[0][0])
            self.assertEqual(expected, _control(result, back_label))
            self.assertEqual(1, len(result.answers))
        self.assertEqual(3, len(backups))

    def test_public_and_invalid_origins_stop_before_reads_backup_and_cleanup(self):
        for admin in (False, True):
            namespace, route, cleared, backups, reads = _runtime(admin)
            callbacks = (
                "menu|admin_db_status|finance", "menu|admin_security_log|",
                "menu|admin_backup_db|admin_security_db|extra",
            ) if admin else (
                "menu|admin_db_status|admin_security_db", "menu|admin_security_log|admin_db_status",
                "menu|admin_backup_db|admin_security_log",
            )
            for callback in callbacks:
                result = _dispatch(route, callback)
                self.assertEqual([], result.edits)
                self.assertEqual(1, len(result.answers))
                self.assertTrue(result.answers[0][1].get("show_alert"))
            self.assertEqual([], cleared)
            self.assertEqual([], backups)
            self.assertEqual([], reads)

    def test_security_db_module_children_keep_module_back_destination(self):
        self.assertIn('(\"🗄 DB trạng thái\", \"menu|admin_db_status|admin_security_db\")', BOT_SOURCE)
        self.assertIn('(\"💾 Sao lưu DB\", \"menu|admin_backup_db|admin_security_db\")', BOT_SOURCE)
        self.assertIn('(\"🛡 Nhật ký bảo mật\", \"menu|admin_security_log|admin_security_db\")', BOT_SOURCE)

        namespace = {
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
        }
        for name in ("admin_db_status_keyboard", "security_log_keyboard"):
            exec(compile(_function_source(name), str(BOT_PATH), "exec"), namespace)

        expected = {
            "admin_db_status_keyboard": {
                "admin_security_db": ("⬅️ Bảo mật / DB", "menu|admin_security_db"),
                "admin_security_log": ("⬅️ Nhật ký bảo mật", "menu|admin_security_log"),
            },
            "security_log_keyboard": {
                "admin_security_db": ("⬅️ Bảo mật / DB", "menu|admin_security_db"),
                "admin_db_status": ("⬅️ DB trạng thái", "menu|admin_db_status"),
            },
        }
        for name, origins in expected.items():
            for origin, expected_back in origins.items():
                with self.subTest(name=name, origin=origin):
                    buttons = _buttons(namespace[name](origin))
                    self.assertIn(expected_back, buttons)
                    for _label, callback in buttons:
                        self.assertLessEqual(len(callback.encode("utf-8")), 64)

    def test_registered_menu_handler_keeps_cross_screen_origin_and_rejects_unknown(self):
        rendered = {}

        async def capture_render(query, text, **kwargs):
            query.edits.append((text, kwargs))
            rendered["reply_markup"] = kwargs.get("reply_markup")

        namespace = {
            "__builtins__": __builtins__,
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "Update": object,
            "VIDEO_TAIL9_TEXT_INPUT_KEY": "fixture_tail",
            "DOC_TOOL_MENU_ACTIONS": set(),
            "is_admin_user": lambda _uid: True,
            "get_user_language": lambda _uid: "vi",
            "safe_edit_query_message": capture_render,
            "record_security_event": lambda *args, **kwargs: None,
            "db_status_admin_text": lambda: "DB STATUS",
            "security_log_text": lambda: "SECURITY LOG",
        }
        for helper in (
            "clear_broadcast_lite_pending", "clear_translation_menu_pending",
            "clear_translation_session", "clear_media_creator_pending_states",
            "clear_support_ticket_pending", "clear_finance_compliance_pending",
            "clear_internal_archive_pending", "clear_doc_tool_pending",
            "clear_storage_addon_pending", "clear_memory_guided_pending",
            "clear_music_guided_pending", "clear_pending_admin_tool_test",
        ):
            namespace[helper] = lambda *_args, **_kwargs: None
        for name in ("admin_db_status_keyboard", "security_log_keyboard", "handle_menu_callback"):
            exec(compile(_function_source(name), str(BOT_PATH), "exec"), namespace)

        cases = (
            ("menu|admin_db_status|admin_security_db", "menu|admin_security_db"),
            ("menu|admin_db_status|admin_security_log", "menu|admin_security_log"),
            ("menu|admin_security_log|admin_security_db", "menu|admin_security_db"),
            ("menu|admin_security_log|admin_db_status", "menu|admin_db_status"),
        )
        for callback, expected_back in cases:
            with self.subTest(callback=callback):
                query = _Query(callback)
                asyncio.run(namespace["handle_menu_callback"](SimpleNamespace(callback_query=query), SimpleNamespace(user_data={})))
                callbacks = [
                    button.callback_data
                    for row in query.edits[0][1]["reply_markup"].inline_keyboard
                    for button in row
                ]
                self.assertIn(expected_back, callbacks)

        invalid = _Query("menu|admin_db_status|finance")
        asyncio.run(namespace["handle_menu_callback"](SimpleNamespace(callback_query=invalid), SimpleNamespace(user_data={})))
        self.assertEqual([], invalid.edits)
        self.assertTrue(invalid.answers[0][1].get("show_alert"))


if __name__ == "__main__":
    unittest.main()
