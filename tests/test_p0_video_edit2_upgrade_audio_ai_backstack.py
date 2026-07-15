from __future__ import annotations

from pathlib import Path

import pytest

from services import video_ai_edit_prompt, video_edit_capabilities, video_local_editing


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _between(start: str, end: str) -> str:
    begin = BOT_SOURCE.index(start)
    finish = BOT_SOURCE.index(end, begin)
    return BOT_SOURCE[begin:finish]


def test_edit2_hub_is_compact_and_old_top_level_tools_are_removed() -> None:
    block = _between("def video_edit_hub_text", "def video_edit_info_text")
    assert "Chỉnh sửa / Nâng cấp video" in block
    expected = (
        "videoedit|ai",
        "videoedit|manual",
        "videoedit|restore",
        "videoedit|guide",
    )
    assert all(callback in block for callback in expected)
    for removed_callback in (
        "videoedit|audio",
        "videoedit|timeline",
        "videoedit|effects",
        "videoedit|plan",
    ):
        assert removed_callback not in block
    assert "Đổi kích thước/tỉ lệ" not in block
    assert "Nén/chuyển MP4" not in block
    assert "Thêm phụ đề SRT" not in block
    assert "videoedit|quick|" not in block


def test_edit2_manual_menu_exposes_only_truthful_operations() -> None:
    block = _between("def video_local_manual_options_keyboard", "def video_local_split_options_text")
    for label in (
        "Cắt & chia đoạn",
        "Ghép & sắp xếp",
        "Chỉnh âm thanh",
        "Hiệu ứng & chuyển động",
        "Đổi tốc độ",
        "Xoay / lật",
        "Cắt đầu/cuối",
        "Bỏ đoạn giữa",
        "Chia thành nhiều đoạn",
        "Thêm video để ghép",
        "Đổi thứ tự",
        "Xoay video",
        "Lật video",
    ):
        assert label in block
    assert "Đặt lại thao tác" not in block
    assert "videoedit|reset_manual" not in block
    for removed in ("aspect", "resolution", "volume", "srt", "text_overlay", "logo", "color_preset"):
        assert f'videoedit|{removed}' not in block


def test_edit2_audio_truth_and_volume_choices() -> None:
    mixed = video_edit_capabilities.audio_source_truth({"has_audio": True, "audio_stream_count": 1})
    assert mixed["independently_adjustable"] is False
    assert "đã trộn" in mixed["public_summary"]
    stems = video_edit_capabilities.audio_source_truth(
        {"has_audio": True, "audio_stream_count": 3, "separate_audio_stems": True}
    )
    assert stems["independently_adjustable"] is True

    block = _between("def video_edit_audio_master_keyboard", "VIDEO_EDIT_EFFECT_INTENTS")
    assert all(f'videoedit|audio_set|{percent}' in block for percent in (20, 40, 60, 80, 100))
    assert "videoedit|audio_custom" in block
    for component in ("audio_dialogue", "audio_music", "audio_ambience", "audio_sfx"):
        item = video_edit_capabilities.capability(component)
        assert item["enabled"] is False
        assert "separator" in item["risk_notes"]


def test_edit2_capability_registry_is_complete_and_truthful() -> None:
    assert video_edit_capabilities.validate_capability_catalog() is True
    for item in video_edit_capabilities.CAPABILITIES:
        assert video_edit_capabilities.REQUIRED_CAPABILITY_FIELDS <= set(item)
    assert video_edit_capabilities.capability("aspect_basic_crop")["enabled"] is True
    assert video_edit_capabilities.capability("aspect_keep_frame")["enabled"] is True
    for unavailable in (
        "aspect_subject_tracking",
        "aspect_background_expand",
        "aspect_blur_background",
        "aspect_safe_zone",
        "enhance_upscale",
        "enhance_denoise",
        "enhance_motion_deblur",
        "enhance_stabilize",
        "enhance_frame_interpolation",
        "enhance_old_video",
    ):
        assert video_edit_capabilities.capability(unavailable)["enabled"] is False


def test_edit2_smart_aspect_does_not_claim_unwired_ai_features() -> None:
    block = _between("def video_ai_edit_aspect_method_text", "def video_ai_edit_duration_keyboard")
    assert "aspect_basic_crop" in block
    assert "aspect_keep_frame" in block
    assert "ai_set_aspect_method|aspect_subject_tracking" not in block
    assert "chưa có runtime được kiểm chứng" in block
    assert "không có nút thực thi" in block


def test_edit2_local_restore_selects_only_the_proven_local_operation() -> None:
    block = _between("def video_ai_edit_route_from_state", "def video_ai_edit_prompt_from_state")
    assert 'selected_capability.get("local_or_provider") == "local"' in block
    assert 'route["execution_lane"] = "local"' in block
    assert 'local_plan.update({"denoise": False, "stabilize": False, "audio_normalize": False})' in block
    assert '"enhance_basic_sharpen"' in block
    assert '"enhance_light_color"' in block


def test_edit2_effect_timing_and_remove_are_planning_only() -> None:
    settings = _between("def video_ai_edit_settings_keyboard", "def video_ai_edit_intensity_keyboard")
    assert "videoedit|ai_effect_timing" in settings
    assert "videoedit|ai_remove_effect" in settings
    timing = _between("def video_ai_edit_effect_timing_keyboard", "def video_ai_edit_duration_keyboard")
    assert all(token in timing for token in ("toan_video", "doan_dau", "doan_giua", "doan_cuoi"))
    payload = video_ai_edit_prompt.build_professional_prompt(
        {"profile": {}, "selected_effect_stack": ["subtle_zoom"]},
        user_request="Làm chuyển động nhẹ",
        settings={"aspect_method": "Giữ toàn cảnh có viền", "effect_timing": "đoạn cuối"},
    )
    assert "timing: đoạn cuối" in payload["sections"]["effects"]
    assert "method: Giữ toàn cảnh có viền" in payload["sections"]["aspect_resolution"]
    assert payload["provider_called"] is False


def test_edit2_back_stack_is_contextual() -> None:
    source = _between("def video_ai_edit_entry_back", "def _video_ai_edit_lane_label")
    assert '"effects": "videoedit|effects"' in source
    assert '"manual_effects": "videoedit|manual_effects"' in source
    assert '"restore": "videoedit|restore"' in source
    assert "video_ai_edit_entry_back(state" in source
    local = _between("def video_local_source_summary_keyboard", "def video_local_manual_options_text")
    assert 'entry_context == "timeline"' in local
    assert 'f"videoedit|{parent}"' in local
    guide = _between("def video_edit_guide_keyboard", "def video_edit_legacy_redirect_text")
    assert "videoedit|hub" in guide
    assert "menu|guide" not in guide


def test_edit2_legacy_callbacks_are_read_only_before_normalization() -> None:
    handler = _between("async def handle_video_editor_callback", "async def handle_video_upload_callback")
    early = handler.index('if raw_action == "quick"')
    normalize = handler.index("action = video_editor_normalize_action(raw_action)")
    old_mutating = handler.index('if action == "quick"')
    assert early < normalize < old_mutating
    read_only = handler[early:normalize]
    assert "clear_video_editor_pending" not in read_only
    assert "set_video_editor_pending" not in read_only
    assert "submit" not in read_only.lower()
    for removed in (
        "aspect",
        "resolution",
        "volume",
        "color_preset",
        "text_overlay",
        "logo",
        "srt",
        "compress",
        "reset_manual",
        "cut",
    ):
        assert f'"{removed}"' in read_only


def test_edit2_local_suggestions_are_rule_based_default_off_and_side_effect_free() -> None:
    suggestions = video_edit_capabilities.local_upgrade_suggestions(
        {"width": 640, "height": 360, "fps": 24, "duration": 30, "bytes": 2_000_000, "has_audio": True}
    )
    assert suggestions
    assert all(item["selected"] is False for item in suggestions)
    assert all(item["cost_xu"] == 0 for item in suggestions)
    assert all(item["reason"] and item["risk"] for item in suggestions)
    assert video_edit_capabilities.no_side_effect_plan() == {
        "job_created": False,
        "outbox_created": False,
        "provider_called": False,
        "file_generated": False,
        "wallet_mutated": False,
        "xu_charged": 0,
    }


def test_edit2_volume_plan_supports_fixed_and_custom_levels() -> None:
    for value in (0.2, 0.4, 0.6, 0.8, 1.0, 0.75, 2.0):
        plan = video_local_editing.normalize_manual_edit_plan(
            {"input_video": "source.mp4", "volume": value},
            source_duration_ms=10_000,
        )
        assert plan["volume"] == value
    with pytest.raises(video_local_editing.LocalVideoEditError, match="volume_invalid"):
        video_local_editing.normalize_manual_edit_plan(
            {"input_video": "source.mp4", "volume": 2.01},
            source_duration_ms=10_000,
        )


def test_edit2_final_confirm_handlers_remain_single() -> None:
    handler = _between("async def handle_video_editor_callback", "async def handle_video_upload_callback")
    assert handler.count('if action == "ai_confirm"') == 1
    assert handler.count('if action == "start"') == 1
