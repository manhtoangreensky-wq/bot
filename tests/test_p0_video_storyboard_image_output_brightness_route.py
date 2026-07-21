from __future__ import annotations

import ast
import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageStat

from services import video_local_editing, video_storyboard2


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


class _Button:
    def __init__(self, text: str, callback_data: str):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


def _compiled_function(name: str, namespace: dict):
    module = ast.parse("from __future__ import annotations\n\n" + _function_source(name))
    exec(compile(module, filename="bot.py", mode="exec"), namespace)
    return namespace[name]


def test_storyboard_prompt_has_two_image_targets_finish_and_exact_back() -> None:
    keyboard = _compiled_function(
        "quick_image_prepared_prompt_keyboard",
        {
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "normalize_user_language": lambda value: value,
            "_safe_int": lambda value, default=0: int(value or default),
            "ui_text": lambda _lang, key: "Menu chính" if key.endswith("main_menu") else "Quay lại",
        },
    )(
        "vi",
        state={
            "owner": "storyboard_image",
            "flow": "storyboard",
            "product": "storyboard_prompt",
            "storyboard_target_index": 1,
            "storyboard_target_count": 2,
        },
    )
    rows = keyboard.inline_keyboard
    assert [button.text for button in rows[0]] == ["✅ Ảnh 1", "Ảnh 2"]
    assert [button.callback_data for button in rows[0]] == [
        "vstoryimg|qi_target_1",
        "vstoryimg|qi_target_2",
    ]
    assert [button.callback_data for button in rows[1]] == [
        "vstoryimg|qi_choose_ratio",
        "vstoryimg|qi_logo_choice",
    ]
    assert [button.callback_data for button in rows[-2]] == ["vstoryimg|qi_finish_image"]
    assert [button.callback_data for button in rows[-1]] == ["vstoryimg|cancel", "menu|main"]
    assert all(len(row) <= 2 for row in rows)


def test_storyboard_ratio_logo_finish_and_quality_back_use_one_owner() -> None:
    handler = _function_source("handle_storyboard_image_callback")
    assert 'if suffix.startswith("qi_ratio_")' in handler
    assert 'if suffix == "qi_logo_skip"' in handler
    assert 'if suffix == "qi_logo_confirm"' in handler
    assert 'if suffix in {"qi_finish_image", "qi_back_ratio"}' in handler
    assert 'set_quick_image_flow(uid, "tier", confirm_token="")' in handler
    assert 'set_quick_image_flow(uid, "prepared_prompt", confirm_token="")' in handler
    assert 'quick_image_prepared_prompt_keyboard(get_user_language(uid) or "vi", state=state)' in handler
    assert 'video_storyboard2.move(board, "assets", push=False, awaiting_input="")' in handler
    assert 'return_to="vstory|image_return"' in _function_source("storyboard2_prepare_quick_image")


def test_storyboard_prompt_explains_finish_quality_invoice_before_generation() -> None:
    source = _function_source("quick_image_prepared_prompt_text")
    for text in ("Hoàn thành ảnh", "chọn chất lượng", "xem hóa đơn", "xác nhận tạo ảnh"):
        assert text in source
    success = _function_source("public_image_success_keyboard")
    assert 'if return_callback == "vstory|image_return"' in success
    assert 'callback_data=return_callback' in success


def test_storyboard_generation_sends_one_image_and_reopens_asset_board() -> None:
    delivery = _function_source("send_generated_image_result")
    assert "context.bot.send_photo" in delivery
    assert "send_media_group" not in delivery

    recorder = _function_source("video_scene3_record_generated_image")
    assert 'target_step == "storyboard2_assets"' in recorder
    assert 'video_storyboard2.assign_image(board, scene_index, slot, record)' in recorder
    assert 'video_storyboard2.move(board, "assets", push=False, awaiting_input="")' in recorder

    confirmation = _function_source("handle_shopaikey_public_image_confirm_delivery_first")
    assert "scene3_return_state = video_scene3_record_generated_image" in confirmation
    assert "panel_text, panel_keyboard = video_scene3_image_handoff_panel(scene3_return_state)" in confirmation
    assert "Ảnh hợp lệ đã được gửi và đưa về đúng phiên Video" in confirmation


def test_storyboard_ai_and_upload_entries_keep_one_non_empty_session() -> None:
    fresh = video_storyboard2.ensure_session(
        video_storyboard2.default_state(),
        "storyboard-session-1",
    )
    assert fresh["storyboard_session_id"] == "storyboard-session-1"
    assert fresh["revision"] == 1
    moved = video_storyboard2.move(fresh, "count", push=True)
    assert moved["storyboard_session_id"] == "storyboard-session-1"

    callback = _function_source("_handle_storyboard2_callback_impl")
    assert 'storyboard2_fresh_board(entry_mode="ai")' in callback
    assert 'storyboard2_fresh_board(entry_mode="existing")' in callback
    assert callback.count("video_storyboard2.default_state()") == 0


def test_storyboard_legacy_empty_session_is_upgraded_but_mismatch_is_blocked() -> None:
    board = video_storyboard2.set_scene_count(video_storyboard2.default_state(), 2)
    saved = {}
    validator = _compiled_function(
        "storyboard_quick_image_owner_valid",
        {
            "storyboard2_state": lambda _context: saved.get("board", board),
            "save_storyboard2_state": lambda _context, value: saved.update(board=value),
            "video_storyboard2": video_storyboard2,
            "_safe_int": lambda value, default=0: int(value or default),
            "uuid": SimpleNamespace(uuid4=lambda: SimpleNamespace(hex="migrated-session")),
        },
    )
    state = {
        "owner": "storyboard_image",
        "flow": "storyboard",
        "product": "storyboard_prompt",
        "return_to": "vstory|image_return",
        "session_id": "",
        "storyboard_scene_index": 1,
        "storyboard_slot": "start",
    }
    assert validator(SimpleNamespace(), state) is True
    assert state["session_id"] == "migrated-session"
    assert saved["board"]["storyboard_session_id"] == "migrated-session"

    mismatched = {**state, "session_id": "older-session"}
    assert validator(SimpleNamespace(), mismatched) is False


def test_storyboard_confirmation_keeps_session_and_rejects_stale_pending_image() -> None:
    fields = _compiled_function(
        "quick_image_video_scene3_confirmation_fields",
        {"_safe_int": lambda value, default=0: int(value or default)},
    )({
        "source_flow": "video_scene3",
        "return_to": "vstory|image_return",
        "return_label": "Ảnh Storyboard",
        "session_id": "storyboard-session-1",
        "storyboard_scene_id": "scene_1",
        "storyboard_scene_index": 1,
        "storyboard_slot": "start",
        "storyboard_prompt_version": 2,
    })
    assert fields["storyboard_session_id"] == "storyboard-session-1"

    board = video_storyboard2.set_scene_count(
        video_storyboard2.ensure_session(video_storyboard2.default_state(), "storyboard-session-1"),
        2,
    )
    validator = _compiled_function(
        "storyboard_pending_image_owner_valid",
        {
            "storyboard2_state": lambda _context: board,
            "_safe_int": lambda value, default=0: int(value or default),
        },
    )
    assert validator(SimpleNamespace(), fields) is True
    assert validator(SimpleNamespace(), {**fields, "storyboard_session_id": "old-session"}) is False

    confirmation = _function_source("handle_shopaikey_public_image_confirm_delivery_first")
    guard_position = confirmation.index("storyboard_pending_image_owner_valid(context, pending)")
    assert guard_position < confirmation.index("create_shopaikey_job(")
    assert guard_position < confirmation.index("shopaikey_preview_final_cost(")
    assert "Bot chưa gọi nguồn tạo ảnh và chưa trừ Xu" in confirmation


def test_image_brightness_is_real_local_pixel_processing() -> None:
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
                "photo_clear_detail": {"brightness": 1.0, "contrast": 1.0, "saturation": 1.0, "sharpness": 1.0, "tone": "neutral"},
                "brightness_only": {"brightness": 1.0, "contrast": 1.0, "saturation": 1.0, "sharpness": 1.0, "tone": "neutral"},
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
            settings={"brightness": percent / 100, "contrast": 1.0, "saturation": 1.0, "sharpness": 1.0},
        )
        assert ok is True and preset == "brightness_only"
        with Image.open(io.BytesIO(payload)) as result:
            means.append(ImageStat.Stat(result.convert("RGB")).mean[0])
    assert means[0] < means[1] < means[2]
    assert means[1] == pytest.approx(100, abs=1)


def test_image_brightness_upload_and_custom_routes_remain_in_brightness_menu() -> None:
    photo = _function_source("handle_image_menu_pending_photo")
    document = _function_source("handle_image_menu_pending_document")
    text = _function_source("handle_image_menu_pending_text")
    callback = _function_source("handle_image_tools_callback")
    for source in (photo, document):
        assert 'if mode == "brightness"' in source
        assert 'image_editor_brightness_keyboard(lang)' in source
    assert 'if action == "image_editor_brightness_custom"' in text
    assert 'preset="brightness_only"' in text
    assert 'if action == "editor_brightness_set"' in callback
    assert 'if action == "editor_brightness_custom"' in callback


def test_video_brightness_validates_and_adds_ffmpeg_filter() -> None:
    plan = video_local_editing.normalize_manual_edit_plan(
        {"input_video": "source.mp4", "brightness_percent": 120},
        source_duration_ms=10_000,
    )
    assert plan["brightness_percent"] == 120
    with pytest.raises(video_local_editing.LocalVideoEditError, match="brightness_invalid"):
        video_local_editing.normalize_manual_edit_plan(
            {"input_video": "source.mp4", "brightness_percent": 201},
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
    assert "eq=brightness=0.100" in " ".join(command)
    assert "Độ sáng 120%" in video_local_editing.public_plan_summary(plan)


def test_video_brightness_callbacks_and_back_are_exact() -> None:
    keyboard = _function_source("video_local_manual_options_keyboard")
    brightness_keyboard = _function_source("video_local_brightness_keyboard")
    callback = _function_source("handle_video_editor_callback")
    pending = _function_source("handle_video_editor_pending_text")
    assert '"videoedit|brightness"' in keyboard
    assert '"videoedit|brightness_set|80"' in brightness_keyboard
    assert '"videoedit|brightness_set|120"' in brightness_keyboard
    assert '"videoedit|brightness_set|100"' in brightness_keyboard
    assert '"videoedit|brightness_custom"' in brightness_keyboard
    assert '"videoedit|options|manual"' in brightness_keyboard
    assert 'if action == "brightness"' in callback
    assert 'if action == "brightness_set"' in callback
    assert 'if action == "brightness_custom"' in callback
    assert 'if step == "await_brightness"' in pending
    assert 'plan["brightness_percent"] = percent' in pending


def test_touched_functions_parse_as_python311_source() -> None:
    for name in (
        "quick_image_prepared_prompt_text",
        "quick_image_prepared_prompt_keyboard",
        "storyboard2_select_ai_image_target",
        "storyboard2_prepare_quick_image",
        "handle_storyboard_image_callback",
        "image_editor_start_text",
        "image_editor_brightness_text",
        "image_editor_brightness_keyboard",
        "process_image_local_editor_bytes",
        "handle_image_tools_callback",
        "handle_image_menu_pending_text",
        "handle_image_menu_pending_photo",
        "handle_image_menu_pending_document",
        "video_local_manual_options_keyboard",
        "video_local_brightness_text",
        "video_local_brightness_keyboard",
        "handle_video_editor_pending_text",
        "handle_video_editor_callback",
    ):
        ast.parse("from __future__ import annotations\n\n" + _function_source(name), filename=f"<{name}>")
