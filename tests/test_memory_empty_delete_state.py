import asyncio
import re
from pathlib import Path
from types import SimpleNamespace
import unittest


class MemoryEmptyDeleteStateTests(unittest.TestCase):
    def test_emitted_delete_confirmation_is_owner_scoped_and_replay_safe(self):
        source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")

        def source_function(name):
            match = re.search(rf"(?m)^def {re.escape(name)}\(", source)
            if not match:
                match = re.search(rf"(?m)^async def {re.escape(name)}\(", source)
            self.assertIsNotNone(match, f"missing source function {name}")
            boundary = re.search(r"(?m)^(?:async )?def [A-Za-z_]\w*\(|^class\s", source[match.end():])
            end = match.end() + boundary.start() if boundary else len(source)
            return source[match.start():end].rstrip()

        class Button:
            def __init__(self, text, callback_data=None):
                self.text = text
                self.callback_data = callback_data

        class Markup:
            def __init__(self, inline_keyboard):
                self.inline_keyboard = inline_keyboard

        class FixtureConnection:
            def __init__(self, owner_id, note):
                self.owner_id = owner_id
                self.note = note
                self.updates = []
                self.closed = False

            def execute(self, sql, params):
                self.updates.append((sql, params))
                if "WHERE id=? AND user_id=?" not in sql:
                    raise AssertionError(f"delete is not owner-scoped: {sql}")
                updated_at, note_id, user_id = params
                if int(note_id) == int(self.note["id"]) and str(user_id) == str(self.owner_id):
                    self.note.update({"is_archived": 1, "status": "archived", "updated_at": updated_at})

            def commit(self):
                return None

            def close(self):
                self.closed = True

        actor_id, other_id, note_id, token = 42, 999, 445, "fixture-delete-token"
        note = {"id": note_id, "user_id": str(actor_id), "status": "active", "is_archived": 0}
        user_pending = {f"memory_guided:{other_id}": {"pending_action": "preserve"}}
        conn = FixtureConnection(actor_id, note)
        notes = []
        events = []
        edits = []
        copy = {
            "notes_delete": "Delete note",
            "common_cancel": "Cancel",
            "common_main_menu": "Main menu",
            "memory_list_title": "Saved notes",
        }

        async def render(query, text, **kwargs):
            edits.append((query.from_user.id, text, kwargs))

        scope = {
            "USER_PENDING": user_pending,
            "QUICK_MEDIA_PENDING_TTL_SECONDS": 900,
            "time": SimpleNamespace(time=lambda: 100.0),
            "_short_pending_text": lambda value, limit: str(value)[:limit],
            "safe_int": lambda value, default=0: int(value) if str(value).isdigit() else default,
            "normalize_user_language": lambda value: value or "vi",
            "get_user_language": lambda _uid: "vi",
            "memory_can_use_full": lambda _uid: True,
            "clear_memory_guided_pending": None,
            "public_hub_copy": lambda _lang: copy,
            "InlineKeyboardButton": Button,
            "InlineKeyboardMarkup": Markup,
            "safe_edit_or_send": render,
            "memory_main_keyboard": lambda _lang: "memory-root",
            "memory_fetch_note": lambda uid, current_note_id: (
                notes.append((uid, current_note_id))
                or dict(note) if str(uid) == str(actor_id) and int(current_note_id) == note_id and note["status"] == "active"
                else None
            ),
            "db_connect": lambda: conn,
            "now_text": lambda: "fixture-time",
            "memory_record_event": lambda *args, **kwargs: events.append((args, kwargs)),
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        }
        exec(compile(
            "\n\n".join(source_function(name) for name in (
                "memory_guided_pending_key",
                "set_memory_guided_pending",
                "get_memory_guided_pending",
                "clear_memory_guided_pending",
                "memory_delete_confirm_keyboard",
                "handle_memory_callback",
            )),
            "bot.py:memory_delete_confirm_round_trip",
            "exec",
        ), scope)

        scope["set_memory_guided_pending"](
            actor_id, "delete_confirm", note_id=note_id, confirm_token=token,
        )
        markup = scope["memory_delete_confirm_keyboard"](note_id, "vi", confirm_token=token)
        callback_data = next(
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.text.startswith("✅")
        )
        registration = re.search(
            r'CallbackQueryHandler\(handle_memory_callback, pattern=r"([^"]+)"\)', source,
        )
        self.assertIsNotNone(registration, "memory callback must be registered")
        self.assertRegex(callback_data, re.compile(registration.group(1)))
        self.assertEqual(f"memory|delete_yes|{note_id}|{token}", callback_data)

        class Query:
            def __init__(self, uid):
                self.data = callback_data
                self.from_user = SimpleNamespace(id=uid)
                self.answers = []

            async def answer(self, *args, **kwargs):
                self.answers.append((args, kwargs))

        def dispatch(query):
            coroutine = scope["handle_memory_callback"](
                SimpleNamespace(callback_query=query), SimpleNamespace(user_data={}),
            )
            try:
                coroutine.send(None)
            except StopIteration:
                return
            coroutine.close()
            self.fail("Memory confirmation callback unexpectedly yielded I/O")

        first = Query(actor_id)
        dispatch(first)
        self.assertEqual([((), {})], first.answers)
        self.assertEqual(1, len(conn.updates), conn.updates)
        self.assertEqual(("fixture-time", note_id, str(actor_id)), conn.updates[0][1])
        self.assertEqual("archived", note["status"])
        self.assertEqual(1, note["is_archived"])
        self.assertTrue(conn.closed)
        self.assertEqual([(actor_id, "✅ Đã xóa/ẩn ghi chú <code>#445</code>.\n\nTOAN AAS chưa trừ Xu.", {
            "parse_mode": "HTML", "reply_markup": "memory-root",
        })], edits)
        self.assertEqual({f"memory_guided:{other_id}": {"pending_action": "preserve"}}, user_pending)
        self.assertEqual(1, len(events))

        replay = Query(actor_id)
        dispatch(replay)
        self.assertEqual([((), {})], replay.answers)
        self.assertEqual(1, len(conn.updates), conn.updates)
        self.assertIn("hết hạn hoặc không còn hợp lệ", edits[-1][1])
        self.assertEqual({f"memory_guided:{other_id}": {"pending_action": "preserve"}}, user_pending)
        self.assertEqual(1, len(events))

    def test_expired_search_cancel_clears_only_matching_delete_confirmation(self):
        source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")

        def source_function(name):
            match = re.search(rf"(?m)^def {re.escape(name)}\(", source)
            if not match:
                match = re.search(rf"(?m)^async def {re.escape(name)}\(", source)
            self.assertIsNotNone(match, f"missing source function {name}")
            boundary = re.search(r"(?m)^(?:async )?def [A-Za-z_]\w*\(|^class\s", source[match.end():])
            end = match.end() + boundary.start() if boundary else len(source)
            return source[match.start():end].rstrip()

        class Button:
            def __init__(self, text, callback_data=None):
                self.text = text
                self.callback_data = callback_data

        class Markup:
            def __init__(self, inline_keyboard):
                self.inline_keyboard = inline_keyboard

        now = [1000.0]
        tokens = iter(("old-confirm", "empty-results-confirm", "new-confirm"))
        pending = {}
        renders = []
        note = {"id": 445, "user_id": "42", "status": "active", "is_archived": 0}

        async def render(query, text, **kwargs):
            renders.append((query.data, text, kwargs))

        scope = {
            "USER_PENDING": pending,
            "QUICK_MEDIA_PENDING_TTL_SECONDS": 900,
            "time": SimpleNamespace(time=lambda: now[0], time_ns=lambda: next(tokens)),
            "_short_pending_text": lambda value, limit: str(value)[:limit],
            "safe_int": lambda value, default=0: int(value) if str(value).isdigit() else default,
            "normalize_user_language": lambda value: value or "vi",
            "get_user_language": lambda _uid: "vi",
            "memory_can_use_full": lambda _uid: True,
            "clear_memory_guided_pending": None,
            "public_hub_copy": lambda _lang: {
                "notes_delete": "Delete note", "common_cancel": "Cancel",
                "common_main_menu": "Main menu", "memory_list_title": "Saved notes",
            },
            "InlineKeyboardButton": Button,
            "InlineKeyboardMarkup": Markup,
            "safe_edit_or_send": render,
            "memory_main_keyboard": lambda _lang: "memory-root",
            "main_memory_keyboard": lambda _lang, _uid: "memory-main",
            "menu_text_main_memory_i18n": lambda _lang: "Memory menu",
            "memory_delete_confirm_text": lambda _note, _lang: "Confirm delete",
            "memory_fetch_note": lambda uid, note_id: (
                dict(note) if str(uid) == "42" and int(note_id) == note["id"] else None
            ),
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        }
        functions = (
            "memory_guided_pending_key", "set_memory_guided_pending",
            "get_memory_guided_pending", "clear_memory_guided_pending",
            "memory_delete_confirm_keyboard", "handle_memory_callback",
        )
        exec(compile("\n\n".join(source_function(name) for name in functions),
                     "bot.py:expired_memory_search_cancel", "exec"), scope)

        class Query:
            def __init__(self, data):
                self.data = data
                self.from_user = SimpleNamespace(id=42)
                self.answers = []

            async def answer(self, *args, **kwargs):
                self.answers.append((args, kwargs))

        context = SimpleNamespace(user_data={
            "memory_search_results": {
                "token": "old-search", "note_ids": [445], "query": "old",
                "created_at_ts": now[0],
            },
        })

        def dispatch(data):
            query = Query(data)
            coroutine = scope["handle_memory_callback"](
                SimpleNamespace(callback_query=query), context,
            )
            try:
                coroutine.send(None)
            except StopIteration:
                return query
            coroutine.close()
            self.fail("Memory callback unexpectedly yielded I/O")

        def cancel_from_latest_confirmation():
            markup = renders[-1][2]["reply_markup"]
            return next(
                button.callback_data
                for row in markup.inline_keyboard
                for button in row
                if button.text.startswith("❌")
            )

        registration = re.search(
            r'CallbackQueryHandler\(handle_memory_callback, pattern=r"([^"]+)"\)', source,
        )
        self.assertIsNotNone(registration, "memory callback must be registered")

        dispatch("memory|delete|445|search|old-search")
        old_cancel = cancel_from_latest_confirmation()
        self.assertEqual("memory|view|445|search|old-search", old_cancel)
        self.assertRegex(old_cancel, re.compile(registration.group(1)))
        context.user_data["memory_search_results"]["created_at_ts"] = 0
        cancel_result = dispatch(old_cancel)
        self.assertEqual([((), {})], cancel_result.answers)
        self.assertEqual("memory-main", renders[-1][2]["reply_markup"])
        self.assertIsNone(scope["get_memory_guided_pending"](42))

        context.user_data["memory_search_results"] = {
            "token": "empty-results-search", "note_ids": [445], "query": "old",
            "created_at_ts": now[0],
        }
        dispatch("memory|delete|445|search|empty-results-search")
        empty_results_cancel = cancel_from_latest_confirmation()
        context.user_data["memory_search_results"]["note_ids"] = []
        dispatch(empty_results_cancel)
        self.assertIsNone(scope["get_memory_guided_pending"](42))

        context.user_data["memory_search_results"] = {
            "token": "new-search", "note_ids": [445], "query": "new",
            "created_at_ts": now[0],
        }
        dispatch("memory|delete|445|search|new-search")
        new_cancel = cancel_from_latest_confirmation()
        self.assertEqual("memory|view|445|search|new-search", new_cancel)
        context.user_data["memory_search_results"]["token"] = "different-search"
        dispatch(old_cancel)
        self.assertEqual("new-search", scope["get_memory_guided_pending"](42)["origin_search_token"])

    def test_empty_delete_list_clears_old_memory_pending_state(self):
        source = (Path(__file__).resolve().parents[1] / 'bot.py').read_text(encoding='utf-8')
        match = re.search(
            r'(?ms)^async def handle_memory_callback\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)',
            source,
        )
        self.assertIsNotNone(match, 'memory callback handler is missing')
        pending = {'pending_action':'delete_id'}

        async def answer(*args, **kwargs): pass
        async def render(*args, **kwargs): pass

        scope = {'get_user_language':lambda uid:'vi', 'normalize_user_language':lambda x:x,
                 'memory_can_use_full':lambda uid:True, 'clear_memory_guided_pending':lambda uid:pending.clear(),
                 'memory_list_notes':lambda *a,**kw:[],
                 'memory_notes_list_text':lambda *a,**kw:'empty', 'memory_main_keyboard':lambda *a:[],
                 'memory_notes_list_keyboard':lambda *a,**kw:[], 'safe_edit_or_send':render,
                 'memory_access_message':lambda:'denied', 'main_memory_keyboard':lambda *a:[],
                 'Update':object, 'ContextTypes':SimpleNamespace(DEFAULT_TYPE=object)}
        exec(compile(match.group(0), 'bot.py:handle_memory_callback', 'exec'), scope)
        query=SimpleNamespace(answer=answer,data='memory|delete_start',from_user=SimpleNamespace(id=42))
        asyncio.run(scope['handle_memory_callback'](SimpleNamespace(callback_query=query),SimpleNamespace()))
        self.assertEqual(pending, {})

    def test_expired_delete_confirmation_cannot_read_or_archive_note(self):
        source = (Path(__file__).resolve().parents[1] / 'bot.py').read_text(encoding='utf-8')

        def source_function(name):
            match = re.search(rf'(?m)^def {re.escape(name)}\(', source)
            if not match:
                match = re.search(rf'(?m)^async def {re.escape(name)}\(', source)
            self.assertIsNotNone(match, f'missing source function {name}')
            boundary = re.search(r'(?m)^(?:async )?def [A-Za-z_]\w*\(|^class\s', source[match.end():])
            end = match.end() + boundary.start() if boundary else len(source)
            return source[match.start():end].rstrip()

        now = [1000.0]
        user_pending = {"memory_guided:999": {"pending_action": "preserve"}}
        edits = []
        note_reads = []
        db_calls = []

        class Button:
            def __init__(self, text, callback_data=None):
                self.text = text
                self.callback_data = callback_data

        class Markup:
            def __init__(self, inline_keyboard):
                self.inline_keyboard = inline_keyboard

        async def render(query, text, **kwargs):
            edits.append((text, kwargs))

        scope = {
            "USER_PENDING": user_pending,
            "QUICK_MEDIA_PENDING_TTL_SECONDS": 900,
            "time": SimpleNamespace(time=lambda: now[0]),
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "_short_pending_text": lambda value, limit: str(value)[:limit],
            "safe_int": lambda value, default=0: int(value) if str(value).isdigit() else default,
            "normalize_user_language": lambda lang: lang or "vi",
            "get_user_language": lambda _uid: "vi",
            "memory_can_use_full": lambda _uid: True,
            "public_hub_copy": lambda _lang: {
                "notes_delete": "Xóa ghi chú", "common_cancel": "Hủy",
                "common_main_menu": "Trang chủ", "memory_list_title": "Ghi chú đã lưu",
            },
            "InlineKeyboardButton": Button,
            "InlineKeyboardMarkup": Markup,
            "safe_edit_or_send": render,
            "memory_main_keyboard": lambda _lang: "memory-root",
            "memory_fetch_note": lambda *_args: note_reads.append("fetch"),
            "db_connect": lambda: db_calls.append("connect"),
        }
        functions = (
            "memory_guided_pending_key", "set_memory_guided_pending",
            "get_memory_guided_pending", "clear_memory_guided_pending",
            "memory_delete_confirm_keyboard", "handle_memory_callback",
        )
        exec(compile("\n\n".join(source_function(name) for name in functions),
                     'bot.py:expired_memory_confirm', 'exec'), scope)

        user_id = 42
        confirm_token = "fixture-token"
        scope["set_memory_guided_pending"](
            user_id, "delete_confirm", note_id=445, confirm_token=confirm_token,
        )
        markup = scope["memory_delete_confirm_keyboard"](
            445, "vi", confirm_token=confirm_token,
        )
        callback_data = next(
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.text.startswith("✅")
        )
        registration = re.search(
            r'CallbackQueryHandler\(handle_memory_callback, pattern=r"([^"]+)"\)', source,
        )
        self.assertIsNotNone(registration, 'memory callback must be registered')
        self.assertRegex(callback_data, re.compile(registration.group(1)))
        now[0] += 901

        class Query:
            def __init__(self, data, uid):
                self.data = data
                self.from_user = SimpleNamespace(id=uid)
                self.answers = []

            async def answer(self, *args, **kwargs):
                self.answers.append((args, kwargs))

        query = Query(callback_data, user_id)
        coroutine = scope["handle_memory_callback"](
            SimpleNamespace(callback_query=query), SimpleNamespace(user_data={}),
        )
        try:
            coroutine.send(None)
        except StopIteration:
            pass
        else:
            coroutine.close()
            self.fail('expired confirmation fixture unexpectedly yielded I/O')

        self.assertEqual([((), {})], query.answers)
        self.assertIn("hết hạn hoặc không còn hợp lệ", edits[0][0])
        self.assertEqual({"memory_guided:999": {"pending_action": "preserve"}}, user_pending)
        self.assertEqual([], note_reads)
        self.assertEqual([], db_calls)
