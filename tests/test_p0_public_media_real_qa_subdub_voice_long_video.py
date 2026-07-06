import asyncio

import bot
from services import product_progress_status


class DummyUser:
    id = 4242


class DummyMessage:
    chat_id = 777


class DummyQuery:
    from_user = DummyUser()
    message = DummyMessage()


def _state(**overrides):
    current = {
        "source_file_id": "file-live-qa",
        "source_file_unique_id": "unique-live-qa",
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "process_type": bot.VIDEO_SUBTITLE_MODE_DUB,
        "target_language": "Tiếng Việt",
        "voice_style": "Giọng nữ",
        "voice_kind": "default_female",
    }
    current.update(overrides)
    return current


def test_subdub_running_duplicate_returns_in_progress_not_fail():
    state = _state()
    key = bot.subtitle_dub_pipeline_job_key(DummyUser.id, DummyMessage.chat_id, state)
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key, user_id=DummyUser.id, chat_id=DummyMessage.chat_id, mode=bot.VIDEO_SUBTITLE_MODE_DUB)

    result = asyncio.run(bot.execute_video_dubbing_pipeline(DummyQuery(), None, state))

    assert result["ok"] is False
    assert result["in_progress"] is True
    assert result["status"] == "STILL_PROCESSING"
    assert "đang xử lý" in result["text"]
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[key]["terminal_state"] == ""


def test_subdub_delivered_duplicate_returns_already_delivered_not_fail():
    state = _state()
    key = bot.subtitle_dub_pipeline_job_key(DummyUser.id, DummyMessage.chat_id, state)
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key, user_id=DummyUser.id, chat_id=DummyMessage.chat_id, mode=bot.VIDEO_SUBTITLE_MODE_DUB)
    assert bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered", video_delivery_message_id="999")

    result = asyncio.run(bot.execute_video_dubbing_pipeline(DummyQuery(), None, state))

    assert result["ok"] is True
    assert result["already_delivered"] is True
    assert result["terminal_state"] == "delivered"
    assert "Kết quả đã gửi" in result["text"]


def test_subdub_status_polling_reads_memory_job_delivered_100():
    key = "public-media-real-qa-delivered"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    try:
        bot.SUBTITLE_DUB_PIPELINE_JOBS[key] = {
            "job_key": key,
            "job_id": "LIVEQA1234567890",
            "public_job_id": "7388DD5899",
            "user_id": str(DummyUser.id),
            "status": "completed",
            "terminal_state": "delivered",
            "output_sent": True,
            "video_delivery_message_id": "123",
            "updated_at": 9999999999.0,
        }

        job = bot.subdub_progress_job_for_user("#7388dd5899", DummyUser.id)
        text = bot.product_progress_status_from_job_text("subdub", job, "7388DD5899")

        assert job["job_key"] == key
        assert "100%" in text
        assert "Đã gửi kết quả" in text
    finally:
        bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)


def test_product_progress_stage_subdub_uses_lifecycle_state():
    state = product_progress_status.product_progress_stage_from_job(
        "subdub",
        {"status": "running", "lifecycle_state": "transcribing", "progress_percent": ""},
    )

    assert state["current_stage"] == "transcribing"
    assert state["percent"] == 35
    assert "đang xử lý" in state["status_text"].lower()


def test_receipt_after_video_delivery_does_not_repeat_success_caption():
    text = bot.video_dubbing_receipt_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_DUB},
        {"video_delivered": True, "charged": 12, "terminal_state": "delivered"},
    )

    assert "Đã tạo video lồng tiếng thành công" in text
    assert "Kết quả:" in text
    assert "Thời lượng:" in text
    assert "Gói/Giá:" in text
    assert "Đã gửi video" in text
    assert text.count("Đã tạo video") == 1
    assert "lỗi" not in text.lower()


def test_default_female_stale_male_voice_is_not_used(monkeypatch):
    monkeypatch.setattr(bot.minimax_voice_adapter, "validate_provider_voice_id", lambda value: bool(value))
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "female-real-voice")
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "male-real-voice")
    state = _state(voice_id="male-real-voice", selected_voice_id="male-real-voice")

    resolution = bot.resolve_video_dub_tts_voice(1, state)

    assert resolution["ok"] is True
    assert resolution["provider_voice_id"] == "female-real-voice"
    assert resolution["resolved_gender"] == "female"
    assert state["selected_tts_voice_id"] == "female-real-voice"


def test_missing_default_female_voice_does_not_fallback_to_male(monkeypatch):
    monkeypatch.setattr(bot.minimax_voice_adapter, "validate_provider_voice_id", lambda value: bool(value))
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "")
    monkeypatch.setattr(bot, "MINIMAX_DEFAULT_FEMALE_VOICE_ID", "")
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "male-real-voice")
    state = _state(voice_id="male-real-voice", selected_voice_id="male-real-voice")

    resolution = bot.resolve_video_dub_tts_voice(1, state)

    assert resolution["ok"] is False
    assert resolution["provider_voice_id"] == "male-real-voice"
    assert resolution["reason"] == "selected_voice_gender_unavailable"
    assert state.get("selected_tts_voice_id", "") != "male-real-voice"


def test_subdub_duration_limit_supports_real_qa_lengths():
    payload = bot.subdub_duration_audit_payload()

    assert bot.pipeline_duration_limit_seconds(False) >= 300
    assert payload["supports_60s"] is True
    assert payload["supports_180s"] is True
    assert payload["supports_300s"] is True
    assert payload["chunking_enabled"] is False


def test_subdub_job_debug_has_live_qa_fields():
    text = bot.subtitle_dub_debug_text(
        {
            "internal_job_id": "LIVEQA1234567890",
            "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
            "status": "completed",
            "stage": "delivered",
            "lifecycle_state": "delivered",
            "progress_percent": 100,
            "pipeline_attempted": True,
            "input_file_path": r"C:\private\subdub\input.mp4",
            "input_file_exists": True,
            "duration_seconds": 65,
            "duration_limit_seconds": 300,
            "chunking_enabled": False,
            "chunk_count": 0,
            "default_female_configured": True,
            "default_male_configured": True,
            "delivery_attempted": True,
            "delivery_message_id": "999",
            "output_validated": True,
            "final_mp4_path": "/tmp/private/final.mp4",
            "duplicate_delivery_prevented": True,
            "public_error_sent": False,
            "error_sent_after_delivery": False,
        }
    )

    assert "lifecycle state" in text
    assert "chunking enabled" in text
    assert "default female configured" in text
    assert "duplicate delivery prevented" in text
    assert "error sent after delivery" in text
    assert r"C:\private" not in text
    assert "/tmp/private" not in text


def test_public_subdub_progress_copy_no_internal_terms():
    text = bot.product_progress_status_from_job_text(
        "subdub",
        {"job_id": "LIVEQA1234567890", "status": "running", "lifecycle_state": "translating"},
        "LIVEQA1234567890",
    )
    lowered = text.lower()

    assert "provider" not in lowered
    assert "api" not in lowered
    assert "ffmpeg" not in lowered
    assert "handler" not in lowered
    assert "callback" not in lowered
