from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import sqlite3
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import (
    video_edit_capabilities,
    video_edit_state_machine,
    video_editengine1,
    video_local_editing,
    video_local_validation,
    video_smart_splitter,
)


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    markers = (f"async def {name}(", f"def {name}(")
    starts = [BOT_SOURCE.find(marker) for marker in markers]
    starts = [position for position in starts if position >= 0]
    if not starts:
        raise AssertionError(f"missing function: {name}")
    start = min(starts)
    next_defs = [
        position
        for position in (
            BOT_SOURCE.find("\ndef ", start + 1),
            BOT_SOURCE.find("\nasync def ", start + 1),
            BOT_SOURCE.find("\n@", start + 1),
        )
        if position >= 0
    ]
    end = min(next_defs) if next_defs else len(BOT_SOURCE)
    return BOT_SOURCE[start:end].rstrip() + "\n"


def _compile_function(name: str, namespace: dict):
    source = "from __future__ import annotations\n\n" + _function_source(name)
    exec(compile(source, filename="bot.py", mode="exec"), namespace)
    return namespace[name]


class _Message:
    chat_id = 99001

    def __init__(self, text: str = "") -> None:
        self.text = text
        self.replies: list[tuple[str, dict]] = []

    async def reply_text(self, text: str, **kwargs):
        self.replies.append((text, kwargs))
        return SimpleNamespace(message_id=7001)


class _Query:
    def __init__(self, user_id: int, data: str) -> None:
        self.id = f"videoedit-{user_id}-{data}"
        self.from_user = SimpleNamespace(id=user_id, first_name="Video Edit")
        self.data = data
        self.message = _Message()
        self.edits: list[tuple[str, dict]] = []
        self.answers: list[tuple[tuple, dict]] = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))
        return True

    async def edit_message_text(self, text: str, **kwargs):
        self.edits.append((text, kwargs))
        return SimpleNamespace(message_id=7002)


def _default_state(user_id: int, **overrides) -> dict:
    plan = video_local_editing.default_manual_edit_plan("")
    plan["trim"] = {"start_ms": 0, "end_ms": 10_000}
    state = {
        "step": "options",
        "edit_mode": "manual_edit",
        "current_screen": "workspace",
        "screen_id": "workspace",
        "parent_callback": "videoedit|manual",
        "selected_tool": "manual",
        "entry_context": "manual",
        "last_section": "manual",
        "source_file_id": "telegram-source",
        "source_file_name": "source.mp4",
        "source_display_name": "source.mp4",
        "source_file_size": 4096,
        "source_duration": 10,
        "source_duration_ms": 10_000,
        "source_video_id": "telegram-source",
        "source_video_hash": "a" * 64,
        "source_metadata": {
            "ok": True,
            "duration": 10.0,
            "duration_ms": 10_000,
            "width": 1280,
            "height": 720,
            "fps": 30.0,
            "has_audio": True,
            "audio_stream_count": 1,
            "format_name": "mp4",
        },
        "inspection_complete": True,
        "manual_edit_plan": plan,
        "edit_session_id": f"edit-{user_id}",
        "state_revision": 3,
        "revision": 3,
        "status": "source_ready",
    }
    state.update(overrides)
    return state


def _state_updater(state: dict):
    def update_pending(_user_id: int, step: str = "", **fields) -> dict:
        state.update(deepcopy(fields))
        state["step"] = step or state.get("step") or "menu"
        return deepcopy(state)

    return update_pending


def _pending_handler_namespace(state: dict) -> dict:
    class _LegacyRouter:
        DEFAULT_PRESERVE_CONTROLS = {}

        @staticmethod
        def route_ai_edit_intent(*_args, **_kwargs):
            return {"suggestions": [], "execution_lane": "local", "preserve_controls": {}}

    update_pending = _state_updater(state)
    return {
        "get_video_editor_pending": lambda _uid: deepcopy(state),
        "clear_video_editor_competing_video_states": lambda *_args, **_kwargs: {},
        "get_user_language": lambda _uid: "vi",
        "safe_int": lambda value, default=0: int(value or default),
        "re": re,
        "video_edit_capabilities": video_edit_capabilities,
        "video_local_editing": video_local_editing,
        "video_local_validation": video_local_validation,
        "video_smart_splitter": video_smart_splitter,
        "video_ai_edit_router": _LegacyRouter,
        "update_video_editor_pending": update_pending,
        "return_video_editor_workspace": lambda _uid, **fields: update_pending(
            _uid,
            "options",
            current_screen="workspace",
            **fields,
        ),
        "video_edit_runtime_capability_admission": lambda *_args, **_kwargs: {
            "ready": True,
            "reason": "ok",
        },
        "video_scene3_keyboard": lambda rows: rows,
        "ui_text": lambda _lang, key: "⬅️ Quay lại" if key == "common.back" else "🏠 Menu chính",
        "video_ai_edit_intent_keyboard": lambda *_args: "intent-keyboard",
        "video_local_manual_options_text": lambda _state, _lang: "Không gian chỉnh sửa local · 0 Xu",
        "video_local_manual_options_keyboard": lambda _lang, _state=None: "workspace-keyboard",
        "video_ai_edit_suggestions_text": lambda _state, _lang: "AI suggestions",
        "video_ai_edit_suggestions_keyboard": lambda _state, _lang: "suggestions-keyboard",
        "video_local_input_keyboard": lambda *_args, **_kwargs: "input-keyboard",
        "video_local_public_error": lambda reason: reason,
    }


def _run_pending_text(state: dict, text: str) -> _Message:
    handler = _compile_function("handle_video_editor_pending_text", _pending_handler_namespace(state))
    message = _Message(text)
    update = SimpleNamespace(
        callback_query=None,
        message=message,
        effective_user=SimpleNamespace(id=901),
    )
    assert asyncio.run(handler(update, SimpleNamespace(user_data={}))) is True
    return message


def test_vietnamese_assistant_compiles_local_and_generative_intent_fails_closed() -> None:
    local_state = _default_state(901, step="await_ai_intent", edit_mode="ai_edit", entry_context="ai")
    local_message = _run_pending_text(local_state, "làm sáng, rõ và âm lượng đều")

    assert local_state["step"] in {"options", "workspace"}
    assert local_state["selected_tool"] == "manual"
    assert local_state["entry_context"] == "ai"
    assert local_state["last_section"] == "ai"
    assert local_state["entry_parent_callback"] == "videoedit|ai_source"
    assert local_state["manual_edit_plan"]["color_preset"] == "bright_clear"
    assert local_state["manual_edit_plan"]["quality_filters"]["sharpen"] is True
    assert local_state["manual_edit_plan"]["audio_normalization"] == "loudnorm"
    assert "0 Xu" in local_message.replies[-1][0]

    blocked_state = _default_state(902, step="await_ai_intent", edit_mode="ai_edit", entry_context="ai")
    before_plan = deepcopy(blocked_state["manual_edit_plan"])
    blocked_message = _run_pending_text(blocked_state, "tạo phép thuật/parallax cho video")

    assert blocked_state["step"] == "await_ai_intent"
    assert blocked_state["manual_edit_plan"] == before_plan
    assert "chưa tạo tác vụ" in blocked_message.replies[-1][0].lower()
    assert "provider" in blocked_message.replies[-1][0].lower()
    assert not blocked_state.get("job_id")


def test_assistant_intent_stays_in_intake_when_worker_cannot_execute_a_selected_filter() -> None:
    state = _default_state(903, step="await_ai_intent", edit_mode="ai_edit", entry_context="ai")
    checked: list[str] = []
    namespace = _pending_handler_namespace(state)

    def deny(feature_key: str, *_args, **_kwargs) -> dict:
        checked.append(feature_key)
        return {"ready": False, "reason": "filter_missing:unsharp"}

    namespace["video_edit_runtime_capability_admission"] = deny
    handler = _compile_function("handle_video_editor_pending_text", namespace)
    message = _Message("làm rõ video")
    update = SimpleNamespace(
        callback_query=None,
        message=message,
        effective_user=SimpleNamespace(id=903),
    )

    assert asyncio.run(handler(update, SimpleNamespace(user_data={}))) is True
    assert checked == ["enhance_basic_sharpen"]
    assert state["step"] == "await_ai_intent"
    assert state.get("provider_call") is False
    assert all("Không gian chỉnh sửa local" not in text for text, _kwargs in message.replies)
    assert any("chưa" in text.lower() and "worker" in text.lower() for text, _kwargs in message.replies)


def test_remove_middle_collects_one_interval_for_one_joined_mp4() -> None:
    state = _default_state(
        903,
        step="await_remove_middle",
        split_mode="remove_middle",
        split_ranges=[],
    )
    message = _run_pending_text(state, "00:02-00:04")

    assert state["step"] == "options"
    assert state["selected_tool"] == "manual"
    assert state["split_mode"] == "remove_middle"
    assert state["split_ranges"] == []
    assert state["manual_edit_plan"]["remove_middle"] == {
        "start_ms": 2_000,
        "end_ms": 4_000,
    }
    assert "một MP4" in message.replies[-1][0]


def test_effect_quality_review_and_set_routes_use_local_contracts() -> None:
    callback = _function_source("handle_video_editor_callback")
    effect_start = callback.index('if action == "effect_pick":')
    restore_start = callback.index('if action == "restore_pick":')
    ai_start = callback.index('if action == "ai":', restore_start)
    effect_block = callback[effect_start:restore_start]
    restore_block = callback[restore_start:ai_start]
    assert '{"restore", "audio"}' in restore_block
    assert 'feature_key != "audio_loudnorm"' in restore_block

    for block in (effect_block, restore_block):
        assert "video_edit_runtime_capability_admission" in block
        assert block.index("video_edit_runtime_capability_admission") < block.index("plan_patch")
        assert "video_edit_capabilities.plan_patch" in block
        assert "video_edit_capabilities.merge_plan_patch" in block
        assert "manual_edit_plan=plan" in block
        assert "video_ai_edit_router.route_ai_edit_intent" not in block

    review_start = callback.index('if action == "review":')
    confirmation_start = callback.index('if action == "confirmation":', review_start)
    review_block = callback[review_start:confirmation_start]
    set_start = callback.rindex('if action == "set":')
    confirm_start = callback.index('if action == "confirm_local":', set_start)
    set_block = callback[set_start:confirm_start]
    assert "video_local_editing.normalize_callback_plan_choice" in set_block
    assert set_block.index("normalize_callback_plan_choice") < set_block.index("plan = dict")

    assert 'video_local_confirmation_text(candidate, lang, stage="review")' in review_block
    assert "video_local_review_keyboard" in review_block
    assert "video_local_editing.plan_has_effective_operation" in review_block
    assert "Chưa có thao tác chỉnh sửa nào được chọn" in review_block
    confirmation_block = callback[confirmation_start:set_start]
    assert "video_local_confirmation_text(candidate, lang)" in confirmation_block
    assert "video_local_confirmation_keyboard" in confirmation_block
    final_confirm = callback[confirm_start:]
    assert "submit_video_edit_local_free_job" in final_confirm
    assert "video_tail9_render" not in callback[review_start:]


def test_restore_pick_without_source_enters_quality_upload_before_filter_gate() -> None:
    callback = _function_source("handle_video_editor_callback")
    start = callback.index('if action == "restore_pick":')
    end = callback.index('if action == "ai":', start)
    block = callback[start:end]
    source_guard = block.index('or not state.get("source_file_id")')
    filter_gate = block.index("video_edit_runtime_capability_admission")
    assert source_guard < filter_gate
    assert "start_video_edit_lane_state(" in block
    assert '"quality_enhance"' in block
    assert 'video_edit_lane_upload_text("quality_enhance", lang)' in block
    assert 'selected_effect=feature_key' in block


def test_local_ui_copy_and_remove_middle_entry_are_truthful() -> None:
    effects = _function_source("video_edit_effects_text")
    guide = _function_source("video_edit_guide_text")
    confirmation = _function_source("video_local_confirmation_text")
    keyboard = _function_source("video_local_confirmation_keyboard")
    callback = _function_source("handle_video_editor_callback")

    assert "Hiệu ứng local" in effects
    assert "0 Xu" in effects
    assert "50 MB" in guide
    assert "0 Xu" in guide
    assert "đúng số phần MP4 đã chọn" in guide
    for english_fragment in ("fade", "vignette", "slow zoom", "giới hạn audio"):
        assert english_fragment not in guide.lower()
    assert "không gọi provider" in confirmation.lower()
    assert keyboard.count("videoedit|confirm_local") == 1
    remove_start = callback.index('if action == "remove_middle":')
    remove_end = callback.index('if action == "split_from_manual":', remove_start)
    remove_block = callback[remove_start:remove_end]
    assert 'state_step="await_remove_middle"' in remove_block
    assert 'selected_tool="manual"' in remove_block
    assert "bỏ một đoạn" in remove_block.lower()
    assert "một MP4" in remove_block


def test_public_assistant_copy_advertises_only_executable_local_goals() -> None:
    upload = _function_source("video_ai_edit_upload_text")
    intent = _function_source("video_ai_edit_intent_text")
    combined = (upload + intent).lower()
    assert "làm sáng" in combined
    assert "làm rõ" in combined
    assert "video dọc" in combined
    assert "walkthrough căn phòng thành nội thất điện ảnh" not in combined
    assert "provider" in combined
    assert "0 xu" in combined


def test_assistant_local_alternative_button_opens_the_real_workspace() -> None:
    callback = _function_source("handle_video_editor_callback")
    start = callback.index('if action == "ai_use_local":')
    end = callback.index('if action == "ai_confirm":', start)
    block = callback[start:end]
    assert "update_video_editor_screen(" in block
    assert '"workspace"' in block
    assert 'parent_callback="videoedit|ai_source"' in block
    assert 'edit_mode="ai_edit"' in block
    assert "video_local_manual_options_text(current, lang)" in block
    assert "video_local_manual_options_keyboard(lang, current)" in block
    assert "query.answer" not in block


def test_legacy_assistant_review_copy_never_advertises_invoice_or_ai_prompt_execution() -> None:
    prompt = _function_source("video_ai_edit_prompt_text")
    prompt_keyboard = _function_source("video_ai_edit_prompt_keyboard")
    status_keyboard = _function_source("video_ai_edit_status_keyboard")
    settings = _function_source("video_ai_edit_settings_text")

    combined = (prompt + prompt_keyboard + status_keyboard + settings).lower()
    assert "xem báo giá" not in combined
    assert "xem lại hóa đơn" not in combined
    assert "prompt chuyên nghiệp" not in combined
    assert "kế hoạch local" in combined
    assert "chưa gọi nguồn xử lý" in combined or "chưa gọi provider" in combined


def test_stale_provider_era_ai_controls_redirect_to_the_canonical_local_workspace() -> None:
    callback = _function_source("handle_video_editor_callback")
    redirect_start = callback.index("VIDEO_EDIT_LEGACY_AI_CONTROL_ACTIONS = {")
    ai_router_start = callback.index('if action.startswith("ai_"):', redirect_start)
    redirect = callback[redirect_start:ai_router_start]

    for action in (
        '"ai_settings"',
        '"ai_set_intensity"',
        '"ai_toggle"',
        '"ai_set_aspect"',
        '"ai_set_text"',
        '"ai_set_motion"',
        '"ai_review"',
        '"ai_prompt"',
    ):
        assert action in redirect
    assert "update_video_editor_screen(" in redirect
    assert '"workspace"' in redirect
    assert "video_local_manual_options_keyboard" in redirect
    assert "submit_video_ai_edit_job" not in redirect
    assert "video_ai_edit_router" not in redirect


def test_waiting_lane_reentry_rerenders_the_same_upload_screen() -> None:
    current_state: dict = {}

    async def render(query, text: str, **kwargs):
        await query.edit_message_text(text, **kwargs)
        return True

    handler = _compile_function(
        "handle_video_editor_callback",
        {
            "get_user_language": lambda _uid: "vi",
            "get_video_editor_pending": lambda _uid: deepcopy(current_state),
            "video_edit_state_machine": video_edit_state_machine,
            "video_editor_normalize_action": lambda value: value,
            "safe_edit_or_send": render,
            "video_edit_lane_upload_text": lambda mode, _lang: f"upload:{mode}",
            "video_edit_lane_upload_keyboard": lambda mode, _lang: f"keyboard:{mode}",
            "logger": logging.getLogger("videoedit-lane-reentry"),
            "sanitize_log_text": str,
        },
    )

    cases = (
        ("videoedit|manual", "manual_edit"),
        ("videoedit|ai", "ai_edit"),
        ("videoedit|restore", "quality_enhance"),
    )
    for callback, edit_mode in cases:
        current_state.clear()
        current_state.update(
            {
                "step": "await_video",
                "edit_mode": edit_mode,
                "awaiting_media": True,
            }
        )
        query = _Query(940, callback)
        update = SimpleNamespace(callback_query=query, effective_user=query.from_user)

        assert asyncio.run(handler(update, SimpleNamespace(user_data={}))) is True
        assert query.edits, f"{callback} must not become a silent no-op"
        assert query.edits[-1][0] == f"upload:{edit_mode}"


def test_hub_entry_does_not_clear_any_video_state_before_telegram_render_succeeds() -> None:
    events: list[str] = []

    async def failed_render(*_args, **_kwargs):
        events.append("render")
        raise RuntimeError("telegram edit failed")

    handler = _compile_function(
        "handle_video_editor_callback",
        {
            "get_user_language": lambda _uid: "vi",
            "clear_video_editor_competing_video_states": lambda *_args: events.append("clear-competing"),
            "clear_video_session": lambda *_args: events.append("clear-session"),
            "clear_video_editor_pending": lambda *_args: events.append("clear-pending"),
            "set_video_route_session": lambda *_args, **_kwargs: events.append("set-route"),
            "safe_edit_or_send": failed_render,
            "video_edit_hub_text": lambda _lang: "hub",
            "video_edit_hub_keyboard": lambda _lang: "hub-keyboard",
            "logger": logging.getLogger("videoedit-hub-transaction"),
            "sanitize_log_text": str,
        },
    )
    query = _Query(941, "videoedit|hub")
    update = SimpleNamespace(callback_query=query, effective_user=query.from_user)

    with pytest.raises(RuntimeError, match="telegram edit failed"):
        asyncio.run(handler(update, SimpleNamespace(user_data={})))
    assert events == ["render"]


@pytest.mark.parametrize(
    ("callback", "edit_mode"),
    [
        ("videoedit|manual", "manual_edit"),
        ("videoedit|ai", "ai_edit"),
        ("videoedit|restore", "quality_enhance"),
    ],
)
def test_lane_entry_commits_state_only_after_telegram_render(callback: str, edit_mode: str) -> None:
    events: list[str] = []

    async def failed_render(*_args, **_kwargs):
        events.append("render")
        raise RuntimeError("telegram edit failed")

    handler = _compile_function(
        "handle_video_editor_callback",
        {
            "get_user_language": lambda _uid: "vi",
            "get_video_editor_pending": lambda _uid: {},
            "video_edit_state_machine": video_edit_state_machine,
            "video_editor_normalize_action": lambda value: value,
            "clear_video_editor_competing_video_states": lambda *_args: events.append("clear-competing"),
            "clear_video_session": lambda *_args: events.append("clear-session"),
            "clear_video_editor_pending": lambda *_args: events.append("clear-pending"),
            "set_video_route_session": lambda *_args, **_kwargs: events.append("set-route"),
            "start_video_edit_lane_state": lambda *_args, **_kwargs: events.append(f"start:{edit_mode}"),
            "safe_edit_or_send": failed_render,
            "video_edit_lane_upload_text": lambda mode, _lang: f"upload:{mode}",
            "video_edit_lane_upload_keyboard": lambda mode, _lang: f"keyboard:{mode}",
            "logger": logging.getLogger("videoedit-lane-transaction"),
            "sanitize_log_text": str,
        },
    )
    query = _Query(942, callback)
    update = SimpleNamespace(callback_query=query, effective_user=query.from_user)

    with pytest.raises(RuntimeError, match="telegram edit failed"):
        asyncio.run(handler(update, SimpleNamespace(user_data={})))
    assert events == ["render"]


def test_videoedit_callback_answers_exactly_at_the_final_route_not_before_validation() -> None:
    callback = _function_source("handle_video_editor_callback")
    action_parse = callback.index("parts = str(query.data or \"\").split")
    assert "await query.answer()" not in callback[:action_parse]

    safe_render = _function_source("safe_edit_or_send")
    assert 'startswith("videoedit|")' in safe_render
    assert 'getattr(query, "_video_edit_callback_answered", False)' in safe_render
    assert 'setattr(query, "_video_edit_callback_answered", True)' in safe_render


def test_videoedit_render_commit_and_callback_answer_follow_transaction_order() -> None:
    events: list[str] = []

    class Query(_Query):
        async def edit_message_text(self, text: str, **kwargs):
            events.append("render")
            return await super().edit_message_text(text, **kwargs)

        async def answer(self, *args, **kwargs):
            events.append("answer")
            return await super().answer(*args, **kwargs)

    safe_render = _compile_function(
        "safe_edit_or_send",
        {
            "inspect": __import__("inspect"),
            "is_soft_telegram_edit_error": lambda _error: False,
            "sanitize_log_text": str,
            "logger": logging.getLogger("videoedit-render-transaction"),
        },
    )
    query = Query(943, "videoedit|manual")

    asyncio.run(
        safe_render(
            query,
            "upload",
            post_render=lambda: events.append("commit"),
        )
    )

    assert events == ["render", "commit", "answer"]
    assert len(query.answers) == 1


def test_legacy_videoedit_tail_uses_the_same_render_commit_answer_transaction() -> None:
    events: list[str] = []

    class Query(_Query):
        async def edit_message_text(self, text: str, **kwargs):
            events.append("render")
            return await super().edit_message_text(text, **kwargs)

        async def answer(self, *args, **kwargs):
            events.append("answer")
            return await super().answer(*args, **kwargs)

    safe_render = _compile_function(
        "safe_edit_or_send",
        {
            "inspect": __import__("inspect"),
            "is_soft_telegram_edit_error": lambda _error: False,
            "sanitize_log_text": str,
            "logger": logging.getLogger("videoedit-legacy-render-transaction"),
        },
    )
    query = Query(944, "video_tail|review|open")
    query._video_edit_transactional = True

    asyncio.run(
        safe_render(
            query,
            "review",
            post_render=lambda: events.append("commit"),
        )
    )

    assert events == ["render", "commit", "answer"]
    assert len(query.answers) == 1


def test_live_ai_pick_is_not_intercepted_by_the_legacy_control_guard() -> None:
    callback = _function_source("handle_video_editor_callback")
    legacy_start = callback.index("VIDEO_EDIT_LEGACY_AI_CONTROL_ACTIONS")
    legacy_end = callback.index("if action in VIDEO_EDIT_LEGACY_AI_CONTROL_ACTIONS", legacy_start)
    legacy_set = callback[legacy_start:legacy_end]

    assert '"ai_pick"' not in legacy_set
    assert 'if action == "ai_pick":' in callback[legacy_end:]


def test_stale_review_recreates_a_complete_manual_upload_intake() -> None:
    callback = _function_source("handle_video_editor_callback")
    review_start = callback.index('if action == "review":')
    review_end = callback.index('if action == "confirmation":', review_start)
    review = callback[review_start:review_end]

    assert "start_video_edit_lane_state" in review
    assert '"manual_edit"' in review
    assert video_edit_state_machine.start_lane("manual_edit")["awaiting_media"] is True


def test_legacy_start_cannot_advance_an_unchanged_plan_to_review() -> None:
    callback = _function_source("handle_video_editor_callback")
    start = callback.index('if action == "start":')
    end = callback.index("return await safe_edit_or_send(query, video_edit_hub_text", start)
    block = callback[start:end]

    assert "plan_has_effective_operation" in block
    assert "split_ranges" in block


def test_quality_source_keyboard_has_no_duplicate_rows_or_callbacks() -> None:
    keyboard = _compile_function(
        "video_quality_enhance_source_keyboard",
        {
            "video_scene3_keyboard": lambda rows: rows,
            "ui_text": lambda _lang, key: "⬅️ Quay lại" if key == "common.back" else "🏠 Menu chính",
            "video_edit_runtime_capability_ready": lambda *_args, **_kwargs: True,
        },
    )
    rows = keyboard("vi")
    callbacks = [callback for row in rows for _label, callback in row]
    assert len(callbacks) == len(set(callbacks))
    assert rows.count(rows[1]) == 1
    assert "videoedit|restore_pick|enhance_resolution_normalize" in callbacks


def test_manual_audio_exposes_runtime_gated_loudness_normalization() -> None:
    keyboard = _function_source("video_edit_audio_keyboard")
    callback = _function_source("handle_video_editor_callback")

    assert "video_edit_runtime_capability_ready" in keyboard
    assert '"videoedit|audio_loudnorm"' in keyboard
    action_start = callback.index('if action == "audio_loudnorm":')
    action_end = callback.index('if action == "audio_component":', action_start)
    action = callback[action_start:action_end]
    assert "video_edit_runtime_capability_admission" in action
    assert 'video_edit_capabilities.plan_patch("audio_loudnorm")' in action
    assert "manual_edit_plan=plan" in action


def test_runtime_filtered_keyboards_hide_unavailable_local_filters() -> None:
    namespace = {
        "video_scene3_keyboard": lambda rows: rows,
        "ui_text": lambda _lang, key: "⬅️ Quay lại" if key == "common.back" else "🏠 Menu chính",
        "video_edit_runtime_capability_ready": lambda key, *_args, **_kwargs: key in {
            "enhance_light_color",
            "effect_fade",
        },
        "video_edit_capabilities": video_edit_capabilities,
    }
    quality = _compile_function("video_quality_enhance_source_keyboard", dict(namespace))
    quality_rows = quality("vi", {"source_metadata": {"has_audio": True}}, runtime={})
    quality_callbacks = [callback for row in quality_rows for _label, callback in row]
    assert "videoedit|restore_pick|enhance_light_color" in quality_callbacks
    assert "videoedit|restore_pick|enhance_basic_sharpen" not in quality_callbacks
    assert "videoedit|restore_pick|enhance_denoise" not in quality_callbacks
    assert "videoedit|restore_pick|audio_loudnorm" not in quality_callbacks

    effects = _compile_function("video_edit_effects_keyboard", dict(namespace))
    effect_rows = effects(
        "vi",
        back_callback="videoedit|workspace",
        state={"source_metadata": {"has_audio": True}},
        runtime={},
    )
    effect_callbacks = [callback for row in effect_rows for _label, callback in row]
    assert "videoedit|effect_pick|effect_fade" in effect_callbacks
    assert "videoedit|effect_pick|effect_vignette" not in effect_callbacks
    assert "videoedit|effect_pick|effect_slow_zoom" not in effect_callbacks
    assert len(effect_callbacks) == len(set(effect_callbacks))


def test_runtime_capability_ui_requires_fresh_matching_worker_snapshot() -> None:
    admission = _function_source("video_edit_runtime_capability_admission")
    status = _function_source("video_edit_worker_status_payload")
    assert 'worker.get("connected")' in admission
    assert 'worker.get("worker_owner")' in admission
    assert 'worker.get("engine_route")' in admission
    assert 'worker.get("worker_id")' in admission
    assert 'worker.get("video_edit_filter_worker_id")' in admission
    assert "local_worker_filter_snapshot_owner_mismatch" in admission
    assert 'get_system_setting("local_worker:ffmpeg_path_seen"' in status
    assert '"ffmpeg_path": reported_ffmpeg_path' in status

    heartbeat = _function_source("internal_worker_heartbeat")
    assert 'payload.get("video_edit_filter_worker_id") or ""' in heartbeat
    assert 'payload.get("video_edit_filter_ffmpeg_path") or ""' in heartbeat
    assert 'payload.get("video_edit_filter_worker_id") or worker_id' not in heartbeat
    assert 'payload.get("video_edit_filter_ffmpeg_path") or ffmpeg_path' not in heartbeat


def test_runtime_capability_ui_fails_closed_on_worker_identity_or_heartbeat() -> None:
    runtime = {
        "enabled": True,
        "poll_enabled": True,
        "token_configured": True,
        "connected": True,
        "ffmpeg_path_configured": True,
        "ffprobe_path_configured": True,
        "heartbeat_contract_version": 1,
        "heartbeat_age_seconds": 1,
        "worker_id": "video-edit-worker-1",
        "worker_owner": video_editengine1.OUTBOX_OWNER,
        "engine_route": video_editengine1.ENGINE_ROUTE,
        "capabilities": [video_editengine1.WORKER_CAPABILITY],
        "video_edit_filters_known": True,
        "video_edit_filters": ["format", "unsharp"],
        "video_edit_filter_worker_id": "video-edit-worker-1",
        "ffmpeg_path": "C:/ffmpeg/bin/ffmpeg.exe",
        "video_edit_filter_ffmpeg_path": "C:/ffmpeg/bin/ffmpeg.exe",
    }
    admission = _compile_function(
        "video_edit_runtime_capability_admission",
        {
            "video_edit_worker_status_payload": lambda: deepcopy(runtime),
            "video_edit_capabilities": video_edit_capabilities,
            "video_editengine1": video_editengine1,
        },
    )
    state = {"source_metadata": {"has_audio": True}}

    assert admission("enhance_basic_sharpen", state, runtime=runtime)["ready"] is True

    blockers = (
        ({"connected": False}, "local_worker_heartbeat_stale"),
        ({"heartbeat_contract_version": 0}, "local_worker_contract_missing"),
        ({"heartbeat_age_seconds": video_editengine1.HEARTBEAT_TTL_SECONDS + 1}, "local_worker_heartbeat_stale"),
        ({"worker_owner": "another-product"}, "local_worker_owner_mismatch"),
        ({"engine_route": "provider-route"}, "local_worker_route_mismatch"),
        ({"capabilities": []}, "local_worker_capability_missing"),
        ({"video_edit_filter_worker_id": "another-worker"}, "local_worker_filter_snapshot_owner_mismatch"),
        ({"video_edit_filter_ffmpeg_path": "D:/other/ffmpeg.exe"}, "local_worker_filter_snapshot_path_mismatch"),
    )
    for overrides, reason in blockers:
        candidate = {**runtime, **overrides}
        result = admission("enhance_basic_sharpen", state, runtime=candidate)
        assert result["ready"] is False
        assert result["reason"] == reason


def test_local_confirmation_and_status_back_targets_stay_in_videoedit_namespace() -> None:
    review = _function_source("video_local_review_keyboard")
    confirmation = _function_source("video_local_confirmation_keyboard")
    confirmation_text = _function_source("video_local_confirmation_text")
    status = _function_source("video_editor_status_keyboard")
    assert "videoedit|confirmation" in review
    assert '"videoedit|workspace"' in review
    assert "videoedit|options|" not in review
    assert confirmation.count("videoedit|confirm_local") == 1
    assert "video_edit_state_machine.confirmation_token" in confirmation
    assert '"videoedit|review"' in confirmation
    assert "videoedit|options|" not in confirmation
    assert 'callback_data="videoedit|hub"' in status
    assert "quyền sử dụng" in confirmation_text.lower()
    assert "logo" in confirmation_text.lower()
    assert "âm thanh" in confirmation_text.lower()
    assert "source_display_name" in confirmation_text
    assert "expected_manual_duration_ms" in confirmation_text
    assert "Chính sách âm thanh" in confirmation_text

    source_info = _function_source("video_local_source_summary_text")
    assert "format_name" in source_info
    assert "Định dạng" in source_info


def test_rotate_flip_child_returns_to_the_transform_parent() -> None:
    keyboard = _function_source("video_local_rotate_flip_keyboard")
    assert '"videoedit|transform"' in keyboard
    assert '"videoedit|workspace"' not in keyboard

    callback = _function_source("handle_video_editor_callback")
    start = callback.index('if action == "manual_rotate_flip":')
    end = callback.index('if action == "brightness":', start)
    block = callback[start:end]
    assert 'parent_callback="videoedit|transform"' in block


def test_successful_inputs_clear_pending_resume_state_before_workspace() -> None:
    helper = _function_source("return_video_editor_workspace")
    assert 'screen_id="workspace"' in helper or '"workspace"' in helper
    assert 'pending_field=""' in helper
    assert 'return_to="workspace"' in helper

    pending_media = _function_source("handle_video_editor_pending_upload")
    pending_text = _function_source("handle_video_editor_pending_text")
    callback = _function_source("handle_video_editor_callback")
    for marker in (
        'if step == "await_srt":',
        'if step == "await_concat_order":',
        'if step in {"await_trim_edges", "await_trim_range"}:',
        'if step == "await_text_overlay":',
        'if step == "await_split_fixed":',
    ):
        source = pending_media if marker == 'if step == "await_srt":' else pending_text
        start = source.index(marker)
        end = source.find("\n    if step == ", start + 1)
        block = source[start:end if end >= 0 else len(source)]
        assert "return_video_editor_workspace(" in block

    for marker in ('if action == "concat_done":', 'if action == "set":'):
        start = callback.index(marker)
        end = callback.find('\n    if action == "', start + 1)
        block = callback[start:end if end >= 0 else len(callback)]
        assert "return_video_editor_workspace(" in block


def test_review_route_guards_incomplete_split_before_confirmation() -> None:
    callback = _function_source("handle_video_editor_callback")
    assert callback.count('if action == "review":') == 1
    review_start = callback.index('if action == "review":')
    confirmation_start = callback.index('if action == "confirmation":', review_start)
    review_block = callback[review_start:confirmation_start]
    assert 'tool == "split" and not state.get("split_ranges")' in review_block
    assert review_block.index("split_ranges") < review_block.index("review_revision")
    assert "candidate = {" in review_block
    assert "post_render=commit_review" in review_block
    confirmation_block = callback[confirmation_start:callback.index('if action == "confirm_local":', confirmation_start)]
    assert 'str(state.get("step") or "") != "review"' in confirmation_block
    assert 'current_screen="confirmation"' in confirmation_block
    assert "candidate = {" in confirmation_block
    assert "post_render=commit_confirmation" in confirmation_block


def test_local_submit_requires_the_final_confirmation_screen() -> None:
    submit = _function_source("submit_video_edit_local_free_job")
    assert 'str(state.get("step") or "") != "confirmation"' in submit
    assert 'str(state.get("current_screen") or "") != "confirmation"' in submit
    assert 'str(state.get("status") or "") != "confirmation_ready"' in submit

    callback = _function_source("handle_video_editor_callback")
    confirm_start = callback.index('if action == "confirm_local":')
    confirm_end = callback.index('if action == "start":', confirm_start)
    confirm_block = callback[confirm_start:confirm_end]
    assert "video_edit_state_machine.confirmation_token" in confirm_block
    assert "parts[2]" in confirm_block
    assert "Nút xác nhận đã cũ" in confirm_block
    assert confirm_block.index("confirmation_token") < confirm_block.index("submit_video_edit_local_free_job")


def test_ai_status_is_a_read_only_alias_for_the_canonical_local_job_status() -> None:
    callback = _function_source("handle_video_editor_callback")
    start = callback.index('if action == "ai_status":')
    end = callback.index('if action.startswith("ai_"):', start)
    status_block = callback[start:end]
    assert "get_local_worker_job(job_id)" in status_block
    assert "video_editengine1.WORKER_JOB_TYPE" in status_block
    assert "video_editor_job_status_text(job, lang)" in status_block
    assert "video_editor_status_keyboard(job_id, lang)" in status_block
    assert "create_job(" not in status_block
    assert "submit_video_edit" not in status_block


def test_every_workspace_rerender_preserves_the_exact_entry_lane_state() -> None:
    sources = "\n".join(
        _function_source(name)
        for name in (
            "handle_video_editor_pending_upload",
            "handle_video_editor_pending_text",
            "handle_video_editor_callback",
        )
    )
    assert "video_local_manual_options_keyboard(lang)" not in sources
    assert "video_local_manual_options_keyboard(lang, current)" in sources
    assert "video_local_manual_options_keyboard(lang, state)" in sources


def test_manual_audio_exposes_a_real_zero_volume_mute_action() -> None:
    keyboard = _function_source("video_edit_audio_master_keyboard")
    callback = _function_source("handle_video_editor_callback")
    assert "🔇 Tắt tiếng" in keyboard
    assert "videoedit|audio_set|0" in keyboard
    start = callback.index('if action == "audio_set":')
    end = callback.index('if action == "audio_custom":', start)
    block = callback[start:end]
    assert "{0, 20, 40, 60, 80, 100}" in block
    assert 'plan["volume"] = percent / 100' in block

    audio_text = _compile_function(
        "video_edit_audio_text",
        {
            "html": html,
            "safe_int": lambda value, default=0: int(value if value is not None else default),
            "video_edit_capabilities": video_edit_capabilities,
        },
    )
    rendered = audio_text(
        {
            "source_file_id": "source-video",
            "source_metadata": {"has_audio": True},
            "manual_edit_plan": {"volume": 0.0},
        },
        "vi",
    )
    assert "Âm lượng tổng đang chọn: <b>0%</b>" in rendered


def test_effect_selection_keeps_back_on_the_exact_effects_parent() -> None:
    callback = _function_source("handle_video_editor_callback")
    start = callback.index('if action == "effect_pick":')
    end = callback.index('if action == "restore":', start)
    block = callback[start:end]
    assert 'back_callback="videoedit|workspace"' in block
    assert 'back_callback="videoedit|options|manual"' not in block


def test_legacy_vertical_ratio_and_method_buttons_keep_their_advertised_value() -> None:
    callback = _function_source("handle_video_editor_callback")
    normalize_start = callback.index("action = video_editor_normalize_action(raw_action)")
    normalize_end = callback.index('if action == "guide":', normalize_start)
    normalization = callback[normalize_start:normalize_end]
    assert 'legacy_raw_action == "vertical"' in normalization
    assert 'legacy_raw_action in {"ratio", "method", "preset"}' in normalization
    assert "len(parts) > 2" in normalization

    vertical_start = callback.index('if action == "vertical":')
    preset_start = callback.index('if action == "preset":', vertical_start)
    vertical = callback[vertical_start:preset_start]
    assert '{"aspect_ratio": "9:16", "mode": "fit"}' in vertical

    ratio_start = callback.index('if action == "ratio":')
    method_start = callback.index('if action == "method":', ratio_start)
    ratio = callback[ratio_start:method_start]
    method_end = callback.index('if action in {"trim_edges", "trim_range"}:', method_start)
    method = callback[method_start:method_end]
    assert '.replace("x", ":")' in ratio
    assert 'crop["mode"]' in method
    assert 'raw_method == "blur"' in method
    assert "Nền mờ chưa có bộ lọc local" in method
    assert 'raw_method = "fit" if raw_method == "blur" else raw_method' not in method


def test_legacy_soft_clean_and_sharpen_are_real_local_edits_without_reupload() -> None:
    callback = _function_source("handle_video_editor_callback")
    preset_start = callback.index('if action == "preset":')
    ratio_start = callback.index('if action == "ratio":', preset_start)
    preset = callback[preset_start:ratio_start]
    assert '"video_soft_clean": "soft_clean"' in preset
    assert "soft_clean" in video_local_editing.COLOR_PRESETS

    normalization_start = callback.index("action = video_editor_normalize_action(raw_action)")
    normalization_end = callback.index('if action == "guide":', normalization_start)
    normalization = callback[normalization_start:normalization_end]
    assert 'legacy_raw_action == "sharpen"' in normalization
    assert 'action = "legacy_sharpen"' in normalization

    sharpen_start = callback.index('if action == "legacy_sharpen":')
    sharpen_end = callback.index('if action == "compress":', sharpen_start)
    sharpen = callback[sharpen_start:sharpen_end]
    assert 'video_edit_runtime_capability_admission("enhance_basic_sharpen", state)' in sharpen
    assert 'video_edit_capabilities.plan_patch("enhance_basic_sharpen")' in sharpen
    assert "video_edit_capabilities.merge_plan_patch" in sharpen
    assert "manual_edit_plan=plan" in sharpen
    assert "clear_video_editor_pending" not in sharpen
    assert "start_video_edit_lane_state" not in sharpen


def test_legacy_menu_back_preserves_a_ready_source_and_returns_to_workspace() -> None:
    callback = _function_source("handle_video_editor_callback")
    assert 'if raw_action == "hub":' in callback
    start = callback.index('if raw_action == "menu":')
    end = callback.index("legacy_raw_action = raw_action", start)
    block = callback[start:end]
    assert "get_video_editor_pending(uid)" in block
    assert 'state.get("source_file_id")' in block
    assert 'state.get("inspection_complete")' in block
    assert "update_video_editor_screen(" in block
    assert '"workspace"' in block
    assert "video_local_manual_options_keyboard(lang, current)" in block
    assert "clear_video_editor_pending(uid)" not in block
    legacy_keyboards = _function_source("video_editor_preset_keyboard") + _function_source("video_editor_ratio_keyboard")
    assert "videoedit|workspace" in legacy_keyboards
    assert "videoedit|menu" not in legacy_keyboards


def test_legacy_shared_tail_redirects_video_edit_before_any_commercial_gate() -> None:
    callback = _function_source("handle_video_tail_callback")
    redirect_index = callback.index('if owner == "video_edit":')
    assert redirect_index < callback.index("save_video_tail9_state")
    assert redirect_index < callback.index('if section != "confirm":')
    assert redirect_index < callback.index("video_tail9.invoice_allowed")
    redirect = callback[redirect_index:callback.index('if section != "confirm":', redirect_index)]
    assert "video_edit_legacy_tail_compatibility(" in redirect
    assert "submit_local_video_editor_job" not in callback

    helper = _function_source("video_edit_legacy_tail_compatibility")
    assert "video_local_confirmation_text(current, lang, stage=\"review\")" in helper
    assert "video_local_review_keyboard(tool, lang)" in helper
    assert "video_editor_job_status_text(job, lang)" in helper
    assert "video_editor_status_keyboard(job_id, lang)" in helper
    for forbidden in (
        "get_user(",
        "invoice_allowed",
        "submit_local_video_editor_job",
        "spend_fixed_credit",
        "provider_call=True",
        "submit_video_ai_edit_job",
    ):
        assert forbidden not in helper


def test_legacy_shared_tail_failure_cannot_reenter_the_commercial_renderer() -> None:
    callback = _function_source("handle_video_tail_callback")
    redirect_index = callback.index('if owner == "video_edit":')
    redirect = callback[redirect_index:callback.index("save_video_tail9_state", redirect_index)]

    assert "video_edit_legacy_tail_compatibility(" in redirect
    assert "except Exception" in redirect
    assert 'setattr(query, "_video_edit_transactional", True)' in redirect
    assert redirect.index("video_edit_legacy_tail_compatibility(") < redirect.index("show_alert=True")
    assert "await query.answer()" not in redirect[:redirect.index("video_edit_legacy_tail_compatibility(")]
    assert "video_tail9_render" not in redirect


def test_legacy_shared_tail_commits_review_state_only_after_telegram_render() -> None:
    events: list[str] = []
    pending = {"video_editor:945": _default_state(945)}

    async def failed_render(*_args, **_kwargs):
        events.append("render")
        raise RuntimeError("telegram render failed")

    def commit_review(user_id: int, step: str, **fields):
        events.append("commit")
        pending[f"video_editor:{user_id}"] = {"step": step, **fields}
        return dict(pending[f"video_editor:{user_id}"])

    helper = _compile_function(
        "video_edit_legacy_tail_compatibility",
        {
            "get_user_language": lambda _uid: "vi",
            "get_video_editor_pending": lambda uid: pending.get(f"video_editor:{uid}"),
            "get_local_worker_job": lambda _job_id: None,
            "video_editengine1": video_editengine1,
            "safe_int": lambda value, default=0: int(value or default),
            "video_edit_state_machine": video_edit_state_machine,
            "video_editor_pending_key": lambda uid: f"video_editor:{uid}",
            "USER_PENDING": pending,
            "json": json,
            "set_video_editor_pending": commit_review,
            "safe_edit_or_send": failed_render,
            "video_local_confirmation_text": lambda *_args, **_kwargs: "review",
            "video_local_review_keyboard": lambda *_args, **_kwargs: "keyboard",
        },
    )
    query = _Query(945, "video_tail|review|open")

    with pytest.raises(RuntimeError, match="telegram render failed"):
        asyncio.run(helper(query, 945, {}, pending["video_editor:945"]))

    assert events == ["render"]
    assert pending["video_editor:945"]["current_screen"] == "workspace"


def test_local_free_job_render_failure_is_not_silently_swallowed_after_commit() -> None:
    submit = _function_source("submit_video_edit_local_free_job")
    failure = submit[submit.index('logger.exception("video local-free confirmation UI failed")') - 80:]

    terminal_block = failure.split("update_video_editor_pending", 1)[0]
    assert "raise" in terminal_block
    assert terminal_block.index("raise") < terminal_block.index("return True")


def test_local_free_job_status_commits_before_callback_answer() -> None:
    submit = _function_source("submit_video_edit_local_free_job")

    assert "def commit_job_status" in submit
    assert 'update_video_editor_pending(uid, "job_status", **candidate)' in submit
    assert "post_render=commit_job_status" in submit


def test_legacy_videoedit_start_only_reopens_confirmation_and_cannot_create_a_job() -> None:
    callback = _function_source("handle_video_editor_callback")
    start = callback.index('if action == "start":')
    block = callback[start:callback.index("return await safe_edit_or_send(query, video_edit_hub_text", start)]

    assert "submit_video_edit_local_free_job" not in block
    assert "video_local_confirmation_text" in block
    assert "video_local_confirmation_keyboard" in block


def test_stale_video_edit_tail_marker_cannot_fall_into_product_video() -> None:
    context = _function_source("video_tail9_context")
    assert "edit_route_marker" in context
    assert 'str(edit_host.get("flow_owner") or "") == "video_edit"' in context
    assert 'str(edit_host.get("product_type") or "") == video_editengine1.PRODUCT_TYPE' in context
    assert '"video_ai_edit"' in context
    assert '"video_local_edit"' in context
    assert 'if edit_ready or edit_route_marker:' in context
    assert 'owner = "video_edit"' in context


def test_legacy_no_source_recovery_creates_a_complete_local_lane_session() -> None:
    callback = _function_source("handle_video_editor_callback")
    allowlist_start = callback.index("VIDEO_EDIT_COMPAT_UPLOAD_ACTIONS = {")
    allowlist_end = callback.index("}", allowlist_start)
    allowlist = callback[allowlist_start:allowlist_end]
    for action in ('"resolution"', '"srt"', '"volume"'):
        assert action in allowlist

    missing_source_commit = callback.index("def commit_missing_source_upload")
    recovery_start = callback.rindex(
        'if not state.get("source_file_id") or not state.get("inspection_complete"):',
        0,
        missing_source_commit,
    )
    recovery_end = callback.index('if action == "workspace":', missing_source_commit)
    recovery = callback[recovery_start:recovery_end]
    assert "start_video_edit_lane_state(" in recovery
    assert "requested_group=requested_group" in recovery
    assert 'set_video_editor_pending(\n            uid,\n            "await_video"' not in recovery


def test_delivery_unknown_status_is_terminal_and_never_claims_waiting_or_retry() -> None:
    status = _function_source("video_editor_job_status_text")
    assert 'canonical_status == "delivery_unknown"' in status
    assert "Cần kiểm tra việc giao file" in status
    assert "không tự gửi lại" in status.lower()


def test_free_delivered_status_never_claims_a_pending_fee() -> None:
    status = _function_source("video_editor_job_status_text")
    assert "confirmed_price_xu <= 0" in status
    assert "miễn phí 0 Xu" in status
    free_branch = status[status.index("confirmed_price_xu <= 0"):status.index('elif charge_state == "charged"')]
    assert "đang được ghi nhận" not in free_branch


def test_split_confirmation_truthfully_promises_multiple_validated_mp4_parts() -> None:
    confirmation = _compile_function(
        "video_local_confirmation_text",
        {
            "html": __import__("html"),
            "safe_int": lambda value, default=0: int(value or default),
            "video_local_editing": video_local_editing,
            "_video_local_duration_text": lambda value: f"{int(value)}ms",
        },
    )
    text = confirmation(
        {
            "selected_tool": "split",
            "split_ranges": [
                {"start_ms": 0, "end_ms": 5_000},
                {"start_ms": 5_000, "end_ms": 10_000},
            ],
        },
        "vi",
    )
    assert "2 file MP4" in text
    assert "một file MP4" not in text


def test_brightness_paths_do_not_enter_shared_commercial_tail() -> None:
    pending = _function_source("handle_video_editor_pending_text")
    callback = _function_source("handle_video_editor_callback")
    brightness_start = pending.index('if step == "await_brightness":')
    brightness_end = pending.index('if step == "await_audio_volume":', brightness_start)
    assert "video_tail9_render" not in pending[brightness_start:brightness_end]
    set_start = callback.index('if action == "brightness_set":')
    set_end = callback.index('if action == "brightness_custom":', set_start)
    assert "video_tail9_render" not in callback[set_start:set_end]


def test_workspace_back_preserves_the_lane_that_created_the_local_plan() -> None:
    pending = _function_source("handle_video_editor_pending_text")
    callback = _function_source("handle_video_editor_callback")

    ai_start = pending.index('if step == "await_ai_intent":')
    ai_end = pending.index('if step == "await_ai_duration":', ai_start)
    ai_block = pending[ai_start:ai_end]
    assert 'entry_parent_callback="videoedit|ai_source"' in ai_block
    assert 'edit_mode="ai_edit"' in ai_block

    restore_start = callback.index('if action == "restore_pick":')
    restore_end = callback.index('if action == "ai":', restore_start)
    restore_block = callback[restore_start:restore_end]
    assert 'entry_parent_callback="videoedit|quality_source"' in restore_block
    assert 'edit_mode="quality_enhance"' in restore_block

    manual_start = callback.index('if action == "manual":')
    manual_end = callback.index('state = dict(get_video_editor_pending(uid) or {})', manual_start)
    manual_block = callback[manual_start:manual_end]
    assert "entry_parent_callback" in manual_block
    assert manual_block.index("source_file_id") < manual_block.index("clear_video_editor_pending")
    assert "video_local_source_summary_text" in manual_block
    assert "video_local_manual_options_text" not in manual_block

    keyboard = _function_source("video_local_manual_options_keyboard")
    assert "entry_parent_callback" in keyboard
    assert '(ui_text(lang, "common.back"), "videoedit|manual")' not in keyboard

    workspace_start = callback.index('if action == "workspace":')
    workspace_end = callback.index('if action == "frame":', workspace_start)
    workspace_block = callback[workspace_start:workspace_end]
    assert "entry_parent_callback" in workspace_block
    assert 'lane="manual_edit"' not in workspace_block
    assert "video_local_manual_options_keyboard(lang, current)" in workspace_block

    done_start = callback.index('if action == "manual_done":')
    done_end = callback.index('if action in {"source_summary", "source_info"}:', done_start)
    done_block = callback[done_start:done_end]
    assert "entry_parent_callback" in done_block
    assert 'parent_callback="videoedit|manual"' not in done_block
    assert "video_local_manual_options_keyboard(lang, current)" in done_block


def test_legacy_requested_group_is_consumed_after_upload() -> None:
    upload = _function_source("handle_video_editor_pending_upload")
    resume = _function_source("resume_video_editor_requested_group")
    assert 'requested_group = str(state.get("requested_group") or "")' in upload
    assert "resume_video_editor_requested_group(" in upload
    assert "requested_group_screen" in resume
    for group in ("cut", "join", "frame", "resolution", "audio", "effects", "overlay", "color", "review"):
        assert f'"{group}"' in resume


def test_legacy_requested_group_resume_strips_transient_state_without_duplicate_kwargs() -> None:
    captured: dict = {}

    def update_screen(_uid: int, screen_id: str, *, parent_callback: str, **fields):
        captured.update({
            "screen_id": screen_id,
            "parent_callback": parent_callback,
            "fields": deepcopy(fields),
        })
        return deepcopy(fields)

    resume = _compile_function(
        "resume_video_editor_requested_group",
        {
            "video_edit_state_machine": video_edit_state_machine,
            "update_video_editor_screen": update_screen,
            "video_local_cut_options_text": lambda _lang: "cut",
            "video_local_cut_options_keyboard": lambda _lang: "cut-keyboard",
        },
    )
    message = _Message()
    state = _default_state(
        908,
        step="await_video",
        current_screen="upload",
        screen_id="upload",
        parent_callback="videoedit|manual",
        requested_group="cut",
    )

    assert asyncio.run(
        resume(
            SimpleNamespace(message=message),
            908,
            state,
            "cut",
            "vi",
        )
    ) is True
    assert captured["screen_id"] == "cut"
    assert captured["parent_callback"] == "videoedit|workspace"
    assert "step" not in captured["fields"]
    assert "current_screen" not in captured["fields"]
    assert "parent_callback" not in captured["fields"]
    assert captured["fields"]["requested_group"] == ""
    assert message.replies[-1][0] == "cut"


def test_invalid_logo_srt_and_concat_inputs_keep_their_exact_parent() -> None:
    upload = _function_source("handle_video_editor_pending_upload")
    legacy = upload[upload.index('step = str(state.get("step") or "")'):]
    metadata_failure_start = legacy.index('if not metadata.get("ok"):')
    metadata_failure_end = legacy.index("cache_recent_media_state", metadata_failure_start)
    metadata_failure = legacy[metadata_failure_start:metadata_failure_end]
    assert "back_callback=back_callback" in metadata_failure

    logo_start = legacy.index('if step == "await_logo":')
    srt_start = legacy.index('if step == "await_srt":', logo_start)
    source_start = legacy.index("source = video_editor_source_from_update", srt_start)
    logo_block = legacy[logo_start:srt_start]
    srt_block = legacy[srt_start:source_start]
    assert 'back_callback="videoedit|overlay"' in logo_block
    assert 'back_callback="videoedit|overlay"' in srt_block

    pending_text = _function_source("handle_video_editor_pending_text")
    order_start = pending_text.index('if step == "await_concat_order":')
    order_end = pending_text.index('if step == "await_ai_intent":', order_start)
    assert 'back_callback="videoedit|join"' in pending_text[order_start:order_end]

    recovery = _function_source("recover_product_video_media_failure")
    assert 'if step in {"await_logo", "await_srt", "await_concat"}:' in recovery
    assert 'back_callback="videoedit|overlay"' in recovery
    assert 'back_callback="videoedit|join"' in recovery


def test_webp_logo_is_accepted_consistently_by_bot_and_worker_contract() -> None:
    extractor = _compile_function(
        "video_editor_aux_source_from_update",
        {
            "safe_int": lambda value, default=0: int(value or default),
            "video_local_validation": video_local_validation,
        },
    )
    document = SimpleNamespace(
        file_id="webp-logo-file",
        file_name="brand.webp",
        mime_type="image/webp",
        file_size=2048,
    )
    result = extractor(
        SimpleNamespace(
            message=SimpleNamespace(photo=[], document=document),
        ),
        "logo",
    )

    assert result["file_id"] == "webp-logo-file"
    assert result["file_name"] == "brand.webp"
    assert ".webp" in video_local_validation.ALLOWED_LOGO_EXTENSIONS


def test_videoedit_guides_never_leave_the_product_or_lose_the_caller() -> None:
    suggestions = _function_source("video_ai_edit_suggestions_keyboard")
    effects = _function_source("video_edit_effects_keyboard")
    assistant_intro = _function_source("video_ai_edit_intro_keyboard")
    assistant_copy = _function_source("video_ai_edit_intro_text")
    audio = _function_source("video_edit_audio_keyboard")
    callback = _function_source("handle_video_editor_callback")
    assert "menu|guide_video_ai" not in suggestions
    assert "videoedit|guide|ai_suggestions" in suggestions
    assert "videoedit|guide|effects" in effects
    assert "videoedit|guide|ai" in assistant_intro
    assert "videoedit|guide|audio" in audio
    assert "0 Xu" in assistant_copy
    assert "báo giá" not in assistant_copy.lower()
    assert "quote" not in assistant_copy.lower()
    guide_start = callback.index('if action == "guide":')
    guide_end = callback.index("VIDEO_EDIT_STATELESS_ACTIONS", guide_start)
    guide_block = callback[guide_start:guide_end]
    assert '"effects": "videoedit|effects"' in guide_block
    assert '"audio": "videoedit|audio"' in guide_block
    assert '"ai_suggestions": "videoedit|ai_suggestions"' in guide_block


def test_local_status_rejects_non_video_edit_worker_jobs() -> None:
    callback = _function_source("handle_video_editor_callback")
    status_start = callback.index('if action == "status":')
    status_end = callback.index('if action == "quick":', status_start)
    status_block = callback[status_start:status_end]
    assert 'str(job.get("job_type") or "") != video_editengine1.WORKER_JOB_TYPE' in status_block


def test_source_info_back_resolves_quality_and_assistant_parents() -> None:
    callback = _function_source("handle_video_editor_callback")
    start = callback.index('if action in {"source_summary", "source_info"}:')
    end = callback.index('if action == "options":', start)
    block = callback[start:end]
    assert '"quality_enhance": "videoedit|quality_source"' in block
    assert '"ai_edit": "videoedit|ai_source"' in block


@pytest.mark.parametrize(
    "callback_value",
    [
        "provider",
        "8k",
        "diagonal",
        "magic",
        "abc",
        "nan",
        "inf",
        "2",
    ],
)
def test_callback_value_normalizer_rejects_malformed_values(callback_value: str) -> None:
    kinds = {
        "provider": "aspect",
        "8k": "resolution",
        "diagonal": "flip",
        "magic": "color_preset",
        "abc": "rotation",
        "nan": "speed",
        "inf": "volume",
        "2": "logo_opacity",
    }
    with pytest.raises(video_local_editing.LocalVideoEditError, match="callback_choice_invalid"):
        video_local_editing.normalize_callback_plan_choice(kinds[callback_value], callback_value)


def test_stale_state_and_videoedit_only_failure_guard_restore_contract_is_present() -> None:
    callback = _function_source("handle_video_editor_callback")
    guard = _function_source("video_editor_callback_state_guard")
    shared_guard = _function_source("video_public_callback_failure_guard")

    assert "VIDEO_EDIT_STATELESS_ACTIONS" in callback
    assert "Phiên chỉnh sửa đã hết hạn" in callback
    assert "clear_video_editor_pending" not in callback[
        callback.index("Phiên chỉnh sửa đã hết hạn") - 500:
        callback.index("Phiên chỉnh sửa đã hết hạn") + 500
    ]
    assert "snapshot" in guard
    assert "had_state" in guard
    assert "USER_PENDING[state_key]" in guard
    assert "video_editor_pending_key" in guard
    assert "video_editor_pending_key" not in shared_guard
    assert "_video_edit_render_failed" not in shared_guard


def test_videoedit_failure_guard_restores_a_hard_render_failure() -> None:
    pending = {"video_editor:904": {"step": "workspace", "manual_edit_plan": {"speed": 1.0}}}

    class ApplicationHandlerStop(Exception):
        pass

    guard = _compile_function(
        "video_editor_callback_state_guard",
        {
            "ApplicationHandlerStop": ApplicationHandlerStop,
            "safe_int": lambda value, default=0: int(value or default),
            "video_editor_pending_key": lambda user_id: f"video_editor:{user_id}",
            "USER_PENDING": pending,
            "json": json,
        },
    )

    async def hard_handler(update, _context):
        pending["video_editor:904"] = {"step": "mutated"}
        raise RuntimeError("render failed")

    query = _Query(904, "videoedit|set|speed|2")
    update = SimpleNamespace(callback_query=query)
    with pytest.raises(RuntimeError, match="render failed"):
        asyncio.run(guard(hard_handler)(update, SimpleNamespace()))
    assert pending["video_editor:904"] == {
        "step": "workspace",
        "manual_edit_plan": {"speed": 1.0},
    }


def test_message_state_guard_commits_success_and_rolls_back_failed_reply() -> None:
    pending = {"video_editor:907": {"step": "await_brightness", "manual_edit_plan": {"speed": 1.0}}}

    class ApplicationHandlerStop(Exception):
        pass

    guard = _compile_function(
        "video_editor_message_state_guard",
        {
            "ApplicationHandlerStop": ApplicationHandlerStop,
            "safe_int": lambda value, default=0: int(value or default),
            "video_editor_pending_key": lambda user_id: f"video_editor:{user_id}",
            "USER_PENDING": pending,
            "json": json,
        },
    )
    update = SimpleNamespace(effective_user=SimpleNamespace(id=907))

    async def failed_reply(_update, _context):
        pending["video_editor:907"] = {"step": "review", "manual_edit_plan": {"speed": 2.0}}
        raise RuntimeError("telegram reply failed")

    with pytest.raises(RuntimeError, match="telegram reply failed"):
        asyncio.run(guard(failed_reply)(update, SimpleNamespace()))
    assert pending["video_editor:907"] == {
        "step": "await_brightness",
        "manual_edit_plan": {"speed": 1.0},
    }

    async def successful_reply(_update, _context):
        pending["video_editor:907"] = {"step": "review", "manual_edit_plan": {"speed": 2.0}}
        return True

    assert asyncio.run(guard(successful_reply)(update, SimpleNamespace())) is True
    assert pending["video_editor:907"] == {
        "step": "review",
        "manual_edit_plan": {"speed": 2.0},
    }
    assert "@video_editor_message_state_guard\nasync def handle_video_editor_invalid_intake_text" in BOT_SOURCE
    assert "@video_editor_message_state_guard\nasync def handle_video_editor_pending_text" in BOT_SOURCE
    assert (
        "@product_video_media_failure_guard\n@video_editor_message_state_guard\n"
        "async def handle_video_editor_pending_upload"
    ) in BOT_SOURCE


def _init_job_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """CREATE TABLE local_worker_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                command TEXT,
                job_type TEXT,
                status TEXT,
                provider TEXT,
                input_file_id TEXT,
                created_at TEXT,
                xu_cost INTEGER,
                admin_only INTEGER,
                updated_at TEXT
            )"""
        )
        conn.commit()
    finally:
        conn.close()


def _ready_worker() -> dict:
    return {
        "enabled": True,
        "poll_enabled": True,
        "token_configured": True,
        "connected": True,
        "ffmpeg_path_configured": True,
        "ffprobe_path_configured": True,
        "delivery_configured": True,
        "heartbeat_contract_version": 1,
        "worker_owner": video_editengine1.OUTBOX_OWNER,
        "engine_route": video_editengine1.ENGINE_ROUTE,
        "capabilities": [video_editengine1.WORKER_CAPABILITY],
        "heartbeat_age_seconds": 1,
        "worker_id": "video-edit-test-worker",
        "video_edit_filters_known": True,
        "video_edit_filters": [
            "afade",
            "atempo",
            "eq",
            "fade",
            "format",
            "pad",
            "scale",
            "setsar",
            "setpts",
        ],
        "video_edit_filter_worker_id": "video-edit-test-worker",
        "ffmpeg_path": "C:/ffmpeg/bin/ffmpeg.exe",
        "video_edit_filter_ffmpeg_path": "C:/ffmpeg/bin/ffmpeg.exe",
    }


def _submit_namespace(db_path: Path, saved: dict) -> dict:
    async def render(query, text: str, **kwargs):
        post_render = kwargs.pop("post_render", None)
        result = await query.edit_message_text(text, **kwargs)
        if post_render:
            post_render()
        return result

    return {
        "get_user_language": lambda _uid: "vi",
        "safe_int": lambda value, default=0: int(value or default),
        "video_local_validation": video_local_validation,
        "video_edit_worker_status_payload": _ready_worker,
        "video_editengine1": video_editengine1,
        "VIDEO_TAIL9_STATE_KEY": "video_tail9",
        "LOCAL_WORKER_MAX_JOB_SECONDS": 1800,
        "db_connect": lambda: sqlite3.connect(db_path),
        "sqlite3": sqlite3,
        "logger": logging.getLogger("videoedit-submit-test"),
        "sanitize_log_text": lambda value: str(value),
        "safe_edit_or_send": render,
        "video_editor_status_keyboard": lambda job_id, _lang: f"status:{job_id}",
        "get_local_worker_job": lambda job_id: {
            "id": int(job_id),
            "user_id": "905",
            "job_type": video_editengine1.WORKER_JOB_TYPE,
            "status": "queued",
            "xu_cost": 0,
        },
        "video_editor_job_status_text": lambda job, _lang: f"Trạng thái tác vụ #{job['id']} · 0 Xu",
        "video_local_manual_options_keyboard": lambda *_args, **_kwargs: "workspace-keyboard",
        "video_edit_lane_upload_keyboard": lambda *_args: "upload-keyboard",
        "video_editor_upload_required_text": lambda _lang: "Cần video nguồn",
        "video_local_public_error": lambda reason: reason,
        "update_video_editor_pending": lambda _uid, step, **fields: saved.update({"step": step, **fields}) or deepcopy(saved),
    }


def test_confirm_local_creates_exactly_one_free_job_and_duplicate_reuses_it(tmp_path: Path) -> None:
    db_path = tmp_path / "videoedit.sqlite3"
    _init_job_db(db_path)
    saved: dict = {}
    submit = _compile_function("submit_video_edit_local_free_job", _submit_namespace(db_path, saved))
    state = _default_state(
        905,
        step="confirmation",
        current_screen="confirmation",
        status="confirmation_ready",
        review_revision=3,
    )
    state["manual_edit_plan"]["brightness_percent"] = 120
    query = _Query(905, "videoedit|confirm_local")
    update = SimpleNamespace(
        callback_query=query,
        message=None,
        effective_user=query.from_user,
    )

    assert asyncio.run(submit(update, SimpleNamespace(), deepcopy(state))) is True
    second_query = _Query(905, "videoedit|confirm_local")
    second_update = SimpleNamespace(
        callback_query=second_query,
        message=None,
        effective_user=second_query.from_user,
    )
    assert asyncio.run(submit(second_update, SimpleNamespace(), {**state, **saved})) is True

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 1
        payload = json.loads(conn.execute("SELECT input_file_id FROM local_worker_jobs").fetchone()[0])
        canonical = conn.execute("SELECT quality_tier_id,price_xu,tail_json FROM video_edit_jobs").fetchone()
    finally:
        conn.close()

    assert payload["quality_tier_id"] == "local-free"
    assert payload["price_xu"] == 0
    assert payload["quoted_price_xu"] == 0
    assert payload["provider_call"] is False
    assert payload["charge_policy"] == "free_local_tool"
    assert canonical == ("local-free", 0, "{}")
    assert saved["step"] == "job_status"
    assert query.edits and all("0 Xu" in text for text, _kwargs in query.edits)
    assert second_query.edits and "0 Xu" in second_query.edits[-1][0]
    assert "trạng thái tác vụ" in second_query.edits[-1][0].lower()

    query.edits.clear()
    duplicate_state = {**state, **deepcopy(saved)}
    assert asyncio.run(submit(update, SimpleNamespace(), duplicate_state)) is True
    assert query.edits
    assert "Trạng thái tác vụ" in query.edits[-1][0]


def test_confirmation_retry_after_ui_failure_reuses_full_split_identity(tmp_path: Path) -> None:
    db_path = tmp_path / "videoedit-ui-retry.sqlite3"
    _init_job_db(db_path)
    saved: dict = {}
    namespace = _submit_namespace(db_path, saved)
    render_attempts = 0

    async def fail_first_render(query, text: str, **kwargs):
        nonlocal render_attempts
        render_attempts += 1
        if render_attempts == 1:
            raise RuntimeError("telegram edit failed before state commit")
        post_render = kwargs.pop("post_render", None)
        result = await query.edit_message_text(text, **kwargs)
        if post_render:
            post_render()
        return result

    namespace["safe_edit_or_send"] = fail_first_render
    submit = _compile_function("submit_video_edit_local_free_job", namespace)
    state = _default_state(
        907,
        step="confirmation",
        current_screen="confirmation",
        status="confirmation_ready",
        review_revision=3,
        state_revision=3,
        selected_tool="split",
        split_mode="custom",
        split_ranges=[
            {"index": 1, "start_ms": 0, "end_ms": 5_000},
            {"index": 2, "start_ms": 5_000, "end_ms": 10_000},
        ],
        coverage_required=True,
    )

    first_query = _Query(907, "videoedit|confirm_local")
    first_update = SimpleNamespace(
        callback_query=first_query,
        message=None,
        effective_user=first_query.from_user,
    )
    with pytest.raises(RuntimeError, match="telegram edit failed before state commit"):
        asyncio.run(submit(first_update, SimpleNamespace(), deepcopy(state)))
    assert saved == {}

    retry_query = _Query(907, "videoedit|confirm_local")
    retry_update = SimpleNamespace(
        callback_query=retry_query,
        message=None,
        effective_user=retry_query.from_user,
    )
    assert asyncio.run(submit(retry_update, SimpleNamespace(), deepcopy(state))) is True

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 1
    finally:
        conn.close()
    assert retry_query.edits
    assert "Đã nhận tác vụ chỉnh sửa local" in retry_query.edits[-1][0]
    assert "đang có một tác vụ" not in retry_query.edits[-1][0]
    assert saved["step"] == "job_status"


def test_stale_confirmation_creates_no_job_and_keeps_review_state(tmp_path: Path) -> None:
    db_path = tmp_path / "stale.sqlite3"
    _init_job_db(db_path)
    saved: dict = {}
    submit = _compile_function("submit_video_edit_local_free_job", _submit_namespace(db_path, saved))
    state = _default_state(
        906,
        step="confirmation",
        current_screen="confirmation",
        status="confirmation_ready",
        review_revision=2,
        state_revision=3,
    )
    query = _Query(906, "videoedit|confirm_local")
    update = SimpleNamespace(callback_query=query, message=None, effective_user=query.from_user)

    assert asyncio.run(submit(update, SimpleNamespace(), deepcopy(state))) is True

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 0
    finally:
        conn.close()
    assert any(kwargs.get("show_alert") is True for _args, kwargs in query.answers)
    assert saved == {}


def test_zero_price_worker_update_checks_price_before_charge_claim() -> None:
    source = _function_source("handle_video_local_edit_worker_job_update")
    assert "canonical_price_xu" in source
    assert "canonical_price_xu > 0" in source
    assert source.index("canonical_price_xu > 0") < source.index("video_editengine1.claim_charge")
