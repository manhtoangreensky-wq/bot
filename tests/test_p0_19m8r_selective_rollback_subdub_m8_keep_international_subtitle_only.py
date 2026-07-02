import inspect
import subprocess
from pathlib import Path

import bot


REPO_ROOT = Path(__file__).resolve().parents[1]


def _changed_files_from_main():
    output = subprocess.check_output(
        ["git", "diff", "--name-only", "origin/main"],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
    )
    return {line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()}


def test_international_language_detection_kept_for_subtitles():
    assert bot.subdub_normalize_language_code("中文") == "zh"
    assert bot.subdub_normalize_language_code("English") == "en"
    assert bot.subdub_detect_language_from_text("你好世界") == "zh"
    assert bot.subdub_detect_language_from_text("Hello world") == "en"
    assert bot.subdub_detect_language_from_text("こんにちは") == "ja"
    assert bot.subdub_detect_language_from_text("안녕하세요") == "ko"
    assert bot.subdub_detect_language_from_text("สวัสดี") == "th"
    assert bot.subdub_detect_language_from_text("Tôi đang dịch phụ đề") == "vi"


def test_subtitle_prepare_exposes_language_metadata_in_return_source():
    source = inspect.getsource(bot.video_dubbing_prepare_subtitles)

    assert "detected_language" in source
    assert "target_language" in source
    assert "source_segment_count" in source
    assert "translated_segment_count" in source
    assert "subdub_detect_language_from_text" in source


def test_risky_m8_long_video_tts_charge_changes_rolled_back():
    core_source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)

    assert not hasattr(bot, "subdub_transcribe_audio_chunks")
    assert not hasattr(bot, "subdub_split_tts_segments")
    assert not hasattr(bot, "subdub_selected_female_voice_unavailable_text")
    assert "PIPELINE_EXCEPTION" not in core_source
    assert "pending_charge_xu" not in core_source
    assert "charge_after_delivery" not in core_source


def test_status_callback_baseline_restored_no_m8_rewrite():
    source = inspect.getsource(bot.handle_video_dubbing_callback)

    assert 'query.answer("Chưa tìm thấy trạng thái xử lý."' in source
    assert "subdub_clean_failure_text" not in source


def test_admin_debug_lookup_kept_without_public_flow_change():
    key = "p019m8r-lookup"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.SUBTITLE_DUB_PIPELINE_JOBS[key] = {
        "job_key": key,
        "job_id": "ABCDEF1234567890ABCD",
        "internal_job_id": "subdub_internal_123",
        "public_job_id": "7388DD5899",
        "user_id": "42",
        "status": "running",
    }

    assert bot.subtitle_dub_debug_lookup_job("7388DD5899")["job_key"] == key
    assert bot.subtitle_dub_debug_lookup_job("#7388DD5899")["job_key"] == key
    assert bot.subtitle_dub_debug_lookup_job("7388dd5899")["job_key"] == key


def test_admin_debug_commands_registered_and_short():
    source = (REPO_ROOT / "bot.py").read_text(encoding="utf-8")
    for command in (
        "subdub_status_debug",
        "subdub_language_debug",
        "subdub_duration_audit",
    ):
        assert f'CommandHandler("{command}"' in source
        assert len(command) <= 32


def test_m8_targeted_test_removed():
    assert not (REPO_ROOT / "tests/test_p0_19m8_real_subdub_baseline_30s_multilingual_female_voice_delivery_fix.py").exists()


def test_only_subdub_files_changed_no_unrelated_modules():
    changed = _changed_files_from_main()

    assert changed <= {
        "bot.py",
        "tests/test_p0_19m8_real_subdub_baseline_30s_multilingual_female_voice_delivery_fix.py",
        "tests/test_p0_19m8r_selective_rollback_subdub_m8_keep_international_subtitle_only.py",
    }
    assert not any(
        token in path.lower()
        for path in changed
        for token in ("payos", "wallet", "payment", "music", "suno", "finance", "pricing", "linkdl")
    )
