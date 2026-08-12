from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
FLOW7_SOURCE = (ROOT / "services" / "video_flow7.py").read_text(encoding="utf-8")
SCRIPT_SOURCE = (ROOT / "services" / "video_script_product.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    markers = (f"def {name}(", f"async def {name}(")
    positions = [BOT_SOURCE.find(marker) for marker in markers]
    start = min(position for position in positions if position >= 0)
    next_def = re.search(r"\n(?:async )?def [A-Za-z_]", BOT_SOURCE[start + 1 :])
    end = start + 1 + next_def.start() if next_def else len(BOT_SOURCE)
    return BOT_SOURCE[start:end]


def _action_block(action: str, next_action: str) -> str:
    callback = _function_source("handle_video_product_callback")
    start = callback.index(f'if action == "{action}"')
    end = callback.index(f'if action == "{next_action}"', start)
    return callback[start:end]


def test_script_ai_is_content_first_and_manual_file_do_not_ask_count_up_front() -> None:
    ai = _action_block("script_ai", "script_manual")
    manual = _action_block("script_manual", "script_upload")
    upload = _action_block("script_upload", "script_file_replace")

    assert '"script_ai_content_source"' in ai
    assert '"script_scene_count"' not in ai
    assert '"awaiting_existing_script"' in manual
    assert '"script_scene_count"' not in manual
    assert '"awaiting_script_file"' in upload
    assert '"script_scene_count"' not in upload


def test_script_ai_order_is_content_goal_audience_platform_style_ratio_duration() -> None:
    callback = _function_source("handle_video_product_callback")
    custom_text = _function_source("handle_video_product_pending_text")

    ai_entry = _action_block("script_ai", "script_manual")
    suggestion = _action_block("script_suggestion", "script_audience_screen")
    goal = _action_block("script_goal", "script_content_source")
    style = _action_block("script_style", "script_ratio_screen")
    ratio = _action_block("script_ratio", "script_duration_screen")

    assert '"script_ai_content_source"' in ai_entry
    assert '"script_ai_goal"' in suggestion
    assert '"script_ai_audience"' in goal
    assert '"script_ai_content_source"' not in goal
    assert '"script_ai_ratio"' in style
    assert '"script_ai_duration"' in ratio
    assert '"awaiting_script_ai_content": ("script_ai_goal", "script_content_brief")' in custom_text
    assert '"awaiting_script_ai_goal": ("script_ai_audience", "script_goal_label")' in custom_text


def test_script_count_is_parser_review_only_then_enters_scene_plan_without_character_detour() -> None:
    script_spec = FLOW7_SOURCE[
        FLOW7_SOURCE.index('"script_to_video": {') :
        FLOW7_SOURCE.index('"storyboard": {')
    ]
    expected = (
        '"script_source"',
        '"content_setup_if_ai"',
        '"full_script_review"',
        '"scene_boundary_review"',
    )
    assert [script_spec.index(token) for token in expected] == sorted(
        script_spec.index(token) for token in expected
    )
    assert '"character"' not in script_spec
    assert re.search(r"^MIN_SCENES\s*=\s*5\s*$", SCRIPT_SOURCE, re.MULTILINE)

    handoff = _function_source("video_flow7_start_confirmed_script_state")
    after_ratio = _function_source("video_flow7_after_ratio")
    assert "video_scene3_flow.build_planning_package(state)" in handoff
    assert '"scene_plan"' in handoff
    assert '"character"' not in handoff
    assert "video_scene3_flow.build_planning_package(updated)" in after_ratio
    assert 'return updated, "scene_plan"' in after_ratio


def test_ai_real_reuses_the_existing_tail_invoice_confirm_and_status_flow() -> None:
    shared_tail = BOT_SOURCE[
        BOT_SOURCE.index("VIDEO_UIFLOW3_SHARED_TAIL_PRODUCTS =") :
        BOT_SOURCE.index("def video_uiflow3_execution_adapter")
    ]
    adapter = _function_source("video_uiflow3_execution_adapter")
    callback = _function_source("handle_video_uiflow3_callback")

    assert '"video_ai_real"' in shared_tail
    assert '"video_ai_real": "b14_invoice"' not in adapter
    summary_start = callback.index('elif action == "summary_done"')
    summary_end = callback.index('elif action == "quality"', summary_start)
    summary = callback[summary_start:summary_end]
    assert 'route["kind"] == "product_tail"' in summary
    assert "video_tail9_render(" in summary

    invoice_keyboard = _function_source("video_tail9_invoice_keyboard")
    confirm_keyboard = _function_source("video_tail9_confirm_keyboard")
    status_renderer = _function_source("video_tail9_render_confirmed_status")
    assert "✅ Xác nhận tạo video" in invoice_keyboard
    assert "⬅️ Quay lại" in invoice_keyboard
    assert "🚀 Bắt đầu tạo video" in confirm_keyboard
    assert "⬅️ Quay lại hóa đơn" in confirm_keyboard
    assert "video_b14_send_or_edit_status_panel" in status_renderer


def test_script_scene3_handoff_opens_the_existing_shared_tail_invoice() -> None:
    callback = _function_source("handle_video_profile_studio_callback")
    handoff_start = callback.index('if action == "handoff"')
    handoff_end = callback.index('if action in {"final_view", "invoice_report"}', handoff_start)
    handoff = callback[handoff_start:handoff_end]

    assert 'flow_kind == "script_to_video"' in handoff
    assert "video_profile_scene1_open_selected_tail_invoice(" in handoff
    assert "video_b14_invoice_text" in handoff

    bridge = _function_source("video_profile_scene1_open_selected_tail_invoice")
    assert "video_tail9_context(" in bridge
    assert "video_tail9.prepare_summary(" in bridge
    assert "video_tail9.select_package(" in bridge
    assert 'video_tail9_render(query, user_id, context, "invoice")' in bridge
    assert "video_b14_invoice_text" not in bridge


def test_script_back_buttons_return_to_the_exact_previous_screen() -> None:
    content_keyboard = _function_source("video_script_content_source_keyboard")
    goal_keyboard = _function_source("video_script_goal_keyboard")
    audience_keyboard = _function_source("video_script_audience_keyboard")
    style_keyboard = _function_source("video_script_style_keyboard")
    duration_keyboard = _function_source("video_script_duration_keyboard")
    review_keyboard = _function_source("video_script_review_keyboard")
    renderer = _function_source("video_script_render_step")

    assert 'callback_data="vproduct|script_hub"' in content_keyboard
    assert 'script_goal_back_callback' in goal_keyboard
    assert 'script_audience_back_callback' in audience_keyboard
    assert 'callback_data="vproduct|script_platform_screen"' in style_keyboard
    assert 'callback_data="vproduct|script_ratio_screen"' in duration_keyboard
    assert 'callback_data="vproduct|script_file_replace"' in review_keyboard
    assert '"awaiting_existing_script": "vproduct|script_hub"' in renderer
    assert 'or "vproduct|script_hub"' in renderer


def test_script_copy_and_file_review_match_the_content_first_contract() -> None:
    suggestions = _function_source("video_script_suggestions_text")
    proposal = _function_source("video_script_proposal_review_text")
    file_review = _function_source("video_script_review_keyboard")

    assert "chuyển thẳng sang Mục tiêu kịch bản" in suggestions
    assert "Số cảnh đề xuất" in proposal
    assert "✅ Dùng nội dung file" in file_review
    assert "⬅️ Quay lại tải file" in file_review
    assert "Gửi file khác" not in file_review
    assert "Bước tải file" not in file_review


def test_removed_count_first_callbacks_fail_safe_without_reopening_old_screens() -> None:
    callback = _function_source("handle_video_product_callback")
    start = callback.index(
        'if action in {"script_entry_count_screen", "script_entry_count", '
        '"script_entry_count_custom", "script_entry_ratio_screen", "script_entry_ratio"}'
    )
    end = callback.index('if action == "script_goal_screen"', start)
    stale = callback[start:end]

    assert "video_script_restore_parser_or_hub" in stale
    assert '"script_scene_count"' not in stale
    assert '"script_scene_ratio"' not in stale


def test_custom_goal_and_scene_plan_navigation_preserve_the_real_state() -> None:
    build_prompt = SCRIPT_SOURCE[
        SCRIPT_SOURCE.index("def build_ai_prompt") :
        SCRIPT_SOURCE.index("def public_choice_label")
    ]
    review_wrapper = _function_source("video_profile_scene1_review_keyboard")
    pending = _function_source("handle_video_profile_studio_pending_text")

    assert 'draft.get("script_goal_label")' in build_prompt
    assert "video_scene3_scene_plan_keyboard(state)" in review_wrapper
    assert "video_scene3_scene_plan_keyboard()" not in pending


def test_reference_video_upload_screens_return_to_the_reference_hub() -> None:
    start_keyboard = _function_source("video_reference_start_keyboard")
    analysis_keyboard = _function_source("video_reference_analysis_start_keyboard")

    for source in (start_keyboard, analysis_keyboard):
        assert 'callback_data="videoref|hub"' in source
        assert 'callback_data="menu|video_ai_true"' not in source


def test_locked_product_names_are_not_part_of_the_new_ui_sync_contract() -> None:
    synced = BOT_SOURCE[
        BOT_SOURCE.index("VIDEO_UIFLOW3_SYNCED_PRODUCTS =") :
        BOT_SOURCE.index("VIDEO_UIFLOW3_PRODUCT_CONTEXT_GUIDANCE")
    ]
    for protected in (
        "video_trend",
        "video_idea",
        "frame_video_local",
        "storyboard_prompt",
        "multi_scene_film",
        "video_local_edit",
    ):
        assert f'"{protected}"' not in synced
