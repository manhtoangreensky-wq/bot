from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str, next_name: str) -> str:
    start = BOT_SOURCE.index(f"def {name}(")
    end = BOT_SOURCE.index(f"def {next_name}(", start)
    return BOT_SOURCE[start:end]


def _async_function_source(name: str, next_name: str) -> str:
    start = BOT_SOURCE.index(f"async def {name}(")
    end = BOT_SOURCE.index(f"async def {next_name}(", start)
    return BOT_SOURCE[start:end]


def _validated_rows(rows):
    callbacks: set[str] = set()
    for row in rows:
        if len(row) != 2:
            raise ValueError("video_scene3_keyboard_requires_exactly_two_buttons_per_row")
        for label, callback in row:
            if not label or not callback or callback in callbacks:
                raise ValueError("video_scene3_keyboard_duplicate_or_empty_button")
            callbacks.add(callback)
    return rows


def _load_keyboard_function(name: str, next_name: str):
    namespace = {
        "normalize_user_language": lambda lang: str(lang or "vi"),
        "video_scene3_keyboard": _validated_rows,
        "ui_text": lambda _lang, key: "⬅️ Quay lại" if key == "common.back" else "🏠 Menu chính",
    }
    exec("from __future__ import annotations\n" + _function_source(name, next_name), namespace)
    return namespace[name]


def _callbacks(rows) -> list[str]:
    return [str(callback) for row in rows for _label, callback in row]


def test_videoedit_brightness_keyboard_builds_with_unique_two_column_rows() -> None:
    keyboard = _load_keyboard_function("video_local_brightness_keyboard", "video_local_cut_options_text")
    rows = keyboard("vi")
    callbacks = _callbacks(rows)
    assert "videoedit|review" in callbacks
    assert "videoedit|options|manual" in callbacks
    assert len(callbacks) == len(set(callbacks))


@pytest.mark.parametrize(
    "action",
    [
        "compress",
        "subtitle",
        "legacy",
        "manual_info",
        "split_info",
        "ai_info",
        "color",
        "preset",
        "text",
        "logo",
        "sharpen",
    ],
)
def test_videoedit_legacy_keyboard_never_duplicates_callbacks(action: str) -> None:
    keyboard = _load_keyboard_function("video_edit_legacy_redirect_keyboard", "video_edit_audio_text")
    rows = keyboard(action, "vi")
    callbacks = _callbacks(rows)
    assert len(callbacks) == len(set(callbacks))


class _Message:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def reply_text(self, text: str, **kwargs):
        self.calls.append((text, kwargs))
        return None


def test_video_enhance_command_opens_only_the_canonical_hub() -> None:
    message = _Message()
    recorded: list[tuple[str, tuple, dict]] = []
    namespace = {
        "get_user_language": lambda _uid: "vi",
        "recent_video_editor_source": lambda _uid: {},
        "set_video_editor_pending": lambda *args, **kwargs: recorded.append(("set", args, kwargs)),
        "clear_video_editor_pending": lambda *args, **kwargs: recorded.append(("clear", args, kwargs)),
        "set_video_route_session": lambda *args, **kwargs: recorded.append(("route", args, kwargs)),
        "video_edit_hub_text": lambda _lang: "🛠️ Chỉnh sửa / Nâng cấp video",
        "video_edit_hub_keyboard": lambda _lang: [
            [("AI", "videoedit|ai"), ("Manual", "videoedit|manual")],
            [("Quality", "videoedit|restore"), ("Guide", "videoedit|guide")],
        ],
        "video_editor_menu_text": lambda _lang: "obsolete menu",
        "video_editor_menu_keyboard": lambda _lang: [[("Color", "videoedit|color"), ("Text", "videoedit|text")]],
    }
    source = _async_function_source("cmd_video_enhance", "cmd_image_enhance")
    exec("from __future__ import annotations\n" + source, namespace)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=70021), message=message)

    asyncio.run(namespace["cmd_video_enhance"](update, SimpleNamespace()))

    assert len(message.calls) == 1
    text, kwargs = message.calls[0]
    assert text == "🛠️ Chỉnh sửa / Nâng cấp video"
    assert _callbacks(kwargs["reply_markup"]) == [
        "videoedit|ai",
        "videoedit|manual",
        "videoedit|restore",
        "videoedit|guide",
    ]
    assert any(item[0] == "clear" for item in recorded)
    assert any(item[0] == "route" for item in recorded)


def test_legacy_guard_does_not_shadow_live_canonical_actions() -> None:
    start = BOT_SOURCE.index("async def handle_video_editor_callback")
    end = BOT_SOURCE.index("async def handle_video_upload_callback", start)
    callback = BOT_SOURCE[start:end]
    assert "canonical_compatibility_action(raw_action)" in callback
    assert 'if raw_action in {"audio", "audio_upload", "timeline", "effects", "plan", "split", "reset_manual", "cut"}' not in callback
    assert "legacy_action_map =" not in callback


def test_lvs27b_root_back_uses_saved_videoedit_language() -> None:
    start = BOT_SOURCE.index('if result.get("exit_parent")')
    end = BOT_SOURCE.index("def commit_parent", start)
    block = BOT_SOURCE[start:end]
    assert "get_user_language(user_id)" in block
    assert "effective_user" not in block
    assert "language_code" not in block
