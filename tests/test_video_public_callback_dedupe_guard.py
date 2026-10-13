"""Characterize the registered public-Video callback replay guard only."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import re
import unittest
from types import SimpleNamespace


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def _source_function(name: str) -> str:
    start = re.search(rf"(?m)^(?:async )?def {re.escape(name)}\(", BOT_SOURCE)
    if not start:
        raise AssertionError(f"missing production helper: {name}")
    boundary = re.search(r"(?m)^(?:async )?def \w+\(|^class \w+", BOT_SOURCE[start.end():])
    end = start.end() + boundary.start() if boundary else len(BOT_SOURCE)
    return BOT_SOURCE[start.start():end].rstrip()


class _HandlerStop(Exception):
    pass


class _Query:
    def __init__(self, event_id: str, data: str):
        self.id = event_id
        self.data = data
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _run_immediate(coro):
    try:
        coro.send(None)
    except StopIteration as completed:
        return completed.value
    raise AssertionError("guard fixture unexpectedly yielded I/O")


class VideoPublicCallbackDedupeGuardTests(unittest.TestCase):
    def test_owner_live_accept_keyboards_bind_receipt_and_emit_registered_payload(self):
        class Button:
            def __init__(self, text, callback_data):
                self.text = text
                self.callback_data = callback_data

        class Markup:
            def __init__(self, inline_keyboard):
                self.inline_keyboard = inline_keyboard

        namespace = {
            "hashlib": hashlib,
            "InlineKeyboardButton": Button,
            "InlineKeyboardMarkup": Markup,
            "ui_text": lambda _lang, key: key,
            "product_video_public_preflight_public_kind": lambda _state: "blocked",
        }
        names = [
            "build_product_video_owner_live_accept_keyboard",
            "product_video_public_preflight_panel_keyboard",
        ]
        if re.search(r"(?m)^def product_video_owner_live_accept_callback_token\(", BOT_SOURCE):
            names.insert(0, "product_video_owner_live_accept_callback_token")
        functions = "from __future__ import annotations\n\n" + "\n\n".join(
            _source_function(name) for name in names
        )
        exec(compile(functions, "bot.py:owner live-accept keyboard", "exec"), namespace)

        receipt = "owner_live_auth_deadbeef0123456789"
        expected_token = hashlib.sha256(receipt.encode("utf-8")).hexdigest()[:12]
        emitted = [
            namespace["build_product_video_owner_live_accept_keyboard"](receipt)
            .inline_keyboard[0][0]
            .callback_data,
            namespace["product_video_public_preflight_panel_keyboard"](owner_receipt=receipt)
            .inline_keyboard[0][0]
            .callback_data,
        ]
        owner_route = re.search(
            r'(?m)^\s*tg_app\.add_handler\(CallbackQueryHandler\('
            r'handle_product_video_owner_live_accept_callback, pattern=r"([^"]+)"\)\)\s*$',
            BOT_SOURCE,
        )
        self.assertIsNotNone(owner_route)
        pattern = re.compile(owner_route.group(1))
        expected_callback = f"vproduct|owner_live_accept|{expected_token}"
        for callback_data in emitted:
            self.assertEqual(callback_data, expected_callback)
            self.assertTrue(pattern.fullmatch(callback_data))

    def test_stale_owner_live_accept_token_is_acknowledged_without_paid_confirmation(self):
        old_receipt = "owner_live_auth_old0123456789"
        active_receipt = "owner_live_auth_new9876543210"
        stale_token = hashlib.sha256(old_receipt.encode("utf-8")).hexdigest()[:12]

        class Query:
            def __init__(self):
                self.id = "callback-stale-owner-receipt-unique"
                self.data = f"vproduct|owner_live_accept|{stale_token}"
                self.from_user = SimpleNamespace(id=777888)
                self.answers = []
                self.edited_text = ""

            async def answer(self, *args, **kwargs):
                self.answers.append((args, kwargs))

            async def edit_message_text(self, text, **kwargs):
                self.edited_text = text
                return text

        query = Query()
        update = SimpleNamespace(
            update_id=778899,
            callback_query=query,
            effective_user=query.from_user,
            effective_chat=SimpleNamespace(id=999111),
        )
        context = SimpleNamespace(
            user_data={
                "video_session": {
                    "owner_acceptance_token": active_receipt,
                    "job_id": 1401,
                    "request_id": "req_1401",
                }
            }
        )

        async def reject_unexpected_paid_path(*args, **kwargs):
            paid_calls.append((args, kwargs))
            raise RuntimeError("paid confirmation must not run for a stale callback")

        paid_calls = []

        async def safe_edit_or_send(query, text):
            query.edited_text = text
            return text

        namespace = {
            "hashlib": hashlib,
            "re": re,
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "safe_edit_or_send": safe_edit_or_send,
            "handle_owner_authorized_live_test_confirm": reject_unexpected_paid_path,
            "logger": SimpleNamespace(error=lambda *_args, **_kwargs: None),
        }
        names = ["handle_product_video_owner_live_accept_callback"]
        if re.search(r"(?m)^def product_video_owner_live_accept_callback_token\(", BOT_SOURCE):
            names.insert(0, "product_video_owner_live_accept_callback_token")
        functions = "from __future__ import annotations\n\n" + "\n\n".join(
            _source_function(name) for name in names
        )
        exec(compile(functions, "bot.py:owner live-accept handler", "exec"), namespace)
        _run_immediate(namespace["handle_product_video_owner_live_accept_callback"](update, context))

        self.assertEqual(paid_calls, [])
        self.assertEqual(len(query.answers), 1)
        self.assertIn("hết hạn", query.edited_text.lower())

    def test_owner_live_accept_has_an_exact_dedicated_route_before_generic_video(self):
        owner_route = re.search(
            r'(?m)^\s*tg_app\.add_handler\(CallbackQueryHandler\('
            r'handle_product_video_owner_live_accept_callback, pattern=r"([^"]+)"\)\)\s*$',
            BOT_SOURCE,
        )
        generic_route = re.search(
            r'(?m)^\s*tg_app\.add_handler\(CallbackQueryHandler\('
            r'handle_video_product_callback, pattern=r"([^"]+)"\)\)\s*$',
            BOT_SOURCE,
        )
        self.assertIsNotNone(owner_route)
        self.assertIsNotNone(generic_route)
        pattern = re.compile(owner_route.group(1))
        self.assertTrue(pattern.fullmatch("vproduct|owner_live_accept"))
        self.assertTrue(pattern.fullmatch("vproduct|owner_live_accept|0123456789ab"))
        self.assertTrue(pattern.fullmatch("vproduct|owner_live_accept|NOT-A-TOKEN"))
        self.assertLess(owner_route.start(), generic_route.start())
        generic_pattern = re.compile(generic_route.group(1))
        self.assertFalse(generic_pattern.match("vproduct|owner_live_accept|0123456789ab"))

    def test_exact_replay_stops_before_route_but_distinct_event_reaches_route(self):
        self.assertIn(
            "tg_app.add_handler(CallbackQueryHandler(video_public_callback_dedupe_guard), group=-9)",
            BOT_SOURCE,
        )
        route_registration = re.search(
            r"tg_app\.add_handler\(CallbackQueryHandler\(handle_video_profile_studio_callback, pattern=(r?['\"][^'\"]+['\"])\)\)",
            BOT_SOURCE,
        )
        self.assertIsNotNone(route_registration)

        prefix_match = re.search(
            r"(?ms)^VIDEO_PUBLIC_CALLBACK_PREFIXES\s*=\s*(\(.*?^\))", BOT_SOURCE
        )
        self.assertIsNotNone(prefix_match)
        prefixes = ast.literal_eval(prefix_match.group(1))
        namespace = {
            "time": SimpleNamespace(time=lambda: 1000.0),
            "VIDEO_PUBLIC_CALLBACK_DEDUPE_TTL_SECONDS": 600,
            "VIDEO_PUBLIC_CALLBACK_PREFIXES": prefixes,
            "_VIDEO_PUBLIC_CALLBACK_CLAIMS": {},
            "ApplicationHandlerStop": _HandlerStop,
        }
        functions = "from __future__ import annotations\n\n" + "\n\n".join(
            _source_function(name)
            for name in (
                "_claim_video_public_event",
                "_is_video_public_callback",
                "video_public_callback_dedupe_guard",
            )
        )
        exec(compile(functions, "bot.py:video public callback guard", "exec"), namespace)

        route_pattern = re.compile(ast.literal_eval(route_registration.group(1)))
        route_calls = []

        async def registered_route(_update, _context):
            route_calls.append("called")

        async def dispatch(query):
            update = SimpleNamespace(callback_query=query)
            context = SimpleNamespace(user_data={})
            # Mirrors the production guard group (-9) before route group (0).
            await namespace["video_public_callback_dedupe_guard"](update, context)
            if route_pattern.match(query.data):
                await registered_route(update, context)

        first = _Query("callback-event-1", "vprofile|image_source|create")
        replay = _Query("callback-event-1", "vprofile|image_source|create")
        distinct_tap = _Query("callback-event-2", "vprofile|image_source|create")

        _run_immediate(dispatch(first))
        with self.assertRaises(_HandlerStop):
            _run_immediate(dispatch(replay))
        _run_immediate(dispatch(distinct_tap))

        self.assertEqual(route_calls, ["called", "called"])
        self.assertEqual(
            replay.answers,
            [(("TOAN AAS đã nhận thao tác này.",), {})],
        )
        self.assertEqual(first.answers, [])
        self.assertEqual(distinct_tap.answers, [])


if __name__ == "__main__":
    unittest.main()
