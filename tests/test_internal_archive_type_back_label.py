import asyncio
import time
from pathlib import Path
from types import SimpleNamespace


class _Button:
    def __init__(self, text, callback_data):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


def _runtime():
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")

    def block(start, end):
        first = source.index(start)
        return source[first:source.index(end, first)]

    definitions = "\n".join((
        block("def internal_archive_pending_key(", "def internal_archive_menu_text()"),
        block("def internal_archive_type_keyboard(", "def internal_archive_type_text("),
        block("async def handle_internal_archive_callback(", "async def handle_internal_archive_pending_upload("),
    ))
    captured = []
    namespace = {
        "time": time,
        "USER_PENDING": {},
        "INTERNAL_ARCHIVE_TTL_SECONDS": 900,
        "INTERNAL_DOC_DEPARTMENTS": {"customers": "Hồ sơ khách hàng"},
        "INTERNAL_DOC_TYPES": {"customers": ("customer_profile",)},
        "document_type_label": lambda _value: "Hồ sơ khách hàng",
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "SimpleNamespace": SimpleNamespace,
        "is_admin_user": lambda _uid: True,
        "clear_doc_tool_pending": lambda _uid: None,
        "clear_media_creator_pending_states": lambda _uid: None,
        "internal_archive_type_text": lambda _department: "TYPE SCREEN",
        "internal_archive_preview_text": lambda state: f"PREVIEW: {state['file_info']['file_name']}",
        "internal_archive_preview_keyboard": lambda: _Markup([]),
        "internal_archive_department_text": lambda _department: "DEPARTMENT DASHBOARD",
        "internal_archive_department_keyboard": lambda: _Markup([]),
    }
    exec(compile("from __future__ import annotations\n" + definitions, "bot.py", "exec"), namespace)

    async def safe_edit(_query, text, **kwargs):
        captured.append((text, kwargs.get("reply_markup")))

    namespace["safe_edit_query_message"] = safe_edit

    class FakeQuery:
        def __init__(self, user_id, data):
            self.data = data
            self.from_user = SimpleNamespace(id=user_id)
            self.message = SimpleNamespace()

        async def answer(self, *args, **kwargs):
            return None

    async def click(user_id, data):
        await namespace["handle_internal_archive_callback"](
            SimpleNamespace(callback_query=FakeQuery(user_id, data)),
            SimpleNamespace(),
        )

    return namespace, captured, click


def _back_button(markup):
    return next(
        button
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data == "archive|back_department"
    )


def test_internal_archive_callback_is_registered_on_telegram_application():
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
    assert r'tg_app.add_handler(CallbackQueryHandler(handle_internal_archive_callback, pattern=r"^archive\|"))' in source


def test_internal_archive_type_back_label_matches_pending_file_destination():
    runtime, captured, click = _runtime()
    user_id = 887766
    file_info = {
        "file_id": "pending-file-id",
        "file_name": "draft.pdf",
        "mime_type": "application/pdf",
        "size_bytes": 123,
    }
    runtime["set_internal_archive_pending"](
        user_id,
        "preview",
        department="customers",
        document_type="customer_profile",
        file_info=file_info,
        title="Pending customer document",
    )

    asyncio.run(click(user_id, "archive|types"))
    state = runtime["get_internal_archive_pending"](user_id)
    assert state["step"] == "choosing_type"
    assert state["file_info"] == file_info
    back_button = _back_button(captured[-1][1])

    asyncio.run(click(user_id, "archive|back_department"))
    state = runtime["get_internal_archive_pending"](user_id)
    assert state["step"] == "preview"
    assert state["file_info"] == file_info
    assert state["title"] == "Pending customer document"
    assert "draft.pdf" in captured[-1][0]

    assert back_button.text == "⬅️ Xem lại hồ sơ"


def test_internal_archive_type_back_label_stays_department_without_pending_file():
    runtime, captured, click = _runtime()
    user_id = 887767
    runtime["set_internal_archive_pending"](user_id, "department_dashboard", department="customers")

    asyncio.run(click(user_id, "archive|types"))
    back_button = _back_button(captured[-1][1])

    asyncio.run(click(user_id, "archive|back_department"))
    state = runtime["get_internal_archive_pending"](user_id)
    assert state["step"] == "department_dashboard"
    assert state["department"] == "customers"
    assert back_button.text == "⬅️ Phòng ban"
