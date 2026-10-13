"""Admin action buttons through their registered ticket handler, without I/O."""
import html
import re
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest


SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
ACTIONS = ("reply", "ask", "suggest", "note", "assign", "lead", "st")


def _run_inert(coroutine):
    try:
        yielded = coroutine.send(None)
    except StopIteration as completed:
        return completed.value
    coroutine.close()
    raise AssertionError(f"No-I/O handler unexpectedly yielded: {yielded!r}")


def _function(name):
    start = re.search(rf"(?m)^(?:async )?def {name}\(", SOURCE)
    assert start, name
    following = re.search(r"(?m)^(?:async )?def \w+\(", SOURCE[start.end():])
    end = start.end() + following.start() if following else len(SOURCE)
    return SOURCE[start.start():end]


CODE = compile(
    "from __future__ import annotations\n"
    + _function("support_ticket_pending_key")
    + _function("set_support_ticket_pending")
    + _function("clear_support_ticket_pending")
    + _function("support_admin_menu_keyboard")
    + _function("support_ticket_admin_keyboard")
    + _function("handle_ticket_callback"),
    "bot.py:ticket action source",
    "exec",
)


class _Button:
    def __init__(self, text, callback_data):
        self.text, self.callback_data = text, callback_data


class _Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


def _click(
    action, *, exists=True, admin=True, disappear_on_update=False,
    read_dispatch=None, status="resolved",
):
    ticket = {
        "id": 41, "ticket_code": "TA-TEST-41", "category": "lead_consulting",
        "message": "test", "status": "new", "admin_note": "",
        "assigned_admin_id": None,
    }
    effects, pending, edits, notices = [], [], [], []
    user_pending_store = {}
    actual_pending_helpers = {}

    def get_language(_uid):
        return "vi"

    def get_ticket(ticket_id):
        assert ticket_id == ticket["id"]
        effects.append("get")
        return dict(ticket) if exists else None

    def update_ticket(ticket_id, **fields):
        assert ticket_id == ticket["id"]
        effects.append("update")
        if not exists or disappear_on_update:
            return None
        ticket.update(fields)
        return dict(ticket)

    def set_pending(*args, **fields):
        effects.append("pending")
        pending.append((args, fields))
        return actual_pending_helpers["set"](*args, **fields)

    def clear_pending(uid):
        effects.append("clear_pending")
        return actual_pending_helpers["clear"](uid)

    async def read_offload(helper, *args, **kwargs):
        assert helper in {get_language, get_ticket}
        if read_dispatch is not None:
            read_dispatch.append("language" if helper is get_language else "ticket")
        return helper(*args, **kwargs)

    async def render(_query, text, **kwargs):
        effects.append("render")
        edits.append((text, kwargs.get("reply_markup")))

    async def reply_text(text):
        effects.append("notice")
        notices.append(text)

    class Query:
        from_user = SimpleNamespace(id=501)

        def __init__(self, data):
            self.data, self.answers = data, []
            self.message = SimpleNamespace(reply_text=reply_text)

        async def answer(self, *args, **kwargs):
            effects.append("ack")
            self.answers.append((args, kwargs))

    ns = {
        "Update": object, "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "InlineKeyboardButton": _Button, "InlineKeyboardMarkup": _Markup,
        "html": html, "uuid": uuid,
        "asyncio": SimpleNamespace(to_thread=read_offload),
        "time": SimpleNamespace(time=lambda: 1000.0),
        "USER_PENDING": user_pending_store,
        "get_user_language": get_language,
        "normalize_user_language": lambda lang: lang,
        "public_hub_copy": lambda _lang: {
            "support_ticket_admin_only": "Admin only",
            "support_ticket_action_unsupported": "Unsupported",
            "support_ticket_not_found": "Ticket not found",
            "main_menu": "Main menu",
        },
        "is_admin_user": lambda _uid: admin,
        "get_support_ticket": get_ticket,
        "update_support_ticket": update_ticket,
        "set_support_ticket_pending": set_pending,
        "clear_support_ticket_pending": clear_pending,
        "safe_edit_or_send": render,
        "support_suggested_reply": lambda *_args: "Draft reply",
        "support_ticket_admin_text": lambda value: f"Ticket {value['id']}",
        "now_text": lambda: "test-time",
    }
    exec(CODE, ns)
    actual_pending_helpers["set"] = ns["set_support_ticket_pending"]
    actual_pending_helpers["clear"] = ns["clear_support_ticket_pending"]
    ns["set_support_ticket_pending"] = set_pending
    ns["clear_support_ticket_pending"] = clear_pending
    routes = []
    ns.update(
        tg_app=SimpleNamespace(add_handler=routes.append),
        CallbackQueryHandler=lambda callback, pattern: (callback, re.compile(pattern)),
    )
    registrations = re.findall(
        r"(?m)^\s*tg_app\.add_handler\(CallbackQueryHandler\(handle_ticket_callback,.*$",
        SOURCE,
    )
    assert len(registrations) == 1
    exec(registrations[0].strip(), ns)
    callback, pattern = routes[0]
    markup = ns["support_ticket_admin_keyboard"](ticket)
    data = next(
        button.callback_data for row in markup.inline_keyboard for button in row
        if (
            button.callback_data.startswith(f"ticket|{action}|")
            and (action != "st" or button.callback_data.split("|")[3] == status)
        )
    )
    assert pattern.search(data)
    query = Query(data)
    _run_inert(callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    query._registered_callback = callback
    query._registered_context = SimpleNamespace()
    query._user_pending_store = user_pending_store
    query.notices = notices
    query.ticket = ticket
    return query, effects, pending, edits


@pytest.mark.parametrize("action", ACTIONS)
def test_emitted_stale_admin_action_alerts_once_without_writes_or_pending(action):
    query, effects, pending, edits = _click(action, exists=False)
    assert pending == []
    if action == "st":
        assert query.answers == [((), {})]
        assert effects == ["ack", "get", "render"]
        assert len(edits) == 1
        assert "Ticket not found" in edits[0][0]
        assert {
            button.callback_data for row in edits[0][1].inline_keyboard for button in row
        } == {"ticket|al|new|0", "menu|main"}
    else:
        assert query.answers == [(("Không tìm thấy ticket.",), {"show_alert": True})]
        assert effects == ["get", "ack"]
        assert edits == []


@pytest.mark.parametrize("action", ACTIONS)
def test_emitted_valid_admin_action_keeps_one_early_ack_and_current_action(action):
    query, effects, pending, edits = _click(action)
    assert query.answers == [((), {})]
    assert effects.count("get") == 1
    assert len(edits) == 1
    state_step = {"reply": "admin_reply_input", "ask": "admin_reply_input",
                  "note": "admin_note_input", "suggest": "admin_reply_preview"}.get(action)
    assert bool(pending) == bool(state_step)
    if state_step:
        assert pending[0][0] == (501, state_step)
        assert pending[0][1]["ticket_id"] == 41
    assert effects.count("update") == int(action in {"suggest", "assign", "lead", "st"})
    assert effects.index("ack") < min(
        i for i, effect in enumerate(effects) if effect in {"update", "pending", "render"}
    )


def test_admin_reply_ask_and_note_prompt_back_returns_to_ticket_and_clears_pending():
    for action in ("reply", "ask", "note"):
        query, effects, pending, edits = _click(action)
        assert len(pending) == 1, action
        prompt_markup = edits[0][1]
        back = next(
            button for row in prompt_markup.inline_keyboard for button in row
            if button.text.startswith("⬅")
        )
        assert back.callback_data == "ticket|av|41|new|0", action

        back_query = type(query)(back.callback_data)
        query._user_pending_store["support_ticket:999"] = {
            "pending_action": "support_ticket", "step": "foreign_fixture"
        }
        update = SimpleNamespace(callback_query=back_query)
        _run_inert(query._registered_callback(update, query._registered_context))

        assert back_query.answers == [((), {})], action
        assert pending[0][0] == (501, {
            "reply": "admin_reply_input", "ask": "admin_reply_input",
            "note": "admin_note_input",
        }[action]), action
        assert "support_ticket:501" not in query._user_pending_store, action
        assert query._user_pending_store["support_ticket:999"]["step"] == "foreign_fixture", action
        assert effects[-4:] == ["ack", "clear_pending", "get", "render"], action
        assert edits[-1][0] == "Ticket 41", action
        assert effects.count("update") == 0, action


@pytest.mark.parametrize("action", ACTIONS)
def test_public_actor_cannot_lookup_or_change_admin_action_ticket(action):
    query, effects, pending, edits = _click(action, admin=False)
    assert query.answers == [(("Admin only",), {"show_alert": True})]
    assert effects == ["ack"]
    assert pending == edits == []


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("exists", (True, False))
def test_emitted_admin_action_schedules_language_and_ticket_reads(action, exists):
    read_dispatch = []
    query, effects, _pending, _edits = _click(action, exists=exists, read_dispatch=read_dispatch)
    assert read_dispatch == ["language", "ticket"]
    assert len(query.answers) == 1
    if action == "st":
        assert effects.index("ack") < effects.index("get")
        assert query.answers == [((), {})]
        if not exists:
            assert effects == ["ack", "get", "render"]
    else:
        assert effects.index("get") < effects.index("ack")
        assert query.answers[0][1].get("show_alert", False) is (not exists)


@pytest.mark.parametrize("status", ("resolved", "refund_pending", "waiting_provider"))
def test_emitted_admin_status_actions_keep_status_notice_and_list_navigation(status):
    read_dispatch = []
    query, effects, pending, edits = _click(
        "st", status=status, read_dispatch=read_dispatch
    )

    assert query.data.split("|")[3] == status
    assert read_dispatch == ["language", "ticket"]
    assert query.answers == [((), {})]
    assert pending == []
    assert query.ticket["status"] == status
    assert effects.index("ack") < effects.index("update")
    assert len(edits) == 1
    buttons = {
        button.callback_data
        for row in edits[0][1].inline_keyboard
        for button in row
    }
    assert {"ticket|al|new|0", "menu|main"} <= buttons
    if status == "refund_pending":
        assert query.notices == [
            "💰 Ticket đã được đánh dấu cần kiểm tra hoàn Xu/refund. Thao tác này chưa cộng hoặc trừ Xu."
        ]
        assert effects.index("update") < effects.index("notice") < effects.index("render")
    else:
        assert query.notices == []


def test_assign_ticket_disappearing_after_validation_keeps_one_ack():
    query, effects, pending, edits = _click("assign", disappear_on_update=True)
    assert query.answers == [((), {})]
    assert effects == ["get", "ack", "update", "render"]
    assert pending == []
    assert len(edits) == 1
    assert "Không tìm thấy ticket." in edits[0][0]
    safe_callbacks = {
        button.callback_data for row in edits[0][1].inline_keyboard for button in row
    }
    assert {"ticket|al|new|0", "menu|admin_support", "menu|main"} <= safe_callbacks
