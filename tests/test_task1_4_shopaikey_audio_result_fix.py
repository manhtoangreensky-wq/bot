import asyncio
import inspect

import bot


def test_shopaikey_official_tts_url_exact(monkeypatch):
    monkeypatch.setattr(bot, "SHOPAIKEY_TTS_BASE_URL", "https://api.shopaikey.com")
    monkeypatch.setattr(bot, "SHOPAIKEY_TTS_ENDPOINT", "/tts/minimax/t2a_v2")
    assert bot.shopaikey_tts_final_url() == "https://api.shopaikey.com/tts/minimax/t2a_v2"


def test_shopaikey_tts_payload_minimax_official(monkeypatch):
    monkeypatch.setattr(bot, "SHOPAIKEY_TTS_MODEL", "speech-2.6-turbo")
    payload = bot.shopaikey_official_tts_payload("Xin chao", voice_id="voice-1")
    assert payload == {
        "model": "speech-2.6-turbo",
        "text": "Xin chao",
        "voice_setting": {"voice_id": "voice-1"},
        "audio_setting": {"format": "mp3"},
    }
    assert "input" not in payload
    assert "response_format" not in payload


def test_shopaikey_tts_default_voice_matches_support():
    assert bot.SHOPAIKEY_TTS_DEFAULT_VOICE == "Vietnamese_Cute_Girl_v1"
    assert bot.SHOPAIKEY_TTS_VOICE == "Vietnamese_Cute_Girl_v1"


def test_shopaikey_tts_hex_audio_success():
    expected = b"\x01\x02" * 300
    audio, detail, http_status = asyncio.run(
        bot.resolve_shopaikey_tts_audio_bytes({"base_resp": {"status_code": 1}, "data": {"audio": expected.hex()}})
    )
    assert audio == expected
    assert "encoding=hex" in detail
    assert http_status == 0


def test_shopaikey_tts_url_audio_success(monkeypatch):
    expected = b"real-audio" * 100

    async def fake_download(url, timeout_seconds=60.0):
        assert url == "https://cdn.example.com/result.mp3"
        return expected, "http=200", 200

    monkeypatch.setattr(bot, "_download_audio_url_bytes", fake_download)
    audio, detail, http_status = asyncio.run(
        bot.resolve_shopaikey_tts_audio_bytes({"url": "https://cdn.example.com/result.mp3"})
    )
    assert audio == expected
    assert "audio_url=yes" in detail
    assert http_status == 200


def test_shopaikey_suno_submit_and_fetch_urls_exact(monkeypatch):
    monkeypatch.setattr(bot, "SHOPAIKEY_SUNO_BASE_URL", "https://api.shopaikey.com/suno")
    monkeypatch.setattr(bot, "SHOPAIKEY_MUSIC_ENDPOINT", "/submit/music")
    monkeypatch.setattr(bot, "SHOPAIKEY_MUSIC_STATUS_ENDPOINT", "/fetch/{taskId}")
    assert bot.shopaikey_suno_final_url(bot.SHOPAIKEY_MUSIC_ENDPOINT) == "https://api.shopaikey.com/suno/submit/music"
    assert bot.shopaikey_suno_fetch_final_url("task-123") == "https://api.shopaikey.com/suno/fetch/task-123"
    assert "/suno/suno/" not in bot.shopaikey_suno_fetch_final_url("task-123")


def test_shopaikey_suno_submit_payload_official(monkeypatch):
    monkeypatch.setattr(bot, "SHOPAIKEY_MUSIC_MODEL", "chirp-fenix")
    payload = bot.shopaikey_suno_submit_payload(
        "Nhac nen",
        title="TOAN AAS",
        tags="tech",
        instrumental=False,
    )
    assert payload == {
        "mv": "chirp-fenix",
        "make_instrumental": False,
        "gpt_description_prompt": "Nhac nen",
        "title": "TOAN AAS",
        "tags": "tech",
    }


def test_shopaikey_suno_task_id_parser_supports_official_and_nested():
    assert bot.extract_shopaikey_suno_task_id({"code": "success", "data": "task-official"}) == "task-official"
    assert bot.extract_shopaikey_suno_task_id({"data": {"task_id": "task-nested"}}) == "task-nested"
    assert bot.extract_shopaikey_suno_task_id({"result": {"taskId": "task-result"}}) == "task-result"


def test_shopaikey_suno_fetch_parser_requires_audio_for_success():
    processing = {"code": "success", "data": {"status": "processing"}}
    completed_without_audio = {"code": "success", "data": {"status": "completed", "data": []}}
    completed = {
        "code": "success",
        "data": {
            "status": "completed",
            "data": [{"audio_url": "https://cdn.example.com/song.mp3"}],
        },
    }
    assert bot.normalize_shopaikey_suno_fetch_status(processing, 200) == "PROCESSING"
    assert bot.normalize_shopaikey_suno_fetch_status(completed_without_audio, 200) == "COMPLETED_NO_AUDIO"
    assert bot.normalize_shopaikey_suno_fetch_status(completed, 200) == "SUCCESS"
    assert bot.extract_shopaikey_suno_audio_urls(completed) == ["https://cdn.example.com/song.mp3"]


def test_shopaikey_suno_audio_parser_handles_nested_url_keys():
    payload = {
        "result": {
            "clips": [
                {"stream_url": "https://cdn.example.com/audio/clip"},
                {"url": "https://cdn.example.com/final.mp3"},
            ]
        }
    }
    assert bot.extract_shopaikey_suno_audio_urls(payload) == [
        "https://cdn.example.com/audio/clip",
        "https://cdn.example.com/final.mp3",
    ]


def test_audio_public_commands_are_admin_guarded_and_registered():
    status_source = inspect.getsource(bot.cmd_audio_public_status)
    open_source = inspect.getsource(bot.cmd_audio_public_open_safe)
    app_source = inspect.getsource(bot.lifespan)
    assert "is_admin_user" in status_source
    assert "is_admin_or_owner" in open_source
    assert 'CommandHandler("audio_public_status", cmd_audio_public_status)' in app_source
    assert 'CommandHandler("audio_public_open_safe", cmd_audio_public_open_safe)' in app_source


def test_audio_public_open_safe_requires_full_suno_smoke(monkeypatch):
    monkeypatch.setattr(bot, "get_minimax_voice_readiness", lambda: {"ready": True, "missing_env": []})
    monkeypatch.setattr(bot, "get_minimax_voice_clone_readiness", lambda: {"ready": True})
    monkeypatch.setattr(bot, "get_suno_music_readiness", lambda: {"ready": True, "missing_env": []})
    monkeypatch.setattr(bot, "voice_pricing_configured", lambda: True)
    monkeypatch.setattr(bot, "music_pricing_configured", lambda: True)
    monkeypatch.setattr(bot, "SUNO_ALLOW_PROCESSING_GATE", False)

    def fake_result(*names):
        if "minimax_tts" in names:
            return {"status": "PASS"}
        if "key4u_suno_job" in names:
            return {"status": "SUCCESS"}
        return {"status": "PASS"}

    monkeypatch.setattr(bot, "preferred_tool_test_result", fake_result)
    source = inspect.getsource(bot.cmd_audio_public_open_safe)
    assert 'music_fetch_status == "PASS_FULL_RESULT"' in source
    assert "SUNO_ALLOW_PROCESSING_GATE" in source


def test_runtime_multiline_env_warning_is_explicit():
    source = inspect.getsource(bot.cmd_runtime)
    assert "TELEGRAM_UPDATE_MODE=webhook" in source
    assert "BOT_USERNAME=toanaasbot" in source


def test_zero_xu_discount_copy_does_not_claim_deduction():
    text = bot.member_discount_display_line({
        "base_cost": 10,
        "discount_xu": 10,
        "discount_rate": 100,
        "final_cost": 0,
        "badge": "VIP",
    })
    assert "Sau ưu đãi: 0 Xu" in text
    assert "Đã trừ: 0 Xu" not in text


def test_key4u_canonical_audio_urls_unchanged():
    assert bot.key4u_minimax_final_url(bot.KEY4U_TTS_ENDPOINT) == "https://api.key4u.shop/minimax/v1/t2a_v2"
    assert bot.key4u_suno_final_url(bot.KEY4U_SUNO_CREATE_ENDPOINT) == "https://api.key4u.shop/suno/submit/music"
