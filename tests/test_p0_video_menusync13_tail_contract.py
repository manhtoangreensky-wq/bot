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

    pending = video_tail9.prepare_summary(state)
    assert pending["summary_status"] == "not_ready"

    summary = video_tail9.mark_branding_skipped(state)
    summary = video_tail9.mark_audio_complete(summary, skipped=True)
    summary = video_tail9.prepare_summary(summary)

    assert summary["summary_status"] == "ready"
    assert summary["content_source"] == "idea_catalog"
    assert summary["selected_prompt"]
    assert summary["audio_status"] == "skipped"
    assert summary["logo_status"] == "skipped"
    assert summary["watermark_status"] == "skipped"


def test_optional_branding_skip_clears_legacy_positions() -> None:
    state = video_tail9.new_state(product_type="video_ai_real", session_id="branding-skip")
    state["logo_config"] = {"enabled": False, "asset_file_id": "", "position": "bottom_right"}
    state["watermark_config"] = {"enabled": False, "text": "", "position": "bottom_right"}

    skipped = video_tail9.mark_branding_skipped(state)

    assert skipped["logo_status"] == "skipped"
    assert skipped["watermark_status"] == "skipped"
    assert skipped["logo_config"]["position"] == ""
    assert skipped["watermark_config"]["position"] == ""


def test_tail_routes_keep_the_exact_logo_audio_unified_summary_back_stack() -> None:
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

    assert 'action in {"open", "summary", "review"}' in review
    assert 'return await video_tail9_render(query, uid, context, "summary")' in review
    renderer = _between("async def video_tail9_render", "def video_tail9_callback_guard")
    assert "video_tail9.next_required_screen(tail)" in renderer
    assert 'if action == "continue":' in summary
    assert 'return await video_tail9_render(query, uid, context, "quality")' in summary
    assert 'if action == "audio":' in summary
    assert 'if action == "back":' in summary
    assert "video_tail9_open_planning_audio" in summary
    assert 'return await video_tail9_render(query, uid, context, "audio")' not in summary
    assert 'else "video_tail|review|prompts"' not in logo_keyboard
    assert 'back_callback = "video_tail|review|prompts"' in logo_keyboard
    assert '[("⬅️ Quay lại", "video_tail|summary|back"), ("🏠 Menu chính", "menu|main")]' in summary_keyboard
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
