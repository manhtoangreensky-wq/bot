"""Owned customer ticket actions acknowledge stale controls exactly once."""
import asyncio
import html
import importlib.util
from pathlib import Path
import re
import time
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location("customer_ticket_ack_fixture", Path(__file__).with_name("test_ticket_view_stale_callback_single_ack.py"))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class Button:
    def __init__(self, text, callback_data):
        self.text, self.callback_data = text, callback_data


class Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class Copy(dict):
    def __missing__(self, key):
        return key


def _runtime(ticket=None):
    reads, edits, writes = [], [], []
    handler = fixture._load_handler([], edits)
    ns = handler.__globals__
    ns.update({
        "InlineKeyboardButton": Button, "InlineKeyboardMarkup": Markup,
        "html": html, "time": time, "USER_PENDING": {},
        "public_hub_copy": lambda _lang: Copy(support_ticket_not_found="Ticket not found", support_ticket_action_unsupported="Action not supported"),
        "get_support_ticket": lambda ticket_id, uid=None: reads.append((ticket_id, uid)) or ticket,
        "update_support_ticket": lambda ticket_id, **fields: writes.append((ticket_id, fields)) or {**ticket, **fields},
    })
    for name in ("support_ticket_detail_keyboard", "support_flow_back_keyboard", "support_ticket_pending_key",
                 "set_support_ticket_pending", "clear_support_ticket_pending"):
        match = re.search(rf"(?ms)^def {name}\(.*?(?=^(?:async )?def |^class |^[A-Z][A-Z0-9_]*\s*=|\Z)", fixture.BOT_SOURCE)
        assert match, name
        exec(compile("from __future__ import annotations\n" + match.group(0), "bot.py:" + name, "exec"), ns)
    routes = []
    ns.update(tg_app=SimpleNamespace(add_handler=routes.append),
              CallbackQueryHandler=lambda callback, pattern: (callback, re.compile(pattern)))
    line = next(line.strip() for line in fixture.BOT_SOURCE.splitlines()
                if "tg_app.add_handler(CallbackQueryHandler(handle_ticket_callback," in line)
    exec(line, ns)
    return ns, routes[0], reads, edits, writes


def _dispatch(route, data):
    handler, pattern = route
    assert pattern.match(data), "emitted ticket action has no registered owner"
    query = fixture._Query(data)
    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))
    return query


class CustomerTicketActionAckTests(unittest.TestCase):
    def test_real_emitted_stale_actions_get_one_alert_without_writes(self):
        ns, route, reads, edits, writes = _runtime()
        markup = ns["support_ticket_detail_keyboard"]({"id": 901}, "vi")
        for action in ("reply_user", "done", "attach"):
            with self.subTest(action=action):
                data = next(button.callback_data for row in markup.inline_keyboard for button in row
                            if button.callback_data.split("|")[1] == action)
                before = len(reads)
                query = _dispatch(route, data)
                self.assertEqual([(("Ticket not found",), {"show_alert": True})], query.answers)
                self.assertEqual([(901, 123)], reads[before:])
        self.assertEqual([], edits)
        self.assertEqual([], writes)
        self.assertEqual({}, ns["USER_PENDING"])

    def test_malformed_customer_action_gets_one_alert_before_lookup(self):
        ns, route, reads, edits, writes = _runtime()
        for action in ("reply_user", "done", "attach"):
            for suffix in ("", "|not-an-id", "|²", "|-1"):
                with self.subTest(action=action, suffix=suffix):
                    query = _dispatch(route, "ticket|" + action + suffix)
                    self.assertEqual([(("Action not supported",), {"show_alert": True})], query.answers)
        self.assertEqual([], reads)
        self.assertEqual([], edits)
        self.assertEqual([], writes)

    def test_valid_customer_action_keeps_single_ack_and_existing_operation(self):
        for action, step in (("reply_user", "awaiting_ticket_reply"), ("attach", "awaiting_attachment"), ("done", None)):
            with self.subTest(action=action):
                ns, route, reads, edits, writes = _runtime({"id": 901, "ticket_code": "FIXTURE-901", "user_id": "123", "status": "new"})
                query = _dispatch(route, "ticket|" + action + "|901")
                self.assertEqual([((), {})], query.answers)
                self.assertEqual([(901, 123)], reads)
                self.assertEqual(1, len(edits))
                if step:
                    self.assertEqual(step, ns["USER_PENDING"]["support_ticket:123"]["step"])
                    self.assertEqual([], writes)
                else:
                    self.assertEqual([(901, {"status": "resolved"})], writes)
                    self.assertEqual({}, ns["USER_PENDING"])


if __name__ == "__main__":
    unittest.main()
