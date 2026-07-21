from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _between(start: str, end: str) -> str:
    begin = BOT_SOURCE.index(start)
    finish = BOT_SOURCE.index(end, begin)
    return BOT_SOURCE[begin:finish]


def test_edit3_public_hub_has_only_four_clear_actions() -> None:
    keyboard = _between("def video_edit_hub_keyboard", "def video_edit_info_text")
    expected = {
        "videoedit|ai",
        "videoedit|manual",
        "videoedit|restore",
        "videoedit|guide",
    }
    for callback in expected:
        assert keyboard.count(f'"{callback}"') == 1
    for removed in (
        "videoedit|audio",
        "videoedit|timeline",
        "videoedit|effects",
        "videoedit|plan",
        "videoedit|reset_manual",
    ):
        assert removed not in keyboard


def test_edit3_manual_actions_appear_only_after_video_summary() -> None:
    summary = _between("def video_local_source_summary_keyboard", "def video_local_manual_options_text")
    manual = _between("def video_local_manual_options_keyboard", "def video_local_split_options_text")
    assert '"videoedit|options|{tool}"' in summary
    for callback in (
        "videoedit|manual_cut",
        "videoedit|manual_join",
        "videoedit|manual_audio",
        "videoedit|manual_effects",
        "videoedit|speed",
        "videoedit|manual_rotate_flip",
    ):
        assert callback in manual
    hub = _between("def video_edit_hub_keyboard", "def video_edit_info_text")
    assert all(callback not in hub for callback in (
        "videoedit|manual_cut",
        "videoedit|manual_join",
        "videoedit|manual_audio",
        "videoedit|manual_effects",
    ))


def test_edit3_manual_submenus_are_complete_and_back_one_screen() -> None:
    cut = _between("def video_local_cut_options_keyboard", "def video_local_join_options_text")
    assert all(callback in cut for callback in (
        "videoedit|trim_edges",
        "videoedit|remove_middle",
        "videoedit|split_from_manual",
        "videoedit|options|manual",
    ))
    join = _between("def video_local_join_options_keyboard", "def video_local_rotate_flip_text")
    assert all(callback in join for callback in (
        "videoedit|concat",
        "videoedit|reorder",
        "videoedit|options|manual",
    ))
    rotate = _between("def video_local_rotate_flip_keyboard", "def video_local_split_options_text")
    assert all(callback in rotate for callback in (
        "videoedit|rotation",
        "videoedit|flip",
        "videoedit|options|manual",
    ))
    split = _between("def video_local_split_options_keyboard", "def video_local_choice_keyboard")
    assert all(callback in split for callback in (
        "videoedit|split_fixed",
        "videoedit|split_count",
        "videoedit|split_custom",
    ))


def test_edit3_entry_clears_stale_product_video_session() -> None:
    handler = _between("async def handle_video_editor_callback", "async def handle_video_upload_callback")
    hub = handler[handler.index('if raw_action in {"hub", "menu"}'):handler.index('if raw_action in {"manual_info"')]
    assert hub.index("clear_video_session(uid)") < hub.index("clear_video_editor_pending(uid)")
    manual = handler[handler.index('if action == "manual"'):handler.index("state = dict(get_video_editor_pending(uid) or {})", handler.index('if action == "manual"'))]
    assert manual.index("clear_video_session(uid)") < manual.index("clear_video_editor_pending(uid)")
    pending = _between("async def handle_video_editor_pending_text", "async def handle_video_editor_callback")
    assert all(step in pending for step in (
        '"await_split_fixed"',
        '"await_split_count"',
        '"await_split_custom"',
    ))


def test_edit3_legacy_buttons_are_read_only_and_cannot_reset_plan() -> None:
    handler = _between("async def handle_video_editor_callback", "async def handle_video_upload_callback")
    start = handler.index('if raw_action in {"audio", "audio_upload"')
    end = handler.index("action = video_editor_normalize_action(raw_action)")
    legacy = handler[start:end]
    for callback in ("audio", "audio_upload", "timeline", "effects", "plan", "split", "reset_manual", "cut"):
        assert f'"{callback}"' in legacy
    assert "clear_video_editor_pending" not in legacy
    assert "set_video_editor_pending" not in legacy
    assert "update_video_editor_pending" not in legacy


def test_edit3_route_contract_matches_visible_hub() -> None:
    route = _between('"video_local_edit": {', "def video_public_route_for_tool")
    assert '"expected_children": ("videoedit|ai", "videoedit|manual", "videoedit|restore", "videoedit|guide")' in route
    assert '"back_target": "menu|main_video"' in route
