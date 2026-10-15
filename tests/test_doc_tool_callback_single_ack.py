import asyncio
import re
from pathlib import Path
from types import SimpleNamespace


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


class _Query:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(id=123, username="tester", first_name="Tester")
        self.message = SimpleNamespace()
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


class _Button:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


def _source_function(name):
    match = re.search(
        rf"(?ms)^(?:async\s+)?def {re.escape(name)}\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)",
        BOT_SOURCE,
    )
    assert match, f"document-tool function {name} is missing"
    return match.group(0)


def _load_runtime(state, edits):
    async def _safe_edit_or_send(query, text, **kwargs):
        edits.append((query, text, kwargs))

    copy = {
        "docs_send_pdf": "Send PDF",
        "docs_send_image": "Send image",
        "docs_remove_last_file": "Remove last file",
        "docs_clear_all": "Clear all",
    }
    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "get_user_language": lambda _uid: "vi",
        "get_doc_tool_pending": lambda _uid: state,
        "doc_tool_config": lambda _tool: {"min_files": 2, "expected": "pdf"},
        "doc_tool_start_text": lambda tool, lang: f"start-{tool}-{lang}",
        "doc_tool_start_keyboard": lambda tool, lang, _state: f"keyboard-{tool}-{lang}",
        "safe_edit_or_send": _safe_edit_or_send,
        "is_admin_user": lambda _uid: False,
        "localized_start_menu_text": lambda _uid, lang: f"main-{lang}",
        "localized_main_menu_keyboard": lambda _is_admin, lang: f"main-keyboard-{lang}",
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "normalize_user_language": lambda lang: lang or "vi",
        "public_hub_copy": lambda _lang: copy,
        "doc_tool_display_copy": lambda _tool, _lang: ("🧩 Merge PDF", "PDF", "Merge"),
        "doc_tool_parent_action": lambda _state, _tool="": "main_docs",
        "doc_tool_parent_label": lambda _state, _tool, _lang: "⬅️ Documents",
        "ui_text": lambda _lang, _key: "🏠 Main menu",
    }
    for name in ("handle_doc_tool_callback", "doc_tool_after_file_keyboard"):
        exec(compile(_source_function(name), f"bot.py:{name}", "exec"), namespace)
    registrations = []
    namespace.update(
        tg_app=SimpleNamespace(add_handler=registrations.append),
        CallbackQueryHandler=lambda callback, pattern: SimpleNamespace(
            callback=callback,
            pattern=re.compile(pattern),
        ),
        registered_handlers=registrations,
    )
    registration = next(
        line.strip()
        for line in BOT_SOURCE.splitlines()
        if "tg_app.add_handler(CallbackQueryHandler(handle_doc_tool_callback," in line
    )
    exec(registration, namespace)
    return namespace


def _emitted_callback(markup, callback_data):
    return next(
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data == callback_data
    )


def _registered_doc_tool_route(namespace, callback_data):
    route = next(
        handler
        for handler in namespace["registered_handlers"]
        if handler.pattern.match(callback_data)
    )
    assert route.callback is namespace["handle_doc_tool_callback"]
    return route


def test_confirm_with_too_few_files_gets_one_alert_ack():
    state = {"doc_tool_current": "merge_pdf", "doc_tool_files": ["file-1"]}
    edits = []
    namespace = _load_runtime(state, edits)
    emitted = _emitted_callback(
        namespace["doc_tool_after_file_keyboard"](state, "vi"),
        "docflow|confirm",
    )
    route = _registered_doc_tool_route(namespace, emitted)
    query = _Query(emitted)
    asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [(("Chưa đủ file để xử lý.",), {"show_alert": True})], query.answers
    assert edits == []


def test_confirm_acknowledges_before_language_lookup():
    state = {"doc_tool_current": "merge_pdf", "doc_tool_files": ["file-1", "file-2"]}
    edits = []
    namespace = _load_runtime(state, edits)
    emitted = _emitted_callback(
        namespace["doc_tool_after_file_keyboard"](state, "vi"),
        "docflow|confirm",
    )
    route = _registered_doc_tool_route(namespace, emitted)
    query = _Query(emitted)
    events = []
    namespace.update(
        get_user_language=lambda _uid: events.append("language") or "vi",
        doc_tool_confirm_text=lambda _state, lang: f"confirm-{lang}",
        doc_tool_confirm_keyboard=lambda lang, _state: f"confirm-keyboard-{lang}",
    )

    original_answer = query.answer

    async def _answer(*args, **kwargs):
        events.append("ack")
        await original_answer(*args, **kwargs)

    query.answer = _answer
    asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert events == ["ack", "language"], events
    assert query.answers == [((), {})]
    assert edits == [(query, "confirm-vi", {"parse_mode": "HTML", "reply_markup": "confirm-keyboard-vi"})]


def test_send_more_keeps_one_ack_and_existing_document_screen():
    state = {"doc_tool_current": "merge_pdf", "doc_tool_files": ["file-1"]}
    edits = []
    namespace = _load_runtime(state, edits)
    emitted = _emitted_callback(
        namespace["doc_tool_after_file_keyboard"](state, "vi"),
        "docflow|send_more",
    )
    route = _registered_doc_tool_route(namespace, emitted)
    query = _Query(emitted)
    asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [((), {})]
    assert edits == [(query, "start-merge_pdf-vi", {"parse_mode": "HTML", "reply_markup": "keyboard-merge_pdf-vi"})]


def test_back_acknowledges_before_user_language_lookup():
    state = {"doc_tool_current": "merge_pdf", "doc_tool_files": ["file-1"]}
    edits = []
    namespace = _load_runtime(state, edits)
    emitted = _emitted_callback(
        namespace["doc_tool_after_file_keyboard"](state, "vi"),
        "docflow|back|main_docs",
    )
    route = _registered_doc_tool_route(namespace, emitted)
    query = _Query(emitted)
    language_lookup_after_ack = []
    cleared = []
    namespace.update(
        get_user_language=lambda _uid: language_lookup_after_ack.append(bool(query.answers)) or "vi",
        clear_doc_tool_pending=cleared.append,
        menu_text_main_docs_i18n=lambda lang: f"documents-{lang}",
        main_docs_keyboard=lambda lang: f"documents-keyboard-{lang}",
    )

    asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert language_lookup_after_ack == [True], language_lookup_after_ack
    assert query.answers == [((), {})]
    assert cleared == [123]
    assert edits == [
        (query, "documents-vi", {"parse_mode": "HTML", "reply_markup": "documents-keyboard-vi"})
    ]
