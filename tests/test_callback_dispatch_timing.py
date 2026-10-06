import asyncio
import re
import unittest
from contextvars import ContextVar
from types import SimpleNamespace
from pathlib import Path


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
LATENCY_FUNCTIONS = (
    "callback_latency_static_prefix",
    "_callback_latency_format_label",
    "_callback_latency_begin",
    "_callback_latency_log",
    "_callback_latency_wrap_handler",
    "_callback_latency_wrap_render",
    "callback_latency_observer",
    "install_callback_latency_instrumentation",
)


class CallbackQueryHandler:
    def __init__(self, callback, pattern=None):
        self.callback = callback
        self.pattern = re.compile(pattern) if isinstance(pattern, str) else pattern


class ApplicationHandlerStop(Exception):
    pass


class FakeApplication:
    def __init__(self, handlers):
        self.handlers = handlers

    def add_handler(self, handler, group=0):
        self.handlers.setdefault(group, []).append(handler)


def _function_source(name):
    start = re.search(rf"(?m)^(?:async\s+)?def {re.escape(name)}\(", BOT_SOURCE)
    if not start:
        return ""
    tail = BOT_SOURCE[start.start():]
    body_start = start.end() - start.start()
    end = re.search(r"(?m)^(?:async\s+)?def \w+\(|^class \w+", tail[body_start:])
    return tail if not end else tail[:body_start + end.start()]


class CallbackDispatchTimingTests(unittest.TestCase):
    def setUp(self):
        missing = [name for name in LATENCY_FUNCTIONS if not _function_source(name)]
        self.assertFalse(missing, f"expected callback timing implementation is missing: {missing}")
        self.now = 0.0
        self.logs = []
        self.namespace = {
            "ContextVar": ContextVar,
            "_CALLBACK_LATENCY_CONTEXT": ContextVar("test_callback_latency", default=None),
            "time": SimpleNamespace(perf_counter=lambda: self.now),
            "re": re,
            "logger": SimpleNamespace(info=lambda message, *args: self.logs.append(message % args)),
            "CallbackQueryHandler": CallbackQueryHandler,
            "ApplicationHandlerStop": ApplicationHandlerStop,
        }
        self.namespace["safe_edit_query_message"] = self._render
        code = "\n".join(_function_source(name) for name in LATENCY_FUNCTIONS)
        exec(compile(code, "bot.py:callback timing", "exec"), self.namespace)

    def test_instrumentation_installs_after_all_direct_callback_registrations(self):
        install_at = BOT_SOURCE.index("install_callback_latency_instrumentation(tg_app)")
        last_registration_at = BOT_SOURCE.rfind("CallbackQueryHandler(")
        self.assertGreater(install_at, last_registration_at)

    async def _render(self, query, text, **_kwargs):
        self.now += 0.005
        return "rendered"

    def _fixture(self, route_callback):
        async def dispatch_throttle_callback_guard(_update, _context):
            self.now += 0.001

        async def safe_mode_callback_guard(_update, _context):
            self.now += 0.002

        async def video_public_callback_dedupe_guard(_update, _context):
            self.now += 0.003

        app = FakeApplication({
            -11: [CallbackQueryHandler(dispatch_throttle_callback_guard)],
            -10: [CallbackQueryHandler(safe_mode_callback_guard)],
            -9: [CallbackQueryHandler(video_public_callback_dedupe_guard)],
            0: [CallbackQueryHandler(route_callback, r"^shopai\|")],
        })
        self.namespace["install_callback_latency_instrumentation"](app)
        update = SimpleNamespace(callback_query=SimpleNamespace(
            data="shopai|PRIVATE-CALLBACK-SECRET",
            from_user=SimpleNamespace(id=987654321),
        ))
        return app, update, SimpleNamespace()

    async def _run_guards(self, app, update, context):
        for group in (-11, -10, -9):
            await app.handlers[group][0].callback(update, context)

    def test_registered_callback_records_guard_handler_and_shared_render_times_anonymously(self):
        async def route(update, _context):
            self.now += 0.004
            await self.namespace["safe_edit_query_message"](
                update.callback_query, "PRIVATE-MESSAGE-SECRET"
            )

        route.__name__ = "handle_shopai_callback"
        app, update, context = self._fixture(route)
        observer_group = max(app.handlers)
        self.assertFalse(self.namespace["install_callback_latency_instrumentation"](app))
        self.assertEqual(len(app.handlers[observer_group]), 1)

        async def dispatch():
            await self._run_guards(app, update, context)
            await app.handlers[0][0].callback(update, context)
            await app.handlers[observer_group][0].callback(update, context)

        asyncio.run(dispatch())

        self.assertEqual(len(self.logs), 1)
        log = self.logs[0]
        self.assertIn("guard_phases=", log)
        fields = dict(re.findall(r"(\w+)=([^ ]+)", log))
        self.assertIn("callback_dispatch_timing", log)
        self.assertEqual(fields["prefix"], "shopai")
        self.assertEqual(fields["handler"], "handle_shopai_callback")
        self.assertAlmostEqual(float(fields["guard_ms"]), 6.0, places=3)
        self.assertEqual(
            fields["guard_phases"],
            "dispatch_throttle_callback_guard:1.000,safe_mode_callback_guard:2.000,"
            "video_public_callback_dedupe_guard:3.000",
        )
        self.assertAlmostEqual(float(fields["handler_ms"]), 9.0, places=3)
        self.assertAlmostEqual(float(fields["render_helper_ms"]), 5.0, places=3)
        self.assertEqual(fields["render_helper_calls"], "1")
        self.assertEqual(fields["outcome"], "ok")
        self.assertTrue(all(secret not in log for secret in (
            "PRIVATE-CALLBACK-SECRET", "PRIVATE-MESSAGE-SECRET", "987654321"
        )))
        self.assertIsNone(self.namespace["_CALLBACK_LATENCY_CONTEXT"].get())

    def test_stopped_shared_guard_logs_coarse_block_and_resets_scope(self):
        async def blocked_guard(_update, _context):
            self.now += 0.002
            raise ApplicationHandlerStop()

        app = FakeApplication({
            -11: [CallbackQueryHandler(blocked_guard)],
            0: [CallbackQueryHandler(lambda *_args: None, r"^shopai\|")],
        })
        blocked_guard.__name__ = "dispatch_throttle_callback_guard"
        self.namespace["install_callback_latency_instrumentation"](app)
        update = SimpleNamespace(callback_query=SimpleNamespace(data="shopai|private"))
        with self.assertRaises(ApplicationHandlerStop):
            asyncio.run(app.handlers[-11][0].callback(update, SimpleNamespace()))

        self.assertEqual(len(self.logs), 1)
        self.assertIn("guard_phases=", self.logs[0])
        fields = dict(re.findall(r"(\w+)=([^ ]+)", self.logs[0]))
        self.assertEqual(fields["outcome"], "blocked")
        self.assertAlmostEqual(float(fields["guard_ms"]), 2.0, places=3)
        self.assertEqual(fields["guard_phases"], "dispatch_throttle_callback_guard:2.000")
        self.assertEqual(fields["handler_ms"], "0.000")
        self.assertNotIn("private", self.logs[0])
        self.assertIsNone(self.namespace["_CALLBACK_LATENCY_CONTEXT"].get())

    def test_handler_error_logs_no_exception_text_and_resets_scope(self):
        async def broken_route(_update, _context):
            self.now += 0.003
            raise RuntimeError("PRIVATE-EXCEPTION-SECRET")

        broken_route.__name__ = "handle_shopai_callback"
        app, update, context = self._fixture(broken_route)

        async def dispatch():
            await self._run_guards(app, update, context)
            await app.handlers[0][0].callback(update, context)

        with self.assertRaisesRegex(RuntimeError, "PRIVATE-EXCEPTION-SECRET"):
            asyncio.run(dispatch())

        self.assertEqual(len(self.logs), 1)
        self.assertIn("outcome=error", self.logs[0])
        self.assertNotIn("PRIVATE-EXCEPTION-SECRET", self.logs[0])
        self.assertNotIn("PRIVATE-CALLBACK-SECRET", self.logs[0])
        self.assertIsNone(self.namespace["_CALLBACK_LATENCY_CONTEXT"].get())


if __name__ == "__main__":
    unittest.main()
