from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from services import profile_router


REPO_ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (REPO_ROOT / "bot.py").read_text(encoding="utf-8")
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
TEST_FILE = "tests/test_p0_video_knowledge1_profile_router_and_studio_menu.py"
ALIGNED_REGRESSION_TESTS = {
    "tests/test_core.py",
    "tests/test_p0_17b11_video_ui_ux_cleanup.py",
    "tests/test_p0_18f_video_menu_route_audit_fix_only.py",
    "tests/test_p0_18k_video_menu_flow_standardization_routing_matrix.py",
    "tests/test_p0_18m_restore_canonical_video_product_flows_from_backup.py",
    "tests/test_p0_18n_hard_lock_video_ui_ux_router_state_machine_back_matrix.py",
    "tests/test_p0_18n1_unify_video_product_entry_ui_flow_matrix.py",
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
    assert validation["profile_count"] == 8
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
    assert len(ids) == 8
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


def test_main_video_menu_exposes_studio_and_edit_hub() -> None:
    assert len(profile_router.STUDIO_PROFILE_OPTIONS) == 14
    assert '("profile_studio", "video_local_edit")' in BOT_SOURCE
    assert '"label_vi": "🧠 Studio Profile AI"' in BOT_SOURCE
    assert '"entry_callback": "vprofile|menu"' in BOT_SOURCE
    assert '"label_vi": "🛠 Chỉnh sửa video"' in BOT_SOURCE
    assert '"entry_callback": "videoedit|hub"' in BOT_SOURCE
    assert 'CallbackQueryHandler(handle_video_profile_studio_callback, pattern=r"^vprofile\\|")' in BOT_SOURCE


def test_edit_video_hub_contains_manual_ai_and_split_scaffolds() -> None:
    hub = _source_between("def video_edit_hub_text", "def video_editor_menu_text")
    assert "✂️ Chỉnh sửa thủ công" in hub
    assert "✨ Chỉnh sửa bằng AI" in hub
    assert "🧩 Cắt video nhiều đoạn" in hub
    assert 'callback_data="videoedit|manual_info"' in hub
    assert 'callback_data="videoedit|ai_info"' in hub
    assert 'callback_data="videoedit|split_info"' in hub
    assert 'callback_data="videoedit|hub"' in hub
    assert "chưa xử lý video và chưa trừ Xu" in hub


def test_profile_studio_back_routes_to_exact_previous_screen() -> None:
    helpers = _source_between("VIDEO_PROFILE_STUDIO_SESSION_KEY", "def video_edit_hub_text")
    callback = _source_between("async def handle_video_profile_studio_callback", "async def handle_video_editor_callback")
    assert 'callback_data="menu|main_video"' in helpers
    assert 'callback_data="vprofile|back_question"' in helpers
    assert 'callback_data="vprofile|back_preview"' in helpers
    assert 'if action == "back_question"' in callback
    assert 'if action in {"edit", "back_preview"}' in callback
    assert '"step": "menu"' in callback
    assert '"step": "await_brief"' in callback


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
    touched = changed | untracked
    assert touched
    for path in touched:
        assert (
            path == "bot.py"
            or path == "services/profile_router.py"
            or path == TEST_FILE
            or path in ALIGNED_REGRESSION_TESTS
            or path.startswith("knowledge/")
        ), path
    forbidden_paths = {
        "local_worker.py",
        "remote_worker.py",
        "services/video_project_queue.py",
        "services/video_provider_router.py",
        "services/video_real_render_connector.py",
    }
    assert not (touched & forbidden_paths)
    assert not any("music" in path.lower() or "suno" in path.lower() or "subdub" in path.lower() for path in touched)
