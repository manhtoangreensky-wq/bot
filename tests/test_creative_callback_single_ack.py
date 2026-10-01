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

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


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


def _registered_creative_route(handler):
    matches = [
        line.strip()
        for line in BOT_SOURCE.splitlines()
        if "tg_app.add_handler(CallbackQueryHandler(handle_creative_callback," in line
    ]
    assert len(matches) == 1, f"expected one creative lifecycle registration, got {len(matches)}"
    app = _Application()
    exec(
        matches[0],
        {
            "tg_app": app,
            "CallbackQueryHandler": _CapturedCallbackQueryHandler,
            "handle_creative_callback": handler,
        },
    )
    assert len(app.handlers) == 1
    return app.handlers[0]


def _emitted_creative_callback(namespace):
    message = _Message()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        message=message,
    )
    context = SimpleNamespace(args=["17"])
    asyncio.run(namespace["cmd_creative_variants"](update, context))
    markup = message.replies[0][1]["reply_markup"]
    callbacks = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    ]
    return next(value for value in callbacks if value == "creative|select|17")


def _variant_list(*_args):
    return [(17, "test", "hook", "angle", "caption", "cta", "tags", 9, "draft", "", "now", None)]


class CreativeCallbackSingleAckTests(unittest.TestCase):
    def test_actual_variant_button_matches_registered_creative_route(self):
        namespace = _load_functions(
            "cmd_creative_variants",
            "handle_creative_callback",
            is_admin_user=lambda uid: uid == 123,
            list_creative_variants=_variant_list,
        )
        callback = _emitted_creative_callback(namespace)
        route = _registered_creative_route(namespace["handle_creative_callback"])

        self.assertIs(route.callback, namespace["handle_creative_callback"])
        self.assertTrue(re.match(route.pattern, callback))

    def test_stale_non_admin_variant_button_gets_one_alert_without_selection_or_edit(self):
        selection_calls = []
        access = {"admin": True}

        def select_variant(*args):
            selection_calls.append(args)
            raise AssertionError("denied stale callback reached creative selection")

        namespace = _load_functions(
            "cmd_creative_variants",
            "handle_creative_callback",
            is_admin_user=lambda _uid: access["admin"],
            list_creative_variants=_variant_list,
            select_creative_variant=select_variant,
        )
        callback = _emitted_creative_callback(namespace)
        access["admin"] = False
        route = _registered_creative_route(namespace["handle_creative_callback"])
        self.assertRegex(callback, route.pattern)

        query = _Query(991122, callback)
        asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

        self.assertEqual(
            query.answers,
            [(('Chỉ Admin được dùng.',), {"show_alert": True})],
        )
        self.assertEqual(query.edits, [])
        self.assertEqual(selection_calls, [])

    def test_authorized_selection_keeps_one_normal_ack_and_existing_result(self):
        selection_calls = []

        def select_variant(user_id, variant_id):
            selection_calls.append((user_id, variant_id))
            return True, (17, 41, "test", "hook", "angle", "caption", "cta", "tags", 9, "selected", "")

        namespace = _load_functions(
            "cmd_creative_variants",
            "handle_creative_callback",
            is_admin_user=lambda uid: uid == 123,
            list_creative_variants=_variant_list,
            select_creative_variant=select_variant,
        )
        callback = _emitted_creative_callback(namespace)
        route = _registered_creative_route(namespace["handle_creative_callback"])
        query = _Query(123, callback)
        asyncio.run(route.callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

        self.assertEqual(query.answers, [((), {})])
        self.assertEqual(selection_calls, [(123, 17)])
        self.assertIn("creative variant #17", query.edits[0][0])
        self.assertIn("/handoff job=41", query.edits[0][0])


if __name__ == "__main__":
    unittest.main()
