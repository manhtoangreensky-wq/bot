from __future__ import annotations

from copy import deepcopy
import html
from pathlib import Path
import re

from services import video_scene3_flow


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
COMPILE_GUARD_SOURCE = (ROOT / "scripts" / "check_bot_source_compile.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    start = BOT_SOURCE.index(f"def {name}(")
    candidates = [
        position
        for marker in ("\ndef ", "\nasync def ")
        if (position := BOT_SOURCE.find(marker, start + 1)) >= 0
    ]
    end = min(candidates) if candidates else len(BOT_SOURCE)
    return BOT_SOURCE[start:end]


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _materials_text_renderer():
    namespace = {
        "html": html,
        "safe_int": _safe_int,
        "video_scene3_flow": video_scene3_flow,
    }
    source = "from __future__ import annotations\n" + _function_source("video_scene3_materials_text")
    exec(compile(source, "<scene3-materials-text>", "exec"), namespace)
    return namespace["video_scene3_materials_text"]


class _Button:
    def __init__(self, text: str, *, callback_data: str):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


def _materials_keyboard_renderer():
    namespace = {
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "video_scene3_flow": video_scene3_flow,
    }
    for name in (
        "video_scene3_keyboard",
        "video_scene3_nav_rows",
        "video_scene3_materials_keyboard",
    ):
        source = "from __future__ import annotations\n" + _function_source(name)
        exec(compile(source, f"<scene3-materials-keyboard:{name}>", "exec"), namespace)
    return namespace["video_scene3_materials_keyboard"]


def _state(item: dict) -> dict:
    return {
        "reference_assets": {
            "items": [item],
            "planning_notes": [],
        },
        "active_material_index": 1,
    }


def test_permanent_guard_compiles_complete_bot_source_in_python_311_ci():
    assert 'source = BOT_PATH.read_text(encoding="utf-8")' in COMPILE_GUARD_SOURCE
    assert 'compile(source, str(BOT_PATH), "exec")' in COMPILE_GUARD_SOURCE
    assert "ast.parse(source, filename=str(BOT_PATH))" in COMPILE_GUARD_SOURCE
    workflow = (ROOT / ".github" / "workflows" / "bot-source-compile.yml").read_text(encoding="utf-8")
    assert 'python-version: "3.11"' in workflow
    assert "python scripts/check_bot_source_compile.py" in workflow
    assert "python -m py_compile bot.py" in workflow


def test_scene3_caption_renderer_has_no_nested_f_string_quote_seam():
    start = BOT_SOURCE.index("def video_scene3_keyboard(")
    end = BOT_SOURCE.index("async def handle_video_profile_studio_callback(")
    scene3_source = BOT_SOURCE[start:end]
    assert re.search(r'''f["']\{f["']''', scene3_source) is None
    compile(
        "from __future__ import annotations\n" + _function_source("video_scene3_materials_text"),
        "<scene3-materials-text>",
        "exec",
    )


def test_caption_is_html_escaped_truncated_and_prefixed_without_mutating_state():
    render = _materials_text_renderer()
    caption = "'single' \"double\" <tag> & " + ("x" * 120)
    state = _state({"type": "character_person", "caption": caption, "file_name": "ignored.png"})
    before = deepcopy(state)
    text = render(state)
    expected = " · " + html.escape(caption[:90])
    assert expected in text
    assert html.escape(caption[:91]) not in text
    assert state == before


def test_empty_caption_has_no_separator_suffix():
    render = _materials_text_renderer()
    item = {"type": "character_person", "caption": "   ", "file_name": ""}
    text = render(_state(item))
    material_type = video_scene3_flow.normalize_material_type(item["type"])
    label = dict(video_scene3_flow.MATERIAL_TYPES).get(material_type, "Tư liệu")
    assert f"1. {label}\n" in text
    assert f"1. {label} · " not in text


def test_file_name_is_used_when_caption_is_empty():
    render = _materials_text_renderer()
    text = render(_state({"type": "product_object", "caption": "", "file_name": "san-pham <01>.png"}))
    assert " · san-pham &lt;01&gt;.png" in text


def test_material_screen_renders_special_quotes_and_keeps_callback_data_unchanged():
    render_text = _materials_text_renderer()
    render_keyboard = _materials_keyboard_renderer()
    caption = "Cảnh 'sáng' \"ấm\" <đẹp>"
    text = render_text(_state({"type": "background", "caption": caption}))
    assert html.escape(caption) in text

    callbacks = [
        button.callback_data
        for row in render_keyboard().inline_keyboard
        for button in row
    ]
    assert callbacks == [
        "vprofile|material|ai_image_plan", "vprofile|material|layout_ideas",
        "vprofile|material|storyboard_prompt", "vprofile|material|character_person",
        "vprofile|material|product_object", "vprofile|material|background",
        "vprofile|material|visual_style_reference", "vprofile|material|storyboard_frames",
        "vprofile|material|logo", "vprofile|material|voice_audio",
        "vprofile|material|music", "vprofile|material_view",
        "vprofile|material_prev", "vprofile|material_next",
        "vprofile|material_edit", "vprofile|material_remove",
        "vprofile|material_restore", "vprofile|material_done",
        "vprofile|back", "menu|main",
    ]
