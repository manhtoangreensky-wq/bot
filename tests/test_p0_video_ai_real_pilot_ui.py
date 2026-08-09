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
    def __init__(self, user_id: int, data: str, query_id: str) -> None:
        self.data = data
        self.id = query_id
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace(chat_id=user_id)
        self.edits: list[dict] = []
        self.answers: list[dict] = []

    async def answer(self, text: str | None = None, **kwargs) -> None:
        self.answers.append({"text": text, **kwargs})

    async def edit_message_text(self, text: str, **kwargs) -> None:
        self.edits.append({"text": text, **kwargs})


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


def test_video_ai_real_pilot_format_screen_uses_accented_portrait_copy_and_scene_duration_choices():
    state = video_uiflow3.new_state("video_ai_real", draft_id="pilot-format")
    state = video_uiflow3.set_entry_mode(state, "prompt_video")
    state = video_uiflow3.set_format(state, ratio="9:16", target_duration_seconds=8)
    state["navigation"]["current_step"] = "format"

    text, markup = bot.video_uiflow3_screen_payload(state)
    callbacks = _callbacks(markup)

    assert "Khung hình & thời lượng" in text
    assert "Dọc 9:16" in text
    assert "6 giây/cảnh" in text
    assert "8 giây/cảnh" in text
    assert "DINH DANG MUC TIEU" not in text
    assert "vid3|duration_scene|6" in callbacks
    assert "vid3|duration_scene|8" in callbacks


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

    assert "Phân vai & âm thanh theo cảnh" in text
    assert "Cảnh 2 nối tiếp kết quả Cảnh 1" in text
    assert "Nhân vật 1" in text
    assert "Nhạc toàn video" in text
    assert "Nhạc theo từng cảnh" in text
    assert "vid3|music_scope" in callbacks


def test_video_ai_real_pilot_location_back_callback_is_the_immediate_parent():
    state = video_uiflow3.set_location_count(_locked_state(), 1)
    state["navigation"]["current_step"] = "production_bible"
    state = bot.video_uiflow3_open_view(
        state,
        "location_detail",
        active_location_id="loc_01",
    )

    _text, markup = bot.video_uiflow3_screen_payload(state)
    back_buttons = [
        _logical_callback(str(button.callback_data or ""))
        for row in markup.inline_keyboard
        for button in row
        if _plain_label(button.text) == "Quay lại"
    ]

    assert back_buttons == ["vid3|view|location_list"]


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
    assert "Kho ý tưởng (chỉ xem)" in labels
    assert "vid3|mode|prompt_video" in callbacks
    assert "vid3|mode|image_video" in callbacks
    assert "vid3|mode|video_video" not in callbacks
    assert "vid3|idea_catalog" in callbacks


def test_video_ai_real_pilot_stays_inside_prompt_to_video_mode():
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
    assert "Khung hình & thời lượng" in prompt_text

    image_state = video_uiflow3.new_state("video_ai_real", draft_id="pilot-scope-image")
    image_state = video_uiflow3.set_entry_mode(image_state, "image_video")
    image_state = video_uiflow3.set_format(
        image_state,
        ratio="9:16",
        target_duration_seconds=16,
    )
    image_state["navigation"]["current_step"] = "format"

    image_text, _image_markup = bot.video_uiflow3_screen_payload(image_state)
    assert "DINH DANG MUC TIEU" in image_text
    assert "Khung hình & thời lượng" not in image_text

    with pytest.raises(ValueError, match="scene_duration_invalid"):
        video_uiflow3.set_format(image_state, seconds_per_scene=6)

    image_state["format"]["seconds_per_scene"] = 6
    normalized_image_state = video_uiflow3.normalize_state(image_state)
    assert normalized_image_state["format"]["seconds_per_scene"] == 8


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
    assert "6 giây/cảnh" in _plain_labels(format_markup)
    assert "8 giây/cảnh" in _plain_labels(format_markup)

    _click_visible(context, user_id, "vid3|ratio|9x16", "pilot-product-first-3")
    _click_visible(context, user_id, "vid3|duration_scene|6", "pilot-product-first-4")
    _click_visible(context, user_id, "vid3|format_done", "pilot-product-first-5")
    content_state = bot.video_uiflow3_state(context)
    assert content_state["navigation"]["current_step"] == "content_hub"
    assert content_state["format"]["ratio"] == "9:16"
    assert content_state["format"]["target_duration_seconds"] == 12


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
    assert "Kho ý tưởng (chỉ xem)" in hub_labels
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
    assert "Tiếp tục đến nhân vật & bối cảnh" in _plain_labels(lock_markup)
    assert "Chọn nội dung khác" in _plain_labels(lock_markup)


def test_video_ai_real_pilot_production_bible_uses_beginner_copy_and_zero_is_explicit_auto():
    state = _locked_state()
    state["navigation"]["current_step"] = "production_bible"

    text, markup = bot.video_uiflow3_screen_payload(state)
    labels = _plain_labels(markup)

    assert "Nhân vật & bối cảnh" in text
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
    assert "Giọng nam 1 (kế hoạch)" in _plain_labels(male_markup)
    assert "Giọng nam 2 (kế hoạch)" in _plain_labels(male_markup)


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
    assert "mỗi cảnh 8 giây" in count_text
    assert "Dùng đề xuất" in _plain_labels(count_markup)

    state = video_uiflow3.confirm_scene_count(state, 2)
    state = video_uiflow3.suggest_scene_plan(state)
    plan_text, plan_markup = bot.video_uiflow3_screen_payload(state)
    assert "Kế hoạch cảnh" in plan_text
    assert "Cảnh 1" in plan_text and "Cảnh 2" in plan_text
    assert "Duyệt kế hoạch" in _plain_labels(plan_markup)

    state["navigation"]["current_step"] = "branding"
    branding_text, branding_markup = bot.video_uiflow3_screen_payload(state)
    assert "Logo & watermark" in branding_text
    assert {"Gửi logo", "Nhập watermark", "Bỏ qua"}.issubset(set(_plain_labels(branding_markup)))

    state["navigation"]["current_step"] = "summary"
    summary_text, summary_markup = bot.video_uiflow3_screen_payload(state)
    assert "Tóm tắt Video AI chân thật" in summary_text
    assert "Nhân vật & bối cảnh" in _plain_labels(summary_markup)
    assert "Phân vai & âm thanh" in _plain_labels(summary_markup)
    assert "Logo & watermark" in _plain_labels(summary_markup)

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
    assert "Rà soát lại Nhân vật & bối cảnh" in dirty_text
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
    assert "🗂 Kho ý tưởng (chỉ xem)" in labels
    assert "⬅️ Quay lại Menu Video" in labels
    assert "flow cũ" not in text.lower()
    assert _callbacks(markup).count("menu|main_video") == 1
    assert all("[x]" not in label and "[ ]" not in label for label in labels)


def test_video_ai_real_non_prompt_source_stays_legacy_while_prompt_input_is_polished():
    state = video_uiflow3.new_state(
        "video_ai_real",
        draft_id="pilot-source",
        capabilities={"video_to_video": True},
    )
    state = bot.video_uiflow3_after_service_update(
        state,
        video_uiflow3.set_entry_mode(state, "image_video"),
    )

    source_text, source_markup = bot.video_uiflow3_screen_payload(state)
    assert "NGUON VIDEO" in source_text
    assert "Ảnh tham chiếu đầu vào" not in source_text
    assert {"Gui tep/anh", "Da nhan 0"}.issubset(set(_plain_labels(source_markup)))
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
    assert "🎬 Cảnh 1 · Phân vai & âm thanh" in detail_text
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
    assert "🧠 Rà soát prompt" in prompt_text
    assert {"Prompt từng cảnh", "Tùy chỉnh nâng cao", "Tiếp tục"}.issubset(set(_plain_labels(prompt_markup)))

    advanced = bot.video_uiflow3_open_view(state, "prompt_advanced")
    advanced_text, advanced_markup = bot.video_uiflow3_screen_payload(advanced)
    assert "🎥 Tùy chỉnh nâng cao theo cảnh" in advanced_text
    assert "vid3|view|prompts" in _callbacks(advanced_markup)


def test_video_ai_real_pilot_duration_and_location_callbacks_persist_only_inside_pilot():
    user_id = 981001
    context = SimpleNamespace(user_data={})
    state = video_uiflow3.new_state("video_ai_real", draft_id="pilot-callback-duration")
    state = video_uiflow3.set_entry_mode(state, "prompt_video")
    state = video_uiflow3.set_format(state, ratio="9:16", target_duration_seconds=16)
    state["navigation"]["current_step"] = "format"
    _save_owned(context, state, user_id)

    _click_visible(context, user_id, "vid3|duration_scene|6", "pilot-duration-1")
    saved = bot.video_uiflow3_state(context)
    assert saved["parent_product"] == "video_ai_real"
    assert saved["format"]["ratio"] == "9:16"
    assert saved["format"]["seconds_per_scene"] == 6
    planned = video_uiflow3.set_content_candidate(
        saved,
        source="manual",
        original_intent="Một video sản phẩm có ba hành động ngắn.",
        approved_brief={"title": "Ba hành động ngắn"},
    )
    planned = video_uiflow3.lock_content(planned)
    assert video_uiflow3.suggest_scene_count(planned) == {
        "count": 3,
        "seconds_per_scene": 6,
        "source": "duration_and_content",
    }

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

    summary_text, _summary_markup = bot.video_uiflow3_screen_payload(state)
    assert "2 cảnh × 6 giây = 12 giây" in summary_text


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

    assert "DINH DANG MUC TIEU" in text
    assert "Khung hình & thời lượng" not in text
