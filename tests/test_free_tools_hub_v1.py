from pathlib import Path

import bot
from free_tools_hub import (
    ALLOWED_FREE_PROVIDER_TASKS,
    FREE_TOOL_TYPES,
    free_provider_candidates,
    generate_contextual_prompt,
    load_prompt_library,
    prompt_library_counts,
    prompt_library_suggestions,
    quota_limit_for_user,
    sensitive_free_task_reason,
    should_show_soft_promo,
)


def _callbacks(markup):
    return {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }


def _source() -> str:
    return Path(bot.__file__).resolve().read_text(encoding="utf-8")


def _source_between(start_marker: str, end_marker: str) -> str:
    source = _source()
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def test_free_hub_menu_visible():
    assert "freehub|main" in _callbacks(bot.main_menu_keyboard(False))
    assert "freehub|main" in _callbacks(bot.localized_main_menu_keyboard(False, "vi"))
    assert "freehub|main" in _callbacks(bot.localized_main_menu_keyboard(False, "en"))
    assert "freehub|main" in _callbacks(bot.localized_main_menu_keyboard(False, "zh"))
    assert "miễn phí không giới hạn" not in bot.free_hub_main_text("vi").lower()


def test_free_hub_callbacks_have_handlers():
    source = _source()
    assert 'CallbackQueryHandler(handle_free_hub_callback, pattern=r"^freehub\\|")' in source
    handler = _source_between(
        "async def handle_free_hub_callback",
        "async def handle_feedback_callback",
    )
    required_actions = {
        "main",
        "chat",
        "meta",
        "ideas",
        "caption",
        "hook",
        "prompts",
        "image_prompt",
        "video_prompt",
        "docs",
        "notes",
        "byok",
        "upload",
        "library",
        "copy",
        "variant",
        "caption_more",
        "save",
    }
    for action in required_actions:
        assert f'"{action}"' in handler


def test_free_hub_reuses_existing_handlers():
    docs_callbacks = _callbacks(bot.free_hub_docs_keyboard("vi"))
    notes_callbacks = _callbacks(bot.free_hub_notes_keyboard("vi"))
    assert "menu|main_docs" in docs_callbacks
    assert "menu|main_memory" in notes_callbacks
    assert "menu|memory_storage_status" in notes_callbacks


def test_free_hub_back_routing():
    assert "freehub|main" in _callbacks(bot.free_hub_input_keyboard("vi"))
    assert "freehub|main" in _callbacks(bot.free_hub_prompts_keyboard("vi"))
    assert "freehub|library" in _callbacks(bot.free_hub_library_suggestions_keyboard("vi"))
    assert "freehub|lib_back" in _callbacks(bot.free_hub_library_item_keyboard("vi"))
    assert "freehub|meta_back_goal" in _callbacks(bot.free_hub_meta_choice_keyboard("meta_platform", "vi"))
    assert "freehub|meta_back_platform" in _callbacks(bot.free_hub_meta_choice_keyboard("meta_ratio", "vi"))
    assert "freehub|meta_back_ratio" in _callbacks(bot.free_hub_meta_choice_keyboard("meta_style", "vi"))


def test_free_hub_no_xu_charge_for_free_tasks():
    record_source = _source_between(
        "def free_hub_record_success",
        "def free_hub_soft_promo_keyboard",
    )
    callback_source = _source_between(
        "async def handle_free_hub_callback",
        "async def handle_feedback_callback",
    )
    pending_source = _source_between(
        "async def handle_free_hub_pending_text",
        "async def handle_free_hub_pending_upload",
    )
    assert "xu_delta=0" in record_source
    assert "spend_fixed_credit" not in callback_source
    assert "deduct" not in callback_source.lower()
    assert "spend_fixed_credit" not in pending_source
    assert "deduct" not in pending_source.lower()
    assert "Xu deducted: <code>0</code>" in bot.free_hub_prompt_result_text(
        {"title": "Test", "prompt": "Prompt test"},
        "image_prompt",
    )


def test_prompt_library_loads_and_has_minimum_seed_count():
    library = load_prompt_library()
    assert library["version"] == "1.0"
    assert len(library["_expanded_items"]) >= 100
    counts = prompt_library_counts(library)
    assert counts["meta_ai_video"] >= 10
    assert counts["image_prompt"] >= 10
    assert counts["video_prompt"] >= 10
    assert counts["caption_cta"] >= 10
    assert counts["hook_script"] >= 10
    assert counts["document_checklist"] >= 10
    assert counts["music_sfx"] >= 10


def test_prompt_library_category_filter_and_random_suggestion():
    library = load_prompt_library()
    first = prompt_library_suggestions(library, "image_prompt", count=3, seed=11)
    second = prompt_library_suggestions(
        library,
        "image_prompt",
        count=3,
        exclude_ids=[item["id"] for item in first],
        seed=12,
    )
    assert len(first) == 3
    assert len(second) == 3
    assert all(item["category_id"] == "image_prompt" for item in first + second)
    assert {item["id"] for item in first}.isdisjoint({item["id"] for item in second})


def test_prompt_library_save_to_notes_is_guarded_by_storage_quota():
    handler = _source_between(
        "async def handle_free_hub_callback",
        "async def handle_feedback_callback",
    )
    assert "memory_quota_error" in handler
    assert "memory_create_note" in handler
    assert '"free-hub, prompt"' in handler


def test_contextual_prompt_product_defaults():
    result = generate_contextual_prompt("tôi bán nước hoa nam cao cấp")
    context = result["context"]
    assert context["industry_id"] == "beauty_fragrance"
    assert context["goal"] == "bán hàng"
    assert context["platform"] == "TikTok/Reels"
    assert context["aspect_ratio"] == "9:16"
    assert 8 <= context["duration_seconds"] <= 15
    assert "sang trọng" in context["style"]


def test_contextual_prompt_contains_scene_camera_lighting_action():
    result = generate_contextual_prompt("máy xay sinh tố mini màu xanh ngọc")
    prompt = result["prompt"].lower()
    for marker in ("cảnh 1", "hành động", "camera", "ánh sáng", "9:16"):
        assert marker in prompt
    assert result["shot_list"]
    assert result["negative_prompt"]


def test_meta_ai_prompt_flow_outputs_prompt_caption_hashtag_cta():
    result = generate_contextual_prompt(
        "app AI tạo nội dung cho người mới",
        {
            "goal": "tăng tương tác",
            "platform": "Instagram/Reels",
            "aspect_ratio": "9:16",
            "style": "UGC đời thường",
        },
    )
    assert result["prompt"]
    assert len(result["variants"]) == 3
    assert result["caption"]
    assert result["hashtags"]
    assert result["cta"]
    assert "copy prompt" in result["copy_instruction"].lower()


def test_meta_ai_prompt_does_not_claim_api_call():
    result = generate_contextual_prompt("quán cafe mới mở")
    instruction = result["copy_instruction"].lower()
    assert "chưa gọi api meta" in instruction
    assert "chưa tạo video" in instruction


def test_free_provider_router_skips_disabled_provider_and_uses_byok_first():
    enabled = {
        "gemini": False,
        "groq": True,
        "openrouter": True,
        "byok_openrouter": True,
    }
    candidates = free_provider_candidates(
        ["gemini", "groq", "openrouter"],
        enabled,
        byok_provider="openrouter",
    )
    assert candidates == ["byok:openrouter", "groq", "openrouter"]


def test_free_provider_router_blocks_sensitive_task():
    assert sensitive_free_task_reason(
        "Tôi đã chuyển khoản rồi, đây là bill thanh toán",
        "free_chat",
    ) == "payment"
    assert sensitive_free_task_reason(
        "API key của tôi là secret",
        "free_chat",
    ) == "secret"
    assert sensitive_free_task_reason(
        "Tạo video render production",
        "video_render",
    ) == "task_not_allowed"
    assert "video_prompt" in ALLOWED_FREE_PROVIDER_TASKS


def test_free_provider_quota_limit():
    limits = {"free": 30, "registered": 100, "premium": 300, "admin": 1000}
    assert quota_limit_for_user(False, False, False, limits) == 30
    assert quota_limit_for_user(False, False, True, limits) == 100
    assert quota_limit_for_user(False, True, True, limits) == 300
    assert quota_limit_for_user(True, False, False, limits) == 1000


def test_free_provider_no_key_logging():
    router_source = _source_between(
        "async def free_provider_router_call",
        "def free_hub_record_success",
    )
    assert "logger." not in router_source
    assert "print(" not in router_source
    assert "user_input" not in router_source.split("errors.append", 1)[-1]
    assert "api_key" not in bot.cmd_free_provider_status.__code__.co_names


def test_free_storage_quota_and_temp_upload_policy():
    assert bot.TOTAL_FREE_STORAGE_MB == 50
    assert bot.NOTES_TEXT_FREE_MB == 10
    assert bot.FILES_AUDIO_FREE_MB == 40
    notes_source = _source_between(
        "def free_hub_notes_text",
        "def free_hub_notes_keyboard",
    )
    assert "file tạm không tính lâu dài" in notes_source.lower()
    upload_source = _source_between(
        "async def handle_free_hub_pending_upload",
        "async def handle_message",
    )
    assert "remember_last_user_file" in upload_source
    assert "memory_create_note" not in upload_source
    assert "video" in upload_source


def test_free_tool_types_cover_requested_routes():
    assert {
        "free_chat",
        "meta_ai_prompt",
        "content_idea",
        "caption_hashtag",
        "hook_script",
        "image_prompt",
        "video_prompt",
        "document_pdf",
        "notes_storage",
        "prompt_library",
        "byok_api",
        "upload_for_postprocess",
    } == FREE_TOOL_TYPES


def test_free_hub_soft_promo_after_success_count_and_cooldown():
    assert should_show_soft_promo(4, after_requests=5, now_ts=1000) is False
    assert should_show_soft_promo(5, after_requests=5, now_ts=1000) is True
    assert should_show_soft_promo(
        10,
        after_requests=5,
        last_shown_ts=1000,
        now_ts=1000 + 23 * 3600,
        cooldown_hours=24,
    ) is False
    assert should_show_soft_promo(
        10,
        after_requests=5,
        last_shown_ts=1000,
        now_ts=1000 + 24 * 3600,
        cooldown_hours=24,
    ) is True


def test_free_hub_admin_commands_registered():
    source = _source()
    assert 'CommandHandler("free_hub_status", cmd_free_hub_status)' in source
    assert 'CommandHandler("free_hub_prompt_test", cmd_free_hub_prompt_test)' in source
    assert 'CommandHandler("free_provider_status", cmd_free_provider_status)' in source
    assert "is_admin_user" in _source_between(
        "async def cmd_free_hub_status",
        "async def cmd_free_provider_status",
    )
    assert "is_admin_user" in _source_between(
        "async def cmd_free_provider_status",
        "async def cmd_free_hub_prompt_test",
    )
