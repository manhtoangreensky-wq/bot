from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    pattern = re.compile(rf"^(?:async )?def {re.escape(name)}\(", re.MULTILINE)
    match = pattern.search(BOT_SOURCE)
    assert match, f"missing function: {name}"
    next_match = re.search(r"\n(?:async )?def [A-Za-z_]", BOT_SOURCE[match.end() :])
    end = match.end() + next_match.start() if next_match else len(BOT_SOURCE)
    return BOT_SOURCE[match.start() : end]


def test_trend_prompt_completion_opens_shared_addon_without_legacy_review() -> None:
    callback = _function_source("handle_video_profile_studio_callback")
    start = callback.index('if action == "video_prompt_done":')
    end = callback.index('if action == "review_image_prompts":', start)
    branch = callback[start:end]

    assert 'video_flow6_product_id(state) == "video_trend"' in branch
    assert 'video_tail9_render(query, uid, context, "addon")' in branch


def test_trend_shared_review_audio_returns_to_shared_addon() -> None:
    callback = _function_source("handle_video_tail_callback")
    start = callback.index('if section == "review":')
    end = callback.index('if section == "summary":', start)
    review = callback[start:end]

    assert 'if action == "cast_audio" and trend_review:' in review
    assert 'video_tail9_render(query, uid, context, "addon")' in review


def test_trend_addon_back_returns_to_prompts_without_legacy_review() -> None:
    callback = _function_source("handle_video_tail_callback")
    start = callback.index('if action == "back" and trend_tail:')
    end = callback.index('if action == "back" and storyboard_tail:', start)
    addon_back = callback[start:end]

    assert '"video_prompts"' in addon_back
    assert 'video_tail_return_to="addon"' in addon_back


def test_old_trend_review_audio_callback_cannot_reopen_legacy_audio_plan() -> None:
    callback = _function_source("handle_video_profile_studio_callback")
    start = callback.index('if action == "review_audio":')
    end = callback.index('if action == "review_post":', start)
    review_audio = callback[start:end]

    assert 'video_flow6_product_id(state) == "video_trend"' in review_audio
    assert 'video_tail9_render(query, uid, context, "addon")' in review_audio
    assert "video_tail9_open_planning_audio" in review_audio
