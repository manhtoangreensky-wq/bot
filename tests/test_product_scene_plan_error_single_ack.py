"""Emitted planning callback and full handler with offline enhancement/transport."""
import asyncio
from copy import deepcopy
import hmac
import html
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from services import video_uiflow3


SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def _source(name):
    start = re.search(rf"(?m)^(?:async )?def {name}\(", SOURCE)
    assert start, name
    following = re.search(r"(?m)^(?:async )?def \w+\(", SOURCE[start.end():])
    end = start.end() + following.start() if following else len(SOURCE)
    return SOURCE[start.start():end]


def _assignment(name):
    start = re.search(rf"(?m)^{name} = ", SOURCE)
    assert start, name
    following = re.search(r"(?m)^(?:[A-Z][A-Z0-9_]* = |(?:async )?def \w+\()", SOURCE[start.end():])
    end = start.end() + following.start() if following else len(SOURCE)
    return SOURCE[start.start():end]


class Button:
    def __init__(self, text, callback_data=None):
        self.text, self.callback_data = text, callback_data


class Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class Query:
    def __init__(self, data, actor_id=701, callback_id="offline-callback"):
        self.data, self.id = data, callback_id
        self.from_user = SimpleNamespace(id=actor_id)
        self.message = SimpleNamespace(chat_id=actor_id)
        self.answers, self.edits = [], []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs.get("reply_markup")))
        return SimpleNamespace(message_id=1)


def _runtime(product, actor_id, *, enhancement_fails=True):
    state = video_uiflow3.new_state(product, draft_id="keep-offline-plan")
    state["navigation"]["current_step"] = "scene_plan"
    state["content"]["original_intent"] = "Keep original content"
    state["owner_user_id"] = actor_id
    state["owner_chat_id"] = actor_id
    context = SimpleNamespace(user_data={"draft": state})
    enhancement_calls = []

    def save(context, value):
        clean = video_uiflow3.normalize_state(value)
        context.user_data["draft"] = clean
        return clean

    async def enhance(value):
        enhancement_calls.append(deepcopy(value))
        if enhancement_fails:
            raise ValueError("scene_plan_missing")
        return value

    async def transport(query, text, **kwargs):
        return await query.edit_message_text(text, **kwargs)

    async def no_shared_review(*_args):
        return None

    ns = {
        "Update": object, "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "InlineKeyboardButton": Button, "InlineKeyboardMarkup": Markup,
        "video_uiflow3": video_uiflow3, "hmac": hmac, "html": html,
        "video_uiflow3_state": lambda context: context.user_data["draft"],
        "save_video_uiflow3_state": save,
        # Neutral fixture state is already canonical. AI/pilot engines are outside this test.
        "video_uiflow3_canonical_screen_state": video_uiflow3.normalize_state,
        "video_ai_real_pilot_screen_payload": lambda *_args, **_kwargs: None,
        "video_uiflow3_ai_enhance_scenes_bounded": enhance,
        "safe_edit_or_send": transport, "safe_edit_or_send_long_html": transport,
        "video_uiflow3_return_to_shared_tail_if_ready": no_shared_review,
        "ApplicationHandlerStop": type("ApplicationHandlerStop", (Exception,), {}),
        "logger": SimpleNamespace(warning=lambda *_args: None),
    }
    for name in ("VIDEO_UIFLOW3_STEP_ACTIONS", "VIDEO_UIFLOW3_ACTION_ARITIES", "VIDEO_UIFLOW3_PRODUCT_LABELS"):
        exec(compile(_assignment(name), f"bot.py:{name}", "exec"), ns)
    for name in (
        "safe_int", "video_public_callback_failure_guard", "video_uiflow3_keyboard",
        "video_uiflow3_nav_rows", "video_uiflow3_progress_text", "video_uiflow3_product_label",
        "_video_uiflow3_screen_payload_unscoped", "video_uiflow3_screen_payload",
        "video_uiflow3_input_error", "video_uiflow3_render", "video_storyboard_entity_bridge_marker",
        "video_uiflow3_clear_transient", "video_uiflow3_action_allowed",
        "video_uiflow3_action_arity_valid", "video_uiflow3_ack_without_interrupting_flow",
    ):
        exec(compile("from __future__ import annotations\n" + _source(name), f"bot.py:{name}", "exec"), ns)
    assert "@video_public_callback_failure_guard\nasync def handle_video_uiflow3_callback" in SOURCE
    exec(compile("from __future__ import annotations\n@video_public_callback_failure_guard\n"
                 + _source("handle_video_uiflow3_callback"), "bot.py:planning handler", "exec"), ns)
    routes = []
    ns.update(tg_app=SimpleNamespace(add_handler=routes.append),
              CallbackQueryHandler=lambda callback, pattern: (callback, re.compile(pattern)))
    registrations = re.findall(
        r"(?m)^\s*tg_app\.add_handler\(CallbackQueryHandler\(handle_video_uiflow3_callback,.*$", SOURCE
    )
    assert len(registrations) == 1
    exec(registrations[0].strip(), ns)
    callback, pattern = routes[0]
    _, markup = ns["video_uiflow3_screen_payload"](state)
    data = next(button.callback_data for row in markup.inline_keyboard for button in row
                if "|scene_plan_auto" in str(button.callback_data))
    assert pattern.search(data)
    assert data == video_uiflow3.scope_callback(state, "vid3|scene_plan_auto")
    return ns, context, callback, data, enhancement_calls


def _click(callback, context, data, actor_id, callback_id="offline-callback"):
    query = Query(data, actor_id, callback_id)
    asyncio.run(callback(SimpleNamespace(callback_query=query), context))
    return query


@pytest.mark.parametrize("product", ["script_image_video", "multi_scene_film"])
@pytest.mark.parametrize("actor_id", [701, 702])
def test_error_after_early_ack_stays_on_same_plan_with_one_ack_and_visible_recovery(product, actor_id):
    ns, context, callback, data, calls = _runtime(product, actor_id)
    before = deepcopy(context.user_data["draft"])
    _, before_markup = ns["video_uiflow3_screen_payload"](before)
    before_callbacks = [button.callback_data for row in before_markup.inline_keyboard for button in row]
    query = _click(callback, context, data, actor_id)

    assert query.answers == [(("Đang phác thảo kế hoạch cảnh...",), {})]
    assert len(calls) == len(query.edits) == 1
    text, markup = query.edits[0]
    assert ns["video_uiflow3_input_error"](ValueError("scene_plan_missing")) in text
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert callbacks == before_callbacks
    assert data in callbacks
    back = "vid3|view|episode_script" if product == "multi_scene_film" else "vid3|back"
    assert video_uiflow3.scope_callback(before, back) in callbacks
    assert "menu|main_video" in callbacks
    after = context.user_data["draft"]
    for field in ("draft_id", "parent_product", "content", "scenes", "source", "format", "bible", "audio"):
        assert after[field] == before[field]
    assert after["navigation"]["current_step"] == "scene_plan"


def test_validation_before_ack_keeps_one_alert_and_existing_rerender():
    ns, context, callback, data, calls = _runtime("script_image_video", 701)
    ns["video_uiflow3_action_allowed"] = lambda *_args: False
    query = _click(callback, context, data, 701)
    assert query.answers == [((ns["video_uiflow3_input_error"](ValueError("video_uiflow3_action_not_relevant")),), {"show_alert": True})]
    assert calls == []
    assert len(query.edits) == 1


def test_successful_plan_and_same_callback_replay_keep_original_behaviour():
    _ns, context, callback, data, calls = _runtime("script_image_video", 701, enhancement_fails=False)
    query = _click(callback, context, data, 701)
    assert query.answers == [(("Đang phác thảo kế hoạch cảnh...",), {})]
    assert len(query.edits) == 1
    repeated = _click(callback, context, data, 701)
    assert repeated.answers == [(("Đã nhận lựa chọn này.",), {})]
    assert repeated.edits == []
    assert len(calls) == 1
