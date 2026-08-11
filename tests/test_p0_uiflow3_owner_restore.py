import asyncio
from types import SimpleNamespace

import bot


def _locked_profile_state(profile_key: str) -> dict:
    profile = dict(bot.video_profile_catalog.PROFILE_BY_KEY[profile_key])
    state = bot.video_uiflow3.new_state(
        "video_ai_real",
        draft_id=f"owner-profile-{profile_key}",
    )
    state = bot.video_uiflow3.set_entry_mode(state, "prompt_video")
    state = bot.video_uiflow3.set_scene_count_preference(state, 1)
    state = bot.video_uiflow3.set_format(
        state,
        ratio="9:16",
        target_duration_seconds=8,
    )
    return bot.video_uiflow3.set_content_candidate(
        state,
        source="content_catalog",
        profile_id=profile_key,
        original_intent=str(profile["description"]),
        approved_brief={
            "title": str(profile["public_name"]),
            "story_formula": list(profile["default_scene_pattern"]),
        },
    )


def test_start_delivers_one_menu_for_the_same_telegram_message(monkeypatch):
    bot.TELEGRAM_MESSAGE_DEDUPE_DONE.clear()
    bot.TELEGRAM_MESSAGE_DEDUPE_LOCKS.clear()
    replies = []

    class Message:
        message_id = 1701
        chat = SimpleNamespace(id=2701)

        async def reply_text(self, text, **kwargs):
            replies.append((text, kwargs))
            return SimpleNamespace(message_id=3701)

    update = SimpleNamespace(
        message=Message(),
        effective_chat=SimpleNamespace(id=2701),
        effective_user=SimpleNamespace(id=4701, first_name="Owner", username="owner"),
    )
    context = SimpleNamespace(args=[])

    monkeypatch.setattr(bot, "log_command_received", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bot, "user_exists", lambda _uid: True)
    monkeypatch.setattr(bot, "get_user", lambda *_args, **_kwargs: (0, 0, False))
    monkeypatch.setattr(bot, "record_usage_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bot, "clear_pending_start_notice", lambda _uid: "")
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(bot, "has_user_language", lambda _uid: True)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "user_selected_vietnamese_initially", lambda _uid: False)
    monkeypatch.setattr(bot, "localized_start_menu_text", lambda _uid, _lang: "MENU")
    monkeypatch.setattr(bot, "mode_start_notice", lambda _uid: "")
    monkeypatch.setattr(bot, "localized_main_menu_keyboard", lambda _admin, _lang: "KEYBOARD")

    async def no_birthday_message(_update, _context):
        return None

    monkeypatch.setattr(bot, "maybe_auto_grant_birthday_gift", no_birthday_message)

    async def deliver_twice():
        await bot.cmd_start(update, context)
        await bot.cmd_start(update, context)

    asyncio.run(deliver_twice())

    assert replies == [("MENU", {"parse_mode": "HTML", "reply_markup": "KEYBOARD"})]


def test_video_menu_restores_each_legacy_product_flow_except_ai_real_prompt_and_image():
    restored = {
        "video_trend": ("vproduct|open|video_trend", "handle_video_product_callback", "trend_first"),
        "script_image_video": ("vproduct|open|script_image_video", "handle_video_product_callback", "intro_then_profile"),
        "frame_video_local": ("vproduct|open|frame_video_local", "handle_video_product_callback", "local_frame_video"),
        "self_shot_scene_change": ("vproduct|open|self_shot_scene_change", "handle_video_product_callback", "self_shot_product_hub"),
        "multi_scene_film": ("longvideo|public_guard", "handle_long_video_callback", "canonical_long_preview"),
        "storyboard_prompt": ("vproduct|open|storyboard_prompt", "handle_video_product_callback", "storyboard2_canonical"),
    }

    for product_id, expected in restored.items():
        route = bot.VIDEO_PUBLIC_ROUTE_MATRIX[product_id]
        assert (route["entry_callback"], route["handler"], route["flow_type"]) == expected
        assert not route["entry_callback"].startswith("vid3|entry|")

    ai_real = bot.VIDEO_PUBLIC_ROUTE_MATRIX["video_ai_real"]
    assert ai_real["entry_callback"] == "vid3|entry|video_ai_real"
    assert ai_real["handler"] == "handle_video_uiflow3_callback"
    assert set(ai_real["expected_children"]) >= {
        "vid3|mode|prompt_video",
        "vid3|mode|image_video",
    }


def test_each_32_content_profile_restores_twenty_profile_specific_ideas():
    signatures = set()

    for profile in bot.video_profile_catalog.PROFILE_SEEDS:
        profile_key = str(profile["profile_key"])
        suggestions = bot.video_ai_real_profile_context_prompts(
            _locked_profile_state(profile_key)
        )
        pattern = " -> ".join(str(item) for item in profile["default_scene_pattern"])

        assert len(suggestions) == 20
        assert [item["key"] for item in suggestions] == [
            f"idea_{index:02d}" for index in range(1, 21)
        ]
        assert all(item["profile_key"] == profile_key for item in suggestions)
        assert all(str(profile["public_name"]) in item["guidance"] for item in suggestions)
        assert all(str(profile["description"]) in item["guidance"] for item in suggestions)
        assert all(pattern in item["guidance"] for item in suggestions)
        signatures.add(tuple(item["guidance"] for item in suggestions))

    assert len(signatures) == len(bot.video_profile_catalog.PROFILE_SEEDS) == 32

    text, markup = bot.video_uiflow3_screen_payload(
        _locked_profile_state("history_culture_mythology")
    )
    labels = [
        button.text
        for row in markup.inline_keyboard
        for button in row
    ]
    assert "5 gợi ý theo Lịch sử / văn hóa / thần thoại" in text
    assert "Bộ gợi ý 1/4" in text
    assert "🔄 Đổi 5 gợi ý" in labels
    assert "Bán hàng tự nhiên" not in text


def test_profile_ideas_keep_category_beats_and_a_complete_prompt_blueprint():
    sales = bot.video_ai_real_profile_context_prompts(
        _locked_profile_state("sales_ads")
    )
    history = bot.video_ai_real_profile_context_prompts(
        _locked_profile_state("history_culture_mythology")
    )

    assert [item["label"] for item in sales] == list(
        bot.video_idea_catalog.CATEGORY_BEAT_IDEAS["sales"]
    )
    assert [item["label"] for item in history] == list(
        bot.video_idea_catalog.CATEGORY_BEAT_IDEAS["history"]
    )

    required_fields = {
        "content_goal",
        "hook",
        "story_formula",
        "clarification",
        "character_direction",
        "location_direction",
        "visual_style",
        "camera",
        "motion",
        "transition",
        "voice",
        "music",
        "subtitle",
        "pacing",
        "constraints",
    }
    for suggestion in (*sales, *history):
        blueprint = dict(suggestion.get("prompt_blueprint") or {})
        assert required_fields <= set(blueprint)
        assert all(blueprint[field] for field in required_fields)
        prompt = str(suggestion.get("prompt") or "")
        for marker in (
            "Mục tiêu nội dung:",
            "Tình tiết chính:",
            "Nhân vật/chủ thể:",
            "Bối cảnh:",
            "Máy quay:",
            "Chuyển động:",
            "Giọng:",
            "Nhạc:",
            "Phụ đề:",
            "Nhịp dựng:",
        ):
            assert marker in prompt

    selected = bot.video_ai_real_apply_context_prompt(
        _locked_profile_state("history_culture_mythology"),
        "idea_01",
    )
    commercial = dict((selected["legacy_compat"] or {})["pilot_commercial"])
    assert commercial["context_prompt_blueprint"] == history[0]["prompt_blueprint"]
    assert commercial["context_prompt"] == history[0]["prompt"]
    assert history[0]["visual_prompt"] in selected["content"]["original_intent"]
    assert history[0]["prompt_blueprint"]["voice"] not in selected["content"]["original_intent"]
    assert history[0]["prompt_blueprint"]["music"] not in selected["content"]["original_intent"]
