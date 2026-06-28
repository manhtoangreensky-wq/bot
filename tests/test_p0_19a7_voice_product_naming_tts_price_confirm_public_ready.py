import asyncio
from pathlib import Path
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def _words(count: int) -> str:
    return " ".join(f"tu{i}" for i in range(int(count)))


def _profile(profile_id: int = 77) -> dict:
    return {
        "id": profile_id,
        "display_name": "Voice ban hang",
        "provider_voice_id": f"voice-{profile_id}-ready",
        "status": "active",
        "preview_audio_ref": "demo-file-id",
        "provider": "minimax",
    }


class CaptureMessage:
    chat_id = 123

    def __init__(self):
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"text": str(text or ""), **kwargs})
        return SimpleNamespace()

    async def reply_audio(self, audio=None, filename=None, caption=None, **kwargs):
        self.outputs.append({"audio": audio, "filename": filename, "caption": str(caption or ""), **kwargs})
        return SimpleNamespace(audio=SimpleNamespace(file_id="tg-audio-id"))

    async def reply_document(self, document=None, filename=None, caption=None, **kwargs):
        self.outputs.append({"document": document, "filename": filename, "caption": str(caption or ""), **kwargs})
        return SimpleNamespace(document=SimpleNamespace(file_id="tg-doc-id"))


def _reset_voice_state(user_id: int):
    for key in (
        bot.music_guided_result_key(user_id),
        bot.music_guided_pending_key(user_id),
        bot.product_context_key(user_id),
    ):
        bot.USER_PENDING.pop(key, None)


def _saved_state(user_id: int, text: str | None = None, *, speed: str = "1.0", volume: int = 100, profile_id: int = 77):
    payload = {
        "voice_tts_settings_source": "saved",
        "voice_tts_settings_profile_id": profile_id,
        "selected_voice_profile_id": profile_id,
        "selected_voice_style": "Voice ban hang",
        "voice_text": text if text is not None else _words(20),
        "tts_speed": speed,
        "voice_tts_volume_percent": volume,
    }
    bot.save_music_guided_result(user_id, payload)
    return payload


def test_saved_voice_button_renames_doc_thu_to_tao_audio():
    labels = _labels(bot.voice_profile_actions_keyboard(77, "vi", bot.PRODUCT_CONTEXT_SHOWROOM, _profile()))
    assert "▶️ Nghe demo" in labels
    assert "🎧 Tạo audio" in labels
    assert "✍️ Đọc thử" not in labels


def test_nghe_demo_remains_demo_no_charge():
    markup = bot.voice_profile_actions_keyboard(77, "vi", bot.PRODUCT_CONTEXT_SHOWROOM, _profile())
    assert "▶️ Nghe demo" in _labels(markup)
    assert any("voice_profile_listen:77" in cb for cb in _callbacks(markup))
    listen_block = Path(bot.__file__).read_text(encoding="utf-8").split('if action.startswith("voice_profile_listen:"):', 1)[1].split('if action.startswith("voice_profile_use:"):', 1)[0]
    assert "spend_fixed_credit_info" not in listen_block


def test_tao_audio_requires_text(monkeypatch):
    user_id = 190701
    _reset_voice_state(user_id)
    bot.save_music_guided_result(user_id, {"voice_tts_settings_source": "saved", "voice_tts_settings_profile_id": 77})
    monkeypatch.setattr(bot, "send_paid_saved_voice_tts_result", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not create without text")))
    message = CaptureMessage()
    asyncio.run(bot.voice_tts_create_from_settings(message, user_id, "vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    assert "Giọng đọc" in message.outputs[-1]["text"]


def test_tao_audio_rejects_under_20_words(monkeypatch):
    user_id = 190702
    _reset_voice_state(user_id)
    _saved_state(user_id, _words(19))
    monkeypatch.setattr(bot, "get_user_voice_profile", lambda uid, pid: _profile(pid))
    message = CaptureMessage()
    asyncio.run(bot.voice_tts_create_from_settings(message, user_id, "vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    assert message.outputs[-1]["text"] == "Nội dung cần ít nhất 20 từ để tạo audio. Anh/chị hãy nhập thêm nội dung rồi thử lại."


def test_tao_audio_counts_words_not_characters():
    assert bot.voice_tts_word_count("a" * 120) == 1
    assert bot.voice_tts_product_text_too_short("a" * 120) is True
    assert bot.voice_tts_word_count("Xin chao, TOAN AAS! Tao audio duoc khong?") == 8


def test_tao_audio_price_0_05_xu_per_word():
    assert bot.voice_tts_product_quote(_words(20))["total_xu"] == 1
    assert bot.voice_tts_product_quote(_words(100))["total_xu"] == 5
    assert bot.voice_tts_product_quote(_words(1000))["total_xu"] == 50


def test_tao_audio_minimum_charge_1_xu():
    quote = bot.voice_tts_product_quote(_words(1))
    assert quote["raw_price_xu"] == 0.05
    assert quote["total_xu"] == 1


def test_tao_audio_rounds_up_if_wallet_integer():
    assert bot.voice_tts_product_quote(_words(30))["raw_price_xu"] == 1.5
    assert bot.voice_tts_product_quote(_words(30))["total_xu"] == 2


def test_tao_audio_shows_price_summary_before_provider_call(monkeypatch):
    user_id = 190703
    _reset_voice_state(user_id)
    _saved_state(user_id, _words(30), speed="1.2", volume=150)
    monkeypatch.setattr(bot, "get_user_voice_profile", lambda uid, pid: _profile(pid))

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("provider path must not run before invoice confirm")

    monkeypatch.setattr(bot, "send_paid_saved_voice_tts_result", forbidden)
    message = CaptureMessage()
    asyncio.run(bot.voice_tts_create_from_settings(message, user_id, "vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    text = message.outputs[-1]["text"]
    assert "Xác nhận tạo audio" in text
    assert "• Nội dung: <b>30 từ</b>" in text
    assert "• Đơn giá: <b>0.05 Xu / từ</b>" in text
    assert "• Tổng thanh toán: <b>2 Xu</b>" in text


def test_tao_audio_no_provider_before_confirm(monkeypatch):
    user_id = 190704
    _reset_voice_state(user_id)
    _saved_state(user_id, _words(20))
    monkeypatch.setattr(bot, "get_user_voice_profile", lambda uid, pid: _profile(pid))

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("audio generation must wait for confirm")

    monkeypatch.setattr(bot, "send_paid_saved_voice_tts_result", forbidden)
    message = CaptureMessage()
    asyncio.run(bot.voice_tts_create_from_settings(message, user_id, "vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    assert "Xác nhận tạo audio" in message.outputs[-1]["text"]


def test_tao_audio_no_charge_before_confirm(monkeypatch):
    user_id = 190705
    _reset_voice_state(user_id)
    _saved_state(user_id, _words(20))
    monkeypatch.setattr(bot, "get_user_voice_profile", lambda uid, pid: _profile(pid))
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no charge before confirm")))
    message = CaptureMessage()
    asyncio.run(bot.voice_tts_create_from_settings(message, user_id, "vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    assert "TOAN AAS chỉ tạo audio và trừ Xu sau khi anh/chị xác nhận." in message.outputs[-1]["text"]


def test_tao_audio_confirm_then_generates_audio(monkeypatch):
    user_id = 190706
    _reset_voice_state(user_id)
    _saved_state(user_id, _words(20))
    monkeypatch.setattr(bot, "get_user_voice_profile", lambda uid, pid: _profile(pid))
    calls = []

    async def fake_send(_message, uid, profile, text, **kwargs):
        calls.append((uid, profile["id"], text, kwargs))
        return True

    monkeypatch.setattr(bot, "send_paid_saved_voice_tts_result", fake_send)
    message = CaptureMessage()
    asyncio.run(bot.voice_tts_generate_after_confirm(message, user_id, "vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    assert calls and calls[0][0] == user_id


def test_tao_audio_success_shows_total_and_charged_xu(monkeypatch, tmp_path):
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"real-nonzero-audio")

    async def fake_process_voice_tts(**_kwargs):
        return SimpleNamespace(ok=True, audio_path=str(audio_path), metadata={})

    monkeypatch.setattr(bot.voice_clone_pipeline, "process_voice_tts", fake_process_voice_tts)
    monkeypatch.setattr(bot, "boost_voice_output_for_asset", lambda asset_id, audio_bytes, volume_percent=100: (audio_bytes, "", {"volume_percent": volume_percent}))
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda _uid, amount, *_args, **_kwargs: {"ok": True, "final_cost": amount})
    monkeypatch.setattr(bot, "create_voice_asset_record", lambda *_args, **_kwargs: {"voice_asset_id": "asset"})
    monkeypatch.setattr(bot, "update_user_voice_profile", lambda *_args, **_kwargs: True)
    message = CaptureMessage()
    ok = asyncio.run(bot.send_paid_saved_voice_tts_result(message, 190707, _profile(), _words(20), speed="1.0", volume_percent=100, lang="vi"))
    assert ok is True
    caption = message.outputs[-1]["caption"]
    assert "✅ Đã tạo audio." in caption
    assert "• Số từ: 20" in caption
    assert "• Tổng giá: 1 Xu" in caption
    assert "• Đã trừ: 1 Xu" in caption


def test_admin_tao_audio_shows_same_price_but_no_charge_internal(monkeypatch, tmp_path):
    audio_path = tmp_path / "admin-audio.mp3"
    audio_path.write_bytes(b"real-nonzero-audio")

    async def fake_process_voice_tts(**_kwargs):
        return SimpleNamespace(ok=True, audio_path=str(audio_path), metadata={})

    def forbidden_charge(*_args, **_kwargs):
        raise AssertionError("admin must not be charged internally")

    monkeypatch.setattr(bot, "is_admin_user", lambda user_id: True)
    monkeypatch.setattr(bot.voice_clone_pipeline, "process_voice_tts", fake_process_voice_tts)
    monkeypatch.setattr(bot, "boost_voice_output_for_asset", lambda asset_id, audio_bytes, volume_percent=100: (audio_bytes, "", {"volume_percent": volume_percent}))
    monkeypatch.setattr(bot, "spend_fixed_credit_info", forbidden_charge)
    monkeypatch.setattr(bot, "create_voice_asset_record", lambda *_args, **_kwargs: {"voice_asset_id": "asset"})
    monkeypatch.setattr(bot, "update_user_voice_profile", lambda *_args, **_kwargs: True)
    message = CaptureMessage()
    ok = asyncio.run(bot.send_paid_saved_voice_tts_result(message, 190708, _profile(), _words(20), speed="1.0", volume_percent=100, lang="vi"))
    assert ok is True
    caption = message.outputs[-1]["caption"]
    assert "• Tổng giá: 1 Xu" in caption
    assert "• Đã trừ: 0 Xu" in caption
    assert "ADMIN" not in caption


def test_speed_volume_then_tao_audio_goes_to_price_summary(monkeypatch):
    user_id = 190709
    _reset_voice_state(user_id)
    _saved_state(user_id, _words(20), speed="1.2", volume=150)
    monkeypatch.setattr(bot, "get_user_voice_profile", lambda uid, pid: _profile(pid))
    message = CaptureMessage()
    asyncio.run(bot.voice_tts_create_from_settings(message, user_id, "vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    text = message.outputs[-1]["text"]
    assert "Xác nhận tạo audio" in text
    assert "• Tốc độ: <b>1.2x</b>" in text
    assert "• Âm lượng: <b>150%</b>" in text


def test_public_voice_products_open():
    assert bot.MINIMAX_VOICE_PUBLIC_ENABLED is True
    assert bot.MINIMAX_VOICE_CLONE_PUBLIC_ENABLED is True


def test_public_status_voice_on_only():
    text = bot.system_public_status_text()
    assert "• Voice: <code>ON</code>" in text
    assert "• Voice TTS: <code>ON</code>" in text
    assert "• Custom voice: <code>ON</code>" in text
    assert "• Video generation: <code>unchanged</code>" in text
    assert "• Subtitle/dub: <code>unchanged</code>" in text
    assert "• Music: <code>ON</code>" in text
    assert "• AI Music: <code>ON</code>" in text
    assert "• AI Song: <code>ON</code>" in text
    assert "• Music Vault: <code>ON</code>" in text


def test_no_admin_provider_debug_words_in_voice_product_ui():
    surfaces = "\n".join([
        bot.voice_tts_price_summary_text(voice_name="Voice ban hang", text=_words(20), speed="1.0", volume_percent=100, lang="vi"),
        "\n".join(_labels(bot.voice_profile_actions_keyboard(77, "vi", bot.PRODUCT_CONTEXT_SHOWROOM, _profile()))),
        bot.voice_profile_status_label("waiting_provider", "vi"),
        bot.tts_provider_guard_text("vi"),
    ]).lower()
    for term in ("admin test mode", "provider_voice_id", "route_errors", "diagnostic", "traceback", "shopaikey", "key4u", "minimax", "provider"):
        assert term not in surfaces


def test_custom_voice_no_fake_success():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    block = source.split("async def send_paid_saved_voice_tts_result", 1)[1].split("async def transcribe_standalone_audio_message", 1)[0]
    assert "if not tts_result.ok or not audio_bytes:" in block
    assert block.index("if not tts_result.ok or not audio_bytes:") < block.index("reply_audio")
