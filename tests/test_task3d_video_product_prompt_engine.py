import asyncio
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import bot
import pytest
from providers.key4u_provider import Key4UConfig, Key4UProvider, join_provider_url
from video_product_system import (
    PRODUCT_FIELDS,
    VIDEO_MENU_ROWS,
    VIDEO_PACKAGE_REGISTRY,
    VIDEO_PRODUCT_REGISTRY,
    PromptVault,
    TrendSourceStore,
    VideoPromptEngine,
    VideoPromptRequest,
    bundle_to_markdown,
    provider_curl_examples,
    registry_audit,
    validate_package_selection,
    validate_video_prompt_bundle,
)


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


class _FakeMessage:
    chat_id = 123456

    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))
        return None


class _FakeQuery:
    def __init__(self, user_id: int, data: str):
        self.from_user = SimpleNamespace(id=user_id, first_name="Task3D")
        self.data = data
        self.message = _FakeMessage()
        self.answered = False
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answered = True

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))
        return None


class _ImmutableDataQuery:
    """Matches Telegram's read-only callback data behavior more closely."""

    def __init__(self, user_id: int, data: str):
        self.from_user = SimpleNamespace(id=user_id, first_name="Task3D")
        self._data = data
        self.message = _FakeMessage()
        self.answered = False
        self.edits = []

    @property
    def data(self):
        return self._data

    async def answer(self, *args, **kwargs):
        self.answered = True

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))
        return None


def _press_vproduct(user_id: int, product_id: str, data: str):
    bot.clear_video_session(user_id)
    bot.task3d_session_step(user_id, "intro", product_id=product_id, return_to="menu|main_video")
    query = _FakeQuery(user_id, data)
    update = SimpleNamespace(callback_query=query)
    asyncio.run(bot.handle_video_product_callback(update, SimpleNamespace()))
    return query, bot.get_video_session(user_id)


def _bundle(product_id="storyboard_prompt", shots=9, package_id=""):
    return VideoPromptEngine().build(
        VideoPromptRequest(
            product_id=product_id,
            user_topic="mèo cam mập trong công viên",
            platform="TikTok/Reels",
            aspect_ratio="9:16",
            duration=max(6, shots * 4),
            package_id=package_id,
            style="cute 3D cinematic",
            shot_count=shots,
            scene_count=shots,
        )
    )


def test_video_menu_all_buttons_have_product_registry():
    markup = bot.main_video_keyboard("vi")
    assert len(markup.inline_keyboard) == 7
    assert [len(row) for row in markup.inline_keyboard] == [2, 2, 2, 2, 2, 2, 2]
    callbacks = _callbacks(markup)
    for product_id in VIDEO_PRODUCT_REGISTRY:
        assert f"vproduct|open|{product_id}" in callbacks
    assert callbacks[-1] == "menu|main"


def test_video_menu_no_dead_buttons():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert 'CallbackQueryHandler(handle_video_product_callback, pattern=r"^vproduct\\|")' in source
    audit = registry_audit()
    assert audit["valid"], audit
    assert audit["wrong_parent_routes"] == []


def test_video_public_copy_no_technical_schema_terms():
    forbidden = (
        "topic|product|niche", "plan|script|prompt_pack", "input_type", "output_type",
        "provider_required", "prompt_pack", "rendered_video", "camera_motion_prompt",
        "local_mp4", "product_id", "registry", "schema", "free_or_paid",
    )
    for product_id in VIDEO_PRODUCT_REGISTRY:
        public_text = bot.task3d_product_intro_text(product_id, "vi")
        labels = " ".join(_labels(bot.task3d_product_intro_keyboard(product_id, "vi")))
        combined = f"{public_text}\n{labels}".lower()
        for term in forbidden:
            assert term.lower() not in combined, (product_id, term, combined)


def test_video_trend_intro_has_today_trends_button():
    labels = _labels(bot.task3d_product_intro_keyboard("video_trend", "vi"))
    assert "🔥 Xem trend hôm nay" in labels
    assert "200 Xu" not in " ".join(labels)


def test_video_trend_intro_has_custom_topic_button():
    labels = _labels(bot.task3d_product_intro_keyboard("video_trend", "vi"))
    assert "✍️ Nhập chủ đề riêng" in labels


def test_video_idea_copy_plain_vietnamese():
    text = bot.task3d_product_intro_text("video_idea", "vi")
    assert "Bạn nhập sản phẩm" in text
    assert "topic|product" not in text


def test_storyboard_copy_plain_vietnamese():
    text = bot.task3d_product_intro_text("storyboard_prompt", "vi")
    assert "storyboard 6/9/12/16 cảnh" in text
    assert "prompt_pack" not in text


def test_motion_prompt_copy_plain_vietnamese():
    text = bot.task3d_product_intro_text("motion_prompt", "vi")
    assert "Mô tả cảnh" in " ".join(_labels(bot.task3d_product_intro_keyboard("motion_prompt", "vi")))
    assert "camera_motion_prompt" not in text


def test_image_to_video_copy_plain_vietnamese():
    text = bot.task3d_product_intro_text("image_to_video", "vi")
    assert "Gửi 1–4 ảnh" in text
    assert "rendered_video" not in text


def test_frame_video_copy_plain_vietnamese():
    text = bot.task3d_product_intro_text("frame_video_local", "vi")
    assert "Ghép ảnh thành video" in text
    assert "local_mp4" not in text


@pytest.mark.parametrize("product_id", sorted(VIDEO_PRODUCT_REGISTRY))
def test_every_product_intro_returns_to_its_containing_video_menu(product_id):
    assert VIDEO_PRODUCT_REGISTRY[product_id]["parent_menu_callback"] == "menu|main_video"
    assert "menu|main_video" in _callbacks(bot.task3d_product_intro_keyboard(product_id, "vi"))


def test_preserved_legacy_product_roots_return_to_video_menu():
    legacy_root_markups = (
        bot.video_frame_intro_keyboard("vi"),
        bot.video_self_scene_ai_keyboard("vi"),
        bot.video_reference_hub_keyboard("vi"),
        bot.music_tools_keyboard("vi", back_callback="menu|main_video"),
        bot.video_editor_menu_keyboard("vi"),
    )
    for markup in legacy_root_markups:
        assert "menu|main_video" in _callbacks(markup)


def test_trend_today_button_returns_3_to_5_ideas():
    query, session = _press_vproduct(993101, "video_trend", "vproduct|trend_today")
    ideas = session["draft"]["trend_ideas"]
    assert query.answered is True
    assert session["current_step"] == "trend_ideas"
    assert 3 <= len(ideas) <= 5
    assert "Gợi ý trend hôm nay" in query.edits[-1][0]
    bot.clear_video_session(993101)


def test_trend_seed_cache_works_without_external_api(tmp_path):
    store = TrendSourceStore(tmp_path / "missing.json")
    ideas = store.list_sources(limit=5)
    assert 3 <= len(ideas) <= 5
    assert store.status()["source"] == "built_in_seed"


def test_trend_refresh_command_admin_only():
    source = inspect.getsource(bot.cmd_trend_source_refresh)
    assert "if not is_admin_user" in source
    assert "Không scrape web" in source


def test_trend_stale_cache_does_not_block_public(tmp_path):
    store = TrendSourceStore(tmp_path / "old.json")
    (tmp_path / "old.json").write_text(json.dumps({"updated_at": "2000-01-01T00:00:00+00:00", "sources": []}), encoding="utf-8")
    assert store.status()["stale"] is True
    assert store.list_sources(limit=3)


def test_trend_select_generates_hook_script_storyboard_prompt():
    user_id = 993102
    _press_vproduct(user_id, "video_trend", "vproduct|trend_today")
    query = _FakeQuery(user_id, "vproduct|trend_select|0")
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    session = bot.get_video_session(user_id)
    assert session["current_step"] == "style"
    prepared = session["draft"]["prepared_prompt_bundle"]
    assert prepared["trend_hooks"]
    for callback in ("vproduct|style|ugc", "vproduct|color|bright", "vproduct|motion|skip"):
        query = _FakeQuery(user_id, callback)
        asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    session = bot.get_video_session(user_id)
    bundle = session["draft"]["prompt_bundle"]
    assert session["current_step"] == "result"
    assert bundle["trend_hooks"]
    assert bundle["script"]
    assert bundle["storyboard_panels"]
    assert bundle["video_prompts"]
    assert bundle["caption"]
    bot.clear_video_session(user_id)


def test_trend_does_not_charge_or_call_provider():
    user_id = 993103
    _press_vproduct(user_id, "video_trend", "vproduct|trend_today")
    query = _FakeQuery(user_id, "vproduct|trend_select|0")
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    session = bot.get_video_session(user_id)
    assert session["draft"]["provider_called"] is False
    assert session["draft"]["xu_charged"] == 0
    bot.clear_video_session(user_id)


def test_video_trend_input_button_sets_waiting_topic():
    query, session = _press_vproduct(993104, "video_trend", "vproduct|trend_custom")
    assert session["current_step"] == "collect_input"
    assert session["draft"]["input_mode"] == "text"
    assert "sản phẩm/chủ đề" in query.edits[-1][0]
    bot.clear_video_session(993104)


def test_video_idea_input_button_sets_waiting_topic():
    query, session = _press_vproduct(993105, "video_idea", "vproduct|input_text|video_idea")
    assert session["current_step"] == "collect_input"
    assert session["draft"]["input_mode"] == "text"
    assert "sản phẩm" in query.edits[-1][0]
    bot.clear_video_session(993105)


def test_storyboard_input_button_sets_waiting_topic():
    query, session = _press_vproduct(993106, "storyboard_prompt", "vproduct|input_text|storyboard_prompt")
    assert session["current_step"] == "collect_input"
    assert session["draft"]["input_mode"] == "text"
    assert "storyboard" in query.edits[-1][0]
    bot.clear_video_session(993106)


def test_motion_prompt_input_button_sets_waiting_scene_description():
    query, session = _press_vproduct(993107, "motion_prompt", "vproduct|input_text|motion_prompt")
    assert session["current_step"] == "collect_input"
    assert session["draft"]["input_mode"] == "text"
    assert "Mô tả cảnh" in query.edits[-1][0]
    bot.clear_video_session(993107)


def test_image_to_video_send_image_button_sets_waiting_images():
    query, session = _press_vproduct(993108, "image_to_video", "vproduct|input_media|image_to_video")
    assert session["current_step"] == "collect_input"
    assert session["draft"]["input_mode"] == "media"
    assert "1–4 ảnh" in query.edits[-1][0]
    bot.clear_video_session(993108)


def test_frame_video_start_button_sets_waiting_images(monkeypatch):
    monkeypatch.setattr(bot, "FRAME_VIDEO_ENABLED", True)
    monkeypatch.setattr(bot, "FRAME_VIDEO_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "FRAME_VIDEO_REQUIRE_LOCAL_WORKER", False)
    monkeypatch.setattr(bot, "FRAME_VIDEO_DIRECT_RENDER_ENABLED", True)
    monkeypatch.setattr(bot, "frame_video_active_jobs_count", lambda: 0)
    user_id = 993109
    bot.clear_video_session(user_id)
    query = _FakeQuery(user_id, "framevideo|start")
    asyncio.run(bot.handle_frame_video_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    state = bot.get_frame_video_state(user_id)
    assert state["step"] == "collect"
    assert state["photos"] == []
    bot.clear_frame_video_state(user_id)


def test_free_products_do_not_show_packages_before_prompt_output():
    for product_id in ("video_trend", "video_idea", "storyboard_prompt", "motion_prompt"):
        labels = " ".join(_labels(bot.task3d_product_intro_keyboard(product_id, "vi")))
        assert "200 Xu" not in labels
        assert "300 Xu" not in labels
        assert "400 Xu" not in labels


def test_use_to_create_video_shows_all_business_packages_only_after_output():
    user_id = 993110
    bot.clear_video_session(user_id)
    bundle = bot.task3d_trend_output_from_source(bot.TASK3D_TREND_STORE.list_sources(limit=1)[0])
    session = bot.task3d_session_step(user_id, "result", product_id="video_trend", prompt_bundle=bundle)
    labels = _labels(bot.task3d_result_keyboard("video_trend", "vi"))
    assert "🎬 Dùng để tạo video" in labels
    assert not any("200 Xu" in label or "300 Xu" in label or "400 Xu" in label for label in labels)
    tier_labels = _labels(bot.video_finalization_tier_keyboard("vi"))
    tier_text = bot.video_finalization_tier_text({}, "vi")
    for price in ("200 Xu", "300 Xu", "400 Xu", "500 Xu", "600 Xu", "800 Xu", "1000 Xu", "1200 Xu", "1500 Xu"):
        assert any(price in label for label in tier_labels)
        assert price in tier_text
    callbacks = _callbacks(bot.video_finalization_tier_keyboard("vi"))
    assert {
        "vfinal|tier|low", "vfinal|tier|basic", "vfinal|tier|common",
        "vfinal|tier|advanced", "vfinal|tier|standard", "vfinal|tier|high",
        "vfinal|tier|future_1000", "vfinal|tier|future_1200", "vfinal|tier|future_1500",
    } <= set(callbacks)
    assert "đang ẩn" not in tier_text.lower()
    assert "kiểm soát chi phí" not in tier_text.lower()
    assert validate_package_selection("video_trend", "package_200", ["none"])["ok"] is True
    bot.clear_video_session(user_id)


def test_video_ai_real_shows_packages_after_prompt_exists():
    user_id = 993111
    bot.clear_video_session(user_id)
    labels = _labels(bot.task3d_product_intro_keyboard("video_ai_real", "vi"))
    assert not any("200 Xu" in label or "300 Xu" in label or "400 Xu" in label for label in labels)
    bundle = _bundle(product_id="video_ai_real", shots=1)
    bot.task3d_session_step(user_id, "result", product_id="video_ai_real", prompt_bundle=bundle.to_dict())
    assert "🎬 Dùng để tạo video" in _labels(bot.task3d_result_keyboard("video_ai_real", "vi"))
    bot.clear_video_session(user_id)


def test_video_ai_real_intro_no_motion_button():
    markup = bot.task3d_product_intro_keyboard("video_ai_real", "vi")
    labels = _labels(markup)
    callbacks = _callbacks(markup)
    for label in ("💡 Gợi ý ý tưởng", "✍️ Nhập prompt", "🔥 Trend hôm nay", "📷 Gửi ảnh tham khảo"):
        assert label in labels
    assert "🎥 Gợi ý chuyển động" not in labels
    assert "vproduct|ideas|video_ai_real" in callbacks
    assert "vproduct|motion_suggest|video_ai_real" not in callbacks
    assert "menu|main_video" in callbacks
    assert [[button.text for button in row] for row in markup.inline_keyboard] == [
        ["💡 Gợi ý ý tưởng", "✍️ Nhập prompt"],
        ["🔥 Trend hôm nay", "📷 Gửi ảnh tham khảo"],
        ["⬅️ Menu video", "🏠 Menu chính"],
    ]


def test_all_video_products_have_guided_flow():
    assert set(bot.TASK3D_GUIDED_FLOW_STEPS) == set(VIDEO_PRODUCT_REGISTRY)
    for product_id, steps in bot.TASK3D_GUIDED_FLOW_STEPS.items():
        assert steps, product_id
        assert "menu|main_video" in _callbacks(bot.task3d_product_intro_keyboard(product_id, "vi"))


def test_guidance_buttons_live_in_guided_steps_not_product_intro():
    premature = {"🎥 Gợi ý chuyển động", "➕ Thêm cảnh", "⏭ Bỏ qua thêm cảnh", "⏭ Bỏ qua add-on"}
    for product_id in ("video_ai_real", "storyboard_prompt", "motion_prompt", "image_to_video", "script_image_video", "multi_scene_film", "self_shot_scene_change"):
        assert premature.isdisjoint(set(_labels(bot.task3d_product_intro_keyboard(product_id, "vi"))))
    assert "⏭ Dùng mặc định" in _labels(bot.task3d_style_keyboard("vi", "video_ai_real"))
    assert "⏭ Dùng mặc định" in _labels(bot.task3d_color_mood_keyboard("vi"))
    assert "⏭ Bỏ qua" in _labels(bot.task3d_motion_keyboard("vi", "video_ai_real"))
    assert "⏭ Bỏ qua" in _labels(bot.task3d_extra_scene_keyboard("vi"))
    assert "🖼 Gợi ý tạo ảnh" in _labels(bot.task3d_image_plan_keyboard("vi"))


def test_video_ai_real_motion_step_after_prompt_or_image():
    user_id = 993216
    _press_vproduct(user_id, "video_ai_real", "vproduct|ideas|video_ai_real")
    query = _FakeQuery(user_id, "vproduct|idea_select|0")
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert bot.get_video_session(user_id)["current_step"] == "style"
    assert "🎥 Gợi ý chuyển động" not in _labels(bot.task3d_product_intro_keyboard("video_ai_real", "vi"))
    query = _FakeQuery(user_id, "vproduct|style|realistic")
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert bot.get_video_session(user_id)["current_step"] == "color"
    query = _FakeQuery(user_id, "vproduct|color|warm")
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert bot.get_video_session(user_id)["current_step"] == "movement"
    assert "Slow push-in" in _labels(bot.task3d_motion_keyboard("vi", "video_ai_real"))
    bot.clear_video_session(user_id)


def test_video_ai_real_style_color_motion_sequence():
    assert bot.task3d_guided_steps("video_ai_real") == ("style", "color", "movement", "result")
    assert "🎬 Chân thật" in _labels(bot.task3d_style_keyboard("vi", "video_ai_real"))
    assert "Ấm áp" in _labels(bot.task3d_color_mood_keyboard("vi"))
    assert "Orbit shot" in _labels(bot.task3d_motion_keyboard("vi", "video_ai_real"))


def test_guided_flow_has_style_color_motion_scene_or_skip_where_applicable():
    style_products = {"video_trend", "video_idea", "storyboard_prompt", "image_to_video", "video_ai_real", "script_image_video", "self_shot_scene_change", "multi_scene_film", "video_reference"}
    color_products = {"video_trend", "storyboard_prompt", "image_to_video", "video_ai_real", "script_image_video", "multi_scene_film"}
    motion_products = {"video_trend", "motion_prompt", "image_to_video", "video_ai_real", "self_shot_scene_change"}
    scene_products = {"storyboard_prompt", "script_image_video", "multi_scene_film"}
    for product_id in style_products:
        assert "style" in bot.task3d_guided_steps(product_id)
    for product_id in color_products:
        assert "color" in bot.task3d_guided_steps(product_id)
    for product_id in motion_products:
        assert "movement" in bot.task3d_guided_steps(product_id)
    for product_id in scene_products:
        assert "extra_scene" in bot.task3d_guided_steps(product_id)
    assert "⏭ Dùng mặc định" in _labels(bot.task3d_style_keyboard("vi", "storyboard_prompt"))
    assert "⏭ Dùng mặc định" in _labels(bot.task3d_color_mood_keyboard("vi"))
    assert "⏭ Bỏ qua" in _labels(bot.task3d_motion_keyboard("vi", "image_to_video"))
    assert "⏭ Bỏ qua" in _labels(bot.task3d_extra_scene_keyboard("vi"))


def test_optional_skip_continues_to_prompt_output():
    user_id = 993217
    bot.clear_video_session(user_id)
    bot.task3d_session_step(user_id, "style", product_id="video_ai_real", topic="video thử")
    for callback in ("vproduct|style|default", "vproduct|color|default", "vproduct|motion|skip"):
        query = _FakeQuery(user_id, callback)
        asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    session = bot.get_video_session(user_id)
    assert session["current_step"] == "result"
    assert session["draft"]["prompt_bundle"]
    assert session["draft"]["provider_called"] is False
    assert session["draft"]["xu_charged"] == 0
    bot.clear_video_session(user_id)


def test_existing_trend_flow_preserved_with_optional_guidance():
    labels = _labels(bot.task3d_product_intro_keyboard("video_trend", "vi"))
    assert {"🔥 Xem trend hôm nay", "✍️ Nhập chủ đề riêng", "🔁 Gợi ý trend khác"}.issubset(set(labels))
    assert bot.task3d_guided_steps("video_trend") == ("style", "color", "movement", "result")


def test_final_confirmation_keyboard_exact_two_column_export_options():
    markup = bot.video_addon_confirm_keyboard("token200", "low", "vi", {"pending_payload": {"video_tier": "low"}})
    labels_by_row = [[button.text for button in row] for row in markup.inline_keyboard]
    callbacks_by_row = [[button.callback_data for button in row] for row in markup.inline_keyboard]
    assert labels_by_row == [
        ["🎬 Xuất video", "⚙️ Đổi tùy chọn"],
        ["⬅️ Quay lại", "🏠 Menu chính"],
    ]
    assert callbacks_by_row == [
        ["videoaddon|export|token200", "vfinal|menu"],
        ["videoaddon|back", "videoaddon|main"],
    ]


def test_guided_idea_motion_and_scene_skip_are_free_prompt_steps():
    user_id = 993115
    query, session = _press_vproduct(user_id, "video_ai_real", "vproduct|ideas|video_ai_real")
    assert session["current_step"] == "idea_suggestions"
    assert "chưa xử lý video và chưa trừ Xu" in query.edits[-1][0]

    query = _FakeQuery(user_id, "vproduct|idea_select|0")
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    session = bot.get_video_session(user_id)
    assert session["current_step"] == "style"
    assert session["draft"]["provider_called"] is not True
    assert session["draft"].get("xu_charged", 0) == 0

    query = _FakeQuery(user_id, "vproduct|style|realistic")
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert bot.get_video_session(user_id)["current_step"] == "color"
    query = _FakeQuery(user_id, "vproduct|color|default")
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert bot.get_video_session(user_id)["current_step"] == "movement"
    query = _FakeQuery(user_id, "vproduct|motion|skip")
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    session = bot.get_video_session(user_id)
    assert session["current_step"] == "result"
    assert session["draft"]["motion_skipped"] is True
    assert session["draft"].get("xu_charged", 0) == 0

    bot.clear_video_session(user_id)
    bot.task3d_session_step(user_id, "extra_scene", product_id="script_image_video", topic="kịch bản thử")
    query = _FakeQuery(user_id, "vproduct|scene_skip")
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    session = bot.get_video_session(user_id)
    assert session["current_step"] == "result"
    assert session["draft"]["extra_scene_skipped"] is True
    assert session["draft"].get("xu_charged", 0) == 0
    bot.clear_video_session(user_id)


def test_trend_back_from_ideas_to_intro():
    user_id = 993112
    _press_vproduct(user_id, "video_trend", "vproduct|trend_today")
    target, session = bot.task3d_back_step(user_id)
    assert target == "intro"
    assert session["product_id"] == "video_trend"
    bot.clear_video_session(user_id)


def test_trend_back_from_output_to_ideas():
    user_id = 993113
    _press_vproduct(user_id, "video_trend", "vproduct|trend_today")
    query = _FakeQuery(user_id, "vproduct|trend_select|0")
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    target, session = bot.task3d_back_step(user_id)
    assert target == "trend_ideas"
    assert session["draft"]["trend_ideas"]
    bot.clear_video_session(user_id)


def test_scene_count_back_to_package():
    finalization_source = inspect.getsource(bot.handle_video_finalization_callback)
    assert 'current_step == "scene_count"' in finalization_source
    assert 'state["step"] = "tier"' in finalization_source
    assert "video_finalization_tier_text" in finalization_source


def test_confirmation_back_to_scene_count():
    source = inspect.getsource(bot.handle_video_finalization_callback)
    assert 'current_step == "confirm"' in source
    assert "video_finalization_render_scene_count" in source


def test_no_reinput_after_back():
    user_id = 993114
    bot.clear_video_session(user_id)
    bot.task3d_session_step(user_id, "intro", product_id="image_to_video")
    bot.task3d_session_step(user_id, "collect_input", input_mode="media", source_media_ref="file-a")
    bot.task3d_session_step(user_id, "platform", input_collected=True)
    target, session = bot.task3d_back_step(user_id)
    assert target == "collect_input"
    assert session["source_media_ref"] == "file-a"
    bot.clear_video_session(user_id)


def test_task1_not_touched():
    hotfix_source = "\n".join(
        inspect.getsource(obj)
        for obj in (
            bot.task3d_product_intro_text,
            bot.task3d_product_intro_keyboard,
            bot.task3d_trend_ideas_text,
            bot.cmd_trend_source_refresh,
        )
    ).lower()
    assert "audio provider" not in hotfix_source
    assert "voice provider" not in hotfix_source
    assert "music provider" not in hotfix_source


def test_task2_not_touched():
    hotfix_source = inspect.getsource(bot.handle_video_product_callback).lower()
    assert "translation" not in hotfix_source
    assert "subtitle" not in hotfix_source
    assert "dubbing" not in hotfix_source


def test_payos_not_touched():
    hotfix_source = "\n".join(
        inspect.getsource(obj)
        for obj in (
            bot.task3d_product_intro_text,
            bot.handle_video_product_callback,
            bot.cmd_trend_source_status,
            bot.cmd_trend_source_refresh,
        )
    ).lower()
    assert "payos" not in hotfix_source
    assert "naptien" not in hotfix_source
    assert "payment webhook" not in hotfix_source


def test_result_child_buttons_return_to_the_result_menu_that_contains_them():
    assert _callbacks(bot.task3d_result_parent_keyboard("vi")) == ["vproduct|result", "menu|main"]
    source = inspect.getsource(bot.handle_video_product_callback)
    assert 'if action == "result"' in source
    assert 'callback_data="vproduct|result"' in source
    assert _callbacks(bot.task3d_scene_count_keyboard("vi"))[-2] == "vproduct|result"


def test_video_product_registry_complete():
    assert len(VIDEO_PRODUCT_REGISTRY) == 13
    for product_id, product in VIDEO_PRODUCT_REGISTRY.items():
        assert product_id == product["product_id"]
        assert not [field for field in PRODUCT_FIELDS if field not in product]
        assert product["purpose"] and product["user_input_type"] and product["output_type"]
        assert product["back_steps"] and product["next_steps"]


def test_video_free_tools_do_not_charge():
    for product_id in ("video_trend", "video_idea", "storyboard_prompt", "motion_prompt", "video_reference"):
        assert VIDEO_PRODUCT_REGISTRY[product_id]["free_or_paid"].startswith("free")
    source = inspect.getsource(bot.task3d_build_bundle_from_session)
    assert "spend_fixed_credit_info" not in source
    assert "deduct_credits" not in source


def test_video_free_tools_do_not_call_provider():
    bundle = _bundle()
    assert bundle.render_plan["provider_call_required"] is False
    assert bundle.render_plan["free_planning_only"] is True
    source = inspect.getsource(bot.task3d_build_bundle_from_session)
    assert "shopaikey_video_create" not in source
    assert "video_generation(" not in source


def test_storyboard_prompt_outputs_scene_table():
    bundle = _bundle(shots=9)
    assert len(bundle.scene_table) == 9
    assert len(bundle.shot_table) == 9
    assert len(bundle.storyboard_panels) == 9
    assert all(shot["image_prompt"] and shot["video_prompt"] for shot in bundle.shot_table)


def test_storyboard_multishot_batches():
    batches = _bundle(shots=9).render_plan["batches"]
    assert [item["shot_numbers"] for item in batches] == [[1, 2], [3, 4], [5, 6], [7, 8], [9]]


def test_script_image_video_generates_image_and_video_prompts():
    bundle = _bundle(product_id="script_image_video", shots=6)
    assert bundle.script
    assert len(bundle.image_prompts) == 6
    assert len(bundle.video_prompts) == 6
    assert all("camera" in prompt.lower() and "lighting" in prompt.lower() for prompt in bundle.video_prompts)


def test_video_ai_real_package_selection():
    for package_id in ("package_200", "package_300", "package_400", "package_500", "package_600", "package_800", "package_1000", "package_1200", "package_1500"):
        assert validate_package_selection("video_ai_real", package_id, ["none"])["ok"]


def test_video_200_free_default_can_reach_final_confirm():
    state = {"pending_payload": {"job_type": "video", "video_tier": "low", "preview_required": False}}
    callbacks = _callbacks(bot.video_addon_confirm_keyboard("token200", "low", "vi", state))
    assert "videoaddon|export|token200" in callbacks
    assert validate_package_selection("video_ai_real", "package_200", ["none"])["ok"]


def test_video_200_final_export_does_not_require_preview_artifact():
    payload = {"job_type": "video", "video_tier": "low", "base_cost": 200, "preview_required": False}
    assert bot.video_paid_preview_required(payload) is False
    assert VIDEO_PACKAGE_REGISTRY["package_200"]["preview_policy"] == "not_required"


def test_video_200_no_paid_addons():
    allowed = VIDEO_PACKAGE_REGISTRY["package_200"]["allowed_addons"]
    assert "none" in allowed
    assert "default_no_audio" in allowed
    assert not any(item in allowed for item in ("ai_music", "paid_voice", "dubbing", "translated_subtitle"))


def test_video_200_paid_addon_requires_upgrade_or_back():
    result = validate_package_selection("video_ai_real", "package_200", ["ai_music"])
    assert result["ok"] is False
    assert result["reason"] == "paid_addon_not_allowed"
    callbacks = _callbacks(bot.video_experience_tier_lock_keyboard("vi"))
    assert callbacks == ["videoaddon|upgrade_300", "videoaddon|export_back"]
    text = bot.video_experience_tier_lock_text("vi", ["paid_music"])
    assert "Gói trải nghiệm 200 Xu không dùng được tính năng có phí" in text
    assert "TOAN AAS chưa xử lý video và chưa trừ Xu" in text


def test_select_200_always_shows_final_confirmation(monkeypatch):
    user_id = 993220
    bot.clear_video_addon_state(user_id)
    monkeypatch.setattr(bot, "get_user", lambda _uid: (5000, None, None))
    monkeypatch.setattr(bot, "record_shopaikey_billing_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(bot, "set_shopaikey_pending_confirmation", lambda *_args, **_kwargs: "token-select-200")
    monkeypatch.setattr(bot, "active_package_item_for_user", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bot, "check_video_beta_200_limit", lambda _uid: {"ok": True, "user_limit": 3})
    state = bot.set_video_addon_state(user_id, {
        "source": "ai",
        "video_tier": "low",
        "current_video_music_option": "ai_music",
        "current_video_music_choice": "ai_music",
        "pending_payload": {
            "job_type": "video",
            "video_tier": "low",
            "prompt": "Prompt video đã sẵn sàng",
            "original_prompt": "Prompt video đã sẵn sàng",
            "music_option": "ai_music",
            "video_finalization_confirmed": True,
        },
    })
    query = _FakeQuery(user_id, "vfinal|tier|low")
    asyncio.run(bot.finalize_video_addon_confirmation(query, user_id, state, "vi"))
    text, kwargs = query.edits[-1]
    assert "Xác nhận xuất video" in text
    assert "không dùng được tính năng có phí" not in text
    assert "videoaddon|export|token-select-200" in _callbacks(kwargs["reply_markup"])

    block_query = _FakeQuery(user_id, "videoaddon|export|token-select-200")
    asyncio.run(bot.handle_video_addon_callback(SimpleNamespace(callback_query=block_query), SimpleNamespace()))
    assert "không dùng được tính năng có phí" in block_query.edits[-1][0]

    back_query = _FakeQuery(user_id, "videoaddon|export_back")
    asyncio.run(bot.handle_video_addon_callback(SimpleNamespace(callback_query=back_query), SimpleNamespace()))
    assert "Xác nhận xuất video" in back_query.edits[-1][0]

    upgrade_query = _FakeQuery(user_id, "videoaddon|upgrade_300")
    asyncio.run(bot.handle_video_addon_callback(SimpleNamespace(callback_query=upgrade_query), SimpleNamespace()))
    upgraded = bot.get_video_finalization_state(user_id)
    assert upgraded["selected_video_tier"] == "basic"
    assert upgraded["step"] == "scene_count"
    assert not bot.get_video_addon_state(user_id)
    assert "300 Xu" in upgrade_query.edits[-1][0]
    upgrade_callbacks = _callbacks(upgrade_query.edits[-1][1]["reply_markup"])
    assert "vfinal|scene_count|1" in upgrade_callbacks
    assert "vfinal|scene_count|3" in upgrade_callbacks
    assert not any(value.startswith("videoaddon|export|") for value in upgrade_callbacks)
    bot.clear_video_addon_state(user_id)


def test_200_paid_addon_blocks_only_on_export_action(monkeypatch):
    user_id = 993221
    bot.clear_video_addon_state(user_id)
    pending = {
        "job_type": "video", "video_tier": "low", "prompt": "Prompt sẵn sàng",
        "original_prompt": "Prompt sẵn sàng", "music_option": "ai_music",
    }
    token = bot.set_shopaikey_pending_confirmation(user_id, pending)
    bot.set_video_addon_state(user_id, {
        "source": "ai", "video_tier": "low", "current_video_music_option": "ai_music",
        "current_video_music_choice": "ai_music", "pending_confirm_token": token,
        "pending_payload": pending,
    })
    query = _FakeQuery(user_id, f"videoaddon|export|{token}")
    asyncio.run(bot.handle_video_addon_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    text, kwargs = query.edits[-1]
    assert "Gói trải nghiệm 200 Xu không dùng được tính năng có phí" in text
    assert _callbacks(kwargs["reply_markup"]) == ["videoaddon|upgrade_300", "videoaddon|export_back"]
    assert token in bot.SHOPAIKEY_PENDING_CONFIRMATIONS
    bot.SHOPAIKEY_PENDING_CONFIRMATIONS.pop(token, None)
    bot.clear_video_addon_state(user_id)


def test_200_free_default_export_path_allowed(monkeypatch):
    user_id = 993222
    pending = {"job_type": "video", "video_tier": "low", "prompt": "Prompt sẵn sàng", "music_option": "none"}
    token = bot.set_shopaikey_pending_confirmation(user_id, pending)
    bot.set_video_addon_state(user_id, {"source": "ai", "video_tier": "low", "pending_confirm_token": token, "pending_payload": pending})
    delegated = {}

    async def fake_confirm(update, context, callback_data_override=""):
        delegated["callback"] = callback_data_override or update.callback_query.data
        await update.callback_query.answer()
        return None

    monkeypatch.setattr(bot, "shopaikey_public_generation_guard", lambda _kind: (True, "ready"))
    monkeypatch.setattr(bot, "video_addon_runtime_guard", lambda _pending: {"ok": True})
    monkeypatch.setattr(bot, "handle_shopaikey_public_callback", fake_confirm)
    query = _FakeQuery(user_id, f"videoaddon|export|{token}")
    asyncio.run(bot.handle_video_addon_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert delegated["callback"] == f"shopai|confirm|{token}"
    assert query.answered is True
    bot.SHOPAIKEY_PENDING_CONFIRMATIONS.pop(token, None)
    bot.clear_video_addon_state(user_id)


def test_video_export_button_routes_to_export_dispatcher():
    source = inspect.getsource(bot.handle_video_addon_callback)
    assert 'if action == "export"' in source
    assert "handle_video_export_confirm(update, context, token)" in source


def test_200_default_male_voice_is_free():
    state = {
        "source": "ai",
        "video_tier": "low",
        "current_video_dubbing_option": "dub_original",
        "current_video_voice_choice": "default_male",
        "pending_payload": {
            "job_type": "video",
            "video_tier": "low",
            "base_cost": 200,
            "dubbing_option": "dub_original",
            "voice_choice": "default_male",
        },
    }
    classified = bot.classify_video_addons_for_package(state)
    assert classified["allowed_for_200"] is True
    assert classified["paid_addons"] == []
    assert classified["default_voice_free"] is True
    assert bot.validate_video_tier_selection(state, "low")["ok"] is True


def test_200_default_female_voice_is_free():
    state = {
        "source": "ai",
        "video_tier": "low",
        "current_video_dubbing_option": "dub_original",
        "current_video_voice_choice": "default_female",
        "pending_payload": {
            "job_type": "video",
            "video_tier": "low",
            "base_cost": 200,
            "dubbing_option": "dub_original",
            "voice_choice": "default_female",
        },
    }
    classified = bot.classify_video_addons_for_package(state)
    assert classified["allowed_for_200"] is True
    assert classified["paid_addons"] == []
    normalized = bot.normalize_video_export_payload_for_classifier(state, classified)
    assert normalized["pending_payload"]["dubbing_option"] == "none"
    assert normalized["pending_payload"]["voice_is_free"] is True


def test_200_invoice_total_200_passes_and_total_above_200_blocks():
    base_state = {
        "source": "ai",
        "video_tier": "low",
        "pending_payload": {"job_type": "video", "video_tier": "low", "base_cost": 200, "music_option": "none"},
        "current_video_price_preview": {"total_xu": 200, "raw_total_xu": 200, "addon_xu": 0},
    }
    assert bot.classify_video_addons_for_package(base_state)["allowed_for_200"] is True

    paid_state = {
        **base_state,
        "current_video_price_preview": {"total_xu": 210, "raw_total_xu": 210, "addon_xu": 10},
        "pending_payload": {**base_state["pending_payload"], "base_cost": 210},
    }
    classified = bot.classify_video_addons_for_package(paid_state)
    assert classified["allowed_for_200"] is False
    assert classified["paid_total_xu"] == 10
    assert bot.validate_video_tier_selection(paid_state, "low")["blocked"] is True


def test_200_custom_voice_is_paid_addon():
    state = {
        "source": "ai",
        "video_tier": "low",
        "current_video_dubbing_option": "dub_original",
        "current_video_voice_choice": "advanced_dubbing",
        "pending_payload": {
            "job_type": "video",
            "video_tier": "low",
            "base_cost": 200,
            "dubbing_option": "dub_original",
            "voice_choice": "advanced_dubbing",
        },
    }
    classified = bot.classify_video_addons_for_package(state)
    assert classified["allowed_for_200"] is False
    assert any(item["key"] in {"paid_voice", "dubbing"} for item in classified["paid_addons"])


def test_200_export_with_free_default_voice_reaches_old_video_core(monkeypatch):
    user_id = 993224
    pending = {
        "job_type": "video",
        "video_tier": "low",
        "prompt": "Prompt sẵn sàng",
        "original_prompt": "Prompt sẵn sàng",
        "base_cost": 200,
        "preview_required": False,
        "dubbing_option": "dub_original",
        "voice_choice": "default_male",
    }
    token = bot.set_shopaikey_pending_confirmation(user_id, pending)
    bot.set_video_addon_state(user_id, {
        "source": "ai",
        "video_tier": "low",
        "current_video_dubbing_option": "dub_original",
        "current_video_voice_choice": "default_male",
        "pending_confirm_token": token,
        "pending_payload": pending,
    })
    delegated = {}

    async def fake_confirm(update, context, callback_data_override=""):
        delegated["callback"] = callback_data_override or update.callback_query.data
        delegated["pending"] = dict(bot.SHOPAIKEY_PENDING_CONFIRMATIONS[token])
        await update.callback_query.answer()
        return None

    monkeypatch.setattr(bot, "shopaikey_public_generation_guard", lambda _kind: (True, "ready"))
    monkeypatch.setattr(bot, "handle_shopaikey_public_callback", fake_confirm)
    query = _FakeQuery(user_id, f"videoaddon|export|{token}")
    asyncio.run(bot.handle_video_addon_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert delegated["callback"] == f"shopai|confirm|{token}"
    assert delegated["pending"]["dubbing_option"] == "none"
    assert delegated["pending"]["voice_is_free"] is True
    assert query.answered is True
    bot.SHOPAIKEY_PENDING_CONFIRMATIONS.pop(token, None)
    bot.clear_video_addon_state(user_id)


def test_200_paid_addon_block_only_after_export_with_total_above_200(monkeypatch):
    user_id = 993225
    pending = {
        "job_type": "video",
        "video_tier": "low",
        "prompt": "Prompt sẵn sàng",
        "base_cost": 210,
        "music_option": "none",
        "video_price_preview": {"total_xu": 210, "raw_total_xu": 210, "addon_xu": 10},
    }
    token = bot.set_shopaikey_pending_confirmation(user_id, pending)
    bot.set_video_addon_state(user_id, {
        "source": "ai",
        "video_tier": "low",
        "current_video_price_preview": {"total_xu": 210, "raw_total_xu": 210, "addon_xu": 10},
        "pending_confirm_token": token,
        "pending_payload": pending,
    })
    query = _FakeQuery(user_id, f"videoaddon|export|{token}")
    asyncio.run(bot.handle_video_addon_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    text, kwargs = query.edits[-1]
    assert "Gói trải nghiệm 200 Xu không dùng được tính năng có phí" in text
    assert _callbacks(kwargs["reply_markup"]) == ["videoaddon|upgrade_300", "videoaddon|export_back"]
    assert token in bot.SHOPAIKEY_PENDING_CONFIRMATIONS
    bot.SHOPAIKEY_PENDING_CONFIRMATIONS.pop(token, None)
    bot.clear_video_addon_state(user_id)


def test_300_export_stays_in_video_flow_and_uses_same_dispatcher(monkeypatch):
    user_id = 993226
    pending = {
        "job_type": "video",
        "video_tier": "basic",
        "prompt": "Prompt sẵn sàng",
        "base_cost": 300,
        "dubbing_option": "dub_original",
        "voice_choice": "default_female",
    }
    token = bot.set_shopaikey_pending_confirmation(user_id, pending)
    bot.set_video_addon_state(user_id, {
        "source": "ai",
        "video_tier": "basic",
        "current_video_dubbing_option": "dub_original",
        "current_video_voice_choice": "default_female",
        "pending_confirm_token": token,
        "pending_payload": pending,
    })
    delegated = {}

    async def fake_confirm(update, context, callback_data_override=""):
        delegated["callback"] = callback_data_override or update.callback_query.data
        await update.callback_query.answer()
        return None

    monkeypatch.setattr(bot, "shopaikey_public_generation_guard", lambda _kind: (True, "ready"))
    monkeypatch.setattr(bot, "handle_shopaikey_public_callback", fake_confirm)
    query = _FakeQuery(user_id, f"videoaddon|export|{token}")
    asyncio.run(bot.handle_video_addon_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert delegated["callback"] == f"shopai|confirm|{token}"
    assert not query.edits
    bot.SHOPAIKEY_PENDING_CONFIRMATIONS.pop(token, None)
    bot.clear_video_addon_state(user_id)


def test_task3d_session_builds_legacy_shopaikey_order():
    session = {
        "product_id": "video_trend",
        "topic": "mèo cam đi cà phê",
        "aspect_ratio": "9:16",
        "style": "cinematic",
        "source_media_ref": "telegram-file-ref",
        "draft": {
            "selected_motion": "camera dolly in",
            "prompt_bundle": {
                "bundle_id": "bundle-legacy-1",
                "script": "Kịch bản Task 3D",
                "video_prompts": ["Mèo cam bước vào quán cà phê, camera dolly in"],
                "shot_table": [{"video_prompt": "Mèo cam bước vào quán cà phê", "duration_seconds": 8}],
            },
        },
    }
    addon = {
        "source": "ai",
        "video_tier": "basic",
        "pending_payload": {"job_type": "video", "video_tier": "basic", "base_cost": 300},
        "current_video_price_preview": {"total_xu": 300, "addon_xu": 0},
    }
    legacy = bot.build_legacy_shopaikey_video_order_from_task3d_session(session, 99100, addon)
    assert legacy["job_type"] == "video"
    assert legacy["product_id"] == "video_trend"
    assert legacy["prompt"] == "Mèo cam bước vào quán cà phê, camera dolly in"
    assert legacy["video_tier"] == "basic"
    assert legacy["task3d_package_id"] == "package_300"
    assert legacy["base_cost"] == 300
    assert legacy["duration_seconds"] == 8
    assert legacy["source_media_ref"] == "telegram-file-ref"
    assert legacy["aspect_ratio"] == "9:16"
    assert legacy["motion"] == "camera dolly in"
    assert legacy["preview_required"] is False
    assert legacy["task3d_legacy_order"] is True


def test_export_button_uses_old_shopaikey_core_without_mutating_telegram_query(monkeypatch):
    user_id = 993227
    bot.clear_video_session(user_id)
    bot.task3d_session_step(user_id, "result", product_id="video_ai_real", topic="Prompt Task 3D")
    pending = {"job_type": "video", "video_tier": "low", "prompt": "Prompt xuất video", "base_cost": 200}
    token = bot.set_shopaikey_pending_confirmation(user_id, pending)
    bot.set_video_addon_state(user_id, {
        "source": "ai", "video_tier": "low", "pending_confirm_token": token, "pending_payload": pending,
        "current_video_price_preview": {"total_xu": 200, "addon_xu": 0},
    })
    delegated = {}

    async def fake_old_core(update, context, callback_data_override=""):
        delegated["callback"] = callback_data_override or update.callback_query.data
        delegated["legacy"] = dict(bot.SHOPAIKEY_PENDING_CONFIRMATIONS[token])
        await update.callback_query.answer()

    monkeypatch.setattr(bot, "shopaikey_public_generation_guard", lambda _kind: (True, "ready"))
    monkeypatch.setattr(bot, "handle_shopaikey_public_callback", fake_old_core)
    original_callback = f"videoaddon|export|{token}"
    query = _ImmutableDataQuery(user_id, original_callback)
    asyncio.run(bot.handle_video_addon_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert query.data == original_callback
    assert delegated["callback"] == f"shopai|confirm|{token}"
    assert delegated["legacy"]["task3d_legacy_order"] is True
    assert delegated["legacy"]["prompt"] == "Prompt xuất video"
    assert query.answered is True
    bot.SHOPAIKEY_PENDING_CONFIRMATIONS.pop(token, None)
    bot.clear_video_addon_state(user_id)
    bot.clear_video_session(user_id)


@pytest.mark.parametrize("tier,cost", [("basic", 300), ("common", 400), ("future_1000", 1000)])
def test_paid_packages_call_old_shopaikey_core_for_now(monkeypatch, tier, cost):
    user_id = 994000 + cost
    pending = {"job_type": "video", "video_tier": tier, "prompt": f"Prompt gói {cost}", "base_cost": cost}
    token = bot.set_shopaikey_pending_confirmation(user_id, pending)
    bot.set_video_addon_state(user_id, {
        "source": "ai", "video_tier": tier, "pending_confirm_token": token, "pending_payload": pending,
        "current_video_price_preview": {"total_xu": cost, "addon_xu": 0},
    })
    delegated = {}

    async def fake_old_core(update, context, callback_data_override=""):
        delegated["callback"] = callback_data_override or update.callback_query.data
        delegated["job_type"] = bot.SHOPAIKEY_PENDING_CONFIRMATIONS[token]["job_type"]
        await update.callback_query.answer()

    monkeypatch.setattr(bot, "shopaikey_public_generation_guard", lambda _kind: (True, "ready"))
    monkeypatch.setattr(bot, "handle_shopaikey_public_callback", fake_old_core)
    query = _ImmutableDataQuery(user_id, f"videoaddon|export|{token}")
    asyncio.run(bot.handle_video_addon_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert delegated == {"callback": f"shopai|confirm|{token}", "job_type": "video"}
    assert not query.edits
    bot.SHOPAIKEY_PENDING_CONFIRMATIONS.pop(token, None)
    bot.clear_video_addon_state(user_id)


def test_export_exception_has_clean_public_message_and_admin_diagnostic(monkeypatch):
    user_id = 993228
    pending = {"job_type": "video", "video_tier": "basic", "prompt": "Prompt giữ nguyên", "base_cost": 300}
    token = bot.set_shopaikey_pending_confirmation(user_id, pending)
    bot.set_video_addon_state(user_id, {
        "source": "ai", "video_tier": "basic", "pending_confirm_token": token, "pending_payload": pending,
        "current_video_price_preview": {"total_xu": 300, "addon_xu": 0},
    })

    async def broken_old_core(update, context, callback_data_override=""):
        raise RuntimeError("provider token=super-secret-value")

    monkeypatch.setattr(bot, "shopaikey_public_generation_guard", lambda _kind: (True, "ready"))
    monkeypatch.setattr(bot, "handle_shopaikey_public_callback", broken_old_core)
    query = _ImmutableDataQuery(user_id, f"videoaddon|export|{token}")
    asyncio.run(bot.handle_video_addon_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    text, kwargs = query.edits[-1]
    assert text == "TOAN AAS chưa tạo được video ở bước này. Bot chưa trừ Xu. Nội dung và tùy chọn của bạn vẫn được giữ nguyên."
    assert "Có lỗi khi xử lý lệnh" not in text
    assert _callbacks(kwargs["reply_markup"]) == ["videoaddon|export_back", "videoaddon|main"]
    assert bot.VIDEO_LAST_EXPORT_ERROR["function_path"].endswith("handle_shopaikey_public_callback")
    assert bot.VIDEO_LAST_EXPORT_ERROR["exception_class"] == "RuntimeError"
    assert "super-secret-value" not in bot.VIDEO_LAST_EXPORT_ERROR["traceback"]
    assert token in bot.SHOPAIKEY_PENDING_CONFIRMATIONS
    bot.SHOPAIKEY_PENDING_CONFIRMATIONS.pop(token, None)
    bot.clear_video_addon_state(user_id)


def test_video_last_export_error_is_admin_only(monkeypatch):
    update = SimpleNamespace(effective_user=SimpleNamespace(id=123), message=_FakeMessage())
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    asyncio.run(bot.cmd_video_last_export_error(update, SimpleNamespace()))
    assert "chỉ dành cho admin" in update.message.replies[-1][0]


def test_video_last_export_error_command_registered():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert 'CommandHandler("video_last_export_error", cmd_video_last_export_error)' in source


def test_shopaikey_success_does_not_call_key4u_fallback(monkeypatch):
    calls = {"key4u": 0}

    async def primary_ok(model, prompt):
        return {"status": "PASS_SUBMITTED", "task_id": "shop-task", "model": model, "attempts": []}

    def forbidden_key4u():
        calls["key4u"] += 1
        raise AssertionError("Key4U must stay untouched while ShopAIKey works")

    monkeypatch.setattr(bot, "shopaikey_video_create_smoke_test", primary_ok)
    monkeypatch.setattr(bot, "key4u_provider_instance", forbidden_key4u)
    result = asyncio.run(bot.submit_public_video_with_key4u_fallback("veo3.1-fast", "prompt", 123))
    assert result["provider_route"] == "shopaikey"
    assert result["task_id"] == "shop-task"
    assert calls["key4u"] == 0


def test_clear_shopaikey_rejection_uses_key4u_fallback(monkeypatch):
    class FakeKey4U:
        def is_configured(self):
            return True

        async def video_generation(self, prompt="", model="", timeout_seconds=0):
            assert prompt == "prompt Task 3D"
            return {"ok": True, "status": "PASS_SUBMITTED", "task_id": "key4u-task", "model": model, "capability": "video_generate"}

    async def primary_rejected(model, prompt):
        return {"status": "FAIL_QUOTA_OR_BALANCE", "error_class": "FAIL_QUOTA_OR_BALANCE", "task_id": "", "attempts": []}

    monkeypatch.setattr(bot, "KEY4U_VIDEO_FALLBACK_ENABLED", True)
    monkeypatch.setattr(bot, "key4u_public_video_fallback_ready", lambda: True)
    monkeypatch.setattr(bot, "shopaikey_video_create_smoke_test", primary_rejected)
    monkeypatch.setattr(bot, "key4u_provider_instance", lambda: FakeKey4U())
    monkeypatch.setattr(bot, "record_provider_usage_event", lambda **kwargs: None)
    result = asyncio.run(bot.submit_public_video_with_key4u_fallback("veo3.1-fast", "prompt Task 3D", 123))
    assert result["provider_route"] == "key4u"
    assert result["task_id"] == "key4u-task"
    assert result["status"] == "PASS_SUBMITTED"


def test_ambiguous_shopaikey_timeout_does_not_fallback(monkeypatch):
    async def primary_timeout(model, prompt):
        return {"status": "FAIL_TIMEOUT", "error_class": "FAIL_TIMEOUT", "task_id": "", "attempts": []}

    monkeypatch.setattr(bot, "KEY4U_VIDEO_FALLBACK_ENABLED", True)
    monkeypatch.setattr(bot, "shopaikey_video_create_smoke_test", primary_timeout)
    monkeypatch.setattr(bot, "key4u_provider_instance", lambda: (_ for _ in ()).throw(AssertionError("unsafe duplicate fallback")))
    result = asyncio.run(bot.submit_public_video_with_key4u_fallback("veo3.1-fast", "prompt", 123))
    assert result["provider_route"] == "shopaikey"
    assert result["status"] == "FAIL_TIMEOUT"


def test_public_video_core_uses_safe_provider_fallback_wrapper():
    source = inspect.getsource(bot.handle_shopaikey_public_callback)
    assert "submit_public_video_with_key4u_fallback(model, prompt, uid, video_tier)" in source
    assert "shopaikey_video_create_smoke_test(model, prompt)" not in source
    callbacks = _callbacks(bot.public_video_submitted_keyboard("key4u-task", "vi", {"provider_route": "key4u"}))
    assert callbacks == ["menu|main"]


@pytest.mark.parametrize("tier", ["future_1000", "future_1200", "future_1500"])
def test_1000_1200_1500_use_key4u_kling_without_shopaikey(monkeypatch, tier):
    seen = {}

    class FakeKey4U:
        def is_configured(self):
            return True

        async def video_generation(self, prompt="", model="", timeout_seconds=0):
            seen["model"] = model
            return {"ok": True, "status": "PASS_SUBMITTED", "task_id": f"{tier}-task", "model": model}

    async def forbidden_shopaikey(model, prompt):
        raise AssertionError("High packages must not submit through ShopAIKey")

    monkeypatch.setattr(bot, "key4u_provider_instance", lambda: FakeKey4U())
    monkeypatch.setattr(bot, "shopaikey_video_create_smoke_test", forbidden_shopaikey)
    monkeypatch.setattr(bot, "record_provider_usage_event", lambda **kwargs: None)
    result = asyncio.run(bot.submit_public_video_with_key4u_fallback("veo3.1-fast", "prompt Kling", 123, tier))
    assert seen["model"] == "kling-video"
    assert result["provider_route"] == "key4u"
    assert result["selected_model"] == "kling-video"
    assert result["status"] == "PASS_SUBMITTED"


def test_export_bridge_allows_ready_key4u_when_shopaikey_guard_is_down(monkeypatch):
    user_id = 993229
    pending = {"job_type": "video", "video_tier": "basic", "prompt": "Prompt fallback", "base_cost": 300}
    token = bot.set_shopaikey_pending_confirmation(user_id, pending)
    bot.set_video_addon_state(user_id, {
        "source": "ai", "video_tier": "basic", "pending_confirm_token": token, "pending_payload": pending,
        "current_video_price_preview": {"total_xu": 300, "addon_xu": 0},
    })
    delegated = {}

    async def fake_old_core(update, context, callback_data_override=""):
        delegated["callback"] = callback_data_override

    monkeypatch.setattr(bot, "shopaikey_public_generation_guard", lambda _kind: (False, "shopaikey unavailable"))
    monkeypatch.setattr(bot, "key4u_public_video_fallback_ready", lambda: True)
    monkeypatch.setattr(bot, "handle_shopaikey_public_callback", fake_old_core)
    query = _ImmutableDataQuery(user_id, f"videoaddon|export|{token}")
    asyncio.run(bot.handle_video_addon_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert delegated["callback"] == f"shopai|confirm|{token}"
    assert not query.edits
    bot.SHOPAIKEY_PENDING_CONFIRMATIONS.pop(token, None)
    bot.clear_video_addon_state(user_id)


def test_200_paid_addon_block_back_and_upgrade_routes():
    callbacks = _callbacks(bot.video_experience_tier_lock_keyboard("vi"))
    assert callbacks == ["videoaddon|upgrade_300", "videoaddon|export_back"]
    source = inspect.getsource(bot.handle_video_addon_callback)
    assert 'if action == "export_back"' in source
    assert 'render_video_addon_screen(query, uid, state, "invoice", lang)' in source
    assert 'if action == "upgrade_300"' in source
    assert '"video_tier": "basic"' in source


def test_final_confirmation_two_column_buttons_all_packages():
    for tier in bot.VIDEO_PUBLIC_TIER_UI_ORDER:
        markup = bot.video_addon_confirm_keyboard(f"token-{tier}", tier, "vi", {"video_tier": tier})
        assert [[button.text for button in row] for row in markup.inline_keyboard] == [
            ["🎬 Xuất video", "⚙️ Đổi tùy chọn"],
            ["⬅️ Quay lại", "🏠 Menu chính"],
        ]


def test_export_action_guards_if_provider_unavailable(monkeypatch):
    user_id = 993223
    pending = {
        "job_type": "video", "video_tier": "low", "prompt": "Prompt sẵn sàng",
        "original_prompt": "Prompt sẵn sàng", "preview_required": False,
    }
    token = bot.set_shopaikey_pending_confirmation(user_id, pending)
    bot.set_video_addon_state(user_id, {"source": "ai", "video_tier": "low", "pending_confirm_token": token, "pending_payload": pending})
    monkeypatch.setattr(bot, "shopaikey_public_generation_guard", lambda _kind: (False, "maintenance"))
    monkeypatch.setattr(bot, "key4u_public_video_fallback_ready", lambda: False)
    query = _FakeQuery(user_id, f"videoaddon|export|{token}")
    asyncio.run(bot.handle_video_addon_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    text, kwargs = query.edits[-1]
    assert "Hệ thống tạo video đang bảo trì hoặc chưa sẵn sàng" in text
    assert "chưa xử lý và chưa trừ Xu" in text
    assert _callbacks(kwargs["reply_markup"]) == ["videoaddon|export_back", "videoaddon|main"]
    assert token in bot.SHOPAIKEY_PENDING_CONFIRMATIONS
    bot.SHOPAIKEY_PENDING_CONFIRMATIONS.pop(token, None)
    bot.clear_video_addon_state(user_id)


def test_no_prompt_vault_added_to_task3d3_public_flow():
    public_flow_source = inspect.getsource(bot.handle_video_product_callback).lower()
    assert "prompt_vault" not in public_flow_source


def test_video_200_creates_provider_job_after_confirm():
    source = inspect.getsource(bot.handle_shopaikey_public_callback)
    confirm_index = source.index('if action not in {"confirm", "package"}')
    create_index = source.index("create_shopaikey_job", confirm_index)
    provider_index = source.index("submit_public_video_with_key4u_fallback", create_index)
    deferred_charge_index = source.index("ShopAIKey video accepted", provider_index)
    assert confirm_index < create_index < provider_index < deferred_charge_index


def test_video_200_no_xu_before_confirm():
    source = inspect.getsource(bot.handle_video_finalization_callback)
    for forbidden in ("spend_fixed_credit_info(", "deduct_credits(", "charge_user("):
        assert forbidden not in source
    assert "awaiting_provider_accept" in inspect.getsource(bot.handle_shopaikey_public_callback)


def test_video_200_refund_or_no_charge_on_fail():
    source = inspect.getsource(bot.handle_shopaikey_public_callback)
    assert "provider_rejected_not_charged" in source
    assert 'refund_status="not_charged"' in source
    assert "Hệ thống tạo video đang bảo trì/nâng cấp nhẹ" in source


def test_video_200_final_export_path():
    bundle = _bundle(product_id="video_ai_real", shots=1, package_id="package_200")
    assert bundle.package_fit["fits"] is True
    assert bundle.package_fit["max_shots"] == 1


def test_video_300_package_path():
    package = VIDEO_PACKAGE_REGISTRY["package_300"]
    assert package["public_enabled"] is True
    assert package["price_xu"] == 300
    assert validate_package_selection("multi_scene_film", "package_300", ["none"])["ok"]


def test_video_400_package_path():
    package = VIDEO_PACKAGE_REGISTRY["package_400"]
    assert package["public_enabled"] is True
    assert package["max_shots"] == 4
    assert validate_package_selection("multi_scene_film", "package_400", ["none"])["ok"]


def test_video_business_packages_visible_and_open():
    labels = _labels(bot.video_finalization_tier_keyboard("vi"))
    callbacks = _callbacks(bot.video_finalization_tier_keyboard("vi"))
    for package_id in ("package_500", "package_600", "package_800", "package_1000", "package_1200", "package_1500"):
        assert VIDEO_PACKAGE_REGISTRY[package_id]["public_enabled"] is True
        assert VIDEO_PACKAGE_REGISTRY[package_id]["cost_gate"] == "open_business_package"
    for label in ("500 Xu", "600 Xu", "800 Xu", "1000 Xu", "1200 Xu", "1500 Xu"):
        assert any(label in item for item in labels)
    for tier in ("advanced", "standard", "high", "future_1000", "future_1200", "future_1500"):
        assert f"vfinal|tier|{tier}" in callbacks
        status = bot.get_public_video_tier_ui_status(tier, False)
        assert status["enabled"] is True
        assert status["visible"] is True
        assert status["public_status"] == "PUBLIC"
    guard_text = bot.video_finalization_tier_guard_text("standard", "vi")
    assert "bảo trì/nâng cấp" in guard_text
    assert "kiểm soát chi phí" not in guard_text.lower()
    assert "provider" not in guard_text.lower()


def test_video_paid_addon_requires_upgrade_on_200():
    result = bot.validate_video_tier_selection({"video_tier": "low", "current_video_music_option": "ai_music"}, "low")
    assert result["blocked"] is True
    assert "paid_music" in result["reasons"]


def test_video_back_routing_no_reupload():
    user_id = 993001
    bot.clear_video_session(user_id)
    bot.task3d_session_step(user_id, "intro", product_id="image_to_video")
    bot.task3d_session_step(user_id, "collect_input", input_mode="media", source_media_ref="file-1")
    bot.task3d_session_step(user_id, "platform", input_collected=True)
    target, session = bot.task3d_back_step(user_id)
    assert target == "collect_input"
    assert session["source_media_ref"] == "file-1"
    assert session["draft"]["source_media_ref"] == "file-1"
    bot.clear_video_session(user_id)


def test_video_upload_stays_in_product_session():
    user_id = 993002
    bot.clear_video_session(user_id)
    bot.task3d_session_step(user_id, "intro", product_id="image_to_video")
    bot.task3d_session_step(user_id, "collect_input", input_mode="media")

    class Message:
        photo = [SimpleNamespace(file_id="photo-task3d")]
        video = None
        document = None

        async def reply_text(self, *args, **kwargs):
            return None

    update = SimpleNamespace(message=Message(), effective_user=SimpleNamespace(id=user_id))
    handled = asyncio.run(bot.handle_video_product_pending_media(update, SimpleNamespace()))
    session = bot.get_video_session(user_id)
    assert handled is True
    assert session["product_id"] == "image_to_video"
    assert session["source_media_ref"] == "photo-task3d"
    assert session["current_step"] == "detail"
    bot.clear_video_session(user_id)


def test_video_provider_status_admin_only():
    source = inspect.getsource(bot.cmd_video_provider_status)
    assert "if not is_admin_user" in source
    assert "chỉ dành cho admin" in source


def test_video_provider_curl_admin_only():
    source = inspect.getsource(bot.cmd_video_provider_curl)
    assert "if not is_admin_user" in source
    sample = provider_curl_examples({"selected_provider": "shopaikey", "final_submit_url": "https://example.test/v1/video", "final_fetch_url": "https://example.test/v1/video/{task_id}"})
    assert "***MASKED***" in sample
    assert "secret-token" not in sample


def test_provider_final_urls_and_no_duplicate_url_segments():
    config = Key4UConfig(base_url="https://api.key4u.shop/v1", video_create_endpoint="/v1/video/create", video_query_endpoint="/v1/video/query")
    status = Key4UProvider(config).get_status()
    assert status["video_submit_final_url"] == "https://api.key4u.shop/v1/video/create"
    assert status["video_fetch_final_url"] == "https://api.key4u.shop/v1/video/query?id={task_id}"
    assert "/v1/v1/" not in status["video_submit_final_url"]
    assert join_provider_url("https://api.key4u.shop/v1", "/v1/video/create") == "https://api.key4u.shop/v1/video/create"


def test_prompt_vault_status():
    status = bot.TASK3D_PROMPT_VAULT.status()
    assert status["exists"] is True
    assert status["count"] >= 15
    assert status["invalid"] == []


def test_prompt_vault_search():
    rows = bot.TASK3D_PROMPT_VAULT.search("multishot")
    assert rows
    assert rows[0]["category"] == "seedance_multishot"
    assert rows[0]["enabled"] is True


def test_prompt_vault_categories_are_seeded():
    data = json.loads((Path(bot.__file__).parent / "docs" / "prompt_vault" / "video_prompts.seed.json").read_text(encoding="utf-8"))
    categories = {item["category"] for item in data["prompts"]}
    assert {
        "product_ad", "affiliate_video", "UGC_video", "cinematic_story", "cute_character_story",
        "horror_story", "action_scene", "transformation_video", "image_to_video_motion",
        "storyboard_9_panel", "storyboard_12_panel", "seedance_multishot",
        "youtube_short_script", "tiktok_hook", "facebook_ad_video",
    } <= categories


def test_prompt_bundle_validation():
    bundle = _bundle(shots=6)
    result = validate_video_prompt_bundle(bundle)
    assert result["valid"], result
    assert all(result["checks"].values())
    for shot in bundle.shot_table:
        for field in (
            "shot_number", "scene_purpose", "subject", "action", "environment", "camera_angle",
            "camera_movement", "lens", "lighting", "mood", "composition", "continuity_notes",
            "duration_seconds", "transition", "audio_sfx", "on_screen_text", "image_prompt",
            "video_prompt", "negative_prompt",
        ):
            assert shot[field]


def test_prompt_pack_exports_json_markdown_and_plain_text_content():
    bundle = _bundle(shots=6)
    markdown = bundle_to_markdown(bundle)
    payload = json.dumps(bundle.to_dict(), ensure_ascii=False)
    assert "## Storyboard" in markdown
    assert "Shot 1" in markdown
    assert '"shot_table"' in payload
    assert "no watermark" in markdown.lower()


def test_video_output_menu_has_prompt_image_video_buttons():
    markup = bot.task3d_result_keyboard("storyboard_prompt", "vi")
    assert [[button.text for button in row] for row in markup.inline_keyboard] == [
        ["🖼 Tạo prompt ảnh", "🎥 Tạo prompt video"],
        ["📦 Xuất bộ prompt", "🔁 Đổi phong cách"],
        ["🎬 Dùng để tạo video"],
        ["⬅️ Quay lại", "🏠 Menu chính"],
    ]
    assert _callbacks(markup)[:2] == ["vproduct|prompt_image", "vproduct|prompt_video"]


def test_all_video_products_output_use_same_action_menu():
    products = (
        "video_trend", "video_idea", "storyboard_prompt", "motion_prompt", "video_ai_real",
        "script_image_video", "image_to_video", "multi_scene_film", "self_shot_scene_change", "video_reference",
    )
    required = {
        "vproduct|prompt_image", "vproduct|prompt_video", "vproduct|export_menu",
        "vproduct|restyle", "vproduct|render", "vproduct|back", "menu|main",
    }
    for product_id in products:
        assert required <= set(_callbacks(bot.task3d_result_keyboard(product_id, "vi"))), product_id


def test_use_to_create_video_opens_package_before_scene_count(monkeypatch):
    user_id = 993290
    bot.clear_video_session(user_id)
    bundle = _bundle(shots=3).to_dict()
    bot.task3d_session_step(user_id, "result", product_id="storyboard_prompt", prompt_bundle=bundle)
    captured = {}

    async def fake_open(*args, **kwargs):
        captured.update({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(bot, "open_video_finalization", fake_open)
    query = _FakeQuery(user_id, "vproduct|render")
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    session = bot.get_video_session(user_id)
    assert session["current_step"] == "result"
    assert captured["kwargs"]["initial_step"] == "tier"
    assert captured["args"][5] == "vproduct|result"
    assert "selected_scene_count" not in captured["args"][6]
    bot.clear_video_session(user_id)


def test_task3d_aspect_keyboard_includes_4x5():
    labels = _labels(bot.task3d_aspect_keyboard("vi"))
    callbacks = _callbacks(bot.task3d_aspect_keyboard("vi"))
    assert "🖼 4:5" in labels
    assert "vproduct|aspect|4:5" in callbacks


def test_scene_count_screen_has_required_buttons_and_no_skip():
    state = {"selected_video_tier": "basic"}
    labels = _labels(bot.video_finalization_scene_count_keyboard(state, "vi"))
    assert labels == [
        "1 cảnh ≈ 6s = 300 Xu",
        "3 cảnh ≈ 18s = 810 Xu",
        "5 cảnh ≈ 30s = 1.350 Xu",
        "10 cảnh ≈ 60s = 2.550 Xu",
        "20 cảnh ≈ 120s = 4.800 Xu",
        "✍️ Tự chọn",
        "⬅️ Quay lại",
        "🏠 Menu chính",
    ]
    assert not any("Bỏ qua" in label for label in labels)
    assert _callbacks(bot.video_finalization_scene_count_keyboard(state, "vi"))[-2:] == ["vfinal|back", "vfinal|main"]


@pytest.mark.parametrize(
    ("scene_count", "duration"),
    ((1, 6), (3, 18), (5, 30), (10, 60), (20, 120)),
)
def test_scene_count_maps_to_estimated_duration(scene_count, duration):
    fields = bot.task3d_scene_count_fields(scene_count)
    assert fields["selected_scene_count"] == scene_count
    assert fields["estimated_scene_seconds"] == 6
    assert fields["estimated_duration_seconds"] == duration
    assert fields["duration_mode"] == "scene_based"
    assert "khoảng" in fields["duration_note"]


def test_package_selection_opens_scene_count(monkeypatch):
    user_id = 993291
    bot.clear_video_finalization_state(user_id)
    bot.set_video_finalization_state(user_id, {
        "step": "tier",
        "source": "storyboard_prompt",
        "source_payload": {"video_prompt": "Prompt video ready"},
        "has_video_prompt": True,
        "session_context": {"video_prompt": "Prompt video ready"},
    })

    async def forbidden_start(*args, **kwargs):
        raise AssertionError("invoice must not open before scene count")

    monkeypatch.setattr(bot, "start_video_addon_step", forbidden_start)
    monkeypatch.setattr(bot, "get_public_video_tier_ui_status", lambda tier, _admin=False: {"enabled": True, "label": tier, "price_xu": bot.video_tier_cost_xu(tier)})
    query = _FakeQuery(user_id, "vfinal|tier|basic")
    asyncio.run(bot.handle_video_finalization_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    state = bot.get_video_finalization_state(user_id)
    assert state["selected_video_tier"] == "basic"
    assert state["step"] == "scene_count"
    assert "Chọn số cảnh video" in query.edits[-1][0]
    bot.clear_video_finalization_state(user_id)


def test_scene_count_then_final_quote(monkeypatch):
    user_id = 993292
    bot.clear_video_finalization_state(user_id)
    bot.clear_video_session(user_id)
    bundle = _bundle(shots=5).to_dict()
    bot.task3d_session_step(user_id, "result", product_id="storyboard_prompt", prompt_bundle=bundle)
    bot.set_video_finalization_state(user_id, {
        "step": "scene_count",
        "selected_video_tier": "basic",
        "source": "storyboard_prompt",
        "source_payload": {"video_prompt": "Prompt video ready"},
        "has_video_prompt": True,
        "session_context": {"video_prompt": "Prompt video ready"},
    })
    captured = {}

    async def fake_start(*args, **kwargs):
        captured.update({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(bot, "start_video_addon_step", fake_start)
    monkeypatch.setattr(bot, "get_public_video_tier_ui_status", lambda tier, _admin=False: {"enabled": True, "label": tier, "price_xu": bot.video_tier_cost_xu(tier)})
    query = _FakeQuery(user_id, "vfinal|scene_count|3")
    asyncio.run(bot.handle_video_finalization_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    state = bot.get_video_finalization_state(user_id)
    assert state["selected_scene_count"] == 3
    assert state["estimated_duration_seconds"] == 18
    pending_payload = captured["args"][2]
    assert pending_payload["selected_scene_count"] == 3
    assert pending_payload["duration_seconds"] == 18
    quote = bot.calculate_video_quote({"video_tier": "basic", "selected_scene_count": 3})
    assert quote["total_xu"] == 810
    bot.clear_video_finalization_state(user_id)
    bot.clear_video_session(user_id)


def test_scene_count_opens_tools_before_final_invoice(monkeypatch):
    user_id = 993295
    bot.clear_video_finalization_state(user_id)
    bot.clear_video_addon_state(user_id)
    bot.clear_video_session(user_id)
    bot.task3d_session_step(user_id, "result", product_id="storyboard_prompt", prompt_bundle=_bundle(shots=5).to_dict())
    bot.set_video_finalization_state(user_id, {
        "step": "scene_count",
        "selected_video_tier": "basic",
        "source": "storyboard_prompt",
        "source_payload": {"video_prompt": "Prompt video ready"},
        "has_video_prompt": True,
        "session_context": {"video_prompt": "Prompt video ready"},
    })
    monkeypatch.setattr(bot, "get_public_video_tier_ui_status", lambda tier, _admin=False: {"enabled": True, "label": tier, "price_xu": bot.video_tier_cost_xu(tier)})
    query = _FakeQuery(user_id, "vfinal|scene_count|3")

    asyncio.run(bot.handle_video_finalization_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert "Công cụ hoàn thiện video" in query.edits[-1][0]
    assert "Tạm tính video: <b>300 × 90% = 270 Xu/cảnh; 270 × 3 = 810 Xu</b>" in query.edits[-1][0]
    callbacks = _callbacks(query.edits[-1][1]["reply_markup"])
    assert {"videoaddon|voice_menu", "videoaddon|music_menu", "videoaddon|subtitle_menu", "videoaddon|none"} <= set(callbacks)
    assert "videoaddon|export" not in "\n".join(callbacks)
    addon_state = bot.get_video_addon_state(user_id)
    assert addon_state["video_order"]["current_screen"] == "video_addon_menu"
    bot.clear_video_finalization_state(user_id)
    bot.clear_video_addon_state(user_id)
    bot.clear_video_session(user_id)


@pytest.mark.parametrize(
    "scene_count,discount_percent,total_xu",
    [(1, 100, 300), (3, 90, 810), (10, 85, 2550), (20, 80, 4800)],
)
def test_scene_pricing_formula_has_no_double_base(scene_count, discount_percent, total_xu):
    quote = bot.calculate_video_quote({"video_tier": "basic", "selected_scene_count": scene_count})
    assert quote["package_base_xu"] == 300
    assert quote["scene_count"] == scene_count
    assert quote["scene_discount_percent"] == discount_percent
    assert quote["scene_video_xu"] == total_xu
    assert quote["addon_fee_xu"] == 0
    assert quote["total_xu"] == total_xu


def test_package_200_is_one_scene_only_and_has_no_multi_scene_buttons():
    state = {"selected_video_tier": "low"}
    labels = _labels(bot.video_finalization_scene_count_keyboard(state, "vi"))
    callbacks = _callbacks(bot.video_finalization_scene_count_keyboard(state, "vi"))
    assert labels == ["1 cảnh ≈ 6s = 200 Xu", "🔷 Nâng lên 300 Xu", "⬅️ Quay lại", "🏠 Menu chính"]
    assert callbacks == ["vfinal|scene_count|1", "vfinal|upgrade_300", "vfinal|back", "vfinal|main"]
    assert "vfinal|scene_custom" not in callbacks


def test_package_200_quote_requires_exactly_one_scene_and_200_xu():
    valid = bot.calculate_video_quote({"video_tier": "low", "selected_scene_count": 1})
    invalid = bot.calculate_video_quote({"video_tier": "low", "selected_scene_count": 3})
    assert valid["is_package_200_valid"] is True
    assert valid["total_xu"] == 200
    assert invalid["is_package_200_valid"] is False
    assert invalid["total_xu"] == 540


def test_legacy_quote_without_scene_selection_preserves_one_clip():
    quote = bot.calculate_video_quote({"video_tier": "basic", "pending_payload": {"base_cost": 300}})
    assert quote["scene_count"] == 1
    assert quote["estimated_seconds"] == 6
    assert quote["total_xu"] == 300


def test_multiscene_admin_tool_never_runs_paid_job_automatically(monkeypatch):
    message = _FakeMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=993299), message=message)
    context = SimpleNamespace(args=["300", "3", "--confirm-paid"])
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "save_tool_test_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(bot, "_safe_set_video_system_setting", lambda *args, **kwargs: None)
    asyncio.run(bot.cmd_tool_test_video_multiscene(update, context))
    text = message.replies[-1][0]
    assert "Paid provider job: <code>NO</code>" in text
    assert "Public enabled: <code>NO</code>" in text
    assert "không đánh dấu PASS" in text


def test_custom_scene_count_accepts_1_to_20(monkeypatch):
    user_id = 993293
    bot.clear_video_finalization_state(user_id)
    bot.set_video_finalization_state(user_id, {
        "step": "scene_count_custom",
        "selected_video_tier": "basic",
        "source": "storyboard_prompt",
        "source_payload": {"video_prompt": "Prompt video ready"},
        "has_video_prompt": True,
        "session_context": {"video_prompt": "Prompt video ready"},
    })
    captured = []

    async def fake_start(*args, **kwargs):
        captured.append((args, kwargs))

    monkeypatch.setattr(bot, "start_video_addon_step", fake_start)
    monkeypatch.setattr(bot, "get_public_video_tier_ui_status", lambda tier, _admin=False: {"enabled": True, "label": tier, "price_xu": bot.video_tier_cost_xu(tier)})
    message = _FakeMessage()
    message.text = "7"
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id))
    handled = asyncio.run(bot.handle_video_finalization_pending_text(update, SimpleNamespace()))
    state = bot.get_video_finalization_state(user_id)
    assert handled is True
    assert state["selected_scene_count"] == 7
    assert state["estimated_duration_seconds"] == 42
    assert captured and captured[0][0][2]["selected_scene_count"] == 7
    bot.clear_video_finalization_state(user_id)


def test_custom_scene_count_rejects_over_20(monkeypatch):
    user_id = 993294
    bot.clear_video_finalization_state(user_id)
    bot.set_video_finalization_state(user_id, {
        "step": "scene_count_custom",
        "selected_video_tier": "basic",
        "source": "storyboard_prompt",
        "source_payload": {"video_prompt": "Prompt video ready"},
        "has_video_prompt": True,
    })

    async def forbidden_start(*args, **kwargs):
        raise AssertionError("over-limit scene count must not open invoice")

    monkeypatch.setattr(bot, "start_video_addon_step", forbidden_start)
    message = _FakeMessage()
    message.text = "25"
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id))
    handled = asyncio.run(bot.handle_video_finalization_pending_text(update, SimpleNamespace()))
    assert handled is True
    assert "tối đa 20 cảnh/khoảng 2 phút" in message.replies[-1][0]
    assert bot.get_video_finalization_state(user_id)["step"] == "scene_count_custom"
    bot.clear_video_finalization_state(user_id)


def test_package_and_confirmation_show_estimated_scene_count():
    state = {
        "source": "storyboard_prompt",
        "source_label": "Storyboard + Prompt",
        "video_tier": "basic",
        "selected_video_tier": "basic",
        "selected_scene_count": 3,
        "estimated_scene_seconds": 6,
        "estimated_duration_seconds": 18,
        "duration_mode": "scene_based",
        "has_video_prompt": True,
        "source_payload": {"video_prompt": "Prompt video ready", "selected_scene_count": 3, "estimated_scene_seconds": 6, "estimated_duration_seconds": 18},
        "pending_payload": {
            "video_tier": "basic",
            "base_cost": 810,
            "selected_scene_count": 3,
            "estimated_scene_seconds": 6,
            "estimated_duration_seconds": 18,
            "duration_seconds": 18,
            "scene_count": 3,
        },
    }
    package_text = bot.video_finalization_tier_text(state, "vi")
    scene_text = bot.video_finalization_scene_count_text(state, "vi")
    invoice_text = bot.video_price_invoice_text(state, "vi")
    assert "Sau khi chọn gói" in package_text
    assert "Số cảnh: <b>3 cảnh</b>" not in package_text
    assert "300 × 90% = 270 Xu/cảnh; 270 × 3 = <b>810 Xu</b>" in scene_text
    assert "Số cảnh: <b>3 cảnh</b>" in invoice_text
    assert "Thời lượng ước tính: <b>khoảng 18 giây</b>" in invoice_text
    assert "Chiết khấu cảnh: <b>10%</b>" in invoice_text
    assert "3 cảnh × 300 Xu × 90% = <b>810 Xu</b>" in invoice_text
    assert "Tổng: <b>810 Xu</b>" in invoice_text
    assert "Thời lượng: <b>18 giây</b>" not in invoice_text


def test_prompt_image_button_stays_in_video_flow():
    callbacks = _callbacks(bot.task3d_result_keyboard("storyboard_prompt", "vi"))
    assert "vproduct|prompt_image" in callbacks
    assert not any(value.startswith(("create_media|", "imgtool|")) for value in callbacks)


def test_prompt_video_button_stays_in_video_flow():
    callbacks = _callbacks(bot.task3d_result_keyboard("storyboard_prompt", "vi"))
    assert "vproduct|prompt_video" in callbacks
    assert not any(value.startswith("create_media|video") for value in callbacks)


def test_prompt_image_does_not_open_standalone_image_menu():
    source = inspect.getsource(bot.handle_video_product_callback)
    prompt_image_source = source[source.index('if action == "prompt_image"'):source.index('if action == "prompt_video"')]
    assert "localized_menu_content" not in prompt_image_source
    assert '"menu|image"' not in prompt_image_source
    assert "handle_image_tools_callback" not in prompt_image_source


def test_prompt_image_scene_selector():
    session = {"draft": {"prompt_bundle": _bundle(shots=6).to_dict()}}
    markup = bot.task3d_prompt_image_scene_keyboard(session, "vi")
    labels = _labels(markup)
    callbacks = _callbacks(markup)
    for index in range(1, 7):
        assert str(index) in labels
        assert f"vproduct|prompt_image_select|{index}" in callbacks
    assert "📦 Tất cả cảnh" in labels
    assert "⭐ Cảnh chính" in labels
    assert callbacks[-2:] == ["vproduct|result", "menu|main"]


def test_prompt_image_detail_shows_scene_prompt():
    bundle = _bundle(shots=3).to_dict()
    session = {"draft": {"prompt_bundle": bundle, "prompt_image_selection": [2]}}
    text = bot.task3d_prompt_detail_text(session, "image")
    assert "Prompt ảnh — 2" in text
    assert bundle["image_prompts"][1][:80] in text


def test_prompt_image_copy_prompt():
    user_id = 993301
    bot.clear_video_session(user_id)
    bundle = _bundle(shots=2).to_dict()
    bot.task3d_session_step(user_id, "prompt_image_detail", product_id="storyboard_prompt", prompt_bundle=bundle, prompt_image_selection=[1])
    query = _FakeQuery(user_id, "vproduct|prompt_image_copy")
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert "dễ sao chép" in query.edits[-1][0]
    assert bundle["image_prompts"][0][:80] in query.edits[-1][0]
    bot.clear_video_session(user_id)


def test_prompt_image_create_image_shows_image_package_selector():
    session = {"draft": {"prompt_bundle": _bundle(shots=2).to_dict(), "prompt_image_selection": [1]}}
    labels = _labels(bot.task3d_prompt_image_package_keyboard("vi"))
    assert labels == [
        "50 Xu Tiết kiệm", "150 Xu Phổ thông", "200 Xu Có bảo hành", "300 Xu Cao cấp",
        "400 Xu Có bảo hành", "500 Xu Cao cấp+", "600 Xu Có bảo hành", "⬅️ Prompt ảnh",
    ]
    assert "chưa gọi hệ tạo ảnh và chưa trừ Xu" in bot.task3d_prompt_image_package_text(session, "vi")


def test_prompt_image_uses_existing_image_pricing():
    assert tuple(bot.TASK3D_VIDEO_IMAGE_PACKAGES) == bot.TASK3D_VIDEO_IMAGE_PACKAGE_ORDER
    assert [bot.TASK3D_VIDEO_IMAGE_PACKAGES[code]["unit_cost_xu"] for code in bot.TASK3D_VIDEO_IMAGE_PACKAGE_ORDER] == [50, 150, 200, 300, 400, 500, 600]
    assert all(
        bot.TASK3D_VIDEO_IMAGE_PACKAGES[code]["provider_tier"] in bot.IMAGE_TIER_ORDER
        for code in bot.TASK3D_VIDEO_IMAGE_PACKAGE_ORDER
    )
    assert all(
        value.startswith("create_media|image_tier_") or value in {"menu|main_image", "menu|main", "create_media|cancel"}
        for value in _callbacks(bot.public_image_tier_keyboard("vi"))
    )


def test_prompt_image_confirm_no_xu_before_confirm():
    user_id = 993302
    bot.clear_video_session(user_id)
    bundle = _bundle(shots=2).to_dict()
    bot.task3d_session_step(user_id, "prompt_image_detail", product_id="storyboard_prompt", prompt_bundle=bundle, prompt_image_selection=[1])
    query = _FakeQuery(user_id, "vproduct|prompt_image_package|200")
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    session = bot.get_video_session(user_id)
    token = session["draft"]["prompt_image_confirm_token"]
    assert token in bot.SHOPAIKEY_PENDING_CONFIRMATIONS
    assert session["draft"].get("xu_charged", 0) == 0
    assert "Chi phí: <b>200 Xu</b>" in query.edits[-1][0]
    assert "chưa tạo ảnh và chưa trừ Xu" in query.edits[-1][0]
    bot.SHOPAIKEY_PENDING_CONFIRMATIONS.pop(token, None)
    bot.clear_video_session(user_id)


def test_prompt_image_provider_guard_no_charge(monkeypatch):
    user_id = 993303
    bot.clear_video_session(user_id)
    bundle = _bundle(shots=2).to_dict()
    bot.task3d_session_step(user_id, "prompt_image_detail", product_id="storyboard_prompt", prompt_bundle=bundle, prompt_image_selection=[1])
    select_query = _FakeQuery(user_id, "vproduct|prompt_image_package|50")
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=select_query), SimpleNamespace()))
    token = bot.get_video_session(user_id)["draft"]["prompt_image_confirm_token"]
    monkeypatch.setattr(bot, "shopaikey_public_generation_guard", lambda _kind: (False, "maintenance"))
    execute_query = _FakeQuery(user_id, f"vproduct|prompt_image_execute|{token}")
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=execute_query), SimpleNamespace()))
    assert "bảo trì/nâng cấp" in execute_query.edits[-1][0]
    assert "chưa trừ Xu" in execute_query.edits[-1][0]
    assert token in bot.SHOPAIKEY_PENDING_CONFIRMATIONS
    bot.SHOPAIKEY_PENDING_CONFIRMATIONS.pop(token, None)
    bot.clear_video_session(user_id)


def test_prompt_video_shot_selector():
    session = {"draft": {"prompt_bundle": _bundle(shots=4).to_dict()}}
    callbacks = _callbacks(bot.task3d_prompt_video_selector_keyboard(session, "vi"))
    for index in range(1, 5):
        assert f"vproduct|prompt_video_select|{index}" in callbacks
    assert "vproduct|prompt_video_select|all" in callbacks
    assert "vproduct|prompt_video_batches" in callbacks
    assert callbacks[-2:] == ["vproduct|result", "menu|main"]


def test_prompt_video_detail_shows_video_prompt():
    bundle = _bundle(shots=3).to_dict()
    session = {"draft": {"prompt_bundle": bundle, "prompt_video_selection": [3]}}
    text = bot.task3d_prompt_detail_text(session, "video")
    assert "Prompt video — 3" in text
    assert bundle["video_prompts"][2][:80] in text


def test_prompt_video_create_routes_to_package_before_scene_count(monkeypatch):
    user_id = 993304
    bot.clear_video_session(user_id)
    bundle = _bundle(shots=3).to_dict()
    bot.task3d_session_step(user_id, "prompt_video_detail", product_id="storyboard_prompt", prompt_bundle=bundle, prompt_video_selection=[2])
    captured = {}

    async def fake_open(*args, **kwargs):
        captured.update({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(bot, "open_video_finalization", fake_open)
    query = _FakeQuery(user_id, "vproduct|prompt_video_create")
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    session = bot.get_video_session(user_id)
    assert session["current_step"] == "prompt_video_detail"
    assert session["draft"]["scene_count_back_callback"] == "vproduct|prompt_video_detail"
    assert session["draft"]["scene_count_render_selected_shots"] == [2]
    assert bundle["video_prompts"][1] in session["draft"]["scene_count_render_video_prompt"]
    package = captured["args"][6]
    assert package["selected_shots"] == [2]
    assert bundle["video_prompts"][1] in package["video_prompt"]
    assert captured["kwargs"]["initial_step"] == "tier"
    assert captured["args"][5] == "vproduct|prompt_video_detail"
    bot.clear_video_session(user_id)


def test_prompt_video_scene_count_preserves_selected_prompt(monkeypatch):
    user_id = 993308
    bot.clear_video_session(user_id)
    bundle = _bundle(shots=3).to_dict()
    bot.task3d_session_step(
        user_id,
        "prompt_video_detail",
        product_id="storyboard_prompt",
        prompt_bundle=bundle,
        scene_count_back_callback="vproduct|prompt_video_detail",
        scene_count_render_video_prompt=f"Shot 2: {bundle['video_prompts'][1]}",
        scene_count_render_prompt_count=1,
        scene_count_render_selected_shots=[2],
    )
    state = bot.video_finalization_apply_scene_count_fields({"source_payload": {}, "session_context": {}, "video_project": {}}, 3, user_id)
    assert state["source_payload"]["selected_shots"] == [2]
    assert bundle["video_prompts"][1] in state["source_payload"]["video_prompt"]
    assert "mở rộng storyboard/prompt lên 3 cảnh" in state["source_payload"]["scene_expansion_note"]
    bot.clear_video_session(user_id)


def test_prompt_video_package_then_export_core():
    source = inspect.getsource(bot.handle_shopaikey_public_callback)
    assert "callback_data_override" in inspect.signature(bot.handle_shopaikey_public_callback).parameters
    assert "submit_public_video_with_key4u_fallback" in source
    assert "prompt_image" not in source
    assert "prompt_video_create" not in source


def test_export_prompt_pack_includes_image_and_video_prompts():
    bundle = _bundle(shots=2).to_dict()
    bundle["caption"] = "Caption thử"
    content = bot.task3d_prompt_export_markdown(bundle)
    assert "## Hook" in content
    assert "## Script" in content
    assert "## Caption" in content
    assert bundle["image_prompts"][0] in content
    assert bundle["video_prompts"][0] in content
    assert bundle["negative_prompt"] in content
    assert "## Batch grouping" in content
    export_source = inspect.getsource(bot.task3d_prompt_export_markdown)
    assert "spend_fixed_credit_info" not in export_source
    assert "shopaikey" not in export_source.lower()


def test_export_prompt_pack_no_xu(monkeypatch):
    user_id = 993307
    bot.clear_video_session(user_id)
    bundle = _bundle(shots=2).to_dict()
    bot.task3d_session_step(user_id, "result", product_id="storyboard_prompt", prompt_bundle=bundle)
    sent = []

    class ExportBot:
        async def send_document(self, **kwargs):
            sent.append(kwargs)

    def forbidden_charge(*args, **kwargs):
        raise AssertionError("prompt pack export must not charge Xu")

    monkeypatch.setattr(bot, "spend_fixed_credit_info", forbidden_charge)
    query = _FakeQuery(user_id, "vproduct|export|markdown")
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace(bot=ExportBot())))
    assert sent and sent[0]["filename"].endswith(".md")
    assert "chưa gọi provider và chưa trừ Xu" in query.edits[-1][0]
    callbacks = _callbacks(query.edits[-1][1]["reply_markup"])
    assert callbacks == ["vproduct|prompt_image", "vproduct|prompt_video", "vproduct|render", "vproduct|result", "menu|main"]
    bot.clear_video_session(user_id)


def test_change_style_preserves_session():
    user_id = 993305
    bot.clear_video_session(user_id)
    bundle = _bundle(shots=2).to_dict()
    bot.task3d_session_step(user_id, "result", product_id="storyboard_prompt", prompt_bundle=bundle, source_media_ref="telegram-file-1", topic="chủ đề giữ lại")
    query = _FakeQuery(user_id, "vproduct|restyle")
    asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    session = bot.get_video_session(user_id)
    assert session["current_step"] == "style"
    assert session["source_media_ref"] == "telegram-file-1"
    assert session["topic"] == "chủ đề giữ lại"
    assert session["draft"]["prompt_bundle"] == bundle
    bot.clear_video_session(user_id)


def test_prompt_image_back_to_scene_selector():
    assert "vproduct|prompt_image" in _callbacks(bot.task3d_prompt_image_detail_keyboard("vi"))


def test_scene_selector_back_to_prompt_pack():
    image_session = {"draft": {"prompt_bundle": _bundle(shots=2).to_dict(), "prompt_image_selection": [1]}}
    assert _callbacks(bot.task3d_prompt_image_scene_keyboard(image_session, "vi"))[-2] == "vproduct|result"
    assert "vproduct|prompt_image_detail" in _callbacks(bot.task3d_prompt_image_package_keyboard("vi"))


def test_prompt_video_back_to_shot_selector():
    assert "vproduct|prompt_video" in _callbacks(bot.task3d_prompt_video_detail_keyboard("vi"))


def test_shot_selector_back_to_prompt_pack():
    video_session = {"draft": {"prompt_bundle": _bundle(shots=2).to_dict(), "prompt_video_selection": [1]}}
    assert _callbacks(bot.task3d_prompt_video_selector_keyboard(video_session, "vi"))[-2] == "vproduct|result"
    assert "vproduct|prompt_video_detail" in inspect.getsource(bot.handle_video_product_callback)


def test_no_reinput_reupload():
    user_id = 993306
    bot.clear_video_session(user_id)
    bundle = _bundle(shots=2).to_dict()
    bot.task3d_session_step(user_id, "result", product_id="image_to_video", prompt_bundle=bundle, source_media_ref="photo-file-id")
    for callback in ("vproduct|prompt_image", "vproduct|prompt_image_select|1", "vproduct|prompt_image_packages"):
        query = _FakeQuery(user_id, callback)
        asyncio.run(bot.handle_video_product_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    session = bot.get_video_session(user_id)
    assert session["source_media_ref"] == "photo-file-id"
    assert session["draft"]["prompt_bundle"] == bundle
    assert session["current_step"] == "prompt_image_package"
    bot.clear_video_session(user_id)


def test_standalone_image_menu_not_changed():
    callbacks = _callbacks(bot.public_image_tier_keyboard("vi"))
    assert callbacks == [
        "create_media|image_tier_low", "create_media|image_tier_standard",
        "create_media|image_tier_standard_warranty", "create_media|image_tier_high",
        "create_media|image_tier_high_warranty", "menu|main_image", "menu|main", "create_media|cancel",
    ]
    assert "vproduct" not in inspect.getsource(bot.public_image_tier_keyboard)


def test_video_export_core_not_changed():
    source = inspect.getsource(bot.handle_shopaikey_public_callback)
    assert "submit_public_video_with_key4u_fallback" in source
    assert "shopai|confirm" not in source
    assert "vproduct|prompt_image" not in source
    assert "vproduct|prompt_video" not in source


def test_all_packages_still_visible():
    labels = _labels(bot.video_finalization_tier_keyboard("vi"))
    for price in (200, 300, 400, 500, 600, 800, 1000, 1200, 1500):
        assert any(f"{price} Xu" in label for label in labels)


def test_multiscene_200_can_export_one_experience_shot():
    assert validate_package_selection("multi_scene_film", "package_200", ["none"])["ok"] is True
    assert validate_package_selection("script_image_video", "package_200", ["none"])["ok"] is True
    assert VIDEO_PACKAGE_REGISTRY["package_200"]["max_shots"] == 1
    assert "một cảnh trải nghiệm" in VIDEO_PRODUCT_REGISTRY["multi_scene_film"]["public_guard_message"]


def test_task3d_commands_are_registered():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    for command in (
        "video_provider_status", "video_provider_curl", "tool_test_video_submit", "tool_test_video_fetch",
        "tool_test_video_200", "prompt_vault_status", "prompt_vault_refresh", "prompt_vault_search",
        "prompt_vault_add", "prompt_vault_import", "prompt_vault_export",
        "trend_source_status", "trend_source_refresh", "trend_source_add", "trend_source_list",
    ):
        assert f'CommandHandler("{command}"' in source
