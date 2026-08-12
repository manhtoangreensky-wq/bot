from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
FLOW7_SOURCE = (ROOT / "services" / "video_flow7.py").read_text(encoding="utf-8")
SCRIPT_SOURCE = (ROOT / "services" / "video_script_product.py").read_text(encoding="utf-8")

_FUNCTION_HEADERS = list(
    re.finditer(r"^(?:async[ \t]+)?def[ \t]+([A-Za-z_][A-Za-z0-9_]*)\(", BOT_SOURCE, re.MULTILINE)
)
_FUNCTION_BOUNDS = {
    match.group(1): (
        match.start(),
        _FUNCTION_HEADERS[index + 1].start() if index + 1 < len(_FUNCTION_HEADERS) else len(BOT_SOURCE),
    )
    for index, match in enumerate(_FUNCTION_HEADERS)
}


def _function_source(name: str) -> str:
    start, end = _FUNCTION_BOUNDS[name]
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
    product_tail = summary[summary.index('if route["kind"] == "product_tail"') :]
    assert "return await video_tail9_render(" in product_tail
    assert "render_blockers" not in product_tail.split("return await video_tail9_render(", 1)[0]

    invoice_handoff = _function_source("video_uiflow3_prepare_b14_session")
    assert "VIDEO_UIFLOW3_DEFERRED_RUNTIME_PRODUCTS" in invoice_handoff
    assert "video_uiflow3_routeengine_handoff_required" not in invoice_handoff

    package_preflight = _function_source("video_tail9_commercial_preflight")
    assert 'owner == "uiflow3"' in package_preflight
    assert "VIDEO_UIFLOW3_DEFERRED_RUNTIME_PRODUCTS" in package_preflight
    assert "VIDEO_TAIL9_DEFERRED_RUNTIME_PRODUCTS" in package_preflight
    assert "video_tail9_deferred_runtime_blocker" in package_preflight
    assert '"not_checked_before_final_confirmation"' in package_preflight

    tail_callback = _function_source("handle_video_tail_callback")
    submit_start = tail_callback.index('if section == "confirm"')
    submit = tail_callback[submit_start:]
    assert "video_uiflow3_b14_execution_blockers(host)" in submit
    assert submit.index("video_uiflow3_b14_execution_blockers(host)") < submit.index(
        "product_video_public_preflight_evaluation("
    )
    assert "video_tail9_prepare_submit_status(" in submit
    assert "video_tail9_render_confirmed_status(" in submit

    invoice_keyboard = _function_source("video_tail9_invoice_keyboard")
    confirm_keyboard = _function_source("video_tail9_confirm_keyboard")
    status_renderer = _function_source("video_tail9_render_confirmed_status")
    assert "✅ Xác nhận tạo video" in invoice_keyboard
    assert "⬅️ Quay lại" in invoice_keyboard
    assert "🚀 Bắt đầu tạo video" in confirm_keyboard
    assert "⬅️ Quay lại hóa đơn" in confirm_keyboard
    assert "video_b14_send_or_edit_status_panel" in status_renderer


def test_selective_video_products_share_the_complete_tail_without_merging_product_flows() -> None:
    shared_tail = BOT_SOURCE[
        BOT_SOURCE.index("VIDEO_UIFLOW3_SHARED_TAIL_PRODUCTS =") :
        BOT_SOURCE.index("def video_uiflow3_execution_adapter")
    ]
    for product in (
        "video_ai_real",
        "video_trend",
        "script_image_video",
        "storyboard_prompt",
        "multi_scene_film",
    ):
        assert f'"{product}"' in shared_tail

    script_bridge = _function_source("video_profile_scene1_open_selected_tail_invoice")
    selfshot_bridge = _function_source("video_selfshotflow4_handle_result")
    assert 'video_tail9_render(query, user_id, context, "addon")' in script_bridge
    assert 'video_tail9_render(query, user_id, context, "invoice")' not in script_bridge
    assert 'if screen == "tail_review"' in selfshot_bridge
    assert '"addon" if return_to_addon else "review"' in selfshot_bridge

    quality = _function_source("video_tail9_quality_keyboard")
    invoice = _function_source("video_tail9_invoice_keyboard")
    confirmation = _function_source("video_tail9_confirm_keyboard")
    status = _function_source("video_tail9_status_recovery_keyboard")
    assert "range(0, len(buttons), 2)" in quality
    assert '"⬅️ Quay lại"' in quality
    assert '"✅ Xác nhận tạo video"' in invoice
    assert '"⬅️ Quay lại"' in invoice
    assert '"🚀 Bắt đầu tạo video"' in confirmation
    assert '"⬅️ Quay lại hóa đơn"' in confirmation
    assert '"⬅️ Quay lại hóa đơn"' in status

    submit = _function_source("handle_video_tail_callback")
    runtime_gate = submit.index("video_uiflow3_b14_execution_blockers(host)")
    assert submit.rfind('if owner != "video_edit"', 0, runtime_gate) >= 0
    uiflow3_deferred_products = BOT_SOURCE[
        BOT_SOURCE.index("VIDEO_UIFLOW3_DEFERRED_RUNTIME_PRODUCTS =") :
        BOT_SOURCE.index("VIDEO_TAIL9_DEFERRED_RUNTIME_PRODUCTS =")
    ]
    for product in (
        "video_ai_real",
        "video_trend",
        "script_image_video",
        "storyboard_prompt",
        "multi_scene_film",
    ):
        assert f'"{product}"' in uiflow3_deferred_products
    deferred_products = BOT_SOURCE[
        BOT_SOURCE.index("VIDEO_TAIL9_DEFERRED_RUNTIME_PRODUCTS =") :
        BOT_SOURCE.index("def video_uiflow3_execution_adapter")
    ]
    assert "*VIDEO_UIFLOW3_DEFERRED_RUNTIME_PRODUCTS" in deferred_products
    for product in ("self_shot_scene_change", "self_shot_cinematic_transform"):
        assert f'"{product}"' in deferred_products
    for protected in ("frame_video_local", "video_idea", "video_local_edit"):
        assert f'"{protected}"' not in deferred_products

    adapter = _function_source("video_uiflow3_execution_adapter")
    assert 'product not in VIDEO_UIFLOW3_DEFERRED_RUNTIME_PRODUCTS' in adapter
    assert '"multi_scene_film": "planning_only"' not in adapter

    confirm = submit[submit.index('if section == "confirm"') :]
    execution_disabled = confirm[
        confirm.index('if not contract.get("execution_enabled")') :
        confirm.index('is_internal = video_b14_is_admin_or_owner', confirm.index('if not contract.get("execution_enabled")'))
    ]
    assert "video_tail9_prepare_submit_status(" in execution_disabled
    assert "video_tail9_render_confirmed_status(" in execution_disabled


def test_script_scene3_handoff_opens_the_existing_shared_tail_addon() -> None:
    callback = _function_source("handle_video_profile_studio_callback")
    handoff_start = callback.index('if action == "handoff"')
    handoff_end = callback.index('if action in {"final_view", "invoice_report"}', handoff_start)
    handoff = callback[handoff_start:handoff_end]

    assert 'flow_kind == "script_to_video"' in handoff
    assert "video_profile_scene1_open_selected_tail_invoice(" in handoff
    assert "video_b14_invoice_text" in handoff

    bridge = _function_source("video_profile_scene1_open_selected_tail_invoice")
    assert "video_tail9_context(" in bridge
    assert 'tail["review_status"] = "not_ready"' in bridge
    assert 'tail["quality_tier_id"] = ""' in bridge
    assert 'video_tail9_render(query, user_id, context, "addon")' in bridge
    assert 'video_tail9_render(query, user_id, context, "invoice")' not in bridge
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


def test_script_hub_has_one_video_menu_exit_without_a_duplicate_back_button() -> None:
    hub_keyboard = _function_source("video_script_hub_keyboard")

    assert hub_keyboard.count('callback_data="menu|main_video"') == 1
    assert "⬅️ Quay lại" not in hub_keyboard


def test_script_file_replace_can_return_to_the_existing_file_review() -> None:
    callback = _function_source("handle_video_product_callback")

    assert '"script_file_review",' in callback
    assert 'if action == "script_file_review":' in callback


def test_script_custom_content_keeps_its_exact_origin_callback() -> None:
    callback = _function_source("handle_video_product_callback")

    start = callback.index('if action == "script_content_custom":')
    end = callback.index('if action == "script_suggestions_refresh":', start)
    custom_content = callback[start:end]
    assert 'draft.get("script_content_input_back_callback")' in custom_content


def test_selfshot_source_upload_returns_to_the_exact_selected_product() -> None:
    source_keyboard = _function_source("video_selfshotflow4_source_keyboard")
    source_router = _function_source("video_selfshot_source_input_keyboard")
    source_request = _function_source("video_selfshotflow4_request_source")

    assert 'f"vproduct|{active_flow}|c4show|segment"' in source_keyboard
    assert 'f"vproduct|selfshot_product|{product_route}"' in source_keyboard
    assert "video_selfshotflow4_source_keyboard(flow, draft)" in source_router
    assert "video_selfshotflow4_source_keyboard(flow, current)" in source_request


def test_shared_review_routes_script_and_selfshot_children_back_to_exact_review() -> None:
    tail_callback = _function_source("handle_video_tail_callback")
    review_start = tail_callback.index('if section == "review"')
    review_end = tail_callback.index('if section == "summary"', review_start)
    review = tail_callback[review_start:review_end]

    assert 'step="selfshot2:scene_plan"' in review
    assert 'step="selfshot3:timeline"' in review
    assert 'target = "prompts" if action == "prompts" else "content_source"' in review
    assert 'target = "prompt" if action == "prompts" else "content"' in review
    assert 'video_tail_return_to="review"' in review

    for name in (
        "video_selfshot2_render",
        "video_selfshot3_render",
        "video_selfshot3_render_prompt_review",
    ):
        assert '"video_tail|review|open"' in _function_source(name)

    product_callback = _function_source("handle_video_product_callback")
    for marker in (
        'current_screen == "prompts"',
        'screen == "audio"',
        'str(current.get("selfshot3_screen") or "") == "timeline"',
        'screen == "wardrobe"',
    ):
        assert marker in product_callback

    scene3_callback = _function_source("handle_video_profile_studio_callback")
    image_done_start = scene3_callback.index('if action == "image_prompt_done"')
    image_done_end = scene3_callback.index('if action == "video_prompt_done"', image_done_start)
    image_done = scene3_callback[image_done_start:image_done_end]
    assert 'prompt_return == "full_review" and tail_return in {"summary", "review"}' in image_done
    assert 'video_tail9_render(query, uid, context, tail_return)' in image_done


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
