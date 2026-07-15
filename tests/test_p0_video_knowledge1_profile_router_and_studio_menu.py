from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from aiedit1_scope_guard import aiedit1_scope_active, without_aiedit1_scope

from services import profile_router


REPO_ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (REPO_ROOT / "bot.py").read_text(encoding="utf-8")
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
TEST_FILE = "tests/test_p0_video_knowledge1_profile_router_and_studio_menu.py"
LOCAL1_TEST_FILE = "tests/test_p0_video_local1_manual_editing_smart_splitter.py"
AIEDIT1_TEST_FILE = "tests/test_p0_video_aiedit1_blackbox_special_effects_transformation.py"
ARCH1_TEST_FILE = "tests/test_p0_profile_arch1_architecture_interior_realestate_studio.py"
SCENE1_TEST_FILE = "tests/test_p0_video_scene1_semantic_story_planner_addon_aware_flow.py"
SCENE2_TEST_FILE = "tests/test_p0_video_scene2_public_entry_order_legacy_bypass_removal.py"
SCENE2_UIFLOW_TEST_FILE = "tests/test_p0_video_uiflow1_align_video_ai_flows_to_hot_trend.py"
SCENE2_UIFLOW_LOCK_TEST_FILE = "tests/test_p0_video_uiflow_lock_current_good_flow.py"
SCENE2_DURATION_TEST_FILE = "tests/test_p0_video_duration2_scene_or_seconds_pricing_decision.py"
SCENE3_TEST_FILE = "tests/test_p0_video_scene3_restore_full_flow.py"
SCENE3UX2_TEST_FILE = "tests/test_p0_video_scene3ux2_guided_style_addon_position_flow.py"
IDEA2_TEST_FILE = "tests/test_p0_video_idea2_dynamic_presets_admin_script_intake.py"
SCENE3UX3_TEST_FILE = "tests/test_p0_video_scene3ux3_unified_video_idea_hub.py"
SCENE3UX4_TEST_FILE = "tests/test_p0_video_scene3ux4_reference_only_idea_hub.py"
IDEA2_SERVICE_FILES = {
    "services/video_idea_catalog.py",
    "services/video_idea_script_intake.py",
    "services/video_idea_store.py",
}
ARCH1_SERVICE_FILES = {
    "services/architecture_profile_router.py",
    "services/architecture_prompt_builder.py",
    "services/architecture_video_prompt_builder.py",
    "services/architecture_scene_planner.py",
    "services/architecture_profile_status.py",
}
ALIGNED_REGRESSION_TESTS = {
    "tests/test_core.py",
    "tests/test_p0_17b7_1_video_menu_cleanup.py",
    "tests/test_p0_17c1_payos_signature_idempotency.py",
    "tests/test_p0_17c2_payos_auto_topup_limits.py",
    "tests/test_p0_17b11_video_ui_ux_cleanup.py",
    "tests/test_p0_18f_video_menu_route_audit_fix_only.py",
    "tests/test_p0_18k_video_menu_flow_standardization_routing_matrix.py",
    "tests/test_p0_18m_restore_canonical_video_product_flows_from_backup.py",
    "tests/test_p0_18n_hard_lock_video_ui_ux_router_state_machine_back_matrix.py",
    "tests/test_p0_18n1_unify_video_product_entry_ui_flow_matrix.py",
    "tests/test_p0_18q2_video_auto_refresh_status_like_subdub_only.py",
    "tests/test_p0_cost2_provider_quota_cycle_reset_alert_baseline.py",
    "tests/test_p0_image_live1_public_image_generation.py",
    "tests/test_p0_image_live1b_provider_freeze_scope_public_confirm.py",
    "tests/test_p0_image_live1d_vproduct_public_confirm_unblocked.py",
    "tests/test_p0_video_uiflow_lock_current_good_flow.py",
}


def _source_between(start: str, end: str) -> str:
    assert start in BOT_SOURCE
    assert end in BOT_SOURCE
    return BOT_SOURCE.split(start, 1)[1].split(end, 1)[0]


def _git_lines(*args: str) -> set[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {line.strip().replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()}


def test_all_knowledge_json_loads_and_startup_validation_is_safe() -> None:
    files = sorted(KNOWLEDGE_ROOT.rglob("*.json"))
    assert files
    for path in files:
        assert json.loads(path.read_text(encoding="utf-8")), path
    validation = profile_router.validate_knowledge_catalog()
    assert validation["ok"] is True
    assert validation["errors"] == []
    assert validation["profile_count"] == 15
    assert validation["video_store_count"] == 6


def test_invalid_profile_fails_safe_without_breaking_public_selection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "broken.json").write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(profile_router, "PROFILE_ROOT", tmp_path)
    profiles, errors = profile_router.load_profiles(strict=False)
    assert profiles == {}
    assert errors and "json_load_failed" in errors[0]
    fallback = profile_router.profile_for_selection("cinematic_vfx")
    assert fallback["profile_id"] == profile_router.SAFE_FALLBACK_PROFILE_ID
    assert fallback["clarifying_questions"]


def test_every_reference_maps_to_at_least_one_existing_store() -> None:
    manifest = json.loads(profile_router.REFERENCE_MANIFEST_PATH.read_text(encoding="utf-8"))
    references = manifest["references"]
    assert len(references) == 18
    assert len({item["reference_id"] for item in references}) == 18
    profile_payloads = [json.loads(path.read_text(encoding="utf-8")) for path in profile_router.PROFILE_ROOT.glob("*.json")]
    video_payloads = [json.loads(path.read_text(encoding="utf-8")) for path in profile_router.VIDEO_ROOT.glob("*.json")]
    profile_ids = {payload["profile_id"] for payload in profile_payloads}
    video_store_ids = {payload["store_id"] for payload in video_payloads}
    store_payloads = {
        **{payload["store_id"]: payload for payload in video_payloads},
        **{f"profile:{payload['profile_id']}": payload for payload in profile_payloads},
    }
    for reference in references:
        stores = reference.get("stores") or []
        assert stores, reference
        for store in stores:
            if str(store).startswith("profile:"):
                assert str(store).split(":", 1)[1] in profile_ids
            else:
                assert store in video_store_ids
            assert reference["reference_id"] in store_payloads[store]["source_reference_ids"]


def test_profile_ids_are_unique_and_profiles_have_required_fields() -> None:
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(profile_router.PROFILE_ROOT.glob("*.json"))]
    ids = [payload["profile_id"] for payload in payloads]
    assert len(ids) == 15
    assert len(ids) == len(set(ids))
    for payload in payloads:
        assert not profile_router.validate_profile_payload(payload, source=payload["profile_id"])


@pytest.mark.parametrize(
    ("user_text", "expected"),
    [
        ("Thiết kế nội thất căn hộ hiện đại", "architecture_interior"),
        ("Cinematic architecture exterior facade walkthrough", "architecture_interior"),
        ("Video bất động sản giới thiệu căn hộ", "real_estate_property"),
        ("Biến cảnh quay thường thành cinematic fantasy VFX", "cinematic_vfx"),
        ("Rigging nhân vật hoạt hình 3D và motion capture", "animation_character"),
        ("Virtual fashion model lookbook runway", "fashion_virtual_model"),
        ("3D product showcase object capture", "product_3d_showcase"),
        ("SaaS app demo screen recording workflow", "app_game_saas_demo"),
        ("Tutorial giải thích dạng talking head UGC", "creator_tutorial_ugc"),
    ],
)
def test_router_selects_expected_profile(user_text: str, expected: str) -> None:
    result = profile_router.route_profile(user_text)
    assert result.selected_profile_id == expected
    assert result.confidence > 0.5
    assert result.clarification_question == ""
    assert result.provider_called is False
    assert result.job_created is False
    assert result.outbox_created is False
    assert result.xu_charged == 0


def test_ambiguous_intent_asks_one_concise_clarification() -> None:
    result = profile_router.route_profile("Làm một video đẹp")
    assert result.confidence < 0.5
    assert result.clarification_question
    assert "?" in result.clarification_question


def test_explicit_selection_wins_and_customer_constraints_are_preserved() -> None:
    request = "Áo đỏ, nền trắng, giữ logo ACME ở góc phải"
    result = profile_router.route_profile(request, selected_profile="cinematic_vfx")
    assert result.selected_profile_id == "cinematic_vfx"
    assert result.confidence == 1.0
    assert result.matched_signals == ["explicit:cinematic_vfx"]
    assert request in result.professional_prompt
    assert "Do not invent addresses, dimensions, prices" in result.professional_prompt


def test_blackbox_router_honors_output_asset_language_ratio_duration_and_scenes() -> None:
    result = profile_router.route_profile(
        "Dashboard SaaS quản lý dự án",
        selected_profile="website_saas_demo",
        requested_output="image",
        uploaded_asset_type="screen capture",
        language="en",
        aspect_ratio="16:9",
        duration=16,
        scene_count=2,
    )
    assert result.selected_profile_id == "app_game_saas_demo"
    assert result.requested_output == "image"
    assert result.language == "en"
    assert result.editing_profile["aspect_ratio"] == "16:9"
    assert result.editing_profile["duration_seconds"] == 16
    assert len(result.scene_plan) == 2
    assert sum(scene["duration_seconds"] for scene in result.scene_plan) == 16
    assert "uploaded_asset_type" not in result.missing_fields


@pytest.mark.parametrize(
    ("user_text", "expected"),
    [
        ("nội thất căn hộ", "architecture_interior"),
        ("interior design walkthrough", "architecture_interior"),
        ("hoạt hình nhân vật", "animation_character"),
        ("character animation", "animation_character"),
        ("thời trang lookbook", "fashion_virtual_model"),
        ("fashion lookbook", "fashion_virtual_model"),
    ],
)
def test_vietnamese_and_english_aliases(user_text: str, expected: str) -> None:
    assert profile_router.route_profile(user_text).selected_profile_id == expected


def test_main_video_menu_hides_studio_but_preserves_internal_route_and_edit_hub() -> None:
    assert len(profile_router.STUDIO_PROFILE_OPTIONS) == 14
    public_rows = _source_between("VIDEO_PUBLIC_MENU_ROWS = (", "VIDEO_PUBLIC_ROUTE_MATRIX = {")
    assert "profile_studio" not in public_rows
    assert '("storyboard_prompt", "video_idea")' in public_rows
    assert '("video_local_edit", "video_downloader")' in public_rows
    assert '"label_vi": "🎯 Studio Profile AI"' in BOT_SOURCE
    assert '"entry_callback": "vprofile|menu"' in BOT_SOURCE
    assert '"label_vi": "🛠️ Chỉnh sửa / Nâng cấp video"' in BOT_SOURCE
    assert '"entry_callback": "videoedit|hub"' in BOT_SOURCE
    assert 'CallbackQueryHandler(handle_video_profile_studio_callback, pattern=r"^vprofile\\|")' in BOT_SOURCE


def test_edit_video_hub_restores_only_tools_with_real_existing_handlers() -> None:
    hub = _source_between("def video_edit_hub_keyboard", "def video_edit_info_text")
    assert "✨ Chỉnh sửa & nâng cấp bằng AI" in hub
    assert "✂️ Chỉnh sửa thủ công" in hub
    assert "🧹 Khôi phục chất lượng" in hub
    assert "❓ Hướng dẫn công cụ này" in hub
    for callback in (
        '"videoedit|ai"', '"videoedit|manual"', '"videoedit|restore"',
        '"videoedit|guide"', '"menu|main_video"',
    ):
        assert callback in hub
    for removed in ('"videoedit|audio"', '"videoedit|timeline"', '"videoedit|effects"', '"videoedit|plan"'):
        assert removed not in hub
    assert "videoedit|quick|" not in hub


def test_profile_studio_back_routes_to_exact_previous_screen() -> None:
    helpers = _source_between("VIDEO_PROFILE_STUDIO_SESSION_KEY", "def video_edit_hub_text")
    callback = _source_between("async def handle_video_profile_studio_callback", "async def handle_video_editor_callback")
    assert '("⬅️ Menu video" if is_vi else "⬅️ Video menu", "menu|main_video")' in helpers
    assert '[("⬅️ Quay lại", "vprofile|back"), ("🏠 Menu chính", "menu|main")]' in helpers
    assert "def video_profile_studio_pop_step" in helpers
    assert 'if action == "back"' in callback
    assert "video_profile_studio_pop_step(context, state)" in callback
    assert '"step": "menu"' in callback
    assert "VIDEO_SCENE1_CANONICAL_STEPS = video_scene3_flow.CANONICAL_STEPS" in helpers


def test_studio_is_session_draft_only_without_submit_job_outbox_or_charge() -> None:
    studio = _source_between("VIDEO_PROFILE_STUDIO_SESSION_KEY", "def video_edit_hub_text")
    studio += _source_between("async def handle_video_profile_studio_pending_text", "async def handle_video_editor_callback")
    for forbidden in (
        "video_provider_router",
        "ShopAIKey",
        "Key4U",
        "create_video_render_job",
        "create_video_project",
        "ensure_product_video_dispatch_outbox",
        "confirm_public_product_video_invoice",
        "deduct_xu",
        "charge_wallet",
    ):
        assert forbidden not in studio
    result = profile_router.route_profile("VFX điện ảnh", selected_profile="cinematic_vfx").to_dict()
    assert result["provider_called"] is False
    assert result["job_created"] is False
    assert result["outbox_created"] is False
    assert result["xu_charged"] == 0


def test_scope_does_not_touch_music_subdub_or_product_video_workers() -> None:
    changed = _git_lines("diff", "--name-only", "origin/main")
    untracked = {
        path for path in _git_lines("ls-files", "--others", "--exclude-standard")
        if not path.startswith("pytest-baseline-r1/")
    }
    raw_touched = changed | untracked
    aiedit1_active = aiedit1_scope_active(raw_touched)
    touched = without_aiedit1_scope(raw_touched)
    assert touched or aiedit1_active
    local1_scope = LOCAL1_TEST_FILE in touched
    local1_allowed = {
        "local_worker.py",
        "services/video_local_editing.py",
        "services/video_smart_splitter.py",
        "services/video_local_validation.py",
        LOCAL1_TEST_FILE,
        "tests/test_p0_free1_refresh_free_tools_menu_existing_zero_cost_shortcuts.py",
    } if local1_scope else set()
    aiedit1_scope = AIEDIT1_TEST_FILE in touched
    aiedit1_allowed = {
        "local_worker.py",
        "services/video_ai_edit_prompt.py",
        "services/video_ai_edit_provider.py",
        "services/video_ai_edit_router.py",
        "services/video_ai_edit_status.py",
        "services/video_ai_edit_validation.py",
        AIEDIT1_TEST_FILE,
    } if aiedit1_scope else set()
    arch1_scope = ARCH1_TEST_FILE in touched
    arch1_allowed = (
        ARCH1_SERVICE_FILES
        | {
            ARCH1_TEST_FILE,
            "tests/aiedit1_scope_guard.py",
            "tests/test_p0_cost2_provider_quota_cycle_reset_alert_baseline.py",
            "tests/test_p0_cskh1_telegram_business_auto_support_bot.py",
        }
    ) if arch1_scope else set()
    scene1_scope = SCENE1_TEST_FILE in touched
    scene1_allowed = {
        "services/video_addon_planner.py",
        "services/video_scene_continuity.py",
        "services/video_scene_transition_planner.py",
        "services/video_prompt_pattern_library.py",
        "services/video_semantic_scene_planner.py",
        "services/video_scene_prompt_builder.py",
        SCENE1_TEST_FILE,
    } if scene1_scope else set()
    scene2_allowed = {
        SCENE2_TEST_FILE,
        SCENE2_UIFLOW_TEST_FILE,
        SCENE2_UIFLOW_LOCK_TEST_FILE,
        SCENE2_DURATION_TEST_FILE,
    } if SCENE2_TEST_FILE in touched else set()
    scene3_allowed = {
        "services/video_scene3_flow.py",
        SCENE3_TEST_FILE,
        SCENE3UX2_TEST_FILE,
        "tests/test_p0_video_scene3boot1_bot_syntax_and_caption_render.py",
    } if SCENE3_TEST_FILE in touched else set()
    idea2_allowed = (
        IDEA2_SERVICE_FILES
        | {IDEA2_TEST_FILE, SCENE3UX3_TEST_FILE, SCENE3UX4_TEST_FILE}
    ) if IDEA2_TEST_FILE in touched else set()
    edit2_test = "tests/test_p0_video_edit2_upgrade_audio_ai_backstack.py"
    edit2_allowed = {
        edit2_test,
        "services/video_edit_capabilities.py",
        "services/video_local_editing.py",
        "services/video_ai_edit_prompt.py",
        "tests/aiedit1_scope_guard.py",
        "tests/test_p0_video_local1_manual_editing_smart_splitter.py",
    } if edit2_test in touched else set()
    for path in touched:
        assert (
            path == "bot.py"
            or path == "services/profile_router.py"
            or path == TEST_FILE
            or path in ALIGNED_REGRESSION_TESTS
            or path.startswith("knowledge/")
            or path in local1_allowed
            or path in aiedit1_allowed
            or path in arch1_allowed
            or path in scene1_allowed
            or path in scene2_allowed
            or path in scene3_allowed
            or path in idea2_allowed
            or path in edit2_allowed
        ), path
    forbidden_paths = {
        "local_worker.py",
        "remote_worker.py",
        "services/video_project_queue.py",
        "services/video_provider_router.py",
        "services/video_real_render_connector.py",
    }
    assert not ((touched - local1_allowed - aiedit1_allowed) & forbidden_paths)
    runtime_touched = {path for path in touched if not path.startswith("tests/")}
    assert not any(
        "music" in path.lower() or "suno" in path.lower() or "subdub" in path.lower()
        for path in runtime_touched
    )
