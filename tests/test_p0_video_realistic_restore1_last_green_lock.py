from __future__ import annotations

import re
from pathlib import Path

from services import video_flow6


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    marker = f"def {name}("
    start = BOT_SOURCE.index(marker)
    next_def = re.search(r"\n(?:async )?def [A-Za-z_]", BOT_SOURCE[start + 1 :])
    end = start + 1 + next_def.start() if next_def else len(BOT_SOURCE)
    return BOT_SOURCE[start:end]


def _restore(state: dict) -> dict:
    namespace = {"video_flow6": video_flow6}
    exec(_function_source("video_ai_realistic_restore_legacy_content_mode"), namespace)
    return namespace["video_ai_realistic_restore_legacy_content_mode"](state)


def _completed_profile_state() -> dict:
    choice = {
        "id": "review_product_story",
        "title": "Mở hộp và hé lộ sản phẩm",
        "concept": "Giới thiệu lợi ích sản phẩm qua hai cảnh liên tiếp.",
    }
    return {
        "source_product_id": "video_ai_real",
        "product_type": "video_ai_real",
        "step": "full_review",
        "scene_count": 2,
        "aspect_ratio": "9:16",
        "ai_input_type": "prompt_video",
        "content_source": "profiles",
        "source_fields": {
            "ai_input_type": "prompt_video",
            "content_source": "profiles",
        },
        "primary_profile_key": "review_demo",
        "content_choice": choice,
        "selected_suggestion": choice,
    }


def test_completed_pre_flow6_profile_plan_regains_only_the_missing_mode() -> None:
    restored = _restore(_completed_profile_state())

    assert restored["content_mode"] == "suggestions"
    assert restored["content_source"] == "profiles"
    assert restored["primary_profile_key"] == "review_demo"
    assert restored["content_choice"]["id"] == "review_product_story"

    result = video_flow6.preflight(
        video_flow6.context_from_scene_state(restored),
        package_available=True,
        engine_ready=True,
        worker_ready=True,
        capability_ready=True,
    )
    assert result["ok"] is True
    assert "content_mode_missing" not in result["blockers"]
    assert result["side_effects"] == {
        "job": 0,
        "outbox": 0,
        "invoice": 0,
        "provider_calls": 0,
        "rendered_files": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }


def test_completed_manual_plan_keeps_its_manual_branch_and_preflight_truth() -> None:
    state = {
        **_completed_profile_state(),
        "content_source": "manual",
        "source_fields": {"ai_input_type": "prompt_video", "content_source": "manual"},
        "manual_content": "Giới thiệu một sản phẩm theo yêu cầu của khách hàng.",
        "content_mode": "",
    }

    restored = _restore(state)

    assert restored["content_mode"] == "manual"
    assert restored["content_source"] == "manual"
    assert restored["content_choice"] == state["content_choice"]


def test_incomplete_realistic_plan_is_not_guessed_or_advanced() -> None:
    state = {
        "source_product_id": "video_ai_real",
        "product_type": "video_ai_real",
        "step": "content_source",
        "scene_count": 2,
        "aspect_ratio": "9:16",
        "ai_input_type": "prompt_video",
        "subject": "Một chủ đề chưa được chọn nguồn nội dung.",
    }

    assert _restore(state) == state


def test_restore_does_not_touch_storyboard_or_other_product_owners() -> None:
    state = {
        **_completed_profile_state(),
        "source_product_id": "storyboard_prompt",
        "product_type": "storyboard_prompt",
        "content_mode": "",
    }

    assert _restore(state) == state


def test_existing_mode_is_preserved_instead_of_reselecting_content() -> None:
    state = {**_completed_profile_state(), "content_mode": "suggestions"}

    restored = _restore(state)

    assert restored["content_mode"] == "suggestions"
    assert restored["content_choice"] == state["content_choice"]


def test_tail_context_uses_the_scoped_restore_before_pricing_preflight() -> None:
    source = _function_source("video_tail9_context")

    assert source.count("video_ai_realistic_restore_legacy_content_mode(host)") == 1
    assert "host = save_video_profile_studio_state(context, restored_host)" in source
    assert source.index("video_ai_realistic_restore_legacy_content_mode(host)") < source.index("requested = str(host.get")


def test_realistic_callback_contract_stays_single_owner_with_single_row_prompts() -> None:
    assert BOT_SOURCE.count(
        'CallbackQueryHandler(handle_video_profile_studio_callback, pattern=r"^vprofile\\|")'
    ) == 1
    prompt_keyboard = _function_source("video_scene3_suggestion_keyboard")
    assert "number_buttons," in prompt_keyboard
    assert "number_buttons[:2]" not in prompt_keyboard
    assert "number_buttons[2:4]" not in prompt_keyboard
