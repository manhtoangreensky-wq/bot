import subprocess
import os
from pathlib import Path

import pytest

import bot


REPO_ROOT = Path(__file__).resolve().parents[1]


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def _changed_files_from_main():
    output = subprocess.check_output(
        ["git", "diff", "--name-only", "origin/main"],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
    )
    return {line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()}


def _current_branch_name():
    for key in ("GITHUB_HEAD_REF", "GITHUB_REF_NAME", "BRANCH_NAME"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return subprocess.check_output(
        ["git", "branch", "--show-current"],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
    ).strip()


def _is_subdub_m6_revert_scope():
    branch = _current_branch_name().lower()
    branch_tokens = (
        "p0-19m6r",
        "revert-subdub-m6",
        "subdub-m6-revert",
        "subdub-m6r",
    )
    return any(token in branch for token in branch_tokens)


def _skip_unless_subdub_m6_revert_scope():
    if not _is_subdub_m6_revert_scope():
        pytest.skip("SubDub M6 revert scope guard is not active for this branch")


def test_subdub_m6_reverted_contract():
    assert not hasattr(bot, "SUBDUB_TELEGRAM_OUTPUT_MAX_MB")
    assert not hasattr(bot, "subdub_pricing_audit_payload")
    assert not hasattr(bot, "subdub_status_debug_payload")
    assert not (REPO_ROOT / "tests/test_p0_19m6_subdub_final_polish_mode_bugs_pricing_file_limit.py").exists()


def test_video_without_subtitle_direct_dub_button_hidden():
    keyboard = bot.subtitle_plus_dub_no_subtitle_menu_keyboard("vi")
    labels = _labels(keyboard)
    callbacks = _callbacks(keyboard)

    assert "🎙 Lồng tiếng trực tiếp" not in labels
    assert all(bot.VIDEO_DUBBING_NO_SUBTITLE_DIRECT_DUB not in str(callback) for callback in callbacks)


def test_video_without_subtitle_keeps_auto_subtitle_then_dub_button():
    keyboard = bot.subtitle_plus_dub_no_subtitle_menu_keyboard("vi")
    labels = _labels(keyboard)
    callbacks = _callbacks(keyboard)

    assert "🎬 Tạo phụ đề rồi lồng tiếng" in labels
    assert f"videodub|no_subtitle_flow|{bot.VIDEO_DUBBING_NO_SUBTITLE_CREATE_THEN_DUB}" in callbacks


def test_subdub_existing_m5_routes_still_present():
    keyboard = bot.subtitle_plus_dub_no_subtitle_menu_keyboard("vi")
    labels = _labels(keyboard)
    callbacks = _callbacks(keyboard)

    assert "⬅️ Phụ đề + Lồng tiếng" in labels
    assert "🏠 Menu chính" in labels
    assert f"videodub|type|{bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}" in callbacks
    assert "menu|main" in callbacks


def test_no_music_files_touched():
    _skip_unless_subdub_m6_revert_scope()
    changed = _changed_files_from_main()
    assert not any("music" in path.lower() or "suno" in path.lower() for path in changed)


def test_no_finance_files_touched():
    _skip_unless_subdub_m6_revert_scope()
    changed = _changed_files_from_main()
    assert not any("finance" in path.lower() or "tax" in path.lower() for path in changed)


def test_no_payos_files_touched():
    _skip_unless_subdub_m6_revert_scope()
    changed = _changed_files_from_main()
    assert not any("payos" in path.lower() or "wallet" in path.lower() or "payment" in path.lower() for path in changed)
