import asyncio
from types import SimpleNamespace

import bot


class FakeBot:
    def __init__(self):
        self.edits = []
        self.sent = []
        self.audio = []

    async def edit_message_text(self, **kwargs):
        self.edits.append(kwargs)
        return SimpleNamespace(message_id=kwargs.get("message_id"))

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(message_id=7000 + len(self.sent))

    async def send_audio(self, **kwargs):
        self.audio.append(kwargs)
        return SimpleNamespace(message_id=8000 + len(self.audio), audio=SimpleNamespace(file_id=f"file-{len(self.audio)}"))


class CaptureMessage:
    def __init__(self, user_id=230501):
        self.chat_id = user_id
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"kind": "text", "text": text, **kwargs})
        return SimpleNamespace(chat_id=self.chat_id, message_id=len(self.outputs))

    async def reply_audio(self, audio=None, filename="", caption="", **kwargs):
        self.outputs.append({"kind": "audio", "audio": audio, "filename": filename, "caption": caption, **kwargs})
        return SimpleNamespace(message_id=len(self.outputs), audio=SimpleNamespace(file_id=f"audio-{len(self.outputs)}"))


class CaptureQuery:
    def __init__(self, data, user_id=230501):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = CaptureMessage(user_id)
        self.answers = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append({"text": text, **kwargs})
        return SimpleNamespace(message_id=1)


def _ctx(fake_bot=None):
    return SimpleNamespace(bot=fake_bot or FakeBot())


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _music_result(user_id=230501, mode="background"):
    return {
        "music_product_flow": "p0_20b1_suggestions",
        "music_product_mode": mode,
        "music_product_tier": "music_tier_basic",
        "music_user_idea": "Nhạc quảng cáo vui tươi",
        "provider_style_prompt": "bright pop",
        "provider_lyrics": "TOAN AAS",
    }


def _reset_auto_refresh():
    bot.PROGRESS_AUTO_REFRESH_JOBS.clear()
    bot.PROGRESS_AUTO_REFRESH_TASKS.clear()


def _completed_music_job(job_id="MUS-AUTO"):
    return {
        "internal_job_id": job_id,
        "feature": "music_suno",
        "product_type": "music_song",
        "music_product_mode": "song",
        "music_product_tier": "music_tier_premium",
        "song_vocal": "female",
        "user_id": "230501",
        "chat_id": "230501",
        "provider": "key4u_suno",
        "provider_task_id": "provider-task-auto",
        "provider_job_id": "provider-task-auto",
        "status": "completed",
        "progress_percent": 85,
        "output_bytes": 4096,
        "artifact_duration_seconds": 33,
        "music_result_duration_seconds": 33,
        "output_sha256": "sha-auto",
    }


def _patch_auto_delivery_ready(monkeypatch, job_id="MUS-AUTO", audio=b"real-mp3-bytes"):
    state = {"job": _completed_music_job(job_id), "charges": 0, "saves": []}

    async def fake_poll(_job_id, **_kwargs):
        job = dict(state["job"])
        return {"ok": True, "status": "COMPLETED", "job": job, "audio_bytes": audio}

    def fake_save(payload):
        state["job"] = dict(payload)
        state["saves"].append(dict(payload))
        return dict(payload)

    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: dict(state["job"]) if _job_id == job_id else {})
    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)
    monkeypatch.setattr(bot, "poll_music_suno_async_job", fake_poll)
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: True)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("admin should not charge")))
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **kwargs: {"vault_id": "MV-AUTO", "storage_ref": ""})
    monkeypatch.setattr(bot, "get_music_vault_entry", lambda _vault_id: {})
    monkeypatch.setattr(bot, "find_music_vault_entry_for_job", lambda _job: {})
    return state


def test_music_panel_removes_check_send_result_row():
    labels = _labels(bot.product_progress_status_keyboard("music_song", "MUS123"))
    assert "🔎 Kiểm tra/gửi kết quả" not in labels


def test_music_panel_keeps_update_status_button():
    labels = _labels(bot.product_progress_status_keyboard("music_bg", "MUS123"))
    assert "🔄 Cập nhật trạng thái" in labels


def test_music_panel_has_only_two_action_rows():
    assert len(bot.product_progress_status_keyboard("music_song", "MUS123").inline_keyboard) == 2


def test_music_confirm_submits_provider_after_final_confirm(monkeypatch):
    calls = []

    async def fake_execute(feature, params, context):
        calls.append((feature, params, context))
        return {"ok": True, "provider_result": {"ok": True, "provider": "key4u_suno", "task_id": "task-23c"}}

    monkeypatch.setattr(bot, "get_user", lambda uid: (999, None, None))
    monkeypatch.setattr(bot, "can_user_access_product_engine", lambda *args, **kwargs: {"allowed": True})
    monkeypatch.setattr(bot, "execute_engine", fake_execute)
    monkeypatch.setattr(bot, "create_music_suno_async_job", lambda **kwargs: {"internal_job_id": "MUS-CONFIRM"})
    monkeypatch.setattr(bot, "music_product_auto_deliver_job", lambda *args, **kwargs: asyncio.sleep(0, result={"ok": False, "status": "PROCESSING"}))
    query = CaptureQuery("music_quick|showroom|music_ai_confirm")
    asyncio.run(bot.handle_music_product_confirm(query, SimpleNamespace(), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_music_result()))
    assert calls
    assert calls[0][2]["confirm_paid"] is True


def test_music_confirm_saves_provider_job_id(monkeypatch):
    saved = {}
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: saved.setdefault("payload", dict(payload)) or payload)
    bot.create_music_suno_async_job(user_id=1, chat_id=1, provider="key4u_suno", task_id="provider-real-1", result=_music_result(), status="submitted")
    assert saved["payload"]["provider_task_id"] == "provider-real-1"
    assert saved["payload"]["provider_job_id"] == "provider-real-1"


def test_music_missing_provider_job_fails_no_charge_not_65_stuck():
    snapshot = bot.progress_auto_refresh_snapshot("music_song", "MUS-MISSING", job={"internal_job_id": "MUS-MISSING", "provider": "key4u_suno", "status": "processing", "progress_percent": 65})
    assert snapshot["terminal_state"] == "failed_no_charge"
    assert snapshot["percent"] != 65
    assert "Đã gửi kết quả" not in snapshot["text"]


def test_music_provider_processing_keeps_progress_without_success():
    snapshot = bot.progress_auto_refresh_snapshot("music_song", "MUS-PROC", job={"internal_job_id": "MUS-PROC", "provider_task_id": "task-1", "status": "processing", "progress_percent": 65})
    assert snapshot["terminal_state"] == ""
    assert snapshot["percent"] == 65
    assert "Đã gửi kết quả" not in snapshot["text"]


def test_music_provider_completed_downloads_and_validates_artifact(monkeypatch):
    saved = {}
    job = {"internal_job_id": "MUS-DONE", "feature": "music_suno", "provider": "key4u_suno", "provider_task_id": "task-ok", "status": "submitted", "output_bytes": 0}

    async def fake_poll(_state, updated_by=""):
        return {"ok": True, "status": "SUCCESS", "output_url": "https://cdn.test/song.mp3"}

    async def fake_download(_url, timeout_seconds=60.0):
        return b"real-audio-bytes", "http=200; bytes=16; content_type=audio/mpeg", 200

    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: dict(saved or job))
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: saved.clear() or saved.update(payload) or payload)
    monkeypatch.setattr(bot, "poll_music_generation_job", fake_poll)
    monkeypatch.setattr(bot, "_download_music_audio_url_bytes", fake_download)
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **kwargs: {"vault_id": "MV23C", "storage_ref": ""})
    result = asyncio.run(bot.poll_music_suno_async_job("MUS-DONE", download=True))
    assert result["ok"] is True
    assert saved["status"] == "completed"
    assert saved["output_bytes"] == len(b"real-audio-bytes")


def test_music_artifact_bytes_required_before_success():
    snapshot = bot.progress_auto_refresh_snapshot("music_song", "MUS-NOBYTES", job={"internal_job_id": "MUS-NOBYTES", "status": "completed", "progress_percent": 100, "output_bytes": 0})
    assert snapshot["terminal_state"] != "delivered"


def test_music_artifact_duration_required_before_success(monkeypatch):
    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", lambda *args, **kwargs: asyncio.sleep(0, result=0))
    message = CaptureMessage()
    result = asyncio.run(bot.send_music_product_audio_result(message, SimpleNamespace(), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_music_result(), audio_bytes=b"real-audio"))
    assert result["status"] == "AUDIO_DURATION_MISSING"
    assert not message.outputs


def test_music_progress_registry_saved_when_panel_sent():
    _reset_auto_refresh()
    record = bot.progress_auto_refresh_register(product_type="music_song", job_id="MUS-REG", chat_id=1, message_id=2, user_id=3, start_task=False)
    assert record["job_id"] == "MUS-REG"
    assert record["product_type"] == "music_song"
    assert record["last_render_hash"]


def test_music_auto_refresh_schedules_tick(monkeypatch):
    _reset_auto_refresh()
    calls = []
    monkeypatch.setattr(bot, "progress_auto_refresh_start_task", lambda context, key: calls.append(key) or True)
    bot.progress_auto_refresh_register(product_type="music_bg", job_id="MUS-SCHEDULE", chat_id=1, message_id=2, context=SimpleNamespace(), start_task=True)
    assert calls == ["music_bg:MUS-SCHEDULE"]


def test_music_auto_refresh_edits_existing_panel(monkeypatch):
    _reset_auto_refresh()
    record = bot.progress_auto_refresh_register(product_type="music_bg", job_id="MUS-EDIT", chat_id=1, message_id=2, start_task=False)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {"internal_job_id": "MUS-EDIT", "provider_task_id": "task", "status": "processing", "progress_percent": 60})
    monkeypatch.setattr(bot, "poll_music_suno_async_job", lambda _job_id, **_kwargs: asyncio.sleep(0, result={"ok": False, "status": "PROCESSING", "job": bot.get_engine_async_job(_job_id), "audio_bytes": b""}))
    fake = FakeBot()
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), record["key"]))
    assert fake.edits
    assert fake.edits[-1]["message_id"] == 2


def test_music_auto_refresh_stops_on_delivered(monkeypatch):
    _reset_auto_refresh()
    record = bot.progress_auto_refresh_register(product_type="music_bg", job_id="MUS-DELIV", chat_id=1, message_id=2, start_task=False)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {"internal_job_id": "MUS-DELIV", "status": "delivered", "output_bytes": 5})
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(), record["key"]))
    assert bot.PROGRESS_AUTO_REFRESH_JOBS[record["key"]]["stopped"] is True


def test_music_auto_refresh_stops_on_failed(monkeypatch):
    _reset_auto_refresh()
    record = bot.progress_auto_refresh_register(product_type="music_bg", job_id="MUS-FAIL", chat_id=1, message_id=2, start_task=False)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {"internal_job_id": "MUS-FAIL", "status": "failed", "error_category": "provider_failed"})
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(), record["key"]))
    assert bot.PROGRESS_AUTO_REFRESH_JOBS[record["key"]]["terminal_state"] == "failed_no_charge"


def test_music_auto_refresh_does_not_submit_provider(monkeypatch):
    _reset_auto_refresh()
    record = bot.progress_auto_refresh_register(product_type="music_bg", job_id="MUS-NOSUBMIT", chat_id=1, message_id=2, start_task=False)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {"internal_job_id": "MUS-NOSUBMIT", "status": "processing", "provider_task_id": ""})
    monkeypatch.setattr(bot, "execute_engine", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no submit")))
    monkeypatch.setattr(bot, "create_music_suno_async_job", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no new job")))
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(), record["key"]))


def test_music_auto_refresh_does_not_send_audio_before_ready(monkeypatch):
    _reset_auto_refresh()
    record = bot.progress_auto_refresh_register(product_type="music_bg", job_id="MUS-NOAUDIO", chat_id=1, message_id=2, start_task=False)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {"internal_job_id": "MUS-NOAUDIO", "status": "processing", "provider_task_id": ""})
    monkeypatch.setattr(bot, "send_music_product_audio_result", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no audio send")))
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(), record["key"]))


def test_music_auto_refresh_does_not_send_success_before_ready(monkeypatch):
    _reset_auto_refresh()
    record = bot.progress_auto_refresh_register(product_type="music_bg", job_id="MUS-NOSUCCESS", chat_id=1, message_id=2, start_task=False)
    fake = FakeBot()
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {"internal_job_id": "MUS-NOSUCCESS", "status": "processing", "provider_task_id": ""})
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), record["key"]))
    assert not fake.sent
    assert not fake.audio


def test_progress_auto_refresh_status_finds_music_registry():
    _reset_auto_refresh()
    bot.progress_auto_refresh_register(product_type="music_song", job_id="MUS-STATUS", chat_id=1, message_id=2, start_task=False)
    assert "MUS-STATUS" in bot.progress_auto_refresh_status_text("MUS-STATUS")


def test_music_completed_artifact_auto_delivers_without_user_click(monkeypatch):
    _reset_auto_refresh()
    _patch_auto_delivery_ready(monkeypatch, "MUS-AUTO1")
    record = bot.progress_auto_refresh_register(product_type="music_song", job_id="MUS-AUTO1", chat_id=230501, message_id=9, user_id=230501, start_task=False)
    fake = FakeBot()
    result = asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), record["key"]))
    assert len(fake.audio) == 1
    assert len(fake.sent) == 1
    assert result["snapshot"]["terminal_state"] == "delivered"


def test_music_auto_delivery_sends_audio_once(monkeypatch):
    _reset_auto_refresh()
    _patch_auto_delivery_ready(monkeypatch, "MUS-AUTO2")
    record = bot.progress_auto_refresh_register(product_type="music_song", job_id="MUS-AUTO2", chat_id=230501, message_id=9, user_id=230501, start_task=False)
    fake = FakeBot()
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), record["key"]))
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), record["key"]))
    assert len(fake.audio) == 1


def test_music_auto_delivery_sends_success_once(monkeypatch):
    _reset_auto_refresh()
    _patch_auto_delivery_ready(monkeypatch, "MUS-AUTO3")
    record = bot.progress_auto_refresh_register(product_type="music_song", job_id="MUS-AUTO3", chat_id=230501, message_id=9, user_id=230501, start_task=False)
    fake = FakeBot()
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), record["key"]))
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), record["key"]))
    assert len(fake.sent) == 1
    assert "Đã tạo nhạc thành công" in fake.sent[0]["text"]


def test_music_auto_delivery_updates_panel_to_100(monkeypatch):
    _reset_auto_refresh()
    _patch_auto_delivery_ready(monkeypatch, "MUS-AUTO4")
    record = bot.progress_auto_refresh_register(product_type="music_song", job_id="MUS-AUTO4", chat_id=230501, message_id=9, user_id=230501, start_task=False)
    fake = FakeBot()
    result = asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), record["key"]))
    assert "Tiến độ: 100%" in fake.edits[-1]["text"]
    assert "Đã gửi file nhạc" in fake.edits[-1]["text"]
    assert result["snapshot"]["percent"] == 100


def test_music_auto_delivery_removes_need_for_check_send_button():
    callbacks = _callbacks(bot.product_progress_status_keyboard("music_song", "MUS-AUTO5"))
    assert "music_quick|showroom|music_ai_status" not in callbacks


def test_music_manual_update_is_fallback_not_required(monkeypatch):
    _reset_auto_refresh()
    _patch_auto_delivery_ready(monkeypatch, "MUS-AUTO6")
    record = bot.progress_auto_refresh_register(product_type="music_song", job_id="MUS-AUTO6", chat_id=230501, message_id=9, user_id=230501, start_task=False)
    fake = FakeBot()
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), record["key"]))
    assert fake.audio
    assert fake.sent


def test_music_manual_update_after_auto_delivery_does_not_resend(monkeypatch):
    state = _patch_auto_delivery_ready(monkeypatch, "MUS-AUTO7")
    _reset_auto_refresh()
    record = bot.progress_auto_refresh_register(product_type="music_song", job_id="MUS-AUTO7", chat_id=230501, message_id=9, user_id=230501, start_task=False)
    fake = FakeBot()
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), record["key"]))
    query = CaptureQuery("progress|status|music_song|MUS-AUTO7")
    asyncio.run(bot.handle_product_progress_callback(SimpleNamespace(callback_query=query), _ctx(fake)))
    assert state["job"]["terminal_state"] == "delivered"
    assert len(fake.audio) == 1
    assert len(fake.sent) == 1


def test_music_detailed_success_not_duplicated_by_plain_success(monkeypatch):
    _reset_auto_refresh()
    _patch_auto_delivery_ready(monkeypatch, "MUS-AUTO8")
    record = bot.progress_auto_refresh_register(product_type="music_song", job_id="MUS-AUTO8", chat_id=230501, message_id=9, user_id=230501, start_task=False)
    fake = FakeBot()
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), record["key"]))
    success_texts = [item["text"] for item in fake.sent if "Đã tạo nhạc thành công" in item["text"]]
    assert len(success_texts) == 1
    assert not any((item.get("caption") or "").startswith("✅") for item in fake.audio)


def test_music_panel_not_stuck_65_after_artifact_ready(monkeypatch):
    _reset_auto_refresh()
    _patch_auto_delivery_ready(monkeypatch, "MUS-AUTO9")
    record = bot.progress_auto_refresh_register(product_type="music_song", job_id="MUS-AUTO9", chat_id=230501, message_id=9, user_id=230501, initial_snapshot={"stage": "generating_song", "percent": 65, "terminal_state": "", "text": "Tiến độ: 65%", "render_hash": "old"}, start_task=False)
    fake = FakeBot()
    result = asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), record["key"]))
    assert result["snapshot"]["percent"] == 100
    assert "Tiến độ: 65%" not in fake.edits[-1]["text"]


def test_music_background_tick_can_deliver_completed_artifact(monkeypatch):
    state = _patch_auto_delivery_ready(monkeypatch, "MUS-BG1")
    state["job"]["product_type"] = "music_bg"
    state["job"]["music_product_mode"] = "background"
    _reset_auto_refresh()
    record = bot.progress_auto_refresh_register(product_type="music_bg", job_id="MUS-BG1", chat_id=230501, message_id=9, user_id=230501, start_task=False)
    fake = FakeBot()
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), record["key"]))
    assert len(fake.audio) == 1
    assert "Nhạc nền" in fake.sent[0]["text"]


def test_music_auto_delivery_does_not_submit_provider_again(monkeypatch):
    _reset_auto_refresh()
    _patch_auto_delivery_ready(monkeypatch, "MUS-AUTO10")
    monkeypatch.setattr(bot, "execute_engine", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no provider submit")))
    monkeypatch.setattr(bot, "create_music_suno_async_job", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no new job")))
    record = bot.progress_auto_refresh_register(product_type="music_song", job_id="MUS-AUTO10", chat_id=230501, message_id=9, user_id=230501, start_task=False)
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(FakeBot()), record["key"]))


def test_music_auto_delivery_does_not_charge_twice(monkeypatch):
    _reset_auto_refresh()
    state = _patch_auto_delivery_ready(monkeypatch, "MUS-AUTO11")
    charges = []
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: False)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: charges.append(args) or {"ok": True, "final_cost": 300})
    record = bot.progress_auto_refresh_register(product_type="music_song", job_id="MUS-AUTO11", chat_id=230501, message_id=9, user_id=230501, start_task=False)
    fake = FakeBot()
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), record["key"]))
    asyncio.run(bot.progress_auto_refresh_tick(_ctx(fake), record["key"]))
    assert len(charges) == 1
    assert state["job"]["charged_xu"] == 300


def test_music_update_status_polls_existing_provider_job_only(monkeypatch):
    calls = []
    job = {"internal_job_id": "MUS-POLL", "provider_task_id": "task-poll", "provider": "key4u_suno", "status": "processing", "output_bytes": 0}
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: dict(job))
    monkeypatch.setattr(bot, "poll_music_suno_async_job", lambda job_id, **kwargs: calls.append(job_id) or asyncio.sleep(0, result={"ok": False, "status": "PROCESSING", "job": job, "audio_bytes": b""}))
    query = CaptureQuery("progress|status|music_bg|MUS-POLL")
    asyncio.run(bot.handle_product_progress_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert calls == ["MUS-POLL"]


def test_music_update_status_does_not_create_new_job(monkeypatch):
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {"internal_job_id": "MUS-NONEW", "provider_task_id": "", "status": "processing"})
    monkeypatch.setattr(bot, "create_music_suno_async_job", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no new job")))
    query = CaptureQuery("progress|status|music_bg|MUS-NONEW")
    asyncio.run(bot.handle_product_progress_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))


def test_music_update_status_does_not_submit_provider_again(monkeypatch):
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {"internal_job_id": "MUS-NOSUBMIT2", "provider_task_id": "", "status": "processing"})
    monkeypatch.setattr(bot, "execute_engine", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no submit again")))
    query = CaptureQuery("progress|status|music_bg|MUS-NOSUBMIT2")
    asyncio.run(bot.handle_product_progress_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))


def test_music_update_status_no_duplicate_delivery_after_delivered(monkeypatch):
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {"internal_job_id": "MUS-SENT", "status": "delivered", "sent_full_at": "now", "output_file_id": "file"})
    monkeypatch.setattr(bot, "send_music_product_audio_result", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no duplicate delivery")))
    query = CaptureQuery("progress|status|music_bg|MUS-SENT")
    asyncio.run(bot.handle_product_progress_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))


def test_music_update_status_does_not_reset_percent(monkeypatch):
    _reset_auto_refresh()
    record = bot.progress_auto_refresh_register(product_type="music_bg", job_id="MUS-NORESET", chat_id=1, message_id=2, initial_snapshot={"stage": "generating_music", "percent": 80, "terminal_state": "", "text": "Tiến độ: 80%", "render_hash": "old"}, start_task=False)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {"internal_job_id": "MUS-NORESET", "provider_task_id": "task", "status": "processing", "progress_percent": 60})
    monkeypatch.setattr(bot, "poll_music_suno_async_job", lambda _job_id, **_kwargs: asyncio.sleep(0, result={"ok": False, "status": "PROCESSING", "job": bot.get_engine_async_job(_job_id), "audio_bytes": b""}))
    result = asyncio.run(bot.progress_auto_refresh_tick(_ctx(), record["key"]))
    assert result["snapshot"]["percent"] == 80


def test_music_delivery_audio_sent_once(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: True)
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **kwargs: {"vault_id": "MV", "storage_ref": ""})
    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", lambda *args, **kwargs: asyncio.sleep(0, result=120))
    message = CaptureMessage()
    first = asyncio.run(bot.send_music_product_audio_result(message, SimpleNamespace(), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_music_result(), audio_bytes=b"real-audio"))
    asyncio.run(bot.send_music_product_audio_result(message, SimpleNamespace(), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=first["result"], audio_bytes=b"real-audio"))
    assert len([item for item in message.outputs if item["kind"] == "audio"]) == 1


def test_music_success_message_sent_once(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: True)
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **kwargs: {"vault_id": "MV", "storage_ref": ""})
    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", lambda *args, **kwargs: asyncio.sleep(0, result=120))
    message = CaptureMessage()
    first = asyncio.run(bot.send_music_product_audio_result(message, SimpleNamespace(), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_music_result(), audio_bytes=b"real-audio", send_success_message=True))
    asyncio.run(bot.send_music_product_audio_result(message, SimpleNamespace(), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=first["result"], audio_bytes=b"real-audio"))
    success_texts = [item.get("text", "") for item in message.outputs if "Đã tạo nhạc thành công" in item.get("text", "")]
    assert len(success_texts) == 1


def test_failed_terminal_blocks_late_success():
    result = asyncio.run(bot.send_music_product_audio_result(CaptureMessage(), SimpleNamespace(), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_music_result(), audio_bytes=b"real-audio", job={"status": "failed"}))
    assert result["status"] == "TERMINAL_FAILED"


def test_delivered_terminal_blocks_late_error(monkeypatch):
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {"internal_job_id": "MUS-DONE", "status": "delivered", "sent_full_at": "now", "output_file_id": "file"})
    result = asyncio.run(bot.poll_music_suno_async_job("MUS-DONE"))
    assert result["status"] == "ALREADY_DELIVERED"


def test_no_fail_warning_before_success_when_delivery_succeeds(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: True)
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **kwargs: {"vault_id": "MV", "storage_ref": ""})
    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", lambda *args, **kwargs: asyncio.sleep(0, result=120))
    message = CaptureMessage()
    asyncio.run(bot.send_music_product_audio_result(message, SimpleNamespace(), user_id=230501, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_music_result(), audio_bytes=b"real-audio"))
    assert not any("⚠️" in str(item.get("text") or item.get("caption") or "") for item in message.outputs)


def test_music_job_debug_is_read_only(monkeypatch):
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {"internal_job_id": "MUS-DBG", "provider_task_id": "task", "status": "processing"})
    text = bot.music_job_debug_text("MUS-DBG")
    assert "Music job debug" in text


def test_music_job_debug_does_not_send_audio(monkeypatch):
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {"internal_job_id": "MUS-DBG", "provider_task_id": "task", "status": "processing"})
    update = SimpleNamespace(effective_user=SimpleNamespace(id=1), message=CaptureMessage())
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: True)
    asyncio.run(bot.cmd_music_job_debug(update, SimpleNamespace(args=["MUS-DBG"])))
    assert not any(item["kind"] == "audio" for item in update.message.outputs)


def test_music_job_debug_does_not_send_success(monkeypatch):
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {"internal_job_id": "MUS-DBG", "provider_task_id": "task", "status": "processing"})
    update = SimpleNamespace(effective_user=SimpleNamespace(id=1), message=CaptureMessage())
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: True)
    asyncio.run(bot.cmd_music_job_debug(update, SimpleNamespace(args=["MUS-DBG"])))
    assert "Đã tạo nhạc thành công" not in update.message.outputs[-1]["text"]


def test_music_job_debug_does_not_call_provider_submit(monkeypatch):
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {"internal_job_id": "MUS-DBG", "provider_task_id": "task", "status": "processing"})
    monkeypatch.setattr(bot, "execute_engine", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("debug submitted provider")))
    bot.music_job_debug_text("MUS-DBG")


def test_music_job_debug_does_not_change_state(monkeypatch):
    saves = []
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {"internal_job_id": "MUS-DBG", "provider_task_id": "task", "status": "processing"})
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: saves.append(payload))
    bot.music_job_debug_text("MUS-DBG")
    assert saves == []


def test_mus_prefix_resolves_music_not_multiscene_video():
    assert bot.resolve_progress_product_type("MUS-ROUTE", "", {}) != "multiscene_video"


def test_progress_status_debug_mus_resolves_music():
    text = bot.product_progress_debug_text("MUS-ROUTE", "", {})
    assert "multiscene_video" not in text
    assert "music" in text


def test_progress_callback_for_mus_uses_music_product_type(monkeypatch):
    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: {"internal_job_id": "MUS-SONG", "product_type": "music_song", "provider_task_id": "task", "status": "processing", "progress_percent": 65})
    monkeypatch.setattr(bot, "poll_music_suno_async_job", lambda _job_id, **_kwargs: asyncio.sleep(0, result={"ok": False, "status": "PROCESSING", "job": bot.get_engine_async_job(_job_id), "audio_bytes": b""}))
    query = CaptureQuery("progress|status|music|MUS-SONG")
    asyncio.run(bot.handle_product_progress_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert "TOAN AAS đang tạo bài hát" in query.edits[-1]["text"]


def test_music_song_product_type_consistent():
    assert bot.music_job_product_type({"music_product_mode": "song"}) == "music_song"


def test_music_bg_product_type_consistent():
    assert bot.music_job_product_type({"music_product_mode": "background"}) == "music_bg"


def test_music_delivered_state_not_reverted_to_5_percent():
    snapshot = bot.progress_auto_refresh_snapshot("music_song", "MUS-DONE", job={"internal_job_id": "MUS-DONE", "status": "delivered", "progress_percent": 5, "output_bytes": 5})
    assert snapshot["percent"] == 100


def test_music_delivered_state_not_reverted_to_65_percent():
    snapshot = bot.progress_auto_refresh_snapshot("music_song", "MUS-DONE", job={"internal_job_id": "MUS-DONE", "status": "delivered", "progress_percent": 65, "output_bytes": 5})
    assert snapshot["percent"] == 100
