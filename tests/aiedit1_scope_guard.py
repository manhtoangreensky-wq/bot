import subprocess


AIEDIT1_TEST_FILE = "tests/test_p0_video_aiedit1_blackbox_special_effects_transformation.py"
AIEDIT1_BRANCH_PREFIX = "hotfix/p0-video-aiedit1-"
AIEDIT1_SCOPE_FILES = frozenset(
    {
        "bot.py",
        "local_worker.py",
        "services/video_ai_edit_prompt.py",
        "services/video_ai_edit_provider.py",
        "services/video_ai_edit_router.py",
        "services/video_ai_edit_status.py",
        "services/video_ai_edit_validation.py",
        "tests/aiedit1_scope_guard.py",
        AIEDIT1_TEST_FILE,
        "tests/test_p0_17b11_video_ui_ux_cleanup.py",
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
    return AIEDIT1_TEST_FILE in normalized or _current_branch().startswith(AIEDIT1_BRANCH_PREFIX)


def without_aiedit1_scope(paths):
    normalized = _normalize(paths)
    if not aiedit1_scope_active(normalized):
        return normalized
    return normalized - AIEDIT1_SCOPE_FILES


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
