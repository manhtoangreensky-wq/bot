"""Owned Ticket navigation preserves Account, list, result and input parents."""
import importlib.util
from pathlib import Path
import re
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location("ticket_ancestry_fixture", Path(__file__).with_name("test_profile_support_pending_origin.py"))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
source = fixture.fixture.fixture.fixture
click = fixture.fixture._dispatch_now
buttons = fixture.fixture.fixture._buttons


def _runtime():
    ns, menu, support, calls, now = fixture._runtime()
    ticket = {"id": 901, "ticket_code": "FIXTURE-901", "user_id": "123", "category": "general_support",
              "priority": "normal", "status": "new", "message": "Fixture ticket", "created_at": "fixture-time"}
    reads = []

    async def to_thread(function, *args, **kwargs):
        return function(*args, **kwargs)

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
        "asyncio": SimpleNamespace(to_thread=to_thread),
        "get_support_ticket": get, "update_support_ticket": update, "list_support_tickets": listing,
        "add_support_ticket_message": lambda *args: calls.append(("message", args)),
        "latest_admin_ticket_reply": lambda _id: "", "latest_support_ticket_message": lambda *_args: "Fixture ticket",
    })
    for name in ("public_support_ticket_category_label", "public_support_ticket_status_label",
                 "public_support_ticket_priority_label", "support_ticket_menu_text", "support_ticket_menu_keyboard",
                 "support_ticket_message_prompt", "support_ticket_input_keyboard", "support_ticket_created_text",
                 "support_ticket_created_keyboard", "ticket_customer_origin_keyboard",
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


def _run_now(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    coroutine.close()
    raise AssertionError("fixture coroutine unexpectedly yielded I/O")


def _dispatch_immediate(route, data):
    handler, pattern = route
    assert pattern.match(data), f"registered route does not accept {data!r}"

    class Query:
        def __init__(self):
            self.data = data
            self.from_user = SimpleNamespace(id=123)
            self.answers = []
            self.edits = []

        async def answer(self, *args, **kwargs):
            self.answers.append((args, kwargs))

    query = Query()
    coroutine = handler(SimpleNamespace(callback_query=query), SimpleNamespace(user_data={}))
    try:
        coroutine.send(None)
    except StopIteration:
        pass
    else:
        coroutine.close()
        raise AssertionError("fixture callback unexpectedly yielded asynchronous I/O")
    return query


def _list(ns, menu, tickets):
    hub = click(menu, fixture.fixture._entry(ns))
    return click(tickets, _select(hub, "ticket", "mine"))


class AccountTicketAncestryTests(unittest.TestCase):
    def test_feedback_created_ticket_view_back_restores_created_result(self):
        ns, _, _, tickets, calls, reads, _, _ = _runtime()
        result_keyboard = ns["ticket_customer_origin_keyboard"](
            ns["support_ticket_created_keyboard"](901, "vi"), "feedback_result", "vi"
        )
        view_callback = next(
            button.callback_data
            for row in result_keyboard.inline_keyboard
            for button in row
            if button.callback_data.startswith("ticket|pv|")
        )
        self.assertEqual("ticket|pv|901|feedback_result", view_callback)

        detail = _dispatch_immediate(tickets, view_callback)
        self.assertEqual([((), {})], detail.answers)
        self.assertEqual("ticket|summary|901|feedback_result", _back(detail))
        result = _dispatch_immediate(tickets, _back(detail))
        self.assertIn("FIXTURE-901", result.edits[0][0])
        self.assertEqual("ticket|pv|901|feedback_result", next(
            button.callback_data
            for row in result.edits[0][1]["reply_markup"].inline_keyboard
            for button in row
            if button.callback_data.startswith("ticket|pv|")
        ))
        self.assertEqual([("get", 901, 123), ("get", 901, 123)], reads)
        self.assertEqual([], calls)

    def test_feedback_ticket_reply_and_attachment_prompts_keep_result_origin(self):
        for action, expected_step in (("reply_user", "awaiting_ticket_reply"), ("attach", "awaiting_attachment")):
            with self.subTest(action=action):
                ns, _, _, tickets, calls, _, _, _ = _runtime()
                result_keyboard = ns["ticket_customer_origin_keyboard"](
                    ns["support_ticket_created_keyboard"](901, "vi"), "feedback_result", "vi"
                )
                prompt_callback = next(
                    button.callback_data
                    for row in result_keyboard.inline_keyboard
                    for button in row
                    if button.callback_data.startswith(f"ticket|{action}|")
                )
                prompt = _dispatch_immediate(tickets, prompt_callback)
                pending = ns["get_support_ticket_pending"](123)
                self.assertEqual(expected_step, pending["step"])
                self.assertEqual("ticket|pv|901|feedback_result", _back(prompt))

                detail = _dispatch_immediate(tickets, _back(prompt))
                self.assertEqual("ticket|summary|901|feedback_result", _back(detail))
                receipt = _dispatch_immediate(tickets, _back(detail))
                self.assertIn("FIXTURE-901", receipt.edits[0][0])
                self.assertIsNone(ns["get_support_ticket_pending"](123))
                self.assertEqual([], calls)

    def test_emitted_my_tickets_back_returns_account_support(self):
        ns, menu, support, tickets, calls, reads, _, _ = _runtime()
        listing = _list(ns, menu, tickets)
        self.assertEqual("support|start|profile", _back(listing))
        hub = click(support, _back(listing))
        self.assertIn("menu|main_profile", [button.callback_data for button in buttons(hub)])
        self.assertEqual([("list", {"user_id": 123, "limit": 10})], reads)
        self.assertEqual([], calls)

    def test_public_emitted_my_tickets_back_restores_public_support_and_home(self):
        ns, menu, support, tickets, calls, reads, now, ticket = _runtime()
        ns["time"].perf_counter = lambda: now["value"]
        public_root = fixture.fixture._dispatch_now(support, "support|start")
        self.assertEqual([((), {})], public_root.answers)
        root_callbacks = [button.callback_data for button in buttons(public_root)]
        entry = next(callback for callback in root_callbacks if callback == "ticket|mine|support")

        listing = _dispatch_immediate(tickets, entry)
        self.assertEqual([((), {})], listing.answers)
        self.assertIn("FIXTURE-901", listing.edits[0][0])
        self.assertEqual([("list", {"user_id": 123, "limit": 10})], reads)
        self.assertEqual("new", ticket["status"])
        self.assertEqual([], calls)
        list_buttons = buttons(listing)
        back = _back(listing)
        home = next(button.callback_data for button in list_buttons if button.callback_data == "menu|main")
        self.assertEqual("support|start", back)

        support_root = fixture.fixture._dispatch_now(support, back)
        self.assertEqual([((), {})], support_root.answers)
        self.assertEqual(root_callbacks, [button.callback_data for button in buttons(support_root)])

        main = fixture.fixture._dispatch_now(menu, home)
        self.assertEqual([((), {})], main.answers)
        self.assertIn("MAIN MENU", main.edits[0][0])
        self.assertEqual([], calls)

    def test_emitted_public_my_tickets_acks_before_language_and_offloads_only_list_read(self):
        ns, _, _, tickets, _, _, _, ticket = _runtime()
        ns["set_support_ticket_pending"](123, "awaiting_message", category="actor-fixture")
        foreign_pending = ns["set_support_ticket_pending"](999, "awaiting_message", category="foreign-fixture")
        emitted = next(
            button.callback_data
            for row in ns["human_support_keyboard"]("vi").inline_keyboard
            for button in row
            if button.callback_data.startswith("ticket|mine|")
        )
        self.assertEqual("ticket|mine|support", emitted)

        events = []
        active_query = {}

        def get_language(user_id):
            events.append(("language", len(active_query["query"].answers), user_id))
            return "vi"

        def list_tickets(**kwargs):
            events.append(("list", len(active_query["query"].answers), kwargs))
            return [dict(ticket)] if str(kwargs.get("user_id")) == "123" else []

        async def to_thread(function, *args, **kwargs):
            events.append(("offload", function.__name__, len(active_query["query"].answers)))
            return function(*args, **kwargs)

        ns["get_user_language"] = get_language
        ns["list_support_tickets"] = list_tickets
        ns["asyncio"] = SimpleNamespace(to_thread=to_thread)

        class Query:
            def __init__(self):
                self.data = emitted
                self.from_user = SimpleNamespace(id=123)
                self.answers = []
                self.edits = []

            async def answer(self, *args, **kwargs):
                self.answers.append((args, kwargs))
                events.append(("ack",))

        query = Query()
        active_query["query"] = query
        handler, pattern = tickets
        self.assertIsNotNone(pattern.match(emitted))
        _run_now(handler(SimpleNamespace(callback_query=query), SimpleNamespace(user_data={})))

        self.assertEqual([((), {})], query.answers)
        self.assertEqual(["ack", "language", "offload", "list"], [event[0] for event in events])
        self.assertEqual(("language", 1, 123), events[1])
        self.assertEqual(("offload", "list_tickets", 1), events[2])
        self.assertEqual(("list", 1, {"user_id": 123, "limit": 10}), events[3])
        self.assertIn("FIXTURE-901", query.edits[0][0])
        self.assertEqual("support|start", _back(query))
        self.assertIn("menu|main", [button.callback_data for button in buttons(query)])
        self.assertIsNone(ns["get_support_ticket_pending"](123))
        self.assertEqual(foreign_pending, ns["get_support_ticket_pending"](999))

    def test_invalid_my_tickets_origin_fails_closed_without_list_read_or_pending_cleanup(self):
        ns, _, _, tickets, _, reads, _, _ = _runtime()
        actor_pending = ns["set_support_ticket_pending"](123, "awaiting_message", category="actor-fixture")
        ns["list_support_tickets"] = lambda **kwargs: reads.append(("list", kwargs)) or []

        query = _dispatch_immediate(tickets, "ticket|mine|admin")

        self.assertEqual(1, len(query.answers))
        self.assertTrue(query.answers[0][1].get("show_alert"))
        self.assertEqual([], query.edits)
        self.assertEqual([], reads)
        self.assertEqual(actor_pending, ns["get_support_ticket_pending"](123))

    def test_emitted_ticket_category_acks_before_language_and_pending_set(self):
        ns, _, _, tickets, _, _, _, _ = _runtime()
        ns["SUPPORT_CATEGORIES"] = {
            "payment_topup", "image_error", "video_error", "document_pdf",
            "package_combo", "refund", "feature_request", "lead_consulting", "other",
        }
        foreign_pending = ns["set_support_ticket_pending"](999, "awaiting_message", category="foreign-fixture")
        emitted = next(
            button.callback_data
            for row in ns["support_ticket_menu_keyboard"]("vi").inline_keyboard
            for button in row
            if button.callback_data == "ticket|cat|image_error"
        )
        events = []
        active_query = {}
        set_pending = ns["set_support_ticket_pending"]

        def get_language(user_id):
            events.append(("language", len(active_query["query"].answers), user_id))
            return "vi"

        def set_pending_with_trace(user_id, step, **kwargs):
            events.append(("pending", len(active_query["query"].answers), user_id, step, kwargs))
            return set_pending(user_id, step, **kwargs)

        ns["get_user_language"] = get_language
        ns["set_support_ticket_pending"] = set_pending_with_trace

        class Query:
            def __init__(self):
                self.data = emitted
                self.from_user = SimpleNamespace(id=123)
                self.answers = []
                self.edits = []

            async def answer(self, *args, **kwargs):
                self.answers.append((args, kwargs))
                events.append(("ack",))

        query = Query()
        active_query["query"] = query
        handler, pattern = tickets
        self.assertIsNotNone(pattern.match(emitted))
        _run_now(handler(SimpleNamespace(callback_query=query), SimpleNamespace(user_data={})))

        self.assertEqual([((), {})], query.answers)
        self.assertEqual(["ack", "language", "pending"], [event[0] for event in events])
        self.assertEqual(("language", 1, 123), events[1])
        self.assertEqual(("pending", 1, 123, "awaiting_message", {"category": "image_error"}), events[2])
        self.assertEqual("image_error", ns["get_support_ticket_pending"](123)["category"])
        self.assertEqual(foreign_pending, ns["get_support_ticket_pending"](999))
        self.assertEqual(1, len(query.edits))
        self.assertEqual("ticket|start", _back(query))
        self.assertIn("menu|main", [button.callback_data for button in buttons(query)])

    def test_public_my_ticket_detail_back_restores_exact_public_list(self):
        ns, _, support, tickets, calls, reads, now, ticket = _runtime()
        ns["time"].perf_counter = lambda: now["value"]
        public_root = fixture.fixture._dispatch_now(support, "support|start")
        public_callbacks = [button.callback_data for button in buttons(public_root)]
        my_tickets = next(callback for callback in public_callbacks if callback == "ticket|mine|support")
        listing = _dispatch_immediate(tickets, my_tickets)
        self.assertEqual([((), {})], listing.answers)
        list_callbacks = [button.callback_data for button in buttons(listing)]
        self.assertIn("FIXTURE-901", listing.edits[0][0])

        view = _select(listing, "ticket", "pv")
        detail = _dispatch_immediate(tickets, view)
        self.assertEqual([((), {})], detail.answers)
        self.assertIn("FIXTURE-901", detail.edits[0][0])
        back = _back(detail)
        self.assertEqual("ticket|mine|support", back)

        returned = _dispatch_immediate(tickets, back)
        self.assertEqual([((), {})], returned.answers)
        self.assertEqual(list_callbacks, [button.callback_data for button in buttons(returned)])
        self.assertIn("FIXTURE-901", returned.edits[0][0])
        self.assertEqual([("list", {"user_id": 123, "limit": 10}),
                          ("get", 901, 123),
                          ("list", {"user_id": 123, "limit": 10})], reads)
        self.assertEqual("new", ticket["status"])
        self.assertEqual([], calls)

    def test_public_support_child_my_tickets_back_restores_exact_child(self):
        expected_pages = {
            "admin_contact": "support_contact_title",
            "cskh_auto": "support_auto_title",
            "premium": "support_premium",
        }
        for action, heading in expected_pages.items():
            with self.subTest(action=action):
                ns, _, support, tickets, calls, reads, _, _ = _runtime()
                root = ns["human_support_keyboard"]("vi")
                entry = next(button.callback_data for row in root.inline_keyboard for button in row
                             if button.callback_data == f"support|{action}")
                page = fixture.fixture._dispatch_now(support, entry)
                self.assertIn(heading, page.edits[0][0])

                mine = _select(page, "ticket", "mine")
                self.assertEqual(f"ticket|mine|{action}", mine)
                listing = _dispatch_immediate(tickets, mine)
                list_callbacks = [button.callback_data for button in buttons(listing)]
                detail = _dispatch_immediate(tickets, _select(listing, "ticket", "pv"))
                self.assertEqual(f"ticket|mine|{action}", _back(detail))
                returned_list = _dispatch_immediate(tickets, _back(detail))
                self.assertEqual(list_callbacks, [button.callback_data for button in buttons(returned_list)])
                back = _back(returned_list)
                self.assertEqual(f"support|{action}", back)
                returned = fixture.fixture._dispatch_now(support, back)
                self.assertIn(heading, returned.edits[0][0])
                self.assertEqual([button.callback_data for button in buttons(page)],
                                 [button.callback_data for button in buttons(returned)])
                self.assertEqual([("list", {"user_id": 123, "limit": 10}), ("get", 901, 123),
                                  ("list", {"user_id": 123, "limit": 10})], reads)
                self.assertEqual([], calls)

    def test_account_support_child_my_tickets_back_restores_exact_child(self):
        expected_pages = {
            "admin_contact": "support_contact_title",
            "cskh_auto": "support_auto_title",
            "premium": "support_premium",
        }
        for action, heading in expected_pages.items():
            with self.subTest(action=action):
                ns, _, support, tickets, calls, reads, _, _ = _runtime()
                root = ns["support_read_origin_keyboard"](
                    ns["human_support_keyboard"]("vi"), True, "vi", root=True
                )
                entry = next(button.callback_data for row in root.inline_keyboard for button in row
                             if button.callback_data == f"support|{action}|profile")
                page = fixture.fixture._dispatch_now(support, entry)
                self.assertIn(heading, page.edits[0][0])
                mine = _select(page, "ticket", "mine")
                self.assertEqual(f"ticket|mine|profile_{action}", mine)
                listing = _dispatch_immediate(tickets, mine)
                list_callbacks = [button.callback_data for button in buttons(listing)]
                detail = _dispatch_immediate(tickets, _select(listing, "ticket", "pv"))
                self.assertEqual(f"ticket|mine|profile_{action}", _back(detail))
                returned_list = _dispatch_immediate(tickets, _back(detail))
                self.assertEqual(list_callbacks, [button.callback_data for button in buttons(returned_list)])
                back = _back(returned_list)
                self.assertEqual(f"support|{action}|profile", back)
                returned = fixture.fixture._dispatch_now(support, back)
                self.assertIn(heading, returned.edits[0][0])
                self.assertEqual([button.callback_data for button in buttons(page)],
                                 [button.callback_data for button in buttons(returned)])
                self.assertEqual([("list", {"user_id": 123, "limit": 10}), ("get", 901, 123),
                                  ("list", {"user_id": 123, "limit": 10})], reads)
                self.assertEqual([], calls)

    def test_ticket_category_menu_my_tickets_back_restores_category_menu(self):
        ns, _, _, tickets, calls, reads, _, _ = _runtime()
        category_page = _dispatch_immediate(tickets, "ticket|start")
        category_callbacks = [button.callback_data for button in buttons(category_page)]
        mine = _select(category_page, "ticket", "mine")
        self.assertEqual("ticket|mine|ticket_menu", mine)

        listing = _dispatch_immediate(tickets, mine)
        self.assertEqual("ticket|start", _back(listing))
        detail = _dispatch_immediate(tickets, _select(listing, "ticket", "pv"))
        self.assertEqual("ticket|mine|ticket_menu", _back(detail))
        returned_list = _dispatch_immediate(tickets, _back(detail))
        self.assertEqual([button.callback_data for button in buttons(listing)],
                         [button.callback_data for button in buttons(returned_list)])
        returned = _dispatch_immediate(tickets, _back(returned_list))
        self.assertEqual(category_callbacks, [button.callback_data for button in buttons(returned)])
        self.assertEqual([("list", {"user_id": 123, "limit": 10}), ("get", 901, 123),
                          ("list", {"user_id": 123, "limit": 10})], reads)
        self.assertEqual([], calls)

    def test_premium_form_my_tickets_back_restores_premium_page(self):
        for profile_origin in (False, True):
            with self.subTest(profile_origin=profile_origin):
                ns, _, support, tickets, calls, reads, _, _ = _runtime()
                root = ns["support_read_origin_keyboard"](
                    ns["human_support_keyboard"]("vi"), profile_origin, "vi", root=True
                )
                premium_entry = next(button.callback_data for row in root.inline_keyboard for button in row
                                     if button.callback_data == ("support|premium|profile" if profile_origin else "support|premium"))
                premium_page = fixture.fixture._dispatch_now(support, premium_entry)
                select_plan = _select(premium_page, "support", "premium_type")
                prompt = fixture.fixture._dispatch_now(support, select_plan)
                expected_origin = "profile_premium" if profile_origin else "premium"
                mine = _select(prompt, "ticket", "mine")
                self.assertEqual(f"ticket|mine|{expected_origin}", mine)

                listing = _dispatch_immediate(tickets, mine)
                expected_back = "support|premium|profile" if profile_origin else "support|premium"
                self.assertEqual(expected_back, _back(listing))
                self.assertIsNone(ns["get_support_ticket_pending"](123))
                returned = fixture.fixture._dispatch_now(support, _back(listing))
                self.assertIn("support_premium", returned.edits[0][0])
                self.assertEqual([("list", {"user_id": 123, "limit": 10})], reads)
                self.assertEqual([], calls)

    def test_account_ticket_origin_remains_profile_scoped(self):
        ns, _, _, tickets, calls, reads, now, ticket = _runtime()
        ns["time"].perf_counter = lambda: now["value"]
        account_root = ns["support_read_origin_keyboard"](
            ns["human_support_keyboard"]("vi"), True, "vi", root=True
        )
        entry = next(button.callback_data for row in account_root.inline_keyboard for button in row
                     if button.text.startswith("📂"))
        self.assertEqual("ticket|mine|profile", entry)

        listing = _dispatch_immediate(tickets, entry)
        view = _select(listing, "ticket", "pv")
        detail = _dispatch_immediate(tickets, view)
        back = _back(detail)
        self.assertEqual("ticket|mine|profile", back)
        returned = _dispatch_immediate(tickets, back)
        self.assertEqual([button.callback_data for button in buttons(listing)],
                         [button.callback_data for button in buttons(returned)])
        self.assertEqual("new", ticket["status"])
        self.assertEqual([("list", {"user_id": 123, "limit": 10}), ("get", 901, 123),
                          ("list", {"user_id": 123, "limit": 10})], reads)
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
        self.assertTrue(_run_now(ns["handle_support_pending_input"](update, SimpleNamespace())))
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
                    self.assertTrue(_run_now(ns["handle_support_pending_input"](update, SimpleNamespace())))
                    self.assertEqual([("message", (901, "user", 123, "Fixture reply", "recorded"))], [item for item in calls if item[0] == "message"])
                    self.assertEqual([("update", 901, {"status": "reviewing"})], [item for item in calls if item[0] == "update"])
                else:
                    message.photo = []
                    message.document = SimpleNamespace(file_id="fixture-file", file_name="fixture.pdf")
                    self.assertTrue(_run_now(ns["handle_support_ticket_attachment"](update, SimpleNamespace())))
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
        self.assertTrue(_run_now(ns["handle_support_pending_input"](SimpleNamespace(effective_user=SimpleNamespace(id=123), message=message), SimpleNamespace())))
        self.assertEqual(before, ns["get_support_ticket_pending"](123))
        back = next(button.callback_data for row in message.replies[-1][1]["reply_markup"].inline_keyboard
                    for button in row if button.text.startswith(("⬅", "🔙")))
        returned = click(tickets, back)
        self.assertEqual("ticket|mine|profile", _back(returned))
        self.assertIsNone(ns["get_support_ticket_pending"](123))
        self.assertEqual(foreign, ns["get_support_ticket_pending"](999))
        self.assertEqual([], calls)

    def test_malformed_detail_ids_alert_once_before_reads_or_pending_cleanup(self):
        ns, _, _, tickets, calls, reads, _, _ = _runtime()
        malformed_ids = (None, "", "-1", "²", "٩٠١", "901.0", "9223372036854775808", "9" * 30)
        for action in ("pv", "av"):
            ns["is_admin_user"] = lambda _uid, route_action=action: route_action == "av"
            for token in malformed_ids:
                with self.subTest(action=action, token=token):
                    reads.clear()
                    calls.clear()
                    ns["set_support_ticket_pending"](123, "awaiting_message", category="other")
                    ns["set_support_ticket_pending"](999, "awaiting_message", category="foreign")
                    actor_pending = dict(ns["get_support_ticket_pending"](123))
                    foreign_pending = dict(ns["get_support_ticket_pending"](999))
                    callback = f"ticket|{action}" if token is None else f"ticket|{action}|{token}"
                    query = _dispatch_immediate(tickets, callback)
                    self.assertEqual(1, len(query.answers))
                    self.assertTrue(query.answers[0][1].get("show_alert"))
                    self.assertEqual([], query.edits)
                    self.assertEqual([], reads)
                    self.assertEqual([], calls)
                    self.assertEqual(actor_pending, ns["get_support_ticket_pending"](123))
                    self.assertEqual(foreign_pending, ns["get_support_ticket_pending"](999))

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
        for data, recovery in (
            ("ticket|pv|901|profile", "ticket|mine|profile"),
            ("ticket|summary|901|profile_result", "ticket|start"),
            ("ticket|reply_user|901|profile", "ticket|start"),
        ):
            query = click(tickets, data)
            self.assertEqual([((), {})], query.answers)
            self.assertEqual(1, len(query.edits))
            self.assertIn(ns["public_hub_copy"]("vi")["support_ticket_not_found"], query.edits[0][0])
            self.assertNotIn("FIXTURE-901", query.edits[0][0])
            self.assertNotIn("Fixture ticket", query.edits[0][0])
            self.assertEqual({recovery, "menu|main"}, {button.callback_data for button in buttons(query)})
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
