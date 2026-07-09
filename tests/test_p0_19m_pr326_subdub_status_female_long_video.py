import inspect

import bot
from services import product_progress_status


def test_subdub_delivered_video_forces_full_green_progress_panel():
    job = {
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "progress_stage": "validating_output",
        "progress_percent": 65,
        "video_delivery_message_id": "777",
        "final_mp4_delivered": True,
        "delivery_succeeded": True,
        "terminal_public_outcome_type": "success",
        "terminal_public_outcome_sent": True,
    }

    stage = product_progress_status.product_progress_stage_from_job("subdub", job)
    panel = product_progress_status.render_product_progress_panel(
        "subdub",
        "DUBJOB",
        stage.get("current_stage"),
        stage.get("percent"),
        stage.get("terminal_state"),
        completed_steps=stage.get("completed_steps"),
    )

    assert stage["terminal_state"] == "delivered"
    assert stage["percent"] == 100
    assert "✅ Gửi kết quả" in panel
    assert "⬜ Gửi kết quả" not in panel
    assert "TOAN AAS chưa xử lý được video này lúc này" not in panel


def test_dub_delivered_receipt_matches_subtitle_success_structure():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "terminal_state": "delivered",
        "duration": "30 giây",
        "target_language": "Tiếng Việt",
        "selected_voice_gender": "female",
        "resolved_gender": "female",
    }
    result = {
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "job_id": "DUB-326",
        "terminal_state": "delivered",
        "terminal_public_outcome_type": "success",
        "video_delivery_message_id": "778",
        "final_mp4_delivered": True,
        "delivery_succeeded": True,
        "charged_xu": 0,
    }

    text = bot.video_dubbing_receipt_text(state, result, "vi")

    assert "Đã tạo video lồng tiếng thành công" in text
    assert "• Kết quả:" in text
    assert "• Loại:" in text
    assert "• Thời lượng:" in text
    assert "• Giọng:" in text
    assert "• Trạng thái: <b>Đã gửi video</b>" in text
    assert "chưa xử lý được video này" not in text


def test_late_fail_suppression_delivered_branch_sends_panel_and_receipt():
    source = inspect.getsource(bot.handle_video_dubbing_callback)
    branch = source[source.index("if latest_failure_job and subdub_should_suppress_generic_fail_for_active_job"):]

    assert 'subdub_progress_text("delivered"' in branch
    assert "video_dubbing_receipt_text(completed_state, receipt_result, lang)" in branch
    assert "subdub_success_message_id" in branch
    assert "success_sent_count" in branch
    assert "generic_product_failure_suppressed_receipt_sent" in branch


def test_female_voice_request_uses_female_default_not_stale_male(monkeypatch):
    monkeypatch.setattr(bot.minimax_voice_adapter, "validate_provider_voice_id", lambda value: bool(value))
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "female-real-voice")
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "male-real-voice")
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "voice_style": "Giọng nữ",
        "voice_kind": "default_female",
        "voice_id": "male-real-voice",
        "selected_voice_id": "male-real-voice",
    }

    resolution = bot.resolve_video_dub_tts_voice(42, state)

    assert resolution["ok"] is True
    assert resolution["provider_voice_id"] == "female-real-voice"
    assert resolution["resolved_gender"] == "female"
    assert state["selected_tts_voice_id"] == "female-real-voice"


def test_subdub_duration_gate_keeps_300s_supported_without_provider_call():
    payload = bot.subdub_duration_gate_payload({"duration": 300}, {}, is_admin=False)
    over = bot.subdub_duration_gate_payload({"duration": 301}, {}, is_admin=False)

    assert payload["duration_limit_seconds"] >= 300
    assert payload["duration_gate_result"] == "pass_long"
    assert payload["chunking_enabled"] is True
    assert payload["chunk_count"] >= 10
    assert over["duration_gate_result"] == "fail_over_limit"


def test_subtitle_only_ass_preserves_source_cue_timing(monkeypatch):
    monkeypatch.setattr(
        bot,
        "resolve_subdub_subtitle_font",
        lambda style: {"ok": True, "family": "Arial", "path": "", "blocker": ""},
    )
    style = bot.subdub_normalize_style(
        {
            "output_type": "burn",
            "video_width": 1280,
            "video_height": 720,
        }
    )
    ass = bot.subdub_generate_ass_from_srt(
        (
            "1\n00:00:00,000 --> 00:00:03,000\nĐoạn đầu.\n\n"
            "2\n00:00:04,000 --> 00:00:08,000\nĐoạn sau phải bám phụ đề gốc.\n"
        ),
        style,
    )

    assert ass.count("Dialogue:") == 2
    assert "0:00:00.00,0:00:03.00" in ass
    assert "0:00:04.00,0:00:08.00" in ass
