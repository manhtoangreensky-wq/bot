from pathlib import Path

import bot
from services import video_asset_intake as assets
from services import video_cinematic_continuity as cinematic
from services import video_product_profiles as profiles
from services import video_profile_context_engine as context_engine
from services import video_prompt_continuity as continuity
from services import video_prompt_vault as vault
from services import video_storyboard_planner as planner


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_prompt_vault_has_12_profile_packs_and_shared_blocks():
    status = vault.vault_status()
    assert status["profile_count"] == 12
    assert set(status["profile_ids"]) == set(vault.PROFILE_IDS)
    assert set(status["shared_blocks"]) == set(vault.SHARED_BLOCKS)
    assert Path(status["config_path"]).is_dir()
    assert status["provider_called"] is False
    assert status["xu_charged"] == 0

    for profile_id in vault.PROFILE_IDS:
        pack = vault.load_profile_pack(profile_id)
        for key in (
            "profile_id",
            "script_formulas",
            "hook_templates",
            "scene_role_templates",
            "shot_templates",
            "camera_templates",
            "motion_templates",
            "visual_style_templates",
            "color_tone_templates",
            "transition_templates",
            "negative_prompt_blocks",
            "product_domains",
        ):
            assert pack.get(key), f"{profile_id} missing {key}"


def test_prompt_vault_is_config_service_not_giant_bot_dict():
    source = Path("bot.py").read_text(encoding="utf-8")
    assert "VIDEO_B14_4_PROMPT_VAULT" not in source
    assert "raw smartphone perfume try-on" not in source
    assert "smooth FPV architecture tour" not in source
    assert "config/video_prompt_vault" not in source.replace("\\", "/")
    assert Path("config/video_prompt_vault/profiles/ugc_affiliate.json").is_file()


def test_public_profile_selection_has_12_profiles_without_test_preview_or_provider_copy():
    markup = bot.video_b14_profile_selection_keyboard("vi")
    profile_callbacks = [
        callback
        for callback in _callbacks(markup)
        if str(callback).startswith("vproduct|b14_profile|") and not str(callback).endswith("|auto")
    ]
    assert len(profile_callbacks) == 12
    assert {callback.rsplit("|", 1)[1] for callback in profile_callbacks} == set(vault.PROFILE_IDS)
    assert "🧠 Tự động đề xuất" in _labels(markup)

    screen = bot.video_b14_profile_selection_text({"draft": {}}, user_id=0, lang="vi")
    combined = " ".join(_labels(markup) + _callbacks(markup) + [screen]).lower()
    for forbidden in ("tạo thử", "xem thử", "preview", "fake", "provider"):
        assert forbidden not in combined
    assert "chưa tạo file thật" in screen
    assert "chưa trừ Xu" in screen


def test_profile_context_selects_product_domain_from_user_idea():
    cases = [
        ("ugc_affiliate", "bán nước hoa nam mùi hương lâu phai", "perfume"),
        ("real_estate_fpv", "tour căn hộ 2 phòng ngủ có ban công nhìn sông", "apartment"),
        ("food_asmr", "video trà sữa đá lạnh có topping", "drink"),
        ("fashion_lookbook", "lookbook outfit váy hè cho nữ", "outfit"),
        ("cinematic_trailer", "trailer robot tương lai đi tìm ký ức", "sci_fi"),
    ]
    for profile_id, idea, expected_domain in cases:
        bundle = context_engine.select_prompt_context(profile_id, user_idea=idea, scene_count=5)
        assert bundle.profile_id == profile_id
        assert bundle.product_domain == expected_domain
        assert bundle.selected_visual_style or bundle.selected_camera_language
        assert bundle.selected_transition_style
        assert bundle.selected_negative_prompt
        assert bundle.provider_called is False
        assert bundle.xu_charged == 0


def test_creative_controls_override_profile_context_and_feed_provider_prompt():
    controls = {
        "visual_style": "vertical smartphone UGC, everyday realistic footage",
        "camera_angle": "vertical smartphone selfie-style camera",
        "camera_motion": "spray, reaction, bottle close-up",
        "color_tone": "bright clean premium bathroom lighting",
        "pacing": "fast retention pacing with short shots",
        "mood": "viral energetic mood",
        "negative_prompt_extra": "no luxury billboard look",
    }
    plan = planner.create_storyboard_plan(
        profile_id="ugc_affiliate",
        idea_text="bán nước hoa nam mùi hương sạch",
        creative_controls=controls,
        scene_count=5,
    )
    prompt = plan.scene_cards[0].provider_prompt.lower()
    assert plan.prompt_context["product_domain"] == "perfume"
    assert "vertical smartphone" in prompt
    assert "spray, reaction, bottle close-up" in prompt
    assert "bright clean premium bathroom lighting" in prompt
    assert "no luxury billboard look" in prompt
    assert "[continuity lock]" in prompt
    assert "[no text rule]" in prompt


def test_cinematic_continuity_ledger_writes_scene_bridges_and_prompt_chain():
    plan = planner.create_storyboard_plan(
        profile_id="cinematic_trailer",
        idea_text="trailer robot tương lai phát hiện ký ức bị đánh cắp",
        scene_count=5,
    )
    ledger = dict(plan.continuity_ledger)
    assert len(ledger["transition_plan"]) == 5
    assert "setup" in ledger["emotional_arc"] or "incident" in ledger["emotional_arc"]
    assert ledger["forbidden_changes"]

    for card in plan.scene_cards:
        assert card.entry_state
        assert card.exit_state
        assert card.match_cut_hint
        assert card.continuity_lock
        assert "[CONTINUITY LOCK]" in card.provider_prompt
        assert "[SCENE ROLE]" in card.provider_prompt
        assert "[VISUAL]" in card.provider_prompt
        assert "[ACTION]" in card.provider_prompt
        assert "[CAMERA]" in card.provider_prompt
        assert "[TRANSITION]" in card.provider_prompt
        assert "[POSTPROCESS READINESS]" in card.provider_prompt
        assert "[NO TEXT RULE]" in card.provider_prompt


def test_prompt_continuity_adapter_keeps_b14_4_chain_and_one_action_rule():
    plan = planner.create_storyboard_plan(
        profile_id="product_review",
        idea_text="review máy xay mini màu xanh ngọc cho bếp nhỏ",
        scene_count=3,
    )
    cards = continuity.build_continuity_prompts(plan.story_bible, plan.scene_cards)
    prompt = cards[0].provider_prompt
    assert "[CONTINUITY LOCK]" in prompt
    assert "[ACTION]" in prompt
    assert "One clear visible action" in prompt
    assert continuity.scene_prompt_has_one_primary_action(prompt) is True

    reference_plan = continuity.create_reference_plan(
        story_bible=plan.story_bible,
        scene_cards=cards,
        asset_pack=assets.new_asset_pack(),
    )
    assert reference_plan.manifest["story_bible"]["creative_controls"]
    assert reference_plan.manifest["provider_core_touched"] is False


def test_storyboard_preview_and_prompt_pack_show_context_without_public_render():
    plan = planner.create_storyboard_plan(
        profile_id="real_estate_fpv",
        idea_text="tour căn hộ 2 phòng ngủ có ban công nhìn sông",
        scene_count=5,
    )
    preview = bot.video_b14_storyboard_preview_text(plan)
    assert "TOAN AAS đã chọn bộ ngữ cảnh prompt phù hợp" in preview
    assert "Ngữ cảnh sản phẩm" in preview
    assert "Continuity arc" in preview
    assert "Chưa tạo file thật" in preview
    assert "chưa trừ Xu" in preview

    bundle = bot.video_b14_prompt_bundle_from_plan(plan)
    session = {"draft": {"b14_storyboard_plan": plan.to_dict(), "prompt_bundle": bundle}}
    prompt_text = bot.video_b14_prompt_text_from_session(session, "video")
    pack_text = bot.video_b14_prompt_pack_text_from_session(session)
    assert "Không tạo file thật" in prompt_text
    assert "provider" not in prompt_text.lower()
    assert "kế hoạch dạng text" in pack_text
    assert "provider" not in pack_text.lower()
    assert "prompt_context" in pack_text
    assert "continuity_ledger" in pack_text


def test_owner_admin_bypass_public_video_gate_and_get_clear_test_label(monkeypatch):
    monkeypatch.setattr(bot, "PUBLIC_MULTISCENE_VIDEO_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_B14_2_PROJECT_WORKER_READY", False)
    monkeypatch.setattr(bot, "frame_video_worker_connected", lambda: False)
    monkeypatch.setattr(bot, "is_owner_user", lambda user_id: int(user_id) == 7)
    monkeypatch.setattr(bot, "is_admin_user", lambda user_id: int(user_id) == 8)

    assert bot.video_b14_public_render_guard(7) == (True, "")
    assert bot.video_b14_public_render_guard(8) == (True, "")
    blocked, message = bot.video_b14_public_render_guard(9)
    assert blocked is False
    assert "chưa xử lý" in message and "chưa trừ Xu" in message
    assert "OWNER/ADMIN TEST MODE" in bot.video_b14_admin_test_label(7, "vi")
    assert "OWNER/ADMIN TEST MODE" in bot.video_b14_admin_test_label(8, "vi")
    assert bot.video_b14_admin_test_label(9, "vi") == ""


def test_package_names_balance_copy_and_200_tier_disable_addons():
    labels = [bot.video_b14_package_button_label(price) for price in bot.VIDEO_B14_2_QUALITY_OPTIONS]
    assert any("Trải nghiệm" in label for label in labels)
    assert any("Premium" in label for label in labels)
    assert any("Max" in label for label in labels)

    session = {
        "product_id": "multi_scene_film",
        "topic": "video trailer robot",
        "draft": {
            "b14_profile_id": "cinematic_trailer",
            "b14_quality_xu": 200,
            "b14_scene_count": 3,
            "b14_addon_plan": {"voice_enabled": True, "music_enabled": True, "subtitle_enabled": True, "logo_enabled": True},
        },
    }
    invoice = bot.video_b14_invoice_for_session(session, 123)
    text = bot.video_b14_invoice_text(session, 123, "vi")
    assert invoice["package_name"] == "Trải nghiệm"
    assert invoice["addons_disabled_by_package"] is True
    assert "Gói trải nghiệm chỉ tạo video gốc" in text
    assert "Xác nhận" in _labels(bot.video_b14_invoice_keyboard("vi"))[0]


def test_b14_4_admin_slash_tools_are_registered():
    source = Path("bot.py").read_text(encoding="utf-8")
    for command in (
        "tool_test_prompt_vault",
        "tool_test_profile_context",
        "tool_test_cinematic_continuity",
        "tool_test_prompt_chain",
    ):
        assert f'CommandHandler("{command}"' in source


def test_all_12_profiles_still_share_common_video_pipeline():
    source = Path("services/video_prompt_vault.py").read_text(encoding="utf-8")
    for forbidden in ("process_multiscene_video_pipeline", "render_scene", "create_local_worker_job"):
        assert forbidden not in source
    assert {profile.profile_id for profile in profiles.list_video_profiles()} == set(vault.PROFILE_IDS)
