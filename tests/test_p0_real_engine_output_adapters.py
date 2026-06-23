import asyncio

import bot


def _admin_only(monkeypatch, admin_id=1):
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: str(uid) == str(admin_id))


def test_music_song_missing_adapter_uses_exact_admin_copy(monkeypatch):
    _admin_only(monkeypatch)
    monkeypatch.setattr(
        bot,
        "get_suno_music_readiness",
        lambda: {
            "ready": False,
            "public_enabled": False,
            "missing_env": ["SUNO_API_KEY"],
            "fetch_ready": False,
            "download_ready": False,
            "full_result_ok": False,
            "reason": "missing",
        },
    )
    monkeypatch.setattr(bot, "music_ai_public_processing_ready", lambda _readiness=None: False)

    decision = bot.can_user_access_product_engine(
        1,
        "music_song",
        "confirm",
        is_provider_call=True,
        is_paid_job=True,
        confirm_paid=True,
        admin_interactive_confirm=True,
    )

    assert decision["allowed"] is False
    assert decision["message"] == "⚙️ Admin test chưa chạy được: music_song chưa có kết quả đầy đủ từ provider hoặc chưa có endpoint tải file nhạc. Không gọi provider mới và không trừ Xu."


def test_execute_engine_music_rejects_ok_without_provider_job_or_bytes(monkeypatch):
    _admin_only(monkeypatch)
    monkeypatch.setattr(
        bot,
        "get_suno_music_readiness",
        lambda: {
            "ready": True,
            "public_enabled": False,
            "missing_env": [],
            "fetch_ready": True,
            "download_ready": True,
            "full_result_ok": True,
            "reason": "configured",
        },
    )
    monkeypatch.setattr(bot, "music_ai_public_processing_ready", lambda _readiness=None: False)

    async def fake_submit(*_args, **_kwargs):
        return {"ok": True, "status": "PASS_SUBMITTED", "provider": "fake_suno", "task_id": "", "detail": "accepted_without_id"}

    monkeypatch.setattr(bot, "submit_music_generation_job", fake_submit)
    result = asyncio.run(
        bot.execute_engine(
            "music_song",
            {"result": {"song_product": "full", "selected_prompt": "test"}},
            {
                "user_id": 1,
                "entry_source": bot.ENGINE_ENTRY_SOURCE_PRODUCT,
                "confirm_paid": True,
                "admin_interactive_confirm": True,
                "is_paid_job": True,
                "admin_smoke": True,
            },
        )
    )

    assert result["ok"] is False
    assert result["status"] == "NO_PROVIDER_JOB"
    assert result.get("job_created") is not True


def test_execute_engine_music_accepts_real_output_bytes_without_fake_pending(monkeypatch):
    _admin_only(monkeypatch)
    monkeypatch.setattr(
        bot,
        "get_suno_music_readiness",
        lambda: {
            "ready": True,
            "public_enabled": False,
            "missing_env": [],
            "fetch_ready": True,
            "download_ready": True,
            "full_result_ok": True,
            "reason": "configured",
        },
    )
    monkeypatch.setattr(bot, "music_ai_public_processing_ready", lambda _readiness=None: False)

    async def fake_submit(*_args, **_kwargs):
        return {"ok": True, "status": "PASS", "provider": "fake_suno", "task_id": "", "output_bytes": b"audio"}

    monkeypatch.setattr(bot, "submit_music_generation_job", fake_submit)
    result = asyncio.run(
        bot.execute_engine(
            "music_song",
            {"result": {"song_product": "half", "selected_prompt": "test"}},
            {
                "user_id": 1,
                "entry_source": bot.ENGINE_ENTRY_SOURCE_PRODUCT,
                "confirm_paid": True,
                "admin_interactive_confirm": True,
                "is_paid_job": True,
                "admin_smoke": True,
            },
        )
    )

    assert result["ok"] is True
    assert result["status"] == "PASS"
    assert result["job_created"] is False
    assert result["has_output_bytes"] is True


def test_deepgram_admin_readiness_uses_api_key_even_when_key4u_public_not_ready(monkeypatch):
    _admin_only(monkeypatch)
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_ENABLED", True)
    monkeypatch.setattr(bot, "ASR_PROVIDER", "key4u")
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "deepgram-key")
    monkeypatch.setattr(bot, "key4u_asr_public_ready", lambda: False)
    monkeypatch.setattr(bot, "key4u_asr_configured", lambda: False)
    monkeypatch.setattr(bot, "shopaikey_stt_public_ready", lambda: False)
    monkeypatch.setattr(bot, "video_translation_provider_available", lambda: True)
    monkeypatch.setattr(bot, "video_tts_provider_available", lambda: True)

    readiness = bot._product_engine_readiness("subtitle_auto", bot.VIDEO_SUBTITLE_MODE_CREATE)

    assert "asr_adapter_missing" not in bot.engine_technical_missing(readiness)


def test_deepgram_adapter_returns_timestamped_srt_and_vtt(monkeypatch):
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "deepgram-key")
    data = {
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {
                            "transcript": "xin chao",
                            "words": [
                                {"word": "xin", "start": 0.0, "end": 0.3},
                                {"word": "chao", "start": 0.35, "end": 0.8},
                            ],
                        }
                    ]
                }
            ]
        }
    }

    async def fake_diagnostic(*_args, **_kwargs):
        return {"status": "PASS", "http_status": 200, "transcript": "xin chao", "transcript_json": data}

    monkeypatch.setattr(bot.AgentDeepgram, "diagnostic", fake_diagnostic)
    result = asyncio.run(bot.deepgram_asr_adapter(b"audio", "audio/wav"))

    assert result["ok"] is True
    assert "-->" in result["srt"]
    assert result["vtt"].startswith("WEBVTT")
    assert result["srt_blocks"] == 1


def test_deepgram_adapter_fails_when_timestamp_blocks_missing(monkeypatch):
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "deepgram-key")

    async def fake_diagnostic(*_args, **_kwargs):
        return {"status": "PASS", "http_status": 200, "transcript": "xin chao", "transcript_json": {"results": {"channels": [{"alternatives": [{"transcript": "xin chao"}]}]}}}

    monkeypatch.setattr(bot.AgentDeepgram, "diagnostic", fake_diagnostic)
    result = asyncio.run(bot.deepgram_asr_adapter(b"audio", "audio/wav"))

    assert result["ok"] is False
    assert result["status"] == "srt_generation_failed"


def test_video_multiscene_names_queue_missing_exactly(monkeypatch):
    monkeypatch.setattr(bot, "SHOPAIKEY_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "configured")
    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_URL", "https://example.test/video")
    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_MODEL", "model")
    monkeypatch.setattr(bot, "KEY4U_ENABLED", False)
    monkeypatch.setattr(bot, "video_multiscene_stitching_available", lambda: True)
    monkeypatch.setattr(bot, "video_multiscene_public_ready", lambda _scene_count: False)
    monkeypatch.setattr(bot, "save_multiscene_job_record", None)

    readiness = bot._product_engine_readiness("video_multiscene", "3")

    assert "queue_missing" in bot.engine_technical_missing(readiness)


def test_voice_admin_diagnostic_includes_structured_route_error_fields():
    route_error = bot.voice_clone_route_error(
        "key4u_minimax",
        "clone",
        "key4u_minimax/clone",
        "FAIL_PROVIDER_ERROR",
        "provider rejected voice id",
        http_status=400,
        provider_status="bad_request",
        output_bytes=0,
        payload_fields=["file_id", "voice_id", "model", "text"],
    )

    text = bot.voice_clone_admin_preview_failure_text(
        {"ready": True, "routes": ["key4u_minimax"], "tts_smoke": "PASS", "clone_smoke": "FAIL"},
        output_bytes=0,
        route_errors=[route_error],
        error="voice_routes_failed",
    )

    assert "adapter=key4u_minimax" in text
    assert "operation=clone" in text
    assert "http_status=400" in text
    assert "provider_status=bad_request" in text
    assert "payload_fields=file_id,voice_id,model,text" in text
    assert "api_key" not in text.lower()
    assert "bearer " not in text.lower()


def test_voice_clone_fallback_routes_include_configured_clone_providers_but_not_edge(monkeypatch):
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "")
    monkeypatch.setattr(bot, "KEY4U_API_KEY", "")
    monkeypatch.setattr(bot, "FISH_AUDIO_KEY", "fish-key")
    monkeypatch.setattr(bot, "ELEVENLABS_API_KEY", "eleven-key")
    monkeypatch.setattr(bot, "edge_tts", object())

    readiness = bot.get_minimax_voice_clone_readiness()

    assert "fish_audio" in readiness["routes"]
    assert "elevenlabs" in readiness["routes"]
    assert all("edge" not in route for route in readiness["routes"])
