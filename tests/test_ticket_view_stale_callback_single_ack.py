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


class _Button:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


def _load_handler(side_effects, edits):
    match = re.search(
        r"(?ms)^async def handle_ticket_callback\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)",
        BOT_SOURCE,
    )
    assert match, "ticket callback handler is missing"

    async def _safe_edit_or_send(query, text, **kwargs):
        edits.append((query, text, kwargs))

    async def _to_thread(function, *args, **kwargs):
        return function(*args, **kwargs)

    namespace = {
        "asyncio": SimpleNamespace(to_thread=_to_thread),
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "normalize_user_language": lambda value: value if value in {"vi", "en"} else None,
        "get_user_language": lambda _uid: "vi",
        "public_hub_copy": lambda _lang: {
            "support_ticket_admin_only": "Admin only",
            "support_ticket_not_found": "Ticket not found",
            "support_ticket_action_unsupported": "Action not supported",
            "support_my_tickets": "My tickets",
            "support_ticket": "Ticket",
            "main_menu": "Main",
        },
        "is_admin_user": lambda _uid: False,
        "clear_support_ticket_pending": lambda uid: side_effects.append(("clear_pending", uid)),
        "get_support_ticket": lambda ticket_id, uid=None: side_effects.append(("get_ticket", ticket_id, uid)) or None,
        "support_ticket_menu_text": lambda lang: f"tickets-{lang}",
        "support_ticket_menu_keyboard": lambda lang: f"tickets-keyboard-{lang}",
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "safe_edit_or_send": _safe_edit_or_send,
    }
    exec(compile(match.group(0), "bot.py:handle_ticket_callback", "exec"), namespace)
    return namespace["handle_ticket_callback"]


def _registered_ticket_pattern():
    match = re.search(
        r"CallbackQueryHandler\(\s*handle_ticket_callback\s*,\s*pattern\s*=\s*r(['\"])(.*?)\1\s*\)",
        BOT_SOURCE,
    )
    assert match, "ticket callback handler is not registered"
    return re.compile(match.group(2))


def test_stale_ticket_view_gets_one_not_found_alert_ack():
    query = _Query("ticket|pv|987654321")
    assert _registered_ticket_pattern().match(query.data)
    side_effects = []
    edits = []
    handler = _load_handler(side_effects, edits)

    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [((), {})], query.answers
    assert side_effects == [("clear_pending", 123), ("get_ticket", 987654321, 123)]
    assert len(edits) == 1
    assert edits[0][1] == "⚠️ Ticket not found"
    assert [button.callback_data for row in edits[0][2]["reply_markup"].inline_keyboard for button in row] == [
        "ticket|mine",
        "menu|main",
    ]


def test_malformed_ticket_view_gets_one_unsupported_alert_ack():
    query = _Query("ticket|pv|not-an-id")
    assert _registered_ticket_pattern().match(query.data)
    side_effects = []
    handler = _load_handler(side_effects, [])

    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [(("Action not supported",), {"show_alert": True})]
    assert side_effects == []


def test_ticket_start_keeps_one_ack_and_existing_screen():
    query = _Query("ticket|start")
    assert _registered_ticket_pattern().match(query.data)
    side_effects = []
    edits = []
    handler = _load_handler(side_effects, edits)

    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [((), {})]
    assert side_effects == [("clear_pending", 123)]
    assert edits == [(query, "tickets-vi", {"reply_markup": "tickets-keyboard-vi"})]
