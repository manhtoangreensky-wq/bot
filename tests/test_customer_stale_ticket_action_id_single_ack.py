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


def _run_no_io(coroutine):
    try:
        return coroutine.send(None)
    except StopIteration as result:
        return result.value
    finally:
        coroutine.close()


def _load_handler():
    match = re.search(
        r"(?ms)^async def handle_ticket_callback\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)",
        BOT_SOURCE,
    )
    assert match, "ticket callback handler is missing"

    async def _safe_edit_or_send(*_args, **_kwargs):
        return None

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
        "is_admin_user": lambda _uid: False,
        "clear_support_ticket_pending": lambda _uid: None,
        "get_support_ticket": lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("invalid customer action ID must be rejected before lookup")
        ),
        "update_support_ticket": lambda *_args, **_kwargs: None,
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


def test_out_of_range_customer_ticket_actions_get_one_alert_before_lookup():
    handler = _load_handler()
    for action in ("reply_user", "attach", "done"):
        query = _Query(f"ticket|{action}|9223372036854775808")
        assert _registered_ticket_pattern().match(query.data)

        _run_no_io(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

        assert query.answers == [(("Action not supported",), {"show_alert": True})], action


def test_non_numeric_customer_ticket_action_gets_one_alert_before_lookup():
    handler = _load_handler()
    for action in ("reply_user", "attach", "done"):
        query = _Query(f"ticket|{action}|stale")
        assert _registered_ticket_pattern().match(query.data)

        _run_no_io(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

        assert query.answers == [(("Action not supported",), {"show_alert": True})], action
