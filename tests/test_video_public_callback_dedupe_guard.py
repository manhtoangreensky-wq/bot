"""Characterize the registered public-Video callback replay guard only."""

from __future__ import annotations

import ast
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
