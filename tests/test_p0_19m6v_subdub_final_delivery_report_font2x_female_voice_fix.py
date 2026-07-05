import inspect
import os
import subprocess
from pathlib import Path

import bot


VALID_SRT = "1\n00:00:00,000 --> 00:00:02,000\nXin chào cả nhà\n"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _branch_name():
    for key in ("GITHUB_HEAD_REF", "GITHUB_REF_NAME", "BRANCH_NAME"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    try:
        return subprocess.check_output(["git", "branch", "--show-current"], text=True, encoding="utf-8").strip()
    except Exception:
        return ""


def test_translated_subtitle_font_size_is_doubled_and_uses_video_play_res():
    style = bot.subdub_normalize_style({
        "subtitle_style_preset": "cover_original",
        "video_width": 1280,
        "video_height": 720,
    })
    ass = bot.subdub_generate_ass_from_srt(VALID_SRT, style)

    assert style["subtitle_font_multiplier"] == 2.0
    assert style["render_size"] <= 48
    assert style["font_size_cap_applied"] is True
    assert "PlayResX: 1280" in ass
    assert "PlayResY: 720" in ass
    assert f",{style['render_size']}," in ass


def test_female_voice_payload_and_resolver_lock_voice_engine_default(monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "female-real-voice")
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "male-real-voice")

    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        **bot.video_dubbing_voice_payload("default_female", None, "vi"),
    }
    resolved = bot.resolve_video_dub_tts_voice_id(19061, state)

    assert resolved == "female-real-voice"
    assert state["requested_voice_gender"] == "female"
    assert state["selected_voice_gender"] == "female"
    assert state["tts_payload_voice_id"] == "female-real-voice"
    assert state["voice_fallback_used"] is False


def test_success_mark_with_video_delivery_keeps_delivered_terminal(monkeypatch):
    monkeypatch.setattr(bot, "persist_subtitle_dub_pipeline_job_snapshot", lambda *_args, **_kwargs: True)
    key = "p019m6v-delivered"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    acquired, _job = bot.acquire_subtitle_dub_pipeline_job(
        key,
        user_id=19062,
        chat_id=19062,
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    )
    assert acquired is True

    ok = bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        delivery_message_id="501",
        terminal_artifact_type="video",
        video_delivery_message_id="501",
    )
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]

    assert ok is True
    assert stored["terminal_state"] == "delivered"
    assert stored["progress_percent"] == 100
    assert stored["terminal_public_outcome_type"] == "success"
    assert stored.get("success_blocked_reason", "") == ""


def test_pipeline_wrapper_passes_delivery_ids_to_terminal_mark():
    source = inspect.getsource(bot.execute_video_dubbing_pipeline)

    assert "video_delivery_message_id=str(result.get(\"video_delivery_message_id\")" in source
    assert "audio_delivery_message_id=str(result.get(\"audio_delivery_message_id\")" in source
    assert "srt_delivery_message_id=str(result.get(\"srt_delivery_message_id\")" in source


def test_final_receipt_after_video_delivery_is_success_not_failure():
    text = bot.video_dubbing_receipt_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB},
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            "terminal_state": "delivered",
            "video_delivery_message_id": "777",
            "charged": 12,
        },
        "vi",
    )

    assert "Kết quả đã gửi phía trên" in text
    assert "chưa xử lý được" not in text
    assert "lỗi" not in text.lower()


def test_success_after_public_failure_is_blocked_with_debug_flag():
    source = (REPO_ROOT / "bot.py").read_text(encoding="utf-8")

    assert "success_after_public_failure_prevented" in source
    assert "success_after_public_failure_video_message_id" in source


def test_no_music_video_generation_payos_pricing_db_changes():
    branch = _branch_name().lower()
    if "p0-19m6v" not in branch and "subdub-final-report" not in branch:
        return

    output = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True)
    changed = {line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()}
    allowed = {
        "bot.py",
        "services/subtitle_dub_product_pipeline.py",
        "tests/test_p0_19m6a_subdub_one_terminal_public_outcome_late_error_duplicate_fix.py",
        "tests/test_p0_19m6u_subdub_input_save_failed_terminalization_debug_progress_fix.py",
        "tests/test_p0_19m6v_subdub_final_delivery_report_font2x_female_voice_fix.py",
        "tests/test_p0_19n_subdub_original_voice_retention_volume_mix_controls.py",
        "tests/test_task2_1_translation_product_logic_cleanup.py",
        "tests/test_task2_4_public_product_screens.py",
        "tests/test_task2_5_user_ux_confirmation_cleanup.py",
        "tests/test_p0_19m6x_subdub_remove_public_srt_fallback_subtitle_style_dub_speed.py",
    }
    assert changed <= allowed
