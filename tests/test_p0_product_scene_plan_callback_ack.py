from __future__ import annotations

from pathlib import Path


BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"


def test_scene_plan_auto_acknowledges_callback_before_gemini_enhancement() -> None:
    source = BOT_PATH.read_text(encoding="utf-8")
    branch_start = source.index('        elif action == "scene_plan_auto":')
    branch_end = source.index('        elif action == "plan_scene"', branch_start)
    branch_source = source[branch_start:branch_end]
    assert branch_source.index("await query.answer()") < branch_source.index(
        "video_uiflow3_ai_enhance_scenes"
    )

    handler_start = source.index("async def handle_video_uiflow3_callback")
    handler_end = source.index("async def handle_video_uiflow3_pending_text", handler_start)
    handler_source = source[handler_start:handler_end]
    assert "if not callback_answered:" in handler_source
