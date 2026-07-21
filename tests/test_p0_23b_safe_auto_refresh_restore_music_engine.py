import asyncio
import inspect
from types import SimpleNamespace

import bot
from services import product_progress_status


class FakeBot:
    def __init__(self):
        self.edits = []
        self.sent = []

    async def edit_message_text(self, **kwargs):
        self.edits.append(kwargs)
        return SimpleNamespace(message_id=kwargs.get("message_id"))

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(message_id=999)


def _ctx(fake_bot=None):
    return SimpleNamespace(bot=fake_bot or FakeBot())


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _reset_auto_refresh():
    bot.PROGRESS_AUTO_REFRESH_JOBS.clear()
    bot.PROGRESS_AUTO_REFRESH_TASKS.clear()


def _register_music(monkeypatch, status="submitted", progress=5, product_type="music_bg", job_id="music-job"):
    _reset_auto_refresh()
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {"internal_job_id": job_id, "feature": "music_song" if product_type == "music_song" else "music_suno", "provider_task_id": "task-23b", "status": status, "progress_percent": progress})
    monkeypatch.setattr(bot, "poll_music_suno_async_job", lambda _job_id, **_kwargs: asyncio.sleep(0, result={"ok": False, "status": "PROCESSING", "job": bot.get_engine_async_job(_job_id), "audio_bytes": b""}))
    return bot.progress_auto_refresh_register(
        product_type=product_type,
        job_id=job_id,
        chat_id=230001,
        message_id=42,
        user_id=230001,
        lang="vi",
        context=SimpleNamespace(),
        start_task=False,
    )


def test_p0_23b_does_not_touch_music_engine_core():
    for func in (bot.create_music_suno_async_job, bot.poll_music_suno_async_job, bot.send_music_product_audio_result):
        source = inspect.getsource(func)
        assert "progress_auto_refresh" not in source
        assert "product_progress_status_keyboard" not in source


def test_p0_23b_does_not_touch_suno_provider_call():
    source = inspect.getsource(bot.poll_music_suno_async_job)
    for expected in ("provider_task_id", "download", "save_engine_async_job"):
        assert expected in source
    for forbidden in ("progress_auto_refresh_tick", "send_product_progress_message"):
        assert forbidden not in source


def test_music_generation_confirm_still_uses_locked_engine_path():
    source = inspect.getsource(bot.handle_music_product_confirm)
    assert "execute_engine(" in source
    assert "create_music_pending_submit_job(" in source
    assert "send_product_progress_message(" in source
    assert "send_music_product_audio_result(" in source
    callbacks = _callbacks(bot.product_progress_status_keyboard("music_song", "MUS123"))
    assert "progress|status|music_song|MUS123" in callbacks
    assert "music_quick|showroom|music_ai_status" not in callbacks


def test_music_song_not_stuck_65_when_provider_completed():
    snapshot = bot.progress_auto_refresh_snapshot("music_song", "song-job", job={"internal_job_id": "song-job", "feature": "music_song", "status": "completed", "progress_percent": 100, "output_bytes": 2048})
    assert snapshot["terminal_state"] == ""
    assert snapshot["percent"] == 85
    assert "Kiểm tra file nhạc" in snapshot["text"]


def test_music_song_fail_clean_when_provider_failed():
    snapshot = bot.progress_auto_refresh_snapshot("music_song", "song-job", job={"internal_job_id": "song-job", "feature": "music_song", "status": "failed", "progress_percent": 65, "error_category": "provider_failed"})
    assert snapshot["terminal_state"] == "failed_no_charge"
    assert "TOAN AAS chưa trừ Xu" in snapshot["text"]
    assert "provider" not in snapshot["text"].lower()


def test_music_song_no_fake_success_without_artifact():
    snapshot = bot.progress_auto_refresh_snapshot("music_song", "song-job", job={"internal_job_id": "song-job", "feature": "music_song", "status": "processing", "progress_percent": 65, "output_bytes": 0})
    assert snapshot["terminal_state"] == ""
    assert snapshot["percent"] == 65
    assert "Đã gửi kết quả" not in snapshot["text"]


def test_progress_auto_refresh_reads_status_only(monkeypatch):
    record = _register_music(monkeypatch, status="submitted", progress=5)
    key = record["key"]
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {"internal_job_id": "music-job", "feature": "music_suno", "status": "processing", "progress_percent": 60})
    fake = FakeBot()
    result = asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), key))
    assert result["status"] == "updated"
    assert fake.edits
    assert "Tiến độ: 60%" in fake.edits[-1]["text"]


def test_progress_auto_refresh_does_not_submit_provider(monkeypatch):
    async def fail_async(*args, **kwargs):
        raise AssertionError("auto refresh must not submit provider")

    record = _register_music(monkeypatch, status="processing", progress=60)
    monkeypatch.setattr(bot, "execute_engine", fail_async)
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(), record["key"]))


def test_progress_auto_refresh_does_not_create_new_job(monkeypatch):
    record = _register_music(monkeypatch, status="processing", progress=60)
    monkeypatch.setattr(bot, "create_music_suno_async_job", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no duplicate job")))
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(), record["key"]))


def test_progress_auto_refresh_does_not_charge(monkeypatch):
    record = _register_music(monkeypatch, status="processing", progress=60)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no charge")))
    monkeypatch.setattr(bot, "refund_charged_credit", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no refund path")))
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(), record["key"]))


def test_progress_auto_refresh_edits_existing_message(monkeypatch):
    record = _register_music(monkeypatch, status="submitted", progress=5)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {"internal_job_id": "music-job", "feature": "music_suno", "status": "downloading", "progress_percent": 85})
    fake = FakeBot()
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), record["key"]))
    assert fake.edits[-1]["chat_id"] == 230001
    assert fake.edits[-1]["message_id"] == 42
    assert fake.sent == []


def test_progress_auto_refresh_stops_on_delivered(monkeypatch):
    record = _register_music(monkeypatch, status="submitted", progress=5)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {"internal_job_id": "music-job", "feature": "music_suno", "status": "delivered", "progress_percent": 100, "output_bytes": 2048, "sent_full_at": "now"})
    result = asyncio.run(bot.progress_auto_refresh_tick(_ctx(), record["key"]))
    stored = bot.PROGRESS_AUTO_REFRESH_JOBS[record["key"]]
    assert result["status"] == "updated"
    assert stored["stopped"] is True
    assert stored["terminal_state"] == "delivered"


def test_progress_auto_refresh_stops_on_failed(monkeypatch):
    record = _register_music(monkeypatch, status="submitted", progress=5)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {"internal_job_id": "music-job", "feature": "music_suno", "status": "failed", "progress_percent": 60})
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(), record["key"]))
    stored = bot.PROGRESS_AUTO_REFRESH_JOBS[record["key"]]
    assert stored["stopped"] is True
    assert stored["terminal_state"] == "failed_no_charge"


def test_progress_update_button_still_read_only(monkeypatch):
    async def fail_async(*args, **kwargs):
        raise AssertionError("progress callback must stay read-only")

    class Query:
        data = "progress|status|music_bg|manual-job"
        from_user = SimpleNamespace(id=230003)
        message = SimpleNamespace(chat_id=230003, message_id=12)
        edits = []

        async def answer(self, *args, **kwargs):
            return None

        async def edit_message_text(self, text, **kwargs):
            self.edits.append({"text": text, **kwargs})
            return SimpleNamespace(message_id=12)

    monkeypatch.setattr(bot, "poll_music_suno_async_job", lambda _job_id, **_kwargs: asyncio.sleep(0, result={"ok": False, "status": "PROCESSING", "job": bot.get_engine_async_job(_job_id), "audio_bytes": b""}))
    monkeypatch.setattr(bot, "execute_engine", fail_async)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {"internal_job_id": "manual-job", "feature": "music_suno", "status": "processing", "progress_percent": 60})
    query = Query()
    asyncio.run(bot.handle_product_progress_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert query.edits
    assert "TOAN AAS đang tạo nhạc nền" in query.edits[-1]["text"]


def test_music_auto_refresh_no_duplicate_song(monkeypatch):
    record = _register_music(monkeypatch, status="processing", progress=65, product_type="music_song", job_id="song-job")
    monkeypatch.setattr(bot, "create_music_suno_async_job", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no duplicate song")))
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(), record["key"]))


def test_video_auto_refresh_no_duplicate_render(monkeypatch):
    _reset_auto_refresh()
    bot.FRAME_VIDEO_JOBS["frame-job"] = {"job_id": "frame-job", "user_id": "230004", "status": "running", "progress_percent": 65}
    try:
        record = bot.progress_auto_refresh_register(product_type="frame_video", job_id="frame-job", chat_id=230004, message_id=55, user_id=230004, start_task=False)
        monkeypatch.setattr(bot, "render_frame_video_from_state", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no render")))
        asyncio.run(bot.progress_auto_refresh_tick(_ctx(), record["key"]))
    finally:
        bot.FRAME_VIDEO_JOBS.pop("frame-job", None)


def test_public_progress_no_technical_words(monkeypatch):
    record = _register_music(monkeypatch, status="submitted", progress=5, product_type="music_song")
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {"internal_job_id": "music-job", "feature": "music_song", "status": "failed", "progress_percent": 65, "last_provider_status": "provider RuntimeError traceback"})
    result = asyncio.run(bot.progress_auto_refresh_tick(_ctx(), record["key"]))
    text = result["snapshot"]["text"]
    lowered = text.lower()
    for forbidden in product_progress_status.PUBLIC_TECHNICAL_WORDS:
        assert forbidden not in lowered
