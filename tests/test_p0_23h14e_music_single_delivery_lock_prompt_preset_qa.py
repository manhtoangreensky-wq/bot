import asyncio
import subprocess
from types import SimpleNamespace

import bot


USER_ID = 231514
JOB_ID = "MUSD8EA089F"
AUDIO_BYTES = b"ID3-toan-aas-h14e-final-audio" * 240


class FakeBot:
    def __init__(self):
        self.audio = []
        self.sent = []

    async def send_audio(self, **kwargs):
        self.audio.append(kwargs)
        return SimpleNamespace(message_id=8000 + len(self.audio), audio=SimpleNamespace(file_id=f"audio-{len(self.audio)}"))

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(message_id=7000 + len(self.sent))


class CaptureMessage:
    def __init__(self, text="", chat_id=USER_ID):
        self.text = text
        self.chat_id = chat_id
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"kind": "text", "text": str(text or ""), **kwargs})
        return SimpleNamespace(message_id=len(self.outputs))

    async def reply_audio(self, audio=None, filename="", caption="", **kwargs):
        self.outputs.append({"kind": "audio", "audio": audio, "filename": filename, "caption": caption, **kwargs})
        return SimpleNamespace(message_id=len(self.outputs), audio=SimpleNamespace(file_id=f"reply-audio-{len(self.outputs)}"))


def _ctx(fake=None):
    return SimpleNamespace(bot=fake or FakeBot())


def _message_update(message, user_id=USER_ID):
    return SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id))


def _reset():
    bot.PROGRESS_AUTO_REFRESH_JOBS.clear()
    bot.PROGRESS_AUTO_REFRESH_TASKS.clear()
    bot.MUSIC_PRODUCT_DELIVERY_MEMORY_LOCKS.clear()
    bot.USER_PENDING.clear()


def _result():
    return {
        "music_product_flow": "p0_20b1_suggestions",
        "music_product_mode": "song",
        "music_product_tier": bot.MUSIC_PRODUCT_TIER_BASIC,
        "music_product_price_xu": 200,
        "provider_style_prompt": "Vietnamese pop, bright chorus, female vocal",
        "provider_lyrics": "[Verse]\nTOAN AAS sang ngay\n[Chorus]\nCung nhau vuon xa",
        "song_vocal": "female",
        "music_task_id": "provider-task-h14e",
        "music_internal_job_id": JOB_ID,
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
        "user_id": str(USER_ID),
        "chat_id": str(USER_ID),
        "provider": "key4u_suno",
        "provider_task_id": "provider-task-h14e",
        "provider_job_id": "provider-task-h14e",
        "status": "completed",
        "progress_percent": 90,
        "output_bytes": len(AUDIO_BYTES),
        "artifact_duration_seconds": 110,
        "music_result_duration_seconds": 110,
        "output_sha256": bot.music_audio_sha256(AUDIO_BYTES),
        "audio_validated": True,
        "artifact_ready": True,
        "music_audio_validated": True,
        "music_artifact_ready": True,
        "pending_charge_xu": 200,
        "charged_xu": 0,
    }


def _patch_store(monkeypatch, job=None, *, admin=True, charge_ok=True, charged=200):
    state = {"job": dict(job or _job()), "charges": []}

    async def fake_duration(*_args, **_kwargs):
        return 110

    def fake_save(payload):
        state["job"] = dict(payload)
        return dict(payload)

    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: dict(state["job"]) if _job_id == state["job"].get("internal_job_id") else {})
    monkeypatch.setattr(bot, "get_engine_async_job_lookup", lambda _job_id: {"job": dict(state["job"]), "resolved_job_id": state["job"].get("internal_job_id"), "lookup_found": True} if _job_id == state["job"].get("internal_job_id") else {"job": {}, "resolved_job_id": "", "lookup_found": False})
    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)
    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", fake_duration)
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **_kwargs: {"vault_id": "MV-H14E", "storage_ref": str(_kwargs.get("job", {}).get("output_path") or "")})
    monkeypatch.setattr(bot, "get_music_vault_entry", lambda _vault_id: {"vault_id": _vault_id, "storage_ref": ""})
    monkeypatch.setattr(bot, "mark_music_vault_status", lambda *args, **kwargs: {"vault_id": args[0] if args else "MV-H14E"})
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: bool(admin))

    def fake_spend(*args, **_kwargs):
        state["charges"].append(args)
        return {"ok": bool(charge_ok), "final_cost": charged if charge_ok else 0, "status": "ok" if charge_ok else "fail"}

    monkeypatch.setattr(bot, "spend_fixed_credit_info", fake_spend)
    return state


def _deliver(monkeypatch, fake=None, result=None, job=None, *, admin=True, source="auto_tick", send_success=True, charge_ok=True, charged=200):
    state = _patch_store(monkeypatch, job or _job(), admin=admin, charge_ok=charge_ok, charged=charged)
    fake = fake or FakeBot()
    delivered = asyncio.run(
        bot.deliver_music_result_once(
            CaptureMessage(chat_id=USER_ID),
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


def test_music_success_sends_exactly_one_audio_file(monkeypatch):
    _reset()
    first, fake, _state = _deliver(monkeypatch)
    second = asyncio.run(bot.deliver_music_result_once(CaptureMessage(chat_id=USER_ID), _ctx(fake), user_id=USER_ID, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=first["result"], audio_bytes=AUDIO_BYTES, job=first["job"], send_success_message=True, source="worker"))
    assert first["ok"] is True
    assert second["duplicate"] is True
    assert len(fake.audio) == 1


def test_start_after_delivery_does_not_resend_audio(monkeypatch):
    _reset()
    first, fake, _state = _deliver(monkeypatch)
    saved = dict(first["result"])
    bot.save_music_guided_result(USER_ID, saved)
    stale_result = {k: v for k, v in _result().items() if k not in {"music_delivery_message_id", "music_result_delivered_at"}}
    second = asyncio.run(bot.deliver_music_result_once(CaptureMessage(chat_id=USER_ID), _ctx(fake), user_id=USER_ID, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=stale_result, audio_bytes=AUDIO_BYTES, job={}, send_success_message=True, source="start_rehydrate"))
    assert second["duplicate"] is True
    assert len(fake.audio) == 1


def test_refresh_after_delivery_does_not_resend_audio(monkeypatch):
    _reset()
    first, fake, _state = _deliver(monkeypatch)
    bot.save_music_guided_result(USER_ID, first["result"])
    refreshed = asyncio.run(bot.deliver_music_result_once(CaptureMessage(chat_id=USER_ID), _ctx(fake), user_id=USER_ID, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=first["result"], audio_bytes=AUDIO_BYTES, job=first["job"], send_success_message=True, source="manual_status_update"))
    assert refreshed["duplicate"] is True
    assert len(fake.audio) == 1


def test_recovery_after_delivery_does_not_resend_audio(monkeypatch):
    _reset()
    first, fake, state = _deliver(monkeypatch)
    state["job"] = first["job"]
    recovered = asyncio.run(bot.deliver_music_ready_artifact_once(JOB_ID, context=_ctx(fake), user_id=USER_ID, source="admin_recover"))
    assert recovered["duplicate"] is True
    assert len(fake.audio) == 1


def test_duplicate_artifact_hash_delivery_prevented(monkeypatch):
    _reset()
    first, fake, _state = _deliver(monkeypatch)
    second = asyncio.run(bot.deliver_music_result_once(CaptureMessage(chat_id=USER_ID), _ctx(fake), user_id=USER_ID, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result={**_result(), "selected_artifact_hash": bot.music_audio_sha256(AUDIO_BYTES)}, audio_bytes=AUDIO_BYTES, job={}, send_success_message=True, source="same_hash"))
    assert second["duplicate"] is True
    assert second["job"].get("duplicate_delivery_prevented") is True
    assert len(fake.audio) == 1
    assert first["result"]["delivered_artifact_hash"]


def test_success_panel_uses_actual_charge_state(monkeypatch):
    _reset()
    delivered, fake, state = _deliver(monkeypatch, admin=False, charged=200)
    assert delivered["charged_xu"] == 200
    assert state["charges"]
    assert "Đã trừ: 200 Xu" in fake.sent[0]["text"]


def test_success_panel_no_charge_reason_if_charged_zero(monkeypatch):
    _reset()
    delivered, fake, _state = _deliver(monkeypatch, admin=True)
    assert delivered["charged_xu"] == 0
    assert "Giá: 200 Xu" in fake.sent[0]["text"]
    assert "Đã trừ: 0 Xu (miễn phí/thử nghiệm)" in fake.sent[0]["text"]


def test_no_charge_before_audio_delivery(monkeypatch):
    _reset()
    state = _patch_store(monkeypatch, admin=False)
    fake = FakeBot()
    result = asyncio.run(bot.deliver_music_result_once(CaptureMessage(chat_id=USER_ID), _ctx(fake), user_id=USER_ID, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=_result(), audio_bytes=b"", job=state["job"], send_success_message=True, source="empty_audio"))
    assert result["ok"] is False
    assert state["charges"] == []
    assert len(fake.audio) == 0


def test_no_duplicate_charge_after_duplicate_delivery_attempt(monkeypatch):
    _reset()
    first, fake, state = _deliver(monkeypatch, admin=False, charged=200)
    second = asyncio.run(bot.deliver_music_result_once(CaptureMessage(chat_id=USER_ID), _ctx(fake), user_id=USER_ID, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=first["result"], audio_bytes=AUDIO_BYTES, job=first["job"], send_success_message=True, source="recover"))
    assert second["duplicate"] is True
    assert len(state["charges"]) == 1


def test_200_xu_prompt_presets_have_valid_style_prompt():
    audit = bot.music_product_prompt_preset_audit(mode="song", tier=bot.MUSIC_PRODUCT_TIER_BASIC, vocal_mode="female")
    assert len(audit) >= 9
    assert all(row["price_xu"] == 200 for row in audit)
    assert all(row["style_prompt_present"] for row in audit)
    assert all(row["lyrics_present"] for row in audit)


def test_lyrics_required_preset_asks_for_lyrics_once():
    _reset()
    user_id = USER_ID + 1
    bot.save_music_guided_result(user_id, {"music_product_mode": "song", "music_product_tier": bot.MUSIC_PRODUCT_TIER_BASIC, "song_vocal": "female"})
    bot.set_music_guided_pending(user_id, "music_product_song_details", product_context=bot.PRODUCT_CONTEXT_SHOWROOM)
    msg = CaptureMessage("Upbeat Indie pop, tropical house, clear warm vocals.", user_id)
    handled = asyncio.run(bot.handle_music_guided_pending_text(_message_update(msg, user_id), SimpleNamespace()))
    assert handled is True
    assert "Lời hát" in msg.outputs[-1]["text"]
    assert bot.get_music_guided_result(user_id)["music_product_pending_lyrics"] is True


def test_lyrics_supplied_routes_to_generation_not_prompt_loop():
    _reset()
    user_id = USER_ID + 2
    bot.save_music_guided_result(user_id, {"music_product_mode": "song", "music_product_tier": bot.MUSIC_PRODUCT_TIER_BASIC, "song_vocal": "female"})
    bot.set_music_guided_pending(user_id, "music_product_song_details", product_context=bot.PRODUCT_CONTEXT_SHOWROOM)
    style = CaptureMessage("Upbeat Indie pop, tropical house, clear warm vocals.", user_id)
    asyncio.run(bot.handle_music_guided_pending_text(_message_update(style, user_id), SimpleNamespace()))
    lyrics = CaptureMessage("Wake up to the morning light", user_id)
    handled = asyncio.run(bot.handle_music_guided_pending_text(_message_update(lyrics, user_id), SimpleNamespace()))
    result = bot.get_music_guided_result(user_id)
    assert handled is True
    assert "Xác nhận tạo bài hát" in lyrics.outputs[-1]["text"]
    assert "Upbeat Indie pop" in result["provider_style_prompt"]
    assert "Wake up to the morning light" in result["provider_lyrics"]
    assert not result.get("music_product_pending_lyrics")


def test_prompt_preset_audit_lists_all_basic_200_xu_presets():
    audit = bot.music_product_prompt_preset_audit(mode="song", tier="basic")
    assert {row["expected_route"] for row in audit} == {"music_product_song_details -> invoice -> music_ai_confirm"}
    assert all({"preset_id", "label", "package", "fixed"}.issubset(row) for row in audit)
    assert all(row["fixed"] for row in audit)


def test_current_working_music_engine_flow_locked(monkeypatch):
    _reset()
    delivered, fake, _state = _deliver(monkeypatch)
    assert delivered["job"]["terminal_state"] == "delivered"
    assert delivered["job"]["delivery_succeeded"] is True
    assert delivered["job"]["delivery_message_id"]
    assert delivered["job"]["delivered_artifact_hash"]
    assert delivered["job"]["terminal_public_outcome_sent"] is True
    assert len(fake.audio) == 1
    assert len(fake.sent) == 1


def test_no_product_video_subdub_payos_pricing_db_changes():
    changed = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True).splitlines()
    forbidden_prefixes = (
        "providers/video",
        "services/video",
        "services/subdub",
        "services/payos",
        "services/wallet",
        "services/payment",
        "config/pricing",
        "migrations/",
    )
    forbidden_exact = {"local_worker.py", "remote_worker.py", "providers/key4u_provider.py"}
    assert not [path for path in changed if path in forbidden_exact or path.startswith(forbidden_prefixes)]
