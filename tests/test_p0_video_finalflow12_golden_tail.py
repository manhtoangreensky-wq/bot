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


def test_review_requires_summary_before_quality_for_all_tail_owners() -> None:
    scene_review = _function_source("video_scene3_full_review_keyboard")
    tail_review = _function_source("video_tail9_review_keyboard")
    summary = _function_source("video_tail9_summary_keyboard")
    edit_review = _function_source("video_tail9_video_edit_review_keyboard")

    assert "video_tail|quality|open" not in scene_review
    assert "video_tail|quality|open" not in tail_review
    assert "video_tail|quality|open" in summary
    assert '[("⭐ Hoàn thiện video", "video_tail|quality|open")]' not in summary
    assert "video_tail|quality|open" not in edit_review
    assert "video_tail|review|summary" in edit_review


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
