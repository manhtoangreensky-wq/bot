from __future__ import annotations

import asyncio
from types import SimpleNamespace

import bot
import pytest
from services import video_uiflow3


def _logical_callback(value: str) -> str:
    parts = str(value or "").split("|")
    if len(parts) >= 4 and parts[:2] == ["vid3", "d"]:
        return "|".join(("vid3", *parts[3:]))
    return str(value or "")


def _callbacks(markup) -> set[str]:
    return {
        _logical_callback(str(button.callback_data or ""))
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }


def _labels(markup) -> set[str]:
    return {
        str(button.text or "")
        for row in markup.inline_keyboard
        for button in row
    }


def _owned(state: dict, user_id: int = 991001) -> dict:
    state = video_uiflow3.normalize_state(state)
    state["owner_user_id"] = user_id
    state["owner_chat_id"] = user_id
    return state


def _prompt_state(*, step: str = "production_bible") -> dict:
    state = video_uiflow3.new_state("video_ai_real", draft_id="image-sync-prompt")
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
        original_intent="Lan giới thiệu một sản phẩm trong quán cà phê sáng.",
        approved_brief={"title": "Giới thiệu sản phẩm"},
    )
    state = video_uiflow3.lock_content(state)
    state["navigation"]["current_step"] = step
    return _owned(state)


def test_image_and_storyboard_products_require_upload_or_ai_image_before_continue():
    image = video_uiflow3.new_state("video_ai_real", draft_id="required-image")
    image = video_uiflow3.set_entry_mode(image, "image_video")
    image = video_uiflow3.set_scene_count_preference(image, 1)
    image = video_uiflow3.set_format(
        image,
        ratio="9:16",
        target_duration_seconds=8,
        seconds_per_scene=8,
    )
    image["navigation"]["current_step"] = "source"
    image_text, image_markup = bot.video_uiflow3_screen_payload(image)

    assert "Ảnh tham chiếu đầu vào" in image_text
    assert {"🖼 Gửi ảnh", "✨ Tạo ảnh AI"} <= _labels(image_markup)
    assert "vid3|source_done" not in _callbacks(image_markup)
    assert image["source"]["required"] is True
    assert image["source"]["complete"] is False

    for mode in ("storyboard_generate", "storyboard_upload"):
        storyboard = video_uiflow3.new_state(
            "storyboard_prompt",
            draft_id=f"required-{mode}",
        )
        storyboard = video_uiflow3.set_entry_mode(storyboard, mode)
        assert storyboard["navigation"]["current_step"] == "source"
        assert storyboard["source"]["required"] is True
        assert storyboard["source"]["complete"] is False

        source_text, source_markup = bot.video_uiflow3_screen_payload(storyboard)
        assert "ảnh" in source_text.lower()
        assert {"vid3|source_media", "vid3|image_ai|source"} <= _callbacks(source_markup)
        assert "vid3|source_done" not in _callbacks(source_markup)


def test_all_creative_reference_intakes_keep_upload_and_ai_creation_actions():
    state = video_uiflow3.set_character_count(_prompt_state(), 1)
    state = video_uiflow3.set_location_count(state, 1)

    character = bot.video_uiflow3_open_view(
        state,
        "character_detail",
        active_character_id="char_01",
    )
    _text, markup = bot.video_uiflow3_screen_payload(character)
    callbacks = _callbacks(markup)
    assert "vid3|char_image|char_01" in callbacks
    assert "vid3|image_ai|character|char_01" in callbacks

    location = bot.video_uiflow3_open_view(
        state,
        "location_detail",
        active_location_id="loc_01",
    )
    _text, markup = bot.video_uiflow3_screen_payload(location)
    callbacks = _callbacks(markup)
    assert "vid3|loc_image|loc_01" in callbacks
    assert "vid3|image_ai|location|loc_01" in callbacks

    state = video_uiflow3.add_product(state, name="Serum", description="Chai xanh")
    state = video_uiflow3.add_prop(state, name="Gương", description="Gương tròn")
    extras = bot.video_uiflow3_open_view(state, "bible_extras")
    _text, markup = bot.video_uiflow3_screen_payload(extras)
    callbacks = _callbacks(markup)
    assert "vid3|product_image|prod_01" in callbacks
    assert "vid3|image_ai|product|prod_01" in callbacks
    assert "vid3|prop_image|prop_01" in callbacks
    assert "vid3|image_ai|prop|prop_01" in callbacks

    scene3_callbacks = {
        str(button.callback_data or "")
        for row in bot.video_scene3_materials_keyboard().inline_keyboard
        for button in row
    }
    for material_type in (
        "character_person",
        "product_object",
        "background",
        "visual_style_reference",
        "storyboard_frames",
    ):
        assert f"vprofile|material_ai|{material_type}" in scene3_callbacks


def test_uiflow3_ai_image_handoff_binds_owner_target_and_returns_to_exact_screen():
    user_id = 991002
    context = SimpleNamespace(user_data={})
    state = _owned(_prompt_state(), user_id)
    state = video_uiflow3.set_character_count(state, 1)
    state = bot.video_uiflow3_open_view(
        state,
        "character_detail",
        active_character_id="char_01",
    )
    bot.save_video_uiflow3_state(context, state)

    pending = bot.video_uiflow3_prepare_quick_image_handoff(
        context,
        state,
        user_id=user_id,
        target_kind="character",
        target_id="char_01",
    )

    assert pending["source_flow"] == "video_uiflow3"
    assert pending["uiflow3_draft_id"] == state["draft_id"]
    assert pending["uiflow3_owner_user_id"] == user_id
    assert pending["uiflow3_target_kind"] == "character"
    assert pending["uiflow3_target_id"] == "char_01"
    assert pending["return_to"] == "vid3|resume"
    assert bot.quick_image_context_return_callback(pending) == "vid3|resume"

    confirmation = bot.quick_image_video_scene3_confirmation_fields(pending)
    assert confirmation["origin_flow"] == "video_uiflow3"
    assert confirmation["uiflow3_draft_id"] == state["draft_id"]
    assert confirmation["uiflow3_target_kind"] == "character"

    saved = bot.video_uiflow3_record_generated_image(
        context,
        user_id,
        confirmation,
        job_id=88,
        output_file_id="generated-character-file",
        prompt="Nhân vật nữ mặc áo xanh",
        delivered=True,
    )
    assert saved is not None
    assert saved.get("ui_view") == "character_detail"
    assert saved.get("active_character_id") == "char_01"
    reference = saved["references"][0]
    assert reference["owner_type"] == "character"
    assert reference["owner_id"] == "char_01"
    assert reference["telegram_file_id"] == "generated-character-file"

    before = bot.video_uiflow3_state(context)
    stale = {**confirmation, "uiflow3_draft_id": "older-draft"}
    assert bot.video_uiflow3_record_generated_image(
        context,
        user_id,
        stale,
        output_file_id="must-not-attach",
        delivered=True,
    ) is None
    assert bot.video_uiflow3_state(context) == before


def test_stale_uiflow3_image_handoff_stops_before_job_provider_or_charge(monkeypatch):
    calls = {"job": 0, "rendered": []}

    monkeypatch.setattr(
        bot,
        "video_uiflow3_record_generated_image",
        lambda *_args, **_kwargs: None,
    )

    def forbidden_job(*_args, **_kwargs):
        calls["job"] += 1
        pytest.fail("stale UIFLOW3 handoff reached job/provider path")

    async def capture_render(_query, text, **_kwargs):
        calls["rendered"].append(str(text or ""))

    monkeypatch.setattr(bot, "create_shopaikey_job", forbidden_job)
    monkeypatch.setattr(bot, "safe_edit_or_send", capture_render)
    monkeypatch.setattr(bot, "shopaikey_preview_final_cost", lambda *_args, **_kwargs: 100)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)

    query = SimpleNamespace(message=SimpleNamespace(chat_id=991003))
    asyncio.run(bot.handle_shopaikey_public_image_confirm_delivery_first(
        SimpleNamespace(user_data={}),
        query,
        991003,
        "vi",
        {
            "origin_flow": "video_uiflow3",
            "uiflow3_draft_id": "stale-draft",
            "return_to": "vid3|resume",
        },
        "xu",
        "token",
        "quick_image_v6",
        "Ảnh nhân vật",
        100,
        "normal",
        "Tiêu chuẩn",
        "1:1",
        "1:1",
        "image-model",
        "",
        "",
        0,
        0,
        0,
        "",
        1000,
    ))

    assert calls["job"] == 0
    assert calls["rendered"]
    assert "chưa gọi" in calls["rendered"][-1].lower()


def test_review_quality_and_invoice_are_separate_and_quality_hides_technical_details():
    review = _prompt_state(step="summary")
    review_text, review_markup = bot.video_uiflow3_screen_payload(review)
    assert "Rà soát cuối" in review_text
    assert "Chọn chất lượng" not in review_text
    assert "vid3|summary_done" in _callbacks(review_markup)
    assert not any(callback.startswith("vid3|quality|") for callback in _callbacks(review_markup))

    quality = video_uiflow3.navigate(review, "package")
    quality_text, quality_markup = bot.video_uiflow3_screen_payload(quality)
    callbacks = _callbacks(quality_markup)
    quality_callbacks = {item for item in callbacks if item.startswith("vid3|quality|")}

    assert "Chọn chất lượng" in quality_text
    assert len(quality_callbacks) >= 8
    assert "vid3|quality_done" in callbacks
    for forbidden in ("model", "provider", "api", "shopaikey", "key4u", "payload", "worker"):
        assert forbidden not in quality_text.lower()
        assert all(forbidden not in label.lower() for label in _labels(quality_markup))

    selected = bot.video_ai_real_apply_quality_product(quality, 300)
    commercial = selected["legacy_compat"]["pilot_commercial"]
    assert commercial["quality"]["tier_id"] == 300
    assert commercial["quality"]["unit_xu"] == 300
    assert commercial["quality"]["seconds"] > 0
    assert selected["side_effects"] == {
        "provider_calls": 0,
        "jobs": 0,
        "outbox": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }
