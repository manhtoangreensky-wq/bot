import asyncio
import inspect
import json
from types import SimpleNamespace

import bot


class CaptureMessage:
    def __init__(self, user_id=18001):
        self.chat_id = user_id
        self.outputs = []

    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        self.outputs.append({"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup, **kwargs})
        return SimpleNamespace(text=text, reply_markup=reply_markup)

    async def reply_audio(self, audio=None, filename=None, caption=None, **kwargs):
        self.outputs.append({"audio": audio, "filename": filename, "caption": str(caption or ""), **kwargs})
        return SimpleNamespace(audio=SimpleNamespace(file_id="tg-default-audio-id"))

    async def reply_document(self, document=None, filename=None, caption=None, **kwargs):
        self.outputs.append({"document": document, "filename": filename, "caption": str(caption or ""), **kwargs})
        return SimpleNamespace(document=SimpleNamespace(file_id="tg-default-doc-id"))


def _init_voice_db(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "voice_p0_17a1.db"))
    monkeypatch.setattr(bot, "DB_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("VOICE_ASSET_STORAGE_DIR", str(tmp_path / "voice_assets"))
    bot.init_db()


def _active_profile(user_id=18010, profile_id=1):
    return {
        "id": profile_id,
        "user_id": str(user_id),
        "status": "active",
        "provider": "key4u_minimax",
        "provider_voice_id": "custom-provider-voice",
        "display_name": "Voice riêng",
    }


def test_default_voice_free_copy():
    text = bot.default_voice_confirm_text("Xin chào", "female", "vi")
    assert "Tạo giọng đọc miễn phí" in text
    assert "Giọng nam/nữ mặc định miễn phí và không trừ Xu" in text


def test_default_voice_no_6s_preview_copy():
    text = bot.default_voice_confirm_text("Xin chào", "male", "vi")
    assert "6 giây" not in text
    assert "Nghe thử" not in text


def test_default_voice_no_preview_quota():
    source = inspect.getsource(bot.send_default_free_tts_result)
    assert "preview_quota_guard" not in source
    assert "consume_preview_quota" not in source


def test_default_voice_no_silver_requirement():
    text = bot.default_voice_confirm_text("Xin chào", "female", "vi")
    assert "Silver" not in text
    assert "hạng" not in text


def test_default_voice_no_15_day_rule():
    text = bot.default_voice_confirm_text("Xin chào", "female", "vi")
    assert "15 ngày" not in text


def test_default_voice_no_50_xu_copy():
    text = bot.default_voice_confirm_text("Xin chào", "female", "vi")
    assert "50 Xu" not in text


def test_default_voice_no_xu_charge():
    source = inspect.getsource(bot.send_default_free_tts_result)
    assert "spend_fixed_credit_info" not in source


def test_default_voice_uses_edge_or_free_adapter(monkeypatch):
    async def paid_route(*_args, **_kwargs):
        raise AssertionError("default free voice must not use paid MiniMax/ShopAIKey/Key4U route")

    async def edge_route(text, voice_id=""):
        return "PASS", b"edge-audio", f"edge:{voice_id}", 0

    monkeypatch.setattr(bot, "shopaikey_minimax_tts_bytes", paid_route)
    monkeypatch.setattr(bot, "key4u_minimax_tts_bytes", paid_route)
    monkeypatch.setattr(bot, "shopaikey_tts_bytes", paid_route)
    monkeypatch.setattr(bot, "tts_edge_bytes", edge_route)

    ok, audio, detail = asyncio.run(bot.synthesize_standalone_tts_audio(
        "Xin chào TOAN AAS",
        voice_id="default_female",
        provider_hint="default_free",
    ))
    assert ok is True
    assert audio == b"edge-audio"
    assert "edge:" in detail


def test_default_voice_confirm_then_full_audio_sent(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)

    async def fake_engine(feature, params, context):
        assert feature == "voice_tts"
        assert params["provider_hint"] == "default_free"
        assert context["is_paid_job"] is False
        return {"ok": True, "output_bytes": b"full-default-audio", "detail": "edge"}

    async def forbidden_cap(*_args, **_kwargs):
        raise AssertionError("default voice must not cut to 6s preview")

    monkeypatch.setattr(bot, "execute_engine", fake_engine)
    monkeypatch.setattr(bot, "cap_voice_preview_audio_bytes", forbidden_cap)
    message = CaptureMessage()
    ok = asyncio.run(bot.send_default_free_tts_result(
        message,
        18002,
        "Xin chào TOAN AAS đây là giọng mặc định miễn phí",
        "female",
    ))
    assert ok is True
    audio_outputs = [item for item in message.outputs if item.get("filename")]
    assert audio_outputs[-1]["filename"] == "toan_aas_default_voice.mp3"
    assert "Miễn phí" in audio_outputs[-1]["caption"]


def test_default_voice_no_paid_provider_route():
    source = inspect.getsource(bot.synthesize_standalone_tts_audio)
    free_block = source[source.index("if free_default_only:"):source.index("elif selected_voice:")]
    assert "key4u_call" not in free_block
    assert "shopaikey_call" not in free_block
    assert "simple_shopaikey_call" not in free_block
    assert "edge_call" in free_block


def test_default_free_voice_asset_price_zero(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)

    async def fake_engine(*_args, **_kwargs):
        return {"ok": True, "output_bytes": b"full-default-audio", "detail": "edge"}

    monkeypatch.setattr(bot, "execute_engine", fake_engine)
    message = CaptureMessage()
    asyncio.run(bot.send_default_free_tts_result(
        message,
        18003,
        "Xin chào TOAN AAS đây là giọng mặc định miễn phí",
        "male",
    ))
    rows = bot.list_voice_asset_records(status="used", user_id="18003")
    assert rows
    metadata = json.loads(rows[0]["metadata_json"])
    assert metadata["price_xu"] == 0
    assert metadata["charge_status"] == "free_default_voice"
    assert rows[0]["voice_kind"] == "default_male"


def test_default_voice_not_charged_50_xu():
    assert "VOICE_PROFILE_PRICE_XU" not in inspect.getsource(bot.send_default_free_tts_result)


def test_custom_voice_first_creation_free(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    assert bot.voice_profile_storage_price_xu(18010) == 0


def test_custom_voice_second_creation_50_xu(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    uid = 18011
    pid = bot.save_user_voice_profile(uid, "sample-file")
    bot.update_user_voice_profile(uid, pid, provider_voice_id="voice-ok", status="active")
    assert bot.voice_profile_storage_price_xu(uid) == bot.VOICE_PROFILE_PRICE_XU == 50


def test_custom_voice_first_free_consumed_only_on_success(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    uid = 18012
    pid = bot.save_user_voice_profile(uid, "sample-file")
    bot.update_user_voice_profile(uid, pid, provider_voice_id="", status="failed_provider_not_ready")
    assert bot.voice_profile_storage_price_xu(uid) == 0


def test_custom_voice_cancel_does_not_consume_first_free(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    uid = 18013
    pid = bot.save_user_voice_profile(uid, "sample-file")
    bot.update_user_voice_profile(uid, pid, provider_voice_id="", status="cancelled")
    assert bot.voice_profile_storage_price_xu(uid) == 0


def test_custom_voice_provider_block_does_not_consume_first_free(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    uid = 18014
    pid = bot.save_user_voice_profile(uid, "sample-file")
    bot.update_user_voice_profile(uid, pid, provider_voice_id="", status="failed_clone_permission_forbidden")
    assert bot.voice_profile_storage_price_xu(uid) == 0


def test_custom_voice_invalid_output_does_not_consume_first_free(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    uid = 18015
    pid = bot.save_user_voice_profile(uid, "sample-file")
    bot.update_user_voice_profile(uid, pid, provider_voice_id="", status="failed_invalid_voice_draft")
    assert bot.voice_profile_storage_price_xu(uid) == 0


def test_custom_voice_delete_does_not_reset_first_free_by_default(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    uid = 18016
    pid = bot.save_user_voice_profile(uid, "sample-file")
    bot.update_user_voice_profile(uid, pid, provider_voice_id="voice-ok", status="active")
    assert bot.soft_delete_voice_profile(uid, pid) is True
    assert bot.voice_profile_storage_price_xu(uid) == 0


def test_custom_voice_create_price_50_xu(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    uid = 18017
    pid = bot.save_user_voice_profile(uid, "sample-file")
    bot.update_user_voice_profile(uid, pid, provider_voice_id="voice-ok", status="active")
    quote_pid = bot.save_user_voice_profile(uid, "sample-file-2")
    quote = bot.voice_clone_quote_text({"id": quote_pid, "user_id": str(uid)}, "vi")
    assert "50 Xu / lần tạo thành công" in quote


def test_custom_voice_no_charge_before_confirm():
    assert "spend_fixed_credit_info" not in inspect.getsource(bot.saved_voice_tts_confirm_text)
    assert "spend_fixed_credit_info" not in inspect.getsource(bot.default_voice_confirm_text)


def test_custom_voice_usage_price_0_2_xu_per_char():
    assert bot.custom_voice_usage_price_xu("a" * 11) == 3


def test_custom_voice_usage_rounds_up_to_whole_xu():
    assert bot.custom_voice_usage_price_xu("a" * 50) == 10
    assert bot.custom_voice_usage_price_xu("a" * 101) == 19


def test_custom_voice_usage_min_more_than_10_chars():
    assert bot.custom_voice_usage_text_too_short("a" * 10) is True
    assert bot.custom_voice_usage_text_too_short("a" * 11) is False


def test_custom_voice_usage_blocks_short_text_before_provider(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)

    async def forbidden_engine(*_args, **_kwargs):
        raise AssertionError("short custom voice text must block before provider")

    monkeypatch.setattr(bot, "execute_engine", forbidden_engine)
    message = CaptureMessage()
    ok = asyncio.run(bot.send_paid_saved_voice_tts_result(message, 18018, _active_profile(18018), "1234567890"))
    assert ok is False
    assert "trên 10 ký tự" in message.outputs[-1]["text"]


def test_custom_voice_usage_requires_duration_more_than_3s():
    assert bot.custom_voice_usage_output_too_short("abcdefghijk", "normal", b"audio") is True
    assert bot.custom_voice_usage_output_too_short("một hai ba bốn năm sáu bảy tám chín mười mười một mười hai", "normal", b"audio") is False


def test_custom_voice_usage_invalid_output_no_charge(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)

    async def fake_engine(*_args, **_kwargs):
        return {"ok": False, "output_bytes": b"", "detail": "provider_failed"}

    def forbidden_charge(*_args, **_kwargs):
        raise AssertionError("invalid output must not charge")

    monkeypatch.setattr(bot, "execute_engine", fake_engine)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", forbidden_charge)
    message = CaptureMessage()
    ok = asyncio.run(bot.send_paid_saved_voice_tts_result(
        message,
        18019,
        _active_profile(18019),
        "một hai ba bốn năm sáu bảy tám chín mười mười một",
    ))
    assert ok is False


def test_custom_voice_usage_duration_too_short_no_charge(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)

    async def fake_engine(*_args, **_kwargs):
        return {"ok": True, "output_bytes": b"audio", "detail": "ok"}

    def forbidden_charge(*_args, **_kwargs):
        raise AssertionError("short output must not charge")

    monkeypatch.setattr(bot, "execute_engine", fake_engine)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", forbidden_charge)
    message = CaptureMessage()
    ok = asyncio.run(bot.send_paid_saved_voice_tts_result(message, 18020, _active_profile(18020), "abcdefghijk"))
    assert ok is False
    assert "trên 3 giây" in message.outputs[-1]["text"]


def test_custom_voice_usage_finalize_only_after_valid_output(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    events = []

    async def fake_engine(*_args, **_kwargs):
        events.append("engine")
        return {"ok": True, "output_bytes": b"valid-custom-audio", "detail": "ok"}

    def fake_charge(user_id, amount, *_args, **_kwargs):
        events.append("charge")
        return {"ok": True, "final_cost": amount}

    monkeypatch.setattr(bot, "execute_engine", fake_engine)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", fake_charge)
    message = CaptureMessage()
    text = "một hai ba bốn năm sáu bảy tám chín mười mười một mười hai"
    ok = asyncio.run(bot.send_paid_saved_voice_tts_result(message, 18021, _active_profile(18021), text))
    assert ok is True
    assert events == ["engine", "charge"]


def test_custom_voice_usage_asset_records_billable_chars(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)

    async def fake_engine(*_args, **_kwargs):
        return {"ok": True, "output_bytes": b"valid-custom-audio", "detail": "ok"}

    monkeypatch.setattr(bot, "execute_engine", fake_engine)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda _uid, amount, *_args, **_kwargs: {"ok": True, "final_cost": amount})
    text = "một hai ba bốn năm sáu bảy tám chín mười mười một mười hai"
    asyncio.run(bot.send_paid_saved_voice_tts_result(CaptureMessage(), 18022, _active_profile(18022), text))
    rows = bot.list_voice_asset_records(status="used", user_id="18022")
    metadata = json.loads(rows[0]["metadata_json"])
    assert metadata["billable_chars"] == bot.custom_voice_usage_billable_chars(text)


def test_custom_voice_usage_asset_records_price_per_char(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    row = bot.create_voice_asset_record(
        18023,
        "voice_saved_tts",
        bot.PRODUCT_CONTEXT_SHOWROOM,
        "custom_clone_usage",
        metadata={"price_per_char_xu": 0.1},
    )
    stored = bot.get_voice_asset_record(row["voice_asset_id"])
    metadata = json.loads(stored["metadata_json"])
    assert metadata["price_per_char_xu"] == 0.1


def test_custom_voice_usage_asset_records_min_rules(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    row = bot.create_voice_asset_record(
        18024,
        "voice_saved_tts",
        bot.PRODUCT_CONTEXT_SHOWROOM,
        "custom_clone_usage",
        metadata={"min_chars_rule": ">10", "min_duration_seconds_rule": ">3"},
    )
    metadata = json.loads(bot.get_voice_asset_record(row["voice_asset_id"])["metadata_json"])
    assert metadata["min_chars_rule"] == ">10"
    assert metadata["min_duration_seconds_rule"] == ">3"


def test_custom_voice_usage_public_copy_shows_chars_and_price():
    text = bot.saved_voice_tts_confirm_text(_active_profile(), "a" * 50, "normal", "vi")
    assert "Số ký tự tính phí" in text
    assert "Dự kiến trừ: <b>10 Xu</b>" in text
    assert "0.2 Xu / ký tự" in text


def test_voice_engine_status_mentions_default_free_direct(monkeypatch):
    monkeypatch.setattr(bot, "voice_provider_dependency_status", lambda: {
        "edge_tts": {"status": "available", "available": True},
        "fish_audio": {"status": "missing"},
        "elevenlabs": {"status": "missing"},
        "deepgram": {"status": "missing"},
        "deepl": {"status": "missing"},
        "auphonic": {"status": "missing"},
        "gemini": {"status": "missing"},
        "heygen": {"status": "missing"},
        "cutout": {"status": "missing"},
        "freesound": {"status": "missing"},
        "jamendo": {"status": "missing"},
    })
    lines = "\n".join(bot.voice_engine_status_lines())
    assert "FREE_FULL_GENERATION_DIRECT" in lines
    assert "Default TTS preview: <code>DISABLED</code>" in lines
    assert "Default TTS price: <code>FREE</code>" in lines
    assert "Default TTS tier requirement: <code>NONE</code>" in lines


def test_voice_engine_status_mentions_custom_create_50_xu():
    lines = "\n".join(bot.voice_engine_status_lines())
    assert "Custom voice creation price" in lines
    assert "50 Xu / successful creation" in lines


def test_voice_engine_status_mentions_custom_usage_0_2_xu_per_char():
    lines = "\n".join(bot.voice_engine_status_lines())
    assert "0.2 Xu / character, rounded up" in lines


def test_voice_engine_status_mentions_custom_usage_min_rules():
    lines = "\n".join(bot.voice_engine_status_lines())
    assert "&gt;10 characters" in lines
    assert "&gt;3 seconds" in lines


def test_voice_engine_status_no_secret():
    lines = "\n".join(bot.voice_engine_status_lines())
    assert "TOKEN=" not in lines
    assert "API_KEY=" not in lines
    assert "Bearer " not in lines
    assert "sk-" not in lines
