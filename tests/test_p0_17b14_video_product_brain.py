import inspect
import os
import shutil
from pathlib import Path

import pytest

import bot
from services import video_asset_intake as assets
from services import video_postprocess_pipeline as post
from services import video_product_profiles as profiles
from services import video_prompt_continuity as continuity
from services import video_storyboard_planner as planner


def _ffmpeg():
    return os.getenv("FFMPEG_PATH") or shutil.which("ffmpeg")


def _run_ffmpeg(cmd):
    import subprocess

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    assert result.returncode == 0, result.stderr
    return result


def _make_video(path: Path, duration=2.0):
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        pytest.skip("ffmpeg required for postprocess smoke")
    _run_ffmpeg([
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x1E88E5:s=320x568:r=30:d={duration:.2f}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(path),
    ])
    return path


def _make_audio(path: Path, duration=1.4, frequency=440):
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        pytest.skip("ffmpeg required for postprocess smoke")
    _run_ffmpeg([
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency={frequency}:duration={duration:.2f}",
        "-c:a",
        "aac",
        str(path),
    ])
    return path


def _make_logo_ppm(path: Path):
    width, height = 48, 48
    payload = bytearray()
    for _y in range(height):
        for _x in range(width):
            payload.extend((255, 255, 255))
    path.write_bytes(f"P6\n{width} {height}\n255\n".encode("ascii") + bytes(payload))
    return path


def _make_srt(path: Path):
    path.write_text("1\n00:00:00,000 --> 00:00:01,500\nTOAN AAS subtitle\n", encoding="utf-8")
    return path


def test_video_profiles_exist_for_12_core_types():
    ids = {profile.profile_id for profile in profiles.list_video_profiles()}
    assert ids == {
        "storytelling",
        "product_review",
        "news",
        "philosophy_quotes",
        "educational",
        "history",
        "ugc_affiliate",
        "real_estate_fpv",
        "fashion_lookbook",
        "food_asmr",
        "lofi_audio_visualizer",
        "cinematic_trailer",
    }


def test_video_profiles_have_unique_ids():
    ids = [profile.profile_id for profile in profiles.list_video_profiles(public_only=False)]
    assert len(ids) == len(set(ids))


def test_video_profiles_have_script_formula_voice_music_subtitle_style():
    for profile in profiles.list_video_profiles():
        assert profile.script_formula
        assert profile.voice_style
        assert profile.music_style
        assert profile.subtitle_style
        assert profile.postprocess_defaults["burn_subtitles"] is True


def test_no_protected_studio_artist_style_in_public_profile():
    assert profiles.validate_profile_style_safety() == {}


def test_profile_lookup_and_menu_mapping_do_not_call_provider():
    assert profiles.get_video_profile("product_review").menu_label == "Video review sản phẩm / affiliate"
    assert profiles.resolve_profile_for_menu_product("video_trend", user_text="ugc affiliate TikTok shop").profile_id == "ugc_affiliate"
    assert profiles.resolve_profile_for_menu_product("video_idea", user_text="tin tức AI hôm nay").profile_id == "news"
    assert profiles.get_scene_template("cinematic_trailer", 5)[0]["role"] == "setup"
    assert "Profile: cinematic_trailer" in profiles.build_profile_prompt_context("cinematic_trailer")


def test_each_profile_has_3_and_5_scene_templates():
    for profile in profiles.list_video_profiles():
        assert len(profile.scene_templates_3) == 3
        assert len(profile.scene_templates_5) == 5
    assert "AIDA" in profiles.get_video_profile("product_review").script_formula
    assert "5W1H" in profiles.get_video_profile("news").script_formula
    assert "ELI5" in profiles.get_video_profile("educational").script_formula
    assert profiles.get_video_profile("history").fact_policy
    assert "pause markers" in profiles.get_video_profile("philosophy_quotes").system_prompt


def test_new_profiles_have_required_policies():
    assert "smartphone" in profiles.get_video_profile("ugc_affiliate").image_style
    assert "FPV" in profiles.get_video_profile("real_estate_fpv").camera_style
    assert "beat" in profiles.get_video_profile("fashion_lookbook").pacing_policy
    assert "sizzle" in profiles.get_video_profile("food_asmr").sfx_policy
    assert "loop extension" in profiles.get_video_profile("lofi_audio_visualizer").postprocess_policy
    assert "letterbox" in profiles.get_video_profile("cinematic_trailer").postprocess_policy


def test_profile_recommendation_keywords():
    assert profiles.recommend_profile_id("ugc affiliate TikTok Shop review") == "ugc_affiliate"
    assert profiles.recommend_profile_id("tour căn hộ bất động sản FPV") == "real_estate_fpv"
    assert profiles.recommend_profile_id("lookbook thời trang váy hè") == "fashion_lookbook"
    assert profiles.recommend_profile_id("món ăn ASMR sizzle crunch") == "food_asmr"
    assert profiles.recommend_profile_id("lofi chill lyrics visualizer") == "lofi_audio_visualizer"
    assert profiles.recommend_profile_id("cinematic trailer phim ngắn") == "cinematic_trailer"
    assert profiles.recommend_profile_id("lịch sử Việt Nam") == "history"
    assert profiles.recommend_video_profile("tin tức kinh tế").profile_id == "news"


def test_no_profile_creates_separate_pipeline_or_large_bot_dict():
    source = inspect.getsource(profiles)
    assert "process_multiscene_video_pipeline" not in source
    assert "render_scene" not in source
    bot_source = Path("bot.py").read_text(encoding="utf-8")
    assert "VIDEO_PRODUCT_PROFILES" not in bot_source
    assert "ugc_affiliate" not in bot_source


def test_bot_b14_admin_commands_and_asset_gate_wiring():
    bot_source = Path("bot.py").read_text(encoding="utf-8")
    for command in (
        "tool_test_video_profiles",
        "tool_test_asset_intake",
        "tool_test_storyboard_planner",
        "tool_test_prompt_continuity",
        "tool_test_video_postprocess",
        "tool_test_video_full_addons",
    ):
        assert f'CommandHandler("{command}"' in bot_source
    assert "vproduct|asset_wait|" in bot_source
    assert "vproduct|asset_class|" in bot_source
    assert "provider_called=False, xu_charged=0" in bot_source
    assert 'PUBLIC_MULTISCENE_VIDEO_ENABLED", "false"' in bot_source
    assert 'PUBLIC_VIDEO_ADDONS_ENABLED", "false"' in bot_source


def test_b14_flow_contract_report_exists_and_audits_12_profiles():
    report = Path("docs/reports/P0_17B14_VIDEO_FLOW_CONTRACT_AUDIT.md")
    assert report.is_file()
    text = report.read_text(encoding="utf-8")
    for profile_id in {
        "storytelling",
        "product_review",
        "news",
        "philosophy_quotes",
        "educational",
        "history",
        "ugc_affiliate",
        "real_estate_fpv",
        "fashion_lookbook",
        "food_asmr",
        "lofi_audio_visualizer",
        "cinematic_trailer",
    }:
        assert f"### {profile_id}" in text
    assert "All 12 profiles share one pipeline" in text
    assert "Render before confirm: no" in text
    assert 'Public "tao thu" button: no' in text


def test_public_video_flow_has_no_tao_thu_or_preview_render_buttons():
    forbidden = (
        "Tạo thử",
        "tạo thử",
        "Xem thử",
        "xem thử",
        "Render thử",
        "render thử",
        "Preview video",
        "preview video",
        "Demo render",
        "demo render",
        "Generate sample",
    )
    keyboards = [
        bot.main_video_keyboard("vi"),
        bot.video_asset_intake_keyboard("vi"),
        bot.video_asset_classify_keyboard("vi"),
        bot.video_asset_scene_order_keyboard("vi"),
    ]
    for product_id in bot.VIDEO_PRODUCT_REGISTRY:
        keyboards.append(bot.task3d_product_intro_keyboard(product_id, "vi"))
    for keyboard in keyboards:
        labels = " ".join(button.text for row in keyboard.inline_keyboard for button in row)
        callbacks = " ".join(str(button.callback_data or "") for row in keyboard.inline_keyboard for button in row)
        combined = f"{labels} {callbacks}"
        for term in forbidden:
            assert term not in combined
        assert "tool_test" not in callbacks


def test_public_storyboard_and_prompt_preview_are_text_only():
    plan = planner.create_storyboard_plan(profile_id="storytelling", idea_text="câu chuyện về sự kiên trì", scene_count=3)
    assert plan.provider_called is False
    assert plan.xu_charged == 0
    assert "No render/provider call before storyboard confirm" in plan.preview_text
    preview = bot.video_b14_storyboard_preview_text(plan)
    assert "Chưa tạo file thật" in preview
    assert "chưa trừ Xu" in preview


def test_public_copy_no_provider_ffmpeg_traceback_or_debug_terms():
    public_texts = [
        bot.menu_text_main_video(),
        bot.menu_text_main_video_i18n("en"),
        bot.menu_text_main_video_i18n("zh"),
        bot.video_ai_true_text("vi"),
        bot.video_ai_true_text("en"),
        bot.video_ai_true_text("zh"),
        bot.video_frame_intro_text("vi"),
        bot.video_frame_intro_text("en"),
        bot.video_frame_intro_text("zh"),
        "\n".join(bot.pricing_frame_video_lines()),
        bot.video_asset_intake_intro_text("vi"),
        bot.VIDEO_B14_PUBLIC_UNSTABLE_TOOL_MESSAGE,
        bot.VIDEO_B14_MULTISCENE_PUBLIC_MESSAGE,
    ]
    for product_id in bot.VIDEO_PRODUCT_REGISTRY:
        public_texts.append(bot.task3d_product_intro_text(product_id, "vi"))
    forbidden = ("provider", "api", "ffmpeg", "traceback", "env", "tool_test", "fake-renderer")
    for text in public_texts:
        lower = str(text).lower()
        for term in forbidden:
            assert term not in lower
    assert "chưa xử lý" in bot.VIDEO_B14_PUBLIC_UNSTABLE_TOOL_MESSAGE
    assert "chưa trừ Xu" in bot.VIDEO_B14_PUBLIC_UNSTABLE_TOOL_MESSAGE


def test_admin_test_tools_available_by_slash_and_mark_admin_test_mode():
    source = Path("bot.py").read_text(encoding="utf-8")
    assert 'CommandHandler("tool_test_video_profiles"' in source
    assert 'CommandHandler("tool_test_prompt_continuity"' in source
    assert "ADMIN TEST MODE" in source


def test_asset_upload_does_not_render_and_limits_public_admin():
    pack = assets.new_asset_pack()
    assert assets.asset_upload_triggers_render() is False
    for index in range(3):
        assets.add_asset(pack, asset_type="character_reference", file_id=f"char-{index}")
    with pytest.raises(ValueError):
        assets.add_asset(pack, asset_type="character_reference", file_id="char-4")
    assets.add_asset(pack, asset_type="character_reference", file_id="char-admin", admin=True)
    assert len(pack.character_refs) == 4


def test_asset_pack_stores_refs_and_storyboard_order():
    pack = assets.new_asset_pack(["brand blue"])
    assets.add_asset(pack, asset_type="product_reference", file_id="p1")
    assets.add_asset(pack, asset_type="scene_background", file_id="b1")
    assets.add_asset(pack, asset_type="storyboard_frame", file_id="s3", scene_index=3)
    assets.add_asset(pack, asset_type="storyboard_frame", file_id="s1", scene_index=1)
    assets.add_asset(pack, asset_type="logo", file_id="logo1")
    assets.add_asset(pack, asset_type="voice_audio", file_id="voice1")
    assets.add_asset(pack, asset_type="music_audio", file_id="music1")
    assert pack.product_refs[0].file_id == "p1"
    assert pack.background_refs[0].file_id == "b1"
    assert [slot.scene_index for slot in pack.storyboard_frames] == [1, 3]
    summary = assets.safe_asset_summary(pack)
    assert "product:1" in summary
    assert "storyboard:2" in summary


def test_story_bible_created_from_profile_and_assets_keeps_consistency():
    pack = assets.new_asset_pack()
    assets.add_asset(pack, asset_type="product_reference", file_id="product-1")
    profile = profiles.get_video_profile("product_review")
    bible = planner.create_story_bible(profile, pack, idea_text="review máy xay mini màu xanh")
    assert bible.profile_id == "product_review"
    assert "sản phẩm chính" in bible.main_subject
    assert any("keep same main subject" in rule for rule in bible.continuity_rules)
    assert "product_refs" in bible.reference_assets_used


def test_scene_cards_templates_and_preview_before_invoice():
    plan = planner.create_storyboard_plan(
        profile_id="educational",
        idea_text="giải thích AI agent cho người mới",
        scene_count=5,
    )
    assert len(plan.scene_cards) == 5
    assert len({card.role for card in plan.scene_cards}) >= 4
    assert "No render/provider call before storyboard confirm" in plan.preview_text
    assert planner.render_allowed_for_plan(plan, storyboard_confirmed=False, final_confirmed=True) is False
    assert planner.render_allowed_for_plan(plan, storyboard_confirmed=True, final_confirmed=False) is False


def test_scene_prompt_contains_story_bible_reference_summary_and_one_action():
    pack = assets.new_asset_pack()
    assets.add_asset(pack, asset_type="character_reference", file_id="c1")
    plan = planner.create_storyboard_plan(profile_id="storytelling", idea_text="nhân vật vượt qua nỗi sợ", asset_pack=pack)
    cards = continuity.build_continuity_prompts(plan.story_bible, plan.scene_cards)
    prompt = cards[0].provider_prompt
    assert "[GLOBAL CONTINUITY]" in prompt
    assert "Same subject/product/character" in prompt
    assert "Asset summary" in prompt
    assert "Avoid random text" in prompt
    assert continuity.scene_prompt_has_one_primary_action(prompt) is True


def test_reference_adapter_uses_assets_when_supported_and_text_fallback_when_not_supported():
    pack = assets.new_asset_pack()
    assets.add_asset(pack, asset_type="character_reference", file_id="c1")
    assets.add_asset(pack, asset_type="storyboard_frame", file_id="frame1", scene_index=1)
    plan = planner.create_storyboard_plan(profile_id="storytelling", idea_text="story", asset_pack=pack)
    continuity.build_continuity_prompts(plan.story_bible, plan.scene_cards)
    fallback = continuity.create_reference_plan(story_bible=plan.story_bible, scene_cards=plan.scene_cards, asset_pack=pack)
    assert fallback.manifest["reference_mode"] == "text_fallback"
    supported = continuity.create_reference_plan(
        story_bible=plan.story_bible,
        scene_cards=plan.scene_cards,
        asset_pack=pack,
        provider_supports_reference_image=True,
        provider_supports_first_frame=True,
    )
    assert supported.manifest["reference_mode"] == "provider_reference"
    assert supported.manifest["subject_refs"]
    assert supported.manifest["first_frame_by_scene"]
    assert supported.manifest["provider_core_touched"] is False


def test_service_modules_have_no_telegram_imports():
    for module in (profiles, assets, planner, continuity, post):
        source = inspect.getsource(module).lower()
        assert "from telegram" not in source
        assert "import telegram" not in source


def test_postprocess_adds_voice_music_logo_subtitle_and_returns_one_final_mp4(tmp_path):
    source = _make_video(tmp_path / "source.mp4")
    voice = _make_audio(tmp_path / "voice.m4a", frequency=440)
    music = _make_audio(tmp_path / "music.m4a", frequency=220)
    logo = _make_logo_ppm(tmp_path / "logo.ppm")
    subtitle = _make_srt(tmp_path / "captions.srt")
    output = tmp_path / "final.mp4"
    result = post.process_video_postprocess_plan(post.VideoPostprocessPlan(
        source_video_path=str(source),
        output_video_path=str(output),
        voice_audio_path=str(voice),
        music_audio_path=str(music),
        logo_path=str(logo),
        subtitle_path=str(subtitle),
        burn_subtitles=True,
        replace_original_audio=True,
    ))
    assert result.ok, result.detail
    assert result.output_video_path == str(output.resolve())
    assert result.output_bytes > 0
    assert result.provider_called is False
    assert result.xu_charged == 0


def test_postprocess_voice_longer_than_video_guard(tmp_path):
    source = _make_video(tmp_path / "source.mp4", duration=1.0)
    voice = _make_audio(tmp_path / "voice.m4a", duration=2.4)
    result = post.process_video_postprocess_plan(post.VideoPostprocessPlan(
        source_video_path=str(source),
        output_video_path=str(tmp_path / "out.mp4"),
        voice_audio_path=str(voice),
    ))
    assert result.ok is False
    assert result.status == "VOICE_LONGER_THAN_VIDEO"


def test_postprocess_does_not_modify_render_engine():
    source = inspect.getsource(post)
    assert "process_multiscene_video_pipeline" not in source
    assert "render_scene" not in source
    assert "xu_charged: int = 0" in source
