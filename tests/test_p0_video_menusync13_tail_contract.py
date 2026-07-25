from __future__ import annotations

from pathlib import Path

import pytest

from services import video_tail9


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _between(start: str, end: str) -> str:
    left = BOT_SOURCE.index(start)
    right = BOT_SOURCE.index(end, left + len(start))
    return BOT_SOURCE[left:right]


@pytest.mark.parametrize(
    "product_type",
    (
        "video_ai_real",
        "video_trend",
        "script_image_video",
        "storyboard_prompt",
        "self_shot_scene_change",
        "self_shot_cinematic_transform",
        "multi_scene_film",
    ),
)
def test_each_shared_tail_product_keeps_completed_content_contract(product_type: str) -> None:
    state = video_tail9.new_state(
        product_type=product_type,
        session_id=f"menusync13-{product_type}",
        scene_count=2,
    )
    state = video_tail9.apply_content_contract(
        state,
        {
            "content_source": "idea_catalog",
            "canonical_content_mode": "idea_catalog",
            "selected_prompt_text": "Prompt đã chọn cho toàn bộ cảnh.",
            "selected_prompt_revision": 2,
            "per_scene_content": [{"scene": 1}, {"scene": 2}],
            "plan_status": "ready",
        },
    )

    summary = video_tail9.prepare_summary(state)

    assert summary["summary_status"] == "ready"
    assert summary["content_source"] == "idea_catalog"
    assert summary["selected_prompt"]
    assert summary["audio_status"] == "not_configured"
    assert summary["logo_status"] == "not_configured"
    assert summary["watermark_status"] == "not_configured"


def test_optional_branding_skip_clears_legacy_positions() -> None:
    state = video_tail9.new_state(product_type="video_ai_real", session_id="branding-skip")
    state["logo_config"] = {"enabled": False, "asset_file_id": "", "position": "bottom_right"}
    state["watermark_config"] = {"enabled": False, "text": "", "position": "bottom_right"}

    skipped = video_tail9.mark_branding_skipped(state)

    assert skipped["logo_status"] == "skipped"
    assert skipped["watermark_status"] == "skipped"
    assert skipped["logo_config"]["position"] == ""
    assert skipped["watermark_config"]["position"] == ""


def test_tail_routes_keep_summary_direct_and_back_to_review() -> None:
    handler = _between(
        "async def handle_video_tail_callback",
        "async def handle_video_tail9_pending_text",
    )
    logo_keyboard = _between(
        "def video_tail9_logo_keyboard",
        "def video_tail9_position_text",
    )
    summary_keyboard = _between(
        "def video_tail9_summary_keyboard",
        "def video_tail9_public_blocker_text",
    )

    review = handler[handler.index('if section == "review":'):handler.index('if section == "summary":')]
    summary = handler[handler.index('if section == "summary":'):handler.index('if section == "audio":')]

    assert 'return await video_tail9_render(query, uid, context, "audio")' not in review
    assert 'if action == "summary":\n            tail = video_tail9.prepare_summary(tail)' in review
    assert 'if action == "back":\n            return await video_tail9_render(query, uid, context, "review")' in summary
    assert '[("⬅️ Quay lại", "video_tail|review|open"), ("🏠 Menu chính", "menu|main")]' in logo_keyboard
    assert '[("⬅️ Quay lại", "video_tail|review|open"), ("🏠 Menu chính", "menu|main")]' in summary_keyboard
    context = _between("def video_tail9_context", "def save_video_tail9_state")
    assert "video_tail9.apply_content_contract(tail, host)" in context


def test_tail_branding_flow_has_one_explicit_position_step_per_asset() -> None:
    handler = _between(
        "async def handle_video_tail_callback",
        "async def handle_video_tail9_pending_text",
    )

    assert '"awaiting_video_tail9_logo"' in handler
    assert '"video_tail9_watermark_input"' in handler
    assert 'video_tail9_position_keyboard("logo")' in BOT_SOURCE
    assert 'video_tail9_position_keyboard("watermark")' in BOT_SOURCE
    assert 'video_tail9_brand_confirm_keyboard(target)' in BOT_SOURCE
    assert 'tail = video_tail9.mark_branding_skipped(tail)' in handler
