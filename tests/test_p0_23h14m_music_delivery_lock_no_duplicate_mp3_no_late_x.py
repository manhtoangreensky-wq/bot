import asyncio
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import bot


USER_ID = 231614
JOB_ID = "MUS09DA2BE5"
AUDIO_BYTES = b"ID3-toan-aas-h14m-final-audio" * 260


class DictTelegramBot:
    def __init__(self):
        self.audio = []
        self.sent = []

    async def send_audio(self, **kwargs):
        self.audio.append(kwargs)
        return {
            "message_id": f"audio-message-{len(self.audio)}",
            "audio": {"file_id": f"audio-file-{len(self.audio)}"},
            "status": "SUCCESS",
        }

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return {"message_id": f"success-message-{len(self.sent)}", "status": "SUCCESS"}


class CaptureMessage:
    def __init__(self, chat_id=USER_ID):
        self.chat_id = chat_id
        self.outputs = []

    async def reply_audio(self, **kwargs):
        self.outputs.append({"kind": "audio", **kwargs})
        return {"message_id": f"reply-audio-{len(self.outputs)}", "audio": {"file_id": f"reply-file-{len(self.outputs)}"}}

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"kind": "text", "text": str(text or ""), **kwargs})
        return {"message_id": f"reply-text-{len(self.outputs)}"}


def _ctx(fake=None):
    return SimpleNamespace(bot=fake or DictTelegramBot())


def _reset():
    bot.PROGRESS_AUTO_REFRESH_JOBS.clear()
    bot.PROGRESS_AUTO_REFRESH_TASKS.clear()
    bot.MUSIC_PRODUCT_DELIVERY_MEMORY_LOCKS.clear()
    bot.USER_PENDING.clear()


def _result():
    return {
        "user_id": USER_ID,
        "music_product_flow": "p0_20b1_suggestions",
        "music_product_mode": "song",
        "music_product_tier": bot.MUSIC_PRODUCT_TIER_BASIC,
        "music_product_price_xu": 200,
        "provider_style_prompt": "Vietnamese pop, bright chorus, female vocal",
        "provider_lyrics": "[Verse]\nTOAN AAS sang ngay\n[Chorus]\nCung nhau vuon xa",
        "song_vocal": "female",
        "selected_vocal_mode": "female",
        "requested_vocal_mode": "female",
        "music_task_id": "provider-task-h14m",
        "music_internal_job_id": JOB_ID,
        "music_job_id": JOB_ID,
    }


def _job(job_id=JOB_ID):
    return {
        "internal_job_id": job_id,
        "feature": "music_suno",
        "product_type": "music_song",
        "music_product_type": "music_song",
        "music_product_mode": "song",
        "music_product_tier": bot.MUSIC_PRODUCT_TIER_BASIC,
        "music_product_price_xu": 200,
        "song_vocal": "female",
        "selected_vocal_mode": "female",
        "requested_vocal_mode": "female",
        "user_id": str(USER_ID),
        "chat_id": str(USER_ID),
        "provider": "key4u_suno",
        "provider_task_id": "provider-task-h14m",
        "provider_job_id": "provider-task-h14m",
        "status": "completed",
        "progress_percent": 90,
        "output_bytes": len(AUDIO_BYTES),
        "artifact_duration_seconds": 190,
        "music_result_duration_seconds": 190,
        "output_sha256": bot.music_audio_sha256(AUDIO_BYTES),
        "audio_validated": True,
        "artifact_ready": True,
        "music_audio_validated": True,
        "music_artifact_ready": True,
        "pending_charge_xu": 200,
        "charged_xu": 0,
    }


def _patch_store(monkeypatch, job=None, *, admin=True):
    state = {"job": dict(job or _job()), "guided": {}, "charges": []}

    async def fake_duration(*_args, **_kwargs):
        return 190

    def fake_save(payload):
        state["job"] = dict(payload)
        return dict(payload)

    def fake_guided(_user_id):
        return dict(state["guided"])

    def fake_save_guided(_user_id, payload):
        state["guided"] = dict(payload)
        return dict(payload)

    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: dict(state["job"]) if _job_id == state["job"].get("internal_job_id") else {})
    monkeypatch.setattr(bot, "get_engine_async_job_lookup", lambda _job_id: {"job": dict(state["job"]), "resolved_job_id": state["job"].get("internal_job_id"), "canonical_job_id": state["job"].get("internal_job_id"), "lookup_found": True} if _job_id == state["job"].get("internal_job_id") else {"job": {}, "resolved_job_id": "", "canonical_job_id": "", "lookup_found": False})
    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)
    monkeypatch.setattr(bot, "get_music_guided_result", fake_guided)
    monkeypatch.setattr(bot, "save_music_guided_result", fake_save_guided)
    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", fake_duration)
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **_kwargs: {"vault_id": "MV-H14M", "storage_ref": ""})
    monkeypatch.setattr(bot, "get_music_vault_entry", lambda _vault_id: {"vault_id": _vault_id, "storage_ref": ""})
    monkeypatch.setattr(bot, "mark_music_vault_status", lambda *args, **kwargs: {"vault_id": args[0] if args else "MV-H14M"})
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: bool(admin))

    def fake_spend(*args, **_kwargs):
        state["charges"].append(args)
        return {"ok": True, "final_cost": 200, "status": "ok"}

    monkeypatch.setattr(bot, "spend_fixed_credit_info", fake_spend)
    return state


def _deliver(monkeypatch, fake=None, result=None, job=None, *, source="auto_tick", send_success=True):
    state = _patch_store(monkeypatch, job or _job())
    fake = fake or DictTelegramBot()
    delivered = asyncio.run(
        bot.deliver_music_result_once(
            CaptureMessage(),
            _ctx(fake),
            user_id=USER_ID,
            lang="vi",
            product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
            result=result or _result(),
            audio_bytes=AUDIO_BYTES,
            job=state["job"],
            updated_by=USER_ID,
            send_success_message=send_success,
            source=source,
        )
    )
    return delivered, fake, state


def test_music_telegram_dict_success_sets_delivery_succeeded(monkeypatch):
    _reset()
    delivered, fake, state = _deliver(monkeypatch)
    assert delivered["ok"] is True
    assert delivered["delivery_message_id"] == "audio-message-1"
    assert delivered["file_id"] == "audio-file-1"
    assert state["job"]["delivery_succeeded"] is True
    assert state["job"]["delivery_state"] == "delivered"
    assert state["job"]["duplicate_guard_state"] == "closed"
    assert len(fake.audio) == 1


def test_music_telegram_success_sets_delivery_succeeded(monkeypatch):
    _reset()
    delivered, _fake, state = _deliver(monkeypatch)
    assert delivered["ok"] is True
    assert state["job"]["delivery_succeeded"] is True
    assert state["job"]["delivery_state_final"] == "delivered"


def test_music_delivery_message_id_saved_on_success(monkeypatch):
    _reset()
    delivered, _fake, state = _deliver(monkeypatch)
    assert delivered["delivery_message_id"] == "audio-message-1"
    assert state["job"]["music_delivery_message_id"] == "audio-message-1"
    assert state["job"]["delivered_artifact_hash"]


def test_music_same_job_same_artifact_sent_once_and_attempt_not_incremented(monkeypatch):
    _reset()
    first, fake, _state = _deliver(monkeypatch)
    first_attempts = int(first["job"].get("delivery_attempt_count") or 0)
    second = asyncio.run(
        bot.deliver_music_result_once(
            CaptureMessage(),
            _ctx(fake),
            user_id=USER_ID,
            lang="vi",
            product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
            result=first["result"],
            audio_bytes=AUDIO_BYTES,
            job=first["job"],
            updated_by=USER_ID,
            send_success_message=True,
            source="manual_refresh",
        )
    )
    assert second["duplicate"] is True
    assert len(fake.audio) == 1
    assert int(second["job"].get("delivery_attempt_count") or 0) == first_attempts


def test_music_same_job_same_artifact_sent_once(monkeypatch):
    _reset()
    first, fake, _state = _deliver(monkeypatch)
    second = asyncio.run(
        bot.deliver_music_result_once(
            CaptureMessage(),
            _ctx(fake),
            user_id=USER_ID,
            lang="vi",
            product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
            result=first["result"],
            audio_bytes=AUDIO_BYTES,
            job=first["job"],
            updated_by=USER_ID,
            send_success_message=True,
            source="same_artifact",
        )
    )
    assert second["duplicate"] is True
    assert len(fake.audio) == 1


def test_music_duplicate_auto_tick_and_manual_refresh_do_not_resend_mp3(monkeypatch):
    _reset()
    first, fake, _state = _deliver(monkeypatch)
    for source in ("auto_tick", "manual_status_update", "admin_recover"):
        duplicate = asyncio.run(
            bot.deliver_music_result_once(
                CaptureMessage(),
                _ctx(fake),
                user_id=USER_ID,
                lang="vi",
                product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
                result=first["result"],
                audio_bytes=AUDIO_BYTES,
                job=first["job"],
                updated_by=USER_ID,
                send_success_message=True,
                source=source,
            )
        )
        assert duplicate["duplicate"] is True
    assert len(fake.audio) == 1
    assert len(fake.sent) == 1


def test_music_duplicate_auto_tick_does_not_resend_mp3(monkeypatch):
    _reset()
    first, fake, _state = _deliver(monkeypatch)
    duplicate = asyncio.run(
        bot.deliver_music_result_once(
            CaptureMessage(),
            _ctx(fake),
            user_id=USER_ID,
            lang="vi",
            product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
            result=first["result"],
            audio_bytes=AUDIO_BYTES,
            job=first["job"],
            updated_by=USER_ID,
            send_success_message=True,
            source="auto_tick",
        )
    )
    assert duplicate["duplicate"] is True
    assert len(fake.audio) == 1


def test_music_manual_refresh_does_not_resend_mp3(monkeypatch):
    _reset()
    first, fake, _state = _deliver(monkeypatch)
    duplicate = asyncio.run(
        bot.deliver_music_result_once(
            CaptureMessage(),
            _ctx(fake),
            user_id=USER_ID,
            lang="vi",
            product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
            result=first["result"],
            audio_bytes=AUDIO_BYTES,
            job=first["job"],
            updated_by=USER_ID,
            send_success_message=True,
            source="manual_status_update",
        )
    )
    assert duplicate["duplicate"] is True
    assert len(fake.audio) == 1


def test_music_duplicate_guard_closes_after_success(monkeypatch):
    _reset()
    delivered, _fake, state = _deliver(monkeypatch)
    assert delivered["job"]["duplicate_guard_state"] == "closed"
    assert state["job"]["music_delivery_lock"] == "sent"


def test_music_late_error_after_delivery_does_not_become_public_x(monkeypatch):
    _reset()
    first, _fake, _state = _deliver(monkeypatch)
    attempts = int(first["job"].get("delivery_attempt_count") or 0)
    updated = bot.record_music_job_full_send_error(first["job"], "Có lỗi khi xử lý lệnh", updated_by=USER_ID)
    assert updated["terminal_state"] == "delivered"
    assert updated["music_terminal_state"] == "delivered"
    assert updated["delivery_state"] == "delivered"
    assert updated["public_x_suppressed"] is True
    assert updated["auto_delivery_blocker"] == ""
    assert int(updated.get("delivery_attempt_count") or 0) == attempts


def test_music_no_public_x_after_audio_delivery(monkeypatch):
    _reset()
    first, _fake, _state = _deliver(monkeypatch)
    updated = bot.record_music_job_full_send_error(first["job"], "late failure", updated_by=USER_ID)
    assert updated["public_x_suppressed"] is True
    assert updated["terminal_state"] == "delivered"


def test_music_exception_after_delivery_does_not_send_x(monkeypatch):
    _reset()
    first, _fake, _state = _deliver(monkeypatch)
    updated = bot.record_music_runtime_error_suppressed(first["job"], reason="Exception", callback_data="music_quick|status", status_panel=False, updated_by=USER_ID)
    assert updated["public_x_suppressed"] is True
    assert updated["late_public_error_suppressed"] is True


def test_music_success_not_overwritten_by_late_failure(monkeypatch):
    _reset()
    first, _fake, _state = _deliver(monkeypatch)
    updated = bot.record_music_job_full_send_error(first["job"], "telegram timeout after success", updated_by=USER_ID)
    assert updated["terminal_state"] == "delivered"
    assert updated["delivery_succeeded"] is True
    assert updated["delivery_state_final"] == "delivered"


def test_music_success_like_send_error_not_classified_as_telegram_delivery_failed(monkeypatch):
    _reset()
    state = _patch_store(monkeypatch)
    updated = bot.record_music_job_full_send_error(state["job"], "SUCCESS", updated_by=USER_ID)
    assert updated["delivery_state"] == "send_unconfirmed_success_like"
    assert updated.get("terminal_state") != "telegram_delivery_failed"
    assert updated["auto_delivery_blocker"] == ""
    assert updated["telegram_send_success_detected"] is True


def test_music_fail_reason_success_not_classified_as_delivery_failed(monkeypatch):
    _reset()
    state = _patch_store(monkeypatch)
    updated = bot.record_music_job_full_send_error(state["job"], "SUCCESS", updated_by=USER_ID)
    assert updated.get("terminal_state") != "telegram_delivery_failed"
    assert updated.get("music_terminal_state") != "telegram_delivery_failed"
    assert updated["fail_reason_safe"] == "SUCCESS"


def test_music_runtime_error_suppression_marks_no_late_x(monkeypatch):
    _reset()
    first, _fake, _state = _deliver(monkeypatch)
    updated = bot.record_music_runtime_error_suppressed(first["job"], reason="RuntimeError", callback_data="progress|status|music_song|MUS09DA2BE5", status_panel=True, updated_by=USER_ID)
    assert updated["late_error_after_delivery_suppressed"] is True
    assert updated["public_x_suppressed"] is True
    assert updated["generic_error_after_delivery_prevented"] is True


def test_music_success_receipt_sent_once_after_duplicate_attempt(monkeypatch):
    _reset()
    first, fake, _state = _deliver(monkeypatch)
    duplicate = asyncio.run(
        bot.deliver_music_result_once(
            CaptureMessage(),
            _ctx(fake),
            user_id=USER_ID,
            lang="vi",
            product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
            result=first["result"],
            audio_bytes=AUDIO_BYTES,
            job=first["job"],
            updated_by=USER_ID,
            send_success_message=True,
            source="worker_retry",
        )
    )
    assert duplicate["duplicate"] is True
    assert len(fake.sent) == 1
    assert "Giọng hát: Nữ" in fake.sent[0]["text"]


def test_music_status_100_and_auto_refresh_stops_after_success(monkeypatch):
    _reset()
    key = bot.progress_auto_refresh_key("music_song", JOB_ID)
    bot.PROGRESS_AUTO_REFRESH_JOBS[key] = {"job_id": JOB_ID, "product_type": "music_song", "percent": 95, "task_alive": True}
    first, _fake, _state = _deliver(monkeypatch)
    record = bot.PROGRESS_AUTO_REFRESH_JOBS[key]
    assert first["job"]["progress_percent"] == 100
    assert first["job"]["refresh_stopped_after_terminal"] is True
    assert record["stopped"] is True
    assert record["task_alive"] is False
    assert record["percent"] == 100


def test_music_status_100_after_delivery(monkeypatch):
    _reset()
    delivered, _fake, _state = _deliver(monkeypatch)
    assert delivered["job"]["progress_percent"] == 100
    assert delivered["result"]["terminal_state"] == "delivered"


def test_music_auto_refresh_stops_after_success(monkeypatch):
    _reset()
    key = bot.progress_auto_refresh_key("music_song", JOB_ID)
    bot.PROGRESS_AUTO_REFRESH_JOBS[key] = {"job_id": JOB_ID, "product_type": "music_song", "percent": 95, "task_alive": True}
    _deliver(monkeypatch)
    assert bot.PROGRESS_AUTO_REFRESH_JOBS[key]["stopped"] is True
    assert bot.PROGRESS_AUTO_REFRESH_JOBS[key]["stopped_reason"] == "delivered"


def test_music_success_receipt_sent_once(monkeypatch):
    _reset()
    first, fake, _state = _deliver(monkeypatch)
    duplicate = asyncio.run(
        bot.deliver_music_result_once(
            CaptureMessage(),
            _ctx(fake),
            user_id=USER_ID,
            lang="vi",
            product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
            result=first["result"],
            audio_bytes=AUDIO_BYTES,
            job=first["job"],
            updated_by=USER_ID,
            send_success_message=True,
            source="refresh_after_success",
        )
    )
    assert duplicate["duplicate"] is True
    assert len(fake.sent) == 1


def test_music_female_suggestion_state_preserved_debug(monkeypatch):
    _reset()
    delivered, _fake, state = _deliver(monkeypatch)
    assert delivered["job"]["requested_vocal_mode"] == "female"
    assert delivered["job"]["selected_vocal_mode"] == "female"
    debug = bot.music_job_debug_text(JOB_ID)
    assert "requested_vocal_mode: <code>female</code>" in debug
    assert "selected_vocal_mode: <code>female</code>" in debug


def test_music_female_receipt_says_nu(monkeypatch):
    _reset()
    _delivered, fake, _state = _deliver(monkeypatch)
    assert len(fake.sent) == 1
    assert "Giọng hát: Nữ" in fake.sent[0]["text"]


def test_music_job_debug_includes_h14m_delivery_fields(monkeypatch):
    _reset()
    first, _fake, _state = _deliver(monkeypatch)
    text = bot.music_job_debug_text(str(first["job"]["internal_job_id"]))
    assert "telegram_send_returned_message" in text
    assert "telegram_send_success_detected" in text
    assert "delivery_success_detection_source" in text
    assert "duplicate_guard_state" in text
    assert "public_x_suppressed" in text


def test_music_duplicate_request_public_copy_removed_from_product_confirm_source():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert "hệ thống không gửi lại yêu cầu tạo nhạc" not in source
    assert "TOAN AAS đã nhận yêu cầu này. Anh/chị theo dõi bảng trạng thái phía trên" not in source


def test_music_duplicate_request_does_not_send_extra_public_copy():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert "TOAN AAS đã nhận yêu cầu này. Anh/chị theo dõi bảng trạng thái phía trên" not in source


def test_music_duplicate_request_keeps_existing_panel():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert '"status": "ALREADY_SUBMITTED"' in source
    assert "await query.answer(\"TOAN AAS đang xử lý yêu cầu này.\"" in source


def test_music_h14m_scope_does_not_touch_forbidden_runtime_areas():
    branch = (
        os.environ.get("GITHUB_HEAD_REF")
        or os.environ.get("GITHUB_REF_NAME")
        or subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
    ).lower()
    if any(token in branch for token in ("p0-19m", "subdub", "subtitle-dub", "subtitle_dub")):
        return
    changed = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True).splitlines()
    allowed = {"bot.py", "tests/test_p0_23h14m_music_delivery_lock_no_duplicate_mp3_no_late_x.py"}
    assert set(changed).issubset(allowed)
