import asyncio
import re
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class CaptureMessage:
    def __init__(self, text="", user_id=220001):
        self.text = text
        self.chat_id = user_id
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"kind": "text", "text": text, **kwargs})
        return SimpleNamespace(message_id=len(self.outputs))

    async def reply_audio(self, audio=None, filename="", caption="", **kwargs):
        self.outputs.append({"kind": "audio", "audio": audio, "filename": filename, "caption": caption, **kwargs})
        return SimpleNamespace(message_id=len(self.outputs), audio=SimpleNamespace(file_id=f"file-{len(self.outputs)}"))


class CaptureQuery:
    def __init__(self, data, user_id=220001):
        self.data = data
        self.message = CaptureMessage(user_id=user_id)
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _update_with_query(data, user_id=220001):
    return SimpleNamespace(callback_query=CaptureQuery(data, user_id), effective_user=SimpleNamespace(id=user_id))


def _message_update(message, user_id=220001):
    return SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id))


def _song_state(user_id=220001, tier="music_tier_basic", vocal="female", idea="Bài hát thương hiệu TOAN AAS vui tươi"):
    state = {
        "music_product_flow": "p0_20b1_suggestions",
        "music_product_mode": "song",
        "music_product_tier": tier,
        "song_vocal": vocal,
        "vocal_mode": vocal,
        "music_user_idea": idea,
    }
    prepared = bot.music_product_prepare_suggestions_result(state, idea=idea, offset=0, lang="vi")
    bot.save_music_guided_result(user_id, prepared)
    return prepared


def _background_state(user_id=220002, tier="music_tier_basic", idea="Nhạc nền công nghệ AI vui tươi"):
    state = {
        "music_product_flow": "p0_20b1_suggestions",
        "music_product_mode": "background",
        "music_product_tier": tier,
        "music_user_idea": idea,
    }
    prepared = bot.music_product_prepare_suggestions_result(state, idea=idea, offset=0, lang="vi")
    bot.save_music_guided_result(user_id, prepared)
    return prepared


def test_song_flow_after_vocal_asks_short_idea_not_manual_template():
    user_id = 220010
    bot.save_music_guided_result(user_id, {"music_product_mode": "song", "music_product_tier": "music_tier_basic"})
    update = _update_with_query("music_quick|showroom|music_vocal:female", user_id)
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    text = update.callback_query.message.outputs[-1]["text"]
    assert "Ý tưởng bài hát" in text
    assert "Tiêu đề:" not in text
    assert "Lời hát:" not in text


def test_song_flow_generates_three_suggestions():
    user_id = 220011
    bot.save_music_guided_result(user_id, {"music_product_mode": "song", "music_product_tier": "music_tier_basic", "song_vocal": "female"})
    bot.set_music_guided_pending(user_id, "music_product_song_idea", product_context=bot.PRODUCT_CONTEXT_SHOWROOM)
    message = CaptureMessage("Bài hát thương hiệu TOAN AAS, vui tươi, công nghệ AI", user_id)
    handled = asyncio.run(bot.handle_music_guided_pending_text(_message_update(message, user_id), SimpleNamespace()))
    state = bot.get_music_guided_result(user_id)
    assert handled is True
    assert len(state["music_suggestions"]) == 3
    assert "TOAN AAS đã chuẩn bị 3 gợi ý bài hát" in message.outputs[-1]["text"]


def test_song_flow_has_regenerate_suggestions_button():
    labels = _labels(bot.music_product_suggestions_keyboard("song", "vi"))
    assert "🔄 Đổi gợi ý" in labels


def test_song_regenerate_keeps_tier_and_vocal():
    user_id = 220012
    _song_state(user_id, tier="music_tier_premium", vocal="female")
    update = _update_with_query("music_quick|showroom|music_product_regenerate_suggestions", user_id)
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    state = bot.get_music_guided_result(user_id)
    assert state["music_product_tier"] == "music_tier_premium"
    assert state["song_vocal"] == "female"
    assert state["music_suggestion_offset"] == 3
    assert len(state["music_suggestions"]) == 3


def test_song_select_suggestion_goes_to_invoice():
    user_id = 220013
    _song_state(user_id, tier="music_tier_standard", vocal="duet")
    update = _update_with_query("music_quick|showroom|music_product_select_suggestion:2", user_id)
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    text = update.callback_query.message.outputs[-1]["text"]
    assert "Xác nhận tạo bài hát" in text
    assert "250 Xu" in text
    assert "Song ca" in text


def test_song_manual_template_only_after_custom_button():
    user_id = 220014
    _song_state(user_id, vocal="male")
    update = _update_with_query("music_quick|showroom|music_product_manual", user_id)
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    text = update.callback_query.message.outputs[-1]["text"]
    assert "Style nhạc" in text
    assert "Male vocal" in text
    assert "Lời hát:" not in text


def test_toan_aas_sample_idea_generates_three_suggestions():
    user_id = 220015
    bot.save_music_guided_result(user_id, {"music_product_mode": "background", "music_product_tier": "music_tier_basic"})
    update = _update_with_query("music_quick|showroom|music_product_sample_idea", user_id)
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    state = bot.get_music_guided_result(user_id)
    assert state["music_user_idea"] == bot.music_product_sample_idea("background").rstrip(".")
    assert len(state["music_suggestions"]) == 3


def test_instrumental_prices_100_150_200():
    labels = [label for label in _labels(bot.music_product_tier_keyboard("background", "vi")) if "Xu" in label]
    assert labels == ["🎵 Cơ bản — 100 Xu", "🎶 Tiêu chuẩn — 150 Xu", "💎 Cao cấp — 200 Xu"]
    assert bot.music_product_tier_price_xu("basic", "background") == 100
    assert bot.music_product_tier_price_xu("standard", "background") == 150
    assert bot.music_product_tier_price_xu("premium", "background") == 200


def test_instrumental_generates_three_suggestions():
    suggestions = bot.build_music_product_suggestions(mode="background", tier="basic", idea="Nhạc nền quảng cáo AI")
    assert len(suggestions) == 3
    assert all(item["lyrics"] == "" for item in suggestions)


def test_instrumental_suggestions_have_no_vocal_by_default():
    text = " ".join(item["style_prompt"] for item in bot.build_music_product_suggestions(mode="background", tier="basic", idea="Nhạc nền"))
    assert "no vocals" in text.lower()
    assert "female lead" not in text.lower()
    assert "male lead" not in text.lower()


def test_instrumental_provider_request_sets_no_lyrics_instrumental():
    state = _background_state()
    result = bot.music_product_result_from_suggestion(state, state["music_suggestions"][0])
    payload = bot.shopaikey_suno_submit_payload(
        result["provider_style_prompt"],
        title=result["provider_title"],
        instrumental=bot.music_result_product_kind(result) == "background",
        lyrics=result["provider_lyrics"],
    )
    assert payload["make_instrumental"] is True
    assert "prompt" not in payload
    assert "no vocals" in payload["gpt_description_prompt"].lower()


def test_song_prices_200_250_300():
    labels = [label for label in _labels(bot.music_product_tier_keyboard("song", "vi")) if "Xu" in label]
    assert labels == ["🎵 Cơ bản — 200 Xu", "🎶 Tiêu chuẩn — 250 Xu", "💎 Cao cấp — 300 Xu"]
    assert bot.music_product_tier_price_xu("basic", "song") == 200
    assert bot.music_product_tier_price_xu("standard", "song") == 250
    assert bot.music_product_tier_price_xu("premium", "song") == 300


def test_song_provider_request_has_lyrics_field():
    state = _song_state(vocal="female")
    result = bot.music_product_result_from_suggestion(state, state["music_suggestions"][0])
    payload = bot.shopaikey_suno_submit_payload(
        result["provider_style_prompt"],
        title=result["provider_title"],
        instrumental=False,
        lyrics=result["provider_lyrics"],
    )
    assert payload["make_instrumental"] is False
    assert payload["prompt"].startswith("[Verse]")


def test_song_provider_request_has_style_field():
    state = _song_state(vocal="duet")
    result = bot.music_product_result_from_suggestion(state, state["music_suggestions"][0])
    payload = bot.shopaikey_suno_submit_payload(result["provider_style_prompt"], instrumental=False, lyrics=result["provider_lyrics"])
    assert payload["gpt_description_prompt"]
    assert "duet" in payload["gpt_description_prompt"].lower()


def test_song_invoice_before_provider_call(monkeypatch):
    user_id = 220016
    state = _song_state(user_id, vocal="female")
    monkeypatch.setattr(bot, "execute_engine", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider before confirm")))
    update = _update_with_query("music_quick|showroom|music_product_select_suggestion:1", user_id)
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    assert "Xác nhận tạo bài hát" in update.callback_query.message.outputs[-1]["text"]
    assert bot.get_music_guided_result(user_id)["music_confirmed"] is False


def test_song_no_provider_before_confirm(monkeypatch):
    user_id = 220017
    bot.save_music_guided_result(user_id, {"music_product_mode": "song", "music_product_tier": "music_tier_basic", "song_vocal": "female"})
    bot.set_music_guided_pending(user_id, "music_product_song_idea", product_context=bot.PRODUCT_CONTEXT_SHOWROOM)
    monkeypatch.setattr(bot, "execute_engine", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider before confirm")))
    message = CaptureMessage("Bài hát công nghệ AI vui tươi", user_id)
    assert asyncio.run(bot.handle_music_guided_pending_text(_message_update(message, user_id), SimpleNamespace())) is True
    assert "3 gợi ý bài hát" in message.outputs[-1]["text"]


def test_song_female_prompt_removes_male_conflict():
    built = bot.build_music_product_prompt({"music_product_mode": "song", "description": "male vocal pop", "vocal_mode": "female", "lyrics": "x"})
    assert not re.search(r"\bmale\s+vocal\b", built["provider_style_prompt"].lower())
    assert "female lead vocal" in built["provider_style_prompt"].lower()


def test_song_male_prompt_removes_female_conflict():
    built = bot.build_music_product_prompt({"music_product_mode": "song", "description": "female vocal pop", "vocal_mode": "male", "lyrics": "x"})
    assert "female vocal" not in built["provider_style_prompt"].lower()
    assert "male lead vocal" in built["provider_style_prompt"].lower()


def test_song_duet_prompt_has_male_female_duet():
    built = bot.build_music_product_prompt({"music_product_mode": "song", "vocal_mode": "duet", "lyrics": "Câu 1\nCâu 2\nĐiệp khúc"})
    assert "male and female duet" in built["provider_style_prompt"].lower()
    assert "[Male Verse]" in built["provider_lyrics"]


def test_song_auto_prompt_no_forced_gender():
    built = bot.build_music_product_prompt({"music_product_mode": "song", "vocal_mode": "auto", "lyrics": "x"})
    style = built["provider_style_prompt"].lower()
    assert "male lead vocal" not in style
    assert "female lead vocal" not in style


def test_music_model_quality_differs_by_tier():
    assert bot.select_music_model_for_tier("basic", mode="background") != bot.select_music_model_for_tier("premium", mode="background")
    assert bot.select_music_model_for_tier("basic", mode="song") != bot.select_music_model_for_tier("premium", mode="song")


def test_instrumental_tier_model_mapping():
    assert bot.select_music_model_for_tier("basic", mode="background") in {"chirp-v3.5", "chirp-v4"}
    assert bot.select_music_model_for_tier("standard", mode="background") in {"chirp-auk", "chirp-bluejay"}
    assert bot.select_music_model_for_tier("premium", supported_models=["chirp-fenix", "chirp-v3.5"], mode="background") == "chirp-fenix"


def test_song_tier_model_mapping():
    assert bot.select_music_model_for_tier("basic", mode="song") in {"chirp-v4", "chirp-auk"}
    assert bot.select_music_model_for_tier("standard", mode="song") in {"chirp-bluejay", "chirp-crow"}
    assert bot.select_music_model_for_tier("premium", supported_models=["chirp-crow", "chirp-v4"], mode="song") == "chirp-crow"


def test_model_ids_not_shown_public():
    state = _song_state(vocal="female")
    result = bot.music_product_result_from_suggestion(state, state["music_suggestions"][0])
    public = "\n".join([
        bot.music_product_tier_selection_text("song", "vi"),
        bot.music_product_suggestions_text(state, "vi"),
        bot.music_product_invoice_text(result, "vi"),
        bot.music_product_success_text({**result, "music_result_duration_seconds": 198}, 0, "vi"),
    ]).lower()
    for forbidden in ("chirp", "provider", "api", "key4u", "shopaikey", "suno", "debug", "metadata"):
        assert forbidden not in public


def test_music_auto_sends_exactly_one_audio(monkeypatch):
    user_id = 220018
    result = bot.music_product_result_from_suggestion(_background_state(user_id), bot.get_music_guided_result(user_id)["music_suggestions"][0])
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: False)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: {"ok": True, "final_cost": 100})
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **kwargs: {"vault_id": "MV1", "storage_ref": ""})
    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", lambda *args, **kwargs: asyncio.sleep(0, result=198))
    message = CaptureMessage(user_id=user_id)
    first = asyncio.run(bot.send_music_product_audio_result(message, SimpleNamespace(), user_id=user_id, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=result, audio_bytes=b"real-audio"))
    second = asyncio.run(bot.send_music_product_audio_result(message, SimpleNamespace(), user_id=user_id, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=first["result"], audio_bytes=b"real-audio"))
    assert first["ok"] is True
    assert second["duplicate"] is True
    assert [item["kind"] for item in message.outputs].count("audio") == 1


def test_music_check_result_does_not_duplicate_after_delivered(monkeypatch):
    user_id = 220019
    result = {**bot.music_product_result_from_suggestion(_background_state(user_id), bot.get_music_guided_result(user_id)["music_suggestions"][0]), "music_result_delivered_at": "now", "music_charged_xu": 100}
    bot.save_music_guided_result(user_id, result)
    monkeypatch.setattr(bot, "poll_music_suno_async_job", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("polled after delivery")))
    update = _update_with_query("music_quick|showroom|music_ai_status", user_id)
    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    assert update.callback_query.message.outputs[-1]["kind"] == "text"
    assert "Đã gửi file nhạc" in update.callback_query.message.outputs[-1]["text"]


def test_music_status_poller_does_not_duplicate_delivery(monkeypatch):
    user_id = 220020
    result = {**bot.music_product_result_from_suggestion(_background_state(user_id), bot.get_music_guided_result(user_id)["music_suggestions"][0]), "music_result_delivered_at": "now", "music_charged_xu": 100}
    monkeypatch.setattr(bot, "poll_music_suno_async_job", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("poller ran after delivery")))
    query = CaptureQuery("music_quick|showroom|music_ai_status", user_id)
    delivered = asyncio.run(bot.music_product_auto_deliver_job(query, SimpleNamespace(), user_id=user_id, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=result, internal_job_id="MUS1"))
    assert delivered["duplicate"] is True
    assert not query.message.outputs


def test_music_delivery_lock_prevents_double_send(monkeypatch):
    user_id = 220021
    result = {**bot.music_product_result_from_suggestion(_background_state(user_id), bot.get_music_guided_result(user_id)["music_suggestions"][0]), "music_result_delivery_lock": "sending"}
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("charged while locked")))
    message = CaptureMessage(user_id=user_id)
    delivered = asyncio.run(bot.send_music_product_audio_result(message, SimpleNamespace(), user_id=user_id, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=result, audio_bytes=b"real-audio"))
    assert delivered["duplicate"] is True
    assert not message.outputs


def test_music_does_not_send_temp_or_partial_file(monkeypatch):
    user_id = 220022
    result = {**bot.music_product_result_from_suggestion(_background_state(user_id), bot.get_music_guided_result(user_id)["music_suggestions"][0]), "is_partial": True}
    message = CaptureMessage(user_id=user_id)
    delivered = asyncio.run(bot.send_music_product_audio_result(message, SimpleNamespace(), user_id=user_id, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=result, audio_bytes=b"real-audio"))
    assert delivered["ok"] is False
    assert delivered["status"] == "FINAL_AUDIO_NOT_READY"
    assert not message.outputs


def test_music_duration_probed_from_audio_result(monkeypatch):
    monkeypatch.setattr(bot, "video_dubbing_audio_duration_seconds", lambda *args, **kwargs: asyncio.sleep(0, result=198.4))
    assert asyncio.run(bot.music_audio_real_duration_seconds(b"real-audio", fallback=120)) == 198


def test_music_success_caption_real_duration():
    result = bot.music_product_result_from_suggestion(_background_state(), bot.get_music_guided_result(220002)["music_suggestions"][0])
    text = bot.music_product_success_text({**result, "music_result_duration_seconds": 198}, 100, "vi")
    assert "3:18" in text
    assert "120 giây" not in text


def test_music_no_double_charge_on_duplicate_attempt(monkeypatch):
    user_id = 220023
    charges = []
    result = bot.music_product_result_from_suggestion(_background_state(user_id), bot.get_music_guided_result(user_id)["music_suggestions"][0])
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: False)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: charges.append(args) or {"ok": True, "final_cost": 100})
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **kwargs: {"vault_id": "MV2", "storage_ref": ""})
    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", lambda *args, **kwargs: asyncio.sleep(0, result=180))
    message = CaptureMessage(user_id=user_id)
    first = asyncio.run(bot.send_music_product_audio_result(message, SimpleNamespace(), user_id=user_id, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=result, audio_bytes=b"real-audio"))
    asyncio.run(bot.send_music_product_audio_result(message, SimpleNamespace(), user_id=user_id, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=first["result"], audio_bytes=b"real-audio"))
    assert len(charges) == 1


def test_music_charge_after_valid_delivery(monkeypatch):
    user_id = 220024
    order = []
    result = bot.music_product_result_from_suggestion(_background_state(user_id), bot.get_music_guided_result(user_id)["music_suggestions"][0])
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: False)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: order.append("charge") or {"ok": True, "final_cost": 100})
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **kwargs: {"vault_id": "MV3", "storage_ref": ""})
    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", lambda *args, **kwargs: asyncio.sleep(0, result=180))
    message = CaptureMessage(user_id=user_id)

    async def tracked_reply_audio(*args, **kwargs):
        order.append("send")
        return SimpleNamespace(message_id=1, audio=SimpleNamespace(file_id="file-ok"))

    message.reply_audio = tracked_reply_audio
    delivered = asyncio.run(bot.send_music_product_audio_result(message, SimpleNamespace(), user_id=user_id, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=result, audio_bytes=b"real-audio"))
    assert delivered["ok"] is True
    assert order == ["send", "charge"]


def test_music_no_charge_before_confirm(monkeypatch):
    user_id = 220025
    bot.save_music_guided_result(user_id, {"music_product_mode": "background", "music_product_tier": "music_tier_basic"})
    bot.set_music_guided_pending(user_id, "music_product_background_idea", product_context=bot.PRODUCT_CONTEXT_SHOWROOM)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("charged before confirm")))
    message = CaptureMessage("Nhạc nền quảng cáo AI vui tươi", user_id)
    assert asyncio.run(bot.handle_music_guided_pending_text(_message_update(message, user_id), SimpleNamespace())) is True
    assert "3 gợi ý nhạc nền" in message.outputs[-1]["text"]


def test_music_no_charge_on_provider_fail(monkeypatch):
    user_id = 220026
    state = _background_state(user_id)
    result = bot.music_product_result_from_suggestion(state, state["music_suggestions"][0])
    monkeypatch.setattr(bot, "can_user_access_product_engine", lambda *args, **kwargs: {"allowed": True})
    monkeypatch.setattr(bot, "get_user", lambda uid: (1000, None, None))

    async def fail_engine(*args, **kwargs):
        return {"ok": False, "status": "FAILED", "detail": "failed"}

    monkeypatch.setattr(bot, "execute_engine", fail_engine)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("charged on fail")))
    query = CaptureQuery("music_quick|showroom|music_ai_confirm", user_id)
    asyncio.run(bot.handle_music_product_confirm(query, SimpleNamespace(), user_id=user_id, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=result))
    assert "chưa trừ Xu" in query.message.outputs[-1]["text"]


def test_music_admin_charges_zero(monkeypatch):
    user_id = 220027
    state = _song_state(user_id, tier="music_tier_premium", vocal="duet")
    result = bot.music_product_result_from_suggestion(state, state["music_suggestions"][0])
    assert "300 Xu" in bot.music_product_invoice_text(result, "vi")
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: True)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("admin charged")))
    monkeypatch.setattr(bot, "upsert_music_vault_from_output", lambda **kwargs: {"vault_id": "MV4", "storage_ref": ""})
    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", lambda *args, **kwargs: asyncio.sleep(0, result=180))
    delivered = asyncio.run(bot.send_music_product_audio_result(CaptureMessage(user_id=user_id), SimpleNamespace(), user_id=user_id, lang="vi", product_context=bot.PRODUCT_CONTEXT_SHOWROOM, result=result, audio_bytes=b"real-audio"))
    assert delivered["charged_xu"] == 0


def test_music_public_ui_no_provider_api_model_debug_words():
    state = _song_state(vocal="female")
    result = bot.music_product_result_from_suggestion(state, state["music_suggestions"][0])
    public = "\n".join([
        bot.music_hub_text("vi"),
        bot.music_product_idea_input_text("song", "music_tier_basic", "female", "vi"),
        bot.music_product_suggestions_text(state, "vi"),
        bot.music_product_invoice_text(result, "vi"),
        bot.music_product_success_text({**result, "music_result_duration_seconds": 198}, 0, "vi"),
        "\n".join(_labels(bot.music_product_invoice_keyboard(result, "vi"))),
    ]).lower()
    for forbidden in ("provider", "api", "model id", "metadata", "prompt hash", "debug", "route", "payload", "traceback", "temporary file", "cache path"):
        assert forbidden not in public
