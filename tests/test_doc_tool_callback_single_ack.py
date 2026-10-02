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


def _load_handler(state, edits):
    match = re.search(
        r"(?ms)^async def handle_doc_tool_callback\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)",
        BOT_SOURCE,
    )
    assert match, "document-tool callback handler is missing"

    async def _safe_edit_or_send(query, text, **kwargs):
        edits.append((query, text, kwargs))

    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "get_user_language": lambda _uid: "vi",
        "get_doc_tool_pending": lambda _uid: state,
        "doc_tool_config": lambda _tool: {"min_files": 2},
        "doc_tool_start_text": lambda tool, lang: f"start-{tool}-{lang}",
        "doc_tool_start_keyboard": lambda tool, lang, _state: f"keyboard-{tool}-{lang}",
        "safe_edit_or_send": _safe_edit_or_send,
        "is_admin_user": lambda _uid: False,
        "localized_start_menu_text": lambda _uid, lang: f"main-{lang}",
        "localized_main_menu_keyboard": lambda _is_admin, lang: f"main-keyboard-{lang}",
    }
    exec(compile(match.group(0), "bot.py:handle_doc_tool_callback", "exec"), namespace)
    return namespace["handle_doc_tool_callback"]


def _registered_doc_tool_pattern():
    match = re.search(
        r"CallbackQueryHandler\(\s*handle_doc_tool_callback\s*,\s*pattern\s*=\s*r(['\"])(.*?)\1\s*\)",
        BOT_SOURCE,
    )
    assert match, "document-tool callback handler is not registered"
    return re.compile(match.group(2))


def test_confirm_with_too_few_files_gets_one_alert_ack():
    query = _Query("docflow|confirm")
    assert _registered_doc_tool_pattern().match(query.data)
    state = {"doc_tool_current": "merge_pdf", "doc_tool_files": ["file-1"]}
    edits = []
    handler = _load_handler(state, edits)

    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [(("Chưa đủ file để xử lý.",), {"show_alert": True})], query.answers
    assert edits == []


def test_send_more_keeps_one_ack_and_existing_document_screen():
    query = _Query("docflow|send_more")
    assert _registered_doc_tool_pattern().match(query.data)
    state = {"doc_tool_current": "merge_pdf", "doc_tool_files": ["file-1"]}
    edits = []
    handler = _load_handler(state, edits)

    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [((), {})]
    assert edits == [(query, "start-merge_pdf-vi", {"parse_mode": "HTML", "reply_markup": "keyboard-merge_pdf-vi"})]
