from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    match = re.search(rf"^(?:async )?def {re.escape(name)}\(", BOT_SOURCE, re.MULTILINE)
    assert match, f"missing function: {name}"
    next_match = re.search(
        r"\n(?=@|(?:async )?def [A-Za-z_])",
        BOT_SOURCE[match.end() :],
    )
    end = match.end() + next_match.start() if next_match else len(BOT_SOURCE)
    return BOT_SOURCE[match.start() : end]


def test_changed_functions_are_syntax_valid() -> None:
    for name in (
        "video_ai_real_pilot_screen_payload",
        "video_profile_scene1_render",
        "video_trend_prepare_entity_bridge",
        "video_trend_finish_requirements_without_legacy_audio",
        "handle_video_profile_studio_callback",
    ):
        compile(_function_source(name), f"bot.py::{name}", "exec")


def test_trend_uses_realistic_character_hub_without_location_duplicate() -> None:
    class _UiFlow:
        VIDEO_AI_REAL_PRODUCT_FIRST_MODES = frozenset({"prompt_video", "image_video"})

    trend_marker = {
        "active": True,
        "back_callback": "vtrend|resume",
    }
    namespace = {
        "video_uiflow3": _UiFlow,
        "video_uiflow3_uses_entity_pilot": lambda _state: True,
        "video_storyboard_entity_bridge_marker": lambda _state: {},
        "video_trend_entity_bridge_marker": lambda _state: trend_marker,
        "video_entity_bridge_marker": lambda _state: trend_marker,
        "video_ai_real_pilot_input_payload": lambda _state: None,
        "video_ai_real_pilot_bible_view_payload": lambda _state, view: None,
        "video_ai_real_pilot_scene_view_payload": lambda _state, view: None,
        "video_ai_real_pilot_prompt_view_payload": lambda _state, view: None,
        "video_ai_real_pilot_nav_rows": lambda back: [
            [("⬅️ Quay lại", back), ("🎬 Menu Video", "menu|main_video")]
        ],
        "video_uiflow3_keyboard": lambda rows: rows,
    }
    exec(
        "from __future__ import annotations\n"
        + _function_source("video_ai_real_pilot_screen_payload"),
        namespace,
    )

    payload = namespace["video_ai_real_pilot_screen_payload"](
        {
            "entry_mode": "selected_trend",
            "bible": {
                "characters": [],
                "locations": [],
                "products": [],
                "props": [],
            },
            "references": [],
        },
        step="production_bible",
        view="",
        prefix="",
    )

    assert payload is not None
    text, rows = payload
    labels = [label for row in rows for label, _callback in row]
    callbacks = [callback for row in rows for _label, callback in row]
    assert "👥 Nhân vật và tham chiếu" in text
    assert "Bối cảnh" not in text
    assert not any("Bối cảnh" in label for label in labels)
    assert {
        "👥 Số nhân vật",
        "👤 Danh sách nhân vật",
        "🖼 Ảnh tham chiếu",
        "🛠 Tùy chỉnh chi tiết",
        "⚡ Tạo nhanh",
        "✨ Tự động gợi ý",
        "✅ Hoàn tất thiết lập nhân vật",
    }.issubset(set(labels))
    assert "vtrend|resume" in callbacks


def test_video_ai_real_character_hub_remains_available_without_a_bridge() -> None:
    class _UiFlow:
        VIDEO_AI_REAL_PRODUCT_FIRST_MODES = frozenset({"prompt_video", "image_video"})

    namespace = {
        "video_uiflow3": _UiFlow,
        "video_uiflow3_uses_entity_pilot": lambda _state: True,
        "video_storyboard_entity_bridge_marker": lambda _state: {},
        "video_entity_bridge_marker": lambda _state: {},
        "video_ai_real_pilot_input_payload": lambda _state: None,
        "video_ai_real_pilot_bible_view_payload": lambda _state, view: None,
        "video_ai_real_pilot_scene_view_payload": lambda _state, view: None,
        "video_ai_real_pilot_prompt_view_payload": lambda _state, view: None,
        "video_ai_real_pilot_nav_rows": lambda back: [[("⬅️ Quay lại", back)]],
        "video_uiflow3_keyboard": lambda rows: rows,
    }
    exec(
        "from __future__ import annotations\n"
        + _function_source("video_ai_real_pilot_screen_payload"),
        namespace,
    )

    payload = namespace["video_ai_real_pilot_screen_payload"](
        {
            "entry_mode": "prompt_video",
            "bible": {"characters": [], "locations": [], "products": [], "props": []},
            "references": [],
        },
        step="production_bible",
        view="",
        prefix="",
    )

    assert payload is not None
    text, rows = payload
    labels = [label for row in rows for label, _callback in row]
    assert "👥 Nhân vật và tham chiếu" in text
    assert "⚡ Tạo nhanh" in labels


def test_trend_bridge_assigns_context_to_requirements_not_character_locations() -> None:
    bridge = _function_source("video_trend_prepare_entity_bridge")
    assert 'state["needs"]["locations"] = "SKIP"' in bridge
    assert "video_uiflow3.set_location_count(state, 0)" in bridge


def test_trend_requirement_done_builds_scene_plan_without_legacy_audio_screen() -> None:
    helper = _function_source("video_trend_finish_requirements_without_legacy_audio")
    callback = _function_source("handle_video_profile_studio_callback")
    requirement_branch = callback[
        callback.index('if action == "req_none":'):
        callback.index('if action == "material":')
    ]

    assert 'video_flow6_product_id(state) != "video_trend"' in helper
    assert "video_scene3_flow.finalize_audio_planning" in helper
    assert "skip=True" in helper
    assert '"scene_plan"' in helper
    assert requirement_branch.count("video_trend_finish_requirements_without_legacy_audio") == 2


def test_trend_old_audio_callbacks_return_to_canonical_addon_or_scene_plan() -> None:
    callback = _function_source("handle_video_profile_studio_callback")
    recovery = callback[
        callback.index("source_product_id = video_flow6_product_id(state)"):
        callback.index('if action == "back":')
    ]
    renderer = _function_source("video_profile_scene1_render")

    assert 'source_product_id == "video_trend"' in recovery
    assert 'step in {"audio_plan", "content_addons"}' in recovery
    assert "video_trend_finish_requirements_without_legacy_audio" in recovery
    assert 'action in {"audio_open", "audio_review", "audio_done", "audio_skip"}' in recovery
    assert 'video_tail9_render(query, uid, context, "addon")' in recovery
    assert 'step in {"audio_plan", "content_addons"}' in renderer
    assert "video_trend_finish_requirements_without_legacy_audio" in renderer


def test_trend_scene_plan_back_returns_to_requirements_not_legacy_audio() -> None:
    callback = _function_source("handle_video_profile_studio_callback")
    back_branch = callback[
        callback.index('if action == "back":'):
        callback.index('if action in {"image_ai_return", "asset_ai_return"}:')
    ]

    assert 'source_product_id == "video_trend"' in back_branch
    assert 'step == "scene_plan"' in back_branch
    assert 'not str(state.get("video_tail_return_to") or "")' in back_branch
    assert 'video_profile_studio_step(context, state, "requirements", push=False)' in back_branch


def test_trend_existing_prompt_to_tail_and_callback_owner_remain_locked() -> None:
    callback = _function_source("handle_video_profile_studio_callback")
    prompt_branch = callback[
        callback.index('if action == "video_prompt_done":'):
        callback.index('if action == "review_image_prompts":')
    ]
    assert 'video_flow6_product_id(state) == "video_trend"' in prompt_branch
    assert 'video_tail9_render(query, uid, context, "addon")' in prompt_branch
    assert BOT_SOURCE.count(
        'CallbackQueryHandler(handle_video_trend2_callback, pattern=r"^vtrend\\|")'
    ) == 1
