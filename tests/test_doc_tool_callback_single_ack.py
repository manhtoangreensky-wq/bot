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
        "docs_confirm": "Confirm",
        "docs_add_more": "Add more",
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
    for name in (
        "handle_doc_tool_callback",
        "doc_tool_after_file_keyboard",
        "doc_tool_confirm_keyboard",
    ):
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


def _run_no_io(awaitable):
    try:
        awaitable.send(None)
    except StopIteration as completed:
        return completed.value
    raise AssertionError("fixture callback unexpectedly yielded I/O")


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
    _run_no_io(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [(("Chưa đủ file để xử lý.",), {"show_alert": True})], query.answers
    assert edits == []


def test_valid_confirm_acknowledges_before_user_language_lookup():
    state = {"doc_tool_current": "merge_pdf", "doc_tool_files": ["file-1", "file-2"]}
    edits = []
    namespace = _load_runtime(state, edits)
    emitted = _emitted_callback(
        namespace["doc_tool_after_file_keyboard"](state, "vi"),
        "docflow|confirm",
    )
    route = _registered_doc_tool_route(namespace, emitted)
    query = _Query(emitted)
    language_lookup_after_ack = []
    thread_calls = []

    def get_language(_uid):
        language_lookup_after_ack.append(bool(query.answers))
        return "vi"

    async def to_thread(function, *args):
        thread_calls.append((function.__name__, args, bool(query.answers)))
        return function(*args)

    namespace.update(
        get_user_language=get_language,
        doc_tool_confirm_text=lambda _state, _lang: "merge-confirm",
        doc_tool_confirm_keyboard=lambda _lang, _state: "merge-confirm-keyboard",
        asyncio=SimpleNamespace(to_thread=to_thread),
    )

    _run_no_io(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert language_lookup_after_ack == [True], language_lookup_after_ack
    assert thread_calls == [("get_language", (123,), True)], thread_calls
    assert query.answers == [((), {})]
    assert edits == [
        (query, "merge-confirm", {"parse_mode": "HTML", "reply_markup": "merge-confirm-keyboard"})
    ]


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
    _run_no_io(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

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

    _run_no_io(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert language_lookup_after_ack == [True], language_lookup_after_ack
    assert query.answers == [((), {})]
    assert cleared == [123]
    assert edits == [
        (query, "documents-vi", {"parse_mode": "HTML", "reply_markup": "documents-keyboard-vi"})
    ]


def test_expired_emitted_confirm_fails_closed_without_processing():
    clock = [100.0]
    expired_state = {
        "doc_tool_current": "merge_pdf",
        "doc_tool_files": ["fixture-file"],
        "created_at_ts": clock[0],
    }
    another_users_state = {
        "doc_tool_current": "merge_pdf",
        "doc_tool_files": ["other-file"],
        "created_at_ts": 195.0,
    }
    edits = []
    namespace = _load_runtime(expired_state, edits)
    pending = {"doc_tool:123": expired_state, "doc_tool:999": another_users_state}
    namespace.update(
        USER_PENDING=pending,
        DOC_TOOL_STATE_TTL_SECONDS=60,
        time=SimpleNamespace(time=lambda: clock[0]),
        doc_tools_keyboard=lambda _lang: "document-hub-keyboard",
    )
    for helper in ("doc_tool_pending_key", "get_doc_tool_pending", "clear_doc_tool_pending"):
        exec(compile(_source_function(helper), f"bot.py:{helper}", "exec"), namespace)

    emitted = _emitted_callback(
        namespace["doc_tool_after_file_keyboard"](expired_state, "vi"),
        "docflow|confirm",
    )
    route = _registered_doc_tool_route(namespace, emitted)
    clock[0] = 200.0
    query = _Query(emitted)
    language_after_ack = []
    processing_calls = []

    def get_language(_uid):
        language_after_ack.append(bool(query.answers))
        return "vi"

    async def to_thread(function, *args):
        return function(*args)

    def forbidden_processing(*_args, **_kwargs):
        processing_calls.append("run_doc_tool_state")
        raise AssertionError("expired confirmation must not process a file")

    namespace.update(
        get_user_language=get_language,
        asyncio=SimpleNamespace(to_thread=to_thread),
        run_doc_tool_state=forbidden_processing,
    )
    _run_no_io(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert language_after_ack == [True]
    assert query.answers == [((), {})]
    assert pending == {"doc_tool:999": another_users_state}, pending
    assert edits == [(
        query,
        "⏰ Yêu cầu tài liệu đã hết hạn. TOAN AAS chưa xử lý file và chưa trừ Xu.",
        {"reply_markup": "document-hub-keyboard"},
    )]
    assert processing_calls == []


def test_expired_emitted_run_fails_closed_without_processing():
    clock = [100.0]
    expired_state = {
        "doc_tool_current": "merge_pdf",
        "doc_tool_files": ["fixture-file-1", "fixture-file-2"],
        "created_at_ts": clock[0],
    }
    another_users_state = {
        "doc_tool_current": "merge_pdf",
        "doc_tool_files": ["other-file"],
        "created_at_ts": 195.0,
    }
    edits = []
    namespace = _load_runtime(expired_state, edits)
    pending = {"doc_tool:123": expired_state, "doc_tool:999": another_users_state}
    namespace.update(
        USER_PENDING=pending,
        DOC_TOOL_STATE_TTL_SECONDS=60,
        time=SimpleNamespace(time=lambda: clock[0]),
        doc_tools_keyboard=lambda _lang: "document-hub-keyboard",
    )
    for helper in ("doc_tool_pending_key", "get_doc_tool_pending", "clear_doc_tool_pending"):
        exec(compile(_source_function(helper), f"bot.py:{helper}", "exec"), namespace)

    emitted = _emitted_callback(
        namespace["doc_tool_confirm_keyboard"]("vi", expired_state),
        "docflow|run",
    )
    route = _registered_doc_tool_route(namespace, emitted)
    clock[0] = 200.0
    query = _Query(emitted)
    language_after_ack = []
    processing_calls = []

    def get_language(_uid):
        language_after_ack.append(bool(query.answers))
        return "vi"

    async def to_thread(function, *args):
        return function(*args)

    def forbidden_processing(*_args, **_kwargs):
        processing_calls.append("run_doc_tool_state")
        raise AssertionError("expired run button must not process a file")

    namespace.update(
        get_user_language=get_language,
        asyncio=SimpleNamespace(to_thread=to_thread),
        run_doc_tool_state=forbidden_processing,
    )
    _run_no_io(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert language_after_ack == [True]
    assert query.answers == [((), {})]
    assert pending == {"doc_tool:999": another_users_state}, pending
    assert edits == [(
        query,
        "⏰ Yêu cầu tài liệu đã hết hạn. TOAN AAS chưa xử lý file và chưa trừ Xu.",
        {"reply_markup": "document-hub-keyboard"},
    )]
    assert processing_calls == []


def test_expired_emitted_file_controls_do_not_mutate_pending_state():
    clock = [100.0]
    expired_state = {
        "doc_tool_current": "merge_pdf",
        "doc_tool_files": ["fixture-file-1", "fixture-file-2"],
        "created_at_ts": clock[0],
    }
    another_users_state = {
        "doc_tool_current": "merge_pdf",
        "doc_tool_files": ["other-file"],
        "created_at_ts": 195.0,
    }
    edits = []
    namespace = _load_runtime(expired_state, edits)
    pending = {"doc_tool:999": another_users_state}
    namespace.update(
        USER_PENDING=pending,
        DOC_TOOL_STATE_TTL_SECONDS=60,
        time=SimpleNamespace(time=lambda: clock[0]),
        doc_tools_keyboard=lambda _lang: "document-hub-keyboard",
    )
    for helper in ("doc_tool_pending_key", "get_doc_tool_pending", "clear_doc_tool_pending"):
        exec(compile(_source_function(helper), f"bot.py:{helper}", "exec"), namespace)

    for callback_data in ("docflow|send_more", "docflow|pop", "docflow|clear"):
        clock[0] = 100.0
        pending["doc_tool:123"] = expired_state.copy()
        emitted = _emitted_callback(
            namespace["doc_tool_after_file_keyboard"](expired_state, "vi"),
            callback_data,
        )
        route = _registered_doc_tool_route(namespace, emitted)
        clock[0] = 200.0
        query = _Query(emitted)

        def get_language(_uid):
            assert query.answers, "language lookup must follow ACK"
            return "vi"

        namespace.update(get_user_language=get_language)
        _run_no_io(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

        assert query.answers == [((), {})], (callback_data, query.answers)
        assert pending == {"doc_tool:999": another_users_state}, (callback_data, pending)
        assert edits[-1] == (
            query,
            "⏰ Yêu cầu tài liệu đã hết hạn. TOAN AAS chưa xử lý file và chưa trừ Xu.",
            {"reply_markup": "document-hub-keyboard"},
        ), (callback_data, edits[-1])


def test_active_emitted_clear_list_only_resets_actor_and_returns_to_upload():
    now = 200.0
    actor_state = {
        "doc_tool_current": "merge_pdf",
        "doc_tool_files": ["actor-file-1", "actor-file-2"],
        "doc_files": ["actor-file-1", "actor-file-2"],
        "doc_tool_file_count": 2,
        "doc_tool_options": {"fixture_option": "keep-only-until-clear"},
        "created_at_ts": now,
    }
    another_users_state = {
        "doc_tool_current": "merge_pdf",
        "doc_tool_files": ["other-file"],
        "doc_files": ["other-file"],
        "doc_tool_file_count": 1,
        "doc_tool_options": {"other_option": "preserve"},
        "created_at_ts": now,
    }
    edits = []
    namespace = _load_runtime(actor_state, edits)
    pending = {"doc_tool:123": actor_state, "doc_tool:999": another_users_state}
    namespace.update(
        USER_PENDING=pending,
        DOC_TOOL_STATE_TTL_SECONDS=60,
        time=SimpleNamespace(time=lambda: now),
        doc_tool_start_text=lambda tool, lang: f"upload-prompt-{tool}-{lang}",
        doc_tool_start_keyboard=lambda tool, lang, _state: f"upload-keyboard-{tool}-{lang}",
    )
    for helper in ("doc_tool_pending_key", "get_doc_tool_pending", "clear_doc_tool_pending"):
        exec(compile(_source_function(helper), f"bot.py:{helper}", "exec"), namespace)

    emitted = _emitted_callback(
        namespace["doc_tool_after_file_keyboard"](actor_state, "vi"),
        "docflow|clear",
    )
    route = _registered_doc_tool_route(namespace, emitted)
    query = _Query(emitted)
    language_after_ack = []

    def get_language(_uid):
        language_after_ack.append(bool(query.answers))
        return "vi"

    namespace.update(get_user_language=get_language)
    _run_no_io(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert language_after_ack == [True]
    assert query.answers == [((), {})]
    assert actor_state["doc_tool_files"] == []
    assert actor_state["doc_files"] == []
    assert actor_state["doc_tool_file_count"] == 0
    assert actor_state["doc_tool_options"] == {}
    assert pending["doc_tool:999"] == another_users_state
    assert edits == [(
        query,
        "🧹 Đã xóa danh sách file tạm. TOAN AAS chưa xử lý và chưa trừ Xu.",
        {"reply_markup": "upload-keyboard-merge_pdf-vi"},
    )]
