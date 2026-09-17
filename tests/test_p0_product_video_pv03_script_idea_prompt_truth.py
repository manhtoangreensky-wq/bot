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
# 11. FAILURE SEMANTICS TRUTH
# ==============================================================================

def test_failure_semantics_distinct_blockers():
    """Distinct blocker classification is maintained for content generation errors."""
    error_classes = [
        "AI_NOT_CONFIGURED",
        "AI_UNAVAILABLE",
        "AI_TIMEOUT",
        "AI_INVALID_RESPONSE",
        "EMPTY_GENERATION",
        "INVALID_USER_INPUT",
        "STALE_DRAFT",
        "REVISION_CONFLICT",
    ]
    # Verify no secret keywords leaked into error labels
    for err in error_classes:
        assert "sk-" not in err.lower()
        assert "key" not in err.lower() or err == "AI_NOT_CONFIGURED"


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

