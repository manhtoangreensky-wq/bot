import html
import re
from pathlib import Path
from types import SimpleNamespace


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
EXPECTED_QUERIES = {
    "sales": "upbeat product review",
    "tech": "futuristic technology background",
    "cinematic": "cinematic trailer hit",
    "review": "light inspiring review background",
    "trend": "upbeat energetic short video",
}


class _Button:
    def __init__(self, text, callback_data=None, **_kwargs):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class _Query:
    def __init__(self, data, events):
        self.data = data
        self.events = events
        self.answers = []
        self.message = _Message(events)

    async def answer(self, *args, **kwargs):
        self.events.append("ack")
        self.answers.append((args, kwargs))


class _Message:
    def __init__(self, events):
        self.events = events
        self.sent = []

    async def reply_text(self, text, **kwargs):
        self.events.append("reply_text")
        self.sent.append((text, kwargs))


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


def _run_no_io(awaitable):
    try:
        awaitable.send(None)
    except StopIteration as completed:
        return completed.value
    raise AssertionError("fixture callback unexpectedly yielded external I/O")


def _registered_route():
    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "SUGGEST_MUSIC_PRESET_QUERIES": EXPECTED_QUERIES,
        "html": html,
    }
    for name in ("suggest_music_style_keyboard", "handle_suggest_music_callback"):
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
        if "tg_app.add_handler(CallbackQueryHandler(handle_suggest_music_callback," in line
    )
    exec(registration, namespace)
    return namespace, registrations


def test_emitted_suggest_music_styles_reach_registered_read_only_recommendation_route():
    namespace, registrations = _registered_route()
    keyboard = namespace["suggest_music_style_keyboard"]()
    emitted = [button for row in keyboard.inline_keyboard for button in row]
    assert {button.callback_data for button in emitted} == {
        f"suggest_music|{preset}" for preset in EXPECTED_QUERIES
    }

    for button in emitted:
        route = next(
            handler for handler in registrations if handler.pattern.match(button.callback_data)
        )
        assert route.callback is namespace["handle_suggest_music_callback"]
        events = []
        query = _Query(button.callback_data, events)
        _run_no_io(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

        keyword = EXPECTED_QUERIES[button.callback_data.split("|", 1)[1]]
        assert query.answers == [((), {})]
        assert events == ["ack", "reply_text"]
        assert len(query.message.sent) == 1
        text, kwargs = query.message.sent[0]
        assert f"<code>{html.escape(keyword)}</code>" in text
        assert f"/music_library {html.escape(keyword)}" in text
        assert "Bot chưa trừ Xu." in text
        assert kwargs == {"parse_mode": "HTML"}


def test_unknown_suggest_music_style_falls_back_to_safe_static_recommendation():
    namespace, registrations = _registered_route()
    route = next(handler for handler in registrations if handler.pattern.match("suggest_music|unknown"))
    events = []
    query = _Query("suggest_music|unknown", events)
    _run_no_io(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [((), {})]
    assert events == ["ack", "reply_text"]
    assert "upbeat product review" in query.message.sent[0][0]
