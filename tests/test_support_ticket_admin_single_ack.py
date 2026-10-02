import asyncio
import ast
from pathlib import Path
from types import SimpleNamespace


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


class _Query:
    def __init__(self, user_id, data):
        self.from_user = SimpleNamespace(id=user_id)
        self.data = data
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, *args, **kwargs):
        self.edits.append((args, kwargs))


def _load_handler(is_admin):
    tree = ast.parse(BOT_SOURCE)
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.AsyncFunctionDef)
        and item.name == "handle_ticket_callback"
    )
    lines = BOT_SOURCE.splitlines(True)
    function_source = "".join(lines[node.lineno - 1 : node.end_lineno])
    async def _safe_edit_or_send(*_args, **_kwargs):
        return None

    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "is_admin_user": is_admin,
        "get_user_language": lambda _uid: "vi",
        "normalize_user_language": lambda value: value,
        "public_hub_copy": lambda _lang: {
            "support_ticket_admin_only": "Chỉ dành cho admin."
        },
        "clear_support_ticket_pending": lambda _uid: None,
        "support_ticket_menu_text": lambda _lang: "ticket-menu",
        "support_ticket_menu_keyboard": lambda _lang: "ticket-keyboard",
        "safe_edit_or_send": _safe_edit_or_send,
    }
    exec(compile(function_source, "bot.py:handle_ticket_callback", "exec"), namespace)
    return namespace["handle_ticket_callback"]


def test_public_admin_ticket_action_is_blocked_with_one_alert_ack():
    assert 'CallbackQueryHandler(handle_ticket_callback, pattern=r"^ticket\\|")' in BOT_SOURCE
    handler = _load_handler(lambda _user_id: False)
    query = _Query(123, "ticket|ask|1")

    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [
        (("Chỉ dành cho admin.",), {"show_alert": True})
    ]
    assert query.edits == []


def test_admin_ticket_non_send_action_keeps_one_normal_ack():
    handler = _load_handler(lambda _user_id: True)
    query = _Query(999, "ticket|start")

    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [((), {})]

