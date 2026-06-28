import asyncio
import re
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class CaptureMessage:
    def __init__(self, text="", user_id=120001):
        self.text = text
        self.chat_id = user_id
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"kind": "text", "text": text, **kwargs})
        return SimpleNamespace(message_id=len(self.outputs))

    async def reply_audio(self, audio=None, filename="", caption="", **kwargs):
        self.outputs.append({"kind": "audio", "audio": audio, "filename": filename, "caption": caption, **kwargs})
        return SimpleNamespace(audio=SimpleNamespace(file_id=f"file-{len(self.outputs)}"))


class CaptureQuery:
    def __init__(self, data="music_quick|showroom|music_ai_confirm", user_id=120001):
        self.data = data
        self.message = CaptureMessage(user_id=user_id)
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _message_update(message, user_id=120001):
    return SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id))


def _product_result(**overrides):
    data = {
        "music_product_mode": "background",
        "music_product_tier": "music_tier_standard",
        "description": "Nhạc nền cinematic cho video bán hàng",
        "genre": "cinematic pop",
        "mood": "tươi sáng",
        "duration_seconds": 60,
    }
    data.update(overrides)
    return bot.music_product_result_from_input(data)


def test_music_studio_has_instrumental_song_vault_edit():
    labels = _labels(bot.music_hub_keyboard("vi"))
    assert "🎼 Tạo nhạc nền" in labels
    assert "🎤 Bài hát có lời" in labels
    assert "📂 Kho nhạc" in labels
    assert "🎚 Cắt/ghép nhạc" in labels


def test_music_creation_has_three_tiers_only():
    labels = _labels(bot.music_product_tier_keyboard("background", "vi"))
    tier_labels = [item for item in labels if "Xu" in item]
    assert tier_labels == ["🎵 Cơ bản — 100 Xu", "🎶 Tiêu chuẩn — 150 Xu", "💎 Cao cấp — 200 Xu"]


def test_music_tier_basic_price_100():
    assert bot.music_product_tier_price_xu("basic") == 100


def test_music_tier_standard_price_150():
    assert bot.music_product_tier_price_xu("standard", "background") == 150


def test_music_tier_premium_price_200():
    assert bot.music_product_tier_price_xu("premium", "background") == 200


def test_music_tier_maps_to_model_preferences():
    assert bot.select_music_model_for_tier("basic") == "chirp-v3.5"
    assert bot.select_music_model_for_tier("standard") == "chirp-auk"
    assert bot.select_music_model_for_tier("premium") == "chirp-fenix"
    assert bot.select_music_model_for_tier("premium", supported_models=["chirp-bluejay"], provider_default="chirp-v4") == "chirp-bluejay"


def test_music_model_ids_not_shown_public():
    text = "\n".join([
        bot.music_product_tier_selection_text("background", "vi"),
        bot.music_product_invoice_text(_product_result(), "vi"),
        "\n".join(_labels(bot.music_product_tier_keyboard("song", "vi"))),
    ]).lower()
    for forbidden in ("chirp", "provider", "api", "key4u", "shopaikey", "suno"):
        assert forbidden not in text


def test_music_prompt_builder_preserves_style_theme_mood():
    built = bot.build_music_product_prompt({
        "music_product_mode": "background",
        "tier": "standard",
        "description": "Nhạc nền cho showroom",
        "genre": "future bass",
        "mood": "sang trọng",
        "duration_seconds": 60,
    })
    style = built["provider_style_prompt"]
    assert "Nhạc nền cho showroom" in style
    assert "future bass" in style
    assert "sang trọng" in style
    assert built["provider_lyrics"] == ""


def test_song_prompt_builder_keeps_lyrics_separate():
    built = bot.build_music_product_prompt({
        "music_product_mode": "song",
        "theme": "thương hiệu cà phê",
        "genre": "pop",
        "mood": "ấm áp",
        "lyrics": "[Verse]\nLy cà phê thơm",
    })
    assert "thương hiệu cà phê" in built["provider_style_prompt"]
    assert built["provider_lyrics"].startswith("[Verse]")
    assert "[Verse]" not in built["provider_style_prompt"]


def test_song_prompt_builder_preserves_lyrics_tags():
    lyrics = "[Intro]\nXin chào\n[Pre-Chorus]\nLên cao\n[Chorus]\nTỏa sáng"
    built = bot.build_music_product_prompt({"music_product_mode": "song", "lyrics": lyrics})
    assert built["provider_lyrics"] == lyrics


def test_song_prompt_builder_male_removes_female_conflict():
    built = bot.build_music_product_prompt({
        "music_product_mode": "song",
        "description": "female vocal ballad",
        "vocal_mode": "male",
        "lyrics": "Một ngày mới",
    })
    style = built["provider_style_prompt"].lower()
    assert "female vocal" not in style
    assert "male lead vocal" in style


def test_song_prompt_builder_female_removes_male_conflict():
    built = bot.build_music_product_prompt({
        "music_product_mode": "song",
        "description": "male vocal pop",
        "vocal_mode": "female",
        "lyrics": "Một ngày mới",
    })
    style = built["provider_style_prompt"].lower()
    assert not re.search(r"\bmale\s+vocal\b", style)
    assert "female lead vocal" in style


def test_song_prompt_builder_duet_adds_duet_instructions():
    built = bot.build_music_product_prompt({
        "music_product_mode": "song",
        "vocal_mode": "duet",
        "lyrics": "Câu một\nCâu hai\nĐiệp khúc",
    })
    assert "male and female duet" in built["provider_style_prompt"]
    assert "[Male Verse]" in built["provider_lyrics"]
    assert "[Female Verse]" in built["provider_lyrics"]
    assert "[Duet Chorus]" in built["provider_lyrics"]


def test_toan_aas_song_prompt_builds_expected_fields():
    built = bot.build_music_product_prompt({"music_product_mode": "song", "tier": "premium", "lyrics": "TOAN AAS tỏa sáng"})
    assert set(built) == {"provider_style_prompt", "provider_lyrics", "provider_title", "provider_metadata"}
    assert built["provider_metadata"]["tier"] == "music_tier_premium"
    assert built["provider_metadata"]["selected_model_key"] == "chirp-fenix"
    assert built["provider_metadata"]["prompt_hash"]


def test_song_male_vocal_mapping():
    assert bot.music_product_vocal_instructions("male").startswith("male lead vocal")


def test_song_female_vocal_mapping():
    assert bot.music_product_vocal_instructions("female").startswith("female lead vocal")


def test_song_duet_vocal_mapping():
    assert "duet chorus" in bot.music_product_vocal_instructions("duet")


def test_song_auto_vocal_mapping():
    assert bot.music_product_vocal_instructions("auto") == ""


def test_female_selection_not_male_prompt():
    built = bot.build_music_product_prompt({"music_product_mode": "song", "vocal_mode": "female", "description": "male singer", "lyrics": "x"})
    assert not re.search(r"\bmale\s+singer\b", built["provider_style_prompt"].lower())


def test_duet_selection_supports_male_female():
    built = bot.build_music_product_prompt({"music_product_mode": "song", "vocal_mode": "duet", "lyrics": "x"})
    style = built["provider_style_prompt"].lower()
    assert "male and female duet" in style


def test_music_invoice_before_provider_call(monkeypatch):
    user_id = 120101
    bot.save_music_guided_result(user_id, {"music_product_flow": "p0_20a_3_tier", "music_product_mode": "background", "music_product_tier": "music_tier_basic"})
    bot.set_music_guided_pending(user_id, "music_product_background_details", product_context=bot.PRODUCT_CONTEXT_SHOWROOM)
    monkeypatch.setattr(bot, "execute_engine", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider called before invoice")))
    message = CaptureMessage("Mô tả: nhạc nền bán hàng\nThể loại: pop\nCảm xúc: vui\nThời lượng: 60 giây", user_id)
    handled = asyncio.run(bot.handle_music_guided_pending_text(_message_update(message, user_id), SimpleNamespace()))
    assert handled is True
    assert "Xác nhận tạo nhạc nền" in message.outputs[-1]["text"]


def test_music_no_provider_before_confirm(monkeypatch):
    user_id = 120102
    bot.save_music_guided_result(user_id, {"music_product_flow": "p0_20a_3_tier", "music_product_mode": "song", "music_product_tier": "music_tier_premium", "song_vocal": "female"})
    bot.set_music_guided_pending(user_id, "music_product_song_details", product_context=bot.PRODUCT_CONTEXT_SHOWROOM)
    monkeypatch.setattr(bot, "execute_engine", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider called before confirm")))
    message = CaptureMessage("Tiêu đề: Cafe\nChủ đề: quán mới\nThể loại: pop\nCảm xúc: vui\nLời hát:\n[Verse]\nCafe thơm", user_id)
    handled = asyncio.run(bot.handle_music_guided_pending_text(_message_update(message, user_id), SimpleNamespace()))
    assert handled is True
    assert "Xác nhận tạo bài hát" in message.outputs[-1]["text"]


def test_music_no_charge_before_confirm(monkeypatch):
    user_id = 120103
    bot.save_music_guided_result(user_id, {"music_product_flow": "p0_20a_3_tier", "music_product_mode": "background", "music_product_tier": "music_tier_standard"})
    bot.set_music_guided_pending(user_id, "music_product_background_details", product_context=bot.PRODUCT_CONTEXT_SHOWROOM)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("charged before confirm")))
    message = CaptureMessage("Mô tả: nhạc nền review\nThể loại: acoustic\nCảm xúc: nhẹ", user_id)
    assert asyncio.run(bot.handle_music_guided_pending_text(_message_update(message, user_id), SimpleNamespace())) is True
    assert "Tổng thanh toán" in message.outputs[-1]["text"]


def test_music_charge_after_success(monkeypatch):
    user_id = 120104
    order = []
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: False)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: order.append("charge") or {"ok": True, "final_cost": 200})
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **kwargs: {"vault_id": "MV1", "storage_ref": ""})
    result = _product_result()
    message = CaptureMessage(user_id=user_id)

    async def tracked_reply_audio(*args, **kwargs):
        order.append("send")
        return SimpleNamespace(audio=SimpleNamespace(file_id="file-success"))

    message.reply_audio = tracked_reply_audio
    delivered = asyncio.run(bot.send_music_product_audio_result(message, SimpleNamespace(), user_id=user_id, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=result, audio_bytes=b"real-audio"))
    assert delivered["ok"] is True
    assert delivered["charged_xu"] == 200
    assert order == ["send", "charge"]


def test_music_no_charge_on_provider_fail(monkeypatch):
    user_id = 120105
    result = _product_result()
    monkeypatch.setattr(bot, "can_user_access_product_engine", lambda *args, **kwargs: {"allowed": True})
    monkeypatch.setattr(bot, "get_user", lambda uid: (1000, None, None))

    async def fail_engine(*args, **kwargs):
        return {"ok": False, "status": "FAILED", "detail": "provider failed"}

    monkeypatch.setattr(bot, "execute_engine", fail_engine)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("charged on provider fail")))
    query = CaptureQuery(user_id=user_id)
    asyncio.run(bot.handle_music_product_confirm(query, SimpleNamespace(), user_id=user_id, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=result))
    assert "chưa trừ Xu" in query.message.outputs[-1]["text"]


def test_music_admin_shows_price_but_charges_zero(monkeypatch):
    user_id = 120106
    result = _product_result(music_product_tier="music_tier_premium")
    assert "200 Xu" in bot.music_product_invoice_text(result, "vi")
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: True)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("admin charged")))
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **kwargs: {"vault_id": "MV1", "storage_ref": ""})
    message = CaptureMessage(user_id=user_id)
    delivered = asyncio.run(bot.send_music_product_audio_result(message, SimpleNamespace(), user_id=user_id, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=result, audio_bytes=b"real-audio"))
    assert delivered["charged_xu"] == 0


def test_music_auto_sends_result_after_completion(monkeypatch):
    user_id = 120107
    result = _product_result()
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: False)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: {"ok": True, "final_cost": 200})
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **kwargs: {"vault_id": "MV2", "storage_ref": ""})

    async def fake_poll(*args, **kwargs):
        return {"ok": True, "status": "COMPLETED", "audio_bytes": b"real-audio", "job": {"internal_job_id": "MUS1", "status": "completed"}}

    monkeypatch.setattr(bot, "poll_music_suno_async_job", fake_poll)
    query = CaptureQuery(user_id=user_id)
    delivered = asyncio.run(bot.music_product_auto_deliver_job(query, SimpleNamespace(), user_id=user_id, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=result, internal_job_id="MUS1"))
    assert delivered["ok"] is True
    assert query.message.outputs[0]["kind"] == "audio"


def test_music_check_result_no_duplicate_send(monkeypatch):
    user_id = 120108
    result = {**_product_result(), "music_result_delivered_at": "now", "music_charged_xu": 200}
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("duplicate charged")))
    message = CaptureMessage(user_id=user_id)
    delivered = asyncio.run(bot.send_music_product_audio_result(message, SimpleNamespace(), user_id=user_id, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=result, audio_bytes=b"real-audio"))
    assert delivered["duplicate"] is True
    assert not message.outputs


def test_music_delivery_idempotent(monkeypatch):
    user_id = 120109
    result = _product_result()
    job = {"sent_full_at": "now", "output_file_id": "file-old", "output_sha256": bot.music_audio_sha256(b"real-audio"), "charged_xu": 200}
    message = CaptureMessage(user_id=user_id)
    delivered = asyncio.run(bot.send_music_product_audio_result(message, SimpleNamespace(), user_id=user_id, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=result, audio_bytes=b"real-audio", job=job))
    assert delivered["duplicate"] is True
    assert delivered["charged_xu"] == 200


def test_music_empty_result_not_success():
    result = _product_result()
    message = CaptureMessage()
    delivered = asyncio.run(bot.send_music_product_audio_result(message, SimpleNamespace(), user_id=120110, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=result, audio_bytes=b""))
    assert delivered["ok"] is False
    assert delivered["status"] == "EMPTY_AUDIO"


def test_music_success_can_save_to_vault(monkeypatch):
    user_id = 120111
    saved = {}
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: False)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: {"ok": True, "final_cost": 100})
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **kwargs: saved.update(kwargs) or {"vault_id": "MV-SAVED", "storage_ref": ""})
    result = _product_result(music_product_tier="music_tier_basic")
    message = CaptureMessage(user_id=user_id)
    delivered = asyncio.run(bot.send_music_product_audio_result(message, SimpleNamespace(), user_id=user_id, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=result, audio_bytes=b"real-audio"))
    assert delivered["result"]["music_vault_id"] == "MV-SAVED"
    assert saved["status"] == "used"


def test_public_music_ready_flags_on_only_after_stable():
    off = bot.music_product_public_ready_flags({"ready": True, "public_enabled": False, "full_result_ok": True, "cost_gate_ok": True})
    on = bot.music_product_public_ready_flags({"ready": True, "public_enabled": True, "full_result_ok": True, "cost_gate_ok": True})
    assert off["Music"] is False
    assert on["Music"] is True
    assert on["AI Music"] is True
    assert on["AI Song"] is True
    assert on["Music Vault"] is True


def test_no_technical_words_in_music_public_ui():
    result = _product_result()
    public = "\n".join([
        bot.music_hub_text("vi"),
        bot.music_product_tier_selection_text("song", "vi"),
        bot.music_product_details_input_text("song", "music_tier_standard", "female", "vi"),
        bot.music_product_invoice_text(result, "vi"),
        "\n".join(_labels(bot.music_product_invoice_keyboard(result, "vi"))),
        "\n".join(_callbacks(bot.music_product_invoice_keyboard(result, "vi"))),
    ]).lower()
    for forbidden in ("provider", "api", "key4u", "shopaikey", "suno", "traceback", "diagnostic", "raw"):
        assert forbidden not in public
