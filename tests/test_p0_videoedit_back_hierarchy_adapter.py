from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import bot
from services import video_local_editing


class _Message:
    chat_id = 88101

    def __init__(self) -> None:
        self.replies: list[tuple[str, dict]] = []

    async def reply_text(self, text: str, **kwargs):
        self.replies.append((text, kwargs))
        return None


class _Query:
    def __init__(self, user_id: int, data: str) -> None:
        self.id = f"cb-{user_id}-{data}"
        self.from_user = SimpleNamespace(id=user_id, first_name="Video Edit")
        self.data = data
        self.message = _Message()
        self.edits: list[tuple[str, dict]] = []
        self.answers: list[tuple[tuple, dict]] = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))
        return None

    async def edit_message_text(self, text: str, **kwargs):
        self.edits.append((text, kwargs))
        return None


def _callbacks(markup) -> list[str]:
    return [
        str(button.callback_data or "")
        for row in markup.inline_keyboard
        for button in row
    ]


def _last_markup(query: _Query):
    if query.edits:
        return query.edits[-1][1].get("reply_markup")
    if query.message.replies:
        return query.message.replies[-1][1].get("reply_markup")
    return None


def _ready_state(user_id: int) -> None:
    bot.clear_video_editor_pending(user_id)
    plan = video_local_editing.default_manual_edit_plan("")
    plan["trim"] = {"start_ms": 0, "end_ms": 10_000}
    bot.set_video_editor_pending(
        user_id,
        "options",
        edit_mode="manual_edit",
        current_screen="workspace",
        selected_tool="manual",
        last_section="manual",
        source_file_id="telegram-source",
        source_file_name="source.mp4",
        source_display_name="source.mp4",
        source_file_size=4096,
        source_duration_ms=10_000,
        source_metadata={
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
        inspection_complete=True,
        manual_edit_plan=plan,
        edit_session_id=f"edit-{user_id}",
        state_revision=1,
    )


def _press(user_id: int, callback: str) -> _Query:
    query = _Query(user_id, callback)
    update = SimpleNamespace(callback_query=query)
    asyncio.run(bot.handle_video_editor_callback(update, SimpleNamespace()))
    return query


def test_videoedit_workspace_exposes_every_real_local_group() -> None:
    callbacks = _callbacks(bot.video_local_manual_options_keyboard("vi"))
    assert callbacks == [
        "videoedit|cut",
        "videoedit|join",
        "videoedit|frame",
        "videoedit|transform",
        "videoedit|audio",
        "videoedit|color",
        "videoedit|overlay",
        "videoedit|effects",
        "videoedit|source_info",
        "videoedit|review",
        "videoedit|manual",
        "menu|main",
    ]


@pytest.mark.parametrize(
    ("open_callback", "expected_back"),
    [
        ("videoedit|manual_cut", "videoedit|workspace"),
        ("videoedit|trim_edges", "videoedit|cut"),
        ("videoedit|split_from_manual", "videoedit|cut"),
        ("videoedit|manual_join", "videoedit|workspace"),
        ("videoedit|concat", "videoedit|join"),
        ("videoedit|manual_rotate_flip", "videoedit|workspace"),
        ("videoedit|rotation", "videoedit|transform"),
        ("videoedit|manual_audio", "videoedit|workspace"),
        ("videoedit|audio_custom", "videoedit|audio"),
        ("videoedit|manual_effects", "videoedit|workspace"),
    ],
)
def test_videoedit_back_returns_to_immediate_parent(open_callback: str, expected_back: str) -> None:
    user_id = 88200 + sum(ord(char) for char in open_callback)
    _ready_state(user_id)
    try:
        query = _press(user_id, open_callback)
        assert expected_back in _callbacks(_last_markup(query))
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_source_info_returns_to_exact_join_caller() -> None:
    user_id = 88301
    _ready_state(user_id)
    try:
        _press(user_id, "videoedit|manual_join")
        query = _press(user_id, "videoedit|source_info")
        assert "videoedit|join" in _callbacks(_last_markup(query))
    finally:
        bot.clear_video_editor_pending(user_id)

