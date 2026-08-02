from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from services import video_flow6, video_tail9


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    pattern = re.compile(rf"^(?:async )?def {re.escape(name)}\(", re.MULTILINE)
    match = pattern.search(BOT_SOURCE)
    assert match, f"missing function: {name}"
    next_match = re.search(r"\n(?:async )?def [A-Za-z_]", BOT_SOURCE[match.end() :])
    end = match.end() + next_match.start() if next_match else len(BOT_SOURCE)
    return BOT_SOURCE[match.start() : end]


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _compile_contract(state: dict, product_type: str) -> dict:
    namespace = {
        "safe_int": _safe_int,
        "video_tail9": video_tail9,
        "video_flow6": video_flow6,
        "video_selfshot2": SimpleNamespace(PRODUCT_ID="self_shot_scene_change"),
        "video_selfshot3": SimpleNamespace(PRODUCT_ID="self_shot_cinematic_transform"),
    }
    exec(_function_source("video_tail12_compile_content_contract"), namespace)
    return namespace["video_tail12_compile_content_contract"](state, product_type=product_type)


def test_idea_handoff_compiles_one_complete_tail_contract() -> None:
    compiled = _compile_contract(
        {
            "content_source": "idea_catalog",
            "catalog_idea_id": "idea-proof-before-after",
            "idea_title": "Trước và sau có bằng chứng",
            "selected_prompt": "Kể mạch rõ, các cảnh nối tự nhiên.",
            "per_scene_content": [
                {"scene_number": 1, "goal": "Mở vấn đề"},
                {"scene_number": 2, "goal": "Khép bằng kết quả"},
            ],
            "scene_count": 2,
            "aspect_ratio": "16:9",
            "idea_parent_flow_owner": "scene3",
            "idea_parent_session_id": "parent-idea-session",
        },
        "video_ai_realistic",
    )

    assert compiled["product_type"] == "video_ai_real"
    assert compiled["content_source"] == "idea_catalog"
    assert compiled["content_mode"] == "suggestions"
    assert compiled["canonical_content_mode"] == "idea_catalog"
    assert compiled["content_choice"] == {
        "id": "idea-proof-before-after",
        "title": "Trước và sau có bằng chứng",
    }
    assert compiled["scene_count"] == 2
    assert compiled["aspect_ratio"] == "16:9"
    assert compiled["selected_prompt"]
    assert compiled["selected_prompt_revision"] >= 1
    assert compiled["plan_status"] == "ready"
    assert compiled["flow_owner"] == "scene3"
    assert compiled["parent_session_id"] == "parent-idea-session"


def test_unified_summary_is_the_only_final_check_before_quality() -> None:
    scene_review = _function_source("video_scene3_full_review_keyboard")
    tail_review = _function_source("video_tail9_review_keyboard")
    summary = _function_source("video_tail9_summary_keyboard")
    edit_review = _function_source("video_tail9_video_edit_review_keyboard")

    assert "video_tail|quality|open" not in scene_review
    assert "video_tail|quality|open" not in tail_review
    assert "video_tail|quality|open" not in summary
    assert '[("⭐ Hoàn thiện video", "video_tail|quality|open")]' not in summary
    assert "video_tail|quality|open" not in edit_review
    assert "return video_tail9_summary_keyboard(tail)" in tail_review
    assert "video_tail|review|logo" in scene_review
    assert "videoedit|overlay" in edit_review
    assert "video_tail|review|summary" in scene_review
    assert "videoedit|review" in edit_review
    assert "video_tail|" not in edit_review
    assert "video_tail|summary|logo" in summary
    assert "video_tail|summary|audio" in summary
    assert "video_tail|summary|continue" in summary
    assert '("⬅️ Quay lại", "video_tail|summary|back")' in summary


def test_completed_legacy_ai_plan_restores_the_missing_content_contract() -> None:
    compiled = _compile_contract(
        {
            "source_product_id": "video_ai_realistic",
            "subject": "Giới thiệu sản phẩm theo mạch rõ ràng",
            "selected_prompt": "Camera nối tự nhiên giữa các cảnh.",
            "plan": {
                "scenes": [
                    {"title": "Mở đầu", "goal": "Nêu vấn đề"},
                    {"title": "Kết thúc", "goal": "Khép bằng kết quả"},
                ],
            },
            "scene_count": 2,
            "aspect_ratio": "9:16",
        },
        "video_ai_realistic",
    )

    assert compiled["content_mode"] == "suggestions"
    assert compiled["content_source"] == "content_profiles"
    assert compiled["primary_profile_key"]
    assert compiled["content_choice"]
    assert compiled["plan_status"] == "ready"


def test_completed_non_ai_scene_plan_restores_the_missing_content_contract() -> None:
    compiled = _compile_contract(
        {
            "source_product_id": "video_trend",
            "selected_prompt": "Giữ mạch trend rõ ràng giữa các cảnh.",
            "plan": {
                "scenes": [
                    {"title": "Mở trend", "goal": "Tạo điểm vào"},
                    {"title": "Khép trend", "goal": "Đưa kết quả"},
                ],
            },
            "scene_count": 2,
            "aspect_ratio": "9:16",
        },
        "video_trend",
    )

    assert compiled["content_mode"] == "suggestions"
    assert compiled["content_source"] == "content_profiles"
    assert compiled["content_choice"]
    assert compiled["plan_status"] == "ready"


def test_last_green_scene_prompts_restore_the_shared_tail_sequence() -> None:
    compiled = _compile_contract(
        {
            "source_product_id": "video_ai_realistic",
            "subject": "Giới thiệu sản phẩm trong một cảnh",
            "plan": {
                "scenes": [
                    {"scene_index": 1, "title": "Mở đầu", "goal": "Giới thiệu sản phẩm"},
                ],
            },
            "video_prompt_versions": {
                "1": {
                    "active_version": 2,
                    "approved": True,
                    "versions": [
                        {"version": 1, "prompt": "Prompt cũ"},
                        {
                            "version": 2,
                            "prompt": "Cảnh 1 giới thiệu sản phẩm, camera tiến nhẹ và kết thúc trọn vẹn.",
                            "provider_prompt": "Scene 1 product reveal with a gentle camera push-in.",
                        },
                    ],
                },
            },
            "scene_count": 1,
            "aspect_ratio": "9:16",
        },
        "video_ai_realistic",
    )

    assert compiled["selected_prompt"] == (
        "Cảnh 1 giới thiệu sản phẩm, camera tiến nhẹ và kết thúc trọn vẹn."
    )

    tail = video_tail9.new_state(
        product_type="video_ai_real",
        session_id="last-green-tail",
        scene_count=1,
        ratio="9:16",
    )
    tail = video_tail9.apply_content_contract(tail, compiled)
    assert video_tail9.next_required_screen(tail) == "logo"

    tail = video_tail9.mark_branding_skipped(tail)
    assert video_tail9.next_required_screen(tail) == "summary"

    tail = video_tail9.prepare_summary(tail)
    assert tail["summary_status"] == "ready"
    assert tail["review_status"] == "ready"
    assert video_tail9.next_required_screen(tail) == ""


def test_direct_summary_callback_keeps_summary_as_its_own_owner() -> None:
    callback = _function_source("handle_video_tail_callback")
    blocker = _function_source("video_tail9_public_blocker_keyboard")
    quality = _function_source("video_tail9_quality_keyboard")

    assert 'action in {"open", "summary", "review"}' in callback
    assert 'video_tail9.prepare_summary(tail)' in callback
    assert 'if section == "summary":' in callback
    assert 'video_tail9_render(query, uid, context, "summary")' in callback
    assert "video_tail|summary|open" in blocker
    assert "video_tail|review|summary" not in blocker
    assert "video_tail|quality|back" in quality
    assert "video_tail|summary|open" not in quality
    assert "video_tail|review|summary" in BOT_SOURCE


def test_canonical_tail_reuses_planning_audio_and_keeps_nine_brand_positions() -> None:
    audio = _function_source("video_scene3_audio_plan_keyboard")
    logo = _function_source("video_tail9_logo_keyboard")
    positions = _function_source("video_tail9_position_keyboard")
    summary = _function_source("video_tail9_summary_keyboard")
    quality = _function_source("video_tail9_quality_keyboard")

    assert '"vprofile|audio_done"' in audio
    assert '"vprofile|audio_skip"' in audio
    assert "*video_scene3_nav_rows()" in audio
    assert '"vprofile|back"' in _function_source("video_scene3_nav_rows")
    assert '"video_tail|logo|done"' in logo
    assert '"video_tail|logo|skip"' in logo
    assert '"video_tail|review|prompts"' in logo
    for position in (
        "top_left", "top_center", "top_right",
        "center_left", "center", "center_right",
        "bottom_left", "bottom_center", "bottom_right",
    ):
        assert f'"{position}"' in positions
    assert '"video_tail|summary|logo"' in summary
    assert '"video_tail|summary|continue"' in summary
    assert '"video_tail|quality|open"' not in summary
    assert '"video_tail|quality|back"' in quality


def test_legacy_review_audio_and_audio_exit_use_the_corrected_tail_order() -> None:
    callback = _function_source("handle_video_tail_callback")
    legacy_review = _function_source("handle_video_profile_studio_callback")

    audio_start = callback.index('if section == "audio":')
    logo_start = callback.index('if section == "logo":', audio_start)
    audio = callback[audio_start:logo_start]
    legacy_start = legacy_review.index('if action == "review_audio":')
    legacy_end = legacy_review.index('if action == "review_post":', legacy_start)
    legacy_audio = legacy_review[legacy_start:legacy_end]

    assert audio.count('video_tail9_render(query, uid, context, "summary")') == 1
    assert "video_tail9_open_planning_audio" in audio
    assert 'video_tail9_render(query, uid, context, "quality")' not in audio
    assert 'action in {"back", "done", "skip"}' in audio
    assert "video_tail9_open_planning_audio" in legacy_audio
    assert 'video_tail9_render(query, uid, context, "audio")' not in legacy_audio


def test_idea_handoff_preserves_parent_ratio_and_public_recovery_copy() -> None:
    dynamic = _function_source("video_idea_dynamic_scene3_state")
    prompt_handler = _function_source("handle_video_idea_prompt_callback")

    assert "selected_ratio = str(" in dynamic
    assert '"ratio": selected_ratio' in dynamic
    assert '"aspect_ratio": selected_ratio' in dynamic
    assert '"aspect_ratio": plan["recommended_aspect_ratio"]' not in dynamic
    assert "Phiên chọn prompt đã hết hạn" not in prompt_handler
    assert "Thiếu flow cha của ý tưởng này" not in prompt_handler
    assert "Chưa thể tiếp tục" in prompt_handler


def test_logo_and_watermark_must_choose_a_position_before_save() -> None:
    callback = _function_source("handle_video_tail_callback")
    pending_text = _function_source("handle_video_tail9_pending_text")
    pending_media = _function_source("handle_video_product_pending_media")

    assert "video_tail9_position_text(argument)" in callback
    assert "not config.get(\"asset_file_id\")" in callback
    assert "not config.get(\"text\")" in callback
    assert 'video_tail9_position_text("watermark")' in pending_text
    assert "video_tail9_position_text(\"logo\")" in pending_media
    assert "video_tail9_position_keyboard(\"logo\")" in pending_media


def test_preconfirm_tail_stays_provider_and_charge_free() -> None:
    callback = _function_source("handle_video_tail_callback")
    contract = video_tail9.package_compatibility(
        "storyboard_to_video",
        scene_count=2,
        ratio="9:16",
        quality_tier_id=300,
        asset_ready=True,
        input_valid=True,
    )

    assert contract["side_effects"] == {
        "job": 0,
        "outbox": 0,
        "provider_calls": 0,
        "generated_files": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }
    before_confirm = callback[: callback.index('if section == "confirm":')]
    for forbidden in ("provider.submit", "create_product_video_job", "wallet_debit", "charge_xu"):
        assert forbidden not in before_confirm
