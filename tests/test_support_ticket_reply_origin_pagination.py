"""Regression for the admin Reply prompt Back target on a filtered ticket page."""

import asyncio
import html
import re
import time
import uuid
import unittest
from pathlib import Path
from types import SimpleNamespace


class _Button:
    def __init__(self, text, callback_data=None, url=None):
        self.text, self.callback_data, self.url = text, callback_data, url


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class _CallbackQueryHandler:
    def __init__(self, callback, pattern):
        self.callback, self.pattern = callback, re.compile(pattern)


class _Application:
    def __init__(self):
        self.handlers = []

    def add_handler(self, handler):
        self.handlers.append(handler)


class _Query:
    def __init__(self, data, user_id):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.answers = 0
        self.reply_markups = []

    async def answer(self, *_args, **_kwargs):
        self.answers += 1


def _actual_function_source(source, name):
    lines = source.splitlines()
    start = next(i for i, line in enumerate(lines) if re.match(rf"^(?:async )?def {re.escape(name)}\(", line))
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"^(?:async )?def \w+\(", lines[i])), len(lines))
    return "\n".join(lines[start:end]) + "\n"


def _load_actual_function(source, name, namespace):
    exec(compile(_actual_function_source(source, name), f"bot.py:{name}", "exec"), namespace)
    return namespace[name]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def _run_inert(coroutine):
    try:
        yielded = coroutine.send(None)
    except StopIteration as completed:
        return completed.value
    coroutine.close()
    raise AssertionError(f"No-I/O callback fixture unexpectedly yielded: {yielded!r}")


def _fixture(language_lookup=None, query_holder=None, ticket_lookup=None):
    admin_id, ticket_id = 4242, 9006
    ticket = {
        "id": ticket_id,
        "ticket_code": "TKT-9006",
        "category": "general_support",
        "priority": "high",
        "status": "new",
        "message": "Fixture ticket; no persistent record.",
        "created_at": "2026-10-01",
        "user_id": "fixture-customer",
    }
    page_tickets = [
        {"id": 9001 + i, "ticket_code": f"TKT-{9001 + i}", "category": "general_support", "user_id": "fixture-customer"}
        for i in range(6)
    ]
    edits, list_calls, user_pending = [], [], {}

    async def safe_edit_or_send(query, _text, *, reply_markup=None, **_kwargs):
        query.reply_markups.append(reply_markup)
        return None

    async def to_thread(function, *args, **kwargs):
        return function(*args, **kwargs)

    def list_support_tickets(**kwargs):
        list_calls.append(kwargs)
        return page_tickets

    namespace = {
        "asyncio": SimpleNamespace(to_thread=to_thread),
        "html": html,
        "time": time,
        "uuid": uuid,
        "USER_PENDING": user_pending,
        "SUPPORT_TICKET_TTL_SECONDS": 600,
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "normalize_user_language": lambda value: value,
        "get_user_language": language_lookup or (lambda _uid: "vi"),
        "public_hub_copy": lambda _lang: {
            "support_ticket_admin_only": "admin only",
            "support_ticket_action_unsupported": "unsupported",
        },
        "is_admin_user": lambda uid: uid == admin_id,
        "support_category_label": lambda category: category,
        "list_support_tickets": list_support_tickets,
        "get_support_ticket": ticket_lookup or (lambda value, *_args, **_kwargs: ticket if int(value) == ticket_id else None),
        "support_ticket_admin_text": lambda _ticket: "ticket detail",
        "safe_edit_or_send": safe_edit_or_send,
    }

    def resolve_support_ticket_once(ticket_id, _user_id):
        if int(ticket_id) != int(ticket["id"]):
            return None
        if str(ticket.get("status") or "").strip().lower() in {"resolved", "closed"}:
            return dict(ticket)
        updater = namespace.get("update_support_ticket")
        if not callable(updater):
            raise AssertionError("fixture Done route requires an inert update seam")
        return updater(ticket_id, status="resolved") or dict(ticket)

    namespace["resolve_support_ticket_once"] = resolve_support_ticket_once
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
    for name in (
        "support_ticket_pending_key",
        "set_support_ticket_pending",
        "get_support_ticket_pending",
        "clear_support_ticket_pending",
        "support_ticket_admin_keyboard",
        "support_admin_list_payload",
        "handle_support_pending_input",
        "handle_ticket_callback",
    ):
        _load_actual_function(source, name, namespace)

    registrations = [
        line.strip()
        for line in _actual_function_source(source, "lifespan").splitlines()
        if "tg_app.add_handler(CallbackQueryHandler(handle_ticket_callback," in line
    ]
    assert len(registrations) == 1
    application = _Application()
    exec(
        compile(registrations[0], "bot.py:ticket-registration", "exec"),
        {**namespace, "tg_app": application, "CallbackQueryHandler": _CallbackQueryHandler},
    )
    assert len(application.handlers) == 1
    handler = application.handlers[0]
    assert handler.callback is namespace["handle_ticket_callback"]

    async def press(data):
        query = _Query(data, admin_id)
        if query_holder is not None:
            query_holder.append(query)
        await handler.callback(SimpleNamespace(callback_query=query), SimpleNamespace())
        return query

    return namespace, handler, press, list_calls, admin_id, ticket_id


class AdminTicketReplyOriginPaginationTest(unittest.TestCase):
    def test_emitted_ticket_summary_back_acks_before_lookup_and_restores_summary(self):
        active_queries = []
        language_ack_counts = []
        ticket_ack_counts = []
        ticket = {
            "id": 9006,
            "ticket_code": "TKT-9006",
            "category": "general_support",
            "status": "new",
            "message": "Fixture ticket; no persistent record.",
        }

        def get_user_language(_uid):
            language_ack_counts.append(active_queries[-1].answers if active_queries else -1)
            return "vi"

        def get_ticket(ticket_id, user_id=None):
            ticket_ack_counts.append(active_queries[-1].answers if active_queries else -1)
            return ticket if int(ticket_id) == 9006 else None

        namespace, handler, press, _list_calls, _admin_id, ticket_id = _fixture(
            language_lookup=get_user_language,
            query_holder=active_queries,
            ticket_lookup=get_ticket,
        )
        namespace["public_hub_copy"] = lambda _lang: {
            "support_my_tickets": "My tickets",
            "support_ticket_list_empty": "No tickets",
            "support_ticket_list_recent": "Recent tickets",
            "support_ticket": "Ticket",
            "support_back": "Back",
            "main_menu": "Main",
            "support_ticket_add_message": "Reply",
            "support_ticket_add_attachment": "Attach",
            "support_ticket_mark_done": "Done",
        }
        namespace["list_support_tickets"] = lambda **_kwargs: [ticket]
        namespace["public_support_ticket_category_label"] = lambda value, _lang: value
        namespace["public_support_ticket_status_label"] = lambda value, _lang: value
        namespace["public_support_ticket_text"] = lambda _ticket, _lang: "ticket-detail"
        namespace["ui_text"] = lambda _lang, _key: "Back"
        namespace["support_ticket_created_text"] = lambda _ticket, _lang: "ticket-summary"
        namespace["support_ticket_created_keyboard"] = lambda _ticket_id, _lang: _Markup(
            [[_Button("View ticket", callback_data=f"ticket|pv|{_ticket_id}")]]
        )

        async def to_thread(function, *args, **kwargs):
            return function(*args, **kwargs)

        namespace["asyncio"] = SimpleNamespace(to_thread=to_thread)
        source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
        for name in (
            "public_support_ticket_list_keyboard",
            "support_ticket_detail_keyboard",
            "ticket_customer_origin_keyboard",
        ):
            _load_actual_function(source, name, namespace)
        _, list_markup = namespace["public_support_ticket_list_keyboard"](4242, "vi")
        result_list_markup = namespace["ticket_customer_origin_keyboard"](
            list_markup, "feedback_result", "vi"
        )
        preview_callback = next(
            callback for callback in _callbacks(result_list_markup)
            if callback == f"ticket|pv|{ticket_id}|feedback_result"
        )
        self.assertIsNotNone(handler.pattern.match(preview_callback))

        detail = _run_inert(press(preview_callback))
        summary_callback = next(
            callback for callback in _callbacks(detail.reply_markups[-1])
            if callback == f"ticket|summary|{ticket_id}|feedback_result"
        )
        summary = _run_inert(press(summary_callback))

        self.assertEqual(language_ack_counts, [1, 1])
        self.assertEqual(ticket_ack_counts, [1, 1])
        self.assertEqual(summary.answers, 1)
        self.assertEqual(_callbacks(summary.reply_markups[-1]), ["ticket|pv|9006|feedback_result"])

    def test_missing_emitted_ticket_summary_back_shows_recovery_after_ack(self):
        active_queries = []
        language_ack_counts = []
        ticket_ack_counts = []

        def get_user_language(_uid):
            language_ack_counts.append(active_queries[-1].answers if active_queries else -1)
            return "vi"

        def get_ticket(ticket_id, user_id=None):
            ticket_ack_counts.append(active_queries[-1].answers if active_queries else -1)
            return None

        namespace, handler, press, _list_calls, _admin_id, ticket_id = _fixture(
            language_lookup=get_user_language,
            query_holder=active_queries,
            ticket_lookup=get_ticket,
        )
        namespace["public_hub_copy"] = lambda _lang: {
            "support_my_tickets": "My tickets",
            "support_ticket_not_found": "Ticket not found",
            "support_ticket": "Ticket",
            "main_menu": "Main",
            "support_back": "Back",
        }
        namespace["support_ticket_menu_text"] = lambda _lang: "ticket-menu"
        namespace["support_ticket_menu_keyboard"] = lambda _lang: _Markup(
            [[_Button("My tickets", callback_data="ticket|mine")]]
        )

        async def to_thread(function, *args, **kwargs):
            return function(*args, **kwargs)

        namespace["asyncio"] = SimpleNamespace(to_thread=to_thread)

        result = _run_inert(press(f"ticket|summary|{ticket_id}|feedback_result"))

        self.assertEqual(language_ack_counts, [1])
        self.assertEqual(ticket_ack_counts, [1])
        self.assertEqual(result.answers, 1)
        self.assertEqual(result.reply_markups[-1].inline_keyboard[0][0].callback_data, "ticket|start")
        self.assertEqual(result.reply_markups[-1].inline_keyboard[1][0].callback_data, "menu|main")

    def test_emitted_ticket_reply_acks_before_lookup_and_preserves_prompt_back(self):
        active_queries = []
        language_ack_counts = []
        ticket_ack_counts = []
        ticket = {
            "id": 9006,
            "ticket_code": "TKT-9006",
            "category": "general_support",
            "status": "new",
            "message": "Fixture ticket; no persistent record.",
        }

        def get_user_language(_uid):
            language_ack_counts.append(active_queries[-1].answers if active_queries else -1)
            return "vi"

        def get_ticket(ticket_id, user_id=None):
            ticket_ack_counts.append(active_queries[-1].answers if active_queries else -1)
            return ticket if int(ticket_id) == 9006 else None

        namespace, handler, press, _list_calls, admin_id, ticket_id = _fixture(
            language_lookup=get_user_language,
            query_holder=active_queries,
            ticket_lookup=get_ticket,
        )
        namespace["public_hub_copy"] = lambda _lang: {
            "support_ticket_back_to_ticket": "Back to ticket",
            "support_ticket_reply_prompt": "Reply prompt",
            "support_ticket_add_message": "Reply",
            "support_ticket_add_attachment": "Attach",
            "support_ticket_mark_done": "Done",
            "support_my_tickets": "My tickets",
            "support_back": "Back",
            "support_ticket": "Ticket",
            "main_menu": "Main",
        }
        namespace["support_flow_back_keyboard"] = lambda callback, label, lang="vi": _Markup(
            [[_Button(label, callback_data=callback)]]
        )

        async def to_thread(function, *args, **kwargs):
            return function(*args, **kwargs)

        namespace["asyncio"] = SimpleNamespace(to_thread=to_thread)
        _load_actual_function(
            (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8"),
            "support_ticket_detail_keyboard",
            namespace,
        )
        emitted = next(
            callback for callback in _callbacks(namespace["support_ticket_detail_keyboard"](ticket, "vi"))
            if callback == f"ticket|reply_user|{ticket_id}"
        )
        self.assertIsNotNone(handler.pattern.match(emitted))

        result = _run_inert(press(emitted))

        pending = namespace["get_support_ticket_pending"](admin_id)
        self.assertEqual(language_ack_counts, [1])
        self.assertEqual(ticket_ack_counts, [1])
        self.assertEqual(result.answers, 1)
        self.assertEqual(pending["step"], "awaiting_ticket_reply")
        self.assertEqual(pending["ticket_id"], "9006")
        self.assertEqual(_callbacks(result.reply_markups[-1]), ["ticket|pv|9006"])

    def test_missing_emitted_ticket_reply_shows_recovery_after_ack(self):
        active_queries = []
        language_ack_counts = []
        ticket_ack_counts = []

        def get_user_language(_uid):
            language_ack_counts.append(active_queries[-1].answers if active_queries else -1)
            return "vi"

        def get_ticket(ticket_id, user_id=None):
            ticket_ack_counts.append(active_queries[-1].answers if active_queries else -1)
            return None

        namespace, handler, press, _list_calls, admin_id, ticket_id = _fixture(
            language_lookup=get_user_language,
            query_holder=active_queries,
            ticket_lookup=get_ticket,
        )
        namespace["public_hub_copy"] = lambda _lang: {
            "support_ticket_not_found": "Ticket not found",
            "support_ticket_add_message": "Reply",
            "support_ticket_add_attachment": "Attach",
            "support_ticket_mark_done": "Done",
            "support_my_tickets": "My tickets",
            "support_back": "Back",
            "support_ticket": "Ticket",
            "main_menu": "Main",
        }

        async def to_thread(function, *args, **kwargs):
            return function(*args, **kwargs)

        namespace["asyncio"] = SimpleNamespace(to_thread=to_thread)
        _load_actual_function(
            (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8"),
            "support_ticket_detail_keyboard",
            namespace,
        )
        emitted = next(
            callback for callback in _callbacks(namespace["support_ticket_detail_keyboard"](
                {"id": ticket_id}, "vi"
            ))
            if callback == f"ticket|reply_user|{ticket_id}"
        )
        self.assertIsNotNone(handler.pattern.match(emitted))

        result = _run_inert(press(emitted))

        self.assertEqual(language_ack_counts, [1])
        self.assertEqual(ticket_ack_counts, [1])
        self.assertEqual(result.answers, 1)
        self.assertIsNone(namespace["get_support_ticket_pending"](admin_id))
        self.assertEqual(result.reply_markups[-1].inline_keyboard[0][0].callback_data, "ticket|start")
        self.assertEqual(result.reply_markups[-1].inline_keyboard[1][0].callback_data, "menu|main")

    def test_emitted_ticket_attach_acks_before_lookup_and_preserves_prompt_back(self):
        active_queries = []
        language_ack_counts = []
        ticket_ack_counts = []
        ticket = {
            "id": 9006,
            "ticket_code": "TKT-9006",
            "category": "general_support",
            "status": "new",
            "message": "Fixture ticket; no persistent record.",
        }

        def get_user_language(_uid):
            language_ack_counts.append(active_queries[-1].answers if active_queries else -1)
            return "vi"

        def get_ticket(ticket_id, user_id=None):
            ticket_ack_counts.append(active_queries[-1].answers if active_queries else -1)
            return ticket if int(ticket_id) == 9006 else None

        namespace, handler, press, _list_calls, admin_id, ticket_id = _fixture(
            language_lookup=get_user_language,
            query_holder=active_queries,
            ticket_lookup=get_ticket,
        )
        namespace["public_hub_copy"] = lambda _lang: {
            "support_ticket_attachment_prompt": "Attach prompt",
            "support_ticket_back_to_ticket": "Back to ticket",
            "support_ticket_add_message": "Reply",
            "support_ticket_add_attachment": "Attach",
            "support_ticket_mark_done": "Done",
            "support_my_tickets": "My tickets",
            "support_back": "Back",
            "support_ticket": "Ticket",
            "main_menu": "Main",
        }

        async def to_thread(function, *args, **kwargs):
            return function(*args, **kwargs)

        namespace["asyncio"] = SimpleNamespace(to_thread=to_thread)
        _load_actual_function(
            (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8"),
            "support_ticket_detail_keyboard",
            namespace,
        )
        emitted = next(
            callback for callback in _callbacks(namespace["support_ticket_detail_keyboard"](ticket, "vi"))
            if callback == f"ticket|attach|{ticket_id}"
        )
        self.assertIsNotNone(handler.pattern.match(emitted))

        result = _run_inert(press(emitted))

        pending = namespace["get_support_ticket_pending"](admin_id)
        self.assertEqual(language_ack_counts, [1])
        self.assertEqual(ticket_ack_counts, [1])
        self.assertEqual(result.answers, 1)
        self.assertEqual(pending["step"], "awaiting_attachment")
        self.assertEqual(pending["ticket_id"], "9006")
        self.assertEqual(_callbacks(result.reply_markups[-1]), ["ticket|pv|9006", "menu|main"])

    def test_missing_emitted_ticket_attach_shows_recovery_after_ack(self):
        active_queries = []
        language_ack_counts = []
        ticket_ack_counts = []

        def get_user_language(_uid):
            language_ack_counts.append(active_queries[-1].answers if active_queries else -1)
            return "vi"

        def get_ticket(ticket_id, user_id=None):
            ticket_ack_counts.append(active_queries[-1].answers if active_queries else -1)
            return None

        namespace, handler, press, _list_calls, admin_id, ticket_id = _fixture(
            language_lookup=get_user_language,
            query_holder=active_queries,
            ticket_lookup=get_ticket,
        )
        namespace["public_hub_copy"] = lambda _lang: {
            "support_ticket_not_found": "Ticket not found",
            "support_ticket_add_message": "Reply",
            "support_ticket_add_attachment": "Attach",
            "support_ticket_mark_done": "Done",
            "support_my_tickets": "My tickets",
            "support_back": "Back",
            "support_ticket": "Ticket",
            "main_menu": "Main",
        }

        async def to_thread(function, *args, **kwargs):
            return function(*args, **kwargs)

        namespace["asyncio"] = SimpleNamespace(to_thread=to_thread)
        _load_actual_function(
            (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8"),
            "support_ticket_detail_keyboard",
            namespace,
        )
        emitted = next(
            callback for callback in _callbacks(namespace["support_ticket_detail_keyboard"](
                {"id": ticket_id}, "vi"
            ))
            if callback == f"ticket|attach|{ticket_id}"
        )
        self.assertIsNotNone(handler.pattern.match(emitted))

        result = _run_inert(press(emitted))

        self.assertEqual(language_ack_counts, [1])
        self.assertEqual(ticket_ack_counts, [1])
        self.assertEqual(result.answers, 1)
        self.assertIsNone(namespace["get_support_ticket_pending"](admin_id))
        self.assertEqual(result.reply_markups[-1].inline_keyboard[0][0].callback_data, "ticket|start")
        self.assertEqual(result.reply_markups[-1].inline_keyboard[1][0].callback_data, "menu|main")

    def test_emitted_ticket_done_acks_before_read_and_updates_once(self):
        active_queries = []
        language_ack_counts = []
        ticket_ack_counts = []
        update_calls = []
        ticket = {
            "id": 9006,
            "ticket_code": "TKT-9006",
            "category": "general_support",
            "status": "new",
            "message": "Fixture ticket; no persistent record.",
        }

        def get_user_language(_uid):
            language_ack_counts.append(active_queries[-1].answers if active_queries else -1)
            return "vi"

        def get_ticket(ticket_id, user_id=None):
            ticket_ack_counts.append(active_queries[-1].answers if active_queries else -1)
            return ticket if int(ticket_id) == 9006 else None

        def update_ticket(ticket_id, **fields):
            update_calls.append((ticket_id, fields))
            return {**ticket, **fields}

        namespace, handler, press, _list_calls, admin_id, ticket_id = _fixture(
            language_lookup=get_user_language,
            query_holder=active_queries,
            ticket_lookup=get_ticket,
        )
        namespace["update_support_ticket"] = update_ticket
        namespace["ticket_customer_origin_keyboard"] = lambda markup, _origin, _lang, **_kwargs: markup
        namespace["public_hub_copy"] = lambda _lang: {
            "support_ticket_back_to_ticket": "Ticket",
            "support_ticket_done_success": "Done",
            "support_ticket_add_message": "Reply",
            "support_ticket_add_attachment": "Attach",
            "support_ticket_mark_done": "Done",
            "support_my_tickets": "My tickets",
            "support_back": "Back",
            "main_menu": "Main",
        }

        async def to_thread(function, *args, **kwargs):
            return function(*args, **kwargs)

        namespace["asyncio"] = SimpleNamespace(to_thread=to_thread)
        _load_actual_function(
            (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8"),
            "support_ticket_detail_keyboard",
            namespace,
        )
        emitted = next(
            callback for callback in _callbacks(namespace["support_ticket_detail_keyboard"](ticket, "vi"))
            if callback == f"ticket|done|{ticket_id}"
        )
        self.assertIsNotNone(handler.pattern.match(emitted))

        result = _run_inert(press(emitted))

        self.assertEqual(language_ack_counts, [1])
        self.assertEqual(ticket_ack_counts, [1])
        self.assertEqual(result.answers, 1)
        self.assertEqual(update_calls, [(ticket_id, {"status": "resolved"})])
        self.assertEqual(
            _callbacks(result.reply_markups[-1]),
            ["ticket|mine", "support|start", "menu|main"],
        )
        self.assertIsNone(namespace["get_support_ticket_pending"](admin_id))

    def test_missing_emitted_ticket_done_recovers_after_ack_without_update(self):
        active_queries = []
        language_ack_counts = []
        ticket_ack_counts = []
        update_calls = []

        def get_user_language(_uid):
            language_ack_counts.append(active_queries[-1].answers if active_queries else -1)
            return "vi"

        def get_ticket(ticket_id, user_id=None):
            ticket_ack_counts.append(active_queries[-1].answers if active_queries else -1)
            return None

        namespace, handler, press, _list_calls, admin_id, ticket_id = _fixture(
            language_lookup=get_user_language,
            query_holder=active_queries,
            ticket_lookup=get_ticket,
        )
        namespace["update_support_ticket"] = lambda ticket_id, **fields: update_calls.append((ticket_id, fields))
        namespace["public_hub_copy"] = lambda _lang: {
            "support_ticket_not_found": "Ticket not found",
            "support_ticket_add_message": "Reply",
            "support_ticket_add_attachment": "Attach",
            "support_ticket_mark_done": "Done",
            "support_my_tickets": "My tickets",
            "support_back": "Back",
            "support_ticket": "Ticket",
            "main_menu": "Main",
        }

        async def to_thread(function, *args, **kwargs):
            return function(*args, **kwargs)

        namespace["asyncio"] = SimpleNamespace(to_thread=to_thread)
        _load_actual_function(
            (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8"),
            "support_ticket_detail_keyboard",
            namespace,
        )
        emitted = next(
            callback for callback in _callbacks(namespace["support_ticket_detail_keyboard"](
                {"id": ticket_id}, "vi"
            ))
            if callback == f"ticket|done|{ticket_id}"
        )
        self.assertIsNotNone(handler.pattern.match(emitted))

        result = _run_inert(press(emitted))

        self.assertEqual(language_ack_counts, [1])
        self.assertEqual(ticket_ack_counts, [1])
        self.assertEqual(result.answers, 1)
        self.assertEqual(update_calls, [])
        self.assertIsNone(namespace["get_support_ticket_pending"](admin_id))
        self.assertEqual(result.reply_markups[-1].inline_keyboard[0][0].callback_data, "ticket|start")
        self.assertEqual(result.reply_markups[-1].inline_keyboard[1][0].callback_data, "menu|main")

    def test_emitted_ticket_preview_acks_before_read_and_preserves_detail(self):
        active_queries = []
        language_ack_counts = []
        lookup_ack_counts = []
        ticket = {
            "id": 9006,
            "ticket_code": "TKT-9006",
            "category": "general_support",
            "status": "new",
            "message": "Fixture ticket; no persistent record.",
        }

        def get_ticket(ticket_id, user_id=None):
            lookup_ack_counts.append(active_queries[-1].answers if active_queries else -1)
            return ticket if int(ticket_id) == 9006 else None

        def get_user_language(_uid):
            language_ack_counts.append(active_queries[-1].answers if active_queries else -1)
            return "vi"

        namespace, handler, press, _list_calls, _admin_id, ticket_id = _fixture(
            language_lookup=get_user_language,
            query_holder=active_queries,
            ticket_lookup=get_ticket,
        )
        namespace["public_hub_copy"] = lambda _lang: {
            "support_my_tickets": "My tickets",
            "support_ticket_list_empty": "No tickets",
            "support_ticket_list_recent": "Recent tickets",
            "support_ticket": "Ticket",
            "support_back": "Back",
            "main_menu": "Main",
        }
        namespace["list_support_tickets"] = lambda **_kwargs: [ticket]
        namespace["public_support_ticket_category_label"] = lambda value, _lang: value
        namespace["public_support_ticket_status_label"] = lambda value, _lang: value
        namespace["public_support_ticket_text"] = lambda _ticket, _lang: "ticket-detail"
        namespace["support_ticket_detail_keyboard"] = lambda _ticket, _lang: "detail-keyboard"
        thread_calls = []

        async def to_thread(function, *args, **kwargs):
            thread_calls.append((function.__name__, args))
            return function(*args, **kwargs)

        namespace["asyncio"] = SimpleNamespace(to_thread=to_thread)
        source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
        _load_actual_function(source, "public_support_ticket_list_keyboard", namespace)
        _, list_markup = namespace["public_support_ticket_list_keyboard"](4242, "vi")
        emitted = next(callback for callback in _callbacks(list_markup) if callback == f"ticket|pv|{ticket_id}")
        self.assertIsNotNone(handler.pattern.match(emitted))

        result = _run_inert(press(emitted))

        self.assertEqual(language_ack_counts, [1])
        self.assertEqual(lookup_ack_counts, [1])
        self.assertEqual(thread_calls, [("get_ticket", (9006, 4242))])
        self.assertEqual(result.answers, 1)
        self.assertEqual(result.reply_markups, ["detail-keyboard"])

    def test_missing_emitted_ticket_preview_keeps_back_and_home_after_ack(self):
        active_queries = []
        language_ack_counts = []
        lookup_ack_counts = []

        def missing_ticket(ticket_id, user_id=None):
            lookup_ack_counts.append(active_queries[-1].answers if active_queries else -1)
            return None

        def get_user_language(_uid):
            language_ack_counts.append(active_queries[-1].answers if active_queries else -1)
            return "vi"

        namespace, handler, press, _list_calls, _admin_id, ticket_id = _fixture(
            language_lookup=get_user_language,
            query_holder=active_queries,
            ticket_lookup=missing_ticket,
        )
        namespace["public_hub_copy"] = lambda _lang: {
            "support_my_tickets": "My tickets",
            "support_ticket_list_empty": "No tickets",
            "support_ticket_list_recent": "Recent tickets",
            "support_ticket": "Ticket",
            "support_ticket_not_found": "Ticket not found",
            "support_back": "Back",
            "main_menu": "Main",
        }
        namespace["list_support_tickets"] = lambda **_kwargs: [{
            "id": ticket_id,
            "ticket_code": "TKT-9006",
            "category": "general_support",
            "status": "new",
        }]
        namespace["public_support_ticket_category_label"] = lambda value, _lang: value
        namespace["public_support_ticket_status_label"] = lambda value, _lang: value

        async def to_thread(function, *args, **kwargs):
            return function(*args, **kwargs)

        namespace["asyncio"] = SimpleNamespace(to_thread=to_thread)
        source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
        _load_actual_function(source, "public_support_ticket_list_keyboard", namespace)
        _, list_markup = namespace["public_support_ticket_list_keyboard"](4242, "vi")
        emitted = next(callback for callback in _callbacks(list_markup) if callback == f"ticket|pv|{ticket_id}")
        self.assertIsNotNone(handler.pattern.match(emitted))

        result = _run_inert(press(emitted))

        self.assertEqual(language_ack_counts, [1])
        self.assertEqual(lookup_ack_counts, [1])
        self.assertEqual(result.answers, 1)
        self.assertEqual(_callbacks(result.reply_markups[-1]), ["ticket|mine", "menu|main"])
        self.assertEqual(result.reply_markups[-1].inline_keyboard[0][0].text, "📂 My tickets")

    def test_emitted_ticket_back_acks_before_language_lookup(self):
        active_queries = []
        lookup_ack_counts = []

        def get_user_language(_uid):
            lookup_ack_counts.append(active_queries[-1].answers if active_queries else -1)
            return "vi"

        namespace, handler, press, _list_calls, _admin_id, _ticket_id = _fixture(
            language_lookup=get_user_language,
            query_holder=active_queries,
        )
        namespace["public_hub_copy"] = lambda _lang: {"support_back": "Back", "main_menu": "Main"}
        namespace["support_ticket_menu_text"] = lambda _lang: "ticket-menu"
        namespace["support_ticket_menu_keyboard"] = lambda _lang: "ticket-keyboard"
        _load_actual_function(
            (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8"),
            "support_ticket_input_keyboard",
            namespace,
        )
        emitted = _callbacks(namespace["support_ticket_input_keyboard"]("vi"))
        self.assertIn("ticket|start", emitted)
        self.assertIsNotNone(handler.pattern.match("ticket|start"))

        result = _run_inert(press("ticket|start"))

        self.assertEqual(lookup_ack_counts, [1])
        self.assertEqual(result.answers, 1)
        self.assertEqual(result.reply_markups, ["ticket-keyboard"])

    def test_reply_prompt_back_returns_to_the_same_filtered_page(self):
        namespace, handler, press, list_calls, _admin_id, ticket_id = _fixture()
        self.assertIsNotNone(handler.pattern.match("ticket|reply|9006|high|6"))

        _list_text, list_markup = namespace["support_admin_list_payload"]("high", 6)
        detail_callback = next(cb for cb in _callbacks(list_markup) if cb.startswith(f"ticket|av|{ticket_id}|"))
        detail = _run_inert(press(detail_callback))
        self.assertEqual(detail.answers, 1)
        detail_markup = detail.reply_markups[-1]
        reply_callback = next(cb for cb in _callbacks(detail_markup) if cb.startswith(f"ticket|reply|{ticket_id}"))
        self.assertEqual(reply_callback, "ticket|reply|9006|high|6")

        prompt = _run_inert(press(reply_callback))
        self.assertEqual(prompt.answers, 1)
        pending = namespace["get_support_ticket_pending"](4242)
        self.assertEqual((pending["source"], pending["list_offset"]), ("high", "6"))
        back_callback = next(cb for cb in _callbacks(prompt.reply_markups[-1]) if cb.startswith("ticket|av|9006|"))
        self.assertEqual(back_callback, "ticket|av|9006|high|6")

        returned_detail = _run_inert(press(back_callback))
        self.assertIsNone(namespace["get_support_ticket_pending"](4242))
        list_callback = next(cb for cb in _callbacks(returned_detail.reply_markups[-1]) if cb.startswith("ticket|al|"))
        self.assertEqual(list_callback, "ticket|al|high|6")
        _run_inert(press(list_callback))
        self.assertEqual(list_calls[-1], {"limit": 6, "offset": 6, "high_priority": True})

    def test_reply_preview_back_returns_to_the_same_filtered_page_without_sending(self):
        namespace, handler, press, list_calls, admin_id, ticket_id = _fixture()
        _list_text, list_markup = namespace["support_admin_list_payload"]("high", 6)
        detail_callback = next(cb for cb in _callbacks(list_markup) if cb.startswith(f"ticket|av|{ticket_id}|"))
        detail = _run_inert(press(detail_callback))
        reply_callback = next(cb for cb in _callbacks(detail.reply_markups[-1]) if cb.startswith(f"ticket|reply|{ticket_id}"))
        prompt = _run_inert(press(reply_callback))

        replies = []

        async def reply_text(text, **kwargs):
            replies.append((text, kwargs))

        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=admin_id),
            message=SimpleNamespace(text="Fixture reply text", reply_text=reply_text),
        )
        send_attempts = []
        context = SimpleNamespace(bot=SimpleNamespace(send_message=lambda **kwargs: send_attempts.append(kwargs)))
        handled = _run_inert(namespace["handle_support_pending_input"](update, context))
        self.assertTrue(handled)
        self.assertEqual(len(replies), 1)
        preview_markup = replies[-1][1]["reply_markup"]
        back_callback = next(cb for cb in _callbacks(preview_markup) if cb.startswith(f"ticket|av|{ticket_id}|"))
        self.assertEqual(back_callback, "ticket|av|9006|high|6")

        returned_detail = _run_inert(press(back_callback))
        self.assertIsNone(namespace["get_support_ticket_pending"](admin_id))
        list_callback = next(cb for cb in _callbacks(returned_detail.reply_markups[-1]) if cb.startswith("ticket|al|"))
        self.assertEqual(list_callback, "ticket|al|high|6")
        _run_inert(press(list_callback))
        self.assertEqual(list_calls[-1], {"limit": 6, "offset": 6, "high_priority": True})
        self.assertEqual(send_attempts, [])

    def test_emitted_admin_ticket_detail_skips_language_lookup_and_restores_list(self):
        active_queries = []
        language_ack_counts = []
        ticket_ack_counts = []
        ticket = {
            "id": 9006,
            "ticket_code": "TKT-9006",
            "category": "general_support",
            "priority": "high",
            "status": "new",
            "user_id": "fixture-customer",
            "message": "Fixture ticket; no persistent record.",
        }

        def get_user_language(_uid):
            language_ack_counts.append(active_queries[-1].answers if active_queries else -1)
            return "vi"

        def get_ticket(ticket_id, user_id=None):
            ticket_ack_counts.append(active_queries[-1].answers if active_queries else -1)
            return ticket if int(ticket_id) == 9006 else None

        namespace, handler, press, _list_calls, _admin_id, ticket_id = _fixture(
            language_lookup=get_user_language,
            query_holder=active_queries,
            ticket_lookup=get_ticket,
        )
        namespace["support_ticket_admin_text"] = lambda _ticket: "admin-ticket-detail"

        async def to_thread(function, *args, **kwargs):
            return function(*args, **kwargs)

        namespace["asyncio"] = SimpleNamespace(to_thread=to_thread)
        _text, list_markup = namespace["support_admin_list_payload"]("high", 6)
        emitted = next(
            callback for callback in _callbacks(list_markup)
            if callback == f"ticket|av|{ticket_id}|high|6"
        )
        self.assertIsNotNone(handler.pattern.match(emitted))

        result = _run_inert(press(emitted))

        self.assertEqual(language_ack_counts, [])
        self.assertEqual(ticket_ack_counts, [1])
        self.assertEqual(result.answers, 1)
        self.assertIn("ticket|al|high|6", _callbacks(result.reply_markups[-1]))
        self.assertIn("menu|main", _callbacks(result.reply_markups[-1]))

    def test_missing_emitted_admin_ticket_detail_recovers_after_ack(self):
        active_queries = []
        language_ack_counts = []
        ticket_ack_counts = []
        ticket = {
            "id": 9006,
            "ticket_code": "TKT-9006",
            "category": "general_support",
            "priority": "high",
            "status": "new",
            "user_id": "fixture-customer",
        }

        def get_user_language(_uid):
            language_ack_counts.append(active_queries[-1].answers if active_queries else -1)
            return "vi"

        def get_ticket(ticket_id, user_id=None):
            ticket_ack_counts.append(active_queries[-1].answers if active_queries else -1)
            return None

        namespace, handler, press, _list_calls, _admin_id, ticket_id = _fixture(
            language_lookup=get_user_language,
            query_holder=active_queries,
            ticket_lookup=get_ticket,
        )
        async def to_thread(function, *args, **kwargs):
            return function(*args, **kwargs)

        namespace["asyncio"] = SimpleNamespace(to_thread=to_thread)
        _text, list_markup = namespace["support_admin_list_payload"]("high", 6)
        emitted = next(
            callback for callback in _callbacks(list_markup)
            if callback == f"ticket|av|{ticket_id}|high|6"
        )
        self.assertIsNotNone(handler.pattern.match(emitted))

        result = _run_inert(press(emitted))

        self.assertEqual(language_ack_counts, [])
        self.assertEqual(ticket_ack_counts, [1])
        self.assertEqual(result.answers, 1)
        self.assertEqual(result.reply_markups[-1].inline_keyboard[0][0].callback_data, "ticket|al|high|6")
        self.assertEqual(result.reply_markups[-1].inline_keyboard[1][0].callback_data, "menu|main")

    def test_unauthorized_emitted_admin_ticket_detail_keeps_denial_before_read(self):
        ticket_reads = []
        namespace, handler, press, _list_calls, _admin_id, ticket_id = _fixture(
            ticket_lookup=lambda ticket_id, user_id=None: ticket_reads.append(ticket_id)
        )
        namespace["is_admin_user"] = lambda _uid: False
        namespace["public_hub_copy"] = lambda _lang: {
            "support_ticket_admin_only": "admin only",
        }
        _text, list_markup = namespace["support_admin_list_payload"]("high", 6)
        emitted = next(
            callback for callback in _callbacks(list_markup)
            if callback == f"ticket|av|{ticket_id}|high|6"
        )
        self.assertIsNotNone(handler.pattern.match(emitted))

        result = _run_inert(press(emitted))

        self.assertEqual(result.answers, 1)
        self.assertTrue(result.reply_markups == [])
        self.assertEqual(ticket_reads, [])

    def test_emitted_admin_ticket_next_page_acks_before_list_read(self):
        active_queries = []
        reads = []
        offloads = []
        namespace, handler, press, _list_calls, _admin_id, _ticket_id = _fixture(
            query_holder=active_queries
        )
        _text, first_page = namespace["support_admin_list_payload"]("high", 0)
        emitted = next(
            callback for callback in _callbacks(first_page)
            if callback == "ticket|al|high|6"
        )
        self.assertIsNotNone(handler.pattern.match(emitted))
        list_support_tickets = namespace["list_support_tickets"]

        def tracked_list_support_tickets(**kwargs):
            reads.append((active_queries[-1].answers if active_queries else -1, kwargs))
            return list_support_tickets(**kwargs)

        async def to_thread(function, *args, **kwargs):
            offloads.append((function.__name__, active_queries[-1].answers))
            return function(*args, **kwargs)

        namespace["list_support_tickets"] = tracked_list_support_tickets
        namespace["asyncio"] = SimpleNamespace(to_thread=to_thread)

        result = _run_inert(press(emitted))

        self.assertEqual(result.answers, 1)
        self.assertEqual(offloads, [("support_admin_list_payload", 1)])
        self.assertEqual(reads, [(1, {"limit": 6, "offset": 6, "high_priority": True})])
        self.assertIn("ticket|al|high|12", _callbacks(result.reply_markups[-1]))

    def test_unauthorized_admin_ticket_next_page_stops_before_list_read(self):
        active_queries = []
        namespace, handler, press, _list_calls, _admin_id, _ticket_id = _fixture(
            query_holder=active_queries
        )
        _text, first_page = namespace["support_admin_list_payload"]("high", 0)
        emitted = next(
            callback for callback in _callbacks(first_page)
            if callback == "ticket|al|high|6"
        )
        self.assertIsNotNone(handler.pattern.match(emitted))
        namespace["is_admin_user"] = lambda _uid: False
        reads = []
        list_support_tickets = namespace["list_support_tickets"]

        def tracked_list_support_tickets(**kwargs):
            reads.append(kwargs)
            return list_support_tickets(**kwargs)

        namespace["list_support_tickets"] = tracked_list_support_tickets

        result = _run_inert(press(emitted))

        self.assertEqual(result.answers, 1)
        self.assertEqual(reads, [])
        self.assertEqual(result.reply_markups, [])

    def test_emitted_admin_search_text_offloads_read_and_keeps_other_pending_state(self):
        namespace, _handler, press, list_calls, admin_id, _ticket_id = _fixture()
        source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
        _load_actual_function(source, "support_admin_menu_keyboard", namespace)
        _load_actual_function(source, "support_admin_search_payload", namespace)
        code_lookups, offloads, replies = [], [], []
        namespace["get_support_ticket_by_code"] = lambda code: code_lookups.append(code) or None
        namespace["set_support_ticket_pending"](9999, "admin_search", source="all")
        other_pending = dict(namespace["get_support_ticket_pending"](9999))

        async def to_thread(function, *args, **kwargs):
            offloads.append((function.__name__, args))
            return function(*args, **kwargs)

        namespace["asyncio"] = SimpleNamespace(to_thread=to_thread)
        search_button = next(
            button for row in namespace["support_admin_menu_keyboard"]().inline_keyboard
            for button in row if button.text == "🔍 Tìm ticket"
        )
        self.assertEqual("ticket|asearch|all", search_button.callback_data)

        def run_immediate(coroutine):
            try:
                coroutine.send(None)
            except StopIteration as result:
                return result.value
            coroutine.close()
            self.fail("fixture unexpectedly yielded I/O")

        prompt = run_immediate(press(search_button.callback_data))
        prompt_callbacks = _callbacks(prompt.reply_markups[-1])
        self.assertEqual("admin_search", namespace["get_support_ticket_pending"](admin_id)["step"])
        self.assertIn("ticket|admin", prompt_callbacks)
        self.assertIn("menu|main", prompt_callbacks)

        class IncomingMessage:
            text = "TKT-FIXTURE-LOOKUP"

            async def reply_text(self, text, **kwargs):
                replies.append((text, kwargs))

        incoming = SimpleNamespace(
            effective_user=SimpleNamespace(id=admin_id),
            message=IncomingMessage(),
        )
        handled = run_immediate(namespace["handle_support_pending_input"](incoming, SimpleNamespace()))

        self.assertTrue(handled)
        self.assertEqual([("support_admin_search_payload", ("TKT-FIXTURE-LOOKUP",))], offloads)
        self.assertEqual(["TKT-FIXTURE-LOOKUP"], code_lookups)
        self.assertEqual([{"search": "TKT-FIXTURE-LOOKUP", "limit": 10}], list_calls)
        self.assertIsNone(namespace["get_support_ticket_pending"](admin_id))
        self.assertEqual(other_pending, namespace["get_support_ticket_pending"](9999))
        result_callbacks = _callbacks(replies[-1][1]["reply_markup"])
        self.assertIn("ticket|admin", result_callbacks)
        self.assertIn("menu|main", result_callbacks)


if __name__ == "__main__":
    unittest.main()
