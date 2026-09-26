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


if __name__ == "__main__":
    unittest.main()
