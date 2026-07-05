import asyncio
import subprocess
from types import SimpleNamespace

import bot


USER_ID = 231616
JOB_ID = "MUSH14OFEMALE"
AUDIO_BYTES = b"ID3-toan-aas-h14o-final-audio" * 260


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


class ReentrantTelegramBot(DictTelegramBot):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.reentrant_result = None

    async def send_audio(self, **kwargs):
        self.audio.append(kwargs)
        if len(self.audio) == 1:
            self.reentrant_result = await bot.deliver_music_result_once(
                CaptureMessage(),
                _ctx(self),
                user_id=USER_ID,
                lang="vi",
                product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
                result=_result(),
                audio_bytes=AUDIO_BYTES,
                job=dict(self.state["initial_job"]),
                updated_by=USER_ID,
                send_success_message=True,
                source="manual_status_update",
            )
        return {
            "message_id": f"audio-message-{len(self.audio)}",
            "audio": {"file_id": f"audio-file-{len(self.audio)}"},
            "status": "SUCCESS",
        }


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
    bot.MUSIC_H14O_FEMALE_SUGGESTION_SEND_GUARDS.clear()
    bot.USER_PENDING.clear()


def _result():
    return {
        "user_id": USER_ID,
        "chat_id": USER_ID,
        "music_product_flow": "p0_20b1_suggestions",
        "music_product_mode": "song",
        "music_product_type": "music_song",
        "music_product_tier": bot.MUSIC_PRODUCT_TIER_BASIC,
        "music_product_price_xu": 200,
        "music_selected_suggestion_id": "song-female-1",
        "vocal_mode_source": "selected_suggestion",
        "provider_style_prompt": "Vietnamese pop, bright chorus, Female vocal",
        "provider_lyrics": "[Verse]\nTOAN AAS sang ngay\n[Chorus]\nCung nhau vuon xa",
        "song_vocal": "female",
        "vocal_mode": "female",
        "selected_vocal_mode": "female",
        "requested_vocal_mode": "female",
        "music_task_id": "provider-task-h14o",
        "music_internal_job_id": JOB_ID,
        "music_job_id": JOB_ID,
    }


def _job(job_id=JOB_ID):
    return {
        "internal_job_id": job_id,
        "feature": "music_suno",
        "product_type": "music_song",
        "music_product_type": "music_song",
        "music_product_flow": "p0_20b1_suggestions",
        "music_product_mode": "song",
        "music_product_tier": bot.MUSIC_PRODUCT_TIER_BASIC,
        "music_product_price_xu": 200,
        "music_selected_suggestion_id": "song-female-1",
        "vocal_mode_source": "selected_suggestion",
        "song_vocal": "female",
        "vocal_mode": "female",
        "selected_vocal_mode": "female",
        "requested_vocal_mode": "female",
        "user_id": str(USER_ID),
        "chat_id": str(USER_ID),
        "provider": "key4u_suno",
        "provider_task_id": "provider-task-h14o",
        "provider_job_id": "provider-task-h14o",
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
    initial_job = dict(job or _job())
    state = {"job": dict(initial_job), "initial_job": initial_job, "guided": {}, "charges": []}

    async def fake_duration(*_args, **_kwargs):
        return 190

    def fake_save(payload):
        state["job"] = dict(payload)
        return dict(payload)

    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: dict(state["job"]) if _job_id == state["job"].get("internal_job_id") else {})
    monkeypatch.setattr(
        bot,
        "get_engine_async_job_lookup",
        lambda _job_id: {
            "job": dict(state["job"]),
            "resolved_job_id": state["job"].get("internal_job_id"),
            "canonical_job_id": state["job"].get("internal_job_id"),
            "lookup_found": True,
        } if _job_id == state["job"].get("internal_job_id") else {"job": {}, "resolved_job_id": "", "canonical_job_id": "", "lookup_found": False},
    )
    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)
    monkeypatch.setattr(bot, "get_music_guided_result", lambda _user_id: dict(state["guided"]))
    monkeypatch.setattr(bot, "save_music_guided_result", lambda _user_id, payload: state["guided"].update(dict(payload)) or dict(payload))
    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", fake_duration)
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **_kwargs: {"vault_id": "MV-H14O", "storage_ref": ""})
    monkeypatch.setattr(bot, "get_music_vault_entry", lambda _vault_id: {"vault_id": _vault_id, "storage_ref": ""})
    monkeypatch.setattr(bot, "mark_music_vault_status", lambda *args, **kwargs: {"vault_id": args[0] if args else "MV-H14O"})
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: bool(admin))
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: state["charges"].append(args) or {"ok": True, "final_cost": 200, "status": "ok"})
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


def test_female_suggestion_one_mp3_only(monkeypatch):
    _reset()
    delivered, fake, state = _deliver(monkeypatch)

    assert delivered["ok"] is True
    assert len(fake.audio) == 1
    assert state["job"]["h14o_female_suggestion_guard_active"] is True
    assert state["job"]["duplicate_guard_state"] == "closed"


def test_female_suggestion_auto_tick_finalizer_race_sends_one(monkeypatch):
    _reset()
    state = _patch_store(monkeypatch)
    fake = ReentrantTelegramBot(state)

    delivered = asyncio.run(bot.deliver_music_result_once(
        CaptureMessage(),
        _ctx(fake),
        user_id=USER_ID,
        lang="vi",
        product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
        result=_result(),
        audio_bytes=AUDIO_BYTES,
        job=state["job"],
        updated_by=USER_ID,
        send_success_message=True,
        source="auto_tick",
    ))

    assert delivered["ok"] is True
    assert len(fake.audio) == 1
    assert fake.reentrant_result["duplicate"] is True
    assert fake.reentrant_result["job"]["duplicate_send_suppressed"] is True
    assert fake.reentrant_result["job"]["duplicate_send_suppressed_count"] >= 1
    assert fake.reentrant_result["job"]["duplicate_send_suppressed_reason"] == "h14o_female_suggestion_in_progress"


def test_female_suggestion_refresh_after_first_send_does_not_resend(monkeypatch):
    _reset()
    first, fake, _state = _deliver(monkeypatch)
    duplicate = asyncio.run(bot.deliver_music_result_once(
        CaptureMessage(),
        _ctx(fake),
        user_id=USER_ID,
        lang="vi",
        product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
        result=_result(),
        audio_bytes=AUDIO_BYTES,
        job=_job(),
        updated_by=USER_ID,
        send_success_message=True,
        source="manual_status_update",
    ))

    assert first["ok"] is True
    assert duplicate["duplicate"] is True
    assert len(fake.audio) == 1
    assert duplicate["job"]["first_delivery_message_id"] == "audio-message-1"


def test_female_suggestion_receipt_sent_once(monkeypatch):
    _reset()
    first, fake, _state = _deliver(monkeypatch)
    duplicate = asyncio.run(bot.deliver_music_result_once(
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
    ))

    assert duplicate["duplicate"] is True
    assert len(fake.sent) == 1
    assert first["job"]["receipt_sent_once"] is True


def test_female_suggestion_no_x_after_duplicate_suppressed(monkeypatch):
    _reset()
    first, _fake, _state = _deliver(monkeypatch)
    updated = bot.record_music_job_full_send_error(first["job"], "late failure after duplicate", updated_by=USER_ID)

    assert updated["terminal_state"] == "delivered"
    assert updated["delivery_state"] == "delivered"
    assert updated["public_x_suppressed"] is True


def test_h14o_debug_fields_present(monkeypatch):
    _reset()
    _delivered, _fake, _state = _deliver(monkeypatch)
    text = bot.music_job_debug_text(JOB_ID)

    assert "h14o_female_suggestion_guard_active: <code>yes</code>" in text
    assert "delivery_guard_key" in text
    assert "sender_sources_seen" in text
    assert "duplicate_send_suppressed_count" in text
    assert "first_delivery_message_id" in text
    assert "receipt_sent_once: <code>yes</code>" in text


def test_h14o_does_not_touch_price_tables():
    changed = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True).splitlines()
    assert "tests/test_p0_23h_price1_music_all_tiers_price_ui_behavior_sync.py" not in changed


def test_h14o_does_not_touch_custom_lyrics_route():
    diff = subprocess.check_output(["git", "diff", "-U0", "origin/main", "--", "bot.py"], text=True)
    changed_lines = "\n".join(line for line in diff.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---")))
    forbidden = ("music_product_song_style", "music_product_song_details", "music_product_manual", "music_product_pending_lyrics")
    assert not any(token in changed_lines for token in forbidden)


def test_h14o_does_not_touch_provider_download_artifact():
    diff = subprocess.check_output(["git", "diff", "-U0", "origin/main", "--", "bot.py"], text=True)
    changed_lines = "\n".join(line for line in diff.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---")))
    forbidden = ("artifact_download", "provider_download_endpoint", "wav_", "download_strategy_used", "select_music_delivery_artifact")
    assert not any(token in changed_lines for token in forbidden)


def test_h14o_does_not_touch_product_video_subdub_voice_payos_db():
    changed = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True).splitlines()
    forbidden_prefixes = (
        "providers/video",
        "services/video",
        "services/subdub",
        "services/payos",
        "services/wallet",
        "services/voice",
        "migrations/",
    )
    forbidden_exact = {"local_worker.py", "remote_worker.py", "providers/key4u_provider.py"}
    assert not any(path in forbidden_exact or path.startswith(forbidden_prefixes) for path in changed)
