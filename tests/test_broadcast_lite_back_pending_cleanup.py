import ast
import asyncio
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import admin_broadcast


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
CLEAR_START = BOT_SOURCE.index("\ndef clear_broadcast_lite_pending(") + 1
CLEAR_END = BOT_SOURCE.index("\n\ndef _broadcast_lite_is_schedule(", CLEAR_START)
CALLBACK_START = BOT_SOURCE.index("\nasync def handle_broadcast_lite_callback(") + 1
CALLBACK_END = BOT_SOURCE.index("\nasync def handle_broadcast_lite_pending_text(", CALLBACK_START)
HANDLER_NODES = ast.parse(
    BOT_SOURCE[CLEAR_START:CLEAR_END] + "\n\n" + BOT_SOURCE[CALLBACK_START:CALLBACK_END]
).body
HANDLERS = {node.name: node for node in HANDLER_NODES}


class _Logger:
    def warning(self, *args, **kwargs):
        return None


class _Button:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


def _function_source(name):
    start = re.search(rf"(?m)^(?:async\s+)?def {re.escape(name)}\s*\(", BOT_SOURCE)
    assert start is not None, name
    boundary = re.search(
        r"(?m)^(?:async\s+)?def \w+\s*\(|^class \w+|^[A-Z][A-Z0-9_]*\s*=",
        BOT_SOURCE[start.end():],
    )
    end = start.end() + boundary.start() if boundary else len(BOT_SOURCE)
    return BOT_SOURCE[start.start():end].rstrip()


def _actual_callback_namespace(db_path):
    calls = []

    async def answer_callback(query, text="", **kwargs):
        await query.answer(text, **kwargs)

    async def edit_callback(query, text, reply_markup=None, **kwargs):
        calls.append((text, reply_markup))
        return True

    scope = {
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "DB_FILE": str(db_path),
        "Update": object,
        "_broadcast_lite_answer_callback": answer_callback,
        "_broadcast_lite_edit": edit_callback,
        "broadcast_lite_admin_menu_keyboard": lambda: "admin-hub-keyboard",
        "broadcast_lite_admin_menu_text": lambda: "Thông báo khách hàng",
        "clear_broadcast_lite_pending_drafts": admin_broadcast.clear_pending_drafts,
        "is_admin_user": lambda user_id: int(user_id) == 9001,
        "logger": _Logger(),
    }
    nodes = [
        HANDLERS["clear_broadcast_lite_pending"],
        HANDLERS["handle_broadcast_lite_callback"],
    ]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "actual-broadcast-callback", "exec"), scope)
    scope["calls"] = calls
    return scope


class BroadcastLiteBackPendingCleanupTests(unittest.TestCase):
    def test_actual_broadcast_lite_callback_is_registered(self):
        registration = 'CallbackQueryHandler(handle_broadcast_lite_callback, pattern=r"^broadcast_lite\\|")'
        self.assertIn(registration, BOT_SOURCE)
        route = re.compile(r"^broadcast_lite\|")
        self.assertIsNotNone(route.match("broadcast_lite|back"))
        self.assertIsNotNone(route.match("broadcast_lite|menu"))

    def _assert_exit_releases_pending_owner_and_preserves_draft(self, action):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "broadcast-lite.db"
            draft = admin_broadcast.create_empty_draft(db_path, 9001, state="awaiting_content")
            retained_content = "Nội dung bản nháp cần giữ nguyên"
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    "UPDATE broadcast_lite_drafts SET message_text=? WHERE draft_id=? AND admin_id=?",
                    (retained_content, str(draft["draft_id"]), "9001"),
                )
                conn.commit()
            finally:
                conn.close()

            namespace = _actual_callback_namespace(db_path)
            answer_calls = []
            admin = SimpleNamespace(id=9001)

            async def answer(text="", **kwargs):
                answer_calls.append((text, kwargs))

            query = SimpleNamespace(data=f"broadcast_lite|{action}", answer=answer)
            update = SimpleNamespace(callback_query=query, effective_user=admin)
            asyncio.run(namespace["handle_broadcast_lite_callback"](update, SimpleNamespace()))

            saved_draft = admin_broadcast.get_draft(db_path, draft["draft_id"], 9001)
            self.assertIsNotNone(saved_draft)
            self.assertEqual(saved_draft["state"], "draft")
            self.assertEqual(saved_draft["message_text"], retained_content)
            self.assertEqual(namespace["calls"], [("Thông báo khách hàng", "admin-hub-keyboard")])
            self.assertEqual(answer_calls, [("", {})])

    def test_back_releases_pending_owner_and_preserves_draft(self):
        self._assert_exit_releases_pending_owner_and_preserves_draft("back")

    def test_menu_releases_pending_owner_and_preserves_draft(self):
        self._assert_exit_releases_pending_owner_and_preserves_draft("menu")

    def test_read_only_views_and_nested_limits_return_to_the_emitting_broadcast_menu(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "broadcast-lite-navigation.db"
            namespace = _actual_callback_namespace(db_path)
            namespace.update(
                InlineKeyboardButton=_Button,
                InlineKeyboardMarkup=_Markup,
                broadcast_lite_admin_menu_text=lambda: "INERT BROADCAST ROOT",
                broadcast_lite_schedule_menu_text=lambda: "📅 Lịch thông báo",
                list_broadcast_lite_campaigns=lambda *_args: [],
                get_broadcast_lite_promo_limits=lambda *_args: {
                    "max_24h": 1, "max_7d": 3, "weekly_then_daily": False,
                },
                clear_broadcast_lite_pending=lambda _uid: None,
            )
            for name in (
                "broadcast_lite_admin_menu_keyboard",
                "broadcast_lite_history_keyboard",
                "broadcast_lite_schedule_menu_keyboard",
                "broadcast_lite_limits_text",
                "broadcast_lite_limits_keyboard",
            ):
                exec(compile(_function_source(name), "bot.py:" + name, "exec"), namespace)

            registered = []
            namespace["tg_app"] = SimpleNamespace(add_handler=registered.append)
            namespace["CallbackQueryHandler"] = lambda callback, pattern: SimpleNamespace(
                callback=callback, pattern=re.compile(pattern)
            )
            registration = next(
                line.strip()
                for line in BOT_SOURCE.splitlines()
                if "tg_app.add_handler(CallbackQueryHandler(handle_broadcast_lite_callback," in line
            )
            exec(registration, namespace)
            route = registered[0]

            def dispatch(callback):
                self.assertIsNotNone(route.pattern.match(callback), callback)
                answers = []

                async def answer(*args, **kwargs):
                    answers.append((args, kwargs))

                query = SimpleNamespace(data=callback, answer=answer)
                update = SimpleNamespace(
                    callback_query=query,
                    effective_user=SimpleNamespace(id=9001),
                )
                asyncio.run(route.callback(update, SimpleNamespace()))
                self.assertEqual([(('',), {})], answers)
                text, markup = namespace["calls"][-1]
                return text, markup

            def controls(markup):
                return [button for row in markup.inline_keyboard for button in row]

            root = namespace["broadcast_lite_admin_menu_keyboard"]()
            expected_roots = {
                "broadcast_lite|history": "📊 Lịch sử gửi",
                "broadcast_lite|sched": "📅 Lịch thông báo",
                "broadcast_lite|limits": "⚙️ Giới hạn gửi",
            }
            for callback, title in expected_roots.items():
                with self.subTest(callback=callback):
                    entry = next(b for b in controls(root) if b.callback_data == callback)
                    self.assertEqual(title, entry.text)
                    page_text, page_markup = dispatch(entry.callback_data)
                    self.assertIn(title.split(" ", 1)[-1], page_text)
                    back = next(b for b in controls(page_markup) if b.text.startswith("⬅"))
                    self.assertEqual("broadcast_lite|back", back.callback_data)
                    root_text, root_markup = dispatch(back.callback_data)
                    self.assertEqual("INERT BROADCAST ROOT", root_text)
                    self.assertEqual(
                        set(expected_roots),
                        {b.callback_data for b in controls(root_markup) if b.callback_data in expected_roots},
                    )

            schedule_text, schedule_markup = dispatch("broadcast_lite|sched")
            self.assertEqual("📅 Lịch thông báo", schedule_text)
            nested_limits = next(
                b for b in controls(schedule_markup)
                if b.callback_data == "broadcast_lite|limits|sched"
            )
            limits_text, limits_markup = dispatch(nested_limits.callback_data)
            self.assertIn("Giới hạn gửi", limits_text)
            self.assertEqual(
                "broadcast_lite|sched",
                next(b for b in controls(limits_markup) if b.text.startswith("⬅")).callback_data,
            )
            returned_schedule, returned_schedule_markup = dispatch("broadcast_lite|sched")
            self.assertEqual("📅 Lịch thông báo", returned_schedule)
            self.assertEqual(
                "broadcast_lite|back",
                next(b for b in controls(returned_schedule_markup) if b.text.startswith("⬅")).callback_data,
            )


if __name__ == "__main__":
    unittest.main()
