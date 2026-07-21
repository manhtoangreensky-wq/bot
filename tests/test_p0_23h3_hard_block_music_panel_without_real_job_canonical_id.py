import asyncio
from types import SimpleNamespace

import bot


class CaptureMessage:
    def __init__(self, chat_id=230503):
        self.chat_id = chat_id
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"text": text, **kwargs})
        return SimpleNamespace(chat_id=self.chat_id, message_id=100 + len(self.outputs))


def _reset():
    bot.PROGRESS_AUTO_REFRESH_JOBS.clear()
    bot.PROGRESS_AUTO_REFRESH_TASKS.clear()
    bot.ENGINE_ASYNC_MEMORY_JOBS.clear()
    bot.MUSIC_PANEL_CREATOR_TRACES.clear()


def test_h3_canonical_music_id_accepts_plain_hyphen_and_hash():
    assert bot.canonical_music_job_id("#MUS-91054179") == "MUS91054179"
    assert bot.canonical_music_job_id("#MUS91054179") == "MUS91054179"
    assert bot.legacy_music_job_id("MUS91054179") == "MUS-91054179"


def test_h3_callback_does_not_truncate_music_job_id():
    callback = bot.product_progress_status.product_progress_update_callback("music_song", "MUS-91054179")
    assert callback == "progress|status|music_song|MUS91054179"


def test_h3_blocks_music_panel_without_real_job(monkeypatch):
    _reset()
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {})
    message = CaptureMessage()
    asyncio.run(bot.send_product_progress_message(
        message,
        SimpleNamespace(),
        product_type="music_song",
        job_id="MUS-91054179",
        current_stage="received_request",
        percent=5,
        start_task=True,
    ))
    assert message.outputs
    assert "TOAN AAS đang tạo bài hát" not in message.outputs[-1]["text"]
    assert "chưa trừ Xu" in message.outputs[-1]["text"]
    assert bot.PROGRESS_AUTO_REFRESH_JOBS == {}
    trace = bot.music_panel_creator_trace("MUS91054179")
    assert trace["blocked"] is True
    assert trace["reason"] == "missing_real_music_job_before_panel"


def test_h3_lookup_plain_finds_legacy_job():
    _reset()
    bot.ENGINE_ASYNC_MEMORY_JOBS["MUS-91054179"] = {"internal_job_id": "MUS-91054179", "feature": "music_suno"}
    lookup = bot.get_engine_async_job_lookup("MUS91054179")
    assert lookup["lookup_found"] is True
    assert lookup["resolved_job_id"] == "MUS-91054179"
