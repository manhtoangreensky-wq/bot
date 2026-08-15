from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_PATH = ROOT / "bot.py"
BOT_SOURCE = BOT_PATH.read_text(encoding="utf-8")
SCENE3_SOURCE = (ROOT / "services" / "video_scene3_flow.py").read_text(
    encoding="utf-8"
)


def _function_source(source: str, name: str) -> str:
    match = re.search(
        rf"(?m)^(?:async\s+def|def)\s+{re.escape(name)}\s*\(",
        source,
    )
    assert match, f"missing function: {name}"
    next_match = re.search(
        r"(?m)^(?:async\s+def|def)\s+[A-Za-z_][A-Za-z0-9_]*\s*\(",
        source[match.end() :],
    )
    end = match.end() + next_match.start() if next_match else len(source)
    return source[match.start() : end]


def _between(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    finish = source.index(end, begin)
    return source[begin:finish]


def test_changed_functions_are_syntax_valid() -> None:
    for name in (
        "video_uiflow3_canonical_screen_state",
        "video_long_uses_entity_pilot",
        "video_long_prepare_entity_pilot",
        "video_uiflow3_uses_entity_pilot",
        "video_ai_real_pilot_creative_payload",
        "video_ai_real_pilot_screen_payload",
        "_video_uiflow3_screen_payload_unscoped",
        "video_uiflow3_mode_target_step",
        "handle_video_uiflow3_callback",
    ):
        compile(
            "from __future__ import annotations\n" + _function_source(BOT_SOURCE, name),
            f"bot.py::{name}",
            "exec",
        )


def test_long_mode_opens_series_goal_instead_of_scene_count() -> None:
    target = _function_source(BOT_SOURCE, "video_uiflow3_mode_target_step")
    callback = _function_source(BOT_SOURCE, "handle_video_uiflow3_callback")
    mode_branch = _between(
        callback,
        'elif action == "mode" and values:',
        'elif action == "series_goal_edit":',
    )

    assert '"multi_scene_film"' in target
    assert '"series_goal"' in target
    assert '"scene_count"' in target
    assert "video_uiflow3_mode_target_step(updated)" in mode_branch
    assert 'target_step="scene_count"' not in mode_branch


def test_long_uses_shared_entity_middle_only_at_production_bible() -> None:
    long_owner = _function_source(BOT_SOURCE, "video_long_uses_entity_pilot")
    shared_owner = _function_source(BOT_SOURCE, "video_uiflow3_uses_entity_pilot")
    screen = _function_source(BOT_SOURCE, "video_ai_real_pilot_screen_payload")

    assert 'parent_product") or "") == "multi_scene_film"' in long_owner
    assert 'get("current_step")' in long_owner
    assert ') == "production_bible"' in long_owner
    assert "video_long_uses_entity_pilot(raw_state)" in shared_owner
    assert "long_video_middle = bool(" in screen
    assert 'str(state.get("parent_product") or "") == "multi_scene_film"' in screen
    assert "and not long_video_middle" in screen


def test_long_middle_assigns_environment_to_requirements_once() -> None:
    prepare = _function_source(BOT_SOURCE, "video_long_prepare_entity_pilot")
    canonical = _function_source(BOT_SOURCE, "video_uiflow3_canonical_screen_state")
    screen = _function_source(BOT_SOURCE, "video_ai_real_pilot_screen_payload")
    entity_panel = _between(
        screen,
        'if step == "production_bible" and not view:',
        'if view == "character_count":',
    )

    assert 'state["needs"]["locations"] = "SKIP"' in prepare
    assert "video_uiflow3.set_location_count(state, 0)" in prepare
    assert "video_long_prepare_entity_pilot(raw_state)" in canonical
    assert "👥 Nhân vật và tham chiếu" in entity_panel
    assert "👥 Số nhân vật" in entity_panel
    assert "👤 Danh sách nhân vật" in entity_panel
    assert "🖼 Ảnh tham chiếu" in entity_panel
    assert "🏞 Số bối cảnh" not in entity_panel
    assert "🗺 Danh sách bối cảnh" not in entity_panel


def test_shared_requirement_screen_contains_one_environment_owner_and_icons() -> None:
    categories = _between(
        SCENE3_SOURCE,
        "REQUIREMENT_CATEGORIES = (",
        "REQUIREMENT_UPLOAD_TYPES = {",
    )
    public_alias = _between(
        BOT_SOURCE,
        "VIDEO_AI_REAL_PILOT_REQUIREMENT_CATEGORIES =",
        "def video_ai_real_pilot_scene3_field_state",
    )
    payload = _function_source(BOT_SOURCE, "video_ai_real_pilot_requirements_payload")

    assert categories.count('("environment", "🏞 Bối cảnh/kiến trúc")') == 1
    assert "video_scene3_flow.PUBLIC_REQUIREMENT_CATEGORIES" in public_alias
    assert "VIDEO_AI_REAL_PILOT_REQUIREMENT_CATEGORIES" in payload
    assert "✨ Tự động gợi ý" in payload
    assert "👁 Xem mục đã chọn" in payload
    assert "không hỏi lại ở màn Nhân vật" in payload


def test_long_bible_continues_to_style_then_requirement_then_episode() -> None:
    callback = _function_source(BOT_SOURCE, "handle_video_uiflow3_callback")
    bible_done = _between(
        callback,
        'elif action == "bible_done":',
        'elif action == "episode_identity":',
    )
    requirement_done = _between(
        callback,
        'elif action in {"pilot_requirement_done", "pilot_requirement_skip"}:',
        'elif action == "pilot_scene_plan_back":',
    )

    assert 'in {"video_ai_real", "multi_scene_film"}' in bible_done
    assert 'video_uiflow3_open_view(state, "pilot_creative_controls")' in bible_done
    assert 'parent_product") or "") == "multi_scene_film"' in requirement_done
    assert 'video_uiflow3_go(state, "episode")' in requirement_done
    assert requirement_done.index('video_uiflow3_go(state, "episode")') < requirement_done.index(
        "count = safe_int"
    )


def test_long_episode_back_returns_to_requirements() -> None:
    callback = _function_source(BOT_SOURCE, "handle_video_uiflow3_callback")
    back_branch = _between(
        callback,
        'elif action == "back":',
        'elif action == "mode" and values:',
    )

    assert 'current_step == "episode"' in back_branch
    assert 'parent_product") or "") == "multi_scene_film"' in back_branch
    assert 'state["navigation"]["current_step"] = "production_bible"' in back_branch
    assert 'video_uiflow3_open_view(state, "pilot_requirements")' in back_branch


def test_long_episode_actions_are_iconized_and_share_two_button_rows() -> None:
    screen = _function_source(BOT_SOURCE, "_video_uiflow3_screen_payload_unscoped")
    episode = _between(screen, 'if step == "episode":', 'if step == "scene_count":')

    assert '[("🔢 Số và tên tập", "vid3|episode_identity"), ("📝 Nội dung tập", "vid3|episode_content")]' in episode
    assert '[("👥 Nhân vật/bối cảnh của tập", "vid3|episode_entities"), ("✅ Hoàn tất nội dung tập", "vid3|episode_done")]' in episode


def test_long_entity_panel_does_not_offer_quick_build_that_skips_episode() -> None:
    screen = _function_source(BOT_SOURCE, "video_ai_real_pilot_screen_payload")
    entity_panel = _between(
        screen,
        'if step == "production_bible" and not view:',
        'if view == "character_count":',
    )

    assert 'parent_product") or "") != "multi_scene_film"' in entity_panel


def test_long_style_and_stale_callback_cannot_quick_build_past_episode() -> None:
    creative = _function_source(BOT_SOURCE, "video_ai_real_pilot_creative_payload")
    callback = _function_source(BOT_SOURCE, "handle_video_uiflow3_callback")
    quick_branch = _between(
        callback,
        'elif action == "quick_build":',
        'elif action == "bible_done":',
    )

    assert 'parent_product") or "") != "multi_scene_film"' in creative
    assert 'parent_product") or "") == "multi_scene_film"' in quick_branch
    assert "Video dài tập cần hoàn tất thông tin tập" in quick_branch
    assert quick_branch.index('parent_product") or "") == "multi_scene_film"') < quick_branch.index(
        "video_ai_real_build_quick_plan"
    )


def test_long_tail_confirmation_remains_maintenance_status_without_job_or_charge() -> None:
    callback = _function_source(BOT_SOURCE, "handle_video_tail_callback")
    guard = _between(
        callback,
        'if not contract.get("execution_enabled"):',
        'if owner != "video_edit" and deferred_runtime_product:',
    )

    assert 'product_type in {"multi_scene_film", "video_long"}' in guard
    assert '"blocker_code": "long_video_under_upgrade"' in guard
    assert "video_tail9_prepare_submit_status" in guard
    assert "video_tail9_render_confirmed_status" in guard
    assert "create_video_job" not in guard
    assert "deduct" not in guard.lower()
    assert "charge" not in guard.lower()


def test_protected_tail_function_is_byte_identical_to_origin_main() -> None:
    baseline = subprocess.run(
        ["git", "show", "origin/main:bot.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout

    assert _function_source(BOT_SOURCE, "handle_video_tail_callback") == _function_source(
        baseline,
        "handle_video_tail_callback",
    )
