import asyncio
import time
from pathlib import Path
from types import SimpleNamespace


class FakeQuery:
    def __init__(self, uid: int, data: str):
        self.data = data
        self.from_user = SimpleNamespace(id=uid, username="admin", first_name="Admin")
        self.message = SimpleNamespace(chat_id=uid)

    async def answer(self, *args, **kwargs):
        return None


class FakeMessage:
    def __init__(self):
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append((str(text), kwargs))
        return SimpleNamespace()


def _pending_namespace():
    pending = {}

    def set_pending(user_id, tool, command="", **_kwargs):
        pending[int(user_id)] = {"tool": tool, "command": command, "confirm_paid": True}

    def get_pending(user_id):
        return dict(pending.get(int(user_id)) or {})

    def clear_pending(user_id):
        return pending.pop(int(user_id), None) is not None

    return pending, set_pending, get_pending, clear_pending


def _install_local_video_planning_pending_clear(source, namespace):
    start = source.index("def _local_video_planning_user_data(")
    end = source.index("\ndef _local_video_planning_set_pending(", start)
    namespace["_LOCAL_VIDEO_PLANNING_PENDING_KEY"] = "local_video_planning_pending_brief"
    exec(compile(source[start:end], "bot.py:local_video_planning_pending_clear", "exec"), namespace)


def _install_finance_compliance_pending(source, namespace, user_pending):
    start = source.index("def finance_compliance_pending_key(")
    end = source.index("\nasync def handle_finance_compliance_pending_text(", start)
    namespace["USER_PENDING"] = user_pending
    namespace["time"] = time
    exec(compile(source[start:end], "bot.py:finance_compliance_pending", "exec"), namespace)


def _planning_context(uid):
    saved_plan_store = {
        "sessions": {"session-1": {"screen": "brief", "session_id": "session-1"}},
        "active_by_chat": {str(uid): "session-1"},
    }
    return SimpleNamespace(
        args=[],
        user_data={
            "local_video_planning_pending_brief": {
                "user_id": str(uid),
                "chat_id": str(uid),
                "session_id": "session-1",
                "expires_at": int(time.time()) + 60,
            },
            "local_video_studio27b_public": saved_plan_store,
            "video_edit_sentinel": {"unchanged": True},
        },
    ), saved_plan_store


def _run_immediate(coro):
    try:
        coro.send(None)
    except StopIteration as completed:
        return completed.value
    raise AssertionError("fixture unexpectedly yielded I/O")


def _emitted_video_home_callback(source):
    start = source.index("def main_video_keyboard(")
    end = source.index("\ndef video_prompt_library_text(", start)

    class Button:
        def __init__(self, text, callback_data):
            self.text = text
            self.callback_data = callback_data

    class Markup:
        def __init__(self, inline_keyboard):
            self.inline_keyboard = inline_keyboard

    namespace = {
        "InlineKeyboardButton": Button,
        "InlineKeyboardMarkup": Markup,
        "normalize_user_language": lambda _lang: "vi",
        "public_hub_copy": lambda _lang: {"main_menu": "Home"},
        "video_public_visible_menu_rows": lambda: (("main_menu",),),
    }
    exec(compile(source[start:end], "bot.py:main_video_keyboard", "exec"), namespace)
    emitted = next(
        button.callback_data
        for row in namespace["main_video_keyboard"]("vi").inline_keyboard
        for button in row
        if button.text == "Home"
    )
    assert 'CallbackQueryHandler(handle_menu_callback, pattern=r"^menu\\|")' in source
    return emitted


def _load_menu_handler(source, pending, set_pending, get_pending, clear_pending):
    start = source.index("async def handle_menu_callback(")
    end = source.index("\nasync def handle_free_hub_callback(", start)
    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "time": time,
        "logger": SimpleNamespace(info=lambda *_args, **_kwargs: None),
        "VIDEO_TAIL9_TEXT_INPUT_KEY": "probe-only",
        "DOC_TOOL_MENU_ACTIONS": set(),
        "PENDING_ADMIN_TOOL_TEST": pending,
        "set_pending_admin_tool_test": set_pending,
        "get_pending_admin_tool_test": get_pending,
        "clear_pending_admin_tool_test": clear_pending,
        "is_admin_user": lambda _uid: True,
        "get_user_language": lambda _uid: "vi",
        "localized_menu_content": lambda *_args, **_kwargs: ("main", object()),
    }

    async def fake_edit(_query, *_args, **_kwargs):
        return None

    namespace["safe_edit_query_message"] = fake_edit
    for name in (
        "clear_broadcast_lite_pending",
        "clear_translation_menu_pending",
        "clear_translation_session",
        "clear_media_creator_pending_states",
        "clear_support_ticket_pending",
        "clear_finance_compliance_pending",
        "clear_internal_archive_pending",
        "clear_doc_tool_pending",
        "clear_storage_addon_pending",
        "clear_memory_guided_pending",
        "clear_music_guided_pending",
    ):
        namespace[name] = lambda *_args, **_kwargs: None
    _install_local_video_planning_pending_clear(source, namespace)
    exec(compile(source[start:end], "bot.py:handle_menu_callback", "exec"), namespace)
    return namespace["handle_menu_callback"]


def _load_start_handler(source, pending, set_pending, get_pending, clear_pending):
    start = source.index("async def cmd_start(")
    end = source.index("\nasync def cmd_menu(", start)
    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "PENDING_ADMIN_TOOL_TEST": pending,
        "set_pending_admin_tool_test": set_pending,
        "get_pending_admin_tool_test": get_pending,
        "clear_pending_admin_tool_test": clear_pending,
        "clear_support_ticket_pending": lambda *_args, **_kwargs: None,
        "clear_internal_archive_pending": lambda *_args, **_kwargs: None,
        "clear_memory_guided_pending": lambda *_args, **_kwargs: None,
        "clear_doc_tool_pending": lambda *_args, **_kwargs: None,
        "clear_storage_addon_pending": lambda *_args, **_kwargs: None,
        "clear_finance_compliance_pending": lambda *_args, **_kwargs: None,
        "clear_translation_menu_pending": lambda *_args, **_kwargs: None,
        "clear_translation_session": lambda *_args, **_kwargs: None,
        "clear_broadcast_lite_pending": lambda *_args, **_kwargs: None,
        "log_command_received": lambda *_args, **_kwargs: None,
        "user_exists": lambda _uid: True,
        "get_user": lambda *_args, **_kwargs: None,
        "record_usage_event": lambda *_args, **_kwargs: None,
        "clear_pending_start_notice": lambda _uid: "",
        "is_admin_user": lambda _uid: True,
        "has_user_language": lambda _uid: True,
        "get_user_language": lambda _uid: "vi",
        "user_selected_vietnamese_initially": lambda _uid: False,
        "localized_start_menu_text": lambda *_args: "",
        "mode_start_notice": lambda _uid: "",
        "localized_main_menu_keyboard": lambda *_args: object(),
        "language_choice_text": lambda *_args: "",
        "language_choice_keyboard": lambda *_args: object(),
        "asyncio": asyncio,
    }

    _install_local_video_planning_pending_clear(source, namespace)

    async def fake_gift(*_args, **_kwargs):
        return None

    namespace["maybe_auto_grant_birthday_gift"] = fake_gift
    exec(compile(source[start:end], "bot.py:cmd_start", "exec"), namespace)
    return namespace["cmd_start"]


def _load_menu_command(source, start_handler):
    start = source.index("async def cmd_menu(")
    end = source.index("\nasync def cmd_language(", start)
    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "cmd_start": start_handler,
    }
    exec(compile(source[start:end], "bot.py:cmd_menu", "exec"), namespace)
    return namespace["cmd_menu"]


def test_menu_exit_clears_pending_admin_tool_test():
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
    uid = 983201
    pending, set_pending, get_pending, clear_pending = _pending_namespace()
    handler = _load_menu_handler(source, pending, set_pending, get_pending, clear_pending)
    set_pending(uid, "asr", "/tool_test_asr")

    asyncio.run(
        handler(
            SimpleNamespace(callback_query=FakeQuery(uid, "menu|main")),
            SimpleNamespace(user_data={}),
        )
    )

    assert get_pending(uid) == {}


def test_start_exit_clears_pending_admin_tool_test():
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
    uid = 983202
    message = FakeMessage()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=uid, first_name="Admin", username="admin"),
        effective_chat=SimpleNamespace(id=uid),
        effective_message=message,
        message=message,
    )
    context = SimpleNamespace(args=[], user_data={})
    pending, set_pending, get_pending, clear_pending = _pending_namespace()
    handler = _load_start_handler(source, pending, set_pending, get_pending, clear_pending)
    set_pending(uid, "full_dub_video", "/tool_test_full_dub_video")

    asyncio.run(handler(update, context))

    assert get_pending(uid) == {}


def test_menu_command_exit_clears_pending_admin_tool_test():
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
    uid = 983203
    message = FakeMessage()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=uid, first_name="Admin", username="admin"),
        effective_chat=SimpleNamespace(id=uid),
        effective_message=message,
        message=message,
    )
    context = SimpleNamespace(args=[], user_data={})
    pending, set_pending, get_pending, clear_pending = _pending_namespace()
    start_handler = _load_start_handler(source, pending, set_pending, get_pending, clear_pending)
    menu_handler = _load_menu_command(source, start_handler)
    set_pending(uid, "asr", "/tool_test_asr")

    asyncio.run(menu_handler(update, context))

    assert get_pending(uid) == {}


def test_start_and_menu_commands_clear_video_planning_text_pending_without_dropping_saved_plan():
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
    for command_name in ("cmd_start", "cmd_menu"):
        uid = 983204
        message = FakeMessage()
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=uid, first_name="User", username="user"),
            effective_chat=SimpleNamespace(id=uid),
            effective_message=message,
            message=message,
        )
        context, saved_plan_store = _planning_context(uid)
        pending, set_pending, get_pending, clear_pending = _pending_namespace()
        set_pending(uid, "asr", "/tool_test_asr")
        start_handler = _load_start_handler(source, pending, set_pending, get_pending, clear_pending)
        handler = start_handler if command_name == "cmd_start" else _load_menu_command(source, start_handler)

        _run_immediate(handler(update, context))

        assert "local_video_planning_pending_brief" not in context.user_data
        assert context.user_data["local_video_studio27b_public"] == saved_plan_store
        assert context.user_data["video_edit_sentinel"] == {"unchanged": True}
        assert get_pending(uid) == {}


def test_main_menu_callback_clears_video_planning_text_pending_without_dropping_saved_plan():
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
    uid = 983205
    emitted_home = _emitted_video_home_callback(source)
    pending, set_pending, get_pending, clear_pending = _pending_namespace()
    handler = _load_menu_handler(source, pending, set_pending, get_pending, clear_pending)
    context, saved_plan_store = _planning_context(uid)
    set_pending(uid, "asr", "/tool_test_asr")

    _run_immediate(
        handler(
            SimpleNamespace(callback_query=FakeQuery(uid, emitted_home)),
            context,
        )
    )

    assert "local_video_planning_pending_brief" not in context.user_data
    assert context.user_data["local_video_studio27b_public"] == saved_plan_store
    assert context.user_data["video_edit_sentinel"] == {"unchanged": True}
    assert get_pending(uid) == {}


def test_start_and_menu_commands_clear_finance_compliance_input_only_for_actor():
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
    for command_name in ("cmd_start", "cmd_menu"):
        uid, other_uid = 983206, 983299
        user_pending = {}
        pending, set_pending, get_pending, clear_pending = _pending_namespace()
        start_handler = _load_start_handler(source, pending, set_pending, get_pending, clear_pending)
        namespace = start_handler.__globals__
        _install_finance_compliance_pending(source, namespace, user_pending)
        namespace["set_finance_compliance_pending"](uid)
        namespace["set_finance_compliance_pending"](other_uid)

        message = FakeMessage()
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=uid, first_name="Admin", username="admin"),
            effective_chat=SimpleNamespace(id=uid),
            effective_message=message,
            message=message,
        )
        context = SimpleNamespace(args=[], user_data={})
        handler = start_handler if command_name == "cmd_start" else _load_menu_command(source, start_handler)

        _run_immediate(handler(update, context))

        assert namespace["get_finance_compliance_pending"](uid) is None
        assert namespace["get_finance_compliance_pending"](other_uid) is not None
        assert user_pending[namespace["finance_compliance_pending_key"](other_uid)]["pending_action"] == "finance_compliance_update"
