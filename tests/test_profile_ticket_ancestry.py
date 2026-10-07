"""Owned Ticket navigation preserves Account, list, result and input parents."""
import asyncio
import importlib.util
from pathlib import Path
import re
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location("ticket_ancestry_fixture", Path(__file__).with_name("test_profile_support_pending_origin.py"))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
source = fixture.fixture.fixture.fixture
click = fixture.fixture.fixture._dispatch
buttons = fixture.fixture.fixture._buttons


def _runtime():
    ns, menu, support, calls, now = fixture._runtime()
    ticket = {"id": 901, "ticket_code": "FIXTURE-901", "user_id": "123", "category": "general_support",
              "priority": "normal", "status": "new", "message": "Fixture ticket", "created_at": "fixture-time"}
    reads = []
    def get(ticket_id, uid=None):
        reads.append(("get", ticket_id, uid))
        return dict(ticket) if ticket_id == 901 and (uid is None or str(uid) == ticket["user_id"]) else None
    def update(ticket_id, **fields):
        calls.append(("update", ticket_id, fields)); ticket.update(fields)
        return dict(ticket)
    def listing(**kwargs):
        reads.append(("list", kwargs))
        return [dict(ticket)] if str(kwargs.get("user_id")) == ticket["user_id"] else []
    ns.update({
        "get_support_ticket": get, "update_support_ticket": update, "list_support_tickets": listing,
        "add_support_ticket_message": lambda *args: calls.append(("message", args)),
        "latest_admin_ticket_reply": lambda _id: "", "latest_support_ticket_message": lambda *_args: "Fixture ticket",
    })
    for name in ("public_support_ticket_category_label", "public_support_ticket_status_label",
                 "public_support_ticket_priority_label", "support_ticket_created_text",
                 "support_ticket_detail_keyboard", "public_support_ticket_list_keyboard", "public_support_ticket_text",
                 "handle_ticket_callback", "handle_support_ticket_attachment"):
        exec(compile("from __future__ import annotations\n" + source._function(name), "bot.py:" + name, "exec"), ns)
    routes = []
    ns.update(tg_app=SimpleNamespace(add_handler=routes.append),
              CallbackQueryHandler=lambda callback, pattern: (callback, re.compile(pattern)))
    line = next(line.strip() for line in source.SOURCE.splitlines()
                if "tg_app.add_handler(CallbackQueryHandler(handle_ticket_callback," in line)
    exec(line, ns)
    return ns, menu, support, routes[0], calls, reads, now, ticket


def _select(query, prefix, action):
    return next(button.callback_data for button in buttons(query)
                if str(button.callback_data).split("|")[:2] == [prefix, action])


def _back(query):
    return next(button.callback_data for button in buttons(query) if button.text.startswith(("⬅", "🔙", "←")))


def _list(ns, menu, tickets):
    hub = click(menu, fixture.fixture._entry(ns))
    return click(tickets, _select(hub, "ticket", "mine"))


class AccountTicketAncestryTests(unittest.TestCase):
    def test_emitted_my_tickets_back_returns_account_support(self):
        ns, menu, support, tickets, calls, reads, _, _ = _runtime()
        listing = _list(ns, menu, tickets)
        self.assertEqual("support|start|profile", _back(listing))
        hub = click(support, _back(listing))
        self.assertIn("menu|main_profile", [button.callback_data for button in buttons(hub)])
        self.assertEqual([("list", {"user_id": 123, "limit": 10})], reads)
        self.assertEqual([], calls)

    def test_detail_opened_from_list_back_returns_same_list(self):
        ns, menu, _, tickets, calls, _, _, _ = _runtime()
        listing = _list(ns, menu, tickets)
        detail = click(tickets, _select(listing, "ticket", "pv"))
        self.assertEqual("ticket|mine|profile", _back(detail))
        returned = click(tickets, _back(detail))
        self.assertIn("FIXTURE-901", returned.edits[0][0])
        self.assertEqual("support|start|profile", _back(returned))
        self.assertEqual([], calls)

    def test_result_view_back_restores_owned_result_without_resubmission(self):
        ns, menu, support, tickets, calls, _, _, _ = _runtime()
        fixture._form(ns, menu, support, "ticket")
        message = fixture.Message("Fixture customer input")
        update = SimpleNamespace(effective_user=SimpleNamespace(id=123, username="fixture", first_name="Fixture"), message=message)
        self.assertTrue(asyncio.run(ns["handle_support_pending_input"](update, SimpleNamespace())))
        before = list(calls)
        markup = message.replies[-1][1]["reply_markup"]
        view = next(button.callback_data for row in markup.inline_keyboard for button in row
                    if str(button.callback_data).startswith("ticket|pv|"))
        detail = click(tickets, view)
        self.assertEqual("ticket|summary|901|profile_result", _back(detail))
        result = click(tickets, _back(detail))
        self.assertIn("FIXTURE-901", result.edits[0][0])
        self.assertIn("support|start|profile", [button.callback_data for button in buttons(result)])
        self.assertEqual(before, calls)

    def test_reply_and_attachment_prompt_back_preserves_detail_context(self):
        for action, step in (("reply_user", "awaiting_ticket_reply"), ("attach", "awaiting_attachment")):
            with self.subTest(action=action):
                ns, menu, _, tickets, calls, _, _, _ = _runtime()
                detail = click(tickets, _select(_list(ns, menu, tickets), "ticket", "pv"))
                prompt = click(tickets, _select(detail, "ticket", action))
                state = ns["get_support_ticket_pending"](123)
                self.assertEqual(step, state["step"])
                self.assertEqual("ticket|pv|901|profile", state.get("back_to"))
                self.assertEqual("ticket|pv|901|profile", _back(prompt))
                returned = click(tickets, _back(prompt))
                self.assertIsNone(ns["get_support_ticket_pending"](123))
                self.assertEqual("ticket|mine|profile", _back(returned))
                self.assertEqual([], calls)

    def test_reply_and_attachment_completion_keep_owned_result_navigation(self):
        for action in ("reply_user", "attach"):
            with self.subTest(action=action):
                ns, menu, _, tickets, calls, _, _, _ = _runtime()
                detail = click(tickets, _select(_list(ns, menu, tickets), "ticket", "pv"))
                click(tickets, _select(detail, "ticket", action))
                message = fixture.Message("Fixture reply")
                user = SimpleNamespace(id=123, username="fixture", first_name="Fixture")
                update = SimpleNamespace(effective_user=user, message=message)
                if action == "reply_user":
                    self.assertTrue(asyncio.run(ns["handle_support_pending_input"](update, SimpleNamespace())))
                    self.assertEqual([("message", (901, "user", 123, "Fixture reply", "recorded"))], [item for item in calls if item[0] == "message"])
                    self.assertEqual([("update", 901, {"status": "reviewing"})], [item for item in calls if item[0] == "update"])
                else:
                    message.photo = []
                    message.document = SimpleNamespace(file_id="fixture-file", file_name="fixture.pdf")
                    self.assertTrue(asyncio.run(ns["handle_support_ticket_attachment"](update, SimpleNamespace())))
                    self.assertEqual([("update", 901, {"attachment_file_id": "fixture-file", "attachment_type": "document", "attachment_name": "fixture.pdf"})], [item for item in calls if item[0] == "update"])
                self.assertIsNone(ns["get_support_ticket_pending"](123))
                markup = message.replies[-1][1]["reply_markup"]
                view = next(button.callback_data for row in markup.inline_keyboard for button in row
                            if str(button.callback_data).startswith("ticket|pv|"))
                self.assertEqual("ticket|pv|901|profile_result", view)
                returned = click(tickets, view)
                result = click(tickets, _back(returned))
                self.assertIn("support|start|profile", [button.callback_data for button in buttons(result)])
                self.assertEqual(1, len([item for item in calls if item[0] == "update"]))

    def test_short_reply_back_cancels_only_its_owned_pending(self):
        ns, menu, _, tickets, calls, _, _, _ = _runtime()
        detail = click(tickets, _select(_list(ns, menu, tickets), "ticket", "pv"))
        click(tickets, _select(detail, "ticket", "reply_user"))
        before = dict(ns["get_support_ticket_pending"](123))
        ns["set_support_ticket_pending"](999, "awaiting_message", category="other")
        foreign = dict(ns["get_support_ticket_pending"](999))
        message = fixture.Message("x")
        self.assertTrue(asyncio.run(ns["handle_support_pending_input"](SimpleNamespace(effective_user=SimpleNamespace(id=123), message=message), SimpleNamespace())))
        self.assertEqual(before, ns["get_support_ticket_pending"](123))
        back = next(button.callback_data for row in message.replies[-1][1]["reply_markup"].inline_keyboard
                    for button in row if button.text.startswith(("⬅", "🔙")))
        returned = click(tickets, back)
        self.assertEqual("ticket|mine|profile", _back(returned))
        self.assertIsNone(ns["get_support_ticket_pending"](123))
        self.assertEqual(foreign, ns["get_support_ticket_pending"](999))
        self.assertEqual([], calls)

    def test_invalid_and_foreign_scoped_reads_preserve_pending_and_do_not_write(self):
        ns, _, _, tickets, calls, reads, _, ticket = _runtime()
        ns["set_support_ticket_pending"](123, "awaiting_message", category="other")
        before = dict(ns["get_support_ticket_pending"](123))
        for data in ("ticket|mine|admin", "ticket|pv|901|profile|extra", "ticket|summary|bad|profile_result", "ticket|summary|901|profile"):
            query = click(tickets, data)
            self.assertEqual(1, len(query.answers))
            self.assertTrue(query.answers[0][1].get("show_alert"))
            self.assertEqual([], query.edits)
        self.assertEqual([], reads)
        ticket["user_id"] = "999"
        for data in ("ticket|pv|901|profile", "ticket|summary|901|profile_result", "ticket|reply_user|901|profile"):
            query = click(tickets, data)
            self.assertEqual(1, len(query.answers))
            self.assertTrue(query.answers[0][1].get("show_alert"))
            self.assertEqual([], query.edits)
            self.assertEqual(before, ns["get_support_ticket_pending"](123))
        self.assertTrue(all(row == ("get", 901, 123) for row in reads))
        self.assertEqual([], calls)

    def test_scoped_done_back_returns_detail_with_one_existing_status_update(self):
        ns, menu, _, tickets, calls, _, _, ticket = _runtime()
        detail = click(tickets, _select(_list(ns, menu, tickets), "ticket", "pv"))
        result = click(tickets, _select(detail, "ticket", "done"))
        self.assertEqual([((), {})], result.answers)
        self.assertEqual("ticket|pv|901|profile", _back(result))
        returned = click(tickets, _back(result))
        self.assertEqual("ticket|mine|profile", _back(returned))
        self.assertEqual("resolved", ticket["status"])
        self.assertEqual([("update", 901, {"status": "resolved"})], calls)

    def test_empty_owned_list_and_legacy_controls_keep_defined_destinations(self):
        ns, menu, _, tickets, calls, _, _, ticket = _runtime()
        legacy = click(tickets, "ticket|pv|901")
        self.assertEqual("support|start", _back(legacy))
        legacy_list = click(tickets, "ticket|mine")
        self.assertEqual("support|start", _back(legacy_list))
        ticket["user_id"] = "999"
        empty = _list(ns, menu, tickets)
        self.assertNotIn("FIXTURE-901", empty.edits[0][0])
        self.assertEqual("support|start|profile", _back(empty))
        for button in buttons(empty):
            if button.callback_data:
                self.assertLessEqual(len(button.callback_data.encode("utf-8")), 64)
        self.assertEqual([], calls)


if __name__ == "__main__":
    unittest.main()
