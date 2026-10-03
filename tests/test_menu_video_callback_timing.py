"""Root Video button through the actual menu route, with deterministic API timing."""
import asyncio
import re
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

import pytest


SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def _function(name):
    start = re.search(rf"(?m)^(?:async )?def {name}\(", SOURCE)
    assert start, name
    following = re.search(r"(?m)^(?:async )?def \w+\(", SOURCE[start.end():])
    end = start.end() + following.start() if following else len(SOURCE)
    return SOURCE[start.start():end]


CODE = compile("from __future__ import annotations\n" + "\n".join(
    _function(name) for name in (
        "localized_main_menu_keyboard", "localized_menu_content",
        "menu_text_main_video", "menu_text_main_video_i18n", "main_video_keyboard",
        "safe_edit_query_message", "handle_menu_callback",
    )
), "bot.py:menu Video path", "exec")


class Button:
    def __init__(self, text, callback_data=None, url=None):
        self.text, self.callback_data, self.url = text, callback_data, url


class Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


def _run(*, admin=False, resume=False, render_error=False, action="main_video"):
    clock, events, logs = {"now": 0.0}, [], []

    def step(event, seconds):
        events.append(event)
        clock["now"] += seconds

    def cleanup(name):
        return lambda *_args, **_kwargs: step(name, .001)

    def language(_uid):
        step("language", .025)
        return "vi"

    def visible_rows():
        step("keyboard", .020)
        return (("video_ai_real",), ("main_menu",))

    class Query:
        from_user = SimpleNamespace(id=873999, username="synthetic", first_name="Test")

        def __init__(self, data):
            self.data, self.answers, self.edits = data, [], []

        async def answer(self, *args, **kwargs):
            step("ack", .400)
            self.answers.append((args, kwargs))

        async def edit_message_text(self, text, **kwargs):
            step("edit", .600)
            self.edits.append((text, kwargs))
            if render_error:
                raise RuntimeError("synthetic render failure")
            return SimpleNamespace(message_id=1)

    ns = {
        "Update": object, "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "InlineKeyboardButton": Button, "InlineKeyboardMarkup": Markup,
        "normalize_user_language": lambda lang: lang,
        "public_hub_copy": lambda _lang: defaultdict(lambda: "label"),
        "product_context_callback": lambda *_args: "music_quick|root",
        "PRODUCT_CONTEXT_SHOWROOM": "showroom",
        "TOAN_AAS_COMMUNITY_URL": "https://example.invalid/",
        "public_chat_runtime": SimpleNamespace(CHAT_PRO_RATE_LABEL="test rate"),
        "is_admin_user": lambda _uid: admin,
        "get_user_language": language,
        "VIDEO_TAIL9_TEXT_INPUT_KEY": "tail_input", "DOC_TOOL_MENU_ACTIONS": set(),
        "time": SimpleNamespace(perf_counter=lambda: clock["now"]),
        "logger": SimpleNamespace(info=lambda *args: logs.append(args)),
        "go_video_screen": lambda *_args: step("video_screen", .010),
        "video_public_visible_menu_rows": visible_rows,
        "video_public_route_for_tool": lambda _tool: {"entry_callback": "vid3|entry|video_ai_real"},
        "video_public_menu_label": lambda *_args: "Video AI",
        "public_video_menu_label": lambda *_args: "Resume",
        "video_uiflow3_state": lambda context: context.user_data.get("draft") or {},
        "video_trend2_cancel_pending_on_video_menu": lambda *_args: step("trend", .005),
        "menu_text_main_image_i18n": lambda _lang: "Image menu",
        "main_image_keyboard": lambda _lang: Markup([]),
    }
    for name in (
        "clear_broadcast_lite_pending", "clear_translation_menu_pending",
        "clear_translation_session", "clear_media_creator_pending_states",
        "clear_support_ticket_pending", "clear_finance_compliance_pending",
        "clear_internal_archive_pending", "clear_doc_tool_pending",
        "clear_storage_addon_pending", "clear_memory_guided_pending",
        "clear_music_guided_pending", "clear_pending_admin_tool_test",
    ):
        ns[name] = cleanup(name)
    exec(CODE, ns)
    root = ns["localized_main_menu_keyboard"](admin, "vi")
    data = next(button.callback_data for row in root.inline_keyboard for button in row
                if button.callback_data == f"menu|{action}")
    routes = []
    ns.update(tg_app=SimpleNamespace(add_handler=routes.append),
              CallbackQueryHandler=lambda callback, pattern: (callback, re.compile(pattern)))
    registrations = re.findall(
        r"(?m)^\s*tg_app\.add_handler\(CallbackQueryHandler\(handle_menu_callback,.*$", SOURCE
    )
    assert len(registrations) == 1
    exec(registrations[0].strip(), ns)
    callback, pattern = routes[0]
    assert pattern.search(data)
    query = Query(data)
    draft = {"keep": "video draft"} if resume else {}
    context = SimpleNamespace(user_data={"draft": draft, "tail_input": "old input"})
    error = None
    try:
        asyncio.run(callback(SimpleNamespace(callback_query=query), context))
    except RuntimeError as exc:
        error = exc
    return query, events, logs, context, error


@pytest.mark.parametrize("admin", [False, True])
@pytest.mark.parametrize("resume", [False, True])
def test_emitted_root_video_records_phases_preserving_ack_screen_back_and_draft(admin, resume):
    query, events, logs, context, error = _run(admin=admin, resume=resume)
    assert error is None
    assert query.answers == [((), {})]
    first_events = ["ack"] + (["clear_broadcast_lite_pending"] if admin else []) + ["language"]
    assert events[:len(first_events)] == first_events
    assert len(query.edits) == 1
    text, kwargs = query.edits[0]
    assert text.startswith("🎬 <b>Video TOAN AAS</b>")
    callbacks = [button.callback_data for row in kwargs["reply_markup"].inline_keyboard for button in row]
    assert "menu|main" in callbacks
    assert ("vid3|resume" in callbacks) == resume
    assert context.user_data["draft"] == ({"keep": "video draft"} if resume else {})
    assert "tail_input" not in context.user_data
    assert len(logs) == 1, "missing root Video timing evidence"
    log = logs[0][0] % logs[0][1:]
    fields = dict(re.findall(r"(\w+)=(\S+)", log))
    assert fields["route"] == "menu|main_video"
    assert fields["role"] == ("admin" if admin else "public")
    assert float(fields["ack_ms"]) == pytest.approx(400)
    assert float(fields["language_ms"]) == pytest.approx(25)
    assert float(fields["build_ms"]) == pytest.approx(55)
    assert float(fields["render_ms"]) == pytest.approx(600)
    phases = ("pre_ack_ms", "ack_ms", "language_ms", "cleanup_ms", "build_ms", "render_ms")
    assert all(float(fields[key]) >= 0 for key in phases)
    assert float(fields["handler_ms"]) == pytest.approx(sum(float(fields[key]) for key in phases))
    assert fields["render_returned"] == "1"
    assert "873999" not in log and text not in log and "video draft" not in log


def test_render_exception_still_propagates_with_anonymous_failed_timing():
    query, _events, logs, _context, error = _run(render_error=True)
    assert str(error) == "synthetic render failure"
    assert query.answers == [((), {})]
    assert len(logs) == 1
    log = logs[0][0] % logs[0][1:]
    assert "render_returned=0" in log
    assert "synthetic render failure" not in log


def test_other_root_menu_keeps_existing_ack_render_without_video_timing():
    query, _events, logs, _context, error = _run(action="main_image")
    assert error is None
    assert query.answers == [((), {})]
    assert query.edits[0][0] == "Image menu"
    assert logs == []
