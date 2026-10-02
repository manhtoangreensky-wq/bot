import asyncio
import re
from pathlib import Path
from types import SimpleNamespace


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


class _Query:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(id=123, username="customer", first_name="Customer")
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _registered_menu_pattern():
    match = re.search(
        r"CallbackQueryHandler\(\s*handle_menu_callback\s*,\s*pattern\s*=\s*r(['\"])(.*?)\1\s*\)",
        BOT_SOURCE,
    )
    assert match, "main menu callback handler is not registered"
    return re.compile(match.group(2))


def _load_menu_handler(clear_calls):
    match = re.search(
        r"(?ms)^async def handle_menu_callback\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)",
        BOT_SOURCE,
    )
    assert match, "main menu callback handler is missing"

    def _record(name):
        return lambda *args, **kwargs: clear_calls.append((name, args, kwargs))

    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "is_admin_user": lambda user_id: False,
        "VIDEO_TAIL9_TEXT_INPUT_KEY": "video_tail9_text_input",
        "get_user_language": lambda _user_id: "vi",
        "clear_translation_menu_pending": _record("translation_menu"),
        "clear_translation_session": _record("translation_session"),
        "clear_media_creator_pending_states": _record("media_creator"),
        "clear_support_ticket_pending": _record("support_ticket"),
        "clear_finance_compliance_pending": _record("finance_compliance"),
        "clear_internal_archive_pending": _record("internal_archive"),
        "clear_doc_tool_pending": _record("doc_tool"),
        "clear_storage_addon_pending": _record("storage_addon"),
        "clear_memory_guided_pending": _record("memory_guided"),
        "clear_music_guided_pending": _record("music_guided"),
        "clear_pending_admin_tool_test": _record("admin_tool_test"),
        "DOC_TOOL_MENU_ACTIONS": set(),
    }
    exec(compile(match.group(0), "bot.py:handle_menu_callback", "exec"), namespace)
    return namespace["handle_menu_callback"]


def test_public_user_denied_menu_gets_one_alert_without_clearing_pending_state():
    cases = (
        ("menu|admin", "Khu vực này chỉ dành cho Admin."),
        ("menu|finance", "Khu vực này chỉ dành cho Admin."),
        ("menu|hint_operator", "Lệnh nội bộ chỉ dành cho Admin."),
    )
    for callback_data, denial_message in cases:
        query = _Query(callback_data)
        assert _registered_menu_pattern().match(query.data)
        clear_calls = []
        handler = _load_menu_handler(clear_calls)

        asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace(user_data={})))

        assert query.answers == [((denial_message,), {"show_alert": True})], (callback_data, query.answers)
        assert clear_calls == [], (callback_data, clear_calls)
