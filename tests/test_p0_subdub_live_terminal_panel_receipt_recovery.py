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
    _fresh_job(key)
    assert bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        delivery_message_id="8282",
        terminal_artifact_type="video",
        video_delivery_message_id="8282",
    )
    message = CaptureMessage()

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


def test_success_receipt_is_blocked_without_confirmed_mp4_delivery():
    key = "terminal-receipt-no-video"
    _fresh_job(key)
    message = CaptureMessage()

    result = asyncio.run(bot.subdub_send_success_receipt_once(message, key, "receipt"))

    assert result is None
    assert message.replies == []
    assert not bot.SUBTITLE_DUB_PIPELINE_JOBS[key].get("receipt_sent_once")
