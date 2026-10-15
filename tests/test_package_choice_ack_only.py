"""PayOS package callbacks must acknowledge an unauthorized tap once."""

import re
import unittest
from pathlib import Path


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
    namespace = {**dependencies}
    source = "from __future__ import annotations\n\n" + "\n\n".join(
        _function_source(name) for name in names
    )
    exec(compile(source, str(BOT_PATH), "exec"), namespace)
    return namespace


def _registered_package_route(handler):
    matches = [
        line.strip()
        for line in BOT_SOURCE.splitlines()
        if "tg_app.add_handler(CallbackQueryHandler(handle_package_choice," in line
    ]
    assert len(matches) == 1, f"expected one package-choice registration, got {len(matches)}"
    app = _Application()
    exec(
        matches[0],
        {
            "tg_app": app,
            "CallbackQueryHandler": _CapturedCallbackQueryHandler,
            "handle_package_choice": handler,
        },
    )
    assert len(app.handlers) == 1
    return app.handlers[0]


class PackageChoiceAckTests(unittest.TestCase):
    def test_emitted_package_callback_matches_registered_route_and_ack_is_after_owner_gate(self):
        namespace = _load_functions("payos_package_callback_data", "handle_package_choice")
        callback = namespace["payos_package_callback_data"]("50k", 123)
        route = _registered_package_route(namespace["handle_package_choice"])
        self.assertRegex(callback, route.pattern)
        source = _function_source("handle_package_choice")
        owner_gate = source.index("    if query.from_user.id != uid:")
        self.assertNotIn(
            "\n    await query.answer()\n",
            source[:owner_gate],
            "an unauthorized callback must not receive a normal ACK before its alert",
        )


if __name__ == "__main__":
    unittest.main()
