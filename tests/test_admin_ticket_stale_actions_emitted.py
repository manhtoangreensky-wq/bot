"""Admin action buttons through their registered ticket handler, without I/O."""
import asyncio
import html
import re
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest


SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
ACTIONS = ("reply", "ask", "suggest", "note", "assign", "lead")


def _function(name):
    start = re.search(rf"(?m)^(?:async )?def {name}\(", SOURCE)
    assert start, name
    following = re.search(r"(?m)^(?:async )?def \w+\(", SOURCE[start.end():])
    end = start.end() + following.start() if following else len(SOURCE)
    return SOURCE[start.start():end]


CODE = compile(
    "from __future__ import annotations\n"
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


def _click(action, *, exists=True, admin=True, disappear_on_update=False):
    ticket = {
        "id": 41, "ticket_code": "TA-TEST-41", "category": "lead_consulting",
        "message": "test", "status": "new", "admin_note": "",
        "assigned_admin_id": None,
    }
    effects, pending, edits = [], [], []

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

    async def render(_query, text, **kwargs):
        effects.append("render")
        edits.append((text, kwargs.get("reply_markup")))

    class Query:
        from_user = SimpleNamespace(id=501)

        def __init__(self, data):
            self.data, self.answers = data, []

        async def answer(self, *args, **kwargs):
            effects.append("ack")
            self.answers.append((args, kwargs))

    ns = {
        "Update": object, "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "InlineKeyboardButton": _Button, "InlineKeyboardMarkup": _Markup,
        "html": html, "uuid": uuid,
        "get_user_language": lambda _uid: "vi",
        "normalize_user_language": lambda lang: lang,
        "public_hub_copy": lambda _lang: {
            "support_ticket_admin_only": "Admin only",
            "support_ticket_action_unsupported": "Unsupported",
        },
        "is_admin_user": lambda _uid: admin,
        "get_support_ticket": get_ticket,
        "update_support_ticket": update_ticket,
        "set_support_ticket_pending": set_pending,
        "safe_edit_or_send": render,
        "support_suggested_reply": lambda *_args: "Draft reply",
        "support_ticket_admin_text": lambda value: f"Ticket {value['id']}",
        "now_text": lambda: "test-time",
    }
    exec(CODE, ns)
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
        if button.callback_data.startswith(f"ticket|{action}|")
    )
    assert pattern.search(data)
    query = Query(data)
    asyncio.run(callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    return query, effects, pending, edits


@pytest.mark.parametrize("action", ACTIONS)
def test_emitted_stale_admin_action_alerts_once_without_writes_or_pending(action):
    query, effects, pending, edits = _click(action, exists=False)
    assert query.answers == [(("Không tìm thấy ticket.",), {"show_alert": True})]
    assert effects == ["get", "ack"]
    assert pending == []
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
    assert effects.count("update") == int(action in {"suggest", "assign", "lead"})
    assert effects.index("ack") < min(
        i for i, effect in enumerate(effects) if effect in {"update", "pending", "render"}
    )


@pytest.mark.parametrize("action", ACTIONS)
def test_public_actor_cannot_lookup_or_change_admin_action_ticket(action):
    query, effects, pending, edits = _click(action, admin=False)
    assert query.answers == [(("Admin only",), {"show_alert": True})]
    assert effects == ["ack"]
    assert pending == edits == []


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
    assert {"ticket|al|new|0", "menu|admin", "menu|main"} <= safe_callbacks
