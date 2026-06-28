import asyncio
import wave

import bot
from providers import key4u_provider
from providers.key4u_provider import Key4UConfig, Key4UProvider
from services import voice_clone_pipeline


PRODUCT_FORBIDDEN_TERMS = (
    "provider",
    "provider_voice_id",
    "route",
    "adapter",
    "http_status",
    "error_code",
    "route_errors",
    "key4u",
    "shopaikey",
    "minimax",
    "api",
    "traceback",
)


class FakeResponse:
    def __init__(self, payload=None, *, status_code=200, content=b"", headers=None, text=""):
        self._payload = payload if payload is not None else {}
        self.status_code = status_code
        self.content = content
        self.headers = headers or {"content-type": "application/json"}
        self.text = text

    def json(self):
        return self._payload


class FakeAsyncClient:
    def __init__(self, response, requests):
        self.response = response
        self.requests = requests

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def post(self, url, **kwargs):
        self.requests.append({"url": url, **kwargs})
        return self.response


def _patch_async_client(monkeypatch, module, response):
    requests = []
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda *_args, **_kwargs: FakeAsyncClient(response, requests))
    return requests


def _patch_shopaikey_voice_env(monkeypatch):
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "sk-test")
    monkeypatch.setattr(bot, "SHOPAIKEY_TTS_BASE_URL", "https://api.shopaikey.test")
    monkeypatch.setattr(bot, "MINIMAX_VOICE_UPLOAD_ENDPOINT", "/tts/minimax/v1/files/upload")
    monkeypatch.setattr(bot, "MINIMAX_VOICE_CLONE_ENDPOINT", "/tts/minimax/v1/voice_clone")
    monkeypatch.setattr(bot, "MINIMAX_TTS_ENDPOINT", "/tts/minimax/t2a_v2")
    monkeypatch.setattr(bot, "MINIMAX_TTS_MODEL", "speech-02-hd")


def _assert_product_clean(text):
    folded = str(text or "").lower()
    for term in PRODUCT_FORBIDDEN_TERMS:
        assert term not in folded


async def _run_pipeline_with_clone_payload(tmp_path, clone_payload, *, seed="toanaas-voice-user123-20260628"):
    sample_path = tmp_path / "sample.mp3"
    sample_path.write_bytes(b"sample-audio-bytes")
    captured = {"clone_voice_id": "", "finalize": {}}

    async def upload_call(audio_bytes):
        assert audio_bytes == b"sample-audio-bytes"
        return "PASS", "file-123", "ok", 200

    async def clone_call(file_id, voice_id):
        captured["clone_voice_id"] = voice_id
        assert file_id == "file-123"
        return "PASS", clone_payload, "ok", 200

    async def tts_call(_text, voice_id="", **_kwargs):
        assert voice_id == seed
        return "PASS", b"preview-audio", "ok", 200

    async def route_attempts_func(_readiness, admin_access=False):
        return [("shopaikey_minimax", upload_call, clone_call, tts_call)]

    async def finalize_profile_func(**kwargs):
        captured["finalize"] = dict(kwargs)
        return {"ok": True}

    result = await voice_clone_pipeline.process_custom_voice_create(
        user_id=123,
        sample_path=sample_path,
        display_name="Voice ban hang",
        product_context="showroom",
        profile_id=77,
        readiness={"ready": True},
        output_dir=str(tmp_path),
        route_attempts_func=route_attempts_func,
        access_allowed_func=lambda *_args, **_kwargs: True,
        ready_for_processing_func=lambda *_args, **_kwargs: True,
        make_provider_voice_id_func=lambda *_args, **_kwargs: seed,
        finalize_profile_func=finalize_profile_func,
    )
    return result, captured


def test_shopaikey_voice_clone_uses_requested_voice_id_when_response_has_no_voice_id(monkeypatch):
    _patch_shopaikey_voice_env(monkeypatch)
    requested_voice_id = "toanaas-voice-user123-20260628"
    response = FakeResponse({"base_resp": {"status_code": 0}, "demo_audio": "00"})
    requests = _patch_async_client(monkeypatch, bot, response)

    status, payload, _detail, http_status = asyncio.run(bot.shopaikey_minimax_voice_clone("file-123", requested_voice_id))

    assert status == "PASS"
    assert http_status == 200
    assert payload["provider_voice_id"] == requested_voice_id
    assert payload["voice_id"] == requested_voice_id
    assert payload["requested_voice_id"] == requested_voice_id
    assert requests[0]["json"]["voice_id"] == requested_voice_id


def test_shopaikey_voice_clone_success_base_resp_zero(monkeypatch):
    _patch_shopaikey_voice_env(monkeypatch)
    response = FakeResponse({"base_resp": {"status_code": 0}, "extra_info": "ok"})
    _patch_async_client(monkeypatch, bot, response)

    status, payload, _detail, _http_status = asyncio.run(
        bot.shopaikey_minimax_voice_clone("file-456", "toanaas-voice-user456-20260628")
    )

    assert status == "PASS"
    assert payload["provider_voice_id"] == "toanaas-voice-user456-20260628"


def test_shopaikey_voice_clone_upload_extracts_file_id(monkeypatch):
    _patch_shopaikey_voice_env(monkeypatch)
    response = FakeResponse({"base_resp": {"status_code": 0}, "file": {"file_id": "file-from-upload"}})
    requests = _patch_async_client(monkeypatch, bot, response)

    status, file_id, _detail, http_status = asyncio.run(bot.shopaikey_minimax_upload_voice_sample(b"abc", filename="sample.mp3"))

    assert status == "PASS"
    assert file_id == "file-from-upload"
    assert http_status == 200
    assert requests[0]["data"]["purpose"] == "voice_clone"


def test_shopaikey_voice_clone_does_not_require_voice_id_in_response(monkeypatch):
    _patch_shopaikey_voice_env(monkeypatch)
    requested_voice_id = "toanaas-voice-no-response-20260628"
    response = FakeResponse({"base_resp": {"status_code": 0}, "demo_audio": "abcd"})
    _patch_async_client(monkeypatch, bot, response)

    status, payload, _detail, _http_status = asyncio.run(bot.shopaikey_minimax_voice_clone("file-789", requested_voice_id))

    assert status == "PASS"
    assert payload["provider_voice_id"] == requested_voice_id


def test_shopaikey_voice_clone_rejects_invalid_requested_voice_id(monkeypatch):
    _patch_shopaikey_voice_env(monkeypatch)
    monkeypatch.setattr(bot.httpx, "AsyncClient", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("provider must not be called")))

    status, payload, detail, http_status = asyncio.run(bot.shopaikey_minimax_voice_clone("file-123", "bad id !"))

    assert status == "FAIL_BAD_REQUEST"
    assert payload == {}
    assert detail == "invalid_requested_voice_id"
    assert http_status == 0


def test_custom_voice_pipeline_saves_requested_voice_id_after_clone_success(tmp_path):
    requested_voice_id = "toanaas-voice-user123-20260628"
    result, captured = asyncio.run(_run_pipeline_with_clone_payload(tmp_path, {}, seed=requested_voice_id))

    assert result.ok is True
    assert result.provider_voice_id == requested_voice_id
    assert captured["clone_voice_id"] == requested_voice_id
    assert captured["finalize"]["provider_voice_id"] == requested_voice_id
    assert result.metadata["requested_provider_voice_id"] == requested_voice_id


def test_custom_voice_rejects_zero_byte_sample_before_provider(tmp_path):
    sample = tmp_path / "empty.mp3"
    sample.write_bytes(b"")

    result = asyncio.run(voice_clone_pipeline.process_custom_voice_create(
        user_id=1,
        sample_path=sample,
        display_name="Voice test",
        product_context="showroom",
        profile_id=1,
    ))

    assert result.ok is False
    assert result.error_code == "sample_missing_or_empty"
    assert result.provider_called is False
    assert "chưa trừ Xu" in result.safe_public_message


def test_custom_voice_rejects_over_20mb_sample_before_provider(tmp_path):
    sample = tmp_path / "large.mp3"
    with sample.open("wb") as handle:
        handle.seek((20 * 1024 * 1024) + 1)
        handle.write(b"x")

    result = asyncio.run(voice_clone_pipeline.process_custom_voice_create(
        user_id=1,
        sample_path=sample,
        display_name="Voice test",
        product_context="showroom",
        profile_id=1,
    ))

    assert result.ok is False
    assert result.error_code == "sample_too_large"
    assert result.provider_called is False
    assert "20MB" in result.safe_public_message


def test_custom_voice_short_sample_clean_message(tmp_path):
    sample = tmp_path / "short.wav"
    with wave.open(str(sample), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\0\0" * 16000)

    result = asyncio.run(voice_clone_pipeline.process_custom_voice_create(
        user_id=1,
        sample_path=sample,
        display_name="Voice test",
        product_context="showroom",
        profile_id=1,
    ))

    assert result.ok is False
    assert result.error_code == "sample_duration_too_short"
    assert "Mẫu giọng hơi ngắn" in result.safe_public_message
    assert "một người nói" in result.safe_public_message
    _assert_product_clean(result.safe_public_message)


def test_custom_voice_unsupported_extension_clean_message(tmp_path):
    sample = tmp_path / "sample.txt"
    sample.write_bytes(b"audio")

    result = asyncio.run(voice_clone_pipeline.process_custom_voice_create(
        user_id=1,
        sample_path=sample,
        display_name="Voice test",
        product_context="showroom",
        profile_id=1,
    ))

    assert result.ok is False
    assert result.error_code == "unsupported_audio_extension"
    assert "mp3, m4a hoặc wav" in result.safe_public_message
    _assert_product_clean(result.safe_public_message)


def test_shopaikey_minimax_t2a_v2_parses_hex_audio(monkeypatch):
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "sk-test")
    monkeypatch.setattr(bot, "SHOPAIKEY_TTS_BASE_URL", "https://api.shopaikey.test")
    monkeypatch.setattr(bot, "MINIMAX_TTS_ENDPOINT", "/tts/minimax/t2a_v2")
    monkeypatch.setattr(bot, "MINIMAX_TTS_MODEL", "speech-02-hd")
    response = FakeResponse({"data": {"audio": b"MP3".hex()}})
    requests = _patch_async_client(monkeypatch, bot, response)

    status, audio_bytes, _detail, http_status = asyncio.run(bot.shopaikey_minimax_tts_bytes("Xin chao", voice_id="voice-real-1"))

    assert status == "PASS"
    assert audio_bytes == b"MP3"
    assert http_status == 200
    assert requests[0]["json"]["voice_setting"]["voice_id"] == "voice-real-1"


def test_key4u_tts_parses_hex_audio(monkeypatch):
    config = Key4UConfig(
        enabled=True,
        api_key="key4u-test",
        voice_base_url="https://voice.key4u.shop/api/v1",
        voice_tts_endpoint="/tts",
        tts_alt_model="speech-2.6-hd",
    )
    provider = Key4UProvider(config)
    response = FakeResponse({"status": "ok", "audio": b"KEY4U".hex()})
    requests = _patch_async_client(monkeypatch, key4u_provider, response)

    result = asyncio.run(provider.voice_tts_fallback("Xin chao", voice_id="voice-real-2"))

    assert result["ok"] is True
    assert result["output_bytes"] == b"KEY4U"
    assert requests[0]["json"]["output_format"] == "hex"
    assert requests[0]["json"]["voice_setting"]["voice_id"] == "voice-real-2"


def test_key4u_tts_not_used_as_clone_route():
    attempts = bot.voice_clone_provider_route_attempts(
        {
            "ready": True,
            "shopaikey_configured": False,
            "key4u_configured": True,
            "fish_audio_configured": False,
            "elevenlabs_configured": False,
        },
        admin_access=True,
    )

    assert attempts
    name, _upload_call, clone_call, tts_call = attempts[0]
    assert name == "key4u_minimax"
    assert clone_call is bot.key4u_minimax_voice_clone
    assert clone_call is not bot.key4u_minimax_tts_bytes
    assert tts_call is not clone_call


def test_saved_custom_voice_tts_uses_provider_voice_id(tmp_path):
    calls = []

    async def execute_tts_func(_text, provider_voice_id="", **_kwargs):
        calls.append(provider_voice_id)
        return {"output_bytes": b"saved-voice-audio"}

    result = asyncio.run(voice_clone_pipeline.process_voice_tts(
        user_id=1,
        text="Xin chao",
        selected_voice_option=55,
        product_context="showroom",
        output_path=str(tmp_path / "tts.mp3"),
        get_profile_func=lambda *_args, **_kwargs: {
            "id": 55,
            "display_name": "Voice da luu",
            "provider_voice_id": "real-provider-voice-55",
        },
        execute_tts_func=execute_tts_func,
    ))

    assert result.ok is True
    assert calls == ["real-provider-voice-55"]
    assert calls[0] != "55"


def test_voice_provider_failure_clean_copy_no_technical_words():
    text = bot.voice_clone_product_failure_text("vi", "provider=shopaikey_minimax route_errors http_status provider_voice_id")

    assert "TOAN AAS chưa tạo được voice" in text
    _assert_product_clean(text)


def test_voice_product_no_provider_key4u_shopaikey_minimax_words(monkeypatch):
    monkeypatch.setattr(bot, "count_successful_custom_voice_profiles", lambda *_args, **_kwargs: 0)
    text = "\n".join([
        bot.voice_clone_product_failure_text("vi", "key4u shopaikey minimax provider"),
        bot.voice_clone_quote_text({"id": 1, "user_id": 1}, "vi"),
    ])

    _assert_product_clean(text)


def test_admin_product_ui_same_as_user_after_provider_failure(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: bool(uid == bot.ADMIN_ID))
    user_text = bot.voice_clone_product_failure_text("vi", "provider_error")
    admin_text = bot.voice_clone_product_failure_text("vi", "provider_error")

    assert admin_text == user_text
    _assert_product_clean(admin_text)
