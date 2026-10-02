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


def _load_handler(side_effects, edits):
    match = re.search(
        r"(?ms)^async def handle_ticket_callback\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)",
        BOT_SOURCE,
    )
    assert match, "ticket callback handler is missing"

    async def _safe_edit_or_send(query, text, **kwargs):
        edits.append((query, text, kwargs))

    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "normalize_user_language": lambda value: value if value in {"vi", "en"} else None,
        "get_user_language": lambda _uid: "vi",
        "public_hub_copy": lambda _lang: {
            "support_ticket_admin_only": "Admin only",
            "support_ticket_not_found": "Ticket not found",
            "support_ticket_action_unsupported": "Action not supported",
        },
        "is_admin_user": lambda _uid: True,
        "clear_support_ticket_pending": lambda uid: side_effects.append(("clear_pending", uid)),
        "get_support_ticket": lambda ticket_id, uid=None: side_effects.append(("get_ticket", ticket_id, uid)) or None,
        "support_ticket_menu_text": lambda lang: f"tickets-{lang}",
        "support_ticket_menu_keyboard": lambda lang: f"tickets-keyboard-{lang}",
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


def test_stale_admin_ticket_detail_gets_one_not_found_alert_ack():
    query = _Query("ticket|av|987654321")
    assert _registered_ticket_pattern().match(query.data)
    side_effects = []
    handler = _load_handler(side_effects, [])

    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [(("Không tìm thấy ticket.",), {"show_alert": True})], query.answers
    assert side_effects == [("clear_pending", 123), ("get_ticket", 987654321, None)]


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
