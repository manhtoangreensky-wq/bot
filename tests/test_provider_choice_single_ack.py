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


def _load_handler(user_pending):
    tree = ast.parse(BOT_SOURCE)
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.AsyncFunctionDef)
        and item.name == "handle_provider_choice"
    )
    lines = BOT_SOURCE.splitlines(True)
    function_source = "".join(lines[node.lineno - 1 : node.end_lineno])
    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "USER_PENDING": user_pending,
        "refund_charged_credit": lambda *args, **kwargs: None,
    }
    exec(compile(function_source, "bot.py:handle_provider_choice", "exec"), namespace)
    return namespace["handle_provider_choice"]


def test_provider_choice_rejects_other_user_with_one_alert_ack():
    handler = _load_handler({})
    query = _Query(2, "prov|voice|paid|1")

    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [
        (("⚠️ Không phải yêu cầu của bạn!",), {"show_alert": True})
    ]
    assert query.edits == []


def test_provider_choice_owner_keeps_one_ack_on_expired_request():
    handler = _load_handler({})
    query = _Query(1, "prov|voice|paid|1")

    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [((), {})]
    assert query.edits == [(("⏰ Yêu cầu đã hết hạn hoặc đã xử lý.",), {})]

