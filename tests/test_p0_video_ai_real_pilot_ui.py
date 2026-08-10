from __future__ import annotations

import asyncio
import re
from types import SimpleNamespace

import bot
import pytest
from services import video_uiflow3


def _locked_state(*, capabilities: dict | None = None) -> dict:
    state = video_uiflow3.new_state(
        "video_ai_real",
        draft_id="pilot-ui",
        capabilities=capabilities,
    )
    state = video_uiflow3.set_entry_mode(state, "prompt_video")
    state = video_uiflow3.set_format(state, ratio="9:16", target_duration_seconds=8)
    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent="Lan va Minh gioi thieu san pham.",
        approved_brief={
            "title": "Gioi thieu san pham",
            "needs_characters": True,
            "needs_locations": True,
            "needs_dialogue": True,
            "needs_voice": True,
        },
    )
    return video_uiflow3.lock_content(state)


def _logical_callback(value: str) -> str:
    parts = str(value or "").split("|")
    if len(parts) >= 4 and parts[:2] == ["vid3", "d"]:
        return "|".join(("vid3", *parts[3:]))
    return str(value or "")


def _callbacks(markup) -> list[str]:
    return [
        _logical_callback(str(button.callback_data or ""))
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def _labels(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def _plain_label(value: str) -> str:
    return re.sub(r"^[^0-9A-Za-zÀ-ỹ]+", "", str(value or "")).strip()


def _plain_labels(markup) -> list[str]:
    return [_plain_label(label) for label in _labels(markup)]


class _PilotQuery:
    def __init__(
        self,
        user_id: int,
        data: str,
        query_id: str,
        *,
        message_id: int = 1,
        chat_id: int | None = None,
    ) -> None:
        self.data = data
        self.id = query_id
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace(
            chat_id=user_id if chat_id is None else chat_id,
            message_id=message_id,
        )
        self.edits: list[dict] = []
        self.answers: list[dict] = []

    async def answer(self, text: str | None = None, **kwargs) -> None:
        self.answers.append({"text": text, **kwargs})

    async def edit_message_text(self, text: str, **kwargs) -> None:
        self.edits.append({"text": text, **kwargs})


class _PilotMessage:
    def __init__(self, user_id: int, text: str, message_id: int) -> None:
        self.chat_id = user_id
        self.text = text
        self.message_id = message_id
        self.replies: list[dict] = []

    async def reply_text(self, text: str, **kwargs) -> None:
        self.replies.append({"text": text, **kwargs})


def _save_owned(context, state: dict, user_id: int) -> dict:
    state = video_uiflow3.normalize_state(state)
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    return bot.save_video_uiflow3_state(context, state)


def _click_visible(context, user_id: int, logical_callback: str, query_id: str) -> _PilotQuery:
    state = bot.video_uiflow3_state(context)
    _text, markup = bot.video_uiflow3_screen_payload(state)
    wire_callback = next(
        (
            str(button.callback_data or "")
            for row in markup.inline_keyboard
            for button in row
            if _logical_callback(str(button.callback_data or "")) == logical_callback
        ),
        "",
    )
    assert wire_callback, f"callback is not visible: {logical_callback}"
    query = _PilotQuery(user_id, wire_callback, query_id)
    asyncio.run(
        bot.handle_video_uiflow3_callback(
            SimpleNamespace(callback_query=query),
            context,
        )
    )
    return query


def _assigned_state() -> dict:
    state = _locked_state(
        capabilities={
            "whole_video_music": True,
            "per_scene_music": True,
            "scene_sfx": True,
            "scene_ambient": True,
        }
    )
    state = video_uiflow3.set_character_count(state, 2)
    state = video_uiflow3.update_character(
        state,
        "char_01",
        display_name="Lan",
        gender="female",
    )
    state = video_uiflow3.update_character(
        state,
        "char_02",
        display_name="Minh",
        gender="male",
    )
    state = video_uiflow3.set_location_count(state, 2)
    state = video_uiflow3.update_location(state, "loc_01", name="Quán cà phê")
    state = video_uiflow3.update_location(state, "loc_02", name="Đường phố")
    state = video_uiflow3.confirm_scene_count(state, 2)
    state = video_uiflow3.suggest_scene_plan(state)
    state = video_uiflow3.assign_scene(
        state,
        "scene_01",
        character_ids=["char_01", "char_02"],
        location_id="loc_01",
    )
    state = video_uiflow3.assign_scene(
        state,
        "scene_02",
        character_ids=["char_02"],
        location_id="loc_02",
    )
    state["navigation"]["current_step"] = "scene_assignment"
    return video_uiflow3.normalize_state(state)


def test_video_ai_real_pilot_ratio_screen_keeps_duration_out_of_the_early_step():
    state = video_uiflow3.new_state("video_ai_real", draft_id="pilot-format")
    state = video_uiflow3.set_entry_mode(state, "prompt_video")
    state = video_uiflow3.set_format(state, ratio="9:16", target_duration_seconds=8)
    state["navigation"]["current_step"] = "format"

    text, markup = bot.video_uiflow3_screen_payload(state)
    callbacks = _callbacks(markup)

    assert "Tỷ lệ khung hình" in text
    assert "Dọc 9:16" in text
    assert "giây/cảnh" not in text
    assert "vid3|duration_scene|6" not in callbacks
    assert "vid3|duration_scene|8" not in callbacks


def test_video_ai_real_pilot_character_detail_uses_gender_label_and_per_character_image():
    state = video_uiflow3.set_character_count(_locked_state(), 2)
    state = video_uiflow3.confirm_scene_count(state, 2)
    state["navigation"]["current_step"] = "production_bible"
    state = bot.video_uiflow3_open_view(
        state,
        "character_detail",
        active_character_id="char_01",
    )

    text, markup = bot.video_uiflow3_screen_payload(state)
    callbacks = _callbacks(markup)

    assert "Giới tính" in text
    assert "Gửi ảnh nhân vật 1" in text
    assert "Nhân vật 1" in text
    assert "male" not in text.lower()
    assert "vid3|char_image|char_01" in callbacks
    assert "vid3|char_scenes|char_01" in callbacks


def test_video_ai_real_pilot_location_detail_offers_context_suggestions_and_exact_parent_back():
    state = video_uiflow3.set_location_count(_locked_state(), 1)
    state["navigation"]["current_step"] = "production_bible"
    state = bot.video_uiflow3_open_view(
        state,
        "location_detail",
        active_location_id="loc_01",
    )

    text, markup = bot.video_uiflow3_screen_payload(state)
    callbacks = _callbacks(markup)

    assert "Gợi ý bối cảnh" in text
    assert "quán cà phê" in text.lower()
    assert "đường phố" in text.lower()
    assert "vid3|loc_suggest|loc_01|cafe" in callbacks
    assert "vid3|loc_suggest|loc_01|street" in callbacks
    assert "vid3|view|location_list" in callbacks


def test_video_ai_real_pilot_location_uses_image_first_and_never_reasks_for_a_preset():
    state = video_uiflow3.set_location_count(_locked_state(), 1)
    state = video_uiflow3.add_source_asset(
        state,
        asset_type="image",
        telegram_file_id="source-location-image",
        fingerprint="sha256:source-location-image",
    )
    state["navigation"]["current_step"] = "production_bible"
    state = bot.video_uiflow3_open_view(
        state,
        "location_detail",
        active_location_id="loc_01",
    )

    no_reference_text, no_reference_markup = bot.video_uiflow3_screen_payload(state)
    assert "Gợi ý bối cảnh" in no_reference_text
    assert "vid3|loc_suggest|loc_01|cafe" in _callbacks(no_reference_markup)
    assert "vid3|source_ref_set|source_01|location|loc_01" in _callbacks(no_reference_markup)

    state = video_uiflow3.add_reference(
        state,
        asset_type="image",
        owner_type="location",
        owner_id="loc_01",
        role="primary_location",
        telegram_file_id="location-image",
        fingerprint="sha256:location-image",
    )
    state = bot.video_uiflow3_open_view(
        state,
        "location_detail",
        active_location_id="loc_01",
    )

    reference_text, reference_markup = bot.video_uiflow3_screen_payload(state)
    assert "Ảnh đã gửi đang là chuẩn bối cảnh" in reference_text
    assert not any(
        callback.startswith("vid3|loc_suggest|loc_01|")
        for callback in _callbacks(reference_markup)
    )


def test_video_ai_real_pilot_scene_assignment_explains_continuity_and_music_scope():
    state = video_uiflow3.set_character_count(
        _locked_state(capabilities={"whole_video_music": True, "per_scene_music": True}),
        2,
    )
    state = video_uiflow3.set_location_count(state, 1)
    state = video_uiflow3.confirm_scene_count(state, 2)
    state = video_uiflow3.suggest_scene_plan(state)
    state["navigation"]["current_step"] = "scene_assignment"

    text, markup = bot.video_uiflow3_screen_payload(state)
    callbacks = _callbacks(markup)

    assert "Phân vai và âm thanh theo cảnh" in text
    assert "Cảnh 2 nối tiếp kết quả Cảnh 1" in text
    assert "Nhân vật 1" in text
    assert "Nhạc toàn video" in text
    assert "Nhạc theo từng cảnh" in text
    assert "vid3|view|audio_options" in callbacks


def test_video_ai_real_pilot_location_back_callback_is_the_immediate_parent():
    state = video_uiflow3.set_location_count(_locked_state(), 1)
    state["navigation"]["current_step"] = "production_bible"
    state = bot.video_uiflow3_open_view(
        state,
        "location_detail",
        active_location_id="loc_01",
    )

    _text, markup = bot.video_uiflow3_screen_payload(state)
    finish_buttons = [
        _logical_callback(str(button.callback_data or ""))
        for row in markup.inline_keyboard
        for button in row
        if _plain_label(button.text) == "Hoàn tất khai báo bối cảnh này"
    ]

    assert finish_buttons == ["vid3|view|location_list"]


def test_video_ai_real_pilot_entry_restores_clear_source_choices_and_readonly_idea_catalog():
    state = video_uiflow3.new_state(
        "video_ai_real",
        draft_id="pilot-entry",
        capabilities={"video_to_video": True},
    )

    text, markup = bot.video_uiflow3_screen_payload(state)
    labels = _plain_labels(markup)
    callbacks = _callbacks(markup)

    assert "Video AI chân thật" in text
    assert "Prompt → Video" in labels
    assert "Ảnh → Video" in labels
    assert "Video mẫu → Video" not in labels
    assert "Kho ý tưởng (chỉ xem)" not in labels
    assert "vid3|mode|prompt_video" in callbacks
    assert "vid3|mode|image_video" in callbacks
    assert "vid3|mode|video_video" not in callbacks
    assert "vid3|idea_catalog" not in callbacks


def test_video_ai_real_product_first_format_applies_to_prompt_and_image_only():
    prompt_state = video_uiflow3.new_state("video_ai_real", draft_id="pilot-scope-prompt")
    prompt_state = video_uiflow3.set_entry_mode(prompt_state, "prompt_video")
    prompt_state = video_uiflow3.set_format(
        prompt_state,
        ratio="9:16",
        target_duration_seconds=16,
        seconds_per_scene=6,
    )
    prompt_state["navigation"]["current_step"] = "format"

    prompt_text, _prompt_markup = bot.video_uiflow3_screen_payload(prompt_state)
    assert "Tỷ lệ khung hình" in prompt_text
    assert "giây/cảnh" not in prompt_text

    image_state = video_uiflow3.new_state("video_ai_real", draft_id="pilot-scope-image")
    image_state = video_uiflow3.set_entry_mode(image_state, "image_video")
    image_state = video_uiflow3.set_scene_count_preference(image_state, 2)
    image_state = video_uiflow3.set_format(
        image_state,
        ratio="9:16",
        target_duration_seconds=12,
        seconds_per_scene=6,
    )
    image_state["navigation"]["current_step"] = "format"

    image_text, _image_markup = bot.video_uiflow3_screen_payload(image_state)
    assert "Tỷ lệ khung hình" in image_text
    assert "Sản phẩm: Ảnh → Video · 2 cảnh" in image_text
    normalized_image_state = video_uiflow3.normalize_state(image_state)
    assert normalized_image_state["format"]["seconds_per_scene"] == 6

    other_product = video_uiflow3.new_state("script_image_video", draft_id="pilot-scope-other")
    with pytest.raises(ValueError, match="scene_duration_invalid"):
        video_uiflow3.set_format(other_product, seconds_per_scene=6)


def test_prompt_product_selection_precedes_scene_count_then_ratio():
    user_id = 981003
    context = SimpleNamespace(user_data={})
    entry = video_uiflow3.new_state("video_ai_real", draft_id="pilot-product-first")
    _save_owned(context, entry, user_id)

    _click_visible(context, user_id, "vid3|mode|prompt_video", "pilot-product-first-1")
    choosing_scenes = bot.video_uiflow3_state(context)
    assert choosing_scenes["entry_mode"] == "prompt_video"
    assert choosing_scenes["navigation"]["current_step"] == "scene_count"
    scene_text, scene_markup = bot.video_uiflow3_screen_payload(choosing_scenes)
    assert "Chọn số cảnh" in scene_text
    assert "Prompt → Video" in scene_text
    assert {"1 cảnh", "2 cảnh", "3 cảnh", "5 cảnh"}.issubset(set(_plain_labels(scene_markup)))

    _click_visible(context, user_id, "vid3|scene_count|2", "pilot-product-first-2")
    choosing_ratio = bot.video_uiflow3_state(context)
    assert choosing_ratio["navigation"]["current_step"] == "format"
    assert choosing_ratio["format"]["scene_count"] == 2
    assert choosing_ratio["format"]["scene_count_confirmed"] is False
    assert choosing_ratio["scenes"] == []
    format_text, format_markup = bot.video_uiflow3_screen_payload(choosing_ratio)
    assert "2 cảnh" in format_text
    assert "Dọc 9:16" in _plain_labels(format_markup)
    assert not any("giây/cảnh" in label for label in _plain_labels(format_markup))

    _click_visible(context, user_id, "vid3|ratio|9x16", "pilot-product-first-3")
    content_state = bot.video_uiflow3_state(context)
    assert content_state["navigation"]["current_step"] == "content_hub"
    assert content_state["format"]["ratio"] == "9:16"


def test_image_product_selection_precedes_scene_count_ratio_then_source_with_exact_back():
    user_id = 981013
    context = SimpleNamespace(user_data={})
    entry = video_uiflow3.new_state("video_ai_real", draft_id="pilot-image-product-first")
    _save_owned(context, entry, user_id)

    _click_visible(context, user_id, "vid3|mode|image_video", "pilot-image-product-first-1")
    choosing_scenes = bot.video_uiflow3_state(context)
    assert choosing_scenes["entry_mode"] == "image_video"
    assert choosing_scenes["source"]["kind"] == "raw_images"
    assert choosing_scenes["navigation"]["current_step"] == "scene_count"
    scene_text, _scene_markup = bot.video_uiflow3_screen_payload(choosing_scenes)
    assert "Sản phẩm: Ảnh → Video" in scene_text

    _click_visible(context, user_id, "vid3|scene_count|2", "pilot-image-product-first-2")
    choosing_format = bot.video_uiflow3_state(context)
    assert choosing_format["navigation"]["current_step"] == "format"
    assert choosing_format["format"]["scene_count"] == 2
    assert choosing_format["scenes"] == []
    format_text, format_markup = bot.video_uiflow3_screen_payload(choosing_format)
    assert "Sản phẩm: Ảnh → Video · 2 cảnh" in format_text
    assert "Dọc 9:16" in _plain_labels(format_markup)
    assert not any("giây/cảnh" in label for label in _plain_labels(format_markup))

    _click_visible(context, user_id, "vid3|ratio|9x16", "pilot-image-product-first-3")
    source_state = bot.video_uiflow3_state(context)
    assert source_state["navigation"]["current_step"] == "source"
    assert source_state["format"]["ratio"] == "9:16"
    assert source_state["format"]["target_duration_seconds"] == 0
    source_text, _source_markup = bot.video_uiflow3_screen_payload(source_state)
    assert "Ảnh tham chiếu đầu vào" in source_text

    _click_visible(context, user_id, "vid3|back", "pilot-image-product-first-4")
    assert bot.video_uiflow3_state(context)["navigation"]["current_step"] == "format"
    _click_visible(context, user_id, "vid3|back", "pilot-image-product-first-5")
    assert bot.video_uiflow3_state(context)["navigation"]["current_step"] == "scene_count"
    _click_visible(context, user_id, "vid3|back", "pilot-image-product-first-6")
    assert bot.video_uiflow3_state(context)["navigation"]["current_step"] == "entry"


def test_image_product_collects_sources_after_format_and_done_advances_to_content():
    user_id = 981014
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.new_state("video_ai_real", draft_id="pilot-image-source-after-format")
    state = video_uiflow3.set_entry_mode(state, "image_video")
    state = video_uiflow3.set_scene_count_preference(state, 2)
    state = video_uiflow3.set_format(
        state,
        ratio="9:16",
        target_duration_seconds=16,
        seconds_per_scene=8,
    )
    state = video_uiflow3.navigate(state, "source")
    state = video_uiflow3.add_source_asset(
        state,
        asset_type="image",
        telegram_file_id="image-source-file-1",
        fingerprint="image-source-fingerprint-1",
    )

    assert state["navigation"]["current_step"] == "source"
    _save_owned(context, state, user_id)
    _click_visible(context, user_id, "vid3|source_done", "pilot-image-source-after-format-1")
    content_state = bot.video_uiflow3_state(context)
    assert content_state["navigation"]["current_step"] == "content_hub"
    assert content_state["entry_mode"] == "image_video"
    assert content_state["format"]["scene_count"] == 2
    assert content_state["format"]["ratio"] == "9:16"


def test_image_product_materializes_preselected_scenes_only_after_bible_done():
    user_id = 981015
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.new_state("video_ai_real", draft_id="pilot-image-deferred-scenes")
    state = video_uiflow3.set_entry_mode(state, "image_video")
    state = video_uiflow3.set_scene_count_preference(state, 2)
    state = video_uiflow3.set_format(
        state,
        ratio="9:16",
        target_duration_seconds=16,
        seconds_per_scene=8,
    )
    state = video_uiflow3.add_source_asset(
        state,
        asset_type="image",
        telegram_file_id="image-deferred-source",
        fingerprint="image-deferred-fingerprint",
    )
    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent="Hai cảnh chuyển động nối tiếp từ một ảnh tham chiếu.",
        approved_brief={
            "title": "Hai cảnh từ ảnh",
            "needs_characters": False,
            "needs_locations": False,
            "needs_dialogue": False,
            "needs_voice": False,
            "needs_music": False,
        },
    )
    state = video_uiflow3.lock_content(state)
    state = video_uiflow3.set_character_count(state, 0)
    state = video_uiflow3.set_location_count(state, 0)
    state["navigation"]["current_step"] = "production_bible"
    _save_owned(context, state, user_id)

    assert bot.video_uiflow3_state(context)["scenes"] == []
    _click_visible(context, user_id, "vid3|bible_done", "pilot-image-deferred-scenes-1")

    planned = bot.video_uiflow3_state(context)
    assert planned["navigation"]["current_step"] == "scene_plan"
    assert planned["format"]["scene_count_confirmed"] is True
    assert [scene["duration_target"] for scene in planned["scenes"]] == [8, 8]
    assert [scene["ratio"] for scene in planned["scenes"]] == ["9:16", "9:16"]


def test_prompt_preselected_scene_count_materializes_only_after_bible_done():
    user_id = 981004
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.new_state("video_ai_real", draft_id="pilot-deferred-scenes")
    state = video_uiflow3.set_entry_mode(state, "prompt_video")
    state = video_uiflow3.set_scene_count_preference(state, 2)
    state = video_uiflow3.set_format(
        state,
        ratio="9:16",
        target_duration_seconds=12,
        seconds_per_scene=6,
    )
    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent="Hai cảnh giới thiệu một sản phẩm.",
        approved_brief={
            "title": "Giới thiệu sản phẩm",
            "needs_characters": False,
            "needs_locations": False,
            "needs_dialogue": False,
            "needs_voice": False,
            "needs_music": False,
        },
    )
    state = video_uiflow3.lock_content(state)
    state = video_uiflow3.set_character_count(state, 0)
    state = video_uiflow3.set_location_count(state, 0)
    state["navigation"]["current_step"] = "production_bible"
    _save_owned(context, state, user_id)

    assert bot.video_uiflow3_state(context)["scenes"] == []
    _click_visible(context, user_id, "vid3|bible_done", "pilot-deferred-scenes-1")

    planned = bot.video_uiflow3_state(context)
    assert planned["navigation"]["current_step"] == "scene_plan"
    assert planned["format"]["scene_count_confirmed"] is True
    assert len(planned["scenes"]) == 2
    assert [scene["duration_target"] for scene in planned["scenes"]] == [6, 6]
    assert [scene["ratio"] for scene in planned["scenes"]] == ["9:16", "9:16"]


def test_video_ai_real_pilot_content_hub_and_content_lock_are_clear_and_accented():
    state = video_uiflow3.new_state("video_ai_real", draft_id="pilot-content")
    state = video_uiflow3.set_entry_mode(state, "prompt_video")
    state = video_uiflow3.set_format(state, ratio="9:16", target_duration_seconds=8)

    hub_text, hub_markup = bot.video_uiflow3_screen_payload(state)
    hub_labels = _plain_labels(hub_markup)

    assert "Chọn nội dung video" in hub_text
    assert "32 loại nội dung" in hub_labels
    assert "Ý tưởng video" in hub_labels
    assert "vid3|idea_catalog" in _callbacks(hub_markup)
    assert "Tự mô tả nội dung" in hub_labels

    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent="Một video giới thiệu sản phẩm cho người mới.",
        approved_brief={"title": "Giới thiệu sản phẩm", "goal": "Tạo niềm tin"},
    )
    lock_text, lock_markup = bot.video_uiflow3_screen_payload(state)

    assert "Nội dung đã chọn" in lock_text
    assert "Chủ đề: Giới thiệu sản phẩm" in lock_text
    assert "Hoàn tất xác nhận nội dung" in _plain_labels(lock_markup)
    assert "Chọn nội dung khác" in _plain_labels(lock_markup)


def test_video_ai_real_pilot_restores_the_old_flow_without_numbered_steps():
    state = video_uiflow3.new_state("video_ai_real", draft_id="pilot-no-step-counter")
    state = video_uiflow3.set_entry_mode(state, "prompt_video")
    state = video_uiflow3.set_scene_count_preference(state, 2)
    state = video_uiflow3.set_format(state, ratio="9:16", target_duration_seconds=16)

    text, _markup = bot.video_uiflow3_screen_payload(state)

    assert "Bước " not in text
    assert "Buoc " not in text
    assert bot.video_uiflow3_progress_text(state) == ""


def test_video_ai_real_pilot_production_bible_uses_beginner_copy_and_zero_is_explicit_auto():
    state = _locked_state()
    state["navigation"]["current_step"] = "production_bible"

    text, markup = bot.video_uiflow3_screen_payload(state)
    labels = _plain_labels(markup)

    assert "Nhân vật và bối cảnh" in text
    assert "Production Bible" not in text
    assert "Số nhân vật" in labels
    assert "Số bối cảnh" in labels
    assert "Tự động gợi ý" in labels

    state = bot.video_uiflow3_open_view(state, "character_count")
    character_text, character_markup = bot.video_uiflow3_screen_payload(state)
    assert "0 = video không khóa nhân vật" in character_text
    assert {"0 nhân vật", "1 nhân vật", "2 nhân vật"}.issubset(set(_plain_labels(character_markup)))

    state = bot.video_uiflow3_open_view(
        _locked_state(),
        "location_count",
    )
    state["navigation"]["current_step"] = "production_bible"
    location_text, location_markup = bot.video_uiflow3_screen_payload(state)
    assert "0 = để hệ thống tự chọn bối cảnh" in location_text
    assert {"0 bối cảnh", "1 bối cảnh", "2 bối cảnh"}.issubset(set(_plain_labels(location_markup)))


def test_video_ai_real_pilot_voice_screen_filters_by_gender_and_explains_distinct_voices():
    state = video_uiflow3.set_character_count(_locked_state(), 2)
    state = bot.video_uiflow3_open_view(
        state,
        "voice_select",
        active_character_id="char_01",
        ui_return_callback="vid3|character|char_01",
    )

    text, markup = bot.video_uiflow3_screen_payload(state)
    assert "Giọng của Nhân vật 1" in text
    assert "hai giọng khác nhau" in text
    assert {"Nhân vật nam", "Nhân vật nữ"}.issubset(set(_plain_labels(markup)))

    state = video_uiflow3.update_character(state, "char_01", gender="male")
    state = bot.video_uiflow3_open_view(
        state,
        "voice_select",
        active_character_id="char_01",
        ui_return_callback="vid3|character|char_01",
    )
    male_text, male_markup = bot.video_uiflow3_screen_payload(state)
    assert "Giọng nam" in male_text
    assert "Giọng nam 1" in _plain_labels(male_markup)
    assert "Giọng nam 2" in _plain_labels(male_markup)


def test_video_ai_real_pilot_music_scope_is_accented_capability_aware_and_returns_to_assignment():
    state = _locked_state(capabilities={"whole_video_music": True, "per_scene_music": True})
    state = video_uiflow3.set_character_count(state, 0)
    state = video_uiflow3.set_location_count(state, 0)
    state = video_uiflow3.confirm_scene_count(state, 2)
    state["navigation"]["current_step"] = "scene_assignment"
    state = bot.video_uiflow3_open_view(state, "music_scope")

    text, markup = bot.video_uiflow3_screen_payload(state)
    labels = _plain_labels(markup)
    callbacks = _callbacks(markup)

    assert "Âm nhạc cho video" in text
    assert "Không dùng nhạc" in labels
    assert "Một bài cho toàn video" in labels
    assert "Nhạc theo từng cảnh" in labels
    assert "vid3|view|scene_assignment" in callbacks


def test_video_ai_real_pilot_scene_count_plan_branding_and_summary_have_one_clear_hub():
    state = video_uiflow3.set_character_count(_locked_state(), 0)
    state = video_uiflow3.set_location_count(state, 0)
    state["navigation"]["current_step"] = "scene_count"

    count_text, count_markup = bot.video_uiflow3_screen_payload(state)
    assert "Số cảnh được đề xuất" in count_text
    assert "thời lượng sẽ chọn ở bước Chất lượng" in count_text
    assert "Dùng đề xuất" in _plain_labels(count_markup)

    state = video_uiflow3.confirm_scene_count(state, 2)
    state = video_uiflow3.suggest_scene_plan(state)
    plan_text, plan_markup = bot.video_uiflow3_screen_payload(state)
    assert "Kế hoạch cảnh" in plan_text
    assert "Cảnh 1" in plan_text and "Cảnh 2" in plan_text
    assert "Duyệt kế hoạch" in _plain_labels(plan_markup)

    state["navigation"]["current_step"] = "branding"
    branding_text, branding_markup = bot.video_uiflow3_screen_payload(state)
    assert "Logo và watermark" in branding_text
    assert {"Gửi logo", "Nhập watermark", "Bỏ qua"}.issubset(set(_plain_labels(branding_markup)))

    state["navigation"]["current_step"] = "summary"
    summary_text, summary_markup = bot.video_uiflow3_screen_payload(state)
    assert "Rà soát cuối" in summary_text
    assert "Nhân vật và bối cảnh" in _plain_labels(summary_markup)
    assert "Phân vai và âm thanh" in _plain_labels(summary_markup)
    assert "Logo và watermark" in _plain_labels(summary_markup)

    dirty_state = _assigned_state()
    dirty_state["format"]["scene_count_confirmed"] = False
    dirty_state["navigation"]["dirty_sections"] = [
        "production_bible",
        "scene_plan",
        "dialogue",
        "prompts",
    ]
    dirty_state["navigation"]["current_step"] = "summary"
    assert len(video_uiflow3.readiness_errors(dirty_state)) > 8

    dirty_text, dirty_markup = bot.video_uiflow3_screen_payload(dirty_state)
    assert "Rà soát lại nhân vật và bối cảnh" in dirty_text
    assert re.search(r"Và \d+ mục khác cần hoàn tất", dirty_text)
    assert "vid3|edit|scene_count" in _callbacks(dirty_markup)


def test_video_ai_real_pilot_summary_scene_count_edit_and_back_stay_in_the_same_flow():
    user_id = 981002
    context = SimpleNamespace(user_data={})
    state = _assigned_state()
    state["format"]["scene_count_confirmed"] = False
    state["navigation"]["current_step"] = "summary"
    _save_owned(context, state, user_id)

    _click_visible(context, user_id, "vid3|edit|scene_count", "pilot-summary-scenes-1")
    editing = bot.video_uiflow3_state(context)
    assert editing["parent_product"] == "video_ai_real"
    assert editing["entry_mode"] == "prompt_video"
    assert editing["navigation"]["current_step"] == "scene_count"
    assert editing["navigation"]["return_to"] == "summary"

    _click_visible(context, user_id, "vid3|back", "pilot-summary-scenes-2")
    restored = bot.video_uiflow3_state(context)
    assert restored["navigation"]["current_step"] == "summary"
    assert restored["navigation"]["return_to"] is None


def test_video_ai_real_pilot_pending_inputs_use_accented_examples_and_exact_back():
    state = video_uiflow3.set_character_count(_locked_state(), 1)
    state = bot.video_uiflow3_await_input(
        state,
        "character_description",
        back_callback="vid3|character|char_01",
        character_id="char_01",
    )

    text, markup = bot.video_uiflow3_screen_payload(state)

    assert "Mô tả Nhân vật 1" in text
    assert "Tên nhân vật | ngoại hình | trang phục | vai trò" in text
    assert "vid3|character|char_01" in _callbacks(markup)


def test_video_ai_real_pilot_restores_old_visual_language_without_technical_markers():
    state = video_uiflow3.new_state(
        "video_ai_real",
        draft_id="pilot-visual-shell",
        capabilities={"video_to_video": True},
    )

    text, markup = bot.video_uiflow3_screen_payload(state)
    labels = _labels(markup)

    assert text.startswith("🎬 Video AI chân thật")
    assert "📝 Prompt → Video" in labels
    assert "🖼 Ảnh → Video" in labels
    assert "🎞 Video mẫu → Video" not in labels
    assert "🗂 Kho ý tưởng (chỉ xem)" not in labels
    assert "⬅️ Quay lại Menu Video" in labels
    assert "flow cũ" not in text.lower()
    assert _callbacks(markup).count("menu|main_video") == 1
    assert all("[x]" not in label and "[ ]" not in label for label in labels)


def test_video_ai_real_image_source_and_prompt_input_use_the_polished_pilot_shell():
    state = video_uiflow3.new_state(
        "video_ai_real",
        draft_id="pilot-source",
        capabilities={"video_to_video": True},
    )
    state = video_uiflow3.set_entry_mode(state, "image_video")
    state = video_uiflow3.set_scene_count_preference(state, 1)
    state = video_uiflow3.set_format(
        state,
        ratio="9:16",
        target_duration_seconds=8,
        seconds_per_scene=8,
    )
    state = video_uiflow3.navigate(state, "source")

    source_text, source_markup = bot.video_uiflow3_screen_payload(state)
    assert "Ảnh tham chiếu đầu vào" in source_text
    assert {"Gửi ảnh", "Đã nhận 0 ảnh"}.issubset(set(_plain_labels(source_markup)))
    assert "vid3|back" in _callbacks(source_markup)

    prompt_state = video_uiflow3.new_state("video_ai_real", draft_id="pilot-manual-input")
    prompt_state = video_uiflow3.set_entry_mode(prompt_state, "prompt_video")
    prompt_state = video_uiflow3.set_format(
        prompt_state,
        ratio="9:16",
        target_duration_seconds=8,
    )
    prompt_state["navigation"]["current_step"] = "content_hub"
    prompt_state = bot.video_uiflow3_await_input(
        prompt_state,
        "manual_content",
        back_callback="vid3|view|content_hub",
    )

    input_text, input_markup = bot.video_uiflow3_screen_payload(prompt_state)
    assert "✍️ Tự mô tả nội dung" in input_text
    assert "chủ đề | mục tiêu | thông điệp chính" in input_text
    assert "vid3|view|content_hub" in _callbacks(input_markup)


def test_video_ai_real_pilot_child_lists_references_and_continuity_are_accented():
    state = _assigned_state()
    state["navigation"]["current_step"] = "production_bible"

    character_state = bot.video_uiflow3_open_view(state, "character_list")
    character_text, character_markup = bot.video_uiflow3_screen_payload(character_state)
    assert "👥 Dàn nhân vật" in character_text
    assert {"Nhân vật 1 · Lan", "Nhân vật 2 · Minh"}.issubset(set(_plain_labels(character_markup)))
    assert "vid3|view|production_bible" in _callbacks(character_markup)

    location_state = bot.video_uiflow3_open_view(state, "location_list")
    location_text, location_markup = bot.video_uiflow3_screen_payload(location_state)
    assert "🏞 Danh sách bối cảnh" in location_text
    assert {"Bối cảnh 1 · Quán cà phê", "Bối cảnh 2 · Đường phố"}.issubset(set(_plain_labels(location_markup)))
    assert "vid3|view|production_bible" in _callbacks(location_markup)

    reference_state = bot.video_uiflow3_open_view(state, "references")
    reference_text, reference_markup = bot.video_uiflow3_screen_payload(reference_state)
    assert "🖼 Ảnh tham chiếu" in reference_text
    assert "Chưa có ảnh tham chiếu" in reference_text
    assert "vid3|view|production_bible" in _callbacks(reference_markup)

    continuity_state = bot.video_uiflow3_open_view(state, "continuity")
    continuity_text, continuity_markup = bot.video_uiflow3_screen_payload(continuity_state)
    assert "🔒 Giữ nhất quán" in continuity_text
    assert {"Khuôn mặt", "Trang phục", "Sản phẩm", "Bối cảnh"}.issubset(set(_plain_labels(continuity_markup)))
    assert all("[x]" not in label and "[ ]" not in label for label in _labels(continuity_markup))


def test_video_ai_real_pilot_scene_children_are_useful_and_back_to_exact_scene_parent():
    state = _assigned_state()

    detail = bot.video_uiflow3_open_view(state, "scene_detail", active_scene_id="scene_01")
    detail_text, detail_markup = bot.video_uiflow3_screen_payload(detail)
    detail_labels = _plain_labels(detail_markup)
    assert "🎬 Cảnh 1 · Phân vai và âm thanh" in detail_text
    assert "Nhân vật: Lan, Minh" in detail_text
    assert "Bối cảnh: Quán cà phê" in detail_text
    assert {"Nhân vật", "Bối cảnh", "Lời thoại", "Giọng nhân vật", "Nhạc cảnh"}.issubset(set(detail_labels))
    assert "vid3|view|scene_assignment" in _callbacks(detail_markup)

    cast = bot.video_uiflow3_open_view(state, "scene_cast", active_scene_id="scene_01")
    cast_text, cast_markup = bot.video_uiflow3_screen_payload(cast)
    assert "👥 Nhân vật trong Cảnh 1" in cast_text
    assert {"Nhân vật 1 · Lan", "Nhân vật 2 · Minh"}.issubset(set(_plain_labels(cast_markup)))
    assert "vid3|scene|scene_01" in _callbacks(cast_markup)

    location = bot.video_uiflow3_open_view(state, "scene_location", active_scene_id="scene_01")
    location_text, location_markup = bot.video_uiflow3_screen_payload(location)
    assert "🏞 Bối cảnh của Cảnh 1" in location_text
    assert "Bối cảnh 1 · Quán cà phê" in _plain_labels(location_markup)
    assert "vid3|scene|scene_01" in _callbacks(location_markup)

    voice = bot.video_uiflow3_open_view(state, "scene_voice", active_scene_id="scene_01")
    voice_text, voice_markup = bot.video_uiflow3_screen_payload(voice)
    assert "🎙 Giọng trong Cảnh 1" in voice_text
    assert "giữ nguyên ở mọi cảnh" in voice_text
    assert "vid3|scene|scene_01" in _callbacks(voice_markup)

    music = bot.video_uiflow3_open_view(state, "scene_music", active_scene_id="scene_01")
    music_text, music_markup = bot.video_uiflow3_screen_payload(music)
    assert "🎵 Nhạc của Cảnh 1" in music_text
    assert {"Dùng nhạc chung", "Tắt riêng cảnh này", "Chọn nhạc riêng"}.issubset(set(_plain_labels(music_markup)))
    assert "vid3|scene|scene_01" in _callbacks(music_markup)


def test_video_ai_real_pilot_scene_plan_and_prompt_children_never_fall_back_to_ascii_ui():
    state = _assigned_state()
    state["navigation"]["current_step"] = "scene_plan"

    scene_list = bot.video_uiflow3_open_view(state, "scene_plan_list")
    list_text, list_markup = bot.video_uiflow3_screen_payload(scene_list)
    assert "🎬 Sửa kế hoạch cảnh" in list_text
    assert {"Cảnh 1", "Cảnh 2"}.issubset(set(_plain_labels(list_markup)))
    assert "vid3|view|scene_plan" in _callbacks(list_markup)

    scene_detail = bot.video_uiflow3_open_view(
        state,
        "scene_plan_detail",
        active_scene_id="scene_01",
    )
    scene_text, scene_markup = bot.video_uiflow3_screen_payload(scene_detail)
    assert "🎬 Kế hoạch Cảnh 1" in scene_text
    assert "Ý chính:" in scene_text and "Hành động:" in scene_text and "Kết quả:" in scene_text
    assert "vid3|view|scene_plan_list" in _callbacks(scene_markup)

    state["navigation"]["current_step"] = "prompts"
    prompt_text, prompt_markup = bot.video_uiflow3_screen_payload(state)
    assert "🧠 Rà soát câu lệnh" in prompt_text
    assert {"Câu lệnh từng cảnh", "Tùy chỉnh nâng cao", "Hoàn tất rà soát câu lệnh"}.issubset(
        set(_plain_labels(prompt_markup))
    )

    advanced = bot.video_uiflow3_open_view(state, "prompt_advanced")
    advanced_text, advanced_markup = bot.video_uiflow3_screen_payload(advanced)
    assert "🎥 Tùy chỉnh nâng cao theo cảnh" in advanced_text
    assert "vid3|view|prompts" in _callbacks(advanced_markup)


def test_video_ai_real_pilot_quality_and_location_callbacks_persist_only_inside_pilot():
    user_id = 981001
    context = SimpleNamespace(user_data={})
    state = _ready_prompt_summary_state()
    _save_owned(context, state, user_id)

    _click_visible(context, user_id, "vid3|summary_done", "pilot-quality-review-1")
    _click_visible(context, user_id, "vid3|quality|300", "pilot-quality-1")
    saved = bot.video_uiflow3_state(context)
    assert saved["parent_product"] == "video_ai_real"
    assert saved["format"]["ratio"] == "9:16"
    assert saved["format"]["seconds_per_scene"] == 5
    assert saved["format"]["target_duration_seconds"] == 10
    assert [scene["duration_target"] for scene in saved["scenes"]] == [5, 5]

    location_state = video_uiflow3.set_location_count(_locked_state(), 1)
    location_state["navigation"]["current_step"] = "production_bible"
    location_state = bot.video_uiflow3_open_view(
        location_state,
        "location_detail",
        active_location_id="loc_01",
    )
    _save_owned(context, location_state, user_id)
    _click_visible(
        context,
        user_id,
        "vid3|loc_suggest|loc_01|cafe",
        "pilot-location-1",
    )
    saved_location = bot.video_uiflow3_state(context)
    location = saved_location["bible"]["locations"][0]
    assert location["name"] == "Quán cà phê"
    assert "ánh sáng cửa sổ" in location["description"]
    assert saved_location["ui_view"] == "location_detail"
    assert saved_location["active_location_id"] == "loc_01"


def test_video_ai_real_pilot_snapshot_keeps_real_portrait_ratio_and_scene_math():
    state = video_uiflow3.new_state("video_ai_real", draft_id="pilot-approved-snapshot")
    state = video_uiflow3.set_entry_mode(state, "prompt_video")
    state = video_uiflow3.set_format(
        state,
        ratio="9:16",
        target_duration_seconds=12,
        seconds_per_scene=6,
    )
    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent="Một chai nước hoa xoay nhẹ trong ánh sáng tự nhiên.",
        approved_brief={
            "title": "Nước hoa chân thật",
            "needs_characters": False,
            "needs_locations": False,
            "needs_dialogue": False,
            "needs_voice": False,
            "needs_music": False,
        },
    )
    state = video_uiflow3.lock_content(state)
    state = video_uiflow3.set_character_count(state, 0)
    state = video_uiflow3.set_location_count(state, 0)
    state = video_uiflow3.confirm_scene_count(state, 2)
    state = video_uiflow3.suggest_scene_plan(state)
    state = video_uiflow3.auto_assign_scenes(state)
    state = video_uiflow3.mark_sections_complete(
        state,
        "production_bible",
        "references",
        "continuity",
        "scene_plan",
        "scene_assignment",
        "dialogue",
        "prompts",
        "branding",
        "summary",
    )
    state["navigation"]["current_step"] = "summary"

    assert video_uiflow3.readiness_errors(state) == []
    snapshot = video_uiflow3.approved_snapshot(state)
    assert snapshot["format"]["ratio"] == "9:16"
    assert snapshot["format"]["seconds_per_scene"] == 6
    assert [scene["ratio"] for scene in snapshot["scenes"]] == ["9:16", "9:16"]
    assert [scene["duration_target"] for scene in snapshot["scenes"]] == [6, 6]

    summary_text, summary_markup = bot.video_uiflow3_screen_payload(state)
    assert "Rà soát cuối" in summary_text
    assert "2 cảnh × 6 giây = 12 giây" not in summary_text
    package = video_uiflow3.navigate(state, "package")
    package_text, package_markup = bot.video_uiflow3_screen_payload(package)
    assert "Chọn chất lượng" in package_text
    assert "Cơ bản · 5 giây · 300 Xu" in _plain_labels(package_markup)


def test_video_ai_real_b14_handoff_scopes_owned_references_to_assigned_scenes():
    state = _ready_prompt_summary_state()
    state = video_uiflow3.set_character_count(state, 2)
    state = video_uiflow3.update_character(
        state,
        "char_01",
        display_name="Lan",
        gender="female",
        description="Lan là nhân vật chính của cảnh một.",
    )
    state = video_uiflow3.update_character(
        state,
        "char_02",
        display_name="Minh",
        gender="male",
        description="Minh là nhân vật chính của cảnh hai.",
    )
    state = video_uiflow3.set_location_count(state, 2)
    state = video_uiflow3.update_location(
        state,
        "loc_01",
        name="Quán cà phê",
        description="Quán cà phê sáng, bàn gỗ cạnh cửa sổ.",
    )
    state = video_uiflow3.update_location(
        state,
        "loc_02",
        name="Đường phố",
        description="Đường phố sạch, ánh sáng ban ngày tự nhiên.",
    )
    state = video_uiflow3.assign_scene(
        state,
        "scene_01",
        character_ids=["char_01"],
        location_id="loc_01",
    )
    state = video_uiflow3.assign_scene(
        state,
        "scene_02",
        character_ids=["char_02"],
        location_id="loc_02",
    )
    state = video_uiflow3.add_reference(
        state,
        asset_type="image",
        owner_type="character",
        owner_id="char_01",
        role="front_face",
        telegram_file_id="file-char-01",
        fingerprint="sha256:char-01",
    )
    state = video_uiflow3.add_reference(
        state,
        asset_type="image",
        owner_type="character",
        owner_id="char_02",
        role="front_face",
        telegram_file_id="file-char-02",
        fingerprint="sha256:char-02",
    )
    state = video_uiflow3.add_reference(
        state,
        asset_type="image",
        owner_type="location",
        owner_id="loc_01",
        role="environment",
        telegram_file_id="file-loc-01",
        fingerprint="sha256:loc-01",
    )
    state = video_uiflow3.add_reference(
        state,
        asset_type="image",
        owner_type="location",
        owner_id="loc_02",
        role="environment",
        telegram_file_id="file-loc-02",
        fingerprint="sha256:loc-02",
    )
    state = video_uiflow3.mark_sections_complete(
        state,
        "production_bible",
        "references",
        "continuity",
        "scene_plan",
        "scene_assignment",
        "dialogue",
        "prompts",
        "branding",
        "summary",
    )
    state["navigation"]["dirty_sections"] = []

    plan = bot.video_uiflow3_b14_storyboard_payload(state)
    cards = {item["scene_index"]: item for item in plan["scene_cards"]}

    assert cards[1]["reference_asset_ids"] == ["file-char-01", "file-loc-01"]
    assert cards[2]["reference_asset_ids"] == ["file-char-02", "file-loc-02"]


def test_uiflow3_storyboard_handoff_maps_source_images_in_scene_order():
    state = _ready_product_summary_state("storyboard_prompt")

    plan = bot.video_uiflow3_b14_storyboard_payload(state)
    cards = sorted(plan["scene_cards"], key=lambda item: item["scene_index"])

    assert [card["start_image_file_id"] for card in cards] == [
        "storyboard_prompt-image-1",
        "storyboard_prompt-image-2",
    ]
    assert [card["reference_asset_ids"] for card in cards] == [
        ["storyboard_prompt-image-1"],
        ["storyboard_prompt-image-2"],
    ]


def test_prompt_scene_duration_change_updates_already_materialized_scenes_on_reconfirm():
    state = video_uiflow3.new_state("video_ai_real", draft_id="pilot-duration-reconfirm")
    state = video_uiflow3.set_entry_mode(state, "prompt_video")
    state = video_uiflow3.set_scene_count_preference(state, 2)
    state = video_uiflow3.set_format(
        state,
        ratio="9:16",
        target_duration_seconds=16,
        seconds_per_scene=8,
    )
    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent="Hai cảnh chuyển động nối tiếp nhau.",
        approved_brief={"title": "Hai cảnh nối tiếp"},
    )
    state = video_uiflow3.lock_content(state)
    state = video_uiflow3.confirm_scene_count(state, 2)
    assert [scene["duration_target"] for scene in state["scenes"]] == [8, 8]

    state = video_uiflow3.set_format(
        state,
        target_duration_seconds=12,
        seconds_per_scene=6,
    )
    assert state["format"]["scene_count_confirmed"] is False

    state = video_uiflow3.confirm_scene_count(state, 2)
    assert state["format"]["target_duration_seconds"] == 12
    assert [scene["duration_target"] for scene in state["scenes"]] == [6, 6]
    assert sum(scene["duration_target"] for scene in state["scenes"]) == 12


def test_video_ai_real_pilot_copy_does_not_change_other_products():
    state = video_uiflow3.new_state("script_image_video", draft_id="not-pilot")
    state = video_uiflow3.set_format(state, ratio="9:16", target_duration_seconds=16)
    state["navigation"]["current_step"] = "format"

    text, _markup = bot.video_uiflow3_screen_payload(state)

    assert "ĐỊNH DẠNG MỤC TIÊU" in text
    assert "Khung hình & thời lượng" not in text


def _ready_prompt_summary_state() -> dict:
    state = video_uiflow3.new_state("video_ai_real", draft_id="pilot-commercial-ready")
    state = video_uiflow3.set_entry_mode(state, "prompt_video")
    state = video_uiflow3.set_scene_count_preference(state, 2)
    state = video_uiflow3.set_format(
        state,
        ratio="9:16",
        target_duration_seconds=16,
        seconds_per_scene=8,
    )
    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent="Hai cảnh giới thiệu một sản phẩm theo phong cách chân thật.",
        approved_brief={
            "title": "Giới thiệu sản phẩm chân thật",
            "needs_characters": False,
            "needs_locations": False,
            "needs_dialogue": False,
            "needs_voice": False,
            "needs_music": False,
        },
    )
    state = video_uiflow3.lock_content(state)
    state = video_uiflow3.set_character_count(state, 0)
    state = video_uiflow3.set_location_count(state, 0)
    state = video_uiflow3.confirm_scene_count(state, 2)
    state = video_uiflow3.suggest_scene_plan(state)
    state = video_uiflow3.auto_assign_scenes(state)
    state = video_uiflow3.mark_sections_complete(
        state,
        "production_bible",
        "references",
        "continuity",
        "scene_plan",
        "scene_assignment",
        "dialogue",
        "prompts",
        "branding",
    )
    state["navigation"]["dirty_sections"] = []
    state["navigation"]["current_step"] = "summary"
    return video_uiflow3.normalize_state(state)


def _ready_product_summary_state(
    product: str,
    *,
    complete_source_probe: bool = True,
) -> dict:
    state = video_uiflow3.new_state(product, draft_id=f"route-engine-{product}")
    if product == "storyboard_prompt":
        state = video_uiflow3.set_entry_mode(state, "storyboard_upload")
    if product in {"video_trend", "script_image_video"}:
        state = video_uiflow3.set_source_metadata(
            state,
            text="Noi dung nguon dung de lap ke hoach video.",
        )
    elif product in {"frame_video_local", "storyboard_prompt"}:
        for index in range(1, 3):
            state = video_uiflow3.add_source_asset(
                state,
                asset_type="frame",
                telegram_file_id=f"{product}-image-{index}",
                fingerprint=f"telegram:{product}-image-{index}",
                file_unique_id=f"{product}-unique-{index}",
                file_size=2048 + index,
                mime_type="image/jpeg",
            )
        if product == "storyboard_prompt":
            state = video_uiflow3.set_source_metadata(
                state,
                detected_panel_count=2,
            )
    elif product == "self_shot_scene_change":
        state = video_uiflow3.add_source_asset(
            state,
            asset_type="source_video",
            telegram_file_id="selfshot-source-video",
            fingerprint="telegram:selfshot-source-video",
            file_unique_id="selfshot-source-unique",
            file_size=4096,
            mime_type="video/mp4",
            duration_seconds=8 if complete_source_probe else 0,
            width=720 if complete_source_probe else 0,
            height=1280 if complete_source_probe else 0,
        )
    state = video_uiflow3.set_format(
        state,
        ratio="9:16",
        target_duration_seconds=16,
    )
    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent="Hai canh noi tiep nhau va giu cung mot thong diep.",
        approved_brief={
            "title": "Hai canh noi tiep",
            "needs_characters": False,
            "needs_locations": False,
            "needs_dialogue": False,
            "needs_voice": False,
            "needs_music": False,
        },
    )
    state = video_uiflow3.lock_content(state)
    state = video_uiflow3.set_character_count(state, 0)
    state = video_uiflow3.set_location_count(state, 0)
    state = video_uiflow3.confirm_scene_count(state, 2)
    state = video_uiflow3.suggest_scene_plan(state)
    state = video_uiflow3.auto_assign_scenes(state)
    state = video_uiflow3.mark_sections_complete(
        state,
        "production_bible",
        "references",
        "continuity",
        "scene_plan",
        "scene_assignment",
        "dialogue",
        "prompts",
        "branding",
        "summary",
    )
    state["navigation"]["dirty_sections"] = []
    state["navigation"]["current_step"] = "summary"
    return video_uiflow3.normalize_state(state)


@pytest.mark.parametrize(
    ("product", "kind", "engine_route", "executor"),
    [
        ("video_ai_real", "b14_invoice", "video_ai_canonical", "video_ai_prompt"),
        ("video_trend", "product_tail", "trend_video", "video_trend"),
        ("script_image_video", "product_tail", "script_to_video", "script_to_video"),
        ("storyboard_prompt", "product_tail", "storyboard_to_video", "storyboard_prompt"),
        ("frame_video_local", "frame_video", "frame_video_render", "image_to_video"),
        ("self_shot_scene_change", "selfshot2", "self_shot_scene_change", "self_shot_scene_change"),
        ("multi_scene_film", "planning_only", "multi_scene_film", "multi_scene_film"),
    ],
)
def test_uiflow3_route_engine_adapter_matrix_is_product_specific(
    product,
    kind,
    engine_route,
    executor,
):
    route = bot.video_uiflow3_execution_adapter(
        video_uiflow3.new_state(product, draft_id=f"route-{product}")
    )

    assert route["kind"] == kind
    assert route["product_type"] == product
    assert route["engine_route"] == engine_route
    assert route["executor_product_type"] == executor


@pytest.mark.parametrize(
    ("product", "engine_route", "executor"),
    [
        ("video_trend", "trend_video", "video_trend"),
        ("script_image_video", "script_to_video", "script_to_video"),
        ("storyboard_prompt", "storyboard_to_video", "storyboard_prompt"),
    ],
)
def test_uiflow3_shared_tail_handoff_keeps_the_selected_product(
    product,
    engine_route,
    executor,
):
    state = _ready_product_summary_state(product)
    tail = bot.video_uiflow3_build_tail_state(state)
    contract = bot.video_tail9.commercial_contract(product)

    assert tail["video_product_type"] == product
    assert tail["video_flow_owner"] == "uiflow3"
    assert tail["engine_route"] == engine_route
    assert contract["executor_product_type"] == executor
    assert tail["video_session_id"] == state["draft_id"]
    assert tail["scene_count"] == 2
    assert tail["summary_status"] == "ready"
    assert tail["review_status"] == "ready"


def test_uiflow3_shared_tail_owner_wins_over_a_stale_video_edit_session(monkeypatch):
    user_id = 981099
    context = SimpleNamespace(user_data={})
    state = _ready_product_summary_state("video_trend")
    _save_owned(context, state, user_id)
    rendered: list[tuple[str, str]] = []

    monkeypatch.setattr(bot, "get_video_editor_pending", lambda _uid: {
        "edit_mode": "manual_edit",
        "source_file_id": "old-video",
        "inspection_complete": True,
        "flow_owner": "video_edit",
        "product_type": bot.video_editengine1.PRODUCT_TYPE,
    })
    monkeypatch.setattr(bot, "get_video_session", lambda _uid: {
        "product_id": bot.video_editengine1.PRODUCT_TYPE,
        "draft": {"flow_owner": "video_edit"},
    })

    async def render_tail(_query, _user_id, _context, screen):
        tail, owner, host = bot.video_tail9_context(_user_id, _context)
        rendered.append((screen, owner, tail.get("video_product_type"), host.get("draft_id")))
        return True

    monkeypatch.setattr(bot, "video_tail9_render", render_tail)
    _click_visible(context, user_id, "vid3|summary_done", "tail-stale-video-edit")

    assert rendered == [("quality", "uiflow3", "video_trend", state["draft_id"])]


def test_uiflow3_shared_tail_resume_reclaims_owner_after_leaving_the_flow(monkeypatch):
    user_id = 981098
    context = SimpleNamespace(user_data={})
    state = _ready_product_summary_state("video_trend")
    _save_owned(context, state, user_id)
    rendered: list[tuple[str, str]] = []

    monkeypatch.setattr(bot, "get_video_editor_pending", lambda _uid: {
        "edit_mode": "manual_edit",
        "source_file_id": "old-video",
        "inspection_complete": True,
        "flow_owner": "video_edit",
        "product_type": bot.video_editengine1.PRODUCT_TYPE,
    })
    monkeypatch.setattr(bot, "get_video_session", lambda _uid: {
        "product_id": bot.video_editengine1.PRODUCT_TYPE,
        "draft": {"flow_owner": "video_edit"},
    })

    async def render_tail(_query, _user_id, _context, screen):
        tail, owner, _host = bot.video_tail9_context(_user_id, _context)
        rendered.append((screen, f"{owner}:{tail.get('video_product_type')}"))
        return True

    monkeypatch.setattr(bot, "video_tail9_render", render_tail)
    _click_visible(context, user_id, "vid3|summary_done", "tail-resume-owner-1")
    bot.deactivate_video_uiflow3_pending_input(context)
    resume = _PilotQuery(user_id, "vid3|resume", "tail-resume-owner-2")
    asyncio.run(bot.handle_video_uiflow3_callback(SimpleNamespace(callback_query=resume), context))

    assert rendered == [
        ("quality", "uiflow3:video_trend"),
        ("quality", "uiflow3:video_trend"),
    ]


def test_uiflow3_frame_handoff_reuses_real_images_and_exact_summary_back():
    state = _ready_product_summary_state("frame_video_local")
    frame = bot.video_uiflow3_build_frame_state(state)
    keyboard = bot.frame_video_quality_keyboard(frame)
    callbacks = _callbacks(keyboard)

    assert frame["commercial_flow_version"] == "framevideo3"
    assert frame["uiflow3_draft_id"] == state["draft_id"]
    assert frame["uiflow3_config_hash"] == video_uiflow3.approved_snapshot(state)["config_hash"]
    assert [item["file_id"] for item in frame["photos"]] == [
        "frame_video_local-image-1",
        "frame_video_local-image-2",
    ]
    assert frame["ratio"] == "9x16"
    assert frame["duration_confirmed"] is True
    assert "vid3|resume" in callbacks
    assert "Hoàn tất chọn chất lượng" in _plain_labels(keyboard)


def test_uiflow3_selfshot_handoff_requires_a_real_source_probe():
    incomplete = bot.video_uiflow3_build_selfshot2_handoff(
        _ready_product_summary_state(
            "self_shot_scene_change",
            complete_source_probe=False,
        )
    )
    complete = bot.video_uiflow3_build_selfshot2_handoff(
        _ready_product_summary_state("self_shot_scene_change")
    )

    assert incomplete["ok"] is False
    assert incomplete["blocker"] == "source_video_probe_missing"
    assert complete["ok"] is True
    assert complete["draft"]["product_id"] == "self_shot_scene_change"
    assert complete["draft"]["source_video"]["file_id"] == "selfshot-source-video"
    assert complete["draft"]["source_analysis"]["duration_seconds"] == 8
    assert complete["draft"]["source_analysis"]["width"] == 720
    assert complete["draft"]["source_analysis"]["height"] == 1280


def test_uiflow3_required_sources_fail_closed_before_approval():
    trend = video_uiflow3.new_state("video_trend", draft_id="required-trend")
    script = video_uiflow3.new_state("script_image_video", draft_id="required-script")
    frame = video_uiflow3.add_source_asset(
        video_uiflow3.new_state("frame_video_local", draft_id="required-frame"),
        asset_type="frame",
        telegram_file_id="only-one-frame",
        fingerprint="telegram:only-one-frame",
    )
    storyboard = video_uiflow3.set_entry_mode(
        video_uiflow3.new_state("storyboard_prompt", draft_id="required-storyboard"),
        "storyboard_upload",
    )
    selfshot = video_uiflow3.new_state(
        "self_shot_scene_change",
        draft_id="required-selfshot",
    )

    assert "source_content_required" in video_uiflow3.readiness_errors(trend)
    assert "source_content_required" in video_uiflow3.readiness_errors(script)
    assert "frame_images_required" in video_uiflow3.readiness_errors(frame)
    assert "storyboard_images_required" in video_uiflow3.readiness_errors(storyboard)
    assert "source_video_required" in video_uiflow3.readiness_errors(selfshot)


@pytest.mark.parametrize("product", ["video_trend", "script_image_video", "storyboard_prompt"])
def test_uiflow3_summary_done_opens_the_selected_products_real_tail(
    monkeypatch,
    product,
):
    user_id = 981100
    context = SimpleNamespace(user_data={})
    _save_owned(context, _ready_product_summary_state(product), user_id)
    rendered: list[tuple[str, str]] = []

    async def render_tail(_query, _user_id, _context, screen):
        tail, owner, _host = bot.video_tail9_context(_user_id, _context)
        rendered.append((screen, f"{owner}:{tail.get('video_product_type')}"))
        return True

    monkeypatch.setattr(bot, "video_tail9_render", render_tail)

    _click_visible(context, user_id, "vid3|summary_done", f"tail-{product}")

    assert rendered == [("quality", f"uiflow3:{product}")]
    saved = bot.video_uiflow3_state(context)
    assert saved[bot.VIDEO_TAIL9_STATE_KEY]["video_product_type"] == product
    assert saved["side_effects"] == {
        "provider_calls": 0,
        "jobs": 0,
        "outbox": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }


@pytest.mark.parametrize(
    ("product", "engine_route", "executor"),
    [
        ("video_trend", "trend_video", "video_trend"),
        ("script_image_video", "script_to_video", "script_to_video"),
        ("storyboard_prompt", "storyboard_to_video", "storyboard_prompt"),
    ],
)
def test_uiflow3_shared_tail_invoice_session_preserves_engine_contract(
    monkeypatch,
    product,
    engine_route,
    executor,
):
    user_id = 981101
    state = _ready_product_summary_state(product)
    tail = bot.video_uiflow3_build_tail_state(state)
    tail["quality_tier_id"] = "400"
    tail["package_id"] = "product_video_400"
    tail["capability_snapshot"] = {"ok": True, "verified": True}
    monkeypatch.setattr(bot, "save_video_session", lambda _uid, session: session)

    _prepared, session = bot.video_uiflow3_prepare_b14_session(
        user_id,
        state,
        tail_state=tail,
        require_attestation=False,
    )
    draft = dict(session.get("draft") or {})

    assert session["product_id"] == product
    assert draft["product_id"] == product
    assert draft["video_tail_engine_route"] == engine_route
    assert draft["video_tail_executor_product_type"] == executor
    assert bot.video_engine_product_type_for_session(session) == executor
    assert draft["b14_storyboard_plan"]["prompt_context"]["public_product_type"] == product
    assert draft["b14_storyboard_plan"]["prompt_context"]["engine_route"] == engine_route
    assert draft["uiflow3_invoice_attestation_required"] is False
    assert draft["provider_called"] is False
    assert draft["job_created"] is False
    assert draft["outbox_created"] is False
    assert draft["xu_charged"] == 0


def test_uiflow3_summary_done_opens_the_real_frame_quality_screen(monkeypatch):
    user_id = 981102
    context = SimpleNamespace(user_data={})
    _save_owned(context, _ready_product_summary_state("frame_video_local"), user_id)
    persisted: list[dict] = []
    monkeypatch.setattr(
        bot,
        "set_frame_video_state",
        lambda _uid, state: persisted.append(dict(state)) or state,
    )

    query = _click_visible(context, user_id, "vid3|summary_done", "frame-tail-01")

    assert persisted
    assert persisted[-1]["commercial_flow_version"] == "framevideo3"
    assert persisted[-1]["step"] == "quality"
    assert [item["file_id"] for item in persisted[-1]["photos"]] == [
        "frame_video_local-image-1",
        "frame_video_local-image-2",
    ]
    assert "Chọn chất lượng video" in query.edits[-1]["text"]
    assert "vid3|resume" in _callbacks(query.edits[-1]["reply_markup"])


def test_uiflow3_summary_done_opens_selfshot_source_analysis_with_exact_back(monkeypatch):
    user_id = 981103
    context = SimpleNamespace(user_data={})
    _save_owned(context, _ready_product_summary_state("self_shot_scene_change"), user_id)
    rendered: list[tuple[str, dict]] = []

    def save_draft(_uid, draft, *, step=""):
        rendered.append((step, dict(draft)))
        return {"draft": dict(draft), "current_step": step}

    async def render_selfshot(_query, _uid, screen, *, draft=None):
        rendered.append((screen, dict(draft or {})))
        return True

    monkeypatch.setattr(bot, "save_video_selfshot2_draft", save_draft)
    monkeypatch.setattr(bot, "video_selfshot2_render", render_selfshot)

    _click_visible(context, user_id, "vid3|summary_done", "selfshot-tail-01")

    assert [item[0] for item in rendered] == ["selfshot2:analysis", "analysis"]
    assert rendered[-1][1]["uiflow3_return_to"] == "vid3|resume"
    assert rendered[-1][1]["source_analysis"]["source_hash"]


def test_uiflow3_shared_tail_quality_back_returns_to_the_same_draft_summary():
    user_id = 981104
    context = SimpleNamespace(user_data={})
    state = _ready_product_summary_state("video_trend")
    snapshot = video_uiflow3.approved_snapshot(state)
    state["legacy_compat"]["approved_snapshot"] = snapshot
    tail = bot.video_uiflow3_build_tail_state(state)
    tail["status_stage"] = "quality"
    state[bot.VIDEO_TAIL9_STATE_KEY] = tail
    _save_owned(context, state, user_id)
    bot.claim_video_uiflow3_tail_owner(context, state)
    query = _PilotQuery(
        user_id,
        "video_tail|quality|back",
        "tail-quality-back-01",
    )
    update = SimpleNamespace(callback_query=query)

    asyncio.run(bot.safe_mode_callback_guard(update, context))
    asyncio.run(
        bot.handle_video_tail_callback(
            update,
            context,
        )
    )

    saved = bot.video_uiflow3_state(context)
    assert saved["parent_product"] == "video_trend"
    assert saved["draft_id"] == "route-engine-video_trend"
    assert saved["navigation"]["current_step"] == "summary"
    assert "RÀ SOÁT KẾ HOẠCH VIDEO" in query.edits[-1]["text"]


def test_uiflow3_selfshot_analysis_back_returns_to_the_same_draft(monkeypatch):
    handoff = bot.video_uiflow3_build_selfshot2_handoff(
        _ready_product_summary_state("self_shot_scene_change")
    )
    captured: list[dict] = []

    monkeypatch.setattr(
        bot,
        "save_video_selfshot2_draft",
        lambda _uid, draft, *, step="": {"draft": dict(draft), "current_step": step},
    )

    async def edit(_target, text, **kwargs):
        captured.append({"text": text, **kwargs})
        return True

    monkeypatch.setattr(bot, "safe_edit_or_send", edit)

    asyncio.run(
        bot.video_selfshot2_render(
            SimpleNamespace(),
            981105,
            "analysis",
            draft=handoff["draft"],
        )
    )

    assert captured
    assert "vid3|resume" in _callbacks(captured[-1]["reply_markup"])
    assert "menu|main_video" in _callbacks(captured[-1]["reply_markup"])


def test_video_ai_real_prompt_model_catalog_uses_verified_seconds_and_triple_fallback_cost():
    catalog = bot.video_ai_real_prompt_model_catalog()
    by_key = {item["key"]: item for item in catalog}

    assert list(by_key) == [
        "grok3_5",
        "grok3_10",
        "veo31_fast_8",
        "veo31_pro_8",
    ]
    assert (by_key["grok3_5"]["seconds"], by_key["grok3_5"]["unit_xu"]) == (5, 190)
    assert (by_key["grok3_10"]["seconds"], by_key["grok3_10"]["unit_xu"]) == (10, 380)
    assert (by_key["veo31_fast_8"]["seconds"], by_key["veo31_fast_8"]["unit_xu"]) == (8, 70)
    assert (by_key["veo31_pro_8"]["seconds"], by_key["veo31_pro_8"]["unit_xu"]) == (8, 340)
    grok_10_shop = next(
        item
        for item in by_key["grok3_10"]["provider_costs"]
        if item["provider"] == "shopaikey"
    )
    assert grok_10_shop["catalog_model"] == "grok-video-3-10s"
    assert grok_10_shop["model"] == "grok-video-3"
    assert grok_10_shop["request_metadata"] == {
        "duration": 10,
        "resolution": "720P",
    }
    assert all(item["description"] and item["quality"] for item in catalog)
    assert all(item["price_multiplier"] == 3 for item in catalog)
    assert {
        key: item["provider_priority"]
        for key, item in by_key.items()
    } == {
        "grok3_5": ["shopaikey", "key4u"],
        "grok3_10": ["shopaikey", "key4u"],
        "veo31_fast_8": ["key4u", "shopaikey"],
        "veo31_pro_8": ["key4u", "shopaikey"],
    }
    assert {
        key: item["pricing_provider"]
        for key, item in by_key.items()
    } == {
        "grok3_5": "key4u",
        "grok3_10": "key4u",
        "veo31_fast_8": "shopaikey",
        "veo31_pro_8": "shopaikey",
    }
    for item in catalog:
        cost_by_provider = {
            cost["provider"]: cost["cost_vnd"]
            for cost in item["provider_costs"]
        }
        priority_costs = [
            cost_by_provider[provider]
            for provider in item["provider_priority"]
        ]
        assert priority_costs == sorted(priority_costs)
        assert item["pricing_cost_vnd"] == max(cost_by_provider.values())
    assert all(item["unit_xu"] % 10 == 0 for item in catalog)
    assert all("trial" not in item["key"] for item in catalog)

    assert bot.video_ai_real_round_sale_xu(81) == 80
    assert bot.video_ai_real_round_sale_xu(82) == 80
    assert bot.video_ai_real_round_sale_xu(83) == 90
    assert bot.video_ai_real_round_sale_xu(84) == 90


def test_video_ai_real_image_model_catalog_uses_verified_triple_fallback_cost():
    catalog = bot.video_ai_real_pricing.image_model_catalog()
    by_key = {item["key"]: item for item in catalog}

    assert list(by_key) == ["grok_image", "grok_image_pro"]
    assert by_key["grok_image"]["unit_xu"] == 20
    assert by_key["grok_image_pro"]["unit_xu"] == 70
    assert by_key["grok_image"]["pricing_provider"] == "shopaikey"
    assert by_key["grok_image"]["provider_costs"] == [
        {
            "provider": "shopaikey",
            "model": "grok-imagine-image",
            "usd_per_image": 0.208,
            "usd_to_vnd": 3250,
            "cost_vnd": 676,
            "pricing_basis": "mỗi ảnh",
            "source_url": "https://shopaikey.com/models",
            "checked_on": "2026-08-09",
        },
        {
            "provider": "key4u",
            "model": "grok-imagine-image",
            "usd_per_image": 0.208,
            "usd_to_vnd": 3000,
            "cost_vnd": 624,
            "pricing_basis": "mỗi ảnh",
            "source_url": "https://key4u.vn/models",
            "checked_on": "2026-08-09",
        },
    ]
    assert all(item["provider_priority"] == ["key4u", "shopaikey"] for item in catalog)
    for item in catalog:
        cost_by_provider = {
            cost["provider"]: cost["cost_vnd"]
            for cost in item["provider_costs"]
        }
        assert item["pricing_cost_vnd"] == max(cost_by_provider.values())
    assert all(item["unit_xu"] % 10 == 0 for item in catalog)


def test_video_ai_real_music_catalog_uses_verified_triple_fallback_cost():
    catalog = bot.video_ai_real_pricing.music_model_catalog()

    assert len(catalog) == 1
    music = catalog[0]
    assert music["key"] == "suno_music"
    assert music["unit"] == "track"
    assert music["unit_xu"] == 80
    assert music["pricing_provider"] == "shopaikey"
    assert music["provider_priority"] == ["key4u", "shopaikey"]
    assert music["provider_costs"] == [
        {
            "provider": "shopaikey",
            "model": "suno_music",
            "usd_per_track": 0.8,
            "usd_to_vnd": 3250,
            "cost_vnd": 2600,
            "pricing_basis": "mỗi lần tạo track",
            "source_url": "https://shopaikey.com/models",
            "checked_on": "2026-08-09",
        },
        {
            "provider": "key4u",
            "model": "suno_music_open",
            "usd_per_track": 0.24,
            "usd_to_vnd": 3000,
            "cost_vnd": 720,
            "pricing_basis": "mỗi lần tạo track",
            "source_url": "https://key4u.vn/models",
            "checked_on": "2026-08-09",
        },
    ]


def _profile_content_lock_state(profile_key: str) -> dict:
    profile = dict(bot.video_profile_catalog.PROFILE_BY_KEY[profile_key])
    state = video_uiflow3.new_state("video_ai_real", draft_id=f"pilot-context-{profile_key}")
    state = video_uiflow3.set_entry_mode(state, "prompt_video")
    state = video_uiflow3.set_scene_count_preference(state, 1)
    state = video_uiflow3.set_format(state, ratio="9:16", target_duration_seconds=8)
    return video_uiflow3.set_content_candidate(
        state,
        source="content_catalog",
        profile_id=profile_key,
        original_intent=str(profile["description"]),
        approved_brief={
            "title": str(profile["public_name"]),
            "story_formula": list(profile["default_scene_pattern"]),
        },
    )


def test_each_32_content_profile_uses_its_own_context_suggestions():
    sales = _profile_content_lock_state("sales_ads")
    history = _profile_content_lock_state("history_culture_mythology")

    sales_text, sales_markup = bot.video_uiflow3_screen_payload(sales)
    history_text, history_markup = bot.video_uiflow3_screen_payload(history)
    sales_labels = set(_plain_labels(sales_markup))
    history_labels = set(_plain_labels(history_markup))

    assert "Bán hàng / quảng cáo" in sales_text
    assert "Lịch sử / văn hóa / thần thoại" in history_text
    assert {"Mở: Hook vấn đề", "Phát triển: Bằng chứng", "Kết: Lời kêu gọi hành động"} <= sales_labels
    assert {"Mở: Bối cảnh", "Phát triển: Diễn biến", "Kết: Ý nghĩa"} <= history_labels
    assert "Bán hàng tự nhiên" not in history_labels
    assert sales_labels != history_labels

    prompt_signatures = set()
    for profile in bot.video_profile_catalog.PROFILE_SEEDS:
        profile_key = str(profile["profile_key"])
        state = _profile_content_lock_state(profile_key)
        suggestions = bot.video_ai_real_profile_context_prompts(state)
        pattern = list(profile["default_scene_pattern"])

        assert [item["key"] for item in suggestions] == [
            "opening",
            "development",
            "ending",
        ]
        assert suggestions[0]["label"] == f"Mở: {pattern[0]}"
        assert suggestions[1]["label"] == f"Phát triển: {pattern[len(pattern) // 2]}"
        assert suggestions[2]["label"] == f"Kết: {pattern[-1]}"
        assert all(item["profile_key"] == profile_key for item in suggestions)
        prompt_signatures.add(tuple(item["guidance"] for item in suggestions))

    assert len(prompt_signatures) == len(bot.video_profile_catalog.PROFILE_SEEDS) == 32


def test_video_ai_real_content_lock_offers_profile_context_suggestions_before_bible():
    user_id = 981021
    context = SimpleNamespace(user_data={})
    state = _profile_content_lock_state("sales_ads")
    _save_owned(context, state, user_id)

    text, markup = bot.video_uiflow3_screen_payload(state)
    assert "Gợi ý theo loại nội dung" in text
    assert {"Mở: Hook vấn đề", "Phát triển: Bằng chứng", "Kết: Lời kêu gọi hành động"}.issubset(
        set(_plain_labels(markup))
    )

    _click_visible(context, user_id, "vid3|context|opening", "pilot-context-prompt-1")
    selected = bot.video_uiflow3_state(context)
    assert selected["navigation"]["current_step"] == "production_bible"
    assert selected["content"]["locked"] is True
    assert "hook vấn đề" in selected["content"]["original_intent"].lower()


def test_video_ai_real_audio_addons_are_compact_finishable_and_return_to_assignment():
    state = _ready_prompt_summary_state()
    state["navigation"]["current_step"] = "scene_assignment"
    state["capabilities"].update({
        "whole_video_music": True,
        "per_scene_music": True,
        "scene_sfx": True,
    })
    state = bot.video_uiflow3_open_view(state, "audio_options")

    text, markup = bot.video_uiflow3_screen_payload(state)
    labels = _plain_labels(markup)
    assert "Âm thanh và phụ đề" in text
    assert {
        "Nhạc",
        "Phụ đề",
        "Lồng tiếng",
        "Hiệu ứng âm thanh",
        "Hoàn tất thiết lập âm thanh và phụ đề",
    }.issubset(set(labels))
    assert all(len(row) <= 2 for row in markup.inline_keyboard)
    assert "vid3|view|scene_assignment" in _callbacks(markup)


def test_video_ai_real_multi_field_sections_keep_finish_while_voice_is_single_choice():
    state = _assigned_state()
    state["navigation"]["current_step"] = "production_bible"

    character_list = bot.video_uiflow3_open_view(state, "character_list")
    _text, character_markup = bot.video_uiflow3_screen_payload(character_list)
    assert "Hoàn tất khai báo nhân vật" in _plain_labels(character_markup)
    assert "vid3|view|production_bible" in _callbacks(character_markup)

    location_list = bot.video_uiflow3_open_view(state, "location_list")
    _text, location_markup = bot.video_uiflow3_screen_payload(location_list)
    assert "Hoàn tất khai báo bối cảnh" in _plain_labels(location_markup)
    assert "vid3|view|production_bible" in _callbacks(location_markup)

    voice = bot.video_uiflow3_open_view(
        state,
        "voice_select",
        active_character_id="char_01",
        ui_return_callback="vid3|character|char_01",
    )
    _text, voice_markup = bot.video_uiflow3_screen_payload(voice)
    assert "Hoàn thành chọn giọng" not in _plain_labels(voice_markup)
    assert "vid3|character|char_01" in _callbacks(voice_markup)

    state["navigation"]["current_step"] = "scene_assignment"
    audio = bot.video_uiflow3_open_view(state, "audio_options")
    _text, audio_markup = bot.video_uiflow3_screen_payload(audio)
    assert "Hoàn tất thiết lập âm thanh và phụ đề" in _plain_labels(audio_markup)
    assert "vid3|view|scene_assignment" in _callbacks(audio_markup)


def test_video_ai_real_voice_choice_returns_to_the_exact_character_parent():
    user_id = 981031
    context = SimpleNamespace(user_data={})
    state = _assigned_state()
    state["navigation"]["current_step"] = "production_bible"
    state = bot.video_uiflow3_open_view(
        state,
        "voice_select",
        active_character_id="char_01",
        ui_return_callback="vid3|character|char_01",
    )
    _save_owned(context, state, user_id)

    _click_visible(context, user_id, "vid3|voice|char_01|vf1", "pilot-voice-auto-parent-1")

    saved = bot.video_uiflow3_state(context)
    assert saved.get("ui_view") == "character_detail"
    assert saved.get("active_character_id") == "char_01"
    assert saved["bible"]["characters"][0]["voice_id"] == bot.VIDEO_UIFLOW3_VOICE_ALIASES["vf1"]


@pytest.mark.parametrize(
    ("view", "callback", "field", "expected"),
    [
        ("audio_subtitle", "vid3|audio_set|subtitle|script", "subtitle_mode", "script"),
        ("audio_dubbing", "vid3|audio_set|dubbing|browser", "dubbing_mode", "browser"),
        ("audio_sfx", "vid3|audio_set|sfx|library", "sfx_mode", "library"),
    ],
)
def test_video_ai_real_single_choice_audio_returns_to_audio_hub(view, callback, field, expected):
    user_id = 981032
    context = SimpleNamespace(user_data={})
    state = _ready_prompt_summary_state()
    state["navigation"]["current_step"] = "scene_assignment"
    state = bot.video_uiflow3_open_view(state, view)
    _save_owned(context, state, user_id)

    _click_visible(context, user_id, callback, f"pilot-audio-auto-parent-{view}")

    saved = bot.video_uiflow3_state(context)
    assert saved.get("ui_view") == "audio_options"
    assert saved["audio"][field] == expected


def test_video_ai_real_skip_branding_advances_to_summary_without_an_extra_click():
    user_id = 981033
    context = SimpleNamespace(user_data={})
    state = _ready_prompt_summary_state()
    state["navigation"]["current_step"] = "branding"
    state = bot.video_uiflow3_open_view(state, "")
    _save_owned(context, state, user_id)

    _click_visible(context, user_id, "vid3|brand|none", "pilot-brand-skip-auto-1")

    saved = bot.video_uiflow3_state(context)
    assert saved["navigation"]["current_step"] == "summary"
    assert saved.get("ui_view") in {None, ""}
    assert saved["branding"] == {}


@pytest.mark.parametrize("panel", ["scene_location", "scene_ambient", "scene_music"])
def test_video_ai_real_single_choice_scene_panels_return_to_their_exact_parent(panel):
    user_id = 981035
    context = SimpleNamespace(user_data={})
    state = _assigned_state()
    state["navigation"]["current_step"] = "scene_assignment"

    if panel == "scene_location":
        state = bot.video_uiflow3_open_view(state, panel, active_scene_id="scene_01")
        callback = "vid3|scene_loc_set|scene_01|loc_02"
        expected_view = "scene_detail"
    elif panel == "scene_ambient":
        state = bot.video_uiflow3_open_view(state, panel, active_scene_id="scene_01")
        callback = "vid3|scene_ambient_set|scene_01|cafe"
        expected_view = "scene_entities"
    else:
        state = bot.video_uiflow3_open_view(state, "audio_music_scenes")
        _save_owned(context, state, user_id)
        _click_visible(context, user_id, "vid3|scene_music|scene_01", "pilot-scene-choice-parent-open")
        callback = "vid3|scene_music_set|scene_01|off"
        expected_view = "audio_music_scenes"
        state = bot.video_uiflow3_state(context)

    _save_owned(context, state, user_id)
    _click_visible(context, user_id, callback, f"pilot-scene-choice-parent-{panel}")

    saved = bot.video_uiflow3_state(context)
    assert saved.get("ui_view") == expected_view
    assert saved.get("active_scene_id") in {None, "", "scene_01"}


def test_video_ai_real_multi_select_panels_use_finish_labels_for_the_exact_parent():
    state = _assigned_state()
    state = video_uiflow3.add_product(
        state,
        name="Sản phẩm A",
        category="Mẫu",
        description="Sản phẩm cần giữ hình dáng.",
    )
    bible_state = video_uiflow3.normalize_state(state)
    bible_state["navigation"]["current_step"] = "production_bible"
    scene_state = video_uiflow3.normalize_state(state)
    scene_state["navigation"]["current_step"] = "scene_assignment"
    panels = [
        (bot.video_uiflow3_open_view(bible_state, "continuity"), "Hoàn tất chọn yếu tố nhất quán", "vid3|view|production_bible"),
        (bot.video_uiflow3_open_view(scene_state, "scene_cast", active_scene_id="scene_01"), "Hoàn tất chọn nhân vật cho cảnh", "vid3|scene|scene_01"),
        (
            bot.video_uiflow3_open_view(
                bible_state,
                "entity_scene_assign",
                assignment_owner_type="character",
                assignment_owner_id="char_01",
            ),
            "Hoàn tất chọn cảnh áp dụng",
            "vid3|character|char_01",
        ),
        (bot.video_uiflow3_open_view(scene_state, "scene_sfx", active_scene_id="scene_01"), "Hoàn tất chọn hiệu ứng âm thanh", "vid3|scene_entities|scene_01"),
        (bot.video_uiflow3_open_view(scene_state, "scene_product", active_scene_id="scene_01"), "Hoàn tất chọn sản phẩm cho cảnh", "vid3|scene_entities|scene_01"),
    ]

    for panel_state, finish_label, parent_callback in panels:
        _text, markup = bot.video_uiflow3_screen_payload(panel_state)
        assert finish_label in _plain_labels(markup)
        assert parent_callback in _callbacks(markup)


def test_video_ai_real_prompt_review_shows_detailed_scene_prompt_and_exact_parent_back():
    state = _ready_prompt_summary_state()
    state["navigation"]["current_step"] = "prompts"
    state = bot.video_uiflow3_open_view(state, "prompt_scenes")

    text, markup = bot.video_uiflow3_screen_payload(state)
    assert "Câu lệnh từng cảnh" in text
    assert {"Cảnh 1", "Cảnh 2", "Hoàn tất rà soát câu lệnh từng cảnh"}.issubset(
        set(_plain_labels(markup))
    )
    assert "vid3|prompt_scene|scene_01" in _callbacks(markup)
    assert "vid3|view|prompts" in _callbacks(markup)

    detail = bot.video_uiflow3_open_view(
        state,
        "prompt_scene_detail",
        active_scene_id="scene_01",
    )
    detail_text, detail_markup = bot.video_uiflow3_screen_payload(detail)
    assert "Câu lệnh chi tiết · Cảnh 1" in detail_text
    assert "Chủ thể" in detail_text
    assert "Hành động" in detail_text
    assert "Bối cảnh" in detail_text
    assert "Sửa câu lệnh của cảnh" in _plain_labels(detail_markup)
    assert "vid3|view|prompt_scenes" in _callbacks(detail_markup)


def test_video_ai_real_quote_includes_each_paid_addon_once_and_exact_total():
    state = _ready_prompt_summary_state()
    state = bot.video_ai_real_apply_prompt_model(state, "grok3_10")
    state["audio"].update({
        "music_scope": "per_scene",
        "music_source": "ai",
        "subtitle_mode": "auto",
        "dubbing_mode": "default_ai",
        "sfx_mode": "ai",
    })

    quote = bot.video_ai_real_prompt_quote(state)
    assert quote["scene_count"] == 2
    assert quote["total_duration_seconds"] == 20
    assert quote["base_xu"] == 760
    assert quote["addons_xu"] == 610
    assert quote["total_xu"] == 1370
    assert quote["estimated_vnd"] == 137000
    assert [(item["key"], item["price_xu"]) for item in quote["addons"]] == [
        ("music_ai", 160),
        ("subtitle_auto", 120),
        ("dubbing_default", 250),
        ("sfx_ai", 80),
    ]


def test_video_ai_real_quote_confirmation_reaches_truthful_status_with_exact_back_stack():
    user_id = 981022
    context = SimpleNamespace(user_data={})
    _save_owned(context, _ready_prompt_summary_state(), user_id)

    _click_visible(context, user_id, "vid3|summary_done", "pilot-commercial-review-1")
    quality_query = _click_visible(context, user_id, "vid3|quality|400", "pilot-commercial-1")
    selected = bot.video_uiflow3_state(context)
    assert selected["format"]["seconds_per_scene"] == 8
    assert selected["format"]["target_duration_seconds"] == 16

    session = bot.get_video_session(user_id)
    draft = dict(session.get("draft") or {})
    assert session["current_step"] == "b14_invoice"
    assert draft["b14_scene_count"] == 2
    assert draft["b14_quality_xu"] == 400
    assert draft["b14_storyboard_plan"]["scene_cards"]
    assert draft["prompt_bundle"]["video_prompts"]
    assert selected["side_effects"] == {
        "provider_calls": 0,
        "jobs": 0,
        "outbox": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }
    invoice_callbacks = _callbacks(quality_query.edits[-1]["reply_markup"])
    assert "Xác nhận báo giá và tạo video" in _plain_labels(
        quality_query.edits[-1]["reply_markup"]
    )
    confirm_callback = next(
        value for value in invoice_callbacks
        if value.startswith("vproduct|b14_confirm|")
    )
    assert re.fullmatch(r"vproduct\|b14_confirm\|[a-f0-9]{12}", confirm_callback)
    assert "vid3|invoice_back" in invoice_callbacks
    assert "vid3|confirmation_submit" not in invoice_callbacks
    assert bot.video_route_expected_handler(confirm_callback) == (
        "handle_product_video_public_confirm_callback"
    )

    invoice_markup = quality_query.edits[-1]["reply_markup"]
    invoice_back_wire = next(
        str(button.callback_data or "")
        for row in invoice_markup.inline_keyboard
        for button in row
        if _logical_callback(str(button.callback_data or "")) == "vid3|invoice_back"
    )
    back_query = _PilotQuery(user_id, invoice_back_wire, "pilot-commercial-back-1")
    asyncio.run(
        bot.handle_video_uiflow3_callback(
            SimpleNamespace(callback_query=back_query),
            context,
        )
    )

    returned = bot.video_uiflow3_state(context)
    assert returned["navigation"]["current_step"] == "package"
    assert returned["side_effects"] == {
        "provider_calls": 0,
        "jobs": 0,
        "outbox": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }


def test_video_ai_real_real_invoice_preserves_selected_scene_duration():
    user_id = 981036
    state = bot.video_ai_real_apply_quality_product(
        _ready_prompt_summary_state(),
        300,
    )

    _prepared, session = bot.video_uiflow3_prepare_b14_session(user_id, state)
    invoice = bot.video_b14_invoice_for_session(session, user_id)

    assert invoice["scene_seconds"] == 5
    assert invoice["duration_seconds"] == 10
    assert (session.get("draft") or {})["b14_scene_seconds"] == 5


def test_video_ai_real_b14_handoff_keeps_logo_image_and_watermark_text():
    user_id = 981038
    state = _ready_prompt_summary_state()
    state["branding"] = {
        "logo": {
            "telegram_file_id": "uiflow3-logo-file",
            "position": "bottom_left",
        },
        "watermark": {
            "text": "TOAN AAS",
            "position": "top_right",
        },
    }
    state = bot.video_ai_real_apply_quality_product(state, 300)

    _prepared, session = bot.video_uiflow3_prepare_b14_session(user_id, state)
    material = bot.product_video_logo_material_from_session(session)
    addon_plan = bot.video_b14_addon_plan_from_session(session)

    assert material["logo_enabled"] is True
    assert material["logo_file_id"] == "uiflow3-logo-file"
    assert material["logo_position"] == "bottom_left"
    assert addon_plan["logo_enabled"] is True
    assert addon_plan["logo_source"] == "text"
    assert addon_plan["logo_text"] == "TOAN AAS"


def test_video_ai_real_b14_rebuild_preserves_durable_submit_identity():
    user_id = 981039
    state = bot.video_ai_real_apply_quality_product(
        _ready_prompt_summary_state(),
        300,
    )
    _prepared, session = bot.video_uiflow3_prepare_b14_session(
        user_id,
        state,
        require_attestation=False,
    )
    draft = dict(session.get("draft") or {})
    draft.update({
        "b14_project_id": 701,
        "b14_queue_job_id": 702,
        "b14_queue_job": {"id": 702, "status": "queued"},
    })
    session["draft"] = draft
    bot.save_video_session(user_id, session)

    _prepared, rebuilt = bot.video_uiflow3_prepare_b14_session(
        user_id,
        state,
        require_attestation=False,
    )
    rebuilt_draft = dict(rebuilt.get("draft") or {})

    assert rebuilt_draft["b14_project_id"] == 701
    assert rebuilt_draft["b14_queue_job_id"] == 702
    assert rebuilt_draft["b14_queue_job"] == {"id": 702, "status": "queued"}


def test_video_ai_real_invoice_attestation_rejects_replaced_or_foreign_invoice():
    session = {
        "current_step": "b14_invoice",
        "product_id": "video_ai_real",
        "draft": {
            "uiflow3_invoice_attestation_required": True,
            "uiflow3_invoice_attestation": {
                "token": "abc123def456",
                "draft_id": "draft-a",
                "config_hash": "hash-a",
                "owner_user_id": 981037,
                "owner_chat_id": 981037,
                "message_id": 41,
                "product_id": "video_ai_real",
            },
            "uiflow3_approved_snapshot": {
                "draft_id": "draft-a",
                "config_hash": "hash-a",
            },
        },
    }

    current = bot.video_uiflow3_validate_invoice_confirmation(
        session,
        user_id=981037,
        chat_id=981037,
        message_id=41,
        token="abc123def456",
    )
    replaced = bot.video_uiflow3_validate_invoice_confirmation(
        {
            **session,
            "draft": {
                **session["draft"],
                "uiflow3_approved_snapshot": {
                    "draft_id": "draft-b",
                    "config_hash": "hash-b",
                },
            },
        },
        user_id=981037,
        chat_id=981037,
        message_id=41,
        token="abc123def456",
    )
    foreign = bot.video_uiflow3_validate_invoice_confirmation(
        session,
        user_id=981037,
        chat_id=777,
        message_id=41,
        token="abc123def456",
    )
    stale_button = bot.video_uiflow3_validate_invoice_confirmation(
        session,
        user_id=981037,
        chat_id=981037,
        message_id=40,
        token="stale0000000",
    )

    assert current == {"ok": True, "reason": ""}
    assert replaced == {"ok": False, "reason": "invoice_snapshot_replaced"}
    assert foreign == {"ok": False, "reason": "invoice_owner_mismatch"}
    assert stale_button == {"ok": False, "reason": "invoice_attestation_mismatch"}


@pytest.mark.parametrize(
    ("callback", "chat_id", "message_id", "replace_snapshot"),
    [
        ("vproduct|b14_confirm", 981037, 41, False),
        ("vproduct|b14_confirm|bad000000000", 981037, 41, False),
        ("vproduct|b14_confirm|abc123def456", 777, 41, False),
        ("vproduct|b14_confirm|abc123def456", 981037, 41, True),
    ],
)
def test_video_ai_real_confirm_handler_rejects_invalid_invoice_before_any_side_effect(
    monkeypatch,
    callback,
    chat_id,
    message_id,
    replace_snapshot,
):
    snapshot = {
        "draft_id": "draft-b" if replace_snapshot else "draft-a",
        "config_hash": "hash-b" if replace_snapshot else "hash-a",
    }
    session = {
        "current_step": "b14_invoice",
        "product_id": "video_ai_real",
        "draft": {
            "b14_scene_count": 2,
            "b14_scene_count_selected": True,
            "b14_quality_xu": 400,
            "uiflow3_invoice_attestation_required": True,
            "uiflow3_invoice_attestation": {
                "token": "abc123def456",
                "draft_id": "draft-a",
                "config_hash": "hash-a",
                "owner_user_id": 981037,
                "owner_chat_id": 981037,
                "message_id": 41,
                "product_id": "video_ai_real",
            },
            "uiflow3_approved_snapshot": snapshot,
        },
    }
    calls = {"preflight": 0, "project": 0, "confirm": 0, "wallet": 0}

    def preflight(*_args, **_kwargs):
        calls["preflight"] += 1
        return {"ready": False, "preflight": {}, "scene_gate": {}}

    async def show_preflight(*_args, **_kwargs):
        return None

    def prepare_project(*_args, **_kwargs):
        calls["project"] += 1
        return {}

    def confirm_project(*_args, **_kwargs):
        calls["confirm"] += 1
        return {"ok": False}

    def wallet_read(*_args, **_kwargs):
        calls["wallet"] += 1
        return (0, None, None)

    monkeypatch.setattr(bot, "get_video_session", lambda _uid: session)
    monkeypatch.setattr(bot, "video_b14_is_admin_or_owner", lambda _uid: False)
    monkeypatch.setattr(bot, "product_video_public_preflight_evaluation", preflight)
    monkeypatch.setattr(bot, "product_video_show_public_preflight_panel", show_preflight)
    monkeypatch.setattr(bot, "video_b14_prepare_project_for_invoice", prepare_project)
    monkeypatch.setattr(bot, "confirm_video_project_invoice", confirm_project)
    monkeypatch.setattr(bot, "get_user", wallet_read)

    query = _PilotQuery(
        981037,
        callback,
        "pilot-invalid-invoice-confirm",
        message_id=message_id,
        chat_id=chat_id,
    )
    asyncio.run(
        bot.handle_product_video_public_confirm_callback(
            SimpleNamespace(callback_query=query),
            SimpleNamespace(user_data={}),
        )
    )

    assert calls == {"preflight": 0, "project": 0, "confirm": 0, "wallet": 0}
    assert query.edits
    assert "không còn hiệu lực" in query.edits[-1]["text"]


def test_video_ai_real_resume_invoice_renders_the_saved_real_b14_invoice():
    user_id = 981034
    context = SimpleNamespace(user_data={})
    _save_owned(context, _ready_prompt_summary_state(), user_id)

    _click_visible(context, user_id, "vid3|summary_done", "pilot-resume-invoice-1")
    _click_visible(context, user_id, "vid3|quality|400", "pilot-resume-invoice-2")
    assert bot.video_uiflow3_state(context)["navigation"]["current_step"] == "invoice"

    resume_query = _PilotQuery(user_id, "vid3|resume", "pilot-resume-invoice-3")
    asyncio.run(
        bot.handle_video_uiflow3_callback(
            SimpleNamespace(callback_query=resume_query),
            context,
        )
    )

    assert resume_query.edits
    callbacks = _callbacks(resume_query.edits[-1]["reply_markup"])
    assert any(value.startswith("vproduct|b14_confirm|") for value in callbacks)
    assert "vid3|invoice_confirm" not in callbacks
    assert bot.get_video_session(user_id)["current_step"] == "b14_invoice"


def test_video_ai_real_quality_screen_keeps_provider_details_internal():
    state = video_uiflow3.navigate(_ready_prompt_summary_state(), "package")

    text, _markup = bot.video_uiflow3_screen_payload(state)

    assert "ShopAIKey" not in text
    assert "Key4U" not in text
    assert "provider" not in text.lower()


def test_video_ai_real_source_image_shortcuts_render_and_return_to_exact_entity():
    user_id = 981023
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.set_character_count(_locked_state(), 1)
    state = video_uiflow3.set_location_count(state, 1)
    state = video_uiflow3.add_source_asset(
        state,
        asset_type="image",
        telegram_file_id="source-image-file",
        fingerprint="telegram:source-image-unique",
    )
    state["navigation"]["current_step"] = "production_bible"
    state = bot.video_uiflow3_open_view(
        state,
        "character_detail",
        active_character_id="char_01",
    )
    _save_owned(context, state, user_id)

    _text, character_markup = bot.video_uiflow3_screen_payload(state)
    assert "vid3|source_ref_set|source_01|character|char_01" in _callbacks(character_markup)
    _click_visible(
        context,
        user_id,
        "vid3|source_ref_set|source_01|character|char_01",
        "pilot-source-character-1",
    )
    character_state = bot.video_uiflow3_state(context)
    assert character_state.get("ui_view") == "character_detail"
    assert character_state.get("active_character_id") == "char_01"

    location_state = bot.video_uiflow3_open_view(
        character_state,
        "location_detail",
        active_location_id="loc_01",
    )
    _save_owned(context, location_state, user_id)
    _text, location_markup = bot.video_uiflow3_screen_payload(location_state)
    assert "vid3|source_ref_set|source_01|location|loc_01" in _callbacks(location_markup)
    _click_visible(
        context,
        user_id,
        "vid3|source_ref_set|source_01|location|loc_01",
        "pilot-source-location-1",
    )
    saved_location = bot.video_uiflow3_state(context)
    assert saved_location.get("ui_view") == "location_detail"
    assert saved_location.get("active_location_id") == "loc_01"


def test_video_ai_real_prompt_scene_edit_accepts_text_and_returns_to_same_scene():
    user_id = 981024
    context = SimpleNamespace(user_data={})
    state = _ready_prompt_summary_state()
    state["navigation"]["current_step"] = "prompts"
    state = bot.video_uiflow3_open_view(state, "prompt_scenes")
    _save_owned(context, state, user_id)

    _click_visible(context, user_id, "vid3|prompt_scene|scene_01", "pilot-prompt-edit-1")
    _click_visible(context, user_id, "vid3|prompt_edit|scene_01", "pilot-prompt-edit-2")
    pending = bot.video_uiflow3_state(context)
    assert pending["pending_input"]["kind"] == "scene_prompt"

    message = _PilotMessage(user_id, "Lan giới thiệu sản phẩm trong ánh sáng cửa sổ tự nhiên.", 88101)
    handled = asyncio.run(
        bot.handle_video_uiflow3_pending_text(
            SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id)),
            context,
        )
    )

    assert handled is True
    saved = bot.video_uiflow3_state(context)
    assert saved.get("ui_view") == "prompt_scene_detail"
    assert saved.get("active_scene_id") == "scene_01"
    assert saved["scenes"][0]["prompt_override"].startswith("Lan giới thiệu")


def test_video_ai_real_character_can_use_a_content_based_default_description():
    user_id = 981025
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.set_character_count(_locked_state(), 1)
    state = video_uiflow3.update_character(state, "char_01", gender="female")
    state["navigation"]["current_step"] = "production_bible"
    state = bot.video_uiflow3_open_view(
        state,
        "character_detail",
        active_character_id="char_01",
    )
    _save_owned(context, state, user_id)

    _text, markup = bot.video_uiflow3_screen_payload(state)
    assert "Dùng mô tả theo nội dung" in _plain_labels(markup)
    _click_visible(context, user_id, "vid3|char_suggest|char_01", "pilot-character-suggest-1")

    saved = bot.video_uiflow3_state(context)
    character = saved["bible"]["characters"][0]
    assert saved.get("ui_view") == "character_detail"
    assert character["description"]
    assert "Giới thiệu sản phẩm" in character["description"]


def test_video_ai_real_per_scene_music_has_a_finishable_scene_picker():
    user_id = 981026
    context = SimpleNamespace(user_data={})
    state = _ready_prompt_summary_state()
    state["navigation"]["current_step"] = "scene_assignment"
    state = bot.video_uiflow3_open_view(state, "audio_options")
    _save_owned(context, state, user_id)

    _click_visible(context, user_id, "vid3|view|audio_music", "pilot-music-scenes-1")
    _click_visible(context, user_id, "vid3|audio_set|music|library_scene", "pilot-music-scenes-2")

    saved = bot.video_uiflow3_state(context)
    assert saved.get("ui_view") == "audio_music_scenes"
    text, markup = bot.video_uiflow3_screen_payload(saved)
    assert "Nhạc theo từng cảnh" in text
    assert {"Cảnh 1", "Cảnh 2", "Hoàn tất chọn nhạc theo từng cảnh"}.issubset(set(_plain_labels(markup)))
    assert "vid3|view|audio_options" in _callbacks(markup)

    _click_visible(context, user_id, "vid3|scene_music|scene_01", "pilot-music-scenes-3")
    scene_music = bot.video_uiflow3_state(context)
    assert scene_music.get("ui_view") == "scene_music"
    assert scene_music.get("active_scene_id") == "scene_01"
    _scene_text, scene_music_markup = bot.video_uiflow3_screen_payload(scene_music)
    assert "vid3|view|audio_music_scenes" in _callbacks(scene_music_markup)
    _click_visible(context, user_id, "vid3|view|audio_music_scenes", "pilot-music-scenes-back-1")
    assert bot.video_uiflow3_state(context).get("ui_view") == "audio_music_scenes"
    _click_visible(context, user_id, "vid3|scene_music|scene_01", "pilot-music-scenes-3b")

    _click_visible(context, user_id, "vid3|scene_music_set|scene_01|off", "pilot-music-scenes-set-1")
    scene_music_after_set = bot.video_uiflow3_state(context)
    assert scene_music_after_set.get("ui_view") == "audio_music_scenes"

    _click_visible(context, user_id, "vid3|scene_music|scene_01", "pilot-music-scenes-open-custom-1")
    _click_visible(context, user_id, "vid3|scene_music_custom|scene_01", "pilot-music-scenes-4")
    pending = bot.video_uiflow3_state(context)
    assert pending["pending_input"]["kind"] == "scene_music"
    _pending_text, pending_markup = bot.video_uiflow3_screen_payload(pending)
    assert "vid3|scene_music|scene_01" in _callbacks(pending_markup)
    _click_visible(context, user_id, "vid3|scene_music|scene_01", "pilot-music-scenes-input-back-1")
    returned_scene_music = bot.video_uiflow3_state(context)
    _returned_text, returned_markup = bot.video_uiflow3_screen_payload(returned_scene_music)
    assert "vid3|view|audio_music_scenes" in _callbacks(returned_markup)
    _click_visible(context, user_id, "vid3|scene_music_custom|scene_01", "pilot-music-scenes-4b")

    message = _PilotMessage(user_id, "Nhạc thư viện tươi sáng cho cảnh mở đầu", 88102)
    handled = asyncio.run(
        bot.handle_video_uiflow3_pending_text(
            SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id)),
            context,
        )
    )
    assert handled is True
    selected = bot.video_uiflow3_state(context)
    assert selected.get("ui_view") == "audio_music_scenes"
    assert selected["audio"]["music_plan"]["scene_01"]["track_id"].startswith("Nhạc thư viện")
    _selected_text, selected_markup = bot.video_uiflow3_screen_payload(selected)
    assert "vid3|scene_music|scene_01" in _callbacks(selected_markup)


def test_video_ai_real_entry_route_metadata_matches_the_visible_product_screen():
    state = video_uiflow3.new_state("video_ai_real", draft_id="pilot-entry-route-contract")
    _text, markup = bot.video_uiflow3_screen_payload(state)
    visible = tuple(_callbacks(markup))
    expected = tuple(bot.VIDEO_PUBLIC_ROUTE_MATRIX["video_ai_real"]["expected_children"])

    assert "vid3|idea_catalog" not in expected
    assert expected == tuple(callback for callback in visible if callback != "menu|main_video")


def _detailed_visual_state() -> dict:
    state = _assigned_state()
    state = video_uiflow3.update_character(
        state,
        "char_01",
        description="Lan mặc áo xanh, biểu cảm tự tin và thao tác sản phẩm tự nhiên.",
    )
    state = video_uiflow3.update_character(
        state,
        "char_02",
        description="Minh mặc áo trắng, phản ứng chân thật và giữ nhận diện ổn định.",
    )
    state = video_uiflow3.update_location(
        state,
        "loc_01",
        description="Quán cà phê sáng, bàn gỗ cạnh cửa sổ và hậu cảnh gọn.",
        lighting="Ánh sáng cửa sổ mềm",
        mood="Ấm áp, đáng tin",
    )
    state = video_uiflow3.add_product(
        state,
        name="Serum A",
        category="Mỹ phẩm",
        description="Chai thủy tinh xanh, nhãn và hình dáng phải giữ nguyên.",
    )
    state = video_uiflow3.add_prop(
        state,
        name="Gương tròn",
        description="Gương nhỏ đặt bên phải sản phẩm.",
    )
    state = video_uiflow3.add_reference(
        state,
        asset_type="image",
        owner_type="character",
        owner_id="char_01",
        role="primary_identity",
        telegram_file_id="character-reference-file",
        fingerprint="character-reference-fingerprint",
    )
    state = video_uiflow3.add_reference(
        state,
        asset_type="image",
        owner_type="location",
        owner_id="loc_01",
        role="primary_location",
        telegram_file_id="location-reference-file",
        fingerprint="location-reference-fingerprint",
    )
    state = video_uiflow3.assign_scene(
        state,
        "scene_01",
        character_ids=["char_01", "char_02"],
        location_id="loc_01",
        product_ids=["prod_01"],
        prop_ids=["prop_01"],
    )
    state = video_uiflow3.update_scene_plan(
        state,
        "scene_01",
        semantic_beat="Lan khám phá vấn đề da khô rồi giới thiệu giải pháp.",
        main_action="Lan mở nắp, nhỏ serum lên tay và Minh quan sát kết cấu.",
        completion_state="Hai nhân vật nhìn thấy kết cấu thấm đều trên da.",
    )
    state = video_uiflow3.update_scene_direction(
        state,
        "scene_01",
        framing="Trung cảnh chuyển sang cận sản phẩm",
        movement="Dolly-in chậm theo bàn tay Lan",
        lighting="Ánh sáng cửa sổ mềm, da và thủy tinh trung thực",
        mood="Tò mò rồi tin tưởng",
    )
    state["audio"].update({
        "dialogue_segments": [{
            "dialogue_id": "dlg_01",
            "scene_id": "scene_01",
            "speaker_id": "char_01",
            "text": "POST_ONLY_DIALOGUE",
        }],
        "voice_cast": {
            "char_01": {"voice_id": "POST_ONLY_VOICE", "gender": "female"},
        },
        "music_scope": "whole_video",
        "music_source": "library",
        "music_plan": {"track_id": "POST_ONLY_MUSIC"},
        "subtitle_mode": "auto",
        "dubbing_mode": "browser",
        "sfx_mode": "library",
        "sfx_plan": [{"scene_id": "scene_01", "cue": "POST_ONLY_SFX"}],
    })
    state["branding"] = {
        "logo_file_id": "POST_ONLY_LOGO",
        "watermark_text": "POST_ONLY_WATERMARK",
    }
    return video_uiflow3.normalize_state(state)


def test_video_ai_real_compiler_materializes_visual_choices_and_separates_postproduction():
    compiled = bot.video_ai_real_compile_state(_detailed_visual_state())
    contract = compiled["render_contract"]
    first = contract["visual"]["scenes"][0]
    prompt = first["visual_prompt"]

    for selected_visual in (
        "Lan",
        "Minh",
        "áo xanh",
        "Quán cà phê",
        "Serum A",
        "Gương tròn",
        "nhỏ serum lên tay",
        "Dolly-in chậm",
        "Ánh sáng cửa sổ mềm",
        "Tò mò rồi tin tưởng",
        "9:16",
    ):
        assert selected_visual in prompt
    assert first["reference_asset_ids"] == ["asset_01", "asset_02"]
    assert first["duration_seconds"] == 8
    assert first["visual_prompt_hash"]

    for post_only in (
        "POST_ONLY_DIALOGUE",
        "POST_ONLY_VOICE",
        "POST_ONLY_MUSIC",
        "POST_ONLY_SFX",
        "POST_ONLY_LOGO",
        "POST_ONLY_WATERMARK",
    ):
        assert post_only not in prompt

    post = contract["post_production"]
    assert post["dialogue"][0]["text"] == "POST_ONLY_DIALOGUE"
    assert post["voice_cast"]["char_01"]["voice_id"] == "POST_ONLY_VOICE"
    assert post["music"]["plan"]["track_id"] == "POST_ONLY_MUSIC"
    assert post["sfx"]["plan"][0]["cue"] == "POST_ONLY_SFX"
    assert post["branding"]["logo_file_id"] == "POST_ONLY_LOGO"
    assert post["branding"]["watermark_text"] == "POST_ONLY_WATERMARK"
    assert contract["provider_called"] is False
    assert contract["job_created"] is False
    assert contract["wallet_mutations"] == 0


def test_video_ai_real_compiler_materializes_per_scene_music_assignments():
    state = _detailed_visual_state()
    state["audio"].update({
        "music_scope": "per_scene",
        "music_source": "library",
        "music_plan": {
            "scene_01": {
                "policy": "track",
                "track_id": "SCENE_ONE_MUSIC",
                "volume": 20,
            },
        },
    })
    compiled = bot.video_ai_real_compile_state(state)["render_contract"]

    assert compiled["post_production"]["music"]["scope"] == "per_scene"
    assert compiled["post_production"]["music"]["scene_assignments"] == {
        "scene_01": {
            "policy": "track",
            "track_id": "SCENE_ONE_MUSIC",
            "volume": 20,
        },
    }


def test_video_ai_real_postproduction_changes_do_not_dirty_or_rewrite_visual_prompts():
    compiled = bot.video_ai_real_compile_state(_detailed_visual_state())
    visual_hash = compiled["render_contract"]["visual"]["visual_hash"]

    changed = bot.video_ai_real_apply_audio_option(compiled, "music", "ai_scene")
    assert "prompts" not in set(changed["navigation"]["dirty_sections"])

    recompiled = bot.video_ai_real_compile_state(changed)
    assert recompiled["render_contract"]["visual"]["visual_hash"] == visual_hash
    assert recompiled["render_contract"]["post_production"]["music"] == {
        "scope": "per_scene",
        "source": "ai",
        "plan": {},
        "scene_assignments": {},
    }


def test_video_ai_real_quick_build_is_deterministic_and_reaches_quality_without_side_effects():
    user_id = 981027
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.new_state("video_ai_real", draft_id="pilot-quick-build")
    state = video_uiflow3.set_entry_mode(state, "prompt_video")
    state = video_uiflow3.set_scene_count_preference(state, 2)
    state = video_uiflow3.set_format(state, ratio="9:16", target_duration_seconds=16)
    state = video_uiflow3.set_content_candidate(
        state,
        source="content_catalog",
        profile_id="product_demo",
        original_intent="Giới thiệu serum cho người mới chăm sóc da.",
        approved_brief={
            "title": "Serum cho người mới",
            "needs_characters": True,
            "needs_locations": True,
            "needs_dialogue": False,
            "needs_voice": False,
            "needs_music": False,
        },
    )
    state = video_uiflow3.lock_content(state)
    state["navigation"]["current_step"] = "production_bible"
    _save_owned(context, state, user_id)

    text, markup = bot.video_uiflow3_screen_payload(state)
    assert "Nhân vật và bối cảnh" in text
    assert {"Tạo nhanh", "Tùy chỉnh chi tiết"}.issubset(set(_plain_labels(markup)))

    _click_visible(context, user_id, "vid3|quick_build", "pilot-quick-build-1")
    quick = bot.video_uiflow3_state(context)
    assert quick["navigation"]["current_step"] == "summary"
    assert quick["render_contract"]["visual"]["scene_count"] == 2
    assert quick["legacy_compat"]["pilot_quick_build"]["seed"]
    assert quick["legacy_compat"]["pilot_quick_build"]["version"] == "quick-v1"
    assert quick["side_effects"] == {
        "provider_calls": 0,
        "jobs": 0,
        "outbox": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }

    second = bot.video_ai_real_build_quick_plan(state)
    assert second["render_contract"]["visual"]["visual_hash"] == quick["render_contract"]["visual"]["visual_hash"]
    summary_text, summary_markup = bot.video_uiflow3_screen_payload(quick)
    assert "Rà soát cuối" in summary_text
    assert {"Logo và watermark", "Hoàn tất rà soát và chọn chất lượng"}.issubset(set(_plain_labels(summary_markup)))


def test_video_ai_real_compile_hook_is_a_noop_for_other_products():
    state = video_uiflow3.new_state("script_image_video", draft_id="protected-other-product")
    before = video_uiflow3.normalize_state(state)

    after = bot.video_ai_real_maybe_compile_state(state)

    assert after == before
    assert "render_contract" not in after


def test_video_ai_real_voice_change_is_post_only_and_keeps_visual_hash():
    user_id = 981028
    context = SimpleNamespace(user_data={})
    state = bot.video_ai_real_compile_state(_detailed_visual_state())
    visual_hash = state["render_contract"]["visual"]["visual_hash"]
    state["navigation"]["current_step"] = "production_bible"
    state = bot.video_uiflow3_open_view(
        state,
        "character_detail",
        active_character_id="char_01",
    )
    _save_owned(context, state, user_id)

    _click_visible(context, user_id, "vid3|char_voice|char_01", "pilot-post-voice-1")
    _click_visible(context, user_id, "vid3|voice|char_01|vf1", "pilot-post-voice-2")

    changed = bot.video_uiflow3_state(context)
    assert "prompts" not in set(changed["navigation"]["dirty_sections"])
    assert "audio" in set(changed["navigation"]["dirty_sections"])
    recompiled = bot.video_ai_real_compile_state(changed)
    assert recompiled["render_contract"]["visual"]["visual_hash"] == visual_hash
    assert recompiled["bible"]["characters"][0]["voice_id"] == "vi-VN-HoaiMyNeural"


def test_video_ai_real_context_suggestion_rebases_after_content_changes():
    state = _locked_state()
    original_revision = state["content"]["revision"]
    state = bot.video_ai_real_apply_context_prompt(state, "story")
    assert state["content"]["revision"] == original_revision + 1
    assert state["content"]["locked"] is False
    assert "prompts" in state["navigation"]["dirty_sections"]

    state = video_uiflow3.set_content_candidate(
        state,
        source="manual",
        original_intent="Nội dung mới về chăm sóc da.",
        approved_brief={"title": "Chăm sóc da mới"},
    )
    changed = bot.video_ai_real_apply_context_prompt(state, "sales")

    assert changed["content"]["original_intent"].startswith("Nội dung mới về chăm sóc da.")
    assert "Nội dung ban đầu về cà phê" not in changed["content"]["original_intent"]
    commercial = changed["legacy_compat"]["pilot_commercial"]
    assert commercial["context_base_intent"] == "Nội dung mới về chăm sóc da."


def test_video_ai_real_post_only_change_preserves_existing_visual_dirtiness():
    state = bot.video_ai_real_compile_state(_detailed_visual_state())
    state["scenes"][0]["main_action"] = "Lan đổi hành động hình ảnh sau lần biên dịch trước."
    state["navigation"]["dirty_sections"] = ["prompts"]

    changed = bot.video_ai_real_apply_audio_option(state, "music", "none")

    assert {"prompts", "audio", "summary"}.issubset(
        set(changed["navigation"]["dirty_sections"])
    )


def test_video_ai_real_model_change_refreshes_existing_visual_contract():
    state = bot.video_ai_real_compile_state(_ready_prompt_summary_state())
    old_hash = state["render_contract"]["visual"]["visual_hash"]

    changed = bot.video_ai_real_apply_prompt_model(state, "grok3_5")

    assert [scene["duration_target"] for scene in changed["scenes"]] == [5, 5]
    contract = changed["render_contract"]["visual"]
    assert [scene["duration_seconds"] for scene in contract["scenes"]] == [5, 5]
    assert contract["visual_hash"] != old_hash


def test_video_ai_real_quote_excludes_per_scene_ai_music_explicitly_turned_off():
    state = bot.video_ai_real_apply_prompt_model(
        _ready_prompt_summary_state(),
        "veo31_fast_8",
    )
    state = bot.video_ai_real_apply_audio_option(state, "music", "ai_scene")
    state = video_uiflow3.set_scene_music(state, "scene_01", policy="off")
    state = bot.video_ai_real_mark_post_only_change(state)

    quote = bot.video_ai_real_prompt_quote(state)

    music = next(item for item in quote["addons"] if item["key"] == "music_ai")
    assert music == {
        "key": "music_ai",
        "label": "Nhạc AI theo từng cảnh",
        "price_xu": 80,
    }
