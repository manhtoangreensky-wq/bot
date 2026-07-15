from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path

from services import video_idea_catalog


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    match = re.search(
        rf"^(?:async\s+)?def\s+{re.escape(name)}\s*\([\s\S]*?(?=^(?:async\s+)?def\s+|^class\s+|\Z)",
        BOT_SOURCE,
        flags=re.MULTILINE,
    )
    assert match, name
    return match.group(0)


def _section(source: str, start: str, end: str) -> str:
    left = source.index(start)
    right = source.index(end, left + len(start))
    return source[left:right]


def test_reference_idea_goes_directly_to_scene_count_and_editable_scene_copy():
    preset_keyboard = _function_source("video_idea_dynamic_preset_keyboard")
    callback = _function_source("handle_video_idea_dynamic_callback")
    preset_branch = _section(
        callback,
        'if action == "preset":',
        '\n    state = video_idea_dynamic_state(uid)\n    preset = dict',
    )
    scene_branch = _section(callback, 'if action == "sc":', 'if action == "use":')

    assert "video_idea_dynamic_scene_count_keyboard" in preset_keyboard
    assert "videa|mode|a" not in preset_keyboard
    assert "videa|mode|m" not in preset_keyboard
    assert "idea2_scene_count" in preset_branch
    assert "video_idea_dynamic_build_drafts(state)" in scene_branch
    assert "idea2_preview" in scene_branch
    assert "idea2_auto_brief" not in scene_branch


def test_reference_preview_only_keeps_edit_continue_back_and_main():
    keyboard = _function_source("video_idea_dynamic_preview_keyboard")
    preview = _function_source("video_idea_dynamic_preview_text")
    editor = _function_source("video_idea_dynamic_edit_text")
    assert "Sửa nội dung" in keyboard
    assert "Tiếp tục hoàn thiện video" in keyboard
    assert "Chọn mẫu khác" in keyboard
    assert "menu|main" in keyboard
    for removed in (
        "Thêm cảnh",
        "Xóa cảnh",
        "Gộp 2 cảnh",
        "Tách cảnh",
        "Đổi thứ tự",
        "Lập lại một cảnh",
        "Khôi phục bản trước",
        "SCENE3",
    ):
        assert removed not in keyboard
    assert "<pre>" not in preview + editor
    assert "<code>" in preview + editor


def test_reference_full_edit_uses_the_copyable_scene_list():
    callback = _function_source("handle_video_idea_dynamic_callback")
    pending = _function_source("handle_video_idea_dynamic_pending_text")
    edit_branch = _section(callback, 'if action == "edit":', 'if action == "back":')

    assert 'state["idea2_edit_mode"] = "full"' in edit_branch
    assert "video_idea_dynamic_edit_text(state)" in edit_branch
    assert 'if mode == "full":' in pending
    assert "video_idea_script_intake.split_manual_script(raw_text)" in pending
    assert "video_idea_script_intake.manual_scene_drafts" in pending


def test_removed_legacy_idea_callbacks_are_read_only_redirects():
    callback = _function_source("handle_video_idea_dynamic_callback")
    custom = _section(callback, 'if action == "custom":', 'if action == "preset":')
    mode = _section(callback, 'if action == "mode":', 'if action == "sc":')
    old_tools = _section(callback, 'if action in {"regen", "restore"}:', 'if action == "edit":')

    assert "idea2_custom_topic" not in custom
    assert "video_idea_dynamic_category_keyboard" in custom
    assert "idea2_manual_script" not in mode
    assert "video_idea_dynamic_scene_count_keyboard" in mode
    assert "video_idea_dynamic_preview_keyboard" in old_tools
    assert "scene_draft_versions" not in old_tools


def test_public_reference_idea_copy_has_no_internal_words():
    public_source = "\n".join(
        _function_source(name)
        for name in (
            "video_idea_menu_text",
            "video_idea_dynamic_page_text",
            "video_idea_dynamic_category_text",
            "video_idea_dynamic_preset_text",
            "video_idea_dynamic_scene_count_text",
            "video_idea_dynamic_preview_text",
            "video_idea_dynamic_edit_text",
        )
    )
    for forbidden in ("job/outbox", "provider", "SCENE3", "chưa tạo file", "dịch vụ bên ngoài"):
        assert forbidden not in public_source


def test_trend_library_is_only_at_entry_and_custom_trend_is_available_everywhere_needed():
    intro = _function_source("task3d_product_intro_keyboard")
    trend_intro = _section(intro, '"video_trend": [', '"video_idea": [')
    inner = _function_source("task3d_trend_ideas_keyboard")

    assert trend_intro.count("Ý tưởng video có sẵn") == 1
    assert "Gợi ý trend hot" in trend_intro
    assert "Tự nhập trend" in trend_intro
    assert "Xem hướng dẫn" in trend_intro
    assert "Ý tưởng video có sẵn" not in inner
    assert "Tự nhập trend" in inner
    assert "Gợi ý khác" in inner
    assert "⬅️ Quay lại" in inner


def test_expired_number_buttons_recover_instead_of_throwing_generic_x():
    handler = _function_source("handle_video_product_callback")
    choose = _section(handler, 'if action == "microflow_choose":', 'if action in {"microflow_custom_topic", "microflow_edit"}:')
    trend = _section(handler, 'if action == "trend_select":', 'if action in {"ideas", "ideas_refresh"}:')

    assert "if not options:" in choose
    assert "Bộ gợi ý này đã hết phiên" in choose
    assert "task3d_product_intro_keyboard" in choose
    assert "if not ideas:" in trend
    assert "TASK3D_TREND_STORE.list_sources" in trend
    assert "task3d_render_step" in trend


def test_two_scene_reference_handoff_stays_two_scene_and_side_effect_free():
    plan = video_idea_catalog.build_plan(video_idea_catalog.IDEAS[0], scene_count=2)
    state = video_idea_catalog.build_scene3_handoff_state(
        plan,
        product_id_override="video_trend",
    )
    assert state["scene_count"] == 2
    assert set(state["video_prompt_versions"]) == {"1", "2"}
    assert len(state["plan"]["scenes"]) == 2
    assert state["final_confirmed"] is False
    assert state["provider_called"] is False
    assert state["job_created"] is False
    assert state["outbox_created"] is False
    assert state["wallet_mutations"] == 0
    assert state["xu_charged"] == 0


def test_every_changed_top_level_function_parses_independently():
    names = (
        "video_profile_scene1_render",
        "video_microflow_option_summary",
        "video_microflow_title",
        "task3d_product_intro_keyboard",
        "task3d_trend_ideas_keyboard",
        "handle_video_product_callback",
        "video_idea_menu_text",
        "video_idea_dynamic_page_text",
        "video_idea_dynamic_category_text",
        "video_idea_dynamic_category_keyboard",
        "video_idea_dynamic_preset_text",
        "video_idea_dynamic_preset_keyboard",
        "video_idea_dynamic_scene_count_keyboard",
        "video_idea_dynamic_preview_text",
        "video_idea_dynamic_preview_keyboard",
        "video_idea_dynamic_edit_text",
        "handle_video_idea_dynamic_pending_text",
        "handle_video_idea_dynamic_callback",
    )
    for name in names:
        source = textwrap.dedent(_function_source(name))
        ast.parse(source, filename=f"bot.py::{name}")
        compile(source, f"bot.py::{name}", "exec")
