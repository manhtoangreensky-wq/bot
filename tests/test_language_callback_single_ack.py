import asyncio
import re
from pathlib import Path
from types import SimpleNamespace


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


class _Query:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(id=123, username="tester", first_name="Tester")
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _load_handler(side_effects, edits):
    match = re.search(
        r"(?ms)^async def handle_language_callback\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)",
        BOT_SOURCE,
    )
    assert match, "language callback handler is missing"

    async def _safe_edit(query, text, **kwargs):
        edits.append((query, text, kwargs))

    def _set_language(uid, lang):
        side_effects.append(("set_language", uid, lang))
        return lang

    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "asyncio": asyncio,
        "normalize_user_language": lambda value: value if value in {"vi", "en"} else None,
        "get_user_language": lambda _uid: "vi",
        "set_user_language": _set_language,
        "is_admin_user": lambda _uid: False,
        "user_selected_vietnamese_initially": lambda _uid: False,
        "enqueue_broadcast_first_start_safe": lambda _uid: None,
        "record_usage_event": lambda *args, **kwargs: side_effects.append(("usage", args, kwargs)),
        "localized_start_menu_text": lambda _uid, lang: f"main-{lang}",
        "localized_main_menu_keyboard": lambda _is_admin, lang: f"keyboard-{lang}",
        "safe_edit_query_message": _safe_edit,
    }
    exec(compile(match.group(0), "bot.py:handle_language_callback", "exec"), namespace)
    return namespace["handle_language_callback"]


def _registered_language_pattern():
    match = re.search(
        r"CallbackQueryHandler\(\s*handle_language_callback\s*,\s*pattern\s*=\s*r(['\"])(.*?)\1\s*\)",
        BOT_SOURCE,
    )
    assert match, "language callback handler is not registered"
    return re.compile(match.group(2))


def test_unsupported_two_letter_language_callback_gets_one_alert_ack():
    query = _Query("lang|xx")
    assert _registered_language_pattern().fullmatch(query.data)
    side_effects = []
    handler = _load_handler(side_effects, [])

    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [(("Language is not supported.",), {"show_alert": True})]
    assert side_effects == []


def test_supported_language_callback_keeps_one_ack_and_updates_menu():
    query = _Query("lang|vi")
    assert _registered_language_pattern().fullmatch(query.data)
    side_effects = []
    edits = []
    handler = _load_handler(side_effects, edits)

    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [((), {})]
    assert side_effects[0] == ("set_language", 123, "vi")
    assert edits == [(query, "main-vi", {"reply_markup": "keyboard-vi"})]
