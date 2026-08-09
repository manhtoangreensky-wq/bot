from __future__ import annotations

import asyncio
from copy import deepcopy
import errno
import importlib
from pathlib import Path
import sys
from types import SimpleNamespace

import bot
import pytest
from services import video_edit_state_machine, video_local_editing


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


class _Message:
    def __init__(self, text: str, message_id: int = 901) -> None:
        self.text = text
        self.message_id = message_id
        self.chat_id = 901
        self.replies: list[tuple[str, dict]] = []

    async def reply_text(self, text: str, **kwargs):
        self.replies.append((text, kwargs))
        return SimpleNamespace(message_id=self.message_id + 1)


class _Query:
    def __init__(self, user_id: int, data: str) -> None:
        self.id = f"videoedit-{user_id}-{data}"
        self.from_user = SimpleNamespace(id=user_id, first_name="Video Edit")
        self.data = data
        self.message = _Message("")
        self.edits: list[tuple[str, dict]] = []
        self.answers: list[tuple[tuple, dict]] = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))
        return None

    async def edit_message_text(self, text: str, **kwargs):
        self.edits.append((text, kwargs))
        return None


def _ready_state(user_id: int, *, step: str = "options") -> dict:
    plan = video_local_editing.default_manual_edit_plan("")
    plan["trim"] = {"start_ms": 0, "end_ms": 60_000}
    return {
        "step": step,
        "edit_mode": "manual_edit",
        "current_screen": "workspace",
        "screen_id": "workspace",
        "parent_callback": "videoedit|manual",
        "entry_parent_callback": "videoedit|manual",
        "selected_tool": "manual",
        "entry_context": "manual",
        "last_section": "manual",
        "source_file_id": "telegram-source",
        "source_file_name": "source.mp4",
        "source_display_name": "source.mp4",
        "source_file_size": 4096,
        "source_duration": 60,
        "source_duration_ms": 60_000,
        "source_video_id": "telegram-source",
        "source_video_hash": "a" * 64,
        "media_lane": "short_media",
        "source_metadata": {
            "ok": True,
            "actual_bytes": 4096,
            "declared_bytes": 4096,
            "duration": 60.0,
            "duration_ms": 60_000,
            "declared_duration_seconds": 60,
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
        "concat_sources": [],
        "logo_source": {},
        "watermark_config": {},
        "subtitle_source": {},
        "edit_session_id": f"edit-{user_id}",
        "session_id": f"edit-{user_id}",
        "state_revision": 3,
        "revision": 3,
        "status": "source_ready",
    }


def _store_state(user_id: int, state: dict) -> dict:
    fields = deepcopy(state)
    step = str(fields.pop("step"))
    return bot.set_video_editor_pending(user_id, step, **fields)


def _run_pending_text(user_id: int, text: str) -> tuple[bool, _Message]:
    message = _Message(text)
    update = SimpleNamespace(
        callback_query=None,
        message=message,
        effective_user=SimpleNamespace(id=user_id),
    )
    handled = asyncio.run(
        bot.handle_video_editor_pending_text(
            update,
            SimpleNamespace(user_data={}),
        )
    )
    return handled, message


def _button_pairs(markup) -> list[tuple[str, str]]:
    return [
        (button.text, button.callback_data)
        for row in markup.inline_keyboard
        for button in row
    ]


def _press_callback(user_id: int, callback: str) -> _Query:
    query = _Query(user_id, callback)
    asyncio.run(
        bot.handle_video_editor_callback(
            SimpleNamespace(callback_query=query),
            SimpleNamespace(user_data={}),
        )
    )
    return query


def test_videoedit_logo_image_and_text_watermark_are_distinct_products() -> None:
    workspace = _button_pairs(bot.video_local_manual_options_keyboard("vi", _ready_state(900)))
    overlay = _button_pairs(bot.video_local_overlay_keyboard("vi"))
    visible = workspace + overlay

    assert ("🖼 Logo ảnh", "videoedit|logo_entry") in visible
    assert ("🏷️ Watermark chữ", "videoedit|watermark_entry") in visible
    assert not any("Logo & watermark" in label or "Logo / watermark" in label for label, _ in visible)

    assert video_edit_state_machine.parent_callback("logo_input") == "videoedit|branding"
    assert video_edit_state_machine.parent_callback("watermark_input") == "videoedit|branding"
    assert video_edit_state_machine.resume_callback("watermark_input", "watermark_text") == "videoedit|watermark_text"
    assert video_edit_state_machine.review_back_callback({"return_to": "watermark_options"}) == "videoedit|watermark_options"


def test_videoedit_logo_screen_consumes_text_and_never_releases_it_to_chat() -> None:
    user_id = 91_001
    bot.clear_video_editor_pending(user_id)
    try:
        state = _ready_state(user_id, step="await_logo")
        state.update(
            {
                "current_screen": "logo_input",
                "screen_id": "logo_input",
                "parent_callback": "videoedit|branding",
                "pending_field": "logo",
            }
        )
        before = _store_state(user_id, state)

        handled, message = _run_pending_text(user_id, "TOAN AAS")

        assert handled is True
        assert bot.video_editor_state_snapshot(bot.get_video_editor_pending(user_id)) == bot.video_editor_state_snapshot(before)
        assert len(message.replies) == 1
        reply, kwargs = message.replies[0]
        assert "Logo ảnh" in reply
        assert "Watermark chữ" in reply
        callbacks = {callback for _, callback in _button_pairs(kwargs["reply_markup"])}
        assert "videoedit|watermark_entry" in callbacks
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_watermark_text_is_owned_and_persists_independently() -> None:
    user_id = 91_002
    bot.clear_video_editor_pending(user_id)
    try:
        state = _ready_state(user_id, step="await_watermark_text")
        state.update(
            {
                "current_screen": "watermark_input",
                "screen_id": "watermark_input",
                "parent_callback": "videoedit|branding",
                "pending_field": "watermark_text",
            }
        )
        source_evidence = {
            key: deepcopy(state[key])
            for key in (
                "source_file_id",
                "source_file_size",
                "source_duration_ms",
                "source_video_hash",
                "source_metadata",
                "inspection_complete",
            )
        }
        _store_state(user_id, state)

        handled, message = _run_pending_text(user_id, "© TOAN AAS")

        assert handled is True
        current = deepcopy(bot.get_video_editor_pending(user_id))
        assert current["step"] == "watermark_options"
        assert current["current_screen"] == "watermark_options"
        assert current["watermark_config"] == {
            "enabled": True,
            "text": "© TOAN AAS",
            "position": "bottom_right",
            "opacity": 0.45,
        }
        overlay = current["manual_edit_plan"]["watermark_overlay"]
        assert overlay["content"] == "© TOAN AAS"
        assert overlay["position"] == "bottom_right"
        assert overlay["opacity"] == 0.45
        assert overlay["start_ms"] == 0
        assert overlay["end_ms"] == 60_000
        for key, value in source_evidence.items():
            assert current[key] == value
        assert len(message.replies) == 1
        assert "Watermark chữ" in message.replies[0][0]
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_watermark_text_defers_end_while_concat_is_pending() -> None:
    user_id = 91_024
    bot.clear_video_editor_pending(user_id)
    try:
        state = _ready_state(user_id, step="await_watermark_text")
        plan = dict(state["manual_edit_plan"])
        plan["concat_inputs"] = ["video_1"]
        state.update(
            {
                "current_screen": "watermark_input",
                "screen_id": "watermark_input",
                "parent_callback": "videoedit|branding",
                "pending_field": "watermark_text",
                "manual_edit_plan": plan,
                "concat_sources": [
                    {
                        "file_id": "append-source",
                        "metadata": {"duration_ms": 5_000},
                    }
                ],
            }
        )
        _store_state(user_id, state)

        handled, _message = _run_pending_text(user_id, "TOAN AAS")

        assert handled is True
        current = dict(bot.get_video_editor_pending(user_id) or {})
        assert current["manual_edit_plan"]["watermark_overlay"]["end_ms"] == 0
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_watermark_screen_consumes_image_without_cross_product_fallthrough() -> None:
    user_id = 91_012
    bot.clear_video_editor_pending(user_id)
    try:
        state = _ready_state(user_id, step="await_watermark_text")
        state.update(
            {
                "current_screen": "watermark_input",
                "screen_id": "watermark_input",
                "parent_callback": "videoedit|workspace",
                "watermark_parent_callback": "videoedit|workspace",
                "pending_field": "watermark_text",
            }
        )
        before = _store_state(user_id, state)
        message = _Message("")
        message.photo = [SimpleNamespace(file_id="wrong-image")]
        update = SimpleNamespace(
            callback_query=None,
            message=message,
            effective_user=SimpleNamespace(id=user_id),
        )

        assert asyncio.run(
            bot.handle_video_editor_pending_upload(
                update,
                SimpleNamespace(user_data={}),
            )
        ) is True
        assert bot.get_video_editor_pending(user_id) == before
        assert len(message.replies) == 1
        assert "Watermark chữ chỉ nhận văn bản" in message.replies[0][0]
        assert ("⬅️ Quay lại", "videoedit|workspace") in _button_pairs(
            message.replies[0][1]["reply_markup"]
        )
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_active_screen_fences_unsolicited_media_from_other_products() -> None:
    user_id = 91_013
    bot.clear_video_editor_pending(user_id)
    try:
        state = _ready_state(user_id, step="review")
        state.update({"current_screen": "review", "status": "review_ready"})
        before = _store_state(user_id, state)
        message = _Message("")
        message.document = SimpleNamespace(file_id="unrequested-media")
        update = SimpleNamespace(
            callback_query=None,
            message=message,
            effective_user=SimpleNamespace(id=user_id),
        )

        assert asyncio.run(
            bot.handle_video_editor_pending_upload(
                update,
                SimpleNamespace(user_data={}),
            )
        ) is True
        assert bot.get_video_editor_pending(user_id) == before
        assert len(message.replies) == 1
        assert "phiên Chỉnh sửa video" in message.replies[0][0]
        assert "không chuyển sang sản phẩm khác" in message.replies[0][0]
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_active_state_has_a_hard_text_ownership_fence() -> None:
    user_id = 91_003
    bot.clear_video_editor_pending(user_id)
    try:
        state = _ready_state(user_id, step="review")
        state.update({"current_screen": "review", "status": "review_ready"})
        _store_state(user_id, state)
        message = _Message("đây là tin của tác vụ chỉnh sửa")
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=user_id),
        )

        assert bot.video_editor_owns_text_message(state) is True
        assert asyncio.run(
            bot.handle_video_editor_owned_text_fallback(
                update,
                SimpleNamespace(user_data={}),
            )
        ) is True
        assert len(message.replies) == 1
        assert "phiên Chỉnh sửa video" in message.replies[0][0]

        handler_start = BOT_SOURCE.index("async def handle_message")
        handler_end = BOT_SOURCE.index("\nasync def ", handler_start + 1)
        handler = BOT_SOURCE[handler_start:handler_end]
        fence = handler.index("handle_video_editor_owned_text_fallback")
        assert fence < handler.index("handle_frame_video_pending_text")
        assert fence < handler.index("handle_aichat_message")
    finally:
        bot.clear_video_editor_pending(user_id)


@pytest.mark.parametrize(
    ("step", "screen", "pending_field", "text"),
    (
        ("await_logo", "logo_input", "logo", "TOAN AAS"),
        (
            "await_watermark_text",
            "watermark_input",
            "watermark_text",
            "© TOAN AAS",
        ),
        ("await_brightness", "brightness_input", "brightness", "200"),
        ("await_trim_edges", "trim_input", "trim_edges", "00:10-00:40"),
    ),
)
def test_actual_handle_message_keeps_videoedit_text_out_of_chat_and_admin_tools(
    monkeypatch: pytest.MonkeyPatch,
    step: str,
    screen: str,
    pending_field: str,
    text: str,
) -> None:
    user_id = 91_030
    bot.clear_video_editor_pending(user_id)
    cross_product_calls: list[str] = []

    async def forbidden_handler(name: str, _update, _context) -> bool:
        cross_product_calls.append(name)
        return True

    monkeypatch.setattr(
        bot,
        "handle_broadcast_lite_pending_text",
        lambda update, context: forbidden_handler("broadcast", update, context),
    )
    monkeypatch.setattr(
        bot,
        "handle_frame_video_pending_text",
        lambda update, context: forbidden_handler("frame", update, context),
    )
    monkeypatch.setattr(
        bot,
        "handle_aichat_message",
        lambda update, context: forbidden_handler("chat", update, context),
    )
    try:
        state = _ready_state(user_id, step=step)
        state.update(
            {
                "current_screen": screen,
                "screen_id": screen,
                "pending_field": pending_field,
                "parent_callback": (
                    "videoedit|branding"
                    if step in {"await_logo", "await_watermark_text"}
                    else "videoedit|color"
                    if step == "await_brightness"
                    else "videoedit|cut"
                ),
            }
        )
        _store_state(user_id, state)
        message = _Message(text)

        asyncio.run(
            bot.handle_message(
                SimpleNamespace(
                    callback_query=None,
                    message=message,
                    effective_user=SimpleNamespace(id=user_id),
                ),
                SimpleNamespace(user_data={}),
            )
        )

        assert cross_product_calls == []
        assert len(message.replies) == 1
        assert bot.get_video_editor_pending(user_id)
    finally:
        bot.clear_video_editor_pending(user_id)


@pytest.mark.parametrize(
    ("user_id", "chat_id", "message_id", "entry_callbacks", "expected_owner"),
    (
        (
            91_040,
            -100_091_040,
            91_040,
            ("create_media|quick_image", "create_media|qi_custom"),
            "quick_image",
        ),
        (
            91_041,
            -100_091_041,
            91_041,
            ("create_media|image_tier_low",),
            "public_image",
        ),
    ),
)
def test_public_image_entry_releases_a_stale_videoedit_text_owner(
    user_id: int,
    chat_id: int,
    message_id: int,
    entry_callbacks: tuple[str, ...],
    expected_owner: str,
) -> None:
    bot.clear_video_editor_pending(user_id)
    bot.clear_quick_image_flow(user_id)
    bot.clear_public_image_prompt_pending(user_id)
    bot.clear_media_aspect_pending(user_id)
    try:
        stale = _ready_state(user_id, step="await_brightness")
        stale.update(
            {
                "current_screen": "brightness_input",
                "screen_id": "brightness_input",
                "pending_field": "brightness",
                "parent_callback": "videoedit|color",
            }
        )
        _store_state(user_id, stale)
        context = SimpleNamespace(user_data={})

        for callback in entry_callbacks:
            query = _Query(user_id, callback)
            asyncio.run(
                bot.handle_create_media_callback(
                    SimpleNamespace(callback_query=query),
                    context,
                )
            )

        message = _Message("© TOAN AAS", message_id=message_id)
        message.chat = SimpleNamespace(id=chat_id)
        asyncio.run(
            bot.handle_message(
                SimpleNamespace(
                    callback_query=None,
                    message=message,
                    effective_message=message,
                    effective_user=SimpleNamespace(id=user_id),
                    effective_chat=SimpleNamespace(id=chat_id),
                ),
                context,
            )
        )

        assert bot.get_video_editor_pending(user_id) == {}
        assert len(message.replies) == 1
        assert "Vui lòng nhập một số từ 20 đến 200" not in message.replies[0][0]
        if expected_owner == "quick_image":
            assert (bot.get_quick_image_flow(user_id) or {}).get("step") == "prepared_prompt"
        else:
            pending = bot.get_media_aspect_pending(user_id, "image") or {}
            assert pending.get("prompt") == "© TOAN AAS"
    finally:
        bot.clear_video_editor_pending(user_id)
        bot.clear_quick_image_flow(user_id)
        bot.clear_public_image_prompt_pending(user_id)
        bot.clear_media_aspect_pending(user_id)
        bot.TELEGRAM_MESSAGE_DEDUPE_DONE.pop(f"{chat_id}:{message_id}", None)
        bot.TELEGRAM_MESSAGE_DEDUPE_LOCKS.pop(f"{chat_id}:{message_id}", None)


def test_videoedit_state_restores_after_process_memory_loss(
    monkeypatch,
    tmp_path: Path,
) -> None:
    store = importlib.import_module("services.video_edit_state_store")
    user_id = 91_006
    monkeypatch.setenv("VIDEO_EDITOR_STATE_DIR", str(tmp_path / "editor-state"))
    monkeypatch.setenv("VIDEO_EDITOR_DURABLE_STATE_TEST", "1")
    bot.clear_video_editor_pending(user_id)
    try:
        expected = _store_state(user_id, _ready_state(user_id, step="await_brightness"))
        assert store.state_path(user_id).is_file()

        bot.USER_PENDING.pop(bot.video_editor_pending_key(user_id), None)
        restored = bot.get_video_editor_pending(user_id)

        assert bot.video_editor_state_snapshot(restored) == bot.video_editor_state_snapshot(expected)
        assert bot.video_editor_owns_text_message(restored) is True

        bot.clear_video_editor_pending(user_id)
        bot.USER_PENDING.pop(bot.video_editor_pending_key(user_id), None)
        assert bot.get_video_editor_pending(user_id) == {}
        assert not store.state_path(user_id).exists()
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_durable_read_reconciles_replaced_state_over_stale_memory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    store = importlib.import_module("services.video_edit_state_store")
    user_id = 91_026
    monkeypatch.setenv("VIDEO_EDITOR_STATE_DIR", str(tmp_path / "replace"))
    monkeypatch.setenv("VIDEO_EDITOR_DURABLE_STATE_TEST", "1")
    bot.clear_video_editor_pending(user_id)
    try:
        original = _store_state(user_id, _ready_state(user_id, step="await_brightness"))
        replacement = _ready_state(user_id, step="await_watermark_text")
        replacement["created_at_ts"] = original["created_at_ts"]
        replacement["current_screen"] = "watermark_input"
        replacement["screen_id"] = "watermark_input"
        replacement["pending_field"] = "watermark_text"
        store.save_state(user_id, replacement, root=tmp_path / "replace")

        current = bot.get_video_editor_pending(user_id)

        assert current["step"] == "await_watermark_text"
        assert current["step"] != original["step"]
        assert bot.USER_PENDING[bot.video_editor_pending_key(user_id)]["step"] == "await_watermark_text"
    finally:
        bot.USER_PENDING.pop(bot.video_editor_pending_key(user_id), None)
        store.delete_state(user_id, root=tmp_path / "replace")


def test_videoedit_durable_read_clears_memory_after_external_delete(
    monkeypatch,
    tmp_path: Path,
) -> None:
    store = importlib.import_module("services.video_edit_state_store")
    user_id = 91_027
    monkeypatch.setenv("VIDEO_EDITOR_STATE_DIR", str(tmp_path / "delete"))
    monkeypatch.setenv("VIDEO_EDITOR_DURABLE_STATE_TEST", "1")
    bot.clear_video_editor_pending(user_id)
    try:
        _store_state(user_id, _ready_state(user_id, step="await_brightness"))
        assert bot.USER_PENDING[bot.video_editor_pending_key(user_id)]
        store.delete_state(user_id, root=tmp_path / "delete")

        assert bot.get_video_editor_pending(user_id) == {}
        assert bot.video_editor_pending_key(user_id) not in bot.USER_PENDING
    finally:
        bot.USER_PENDING.pop(bot.video_editor_pending_key(user_id), None)
        store.delete_state(user_id, root=tmp_path / "delete")


def test_videoedit_owned_media_wins_over_an_active_other_product_session(
    monkeypatch,
) -> None:
    user_id = 91_028
    bot.clear_video_editor_pending(user_id)
    try:
        state = _ready_state(user_id, step="await_watermark_text")
        state.update(
            {
                "current_screen": "watermark_input",
                "screen_id": "watermark_input",
                "parent_callback": "videoedit|branding",
                "pending_field": "watermark_text",
            }
        )
        before = _store_state(user_id, state)
        monkeypatch.setattr(bot, "get_video_session", lambda _uid: {"product_id": "frame_video"})
        message = _Message("")
        message.photo = [SimpleNamespace(file_id="wrong-image")]
        update = SimpleNamespace(
            callback_query=None,
            message=message,
            effective_user=SimpleNamespace(id=user_id),
        )

        assert asyncio.run(
            bot.handle_video_editor_pending_upload(
                update,
                SimpleNamespace(user_data={}),
            )
        ) is True
        assert bot.get_video_editor_pending(user_id) == before
        assert len(message.replies) == 1
        assert "Watermark chữ chỉ nhận văn bản" in message.replies[0][0]
    finally:
        bot.clear_video_editor_pending(user_id)


@pytest.mark.parametrize(
    "function_name",
    [
        "submit_video_ai_edit_job",
        "submit_video_edit_local_free_job",
        "submit_local_video_editor_job",
    ],
)
def test_videoedit_submit_paths_fence_entry_state_before_job_side_effects(
    function_name: str,
) -> None:
    start = BOT_SOURCE.index(f"async def {function_name}")
    next_start = BOT_SOURCE.find("\nasync def ", start + 1)
    body = BOT_SOURCE[start: next_start if next_start >= 0 else len(BOT_SOURCE)]

    assert "begin_video_editor_submission(" in body
    assert "finish_video_editor_submission(" in body
    assert "clear_video_editor_pending(uid)" not in body


def test_videoedit_submission_begin_preserves_a_newer_durable_winner(
    monkeypatch,
    tmp_path: Path,
) -> None:
    store = importlib.import_module("services.video_edit_state_store")
    user_id = 91_029
    monkeypatch.setenv("VIDEO_EDITOR_STATE_DIR", str(tmp_path / "submit-begin"))
    monkeypatch.setenv("VIDEO_EDITOR_DURABLE_STATE_TEST", "1")
    bot.clear_video_editor_pending(user_id)
    try:
        first = _store_state(user_id, _ready_state(user_id, step="confirmation"))
        winner = {**first, "step": "await_watermark_text", "status": "input_ready"}
        store.save_state(user_id, winner, root=tmp_path / "submit-begin")

        with pytest.raises(bot.VideoEditorStateCommitError) as error:
            bot.begin_video_editor_submission(user_id, first, lane="local-free")

        assert error.value.winner == winner
        assert bot.get_video_editor_pending(user_id) == winner
    finally:
        bot.USER_PENDING.pop(bot.video_editor_pending_key(user_id), None)
        store.delete_state(user_id, root=tmp_path / "submit-begin")


def test_videoedit_submission_finish_never_clears_a_newer_winner(
    monkeypatch,
    tmp_path: Path,
) -> None:
    store = importlib.import_module("services.video_edit_state_store")
    user_id = 91_030
    monkeypatch.setenv("VIDEO_EDITOR_STATE_DIR", str(tmp_path / "submit-finish"))
    monkeypatch.setenv("VIDEO_EDITOR_DURABLE_STATE_TEST", "1")
    bot.clear_video_editor_pending(user_id)
    try:
        first = _store_state(user_id, _ready_state(user_id, step="confirmation"))
        reserved = bot.begin_video_editor_submission(user_id, first, lane="local-paid")
        winner = {**reserved, "step": "await_logo", "status": "input_ready"}
        store.save_state(user_id, winner, root=tmp_path / "submit-finish")

        committed, current = bot.finish_video_editor_submission(
            user_id,
            reserved,
            {},
            replacement_exists=False,
        )

        assert committed is False
        assert current == winner
        assert bot.get_video_editor_pending(user_id) == winner
    finally:
        bot.USER_PENDING.pop(bot.video_editor_pending_key(user_id), None)
        store.delete_state(user_id, root=tmp_path / "submit-finish")


@pytest.mark.parametrize("guard_kind", ["message", "callback"])
def test_videoedit_restored_state_survives_failed_reply_rollback(
    monkeypatch,
    tmp_path: Path,
    guard_kind: str,
) -> None:
    user_id = 91_007 if guard_kind == "message" else 91_008
    monkeypatch.setenv("VIDEO_EDITOR_STATE_DIR", str(tmp_path / guard_kind))
    monkeypatch.setenv("VIDEO_EDITOR_DURABLE_STATE_TEST", "1")
    bot.clear_video_editor_pending(user_id)
    expected = _store_state(user_id, _ready_state(user_id, step="await_brightness"))
    bot.USER_PENDING.pop(bot.video_editor_pending_key(user_id), None)

    async def failing_handler(update, _context):
        current = bot.get_video_editor_pending(user_id)
        bot.update_video_editor_pending(
            user_id,
            "review",
            current_screen="review",
            manual_edit_plan=deepcopy(current["manual_edit_plan"]),
        )
        raise RuntimeError("telegram render failed")

    guarded = (
        bot.video_editor_message_state_guard(failing_handler)
        if guard_kind == "message"
        else bot.video_editor_callback_state_guard(failing_handler)
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        message=_Message("200") if guard_kind == "message" else None,
        callback_query=(
            SimpleNamespace(from_user=SimpleNamespace(id=user_id))
            if guard_kind == "callback"
            else None
        ),
    )
    try:
        with pytest.raises(RuntimeError, match="telegram render failed"):
            asyncio.run(guarded(update, SimpleNamespace(user_data={})))
        bot.USER_PENDING.pop(bot.video_editor_pending_key(user_id), None)
        assert bot.video_editor_state_snapshot(bot.get_video_editor_pending(user_id)) == bot.video_editor_state_snapshot(expected)
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_corrupt_durable_created_at_fails_closed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    store = importlib.import_module("services.video_edit_state_store")
    user_id = 91_009
    monkeypatch.setenv("VIDEO_EDITOR_STATE_DIR", str(tmp_path / "corrupt-created-at"))
    monkeypatch.setenv("VIDEO_EDITOR_DURABLE_STATE_TEST", "1")
    state = _ready_state(user_id, step="await_brightness")
    state["created_at_ts"] = "not-a-number"
    store.save_state(user_id, state)
    bot.USER_PENDING.pop(bot.video_editor_pending_key(user_id), None)

    assert bot.get_video_editor_pending(user_id) == {}
    assert not store.state_path(user_id).exists()


def test_videoedit_clear_does_not_report_success_when_durable_delete_failed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    user_id = 91_010
    monkeypatch.setenv("VIDEO_EDITOR_STATE_DIR", str(tmp_path / "delete-failure"))
    monkeypatch.setenv("VIDEO_EDITOR_DURABLE_STATE_TEST", "1")
    expected = _store_state(user_id, _ready_state(user_id))

    with monkeypatch.context() as patcher:
        patcher.setattr(
            bot.video_edit_state_store,
            "compare_and_swap_state",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("denied")),
        )
        patcher.setattr(
            bot.video_edit_state_store,
            "delete_state",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("denied")),
        )
        with pytest.raises(RuntimeError, match="video_editor_state_commit_failed"):
            bot.clear_video_editor_pending(user_id)
        assert bot.get_video_editor_pending(user_id) == expected

    assert bot.clear_video_editor_pending(user_id) is True


def test_videoedit_durable_compare_and_swap_preserves_newer_process_winner(
    monkeypatch,
    tmp_path: Path,
) -> None:
    store = importlib.import_module("services.video_edit_state_store")
    user_id = 91_011
    root = tmp_path / "durable-cas"
    first = _ready_state(user_id, step="await_brightness")
    second = {**first, "step": "await_trim_edges", "state_revision": 4}
    stale_replacement = {**first, "step": "review", "state_revision": 3}
    store.save_state(user_id, first, root=root)
    store.save_state(user_id, second, root=root)

    replaced, winner = store.compare_and_swap_state(
        user_id,
        expected_state=first,
        replacement_state=stale_replacement,
        root=root,
    )

    assert replaced is False
    assert winner == second
    assert store.load_state(user_id, root=root) == second


@pytest.mark.parametrize("stale_action", ["update", "clear"])
def test_videoedit_stale_ordinary_mutation_preserves_newer_process_winner(
    monkeypatch,
    tmp_path: Path,
    stale_action: str,
) -> None:
    store = importlib.import_module("services.video_edit_state_store")
    user_id = 91_012 if stale_action == "update" else 91_013
    monkeypatch.setenv("VIDEO_EDITOR_STATE_DIR", str(tmp_path / stale_action))
    monkeypatch.setenv("VIDEO_EDITOR_DURABLE_STATE_TEST", "1")
    bot.clear_video_editor_pending(user_id)
    first = _store_state(user_id, _ready_state(user_id, step="await_brightness"))
    winner = {
        **first,
        "step": "await_trim_edges",
        "state_revision": 4,
        "revision": 4,
    }
    replaced, _ = store.compare_and_swap_state(
        user_id,
        expected_state=first,
        replacement_state=winner,
    )
    assert replaced is True
    # Model a second bot process winning durable CAS while this process still
    # holds the older in-memory snapshot.  A stale transition must use the
    # exact compare-and-set API; ordinary reads now reconcile to the winner.
    assert bot.video_editor_state_snapshot(
        bot.USER_PENDING[bot.video_editor_pending_key(user_id)]
    ) == bot.video_editor_state_snapshot(first)

    if stale_action == "update":
        committed, current = bot.compare_and_set_video_editor_pending(
            user_id,
            first,
            "review",
            current_screen="review",
            state_revision=3,
        )
        assert committed is False
        assert current == winner
    else:
        with pytest.raises(RuntimeError, match="video_editor_state_commit_conflict"):
            bot.compare_and_replace_video_editor_pending(
                user_id,
                first,
                {},
                replacement_exists=False,
                expected_exists=True,
                raise_on_failure=True,
            )

    assert bot.video_editor_state_snapshot(
        bot.get_video_editor_pending(user_id)
    ) == bot.video_editor_state_snapshot(winner)
    assert store.load_state(user_id) == winner
    assert bot.clear_video_editor_pending(user_id) is True


@pytest.mark.parametrize("has_existing_state", [False, True])
def test_videoedit_durable_write_failure_never_commits_memory_only_state(
    monkeypatch,
    tmp_path: Path,
    has_existing_state: bool,
) -> None:
    store = importlib.import_module("services.video_edit_state_store")
    user_id = 91_014 if has_existing_state else 91_015
    monkeypatch.setenv("VIDEO_EDITOR_STATE_DIR", str(tmp_path / "write-failure"))
    monkeypatch.setenv("VIDEO_EDITOR_DURABLE_STATE_TEST", "1")
    bot.clear_video_editor_pending(user_id)
    expected = (
        _store_state(user_id, _ready_state(user_id, step="await_brightness"))
        if has_existing_state
        else {}
    )

    def fail_write(*_args, **_kwargs):
        raise OSError("disk unavailable")

    with monkeypatch.context() as patcher:
        patcher.setattr(store, "save_state", fail_write)
        patcher.setattr(store, "compare_and_swap_state", fail_write)
        replacement = _ready_state(user_id)
        replacement.pop("step", None)
        replacement["current_screen"] = "review"
        with pytest.raises(RuntimeError, match="video_editor_state_commit_failed"):
            bot.set_video_editor_pending(
                user_id,
                "review",
                **replacement,
            )

    assert bot.video_editor_state_snapshot(
        bot.get_video_editor_pending(user_id)
    ) == bot.video_editor_state_snapshot(expected)
    assert store.load_state(user_id) == expected
    if expected:
        assert bot.clear_video_editor_pending(user_id) is True


@pytest.mark.parametrize("guard_kind", ["message", "callback"])
def test_videoedit_state_guard_rerenders_newer_winner_after_stale_mutation(
    monkeypatch,
    tmp_path: Path,
    guard_kind: str,
) -> None:
    store = importlib.import_module("services.video_edit_state_store")
    user_id = 91_016 if guard_kind == "message" else 91_017
    monkeypatch.setenv("VIDEO_EDITOR_STATE_DIR", str(tmp_path / guard_kind))
    monkeypatch.setenv("VIDEO_EDITOR_DURABLE_STATE_TEST", "1")
    bot.clear_video_editor_pending(user_id)
    first = _store_state(user_id, _ready_state(user_id, step="await_brightness"))
    winner = {
        **first,
        "step": "await_trim_edges",
        "current_screen": "trim",
        "state_revision": 4,
        "revision": 4,
    }
    rerenders: list[dict] = []

    real_get = bot.get_video_editor_pending
    raced = False

    def get_with_race(uid):
        nonlocal raced
        current = real_get(uid)
        if uid == user_id and not raced:
            raced = True
            store.save_state(uid, winner)
        return current

    monkeypatch.setattr(bot, "get_video_editor_pending", get_with_race)

    async def record_rerender(_target, state, _lang):
        rerenders.append(bot.video_editor_state_snapshot(state))

    monkeypatch.setattr(bot, "rerender_video_editor_after_stale_commit", record_rerender)
    monkeypatch.setattr(bot, "get_user_language", lambda _user_id: "vi")

    async def stale_message_handler(_update, _context):
        bot.update_video_editor_pending(user_id, "review", current_screen="review")
        raise AssertionError("stale mutation continued")

    async def stale_callback_handler(_update, _context):
        bot.update_video_editor_pending(user_id, "review", current_screen="review")
        raise AssertionError("stale mutation continued")

    if guard_kind == "message":
        guarded = bot.video_editor_message_state_guard(stale_message_handler)
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=user_id),
            message=_Message("200"),
            callback_query=None,
        )
    else:
        guarded = bot.video_editor_callback_state_guard(stale_callback_handler)
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=user_id),
            message=None,
            callback_query=SimpleNamespace(from_user=SimpleNamespace(id=user_id)),
        )

    assert asyncio.run(guarded(update, SimpleNamespace(user_data={}))) is True
    assert raced is True
    assert rerenders == [bot.video_editor_state_snapshot(winner)]
    assert store.load_state(user_id) == winner
    assert bot.clear_video_editor_pending(user_id) is True


def test_videoedit_expired_cache_cannot_delete_a_fresh_durable_winner(
    monkeypatch,
    tmp_path: Path,
) -> None:
    store = importlib.import_module("services.video_edit_state_store")
    user_id = 91_018
    monkeypatch.setenv("VIDEO_EDITOR_STATE_DIR", str(tmp_path / "expired-race"))
    monkeypatch.setenv("VIDEO_EDITOR_DURABLE_STATE_TEST", "1")
    bot.clear_video_editor_pending(user_id)
    expired = _ready_state(user_id, step="await_brightness")
    expired["created_at_ts"] = 1.0
    winner = _ready_state(user_id, step="await_trim_edges")
    winner["created_at_ts"] = __import__("time").time()
    winner["state_revision"] = 9
    winner["revision"] = 9
    store.save_state(user_id, winner)
    bot.USER_PENDING[bot.video_editor_pending_key(user_id)] = deepcopy(expired)

    restored = bot.get_video_editor_pending(user_id)

    assert bot.video_editor_state_snapshot(restored) == bot.video_editor_state_snapshot(winner)
    assert store.load_state(user_id) == winner
    assert bot.clear_video_editor_pending(user_id) is True


def test_videoedit_restart_read_failure_keeps_text_and_media_owned(
    monkeypatch,
    tmp_path: Path,
) -> None:
    user_id = 91_019
    monkeypatch.setenv("VIDEO_EDITOR_STATE_DIR", str(tmp_path / "read-failure"))
    monkeypatch.setenv("VIDEO_EDITOR_DURABLE_STATE_TEST", "1")
    bot.USER_PENDING.pop(bot.video_editor_pending_key(user_id), None)
    monkeypatch.setattr(
        bot.video_edit_state_store,
        "load_state",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError("denied")),
    )

    with pytest.raises(bot.VideoEditorStateUnavailableError):
        bot.get_video_editor_pending(user_id)

    message = _Message("200")
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        message=message,
        callback_query=None,
    )
    asyncio.run(bot.handle_message(update, SimpleNamespace(user_data={})))
    assert len(message.replies) == 1
    assert "không chuyển sang Chatbot" in message.replies[0][0]


def test_videoedit_state_store_propagates_file_read_errors(
    monkeypatch,
    tmp_path: Path,
) -> None:
    store = importlib.import_module("services.video_edit_state_store")
    user_id = 91_020
    root = tmp_path / "unreadable-state"
    store.save_state(user_id, _ready_state(user_id), root=root)
    expected_path = store.state_path(user_id, root=root)
    original_read_text = Path.read_text

    def fail_selected_path(path: Path, *args, **kwargs):
        if path == expected_path:
            raise PermissionError("denied")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_selected_path)
    with pytest.raises(PermissionError, match="denied"):
        store.load_state(user_id, root=root)
    assert expected_path.exists()


@pytest.mark.parametrize(
    "contention_errno",
    [
        pytest.param(errno.EACCES, id="eacces"),
        pytest.param(errno.EAGAIN, id="eagain"),
    ],
)
def test_videoedit_state_store_posix_lock_is_bounded_and_error_specific(
    monkeypatch,
    contention_errno: int,
) -> None:
    store = importlib.import_module("services.video_edit_state_store")
    lock_flags: list[int] = []

    class FakeClock:
        def __init__(self) -> None:
            self.now = 100.0
            self.sleeps: list[float] = []

        def monotonic(self) -> float:
            return self.now

        def sleep(self, seconds: float) -> None:
            self.sleeps.append(seconds)
            self.now += seconds

    class NonEmptyHandle:
        def seek(self, _offset: int, _whence: int = 0) -> None:
            return None

        def tell(self) -> int:
            return 1

        def fileno(self) -> int:
            return 73

    clock = FakeClock()
    fake_fcntl = SimpleNamespace(LOCK_EX=2, LOCK_NB=4)

    def contend(_fd: int, flags: int) -> None:
        lock_flags.append(flags)
        raise OSError(contention_errno, "busy")

    fake_fcntl.flock = contend
    monkeypatch.setattr(
        store,
        "os",
        SimpleNamespace(name="posix", SEEK_END=2),
    )
    monkeypatch.setattr(store, "_LOCK_TIMEOUT_SECONDS", 0.025)
    retry_interval = 0.01
    monkeypatch.setattr(
        store,
        "time",
        SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep),
    )
    monkeypatch.setitem(sys.modules, "fcntl", fake_fcntl)

    started_at = clock.now
    with pytest.raises(
        TimeoutError,
        match="^video_editor_state_lock_timeout$",
    ):
        store._lock_handle(NonEmptyHandle())

    assert len(lock_flags) > 1
    assert set(lock_flags) == {fake_fcntl.LOCK_EX | fake_fcntl.LOCK_NB}
    elapsed = clock.now - started_at
    assert elapsed >= store._LOCK_TIMEOUT_SECONDS
    assert elapsed <= store._LOCK_TIMEOUT_SECONDS + retry_interval
    assert clock.sleeps
    assert set(clock.sleeps) == {retry_interval}

    sleeps_before_non_contention = list(clock.sleeps)

    def fail_without_contention(_fd: int, flags: int) -> None:
        lock_flags.append(flags)
        raise OSError(errno.EIO, "disk failure")

    fake_fcntl.flock = fail_without_contention
    with pytest.raises(OSError) as error:
        store._lock_handle(NonEmptyHandle())

    assert error.value.errno == errno.EIO
    assert clock.sleeps == sleeps_before_non_contention
    assert lock_flags[-1] == fake_fcntl.LOCK_EX | fake_fcntl.LOCK_NB


def test_videoedit_state_store_windows_lock_retries_only_eacces_and_propagates_other_errors(
    monkeypatch,
) -> None:
    store = importlib.import_module("services.video_edit_state_store")
    retry_interval = 0.01
    timeout = 0.025
    lock_calls: list[tuple[int, int, int]] = []

    class FakeClock:
        def __init__(self) -> None:
            self.now = 100.0
            self.sleeps: list[float] = []

        def monotonic(self) -> float:
            return self.now

        def sleep(self, seconds: float) -> None:
            self.sleeps.append(seconds)
            self.now += seconds

    class NonEmptyHandle:
        def seek(self, _offset: int, _whence: int = 0) -> None:
            return None

        def tell(self) -> int:
            return 1

        def fileno(self) -> int:
            return 73

    clock = FakeClock()
    fake_msvcrt = SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2)

    def contend(fd: int, mode: int, size: int) -> None:
        lock_calls.append((fd, mode, size))
        raise OSError(errno.EACCES, "busy")

    fake_msvcrt.locking = contend
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
    monkeypatch.setattr(store.os, "name", "nt")
    monkeypatch.setattr(store, "_LOCK_TIMEOUT_SECONDS", timeout)
    monkeypatch.setattr(
        store,
        "time",
        SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep),
    )

    started_at = clock.now
    with pytest.raises(
        TimeoutError,
        match="^video_editor_state_lock_timeout$",
    ):
        store._lock_handle(NonEmptyHandle())

    elapsed = clock.now - started_at
    assert len(lock_calls) > 1
    assert {mode for _fd, mode, _size in lock_calls} == {fake_msvcrt.LK_NBLCK}
    assert {size for _fd, _mode, size in lock_calls} == {1}
    assert elapsed >= timeout
    assert elapsed <= timeout + retry_interval
    assert clock.sleeps
    assert set(clock.sleeps) == {retry_interval}

    sleeps_before_non_contention = list(clock.sleeps)
    for failure_errno in (errno.EAGAIN, errno.EINVAL, errno.EIO, errno.EBADF):

        def fail_without_contention(
            fd: int,
            mode: int,
            size: int,
            *,
            failure_errno: int = failure_errno,
        ) -> None:
            lock_calls.append((fd, mode, size))
            raise OSError(failure_errno, "lock failure")

        fake_msvcrt.locking = fail_without_contention
        before = clock.now
        with pytest.raises(OSError) as error:
            store._lock_handle(NonEmptyHandle())
        assert error.value.errno == failure_errno
        assert clock.now == before
        assert clock.sleeps == sleeps_before_non_contention


def test_videoedit_state_store_process_lock_timeout_does_not_release(
    monkeypatch,
    tmp_path: Path,
) -> None:
    store = importlib.import_module("services.video_edit_state_store")

    class BusyProcessLock:
        def __init__(self) -> None:
            self.acquire_timeouts: list[float] = []
            self.release_calls = 0

        def acquire(self, *, timeout: float) -> bool:
            self.acquire_timeouts.append(timeout)
            return False

        def release(self) -> None:
            self.release_calls += 1

        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _traceback) -> bool:
            return False

    process_lock = BusyProcessLock()
    timeout = 0.125
    monkeypatch.setattr(store, "_LOCK", process_lock)
    monkeypatch.setattr(store, "_LOCK_TIMEOUT_SECONDS", timeout)
    path = store.state_path(91_034, root=tmp_path / "process-lock")

    with pytest.raises(
        TimeoutError,
        match="^video_editor_state_lock_timeout$",
    ):
        with store._state_file_lock(path):
            pass

    assert process_lock.acquire_timeouts == [timeout]
    assert process_lock.release_calls == 0


def test_videoedit_configured_state_root_symlink_is_rejected(
    monkeypatch,
    tmp_path: Path,
) -> None:
    store = importlib.import_module("services.video_edit_state_store")
    target = tmp_path / "outside-target"
    target.mkdir()
    configured = tmp_path / "configured-state"
    try:
        configured.symlink_to(target, target_is_directory=True)
    except OSError:
        original_realpath = store.os.path.realpath

        def simulate_link_resolution(value):
            if store.os.path.normcase(store.os.path.abspath(str(value))) == store.os.path.normcase(
                store.os.path.abspath(str(configured))
            ):
                return str(target)
            return original_realpath(value)

        monkeypatch.setattr(store.os.path, "realpath", simulate_link_resolution)

    assert store.state_root(configured) == configured.absolute()
    with pytest.raises(OSError, match="video_editor_state_root_symlink"):
        store.save_state(91_021, _ready_state(91_021), root=configured)
    assert not (target / "user-91021.json").exists()


def test_videoedit_photo_owner_precedes_stale_broadcast_draft(monkeypatch) -> None:
    calls: list[str] = []

    async def video_edit_owner(_update, _context):
        calls.append("video_edit")
        return True

    async def broadcast_owner(_update, _context):
        calls.append("broadcast")
        return True

    monkeypatch.setattr(bot, "handle_video_editor_pending_upload", video_edit_owner)
    monkeypatch.setattr(bot, "handle_broadcast_lite_pending_photo", broadcast_owner)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=91_022, first_name="Admin"),
        message=SimpleNamespace(photo=[SimpleNamespace(file_id="logo")]),
    )

    asyncio.run(bot.handle_photo(update, SimpleNamespace(user_data={})))

    assert calls == ["video_edit"]


def test_videoedit_photo_falls_through_to_broadcast_only_when_editor_declines(
    monkeypatch,
) -> None:
    calls: list[str] = []

    async def video_edit_declines(_update, _context):
        calls.append("video_edit")
        return False

    async def broadcast_accepts(_update, _context):
        calls.append("broadcast")
        return True

    monkeypatch.setattr(bot, "handle_video_editor_pending_upload", video_edit_declines)
    monkeypatch.setattr(bot, "handle_broadcast_lite_pending_photo", broadcast_accepts)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=91_023, first_name="Admin"),
        message=SimpleNamespace(photo=[SimpleNamespace(file_id="broadcast-photo")]),
    )

    asyncio.run(bot.handle_photo(update, SimpleNamespace(user_data={})))

    assert calls == ["video_edit", "broadcast"]


def test_videoedit_legacy_owned_steps_cannot_fall_through_to_chat() -> None:
    for step, selected_tool in (
        ("await_video", "manual"),
        ("await_ai_video", "ai_edit"),
    ):
        assert bot.video_editor_owns_text_message(
            {
                "step": step,
                "selected_tool": selected_tool,
                "current_screen": "upload",
            }
        ) is True


@pytest.mark.parametrize(
    ("screen", "expected"),
    (
        ("workspace", "videoedit|workspace"),
        ("overlay", "videoedit|overlay"),
        ("review", "videoedit|review"),
        ("branding", "videoedit|branding"),
    ),
)
def test_videoedit_logo_and_watermark_preserve_the_visible_parent(
    screen: str,
    expected: str,
) -> None:
    state = {"current_screen": screen, "parent_callback": expected}
    assert bot.video_local_logo_parent_callback(state) == expected
    assert bot.video_local_watermark_parent_callback(state) == expected


@pytest.mark.parametrize(
    ("source_screen", "resolver", "stale_marker"),
    (
        (
            "watermark_options",
            bot.video_local_logo_parent_callback,
            "logo_parent_callback",
        ),
        (
            "logo_options",
            bot.video_local_watermark_parent_callback,
            "watermark_parent_callback",
        ),
    ),
)
@pytest.mark.parametrize(
    "visible_parent",
    ("videoedit|workspace", "videoedit|overlay", "videoedit|review"),
)
def test_switching_branding_products_keeps_the_visible_parent(
    source_screen: str,
    resolver,
    stale_marker: str,
    visible_parent: str,
) -> None:
    state = {
        "current_screen": source_screen,
        "parent_callback": visible_parent,
        stale_marker: "videoedit|branding",
    }

    assert resolver(state) == visible_parent


def test_back_from_audio_upload_clears_the_pending_media_owner() -> None:
    user_id = 91_033
    bot.clear_video_editor_pending(user_id)
    try:
        _store_state(user_id, _ready_state(user_id))
        _press_callback(user_id, "videoedit|manual_audio")
        _press_callback(user_id, "videoedit|audio_add|music")
        waiting = dict(bot.get_video_editor_pending(user_id) or {})
        assert waiting["step"] == "await_audio_asset"
        assert waiting["awaiting_media"] is True
        assert waiting["pending_field"] == "audio_asset"

        query = _press_callback(user_id, "videoedit|audio")
        current = dict(bot.get_video_editor_pending(user_id) or {})
        text, _keyboard, _parse_mode = bot.video_editor_current_render_model(
            current,
            "vi",
        )

        assert current["step"] == "audio"
        assert current["current_screen"] == "audio"
        assert current["awaiting_media"] is False
        assert current["pending_field"] == ""
        assert current["audio_pending_kind"] == ""
        assert "Gửi video cần chỉnh sửa" not in text
        assert "âm thanh" in text.lower()
        assert ("⬅️ Quay lại", "videoedit|workspace") in _button_pairs(
            query.edits[-1][1]["reply_markup"]
        )
    finally:
        bot.clear_video_editor_pending(user_id)


def test_video_editor_session_files_are_excluded_from_git() -> None:
    ignored = {
        line.strip().replace("\\", "/")
        for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "video_editor_sessions/" in ignored


def _state_with_both_branding_products(user_id: int, *, screen: str) -> dict:
    state = _ready_state(user_id, step=f"{screen}")
    plan = deepcopy(state["manual_edit_plan"])
    plan["logo_overlay"] = {
        "position": "top_right",
        "scale": 0.12,
        "opacity": 1.0,
    }
    plan["watermark_overlay"] = {
        "content": "© TOAN AAS",
        "position": "bottom_right",
        "opacity": 0.45,
        "start_ms": 0,
        "end_ms": 60_000,
    }
    state.update(
        {
            "current_screen": screen,
            "screen_id": screen,
            "parent_callback": "videoedit|branding",
            "logo_parent_callback": "videoedit|branding",
            "watermark_parent_callback": "videoedit|branding",
            "return_to": screen,
            "pending_field": "",
            "manual_edit_plan": plan,
            "logo_source": {
                "file_id": "logo-image",
                "file_name": "logo.png",
                "file_size": 1_024,
            },
            "watermark_config": {
                "enabled": True,
                "text": "© TOAN AAS",
                "position": "bottom_right",
                "opacity": 0.45,
            },
        }
    )
    return state


def test_editing_and_removing_logo_preserves_the_text_watermark() -> None:
    user_id = 91_031
    bot.clear_video_editor_pending(user_id)
    try:
        original = _state_with_both_branding_products(
            user_id,
            screen="logo_options",
        )
        expected_watermark = deepcopy(original["watermark_config"])
        expected_overlay = deepcopy(
            original["manual_edit_plan"]["watermark_overlay"]
        )
        _store_state(user_id, original)

        changed = _press_callback(
            user_id,
            "videoedit|set|logo_position|bottom_left",
        )
        assert changed.answers
        current = deepcopy(bot.get_video_editor_pending(user_id))
        assert current["manual_edit_plan"]["logo_overlay"]["position"] == "bottom_left"
        assert current["watermark_config"] == expected_watermark
        assert current["manual_edit_plan"]["watermark_overlay"] == expected_overlay

        removed = _press_callback(user_id, "videoedit|logo_remove")
        assert removed.answers
        current = deepcopy(bot.get_video_editor_pending(user_id))
        assert current["logo_source"] == {}
        assert current["manual_edit_plan"]["logo_overlay"] == {}
        assert current["watermark_config"] == expected_watermark
        assert current["manual_edit_plan"]["watermark_overlay"] == expected_overlay
    finally:
        bot.clear_video_editor_pending(user_id)


def test_editing_and_removing_text_watermark_preserves_the_image_logo() -> None:
    user_id = 91_032
    bot.clear_video_editor_pending(user_id)
    try:
        original = _state_with_both_branding_products(
            user_id,
            screen="watermark_options",
        )
        expected_logo = deepcopy(original["logo_source"])
        expected_overlay = deepcopy(original["manual_edit_plan"]["logo_overlay"])
        _store_state(user_id, original)

        changed = _press_callback(
            user_id,
            "videoedit|set|watermark_position|top_left",
        )
        assert changed.answers
        current = deepcopy(bot.get_video_editor_pending(user_id))
        assert current["watermark_config"]["position"] == "top_left"
        assert current["logo_source"] == expected_logo
        assert current["manual_edit_plan"]["logo_overlay"] == expected_overlay

        removed = _press_callback(user_id, "videoedit|watermark_remove")
        assert removed.answers
        current = deepcopy(bot.get_video_editor_pending(user_id))
        assert current["watermark_config"] == {}
        assert "watermark_overlay" not in current["manual_edit_plan"]
        assert current["logo_source"] == expected_logo
        assert current["manual_edit_plan"]["logo_overlay"] == expected_overlay
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_summary_exposes_separate_branding_products() -> None:
    summary = _button_pairs(
        bot.video_tail9_summary_keyboard({"video_product_type": "video_local_edit"})
    )
    assert ("🖼 Logo ảnh", "videoedit|logo_entry") in summary
    assert ("🏷️ Watermark chữ", "videoedit|watermark_entry") in summary
    assert not any(
        "logo và watermark" in label.lower()
        or "logo / watermark" in label.lower()
        or "logo & watermark" in label.lower()
        for label, _callback in summary
    )


def test_videoedit_review_back_knows_the_branding_hub() -> None:
    assert (
        video_edit_state_machine.review_back_callback({"return_to": "branding"})
        == "videoedit|branding"
    )


def test_videoedit_branding_keyboards_keep_review_back_unique() -> None:
    for keyboard in (
        bot.video_local_logo_keyboard("vi", back_callback="videoedit|review"),
        bot.video_local_watermark_keyboard("vi", back_callback="videoedit|review"),
    ):
        callbacks = [callback for _label, callback in _button_pairs(keyboard)]
        assert callbacks.count("videoedit|review") == 1
        assert len(callbacks) == len(set(callbacks))
        assert ("⬅️ Quay lại", "videoedit|review") in _button_pairs(keyboard)


def test_brightness_and_trim_keep_the_inspected_source_evidence() -> None:
    cases = (
        (91_004, "await_brightness", "200"),
        (91_005, "await_trim_edges", "00:10-00:40"),
    )
    for user_id, step, text in cases:
        bot.clear_video_editor_pending(user_id)
        try:
            state = _ready_state(user_id, step=step)
            source_evidence = {
                key: deepcopy(state[key])
                for key in (
                    "source_file_id",
                    "source_file_size",
                    "source_duration_ms",
                    "source_video_hash",
                    "source_metadata",
                    "inspection_complete",
                )
            }
            _store_state(user_id, state)

            handled, message = _run_pending_text(user_id, text)

            assert handled is True
            assert len(message.replies) == 1
            current = deepcopy(bot.get_video_editor_pending(user_id))
            for key, value in source_evidence.items():
                assert current[key] == value
            assert "Video chưa có thông tin kỹ thuật hợp lệ" not in message.replies[0][0]
            assert "Bạn muốn mình giúp gì" not in message.replies[0][0]
        finally:
            bot.clear_video_editor_pending(user_id)


def test_watermark_has_an_independent_render_plan_and_alpha_drawtext() -> None:
    plan = video_local_editing.default_manual_edit_plan("source.mp4")
    plan.update(
        {
            "trim": {"start_ms": 0, "end_ms": 5_000},
            "text_overlay": {
                "content": "Tiêu đề thường",
                "position": "top_center",
                "start_ms": 0,
                "end_ms": 1_000,
                "font_size": 42,
                "outline": 2,
            },
            "watermark_overlay": {
                "content": "© TOAN AAS",
                "position": "bottom_right",
                "start_ms": 0,
                "end_ms": 5_000,
                "font_size": 32,
                "outline": 2,
                "opacity": 0.45,
            },
            "logo_overlay": {
                "path": "logo.png",
                "position": "top_right",
                "scale": 0.12,
                "opacity": 0.75,
            },
        }
    )

    normalized = video_local_editing.normalize_manual_edit_plan(
        plan,
        source_duration_ms=5_000,
    )

    assert normalized["text_overlay"]["content"] == "Tiêu đề thường"
    assert normalized["watermark_overlay"]["content"] == "© TOAN AAS"
    assert normalized["watermark_overlay"]["opacity"] == 0.45
    assert normalized["logo_overlay"]["path"] == "logo.png"
    filters = video_local_editing.required_optional_filters(
        normalized,
        has_audio=False,
    )
    assert "drawtext" in filters
    command = video_local_editing.build_manual_ffmpeg_command(
        normalized,
        output_path="output.mp4",
        source_probe={"width": 1280, "height": 720, "fps": 30, "has_audio": False},
        ffmpeg_path="ffmpeg",
    )
    rendered = " ".join(command)
    assert rendered.count("drawtext=") == 2
    assert "fontcolor=white@0.450" in rendered
    assert "bordercolor=black@0.405" in rendered
    assert "overlay=" in rendered

    summary = video_local_editing.public_plan_summary(
        normalized,
        source_duration_ms=5_000,
    )
    assert "Chèn chữ" in summary
    assert any(item.startswith("Watermark chữ") for item in summary)
    assert any(item.startswith("Logo ảnh") for item in summary)
    assert not any("Logo / watermark" in item for item in summary)


def test_default_watermark_end_waits_for_the_final_concat_speed_timeline() -> None:
    plan = video_local_editing.default_manual_edit_plan("source.mp4")
    plan.update(
        {
            "trim": {"start_ms": 0, "end_ms": 2_000},
            "remove_middle": {"start_ms": 500, "end_ms": 1_000},
            "concat_inputs": ["append.mp4"],
            "speed": 0.5,
            "watermark_overlay": {
                "content": "TOAN AAS",
                "position": "bottom_right",
                "start_ms": 0,
                "font_size": 28,
                "outline": 2,
                "opacity": 0.45,
            },
        }
    )

    before_concat = video_local_editing.normalize_manual_edit_plan(
        plan,
        source_duration_ms=2_000,
    )
    assert before_concat["watermark_overlay"]["end_ms"] == 0

    after_concat_plan = deepcopy(before_concat)
    after_concat_plan["concat_inputs"] = []
    after_concat_plan["trim"] = {"start_ms": 0, "end_ms": 2_500}
    after_concat_plan["remove_middle"] = {}
    after_concat = video_local_editing.normalize_manual_edit_plan(
        after_concat_plan,
        source_duration_ms=2_500,
    )
    assert after_concat["watermark_overlay"]["end_ms"] == 5_000
