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


def test_script_ai_starts_with_count_then_ratio_while_manual_and_file_keep_source_first() -> None:
    ai = _action_block("script_ai", "script_manual")
    manual = _action_block("script_manual", "script_upload")
    upload = _action_block("script_upload", "script_file_replace")

    assert '"script_entry_count"' in ai
    assert '"script_ai_content_source"' not in ai
    assert '"awaiting_existing_script"' in manual
    assert '"script_scene_count"' not in manual
    assert '"awaiting_script_file"' in upload
    assert '"script_scene_count"' not in upload


def test_script_ai_order_is_count_ratio_content_creative_goal_audience_platform_duration() -> None:
    callback = _function_source("handle_video_product_callback")
    custom_text = _function_source("handle_video_product_pending_text")

    ai_entry = _action_block("script_ai", "script_manual")
    count = _action_block("script_entry_count", "script_entry_ratio_screen")
    ratio = _action_block("script_entry_ratio", "script_goal_screen")
    suggestion = _action_block("script_suggestion", "script_audience_screen")
    goal = _action_block("script_goal", "script_content_source")
    platform = _action_block("script_platform", "script_style_screen")

    assert '"script_entry_count"' in ai_entry
    assert '"script_entry_ratio"' in count
    assert '"script_ai_content_source"' in ratio
    assert "video_script_open_creative_details" in suggestion
    assert 'phase="pre_script"' in suggestion
    assert '"script_ai_audience"' in goal
    assert '"script_ai_content_source"' not in goal
    assert '"script_ai_duration"' in platform
    assert '"script_ai_style"' not in platform
    assert '"awaiting_script_ai_content": ("script_creative_details", "script_content_brief")' in custom_text
    assert '"awaiting_script_ai_goal": ("script_ai_audience", "script_goal_label")' in custom_text


def test_script_parser_reuses_pre_script_creative_details_or_opens_them_once_after_ratio() -> None:
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
    assert 'creative_complete = bool(draft.get("script_creative_complete"))' in handoff
    assert '"script_creative_phase": "complete" if creative_complete else "post_parser"' in handoff
    assert "video_scene3_flow.build_planning_package(state)" in handoff
    assert '"scene_plan"' in handoff
    assert '"character"' in handoff
    assert 'if bool(updated.get("script_creative_complete"))' in after_ratio
    assert "video_scene3_flow.build_planning_package(updated)" in after_ratio
    assert 'return updated, "scene_plan"' in after_ratio
    assert 'return updated, "character"' in after_ratio


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


def test_uiflow3_duplicate_callback_is_consumed_before_stale_snapshot_render() -> None:
    callback = _function_source("handle_video_uiflow3_callback")
    claim = callback.index("state, claimed = video_uiflow3.claim_callback")
    duplicate_guard = callback.index("if not claimed:", claim)
    stale_guard = callback.index("not hmac.compare_digest")
    duplicate_block = callback[duplicate_guard:stale_guard]

    assert claim < duplicate_guard < stale_guard
    assert "return True" in duplicate_block
    assert "video_uiflow3_render" not in duplicate_block


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
    assert "if quality not in VIDEO_AI_REAL_QUALITY_MODEL_KEYS:" not in bridge
    assert 'video_profile_studio_step(context, state, "quality")' not in bridge
    assert 'tail["review_status"] = "not_ready"' in bridge
    assert 'tail["quality_tier_id"] = ""' in bridge
    assert 'video_tail9_render(query, user_id, context, "addon")' in bridge
    assert 'video_tail9_render(query, user_id, context, "invoice")' not in bridge
    assert "video_b14_invoice_text" not in bridge


def test_script_back_buttons_return_to_the_exact_previous_screen() -> None:
    content_keyboard = _function_source("video_script_content_source_keyboard")
    goal_keyboard = _function_source("video_script_goal_keyboard")
    audience_keyboard = _function_source("video_script_audience_keyboard")
    duration_keyboard = _function_source("video_script_duration_keyboard")
    review_keyboard = _function_source("video_script_review_keyboard")
    renderer = _function_source("video_script_render_step")

    assert 'draft.get("script_entry_route")' in content_keyboard
    assert '"vproduct|script_entry_ratio_screen"' in content_keyboard
    assert 'else "vproduct|script_hub"' in content_keyboard
    assert 'script_goal_back_callback' in goal_keyboard
    assert 'script_audience_back_callback' in audience_keyboard
    assert 'callback_data="vproduct|script_platform_screen"' in duration_keyboard
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


def test_selfshot_scene_change_reuses_creative_controls_between_plan_and_prompts() -> None:
    callback = _function_source("handle_video_product_callback")
    profile_callback = _function_source("handle_video_profile_studio_callback")
    opener = _function_source("video_selfshot2_open_creative_details")
    finisher = _function_source("video_selfshot2_finish_creative_details")

    assert 'operation == "compile_prompts"' in callback
    assert "video_selfshot2_open_creative_details" in callback
    assert '"creative_controls"' in opener
    assert '"character"' not in opener
    assert '"image_source"' not in opener
    assert "video_selfshot2_finish_creative_details" in profile_callback
    assert "video_selfshot2_compile_prompts" in finisher
    assert '"prompts"' in finisher


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

    for name in ("video_selfshot2_render", "video_selfshot3_render"):
        assert 'f"video_tail|{shared_tail_return}|open"' in _function_source(name)
    assert 'f"video_tail|{tail_return}|open"' in _function_source(
        "video_selfshot3_render_prompt_review"
    )

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
    assert "video_profile_scene1_can_return_to_shared_tail(state, tail_return)" in image_done
    assert 'video_tail9_render(query, uid, context, tail_return)' in image_done


def test_script_copy_and_file_review_keep_full_source_before_parser_and_selected_count() -> None:
    suggestions = _function_source("video_script_suggestions_text")
    proposal = _function_source("video_script_proposal_review_text")
    file_review = _function_source("video_script_review_keyboard")

    assert "Chi tiết sáng tạo" in suggestions
    assert "Số cảnh đề xuất" in proposal
    assert "✅ Dùng nội dung file" in file_review
    assert "⬅️ Quay lại tải file" in file_review
    assert "Gửi file khác" not in file_review
    assert "Bước tải file" not in file_review


def test_count_first_callbacks_restore_the_existing_count_and_ratio_screens() -> None:
    callback = _function_source("handle_video_product_callback")
    count_screen = _action_block("script_entry_count_screen", "script_entry_count_custom")
    count = _action_block("script_entry_count", "script_entry_ratio_screen")
    ratio_screen = _action_block("script_entry_ratio_screen", "script_entry_ratio")
    ratio = _action_block("script_entry_ratio", "script_goal_screen")

    assert '"script_entry_count"' in count_screen
    assert '"awaiting_script_entry_count"' in callback
    assert 'script_entry_scene_count=scene_count' in count
    assert '"script_entry_ratio"' in count
    assert '"script_entry_ratio"' in ratio_screen
    assert 'script_ratio=ratio' in ratio
    assert '"script_ai_content_source"' in ratio


def test_script_duration_never_recalculates_or_overwrites_the_selected_scene_count() -> None:
    callback = _function_source("handle_video_product_callback")
    pending = _function_source("handle_video_product_pending_text")

    duration = _action_block("script_duration", "script_ai_review")
    duration_pending = pending[
        pending.index('if current_step == "awaiting_script_ai_duration":') :
        pending.index('if current_step == "awaiting_script_ai_edit":')
    ]
    assert "estimated_scene_count" not in duration
    assert "script_entry_scene_count=" not in duration
    assert "estimated_scene_count" not in duration_pending
    assert "script_entry_scene_count=" not in duration_pending
    assert 'current_step == "awaiting_script_entry_count"' in pending


def test_script_ai_parser_keeps_the_selected_scene_count_locked_without_a_second_choice() -> None:
    callback = _function_source("handle_video_product_callback")
    use_start = callback.index('if action == "script_ai_use":')
    use_end = callback.index('if action == "script_file_use":', use_start)
    use_block = callback[use_start:use_end]
    custom_start = callback.index('if action == "script_count_custom":')
    custom_end = callback.index('if product_id == "script_image_video":', custom_start)
    custom_block = callback[custom_start:custom_end]
    count_keyboard = _function_source("video_flow7_script_count_keyboard")
    pending = _function_source("handle_video_product_pending_text")
    pending_start = pending.index('if current_step == "awaiting_script_scene_count":')
    pending_end = pending.index('if current_step == "awaiting_existing_script":', pending_start)
    pending_block = pending[pending_start:pending_end]

    assert "locked_ai" in use_block
    assert "locked=locked_ai" in use_block
    assert "locked_ai" in custom_block
    assert "if locked_ai:" in pending_block
    assert "locked=True" in pending_block
    assert "locked: bool = False" in count_keyboard


def test_selfshot2_creative_controls_back_to_scene_plan() -> None:
    creative_keyboard = _function_source("video_scene3_creative_keyboard")

    assert "selfshot2_creative_setup" in creative_keyboard
    assert 'vproduct|ss2|show|scene_plan' in creative_keyboard


def test_storyboard_legacy_finish_preserves_completed_addon_review_then_enters_quality() -> None:
    callback = _function_source("_handle_storyboard2_callback_impl")
    finish_start = callback.index('if action == "finish":')
    finish_end = callback.index('if action in deferred_answer_actions:', finish_start)
    finish = callback[finish_start:finish_end]

    assert "video_tail9.mark_addon_complete" in finish
    assert "video_tail9.mark_review_complete" in finish
    assert 'video_tail9_render(query, uid, context, "quality")' in finish
    assert 'video_tail9_render(query, uid, context, "addon")' not in finish


def test_storyboard_canonical_transition_enters_one_shared_addon_and_review_tail() -> None:
    callback = _function_source("_handle_storyboard2_callback_impl")
    start = callback.index('if action in {"transition_natural", "transition_done"}:')
    end = callback.index('if action == "addons_screen":', start)
    transition = callback[start:end]

    assert 'action in {"transition_natural", "transition_done"}' in transition
    assert "storyboard2_scene3_handoff(context, board)" in transition
    assert 'video_tail9_render(query, uid, context, "addon")' in transition
    assert 'video_storyboard2.move(board, "addons")' not in transition
    assert 'board["addons"] = {}' not in transition


def test_selfshot2_enters_the_same_shared_addon_tail_as_selfshot3() -> None:
    callback = _function_source("handle_video_product_callback")
    start = callback.index('if operation == "finish":')
    end = callback.index('if operation == "compile_prompts"', start)
    finish = callback[start:end]

    assert "video_tail9.mark_addon_complete" not in finish
    assert "video_tail9.mark_review_complete" not in finish
    assert 'video_tail9_render(query, uid, context, "quality")' not in finish
    assert 'video_tail9_render(query, uid, context, "addon")' in finish


def test_selfshot3_keeps_the_shared_addon_for_logo_and_watermark() -> None:
    callback = _function_source("handle_video_product_callback")
    ss3_start = callback.index('if action == "ss3":')
    finish_start = callback.index('if operation == "finish":', ss3_start)
    finish_end = callback.index('if operation == "source":', finish_start)
    finish = callback[finish_start:finish_end]

    assert 'video_tail9_render(query, uid, context, "addon")' in finish


def test_selfshot3_quality_converts_source_duration_to_billable_scene_count() -> None:
    callback = _function_source("handle_video_tail_callback")
    quality_start = callback.index('if section == "quality"')
    quality_end = callback.index('if section == "confirm"', quality_start)
    quality = callback[quality_start:quality_end]
    helper = _function_source("video_selfshot3_scene_count_for_quality")
    host = _function_source("video_selfshot3_tail_host")
    quality_text = _function_source("video_tail9_quality_text")

    assert "video_selfshot3_scene_count_for_quality" in quality
    assert "selection_tail = dict(tail)" in quality
    assert '"scene_count": calculated_scene_count' in quality
    assert '"estimated_duration": calculated_scene_count * scene_seconds' in quality
    assert "video_tail9_commercial_preflight" in quality
    assert "selection_tail," in quality
    assert "tail = selection_tail" in quality
    assert "math.ceil" in helper
    assert "source_duration_seconds" in helper
    assert "video_selfshot3.PRODUCT_ID" in helper
    assert "video_selfshot3_scene_count_for_quality" in quality_text
    assert 'segment_duration_seconds = float(segment.get("duration_ms") or 0) / 1000.0' in host
    assert "segment_duration_seconds or float(" in host


def test_script_creative_details_finish_before_goal_or_scene_plan_without_opening_audio() -> None:
    callback = _function_source("handle_video_profile_studio_callback")
    finish = _function_source("video_script_finish_creative_details")

    req_none = callback[
        callback.index('if action == "req_none":') :
        callback.index('if action == "req_done":')
    ]
    req_done = callback[
        callback.index('if action == "req_done":') :
        callback.index('if action == "material":')
    ]
    assert "video_script_finish_creative_details" in req_none
    assert "video_script_finish_creative_details" in req_done
    assert req_none.index("video_script_finish_creative_details") < req_none.index('"audio_plan"')
    assert req_done.index("video_script_finish_creative_details") < req_done.index('"audio_plan"')
    assert 'phase == "post_parser"' in finish
    assert '"script_ai_goal"' in finish
    assert '"scene_plan"' in finish


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
