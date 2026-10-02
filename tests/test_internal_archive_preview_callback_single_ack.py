import asyncio
import re
from pathlib import Path
from types import SimpleNamespace


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


class _Query:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(id=123, username="admin", first_name="Admin")
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _load_handler(state, edits):
    match = re.search(
        r"(?ms)^async def handle_internal_archive_callback\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)",
        BOT_SOURCE,
    )
    assert match, "internal-archive callback handler is missing"

    async def _safe_edit(query, text, **kwargs):
        edits.append((query, text, kwargs))

    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "is_admin_user": lambda _uid: True,
        "clear_internal_archive_pending": lambda _uid: None,
        "clear_doc_tool_pending": lambda _uid: None,
        "clear_media_creator_pending_states": lambda _uid: None,
        "get_internal_archive_pending": lambda _uid: state,
        "internal_archive_menu_text": lambda: "archive-menu",
        "internal_archive_menu_keyboard": lambda: "archive-keyboard",
        "safe_edit_query_message": _safe_edit,
    }
    exec(compile(match.group(0), "bot.py:handle_internal_archive_callback", "exec"), namespace)
    return namespace["handle_internal_archive_callback"]


def _registered_archive_pattern():
    match = re.search(
        r"CallbackQueryHandler\(\s*handle_internal_archive_callback\s*,\s*pattern\s*=\s*r(['\"])(.*?)\1\s*\)",
        BOT_SOURCE,
    )
    assert match, "internal-archive callback handler is not registered"
    return re.compile(match.group(2))


def test_stale_preview_without_file_gets_one_alert_ack():
    query = _Query("archive|preview")
    assert _registered_archive_pattern().match(query.data)
    edits = []
    handler = _load_handler({}, edits)

    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [(("Chưa có hồ sơ chờ lưu.",), {"show_alert": True})], query.answers
    assert edits == []


def test_archive_root_keeps_one_ack_and_existing_menu():
    query = _Query("archive|root")
    assert _registered_archive_pattern().match(query.data)
    edits = []
    handler = _load_handler({}, edits)

    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [((), {})]
    assert edits == [(query, "archive-menu", {"reply_markup": "archive-keyboard"})]
