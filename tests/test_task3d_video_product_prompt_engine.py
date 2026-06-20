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


def test_result_child_buttons_return_to_the_result_menu_that_contains_them():
    assert _callbacks(bot.task3d_result_parent_keyboard("vi")) == ["vproduct|result", "menu|main"]
    source = inspect.getsource(bot.handle_video_product_callback)
    assert 'if action == "result"' in source
    assert 'callback_data="vproduct|result"' in source
    assert 'lang, "vproduct|result", package' in source


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
    for package_id in ("package_200", "package_300", "package_400"):
        assert validate_package_selection("video_ai_real", package_id, ["none"])["ok"]


def test_video_200_free_default_can_reach_final_confirm():
    state = {"pending_payload": {"job_type": "video", "video_tier": "low", "preview_required": False}}
    callbacks = _callbacks(bot.video_addon_confirm_keyboard("token200", "low", "vi", state))
    assert "shopai|confirm|token200" in callbacks
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


def test_video_200_paid_addon_requires_upgrade_or_remove():
    result = validate_package_selection("video_ai_real", "package_200", ["ai_music"])
    assert result["ok"] is False
    assert result["reason"] == "paid_addon_not_allowed"
    callbacks = _callbacks(bot.video_experience_tier_lock_keyboard("vi"))
    assert "videoaddon|remove_paid_addons" in callbacks
    assert "vfinal|tier|basic" in callbacks


def test_video_200_creates_provider_job_after_confirm():
    source = inspect.getsource(bot.handle_shopaikey_public_callback)
    confirm_index = source.index('if action not in {"confirm", "package"}')
    create_index = source.index("create_shopaikey_job", confirm_index)
    provider_index = source.index("shopaikey_video_create_smoke_test", create_index)
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
    assert "Provider không nhận job" in source


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


def test_video_600_hidden_or_guarded():
    assert VIDEO_PACKAGE_REGISTRY["package_600_off"]["public_enabled"] is False
    labels = _labels(bot.video_finalization_tier_keyboard("vi"))
    assert not any("600 Xu" in label for label in labels)
    assert "vfinal|tier|standard" not in _callbacks(bot.video_finalization_tier_keyboard("vi"))


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
    assert session["current_step"] == "platform"
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


def test_multiscene_200_is_blocked_but_one_shot_pipeline_is_allowed():
    assert validate_package_selection("multi_scene_film", "package_200", ["none"])["ok"] is False
    assert validate_package_selection("script_image_video", "package_200", ["none"])["ok"] is True
    assert VIDEO_PACKAGE_REGISTRY["package_200"]["max_shots"] == 1


def test_task3d_commands_are_registered():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    for command in (
        "video_provider_status", "video_provider_curl", "tool_test_video_submit", "tool_test_video_fetch",
        "tool_test_video_200", "prompt_vault_status", "prompt_vault_refresh", "prompt_vault_search",
        "prompt_vault_add", "prompt_vault_import", "prompt_vault_export",
    ):
        assert f'CommandHandler("{command}"' in source
