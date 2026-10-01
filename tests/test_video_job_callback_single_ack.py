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


def _registered_video_job_route(handler):
    matches = [
        line.strip()
        for line in BOT_SOURCE.splitlines()
        if "tg_app.add_handler(CallbackQueryHandler(handle_video_job_callback," in line
    ]
    assert len(matches) == 1, f"expected one video-job lifecycle registration, got {len(matches)}"
    app = _Application()
    exec(
        matches[0],
        {
            "tg_app": app,
            "CallbackQueryHandler": _CapturedCallbackQueryHandler,
            "handle_video_job_callback": handler,
        },
    )
    assert len(app.handlers) == 1
    return app.handlers[0]


def _video_plan_namespace(is_admin_user):
    campaign = (2, "fixture", "", "", "tiktok", "https://example.invalid", "")
    return _load_functions(
        "cmd_video_plan",
        "handle_video_job_callback",
        is_admin_user=is_admin_user,
        gemini_client=object(),
        openai_client=None,
        parse_key_value_args=lambda _raw: {
            "campaign": "2",
            "topic": "fixture topic",
            "platforms": "tiktok",
        },
        get_campaign=lambda *_args: campaign,
        get_social_channel=lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected channel read")),
        get_affiliate_link=lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected affiliate read")),
        build_video_brief_prompt=lambda *_args: "fixture prompt",
        AgentGemini=SimpleNamespace(chat=lambda *_args, **_kwargs: "fixture brief"),
        create_video_job=lambda *_args: 17,
        html_pre=lambda value, *_args: str(value),
    )


def _emitted_video_job_callback(namespace):
    message = _Message()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        message=message,
    )
    context = SimpleNamespace(args=["campaign=2", "topic=fixture"])
    asyncio.run(namespace["cmd_video_plan"](update, context))
    markup = message.edits[0][1]["reply_markup"]
    callbacks = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    ]
    return next(value for value in callbacks if value == "job|approve|17")


def _forbidden(name, effects):
    def call(*_args, **_kwargs):
        effects.append(name)
        raise AssertionError(f"denied callback reached video-job operation: {name}")
    return call


class VideoJobCallbackSingleAckTests(unittest.TestCase):
    def test_actual_video_plan_button_matches_registered_job_route(self):
        namespace = _video_plan_namespace(lambda uid: uid == 123)
        callback = _emitted_video_job_callback(namespace)
        route = _registered_video_job_route(namespace["handle_video_job_callback"])

        self.assertIs(route.callback, namespace["handle_video_job_callback"])
        self.assertRegex(callback, route.pattern)

    def test_stale_non_admin_approval_button_gets_one_alert_without_job_lookup_or_update(self):
        access = {"admin": True}
        effects = []
        namespace = _video_plan_namespace(lambda _uid: access["admin"])
        callback = _emitted_video_job_callback(namespace)
        access["admin"] = False
        namespace["get_video_job"] = _forbidden("get_video_job", effects)
        namespace["update_video_job_status"] = _forbidden("update_video_job_status", effects)
        namespace["campaign_stats"] = _forbidden("campaign_stats", effects)
        route = _registered_video_job_route(namespace["handle_video_job_callback"])
        self.assertRegex(callback, route.pattern)

        query = _Query(991122, callback)
        asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

        self.assertEqual(
            query.answers,
            [(('Chỉ Admin được dùng.',), {"show_alert": True})],
        )
        self.assertEqual(query.edits, [])
        self.assertEqual(effects, [])

    def test_authorized_approval_keeps_one_ack_and_existing_status_update_with_fake_seams(self):
        updates = []
        job = (17, 2, 0, "fixture topic", "tiktok", "https://example.invalid", "draft", "fixture brief")

        def update_status(*args):
            updates.append(args)

        namespace = _video_plan_namespace(lambda uid: uid == 123)
        namespace["get_video_job"] = lambda job_id, user_id: job if (job_id, user_id) == (17, 123) else None
        namespace["update_video_job_status"] = update_status
        route = _registered_video_job_route(namespace["handle_video_job_callback"])
        callback = _emitted_video_job_callback(namespace)
        query = _Query(123, callback)
        asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

        self.assertEqual(query.answers, [((), {})])
        self.assertEqual(updates, [(17, "approved", "approved_at")])
        self.assertIn("Đã duyệt VIDEO JOB #17", query.edits[0][0])


if __name__ == "__main__":
    unittest.main()
