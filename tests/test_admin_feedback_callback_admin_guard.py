import asyncio
from pathlib import Path
from types import SimpleNamespace


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


class _Query:
    def __init__(self, user_id):
        self.data = "admin_gopy|inbox"
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace(chat_id=user_id)
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _load_handler(is_admin, calls):
    start = BOT_SOURCE.index("async def handle_admin_gopy_callback(")
    end = BOT_SOURCE.index("\n\n# ==============================================================================", start)
    async def _cmd_admin_gopy(update, context):
        calls.append((update, context))

    namespace = {
        "SimpleNamespace": SimpleNamespace,
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "is_admin_user": is_admin,
        "cmd_admin_gopy": _cmd_admin_gopy,
    }
    exec(compile(BOT_SOURCE[start:end], "bot.py:handle_admin_gopy_callback", "exec"), namespace)
    return namespace["handle_admin_gopy_callback"]


def test_admin_feedback_callback_is_registered_and_public_is_blocked():
    assert 'CallbackQueryHandler(handle_admin_gopy_callback, pattern=r"^admin_gopy\\|")' in BOT_SOURCE

    calls = []
    handler = _load_handler(lambda user_id: user_id == 999, calls)
    query = _Query(123)

    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [(("⛔ Khu vực này chỉ dành cho Admin.",), {"show_alert": True})]
    assert calls == []


def test_admin_feedback_callback_keeps_admin_inbox_route():
    calls = []
    handler = _load_handler(lambda user_id: user_id == 999, calls)
    query = _Query(999)

    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [((), {})]
    assert len(calls) == 1
    assert calls[0][0].effective_user.id == 999
    assert calls[0][0].message is query.message
