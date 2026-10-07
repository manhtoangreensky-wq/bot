import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


class _Query:
    def __init__(self, user_id, data):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _load_handler(cleared, edits):
    tree = ast.parse(BOT_SOURCE)
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.AsyncFunctionDef)
        and item.name == "handle_human_support_callback"
    )
    function_source = "\n".join(BOT_SOURCE.splitlines()[node.lineno - 1 : node.end_lineno])

    async def _safe_edit_or_send(query, text, **kwargs):
        edits.append((query, text, kwargs))

    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "normalize_user_language": lambda value: value,
        "get_user_language": lambda _uid: "vi",
        "clear_support_ticket_pending": lambda uid: cleared.append(uid),
        "safe_edit_or_send": _safe_edit_or_send,
        "human_support_text": lambda _lang: "support-main",
        "human_support_keyboard": lambda _lang: "support-keyboard",
    }
    helper = next(item for item in tree.body if isinstance(item, ast.FunctionDef)
                  and item.name == "support_read_origin_keyboard")
    helper_source = "\n".join(BOT_SOURCE.splitlines()[helper.lineno - 1:helper.end_lineno])
    exec(compile(helper_source, "bot.py:support_read_origin_keyboard", "exec"), namespace)
    form_helper = next(item for item in tree.body if isinstance(item, ast.FunctionDef)
                       and item.name == "support_form_origin_keyboard")
    form_source = "\n".join(BOT_SOURCE.splitlines()[form_helper.lineno - 1:form_helper.end_lineno])
    exec(compile(form_source, "bot.py:support_form_origin_keyboard", "exec"), namespace)
    exec(compile(function_source, "bot.py:handle_human_support_callback", "exec"), namespace)
    return namespace["handle_human_support_callback"]


def test_unknown_support_callback_shows_one_alert_ack():
    cleared = []
    edits = []
    query = _Query(123, "support|removed_action")
    handler = _load_handler(cleared, edits)

    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [
        (("Thao tác hỗ trợ chưa được hỗ trợ.",), {"show_alert": True})
    ]
    assert edits == []
    assert cleared == []


def test_missing_support_action_argument_shows_one_alert_ack():
    query = _Query(123, "support|premium_type")
    handler = _load_handler([], [])

    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [
        (("Thao tác hỗ trợ chưa được hỗ trợ.",), {"show_alert": True})
    ]


def test_support_start_route_keeps_normal_ack_and_returns_main_screen():
    assert 'CallbackQueryHandler(handle_human_support_callback, pattern=r"^support\\|")' in BOT_SOURCE
    cleared = []
    edits = []
    query = _Query(123, "support|start")
    handler = _load_handler(cleared, edits)

    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [((), {})]
    assert cleared == [123]
    assert edits == [(query, "support-main", {"reply_markup": "support-keyboard"})]
