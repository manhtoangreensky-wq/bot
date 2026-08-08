from __future__ import annotations

import asyncio
import ast
import html
import json
import logging
import os
import re
import sqlite3
import time
from copy import deepcopy
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import (
    video_edit_capabilities,
    video_edit_media_transport,
    video_edit_state_machine,
    video_editengine1,
    video_local_editing,
    video_local_validation,
    video_smart_splitter,
    video_tail9,
)


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _top_level_function_sources() -> dict[str, str]:
    tree = ast.parse(BOT_SOURCE)
    lines = BOT_SOURCE.splitlines(keepends=True)
    return {
        node.name: "".join(lines[node.lineno - 1 : node.end_lineno]).rstrip() + "\n"
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.end_lineno is not None
    }


def _function_source(name: str) -> str:
    function_source = _top_level_function_sources().get(name)
    if function_source is None:
        raise AssertionError(f"missing function: {name}")
    return function_source


def _compile_function(name: str, namespace: dict):
    source = "from __future__ import annotations\n\n" + _function_source(name)
    exec(compile(source, filename="bot.py", mode="exec"), namespace)
    return namespace[name]


def _isolated_callback_flags() -> dict[str, ContextVar]:
    return {
        "_VIDEO_EDIT_CALLBACK_ANSWERED": ContextVar(
            "test_video_edit_callback_answered",
            default=False,
        ),
        "_VIDEO_EDIT_CALLBACK_TRANSACTIONAL": ContextVar(
            "test_video_edit_callback_transactional",
            default=False,
        ),
    }


def _isolated_guard_dependencies(pending: dict) -> tuple[ContextVar, dict]:
    tracker = ContextVar("test_video_editor_state_write", default=None)
    guard_snapshot = ContextVar("test_video_editor_guard_snapshot", default=None)
    submission_committed = ContextVar(
        "test_video_editor_submission_committed",
        default=False,
    )

    def snapshot(value) -> dict:
        return deepcopy(dict(value or {}))

    def rollback(user_id, write_record, original, *, snapshot_exists: bool):
        record = dict(write_record or {})
        key = f"video_editor:{user_id}"
        current_exists = key in pending
        current = snapshot(pending.get(key) or {})
        if (
            str(record.get("user_id") or "") != str(user_id)
            or current_exists != bool(record.get("exists"))
            or current != snapshot(record.get("state") or {})
        ):
            return False, current
        if snapshot_exists:
            pending[key] = snapshot(original)
            return True, snapshot(original)
        pending.pop(key, None)
        return True, {}

    async def rerender(*_args, **_kwargs):
        return None

    async def notify_unavailable(*_args, **_kwargs):
        return None

    class ApplicationHandlerStop(Exception):
        pass

    class VideoEditorStateCommitError(RuntimeError):
        def __init__(self, reason: str, winner: dict | None = None) -> None:
            super().__init__(reason)
            self.winner = snapshot(winner)

    class VideoEditorStateUnavailableError(RuntimeError):
        pass

    return tracker, {
        "ApplicationHandlerStop": ApplicationHandlerStop,
        "VideoEditorStateCommitError": VideoEditorStateCommitError,
        "VideoEditorStateUnavailableError": VideoEditorStateUnavailableError,
        "safe_int": lambda value, default=0: int(value or default),
        "video_editor_pending_key": lambda user_id: f"video_editor:{user_id}",
        "get_video_editor_pending": lambda user_id: snapshot(
            pending.get(f"video_editor:{user_id}") or {}
        ),
        "video_editor_state_snapshot": snapshot,
        "rollback_video_editor_guard_state": rollback,
        "rerender_video_editor_after_stale_commit": rerender,
        "notify_video_editor_state_unavailable": notify_unavailable,
        "get_user_language": lambda _uid: "vi",
        "html": html,
        "_VIDEO_EDITOR_STATE_WRITE": tracker,
        "_VIDEO_EDITOR_GUARD_SNAPSHOT": guard_snapshot,
        "_VIDEO_EDITOR_SUBMISSION_COMMITTED": submission_committed,
        "USER_PENDING": pending,
        **_isolated_callback_flags(),
    }


VIDEO_EDITOR_SPLIT_CALLBACK_ALLOWED = _compile_function(
    "video_editor_split_callback_allowed",
    {},
)
VIDEO_EDITOR_STATE_SNAPSHOT = _compile_function(
    "video_editor_state_snapshot",
    {"json": json},
)
VIDEO_EDIT_REVIEW_RETURN_ACTION = _compile_function(
    "video_edit_review_return_action",
    {},
)


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
        "media_lane": "short_media",
        "source_metadata": {
            "ok": True,
            "actual_bytes": 4096,
            "declared_bytes": 4096,
            "duration": 10.0,
            "duration_ms": 10_000,
            "declared_duration_seconds": 10,
            "source_sha256": "a" * 64,
            "media_lane": "short_media",
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
        "video_local_manual_options_text": lambda _state, _lang: "Không gian chỉnh sửa cục bộ · 0 Xu",
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


@pytest.mark.parametrize(
    ("name", "value", "reason"),
    (
        (
            "TELEGRAM_API_PROXY_SECRET",
            "secret\r\nX-Injected: yes",
            "telegram_proxy_secret_invalid",
        ),
        (
            "TELEGRAM_API_PROXY_SECRET_HEADER",
            "X-Good\nX-Injected",
            "telegram_proxy_secret_header_invalid",
        ),
    ),
)
def test_videoedit_bot_rejects_raw_proxy_header_injection_before_normalization(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    reason: str,
) -> None:
    read_proxy_env = _compile_function(
        "_telegram_proxy_env",
        {"os": os},
    )
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=reason):
        read_proxy_env(name, reason=reason)

    infrastructure = BOT_SOURCE[
        BOT_SOURCE.index("# ─── INFRA.LOCALBOTAPI") :
        BOT_SOURCE.index("def normalize_telegram_api_root")
    ]
    assert re.search(
        rf'_telegram_proxy_env\(\s*"{re.escape(name)}"',
        infrastructure,
    )
    assert f'_first_env_line(_env("{name}"))' not in infrastructure


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
    assert "dịch vụ bên ngoài" in blocked_message.replies[-1][0].lower()
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
    assert all("Không gian chỉnh sửa cục bộ" not in text for text, _kwargs in message.replies)
    assert any("chưa" in text.lower() and "bộ xử lý" in text.lower() for text, _kwargs in message.replies)


def test_text_overlay_accepts_the_final_concat_and_slow_speed_timeline() -> None:
    state = _default_state(
        904,
        step="await_text_overlay",
        concat_sources=[{"metadata": {"duration_ms": 4_000}}],
    )
    state["manual_edit_plan"]["speed"] = 0.5

    _run_pending_text(state, "Nhãn cuối | dưới | 00:20-00:24 | 42")

    assert state["step"] == "options"
    assert state["manual_edit_plan"]["text_overlay"] == {
        "content": "Nhãn cuối",
        "position": "bottom",
        "start_ms": 20_000,
        "end_ms": 24_000,
        "font_size": 42,
        "outline": 2,
    }


def test_text_overlay_default_and_limit_use_the_exact_final_timeline() -> None:
    default_state = _default_state(
        905,
        step="await_text_overlay",
        concat_sources=[{"source_metadata": {"duration_ms": 4_000}}],
    )
    default_state["manual_edit_plan"]["speed"] = 0.5

    _run_pending_text(default_state, "Nhãn toàn video")

    assert default_state["manual_edit_plan"]["text_overlay"]["end_ms"] == 28_000

    too_late = _default_state(906, step="await_text_overlay")
    too_late["manual_edit_plan"]["speed"] = 2.0
    before_plan = deepcopy(too_late["manual_edit_plan"])

    message = _run_pending_text(too_late, "Quá muộn | dưới | 00:05-00:06 | 42")

    assert too_late["step"] == "await_text_overlay"
    assert too_late["manual_edit_plan"] == before_plan
    assert "range_after_duration" in message.replies[-1][0]


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
    assert "replace_video_edit_lane_state(" in block
    assert "callback_entry_state" in block
    assert '"quality_enhance"' in block
    assert 'video_edit_lane_upload_text("quality_enhance", lang)' in block
    assert 'selected_effect=feature_key' in block


def test_local_ui_copy_and_remove_middle_entry_are_truthful() -> None:
    effects = _function_source("video_edit_effects_text")
    guide = _function_source("video_edit_guide_text")
    confirmation = _function_source("video_local_confirmation_text")
    keyboard = _function_source("video_local_confirmation_keyboard")
    callback = _function_source("handle_video_editor_callback")

    assert "Hiệu ứng cục bộ" in effects
    assert "0 Xu" in effects
    assert "20 MiB" in guide
    assert "60 giây" in guide
    assert "0 Xu" in guide
    assert "đúng số phần MP4 đã chọn" in guide
    for english_fragment in ("fade", "vignette", "slow zoom", "giới hạn audio"):
        assert english_fragment not in guide.lower()
    assert "không gọi dịch vụ bên ngoài" in confirmation.lower()
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
    assert "dịch vụ bên ngoài" in combined
    assert "0 xu" in combined


def test_videoedit_lane_copy_uses_routing_thresholds_not_public_hard_limits() -> None:
    guide = _compile_function(
        "video_edit_guide_text",
        {"normalize_user_language": lambda _lang: "vi"},
    )("vi")
    assistant_upload = _compile_function("video_ai_edit_upload_text", {})("vi")
    quality_upload = _compile_function(
        "video_edit_lane_upload_text",
        {
            "video_edit_state_machine": video_edit_state_machine,
            "video_local_upload_text": lambda _mode, _lang: "manual",
            "video_ai_edit_upload_text": lambda _lang: assistant_upload,
        },
    )("quality_enhance", "vi")
    public_error = _compile_function("video_local_public_error", {})
    public_lane_notice = "\n".join(
        (
            public_error("video_too_large", "vi"),
            public_error("duration_too_long", "vi"),
        )
    )

    for copy in (guide, quality_upload, assistant_upload, public_lane_notice):
        assert "20 MiB" in copy
        assert "60 giây" in copy
        assert "Telegram" in copy
        assert "VPS/server" in copy
        assert "tự động" in copy
        assert "dung lượng tạm" in copy
        assert "50 MB" not in copy
        assert "30 phút" not in copy
        assert "không giới hạn" not in copy.lower()


def test_videoedit_vietnamese_surfaces_translate_pipeline_terms_for_users() -> None:
    import bot as bot_module

    state = _default_state(905)
    state["manual_edit_plan"]["brightness_percent"] = 120
    rendered = "\n".join(
        [
            bot_module.video_edit_guide_text("vi"),
            bot_module.video_edit_effects_text("vi", source_ready=True),
            bot_module.video_local_frame_text("vi"),
            bot_module.video_local_transform_text("vi"),
            bot_module.video_local_color_text("vi"),
            bot_module.video_local_overlay_text("vi"),
            bot_module.video_local_confirmation_text(state, "vi"),
        ]
    ).lower()

    for internal_term in ("local", "provider", "invoice", "worker", "job"):
        assert not re.search(rf"(?<![\w]){internal_term}(?![\w])", rendered)


def test_videoedit_goal_assistant_and_public_alerts_are_vietnamese_first() -> None:
    import bot as bot_module

    state = _default_state(906)
    state.update(
        {
            "ai_suggestions": [
                {
                    "title": "Làm rõ tự nhiên",
                    "result": "Tăng độ rõ vừa phải và giữ nguyên chủ thể.",
                    "estimated_intensity": "Vừa",
                    "preserve_summary": "chủ thể chính",
                    "local_fallback_available": True,
                }
            ],
            "ai_route": {
                "profile_title": "Làm rõ tự nhiên",
                "execution_lane": "local",
                "profile": {"visual_objective": "Làm rõ video theo yêu cầu"},
            },
            "execution_lane": "local",
            "prompt_payload": {
                "prompt": "Làm sáng nhẹ và giữ nguyên chủ thể.",
                "negative_prompt": "Không làm méo hình.",
            },
        }
    )
    invoice = bot_module.video_ai_edit_invoice_snapshot(state)
    stale_color_plan = deepcopy(state["manual_edit_plan"])
    stale_color_plan["color_preset"] = "unknown_saved_value"
    compiler_messages = [
        str(
            video_edit_capabilities.compile_local_intent(intent).get("message_vi")
            or ""
        )
        for intent in ("", "làm sáng", "thay nền")
    ]
    rendered = "\n".join(
        [
            bot_module.video_ai_edit_intro_text("vi"),
            bot_module.video_ai_edit_upload_text("vi"),
            bot_module.video_ai_edit_source_summary_text(state, "vi"),
            bot_module.video_ai_edit_intent_text("vi"),
            bot_module.video_ai_edit_suggestions_text(state, "vi"),
            bot_module.video_ai_edit_settings_text(state, "vi"),
            bot_module.video_ai_edit_aspect_method_text(state),
            bot_module.video_ai_edit_aspect_limits_text(),
            bot_module.video_ai_edit_prompt_text(state, "vi"),
            bot_module.video_ai_edit_invoice_text(state, invoice, "vi"),
            bot_module.video_local_brightness_text(state, "vi"),
            bot_module.video_editor_public_guard_text("vi"),
            bot_module.video_local_public_error("worker_unavailable"),
            bot_module.video_tail9_video_edit_review_text(
                {"video_product_type": "video_edit", "estimated_duration": 10},
                state,
            ),
            bot_module.video_tail9_video_edit_operations_text(state),
            "\n".join(video_local_editing.public_plan_summary(stale_color_plan)),
            *compiler_messages,
        ]
    ).lower()

    for internal_term in (
        "local",
        "provider",
        "invoice",
        "worker",
        "job",
        "preset",
        "runtime",
        "metadata",
        "ffmpeg",
        "crop",
        "flow",
        "prompt",
        "cinematic",
    ):
        assert not re.search(rf"(?<![\w]){internal_term}(?![\w])", rendered)

    keyboards = (
        bot_module.video_ai_edit_settings_keyboard("vi", state),
        bot_module.video_ai_edit_prompt_keyboard("vi"),
        bot_module.video_ai_edit_invoice_keyboard(invoice, "vi"),
        bot_module.video_ai_edit_status_keyboard(7, "vi"),
        bot_module.video_local_manual_options_keyboard("vi", state),
        bot_module.video_local_color_keyboard("vi"),
        bot_module.video_editor_preset_keyboard("vi"),
    )
    public_labels = "\n".join(
        str(button.text)
        for keyboard in keyboards
        for row in keyboard.inline_keyboard
        for button in row
    ).lower()
    for internal_term in ("local", "provider", "invoice", "worker", "job", "preset", "cinematic"):
        assert not re.search(rf"(?<![\w]){internal_term}(?![\w])", public_labels)

    public_route_source = "\n".join(
        [
            _function_source("handle_video_editor_callback"),
            _function_source("handle_video_editor_pending_upload"),
            _function_source("handle_video_editor_pending_text"),
            _function_source("submit_video_edit_local_free_job"),
            _function_source("video_edit_legacy_tail_compatibility"),
        ]
    )
    for public_leak in (
        "Worker chưa xác nhận",
        "chưa được worker xác nhận",
        "thao tác local",
        "Preset màu",
        "bộ lọc local",
        "xử lý local",
        "gọi provider",
        "tác vụ chỉnh sửa local",
        "trợ lý chỉnh sửa local",
        "độ phân giải local",
        "kế hoạch local",
        "Bộ xử lý local",
        "tác vụ local",
        "phương án local",
        "Chi phí local",
        "Không invoice",
        "FFmpeg/ffprobe",
    ):
        assert public_leak not in public_route_source


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
    assert "kế hoạch cục bộ" in combined
    assert "chưa gọi nguồn xử lý" in combined or "chưa gọi dịch vụ bên ngoài" in combined


def test_goal_assistant_review_shows_a_vietnamese_edit_plan_not_internal_prompt() -> None:
    import bot as bot_module

    state = _default_state(907)
    state["manual_edit_plan"]["brightness_percent"] = 120
    state.update(
        {
            "ai_route": {
                "profile_title": "Làm sáng tự nhiên",
                "execution_lane": "local",
                "profile": {"visual_objective": "Làm sáng và giữ nguyên chủ thể"},
            },
            "execution_lane": "local",
            "prompt_payload": {
                "prompt": "INTERNAL_PROVIDER_PROMPT_SENTINEL",
                "negative_prompt": "INTERNAL_NEGATIVE_PROMPT_SENTINEL",
            },
        }
    )

    text = bot_module.video_ai_edit_prompt_text(state, "vi")

    assert "INTERNAL_PROVIDER_PROMPT_SENTINEL" not in text
    assert "INTERNAL_NEGATIVE_PROMPT_SENTINEL" not in text
    assert "Kế hoạch chỉnh sửa" in text
    assert "Độ sáng 120%" in text
    assert "Giới hạn an toàn" in text
    assert "<code>" not in text


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
            "video_editor_split_callback_allowed": VIDEO_EDITOR_SPLIT_CALLBACK_ALLOWED,
            "video_editor_state_snapshot": lambda value: deepcopy(dict(value or {})),
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
            "get_video_editor_pending": lambda _uid: {},
            "video_edit_state_machine": video_edit_state_machine,
            "video_editor_normalize_action": lambda value: value,
            "video_editor_split_callback_allowed": VIDEO_EDITOR_SPLIT_CALLBACK_ALLOWED,
            "video_editor_state_snapshot": lambda value: deepcopy(dict(value or {})),
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
            "video_editor_split_callback_allowed": VIDEO_EDITOR_SPLIT_CALLBACK_ALLOWED,
            "video_editor_state_snapshot": lambda value: deepcopy(dict(value or {})),
            "clear_video_editor_competing_video_states": lambda *_args: events.append("clear-competing"),
            "clear_video_session": lambda *_args: events.append("clear-session"),
            "clear_video_editor_pending": lambda *_args: events.append("clear-pending"),
            "set_video_route_session": lambda *_args, **_kwargs: events.append("set-route"),
            "replace_video_edit_lane_state": lambda *_args, **_kwargs: events.append(f"replace:{edit_mode}"),
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
    action_parse = callback.index(
        "parts = str(callback_data_override or query.data or \"\").split"
    )
    assert "await query.answer()" not in callback[:action_parse]

    safe_render = _function_source("safe_edit_or_send")
    assert 'startswith("videoedit|")' in safe_render
    assert "_VIDEO_EDIT_CALLBACK_ANSWERED.get()" in safe_render
    assert "_VIDEO_EDIT_CALLBACK_ANSWERED.set(True)" in safe_render
    assert 'setattr(query, "_video_edit_callback_answered"' not in safe_render


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
            **_isolated_callback_flags(),
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

    callback_flags = _isolated_callback_flags()
    safe_render = _compile_function(
        "safe_edit_or_send",
        {
            "inspect": __import__("inspect"),
            "is_soft_telegram_edit_error": lambda _error: False,
            "sanitize_log_text": str,
            "logger": logging.getLogger("videoedit-legacy-render-transaction"),
            **callback_flags,
        },
    )
    query = Query(944, "video_tail|review|open")
    transactional_token = callback_flags["_VIDEO_EDIT_CALLBACK_TRANSACTIONAL"].set(True)
    try:
        asyncio.run(
            safe_render(
                query,
                "review",
                post_render=lambda: events.append("commit"),
            )
        )
    finally:
        callback_flags["_VIDEO_EDIT_CALLBACK_TRANSACTIONAL"].reset(transactional_token)

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

    assert "replace_video_edit_lane_state" in review
    assert "callback_entry_state" in review
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
    assert "video_edit_state_machine.review_back_callback" in review
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
    assert "review_return_to" in helper
    assert "state.get(\"parent_callback\")" in helper

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


def test_latest_and_legacy_status_actions_are_stateless_read_only_owned_refreshes() -> None:
    callback = _function_source("handle_video_editor_callback")
    stateless_start = callback.index("VIDEO_EDIT_STATELESS_ACTIONS = {")
    stateless_end = callback.index("VIDEO_EDIT_COMPAT_UPLOAD_ACTIONS", stateless_start)
    stateless = callback[stateless_start:stateless_end]
    for action in ('"latest_status"', '"status"', '"ai_status"'):
        assert action in stateless

    latest_start = callback.index('if action == "latest_status":')
    latest_end = callback.index("\n    if ", latest_start + 1)
    latest_block = callback[latest_start:latest_end]
    assert "get_latest_video_editor_job(uid)" in latest_block
    assert "video_editor_job_status_text(job, lang)" in latest_block
    assert "video_editor_status_keyboard(job_id, lang)" in latest_block
    assert "video_editor_latest_status_fallback_keyboard(lang)" in latest_block
    assert "set_video_editor_pending" not in latest_block
    assert "update_video_editor_pending" not in latest_block
    assert "submit_video_edit" not in latest_block

    status_start = callback.index('if action == "status":')
    status_end = callback.index('if action == "quick":', status_start)
    status_block = callback[status_start:status_end]
    assert "get_local_worker_job_readonly(job_id)" in status_block
    assert "except sqlite3.Error" in status_block
    assert "video_editor_latest_status_unavailable_text(lang)" in status_block
    assert "str(job.get(\"user_id\") or \"\") != str(uid) and not is_admin_user(uid)" in status_block
    assert "set_video_editor_pending" not in status_block
    assert "submit_video_edit" not in status_block

    start = callback.index('if action == "ai_status":')
    end = callback.index('if action.startswith("ai_"):', start)
    ai_status_block = callback[start:end]
    assert "get_local_worker_job_readonly(job_id)" in ai_status_block
    assert "except sqlite3.Error" in ai_status_block
    assert "video_editor_latest_status_unavailable_text(lang)" in ai_status_block
    assert "video_editengine1.WORKER_JOB_TYPE" in ai_status_block
    assert "video_editor_job_status_text(job, lang)" in ai_status_block
    assert "video_editor_status_keyboard(job_id, lang)" in ai_status_block
    assert "str(job.get(\"user_id\") or \"\") != str(uid) and not is_admin_user(uid)" in ai_status_block
    assert "create_job(" not in ai_status_block
    assert "set_video_editor_pending" not in ai_status_block
    assert "submit_video_edit" not in ai_status_block

    readonly_lookup = _function_source("get_local_worker_job_readonly")
    assert "db_connect_readonly()" in readonly_lookup
    assert "SELECT id,user_id,command,job_type,status" in readonly_lookup
    assert "INSERT" not in readonly_lookup
    assert "UPDATE" not in readonly_lookup
    assert "DELETE" not in readonly_lookup


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
    assert "Nền mờ chưa có bộ lọc cục bộ" in method
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
    assert "video_local_review_keyboard(tool, lang, current)" in helper
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


def test_legacy_videoedit_callback_claim_is_cas_persisted_before_migration() -> None:
    source = _function_source("handle_video_tail_callback")
    owner_start = source.index('if owner == "video_edit":')
    owner_end = source.index("save_video_tail9_state(uid, context, tail, owner, host)", owner_start)
    owner_block = source[owner_start:owner_end]

    assert "compare_and_set_video_editor_pending(" in owner_block
    assert "VIDEO_TAIL9_STATE_KEY" in owner_block
    assert "rerender_video_editor_after_stale_commit(" in owner_block
    assert owner_block.index("compare_and_set_video_editor_pending(") < owner_block.index(
        "video_edit_legacy_tail_compatibility("
    )
    assert "save_video_tail9_state(" not in owner_block


def test_duplicate_legacy_videoedit_callback_migrates_only_once() -> None:
    user_id = 948
    pending = {f"video_editor:{user_id}": _default_state(user_id)}
    migration_calls: list[str] = []

    def get_pending(uid: int) -> dict:
        return deepcopy(pending.get(f"video_editor:{uid}") or {})

    def tail_context(uid: int, _context) -> tuple[dict, str, dict]:
        host = get_pending(uid)
        return deepcopy(host.get("video_tail9") or {}), "video_edit", host

    def claim_callback(tail: dict, callback_id: str) -> tuple[dict, bool]:
        current = deepcopy(tail)
        if current.get("last_callback_id") == callback_id:
            return current, False
        current["last_callback_id"] = callback_id
        return current, True

    def compare_and_set(uid: int, expected: dict, step: str = "", **fields):
        current = get_pending(uid)
        if current != expected:
            return False, current
        current.update(fields)
        if step:
            current["step"] = step
        pending[f"video_editor:{uid}"] = deepcopy(current)
        return True, current

    async def migrate(_query, _uid: int, _tail: dict, _host: dict):
        migration_calls.append("migrated")
        return True

    async def stale_rerender(*_args, **_kwargs):
        raise AssertionError("claim CAS unexpectedly lost")

    handler = _compile_function(
        "handle_video_tail_callback",
        {
            "video_tail9_context": tail_context,
            "video_tail9": SimpleNamespace(claim_callback=claim_callback),
            "compare_and_set_video_editor_pending": compare_and_set,
            "video_editor_state_snapshot": lambda value: deepcopy(dict(value or {})),
            "VIDEO_TAIL9_STATE_KEY": "video_tail9",
            "rerender_video_editor_after_stale_commit": stale_rerender,
            "get_user_language": lambda _uid: "vi",
            "video_edit_legacy_tail_compatibility": migrate,
            "save_video_tail9_state": lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("commercial tail save used for Video Edit")
            ),
            "logger": logging.getLogger("videoedit-legacy-claim-test"),
            **_isolated_callback_flags(),
        },
    )
    query = _Query(user_id, "video_tail|review|open")
    update = SimpleNamespace(callback_query=query)

    assert asyncio.run(handler(update, SimpleNamespace())) is True
    assert asyncio.run(handler(update, SimpleNamespace())) is None
    assert migration_calls == ["migrated"]
    assert pending[f"video_editor:{user_id}"]["video_tail9"]["last_callback_id"] == query.id


def test_legacy_shared_tail_failure_cannot_reenter_the_commercial_renderer() -> None:
    callback = _function_source("handle_video_tail_callback")
    redirect_index = callback.index('if owner == "video_edit":')
    redirect = callback[redirect_index:callback.index("save_video_tail9_state", redirect_index)]

    assert "video_edit_legacy_tail_compatibility(" in redirect
    assert "except Exception" in redirect
    assert "_VIDEO_EDIT_CALLBACK_TRANSACTIONAL.set(True)" in redirect
    assert 'setattr(query, "_video_edit_transactional"' not in redirect
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
            "video_editor_state_snapshot": VIDEO_EDITOR_STATE_SNAPSHOT,
            "video_edit_review_return_action": VIDEO_EDIT_REVIEW_RETURN_ACTION,
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
    commit_start = submit.rindex("committed, winner = finish_video_editor_submission(")
    marker_start = submit.index("mark_video_editor_submission_committed()", commit_start)
    render_start = submit.index("await safe_edit_or_send(", marker_start)
    commit_block = submit[commit_start:marker_start]

    assert "committed, winner = finish_video_editor_submission(" in commit_block
    assert "uid," in commit_block
    assert "reserved_state," in commit_block
    assert "candidate," in commit_block
    assert "replacement_exists=True," in commit_block
    assert "if not committed:" in commit_block
    assert commit_start < marker_start < render_start
    assert "post_render=" not in submit


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
    assert "replace_video_edit_lane_state(" in recovery
    assert "callback_entry_state" in recovery
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
    assert "local" not in free_branch.lower()


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
    assert manual_block.index("source_file_id") < manual_block.index("replace_video_edit_lane_state")
    assert "callback_entry_state" in manual_block
    assert "clear_video_editor_pending" not in manual_block
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
    metadata_failure_end = legacy.index(
        'source["source_file_size"]', metadata_failure_start
    )
    metadata_failure = legacy[metadata_failure_start:metadata_failure_end]
    assert "back_callback=back_callback" in metadata_failure

    logo_start = legacy.index('if step == "await_logo":')
    srt_start = legacy.index('if step == "await_srt":', logo_start)
    source_start = legacy.index("source = video_editor_source_from_update", srt_start)
    logo_block = legacy[logo_start:srt_start]
    srt_block = legacy[srt_start:source_start]
    assert "logo_parent = video_local_logo_parent_callback(state)" in logo_block
    assert "back_callback=logo_parent" in logo_block
    assert 'back_callback="videoedit|overlay"' in srt_block

    pending_text = _function_source("handle_video_editor_pending_text")
    order_start = pending_text.index('if step == "await_concat_order":')
    order_end = pending_text.index('if step == "await_ai_intent":', order_start)
    assert 'back_callback="videoedit|join"' in pending_text[order_start:order_end]

    recovery = _function_source("recover_product_video_media_failure")
    assert 'if step in {"await_logo", "await_srt", "await_concat"}:' in recovery
    assert 'back_callback="videoedit|overlay"' in recovery
    assert 'back_callback="videoedit|join"' in recovery


def test_logo_upload_commits_the_canonical_logo_options_screen() -> None:
    upload = _function_source("handle_video_editor_pending_upload")
    start = upload.index('if step == "await_logo":')
    end = upload.index('if step == "await_srt":', start)
    block = upload[start:end]
    assert "update_video_editor_screen(" in block
    assert '"logo_options"' in block
    assert "parent_callback=logo_parent" in block
    assert "logo_parent_callback=logo_parent" in block
    assert 'update_video_editor_pending(uid, "logo_options"' not in block


def test_legacy_tail_logo_upload_renders_only_canonical_videoedit_actions() -> None:
    upload = _function_source("handle_video_editor_pending_upload")
    start = upload.index('if edit_mode and str(state.get("step") or "") == "awaiting_video_tail9_logo":')
    end = upload.index("if edit_mode and video_edit_state_machine.is_duplicate_message", start)
    block = upload[start:end]

    assert "video_tail|" not in block
    assert "update_video_editor_screen(" in block
    assert '"logo_options"' in block
    assert "video_local_logo_keyboard" in block

    recovery = _function_source("recover_product_video_media_failure")
    recovery_start = recovery.index('if step == "awaiting_video_tail9_logo":')
    recovery_end = recovery.index('if step in {"await_logo", "await_srt", "await_concat"}:', recovery_start)
    recovery_block = recovery[recovery_start:recovery_end]
    assert "video_tail|" not in recovery_block
    assert "videoedit|overlay" in recovery_block


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
    assert "_VIDEO_EDITOR_STATE_WRITE" in guard
    assert "rollback_video_editor_guard_state" in guard
    assert "USER_PENDING[state_key]" not in guard
    assert "video_editor_pending_key" in guard
    assert "video_editor_pending_key" not in shared_guard
    assert "_video_edit_render_failed" not in shared_guard


def test_videoedit_lane_replacement_never_clears_before_atomic_set() -> None:
    callback = _function_source("handle_video_editor_callback")
    tree = ast.parse(callback)
    replacement_closures = {
        "commit_quality_entry",
        "commit_quality_reupload",
        "commit_quality_pick_upload",
        "commit_ai_entry",
        "commit_ai_reupload",
        "commit_manual_entry",
        "commit_manual_upload",
        "commit_legacy_upload",
    }
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in replacement_closures:
            found.add(node.name)
            source = ast.get_source_segment(callback, node) or ""
            assert "clear_video_editor_pending" not in source
            assert (
                "replace_video_edit_lane_state" in source
                or "compare_and_replace_video_editor_pending" in source
            )
    assert found == replacement_closures

    quick_start = callback.index('if action == "quick":')
    quick_end = callback.index('if action == "manual":', quick_start)
    quick_block = callback[quick_start:quick_end]
    assert "clear_video_editor_pending" not in quick_block
    assert "set_video_editor_pending" in quick_block


def test_videoedit_failure_guard_restores_a_hard_render_failure() -> None:
    pending = {"video_editor:904": {"step": "workspace", "manual_edit_plan": {"speed": 1.0}}}
    tracker, dependencies = _isolated_guard_dependencies(pending)

    guard = _compile_function(
        "video_editor_callback_state_guard",
        dependencies,
    )

    async def hard_handler(update, _context):
        mutated = {"step": "mutated"}
        pending["video_editor:904"] = mutated
        tracker.set({"user_id": "904", "exists": True, "state": mutated})
        raise RuntimeError("render failed")

    query = _Query(904, "videoedit|set|speed|2")
    update = SimpleNamespace(callback_query=query)
    with pytest.raises(RuntimeError, match="render failed"):
        asyncio.run(guard(hard_handler)(update, SimpleNamespace()))
    assert pending["video_editor:904"] == {
        "step": "workspace",
        "manual_edit_plan": {"speed": 1.0},
    }


def test_videoedit_submission_side_effect_fence_preserves_job_state_after_render_failure() -> None:
    """A created job must win over the pre-submit rollback snapshot."""

    pending = {
        "video_editor:905": {
            "step": "confirmation",
            "current_screen": "confirmation",
            "status": "confirmation_ready",
        }
    }
    tracker, dependencies = _isolated_guard_dependencies(pending)
    committed = ContextVar("test_video_editor_submission_committed", default=False)
    dependencies["_VIDEO_EDITOR_SUBMISSION_COMMITTED"] = committed
    guard = _compile_function("video_editor_callback_state_guard", dependencies)
    winner = {
        "step": "job_status",
        "current_screen": "job_status",
        "status": "queued",
        "job_id": 812,
    }

    async def handler(update, _context):
        pending["video_editor:905"] = deepcopy(winner)
        tracker.set({"user_id": "905", "exists": True, "state": deepcopy(winner)})
        committed.set(True)
        raise RuntimeError("telegram render failed after job creation")

    query = _Query(905, "videoedit|confirm_local")
    update = SimpleNamespace(callback_query=query)
    with pytest.raises(RuntimeError, match="after job creation"):
        asyncio.run(guard(handler)(update, SimpleNamespace()))
    assert pending["video_editor:905"] == winner


def test_videoedit_submit_paths_mark_irreversible_job_before_ui_render() -> None:
    for name in (
        "submit_video_ai_edit_job",
        "submit_video_edit_local_free_job",
        "submit_local_video_editor_job",
    ):
        source = _function_source(name)
        assert "mark_video_editor_submission_committed()" in source, name

    local_free = _function_source("submit_video_edit_local_free_job")
    commit = local_free.rindex("finish_video_editor_submission(")
    render = local_free.index("await safe_edit_or_send(", commit)
    assert commit < render
    assert "post_render=commit_job_status" not in local_free


def test_videoedit_media_dispatch_precedes_admin_tool_media_dispatch() -> None:
    for name in ("handle_media", "handle_media_cache_only"):
        source = _function_source(name)
        video = source.index("handle_video_editor_pending_upload")
        caption = source.index("handle_caption_admin_tool_test_media")
        pending_admin = source.index("handle_pending_admin_tool_test_media")
        assert video < caption < pending_admin, name


def test_videoedit_submit_db_connect_failure_rolls_back_reserved_state(tmp_path: Path) -> None:
    saved = _default_state(
        913,
        step="confirmation",
        current_screen="confirmation",
        status="confirmation_ready",
        review_revision=3,
        state_revision=3,
    )
    saved["manual_edit_plan"]["brightness_percent"] = 120
    namespace = _submit_namespace(tmp_path / "unused.sqlite3", saved)
    namespace["db_connect"] = lambda: (_ for _ in ()).throw(OSError("database unavailable"))
    submit = _compile_function("submit_video_edit_local_free_job", namespace)
    query = _Query(913, "videoedit|confirm_local")
    update = SimpleNamespace(callback_query=query, message=None, effective_user=query.from_user)

    assert asyncio.run(submit(update, SimpleNamespace(), deepcopy(saved))) is True
    assert saved["step"] == "confirmation"
    assert saved["status"] == "confirmation_ready"
    assert query.edits
    assert "chưa tạo tác vụ" in query.edits[-1][0].lower()


def test_message_state_guard_commits_success_and_rolls_back_failed_reply() -> None:
    pending = {"video_editor:907": {"step": "await_brightness", "manual_edit_plan": {"speed": 1.0}}}
    tracker, dependencies = _isolated_guard_dependencies(pending)

    guard = _compile_function(
        "video_editor_message_state_guard",
        dependencies,
    )
    update = SimpleNamespace(effective_user=SimpleNamespace(id=907))

    async def failed_reply(_update, _context):
        mutated = {"step": "review", "manual_edit_plan": {"speed": 2.0}}
        pending["video_editor:907"] = mutated
        tracker.set({"user_id": "907", "exists": True, "state": mutated})
        raise RuntimeError("telegram reply failed")

    with pytest.raises(RuntimeError, match="telegram reply failed"):
        asyncio.run(guard(failed_reply)(update, SimpleNamespace()))
    assert pending["video_editor:907"] == {
        "step": "await_brightness",
        "manual_edit_plan": {"speed": 1.0},
    }

    async def successful_reply(_update, _context):
        committed = {"step": "review", "manual_edit_plan": {"speed": 2.0}}
        pending["video_editor:907"] = committed
        tracker.set({"user_id": "907", "exists": True, "state": committed})
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
        "workspace_ready": True,
        "workspace_free_bytes": 10 * 1024 * 1024 * 1024,
        "video_edit_max_deadline_seconds": 1800,
        "worker_token_ready": True,
        "local_bot_api_ready": True,
    }


def _submit_namespace(db_path: Path, saved: dict) -> dict:
    def snapshot(value) -> dict:
        return deepcopy(dict(value or {}))

    last_submit_user_id = {"value": ""}

    class VideoEditorStateCommitError(RuntimeError):
        def __init__(self, reason: str, winner: dict | None = None) -> None:
            super().__init__(reason)
            self.winner = snapshot(winner)

    def begin_submission(user_id, expected_state: dict, *, lane: str) -> dict:
        last_submit_user_id["value"] = str(user_id)
        current = snapshot(saved)
        # The isolated submit harness receives the durable confirmation state as
        # the function argument; an empty fixture is that initial durable row.
        if current and current != snapshot(expected_state):
            raise VideoEditorStateCommitError(
                "video_editor_submit_state_conflict",
                current,
            )
        reserved = snapshot(expected_state)
        reserved.update(
            {
                "step": "submitting",
                "current_screen": "submitting",
                "status": "submitting",
                "pending_field": "",
                "awaiting_media": False,
                "submission_lane": str(lane or "local")[:40],
            }
        )
        return reserved

    def finish_submission(
        user_id,
        expected_reserved_state: dict,
        replacement_state: dict | None = None,
        *,
        replacement_exists: bool = True,
    ) -> tuple[bool, dict]:
        current = snapshot(saved)
        if current and current != snapshot(expected_reserved_state):
            return False, current
        replacement = snapshot(replacement_state)
        saved.clear()
        if replacement_exists:
            saved.update(replacement)
        return True, replacement if replacement_exists else {}

    async def rerender_after_stale_commit(query, winner: dict, _lang: str):
        job_id = int(dict(winner or {}).get("job_id") or 0)
        if job_id:
            await query.edit_message_text(
                f"✅ Đã nhận yêu cầu xử lý video · tác vụ #{job_id}",
                reply_markup=f"status:{job_id}",
            )

    async def render(query, text: str, **kwargs):
        post_render = kwargs.pop("post_render", None)
        result = await query.edit_message_text(text, **kwargs)
        if post_render:
            post_render()
        return result

    namespace = {
        "get_user_language": lambda _uid: "vi",
        "html": html,
        "re": re,
        "safe_int": lambda value, default=0: int(value or default),
        "video_local_editing": video_local_editing,
        "video_local_validation": video_local_validation,
        "video_tail9": video_tail9,
        "logo_watermark_normalize_position": lambda value, default="bottom_right": (
            video_local_editing._canonical_overlay_position(value, default)
        ),
        "video_edit_worker_status_payload": _ready_worker,
        "video_editengine1": video_editengine1,
        "VIDEO_TAIL9_STATE_KEY": "video_tail9",
        "LOCAL_WORKER_MAX_JOB_SECONDS": 1800,
        "db_connect": lambda: sqlite3.connect(db_path),
        "sqlite3": sqlite3,
        "logger": logging.getLogger("videoedit-submit-test"),
        "sanitize_log_text": lambda value: str(value),
        "time": time,
        "safe_edit_or_send": render,
        "video_editor_status_keyboard": lambda job_id, _lang: f"status:{job_id}",
        "video_editor_state_snapshot": snapshot,
        "begin_video_editor_submission": begin_submission,
        "finish_video_editor_submission": finish_submission,
        "mark_video_editor_submission_committed": lambda: None,
        "VideoEditorStateCommitError": VideoEditorStateCommitError,
        "rerender_video_editor_after_stale_commit": rerender_after_stale_commit,
        "video_tail9_quality_keyboard": lambda *_args, **_kwargs: "quality-keyboard",
        "get_local_worker_job": lambda job_id: {
            "id": int(job_id),
            "user_id": last_submit_user_id["value"] or "905",
            "job_type": video_editengine1.WORKER_JOB_TYPE,
            "status": "queued",
            "xu_cost": 0,
        },
        "video_editor_job_status_text": lambda job, _lang: f"Trạng thái tác vụ #{job['id']} · 0 Xu",
        "video_local_manual_options_keyboard": lambda *_args, **_kwargs: "workspace-keyboard",
        "video_edit_lane_upload_keyboard": lambda *_args: "upload-keyboard",
        "video_editor_upload_required_text": lambda _lang: "Cần video nguồn",
        "video_local_public_error": lambda reason, _lang="vi": reason,
        "update_video_editor_pending": lambda _uid, step, **fields: saved.update({"step": step, **fields}) or deepcopy(saved),
    }
    namespace["video_editor_plan_with_watermark"] = _compile_function(
        "video_editor_plan_with_watermark",
        {
            "re": re,
            "safe_int": lambda value, default=0: int(value or default),
            "video_local_editing": video_local_editing,
        },
    )
    namespace["video_edit_submit_inspection_evidence"] = _compile_video_edit_submit_evidence_helper()
    return namespace


def _video_edit_submit_evidence_state(
    *,
    actual_bytes: int = 1_024,
    duration_ms: int = 10_000,
    declared_bytes: int = 1_024,
    declared_duration_seconds: int = 10,
    media_lane: str = "short_media",
    metadata_lane: str | None = None,
) -> dict:
    source_sha256 = "a" * 64
    return {
        "inspection_complete": True,
        "source_video_hash": source_sha256,
        "source_file_size": actual_bytes,
        "media_lane": media_lane,
        "private_source_path": "C:/private/input.mp4",
        "provider_token": "must-not-leave-the-helper",
        "source_metadata": {
            "ok": True,
            "actual_bytes": actual_bytes,
            "duration_ms": duration_ms,
            "source_sha256": source_sha256,
            "declared_bytes": declared_bytes,
            "declared_duration_seconds": declared_duration_seconds,
            "media_lane": metadata_lane or media_lane,
            "nested": {"preserved": True},
        },
    }


def _compile_video_edit_submit_evidence_helper():
    marker = "\ndef video_edit_submit_inspection_evidence("
    start = BOT_SOURCE.find(marker)
    if start < 0:
        raise AssertionError("missing function: video_edit_submit_inspection_evidence")
    end = BOT_SOURCE.find("\n\nasync def submit_video_edit_local_free_job(", start)
    if end < 0:
        raise AssertionError("submit function no longer bounds inspection evidence helper")
    namespace = {
        "deepcopy": deepcopy,
        "re": re,
        "video_edit_media_transport": __import__(
            "services.video_edit_media_transport",
            fromlist=["video_edit_media_transport"],
        ),
    }
    source = "from __future__ import annotations\n\n" + BOT_SOURCE[start + 1 : end]
    exec(compile(source, filename="bot.py", mode="exec"), namespace)
    return namespace["video_edit_submit_inspection_evidence"]


def test_video_edit_submit_inspection_evidence_accepts_exact_short_evidence() -> None:
    helper = _compile_video_edit_submit_evidence_helper()
    state = _video_edit_submit_evidence_state()
    original = deepcopy(state)

    evidence = helper(state)

    assert state == original
    assert evidence == {
        "ok": True,
        "media_lane": "short_media",
        "source_metadata": original["source_metadata"],
        "actual_bytes": 1_024,
        "duration_ms": 10_000,
        "source_sha256": "a" * 64,
    }
    assert "private_source_path" not in evidence
    assert "provider_token" not in evidence
    assert "C:/private" not in json.dumps(evidence, sort_keys=True)
    state["source_metadata"]["nested"]["preserved"] = False
    assert evidence["source_metadata"]["nested"]["preserved"] is True


def test_video_edit_submit_inspection_evidence_accepts_large_actual_or_declared_media() -> None:
    helper = _compile_video_edit_submit_evidence_helper()
    state = _video_edit_submit_evidence_state(
        actual_bytes=51 * 1024 * 1024,
        duration_ms=60_000,
        declared_bytes=51 * 1024 * 1024,
        declared_duration_seconds=60,
        media_lane="large_media",
    )
    original = deepcopy(state)

    evidence = helper(state)

    assert state == original
    assert evidence["ok"] is True
    assert evidence["media_lane"] == "large_media"
    assert evidence["actual_bytes"] == 51 * 1024 * 1024
    assert evidence["duration_ms"] == 60_000


def test_video_edit_submit_inspection_evidence_unknown_declaration_requires_large_lane() -> None:
    helper = _compile_video_edit_submit_evidence_helper()
    state = _video_edit_submit_evidence_state(
        declared_bytes=0,
        declared_duration_seconds=0,
        media_lane="large_media",
    )
    original = deepcopy(state)

    evidence = helper(state)

    assert state == original
    assert evidence["ok"] is True
    assert evidence["media_lane"] == "large_media"


@pytest.mark.parametrize(
    "case,state",
    [
        ("inspection_false", {**_video_edit_submit_evidence_state(), "inspection_complete": False}),
        ("inspection_integer", {**_video_edit_submit_evidence_state(), "inspection_complete": 1}),
        ("metadata_not_ok", {**_video_edit_submit_evidence_state(), "source_metadata": {**_video_edit_submit_evidence_state()["source_metadata"], "ok": False}}),
        ("actual_bytes_bool", {**_video_edit_submit_evidence_state(), "source_metadata": {**_video_edit_submit_evidence_state()["source_metadata"], "actual_bytes": True}}),
        ("actual_bytes_zero", {**_video_edit_submit_evidence_state(), "source_metadata": {**_video_edit_submit_evidence_state()["source_metadata"], "actual_bytes": 0}}),
        ("actual_bytes_negative", {**_video_edit_submit_evidence_state(), "source_metadata": {**_video_edit_submit_evidence_state()["source_metadata"], "actual_bytes": -1}}),
        ("duration_bool", {**_video_edit_submit_evidence_state(), "source_metadata": {**_video_edit_submit_evidence_state()["source_metadata"], "duration_ms": True}}),
        ("duration_zero", {**_video_edit_submit_evidence_state(), "source_metadata": {**_video_edit_submit_evidence_state()["source_metadata"], "duration_ms": 0}}),
        ("duration_negative", {**_video_edit_submit_evidence_state(), "source_metadata": {**_video_edit_submit_evidence_state()["source_metadata"], "duration_ms": -1}}),
        ("hash_malformed", {**_video_edit_submit_evidence_state(), "source_metadata": {**_video_edit_submit_evidence_state()["source_metadata"], "source_sha256": "not-a-sha256"}}),
        ("hash_uppercase", {**_video_edit_submit_evidence_state(), "source_metadata": {**_video_edit_submit_evidence_state()["source_metadata"], "source_sha256": "A" * 64}}),
        ("hash_mismatch", {**_video_edit_submit_evidence_state(), "source_video_hash": "b" * 64}),
        ("top_level_size_mismatch", {**_video_edit_submit_evidence_state(), "source_file_size": 1_025}),
        ("top_level_lane_invalid", {**_video_edit_submit_evidence_state(), "media_lane": "unknown"}),
        ("metadata_lane_invalid", {**_video_edit_submit_evidence_state(), "source_metadata": {**_video_edit_submit_evidence_state()["source_metadata"], "media_lane": "unknown"}}),
        ("stored_lanes_differ", {**_video_edit_submit_evidence_state(), "source_metadata": {**_video_edit_submit_evidence_state()["source_metadata"], "media_lane": "large_media"}}),
        ("actual_promotes_large", {**_video_edit_submit_evidence_state(), "source_metadata": {**_video_edit_submit_evidence_state()["source_metadata"], "duration_ms": (int(video_edit_media_transport.SHORT_MEDIA_MAX_SECONDS) + 1) * 1_000}}),
        ("declared_promotes_large", {**_video_edit_submit_evidence_state(), "source_metadata": {**_video_edit_submit_evidence_state()["source_metadata"], "declared_bytes": 51 * 1024 * 1024}}),
        ("state_not_dict", ["not-a-state"]),
        ("metadata_not_dict", {**_video_edit_submit_evidence_state(), "source_metadata": ["not-metadata"]}),
    ],
)
def test_video_edit_submit_inspection_evidence_fails_closed_for_invalid_evidence(
    case: str,
    state,
) -> None:
    helper = _compile_video_edit_submit_evidence_helper()
    original = deepcopy(state)

    evidence = helper(state)

    assert state == original, case
    assert evidence == {
        "ok": False,
        "reason": "video_edit_inspection_evidence_invalid",
    }, case
    assert "private" not in json.dumps(evidence, sort_keys=True), case
    assert "token" not in json.dumps(evidence, sort_keys=True), case
    assert "source_sha256" not in evidence, case


def test_confirm_local_creates_exactly_one_free_job_and_duplicate_reuses_it(tmp_path: Path) -> None:
    db_path = tmp_path / "videoedit.sqlite3"
    _init_job_db(db_path)
    saved: dict = {}
    namespace = _submit_namespace(db_path, saved)
    create_calls = 0

    class _EngineSpy:
        def __getattr__(self, name):
            return getattr(video_editengine1, name)

        @staticmethod
        def create_job(*args, **kwargs):
            nonlocal create_calls
            create_calls += 1
            return video_editengine1.create_job(*args, **kwargs)

    namespace["video_editengine1"] = _EngineSpy()
    submit = _compile_function("submit_video_edit_local_free_job", namespace)
    large_bytes = 51 * 1024 * 1024
    large_duration_ms = 61_000
    state = _default_state(
        905,
        step="confirmation",
        current_screen="confirmation",
        status="confirmation_ready",
        review_revision=3,
        source_file_size=large_bytes,
        source_duration=61,
        source_duration_ms=large_duration_ms,
        source_video_hash="b" * 64,
        media_lane="large_media",
        source_metadata={
            "ok": True,
            "actual_bytes": large_bytes,
            "declared_bytes": large_bytes,
            "duration": 61.0,
            "duration_ms": large_duration_ms,
            "declared_duration_seconds": 61,
            "source_sha256": "b" * 64,
            "media_lane": "large_media",
            "width": 1280,
            "height": 720,
            "fps": 30.0,
            "has_audio": True,
            "audio_stream_count": 1,
            "format_name": "mp4",
        },
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
    assert payload["media_lane"] == "large_media"
    assert payload["source_file_size"] == large_bytes
    assert payload["source_video_hash"] == "b" * 64
    assert payload["source_metadata"] == state["source_metadata"]
    assert payload["source_manifest"] == state["source_metadata"]
    assert "max_render_seconds" not in payload
    assert payload["charge_policy"] == "free_local_tool"
    assert payload["rights_confirmation"]["confirmed"] is True
    assert payload["rights_confirmation"]["policy"] == "video_edit_rights_v1"
    assert payload["rights_confirmation"]["user_id"] == "905"
    assert payload["rights_confirmation"]["review_revision"] == 3
    assert payload["rights_confirmation"]["confirmed_at_unix"] > 0
    assert canonical == ("local-free", 0, "{}")
    assert saved["step"] == "job_status"
    assert create_calls == 1
    assert query.edits and all("0 Xu" in text for text, _kwargs in query.edits)
    assert second_query.edits and "0 Xu" in second_query.edits[-1][0]
    assert "trạng thái tác vụ" in second_query.edits[-1][0].lower()

    query.edits.clear()
    duplicate_state = {**state, **deepcopy(saved)}
    assert asyncio.run(submit(update, SimpleNamespace(), duplicate_state)) is True
    assert query.edits
    assert "Trạng thái tác vụ" in query.edits[-1][0]


def test_confirm_local_invalid_inspection_evidence_creates_no_job_or_preflight(tmp_path: Path) -> None:
    db_path = tmp_path / "videoedit-invalid-evidence.sqlite3"
    _init_job_db(db_path)
    saved: dict = {}
    namespace = _submit_namespace(db_path, saved)

    class _EngineSpy:
        def __getattr__(self, name):
            return getattr(video_editengine1, name)

        @staticmethod
        def preflight(*_args, **_kwargs):
            raise AssertionError("preflight must not run for invalid evidence")

        @staticmethod
        def create_job(*_args, **_kwargs):
            raise AssertionError("create_job must not run for invalid evidence")

    namespace["video_editengine1"] = _EngineSpy()
    submit = _compile_function("submit_video_edit_local_free_job", namespace)
    state = _default_state(
        906,
        step="confirmation",
        current_screen="confirmation",
        status="confirmation_ready",
        review_revision=3,
    )
    state["source_metadata"]["ok"] = False
    query = _Query(906, "videoedit|confirm_local")
    update = SimpleNamespace(callback_query=query, message=None, effective_user=query.from_user)

    assert asyncio.run(submit(update, SimpleNamespace(), state)) is True

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='video_edit_jobs'"
        ).fetchone()[0] == 0
    finally:
        conn.close()
    assert len(query.edits) == 1
    recovery_text, recovery_kwargs = query.edits[0]
    assert "Kế hoạch chỉnh sửa vẫn được giữ" in recovery_text
    assert "chưa tạo tác vụ và chưa trừ Xu" in recovery_text
    assert recovery_kwargs == {"reply_markup": "upload-keyboard"}
    assert saved == {}


def test_free_submit_source_does_not_use_legacy_size_or_render_limits() -> None:
    submit = _function_source("submit_video_edit_local_free_job")

    assert "MAX_UPLOAD_BYTES" not in submit
    assert "max_render_seconds" not in submit


def _paid_video_edit_tail(*, price_xu: int = 300) -> dict:
    return {
        "video_product_type": "video_local_edit",
        "video_session_id": "paid-video-edit-session",
        "plan_revision": 3,
        "plan_approved": True,
        "package_id": "video-local-standard",
        "quality_tier_id": "300",
        "capability_snapshot": {"ok": True, "reason": "ok"},
        "pricing_snapshot": {"total_xu": price_xu},
    }


def test_paid_submit_queues_large_canonical_evidence_without_charge(tmp_path: Path) -> None:
    db_path = tmp_path / "videoedit-paid.sqlite3"
    _init_job_db(db_path)
    saved: dict = {}
    namespace = _submit_namespace(db_path, saved)
    calls = {"create": 0, "claim": 0, "charge": 0}

    class _EngineSpy:
        def __getattr__(self, name):
            return getattr(video_editengine1, name)

        @staticmethod
        def preflight(*_args, **_kwargs):
            return {"ok": True, "reason": "ok"}

        @staticmethod
        def create_job(*args, **kwargs):
            calls["create"] += 1
            return video_editengine1.create_job(*args, **kwargs)

        @staticmethod
        def claim_charge(*_args, **_kwargs):
            calls["claim"] += 1
            raise AssertionError("submit must not claim a charge")

        @staticmethod
        def charge(*_args, **_kwargs):
            calls["charge"] += 1
            raise AssertionError("submit must not charge")

    namespace["video_editengine1"] = _EngineSpy()
    submit = _compile_function("submit_local_video_editor_job", namespace)
    large_bytes = 51 * 1024 * 1024
    large_duration_ms = 61_000
    evidence_state = _video_edit_submit_evidence_state(
        actual_bytes=large_bytes,
        duration_ms=large_duration_ms,
        declared_bytes=large_bytes,
        declared_duration_seconds=61,
        media_lane="large_media",
    )
    state = _default_state(
        908,
        source_file_size=large_bytes,
        source_duration=61,
        source_duration_ms=large_duration_ms,
        source_video_hash="a" * 64,
        media_lane="large_media",
        source_metadata=evidence_state["source_metadata"],
    )
    query = _Query(908, "videoedit|confirm_paid")
    update = SimpleNamespace(callback_query=query, message=None, effective_user=query.from_user)

    assert asyncio.run(submit(update, SimpleNamespace(), state, tail=_paid_video_edit_tail())) is True

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 1
        payload = json.loads(conn.execute("SELECT input_file_id FROM local_worker_jobs").fetchone()[0])
        charge = conn.execute(
            "SELECT charge_state,charged_xu FROM video_edit_jobs"
        ).fetchone()
    finally:
        conn.close()

    assert payload["media_lane"] == "large_media"
    assert payload["source_file_size"] == large_bytes
    assert payload["source_video_hash"] == "a" * 64
    assert payload["source_metadata"] == evidence_state["source_metadata"]
    assert "max_render_seconds" not in payload
    assert payload["price_xu"] == 300
    assert payload["quoted_price_xu"] == 300
    assert payload["provider_call"] is False
    assert payload["charge_policy"] == "after_valid_mp4_delivery"
    assert charge == ("not_charged", 0)
    assert calls == {"create": 1, "claim": 0, "charge": 0}


@pytest.mark.parametrize(
    "concat_duration_fields",
    [
        pytest.param({"duration_seconds": 2}, id="top-level-duration-seconds"),
        pytest.param(
            {"metadata": {"duration_seconds": 2}},
            id="nested-duration-seconds",
        ),
    ],
)
def test_paid_submit_preflights_exact_final_plan_and_assets_before_side_effects(
    tmp_path: Path,
    concat_duration_fields: dict,
) -> None:
    db_path = tmp_path / "videoedit-paid-final-preflight.sqlite3"
    _init_job_db(db_path)
    saved: dict = {}
    namespace = _submit_namespace(db_path, saved)
    captured: dict = {}
    calls = {"preflight": 0, "db": 0, "create": 0, "claim": 0, "charge": 0}

    class _EngineSpy:
        def __getattr__(self, name):
            return getattr(video_editengine1, name)

        @staticmethod
        def preflight(current, runtime):
            calls["preflight"] += 1
            captured["state"] = deepcopy(current)
            captured["runtime"] = deepcopy(runtime)
            captured["capacity"] = video_editengine1._preflight_capacity_evidence(
                current,
                dict(current.get("source_metadata") or {}),
                dict(current.get("manual_edit_plan") or {}),
            )
            return {"ok": False, "reason": "local_worker_workspace_insufficient"}

        @staticmethod
        def create_job(*_args, **_kwargs):
            calls["create"] += 1
            raise AssertionError("blocked preflight must not create a job")

        @staticmethod
        def claim_charge(*_args, **_kwargs):
            calls["claim"] += 1
            raise AssertionError("submit must not claim a charge")

        @staticmethod
        def charge(*_args, **_kwargs):
            calls["charge"] += 1
            raise AssertionError("submit must not charge")

    def blocked_db_connect():
        calls["db"] += 1
        raise AssertionError("blocked preflight must stop before opening the job database")

    namespace["video_editengine1"] = _EngineSpy()
    namespace["db_connect"] = blocked_db_connect
    submit = _compile_function("submit_local_video_editor_job", namespace)
    state = _default_state(
        913,
        source_duration_ms=5_000,
        concat_sources=[{
            "file_id": "concat-final",
            "file_size": 2_000,
            "mime_type": "video/mp4",
            **concat_duration_fields,
        }],
        subtitle_source={
            "file_id": "subtitle-final",
            "file_size": 1_000,
            "mime_type": "text/srt",
        },
    )
    state["manual_edit_plan"]["trim"] = {"start_ms": 0, "end_ms": 0}
    state["manual_edit_plan"]["speed"] = 0.5
    state["manual_edit_plan"]["text_overlay"] = {
        "content": "Tiêu đề thường",
        "position": "top_center",
        "start_ms": 0,
        "end_ms": 4_000,
        "font_size": 42,
        "outline": 2,
    }
    tail = _paid_video_edit_tail(price_xu=500)
    tail.update({
        "quality_tier_id": "500",
        "audio_config": {
            "source_audio_available": True,
            "source_audio": True,
            "dubbing": False,
            "music": False,
            "sfx": False,
            "subtitles": False,
            "volumes": {"source_audio": 65},
        },
        "logo_config": {
            "enabled": True,
            "asset_file_id": "tail-logo-final",
            "file_size": 4_000,
            "mime_type": "image/webp",
            "position": "center_right",
        },
        "watermark_config": {
            "enabled": True,
            "text": "TOAN AAS",
            "position": "bottom_center",
            "opacity_percent": 45,
        },
    })
    query = _Query(913, "videoedit|confirm_paid")
    update = SimpleNamespace(
        callback_query=query,
        message=None,
        effective_user=query.from_user,
    )

    assert asyncio.run(submit(update, SimpleNamespace(), state, tail=tail)) is True

    preflight_state = captured["state"]
    final_plan = preflight_state["manual_edit_plan"]
    assert final_plan["resolution"] == "1080p"
    assert final_plan["volume"] == 0.65
    assert final_plan["logo_overlay"] == {
        "position": "center_right",
        "scale": 0.12,
        "opacity": 1.0,
    }
    assert final_plan["text_overlay"]["content"] == "Tiêu đề thường"
    assert final_plan["text_overlay"]["position"] == "top_center"
    assert final_plan["text_overlay"]["end_ms"] == 4_000
    assert final_plan["watermark_overlay"]["content"] == "TOAN AAS"
    assert final_plan["watermark_overlay"]["position"] == "bottom_center"
    assert final_plan["watermark_overlay"]["opacity"] == 0.45
    assert final_plan["watermark_overlay"]["end_ms"] == 0
    assert preflight_state["logo_source"] == {
        "file_id": "tail-logo-final",
        "file_name": "logo.png",
        "mime_type": "image/webp",
        "file_size": 4_000,
    }
    assert captured["capacity"]["declared_input_bytes"] == 4_096 + 2_000 + 1_000 + 4_000
    assert calls == {"preflight": 1, "db": 0, "create": 0, "claim": 0, "charge": 0}

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN ('video_edit_jobs','video_edit_outbox')"
        ).fetchone()[0] == 0
    finally:
        conn.close()
    assert saved == {}


def test_paid_confirmation_retry_reuses_canonical_identity_without_charge(tmp_path: Path) -> None:
    db_path = tmp_path / "videoedit-paid-retry.sqlite3"
    _init_job_db(db_path)
    saved: dict = {}
    namespace = _submit_namespace(db_path, saved)
    calls = {"create": 0, "claim": 0, "charge": 0}

    class _EngineSpy:
        def __getattr__(self, name):
            return getattr(video_editengine1, name)

        @staticmethod
        def preflight(*_args, **_kwargs):
            return {"ok": True, "reason": "ok"}

        @staticmethod
        def create_job(*args, **kwargs):
            calls["create"] += 1
            return video_editengine1.create_job(*args, **kwargs)

        @staticmethod
        def claim_charge(*_args, **_kwargs):
            calls["claim"] += 1
            raise AssertionError("submit must not claim a charge")

        @staticmethod
        def charge(*_args, **_kwargs):
            calls["charge"] += 1
            raise AssertionError("submit must not charge")

    namespace["video_editengine1"] = _EngineSpy()
    namespace["video_edit_submit_inspection_evidence"] = lambda _state: {
        "ok": True,
        "media_lane": "large_media",
        "source_metadata": {},
        "actual_bytes": 51 * 1024 * 1024,
        "duration_ms": 61_000,
        "source_sha256": "a" * 64,
    }
    submit = _compile_function("submit_local_video_editor_job", namespace)
    evidence_state = _video_edit_submit_evidence_state(
        actual_bytes=51 * 1024 * 1024,
        duration_ms=61_000,
        declared_bytes=51 * 1024 * 1024,
        declared_duration_seconds=61,
        media_lane="large_media",
    )
    state = _default_state(
        910,
        selected_tool="manual",
        source_file_size=51 * 1024 * 1024,
        source_duration=61,
        source_duration_ms=61_000,
        source_video_hash="a" * 64,
        media_lane="large_media",
        source_metadata=evidence_state["source_metadata"],
        concat_sources=[{"file_id": "concat-paid-1", "mime_type": "video/mp4"}],
        logo_source={"file_id": "logo-paid-1", "mime_type": "image/png"},
        subtitle_source={"file_id": "subtitle-paid-1", "mime_type": "text/srt"},
        split_mode="custom",
        split_ranges=[
            {"index": 1, "start_ms": 0, "end_ms": 30_000},
            {"index": 2, "start_ms": 30_000, "end_ms": 61_000},
        ],
        coverage_required=False,
    )
    first_query = _Query(910, "videoedit|confirm_paid")
    second_query = _Query(910, "videoedit|confirm_paid")
    first_update = SimpleNamespace(
        callback_query=first_query,
        message=None,
        effective_user=first_query.from_user,
    )
    second_update = SimpleNamespace(
        callback_query=second_query,
        message=None,
        effective_user=second_query.from_user,
    )

    assert asyncio.run(submit(first_update, SimpleNamespace(), state, tail=_paid_video_edit_tail())) is True
    assert asyncio.run(submit(second_update, SimpleNamespace(), state, tail=_paid_video_edit_tail())) is True

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM video_edit_outbox").fetchone()[0] == 1
        assert conn.execute("SELECT charge_state,charged_xu FROM video_edit_jobs").fetchone() == (
            "not_charged",
            0,
        )
        payload = json.loads(conn.execute("SELECT input_file_id FROM local_worker_jobs").fetchone()[0])
    finally:
        conn.close()
    assert "source_manifest" not in payload
    assert "plan_schema_version" not in payload
    assert payload["local1_mode"] == "manual"
    assert payload["split_mode"] == "custom"
    assert payload["split_ranges"] == state["split_ranges"]
    assert payload["coverage_required"] is False
    assert payload["concat_sources"] == state["concat_sources"]
    assert payload["logo_source"] == state["logo_source"]
    assert payload["subtitle_source"] == state["subtitle_source"]
    assert calls == {"create": 1, "claim": 0, "charge": 0}
    assert second_query.edits and "Đã nhận yêu cầu xử lý video" in second_query.edits[-1][0]


def test_paid_retry_reuses_pre_feature_worker_identity_without_charge(tmp_path: Path) -> None:
    db_path = tmp_path / "videoedit-paid-pre-feature-retry.sqlite3"
    _init_job_db(db_path)
    nested_manifest = {
        "asset_id": "historic-paid-source",
        "transport": {"storage_key": "video-edit/historic-paid-source.mp4"},
    }
    evidence_state = _video_edit_submit_evidence_state(
        actual_bytes=4_096,
        declared_bytes=4_096,
    )
    source_metadata = {
        **evidence_state["source_metadata"],
        "source_manifest": nested_manifest,
    }
    state = _default_state(912, source_metadata=source_metadata)
    tail = _paid_video_edit_tail()
    normalized_tail = video_tail9.normalize_state(tail)
    plan = deepcopy(state["manual_edit_plan"])
    plan["resolution"] = "720p"
    pre_feature_payload = {
        "local1_contract": 1,
        "local1_mode": "manual",
        "product_type": video_editengine1.PRODUCT_TYPE,
        "flow_owner": "video_edit",
        "engine_route": video_editengine1.ENGINE_ROUTE,
        "worker_owner": video_editengine1.OUTBOX_OWNER,
        "worker_capability": video_editengine1.WORKER_CAPABILITY,
        "user_id": "912",
        "chat_id": str(_Message.chat_id),
        "source_file_id": state["source_file_id"],
        "source_video_id": state["source_video_id"],
        "source_video_hash": state["source_video_hash"],
        "source_file_name": state["source_file_name"],
        "source_file_size": state["source_file_size"],
        "source_metadata": source_metadata,
        "media_lane": state["media_lane"],
        "state_revision": state["state_revision"],
        "ratio": "keep",
        "audio_policy": "preserve_if_present",
        "manual_edit_plan": plan,
        "concat_sources": [],
        "logo_source": {},
        "subtitle_source": {},
        "split_mode": "",
        "split_ranges": [],
        "coverage_required": True,
        "charge_policy": "after_valid_mp4_delivery",
        "price_xu": 300,
        "quoted_price_xu": 300,
        "quality_tier_id": "300",
        "provider_call": False,
    }
    assert "plan_schema_version" not in pre_feature_payload
    assert "source_manifest" not in pre_feature_payload

    conn = sqlite3.connect(db_path)
    try:
        seeded = video_editengine1.create_job(
            conn,
            user_id=912,
            chat_id=str(_Message.chat_id),
            edit_session_id=state["edit_session_id"],
            source_file_id=state["source_file_id"],
            source_metadata=source_metadata,
            plan=plan,
            tail=normalized_tail,
            quality_tier_id="300",
            price_xu=300,
            worker_payload=pre_feature_payload,
        )
        conn.commit()
    finally:
        conn.close()
    assert seeded["created"] is True

    saved: dict = {}
    namespace = _submit_namespace(db_path, saved)
    calls = {"create": 0, "claim": 0, "charge": 0}
    lookup_keys: list[tuple[str, str]] = []

    class _EngineSpy:
        def __getattr__(self, name):
            return getattr(video_editengine1, name)

        @staticmethod
        def preflight(*_args, **_kwargs):
            return {"ok": True, "reason": "ok"}

        @staticmethod
        def stable_idempotency_key(**kwargs):
            key = video_editengine1.stable_idempotency_key(**kwargs)
            lookup_keys.append(("v3", key))
            return key

        @staticmethod
        def _historic_v2_idempotency_key(**kwargs):
            key = video_editengine1._historic_v2_idempotency_key(**kwargs)
            lookup_keys.append(("v2", key))
            return key

        @staticmethod
        def create_job(*args, **kwargs):
            calls["create"] += 1
            return video_editengine1.create_job(*args, **kwargs)

        @staticmethod
        def claim_charge(*_args, **_kwargs):
            calls["claim"] += 1
            raise AssertionError("submit must not claim a charge")

        @staticmethod
        def charge(*_args, **_kwargs):
            calls["charge"] += 1
            raise AssertionError("submit must not charge")

    namespace["video_editengine1"] = _EngineSpy()
    submit = _compile_function("submit_local_video_editor_job", namespace)
    query = _Query(912, "videoedit|confirm_paid")
    update = SimpleNamespace(callback_query=query, message=None, effective_user=query.from_user)

    assert asyncio.run(submit(update, SimpleNamespace(), state, tail=tail)) is True

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM video_edit_outbox").fetchone()[0] == 1
        assert conn.execute("SELECT charge_state,charged_xu FROM video_edit_jobs").fetchone() == (
            "not_charged",
            0,
        )
        queued_payload = json.loads(
            conn.execute("SELECT input_file_id FROM local_worker_jobs").fetchone()[0]
        )
    finally:
        conn.close()

    assert queued_payload["source_metadata"] == source_metadata
    assert queued_payload["source_video_hash"] == state["source_video_hash"]
    assert queued_payload["source_file_size"] == state["source_file_size"]
    assert queued_payload["media_lane"] == state["media_lane"]
    assert "source_manifest" not in queued_payload
    assert "plan_schema_version" not in queued_payload
    assert lookup_keys[0] == ("v3", seeded["idempotency_key"])
    assert [version for version, _key in lookup_keys] == ["v3", "v2"]
    assert calls == {"create": 1, "claim": 0, "charge": 0}
    assert query.edits and "Đã nhận yêu cầu xử lý video" in query.edits[-1][0]


def test_paid_submit_value_error_fails_closed_without_job_or_charge(tmp_path: Path) -> None:
    db_path = tmp_path / "videoedit-paid-value-error.sqlite3"
    _init_job_db(db_path)
    saved: dict = {}
    namespace = _submit_namespace(db_path, saved)
    calls = {"create": 0, "claim": 0, "charge": 0}

    class _EngineSpy:
        def __getattr__(self, name):
            return getattr(video_editengine1, name)

        @staticmethod
        def preflight(*_args, **_kwargs):
            return {"ok": True, "reason": "ok"}

        @staticmethod
        def create_job(*_args, **_kwargs):
            calls["create"] += 1
            raise ValueError("idempotency_identity_mismatch:tail")

        @staticmethod
        def claim_charge(*_args, **_kwargs):
            calls["claim"] += 1
            raise AssertionError("submit must not claim a charge")

        @staticmethod
        def charge(*_args, **_kwargs):
            calls["charge"] += 1
            raise AssertionError("submit must not charge")

    namespace["video_editengine1"] = _EngineSpy()
    submit = _compile_function("submit_local_video_editor_job", namespace)
    query = _Query(911, "videoedit|confirm_paid")
    update = SimpleNamespace(callback_query=query, message=None, effective_user=query.from_user)

    assert asyncio.run(
        submit(update, SimpleNamespace(), _default_state(911), tail=_paid_video_edit_tail())
    ) is True

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM video_edit_outbox").fetchone()[0] == 0
    finally:
        conn.close()
    assert calls == {"create": 1, "claim": 0, "charge": 0}
    assert query.edits == [
        (
            "⚠️ Chưa thể lưu tác vụ chỉnh sửa. TOAN AAS chưa trừ Xu.",
            {"reply_markup": "quality-keyboard"},
        )
    ]
    assert saved.get("edit_session_id") == "edit-911"
    assert saved.get("step") == "options"
    assert saved.get("current_screen") == "workspace"
    assert saved.get("status") == "source_ready"


def test_paid_submit_invalid_evidence_stops_before_preflight_or_job(tmp_path: Path) -> None:
    db_path = tmp_path / "videoedit-paid-invalid.sqlite3"
    _init_job_db(db_path)
    saved: dict = {}
    namespace = _submit_namespace(db_path, saved)

    class _EngineSpy:
        def __getattr__(self, name):
            return getattr(video_editengine1, name)

        @staticmethod
        def preflight(*_args, **_kwargs):
            raise AssertionError("preflight must not run for invalid evidence")

        @staticmethod
        def create_job(*_args, **_kwargs):
            raise AssertionError("create_job must not run for invalid evidence")

    namespace["video_editengine1"] = _EngineSpy()
    submit = _compile_function("submit_local_video_editor_job", namespace)
    state = _default_state(909)
    state["source_metadata"]["ok"] = False
    query = _Query(909, "videoedit|confirm_paid")
    update = SimpleNamespace(callback_query=query, message=None, effective_user=query.from_user)

    assert asyncio.run(submit(update, SimpleNamespace(), state, tail=_paid_video_edit_tail())) is True

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='video_edit_jobs'"
        ).fetchone()[0] == 0
    finally:
        conn.close()
    assert len(query.edits) == 1
    recovery_text, recovery_kwargs = query.edits[0]
    assert "Kế hoạch chỉnh sửa vẫn được giữ" in recovery_text
    assert "chưa tạo tác vụ và chưa trừ Xu" in recovery_text
    assert recovery_kwargs == {"parse_mode": None, "reply_markup": "upload-keyboard"}
    assert saved == {}


def test_paid_submit_source_does_not_use_legacy_size_or_render_limits() -> None:
    submit = _function_source("submit_local_video_editor_job")

    assert "MAX_UPLOAD_BYTES" not in submit
    assert "max_render_seconds" not in submit


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
            raise RuntimeError("telegram edit failed after state commit")
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
        manual_edit_plan=video_local_editing.neutral_split_manual_plan(),
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
    with pytest.raises(RuntimeError, match="telegram edit failed after state commit"):
        asyncio.run(submit(first_update, SimpleNamespace(), deepcopy(state)))
    assert saved["step"] == "job_status"
    assert saved["job_id"] > 0

    retry_query = _Query(907, "videoedit|confirm_local")
    retry_update = SimpleNamespace(
        callback_query=retry_query,
        message=None,
        effective_user=retry_query.from_user,
    )
    assert asyncio.run(submit(retry_update, SimpleNamespace(), deepcopy(saved))) is True

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 1
    finally:
        conn.close()
    assert retry_query.edits
    assert "Trạng thái tác vụ" in retry_query.edits[-1][0]
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


def test_videoedit_stale_render_model_covers_every_owned_screen_family() -> None:
    source = _function_source("video_editor_current_render_model")
    for marker in (
        "video_local_frame_text",
        "video_local_transform_text",
        "video_local_color_text",
        "video_local_overlay_text",
        "video_local_branding_text",
        "video_local_watermark_text",
        "video_local_logo_keyboard",
        "video_local_watermark_keyboard",
        "video_local_cut_options_text",
        "video_local_join_options_text",
        "video_edit_audio_text",
        "video_edit_effects_text",
        "video_ai_edit_source_summary_text",
        "video_quality_enhance_source_text",
        "video_local_choice_keyboard",
        "video_edit_state_machine.resume_callback",
    ):
        assert marker in source
    assert "Tiếp tục bước hiện tại" in source


def test_split_owned_state_uses_a_fail_closed_callback_allowlist() -> None:
    helper = _function_source("video_editor_split_callback_allowed")
    callback = _function_source("handle_video_editor_callback")
    assert "split_owned_allowed_actions" in helper
    assert 'action == "options"' in helper
    assert 'parts[2] == "split"' in helper
    assert 'action == "upload"' in helper
    assert 'current_screen == "split"' in helper
    assert "video_editor_split_callback_allowed(action, parts, split_owned_state)" in callback
    assert "stale_manual_actions_while_split" not in callback


def test_split_reset_uses_a_duration_independent_neutral_manual_plan() -> None:
    callback = _function_source("handle_video_editor_callback")
    start = callback.index('if action == "split_reset_manual":')
    end = callback.index('if action == "concat":', start)
    reset = callback[start:end]
    assert "neutral_split_manual_plan" in reset
    assert '"end_ms": source_duration_ms' not in reset


def test_every_split_entry_reuses_the_canonical_neutral_plan_contract() -> None:
    callback = _function_source("handle_video_editor_callback")
    pending_upload = _function_source("handle_video_editor_pending_upload")
    options_start = callback.index('if action == "options":')
    options_end = callback.index("legacy_choice = {", options_start)
    split_start = callback.index('if action == "split_from_manual":')
    split_end = callback.index('if action == "split_reset_manual":', split_start)

    assert "neutral_split_manual_plan" in callback[options_start:options_end]
    assert "neutral_split_manual_plan" in callback[split_start:split_end]
    assert "neutral_split_manual_plan" in pending_upload


def test_videoedit_summary_copy_is_vietnamese_without_changing_other_products() -> None:
    import bot as bot_module

    for product_type in ("video_edit", "video_local_edit"):
        text = bot_module.video_tail9_summary_text(
            {"video_product_type": product_type}
        )
        markup = bot_module.video_tail9_summary_keyboard(
            {"video_product_type": product_type}
        )
        labels = [
            button.text
            for row in markup.inline_keyboard
            for button in row
        ]
        assert "Tổng hợp chỉnh sửa video" in text
        assert "chọn gói" not in text.lower()
        assert "🖼 Logo ảnh" in labels
        assert "🏷️ Watermark chữ" in labels
        assert not any("logo và watermark" in label.lower() for label in labels)

    product_tail = {
        "video_product_type": "product_video",
        "video_flow_owner": "product_video",
    }
    product_text = bot_module.video_tail9_summary_text(product_tail)
    product_markup = bot_module.video_tail9_summary_keyboard(product_tail)
    product_labels = [
        button.text
        for row in product_markup.inline_keyboard
        for button in row
    ]
    assert "Prompt video" in product_text
    assert "Âm thanh/Add-on" in product_text
    assert "Logo/Watermark" in product_text
    assert "owner product_video" in product_text
    assert any("Tiếp tục chọn gói" in label for label in product_labels)
    assert "🖼️ Sửa Logo/Watermark" in product_labels
