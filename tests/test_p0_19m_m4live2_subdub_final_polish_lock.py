import inspect
import subprocess

import pytest

import bot


VALID_SRT = "1\n00:00:00,000 --> 00:00:02,000\nXin chao ca nha\n"
LONG_SRT = (
    "1\n"
    "00:00:00,000 --> 00:00:06,000\n"
    "Di thi di, roi lan nay cung may la co co hoi o Douyin cua to oi, to da co gang het suc roi.\n"
)
OVERLAP_SRT = (
    "1\n"
    "00:00:00,000 --> 00:00:03,000\n"
    "Cau thu nhat can hien dung nhip.\n\n"
    "2\n"
    "00:00:01,000 --> 00:00:04,000\n"
    "Cau thu hai khong duoc chen hang len cau truoc.\n"
)


def _style_state(mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE, *, width=1280, height=720):
    return {
        "mode": mode,
        "output_type": "burn",
        "video_width": width,
        "video_height": height,
        "subtitle_style_preset": "cover_original",
    }


def _style_fields(ass: str) -> list[str]:
    return next(line for line in ass.splitlines() if line.startswith("Style: Default")).split(",")


def _dialogue_lines(ass: str) -> list[str]:
    return [line for line in ass.splitlines() if line.startswith("Dialogue:")]


def _ass_seconds(value: str) -> float:
    hours, minutes, rest = value.split(":", 2)
    seconds, centis = rest.split(".", 1)
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(centis) / 100.0


def _dialogue_times(ass: str) -> list[tuple[float, float]]:
    result = []
    for line in _dialogue_lines(ass):
        parts = line.split(",", 9)
        result.append((_ass_seconds(parts[1]), _ass_seconds(parts[2])))
    return result


def test_m4live2_subtitle_margin_locked_to_bottom_edge():
    style = bot.subdub_normalize_style(_style_state())
    ass = bot.subdub_generate_ass_from_srt(VALID_SRT, _style_state())
    fields = _style_fields(ass)

    assert style["m4live2_subtitle_bottom_lock"] is True
    assert style["subtitle_alignment"] == "bottom_center"
    assert 4 <= style["subtitle_margin_v_after"] <= 8
    assert int(fields[18]) == 2
    assert int(fields[21]) == style["subtitle_margin_v_after"]
    assert "subtitle_margin_v_effective" in ass


def test_m4live2_subtitle_bottom_box_within_safe_bottom_band():
    ass = bot.subdub_generate_ass_from_srt(VALID_SRT, _style_state())
    fields = _style_fields(ass)

    assert int(fields[21]) <= 6
    assert "; m4live2_subtitle_bottom_lock: yes" in ass


def test_m4live2_subtitle_uses_no_vertical_position_override():
    ass = bot.subdub_generate_ass_from_srt(VALID_SRT, _style_state())

    assert "; subtitle_pos_override_removed: yes" in ass
    assert "\\pos" not in ass
    assert "\\move" not in ass


def test_m4live2_subtitle_wraps_to_max_two_lines_without_losing_text():
    ass = bot.subdub_generate_ass_from_srt(LONG_SRT, _style_state())
    dialogues = _dialogue_lines(ass)

    assert dialogues
    assert all(line.count("\\N") <= 1 for line in dialogues)
    joined = " ".join(line.split(",", 9)[-1].replace("\\N", " ") for line in dialogues)
    assert "Douyin" in joined
    assert "co gang het suc" in joined


def test_m4live2_subtitle_suppresses_overlapping_dialogue_events():
    ass = bot.subdub_generate_ass_from_srt(OVERLAP_SRT, _style_state())
    times = _dialogue_times(ass)

    assert "subtitle_overlap_events_suppressed:" in ass
    assert len(times) >= 2
    for (_prev_start, prev_end), (start, _end) in zip(times, times[1:]):
        assert start >= prev_end


def test_m4live2_subtitle_renderer_only_does_not_touch_pipeline():
    source = inspect.getsource(bot.subdub_generate_ass_from_srt)

    assert "subdub_ass_text_chunks" in source
    assert "prepare_subtitles" not in source
    assert "synthesize_segments" not in source
    assert "run_subdub_pipeline" not in source


def test_m4live2_late_failure_update_after_video_delivery_is_suppressed():
    key = "m4live2-late-fail"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key, user_id=1, chat_id=1, mode=bot.VIDEO_SUBTITLE_MODE_DUB)
    assert bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        terminal_artifact_type="video",
        video_delivery_message_id="501",
        success_message_id="502",
    )

    updated = bot.update_subtitle_dub_pipeline_job(
        key,
        status="failed",
        terminal_state="failed_no_charge",
        lifecycle_state="failed_no_charge",
        current_stage="failed_no_charge",
        terminal_public_outcome_type="failure",
        public_error_sent=True,
        public_failure_sent=True,
        public_error_sent_count=1,
        last_error_safe=bot.subdub_clean_failure_text("vi"),
        pipeline_blocker="late_status_poll",
    )

    assert updated["terminal_state"] == "delivered"
    assert updated["status"] == "completed"
    assert updated["progress_percent"] == 100
    assert updated["terminal_public_outcome_type"] == "success"
    assert updated["late_public_error_suppressed"] is True
    assert updated["public_error_sent"] is False
    assert updated["public_failure_sent"] is False


def _late_failure_after_delivered(mode: str, key: str) -> dict:
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key, user_id=1, chat_id=1, mode=mode)
    assert bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        terminal_artifact_type="video",
        video_delivery_message_id=f"{key}-video",
        success_message_id=f"{key}-success",
    )
    return bot.update_subtitle_dub_pipeline_job(
        key,
        status="failed",
        terminal_state="failed_no_charge",
        terminal_public_outcome_type="failure",
        public_error_sent=True,
        public_failure_sent=True,
        public_error_sent_count=1,
        pipeline_blocker="late_status_poll",
    )


def test_m4live2_dub_mp4_suppresses_late_failure_text():
    updated = _late_failure_after_delivered(bot.VIDEO_SUBTITLE_MODE_DUB, "m4live2-dub-late")

    assert updated["terminal_state"] == "delivered"
    assert updated["terminal_public_outcome_type"] == "success"
    assert updated["late_public_error_suppressed"] is True
    assert updated["public_error_sent"] is False


def test_m4live2_subtitle_dub_mp4_suppresses_late_failure_text():
    updated = _late_failure_after_delivered(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "m4live2-combo-late")

    assert updated["terminal_state"] == "delivered"
    assert updated["terminal_public_outcome_type"] == "success"
    assert updated["late_public_error_suppressed"] is True
    assert updated["public_error_sent"] is False


def test_m4live2_dub_receipt_prefers_sent_video_over_failure_state():
    receipt = bot.video_dubbing_receipt_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "video_duration": 30},
        {
            "terminal_public_outcome_type": "failure",
            "public_error_sent": True,
            "video_delivery_message_id": "601",
            "final_mp4_delivered": True,
            "terminal_state": "delivered",
            "charged_xu": 0,
        },
        "vi",
    )

    assert "Đã tạo video lồng tiếng thành công" in receipt
    assert "chưa xử lý được video" not in receipt
    assert "chưa tạo được video" not in receipt


def test_m4live2_dub_status_goes_full_green_after_delivery():
    text = bot.subdub_progress_text("delivered", "M4LIVE2", "vi")

    assert "Tiến độ: 100%" in text
    assert "✅ Gửi kết quả" in text
    assert "TOAN AAS đang xử lý" not in text.splitlines()[0]


def test_m4live2_subtitle_dub_status_all_green_after_delivery():
    text = bot.subdub_progress_text("delivered", "M4LIVE2COMBO", "vi")

    assert "Tiến độ: 100%" in text
    assert "✅ Nhận video" in text
    assert "✅ Gửi kết quả" in text
    assert "✅ TOAN AAS đã hoàn tất video" in text.splitlines()[0]


def test_m4live2_failure_text_only_when_no_mp4_delivered():
    text = bot.video_dubbing_receipt_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_DUB},
        {"terminal_public_outcome_type": "failure", "public_error_sent": True},
        "vi",
    )

    assert "TOAN AAS chưa tạo được video hoàn chỉnh lúc này" in text
    assert "Hệ thống chưa trừ Xu" in text


def test_m4live2_no_duplicate_terminal_outcome():
    key = "m4live2-no-duplicate"
    first = _late_failure_after_delivered(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, key)
    second = bot.update_subtitle_dub_pipeline_job(
        key,
        status="failed",
        terminal_state="failed_no_charge",
        terminal_public_outcome_type="failure",
        public_error_sent=True,
        public_error_sent_count=1,
    )

    assert first["terminal_public_outcome_type"] == "success"
    assert second["terminal_public_outcome_type"] == "success"
    assert second["terminal_state"] == "delivered"
    assert second["ignored_late_error_count"] >= first["ignored_late_error_count"]


def test_m4live2_female_voice_uses_female_default_not_stale_male():
    state = {
        "voice_kind": "default_female",
        "voice_id": "male-qn-qingse",
        "selected_voice_gender": "female",
        "requested_voice_gender": "female",
    }
    resolution = bot.resolve_video_dub_tts_voice(1, state)

    assert resolution["ok"] is True
    assert resolution["provider_voice_id"] == bot.get_tts_voice_id("default_female")
    assert resolution["selected_voice_gender"] == "female"
    assert resolution["requested_voice_gender"] == "female"
    assert not bot.subdub_voice_gender_conflict(resolution["provider_voice_id"], "female")


def test_m4live2_female_voice_blocks_clean_if_female_config_is_unusable(monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", bot.get_tts_voice_id("default_male"))
    monkeypatch.setattr(bot, "MINIMAX_DEFAULT_FEMALE_VOICE_ID", bot.get_tts_voice_id("default_male"))
    state = {"voice_kind": "default_female", "selected_voice_gender": "female"}

    resolution = bot.resolve_video_dub_tts_voice(1, state)

    assert resolution["ok"] is False
    assert resolution["reason"] == "selected_voice_gender_unavailable"
    assert resolution.get("fallback_used") is False


def test_m4live2_dub_speech_rate_is_slowed_and_cue_based():
    config = bot.subdub_dub_speech_config({"voice_speed": "1.0", "selected_voice_gender": "female"})

    assert 0.85 <= config["dub_speech_rate"] <= 0.92
    assert config["dub_max_speech_rate"] <= 1.05
    assert config["dub_timing_reference"] == "subtitle_cues"
    assert config["dub_max_start_early_ms"] == 0
    assert config["no_male_fallback_when_female_requested"] is True


def test_m4live2_explicit_user_speech_rate_is_preserved():
    config = bot.subdub_dub_speech_config({"voice_speed": "1.5", "selected_voice_gender": "female"})

    assert config["dub_speech_rate"] == 1.5
    assert config["dub_max_speech_rate"] == 1.5
    assert config["dub_timing_reference"] == "subtitle_cues"


def test_m4live2_dub_wrapper_applies_speech_config_without_provider_call():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)

    assert "subdub_dub_speech_config" in source
    assert "kwargs[\"base_speed\"]" in source
    assert "kwargs[\"max_speed\"]" in source
    assert "male_fallback_used" in source


def test_m4live2_dub_audio_not_before_cue_start():
    source = inspect.getsource(bot.build_dub_timeline_audio)

    assert "delay_ms = max(0" in source
    assert "adelay=" in source


def test_m4live2_dub_uses_subtitle_timing_reference():
    config = bot.subdub_dub_speech_config({"voice_kind": "default_female"})

    assert config["dub_timing_reference"] == "subtitle_cues"
    assert config["dub_audio_pacing_applied"] is True


def test_m4live2_subtitle_dub_uses_subtitle_renderer_contract():
    style = bot.subdub_normalize_style(_style_state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB))
    ass = bot.subdub_generate_ass_from_srt(VALID_SRT, _style_state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB))

    assert style["m4live2_subtitle_bottom_lock"] is True
    assert style["subtitle_alignment"] == "bottom_center"
    assert "; subtitle_max_lines: 2" in ass


def test_m4live2_subtitle_dub_no_old_dub_style_override():
    core_source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    renderer_source = inspect.getsource(bot.video_dubbing_render_video)

    assert "m4live1_dub_wrapper_restored" in core_source
    assert "video_dubbing_render_video" in core_source
    assert "subdub_generate_ass_from_srt" in renderer_source
    assert "known_good" not in core_source


def test_m4live2_duration_over_30_uses_long_route_or_clean_block(monkeypatch):
    payload = bot.subdub_duration_gate_payload({"duration": 45}, {}, is_admin=False)

    assert payload["duration_gate_result"] == "pass_long"
    assert payload["over_30_supported"] is True
    assert payload["over_30_route"] == "async"
    assert payload["duration_preflight_done"] is True

    monkeypatch.setattr(bot, "SUBDUB_MAX_DURATION_SECONDS", 40)
    blocked = bot.subdub_duration_gate_payload({"duration": 45}, {}, is_admin=False)
    assert blocked["duration_gate_result"] == "fail_over_limit"
    assert blocked["over_30_route"] == "blocked_clean"
    assert "dài hơn giới hạn" in bot.subdub_duration_over_limit_text("vi")
    assert bot.subdub_duration_over_limit_text("vi") != bot.subdub_clean_failure_text("vi")


def test_m4live2_does_not_touch_locked_runtime_areas():
    output = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True)
    changed = {line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()}
    storage5_allowed = {
        "bot.py",
        "services/storage_migration.py",
        "services/storage_weekly.py",
        "tests/test_p0_storage4_fix_vps_sftp_key_config_raw_private_key_ed25519_backup_db_cleanup.py",
        "tests/test_p0_storage5_weekly_railway_vps_archive_safe_aggressive_cleanup.py",
        "tests/test_p0_cskh1_telegram_business_auto_support_bot.py",
        "tests/test_p0_cskh2_toan_aas_training_data_playbook.py",
        "tests/test_p0_cskh2a_business_arm_mode_without_connection.py",
        "tests/test_p0_cskh3_conversation_brain_natural_replies.py",
        "tests/test_p0_19m_m4live1_subdub_style_renderer_only_and_dub_modes_restore.py",
        "tests/test_p0_19m_m4live2_subdub_final_polish_lock.py",
    }
    if changed <= storage5_allowed and any(
        path.startswith("services/storage_") or path.startswith("tests/test_p0_storage")
        for path in changed
    ):
        return
    allowed = {
        "bot.py",
        "tests/test_p0_19m_m4live2_subdub_final_polish_lock.py",
    }
    assert changed <= allowed

    locked_tokens = (
        "music",
        "suno",
        "video_provider",
        "video_real_render",
        "payos",
        "wallet",
        "pricing",
        "finance",
        "db",
        "webhook",
        "local_worker.py",
        "remote_worker.py",
        "services/subtitle_dub_product_pipeline.py",
    )
    runtime_changed = {path for path in changed if not path.startswith("tests/")}
    assert not any(any(token in path.lower() for token in locked_tokens) for path in runtime_changed)


def test_m4live2_run_subdub_pipeline_contract_unchanged():
    output = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True)
    changed = {line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()}

    assert "services/subtitle_dub_product_pipeline.py" not in changed
    pipeline = __import__("services.subtitle_dub_product_pipeline", fromlist=["run_subdub_pipeline"])
    wrapper_signature = inspect.signature(pipeline.run_subdub_pipeline)
    core_signature = inspect.signature(pipeline.process_subtitle_dub_job)
    wrapper_source = inspect.getsource(pipeline.run_subdub_pipeline)
    assert "kwargs" in wrapper_signature.parameters
    assert "process_subtitle_dub_job" in wrapper_source
    assert "prepare_subtitles" in core_signature.parameters
    assert "render_video" in core_signature.parameters
