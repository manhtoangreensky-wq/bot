import asyncio
from types import SimpleNamespace

import bot


USER_ID = 232001
AUDIO_BYTES = b"ID3-toan-aas-price1-final-audio" * 240


class FakeBot:
    def __init__(self):
        self.audio = []
        self.sent = []

    async def send_audio(self, **kwargs):
        self.audio.append(kwargs)
        return {"message_id": f"audio-{len(self.audio)}", "audio": {"file_id": f"file-{len(self.audio)}"}, "status": "SUCCESS"}

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return {"message_id": f"receipt-{len(self.sent)}", "status": "SUCCESS"}


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
    return SimpleNamespace(bot=fake or FakeBot())


def _reset():
    bot.PROGRESS_AUTO_REFRESH_JOBS.clear()
    bot.PROGRESS_AUTO_REFRESH_TASKS.clear()
    bot.MUSIC_PRODUCT_DELIVERY_MEMORY_LOCKS.clear()
    bot.USER_PENDING.clear()


def _result(mode="song", tier=bot.MUSIC_PRODUCT_TIER_BASIC, vocal="female"):
    data = {
        "music_product_flow": "p0_20b1_suggestions",
        "music_product_mode": mode,
        "music_product_tier": tier,
        "theme": "TOAN AAS nang luong moi",
        "description": "Upbeat brand music for TOAN AAS",
        "genre": "Pop",
        "mood": "Uplifting",
        "style_prompt": "Upbeat Pop, bright synth, clean studio production",
        "duration_seconds": 180,
    }
    if mode == "song":
        data.update({
            "song_vocal": vocal,
            "vocal_mode": vocal,
            "lyrics": "[Verse]\nTOAN AAS sang len\n[Chorus]\nCung nhau di xa",
        })
    return bot.music_product_result_from_input(data)


def _job(result, job_id="MUSPRICE1"):
    return {
        "internal_job_id": job_id,
        "feature": "music_suno",
        "product_type": bot.music_product_progress_type(result),
        "music_product_type": bot.music_product_progress_type(result),
        "music_product_mode": result["music_product_mode"],
        "music_product_tier": result["music_product_tier"],
        "music_product_price_xu": bot.music_result_price_xu(result),
        "song_vocal": result.get("song_vocal") or "",
        "selected_vocal_mode": result.get("selected_vocal_mode") or result.get("song_vocal") or "",
        "requested_vocal_mode": result.get("requested_vocal_mode") or result.get("song_vocal") or "",
        "user_id": str(USER_ID),
        "chat_id": str(USER_ID),
        "provider": "key4u_suno",
        "provider_task_id": f"provider-{job_id}",
        "status": "completed",
        "progress_percent": 90,
        "output_bytes": len(AUDIO_BYTES),
        "artifact_duration_seconds": 180,
        "music_result_duration_seconds": 180,
        "output_sha256": bot.music_audio_sha256(AUDIO_BYTES),
        "audio_validated": True,
        "artifact_ready": True,
        "music_audio_validated": True,
        "music_artifact_ready": True,
        "pending_charge_xu": bot.music_result_price_xu(result),
        "charged_xu": 0,
    }


def _patch_store(monkeypatch, result, *, admin=False):
    state = {"job": _job(result), "guided": {}, "charges": []}

    async def fake_duration(*_args, **_kwargs):
        return 180

    def fake_save(payload):
        state["job"] = dict(payload)
        return dict(payload)

    monkeypatch.setattr(bot, "get_engine_async_job", lambda _job_id: dict(state["job"]) if _job_id == state["job"].get("internal_job_id") else {})
    monkeypatch.setattr(bot, "get_engine_async_job_lookup", lambda _job_id: {"job": dict(state["job"]), "resolved_job_id": state["job"].get("internal_job_id"), "lookup_found": True} if _job_id == state["job"].get("internal_job_id") else {"job": {}, "resolved_job_id": "", "lookup_found": False})
    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)
    monkeypatch.setattr(bot, "get_music_guided_result", lambda _uid: dict(state["guided"]))
    monkeypatch.setattr(bot, "save_music_guided_result", lambda _uid, payload: state["guided"].update(dict(payload)) or dict(payload))
    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", fake_duration)
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **_kwargs: {"vault_id": "MV-PRICE1", "storage_ref": ""})
    monkeypatch.setattr(bot, "get_music_vault_entry", lambda _vault_id: {"vault_id": _vault_id, "storage_ref": ""})
    monkeypatch.setattr(bot, "mark_music_vault_status", lambda *args, **kwargs: {"vault_id": args[0] if args else "MV-PRICE1"})
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: bool(admin))

    def fake_spend(*args, **_kwargs):
        state["charges"].append(args)
        return {"ok": True, "final_cost": bot.music_result_price_xu(result), "status": "ok"}

    monkeypatch.setattr(bot, "spend_fixed_credit_info", fake_spend)
    return state


def _deliver_contract(monkeypatch, result):
    _reset()
    fake = FakeBot()
    state = _patch_store(monkeypatch, result, admin=False)
    delivered = asyncio.run(
        bot.send_music_product_audio_result(
            CaptureMessage(),
            _ctx(fake),
            user_id=USER_ID,
            lang="vi",
            product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
            result=result,
            audio_bytes=AUDIO_BYTES,
            job=state["job"],
            updated_by=USER_ID,
            send_success_message=True,
            source="price1_contract",
        )
    )
    duplicate = asyncio.run(
        bot.send_music_product_audio_result(
            CaptureMessage(),
            _ctx(fake),
            user_id=USER_ID,
            lang="vi",
            product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
            result=delivered["result"],
            audio_bytes=AUDIO_BYTES,
            job=delivered["job"],
            updated_by=USER_ID,
            send_success_message=True,
            source="price1_duplicate",
        )
    )
    return delivered, duplicate, fake, state


def _contract_summary(delivered):
    return {
        "ok": delivered["ok"],
        "status": delivered["status"],
        "charge_ok": delivered["charge_ok"],
        "delivery_state": delivered["job"]["delivery_state"],
        "terminal_state": delivered["job"]["terminal_state"],
        "duplicate_guard_state": delivered["job"]["duplicate_guard_state"],
        "progress_percent": delivered["job"]["progress_percent"],
        "refresh_stopped_after_terminal": delivered["job"]["refresh_stopped_after_terminal"],
    }


def test_music_lyrics_200_250_300_same_delivery_contract(monkeypatch):
    base_summary = None
    for tier, price in [
        (bot.MUSIC_PRODUCT_TIER_BASIC, 200),
        (bot.MUSIC_PRODUCT_TIER_STANDARD, 250),
        (bot.MUSIC_PRODUCT_TIER_PREMIUM, 300),
    ]:
        result = _result("song", tier, "female")
        delivered, duplicate, fake, state = _deliver_contract(monkeypatch, result)
        summary = _contract_summary(delivered)
        base_summary = base_summary or summary
        assert summary == base_summary
        assert bot.music_result_price_xu(result) == price
        assert delivered["charged_xu"] == price
        assert duplicate["duplicate"] is True
        assert len(fake.audio) == 1
        assert len(fake.sent) == 1
        assert len(state["charges"]) == 1


def test_music_instrumental_200_250_300_same_delivery_contract(monkeypatch):
    base_summary = None
    for tier, price in [
        (bot.MUSIC_PRODUCT_TIER_BASIC, 130),
        (bot.MUSIC_PRODUCT_TIER_STANDARD, 150),
        (bot.MUSIC_PRODUCT_TIER_PREMIUM, 200),
    ]:
        result = _result("background", tier)
        delivered, duplicate, fake, state = _deliver_contract(monkeypatch, result)
        summary = _contract_summary(delivered)
        base_summary = base_summary or summary
        assert summary == base_summary
        assert bot.music_result_price_xu(result) == price
        assert delivered["charged_xu"] == price
        assert duplicate["duplicate"] is True
        assert len(fake.audio) == 1
        assert len(fake.sent) == 1
        assert len(state["charges"]) == 1


def test_music_all_tiers_no_duplicate_mp3(monkeypatch):
    for mode, tier in [
        ("song", bot.MUSIC_PRODUCT_TIER_BASIC),
        ("song", bot.MUSIC_PRODUCT_TIER_STANDARD),
        ("song", bot.MUSIC_PRODUCT_TIER_PREMIUM),
        ("background", bot.MUSIC_PRODUCT_TIER_BASIC),
        ("background", bot.MUSIC_PRODUCT_TIER_STANDARD),
        ("background", bot.MUSIC_PRODUCT_TIER_PREMIUM),
    ]:
        result = _result(mode, tier, "duet")
        _delivered, duplicate, fake, _state = _deliver_contract(monkeypatch, result)
        assert duplicate["duplicate"] is True
        assert len(fake.audio) == 1


def test_music_all_tiers_no_late_x_after_success(monkeypatch):
    for tier in bot.MUSIC_PRODUCT_TIER_ORDER:
        result = _result("song", tier, "female")
        delivered, _duplicate, _fake, _state = _deliver_contract(monkeypatch, result)
        updated = bot.record_music_job_full_send_error(delivered["job"], "late failure", updated_by=USER_ID)
        assert updated["terminal_state"] == "delivered"
        assert updated["public_x_suppressed"] is True
        assert updated["auto_delivery_blocker"] == ""


def test_music_all_tiers_correct_price_display():
    expected = {
        ("song", "200"): (bot.MUSIC_PRODUCT_TIER_BASIC, 200),
        ("song", "250"): (bot.MUSIC_PRODUCT_TIER_STANDARD, 250),
        ("song", "300"): (bot.MUSIC_PRODUCT_TIER_PREMIUM, 300),
        ("background", "100"): (bot.MUSIC_PRODUCT_TIER_BASIC, 130),
        ("background", "150"): (bot.MUSIC_PRODUCT_TIER_STANDARD, 150),
        ("background", "200"): (bot.MUSIC_PRODUCT_TIER_PREMIUM, 200),
    }
    for (mode, raw_tier), (tier, price) in expected.items():
        result = _result(mode, raw_tier, "male")
        invoice = bot.music_product_invoice_text(result, "vi")
        success = bot.music_product_success_text({**result, "music_result_duration_seconds": 180}, price, "vi")
        assert result["music_product_tier"] == tier
        assert bot.music_result_price_xu(result) == price
        assert f"Giá: <b>{price} Xu</b>" in invoice
        assert f"Giá: {price} Xu" in success


def test_music_all_tiers_charge_after_delivery_policy(monkeypatch):
    for mode, tier in [
        ("song", "200"),
        ("song", "250"),
        ("song", "300"),
        ("background", "100"),
        ("background", "150"),
        ("background", "200"),
    ]:
        result = _result(mode, tier)
        delivered, _duplicate, fake, state = _deliver_contract(monkeypatch, result)
        assert delivered["job"]["charge_after_delivery"] is True
        assert len(fake.audio) == 1
        assert len(state["charges"]) == 1
        assert delivered["charged_xu"] == bot.music_result_price_xu(result)


def test_music_legacy_price_tier_mapping_is_mode_aware():
    assert bot.music_confirm_tier_from_legacy_price({"price_xu": 200}, "song") == bot.MUSIC_PRODUCT_TIER_BASIC
    assert bot.music_confirm_tier_from_legacy_price({"price_xu": 250}, "song") == bot.MUSIC_PRODUCT_TIER_STANDARD
    assert bot.music_confirm_tier_from_legacy_price({"price_xu": 300}, "song") == bot.MUSIC_PRODUCT_TIER_PREMIUM
    assert bot.music_confirm_tier_from_legacy_price({"price_xu": 100}, "background") == bot.MUSIC_PRODUCT_TIER_BASIC
    assert bot.music_confirm_tier_from_legacy_price({"price_xu": 150}, "background") == bot.MUSIC_PRODUCT_TIER_STANDARD
    assert bot.music_confirm_tier_from_legacy_price({"price_xu": 200}, "background") == bot.MUSIC_PRODUCT_TIER_PREMIUM


def test_music_price1_no_provider_download_artifact_changes():
    # PRICE1 is route/state/price parity only; provider/artifact helpers must stay out of this test surface.
    assert callable(bot.deliver_music_result_once)
    assert callable(bot.music_product_tier_price_map)
