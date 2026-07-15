import asyncio
from types import SimpleNamespace

import bot


class CaptureBot:
    def __init__(self):
        self.edits = []

    async def edit_message_text(self, **kwargs):
        self.edits.append(dict(kwargs))
        return SimpleNamespace(message_id=kwargs["message_id"], chat_id=kwargs["chat_id"])


class CaptureMessage:
    def __init__(self, chat_id=7070, message_id=8080):
        self.chat_id = chat_id
        self.message_id = message_id
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((str(text), dict(kwargs)))
        return SimpleNamespace(message_id=9000 + len(self.replies), chat_id=self.chat_id)


class CaptureQuery:
    def __init__(self, message, bot_client):
        self.message = message
        self._bot_client = bot_client

    def get_bot(self):
        return self._bot_client


def _fresh_job(key, mode=bot.VIDEO_SUBTITLE_MODE_DUB):
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    acquired, job = bot.acquire_subtitle_dub_pipeline_job(
        key,
        user_id=7070,
        chat_id=7070,
        mode=mode,
        status_panel_message_id="8080",
        status_panel_chat_id="7070",
    )
    assert acquired is True
    return job


def test_terminal_panel_edits_stored_panel_to_full_green_after_real_mp4_delivery():
    key = "terminal-panel-real-video"
    job = _fresh_job(key)
    assert bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        delivery_message_id="8181",
        terminal_artifact_type="video",
        video_delivery_message_id="8181",
    )

    capture_bot = CaptureBot()
    message = CaptureMessage()
    query = CaptureQuery(message, capture_bot)
    result = asyncio.run(
        bot.subdub_finalize_delivered_panel(
            query,
            SimpleNamespace(bot=capture_bot),
            key,
            job["job_id"],
            "vi",
            {"has_video": True, "video_delivery_message_id": "8181"},
        )
    )

    assert result is not None
    assert len(capture_bot.edits) == 1
    edit = capture_bot.edits[0]
    assert edit["chat_id"] == 7070
    assert edit["message_id"] == 8080
    assert "100%" in edit["text"]
    assert "✅ Kiểm tra file" in edit["text"]
    assert "✅ Gửi kết quả" in edit["text"]
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    assert stored["progress_percent"] == 100
    assert stored["panel_final_percent"] == 100
    assert stored["status_panel_terminalized"] is True
    assert stored["status_panel_terminal_edit_method"] == "stored_message_id"


def test_terminal_panel_does_not_fake_success_without_video_delivery_message_id():
    key = "terminal-panel-no-video-message"
    job = _fresh_job(key, bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB)
    capture_bot = CaptureBot()
    message = CaptureMessage()
    query = CaptureQuery(message, capture_bot)

    result = asyncio.run(
        bot.subdub_finalize_delivered_panel(
            query,
            SimpleNamespace(bot=capture_bot),
            key,
            job["job_id"],
            "vi",
            {"has_video": True, "delivery_success": True},
        )
    )

    assert result is None
    assert capture_bot.edits == []
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    assert stored["terminal_state"] == ""
    assert stored["progress_percent"] < 100


def test_success_receipt_is_sent_once_after_confirmed_mp4_delivery():
    key = "terminal-receipt-once"
    job = _fresh_job(key)
    assert bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        delivery_message_id="8282",
        terminal_artifact_type="video",
        video_delivery_message_id="8282",
    )
    message = CaptureMessage()
    capture_bot = CaptureBot()
    query = CaptureQuery(message, capture_bot)
    asyncio.run(
        bot.subdub_finalize_delivered_panel(
            query,
            SimpleNamespace(bot=capture_bot),
            key,
            job["job_id"],
            "vi",
            {"final_mp4_delivered": True, "video_delivery_message_id": "8282"},
        )
    )

    first = asyncio.run(
        bot.subdub_send_success_receipt_once(message, key, "receipt", reply_markup="buttons")
    )
    second = asyncio.run(
        bot.subdub_send_success_receipt_once(message, key, "receipt", reply_markup="buttons")
    )

    assert first is not None
    assert second is None
    assert len(message.replies) == 1
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    assert stored["receipt_sent_once"] is True
    assert stored["receipt_message_id"] == "9001"
    assert stored["duplicate_receipt_prevented"] is True


def test_success_receipt_waits_until_terminal_panel_is_really_green():
    key = "terminal-receipt-waits-for-panel"
    _fresh_job(key)
    assert bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        delivery_message_id="8283",
        terminal_artifact_type="video",
        video_delivery_message_id="8283",
    )
    message = CaptureMessage()

    result = asyncio.run(bot.subdub_send_success_receipt_once(message, key, "receipt"))

    assert result is None
    assert message.replies == []
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    assert stored["receipt_send_state"] == "blocked_until_terminal_panel"
    assert stored["receipt_blocked_reason"] == "terminal_panel_not_confirmed"
    assert stored["receipt_sent_once"] is False


def test_success_receipt_is_blocked_without_confirmed_mp4_delivery():
    key = "terminal-receipt-no-video"
    _fresh_job(key)
    message = CaptureMessage()

    result = asyncio.run(bot.subdub_send_success_receipt_once(message, key, "receipt"))

    assert result is None
    assert message.replies == []
    assert not bot.SUBTITLE_DUB_PIPELINE_JOBS[key].get("receipt_sent_once")


def test_internal_success_flags_are_not_telegram_video_delivery_evidence():
    result = {
        "ok": True,
        "has_video": True,
        "video_delivered": True,
        "final_mp4_delivered": True,
        "delivery_success": True,
        "delivery_succeeded": True,
        "sent_video": 1,
        "sent_video_document": 1,
        "delivery_message_id": "generic-only",
        "telegram_message_id": "generic-only",
    }

    assert bot.subdub_terminal_delivery_evidence(result) == {}
    assert bot.subdub_result_has_delivered_video(result) is False
    assert bot.subdub_registry_terminal_state(result) == "failed_no_charge"


def test_final_video_message_id_wins_over_generic_telegram_message_id():
    result = {
        "ok": True,
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "terminal_state": "delivered",
        "final_mp4_delivered": True,
        "final_video_message_id": "real-video-9101",
        "telegram_message_id": "generic-message-9102",
    }

    evidence = bot.subdub_terminal_delivery_evidence(result)

    assert evidence["is_video"] is True
    assert evidence["message_id"] == "real-video-9101"
    assert bot.subdub_confirmed_video_delivery_message_id(result) == "real-video-9101"


def test_registry_commits_delivered_only_with_lane_specific_telegram_evidence():
    video_result = {
        "ok": True,
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "terminal_state": "delivered",
        "final_mp4_delivered": True,
        "video_delivery_message_id": "real-video-9001",
    }
    srt_result = {
        "ok": True,
        "mode": bot.VIDEO_SUBTITLE_MODE_CREATE,
        "terminal_state": "delivered",
        "terminal_artifact_type": "subtitle",
        "srt_delivery_message_id": "real-srt-9002",
    }

    assert bot.subdub_registry_terminal_state(video_result) == "delivered"
    assert bot.subdub_registry_terminal_state(srt_result) == "delivered"


def test_all_four_video_lanes_finish_full_green_and_send_one_receipt_after_real_message_id():
    modes = (
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    )

    for index, mode in enumerate(modes, start=1):
        key = f"terminal-all-lanes-{index}"
        job = _fresh_job(key, mode)
        delivery_id = str(8300 + index)
        assert bot.mark_subtitle_dub_pipeline_output_sent(
            key,
            terminal_state="delivered",
            delivery_message_id=delivery_id,
            terminal_artifact_type="video",
            video_delivery_message_id=delivery_id,
        )

        capture_bot = CaptureBot()
        message = CaptureMessage()
        query = CaptureQuery(message, capture_bot)
        result = {
            "mode": mode,
            "has_video": True,
            "final_mp4_delivered": True,
            "video_delivery_message_id": delivery_id,
        }

        finalized = asyncio.run(
            bot.subdub_finalize_delivered_panel(
                query,
                SimpleNamespace(bot=capture_bot),
                key,
                job["job_id"],
                "vi",
                result,
            )
        )
        first_receipt = asyncio.run(
            bot.subdub_send_success_receipt_once(message, key, f"receipt-{mode}")
        )
        duplicate_receipt = asyncio.run(
            bot.subdub_send_success_receipt_once(message, key, f"receipt-{mode}")
        )

        assert finalized is not None
        assert len(capture_bot.edits) == 1
        assert "100%" in capture_bot.edits[0]["text"]
        assert "✅ Kiểm tra file" in capture_bot.edits[0]["text"]
        assert "✅ Gửi kết quả" in capture_bot.edits[0]["text"]
        assert first_receipt is not None
        assert duplicate_receipt is None
        assert len(message.replies) == 1
        stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
        assert stored["progress_percent"] == 100
        assert stored["completed_steps"] == bot.subdub_completed_steps_for_lifecycle("delivered", "delivered")
        assert stored["status_panel_terminalized"] is True
        assert stored["receipt_sent_once"] is True


def test_auto_subtitle_srt_delivery_also_finishes_panel_and_receipt_once():
    key = "terminal-auto-subtitle-srt"
    job = _fresh_job(key, bot.VIDEO_SUBTITLE_MODE_CREATE)
    assert bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        delivery_message_id="8401",
        terminal_artifact_type="subtitle",
        srt_delivery_message_id="8401",
    )

    capture_bot = CaptureBot()
    message = CaptureMessage()
    query = CaptureQuery(message, capture_bot)
    result = {
        "mode": bot.VIDEO_SUBTITLE_MODE_CREATE,
        "terminal_artifact_type": "subtitle",
        "srt_delivery_message_id": "8401",
        "final_mp4_delivered": False,
    }

    finalized = asyncio.run(
        bot.subdub_finalize_delivered_panel(
            query,
            SimpleNamespace(bot=capture_bot),
            key,
            job["job_id"],
            "vi",
            result,
        )
    )
    receipt = asyncio.run(
        bot.subdub_send_success_receipt_once(message, key, "auto-subtitle receipt")
    )

    assert finalized is not None
    assert receipt is not None
    assert len(capture_bot.edits) == 1
    assert "100%" in capture_bot.edits[0]["text"]
    assert len(message.replies) == 1
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    assert stored["terminal_artifact_type"] == "subtitle"
    assert stored["srt_delivery_message_id"] == "8401"
    assert stored["final_mp4_delivered"] is False
    assert stored["progress_percent"] == 100
    assert stored["receipt_sent_once"] is True
