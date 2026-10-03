"""Exercise split-PDF page-prompt Back from its button through the real route."""
import asyncio
import re
import time
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace


SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def _source_function(name):
    start = re.search(rf"(?m)^(?:async )?def {re.escape(name)}\(", SOURCE)
    assert start, f"missing actual source function: {name}"
    following = re.search(r"(?m)^(?:async )?def [A-Za-z_]\w*\(", SOURCE[start.end():])
    end = start.end() + following.start() if following else len(SOURCE)
    return SOURCE[start.start():end]


class _Button:
    def __init__(self, text, callback_data=None, **kwargs):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class _Query:
    def __init__(self, data, user_id):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _runtime(user_id, files, options):
    screens = []

    async def render(_query, text, **kwargs):
        screens.append((text, kwargs.get("reply_markup")))

    runtime = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "USER_PENDING": {
            f"doc_tool:{user_id}": {
                "doc_tool_current": "split_pdf",
                "doc_tool_files": list(files),
                "doc_files": list(files),
                "doc_tool_file_count": len(files),
                "doc_tool_options": dict(options),
                "doc_tool_previous_step": "main_docs",
                "doc_previous_menu": "main_docs",
                "doc_tool_user_id": str(user_id),
                "awaiting_page_spec": "0",
                "created_at_ts": time.time(),
            }
        },
        "time": time,
        "DOC_TOOL_STATE_TTL_SECONDS": 600,
        "DOC_TOOL_MAX_FILES": 20,
        "DOC_TOOL_CONFIG": {"split_pdf": {"expected": "pdf", "max_files": 5, "min_files": 1}},
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "public_hub_copy": lambda _lang: defaultdict(lambda: "label"),
        "normalize_user_language": lambda lang: lang,
        "doc_tool_config": lambda tool: {"expected": "pdf", "max_files": 5, "min_files": 1},
        "doc_tool_parent_label": lambda *_args: "⬅️ Back to Docs",
        "ui_text": lambda *_args: "Home",
        "doc_tool_received_text": lambda *_args: "Received files",
        "doc_tool_start_text": lambda *_args: "Upload files",
        "doc_tool_start_keyboard": lambda *_args: _Markup([]),
        "doc_tool_confirm_text": lambda *_args: "Confirm",
        "doc_tool_confirm_keyboard": lambda *_args: _Markup([]),
        "get_user_language": lambda _uid: "vi",
        "safe_edit_or_send": render,
        "menu_text_main_docs_i18n": lambda _lang: "Docs menu",
        "main_docs_keyboard": lambda _lang: "docs-keyboard",
        "logger": SimpleNamespace(warning=lambda *args, **kwargs: None),
    }
    for name in (
        "doc_tool_pending_key",
        "clear_doc_tool_pending",
        "get_doc_tool_pending",
        "doc_tool_parent_action",
        "doc_tool_after_file_keyboard",
        "handle_doc_tool_callback",
    ):
        exec(
            compile("from __future__ import annotations\n" + _source_function(name), f"bot.py:{name}", "exec"),
            runtime,
        )

    registrations = re.findall(
        r"(?m)^\s*tg_app\.add_handler\(CallbackQueryHandler\(handle_doc_tool_callback,.*$",
        SOURCE,
    )
    assert len(registrations) == 1, "document callback must have one registered route"
    routes = []
    runtime.update(
        tg_app=SimpleNamespace(add_handler=routes.append),
        CallbackQueryHandler=lambda callback, pattern: (callback, re.compile(pattern)),
    )
    exec(compile(registrations[0].strip(), "bot.py:document callback registration", "exec"), runtime)
    assert len(routes) == 1
    callback, pattern = routes[0]
    return runtime, screens, callback, pattern


def _click(callback, pattern, data, user_id):
    assert pattern.search(data), f"registered document handler does not accept {data!r}"
    query = _Query(data, user_id)
    asyncio.run(callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    return query


def _callback_for(markup, label_prefix):
    return next(
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.text.startswith(label_prefix)
    )


def test_split_pdf_page_prompt_back_emits_preserving_route_and_keeps_selection():
    user_id = 77
    files = [{"file_id": "keep-file", "file_name": "input.pdf"}]
    options = {"preserved_option": "value"}
    runtime, screens, callback, pattern = _runtime(user_id, files, options)

    # Follow the real emitted Ask-pages action to enter the input prompt.
    received_markup = runtime["doc_tool_after_file_keyboard"](
        runtime["get_doc_tool_pending"](user_id), "vi"
    )
    ask_pages = _callback_for(received_markup, "✍️")
    _click(callback, pattern, ask_pages, user_id)
    prompting_state = runtime["get_doc_tool_pending"](user_id)
    assert prompting_state["awaiting_page_spec"] == "1"

    # Click Back from the keyboard actually rendered at the page prompt.
    back_button = next(
        button
        for row in screens[-1][1].inline_keyboard
        for button in row
        if button.text.startswith("⬅️")
    )
    emitted_back = back_button.callback_data
    back_query = _click(callback, pattern, emitted_back, user_id)
    state = runtime["get_doc_tool_pending"](user_id)

    assert state["awaiting_page_spec"] == "0"
    assert state["doc_tool_files"] == files
    assert state["doc_files"] == files
    assert state["doc_tool_file_count"] == 1
    assert state["doc_tool_options"] == options
    assert screens[-1][0] == "Received files"
    assert emitted_back == "docflow|back_received"
    assert back_button.text == "⬅️ label"
    assert back_query.answers == [((), {})]


def test_document_tool_parent_back_still_clears_session_and_returns_docs_menu():
    user_id = 78
    runtime, screens, callback, pattern = _runtime(
        user_id,
        [{"file_id": "release-file", "file_name": "input.pdf"}],
        {},
    )
    markup = runtime["doc_tool_after_file_keyboard"](
        runtime["get_doc_tool_pending"](user_id), "vi"
    )
    emitted_back = _callback_for(markup, "⬅️")
    query = _click(callback, pattern, emitted_back, user_id)

    assert emitted_back == "docflow|back"
    assert runtime["get_doc_tool_pending"](user_id) == {}
    assert screens[-1] == ("Docs menu", "docs-keyboard")
    assert query.answers == [((), {})]
