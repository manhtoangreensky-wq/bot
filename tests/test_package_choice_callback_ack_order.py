import re
from pathlib import Path
from types import SimpleNamespace


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


class _StopAfterLanguageLookup(Exception):
    pass


class _Query:
    def __init__(self, data, events, user_id=123):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id, first_name="Fixture")
        self.events = events
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.events.append("ack")
        self.answers.append((args, kwargs))


class _Button:
    def __init__(self, text, callback_data=None, **_kwargs):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


def _source_function(name):
    starts = (
        BOT_SOURCE.find(f"\nasync def {name}(") + 1,
        BOT_SOURCE.find(f"\ndef {name}(") + 1,
    )
    start = next((position for position in starts if position > 0), -1)
    assert start >= 0, f"production function {name} is missing"
    body_lines = BOT_SOURCE[start:].splitlines(keepends=True)
    body = [body_lines[0]]
    for line in body_lines[1:]:
        if line.startswith(("async def ", "def ", "class ")):
            break
        body.append(line)
    return "".join(body)


def _registered_package_choice_route(events, language_lookup=None):
    if language_lookup is None:
        language_lookup = lambda _uid: (_ for _ in ()).throw(_StopAfterLanguageLookup())
    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "expire_old_payos_orders": lambda: events.append("expire"),
        "get_user_language": language_lookup,
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "public_pricing_locale": lambda _lang: "vi",
        "ui_text": lambda _lang, _key: "Main menu",
        "public_copy_locale": lambda _lang: "vi",
        "public_hub_copy": lambda _locale: {"common_failed": "Request failed"},
        "public_account_flow_copy": lambda _locale: {},
        "public_topup_deep_copy": lambda _lang: {},
    }
    for name in (
        "payos_package_callback_data",
        "manual_package_callback_data",
        "main_topup_keyboard",
        "handle_package_choice",
    ):
        exec(compile(_source_function(name), f"bot.py:{name}", "exec"), namespace)

    registrations = []
    namespace.update(
        tg_app=SimpleNamespace(add_handler=registrations.append),
        CallbackQueryHandler=lambda callback, pattern: SimpleNamespace(
            callback=callback,
            pattern=re.compile(pattern),
        ),
    )
    registration = next(
        line.strip()
        for line in BOT_SOURCE.splitlines()
        if "tg_app.add_handler(CallbackQueryHandler(handle_package_choice," in line
    )
    exec(registration, namespace)

    keyboard = namespace["main_topup_keyboard"]("vi", 123)
    emitted = [
        button for row in keyboard.inline_keyboard for button in row
        if button.callback_data.startswith("payos_pkg|")
    ]
    assert [button.callback_data for button in emitted] == [
        "payos_pkg|10k|123", "payos_pkg|20k|123", "payos_pkg|50k|123",
        "payos_pkg|100k|123", "payos_pkg|200k|123", "payos_pkg|500k|123",
    ]
    return emitted, registrations, namespace


def _run_no_io(awaitable):
    try:
        awaitable.send(None)
    except StopIteration as completed:
        return completed.value
    raise AssertionError("fixture callback unexpectedly yielded I/O")


def test_every_emitted_package_choice_acknowledges_before_expiring_old_orders():
    events = []
    emitted, registrations, namespace = _registered_package_choice_route(events)
    for button in emitted:
        callback_data = button.callback_data
        package_key = callback_data.split("|")[1]
        assert callback_data == namespace["payos_package_callback_data"](package_key, 123)
        route = next(handler for handler in registrations if handler.pattern.match(callback_data))
        assert route.callback is namespace["handle_package_choice"]
        query = _Query(callback_data, events)
        update = SimpleNamespace(callback_query=query)

        try:
            _run_no_io(route.callback(update, SimpleNamespace()))
        except _StopAfterLanguageLookup:
            pass
        else:
            raise AssertionError("fixture should stop before any package or payment work")

        assert events[-2:] == ["ack", "expire"], (callback_data, events)
        assert events.count("ack") == events.count("expire"), (callback_data, events)


def test_foreign_owner_denial_uses_one_alert_and_keeps_expiry_after_ack():
    events = []
    emitted, registrations, namespace = _registered_package_choice_route(
        events,
        language_lookup=lambda _uid: "vi",
    )
    callback_data = emitted[0].callback_data
    route = next(handler for handler in registrations if handler.pattern.match(callback_data))
    query = _Query(callback_data, events, user_id=456)

    _run_no_io(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [
        (("⚠️ Không phải yêu cầu của bạn!",), {"show_alert": True})
    ]
    assert events == ["ack", "expire"]
    assert route.callback is namespace["handle_package_choice"]


def test_foreign_owner_denial_uses_clicking_users_locale():
    events = []
    language_reads = []

    def language_lookup(user_id):
        language_reads.append(user_id)
        return {123: "vi", 456: "en"}.get(user_id)

    emitted, registrations, namespace = _registered_package_choice_route(
        events,
        language_lookup=language_lookup,
    )
    namespace["public_copy_locale"] = lambda lang: "en" if lang == "en" else "vi"
    namespace["public_hub_copy"] = lambda locale: {"common_failed": f"localized-{locale}"}
    callback_data = emitted[0].callback_data
    route = next(handler for handler in registrations if handler.pattern.match(callback_data))
    query = _Query(callback_data, events, user_id=456)

    _run_no_io(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert language_reads == [456], "denial copy must follow the user who pressed the button"
    assert query.answers == [(("⚠️ localized-en",), {"show_alert": True})]
    assert events == ["ack", "expire"]


def test_malformed_package_choice_keeps_single_ack_before_expiry():
    events = []
    _emitted, registrations, namespace = _registered_package_choice_route(events)
    route = next(
        handler for handler in registrations
        if handler.pattern.match("payos_pkg|malformed")
    )
    query = _Query("payos_pkg|malformed", events)

    _run_no_io(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [((), {})]
    assert events == ["ack", "expire"]


def test_malformed_package_owner_id_is_rejected_once_without_raising():
    events = []
    emitted, registrations, namespace = _registered_package_choice_route(events)
    callback_data = emitted[0].callback_data.rsplit("|", 1)[0] + "|not-a-user-id"
    route = next(handler for handler in registrations if handler.pattern.match(callback_data))
    query = _Query(callback_data, events)

    caught = None
    try:
        _run_no_io(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    except Exception as exc:
        caught = exc

    assert caught is None, f"malformed package callback raised {type(caught).__name__}"
    assert query.answers == [
        (("⚠️ Nút nạp đã hết phiên. Vui lòng mở lại bảng nạp.",), {"show_alert": True})
    ]
    assert events == ["ack", "expire"]
    assert route.callback is namespace["handle_package_choice"]
