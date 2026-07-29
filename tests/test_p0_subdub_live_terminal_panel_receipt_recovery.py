import asyncio
from types import SimpleNamespace

import bot


class CaptureBot:
    def __init__(self):
        self.edits = []

    async def edit_message_text(self, **kwargs):
        self.edits.append(dict(kwargs))
        return SimpleNamespace(message_id=kwargs["message_id"], chat_id=kwargs["chat_id"])


class AlreadyTerminalBot(CaptureBot):
    async def edit_message_text(self, **kwargs):
        self.edits.append(dict(kwargs))
        raise RuntimeError("Message is not modified")


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


class ProgressQuery(CaptureQuery):
    def __init__(self, message, bot_client, job_id="RECOVERED"):
        super().__init__(message, bot_client)
        self.data = f"progress|status|subdub|{job_id}"
        self.from_user = SimpleNamespace(id=7070)
        self.answer_count = 0

    async def answer(self):
        self.answer_count += 1

    async def edit_message_text(self, text, **kwargs):
        return await self._bot_client.edit_message_text(
            chat_id=self.message.chat_id,
            message_id=self.message.message_id,
            text=text,
            **kwargs,
        )


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


def test_terminal_panel_recovers_with_replacement_when_stored_panel_is_unavailable():
    key = "terminal-panel-replacement"
    job = _fresh_job(key)
    assert bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        delivery_message_id="8182",
        terminal_artifact_type="video",
        video_delivery_message_id="8182",
    )
    bot.SUBTITLE_DUB_PIPELINE_JOBS[key]["status_panel_message_id"] = ""
    bot.SUBTITLE_DUB_PIPELINE_JOBS[key]["status_panel_chat_id"] = ""

    capture_bot = CaptureBot()
    message = CaptureMessage()
    query = CaptureQuery(message, capture_bot)
    finalized = asyncio.run(
        bot.subdub_finalize_delivered_panel(
            query,
            SimpleNamespace(bot=capture_bot),
            key,
            job["job_id"],
            "vi",
            {"has_video": True, "video_delivery_message_id": "8182"},
        )
    )
    receipt = asyncio.run(
        bot.subdub_send_success_receipt_once(message, key, "receipt")
    )

    assert finalized is not None
    assert capture_bot.edits == []
    assert len(message.replies) == 2
    assert "100%" in message.replies[0][0]
    assert message.replies[1][0] == "receipt"
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    assert stored["status_panel_terminal_edit_method"] == "replacement_status_message"
    assert stored["status_panel_terminalized"] is True
    assert stored["panel_final_percent"] == 100
    assert stored["receipt_sent_once"] is True


def test_terminal_panel_treats_message_not_modified_as_confirmed_without_replacement():
    key = "terminal-panel-already-green"
    job = _fresh_job(key)
    assert bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        delivery_message_id="8183",
        terminal_artifact_type="video",
        video_delivery_message_id="8183",
    )
    capture_bot = AlreadyTerminalBot()
    message = CaptureMessage()
    query = CaptureQuery(message, capture_bot)

    finalized = asyncio.run(
        bot.subdub_finalize_delivered_panel(
            query,
            SimpleNamespace(bot=capture_bot),
            key,
            job["job_id"],
            "vi",
            {"video_delivery_message_id": "8183"},
        )
    )

    assert finalized is message
    assert len(capture_bot.edits) == 1
    assert message.replies == []
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    assert stored["status_panel_terminal_edit_method"] == "stored_message_already_terminal"
    assert stored["status_panel_terminal_edit_confirmed"] is True


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


def test_uncertain_receipt_send_is_never_retried_automatically():
    key = "terminal-receipt-timeout-no-retry"
    job = _fresh_job(key)
    assert bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        delivery_message_id="8284",
        terminal_artifact_type="video",
        video_delivery_message_id="8284",
    )
    capture_bot = CaptureBot()
    panel_message = CaptureMessage()
    asyncio.run(
        bot.subdub_finalize_delivered_panel(
            CaptureQuery(panel_message, capture_bot),
            SimpleNamespace(bot=capture_bot),
            key,
            job["job_id"],
            "vi",
            {"video_delivery_message_id": "8284"},
        )
    )

    class TimeoutReceiptMessage(CaptureMessage):
        def __init__(self):
            super().__init__()
            self.attempts = 0

        async def reply_text(self, *_args, **_kwargs):
            self.attempts += 1
            raise TimeoutError("ReadTimeout while sending receipt")

    message = TimeoutReceiptMessage()
    first = asyncio.run(bot.subdub_send_success_receipt_once(message, key, "receipt"))
    second = asyncio.run(bot.subdub_send_success_receipt_once(message, key, "receipt"))

    assert first is None
    assert second is None
    assert message.attempts == 1
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    assert stored["receipt_send_state"] == "unknown"
    assert stored["receipt_send_uncertain"] is True
    assert stored["duplicate_receipt_prevented"] is True


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
    assert bot.subdub_job_video_delivery_succeeded(result) is False
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


def test_srt_only_evidence_cannot_complete_a_lane_that_requires_final_mp4():
    result = {
        "ok": True,
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "terminal_artifact_type": "subtitle",
        "srt_delivery_message_id": "srt-only-9003",
        "delivery_success": True,
    }

    assert bot.subdub_terminal_delivery_evidence(result) == {}
    assert bot.subdub_registry_terminal_state(result) == "failed_no_charge"


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


def test_status_refresh_repairs_persisted_delivered_panel_and_receipt_without_reprocessing(monkeypatch):
    key = "persisted-terminal-recovery"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    persisted = {
        "job_key": key,
        "job_id": "RECOVERED",
        "internal_job_id": "RECOVERED",
        "user_id": "7070",
        "chat_id": "7070",
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "mapped_mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "status": "completed",
        "terminal_state": "delivered",
        "progress_percent": 100,
        "video_delivery_message_id": "real-video-9901",
        "final_mp4_delivered": True,
        "status_panel_message_id": "8080",
        "status_panel_chat_id": "7070",
        "charged_xu": 0,
    }
    monkeypatch.setattr(bot, "subdub_progress_job_for_user", lambda *_args, **_kwargs: dict(persisted))
    monkeypatch.setattr(bot, "get_engine_async_job", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(bot, "progress_auto_refresh_register_message", lambda *_args, **_kwargs: None)

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("status recovery must not reprocess providers")

    monkeypatch.setattr(bot, "asr_transcribe_audio", forbidden)
    monkeypatch.setattr(bot, "translate_subtitle_text", forbidden)
    monkeypatch.setattr(bot, "video_dubbing_tts_bytes", forbidden)

    capture_bot = CaptureBot()
    message = CaptureMessage()
    query = ProgressQuery(message, capture_bot)
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(bot=capture_bot)

    first = asyncio.run(bot.handle_product_progress_callback(update, context))
    second = asyncio.run(bot.handle_product_progress_callback(update, context))

    assert first is not None
    assert second is not None
    assert query.answer_count == 2
    assert len(capture_bot.edits) == 2
    assert all("100%" in edit["text"] for edit in capture_bot.edits)
    assert len(message.replies) == 1
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    assert stored["status_panel_terminalized"] is True
    assert stored["receipt_sent_once"] is True
    assert stored["video_delivery_message_id"] == "real-video-9901"


def test_status_refresh_delivers_validated_unattempted_mp4_once_without_provider_replay(monkeypatch, tmp_path):
    key = "persisted-unattempted-mp4"
    output_path = tmp_path / "validated.mp4"
    output_path.write_bytes(b"validated-mp4-fixture")
    persisted = {
        "job_key": key,
        "job_id": "RECOVER-MP4-1",
        "internal_job_id": "RECOVER-MP4-1",
        "user_id": "7070",
        "chat_id": "7070",
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "mapped_mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "status": "running",
        "terminal_state": "",
        "progress_percent": 90,
        "final_mp4_path": str(output_path),
        "final_mp4_exists": True,
        "final_mp4_validated": True,
        "output_validated": True,
        "delivery_attempted": False,
        "delivery_attempts": 0,
        "status_panel_message_id": "8081",
        "status_panel_chat_id": "7070",
        "charged_xu": 0,
    }
    assert bot.subdub_existing_mp4_recovery_candidate(
        {**persisted, "delivery_attempted": True, "delivery_attempts": 1}
    ) == ""
    monkeypatch.setattr(
        bot,
        "subdub_progress_job_for_user",
        lambda *_args, **_kwargs: dict(bot.SUBTITLE_DUB_PIPELINE_JOBS.get(key) or persisted),
    )
    monkeypatch.setattr(bot, "get_engine_async_job", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(bot, "progress_auto_refresh_register_message", lambda *_args, **_kwargs: None)
    calls = []

    async def deliver_once(*_args, **kwargs):
        calls.append(dict(kwargs))
        return {
            "video": 1,
            "video_document": 0,
            "telegram_message_id": "recovered-video-1",
            "video_delivery_message_id": "recovered-video-1",
            "terminal_artifact_type": "video",
            "final_mp4_delivered": True,
            "final_mp4_validated": True,
            "duration_coverage_ok": True,
            "output_validation": {"ok": True},
        }

    monkeypatch.setattr(bot, "send_public_subtitle_dub_final_outputs", deliver_once)
    for name in ("asr_transcribe_audio", "translate_subtitle_text", "video_dubbing_tts_bytes"):
        async def forbidden(*_args, **_kwargs):
            raise AssertionError("MP4 recovery must not replay providers")
        monkeypatch.setattr(bot, name, forbidden)

    capture_bot = CaptureBot()
    message = CaptureMessage()
    query = ProgressQuery(message, capture_bot, job_id="RECOVER-MP4-1")
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(bot=capture_bot)

    first = asyncio.run(bot.handle_product_progress_callback(update, context))
    second = asyncio.run(bot.handle_product_progress_callback(update, context))

    assert first is not None
    assert second is not None
    assert len(calls) == 1
    assert calls[0]["canonical_video_path"] == str(output_path)
    assert len(message.replies) == 1
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    assert stored["video_delivery_message_id"] == "recovered-video-1"
    assert stored["delivery_attempted"] is True
    assert stored["status_panel_terminalized"] is True


def test_status_refresh_terminalizes_interrupted_persisted_job_without_mp4_no_charge(monkeypatch):
    key = "persisted-interrupted-no-mp4"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    persisted = {
        "job_key": key,
        "job_id": "INTERRUPTED-35",
        "internal_job_id": "INTERRUPTED-35",
        "user_id": "7070",
        "chat_id": "7070",
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "mapped_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "status": "running",
        "terminal_state": "",
        "lifecycle_state": "transcribing",
        "current_stage": "transcribing",
        "progress_stage": "transcribing",
        "progress_percent": 35,
        "pipeline_started": True,
        "final_mp4_exists": False,
        "final_mp4_validated": False,
        "delivery_attempted": False,
        "lookup_store_hit": "engine_async_feature_index",
        "status_panel_message_id": "8082",
        "status_panel_chat_id": "7070",
        "charged_xu": 0,
    }
    monkeypatch.setattr(bot, "subdub_progress_job_for_user", lambda *_args, **_kwargs: dict(persisted))
    monkeypatch.setattr(bot, "get_engine_async_job", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(bot, "progress_auto_refresh_register_message", lambda *_args, **_kwargs: None)

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("interrupted status recovery must not reprocess or deliver")

    for name in (
        "asr_transcribe_audio",
        "translate_subtitle_text",
        "video_dubbing_tts_bytes",
        "send_public_subtitle_dub_final_outputs",
    ):
        monkeypatch.setattr(bot, name, forbidden)

    capture_bot = CaptureBot()
    message = CaptureMessage()
    query = ProgressQuery(message, capture_bot, job_id="INTERRUPTED-35")
    result = asyncio.run(
        bot.handle_product_progress_callback(
            SimpleNamespace(callback_query=query),
            SimpleNamespace(bot=capture_bot),
        )
    )

    assert result is not None
    assert len(capture_bot.edits) == 1
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    assert stored["terminal_state"] == "failed_no_charge"
    assert stored["charge_status"] == "not_charged"
    assert stored["progress_percent"] == 35
    assert stored["status_panel_terminalized"] is True
    assert stored["refresh_stopped_after_terminal"] is True
