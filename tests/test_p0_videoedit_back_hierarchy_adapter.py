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


class _StateChangingQuery(_Query):
    def __init__(self, user_id: int, data: str, change_state) -> None:
        super().__init__(user_id, data)
        self._change_state = change_state

    async def edit_message_text(self, text: str, **kwargs):
        self.edits.append((text, kwargs))
        self._change_state()
        return None


def _callbacks(markup) -> list[str]:
    return [
        str(button.callback_data or "")
        for row in markup.inline_keyboard
        for button in row
    ]


def _pairs(markup) -> list[tuple[str, str]]:
    return [
        (str(button.text or ""), str(button.callback_data or ""))
        for row in markup.inline_keyboard
        for button in row
    ]


def _last_markup(query: _Query):
    if query.edits:
        return query.edits[-1][1].get("reply_markup")
    if query.message.replies:
        return query.message.replies[-1][1].get("reply_markup")
    return None


def _single_callback_starting_with(markup, prefix: str) -> str:
    matches = [
        callback
        for callback in _callbacks(markup)
        if callback.startswith(prefix)
    ]
    assert len(matches) == 1
    return matches[0]


def _nested_value(payload: dict, path: tuple[str, ...]):
    current = payload
    for key in path:
        current = current[key]
    return current


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
        "videoedit|logo_entry",
        "videoedit|watermark_entry",
        "videoedit|source_info",
        "videoedit|latest_status",
        "videoedit|review",
        "videoedit|upload|manual",
        "videoedit|manual",
        "menu|main",
    ]


def test_videoedit_workspace_separates_logo_watermark_and_uses_forward_finish_copy() -> None:
    pairs = _pairs(bot.video_local_manual_options_keyboard("vi"))

    assert ("🖼 Logo ảnh", "videoedit|logo_entry") in pairs
    assert ("🏷️ Watermark chữ", "videoedit|watermark_entry") in pairs
    assert ("🎞 Thông tin video", "videoedit|source_info") in pairs
    assert ("📊 Trạng thái chỉnh sửa", "videoedit|latest_status") in pairs
    assert ("✅ Hoàn tất & tiếp tục", "videoedit|review") in pairs
    assert ("📎 Gửi video khác", "videoedit|upload|manual") in pairs
    assert ("📋 Xem lại", "videoedit|review") not in pairs
    assert pairs.index(("🖼 Logo ảnh", "videoedit|logo_entry")) < pairs.index(
        ("✅ Hoàn tất & tiếp tục", "videoedit|review")
    )
    assert pairs.index(("🏷️ Watermark chữ", "videoedit|watermark_entry")) < pairs.index(
        ("✅ Hoàn tất & tiếp tục", "videoedit|review")
    )


def test_videoedit_workspace_logo_entry_opens_upload_or_existing_options_without_wrong_review_loop() -> None:
    new_user = 88410
    existing_user = 88411
    _ready_state(new_user)
    _ready_state(existing_user)
    bot.update_video_editor_screen(
        existing_user,
        "workspace",
        parent_callback="videoedit|manual",
        logo_source={
            "file_id": "existing-logo",
            "file_name": "logo.png",
            "mime_type": "image/png",
            "file_size": 4096,
        },
        manual_edit_plan={
            "trim": {"start_ms": 0, "end_ms": 5_000},
            "logo_overlay": {
                "position": "top_right",
                "scale": 0.12,
                "opacity": 1.0,
            },
        },
    )
    try:
        upload = _press(new_user, "videoedit|logo_entry")
        upload_state = dict(bot.get_video_editor_pending(new_user) or {})
        assert upload_state["current_screen"] == "logo_input"
        assert upload_state["parent_callback"] == "videoedit|workspace"
        assert "Logo ảnh" in upload.edits[-1][0]
        assert ("⬅️ Quay lại", "videoedit|workspace") in _pairs(
            _last_markup(upload)
        )

        options = _press(existing_user, "videoedit|logo_entry")
        option_state = dict(bot.get_video_editor_pending(existing_user) or {})
        option_pairs = _pairs(_last_markup(options))
        assert option_state["current_screen"] == "logo_options"
        assert option_state["parent_callback"] == "videoedit|workspace"
        assert ("📎 Đổi ảnh", "videoedit|logo") in option_pairs
        assert ("🗑 Xóa logo", "videoedit|logo_remove") in option_pairs
        assert ("✅ Xem lại", "videoedit|review") in option_pairs
        assert ("⬅️ Quay lại", "videoedit|workspace") in option_pairs

        removed = _press(existing_user, "videoedit|logo_remove")
        removed_state = dict(bot.get_video_editor_pending(existing_user) or {})
        assert removed_state["current_screen"] == "workspace"
        assert removed_state.get("logo_source") == {}
        assert removed_state["manual_edit_plan"].get("logo_overlay") == {}
        assert ("🖼 Logo ảnh", "videoedit|logo_entry") in _pairs(
            _last_markup(removed)
        )
    finally:
        bot.clear_video_editor_pending(new_user)
        bot.clear_video_editor_pending(existing_user)


@pytest.mark.parametrize("product", ["logo", "watermark"])
@pytest.mark.parametrize(
    ("visible_parent", "expected_screen"),
    [
        ("videoedit|workspace", "workspace"),
        ("videoedit|overlay", "overlay"),
        ("videoedit|branding", "branding"),
        ("videoedit|review", "review"),
    ],
)
def test_videoedit_branding_options_and_remove_preserve_the_actual_parent(
    product: str,
    visible_parent: str,
    expected_screen: str,
) -> None:
    user_id = 88_450 + (0 if product == "logo" else 10) + len(visible_parent)
    _ready_state(user_id)
    state = dict(bot.get_video_editor_pending(user_id) or {})
    plan = dict(state.get("manual_edit_plan") or {})
    plan["logo_overlay"] = {
        "position": "top_right",
        "scale": 0.12,
        "opacity": 0.75,
    }
    plan["watermark_overlay"] = {
        "content": "TOAN AAS",
        "position": "bottom_right",
        "start_ms": 0,
        "end_ms": 10_000,
        "font_size": 32,
        "outline": 2,
        "opacity": 0.45,
    }
    bot.update_video_editor_pending(
        user_id,
        "review" if expected_screen == "review" else "options",
        current_screen=expected_screen,
        screen_id=expected_screen,
        parent_callback="videoedit|workspace",
        return_to="workspace",
        status="review_ready" if expected_screen == "review" else "source_ready",
        review_revision=2 if expected_screen == "review" else 0,
        state_revision=2 if expected_screen == "review" else 1,
        logo_source={"file_id": "logo-source", "file_name": "logo.png"},
        watermark_config={
            "enabled": True,
            "text": "TOAN AAS",
            "position": "bottom_right",
            "opacity": 0.45,
        },
        manual_edit_plan=plan,
    )
    try:
        opened = _press(user_id, f"videoedit|{product}_entry")
        opened_state = dict(bot.get_video_editor_pending(user_id) or {})
        assert opened_state["parent_callback"] == visible_parent
        assert ("⬅️ Quay lại", visible_parent) in _pairs(_last_markup(opened))

        removed = _press(user_id, f"videoedit|{product}_remove")
        after = dict(bot.get_video_editor_pending(user_id) or {})
        assert after["current_screen"] == expected_screen
        assert f"videoedit|{product}_options" not in _callbacks(_last_markup(removed))
        if product == "logo":
            assert after["logo_source"] == {}
            assert after["manual_edit_plan"].get("logo_overlay") == {}
            assert after["watermark_config"]["enabled"] is True
        else:
            assert after["watermark_config"] == {}
            assert "watermark_overlay" not in after["manual_edit_plan"]
            assert after["logo_source"]["file_id"] == "logo-source"
        if expected_screen == "review":
            assert "Xem lại kế hoạch" in removed.edits[-1][0]
            assert after["step"] == "review"
            assert after["status"] == "review_ready"
            assert after["review_revision"] == after["state_revision"]
            assert after["state_revision"] > 2
            removed_pairs = _pairs(_last_markup(removed))
            assert ("➡️ Tiếp tục xác nhận", "videoedit|confirmation") in removed_pairs
            assert ("⬅️ Quay lại", "videoedit|workspace") in removed_pairs
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_workspace_logo_upload_keeps_workspace_parent_through_option_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = 88412
    _ready_state(user_id)
    monkeypatch.setattr(
        bot,
        "video_editor_aux_source_from_update",
        lambda _update, _kind: {
            "file_id": "workspace-logo",
            "file_name": "brand.webp",
            "mime_type": "image/webp",
            "file_size": 8_192,
        },
    )
    try:
        _press(user_id, "videoedit|logo_entry")
        upload_message = _Message()
        upload_message.message_id = 7_401
        upload = SimpleNamespace(
            effective_user=SimpleNamespace(id=user_id),
            message=upload_message,
            callback_query=None,
        )

        assert asyncio.run(
            bot.handle_video_editor_pending_upload(upload, SimpleNamespace())
        ) is True
        uploaded = dict(bot.get_video_editor_pending(user_id) or {})
        assert uploaded["current_screen"] == "logo_options"
        assert uploaded["parent_callback"] == "videoedit|workspace"
        assert uploaded["return_to"] == "logo_options"
        assert ("⬅️ Quay lại", "videoedit|workspace") in _pairs(
            upload_message.replies[-1][1]["reply_markup"]
        )

        changed = _press(user_id, "videoedit|set|logo_position|bottom_right")
        changed_state = dict(bot.get_video_editor_pending(user_id) or {})
        assert changed_state["current_screen"] == "logo_options"
        assert changed_state["parent_callback"] == "videoedit|workspace"
        assert changed_state["return_to"] == "logo_options"
        assert changed_state["manual_edit_plan"]["logo_overlay"]["position"] == "bottom_right"
        assert ("⬅️ Quay lại", "videoedit|workspace") in _pairs(
            _last_markup(changed)
        )

        _text, resumed_markup, _parse_mode = bot.video_editor_current_render_model(
            changed_state,
            "vi",
        )
        assert ("⬅️ Quay lại", "videoedit|workspace") in _pairs(resumed_markup)
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_logo_options_review_back_returns_to_logo_without_losing_asset() -> None:
    user_id = 88413
    _ready_state(user_id)
    bot.update_video_editor_screen(
        user_id,
        "workspace",
        parent_callback="videoedit|manual",
        logo_source={
            "file_id": "review-logo",
            "file_name": "review-logo.png",
            "mime_type": "image/png",
            "file_size": 4_096,
        },
        manual_edit_plan={
            "logo_overlay": {
                "position": "top_left",
                "scale": 0.12,
                "opacity": 0.75,
            },
        },
    )
    try:
        _press(user_id, "videoedit|logo_entry")
        review = _press(user_id, "videoedit|review")
        assert ("⬅️ Quay lại", "videoedit|logo_options") in _pairs(
            _last_markup(review)
        )

        returned = _press(user_id, "videoedit|logo_options")
        returned_state = dict(bot.get_video_editor_pending(user_id) or {})
        assert returned_state["current_screen"] == "logo_options"
        assert returned_state["logo_source"]["file_id"] == "review-logo"
        assert returned_state["manual_edit_plan"]["logo_overlay"]["opacity"] == 0.75
        assert ("⬅️ Quay lại", "videoedit|review") in _pairs(
            _last_markup(returned)
        )
    finally:
        bot.clear_video_editor_pending(user_id)


@pytest.mark.parametrize(
    ("visible_callback", "expected_screen"),
    [
        ("videoedit|cut", "cut"),
        ("videoedit|join", "join"),
        ("videoedit|frame", "frame"),
        ("videoedit|transform", "transform"),
        ("videoedit|audio", "audio"),
        ("videoedit|color", "color"),
        ("videoedit|overlay", "overlay"),
        ("videoedit|effects", "effects"),
    ],
)
def test_videoedit_every_visible_workspace_group_opens_its_owned_screen(
    visible_callback: str,
    expected_screen: str,
) -> None:
    user_id = 88150 + sum(ord(char) for char in visible_callback)
    _ready_state(user_id)
    try:
        query = _press(user_id, visible_callback)
        current = dict(bot.get_video_editor_pending(user_id) or {})
        assert _last_markup(query) is not None
        assert current["current_screen"] == expected_screen
        assert not query.answers or not query.answers[-1][1].get("show_alert")
    finally:
        bot.clear_video_editor_pending(user_id)


@pytest.mark.parametrize(
    ("open_callback", "expected_back"),
    [
        ("videoedit|manual_cut", "videoedit|workspace"),
        ("videoedit|trim_edges", "videoedit|cut"),
        ("videoedit|split_from_manual", "videoedit|cut"),
        ("videoedit|manual_join", "videoedit|workspace"),
        ("videoedit|concat", "videoedit|join"),
        ("videoedit|manual_rotate_flip", "videoedit|transform"),
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


@pytest.mark.parametrize(
    ("open_callbacks", "expected_back"),
    [
        (("videoedit|cut", "videoedit|trim_edges"), "videoedit|cut"),
        (("videoedit|cut", "videoedit|remove_middle"), "videoedit|cut"),
        (("videoedit|join", "videoedit|concat"), "videoedit|join"),
        (("videoedit|join", "videoedit|reorder"), "videoedit|join"),
        (("videoedit|frame", "videoedit|aspect"), "videoedit|frame"),
        (("videoedit|frame", "videoedit|resolution"), "videoedit|frame"),
        (("videoedit|transform", "videoedit|speed"), "videoedit|transform"),
        (
            ("videoedit|transform", "videoedit|manual_rotate_flip", "videoedit|rotation"),
            "videoedit|transform",
        ),
        (
            ("videoedit|transform", "videoedit|manual_rotate_flip", "videoedit|flip"),
            "videoedit|transform",
        ),
        (
            ("videoedit|audio", "videoedit|audio_master"),
            "videoedit|audio",
        ),
        (
            ("videoedit|audio", "videoedit|audio_master", "videoedit|audio_custom"),
            "videoedit|audio",
        ),
        (
            ("videoedit|audio", "videoedit|audio_component|audio_dialogue"),
            "videoedit|audio",
        ),
        (("videoedit|color", "videoedit|brightness"), "videoedit|color"),
        (
            ("videoedit|color", "videoedit|brightness", "videoedit|brightness_custom"),
            "videoedit|brightness",
        ),
        (("videoedit|color", "videoedit|color_preset"), "videoedit|color"),
        (("videoedit|overlay", "videoedit|text_overlay"), "videoedit|overlay"),
        (("videoedit|overlay", "videoedit|logo"), "videoedit|overlay"),
        (("videoedit|overlay", "videoedit|srt"), "videoedit|overlay"),
        (("videoedit|effects",), "videoedit|workspace"),
    ],
)
def test_videoedit_every_visible_nested_screen_renders_its_exact_back_without_cross_route(
    open_callbacks: tuple[str, ...],
    expected_back: str,
) -> None:
    user_id = 88250 + sum(ord(char) for char in "|".join(open_callbacks))
    _ready_state(user_id)
    try:
        query = None
        for callback in open_callbacks:
            query = _press(user_id, callback)
        assert query is not None
        callbacks = _callbacks(_last_markup(query))
        assert expected_back in callbacks
        assert not any(
            callback.startswith(
                ("vproduct|", "framevideo|", "subdub|", "lvs27a|", "lvs27b|")
            )
            for callback in callbacks
        )
    finally:
        bot.clear_video_editor_pending(user_id)


@pytest.mark.parametrize(
    (
        "open_callbacks",
        "choice_callbacks",
        "plan_path",
        "expected_value",
        "review_fragment",
    ),
    [
        (
            ("videoedit|frame", "videoedit|aspect"),
            ("videoedit|set|aspect|9x16", "videoedit|set|aspect_mode|crop"),
            ("crop_or_fit", "mode"),
            "crop",
            "Tỉ lệ 9:16 · Cắt vừa khung",
        ),
        (
            ("videoedit|frame", "videoedit|resolution"),
            ("videoedit|set|resolution|720p",),
            ("resolution",),
            "720p",
            "Độ phân giải 720p",
        ),
        (
            ("videoedit|transform", "videoedit|manual_rotate_flip", "videoedit|rotation"),
            ("videoedit|set|rotation|90",),
            ("rotation",),
            90,
            "Xoay 90°",
        ),
        (
            ("videoedit|transform", "videoedit|manual_rotate_flip", "videoedit|flip"),
            ("videoedit|set|flip|horizontal",),
            ("flip",),
            "horizontal",
            "Lật ngang",
        ),
        (
            ("videoedit|transform", "videoedit|speed"),
            ("videoedit|set|speed|1.5",),
            ("speed",),
            1.5,
            "Tốc độ 1.5x",
        ),
        (
            ("videoedit|audio", "videoedit|audio_master"),
            ("videoedit|audio_set|60",),
            ("volume",),
            0.6,
            "Âm lượng 60%",
        ),
        (
            ("videoedit|color", "videoedit|brightness"),
            ("videoedit|brightness_set|120",),
            ("brightness_percent",),
            120,
            "Độ sáng 120%",
        ),
        (
            ("videoedit|color", "videoedit|color_preset"),
            ("videoedit|set|color_preset|warm",),
            ("color_preset",),
            "warm",
            "Màu: Tông ấm",
        ),
        (
            ("videoedit|audio",),
            ("videoedit|audio_set|0",),
            ("volume",),
            0.0,
            "Tắt tiếng",
        ),
    ],
)
def test_videoedit_direct_manual_choices_persist_and_are_visible_in_review(
    open_callbacks: tuple[str, ...],
    choice_callbacks: tuple[str, ...],
    plan_path: tuple[str, ...],
    expected_value,
    review_fragment: str,
) -> None:
    user_id = 88450 + sum(ord(char) for char in "|".join(choice_callbacks))
    _ready_state(user_id)
    try:
        for callback in open_callbacks:
            _press(user_id, callback)
        for callback in choice_callbacks:
            _press(user_id, callback)

        state = dict(bot.get_video_editor_pending(user_id) or {})
        plan = dict(state.get("manual_edit_plan") or {})
        assert _nested_value(plan, plan_path) == expected_value
        assert review_fragment in "\n".join(
            video_local_editing.public_plan_summary(
                plan,
                source_duration_ms=10_000,
            )
        )

        review = _press(user_id, "videoedit|review")
        assert review.edits
        assert review_fragment in review.edits[-1][0]
    finally:
        bot.clear_video_editor_pending(user_id)


@pytest.mark.parametrize(
    ("open_callbacks", "expected_back"),
    [
        (("videoedit|color", "videoedit|brightness"), "videoedit|brightness"),
        (
            ("videoedit|transform", "videoedit|manual_rotate_flip", "videoedit|rotation"),
            "videoedit|rotation",
        ),
        (
            ("videoedit|transform", "videoedit|manual_rotate_flip", "videoedit|flip"),
            "videoedit|flip",
        ),
    ],
)
def test_videoedit_source_info_returns_to_exact_brightness_rotate_or_flip_picker(
    open_callbacks: tuple[str, ...],
    expected_back: str,
) -> None:
    user_id = 88320 + sum(ord(char) for char in expected_back)
    _ready_state(user_id)
    try:
        for callback in open_callbacks:
            _press(user_id, callback)
        summary = _press(user_id, "videoedit|source_info")
        assert ("⬅️ Quay lại", expected_back) in _pairs(_last_markup(summary))
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_confirmation_source_info_back_preserves_exact_confirmation() -> None:
    user_id = 88321
    _ready_state(user_id)
    try:
        state = dict(bot.get_video_editor_pending(user_id) or {})
        plan = dict(state.get("manual_edit_plan") or {})
        plan["brightness_percent"] = 120
        bot.update_video_editor_pending(user_id, manual_edit_plan=plan)
        _press(user_id, "videoedit|review")
        confirmation = _press(user_id, "videoedit|confirmation")
        before = dict(bot.get_video_editor_pending(user_id) or {})
        before_token = next(
            callback
            for _label, callback in _pairs(_last_markup(confirmation))
            if callback.startswith("videoedit|confirm_local|")
        )

        source = _press(user_id, "videoedit|source_info")
        assert dict(bot.get_video_editor_pending(user_id) or {}) == before
        assert ("⬅️ Quay lại", "videoedit|confirmation") in _pairs(
            _last_markup(source)
        )

        returned = _press(user_id, "videoedit|confirmation")
        after = dict(bot.get_video_editor_pending(user_id) or {})
        after_token = next(
            callback
            for _label, callback in _pairs(_last_markup(returned))
            if callback.startswith("videoedit|confirm_local|")
        )
        assert after == before
        assert after_token == before_token
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_public_vietnamese_labels_pair_with_their_exact_callbacks() -> None:
    hub = _pairs(bot.video_edit_hub_keyboard("vi"))
    assert ("✨ Chỉnh sửa theo mục tiêu", "videoedit|ai") in hub
    assert ("✂️ Chỉnh sửa thủ công", "videoedit|manual") in hub

    audio = _pairs(
        bot.video_edit_audio_keyboard(
            {
                "source_file_id": "source",
                "source_metadata": {"has_audio": True, "audio_stream_count": 1},
                "manual_edit_plan": video_local_editing.default_manual_edit_plan(""),
            },
            "vi",
        )
    )
    assert ("ℹ️ Kiểm tra âm thanh", "videoedit|audio_component|audio_dialogue") in audio
    assert all(
        callback.startswith("videoedit|audio_component|")
        for label, callback in audio
        if label.startswith("ℹ️")
    )

    overlay = _pairs(bot.video_local_overlay_keyboard("vi"))
    assert ("🖼 Logo ảnh", "videoedit|logo_entry") in overlay
    assert ("🏷️ Watermark chữ", "videoedit|watermark_entry") in overlay


def test_videoedit_audio_component_copy_never_claims_an_unavailable_stem_control() -> None:
    text = bot.video_edit_audio_component_text(
        "audio_dialogue",
        {
            "source_metadata": {
                "has_audio": True,
                "audio_stream_count": 4,
                "separate_audio_stems": True,
                "named_audio_tracks": ["dialogue", "music", "ambience", "sfx"],
            }
        },
    )
    assert "nút thông tin" in text.lower()
    assert "chưa mở điều khiển chỉnh riêng" in text.lower()
    assert "có thể được chỉnh độc lập" not in text.lower()


def test_videoedit_review_back_returns_to_the_saved_cut_parent() -> None:
    user_id = 88302
    _ready_state(user_id)
    try:
        state = dict(bot.get_video_editor_pending(user_id) or {})
        plan = dict(state.get("manual_edit_plan") or {})
        plan["trim"] = {"start_ms": 0, "end_ms": 9_000}
        bot.update_video_editor_pending(user_id, manual_edit_plan=plan)
        _press(user_id, "videoedit|manual_cut")
        query = _press(user_id, "videoedit|review")
        assert "videoedit|cut" in _callbacks(_last_markup(query))
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_brightness_direct_review_back_returns_to_brightness() -> None:
    user_id = 88308
    _ready_state(user_id)
    try:
        _press(user_id, "videoedit|color")
        _press(user_id, "videoedit|brightness")
        review = _press(user_id, "videoedit|brightness_set|120")
        current = dict(bot.get_video_editor_pending(user_id) or {})
        assert current["current_screen"] == "review"
        assert current["return_to"] == "brightness"
        review_pairs = _pairs(_last_markup(review))
        assert ("⬅️ Quay lại", "videoedit|brightness") in review_pairs

        back_callback = next(
            callback
            for label, callback in review_pairs
            if label == "⬅️ Quay lại"
        )
        returned = _press(user_id, back_callback)
        returned_state = dict(bot.get_video_editor_pending(user_id) or {})
        assert (
            "☀️ Tăng lên 120%",
            "videoedit|brightness_set|120",
        ) in _pairs(_last_markup(returned))
        assert returned_state["return_to"] == "color"
    finally:
        bot.clear_video_editor_pending(user_id)


@pytest.mark.parametrize(
    ("open_callback", "expected_return_to", "expected_back"),
    [
        ("videoedit|manual_join", "join", "videoedit|join"),
        ("videoedit|frame", "frame", "videoedit|frame"),
        ("videoedit|transform", "transform", "videoedit|transform"),
        ("videoedit|manual_audio", "audio", "videoedit|audio"),
        ("videoedit|color", "color", "videoedit|color"),
        ("videoedit|overlay", "overlay", "videoedit|overlay"),
        ("videoedit|manual_effects", "effects", "videoedit|effects"),
    ],
)
def test_videoedit_review_back_matrix_uses_the_group_that_opened_review(
    open_callback: str,
    expected_return_to: str,
    expected_back: str,
) -> None:
    user_id = 88400 + sum(ord(char) for char in open_callback)
    _ready_state(user_id)
    try:
        state = dict(bot.get_video_editor_pending(user_id) or {})
        plan = dict(state.get("manual_edit_plan") or {})
        plan["brightness_percent"] = 120
        bot.update_video_editor_pending(user_id, manual_edit_plan=plan)

        _press(user_id, open_callback)
        opened = dict(bot.get_video_editor_pending(user_id) or {})
        assert opened["return_to"] == expected_return_to
        review = _press(user_id, "videoedit|review")
        assert ("⬅️ Quay lại", expected_back) in _pairs(_last_markup(review))
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_split_review_back_preserves_split_state_and_ranges() -> None:
    user_id = 88303
    _ready_state(user_id)
    try:
        _press(user_id, "videoedit|split_from_manual")
        opened = dict(bot.get_video_editor_pending(user_id) or {})
        assert opened["return_to"] == "split"
        assert opened["manual_edit_plan"] == video_local_editing.neutral_split_manual_plan()
        ranges = [
            {"index": 1, "start_ms": 0, "end_ms": 4_000},
            {"index": 2, "start_ms": 4_000, "end_ms": 10_000},
        ]
        bot.update_video_editor_pending(
            user_id,
            "split",
            selected_tool="split",
            split_mode="custom",
            split_ranges=ranges,
            coverage_required=True,
        )
        review = _press(user_id, "videoedit|review")
        assert "videoedit|split" in _callbacks(_last_markup(review))
        _press(user_id, "videoedit|split")
        state = dict(bot.get_video_editor_pending(user_id) or {})
        assert state["selected_tool"] == "split"
        assert state["split_ranges"] == ranges
        assert state["return_to"] == "split"
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_legacy_options_split_cannot_bypass_the_explicit_reset() -> None:
    user_id = 88333
    _ready_state(user_id)
    try:
        state = dict(bot.get_video_editor_pending(user_id) or {})
        plan = dict(state.get("manual_edit_plan") or {})
        plan["brightness_percent"] = 130
        bot.update_video_editor_pending(user_id, manual_edit_plan=plan)
        before = dict(bot.get_video_editor_pending(user_id) or {})

        warning = _press(user_id, "videoedit|options|split")
        after = dict(bot.get_video_editor_pending(user_id) or {})

        assert "kế hoạch chia riêng" in warning.edits[-1][0].lower()
        assert after == before
        reset_callback = _single_callback_starting_with(
            _last_markup(warning),
            "videoedit|split_reset_manual|",
        )
        assert (
            "🧩 Bắt đầu kế hoạch chia riêng",
            reset_callback,
        ) in _pairs(_last_markup(warning))
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_stale_legacy_menu_cannot_escape_an_active_split_plan() -> None:
    user_id = 88334
    _ready_state(user_id)
    try:
        _press(user_id, "videoedit|split_from_manual")
        ranges = [
            {"index": 1, "start_ms": 0, "end_ms": 5_000},
            {"index": 2, "start_ms": 5_000, "end_ms": 10_000},
        ]
        bot.update_video_editor_pending(
            user_id,
            "split",
            current_screen="split",
            selected_tool="split",
            split_mode="custom",
            split_ranges=ranges,
        )
        before = dict(bot.get_video_editor_pending(user_id) or {})

        stale = _press(user_id, "videoedit|menu")

        assert stale.answers[-1][1].get("show_alert") is True
        assert dict(bot.get_video_editor_pending(user_id) or {}) == before
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_split_reupload_preserves_split_ownership_and_neutral_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = 88335
    _ready_state(user_id)
    metadata = {
        "ok": True,
        "duration": 10.137,
        "duration_ms": 10_137,
        "width": 1_280,
        "height": 720,
        "fps": 30.0,
        "has_video": True,
        "has_audio": True,
        "audio_stream_count": 1,
        "format_name": "mp4",
        "bytes": 4_096,
        "source_sha256": "a" * 64,
    }

    async def fake_inspect(_context, _source):
        return dict(metadata)

    monkeypatch.setattr(
        bot,
        "video_editor_source_from_update",
        lambda _update: {
            "source_file_id": "replacement-video",
            "source_file_name": "replacement.mp4",
            "source_file_size": 4_096,
            "source_mime_type": "video/mp4",
        },
    )
    monkeypatch.setattr(bot, "inspect_video_editor_source", fake_inspect)
    monkeypatch.setattr(bot, "cache_recent_media_state", lambda _update: None)
    try:
        _press(user_id, "videoedit|split_from_manual")
        _press(user_id, "videoedit|upload|split")
        intake = dict(bot.get_video_editor_pending(user_id) or {})
        assert intake["edit_mode"] == "manual_edit"
        assert intake["selected_tool"] == "split"
        assert intake["entry_context"] == "split"
        assert intake["manual_edit_plan"] == video_local_editing.neutral_split_manual_plan()

        upload_message = _Message()
        upload_message.message_id = 7_101
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=user_id),
            message=upload_message,
            callback_query=None,
        )
        assert asyncio.run(
            bot.handle_video_editor_pending_upload(update, SimpleNamespace())
        ) is True

        current = dict(bot.get_video_editor_pending(user_id) or {})
        assert current["source_file_id"] == "replacement-video"
        assert current["selected_tool"] == "split"
        assert current["current_screen"] == "split"
        assert current["manual_edit_plan"] == video_local_editing.neutral_split_manual_plan()
        assert current["split_ranges"] == []
        assert "videoedit|split_fixed" in _callbacks(
            upload_message.replies[-1][1]["reply_markup"]
        )
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_visible_split_back_exits_cleanly_without_mixing_manual_state() -> None:
    user_id = 88331
    _ready_state(user_id)
    try:
        ranges = [
            {"index": 1, "start_ms": 0, "end_ms": 5_000},
            {"index": 2, "start_ms": 5_000, "end_ms": 10_000},
        ]
        bot.update_video_editor_pending(
            user_id,
            "split",
            current_screen="split",
            parent_callback="videoedit|cut",
            selected_tool="split",
            split_mode="custom_ranges",
            split_ranges=ranges,
            split_part_count=2,
            coverage_required=True,
        )

        query = _press(user_id, "videoedit|manual_cut")
        state = dict(bot.get_video_editor_pending(user_id) or {})

        assert not query.answers or not query.answers[-1][1].get("show_alert")
        assert state["current_screen"] == "cut"
        assert state["selected_tool"] == "manual"
        assert state["split_ranges"] == []
        assert state["split_mode"] == ""
        assert state["split_part_count"] == 0
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_audio_reupload_opens_a_fresh_audio_intake() -> None:
    user_id = 88304
    _ready_state(user_id)
    try:
        state = dict(bot.get_video_editor_pending(user_id) or {})
        metadata = dict(state.get("source_metadata") or {})
        metadata.update({"has_audio": False, "audio_stream_count": 0})
        stale_plan = dict(state.get("manual_edit_plan") or {})
        stale_plan["brightness_percent"] = 135
        bot.update_video_editor_pending(
            user_id,
            source_metadata=metadata,
            manual_edit_plan=stale_plan,
            concat_sources=[{"file_id": "old-concat"}],
            logo_source={"file_id": "old-logo"},
            subtitle_source={"file_id": "old-srt"},
            split_ranges=[{"index": 1, "start_ms": 0, "end_ms": 10_000}],
            state_revision=9,
        )
        _press(user_id, "videoedit|manual_audio")
        query = _press(user_id, "videoedit|audio_upload")
        current = dict(bot.get_video_editor_pending(user_id) or {})
        assert "Gửi video" in query.edits[-1][0]
        assert current["awaiting_media"] is True
        assert current["source_file_id"] is None
        assert current["requested_group"] == "audio"
        assert current["current_screen"] == "manual_edit_upload"
        assert current["return_to"] == "videoedit|hub"
        assert current["state_revision"] == 1
        assert not current.get("manual_edit_plan")
        assert not current.get("concat_sources")
        assert not current.get("logo_source")
        assert not current.get("subtitle_source")
        assert not current.get("split_ranges")
        assert ("⬅️ Quay lại", "videoedit|hub") in _pairs(_last_markup(query))
        fresh_snapshot = dict(current)
        stale = _press(user_id, "videoedit|audio_upload")
        assert stale.answers[-1][1].get("show_alert") is True
        assert dict(bot.get_video_editor_pending(user_id) or {}) == fresh_snapshot
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_manual_to_split_requires_an_explicit_destructive_reset() -> None:
    user_id = 88305
    _ready_state(user_id)
    try:
        state = dict(bot.get_video_editor_pending(user_id) or {})
        plan = dict(state.get("manual_edit_plan") or {})
        plan["brightness_percent"] = 130
        plan["audio_tracks"] = [
            {
                "path": "",
                "kind": "music",
                "volume": 0.35,
                "start_ms": 0,
                "end_ms": 0,
            }
        ]
        bot.update_video_editor_pending(
            user_id,
            manual_edit_plan=plan,
            concat_sources=[{"file_id": "concat"}],
            logo_source={"file_id": "logo"},
            subtitle_source={"file_id": "srt"},
            audio_sources=[
                {
                    "file_id": "music",
                    "kind": "music",
                    "volume": 0.35,
                    "start_ms": 0,
                    "end_ms": 0,
                }
            ],
            watermark_config={
                "enabled": True,
                "text": "TOAN AAS",
                "position": "bottom_right",
                "opacity": 0.45,
            },
        )
        before_warning = dict(bot.get_video_editor_pending(user_id) or {})

        warning = _press(user_id, "videoedit|split_from_manual")
        warned_state = dict(bot.get_video_editor_pending(user_id) or {})
        assert "kế hoạch chia riêng" in warning.edits[-1][0].lower()
        reset_callback = _single_callback_starting_with(
            _last_markup(warning),
            "videoedit|split_reset_manual|",
        )
        assert (
            "🧩 Bắt đầu kế hoạch chia riêng",
            reset_callback,
        ) in _pairs(_last_markup(warning))
        for key in (
            "manual_edit_plan",
            "concat_sources",
            "logo_source",
            "subtitle_source",
            "audio_sources",
            "source_file_id",
            "source_metadata",
            "edit_session_id",
            "state_revision",
        ):
            assert warned_state[key] == before_warning[key]
        assert warned_state["selected_tool"] == "manual"

        _press(user_id, reset_callback)
        reset_state = dict(bot.get_video_editor_pending(user_id) or {})
        assert reset_state["selected_tool"] == "split"
        assert reset_state["return_to"] == "split"
        assert reset_state["current_screen"] == "split"
        assert reset_state["parent_callback"] == "videoedit|cut"
        assert reset_state["source_file_id"] == before_warning["source_file_id"]
        assert reset_state["source_metadata"] == before_warning["source_metadata"]
        assert reset_state["edit_session_id"] == before_warning["edit_session_id"]
        assert video_local_editing.plan_has_effective_operation(
            reset_state["manual_edit_plan"], source_duration_ms=10_000
        ) is False
        assert reset_state["manual_edit_plan"]["trim"] == {
            "start_ms": 0,
            "end_ms": 0,
        }
        assert reset_state["concat_sources"] == []
        assert reset_state["logo_source"] == {}
        assert reset_state["subtitle_source"] == {}
        assert reset_state["audio_sources"] == []
        assert reset_state["watermark_config"] == {}
        assert "watermark_overlay" not in bot.video_editor_plan_with_watermark(
            reset_state
        )
        assert reset_state["split_ranges"] == []
        assert not reset_state.get("pending_field")
        reset_snapshot = dict(reset_state)
        duplicate = _press(user_id, reset_callback)
        assert duplicate.answers[-1][1].get("show_alert") is True
        assert dict(bot.get_video_editor_pending(user_id) or {}) == reset_snapshot
    finally:
        bot.clear_video_editor_pending(user_id)


@pytest.mark.parametrize("replacement", ["deleted", "new_session"])
def test_videoedit_split_reset_never_resurrects_or_overwrites_changed_state(
    replacement: str,
) -> None:
    user_id = 88308
    _ready_state(user_id)
    try:
        original = dict(bot.get_video_editor_pending(user_id) or {})
        plan = dict(original.get("manual_edit_plan") or {})
        plan["brightness_percent"] = 130
        bot.update_video_editor_pending(user_id, manual_edit_plan=plan)
        warning = _press(user_id, "videoedit|split_from_manual")
        reset_callback = _single_callback_starting_with(
            _last_markup(warning),
            "videoedit|split_reset_manual|",
        )

        def change_state() -> None:
            bot.clear_video_editor_pending(user_id)
            if replacement == "new_session":
                bot.start_video_edit_lane_state(
                    user_id,
                    "manual_edit",
                    edit_session_id="replacement-session",
                )

        query = _StateChangingQuery(
            user_id,
            reset_callback,
            change_state,
        )
        asyncio.run(
            bot.handle_video_editor_callback(
                SimpleNamespace(callback_query=query),
                SimpleNamespace(),
            )
        )

        current = dict(bot.get_video_editor_pending(user_id) or {})
        if replacement == "deleted":
            assert current == {}
            assert query.edits[-1][0] == bot.video_edit_hub_text("vi")
        else:
            assert current["edit_session_id"] == "replacement-session"
            assert current["selected_tool"] == "manual"
            assert current["current_screen"] == "manual_edit_upload"
            assert current["awaiting_media"] is True
            assert current["source_file_id"] is None
            assert query.edits[-1][0] == bot.video_edit_lane_upload_text(
                "manual_edit", "vi"
            )
        assert query.answers[-1][1].get("show_alert") is True
    finally:
        bot.clear_video_editor_pending(user_id)


@pytest.mark.parametrize(
    "callback",
    [
        "videoedit|hub",
        "videoedit|quality_upload",
        "videoedit|ai_upload",
        "videoedit|upload|manual",
        "videoedit|audio_reupload",
    ],
)
def test_videoedit_post_render_lane_transition_preserves_concurrent_winner(
    callback: str,
) -> None:
    user_id = 88_910 + len(callback)
    _ready_state(user_id)
    if callback.endswith("audio_reupload"):
        bot.update_video_editor_screen(
            user_id,
            "audio",
            parent_callback="videoedit|workspace",
            state_step="audio",
        )

    def install_winner() -> None:
        bot.start_video_edit_lane_state(
            user_id,
            "manual_edit",
            edit_session_id=f"winner-{user_id}",
        )

    query = _StateChangingQuery(user_id, callback, install_winner)
    try:
        asyncio.run(
            bot.handle_video_editor_callback(
                SimpleNamespace(callback_query=query),
                SimpleNamespace(user_data={}),
            )
        )
        current = dict(bot.get_video_editor_pending(user_id) or {})
        assert current["edit_session_id"] == f"winner-{user_id}"
    finally:
        bot.clear_video_editor_pending(user_id)


@pytest.mark.parametrize("action", ["review", "confirmation"])
def test_videoedit_post_render_commit_uses_full_state_cas_and_rerenders_current_state(
    action: str,
) -> None:
    user_id = 88330 + len(action)
    _ready_state(user_id)
    try:
        state = dict(bot.get_video_editor_pending(user_id) or {})
        plan = dict(state.get("manual_edit_plan") or {})
        plan["brightness_percent"] = 120
        bot.update_video_editor_pending(user_id, manual_edit_plan=plan)
        if action == "confirmation":
            _press(user_id, "videoedit|review")

        replacement: dict = {}

        def change_state() -> None:
            _ready_state(user_id)
            replacement_plan = dict(
                (bot.get_video_editor_pending(user_id) or {}).get("manual_edit_plan")
                or {}
            )
            replacement_plan["color_preset"] = "warm"
            replacement.update(
                bot.update_video_editor_pending(
                    user_id,
                    "options",
                    current_screen="workspace",
                    edit_session_id="replacement-session",
                    session_id="replacement-session",
                    state_revision=77,
                    revision=81,
                    manual_edit_plan=replacement_plan,
                )
            )

        query = _StateChangingQuery(
            user_id,
            f"videoedit|{action}",
            change_state,
        )
        asyncio.run(
            bot.handle_video_editor_callback(
                SimpleNamespace(callback_query=query),
                SimpleNamespace(),
            )
        )

        assert dict(bot.get_video_editor_pending(user_id) or {}) == replacement
        assert query.edits[-1][0] == bot.video_local_manual_options_text(
            replacement, "vi"
        )
        assert query.answers[-1][1].get("show_alert") is True
    finally:
        bot.clear_video_editor_pending(user_id)


@pytest.mark.parametrize(
    ("state_patch", "expected_callback"),
    [
        ({"current_screen": "frame"}, "videoedit|aspect"),
        ({"current_screen": "transform"}, "videoedit|speed"),
        ({"current_screen": "color"}, "videoedit|brightness"),
        ({"current_screen": "overlay"}, "videoedit|text_overlay"),
        ({"current_screen": "cut"}, "videoedit|trim_edges"),
        ({"current_screen": "join"}, "videoedit|concat"),
        ({"current_screen": "audio"}, "videoedit|audio_component|audio_dialogue"),
        (
            {"current_screen": "ai_edit", "edit_mode": "ai_edit"},
            "videoedit|ai_intent",
        ),
        (
            {
                "current_screen": "quality_enhance",
                "edit_mode": "quality_enhance",
            },
            "videoedit|restore_limits",
        ),
        (
            {
                "current_screen": "trim_input",
                "step": "await_trim_edges",
                "pending_field": "trim_edges",
            },
            "videoedit|trim_edges",
        ),
    ],
)
def test_videoedit_stale_renderer_uses_the_exact_winning_screen(
    state_patch: dict,
    expected_callback: str,
) -> None:
    user_id = 88345 + sum(ord(char) for char in expected_callback)
    _ready_state(user_id)
    try:
        state = dict(bot.get_video_editor_pending(user_id) or {})
        state.update(state_patch)
        _text, markup, _parse_mode = bot.video_editor_current_render_model(
            state, "vi"
        )
        assert expected_callback in _callbacks(markup)
    finally:
        bot.clear_video_editor_pending(user_id)


@pytest.mark.parametrize(
    "callback",
    [
        "videoedit|frame",
        "videoedit|aspect",
        "videoedit|resolution",
        "videoedit|rotation",
        "videoedit|flip",
        "videoedit|speed",
        "videoedit|volume",
        "videoedit|color_preset",
        "videoedit|set|speed|2",
        "videoedit|brightness_set|120",
        "videoedit|options|manual",
        "videoedit|manual_done",
        "videoedit|trim_edges",
        "videoedit|trim_range",
        "videoedit|remove_middle",
    ],
)
def test_videoedit_stale_manual_callbacks_cannot_mutate_split_owned_state(
    callback: str,
) -> None:
    user_id = 88350 + sum(ord(char) for char in callback)
    _ready_state(user_id)
    try:
        ranges = [
            {"index": 1, "start_ms": 0, "end_ms": 5_000},
            {"index": 2, "start_ms": 5_000, "end_ms": 10_000},
        ]
        before = bot.update_video_editor_pending(
            user_id,
            "split",
            current_screen="split",
            parent_callback="videoedit|cut",
            selected_tool="split",
            split_mode="custom_ranges",
            split_ranges=ranges,
            manual_edit_plan={},
        )

        query = _press(user_id, callback)

        assert dict(bot.get_video_editor_pending(user_id) or {}) == before
        assert query.answers[-1][1].get("show_alert") is True
        assert "đã cũ" in str(query.answers[-1][0][0]).lower()
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_public_review_copy_is_fully_vietnamese_and_callbacks_stay_stable() -> None:
    tail = {
        "video_product_type": bot.video_editengine1.PRODUCT_TYPE,
        "content_source": "manual",
        "scene_count": 1,
        "estimated_duration": 5,
        "ratio": "16:9",
        "audio_status": "skipped",
    }
    text = bot.video_tail9_video_edit_review_text(
        tail,
        {
            "source_duration": 5,
            "source_metadata": {"duration": 5, "has_audio": True},
            "manual_edit_plan": {"brightness_percent": 120},
        },
    )
    review_pairs = _pairs(bot.video_tail9_video_edit_review_keyboard())
    summary_text = bot.video_tail9_summary_text(tail)
    summary_pairs = _pairs(bot.video_tail9_summary_keyboard(tail))
    recovery_text = bot.video_idea_prompt_owner_recovery_text({})
    recovery_pairs = _pairs(bot.video_idea_prompt_owner_recovery_keyboard())
    public_copy = "\n".join(
        [
            text,
            summary_text,
            recovery_text,
            *(
                label
                for label, _callback in review_pairs + summary_pairs + recovery_pairs
            ),
        ]
    )

    for forbidden in (
        "Review chỉnh sửa video",
        "Quay lại Review",
        "Logo/Watermark",
        "Âm thanh & Add-on",
        "Âm thanh/Add-on",
        "Engine",
        "Prompt video",
        "owner",
    ):
        assert forbidden not in public_copy
    assert ("🖼 Logo ảnh", "videoedit|logo_entry") in review_pairs
    assert ("🏷️ Watermark chữ", "videoedit|watermark_entry") in review_pairs
    assert ("➡️ Âm thanh và bổ sung", "videoedit|audio") in review_pairs
    assert ("🖼 Logo ảnh", "videoedit|logo_entry") in summary_pairs
    assert ("🏷️ Watermark chữ", "videoedit|watermark_entry") in summary_pairs
    assert ("⬅️ Quay lại", "video_tail|review|open") in recovery_pairs


def test_videoedit_logo_upload_and_source_info_return_to_existing_logo_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = 88306
    _ready_state(user_id)
    try:
        _press(user_id, "videoedit|overlay")
        _press(user_id, "videoedit|logo")
        monkeypatch.setattr(
            bot,
            "video_editor_aux_source_from_update",
            lambda _update, _kind: {
                "file_id": "logo-image",
                "file_name": "logo.png",
                "mime_type": "image/png",
                "file_size": 4_096,
            },
        )
        upload_message = _Message()
        upload_message.message_id = 7_001
        upload = SimpleNamespace(
            effective_user=SimpleNamespace(id=user_id),
            message=upload_message,
            callback_query=None,
        )
        assert asyncio.run(
            bot.handle_video_editor_pending_upload(upload, SimpleNamespace())
        ) is True
        uploaded = dict(bot.get_video_editor_pending(user_id) or {})
        assert uploaded["current_screen"] == "logo_options"
        assert uploaded["parent_callback"] == "videoedit|overlay"
        assert not uploaded.get("pending_field")
        assert uploaded["logo_source"]["file_id"] == "logo-image"

        summary = _press(user_id, "videoedit|source_summary")
        assert ("⬅️ Quay lại", "videoedit|logo_options") in _pairs(
            _last_markup(summary)
        )
        options = _press(user_id, "videoedit|logo_options")
        option_callbacks = _callbacks(_last_markup(options))
        assert "videoedit|set|logo_position|top_left" in option_callbacks
        assert "videoedit|set|logo_opacity|0.75" in option_callbacks
        assert not any("logo_scale" in callback for callback in option_callbacks)
        _press(user_id, "videoedit|set|logo_position|bottom_left")
        _press(user_id, "videoedit|set|logo_opacity|0.75")
        changed = dict(bot.get_video_editor_pending(user_id) or {})
        assert changed["current_screen"] == "logo_options"
        assert changed["manual_edit_plan"]["logo_overlay"]["position"] == "bottom_left"
        assert changed["manual_edit_plan"]["logo_overlay"]["opacity"] == 0.75

        review = _press(user_id, "videoedit|review")
        review_text = review.edits[-1][0]
        assert "Logo ảnh" in review_text
        assert "Logo / watermark" not in review_text
        assert "Dưới trái" in review_text
        assert "75%" in review_text
        _press(user_id, "videoedit|overlay")
        stale = _press(user_id, "videoedit|set|logo_position|top_right")
        assert stale.answers[-1][1].get("show_alert") is True
        final_state = dict(bot.get_video_editor_pending(user_id) or {})
        assert final_state["manual_edit_plan"]["logo_overlay"]["position"] == "bottom_left"
        assert final_state["manual_edit_plan"]["logo_overlay"]["opacity"] == 0.75
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_concat_upload_is_immediately_bound_to_the_manual_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = 88336
    _ready_state(user_id)

    async def fake_inspect(_context, _source):
        return {
            "ok": True,
            "duration": 5.0,
            "duration_ms": 5_000,
            "width": 640,
            "height": 360,
            "fps": 30.0,
            "has_video": True,
            "has_audio": True,
            "audio_stream_count": 1,
            "format_name": "mp4",
            "bytes": 4_096,
            "source_sha256": "b" * 64,
        }

    monkeypatch.setattr(
        bot,
        "video_editor_source_from_update",
        lambda _update: {
            "source_file_id": "concat-video",
            "source_file_name": "concat.mp4",
            "source_file_size": 4_096,
            "source_mime_type": "video/mp4",
        },
    )
    monkeypatch.setattr(bot, "inspect_video_editor_source", fake_inspect)
    monkeypatch.setattr(bot, "cache_recent_media_state", lambda _update: None)
    try:
        _press(user_id, "videoedit|manual_join")
        _press(user_id, "videoedit|concat")
        upload_message = _Message()
        upload_message.message_id = 7_201
        upload = SimpleNamespace(
            effective_user=SimpleNamespace(id=user_id),
            message=upload_message,
            callback_query=None,
        )

        assert asyncio.run(
            bot.handle_video_editor_pending_upload(upload, SimpleNamespace())
        ) is True
        uploaded = dict(bot.get_video_editor_pending(user_id) or {})
        assert [item["file_id"] for item in uploaded["concat_sources"]] == [
            "concat-video"
        ]
        assert uploaded["manual_edit_plan"]["concat_inputs"] == ["video_1"]

        _press(user_id, "videoedit|manual_join")
        review = _press(user_id, "videoedit|review")
        reviewed = dict(bot.get_video_editor_pending(user_id) or {})
        assert reviewed["current_screen"] == "review"
        assert "Ghép 2 video" in review.edits[-1][0]
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_confirmation_uses_nested_concat_metadata_and_split_audio_truth() -> None:
    manual = video_local_editing.default_manual_edit_plan("")
    manual["trim"] = {"start_ms": 0, "end_ms": 10_000}
    text = bot.video_local_confirmation_text(
        {
            "selected_tool": "manual",
            "source_file_name": "source.mp4",
            "source_duration_ms": 10_000,
            "source_metadata": {"duration_ms": 10_000, "has_audio": True},
            "manual_edit_plan": manual,
            "concat_sources": [{"metadata": {"duration_ms": 5_000}}],
        },
        "vi",
        stage="review",
    )
    assert "0:15" in text

    manual["volume"] = 0.0
    manual["audio_normalization"] = "loudnorm"
    split = bot.video_local_confirmation_text(
        {
            "selected_tool": "split",
            "source_file_name": "source.mp4",
            "source_metadata": {"duration_ms": 10_000, "has_audio": True},
            "manual_edit_plan": manual,
            "split_ranges": [
                {"index": 1, "start_ms": 0, "end_ms": 5_000},
                {"index": 2, "start_ms": 5_000, "end_ms": 10_000},
            ],
        },
        "vi",
        stage="review",
    )
    assert "Giữ âm thanh nguồn trong từng phần" in split
    assert "Tắt tiếng đầu ra" not in split


def test_videoedit_mute_clears_loudnorm_and_loudnorm_is_blocked_while_muted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = 88307
    _ready_state(user_id)
    monkeypatch.setattr(
        bot,
        "video_edit_runtime_capability_admission",
        lambda *_args, **_kwargs: {"ready": True, "reason": "ok"},
    )
    try:
        state = dict(bot.get_video_editor_pending(user_id) or {})
        plan = dict(state.get("manual_edit_plan") or {})
        plan["audio_normalization"] = "loudnorm"
        bot.update_video_editor_pending(user_id, manual_edit_plan=plan)

        _press(user_id, "videoedit|audio_set|0")
        muted = dict(bot.get_video_editor_pending(user_id) or {})
        assert muted["manual_edit_plan"]["volume"] == 0.0
        assert muted["manual_edit_plan"]["audio_normalization"] == "off"

        blocked = _press(user_id, "videoedit|audio_loudnorm")
        after = dict(bot.get_video_editor_pending(user_id) or {})
        assert blocked.answers[-1][1].get("show_alert") is True
        assert "tắt tiếng" in str(blocked.answers[-1][0][0]).lower()
        assert after["manual_edit_plan"]["audio_normalization"] == "off"
    finally:
        bot.clear_video_editor_pending(user_id)


@pytest.mark.parametrize(
    ("state", "expected_upload_callback"),
    [
        ({}, "videoedit|upload|manual"),
        ({"edit_mode": "manual_edit"}, "videoedit|upload|manual"),
        ({"edit_mode": "ai_edit"}, "videoedit|ai_upload"),
        ({"edit_mode": "quality_enhance"}, "videoedit|quality_upload"),
    ],
)
def test_videoedit_send_another_preserves_manual_ai_quality_lane(
    state: dict,
    expected_upload_callback: str,
) -> None:
    pairs = _pairs(bot.video_local_manual_options_keyboard("vi", state))

    assert ("📎 Gửi video khác", expected_upload_callback) in pairs


@pytest.mark.parametrize(
    ("logo_parent", "expected_back"),
    [
        ("videoedit|workspace", "videoedit|workspace"),
        ("videoedit|overlay", "videoedit|overlay"),
    ],
)
def test_videoedit_direct_and_nested_logo_failure_keep_exact_parent(
    logo_parent: str,
    expected_back: str,
) -> None:
    user_id = 88_500 + len(logo_parent)
    plan = video_local_editing.default_manual_edit_plan("")
    plan["brightness_percent"] = 125
    message = _Message()
    message.message_id = 8_500
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        message=message,
    )
    bot.clear_video_editor_pending(user_id)
    try:
        before = bot.set_video_editor_pending(
            user_id,
            "await_logo",
            current_screen="logo_input",
            parent_callback=logo_parent,
            logo_parent_callback=logo_parent,
            pending_field="logo",
            source_file_id="video-source",
            manual_edit_plan=plan,
            edit_session_id="logo-recovery-session",
        )

        assert asyncio.run(
            bot.recover_product_video_media_failure(
                update,
                SimpleNamespace(),
                handler_name="handle_video_editor_pending_upload",
            )
        ) is True
        recovered = dict(bot.get_video_editor_pending(user_id) or {})
        assert recovered["parent_callback"] == logo_parent
        assert recovered["logo_parent_callback"] == logo_parent
        assert recovered["manual_edit_plan"] == before["manual_edit_plan"]
        assert expected_back in _callbacks(message.replies[-1][1]["reply_markup"])

        assert asyncio.run(
            bot.recover_product_video_media_failure(
                update,
                SimpleNamespace(),
                handler_name="handle_video_editor_pending_upload",
            )
        ) is True
        assert len(message.replies) == 1
        assert dict(bot.get_video_editor_pending(user_id) or {}) == recovered
    finally:
        bot.clear_video_editor_pending(user_id)


@pytest.mark.parametrize(
    ("logo_parent", "expected_screen"),
    [
        ("videoedit|workspace", "workspace"),
        ("videoedit|overlay", "overlay"),
    ],
)
def test_videoedit_logo_remove_is_screen_owned_and_preserves_non_logo_plan(
    logo_parent: str,
    expected_screen: str,
) -> None:
    user_id = 88_600 + len(logo_parent)
    plan = video_local_editing.default_manual_edit_plan("")
    plan.update(
        {
            "brightness_percent": 125,
            "text_overlay": {"content": "keep this"},
            "logo_overlay": {"position": "bottom_left", "opacity": 0.75},
        }
    )
    bot.clear_video_editor_pending(user_id)
    try:
        before = bot.set_video_editor_pending(
            user_id,
            "logo_options",
            current_screen="logo_options",
            parent_callback=logo_parent,
            logo_parent_callback=logo_parent,
            return_to="logo_options",
            source_file_id="video-source",
            source_file_name="source.mp4",
            inspection_complete=True,
            source_duration_ms=10_000,
            source_metadata={"duration_ms": 10_000},
            edit_session_id="keep-session",
            session_id="keep-session",
            logo_source={"file_id": "logo-source", "file_name": "logo.png"},
            manual_edit_plan=plan,
        )

        removed = _press(user_id, "videoedit|logo_remove")
        after = dict(bot.get_video_editor_pending(user_id) or {})
        assert after["current_screen"] == expected_screen
        assert after["logo_source"] == {}
        assert after["manual_edit_plan"]["logo_overlay"] == {}
        assert after["manual_edit_plan"]["brightness_percent"] == 125
        assert after["manual_edit_plan"]["text_overlay"] == {"content": "keep this"}
        assert after["source_file_id"] == before["source_file_id"]
        assert after["source_file_name"] == before["source_file_name"]
        assert after["edit_session_id"] == before["edit_session_id"]
        assert not removed.answers or not removed.answers[-1][1].get("show_alert")

        stale_before = dict(after)
        stale = _press(user_id, "videoedit|logo_remove")
        assert dict(bot.get_video_editor_pending(user_id) or {}) == stale_before
        assert stale.answers[-1][1].get("show_alert") is True
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_logo_remove_resets_review_return_target() -> None:
    user_id = 88_700
    plan = video_local_editing.default_manual_edit_plan("")
    plan.update(
        {
            "brightness_percent": 125,
            "logo_overlay": {"position": "top_right", "opacity": 1.0},
        }
    )
    bot.clear_video_editor_pending(user_id)
    try:
        bot.set_video_editor_pending(
            user_id,
            "logo_options",
            current_screen="logo_options",
            parent_callback="videoedit|workspace",
            logo_parent_callback="videoedit|workspace",
            return_to="logo_options",
            source_file_id="video-source",
            inspection_complete=True,
            source_duration_ms=10_000,
            source_metadata={"duration_ms": 10_000},
            logo_source={"file_id": "logo-source"},
            manual_edit_plan=plan,
        )

        _press(user_id, "videoedit|logo_remove")
        removed = dict(bot.get_video_editor_pending(user_id) or {})
        assert removed["return_to"] == "workspace"
        review = _press(user_id, "videoedit|review")
        reviewed = dict(bot.get_video_editor_pending(user_id) or {})
        assert reviewed["return_to"] == "workspace"
        assert "videoedit|workspace" in _callbacks(_last_markup(review))
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_logo_parent_marker_survives_state_serialization() -> None:
    user_id = 88_800
    bot.clear_video_editor_pending(user_id)
    try:
        saved = bot.set_video_editor_pending(
            user_id,
            "await_logo",
            logo_parent_callback="videoedit|workspace",
        )
        updated = bot.update_video_editor_pending(
            user_id,
            logo_parent_callback="videoedit|overlay",
        )

        assert saved["logo_parent_callback"] == "videoedit|workspace"
        assert updated["logo_parent_callback"] == "videoedit|overlay"
        assert bot.get_video_editor_pending(user_id)["logo_parent_callback"] == "videoedit|overlay"
    finally:
        bot.clear_video_editor_pending(user_id)


def test_videoedit_overlay_logo_entry_ignores_a_stale_workspace_logo_marker() -> None:
    user_id = 88_801
    _ready_state(user_id)
    try:
        _press(user_id, "videoedit|logo_entry")
        direct = dict(bot.get_video_editor_pending(user_id) or {})
        assert direct["logo_parent_callback"] == "videoedit|workspace"

        _press(user_id, "videoedit|workspace")
        _press(user_id, "videoedit|overlay")
        nested = _press(user_id, "videoedit|logo")
        nested_state = dict(bot.get_video_editor_pending(user_id) or {})

        assert nested_state["current_screen"] == "logo_input"
        assert nested_state["parent_callback"] == "videoedit|overlay"
        assert nested_state["logo_parent_callback"] == "videoedit|overlay"
        assert ("⬅️ Quay lại", "videoedit|overlay") in _pairs(
            _last_markup(nested)
        )
    finally:
        bot.clear_video_editor_pending(user_id)
