import asyncio
import html
import re
import unittest
from pathlib import Path
from types import SimpleNamespace


BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"
BOT_SOURCE = BOT_PATH.read_text(encoding="utf-8")


def _function_source(name):
    start = re.search(rf"(?m)^(?:async\s+)?def {re.escape(name)}\s*\(", BOT_SOURCE)
    assert start is not None, f"missing source function: {name}"
    boundary = re.search(
        r"(?m)^(?:async\s+)?def\s+\w+\s*\(|^class\s+\w+|^[A-Z][A-Z0-9_]*\s*=",
        BOT_SOURCE[start.end():],
    )
    end = start.end() + boundary.start() if boundary else len(BOT_SOURCE)
    return BOT_SOURCE[start.start():end].rstrip()


class _Button:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class _Message:
    def __init__(self):
        self.replies = []
        self.edits = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))
        return self

    async def edit_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class _Query:
    def __init__(self, user_id, data):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class _CapturedCallbackQueryHandler:
    def __init__(self, callback, pattern):
        self.callback = callback
        self.pattern = pattern


class _Application:
    def __init__(self):
        self.handlers = []

    def add_handler(self, handler):
        self.handlers.append(handler)


def _load_functions(*names, **dependencies):
    namespace = {
        "SimpleNamespace": SimpleNamespace,
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "html": html,
        "re": re,
        **dependencies,
    }
    source = "from __future__ import annotations\n\n" + "\n\n".join(
        _function_source(name) for name in names
    )
    exec(compile(source, str(BOT_PATH), "exec"), namespace)
    return namespace


def _registered_trend_route(handler):
    matches = [
        line.strip()
        for line in BOT_SOURCE.splitlines()
        if "tg_app.add_handler(CallbackQueryHandler(handle_trend_callback," in line
    ]
    assert len(matches) == 1, f"expected one trend lifecycle registration, got {len(matches)}"
    app = _Application()
    exec(
        matches[0],
        {
            "tg_app": app,
            "CallbackQueryHandler": _CapturedCallbackQueryHandler,
            "handle_trend_callback": handler,
        },
    )
    assert len(app.handlers) == 1
    return app.handlers[0]


async def _fixture_trends(_niche, _platform, limit=5):
    assert limit == 5
    return [{"title": "fixture trend", "url": "https://example.invalid", "source": "fixture", "summary": "fixture"}]


def _trend_command_namespace(is_admin_user):
    def save(*args):
        return 17

    return _load_functions(
        "cmd_trend_search",
        "handle_trend_callback",
        is_admin_user=is_admin_user,
        parse_key_value_args=lambda _raw: {},
        get_social_channel=lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected channel read")),
        get_affiliate_link=lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected affiliate read")),
        get_campaign=lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected campaign read")),
        fetch_google_news_trends=_fixture_trends,
        score_trend_candidate=lambda *_args: {
            "trend_score": 91,
            "affiliate_fit_score": 0.8,
            "competition_score": 0.2,
            "score_reason": "fixture only",
        },
        save_trend_candidate=save,
        build_trend_prompt_suggestions=lambda *_args: [],
        reply_html_lines=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected suggestion reply")),
    )


def _emitted_trend_callback(namespace):
    message = _Message()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        message=message,
    )
    context = SimpleNamespace(args=[])
    asyncio.run(namespace["cmd_trend_search"](update, context))
    markup = message.edits[0][1]["reply_markup"]
    callbacks = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    ]
    return next(value for value in callbacks if value == "trend|video|17")


def _forbidden(name, effects):
    def call(*_args, **_kwargs):
        effects.append(name)
        raise AssertionError(f"callback reached protected operation: {name}")
    return call


class TrendCallbackSingleAckTests(unittest.TestCase):
    def test_actual_search_button_matches_registered_trend_route(self):
        namespace = _trend_command_namespace(lambda uid: uid == 123)
        callback = _emitted_trend_callback(namespace)
        route = _registered_trend_route(namespace["handle_trend_callback"])

        self.assertIs(route.callback, namespace["handle_trend_callback"])
        self.assertRegex(callback, route.pattern)

    def test_stale_non_admin_trend_button_gets_one_alert_before_job_seams(self):
        access = {"admin": True}
        effects = []
        namespace = _trend_command_namespace(lambda _uid: access["admin"])
        callback = _emitted_trend_callback(namespace)
        access["admin"] = False

        namespace["get_trend_candidate"] = _forbidden("trend_read", effects)
        namespace["create_calendar_slot"] = _forbidden("calendar_slot", effects)
        namespace["create_production_job"] = _forbidden("production_job", effects)
        namespace["update_trend_status"] = _forbidden("trend_status_write", effects)
        route = _registered_trend_route(namespace["handle_trend_callback"])
        self.assertRegex(callback, route.pattern)

        query = _Query(991122, callback)
        asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

        self.assertEqual(
            query.answers,
            [(('Chỉ Admin được dùng.',), {"show_alert": True})],
        )
        self.assertEqual(query.edits, [])
        self.assertEqual(effects, [])

    def test_authorized_callback_keeps_one_normal_ack_and_stops_before_job_creation(self):
        effects = []
        lookups = []
        namespace = _trend_command_namespace(lambda uid: uid == 123)

        def get_trend(trend_id, _user_id):
            lookups.append(trend_id)
            return (
                17, "niche", "tiktok", "fixture trend", "https://example.invalid", "fixture",
                "summary", 0, 0, 0, "ready", 91, 0.8, 0.2, "fixture only",
            )

        namespace["get_trend_candidate"] = get_trend
        for name in (
            "get_social_channel",
            "create_calendar_slot",
            "get_calendar_slot",
            "create_production_job",
            "update_trend_status",
        ):
            namespace[name] = _forbidden(name, effects)
        route = _registered_trend_route(namespace["handle_trend_callback"])
        callback = _emitted_trend_callback(namespace)
        query = _Query(123, callback)
        asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

        self.assertEqual(query.answers, [((), {})])
        self.assertEqual(lookups, [17])
        self.assertIn("chưa gắn channel", query.edits[0][0])
        self.assertEqual(effects, [])


if __name__ == "__main__":
    unittest.main()
