import re
from pathlib import Path
from types import SimpleNamespace


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def _run_inert(coroutine):
    try:
        yielded = coroutine.send(None)
    except StopIteration as completed:
        return completed.value
    coroutine.close()
    raise AssertionError(f"No-I/O handler unexpectedly yielded: {yielded!r}")


class _Query:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(id=123, username="admin", first_name="Admin")
        self.answers = []
        self.messages = []
        self.message = SimpleNamespace(reply_text=self._reply_text)

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def _reply_text(self, text):
        self.messages.append(text)


class _Button:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


def _emitted_admin_status_callbacks(ticket_id, source="new", list_offset=0):
    match = re.search(
        r"(?ms)^def support_ticket_admin_keyboard\(.*?(?=^def\s|^class\s|\Z)",
        BOT_SOURCE,
    )
    assert match, "Admin Ticket detail keyboard builder is missing"
    namespace = {
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
    }
    exec(compile(match.group(0), "bot.py:support_ticket_admin_keyboard", "exec"), namespace)
    markup = namespace["support_ticket_admin_keyboard"](
        {"id": ticket_id},
        source=source,
        list_offset=list_offset,
    )
    return {
        button.text: button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data and button.callback_data.startswith(f"ticket|st|{ticket_id}|")
    }


def _emitted_admin_status_callback(ticket_id):
    return _emitted_admin_status_callbacks(ticket_id)["✅ Đã xử lý"]


def _load_handler(side_effects, edits, ticket=None, query=None, read_trace=None):
    match = re.search(
        r"(?ms)^async def handle_ticket_callback\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)",
        BOT_SOURCE,
    )
    assert match, "ticket callback handler is missing"

    async def _safe_edit_or_send(query, text, **kwargs):
        edits.append((query, text, kwargs))

    async def _read_only_thread(helper, *args, **kwargs):
        return helper(*args, **kwargs)

    def _get_ticket(ticket_id, uid=None):
        side_effects.append(("get_ticket", ticket_id, uid))
        if query is not None and read_trace is not None:
            read_trace.append(("ticket", len(query.answers)))
        if ticket is not None and int(ticket_id) == int(ticket["id"]):
            return dict(ticket)
        return None

    def _update_ticket(ticket_id, **kwargs):
        side_effects.append(("update_ticket", ticket_id, kwargs))
        if ticket is not None and int(ticket_id) == int(ticket["id"]):
            ticket.update(kwargs)
            return dict(ticket)
        return None

    def _get_user_language(_uid):
        if query is not None and read_trace is not None:
            read_trace.append(("language", len(query.answers)))
        return "vi"

    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "asyncio": SimpleNamespace(to_thread=_read_only_thread),
        "normalize_user_language": lambda value: value if value in {"vi", "en"} else None,
        "get_user_language": _get_user_language,
        "public_hub_copy": lambda _lang: {
            "support_ticket_admin_only": "Admin only",
            "support_ticket_not_found": "Ticket not found",
            "support_ticket_action_unsupported": "Action not supported",
            "main_menu": "Main menu",
        },
        "is_admin_user": lambda _uid: True,
        "clear_support_ticket_pending": lambda uid: side_effects.append(("clear_pending", uid)),
        "get_support_ticket": _get_ticket,
        "update_support_ticket": _update_ticket,
        "support_ticket_menu_text": lambda lang: f"tickets-{lang}",
        "support_ticket_menu_keyboard": lambda lang: f"tickets-keyboard-{lang}",
        "support_ticket_admin_text": lambda _ticket: "ticket-detail",
        "support_ticket_admin_keyboard": lambda *_args: "ticket-keyboard",
        "support_admin_menu_keyboard": lambda *_args: "admin-keyboard",
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


def test_stale_admin_status_acks_once_and_recovers_to_same_list_page():
    query = _Query(_emitted_admin_status_callbacks(987654321, "high", 6)["✅ Đã xử lý"])
    assert query.data == "ticket|st|987654321|resolved|high|6", query.data
    assert _registered_ticket_pattern().match(query.data)
    side_effects = []
    edits = []
    read_trace = []
    handler = _load_handler(side_effects, edits, query=query, read_trace=read_trace)

    _run_inert(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [((), {})], query.answers
    assert side_effects == [("get_ticket", 987654321, None)], side_effects
    assert read_trace == [("language", 1), ("ticket", 1)], read_trace
    assert len(edits) == 1 and "Ticket not found" in edits[0][1], edits
    markup = edits[0][2]["reply_markup"]
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert callbacks == ["ticket|al|high|6", "menu|main"], callbacks


def test_malformed_admin_status_gets_one_unsupported_alert_without_lookup():
    query = _Query("ticket|st|not-an-id|resolved")
    assert _registered_ticket_pattern().match(query.data)
    side_effects = []
    handler = _load_handler(side_effects, [])

    _run_inert(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [(("Action not supported",), {"show_alert": True})]
    assert side_effects == []


def test_unknown_admin_status_gets_one_unsupported_alert_before_ticket_lookup():
    emitted = _emitted_admin_status_callback(987654321)
    assert emitted == "ticket|st|987654321|resolved|new|0"
    invalid = emitted.replace("|resolved|", "|not_a_status|")
    assert invalid == "ticket|st|987654321|not_a_status|new|0"
    assert _registered_ticket_pattern().match(invalid)

    ticket = {"id": 987654321, "status": "new"}
    query = _Query(invalid)
    side_effects = []
    edits = []
    handler = _load_handler(side_effects, edits, ticket=ticket)

    _run_inert(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert side_effects == [], side_effects
    assert query.answers == [(("Action not supported",), {"show_alert": True})], query.answers
    assert edits == [], edits
    assert ticket["status"] == "new", ticket


def test_all_emitted_admin_statuses_remain_accepted():
    expected = {
        "✅ Đã xử lý": ("resolved", False),
        "💰 Đánh dấu refund": ("refund_pending", True),
        "⏳ Chờ provider": ("waiting_provider", False),
    }
    emitted = _emitted_admin_status_callbacks(987654321)
    assert set(emitted) == set(expected), emitted

    for label, (status, sends_notice) in expected.items():
        ticket = {"id": 987654321, "status": "new"}
        side_effects = []
        edits = []
        query = _Query(emitted[label])
        assert _registered_ticket_pattern().match(query.data)
        handler = _load_handler(side_effects, edits, ticket=ticket)

        _run_inert(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

        assert query.answers == [((), {})], (label, query.answers)
        assert side_effects == [
            ("get_ticket", 987654321, None),
            ("update_ticket", 987654321, {"status": status}),
        ], (label, side_effects)
        assert ticket["status"] == status, (label, ticket)
        assert edits == [(query, "ticket-detail", {"reply_markup": "ticket-keyboard"})]
        if sends_notice:
            assert query.messages == [
                "💰 Ticket đã được đánh dấu cần kiểm tra hoàn Xu/refund. Thao tác này chưa cộng hoặc trừ Xu."
            ]
        else:
            assert query.messages == []


def test_valid_admin_status_acks_before_language_and_ticket_reads():
    query = _Query(_emitted_admin_status_callback(987654321))
    ticket = {"id": 987654321, "status": "new"}
    side_effects = []
    edits = []
    read_trace = []
    handler = _load_handler(side_effects, edits, ticket=ticket, query=query, read_trace=read_trace)

    _run_inert(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert read_trace == [("language", 1), ("ticket", 1)], read_trace
    assert query.answers == [((), {})], query.answers


def test_ticket_start_keeps_one_ack_and_existing_admin_screen():
    query = _Query("ticket|start")
    assert _registered_ticket_pattern().match(query.data)
    side_effects = []
    edits = []
    handler = _load_handler(side_effects, edits)

    _run_inert(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [((), {})]
    assert side_effects == [("clear_pending", 123)]
    assert edits == [(query, "tickets-vi", {"reply_markup": "tickets-keyboard-vi"})]
