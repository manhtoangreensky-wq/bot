import asyncio
from pathlib import Path
from types import SimpleNamespace

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


class _FakeFreeHubQuery:
    def __init__(self, data="freehub|main", user_id=12345):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id, username="tester", first_name="Tester")
        self.message = SimpleNamespace(chat_id=user_id)
        self.answered = False
        self.edited = None

    async def answer(self, *args, **kwargs):
        self.answered = True
        self.answer_args = args
        self.answer_kwargs = kwargs

    async def edit_message_text(self, text, parse_mode=None, reply_markup=None):
        self.edited = {
            "text": text,
            "parse_mode": parse_mode,
            "reply_markup": reply_markup,
        }
        return self.edited


def _labels(markup):
    return [[button.text for button in row] for row in markup.inline_keyboard]


def _callback_set(markup):
    return {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }


def test_free_hub_remains_available_from_its_existing_legacy_entrypoint():
    assert "freehub|main" in _callbacks(bot.main_menu_keyboard(False))
    assert "miễn phí không giới hạn" not in bot.free_hub_main_text("vi").lower()


def test_main_menu_layout_regular_user():
    markup = bot.localized_main_menu_keyboard(False, "vi")
    labels = _labels(markup)

    assert labels[0] == ["🖼 Tạo ảnh AI", "🎬 Tạo video AI"]
    assert labels[1] == ["🎵 Nhạc & âm thanh", "🎙 Voice & lồng tiếng"]
    assert labels[2] == ["💬 Hỏi AI • 5/25 Xu/1K", "📚 Hướng dẫn"]
    assert labels[3] == ["🎧 Hỗ trợ", "📊 Trung tâm"]
    assert labels[4] == ["🌐 Đổi ngôn ngữ", "🏠 Menu chính"]
    assert [len(row) for row in markup.inline_keyboard] == [2, 2, 2, 2, 2]
    assert all("🔐 Admin" not in label for row in labels for label in row)
    assert "menu|main_video" in _callback_set(markup)


def test_main_menu_layout_admin():
    markup = bot.localized_main_menu_keyboard(True, "vi")
    labels = _labels(markup)

    assert labels[0] == ["🖼 Tạo ảnh AI", "🎬 Tạo video AI"]
    assert labels[3] == ["🎧 Hỗ trợ", "📊 Trung tâm"]
    assert labels[4] == ["🌐 Đổi ngôn ngữ", "🏠 Menu chính"]
    assert labels[-1] == ["🔐 Admin"]
    assert len(markup.inline_keyboard[-1]) == 1
    assert [len(row) for row in markup.inline_keyboard[:-1]] == [2, 2, 2, 2, 2]


def test_main_menu_callbacks_have_handlers():
    source = _source()
    markup = bot.localized_main_menu_keyboard(True, "vi")
    callbacks = _callback_set(markup)

    assert callbacks == {
        "menu|chat_pro",
        "menu|main_image",
        "menu|main_video",
        "menu|translate",
        "music_quick|showroom|root",
        "menu|main_guide",
        "menu|support",
        "back_lang",
        "menu|main",
        "menu|admin",
    }
    assert 'CallbackQueryHandler(handle_free_hub_callback, pattern=r"^freehub\\|")' in source
    assert 'CallbackQueryHandler(handle_menu_callback, pattern=r"^menu\\|")' in source
    assert 'CallbackQueryHandler(handle_pricing_callback, pattern=r"^pricing\\|")' in source
    assert 'CallbackQueryHandler(handle_feedback_callback, pattern=r"^feedback\\|")' in source
    assert 'CallbackQueryHandler(handle_language_callback, pattern=r"^(lang\\|(?:[a-z]{2}|fil)|lang_more|back_lang|lang_back)$")' in source


def test_video_main_button_opens_video_menu():
    text, markup = bot.localized_menu_content("main_video", False, "vi", user_id=12345)
    callbacks = _callback_set(markup)

    assert "VIDEO TOAN AAS" in text.upper()
    assert "vproduct|open|video_ai_real" in callbacks
    assert "vproduct|open|video_trend" in callbacks
    assert "menu|main" in callbacks


def test_free_tools_main_keyboard_is_compact_placeholder():
    callbacks = _callback_set(bot.free_hub_main_keyboard("vi"))

    assert {
        "freehub|meta",
        "freehub|caption",
        "freehub|ideas",
        "freehub|prompts",
        "freehub|publish_package",
        "freehub|library",
        "menu|main_memory",
        "freehub|upload",
        "freehub|hook",
        "freehub|lib_music",
        "support|start",
        "feedback|start",
        "menu|main",
    }.issubset(callbacks)
    assert "freehub|chat" not in callbacks
    assert "freehub|byok" not in callbacks
    assert not any(callback.startswith("videoref|") for callback in callbacks)


def test_free_tools_button_opens_menu(monkeypatch):
    monkeypatch.setattr(bot, "FREE_HUB_ENABLED", True)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    query = _FakeFreeHubQuery("freehub|main")
    update = SimpleNamespace(callback_query=query)

    asyncio.run(bot.handle_free_hub_callback(update, SimpleNamespace()))

    assert query.answered is True
    assert "Công cụ miễn phí TOAN AAS" in query.edited["text"]
    assert "freehub|meta" in _callback_set(query.edited["reply_markup"])
    assert "menu|main" in _callback_set(query.edited["reply_markup"])


def test_free_tools_child_buttons_guard_if_not_ready(monkeypatch):
    monkeypatch.setattr(bot, "FREE_HUB_ENABLED", True)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    query = _FakeFreeHubQuery("freehub|unknown_button")
    update = SimpleNamespace(callback_query=query)

    asyncio.run(bot.handle_free_hub_callback(update, SimpleNamespace()))

    assert query.answered is True
    assert "đang hoàn thiện nút này" in query.edited["text"]
    assert "chưa gọi API" in query.edited["text"]
    assert "chưa trừ Xu" in query.edited["text"]


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
        "publish_package",
        "prompt_back",
        "copy",
        "variant",
        "caption_more",
        "save",
        "suggest_more",
        "suggest_custom",
    }
    for action in required_actions:
        assert f'"{action}"' in handler
    assert 'action.startswith("use_prompt")' in handler


def test_free_hub_reuses_existing_handlers():
    docs_callbacks = _callbacks(bot.free_hub_docs_keyboard("vi"))
    notes_callbacks = _callbacks(bot.free_hub_notes_keyboard("vi"))
    assert "menu|hint_doc_image_to_pdf" in docs_callbacks
    assert "menu|hint_doc_compress_pdf" in docs_callbacks
    assert "freehub|docs_split_merge" in docs_callbacks
    assert "freehub|docs_summary_guard" in docs_callbacks
    assert "menu|main_memory" in notes_callbacks
    assert "menu|memory_storage_status" in notes_callbacks


def test_free_hub_main_links_notes_documents_directly_and_hides_byok():
    callbacks = _callbacks(bot.free_hub_main_keyboard("vi"))
    assert "menu|main_memory" in callbacks
    assert "freehub|docs" not in callbacks
    assert "freehub|notes" not in callbacks
    assert "freehub|byok" not in callbacks
    labels = [button.text for row in bot.free_hub_main_keyboard("vi").inline_keyboard for button in row]
    assert "📝 Ghi chú / Tài liệu" in labels
    assert not any("API" in label for label in labels)


def test_free_hub_removes_reference_shortcuts_and_renames_prompt_library():
    markup = bot.free_hub_main_keyboard("vi")
    callbacks = _callbacks(markup)
    labels = [button.text for row in markup.inline_keyboard for button in row]

    assert "videoref|hub" not in callbacks
    assert "videoref|profile" not in callbacks
    assert "🎬 Prompt theo video mẫu" not in labels
    assert "📺 Hồ sơ kênh" not in labels
    assert "📚 Kho prompt mẫu" in labels
    assert "freehub|library" in callbacks


def test_free_prompt_library_back_to_free_hub():
    markup = bot.free_hub_library_keyboard("vi")
    callbacks = _callbacks(markup)
    labels = [button.text for row in markup.inline_keyboard for button in row]

    assert "freehub|main" in callbacks
    assert "🎬 Prompt video" in labels
    assert "🖼 Prompt ảnh" in labels
    assert "🎵 Nhạc/SFX" in labels
    assert "🔁 Gợi ý ngẫu nhiên" in labels


def test_free_hub_suggestion_flow_before_input():
    suggestions = bot.free_hub_suggestion_items("meta_ai_prompt", 0)
    more = bot.free_hub_suggestion_items("meta_ai_prompt", 3)
    assert len(suggestions) == 3
    assert len(more) == 3
    assert suggestions != more
    text = bot.free_hub_suggestions_text("meta_ai_prompt", suggestions, "vi")
    assert "3 gợi ý" in text
    assert "không trừ Xu" in text
    callbacks = _callbacks(bot.free_hub_suggestions_keyboard("vi"))
    assert {
        "freehub|suggest_pick1",
        "freehub|suggest_pick2",
        "freehub|suggest_pick3",
        "freehub|suggest_more",
        "freehub|suggest_custom",
        "freehub|main",
    }.issubset(callbacks)


def test_prompt_flow_generates_three_prompts_and_has_required_actions():
    result = bot.free_hub_meta_prompt_pack("nước hoa nam", 0)
    choices = bot.free_hub_prompt_choices(result)
    callbacks = _callbacks(bot.free_hub_result_keyboard("vi", "meta_ai_prompt", meta=True))

    assert len(choices) == 3
    assert {
        "freehub|use_prompt1",
        "freehub|use_prompt2",
        "freehub|use_prompt3",
        "freehub|variant",
        "freehub|edit",
        "freehub|save",
        "freehub|use_video",
        "freehub|copy",
    }.issubset(callbacks)


def test_prompt_create_video_ai_guard_has_no_local_export():
    callbacks = _callbacks(bot.free_hub_video_ai_guard_keyboard("vi"))
    text = bot.free_hub_video_ai_guard_text({"selected_prompt": "prompt test"}, "vi")

    assert "chưa xử lý video" in text
    assert "bảo trì/nâng cấp nhẹ" in text
    assert "chưa trừ Xu" in text
    assert "freehub|prompt_back" in callbacks
    assert "vfinal|export_local" not in callbacks
    assert "menu|main_video" not in callbacks


def test_free_hub_back_routing():
    assert "freehub|main" in _callbacks(bot.free_hub_input_keyboard("vi"))
    assert "freehub|main" in _callbacks(bot.free_hub_prompts_keyboard("vi"))
    assert "freehub|main" in _callbacks(bot.free_hub_library_suggestions_keyboard("vi"))
    assert "freehub|main" in _callbacks(bot.free_hub_library_item_keyboard("vi"))
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
        "image_video_prompt",
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
