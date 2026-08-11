from __future__ import annotations

import importlib
import asyncio
from types import SimpleNamespace

import bot
import pytest


def _rows(markup) -> list[list[tuple[str, str]]]:
    return [
        [(button.text, button.callback_data) for button in row]
        for row in markup.inline_keyboard
    ]


class _Message:
    chat_id = 91_001

    def __init__(self) -> None:
        self.replies: list[tuple[str, dict]] = []

    async def reply_text(self, text: str, **kwargs):
        self.replies.append((text, kwargs))


class _UploadMessage(_Message):
    message_id = 7_701


class _TextMessage(_Message):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class _Query:
    def __init__(self, user_id: int, callback: str) -> None:
        self.id = f"ai-edit-{user_id}-{callback}"
        self.from_user = SimpleNamespace(id=user_id, first_name="AI Edit", username="")
        self.data = callback
        self.message = _Message()
        self.edits: list[tuple[str, dict]] = []
        self.answers: list[tuple[tuple, dict]] = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text: str, **kwargs):
        self.edits.append((text, kwargs))


def _press(user_id: int, callback: str) -> _Query:
    query = _Query(user_id, callback)
    asyncio.run(
        bot.handle_video_editor_callback(
            SimpleNamespace(callback_query=query),
            SimpleNamespace(user_data={}),
        )
    )
    return query


def _press_menu(user_id: int, callback: str = "menu|main") -> _Query:
    query = _Query(user_id, callback)
    asyncio.run(
        bot.handle_menu_callback(
            SimpleNamespace(callback_query=query),
            SimpleNamespace(user_data={}),
        )
    )
    return query


def _last_rows(query: _Query) -> list[list[tuple[str, str]]]:
    payload = query.edits[-1][1] if query.edits else query.message.replies[-1][1]
    return _rows(payload["reply_markup"])


def test_ai_edit_public_entry_buttons_are_exact_and_protected_siblings_do_not_move() -> None:
    assert _rows(bot.video_edit_hub_keyboard("vi")) == [
        [
            ("🤖 Chỉnh sửa video AI", "videoedit|ai"),
            ("✂️ Chỉnh sửa thủ công", "videoedit|manual"),
        ],
        [
            ("🧹 Nâng chất lượng video", "videoedit|restore"),
            ("❓ Hướng dẫn công cụ này", "videoedit|guide"),
        ],
        [
            ("⬅️ Quay lại", "menu|main_video"),
            ("🏠 Menu chính", "menu|main"),
        ],
    ]

    source_rows = _rows(bot.video_ai_edit_source_summary_keyboard("vi", {}))
    assert source_rows == [
        [
            ("🎨 Chọn nội dung cần chỉnh", "videoedit|ai_catalog"),
            ("📎 Gửi video khác", "videoedit|ai_upload"),
        ],
        [
            ("⬅️ Quay lại", "videoedit|ai"),
            ("🏠 Menu chính", "menu|main"),
        ],
    ]


def test_catalog_is_one_39_item_authority_with_compact_pages_and_visible_checkmarks() -> None:
    try:
        catalog = importlib.import_module("services.video_ai_edit_catalog")
    except ModuleNotFoundError:
        pytest.fail("canonical AI Edit catalog is not implemented")

    assert len(catalog.CAPABILITIES) == 39
    assert {
        category.stable_id: len(catalog.capabilities_for_category(category.stable_id))
        for category in catalog.CATEGORIES
    } == {
        "scene": 12,
        "person": 7,
        "object": 8,
        "style": 8,
        "text": 4,
    }
    assert all(
        len(catalog.capability_page(category.stable_id, page_index).items) <= 4
        for category in catalog.CATEGORIES
        for page_index in range(catalog.page_count(category.stable_id))
    )
    assert all(item.enabled_production is False for item in catalog.CAPABILITIES)

    state = {"ai_edit_selected": ["scene_background", "person_outfit_color"]}
    assert _rows(bot.video_ai_edit_catalog_home_keyboard(state, "vi")) == [
        [
            ("🎨 Cảnh & phông nền", "videoedit|ai_cat|scene.0"),
            ("👤 Người / nhân vật", "videoedit|ai_cat|person.0"),
        ],
        [
            ("📦 Vật thể & sản phẩm", "videoedit|ai_cat|object.0"),
            ("✨ Phong cách hình ảnh", "videoedit|ai_cat|style.0"),
        ],
        [("📝 Chữ & yêu cầu khác", "videoedit|ai_cat|text.0")],
        [("✅ Đã chọn (2)", "videoedit|ai_selected")],
        [
            ("⬅️ Quay lại", "videoedit|ai_source"),
            ("🏠 Menu chính", "menu|main"),
        ],
    ]

    scene_rows = _rows(bot.video_ai_edit_category_keyboard(state, "scene", 0, "vi"))
    assert scene_rows[:2] == [
        [
            ("✅ Đổi phông nền", "videoedit|ai_item|scene_background.scene.0"),
            ("⬜ Đổi địa điểm", "videoedit|ai_item|scene_location.scene.0"),
        ],
        [
            ("⬜ Đổi ánh sáng", "videoedit|ai_item|scene_lighting.scene.0"),
            ("⬜ Đổi thời tiết", "videoedit|ai_item|scene_weather.scene.0"),
        ],
    ]
    assert all(len(row) <= 2 for row in scene_rows)
    assert ("➡️ Trang sau", "videoedit|ai_cat|scene.1") in scene_rows[2]
    assert scene_rows[-1] == [
        ("⬅️ Quay lại", "videoedit|ai_catalog"),
        ("🏠 Menu chính", "menu|main"),
    ]
    assert "Nhập chữ cũ cần thay" in bot.video_ai_edit_detail_text({}, "text_replace", "vi")


def test_catalog_callbacks_toggle_exact_items_persist_across_categories_and_back_exactly() -> None:
    try:
        ai_state = importlib.import_module("services.video_ai_edit_state")
    except ModuleNotFoundError:
        pytest.fail("dedicated AI Edit draft state is not implemented")

    user_id = 91_001
    bot.clear_video_editor_pending(user_id)
    ai_state.clear_draft(user_id)
    try:
        ai_state.replace_source_draft(
            user_id=user_id,
            chat_id=91_001,
            draft_id="ai-edit-session",
            source={
                "file_id": "owned-video",
                "file_unique_id": "owned-video-unique",
                "file_name": "owned.mp4",
                "file_size": 4_096,
                "fingerprint": "a" * 64,
            },
            metadata={
                "ok": True,
                "duration": 12.0,
                "duration_ms": 12_000,
                "width": 1_080,
                "height": 1_920,
                "has_video": True,
            },
        )

        home = _press(user_id, "videoedit|ai_catalog")
        assert "videoedit|ai_source" in [callback for row in _last_rows(home) for _label, callback in row]
        assert ai_state.load_draft(user_id)["current_screen"] == "ai_catalog"

        scene = _press(user_id, "videoedit|ai_cat|scene.0")
        assert _last_rows(scene)[-1][0] == ("⬅️ Quay lại", "videoedit|ai_catalog")

        selected_scene = _press(user_id, "videoedit|ai_item|scene_background.scene.0")
        assert _last_rows(selected_scene)[0][0] == (
            "✅ Đổi phông nền",
            "videoedit|ai_item|scene_background.scene.0",
        )

        person = _press(user_id, "videoedit|ai_cat|person.0")
        assert _last_rows(person)[-1][0] == ("⬅️ Quay lại", "videoedit|ai_catalog")
        _press(user_id, "videoedit|ai_item|person_outfit_color.person.0")

        current = ai_state.load_draft(user_id)
        assert current["ai_edit_selected"] == [
            "scene_background",
            "person_outfit_color",
        ]

        ai_state.update_draft(
            user_id,
            ai_edit_details={
                "scene_background": {"desired_background": "studio"},
                "person_outfit_color": {"desired_color": "black"},
            },
        )
        _press(user_id, "videoedit|ai_cat|scene.0")
        _press(user_id, "videoedit|ai_item|scene_background.scene.0")
        current = ai_state.load_draft(user_id)
        assert current["ai_edit_selected"] == ["person_outfit_color"]
        assert current["ai_edit_details"] == {
            "person_outfit_color": {"desired_color": "black"}
        }

        emitted = [
            callback
            for query in (home, scene, selected_scene, person)
            for row in _last_rows(query)
            for _label, callback in row
            if callback.startswith("videoedit|")
        ]
        assert all(bot.video_editor_callback_arity_valid(callback.split("|")) for callback in emitted)
    finally:
        bot.clear_video_editor_pending(user_id)
        ai_state.clear_draft(user_id)


def test_ai_entry_upload_hands_one_owned_source_to_the_catalog_without_entering_other_lanes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ai_state = importlib.import_module("services.video_ai_edit_state")
    user_id = 91_002
    bot.clear_video_editor_pending(user_id)
    ai_state.clear_draft(user_id)

    source = {
        "source_file_id": "telegram-video",
        "source_file_unique_id": "telegram-video-unique",
        "source_file_name": "source.mp4",
        "source_file_size": 4_096,
        "source_mime_type": "video/mp4",
    }
    metadata = {
        "ok": True,
        "duration": 12.0,
        "duration_ms": 12_000,
        "width": 1_080,
        "height": 1_920,
        "fps": 30.0,
        "has_video": True,
        "has_audio": True,
        "format_name": "mp4",
        "bytes": 4_096,
        "source_sha256": "b" * 64,
    }

    async def inspect_source(*_args, **_kwargs):
        return dict(metadata)

    monkeypatch.setattr(bot, "video_editor_source_from_update", lambda _update: dict(source))
    monkeypatch.setattr(bot, "inspect_video_editor_source", inspect_source)
    monkeypatch.setattr(bot, "cache_recent_media_state", lambda _update: None)

    try:
        entry = _press(user_id, "videoedit|ai")
        assert _last_rows(entry)[-1][0] == ("⬅️ Quay lại", "videoedit|hub")
        pending = dict(bot.get_video_editor_pending(user_id) or {})
        assert pending["step"] == "await_edit_video"
        assert pending["entry_context"] == "ai"

        message = _UploadMessage()
        handled = asyncio.run(
            bot.handle_video_editor_pending_upload(
                SimpleNamespace(
                    effective_user=SimpleNamespace(id=user_id),
                    effective_chat=SimpleNamespace(id=91_001),
                    message=message,
                    callback_query=None,
                ),
                SimpleNamespace(user_data={}),
            )
        )
        assert handled is True
        assert "Sẵn sàng chọn nội dung chỉnh sửa AI" in message.replies[-1][0]
        assert "Gợi ý từ thông tin file" not in message.replies[-1][0]
        assert _rows(message.replies[-1][1]["reply_markup"]) == [
            [
                ("🎨 Chọn nội dung cần chỉnh", "videoedit|ai_catalog"),
                ("📎 Gửi video khác", "videoedit|ai_upload"),
            ],
            [
                ("⬅️ Quay lại", "videoedit|ai"),
                ("🏠 Menu chính", "menu|main"),
            ],
        ]

        draft = ai_state.load_draft(user_id)
        assert draft["user_id"] == str(user_id)
        assert draft["chat_id"] == "91001"
        assert draft["source"]["fingerprint"] == "b" * 64
        assert draft["current_screen"] == "ai_source_summary"
        assert bot.get_video_editor_pending(user_id) == {}

        catalog = _press(user_id, "videoedit|ai_catalog")
        callbacks = [callback for row in _last_rows(catalog) for _label, callback in row]
        assert "videoedit|ai_cat|scene.0" in callbacks
        assert not any(
            callback.startswith(("vproduct|", "vid3|", "subdub|", "framevideo|"))
            for callback in callbacks
        )
    finally:
        bot.clear_video_editor_pending(user_id)
        ai_state.clear_draft(user_id)


def test_selected_details_and_summary_return_to_the_exact_ai_menu_that_opened_them() -> None:
    ai_state = importlib.import_module("services.video_ai_edit_state")
    user_id = 91_003
    ai_state.clear_draft(user_id)
    ai_state.replace_source_draft(
        user_id=user_id,
        chat_id=91_001,
        draft_id="detail-session",
        source={
            "file_id": "owned-video",
            "file_name": "owned.mp4",
            "file_size": 4_096,
            "fingerprint": "c" * 64,
        },
        metadata={
            "ok": True,
            "has_video": True,
            "duration": 8.0,
            "duration_ms": 8_000,
            "width": 720,
            "height": 1_280,
        },
    )
    try:
        _press(user_id, "videoedit|ai_catalog")
        _press(user_id, "videoedit|ai_cat|scene.0")
        scene_toggle = _press(user_id, "videoedit|ai_item|scene_background.scene.0")
        assert scene_toggle.edits, scene_toggle.answers
        assert ai_state.load_draft(user_id)["ai_edit_selected"] == ["scene_background"]
        person_category = _press(user_id, "videoedit|ai_cat|person.0")
        assert person_category.edits, person_category.answers
        person_toggle = _press(user_id, "videoedit|ai_item|person_outfit_color.person.0")
        assert person_toggle.edits, person_toggle.answers
        assert ai_state.load_draft(user_id)["ai_edit_selected"] == [
            "scene_background",
            "person_outfit_color",
        ]

        selected = _press(user_id, "videoedit|ai_selected")
        assert _last_rows(selected) == [
            [
                ("✍️ Đổi phông nền", "videoedit|ai_detail|scene_background"),
                ("✍️ Đổi màu trang phục", "videoedit|ai_detail|person_outfit_color"),
            ],
            [("➡️ Xem lại lựa chọn", "videoedit|ai_summary")],
            [
                ("⬅️ Quay lại", "videoedit|ai_cat|person.0"),
                ("🏠 Menu chính", "menu|main"),
            ],
        ]
        returned_category = _press(user_id, "videoedit|ai_cat|person.0")
        assert _last_rows(returned_category)[0][0] == (
            "⬜ Thay người / nhân vật",
            "videoedit|ai_item|person_replace.person.0",
        )
        selected = _press(user_id, "videoedit|ai_selected")

        detail = _press(user_id, "videoedit|ai_detail|scene_background")
        assert _last_rows(detail)[-1] == [
            ("⬅️ Quay lại", "videoedit|ai_selected"),
            ("🏠 Menu chính", "menu|main"),
        ]
        returned_selected = _press(user_id, "videoedit|ai_selected")
        assert ai_state.load_draft(user_id)["pending_input"] == {}
        assert _last_rows(returned_selected)[-1] == [
            ("⬅️ Quay lại", "videoedit|ai_cat|person.0"),
            ("🏠 Menu chính", "menu|main"),
        ]
        _press(user_id, "videoedit|ai_detail|scene_background")
        first_text = _TextMessage("Studio hiện đại, sáng mềm")
        assert asyncio.run(
            bot.handle_video_ai_edit_pending_text(
                SimpleNamespace(
                    effective_user=SimpleNamespace(id=user_id),
                    effective_chat=SimpleNamespace(id=91_001),
                    message=first_text,
                ),
                SimpleNamespace(user_data={}),
            )
        ) is True

        _press(user_id, "videoedit|ai_detail|person_outfit_color")
        second_text = _TextMessage("Màu đen")
        assert asyncio.run(
            bot.handle_video_ai_edit_pending_text(
                SimpleNamespace(
                    effective_user=SimpleNamespace(id=user_id),
                    effective_chat=SimpleNamespace(id=91_001),
                    message=second_text,
                ),
                SimpleNamespace(user_data={}),
            )
        ) is True

        current = ai_state.load_draft(user_id)
        assert current["ai_edit_details"] == {
            "scene_background": {"text": "Studio hiện đại, sáng mềm"},
            "person_outfit_color": {"text": "Màu đen"},
        }
        assert current["pending_input"] == {}

        review = _press(user_id, "videoedit|ai_summary")
        assert review.edits, review.answers
        review_text = review.edits[-1][0]
        assert "Studio hiện đại, sáng mềm" in review_text
        assert "Màu đen" in review_text
        assert _last_rows(review) == [
            [("✏️ Chỉnh lại lựa chọn", "videoedit|ai_selected")],
            [
                ("⬅️ Quay lại", "videoedit|ai_summary_back"),
                ("🏠 Menu chính", "menu|main"),
            ],
        ]
        assert not any(
            forbidden in review_text
            for forbidden in ("Key4U", "ElevenLabs", "PixVerse", "endpoint", "task_id")
        )
        summary_back = _press(user_id, "videoedit|ai_summary_back")
        assert _last_rows(summary_back)[-1] == [
            ("⬅️ Quay lại", "videoedit|ai_cat|person.0"),
            ("🏠 Menu chính", "menu|main"),
        ]
    finally:
        ai_state.clear_draft(user_id)


def test_reference_detail_owns_only_its_image_and_binds_it_to_the_exact_ai_draft() -> None:
    ai_state = importlib.import_module("services.video_ai_edit_state")
    user_id = 91_004
    ai_state.clear_draft(user_id)
    ai_state.replace_source_draft(
        user_id=user_id,
        chat_id=91_001,
        draft_id="reference-session",
        source={
            "file_id": "owned-video",
            "file_name": "owned.mp4",
            "file_size": 4_096,
            "fingerprint": "d" * 64,
        },
        metadata={
            "ok": True,
            "has_video": True,
            "duration": 8.0,
            "duration_ms": 8_000,
            "width": 720,
            "height": 1_280,
        },
    )
    try:
        _press(user_id, "videoedit|ai_catalog")
        _press(user_id, "videoedit|ai_cat|person.0")
        _press(user_id, "videoedit|ai_item|person_replace.person.0")
        _press(user_id, "videoedit|ai_selected")
        detail = _press(user_id, "videoedit|ai_detail|person_replace")
        assert _last_rows(detail)[-1] == [
            ("⬅️ Quay lại", "videoedit|ai_selected"),
            ("🏠 Menu chính", "menu|main"),
        ]

        message = _Message()
        message.photo = [
            SimpleNamespace(file_id="reference-small", file_unique_id="reference-small-unique", file_size=20),
            SimpleNamespace(file_id="reference-large", file_unique_id="reference-large-unique", file_size=40),
        ]
        assert asyncio.run(
            bot.handle_video_ai_edit_pending_media(
                SimpleNamespace(
                    effective_user=SimpleNamespace(id=user_id),
                    effective_chat=SimpleNamespace(id=91_001),
                    message=message,
                ),
                SimpleNamespace(user_data={}),
            )
        ) is True

        current = ai_state.load_draft(user_id)
        assert current["pending_input"] == {}
        assert current["ai_edit_references"] == {
            "person_replace": {
                "file_id": "reference-large",
                "file_unique_id": "reference-large-unique",
                "file_size": 40,
                "user_id": str(user_id),
                "chat_id": "91001",
                "draft_id": "reference-session",
                "selection_id": "person_replace",
                "source_fingerprint": "d" * 64,
            }
        }
        assert _rows(message.replies[-1][1]["reply_markup"])[-1] == [
            ("⬅️ Quay lại", "videoedit|ai_cat|person.0"),
            ("🏠 Menu chính", "menu|main"),
        ]
    finally:
        ai_state.clear_draft(user_id)


def test_ai_source_admission_only_accepts_mp4_mov_with_the_public_ui_limits() -> None:
    ai_state = importlib.import_module("services.video_ai_edit_state")
    source = {"file_name": "source.mp4", "file_size": 50 * 1024 * 1024}
    metadata = {"ok": True, "has_video": True, "duration": 30.0, "width": 1920, "height": 1080}

    assert ai_state.source_admission(source, metadata) == {"ok": True, "reason": ""}
    assert ai_state.source_admission({**source, "file_name": "source.mkv"}, metadata)["reason"] == "ai_edit_source_format"
    assert ai_state.source_admission(source, {**metadata, "duration": 30.1})["reason"] == "ai_edit_source_duration"
    assert ai_state.source_admission({**source, "file_size": 50 * 1024 * 1024 + 1}, metadata)["reason"] == "ai_edit_source_size"
    assert ai_state.source_admission(source, {**metadata, "width": 1921})["reason"] == "ai_edit_source_dimensions"


def test_ai_upload_rejects_an_ineligible_source_without_creating_an_ai_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ai_state = importlib.import_module("services.video_ai_edit_state")
    user_id = 91_005
    bot.clear_video_editor_pending(user_id)
    ai_state.clear_draft(user_id)
    monkeypatch.setattr(
        bot,
        "video_editor_source_from_update",
        lambda _update: {
            "source_file_id": "wrong-format",
            "source_file_unique_id": "wrong-format-unique",
            "source_file_name": "wrong-format.mkv",
            "source_file_size": 4_096,
            "source_mime_type": "video/x-matroska",
        },
    )

    async def inspect_source(*_args, **_kwargs):
        return {
            "ok": True,
            "has_video": True,
            "duration": 10.0,
            "duration_ms": 10_000,
            "width": 1_080,
            "height": 1_920,
            "source_sha256": "e" * 64,
        }

    monkeypatch.setattr(bot, "inspect_video_editor_source", inspect_source)
    monkeypatch.setattr(bot, "cache_recent_media_state", lambda _update: None)
    try:
        _press(user_id, "videoedit|ai")
        message = _UploadMessage()
        assert asyncio.run(
            bot.handle_video_editor_pending_upload(
                SimpleNamespace(
                    effective_user=SimpleNamespace(id=user_id),
                    effective_chat=SimpleNamespace(id=91_001),
                    message=message,
                    callback_query=None,
                ),
                SimpleNamespace(user_data={}),
            )
        ) is True
        assert "MP4 hoặc MOV" in message.replies[-1][0]
        assert ai_state.load_draft(user_id) == {}
        assert dict(bot.get_video_editor_pending(user_id) or {})["step"] == "await_edit_video"
        assert _rows(message.replies[-1][1]["reply_markup"])[-1] == [
            ("⬅️ Quay lại", "videoedit|hub"),
            ("🏠 Menu chính", "menu|main"),
        ]
    finally:
        bot.clear_video_editor_pending(user_id)
        ai_state.clear_draft(user_id)


def test_stale_catalog_item_cannot_change_a_selection_after_the_user_moves_to_another_category() -> None:
    ai_state = importlib.import_module("services.video_ai_edit_state")
    user_id = 91_006
    ai_state.clear_draft(user_id)
    ai_state.replace_source_draft(
        user_id=user_id,
        chat_id=91_001,
        draft_id="stale-session",
        source={"file_id": "source", "file_name": "source.mp4", "file_size": 4_096, "fingerprint": "f" * 64},
        metadata={"ok": True, "has_video": True, "duration": 8.0, "width": 720, "height": 1280},
    )
    try:
        _press(user_id, "videoedit|ai_catalog")
        _press(user_id, "videoedit|ai_cat|scene.0")
        _press(user_id, "videoedit|ai_cat|person.0")
        stale = _press(user_id, "videoedit|ai_item|scene_background.scene.0")
        assert ai_state.load_draft(user_id)["ai_edit_selected"] == []
        assert stale.answers[-1][1]["show_alert"] is True
    finally:
        ai_state.clear_draft(user_id)


def test_ai_edit_hub_exit_clears_the_ai_draft_so_it_cannot_capture_later_input() -> None:
    ai_state = importlib.import_module("services.video_ai_edit_state")
    user_id = 91_007
    ai_state.clear_draft(user_id)
    ai_state.replace_source_draft(
        user_id=user_id,
        chat_id=91_001,
        draft_id="exit-session",
        source={"file_id": "source", "file_name": "source.mp4", "file_size": 4096, "fingerprint": "0" * 64},
        metadata={"ok": True, "has_video": True, "duration": 8.0, "width": 720, "height": 1280},
    )
    try:
        hub = _press(user_id, "videoedit|hub")
        assert _last_rows(hub) == _rows(bot.video_edit_hub_keyboard("vi"))
        assert ai_state.load_draft(user_id) == {}
    finally:
        ai_state.clear_draft(user_id)


def test_ai_edit_main_menu_exit_clears_the_ai_draft_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ai_state = importlib.import_module("services.video_ai_edit_state")
    user_id = 91_008
    ai_state.clear_draft(user_id)
    monkeypatch.setattr(bot, "localized_menu_content", lambda *_args: ("menu", bot.video_edit_hub_keyboard("vi")))
    ai_state.replace_source_draft(
        user_id=user_id,
        chat_id=91_001,
        draft_id="main-exit-session",
        source={"file_id": "source", "file_name": "source.mp4", "file_size": 4096, "fingerprint": "1" * 64},
        metadata={"ok": True, "has_video": True, "duration": 8.0, "width": 720, "height": 1280},
    )
    try:
        _press_menu(user_id)
        assert ai_state.load_draft(user_id) == {}
    finally:
        ai_state.clear_draft(user_id)


def test_stale_category_navigation_cannot_leave_a_detail_input_screen() -> None:
    ai_state = importlib.import_module("services.video_ai_edit_state")
    user_id = 91_009
    ai_state.clear_draft(user_id)
    ai_state.replace_source_draft(
        user_id=user_id,
        chat_id=91_001,
        draft_id="stale-navigation-session",
        source={"file_id": "source", "file_name": "source.mp4", "file_size": 4096, "fingerprint": "2" * 64},
        metadata={"ok": True, "has_video": True, "duration": 8.0, "width": 720, "height": 1280},
    )
    try:
        _press(user_id, "videoedit|ai_catalog")
        _press(user_id, "videoedit|ai_cat|scene.0")
        _press(user_id, "videoedit|ai_item|scene_background.scene.0")
        _press(user_id, "videoedit|ai_selected")
        _press(user_id, "videoedit|ai_detail|scene_background")
        assert ai_state.load_draft(user_id)["current_screen"] == "ai_detail"

        stale = _press(user_id, "videoedit|ai_cat|person.0")
        current = ai_state.load_draft(user_id)
        assert current["current_screen"] == "ai_detail"
        assert current["pending_input"] == {"capability_id": "scene_background", "field": "text"}
        assert stale.answers[-1][1]["show_alert"] is True
    finally:
        ai_state.clear_draft(user_id)


def test_every_public_ai_edit_button_has_a_unique_valid_telegram_callback() -> None:
    catalog = importlib.import_module("services.video_ai_edit_catalog")
    state = {"ai_edit_selected": [item.stable_id for item in catalog.CAPABILITIES]}
    keyboards = [
        bot.video_edit_hub_keyboard("vi"),
        bot.video_ai_edit_upload_keyboard("vi"),
        bot.video_ai_edit_source_summary_keyboard("vi", {}),
        bot.video_ai_edit_catalog_home_keyboard(state, "vi"),
        bot.video_ai_edit_selected_keyboard(state, "vi"),
        bot.video_ai_edit_detail_keyboard("vi"),
        bot.video_ai_edit_summary_keyboard("vi"),
        *[
            bot.video_ai_edit_category_keyboard(state, category.stable_id, page_index, "vi")
            for category in catalog.CATEGORIES
            for page_index in range(catalog.page_count(category.stable_id))
        ],
    ]
    for markup in keyboards:
        callbacks = [
            callback
            for row in _rows(markup)
            for _label, callback in row
            if callback.startswith("videoedit|ai")
        ]
        assert callbacks
        assert len(callbacks) == len(set(callbacks))
        assert all(len(callback.encode("utf-8")) <= 64 for callback in callbacks)
        assert all(bot.video_editor_callback_arity_valid(callback.split("|")) for callback in callbacks)
