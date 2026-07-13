from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from services import architecture_profile_router, architecture_profile_status
from services.architecture_prompt_builder import (
    ARCHITECTURAL_STYLES,
    EXTERIOR_PROJECT_TYPES,
    IMAGE_NEGATIVE_PROMPT,
    INTERIOR_SPACE_TYPES,
    RENOVATION_SCOPES,
    build_architecture_image_prompt,
    conflicting_styles,
    default_preservation,
)
from services.architecture_scene_planner import build_architecture_scene_plan
from services.architecture_video_prompt_builder import (
    CAMERA_PRESETS,
    VIDEO_NEGATIVE_PROMPT,
    build_architecture_video_prompt,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (REPO_ROOT / "bot.py").read_text(encoding="utf-8")
TEST_FILE = "tests/test_p0_profile_arch1_architecture_interior_realestate_studio.py"
SCENE2_TEST_FILE = "tests/test_p0_video_scene2_public_entry_order_legacy_bypass_removal.py"
SCENE2_UIFLOW_TEST_FILE = "tests/test_p0_video_uiflow1_align_video_ai_flows_to_hot_trend.py"
SCENE2_UIFLOW_LOCK_TEST_FILE = "tests/test_p0_video_uiflow_lock_current_good_flow.py"
SCENE2_DURATION_TEST_FILE = "tests/test_p0_video_duration2_scene_or_seconds_pricing_decision.py"


def _git_lines(*args: str) -> set[str]:
    completed = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, check=True, capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    return {line.strip().replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()}


def _architecture_source() -> str:
    return BOT_SOURCE.split('ARCHITECTURE_PROFILE_SESSION_KEY = "architecture_profile_studio"', 1)[1].split("def video_edit_hub_text", 1)[0]


def test_arch1_studio_menu_present() -> None:
    assert "🏗 Studio Kiến trúc" in BOT_SOURCE
    assert 'callback_data="archprofile|menu"' in BOT_SOURCE
    assert "Chọn loại dự án" in BOT_SOURCE


def test_arch1_all_profile_buttons_present() -> None:
    source = _architecture_source()
    assert "architecture_profile_router.ARCHITECTURE_PROFILE_MENU" in source
    ids = []
    for profile_id, label in architecture_profile_router.ARCHITECTURE_PROFILE_MENU:
        ids.append(profile_id)
        assert label
    assert ids == [
        "architecture_exterior", "interior_design", "space_renovation",
        "real_estate_property", "architecture_walkthrough",
        "floorplan_visualization", "commercial_space", "landscape_garden", "auto",
    ]


def test_arch1_exact_back_to_profile_studio() -> None:
    source = _architecture_source()
    assert 'callback_data="vprofile|menu"' in source
    assert 'callback_data="archprofile|back_question"' in source
    assert 'callback_data="archprofile|back_preview"' in source
    assert 'callback_data="archprofile|back_output"' in source
    assert 'callback_data="archprofile|back_assets"' in source
    assert 'CallbackQueryHandler(handle_architecture_profile_callback, pattern=r"^archprofile\\|")' in BOT_SOURCE


def test_arch1_no_provider_job_or_charge_from_menu() -> None:
    source = _architecture_source()
    for forbidden in (
        "video_provider_router", "ShopAIKey", "Key4U", "create_video_project",
        "create_video_render_job", "ensure_product_video_dispatch_outbox",
        "deduct_xu", "charge_wallet",
    ):
        assert forbidden not in source
    assert '"provider_called"] = False' in source
    assert '"job_created"] = False' in source
    assert '"outbox_created"] = False' in source
    assert '"xu_charged"] = 0' in source


def test_arch1_all_profile_json_loads() -> None:
    profiles, errors = architecture_profile_router.load_architecture_profiles(strict=False)
    assert errors == []
    assert set(profiles) == set(architecture_profile_router.ARCHITECTURE_PROFILE_IDS)
    assert len(profiles) == 8


def test_arch1_profile_ids_unique_and_required_fields_present() -> None:
    profiles, _ = architecture_profile_router.load_architecture_profiles(strict=True)
    assert len(profiles) == len(set(profiles)) == 8
    for profile_id, payload in profiles.items():
        assert payload["profile_id"] == profile_id
        assert payload["title_vi"]
        assert architecture_profile_router.validate_architecture_profile(payload, source=profile_id) == []


def test_arch1_duplicate_or_filename_mismatched_profile_fails_safely(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profiles, _ = architecture_profile_router.load_architecture_profiles(strict=True)
    for profile_id, payload in profiles.items():
        item = dict(payload)
        if profile_id == "architecture_exterior":
            item["profile_id"] = "interior_design"
        (tmp_path / f"{profile_id}.json").write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(architecture_profile_router, "PROFILE_ROOT", tmp_path)
    loaded, errors = architecture_profile_router.load_architecture_profiles(strict=False)
    assert "architecture_exterior" not in loaded
    assert any("filename_mismatch" in error or "duplicate_profile_id" in error for error in errors)


def test_arch1_reference_ids_valid() -> None:
    valid = architecture_profile_router.valid_reference_ids()
    profiles, _ = architecture_profile_router.load_architecture_profiles(strict=True)
    for payload in profiles.values():
        assert set(payload["source_reference_ids"]) <= valid


def test_arch1_invalid_profile_fails_safely(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "interior_design.json").write_text("{bad-json", encoding="utf-8")
    monkeypatch.setattr(architecture_profile_router, "PROFILE_ROOT", tmp_path)
    profiles, errors = architecture_profile_router.load_architecture_profiles(strict=False)
    assert profiles == {}
    assert errors
    route = architecture_profile_router.route_architecture_profile({"user_text": "Làm nội thất"})
    assert route["profile_id"] == "interior_design"
    assert route["knowledge_valid"] is False
    assert route["provider_called"] is False


def test_arch1_project_space_and_renovation_libraries_complete() -> None:
    assert {"Nhà phố", "Biệt thự", "Nhà xưởng", "Trường học", "Cảnh quan sân vườn"} <= set(EXTERIOR_PROJECT_TYPES)
    assert {"Phòng khách", "Phòng ngủ", "Phòng tắm", "Văn phòng", "Spa / salon"} <= set(INTERIOR_SPACE_TYPES)
    assert {"Giữ nguyên toàn bộ hình học", "Chỉ đổi màu/vật liệu", "Cải tạo toàn diện"} <= set(RENOVATION_SCOPES)


def test_arch1_style_library_complete() -> None:
    assert len(ARCHITECTURAL_STYLES) == 27
    required = {
        "key_forms", "dominant_materials", "palette", "lighting",
        "furniture_characteristics", "exterior_characteristics",
        "unsuitable_combinations", "prompt_vocabulary", "negative_constraints",
    }
    for style in ARCHITECTURAL_STYLES.values():
        assert required <= set(style)
        assert all(style[key] not in (None, "") for key in required - {"unsuitable_combinations"})


def test_arch1_style_material_and_palette_mapping() -> None:
    for name in ("Japandi", "Indochine", "Industrial", "Modern Vietnamese", "Resort style"):
        assert ARCHITECTURAL_STYLES[name]["dominant_materials"]
        assert ARCHITECTURAL_STYLES[name]["palette"]


def test_arch1_conflicting_styles_ask_clarification_and_explicit_fusion_allowed() -> None:
    assert conflicting_styles(["Tối giản", "Art Deco"])
    assert conflicting_styles(["Tối giản", "Art Deco"], explicit_fusion=True) == []
    blocked = build_architecture_image_prompt({"style": ["Tối giản", "Art Deco"]})
    assert blocked["ok"] is False
    assert "chọn một phong cách" in blocked["clarification_question"]
    allowed = build_architecture_image_prompt({"style": ["Tối giản", "Art Deco"], "explicit_style_fusion": True})
    assert allowed["ok"] is True


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Làm mặt tiền căn nhà hiện đại hơn", "architecture_exterior"),
        ("Thiết kế lại phòng khách này theo phong cách Japandi", "interior_design"),
        ("Biến phòng trống thành phòng ngủ cao cấp", "space_renovation"),
        ("Video bất động sản để đăng bán căn hộ", "real_estate_property"),
        ("Làm video đi xuyên căn hộ để đăng bán", "architecture_walkthrough"),
        ("Từ mặt bằng này dựng phối cảnh", "floorplan_visualization"),
        ("Thiết kế quán cà phê", "commercial_space"),
        ("Thiết kế sân vườn biệt thự", "landscape_garden"),
    ],
)
def test_arch1_router_profiles(text: str, expected: str) -> None:
    route = architecture_profile_router.route_architecture_profile({"user_text": text})
    assert route["profile_id"] == expected
    assert route["provider_called"] is False
    assert route["job_created"] is False
    assert route["outbox_created"] is False
    assert route["xu_charged"] == 0


def test_arch1_explicit_profile_wins() -> None:
    route = architecture_profile_router.route_architecture_profile({
        "user_text": "Thiết kế sân vườn", "explicit_profile": "interior_design",
    })
    assert route["profile_id"] == "interior_design"
    assert route["confidence"] == 1.0


def test_arch1_ambiguous_request_asks_one_clarification() -> None:
    route = architecture_profile_router.route_architecture_profile({"user_text": "Làm đẹp hơn"})
    assert route["confidence"] < 0.5
    assert route["clarification_question"].count("?") == 1


def test_arch1_questions_skip_known_values_and_one_at_a_time() -> None:
    answers = {"space_type": "Phòng khách", "dimensions": "Chưa biết"}
    item = architecture_profile_router.next_missing_question("interior_design", answers)
    assert item == {"field": "style", "question": "Anh/chị muốn phong cách nội thất nào?"}
    assert isinstance(item["question"], str)


def test_arch1_requested_video_copy_routes_to_video_and_string_lists_remain_whole() -> None:
    route = architecture_profile_router.route_architecture_profile({
        "explicit_profile": "real_estate_property",
        "user_text": "Giới thiệu căn hộ đang đăng bán",
        "requested_output": "Video walkthrough",
        "preserve_requirements": "Giữ nguyên cửa và cửa sổ",
        "materials": "gỗ sồi sáng",
        "duration": "32 giây",
    })
    assert route["recommended_output"] == "video"
    assert route["preserve_constraints"] == ["Giữ nguyên cửa và cửa sổ"]
    assert "gỗ sồi sáng" in route["professional_image_prompt"]
    assert route["scene_plan_summary"]["total_duration_seconds"] == 32


def test_arch1_short_answer_and_exact_question_stack_source_contract() -> None:
    source = BOT_SOURCE.split("async def handle_architecture_profile_pending_text", 1)[1].split("async def handle_video_profile_studio_pending_text", 1)[0]
    assert 'answers[field_name] = text[:1000]' in source
    assert 'history.append(field_name)' in source
    assert 'previous = history.pop()' in source
    assert 'state["current_field"] = previous' in source


@pytest.mark.parametrize(
    ("asset_type", "file_name", "mime"),
    [
        ("interior_photo", "room.jpg", "image/jpeg"),
        ("floorplan", "plan.pdf", "application/pdf"),
        ("walkthrough_reference", "tour.mov", "video/quicktime"),
    ],
)
def test_arch1_reference_upload_types(asset_type: str, file_name: str, mime: str) -> None:
    result = architecture_profile_status.validate_reference_asset(
        {"file_id": "telegram-file", "file_name": file_name, "mime_type": mime, "file_size": 1024},
        asset_type=asset_type,
    )
    assert result["ok"] is True
    assert result["provider_called"] is False
    assert result["hidden_analysis_called"] is False
    assert "path" not in result["asset"]


def test_arch1_invalid_asset_and_path_traversal_blocked() -> None:
    invalid = architecture_profile_status.validate_reference_asset(
        {"file_id": "x", "file_name": "malware.exe", "mime_type": "application/octet-stream", "file_size": 100},
        asset_type="interior_photo",
    )
    traversal = architecture_profile_status.validate_reference_asset(
        {"file_id": "x", "file_name": "../room.jpg", "mime_type": "image/jpeg", "file_size": 100},
        asset_type="interior_photo",
    )
    assert invalid["ok"] is False
    assert traversal == {"ok": False, "reason": "path_traversal_blocked", "provider_called": False}


def test_arch1_geometry_preservation_defaults() -> None:
    assert "Giữ nguyên hình học" in default_preservation("space_renovation", True)
    floor = default_preservation("floorplan_visualization")
    assert any("kích thước" in item for item in floor)
    assert any("Không tự thêm phòng" in item for item in floor)
    realestate = default_preservation("real_estate_property")
    assert any("quy mô thật" in item for item in realestate)
    assert any("không bịa góc nhìn" in item.lower() for item in realestate)


def test_arch1_image_prompt_professional_sections_and_no_invented_dimensions() -> None:
    result = build_architecture_image_prompt({
        "profile_id": "interior_design",
        "project_type": "Căn hộ",
        "space_type": "Phòng khách",
        "user_text": "Thiết kế phòng khách Japandi",
        "style": "Japandi",
        "materials": ["gỗ sồi sáng", "travertine"],
        "preserve_requirements": ["Giữ nguyên cửa sổ"],
    })
    assert result["ok"] is True
    assert "Phòng khách" in result["prompt"] or "Căn hộ" in result["prompt"]
    assert "Japandi" in result["prompt"]
    assert "gỗ sồi sáng" in result["prompt"]
    assert "Giữ nguyên cửa sổ" in result["prompt"]
    assert "Do not invent dimensions" in result["prompt"]
    assert set(IMAGE_NEGATIVE_PROMPT) <= set(result["negative_prompt"].split(", "))
    assert len(result["sections"]) == 16


def test_arch1_video_prompt_camera_preservation_consistency_and_negative() -> None:
    result = build_architecture_video_prompt({
        "profile_id": "architecture_walkthrough",
        "user_text": "Walkthrough căn hộ",
        "room_order": ["Lối vào", "Phòng khách", "Bếp", "Ban công"],
        "preserve_requirements": ["Giữ thứ tự phòng", "Giữ cửa/cửa sổ"],
        "duration": 32,
        "aspect_ratio": "9:16",
    })
    assert result["ok"] is True
    assert "Camera path" in result["prompt"]
    assert "Giữ thứ tự phòng" in result["prompt"]
    assert "carry the previous scene end state" in result["prompt"]
    assert set(VIDEO_NEGATIVE_PROMPT) <= set(result["negative_prompt"].split(", "))
    assert "Room-to-room continuity" in CAMERA_PRESETS


def test_arch1_before_after_transition_prompt() -> None:
    result = build_architecture_video_prompt({"profile_id": "space_renovation", "user_text": "Video trước và sau cải tạo", "duration": 24})
    assert "before/after match-cut reveal" in result["prompt"]


@pytest.mark.parametrize("profile_id", ["architecture_walkthrough", "interior_design", "architecture_exterior", "floorplan_visualization"])
def test_arch1_scene_duration_exact_coverage_and_no_teleport(profile_id: str) -> None:
    plan = build_architecture_scene_plan({"profile_id": profile_id, "duration": 41, "scene_count": 5})
    assert plan["scene_count"] == 5
    assert sum(item["duration_seconds"] for item in plan["shots"]) == 41
    assert plan["exact_duration_coverage"] is True
    assert plan["camera_teleport_detected"] is False


def test_arch1_walkthrough_room_order_consistent() -> None:
    order = ["Lối vào", "Phòng khách", "Bếp", "Ban công"]
    plan = build_architecture_scene_plan({"profile_id": "architecture_walkthrough", "room_order": order, "duration": 32})
    assert [item["space"] for item in plan["shots"]] == order


def test_arch1_realestate_truth_guards_and_labels() -> None:
    current = architecture_profile_router.route_architecture_profile({
        "explicit_profile": "real_estate_property", "user_text": "Làm ảnh đăng bán căn hộ", "truth_mode": "giữ hiện trạng",
    })
    concept = architecture_profile_router.route_architecture_profile({
        "explicit_profile": "real_estate_property", "user_text": "Làm ảnh đăng bán căn hộ", "truth_mode": "phối cảnh ý tưởng cải tạo",
    })
    assert current["real_estate_truth_label"] == "Chỉnh ảnh hiện trạng"
    assert concept["real_estate_truth_label"] == "Phối cảnh ý tưởng cải tạo"
    combined = " ".join(current["preserve_constraints"]).lower() + " " + current["professional_image_prompt"].lower()
    assert "hình học" in combined
    assert "tiện ích" in combined or "amenities" in combined
    assert "do not invent" in current["professional_image_prompt"].lower()


def test_arch1_destination_handoff_prefill_source_contract() -> None:
    source = _architecture_source()
    handoff_source = BOT_SOURCE.split('if action == "handoff_video":', 1)[1].split(
        "async def cmd_architecture_profile_status", 1
    )[0]
    assert 'prompt_source="architecture_profile"' in source
    assert 'architecture_profile_id=' in source
    assert 'architecture_reference_assets=' in source
    assert '"architecture_video_prompt"' in source
    assert '"architecture_scene_plan"' in source
    assert '"return_to": "archprofile|output"' in source
    assert 'callback_data="archprofile|handoff_video"' in source
    assert "return await start_public_video_scene2_step(" in handoff_source
    assert 'callback_data="archprofile|output"' in source
    assert 'parent_callback_override=parent_callback if architecture_handoff else ""' in BOT_SOURCE
    assert '"archprofile|output"\n            if architecture_handoff' in BOT_SOURCE


def test_arch1_public_preview_clean_and_truthful() -> None:
    source = _architecture_source()
    preview = source.split("def architecture_preview_text", 1)[1].split("def architecture_preview_keyboard", 1)[0]
    for forbidden in ("ShopAIKey", "Key4U", "result_url", "provider_task_id", "API key", "file path"):
        assert forbidden not in preview
    assert "Hệ thống chưa tạo file" in preview
    assert "chưa trừ Xu" in preview
    assert "Kế hoạch cảnh" in preview
    assert "Yêu cầu cần giữ" in preview


def test_arch1_session_draft_user_isolation_resume_delete() -> None:
    architecture_profile_status.delete_draft(1001)
    architecture_profile_status.delete_draft(1002)
    saved = architecture_profile_status.save_draft(1001, {"profile_id": "interior_design", "answers": {"style": "Japandi"}})
    assert saved["provider_task_created"] is False
    assert architecture_profile_status.load_draft(1001)["answers"]["style"] == "Japandi"
    assert architecture_profile_status.load_draft(1002) == {}
    assert architecture_profile_status.delete_draft(1001) is True
    assert architecture_profile_status.load_draft(1001) == {}


def test_arch1_status_and_debug_truth_mask_paths() -> None:
    status = architecture_profile_status.status_payload(profile_count=8, profile_json_loaded=True)
    assert status["architecture_profile_count"] == 8
    assert status["provider_calls_from_profile_studio"] is False
    assert status["xu_charged_from_profile_studio"] == 0
    assert status["paths_exposed"] is False
    debug = architecture_profile_status.debug_payload()
    assert debug["provider_task_created_by_profile_studio"] is False
    assert debug["charge_created_by_profile_studio"] is False
    assert debug["private_path_exposed"] is False
    assert 'CommandHandler("architecture_profile_status", cmd_architecture_profile_status)' in BOT_SOURCE
    assert 'CommandHandler("architecture_profile_debug", cmd_architecture_profile_debug)' in BOT_SOURCE


def test_arch1_debug_reads_nested_saved_route_and_handoff_truth() -> None:
    architecture_profile_status.delete_draft(2001)
    architecture_profile_status.save_draft(2001, {
        "profile_id": "architecture_walkthrough",
        "destination_handoff_status": "video_prefill_ready",
        "draft": {
            "profile_id": "architecture_walkthrough",
            "confidence": 1.0,
            "professional_video_prompt": "walkthrough prompt",
            "negative_prompt": "camera jitter",
            "scene_plan": [{"index": 1}],
            "recommended_output": "video",
        },
    })
    debug = architecture_profile_status.debug_payload(2001)
    assert debug["profile_id"] == "architecture_walkthrough"
    assert debug["prompt_present"] is True
    assert debug["scene_count"] == 1
    assert debug["destination_handoff_status"] == "video_prefill_ready"
    architecture_profile_status.delete_draft(2001)


def test_arch1_profile_preview_free_destination_owns_pricing() -> None:
    route = architecture_profile_router.route_architecture_profile({"explicit_profile": "interior_design", "user_text": "Phòng khách Japandi"})
    assert route["preview_price_xu"] == 0
    assert route["xu_charged"] == 0
    source = _architecture_source()
    assert "video_b14_invoice_for_session" not in source
    assert "create_invoice" not in source
    assert "PAYOS" not in source.upper()


def test_arch1_scope_lock() -> None:
    changed = _git_lines("diff", "--name-only", "origin/main")
    untracked = {
        item for item in _git_lines("ls-files", "--others", "--exclude-standard")
        if not item.startswith("pytest-baseline-r1/")
    }
    touched = changed | untracked
    allowed_runtime = {
        "bot.py", "services/profile_router.py",
        "services/architecture_profile_router.py",
        "services/architecture_prompt_builder.py",
        "services/architecture_video_prompt_builder.py",
        "services/architecture_scene_planner.py",
        "services/architecture_profile_status.py",
    }
    allowed_tests = {
        TEST_FILE,
        "tests/aiedit1_scope_guard.py",
        "tests/test_p0_cost2_provider_quota_cycle_reset_alert_baseline.py",
        "tests/test_p0_cskh1_telegram_business_auto_support_bot.py",
        "tests/test_p0_video_knowledge1_profile_router_and_studio_menu.py",
    }
    if SCENE2_TEST_FILE in touched:
        allowed_tests.update(
            {
                SCENE2_TEST_FILE,
                SCENE2_UIFLOW_TEST_FILE,
                SCENE2_UIFLOW_LOCK_TEST_FILE,
                SCENE2_DURATION_TEST_FILE,
            }
        )
    allowed_profiles = {
        "knowledge/profiles/architecture_exterior.json",
        "knowledge/profiles/interior_design.json",
        "knowledge/profiles/space_renovation.json",
        "knowledge/profiles/real_estate_property.json",
        "knowledge/profiles/architecture_walkthrough.json",
        "knowledge/profiles/floorplan_visualization.json",
        "knowledge/profiles/commercial_space.json",
        "knowledge/profiles/landscape_garden.json",
    }
    for path in touched:
        assert path in allowed_runtime or path in allowed_tests or path in allowed_profiles, path
    forbidden = (
        "music", "suno", "subdub", "voice", "payos", "wallet", "payment",
        "video_project_queue", "video_provider_router", "video_real_render_connector",
        "remote_worker", "local_worker", "webhook",
    )
    runtime = {path.lower() for path in touched if not path.startswith("tests/") and not path.startswith("knowledge/")}
    assert not any(token in path for token in forbidden for path in runtime)


def test_arch1_old_scope_guards_are_aligned_narrowly() -> None:
    from tests.aiedit1_scope_guard import arch1_scope_active

    touched = _git_lines("diff", "--name-only", "origin/main") | {
        item for item in _git_lines("ls-files", "--others", "--exclude-standard")
        if not item.startswith("pytest-baseline-r1/")
    }
    if SCENE2_TEST_FILE in touched:
        assert arch1_scope_active(touched) is False
    else:
        assert arch1_scope_active(touched) is True
    assert arch1_scope_active(touched | {"services/video_provider_router.py"}) is False


def test_arch1_no_real_provider_calls() -> None:
    for module_path in (
        "services/architecture_profile_router.py",
        "services/architecture_prompt_builder.py",
        "services/architecture_video_prompt_builder.py",
        "services/architecture_scene_planner.py",
        "services/architecture_profile_status.py",
    ):
        source = (REPO_ROOT / module_path).read_text(encoding="utf-8")
        for forbidden in ("httpx", "requests.", "OpenAI(", "genai.", "ShopAIKey", "Key4U", "provider.submit"):
            assert forbidden not in source


def test_arch1_media_hook_is_safe_without_session_context() -> None:
    source = _architecture_source()
    assert 'user_data = getattr(context, "user_data", None)' in source
    assert 'state = dict(user_data.get(ARCHITECTURE_PROFILE_SESSION_KEY) or {}) if isinstance(user_data, dict) else {}' in source
