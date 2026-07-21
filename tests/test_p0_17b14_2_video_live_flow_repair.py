import inspect
from pathlib import Path

import bot
from services import video_asset_intake as assets
from services import video_prompt_continuity as continuity
from services import video_storyboard_planner as planner


FORBIDDEN_PLACEHOLDERS = (
    "sản phẩm chính trong ảnh tham chiếu",
    "performs one clear action",
    "user idea",
    "main subject",
    "reference asset",
)


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_b14_2_flow_repair_report_exists():
    report = Path("docs/reports/P0_17B14_2_VIDEO_LIVE_FLOW_REPAIR.md")
    assert report.is_file()
    text = report.read_text(encoding="utf-8")
    assert "Canonical public flow" in text
    assert "No provider/render/Xu before final confirm" in text
    assert "Duplicate screens removed" in text


def test_asset_intake_recommends_reference_images_and_skip_warning():
    text = bot.video_asset_intake_intro_text("vi")
    assert "Muốn video sát ý hơn" in text
    assert "độ giống nhân vật/sản phẩm" in text
    labels = _labels(bot.video_asset_intake_keyboard("vi"))
    for label in (
        "📸 Gửi ảnh nhân vật/sản phẩm",
        "🏞 Gửi ảnh bối cảnh",
        "🧩 Gửi ảnh storyboard",
        "🏷 Gửi logo",
        "🎙 Gửi voice/audio",
        "🎵 Gửi nhạc nền",
        "⏭ Bỏ qua",
        "✅ Xong phần tư liệu",
    ):
        assert label in labels
    warning = bot.video_b14_asset_skip_warning_text("vi")
    assert "đang bỏ qua ảnh tư liệu" in warning
    assert _callbacks(bot.video_b14_asset_skip_warning_keyboard("vi"))[:2] == [
        "vproduct|asset_intro",
        "vproduct|asset_skip_confirm",
    ]


def test_storyboard_preview_buttons_are_text_planning_only():
    callbacks = _callbacks(bot.video_b14_storyboard_keyboard("vi"))
    assert callbacks == [
        "vproduct|storyboard_confirm",
        "vproduct|b14_prompt_image_text",
        "vproduct|b14_prompt_video_text",
        "vproduct|b14_export_pack",
        "vproduct|b14_creative_screen",
        "vproduct|storyboard_confirm",
        "vproduct|asset_intro",
        "vproduct|b14_addons",
        "vproduct|b14_creative_screen",
        "menu|main",
    ]
    combined = " ".join(_labels(bot.video_b14_storyboard_keyboard("vi")) + callbacks).lower()
    assert "tạo thử" not in combined
    assert "xem thử" not in combined
    assert "preview" not in combined
    assert "fake" not in combined


def test_public_render_guard_blocks_before_invoice(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda _user_id: False)
    monkeypatch.setattr(bot, "PUBLIC_MULTISCENE_VIDEO_ENABLED", False)
    ok, message = bot.video_b14_public_render_guard(123456)
    assert ok is False
    assert "chưa xử lý" in message and "chưa trừ Xu" in message

    monkeypatch.setattr(bot, "PUBLIC_MULTISCENE_VIDEO_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_B14_2_PROJECT_WORKER_READY", False)
    ok, message = bot.video_b14_public_render_guard(123456)
    assert ok is False
    assert "Hệ thống dựng video nền chưa sẵn sàng" in message

    monkeypatch.setattr(bot, "VIDEO_B14_2_PROJECT_WORKER_READY", True)
    monkeypatch.setattr(bot, "frame_video_worker_connected", lambda: False)
    ok, message = bot.video_b14_public_render_guard(123456)
    assert ok is False
    assert "chưa xử lý" in message and "chưa trừ Xu" in message

    monkeypatch.setattr(bot, "frame_video_worker_connected", lambda: True)
    assert bot.video_b14_public_render_guard(123456) == (True, "")


def test_admin_bypasses_public_video_gate(monkeypatch):
    monkeypatch.setattr(bot, "PUBLIC_MULTISCENE_VIDEO_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_B14_2_PROJECT_WORKER_READY", False)
    monkeypatch.setattr(bot, "frame_video_worker_connected", lambda: False)
    monkeypatch.setattr(bot, "is_admin_user", lambda user_id: int(user_id) == 1)
    assert bot.video_b14_public_render_guard(1) == (True, "")


def test_addon_volume_ui_only_saves_json_shape():
    session = {
        "product_id": "multi_scene_film",
        "topic": "phim ngắn cinematic về robot giao hàng",
        "draft": {"b14_profile_id": "cinematic_trailer"},
    }
    plan = bot.video_b14_addon_plan_from_session(session)
    assert {
        "voice_enabled",
        "voice_source",
        "voice_id",
        "voice_volume_percent",
        "voice_speed_percent",
        "music_enabled",
        "music_source",
        "music_id",
        "music_volume_percent",
        "sfx_enabled",
        "subtitle_enabled",
        "subtitle_source",
        "logo_enabled",
        "logo_file_id",
        "logo_position",
        "logo_opacity_percent",
    }.issubset(plan.keys())
    labels = _labels(bot.video_b14_addon_keyboard("vi"))
    assert "🎙 Âm lượng giọng" in labels
    assert "🎵 Âm lượng nhạc" in labels
    assert "🏷 Logo" in labels
    assert "💬 Phụ đề" in labels
    assert "✅ Xong add-ons" in labels


def test_package_200_invoice_disables_addons():
    session = {
        "product_id": "multi_scene_film",
        "topic": "phim ngắn cinematic về robot giao hàng",
        "draft": {
            "b14_profile_id": "cinematic_trailer",
            "b14_quality_xu": 200,
            "b14_scene_count": 3,
            "b14_addon_plan": {
                "voice_enabled": True,
                "music_enabled": True,
                "subtitle_enabled": True,
                "logo_enabled": True,
            },
        },
    }
    invoice = bot.video_b14_invoice_for_session(session, 123456)
    text = bot.video_b14_invoice_text(session, 123456, "vi")
    assert invoice["addons_disabled_by_package"] is True
    assert "Gói trải nghiệm chỉ tạo video gốc" in text


def test_storyboard_brain_no_generic_placeholders():
    pack = assets.new_asset_pack()
    assets.add_asset(pack, asset_type="product_reference", file_id="product-1")
    plan = planner.create_storyboard_plan(
        profile_id="product_review",
        idea_text="review máy xay mini màu xanh ngọc cho căn bếp nhỏ",
        asset_pack=pack,
        scene_count=5,
    )
    cards = continuity.build_continuity_prompts(plan.story_bible, plan.scene_cards)
    prompt_text = "\n".join(card.provider_prompt for card in cards).lower()
    for placeholder in FORBIDDEN_PLACEHOLDERS:
        assert placeholder not in prompt_text
    assert "máy xay mini màu xanh ngọc" in prompt_text
    assert all(card.quality_score for card in cards)


def test_storyboard_scene_has_required_fields_and_quality_repair():
    plan = planner.create_storyboard_plan(
        profile_id="real_estate_fpv",
        idea_text="tour căn hộ 2 phòng ngủ ở Thủ Thiêm có ban công nhìn sông",
        scene_count=10,
    )
    assert len(plan.scene_cards) == 10
    for card in plan.scene_cards:
        assert card.duration_seconds
        assert card.narration_line
        assert card.visual_goal
        assert card.subject_action
        assert card.camera_motion
        assert card.composition
        assert card.background
        assert card.transition_from_previous
        assert card.transition_to_next
        assert card.music_cue
        assert card.logo_cue
        assert card.provider_prompt
        assert min(card.quality_score.values()) >= 3


def test_video_product_callback_uses_b14_confirm_for_charge_and_queue():
    source = inspect.getsource(bot.handle_video_product_callback)
    before_confirm = source.split('if action == "b14_confirm":', 1)[0]
    assert "confirm_video_project_invoice" not in before_confirm
    assert "process_multiscene_video_pipeline" not in before_confirm
    assert "create_local_worker_job" not in before_confirm
    assert "confirm_video_project_invoice" in source.split('if action == "b14_confirm":', 1)[1]
