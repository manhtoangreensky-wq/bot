import subprocess
from pathlib import Path


AIEDIT1_TEST_FILE = "tests/test_p0_video_aiedit1_blackbox_special_effects_transformation.py"
AIEDIT1_BRANCH_PREFIX = "hotfix/p0-video-aiedit1-"
LOCAL1_BOOT_COMPAT_SERVICE = "services/video_local_editing.py"
LOCAL1_BOOT_COMPAT_TEST = "tests/test_p0_video_local1_manual_editing_smart_splitter.py"
LOCAL1_BOOT_COMPAT_MARKER = "test_local1_concat_manifest_is_python311_safe_and_escapes_paths"
ARCH1_TEST_FILE = "tests/test_p0_profile_arch1_architecture_interior_realestate_studio.py"
ARCH1_SCOPE_MARKER = "test_arch1_scope_lock"
SCENE3UX2_BRANCH_PREFIX = "hotfix/p0-video-scene3ux2-"
VIDEO_EDIT3_BRANCH_PREFIX = "hotfix/p0-video-edit3-"
VIDEO_EDIT_COMPLETION_BRANCH_PREFIX = "fix/p0-videoedit-completion-"
VIDEO_EDIT_COMPLETION_SCOPE_FILES = frozenset(
    {
        "bot.py",
        "local_worker.py",
        "services/video_edit_state_machine.py",
        "services/video_edit_capabilities.py",
        "services/video_editengine1.py",
        "services/video_local_editing.py",
        "services/video_local_validation.py",
        "tests/aiedit1_scope_guard.py",
        "tests/test_p0_video_aiedit1_blackbox_special_effects_transformation.py",
        "tests/test_p0_video_editengine2_buttons_worker_heartbeat_package.py",
        "tests/test_p0_video_edit3_compact_manual_flow.py",
        "tests/test_p0_video_edit3_canonical_intake_route_state_machine.py",
        "tests/test_p0_video_edit2_upgrade_audio_ai_backstack.py",
        "tests/test_p0_video_finalflow12_golden_tail.py",
        "tests/test_p0_video_knowledge1_profile_router_and_studio_menu.py",
        "tests/test_p0_video_local1_manual_editing_smart_splitter.py",
        "tests/test_p0_video_statusrestore18_old_status_only.py",
        "tests/test_p0_video_tailflow16_dedupe_summary_audio_status.py",
        "tests/test_p0_videoedit_back_hierarchy_adapter.py",
        "tests/test_p0_videoedit_canonical_bot_routes.py",
        "tests/test_p0_videoedit_canonical_local_runtime.py",
        "tests/test_p0_videoedit_canonical_local_worker_receipt.py",
        "tests/test_p0_videoedit_canonical_navigation.py",
        "tests/test_p0_videoedit_job_safety.py",
        "tests/test_p0_videoedit_latest_status_navigation.py",
        "tests/test_p0_videoedit_local_free_job.py",
        "tests/test_p0_videoedit_parent_allowlist.py",
        "tests/test_p0_videoedit_real_media_matrix.py",
        "tests/test_p0_videoedit_review_parent_hardening.py",
        "tests/test_p0_videoedit_split_receipt_checkpoint.py",
        "tests/test_p1_localvideostudio27b_public_ui.py",
        "docs/superpowers/plans/2026-07-31-video-edit-completion-hardening.md",
        "docs/superpowers/plans/2026-08-01-video-edit-latest-status.md",
        "docs/superpowers/plans/2026-08-02-video-edit-cpu-verification-matrix.md",
        "docs/superpowers/specs/2026-08-01-video-edit-latest-status-design.md",
    }
)
VIDEO_EDIT3_SCOPE_FILES = frozenset(
    {
        "services/video_edit_state_machine.py",
        "services/video_local_validation.py",
        "tests/test_p0_video_edit3_canonical_intake_route_state_machine.py",
    }
)
SCENE3UX2_SCOPE_FILES = frozenset(
    {
        "bot.py",
        "services/video_scene3_flow.py",
        "tests/aiedit1_scope_guard.py",
        "tests/conftest.py",
        "tests/test_p0_profile_arch1_architecture_interior_realestate_studio.py",
        "tests/test_p0_video_knowledge1_profile_router_and_studio_menu.py",
        "tests/test_p0_video_scene3_restore_full_flow.py",
        "tests/test_p0_video_scene3ux2_guided_style_addon_position_flow.py",
    }
)
ARCH1_PROFILE_FILES = frozenset(
    {
        "knowledge/profiles/architecture_exterior.json",
        "knowledge/profiles/interior_design.json",
        "knowledge/profiles/space_renovation.json",
        "knowledge/profiles/real_estate_property.json",
        "knowledge/profiles/architecture_walkthrough.json",
        "knowledge/profiles/floorplan_visualization.json",
        "knowledge/profiles/commercial_space.json",
        "knowledge/profiles/landscape_garden.json",
    }
)
ARCH1_RUNTIME_FILES = frozenset(
    {
        "services/profile_router.py",
        "services/architecture_profile_router.py",
        "services/architecture_prompt_builder.py",
        "services/architecture_video_prompt_builder.py",
        "services/architecture_scene_planner.py",
        "services/architecture_profile_status.py",
    }
)
ARCH1_SCOPE_FILES = frozenset(
    {
        *ARCH1_RUNTIME_FILES,
        "tests/aiedit1_scope_guard.py",
        ARCH1_TEST_FILE,
        "tests/test_p0_cost2_provider_quota_cycle_reset_alert_baseline.py",
        "tests/test_p0_cskh1_telegram_business_auto_support_bot.py",
        "tests/test_p0_video_knowledge1_profile_router_and_studio_menu.py",
    }
)
ARCH1_ALLOWED_FILES = frozenset({"bot.py"}) | ARCH1_SCOPE_FILES | ARCH1_PROFILE_FILES
AIEDIT1_SCOPE_FILES = frozenset(
    {
        "bot.py",
        "local_worker.py",
        "services/video_ai_edit_prompt.py",
        "services/video_ai_edit_provider.py",
        "services/video_ai_edit_router.py",
        "services/video_ai_edit_status.py",
        "services/video_ai_edit_validation.py",
        "services/video_edit_capabilities.py",
        "services/video_local_editing.py",
        "tests/aiedit1_scope_guard.py",
        AIEDIT1_TEST_FILE,
        "tests/test_p0_17b11_video_ui_ux_cleanup.py",
        "tests/test_p0_17b7_1_video_menu_cleanup.py",
        "tests/test_p0_18f_video_menu_route_audit_fix_only.py",
        "tests/test_p0_18k_video_menu_flow_standardization_routing_matrix.py",
        "tests/test_p0_18m_restore_canonical_video_product_flows_from_backup.py",
        "tests/test_p0_18q2_video_auto_refresh_status_like_subdub_only.py",
        "tests/test_p0_23h14f_music_voice_preset_duet_progress_single_track_fix.py",
        "tests/test_p0_23h14g_music_expose_custom_lyrics_button_on_idea_screen.py",
        "tests/test_p0_23h14h_music_compact_idea_menu_restore_female_voice_pr173.py",
        "tests/test_p0_aichat1_copilot_consent.py",
        "tests/test_p0_aichat1b_free_tools_menu_cleanup.py",
        "tests/test_p0_aichat4_smart_intent_context_backstack.py",
        "tests/test_p0_aichat5_live_context_action_trace.py",
        "tests/test_p0_aichat6_open_public_live_flows.py",
        "tests/test_p0_cost2_provider_quota_cycle_reset_alert_baseline.py",
        "tests/test_p0_cskh1_telegram_business_auto_support_bot.py",
        "tests/test_p0_cskh2_toan_aas_training_data_playbook.py",
        "tests/test_p0_cskh2a_business_arm_mode_without_connection.py",
        "tests/test_p0_cskh3_conversation_brain_natural_replies.py",
        "tests/test_p0_cskh4_aas_product_knowledge_pricing_mixed_intents.py",
        "tests/test_p0_cskh5b_live_business_followup_pricing_runtime.py",
        "tests/test_p0_cskh5c_business_self_echo_duplicate_guard.py",
        "tests/test_p0_cskh6_human_touch_playbook_safe_training_pack.py",
        "tests/test_p0_free1_refresh_free_tools_menu_existing_zero_cost_shortcuts.py",
        "tests/test_p0_image_live1_public_image_generation.py",
        "tests/test_p0_image_live1b_provider_freeze_scope_public_confirm.py",
        "tests/test_p0_image_live1d_vproduct_public_confirm_unblocked.py",
        "tests/test_p0_video_duration2_scene_or_seconds_pricing_decision.py",
        "tests/test_p0_video_knowledge1_profile_router_and_studio_menu.py",
        "tests/test_p0_video_local1_manual_editing_smart_splitter.py",
        "tests/test_p0_video_edit2_upgrade_audio_ai_backstack.py",
    }
)


def _normalize(paths):
    return {str(path).strip().replace("\\", "/") for path in paths if str(path).strip()}


def _current_branch():
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def aiedit1_scope_active(paths=()):
    normalized = _normalize(paths)
    return (
        AIEDIT1_TEST_FILE in normalized
        or _current_branch().startswith(AIEDIT1_BRANCH_PREFIX)
        or _current_branch().startswith(SCENE3UX2_BRANCH_PREFIX)
    )


def arch1_scope_active(paths=()):
    normalized = _normalize(paths)
    marker_path = Path(__file__).resolve().parents[1] / ARCH1_TEST_FILE
    marker_present = (
        marker_path.is_file()
        and ARCH1_SCOPE_MARKER in marker_path.read_text(encoding="utf-8")
    )
    has_architecture_change = bool(normalized & (ARCH1_RUNTIME_FILES | ARCH1_PROFILE_FILES))
    return (
        marker_present
        and ARCH1_TEST_FILE in normalized
        and has_architecture_change
        and normalized <= ARCH1_ALLOWED_FILES
    )


def aiedit1_scope_files(paths=()):
    normalized = _normalize(paths)
    allowed = set(AIEDIT1_SCOPE_FILES)
    if _current_branch().startswith(SCENE3UX2_BRANCH_PREFIX):
        allowed.update(SCENE3UX2_SCOPE_FILES)
    if _current_branch().startswith(VIDEO_EDIT3_BRANCH_PREFIX):
        allowed.update(VIDEO_EDIT3_SCOPE_FILES)
    if _current_branch().startswith(VIDEO_EDIT_COMPLETION_BRANCH_PREFIX):
        allowed.update(VIDEO_EDIT_COMPLETION_SCOPE_FILES)
    marker_path = Path(__file__).resolve().parents[1] / LOCAL1_BOOT_COMPAT_TEST
    marker_present = (
        marker_path.is_file()
        and LOCAL1_BOOT_COMPAT_MARKER in marker_path.read_text(encoding="utf-8")
    )
    if (
        {LOCAL1_BOOT_COMPAT_SERVICE, LOCAL1_BOOT_COMPAT_TEST} <= normalized
        and marker_present
    ):
        allowed.add(LOCAL1_BOOT_COMPAT_SERVICE)
    if arch1_scope_active(normalized):
        allowed.update(ARCH1_SCOPE_FILES)
        allowed.update(ARCH1_PROFILE_FILES)
    return frozenset(allowed)


def without_aiedit1_scope(paths):
    normalized = _normalize(paths)
    if not aiedit1_scope_active(normalized):
        return normalized
    return normalized - aiedit1_scope_files(normalized)


def aiedit1_local_worker_allowed(paths=()):
    return aiedit1_scope_active(paths)


def aiedit1_bot_diff_has_no_locked_markers(diff, markers):
    if not aiedit1_scope_active():
        return False
    changed_lines = "\n".join(
        line
        for line in str(diff).splitlines()
        if (line.startswith("+") or line.startswith("-")) and not line.startswith(("+++", "---"))
    ).lower()
    return not any(str(marker).lower() in changed_lines for marker in markers)
