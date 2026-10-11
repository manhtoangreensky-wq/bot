import asyncio
import html
import re
import unittest
from pathlib import Path
from types import SimpleNamespace


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def _source_function(name):
    start = re.search(rf"(?m)^(?:async )?def {re.escape(name)}\(", BOT_SOURCE)
    if not start:
        raise AssertionError(f"missing actual source function: {name}")
    following = re.search(r"(?m)^(?:async )?def [A-Za-z_]\w*\(", BOT_SOURCE[start.end():])
    end = start.end() + following.start() if following else len(BOT_SOURCE)
    return BOT_SOURCE[start.start():end]


class _Button:
    def __init__(self, text, callback_data):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class _Query:
    def __init__(self, user_id, data):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace(chat_id=-100441)
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def _run_no_io(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as completed:
        return completed.value
    coroutine.close()
    raise AssertionError("archive callback fixture unexpectedly yielded I/O")


def _registered_archive_pattern():
    registration = re.search(
        r"CallbackQueryHandler\(\s*handle_internal_archive_callback\s*,\s*pattern\s*=\s*r(['\"])(.*?)\1\s*\)",
        BOT_SOURCE,
    )
    if not registration:
        raise AssertionError("actual Internal Archive callback registration is missing")
    return re.compile(registration.group(2))


def _runtime():
    clock = [1000.0]
    captured = []
    sent_documents = []
    documents = {
        441: {
            "id": 441,
            "title": "Fixture policy",
            "department": "customers",
            "document_type": "general",
            "file_name": "policy.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 12,
            "tags": "fixture",
            "description": "Fixture only",
            "retention_policy": "permanent",
            "confidentiality_level": "internal",
            "created_at": "2026-01-01T00:00:00Z",
            "file_id": "fixture-file-id",
        },
        442: {
            "id": 442,
            "title": "Missing file fixture",
            "department": "customers",
            "document_type": "general",
            "file_name": "missing.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 12,
            "tags": "fixture",
            "description": "Fixture only",
            "retention_policy": "permanent",
            "confidentiality_level": "internal",
            "created_at": "2026-01-01T00:00:00Z",
            "file_id": "",
        },
    }
    lookup_calls = []
    recent_calls = []
    pending_clear_calls = []

    def get_document(user_id, document_id):
        lookup_calls.append((user_id, document_id))
        return documents.get(document_id, {})

    def recent_documents(user_id, department, limit):
        recent_calls.append((user_id, department, limit))
        return [documents[441]] if department == "customers" else []

    async def send_document(**kwargs):
        sent_documents.append(kwargs)

    async def to_thread(function, *args):
        return function(*args)

    namespace = {
        "asyncio": SimpleNamespace(to_thread=to_thread),
        "USER_PENDING": {},
        "html": html,
        "time": SimpleNamespace(time=lambda: clock[0]),
        "INTERNAL_ARCHIVE_TTL_SECONDS": 900,
        "INTERNAL_DOC_DEPARTMENTS": {
            "customers": "Hồ sơ khách hàng",
            "sales": "Hồ sơ kinh doanh",
        },
        "INTERNAL_DOC_TYPES": {
            "customers": ("customer_profile",),
            "sales": ("sales_record",),
        },
        "INTERNAL_DOC_DEPARTMENT_HELP": {},
        "document_type_label": lambda value: {
            "customer_profile": "Hồ sơ khách hàng",
            "sales_record": "Hồ sơ kinh doanh",
            "general": "Loại khác / chưa phân loại",
        }.get(value, str(value)),
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "SimpleNamespace": SimpleNamespace,
        "is_admin_user": lambda _uid: True,
        "clear_doc_tool_pending": lambda uid: pending_clear_calls.append(("doc", uid)),
        "clear_media_creator_pending_states": lambda uid: pending_clear_calls.append(("media", uid)),
        "internal_archive_menu_text": lambda: "ARCHIVE ROOT",
        "internal_archive_preview_text": lambda state: (
            f"PREVIEW: {state.get('department')}/{state.get('document_type')}"
        ),
        "internal_archive_department_text": lambda department: f"DEPARTMENT DASHBOARD: {department}",
        "internal_archive_recent_text": lambda rows, department: "\n".join([
            f"🕘 <b>Hồ sơ gần đây — {department}</b>", "",
            f"1. <b>{rows[0]['title']}</b>",
            f"   Loại chung · {rows[0]['created_at']}",
        ]) if rows else f"Hồ sơ gần đây — {department}: trống",
        "recent_internal_documents": recent_documents,
        "get_internal_document": get_document,
        "internal_archive_document_text": lambda item: f"DOCUMENT DETAIL: {item['id']}",
        "safe_edit_query_message": None,
        "_archive_documents": documents,
        "_archive_lookup_calls": lookup_calls,
        "_archive_recent_calls": recent_calls,
        "_archive_pending_clear_calls": pending_clear_calls,
        "_archive_sent_documents": sent_documents,
    }
    for name in (
        "internal_archive_pending_key",
        "set_internal_archive_pending",
        "get_internal_archive_pending",
        "clear_internal_archive_pending",
        "internal_archive_menu_keyboard",
        "internal_archive_preview_keyboard",
        "internal_archive_department_keyboard",
        "internal_archive_type_keyboard",
        "internal_archive_type_text",
        "internal_archive_quick_save_text",
        "internal_archive_upload_prompt_text",
        "internal_archive_help_text",
        "internal_archive_results_keyboard",
        "handle_internal_archive_callback",
    ):
        exec(compile("from __future__ import annotations\n" + _source_function(name), f"bot.py:{name}", "exec"), namespace)

    async def safe_edit(_query, text, **kwargs):
        captured.append((text, kwargs.get("reply_markup")))

    namespace["safe_edit_query_message"] = safe_edit
    route_pattern = _registered_archive_pattern()
    archive_context = SimpleNamespace(bot=SimpleNamespace(send_document=send_document))

    async def dispatch(query, context=None):
        if not route_pattern.match(query.data):
            raise AssertionError(f"emitted callback is not handled by Archive route: {query.data}")
        await namespace["handle_internal_archive_callback"](
            SimpleNamespace(callback_query=query), context or archive_context
        )
        return query

    async def click(user_id, callback_data):
        query = _Query(user_id, callback_data)
        await dispatch(query)
        if len(query.answers) != 1:
            raise AssertionError(f"expected one callback acknowledgement, got {len(query.answers)}")
        return query

    namespace["_archive_dispatch"] = dispatch
    return namespace, captured, clock, click


class InternalArchiveSearchBackOriginTests(unittest.TestCase):
    def test_archive_document_reads_are_acknowledged_before_lookup(self):
        for action in ("view", "file"):
            with self.subTest(action=action):
                runtime, _captured, _clock, _click = _runtime()
                user_id = 700222
                query = _Query(user_id, f"archive|{action}|441")
                looked_up = []

                def get_document_after_ack(admin_id, document_id):
                    self.assertEqual([((), {})], query.answers)
                    looked_up.append((admin_id, document_id))
                    return runtime["_archive_documents"][document_id]

                runtime["get_internal_document"] = get_document_after_ack
                archive_namespace = {}

                async def to_thread(function, *args):
                    return function(*args)

                # Re-load only the actual production callback with an injected
                # no-I/O thread seam; no file read or Telegram send occurs.
                exec(
                    compile("from __future__ import annotations\n" + _source_function("handle_internal_archive_callback"), "bot.py:archive_latency", "exec"),
                    archive_namespace,
                )
                archive_namespace.update(runtime)

                archive_namespace["asyncio"] = SimpleNamespace(to_thread=to_thread)
                sent = []

                async def send_document(**kwargs):
                    sent.append(kwargs)

                context = SimpleNamespace(bot=SimpleNamespace(send_document=send_document))
                _run_no_io(archive_namespace["handle_internal_archive_callback"](
                    SimpleNamespace(callback_query=query), context,
                ))

                self.assertEqual([(user_id, 441)], looked_up)
                self.assertEqual([((), {})], query.answers)
                self.assertEqual(len(sent), 1 if action == "file" else 0)

    def test_emitted_department_type_back_returns_to_same_department(self):
        runtime, captured, _clock, click = _runtime()
        user_id = 700122

        root_markup = runtime["internal_archive_menu_keyboard"]()
        department_callback = next(
            callback for callback in _callbacks(root_markup)
            if callback == "archive|dept|customers"
        )
        department_query = asyncio.run(click(user_id, department_callback))
        self.assertEqual(department_query.answers, [((), {})])
        department_markup = captured[-1][1]

        types_button = next(
            button for row in department_markup.inline_keyboard for button in row
            if button.text == "🏷 Chọn loại hồ sơ"
        )
        self.assertEqual(types_button.callback_data, "archive|types")
        type_query = asyncio.run(click(user_id, types_button.callback_data))
        self.assertEqual(type_query.answers, [((), {})])
        self.assertIn("Chọn loại hồ sơ — Hồ sơ khách hàng", captured[-1][0])
        type_markup = captured[-1][1]
        back_button = next(
            button for row in type_markup.inline_keyboard for button in row
            if button.text.startswith("⬅️")
        )
        self.assertEqual(back_button.text, "⬅️ Phòng ban")
        self.assertEqual(back_button.callback_data, "archive|back_department")
        self.assertIn("archive|type|customer_profile", _callbacks(type_markup))

        back_query = asyncio.run(click(user_id, back_button.callback_data))

        self.assertEqual(back_query.answers, [((), {})])
        self.assertEqual(captured[-1][0], "DEPARTMENT DASHBOARD: customers")
        self.assertEqual(_callbacks(captured[-1][1]), _callbacks(department_markup))
        state = runtime["get_internal_archive_pending"](user_id)
        self.assertEqual(state["step"], "department_dashboard")
        self.assertEqual(state["department"], "customers")
        self.assertEqual(runtime["_archive_lookup_calls"], [])
        self.assertEqual(runtime["_archive_recent_calls"], [])
        self.assertEqual(runtime["_archive_sent_documents"], [])

    def test_emitted_type_selection_back_returns_to_same_type_picker(self):
        runtime, captured, _clock, click = _runtime()
        user_id = 700123

        asyncio.run(click(user_id, "archive|dept|customers"))
        department_markup = captured[-1][1]
        types_button = next(
            button for row in department_markup.inline_keyboard for button in row
            if button.text == "🏷 Chọn loại hồ sơ"
        )
        asyncio.run(click(user_id, types_button.callback_data))
        type_markup = captured[-1][1]
        type_callback = next(
            callback for callback in _callbacks(type_markup)
            if callback == "archive|type|customer_profile"
        )

        selected_query = asyncio.run(click(user_id, type_callback))

        self.assertEqual(selected_query.answers, [((), {})])
        self.assertIn("Gửi file hồ sơ", captured[-1][0])
        self.assertIn("Hồ sơ khách hàng", captured[-1][0])
        upload_markup = captured[-1][1]
        self.assertEqual(_callbacks(upload_markup), ["archive|types", "menu|main"])
        pending = runtime["get_internal_archive_pending"](user_id)
        self.assertEqual(pending["step"], "awaiting_file")
        self.assertEqual(pending["department"], "customers")
        self.assertEqual(pending["document_type"], "customer_profile")

        back_query = asyncio.run(click(user_id, _callbacks(upload_markup)[0]))

        self.assertEqual(back_query.answers, [((), {})])
        self.assertIn("Chọn loại hồ sơ — Hồ sơ khách hàng", captured[-1][0])
        self.assertEqual(_callbacks(captured[-1][1]), _callbacks(type_markup))
        restored = runtime["get_internal_archive_pending"](user_id)
        self.assertEqual(restored["step"], "choosing_type")
        self.assertEqual(restored["department"], "customers")
        self.assertEqual(restored["document_type"], "customer_profile")
        self.assertEqual(runtime["_archive_lookup_calls"], [])
        self.assertEqual(runtime["_archive_recent_calls"], [])
        self.assertEqual(runtime["_archive_sent_documents"], [])

    def test_emitted_quick_save_back_returns_to_same_department(self):
        runtime, captured, _clock, click = _runtime()
        user_id = 700124

        asyncio.run(click(user_id, "archive|dept|customers"))
        department_markup = captured[-1][1]
        quick_button = next(
            button for row in department_markup.inline_keyboard for button in row
            if button.text == "📎 Lưu file vào nhóm này"
        )
        quick_query = asyncio.run(click(user_id, quick_button.callback_data))

        self.assertEqual(quick_query.answers, [((), {})])
        self.assertIn("Lưu nhanh vào nhóm Hồ sơ khách hàng", captured[-1][0])
        upload_markup = captured[-1][1]
        self.assertEqual(_callbacks(upload_markup), ["archive|back_department", "menu|main"])
        pending = runtime["get_internal_archive_pending"](user_id)
        self.assertEqual(pending["step"], "awaiting_file")
        self.assertEqual(pending["department"], "customers")
        self.assertEqual(pending["document_type"], "general")

        back_query = asyncio.run(click(user_id, _callbacks(upload_markup)[0]))

        self.assertEqual(back_query.answers, [((), {})])
        self.assertEqual(captured[-1][0], "DEPARTMENT DASHBOARD: customers")
        self.assertEqual(_callbacks(captured[-1][1]), _callbacks(department_markup))
        restored = runtime["get_internal_archive_pending"](user_id)
        self.assertEqual(restored["step"], "department_dashboard")
        self.assertEqual(restored["department"], "customers")
        self.assertEqual(runtime["_archive_lookup_calls"], [])
        self.assertEqual(runtime["_archive_recent_calls"], [])
        self.assertEqual(runtime["_archive_sent_documents"], [])

    def test_emitted_department_search_back_returns_to_same_department(self):
        runtime, captured, _clock, click = _runtime()
        user_id = 700125
        root_markup = runtime["internal_archive_menu_keyboard"]()
        department_callback = next(
            callback for callback in _callbacks(root_markup)
            if callback == "archive|dept|customers"
        )

        department_query = asyncio.run(click(user_id, department_callback))

        self.assertEqual(department_query.answers, [((), {})])
        department_markup = captured[-1][1]
        search_button = next(
            button for row in department_markup.inline_keyboard for button in row
            if button.text == "🔍 Tìm trong nhóm"
        )
        search_query = asyncio.run(click(user_id, search_button.callback_data))

        self.assertEqual(search_query.answers, [((), {})])
        self.assertIn("Tìm trong Hồ sơ khách hàng", captured[-1][0])
        search_markup = captured[-1][1]
        self.assertEqual(
            _callbacks(search_markup),
            ["archive|back_department|customers", "menu|main"],
        )
        pending = runtime["get_internal_archive_pending"](user_id)
        self.assertEqual(pending["step"], "awaiting_search_department")
        self.assertEqual(pending["department"], "customers")

        back_query = asyncio.run(click(user_id, _callbacks(search_markup)[0]))

        self.assertEqual(back_query.answers, [((), {})])
        self.assertEqual(captured[-1][0], "DEPARTMENT DASHBOARD: customers")
        self.assertEqual(_callbacks(captured[-1][1]), _callbacks(department_markup))
        restored = runtime["get_internal_archive_pending"](user_id)
        self.assertEqual(restored["step"], "department_dashboard")
        self.assertEqual(restored["department"], "customers")
        self.assertEqual(runtime["_archive_lookup_calls"], [])
        self.assertEqual(runtime["_archive_recent_calls"], [])
        self.assertEqual(runtime["_archive_sent_documents"], [])

    def test_emitted_department_back_returns_to_archive_root(self):
        runtime, captured, _clock, click = _runtime()
        user_id = 700126
        root_markup = runtime["internal_archive_menu_keyboard"]()
        root_callbacks = _callbacks(root_markup)

        department_query = asyncio.run(click(user_id, "archive|dept|customers"))

        self.assertEqual(department_query.answers, [((), {})])
        department_markup = captured[-1][1]
        back_button = next(
            button for row in department_markup.inline_keyboard for button in row
            if button.text == "⬅️ Hồ sơ nội bộ"
        )
        self.assertEqual(back_button.callback_data, "archive|root")

        back_query = asyncio.run(click(user_id, back_button.callback_data))

        self.assertEqual(back_query.answers, [((), {})])
        self.assertEqual(captured[-1][0], "ARCHIVE ROOT")
        self.assertEqual(_callbacks(captured[-1][1]), root_callbacks)
        self.assertIsNone(runtime["get_internal_archive_pending"](user_id))
        self.assertEqual(runtime["_archive_lookup_calls"], [])
        self.assertEqual(runtime["_archive_recent_calls"], [])
        self.assertEqual(runtime["_archive_sent_documents"], [])

    def test_emitted_discard_returns_to_department_and_preserves_other_user_pending(self):
        runtime, captured, _clock, click = _runtime()
        user_id = 700106
        other_user_id = 700107
        file_info = {
            "file_id": "fixture-discard-file",
            "file_name": "unsaved.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 48,
        }
        other_pending = {
            "department": "sales",
            "document_type": "sales_record",
            "file_info": {"file_id": "other-user-file", "file_name": "other.pdf"},
            "title": "Other user's draft",
        }
        runtime["set_internal_archive_pending"](
            user_id,
            "preview",
            department="customers",
            document_type="customer_profile",
            file_info=dict(file_info),
            title="Actor's unsaved draft",
        )
        runtime["set_internal_archive_pending"](
            other_user_id,
            "preview",
            **other_pending,
        )
        other_pending_state = dict(runtime["get_internal_archive_pending"](other_user_id))
        preview_markup = runtime["internal_archive_preview_keyboard"]()
        discard_button = next(
            button
            for row in preview_markup.inline_keyboard
            for button in row
            if button.text == "📁 Hồ sơ hiện tại"
        )
        self.assertEqual("archive|discard_to_dept", discard_button.callback_data)

        query = asyncio.run(click(user_id, discard_button.callback_data))

        self.assertEqual(query.answers, [((), {})])
        self.assertEqual(captured[-1][0], "DEPARTMENT DASHBOARD: customers")
        expected_dashboard = runtime["internal_archive_department_keyboard"]()
        self.assertEqual(_callbacks(captured[-1][1]), _callbacks(expected_dashboard))
        actor_state = runtime["get_internal_archive_pending"](user_id)
        self.assertEqual(actor_state["step"], "department_dashboard")
        self.assertEqual(actor_state["department"], "customers")
        self.assertNotIn("file_info", actor_state)
        self.assertNotIn("title", actor_state)
        self.assertEqual(
            runtime["get_internal_archive_pending"](other_user_id),
            other_pending_state,
        )

    def test_emitted_edit_control_enters_owner_metadata_pending_state(self):
        runtime, captured, _clock, click = _runtime()
        user_id = 700105
        file_info = {
            "file_id": "fixture-edit-file",
            "file_name": "fixture-profile.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 96,
        }
        runtime["set_internal_archive_pending"](
            user_id,
            "preview",
            department="customers",
            document_type="customer_profile",
            file_info=dict(file_info),
            title="Fixture profile only",
        )
        preview_markup = runtime["internal_archive_preview_keyboard"]()
        emitted_edit = next(
            callback for callback in _callbacks(preview_markup)
            if callback == "archive|edit"
        )

        query = asyncio.run(click(user_id, emitted_edit))

        self.assertEqual(query.answers, [((), {})])
        self.assertIn("Tên hồ sơ | tag | retention | bảo_mật | mô tả", captured[-1][0])
        pending = runtime["get_internal_archive_pending"](user_id)
        self.assertEqual(pending["step"], "awaiting_metadata")
        self.assertEqual(pending["department"], "customers")
        self.assertEqual(pending["document_type"], "customer_profile")
        self.assertEqual(pending["file_info"], file_info)
        self.assertEqual(pending["title"], "Fixture profile only")

    def test_emitted_change_department_back_returns_to_same_preview(self):
        runtime, captured, _clock, click = _runtime()
        user_id = 700104
        file_info = {
            "file_id": "fixture-archive-file",
            "file_name": "fixture.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 64,
        }
        runtime["set_internal_archive_pending"](
            user_id,
            "preview",
            department="customers",
            document_type="customer_profile",
            file_info=dict(file_info),
        )
        preview_markup = runtime["internal_archive_preview_keyboard"]()
        emitted_change_dept = next(
            callback for callback in _callbacks(preview_markup)
            if callback == "archive|change_dept"
        )

        change_query = asyncio.run(click(user_id, emitted_change_dept))

        self.assertEqual(change_query.answers, [((), {})])
        self.assertEqual(captured[-1][0], "📁 <b>Chọn phòng ban mới</b>")
        department_picker = captured[-1][1]
        self.assertEqual(
            _callbacks(department_picker),
            [
                "archive|dept|customers", "archive|dept|sales",
                "archive|preview", "menu|main",
            ],
        )
        preview_state = runtime["get_internal_archive_pending"](user_id)
        self.assertEqual(preview_state["step"], "preview")
        self.assertEqual(preview_state["department"], "customers")
        self.assertEqual(preview_state["document_type"], "customer_profile")
        self.assertEqual(preview_state["file_info"], file_info)

        emitted_back = next(
            callback for callback in _callbacks(department_picker)
            if callback == "archive|preview"
        )
        back_query = asyncio.run(click(user_id, emitted_back))

        self.assertEqual(back_query.answers, [((), {})])
        self.assertEqual(captured[-1][0], "PREVIEW: customers/customer_profile")
        self.assertEqual(_callbacks(captured[-1][1]), _callbacks(preview_markup))
        restored_state = runtime["get_internal_archive_pending"](user_id)
        self.assertEqual(restored_state["step"], "preview")
        self.assertEqual(restored_state["department"], "customers")
        self.assertEqual(restored_state["document_type"], "customer_profile")
        self.assertEqual(restored_state["file_info"], file_info)

    def test_emitted_department_help_back_returns_to_same_department(self):
        runtime, captured, _clock, click = _runtime()
        user_id = 700121

        root_markup = runtime["internal_archive_menu_keyboard"]()
        department_callback = next(
            callback for callback in _callbacks(root_markup)
            if callback == "archive|dept|customers"
        )
        asyncio.run(click(user_id, department_callback))
        department_markup = captured[-1][1]
        self.assertIn("archive|help", _callbacks(department_markup))

        help_callback = next(
            button.callback_data
            for row in department_markup.inline_keyboard
            for button in row
            if button.text == "ℹ️ Hướng dẫn lưu"
        )
        help_query = asyncio.run(click(user_id, help_callback))

        self.assertEqual(help_query.answers, [((), {})])
        self.assertIn("Hướng dẫn lưu — Hồ sơ khách hàng", captured[-1][0])
        help_markup = captured[-1][1]
        self.assertEqual(
            _callbacks(help_markup),
            ["archive|quick", "archive|types", "archive|back_department", "menu|main"],
        )
        emitted_back = next(
            button.callback_data
            for row in help_markup.inline_keyboard
            for button in row
            if button.text.startswith("⬅️")
        )
        self.assertEqual(emitted_back, "archive|back_department")

        back_query = asyncio.run(click(user_id, emitted_back))

        self.assertEqual(back_query.answers, [((), {})])
        self.assertEqual(captured[-1][0], "DEPARTMENT DASHBOARD: customers")
        self.assertEqual(_callbacks(captured[-1][1]), _callbacks(department_markup))
        state = runtime["get_internal_archive_pending"](user_id)
        self.assertEqual(state["step"], "department_dashboard")
        self.assertEqual(state["department"], "customers")
        self.assertEqual(runtime["_archive_lookup_calls"], [])
        self.assertEqual(runtime["_archive_recent_calls"], [])
        self.assertEqual(runtime["_archive_sent_documents"], [])

    def test_emitted_recent_button_renders_fixture_and_back_returns_to_department(self):
        runtime, captured, _clock, click = _runtime()
        user_id = 700120
        asyncio.run(click(user_id, "archive|dept|customers"))
        department_keyboard = captured[-1][1]
        emitted_recent = next(
            callback for callback in _callbacks(department_keyboard)
            if callback == "archive|recent"
        )

        recent_query = asyncio.run(click(user_id, emitted_recent))

        self.assertEqual(recent_query.answers, [((), {})])
        self.assertEqual(runtime["_archive_recent_calls"], [(user_id, "customers", 5)])
        self.assertEqual(
            captured[-1][0],
            "🕘 <b>Hồ sơ gần đây — customers</b>\n\n"
            "1. <b>Fixture policy</b>\n   Loại chung · 2026-01-01T00:00:00Z",
        )
        self.assertEqual(
            _callbacks(captured[-1][1]),
            ["archive|view|441", "archive|back_department", "menu|main"],
        )
        recent_state = runtime["get_internal_archive_pending"](user_id)
        self.assertEqual(recent_state["step"], "recent_results")
        self.assertEqual(recent_state["department"], "customers")
        self.assertEqual(recent_state["search_result_ids"], [441])

        back_query = asyncio.run(click(user_id, "archive|back_department"))

        self.assertEqual(back_query.answers, [((), {})])
        self.assertEqual(captured[-1][0], "DEPARTMENT DASHBOARD: customers")
        self.assertEqual(_callbacks(captured[-1][1]), _callbacks(department_keyboard))
        department_state = runtime["get_internal_archive_pending"](user_id)
        self.assertEqual(department_state["step"], "department_dashboard")
        self.assertEqual(department_state["department"], "customers")

    def test_emitted_archive_view_result_dispatches_and_renders_fixture_document(self):
        runtime, captured, _clock, click = _runtime()
        user_id = 700100
        results_markup = runtime["internal_archive_results_keyboard"](
            [{"id": 441, "title": "Fixture policy"}], department="customers", search=True
        )
        emitted_view = _callbacks(results_markup)[0]
        self.assertEqual(emitted_view, "archive|view|441")

        query = asyncio.run(click(user_id, emitted_view))

        self.assertEqual(query.answers, [((), {})])
        self.assertEqual(runtime["_archive_lookup_calls"], [(user_id, 441)])
        self.assertEqual(captured[-1][0], "DOCUMENT DETAIL: 441")
        self.assertEqual(
            _callbacks(captured[-1][1]),
            ["archive|file|441", "archive|search", "archive|root", "menu|main"],
        )

    def test_emitted_archive_file_button_sends_only_the_fixture_file(self):
        runtime, captured, _clock, click = _runtime()
        user_id = 700109
        results_markup = runtime["internal_archive_results_keyboard"](
            [{"id": 441, "title": "Fixture policy"}], department="customers", search=True
        )
        emitted_view = _callbacks(results_markup)[0]
        asyncio.run(click(user_id, emitted_view))
        emitted_file = next(
            callback for callback in _callbacks(captured[-1][1])
            if callback.startswith("archive|file|")
        )
        self.assertEqual(emitted_file, "archive|file|441")

        file_query = _Query(user_id, emitted_file)
        asyncio.run(runtime["_archive_dispatch"](file_query))

        self.assertEqual(file_query.answers, [((), {})])
        self.assertEqual(runtime["_archive_sent_documents"], [{
            "chat_id": -100441,
            "document": "fixture-file-id",
            "caption": "Hồ sơ #441: Fixture policy",
        }])
        self.assertEqual(runtime["_archive_lookup_calls"], [(user_id, 441), (user_id, 441)])

    def test_malformed_archive_id_alerts_and_stale_rows_render_recovery_without_cleanup(self):
        cases = (
            ("archive|view|not-an-id", "Mã hồ sơ không hợp lệ.", []),
            ("archive|view", "Mã hồ sơ không hợp lệ.", []),
            ("archive|view|999", "Không tìm thấy hồ sơ.", [(700110, 999)]),
            ("archive|file|not-an-id", "Mã hồ sơ không hợp lệ.", []),
            ("archive|file|442", "File không còn khả dụng.", [(700110, 442)]),
        )
        for callback_data, alert_text, expected_lookups in cases:
            with self.subTest(callback_data=callback_data):
                runtime, captured, _clock, _click = _runtime()
                query = _Query(700110, callback_data)
                self.assertTrue(_registered_archive_pattern().match(callback_data))
                error = None
                try:
                    asyncio.run(runtime["_archive_dispatch"](query))
                except Exception as exc:  # The regression asserts no handler exception.
                    error = exc

                self.assertIsNone(error, f"callback raised instead of failing closed: {error!r}")
                if expected_lookups:
                    self.assertEqual(query.answers, [((), {})])
                    self.assertIn(alert_text, captured[-1][0])
                    self.assertEqual(_callbacks(captured[-1][1])[-3:], [
                        "archive|search", "menu|main_memory", "menu|main",
                    ])
                else:
                    self.assertEqual(query.answers, [((alert_text,), {"show_alert": True})])
                    self.assertEqual(captured, [])
                self.assertEqual(runtime["_archive_lookup_calls"], expected_lookups)
                self.assertEqual(runtime["_archive_pending_clear_calls"], [])

    def test_root_search_prompt_back_returns_to_archive_root(self):
        runtime, captured, _clock, click = _runtime()
        user_id = 700101
        root_markup = runtime["internal_archive_menu_keyboard"]()
        self.assertEqual(
            _callbacks(root_markup),
            [
                "archive|dept|customers", "archive|dept|sales", "archive|search",
                "menu|main_memory", "menu|main",
            ],
        )

        search_button = next(
            button for row in root_markup.inline_keyboard for button in row
            if button.text == "🔍 Tìm hồ sơ"
        )
        self.assertEqual("archive|search", search_button.callback_data)
        search_query = asyncio.run(click(user_id, search_button.callback_data))
        self.assertEqual(search_query.answers, [((), {})])
        back_markup = captured[-1][1]
        self.assertEqual(_callbacks(back_markup), ["archive|root", "menu|main"])
        self.assertEqual(runtime["get_internal_archive_pending"](user_id)["step"], "awaiting_search")

        back_query = asyncio.run(click(user_id, _callbacks(back_markup)[0]))
        self.assertEqual(back_query.answers, [((), {})])
        self.assertEqual(captured[-1][0], "ARCHIVE ROOT")
        self.assertEqual(_callbacks(captured[-1][1]), _callbacks(root_markup))
        self.assertIsNone(runtime["get_internal_archive_pending"](user_id))

    def test_expired_department_search_back_still_returns_to_its_department(self):
        runtime, captured, clock, click = _runtime()
        user_id = 700102
        await_click = lambda callback: asyncio.run(click(user_id, callback))

        await_click("archive|dept|customers")
        department_markup = captured[-1][1]
        self.assertEqual(
            _callbacks(department_markup),
            [
                "archive|quick", "archive|recent", "archive|types", "archive|search_dept",
                "archive|help", "archive|root", "menu|main",
            ],
        )
        await_click("archive|search_dept")
        search_prompt_markup = captured[-1][1]
        self.assertEqual(_callbacks(search_prompt_markup), ["archive|back_department|customers", "menu|main"])
        self.assertEqual(runtime["get_internal_archive_pending"](user_id)["step"], "awaiting_search_department")

        clock[0] += 901
        await_click(_callbacks(search_prompt_markup)[0])

        state = runtime["get_internal_archive_pending"](user_id)
        self.assertEqual(state and state.get("step"), "department_dashboard")
        self.assertEqual(state and state.get("department"), "customers")
        self.assertEqual(captured[-1][0], "DEPARTMENT DASHBOARD: customers")
        self.assertEqual(_callbacks(captured[-1][1]), _callbacks(department_markup))

    def test_expired_emitted_quick_save_button_returns_to_root_without_pending(self):
        runtime, captured, clock, click = _runtime()
        user_id, other_user_id = 700104, 700105
        root_markup = runtime["internal_archive_menu_keyboard"]()
        department_callback = next(
            callback for callback in _callbacks(root_markup)
            if callback == "archive|dept|customers"
        )
        asyncio.run(click(user_id, department_callback))
        department_markup = captured[-1][1]
        quick_button = next(
            button for row in department_markup.inline_keyboard for button in row
            if button.text == "📎 Lưu file vào nhóm này"
        )
        clock[0] += 901
        other_state = runtime["set_internal_archive_pending"](
            other_user_id, "department_dashboard", department="sales"
        )
        stale_query = asyncio.run(click(user_id, quick_button.callback_data))

        self.assertEqual(stale_query.answers, [((), {})])
        self.assertEqual(captured[-1][0], "ARCHIVE ROOT")
        self.assertEqual(_callbacks(captured[-1][1]), _callbacks(root_markup))
        self.assertIsNone(runtime["get_internal_archive_pending"](user_id))
        self.assertEqual(
            runtime["get_internal_archive_pending"](other_user_id),
            other_state,
        )
        self.assertEqual(runtime["_archive_lookup_calls"], [])
        self.assertEqual(runtime["_archive_recent_calls"], [])
        self.assertEqual(runtime["_archive_sent_documents"], [])

    def test_expired_emitted_recent_button_returns_to_root_without_query(self):
        runtime, captured, clock, click = _runtime()
        user_id, other_user_id = 700106, 700107
        root_markup = runtime["internal_archive_menu_keyboard"]()
        department_callback = next(
            callback for callback in _callbacks(root_markup)
            if callback == "archive|dept|customers"
        )
        asyncio.run(click(user_id, department_callback))
        department_markup = captured[-1][1]
        recent_button = next(
            button for row in department_markup.inline_keyboard for button in row
            if button.text == "🕘 Hồ sơ gần đây"
        )

        clock[0] += 901
        other_state = runtime["set_internal_archive_pending"](
            other_user_id, "department_dashboard", department="sales"
        )
        stale_query = asyncio.run(click(user_id, recent_button.callback_data))

        self.assertEqual(stale_query.answers, [((), {})])
        self.assertEqual(captured[-1][0], "ARCHIVE ROOT")
        self.assertEqual(_callbacks(captured[-1][1]), _callbacks(root_markup))
        self.assertIsNone(runtime["get_internal_archive_pending"](user_id))
        self.assertEqual(
            runtime["get_internal_archive_pending"](other_user_id),
            other_state,
        )
        self.assertEqual(runtime["_archive_recent_calls"], [])
        self.assertEqual(runtime["_archive_lookup_calls"], [])
        self.assertEqual(runtime["_archive_sent_documents"], [])

    def test_expired_emitted_types_button_returns_to_root_without_upload_state(self):
        runtime, captured, clock, click = _runtime()
        user_id, other_user_id = 700108, 700109
        root_markup = runtime["internal_archive_menu_keyboard"]()
        department_callback = next(
            callback for callback in _callbacks(root_markup)
            if callback == "archive|dept|customers"
        )
        asyncio.run(click(user_id, department_callback))
        department_markup = captured[-1][1]
        types_button = next(
            button for row in department_markup.inline_keyboard for button in row
            if button.text == "🏷 Chọn loại hồ sơ"
        )

        clock[0] += 901
        other_state = runtime["set_internal_archive_pending"](
            other_user_id, "department_dashboard", department="sales"
        )
        stale_query = asyncio.run(click(user_id, types_button.callback_data))

        self.assertEqual(stale_query.answers, [((), {})])
        self.assertEqual(captured[-1][0], "ARCHIVE ROOT")
        self.assertEqual(_callbacks(captured[-1][1]), _callbacks(root_markup))
        self.assertIsNone(runtime["get_internal_archive_pending"](user_id))
        self.assertEqual(
            runtime["get_internal_archive_pending"](other_user_id),
            other_state,
        )
        self.assertEqual(runtime["_archive_lookup_calls"], [])
        self.assertEqual(runtime["_archive_recent_calls"], [])
        self.assertEqual(runtime["_archive_sent_documents"], [])

    def test_expired_emitted_department_search_returns_to_root_without_prompt(self):
        runtime, captured, clock, click = _runtime()
        user_id, other_user_id = 700110, 700111
        root_markup = runtime["internal_archive_menu_keyboard"]()
        department_callback = next(
            callback for callback in _callbacks(root_markup)
            if callback == "archive|dept|customers"
        )
        asyncio.run(click(user_id, department_callback))
        department_markup = captured[-1][1]
        search_button = next(
            button for row in department_markup.inline_keyboard for button in row
            if button.text == "🔍 Tìm trong nhóm"
        )

        clock[0] += 901
        other_state = runtime["set_internal_archive_pending"](
            other_user_id, "department_dashboard", department="sales"
        )
        stale_query = asyncio.run(click(user_id, search_button.callback_data))

        self.assertEqual(stale_query.answers, [((), {})])
        self.assertEqual(captured[-1][0], "ARCHIVE ROOT")
        self.assertEqual(_callbacks(captured[-1][1]), _callbacks(root_markup))
        self.assertIsNone(runtime["get_internal_archive_pending"](user_id))
        self.assertEqual(
            runtime["get_internal_archive_pending"](other_user_id),
            other_state,
        )
        self.assertEqual(runtime["_archive_recent_calls"], [])
        self.assertEqual(runtime["_archive_lookup_calls"], [])
        self.assertEqual(runtime["_archive_sent_documents"], [])

    def test_live_department_state_outranks_stale_search_back_payload(self):
        runtime, captured, _clock, click = _runtime()
        user_id = 700103
        runtime["set_internal_archive_pending"](
            user_id, "department_dashboard", department="sales"
        )

        asyncio.run(click(user_id, "archive|back_department|customers"))

        state = runtime["get_internal_archive_pending"](user_id)
        self.assertEqual(state["step"], "department_dashboard")
        self.assertEqual(state["department"], "sales")
        self.assertEqual(captured[-1][0], "DEPARTMENT DASHBOARD: sales")
        self.assertEqual(
            _callbacks(captured[-1][1]),
            [
                "archive|quick", "archive|recent", "archive|types", "archive|search_dept",
                "archive|help", "archive|root", "menu|main",
            ],
        )


if __name__ == "__main__":
    unittest.main()
