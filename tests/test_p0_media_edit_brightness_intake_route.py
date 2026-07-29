from __future__ import annotations

import ast
import io
from pathlib import Path

import pytest
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageStat

from services import video_edit_state_machine, video_local_editing


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    async_marker = f"async def {name}("
    sync_marker = f"def {name}("
    start = BOT_SOURCE.find(async_marker)
    if start < 0:
        start = BOT_SOURCE.index(sync_marker)
    candidates = [BOT_SOURCE.find("\ndef ", start + 1), BOT_SOURCE.find("\nasync def ", start + 1)]
    ends = [position for position in candidates if position >= 0]
    return BOT_SOURCE[start:min(ends) if ends else len(BOT_SOURCE)]


def _compiled_function(name: str, namespace: dict):
    module = ast.parse("from __future__ import annotations\n\n" + _function_source(name))
    exec(compile(module, filename="bot.py", mode="exec"), namespace)
    return namespace[name]


class _Button:
    def __init__(self, text: str, callback_data: str):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


def test_public_image_edit_menu_exposes_real_brightness_route() -> None:
    keyboard = _compiled_function(
        "image_edit_choice_keyboard",
        {
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "normalize_user_language": lambda value: value,
            "ui_text": lambda _lang, _key: "Menu chính",
        },
    )("vi")
    rows = keyboard.inline_keyboard
    callbacks = [button.callback_data for row in rows for button in row]
    assert "imgtool|editor_brightness" in callbacks
    brightness_row = next(row for row in rows if row[0].callback_data == "imgtool|editor_brightness")
    assert [button.callback_data for button in brightness_row] == [
        "imgtool|editor_brightness",
        "imgtool|edit_type_custom",
    ]
    assert [button.callback_data for button in rows[-1]] == ["menu|main_image", "menu|main"]
    assert all(len(row) <= 2 for row in rows)


def test_image_brightness_changes_pixels_locally() -> None:
    processor = _compiled_function(
        "process_image_local_editor_bytes",
        {
            "Image": Image,
            "ImageEnhance": ImageEnhance,
            "ImageFilter": ImageFilter,
            "ImageOps": ImageOps,
            "ImageDraw": None,
            "ImageFont": None,
            "io": io,
            "IMAGE_EDITOR_PRESETS": {
                "brightness_only": {
                    "brightness": 1.0,
                    "contrast": 1.0,
                    "saturation": 1.0,
                    "sharpness": 1.0,
                    "tone": "neutral",
                },
            },
            "_image_editor_overlay_tone": lambda image, _tone: image,
            "sanitize_log_text": str,
        },
    )
    source = Image.new("RGB", (12, 12), (100, 100, 100))
    raw = io.BytesIO()
    source.save(raw, format="PNG")
    means = []
    for percent in (80, 100, 120):
        ok, payload, _size, preset = processor(
            raw.getvalue(),
            preset="brightness_only",
            settings={
                "brightness": percent / 100,
                "contrast": 1.0,
                "saturation": 1.0,
                "sharpness": 1.0,
            },
        )
        assert ok is True and preset == "brightness_only"
        with Image.open(io.BytesIO(payload)) as result:
            means.append(ImageStat.Stat(result.convert("RGB")).mean[0])
    assert means[0] < means[1] < means[2]
    assert means[1] == pytest.approx(100, abs=1)


def test_video_brightness_is_visible_and_reaches_ffmpeg() -> None:
    menu = _function_source("video_local_manual_options_keyboard")
    color_menu = _function_source("video_local_color_keyboard")
    callback = _function_source("handle_video_editor_callback")
    pending = _function_source("handle_video_editor_pending_text")
    assert '"videoedit|color"' in menu
    assert '"videoedit|brightness"' in color_menu
    assert 'if action == "brightness_set"' in callback
    assert 'if step == "await_brightness"' in pending

    plan = video_local_editing.normalize_manual_edit_plan(
        {"input_video": "source.mp4", "brightness_percent": 130},
        source_duration_ms=10_000,
    )
    command = video_local_editing.build_manual_ffmpeg_command(
        plan,
        output_path="output.mp4",
        source_probe={
            "ok": True,
            "duration": 10.0,
            "duration_ms": 10_000,
            "width": 640,
            "height": 360,
            "fps": 24.0,
            "has_video": True,
            "has_audio": True,
            "format_name": "mov,mp4",
            "bytes": 4096,
        },
        ffmpeg_path="ffmpeg",
    )
    assert "eq=brightness=0.150" in " ".join(command)
    assert "Độ sáng 130%" in video_local_editing.public_plan_summary(plan)


def test_video_edit_callback_answer_failure_cannot_surface_generic_x() -> None:
    callback = _function_source("handle_video_editor_callback")
    prologue = callback[: callback.index("    uid = query.from_user.id")]
    assert "try:" in prologue
    assert "await query.answer()" in prologue
    assert "except Exception as exc:" in prologue
    assert "videoedit callback answer skipped" in prologue
    assert "Có lỗi khi xử lý lệnh" not in callback


def test_video_edit_callback_has_one_public_owner_and_global_dedupe() -> None:
    registration = 'CallbackQueryHandler(handle_video_editor_callback, pattern=r"^videoedit\\|")'
    assert BOT_SOURCE.count(registration) == 1
    prefixes = BOT_SOURCE[
        BOT_SOURCE.index("VIDEO_PUBLIC_CALLBACK_PREFIXES = (") :
        BOT_SOURCE.index("_VIDEO_PUBLIC_CALLBACK_CLAIMS:")
    ]
    assert '"videoedit|"' in prefixes


def test_video_edit_upload_failure_keeps_exact_lane_without_generic_x() -> None:
    error_handler = _function_source("on_telegram_error")
    recovery = error_handler.index("if video_edit_intake_error_mode")
    generic = error_handler.index('"❌ Có lỗi khi xử lý lệnh. Bot chưa trừ Xu. Vui lòng thử lại sau."')
    assert recovery < generic
    recovery_block = error_handler[recovery:generic]
    assert "video_edit_intake_runtime_error" in recovery_block
    assert "save_video_edit_canonical_state" in recovery_block
    assert "video_edit_lane_upload_keyboard" in recovery_block
    assert "Phiên Chỉnh sửa / Nâng cấp vẫn được giữ nguyên" in recovery_block
    assert "return" in recovery_block

    for mode in ("manual_edit", "ai_edit", "quality_enhance"):
        state = video_edit_state_machine.start_lane(mode)
        waiting = video_edit_state_machine.keep_waiting_after_invalid(
            state,
            "video_edit_intake_runtime_error",
        )
        assert waiting["edit_mode"] == mode
        assert waiting["awaiting_media"] is True
        assert waiting["source_file_id"] is None
        assert video_edit_state_machine.back_target(mode) == "videoedit|hub"


def test_media_gateways_keep_one_canonical_video_edit_owner() -> None:
    for gateway in (
        "handle_photo",
        "handle_document_cache_only",
        "handle_media",
        "handle_media_cache_only",
    ):
        source = _function_source(gateway)
        assert source.count("handle_video_editor_pending_upload(update, context)") == 1
    assert BOT_SOURCE.count("async def handle_video_editor_pending_upload(") == 1


def test_changed_functions_parse_as_python311() -> None:
    for name in (
        "on_telegram_error",
        "image_edit_menu_start_text",
        "image_edit_instruction_text",
        "image_menu_v5_text",
        "image_edit_choice_keyboard",
        "handle_video_editor_pending_upload",
    ):
        ast.parse("from __future__ import annotations\n\n" + _function_source(name), filename=f"<{name}>")
