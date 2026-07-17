from __future__ import annotations

from pathlib import Path

from services import video_scene3_flow


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    markers = (f"def {name}(", f"async def {name}(")
    starts = [BOT_SOURCE.find(marker) for marker in markers]
    start = min(position for position in starts if position >= 0)
    candidates = [
        position
        for marker in ("\ndef ", "\nasync def ")
        if (position := BOT_SOURCE.find(marker, start + 1)) >= 0
    ]
    return BOT_SOURCE[start:min(candidates) if candidates else len(BOT_SOURCE)]


def _state(scene_count: int = 3) -> dict:
    state = video_scene3_flow.default_state(
        product_type="video_ai_real",
        subject="Giới thiệu sản phẩm bằng một mạch kể rõ và nhất quán",
    )
    state = video_scene3_flow.invalidate_scene_outputs(state, scene_count)
    state.update({
        "technical_profile": "product_3d_showcase",
        "content_type": "product_review",
    })
    return video_scene3_flow.normalize_state(state)


def test_canonical_order_and_back_matrix_are_explicit():
    expected = (
        "content_mode", "scene_count", "aspect_ratio", "asset_gate",
        "technical_profile", "content_choice", "character", "image_source",
        "image_assets", "creative_controls", "requirements", "audio_plan",
        "scene_plan", "image_prompts", "video_prompts", "full_review",
        "quality", "final_report", "final_confirmation",
    )
    assert video_scene3_flow.CANONICAL_STEPS == expected
    assert video_scene3_flow.BACK_STEP["aspect_ratio"] == "scene_count"
    assert video_scene3_flow.BACK_STEP["technical_profile"] == "aspect_ratio"
    assert video_scene3_flow.BACK_STEP["content_choice"] == "technical_profile"
    assert video_scene3_flow.BACK_STEP["character"] == "content_choice"
    assert video_scene3_flow.BACK_STEP["automatic_text"] == "full_review"
    assert video_scene3_flow.BACK_STEP["post_addons"] == "full_review"
    assert video_scene3_flow.canonical_back_step({"step": "automatic_text_review"}) == "automatic_text"
    assert video_scene3_flow.canonical_back_step({
        "step": "automatic_text_review",
        "automatic_text_return_step": "full_review",
    }) == "full_review"
    assert video_scene3_flow.canonical_back_step({
        "step": "transitions",
        "transitions_return_step": "full_review",
    }) == "full_review"
    assert video_scene3_flow.canonical_back_step({
        "step": "automatic_text_scope",
        "active_automatic_text_id": "",
    }) == "automatic_text"


def test_profile_screen_has_fourteen_profiles_and_only_two_extra_actions():
    assert len(video_scene3_flow.TECHNICAL_PROFILES) == 14
    source = _function_source("video_scene3_profile_keyboard")
    assert "Gợi ý profile phù hợp" in source
    assert "Tự nhập profile" in source
    for forbidden in (
        "Dùng profile gợi ý", "Khôi phục profile trước", "Đổi gợi ý",
        "Dùng 2 cảnh đề xuất",
    ):
        assert forbidden not in source


def test_shared_field_editor_is_used_for_requirements_and_creative_fields():
    keyboard = _function_source("video_scene3_field_editor_keyboard")
    assert "range(1, 6)" in keyboard
    assert "Tự nhập" in keyboard
    assert "restore_action" in keyboard
    assert 'entry.get("history")' in keyboard
    assert "video_scene3_field_editor_keyboard(" in _function_source("video_scene3_requirement_detail_keyboard")
    assert "video_scene3_field_editor_keyboard(" in _function_source("video_scene3_creative_detail_keyboard")


def test_image_prompt_path_is_conditional_and_image_quote_has_zero_side_effects():
    description = video_scene3_flow.set_image_source_mode(_state(), "description")
    uploaded = video_scene3_flow.set_image_source_mode(_state(), "uploaded")
    create = video_scene3_flow.set_image_source_mode(_state(), "create")
    assert not video_scene3_flow.image_prompts_required(description)
    assert video_scene3_flow.image_prompts_required(uploaded)
    assert video_scene3_flow.image_prompts_required(create)

    create = video_scene3_flow.prepare_image_generation_quote(create, 150)
    quote = create["image_generation_quote"]
    assert quote == {
        "image_count": 3,
        "unit_price_xu": 150,
        "total_price_xu": 450,
        "quote_consistent": True,
        "provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }
    create = video_scene3_flow.confirm_image_generation_quote(create)
    assert create["image_generation_confirmed"] is True
    assert video_scene3_flow.preconfirm_side_effects(create) == {
        "provider_called": False,
        "image_provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "xu_charged": 0,
        "wallet_mutations": 0,
    }


def test_audio_and_text_have_one_canonical_owner_each():
    assert dict(video_scene3_flow.AUDIO_PLANNING_ADDONS) == {
        "dubbing": "🎙️ Lồng tiếng",
        "subtitles": "💬 Phụ đề",
        "source_audio": "🔊 Âm thanh gốc",
        "music": "🎵 Nhạc nền",
        "sfx": "💥 Hiệu ứng âm thanh",
    }
    assert video_scene3_flow.PUBLIC_CONTENT_ADDONS == ()
    assert {key for key, _label in video_scene3_flow.PUBLIC_POST_ADDONS} == {
        "logo_image", "watermark_text",
    }
    assert {key for key, _label in video_scene3_flow.PUBLIC_CONFIGURABLE_POST_ADDONS} == {
        "logo_image", "watermark_text", "subtitles", "dubbing",
        "music", "sfx", "source_audio",
    }
    audio_keyboard = _function_source("video_scene3_audio_plan_keyboard")
    assert "Lời dẫn/lời thoại" not in audio_keyboard
    assert "Phụ đề/chữ hiển thị" not in audio_keyboard
    assert "Nhịp/cảm xúc nhạc" not in audio_keyboard
    assert "Giọng đọc" not in audio_keyboard


def test_character_grounding_controls_follow_character_voice():
    ambiguous = video_scene3_flow.set_character_mode(_state(), "auto")
    blocked = video_scene3_flow.configure_voice_choice(ambiguous, "follow_character")
    assert not (blocked["postproduction_addons"]["dubbing"] or {}).get("enabled")
    assert blocked["character_config"]["needs_gender_confirmation"] is True

    female = video_scene3_flow.set_character_mode(_state(), "female")
    configured = video_scene3_flow.configure_voice_choice(female, "follow_character")
    dubbing = configured["postproduction_addons"]["dubbing"]
    assert dubbing["enabled"] is True
    assert dubbing["value"]["voice_choice"] == "default_female"


def test_all_audio_owners_accept_zero_to_two_hundred_with_peak_guard():
    assert video_scene3_flow.AUDIO_VOLUME_LEVELS == (0, 25, 50, 75, 100, 125, 150, 175, 200)
    for key in video_scene3_flow.AUDIO_POST_ADDONS:
        loud = video_scene3_flow.configure_audio_volume(_state(), key, 200)
        value = loud["postproduction_addons"][key]["value"]
        assert loud["postproduction_addons"][key]["enabled"] is True
        assert value["volume_percent"] == 200
        assert value["peak_guard"] is True
        assert value["clipping_guard"] == "limit_peak_before_mix"
        muted = video_scene3_flow.configure_audio_volume(loud, key, 0)
        assert muted["postproduction_addons"][key]["enabled"] is False


def test_character_intro_is_scene_scoped_timed_and_truthful_without_fake_tracking():
    state = video_scene3_flow.upsert_automatic_text_item(
        _state(),
        item_type="character_intro",
        text="Minh Anh · Kiến trúc sư",
        scene_scope="2",
        position="tracked",
    )
    item = state["automatic_text_items"][0]
    assert item["scene_scope"] == "2"
    assert item["target_kind"] == "person"
    assert item["timing_requested"] == "character_appears"
    assert item["timing"] == "scene_start"
    assert item["duration_seconds"] == 3
    assert item["disappear_on_scene_change"] is True
    assert item["style"] == "Thẻ giới thiệu nhân vật"
    assert item["animation"] == "slide_soft"
    assert item["tracking_requested"] is True
    assert item["tracking_active"] is False
    assert item["tracking_fallback_reason"] == "runtime_tracking_unavailable"
    assert item["position"] != "bottom_center"
    assert item["design"] == {
        "family": "Inter",
        "weight": "semibold",
        "text_color": "#FFFFFF",
        "accent_color": "#22C55E",
        "background": "dark_translucent_lower_third",
        "shadow": "soft",
        "max_lines": 2,
        "line_height": 1.15,
        "safe_margin_ratio": 0.04,
        "title_size_ratio": 0.045,
        "detail_size_ratio": 0.032,
    }
    assert item["layout_guard"] == {
        "always_avoid": ("subtitles", "logo", "watermark", "existing_text", "frame_edges"),
        "avoid_when_detectable": ("face", "person", "product"),
        "fallback": "fixed_safe_position",
    }

    original_position = item["position"]
    replaced = video_scene3_flow.upsert_automatic_text_item(
        state,
        item_type="character_intro",
        text="Minh Anh · Giám đốc sáng tạo",
        scene_scope="2",
        position="tracked",
    )
    assert len(replaced["automatic_text_items"]) == 1
    assert replaced["automatic_text_items"][0]["text"].startswith("Minh Anh")
    assert replaced["automatic_text_items"][0]["position"] == original_position
    assert replaced["postproduction_addons"]["automatic_text"]["value"]["item_count"] == 1


def test_character_intro_defaults_to_current_scene_and_requires_scene_before_copy():
    state = _state()
    state["active_scene_index"] = 3
    state = video_scene3_flow.upsert_automatic_text_item(
        state,
        item_type="character_intro",
        text="Lan · Người dẫn chương trình",
        scene_scope="all",
        position="tracked",
    )
    assert state["automatic_text_items"][0]["scene_scope"] == "3"
    handler = _function_source("handle_video_profile_studio_callback")
    assert 'if item_type in {"character_intro", "tracked_label"}' in handler
    assert '"automatic_text_scope"' in handler
    scope = _function_source("video_scene3_automatic_text_scope_keyboard")
    assert "character_card" in scope
    assert "Cảnh {index}" in scope
    scope_text = _function_source("video_scene3_automatic_text_scope_text")
    assert "thẻ giới thiệu chỉ hiện ở cảnh đó" in scope_text
    assert "2–5 giây hoặc hết cảnh" in scope_text


def test_each_new_character_gets_one_scene_scoped_intro_card_without_fabrication():
    state = _state(3)
    state = video_scene3_flow.upsert_automatic_text_item(
        state,
        item_type="character_intro",
        text="Lan · Người dẫn chương trình",
        scene_scope="1",
        position="tracked",
    )
    state = video_scene3_flow.upsert_automatic_text_item(
        state,
        item_type="character_intro",
        text="Minh · Kỹ thuật viên",
        scene_scope="3",
        position="tracked",
    )
    items = state["automatic_text_items"]
    assert len(items) == 2
    assert [item["scene_scope"] for item in items] == ["1", "3"]
    assert all(item["duration_seconds"] == 3 for item in items)
    assert all(item["disappear_on_scene_change"] for item in items)
    assert all(item["tracking_active"] is False for item in items)
    assert all(item["timing"] == "scene_start" for item in items)
    assert all(item["tracking_fallback_reason"] == "runtime_tracking_unavailable" for item in items)


def test_storyboard_and_legacy_image_source_routes_use_one_canonical_owner():
    source_keyboard = _function_source("video_scene3_image_source_keyboard")
    assert "storyboard_image_required" in source_keyboard
    assert "Gửi ảnh có sẵn" in source_keyboard
    assert "Tạo ảnh mới" in source_keyboard
    assert "video_scene3_image_source_keyboard(state)" in _function_source("video_scene3_image_strategy_keyboard")
    handler = _function_source("handle_video_profile_studio_callback")
    assert "Retired per-scene source callbacks are read-only redirects" in handler
    assert 'video_profile_studio_step(context, state, "image_source", push=False)' in handler


def test_automatic_text_ui_exposes_scene_target_duration_and_safe_fallback():
    review = _function_source("video_scene3_automatic_text_review_keyboard")
    assert "Cảnh áp dụng" in review
    assert "Đối tượng" in review
    assert "Thời lượng" in review
    assert "Vị trí" in review
    assert "Hiệu ứng" in review
    assert "Kiểu chữ" in review
    target = _function_source("video_scene3_automatic_text_target_keyboard")
    assert "AUTOMATIC_TEXT_TARGETS" in target
    duration = _function_source("video_scene3_automatic_text_duration_keyboard")
    assert "AUTOMATIC_TEXT_DURATIONS" in duration
    text = _function_source("video_scene3_automatic_text_review_text")
    assert "không tự bịa tên hay chức danh" in text
    assert "vị trí cố định an toàn" in text


def test_prompt_editor_and_public_keyboards_remove_duplicate_actions():
    prompt = _function_source("video_scene3_prompt_keyboard")
    for required in (
        "Gợi ý lại", "Sửa câu lệnh", "Sửa loại trừ", "Xem đầy đủ",
        "Sao chép", "Khôi phục", "Cảnh trước", "Cảnh sau",
        "Duyệt tất cả", "Xong phần này", "Quay lại", "Menu chính",
    ):
        assert required in prompt
    assert "Duyệt cảnh này" not in prompt

    public_sources = "\n".join([
        _function_source("video_profile_scene1_count_keyboard"),
        _function_source("video_scene3_profile_keyboard"),
        _function_source("video_scene3_scene_plan_keyboard"),
        _function_source("video_scene3_audio_plan_keyboard"),
        _function_source("video_scene3_post_keyboard"),
    ])
    for forbidden in (
        "Dùng 2 cảnh đề xuất", "Dùng profile gợi ý", "Khôi phục profile trước",
        "Nhịp/cảm xúc nhạc", "Giọng đọc", "Không dùng tùy chọn",
    ):
        assert forbidden not in public_sources


def test_review_routes_store_explicit_return_targets_and_no_preconfirm_submit():
    handler = _function_source("handle_video_profile_studio_callback")
    assert 'transitions_return_step="full_review"' in handler
    assert 'automatic_text_return_step="full_review"' in handler
    assert 'post_list_return_step="full_review"' in handler
    assert "canonical_back_step(state)" in handler
    assert "provider_submit" not in _function_source("video_scene3_automatic_text_keyboard")
    assert "provider_submit" not in _function_source("video_scene3_image_quote_keyboard")
    assert video_scene3_flow.preconfirm_audio_side_effects(_state()) == {
        "music_provider_calls": 0,
        "voice_provider_calls": 0,
        "files_generated": 0,
    }
