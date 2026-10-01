import asyncio
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


def _load_menu_handler(source, pending, set_pending, get_pending, clear_pending):
    start = source.index("async def handle_menu_callback(")
    end = source.index("\nasync def handle_free_hub_callback(", start)
    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
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
