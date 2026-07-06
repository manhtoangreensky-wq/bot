import inspect
import os
import subprocess

import pytest

import bot
from services import product_progress_status


VALID_SRT = "1\n00:00:00,000 --> 00:00:02,000\nXin chao ca nha\n"


def _changed_files() -> set[str]:
    output = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True)
    return {line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()}


def _current_branch_name() -> str:
    for key in ("GITHUB_HEAD_REF", "GITHUB_REF_NAME", "BRANCH_NAME"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    try:
        return subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
    except Exception:
        return ""


def _is_subdub_m6w_scope() -> bool:
    branch = _current_branch_name().lower()
    branch_tokens = (
        "p0-19m6w",
        "p0-19m6y",
        "subdub-emergency-rollback",
        "emergency-selective-rollback-subdub",
        "subdub-pipeline-font-volume-ui",
        "revert-subdub-m6x",
    )
    return any(token in branch for token in branch_tokens)


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def test_dub_only_pipeline_restored_from_pre_231():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)

    assert "SUBDUB_VOLUME_MIX_UI_ENABLED" in source
    assert "video_dubbing_render_video" in source
    assert "kwargs.setdefault(\"original_audio_volume_percent\"" in source
    assert "if SUBDUB_VOLUME_MIX_UI_ENABLED" in source


def test_subtitle_plus_dub_pipeline_restored_from_pre_231():
    source = inspect.getsource(bot.video_dubbing_render_video)

    assert "if not SUBDUB_VOLUME_MIX_UI_ENABLED" in source
    assert "keep_original_audio = False" in source
    assert "dubbed_voice_volume_percent = None" in source


def test_status_steps_have_single_receive_step():
    steps = product_progress_status.product_progress_spec("subdub")["steps"]
    labels = [item["label"] for item in steps if item["key"] != "delivered"]

    assert labels.count("Nhận video") == 1
    assert labels == [
        "Nhận video",
        "Tách âm thanh",
        "Nhận diện lời thoại",
        "Dịch nội dung",
        "Tạo phụ đề / Tạo giọng lồng tiếng",
        "Ghép video",
        "Kiểm tra file",
        "Gửi kết quả",
    ]


def test_dub_status_steps_have_single_receive_step():
    labels = bot.subdub_mode_expected_steps(bot.VIDEO_SUBTITLE_MODE_DUB)

    assert labels.count("Nhận video") == 1


def test_subtitle_plus_dub_status_steps_have_single_receive_step():
    labels = bot.subdub_mode_expected_steps(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB)

    assert labels.count("Nhận video") == 1


def test_status_panel_has_no_duplicate_receive_video():
    text = product_progress_status.render_product_progress_panel(
        "subdub",
        "M6WJOB",
        "received_file",
        5,
        "",
    )

    assert text.count("Nhận video") == 1


def test_no_public_audio_fallback_after_restore():
    assert bot.SUBDUB_PUBLIC_AUDIO_FALLBACK_ENABLED is False


def test_no_fake_success_without_delivered_mp4():
    key = "m6w-no-fake-success"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    acquired, _job = bot.acquire_subtitle_dub_pipeline_job(
        key,
        user_id=19610,
        chat_id=19610,
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
    )
    assert acquired is True

    ok = bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered")
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]

    assert ok is False
    assert stored["terminal_state"] == "failed_no_charge"
    assert stored["success_blocked_reason"] == "missing_valid_delivered_mp4"


def test_final_video_delivery_finalizes_panel_and_report():
    key = "m6w-delivered"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    acquired, _job = bot.acquire_subtitle_dub_pipeline_job(
        key,
        user_id=19611,
        chat_id=19611,
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    )
    assert acquired is True

    ok = bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        delivery_message_id="901",
        terminal_artifact_type="video",
        video_delivery_message_id="901",
    )
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]

    assert ok is True
    assert stored["terminal_state"] == "delivered"
    assert stored["progress_percent"] == 100
    assert stored["terminal_public_outcome_type"] == "success"


def test_subtitle_font_uses_pre_231_baseline_plus_two_responsive():
    style = bot.subdub_normalize_style({
        "subtitle_style_preset": "cover_original",
        "video_width": 1280,
        "video_height": 720,
    })

    assert style["subtitle_style_baseline_source"] == "pre_231"
    assert style["translated_font_size_baseline"] == style["size"]
    assert 1.0 <= style["translated_font_size_multiplier"] <= 1.25
    assert style["translated_font_size_final"] == style["render_size"]
    assert style["render_size"] <= style["subtitle_font_size_before_live_effective"] - 2
    assert style["subtitle_font_size_delta"] <= -2
    assert style["render_size"] <= 48


def test_subtitle_font_not_huge_absolute_hardcoded():
    style = bot.subdub_normalize_style({
        "subtitle_style_preset": "cover_original",
        "video_width": 1280,
        "video_height": 720,
    })

    assert style["render_size"] < 76


def test_subtitle_font_capped_by_video_height():
    style_720 = bot.subdub_normalize_style({"subtitle_style_preset": "cover_original", "video_width": 1280, "video_height": 720})
    style_1080 = bot.subdub_normalize_style({"subtitle_style_preset": "cover_original", "video_width": 1920, "video_height": 1080})

    assert style_720["render_size"] <= 65
    assert style_1080["render_size"] <= 76
    assert style_720["subtitle_font_size_delta"] <= -2


def test_translated_subtitle_wraps_max_two_lines():
    style = bot.subdub_normalize_style({"subtitle_style_preset": "cover_original", "video_width": 1280, "video_height": 720})

    assert style["subtitle_wrap_lines_max"] == 2
    assert style["max_lines"] <= 2


def test_translated_subtitle_does_not_cover_original_subtitle_with_black_bar():
    style = bot.subdub_normalize_style({"subtitle_style_preset": "cover_original", "video_width": 1280, "video_height": 720})

    assert style["cover_height_ratio"] <= 0.06
    assert style["cover_y_ratio"] >= 0.90


def test_vietnamese_glyphs_supported():
    ass = bot.subdub_generate_ass_from_srt(
        "1\n00:00:00,000 --> 00:00:02,000\nXin chào thế giới\n",
        {"subtitle_style_preset": "cover_original", "video_width": 1280, "video_height": 720},
    )

    assert "Xin chào thế giới" in ass


def test_broken_volume_button_grid_replaced_by_split_numeric_layers():
    assert bot.SUBDUB_VOLUME_MIX_UI_ENABLED is True
    assert bot.subdub_audio_mix_available({"mode": bot.VIDEO_SUBTITLE_MODE_DUB}) is True

    keyboard = bot.subdub_audio_mix_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_DUB})
    labels = _labels(keyboard)

    assert labels == ["🔊 Âm thanh gốc", "🎙 Giọng lồng tiếng", "⬅️ Quay lại"]
    assert not any(label.startswith("Gốc ") or label.startswith("Lồng ") for label in labels)


def test_volume_mix_ui_disabled_does_not_affect_dub_pipeline():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)

    disabled_branch = source.split("if SUBDUB_VOLUME_MIX_UI_ENABLED", 1)[1]
    assert "kwargs.setdefault(\"original_audio_mode\", audio_mode)" in disabled_branch


def test_volume_mix_defaults_allow_user_selected_mix():
    mix = bot.subdub_audio_mix_state_fields({
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "keep_original_audio": "1",
        "original_audio_volume_percent": "80",
        "dubbed_voice_volume_percent": "200",
    })

    assert mix["keep_original_audio"] is True
    assert mix["original_audio_volume_percent"] == 80
    assert mix["dubbed_voice_volume_percent"] == 200
    assert mix["audio_mix_mode"] == "keep_original"


def test_no_public_fixed_percentage_grid_with_audio_entry_button():
    dub_labels = _labels(bot.video_dubbing_confirm_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_DUB}))
    combo_labels = _labels(bot.video_dubbing_confirm_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}))

    assert "🎚 Âm thanh" in dub_labels
    assert "🎚 Âm thanh" in combo_labels
    assert not any(label.startswith("Gốc ") or label.startswith("Lồng ") for label in dub_labels + combo_labels)


def test_final_video_success_report_sent_once():
    source = inspect.getsource(bot.handle_video_dubbing_callback)

    assert "subdub_success_message_id" in source
    assert "success_sent_count=max(1" in source


def test_no_failure_after_video_success():
    source = inspect.getsource(bot.execute_video_dubbing_pipeline)

    assert "late_error_suppressed" in source
    assert "subdub_job_blocks_public_fail(current_job)" in source


def test_success_report_has_charge_state():
    text = bot.video_dubbing_receipt_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_DUB},
        {"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "charged": 12, "video_delivery_message_id": "901"},
        "vi",
    )

    assert "Chi phí:" in text
    assert "12 Xu" in text


def test_refresh_after_delivery_keeps_success_state():
    job = {"job_id": "m6w-ok", "terminal_state": "delivered", "progress_stage": "failed_no_charge"}
    text = bot.subdub_job_public_status_text(job, "vi")

    assert "Đã gửi kết quả" in text
    assert "chưa xử lý" not in text.lower()


def test_no_product_video_music_payos_pricing_db_changes():
    if not _is_subdub_m6w_scope():
        pytest.skip("SubDub M6W scope guard is not active for this branch")
    branch = _current_branch_name().lower()
    changed = _changed_files()
    allowed = {
        "bot.py",
        "services/product_progress_status.py",
        "tests/test_p0_19m5_complete_subdub_status_style_dub_voice_audio_delivery_sync.py",
        "tests/test_p0_19m8r_selective_rollback_subdub_m8_keep_international_subtitle_only.py",
        "tests/test_p0_19m6w_subdub_emergency_rollback_pipeline_font_volume_ui.py",
        "tests/test_p0_19m6v_subdub_final_delivery_report_font2x_female_voice_fix.py",
        "tests/test_p0_19m6a_subdub_one_terminal_public_outcome_late_error_duplicate_fix.py",
        "tests/test_p0_19n_subdub_original_voice_retention_volume_mix_controls.py",
        "tests/test_task2_4_public_product_screens.py",
        "tests/test_task2_5_user_ux_confirmation_cleanup.py",
    }

    if "p0-19m6y" not in branch:
        assert changed <= allowed
    forbidden = ("payos", "wallet", "pricing", "finance", "music", "suno", "video_provider", "remote_worker.py", "local_worker.py")
    assert not any(any(token in path.lower() for token in forbidden) for path in changed)


def test_no_large_telegram_duration_gate_changes():
    if "p0-19m6y" in _current_branch_name().lower():
        pytest.skip("M6Y intentionally reverts M6X SubDub pipeline changes")
    changed = _changed_files()

    assert "services/subtitle_dub_product_pipeline.py" not in changed
    assert not any(
        "duration" in path.lower() or "delivery" in path.lower()
        for path in changed
        if path != "bot.py" and not path.startswith("tests/")
    )
